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
import json
from datetime import datetime

logger = logging.getLogger("main")

router = APIRouter()

# In-memory storage for download tasks
download_tasks: Dict[str, dict] = {}
projects_download_tasks: Dict[str, dict] = {}

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
async def admin_panel(request: Request, current_user: str = Depends(get_admin_user)):
    """Admin panel - only accessible by admin user"""
    current_secret_key = get_current_secret_key()
    if current_secret_key != "Not set":
        current_secret_key = f"{current_secret_key[0:8]}***"
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "current_secret_key": current_secret_key,
        "current_user": current_user
    })

@router.get("/admin/users")
async def list_users(page: int = 1, search: str = "", _: str = Depends(get_admin_user), 
                    user_db: Session = Depends(get_user_db), db: Session = Depends(get_db)):
    """Get list of all users with pagination, search and scan statistics"""
    try:
        page_size = 15
        offset = (page - 1) * page_size
        
        # Base query
        query = user_db.query(User)
        
        # Apply search filter
        if search.strip():
            query = query.filter(User.username.ilike(f"%{search.strip()}%"))
        
        # Get total users count with search applied
        total_users = query.count()
        total_pages = (total_users + page_size - 1) // page_size
        
        # Get users for current page
        users = query.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()
        
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
        username = username.replace(":", ".").replace("/", ".")
        new_user = User(username=username, password_hash=password_hash)
        user_db.add(new_user)
        user_db.commit()
        
        logger.warning(f"New user created: '{username}'")
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
        
        logger.warning(f"User deleted: '{username}'")
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
            logger.warning("SECRET_KEY updated by 'admin'")
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

@router.get("/admin/api-tokens")
async def list_api_tokens(page: int = 1, search: str = "", _: str = Depends(get_admin_user), db: Session = Depends(get_db)):
    """Get list of all API tokens with pagination and search"""
    try:
        from models import ApiToken
        
        page_size = 10
        offset = (page - 1) * page_size
        
        # Base query
        query = db.query(ApiToken)
        
        # Apply search filter
        if search.strip():
            query = query.filter(ApiToken.name.ilike(f"%{search.strip()}%"))
        
        # Get total tokens count with search applied
        total_tokens = query.count()
        total_pages = (total_tokens + page_size - 1) // page_size
        
        # Get tokens for current page
        tokens = query.order_by(ApiToken.created_at.desc()).offset(offset).limit(page_size).all()
        
        tokens_data = []
        for token in tokens:
            # Parse permissions
            try:
                permissions = json.loads(token.permissions)
            except:
                permissions = {}
            
            tokens_data.append({
                "id": token.id,
                "name": token.name,
                "prefix": token.prefix,
                "created_by": token.created_by,
                "created_at": token.created_at.strftime("%d.%m.%Y %H:%M") if token.created_at else "Unknown",
                "expires_at": token.expires_at.strftime("%d.%m.%Y %H:%M") if token.expires_at else None,
                "last_used_at": token.last_used_at.strftime("%d.%m.%Y %H:%M") if token.last_used_at else "Never",
                "is_active": token.is_active,
                "permissions": permissions,
                "requests_per_minute": token.requests_per_minute,
                "requests_per_hour": token.requests_per_hour,
                "requests_per_day": token.requests_per_day
            })
        
        return {
            "status": "success", 
            "tokens": tokens_data,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_tokens": total_tokens,
                "page_size": page_size
            }
        }
        
    except Exception as e:
        logger.error(f"Error listing API tokens: {e}")
        return {"status": "error", "message": str(e)}
    
