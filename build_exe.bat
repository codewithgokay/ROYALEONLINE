@echo off
title Royale Bot — EXE Builder
color 0B

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║     Royale Online Bot — EXE Builder      ║
echo  ║     PyInstaller ile tek dosya olusturur  ║
echo  ╚══════════════════════════════════════════╝
echo.
echo  Bu script RoyaleBot.exe dosyasini olusturur.
echo  Tamamlanmasi birkaç dakika surebilir...
echo.

:: ── Venv ve bağımlılıklar ─────────────────────────────────────────────────────
if not exist ".venv\" (
    echo  [1/4] Sanal ortam olusturuluyor...
    python -m venv .venv
)

echo  [2/4] PyInstaller yukleniyor...
.venv\Scripts\pip install -q pyinstaller pillow pytesseract pyautogui pynput mss pygetwindow

:: ── Build ─────────────────────────────────────────────────────────────────────
echo  [3/4] EXE olusturuluyor...
echo.

.venv\Scripts\pyinstaller ^
    --onefile ^
    --windowed ^
    --name "RoyaleBot" ^
    --add-data "macro_recorder.py;." ^
    --hidden-import "PIL._tkinter_finder" ^
    --hidden-import "pynput.keyboard._win32" ^
    --hidden-import "pynput.mouse._win32" ^
    royale_bot.py

if errorlevel 1 (
    echo.
    echo  [HATA] Build basarisiz oldu. Hata mesajini yukarda inceleyin.
    pause
    exit /b 1
)

:: ── Sonuç ────────────────────────────────────────────────────────────────────
echo.
echo  [4/4] Tamamlandi!
echo.
echo  ✓ EXE dosyasi: dist\RoyaleBot.exe
echo.
echo  NOT: EXE calistirabilmek icin Tesseract ayri olarak kurulmalidir.
echo  https://github.com/UB-Mannheim/tesseract/wiki
echo.

choice /C YN /M "  dist\ klasorunu ac?"
if errorlevel 1 if not errorlevel 2 explorer dist\

pause
