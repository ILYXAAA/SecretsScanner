"""
Add hash_from_ci field to secrets and backfill data.
Calculates SHA-256 from: file path + secret value + line number (concatenated, no delimiter).
"""


def upgrade(migration_system):
    """Add hash_from_ci column and backfill existing records"""
    from sqlalchemy import text
    import hashlib

    migration_system.safe_add_column("secrets", "hash_from_ci TEXT")

    # Optional index to speed up external service lookups
    migration_system.safe_create_index(
        "CREATE INDEX IF NOT EXISTS idx_secrets_hash_from_ci ON secrets (hash_from_ci)",
        "idx_secrets_hash_from_ci"
    )

    with migration_system.engine.connect() as conn:
        rows = conn.execute(text("SELECT id, path, secret, line FROM secrets")).fetchall()
        updated = 0

        for row in rows:
            path = row[1] or ""
            secret = row[2] or ""
            line = row[3] or 0
            raw = f"{path}{secret}{line}"
            hash_from_ci = hashlib.sha256(raw.encode("utf-8")).hexdigest()

            conn.execute(
                text("UPDATE secrets SET hash_from_ci = :hash_value WHERE id = :id"),
                {"hash_value": hash_from_ci, "id": row[0]}
            )
            updated += 1

        conn.commit()
        print(f"Added hash_from_ci and backfilled {updated} secrets")


def downgrade(migration_system):
    """Remove hash_from_ci column and index"""
    from sqlalchemy import text

    with migration_system.engine.connect() as conn:
        conn.execute(text("DROP INDEX IF EXISTS idx_secrets_hash_from_ci"))
        conn.commit()

    # SQLite does not support DROP COLUMN
    if "sqlite" in migration_system.database_url:
        print("SQLite does not support DROP COLUMN, skipping hash_from_ci column removal")
        return

    with migration_system.engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE secrets DROP COLUMN hash_from_ci"))
            conn.commit()
            print("Dropped hash_from_ci column from secrets table")
        except Exception as e:
            print(f"Could not drop hash_from_ci column: {e}")
