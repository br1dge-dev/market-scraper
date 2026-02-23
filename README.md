# Cardmarket Tracker

Riftbound price tracker for Cardmarket.de — scraper, reports, watchdog.

## Stack

- **Scraper**: Playwright + Chromium (Python)
- **DB**: SQLite (`cardmarket.db`, lokal only)
- **Reports**: Telegram (Bot → Gruppe "Riftbound Rippers")
- **Scheduling**: macOS crontab

## Tracked Products

| Product | Scraper Arg |
|---------|-------------|
| Arcane Box Set | `arcane` |
| Origins Booster Box | `origins` |
| Spiritforged Booster Box | `spiritforged` |

## Scripts

| Script | Was |
|--------|-----|
| `scraper.py <product>` | Scrapet Listings von Cardmarket |
| `daily_report_v2.py` | Täglicher Report mit Sparklines |
| `weekly_report.py` | Wöchentlicher Überblick |
| `watchdog.py` | Alert bei >2h ohne neue Daten |

## Setup

```bash
# Dependencies
pip3 install playwright python-telegram-bot
playwright install chromium

# Env
cp .env.example .env  # Telegram Bot Token + Chat ID eintragen

# DB initialisieren
python3 -c "import sqlite3; conn = sqlite3.connect('cardmarket.db'); conn.executescript(open('schema.sql').read())"
```

## Crontab

```cron
SKILL_DIR=/path/to/cardmarket-tracker

27 * * * * cd $SKILL_DIR && python3 scraper.py origins
42 * * * * cd $SKILL_DIR && python3 scraper.py spiritforged
57 * * * * cd $SKILL_DIR && python3 scraper.py arcane
0 8,18 * * * cd $SKILL_DIR && python3 daily_report_v2.py
0 21 * * 0  cd $SKILL_DIR && python3 weekly_report.py
0 */3 * * * cd $SKILL_DIR && python3 watchdog.py
```

## Structure

```
cardmarket-tracker/
├── scraper.py          # Unified Scraper (Playwright)
├── daily_report_v2.py  # Daily Report
├── weekly_report.py    # Weekly Report
├── watchdog.py         # Watchdog / Alert
├── schema.sql          # DB Schema
├── cardmarket.db       # SQLite DB (gitignored)
├── .env                # Secrets (gitignored)
└── deprecated/         # Alte Einzelscraper
```
