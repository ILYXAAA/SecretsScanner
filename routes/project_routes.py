from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from urllib.parse import urlparse
import urllib.parse
import logging
import json
import os
from config import get_full_url, HUB_TYPE
from models import Project, Scan, Secret
from services.auth import get_current_user
from services.database import get_db
from services.templates import templates
#import time
logger = logging.getLogger("main")
user_logger = logging.getLogger("user_actions")

router = APIRouter()

def validate_repo_url(repo_url: str, hub_type: str) -> str:
    """Validate and normalize repository URL based on hub type"""
    repo_url = (repo_url or "").strip()
    
    # Проверяем что URL не содержит параметров версии или commit в пути
    if "?" in repo_url:
        raise ValueError("❌ Ссылка на репозиторий не должна содержать параметры (version, commit и т.д.). Используйте базовую ссылку на репозиторий.")
    
    if "/commit/" in repo_url:
        raise ValueError("❌ Ссылка на репозиторий не должна содержать путь к коммиту (/commit/). Используйте базовую ссылку на репозиторий.")
    
    # Check for devzone URLs first
    if "devzone.local" in repo_url:
        # Normalize legacy/malformed DevZone URL format:
        # - https://git.devzone.local:devzone/group/project/repo -> https://git.devzone.local/devzone/group/project/repo
        # Some systems incorrectly use ":devzone" as a namespace separator; DevZone expects "/devzone".
        if repo_url.startswith(("http://git.devzone.local:devzone/", "https://git.devzone.local:devzone/")):
            scheme, rest = repo_url.split("://", 1)
            rest = rest.replace("git.devzone.local:devzone/", "git.devzone.local/devzone/", 1)
            repo_url = f"{scheme}://{rest}"

        # Convert git@ format to https for devzone
        if repo_url.startswith("git@git.devzone.local:"):
            # Extract path after the colon
            path = repo_url.split("git@git.devzone.local:")[1]
            # Remove .git suffix if present
            if path.endswith(".git"):
                path = path[:-4]
            # Construct https URL
            normalized_url = f"https://git.devzone.local/{path}"
            return normalized_url
        elif repo_url.startswith("https://git.devzone.local"):
            # Already in correct format, just normalize
            normalized_url = repo_url.rstrip('/')
            if normalized_url.endswith(".git"):
                normalized_url = normalized_url[:-4]
            return normalized_url
        else:
            raise ValueError("❌ Некорректный формат URL для devzone")
    
    if hub_type == "Azure":
        import re
        
        parsed = urlparse(repo_url)
        
        if not parsed.netloc:
            raise ValueError("❌ URL должен содержать имя сервера")
        
        path_parts = parsed.path.strip('/').split('/')
        
        if '_git' not in path_parts:
            raise ValueError("❌ URL не содержит '_git'")
        
        git_index = path_parts.index('_git')
        
        if git_index + 1 >= len(path_parts):
            raise ValueError("❌ URL некорректен: отсутствует имя репозитория после '_git'")
        
        repository = path_parts[git_index + 1]
        
        if git_index >= 2:
            collection = path_parts[0]
            project = path_parts[git_index - 1]
        elif git_index == 1:
            collection = path_parts[0]
            project = repository
        else:
            raise ValueError("❌ Невозможно определить коллекцию и проект из URL")
        
        if not collection or not project or not repository:
            raise ValueError("❌ URL содержит пустые компоненты")
        
        # Проверяем, что проект не является UUID
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        if re.match(uuid_pattern, project, re.IGNORECASE):
            raise ValueError("❌ URL содержит UUID в качестве имени проекта. Используйте URL с читаемым именем проекта вместо UUID.")
        
        return repo_url
    
    elif hub_type == "Git":
        parsed = urlparse(repo_url)
        if not parsed.netloc:
            raise ValueError("❌ Некорректный URL репозитория")
        if parsed.scheme not in ['http', 'https']:
            raise ValueError("❌ URL должен использовать HTTP или HTTPS")
        
        return repo_url
    
    return repo_url

