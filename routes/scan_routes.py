from fastapi import APIRouter, Request, Form, Depends, HTTPException, File, UploadFile, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response, FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from pathlib import Path
import urllib.parse
import uuid
import json
import httpx
import asyncio
import logging
import html
import gzip
import base64

from config import get_full_url, MICROSERVICE_URL, APP_HOST, APP_PORT, HUB_TYPE, get_auth_headers
from models import Project, Scan, Secret
from services.auth import get_current_user
from services.database import get_db, sanitize_string
from services.microservice_client import check_microservice_health
from utils.html_report_generator import generate_html_report
from services.templates import templates
import time
logger = logging.getLogger("main")
user_logger = logging.getLogger("user_actions")

router = APIRouter()

def decompress_callback_data(payload: dict) -> dict:
    """Decompress callback data if it's compressed"""
    try:
        if payload.get("compressed", False):
            compressed_b64 = payload.get("data", "")
            original_size = payload.get("original_size", 0)
            compressed_size = payload.get("compressed_size", 0)
            
            compressed_data = base64.b64decode(compressed_b64.encode('ascii'))
            
            decompressed_data = gzip.decompress(compressed_data)
            
            decompressed_json = decompressed_data.decode('utf-8')
            original_payload = json.loads(decompressed_json)
            
            logger.info(f"📥 Получены сжатые данные:")
            logger.info(f"   Оригинал: {original_size / 1024:.2f} KB")
            logger.info(f"   Сжато: {compressed_size / 1024:.2f} KB")
            logger.info(f"   Экономия: {(1 - compressed_size / original_size) * 100:.1f}%")
            
            return original_payload
        else:
            return payload
            
    except Exception as e:
        logger.error(f"❌ Ошибка декомпрессии данных: {e}")
        raise ValueError(f"Failed to decompress callback data: {e}")

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

def normalize_file_path(file_path: str, repo_url: str) -> str:
    """Normalize file path by removing repo URL if present"""
    if not file_path or not repo_url:
        return file_path
    
    # Remove trailing slash from repo_url
    repo_url = repo_url.rstrip('/')
    
    # If file_path contains the repo_url, extract just the file path
    if repo_url in file_path:
        # Find the position after repo_url
        repo_end = file_path.find(repo_url) + len(repo_url)
        # Extract everything after repo_url, removing leading slashes
        path_part = file_path[repo_end:].lstrip('/')
        return '/' + path_part if path_part else file_path
    
    # If it doesn't start with '/', add it
    if not file_path.startswith('/'):
        file_path = '/' + file_path
    
    return file_path

