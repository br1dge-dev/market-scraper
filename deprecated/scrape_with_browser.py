#!/usr/bin/env python3
"""
Cardmarket Scraper - Nutzt OpenClaw Browser direkt (profile=openclaw)
Keine Extensions, kein Gefummel - reiner Browser unter unserer Kontrolle.
"""

import sqlite3
import json
import re
import sys
from datetime import datetime

DB_PATH = "/Users/robert/.openclaw/workspace/cardmarket.db"
URL = "https://www.cardmarket.com/en/Riftbound/Products/Box-Sets/Arcane-Box-Set?sellerCountry=7"

def save_to_db(listings, floor_price):
    """Speichert Daten in SQLite"""
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
    return scrape_id

def check_suspected_sales():
    """Prüft auf fehlende Seller"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM scrapes ORDER BY id DESC LIMIT 2')
    scrapes = cursor.fetchall()
    
    if len(scrapes) < 2:
        conn.close()
        return []
    
    current_id = scrapes[0][0]
    prev_id = scrapes[1][0]
    
    # Fehlende Seller aus Q1
    cursor.execute('''
        WITH prev_prices AS (
            SELECT seller, price,
                   NTILE(4) OVER (ORDER BY price) as quartile
            FROM listings WHERE scrape_id = ?
        ),
        current_sellers AS (
            SELECT DISTINCT seller FROM listings WHERE scrape_id = ?
        )
        SELECT p.seller, p.price 
        FROM prev_prices p
        LEFT JOIN current_sellers c ON p.seller = c.seller
        WHERE c.seller IS NULL AND p.quartile = 1
    ''', (prev_id, current_id))
    
    sales = cursor.fetchall()
    
    for seller, price in sales:
        cursor.execute('''
            INSERT OR IGNORE INTO suspected_sales (product_id, detected_at, seller, price, confidence, reasoning)
            VALUES (1, datetime('now'), ?, ?, 'medium', 'Seller not in current scrape, was in Q1 price range')
        ''', (seller, price))
    
    conn.commit()
    conn.close()
    return sales

def parse_snapshot_data(snapshot_text):
    """Parst Listing-Daten aus Browser-Snapshot"""
    listings = []
    lines = snapshot_text.split('\n')
    
    for line in lines:
        # Suche nach Mustern wie "SellerName €XXX,XX Quantity"
        match = re.search(r'([A-Za-z0-9_]+).*?(\d+[.,]\d{2})\s*€', line)
        if match:
            seller = match.group(1)
            price_str = match.group(2).replace(',', '.')
            try:
                price = float(price_str)
                if price > 50:  # Sanity check
                    listings.append({
                        'seller': seller,
                        'price': price,
                        'quantity': 1,
                        'location': 'Germany'
                    })
            except:
                pass
    
    return listings

if __name__ == '__main__':
    print("🦀 Cardmarket Browser Scraper")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"🌐 URL: {URL}")
    print("")
    print("⚠️  Dieses Script wird vom Cronjob-Agenten aufgerufen.")
    print("   Der Agent verwendet das 'browser' Tool mit profile=openclaw.")
