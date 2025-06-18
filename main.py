from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, File, UploadFile, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text, Boolean, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from CredsManager import decrypt_from_file
from urllib.parse import urlparse
import uuid
import json
import httpx
import asyncio
import logging
import urllib.parse
from typing import Optional, List
import os
from pathlib import Path
import shutil
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

app = FastAPI(title="Secrets Scanner")

# Create directories if they don't exist
Path("templates").mkdir(exist_ok=True)
Path("ico").mkdir(exist_ok=True)

# Mount static files for favicon
app.mount("/ico", StaticFiles(directory="ico"), name="ico")

templates = Jinja2Templates(directory="templates")

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database/secrets_scanner.db")
if "database/" in DATABASE_URL:
    Path("database").mkdir(exist_ok=True)
MICROSERVICE_URL = os.getenv("MICROSERVICE_URL", "http://127.0.0.1:8001")
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
HUB_TYPE = os.getenv("HUB_TYPE", "Azure")  # Git or Azure

# Backup configuration
BACKUP_DIR = os.getenv("BACKUP_DIR", "./backups")
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "7"))
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
# Create backup directory
Path(BACKUP_DIR).mkdir(exist_ok=True)
# Setup logging for backups
logging.basicConfig(level=logging.INFO)
backup_logger = logging.getLogger("backup")

# Add JSON filter to Jinja2
def tojson_filter(obj):
    if obj is None:
        return json.dumps("")
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        return json.dumps("")

def datetime_filter(timestamp):
    if timestamp:
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    return 'Unknown'

def basename_filter(path):
    if path:
        return path.split('/')[-1]
    return ''

def urldecode_filter(text):
    if text:
        return urllib.parse.unquote(text)
    return ''

templates.env.filters['tojson'] = tojson_filter
templates.env.filters['strftime'] = datetime_filter
templates.env.filters['basename'] = basename_filter
templates.env.filters['urldecode'] = urldecode_filter

# Database setup
SQLALCHEMY_DATABASE_URL = DATABASE_URL
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    repo_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Scan(Base):
    __tablename__ = "scans"
    id = Column(String, primary_key=True, index=True)
    project_name = Column(String, index=True)
    repo_commit = Column(String)
    ref_type = Column(String)
    ref = Column(String)
    status = Column(String, default="running")  # running, completed, failed
    started_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime)
    files_scanned = Column(Integer)  # New field for tracking scanned files
    error_message = Column(Text, default="No message")  # Add default value

class Secret(Base):
    __tablename__ = "secrets"
    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(String, index=True)
    path = Column(String)
    line = Column(Integer)
    secret = Column(String)
    context = Column(Text)
    severity = Column(String)
    type = Column(String)
    status = Column(String, default="No status")  # No status, Confirmed, Refuted
    is_exception = Column(Boolean, default=False)
    exception_comment = Column(Text)
    refuted_at = Column(DateTime)  # New field for tracking when secret was refuted