@router.post("/project/{project_name}/scan")
async def start_scan(request: Request, project_name: str, ref_type: str = Form(...), 
                    ref: str = Form(...), current_user: str = Depends(get_current_user), _: bool = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check microservice health
    if not await check_microservice_health():
        return RedirectResponse(url=get_full_url(f"project/{project_name}?error=microservice_unavailable"), status_code=302)
    
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
    user_logger.info(f"User '{current_user}' started scan for project '{project_name}' ({ref_type}: {ref})")
    
    # Start scan via microservice - ИСПРАВЛЕН callback URL
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
                return RedirectResponse(url=get_full_url(f"project/{project_name}?error=microservice_invalid_response"), status_code=302)
            
            if response.status_code == 200 and result.get("status") == "accepted":
                # Success - update scan status to running
                scan.status = "running"
                scan.ref = result.get("Ref", ref)  # Use resolved ref from microservice
                db.commit()
                return RedirectResponse(url=get_full_url(f"scan/{scan_id}"), status_code=302)
            else:
                # Microservice returned an error (could be 400, 500, etc.)
                scan.status = "failed"
                db.commit()
                error_msg = result.get("message", "Unknown error from microservice")
                # URL encode the error message to handle special characters
                encoded_error = urllib.parse.quote(error_msg)
                return RedirectResponse(url=get_full_url(f"project/{project_name}?error={encoded_error}"), status_code=302)
                
    except httpx.TimeoutException:
        scan.status = "failed"
        db.commit()
        return RedirectResponse(url=get_full_url(f"project/{project_name}?error=microservice_timeout"), status_code=302)
    except Exception as e:
        scan.status = "failed"
        db.commit()
        return RedirectResponse(url=get_full_url(f"project/{project_name}?error=microservice_connection_error"), status_code=302)

@router.post("/project/{project_name}/local-scan")
async def start_local_scan(request: Request, project_name: str, 
                          commit: str = Form(...), zip_file: UploadFile = File(...),
                          _: bool = Depends(get_current_user), current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check microservice health
    if not await check_microservice_health():
        return RedirectResponse(url=get_full_url(f"project/{project_name}?error=microservice_unavailable"), status_code=302)
    
    # Validate file type
    if not zip_file.filename.endswith('.zip'):
        return RedirectResponse(url=get_full_url(f"project/{project_name}?error=invalid_file_format"), status_code=302)
    
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
    user_logger.info(f"User '{current_user}' started local scan for project '{project_name}' (commit: {commit})")
    
    # Prepare callback URL - ИСПРАВЛЕН
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
                return RedirectResponse(url=get_full_url(f"project/{project_name}?error=microservice_invalid_response"), status_code=302)
            
            if response.status_code == 200 and result.get("status") == "accepted":
                scan.status = "running"
                db.commit()
                return RedirectResponse(url=get_full_url(f"scan/{scan_id}"), status_code=302)
            else:
                scan.status = "failed"
                scan.error_message = result.get("message", "Unknown error")
                db.commit()
                error_msg = result.get("message", "Unknown error from microservice")
                encoded_error = urllib.parse.quote(error_msg)
                return RedirectResponse(url=get_full_url(f"project/{project_name}?error={encoded_error}"), status_code=302)
                
    except httpx.TimeoutException:
        scan.status = "failed"
        scan.error_message = "Microservice timeout"
        db.commit()
        return RedirectResponse(url=get_full_url(f"project/{project_name}?error=microservice_timeout"), status_code=302)
    except Exception as e:
        scan.status = "failed"
        scan.error_message = str(e)
        db.commit()
        return RedirectResponse(url=get_full_url(f"project/{project_name}?error=local_scan_failed"), status_code=302)

@router.get("/scan/{scan_id}", response_class=HTMLResponse)
async def scan_status(request: Request, scan_id: str, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    return templates.TemplateResponse("scan_status.html", {
        "request": request,
        "scan": scan,
        "current_user": current_user
    })

@router.get("/api/scan/{scan_id}/status")
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
        "files_scanned": scan.files_scanned,
        "excluded_files_count": scan.excluded_files_count
    }

async def process_scan_results_background(scan_id: str, data: dict, db_session: Session):
    """Background task для обработки результатов сканирования"""
    start_time = datetime.now()
    
    try:
        # Поиск скана в БД
        scan = db_session.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            logger.error(f"❌ Скан не найден в БД: {scan_id}")
            return
        
        project_name = scan.project_name
        logger.info(f"🔍 Текущий статус скана {scan_id}: {scan.status}")

        # Check if scan completed with error
        if data.get("Status") == "Error":
            scan.status = "failed"
            scan.completed_at = datetime.now()
            error_message = data.get("Message", "Unknown error occurred during scanning")
            logger.error(f"💥 Скан {scan_id} завершился с ошибкой: {error_message}")
            scan.error_message = error_message
            db_session.commit()
            
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"⏱️ Обработка ошибки скана {scan_id} заняла {processing_time:.2f} секунд")
            return

        # Handle partial results
        if data.get("Status") == "partial":
            files_scanned = data.get("AllFiles", 0)
            excluded_files_count = data.get("FilesExcluded", 0)
            excluded_files_list = data.get("SkippedFiles", "")

            scan.files_scanned = files_scanned
            scan.excluded_files_count = excluded_files_count
            scan.excluded_files_list = excluded_files_list
            db_session.commit()
            logger.info(f"📊 Частичные результаты для scan {scan_id}: {files_scanned} файлов просканировано")
            return

        # Handle complete results
        if data.get("Status") == "completed":
            logger.info(f"🎉 Скан {scan_id} завершен успешно")
            
            # Обновляем основную информацию о скане
            scan.status = "completed"
            scan.repo_commit = data.get("RepoCommit")
            scan.completed_at = datetime.now()
            scan.files_scanned = data.get("AllFiles")
            scan.excluded_files_count = data.get("FilesExcluded")
            scan.excluded_files_list = data.get("SkippedFiles")
            
            # Обработка данных о языках программирования
            detected_languages = data.get("DetectedLanguages", {})
            if detected_languages:
                scan.detected_languages = json.dumps(detected_languages, ensure_ascii=False)
                logger.info(f"🔍 Обнаружено языков: {len(detected_languages)}")
            
            # Обработка данных о фреймворках
            detected_frameworks = data.get("DetectedFrameworks", {})
            if detected_frameworks:
                scan.detected_frameworks = json.dumps(detected_frameworks, ensure_ascii=False)
                logger.info(f"🎯 Обнаружено фреймворков: {len(detected_frameworks)}")

            db_session.commit()
            
            logger.info(f"📂 Итого файлов просканировано: {scan.files_scanned}. Пропущено по правилам: {scan.excluded_files_count}")
            logger.info(f"🔗 Commit: {scan.repo_commit}")
            
            # Clear existing secrets for this scan
            existing_secrets_count = db_session.query(func.count(Secret.id)).filter(Secret.scan_id == scan_id).scalar()
            if existing_secrets_count > 0:
                logger.info(f"🗑️ Удаляем {existing_secrets_count} существующих секретов для scan {scan_id}")
                db_session.query(Secret).filter(Secret.scan_id == scan_id).delete()
                db_session.commit()
            
            results = data.get("Results", [])
            logger.info(f"🔍 Получено {len(results)} новых секретов для обработки")
            
            # Get previous scans for this project
            previous_scans_start = datetime.now()
            previous_scans = db_session.query(Scan).filter(
                Scan.project_name == project_name,
                Scan.id != scan_id,
                Scan.completed_at.is_not(None)
            ).order_by(Scan.completed_at.desc()).limit(5).all()  # Только 5 последних сканов
            
            previous_scans_time = (datetime.now() - previous_scans_start).total_seconds()
            logger.info(f"📋 Найдено {len(previous_scans)} предыдущих сканов за {previous_scans_time:.2f} секунд")
            
            # Get manual secrets только из последнего скана
            manual_secrets = []
            if previous_scans:
                most_recent_scan = previous_scans[0]
                manual_secrets = db_session.query(Secret).filter(
                    Secret.scan_id == most_recent_scan.id,
                    Secret.secret.like("% (добавлен вручную, см. context)")
                ).all()
                logger.info(f"📝 Найдено {len(manual_secrets)} ручных секретов из предыдущего скана")
            
            # Создаем мапу предыдущих секретов для быстрого поиска
            mapping_start = datetime.now()
            previous_secrets_map = {}
            if previous_scans and len(results) < 10000:  # Только для разумного количества
                logger.info(f"🗺️ Создаем карту предыдущих статусов для {len(results)} секретов")
                for prev_scan in previous_scans[:2]:  # Только 2 последних скана
                    prev_secrets = db_session.query(Secret).filter(
                        Secret.scan_id == prev_scan.id,
                        Secret.status != "No status"
                    ).all()
                    
                    for prev_secret in prev_secrets:
                        key = (prev_secret.path, prev_secret.line, prev_secret.secret, prev_secret.type)
                        if key not in previous_secrets_map:
                            previous_secrets_map[key] = prev_secret
                
                mapping_time = (datetime.now() - mapping_start).total_seconds()
                logger.info(f"🗺️ Карта предыдущих статусов создана за {mapping_time:.2f} секунд ({len(previous_secrets_map)} записей)")
            else:
                logger.info(f"⏭️ Пропускаем создание карты статусов (слишком много секретов: {len(results)})")
            
            # Обрабатываем секреты батчами
            batch_size = 1000
            total_processed = 0
            batch_processing_start = datetime.now()
            
            for i in range(0, len(results), batch_size):
                batch_start = datetime.now()
                batch = results[i:i + batch_size]
                batch_secrets = []
                
                logger.info(f"🔄 Обрабатываем батч {i//batch_size + 1}/{(len(results) + batch_size - 1)//batch_size} ({len(batch)} секретов)")
                
                # Обработка секретов в батче
                for j, result in enumerate(batch):
                    try:
                        # Быстрый поиск предыдущего статуса
                        most_recent_secret = None
                        if previous_secrets_map:
                            key = (result.get("path"), result.get("line"), result.get("secret"), result.get("Type", result.get("type")))
                            most_recent_secret = previous_secrets_map.get(key)
                        
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
                            else:
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
                            severity = result.get("severity", result.get("Severity", "High"))

                        secret = Secret(
                            scan_id=scan_id,
                            path=sanitize_string(result.get("path", "")),
                            line=result.get("line", 0),
                            secret=sanitize_string(result.get("secret", "")),
                            context=sanitize_string(result.get("context", "")),
                            severity=severity,
                            confidence=result.get("confidence", 1.0),
                            type=sanitize_string(result.get("Type", result.get("type", "Unknown"))),
                            is_exception=is_exception,
                            exception_comment=sanitize_string(exception_comment) if exception_comment else None,
                            status=status,
                            refuted_at=refuted_at,
                            confirmed_by=most_recent_secret.confirmed_by if most_recent_secret else None,
                            refuted_by=most_recent_secret.refuted_by if most_recent_secret else None
                        )
                        batch_secrets.append(secret)
                    except Exception as e:
                        logger.error(f"❌ Ошибка при создании объекта Secret для секрета {j} в батче {i//batch_size + 1}: {type(e).__name__}: {e}")
                        continue
                
                # Сохраняем батч
                if batch_secrets:  # Только если есть что сохранять
                    db_session.add_all(batch_secrets)
                    db_session.commit()
                    total_processed += len(batch_secrets)
                    
                    batch_time = (datetime.now() - batch_start).total_seconds()
                    logger.info(f"✅ Батч {i//batch_size + 1} обработан за {batch_time:.2f} секунд ({len(batch_secrets)} секретов)")
                else:
                    logger.warning(f"⚠️ Батч {i//batch_size + 1} пуст - нечего сохранять")
            
            batch_processing_time = (datetime.now() - batch_processing_start).total_seconds()
            logger.info(f"📦 Все батчи обработаны за {batch_processing_time:.2f} секунд (итого: {total_processed} секретов)")
            
            # Add manual secrets
            manual_secrets_start = datetime.now()
            added_manual_count = 0
            for manual_secret in manual_secrets:
                existing_manual = db_session.query(Secret).filter(
                    Secret.scan_id == scan_id,
                    Secret.secret == manual_secret.secret,
                    Secret.path == manual_secret.path,
                    Secret.line == manual_secret.line,
                    Secret.type == manual_secret.type
                ).first()
                
                if not existing_manual:
                    new_manual_secret = Secret(
                        scan_id=scan_id,
                        path=manual_secret.path,
                        line=manual_secret.line,
                        secret=manual_secret.secret,
                        context=manual_secret.context,
                        severity=manual_secret.severity,
                        type=manual_secret.type,
                        status=manual_secret.status,
                        is_exception=manual_secret.is_exception,
                        exception_comment=manual_secret.exception_comment,
                        confirmed_by=manual_secret.confirmed_by,
                        refuted_by=manual_secret.refuted_by,
                        refuted_at=manual_secret.refuted_at
                    )
                    db_session.add(new_manual_secret)
                    added_manual_count += 1
            
            if added_manual_count > 0:
                db_session.commit()
                manual_secrets_time = (datetime.now() - manual_secrets_start).total_seconds()
                logger.info(f"📝 Добавлено {added_manual_count} ручных секретов за {manual_secrets_time:.2f} секунд")
            
            total_processing_time = (datetime.now() - start_time).total_seconds()
            update_scan_counters(db_session, scan_id)
            logger.info(f"🎊 Скан {scan_id} полностью обработан за {total_processing_time:.2f} секунд:")
            logger.info(f"   📊 Всего секретов: {len(results)}")
            logger.info(f"   📝 Ручных секретов: {added_manual_count}")
            logger.info(f"   📂 Файлов просканировано: {scan.files_scanned}")
            logger.info(f"   📂 Файлов пропущено по правилам: {scan.excluded_files_count}")
            logger.info(f"   🗺️ Применено предыдущих статусов: {len(previous_secrets_map)}")
            
            return

        logger.warning(f"❓ Неизвестный статус получен для scan {scan_id}: {data.get('Status')}")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при обработке результатов скана {scan_id}: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"📋 Traceback: {traceback.format_exc()}")
        
        # Попытаемся пометить скан как failed
        try:
            scan = db_session.query(Scan).filter(Scan.id == scan_id).first()
            if scan:
                scan.status = "failed"
                scan.completed_at = datetime.now()
                scan.error_message = f"Background processing error: {str(e)}"
                db_session.commit()
        except:
            pass

