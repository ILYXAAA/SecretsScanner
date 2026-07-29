"""
Remove secrets_details column and legacy Too Many Secrets aggregate rows.
"""


def upgrade(migration_system):
    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        conn.execute(text("DELETE FROM secrets WHERE type = 'Too Many Secrets'"))
        conn.commit()
        print("Deleted legacy Too Many Secrets aggregate rows")

    if "sqlite" in migration_system.database_url:
        print("SQLite does not support DROP COLUMN, secrets_details column left unused")
        return

    with migration_system.engine.connect() as conn:
        from sqlalchemy import text
        try:
            conn.execute(text("ALTER TABLE secrets DROP COLUMN secrets_details"))
            conn.commit()
            print("Dropped secrets_details column from secrets table")
        except Exception as e:
            print(f"Could not drop secrets_details column: {e}")


def downgrade(migration_system):
    migration_system.safe_add_column("secrets", "secrets_details TEXT")
