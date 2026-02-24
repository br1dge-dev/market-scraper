#!/bin/bash
# Cardmarket Tracker Skill - Setup Script
# Dieses Script richtet die Datenbank und Cronjobs ein

set -e

echo "🦀 Cardmarket Tracker Skill Setup"
echo "=================================="

# Prüfe ob sqlite3 installiert ist
if ! command -v sqlite3 &> /dev/null; then
    echo "❌ sqlite3 nicht gefunden. Bitte installieren:"
    echo "   macOS: brew install sqlite3"
    echo "   Linux: sudo apt-get install sqlite3"
    exit 1
fi

# Datenbank erstellen
DB_PATH="${1:-./cardmarket.db}"
echo "📁 Erstelle Datenbank: $DB_PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sqlite3 "$DB_PATH" < "$SCRIPT_DIR/schema.sql"

echo "✅ Datenbank erstellt!"
echo ""
echo "🔧 Nächste Schritte:"
echo "   1. Cronjobs importieren: openclaw skill cardmarket-tracker/setup-cron"
echo "   2. Chrome Extension verbinden"
echo "   3. Ersten Scrape starten: /scrape_cardmarket"
