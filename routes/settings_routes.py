from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from dotenv import set_key, load_dotenv
import urllib.parse
import logging
import os

from config import DATABASE_URL, BACKUP_RETENTION_DAYS
from services.auth import get_current_user, get_user_db, get_password_hash, verify_password, get_admin_user
from services.microservice_client import (
    get_pat_token, set_pat_token, get_rules_info, get_rules_content, update_rules,
    get_fp_rules_info, get_fp_rules_content, update_fp_rules,
    get_excluded_extensions_info, get_excluded_extensions_content, update_excluded_extensions,
    get_excluded_files_info, get_excluded_files_content, update_excluded_files,
    check_microservice_health
)
from models import User
from services.templates import templates
logger = logging.getLogger("main")
user_logger = logging.getLogger("user_actions")

router = APIRouter()

def get_current_api_key():
    """Get current API key from environment"""
    load_dotenv()
    return os.getenv("API_KEY", "Not set")

def update_api_key_in_env(new_api_key: str):
    """Update API key in .env file"""
    try:
        env_file = ".env"
        set_key(env_file, "API_KEY", new_api_key)
        load_dotenv(override=True)
        return True
    except Exception as e:
        logger.error(f"Error updating API key in .env: {e}")
        return False

@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, current_user: str = Depends(get_current_user)):
   # Get current API key
   current_api_key = get_current_api_key()
   if current_api_key != "Not set":
       current_api_key = current_api_key[:4] + "*" * (len(current_api_key) - 4)
   
   # Get current PAT token
   current_token = "Not set"
   microservice_available = await check_microservice_health()
   
   # Check if database is SQLite for backup functionality
   is_sqlite = "sqlite" in DATABASE_URL.lower()
   if "postgresql" in DATABASE_URL.lower():
       db_type = "PostgreSQL"
   elif "mysql" in DATABASE_URL.lower():
       db_type = "MySQL"
   elif "sqlite" in DATABASE_URL.lower():
       db_type = "SQLite"
   else:
       db_type = "Другая"
   
   if microservice_available:
       current_token = await get_pat_token()
   else:
       current_token = "Error: microservice unavailable"
       logger.error("GET 'pat_token': microservice unavailable")
   
   # Get rules info and content
   rules_info = None
   current_rules_content = ""
   
   if microservice_available:
       rules_info = await get_rules_info()
       if rules_info and rules_info.get("exists", False):
           current_rules_content = await get_rules_content()
   else:
       rules_info = {"error": "microservice_unavailable"}
       logger.error("GET 'rules_info': microservice unavailable")
   
   # Get False-Positive rules info and content
   fp_rules_info = None
   current_fp_rules_content = ""
   
   if microservice_available:
       fp_rules_info = await get_fp_rules_info()
       if fp_rules_info and fp_rules_info.get("exists", False):
           current_fp_rules_content = await get_fp_rules_content()
   else:
       fp_rules_info = {"error": "microservice_unavailable"}
       logger.error("GET 'fp_rules_info': microservice unavailable")
   
   # Get excluded extensions info and content
   excluded_extensions_info = None
   current_excluded_extensions_content = ""
   
   if microservice_available:
       excluded_extensions_info = await get_excluded_extensions_info()
       if excluded_extensions_info and excluded_extensions_info.get("exists", False):
           current_excluded_extensions_content = await get_excluded_extensions_content()
   else:
       excluded_extensions_info = {"error": "microservice_unavailable"}
       logger.error("GET 'excluded_extensions_info': microservice unavailable")
   
   # Get excluded files info and content
   excluded_files_info = None
   current_excluded_files_content = ""
   
   if microservice_available:
       excluded_files_info = await get_excluded_files_info()
       if excluded_files_info and excluded_files_info.get("exists", False):
           current_excluded_files_content = await get_excluded_files_content()
   else:
       excluded_files_info = {"error": "microservice_unavailable"}
       logger.error("GET 'excluded_files_info': microservice unavailable")
   
   # Ensure all content variables are strings
   if current_rules_content is None:
       current_rules_content = ""
   if current_fp_rules_content is None:
       current_fp_rules_content = ""
   if current_excluded_extensions_content is None:
       current_excluded_extensions_content = ""
   if current_excluded_files_content is None:
       current_excluded_files_content = ""
   
   return templates.TemplateResponse("settings.html", {
       "request": request,
       "current_api_key": current_api_key or "Not set",
       "current_token": current_token or "Not set",
       "rules_info": rules_info,
       "current_rules_content": current_rules_content,
       "fp_rules_info": fp_rules_info,
       "current_fp_rules_content": current_fp_rules_content,
       "excluded_extensions_info": excluded_extensions_info,
       "current_excluded_extensions_content": current_excluded_extensions_content,
       "excluded_files_info": excluded_files_info,
       "current_excluded_files_content": current_excluded_files_content,
       "BACKUP_RETENTION_DAYS": BACKUP_RETENTION_DAYS,
       "microservice_available": microservice_available,
       "is_sqlite": is_sqlite,
       "db_type": db_type,
       "current_user": current_user
   })

