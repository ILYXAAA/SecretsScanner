from fastapi import FastAPI, Request, Form, Depends, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
# from fastapi.security import HTTPBearer
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text, Boolean, func, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from contextlib import asynccontextmanager
import uuid
import json
import httpx
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import urllib.parse
from typing import Optional, List
import os
from pathlib import Path
import shutil
from dotenv import load_dotenv, set_key
from jose import JWTError, jwt
import secrets
import html
from utils.html_report_generator import generate_html_report
from passlib.context import CryptContext
# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

os.system("") # Для цветной консоли
# Load environment variables
load_dotenv()

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 часов

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    task1 = asyncio.create_task(check_scan_timeouts())
    task2 = asyncio.create_task(backup_scheduler())
    
    yield
    
    # Shutdown
    task1.cancel()
    task2.cancel()
    try:
        await task1
    except asyncio.CancelledError:
        pass
    try:
        await task2
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Secrets Scanner", lifespan=lifespan)

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
MICROSERVICE_URL = os.getenv("MICROSERVICE_URL")
APP_HOST = os.getenv("APP_HOST")
APP_PORT = int(os.getenv("APP_PORT"))
HUB_TYPE = os.getenv("HUB_TYPE", "Azure")  # Git or Azure

# Backup configuration
BACKUP_DIR = os.getenv("BACKUP_DIR", "./backups")
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "7"))
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
# Create backup directory
Path(BACKUP_DIR).mkdir(exist_ok=True)
# Setup logging for backups
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('secrets_scanner.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'),
        logging.StreamHandler()  # Также выводить в консоль
    ]
)
backup_logger = logging.getLogger("backup")
logger = logging.getLogger("main")

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
        return datetime.fromtimestamp(timestamp).strftime('%d.%m.%Y %H:%M:%S')
    return 'Unknown'

# def basename_filter(path):
#     if path:
#         return path.split('/')[-1]
#     return ''

def urldecode_filter(text):
    if text:
        return urllib.parse.unquote(text)
    return ''

templates.env.filters['tojson'] = tojson_filter
templates.env.filters['strftime'] = datetime_filter
# templates.env.filters['basename'] = basename_filter
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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(String, nullable=True)

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
    started_by = Column(String, nullable=True)

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
    refuted_at = Column(DateTime)  # Field for tracking when secret was refuted
    confirmed_by = Column(String, nullable=True)
    refuted_by = Column(String, nullable=True)

class AuthenticationException(Exception):
    pass

class MultiScan(Base):
    __tablename__ = "multi_scans"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True)
    scan_ids = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    name = Column(String)

# Отдельный Base для пользователей
UserBase = declarative_base()
class User(UserBase):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

def ensure_user_database():
    auth_dir = Path("Auth")
    auth_dir.mkdir(exist_ok=True)
    
    USERS_DATABASE_URL = os.getenv("USERS_DATABASE_URL", "sqlite:///./Auth/users.db")
    user_engine = create_engine(USERS_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in USERS_DATABASE_URL else {})
    UserBase.metadata.create_all(bind=user_engine)
    logger.info("User database initialized")
ensure_user_database()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user_db():
    auth_dir = Path("Auth")
    auth_dir.mkdir(exist_ok=True)
    
    USERS_DATABASE_URL = os.getenv("USERS_DATABASE_URL", "sqlite:///./Auth/users.db")
    user_engine = create_engine(USERS_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in USERS_DATABASE_URL else {})
    
    UserBase.metadata.create_all(bind=user_engine)
    
    UserSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=user_engine)
    db = UserSessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_indexes():
    """Создание индексов для оптимизации производительности"""
    try:
        with engine.connect() as conn:
            # Композитный индекс для поиска похожих секретов
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_secrets_composite ON secrets (path, line, secret, type)"))
            
            # Индекс для фильтрации по scan_id и is_exception
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_secrets_scan_exception ON secrets (scan_id, is_exception)"))
            
            # Индекс для фильтрации по severity
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_secrets_severity ON secrets (scan_id, severity, is_exception)"))
            
            # Индекс для фильтрации по type
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_secrets_type ON secrets (scan_id, type, is_exception)"))
            
            # Индекс для поиска секретов по проекту и времени
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scans_project_time ON scans (project_name, completed_at)"))
            
            # Индекс для статуса сканов
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scans_status ON scans (status, started_at)"))
            
            conn.commit()
            logger.info("Database indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")


