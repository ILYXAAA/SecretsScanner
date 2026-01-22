from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import timedelta
import os

from config import get_full_url, ACCESS_TOKEN_EXPIRE_MINUTES, USERS_DATABASE_URL
from models import User
from services.auth import (
    verify_credentials, 
    create_access_token, 
    verify_token, 
    get_user_db
)
from services.templates import templates
import logging

user_logger = logging.getLogger("user_actions")
logger = logging.getLogger("main")

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    token = request.cookies.get("auth_token")
    if token:
        username = verify_token(token)
        if username:
            # Проверяем существование пользователя
            user_engine = create_engine(USERS_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in USERS_DATABASE_URL else {})
            UserSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=user_engine)
            user_db = UserSessionLocal()
            
            try:
                user = user_db.query(User).filter(User.username == username).first()
                if user:
                    return RedirectResponse(url=get_full_url("dashboard"), status_code=302)
            finally:
                user_db.close()
        
        # Токен невалиден или пользователь не существует - удаляем cookie
        if username:
            user_logger.error(f"Invalid or expired token for user '{username}', clearing cookie")
        else:
            user_logger.error(f"Service got an invalid or expired token")
        response = templates.TemplateResponse("login.html", {"request": request})
        response.delete_cookie(key="auth_token")
        return response
    
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), user_db: Session = Depends(get_user_db)):
    if verify_credentials(username, password, user_db):
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": username}, expires_delta=access_token_expires
        )
        response = RedirectResponse(url=get_full_url("dashboard"), status_code=302)
        response.set_cookie(
            key="auth_token", 
            value=access_token, 
            httponly=True,
            secure=True if os.getenv("HTTPS", "false").lower() == "true" else False,
            samesite="lax",
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        user_logger.info(f"User '{username}' successfully logged in")
        return response
    user_logger.error(f"Failed login attempt for username: '{username}'")
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@router.get("/logout")
async def logout():
    response = RedirectResponse(url=get_full_url(""), status_code=302)
    response.delete_cookie(key="auth_token")
    return response

@router.get("/maintenance", response_class=HTMLResponse)
async def maintenance_page(request: Request):
    """Maintenance page with admin login form"""
    from services.database import SessionLocal
    from routes.admin_routes import get_maintenance_end_time
    
    db = SessionLocal()
    try:
        end_time = get_maintenance_end_time(db)
        return templates.TemplateResponse("maintenance.html", {
            "request": request,
            "end_time": end_time
        })
    finally:
        db.close()

@router.post("/maintenance/login")
async def maintenance_login(request: Request, username: str = Form(...), password: str = Form(...), user_db: Session = Depends(get_user_db)):
    """Login for admin on maintenance page - only allows admin users"""
    try:
        logger.info(f"Maintenance login POST request received for username: '{username}'")
        
        if verify_credentials(username, password, user_db):
            # Check if user is admin
            if username != "admin":
                from services.database import SessionLocal
                from routes.admin_routes import get_maintenance_end_time
                
                db = SessionLocal()
                try:
                    end_time = get_maintenance_end_time(db)
                finally:
                    db.close()
                
                user_logger.warning(f"Non-admin user '{username}' attempted to login during maintenance")
                return templates.TemplateResponse("maintenance.html", {
                    "request": request,
                    "end_time": end_time,
                    "error": "Только администратор может войти во время технических работ"
                })
            
            # Admin login successful
            access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = create_access_token(
                data={"sub": username}, expires_delta=access_token_expires
            )
            response = RedirectResponse(url=get_full_url("admin"), status_code=302)
            response.set_cookie(
                key="auth_token", 
                value=access_token, 
                httponly=True,
                secure=True if os.getenv("HTTPS", "false").lower() == "true" else False,
                samesite="lax",
                max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )
            user_logger.info(f"Admin '{username}' successfully logged in during maintenance")
            logger.info(f"Admin '{username}' successfully logged in during maintenance, redirecting to admin panel")
            return response
        
        # Invalid credentials
        from services.database import SessionLocal
        from routes.admin_routes import get_maintenance_end_time
        
        db = SessionLocal()
        try:
            end_time = get_maintenance_end_time(db)
        finally:
            db.close()
        
        user_logger.error(f"Failed maintenance login attempt for username: '{username}'")
        logger.warning(f"Failed maintenance login attempt for username: '{username}'")
        return templates.TemplateResponse("maintenance.html", {
            "request": request,
            "end_time": end_time,
            "error": "Неверные учетные данные"
        })
    except Exception as e:
        logger.error(f"Error in maintenance_login: {e}", exc_info=True)
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        from services.database import SessionLocal
        from routes.admin_routes import get_maintenance_end_time
        
        db = SessionLocal()
        try:
            end_time = get_maintenance_end_time(db)
        finally:
            db.close()
        
        return templates.TemplateResponse("maintenance.html", {
            "request": request,
            "end_time": end_time,
            "error": f"Ошибка при авторизации: {str(e)}"
        })