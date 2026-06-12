#!/usr/bin/env python3
"""
Cardmarket Daily Report v2 - Premium Telegram Report
Sparklines, Trends, Insights, Market Overview
"""

import sqlite3
import os
import json
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
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

from products import PRODUCTS, by_category, boxes as box_products

SPARKLINE_CHARS = '▁▂▃▄▅▆▇█'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA busy_timeout = 5000')
    return conn


def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN nicht gesetzt")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': 'true',  # Telegram API expects string
        'disable_notification': 'false',
    }).encode()
    try:
        req = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode())
            return result.get('ok', False)
    except Exception as e:
        print(f"❌ Fehler beim Senden: {e}")
        return False


def sparkline(values):
    """Erzeugt Unicode-Sparkline aus einer Liste von Zahlen."""
    if not values or len(values) < 2:
        return '—'
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    return ''.join(SPARKLINE_CHARS[min(int((v - mn) / rng * 7), 7)] for v in values)


def get_24h_floors(cursor, product_id):
    """Holt stündliche Floor-Preise der letzten 24h."""
    cursor.execute('''
        SELECT floor_price, scraped_at
        FROM scrapes
        WHERE product_id = ? AND scraped_at > datetime('now', '-24 hours')
        ORDER BY scraped_at ASC
    ''', (product_id,))
    return cursor.fetchall()


def get_current_and_previous(cursor, product_id):
    """Aktueller + 24h-vorheriger Scrape."""
    cursor.execute('''
        SELECT floor_price, total_listings, scraped_at
        FROM scrapes WHERE product_id = ?
        ORDER BY id DESC LIMIT 1
    ''', (product_id,))
    current = cursor.fetchone()

    cursor.execute('''
        SELECT floor_price, total_listings
        FROM scrapes
        WHERE product_id = ? AND scraped_at < datetime('now', '-20 hours')
        ORDER BY id DESC LIMIT 1
    ''', (product_id,))
    previous = cursor.fetchone()

    return current, previous


def get_suspected_sales_24h(cursor):
    cursor.execute('''
        SELECT p.name, COUNT(*) as cnt, MIN(s.price) as min_p, MAX(s.price) as max_p
        FROM suspected_sales s
        JOIN products p ON s.product_id = p.id
        WHERE s.detected_at > datetime('now', '-24 hours')
        GROUP BY s.product_id
    ''')
    return cursor.fetchall()


def format_change(current, previous):
    if not previous or not current:
        return '🆕'
    diff = current - previous
    pct = (diff / previous) * 100 if previous else 0
    if abs(pct) < 0.5:
        return '➡️ stabil'
    arrow = '📈' if diff > 0 else '📉'
    sign = '+' if diff > 0 else ''
    return f'{arrow} {sign}{diff:.2f}€ ({sign}{pct:.1f}%)'


def generate_report():
    conn = get_db()
    cursor = conn.cursor()

    now = datetime.now()
    today_str = now.strftime('%d.%m.%Y')
    time_str = now.strftime('%H:%M')

    lines = []
    lines.append(f'📊 <b>RIFTBOUND MARKTBERICHT</b>')
    lines.append(f'🕐 {today_str} · {time_str} Uhr')
    lines.append('━' * 22)
    lines.append('')

    product_data = {}

    # Render je Kategorie (Booster Boxes, Box Sets, Singles getrennt)
    for cat, cat_label, cat_products in by_category():
        lines.append(f'<b>{cat_label}</b>')
        for pid, pcfg in cat_products.items():
            current, previous = get_current_and_previous(cursor, pid)
            floors_24h = get_24h_floors(cursor, pid)

            if not current:
                lines.append(f'{pcfg["emoji"]} <b>{pcfg["short_name"]}</b>: Keine Daten')
                lines.append('')
                continue

            floor = current[0]
            listings = current[1]
            prev_floor = previous[0] if previous else None
            prev_listings = previous[1] if previous else None

            prices = [r[0] for r in floors_24h]
            times = [r[1] for r in floors_24h]

            low_24h = min(prices) if prices else floor
            high_24h = max(prices) if prices else floor
            spark = sparkline(prices)

            best_time = '—'
            if prices and times:
                min_idx = prices.index(min(prices))
                try:
                    best_time = datetime.fromisoformat(times[min_idx]).strftime('%H:%M')
                except:
                    best_time = times[min_idx][-5:]

            change_str = format_change(floor, prev_floor)

            listing_change = ''
            if prev_listings:
                ldiff = listings - prev_listings
                if ldiff != 0:
                    sign = '+' if ldiff > 0 else ''
                    listing_change = f' ({sign}{ldiff})'

            lines.append(f'{pcfg["emoji"]} <b>{pcfg["short_name"]}</b>  <b>{floor:.2f}€</b>  {change_str}')
            lines.append(f'   24h: {low_24h:.2f}–{high_24h:.2f}€ · {listings} Listings{listing_change}')
            lines.append(f'   <code>{spark}</code>')
            if low_24h < floor:
                lines.append(f'   ⏰ Tief: {best_time} ({low_24h:.2f}€)')
            lines.append('')

            product_data[pid] = {
                'floor': floor, 'listings': listings,
                'name': pcfg['short_name'], 'emoji': pcfg['emoji'],
                'category': pcfg['category'],
            }

    # Suspected sales
    sales = get_suspected_sales_24h(cursor)
    if sales:
        lines.append('🚨 <b>Verkaufsverdacht (24h)</b>')
        for name, cnt, min_p, max_p in sales:
            if min_p == max_p:
                lines.append(f'   • {name}: {cnt}x @ {min_p:.2f}€')
            else:
                lines.append(f'   • {name}: {cnt}x ({min_p:.2f}–{max_p:.2f}€)')
        lines.append('')

    # Markt-Überblick: NUR Booster-Markt (BBs + Box Sets), Singles separat
    box_data = {pid: v for pid, v in product_data.items() if v['category'] in ('booster-box', 'box-set')}
    single_data = {pid: v for pid, v in product_data.items() if v['category'] == 'single'}

    if box_data:
        cheapest_box = min(box_data.values(), key=lambda x: x['floor'])
        total_box_listings = sum(v['listings'] for v in box_data.values())

        lines.append('━' * 22)
        lines.append(f'📦 Günstigste Box: <b>{cheapest_box["name"]}</b> ({cheapest_box["floor"]:.2f}€)')
        lines.append(f'📊 Box-Markt: {total_box_listings} Listings')

        sorted_b = sorted(box_data.values(), key=lambda x: x['floor'])
        ranking = ' → '.join(f'{p["emoji"]}{p["floor"]:.0f}€' for p in sorted_b)
        lines.append(f'🏆 Box-Ranking: {ranking}')

    lines.append('')
    lines.append('<i>cardmarket.com · DE Seller · EN Karten · stündlich gescannt</i>')

    conn.close()
    return '\n'.join(lines)


def main():
    print("📊 Generiere Daily Report v2...")
    report = generate_report()
    print()
    print(report)
    print()
    if send_telegram_message(report):
        print("✅ Report gesendet")
    else:
        print("❌ Fehler beim Senden")
        return 1
    return 0


if __name__ == '__main__':
    exit(main())
