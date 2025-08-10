from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import json
import os
from services.database import SessionLocal
from datetime import datetime, timedelta
# Import configuration
from config import BASE_URL, APP_HOST, APP_PORT, TIMEOUT
# Import models and database setup
from models import AuthenticationException, Scan, MultiScan
from services.database import initialize_database
from services.auth import ensure_user_database, auth_exception_handler
from services.backup_service import backup_scheduler

# Import background tasks
async def check_scan_timeouts():
    """Background task to check for timed out scans"""
    while True:
        try:
            db = SessionLocal()
            
            # Find all running scans
            running_scans = db.query(Scan).filter(Scan.status == "running").all()
            
            for scan in running_scans:
                # Check if scan is part of multi-scan
                multi_scan = db.query(MultiScan).filter(
                    MultiScan.scan_ids.like(f'%"{scan.id}"%')
                ).first()
                
                if multi_scan:
                    # Parse scan_ids and find position
                    scan_ids = json.loads(multi_scan.scan_ids)
                    try:
                        position = scan_ids.index(scan.id)
                        # Для мультисканов - каждому последующему скану +10 минут таймаута
                        timeout_minutes = TIMEOUT + (position * 10)
                    except ValueError:
                        # Fallback if scan_id not found in list
                        timeout_minutes = TIMEOUT
                else:
                    # Regular scan - use base timeout
                    timeout_minutes = TIMEOUT
                
                # Check if scan has timed out
                timeout_threshold = datetime.now() - timedelta(minutes=timeout_minutes)
                
                if scan.started_at < timeout_threshold:
                    scan.status = "timeout"
                    scan.completed_at = datetime.now()
            
            db.commit()
            db.close()
            
        except Exception as e:
            logger.error(f"Error checking scan timeouts: {e}")
        
        # Check every minute
        await asyncio.sleep(10)

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
# app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/static/{file_path:path}")
async def serve_static(file_path: str):
    file_location = os.path.join("static", file_path)
    if os.path.exists(file_location):
        return FileResponse(file_location)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="File not found")

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
from routes.secrets_history_routes import router as secrets_history_router

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(project_router)
app.include_router(scan_router)
app.include_router(settings_router)
app.include_router(multi_scan_router)
app.include_router(admin_router)
app.include_router(logs_router)
app.include_router(secrets_history_router)

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