@router.post("/admin/create-api-token")
async def create_api_token(
    request: Request, 
    name: str = Form(...),
    expires_days: int = Form(default=365),
    permissions: str = Form(default="{}"),
    requests_per_minute: int = Form(default=60),
    requests_per_hour: int = Form(default=1000),
    requests_per_day: int = Form(default=10000),
    admin_user: str = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Create new API token - admin only"""
    try:
        from models import ApiToken
        from api.utils import generate_api_token, get_token_prefix, validate_permissions
        from datetime import timedelta
        
        # Check if token with this name already exists
        existing_token = db.query(ApiToken).filter(ApiToken.name == name).first()
        if existing_token:
            return RedirectResponse(url="/secret_scanner/admin?error=api_token_exists", status_code=302)
        
        # Generate token
        full_token, token_hash = generate_api_token()
        token_prefix = get_token_prefix(full_token)
        
        # Parse and validate permissions
        try:
            permissions_dict = json.loads(permissions)
            permissions_dict = validate_permissions(permissions_dict)
        except:
            permissions_dict = {"project_add": False, "project_check": True, "scan": False, "multi_scan": False, "scan_results": True}
        
        # Calculate expiration date
        expires_at = None
        if expires_days > 0:
            expires_at = datetime.now() + timedelta(days=expires_days)
        
        # Create token record
        api_token = ApiToken(
            name=name,
            token_hash=token_hash,
            prefix=token_prefix,
            created_by=admin_user,
            expires_at=expires_at,
            is_active=True,
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
            requests_per_day=requests_per_day,
            permissions=json.dumps(permissions_dict)
        )
        
        db.add(api_token)
        db.commit()
        
        logger.warning(f"API token created: '{name}' by '{admin_user}'")
        
        # Redirect with token in query param for display (one-time only)
        import urllib.parse
        encoded_token = urllib.parse.quote(full_token)
        return RedirectResponse(
            url=f"/secret_scanner/admin?success=api_token_created&token={encoded_token}&token_name={urllib.parse.quote(name)}", 
            status_code=302
        )
        
    except Exception as e:
        logger.error(f"Error creating API token: {e}")
        return RedirectResponse(url="/secret_scanner/admin?error=api_token_creation_failed", status_code=302)

@router.post("/admin/delete-api-token/{token_id}")
async def delete_api_token(
    token_id: int, 
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Delete API token - admin only"""
    try:
        from models import ApiToken, ApiUsage
        
        token = db.query(ApiToken).filter(ApiToken.id == token_id).first()
        if not token:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "API token not found"}
            )
        
        token_name = token.name
        
        # Delete related usage records
        db.query(ApiUsage).filter(ApiUsage.token_id == token_id).delete()
        
        # Delete token
        db.delete(token)
        db.commit()
        
        logger.warning(f"API token deleted: '{token_name}'")
        return {"status": "success", "message": "API token deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting API token: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@router.post("/admin/toggle-api-token/{token_id}")
async def toggle_api_token(
    token_id: int,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Toggle API token active status - admin only"""
    try:
        from models import ApiToken
        
        token = db.query(ApiToken).filter(ApiToken.id == token_id).first()
        if not token:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "API token not found"}
            )
        
        token.is_active = not token.is_active
        db.commit()
        
        status = "activated" if token.is_active else "deactivated"
        logger.warning(f"API token '{status}': '{token.name}'")
        
        return {"status": "success", "message": f"API token {status} successfully", "is_active": token.is_active}
        
    except Exception as e:
        logger.error(f"Error toggling API token: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

def create_projects_html_report(projects_data: list, technologies: list) -> str:
    """Create HTML report for projects with technologies"""
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отчет по проектам с технологиями</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 20px;
            background: #f8f9fa;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #28a745;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .summary {{
            background: #e8f5e8;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            border-left: 4px solid #28a745;
        }}
        .summary h3 {{
            margin-top: 0;
            color: #155724;
        }}
        .project {{
            background: #f8f9fa;
            margin: 20px 0;
            padding: 25px;
            border-radius: 8px;
            border-left: 4px solid #007bff;
            border: 1px solid #dee2e6;
        }}
        .project-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .project-name {{
            font-size: 1.4em;
            font-weight: 600;
            color: #333;
        }}
        .project-url {{
            font-family: monospace;
            background: #e9ecef;
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 0.9em;
        }}
        .project-url a {{
            color: #007bff;
            text-decoration: none;
        }}
        .project-url a:hover {{
            text-decoration: underline;
        }}
        .tech-section {{
            margin: 15px 0;
        }}
        .tech-title {{
            font-weight: 600;
            color: #495057;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .tech-badge {{
            display: inline-block;
            background: #007bff;
            color: white;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 0.85em;
            margin: 3px;
            font-weight: 500;
        }}
        .framework-details {{
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin: 15px 0;
            border: 1px solid #dee2e6;
        }}
        .detection-item {{
            margin: 8px 0;
            padding: 8px;
            background: #f1f3f4;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.9em;
            word-break: break-all;
        }}
        .language-stats {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 15px;
        }}
        .language-item {{
            background: white;
            padding: 8px 12px;
            border-radius: 6px;
            border: 1px solid #dee2e6;
            font-size: 0.9em;
            min-width: 120px;
        }}
        .percentage {{
            color: #28a745;
            font-weight: 600;
        }}
        .meta-info {{
            color: #6c757d;
            font-size: 0.9em;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #dee2e6;
        }}
        .no-projects {{
            text-align: center;
            color: #6c757d;
            font-style: italic;
            padding: 40px;
            background: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #dee2e6;
        }}
        .icon {{
            font-style: normal;
        }}
        /* Collapsible sections */
        .collapsible {{
            cursor: pointer;
            padding: 12px 15px;
            background: #ffffff;
            border: 1px solid #007bff;
            border-radius: 6px;
            margin: 15px 0 0 0;
            user-select: none;
            transition: all 0.3s ease;
            color: #007bff;
            font-weight: 500;
        }}
        .collapsible:hover {{
            background: #e7f3ff;
            border-color: #0056b3;
        }}
        .collapsible.active {{
            background: #007bff;
            color: white;
            border-color: #0056b3;
        }}
        .collapsible-content {{
            display: none;
            padding: 20px;
            background: white;
            border: 1px solid #007bff;
            border-top: none;
            border-radius: 0 0 6px 6px;
            margin-bottom: 0;
        }}
        .collapsible-content.active {{
            display: block;
        }}
        .chevron {{
            float: right;
            transition: transform 0.3s ease;
            font-weight: bold;
        }}
        .chevron.down {{
            transform: rotate(180deg);
        }}
        .control-button {{
            background: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9em;
            font-weight: 500;
            transition: background-color 0.2s;
        }}
        .control-button:hover {{
            background: #0056b3;
        }}
        .section-divider {{
            border-top: 2px solid #dee2e6;
            margin: 25px 0 15px 0;
            padding-top: 15px;
        }}
        @media (max-width: 768px) {{
            .project-header {{
                flex-direction: column;
                align-items: flex-start;
            }}
            .language-stats {{
                flex-direction: column;
            }}
            .language-item {{
                min-width: auto;
                width: 100%;
            }}
            .container {{
                margin: 10px;
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Отчет по проектам с технологиями</h1>
        
        <div class="summary">
            <h3>📋 Сводка</h3>
            <p><strong>Искомые технологии:</strong> {technologies_str}</p>
            <p><strong>Найдено проектов:</strong> {total_projects}</p>
            <p><strong>Дата создания отчета:</strong> {report_date}</p>
            
            <div style="margin-top: 20px;">
                <button onclick="toggleAllDetails()" class="control-button">
                    📊 Показать/скрыть всю дополнительную информацию
                </button>
            </div>
        </div>
        
        {projects_html}
    </div>
    
    <script>
        let allExpanded = false;
        
        function toggleCollapsible(element) {{
            const content = element.nextElementSibling;
            const chevron = element.querySelector('.chevron');
            
            element.classList.toggle('active');
            content.classList.toggle('active');
            chevron.classList.toggle('down');
        }}
        
        function toggleAllDetails() {{
            const collapsibles = document.querySelectorAll('.collapsible');
            const contents = document.querySelectorAll('.collapsible-content');
            const chevrons = document.querySelectorAll('.chevron');
            
            allExpanded = !allExpanded;
            
            collapsibles.forEach(function(collapsible) {{
                if (allExpanded) {{
                    collapsible.classList.add('active');
                }} else {{
                    collapsible.classList.remove('active');
                }}
            }});
            
            contents.forEach(function(content) {{
                if (allExpanded) {{
                    content.classList.add('active');
                }} else {{
                    content.classList.remove('active');
                }}
            }});
            
            chevrons.forEach(function(chevron) {{
                if (allExpanded) {{
                    chevron.classList.add('down');
                }} else {{
                    chevron.classList.remove('down');
                }}
            }});
        }}
        
        // Add click handlers to all collapsible elements
        document.addEventListener('DOMContentLoaded', function() {{
            const collapsibles = document.querySelectorAll('.collapsible');
            collapsibles.forEach(function(collapsible) {{
                collapsible.addEventListener('click', function() {{
                    toggleCollapsible(this);
                }});
            }});
        }});
    </script>
</body>
</html>"""
    
    if not projects_data:
        projects_html = '<div class="no-projects">📭 Проекты с указанными технологиями не найдены</div>'
    else:
        projects_html = ""
        
        for project_info in projects_data:
            project = project_info['project']
            latest_scan = project_info['latest_scan']
            language_stats = project_info['language_stats']
            framework_stats = project_info['framework_stats']
            matched_techs = project_info['matched_technologies']
            
            # Формируем HTML для проекта
            project_html = f"""
        <div class="project">
            <div class="project-header">
                <div class="project-name">🚀 {project.name}</div>
                <div class="project-url"><a href="{project.repo_url}" target="_blank" rel="noopener">{project.repo_url}</a></div>
            </div>
            
            <div class="tech-section">
                <div class="tech-title">🎯 Найденные технологии:</div>
                <div>"""
            
            for tech in matched_techs:
                project_html += f'<span class="tech-badge">{tech}</span>'
            
            project_html += """
                </div>
            </div>"""
            
            # Проверяем есть ли дополнительная информация для показа
            has_framework_details = framework_stats and any(
                framework.lower() in [tech.lower() for tech in matched_techs] 
                for framework in framework_stats.keys()
            )
            
            has_additional_info = has_framework_details or language_stats
            
            # Если есть дополнительная информация, добавляем сворачиваемую секцию
            if has_additional_info:
                project_html += """
            <div class="collapsible">
                <span>📊 Дополнительная информация</span>
                <span class="chevron">▼</span>
            </div>
            <div class="collapsible-content">"""
                
                # Добавляем детали по фреймворкам
                if has_framework_details:
                    project_html += """
                <div class="tech-title">🔧 Детали по фреймворкам:</div>"""
                    
                    for framework, details in framework_stats.items():
                        if framework.lower() in [tech.lower() for tech in matched_techs]:
                            project_html += f"""
                <div class="framework-details">
                    <strong>📦 {framework}</strong>
                    <div style="margin-top: 8px;">
                        <em>Обнаружения ({len(details['detections'])} файлов):</em>"""
                            
                            for detection in details['detections']:
                                project_html += f'<div class="detection-item">📄 {detection}</div>'
                            
                            project_html += """
                    </div>
                </div>"""
                
                # Добавляем статистику по языкам
                if language_stats:
                    # Добавляем разделитель если есть и фреймворки и языки
                    if has_framework_details:
                        project_html += '<div class="section-divider"></div>'
                    
                    project_html += """
                <div class="tech-title">💻 Статистика по языкам:</div>
                <div class="language-stats">"""
                    
                    for lang_stat in language_stats:
                        icon = lang_stat.get('icon', '📄')
                        project_html += f"""
                <div class="language-item">
                    <span class="icon">{icon}</span> <strong>{lang_stat['language']}</strong>
                    <div><span class="percentage">{lang_stat['percentage']}%</span></div>
                    <small>{lang_stat['count']} файлов</small>
                </div>"""
                    
                    project_html += """
                </div>"""
                
                project_html += """
            </div>"""
            
            # Метаинформация
            scan_date = latest_scan.started_at.strftime("%d.%m.%Y %H:%M") if latest_scan and latest_scan.started_at else "Неизвестно"
            created_date = project.created_at.strftime("%d.%m.%Y") if project.created_at else "Неизвестно"
            
            project_html += f"""
            <div class="meta-info">
                ℹ️ <strong>Создан:</strong> {created_date} | 
                <strong>Автор:</strong> {project.created_by} | 
                <strong>Последнее сканирование:</strong> {scan_date}
            </div>
        </div>"""
            
            projects_html += project_html
    
    from datetime import datetime
    return html_template.format(
        technologies_str=", ".join(technologies),
        total_projects=len(projects_data),
        report_date=datetime.now().strftime("%d.%m.%Y %H:%M"),
        projects_html=projects_html
    )

async def prepare_projects_download(task_id: str, technologies: list):
    """Background task to prepare projects download"""
    from services.database import SessionLocal
    db = SessionLocal()
    
    try:
        projects_download_tasks[task_id]["status"] = "processing"
        projects_download_tasks[task_id]["message"] = "Поиск проектов с указанными технологиями..."
        
        # Получаем все проекты с их последними сканами
        projects = db.query(Project).all()
        matched_projects = []
        processed_count = 0
        
        projects_download_tasks[task_id]["message"] = f"Проверка {len(projects)} проектов..."
        
        for project in projects:
            processed_count += 1
            
            # Получаем последний скан для проекта
            latest_scan = db.query(Scan).filter(
                Scan.project_name == project.name
            ).order_by(Scan.started_at.desc()).first()
            
            if not latest_scan:
                continue
            
            # Проверяем языки и фреймворки
            matched_technologies = []
            language_stats = []
            framework_stats = {}
            
            # Получаем статистику языков
            if latest_scan.detected_languages:
                try:
                    detected_languages = json.loads(latest_scan.detected_languages)
                    # Проверяем языки
                    for lang_name in detected_languages.keys():
                        if lang_name.lower() in [tech.lower() for tech in technologies]:
                            matched_technologies.append(lang_name)
                    
                    # Формируем статистику для отчета
                    language_stats = get_language_stats_from_project_scan(latest_scan)
                        
                except json.JSONDecodeError:
                    pass
            
            # Получаем статистику фреймворков
            if latest_scan.detected_frameworks:
                try:
                    detected_frameworks = json.loads(latest_scan.detected_frameworks)
                    # Проверяем фреймворки
                    for fw_name in detected_frameworks.keys():
                        if fw_name.lower() in [tech.lower() for tech in technologies]:
                            matched_technologies.append(fw_name)
                    
                    # Формируем статистику для отчета
                    framework_stats = get_framework_stats_from_project_scan(latest_scan)
                        
                except json.JSONDecodeError:
                    pass
            
            if matched_technologies:
                matched_projects.append({
                    'project': project,
                    'latest_scan': latest_scan,
                    'language_stats': language_stats,
                    'framework_stats': framework_stats,
                    'matched_technologies': list(set(matched_technologies))  # убираем дубликаты
                })
            
            # Обновляем прогресс каждые 10 проектов
            if processed_count % 10 == 0:
                projects_download_tasks[task_id]["message"] = f"Обработано {processed_count}/{len(projects)} проектов. Найдено: {len(matched_projects)}"
        
        if not matched_projects:
            projects_download_tasks[task_id]["status"] = "error"
            projects_download_tasks[task_id]["message"] = "Проекты с указанными технологиями не найдены"
            return
        
        projects_download_tasks[task_id]["message"] = f"Найдено {len(matched_projects)} проектов. Создание HTML отчета..."
        
        # Создаем HTML отчет
        html_content = create_projects_html_report(matched_projects, technologies)
        
        # Сохраняем файл
        tmp_dir = "tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        html_path = os.path.join(tmp_dir, f"projects_report_{task_id}.html")
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        projects_download_tasks[task_id]["file_path"] = html_path
        projects_download_tasks[task_id]["filename"] = f"projects_technologies_report.html"
        projects_download_tasks[task_id]["content_type"] = "text/html"
        projects_download_tasks[task_id]["status"] = "ready"
        projects_download_tasks[task_id]["message"] = f"Отчет готов к скачиванию ({len(matched_projects)} проектов)"
        
    except Exception as e:
        logger.error(f"Error preparing projects download: {e}")
        projects_download_tasks[task_id]["status"] = "error"
        projects_download_tasks[task_id]["message"] = f"Ошибка: {str(e)}"
    finally:
        db.close()

def get_language_stats_from_project_scan(scan):
    """Get language statistics from scan - копия функции из project_routes.py"""
    if not scan.detected_languages:
        return []
    
    try:
        detected_languages = json.loads(scan.detected_languages)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse detected_languages for scan {scan.id}")
        return []
    
    if not detected_languages:
        return []
    
    # Загружаем паттерны языков (упрощенная версия)
    language_patterns = {}
    try:
        patterns_file = os.path.join("static", "languages_patterns.json")
        with open(patterns_file, 'r', encoding='utf-8') as f:
            language_patterns = json.load(f)
    except Exception:
        pass
    
    total_files = sum(lang_data.get("Files", 0) for lang_data in detected_languages.values())
    
    if total_files == 0:
        return []
    
    language_stats = []
    sorted_languages = sorted(detected_languages.items(), key=lambda x: x[1].get("Files", 0), reverse=True)
    
    for language, lang_data in sorted_languages:
        file_count = lang_data.get("Files", 0)
        percentage = (file_count / total_files) * 100 if total_files > 0 else 0
        
        lang_config = language_patterns.get(language.lower(), {})
        
        language_stats.append({
            'language': language,
            'count': file_count,
            'percentage': round(percentage, 1),
            'color': lang_config.get('color', '#6b7280'),
            'icon': lang_config.get('icon', '📄'),
            'extensions': lang_data.get("ExtensionsList", [])
        })
    
    return language_stats

def get_framework_stats_from_project_scan(scan):
    """Get framework statistics from scan - копия функции из project_routes.py"""
    if not scan.detected_frameworks:
        return {}
    
    try:
        detected_frameworks = json.loads(scan.detected_frameworks)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse detected_frameworks for scan {scan.id}")
        return {}
    
    # Загружаем паттерны (упрощенная версия)
    language_patterns = {}
    try:
        patterns_file = os.path.join("static", "languages_patterns.json")
        with open(patterns_file, 'r', encoding='utf-8') as f:
            language_patterns = json.load(f)
    except Exception:
        pass
    
    framework_stats = {}
    for framework, detections in detected_frameworks.items():
        framework_lower = framework.lower()
        framework_config = language_patterns.get(framework_lower, {})
        
        framework_stats[framework] = {
            'detections': detections,
            'color': framework_config.get('color', '#6b7280'),
            'icon': framework_config.get('icon', '🔧')
        }
    
    return framework_stats

# Добавить эти маршруты в конец файла admin_routes.py

@router.post("/admin/export-projects")
async def export_projects(background_tasks: BackgroundTasks, 
                         technologies: list = Form(..., alias="technologies[]"),
                         _: str = Depends(get_admin_user)):
    """Export projects with specific technologies - admin only"""
    try:
        if not technologies:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Не выбраны технологии для поиска"}
            )
        
        # Нормализуем технологии
        normalized_technologies = []
        tech_mapping = {
            'nestjs': 'NestJS',
            'vue': 'Vue',
            'angular': 'Angular',
            'scala': 'Scala',
            'dart': 'Dart',
            'groovy': 'Groovy'
        }
        
        for tech in technologies:
            if tech.lower() in tech_mapping:
                normalized_technologies.append(tech_mapping[tech.lower()])
        
        if not normalized_technologies:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Неизвестные технологии"}
            )
        
        # Генерируем уникальный ID задачи
        task_id = str(uuid.uuid4())
        
        # Инициализируем задачу
        projects_download_tasks[task_id] = {
            "status": "started",
            "message": "Инициализация...",
            "file_path": None,
            "filename": None,
            "content_type": None
        }
        
        # Запускаем фоновую задачу
        background_tasks.add_task(prepare_projects_download, task_id, normalized_technologies)
        
        return {"status": "success", "task_id": task_id}
        
    except Exception as e:
        logger.error(f"Error starting projects export: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@router.get("/admin/export-projects-status/{task_id}")
async def export_projects_status(task_id: str, _: str = Depends(get_admin_user)):
    """Check projects export status"""
    if task_id not in projects_download_tasks:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Task not found"}
        )
    
    task = projects_download_tasks[task_id]
    return {
        "status": task["status"],
        "message": task["message"]
    }

@router.get("/admin/download-projects/{task_id}")
async def download_projects(task_id: str, _: str = Depends(get_admin_user)):
    """Download prepared projects report file"""
    if task_id not in projects_download_tasks:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Task not found"}
        )
    
    task = projects_download_tasks[task_id]
    
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
        # Возвращаем файл и планируем очистку
        response = FileResponse(
            path=task["file_path"],
            filename=task["filename"],
            media_type=task["content_type"]
        )
        
        # Планируем очистку
        async def cleanup():
            await asyncio.sleep(5)  # Ждем 5 секунд перед очисткой
            try:
                if os.path.exists(task["file_path"]):
                    os.remove(task["file_path"])
                if task_id in projects_download_tasks:
                    del projects_download_tasks[task_id]
            except Exception as e:
                logger.error(f"Error cleaning up projects download file: {e}")
        
        asyncio.create_task(cleanup())
        
        return response
        
    except Exception as e:
        logger.error(f"Error downloading projects file: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )