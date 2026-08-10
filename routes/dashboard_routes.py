from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from config import HUB_TYPE
from models import Project, Scan, Secret
from services.auth import get_current_user
from services.database import get_db
from services.templates import templates
#import time

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, page: int = 1, search: str = "", current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    #start = time.time()
    per_page = 20
    offset = (page - 1) * per_page
    
    # Recent scans with project repo URLs
    recent_scans = db.query(Scan).order_by(Scan.started_at.desc()).limit(20).all()
    project_names = list({scan.project_name for scan in recent_scans})
    projects_by_name = {}
    if project_names:
        projects_by_name = {
            project.name: project
            for project in db.query(Project).filter(Project.name.in_(project_names)).all()
        }

    recent_scans_data = []
    for scan in recent_scans:
        project = projects_by_name.get(scan.project_name)
        scan_type = scan.scan_type or "secrets"
        recent_scans_data.append({
            "scan": scan,
            "repo_url": project.repo_url if project else "",
            "high_count": scan.high_secrets_count or 0,
            "potential_count": scan.potential_secrets_count or 0,
            "violations_count": scan.violations_count or 0,
            "findings_total": (scan.violations_count or 0) if scan_type == "forbidden" else (scan.high_secrets_count or 0) + (scan.potential_secrets_count or 0),
            "scan_type": scan_type,
        })
    
    # Оптимизированный запрос проектов с пагинацией и поиском
    projects_query = db.query(Project)
    if search:
        projects_query = projects_query.filter(
            Project.name.contains(search) | Project.repo_url.contains(search)
        )
    
    total_projects = projects_query.count()
    projects_list = projects_query.offset(offset).limit(per_page).all()
    
    # Получить последние сканы для проектов ОДНИМ эффективным запросом
    project_names = [p.name for p in projects_list]
    
    # Подзапрос для поиска ID последних сканов по каждому проекту
    latest_scans_subquery = db.query(
        Scan.project_name,
        func.max(Scan.started_at).label('max_date')
    ).filter(
        Scan.project_name.in_(project_names)
    ).group_by(Scan.project_name).subquery()
    
    # Получить полные данные последних сканов с денормализованными счетчиками
    latest_scans = db.query(Scan).join(
        latest_scans_subquery,
        (Scan.project_name == latest_scans_subquery.c.project_name) &
        (Scan.started_at == latest_scans_subquery.c.max_date)
    ).all()
    
    # Создать словарь для быстрого поиска
    scans_dict = {scan.project_name: scan for scan in latest_scans}
    
    # Формируем данные проектов
    projects_data = []
    for project in projects_list:
        latest_scan = scans_dict.get(project.name)
        
        # Используем денормализованные счетчики из таблицы scans
        if latest_scan and latest_scan.status == 'completed':
            high_count = latest_scan.high_secrets_count or 0
            potential_count = latest_scan.potential_secrets_count or 0
        else:
            high_count = 0
            potential_count = 0
        
        scan_type = None
        findings_total = None
        if latest_scan:
            scan_type = latest_scan.scan_type or "secrets"
            if latest_scan.status == "completed":
                findings_total = (
                    (latest_scan.violations_count or 0)
                    if scan_type == "forbidden"
                    else (latest_scan.high_secrets_count or 0) + (latest_scan.potential_secrets_count or 0)
                )

        projects_data.append({
            "project": project,
            "latest_scan": latest_scan,
            "repo_url": project.repo_url or "",
            "high_count": high_count,
            "potential_count": potential_count,
            "findings_total": findings_total,
            "scan_type": scan_type,
            "latest_scan_date": latest_scan.started_at if latest_scan else datetime.min
        })
    
    # Сортируем по дате последнего скана
    projects_data.sort(key=lambda x: x["latest_scan_date"], reverse=True)
    total_pages = (total_projects + per_page - 1) // per_page

    #end = time.time()
    #print(f"Время выполнения: {end - start:.4f} секунд")
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "recent_scans": recent_scans_data,
        "projects": projects_data,
        "current_page": page,
        "total_pages": total_pages,
        "search": search,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "HUB_TYPE": HUB_TYPE,
        "current_user": current_user
    })