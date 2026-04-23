#!/usr/bin/env python3
"""
keyboard_listener.py — Bağımsız Klavye Kaydedici
==================================================
Ana süreçten subprocess olarak çağrılır.
pynput bu scriptin KENDİ ana thread'inde çalışır → TSM crash olmaz.
Olayları JSON satırları olarak stdout'a yazar.

Kullanım:
    python keyboard_listener.py <start_time_float>
"""

import sys
import json
import time

start_time = float(sys.argv[1]) if len(sys.argv) > 1 else time.time()

try:
    from pynput import keyboard as _kb
except ImportError:
    sys.exit(0)


def _on_press(key):
    try:
        ch = key.char          # Normal karakter (a, b, 1, ...)
    except AttributeError:
        ch = key.name          # Özel tuş (space, enter, f1, ...)

    if ch:
        ev = {
            "type": "key",
            "key":  ch,
            "t":    round(time.time() - start_time, 3),
        }
        try:
            sys.stdout.write(json.dumps(ev) + "\n")
            sys.stdout.flush()
        except Exception:
            pass


try:
    with _kb.Listener(on_press=_on_press) as listener:
        listener.join()
except Exception:
    pass
