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
    ScanStatusResponse, ScanResultsResponse, ErrorResponse, validate_scan_id
)
from config import MICROSERVICE_URL, APP_HOST, APP_PORT, HUB_TYPE, BASE_URL, get_auth_headers
from routes.project_routes import validate_repo_url
from services.microservice_client import check_microservice_health

logger = logging.getLogger("main")
user_logger = logging.getLogger("user_actions")
router = APIRouter(prefix=f"/api/v1")

@router.post(
    "/project/add",
    response_model=ProjectAddResponse,
    responses={
        200: {
            "description": "Project created successfully",
            "model": ProjectAddResponse
        },
        400: {
            "description": "Bad Request - Invalid repository URL or project already exists",
            "model": ErrorResponse
        },
        401: {
            "description": "Unauthorized - Invalid or missing API token",
            "model": ErrorResponse
        },
        403: {
            "description": "Forbidden - Insufficient permissions (project_add required)",
            "model": ErrorResponse
        },
        429: {
            "description": "Rate Limit Exceeded",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal Server Error",
            "model": ErrorResponse
        }
    },
    summary="Add new project",
    description="""
    Create a new project for scanning. The project name will be automatically generated from the repository URL.
    
    **Required Permission:** `project_add`
    
    **Process:**
    1. Validates repository URL format
    2. Checks if project already exists
    3. Generates unique project name
    4. Creates project record
    
    **Repository URL Requirements:**
    - Must be a valid HTTP/HTTPS or git@ URL
    - Should not contain query parameters
    - Should not contain commit paths
    
    **Rate Limits:** Consumes 1 request from your quota
    """,
    tags=["Projects"]
)
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
        user_logger.info(f"API token '{token.name}' created project '{project_name}' with repo URL: {normalized_url}")
        
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

@router.post(
    "/project/check",
    response_model=ProjectCheckResponse,
    responses={
        200: {
            "description": "Project check completed",
            "model": ProjectCheckResponse
        },
        400: {
            "description": "Bad Request - Invalid input parameters",
            "model": ErrorResponse
        },
        401: {
            "description": "Unauthorized - Invalid or missing API token",
            "model": ErrorResponse
        },
        403: {
            "description": "Forbidden - Insufficient permissions (project_check required)",
            "model": ErrorResponse
        },
        429: {
            "description": "Rate Limit Exceeded",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal Server Error",
            "model": ErrorResponse
        }
    },
    summary="Check project existence",
    description="""
    Check if a project exists in the system by repository URL or project name.
    
    **Required Permission:** `project_check`
    
    **Search Methods:**
    1. By repository URL (exact match after normalization)
    2. By project name (exact match)
    
    At least one parameter must be provided. If both are provided, repository URL takes precedence.
    
    **Rate Limits:** Consumes 1 request from your quota
    """,
    tags=["Projects"]
)  
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
            # if project.created_by != f"API:{token.name}":
            #     logger.info(f"[API: {token.name}] Access to project not permitted ({response_time}ms)")
            #     return ProjectCheckResponse(exists=False, project_name="Not permitted")
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

@router.post(
    "/scan",
    response_model=ScanResponse,
    responses={
        200: {
            "description": "Scan started successfully",
            "model": ScanResponse
        },
        400: {
            "description": "Bad Request - Invalid parameters or microservice error",
            "model": ErrorResponse
        },
        401: {
            "description": "Unauthorized - Invalid or missing API token",
            "model": ErrorResponse
        },
        403: {
            "description": "Forbidden - Insufficient permissions (scan required)",
            "model": ErrorResponse
        },
        404: {
            "description": "Not Found - Project does not exist",
            "model": ErrorResponse
        },
        408: {
            "description": "Request Timeout - Microservice timeout",
            "model": ErrorResponse
        },
        429: {
            "description": "Rate Limit Exceeded",
            "model": ErrorResponse
        },
        503: {
            "description": "Service Unavailable - Microservice unavailable",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal Server Error",
            "model": ErrorResponse
        }
    },
    summary="Start repository scan",
    description="""
    Start scanning a specific commit of a repository for secrets and credentials.
    
    **Required Permission:** `scan`
    
    **Prerequisites:**
    - Project must exist (use `/project/add` first if needed)
    - Repository must be accessible
    - Commit hash must exist in the repository
    
    **Process:**
    1. Validates repository URL and commit hash
    2. Finds existing project
    3. Creates scan record
    4. Queues scan job in microservice
    5. Returns scan ID for tracking
    
    **Tracking:**
    Use the returned `scan_id` with `/scan/{scan_id}/status` to monitor progress
    and `/scan/{scan_id}/results` to retrieve results when completed.
    
    **Rate Limits:** Consumes 1 request from your quota
    """,
    tags=["Scanning"]
)
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
        # if project.created_by != f"API:{token.name}":
        #     return JSONResponse(
        #         status_code=403,
        #         content={"success": False, "message": "You are not permitted to launch this scan"}
        #     )
        
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
                        user_logger.info(f"API token '{token.name}' started scan for project '{project.name}' (commit: {request.commit})")
                        
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

