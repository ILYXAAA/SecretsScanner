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
    files_scanned = Column(Integer)  # New field for tracking scanned files
    excluded_files_count = Column(Integer)
    excluded_files_list = Column(String)
    error_message = Column(Text, default="No message")  # Add default value
    started_by = Column(String, nullable=True)

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