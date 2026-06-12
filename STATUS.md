# Cardmarket Tracker — Status

**Letzte Aktualisierung:** 12.06.2026

> Single Source of Truth für den Cardmarket Tracker. Robert's MEMORY.md verweist hierher — keine Duplikation.

## Status

✅ **Operational** seit 16.02.2026
**Repo:** `github:br1dge-dev/market-scraper`
**DB:** `cardmarket.db` (SQLite, lokal)
**Telegram:** Riftbound Rippers (`-5223953277`) via Bot Token in `.env`

## Tracked Products

| ID | Slug | Name | Kategorie | Aktueller Floor |
|----|------|------|-----------|-----------------|
| 1 | `arcane` | Arcane Box Set | Box Sets | 178,88€ (12.06.) |
| 2 | `origins` | Origins Booster Box | Booster Boxes | 168,00€ (12.06.) |
| 3 | `spiritforged` | Spiritforged Booster Box | Booster Boxes | 132,99€ (12.06.) |
| 4 | `dazzling-aurora` | Dazzling Aurora | **Singles** | 25,00€ (12.06.) |
| 5 | `unleashed` | Unleashed Booster Box | Booster Boxes | 114,00€ (12.06.) |
| 6 | `worlds-bundle` | Worlds Bundle 2025 | Box Sets | 197,90€ (12.06.) |
| 7 | `proving-grounds` | Proving Grounds | Box Sets | 75,00€ (12.06.) |

> Aurora ist eine **Single Card**, kein Booster-Produkt. Nur als Vergleichswert relevant.
> Floor-Werte updaten sich automatisch — für Live-Daten siehe Daily Reports auf Telegram.

## Sammlung-Tracking (DotGG → Cardmarket-Alerts)

**Datenquelle:** DotGG API (`api.dotgg.gg/cgfw/getuserdata` + `/cgfw/getcards`)
**Auth:** `DOTGG_USER_ID` + `DOTGG_TOKEN` in `.env` (one-time login via `dotgg_login.py`)

### Scripts

| Script | Zweck |
|--------|-------|
| `dotgg_login.py` | Einmalig: Login → schreibt Token in `.env` (chmod 600) |
| `collection_sync.py` | Pullt Sammlung + aktuelle Cardmarket-Preise → DB-Snapshot |
| `collection_alerts.py` | Vergleicht zwei letzte Snapshots → Alert bei ≥5% ± ≥1€ ± Min 3€ |

### Tabellen

- `user_collection` (current state, 1 Zeile pro Karte)
- `card_prices` (Snapshot pro Sync-Lauf, append-only, **nur DotGG-Singles**)
- `card_alerts_sent` (Dedup, 24h Cooldown pro card_id+alert_type)

> **Wichtig:** `card_prices` ist **NICHT** für Booster-Box-Floors. Floor-Historie der Produkte liegt in `scrapes` (1 Zeile pro Scrape). Für aggregierte Reports wird direkt auf `scrapes` aggregiert — keine separate View nötig.

### Alert-Schwellen (Defaults)

| Param | Wert |
|-------|------|
| Drop / Spike | ≥5% Veränderung |
| Min absolut | ≥1€ Differenz |
| Min Kartenwert | ≥3€ (Rauschen-Filter) |
| Foil-Tracking | separat, gleiche Schwellen |
| Dedup | 24h Cooldown |

Tuning: Konstanten oben in `collection_alerts.py`.

## Scheduling (macOS launchd, kein LLM)

**Migration abgeschlossen:** crontab → launchd (12.05. → 27.05.2026). Begründung: `crontab <file>` hängt auf macOS (TCC/Lock-Probleme). launchd ist nativ, stabil, sudo-frei. **Neue Jobs gehen direkt zu launchd.**

**Scraper (stündlich, versetzt, alle launchd):**

| Minute | Produkt | Plist | Seit |
|--------|---------|-------|------|
| :07 | proving-grounds | `com.br1dge.cardmarket.proving-grounds.plist` | 27.05.2026 |
| :12 | dazzling-aurora | `com.br1dge.cardmarket.scraper-dazzling-aurora.plist` | 22.05.2026 |
| :17 | worlds-bundle | `com.br1dge.cardmarket.worlds-bundle.plist` | 12.05.2026 |
| :27 | origins | `com.br1dge.cardmarket.scraper-origins.plist` | 22.05.2026 |
| :42 | spiritforged | `com.br1dge.cardmarket.scraper-spiritforged.plist` | 22.05.2026 |
| :57 | arcane | `com.br1dge.cardmarket.scraper-arcane.plist` | 22.05.2026 |
| :02 | unleashed | `com.br1dge.cardmarket.scraper-unleashed.plist` | 22.05.2026 |

**Reports + Alerts (alle launchd):**

