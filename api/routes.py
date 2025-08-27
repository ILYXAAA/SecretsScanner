import time
import uuid
import json
import logging
import urllib.parse
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import httpx

from services.database import get_db
from models import Project, Scan, Secret, MultiScan, ApiToken
from api.middleware import get_api_token, require_permission
from api.schemas import (
    ProjectAddRequest, ProjectCheckRequest, ScanRequest, MultiScanRequest,
    ProjectAddResponse, ProjectCheckResponse, ScanResponse, MultiScanResponse,
    ScanStatusResponse, ScanResultsResponse, validate_scan_id
)
from config import MICROSERVICE_URL, APP_HOST, APP_PORT, HUB_TYPE, get_auth_headers
from routes.project_routes import validate_repo_url
from services.microservice_client import check_microservice_health

logger = logging.getLogger("main")
router = APIRouter(prefix="/api/v1", tags=["API v1"])

@router.post("/project/add", response_model=ProjectAddResponse)
async def api_project_add(
    request: ProjectAddRequest,
    db: Session = Depends(get_db),
    token: ApiToken = Depends(require_permission("project_add"))
):
    """Add a new project via API"""
    start_time = time.time()
    
    try:
        # Validate and normalize repository URL
        try:
            normalized_url = validate_repo_url(request.repository, HUB_TYPE)
        except ValueError as e:
            logger.warning(f"[API: {token.name}] Invalid repository URL: {request.repository}")
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": str(e)}
            )
        
        # Check if project already exists by repo URL
        existing_project = db.query(Project).filter(Project.repo_url == normalized_url).first()
        if existing_project:
            logger.info(f"[API: {token.name}] Project already exists: {existing_project.name}")
            return ProjectAddResponse(
                success=False,
                message=f"Project with this repository already exists: {existing_project.name}"
            )
        
        # Generate project name from repository URL
        try:
            # Extract project name from URL (last part of path)
            if normalized_url.endswith('.git'):
                repo_name = normalized_url.split('/')[-1][:-4]  # Remove .git
            else:
                repo_name = normalized_url.split('/')[-1]
                
            # Clean project name
            project_name = repo_name.replace('-', '_').replace('.', '_')
            
            # Ensure uniqueness
            base_name = project_name
            counter = 1
            while db.query(Project).filter(Project.name == project_name).first():
                project_name = f"{base_name}_{counter}"
                counter += 1
                
        except Exception as e:
            logger.error(f"[API: {token.name}] Error generating project name: {e}")
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Could not generate project name from repository URL"}
            )
        
        # Create project
        project = Project(
            name=project_name,
            repo_url=normalized_url,
            created_by=f"API:{token.name}"
        )
        
        db.add(project)
        db.commit()
        
        response_time = int((time.time() - start_time) * 1000)
        logger.info(f"[API: {token.name}] Created project '{project_name}' ({response_time}ms)")
        
        return ProjectAddResponse(
            success=True,
            message=f"Project {project_name} created successfully"
        )
        
    except Exception as e:
        logger.error(f"[API: {token.name}] Error creating project: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error"}
        )

@router.post("/project/check", response_model=ProjectCheckResponse)  
async def api_project_check(
    request: ProjectCheckRequest,
    db: Session = Depends(get_db),
    token: ApiToken = Depends(require_permission("project_check"))
):
    """Check if project exists via API"""
    start_time = time.time()
    
    try:
        project = None
        
        # Search by repository URL first
        if request.repository:
            try:
                normalized_url = validate_repo_url(request.repository, HUB_TYPE)
                project = db.query(Project).filter(Project.repo_url == normalized_url).first()
            except ValueError:
                # Invalid URL format, continue to search by name
                pass
        
        # Search by project name if not found by URL
        if not project and request.project_name:
            project = db.query(Project).filter(Project.name == request.project_name).first()
        
        response_time = int((time.time() - start_time) * 1000)
        
        if project:
            logger.info(f"[API: {token.name}] Project found: {project.name} ({response_time}ms)")
            return ProjectCheckResponse(exists=True, project_name=project.name)
        else:
            logger.info(f"[API: {token.name}] Project not found ({response_time}ms)")
            return ProjectCheckResponse(exists=False, project_name="")
            
    except Exception as e:
        logger.error(f"[API: {token.name}] Error checking project: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error"}
        )

