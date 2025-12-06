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
    
    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        
        # Create table
        conn.execute(text(create_settings_table))
        print("Created settings table")
        
        # Insert default maintenance_mode = false
        try:
            conn.execute(text("""
                INSERT OR IGNORE INTO settings (key, value, updated_by) 
                VALUES ('maintenance_mode', 'false', 'system')
            """))
            print("Inserted default maintenance_mode setting")
        except Exception as e:
            print(f"Warning: Could not insert default setting: {e}")
        
        # Create index
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_settings_key ON settings (key)"))
            print("Created index for settings table")
        except Exception as e:
            print(f"Warning: Could not create index: {e}")
        
        conn.commit()
        print("Settings table created successfully")

def downgrade(migration_system):
    """Remove settings table"""
    
    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        
        try:
            conn.execute(text("DROP TABLE IF EXISTS settings"))
            print("Dropped settings table")
            conn.commit()
            print("Settings table removed successfully")
        except Exception as e:
            print(f"Error removing settings table: {e}")
            conn.rollback()

