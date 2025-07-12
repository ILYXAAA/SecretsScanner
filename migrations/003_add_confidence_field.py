"""
Add confidence field to secrets
Adds confidence scoring for detected secrets
"""

def upgrade(migration_system):
    """Add confidence column to secrets table"""
    
    # Добавляем колонку confidence
    if "postgresql" in migration_system.database_url:
        migration_system.safe_add_column("secrets", "confidence REAL DEFAULT 1.0")
    else:
        migration_system.safe_add_column("secrets", "confidence REAL DEFAULT 1.0")
    
    # Обновляем существующие записи
    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        conn.execute(text("UPDATE secrets SET confidence = 1.0 WHERE confidence IS NULL"))
        conn.commit()
        print("Updated existing records with default confidence value")

def downgrade(migration_system):
    """Remove confidence column"""
    
    # SQLite не поддерживает DROP COLUMN
    if "sqlite" in migration_system.database_url:
        print("SQLite does not support DROP COLUMN, skipping confidence column removal")
        return
    
    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        try:
            conn.execute(text("ALTER TABLE secrets DROP COLUMN confidence"))
            conn.commit()
            print("Dropped confidence column from secrets table")
        except Exception as e:
            print(f"Could not drop confidence column: {e}")