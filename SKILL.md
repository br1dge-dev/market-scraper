# Cardmarket Tracker

Vollautomatisches Markt-Tracking für Riftbound-Produkte auf Cardmarket.de

## 📊 Aktiver Betrieb (seit 16.02.2026)

3 Produkte werden stündlich getrackt:

| Produkt | DB-ID | Cron | Zeit |
|---------|-------|------|------|
| **Arcane Box Set** | 1 | `cardmarket-arcane-tracker` | :57 |
| **Origins Booster Box** | 2 | `cardmarket-origins-tracker` | :27 |
| **Spiritforged Booster Box** | 3 | `cardmarket-spiritforged-tracker` | :42 |

### Reports
- **Morning Report:** Täglich 08:00 → Telegram-Gruppe
- **Daily Report:** Täglich 18:00 → Telegram-Gruppe
- **Weekly Report:** Sonntags 21:00 → Telegram-Gruppe
- **Telegram-Gruppe:** `-5223953277` (Riftbound Rippers)

---

## 🏗️ Architektur

```
┌─────────────────────────────────────────────────────┐
│                    CRON JOBS                         │
│  :27 Origins  →  :42 Spiritforged  →  :57 Arcane    │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│           scraper.py <product> (Playwright)          │
│  • Unified Scraper für alle 3 Produkte              │
│  • Chromium mit Anti-Detection                       │
│  • Lazy-Loading (Scroll + "Load More")               │
│  • 45-69 Listings pro Produkt                        │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│              SQLite Datenbank                        │
│  cardmarket.db (workspace root)                      │
│  • products, scrapes, listings                       │
│  • suspected_sales, price_distribution               │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│              Reports (Telegram)                      │
│  • daily_report_v2.py (Sparklines, Trends, Ranking)  │
│  • weekly_report.py (Min/Max/Avg, Volatilität)       │
└─────────────────────────────────────────────────────┘
```

---

## 📁 Dateien

| File | Status | Beschreibung |
|------|--------|--------------|
| `scraper.py` | ✅ **Aktiv** | Unified Scraper: `python3 scraper.py origins\|spiritforged\|arcane` |
| `daily_report_v2.py` | ✅ **Aktiv** | Daily/Morning Report (Sparklines, 24h Range, Ranking) |
| `weekly_report.py` | ✅ **Aktiv** | Weekly Report (Sonntags) |
| `schema.sql` | ✅ Aktiv | DB-Schema |
| `analysis_queries_v2.sql` | ✅ Aktiv | SQL-Analyse-Queries |
| `.env` | 🔒 | TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID |
| `deprecated/` | 📁 | Alte Scraper, Shell-Scripts, Wrapper |

---

## 🔧 Technische Details

### Unified Scraper (`scraper.py`)
```bash
python3 scraper.py origins       # Origins Booster Box (ID 2)
python3 scraper.py spiritforged  # Spiritforged Booster Box (ID 3)
python3 scraper.py arcane        # Arcane Box Set (ID 1)
```

Produkt-Configs sind im Script definiert (URL, DB-ID, Filter, Location).

### Anti-Scraping
- User-Agent Spoofing
- `navigator.webdriver` → undefined
- Viewport 1920x2000, Locale de-DE, TZ Europe/Berlin

### Lazy-Loading
1. Initial Load → "Load More" Button klicken (bis zu 10x)
2. Scrollen bis keine neuen Listings
3. Location-Filter: nur `Germany` für Floor-Berechnung

### Verkaufsverdacht-Logik
Seller aus Q1 (unterstes Quartil) des vorherigen Scrapes, die im aktuellen fehlen → `suspected_sale`

### DB-Schema
```
products       → Produktkatalog (3 Einträge)
scrapes        → Zeitreihe (product_id, floor_price, total_listings)
listings       → Einzelne Listings (seller, price, qty, location)
suspected_sales → Automatisch erkannte Verkäufe
price_distribution → (angelegt, noch nicht befüllt)
```

### Daily Report v2 Features
- Unicode Sparklines (▁▂▃▄▅▆▇█) für 24h Preisverlauf
- 24h High/Low Range
- Listing-Änderungen mit +/- Delta
- Tiefpunkt-Erkennung (beste Kaufzeit)
- Markt-Ranking nach Floor-Preis
- Verkaufsverdacht-Summary

---

## ⏰ Cronjobs

| Name | Schedule | Task |
|------|----------|------|
| `cardmarket-origins-tracker` | every 1h (:27) | `scraper.py origins` |
| `cardmarket-spiritforged-tracker` | every 1h (:42) | `scraper.py spiritforged` |
| `cardmarket-arcane-tracker` | every 1h (:57) | `scraper.py arcane` |
| `cardmarket-morning-report` | 08:00 daily | `daily_report_v2.py` |
| `cardmarket-daily-report` | 18:00 daily | `daily_report_v2.py` |
| `cardmarket-weekly-report` | So 21:00 | `weekly_report.py` |

Alle Cronjobs: Model `moonshot/kimi-k2.5`, Target `isolated`, Delivery via Telegram.

---

## 🚀 Setup / Recovery

```bash
# 1. DB initialisieren
sqlite3 cardmarket.db < skills/cardmarket-tracker/schema.sql

# 2. Produkte einfügen
sqlite3 cardmarket.db "INSERT INTO products VALUES 
  (1,'Arcane Box Set','Box Sets','Riftbound','/en/Riftbound/Products/Box-Sets/Arcane-Box-Set'),
  (2,'Origins Booster Box','Booster Boxes','Riftbound','/en/Riftbound/Products/Booster-Boxes/Origins-Booster-Box'),
  (3,'Spiritforged Booster Box','Booster Boxes','Riftbound','/en/Riftbound/Products/Booster-Boxes/Spiritforged-Booster-Box');"

# 3. Cronjobs via openclaw cron add (Schedules siehe oben)
```

### Backup
Snapshot vom 20.02.2026 in `backups/cardmarket-2026-02-20/` (DB + Skills + MEMORY.md + Cronjob-Config).
Restore-Anleitung: `backups/cardmarket-2026-02-20/RESTORE.md`

---

## 📝 Learnings

1. **Lazy-Loading ist essentiell** – ohne Scrollen nur 30% der Daten
2. **Zeitversatzte Cronjobs** – 15min Abstand verhindert Überlastung
3. **Playwright > Requests** – Cardmarket blockt einfache HTTP-Requests
4. **Seller-Sets rotieren** – Cardmarket zeigt nicht immer alle Seller (Session-basiert)
5. **PRAGMA busy_timeout** – wichtig bei shared SQLite (noch nicht in allen Scripts)

---

**Für:** @br1dge_eth  
**Letzte Aktualisierung:** 20.02.2026
