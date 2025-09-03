from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, FileResponse
import os
import logging
import tempfile
from typing import Optional
from datetime import datetime, date
import re

from services.auth import get_current_user
from services.templates import templates
logger = logging.getLogger("main")
user_logger = logging.getLogger("user_actions")

router = APIRouter()

@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, current_user: str = Depends(get_current_user)):
    """Logs page - shows system logs in real-time"""
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "current_user": current_user
    })

def preprocess_log_lines(lines):
    """Предобработка логов: объединение многострочных записей"""
    if not lines:
        return []
    
    processed_lines = []
    current_log_entry = None
    log_pattern = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')
    
    for line in lines:
        line = line.rstrip()
        if not line:
            continue
            
        # Проверяем, начинается ли строка с timestamp
        if log_pattern.match(line):
            # Если есть накопленная запись, добавляем её
            if current_log_entry:
                processed_lines.append(current_log_entry)
            # Начинаем новую запись
            current_log_entry = line
        else:
            # Это продолжение предыдущей записи
            if current_log_entry:
                current_log_entry += "\n" + line
            else:
                # Если нет предыдущей записи, создаем как есть
                processed_lines.append(line)
    
    # Добавляем последнюю накопленную запись
    if current_log_entry:
        processed_lines.append(current_log_entry)
    
    return processed_lines

def filter_logs_by_date(lines, start_date: Optional[date] = None, end_date: Optional[date] = None):
    """Фильтрация логов по датам"""
    if not start_date and not end_date:
        return lines
    
    filtered_lines = []
    log_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2})')
    
    for line in lines:
        match = log_pattern.match(line)
        if match:
            try:
                log_date = datetime.strptime(match.group(1), '%Y-%m-%d').date()
                
                # Проверяем диапазон дат
                if start_date and log_date < start_date:
                    continue
                if end_date and log_date > end_date:
                    continue
                    
                filtered_lines.append(line)
            except ValueError:
                # Если не удалось распарсить дату, включаем строку
                filtered_lines.append(line)
        else:
            # Строки без даты включаем (они могут быть частью многострочных записей)
            filtered_lines.append(line)
    
    return filtered_lines

