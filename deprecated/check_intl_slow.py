#!/usr/bin/env python3
"""
Langsamer internationaler Check - mit langen Pausen gegen Rate-Limits.
Usage: python3 check_intl_slow.py
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
    loc_elem = await row.query_selector('span[aria-label*="Item location:"]')
    if loc_elem:
        aria = await loc_elem.get_attribute('aria-label') or ''
        title = await loc_elem.get_attribute('data-bs-original-title') or ''
        for text in [aria, title]:
            match = re.search(r'Item location:\s*(\w+)', text)
            if match:
                return match.group(1)
    return 'Unknown'


async def check_product(browser_context, product_key):
    cfg = PRODUCTS[product_key]
    url = cfg['url']
    page = await browser_context.new_page()

    try:
        print(f"\n{'='*60}")
        print(f"🌍 {cfg['name']}")
        print(f"URL: {url}")
        print('-'*60)

        print("🌐 Lade Produktseite...")
        response = await page.goto(url, wait_until='domcontentloaded', timeout=90000)
        print(f"📊 Status: {response.status}")

        if response.status == 429:
            print("⚠️ Rate-Limit! Warte 60 Sekunden...")
            await asyncio.sleep(60)
            await page.close()
            return None

        await page.wait_for_timeout(8000)  # Länger warten für Content

        # Scrolle für Lazy-Loading
        for i in range(8):
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(2500)

        rows = await page.query_selector_all('.article-row')
        print(f"📦 {len(rows)} Listings gefunden")

        if not rows:
            print("❌ Keine Listings - möglicherweise blockiert")
            await page.close()
            return None

        # Parse internationale Listings
        listings = []
        for row in rows[:60]:
            try:
                seller_elem = await row.query_selector('a[href*="/Users/"]')
                seller = await seller_elem.text_content() if seller_elem else 'Unknown'
                seller = seller.strip() if seller else 'Unknown'

                price_elem = await row.query_selector('.price, .fw-bold')
                price_text = await price_elem.text_content() if price_elem else '0 €'
                match = re.search(r'([\d,]+)\s*€', price_text or '')
                price = float(match.group(1).replace(',', '.')) if match else 0

                location = await extract_location(row)

                if seller != 'Unknown' and price > 0 and location != 'Germany':
                    listings.append({
                        'seller': seller,
                        'price': price,
                        'location': location
                    })
            except Exception:
                continue

        if not listings:
            print("❌ Keine internationalen Angebote gefunden")
            await page.close()
            return None

        # Sortiere nach Preis
        listings.sort(key=lambda x: x['price'])

        print(f"\n🌍 TOP 5 INTERNATIONALE ANGEBOTE:")
        for i, l in enumerate(listings[:5], 1):
            print(f"  {i}. {l['seller']}: {l['price']:.2f}€ ({l['location']})")

        # Nimm das günstigste für Versand-Details
        cheapest = listings[0]
        print(f"\n🔍 Prüfe Versand für: {cheapest['seller']} ({cheapest['location']})")

        # Seller-Profil öffnen
        seller_url = f"https://www.cardmarket.com/en/Users/{cheapest['seller']}"
        print(f"   Öffne: {seller_url}")

        await page.goto(seller_url, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(5000)

        # Klicke auf Shipping-Tab
        shipping_selectors = [
            'a[href*="/Shipping"]',
            'a.nav-link:has-text("Shipping")',
            'button:has-text("Shipping")',
            'a:has-text("Versand")'
        ]

        for sel in shipping_selectors:
            try:
                link = await page.query_selector(sel)
                if link:
                    await link.click()
                    await page.wait_for_timeout(4000)
                    break
            except:
                pass

        # Extrahiere Versanddaten
        shipping_costs = {}
        shipping_table = await page.query_selector('table.table')

        if shipping_table:
            print(f"\n📋 Versandtabelle:")
            table_rows = await shipping_table.query_selector_all('tr')

            for row in table_rows:
                try:
                    cells = await row.query_selector_all('td, th')
                    if len(cells) >= 2:
                        cell_texts = []
                        for cell in cells:
                            text = await cell.text_content()
                            cell_texts.append(' '.join(text.split()))
                        row_text = ' | '.join(cell_texts)

                        if 'Germany' in row_text or 'Deutschland' in row_text:
                            print(f"   → {row_text[:120]}")
                            # Preise extrahieren
                            prices = re.findall(r'(\d+[,.]\d+)\s*[€$€]', row_text)
                            if prices:
                                shipping_costs['standard'] = prices[0]
                                if len(prices) > 1:
                                    shipping_costs['tracked'] = prices[1]
                except:
                    continue
        else:
            print("   Keine Versandtabelle gefunden")

        await page.close()

        # Ergebnis
        result = {
            'product': cfg['name'],
            'seller': cheapest['seller'],
            'location': cheapest['location'],
            'price': cheapest['price'],
            'shipping': shipping_costs
        }

        print(f"\n💰 ERGEBNIS:")
        print(f"   Artikel: {cheapest['price']:.2f}€")
        if shipping_costs:
            for method, cost in shipping_costs.items():
                cost_float = float(cost.replace(',', '.'))
                total = cheapest['price'] + cost_float
                print(f"   + Versand ({method}): {cost}€")
                print(f"   = GESAMT: {total:.2f}€")
        else:
            print(f"   + Versand: unbekannt (geschätzt 10-20€)")
            print(f"   = Geschätzter Total: {cheapest['price'] + 15:.2f}€")

        return result

    except Exception as e:
        print(f"❌ Fehler bei {product_key}: {e}")
        await page.close()
        return None


async def main():
    print("🌐 Internationaler Floor-Check (langsam)")
    print("⏳ Starte in 60 Sekunden (Rate-Limit Schutz)...")
    await asyncio.sleep(60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 2500},
            locale='de-DE',
            timezone_id='Europe/Berlin'
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """)

        results = []
        for i, key in enumerate(PRODUCTS):
            result = await check_product(context, key)
            if result:
                results.append(result)

            # Lange Pause zwischen Produkten
            if i < len(PRODUCTS) - 1:
                print(f"\n⏳ Pause: Warte 90 Sekunden vor nächstem Produkt...")
                await asyncio.sleep(90)

        await browser.close()

        # Zusammenfassung
        print(f"\n{'='*60}")
        print("📊 ZUSAMMENFASSUNG")
        print('='*60)

        for r in results:
            print(f"\n{r['product']}:")
            print(f"   {r['seller']} ({r['location']}): {r['price']:.2f}€")
            if r['shipping']:
                costs = [float(v.replace(',', '.')) for v in r['shipping'].values()]
                min_shipping = min(costs) if costs else 15
                print(f"   Versand: {min_shipping:.2f}€")
                print(f"   → GESAMT: {r['price'] + min_shipping:.2f}€")
            else:
                print(f"   → Geschätzt: {r['price'] + 15:.2f}€ (inkl. 15€ Versand)")


if __name__ == '__main__':
    asyncio.run(main())
