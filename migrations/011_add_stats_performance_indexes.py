"""
Add performance indexes for statistics dashboard
Optimizes queries for scan activity, confidence accuracy, and file extensions stats
"""

def upgrade(migration_system):
    """Create performance indexes for stats dashboard queries"""
    
    # Индекс для confidence-accuracy запросов
    # Покрывает фильтры: status (Confirmed/Refuted), confidence, is_exception
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_secrets_status_confidence ON secrets (status, confidence, is_exception)",
        "idx_secrets_status_confidence"
    )
    
    # Индекс для scan-activity запросов (если еще не существует)
    # Уже может быть в idx_scans_status, но создаем специфичный для started_at
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_scans_status_started ON scans (status, started_at)",
        "idx_scans_status_started"
    )
    
    # Дополнительный индекс для оптимизации JOIN запросов со сканами
    # Покрывает фильтры: completed scans + status secrets
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_secrets_scan_status ON secrets (scan_id, status, is_exception)",
        "idx_secrets_scan_status"
    )
    
    print("Created performance indexes for statistics dashboard optimization")

def downgrade(migration_system):
    """Drop performance indexes"""
    
    indexes_to_drop = [
        "idx_secrets_status_confidence",
        "idx_scans_status_started",
        "idx_secrets_scan_status"
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
    
    print("Removed statistics dashboard performance indexes")

