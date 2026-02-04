"""
URL parser for Azure DevOps and Devzone repository URLs
Supports parsing commit, branch, and tag references from URLs
"""
from urllib.parse import urlparse, parse_qs
import re
from typing import Dict, Optional, Tuple


def parse_repo_url_with_ref(repo_url: str) -> Dict[str, str]:
    """
    Parse repository URL and extract reference information (commit, branch, or tag)
    
    Supports:
    - Azure DevOps URLs with version parameter (?version=GBbranch, ?version=GTtag, ?version=GCcommit)
    - Azure DevOps URLs with /commit/hash path
    - Devzone URLs (git.devzone.local) with version parameter or /commit/hash path
    
    Args:
        repo_url: Full repository URL with optional ref information
        
    Returns:
        Dict with keys:
            - base_repo_url: Clean repository URL without ref info
            - ref_type: 'Commit', 'Branch', or 'Tag'
            - ref: Reference value (commit hash, branch name, or tag name)
            
    Raises:
        ValueError: If URL format is invalid or unsupported
    """
    if not repo_url or not isinstance(repo_url, str):
        raise ValueError("Repository URL cannot be empty")
    
    repo_url = repo_url.strip()
    
    # Check if it's a Devzone URL
    if "devzone.local" in repo_url.lower() or "git.devzone.local" in repo_url.lower():
        return _parse_devzone_url(repo_url)
    
    # Check if it's an Azure DevOps URL
    if "_git" in repo_url:
        return _parse_azure_devops_url(repo_url)
    
    raise ValueError("Unsupported repository URL format. Only Azure DevOps and Devzone URLs are supported.")


