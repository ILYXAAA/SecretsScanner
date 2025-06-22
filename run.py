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

def setup_login_key():
    logging.info("Необходимо настроить LOGIN_KEY")
    while True:
        try:
            filename = "Auth/login.dat"
            message = input("Введите логин для учетной записи\n>")

            key = Fernet.generate_key().decode()
            fernet = Fernet(key.encode())
            encrypted = fernet.encrypt(message.encode())

            with open(filename, "wb") as file:
                file.write(encrypted)

            input("Нажмите Enter для подтверждения (Консоль будет очищена)")
            set_key(".env", "LOGIN_KEY", key)
            load_dotenv(override=True)
            os.system('cls' if os.name == 'nt' else 'clear')
            break
        except Exception as error:
            print(str(error))

def setup_password_key():
    logging.info("Необходимо настроить PASSWORD_KEY")
    while True:
        try:
            filename = "Auth/password.dat"
            message = input("Введите пароль для учетной записи\n>")

            key = Fernet.generate_key().decode()
            fernet = Fernet(key.encode())
            encrypted = fernet.encrypt(message.encode())

            with open(filename, "wb") as file:
                file.write(encrypted)

            input("Нажмите Enter для подтверждения (Консоль будет очищена)")
            set_key(".env", "PASSWORD_KEY", key)
            load_dotenv(override=True)
            os.system('cls' if os.name == 'nt' else 'clear')
            break
        except Exception as error:
            print(str(error))

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
    """Создает .env файл с базовыми настройками"""
    if not os.path.exists(".env"):
        with open('.env', 'w') as f:
            f.write("")
    
    set_key(".env", "DATABASE_URL", "sqlite:///./database/secrets_scanner.db")
    set_key(".env", "HUB_TYPE", "Azure")
    set_key(".env", "BACKUP_DIR", "./backups")
    set_key(".env", "BACKUP_RETENTION_DAYS", "7")
    set_key(".env", "BACKUP_INTERVAL_HOURS", "24")

    load_dotenv(override=True)

    logging.info(".env обновлен базовыми настройками")

def is_first_run():
    """Проверяет, является ли это первым запуском"""
    env_file = Path('.env')
    if not env_file.exists():
        return True
    
    # Проверяем содержимое .env файла
    load_dotenv()
    required_vars = ['HUB_TYPE', 'DATABASE_URL', 'BACKUP_DIR', 'BACKUP_RETENTION_DAYS', 
                     'BACKUP_INTERVAL_HOURS', 'LOGIN_KEY', 'PASSWORD_KEY', 'API_KEY', 
                     'APP_HOST', 'APP_PORT', 'MICROSERVICE_URL', 'SECRET_KEY']
    
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
    if not os.getenv("LOGIN_KEY") or os.getenv("LOGIN_KEY") == "***":
        setup_login_key()
    if not os.getenv("PASSWORD_KEY") or os.getenv("PASSWORD_KEY") == "***":
        setup_password_key()
    if not os.getenv("API_KEY") or os.getenv("API_KEY") == "***":
        setup_api_key()

    required_files = ["Auth/login.dat", "Auth/password.dat", "templates/dashboard.html", "templates/login.html",
                      "templates/multi_scan.html", "templates/project.html", "templates/scan_results.html", 
                      "templates/scan_status.html", "templates/settings.html", "utils/html_report_generator.py", "CredsManager.py", "main.py"]
    
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