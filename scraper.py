#!/usr/bin/env python3
"""
Cardmarket Unified Scraper - All Riftbound products in one file.
Usage: python3 scraper.py <product>
       product: origins | spiritforged | arcane
"""

import sqlite3
import os
import re
import sys
import asyncio
import json
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# === PRICE ALERT CONFIG ===
# Alert threshold: listings this % below floor trigger an alert
PRICE_ALERT_THRESHOLD_PCT = 5  # Alert if listing is >=5% below current floor
# ===========================

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


def send_telegram(message):
    """Send alert via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN nicht gesetzt — Alert nur auf stdout")
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
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode()).get('ok', False)
    except Exception as e:
        print(f"❌ Telegram-Fehler: {e}")
        return False

PRODUCTS = {
    'origins': {
        'id': 2,
        'name': 'Origins Booster Box',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Booster-Boxes/Origins-Booster-Box',
        'filter': 'sellerCountry=7&language=1',
        'required_location': 'Germany',
    },
    'spiritforged': {
        'id': 3,
        'name': 'Spiritforged Booster Box',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Booster-Boxes/Spiritforged-Booster-Box',
        'filter': 'sellerCountry=7&language=1',
        'required_location': 'Germany',
    },
    'arcane': {
        'id': 1,
        'name': 'Arcane Box Set',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Box-Sets/Arcane-Box-Set',
        'filter': 'sellerCountry=7&language=1',
        'required_location': 'Germany',
    },
}


async def extract_location(row):
    """Extrahiert Location aus aria-label oder data-bs-original-title"""
    loc_elem = await row.query_selector('span[aria-label*="Item location:"]')
    if loc_elem:
        aria = await loc_elem.get_attribute('aria-label') or ''
        title = await loc_elem.get_attribute('data-bs-original-title') or ''
        for text in [aria, title]:
            match = re.search(r'Item location:\s*(\w+)', text)
            if match:
                return match.group(1)
    return 'Unknown'


async def scrape_product(product_key: str):
    """Scraper für ein Produkt"""
    cfg = PRODUCTS[product_key]
    product_id = cfg['id']
    product_url = cfg['url']
    filter_url = f"{product_url}?{cfg['filter']}"
    required_location = cfg['required_location']

    print(f"🦋 {cfg['name']} Scraper - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"URL: {filter_url}")
    print(f"Required Location: {required_location}")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 2000},
            locale='de-DE',
            timezone_id='Europe/Berlin'
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """)

        page = await context.new_page()

        try:
            print("🌐 Lade Seite...")
            response = await page.goto(filter_url, wait_until='domcontentloaded', timeout=60000)
            print(f"📊 Status: {response.status}")

            await page.wait_for_selector('.article-row', timeout=30000)
            await page.wait_for_timeout(3000)

            initial_count = len(await page.query_selector_all('.article-row'))
            print(f"📦 Initiale Listings: {initial_count}")

            # Load-More Button
            load_more_selectors = [
                'button:has-text("ZEIGE MEHR")',
                'button:has-text("Load more")',
                'button:has-text("Show more")',
                '.load-more-articles',
                '[data-testid="load-more"]',
                '.table-footer button',
            ]

            print("\n🔍 Suche nach Load-More Button...")
            for selector in load_more_selectors:
                for attempt in range(10):
                    try:
                        btn = await page.query_selector(selector)
                        if btn:
                            visible = await btn.is_visible()
                            if visible:
                                # Wait for any spinner to disappear before clicking
                                try:
                                    await page.wait_for_selector('.spinner, .loader, .loading', state='hidden', timeout=5000)
                                except:
                                    pass  # Spinner might not exist
                                # Use force=True to bypass spinner interception
                                await btn.click(force=True)
                                await page.wait_for_timeout(2000)
                                new_count = len(await page.query_selector_all('.article-row'))
                                if new_count <= initial_count:
                                    break
                                initial_count = new_count
                            else:
                                break
                        else:
                            break
                    except Exception as e:
                        print(f"   ⚠️ Click failed (attempt {attempt+1}): {str(e)[:50]}")
                        await page.wait_for_timeout(1000)
                        continue

            # Scrollen
            print("\n📜 Scrolle für mehr Content...")
            last_count = initial_count
            no_change = 0
            for _ in range(20):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1000)
                current = len(await page.query_selector_all('.article-row'))
                if current > last_count:
                    last_count = current
                    no_change = 0
                else:
                    no_change += 1
                    if no_change >= 3:
                        break

            final_count = len(await page.query_selector_all('.article-row'))
            print(f"\n📊 GESAMT: {final_count} Listings geladen")

            # Extrahiere Listings MIT Location
            all_listings = []
            de_listings = []
            non_de_listings = []

            rows = await page.query_selector_all('.article-row')

            for row in rows:
                try:
                    seller_elem = await row.query_selector('a[href*="/Users/"]')
                    seller = await seller_elem.text_content() if seller_elem else 'Unknown'
                    seller = seller.strip() if seller else 'Unknown'

                    price_elem = await row.query_selector('.price, .fw-bold')
                    price_text = await price_elem.text_content() if price_elem else '0 €'
                    match = re.search(r'([\d,]+)\s*€', price_text or '')
                    price = float(match.group(1).replace(',', '.')) if match else 0

                    qty_elem = await row.query_selector('.badge, .amount, .item-count')
                    qty_text = await qty_elem.text_content() if qty_elem else '1'
                    try:
                        qty = int(re.search(r'\d+', qty_text or '1').group())
                    except:
                        qty = 1

                    location = await extract_location(row)

                    if seller and seller != 'Unknown' and price > 0:
                        listing = {'seller': seller, 'price': price, 'quantity': qty, 'location': location}
                        all_listings.append(listing)

                        if location == required_location:
                            de_listings.append(listing)
                        else:
                            non_de_listings.append(listing)

                except Exception:
                    continue

            print(f"✅ Erfolgreich geparst: {len(all_listings)} Listings")
            print(f"   🇩🇪 Germany: {len(de_listings)}")
            print(f"   🌍 Other: {len(non_de_listings)}")

            if non_de_listings:
                print(f"\n🚨 WARNUNG: {len(non_de_listings)} NON-DE Listings gefunden!")
                for l in non_de_listings[:5]:
                    print(f"   - {l['seller']}: {l['price']}€ ({l['location']})")

            if not de_listings:
                print("❌ KEINE DEUTSCHEN LISTINGS GEFUNDEN!")
                await browser.close()
                return 0, None

            floor_price = min(l['price'] for l in de_listings)
            print(f"\n💶 Floor-Price (nur DE): {floor_price:.2f}€")

            await browser.close()

            save_to_db(product_id, required_location, all_listings, floor_price, len(de_listings))
            return len(all_listings), floor_price

        except Exception as e:
            await browser.close()
            print(f"❌ Fehler: {e}")
            raise


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA busy_timeout = 5000')
    return conn


