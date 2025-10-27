from sqlalchemy import Column, String, DateTime, Integer, Text, Boolean, Float
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

# Main database models
Base = declarative_base()

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    repo_url = Column(String)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(String, nullable=True)

class Scan(Base):
    __tablename__ = "scans"
    id = Column(String, primary_key=True, index=True)
    project_name = Column(String, index=True)
    repo_commit = Column(String)
    ref_type = Column(String)
    ref = Column(String)
    status = Column(String, default="running")  # running, completed, failed
    started_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime)
    files_scanned = Column(Integer)
    excluded_files_count = Column(Integer)
    excluded_files_list = Column(String)
    error_message = Column(Text, default="No message")
    started_by = Column(String, nullable=True)
    detected_languages = Column(Text, default="{}")
    detected_frameworks = Column(Text, default="{}")
    high_secrets_count = Column(Integer, default=0)
    potential_secrets_count = Column(Integer, default=0)

class Secret(Base):
    __tablename__ = "secrets"
    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(String, index=True)
    path = Column(String)
    line = Column(Integer)
    secret = Column(String)
    context = Column(Text)
    severity = Column(String)
    type = Column(String)
    confidence = Column(Float, default=1.0)
    status = Column(String, default="No status")  # No status, Confirmed, Refuted
    is_exception = Column(Boolean, default=False)
    exception_comment = Column(Text)
    refuted_at = Column(DateTime)  # Field for tracking when secret was refuted
    confirmed_by = Column(String, nullable=True)
    refuted_by = Column(String, nullable=True)

class MultiScan(Base):
    __tablename__ = "multi_scans"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True)
    scan_ids = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    name = Column(String)

# API Token models
class ApiToken(Base):
    __tablename__ = "api_tokens"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)  # Team/client name
    token_hash = Column(String, unique=True, nullable=False, index=True)  # SHA256 hash of token
    prefix = Column(String, nullable=False)  # First 8 chars for identification (ss_live_)
    created_by = Column(String, nullable=False)  # Admin who created the token
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)  # None = never expires
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Rate limits
    requests_per_minute = Column(Integer, default=60)
    requests_per_hour = Column(Integer, default=1000) 
    requests_per_day = Column(Integer, default=10000)
    
    # Permissions as JSON string
    permissions = Column(Text, default='{}')  # {"project_add": true, "scan": true, etc}

class ApiUsage(Base):
    __tablename__ = "api_usage"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    token_id = Column(Integer, nullable=False, index=True)
    endpoint = Column(String, nullable=False)  # e.g., "POST /api/v1/scan"
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    response_status = Column(Integer)  # HTTP status code
    response_time_ms = Column(Integer)  # Response time in milliseconds
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

# Separate Base for users (different database)
UserBase = declarative_base()

class User(UserBase):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# Custom exceptions
class AuthenticationException(Exception):
    pass