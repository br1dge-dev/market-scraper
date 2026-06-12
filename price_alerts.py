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

from products import PRODUCTS

ATL_DROP_PCT = 0.05   # 5% unter bisherigem ATL = Alert
ATL_ALERTS_LOG = Path(__file__).parent / '.atl_alerts_sent.json'  # Dedup-Tracking

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


def get_all_time_low(cursor, product_id):
    """Historischer Tiefstpreis (min floor_price) für Produkt."""
    cursor.execute('''
        SELECT MIN(floor_price) as atl
        FROM scrapes
        WHERE product_id = ? AND floor_price IS NOT NULL
    ''', (product_id,))
    row = cursor.fetchone()
    return row['atl'] if row and row['atl'] else None


def load_atl_alerts_log():
    """Gesendete ATL-Alerts laden (für Dedup)."""
    if ATL_ALERTS_LOG.exists():
        with open(ATL_ALERTS_LOG) as f:
            return json.load(f)
    return {}


def save_atl_alerts_log(log):
    """Gesendete ATL-Alerts speichern."""
    with open(ATL_ALERTS_LOG, 'w') as f:
        json.dump(log, f, indent=2)


# --- Checks ---

def check_product_atl(cursor, pid, cfg, alerts_log):
    """
    ATL-only Alert-Logik:
    - Meldet nur wenn aktueller Floor < (ATL * 0.95) — mind. 5% unter bisherigem Tief
    - Dedupliziert: Gleicher Floor-Preis nicht mehrfach melden
    """
    name = cfg['name']
    alerts = []

    latest = get_latest(cursor, pid)
    if not latest or latest['floor_price'] is None:
        return alerts

    current_floor = latest['floor_price']
    atl = get_all_time_low(cursor, pid)

    if atl is None:
        return alerts  # Noch keine Historie

    # Prüfe: Ist current_floor ein neuer ATL (mind. 5% unter bisherigem ATL)?
    atl_threshold = atl * (1 - ATL_DROP_PCT)

    if current_floor <= atl_threshold:
        # Dedup-Check: Haben wir diesen Floor-Preis bereits gemeldet?
        product_key = str(pid)
        last_alerted_floor = alerts_log.get(product_key)

        if last_alerted_floor == current_floor:
            return alerts  # Schon gemeldet

        drop_pct = (atl - current_floor) / atl * 100
        alerts.append(
            f"🚨 <b>NEUER ATL — {name}</b>\n"
            f"   Floor: <b>{current_floor:.2f}€</b> (vorher: {atl:.2f}€)\n"
            f"   <b>{drop_pct:.1f}% unter bisherigem Tief</b>"
        )
        # Speichere für Dedup
        alerts_log[product_key] = current_floor

    return alerts


# --- Main ---

def run():
    if not os.path.exists(DB_PATH):
        print(f"❌ DB nicht gefunden: {DB_PATH}")
        return 1

    # ATL-Alert-Log laden (für Dedup)
    alerts_log = load_atl_alerts_log()

    conn = get_conn()
    cursor = conn.cursor()

    all_alerts = []
    for pid, cfg in PRODUCTS.items():
        all_alerts.extend(check_product_atl(cursor, pid, cfg, alerts_log))

    conn.close()

    if not all_alerts:
        print(f"✅ Keine ATL-Alerts ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
        return 0

    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    msg = f"🔔 <b>Cardmarket ATL Alert</b> — {now}\n\n"
    msg += '\n\n'.join(all_alerts)

    print(msg)
    success = send_telegram(msg)

    if success:
        save_atl_alerts_log(alerts_log)

    return 0


if __name__ == '__main__':
    sys.exit(run())
