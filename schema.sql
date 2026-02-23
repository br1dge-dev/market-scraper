-- Cardmarket Tracker Skill - Database Schema
-- Für SQLite3

-- Produkte (optional für Multi-Produkt-Tracking)
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    game TEXT,
    url_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Scrapes (Zeitstempel + Marktdaten)
CREATE TABLE IF NOT EXISTS scrapes (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_listings INTEGER,
    floor_price REAL,
    price_trend REAL,
    avg_30d REAL,
    avg_7d REAL,
    avg_1d REAL,
    filters_applied TEXT
);

-- Einzelne Listings
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY,
    scrape_id INTEGER,
    seller TEXT NOT NULL,
    seller_rating INTEGER,
    seller_type TEXT,
    price REAL NOT NULL,
    quantity INTEGER,
    location TEXT,
    language TEXT,
    condition_notes TEXT,
    FOREIGN KEY (scrape_id) REFERENCES scrapes(id)
);

-- Verkaufsverdacht
CREATE TABLE IF NOT EXISTS suspected_sales (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    detected_at TIMESTAMP,
    seller TEXT,
    price REAL,
    confidence TEXT,
    reasoning TEXT
);

-- Preisverteilung (für Analysen)
CREATE TABLE IF NOT EXISTS price_distribution (
    id INTEGER PRIMARY KEY,
    scrape_id INTEGER,
    range_label TEXT,
    min_price REAL,
    max_price REAL,
    listing_count INTEGER,
    avg_price REAL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_listings_scrape ON listings(scrape_id);
CREATE INDEX IF NOT EXISTS idx_listings_seller ON listings(seller);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price);
CREATE INDEX IF NOT EXISTS idx_scrapes_product_time ON scrapes(product_id, scraped_at);
CREATE INDEX IF NOT EXISTS idx_sales_product ON suspected_sales(product_id, detected_at);

-- Standard-Produkt einfügen
INSERT OR IGNORE INTO products (id, name, category, game, url_path) 
VALUES (1, 'Arcane Box Set', 'Box Sets', 'Riftbound', '/en/Riftbound/Products/Box-Sets/Arcane-Box-Set');
