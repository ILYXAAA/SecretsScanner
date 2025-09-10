from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
import httpx
import logging
import os
from typing import Optional

from config import get_auth_headers
from services.auth import get_current_user
from services.database import get_db
from services.templates import templates

logger = logging.getLogger("main")
user_logger = logging.getLogger("user_actions")

router = APIRouter()

# Get admin API key from environment
ADMIN_MICROSERVICE_API_KEY = os.getenv("ADMIN_MICROSERVICE_API_KEY")
MICROSERVICE_URL = os.getenv("MICROSERVICE_URL", "http://localhost:8001")

def is_admin(user: str) -> bool:
    """Check if user has admin privileges"""
    # You can customize this logic based on your admin users definition
    # For now, assuming admin user is simply "admin"
    return user == "admin"

async def get_admin_user(current_user: str = Depends(get_current_user)) -> str:
    """Dependency to check if current user is admin"""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Access denied. Admin privileges required.")
    return current_user

def get_admin_headers() -> dict:
    """Get headers with admin API key for microservice requests"""
    if not ADMIN_MICROSERVICE_API_KEY:
        raise HTTPException(status_code=500, detail="Admin API key not configured")
    
    return {
        "X-API-Key": ADMIN_MICROSERVICE_API_KEY,
        "Content-Type": "application/json"
    }

async def make_microservice_request(method: str, endpoint: str, timeout: int = 30) -> dict:
    """Make request to microservice with error handling"""
    url = f"{MICROSERVICE_URL}{endpoint}"
    headers = get_admin_headers()
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
    except httpx.TimeoutException:
        logger.error(f"Timeout while calling microservice endpoint: {endpoint}")
        raise HTTPException(status_code=504, detail="Microservice request timeout")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling microservice: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Endpoint not found")
        elif e.response.status_code == 403:
            raise HTTPException(status_code=403, detail="Access denied to microservice")
        else:
            raise HTTPException(status_code=e.response.status_code, detail=f"Microservice error: {e.response.text}")
    except httpx.RequestError as e:
        # logger.error(f"Request error calling microservice: {str(e)}")
        raise HTTPException(status_code=503, detail="Unable to connect to microservice")
    except Exception as e:
        logger.error(f"Unexpected error calling microservice: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/admin/workers", response_class=HTMLResponse)
async def workers_management_page(request: Request, current_user: str = Depends(get_admin_user)):
    """Render workers management page"""
    user_logger.info(f"Admin user {current_user} accessed workers management page")
    
    return templates.TemplateResponse("admin_workers_service.html", {
        "request": request,
        "current_user": current_user
    })

@router.get("/admin/workers-status")
async def get_workers_status(current_user: str = Depends(get_admin_user)):
    """Get workers status with queue and summary information for auto-refresh"""
    try:
        # Get workers data
        workers_data = await make_microservice_request("GET", "/admin/workers")
        
        # Get service stats for queue and workers summary
        service_stats = await make_microservice_request("GET", "/admin/service_stats")
        
        # Process workers data to include additional metrics
        workers = workers_data.get("workers", [])
        
        # Add CPU and memory data from service stats if available
        if "workers" in service_stats and "processes" in service_stats["workers"]:
            process_data = {proc["worker_id"]: proc for proc in service_stats["workers"]["processes"]}
            
            for worker in workers:
                worker_id = worker["worker_id"]
                if worker_id in process_data:
                    worker["cpu_percent"] = process_data[worker_id].get("cpu_percent", 0)
                    worker["memory_mb"] = process_data[worker_id].get("memory_mb", 0)
                else:
                    worker["cpu_percent"] = 0
                    worker["memory_mb"] = 0
        
        # Get queue stats and expand processing status
        queue_stats = service_stats.get("queue", {})
        
        # If microservice provides detailed status breakdown, use it
        # Otherwise, we'll get individual status counts from tasks endpoint
        if "processing" in queue_stats and "downloading" not in queue_stats:
            # Get recent tasks to calculate individual processing status counts
            try:
                tasks_data = await make_microservice_request("GET", "/admin/tasks?status=downloading,unpacking,scanning,ml_validation&limit=1000", timeout=10)
                if tasks_data.get("status") == "success":
                    tasks = tasks_data.get("tasks", [])
                    
                    # Count individual processing statuses
                    downloading_count = len([t for t in tasks if t.get("status") == "downloading"])
                    unpacking_count = len([t for t in tasks if t.get("status") == "unpacking"])
                    scanning_count = len([t for t in tasks if t.get("status") == "scanning"])
                    ml_validation_count = len([t for t in tasks if t.get("status") == "ml_validation"])
                    
                    # Add individual counts to queue stats
                    queue_stats.update({
                        "downloading": downloading_count,
                        "unpacking": unpacking_count,
                        "scanning": scanning_count,
                        "ml_validation": ml_validation_count
                    })
            except Exception as e:
                logger.warning(f"Could not get detailed processing status counts: {e}")
                # Fallback - set individual counts to 0 if we can't get them
                queue_stats.update({
                    "downloading": 0,
                    "unpacking": 0,
                    "scanning": 0,
                    "ml_validation": 0
                })
        
        response_data = {
            "status": "success",
            "workers": workers,
            "queue": queue_stats,
            "workers_summary": service_stats.get("workers", {})
        }
        
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workers status: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to get workers status: {str(e)}"}
        )