# Функция миграции БД т.к. добавлен новый функционал
def migrate_database():
    """Add new columns for user tracking"""
    try:
        with engine.connect() as conn:
            # Check if columns exist before adding them
            try:
                conn.execute(text("SELECT started_by FROM scans LIMIT 1"))
            except:
                conn.execute(text("ALTER TABLE scans ADD COLUMN started_by TEXT"))
                logger.info("Added started_by column to scans table")
            
            try:
                conn.execute(text("SELECT created_by FROM projects LIMIT 1"))
            except:
                conn.execute(text("ALTER TABLE projects ADD COLUMN created_by TEXT"))
                logger.info("Added created_by column to projects table")
            
            try:
                conn.execute(text("SELECT confirmed_by FROM secrets LIMIT 1"))
            except:
                conn.execute(text("ALTER TABLE secrets ADD COLUMN confirmed_by TEXT"))
                logger.info("Added confirmed_by column to secrets table")
            
            try:
                conn.execute(text("SELECT refuted_by FROM secrets LIMIT 1"))
            except:
                conn.execute(text("ALTER TABLE secrets ADD COLUMN refuted_by TEXT"))
                logger.info("Added refuted_by column to secrets table")
            
            # Add multi_scans table
            try:
                conn.execute(text("SELECT id FROM multi_scans LIMIT 1"))
            except:
                conn.execute(text("""
                    CREATE TABLE multi_scans (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        scan_ids TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        name TEXT
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_multi_scans_user ON multi_scans (user_id)"))
                logger.info("Created multi_scans table")
            
            conn.commit()
            logger.info("Database migration completed successfully")
    except Exception as e:
        logger.error(f"Error during database migration: {e}")

Base.metadata.create_all(bind=engine)
migrate_database()  # Миграция БД новый функционал
create_indexes()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except JWTError:
        return None

# Обработчик исключений
@app.exception_handler(AuthenticationException)
async def auth_exception_handler(request: Request, exc: AuthenticationException):
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(key="auth_token")  # Удаляем невалидный токен
    return response

async def get_current_user(request: Request):
    token = request.cookies.get("auth_token")
    if not token:
        raise AuthenticationException()
    
    username = verify_token(token)
    if not username:
        raise AuthenticationException()
    
    # Check if user exists in database
    auth_dir = Path("Auth")
    auth_dir.mkdir(exist_ok=True)
    
    USERS_DATABASE_URL = os.getenv("USERS_DATABASE_URL", "sqlite:///./Auth/users.db")
    user_engine = create_engine(USERS_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in USERS_DATABASE_URL else {})
    UserSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=user_engine)
    user_db = UserSessionLocal()
    
    try:
        user = user_db.query(User).filter(User.username == username).first()
        if not user:
            raise AuthenticationException()
    finally:
        user_db.close()
    
    return username

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Authentication
# security = HTTPBearer()

# def load_credentials():
#     try:
#         LOGIN_FILE = "Auth/login.dat"
#         PASSWORD_FILE = "Auth/password.dat"
#         username = decrypt_from_file(LOGIN_FILE, key_name="LOGIN_KEY")
#         password = decrypt_from_file(PASSWORD_FILE, key_name="PASSWORD_KEY")
#         return [username, password]
#     except Exception as error:
#         logger.error(f"Error: {str(error)}")
#         logger.error("Если это первый запуск - необходимо запустить мастер настройки Auth данных `python CredsManager.py`")

#     return None

def verify_credentials(username: str, password: str, user_db: Session):
    user = user_db.query(User).filter(User.username == username).first()
    if user and verify_password(password, user.password_hash):
        return True
    return False

async def check_scan_timeouts():
    while True:
        try:
            db = SessionLocal()
            timeout_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)
            
            # Find running scans that started more than 10 minutes ago
            timed_out_scans = db.query(Scan).filter(
                Scan.status == "running",
                Scan.started_at < timeout_threshold
            ).all()
            
            for scan in timed_out_scans:
                scan.status = "timeout"
                scan.completed_at = datetime.now(timezone.utc)
            
            if timed_out_scans:
                db.commit()
                logger.warning(f"Marked {len(timed_out_scans)} scans as timed out")
            
            db.close()
        except Exception as e:
            logger.error(f"Error checking scan timeouts: {e}")
        
        # Check every minute
        await asyncio.sleep(60)

def get_auth_headers():
    load_dotenv(override=True)
    API_KEY = os.getenv("API_KEY")
    if not API_KEY:
        raise ValueError("API_KEY must be set in .env file")
    """Get headers with API key for microservice requests"""
    return {"X-API-Key": API_KEY}

async def check_microservice_health():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/health", timeout=5.0, headers=get_auth_headers())
            return response.status_code == 200
    except:
        return False


def get_scan_statistics(db: Session, scan_id: str):
    """Get high and potential secret counts for a scan"""
    high_count = db.query(func.count(Secret.id)).filter(
        Secret.scan_id == scan_id,
        Secret.severity == "High",
        Secret.is_exception == False
    ).scalar() or 0
    
    potential_count = db.query(func.count(Secret.id)).filter(
        Secret.scan_id == scan_id,
        Secret.severity == "Potential",
        Secret.is_exception == False
    ).scalar() or 0
    
    return high_count, potential_count

# Favicon route
@app.get("/favicon.ico")
async def favicon():
    favicon_path = Path("ico/favicon.ico")
    if favicon_path.exists():
        return FileResponse("ico/favicon.ico")
    else:
        raise HTTPException(status_code=404, detail="Favicon not found")

# Routes
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    token = request.cookies.get("auth_token")
    if token:
        username = verify_token(token)
        if username:
            # Проверяем существование пользователя
            USERS_DATABASE_URL = os.getenv("USERS_DATABASE_URL", "sqlite:///./Auth/users.db")
            user_engine = create_engine(USERS_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in USERS_DATABASE_URL else {})
            UserSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=user_engine)
            user_db = UserSessionLocal()
            
            try:
                user = user_db.query(User).filter(User.username == username).first()
                if user:
                    return RedirectResponse(url="/dashboard", status_code=302)
            finally:
                user_db.close()
        
        # Токен невалиден или пользователь не существует - удаляем cookie
        response = templates.TemplateResponse("login.html", {"request": request})
        response.delete_cookie(key="auth_token")
        return response
    
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), user_db: Session = Depends(get_user_db)):
    if verify_credentials(username, password, user_db):
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": username}, expires_delta=access_token_expires
        )
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(
            key="auth_token", 
            value=access_token, 
            httponly=True,
            secure=True if os.getenv("HTTPS", "false").lower() == "true" else False,
            samesite="strict",
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(key="auth_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, page: int = 1, search: str = "", current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    per_page = 10
    offset = (page - 1) * per_page
    
    # Оптимизированный запрос для получения recent scans с статистикой
    recent_scans_query = db.query(
        Scan,
        func.count(Secret.id).filter(Secret.severity == 'High', Secret.is_exception == False).label('high_count'),
        func.count(Secret.id).filter(Secret.severity == 'Potential', Secret.is_exception == False).label('potential_count')
    ).outerjoin(Secret, Scan.id == Secret.scan_id).group_by(Scan.id).order_by(Scan.started_at.desc()).limit(20)
    
    recent_scans_data = []
    for scan, high_count, potential_count in recent_scans_query.all():
        recent_scans_data.append({
            "scan": scan,
            "high_count": high_count or 0,
            "potential_count": potential_count or 0
        })
    
    # Оптимизированный запрос проектов с пагинацией и поиском по названию и репозиторию
    projects_query = db.query(Project)
    if search:
        projects_query = projects_query.filter(
            Project.name.contains(search) | Project.repo_url.contains(search)
        )
    
    total_projects = projects_query.count()
    projects_list = projects_query.offset(offset).limit(per_page).all()
    
    # Получить последние сканы для проектов одним запросом
    project_names = [p.name for p in projects_list]
    latest_scans_subquery = db.query(
        Scan.project_name,
        func.max(Scan.started_at).label('max_date')
    ).filter(Scan.project_name.in_(project_names)).group_by(Scan.project_name).subquery()
    
    latest_scans = db.query(Scan).join(
        latest_scans_subquery,
        (Scan.project_name == latest_scans_subquery.c.project_name) &
        (Scan.started_at == latest_scans_subquery.c.max_date)
    ).all()
    
    # Создать словарь для быстрого поиска
    scans_dict = {scan.project_name: scan for scan in latest_scans}
    
    # Получить статистику для latest scans одним запросом
    completed_scan_ids = [scan.id for scan in latest_scans if scan.status == 'completed']
    if completed_scan_ids:
        stats_query = db.query(
            Secret.scan_id,
            func.count(Secret.id).filter(Secret.severity == 'High').label('high_count'),
            func.count(Secret.id).filter(Secret.severity == 'Potential').label('potential_count')
        ).filter(
            Secret.scan_id.in_(completed_scan_ids),
            Secret.is_exception == False
        ).group_by(Secret.scan_id).all()
        
        stats_dict = {stat.scan_id: (stat.high_count, stat.potential_count) for stat in stats_query}
    else:
        stats_dict = {}
    
    projects_data = []
    for project in projects_list:
        latest_scan = scans_dict.get(project.name)
        high_count = 0
        potential_count = 0
        
        if latest_scan and latest_scan.status == 'completed':
            high_count, potential_count = stats_dict.get(latest_scan.id, (0, 0))
        
        projects_data.append({
            "project": project,
            "latest_scan": latest_scan,
            "high_count": high_count,
            "potential_count": potential_count,
            "latest_scan_date": latest_scan.started_at if latest_scan else datetime.min
        })
    
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
        "HUB_TYPE": HUB_TYPE,
        "current_user": current_user
    })

@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, current_user: str = Depends(get_current_user)):
   # Get current API key
   current_api_key = get_current_api_key()
   if current_api_key != "Not set":
       current_api_key = current_api_key[:4] + "*" * (len(current_api_key) - 4)
   # Get current PAT token
   current_token = "Not set"
   microservice_available = True
   
   try:
       async with httpx.AsyncClient() as client:
           response = await client.get(f"{MICROSERVICE_URL}/get-pat", headers=get_auth_headers(), timeout=5.0)
           if response.status_code == 200:
               data = response.json()
               if data.get("status") == "success":
                   current_token = data.get("token", "Not set")
   except:
       current_token = "Error: microservice unavailable"
       microservice_available = False
   
   # Get rules info and content
   rules_info = None
   current_rules_content = ""
   
   if microservice_available:
       try:
           async with httpx.AsyncClient() as client:
               # Get rules info
               info_response = await client.get(f"{MICROSERVICE_URL}/rules-info", headers=get_auth_headers(), timeout=5.0)
               
               if info_response.status_code == 200:
                   rules_info = info_response.json()
                   
                   # If rules exist, get their content
                   if rules_info and rules_info.get("exists", False):
                       rules_response = await client.get(f"{MICROSERVICE_URL}/get-rules", timeout=5.0, headers=get_auth_headers())
                       
                       if rules_response.status_code == 200:
                           rules_data = rules_response.json()
                           if rules_data.get("status") == "success":
                               current_rules_content = rules_data.get("rules", "")
               else:
                   rules_info = {"error": "microservice_unavailable"}
       except Exception as e:
           logger.error(f"Error fetching rules: {e}")
           rules_info = {"error": "microservice_unavailable"}
   else:
       rules_info = {"error": "microservice_unavailable"}
   
   # Get False-Positive rules info and content
   fp_rules_info = None
   current_fp_rules_content = ""
   
   if microservice_available:
       try:
           async with httpx.AsyncClient() as client:
               # Get FP rules info
               info_response = await client.get(f"{MICROSERVICE_URL}/rules-fp-info", timeout=5.0, headers=get_auth_headers())
               
               if info_response.status_code == 200:
                   fp_rules_info = info_response.json()
                   
                   # If FP rules exist, get their content
                   if fp_rules_info and fp_rules_info.get("exists", False):
                       fp_rules_response = await client.get(f"{MICROSERVICE_URL}/get-fp-rules", timeout=5.0, headers=get_auth_headers())
                       
                       if fp_rules_response.status_code == 200:
                           fp_rules_data = fp_rules_response.json()
                           if fp_rules_data.get("status") == "success":
                               current_fp_rules_content = fp_rules_data.get("fp_rules", "")
       except Exception as e:
           logger.error(f"Error fetching FP rules: {e}")
           fp_rules_info = {"error": "microservice_unavailable"}
   else:
       fp_rules_info = {"error": "microservice_unavailable"}
   
   # Get excluded extensions info and content
   excluded_extensions_info = None
   current_excluded_extensions_content = ""
   
   if microservice_available:
       try:
           async with httpx.AsyncClient() as client:
               # Get excluded extensions info
               info_response = await client.get(f"{MICROSERVICE_URL}/excluded-extensions-info", timeout=5.0, headers=get_auth_headers())
               
               if info_response.status_code == 200:
                   excluded_extensions_info = info_response.json()
                   
                   # If file exists, get content
                   if excluded_extensions_info and excluded_extensions_info.get("exists", False):
                       content_response = await client.get(f"{MICROSERVICE_URL}/get-excluded-extensions", timeout=5.0, headers=get_auth_headers())
                       
                       if content_response.status_code == 200:
                           content_data = content_response.json()
                           if content_data.get("status") == "success":
                               current_excluded_extensions_content = content_data.get("excluded_extensions", "")
       except Exception as e:
           logger.error(f"Error fetching excluded extensions: {e}")
           excluded_extensions_info = {"error": "microservice_unavailable"}
   else:
       excluded_extensions_info = {"error": "microservice_unavailable"}
   
   # Get excluded files info and content
   excluded_files_info = None
   current_excluded_files_content = ""
   
   if microservice_available:
       try:
           async with httpx.AsyncClient() as client:
               # Get excluded files info
               info_response = await client.get(f"{MICROSERVICE_URL}/excluded-files-info", timeout=5.0, headers=get_auth_headers())
               
               if info_response.status_code == 200:
                   excluded_files_info = info_response.json()
                   
                   # If file exists, get content
                   if excluded_files_info and excluded_files_info.get("exists", False):
                       content_response = await client.get(f"{MICROSERVICE_URL}/get-excluded-files", timeout=5.0, headers=get_auth_headers())
                       
                       if content_response.status_code == 200:
                           content_data = content_response.json()
                           if content_data.get("status") == "success":
                               current_excluded_files_content = content_data.get("excluded_files", "")
       except Exception as e:
           logger.error(f"Error fetching excluded files: {e}")
           excluded_files_info = {"error": "microservice_unavailable"}
   else:
       excluded_files_info = {"error": "microservice_unavailable"}
   
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
       "current_user": current_user
   })

@app.post("/settings/change-password")
async def change_password(request: Request, current_password: str = Form(...), 
                         new_password: str = Form(...), confirm_password: str = Form(...),
                         current_user: str = Depends(get_current_user), user_db: Session = Depends(get_user_db)):
    try:
        # Validate passwords match
        if new_password != confirm_password:
            return RedirectResponse(url="/settings?error=password_mismatch", status_code=302)
        
        # Get current user from database
        user = user_db.query(User).filter(User.username == current_user).first()
        if not user:
            return RedirectResponse(url="/settings?error=user_not_found", status_code=302)
        
        # Verify current password
        if not verify_password(current_password, user.password_hash):
            return RedirectResponse(url="/settings?error=password_change_failed", status_code=302)
        
        # Update password
        user.password_hash = get_password_hash(new_password)
        user_db.commit()
        
        return RedirectResponse(url="/settings?success=password_changed", status_code=302)
        
    except Exception as e:
        logger.error(f"Password change error: {e}")
        return RedirectResponse(url="/settings?error=password_change_failed", status_code=302)

@app.post("/settings/update-api-key")
async def update_api_key(request: Request, api_key: str = Form(...), _: bool = Depends(get_current_user)):
    try:
        if update_api_key_in_env(api_key):
            return RedirectResponse(url="/settings?success=api_key_updated", status_code=302)
        else:
            return RedirectResponse(url="/settings?error=api_key_update_failed", status_code=302)
    except Exception as e:
        logger.error(f"API key update error: {e}")
        return RedirectResponse(url="/settings?error=api_key_update_failed", status_code=302)

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

@app.post("/settings/update-fp-rules")
async def update_fp_rules(request: Request, fp_rules_content: str = Form(...), _: bool = Depends(get_current_user)):
    try:
        if not fp_rules_content.strip():
            return RedirectResponse(url="/settings?error=empty_content", status_code=302)
        
        # Send content to microservice
        payload = {
            "content": fp_rules_content
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{MICROSERVICE_URL}/update-fp-rules",
                json=payload, headers=get_auth_headers()
            )
            
            if response.status_code == 200:
                return RedirectResponse(url="/settings?success=fp_rules_updated", status_code=302)
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get("message", f"Microservice error: HTTP {response.status_code}")
                except:
                    error_message = f"Microservice error: HTTP {response.status_code}"
                
                encoded_error = urllib.parse.quote(error_message)
                return RedirectResponse(url=f"/settings?error={encoded_error}", status_code=302)
                
    except Exception as e:
        logger.error(f"FP rules update error: {e}")
        import traceback
        traceback.print_exc()
        error_message = f"Update error: {str(e)}"
        encoded_error = urllib.parse.quote(error_message)
        return RedirectResponse(url=f"/settings?error={encoded_error}", status_code=302)

@app.post("/settings/update-token")
async def update_token(request: Request, token: str = Form(...), _: bool = Depends(get_current_user)):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{MICROSERVICE_URL}/set-pat", 
                                       json={"token": token}, headers=get_auth_headers(), timeout=10.0)
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
                f"{MICROSERVICE_URL}/update-rules", headers=get_auth_headers(),
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
        logger.error(f"Rules update error: {e}")
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
                json=payload, headers=get_auth_headers()
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
        logger.error(f"Excluded extensions update error: {e}")
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
                json=payload, headers=get_auth_headers()
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
        logger.error(f"Excluded files update error: {e}")
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
                     current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        validate_repo_url(repo_url, HUB_TYPE)
        
        existing = db.query(Project).filter(Project.name == project_name).first()
        if existing:
            return RedirectResponse(url="/dashboard?error=project_exists", status_code=302)
        
        project = Project(name=project_name, repo_url=repo_url, created_by=current_user)  # Добавлен created_by
        db.add(project)
        db.commit()
        
        return RedirectResponse(url=f"/project/{project_name}", status_code=302)
    
    except ValueError as e:
        encoded_error = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/dashboard?error={encoded_error}", status_code=302)
    except Exception as e:
        logger.error(f"Error adding project: {e}")
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
        logger.error(f"Error updating project: {e}")
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
async def project_page(request: Request, project_name: str, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
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
        "HUB_TYPE": HUB_TYPE,
        "current_user": current_user
    })

@app.post("/project/{project_name}/scan")
async def start_scan(request: Request, project_name: str, ref_type: str = Form(...), 
                    ref: str = Form(...), current_user: str = Depends(get_current_user), _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check microservice health
    if not await check_microservice_health():
        return RedirectResponse(url=f"/project/{project_name}?error=microservice_unavailable", status_code=302)
    
    # Create scan record with 'pending' status
    scan_id = str(uuid.uuid4())
    scan = Scan(
        id=scan_id, 
        project_name=project_name, 
        ref_type=ref_type, 
        ref=ref, 
        status="pending",
        started_by=current_user
    )
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
            }, headers=get_auth_headers(), timeout=30.0)
            
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

@app.post("/project/{project_name}/local-scan")
async def start_local_scan(request: Request, project_name: str, 
                          commit: str = Form(...), zip_file: UploadFile = File(...),
                          _: bool = Depends(get_current_user), current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check microservice health
    if not await check_microservice_health():
        return RedirectResponse(url=f"/project/{project_name}?error=microservice_unavailable", status_code=302)
    
    # Validate file type
    if not zip_file.filename.endswith('.zip'):
        return RedirectResponse(url=f"/project/{project_name}?error=invalid_file_format", status_code=302)
    
    # Create scan record
    scan_id = str(uuid.uuid4())
    scan = Scan(
        id=scan_id, 
        project_name=project_name, 
        ref_type="Commit", 
        ref=commit, 
        repo_commit=commit,
        status="pending",
        started_by=current_user
    )
    db.add(scan)
    db.commit()
    
    # Prepare callback URL
    callback_url = f"http://{APP_HOST}:{APP_PORT}/get_results/{project_name}/{scan_id}"
    
    try:
        # Read file content BEFORE creating the request
        file_content = await zip_file.read()
        
        # Reset file pointer and create new file-like object
        from io import BytesIO
        file_obj = BytesIO(file_content)
        
        # Create form data
        files = {
            'zip_file': (zip_file.filename, file_obj, 'application/zip')
        }
        data = {
            'ProjectName': project_name,
            'RepoUrl': project.repo_url,
            'CallbackUrl': callback_url,
            'RefType': 'Commit',
            'Ref': commit
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{MICROSERVICE_URL}/local_scan",
                files=files, headers=get_auth_headers(),
                data=data
            )
            
            try:
                result = response.json()
            except:
                scan.status = "failed"
                scan.error_message = "Invalid response from microservice"
                db.commit()
                return RedirectResponse(url=f"/project/{project_name}?error=microservice_invalid_response", status_code=302)
            
            if response.status_code == 200 and result.get("status") == "accepted":
                scan.status = "running"
                db.commit()
                return RedirectResponse(url=f"/scan/{scan_id}", status_code=302)
            else:
                scan.status = "failed"
                scan.error_message = result.get("message", "Unknown error")
                db.commit()
                error_msg = result.get("message", "Unknown error from microservice")
                encoded_error = urllib.parse.quote(error_msg)
                return RedirectResponse(url=f"/project/{project_name}?error={encoded_error}", status_code=302)
                
    except httpx.TimeoutException:
        scan.status = "failed"
        scan.error_message = "Microservice timeout"
        db.commit()
        return RedirectResponse(url=f"/project/{project_name}?error=microservice_timeout", status_code=302)
    except Exception as e:
        scan.status = "failed"
        scan.error_message = str(e)
        db.commit()
        return RedirectResponse(url=f"/project/{project_name}?error=local_scan_failed", status_code=302)

@app.get("/scan/{scan_id}", response_class=HTMLResponse)
async def scan_status(request: Request, scan_id: str, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    return templates.TemplateResponse("scan_status.html", {
        "request": request,
        "scan": scan,
        "current_user": current_user
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
        scan.completed_at = datetime.now(timezone.utc)
        error_message = data.get("Message", "Unknown error occurred during scanning")
        logger.error(f"Scan {scan_id} failed with error: {error_message}")
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
        scan.completed_at = datetime.now(timezone.utc)
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
                refuted_at=refuted_at,
                confirmed_by=most_recent_secret.confirmed_by if most_recent_secret else None,
                refuted_by=most_recent_secret.refuted_by if most_recent_secret else None
            )
            db.add(secret)
        
        db.commit()
        return {"status": "success"}

    # If status is not recognized, treat as error
    return {"status": "error", "message": "Unknown status received"}

@app.get("/scan/{scan_id}/results", response_class=HTMLResponse)
async def scan_results(request: Request, scan_id: str, severity_filter: str = "", 
                     type_filter: str = "", show_exceptions: bool = False,
                     current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    # Get project info
    project = db.query(Project).filter(Project.name == scan.project_name).first()
    
    # Получить ВСЕ секреты для JavaScript (БЕЗ фильтрации на стороне сервера)
    all_secrets_query = db.query(Secret).filter(Secret.scan_id == scan_id).order_by(
        Secret.severity == 'Potential',
        Secret.path,
        Secret.line
    ).all()
    
    # Исправленный подсчет статистики - отдельными запросами
    total_secrets = db.query(func.count(Secret.id)).filter(
        Secret.scan_id == scan_id,
        Secret.is_exception == False
    ).scalar() or 0
    
    high_secrets = db.query(func.count(Secret.id)).filter(
        Secret.scan_id == scan_id,
        Secret.severity == 'High',
        Secret.is_exception == False
    ).scalar() or 0
    
    potential_secrets = db.query(func.count(Secret.id)).filter(
        Secret.scan_id == scan_id,
        Secret.severity == 'Potential',
        Secret.is_exception == False
    ).scalar() or 0
    
    # Получить уникальные типы и severity отдельными эффективными запросами
    unique_types_query = db.query(Secret.type.distinct()).filter(Secret.scan_id == scan_id)
    unique_types = [row[0] for row in unique_types_query.all() if row[0]]
    
    unique_severities_query = db.query(Secret.severity.distinct()).filter(Secret.scan_id == scan_id)
    unique_severities = [row[0] for row in unique_severities_query.all() if row[0]]
    
    # Инициализируем переменные в начале
    secrets_data = []
    previous_secrets_map = {}
    previous_scans = []
    
    # Оптимизированный поиск предыдущих статусов только для небольших наборов
    if all_secrets_query and len(all_secrets_query) < 500:  # Только для небольших наборов
        # Получить все предыдущие сканы одним запросом
        previous_scans = db.query(Scan.id, Scan.completed_at).filter(
            Scan.project_name == scan.project_name,
            Scan.id != scan_id,
            Scan.completed_at < scan.completed_at
        ).order_by(Scan.completed_at.desc()).all()
        
        previous_scan_ids = [s.id for s in previous_scans]
        
        # Получить все предыдущие секреты одним запросом
        if previous_scan_ids:
            previous_secrets = db.query(Secret).filter(
                Secret.scan_id.in_(previous_scan_ids),
                Secret.status != "No status"
            ).all()
            
            # Создать карту для быстрого поиска
            for prev_secret in previous_secrets:
                key = (prev_secret.path, prev_secret.line, prev_secret.secret, prev_secret.type)
                if key not in previous_secrets_map:
                    previous_secrets_map[key] = prev_secret
    
    # Обработка секретов
    for secret in all_secrets_query:
        previous_status = None
        previous_scan_date = None
        
        if previous_secrets_map:
            key = (secret.path, secret.line, secret.secret, secret.type)
            if key in previous_secrets_map:
                prev_secret = previous_secrets_map[key]
                previous_status = prev_secret.status
                # Найти дату скана для этого секрета
                for scan_info in previous_scans:
                    if prev_secret.scan_id == scan_info.id:
                        previous_scan_date = scan_info.completed_at.strftime('%Y-%m-%d %H:%M')
                        break
        
        # БЕЗОПАСНОЕ создание объекта секрета с экранированием
        secret_obj = {
            "id": secret.id,
            "path": html.escape(secret.path or "", quote=True),
            "line": secret.line or 0,
            "secret": html.escape(secret.secret or "", quote=True),
            "context": html.escape(secret.context or "", quote=True),
            "severity": html.escape(secret.severity or "", quote=True),
            "type": html.escape(secret.type or "", quote=True),
            "status": html.escape(secret.status or "No status", quote=True),
            "is_exception": bool(secret.is_exception),
            "exception_comment": html.escape(secret.exception_comment or "", quote=True),
            "refuted_at": secret.refuted_at.strftime('%Y-%m-%d %H:%M') if secret.refuted_at else None,
            "confirmed_by": secret.confirmed_by if secret.confirmed_by else None,
            "refuted_by": secret.refuted_by if secret.refuted_by else None,
            "previous_status": html.escape(previous_status or "", quote=True) if previous_status else None,
            "previous_scan_date": previous_scan_date
        }
        secrets_data.append(secret_obj)

    return templates.TemplateResponse("scan_results.html", {
        "request": request,
        "scan": scan,
        "project": project,
        # "secrets": all_secrets_query,  # Для обратной совместимости от предыдущей версии html шаблона. Сейчас уже работает нормально
        "secrets_data": secrets_data,  # Передаем как объект для скрытого элемента
        "project_repo_url": project.repo_url or "",
        "scan_commit": scan.repo_commit or "",
        "unique_types": unique_types,
        "unique_severities": unique_severities,
        "total_secrets": total_secrets,
        "high_secrets": high_secrets,
        "potential_secrets": potential_secrets,
        "hub_type": HUB_TYPE,
        "current_filters": {
            "severity": severity_filter,
            "type": type_filter,
            "show_exceptions": show_exceptions
        },
        "current_user": current_user
    })

@app.post("/secrets/{secret_id}/update-status")
async def update_secret_status(secret_id: int, status: str = Form(...), 
                              comment: str = Form(""), current_user: str = Depends(get_current_user), 
                              db: Session = Depends(get_db)):
    secret = db.query(Secret).filter(Secret.id == secret_id).first()
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    
    secret.status = status
    if status == "Refuted":
        secret.is_exception = True
        secret.exception_comment = comment
        secret.refuted_at = datetime.now(timezone.utc)
        secret.refuted_by = current_user
        secret.confirmed_by = None
    elif status == "Confirmed":
        secret.is_exception = False
        secret.exception_comment = None
        secret.refuted_at = None
        secret.confirmed_by = current_user
        secret.refuted_by = None
    else:
        secret.is_exception = False
        secret.exception_comment = None
        secret.refuted_at = None
        secret.confirmed_by = None
        secret.refuted_by = None
    
    db.commit()
    return {"status": "success"}

@app.post("/secrets/bulk-action")
async def bulk_secret_action(request: Request, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
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
                secret.refuted_at = datetime.now(timezone.utc)
                secret.refuted_by = current_user
                secret.confirmed_by = None
            elif value == "Confirmed":
                secret.is_exception = False
                secret.exception_comment = None
                secret.refuted_at = None
                secret.confirmed_by = current_user
                secret.refuted_by = None
            else:
                secret.is_exception = False
                secret.exception_comment = None
                secret.refuted_at = None
                secret.confirmed_by = None
                secret.refuted_by = None
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
    
    # Get only non-exception secrets from this scan
    secrets = db.query(Secret).filter(
        Secret.scan_id == scan_id,
        Secret.is_exception == False
    ).all()
    
    # Create export data (only path and line)
    export_data = [
        {
            "path": secret.path,
            "line": secret.line
        }
        for secret in secrets
    ]
    
    # Generate filename
    commit_short = scan.repo_commit[:7] if scan.repo_commit else "unknown"
    #scan_date = scan.completed_at.strftime("%Y%m%d") if scan.completed_at else "pending"
    filename = f"{scan.project_name}_{commit_short}.json"
    
    return JSONResponse(
        content=export_data,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/scan/{scan_id}/export-html")
async def export_scan_results_html(scan_id: str, _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    project = db.query(Project).filter(Project.name == scan.project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get only non-exception secrets from this scan (same as displayed on page)
    secrets = db.query(Secret).filter(
        Secret.scan_id == scan_id,
        Secret.is_exception == False
    ).order_by(
        Secret.severity == 'Potential',
        Secret.path,
        Secret.line
    ).all()
    
    # Generate HTML report
    html_content = generate_html_report(scan, project, secrets, HUB_TYPE)
    
    # Generate filename
    commit_short = scan.repo_commit[:7] if scan.repo_commit else "unknown"
    #scan_date = scan.completed_at.strftime("%Y%m%d") if scan.completed_at else "pending"
    filename = f"{scan.project_name}_{commit_short}.html"
    
    return HTMLResponse(
        content=html_content,
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
   # Create initial backup only if none exist
   backup_dir = Path(BACKUP_DIR)
   existing_backups = list(backup_dir.glob("secrets_scanner_backup_*.db"))
   
   if not existing_backups:
       backup_logger.info("No existing backups found, creating initial backup")
       backup_path = create_database_backup()
       if backup_path:
           cleanup_old_backups()
   else:
       backup_logger.info(f"Found {len(existing_backups)} existing backups, skipping initial backup")
   
   while True:
       try:
           # Wait for backup interval
           await asyncio.sleep(BACKUP_INTERVAL_HOURS * 3600)
           
           # Create backup after waiting
           backup_path = create_database_backup()
           
           if backup_path:
               cleanup_old_backups()
           
       except Exception as e:
           backup_logger.error(f"Backup scheduler error: {str(e)}")
           # Wait 1 hour before retrying on error
           await asyncio.sleep(3600)

@app.get("/admin/backup-status")
async def backup_status(_: bool = Depends(get_current_user)):
    """Get backup configuration and status"""
    try:
        backup_dir = Path(BACKUP_DIR)
        all_backups = []
        
        if backup_dir.exists():
            for backup_file in sorted(backup_dir.glob("secrets_scanner_backup_*.db"), 
                                    key=lambda x: x.stat().st_mtime, reverse=True):
                stat = backup_file.stat()
                all_backups.append({
                    "filename": backup_file.name,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
        
        response_data = {
            "status": "success",
            "config": {
                "backup_dir": str(BACKUP_DIR),
                "retention_days": BACKUP_RETENTION_DAYS,
                "interval_hours": BACKUP_INTERVAL_HOURS
            },
            "backups": all_backups[:20],  # Show only first 20
            "total_backups": len(all_backups),  # Total count
            "timestamp": datetime.now().isoformat()
        }
        
        return JSONResponse(
            content=response_data,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except Exception as e:
        logger.error(f"Backup status error: {e}")
        return JSONResponse(
            content={
                "status": "error", 
                "message": str(e),
                "config": {
                    "backup_dir": str(BACKUP_DIR),
                    "retention_days": BACKUP_RETENTION_DAYS,
                    "interval_hours": BACKUP_INTERVAL_HOURS
                },
                "backups": [],
                "total_backups": 0,
                "timestamp": datetime.now().isoformat()
            },
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )

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

@app.get("/multi-scan", response_class=HTMLResponse)
async def multi_scan_page(request: Request, current_user: str = Depends(get_current_user)):
    return templates.TemplateResponse("multi_scan.html", {
        "request": request,
        "current_user": current_user
    })

@app.get("/api/project/check")
async def check_project_exists(repo_url: str, _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    """Check if project exists by repo URL"""
    project = db.query(Project).filter(Project.repo_url == repo_url).first()
    if project:
        return {"exists": True, "project_name": project.name}
    else:
        return {"exists": False}

@app.get("/api/scan/{scan_id}/status")
async def get_scan_status(scan_id: str, _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get current scan status with statistics"""
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    # Get statistics if scan is completed
    high_count = 0
    potential_count = 0
    
    if scan.status == 'completed':
        high_count, potential_count = get_scan_statistics(db, scan_id)
    
    return {
        "scan_id": scan.id,
        "project_name": scan.project_name,
        "status": scan.status,
        "ref_type": scan.ref_type,
        "ref": scan.ref,
        "commit": scan.repo_commit,
        "started_at": scan.started_at.strftime('%Y-%m-%d %H:%M') if scan.started_at else None,
        "completed_at": scan.completed_at.strftime('%Y-%m-%d %H:%M') if scan.completed_at else None,
        "high_count": high_count,
        "potential_count": potential_count,
        "files_scanned": scan.files_scanned
    }

@app.post("/multi_scan")
async def multi_scan(request: Request, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
   """Handle multi-scan requests"""
   try:
       scan_requests = await request.json()
       
       if not isinstance(scan_requests, list) or len(scan_requests) == 0:
           return JSONResponse(
               status_code=400,
               content={"status": "error", "message": "Invalid request format"}
           )
       
       # Check microservice health
       if not await check_microservice_health():
           return JSONResponse(
               status_code=503,
               content={"status": "error", "message": "Микросервис недоступен"}
           )
       
       # Create multi-scan record
       multi_scan_id = str(uuid.uuid4())
       scan_ids = []
       
       # Create scan records in database
       scan_records = []
       for scan_request in scan_requests:
           # Extract scan ID from callback URL or generate new
           callback_url = scan_request.get("CallbackUrl", "")
           scan_id = callback_url.split("/")[-1] if callback_url else str(uuid.uuid4())
           scan_ids.append(scan_id)
           
           # Create scan record
           scan = Scan(
               id=scan_id,
               project_name=scan_request["ProjectName"],
               ref_type=scan_request["RefType"],
               ref=scan_request["Ref"],
               status="pending",
               started_by=current_user
           )
           db.add(scan)
           scan_records.append(scan)
       
       # Create multi-scan record
       multi_scan = MultiScan(
           id=multi_scan_id,
           user_id=current_user,
           scan_ids=json.dumps(scan_ids),
           name=f"Multi-scan {datetime.now().strftime('%Y-%m-%d %H:%M')}"
       )
       db.add(multi_scan)
       db.commit()
       
       # Send request to microservice
       try:
           async with httpx.AsyncClient(timeout=300.0) as client:  # 5 minutes timeout
               microservice_payload = {
                   "repositories": scan_requests
               }
               
               response = await client.post(
                   f"{MICROSERVICE_URL}/multi_scan",
                   json=microservice_payload, headers=get_auth_headers()
               )
               
               # Handle different response status codes
               if response.status_code == 200:
                   result = response.json()
                   
                   if result.get("status") == "accepted":
                       # All repositories resolved successfully - update scan records
                       scan_data_list = result.get("data", [])
                       for i, scan_record in enumerate(scan_records):
                           if i < len(scan_data_list):
                               scan_data = scan_data_list[i]
                               scan_record.status = "running"
                               scan_record.ref = scan_data.get("Ref", scan_record.ref)
                               scan_record.repo_commit = scan_data.get("commit")
                           else:
                               # Fallback if data is incomplete
                               scan_record.status = "running"
                       
                       db.commit()
                       
                       # Add base repo URLs to response data
                       for i, scan_data in enumerate(scan_data_list):
                           if i < len(scan_requests):
                               scan_data["BaseRepoUrl"] = scan_requests[i]["RepoUrl"]
                       
                       return JSONResponse(
                           status_code=200,
                           content={
                               "status": "accepted",
                               "message": result.get("message", "Мультисканирование добавлено в очередь"),
                               "data": scan_data_list,
                               "multi_scan_id": multi_scan_id,
                               "RepoUrl": result.get("RepoUrl", "Undefined")
                           }
                       )
                   
                   else:
                       # Unexpected status in 200 response
                       db.delete(multi_scan)
                       error_message = result.get("message", "Неизвестная ошибка")
                       for scan_record in scan_records:
                           scan_record.status = "failed"
                           scan_record.error_message = error_message
                       
                       db.commit()
                       return JSONResponse(
                           status_code=400,
                           content={
                               "status": "error",
                               "message": error_message
                           }
                       )
               
               elif response.status_code == 400:
                   # Validation failed - some repositories couldn't be resolved
                   try:
                       result = response.json()
                       if result.get("status") == "validation_failed":
                           scan_data_list = result.get("data", [])
                           
                           # Add base repo URLs to response data even for failed validation
                           for i, scan_data in enumerate(scan_data_list):
                               if i < len(scan_requests):
                                   scan_data["BaseRepoUrl"] = scan_requests[i]["RepoUrl"]
                           
                           # Update scan records based on validation results
                           for i, scan_record in enumerate(scan_records):
                               if i < len(scan_data_list):
                                   scan_data = scan_data_list[i]
                                   if scan_data.get("commit") == "not_found":
                                       scan_record.status = "failed"
                                       scan_record.error_message = "Failed to resolve commit"
                                   else:
                                       # This shouldn't happen in validation_failed, but handle it
                                       scan_record.status = "failed"
                                       scan_record.error_message = "Validation failed"
                               else:
                                   scan_record.status = "failed"
                                   scan_record.error_message = "Validation failed"
                           
                           db.commit()
                           return JSONResponse(
                               status_code=400,
                               content={
                                   "status": "validation_failed",
                                   "message": result.get("message", "Не удалось отрезолвить коммиты"),
                                   "data": scan_data_list
                               }
                           )
                       else:
                           # Other 400 error
                           db.delete(multi_scan)
                           error_message = result.get("message", "Ошибка валидации")
                           for scan_record in scan_records:
                               scan_record.status = "failed"
                               scan_record.error_message = error_message
                           
                           db.commit()
                           return JSONResponse(
                               status_code=400,
                               content={
                                   "status": "error",
                                   "message": error_message
                               }
                           )
                   except Exception as parse_error:
                       # Can't parse 400 response
                       db.delete(multi_scan)
                       error_message = "Ошибка валидации запроса"
                       for scan_record in scan_records:
                           scan_record.status = "failed"
                           scan_record.error_message = error_message
                       
                       db.commit()
                       return JSONResponse(
                           status_code=400,
                           content={
                               "status": "error",
                               "message": error_message
                           }
                       )
               
               elif response.status_code == 429:
                   # Queue is full
                   try:
                       result = response.json()
                       error_message = result.get("message", "Очередь переполнена")
                   except:
                       error_message = "Очередь переполнена"
                   
                   # Mark scans as failed due to queue overflow
                   db.delete(multi_scan)
                   for scan_record in scan_records:
                       scan_record.status = "failed"
                       scan_record.error_message = "Queue full"
                   
                   db.commit()
                   return JSONResponse(
                       status_code=429,
                       content={
                           "status": "queue_full",
                           "message": error_message
                       }
                   )
               
               else:
                   # Other HTTP error codes
                   try:
                       error_data = response.json()
                       error_message = error_data.get("message", error_data.get("detail", f"HTTP {response.status_code}"))
                   except:
                       error_message = f"HTTP {response.status_code}"
                   
                   # Mark all scans as failed
                   db.delete(multi_scan)
                   for scan_record in scan_records:
                       scan_record.status = "failed"
                       scan_record.error_message = f"Microservice error: {error_message}"
                   
                   db.commit()
                   
                   return JSONResponse(
                       status_code=response.status_code,
                       content={
                           "status": "error", 
                           "message": f"Ошибка микросервиса: {error_message}"
                       }
                   )
       
       except httpx.TimeoutException:
           # Mark all scans as failed due to timeout
           db.delete(multi_scan)
           for scan_record in scan_records:
               scan_record.status = "failed"
               scan_record.error_message = "Microservice timeout"
           
           db.commit()
           
           return JSONResponse(
               status_code=408,
               content={"status": "error", "message": "Таймаут микросервиса"}
           )
       
       except Exception as e:
           # Mark all scans as failed due to connection error
           db.delete(multi_scan)
           for scan_record in scan_records:
               scan_record.status = "failed"
               scan_record.error_message = f"Connection error: {str(e)}"
           
           db.commit()
           
           return JSONResponse(
               status_code=500,
               content={"status": "error", "message": "Ошибка соединения с микросервисом"}
           )
   
   except Exception as e:
       logger.error(f"Multi-scan error: {e}")
       import traceback
       traceback.print_exc()
       
       return JSONResponse(
           status_code=500,
           content={"status": "error", "message": "Внутренняя ошибка сервера"}
       )

@app.get("/api/multi-scans")
async def get_user_multi_scans(current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get all multi-scans for current user"""
    try:
        multi_scans = db.query(MultiScan).filter(
            MultiScan.user_id == current_user
        ).order_by(MultiScan.created_at.desc()).limit(10).all()
        
        result = []
        for multi_scan in multi_scans:
            scan_ids = json.loads(multi_scan.scan_ids)
            
            # Get scan details
            scans = db.query(Scan).filter(Scan.id.in_(scan_ids)).all()
            scans_data = []
            
            for scan in scans:
                high_count = 0
                potential_count = 0
                
                if scan.status == 'completed':
                    high_count, potential_count = get_scan_statistics(db, scan.id)
                
                scans_data.append({
                    "scan_id": scan.id,
                    "project_name": scan.project_name,
                    "status": scan.status,
                    "ref_type": scan.ref_type,
                    "ref": scan.ref,
                    "commit": scan.repo_commit,
                    "started_at": scan.started_at.strftime('%Y-%m-%d %H:%M') if scan.started_at else None,
                    "completed_at": scan.completed_at.strftime('%Y-%m-%d %H:%M') if scan.completed_at else None,
                    "high_count": high_count,
                    "potential_count": potential_count,
                    "files_scanned": scan.files_scanned
                })
            
            result.append({
                "multi_scan_id": multi_scan.id,
                "name": multi_scan.name,
                "created_at": multi_scan.created_at.strftime('%Y-%m-%d %H:%M'),
                "scans": scans_data
            })
        
        return {"status": "success", "multi_scans": result}
        
    except Exception as e:
        logger.error(f"Error getting multi-scans: {e}")
        return {"status": "error", "message": str(e)}

def is_admin(username: str) -> bool:
    """Check if user is admin"""
    return username == "admin"

async def get_admin_user(request: Request):
    """Dependency to check if current user is admin"""
    current_user = await get_current_user(request)
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Access denied")
    return current_user

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
        
        # Update global SECRET_KEY variable
        global SECRET_KEY
        SECRET_KEY = new_secret_key
        
        return True
    except Exception as e:
        logger.error(f"Error updating SECRET_KEY in .env: {e}")
        return False

# Admin Panel Routes

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, _: str = Depends(get_admin_user)):
    """Admin panel - only accessible by admin user"""
    current_secret_key = get_current_secret_key()
    if current_secret_key != "Not set":
        current_secret_key = f"{current_secret_key[0:8]}***"
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "current_secret_key": current_secret_key
    })

@app.get("/admin/users")
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

@app.post("/admin/create-user")
async def create_user(request: Request, username: str = Form(...), password: str = Form(...),
                     _: str = Depends(get_admin_user), user_db: Session = Depends(get_user_db)):
    """Create new user - admin only"""
    try:
        # Check if user already exists
        existing_user = user_db.query(User).filter(User.username == username).first()
        if existing_user:
            return RedirectResponse(url="/admin?error=user_exists", status_code=302)
        
        # Create new user
        password_hash = get_password_hash(password)
        new_user = User(username=username, password_hash=password_hash)
        user_db.add(new_user)
        user_db.commit()
        
        logger.info(f"New user created: {username}")
        return RedirectResponse(url="/admin?success=user_created", status_code=302)
        
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return RedirectResponse(url="/admin?error=user_creation_failed", status_code=302)

@app.post("/admin/delete-user/{username}")
async def delete_user(username: str, _: str = Depends(get_admin_user), 
                     user_db: Session = Depends(get_user_db)):
    """Delete user - admin only"""
    try:
        # Prevent admin deletion
        if username == "admin":
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Cannot delete admin user"}
            )
        
        # Find and delete user
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

@app.post("/admin/update-secret-key")
async def update_secret_key(request: Request, secret_key: str = Form(""),
                           _: str = Depends(get_admin_user)):
    """Update SECRET_KEY - admin only"""
    try:
        # Use provided key or generate new one
        new_key = secret_key.strip() if secret_key.strip() else None
        
        if update_secret_key_in_env(new_key):
            logger.info("SECRET_KEY updated by admin")
            return RedirectResponse(url="/admin?success=secret_key_updated", status_code=302)
        else:
            return RedirectResponse(url="/admin?error=secret_key_update_failed", status_code=302)
            
    except Exception as e:
        logger.error(f"Error updating SECRET_KEY: {e}")
        return RedirectResponse(url="/admin?error=secret_key_update_failed", status_code=302)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)