#!/usr/bin/env python3
"""
Cardmarket Daily Report - Deterministisch, keine KI
Erstellt täglich um 18:00 einen sauberen Marktbericht
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

DB_PATH = os.getenv('CARDMARKET_DB_PATH', '/Users/robert/.openclaw/workspace/cardmarket.db')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '-5223953277')

PRODUCTS = {
    1: 'Arcane Box Set',
    2: 'Origins Booster EN',
    3: 'Spiritforged Booster EN'
}

def send_telegram_message(message):
    """Sendet Nachricht via Telegram Bot API"""
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN nicht gesetzt")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }).encode()
    
    try:
        req = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode())
            return result.get('ok', False)
    except Exception as e:
        print(f"❌ Fehler beim Senden: {e}")
        return False

def get_product_stats(cursor, product_id):
    """Holt Stats für ein Produkt (heute vs gestern)"""
    # Heute (letzter Scrape)
    cursor.execute('''
        SELECT floor_price, total_listings, scraped_at
        FROM scrapes
        WHERE product_id = ?
        ORDER BY id DESC
        LIMIT 1
    ''', (product_id,))
    today = cursor.fetchone()
    
    # Gestern (ca. 24h zurück)
    cursor.execute('''
        SELECT floor_price, total_listings
        FROM scrapes
        WHERE product_id = ? AND scraped_at < datetime('now', '-20 hours')
        ORDER BY id DESC
        LIMIT 1
    ''', (product_id,))
    yesterday = cursor.fetchone()
    
    return today, yesterday

def get_suspected_sales(cursor, hours=24):
    """Holt Verkaufsverdachte der letzten X Stunden"""
    cursor.execute('''
        SELECT p.name, s.seller, s.price, s.detected_at
        FROM suspected_sales s
        JOIN products p ON s.product_id = p.id
        WHERE s.detected_at > datetime('now', '-{} hours')
        ORDER BY s.detected_at DESC
    '''.format(hours))
    return cursor.fetchall()

def format_price_change(current, previous):
    """Formatiert Preisänderung mit Emoji"""
    if not previous or not current:
        return "🆕 Neu"
    
    diff = current - previous
    pct = (diff / previous) * 100 if previous else 0
    
    if abs(pct) < 0.5:
        return "➡️ Stabil"
    elif diff < 0:
        return f"📉 {-diff:.2f}€ ({abs(pct):.1f}%)"
    else:
        return f"📈 +{diff:.2f}€ ({pct:.1f}%)"

def generate_daily_report():
    """Generiert den Daily Report"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    today_str = datetime.now().strftime('%d.%m.%Y')
    
    report = f"📊 <b>RIFTBOUND DAILY REPORT</b>\n"
    report += f"🕐 {today_str} 18:00\n"
    report += "━" * 20 + "\n\n"
    
    # Pro Produkt
    for pid, pname in PRODUCTS.items():
        today, yesterday = get_product_stats(cursor, pid)
        
        if not today:
            report += f"❌ <b>{pname}</b>: Keine Daten\n\n"
            continue
        
        current_floor = today[0]
        current_listings = today[1]
        prev_floor = yesterday[0] if yesterday else None
        
        change_str = format_price_change(current_floor, prev_floor)
        
        report += f"<b>{pname}</b>\n"
        report += f"💶 Floor: <b>{current_floor:.2f}€</b>\n"
        report += f"📊 Trend: {change_str}\n"
        report += f"📦 Listings: {current_listings}\n\n"
    
    # Verkaufsverdachte
    sales = get_suspected_sales(cursor, 24)
    if sales:
        report += "🚨 <b>Verkaufsverdachte (24h)</b>\n"
        for product, seller, price, detected in sales[:5]:  # Max 5
            report += f"• {seller} @ {price:.2f}€ ({product})\n"
        report += "\n"
    
    # Zusammenfassung
    report += "━" * 20 + "\n"
    report += "<i>Nur signifikante Änderungen (>2% oder >5€)</i>\n"
    report += "<i>Preise von cardmarket.com (DE Seller, EN Karten)</i>"
    
    conn.close()
    return report

def main():
    print(f"📊 Generiere Daily Report...")
    
    report = generate_daily_report()
    
    print("\n" + "="*50)
    print(report)
    print("="*50)
    
    if send_telegram_message(report):
        print("✅ Daily Report gesendet")
    else:
        print("❌ Fehler beim Senden")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
