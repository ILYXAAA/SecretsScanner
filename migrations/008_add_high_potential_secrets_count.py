"""
Add high_secrets_count and potential_secrets_count to scans table
Adds denormalized counters for dashboard performance optimization
"""

def upgrade(migration_system):
    """Add secrets count columns to scans table and populate them"""
    
    # Add new columns
    migration_system.safe_add_column("scans", "high_secrets_count INTEGER DEFAULT 0")
    migration_system.safe_add_column("scans", "potential_secrets_count INTEGER DEFAULT 0")
    
    print("Added high_secrets_count and potential_secrets_count columns to scans table")
    
    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        
        # Обновляем счетчики для всех завершенных сканов
        update_query = text("""
            UPDATE scans 
            SET high_secrets_count = (
                SELECT COUNT(*) 
                FROM secrets 
                WHERE secrets.scan_id = scans.id 
                AND secrets.severity = 'High' 
                AND secrets.is_exception = false
            ),
            potential_secrets_count = (
                SELECT COUNT(*) 
                FROM secrets 
                WHERE secrets.scan_id = scans.id 
                AND secrets.severity = 'Potential' 
                AND secrets.is_exception = false
            )
            WHERE scans.status = 'completed'
        """)
        
        result = conn.execute(update_query)
        conn.commit()
        
        print(f"Updated secrets counters for existing completed scans (affected rows: {result.rowcount})")

def downgrade(migration_system):
    """Remove secrets count columns from scans table"""
    
    # SQLite не поддерживает DROP COLUMN
    if "sqlite" in migration_system.database_url:
        print("SQLite does not support DROP COLUMN, skipping column removal")
        return
    
    columns_to_drop = [
        ("scans", "high_secrets_count"),
        ("scans", "potential_secrets_count")
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