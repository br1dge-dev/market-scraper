#!/bin/bash
# install.sh — Cardmarket Tracker launchd Setup
#
# Installiert Plists aus diesem Verzeichnis als User-LaunchAgents.
# Kein sudo nötig (User-scoped via launchctl bootstrap).
#
# Safety: Wenn crontab noch cardmarket-Einträge hat, refuse install
# (würde Doppelläufe verursachen). Override mit --force.
#
# Usage:
#   ./install.sh <name>     # eine Plist installieren (sicher)
#   ./install.sh --all      # alle Plists installieren
#   ./install.sh --remove   # alle Plists entfernen (uninstall)
#   ./install.sh --status   # zeige geladene Jobs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/Library/LaunchAgents"
UID_NUM=$(id -u)
PREFIX="com.br1dge.cardmarket."
FORCE=0

mkdir -p "$TARGET_DIR"

check_crontab_collision() {
    # Returns 0 if collision (cardmarket entries in crontab)
    crontab -l 2>/dev/null | grep -q "cardmarket-tracker"
}

install_one() {
    local src="$1"
    local name="$(basename "$src" .plist)"
    local dst="$TARGET_DIR/$name.plist"

    if ! plutil -lint "$src" > /dev/null; then
        echo "❌ $name: ungültiges Plist" >&2
        return 1
    fi

    # Idempotent reinstall
    if launchctl print "gui/$UID_NUM/$name" > /dev/null 2>&1; then
        launchctl bootout "gui/$UID_NUM/$name" 2>/dev/null || true
    fi

    cp "$src" "$dst"
    launchctl bootstrap "gui/$UID_NUM" "$dst"
    echo "✅ $name installed"
}

remove_one() {
    local name="$1"
    local dst="$TARGET_DIR/$name.plist"

    if launchctl print "gui/$UID_NUM/$name" > /dev/null 2>&1; then
        launchctl bootout "gui/$UID_NUM/$name" 2>/dev/null || true
    fi
    rm -f "$dst"
    echo "🗑️  $name removed"
}

show_status() {
    echo "=== Cardmarket launchd Jobs ==="
    local jobs
    jobs=$(launchctl list 2>/dev/null | grep cardmarket || true)
    if [ -z "$jobs" ]; then
        echo "  (keine geladen)"
    else
        echo "$jobs"
    fi
    echo ""
    echo "=== Crontab Cardmarket-Einträge ==="
    crontab -l 2>/dev/null | grep "cardmarket-tracker" || echo "  (keine — clean)"
}

# Parse args
case "${1:-}" in
    --force)
        FORCE=1
        shift
        ;;
esac

case "${1:-}" in
    --status|-s)
        show_status
        exit 0
        ;;
    --remove|-r)
        for plist in "$TARGET_DIR/${PREFIX}"*.plist; do
            [ -e "$plist" ] || continue
            name=$(basename "$plist" .plist)
            remove_one "$name"
        done
        ;;
    --all|-a)
        if [ "$FORCE" -ne 1 ] && check_crontab_collision; then
            echo "⚠️  STOP: crontab enthält noch cardmarket-Einträge!"
            echo "    Lade ich jetzt alle Plists, gibt es Doppelläufe."
            echo ""
            echo "    Korrekt: ./cutover.sh (clear crontab + bootstrap all)"
            echo "    Override: ./install.sh --force --all"
            exit 2
        fi
        for plist in "$SCRIPT_DIR"/${PREFIX}*.plist; do
            [ -e "$plist" ] || continue
            install_one "$plist"
        done
        ;;
    "")
        echo "Usage: $0 <name> | --all | --remove | --status | --force --all"
        echo ""
        echo "Verfügbare Plists:"
        for plist in "$SCRIPT_DIR"/${PREFIX}*.plist; do
            [ -e "$plist" ] || continue
            name=$(basename "$plist" .plist | sed "s/^${PREFIX}//")
            echo "  • $name"
        done
        exit 1
        ;;
    *)
        # Single job install
        plist="$SCRIPT_DIR/${PREFIX}${1}.plist"
        [ -e "$plist" ] || plist="$SCRIPT_DIR/${1}.plist"
        if [ ! -e "$plist" ]; then
            echo "❌ Plist nicht gefunden: $1" >&2
            exit 1
        fi

        # Safety: warn if this slug is also in crontab
        slug="${1#${PREFIX}}"
        if [ "$FORCE" -ne 1 ] && crontab -l 2>/dev/null | grep -q "scraper.py $slug\|${slug}.py"; then
            echo "⚠️  $slug ist auch in crontab. Doppelläufe!"
            echo "    Erst crontab-Eintrag entfernen, dann hier nochmal."
            echo "    Override: ./install.sh --force $1"
            exit 2
        fi
        install_one "$plist"
        ;;
esac

echo ""
show_status
