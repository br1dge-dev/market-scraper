-- =====================================================
-- KORRIGIERTE ANALYSIS QUERIES
-- Für Arcane Box Set (Riftbound) Markt-Intelligenz
-- =====================================================

-- 1. TÄGLICHE VERKAUFS-SCHÄTZUNG (korrigiert)
-- Wie viele Sets wurden heute wahrscheinlich verkauft?
SELECT 
    date(detected_at) as date,
    COUNT(*) as suspected_sales,
    ROUND(AVG(price), 2) as avg_sale_price,
    MIN(price) as cheapest_sale,
    MAX(price) as highest_sale
FROM suspected_sales
WHERE confidence IN ('high', 'medium')
GROUP BY date(detected_at)
ORDER BY date DESC;

-- 2. PREIS-TREND ÜBER ZEIT (korrigiert)
-- Entwicklung des Floor Prices
SELECT 
    date(scraped_at) as date,
    COUNT(*) as scrapes_that_day,
    MIN(floor_price) as daily_floor_low,
    MAX(floor_price) as daily_floor_high,
    ROUND(AVG(floor_price), 2) as avg_floor,
    ROUND(AVG(total_listings), 0) as avg_german_listings
FROM scrapes
WHERE product_id = 1
GROUP BY date(scraped_at)
ORDER BY date DESC;

-- 3. KORREKTE VERKAUFS-ANALYSE (vergleicht aufeinanderfolgende Scrapes)
WITH ordered_scrapes AS (
    SELECT 
        id,
        scraped_at,
        floor_price,
        total_listings,
        LAG(id) OVER (ORDER BY scraped_at) as prev_id,
        LAG(floor_price) OVER (ORDER BY scraped_at) as prev_floor
    FROM scrapes
    WHERE product_id = 1
),
sales_analysis AS (
    SELECT 
        s.id,
        s.scraped_at,
        s.floor_price,
        s.prev_floor,
        s.floor_price - s.prev_floor as floor_delta,
        s.total_listings,
        -- Vergleiche Seller-Listen
        (SELECT COUNT(*) FROM listings l WHERE l.scrape_id = s.id) as curr_count,
        (SELECT COUNT(*) FROM listings l WHERE l.scrape_id = s.prev_id) as prev_count
    FROM ordered_scrapes s
)
SELECT 
    scraped_at,
    ROUND(floor_price, 2) as floor,
    ROUND(prev_floor, 2) as prev_floor,
    ROUND(floor_delta, 2) as delta,
    total_listings,
    CASE 
        WHEN floor_delta < -5 THEN '📉 DROP'
        WHEN floor_delta > 5 THEN '📈 RISE'
        ELSE '➡️ STABLE'
    END as trend
FROM sales_analysis
WHERE prev_id IS NOT NULL
ORDER BY scraped_at DESC;

-- 4. Q1 VERKÄUFER (aktuell) - Floor-Nähe = Verkaufswahrscheinlich
WITH current_scrape AS (
    SELECT MAX(id) as id, MIN(price) as floor FROM listings WHERE scrape_id = (SELECT MAX(id) FROM scrapes WHERE product_id = 1)
),
price_range AS (
    SELECT 
        cs.id as scrape_id,
        cs.floor,
        MAX(l.price) as ceiling,
        (MAX(l.price) - cs.floor) as spread
    FROM listings l
    CROSS JOIN current_scrape cs
    WHERE l.scrape_id = cs.id
    GROUP BY cs.id, cs.floor
)
SELECT 
    l.seller,
    l.price,
    l.quantity,
    l.seller_rating,
    CASE 
        WHEN l.price <= pr.floor + (pr.spread * 0.10) THEN '🔥 HOT (Bottom 10%)'
        WHEN l.price <= pr.floor + (pr.spread * 0.20) THEN '⚡ WARM (Bottom 20%)'
        ELSE '📊 NORMAL'
    END as sale_probability
FROM listings l
JOIN price_range pr ON l.scrape_id = pr.scrape_id
WHERE l.scrape_id = (SELECT MAX(id) FROM scrapes WHERE product_id = 1)
ORDER BY l.price ASC
LIMIT 10;

-- 5. FEHLENDE SELLER (Verkaufsverdacht)
WITH current_sellers AS (
    SELECT DISTINCT seller FROM listings 
    WHERE scrape_id = (SELECT MAX(id) FROM scrapes WHERE product_id = 1)
),
previous_sellers AS (
    SELECT DISTINCT seller FROM listings 
    WHERE scrape_id = (SELECT MAX(id) FROM scrapes WHERE product_id = 1 AND id < (SELECT MAX(id) FROM scrapes WHERE product_id = 1))
)
SELECT 
    s.seller,
    (SELECT price FROM listings WHERE seller = s.seller AND scrape_id = (SELECT MAX(id) FROM scrapes WHERE product_id = 1 AND id < (SELECT MAX(id) FROM scrapes WHERE product_id = 1))) as last_price,
    (SELECT quantity FROM listings WHERE seller = s.seller AND scrape_id = (SELECT MAX(id) FROM scrapes WHERE product_id = 1 AND id < (SELECT MAX(id) FROM scrapes WHERE product_id = 1))) as last_quantity,
    '🔴 VERKAUFSVERDACHT' as status
FROM previous_sellers s
WHERE s.seller NOT IN (SELECT seller FROM current_sellers);

-- 6. MARKT-BEWEGUNG (letzte 24h)
WITH latest AS (
    SELECT * FROM scrapes 
    WHERE product_id = 1 
    ORDER BY scraped_at DESC LIMIT 1
),
previous AS (
    SELECT * FROM scrapes 
    WHERE product_id = 1 
    ORDER BY scraped_at DESC LIMIT 1 OFFSET 1
)
SELECT 
    l.scraped_at as current_time,
    p.scraped_at as previous_time,
    ROUND(l.floor_price, 2) as current_floor,
    ROUND(p.floor_price, 2) as previous_floor,
    ROUND(l.floor_price - p.floor_price, 2) as floor_delta,
    l.total_listings - p.total_listings as listings_delta
FROM latest l, previous p;

-- 7. WOCHENTLICHE ZUSAMMENFASSUNG
SELECT 
    strftime('%Y-W%W', scraped_at) as week,
    COUNT(*) as scrape_count,
    MIN(ROUND(floor_price, 2)) as week_low,
    MAX(ROUND(floor_price, 2)) as week_high,
    ROUND(AVG(floor_price), 2) as week_avg_floor,
    MIN(total_listings) as min_listings,
    MAX(total_listings) as max_listings
FROM scrapes
WHERE product_id = 1
GROUP BY week
ORDER BY week DESC;

-- 8. SELLER-VERHALTEN (Top 10 nach Aktivität)
SELECT 
    seller,
    COUNT(DISTINCT scrape_id) as times_seen,
    MIN(price) as lowest_price_ever,
    MAX(price) as highest_price_ever,
    ROUND(AVG(price), 2) as avg_price,
    MAX(scraped_at) as last_seen
FROM listings l
JOIN scrapes s ON l.scrape_id = s.id
WHERE s.product_id = 1
GROUP BY seller
ORDER BY times_seen DESC, last_seen DESC
LIMIT 10;
