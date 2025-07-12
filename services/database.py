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

# def create_indexes():
#     """Создание индексов для оптимизации производительности"""
#     try:
#         with engine.connect() as conn:
#             conn.execute(text("CREATE INDEX IF NOT EXISTS idx_secrets_composite ON secrets (path, line, secret, type)"))
#             conn.execute(text("CREATE INDEX IF NOT EXISTS idx_secrets_scan_exception ON secrets (scan_id, is_exception)"))
#             conn.execute(text("CREATE INDEX IF NOT EXISTS idx_secrets_severity ON secrets (scan_id, severity, is_exception)"))
#             conn.execute(text("CREATE INDEX IF NOT EXISTS idx_secrets_type ON secrets (scan_id, type, is_exception)"))
#             conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scans_project_time ON scans (project_name, completed_at)"))
#             conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scans_status ON scans (status, started_at)"))
            
#             conn.commit()
#             logger.info("Database indexes created successfully")
#     except Exception as e:
#         logger.error(f"Error creating indexes: {e}")

# def migrate_database():
#     """Add new columns for user tracking"""
#     try:
#         with engine.connect() as conn:
#             # Check if columns exist before adding them excluded_files_list
#             try:
#                 conn.execute(text("SELECT started_by FROM scans LIMIT 1"))
#             except:
#                 conn.execute(text("ALTER TABLE scans ADD COLUMN started_by TEXT"))
#                 logger.info("Added started_by column to scans table")
            
#             try:
#                 conn.execute(text("SELECT created_by FROM projects LIMIT 1"))
#             except:
#                 conn.execute(text("ALTER TABLE projects ADD COLUMN created_by TEXT"))
#                 logger.info("Added created_by column to projects table")
            
#             try:
#                 conn.execute(text("SELECT confirmed_by FROM secrets LIMIT 1"))
#             except:
#                 conn.execute(text("ALTER TABLE secrets ADD COLUMN confirmed_by TEXT"))
#                 logger.info("Added confirmed_by column to secrets table")
            
#             try:
#                 conn.execute(text("SELECT refuted_by FROM secrets LIMIT 1"))
#             except:
#                 conn.execute(text("ALTER TABLE secrets ADD COLUMN refuted_by TEXT"))
#                 logger.info("Added refuted_by column to secrets table")
            
#             # Add multi_scans table
#             try:
#                 conn.execute(text("SELECT id FROM multi_scans LIMIT 1"))
#             except:
#                 conn.execute(text("""
#                     CREATE TABLE multi_scans (
#                         id TEXT PRIMARY KEY,
#                         user_id TEXT NOT NULL,
#                         scan_ids TEXT NOT NULL,
#                         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#                         name TEXT
#                     )
#                 """))
#                 conn.execute(text("CREATE INDEX IF NOT EXISTS idx_multi_scans_user ON multi_scans (user_id)"))
#                 logger.info("Created multi_scans table")
            
#             try:
#                 conn.execute(text("SELECT confidence FROM secrets LIMIT 1"))
#             except:
#                 conn.execute(text("ALTER TABLE secrets ADD COLUMN confidence REAL DEFAULT 1.0"))
#                 conn.execute(text("UPDATE secrets SET confidence = 1.0 WHERE confidence IS NULL"))
#                 logger.info("Added confidence column to secrets table")

#             conn.commit()
#             logger.info("Database migration completed successfully")
#     except Exception as e:
#         logger.error(f"Error during database migration: {e}")

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