"""
Recalculate hash_from_ci using the project name derived from the repository URL.

The container (SKIBKSU) builds `project` from REPO_WEB_URL/REPO_URL, so hashes must
not depend on the entity name or on uniqueness suffixes (_1, _2).

Projects whose scans already use the derived name (scans.project_name equals the
name derived from repo_url) are skipped: their hashes are already correct.
"""

from utils.ci_hash import build_hash_from_ci
from utils.project_name import ci_project_name


def upgrade(migration_system):
    from sqlalchemy import text

    with migration_system.engine.connect() as conn:
        projects = conn.execute(
            text("SELECT id, name, repo_url FROM projects ORDER BY id")
        ).fetchall()

        total_updated = 0
        skipped_ok = 0
        skipped_invalid = []

        for _, name, repo_url in projects:
            try:
                derived = ci_project_name(repo_url or "")
            except ValueError:
                skipped_invalid.append(name)
                continue

            if derived == name:
                skipped_ok += 1
                continue

            rows = conn.execute(
                text(
                    """
                    SELECT s.id, s.path, s.secret, s.line
                    FROM secrets s
                    JOIN scans sc ON sc.id = s.scan_id
                    WHERE sc.project_name = :name
                    """
                ),
                {"name": name},
            ).fetchall()

            for secret_id, path, secret_value, line_number in rows:
                new_hash = build_hash_from_ci(
                    derived, path or "", secret_value or "", line_number or 0
                )
                conn.execute(
                    text("UPDATE secrets SET hash_from_ci = :h WHERE id = :id"),
                    {"h": new_hash, "id": secret_id},
                )

            conn.commit()
            total_updated += len(rows)
            print(f"  {name} -> {derived}: {len(rows)} secrets recalculated")

        print(
            f"Recalculated hash_from_ci for {total_updated} secrets; "
            f"{skipped_ok} project(s) already correct, "
            f"{len(skipped_invalid)} skipped (no valid repo_url)"
        )
        for name in skipped_invalid:
            print(f"  skipped: {name}")


def downgrade(migration_system):
    print("No downgrade action for hash recalculation migration")
