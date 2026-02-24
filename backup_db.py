#!/usr/bin/env python3
"""
Cardmarket DB Auto-Backup
- Täglicher Snapshot um 03:00
- Retention: 14 Tage
- Kein LLM, deterministisch
"""

import sqlite3
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / 'cardmarket.db'
BACKUP_DIR = Path(__file__).parent / 'backups'
RETENTION_DAYS = 14


def backup_database():
    """Erstellt tägliches DB-Backup"""
    if not DB_PATH.exists():
        print(f"❌ Datenbank nicht gefunden: {DB_PATH}")
        return 1
    
    # Backup-Ordner erstellen
    BACKUP_DIR.mkdir(exist_ok=True)
    
    # Backup-Name mit Datum
    today = datetime.now().strftime('%Y-%m-%d')
    backup_path = BACKUP_DIR / f'cardmarket-{today}.db'
    
    # Kopieren (SQLite backup ist atomic)
    try:
        shutil.copy2(DB_PATH, backup_path)
        size_mb = backup_path.stat().st_size / (1024 * 1024)
        print(f"✅ Backup erstellt: {backup_path.name} ({size_mb:.1f} MB)")
    except Exception as e:
        print(f"❌ Backup fehlgeschlagen: {e}")
        return 1
    
    # Alte Backups löschen (Retention)
    deleted = cleanup_old_backups()
    
    print(f"🧹 {deleted} alte Backups gelöscht (Retention: {RETENTION_DAYS} Tage)")
    return 0


def cleanup_old_backups():
    """Löscht Backups älter als RETENTION_DAYS"""
    if not BACKUP_DIR.exists():
        return 0
    
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    deleted = 0
    
    for backup_file in BACKUP_DIR.glob('cardmarket-*.db'):
        try:
            # Datum aus Filename extrahieren
            date_str = backup_file.stem.replace('cardmarket-', '')
            backup_date = datetime.strptime(date_str, '%Y-%m-%d')
            
            if backup_date < cutoff:
                backup_file.unlink()
                deleted += 1
                print(f"   🗑️ Gelöscht: {backup_file.name}")
        except ValueError:
            # Ungültiges Datum im Filename - überspringen
            continue
        except Exception as e:
            print(f"   ⚠️ Fehler beim Löschen {backup_file}: {e}")
    
    return deleted


def main():
    print(f"💾 Cardmarket DB Backup - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"📁 Quelle: {DB_PATH}")
    print(f"📁 Ziel: {BACKUP_DIR}")
    print()
    
    return backup_database()


if __name__ == '__main__':
    exit(main())