Base.metadata.create_all(bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Authentication
security = HTTPBearer()

def load_credentials():
    try:
        LOGIN_FILE = "Auth/login.dat"
        PASSWORD_FILE = "Auth/password.dat"
        username = decrypt_from_file(LOGIN_FILE, key_name="LOGIN_KEY")
        password = decrypt_from_file(PASSWORD_FILE, key_name="PASSWORD_KEY")
        return [username, password]
    except Exception as error:
        print(f"Error: {str(error)}")
        print("Если это первый запуск - необходимо запустить мастер настройки Auth данных `python CredsManager.py`")

    return None

def verify_credentials(username: str, password: str):
    creds = load_credentials()
    if creds and creds[0] == username and creds[1] == password:
        return True
    return False

async def get_current_user(request: Request):
    auth_cookie = request.cookies.get("auth_token")
    if not auth_cookie:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return True

async def check_scan_timeouts():
    while True:
        try:
            db = SessionLocal()
            timeout_threshold = datetime.utcnow() - timedelta(minutes=10)
            
            # Find running scans that started more than 10 minutes ago
            timed_out_scans = db.query(Scan).filter(
                Scan.status == "running",
                Scan.started_at < timeout_threshold
            ).all()
            
            for scan in timed_out_scans:
                scan.status = "timeout"
                scan.completed_at = datetime.utcnow()
            
            if timed_out_scans:
                db.commit()
                print(f"Marked {len(timed_out_scans)} scans as timed out")
            
            db.close()
        except Exception as e:
            print(f"Error checking scan timeouts: {e}")
        
        # Check every minute
        await asyncio.sleep(60)

async def check_microservice_health():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/health", timeout=5.0)
            return response.status_code == 200
    except:
        return False

def get_scan_statistics(db: Session, scan_id: str):
    """Get high and potential secret counts for a scan"""
    high_count = db.query(Secret).filter(
        Secret.scan_id == scan_id,
        Secret.severity == "High",
        Secret.is_exception == False
    ).count()
    
    potential_count = db.query(Secret).filter(
        Secret.scan_id == scan_id,
        Secret.severity == "Potential",
        Secret.is_exception == False
    ).count()
    
    return high_count, potential_count

# Favicon route
@app.get("/favicon.ico")
async def favicon():
    favicon_path = Path("ico/favicon.ico")
    if favicon_path.exists():
        return FileResponse("ico/favicon.ico")
    else:
        # Return a simple 204 No Content if favicon doesn't exist
        raise HTTPException(status_code=404, detail="Favicon not found")

# Routes
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.cookies.get("auth_token"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if verify_credentials(username, password):
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(key="auth_token", value="authenticated", httponly=True)
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(key="auth_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, page: int = 1, search: str = "", _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    per_page = 10
    offset = (page - 1) * per_page
    
    # Get recent scans (last 20 scans ordered by start time)
    recent_scans_query = db.query(Scan).order_by(Scan.started_at.desc()).limit(20)
    recent_scans = recent_scans_query.all()
    
    # Add statistics to recent scans
    recent_scans_data = []
    for scan in recent_scans:
        high_count, potential_count = get_scan_statistics(db, scan.id)
        recent_scans_data.append({
            "scan": scan,
            "high_count": high_count,
            "potential_count": potential_count
        })
    
    # Get projects with pagination and search
    projects_query = db.query(Project)
    if search:
        projects_query = projects_query.filter(Project.name.contains(search))
    
    total_projects = projects_query.count()
    projects_list = projects_query.offset(offset).limit(per_page).all()
    
    # Add latest scan info to each project and sort by latest scan date
    projects_data = []
    for project in projects_list:
        latest_scan = db.query(Scan).filter(
            Scan.project_name == project.name
        ).order_by(Scan.started_at.desc()).first()
        
        high_count = 0
        potential_count = 0
        
        if latest_scan and latest_scan.status == 'completed':
            high_count, potential_count = get_scan_statistics(db, latest_scan.id)
        
        projects_data.append({
            "project": project,
            "latest_scan": latest_scan,
            "high_count": high_count,
            "potential_count": potential_count,
            "latest_scan_date": latest_scan.started_at if latest_scan else datetime.min
        })
    
    # Sort projects by latest scan date (newest first)
    projects_data.sort(key=lambda x: x["latest_scan_date"], reverse=True)
    
    total_pages = (total_projects + per_page - 1) // per_page
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "recent_scans": recent_scans_data,
        "projects": projects_data,
        "current_page": page,
        "total_pages": total_pages,
        "search": search,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "HUB_TYPE": HUB_TYPE
    })

@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, _: bool = Depends(get_current_user)):
    # Get current PAT token
    current_token = "Not set"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/get-pat", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    current_token = data.get("token", "Not set")
    except:
        current_token = "Error fetching token"
    
    # Get rules info and content
    rules_info = None
    current_rules_content = ""
    
    try:
        async with httpx.AsyncClient() as client:
            # Get rules info
            info_response = await client.get(f"{MICROSERVICE_URL}/rules-info", timeout=5.0)
            
            if info_response.status_code == 200:
                rules_info = info_response.json()
                
                # If rules exist, get their content
                if rules_info and rules_info.get("exists", False):
                    rules_response = await client.get(f"{MICROSERVICE_URL}/get-rules", timeout=5.0)
                    
                    if rules_response.status_code == 200:
                        rules_data = rules_response.json()
                        if rules_data.get("status") == "success":
                            current_rules_content = rules_data.get("rules", "")
            else:
                if info_response.status_code == 503:
                    rules_info = "error=microservice_unavailable"
    except Exception as e:
        print(f"Error fetching rules: {e}")
        pass
    
    # Get excluded extensions info and content
    excluded_extensions_info = None
    current_excluded_extensions_content = ""
    
    try:
        async with httpx.AsyncClient() as client:
            # Get excluded extensions info
            info_response = await client.get(f"{MICROSERVICE_URL}/excluded-extensions-info", timeout=5.0)
            
            if info_response.status_code == 200:
                excluded_extensions_info = info_response.json()
                
                # If file exists, get content
                if excluded_extensions_info and excluded_extensions_info.get("exists", False):
                    content_response = await client.get(f"{MICROSERVICE_URL}/get-excluded-extensions", timeout=5.0)
                    
                    if content_response.status_code == 200:
                        content_data = content_response.json()
                        if content_data.get("status") == "success":
                            current_excluded_extensions_content = content_data.get("excluded_extensions", "")
    except Exception as e:
        print(f"Error fetching excluded extensions: {e}")
        pass
    
    # Get excluded files info and content
    excluded_files_info = None
    current_excluded_files_content = ""
    
    try:
        async with httpx.AsyncClient() as client:
            # Get excluded files info
            info_response = await client.get(f"{MICROSERVICE_URL}/excluded-files-info", timeout=5.0)
            
            if info_response.status_code == 200:
                excluded_files_info = info_response.json()
                
                # If file exists, get content
                if excluded_files_info and excluded_files_info.get("exists", False):
                    content_response = await client.get(f"{MICROSERVICE_URL}/get-excluded-files", timeout=5.0)
                    
                    if content_response.status_code == 200:
                        content_data = content_response.json()
                        if content_data.get("status") == "success":
                            current_excluded_files_content = content_data.get("excluded_files", "")
    except Exception as e:
        print(f"Error fetching excluded files: {e}")
        pass
    
    # Ensure all content variables are strings
    if current_rules_content is None:
        current_rules_content = ""
    if current_excluded_extensions_content is None:
        current_excluded_extensions_content = ""
    if current_excluded_files_content is None:
        current_excluded_files_content = ""
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "current_token": current_token or "Not set",
        "rules_info": rules_info,
        "current_rules_content": current_rules_content,
        "excluded_extensions_info": excluded_extensions_info,
        "current_excluded_extensions_content": current_excluded_extensions_content,
        "excluded_files_info": excluded_files_info,
        "current_excluded_files_content": current_excluded_files_content,
        "BACKUP_RETENTION_DAYS": BACKUP_RETENTION_DAYS  # Add this line
    })

