import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# Для цветной консоли
os.system("")
load_dotenv()

# Proxy settings
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

# Base URL configuration
BASE_URL = "/secret_scanner"

def get_full_url(path: str) -> str:
    """Helper to create full URLs with base prefix"""
    if path.startswith('/'):
        path = path[1:]
    return f"{BASE_URL}/{path}" if path else BASE_URL

# Security configuration
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 часов

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database/secrets_scanner.db")
if "database/" in DATABASE_URL:
    Path("database").mkdir(exist_ok=True)

USERS_DATABASE_URL = os.getenv("USERS_DATABASE_URL", "sqlite:///./Auth/users.db")

# Microservice configuration
MICROSERVICE_URL = os.getenv("MICROSERVICE_URL")
APP_HOST = os.getenv("APP_HOST")
APP_PORT = int(os.getenv("APP_PORT"))
HUB_TYPE = os.getenv("HUB_TYPE", "Azure")  # Git or Azure

# Backup configuration
BACKUP_DIR = os.getenv("BACKUP_DIR", "./backups")
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "7"))
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))

# Create necessary directories
Path(BACKUP_DIR).mkdir(exist_ok=True)
Path("templates").mkdir(exist_ok=True)
Path("ico").mkdir(exist_ok=True)

def get_auth_headers():
    """Get headers with API key for microservice requests"""
    load_dotenv(override=True)
    API_KEY = os.getenv("API_KEY")
    if not API_KEY:
        raise ValueError("API_KEY must be set in .env file")
    return {"X-API-Key": API_KEY}