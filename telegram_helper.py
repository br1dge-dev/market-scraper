#!/usr/bin/env python3
"""
telegram_helper.py — zentrale Send-Funktion für alle Cardmarket-Skripte.

Best Practice:
- 1 Aufruf = 1 Telegram-Nachricht (kein Multi-Send-Pattern)
- HTML parse_mode konsistent oder Plain Text — niemals mischen
- disable_web_page_preview als String 'true' (Telegram API quirk)
- Fehlerbehandlung mit klarem Output

Usage:
    from telegram_helper import send_telegram

    send_telegram("📊 Mein Report", parse_mode='HTML')
    send_telegram("plain text alert", parse_mode=None)
"""

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path


def _load_env():
    env_file = Path(__file__).resolve().parent / '.env'
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith('#') or '=' not in s:
            continue
        k, v = s.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def send_telegram(text, parse_mode='HTML', chat_id=None, disable_preview=True, silent=False):
    """
    Sendet eine Telegram-Nachricht. Returns (ok: bool, response: dict|None).

    parse_mode: 'HTML' (default), 'MarkdownV2', oder None für plain text
    chat_id: optional override, default aus TELEGRAM_CHAT_ID env var
    disable_preview: True (default) — verhindert Link-Previews
    silent: True für stille Notifications (kein Sound)
    """
    _load_env()
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print("⚠️ TELEGRAM_BOT_TOKEN nicht gesetzt")
        return False, None

    cid = chat_id or os.getenv('TELEGRAM_CHAT_ID')
    if not cid:
        print("⚠️ TELEGRAM_CHAT_ID nicht gesetzt")
        return False, None

    payload = {
        'chat_id': cid,
        'text': text,
        'disable_web_page_preview': 'true' if disable_preview else 'false',
        'disable_notification': 'true' if silent else 'false',
    }
    if parse_mode:
        payload['parse_mode'] = parse_mode

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(payload).encode()

    try:
        req = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read().decode())
            return result.get('ok', False), result
    except Exception as e:
        print(f"❌ Telegram-Send-Fehler: {e}")
        return False, None


def send_telegram_photo(photo_path, caption=None, parse_mode='HTML', chat_id=None):
    """Sendet ein lokales Bild. photo_path muss existieren."""
    _load_env()
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print("⚠️ TELEGRAM_BOT_TOKEN nicht gesetzt")
        return False, None

    cid = chat_id or os.getenv('TELEGRAM_CHAT_ID')
    p = Path(photo_path)
    if not p.exists():
        print(f"❌ Bild nicht gefunden: {photo_path}")
        return False, None

    # Multipart form via stdlib — minimal manual implementation
    import mimetypes
    import uuid

    boundary = f"----openclaw{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(str(p))[0] or 'image/png'

    body = []
    body.append(f"--{boundary}\r\n".encode())
    body.append(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{cid}\r\n'.encode())
    if caption:
        body.append(f"--{boundary}\r\n".encode())
        body.append(f'Content-Disposition: form-data; name="caption"\r\n\r\n'.encode())
        body.append(caption.encode())
        body.append(b"\r\n")
        if parse_mode:
            body.append(f"--{boundary}\r\n".encode())
            body.append(f'Content-Disposition: form-data; name="parse_mode"\r\n\r\n{parse_mode}\r\n'.encode())
    body.append(f"--{boundary}\r\n".encode())
    body.append(f'Content-Disposition: form-data; name="photo"; filename="{p.name}"\r\n'.encode())
    body.append(f"Content-Type: {mime}\r\n\r\n".encode())
    body.append(p.read_bytes())
    body.append(f"\r\n--{boundary}--\r\n".encode())

    data = b"".join(body)
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    req = urllib.request.Request(
        url, data=data, method='POST',
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read().decode())
            return result.get('ok', False), result
    except Exception as e:
        print(f"❌ Photo-Send-Fehler: {e}")
        return False, None


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: telegram_helper.py <message> [parse_mode]")
        sys.exit(1)
    msg = sys.argv[1]
    pm = sys.argv[2] if len(sys.argv) > 2 else 'HTML'
    ok, _ = send_telegram(msg, parse_mode=pm if pm.lower() != 'none' else None)
    sys.exit(0 if ok else 1)
