"""
Add forbidden check scan type, summary fields, and forbidden_violations table.
"""


def upgrade(migration_system):
    migration_system.safe_add_column("scans", "scan_type VARCHAR DEFAULT 'secrets'")
    migration_system.safe_add_column("scans", "violations_count INTEGER DEFAULT 0")
    migration_system.safe_add_column("scans", "forbidden_passed BOOLEAN")
    migration_system.safe_add_column("scans", "forbidden_summary TEXT")

    create_forbidden_violations = """
    CREATE TABLE IF NOT EXISTS forbidden_violations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id VARCHAR NOT NULL,
        path VARCHAR,
        size INTEGER,
        category VARCHAR,
        language VARCHAR,
        extension VARCHAR,
        is_binary BOOLEAN DEFAULT 0,
        binary_reason VARCHAR,
        is_blocking BOOLEAN DEFAULT 1,
        violation_reasons TEXT,
        hash_from_ci VARCHAR,
        status VARCHAR DEFAULT 'No status',
        is_exception BOOLEAN DEFAULT 0,
        exception_comment TEXT,
        refuted_at DATETIME,
        confirmed_by VARCHAR,
        refuted_by VARCHAR
    )
    """

    if "postgresql" in migration_system.database_url:
        create_forbidden_violations = """
        CREATE TABLE IF NOT EXISTS forbidden_violations (
            id SERIAL PRIMARY KEY,
            scan_id VARCHAR NOT NULL,
            path VARCHAR,
            size INTEGER,
            category VARCHAR,
            language VARCHAR,
            extension VARCHAR,
            is_binary BOOLEAN DEFAULT FALSE,
            binary_reason VARCHAR,
            is_blocking BOOLEAN DEFAULT TRUE,
            violation_reasons TEXT,
            hash_from_ci VARCHAR,
            status VARCHAR DEFAULT 'No status',
            is_exception BOOLEAN DEFAULT FALSE,
            exception_comment TEXT,
            refuted_at TIMESTAMP,
            confirmed_by VARCHAR,
            refuted_by VARCHAR
        )
        """

    migration_system.safe_create_table(create_forbidden_violations, "forbidden_violations")

    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_forbidden_violations_scan_id ON forbidden_violations (scan_id)",
        "idx_forbidden_violations_scan_id",
    )
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_forbidden_violations_hash ON forbidden_violations (hash_from_ci)",
        "idx_forbidden_violations_hash",
    )
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_forbidden_violations_scan_exception ON forbidden_violations (scan_id, is_exception)",
        "idx_forbidden_violations_scan_exception",
    )
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_scans_scan_type ON scans (project_name, scan_type, started_at)",
        "idx_scans_scan_type",
    )

    print("Added forbidden check support (scan_type, forbidden_violations)")


def downgrade(migration_system):
    from sqlalchemy import text

    indexes_to_drop = [
        "idx_scans_scan_type",
        "idx_forbidden_violations_scan_exception",
        "idx_forbidden_violations_hash",
        "idx_forbidden_violations_scan_id",
    ]

    with migration_system.engine.connect() as conn:
        for index_name in indexes_to_drop:
            try:
                conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
            except Exception as e:
                print(f"Could not drop index {index_name}: {e}")
        conn.commit()

    migration_system.safe_drop_table("forbidden_violations")

    migration_system.safe_drop_column("scans", "forbidden_summary")
    migration_system.safe_drop_column("scans", "forbidden_passed")
    migration_system.safe_drop_column("scans", "violations_count")
    migration_system.safe_drop_column("scans", "scan_type")

    print("Removed forbidden check support")
