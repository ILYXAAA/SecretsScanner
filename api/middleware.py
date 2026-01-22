import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from collections import defaultdict, deque
from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from services.database import get_db
from models import ApiToken
from api.utils import get_token_by_hash, is_token_expired, update_token_last_used, log_api_usage

logger = logging.getLogger("main")

# In-memory rate limiting storage
# Structure: {token_id: {"minute": deque(), "hour": deque(), "day": deque()}}
rate_limit_storage: Dict[int, Dict[str, deque]] = defaultdict(lambda: {
    "minute": deque(),
    "hour": deque(), 
    "day": deque()
})

def cleanup_old_requests():
    """Clean up old request timestamps to prevent memory leaks"""
    current_time = time.time()
    
    for token_id in list(rate_limit_storage.keys()):
        token_data = rate_limit_storage[token_id]
        
        # Clean up requests older than 1 day
        while token_data["day"] and current_time - token_data["day"][0] > 86400:  # 24 hours
            token_data["day"].popleft()
        
        # Clean up requests older than 1 hour
        while token_data["hour"] and current_time - token_data["hour"][0] > 3600:  # 1 hour
            token_data["hour"].popleft()
        
        # Clean up requests older than 1 minute
        while token_data["minute"] and current_time - token_data["minute"][0] > 60:  # 1 minute
            token_data["minute"].popleft()
        
        # Remove token entry if all queues are empty
        if not any([token_data["minute"], token_data["hour"], token_data["day"]]):
            del rate_limit_storage[token_id]

def check_rate_limits(token: ApiToken) -> Tuple[bool, str]:
    """
    Check if token has exceeded rate limits
    
    Returns:
        Tuple[bool, str]: (is_allowed, error_message)
    """
    current_time = time.time()
    token_data = rate_limit_storage[token.id]
    
    # Cleanup old requests first
    cleanup_old_requests()
    
    # Check minute limit
    minute_count = len([req for req in token_data["minute"] if current_time - req <= 60])
    if minute_count >= token.requests_per_minute:
        return False, f"Rate limit exceeded: {token.requests_per_minute} requests per minute"
    
    # Check hour limit  
    hour_count = len([req for req in token_data["hour"] if current_time - req <= 3600])
    if hour_count >= token.requests_per_hour:
        return False, f"Rate limit exceeded: {token.requests_per_hour} requests per hour"
    
    # Check day limit
    day_count = len([req for req in token_data["day"] if current_time - req <= 86400])
    if day_count >= token.requests_per_day:
        return False, f"Rate limit exceeded: {token.requests_per_day} requests per day"
    
    return True, ""

def record_request(token_id: int):
    """Record a new API request for rate limiting"""
    current_time = time.time()
    token_data = rate_limit_storage[token_id]
    
    # Add to all time windows
    token_data["minute"].append(current_time)
    token_data["hour"].append(current_time) 
    token_data["day"].append(current_time)

def extract_bearer_token(request: Request) -> Optional[str]:
    """Extract Bearer token from X-API-TOKEN header"""
    auth_header = request.headers.get("X-API-TOKEN")
    
    if not auth_header:
        return None
    
    if not auth_header.startswith("Bearer "):
        return None
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    
    if not token.strip():
        return None
        
    return token.strip()