@router.get("/admin/service-stats")
async def get_service_stats(current_user: str = Depends(get_admin_user)):
    """Get detailed service statistics - called manually via button"""
    try:
        service_stats = await make_microservice_request("GET", "/admin/service_stats", timeout=60)
        
        user_logger.info(f"Admin user {current_user} successfully retrieved service statistics")
        
        return JSONResponse(content=service_stats)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting service stats: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to get service stats: {str(e)}"}
        )

@router.post("/admin/workers")
async def add_worker(current_user: str = Depends(get_admin_user)):
    """Add new worker"""
    try:
        result = await make_microservice_request("POST", "/admin/workers/add")
        
        user_logger.info(f"Admin user {current_user} successfully added worker: {result.get('worker_id', 'unknown')}")
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding worker: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to add worker: {str(e)}"}
        )

@router.post("/admin/workers/{worker_id}/stop")
async def stop_worker(worker_id: str, current_user: str = Depends(get_admin_user)):
    """Gracefully stop worker"""
    try:
        result = await make_microservice_request("POST", f"/admin/workers/{worker_id}/stop")
        
        user_logger.warning(f"Admin user {current_user} successfully sent stop command to worker {worker_id}")
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping worker {worker_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to stop worker: {str(e)}"}
        )

@router.post("/admin/workers/{worker_id}/kill")
async def kill_worker(worker_id: str, current_user: str = Depends(get_admin_user)):
    """Forcefully kill worker"""
    try:
        result = await make_microservice_request("POST", f"/admin/workers/{worker_id}/kill")
        
        user_logger.warning(f"Admin user {current_user} successfully killed worker {worker_id}")
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error killing worker {worker_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to kill worker: {str(e)}"}
        )

@router.post("/admin/workers/{worker_id}/pause")
async def pause_worker(worker_id: str, current_user: str = Depends(get_admin_user)):
    """Pause worker (stop accepting new tasks)"""
    try:
        result = await make_microservice_request("POST", f"/admin/workers/{worker_id}/pause")
        
        user_logger.warning(f"Admin user {current_user} successfully paused worker {worker_id}")
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing worker {worker_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to pause worker: {str(e)}"}
        )

@router.post("/admin/workers/{worker_id}/resume")
async def resume_worker(worker_id: str, current_user: str = Depends(get_admin_user)):
    """Resume worker (start accepting new tasks)"""
    try:
        result = await make_microservice_request("POST", f"/admin/workers/{worker_id}/resume")
        
        user_logger.warning(f"Admin user {current_user} successfully resumed worker {worker_id}")
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming worker {worker_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to resume worker: {str(e)}"}
        )

@router.post("/admin/workers/{worker_id}/restart")
async def restart_worker(worker_id: str, current_user: str = Depends(get_admin_user)):
    """Restart worker"""
    try:
        result = await make_microservice_request("POST", f"/admin/workers/{worker_id}/restart")
        
        user_logger.warning(f"Admin user {current_user} successfully restarted worker {worker_id}")
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restarting worker {worker_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to restart worker: {str(e)}"}
        )

@router.get("/admin/tasks")
async def get_tasks(
    status: Optional[str] = None,
    limit: Optional[int] = 200,  # Изменено: возвращен лимит по умолчанию 200
    current_user: str = Depends(get_admin_user)
):
    """Get tasks with filtering and analytics - supports both server-side and client-side pagination"""
    try:
        # Build query parameters
        params = []
        if status:
            params.append(f"status={status}")
        
        # Если лимит равен 0, то получаем все задачи для клиентской пагинации
        # Иначе используем серверную пагинацию
        if limit is not None:
            if limit == 0:
                # Для клиентской пагинации получаем все задачи
                params.append("limit=0")
            else:
                # Для серверной пагинации используем указанный лимит
                params.append(f"limit={limit}")
        else:
            # По умолчанию лимит 200
            params.append("limit=200")
        
        query_string = "?" + "&".join(params) if params else "?limit=200"
        endpoint = f"/admin/tasks{query_string}"
        
        result = await make_microservice_request("GET", endpoint, timeout=60)
        
        # Add analytics calculations
        tasks = result.get("tasks", [])
        
        # Calculate execution time statistics for completed tasks
        completed_tasks = [t for t in tasks if t.get("status") == "completed" and t.get("execution_time")]
        
        analytics = {
            "total_tasks": len(tasks),
            "completed_count": len([t for t in tasks if t.get("status") == "completed"]),
            "failed_count": len([t for t in tasks if t.get("status") == "failed"]),
            "pending_count": len([t for t in tasks if t.get("status") == "pending"]),
            "processing_count": len([t for t in tasks if t.get("status") in ["downloading", "unpacking", "scanning", "ml_validation"]]),
        }
        
        if completed_tasks:
            execution_times = [t["execution_time"] for t in completed_tasks]
            analytics.update({
                "avg_execution_time": sum(execution_times) / len(execution_times),
                "min_execution_time": min(execution_times),
                "max_execution_time": max(execution_times),
                "success_rate": (analytics["completed_count"] / max(analytics["total_tasks"], 1)) * 100
            })
        else:
            analytics.update({
                "avg_execution_time": 0,
                "min_execution_time": 0,
                "max_execution_time": 0,
                "success_rate": 0
            })
        
        # Add analytics to result
        result["analytics"] = analytics
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tasks: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to get tasks: {str(e)}"}
        )