@app.post("/settings/update-token")
async def update_token(request: Request, token: str = Form(...), _: bool = Depends(get_current_user)):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{MICROSERVICE_URL}/set-pat", 
                                       json={"token": token}, timeout=10.0)
            if response.status_code == 200:
                return RedirectResponse(url="/settings?success=token_updated", status_code=302)
            else:
                return RedirectResponse(url="/settings?error=token_update_failed", status_code=302)
    except:
        return RedirectResponse(url="/settings?error=microservice_unavailable", status_code=302)

@app.post("/settings/update-rules")
async def update_rules(request: Request, rules_content: str = Form(...), _: bool = Depends(get_current_user)):
    try:
        if not rules_content.strip():
            return RedirectResponse(url="/settings?error=empty_content", status_code=302)
        
        # Send content to microservice
        payload = {
            "content": rules_content
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{MICROSERVICE_URL}/update-rules",
                json=payload
            )
            
            if response.status_code == 200:
                return RedirectResponse(url="/settings?success=rules_updated", status_code=302)
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get("message", f"Microservice error: HTTP {response.status_code}")
                except:
                    error_message = f"Microservice error: HTTP {response.status_code}"
                
                encoded_error = urllib.parse.quote(error_message)
                return RedirectResponse(url=f"/settings?error={encoded_error}", status_code=302)
                
    except Exception as e:
        print(f"Rules update error: {e}")
        import traceback
        traceback.print_exc()
        error_message = f"Update error: {str(e)}"
        encoded_error = urllib.parse.quote(error_message)
        return RedirectResponse(url=f"/settings?error={encoded_error}", status_code=302)

