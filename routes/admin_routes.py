from fastapi import APIRouter, Request, Form, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_
from dotenv import set_key, load_dotenv
import secrets
import logging
import os
import tempfile
import zipfile
import asyncio
from typing import Dict
import uuid
import re
from services.auth import get_admin_user, get_user_db, get_password_hash
from services.backup_service import create_database_backup, get_backup_status, list_backups
from models import User, Secret, Scan, Project
from services.templates import templates
from services.database import get_db

logger = logging.getLogger("main")

router = APIRouter()

# In-memory storage for download tasks
download_tasks: Dict[str, dict] = {}

def get_current_secret_key():
    """Get current SECRET_KEY from environment"""
    load_dotenv()
    return os.getenv("SECRET_KEY", "Not set")

def update_secret_key_in_env(new_secret_key: str = None):
    """Update SECRET_KEY in .env file"""
    try:
        if not new_secret_key:
            new_secret_key = secrets.token_urlsafe(32)
        
        env_file = ".env"
        set_key(env_file, "SECRET_KEY", new_secret_key)
        load_dotenv(override=True)

        # Update the global SECRET_KEY variable
        from config import SECRET_KEY
        globals()['SECRET_KEY'] = new_secret_key
        
        return True
    except Exception as e:
        logger.error(f"Error updating SECRET_KEY in .env: {e}")
        return False

def filter_and_clean_secrets(secrets_list):
    """Filter and clean secrets list"""
    # Excluded strings
    excluded_strings = [
        "ФАЙЛ НЕ ВЫВЕДЕН ПОЛНОСТЬЮ",
        "СТРОКА НЕ СКАНИРОВАЛАСЬ"
    ]
    
    # Get unique secrets and filter out empty and excluded ones
    unique_secrets = set()
    
    for secret in secrets_list:
        secret_value = secret.secret
        
        # Skip if empty or whitespace only
        if not secret_value or not secret_value.strip():
            continue
            
        # Skip if contains excluded strings
        if any(excluded in secret_value for excluded in excluded_strings):
            continue
        
        # Remove all control characters (ASCII 0-31 and 127)
        # Keep only printable characters (32-126) and basic whitespace (space, tab, newline)
        cleaned_secret = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', secret_value)
        
        # Additional cleanup: remove excessive whitespace and strip
        cleaned_secret = re.sub(r'\s+', ' ', cleaned_secret).strip()
        
        # Skip if empty after cleaning
        if not cleaned_secret:
            continue
            
        # Add to set (automatically handles uniqueness)
        unique_secrets.add(cleaned_secret)
    
    return sorted(list(unique_secrets))

def filter_and_clean_secrets_optimized(secrets_list):
    """Optimized filter and clean secrets list for string inputs"""
    # Excluded strings
    excluded_strings = [
        "ФАЙЛ НЕ ВЫВЕДЕН ПОЛНОСТЬЮ",
        "СТРОКА НЕ СКАНИРОВАЛАСЬ"
    ]
    
    # Get unique secrets and filter out empty and excluded ones
    unique_secrets = set()
    
    for secret_value in secrets_list:
        # Skip if empty or whitespace only
        if not secret_value or not secret_value.strip():
            continue
            
        # Skip if contains excluded strings
        if any(excluded in secret_value for excluded in excluded_strings):
            continue
        
        # Remove all control characters (ASCII 0-31 and 127)
        cleaned_secret = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', secret_value)
        
        # Additional cleanup: remove excessive whitespace and strip
        cleaned_secret = re.sub(r'\s+', ' ', cleaned_secret).strip()
        
        # Skip if empty after cleaning
        if not cleaned_secret:
            continue
            
        # Add to set (automatically handles uniqueness)
        unique_secrets.add(cleaned_secret)
    
    return sorted(list(unique_secrets))

