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
ACCESS_TOKEN_EXPIRE_MINUTES = 600 * 3 # 30 часов

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

# Auto-exported falses.txt refresh interval (hours)
FALSES_REFRESH_INTERVAL_HOURS = int(os.getenv("FALSES_REFRESH_INTERVAL_HOURS", "1"))

# Optional: auto-push falses.txt to Azure DevOps Git
def _env_unquoted(key, default=""):
    return os.getenv(key, default).strip().strip('"').strip("'")


FALSES_GIT_REPO_URL = _env_unquoted("FALSES_GIT_REPO_URL")
FALSES_GIT_PAT = _env_unquoted("FALSES_GIT_PAT")
FALSES_GIT_BRANCH = _env_unquoted("FALSES_GIT_BRANCH", "script_with_Docker")
FALSES_GIT_FILE_PATH = _env_unquoted("FALSES_GIT_FILE_PATH", "/src/storage/falses.txt")
FALSES_GIT_COMMITTER_NAME = _env_unquoted("FALSES_GIT_COMMITTER_NAME", "SecretsScanner_bot")
FALSES_GIT_COMMITTER_EMAIL = _env_unquoted("FALSES_GIT_COMMITTER_EMAIL", "secrets-scanner@local")
FALSES_GIT_SSL_VERIFY = _env_unquoted("FALSES_GIT_SSL_VERIFY", "false").lower() in ("1", "true", "yes", "on")
# Full path to git binary (systemd/minimal PATH often omits /usr/bin)
FALSES_GIT_BINARY = _env_unquoted("FALSES_GIT_BINARY")

# Create necessary directories
Path(BACKUP_DIR).mkdir(exist_ok=True)
Path("generated").mkdir(exist_ok=True)
Path("templates").mkdir(exist_ok=True)
Path("ico").mkdir(exist_ok=True)

# Other
TIMEOUT = 30

def get_auth_headers():
    """Get headers with API key for microservice requests"""
    load_dotenv(override=True)
    API_KEY = os.getenv("API_KEY")
    if not API_KEY:
        raise ValueError("API_KEY must be set in .env file")
    return {"X-API-Key": API_KEY}