def load_language_patterns():
    """Load language patterns from JSON file"""
    try:
        patterns_file = os.path.join("static", "languages_patterns.json")
        with open(patterns_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading language patterns: {e}")
        return {}

def get_language_stats_from_scan(scan):
    """Get language statistics from scan data provided by microservice"""
    if not scan.detected_languages:
        return []
    
    try:
        detected_languages = json.loads(scan.detected_languages)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse detected_languages for scan {scan.id}")
        return []
    
    if not detected_languages:
        return []
    
    language_patterns = load_language_patterns()
    
    # Вычисляем общее количество файлов
    total_files = sum(lang_data.get("Files", 0) for lang_data in detected_languages.values())
    
    if total_files == 0:
        return []
    
    language_stats = []
    
    # Сортируем языки по количеству файлов
    sorted_languages = sorted(detected_languages.items(), key=lambda x: x[1].get("Files", 0), reverse=True)
    
    for language, lang_data in sorted_languages:
        file_count = lang_data.get("Files", 0)
        extensions_list = lang_data.get("ExtensionsList", [])
        
        percentage = (file_count / total_files) * 100 if total_files > 0 else 0
        
        # Получаем метаданные языка из patterns
        lang_config = language_patterns.get(language.lower(), {})
        
        language_stats.append({
            'language': language,
            'count': file_count,
            'percentage': round(percentage, 1),
            'color': lang_config.get('color', '#6b7280'),  # серый по умолчанию
            'icon': lang_config.get('icon', None),
            'extensions': extensions_list
        })
    
    return language_stats

def get_framework_stats_from_scan(scan):
    """Get framework statistics from scan data provided by microservice"""
    if not scan.detected_frameworks:
        return {}
    
    try:
        detected_frameworks = json.loads(scan.detected_frameworks)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse detected_frameworks for scan {scan.id}")
        return {}
    
    language_patterns = load_language_patterns()
    
    # Добавляем метаданные к фреймворкам
    framework_stats = {}
    for framework, detections in detected_frameworks.items():
        framework_lower = framework.lower()
        framework_config = language_patterns.get(framework_lower, {})
        
        framework_stats[framework] = {
            'detections': detections,
            'color': framework_config.get('color', '#6b7280'),
            'icon': framework_config.get('icon', None)
        }
    
    return framework_stats

@router.get("/project/{project_name}", response_class=HTMLResponse)
async def project_page(request: Request, project_name: str, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    #start = time.time()
    project = db.query(Project).filter(Project.name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get latest scan
    latest_scan = db.query(Scan).filter(Scan.project_name == project_name).order_by(Scan.started_at.desc()).first()
    
    # Get language and framework statistics from latest scan
    language_stats = []
    framework_stats = {}
    if latest_scan:
        language_stats = get_language_stats_from_scan(latest_scan)
        framework_stats = get_framework_stats_from_scan(latest_scan)
    
    # Get all scans for history
    scans = db.query(Scan).filter(Scan.project_name == project_name).order_by(Scan.started_at.desc()).all()
    
    # Count confirmed secrets for each scan
    scan_stats = []
    for scan in scans:
        confirmed_count = db.query(Secret).filter(
            Secret.scan_id == scan.id,
            Secret.is_exception == False
        ).count()
        scan_stats.append({
            "scan": scan,
            "confirmed_count": confirmed_count
        })
    
    # Get all projects for merge functionality
    all_projects = db.query(Project).filter(Project.name != project_name).all()
    
    #end = time.time()
    #print(f"Время выполнения: {end - start:.4f} секунд")
    return templates.TemplateResponse("project.html", {
        "request": request,
        "project": project,
        "latest_scan": latest_scan,
        "language_stats": language_stats,
        "framework_stats": framework_stats,
        "scan_stats": scan_stats,
        "all_projects": all_projects,
        "HUB_TYPE": HUB_TYPE,
        "current_user": current_user
    })

@router.post("/projects/add")
async def add_project(request: Request, project_name: str = Form(...), repo_url: str = Form(...), 
                     current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        # Validate project name
        project_name = project_name.strip()
        repo_url = repo_url.strip()
        
        if not project_name:
            return RedirectResponse(url=get_full_url("dashboard?error=empty_project_name"), status_code=302)
        
        if not repo_url:
            return RedirectResponse(url=get_full_url("dashboard?error=empty_repo_url"), status_code=302)
        
        # Check project name format
        import re
        if not re.match(r'^[a-zA-Z0-9._\-\s]+$', project_name):
            return RedirectResponse(url=get_full_url("dashboard?error=invalid_project_name"), status_code=302)
        
        # Validate and normalize repository URL
        normalized_url = validate_repo_url(repo_url, HUB_TYPE)
        
        # Check if project already exists by name
        existing_name = db.query(Project).filter(Project.name == project_name).first()
        if existing_name:
            user_logger.info(f"User '{current_user}' attempted to create duplicate project '{project_name}'")
            return RedirectResponse(url=get_full_url("dashboard?error=project_exists"), status_code=302)
        
        # Check if project already exists by repo URL
        existing_url = db.query(Project).filter(Project.repo_url == normalized_url).first()
        if existing_url:
            user_logger.info(f"User '{current_user}' attempted to create project with duplicate repo URL: {normalized_url}")
            return RedirectResponse(url=get_full_url("dashboard?error=repo_url_exists"), status_code=302)
        
        # Create project
        project = Project(name=project_name, repo_url=normalized_url, created_by=current_user)
        db.add(project)
        db.commit()
        user_logger.info(f"User '{current_user}' created new project '{project_name}' with repo URL: {normalized_url}")
        
        return RedirectResponse(url=get_full_url(f"project/{project_name}"), status_code=302)
    
    except ValueError as e:
        encoded_error = urllib.parse.quote(str(e))
        return RedirectResponse(url=get_full_url(f"dashboard?error={encoded_error}"), status_code=302)
    except Exception as e:
        logger.error(f"Error adding project: {e}")
        return RedirectResponse(url=get_full_url("dashboard?error=unexpected_error"), status_code=302)
    
@router.post("/projects/update")
async def update_project(request: Request, project_id: int = Form(...), project_name: str = Form(...), 
                        repo_url: str = Form(...), _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        # Validate and normalize repository URL based on hub type
        normalized_url = validate_repo_url(repo_url, HUB_TYPE)
        
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return RedirectResponse(url=get_full_url(f"project/{project_name}?error=project_not_found"), status_code=302)
        
        existing = db.query(Project).filter(Project.name == project_name, Project.id != project_id).first()
        if existing:
            return RedirectResponse(url=get_full_url(f"project/{project.name}?error=project_exists"), status_code=302)
        
        # Store old project name for updating related scans
        old_project_name = project.name
        
        # Update project
        project.name = project_name
        project.repo_url = normalized_url
        
        # Update all scans that reference the old project name
        if old_project_name != project_name:
            db.query(Scan).filter(Scan.project_name == old_project_name).update(
                {Scan.project_name: project_name}
            )
        
        db.commit()
        user_logger.warning(f"Project '{old_project_name}' updated to '{project_name}' by user (repo URL: {normalized_url})")

        return RedirectResponse(url=get_full_url(f"project/{project_name}?success=project_updated"), status_code=302)
    
    except ValueError as e:
        encoded_error = urllib.parse.quote(str(e))
        return RedirectResponse(url=get_full_url(f"project/{project_name}?error={encoded_error}"), status_code=302)
    except Exception as e:
        logger.error(f"Error updating project: {e}")
        return RedirectResponse(url=get_full_url(f"project/{project_name}?error=project_update_failed"), status_code=302)

@router.post("/projects/{project_id}/delete")
async def delete_project(project_id: int, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse(url=get_full_url("dashboard?error=project_not_found"), status_code=302)
    
    # Delete all related scans and secrets
    scans = db.query(Scan).filter(Scan.project_name == project.name).all()
    for scan in scans:
        db.query(Secret).filter(Secret.scan_id == scan.id).delete()
        db.delete(scan)
    
    db.delete(project)
    db.commit()
    user_logger.warning(f"User '{current_user}' deleted project '{project.name}' (including {len(scans)} scans)")
    
    return RedirectResponse(url=get_full_url("dashboard?success=project_deleted"), status_code=302)

@router.post("/projects/merge")
async def merge_projects(request: Request, 
                        main_project_name: str = Form(...), 
                        target_project_name: str = Form(...),
                        new_repo_url: str = Form(...),
                        current_user: str = Depends(get_current_user), 
                        db: Session = Depends(get_db)):
    """Merge two projects - move all scans from target project to main project"""
    try:
        # Validate inputs
        main_project_name = main_project_name.strip()
        target_project_name = target_project_name.strip()
        new_repo_url = new_repo_url.strip()
        
        if not main_project_name or not target_project_name or not new_repo_url:
            return RedirectResponse(url=get_full_url(f"project/{main_project_name}?error=empty_merge_fields"), status_code=302)
        
        if main_project_name == target_project_name:
            return RedirectResponse(url=get_full_url(f"project/{main_project_name}?error=same_project_merge"), status_code=302)
        
        # Validate and normalize repository URL
        normalized_url = validate_repo_url(new_repo_url, HUB_TYPE)
        
        # Check if both projects exist
        main_project = db.query(Project).filter(Project.name == main_project_name).first()
        target_project = db.query(Project).filter(Project.name == target_project_name).first()
        
        if not main_project:
            return RedirectResponse(url=get_full_url(f"project/{main_project_name}?error=main_project_not_found"), status_code=302)
        
        if not target_project:
            return RedirectResponse(url=get_full_url(f"project/{main_project_name}?error=target_project_not_found"), status_code=302)
        
        # Get all scans from target project
        target_scans = db.query(Scan).filter(Scan.project_name == target_project_name).all()
        
        # Update all target scans to point to main project
        scan_count = 0
        for scan in target_scans:
            scan.project_name = main_project_name
            scan_count += 1
        
        # Update main project repository URL
        main_project.repo_url = normalized_url
        
        # Delete target project
        db.delete(target_project)
        
        db.commit()
        
        user_logger.warning(f"User '{current_user}' merged project '{target_project_name}' into '{main_project_name}'. {scan_count} scans moved. New repo URL: {normalized_url}")
        
        return RedirectResponse(url=get_full_url(f"project/{main_project_name}?success=project_merged&merged_scans={scan_count}"), status_code=302)
    
    except ValueError as e:
        encoded_error = urllib.parse.quote(str(e))
        return RedirectResponse(url=get_full_url(f"project/{main_project_name}?error={encoded_error}"), status_code=302)
    except Exception as e:
        logger.error(f"Error merging projects: {e}")
        return RedirectResponse(url=get_full_url(f"project/{main_project_name}?error=project_merge_failed"), status_code=302)

@router.get("/api/project/check")
async def check_project_exists(repo_url: str, _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    """Check if project exists by repo URL"""
    project = db.query(Project).filter(Project.repo_url == repo_url).first()
    if project:
        return {"exists": True, "project_name": project.name}
    else:
        return {"exists": False}

@router.get("/api/projects/search")
async def search_projects(q: str, current_project: str = "", _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    """Search projects by name for autocomplete"""
    projects = db.query(Project).filter(
        Project.name.ilike(f"%{q}%"),
        Project.name != current_project
    ).limit(10).all()
    
    return {"projects": [{"name": p.name, "repo_url": p.repo_url} for p in projects]}