# launchd Setup

macOS-natives Scheduling für den Cardmarket Tracker. Ersetzt langfristig `crontab`.

## Warum launchd statt crontab?

- `crontab <file>` hängt auf macOS regelmäßig (TCC-Permission-Dialoge, Lock-Issues)
- launchd ist macOS-nativ, stabil, Apple-empfohlen
- Plists sind versionierbar im Git-Repo
- `launchctl bootstrap` läuft ohne sudo (User-scoped LaunchAgents)
- Auto-restart bei Crash, integriertes Logging
- Hot-reload via `install.sh` ohne Lock-Probleme

## Quickstart

```bash
# Alle Plists installieren
./install.sh

# Nur einen Job
./install.sh worlds-bundle

# Alle entfernen
./install.sh --remove

# Status
launchctl list | grep cardmarket

# Manuell triggern (Test)
launchctl kickstart -k gui/$(id -u)/com.br1dge.cardmarket.worlds-bundle

# Logs
tail -f /tmp/cardmarket-worlds-bundle.log
```

## Konventionen

- **Label-Prefix:** `com.br1dge.cardmarket.<slug>`
- **Plist-Name:** identisch zum Label
- **Logs:** `/tmp/cardmarket-<slug>.log` (stdout + stderr)
- **Working dir:** `/Users/robert/Projects/cardmarket-tracker`
- **Python:** `/usr/bin/python3` (system, hat playwright via User-site-packages)

## Status Migration

| Job | crontab | launchd |
|-----|---------|---------|
| unleashed (:02) | ✅ aktiv | — |
| dazzling-aurora (:12) | ✅ aktiv | — |
| **worlds-bundle (:17)** | — | **✅ aktiv** |
| origins (:27) | ✅ aktiv | — |
| spiritforged (:42) | ✅ aktiv | — |
| arcane (:57) | ✅ aktiv | — |
| daily_report_v2 (8/18) | ✅ aktiv | — |
| weekly_report_v2 (So 21) | ✅ aktiv | — |
| price_alerts (8:30/18:30) | ✅ aktiv | — |
| watchdog (alle 3h) | ✅ aktiv | — |
| backup_db (3:00) | ✅ aktiv | — |
| collection_sync/alerts | ✅ aktiv | — |

**Plan:** Sukzessive Migration aller Jobs auf launchd, dann crontab leeren (braucht sudo nach Reboot).

## Plist-Template

Siehe `com.br1dge.cardmarket.worlds-bundle.plist` als Vorlage.

Pflichtfelder:
- `Label` — eindeutig
- `ProgramArguments` — `[python3, script.py, args...]`
- `WorkingDirectory` — Projektpfad
- `StartCalendarInterval` — Cron-Äquivalent (Minute/Hour/Weekday/Day)
- `StandardOutPath` + `StandardErrorPath` — Log-Datei
- `EnvironmentVariables` — mindestens `PATH` + `HOME`

## Troubleshooting

**Job läuft nicht zum geplanten Zeitpunkt:**
```bash
launchctl print gui/$(id -u)/com.br1dge.cardmarket.worlds-bundle
# State sollte "waiting" sein
```

**Manueller Test:**
```bash
launchctl kickstart -k gui/$(id -u)/com.br1dge.cardmarket.worlds-bundle
tail -f /tmp/cardmarket-worlds-bundle.log
```

**Plist-Syntax prüfen:**
```bash
plutil -lint com.br1dge.cardmarket.worlds-bundle.plist
```

**Reload nach Plist-Änderung:**
```bash
./install.sh worlds-bundle  # bootout + bootstrap, idempotent
```
