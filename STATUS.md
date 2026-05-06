# Cardmarket Tracker — Status

**Letzte Aktualisierung:** 06.05.2026

> Single Source of Truth für den Cardmarket Tracker. Robert's MEMORY.md verweist hierher — keine Duplikation.

## Status

✅ **Operational** seit 16.02.2026
**Repo:** `github:br1dge-dev/market-scraper`
**DB:** `cardmarket.db` (SQLite, lokal)
**Telegram:** Riftbound Rippers (`-5223953277`) via Bot Token in `.env`

## Tracked Products

| ID | Slug | Name | Kategorie | Letzter Floor |
|----|------|------|-----------|---------------|
| 1 | `arcane` | Arcane Box Set | Box Sets | — |
| 2 | `origins` | Origins Booster Box | Booster Boxes | — |
| 3 | `spiritforged` | Spiritforged Booster Box | Booster Boxes | — |
| 4 | `dazzling-aurora` | Dazzling Aurora | **Singles** | 43€ (06.05.) |
| 5 | `unleashed` | Unleashed Booster Box | Booster Boxes | 136€ (06.05.) |

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
- `card_prices` (Snapshot pro Sync-Lauf, append-only)
- `card_alerts_sent` (Dedup, 24h Cooldown pro card_id+alert_type)

### Alert-Schwellen (Defaults)

| Param | Wert |
|-------|------|
| Drop / Spike | ≥5% Veränderung |
| Min absolut | ≥1€ Differenz |
| Min Kartenwert | ≥3€ (Rauschen-Filter) |
| Foil-Tracking | separat, gleiche Schwellen |
| Dedup | 24h Cooldown |

Tuning: Konstanten oben in `collection_alerts.py`.

## Scheduling (macOS crontab, kein LLM)

```
:02 unleashed
:12 dazzling-aurora
:27 origins
:42 spiritforged
:57 arcane
```

| Schedule | Was |
|----------|-----|
| stündlich (5 Slots) | Scrapes (siehe oben) |
| 08:00 + 18:00 | Daily Report v2 |
| So 21:00 | Weekly Report |
| 08:30 + 18:30 | Price Alerts |
| alle 3h | Watchdog |
| 03:00 | DB Backup |

## Architektur-Prinzipien

1. **Kein LLM nötig** — pure Python + SQLite + Telegram Bot API
2. **Crontab ODER Sub-Agent, nie beides** (Doppelläufe vermieden)
3. **Scraper-Crons:** silent, keine Notifications
4. **Report/Alert-Crons:** announce → Telegram
5. **`.env` ist NICHT in Git** — Secrets bleiben lokal

## Neues Produkt hinzufügen

1. `scraper.py` → `PRODUCTS` dict erweitern (id, name, url, filter)
2. DB seed: `INSERT INTO products (id, name, category, game, url_path) VALUES (...)`
3. `crontab -e` → neuen Slot eintragen
4. Test-Run: `cd ~/Projects/cardmarket-tracker && python3 scraper.py <slug>`
5. Diese STATUS.md updaten

## Learnings

1. Lazy-Loading essentiell — ohne Scrollen nur ~30% der Listings
2. Zeitversetzte Cronjobs (12-15min Abstand) verhindern Überlastung
3. Playwright > Requests — Cardmarket blockt HTTP
4. Cronjobs ODER Sub-Agent, nie beides
5. Scraper-Crons: silent. Report-Crons: announce
6. Single Cards (z.B. Aurora) gehören als separate Kategorie ausgewiesen — sonst verwirren sie Floor-Vergleiche

## Sicherheits-Incident (21.02.2026)

`cardscanner` Repo (public, NICHT dieses) hatte kein `.gitignore` — Workspace-Dateien kurzzeitig auf GitHub. Telegram Bot Token + DotGG Auth Token rotiert. Details: `~/.openclaw/workspace-robert/SECURITY.md`.

## TODOs

→ Siehe `~/.openclaw/workspace-robert/TODO-cardmarket.md` (falls vorhanden) oder GitHub Issues im Repo.
