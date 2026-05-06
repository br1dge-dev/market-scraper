#!/usr/bin/env python3
"""
collection_sync.py — Pull DotGG user collection + current card prices, store snapshot in DB.

- Fetches user_collection from DotGG (auth)
- Fetches all riftbound cards (no auth) → Cardmarket prices (cmPrice, cmFoilPrice)
- Upserts user_collection table (current state)
- Inserts price snapshot rows for ALL collected cards into card_prices

Run via cron every 6h.
"""

import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent
DB_PATH = REPO / 'cardmarket.db'
ENV_FILE = REPO / '.env'

CARDS_URL = 'https://api.dotgg.gg/cgfw/getcards?game=riftbound'
USERDATA_URL = 'https://api.dotgg.gg/cgfw/getuserdata?game=riftbound'


def load_env():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith('#') or '=' not in s:
            continue
        k, v = s.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def http_get(url, headers=None, timeout=20):
    h = headers or {}
    h.setdefault('User-Agent', 'DotGG/2.0 (Mobile; iOS)')
    h.setdefault('Accept', 'application/json')
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ''
        print(f"⚠️ HTTP {e.code} for {url}: {body[:300]}")
        raise


def fetch_user_collection():
    user_id = os.getenv('DOTGG_USER_ID')
    token = os.getenv('DOTGG_TOKEN')
    if not user_id or not token:
        print("❌ DOTGG_USER_ID / DOTGG_TOKEN missing — run dotgg_login.py first")
        sys.exit(2)
    headers = {
        'Dotgguserauth': f"{user_id}:{token}",
        'Accept': 'application/json',
    }
    data = http_get(USERDATA_URL, headers=headers)
    return data.get('collection', [])


def fetch_cards_index():
    """Returns dict[card_id] = card_meta with cmPrice / cmFoilPrice / etc."""
    cards = http_get(CARDS_URL)
    return {c['id']: c for c in cards}


def upsert_collection(conn, items):
    cur = conn.cursor()
    cur.execute("DELETE FROM user_collection")
    rows = []
    for it in items:
        try:
            std = int(it.get('standard') or 0)
            foil = int(it.get('foil') or 0)
            trade = int(it.get('trade') or 0)
            wish = int(it.get('wish') or 0)
        except (ValueError, TypeError):
            continue
        if std + foil + trade + wish == 0:
            continue
        rows.append((it['card'], std, foil, trade, wish))
    cur.executemany(
        "INSERT INTO user_collection (card_id, standard_count, foil_count, trade_count, wish_count) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def snapshot_prices(conn, collection_ids, cards_index):
    cur = conn.cursor()
    rows = []
    missing = []
    for cid in collection_ids:
        c = cards_index.get(cid)
        if not c:
            missing.append(cid); continue
        cm = c.get('cmPrice')
        cmf = c.get('cmFoilPrice')
        if cm is None and cmf is None:
            continue  # no Cardmarket data
        rows.append((
            cid,
            c.get('name'),
            c.get('set_name'),
            c.get('rarity'),
            float(cm) if cm else None,
            float(cmf) if cmf else None,
            float(c.get('cmDelta7dPrice') or 0) or None,
            float(c.get('cmDelta7dPriceFoil') or 0) or None,
        ))
    cur.executemany(
        "INSERT INTO card_prices (card_id, card_name, set_name, rarity, cm_price, cm_foil_price, cm_delta_7d, cm_delta_7d_foil) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows), len(missing)


def main():
    load_env()
    print("📥 Fetching collection from DotGG …")
    items = fetch_user_collection()
    print(f"   → {len(items)} collection entries")

    print("📥 Fetching card catalog (1000+ cards) …")
    cards_index = fetch_cards_index()
    print(f"   → {len(cards_index)} cards in index")

    conn = sqlite3.connect(DB_PATH)
    try:
        n_coll = upsert_collection(conn, items)
        collection_ids = [it['card'] for it in items if int(it.get('standard') or 0) + int(it.get('foil') or 0) > 0]
        n_prices, n_missing = snapshot_prices(conn, collection_ids, cards_index)
    finally:
        conn.close()

    print(f"✅ Collection: {n_coll} cards stored")
    print(f"✅ Prices: {n_prices} snapshot rows (missing CM data: {n_missing})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
