from pydantic import BaseModel, field_validator, model_validator, Field
from typing import List, Optional
import re

# Request Models

class ProjectAddRequest(BaseModel):
    """Add a new project to the system"""
    repository: str = Field(
        ...,
        description="Repository URL to add for scanning",
        example="https://github.com/user/awesome-project",
        min_length=1
    )
    
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

    class Config:
        json_schema_extra = {
            "example": {
                "repository": "https://github.com/user/awesome-project"
            }
        }


class ProjectCheckRequest(BaseModel):
    """Check if a project exists in the system"""
    repository: Optional[str] = Field(
        None,
        description="Repository URL to check",
        example="https://github.com/user/awesome-project"
    )
    project_name: Optional[str] = Field(
        None,
        description="Project name to check",
        example="awesome-project"
    )
    
    @field_validator('repository', 'project_name')
    @classmethod
    def validate_fields(cls, v):
        if v is not None:
            return v.strip() if v.strip() else None
        return v
    
    @model_validator(mode='after')
    def validate_required_fields(self):
        if not self.repository and not self.project_name:
            raise ValueError("Either 'repository' or 'project_name' must be provided")
        return self

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "repository": "https://github.com/user/awesome-project"
                },
                {
                    "project_name": "awesome-project"
                }
            ]
        }


class ScanRequest(BaseModel):
    """Start a single repository scan"""
    repository: str = Field(
        ...,
        description="Repository URL to scan",
        example="https://github.com/user/awesome-project",
        min_length=1
    )
    commit: str = Field(
        ...,
        description="Git commit hash to scan (7-40 alphanumeric characters)",
        example="abc123def456",
        min_length=7,
        max_length=40
    )
    
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

    class Config:
        json_schema_extra = {
            "example": {
                "repository": "https://github.com/user/awesome-project",
                "commit": "abc123def456"
            }
        }


class MultiScanRequestItem(BaseModel):
    """Individual scan item for multi-scan request"""
    repository: str = Field(
        ...,
        description="Repository URL to scan",
        example="https://github.com/user/project-1"
    )
    commit: str = Field(
        ...,
        description="Git commit hash to scan",
        example="abc123def456"
    )
    
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

# Response Models

class ProjectAddResponse(BaseModel):
    """Response for project addition"""
    success: bool = Field(description="Whether the operation was successful")
    message: str = Field(description="Human-readable result message", example="Project awesome-project created successfully")

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "success": True,
                    "message": "Project awesome-project created successfully"
                },
                {
                    "success": False,
                    "message": "Project with this repository already exists: existing-project"
                }
            ]
        }


class ProjectCheckResponse(BaseModel):
    """Response for project existence check"""
    exists: bool = Field(description="Whether the project exists in the system")
    project_name: str = Field(description="Project name if exists, empty string otherwise")

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "exists": True,
                    "project_name": "awesome-project"
                },
                {
                    "exists": False,
                    "project_name": ""
                }
            ]
        }


class ScanResponse(BaseModel):
    """Response for scan initiation"""
    success: bool = Field(description="Whether the scan was started successfully")
    message: str = Field(description="Human-readable result message")
    scan_id: Optional[str] = Field(None, description="Unique scan identifier for tracking progress", example="550e8400-e29b-41d4-a716-446655440000")

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "success": True,
                    "message": "Scan has been queued",
                    "scan_id": "550e8400-e29b-41d4-a716-446655440000"
                },
                {
                    "success": False,
                    "message": "Project not found. Please add the project first."
                }
            ]
        }


class MultiScanResponse(BaseModel):
    """Response for multi-scan initiation"""
    success: bool = Field(description="Whether the multi-scan was started successfully")
    message: str = Field(description="Human-readable result message")
    scan_id: Optional[str] = Field(None, description="JSON array of individual scan IDs", example='["550e8400-e29b-41d4-a716-446655440000", "550e8400-e29b-41d4-a716-446655440001"]')

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "success": True,
                    "message": "Multi-scan has been queued",
                    "scan_id": "550e8400-e29b-41d4-a716-446655440001"
                },
                {
                    "success": False,
                    "message": "Too many scans requested (max 10)"
                }
            ]
        }


class ScanStatusResponse(BaseModel):
    """Response for scan status check"""
    scan_id: str = Field(description="Scan identifier")
    status: str = Field(description="Current scan status", enum=["pending", "running", "completed", "failed", "not_found"])
    message: str = Field(description="Status description")

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "scan_id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "completed",
                    "message": "Scan completed successfully"
                },
                {
                    "scan_id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "running",
                    "message": "Scan is still running"
                },
                {
                    "scan_id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "failed",
                    "message": "Microservice timeout"
                },
                {
                    "scan_id": "invalid-scan-id",
                    "status": "not_found",
                    "message": "Scan not found"
                }
            ]
        }


class SecretResult(BaseModel):
    """Individual secret detection result"""
    path: str = Field(description="File path where secret was found", example="/src/config.js")
    line: int = Field(description="Line number in the file", example=42)

    class Config:
        json_schema_extra = {
            "example": {
                "path": "/src/config.js",
                "line": 42
            }
        }


class ScanResultsResponse(BaseModel):
    """Response for scan results"""
    scan_id: str = Field(description="Scan identifier")
    status: str = Field(description="Scan status", enum=["completed", "not_found"])
    results: Optional[List[SecretResult]] = Field(None, description="List of detected secrets (only for completed scans)")

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "scan_id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "completed",
                    "results": [
                        {
                            "path": "/src/config.js",
                            "line": 42
                        },
                        {
                            "path": "/src/auth.py",
                            "line": 15
                        }
                    ]
                },
                {
                    "scan_id": "invalid-scan-id",
                    "status": "not_found"
                }
            ]
        }


class ErrorResponse(BaseModel):
    """Standard error response format"""
    success: bool = Field(False, description="Always false for error responses")
    message: str = Field(description="Error description")
    error_code: Optional[str] = Field(None, description="Optional error code for programmatic handling")

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "success": False,
                    "message": "Invalid or expired API token"
                },
                {
                    "success": False,
                    "message": "Rate limit exceeded: 60 requests per minute"
                },
                {
                    "success": False,
                    "message": "Insufficient permissions: scan required"
                }
            ]
        }


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