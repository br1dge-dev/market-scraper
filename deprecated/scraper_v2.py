#!/usr/bin/env python3
"""
Cardmarket Scraper - Mit Load-Strategie gegen Cloudflare
"""

import sqlite3
import sys
import os
import re
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

DB_PATH = os.getenv('CARDMARKET_DB_PATH', '/Users/robert/.openclaw/workspace/cardmarket.db')
PRODUCT_URL = os.getenv('CARDMARKET_PRODUCT_URL', 'https://www.cardmarket.com/en/Riftbound/Products/Box-Sets/Arcane-Box-Set')
FILTER_URL = f"{PRODUCT_URL}?sellerCountry=7"

async def scrape_cardmarket():
    print(f"🦀 Cardmarket Scraper - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"URL: {FILTER_URL}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='de-DE',
            timezone_id='Europe/Berlin'
        )
        
        page = await context.new_page()
        
        try:
            print("🌐 Lade Seite (commit-wait)...")
            # Nutze 'commit' statt 'networkidle' - schneller
            await page.goto(FILTER_URL, wait_until='commit', timeout=30000)
            
            # Warte auf Body
            await page.wait_for_selector('body', timeout=10000)
            await page.wait_for_timeout(5000)  # Warte auf JS
            
            # Prüfe auf Cloudflare Challenge
            content = await page.content()
            if 'cf-browser-verification' in content or 'Just a moment' in content:
                print("⚠️ Cloudflare Challenge erkannt - warte 10s...")
                await page.wait_for_timeout(10000)
                content = await page.content()
            
            if 'cf-browser-verification' in content:
                print("❌ Cloudflare blockt weiterhin")
                await browser.close()
                return 0, None
            
            # Screenshot für Debug
            await page.screenshot(path='/tmp/cardmarket_last.png')
            
            # Parsen mit verschiedenen Selektoren
            listings = []
            
            # Versuche verschiedene Selektoren
            selectors = [
                'table tbody tr',  # Standard Tabelle
                '.article-table tbody tr',
                '[class*="article"]',
                '.row.g-0',
            ]
            
            for selector in selectors:
                rows = await page.query_selector_all(selector)
                print(f"🔍 Selektor '{selector}': {len(rows)} Zeilen")
                
                if len(rows) > 3:
                    for row in rows:
                        try:
                            text = await row.text_content()
                            if not text or '€' not in text:
                                continue
                            
                            # Versuche Seller zu finden
                            seller_match = re.search(r'/Users/([^/\s]+)', text) or re.search(r'([A-Za-z0-9_]{3,20})\s+\d+.*€', text)
                            seller = seller_match.group(1) if seller_match else 'Unknown'
                            
                            # Preis
                            price_match = re.search(r'([\d,]+)\s*€', text)
                            price = float(price_match.group(1).replace(',', '.')) if price_match else 0
                            
                            if seller != 'Unknown' and price > 0:
                                listings.append({
                                    'seller': seller,
                                    'price': price,
                                    'quantity': 1,
                                    'location': 'Germany'
                                })
                        except:
                            continue
                    
                    if len(listings) >= 5:
                        break
            
            print(f"✅ Geparste Listings: {len(listings)}")
            
            # Floor-Price
            floor_price = min([l['price'] for l in listings]) if listings else None
            
            await browser.close()
            
            if listings:
                save_to_db(listings, floor_price)
                return len(listings), floor_price
            else:
                print("❌ Keine Listings gefunden")
                return 0, None
                
        except Exception as e:
            print(f"❌ Fehler: {e}")
            await browser.close()
            raise

def save_to_db(listings, floor_price):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO scrapes (product_id, total_listings, floor_price, filters_applied)
        VALUES (1, ?, ?, 'sellerCountry=7')
    ''', (len(listings), floor_price))
    
    scrape_id = cursor.lastrowid
    
    for listing in listings:
        cursor.execute('''
            INSERT INTO listings (scrape_id, seller, price, quantity, location)
            VALUES (?, ?, ?, ?, ?)
        ''', (scrape_id, listing['seller'], listing['price'], listing['quantity'], listing['location']))
    
    conn.commit()
    conn.close()
    print(f"✅ Gespeichert: Scrape #{scrape_id}, {len(listings)} Listings, Floor: {floor_price:.2f}€" if floor_price else f"✅ Gespeichert: {len(listings)} Listings")

if __name__ == '__main__':
    count, floor = asyncio.run(scrape_cardmarket())
    print(f"\n{'✅' if count > 0 else '❌'} Complete: {count} Listings")
