from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
import httpx
import logging
import os
from typing import Optional

from config import get_auth_headers
from services.auth import get_current_user
from services.database import get_db
from services.templates import templates

logger = logging.getLogger("main")
user_logger = logging.getLogger("user_actions")

router = APIRouter()

# Get microservice configuration
MICROSERVICE_URL = os.getenv("MICROSERVICE_URL", "http://localhost:8001")
MICROSERVICE_API_KEY = os.getenv("API_KEY")

def get_microservice_headers() -> dict:
    """Get headers for microservice requests"""
    headers = {"Content-Type": "application/json"}
    
    if MICROSERVICE_API_KEY:
        headers["X-API-Key"] = MICROSERVICE_API_KEY
    
    return headers

async def make_microservice_request(method: str, endpoint: str, params: dict = None, timeout: int = 30) -> dict:
    """Make request to microservice with error handling"""
    url = f"{MICROSERVICE_URL}{endpoint}"
    headers = get_microservice_headers()
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, json=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
    except httpx.TimeoutException:
        logger.error(f"Timeout while calling microservice endpoint: {endpoint}")
        raise HTTPException(status_code=504, detail="Microservice request timeout")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling microservice: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Task not found")
        elif e.response.status_code == 403:
            raise HTTPException(status_code=403, detail="Access denied to microservice")
        else:
            raise HTTPException(status_code=e.response.status_code, detail=f"Microservice error: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Request error calling microservice: {str(e)}")
        raise HTTPException(status_code=503, detail="Unable to connect to microservice")
    except Exception as e:
        logger.error(f"Unexpected error calling microservice: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/scan/{scan_id}/status", response_class=HTMLResponse)