async def prepare_secrets_download(task_id: str, status_filter: str, db_session: Session):
    """Background task to prepare secrets download"""
    # Create new database session for background task
    from services.database import SessionLocal
    db = SessionLocal()
    
    try:
        download_tasks[task_id]["status"] = "processing"
        download_tasks[task_id]["message"] = "Получение секретов из базы данных..."
        
        # Get total count first for progress tracking
        count_query = db.query(Secret)
        if status_filter == "confirmed":
            count_query = count_query.filter(Secret.status == "Confirmed")
        elif status_filter == "refuted":
            count_query = count_query.filter(Secret.status == "Refuted")
        
        total_count = count_query.count()
        
        if total_count == 0:
            download_tasks[task_id]["status"] = "error"
            download_tasks[task_id]["message"] = "Секреты не найдены"
            return
        
        download_tasks[task_id]["message"] = f"Найдено {total_count} записей. Загрузка данных..."
        
        # Process secrets in batches
        batch_size = 5000  # Увеличиваем размер батча
        all_secrets = []
        processed = 0
        
        # Use more efficient query with only needed field
        base_query = db.query(Secret.secret)  # Только поле secret
        if status_filter == "confirmed":
            base_query = base_query.filter(Secret.status == "Confirmed")
        elif status_filter == "refuted":
            base_query = base_query.filter(Secret.status == "Refuted")
        
        # Process in chunks
        for offset in range(0, total_count, batch_size):
            batch = base_query.offset(offset).limit(batch_size).all()
            
            # Extract just the secret values
            batch_secrets = [row.secret for row in batch]
            all_secrets.extend(batch_secrets)
            
            processed += len(batch)
            download_tasks[task_id]["message"] = f"Загружено {processed}/{total_count} записей..."
            
            # Small yield to prevent blocking
            await asyncio.sleep(0.001)
            
            # Break if we got less than batch_size (end of data)
            if len(batch) < batch_size:
                break
        
        download_tasks[task_id]["message"] = f"Загружено {len(all_secrets)} записей. Фильтрация и очистка..."
        
        # Filter and clean secrets - работаем со строками напрямую
        cleaned_secrets = filter_and_clean_secrets_optimized(all_secrets)
        
        if not cleaned_secrets:
            download_tasks[task_id]["status"] = "error"
            download_tasks[task_id]["message"] = "После фильтрации секреты не найдены"
            return
        
        download_tasks[task_id]["message"] = f"Подготовлено {len(cleaned_secrets)} уникальных секретов. Создание файла..."
        
        # Create tmp directory if it doesn't exist
        tmp_dir = "tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        
        # Determine if we need a zip file (threshold: 1000 secrets)
        use_zip = len(cleaned_secrets) > 1000
        
        if use_zip:
            download_tasks[task_id]["message"] = "Создание ZIP архива..."
            zip_path = os.path.join(tmp_dir, f"secrets_{task_id}.zip")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                txt_content = "\n".join(cleaned_secrets)
                zipf.writestr(f"secrets_{status_filter}.txt", txt_content)
            
            download_tasks[task_id]["file_path"] = zip_path
            download_tasks[task_id]["filename"] = f"secrets_{status_filter}.zip"
            download_tasks[task_id]["content_type"] = "application/zip"
        else:
            download_tasks[task_id]["message"] = "Создание TXT файла..."
            txt_path = os.path.join(tmp_dir, f"secrets_{task_id}.txt")
            
            with open(txt_path, 'w', encoding='utf-8') as f:
                for secret_value in cleaned_secrets:
                    f.write(f"{secret_value}\n")
            
            download_tasks[task_id]["file_path"] = txt_path
            download_tasks[task_id]["filename"] = f"secrets_{status_filter}.txt"
            download_tasks[task_id]["content_type"] = "text/plain"
        
        download_tasks[task_id]["status"] = "ready"
        download_tasks[task_id]["message"] = f"Файл готов к скачиванию ({len(cleaned_secrets)} уникальных секретов)"
        
    except Exception as e:
        logger.error(f"Error preparing secrets download: {e}")
        download_tasks[task_id]["status"] = "error"
        download_tasks[task_id]["message"] = f"Ошибка: {str(e)}"
    finally:
        # Always close the database session
        db.close()

@router.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, _: str = Depends(get_admin_user)):
    """Admin panel - only accessible by admin user"""
    current_secret_key = get_current_secret_key()
    if current_secret_key != "Not set":
        current_secret_key = f"{current_secret_key[0:8]}***"
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "current_secret_key": current_secret_key
    })

@router.get("/admin/users")
async def list_users(page: int = 1, _: str = Depends(get_admin_user), 
                    user_db: Session = Depends(get_user_db), db: Session = Depends(get_db)):
    """Get list of all users with pagination and scan statistics"""
    try:
        page_size = 15
        offset = (page - 1) * page_size
        
        # Get total users count
        total_users = user_db.query(User).count()
        total_pages = (total_users + page_size - 1) // page_size
        
        # Get users for current page
        users = user_db.query(User).order_by(User.created_at.desc()).offset(offset).limit(page_size).all()
        
        users_data = []
        for user in users:
            # Count scans by this user
            scan_count = db.query(Scan).filter(Scan.started_by == user.username).count()
            
            # Count projects created by this user
            project_count = db.query(Project).filter(Project.created_by == user.username).count()
            
            users_data.append({
                "username": user.username,
                "created_at": user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else "Unknown",
                "scan_count": scan_count,
                "project_count": project_count
            })
        
        return {
            "status": "success", 
            "users": users_data,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_users": total_users,
                "page_size": page_size
            }
        }
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/admin/create-user")
async def create_user(request: Request, username: str = Form(...), password: str = Form(...),
                     _: str = Depends(get_admin_user), user_db: Session = Depends(get_user_db)):
    """Create new user - admin only"""
    try:
        existing_user = user_db.query(User).filter(User.username == username).first()
        if existing_user:
            return RedirectResponse(url="/secret_scanner/admin?error=user_exists", status_code=302)
        
        password_hash = get_password_hash(password)
        new_user = User(username=username, password_hash=password_hash)
        user_db.add(new_user)
        user_db.commit()
        
        logger.info(f"New user created: {username}")
        return RedirectResponse(url="/secret_scanner/admin?success=user_created", status_code=302)
        
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return RedirectResponse(url="/secret_scanner/admin?error=user_creation_failed", status_code=302)

