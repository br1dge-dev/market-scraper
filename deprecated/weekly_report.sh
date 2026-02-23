#!/bin/bash
# =====================================================
# CARDMARKET WEEKLY INTELLIGENCE REPORT - KORRIGIERT
# Wöchentliche Marktanalyse für Arcane Box Set
# =====================================================

DB_PATH="/Users/christian/+CODING/Hobby/openclaw/workspace/cardmarket.db"
WEEK=$(date '+%Y-W%W')

echo "📈 WEEKLY INTELLIGENCE — Arcane Box Set"
echo "=========================================="
echo "Woche: $WEEK"
echo ""

# 1. Wochen-Zusammenfassung
echo "📊 WOCHENÜBERSICHT"
echo "------------------"
sqlite3 "$DB_PATH" "
SELECT 
    COUNT(*) as scrapes_diese_woche,
    MIN(ROUND(floor_price, 2)) || ' €' as wochen_tief,
    MAX(ROUND(floor_price, 2)) || ' €' as wochen_hoch,
    ROUND(AVG(floor_price), 2) || ' €' as durchschnitt_floor,
    MIN(total_listings) || ' - ' || MAX(total_listings) as listing_range
FROM scrapes 
WHERE product_id = 1 
AND scraped_at >= datetime('now', '-7 days', 'localtime');
"
echo ""

# 2. Verkaufs-Schätzung (7 Tage)
echo "🛒 GESCHÄTZTE VERKÄUFE (7 Tage)"
echo "--------------------------------"
sqlite3 "$DB_PATH" "
SELECT 
    date(detected_at) as datum,
    COUNT(*) as anzahl,
    ROUND(AVG(price), 2) || ' €' as durchschnittspreis,
    MIN(price) || ' €' as guenstigster,
    MAX(price) || ' €' as teuerster
FROM suspected_sales 
WHERE product_id = 1 
AND detected_at >= datetime('now', '-7 days', 'localtime')
GROUP BY date(detected_at)
ORDER BY datum;
"
echo ""

# 3. Preis-Trend der Woche
echo "📉 PREIS-TREND (Letzte 7 Tage)"
echo "-----------------------------"
sqlite3 "$DB_PATH" "
WITH daily AS (
    SELECT 
        date(scraped_at) as tag,
        MIN(floor_price) as tages_tief
    FROM scrapes 
    WHERE product_id = 1 
    AND scraped_at >= datetime('now', '-7 days', 'localtime')
    GROUP BY date(scraped_at)
),
mittrends AS (
    SELECT 
        tag,
        tages_tief,
        LAG(tages_tief) OVER (ORDER BY tag) as vortag,
        CASE 
            WHEN tages_tief < LAG(tages_tief) OVER (ORDER BY tag) THEN '📉'
            WHEN tages_tief > LAG(tages_tief) OVER (ORDER BY tag) THEN '📈'
            ELSE '➡️'
        END as trend
    FROM daily
)
SELECT 
    tag || ': ' || ROUND(tages_tief, 2) || '€ ' || trend
FROM mittrends
ORDER BY tag;
"
echo ""

# 4. Seller-Retention (Top 10 aktivste)
echo "👤 SELLER-ANALYSE (Top 10 nach Aktivität)"
echo "-----------------------------------------"
sqlite3 "$DB_PATH" "
SELECT 
    seller,
    COUNT(DISTINCT scrape_id) as gesehen_x_mal,
    MIN(price) || '€' as guenstigst,
    MAX(price) || '€' as teuerst,
    ROUND(AVG(price), 0) || '€' as durchschnitt
FROM listings l
JOIN scrapes s ON l.scrape_id = s.id
WHERE s.product_id = 1
AND s.scraped_at >= datetime('now', '-7 days', 'localtime')
GROUP BY seller
ORDER BY gesehen_x_mal DESC, AVG(price) ASC
LIMIT 10;
"
echo ""

# 5. Preis-Druck Analyse
echo "⚡ PREIS-DRUCK (Seller-Preisänderungen)"
echo "---------------------------------------"
sqlite3 "$DB_PATH" "
WITH aenderungen AS (
    SELECT 
        l.seller,
        l.price as aktuell,
        LAG(l.price) OVER (PARTITION BY l.seller ORDER BY s.scraped_at) as vorher
    FROM listings l
    JOIN scrapes s ON l.scrape_id = s.id
    WHERE s.product_id = 1
    AND s.scraped_at >= datetime('now', '-7 days', 'localtime')
)
SELECT 
    'Preissenkungen: ' || COUNT(CASE WHEN aktuell < vorher THEN 1 END) ||
    ' | Erhöhungen: ' || COUNT(CASE WHEN aktuell > vorher THEN 1 END) ||
    ' | Stabil: ' || COUNT(CASE WHEN aktuell = vorher THEN 1 END) as statistik
FROM aenderungen
WHERE vorher IS NOT NULL;
"
echo ""

# 6. Empfehlung
echo "💡 WOCHEN-EMPFEHLUNG"
echo "--------------------"
sqlite3 "$DB_PATH" "
WITH wochenvergleich AS (
    SELECT 
        AVG(CASE WHEN scraped_at >= datetime('now', '-3 days', 'localtime') 
            THEN floor_price END) as letzte_3_tage,
        AVG(CASE WHEN scraped_at < datetime('now', '-3 days', 'localtime') 
            AND scraped_at >= datetime('now', '-7 days', 'localtime') 
            THEN floor_price END) as tage_4_bis_7
    FROM scrapes
    WHERE product_id = 1
    AND scraped_at >= datetime('now', '-7 days', 'localtime')
)
SELECT 
    CASE 
        WHEN letzte_3_tage < tage_4_bis_7 * 0.95 
            THEN '⏰ WARTEN: Preis sinkt (' || ROUND(letzte_3_tage, 0) || '€ vs ' || 
                 ROUND(tage_4_bis_7, 0) || '€)'
        WHEN letzte_3_tage > tage_4_bis_7 * 1.05 
            THEN '⚠️ KAUFEN: Preis steigt (' || ROUND(letzte_3_tage, 0) || '€ vs ' || 
                 ROUND(tage_4_bis_7, 0) || '€)'
        ELSE '➡️ STABIL: Preis konsolidiert bei ~' || ROUND(letzte_3_tage, 0) || '€'
    END as empfehlung
FROM wochenvergleich;
"
echo ""

echo "=========================================="
echo "Weekly Report Ende — Nächster: nächste Woche Sonntag"
