"""
Add language and framework data to scans table
Adds columns for storing detected languages and frameworks from microservice
"""

def upgrade(migration_system):
    """Add language and framework data columns to scans table"""
    
    # Add detected_languages column
    migration_system.safe_add_column("scans", "detected_languages TEXT DEFAULT '{}'")
    
    # Add detected_frameworks column  
    migration_system.safe_add_column("scans", "detected_frameworks TEXT DEFAULT '{}'")
    
    print("Added detected_languages and detected_frameworks columns to scans table")

def downgrade(migration_system):
    """Remove language and framework data columns from scans table"""
    
    # SQLite не поддерживает DROP COLUMN, поэтому пропускаем для SQLite
    if "sqlite" in migration_system.database_url:
        print("SQLite does not support DROP COLUMN, skipping column removal")
        return
    
    columns_to_drop = [
        ("scans", "detected_languages"),
        ("scans", "detected_frameworks")
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