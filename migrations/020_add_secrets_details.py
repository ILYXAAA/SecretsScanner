"""
Add secrets_details field to secrets table.
Stores JSON array of individual secrets for "Too Many Secrets" type findings.
"""


def upgrade(migration_system):
    migration_system.safe_add_column("secrets", "secrets_details TEXT")


def downgrade(migration_system):
    if "sqlite" in migration_system.database_url:
        print("SQLite does not support DROP COLUMN, skipping secrets_details column removal")
        return

    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        try:
            conn.execute(text("ALTER TABLE secrets DROP COLUMN secrets_details"))
            conn.commit()
            print("Dropped secrets_details column from secrets table")
        except Exception as e:
            print(f"Could not drop secrets_details column: {e}")
