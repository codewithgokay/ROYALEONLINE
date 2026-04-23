#!/bin/bash
# macOS double-click launcher for Royale Online Bot
# Çift tıklayarak çalıştırmak için: chmod +x start.command

cd "$(dirname "$0")"

echo ""
echo " ╔══════════════════════════════════════════╗"
echo " ║     Royale Online — Oto-Av Botu          ║"
echo " ╚══════════════════════════════════════════╝"
echo ""

# ── Python kontrolü ──────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo " [HATA] python3 bulunamadı!"
    echo " Lütfen https://www.python.org adresinden Python 3.10+ yükleyin."
    read -p " Devam etmek için Enter'a bas..."
    exit 1
fi

# ── Sanal ortam ──────────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo " [1/3] Sanal ortam oluşturuluyor..."
    python3 -m venv .venv
fi

# ── Bağımlılıklar ────────────────────────────────────────────────────────────
echo " [2/3] Bağımlılıklar kontrol ediliyor..."
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

# ── Tesseract kontrolü ───────────────────────────────────────────────────────
if ! command -v tesseract &>/dev/null; then
    if [ ! -f "/opt/homebrew/bin/tesseract" ] && [ ! -f "/usr/local/bin/tesseract" ]; then
        echo ""
        echo " [UYARI] Tesseract bulunamadı!"
        echo " Yüklemek için: brew install tesseract tesseract-lang"
        echo ""
    fi
fi

# ── Başlat ───────────────────────────────────────────────────────────────────
echo " [3/3] Bot başlatılıyor..."
echo ""
.venv/bin/python royale_bot.py

echo ""
read -p " Bot kapandı. Çıkmak için Enter'a bas..."