@app.post("/settings/update-excluded-extensions")
async def update_excluded_extensions(request: Request, excluded_extensions_content: str = Form(...), _: bool = Depends(get_current_user)):
    try:
        if not excluded_extensions_content.strip():
            return RedirectResponse(url="/settings?error=empty_content", status_code=302)
        
        # Send content to microservice
        payload = {
            "content": excluded_extensions_content
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{MICROSERVICE_URL}/update-excluded-extensions",
                json=payload
            )
            
            if response.status_code == 200:
                return RedirectResponse(url="/settings?success=excluded_extensions_updated", status_code=302)
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get("message", f"Microservice error: HTTP {response.status_code}")
                except:
                    error_message = f"Microservice error: HTTP {response.status_code}"
                
                encoded_error = urllib.parse.quote(error_message)
                return RedirectResponse(url=f"/settings?error={encoded_error}", status_code=302)
                
    except Exception as e:
        print(f"Excluded extensions update error: {e}")
        import traceback
        traceback.print_exc()
        error_message = f"Update error: {str(e)}"
        encoded_error = urllib.parse.quote(error_message)
        return RedirectResponse(url=f"/settings?error={encoded_error}", status_code=302)

@app.post("/settings/update-excluded-files")
async def update_excluded_files(request: Request, excluded_files_content: str = Form(...), _: bool = Depends(get_current_user)):
    try:
        if not excluded_files_content.strip():
            return RedirectResponse(url="/settings?error=empty_content", status_code=302)
        
        # Send content to microservice
        payload = {
            "content": excluded_files_content
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{MICROSERVICE_URL}/update-excluded-files",
                json=payload
            )
            
            if response.status_code == 200:
                return RedirectResponse(url="/settings?success=excluded_files_updated", status_code=302)
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get("message", f"Microservice error: HTTP {response.status_code}")
                except:
                    error_message = f"Microservice error: HTTP {response.status_code}"
                
                encoded_error = urllib.parse.quote(error_message)
                return RedirectResponse(url=f"/settings?error={encoded_error}", status_code=302)
                
    except Exception as e:
        print(f"Excluded files update error: {e}")
        import traceback
        traceback.print_exc()
        error_message = f"Update error: {str(e)}"
        encoded_error = urllib.parse.quote(error_message)
        return RedirectResponse(url=f"/settings?error={encoded_error}", status_code=302)

def validate_repo_url(repo_url: str, hub_type: str) -> None:
    """Validate repository URL based on hub type"""
    if hub_type == "Azure":
        parsed = urlparse(repo_url)
        
        if not parsed.netloc:
            raise ValueError("❌ URL должен содержать имя сервера")
        
        path_parts = parsed.path.strip('/').split('/')
        
        if '_git' not in path_parts:
            raise ValueError("❌ URL не содержит '_git'")
        
        git_index = path_parts.index('_git')
        
        if git_index + 1 >= len(path_parts):
            raise ValueError("❌ URL некорректен: отсутствует имя репозитория после '_git'")
        
        repository = path_parts[git_index + 1]
        
        if git_index >= 2:
            collection = path_parts[0]
            project = path_parts[git_index - 1]
        elif git_index == 1:
            collection = path_parts[0]
            project = repository
        else:
            raise ValueError("❌ Невозможно определить коллекцию и проект из URL")
        
        if not collection or not project or not repository:
            raise ValueError("❌ URL содержит пустые компоненты")
    
    elif hub_type == "Git":
        parsed = urlparse(repo_url)
        if not parsed.netloc:
            raise ValueError("❌ Некорректный URL репозитория")
        if parsed.scheme not in ['http', 'https']:
            raise ValueError("❌ URL должен использовать HTTP или HTTPS")

