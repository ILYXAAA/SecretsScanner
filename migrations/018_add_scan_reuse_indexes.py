"""
Add indexes to speed up API scan deduplication lookups.
"""


def upgrade(migration_system):
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_scans_reuse_active ON scans (project_name, ref_type, ref, status, started_at)",
        "idx_scans_reuse_active",
    )
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_scans_reuse_completed ON scans (project_name, status, completed_at)",
        "idx_scans_reuse_completed",
    )
    print("Created indexes for API scan reuse lookups")


def downgrade(migration_system):
    from sqlalchemy import text

    indexes_to_drop = [
        "idx_scans_reuse_active",
        "idx_scans_reuse_completed",
    ]

    with migration_system.engine.connect() as conn:
        for index_name in indexes_to_drop:
            try:
                conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                print(f"Dropped index {index_name}")
            except Exception as e:
                print(f"Could not drop index {index_name}: {e}")
        conn.commit()

    print("Removed API scan reuse indexes")
