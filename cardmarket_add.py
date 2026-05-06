#!/usr/bin/env python3
"""
cardmarket_add.py — Add a new product to the tracker in one shot.

Usage:
    python3 cardmarket_add.py <cardmarket-url> [--slug SLUG] [--category booster-box|box-set|single] [--emoji X] [--no-scrape]

What it does:
    1. Parses the Cardmarket URL → derives name + category
    2. Inserts into products.py PRODUCTS dict (next available id)
    3. Inserts into SQLite products table
    4. Inserts into scraper.py PRODUCTS dict (so the scraper knows it)
    5. Adds a crontab line at the next free :MM slot
    6. Triggers an initial test scrape (unless --no-scrape)
    7. Posts a confirmation summary

Idempotent: if URL/slug already tracked, exits cleanly.
"""

import argparse
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from products import PRODUCTS, by_slug  # noqa: E402

DB_PATH = REPO / 'cardmarket.db'
PRODUCTS_PY = REPO / 'products.py'
SCRAPER_PY = REPO / 'scraper.py'

# Slot-Reihenfolge je 5 Minuten (verteilt über die Stunde)
PREFERRED_MINUTES = [2, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57, 7]


def derive_from_url(url):
    """Erkennt Kategorie + Name aus Cardmarket-URL."""
    url = url.strip().rstrip('/')
    # Beispiele:
    #   /en/Riftbound/Products/Booster-Boxes/Unleashed-Booster-Box
    #   /en/Riftbound/Products/Singles/Origins/Dazzling-Aurora
    #   /en/Riftbound/Products/Box-Sets/Arcane-Box-Set
    m = re.search(r'/Products/([^/]+)/(.+)$', url)
    if not m:
        raise ValueError(f"Cannot parse Cardmarket URL: {url}")
    cat_raw = m.group(1)
    tail = m.group(2)
    last = tail.split('/')[-1]

    cat_map = {
        'Booster-Boxes': 'booster-box',
        'Box-Sets': 'box-set',
        'Singles': 'single',
    }
    category = cat_map.get(cat_raw, 'booster-box')

    name = last.replace('-', ' ')
    short = name
    # Bei BBs: "Unleashed Booster Box" → kurz "Unleashed"
    if category == 'booster-box':
        short = re.sub(r'\s*Booster Box$', '', name)
    elif category == 'box-set':
        short = re.sub(r'\s*Box Set$', '', name) + ' Box Set'

    slug = re.sub(r'[^a-z0-9]+', '-', last.lower()).strip('-')
    if category == 'booster-box':
        slug = re.sub(r'-booster-box$', '', slug) or slug
    return {
        'slug': slug,
        'name': name,
        'short_name': short,
        'category': category,
        'url': url if url.startswith('http') else 'https://www.cardmarket.com' + url,
    }


def next_product_id():
    return max(PRODUCTS.keys()) + 1 if PRODUCTS else 1


