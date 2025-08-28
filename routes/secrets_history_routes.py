from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from datetime import datetime
import json
import html
from models import Project, Scan, Secret
from services.auth import get_current_user
from services.database import get_db
from services.templates import templates
from config import HUB_TYPE

router = APIRouter()

def safe_json_for_html(data):
    """Безопасная сериализация JSON для вставки в HTML"""
    # Сначала сериализуем в JSON
    json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    
    # Затем экранируем только опасные HTML символы, но НЕ кавычки JSON
    json_str = json_str.replace('&', '&amp;')
    json_str = json_str.replace('<', '&lt;')
    json_str = json_str.replace('>', '&gt;')
    # НЕ экранируем кавычки - они нужны для JSON!
    
    return json_str

@router.get("/project/{project_name}/secrets-history", response_class=HTMLResponse)
async def project_secrets_history(request: Request, project_name: str, 
                                current_user: str = Depends(get_current_user), 
                                db: Session = Depends(get_db)):
    """Показать историю всех секретов проекта с поддержкой пагинации и фильтров"""
    
    # Проверяем что проект существует
    project = db.query(Project).filter(Project.name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Получаем только завершенные сканы проекта
    all_scans = db.query(Scan).filter(
        Scan.project_name == project_name,
        Scan.status == "completed"
    ).order_by(Scan.completed_at.asc()).all()
    
    if not all_scans:
        # Нет сканов - возвращаем пустую страницу
        return templates.TemplateResponse("secrets_history.html", {
            "request": request,
            "project": project,
            "secrets_data": [],
            "secrets_json": "[]",
            "secrets_all_json": "[]",
            "total_confirmed": 0,
            "total_all": 0,
            "unique_commits_count": 0,
            "latest_scan": None,
            "HUB_TYPE": HUB_TYPE,
            "current_user": current_user
        })
    
    latest_scan = all_scans[-1]
    
    # ОПТИМИЗАЦИЯ: Получаем все секреты одним запросом с JOIN
    all_secrets_query = db.query(Secret, Scan).join(
        Scan, Secret.scan_id == Scan.id
    ).filter(
        Scan.project_name == project_name,
        Scan.status == "completed"
    ).order_by(Scan.completed_at.asc())
    
    all_secrets_data = all_secrets_query.all()
    
    # ОПТИМИЗАЦИЯ: Получаем активные секреты из последнего скана одним запросом
    latest_scan_active_secrets = set()
    if latest_scan:
        latest_active_secrets = db.query(Secret).filter(
            Secret.scan_id == latest_scan.id,
            Secret.status == "Confirmed"
        ).all()
        
        for secret in latest_active_secrets:
            key = (secret.path or "", secret.line or 0)
            latest_scan_active_secrets.add(key)
    
    # Создаем индекс сканов для быстрого поиска
    scan_index = {scan.id: scan for scan in all_scans}
    
    # ОПТИМИЗАЦИЯ: Группировка секретов
    secrets_map = {}
    
    for secret, scan in all_secrets_data:
        key = (secret.path or "", secret.line or 0)
        
        if key not in secrets_map:
            secrets_map[key] = {
                "id": secret.id,
                "path": secret.path or "",
                "line": secret.line or 0,
                "current_secret": "",
                "current_context": "",
                "severity": secret.severity or "High",
                "type": secret.type or "Unknown",
                "confidence": float(secret.confidence or 1.0),
                "latest_commit": latest_scan.repo_commit if latest_scan else "",
                "timeline": [],
                "commits": set(),
                "scan_ids": set(),
                "has_confirmed": False,
                "found_in_scans": set(),
                "first_found_scan_date": None
            }
        
        # Отмечаем если есть подтвержденные записи
        if secret.status == "Confirmed":
            secrets_map[key]["has_confirmed"] = True
        
        # Запоминаем первое обнаружение
        if secrets_map[key]["first_found_scan_date"] is None:
            secrets_map[key]["first_found_scan_date"] = scan.completed_at or scan.started_at
        
        # Добавляем запись в хронологию
        timeline_entry = {
            "scan_id": scan.id,
            "commit": scan.repo_commit or "",
            "scan_date": (scan.completed_at or scan.started_at).isoformat(),
            "status": secret.status,
            "secret_value": secret.secret or "",
            "context": secret.context or "",
            "confirmed_by": secret.confirmed_by if secret.status == "Confirmed" else None,
            "refuted_by": secret.refuted_by if secret.status == "Refuted" else None,
            "refuted_at": secret.refuted_at.isoformat() if secret.refuted_at else None,
            "exception_comment": secret.exception_comment if secret.status == "Refuted" else None,
            "found_secret": True
        }
        secrets_map[key]["timeline"].append(timeline_entry)
        secrets_map[key]["found_in_scans"].add(scan.id)
        
        if scan.repo_commit:
            secrets_map[key]["commits"].add(scan.repo_commit)
        secrets_map[key]["scan_ids"].add(scan.id)
    
    # ОПТИМИЗАЦИЯ: Добавляем "Not Found" записи только для релевантных сканов
    for key, secret_data in secrets_map.items():
        first_found_date = secret_data["first_found_scan_date"]
        if not first_found_date:
            continue
            
        for scan in all_scans:
            scan_date = scan.completed_at or scan.started_at
            # Добавляем только сканы ПОСЛЕ первого обнаружения
            if scan.id not in secret_data["found_in_scans"] and scan_date >= first_found_date:
                timeline_entry = {
                    "scan_id": scan.id,
                    "commit": scan.repo_commit or "",
                    "scan_date": (scan.completed_at or scan.started_at).isoformat(),
                    "status": "Not Found",
                    "secret_value": "",
                    "context": "",
                    "confirmed_by": None,
                    "refuted_by": None,
                    "refuted_at": None,
                    "exception_comment": None,
                    "found_secret": False
                }
                secret_data["timeline"].append(timeline_entry)
    
    # Обработка финального списка
    secrets_list = []
    secrets_list_all = []
    all_commits = set()
    
    for key, secret_data in secrets_map.items():
        # Сортируем timeline по дате
        secret_data["timeline"].sort(key=lambda x: x["scan_date"])
        
        # Проверяем осмысленность статуса
        has_meaningful_status = any(
            entry["status"] in ["Confirmed", "Refuted"] 
            for entry in secret_data["timeline"]
        )
        
        if not has_meaningful_status:
            continue
        
        # Получаем последнее найденное значение
        last_found_entry = None
        for entry in reversed(secret_data["timeline"]):
            if entry["found_secret"]:
                last_found_entry = entry
                break
        
        if last_found_entry:
            secret_data["current_secret"] = last_found_entry["secret_value"]
            secret_data["current_context"] = last_found_entry["context"]
        
        # Определяем новую логику статуса
        status = "active"
        status_reason = ""
        
        # Проверяем, есть ли секрет в последнем скане
        is_in_latest = key in latest_scan_active_secrets
        
        # Проверяем, был ли когда-либо опровергнут
        was_refuted = any(entry["status"] == "Refuted" for entry in secret_data["timeline"])
        
        if was_refuted:
            status = "refuted"
            status_reason = "refuted"
        elif not is_in_latest:
            # Секрет был подтвержден, но не найден в последнем скане
            status = "resolved"
            status_reason = "resolved"
        
        secret_data["status"] = status
        secret_data["status_reason"] = status_reason
        
        # Определяем кто последний раз подтвердил
        confirmed_by = ""
        for entry in reversed(secret_data["timeline"]):
            if entry["status"] == "Confirmed" and entry["confirmed_by"]:
                confirmed_by = entry["confirmed_by"]
                break
        secret_data["confirmed_by"] = confirmed_by
        
        # ВАЖНО: Конвертируем все set и datetime в JSON-совместимые типы
        secret_data["commits"] = list(secret_data["commits"])
        secret_data["scan_ids"] = list(secret_data["scan_ids"])
        secret_data["found_in_scans"] = list(secret_data["found_in_scans"])
        secret_data["unique_commits"] = list(secret_data["commits"])  # Используем уже конвертированный список
        
        # Конвертируем даты в строки
        secret_data["last_scan_date"] = secret_data["timeline"][-1]["scan_date"] if secret_data["timeline"] else ""
        secret_data["first_scan_date"] = secret_data["timeline"][0]["scan_date"] if secret_data["timeline"] else ""
        
        # Удаляем служебное поле с datetime
        if "first_found_scan_date" in secret_data:
            del secret_data["first_found_scan_date"]
        
        # Добавляем коммиты в общий set
        all_commits.update(secret_data["commits"])
        
        # Добавляем в списки
        secrets_list_all.append(secret_data)
        
        if secret_data["has_confirmed"]:
            secrets_list.append(secret_data)
    
    # Сортируем по дате последнего скана
    secrets_list.sort(key=lambda x: x["last_scan_date"], reverse=True)
    secrets_list_all.sort(key=lambda x: x["last_scan_date"], reverse=True)

    secrets_json = safe_json_for_html(secrets_list)
    secrets_all_json = safe_json_for_html(secrets_list_all)
    
    # JSON для JavaScript - теперь все объекты сериализуемы
    #secrets_json = json.dumps(secrets_list_safe, ensure_ascii=False, separators=(',', ':'))
    #secrets_all_json = json.dumps(secrets_list_all_safe, ensure_ascii=False, separators=(',', ':'))
    
    return templates.TemplateResponse("secrets_history.html", {
        "request": request,
        "project": project,
        "secrets_data": secrets_list,
        "secrets_json": secrets_json,
        "secrets_all_json": secrets_all_json,
        "total_confirmed": len(secrets_list),
        "total_all": len(secrets_list_all),
        "unique_commits_count": len(all_commits),
        "latest_scan": latest_scan,
        "HUB_TYPE": HUB_TYPE,
        "current_user": current_user
    })