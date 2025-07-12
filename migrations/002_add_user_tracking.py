"""
Add user tracking fields
Adds columns to track which user performed actions
"""

def upgrade(migration_system):
    """Add user tracking columns"""
    
    # Добавляем колонки для отслеживания пользователей
    migration_system.safe_add_column("scans", "started_by TEXT")
    migration_system.safe_add_column("projects", "created_by TEXT")
    migration_system.safe_add_column("secrets", "confirmed_by TEXT")
    migration_system.safe_add_column("secrets", "refuted_by TEXT")

def downgrade(migration_system):
    """Remove user tracking columns"""
    
    # SQLite не поддерживает DROP COLUMN, поэтому пропускаем для SQLite
    if "sqlite" in migration_system.database_url:
        print("SQLite does not support DROP COLUMN, skipping column removal")
        return
    
    columns_to_drop = [
        ("scans", "started_by"),
        ("projects", "created_by"),
        ("secrets", "confirmed_by"),
        ("secrets", "refuted_by")
    ]
    
    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        for table, column in columns_to_drop:
            try:
                conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
                print(f"Dropped column {column} from {table}")
            except Exception as e:
                print(f"Could not drop column {column} from {table}: {e}")
        conn.commit()