@router.post("/settings/change-password")
async def change_password(request: Request, current_password: str = Form(...), 
                         new_password: str = Form(...), confirm_password: str = Form(...),
                         current_user: str = Depends(get_current_user), user_db: Session = Depends(get_user_db)):
    try:
        if new_password != confirm_password:
            return RedirectResponse(url="/secret_scanner/settings?error=password_mismatch", status_code=302)
        
        user = user_db.query(User).filter(User.username == current_user).first()
        if not user:
            return RedirectResponse(url="/secret_scanner/settings?error=user_not_found", status_code=302)
        
        if not verify_password(current_password, user.password_hash):
            return RedirectResponse(url="/secret_scanner/settings?error=password_change_failed", status_code=302)
        
        user.password_hash = get_password_hash(new_password)
        user_db.commit()
        user_logger.warning(f"User '{current_user}' changed their password")
        
        return RedirectResponse(url="/secret_scanner/settings?success=password_changed", status_code=302)
        
    except Exception as e:
        logger.error(f"Password change error: {e}")
        return RedirectResponse(url="/secret_scanner/settings?error=password_change_failed", status_code=302)

@router.post("/settings/update-api-key")
async def update_api_key(request: Request, api_key: str = Form(...), _: str = Depends(get_admin_user)):
    try:
        if update_api_key_in_env(api_key):
            user_logger.warning(f"'admin' updated API key")
            return RedirectResponse(url="/secret_scanner/settings?success=api_key_updated", status_code=302)
        else:
            return RedirectResponse(url="/secret_scanner/settings?error=api_key_update_failed", status_code=302)
    except Exception as e:
        logger.error(f"API key update error: {e}")
        return RedirectResponse(url="/secret_scanner/settings?error=api_key_update_failed", status_code=302)

@router.post("/settings/update-token")
async def update_token(request: Request, token: str = Form(...), _: str = Depends(get_admin_user)):
    try:
        if await set_pat_token(token):
            user_logger.warning(f"'admin' updated PAT token")
            return RedirectResponse(url="/secret_scanner/settings?success=token_updated", status_code=302)
        else:
            return RedirectResponse(url="/secret_scanner/settings?error=token_update_failed", status_code=302)
    except:
        return RedirectResponse(url="/secret_scanner/settings?error=microservice_unavailable", status_code=302)

@router.post("/settings/update-rules")
async def update_rules_route(request: Request, rules_content: str = Form(...), current_user: str = Depends(get_current_user)):
    try:
        if not rules_content.strip():
            return RedirectResponse(url="/secret_scanner/settings?error=empty_content", status_code=302)
        
        response = await update_rules(rules_content)
        
        if response.status_code == 200:
            user_logger.warning(f"User '{current_user}' updated scanning rules configuration")
            return RedirectResponse(url="/secret_scanner/settings?success=rules_updated", status_code=302)
        else:
            try:
                error_data = response.json()
                error_message = error_data.get("message", f"Microservice error: HTTP {response.status_code}")
            except:
                error_message = f"Microservice error: HTTP {response.status_code}"
            
            encoded_error = urllib.parse.quote(error_message)
            return RedirectResponse(url=f"/secret_scanner/settings?error={encoded_error}", status_code=302)
            
    except Exception as e:
        logger.error(f"Rules update error: {e}")
        import traceback
        traceback.print_exc()
        error_message = f"Update error: {str(e)}"
        encoded_error = urllib.parse.quote(error_message)
        return RedirectResponse(url=f"/secret_scanner/settings?error={encoded_error}", status_code=302)