@router.post(
    "/multi_scan",
    response_model=MultiScanResponse,
    responses={
        200: {
            "description": "Multi-scan started successfully",
            "model": MultiScanResponse
        },
        400: {
            "description": "Bad Request - Invalid parameters, too many scans, or microservice error",
            "model": ErrorResponse
        },
        401: {
            "description": "Unauthorized - Invalid or missing API token",
            "model": ErrorResponse
        },
        403: {
            "description": "Forbidden - Insufficient permissions (multi_scan required)",
            "model": ErrorResponse
        },
        404: {
            "description": "Not Found - One or more projects do not exist",
            "model": ErrorResponse
        },
        408: {
            "description": "Request Timeout - Microservice timeout",
            "model": ErrorResponse
        },
        429: {
            "description": "Rate Limit Exceeded",
            "model": ErrorResponse
        },
        503: {
            "description": "Service Unavailable - Microservice unavailable",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal Server Error",
            "model": ErrorResponse
        }
    },
    summary="Start multiple repository scans",
    description="""
    Start scanning multiple repositories simultaneously. Maximum 10 repositories per request.
    
    **Required Permission:** `multi_scan`
    
    **Prerequisites:**
    - All projects must exist (use `/project/add` for each if needed)
    - All repositories must be accessible
    - All commit hashes must exist in their respective repositories
    
    **Limitations:**
    - Maximum 10 repositories per multi-scan
    - All repositories must pass validation before any scans start
    
    **Process:**
    1. Validates all repository URLs and commit hashes
    2. Verifies all projects exist
    3. Creates individual scan records
    4. Creates multi-scan record for tracking
    5. Queues all scans in microservice
    6. Returns multi-scan ID for tracking
    
    **Tracking:**
    Use the returned multi-scan ID with individual scan tracking endpoints.
    Multi-scans may take longer due to sequential processing.
    
    **Rate Limits:** Consumes 1 request from your quota regardless of repository count
    """,
    tags=["Scanning"]
)
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
        
        if len(request) > 10:
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
        individual_scan_ids = []
        
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
            individual_scan_ids.append(scan_id)
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
        multi_scan = MultiScan(
            id=multi_scan_id,
            user_id=f"API:{token.name}",
            scan_ids=json.dumps(individual_scan_ids),
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
                        user_logger.info(f"API token '{token.name}' started multi-scan with {len(scan_records)} repositories")
                        
                        return MultiScanResponse(
                            success=True,
                            message="Multi-scan has been queued",
                            scan_id=json.dumps(individual_scan_ids)  # Возвращаем список scan_id как JSON string
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

@router.get(
    "/scan/{scan_id}/status",
    response_model=ScanStatusResponse,
    responses={
        200: {
            "description": "Scan status retrieved successfully",
            "model": ScanStatusResponse
        },
        400: {
            "description": "Bad Request - Invalid scan ID format",
            "model": ErrorResponse
        },
        401: {
            "description": "Unauthorized - Invalid or missing API token",
            "model": ErrorResponse
        },
        403: {
            "description": "Forbidden - Insufficient permissions (scan_results required)",
            "model": ErrorResponse
        },
        429: {
            "description": "Rate Limit Exceeded",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal Server Error",
            "model": ErrorResponse
        }
    },
    summary="Get scan status",
    description="""
    Retrieve the current status of a scan operation.
    
    **Required Permission:** `scan_results`
    
    **Status Values:**
    - `pending`: Scan is queued but not started
    - `running`: Scan is currently in progress
    - `completed`: Scan finished successfully (results available)
    - `failed`: Scan encountered an error
    - `not_found`: Scan ID does not exist
    
    **Usage:**
    Poll this endpoint to monitor scan progress. Once status is `completed`,
    use `/scan/{scan_id}/results` to retrieve the findings.
    
    **Rate Limits:** Consumes 1 request from your quota
    """,
    tags=["Scanning"]
)
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
        
        if scan.started_by != f"API:{token.name}":
            logger.info(f"[API: {token.name}] Access to scan not permitted: {scan_id}")
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

@router.get(
    "/scan/{scan_id}/results",
    response_model=ScanResultsResponse,
    responses={
        200: {
            "description": "Scan results retrieved successfully",
            "model": ScanResultsResponse
        },
        400: {
            "description": "Bad Request - Invalid scan ID format",
            "model": ErrorResponse
        },
        401: {
            "description": "Unauthorized - Invalid or missing API token",
            "model": ErrorResponse
        },
        403: {
            "description": "Forbidden - Insufficient permissions (scan_results required)",
            "model": ErrorResponse
        },
        429: {
            "description": "Rate Limit Exceeded",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal Server Error",
            "model": ErrorResponse
        }
    },
    summary="Get scan results",
    description="""
    Retrieve the detailed results of a completed scan.
    
    **Required Permission:** `scan_results`
    
    **Availability:**
    Results are only available for scans with status `completed`.
    For other statuses, use `/scan/{scan_id}/status` first.
    
    **Result Format:**
    Returns a list of detected secrets with file paths and line numbers.
    Only confirmed secrets are included (refuted/false positives are excluded).
    
    **Note:**
    Results contain only location information (path and line number) for security.
    Actual secret values are not included in API responses.
    
    **Rate Limits:** Consumes 1 request from your quota
    """,
    tags=["Scanning"]
)
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
        
        if scan.started_by != f"API:{token.name}":
            logger.info(f"[API: {token.name}] Access to scan not permitted: {scan_id}")
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