@app.post("/projects/add")
async def add_project(request: Request, project_name: str = Form(...), repo_url: str = Form(...), 
                     _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        # Validate repository URL based on hub type
        validate_repo_url(repo_url, HUB_TYPE)
        
        # Check if project already exists
        existing = db.query(Project).filter(Project.name == project_name).first()
        if existing:
            return RedirectResponse(url="/dashboard?error=project_exists", status_code=302)
        
        project = Project(name=project_name, repo_url=repo_url)
        db.add(project)
        db.commit()
        
        # Redirect to the project page instead of dashboard
        return RedirectResponse(url=f"/project/{project_name}", status_code=302)
    
    except ValueError as e:
        encoded_error = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/dashboard?error={encoded_error}", status_code=302)
    except Exception as e:
        print(f"Error adding project: {e}")
        return RedirectResponse(url="/dashboard?error=unexpected_error", status_code=302)

@app.post("/projects/update")
async def update_project(request: Request, project_id: int = Form(...), project_name: str = Form(...), 
                        repo_url: str = Form(...), _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        # Validate repository URL based on hub type
        validate_repo_url(repo_url, HUB_TYPE)
        
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return RedirectResponse(url=f"/project/{project_name}?error=project_not_found", status_code=302)
        
        existing = db.query(Project).filter(Project.name == project_name, Project.id != project_id).first()
        if existing:
            return RedirectResponse(url=f"/project/{project.name}?error=project_exists", status_code=302)
        
        # Store old project name for updating related scans
        old_project_name = project.name
        
        # Update project
        project.name = project_name
        project.repo_url = repo_url
        
        # Update all scans that reference the old project name
        if old_project_name != project_name:
            db.query(Scan).filter(Scan.project_name == old_project_name).update(
                {Scan.project_name: project_name}
            )
        
        db.commit()
        
        return RedirectResponse(url=f"/project/{project_name}?success=project_updated", status_code=302)
    
    except ValueError as e:
        encoded_error = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/project/{project_name}?error={encoded_error}", status_code=302)
    except Exception as e:
        print(f"Error updating project: {e}")
        return RedirectResponse(url=f"/project/{project_name}?error=project_update_failed", status_code=302)

@app.post("/projects/{project_id}/delete")
async def delete_project(project_id: int, _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse(url="/dashboard?error=project_not_found", status_code=302)
    
    # Delete all related scans and secrets
    scans = db.query(Scan).filter(Scan.project_name == project.name).all()
    for scan in scans:
        db.query(Secret).filter(Secret.scan_id == scan.id).delete()
        db.delete(scan)
    
    db.delete(project)
    db.commit()
    
    return RedirectResponse(url="/dashboard?success=project_deleted", status_code=302)

@app.get("/project/{project_name}", response_class=HTMLResponse)
async def project_page(request: Request, project_name: str, _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get latest scan
    latest_scan = db.query(Scan).filter(Scan.project_name == project_name).order_by(Scan.started_at.desc()).first()
    
    # Get all scans for history
    scans = db.query(Scan).filter(Scan.project_name == project_name).order_by(Scan.started_at.desc()).all()
    
    # Count confirmed secrets for each scan
    scan_stats = []
    for scan in scans:
        confirmed_count = db.query(Secret).filter(
            Secret.scan_id == scan.id,
            Secret.is_exception == False
        ).count()
        scan_stats.append({
            "scan": scan,
            "confirmed_count": confirmed_count
        })
    
    return templates.TemplateResponse("project.html", {
        "request": request,
        "project": project,
        "latest_scan": latest_scan,
        "scan_stats": scan_stats,
        "HUB_TYPE": HUB_TYPE
    })

@app.post("/project/{project_name}/scan")
async def start_scan(request: Request, project_name: str, ref_type: str = Form(...), 
                    ref: str = Form(...), _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check microservice health
    if not await check_microservice_health():
        return RedirectResponse(url=f"/project/{project_name}?error=microservice_unavailable", status_code=302)
    
    # Create scan record with 'pending' status
    scan_id = str(uuid.uuid4())
    scan = Scan(id=scan_id, project_name=project_name, ref_type=ref_type, ref=ref, status="pending")
    db.add(scan)
    db.commit()
    
    # Start scan via microservice
    callback_url = f"http://{APP_HOST}:{APP_PORT}/get_results/{project_name}/{scan_id}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{MICROSERVICE_URL}/scan", json={
                "ProjectName": project_name,
                "RepoUrl": project.repo_url,
                "RefType": ref_type,
                "Ref": ref,
                "CallbackUrl": callback_url
            }, timeout=30.0)
            
            # Parse JSON response regardless of status code
            try:
                result = response.json()
            except:
                # If JSON parsing fails, treat as generic HTTP error
                scan.status = "failed"
                db.commit()
                return RedirectResponse(url=f"/project/{project_name}?error=microservice_invalid_response", status_code=302)
            
            if response.status_code == 200 and result.get("status") == "accepted":
                # Success - update scan status to running
                scan.status = "running"
                scan.ref = result.get("Ref", ref)  # Use resolved ref from microservice
                db.commit()
                return RedirectResponse(url=f"/scan/{scan_id}", status_code=302)
            else:
                # Microservice returned an error (could be 400, 500, etc.)
                scan.status = "failed"
                db.commit()
                error_msg = result.get("message", "Unknown error from microservice")
                # URL encode the error message to handle special characters
                import urllib.parse
                encoded_error = urllib.parse.quote(error_msg)
                return RedirectResponse(url=f"/project/{project_name}?error={encoded_error}", status_code=302)
                
    except httpx.TimeoutException:
        scan.status = "failed"
        db.commit()
        return RedirectResponse(url=f"/project/{project_name}?error=microservice_timeout", status_code=302)
    except Exception as e:
        scan.status = "failed"
        db.commit()
        return RedirectResponse(url=f"/project/{project_name}?error=microservice_connection_error", status_code=302)

@app.get("/scan/{scan_id}", response_class=HTMLResponse)
async def scan_status(request: Request, scan_id: str, _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    return templates.TemplateResponse("scan_status.html", {
        "request": request,
        "scan": scan
    })

@app.post("/get_results/{project_name}/{scan_id}")
async def receive_scan_results(project_name: str, scan_id: str, request: Request, db: Session = Depends(get_db)):
    data = await request.json()

    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        return {"status": "error", "message": "Scan not found"}

    # Check if scan completed with error
    if data.get("Status") == "Error":
        scan.status = "failed"
        scan.completed_at = datetime.utcnow()
        error_message = data.get("Message", "Unknown error occurred during scanning")
        print(f"Scan {scan_id} failed with error: {error_message}")
        scan.error_message = error_message
        db.commit()
        return {"status": "error", "message": error_message}

    # Handle partial results
    if data.get("Status") == "partial":
        # Update files scanned count for partial results
        scan.files_scanned = data.get("FilesScanned", 0)
        # Keep status as "running" for partial results
        db.commit()
        return {"status": "success", "message": "Partial results received"}

    # Handle complete results
    if data.get("Status") == "completed":
        scan.status = "completed"
        scan.repo_commit = data.get("RepoCommit")
        scan.completed_at = datetime.utcnow()
        scan.files_scanned = data.get("FilesScanned")
        
        # Clear existing secrets for this scan (in case of reprocessing)
        db.query(Secret).filter(Secret.scan_id == scan_id).delete()
        
        # Save secrets with smart exception handling
        for result in data.get("Results", []):
            # Check if this exact secret was previously handled in this project
            previous_scans = db.query(Scan).filter(
                Scan.project_name == project_name,
                Scan.id != scan_id,
                Scan.completed_at.is_not(None)
            ).order_by(Scan.completed_at.desc()).all()
            
            # Find the most recent decision about this secret
            most_recent_secret = None
            for prev_scan in previous_scans:
                similar_secret = db.query(Secret).filter(
                    Secret.scan_id == prev_scan.id,
                    Secret.path == result["path"],
                    Secret.line == result["line"],
                    Secret.secret == result["secret"],
                    Secret.type == result["Type"]
                ).first()
                
                if similar_secret:
                    most_recent_secret = similar_secret
                    break
            
            # Apply the most recent decision
            if most_recent_secret:
                if most_recent_secret.status == "Refuted":
                    is_exception = True
                    status = "Refuted"
                    exception_comment = most_recent_secret.exception_comment
                    refuted_at = most_recent_secret.refuted_at
                elif most_recent_secret.status == "Confirmed":
                    is_exception = False
                    status = "Confirmed"
                    exception_comment = None
                    refuted_at = None
                else:  # "No status"
                    is_exception = False
                    status = "No status"
                    exception_comment = None
                    refuted_at = None
                severity = most_recent_secret.severity
            else:
                is_exception = False
                status = "No status"
                exception_comment = None
                refuted_at = None
                severity = result["severity"]

            secret = Secret(
                scan_id=scan_id,
                path=result["path"],
                line=result["line"],
                secret=result["secret"],
                context=result["context"],
                severity=severity,
                type=result["Type"],
                is_exception=is_exception,
                exception_comment=exception_comment,
                status=status,
                refuted_at=refuted_at
            )
            db.add(secret)
        
        db.commit()
        return {"status": "success"}

    # If status is not recognized, treat as error
    return {"status": "error", "message": "Unknown status received"}

@app.get("/scan/{scan_id}/results", response_class=HTMLResponse)
async def scan_results(request: Request, scan_id: str, severity_filter: str = "", 
                      type_filter: str = "", show_exceptions: bool = False,
                      _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    # Get project info
    project = db.query(Project).filter(Project.name == scan.project_name).first()
    
    # Get ALL secrets for statistics (excluding exceptions)
    all_non_exception_secrets = db.query(Secret).filter(
        Secret.scan_id == scan_id,
        Secret.is_exception == False
    ).all()
    
    # Calculate statistics
    total_secrets = len(all_non_exception_secrets)
    high_secrets = len([s for s in all_non_exception_secrets if s.severity == 'High'])
    potential_secrets = len([s for s in all_non_exception_secrets if s.severity == 'Potential'])
    
    # Build query for secrets to display
    query = db.query(Secret).filter(Secret.scan_id == scan_id)
    
    if not show_exceptions:
        query = query.filter(Secret.is_exception == False)
    
    if severity_filter:
        query = query.filter(Secret.severity == severity_filter)
    
    if type_filter:
        query = query.filter(Secret.type == type_filter)
    
    # Order: High first, then Potential, then by path and line
    secrets = query.order_by(
        Secret.severity == 'Potential',  # This puts High (False) before Potential (True)
        Secret.path,
        Secret.line
    ).all()
    
    # Get unique types and severities for filters
    all_secrets = db.query(Secret).filter(Secret.scan_id == scan_id).all()
    unique_types = list(set(s.type for s in all_secrets))
    unique_severities = list(set(s.severity for s in all_secrets))
    
    # For each secret, check if there are similar secrets in previous scans with different statuses
    # This helps users see the history and make informed decisions
    secrets_data = []
    for secret in secrets:
        # Find similar secrets in previous scans for this project
        previous_scans = db.query(Scan).filter(
            Scan.project_name == scan.project_name,
            Scan.id != scan_id,
            Scan.completed_at < scan.completed_at
        ).order_by(Scan.completed_at.desc()).all()
        
        previous_status = None
        previous_scan_date = None
        
        for prev_scan in previous_scans:
            similar_secret = db.query(Secret).filter(
                Secret.scan_id == prev_scan.id,
                Secret.path == secret.path,
                Secret.line == secret.line,
                Secret.secret == secret.secret,
                Secret.type == secret.type
            ).first()
            
            if similar_secret and similar_secret.status != "No status":
                previous_status = similar_secret.status
                previous_scan_date = prev_scan.completed_at.strftime('%Y-%m-%d %H:%M')
                break  # Take the most recent previous status
        
        secrets_data.append({
            "id": secret.id,
            "path": secret.path,
            "line": secret.line,
            "secret": secret.secret,
            "context": secret.context,
            "severity": secret.severity,
            "type": secret.type,
            "status": secret.status,
            "is_exception": secret.is_exception,
            "exception_comment": secret.exception_comment or "",
            "refuted_at": secret.refuted_at.strftime('%Y-%m-%d %H:%M') if secret.refuted_at else None,
            "previous_status": previous_status,
            "previous_scan_date": previous_scan_date
        })
    
    return templates.TemplateResponse("scan_results.html", {
        "request": request,
        "scan": scan,
        "project": project,
        "secrets": secrets,
        "secrets_data": secrets_data,
        "unique_types": unique_types,
        "unique_severities": unique_severities,
        "total_secrets": total_secrets,
        "high_secrets": high_secrets,
        "potential_secrets": potential_secrets,
        "hub_type": HUB_TYPE,  # Add hub type to template context
        "current_filters": {
            "severity": severity_filter,
            "type": type_filter,
            "show_exceptions": show_exceptions
        }
    })

@app.post("/secrets/{secret_id}/update-status")
async def update_secret_status(secret_id: int, status: str = Form(...), 
                              comment: str = Form(""), _: bool = Depends(get_current_user), 
                              db: Session = Depends(get_db)):
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    
    secret.status = status
    if status == "Refuted":
        secret.is_exception = True
        secret.exception_comment = comment
        secret.refuted_at = datetime.utcnow()
    else:
        secret.is_exception = False
        secret.exception_comment = None
        secret.refuted_at = None
    
    db.commit()
    return {"status": "success"}

@app.post("/secrets/bulk-action")
async def bulk_secret_action(request: Request, _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    secret_ids = data.get("secret_ids", [])
    action = data.get("action")
    value = data.get("value", "")
    comment = data.get("comment", "")
    
    secrets = db.query(Secret).filter(Secret.id.in_(secret_ids)).all()
    
    for secret in secrets:
        if action == "status":
            secret.status = value
            if value == "Refuted":
                secret.is_exception = True
                secret.exception_comment = comment
                secret.refuted_at = datetime.utcnow()
            else:
                secret.is_exception = False
                secret.exception_comment = None
                secret.refuted_at = None
        elif action == "severity":
            secret.severity = value
    
    db.commit()
    return {"status": "success"}

@app.post("/scan/{scan_id}/delete")
async def delete_scan(scan_id: str, _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    project_name = scan.project_name
    
    # Delete all secrets and exceptions related to this scan
    db.query(Secret).filter(Secret.scan_id == scan_id).delete()
    
    # Delete the scan itself
    db.delete(scan)
    db.commit()
    
    return RedirectResponse(url=f"/project/{project_name}?success=scan_deleted", status_code=302)

@app.get("/scan/{scan_id}/export")
async def export_scan_results(scan_id: str, _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    # Get non-exception secrets
    secrets = db.query(Secret).filter(
        Secret.scan_id == scan_id,
        Secret.is_exception == False
    ).all()
    
    # Create export data (without actual secrets)
    export_data = [
        {
            "path": secret.path,
            "line": secret.line
        }
        for secret in secrets
    ]
    
    # Generate filename
    commit_short = scan.repo_commit[:7] if scan.repo_commit else "unknown"
    filename = f"{scan.project_name}_{commit_short}.json"
    
    return JSONResponse(
        content=export_data,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

def create_database_backup():
    """Create a database backup with timestamp"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"secrets_scanner_backup_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        # Get the database file path
        if "sqlite" in DATABASE_URL:
            db_file = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
            if os.path.exists(db_file):
                shutil.copy2(db_file, backup_path)
                backup_logger.info(f"Database backup created: {backup_path}")
                return backup_path
            else:
                backup_logger.error(f"Database file not found: {db_file}")
                return None
        else:
            # For non-SQLite databases, you'd implement pg_dump, mysqldump, etc.
            backup_logger.warning("Backup only implemented for SQLite databases")
            return None
            
    except Exception as e:
        backup_logger.error(f"Backup failed: {str(e)}")
        return None

def cleanup_old_backups():
    """Remove backups older than retention period"""
    try:
        cutoff_date = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
        backup_dir = Path(BACKUP_DIR)
        
        removed_count = 0
        for backup_file in backup_dir.glob("secrets_scanner_backup_*.db"):
            if backup_file.stat().st_mtime < cutoff_date.timestamp():
                backup_file.unlink()
                removed_count += 1
                backup_logger.info(f"Removed old backup: {backup_file.name}")
        
        if removed_count > 0:
            backup_logger.info(f"Cleaned up {removed_count} old backups")
            
    except Exception as e:
        backup_logger.error(f"Backup cleanup failed: {str(e)}")

async def backup_scheduler():
    """Background task to handle regular backups"""
    while True:
        try:
            # Create backup
            backup_path = create_database_backup()
            
            if backup_path:
                # Cleanup old backups after successful backup
                cleanup_old_backups()
            
            # Wait for next backup interval
            await asyncio.sleep(BACKUP_INTERVAL_HOURS * 3600)
            
        except Exception as e:
            backup_logger.error(f"Backup scheduler error: {str(e)}")
            # Wait 1 hour before retrying on error
            await asyncio.sleep(3600)

@app.get("/admin/backup-status")
async def backup_status(_: bool = Depends(get_current_user)):
    """Get backup configuration and status"""
    try:
        backup_dir = Path(BACKUP_DIR)
        backups = []
        
        if backup_dir.exists():
            for backup_file in sorted(backup_dir.glob("secrets_scanner_backup_*.db"), reverse=True):
                stat = backup_file.stat()
                backups.append({
                    "filename": backup_file.name,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
        
        return {
            "status": "success",
            "config": {
                "backup_dir": BACKUP_DIR,
                "retention_days": BACKUP_RETENTION_DAYS,
                "interval_hours": BACKUP_INTERVAL_HOURS
            },
            "backups": backups[:10]  # Show last 10 backups
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/admin/backup")
async def manual_backup(_: bool = Depends(get_current_user)):
    """Manually trigger a database backup"""
    backup_path = create_database_backup()
    if backup_path:
        return {"status": "success", "message": f"Backup created: {os.path.basename(backup_path)}"}
    else:
        return {"status": "error", "message": "Backup failed"}

@app.get("/admin/backups")
async def list_backups(_: bool = Depends(get_current_user)):
    """List available backups"""
    try:
        backup_dir = Path(BACKUP_DIR)
        backups = []
        
        for backup_file in sorted(backup_dir.glob("secrets_scanner_backup_*.db"), reverse=True):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        
        return {"status": "success", "backups": backups}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Start background task
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(check_scan_timeouts())
    asyncio.create_task(backup_scheduler())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)