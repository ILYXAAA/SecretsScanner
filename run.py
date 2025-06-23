import uvicorn
import os
import sys
import signal
import multiprocessing
import logging
from pathlib import Path
import ipaddress
from cryptography.fernet import Fernet
import secrets
from dotenv import load_dotenv, set_key
os.system("") # Для цветной консоли

# Configure colored logging
class ColoredFormatter(logging.Formatter):
    """Colored log formatter"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }
    
    def format(self, record):
        # Создаем копию записи, чтобы не изменять оригинал
        colored_record = logging.makeLogRecord(record.__dict__)
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        colored_record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(colored_record)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Удаляем существующие обработчики
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Консольный обработчик с цветами
    console_handler = logging.StreamHandler()
    formatter = ColoredFormatter(fmt='[%(levelname)s] %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Файловый обработчик БЕЗ цветов
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        'secrets_scanner.log', 
        maxBytes=10*1024*1024, 
        backupCount=5,
        encoding='utf-8'
    )
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger

def setup_multiprocessing():
    """Configure multiprocessing for Windows/Linux compatibility"""
    if sys.platform.startswith('win'):
        multiprocessing.set_start_method('spawn', force=True)
    else:
        try:
            multiprocessing.set_start_method('fork', force=True)
        except RuntimeError:
            pass

def setup_host():
    logging.info("Необходимо настроить APP_HOST")
    while True:
        host = input("Введите APP_HOST в (формате 127.0.0.1)\n>")
        try:
            ipaddress.ip_address(host) # Вызовет ValueError если хост некорректный
            set_key(".env", "APP_HOST", host)
            load_dotenv(override=True)
            break
        except ValueError as error:
            print(str(error))
        
def setup_port():
    logging.info("Необходимо настроить APP_PORT")
    while True:
        port = input("Введите APP_PORT (в формате 8000)\n>")
        if port.isdigit() and 1 <= int(port) <= 65535:
            set_key(".env", "APP_PORT", port)
            load_dotenv(override=True)
            break

def setup_microservice_url():
    from urllib.parse import urlparse
    import ipaddress
    logging.info("Необходимо настроить MICROSERVICE_URL")
    while True:
        url = input("Введите MICROSERVICE_URL (в формате http://127.0.0.1:8001)\n>").strip()
        try:
            p = urlparse(url)
            assert p.scheme in ("http", "https")
            assert ipaddress.ip_address(p.hostname)
            assert p.port and 1 <= p.port <= 65535
        except:
            logging.error("Невалидный MICROSERVICE_URL")
        else:
            set_key(".env", "MICROSERVICE_URL", url)
            load_dotenv(override=True)
            break

def setup_secret_key():
    logging.info("Необходимо настроить SECRET_KEY (используется для сессий)")
    answer = input("Хотите сгенерировать токен автоматически? (Y/N)\n>")
    if answer.lower() in ["y", "ye", "yes"]:
        apiKey = secrets.token_urlsafe(32)
        print(f"Сгенерирован SECRET_KEY. Скопируйте его и используйте для сессий")
        print(f"> {apiKey}")
        input("Нажмите Enter для подтверждения (Консоль будет очищена)")
        set_key(".env", "SECRET_KEY", apiKey)
        load_dotenv(override=True)
        os.system('cls' if os.name == 'nt' else 'clear')
    else:
        print("Введите SECRET_KEY")
        apiKey = input(">")
        input("Нажмите Enter для подтверждения (Консоль будет очищена)")
        set_key(".env", "SECRET_KEY", apiKey)
        load_dotenv(override=True)
        os.system('cls' if os.name == 'nt' else 'clear')

def setup_api_key():
    logging.info("Необходимо настроить API_KEY (используется для доступа к микросервису)")
    print("Введите API_TOKEN")
    apiKey = input(">")
    input("Нажмите Enter для подтверждения (Консоль будет очищена)")
    set_key(".env", "API_KEY", apiKey)
    load_dotenv(override=True)
    os.system('cls' if os.name == 'nt' else 'clear')

def create_default_env_file():
    """Создает .env файл с базовыми настройками, если переменные ещё не заданы"""
    if not os.path.exists(".env"):
        with open('.env', 'w'):
            pass  # просто создаём пустой файл

    load_dotenv()  # загружаем переменные перед проверками

    defaults = {
        "DATABASE_URL": "sqlite:///./database/secrets_scanner.db",
        "USERS_DATABASE_URL": "sqlite:///./Auth/users.db",
        "HUB_TYPE": "Azure",
        "BACKUP_DIR": "./backups",
        "BACKUP_RETENTION_DAYS": "7",
        "BACKUP_INTERVAL_HOURS": "24"
    }

    for key, value in defaults.items():
        if not os.getenv(key):
            set_key(".env", key, value)

    logging.info(".env дополнен базовыми настройками")

def check_and_setup_user_database():
    """Setup user database and create first user if needed"""
    from pathlib import Path
    from getpass import getpass
    from sqlalchemy import create_engine, Column, String, DateTime, Integer
    from sqlalchemy.orm import declarative_base
    from sqlalchemy.orm import sessionmaker
    from passlib.context import CryptContext
    from datetime import datetime, timezone
    import os

    # Setup
    Path("Auth").mkdir(exist_ok=True)
    USERS_DATABASE_URL = os.getenv("USERS_DATABASE_URL", "sqlite:///./Auth/users.db")

    UserBase = declarative_base()
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    class User(UserBase):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True, index=True)
        username = Column(String, unique=True, index=True, nullable=False)
        password_hash = Column(String, nullable=False)
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Create DB and check users
    engine = create_engine(USERS_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in USERS_DATABASE_URL else {})
    UserBase.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            logging.warning("В БД users.db не найдено ни одного пользователя. Необходимо создать пользователя-администратора.")
            logging.warning("Дальнейшее управление пользователями будет доступно в UsersManager.py, либо в панели Администратора на сайте")
            
            while True:
                username = "admin"
                print(f"Имя пользователя: {username}")
                answer = input("Хотите сгенерироваать пароль автоматически? (Y/N)")
                if answer.lower() in ["y", "yes"]:
                    password = secrets.token_urlsafe(32)
                    print(f"Пароль сгенерирован:\n    {password}\nПожалуйста сохраните его. После продолжения консоль будет очищена.")
                    input("Нажмите Enter для продолжения..")
                    os.system('cls' if os.name == 'nt' else 'clear')
                else:
                    password = getpass("Введите пароль для администратора: ").strip()
                    password2 = getpass("Введите еще раз, для для подтверждения: ").strip()
                    if password != password2:
                        logging.warning("Пароли не совпадают! Повторите ввод.")
                        continue
                # Простейшая валидация пароля
                if len(password) < 8:
                    logging.warning("Пароль должен быть не менее 8 символов. Повторите ввод.")
                    continue
                if username == "":
                    logging.warning("Имя пользователя не может быть пустым.")
                    continue

                try:
                    hashed_password = pwd_context.hash(password)
                    user = User(username=username, password_hash=hashed_password)
                    db.add(user)
                    db.commit()
                    logging.info(f"Пользователь '{username}' успешно создан.")
                    break  # выходим из цикла после успешной регистрации
                except Exception as e:
                    db.rollback()
                    logging.error(f"Ошибка при создании пользователя: {e}")
    finally:
        db.close()
    logging.info("Проведена валидация БД users.db")

def is_first_run():
    """Проверяет, является ли это первым запуском"""
    env_file = Path('.env')
    if not env_file.exists():
        return True
    
    # Проверяем содержимое .env файла
    load_dotenv()
    required_vars = ['HUB_TYPE', 'DATABASE_URL', 'BACKUP_DIR', 'BACKUP_RETENTION_DAYS', 
                     'BACKUP_INTERVAL_HOURS', 'LOGIN_KEY', 'PASSWORD_KEY', 'API_KEY', 
                     'APP_HOST', 'APP_PORT', 'MICROSERVICE_URL', 'SECRET_KEY', 'USERS_DATABASE_URL']
    
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            return True
    
    return False

def validate_environment():
    logging.info("Валидация настроек окружения...")
    if is_first_run():
        logging.info("Обнаружен первый запуск. Настройка окружения...")
        create_default_env_file()
    
    if not os.getenv("APP_HOST"):
        setup_host()
    if not os.getenv("APP_PORT"):
        setup_port()
    if not os.getenv("MICROSERVICE_URL"):
        setup_microservice_url()
    if not os.getenv("SECRET_KEY") or os.getenv("SECRET_KEY") == "***":
        setup_secret_key()
    if not os.getenv("API_KEY") or os.getenv("API_KEY") == "***":
        setup_api_key()

    check_and_setup_user_database()

    required_files = ["templates/dashboard.html", "templates/login.html", "templates/admin.html", "UsersManager.py",
                      "templates/multi_scan.html", "templates/project.html", "templates/scan_results.html", 
                      "templates/scan_status.html", "templates/settings.html", "utils/html_report_generator.py", "main.py"]
    
    validation_result = True
    for file in required_files:
        if not os.path.exists(file):
            logging.error(f"Required файл не найден: {file}")
            validation_result = False

    return validation_result

def check_dependencies():
    """Check if required Python packages are installed"""
    try:
        import uvicorn
        logging.info("uvicorn is installed")
    except ImportError:
        logging.error("uvicorn is not installed")
        return False
    
    try:
        import fastapi
        logging.info("fastapi is installed")
    except ImportError:
        logging.error("fastapi is not installed")
        return False
    
    return True

def main():
    """Main startup function"""
    setup_logging()
    
    print("Secret Scanner Startup")
    print("=" * 40)
    
    try:
        # Check dependencies
        print("\nChecking Python dependencies...")
        if not check_dependencies():
            logging.error("Required dependencies not installed")
            logging.info("Please run: pip install -r requirements.txt")
            sys.exit(1)
        
        if not validate_environment():
            print("Произошла ошибка валидации переменных окружения. Завершение программы")
            sys.exit(1)
        logging.info("Валидация переменных окружения прошла успешно")
        
        from main import app
        
        print("Starting SecretsScanner server...")
        host = os.getenv("APP_HOST")
        port = int(os.getenv("APP_PORT"))
        uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)
        
    except KeyboardInterrupt:
        print("\nReceived interrupt signal")
    except ImportError as e:
        logging.error(f"Import error: {e}")
        logging.info("Please run: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Critical startup error: {e}")
        sys.exit(1)
    finally:
        print("Service stopped")

if __name__ == "__main__":
    main()