#!/usr/bin/env python3
"""
collection_alerts.py — Compare latest snapshot vs previous, alert on significant moves.

Alert-Logik (default):
- DROP:  cm_price ≤ -5% UND ≥1€ Differenz UND aktueller Preis ≥3€
- SPIKE: cm_price ≥ +5% UND ≥1€ Differenz UND aktueller Preis ≥3€
- Foil wird separat geprüft mit gleichem Schema
- Alerts werden dedupliziert: gleiche (card_id, alert_type, price) wird in 24h nicht erneut gesendet

Run via cron every 6h, direkt nach collection_sync.py.
"""

import os
import sqlite3
import sys
import json
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent
DB_PATH = REPO / 'cardmarket.db'
ENV_FILE = REPO / '.env'

# Thresholds
DROP_PCT = -0.05
SPIKE_PCT = 0.05
MIN_DIFF_EUR = 1.0
MIN_PRICE_EUR = 3.0
DEDUP_HOURS = 24


def load_env():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith('#') or '=' not in s:
            continue
        k, v = s.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def telegram_send(msg):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat:
        print(f"⚠️ Telegram missing — would send:\n{msg}")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        'chat_id': chat, 'text': msg, 'parse_mode': 'HTML',
        'disable_web_page_preview': 'true',
    }).encode()
    try:
        req = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode()).get('ok', False)
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


def get_collected_cards(conn):
    """Returns list of (card_id, has_standard, has_foil)."""
    cur = conn.cursor()
    cur.execute("SELECT card_id, standard_count, foil_count FROM user_collection")
    return [(r[0], r[1] > 0, r[2] > 0) for r in cur.fetchall()]


def get_two_latest_prices(conn, card_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT cm_price, cm_foil_price, scraped_at, card_name, set_name, rarity
        FROM card_prices WHERE card_id = ?
        ORDER BY scraped_at DESC LIMIT 2
    """, (card_id,))
    return cur.fetchall()


def alert_already_sent(conn, card_id, alert_type, hours=DEDUP_HOURS):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT 1 FROM card_alerts_sent
        WHERE card_id = ? AND alert_type = ?
          AND sent_at > datetime('now', '-{hours} hours')
        LIMIT 1
    """, (card_id, alert_type))
    return cur.fetchone() is not None


def record_alert(conn, card_id, alert_type, price):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO card_alerts_sent (card_id, alert_type, price_at_alert) VALUES (?, ?, ?)",
        (card_id, alert_type, price),
    )
    conn.commit()


def evaluate_card(conn, card_id, has_standard, has_foil):
    """Returns list of alert dicts for this card."""
    rows = get_two_latest_prices(conn, card_id)
    if len(rows) < 2:
        return []
    cur_price, cur_foil, _, name, set_name, rarity = rows[0]
    prev_price, prev_foil, *_ = rows[1]

    alerts = []
    cm_url = f"https://www.cardmarket.com/en/Riftbound/Cards/{(name or '').replace(' ', '-')}"

    def check(kind, cur, prev, label):
        if cur is None or prev is None or prev == 0:
            return
        if cur < MIN_PRICE_EUR:
            return
        diff = cur - prev
        pct = diff / prev
        if abs(diff) < MIN_DIFF_EUR:
            return
        if pct <= DROP_PCT:
            atype = f"{kind}-drop"
            if not alert_already_sent(conn, card_id, atype):
                alerts.append({'kind': atype, 'label': label, 'cur': cur, 'prev': prev, 'pct': pct, 'diff': diff,
                               'name': name, 'set': set_name, 'rarity': rarity, 'url': cm_url})
        elif pct >= SPIKE_PCT:
            atype = f"{kind}-spike"
            if not alert_already_sent(conn, card_id, atype):
                alerts.append({'kind': atype, 'label': label, 'cur': cur, 'prev': prev, 'pct': pct, 'diff': diff,
                               'name': name, 'set': set_name, 'rarity': rarity, 'url': cm_url})

    if has_standard:
        check('std', cur_price, prev_price, 'Standard')
    if has_foil:
        check('foil', cur_foil, prev_foil, 'Foil')

    return alerts


def format_alert(a):
    arrow = '📉' if 'drop' in a['kind'] else '📈'
    sign = '+' if a['diff'] > 0 else ''
    return (
        f"{arrow} <b>{a['name']}</b> <i>({a['set']}, {a['rarity']})</i>\n"
        f"   {a['label']}: <b>{a['cur']:.2f}€</b> "
        f"({sign}{a['diff']:.2f}€ / {sign}{a['pct']*100:.1f}% vs. vorher {a['prev']:.2f}€)\n"
        f"   <a href=\"{a['url']}\">→ Cardmarket</a>"
    )


def main():
    load_env()
    conn = sqlite3.connect(DB_PATH)
    try:
        cards = get_collected_cards(conn)
        evaluated = []  # list of (card_id, alert_dict)
        for card_id, has_std, has_foil in cards:
            for a in evaluate_card(conn, card_id, has_std, has_foil):
                evaluated.append((card_id, a))

        if not evaluated:
            print("🟢 Keine Alerts.")
            return 0

        drops = [(c, a) for c, a in evaluated if 'drop' in a['kind']]
        spikes = [(c, a) for c, a in evaluated if 'spike' in a['kind']]
        drops.sort(key=lambda x: x[1]['pct'])
        spikes.sort(key=lambda x: -x[1]['pct'])

        lines = ['🚨 <b>SAMMLUNGS-ALERTS (Cardmarket EU/DE)</b>', '']
        if drops:
            lines.append(f'<b>📉 Preisrückgänge ({len(drops)})</b>')
            for _, a in drops[:8]:
                lines.append(format_alert(a)); lines.append('')
        if spikes:
            lines.append(f'<b>📈 Preissprünge ({len(spikes)})</b>')
            for _, a in spikes[:8]:
                lines.append(format_alert(a)); lines.append('')
        if len(evaluated) > 16:
            lines.append(f'<i>… +{len(evaluated)-16} weitere übersprungen</i>')

        msg = '\n'.join(lines).strip()
        if telegram_send(msg):
            print(f"✅ Alert sent: {len(evaluated)} items")
            for cid, a in evaluated:
                record_alert(conn, cid, a['kind'], a['cur'])
        else:
            print(f"⚠️ Telegram failed; alerts not recorded")
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