| Schedule | Was | Plist |
|----------|-----|-------|
| 08:00 + 18:00 | Daily Report v2 | `com.br1dge.cardmarket.daily-report.plist` |
| So 21:00 | Weekly Report | `com.br1dge.cardmarket.weekly-report.plist` |
| 08:30 + 18:30 | Price Alerts | `com.br1dge.cardmarket.price-alerts.plist` |
| 0,3,6,9,12,15,18,21 Uhr | Watchdog | `com.br1dge.cardmarket.watchdog.plist` |
| 03:00 | DB Backup | `com.br1dge.cardmarket.backup.plist` |

**Collection (DotGG):**

| Schedule | Was | Plist |
|----------|-----|-------|
| 09:00 + 21:00 | Collection Sync | `com.br1dge.cardmarket.collection-sync.plist` |
| 09:30 + 21:30 | Collection Alerts | `com.br1dge.cardmarket.collection-alerts.plist` |

**Logs:** alle unter `/tmp/cardmarket-*.log` (kein `logs/`-Verzeichnis im Repo).

**Status-Check:**
```bash
launchctl list | grep br1dge.cardmarket
```

## Architektur-Prinzipien

1. **Kein LLM nötig** — pure Python + SQLite + Telegram Bot API
2. **Crontab ODER Sub-Agent, nie beides** (Doppelläufe vermieden) — jetzt komplett launchd
3. **Scraper-Crons:** silent, keine Notifications
4. **Report/Alert-Crons:** announce → Telegram
5. **`.env` ist NICHT in Git** — Secrets bleiben lokal
6. **Single Source of Truth:** `products.py` definiert Produkte, alle Scripts importieren von dort
7. **Schreibrechte:** Scraper laufen via `/usr/bin/python3` (System-Python, nicht venv) — keine Venv-Komplexität

## Neues Produkt hinzufügen

1. `products.py` → `PRODUCTS` dict erweitern (id, slug, name, category, emoji, url)
2. `scraper.py` → `PRODUCTS` dict erweitern (id, name, url, filter, required_location)
3. DB seed: `INSERT INTO products (id, name, category, game, url_path) VALUES (...)`
4. **Scheduling: launchd** (nicht mehr crontab):
   - Plist erstellen in `~/Library/LaunchAgents/com.br1dge.cardmarket.<slug>.plist` (siehe worlds-bundle als Vorlage)
   - `launchctl load <plist>` zum Aktivieren
5. Test-Run: `cd ~/Projects/cardmarket-tracker && python3 scraper.py <slug>`
6. Diese STATUS.md updaten

## Datenquellen & Aggregationen

| Frage | Query |
|-------|-------|
| Aktueller Floor pro Produkt | `SELECT product_id, floor_price FROM scrapes WHERE id IN (SELECT MAX(id) FROM scrapes GROUP BY product_id)` |
| Floor-Trend 7d | `SELECT date(scraped_at), AVG(floor_price) FROM scrapes WHERE scraped_at >= date('now', '-7 days') GROUP BY date(scraped_at)` |
| Verdächtige Verkäufe | `suspected_sales`-Tabelle (vom Scraper befüllt) |
| Schnäppchen-Alerts | `card_alerts_sent` (DotGG-Sammlung) |

→ Keine Views nötig — `scrapes` ist die kanonische Floor-Historie.

## Backups

**Skript:** `backup_db.py` via launchd (03:00)
**Ziel:** `~/Projects/cardmarket-tracker/backups/cardmarket-YYYY-MM-DD.db`
**Retention:** aktuell keine automatische — manuelle Aufbewahrung. Backups älter als 30 Tage können bedenkenlos gelöscht werden (`rm backups/cardmarket-YYYY-MM-DD.db`).
**Lücken möglich:** Backup läuft nur wenn Mac wach ist (Sleep = kein Scrape, kein Backup).

## Learnings

1. Lazy-Loading essentiell — ohne Scrollen nur ~30% der Listings
2. Zeitversetzte Cronjobs (12-15min Abstand) verhindern Überlastung
3. Playwright > Requests — Cardmarket blockt HTTP
4. Cronjobs ODER Sub-Agent, nie beides
5. Scraper-Crons: silent. Report-Crons: announce
6. Single Cards (z.B. Aurora) gehören als separate Kategorie ausgewiesen — sonst verwirren sie Floor-Vergleiche
7. **launchd > crontab auf macOS** (TCC-Probleme, Permission-Blocks)
8. **Seller-Blocklist** schützt vor Ausreißern (WHITEBEARD23, Kaiju-Cards) — bei neuen Bad-Data-Sellern erweitern
9. **Floor-Korrektur rückwirkend:** `UPDATE scrapes SET floor_price = (SELECT MIN(price) FROM listings WHERE scrape_id = scrapes.id) WHERE product_id = ? AND floor_price = ?`

## Sicherheits-Incident (21.02.2026)

`cardscanner` Repo (public, NICHT dieses) hatte kein `.gitignore` — Workspace-Dateien kurzzeitig auf GitHub. Telegram Bot Token + DotGG Auth Token rotiert. Details: `~/.openclaw/workspace-robert/SECURITY.md`.

## TODOs

→ Siehe `~/.openclaw/workspace-robert/TODO-cardmarket.md` (falls vorhanden) oder GitHub Issues im Repo.