@router.post("/admin/tasks/{task_id}/retry")
async def retry_task(task_id: str, current_user: str = Depends(get_admin_user)):
    """Retry failed task"""
    try:
        result = await make_microservice_request("POST", f"/admin/tasks/{task_id}/retry")
        
        user_logger.warning(f"Admin user {current_user} successfully retried task {task_id}")
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying task {task_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to retry task: {str(e)}"}
        )

@router.post("/admin/maintenance/cleanup")
async def cleanup_old_tasks(current_user: str = Depends(get_admin_user)):
    """Cleanup old completed/failed tasks"""
    try:
        result = await make_microservice_request("POST", "/admin/maintenance/cleanup_old_tasks", timeout=120)
        
        cleaned_count = result.get("cleaned_count", 0)
        user_logger.warning(f"Admin user {current_user} successfully cleaned up {cleaned_count} old tasks")
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning up old tasks: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to cleanup old tasks: {str(e)}"}
        )

@router.get("/admin/tasks/analytics")
async def get_tasks_analytics(
    days: Optional[int] = 7,
    current_user: str = Depends(get_admin_user)
):
    """Get detailed tasks analytics for the specified period"""
    try:
        # Get all completed and failed tasks without limit for analytics
        result = await make_microservice_request("GET", "/admin/tasks?limit=0", timeout=60)
        
        tasks = result.get("tasks", [])
        
        # Filter tasks by date if needed (this would require created_at filtering in microservice)
        # For now, we'll work with all available tasks
        
        # Calculate comprehensive analytics
        completed_tasks = [t for t in tasks if t.get("status") == "completed"]
        failed_tasks = [t for t in tasks if t.get("status") == "failed"]
        
        # Project-wise statistics
        project_stats = {}
        for task in tasks:
            project = task.get("project_name", "Unknown")
            if project not in project_stats:
                project_stats[project] = {"total": 0, "completed": 0, "failed": 0, "avg_time": 0}
            
            project_stats[project]["total"] += 1
            if task.get("status") == "completed":
                project_stats[project]["completed"] += 1
            elif task.get("status") == "failed":
                project_stats[project]["failed"] += 1
        
        # Calculate average execution time per project
        for project in project_stats:
            project_tasks = [t for t in completed_tasks if t.get("project_name") == project and t.get("execution_time")]
            if project_tasks:
                project_stats[project]["avg_time"] = sum(t["execution_time"] for t in project_tasks) / len(project_tasks)
        
        # Task type statistics
        task_type_stats = {}
        for task in tasks:
            task_type = task.get("task_type", "unknown")
            if task_type not in task_type_stats:
                task_type_stats[task_type] = {"total": 0, "completed": 0, "failed": 0}
            
            task_type_stats[task_type]["total"] += 1
            if task.get("status") == "completed":
                task_type_stats[task_type]["completed"] += 1
            elif task.get("status") == "failed":
                task_type_stats[task_type]["failed"] += 1
        
        # Top slowest tasks
        slowest_tasks = sorted(
            [t for t in completed_tasks if t.get("execution_time")],
            key=lambda x: x["execution_time"],
            reverse=True
        )[:10]
        
        # Most failed projects
        failed_project_stats = sorted(
            [(project, stats["failed"]) for project, stats in project_stats.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        analytics = {
            "total_tasks": len(tasks),
            "completed_tasks": len(completed_tasks),
            "failed_tasks": len(failed_tasks),
            "success_rate": (len(completed_tasks) / max(len(tasks), 1)) * 100,
            "project_statistics": project_stats,
            "task_type_statistics": task_type_stats,
            "slowest_tasks": slowest_tasks,
            "most_failed_projects": failed_project_stats
        }
        
        if completed_tasks:
            execution_times = [t["execution_time"] for t in completed_tasks if t.get("execution_time")]
            if execution_times:
                analytics.update({
                    "avg_execution_time": sum(execution_times) / len(execution_times),
                    "min_execution_time": min(execution_times),
                    "max_execution_time": max(execution_times),
                    "median_execution_time": sorted(execution_times)[len(execution_times) // 2]
                })
        
        user_logger.info(f"Admin user {current_user} retrieved comprehensive analytics for {len(tasks)} tasks")
        
        return JSONResponse(content={"status": "success", "analytics": analytics})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tasks analytics: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to get tasks analytics: {str(e)}"}
        )