@router.post("/scan", response_model=ScanResponse)
async def api_scan(
    request: ScanRequest,
    db: Session = Depends(get_db),
    token: ApiToken = Depends(require_permission("scan"))
):
    """Start a single scan via API"""
    start_time = time.time()
    
    try:
        # Validate repository URL and find/create project
        try:
            normalized_url = validate_repo_url(request.repository, HUB_TYPE)
        except ValueError as e:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": str(e)}
            )
        
        # Find project by repository URL
        project = db.query(Project).filter(Project.repo_url == normalized_url).first()
        if not project:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Project not found. Please add the project first."}
            )
        
        # Check microservice health
        if not await check_microservice_health():
            return JSONResponse(
                status_code=503,
                content={"success": False, "message": "Microservice unavailable"}
            )
        
        # Create scan record
        scan_id = str(uuid.uuid4())
        scan = Scan(
            id=scan_id,
            project_name=project.name,
            ref_type="Commit",
            ref=request.commit,
            status="pending",
            started_by=f"API:{token.name}"
        )
        db.add(scan)
        db.commit()
        
        # Start scan via microservice
        callback_url = f"http://{APP_HOST}:{APP_PORT}/get_results/{project.name}/{scan_id}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                microservice_request = {
                    "ProjectName": project.name,
                    "RepoUrl": project.repo_url,
                    "RefType": "Commit",
                    "Ref": request.commit,
                    "CallbackUrl": callback_url
                }
                
                response = await client.post(
                    f"{MICROSERVICE_URL}/scan",
                    json=microservice_request,
                    headers=get_auth_headers()
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("status") == "accepted":
                        scan.status = "running" 
                        scan.ref = result.get("Ref", request.commit)
                        db.commit()
                        
                        response_time = int((time.time() - start_time) * 1000)
                        logger.info(f"[API: {token.name}] Scan started: {scan_id} ({response_time}ms)")
                        
                        return ScanResponse(
                            success=True,
                            message="Scan has been queued",
                            scan_id=scan_id
                        )
                    else:
                        scan.status = "failed"
                        scan.error_message = result.get("message", "Unknown error")
                        db.commit()
                        return JSONResponse(
                            status_code=400,
                            content={"success": False, "message": result.get("message", "Scan failed")}
                        )
                else:
                    scan.status = "failed"
                    db.commit()
                    return JSONResponse(
                        status_code=response.status_code,
                        content={"success": False, "message": "Microservice error"}
                    )
                    
        except httpx.TimeoutException:
            scan.status = "failed"
            scan.error_message = "Microservice timeout"
            db.commit()
            return JSONResponse(
                status_code=408,
                content={"success": False, "message": "Microservice timeout"}
            )
        except Exception as e:
            scan.status = "failed"
            scan.error_message = str(e)
            db.commit()
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "Connection error"}
            )
            
    except Exception as e:
        logger.error(f"[API: {token.name}] Error starting scan: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error"}
        )

@router.post("/multi_scan", response_model=MultiScanResponse)
async def api_multi_scan(
    request: MultiScanRequest,
    db: Session = Depends(get_db),
    token: ApiToken = Depends(require_permission("multi_scan"))
):
    """Start multiple scans via API"""
    start_time = time.time()
    
    try:
        if not request or len(request) == 0:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Empty scan request list"}
            )
        
        if len(request) > 10:  # Limit multi-scan size
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Too many scans requested (max 10)"}
            )
        
        # Check microservice health
        if not await check_microservice_health():
            return JSONResponse(
                status_code=503,
                content={"success": False, "message": "Microservice unavailable"}
            )
        
        # Validate all repositories and prepare scan requests
        scan_requests = []
        scan_records = []
        
        for item in request:
            try:
                normalized_url = validate_repo_url(item.repository, HUB_TYPE)
            except ValueError as e:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "message": f"Invalid repository URL: {e}"}
                )
            
            # Find project
            project = db.query(Project).filter(Project.repo_url == normalized_url).first()
            if not project:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "message": f"Project not found for repository: {normalized_url}"}
                )
            
            # Create scan record
            scan_id = str(uuid.uuid4())
            callback_url = f"http://{APP_HOST}:{APP_PORT}/get_results/{project.name}/{scan_id}"
            
            scan_requests.append({
                "ProjectName": project.name,
                "RepoUrl": project.repo_url,
                "RefType": "Commit",
                "Ref": item.commit,
                "CallbackUrl": callback_url
            })
            
            scan = Scan(
                id=scan_id,
                project_name=project.name,
                ref_type="Commit",
                ref=item.commit,
                status="pending",
                started_by=f"API:{token.name}"
            )
            scan_records.append(scan)
        
        # Create multi-scan record
        multi_scan_id = str(uuid.uuid4())
        scan_ids = [scan.id for scan in scan_records]
        
        multi_scan = MultiScan(
            id=multi_scan_id,
            user_id=f"API:{token.name}",
            scan_ids=json.dumps(scan_ids),
            name=f"API Multi-scan {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        
        # Save all records
        for scan in scan_records:
            db.add(scan)
        db.add(multi_scan)
        db.commit()
        
        # Send to microservice
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                microservice_payload = {"repositories": scan_requests}
                
                response = await client.post(
                    f"{MICROSERVICE_URL}/multi_scan",
                    json=microservice_payload,
                    headers=get_auth_headers()
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("status") == "accepted":
                        # Update scan records to running
                        for scan in scan_records:
                            scan.status = "running"
                        db.commit()
                        
                        response_time = int((time.time() - start_time) * 1000)
                        logger.info(f"[API: {token.name}] Multi-scan started: {multi_scan_id} with {len(scan_records)} scans ({response_time}ms)")
                        
                        return MultiScanResponse(
                            success=True,
                            message="Multi-scan has been queued",
                            scan_id=multi_scan_id
                        )
                    else:
                        # Mark all scans as failed
                        for scan in scan_records:
                            scan.status = "failed"
                            scan.error_message = result.get("message", "Multi-scan failed")
                        db.commit()
                        
                        return JSONResponse(
                            status_code=400,
                            content={"success": False, "message": result.get("message", "Multi-scan failed")}
                        )
                else:
                    # Mark all scans as failed
                    for scan in scan_records:
                        scan.status = "failed" 
                        scan.error_message = "Microservice error"
                    db.commit()
                    
                    return JSONResponse(
                        status_code=response.status_code,
                        content={"success": False, "message": "Microservice error"}
                    )
                    
        except httpx.TimeoutException:
            for scan in scan_records:
                scan.status = "failed"
                scan.error_message = "Microservice timeout"
            db.commit()
            
            return JSONResponse(
                status_code=408,
                content={"success": False, "message": "Microservice timeout"}
            )
        except Exception as e:
            for scan in scan_records:
                scan.status = "failed" 
                scan.error_message = str(e)
            db.commit()
            
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "Connection error"}
            )
            
    except Exception as e:
        logger.error(f"[API: {token.name}] Error starting multi-scan: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error"}
        )

