"""
MacroRecorder — Mouse (hold dahil) & Klavye Kaydedici
======================================================
macOS : CoreGraphics HID (izin gerektirmez, thread-safe)
Windows: pynput listener (Input Monitoring gerektirmez)

Olay tipleri (JSON):
  mousedown  → {type, x, y, button, t}   hold başlangıcı
  mouseup    → {type, x, y, button, t}   hold bitişi
  keydown    → {type, key, t}            tuş basıldı
  keyup      → {type, key, t}            tuş bırakıldı   (opsiyonel)

Oynatma:
  mousedown  → pyautogui.mouseDown()
  mouseup    → pyautogui.mouseUp()
  keydown    → pyautogui.keyDown()
  keyup      → pyautogui.keyUp()
  click      → pyautogui.click()  (eski format uyumu)
"""

import sys
import time
import json
import ctypes
import threading

IS_WINDOWS = sys.platform == "win32"
IS_MAC     = sys.platform == "darwin"

# ── pyautogui ─────────────────────────────────────────────────────────────────
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE    = 0.0
except ImportError:
    pyautogui = None

# ── PIL ───────────────────────────────────────────────────────────────────────
try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

# ── CoreGraphics — ctypes (izin gerektirmez, thread-safe) ─────────────────────
_CG_OK = False
try:
    _cg = ctypes.CDLL(
        '/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    _cf = ctypes.CDLL(
        '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')

    # CGPoint
    class _CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    # CGEventCreate(source) → CGEventRef
    _cg.CGEventCreate.restype  = ctypes.c_void_p
    _cg.CGEventCreate.argtypes = [ctypes.c_void_p]

    # CGEventGetLocation(event) → CGPoint
    _cg.CGEventGetLocation.restype  = _CGPoint
    _cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]

    # CFRelease(ref)
    _cf.CFRelease.restype  = None
    _cf.CFRelease.argtypes = [ctypes.c_void_p]

    # CGEventSourceButtonState(stateID, button) → bool
    _cg.CGEventSourceButtonState.restype  = ctypes.c_bool
    _cg.CGEventSourceButtonState.argtypes = [ctypes.c_int32, ctypes.c_uint32]

    # CGEventSourceKeyState(stateID, keycode) → bool
    _cg.CGEventSourceKeyState.restype  = ctypes.c_bool
    _cg.CGEventSourceKeyState.argtypes = [ctypes.c_int32, ctypes.c_uint16]

    _HID = ctypes.c_int32(1)   # kCGEventSourceStateHIDSystemState
    _CG_OK = True

except Exception as _e:
    pass   # Fallback: kayıt devre dışı


# ── macOS keycode → pyautogui key adı ────────────────────────────────────────
# Sadece oyunda kullanılabilecek tuşlar dahil edildi.
# pyautogui 'press()' için geçerli adlar kullanılır.
_KEYCODE_MAP: dict[int, str] = {
    # Harfler (a-z)
    0:'a', 1:'s', 2:'d', 3:'f', 4:'h', 5:'g', 6:'z', 7:'x',
    8:'c', 9:'v', 11:'b', 12:'q', 13:'w', 14:'e', 15:'r',
    16:'y', 17:'t', 31:'o', 32:'u', 34:'i', 35:'p',
    37:'l', 38:'j', 40:'k', 45:'n', 46:'m',
    # Rakamlar
    18:'1', 19:'2', 20:'3', 21:'4', 22:'6', 23:'5',
    25:'9', 26:'7', 28:'8', 29:'0',
    # Noktalama / Semboller
    24:'=', 27:'-', 30:']', 33:'[', 39:"'", 41:';',
    42:'\\', 43:',', 44:'/', 47:'.', 50:'`',
    # Özel tuşlar
    36:'enter', 48:'tab', 49:'space', 51:'backspace', 53:'escape',
    # Fonksiyon tuşları
    122:'f1', 120:'f2', 99:'f3', 118:'f4',
    96:'f5',  97:'f6', 98:'f7', 100:'f8',
    101:'f9', 109:'f10', 103:'f11', 111:'f12',
    # Yön tuşları
    123:'left', 124:'right', 125:'down', 126:'up',
    # Navigasyon
    115:'home', 119:'end', 116:'pageup', 121:'pagedown',
    117:'delete',
    # Modifier tuşları (kaydedilir fakat oynatmada atlanır)
    56:'shift', 60:'shift',
    59:'ctrl',  62:'ctrl',
    58:'alt',   61:'alt',
    55:'command', 54:'command',
}

# Oynatmada basılmayacak tuşlar (modifier tek başına anlamsız)
_NO_PLAY = frozenset({'shift', 'ctrl', 'alt', 'command'})

# ── pynput — Windows / cross-platform fallback ────────────────────────────
try:
    from pynput import mouse as _pynput_mouse, keyboard as _pynput_kb
    PYNPUT_OK = True
except ImportError:
    _pynput_mouse = _pynput_kb = None
    PYNPUT_OK = False

# pynput key → pyautogui key name
def _pynput_key_name(key) -> str:
    """pynput Key/KeyCode nesnesini pyautogui tuş ismine çevirir."""
    try:
        # Normal karakter tuşu
        if hasattr(key, 'char') and key.char:
            return key.char.lower()
    except Exception:
        pass
    try:
        # Özel tuş (Key.space, Key.enter, ...)
        name = key.name
        _MAP = {
            'space': 'space', 'enter': 'enter', 'tab': 'tab',
            'backspace': 'backspace', 'delete': 'delete', 'escape': 'escape',
            'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right',
            'home': 'home', 'end': 'end', 'page_up': 'pageup',
            'page_down': 'pagedown',
            'f1':'f1','f2':'f2','f3':'f3','f4':'f4','f5':'f5','f6':'f6',
            'f7':'f7','f8':'f8','f9':'f9','f10':'f10','f11':'f11','f12':'f12',
            'shift': 'shift', 'shift_l': 'shift', 'shift_r': 'shift',
            'ctrl': 'ctrl', 'ctrl_l': 'ctrl', 'ctrl_r': 'ctrl',
            'alt': 'alt', 'alt_l': 'alt', 'alt_r': 'alt',
            'cmd': 'command', 'cmd_l': 'command', 'cmd_r': 'command',
        }
        return _MAP.get(name, name)
    except Exception:
        return ''


class MacroRecorder:
    """
    Mouse (hold dahil) ve klavye tuşlarını kaydeder ve oynatır.
    macOS : CoreGraphics HID (izin gerektirmez)
    Windows: pynput listener (cross-platform)
    """

    def __init__(self):
        self.events: list[dict] = []
        self.recording    = False
        self._start_time  = 0.0
        self._poll_thread = None
        self._pynput_listeners = []   # Windows pynput listeners

    # ── Kayıt başlat / durdur ─────────────────────────────────────────────────
    def start_recording(self):
        self.events      = []
        self.recording   = True
        self._start_time = time.time()

        if _CG_OK:
            # macOS: CoreGraphics HID polling
            self._poll_thread = threading.Thread(
                target=self._poll_all, daemon=True)
            self._poll_thread.start()
        elif PYNPUT_OK:
            # Windows / fallback: pynput listeners
            self._start_pynput_recording()
        else:
            self.recording = False
            raise RuntimeError(
                "Kayıt başlatılamadı — CoreGraphics (macOS) veya pynput (Windows) gerekli.\n"
                "Windows için: pip install pynput")

    def stop_recording(self):
        self.recording = False
        # pynput listenerları durdur
        for listener in self._pynput_listeners:
            try:
                listener.stop()
            except Exception:
                pass
        self._pynput_listeners.clear()
        # Olayları kronolojik sıraya koy
        self.events.sort(key=lambda e: e["t"])

    # ── pynput backend (Windows) ──────────────────────────────────────────────
    def _start_pynput_recording(self):
        """pynput mouse + keyboard listenerları başlatır (Windows/Linux)."""
        start = self._start_time

        def on_click(x, y, button, pressed):
            if not self.recording:
                return False   # listener'ı durdur
            btn_name = "right" if "right" in str(button).lower() else "left"
            ev_type  = "mousedown" if pressed else "mouseup"
            self.events.append({
                "type": ev_type, "x": x, "y": y,
                "button": btn_name,
                "t": round(time.time() - start, 3),
            })

        def on_press(key):
            if not self.recording:
                return False
            name = _pynput_key_name(key)
            if name:
                self.events.append({
                    "type": "keydown", "key": name,
                    "t": round(time.time() - start, 3),
                })

        def on_release(key):
            if not self.recording:
                return False
            name = _pynput_key_name(key)
            if name:
                self.events.append({
                    "type": "keyup", "key": name,
                    "t": round(time.time() - start, 3),
                })

        ml = _pynput_mouse.Listener(on_click=on_click)
        kl = _pynput_kb.Listener(on_press=on_press, on_release=on_release)
        ml.start()
        kl.start()
        self._pynput_listeners = [ml, kl]

    # ── Yardımcı: mouse pozisyonu ─────────────────────────────────────────────
    def _get_mouse_pos(self) -> tuple[int, int]:
        """Thread-safe mouse position (CoreGraphics on macOS, pyautogui elsewhere)."""
        if _CG_OK:
            try:
                ev_ref = _cg.CGEventCreate(None)
                pos    = _cg.CGEventGetLocation(ev_ref)
                _cf.CFRelease(ev_ref)
                return int(pos.x), int(pos.y)
            except Exception:
                pass
        if pyautogui:
            try:
                p = pyautogui.position()
                return int(p.x), int(p.y)
            except Exception:
                pass
        return 0, 0

    # ── Ana polling döngüsü ───────────────────────────────────────────────────
    def _poll_all(self):
        """
        ~120 FPS'de hem mouse butonlarını hem tüm klavye tuşlarını sorgular.
        Her state değişikliğinde (rising/falling edge) bir olay kaydeder.
        """
        prev_left  = False
        prev_right = False
        prev_keys  = {kc: False for kc in _KEYCODE_MAP}
        hid        = _HID

        INTERVAL = 0.008   # 8 ms ≈ 120 fps

        while self.recording:
            try:
                t = round(time.time() - self._start_time, 3)

                # ── Mouse butonları (left=0, right=1) ──────────────────────
                left_now  = bool(_cg.CGEventSourceButtonState(hid, 0))
                right_now = bool(_cg.CGEventSourceButtonState(hid, 1))

                if left_now != prev_left:
                    x, y    = self._get_mouse_pos()
                    ev_type = "mousedown" if left_now else "mouseup"
                    self.events.append({
                        "type": ev_type, "x": x, "y": y,
                        "button": "left", "t": t,
                    })

                if right_now != prev_right:
                    x, y    = self._get_mouse_pos()
                    ev_type = "mousedown" if right_now else "mouseup"
                    self.events.append({
                        "type": ev_type, "x": x, "y": y,
                        "button": "right", "t": t,
                    })

                prev_left  = left_now
                prev_right = right_now

                # ── Klavye: her kayıtlı keycode kontrol ────────────────────
                for kc, key_name in _KEYCODE_MAP.items():
                    now = bool(_cg.CGEventSourceKeyState(hid, kc))
                    was = prev_keys[kc]

                    if now and not was:
                        # Tuş yeni basıldı (rising edge)
                        self.events.append({
                            "type": "keydown",
                            "key":  key_name,
                            "t":    t,
                        })
                    elif not now and was:
                        # Tuş bırakıldı (falling edge) — hold için önemli
                        self.events.append({
                            "type": "keyup",
                            "key":  key_name,
                            "t":    t,
                        })

                    prev_keys[kc] = now

            except Exception:
                pass

            time.sleep(INTERVAL)

    # ── Kaydet / Yükle ────────────────────────────────────────────────────────
    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.events, f, ensure_ascii=False, indent=2)

    def load(self, path: str):
        with open(path, encoding="utf-8") as f:
            self.events = json.load(f)

    # ── Oynat ─────────────────────────────────────────────────────────────────
    def play(self, speed: float = 1.0, log_cb=None, stop_check=None):
        """
        Kayıtlı olayları zamanlama ile oynatır.

        mousedown/mouseup çifti → hold doğru süreyle tekrarlanır
        keydown/keyup çifti    → tuş basılı tutma doğru süreyle tekrarlanır
        keydown (tek başına)   → pyautogui.press() — kısa tık
        """
        if not self.events or pyautogui is None:
            return

        prev_t = 0.0
        for ev in self.events:
            if stop_check and stop_check():
                return

            # Olaylar arası gecikme (hız faktörüne göre ölçeklenir)
            delay = (ev["t"] - prev_t) / max(speed, 0.1)
            if delay > 0.004:
                time.sleep(delay)
            prev_t = ev["t"]

            etype    = ev.get("type", "")
            x        = ev.get("x", 0)
            y        = ev.get("y", 0)
            btn      = ev.get("button", "left")
            key_name = ev.get("key", "")

            try:
                # ── Mouse hold ──────────────────────────────────────────────
                if etype == "mousedown":
                    pyautogui.mouseDown(x=x, y=y, button=btn, _pause=False)
                    if log_cb:
                        log_cb(f"🖱️ Basılı ({x},{y}) [{btn}]")

                elif etype == "mouseup":
                    pyautogui.mouseUp(x=x, y=y, button=btn, _pause=False)
                    if log_cb:
                        log_cb(f"🖱️ Bırakıldı ({x},{y}) [{btn}]")

                # ── Mouse tıklama (eski format) ─────────────────────────────
                elif etype == "click":
                    pyautogui.click(x=x, y=y, _pause=False)
                    if log_cb:
                        log_cb(f"🖱️ Tıklama ({x},{y})")

                # ── Klavye ──────────────────────────────────────────────────
                elif etype == "keydown":
                    if key_name and key_name not in _NO_PLAY:
                        pyautogui.keyDown(key_name, _pause=False)
                    if log_cb:
                        log_cb(f"⌨️ Basıldı: {key_name}")

                elif etype == "keyup":
                    if key_name and key_name not in _NO_PLAY:
                        pyautogui.keyUp(key_name, _pause=False)
                    if log_cb:
                        log_cb(f"⌨️ Bırakıldı: {key_name}")

                # ── Eski "key" formatı ──────────────────────────────────────
                elif etype == "key":
                    if key_name and key_name not in _NO_PLAY:
                        pyautogui.press(key_name, _pause=False)
                    if log_cb:
                        log_cb(f"⌨️ Tuş: {key_name}")

            except Exception as ex:
                if log_cb:
                    log_cb(f"⚠️ [{etype}] oynatma hatası: {ex}")