def save_to_db(product_id, required_location, listings, floor_price, de_count):
    """Speichert in SQLite"""
    conn = get_db()
    cursor = conn.cursor()

    non_de = [l for l in listings if l['location'] != required_location]

    cursor.execute('''
        INSERT INTO scrapes (product_id, total_listings, floor_price, filters_applied)
        VALUES (?, ?, ?, 'sellerCountry=7&language=1')
    ''', (product_id, de_count, floor_price))

    scrape_id = cursor.lastrowid

    for listing in listings:
        cursor.execute('''
            INSERT INTO listings (scrape_id, seller, price, quantity, location, language, condition_notes)
            VALUES (?, ?, ?, ?, ?, 'English', ?)
        ''', (scrape_id, listing['seller'], listing['price'], listing['quantity'],
              listing['location'], 'NON-DE' if listing['location'] != required_location else None))

    conn.commit()

    # Verkaufsverdacht prüfen (nur DE-Listings)
    check_suspected_sales(cursor, product_id)

    # Schnäppchen-Alert: neue Listings deutlich unter Floor
    check_price_alerts(cursor, product_id, scrape_id, floor_price)

    conn.commit()
    conn.close()

    if non_de:
        print(f"⚠️  {len(non_de)} non-DE Listings gespeichert (markiert)")
    print(f"✅ Gespeichert: Scrape #{scrape_id} ({de_count} DE Listings)")