@router.get("/api/logs")
async def get_logs(
    lines: int = 1000, 
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    _: str = Depends(get_current_user)
):
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
        
        # Предобработка логов
        processed_lines = preprocess_log_lines(all_lines)
        
        # Фильтрация по датам
        if start_date or end_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
                processed_lines = filter_logs_by_date(processed_lines, start_date_obj, end_date_obj)
            except ValueError as e:
                return {
                    "status": "error",
                    "message": f"Invalid date format: {e}",
                    "lines": [],
                    "size": 0
                }
        
        # Применяем ограничение по количеству строк
        if lines > 0:
            log_lines = processed_lines[-lines:]
        else:
            log_lines = processed_lines
            
        return {
            "status": "success",
            "lines": log_lines,
            "total_lines": len(processed_lines),
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

@router.get("/api/download-logs")
async def download_logs(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user)
):
    """Download main service logs as file"""
    try:
        log_file_path = "secrets_scanner.log"
        
        if not os.path.exists(log_file_path):
            return {
                "status": "error",
                "message": "Log file not found"
            }
        
        # Generate filename with current timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # If date filtering is requested, process the logs
        if start_date or end_date:
            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
            
            processed_lines = preprocess_log_lines(all_lines)
            
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
                filtered_lines = filter_logs_by_date(processed_lines, start_date_obj, end_date_obj)
            except ValueError as e:
                return {
                    "status": "error",
                    "message": f"Invalid date format: {e}"
                }
            
            # Create temporary file with filtered content
            temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log', encoding='utf-8')
            temp_file.write('\n'.join(filtered_lines))
            temp_file.close()
            
            # Generate filename with date range
            date_suffix = ""
            if start_date and end_date:
                date_suffix = f"_{start_date}_to_{end_date}"
            elif start_date:
                date_suffix = f"_from_{start_date}"
            elif end_date:
                date_suffix = f"_until_{end_date}"
            
            filename = f"secrets_scanner{date_suffix}_{timestamp}.log"
            user_logger.warning(f"Log file '{filename}' exported by user '{current_user}' (.log)")

            return FileResponse(
                path=temp_file.name,
                filename=filename,
                media_type='text/plain',
                background=lambda: os.unlink(temp_file.name)  # Delete temp file after sending
            )
        else:
            # Return original file
            filename = f"secrets_scanner_{timestamp}.log"
            user_logger.warning(f"Log file '{filename}' exported by user '{current_user}' (.log)")
            return FileResponse(
                path=log_file_path,
                filename=filename,
                media_type='text/plain'
            )
        
    except Exception as e:
        logger.error(f"Error downloading logs: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

@router.get("/api/download-microservice-logs")
async def download_microservice_logs(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user)
):
    """Download microservice logs as file"""
    try:
        microservice_log_path = os.getenv("MICROSERVICE_LOG_PATH")
        
        if not microservice_log_path:
            return {
                "status": "error",
                "message": "Microservice log path not configured"
            }
        
        if not os.path.exists(microservice_log_path):
            return {
                "status": "error",
                "message": "Microservice log file not found"
            }
        
        # Generate filename with current timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # If date filtering is requested, process the logs
        if start_date or end_date:
            with open(microservice_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
            
            processed_lines = preprocess_log_lines(all_lines)
            
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
                filtered_lines = filter_logs_by_date(processed_lines, start_date_obj, end_date_obj)
            except ValueError as e:
                return {
                    "status": "error",
                    "message": f"Invalid date format: {e}"
                }
            
            # Create temporary file with filtered content
            temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log', encoding='utf-8')
            temp_file.write('\n'.join(filtered_lines))
            temp_file.close()
            
            # Generate filename with date range
            date_suffix = ""
            if start_date and end_date:
                date_suffix = f"_{start_date}_to_{end_date}"
            elif start_date:
                date_suffix = f"_from_{start_date}"
            elif end_date:
                date_suffix = f"_until_{end_date}"
            
            filename = f"microservice{date_suffix}_{timestamp}.log"
            user_logger.warning(f"Log file '{filename}' exported by user '{current_user}' (.log)")

            return FileResponse(
                path=temp_file.name,
                filename=filename,
                media_type='text/plain',
                background=lambda: os.unlink(temp_file.name)  # Delete temp file after sending
            )
        else:
            # Return original file
            filename = f"microservice_{timestamp}.log"
            user_logger.warning(f"Log file '{filename}' exported by user '{current_user}' (.log)")

            return FileResponse(
                path=microservice_log_path,
                filename=filename,
                media_type='text/plain'
            )
        
    except Exception as e:
        logger.error(f"Error downloading microservice logs: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

@router.get("/api/microservice-logs")
async def get_microservice_logs(
    lines: int = 1000, 
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    _: str = Depends(get_current_user)
):
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
        
        # Предобработка логов
        processed_lines = preprocess_log_lines(all_lines)
        
        # Фильтрация по датам
        if start_date or end_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
                processed_lines = filter_logs_by_date(processed_lines, start_date_obj, end_date_obj)
            except ValueError as e:
                return {
                    "status": "error",
                    "message": f"Invalid date format: {e}",
                    "lines": [],
                    "size": 0
                }
        
        # Применяем ограничение по количеству строк
        if lines > 0:
            log_lines = processed_lines[-lines:]
        else:
            log_lines = processed_lines
            
        return {
            "status": "success",
            "lines": log_lines,
            "total_lines": len(processed_lines),
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

@router.get("/api/user-actions-logs")
async def get_user_actions_logs(
    lines: int = 1000, 
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    _: str = Depends(get_current_user)
):
    """Get user actions logs"""
    try:
        log_file_path = "user_actions.log"
        
        if not os.path.exists(log_file_path):
            return {
                "status": "error", 
                "message": "User actions log file not found",
                "lines": [],
                "size": 0
            }
        
        file_stats = os.stat(log_file_path)
        file_size = file_stats.st_size
        
        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
        
        # Предобработка логов
        processed_lines = preprocess_log_lines(all_lines)
        
        # Фильтрация по датам
        if start_date or end_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
                processed_lines = filter_logs_by_date(processed_lines, start_date_obj, end_date_obj)
            except ValueError as e:
                return {
                    "status": "error",
                    "message": f"Invalid date format: {e}",
                    "lines": [],
                    "size": 0
                }
        
        # Применяем ограничение по количеству строк
        if lines > 0:
            log_lines = processed_lines[-lines:]
        else:
            log_lines = processed_lines
            
        return {
            "status": "success",
            "lines": log_lines,
            "total_lines": len(processed_lines),
            "size": file_size,
            "last_modified": file_stats.st_mtime
        }
        
    except Exception as e:
        logger.error(f"Error reading user actions logs: {e}")
        return {
            "status": "error",
            "message": str(e),
            "lines": [],
            "size": 0
        }

@router.get("/api/download-user-actions-logs")
async def download_user_actions_logs(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user)
):
    """Download user actions logs as file"""
    try:
        log_file_path = "user_actions.log"
        
        if not os.path.exists(log_file_path):
            return {
                "status": "error",
                "message": "User actions log file not found"
            }
        
        # Generate filename with current timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # If date filtering is requested, process the logs
        if start_date or end_date:
            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
            
            processed_lines = preprocess_log_lines(all_lines)
            
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
                filtered_lines = filter_logs_by_date(processed_lines, start_date_obj, end_date_obj)
            except ValueError as e:
                return {
                    "status": "error",
                    "message": f"Invalid date format: {e}"
                }
            
            # Create temporary file with filtered content
            temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log', encoding='utf-8')
            temp_file.write('\n'.join(filtered_lines))
            temp_file.close()
            
            # Generate filename with date range
            date_suffix = ""
            if start_date and end_date:
                date_suffix = f"_{start_date}_to_{end_date}"
            elif start_date:
                date_suffix = f"_from_{start_date}"
            elif end_date:
                date_suffix = f"_until_{end_date}"
            
            filename = f"user_actions{date_suffix}_{timestamp}.log"
            user_logger.warning(f"Log file '{filename}' exported by user '{current_user}' (.log)")

            return FileResponse(
                path=temp_file.name,
                filename=filename,
                media_type='text/plain',
                background=lambda: os.unlink(temp_file.name)  # Delete temp file after sending
            )
        else:
            # Return original file
            filename = f"user_actions_{timestamp}.log"
            user_logger.warning(f"Log file '{filename}' exported by user '{current_user}' (.log)")
            return FileResponse(
                path=log_file_path,
                filename=filename,
                media_type='text/plain'
            )
        
    except Exception as e:
        logger.error(f"Error downloading user actions logs: {e}")
        return {
            "status": "error",
            "message": str(e)
        }