@router.get("/scan/{scan_id}/status", response_model=ScanStatusResponse)
async def api_scan_status(
    scan_id: str,
    db: Session = Depends(get_db),
    token: ApiToken = Depends(require_permission("scan_results"))
):
    """Get scan status via API"""
    start_time = time.time()
    
    try:
        # Validate scan ID format
        if not validate_scan_id(scan_id):
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Invalid scan ID format"}
            )
        
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        
        if not scan:
            logger.info(f"[API: {token.name}] Scan not found: {scan_id}")
            return ScanStatusResponse(
                scan_id=scan_id,
                status="not_found", 
                message="Scan not found"
            )
        
        response_time = int((time.time() - start_time) * 1000)
        
        # Map internal status to API status
        if scan.status == "completed":
            message = "Scan completed successfully"
        elif scan.status == "failed":
            message = scan.error_message or "Scan failed"
        elif scan.status == "running":
            message = "Scan is still running"
        elif scan.status == "pending":
            message = "Scanning in the pending status"
        else:
            message = f"Scan status: {scan.status}"
        
        logger.info(f"[API: {token.name}] Scan status checked: {scan_id} -> {scan.status} ({response_time}ms)")
        
        return ScanStatusResponse(
            scan_id=scan_id,
            status=scan.status,
            message=message
        )
        
    except Exception as e:
        logger.error(f"[API: {token.name}] Error getting scan status: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error"}
        )

@router.get("/scan/{scan_id}/results", response_model=ScanResultsResponse)
async def api_scan_results(
    scan_id: str,
    db: Session = Depends(get_db),
    token: ApiToken = Depends(require_permission("scan_results"))
):
    """Get scan results via API"""
    start_time = time.time()
    
    try:
        # Validate scan ID format
        if not validate_scan_id(scan_id):
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Invalid scan ID format"}
            )
        
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        
        if not scan:
            logger.info(f"[API: {token.name}] Scan not found: {scan_id}")
            return ScanResultsResponse(
                scan_id=scan_id,
                status="not_found"
            )
        
        if scan.status != "completed":
            return ScanResultsResponse(
                scan_id=scan_id,
                status=scan.status
            )
        
        # Get secrets (exclude refuted ones)
        secrets = db.query(Secret).filter(
            Secret.scan_id == scan_id,
            Secret.status != "Refuted"
        ).all()
        
        # Format results like the export function
        results = []
        for secret in secrets:
            results.append({
                "path": secret.path,
                "line": secret.line
            })
        
        response_time = int((time.time() - start_time) * 1000)
        logger.info(f"[API: {token.name}] Scan results retrieved: {scan_id} -> {len(results)} secrets ({response_time}ms)")
        
        return ScanResultsResponse(
            scan_id=scan_id,
            status="completed",
            results=results
        )
        
    except Exception as e:
        logger.error(f"[API: {token.name}] Error getting scan results: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error"}
        )