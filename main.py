from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Import configuration
from config import BASE_URL, APP_HOST, APP_PORT

# Import models and database setup
from models import AuthenticationException
from services.database import initialize_database
from services.auth import ensure_user_database, auth_exception_handler
from services.backup_service import backup_scheduler

# Import background tasks
async def check_scan_timeouts():
    """Background task to check for timed out scans"""
    from datetime import datetime, timezone, timedelta
    from services.database import SessionLocal
    from models import Scan
    
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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('secrets_scanner.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'),
        logging.StreamHandler()  # Также выводить в консоль
    ]
)
logger = logging.getLogger("main")

# Initialize FastAPI app
app = FastAPI(title="Secrets Scanner", lifespan=lifespan, root_path=BASE_URL)

# Mount static files
app.mount("/ico", StaticFiles(directory="ico"), name="ico")

# Initialize databases
ensure_user_database()
initialize_database()

# Exception handler for authentication
app.exception_handler(AuthenticationException)(auth_exception_handler)

# Import and include routers
from routes.auth_routes import router as auth_router
from routes.dashboard_routes import router as dashboard_router
from routes.project_routes import router as project_router
from routes.scan_routes import router as scan_router
from routes.settings_routes import router as settings_router
from routes.multi_scan_routes import router as multi_scan_router
from routes.admin_routes import router as admin_router
from routes.logs_routes import router as logs_router

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(project_router)
app.include_router(scan_router)
app.include_router(settings_router)
app.include_router(multi_scan_router)
app.include_router(admin_router)
app.include_router(logs_router)

# Favicon route
@app.get("/favicon.ico")
async def favicon():
    favicon_path = Path("ico/favicon.ico")
    if favicon_path.exists():
        return FileResponse("ico/favicon.ico")
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Favicon not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)