"""
Recalculate hash_from_ci after normalizing DevZone file paths.
Normalization: remove "/devzone_repository/" prefix from secrets.path before hashing.
Formula: SHA-256(normalized_path + secret + line)
"""


def upgrade(migration_system):
    """Recalculate hash_from_ci for existing records"""
    from sqlalchemy import text
    import hashlib

    with migration_system.engine.connect() as conn:
        rows = conn.execute(text("SELECT id, path, secret, line FROM secrets")).fetchall()
        updated = 0

        for row in rows:
            secret_id = row[0]
            path = (row[1] or "").replace("/devzone_repository/", "")
            secret = row[2] or ""
            line = row[3] or 0
            raw = f"{path}{secret}{line}"
            hash_from_ci = hashlib.sha256(raw.encode("utf-8")).hexdigest()

            conn.execute(
                text("UPDATE secrets SET hash_from_ci = :hash_value WHERE id = :id"),
                {"hash_value": hash_from_ci, "id": secret_id}
            )
            updated += 1

        conn.commit()
        print(f"Recalculated hash_from_ci for {updated} secrets (normalized devzone_repository prefix)")


def downgrade(migration_system):
    """
    No-op downgrade: previous hashes are not recoverable without storing prior values.
    """
    print("No downgrade action for hash recalculation migration")
