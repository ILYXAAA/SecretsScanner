from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, distinct, case
from datetime import datetime, timedelta
from typing import Optional
import logging

from models import Project, Scan, Secret, User
from services.auth import get_current_user, get_user_db
from services.database import get_db
from services.templates import templates

router = APIRouter()
logger = logging.getLogger("main")

@router.get("/stats-dashboard", response_class=HTMLResponse)
async def stats_dashboard(
    request: Request,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Страница статистики с дашбордами"""
    return templates.TemplateResponse("stats_dashboard.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "stats-dashboard"
    })

@router.get("/api/stats/kpi")
async def get_kpi_stats(
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить KPI метрики"""

    # Active Confirmed Secrets - все подтвержденные секреты
    active_confirmed = db.query(func.count(Secret.id)).join(
        Scan, Secret.scan_id == Scan.id
    ).filter(
        Scan.status == "completed",
        Secret.status == "Confirmed",
        Secret.is_exception == False
    ).scalar() or 0

    # New Confirmed в последние 24 часа
    day_ago = datetime.now() - timedelta(days=1)
    new_24h = db.query(func.count(Secret.id)).join(
        Scan, Secret.scan_id == Scan.id
    ).filter(
        Scan.completed_at >= day_ago,
        Scan.status == "completed",
        Secret.status == "Confirmed",
        Secret.is_exception == False
    ).scalar() or 0

    # New Confirmed за последние 7 дней
    week_ago = datetime.now() - timedelta(days=7)
    new_7d = db.query(func.count(Secret.id)).join(
        Scan, Secret.scan_id == Scan.id
    ).filter(
        Scan.completed_at >= week_ago,
        Scan.status == "completed",
        Secret.status == "Confirmed",
        Secret.is_exception == False
    ).scalar() or 0

    # Секреты со статусом "No status" - требуют разметки
    no_status_count = db.query(func.count(Secret.id)).join(
        Scan, Secret.scan_id == Scan.id
    ).filter(
        Scan.status == "completed",
        Secret.status == "No status",
        Secret.is_exception == False
    ).scalar() or 0

    return {
        "active_confirmed": active_confirmed,
        "new_24h": new_24h,
        "new_7d": new_7d,
        "no_status_count": no_status_count
    }

@router.get("/api/stats/trends")
async def get_trends(
    days: int = 30,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить тренды по дням (30 или 90 дней)"""

    start_date = datetime.now() - timedelta(days=days)

    # Получаем секреты по дням с разбивкой по severity
    trends = db.query(
        func.date(Scan.completed_at).label('date'),
        Secret.severity,
        func.count(Secret.id).label('count')
    ).join(
        Scan, Secret.scan_id == Scan.id
    ).filter(
        Scan.completed_at >= start_date,
        Scan.status == "completed",
        Secret.status == "Confirmed",
        Secret.is_exception == False
    ).group_by(
        func.date(Scan.completed_at),
        Secret.severity
    ).order_by(
        func.date(Scan.completed_at)
    ).all()

    # Форматируем данные для фронтенда
    data_by_date = {}
    for record in trends:
        date_str = record.date.strftime('%Y-%m-%d') if hasattr(record.date, 'strftime') else str(record.date)
        if date_str not in data_by_date:
            data_by_date[date_str] = {"High": 0, "Potential": 0}
        data_by_date[date_str][record.severity] = record.count

    # Преобразуем в список для графика
    result = []
    for date_str in sorted(data_by_date.keys()):
        result.append({
            "date": date_str,
            "high": data_by_date[date_str]["High"],
            "potential": data_by_date[date_str]["Potential"],
            "total": data_by_date[date_str]["High"] + data_by_date[date_str]["Potential"]
        })

    return {
        "days": days,
        "data": result
    }

@router.get("/api/stats/top-projects")
async def get_top_projects(
    limit: int = 5,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить топ проектов по количеству подтвержденных секретов"""

    top_projects = db.query(
        Scan.project_name,
        func.count(Secret.id).label('secret_count')
    ).join(
        Secret, Scan.id == Secret.scan_id
    ).filter(
        Scan.status == "completed",
        Secret.status == "Confirmed",
        Secret.is_exception == False
    ).group_by(
        Scan.project_name
    ).order_by(
        func.count(Secret.id).desc()
    ).limit(limit).all()

    result = [
        {
            "project_name": project.project_name,
            "secret_count": project.secret_count
        }
        for project in top_projects
    ]

    return {
        "top_projects": result
    }

@router.get("/api/stats/secret-types")
async def get_secret_types(
    limit: int = 10,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить распределение по типам секретов (топ-10)"""

    secret_types = db.query(
        Secret.type,
        func.count(Secret.id).label('count')
    ).join(
        Scan, Secret.scan_id == Scan.id
    ).filter(
        Scan.status == "completed",
        Secret.status == "Confirmed",
        Secret.is_exception == False
    ).group_by(
        Secret.type
    ).order_by(
        func.count(Secret.id).desc()
    ).limit(limit).all()

    total = sum(st.count for st in secret_types)

    result = [
        {
            "type": st.type,
            "count": st.count,
            "percentage": round((st.count / total * 100), 1) if total > 0 else 0
        }
        for st in secret_types
    ]

    return {
        "secret_types": result,
        "total": total
    }

@router.get("/api/stats/status-distribution")
async def get_status_distribution(
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить распределение секретов по статусам"""

    status_stats = db.query(
        Secret.status,
        func.count(Secret.id).label('count')
    ).join(
        Scan, Secret.scan_id == Scan.id
    ).filter(
        Scan.status == "completed"
    ).group_by(
        Secret.status
    ).all()

    total = sum(st.count for st in status_stats)

    result = {
        "confirmed": 0,
        "refuted": 0,
        "no_status": 0,
        "total": total
    }

    for st in status_stats:
        if st.status == "Confirmed":
            result["confirmed"] = st.count
        elif st.status == "Refuted":
            result["refuted"] = st.count
        elif st.status == "No status":
            result["no_status"] = st.count

    # Вычисляем проценты
    if total > 0:
        result["confirmed_pct"] = round((result["confirmed"] / total * 100), 1)
        result["refuted_pct"] = round((result["refuted"] / total * 100), 1)
        result["no_status_pct"] = round((result["no_status"] / total * 100), 1)
    else:
        result["confirmed_pct"] = 0
        result["refuted_pct"] = 0
        result["no_status_pct"] = 0

    # False Positive Rate
    if result["confirmed"] + result["refuted"] > 0:
        result["fp_rate"] = round(
            (result["refuted"] / (result["confirmed"] + result["refuted"]) * 100), 1
        )
    else:
        result["fp_rate"] = 0

    return result

@router.get("/api/stats/scan-activity")
async def get_scan_activity(
    days: int = 30,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить активность сканирований по времени"""
    
    start_date = datetime.now() - timedelta(days=days)
    
    # Оптимизированный запрос: фильтруем по дате и группируем на уровне БД
    scan_stats = db.query(
        func.date(Scan.started_at).label('date'),
        Scan.status,
        func.count(Scan.id).label('count')
    ).filter(
        Scan.started_at >= start_date
    ).group_by(
        func.date(Scan.started_at),
        Scan.status
    ).order_by(
        func.date(Scan.started_at)
    ).all()
    
    # Форматируем данные для фронтенда
    data_by_date = {}
    for record in scan_stats:
        date_str = record.date.strftime('%Y-%m-%d') if hasattr(record.date, 'strftime') else str(record.date)
        if date_str not in data_by_date:
            data_by_date[date_str] = {"completed": 0, "failed": 0, "running": 0}
        if record.status == "completed":
            data_by_date[date_str]["completed"] = record.count
        elif record.status == "failed":
            data_by_date[date_str]["failed"] = record.count
        elif record.status == "running":
            data_by_date[date_str]["running"] = record.count
    
    # Преобразуем в список для графика
    result = []
    for date_str in sorted(data_by_date.keys()):
        result.append({
            "date": date_str,
            "completed": data_by_date[date_str]["completed"],
            "failed": data_by_date[date_str]["failed"],
            "running": data_by_date[date_str]["running"]
        })
    
    return {
        "days": days,
        "data": result
    }

@router.get("/api/stats/top-file-extensions")
async def get_top_file_extensions(
    limit: int = 10,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить топ расширений файлов с Confirmed секретами"""
    
    # Оптимизация: получаем уникальные пути с подсчетом на уровне БД
    import os
    extension_counts = {}
    
    # Получаем уникальные пути и их количество (группировка на уровне БД)
    # ВАЖНО: Сортируем по количеству секретов DESC перед limit(),
    # чтобы брать ТОП-50,000 путей с наибольшим количеством секретов
    # Это гарантирует точную статистику для топ-10 расширений
    paths_with_counts = db.query(
        Secret.path,
        func.count(Secret.id).label('count')
    ).join(
        Scan, Secret.scan_id == Scan.id
    ).filter(
        Scan.status == "completed",
        Secret.status == "Confirmed",
        Secret.is_exception == False,
        Secret.path.isnot(None),
        Secret.path != ''
    ).group_by(Secret.path).order_by(
        func.count(Secret.id).desc()  # Сортируем по количеству секретов (от большего к меньшему)
    ).limit(50000).all()  # Берем топ-50,000 путей - достаточно для точной статистики топ-10 расширений
    
    # Группируем по расширениям
    for path_count in paths_with_counts:
        _, ext = os.path.splitext(path_count.path)
        if not ext:
            ext = ".no_extension"
        extension_counts[ext] = extension_counts.get(ext, 0) + path_count.count
    
    # Сортируем и берем топ
    sorted_extensions = sorted(extension_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    result = [{"extension": ext, "count": count} for ext, count in sorted_extensions]
    
    return {
        "extensions": result
    }

@router.get("/api/stats/confidence-accuracy")
async def get_confidence_accuracy(
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить точность модели по диапазонам confidence"""
    
    # Оптимизация: агрегация на уровне БД через SQL
    # Confidence в диапазоне 0-1, умножаем на 100 для процентов прямо в SQL
    confidence_percent = Secret.confidence * 100.0
    
    # Используем CASE WHEN для группировки по диапазонам в SQL
    confidence_ranges = case(
        (and_(confidence_percent >= 0, confidence_percent < 10), '0-10'),
        (and_(confidence_percent >= 10, confidence_percent < 20), '10-20'),
        (and_(confidence_percent >= 20, confidence_percent < 30), '20-30'),
        (and_(confidence_percent >= 30, confidence_percent < 40), '30-40'),
        (and_(confidence_percent >= 40, confidence_percent < 50), '40-50'),
        (and_(confidence_percent >= 50, confidence_percent < 60), '50-60'),
        (and_(confidence_percent >= 60, confidence_percent < 70), '60-70'),
        (and_(confidence_percent >= 70, confidence_percent < 80), '70-80'),
        (and_(confidence_percent >= 80, confidence_percent < 90), '80-90'),
        (and_(confidence_percent >= 90, confidence_percent <= 100), '90-100'),
        else_='unknown'
    )
    
    # Агрегируем по диапазонам и статусам на уровне БД
    # Используем func.count() - БД выполняет подсчет, а не загружает все записи
    stats = db.query(
        confidence_ranges.label('range'),
        Secret.status,
        func.count(Secret.id).label('count')
    ).join(
        Scan, Secret.scan_id == Scan.id
    ).filter(
        Scan.status == "completed",
        Secret.status.in_(["Confirmed", "Refuted"]),  # Только проверенные
        # Для Confirmed исключаем exceptions, для Refuted включаем все (они все exceptions)
        or_(
            and_(Secret.status == "Confirmed", Secret.is_exception == False),
            Secret.status == "Refuted"
        ),
        Secret.confidence.isnot(None)
    ).group_by(
        confidence_ranges,
        Secret.status
    ).all()
    
    # Форматируем данные - агрегированные данные, не все записи
    range_data = {}
    for stat in stats:
        range_key = stat.range
        if range_key not in range_data:
            range_data[range_key] = {"confirmed": 0, "refuted": 0}
        
        if stat.status == "Confirmed":
            range_data[range_key]["confirmed"] = stat.count
        elif stat.status == "Refuted":
            range_data[range_key]["refuted"] = stat.count
    
    # Создаем список всех диапазонов в правильном порядке
    ranges_order = ['0-10', '10-20', '20-30', '30-40', '40-50', '50-60', '60-70', '70-80', '80-90', '90-100']
    result = []
    for range_name in ranges_order:
        result.append({
            "range": range_name,
            "confirmed": range_data.get(range_name, {}).get("confirmed", 0),
            "refuted": range_data.get(range_name, {}).get("refuted", 0)
        })
    
    return {
        "ranges": result
    }

@router.get("/api/stats/low-confidence-confirmed")
async def get_low_confidence_confirmed(
    limit: int = 400,
    excluded_users: Optional[str] = None,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить топ-50 подтвержденных секретов с наименьшим confidence
       только из последнего completed-скана каждого проекта.
    """
    
    # Parse excluded users list
    excluded_users_list = []
    if excluded_users:
        excluded_users_list = [u.strip() for u in excluded_users.split(',') if u.strip()]
    
    # Подзапрос: выбираем последний completed-скан для каждого проекта
    latest_scans_subq = (
        db.query(
            Scan.project_name,
            func.max(Scan.id).label("latest_scan_id")
        )
        .filter(Scan.status == "completed")
        .group_by(Scan.project_name)
        .subquery()
    )
    
    # Основной запрос: секреты только из последних completed-сканов
    query = db.query(
        Secret.id,
        Secret.path,
        Secret.type,
        Secret.confidence,
        Secret.severity,
        Secret.secret,
        Scan.project_name
    ).join(
        Scan, Secret.scan_id == Scan.id
    ).join(
        latest_scans_subq,
        (latest_scans_subq.c.project_name == Scan.project_name) &
        (latest_scans_subq.c.latest_scan_id == Scan.id)
    ).filter(
        Secret.status == "Confirmed",
        Secret.is_exception == False,
        Secret.confidence.isnot(None)
    )
    
    # Exclude secrets confirmed by excluded users
    if excluded_users_list:
        query = query.filter(~Secret.confirmed_by.in_(excluded_users_list))
    
    secrets = query.order_by(
        Secret.confidence.asc()
    ).limit(limit).all()
    
    result = []
    for secret in secrets:
        if "добавлен вручную" not in secret.secret:
            result.append({
                "id": secret.id,
                "path": secret.path or "",
                "type": secret.type or "Unknown",
                "confidence": round(float(secret.confidence) * 100, 1),
                "severity": secret.severity or "High",
                "secret": secret.secret or "",
                "project_name": secret.project_name or ""
            })
    
    return {
        "secrets": result
    }

@router.get("/api/stats/high-confidence-refuted")
async def get_high_confidence_refuted(
    limit: int = 400,
    excluded_users: Optional[str] = None,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить топ-50 опровергнутых секретов с наивысшим confidence
       только из последних completed-сканов каждого проекта.
    """
    
    # Parse excluded users list
    excluded_users_list = []
    if excluded_users:
        excluded_users_list = [u.strip() for u in excluded_users.split(',') if u.strip()]
    
    # Подзапрос: последние completed-сканы для каждого проекта
    latest_scans_subq = (
        db.query(
            Scan.project_name,
            func.max(Scan.id).label("latest_scan_id")
        )
        .filter(Scan.status == "completed")
        .group_by(Scan.project_name)
        .subquery()
    )
    
    # Основной запрос: секреты только из последних completed-сканов
    query = db.query(
        Secret.id,
        Secret.path,
        Secret.type,
        Secret.confidence,
        Secret.severity,
        Secret.secret,
        Scan.project_name
    ).join(
        Scan, Secret.scan_id == Scan.id
    ).join(
        latest_scans_subq,
        (latest_scans_subq.c.project_name == Scan.project_name) &
        (latest_scans_subq.c.latest_scan_id == Scan.id)
    ).filter(
        Secret.status == "Refuted",
        Secret.confidence.isnot(None)
    )
    
    # Exclude secrets refuted by excluded users
    if excluded_users_list:
        query = query.filter(~Secret.refuted_by.in_(excluded_users_list))
    
    secrets = query.order_by(
        Secret.confidence.desc()
    ).limit(limit).all()
    
    result = []
    for secret in secrets:
        if "добавлен вручную" not in secret.secret:
            result.append({
                "id": secret.id,
                "path": secret.path or "",
                "type": secret.type or "Unknown",
                "confidence": round(float(secret.confidence) * 100, 1),
                "severity": secret.severity or "High",
                "secret": secret.secret or "",
                "project_name": secret.project_name or ""
            })
    
    return {
        "secrets": result
    }

@router.get("/api/stats/users/all")
async def get_all_users_for_stats(
    current_user: str = Depends(get_current_user),
    user_db: Session = Depends(get_user_db)
):
    """Get list of all users for selection (no pagination) - available for authenticated users"""
    try:
        users = user_db.query(User).order_by(User.username).all()
        users_data = [{"username": user.username} for user in users]
        return {"status": "success", "users": users_data}
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )
