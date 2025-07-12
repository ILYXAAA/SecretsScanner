"""
Add excluded_files_count and excluded_files_list
"""

def upgrade(migration_system):
    """Apply migration changes"""
    from sqlalchemy import text
    # Add column to scans
    migration_system.safe_add_column("scans", "excluded_files_count INTEGER DEFAULT '0'")
    # Add column to scans
    migration_system.safe_add_column("scans", "excluded_files_list TEXT")

def downgrade(migration_system):
    """Rollback migration changes"""
    from sqlalchemy import text
    # Drop column excluded_files_count from scans
    migration_system.safe_drop_column("scans", "excluded_files_count")
    # Drop column excluded_files_list from scans
    migration_system.safe_drop_column("scans", "excluded_files_list")