async def scan_status_page(
    request: Request, 
    scan_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """Render scan status page with dynamic status updates"""
    try:
        # Получаем базовую информацию о скане из базы данных
        # Предполагается, что у вас есть модель Scan в базе данных
        from models import Scan  # Adjust import as needed
        
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Формируем callback URL для получения статуса через микросервис
        app_host = os.getenv("APP_HOST", "localhost")
        app_port = os.getenv("APP_PORT", "8000")
        callback_url = f"http://{app_host}:{app_port}/get_results/{scan.project_name}/{scan_id}"
        
        user_logger.info(f"User {current_user} accessed scan status page for scan {scan_id}")
        logger.debug(f"Generated callback URL: {callback_url}")
        
        return templates.TemplateResponse("scan_status.html", {
            "request": request,
            "current_user": current_user,
            "scan": scan,
            "callback_url": callback_url
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rendering scan status page for scan {scan_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/task-status")
async def get_task_status_by_callback(
    callback_url: str = Query(..., description="Callback URL задачи"),
    current_user: str = Depends(get_current_user)
):
    """
    Получить статус и прогресс задачи по callback URL через микросервис
    Прокси-эндпоинт для вызова /task_status микросервиса
    """
    try:
        # Вызываем микросервис для получения статуса задачи
        params = {"callback_url": callback_url}
        result = await make_microservice_request("GET", "/task_status", params=params, timeout=10)
        
        user_logger.info(f"User {current_user} requested task status for callback_url: {callback_url}")
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status by callback URL '{callback_url}': {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Failed to get task status: {str(e)}"
            }
        )

@router.get("/scan/{scan_id}/task-status")
async def get_scan_task_status(
    scan_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Получить статус задачи для конкретного скана
    Альтернативный эндпоинт, который автоматически формирует callback_url
    """
    try:
        # Получаем информацию о скане из базы данных
        from models import Scan  # Adjust import as needed
        
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Формируем callback URL
        app_host = os.getenv("APP_HOST", "localhost")
        app_port = os.getenv("APP_PORT", "8000")
        callback_url = f"http://{app_host}:{app_port}/get_results/{scan.project_name}/{scan_id}"
        
        # Вызываем микросервис для получения статуса задачи
        params = {"callback_url": callback_url}
        result = await make_microservice_request("GET", "/task_status", params=params, timeout=10)
        
        user_logger.info(f"User {current_user} requested task status for scan {scan_id}")
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status for scan {scan_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Failed to get task status: {str(e)}"
            }
        )

@router.get("/project/{project_name}/scans/{scan_id}/status")
async def get_project_scan_status(
    project_name: str,
    scan_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    Получить статус задачи по имени проекта и ID скана
    Удобный эндпоинт для получения статуса без обращения к базе данных
    """
    try:
        # Формируем callback URL напрямую
        app_host = os.getenv("APP_HOST", "localhost")
        app_port = os.getenv("APP_PORT", "8000")
        callback_url = f"http://{app_host}:{app_port}/get_results/{project_name}/{scan_id}"
        
        # Вызываем микросервис для получения статуса задачи
        params = {"callback_url": callback_url}
        result = await make_microservice_request("GET", "/task_status", params=params, timeout=10)
        
        user_logger.info(f"User {current_user} requested task status for project {project_name}, scan {scan_id}")
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status for project {project_name}, scan {scan_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Failed to get task status: {str(e)}"
            }
        )

@router.post("/scan/{scan_id}/cancel")
async def cancel_scan(
    scan_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Отменить активное сканирование
    Попытается найти и отменить задачу в микросервисе
    """
    try:
        # Получаем информацию о скане из базы данных
        from models import Scan  # Adjust import as needed
        
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Формируем callback URL
        app_host = os.getenv("APP_HOST", "localhost")
        app_port = os.getenv("APP_PORT", "8000")
        callback_url = f"http://{app_host}:{app_port}/get_results/{scan.project_name}/{scan_id}"
        
        # Сначала получаем статус задачи
        params = {"callback_url": callback_url}
        status_result = await make_microservice_request("GET", "/task_status", params=params, timeout=10)
        
        if status_result.get("status") != "success":
            raise HTTPException(status_code=404, detail="Task not found in microservice")
        
        task_id = status_result.get("task_id")
        current_status = status_result.get("current_status")
        
        # Проверяем, можно ли отменить задачу
        if current_status in ["completed", "failed"]:
            return JSONResponse(
                content={
                    "status": "error",
                    "message": f"Cannot cancel task with status: {current_status}"
                }
            )
        
        # Пытаемся отменить задачу (если у микросервиса есть такой эндпоинт)
        try:
            cancel_result = await make_microservice_request("POST", f"/admin/tasks/{task_id}/cancel", timeout=30)
            user_logger.warning(f"User {current_user} cancelled scan {scan_id} (task {task_id})")
            return JSONResponse(content=cancel_result)
        except HTTPException as e:
            if e.status_code == 404:
                # Если эндпоинта отмены нет, просто возвращаем информацию
                return JSONResponse(
                    content={
                        "status": "info",
                        "message": "Task cancellation endpoint not available. Task will continue running.",
                        "task_id": task_id,
                        "current_status": current_status
                    }
                )
            raise
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling scan {scan_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Failed to cancel scan: {str(e)}"
            }
        )

@router.get("/api/scan-status/{scan_id}")
async def api_get_scan_status(
    scan_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    API эндпоинт для получения статуса скана
    Возвращает JSON с полной информацией о состоянии задачи
    """
    try:
        # Получаем информацию о скане из базы данных
        from models import Scan  # Adjust import as needed
        
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        
        # Формируем callback URL
        app_host = os.getenv("APP_HOST", "localhost")
        app_port = os.getenv("APP_PORT", "8000")
        callback_url = f"http://{app_host}:{app_port}/get_results/{scan.project_name}/{scan_id}"
        
        # Получаем статус из микросервиса
        params = {"callback_url": callback_url}
        microservice_result = await make_microservice_request("GET", "/task_status", params=params, timeout=10)
        
        # Комбинируем данные из базы данных и микросервиса
        from datetime import datetime
        
        combined_result = {
            "scan_id": scan_id,
            "project_name": scan.project_name,
            "callback_url": callback_url,
            "database_status": scan.status if hasattr(scan, 'status') else None,
            "microservice_data": microservice_result,
            "last_updated": datetime.now().isoformat()
        }
        
        return JSONResponse(content=combined_result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting API scan status for {scan_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Failed to get scan status: {str(e)}"
            }
        )