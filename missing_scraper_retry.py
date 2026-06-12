#!/usr/bin/env python3
"""
Retry scraper for missing Origins cards that got 403/blocked.
Reads existing missing_prices.json and retries failed cards with much longer delays.
"""

import asyncio
import json
import os
import random
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

REPO = Path(__file__).resolve().parent
INPUT_PATH = REPO / 'missing_prices.json'
OUTPUT_PATH = REPO / 'missing_prices.json'


def load_existing():
    if not INPUT_PATH.exists():
        return {'results': [], 'errors': []}
    with open(INPUT_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_failed_cards(existing):
    """Return list of card dicts from existing errors that we want to retry."""
    errors = existing.get('errors', [])
    cards = []
    for e in errors:
        cards.append({
            'id': e['id'],
            'name': e['name'],
            'cmurl': e.get('url', ''),  # URL may not be stored in error; we'll rebuild
            'promo': 'Promo' in e['name'],
            'rarity': '',
        })
    return cards


async def extract_floor_price(page):
    try:
        await page.wait_for_selector('.article-row', timeout=20000)
        await page.wait_for_timeout(2000)
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
        seller_elem = await row.query_selector('a[href*=\"/Users/\"]')
        seller = ''
        if seller_elem:
            seller = (await seller_elem.text_content() or '').strip()
        return price, seller
    except Exception as e:
        return None, str(e)


async def scrape_card(page, card, attempt=0):
    card_id = card['id']
    name = card['name']
    url = card.get('cmurl', '')
    if not url:
        # Rebuild URL from slug if possible, but we don't have it here.
        # Try to use the card_id pattern or just return error.
        return None, "No URL available"
    
    separator = '&' if '?' in url else '?'
    filter_url = f"{url}{separator}sellerCountry=7&language=1"
    
    try:
        response = await page.goto(filter_url, wait_until='domcontentloaded', timeout=45000)
        if response.status >= 400:
            if response.status == 403 and attempt < 3:
                return 'retry_403', f"HTTP 403"
            return None, f"HTTP {response.status}"
        price, seller = await extract_floor_price(page)
        if price is not None:
            return {
                'id': card_id,
                'name': name,
                'rarity': card.get('rarity', ''),
                'promo': card.get('promo', False),
                'floor_price': price,
                'seller': seller,
                'url': filter_url,
                'scraped_at': datetime.now().isoformat(),
            }, None
        else:
            return None, seller
    except Exception as e:
        return None, str(e)


async def scrape_cards(cards):
    results = []
    still_errors = []
    total = len(cards)
    
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
        
        for idx, card in enumerate(cards, 1):
            card_id = card['id']
            name = card['name']
            print(f"\n[{idx}/{total}] {card_id} — {name}")
            
            result, error = await scrape_card(page, card, attempt=0)
            
            if result == 'retry_403':
                # Long backoff for 403
                backoff = 60 + random.uniform(30, 60)
                print(f"    🚫 403 — backing off {backoff:.0f}s...")
                await asyncio.sleep(backoff)
                result, error = await scrape_card(page, card, attempt=1)
                if result == 'retry_403':
                    backoff2 = 120 + random.uniform(30, 60)
                    print(f"    🚫 403 again — backing off {backoff2:.0f}s...")
                    await asyncio.sleep(backoff2)
                    result, error = await scrape_card(page, card, attempt=2)
                    if result == 'retry_403':
                        error = "HTTP 403 after 3 attempts"
                        result = None
            
            if result and result != 'retry_403':
                results.append(result)
                print(f"    ✅ {result['floor_price']:.2f}€ (Seller: {result['seller']})")
            else:
                still_errors.append({'id': card_id, 'name': name, 'error': error})
                print(f"    ❌ {error}")
            
            # Rate limit: wait 25-35s between requests
            if idx < total:
                delay = 25 + random.uniform(0, 10)
                print(f"    ⏳ Waiting {delay:.1f}s...")
                await asyncio.sleep(delay)
        
        await browser.close()
    
    return results, still_errors


def merge_and_save(existing, new_results, new_errors):
    # Merge results: overwrite by id
    all_results = {r['id']: r for r in existing.get('results', [])}
    for r in new_results:
        all_results[r['id']] = r
    
    # Errors are just the ones that still failed
    output = {
        'scraped_at': datetime.now().isoformat(),
        'missing_total': existing.get('missing_total', 0),
        'scraped_count': len(all_results),
        'error_count': len(new_errors),
        'results': list(all_results.values()),
        'errors': new_errors,
    }
    
    total_cost = sum(r['floor_price'] for r in all_results.values())
    output['total_cost'] = round(total_cost, 2)
    
    rarity_summary = {}
    for r in all_results.values():
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
    print(f"📊 Total scraped: {len(all_results)} / {output['missing_total']}")
    print(f"💰 Total cost: {total_cost:.2f}€")
    print(f"⚠️ Remaining errors: {len(new_errors)}")
    if new_errors:
        for e in new_errors:
            print(f"   - {e['id']} {e['name']}: {e['error']}")


async def main():
    existing = load_existing()
    failed = get_failed_cards(existing)
    if not failed:
        print("No failed cards to retry!")
        return 0
    
    print(f"🔄 Retrying {len(failed)} failed cards with longer delays...")
    results, errors = await scrape_cards(failed)
    merge_and_save(existing, results, errors)
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
