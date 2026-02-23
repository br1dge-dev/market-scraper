#!/bin/bash
# =====================================================
# CARDMARKET DAILY REPORT - KORRIGIERT
# Tägliche Zusammenfassung der Arcane Box Set Daten
# =====================================================

DB_PATH="/Users/christian/+CODING/Hobby/openclaw/workspace/cardmarket.db"
REPORT_DATE=$(date '+%Y-%m-%d')
REPORT_TIME=$(date '+%H:%M')

echo "📊 CARDMARKET DAILY REPORT — Arcane Box Set"
echo "============================================"
echo "Datum: $REPORT_DATE $REPORT_TIME"
echo ""

# 1. Heutige Marktdaten (letzter Scrape)
echo "🏪 MARKTÜBERSICHT (Letzter Stand)"
echo "-------------------------"
sqlite3 "$DB_PATH" "
SELECT 
    'Aktuelle deutsche Listings: ' || total_listings,
    'Floor Price: ' || ROUND(floor_price, 2) || ' €',
    'Price Trend: ' || ROUND(price_trend, 2) || ' €',
    '30-Tage Ø: ' || ROUND(avg_30d, 2) || ' €'
FROM scrapes 
WHERE product_id = 1 
ORDER BY scraped_at DESC 
LIMIT 1;
"
echo ""

# 2. Floor Price Entwicklung (letzte 24h/alle heutigen Scrapes)
echo "📈 FLOOR PRICE ENTWICKLUNG (Heute)"
echo "--------------------------------"
sqlite3 "$DB_PATH" "
SELECT 
    strftime('%H:%M', scraped_at) as zeit,
    ROUND(floor_price, 2) || ' €' as floor,
    total_listings as deutsche_listings
FROM scrapes 
WHERE product_id = 1 
AND date(scraped_at) = date('now', 'localtime')
ORDER BY scraped_at;
"
echo ""

# 3. Verkaufs-Schätzung (heute)
echo "🛒 VERKAUFS-SCHÄTZUNG (Heute)"
echo "-----------------------------"
sqlite3 "$DB_PATH" "
SELECT 
    COUNT(*) || ' Verkäufe geschätzt' as summary,
    'Ø ' || ROUND(AVG(price), 2) || ' €' as durchschnitt
FROM suspected_sales 
WHERE product_id = 1
AND date(detected_at) = date('now', 'localtime');
"
echo ""

# 4. Fehlende Seller (seit letztem Scrape)
echo "🔴 FEHLENDE SELLER (Verkaufsverdacht)"
echo "------------------------------------"
sqlite3 "$DB_PATH" "
WITH current_scrape AS (
    SELECT MAX(id) as id FROM scrapes WHERE product_id = 1
),
previous_scrape AS (
    SELECT MAX(id) as id FROM scrapes 
    WHERE product_id = 1 
    AND id < (SELECT id FROM current_scrape)
),
current_sellers AS (
    SELECT DISTINCT seller, price, quantity 
    FROM listings 
    WHERE scrape_id = (SELECT id FROM current_scrape)
),
previous_sellers AS (
    SELECT DISTINCT seller, price, quantity 
    FROM listings 
    WHERE scrape_id = (SELECT id FROM previous_scrape)
)
SELECT 
    s.seller,
    'zuletzt: ' || s.price || ' € (' || s.quantity || 'x)' as info,
    CASE 
        WHEN s.price < 200 THEN '🔥🔥🔥 Hoher Verdacht (Q1)'
        WHEN s.price < 250 THEN '🔥🔥 Mittlerer Verdacht'
        ELSE '🔥 Niedriger Verdacht'
    END as prioritaet
FROM previous_sellers s
WHERE s.seller NOT IN (SELECT seller FROM current_sellers)
ORDER BY s.price ASC
LIMIT 10;
"
echo ""

# 5. Top 5 günstigste Angebote
echo "🏆 TOP 5 GÜNSTIGSTE ANGEBOTE"
echo "----------------------------"
sqlite3 "$DB_PATH" "
SELECT 
    seller || ': ' || ROUND(price, 2) || ' € (' || quantity || 'x)'
FROM listings l
JOIN scrapes s ON l.scrape_id = s.id
WHERE s.product_id = 1
AND s.id = (SELECT MAX(id) FROM scrapes WHERE product_id = 1)
ORDER BY price ASC
LIMIT 5;
"
echo ""

# 6. Neue Seller (seit letztem Scrape)
echo "✨ NEUE SELLER (seit letztem Scrape)"
echo "------------------------------------"
sqlite3 "$DB_PATH" "
WITH current_scrape AS (
    SELECT MAX(id) as id FROM scrapes WHERE product_id = 1
),
previous_scrape AS (
    SELECT MAX(id) as id FROM scrapes 
    WHERE product_id = 1 
    AND id < (SELECT id FROM current_scrape)
),
current_sellers AS (
    SELECT DISTINCT seller, price, quantity 
    FROM listings 
    WHERE scrape_id = (SELECT id FROM current_scrape)
),
previous_sellers AS (
    SELECT DISTINCT seller
    FROM listings 
    WHERE scrape_id = (SELECT id FROM previous_scrape)
)
SELECT 
    s.seller,
    s.price || ' € (' || s.quantity || 'x)' as angebot
FROM current_sellers s
WHERE s.seller NOT IN (SELECT seller FROM previous_sellers)
ORDER BY s.price ASC
LIMIT 5;
"
echo ""

echo "============================================"
echo "Report Ende — Nächster Scrape: stündlich"