@router.post("/admin/delete-user/{username}")
async def delete_user(username: str, _: str = Depends(get_admin_user), 
                     user_db: Session = Depends(get_user_db)):
    """Delete user - admin only"""
    try:
        if username == "admin":
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Cannot delete admin user"}
            )
        
        user = user_db.query(User).filter(User.username == username).first()
        if not user:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "User not found"}
            )
        
        user_db.delete(user)
        user_db.commit()
        
        logger.info(f"User deleted: {username}")
        return {"status": "success", "message": "User deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@router.post("/admin/update-secret-key")
async def update_secret_key(request: Request, secret_key: str = Form(""),
                           _: str = Depends(get_admin_user)):
    """Update SECRET_KEY - admin only"""
    try:
        new_key = secret_key.strip() if secret_key.strip() else None
        
        if update_secret_key_in_env(new_key):
            logger.info("SECRET_KEY updated by admin")
            return RedirectResponse(url="/secret_scanner/admin?success=secret_key_updated", status_code=302)
        else:
            return RedirectResponse(url="/secret_scanner/admin?error=secret_key_update_failed", status_code=302)
            
    except Exception as e:
        logger.error(f"Error updating SECRET_KEY: {e}")
        return RedirectResponse(url="/secret_scanner/admin?error=secret_key_update_failed", status_code=302)

@router.post("/admin/export-secrets")
async def export_secrets(background_tasks: BackgroundTasks, status_filter: str = Form(...),
                        _: str = Depends(get_admin_user)):
    """Export secrets - admin only"""
    try:
        if status_filter not in ["all", "confirmed", "refuted"]:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Invalid status filter"}
            )
        
        # Generate unique task ID
        task_id = str(uuid.uuid4())
        
        # Initialize task
        download_tasks[task_id] = {
            "status": "started",
            "message": "Инициализация...",
            "file_path": None,
            "filename": None,
            "content_type": None
        }
        
        # Start background task without passing db session
        background_tasks.add_task(prepare_secrets_download, task_id, status_filter, None)
        
        return {"status": "success", "task_id": task_id}
        
    except Exception as e:
        logger.error(f"Error starting export: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )
@router.get("/admin/export-status/{task_id}")
async def export_status(task_id: str, _: str = Depends(get_admin_user)):
    """Check export status"""
    if task_id not in download_tasks:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Task not found"}
        )
    
    task = download_tasks[task_id]
    return {
        "status": task["status"],
        "message": task["message"]
    }

@router.get("/admin/download/{task_id}")
async def download_secrets(task_id: str, _: str = Depends(get_admin_user)):
    """Download prepared secrets file"""
    if task_id not in download_tasks:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Task not found"}
        )
    
    task = download_tasks[task_id]
    
    if task["status"] != "ready":
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "File not ready"}
        )
    
    if not os.path.exists(task["file_path"]):
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "File not found"}
        )
    
    try:
        # Return file and clean up task
        response = FileResponse(
            path=task["file_path"],
            filename=task["filename"],
            media_type=task["content_type"]
        )
        
        # Schedule cleanup
        async def cleanup():
            await asyncio.sleep(5)  # Wait 5 seconds before cleanup
            try:
                if os.path.exists(task["file_path"]):
                    os.remove(task["file_path"])
                if task_id in download_tasks:
                    del download_tasks[task_id]
            except Exception as e:
                logger.error(f"Error cleaning up download file: {e}")
        
        asyncio.create_task(cleanup())
        
        return response
        
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@router.get("/admin/backup-status")
async def backup_status(_: bool = Depends(get_admin_user)):
    """Get backup configuration and status"""
    response_data = get_backup_status()
    
    return JSONResponse(
        content=response_data,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@router.post("/admin/backup")
async def manual_backup(_: bool = Depends(get_admin_user)):
    """Manually trigger a database backup"""
    backup_path = create_database_backup()
    if backup_path:
        return {"status": "success", "message": f"Backup created: {os.path.basename(backup_path)}"}
    else:
        return {"status": "error", "message": "Backup failed"}

@router.get("/admin/backups")
async def list_backups_route(_: bool = Depends(get_admin_user)):
    """List available backups"""
    return list_backups()