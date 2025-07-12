from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from dotenv import set_key, load_dotenv
import secrets
import logging
import os

from services.auth import get_admin_user, get_user_db, get_password_hash
from services.backup_service import create_database_backup, get_backup_status, list_backups
from models import User
from services.templates import templates
logger = logging.getLogger("main")

router = APIRouter()

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
async def list_users(_: str = Depends(get_admin_user), user_db: Session = Depends(get_user_db)):
    """Get list of all users"""
    try:
        users = user_db.query(User).order_by(User.created_at.desc()).all()
        
        users_data = []
        for user in users:
            users_data.append({
                "username": user.username,
                "created_at": user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else "Unknown"
            })
        
        return {"status": "success", "users": users_data}
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