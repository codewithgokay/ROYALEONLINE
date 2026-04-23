# ⚔️ Royale Online — Ölüm Dedektörü & Oto-Av Botu

## Programı Başlatmak
```bash
python3.11 royale_bot.py
```

## Kurulum Adımları (bir kez yapılır)

```bash
pip install pillow pytesseract pyautogui pynput
brew install tesseract tesseract-lang
```

## Nasıl Kullanılır?

### 1. Tarama Bölgesi Sekmesi
- **"🖱️ Bölge Seç"** butonuna basın ve oyunda "şehirde yeniden başla" yazısının göründüğü köşeyi sürükleyerek seçin.
- **"🔬 Bölgeyi Test Et"** ile OCR'ın metni doğru okuduğunu kontrol edin (Log sekmesinde göreceksiniz).
- Tespit edilecek metinleri düzenleyebilirsiniz (varsayılan: yeniden başla, şehirde yeniden…).

### 2. Hareket Dizisi Sekmesi
Ölüm sonrası karakterin izleyeceği yolu burada tanımlayın:

- **"➕ Tıklama Ekle"** → Haritada bir noktaya tıklamak için: X ve Y koordinat girin
  - 📍 Koordinatı öğrenmek için "Konum Al" butonuna basın ve 3 saniye içinde mouse'u o noktaya götürün
- **"⌨ Tuş Ekle"** → Klavye tuşu basmak için (örn: `w`, `d`, `F5`)
- **"⏳ Bekleme Ekle"** → Bekleme süresi ekleyin
- Son olarak **"✓ Kaydet"** butonuna basın.

### 3. Tuşlar Sekmesi
- Oto-av tuşunu girin (örn: `F5`, `F6`, `f`, `r`)
- Veya "Tuşu Dinleyerek Seç" ile tuşa basarak otomatik algılatın.

### 4. Başlatma
- **"▶ BAŞLAT"** butonuna basın.
- Bot ekranı taramaya başlar; karakter öldüğünde:
  1. "Yeniden Başla" butonuna tıklar
  2. Hareket dizisini uygular
  3. Oto-av tuşuna basar

## İpuçları

- macOS'ta **Sistem Tercihleri → Gizlilik → Erişilebilirlik** ve **Ekran Kaydı** izinlerini Python'a verin.
- Tarama aralığını (ms) düşürürseniz daha hızlı tepki verir ama CPU kullanımı artar.
- Mouse sol-üst köşeye giderse program güvenlik modunda durur (PyAutoGUI failsafe).
- Log sekmesinde tüm işlemleri takip edebilirsiniz.