async def get_api_token(request: Request, db: Session = Depends(get_db)) -> ApiToken:
    """
    Dependency to get and validate API token from request
    
    Raises:
        HTTPException: Various HTTP errors for authentication issues
    """
    start_time = time.time()
    
    # Extract token from X-API-TOKEN header
    token_string = extract_bearer_token(request)
    
    if not token_string:
        logger.error(f"[API] Missing or invalid X-API-TOKEN header from '{request.client.host}'")
        raise HTTPException(
            status_code=401,
            detail={"success": False, "message": "Missing or invalid X-API-TOKEN header"}
        )
    
    # Get token from database
    token = get_token_by_hash(db, token_string)
    
    if not token:
        logger.error(f"[API] Invalid token attempt from '{request.client.host}'")
        raise HTTPException(
            status_code=401,
            detail={"success": False, "message": "Invalid X-API-TOKEN token"}
        )
    
    # Check if token is active
    if not token.is_active:
        logger.error(f"[API: {token.name}] Inactive X-API-TOKEN used from '{request.client.host}'")
        raise HTTPException(
            status_code=401,
            detail={"success": False, "message": "API token is inactive"}
        )
    
    # Check if token is expired
    if is_token_expired(token):
        logger.error(f"[API: {token.name}] Expired X-API-TOKEN used from '{request.client.host}'")
        raise HTTPException(
            status_code=401,
            detail={"success": False, "message": "API token has expired"}
        )
    
    # Check rate limits
    is_allowed, error_message = check_rate_limits(token)
    if not is_allowed:
        logger.error(f"[API: {token.name}] Rate limit exceeded from '{request.client.host}': {error_message}")
        raise HTTPException(
            status_code=429,
            detail={"success": False, "message": error_message}
        )
    
    # Record this request for rate limiting
    record_request(token.id)
    
    # Update last used timestamp
    update_token_last_used(db, token)
    
    # Log successful authentication
    processing_time = int((time.time() - start_time) * 1000)
    logger.info(f"[API: {token.name}] Authenticated request to '{request.method}' {request.url.path} from '{request.client.host}' (auth: {processing_time}ms)")
    
    return token

def check_permission(token: ApiToken, permission: str) -> bool:
    """Check if token has required permission"""
    from api.utils import has_permission
    return has_permission(token, permission)

def require_permission(permission: str):
    """Dependency factory for checking specific permissions"""
    async def permission_dependency(token: ApiToken = Depends(get_api_token)) -> ApiToken:
        if not check_permission(token, permission):
            logger.error(f"[API: {token.name}] Permission denied: '{permission}'")
            raise HTTPException(
                status_code=403,
                detail={"success": False, "message": f"Insufficient permissions: {permission} required"}
            )
        return token
    
    return permission_dependency

async def log_api_request(request: Request, call_next):
    """Middleware to log API requests and responses"""
    # Only process API routes
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    
    start_time = time.time()
    
    # Get client info
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    
    try:
        response = await call_next(request)
        
        # Calculate response time
        response_time = int((time.time() - start_time) * 1000)
        
        # Log the request
        endpoint = f"{request.method} {request.url.path}"
        
        # Try to get token info for logging (optional, won't fail if token invalid)
        token_name = "unknown"
        token_id = None
        
        try:
            auth_header = request.headers.get("X-API-TOKEN")
            if auth_header and auth_header.startswith("Bearer "):
                token_string = auth_header[7:].strip()
                if token_string:
                    from services.database import SessionLocal
                    with SessionLocal() as db:
                        token = get_token_by_hash(db, token_string)
                        if token:
                            token_name = token.name
                            token_id = token.id
        except:
            pass  # Ignore errors in token extraction for logging
        
        # Log to database if we have token info
        if token_id:
            try:
                from services.database import SessionLocal
                with SessionLocal() as db:
                    log_api_usage(
                        db=db,
                        token_id=token_id,
                        endpoint=endpoint,
                        response_status=response.status_code,
                        response_time_ms=response_time,
                        ip_address=client_ip,
                        user_agent=user_agent
                    )
            except Exception as e:
                logger.error(f"Failed to log API usage: {e}")
        
        # Log to application logs
        logger.info(f"[API: {token_name}] '{endpoint}' -> '{response.status_code}' ({response_time}ms)")
        
        return response
        
    except Exception as e:
        # Log failed requests
        response_time = int((time.time() - start_time) * 1000)
        endpoint = f"{request.method} {request.url.path}"
        
        logger.error(f"[API] '{endpoint}' failed after {response_time}ms: {str(e)}")
        
        # Re-raise the exception
        raise

# Cleanup task - should be called periodically
def cleanup_rate_limits():
    """Cleanup old rate limit data - call this periodically"""
    cleanup_old_requests()