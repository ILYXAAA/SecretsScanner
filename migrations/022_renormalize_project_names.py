"""
Renormalize project names from repository URLs.

Formula: last URL path segment, strip .git, replace '-' and '.' with '_'.
Collisions within the batch get suffixes _1, _2, ...
Updates scans.project_name to match renamed projects.
"""

from utils.project_name import derive_project_name_from_repo_url, allocate_unique_project_name_from_set


def upgrade(migration_system):
    from sqlalchemy import text

    with migration_system.engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, name, repo_url FROM projects ORDER BY id")
        ).fetchall()

        used_names = set()
        mappings = []

        for project_id, old_name, repo_url in rows:
            try:
                base_name = derive_project_name_from_repo_url(repo_url or "")
                new_name = allocate_unique_project_name_from_set(base_name, used_names)
            except ValueError:
                new_name = old_name
                used_names.add(old_name)

            mappings.append((project_id, old_name, new_name))

        renames = [(old_name, new_name) for _, old_name, new_name in mappings if old_name != new_name]

        if not renames:
            print("Project names already normalized, no changes")
            return

        case_parts = []
        params = {}
        for index, (old_name, new_name) in enumerate(renames):
            case_parts.append(f"WHEN :old_{index} THEN :new_{index}")
            params[f"old_{index}"] = old_name
            params[f"new_{index}"] = new_name

        conn.execute(
            text(
                f"UPDATE scans SET project_name = CASE project_name "
                f"{' '.join(case_parts)} ELSE project_name END"
            ),
            params,
        )

        conn.execute(text("UPDATE projects SET name = '__mig_' || id"))

        for project_id, _, new_name in mappings:
            conn.execute(
                text("UPDATE projects SET name = :new_name WHERE id = :project_id"),
                {"new_name": new_name, "project_id": project_id},
            )

        conn.commit()
        print(f"Renamed {len(renames)} project(s)")
        for old_name, new_name in renames:
            print(f"  {old_name} -> {new_name}")


def downgrade(migration_system):
    print("No downgrade action for project name renormalization migration")
