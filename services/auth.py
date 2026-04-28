from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import logging

from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, USERS_DATABASE_URL, get_full_url
from models import UserBase, User, AuthenticationException

logger = logging.getLogger("main")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

USER_ROLE = "user"
ADMIN_ROLE = "admin"
VALID_ROLES = {USER_ROLE, ADMIN_ROLE}

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def ensure_user_database():
    auth_dir = Path("Auth")
    auth_dir.mkdir(exist_ok=True)
    
    user_engine = create_engine(USERS_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in USERS_DATABASE_URL else {})
    UserBase.metadata.create_all(bind=user_engine)
    ensure_user_schema(user_engine)
    logger.info("User database initialized")

def ensure_user_schema(user_engine):
    """Ensure existing user databases have role support."""
    inspector = inspect(user_engine)
    columns = {column["name"] for column in inspector.get_columns("users")}

    with user_engine.begin() as conn:
        if "role" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'user' NOT NULL"))

        conn.execute(text("UPDATE users SET role = 'user' WHERE role IS NULL OR role = ''"))
        conn.execute(text("UPDATE users SET role = 'admin' WHERE username = 'admin'"))

def get_user_db():
    auth_dir = Path("Auth")
    auth_dir.mkdir(exist_ok=True)
    
    user_engine = create_engine(USERS_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in USERS_DATABASE_URL else {})
    
    UserBase.metadata.create_all(bind=user_engine)
    ensure_user_schema(user_engine)
    
    UserSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=user_engine)
    db = UserSessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except JWTError:
        return None

def verify_credentials(username: str, password: str, user_db: Session):
    user = user_db.query(User).filter(User.username == username).first()
    if user and verify_password(password, user.password_hash):
        return True
    return False

async def get_current_user(request: Request):
    token = request.cookies.get("auth_token")
    if not token:
        raise AuthenticationException()
    
    username = verify_token(token)
    if not username:
        raise AuthenticationException()
    
    # Check if user exists in database
    auth_dir = Path("Auth")
    auth_dir.mkdir(exist_ok=True)
    
    user_engine = create_engine(USERS_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in USERS_DATABASE_URL else {})
    UserBase.metadata.create_all(bind=user_engine)
    ensure_user_schema(user_engine)
    UserSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=user_engine)
    user_db = UserSessionLocal()
    
    try:
        user = user_db.query(User).filter(User.username == username).first()
        if not user:
            raise AuthenticationException()
    finally:
        user_db.close()
    
    return username

def get_user_role(username: str) -> str:
    """Get user role from auth database."""
    if not username:
        return USER_ROLE

    auth_dir = Path("Auth")
    auth_dir.mkdir(exist_ok=True)

    user_engine = create_engine(USERS_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in USERS_DATABASE_URL else {})
    UserBase.metadata.create_all(bind=user_engine)
    ensure_user_schema(user_engine)

    UserSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=user_engine)
    user_db = UserSessionLocal()

    try:
        user = user_db.query(User).filter(User.username == username).first()
        if not user:
            return USER_ROLE
        if user.username == "admin" and user.role != ADMIN_ROLE:
            user.role = ADMIN_ROLE
            user_db.commit()
        return user.role if user.role in VALID_ROLES else USER_ROLE
    finally:
        user_db.close()

def is_admin(username: str) -> bool:
    """Check if user has admin role."""
    return get_user_role(username) == ADMIN_ROLE

async def get_admin_user(request: Request):
    """Dependency to check if current user is admin"""
    current_user = await get_current_user(request)
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Access denied")
    return current_user

# Exception handler
async def auth_exception_handler(request: Request, exc: AuthenticationException):
    response = RedirectResponse(url=get_full_url(""), status_code=302)
    response.delete_cookie(key="auth_token")  # Удаляем невалидный токен
    return response