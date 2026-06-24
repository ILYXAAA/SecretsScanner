"""
Recalculate hash_from_ci after fixing DevZone path normalization.

Bug fix: stripping "/devzone_repository/" removed the leading slash from paths like
/devzone_repository/src/foo -> src/foo instead of /src/foo.

Formula: SHA-256(normalized_path + secret + line)
"""

from utils.ci_hash import build_hash_from_ci


def upgrade(migration_system):
    """Recalculate hash_from_ci for all secrets using corrected path normalization."""
    from sqlalchemy import text

    with migration_system.engine.connect() as conn:
        rows = conn.execute(text("SELECT id, path, secret, line FROM secrets")).fetchall()
        updated = 0

        for row in rows:
            secret_id = row[0]
            hash_from_ci = build_hash_from_ci(row[1] or "", row[2] or "", row[3] or 0)

            conn.execute(
                text("UPDATE secrets SET hash_from_ci = :hash_value WHERE id = :id"),
                {"hash_value": hash_from_ci, "id": secret_id},
            )
            updated += 1

        conn.commit()
        print(
            f"Recalculated hash_from_ci for {updated} secrets "
            "(fixed leading slash after devzone_repository prefix strip)"
        )


def downgrade(migration_system):
    """No-op downgrade: previous hashes are not recoverable without storing prior values."""
    print("No downgrade action for hash recalculation migration")
