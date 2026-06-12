#!/usr/bin/env python3
"""
Weekly Average Price Charts für Cardmarket Produkte
Zeigt Durchschnittspreise pro Woche seit Aufzeichnungsbeginn
"""

import sqlite3
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

# Config
DB_PATH = Path(__file__).parent / "cardmarket.db"
OUTPUT_DIR = Path(__file__).parent / "charts"
OUTPUT_DIR.mkdir(exist_ok=True)

# Produkt-Mapping (basierend auf scraper.py args)
PRODUCTS = {
    1: "Arcane Box Set",
    2: "Origins Booster Box", 
    3: "Spiritforged Booster Box"
}


def get_weekly_averages(conn, product_id):
    """Berechnet durchschnittlichen Preis pro Woche aus listings"""
    query = """
    SELECT 
        s.scraped_at,
        AVG(l.price) as avg_price,
        COUNT(l.id) as listing_count
    FROM scrapes s
    JOIN listings l ON l.scrape_id = s.id
    WHERE s.product_id = ?
        AND l.location = 'Germany'
    GROUP BY s.id, s.scraped_at
    ORDER BY s.scraped_at
    """
    
    cursor = conn.execute(query, (product_id,))
    rows = cursor.fetchall()
    
    # Gruppiere nach Kalenderwoche
    weekly_data = defaultdict(lambda: {'prices': [], 'listing_count': 0})
    
    for row in rows:
        scraped_at = datetime.fromisoformat(row[0].replace('Z', '+00:00').replace('+00:00', ''))
        # ISO Kalenderwoche (Montag als Wochenstart)
        year, week, _ = scraped_at.isocalendar()
        week_key = (year, week)
        
        weekly_data[week_key]['prices'].append(row[1])
        weekly_data[week_key]['listing_count'] += row[2]
    
    # Berechne Durchschnitte und sortiere
    result = []
    for (year, week), data in sorted(weekly_data.items()):
        avg_price = sum(data['prices']) / len(data['prices'])
        # Wochenmittwoch als repräsentativer Zeitpunkt
        week_date = datetime.strptime(f'{year}-W{week}-1', '%G-W%V-%u')
        result.append({
            'date': week_date,
            'avg_price': avg_price,
            'listing_count': data['listing_count']
        })
    
    return result


def create_chart(product_id, product_name, weekly_data):
    """Erstellt ein Chart für ein Produkt"""
    if not weekly_data:
        return None
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Daten extrahieren
    dates = [d['date'] for d in weekly_data]
    prices = [d['avg_price'] for d in weekly_data]
    
    # Hauptlinie: Durchschnittspreis
    ax.plot(dates, prices, linewidth=2, color='#2E86AB', marker='o', markersize=4)
    
    # Styling
    ax.set_title(f'{product_name}\nDurchschnittspreis pro Woche (DE-Listings)', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xlabel('Woche', fontsize=11)
    ax.set_ylabel('Ø Preis (€)', fontsize=11)
    
    # Formatierung
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}€'))
    
    # X-Achse: Monate formatieren
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    plt.xticks(rotation=45, ha='right')
    
    # Min/Max markieren
    min_price = min(prices)
    max_price = max(prices)
    min_idx = prices.index(min_price)
    max_idx = prices.index(max_price)
    min_date = dates[min_idx]
    max_date = dates[max_idx]
    
    ax.annotate(f'Min: {min_price:.0f}€', 
                xy=(min_date, min_price),
                xytext=(10, -20), textcoords='offset points',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgreen', alpha=0.7),
                arrowprops=dict(arrowstyle='->', color='green'))
    
    ax.annotate(f'Max: {max_price:.0f}€',
                xy=(max_date, max_price),
                xytext=(10, 20), textcoords='offset points',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightcoral', alpha=0.7),
                arrowprops=dict(arrowstyle='->', color='red'))
    
    # Stats-Box
    avg_price = sum(prices) / len(prices)
    stats_text = f"Datenpunkte: {len(weekly_data)} Wochen\n"
    stats_text += f"Ø: {avg_price:.0f}€ | Min: {min_price:.0f}€ | Max: {max_price:.0f}€"
    
    ax.text(0.02, 0.98, stats_text,
            transform=ax.transAxes, fontsize=9, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    
    # Speichern
    safe_name = product_name.lower().replace(' ', '_').replace('-', '_')
    filename = OUTPUT_DIR / f"weekly_avg_{safe_name}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    
    return filename


def main():
    print("📊 Generiere Weekly Average Charts...\n")
    
    conn = sqlite3.connect(DB_PATH)
    
    created_files = []
    
    for product_id, product_name in PRODUCTS.items():
        print(f"🔄 Verarbeite: {product_name}")
        
        weekly_data = get_weekly_averages(conn, product_id)
        
        if not weekly_data:
            print(f"   ⚠️  Keine Daten für {product_name}")
            continue
        
        print(f"   📈 {len(weekly_data)} Wochen mit Daten")
        
        filepath = create_chart(product_id, product_name, weekly_data)
        if filepath:
            created_files.append(filepath)
            print(f"   ✅ {filepath.name}\n")
    
    conn.close()
    
    print(f"\n🎉 Fertig! {len(created_files)} Charts erstellt in: {OUTPUT_DIR}")
    for f in created_files:
        print(f"   • {f.name}")


if __name__ == "__main__":
    main()