def _parse_azure_devops_url(repo_url: str) -> Dict[str, str]:
    """Parse Azure DevOps repository URL"""
    try:
        url_obj = urlparse(repo_url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {e}")
    
    path_parts = [p for p in url_obj.path.strip('/').split('/') if p]
    
    if '_git' not in path_parts:
        raise ValueError("URL does not contain '_git'")
    
    git_index = path_parts.index('_git')
    
    if git_index + 1 >= len(path_parts):
        raise ValueError("URL is invalid: repository name missing after '_git'")
    
    repository = path_parts[git_index + 1]
    
    if git_index < 1:
        raise ValueError("Insufficient information before '_git'")
    
    project = path_parts[git_index - 1]
    
    # Check if project is UUID (not allowed)
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    if re.match(uuid_pattern, project, re.IGNORECASE):
        raise ValueError("URL contains UUID as project name. Use URL with readable project name instead of UUID.")
    
    # Default values
    ref_type = "Branch"
    ref = "main"
    
    # Check for commit in path (format: /commit/hash)
    commit_index = -1
    try:
        commit_index = path_parts.index('commit')
    except ValueError:
        pass
    
    if commit_index != -1 and commit_index == git_index + 2:
        # Check if version parameter is also present (conflict)
        if url_obj.query and 'version' in parse_qs(url_obj.query):
            raise ValueError("URL contains both commit in path and version parameter")
        
        ref_type = "Commit"
        if commit_index + 1 < len(path_parts):
            ref = path_parts[commit_index + 1]
        else:
            raise ValueError("URL is invalid: commit hash missing after '/commit/'")
    
    # Check for version parameter
    elif url_obj.query:
        query_params = parse_qs(url_obj.query)
        if 'version' in query_params:
            version = query_params['version'][0]
            
            # Check if commit is also in path (conflict)
            if commit_index != -1:
                raise ValueError("URL contains both version parameter and commit in path")
            
            if version.startswith('GB'):
                ref_type = "Branch"
                ref = version[2:]
            elif version.startswith('GT'):
                ref_type = "Tag"
                ref = version[2:]
            elif version.startswith('GC'):
                ref_type = "Commit"
                ref = version[2:]
            else:
                raise ValueError(f"Unsupported version parameter format: {version}")
            
            if not ref:
                raise ValueError("Empty value after prefix in version parameter")
    
    # Clean base repo URL - remove commit path and query parameters
    clean_path = url_obj.path
    if '/commit/' in clean_path:
        clean_path = clean_path.split('/commit/')[0]
    
    base_repo_url = f"{url_obj.scheme}://{url_obj.netloc}{clean_path}"
    
    return {
        "base_repo_url": base_repo_url,
        "ref_type": ref_type,
        "ref": ref
    }


def _parse_devzone_url(repo_url: str) -> Dict[str, str]:
    """Parse Devzone repository URL"""
    # Normalize legacy/malformed DevZone URL format:
    # - https://git.devzone.local:devzone/group/project/repo -> https://git.devzone.local/devzone/group/project/repo
    # Some systems incorrectly use ":devzone" as a namespace separator; DevZone expects "/devzone".
    if isinstance(repo_url, str) and repo_url.startswith(("http://git.devzone.local:devzone/", "https://git.devzone.local:devzone/")):
        scheme, rest = repo_url.split("://", 1)
        rest = rest.replace("git.devzone.local:devzone/", "git.devzone.local/devzone/", 1)
        repo_url = f"{scheme}://{rest}"

    try:
        url_obj = urlparse(repo_url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {e}")
    
    # Convert git@ format to https if needed
    if repo_url.startswith("git@git.devzone.local:"):
        # Extract path after colon
        path = repo_url.split("git@git.devzone.local:")[1]
        # Remove .git suffix if present
        if path.endswith(".git"):
            path = path[:-4]
        # Construct https URL
        repo_url = f"https://git.devzone.local/{path}"
        url_obj = urlparse(repo_url)
    
    if not url_obj.netloc or "devzone.local" not in url_obj.netloc.lower():
        raise ValueError("Invalid Devzone URL format")
    
    path_parts = [p for p in url_obj.path.strip('/').split('/') if p]
    
    if not path_parts:
        raise ValueError("Devzone URL must contain repository path")
    
    # Default values
    ref_type = "Branch"
    ref = "main"
    
    # Check for commit in path (format: /commit/hash)
    commit_index = -1
    try:
        commit_index = path_parts.index('commit')
    except ValueError:
        pass
    
    if commit_index != -1 and commit_index < len(path_parts) - 1:
        # Check if version parameter is also present (conflict)
        if url_obj.query and 'version' in parse_qs(url_obj.query):
            raise ValueError("URL contains both commit in path and version parameter")
        
        ref_type = "Commit"
        ref = path_parts[commit_index + 1]
        if not ref:
            raise ValueError("URL is invalid: commit hash missing after '/commit/'")
    
    # Check for version parameter
    elif url_obj.query:
        query_params = parse_qs(url_obj.query)
        if 'version' in query_params:
            version = query_params['version'][0]
            
            # Check if commit is also in path (conflict)
            if commit_index != -1:
                raise ValueError("URL contains both version parameter and commit in path")
            
            if version.startswith('GB'):
                ref_type = "Branch"
                ref = version[2:]
            elif version.startswith('GT'):
                ref_type = "Tag"
                ref = version[2:]
            elif version.startswith('GC'):
                ref_type = "Commit"
                ref = version[2:]
            else:
                raise ValueError(f"Unsupported version parameter format: {version}")
            
            if not ref:
                raise ValueError("Empty value after prefix in version parameter")
    
    # Clean base repo URL - remove commit path and query parameters
    clean_path = url_obj.path
    if '/commit/' in clean_path:
        clean_path = clean_path.split('/commit/')[0]
    
    # Remove .git suffix if present
    if clean_path.endswith('.git'):
        clean_path = clean_path[:-4]
    
    base_repo_url = f"{url_obj.scheme}://{url_obj.netloc}{clean_path}"
    
    return {
        "base_repo_url": base_repo_url,
        "ref_type": ref_type,
        "ref": ref
    }
