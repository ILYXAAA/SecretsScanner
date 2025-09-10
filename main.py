from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
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
from logging_config import setup_logging

# Import API middleware
from api.middleware import log_api_request, cleanup_rate_limits

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

async def cleanup_api_data():
    """Background task to cleanup API rate limiting data"""
    while True:
        try:
            cleanup_rate_limits()
        except Exception as e:
            logger.error(f"Error cleaning up API data: {e}")
        
        # Cleanup every 5 minutes
        await asyncio.sleep(300)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    task1 = asyncio.create_task(check_scan_timeouts())
    task2 = asyncio.create_task(backup_scheduler())
    task3 = asyncio.create_task(cleanup_api_data())
    
    yield
    
    # Shutdown
    task1.cancel()
    task2.cancel()
    task3.cancel()
    try:
        await task1
    except asyncio.CancelledError:
        pass
    try:
        await task2
    except asyncio.CancelledError:
        pass
    try:
        await task3
    except asyncio.CancelledError:
        pass

# Основной логгер сервиса
logger = setup_logging(log_file="secrets_scanner.log")
logger = logging.getLogger("main")

# Логгер действий пользователей (отдельный файл, без консоли)
user_logger = logging.getLogger("user_actions")
user_handler = RotatingFileHandler(
    "user_actions.log",
    maxBytes=10*1024*1024,
    backupCount=5,
    encoding="utf-8"
)
user_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
))
user_logger.addHandler(user_handler)
user_logger.setLevel(logging.INFO)
user_logger.propagate = False  # чтобы не дублировалось в консоль/основной логгер

# Initialize FastAPI app with comprehensive documentation
app = FastAPI(
    title="Secrets Scanner API",
    description="API for scanning repositories for secrets and credentials",
    version="1.0.0",
    lifespan=lifespan, 
    root_path=BASE_URL,
    docs_url=None,  # Disable default docs
    redoc_url=None,  # Disable default redoc
    openapi_url=f"/api/openapi.json"
)

# Custom Swagger UI with enhanced settings
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi

@app.get("/api/openapi.json", include_in_schema=False)
async def get_openapi():
    """Return OpenAPI schema"""
    # Используем стандартную схему FastAPI
    return app.openapi()

@app.get("/api/swagger", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=f"{BASE_URL}/api/openapi.json",
        title=f"{app.title} - Interactive API Documentation",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url=f"{BASE_URL}/static/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url=f"{BASE_URL}/static/swagger-ui/swagger-ui.css",
        swagger_ui_parameters={
            "deepLinking": True,
            "displayOperationId": False,
            "defaultModelsExpandDepth": 2,
            "defaultModelExpandDepth": 2,
            "defaultModelRendering": "model",
            "displayRequestDuration": True,
            "docExpansion": "list",
            "filter": True,
            "operationsSorter": "method",
            "showExtensions": True,
            "showCommonExtensions": True,
            "tryItOutEnabled": True,
            "persistAuthorization": True,
            "layout": "BaseLayout",
            "servers": [
                {"url": f"{BASE_URL}", "description": "Production server"}
            ]
        }
    )

@app.get("/api/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=f"{BASE_URL}/api/openapi.json",
        title=f"{app.title} - API Documentation",
        redoc_js_url=f"{BASE_URL}/static/redoc/redoc.standalone.js",
        with_google_fonts=False
    )

# Add API logging middleware (must be before other middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=log_api_request)

# Mount static files
app.mount("/ico", StaticFiles(directory="ico"), name="ico")

@app.get("/static/{file_path:path}")
async def serve_static(file_path: str):
    file_location = os.path.join("static", file_path)
    if os.path.exists(file_location):
        response = FileResponse(file_location)
        response.headers["Cache-Control"] = "public, max-age=604800"
        return response
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
from routes.admin_workers_service import router as admin_microservice_router
from routes.logs_routes import router as logs_router
from routes.secrets_history_routes import router as secrets_history_router
from routes.scan_status_routes import router as scan_results_router

# Import API router
from api import router as api_router

