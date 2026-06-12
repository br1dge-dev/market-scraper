"""
products.py — Zentraler Produktkatalog für den Cardmarket Tracker.

Single Source of Truth für ID, Name, Slug, Kategorie, Emoji, URL.
Reports + Alerts + Watchdog importieren von hier.
"""

PRODUCTS = {
    1: {
        'slug': 'arcane',
        'name': 'Arcane Box Set',
        'short_name': 'Arcane Box Set',
        'category': 'box-set',  # Sonderfall: weder reine BB noch Single
        'emoji': '🔮',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Box-Sets/Arcane-Box-Set',
    },
    2: {
        'slug': 'origins',
        'name': 'Origins Booster Box',
        'short_name': 'Origins',
        'category': 'booster-box',
        'emoji': '🦋',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Booster-Boxes/Origins-Booster-Box',
    },
    3: {
        'slug': 'spiritforged',
        'name': 'Spiritforged Booster Box',
        'short_name': 'Spiritforged',
        'category': 'booster-box',
        'emoji': '⚔️',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Booster-Boxes/Spiritforged-Booster-Box',
    },
    4: {
        'slug': 'dazzling-aurora',
        'name': 'Dazzling Aurora',
        'short_name': 'Aurora',
        'category': 'single',
        'emoji': '✨',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Singles/Origins/Dazzling-Aurora',
    },
    5: {
        'slug': 'unleashed',
        'name': 'Unleashed Booster Box',
        'short_name': 'Unleashed',
        'category': 'booster-box',
        'emoji': '⚡',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Booster-Boxes/Unleashed-Booster-Box',
    },
    6: {
        'slug': 'worlds-bundle',
        'name': 'Worlds Bundle 2025',
        'short_name': 'Worlds Bundle',
        'category': 'box-set',
        'emoji': '🏆',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Box-Sets/Worlds-Bundle-2025',
    },
    7: {
        'slug': 'proving-grounds',
        'name': 'Proving Grounds',
        'short_name': 'Proving Grounds',
        'category': 'box-set',
        'emoji': '🎯',
        'url': 'https://www.cardmarket.com/en/Riftbound/Products/Box-Sets/Proving-Grounds',
    },
}


# Kategorien-Reihenfolge für Reports
CATEGORY_ORDER = ['booster-box', 'box-set', 'single']

CATEGORY_LABELS = {
    'booster-box': '📦 Booster Boxes',
    'box-set': '🎁 Box Sets',
    'single': '🃏 Single Cards',
}


def boxes():
    """Alle Produkte die als 'Booster-Markt' zählen (BB + Box Sets, ohne Singles)."""
    return {pid: p for pid, p in PRODUCTS.items() if p['category'] in ('booster-box', 'box-set')}


def singles():
    """Single Cards."""
    return {pid: p for pid, p in PRODUCTS.items() if p['category'] == 'single'}


def by_category():
    """Generator über (category, label, {pid: cfg}) in CATEGORY_ORDER."""
    for cat in CATEGORY_ORDER:
        items = {pid: p for pid, p in PRODUCTS.items() if p['category'] == cat}
        if items:
            yield cat, CATEGORY_LABELS[cat], items


def get(product_id):
    return PRODUCTS.get(product_id)


def by_slug(slug):
    for pid, p in PRODUCTS.items():
        if p['slug'] == slug:
            return pid, p
    return None, None
