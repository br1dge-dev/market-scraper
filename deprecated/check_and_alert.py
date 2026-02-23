#!/usr/bin/env python3
"""
Cardmarket Alert Checker - Wrapper für Scraper mit Floor-Preis-Vergleich
Best Practice: Deterministische Alert-Logik, keine KI-Halluzination
"""

import sqlite3
import os
import sys
import subprocess
import json
from datetime import datetime
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
    1: {'name': 'Arcane Box Set', 'scraper': 'scraper_full.py', 'product_id': 1},
    2: {'name': 'Origins Booster EN', 'scraper': 'scraper_origins.py', 'product_id': 2},
    3: {'name': 'Spiritforged Booster EN', 'scraper': 'scraper_spiritforged.py', 'product_id': 3}
}

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def get_last_floor(cursor, product_id):
    """Holt den vorherigen Floor-Preis aus der DB"""
    cursor.execute('''
        SELECT floor_price, scraped_at 
        FROM scrapes 
        WHERE product_id = ? 
        ORDER BY id DESC 
        LIMIT 1 OFFSET 1
    ''', (product_id,))
    result = cursor.fetchone()
    return (result[0], result[1]) if result else (None, None)

def send_telegram_alert(product_name, current_floor, previous_floor, listings_count, drop_percent):
    """Sendet Alert via Telegram Bot API"""
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN nicht gesetzt, Alert wird nicht gesendet")
        return False
    
    emoji = "🚨" if drop_percent > 10 else "📉"
    message = f"""{emoji} <b>Riftbound Preis-Alert</b>

<b>{product_name}</b>
💶 Floor: <b>{current_floor:.2f}€</b> (vorher: {previous_floor:.2f}€)
📉 Drop: <b>-{drop_percent:.1f}%</b>
📦 Listings: {listings_count}

🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
    
    import urllib.request
    import urllib.parse
    
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
            if result.get('ok'):
                print(f"✅ Alert gesendet: {product_name} @ {current_floor:.2f}€")
                return True
            else:
                print(f"❌ Telegram API Fehler: {result}")
                return False
    except Exception as e:
        print(f"❌ Fehler beim Senden: {e}")
        return False

def run_scraper(product_id):
    """Führt den Scraper aus und gibt das Ergebnis zurück"""
    product = PRODUCTS.get(product_id)
    if not product:
        print(f"❌ Unbekanntes Produkt: {product_id}")
        return None, None
    
    scraper_path = f"/Users/robert/.openclaw/workspace/skills/cardmarket-tracker/{product['scraper']}"
    
    print(f"🦀 Starte Scraper: {product['scraper']}")
    try:
        result = subprocess.run(
            ['python3', scraper_path],
            capture_output=True,
            text=True,
            timeout=300,
            cwd='/Users/robert/.openclaw/workspace/skills/cardmarket-tracker'
        )
        print(result.stdout)
        if result.stderr:
            print(f"⚠️ Stderr: {result.stderr}")
        
        # Prüfe ob Scraper erfolgreich war
        if result.returncode != 0:
            print(f"❌ Scraper failed with exit code {result.returncode}")
            print(f"Stderr: {result.stderr}")
            return None, None
        
        # Scraper gibt "Floor: XXX.XX€" aus - parsen wir den
        floor = None
        listings = None
        for line in result.stdout.split('\n'):
            if 'Floor-Price:' in line or 'Floor:' in line:
                import re
                # Regex matched Zahlen mit Punkt ODER Komma als Dezimal-Trennzeichen
                match = re.search(r'([\d]+[.,]?[\d]*)\s*€', line)
                if match:
                    floor = float(match.group(1).replace(',', '.'))
            if 'Listings:' in line or 'gesammelt:' in line:
                import re
                match = re.search(r'(\d+)', line)
                if match:
                    listings = int(match.group(1))
        
        return floor, listings
    except subprocess.TimeoutExpired:
        print("❌ Scraper Timeout nach 5 Minuten")
        return None, None
    except Exception as e:
        print(f"❌ Scraper Fehler: {e}")
        return None, None

def check_product(product_id):
    """Haupt-Logik: Scrape → Vergleich → Alert bei Bedarf"""
    product = PRODUCTS[product_id]
    print(f"\n{'='*50}")
    print(f"🔍 Prüfe: {product['name']}")
    print(f"{'='*50}")
    
    # Vorherigen Floor holen
    conn = get_db_connection()
    cursor = conn.cursor()
    previous_floor, previous_time = get_last_floor(cursor, product_id)
    conn.close()
    
    if previous_floor:
        print(f"📊 Vorheriger Floor: {previous_floor:.2f}€ ({previous_time})")
    else:
        print("ℹ️ Keine Historie (erster Run)")
    
    # Scraper ausführen
    current_floor, listings_count = run_scraper(product_id)
    
    if current_floor is None:
        print("❌ Scraper lieferte keinen Floor-Preis")
        return False
    
    print(f"📊 Aktueller Floor: {current_floor:.2f}€")
    
    # Vergleich und Alert (nur bei gültigen Preisen > 0)
    if previous_floor and previous_floor > 0 and current_floor and current_floor > 0:
        drop_percent = ((previous_floor - current_floor) / previous_floor) * 100
        print(f"📉 Veränderung: {drop_percent:+.2f}%")
        
        if drop_percent >= 5.0:
            print(f"🚨 ALERT: Drop > 5% erkannt!")
            send_telegram_alert(
                product['name'],
                current_floor,
                previous_floor,
                listings_count or 0,
                drop_percent
            )
        else:
            print(f"✅ Kein Alert: Drop ({drop_percent:.1f}%) unter 5% Schwelle")
    else:
        print("ℹ️ Kein Vergleich möglich (erster Scrape oder ungültiger Preis)")
    
    return True

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 check_and_alert.py <product_id>")
        print("  product_id: 1=Arcane, 2=Origins, 3=Spiritforged")
        print("\nUmgebungsvariablen:")
        print("  TELEGRAM_BOT_TOKEN - Bot Token für Alerts")
        print("  TELEGRAM_CHAT_ID   - Ziel-Chat (default: -5223953277)")
        sys.exit(1)
    
    try:
        product_id = int(sys.argv[1])
        if product_id not in PRODUCTS:
            print(f"❌ Ungültige Produkt-ID: {product_id}")
            print(f"Gültig: {list(PRODUCTS.keys())}")
            sys.exit(1)
    except ValueError:
        print("❌ Produkt-ID muss eine Zahl sein")
        sys.exit(1)
    
    success = check_product(product_id)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
