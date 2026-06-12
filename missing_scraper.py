#!/usr/bin/env python3
"""
Scrapes Cardmarket floor prices for missing Origins cards.
- Loads missing cards from local DB + DotGG API
- Opens each Cardmarket product page with filters: sellerCountry=7&language=1
- Extracts cheapest listing price
- Saves results to missing_prices.json
- Rate limit: min 4.5s between requests
"""

import asyncio
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

REPO = Path(__file__).resolve().parent
DB_PATH = REPO / 'cardmarket.db'
OUTPUT_PATH = REPO / 'missing_prices.json'

CARDS_URL = 'https://api.dotgg.gg/cgfw/getcards?game=riftbound'

# Headers for urllib
import urllib.request


def http_get(url, headers=None, timeout=20):
    h = headers or {}
    h.setdefault('User-Agent', 'DotGG/2.0 (Mobile; iOS)')
    h.setdefault('Accept', 'application/json')
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"⚠️ HTTP error for {url}: {e}")
        raise


def get_missing_cards():
    """Fetch DotGG cards and local collection, return missing Origins cards with cmurl."""
    print("📥 Fetching DotGG card catalog...")
    cards = http_get(CARDS_URL)
    origins = [c for c in cards if c.get('set_name') == 'Origins']
    print(f"   → {len(origins)} Origins cards total")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT card_id, standard_count, foil_count FROM user_collection')
    collection = {row[0]: row[1] + row[2] for row in cur.fetchall()}
    conn.close()
    print(f"   → {len(collection)} cards in local collection")

    missing = []
    for c in origins:
        if collection.get(c['id'], 0) == 0 and c.get('cmurl'):
            missing.append(c)

    print(f"   → {len(missing)} missing cards with Cardmarket URL")
    return missing


async def extract_floor_price(page, card_name):
    """Extract cheapest price from first .article-row on page."""
    try:
        await page.wait_for_selector('.article-row', timeout=20000)
        # Wait a bit for dynamic content
        await page.wait_for_timeout(1500)
        
        rows = await page.query_selector_all('.article-row')
        if not rows:
            return None, "No listings found"

        row = rows[0]
        price_elem = await row.query_selector('.price, .fw-bold')
        if not price_elem:
            return None, "Price element not found"
        
        price_text = await price_elem.text_content()
        match = re.search(r'([\d,]+)\s*€', price_text or '')
        if not match:
            return None, f"Could not parse price: {price_text}"
        
        price = float(match.group(1).replace(',', '.'))
        
        # Also extract seller name if available
        seller_elem = await row.query_selector('a[href*="/Users/"]')
        seller = ''
        if seller_elem:
            seller = (await seller_elem.text_content() or '').strip()
        
        return price, seller
    except Exception as e:
        return None, str(e)


async def scrape_cards(missing_cards):
    results = []
    errors = []
    total = len(missing_cards)
    
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
        
        for idx, card in enumerate(missing_cards, 1):
            card_id = card['id']
            name = card['name']
            url = card['cmurl']
            promo = card.get('promo') == '1'
            rarity = card.get('rarity', '')
            
            # Append filters
            separator = '&' if '?' in url else '?'
            filter_url = f"{url}{separator}sellerCountry=7&language=1"
            
            print(f"\n[{idx}/{total}] {card_id} — {name}")
            print(f"    URL: {filter_url}")
            
            page = await context.new_page()
            try:
                response = await page.goto(filter_url, wait_until='domcontentloaded', timeout=45000)
                if response.status >= 400:
                    errors.append({'id': card_id, 'name': name, 'error': f'HTTP {response.status}'})
                    print(f"    ❌ HTTP {response.status}")
                    continue
                
                price, seller = await extract_floor_price(page, name)
                if price is not None:
                    results.append({
                        'id': card_id,
                        'name': name,
                        'rarity': rarity,
                        'promo': promo,
                        'floor_price': price,
                        'seller': seller,
                        'url': filter_url,
                        'scraped_at': datetime.now().isoformat(),
                    })
                    print(f"    ✅ {price:.2f}€ (Seller: {seller})")
                else:
                    errors.append({'id': card_id, 'name': name, 'error': seller})
                    print(f"    ⚠️ {seller}")
                    
            except Exception as e:
                errors.append({'id': card_id, 'name': name, 'error': str(e)[:200]})
                print(f"    ❌ Exception: {e}")
            finally:
                await page.close()
            
            # Rate limit: wait at least 4.5s before next request
            if idx < total:
                await asyncio.sleep(4.5)
        
        await browser.close()
    
    return results, errors


def save_results(results, errors, missing_count):
    output = {
        'scraped_at': datetime.now().isoformat(),
        'missing_total': missing_count,
        'scraped_count': len(results),
        'error_count': len(errors),
        'results': results,
        'errors': errors,
    }
    
    total_cost = sum(r['floor_price'] for r in results)
    output['total_cost'] = round(total_cost, 2)
    
    # Summary by rarity
    rarity_summary = {}
    for r in results:
        rarity_summary.setdefault(r['rarity'], {'count': 0, 'cost': 0.0})
        rarity_summary[r['rarity']]['count'] += 1
        rarity_summary[r['rarity']]['cost'] += r['floor_price']
    
    output['summary_by_rarity'] = {
        k: {'count': v['count'], 'cost': round(v['cost'], 2)}
        for k, v in sorted(rarity_summary.items())
    }
    
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print(f"💾 Saved to: {OUTPUT_PATH}")
    print(f"📊 Scraped: {len(results)} / {missing_count}")
    print(f"💰 Total cost: {total_cost:.2f}€")
    print(f"⚠️ Errors: {len(errors)}")
    if errors:
        print("Errors:")
        for e in errors:
            print(f"   - {e['id']} {e['name']}: {e['error']}")


async def main():
    missing = get_missing_cards()
    if not missing:
        print("No missing cards found!")
        return 0
    
    results, errors = await scrape_cards(missing)
    save_results(results, errors, len(missing))
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
