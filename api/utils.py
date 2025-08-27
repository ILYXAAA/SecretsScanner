import secrets
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from models import ApiToken, ApiUsage

# Token configuration
TOKEN_PREFIX = "ss_live_"
TOKEN_LENGTH = 32  # Length of random part after prefix

def generate_api_token() -> tuple[str, str]:
    """
    Generate a new API token and return (full_token, hash)
    
    Returns:
        tuple: (full_token, sha256_hash)
    """
    # Generate random token part
    random_part = secrets.token_urlsafe(TOKEN_LENGTH)[:TOKEN_LENGTH]
    
    # Create full token with prefix
    full_token = TOKEN_PREFIX + random_part
    
    # Create hash for storage
    token_hash = hashlib.sha256(full_token.encode()).hexdigest()
    
    return full_token, token_hash

def hash_token(token: str) -> str:
    """Hash a token for secure storage"""
    return hashlib.sha256(token.encode()).hexdigest()

def get_token_prefix(token: str) -> str:
    """Extract prefix from token for identification"""
    if len(token) >= 12:
        return token[:12] + "..."
    return token

def validate_token_format(token: str) -> bool:
    """Validate token format"""
    if not token.startswith(TOKEN_PREFIX):
        return False
    
    if len(token) != len(TOKEN_PREFIX) + TOKEN_LENGTH:
        return False
    
    # Check that random part contains only valid URL-safe characters
    random_part = token[len(TOKEN_PREFIX):]
    valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    return all(c in valid_chars for c in random_part)

def get_token_by_hash(db: Session, token: str) -> Optional[ApiToken]:
    """
    Get API token from database by token string
    
    Args:
        db: Database session
        token: Full token string
    
    Returns:
        ApiToken or None if not found
    """
    if not validate_token_format(token):
        return None
    
    token_hash = hash_token(token)
    return db.query(ApiToken).filter(
        ApiToken.token_hash == token_hash,
        ApiToken.is_active == True
    ).first()

def is_token_expired(token: ApiToken) -> bool:
    """Check if token is expired"""
    if token.expires_at is None:
        return False
    
    return datetime.now() > token.expires_at

def get_token_permissions(token: ApiToken) -> Dict[str, bool]:
    """
    Parse token permissions from JSON
    
    Args:
        token: ApiToken instance
    
    Returns:
        Dictionary of permissions
    """
    try:
        return json.loads(token.permissions)
    except (json.JSONDecodeError, TypeError):
        return {}

def has_permission(token: ApiToken, permission: str) -> bool:
    """
    Check if token has specific permission
    
    Args:
        token: ApiToken instance
        permission: Permission string (e.g., 'project_add', 'scan')
    
    Returns:
        Boolean indicating if permission is granted
    """
    permissions = get_token_permissions(token)
    return permissions.get(permission, False)

def update_token_last_used(db: Session, token: ApiToken):
    """Update token's last_used_at timestamp"""
    token.last_used_at = datetime.now()
    db.commit()

def log_api_usage(
    db: Session,
    token_id: int,
    endpoint: str,
    response_status: int,
    response_time_ms: int,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
):
    """
    Log API usage to database
    
    Args:
        db: Database session
        token_id: API token ID
        endpoint: API endpoint called
        response_status: HTTP response status
        response_time_ms: Response time in milliseconds
        ip_address: Client IP address
        user_agent: Client User-Agent
    """
    usage_record = ApiUsage(
        token_id=token_id,
        endpoint=endpoint,
        response_status=response_status,
        response_time_ms=response_time_ms,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    db.add(usage_record)
    db.commit()

def create_default_permissions() -> Dict[str, bool]:
    """Create default permissions set for new tokens"""
    return {
        "project_add": False,
        "project_check": True,
        "scan": False,
        "multi_scan": False,
        "scan_results": True
    }

def validate_permissions(permissions: Dict[str, Any]) -> Dict[str, bool]:
    """
    Validate and clean permissions dictionary
    
    Args:
        permissions: Raw permissions dictionary
    
    Returns:
        Cleaned permissions with only valid keys and boolean values
    """
    valid_permissions = [
        "project_add",
        "project_check", 
        "scan",
        "multi_scan",
        "scan_results"
    ]
    
    cleaned = {}
    for key, value in permissions.items():
        if key in valid_permissions:
            # Convert to boolean
            cleaned[key] = bool(value)
    
    # Ensure all valid permissions are present with default False
    for perm in valid_permissions:
        if perm not in cleaned:
            cleaned[perm] = False
    
    return cleaned