from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timezone
import logging

from config import DATABASE_URL
from models import Base

logger = logging.getLogger("main")

# Database setup
SQLALCHEMY_DATABASE_URL = DATABASE_URL
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Database dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def sanitize_string(value):
    """Удаляет NUL-символы и др из строки для совместимости с PostgreSQL"""
    if isinstance(value, str):
        return value.replace('\x00', '').replace('\x01', '').replace('\x02', '').replace('\x03', '').replace('\x04', '').replace('\x05', '').replace('\x06', '').replace('\x07', '').replace('\x08', '')
    return value

def initialize_database():
    """Initialize database with tables and run migrations"""
    # Создаем базовые таблицы
    Base.metadata.create_all(bind=engine)
    
    # Инициализируем и запускаем миграции
    from services.migrations import initialize_migrations, run_migrations
    initialize_migrations(DATABASE_URL)
    run_migrations()
    
    logger.info("Database initialized successfully")