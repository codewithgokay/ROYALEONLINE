"""
Royale Online — Ölüm Dedektörü & Oto-Av Botu
=============================================
• Ekranı sürekli tarar; köşede "yeniden başla" / "şehirde yeniden başla" metnini yakalar.
• Metni bulunca otomatik tıklar, karakteri hedef noktaya götürür ve oto-av tuşuna basar.
• Tüm ayarlar GUI üzerinden yapılır; hiç kod değişikliği gerekmez.

Gereksinimler:
  pip install pillow pytesseract pyautogui pynput mss pygetwindow
  macOS : brew install tesseract tesseract-lang
  Windows: https://github.com/UB-Mannheim/tesseract/wiki (installer)
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import queue
import json
import sys
import os
from macro_recorder import MacroRecorder

IS_WINDOWS = sys.platform == "win32"
IS_MAC     = sys.platform == "darwin"

# ── Windows DPI Scaling fix ───────────────────────────────────────────────────
# MUST run before any screen capture or GUI starts.
# Without this, 125%/150% DPI scaling makes mss capture the wrong region.
if IS_WINDOWS:
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()   # Fallback (Win Vista+)
        except Exception:
            pass

try:
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
        kCGWindowListExcludeDesktopElements,
    )
    QUARTZ_OK = True
except ImportError:
    QUARTZ_OK = False

try:
    from AppKit import NSWorkspace
    APPKIT_OK = True
except ImportError:
    APPKIT_OK = False

# Windows: pygetwindow for window listing & focus
try:
    import pygetwindow as pgw
    PGWIN_OK = True
except ImportError:
    pgw = None
    PGWIN_OK = False

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
except ImportError:
    pyautogui = None

try:
    from PIL import Image, ImageGrab, ImageEnhance, ImageFilter
except ImportError:
    Image = ImageGrab = ImageEnhance = ImageFilter = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    import pynput.keyboard as kb_module
    kb_ctrl = kb_module.Controller()
except ImportError:
    kb_module = kb_ctrl = None

# --- Tesseract Path Discovery (macOS + Windows) ---
if pytesseract:
    _tess_candidates = []
    if IS_MAC:
        _tess_candidates = [
            "/opt/homebrew/bin/tesseract",   # M1/M2/M3 Mac
            "/usr/local/bin/tesseract",      # Intel Mac
            "/usr/bin/tesseract",
        ]
    elif IS_WINDOWS:
        _tess_candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
    for _p in _tess_candidates:
        if os.path.exists(_p):
            pytesseract.pytesseract.tesseract_cmd = _p
            break

# Runtime verify: actually call tesseract and check Turkish language pack
_TESS_OK  = False
_TESS_TUR = False
if pytesseract:
    try:
        pytesseract.get_tesseract_version()
        _TESS_OK = True
        # Check Turkish language pack
        langs = pytesseract.get_languages(config='')
        _TESS_TUR = 'tur' in langs
    except Exception:
        pass

# ── Renk paleti ────────────────────────────────────────────────────────────────
BG       = "#0f0f1a"
SURFACE  = "#1e2040"
SURFACE2 = "#1a2a4a"
ACCENT   = "#e94560"
ACCENT2  = "#1a4a80"
SUCCESS  = "#22c55e"
DANGER   = "#ef4444"
WARNING  = "#f59e0b"
INFO     = "#60cdff"
FG       = "#e8eef6"
FG_DIM   = "#b0bec5"
BORDER   = "#2a3a5a"
GOLD     = "#fbbf24"

# ── Font (platform-aware) ────────────────────────────────────────────────────
if IS_MAC:
    _FONT_FAMILY = "SF Pro Display"
elif IS_WINDOWS:
    _FONT_FAMILY = "Segoe UI"
else:
    _FONT_FAMILY = "Ubuntu"

FONT    = (_FONT_FAMILY, 13)
FONT_SM = (_FONT_FAMILY, 11)
FONT_LG = (_FONT_FAMILY, 18, "bold")
FONT_XL = (_FONT_FAMILY, 28, "bold")


def make_btn(parent, *, text, bg, fg="black", active_bg=None,
             font=None, command=None, **kw):
    """macOS'ta native aqua stilini baskılayan buton factory'si.
    highlightbackground=bg sayesinde sistem beyaz çerçeveyi/arka planı
    override etmez ve fg rengi her zaman okunabilir kalır.
    """
    if active_bg is None:
        active_bg = bg
    if font is None:
        font = FONT_SM
    btn = tk.Button(
        parent,
        text=text,
        bg=bg,
        fg=fg,
        activebackground=active_bg,
        activeforeground=fg,
        font=font,
        relief="flat",
        cursor="hand2",
        highlightbackground=bg,   # <── macOS aqua override'ı kaldırır
        highlightthickness=1,
        command=command,
        **kw,
    )
    return btn

# ── Sabitler ──────────────────────────────────────────────────────────────────
# Sayfaya özgü, yeterince uzun ifadeler — genel kelimelerden kaçın
DEFAULT_DEATH_TEXTS = [
    "şehirde yeniden başla",
    "şehirde yeniden",
    "yeniden başla’ya",
]


# ── Bağımlılık kontrolü ───────────────────────────────────────────────────────
def check_dependencies():
    missing = []
    if pyautogui is None:
        missing.append("pyautogui")
    if Image is None or ImageGrab is None:
        missing.append("Pillow")
    if pytesseract is None:
        missing.append("pytesseract")
    if kb_module is None:
        missing.append("pynput")
    return missing


def get_startup_diagnostics() -> list:
    """Bot açılışında Log sekmesine yazılacak sistem bilgisi."""
    lines = []
    lines.append(f"💻 Platform  : {sys.platform} | Python {sys.version.split()[0]}")

    # Tesseract
    tess_cmd = "N/A"
    if pytesseract:
        tess_cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", "N/A")
    if _TESS_OK:
        lines.append(f"✅ Tesseract : {tess_cmd}")
        if _TESS_TUR:
            lines.append("✅ Türkçe OCR: Dil paketi kurulu — ölüm ekranı tanınabilir")
        else:
            lines.append("⚠️ Türkçe OCR: DİL PAKETİ EKSİK! Ölüm metni tanınamaz.")
            lines.append("   → Tesseract'ı tekrar kur, kurulumda 'Turkish' seç!")
    else:
        lines.append("❌ Tesseract : BULUNAMADI — OCR çalışmaz, ölüm tanınamaz!")
        if IS_WINDOWS:
            lines.append("   → https://github.com/UB-Mannheim/tesseract/wiki")
        else:
            lines.append("   → brew install tesseract tesseract-lang")

    # DPI (Windows)
    if IS_WINDOWS:
        try:
            import ctypes
            dpi = ctypes.windll.user32.GetDpiForSystem()
            scale = round(dpi / 96 * 100)
            status = "✅" if scale == 100 else "⚠️"
            lines.append(f"{status} Windows DPI: {dpi} ({scale}%) — DPI-Aware mod aktif")
            if scale != 100:
                lines.append("   → DPI!=100% tespit edildi. Koordinatlar otomatik düzeltildi.")
        except Exception:
            pass

    # Screen capture
    lines.append(f"📸 Ekran yakalama: {'mss ✅' if MSS_OK else 'PIL ImageGrab (yedek)'}")

    # Window picker
    if IS_WINDOWS:
        lines.append(f"🪟 Pencere listesi: {'pygetwindow ✅' if PGWIN_OK else 'YOK — pip install pygetwindow'}")
    else:
        lines.append(f"🪟 Pencere listesi: {'Quartz (macOS) ✅' if QUARTZ_OK else 'YOK'}")

    return lines


def get_active_app_name() -> str:
    """Ön plandaki uygulamanın adını döndürür (platform-aware)."""
    # macOS
    if APPKIT_OK:
        try:
            info = NSWorkspace.sharedWorkspace().activeApplication()
            return (info or {}).get("NSApplicationName", "")
        except Exception:
            return ""
    # Windows
    if IS_WINDOWS and PGWIN_OK:
        try:
            w = pgw.getActiveWindow()
            return w.title if w else ""
        except Exception:
            return ""
    return ""


# ── Pencere listesi (platform-aware) ────────────────────────────────────────
def get_windows():
    """
    Tüm görünür pencereleri döndürür.
    Her eleman: {"app": str, "title": str, "x": int, "y": int, "w": int, "h": int}
    macOS: Quartz / Windows: pygetwindow
    """
    # ── macOS (Quartz) ───────────────────────────────────────────────────────
    if QUARTZ_OK:
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
            kCGNullWindowID,
        )
        results = []
        for w in window_list:
            bounds = w.get("kCGWindowBounds", {})
            width  = int(bounds.get("Width",  0))
            height = int(bounds.get("Height", 0))
            if width < 50 or height < 50:
                continue
            layer = w.get("kCGWindowLayer", 999)
            if layer > 0:
                continue
            app   = w.get("kCGWindowOwnerName", "?") or "?"
            title = w.get("kCGWindowName",      "")  or ""
            x     = int(bounds.get("X", 0))
            y     = int(bounds.get("Y", 0))
            wid   = int(w.get("kCGWindowNumber", 0))
            results.append({"app": app, "title": title,
                            "x": x, "y": y, "w": width, "h": height, "wid": wid})
        results.sort(key=lambda r: r["app"].lower())
        return results

    # ── Windows (pygetwindow) ────────────────────────────────────────────────
    if IS_WINDOWS and PGWIN_OK:
        results = []
        try:
            for win in pgw.getAllWindows():
                if not win.visible:
                    continue
                if win.width < 50 or win.height < 50:
                    continue
                title = win.title or ""
                results.append({
                    "app":   title,
                    "title": title,
                    "x":     win.left,
                    "y":     win.top,
                    "w":     win.width,
                    "h":     win.height,
                    "_win_obj": win,   # kept for focus use
                })
        except Exception:
            pass
        results.sort(key=lambda r: r["app"].lower())
        return results

    return []


# ── Ekran yakalama & OCR ──────────────────────────────────────────────────────
try:
    import mss as _mss_module
    _mss_instance = _mss_module.MSS()   # mss.mss() deprecated → use MSS()
    MSS_OK = True
except Exception:
    _mss_instance = None
    MSS_OK = False


def capture_region(x, y, w, h):
    """Ekranın belirli bir bölgesini yakalar. mss > ImageGrab (120x hızlı)."""
    if MSS_OK and _mss_instance is not None:
        try:
            mon  = {"left": x, "top": y, "width": w, "height": h}
            shot = _mss_instance.grab(mon)
            return Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
        except Exception:
            pass
    # Fallback: PIL ImageGrab
    try:
        return ImageGrab.grab(bbox=(x, y, x + w, y + h))
    except Exception:
        return None


def preprocess_image(img):
    """OCR doğruluğunu artırmak için görüntü ön işleme."""
    img = img.convert("L")                          # Gri tonlama
    img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)  # Büyüt
    img = ImageEnhance.Contrast(img).enhance(2.5)  # Kontrast artır
    img = img.filter(ImageFilter.SHARPEN)           # Keskinleştir
    return img


def ocr_image(img, lang="tur"):
    """Görüntüden metin çıkar. Turkce yoksa Latin+eng ile yeniden dener."""
    if pytesseract is None:
        return ""
    # Önce Turkish ile dene
    if _TESS_TUR:
        try:
            text = pytesseract.image_to_string(img, lang="tur+eng", config="--psm 6")
            return text.lower().strip()
        except Exception:
            pass
    # Turkish yoksa veya hata varsa: sadece eng
    try:
        text = pytesseract.image_to_string(img, config="--psm 6")
        return text.lower().strip()
    except Exception:
        return ""


def find_text_position(img, raw_img, x_offset, y_offset, target_texts):
    """
    Hedef metni görüntüde bul ve tıklanacak koordinatı döndür.
    Başarılı olursa (screen_x, screen_y) döndürür; bulamazsa None.
    """
    try:
        data = pytesseract.image_to_data(
            img,
            lang="tur+eng",
            config="--psm 6",
            output_type=pytesseract.Output.DICT
        )
    except Exception:
        try:
            data = pytesseract.image_to_data(
                img,
                config="--psm 6",
                output_type=pytesseract.Output.DICT
            )
        except Exception:
            return None

    n = len(data["text"])
    scale_x = raw_img.width  / img.width
    scale_y = raw_img.height / img.height

    for i in range(n):
        word = data["text"][i].lower().strip()
        if not word:
            continue
        for target in target_texts:
            if target in word or word in target:
                bx = int(data["left"][i]   * scale_x)
                by = int(data["top"][i]    * scale_y)
                bw = int(data["width"][i]  * scale_x)
                bh = int(data["height"][i] * scale_y)
                cx = x_offset + bx + bw // 2
                cy = y_offset + by + bh // 2
                return (cx, cy)
    return None


# ── Ana Bot sınıfı ────────────────────────────────────────────────────────────
class RoyaleBot:
    def __init__(self, gui_callback):
        self.cb          = gui_callback       # GUI güncellemesi için callback
        self.running     = False
        self.thread      = None
        self.death_count = 0
        self.scan_count  = 0

        # Seçili pencereler (app picker) — birden fazla desteklenir
        self.selected_windows = []   # her dict: {app, title, x, y, w, h, last_death_at}

        # Ayarlar (GUI'den güncellenir)
        self.scan_x      = tk.IntVar(value=0)
        self.scan_y      = tk.IntVar(value=0)
        self.scan_w      = tk.IntVar(value=500)
        self.scan_h      = tk.IntVar(value=300)
        self.scan_ms     = tk.IntVar(value=1000)        # Tarama aralığı (ms)

        self.respawn_key    = tk.StringVar(value="y")    # Yeniden başlatma tuşu
        self.respawn_delay  = tk.DoubleVar(value=8.0)  # Respawn sonrası bekleme (s)
        self.auto_hunt_key  = tk.StringVar(value="k")

        # ── Hareket Makrosu (respawn → oto-av arası) ──────────────────────────
        self.move_macro_recorder = MacroRecorder()
        self.move_macro_path     = tk.StringVar(value="move_macro.json")
        self.move_macro_speed    = tk.DoubleVar(value=1.0)

        # Ölüm tespiti ayarları
        self.death_texts  = list(DEFAULT_DEATH_TEXTS)
        self.cooldown_sec = tk.IntVar(value=20)   # Tekrar tetiklenme engeli (s)




    def start(self):
        if self.running:
            return
        self.running = True
        self.thread  = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _loop(self):
        self.cb("log", "🟢 Bot başlatıldı — ekran taranıyor…")
        while self.running:
            try:
                self._scan_once()
            except Exception as e:
                self.cb("log", f"⚠️ Hata: {e}")
            interval = max(0.2, self.scan_ms.get() / 1000)
            time.sleep(interval)
        self.cb("log", "🔴 Bot durduruldu.")

    def _scan_once(self):
        """
        Seçili tüm pencerelerin ekran bölgelerini bağımsız tara.
        Her pencere kendi koordinatlarından yakalandığından, ön planda
        olmasına gerek yok — çoklu oyun desteği sağlanır.
        """
        cooldown = self.cooldown_sec.get()
        MIN_LEN  = 8
        now      = time.time()

        # Taranacak pencere listesi; hiç seçilmediyse manuel bölgeyi kullan
        if self.selected_windows:
            targets = self.selected_windows
        else:
            if not hasattr(self, "_manual_target"):
                self._manual_target = {
                    "app": "", "title": "",
                    "x": self.scan_x.get(), "y": self.scan_y.get(),
                    "w": self.scan_w.get(), "h": self.scan_h.get(),
                    "last_death_at": 0.0,
                }
            else:
                # Koordinatları güncelle ama last_death_at'ı koru
                self._manual_target.update({
                    "x": self.scan_x.get(), "y": self.scan_y.get(),
                    "w": self.scan_w.get(), "h": self.scan_h.get(),
                })
            targets = [self._manual_target]

        for win in targets:
            # Per-window cooldown
            if now - win.get("last_death_at", 0.0) < cooldown:
                continue

            # Başlık çubuğunu atla: MuMu üst 35px = emülatör başlık
            TITLE_BAR = 35
            x  = win["x"]
            y  = win["y"] + TITLE_BAR
            lw = win["w"]
            lh = win["h"] - TITLE_BAR
            if lh <= 0:
                continue
            raw = capture_region(x, y, lw, lh)

            if raw is None:
                continue

            proc = preprocess_image(raw)
            text = ocr_image(proc)

            self.scan_count += 1
            if self.scan_count % 10 == 0:
                self.cb("scan_count", self.scan_count)

            for target in self.death_texts:
                if len(target) >= MIN_LEN and target in text:
                    app_label = win.get("app", "?") or "?"
                    idx = text.find(target)
                    ctx = text[max(0, idx-20):idx+len(target)+20].replace("\n", " ")
                    self.cb("log", f"💀 Ölüm [{app_label}] @ ({win['x']},{win['y']})")
                    self.cb("log", f"   eşleşen: '{target}'  |  bağlam: '…{ctx}…'")
                    self._handle_death(raw, proc, x, y, win)
                    return   # Bir seferde bir pencereyi işle


    def _ensure_focus(self, win, label: str, step: str) -> bool:
        """
        Pencereyi odakla ve doğrula; başarısız olursa bir kez daha dene.
        Yine başarısız olursa False döner (çağıran uygun aksiyonu alır).
        """
        if win is None:
            return True
        ok = self._focus_win(win)
        if ok:
            self.cb("log", f"✅ [{label}] focus tamam ({step})")
            return True
        # İlk deneme başarısız — 0.3s bekleyip tekrar dene
        self.cb("log", f"⚠️ [{label}] focus kaydı ({step}) — yeniden deneniyor…")
        time.sleep(0.3)
        ok = self._focus_win(win)
        if not ok:
            self.cb("log", f"❌ [{label}] focus alınamadı ({step})")
        return ok

    def _handle_death(self, raw_img, proc_img, x_off, y_off, win=None):
        """Ölüm yönetimi: pencereye odaklan → doğrula → respawn → bekle → yeniden odaklan → hareket → oto-av."""
        # Per-window cooldown timestamp
        if win is not None:
            win["last_death_at"] = time.time()
        app_lbl = (win.get("app", "") or "") if win else ""
        self.cb("status", "💀 Ölüm!")
        if app_lbl:
            self.cb("log", f"💀 [{app_lbl}] ölüm işleniyor…")
        time.sleep(0.3)

        # 0) Pencereye odaklan + doğrula
        if win:
            if not self._ensure_focus(win, app_lbl, "ölüm başlangıcı"):
                self.cb("log", f"❌ [{app_lbl}] pencere odaklanamadı — ölüm işlemi iptal edildi.")
                return

        # 1) Yeniden başlatma tuşuna bas
        rkey = self.respawn_key.get().strip()
        if rkey:
            press_key = rkey.lower() if len(rkey) == 1 else rkey
            self.cb("log", f"🎮 [{app_lbl}] Respawn tuşuna basılıyor: {rkey}")
            pyautogui.press(press_key)
        else:
            self.cb("log", "⚠️ Respawn tuşu tanımlanmamış!")

        # 2) Yükleme bekleme süresi
        delay = max(0.5, self.respawn_delay.get())
        self.cb("log", f"⏳ {delay}s bekleniyor (yükleme)...")
        time.sleep(delay)

        # 2b) Yükleme sonrası focus tekrar doğrula — uzun beklemede kayabilir
        if win:
            self._ensure_focus(win, app_lbl, "yükleme sonrası")

        # 3) Hareket makrosu (respawn → av noktası)
        move_events = self.move_macro_recorder.events
        if move_events:
            self.cb("log", f"🕹️ [{app_lbl}] Hareket makrosu oynatılıyor ({len(move_events)} olay)…")
            self.move_macro_recorder.play(
                speed=self.move_macro_speed.get(),
                log_cb=lambda m: self.cb("log", m),
                stop_check=lambda: not self.running,
            )
            time.sleep(0.2)

        # 5) Oto-av tuşuna bas — son focus doğrulaması
        hunt_key = self.auto_hunt_key.get().strip()
        if hunt_key:
            if win:
                self._ensure_focus(win, app_lbl, "oto-av öncesi")
            self.cb("log", f"🗡️ [{app_lbl}] Oto-av tuşu basılıyor: {hunt_key}")
            pyautogui.press(hunt_key.lower() if len(hunt_key) == 1 else hunt_key)

        self.death_count += 1
        self.cb("death_count", self.death_count)
        self.cb("status", "⚔️ Av devam ediyor…")
        self.cb("log", f"✅ [{app_lbl}] Yeniden başlatma tamamlandı.")

    def _focus_win(self, win: dict) -> bool:
        """
        Belirtilen pencereyi ön plana alır ve focus'u doğrular.
        macOS : AppKit process aktivasyonu + köşe tıklaması
        Windows: pygetwindow.activate() + köşe tıklaması
        True → focus başarılı / doğrulanamadı ama devam edilebilir
        False → app adı biliniyor ve yanlış app ön planda
        """
        if pyautogui is None:
            return True
        app_name = win.get("app", "")

        # 1a) macOS — AppKit process aktivasyonu
        if APPKIT_OK and app_name:
            try:
                from AppKit import NSWorkspace
                NSApplicationActivateIgnoringOtherApps = 2
                for app in NSWorkspace.sharedWorkspace().runningApplications():
                    if app.localizedName() == app_name:
                        app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                        time.sleep(0.15)
                        break
            except Exception:
                pass

        # 1b) Windows — pygetwindow activate
        elif IS_WINDOWS and PGWIN_OK:
            try:
                win_obj = win.get("_win_obj")
                if win_obj:
                    win_obj.activate()
                elif app_name:
                    wins = pgw.getWindowsWithTitle(app_name)
                    if wins:
                        wins[0].activate()
                time.sleep(0.15)
            except Exception:
                pass

        # 2) Köşeye tıkla — doğru pencereyi öne getirir
        try:
            cx = win["x"] + 5
            cy = win["y"] + 5
            pyautogui.click(cx, cy, _pause=False)
            time.sleep(0.25)
        except Exception:
            pass

        # 3) Doğrulama
        if app_name:
            active = get_active_app_name()
            # Windows'ta title bazlı eşleştirme (app_name = pencere başlığı)
            if IS_WINDOWS:
                return app_name in active or active in app_name
            return active == app_name
        return True





# ── GUI ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Royale Online — Ölüm Dedektörü & Oto-Av")
        self.resizable(False, False)
        self.configure(bg=BG)

        missing = check_dependencies()
        if missing:
            messagebox.showerror(
                "Eksik Kütüphane",
                "Şu kütüphaneler eksik:\n" + "\n".join(missing) +
                "\n\nLütfen requirements.txt'i kurun."
            )
            self.destroy()
            return

        self.bot         = RoyaleBot(self._bot_callback)
        self.log_queue   = queue.Queue()
        self.move_rows = []   # GUI hareket satırları

        self._build_ui()
        self._poll_log()

        # Başlangıç tanılama logları — Log sekmesinde görünür
        self.after(200, self._log_startup_diagnostics)

        # Merkeze al
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def _log_startup_diagnostics(self):
        """Başlangıç tanılama bilgilerini Log sekmesine yazar."""
        self._append_log("─" * 48)
        self._append_log("🔧 SİSTEM TANILAMA")
        for line in get_startup_diagnostics():
            self._append_log(line)
        self._append_log("─" * 48)

    # ── Callback (thread-safe) ─────────────────────────────────────────────────
    def _bot_callback(self, event, data):
        self.log_queue.put((event, data))

    def _poll_log(self):
        try:
            while True:
                event, data = self.log_queue.get_nowait()
                if event == "log":
                    self._append_log(data)
                elif event == "status":
                    self.status_var.set(data)
                elif event == "death_count":
                    self.death_var.set(str(data))
                elif event == "scan_count":
                    self.scan_var.set(str(data))
        except queue.Empty:
            pass
        self.after(100, self._poll_log)

    def _append_log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ── Ana UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Başlık ──────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=SURFACE2, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚔️  Royale Online Bot", font=FONT_LG,
                 bg=SURFACE2, fg=ACCENT).pack()
        tk.Label(hdr, text="Ölüm Dedektörü  •  Otomatik Yeniden Başlatma  •  Oto-Av",
                 font=FONT_SM, bg=SURFACE2, fg=FG_DIM).pack(pady=(2, 0))

        # ── İstatistik kartları ──────────────────────────────────────────────
        stats = tk.Frame(self, bg=BG, pady=8)
        stats.pack(fill="x", padx=16)
        self.death_var = tk.StringVar(value="0")
        self.scan_var  = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="⏸️ Bekleniyor…")
        self._stat_card(stats, "💀 Ölüm Sayısı", self.death_var, ACCENT)
        self._stat_card(stats, "🔍 Tarama",      self.scan_var,  INFO)

        tk.Label(self, textvariable=self.status_var,
                 font=(FONT[0], 12, "bold"), bg=BG, fg=GOLD).pack(pady=(0, 4))

        # ── Notebook (sekmeler) ──────────────────────────────────────────────
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook",      background=BG,      borderwidth=0)
        style.configure("TNotebook.Tab",  background=SURFACE, foreground=FG_DIM,
                        padding=[14, 6], font=FONT_SM)
        style.map("TNotebook.Tab",
                  background=[("selected", ACCENT2)],
                  foreground=[("selected", FG)])

        # ── Kontrol butonları (üstte — her zaman görünür) ────────────────────
        ctrl = tk.Frame(self, bg=BG, pady=8)
        ctrl.pack(fill="x", padx=12)

        self.start_btn = make_btn(
            ctrl, text="▶  BAŞLAT",
            font=(FONT[0], 14, "bold"),
            bg=SUCCESS, fg="black", active_bg="#16a34a",
            padx=24, pady=10, command=self._toggle,
        )
        self.start_btn.pack(side="left", fill="x", expand=True)

        make_btn(
            ctrl, text="🪟 Uygulama Seç",
            bg=GOLD, fg="black", active_bg="#d97706",
            padx=14, pady=10, command=self._pick_application,
        ).pack(side="left", padx=(8, 0))


        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Sekmeler
        tab1 = tk.Frame(nb, bg=BG)
        tab2 = tk.Frame(nb, bg=BG)
        tab3 = tk.Frame(nb, bg=BG)
        nb.add(tab1, text=" 🔍 Tarama Bölgesi ")
        nb.add(tab2, text=" ⌨️ Tuşlar & Hedef ")
        nb.add(tab3, text=" 📋 Log ")

        self._build_scan_tab(tab1)
        self._build_key_tab(tab2)
        self._build_log_tab(tab3)

    def _stat_card(self, parent, label, var, color):
        f = tk.Frame(parent, bg=SURFACE, padx=20, pady=8, relief="flat")
        f.pack(side="left", expand=True, padx=8)
        tk.Label(f, text=label, font=FONT_SM, bg=SURFACE, fg=FG_DIM).pack()
        tk.Label(f, textvariable=var, font=(FONT[0], 24, "bold"),
                 bg=SURFACE, fg=color).pack()

    def _refresh_win_list(self):
        """Seçili pencere listesini GUI'de yeniden çizer."""
        for w in self.win_list_frame.winfo_children():
            w.destroy()
        if not self.bot.selected_windows:
            tk.Label(self.win_list_frame,
                     text="  Henüz pencere eklenmedi — '🪟 Uygulama Seç' butonunu kullan",
                     font=(FONT[0], 9), bg=BG, fg=FG_DIM).pack(anchor="w", pady=2)
            return
        for i, win in enumerate(self.bot.selected_windows):
            row_f = tk.Frame(self.win_list_frame, bg=SURFACE2, padx=8, pady=4)
            row_f.pack(fill="x", pady=1)
            label = f"{win['app']}" + (f" — {win['title']}" if win.get('title') else "")
            tk.Label(row_f,
                     text=f"{i+1}. {label}   |   ({win['x']},{win['y']}) {win['w']}×{win['h']}",
                     font=(FONT[0], 9), bg=SURFACE2, fg=INFO, anchor="w").pack(side="left", fill="x", expand=True)
            make_btn(row_f, text="✕",
                     bg=DANGER, fg="black", active_bg="#b91c1c",
                     padx=6, pady=1,
                     command=lambda w=win: self._remove_win(w)
                     ).pack(side="right")

    def _remove_win(self, win: dict):
        """Pencereyi izleme listesinden çıkarır."""
        if win in self.bot.selected_windows:
            self.bot.selected_windows.remove(win)
        self._refresh_win_list()
        self._bot_callback("log", f"🗑️ Pencere kaldırıldı: {win.get('app', '?')}")

    def _clear_all_windows(self):
        """Tüm izlenen pencereleri temizler."""
        self.bot.selected_windows.clear()
        self._refresh_win_list()
        self._bot_callback("log", "🗑️ Tüm pencereler kaldırıldı.")

    # ── Tarama Bölgesi sekmesi ────────────────────────────────────────────────
    def _build_scan_tab(self, parent):
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        pad = tk.Frame(canvas, bg=BG, padx=16, pady=12)
        win_id = canvas.create_window((0, 0), window=pad, anchor="nw")

        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_configure(e):
            canvas.itemconfig(win_id, width=e.width)
        pad.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # ── Seçili Pencereler Panelı ───────────────────────────────────────
        hdr_f = tk.Frame(pad, bg=SURFACE2, padx=10, pady=6)
        hdr_f.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 4))
        tk.Label(hdr_f, text="🪟  İzlenen Pencereler",
                 font=(FONT[0], 11, "bold"), bg=SURFACE2, fg=INFO).pack(side="left")
        tk.Label(hdr_f,
                 text="(En fazla 3 pencere — her biri bağımsız taranır)",
                 font=(FONT[0], 9), bg=SURFACE2, fg=FG_DIM).pack(side="left", padx=(8, 0))

        # Pencere listesi satırları için container
        self.win_list_frame = tk.Frame(pad, bg=BG)
        self.win_list_frame.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 4))
        self._refresh_win_list()

        # Uygulama ekle / tümünü kaldır butonları
        win_btn_f = tk.Frame(pad, bg=BG)
        win_btn_f.grid(row=2, column=0, columnspan=4, sticky="w", pady=(0, 10))
        make_btn(win_btn_f, text="➕ Uygulama Ekle",
                 bg=GOLD, fg="black", active_bg="#d97706",
                 padx=12, pady=5, command=self._pick_application).pack(side="left")
        make_btn(win_btn_f, text="🔄 Yenile",
                 bg=ACCENT2, fg="black", active_bg="#1e5a9a",
                 padx=12, pady=5, command=self._refresh_win_list).pack(side="left", padx=(8, 0))
        make_btn(win_btn_f, text="🗑 Tümünü Kaldır",
                 bg=DANGER, fg="white", active_bg="#cc3333",
                 padx=12, pady=5, command=self._clear_all_windows).pack(side="left", padx=(8, 0))

        tk.Label(pad, text="📌 Manuel Tarama Bölgesi (pencere seçilmediyse)",
                 font=(FONT[0], 12, "bold"), bg=BG, fg=GOLD).grid(
                     row=3, column=0, columnspan=4, sticky="w", pady=(0, 8))

        fields = [
            ("X (sol)",    self.bot.scan_x),
            ("Y (üst)",    self.bot.scan_y),
            ("Genişlik",   self.bot.scan_w),
            ("Yükseklik",  self.bot.scan_h),
        ]
        for i, (lbl, var) in enumerate(fields):
            row, col = divmod(i, 2)
            r = row + 4
            c = col * 2
            tk.Label(pad, text=lbl, font=FONT_SM, bg=BG, fg=FG_DIM).grid(
                row=r, column=c, sticky="w", padx=(0, 4), pady=4)
            e = tk.Entry(pad, textvariable=var, width=8,
                         bg=SURFACE, fg=FG, insertbackground=FG,
                         relief="flat", font=FONT, justify="center")
            e.grid(row=r, column=c + 1, sticky="w", padx=(0, 16))

        # Tarama aralığı
        tk.Label(pad, text="Tarama Aralığı (ms)", font=FONT_SM, bg=BG, fg=FG_DIM).grid(
            row=6, column=0, sticky="w", pady=(12, 0))
        tk.Scale(
            pad, from_=200, to=5000, resolution=100,
            orient="horizontal", variable=self.bot.scan_ms,
            bg=BG, fg=FG, troughcolor=SURFACE, highlightthickness=0,
            activebackground=ACCENT, sliderrelief="flat", length=200,
        ).grid(row=6, column=1, columnspan=3, sticky="w", pady=(12, 0))

        # Ölüm metinleri
        tk.Label(pad, text="Tespit Edilecek Metinler (virgülle ayır)",
                 font=FONT_SM, bg=BG, fg=FG_DIM).grid(
                     row=7, column=0, columnspan=4, sticky="w", pady=(16, 4))
        self.death_text_entry = tk.Text(
            pad, height=3, width=50,
            bg=SURFACE, fg=FG, insertbackground=FG,
            relief="flat", font=FONT_SM, wrap="word",
        )
        self.death_text_entry.grid(row=8, column=0, columnspan=4, sticky="ew")
        self.death_text_entry.insert("end", ", ".join(DEFAULT_DEATH_TEXTS))

        make_btn(
            pad, text="✓ Metinleri Kaydet",
            bg=ACCENT2, fg="black", active_bg="#1e5a9a",
            padx=10, pady=4, command=self._save_death_texts,
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # Test butonu
        make_btn(
            pad, text="🔬 Bölgeyi Test Et",
            bg=ACCENT, fg="black", active_bg="#c41040",
            padx=10, pady=4, command=self._test_scan,
        ).grid(row=9, column=2, columnspan=2, sticky="w", pady=(6, 0))

        # Cooldown
        tk.Label(pad, text="🛡️ Yeniden Tetiklenme Engeli (saniye)",
                 font=FONT_SM, bg=BG, fg=FG_DIM).grid(
                     row=10, column=0, columnspan=2, sticky="w", pady=(14, 2))
        tk.Scale(
            pad, from_=5, to=120, resolution=5,
            orient="horizontal", variable=self.bot.cooldown_sec,
            bg=BG, fg=FG, troughcolor=SURFACE, highlightthickness=0,
            activebackground=ACCENT, sliderrelief="flat", length=200,
        ).grid(row=10, column=1, columnspan=3, sticky="w", pady=(14, 2))
        tk.Label(pad,
                 text="Bir ölüm işlendikten sonra bu süre geçmeden bot tekrar tetiklenmez.\n"
                      "Yanlış algılama yaşanıyorsa bu değeri artır.",
                 font=(FONT[0], 9), bg=BG, fg=FG_DIM).grid(
                     row=11, column=0, columnspan=4, sticky="w")

    def _save_death_texts(self):
        raw = self.death_text_entry.get("1.0", "end").strip()
        texts = [t.strip().lower() for t in raw.split(",") if t.strip()]
        if texts:
            self.bot.death_texts = texts
            messagebox.showinfo("Kaydedildi", f"{len(texts)} metin kaydedildi.")
        else:
            messagebox.showwarning("Uyarı", "En az bir metin girin.")

    def _test_scan(self):
        """Bölgeyi yakalar, OCR yapar ve sonucu gösterir."""
        def run():
            x, y, w, h = (
                self.bot.scan_x.get(), self.bot.scan_y.get(),
                self.bot.scan_w.get(), self.bot.scan_h.get(),
            )
            raw = capture_region(x, y, w, h)
            if raw is None:
                self._bot_callback("log", "⚠️ Ekran yakalanamadı")
                return
            proc = preprocess_image(raw)
            text = ocr_image(proc)
            self._bot_callback("log", f"🔬 OCR çıktısı: {repr(text[:120])}")
        threading.Thread(target=run, daemon=True).start()

    # ── Hareket Dizisi sekmesi ────────────────────────────────────────────────
    def _build_move_tab(self, parent):
        pad = tk.Frame(parent, bg=BG, padx=16, pady=12)
        pad.pack(fill="both", expand=True)

        tk.Label(pad,
                 text="🚶 Yeniden Doğduktan Sonra Karakterin İzleyeceği Yol",
                 font=(FONT[0], 12, "bold"), bg=BG, fg=GOLD).pack(anchor="w")
        tk.Label(pad,
                 text="Her adım: Konuma Tıkla veya Tuşa Bas. Sıra önemlidir.",
                 font=FONT_SM, bg=BG, fg=FG_DIM).pack(anchor="w", pady=(2, 8))

        # Adım listesi
        self.steps_frame = tk.Frame(pad, bg=BG)
        self.steps_frame.pack(fill="both", expand=True)

        # Başlık satırı
        hdr = tk.Frame(self.steps_frame, bg=SURFACE)
        hdr.pack(fill="x", pady=(0, 4))
        for txt, w in [
            ("Tür", 80), ("X / Tuş", 100), ("Y", 70),
            ("Süre(s)", 70), ("Bekle(s)", 70), ("", 60)
        ]:
            tk.Label(hdr, text=txt, font=(FONT[0], 10, "bold"),
                     bg=SURFACE, fg=FG_DIM, width=w // 8).pack(
                         side="left", padx=4)

        self.rows_container = tk.Frame(pad, bg=BG)
        self.rows_container.pack(fill="both", pady=(0, 8))

        # Butonlar
        btn_f = tk.Frame(pad, bg=BG)
        btn_f.pack(anchor="w")
        make_btn(btn_f, text="➕ Tıklama Ekle",
                 bg=ACCENT2, fg="black", active_bg="#1e5a9a",
                 padx=10, pady=5,
                 command=lambda: self._add_move_row("move")).pack(side="left")
        make_btn(btn_f, text="🖱️ Sürükleme Ekle",
                 bg="#2a5a3a", fg="black", active_bg="#356a4a",
                 padx=10, pady=5,
                 command=lambda: self._add_move_row("drag")).pack(side="left", padx=(8, 0))
        make_btn(btn_f, text="⌨ Tuş Ekle",
                 bg="#2a3a5a", fg="black", active_bg="#354a70",
                 padx=10, pady=5,
                 command=lambda: self._add_move_row("key")).pack(side="left", padx=(8, 0))
        make_btn(btn_f, text="⏳ Bekleme Ekle",
                 bg="#2a3a5a", fg="black", active_bg="#354a70",
                 padx=10, pady=5,
                 command=lambda: self._add_move_row("wait")).pack(side="left", padx=(8, 0))
        make_btn(btn_f, text="✓ Kaydet",
                 bg=SUCCESS, fg="black", active_bg="#16a34a",
                 padx=10, pady=5,
                 command=self._save_move_sequence).pack(side="left", padx=(16, 0))

    def _add_move_row(self, rtype):
        row_data = {
            "type":     tk.StringVar(value=rtype),
            "x":        tk.IntVar(value=0),
            "y":        tk.IntVar(value=0),
            "x2":       tk.IntVar(value=0),   # Sürükleme bitiş X
            "y2":       tk.IntVar(value=0),   # Sürükleme bitiş Y
            "key":      tk.StringVar(value=""),
            "duration": tk.DoubleVar(value=1.5),
            "wait":     tk.DoubleVar(value=0.3),
            "count":    tk.IntVar(value=1),
        }
        self.move_rows.append(row_data)

        f = tk.Frame(self.rows_container, bg=SURFACE, pady=4, padx=6)
        f.pack(fill="x", pady=2)
        row_data["frame"] = f

        type_options = ["move", "drag", "key", "wait"]
        type_menu = tk.OptionMenu(f, row_data["type"], *type_options,
                                  command=lambda v, rd=row_data, fr=f: self._refresh_row(rd, fr))
        type_menu.config(bg=ACCENT2, fg=FG, relief="flat",
                         activebackground=SURFACE, font=FONT_SM, width=6)
        type_menu["menu"].config(bg=SURFACE, fg=FG)
        type_menu.pack(side="left", padx=(0, 6))

        self._render_row_fields(row_data, f)

        make_btn(f, text="✕", bg=DANGER, fg="black", active_bg="#b91c1c",
                 padx=6, pady=2,
                 command=lambda rd=row_data, fr=f: self._remove_row(rd, fr)
                 ).pack(side="right")

    def _render_row_fields(self, rd, frame):
        # Mevcut alanları temizle
        for child in list(frame.winfo_children()):
            if isinstance(child, tk.OptionMenu) or (
                hasattr(child, "pack_info") and child.pack_info().get("side") == "right"
            ):
                continue
            if not isinstance(child, tk.OptionMenu):
                try:
                    child.destroy()
                except Exception:
                    pass

        rtype = rd["type"].get()

        def entry(parent, var, w=7, label=""):
            if label:
                tk.Label(parent, text=label, font=(FONT[0], 9),
                         bg=SURFACE, fg=FG_DIM).pack(side="left")
            e = tk.Entry(parent, textvariable=var, width=w,
                         bg=BG, fg=FG, insertbackground=FG,
                         relief="flat", font=FONT_SM, justify="center")
            e.pack(side="left", padx=2)

        def cap_btn(parent, xv, yv, label="📍"):
            """Küçük yakalama butonu — 3s geri sayım sonra mouse konumunu xv,yv'e yazar."""
            make_btn(parent, text=label, bg="#354a70", fg="black",
                     active_bg="#4a6090", padx=4, pady=1,
                     command=lambda: self._capture_into(xv, yv)).pack(side="left", padx=(0, 6))

        if rtype == "move":
            entry(frame, rd["x"],        6, "X:")
            entry(frame, rd["y"],        6, "Y:")
            entry(frame, rd["duration"], 5, "Süre:")
            entry(frame, rd["wait"],     5, "Bekle:")
        elif rtype == "drag":
            tk.Label(frame, text="Baş:", font=(FONT[0], 9),
                     bg=SURFACE, fg=GOLD).pack(side="left")
            entry(frame, rd["x"], 6, "X:")
            entry(frame, rd["y"], 6, "Y:")
            cap_btn(frame, rd["x"], rd["y"], "📍 Baş")
            tk.Label(frame, text="→", font=(FONT[0], 9),
                     bg=SURFACE, fg=FG_DIM).pack(side="left", padx=2)
            tk.Label(frame, text="Bitiş:", font=(FONT[0], 9),
                     bg=SURFACE, fg=GOLD).pack(side="left")
            entry(frame, rd["x2"], 6, "X:")
            entry(frame, rd["y2"], 6, "Y:")
            cap_btn(frame, rd["x2"], rd["y2"], "📍 Bitiş")
            entry(frame, rd["duration"], 5, "Süre:")
            entry(frame, rd["wait"],     5, "Bekle:")
        elif rtype == "key":
            entry(frame, rd["key"],   8, "Tuş:")
            entry(frame, rd["count"], 4, "Adet:")
            entry(frame, rd["wait"],  5, "Bekle:")
        elif rtype == "wait":
            entry(frame, rd["wait"],  5, "Saniye:")

    def _refresh_row(self, rd, frame):
        # OptionMenu hariç tüm widget'ları yeniden oluştur
        children = list(frame.winfo_children())
        for w in children[1:]:   # 0. eleman OptionMenu
            try:
                if not (hasattr(w, "cget") and w.cget("bg") == DANGER):
                    w.destroy()
            except Exception:
                pass
        self._render_row_fields(rd, frame)

    def _remove_row(self, rd, frame):
        if rd in self.move_rows:
            self.move_rows.remove(rd)
        frame.destroy()

    def _save_move_sequence(self):
        seq = []
        for rd in self.move_rows:
            rtype = rd["type"].get()
            if rtype == "move":
                seq.append({
                    "type":     "move",
                    "x":        rd["x"].get(),
                    "y":        rd["y"].get(),
                    "duration": max(0.1, rd["duration"].get()),
                    "wait":     max(0.0, rd["wait"].get()),
                })
            elif rtype == "drag":
                seq.append({
                    "type":     "drag",
                    "x":        rd["x"].get(),
                    "y":        rd["y"].get(),
                    "x2":       rd["x2"].get(),
                    "y2":       rd["y2"].get(),
                    "duration": max(0.2, rd["duration"].get()),
                    "wait":     max(0.0, rd["wait"].get()),
                })
            elif rtype == "key":
                seq.append({
                    "type":  "key",
                    "key":   rd["key"].get().strip(),
                    "count": max(1, rd["count"].get()),
                    "wait":  max(0.0, rd["wait"].get()),
                    "delay": 0.1,
                })
            elif rtype == "wait":
                seq.append({
                    "type":    "wait",
                    "seconds": max(0.1, rd["wait"].get()),
                })
        self.bot.move_sequence = seq
        messagebox.showinfo("Kaydedildi", f"{len(seq)} adım kaydedildi.")

    # ── Tuşlar & Hedef Koordinat sekmesi ──────────────────────────────────────
    def _build_key_tab(self, parent):
        # Scrollable wrapper so tall content is always reachable
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        pad = tk.Frame(canvas, bg=BG, padx=16, pady=16)
        win_id = canvas.create_window((0, 0), window=pad, anchor="nw")

        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_configure(e):
            canvas.itemconfig(win_id, width=e.width)
        pad.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # ─── 1. Bölüm: Respawn Tuşu ───────────────────────────────────────────
        tk.Label(pad, text="🎮 Yeniden Başlatma Tuşu",
                 font=(FONT[0], 12, "bold"), bg=BG, fg=GOLD).grid(
                     row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        tk.Label(pad,
                 text="Ölüm ekranı algılandığında basılacak tuş (oyunda 'Yeniden Başla'ya atadığın tuş):",
                 font=FONT_SM, bg=BG, fg=FG_DIM).grid(
                     row=1, column=0, columnspan=3, sticky="w", pady=(0, 6))

        tk.Entry(pad, textvariable=self.bot.respawn_key, width=10,
                 bg=SURFACE, fg=FG, insertbackground=FG,
                 relief="flat", font=(FONT[0], 18, "bold"), justify="center",
                 ).grid(row=2, column=0, sticky="w", pady=4)

        make_btn(
            pad, text="⌨ Dinleyerek Seç",
            bg=ACCENT2, fg="black", active_bg="#1e5a9a",
            padx=10, pady=6, command=self._pick_respawn_key,
        ).grid(row=2, column=1, sticky="w", padx=(10, 0))

        tk.Label(pad, text="Yükleme Bekleme Süresi (saniye)",
                 font=FONT_SM, bg=BG, fg=FG_DIM).grid(
                     row=3, column=0, columnspan=2, sticky="w", pady=(10, 2))
        tk.Scale(
            pad, from_=0.5, to=30.0, resolution=0.5,
            orient="horizontal", variable=self.bot.respawn_delay,
            bg=BG, fg=FG, troughcolor=SURFACE, highlightthickness=0,
            activebackground=ACCENT, sliderrelief="flat", length=220, digits=2,
        ).grid(row=4, column=0, columnspan=2, sticky="w")
        tk.Label(pad, text="Respawn tuşundan sonra hedefe hareket başlamadan önce beklenir.",
                 font=(FONT[0], 9), bg=BG, fg=FG_DIM).grid(
                     row=5, column=0, columnspan=3, sticky="w", pady=(2, 12))

        tk.Label(pad, text="─" * 50, bg=BG, fg=BORDER).grid(
            row=6, column=0, columnspan=3, sticky="ew", pady=(12, 0))

        # ─── 2. Bölüm: Oto-Av Tuşu ───────────────────────────────────────────
        tk.Label(pad, text="⚔️ Oto-Av Tuşu",
                 font=(FONT[0], 12, "bold"), bg=BG, fg=GOLD).grid(
                     row=13, column=0, columnspan=3, sticky="w", pady=(12, 4))
        tk.Label(pad,
                 text="Hedefe gidildikten sonra basılacak tuş:",
                 font=FONT_SM, bg=BG, fg=FG_DIM).grid(
                     row=14, column=0, columnspan=3, sticky="w", pady=(0, 6))

        tk.Entry(pad, textvariable=self.bot.auto_hunt_key, width=10,
                 bg=SURFACE, fg=FG, insertbackground=FG,
                 relief="flat", font=(FONT[0], 18, "bold"), justify="center",
                 ).grid(row=15, column=0, sticky="w", pady=4)

        make_btn(
            pad, text="⌨ Dinleyerek Seç",
            bg=ACCENT2, fg="black", active_bg="#1e5a9a",
            padx=10, pady=6, command=self._pick_hunt_key,
        ).grid(row=15, column=1, sticky="w", padx=(10, 0))

        tk.Label(pad, text="─" * 50, bg=BG, fg=BORDER).grid(
            row=16, column=0, columnspan=3, sticky="ew", pady=(12, 0))

        # Akış özeti
        tk.Label(pad,
                 text="📌 Sıra:  1️⃣ Ölüm tespit  →  2️⃣ Respawn tuşu  →  "
                      "3️⃣ Bekleme  →  4️⃣ Hareket makrosu  →  5️⃣ Oto-av tuşu",
                 font=FONT_SM, bg=BG, fg=INFO, justify="left").grid(
                     row=17, column=0, columnspan=3, sticky="w", pady=10)

        tk.Label(pad, text="─" * 50, bg=BG, fg=BORDER).grid(
            row=18, column=0, columnspan=3, sticky="ew")

        # ─── 4. Bölüm: Hareket Makrosu ────────────────────────────────────────
        tk.Label(pad, text="🕹️ Hareket Makrosu (Respawn → Av Noktası)",
                 font=(FONT[0], 12, "bold"), bg=BG, fg=GOLD).grid(
                     row=19, column=0, columnspan=3, sticky="w", pady=(12, 4))
        tk.Label(pad,
                 text="Respawn bekleme bittikten sonra oynatılacak makro.\n"
                      "Kaydet butonuna bas → oyunda WASD ile hareket et → Durdur & Kaydet.",
                 font=FONT_SM, bg=BG, fg=FG_DIM).grid(
                     row=20, column=0, columnspan=3, sticky="w", pady=(0, 8))

        # Durum + olay sayacı
        self.move_rec_status_var = tk.StringVar(value="⏸️  Kayıt Yok")
        self.move_rec_count_var  = tk.StringVar(value="")
        mv_sf = tk.Frame(pad, bg=BG)
        mv_sf.grid(row=21, column=0, columnspan=3, sticky="w", pady=(0, 4))
        tk.Label(mv_sf, textvariable=self.move_rec_status_var,
                 font=(FONT[0], 11, "bold"), bg=BG, fg=GOLD).pack(side="left")
        tk.Label(mv_sf, textvariable=self.move_rec_count_var,
                 font=FONT_SM, bg=BG, fg=FG_DIM).pack(side="left", padx=(10, 0))

        # Kayıt butonları
        mv_bf = tk.Frame(pad, bg=BG)
        mv_bf.grid(row=22, column=0, columnspan=3, sticky="w", pady=4)
        self.move_rec_btn = make_btn(mv_bf, text="🔴  Kaydet",
                                     bg=ACCENT, fg="black", active_bg="#c41040",
                                     padx=14, pady=6, command=self._start_move_rec)
        self.move_rec_btn.pack(side="left")
        self.move_stop_btn = make_btn(mv_bf, text="⏹  Durdur & Kaydet",
                                      bg="#2a3a5a", fg="black", active_bg="#354a70",
                                      padx=14, pady=6, command=self._stop_move_rec,
                                      state="disabled")
        self.move_stop_btn.pack(side="left", padx=(8, 0))
        make_btn(mv_bf, text="▶  Test Et",
                 bg="#1a4a30", fg="black", active_bg="#255a3a",
                 padx=14, pady=6, command=self._test_move_macro).pack(side="left", padx=(8, 0))
        make_btn(mv_bf, text="🗑 Sil",
                 bg=DANGER, fg="white", active_bg="#cc3333",
                 padx=10, pady=6, command=self._clear_move_macro).pack(side="left", padx=(8, 0))

        # Oynatma hızı
        mv_spd_f = tk.Frame(pad, bg=BG)
        mv_spd_f.grid(row=23, column=0, columnspan=3, sticky="w", pady=(6, 0))
        tk.Label(mv_spd_f, text="Oynatma Hızı:", font=FONT_SM, bg=BG, fg=FG_DIM).pack(side="left")
        tk.Scale(mv_spd_f, from_=0.25, to=3.0, resolution=0.25, orient="horizontal",
                 variable=self.bot.move_macro_speed,
                 bg=BG, fg=FG, troughcolor=SURFACE, highlightthickness=0,
                 activebackground=ACCENT, sliderrelief="flat", length=150, digits=3,
                 ).pack(side="left", padx=6)
        tk.Label(mv_spd_f, textvariable=self.bot.move_macro_speed,
                 font=(FONT[0], 10, "bold"), bg=BG, fg=ACCENT).pack(side="left")
        tk.Label(mv_spd_f, text="×", font=FONT_SM, bg=BG, fg=FG_DIM).pack(side="left", padx=2)



    # ── Hareket Makrosu metodları ──────────────────────────────────────────────
    def _start_move_rec(self):
        self.move_rec_btn.config(state="disabled")
        self.move_stop_btn.config(state="disabled")
        self._bot_callback("log", "⏳ Kayıt 3 saniye sonra başlıyor — Cmd+Tab ile oyuna geç!")
        self._move_rec_countdown(3)

    def _move_rec_countdown(self, remaining: int):
        if remaining > 0:
            self.move_rec_status_var.set(f"⏳  Kayıt başlıyor… {remaining}")
            self.after(1000, lambda: self._move_rec_countdown(remaining - 1))
        else:
            try:
                self.bot.move_macro_recorder.events.clear()
                self.bot.move_macro_recorder.start_recording()
                self.move_stop_btn.config(state="normal")
                self.move_rec_status_var.set("🔴  Kayıt Devam Ediyor…")
                self._bot_callback("log", "🔴 Kayıt başladı — oyunda hareket et!")
                self._update_move_rec_count()
            except Exception as e:
                self.move_rec_btn.config(state="normal")
                messagebox.showerror("Kayıt Hatası", str(e))

    def _update_move_rec_count(self):
        if self.bot.move_macro_recorder.recording:
            n = len(self.bot.move_macro_recorder.events)
            self.move_rec_count_var.set(f"{n} olay kaydedildi")
            self.after(500, self._update_move_rec_count)

    def _stop_move_rec(self):
        self.bot.move_macro_recorder.stop_recording()
        self.move_rec_btn.config(state="normal")
        self.move_stop_btn.config(state="disabled")
        n = len(self.bot.move_macro_recorder.events)
        self.move_rec_status_var.set(f"✅  {n} olay kaydedildi")
        self.move_rec_count_var.set("")
        path = self.bot.move_macro_path.get()
        try:
            self.bot.move_macro_recorder.save(path)
            self._bot_callback("log", f"💾 Hareket makrosu kaydedildi: {path}  ({n} olay)")
        except Exception as e:
            messagebox.showerror("Kayıt Hatası", str(e))

    def _test_move_macro(self):
        path = self.bot.move_macro_path.get()
        if not self.bot.move_macro_recorder.events:
            if os.path.exists(path):
                self.bot.move_macro_recorder.load(path)
            else:
                messagebox.showwarning("Makro Yok", "Henüz hareket makrosu kaydedilmedi.")
                return
        def run():
            n = len(self.bot.move_macro_recorder.events)
            self._bot_callback("log", f"▶ Hareket makrosu test oynatılıyor ({n} olay)…")
            self.bot.move_macro_recorder.play(
                speed=self.bot.move_macro_speed.get(),
                log_cb=lambda m: self._bot_callback("log", m),
                stop_check=lambda: False,
            )
            self._bot_callback("log", "✅ Hareket makrosu testi tamamlandı.")
        threading.Thread(target=run, daemon=True).start()

    def _clear_move_macro(self):
        self.bot.move_macro_recorder.events.clear()
        path = self.bot.move_macro_path.get()
        if os.path.exists(path):
            os.remove(path)
        self.move_rec_status_var.set("⏸️  Kayıt Yok")
        self.move_rec_count_var.set("")
        self._bot_callback("log", "🗑️ Hareket makrosu silindi.")

    def _pick_hunt_key(self):
        popup = tk.Toplevel(self, bg=BG)
        popup.title("Tuş Seç")
        popup.geometry("300x160")
        popup.resizable(False, False)
        popup.grab_set()
        popup.focus_force()

        tk.Label(popup, text="Oto-av tuşuna basın…",
                 font=(FONT[0], 14), bg=BG, fg=FG).pack(pady=30)
        lbl = tk.Label(popup, text="—", font=(FONT[0], 22, "bold"),
                       bg=BG, fg=ACCENT)
        lbl.pack()

        def on_key(event):
            k = event.keysym
            if k in ("Shift_L", "Shift_R", "Control_L", "Control_R",
                     "Alt_L", "Alt_R", "Meta_L", "Meta_R"):
                return
            # pyautogui formatına çevir
            pag_key = k.lower() if len(k) == 1 else k
            self.bot.auto_hunt_key.set(pag_key)
            popup.destroy()

        popup.bind("<KeyPress>", on_key)

    def _pick_respawn_key(self):
        popup = tk.Toplevel(self, bg=BG)
        popup.title("Respawn Tuşu Seç")
        popup.geometry("320x170")
        popup.resizable(False, False)
        popup.grab_set()
        popup.focus_force()

        tk.Label(popup, text="🎮 Yeniden başlatma tuşuna basın…",
                 font=(FONT[0], 13), bg=BG, fg=FG).pack(pady=24)
        lbl = tk.Label(popup, text="—", font=(FONT[0], 22, "bold"),
                       bg=BG, fg=GOLD)
        lbl.pack()

        def on_key(event):
            k = event.keysym
            if k in ("Shift_L", "Shift_R", "Control_L", "Control_R",
                     "Alt_L", "Alt_R", "Meta_L", "Meta_R"):
                return
            pag_key = k.lower() if len(k) == 1 else k
            self.bot.respawn_key.set(pag_key)
            popup.destroy()

        popup.bind("<KeyPress>", on_key)



    def _capture_into(self, x_var, y_var):
        """3 sn geri sayım sonra mouse konumunu x_var ve y_var'a yazar."""
        def countdown():
            for i in (3, 2, 1):
                self._bot_callback("log", f"⏱️ {i}… (mouse'u konuma götür)")
                time.sleep(1)
            x, y = pyautogui.position()
            x_var.set(x)
            y_var.set(y)
            self._bot_callback("log", f"📍 Yakalandı: X={x}, Y={y}")
        threading.Thread(target=countdown, daemon=True).start()

    # ── Log sekmesi ──────────────────────────────────────────────────────────
    def _build_log_tab(self, parent):
        pad = tk.Frame(parent, bg=BG, padx=8, pady=8)
        pad.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            pad, bg="#0a0a14", fg="#a8ff78", insertbackground=FG,
            relief="flat", font=("Menlo", 11), wrap="word",
            state="disabled", height=18,
        )
        sb = tk.Scrollbar(pad, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)

        make_btn(
            pad, text="🗑 Temizle",
            bg="#2a3a5a", fg="black", active_bg="#354a70",
            padx=10, pady=4, command=self._clear_log,
        ).pack(anchor="e", pady=(4, 0))

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    # ── Kontrol butonları ─────────────────────────────────────────────────────
    def _toggle(self):
        if self.bot.running:
            self.bot.stop()
            self.start_btn.config(text="▶  BAŞLAT", bg=SUCCESS,
                                  activebackground="#16a34a")
            self.status_var.set("⏸️ Durduruldu")
        else:
            self.bot.start()
            self.start_btn.config(text="■  DURDUR", bg=DANGER,
                                  activebackground="#b91c1c")
            self.status_var.set("🔍 Taranıyor…")

    def _pick_region(self):
        """Kullanıcı sürükleyerek tarama bölgesini seçsin."""
        self.withdraw()
        time.sleep(0.4)

        overlay = tk.Toplevel()
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.25)
        overlay.configure(bg="black")
        overlay.attributes("-topmost", True)
        overlay.lift()
        overlay.focus_force()

        canvas = tk.Canvas(overlay, cursor="crosshair", bg="black",
                            highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        rect_id  = [None]
        start_xy = [None]

        def on_press(e):
            start_xy[0] = (e.x, e.y)
            rect_id[0]  = canvas.create_rectangle(
                e.x, e.y, e.x, e.y, outline=ACCENT, width=2, fill=""
            )

        def on_drag(e):
            if rect_id[0] and start_xy[0]:
                x0, y0 = start_xy[0]
                canvas.coords(rect_id[0], x0, y0, e.x, e.y)

        def on_release(e):
            if start_xy[0]:
                x0, y0 = start_xy[0]
                x1, y1 = e.x, e.y
                rx, ry = min(x0, x1), min(y0, y1)
                rw, rh = abs(x1 - x0), abs(y1 - y0)
                self.bot.scan_x.set(rx)
                self.bot.scan_y.set(ry)
                self.bot.scan_w.set(max(rw, 50))
                self.bot.scan_h.set(max(rh, 50))
            overlay.destroy()
            self.deiconify()

        canvas.bind("<ButtonPress-1>",   on_press)
        canvas.bind("<B1-Motion>",       on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        overlay.bind("<Escape>", lambda e: (overlay.destroy(), self.deiconify()))

    def _get_mouse_pos(self):
        """3 saniyelik geri sayım sonrası mouse koordinatını loglar."""
        def countdown():
            for i in (3, 2, 1):
                self._bot_callback("log", f"⏱️ {i}… (mouse'u konuma götür)")
                time.sleep(1)
            x, y = pyautogui.position()
            msg = f"📍 Mouse konumu: X={x}, Y={y}"
            win = self.bot.selected_windows[0] if self.bot.selected_windows else None
            if win:
                rel_x = x - win["x"]
                rel_y = y - win["y"]
                msg += f"  |  Pencere içi: relX={rel_x}, relY={rel_y}"
            self._bot_callback("log", msg)
        threading.Thread(target=countdown, daemon=True).start()

    # ── Uygulama / Pencere seçici ─────────────────────────────────────────────
    def _pick_application(self):
        """Çalışan tüm pencereleri listeler; seçileni scan bölgesi olarak atar."""
        windows = get_windows()
        if not windows:
            messagebox.showwarning(
                "Pencere Bulunamadı",
                "Görünür pencere listelenemedi.\n"
                "Quartz erişimi yoksa manuel koordinat girin."
            )
            return

        popup = tk.Toplevel(self, bg=BG)
        popup.title("Uygulama / Pencere Seç")
        popup.geometry("620x480")
        popup.resizable(True, True)
        popup.grab_set()
        popup.focus_force()

        tk.Label(popup, text="🪟  Pencere Seç",
                 font=FONT_LG, bg=BG, fg=GOLD).pack(pady=(16, 4))
        tk.Label(popup,
                 text="Seçilen pencerenin sınırları tarama bölgesi olarak atanır.",
                 font=FONT_SM, bg=BG, fg=FG_DIM).pack(pady=(0, 8))

        # Arama kutusu
        search_var = tk.StringVar()
        search_entry = tk.Entry(popup, textvariable=search_var,
                                bg=SURFACE, fg=FG, insertbackground=FG,
                                relief="flat", font=FONT, justify="left")
        search_entry.pack(fill="x", padx=16, pady=(0, 6))
        search_entry.insert(0, "Ara…")
        search_entry.bind("<FocusIn>",  lambda e: search_entry.delete(0, "end")
                          if search_entry.get() == "Ara…" else None)

        # Liste
        list_frame = tk.Frame(popup, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=16)

        sb = tk.Scrollbar(list_frame)
        sb.pack(side="right", fill="y")

        lb = tk.Listbox(
            list_frame,
            bg=SURFACE, fg=FG, selectbackground=ACCENT2, selectforeground=FG,
            relief="flat", font=FONT_SM, activestyle="none",
            yscrollcommand=sb.set,
        )
        lb.pack(fill="both", expand=True)
        sb.config(command=lb.yview)

        # Pencere önizleme etiketi
        preview_var = tk.StringVar(value="")
        tk.Label(popup, textvariable=preview_var,
                 font=(FONT[0], 10), bg=BG, fg=INFO).pack(pady=4)

        # Listeyi filtrele / doldur
        visible = []

        def populate(filter_text=""):
            lb.delete(0, "end")
            visible.clear()
            ft = filter_text.lower()
            for w in windows:
                label = f"{w['app']}" + (f"  —  {w['title']}" if w['title'] else "")
                if ft and ft not in label.lower():
                    continue
                lb.insert("end", f"  {label}")
                visible.append(w)

        populate()
        search_var.trace_add("write", lambda *_: populate(search_var.get()
                              if search_var.get() != "Ara…" else ""))

        def on_select(event=None):
            sel = lb.curselection()
            if not sel:
                return
            w = visible[sel[0]]
            preview_var.set(
                f"X={w['x']}  Y={w['y']}  Genişlik={w['w']}  Yükseklik={w['h']}"
            )

        def on_confirm(event=None):
            sel = lb.curselection()
            if not sel:
                messagebox.showwarning("Seçim Yok", "Lütfen bir pencere seçin.",
                                       parent=popup)
                return
            w = visible[sel[0]]
            # Zaten listede var mı?
            for existing in self.bot.selected_windows:
                if existing["x"] == w["x"] and existing["y"] == w["y"]:
                    messagebox.showinfo("Zaten Eklendi",
                                        f"{w['app']} zaten listede.", parent=popup)
                    return
            if len(self.bot.selected_windows) >= 3:
                messagebox.showwarning("Limit", "En fazla 3 pencere eklenebilir.",
                                       parent=popup)
                return
            # Ekle
            w["last_death_at"] = 0.0
            self.bot.selected_windows.append(w)
            label = f"{w['app']}" + (f" — {w['title']}" if w['title'] else "")
            self._bot_callback("log",
                f"🪟 Eklendi: {label}  ({w['x']},{w['y']}) {w['w']}×{w['h']}")
            self._refresh_win_list()
            popup.destroy()

        lb.bind("<<ListboxSelect>>", on_select)
        lb.bind("<Double-Button-1>",  on_confirm)

        # Butonlar
        btn_f = tk.Frame(popup, bg=BG)
        btn_f.pack(pady=(4, 12))
        make_btn(btn_f, text="➕ Ekle",
                 bg=SUCCESS, fg="black", active_bg="#16a34a",
                 padx=20, pady=6, command=on_confirm).pack(side="left", padx=8)
        make_btn(btn_f, text="✕ İptal",
                 bg="#2a3a5a", fg="black", active_bg="#354a70",
                 padx=20, pady=6, command=popup.destroy).pack(side="left", padx=8)
        make_btn(btn_f, text="🔄 Yenile",
                 bg=ACCENT2, fg="black", active_bg="#1e5a9a",
                 padx=16, pady=6,
                 command=lambda: [
                     windows.clear(),
                     windows.__iadd__(get_windows()),
                     populate(search_var.get() if search_var.get() != "Ara…" else "")
                 ]).pack(side="left", padx=8)


# ── Giriş noktası ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
