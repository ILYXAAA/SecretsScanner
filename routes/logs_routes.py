from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
import os
import logging
from typing import Optional

from services.auth import get_current_user
from services.templates import templates
logger = logging.getLogger("main")

router = APIRouter()

@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, current_user: str = Depends(get_current_user)):
    """Logs page - shows system logs in real-time"""
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "current_user": current_user
    })

@router.get("/api/logs")
async def get_logs(lines: int = 1000, _: str = Depends(get_current_user)):
    """Get main service logs"""
    try:
        log_file_path = "secrets_scanner.log"
        
        if not os.path.exists(log_file_path):
            return {
                "status": "error", 
                "message": "Log file not found",
                "lines": [],
                "size": 0
            }
        
        file_stats = os.stat(log_file_path)
        file_size = file_stats.st_size
        
        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
        
        cleaned_lines = [line.rstrip() for line in all_lines if line.strip()]
        
        if lines > 0:
            log_lines = cleaned_lines[-lines:]
        else:
            log_lines = cleaned_lines
            
        return {
            "status": "success",
            "lines": log_lines,
            "total_lines": len(cleaned_lines),
            "size": file_size,
            "last_modified": file_stats.st_mtime
        }
        
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        return {
            "status": "error",
            "message": str(e),
            "lines": [],
            "size": 0
        }

@router.get("/api/microservice-logs")
async def get_microservice_logs(lines: int = 1000, _: str = Depends(get_current_user)):
    """Get microservice logs"""
    try:
        microservice_log_path = os.getenv("MICROSERVICE_LOG_PATH")
        
        if not microservice_log_path:
            return {
                "status": "error",
                "message": "Microservice log path not configured",
                "lines": [],
                "size": 0
            }
        
        if not os.path.exists(microservice_log_path):
            return {
                "status": "error", 
                "message": "Microservice log file not found",
                "lines": [],
                "size": 0
            }
        
        file_stats = os.stat(microservice_log_path)
        file_size = file_stats.st_size
        
        with open(microservice_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
        
        cleaned_lines = [line.rstrip() for line in all_lines if line.strip()]
        
        if lines > 0:
            log_lines = cleaned_lines[-lines:]
        else:
            log_lines = cleaned_lines
            
        return {
            "status": "success",
            "lines": log_lines,
            "total_lines": len(cleaned_lines),
            "size": file_size,
            "last_modified": file_stats.st_mtime
        }
        
    except Exception as e:
        logger.error(f"Error reading microservice logs: {e}")
        return {
            "status": "error",
            "message": str(e),
            "lines": [],
            "size": 0
        }