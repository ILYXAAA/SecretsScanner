"""
Add API tokens and usage tracking tables
Adds api_tokens and api_usage tables for API authentication and rate limiting
"""

def upgrade(migration_system):
    """Add API tokens and usage tables"""
    
    # Create api_tokens table
    create_api_tokens_table = """
    CREATE TABLE IF NOT EXISTS api_tokens (
        id INTEGER PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        token_hash VARCHAR(64) NOT NULL UNIQUE,
        prefix VARCHAR(255) NOT NULL,
        created_by VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NULL,
        is_active BOOLEAN DEFAULT TRUE,
        last_used_at TIMESTAMP NULL,
        requests_per_minute INTEGER DEFAULT 60,
        requests_per_hour INTEGER DEFAULT 1000,
        requests_per_day INTEGER DEFAULT 10000,
        permissions TEXT DEFAULT '{}'
    )
    """
    
    # Create api_usage table
    create_api_usage_table = """
    CREATE TABLE IF NOT EXISTS api_usage (
        id INTEGER PRIMARY KEY,
        token_id INTEGER NOT NULL,
        endpoint VARCHAR(255) NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        response_status INTEGER,
        response_time_ms INTEGER,
        ip_address VARCHAR(45) NULL,
        user_agent VARCHAR(512) NULL
    )
    """
    
    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        
        # Create tables
        conn.execute(text(create_api_tokens_table))
        print("Created api_tokens table")
        
        conn.execute(text(create_api_usage_table))
        print("Created api_usage table")
        
        # Create indexes
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens (token_hash)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_api_tokens_active ON api_tokens (is_active)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_api_tokens_name ON api_tokens (name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_api_usage_token_id ON api_usage (token_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_api_usage_timestamp ON api_usage (timestamp)"))
            print("Created indexes for API tables")
        except Exception as e:
            print(f"Warning: Could not create some indexes: {e}")
        
        conn.commit()
        print("API tokens tables created successfully")

def downgrade(migration_system):
    """Remove API tokens tables"""
    
    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        
        try:
            # Drop tables in reverse order (usage first due to potential foreign key constraints)
            conn.execute(text("DROP TABLE IF EXISTS api_usage"))
            print("Dropped api_usage table")
            
            conn.execute(text("DROP TABLE IF EXISTS api_tokens"))
            print("Dropped api_tokens table")
            
            conn.commit()
            print("API tokens tables removed successfully")
            
        except Exception as e:
            print(f"Error removing API tokens tables: {e}")
            conn.rollback()