def check_suspected_sales(cursor, product_id):
    """Prüft auf fehlende Seller (Verkaufsverdacht) - nur DE Listings!"""
    cursor.execute('SELECT id FROM scrapes WHERE product_id = ? ORDER BY id DESC LIMIT 2', (product_id,))
    scrapes = cursor.fetchall()

    if len(scrapes) < 2:
        print("ℹ️ Nicht genug Historie für Verkaufsanalyse")
        return

    current_scrape = scrapes[0][0]
    previous_scrape = scrapes[1][0]

    cursor.execute('''
        WITH prev_prices AS (
            SELECT seller, price,
                   NTILE(4) OVER (ORDER BY price) as quartile
            FROM listings WHERE scrape_id = ? AND location = 'Germany'
        ),
        current_sellers AS (
            SELECT DISTINCT seller FROM listings WHERE scrape_id = ? AND location = 'Germany'
        )
        SELECT p.seller, p.price
        FROM prev_prices p
        LEFT JOIN current_sellers c ON p.seller = c.seller
        WHERE c.seller IS NULL AND p.quartile = 1
    ''', (previous_scrape, current_scrape))

    missing_sellers = cursor.fetchall()

    for seller, price in missing_sellers:
        cursor.execute('''
            INSERT INTO suspected_sales (product_id, detected_at, seller, price, confidence, reasoning)
            VALUES (?, datetime('now'), ?, ?, 'medium', 'Seller not in current scrape, was in Q1 price range')
        ''', (product_id, seller, price))
        print(f"🚨 Verkaufsverdacht: {seller} @ {price:.2f}€")


def check_price_alerts(cursor, product_id, current_scrape_id, current_floor):
    """Check for listings significantly below floor price and print alerts."""
    if not current_floor or current_floor <= 0:
        return

    threshold = current_floor * (1 - PRICE_ALERT_THRESHOLD_PCT / 100)

    # Get previous floor to compare against (use previous scrape's floor, not current)
    cursor.execute('''
        SELECT floor_price FROM scrapes
        WHERE product_id = ? AND id < ?
        ORDER BY id DESC LIMIT 1
    ''', (product_id, current_scrape_id))
    row = cursor.fetchone()
    prev_floor = row[0] if row else None

    # Use the higher of previous floor and current floor as reference
    # This way we catch listings that are cheap relative to the market
    ref_price = max(prev_floor or 0, current_floor)
    if ref_price <= 0:
        return

    threshold = ref_price * (1 - PRICE_ALERT_THRESHOLD_PCT / 100)

    # Find bargain listings in current scrape (DE only)
    cursor.execute('''
        SELECT seller, price, quantity FROM listings
        WHERE scrape_id = ? AND location = 'Germany' AND price <= ?
        ORDER BY price ASC
    ''', (current_scrape_id, threshold))

    bargains = cursor.fetchall()

    if bargains:
        # Get product name
        cursor.execute('SELECT name FROM products WHERE id = ?', (product_id,))
        prod_row = cursor.fetchone()
        product_name = prod_row[0] if prod_row else f'Product #{product_id}'

        print(f"\n🚨🚨🚨 PRICE ALERT: {product_name} 🚨🚨🚨")
        print(f"Reference Floor: {ref_price:.2f}€ | Alert Threshold: <{threshold:.2f}€ (-{PRICE_ALERT_THRESHOLD_PCT}%)")

        alert_lines = [f'🚨 <b>PRICE ALERT: {product_name}</b>']
        alert_lines.append(f'Floor: {ref_price:.2f}€ | Threshold: &lt;{threshold:.2f}€ (-{PRICE_ALERT_THRESHOLD_PCT}%)')
        alert_lines.append('')

        for seller, price, qty in bargains:
            pct_below = ((ref_price - price) / ref_price) * 100
            print(f"  🔥 {seller}: {price:.2f}€ (x{qty}) → {pct_below:.1f}% unter Floor!")
            alert_lines.append(f'🔥 {seller}: <b>{price:.2f}€</b> (x{qty}) → {pct_below:.1f}% unter Floor')

        # Find product URL
        product_url = ''
        for key, cfg in PRODUCTS.items():
            if cfg['id'] == product_id:
                product_url = cfg['url']
                break
        if product_url:
            alert_lines.append(f'\n🛒 <a href="{product_url}">Auf Cardmarket ansehen</a>')
        print(f"🚨 {len(bargains)} Schnäppchen gefunden! 🚨\n")

        # Send Telegram alert
        send_telegram('\n'.join(alert_lines))


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print("Usage: python3 scraper.py <product>")
        print("  Products: origins, spiritforged, arcane")
        sys.exit(0 if '--help' in sys.argv else 1)

    product_key = sys.argv[1].lower()
    if product_key not in PRODUCTS:
        print(f"❌ Unknown product: {product_key}")
        print(f"   Valid: {', '.join(PRODUCTS.keys())}")
        sys.exit(1)

    count, floor = asyncio.run(scrape_product(product_key))
    if floor:
        print(f"\n🏁 FERTIG: {count} Listings, Floor: {floor:.2f}€")
    else:
        print(f"\n🏁 FERTIG: Fehler!")
        sys.exit(1)


if __name__ == '__main__':
    main()
