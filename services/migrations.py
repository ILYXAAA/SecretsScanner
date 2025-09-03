import os
import importlib.util
import logging
from pathlib import Path
from typing import List, Dict, Any
from sqlalchemy import create_engine, text, MetaData, Table, Column, String, DateTime, Integer, inspect
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone
import json

logger = logging.getLogger("migrations")

class MigrationSystem:
    def __init__(self, database_url: str, migrations_dir: str = "migrations"):
        self.database_url = database_url
        self.migrations_dir = Path(migrations_dir)
        self.engine = create_engine(database_url, connect_args={"check_same_thread": False} if "sqlite" in database_url else {})
        
        # Создаем папку миграций если её нет
        self.migrations_dir.mkdir(exist_ok=True)
        
        # Инициализируем таблицу версий миграций
        self._init_migrations_table()
    
    def _init_migrations_table(self):
        """Создает таблицу для отслеживания применённых миграций"""
        try:
            with self.engine.connect() as conn:
                # Проверяем существует ли таблица
                inspector = inspect(self.engine)
                if 'schema_migrations' not in inspector.get_table_names():
                    conn.execute(text("""
                        CREATE TABLE schema_migrations (
                            version VARCHAR(255) PRIMARY KEY,
                            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            description VARCHAR(500)
                        )
                    """))
                    conn.commit()
                    logger.info("Created schema_migrations table")
        except Exception as e:
            logger.critical(f"Error creating migrations table: {e}")
            raise
    
    def _get_applied_migrations(self) -> List[str]:
        """Получает список применённых миграций"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
                return [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.critical(f"Error getting applied migrations: {e}")
            return []
    
    def _get_available_migrations(self) -> List[Dict[str, Any]]:
        """Получает список доступных файлов миграций"""
        migrations = []
        
        for file_path in sorted(self.migrations_dir.glob("*.py")):
            if file_path.name.startswith("__"):
                continue
                
            # Парсим имя файла: 001_description.py
            parts = file_path.stem.split("_", 1)
            if len(parts) >= 2 and parts[0].isdigit():
                version = parts[0].zfill(3)  # Приводим к формату 001, 002, etc
                description = parts[1].replace("_", " ").title()
                
                migrations.append({
                    "version": version,
                    "description": description,
                    "file_path": file_path,
                    "module_name": file_path.stem
                })
        
        return migrations
    
    def _load_migration_module(self, file_path: Path):
        """Загружает модуль миграции"""
        try:
            spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            logger.critical(f"Error loading migration {file_path}: {e}")
            raise
    
    def _mark_migration_applied(self, version: str, description: str):
        """Помечает миграцию как применённую"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO schema_migrations (version, description, applied_at) VALUES (:version, :description, :applied_at)"
                ), {
                    "version": version,
                    "description": description,
                    "applied_at": datetime.now(timezone.utc)
                })
                conn.commit()
        except Exception as e:
            logger.error(f"Error marking migration '{version}' as applied: {e}")
            raise
    
    def _unmark_migration_applied(self, version: str):
        """Убирает отметку о применении миграции"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("DELETE FROM schema_migrations WHERE version = :version"), {"version": version})
                conn.commit()
        except Exception as e:
            logger.error(f"Error unmarking migration '{version}': {e}")
            raise
    
    def column_exists(self, table_name: str, column_name: str) -> bool:
        """Проверяет существование колонки в таблице"""
        try:
            inspector = inspect(self.engine)
            columns = [col['name'] for col in inspector.get_columns(table_name)]
            return column_name in columns
        except Exception:
            return False
    
    def table_exists(self, table_name: str) -> bool:
        """Проверяет существование таблицы"""
        try:
            inspector = inspect(self.engine)
            return table_name in inspector.get_table_names()
        except Exception:
            return False
    
    def index_exists(self, index_name: str) -> bool:
        """Проверяет существование индекса"""
        try:
            with self.engine.connect() as conn:
                if "postgresql" in self.database_url:
                    result = conn.execute(text(
                        "SELECT COUNT(*) FROM pg_indexes WHERE indexname = :index_name"
                    ), {"index_name": index_name})
                elif "sqlite" in self.database_url:
                    result = conn.execute(text(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name = :index_name"
                    ), {"index_name": index_name})
                else:
                    # MySQL
                    result = conn.execute(text(
                        "SELECT COUNT(*) FROM information_schema.statistics WHERE index_name = :index_name"
                    ), {"index_name": index_name})
                
                return result.scalar() > 0
        except Exception:
            return False
    
    def safe_add_column(self, table_name: str, column_definition: str):
        """Безопасно добавляет колонку если её нет"""
        column_name = column_definition.split()[0]
        if not self.column_exists(table_name, column_name):
            with self.engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}"))
                conn.commit()
                logger.info(f"Added column '{column_name}' to '{table_name}'")
        else:
            logger.info(f"Column '{column_name}' already exists in '{table_name}'")
    
    def safe_create_table(self, table_sql: str, table_name: str):
        """Безопасно создаёт таблицу если её нет"""
        if not self.table_exists(table_name):
            with self.engine.connect() as conn:
                conn.execute(text(table_sql))
                conn.commit()
                logger.info(f"Created table '{table_name}'")
        else:
            logger.info(f"Table '{table_name}' already exists")
    
    def safe_drop_table(self, table_name: str):
        """Безопасно удаляет таблицу если она существует"""
        if self.table_exists(table_name):
            with self.engine.connect() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
                conn.commit()
                logger.warning(f"Dropped table '{table_name}'")
        else:
            logger.info(f"Table '{table_name}' does not exist")
    
    def safe_drop_column(self, table_name: str, column_name: str):
        """Безопасно удаляет колонку (с учётом ограничений SQLite)"""
        if "sqlite" in self.database_url:
            logger.warning(f"SQLite does not support DROP COLUMN for '{table_name}.{column_name}', skipping")
            return
        
        if self.column_exists(table_name, column_name):
            with self.engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}"))
                conn.commit()
                logger.info(f"Dropped column '{column_name}' from '{table_name}'")
        else:
            logger.info(f"Column '{column_name}' does not exist in '{table_name}'")
    
    def execute_sql(self, sql: str, description: str = "SQL operation"):
        """Выполняет произвольный SQL с логированием"""
        with self.engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
            logger.info(f"Executed: '{description}'")
    
    def safe_create_index(self, index_sql: str, index_name: str):
        """Безопасно создаёт индекс если его нет"""
        if not self.index_exists(index_name):
            with self.engine.connect() as conn:
                conn.execute(text(index_sql))
                conn.commit()
                logger.info(f"Created index '{index_name}'")
        else:
            logger.info(f"Index '{index_name}' already exists")
    
    def migrate(self, target_version: str = None):
        """Применяет миграции до указанной версии (или все доступные)"""
        applied_migrations = set(self._get_applied_migrations())
        available_migrations = self._get_available_migrations()
        
        logger.info(f"Applied migrations: {json.dumps(sorted(applied_migrations))}")
        logger.info(f"Available migrations: {json.dumps([m['version'] for m in available_migrations])}")
        
        # Фильтруем миграции для применения
        migrations_to_apply = []
        for migration in available_migrations:
            if migration["version"] not in applied_migrations:
                if target_version is None or migration["version"] <= target_version:
                    migrations_to_apply.append(migration)
        
        if not migrations_to_apply:
            logger.info("No migrations to apply")
            return
        
        logger.info(f"Applying {len(migrations_to_apply)} migrations...")
        
        for migration in migrations_to_apply:
            try:
                logger.info(f"Applying migration '{migration['version']}': {migration['description']}")
                
                # Загружаем модуль миграции
                module = self._load_migration_module(migration["file_path"])
                
                # Проверяем наличие функции upgrade
                if not hasattr(module, 'upgrade'):
                    raise Exception(f"Migration {migration['version']} missing upgrade() function")
                
                # Применяем миграцию
                module.upgrade(self)
                
                # Помечаем как применённую
                self._mark_migration_applied(migration["version"], migration["description"])
                
                logger.info(f"Successfully applied migration '{migration['version']}'")
                
            except Exception as e:
                logger.critical(f"Failed to apply migration '{migration['version']}': {e}")
                raise
    
    def rollback(self, target_version: str):
        """Откатывает миграции до указанной версии"""
        applied_migrations = sorted(self._get_applied_migrations(), reverse=True)
        available_migrations = {m["version"]: m for m in self._get_available_migrations()}
        
        migrations_to_rollback = []
        for version in applied_migrations:
            if version > target_version:
                if version in available_migrations:
                    migrations_to_rollback.append(available_migrations[version])
                else:
                    logger.warning(f"Migration file for version '{version}' not found, skipping rollback")
        
        if not migrations_to_rollback:
            logger.info("No migrations to rollback")
            return
        
        logger.info(f"Rolling back {len(migrations_to_rollback)} migrations...")
        
        for migration in migrations_to_rollback:
            try:
                logger.info(f"Rolling back migration '{migration['version']}': {migration['description']}")
                
                # Загружаем модуль миграции
                module = self._load_migration_module(migration["file_path"])
                
                # Проверяем наличие функции downgrade
                if not hasattr(module, 'downgrade'):
                    logger.warning(f"Migration '{migration['version']}' missing downgrade() function, skipping")
                    continue
                
                # Откатываем миграцию
                module.downgrade(self)
                
                # Убираем отметку о применении
                self._unmark_migration_applied(migration["version"])
                
                logger.info(f"Successfully rolled back migration '{migration['version']}'")
                
            except Exception as e:
                logger.critical(f"Failed to rollback migration '{migration['version']}': {e}")
                raise
    
    def status(self):
        """Показывает статус миграций"""
        applied_migrations = set(self._get_applied_migrations())
        available_migrations = self._get_available_migrations()
        
        print("\nMigration Status:")
        print("=" * 50)
        
        for migration in available_migrations:
            status = "✅ Applied" if migration["version"] in applied_migrations else "❌ Pending"
            print(f"{migration['version']}: {migration['description']} - {status}")
        
        pending_count = len([m for m in available_migrations if m["version"] not in applied_migrations])
        print(f"\nTotal: {len(available_migrations)} migrations, {pending_count} pending")

# Глобальный экземпляр для использования в приложении
migration_system = None

def initialize_migrations(database_url: str):
    """Инициализирует систему миграций"""
    global migration_system
    migration_system = MigrationSystem(database_url)
    return migration_system

def run_migrations():
    """Запускает все ожидающие миграции"""
    if migration_system:
        migration_system.migrate()
    else:
        logger.critical("Migration system not initialized")