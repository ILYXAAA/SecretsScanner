"""
Initial database schema migration
Creates all base tables for the Secrets Scanner application
"""

def upgrade(migration_system):
    """Create initial schema"""
    
    # Создаем базовые индексы для оптимизации
    indexes = [
        ("CREATE INDEX IF NOT EXISTS idx_secrets_composite ON secrets (path, line, secret, type)", "idx_secrets_composite"),
        ("CREATE INDEX IF NOT EXISTS idx_secrets_scan_exception ON secrets (scan_id, is_exception)", "idx_secrets_scan_exception"),
        ("CREATE INDEX IF NOT EXISTS idx_secrets_severity ON secrets (scan_id, severity, is_exception)", "idx_secrets_severity"),
        ("CREATE INDEX IF NOT EXISTS idx_secrets_type ON secrets (scan_id, type, is_exception)", "idx_secrets_type"),
        ("CREATE INDEX IF NOT EXISTS idx_scans_project_time ON scans (project_name, completed_at)", "idx_scans_project_time"),
        ("CREATE INDEX IF NOT EXISTS idx_scans_status ON scans (status, started_at)", "idx_scans_status"),
    ]
    
    for index_sql, index_name in indexes:
        migration_system.safe_create_index(index_sql, index_name)

def downgrade(migration_system):
    """Drop initial schema indexes"""
    
    indexes_to_drop = [
        "idx_secrets_composite",
        "idx_secrets_scan_exception", 
        "idx_secrets_severity",
        "idx_secrets_type",
        "idx_scans_project_time",
        "idx_scans_status"
    ]
    
    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        for index_name in indexes_to_drop:
            try:
                conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                print(f"Dropped index {index_name}")
            except Exception as e:
                print(f"Could not drop index {index_name}: {e}")
        conn.commit()