@router.post("/settings/update-fp-rules")
async def update_fp_rules_route(request: Request, fp_rules_content: str = Form(...), current_user: str = Depends(get_current_user)):
    try:
        if not fp_rules_content.strip():
            return RedirectResponse(url="/secret_scanner/settings?error=empty_content", status_code=302)
        
        response = await update_fp_rules(fp_rules_content)
        
        if response.status_code == 200:
            user_logger.warning(f"User '{current_user}' updated false-positive rules configuration")
            return RedirectResponse(url="/secret_scanner/settings?success=fp_rules_updated", status_code=302)
        else:
            try:
                error_data = response.json()
                error_message = error_data.get("message", f"Microservice error: HTTP {response.status_code}")
            except:
                error_message = f"Microservice error: HTTP {response.status_code}"
            
            encoded_error = urllib.parse.quote(error_message)
            return RedirectResponse(url=f"/secret_scanner/settings?error={encoded_error}", status_code=302)
            
    except Exception as e:
        logger.error(f"FP rules update error: {e}")
        import traceback
        traceback.print_exc()
        error_message = f"Update error: {str(e)}"
        encoded_error = urllib.parse.quote(error_message)
        return RedirectResponse(url=f"/secret_scanner/settings?error={encoded_error}", status_code=302)

@router.post("/settings/update-excluded-extensions")
async def update_excluded_extensions_route(request: Request, excluded_extensions_content: str = Form(...), current_user: str = Depends(get_current_user)):
    try:
        if not excluded_extensions_content.strip():
            return RedirectResponse(url="/secret_scanner/settings?error=empty_content", status_code=302)
        
        response = await update_excluded_extensions(excluded_extensions_content)
        
        if response.status_code == 200:
            user_logger.warning(f"User '{current_user}' updated excluded extensions configuration")
            return RedirectResponse(url="/secret_scanner/settings?success=excluded_extensions_updated", status_code=302)
        else:
            try:
                error_data = response.json()
                error_message = error_data.get("message", f"Microservice error: HTTP {response.status_code}")
            except:
                error_message = f"Microservice error: HTTP {response.status_code}"
            
            encoded_error = urllib.parse.quote(error_message)
            return RedirectResponse(url=f"/secret_scanner/settings?error={encoded_error}", status_code=302)
            
    except Exception as e:
        logger.error(f"Excluded extensions update error: {e}")
        import traceback
        traceback.print_exc()
        error_message = f"Update error: {str(e)}"
        encoded_error = urllib.parse.quote(error_message)
        return RedirectResponse(url=f"/secret_scanner/settings?error={encoded_error}", status_code=302)

@router.post("/settings/update-excluded-files")
async def update_excluded_files_route(request: Request, excluded_files_content: str = Form(...), current_user: str = Depends(get_current_user)):
    try:
        if not excluded_files_content.strip():
            return RedirectResponse(url="/secret_scanner/settings?error=empty_content", status_code=302)
        
        response = await update_excluded_files(excluded_files_content)
        
        if response.status_code == 200:
            user_logger.warning(f"User '{current_user}' updated excluded files configuration")
            return RedirectResponse(url="/secret_scanner/settings?success=excluded_files_updated", status_code=302)
        else:
            try:
                error_data = response.json()
                error_message = error_data.get("message", f"Microservice error: HTTP {response.status_code}")
            except:
                error_message = f"Microservice error: HTTP {response.status_code}"
            
            encoded_error = urllib.parse.quote(error_message)
            return RedirectResponse(url=f"/secret_scanner/settings?error={encoded_error}", status_code=302)
            
    except Exception as e:
        logger.error(f"Excluded files update error: {e}")
        import traceback
        traceback.print_exc()
        error_message = f"Update error: {str(e)}"
        encoded_error = urllib.parse.quote(error_message)
        return RedirectResponse(url=f"/secret_scanner/settings?error={encoded_error}", status_code=302)