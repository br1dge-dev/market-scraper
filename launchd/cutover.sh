#!/bin/bash
# cutover.sh — Final crontab → launchd Migration
#
# Macht in einem Schritt:
#   1. Backup der aktuellen crontab
#   2. Sudo-Kill der zombie crontab-Prozesse (falls vorhanden)
#   3. Filter: cardmarket-Einträge raus, Rest (z.B. Garmin) bleibt
#   4. launchctl bootstrap für alle Cardmarket-Plists
#   5. Verify
#
# Braucht sudo (für killall crontab).
#
# Usage: ./cutover.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_FILE="/tmp/crontab-pre-cutover-$(date +%Y%m%d-%H%M%S).txt"

echo "🦞 Cardmarket Cutover: crontab → launchd"
echo "========================================="
echo ""

# === Step 1: Backup ===
echo "📦 1/5 Backup aktuelle crontab..."
if crontab -l > "$BACKUP_FILE" 2>/dev/null; then
    echo "    Saved: $BACKUP_FILE ($(wc -l < "$BACKUP_FILE") Zeilen)"
else
    echo "    (keine crontab vorhanden)"
    touch "$BACKUP_FILE"
fi
echo ""

# === Step 2: Kill zombies ===
echo "💀 2/5 Kille zombie crontab-Prozesse..."
ZOMBIES=$(pgrep -f "^/usr/bin/crontab\|^crontab " 2>/dev/null | wc -l | tr -d ' ')
if [ "$ZOMBIES" -gt 0 ]; then
    echo "    Gefunden: $ZOMBIES zombie(s) — kille mit sudo (Passwort nötig)"
    sudo killall crontab 2>/dev/null || true
    sleep 1
    REMAINING=$(pgrep -f "^/usr/bin/crontab\|^crontab " 2>/dev/null | wc -l | tr -d ' ')
    if [ "$REMAINING" -gt 0 ]; then
        echo "    ⚠️  $REMAINING Prozess(e) übrig — versuche -9"
        sudo killall -9 crontab 2>/dev/null || true
    fi
    echo "    ✅ Zombies weg"
else
    echo "    Keine Zombies"
fi
echo ""

# === Step 3: Filter crontab ===
echo "✂️  3/5 Filter crontab (cardmarket-Einträge raus)..."
TMP_CRONTAB=$(mktemp)
trap "rm -f $TMP_CRONTAB" EXIT

# Whitelist: nur Zeilen behalten die zu Nicht-Cardmarket-Jobs gehören.
# Aktuell: Garmin/Coach. Wenn weitere externe Jobs hinzukommen,
# Pattern hier erweitern.
KEEP_PATTERN="workspace-coach|garmin_sync|Little Gino"

grep -E "$KEEP_PATTERN" "$BACKUP_FILE" > "$TMP_CRONTAB" || true

REMOVED=$(($(wc -l < "$BACKUP_FILE") - $(wc -l < "$TMP_CRONTAB")))
KEPT=$(wc -l < "$TMP_CRONTAB" | tr -d ' ')
echo "    $REMOVED Zeile(n) entfernt, $KEPT behalten"
if [ "$KEPT" -gt 0 ]; then
    echo "    Behaltene Zeilen:"
    sed 's/^/      /' "$TMP_CRONTAB"
fi

if crontab "$TMP_CRONTAB"; then
    echo "    ✅ Neue crontab aktiv"
else
    echo "    ❌ crontab-Update fehlgeschlagen — Rollback möglich mit:"
    echo "       crontab $BACKUP_FILE"
    exit 1
fi
echo ""

# === Step 4: Bootstrap launchd ===
echo "🚀 4/5 Lade alle launchd-Jobs..."
"$SCRIPT_DIR/install.sh" --all
echo ""

# === Step 5: Verify ===
echo "🔍 5/5 Verify..."
echo ""
echo "Crontab-Einträge (sollte ohne cardmarket sein):"
crontab -l 2>/dev/null | grep -E "^[^#]" | head -20 || echo "  (leer)"
echo ""
echo "launchd Cardmarket Jobs:"
launchctl list | grep cardmarket || echo "  ❌ keine geladen!"
echo ""

echo "✅ Cutover abgeschlossen."
echo ""
echo "Backup der alten crontab: $BACKUP_FILE"
echo "Rollback (falls nötig):    crontab $BACKUP_FILE && ./install.sh --remove"
