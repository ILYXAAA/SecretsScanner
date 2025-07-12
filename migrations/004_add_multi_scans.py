"""
Add multi_scans table
Creates table for tracking multi-scan operations
"""

def upgrade(migration_system):
    """Create multi_scans table"""
    
    # Создаем таблицу multi_scans если её нет
    if not migration_system.table_exists("multi_scans"):
        with migration_system.engine.connect() as conn:
            from sqlalchemy import text
            if "postgresql" in migration_system.database_url:
                conn.execute(text("""
                    CREATE TABLE multi_scans (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        scan_ids TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        name TEXT
                    )
                """))
            else:
                # SQLite
                conn.execute(text("""
                    CREATE TABLE multi_scans (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        scan_ids TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        name TEXT
                    )
                """))
            conn.commit()
            print("Created multi_scans table")
    
    # Создаем индекс
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_multi_scans_user ON multi_scans (user_id)",
        "idx_multi_scans_user"
    )

def downgrade(migration_system):
    """Drop multi_scans table"""
    
    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        try:
            conn.execute(text("DROP INDEX IF EXISTS idx_multi_scans_user"))
            conn.execute(text("DROP TABLE IF EXISTS multi_scans"))
            conn.commit()
            print("Dropped multi_scans table and index")
        except Exception as e:
            print(f"Could not drop multi_scans table: {e}")