def update_scan_counters(db: Session, scan_id: str):
    try:
        """Update denormalized counters in scans table"""
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
        
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if scan:
            scan.high_secrets_count = high_count
            scan.potential_secrets_count = potential_count
            db.commit()
    except Exception as error:
        logger.error(error)

@router.post("/get_results/{project_name}/{scan_id}")
async def receive_scan_results(project_name: str, scan_id: str, request: Request, 
                              background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    start_time = datetime.now()
    logger.info(f"📥 Получен callback для scan_id: {scan_id}, project: {project_name}")
    
    try:
        # Получаем raw данные
        try:
            raw_data = await request.json()
            logger.info(f"📊 Размер полученных данных: {len(str(raw_data))} символов")
        except Exception as e:
            logger.error(f"❌ Ошибка чтения JSON из request для scan {scan_id}: {type(e).__name__}: {e}")
            return {"status": "error", "message": "Failed to parse JSON from request"}
        
        # Декомпрессируем если нужно
        try:
            data = decompress_callback_data(raw_data)
            logger.info(f"✅ Данные успешно декомпрессированы для scan {scan_id}")
        except ValueError as e:
            logger.error(f"❌ Ошибка декомпрессии для scan {scan_id}: {e}")
            return {"status": "error", "message": "Data decompression failed"}
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при декомпрессии для scan {scan_id}: {type(e).__name__}: {e}")
            return {"status": "error", "message": "Unexpected decompression error"}
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при получении данных для scan {scan_id}: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"📋 Traceback: {traceback.format_exc()}")
        return {"status": "error", "message": "Critical error processing request data"}

    # Быстрая проверка что скан существует
    try:
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            logger.error(f"❌ Скан не найден в БД: {scan_id}")
            return {"status": "error", "message": "Scan not found"}
        logger.info(f"🔍 Текущий статус скана {scan_id}: {scan.status}")
    except Exception as e:
        logger.error(f"❌ Ошибка при поиске скана {scan_id} в БД: {type(e).__name__}: {e}")
        return {"status": "error", "message": "Database error while finding scan"}

    # Запускаем обработку в фоне
    try:
        background_tasks.add_task(process_scan_results_background, scan_id, data, db)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"⚡ Callback для scan {scan_id} принят и отправлен в фоновую обработку за {processing_time:.2f} секунд")
        
        return {"status": "accepted", "message": "Results received and queued for processing"}
    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении задачи в фон для scan {scan_id}: {type(e).__name__}: {e}")
        return {"status": "error", "message": "Failed to queue background processing"}

