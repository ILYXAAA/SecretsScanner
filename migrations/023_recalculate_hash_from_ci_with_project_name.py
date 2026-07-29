"""
Recalculate hash_from_ci to include project name.

Formula: SHA-256(project_name + normalized_path + secret + line)
Run after 022_renormalize_project_names so project_name values are canonical.
"""

from utils.ci_hash import build_hash_from_ci


def upgrade(migration_system):
    from sqlalchemy import text

    with migration_system.engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT s.id, s.path, s.secret, s.line, sc.project_name
                FROM secrets s
                LEFT JOIN scans sc ON sc.id = s.scan_id
                """
            )
        ).fetchall()

        updated = 0
        for secret_id, path, secret_value, line_number, project_name in rows:
            hash_from_ci = build_hash_from_ci(
                project_name or "",
                path or "",
                secret_value or "",
                line_number or 0,
            )
            conn.execute(
                text("UPDATE secrets SET hash_from_ci = :hash_value WHERE id = :id"),
                {"hash_value": hash_from_ci, "id": secret_id},
            )
            updated += 1

        conn.commit()
        print(
            f"Recalculated hash_from_ci for {updated} secrets "
            "(project_name + normalized_path + secret + line)"
        )


def downgrade(migration_system):
    print("No downgrade action for hash recalculation migration")
