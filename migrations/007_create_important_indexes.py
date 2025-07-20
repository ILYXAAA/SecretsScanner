"""
Create important performance indexes
Adds critical composite indexes to optimize dashboard queries
"""

def upgrade(migration_system):
    """Create performance-critical indexes"""
    
    # Критически важный индекс для запросов статистики секретов
    # Покрывает все фильтры в dashboard: scan_id, severity, is_exception
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_secrets_scan_severity_exception ON secrets (scan_id, severity, is_exception)",
        "idx_secrets_scan_severity_exception"
    )
    
    # Индекс для быстрого поиска последних сканов по проектам
    # Покрывает фильтрацию и сортировку в dashboard
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_scans_project_status_date ON scans (project_name, status, started_at DESC)",
        "idx_scans_project_status_date"
    )
    
    # Дополнительный индекс для поиска проектов
    # Ускорит поиск по названию и repo_url в dashboard
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_projects_search ON projects (name, repo_url)",
        "idx_projects_search"
    )
    
    # Индекс для оптимизации GROUP BY запросов по статистике
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_secrets_scan_exception_only ON secrets (scan_id, is_exception)",
        "idx_secrets_scan_exception_only"
    )
    
    print("Created critical performance indexes for dashboard optimization")

def downgrade(migration_system):
    """Drop performance indexes"""
    
    indexes_to_drop = [
        "idx_secrets_scan_severity_exception",
        "idx_scans_project_status_date", 
        "idx_projects_search",
        "idx_secrets_scan_exception_only"
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
    
    print("Removed performance indexes")