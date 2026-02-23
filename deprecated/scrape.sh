#!/bin/bash
# Cardmarket Scraper - Direkter Browser-Ansatz ohne Extension
# Nutzt OpenClaw's isolierten Browser (profile=openclaw)

DB_PATH="${CARDMARKET_DB_PATH:-/Users/robert/.openclaw/workspace/cardmarket.db}"
PRODUCT_URL="${CARDMARKET_PRODUCT_URL:-https://www.cardmarket.com/en/Riftbound/Products/Box-Sets/Arcane-Box-Set}"
FILTER_URL="${PRODUCT_URL}?sellerCountry=7"

echo "🦀 Cardmarket Scraper"
echo "===================="
echo "URL: $FILTER_URL"
echo "DB:  $DB_PATH"
echo ""

# Prüfe DB
if [ ! -f "$DB_PATH" ]; then
    echo "❌ Datenbank nicht gefunden: $DB_PATH"
    exit 1
fi

echo "✅ Datenbank OK"
echo ""
echo "Nächster Schritt: Browser-Automation via OpenClaw"
echo "(Wird vom Cronjob-Agenten ausgeführt)"
