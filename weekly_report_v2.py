#!/usr/bin/env python3
"""
Cardmarket Weekly Report v2 - Premium Telegram Report
Sparklines, Trends, Insights (wie Daily v2, aber für 7 Tage)
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

PRODUCTS = {
    1: {'name': 'Arcane Box Set', 'emoji': '🔮'},
    2: {'name': 'Origins Booster', 'emoji': '🦋'},
    3: {'name': 'Spiritforged Booster', 'emoji': '⚔️'},
}

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
        'disable_web_page_preview': 'true',
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


def get_weekly_data(cursor, product_id):
    """Holt tägliche Floor-Preise der letzten 7 Tage (1x pro Tag)."""
    cursor.execute('''
        SELECT floor_price, scraped_at
        FROM scrapes
        WHERE product_id = ? AND scraped_at > datetime('now', '-7 days')
        ORDER BY scraped_at ASC
    ''', (product_id,))
    return cursor.fetchall()


def get_weekly_stats(cursor, product_id):
    """Holt Wochen-Stats (Min/Max/Avg)."""
    cursor.execute('''
        SELECT 
            MIN(floor_price) as min_price,
            MAX(floor_price) as max_price,
            AVG(floor_price) as avg_price,
            MIN(total_listings) as min_listings,
            MAX(total_listings) as max_listings,
            COUNT(*) as scrape_count
        FROM scrapes
        WHERE product_id = ? 
        AND scraped_at > datetime('now', '-7 days')
    ''', (product_id,))
    return cursor.fetchone()


def get_current_and_week_ago(cursor, product_id):
    """Aktueller + Vorwoche Preis für Trend."""
    cursor.execute('''
        SELECT floor_price
        FROM scrapes
        WHERE product_id = ?
        ORDER BY scraped_at DESC LIMIT 1
    ''', (product_id,))
    current = cursor.fetchone()
    
    cursor.execute('''
        SELECT floor_price
        FROM scrapes
        WHERE product_id = ? AND scraped_at < datetime('now', '-6 days')
        ORDER BY scraped_at DESC LIMIT 1
    ''', (product_id,))
    week_ago = cursor.fetchone()
    
    return current[0] if current else None, week_ago[0] if week_ago else None


def get_weekly_sales(cursor):
    """Holt Verkaufsverdachte der Woche."""
    cursor.execute('''
        SELECT p.name, COUNT(*) as cnt, MIN(s.price) as min_p, MAX(s.price) as max_p
        FROM suspected_sales s
        JOIN products p ON s.product_id = p.id
        WHERE s.detected_at > datetime('now', '-7 days')
        GROUP BY s.product_id
    ''')
    return cursor.fetchall()


def format_change(current, previous):
    """Formatiert Preisänderung mit Pfeilen."""
    if not previous or not current:
        return '🆕'
    diff = current - previous
    pct = (diff / previous) * 100 if previous else 0
    if abs(pct) < 0.5:
        return '➡️ stabil'
    arrow = '📈' if diff > 0 else '📉'
    sign = '+' if diff > 0 else ''
    return f'{arrow} {sign}{diff:.2f}€ ({sign}{pct:.1f}%)'


def generate_weekly_report():
    conn = get_db()
    cursor = conn.cursor()

    now = datetime.now()
    today_str = now.strftime('%d.%m.%Y')
    week_start = (now - timedelta(days=7)).strftime('%d.%m.')

    lines = []
    lines.append(f'📈 <b>RIFTBOUND WEEKLY REPORT</b>')
    lines.append(f'🗓️ {week_start} - {today_str}')
    lines.append('━' * 22)
    lines.append('')

    product_data = {}

    for pid, pcfg in PRODUCTS.items():
        weekly_data = get_weekly_data(cursor, pid)
        stats = get_weekly_stats(cursor, pid)
        current, week_ago = get_current_and_week_ago(cursor, pid)

        if not stats or not stats[0] or not current:
            lines.append(f'{pcfg["emoji"]} <b>{pcfg["name"]}:</b> Keine Daten')
            lines.append('')
            continue

        min_price, max_price, avg_price, min_listings, max_listings, count = stats
        
        # Sparkline aus täglichen Daten
        daily_prices = [r[0] for r in weekly_data] if weekly_data else [current]
        spark = sparkline(daily_prices)
        
        # Best day/time für Bestpreis
        best_day = '—'
        if weekly_data:
            min_idx = daily_prices.index(min(daily_prices))
            try:
                best_time = datetime.fromisoformat(weekly_data[min_idx][1])
                best_day = best_time.strftime('%a %H:%M')
            except:
                best_day = weekly_data[min_idx][1][:10]

        # Trend Vergleich Woche
        change_str = format_change(current, week_ago)
        
        # Listings Range
        listings_change = ''
        if min_listings and max_listings:
            if max_listings != min_listings:
                listings_change = f' ({min_listings}-{max_listings})'
            else:
                listings_change = f' ({min_listings})'

        lines.append(f'{pcfg["emoji"]} <b>{pcfg["name"]}</b>')
        lines.append(f'   💶 Floor: <b>{current:.2f}€</b>  {change_str}')
        lines.append(f'   📊 Ø Schnitt: {avg_price:.2f}€')
        lines.append(f'   📉 Range: {min_price:.2f}€ - {max_price:.2f}€')
        lines.append(f'   📦 Listings: Aktuell{listings_change}')
        lines.append(f'   📈 7-Tage: <code>{spark}</code>')
        if min_price < current:
            lines.append(f'   ⏰ Bestpreis: {best_day} ({min_price:.2f}€)')
        lines.append(f'   🔄 Scans: {count}')
        lines.append('')

        product_data[pid] = {
            'floor': current,
            'avg': avg_price,
            'name': pcfg['name'],
            'emoji': pcfg['emoji']
        }

    # Suspected sales
    sales = get_weekly_sales(cursor)
    if sales:
        lines.append('🚨 <b>Verkaufsverdacht (7 Tage)</b>')
        for name, cnt, min_p, max_p in sales:
            if min_p == max_p:
                lines.append(f'   • {name}: {cnt}x @ {min_p:.2f}€')
            else:
                lines.append(f'   • {name}: {cnt}x ({min_p:.2f}–{max_p:.2f}€)')
        lines.append('')

    # Market overview
    if product_data:
        cheapest = min(product_data.values(), key=lambda x: x['floor'])
        lines.append('━' * 22)
        lines.append(f'🏷️ Günstigster: <b>{cheapest["name"]}</b> ({cheapest["floor"]:.2f}€)')
        
        # Ranking by floor price
        sorted_p = sorted(product_data.values(), key=lambda x: x['floor'])
        ranking = ' → '.join(f'{p["emoji"]}{p["floor"]:.0f}€' for p in sorted_p)
        lines.append(f'🏆 {ranking}')
        
        # Ranking by average
        sorted_avg = sorted(product_data.values(), key=lambda x: x['avg'])
        avg_ranking = ' → '.join(f'{p["emoji"]}{p["avg"]:.0f}€' for p in sorted_avg)
        lines.append(f'📊 Ø-Schnitt: {avg_ranking}')

    lines.append('')
    lines.append('<i>Wochenbericht | cardmarket.com | stündlich gescannt</i>')

    conn.close()
    return '\n'.join(lines)


def main():
    print("📈 Generiere Weekly Report v2...")
    report = generate_weekly_report()
    print()
    print(report)
    print()
    if send_telegram_message(report):
        print("✅ Weekly Report gesendet")
    else:
        print("❌ Fehler beim Senden")
        return 1
    return 0


if __name__ == '__main__':
    exit(main())
