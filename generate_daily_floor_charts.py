#!/usr/bin/env python3
"""
Daily Floor Price Charts für Cardmarket Produkte
Zeigt Floor-Preis pro Tag seit Aufzeichnungsbeginn
"""

import sqlite3
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from pathlib import Path

# Config
DB_PATH = Path(__file__).parent / "cardmarket.db"
OUTPUT_DIR = Path(__file__).parent / "charts"
OUTPUT_DIR.mkdir(exist_ok=True)

# Produkt-Mapping
PRODUCTS = {
    1: "Arcane Box Set",
    2: "Origins Booster Box", 
    3: "Spiritforged Booster Box"
}


def get_daily_floor_prices(conn, product_id):
    """Holt Floor-Preis pro Tag"""
    query = """
    SELECT 
        DATE(scraped_at) as day,
        MIN(floor_price) as floor_price,
        COUNT(*) as scrape_count
    FROM scrapes
    WHERE product_id = ?
        AND floor_price IS NOT NULL
        AND floor_price > 0
    GROUP BY DATE(scraped_at)
    ORDER BY day
    """
    
    cursor = conn.execute(query, (product_id,))
    rows = cursor.fetchall()
    
    result = []
    for row in rows:
        result.append({
            'date': datetime.strptime(row[0], '%Y-%m-%d'),
            'floor_price': row[1],
            'scrapes': row[2]
        })
    
    return result


def create_floor_chart(product_id, product_name, daily_data):
    """Erstellt ein Floor-Price Chart"""
    if not daily_data:
        return None
    
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # Daten extrahieren
    dates = [d['date'] for d in daily_data]
    floors = [d['floor_price'] for d in daily_data]
    
    # Floor-Preis Linie
    ax.plot(dates, floors, linewidth=2, color='#E63946', marker='o', 
            markersize=3, label='Floor Price')
    
    # Area fill für bessere Visualisierung
    ax.fill_between(dates, floors, alpha=0.3, color='#E63946')
    
    # Styling
    ax.set_title(f'{product_name}\nFloor Price (täglich)', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xlabel('Datum', fontsize=11)
    ax.set_ylabel('Floor Price (€)', fontsize=11)
    
    # Grid & Format
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}€'))
    
    # X-Achse: Tage formatieren
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))  # Alle 2 Tage
    plt.xticks(rotation=45, ha='right')
    
    # Min/Max markieren
    min_price = min(floors)
    max_price = max(floors)
    min_idx = floors.index(min_price)
    max_idx = floors.index(max_price)
    
    ax.annotate(f'Min: {min_price:.0f}€', 
                xy=(dates[min_idx], min_price),
                xytext=(10, -25), textcoords='offset points',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgreen', alpha=0.8),
                arrowprops=dict(arrowstyle='->', color='green', lw=1.5),
                fontsize=9)
    
    ax.annotate(f'Max: {max_price:.0f}€',
                xy=(dates[max_idx], max_price),
                xytext=(10, 25), textcoords='offset points',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightcoral', alpha=0.8),
                arrowprops=dict(arrowstyle='->', color='red', lw=1.5),
                fontsize=9)
    
    # Stats-Box
    current = floors[-1]
    change = current - floors[0]
    change_pct = (change / floors[0]) * 100
    trend = "📈" if change > 0 else "📉" if change < 0 else "➡️"
    
    stats_text = f"Datenpunkte: {len(daily_data)} Tage\n"
    stats_text += f"Start: {floors[0]:.0f}€ → Heute: {current:.0f}€\n"
    stats_text += f"{trend} Change: {change:+.0f}€ ({change_pct:+.1f}%)\n"
    stats_text += f"Min: {min_price:.0f}€ | Max: {max_price:.0f}€"
    
    ax.text(0.02, 0.98, stats_text,
            transform=ax.transAxes, fontsize=9, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))
    
    # Legende
    ax.legend(loc='upper right')
    
    plt.tight_layout()
    
    # Speichern
    safe_name = product_name.lower().replace(' ', '_').replace('-', '_')
    filename = OUTPUT_DIR / f"daily_floor_{safe_name}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    
    return filename


def main():
    print("📊 Generiere Daily Floor Price Charts...\n")
    
    conn = sqlite3.connect(DB_PATH)
    
    created_files = []
    
    for product_id, product_name in PRODUCTS.items():
        print(f"🔄 Verarbeite: {product_name}")
        
        daily_data = get_daily_floor_prices(conn, product_id)
        
        if not daily_data:
            print(f"   ⚠️  Keine Daten für {product_name}")
            continue
        
        print(f"   📈 {len(daily_data)} Tage mit Daten")
        print(f"   💶 Current Floor: {daily_data[-1]['floor_price']:.0f}€")
        
        filepath = create_floor_chart(product_id, product_name, daily_data)
        if filepath:
            created_files.append(filepath)
            print(f"   ✅ {filepath.name}\n")
    
    conn.close()
    
    print(f"\n🎉 Fertig! {len(created_files)} Charts erstellt")
    for f in created_files:
        print(f"   • {f}")


if __name__ == "__main__":
    main()