@router.get("/scan/{scan_id}/results", response_class=HTMLResponse)
async def scan_results(request: Request, scan_id: str, severity_filter: str = "", 
                     type_filter: str = "", show_exceptions: bool = False,
                     current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    #import time
    update_scan_counters(db, scan_id)
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    # Get project info
    project = db.query(Project).filter(Project.name == scan.project_name).first()
    
    # Оптимизированный запрос секретов с упрощенной сортировкой
    #start = time.time()
    all_secrets_query = db.query(Secret).filter(Secret.scan_id == scan_id).order_by(
        Secret.severity == 'Potential',  # Вернуть оригинальное выражение
        Secret.path,
        Secret.line
    ).all()
    #print(f"Секреты загружены за: {time.time() - start:.2f}с")
    
    # Используем денормализованные счетчики из таблицы scans
    high_secrets = scan.high_secrets_count or 0
    potential_secrets = scan.potential_secrets_count or 0
    total_secrets = high_secrets + potential_secrets
    
    # Получить уникальные типы и severity одним запросом каждый
    unique_types_query = db.query(Secret.type.distinct()).filter(Secret.scan_id == scan_id)
    unique_types = [row[0] for row in unique_types_query.all() if row[0]]
    
    unique_severities_query = db.query(Secret.severity.distinct()).filter(Secret.scan_id == scan_id)
    unique_severities = [row[0] for row in unique_severities_query.all() if row[0]]
    
    # Инициализируем переменные
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
    #start = time.time()
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
            "confidence": float(secret.confidence) if secret.confidence is not None else 1.0,
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
    
    #print(f"Обработка секретов: {time.time() - start:.2f}с")

    return templates.TemplateResponse("scan_results.html", {
        "request": request,
        "scan": scan,
        "project": project,
        "secrets_data": secrets_data,
        "project_repo_url": project.repo_url or "",
        "scan_commit": scan.repo_commit or "",
        "unique_types": unique_types,
        "unique_severities": unique_severities,
        "total_secrets": total_secrets,
        "high_secrets": high_secrets,
        "potential_secrets": potential_secrets,
        "HUB_TYPE": HUB_TYPE,
        "current_filters": {
            "severity": severity_filter,
            "type": type_filter,
            "show_exceptions": show_exceptions
        },
        "current_user": current_user
    })

@router.post("/secrets/{secret_id}/update-status")
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
        secret.refuted_at = datetime.now()
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
    
    # Обновляем денормализованные счетчики
    update_scan_counters(db, secret.scan_id)
    user_logger.info(f"User '{current_user}' updated secret status to '{status}' for secret ID {secret_id}")
    
    return {"status": "success"}

@router.post("/secrets/bulk-action")
async def bulk_secret_action(request: Request, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    secret_ids = data.get("secret_ids", [])
    action = data.get("action")
    value = data.get("value", "")
    comment = data.get("comment", "")
    
    secrets = db.query(Secret).filter(Secret.id.in_(secret_ids)).all()
    affected_scan_ids = set()
    
    for secret in secrets:
        affected_scan_ids.add(secret.scan_id)
        
        if action == "status":
            secret.status = value
            if value == "Refuted":
                secret.is_exception = True
                secret.exception_comment = comment
                secret.refuted_at = datetime.now()
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
    
    # Обновляем счетчики для всех затронутых сканов
    for scan_id in affected_scan_ids:
        update_scan_counters(db, scan_id)
    user_logger.info(f"User '{current_user}' performed bulk action '{action}' on {len(secret_ids)} secrets (value: '{value}')")
    return {"status": "success"}

@router.post("/secrets/add-custom")
async def add_custom_secret(request: Request, scan_id: str = Form(...), secret_value: str = Form(...),
                           context: str = Form(...), line: int = Form(...), secret_type: str = Form(...),
                           file_path: str = Form(...), current_user: str = Depends(get_current_user), 
                           db: Session = Depends(get_db)):
    """Add a custom secret found by user"""
    try:
        logger.info(f"Attempting to add custom secret for scan_id: {scan_id}")
        
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            logger.error(f"Scan not found in database: {scan_id}")
            return JSONResponse(status_code=404, content={"status": "error", "message": f"Scan not found: {scan_id}"})
        
        project = db.query(Project).filter(Project.name == scan.project_name).first()
        if not project:
            logger.error(f"Project not found: {scan.project_name}")
            return JSONResponse(status_code=404, content={"status": "error", "message": "Project not found"})
        
        normalized_path = normalize_file_path(file_path, project.repo_url)
        
        modified_secret_value = secret_value + " (добавлен вручную, см. context)"
        
        manual_context_info = "\nДанный секрет был добавлен вручную. Перед выставлением замечаний - перепроверьте существует ли данный секрет в текущей версии кода. \nЕсли данного секрета больше не существует - вы можете удалить эту запись по кнопке снизу"
        full_context = context + manual_context_info
        
        existing_secret = db.query(Secret).filter(
            Secret.scan_id == scan_id,
            Secret.path == normalized_path,
            Secret.line == line,
            Secret.secret == modified_secret_value
        ).first()
        
        if existing_secret:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Secret already exists"})
        
        new_secret = Secret(
            scan_id=scan_id,
            path=normalized_path,
            line=line,
            secret=modified_secret_value,
            context=full_context,
            severity="High",
            confidence=1.0,
            type=secret_type,
            status="Confirmed",
            is_exception=False,
            confirmed_by=current_user
        )
        
        db.add(new_secret)
        db.commit()
        
        # Обновляем денормализованные счетчики
        update_scan_counters(db, scan_id)
        user_logger.info(f"User '{current_user}' added custom secret to scan '{scan_id}' in project '{scan.project_name}'")
        
        logger.info(f"Custom secret successfully added with ID: {new_secret.id}")
        
        # Get updated secrets data
        all_secrets_query = db.query(Secret).filter(Secret.scan_id == scan_id).order_by(
            Secret.severity == 'Potential',
            Secret.path,
            Secret.line
        ).all()
        
        secrets_data = []
        for secret in all_secrets_query:
            secret_obj = {
                "id": secret.id,
                "path": html.escape(secret.path or "", quote=True),
                "line": secret.line or 0,
                "secret": html.escape(secret.secret or "", quote=True),
                "context": html.escape(secret.context or "", quote=True),
                "severity": secret.severity or "",
                "type": html.escape(secret.type or "", quote=True),
                "confidence": float(secret.confidence) if secret.confidence is not None else 1.0,
                "status": secret.status or "No status",
                "is_exception": bool(secret.is_exception),
                "exception_comment": html.escape(secret.exception_comment or "", quote=True),
                "refuted_at": secret.refuted_at.strftime('%Y-%m-%d %H:%M') if secret.refuted_at else None,
                "confirmed_by": secret.confirmed_by if secret.confirmed_by else None,
                "refuted_by": secret.refuted_by if secret.refuted_by else None,
                "previous_status": None,
                "previous_scan_date": None
            }
            secrets_data.append(secret_obj)
        
        logger.info(f"Custom secret added by {current_user} to scan {scan_id}")
        return JSONResponse(
            status_code=200,
            content={
                "status": "success", 
                "message": "Secret added successfully",
                "secrets_data": secrets_data
            }
        )
        
    except Exception as e:
        logger.error(f"Error adding custom secret: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Failed to add secret: {str(e)}"})

@router.post("/secrets/{secret_id}/delete")
async def delete_secret(secret_id: int, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete a secret from database"""
    try:
        secret = db.query(Secret).filter(Secret.id == secret_id).first()
        if not secret:
            return JSONResponse(status_code=404, content={"status": "error", "message": "Secret not found"})
        
        scan_id = secret.scan_id
        db.delete(secret)
        db.commit()
        
        # Обновляем денормализованные счетчики
        update_scan_counters(db, scan_id)
        
        # Get updated secrets data
        all_secrets_query = db.query(Secret).filter(Secret.scan_id == scan_id).order_by(
            Secret.severity == 'Potential',
            Secret.path,
            Secret.line
        ).all()
        
        secrets_data = []
        for secret in all_secrets_query:
            secret_obj = {
                "id": secret.id,
                "path": html.escape(secret.path or "", quote=True),
                "line": secret.line or 0,
                "secret": html.escape(secret.secret or "", quote=True),
                "context": html.escape(secret.context or "", quote=True),
                "severity": secret.severity or "",
                "type": html.escape(secret.type or "", quote=True),
                "confidence": float(secret.confidence) if secret.confidence is not None else 1.0,
                "status": secret.status or "No status",
                "is_exception": bool(secret.is_exception),
                "exception_comment": html.escape(secret.exception_comment or "", quote=True),
                "refuted_at": secret.refuted_at.strftime('%Y-%m-%d %H:%M') if secret.refuted_at else None,
                "confirmed_by": secret.confirmed_by if secret.confirmed_by else None,
                "refuted_by": secret.refuted_by if secret.refuted_by else None,
                "previous_status": None,
                "previous_scan_date": None
            }
            secrets_data.append(secret_obj)
        
        logger.info(f"Secret {secret_id} deleted by {current_user}")
        return {
            "status": "success",
            "message": "Secret deleted successfully", 
            "secrets_data": secrets_data
        }
        
    except Exception as e:
        logger.error(f"Error deleting secret: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to delete secret"})

@router.post("/scan/{scan_id}/delete")
async def delete_scan(scan_id: str, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    project_name = scan.project_name
    
    # Delete all secrets and exceptions related to this scan
    db.query(Secret).filter(Secret.scan_id == scan_id).delete()
    
    # Delete the scan itself
    db.delete(scan)
    db.commit()
    user_logger.warning(f"User '{current_user}' deleted scan '{scan_id}' from project '{project_name}'")
    
    return RedirectResponse(url=get_full_url(f"project/{project_name}?success=scan_deleted"), status_code=302)

@router.get("/scan/{scan_id}/export")
async def export_scan_results(scan_id: str, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
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
    filename = f"{scan.project_name}_{commit_short}.json"
    
    # Генерируем отформатированный JSON
    formatted_json = json.dumps(export_data, indent=2, ensure_ascii=False)
    user_logger.info(f"Results for {scan_id} exported by user '{current_user}' (JSON)")
    return Response(
        content=formatted_json,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/scan/{scan_id}/export-html")
async def export_scan_results_html(scan_id: str, current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    project = db.query(Project).filter(Project.name == scan.project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Подсчитать количество секретов перед их загрузкой
    secrets_count = db.query(func.count(Secret.id)).filter(
        Secret.scan_id == scan_id,
        Secret.is_exception == False
    ).scalar() or 0
    
    # Проверить лимит
    if secrets_count > 3000:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot generate HTML report: too many secrets ({secrets_count}). Maximum allowed: 3000. Please use JSON export instead."
        )
    
    secrets = db.query(Secret).filter(
        Secret.scan_id == scan_id,
        Secret.is_exception == False
    ).order_by(
        Secret.severity == 'Potential',
        Secret.path,
        Secret.line
    ).all()
    
    # Выполнить генерацию отчета в отдельном потоке
    html_content = await asyncio.to_thread(
        generate_html_report, scan, project, secrets, HUB_TYPE
    )
    
    commit_short = scan.repo_commit[:7] if scan.repo_commit else "unknown"
    filename = f"{scan.project_name}_{commit_short}.html"
    
    safe_filename = filename.encode('ascii', 'ignore').decode('ascii')
    user_logger.info(f"Results for {scan_id} exported by user '{current_user}' (HTML)")
    return HTMLResponse(
        content=html_content,
        headers={"Content-Disposition": f"attachment; filename={safe_filename}"}
    )