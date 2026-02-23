#!/usr/bin/env python3
"""
One-off check: Find cheapest international offer and extract shipping costs.
Usage: python3 check_intl_shipping.py <product>
"""

import re
import sys
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

PRODUCTS = {
    'origins': {
        'name': 'Origins Booster Box',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Booster-Boxes/Origins-Booster-Box',
    },
    'spiritforged': {
        'name': 'Spiritforged Booster Box',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Booster-Boxes/Spiritforged-Booster-Box',
    },
    'arcane': {
        'name': 'Arcane Box Set',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Box-Sets/Arcane-Box-Set',
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


async def check_product(product_key, initial_delay=0):
    # Warte am Anfang, falls Rate-Limit aktiv
    if initial_delay > 0:
        print(f"⏳ Warte {initial_delay}s (Rate-Limit Schutz)...")
        await asyncio.sleep(initial_delay)
    
    cfg = PRODUCTS[product_key]
    url = cfg['url']

    print(f"\n🌍 {cfg['name']}")
    print(f"URL: {url}")
    print("-" * 50)

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
            # Lade Seite OHNE Country-Filter
            print("🌐 Lade internationale Angebote...")
            response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            print(f"📊 Status: {response.status}")

            if response.status == 429:
                print("⚠️ Rate-limited von Cardmarket. Warte 10 Sekunden...")
                await page.wait_for_timeout(10000)

            await page.wait_for_selector('.article-row', timeout=30000)
            await page.wait_for_timeout(5000)

            # Scrolle für Lazy-Loading
            for _ in range(5):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(2000)

            rows = await page.query_selector_all('.article-row')
            print(f"📦 {len(rows)} Listings gefunden")

            listings = []
            for row in rows[:50]:  # Nur Top 50 für Performance
                try:
                    seller_elem = await row.query_selector('a[href*="/Users/"]')
                    seller = await seller_elem.text_content() if seller_elem else 'Unknown'

                    price_elem = await row.query_selector('.price, .fw-bold')
                    price_text = await price_elem.text_content() if price_elem else '0 €'
                    match = re.search(r'([\d,]+)\s*€', price_text or '')
                    price = float(match.group(1).replace(',', '.')) if match else 0

                    location = await extract_location(row)

                    # Finde den Artikel-Link
                    article_url = None
                    link_elem = await row.query_selector('a.article-row__link, a[href*="/Products/"], a[href*="/sell/items/"]')
                    if link_elem:
                        href = await link_elem.get_attribute('href')
                        if href:
                            if href.startswith('/'):
                                article_url = 'https://www.cardmarket.com' + href
                            elif not href.startswith('http'):
                                article_url = 'https://www.cardmarket.com/' + href
                            else:
                                article_url = href

                    if seller != 'Unknown' and price > 0 and location != 'Germany':
                        listings.append({
                            'seller': seller.strip(),
                            'price': price,
                            'location': location,
                            'url': article_url
                        })

                except Exception:
                    continue

            if not listings:
                print("❌ Keine internationalen Angebote gefunden")
                await browser.close()
                return

            # Sortiere nach Preis
            listings.sort(key=lambda x: x['price'])

            print(f"\n🌍 GÜNSTIGSTE INTERNATIONALE ANGEBOTE:")
            for i, l in enumerate(listings[:5], 1):
                print(f"  {i}. {l['seller']}: {l['price']:.2f}€ ({l['location']}) - {l['url'][:60] if l['url'] else 'no url'}...")

            # Nimm das günstigste und prüfe Versand
            cheapest = listings[0]
            print(f"\n🔍 Prüfe Versandkosten für günstigstes Angebot...")
            print(f"   Seller: {cheapest['seller']}")
            print(f"   Preis: {cheapest['price']:.2f}€")
            print(f"   Location: {cheapest['location']}")

            # Baue Seller-URL direkt
            seller_name = cheapest['seller'].replace(' ', '%20')
            seller_url = f"https://www.cardmarket.com/en/Users/{seller_name}"
            print(f"\n🔍 Prüfe Seller-Profil: {seller_url}")

            await page.goto(seller_url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(4000)

            # Suche nach Shipping-Link oder -Tab
            shipping_link = await page.query_selector('a[href*="/Shipping"], a:has-text("Shipping"), a:has-text("Versand")')
            if shipping_link:
                await shipping_link.click()
                await page.wait_for_timeout(4000)

            # Extrahiere Versandtabelle
            shipping_table = await page.query_selector('table.table, .shipping-rates-table, [class*="shipping"] table')
            shipping_costs = {}

            if shipping_table:
                # Hole alle Zeilen
                rows = await shipping_table.query_selector_all('tr')
                print(f"📋 Versandtabelle gefunden ({len(rows)} Zeilen):")
                current_country = None
                for row in rows:
                    row_text = await row.text_content()
                    row_text = ' '.join(row_text.split())

                    # Suche nach Germany/Deutschland-Zeilen
                    if 'Germany' in row_text or 'Deutschland' in row_text:
                        print(f"   → {row_text[:150]}")
                        # Versuche, Preis zu extrahieren
                        price_match = re.search(r'(\d+[,.]\d+)\s*[€$]', row_text)
                        if price_match:
                            shipping_costs['standard'] = price_match.group(1)
                        current_country = 'Germany'
                    elif current_country == 'Germany' and ('€' in row_text or 'tracked' in row_text.lower() or 'insured' in row_text.lower()):
                        # Folgezeilen für Germany (tracked, insured, etc.)
                        print(f"      {row_text[:150]}")
                        if 'tracked' in row_text.lower() or 'registered' in row_text.lower():
                            price_match = re.search(r'(\d+[,.]\d+)\s*[€$]', row_text)
                            if price_match:
                                shipping_costs['tracked'] = price_match.group(1)
                        if 'insured' in row_text.lower():
                            price_match = re.search(r'(\d+[,.]\d+)\s*[€$]', row_text)
                            if price_match:
                                shipping_costs['insured'] = price_match.group(1)
            else:
                # Fallback: Suche im gesamten Seitentext
                page_text = await page.text_content()
                print(f"📋 Versandinfos aus Seitentext:")
                lines = [l.strip() for l in page_text.split('\n') if l.strip()]
                for line in lines:
                    line_clean = ' '.join(line.split())
                    if 'Germany' in line_clean and len(line_clean) < 200:
                        print(f"   {line_clean[:100]}")
                        price_match = re.search(r'(\d+[,.]\d+)\s*[€$]', line_clean)
                        if price_match and 'standard' not in shipping_costs:
                            shipping_costs['standard'] = price_match.group(1)

            await browser.close()

            # Berechne Gesamtkosten
            print(f"\n💰 KOSTENÜBERSICHT:")
            print(f"   Artikelpreis: {cheapest['price']:.2f}€")
            print(f"   Verkäufer: {cheapest['seller']} ({cheapest['location']})")

            if shipping_costs:
                for method, cost in shipping_costs.items():
                    total = cheapest['price'] + float(cost.replace(',', '.'))
                    print(f"   + Versand ({method}): {cost}€")
                    print(f"   = GESAMT: {total:.2f}€")
            else:
                print(f"   + Versand: nicht ermittelt (ca. 10-20€ geschätzt)")
                print(f"   = Geschätzte Gesamtkosten: {cheapest['price'] + 15:.2f}€")

        except Exception as e:
            await browser.close()
            print(f"❌ Fehler: {e}")
            import traceback
            traceback.print_exc()


async def run_all_products():
    """Führt alle Produkte mit langen Pausen aus"""
    print("⏳ Starte in 30 Sekunden (Rate-Limit Schutz)...")
    await asyncio.sleep(30)
    
    for i, key in enumerate(PRODUCTS):
        await check_product(key, initial_delay=0)
        if i < len(PRODUCTS) - 1:  # Nach letztem Produkt nicht warten
            print("\n⏳ Warte 45 Sekunden vor nächstem Produkt...")
            await asyncio.sleep(45)
        print("\n" + "=" * 60)

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print("Usage: python3 check_intl_shipping.py <product>")
        print("  Products: origins, spiritforged, arcane")
        print("  or: all (für alle drei)")
        sys.exit(0)

    product_key = sys.argv[1].lower()

    if product_key == 'all':
        asyncio.run(run_all_products())
    elif product_key in PRODUCTS:
        asyncio.run(check_product(product_key, initial_delay=30))
    else:
        print(f"❌ Unknown product: {product_key}")
        print(f"   Valid: {', '.join(PRODUCTS.keys())}, all")
        sys.exit(1)


if __name__ == '__main__':
    main()
