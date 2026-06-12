#!/usr/bin/env python3
"""Scrape Cardmarket floor prices for missing Origins cards."""

import json
import re
import time
import sys
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

INPUT_FILE = "/Users/robert/Projects/cardmarket-tracker/missing_cards.json"
OUTPUT_FILE = "/Users/robert/Projects/cardmarket-tracker/missing_prices.json"

# Load cards
with open(INPUT_FILE) as f:
    cards = json.load(f)

# Load existing progress if any
results = []
if __import__('os').path.exists(OUTPUT_FILE):
    try:
        with open(OUTPUT_FILE) as f:
            results = json.load(f)
    except Exception:
        results = []

# Track which cards are already done
done_ids = {r["id"] for r in results}
remaining = [c for c in cards if c["id"] not in done_ids]

def slugify(name):
    """Convert card name to URL slug."""
    s = name.lower()
    # Remove apostrophes and other special chars except hyphens
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    # Replace spaces with hyphens
    s = re.sub(r"\s+", "-", s)
    # Remove multiple hyphens
    s = re.sub(r"-+", "-", s)
    return s.strip("-")

def build_url(card):
    """Build Cardmarket URL for a card."""
    if card.get("cmurl"):
        base = card["cmurl"]
    else:
        slug = slugify(card["name"])
        base = f"https://www.cardmarket.com/en/Riftbound/Products/Singles/Origins/{slug}"
    # Append filters
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}sellerCountry=7&language=1"

def detect_block(page):
    """Detect if we've been blocked."""
    title = page.title().lower()
    content = page.content().lower()
    block_indicators = [
        "access denied",
        "cloudflare",
        "captcha",
        "ddos protection",
        "blocked",
        "security check",
    ]
    for indicator in block_indicators:
        if indicator in title or indicator in content:
            return True
    return False

def extract_price(page):
    """Extract cheapest listing price from the page."""
    # Try multiple selectors for the price table
    selectors = [
        # First data row in the offers table
        "table.table tbody tr",
        "[data-testid='offers-table'] tbody tr",
        ".table-responsive tbody tr",
        ".offers-table tbody tr",
    ]
    
    for selector in selectors:
        rows = page.query_selector_all(selector)
        for row in rows:
            # Skip header rows
            cells = row.query_selector_all("td")
            if len(cells) >= 3:
                # Look for price cell - usually contains € or a number with comma/dot
                for cell in cells:
                    text = cell.inner_text().strip()
                    # Match prices like "1,23 €" or "12.34 €" or just "1,23"
                    if re.search(r"\d+[,.]\d+", text) and ("€" in text or "," in text):
                        # Clean and return
                        price = text.replace("€", "").strip().replace(",", ".")
                        try:
                            float(price)
                            return text  # Return raw text
                        except ValueError:
                            continue
    
    # Fallback: search entire page for price patterns near "from" or "starting at"
    page_text = page.inner_text()
    # Look for patterns like "from 1,23 €" in the page
    matches = re.findall(r"(\d+[,.]\d+)\s*€", page_text)
    if matches:
        return matches[0] + " €"
    
    return None

print(f"Starting scrape: {len(remaining)}/{len(cards)} cards remaining")
print(f"Started at: {datetime.now().isoformat()}")

blocked = False

with sync_playwright() as p:
    # Launch with stealth-like settings
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ]
    )
    
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="de-DE",
        timezone_id="Europe/Berlin",
    )
    
    # Remove webdriver property
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)
    
    page = context.new_page()
    
    for idx, card in enumerate(remaining):
        card_id = card["id"]
        url = build_url(card)
        
        print(f"\n[{idx+1}/{len(remaining)}] {card_id} - {card['name']}")
        print(f"    URL: {url}")
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # Wait a bit for JS to render
            page.wait_for_timeout(2000)
            
            # Check for block
            if detect_block(page):
                print(f"    ⚠️  IP BLOCK DETECTED! Stopping immediately.")
                blocked = True
                break
            
            # Extract price
            price = extract_price(page)
            
            if price:
                print(f"    ✓ Price found: {price}")
            else:
                print(f"    ⚠ No price found on page")
            
            result = {
                "id": card_id,
                "name": card["name"],
                "rarity": card["rarity"],
                "url": url,
                "price_found": price,
                "previous_price": card.get("cmPrice"),
                "scraped_at": datetime.now().isoformat(),
                "status": "ok" if price else "no_price",
            }
            
        except PlaywrightTimeout:
            print(f"    ✗ Timeout loading page")
            result = {
                "id": card_id,
                "name": card["name"],
                "rarity": card["rarity"],
                "url": url,
                "price_found": None,
                "previous_price": card.get("cmPrice"),
                "scraped_at": datetime.now().isoformat(),
                "status": "timeout",
            }
        except Exception as e:
            print(f"    ✗ Error: {e}")
            result = {
                "id": card_id,
                "name": card["name"],
                "rarity": card["rarity"],
                "url": url,
                "price_found": None,
                "previous_price": card.get("cmPrice"),
                "scraped_at": datetime.now().isoformat(),
                "status": f"error: {str(e)[:100]}",
            }
        
        # Save progress after each card
        results.append(result)
        with open(OUTPUT_FILE, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Wait EXACTLY 10 seconds between cards (unless we're done or blocked)
        if not blocked and idx < len(remaining) - 1:
            time.sleep(10)
    
    browser.close()

# Calculate summary
successful = [r for r in results if r["status"] == "ok" and r["price_found"]]
total_cost = 0.0
for r in successful:
    # Parse price - handle both comma and dot
    price_str = r["price_found"].replace("€", "").strip().replace(",", ".")
    try:
        total_cost += float(price_str)
    except ValueError:
        pass

print(f"\n{'='*60}")
print(f"SCRAPING SUMMARY")
print(f"{'='*60}")
print(f"Total cards: {len(cards)}")
print(f"Successfully scraped: {len(successful)}")
print(f"Failed/timeout: {len(results) - len(successful)}")
print(f"Blocked: {'YES - STOPPED EARLY' if blocked else 'No'}")
print(f"Total floor cost: {total_cost:.2f} €")
print(f"Finished at: {datetime.now().isoformat()}")

# Print all results
print(f"\n{'='*60}")
print("RESULTS:")
for r in results:
    status_icon = "✓" if r["status"] == "ok" else "✗"
    print(f"  {status_icon} {r['id']} ({r['name']}): {r.get('price_found', 'N/A')} (was: {r.get('previous_price', 'N/A')})")
