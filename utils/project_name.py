"""Derive unique project names from repository URLs."""


def derive_project_name_from_repo_url(repo_url: str) -> str:
    """
    Build a project name from the repository URL:
    last path segment, strip optional .git, replace '-' and '.' with '_'.
    """
    url = (repo_url or "").strip().rstrip("/")
    if not url:
        raise ValueError("Repository URL cannot be empty")

    segment = url.split("/")[-1]
    if not segment:
        raise ValueError("Could not extract repository name from URL")

    if segment.lower().endswith(".git"):
        segment = segment[:-4]

    if not segment:
        raise ValueError("Could not extract repository name from URL")

    return segment.replace("-", "_").replace(".", "_")


def allocate_unique_project_name_from_set(base_name: str, used_names: set) -> str:
    """Return a unique project name using an in-memory set (for migrations/batch renames)."""
    project_name = base_name
    counter = 1
    while project_name in used_names:
        project_name = f"{base_name}_{counter}"
        counter += 1
    used_names.add(project_name)
    return project_name


def allocate_unique_project_name(db, base_name: str, model) -> str:
    """Return base_name or base_name_N if the name is already taken."""
    project_name = base_name
    counter = 1
    while db.query(model).filter(model.name == project_name).first():
        project_name = f"{base_name}_{counter}"
        counter += 1
    return project_name


def generate_project_name_from_repo_url(db, repo_url: str, model) -> str:
    """Derive and allocate a unique project name for a repository URL."""
    base_name = derive_project_name_from_repo_url(repo_url)
    return allocate_unique_project_name(db, base_name, model)
