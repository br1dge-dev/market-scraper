#!/usr/bin/env python3
"""
Cardmarket Scraper Watchdog
Checks if scrapes have run recently. Alerts via Telegram if not.
Usage: python3 watchdog.py [--max-age-hours 2]
"""

import sqlite3
import os
import sys
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

# .env laden
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value.strip('"\''))

DB_PATH = os.getenv('CARDMARKET_DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cardmarket.db'))
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
# Watchdog alerts go to br1dge directly, not the group
TELEGRAM_ALERT_CHAT_ID = os.getenv('TELEGRAM_ALERT_CHAT_ID')

MAX_AGE_HOURS = 2

from products import PRODUCTS as _P
PRODUCTS = {pid: p['short_name'] for pid, p in _P.items()}


def send_telegram(message, chat_id=None, retries=3, delay=5):
    if not TELEGRAM_BOT_TOKEN:
        print(f"⚠️ No token — stdout only: {message}")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for attempt in range(1, retries + 1):
        try:
            data = urllib.parse.urlencode({
                'chat_id': chat_id or TELEGRAM_ALERT_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML',
            }).encode()
            req = urllib.request.Request(url, data=data, method='POST')
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                if result.get('ok'):
                    return True
                print(f"⚠️ Telegram not ok (attempt {attempt}): {result.get('description')}")
        except Exception as e:
            print(f"❌ Telegram error (attempt {attempt}/{retries}): {e}")
        if attempt < retries:
            time.sleep(delay)
    print("❌ All Telegram retries exhausted — alert not delivered!")
    return False


def check():
    if not os.path.exists(DB_PATH):
        send_telegram("🚨 <b>Watchdog:</b> cardmarket.db nicht gefunden!")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA busy_timeout = 5000')
    cursor = conn.cursor()

    cutoff = datetime.utcnow() - timedelta(hours=MAX_AGE_HOURS)
    cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')

    missing = []
    for pid, pname in PRODUCTS.items():
        cursor.execute('''
            SELECT MAX(scraped_at) FROM scrapes WHERE product_id = ?
        ''', (pid,))
        row = cursor.fetchone()
        last_scrape = row[0] if row and row[0] else None

        if not last_scrape or last_scrape < cutoff_str:
            age = "nie" if not last_scrape else last_scrape
            missing.append(f"• {pname}: letzter Scrape {age}")

    conn.close()

    if missing:
        msg = f"🚨 <b>Scraper Watchdog Alert</b>\n"
        msg += f"Keine Daten seit {MAX_AGE_HOURS}h für:\n\n"
        msg += '\n'.join(missing)
        msg += f"\n\n<i>Prüfe ob crontab läuft: crontab -l</i>"
        print(msg)
        send_telegram(msg)
        return 1
    else:
        print(f"✅ Alle Produkte haben Daten der letzten {MAX_AGE_HOURS}h")
        return 0


if __name__ == '__main__':
    if '--max-age-hours' in sys.argv:
        idx = sys.argv.index('--max-age-hours')
        if idx + 1 < len(sys.argv):
            MAX_AGE_HOURS = int(sys.argv[idx + 1])
    sys.exit(check())
