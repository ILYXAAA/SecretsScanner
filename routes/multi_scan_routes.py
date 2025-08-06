from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
import httpx
import uuid
import json
import logging

from config import MICROSERVICE_URL, APP_HOST, APP_PORT, get_auth_headers
from models import Scan, Secret, MultiScan
from services.auth import get_current_user
from services.database import get_db
from services.microservice_client import check_microservice_health
from services.templates import templates
logger = logging.getLogger("main")

router = APIRouter()

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

@router.get("/multi-scan", response_class=HTMLResponse)
async def multi_scan_page(request: Request, current_user: str = Depends(get_current_user)):
    return templates.TemplateResponse("multi_scan.html", {
        "request": request,
        "current_user": current_user
    })

@router.post("/multi_scan")
async def multi_scan(request: Request, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
  """Handle multi-scan requests"""
  try:
      scan_requests = await request.json()
      
      if not isinstance(scan_requests, list) or len(scan_requests) == 0:
          return JSONResponse(
              status_code=400,
              content={"status": "error", "message": "Invalid request format"}
          )
      
      # Validate repo URLs - ensure they don't contain ref parameters
      for scan_request in scan_requests:
          repo_url = scan_request.get("RepoUrl", "")
          if "?" in repo_url or "/commit/" in repo_url:
              return JSONResponse(
                  status_code=400,
                  content={"status": "error", "message": f"Repo URL должен быть базовой ссылкой на репозиторий без параметров: {repo_url}"}
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
          # Generate new scan ID
          scan_id = str(uuid.uuid4())
          scan_ids.append(scan_id)
          
          # Create correct callback URL with BASE_URL prefix
          callback_url = f"http://{APP_HOST}:{APP_PORT}/get_results/{scan_request['ProjectName']}/{scan_id}"
          scan_request["CallbackUrl"] = callback_url
          
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

@router.get("/api/multi-scans")
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
                    "files_scanned": scan.files_scanned,
                    "excluded_files_count": scan.excluded_files_count
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