def find_free_minute():
    used = set()
    try:
        out = subprocess.check_output(['crontab', '-l'], text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        out = ''
    for line in out.splitlines():
        m = re.match(r'^\s*(\d+)\s+\*\s+\*\s+\*\s+\*\s+.*scraper\.py', line)
        if m:
            used.add(int(m.group(1)))
    for slot in PREFERRED_MINUTES:
        if slot not in used:
            return slot
    return None


def patch_products_py(new_id, info, emoji):
    src = PRODUCTS_PY.read_text()
    block = f"""    {new_id}: {{
        'slug': '{info['slug']}',
        'name': '{info['name']}',
        'short_name': '{info['short_name']}',
        'category': '{info['category']}',
        'emoji': '{emoji}',
        'url': '{info['url']}',
    }},
}}"""
    if "PRODUCTS = {" not in src:
        raise RuntimeError("products.py shape changed unexpectedly")
    new_src = re.sub(r'(\}\s*,\s*\n)\}\n', r'\1' + block.split('}', 1)[0] + '},\n}\n', src, count=1)
    if new_src == src:
        # Fallback: brute insert before final '}'
        idx = src.rfind('}')
        new_src = src[:idx] + block.split('}', 1)[0] + '},\n}\n'
    PRODUCTS_PY.write_text(new_src)


def patch_scraper_py(new_id, info):
    src = SCRAPER_PY.read_text()
    block = f"""    '{info['slug']}': {{
        'id': {new_id},
        'name': '{info['name']}',
        'url': '{info['url']}',
        'filter': 'sellerCountry=7&language=1',
        'required_location': 'Germany',
    }},
}}"""
    new_src = re.sub(r'(\},\s*\n)\}\s*\n', r'\1' + block.split('}', 1)[0] + '},\n}\n', src, count=1)
    if new_src == src:
        idx = src.find('}\n\n\nasync def')
        if idx == -1:
            raise RuntimeError("scraper.py shape changed; insert manually")
        # find PRODUCTS dict's last '}' before idx
        sub = src[:idx]
        last_close = sub.rfind('}')
        new_src = sub[:last_close] + block.split('}', 1)[0] + '},\n}' + src[idx:]
    SCRAPER_PY.write_text(new_src)


def db_insert(new_id, info):
    conn = sqlite3.connect(DB_PATH)
    try:
        url_path = info['url'].split('cardmarket.com', 1)[-1]
        conn.execute(
            "INSERT OR IGNORE INTO products (id, name, category, game, url_path) VALUES (?, ?, ?, ?, ?)",
            (new_id, info['name'], info['category'], 'Riftbound', url_path),
        )
        conn.commit()
    finally:
        conn.close()


def add_crontab_line(slug, minute):
    line = f"{minute} * * * * cd $SKILL_DIR && /usr/bin/python3 scraper.py {slug} >> /tmp/cardmarket-{slug}.log 2>&1"
    out = subprocess.check_output(['crontab', '-l'], text=True, stderr=subprocess.DEVNULL)
    if line in out:
        return False
    new_crontab = out.rstrip() + '\n' + line + '\n'
    p = subprocess.run(['crontab', '-'], input=new_crontab, text=True)
    return p.returncode == 0


def emoji_for_category(cat):
    return {'booster-box': '📦', 'box-set': '🎁', 'single': '🃏'}.get(cat, '⭐')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('url', help='Cardmarket URL (full or path)')
    ap.add_argument('--slug', help='Override auto-derived slug')
    ap.add_argument('--category', choices=['booster-box', 'box-set', 'single'])
    ap.add_argument('--emoji', help='Override emoji')
    ap.add_argument('--no-scrape', action='store_true', help='Skip initial test scrape')
    args = ap.parse_args()

    info = derive_from_url(args.url)
    if args.slug:
        info['slug'] = args.slug
    if args.category:
        info['category'] = args.category
    emoji = args.emoji or emoji_for_category(info['category'])

    pid_existing, _ = by_slug(info['slug'])
    if pid_existing:
        print(f"⚠️  Slug '{info['slug']}' already tracked (id={pid_existing}). Nothing to do.")
        return 0

    new_id = next_product_id()
    print(f"➕ Adding {info['name']} (id={new_id}, slug='{info['slug']}', cat={info['category']})")

    patch_products_py(new_id, info, emoji)
    patch_scraper_py(new_id, info)
    db_insert(new_id, info)

    minute = find_free_minute()
    if minute is None:
        print("⚠️  No free :MM slot in PREFERRED_MINUTES — add cron line manually.")
    else:
        if add_crontab_line(info['slug'], minute):
            print(f"⏰ Crontab: :{minute:02d} * * * * → scraper.py {info['slug']}")

    if not args.no_scrape:
        print("🚀 Test-Scrape …")
        env = os.environ.copy()
        env['SKILL_DIR'] = str(REPO)
        rc = subprocess.run(['/usr/bin/python3', str(SCRAPER_PY), info['slug']], env=env, cwd=REPO).returncode
        if rc != 0:
            print(f"⚠️  Test-Scrape exit {rc} — check scraper.py / network.")

    print(f"✅ Done. {info['short_name']} ist auf der Beobachtungsliste.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
