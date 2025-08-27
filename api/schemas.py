from pydantic import BaseModel, field_validator, model_validator
from typing import List, Optional, Self
import re

class ProjectAddRequest(BaseModel):
    repository: str
    
    @field_validator('repository')
    @classmethod
    def validate_repository(cls, v):
        if not v or not v.strip():
            raise ValueError('Repository URL cannot be empty')
        
        v = v.strip()
        
        # Check for parameters or commit paths
        if "?" in v:
            raise ValueError("Repository URL should not contain parameters (version, commit etc.). Use base repository URL.")
        
        if "/commit/" in v:
            raise ValueError("Repository URL should not contain commit path (/commit/). Use base repository URL.")
        
        return v

class ProjectCheckRequest(BaseModel):
    repository: Optional[str] = None
    project_name: Optional[str] = None
    
    @field_validator('repository', 'project_name')
    @classmethod
    def validate_fields(cls, v):
        if v is not None:
            return v.strip() if v.strip() else None
        return v
    
    @model_validator(mode='after')
    def validate_required_fields(self) -> Self:
        if not self.repository and not self.project_name:
            raise ValueError("Either 'repository' or 'project_name' must be provided")
        return self

class ScanRequest(BaseModel):
    repository: str
    commit: str
    
    @field_validator('repository')
    @classmethod
    def validate_repository(cls, v):
        if not v or not v.strip():
            raise ValueError('Repository URL cannot be empty')
        return v.strip()
    
    @field_validator('commit')
    @classmethod
    def validate_commit(cls, v):
        if not v or not v.strip():
            raise ValueError('Commit cannot be empty')
        
        v = v.strip()
        
        # Basic commit hash validation (should be alphanumeric, 7-40 chars)
        if not re.match(r'^[a-fA-F0-9]{7,40}$', v):
            raise ValueError('Commit should be a valid hash (7-40 alphanumeric characters)')
        
        return v

class MultiScanRequestItem(BaseModel):
    repository: str
    commit: str
    
    @field_validator('repository')
    @classmethod
    def validate_repository(cls, v):
        if not v or not v.strip():
            raise ValueError('Repository URL cannot be empty')
        return v.strip()
    
    @field_validator('commit')
    @classmethod
    def validate_commit(cls, v):
        if not v or not v.strip():
            raise ValueError('Commit cannot be empty')
        
        v = v.strip()
        
        # Basic commit hash validation
        if not re.match(r'^[a-fA-F0-9]{7,40}$', v):
            raise ValueError('Commit should be a valid hash (7-40 alphanumeric characters)')
        
        return v

# For multi-scan, we expect a direct list of items
MultiScanRequest = List[MultiScanRequestItem]

# Response schemas
class SuccessResponse(BaseModel):
    success: bool = True
    message: str

class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: Optional[str] = None

class ProjectAddResponse(BaseModel):
    success: bool
    message: str

class ProjectCheckResponse(BaseModel):
    exists: bool
    project_name: str

class ScanResponse(BaseModel):
    success: bool
    message: str
    scan_id: Optional[str] = None

class MultiScanResponse(BaseModel):
    success: bool
    message: str
    scan_id: Optional[str] = None  # multi_scan_id

class ScanStatusResponse(BaseModel):
    scan_id: str
    status: str  # completed, failed, running, not_found, pending
    message: str

class ScanResultsResponse(BaseModel):
    scan_id: str
    status: str  # completed, not_found
    results: Optional[List[dict]] = None

# Validation helper functions
def validate_scan_id(scan_id: str) -> bool:
    """Validate scan ID format (UUID)"""
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    return bool(re.match(uuid_pattern, scan_id, re.IGNORECASE))

def sanitize_repository_url(repo_url: str) -> str:
    """Sanitize and normalize repository URL"""
    if not repo_url:
        return repo_url
    
    # Remove trailing slashes
    repo_url = repo_url.rstrip('/')
    
    # Basic URL validation
    if not repo_url.startswith(('http://', 'https://', 'git@')):
        raise ValueError('Repository URL must start with http://, https://, or git@')
    
    return repo_url