"""
Add maintenance mode settings table
Adds settings table with maintenance_mode flag for service maintenance control
"""

def upgrade(migration_system):
    """Add settings table with maintenance_mode"""
    
    # Create settings table
    create_settings_table = """
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY,
        key VARCHAR(255) NOT NULL UNIQUE,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_by VARCHAR(255)
    )
    """
    
    migration_system.safe_create_table(create_settings_table, "settings")
    print("Created settings table")
    
    # Insert default maintenance_mode = false
    # Support both SQLite and PostgreSQL
    engine_name = migration_system.engine.dialect.name
    
    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        
        try:
            if engine_name == 'sqlite':
                conn.execute(text("""
                    INSERT OR IGNORE INTO settings (key, value, updated_by) 
                    VALUES ('maintenance_mode', 'false', 'system')
                """))
            elif engine_name == 'postgresql':
                conn.execute(text("""
                    INSERT INTO settings (key, value, updated_by) 
                    VALUES ('maintenance_mode', 'false', 'system')
                    ON CONFLICT (key) DO NOTHING
                """))
            else:
                # For other databases, try with try/except
                conn.execute(text("""
                    INSERT INTO settings (key, value, updated_by) 
                    VALUES ('maintenance_mode', 'false', 'system')
                """))
            
            conn.commit()
            print("Inserted default maintenance_mode setting")
        except Exception as e:
            print(f"Warning: Could not insert default setting: {e}")
            conn.rollback()
    
    # Create index
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_settings_key ON settings (key)",
        "idx_settings_key"
    )
    print("Created index for settings table")
    print("Settings table created successfully")

def downgrade(migration_system):
    """Remove settings table"""
    
    migration_system.safe_drop_table("settings")
    print("Settings table removed successfully")

