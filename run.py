#!/usr/bin/env python3
"""
Startup script for Secrets Scanner
"""

import os
import sys
import logging
import secrets
from pathlib import Path
from dotenv import load_dotenv

os.system("") # Для цветной консоли

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
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)

def setup_logging():
    """Setup colored logging"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    console_handler = logging.StreamHandler()
    formatter = ColoredFormatter(fmt='[%(levelname)s] %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

def create_env_file():
    """Create .env file from template and configure settings"""
    example_file = Path('.env.example')
    if not example_file.exists():
        logging.error(".env.example file not found")
        return False
    
    # Read template
    with open(example_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("\nFirst-time setup: Configure server settings")
    print("-" * 40)
    
    # Get MICROSERVICE_URL
    while True:
        microservice_url = input("Enter microservice URL (default: http://127.0.0.1:8001): ").strip()
        if not microservice_url:
            microservice_url = "http://127.0.0.1:8001"
        if microservice_url.startswith("http://") or microservice_url.startswith("https://"):
            break
        print("URL must start with http:// or https://")
    
    # Get HOST
    host = input("Enter server host (default: 127.0.0.1): ").strip()
    if not host:
        host = "127.0.0.1"
    
    # Get PORT
    while True:
        port_input = input("Enter server port (default: 8000): ").strip()
        if not port_input:
            port = "8000"
            break
        try:
            port_num = int(port_input)
            if 1024 <= port_num <= 65535:
                port = port_input
                break
            print("Port must be between 1024 and 65535")
        except ValueError:
            print("Invalid port number")
    
    # Generate SECRET_KEY
    secret_key = secrets.token_urlsafe(32)
    logging.info("Generated SECRET_KEY automatically")
    
    # Update content
    content = content.replace("MICROSERVICE_URL=http://127.0.0.1:8001", f"MICROSERVICE_URL={microservice_url}")
    content = content.replace("APP_HOST=127.0.0.1", f"APP_HOST={host}")
    content = content.replace("APP_PORT=8000", f"APP_PORT={port}")
    content = content.replace("SECRET_KEY=***", f"SECRET_KEY={secret_key}")
    
    # Write .env file
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(content)
    
    logging.info("Configuration saved to .env")
    
    # Run first_setup from CredsManager
    try:
        from CredsManager import first_setup
        logging.info("Running authentication setup...")
        if first_setup():
            logging.info("Authentication setup completed")
            # Reload .env to get updated keys
            load_dotenv(override=True)
            return True
        else:
            logging.error("Authentication setup failed")
            return False
    except ImportError:
        logging.error("Could not import first_setup from CredsManager.py")
        logging.info("Please run: python CredsManager.py manually")
        return False
    except Exception as e:
        logging.error(f"Error during authentication setup: {e}")
        return False

def check_files():
    """Check if required files exist"""
    required_files = {
        'main.py': 'Main FastAPI application',
        'requirements.txt': 'Python dependencies',
        'CredsManager.py': 'Credentials manager script'
    }
    
    missing_files = []
    for file, description in required_files.items():
        if not Path(file).exists():
            missing_files.append(f"{file} ({description})")
        else:
            logging.info(f"{file} found")
    
    if missing_files:
        logging.error("Missing required files:")
        for file in missing_files:
            logging.error(f"  - {file}")
        return False
    
    return True

def check_directories():
    """Check and create required directories"""
    required_dirs = ['database', 'backups', 'Auth', 'templates', 'utils']
    
    for dir_name in required_dirs:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            logging.info(f"Creating directory: {dir_name}")
            dir_path.mkdir(parents=True, exist_ok=True)
        else:
            logging.info(f"Directory '{dir_name}' found")

def check_env_config():
    """Check environment configuration"""
    env_file = Path('.env')
    if env_file.exists():
        load_dotenv()
        logging.info(".env configuration file found and loaded")
    else:
        logging.warning(".env file not found. Creating from template...")
        if not create_env_file():
            return False
        load_dotenv()
    
    # Check required variables
    required_vars = ["SECRET_KEY", "LOGIN_KEY", "PASSWORD_KEY"]
    missing_vars = []
    
    for var in required_vars:
        value = os.getenv(var)
        if not value or value == "***":
            missing_vars.append(var)
        else:
            logging.info(f"{var} is configured")
    
    if missing_vars:
        logging.error(f"Missing required variables: {missing_vars}")
        logging.info("Run: python CredsManager.py")
        return False
    
    # Set defaults for optional variables
    defaults = {
        "DATABASE_URL": "sqlite:///./database/secrets_scanner.db",
        "HUB_TYPE": "Azure",
        "BACKUP_DIR": "./backups",
        "BACKUP_RETENTION_DAYS": "7",
        "BACKUP_INTERVAL_HOURS": "24"
    }
    
    for var, default in defaults.items():
        if not os.getenv(var):
            os.environ[var] = default
            logging.info(f"{var} set to default: {default}")
    
    return True

def check_credentials():
    """Check credentials files"""
    creds_files = ["Auth/login.dat", "Auth/password.dat"]
    
    for creds_file in creds_files:
        if not Path(creds_file).exists():
            logging.error(f"Credentials file '{creds_file}' not found")
            logging.info("Run: python CredsManager.py")
            return False
        else:
            logging.info(f"Credentials file '{creds_file}' found")
    
    return True

def check_dependencies():
    """Check if required Python packages are installed"""
    try:
        import uvicorn, fastapi
        logging.info("Required packages installed")
        return True
    except ImportError:
        logging.error("Missing packages")
        return False

def display_startup_info():
    """Display startup information"""
    app_host = os.getenv('APP_HOST', '127.0.0.1')
    app_port = os.getenv('APP_PORT', '8000')
    hub_type = os.getenv('HUB_TYPE', 'Azure')
    microservice_url = os.getenv('MICROSERVICE_URL', 'http://127.0.0.1:8001')
    
    print(f"\nStarting Secrets Scanner...")
    print(f"Application URL: http://{app_host}:{app_port}")
    print(f"Microservice URL: {microservice_url}")
    print(f"Repository hub type: {hub_type}")
    print(f"Database: {os.getenv('DATABASE_URL', 'sqlite:///./database/secrets_scanner.db')}")

def main():
    logger = setup_logging()
    
    print("Secrets Scanner Startup Check")
    print("=" * 50)
    
    # Check files
    print("\nChecking required files...")
    if not check_files():
        logging.error("Missing required files")
        sys.exit(1)
    
    # Check directories
    print("\nChecking directories...")
    check_directories()
    
    # Check dependencies
    print("\nChecking Python dependencies...")
    if not check_dependencies():
        logging.error("Required dependencies not installed")
        logging.info("Run: pip install -r requirements.txt")
        sys.exit(1)
    
    # Check environment
    print("\nChecking environment configuration...")
    if not check_env_config():
        logging.error("Environment configuration incomplete")
        sys.exit(1)
    
    # Check credentials
    print("\nChecking authentication credentials...")
    if not check_credentials():
        logging.error("Authentication credentials not configured")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    logging.info("All startup checks passed!")
    
    display_startup_info()
    print("\n" + "=" * 50)
    
    # Start application
    try:
        app_host = os.getenv('APP_HOST', '127.0.0.1')
        app_port = int(os.getenv('APP_PORT', '8000'))
        
        import uvicorn
        from main import app
        
        print("Starting application server...")
        uvicorn.run(app, host=app_host, port=app_port, log_level="info", access_log=True)
        
    except ImportError as e:
        logging.error(f"Import error: {e}")
        logging.info("Run: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error starting application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()