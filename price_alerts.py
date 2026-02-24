#!/usr/bin/env python3
"""
Cardmarket Price Alerts
Checks for notable floor price movements and listing spikes.
Sends alerts to Riftbound Rippers group.

Usage: python3 price_alerts.py [--dry-run]
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

# --- Config ---

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
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')  # Riftbound Rippers group

DRY_RUN = '--dry-run' in sys.argv

PRODUCTS = {
    1: {'name': 'Arcane Box Set',        'threshold': 175.0},
    2: {'name': 'Origins Booster Box',   'threshold': 178.0},
    3: {'name': 'Spiritforged Booster',  'threshold': 153.0},
}

DROP_PCT_TRIGGER = 0.05   # 5% drop vs 24h avg
LISTING_SPIKE_TRIGGER = 0.25  # 25% listing increase vs prev scrape

RETRY_ATTEMPTS = 3
RETRY_DELAY_S = 5


# --- Telegram ---

def send_telegram(message, retries=RETRY_ATTEMPTS):
    if DRY_RUN:
        print(f"[DRY RUN] Would send:\n{message}")
        return True
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Missing token or chat_id — stdout only:")
        print(message)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for attempt in range(1, retries + 1):
        try:
            data = urllib.parse.urlencode({
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML',
            }).encode()
            req = urllib.request.Request(url, data=data, method='POST')
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                if result.get('ok'):
                    return True
                print(f"⚠️  Telegram not ok (attempt {attempt}): {result.get('description')}")
        except Exception as e:
            print(f"❌ Telegram error (attempt {attempt}/{retries}): {e}")

        if attempt < retries:
            time.sleep(RETRY_DELAY_S)

    print("❌ All Telegram retries exhausted — alert not delivered!")
    return False


# --- DB helpers ---

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA busy_timeout = 5000')
    conn.row_factory = sqlite3.Row
    return conn


def get_latest(cursor, product_id):
    cursor.execute('''
        SELECT floor_price, total_listings, scraped_at
        FROM scrapes WHERE product_id = ?
        ORDER BY scraped_at DESC LIMIT 1
    ''', (product_id,))
    return cursor.fetchone()


def get_avg_24h(cursor, product_id):
    cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        SELECT AVG(floor_price) as avg_floor, COUNT(*) as n
        FROM scrapes
        WHERE product_id = ? AND scraped_at >= ?
    ''', (product_id, cutoff))
    return cursor.fetchone()


def get_prev_listings(cursor, product_id):
    """Second most recent scrape for listing comparison."""
    cursor.execute('''
        SELECT total_listings, scraped_at
        FROM scrapes WHERE product_id = ?
        ORDER BY scraped_at DESC LIMIT 2
    ''', (product_id,))
    rows = cursor.fetchall()
    return rows[1] if len(rows) >= 2 else None


# --- Checks ---

def check_product(cursor, pid, cfg):
    name = cfg['name']
    threshold = cfg['threshold']
    alerts = []

    latest = get_latest(cursor, pid)
    if not latest:
        return alerts

    floor = latest['floor_price']
    listings = latest['total_listings']

    # 1) Absolute threshold
    if floor is not None and floor < threshold:
        alerts.append(
            f"📉 <b>{name}</b>: Floor bei <b>{floor:.2f}€</b> — unter Schwellwert ({threshold:.0f}€)"
        )

    # 2) Drop >5% vs 24h average
    avg_row = get_avg_24h(cursor, pid)
    if avg_row and avg_row['avg_floor'] and avg_row['n'] >= 3:
        avg_24h = avg_row['avg_floor']
        if floor is not None and avg_24h > 0:
            drop_pct = (avg_24h - floor) / avg_24h
            if drop_pct >= DROP_PCT_TRIGGER:
                alerts.append(
                    f"⚠️ <b>{name}</b>: Floor {floor:.2f}€ — "
                    f"<b>{drop_pct*100:.1f}% unter 24h-Ø</b> ({avg_24h:.2f}€)"
                )

    # 3) Listing spike vs prev scrape
    prev = get_prev_listings(cursor, pid)
    if prev and prev['total_listings'] and listings:
        prev_listings = prev['total_listings']
        spike_pct = (listings - prev_listings) / prev_listings
        if spike_pct >= LISTING_SPIKE_TRIGGER:
            alerts.append(
                f"📦 <b>{name}</b>: Listings von {prev_listings} → <b>{listings}</b> "
                f"(+{spike_pct*100:.0f}%) — möglicher Preisdruck"
            )

    return alerts


# --- Main ---

def run():
    if not os.path.exists(DB_PATH):
        print(f"❌ DB nicht gefunden: {DB_PATH}")
        return 1

    conn = get_conn()
    cursor = conn.cursor()

    all_alerts = []
    for pid, cfg in PRODUCTS.items():
        all_alerts.extend(check_product(cursor, pid, cfg))

    conn.close()

    if not all_alerts:
        print(f"✅ Keine Preis-Alerts ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
        return 0

    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    msg = f"🔔 <b>Cardmarket Alert</b> — {now}\n\n"
    msg += '\n\n'.join(all_alerts)

    print(msg)
    send_telegram(msg)
    return 0


if __name__ == '__main__':
    sys.exit(run())