# Include all routers
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(project_router)
app.include_router(scan_router)
app.include_router(settings_router)
app.include_router(multi_scan_router)
app.include_router(admin_router)
app.include_router(admin_microservice_router)
app.include_router(logs_router)
app.include_router(secrets_history_router)
app.include_router(scan_results_router)

# Include API router
app.include_router(api_router)

def custom_api_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    from fastapi.routing import APIRoute
    from fastapi.openapi.utils import get_openapi
    
    # Get ALL routes first to understand the structure
    all_routes = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            all_routes.append(route)
    
    # Filter only API routes - more precise filtering
    api_routes = []
    for route in all_routes:
        # Check if route path contains /api/v1 and is not excluded
        if (route.path.startswith("/api/v1") or "/api/v1/" in route.path) and not route.include_in_schema == False:
            api_routes.append(route)
    
    # If no API routes found, create empty schema
    if not api_routes:
        openapi_schema = {
            "openapi": "3.0.2",
            "info": {
                "title": "Secrets Scanner API",
                "version": "1.0.0",
                "description": "API для сканирования репозиториев на предмет нескрытых секретов."
            },
            "paths": {},
            "components": {
                "securitySchemes": {
                    "BearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "API Key",
                        "description": "Enter your API token (e.g., ss_live_abc123...)"
                    }
                }
            }
        }
    else:
        # Create a temporary FastAPI app with only API routes
        from fastapi import FastAPI
        temp_app = FastAPI()
        
        # Add only API routes to temp app
        for route in api_routes:
            temp_app.router.routes.append(route)
        
        # Generate schema from temp app
        try:
            openapi_schema = get_openapi(
                title="Secrets Scanner API",
                version="1.0.0", 
                description="API для сканирования репозиториев на предмет нескрытых секретов.",
                routes=temp_app.router.routes
            )
        except TypeError:
            # Fallback for older FastAPI versions
            openapi_schema = {
                "openapi": "3.0.2",
                "info": {
                    "title": "Secrets Scanner API",
                    "version": "1.0.0",
                    "description": "API для сканирования репозиториев на предмет нескрытых секретов."
                },
                "paths": {},
                "components": {}
            }
    
    # Ensure components section exists
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    
    # Add Bearer token security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "API Key", 
            "description": "Enter your API token (e.g., ss_live_abc123...)"
        }
    }

    openapi_schema["servers"] = [
        {
            "url": f"{BASE_URL}",
            "description": "Production server"
        }
    ]
    
    # Apply security to all paths
    if "paths" in openapi_schema:
        for path_key in openapi_schema["paths"]:
            path_obj = openapi_schema["paths"][path_key]
            for method in path_obj:
                if method.lower() in ["get", "post", "put", "delete", "patch"]:
                    if "security" not in path_obj[method]:
                        path_obj[method]["security"] = [{"BearerAuth": []}]
    
    # Add metadata
    if "info" not in openapi_schema:
        openapi_schema["info"] = {}
        
    openapi_schema["info"].update({
        "contact": {
            "name": "Secrets Scanner API Support",
            "url": "https://github.com/your-org/secrets-scanner"
        },
        "license": {
            "name": "MIT License", 
            "url": "https://opensource.org/licenses/MIT"
        }
    })
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Set custom OpenAPI schema
app.openapi = custom_api_openapi

# Health check endpoint for API monitoring
@app.get("/api/health", include_in_schema=False)
async def api_health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

# API documentation redirect
@app.get("/api", include_in_schema=False)
async def api_redirect():
    """Redirect /api to Swagger documentation"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"{BASE_URL}/api/swagger")

# Favicon route
@app.get("/favicon.ico")
async def favicon():
    favicon_path = Path("ico/favicon.ico")
    if favicon_path.exists():
        return FileResponse("ico/favicon.ico")
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Favicon not found")

# Root endpoint redirects to dashboard (restore original behavior)
@app.get("/", include_in_schema=False)
async def root():
    """Redirect to dashboard"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"{BASE_URL}/dashboard")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host=APP_HOST, 
        port=APP_PORT,
        log_level="info",
        access_log=True,
        log_config=None
    )