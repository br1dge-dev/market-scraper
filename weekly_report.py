#!/usr/bin/env python3
"""
Cardmarket Weekly Report - Deterministisch, keine KI
Erstellt sonntags um 21:00 einen Wochenbericht
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

DB_PATH = os.getenv('CARDMARKET_DB_PATH', '/Users/robert/Projects/cardmarket-tracker/cardmarket.db')
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

def get_weekly_stats(cursor, product_id):
    """Holt Wochen-Stats (Min/Max/Avg)"""
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

def get_weekly_sales(cursor):
    """Holt Verkaufsverdachte der Woche"""
    cursor.execute('''
        SELECT p.name, s.seller, s.price, s.confidence
        FROM suspected_sales s
        JOIN products p ON s.product_id = p.id
        WHERE s.detected_at > datetime('now', '-7 days')
        ORDER BY s.detected_at DESC
    ''')
    return cursor.fetchall()

def generate_weekly_report():
    """Generiert den Weekly Report"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    today_str = datetime.now().strftime('%d.%m.%Y')
    week_start = (datetime.now() - timedelta(days=7)).strftime('%d.%m.')
    
    report = f"📈 <b>RIFTBOUND WEEKLY REPORT</b>\n"
    report += f"🗓️ {week_start} - {today_str}\n"
    report += "━" * 25 + "\n\n"
    
    # Pro Produkt
    for pid, pname in PRODUCTS.items():
        stats = get_weekly_stats(cursor, pid)
        
        if not stats or not stats[0]:
            report += f"❌ <b>{pname}</b>: Keine Daten\n\n"
            continue
        
        min_price, max_price, avg_price, min_listings, max_listings, count = stats
        volatility = ((max_price - min_price) / min_price * 100) if min_price else 0
        
        report += f"<b>{pname}</b>\n"
        report += f"💶 Range: {min_price:.2f}€ - {max_price:.2f}€\n"
        report += f"📊 Ø Durchschnitt: {avg_price:.2f}€\n"
        report += f"📈 Volatilität: {volatility:.1f}%\n"
        report += f"📦 Listings: {min_listings}-{max_listings}\n"
        report += f"🔄 Scans: {count}\n\n"
    
    # Verkaufsverdachte
    sales = get_weekly_sales(cursor)
    if sales:
        report += "🚨 <b>Verkaufsverdachte (7 Tage)</b>\n"
        sales_by_product = {}
        for product, seller, price, conf in sales:
            if product not in sales_by_product:
                sales_by_product[product] = []
            sales_by_product[product].append((seller, price, conf))
        
        for product, items in sales_by_product.items():
            report += f"\n<b>{product}</b>: {len(items)}\n"
            for seller, price, conf in items[:3]:  # Max 3 pro Produkt
                report += f"  • {seller} @ {price:.2f}€\n"
        report += "\n"
    else:
        report += "✅ Keine Verkaufsverdachte\n\n"
    
    # Fazit
    report += "━" * 25 + "\n"
    report += "<i>Wochenbericht basierend auf stündlichen Scans | cardmarket.com</i>\n"
    report += "<i>Verkaufsverdacht = Seller aus Q1 Preisrange nicht mehr gelistet</i>"
    
    conn.close()
    return report

def main():
    print(f"📈 Generiere Weekly Report...")
    
    report = generate_weekly_report()
    
    print("\n" + "="*50)
    print(report)
    print("="*50)
    
    if send_telegram_message(report):
        print("✅ Weekly Report gesendet")
    else:
        print("❌ Fehler beim Senden")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
