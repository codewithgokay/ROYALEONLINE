@echo off
title Royale Online Bot — Launcher
color 0A

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║     Royale Online — Oto-Av Botu          ║
echo  ║     github.com/codewithgokay/ROYALEONLINE ║
echo  ╚══════════════════════════════════════════╝
echo.

:: ── Python kontrolü ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [HATA] Python bulunamadi!
    echo  Lutfen https://www.python.org/downloads/ adresinden Python 3.10+ yukleyin.
    echo  Kurulum sirasinda "Add Python to PATH" secenegini isaretleyin!
    pause
    exit /b 1
)

:: ── Sanal ortam olustur (ilk calistirmada) ───────────────────────────────────
if not exist ".venv\" (
    echo  [1/3] Sanal ortam olusturuluyor...
    python -m venv .venv
    if errorlevel 1 (
        echo  [HATA] Sanal ortam olusturulamadi.
        pause
        exit /b 1
    )
    echo  [OK] Sanal ortam hazir.
    echo.
)

:: ── Bağımlılıkları yükle ─────────────────────────────────────────────────────
echo  [2/3] Gerekli kutuphaneler kontrol ediliyor / yukleniyor...
.venv\Scripts\pip install -q --upgrade pip
.venv\Scripts\pip install -q -r requirements.txt
if errorlevel 1 (
    echo  [HATA] Kutuphaneler yuklenemedi. requirements.txt dosyasini kontrol edin.
    pause
    exit /b 1
)
echo  [OK] Tum kutuphaneler hazir.
echo.

:: ── Tesseract kontrolü ───────────────────────────────────────────────────────
if not exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    if not exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" (
        echo  [UYARI] Tesseract bulunamadi!
        echo  OCR ozelligi icin Tesseract yukleyin:
        echo  https://github.com/UB-Mannheim/tesseract/wiki
        echo.
        echo  Tesseract olmadan bot calisir ama olum ekrani TANINAMAZ.
        echo.
        choice /C YN /M "  Tesseract olmadan devam etmek istiyor musun?"
        if errorlevel 2 (
            start https://github.com/UB-Mannheim/tesseract/wiki
            pause
            exit /b 0
        )
    )
)

:: ── Botu başlat ──────────────────────────────────────────────────────────────
echo  [3/3] Bot baslatiliyor...
echo.
.venv\Scripts\python royale_bot.py

if errorlevel 1 (
    echo.
    echo  [HATA] Bot beklenmedik sekilde kapandi.
    pause
)
