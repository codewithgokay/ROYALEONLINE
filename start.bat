@echo off
title Royale Online Bot — Launcher
color 0A

echo.
echo  ===========================================
echo   Royale Online -- Oto-Av Botu
echo   github.com/codewithgokay/ROYALEONLINE
echo  ===========================================
echo.

:: ── Python kontrolü ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [HATA] Python bulunamadi!
    echo.
    echo  Cozum: https://www.python.org/downloads/
    echo  Kurulumda "Add Python to PATH" secenegini isaretleyin!
    echo.
    pause
    exit /b 1
)

echo  [OK] Python bulundu:
python --version
echo.

:: ── Sanal ortam ──────────────────────────────────────────────────────────────
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

:: ── Pip güncelle ─────────────────────────────────────────────────────────────
echo  [2/3] pip guncelleniyor...
.venv\Scripts\python -m pip install --upgrade pip --quiet
echo  [OK] pip guncellendi.
echo.

:: ── Paketleri teker teker yükle (hangisi hata verirse belli olsun) ────────────
echo  [3/3] Gerekli paketler yukleniyor...
echo.

set FAILED=0

call :install_pkg "pillow>=9.0.0"
call :install_pkg "pytesseract>=0.3.10"
call :install_pkg "pyautogui>=0.9.50"
call :install_pkg "pynput>=1.7.0"
call :install_pkg "mss>=6.1.0"
call :install_pkg "pygetwindow>=0.0.9"

if %FAILED%==1 (
    echo.
    echo  ============================================
    echo   BAZI PAKETLER YUKLENEMEDI (yukarda gorun)
    echo   Bot yine de calisabilir, devam ediliyor...
    echo  ============================================
    echo.
    timeout /t 4 /nobreak >nul
)

:: ── Tesseract kontrolü ───────────────────────────────────────────────────────
echo.
if not exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    if not exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" (
        echo  [UYARI] Tesseract bulunamadi!
        echo.
        echo  OCR olmadan olum ekrani TANINAMAZ.
        echo  Tesseract'i buradan indir (kurulumda "Turkish" sec):
        echo  https://github.com/UB-Mannheim/tesseract/wiki
        echo.
        choice /C YN /M "  Tesseract olmadan yine de devam et?"
        if errorlevel 2 (
            start https://github.com/UB-Mannheim/tesseract/wiki
            pause
            exit /b 0
        )
    ) else (
        echo  [OK] Tesseract bulundu (x86).
    )
) else (
    echo  [OK] Tesseract bulundu.
)

:: ── Botu başlat ──────────────────────────────────────────────────────────────
echo.
echo  Bot baslatiliyor...
echo.
.venv\Scripts\python royale_bot.py

if errorlevel 1 (
    echo.
    echo  [HATA] Bot beklenmedik sekilde kapandi.
    echo  Hata mesajini yukarda inceleyin.
    pause
)
goto :eof

:: ── Yardımcı fonksiyon ───────────────────────────────────────────────────────
:install_pkg
set PKG=%~1
echo    Yukleniyor: %PKG%
.venv\Scripts\pip install "%PKG%" --quiet
if errorlevel 1 (
    echo    [HATA] Yuklenemedi: %PKG%
    set FAILED=1
) else (
    echo    [OK] %PKG%
)
goto :eof
