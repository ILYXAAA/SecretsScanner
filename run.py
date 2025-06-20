#!/usr/bin/env python3
"""
Startup script for Secrets Scanner
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure colored logging
class ColoredFormatter(logging.Formatter):
    """Colored log formatter"""
    
    # Color codes
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
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler with colored formatter
    console_handler = logging.StreamHandler()
    formatter = ColoredFormatter(
        fmt='[%(levelname)s] %(message)s'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

def check_files():
    """Check if required files exist"""
    required_files = {
        'main.py': 'Main FastAPI application',
        'requirements.txt': 'Python dependencies',
        'CredsManager.py': 'Credentials manager script'
    }
    
    optional_files = {
        '.env': 'Environment settings file (will use defaults if missing)',
        'README.md': 'Documentation file'
    }
    
    missing_files = []
    for file, description in required_files.items():
        if not Path(file).exists():
            missing_files.append(f"{file} ({description})")
        else:
            logging.info(f"{file} found")
    
    # Check optional files
    for file, description in optional_files.items():
        if Path(file).exists():
            logging.info(f"{file} found")
        else:
            logging.warning(f"{file} not found - {description}")
    
    if missing_files:
        logging.error("Missing required files:")
        for file in missing_files:
            logging.error(f"  - {file}")
        return False
    
    return True

def check_directories():
    """Check and create required directories"""
    required_dirs = [
        'database',
        'backups', 
        'Auth',
        'templates',
        'utils'
    ]
    
    for dir_name in required_dirs:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            logging.info(f"Creating directory: {dir_name}")
            dir_path.mkdir(parents=True, exist_ok=True)
        else:
            logging.info(f"Directory '{dir_name}' found")

def check_env_config():
    """Check environment configuration"""
    # Load environment variables from .env if it exists
    env_file = Path('.env')
    if env_file.exists():
        load_dotenv()
        logging.info(".env configuration file found and loaded")
    else:
        logging.warning(".env file not found. Using default configuration.")
        logging.info("You can copy .env.example to .env for custom configuration")
    
    # Define required and optional environment variables
    required_env_vars = {
        "SECRET_KEY": "Key for Auth JWT (generate with utils/generate_random_key.py)",
        "LOGIN_KEY": "Login authentication key (set via CredsManager.py)",
        "PASSWORD_KEY": "Password authentication key (set via CredsManager.py)"
    }
    
    optional_env_vars = {
        "DATABASE_URL": "sqlite:///./database/secrets_scanner.db",
        "MICROSERVICE_URL": "http://127.0.0.1:8001", 
        "APP_HOST": "127.0.0.1",
        "APP_PORT": "8000",
        "HUB_TYPE": "Azure",
        "BACKUP_DIR": "./backups",
        "BACKUP_RETENTION_DAYS": "7",
        "BACKUP_INTERVAL_HOURS": "24"
    }
    
    missing_required = []
    
    # Check required environment variables
    for env_var, description in required_env_vars.items():
        value = os.getenv(env_var)
        if not value or value == "***":
            missing_required.append((env_var, description))
        else:
            logging.info(f"{env_var} is configured")
    
    # Set defaults for optional variables if not present
    for env_var, default_value in optional_env_vars.items():
        if not os.getenv(env_var):
            os.environ[env_var] = default_value
            logging.info(f"{env_var} set to default: {default_value}")
        else:
            logging.info(f"{env_var} is configured")
    
    # Report missing required variables
    if missing_required:
        logging.error("Missing required environment variables:")
        for env_var, description in missing_required:
            logging.error(f"  - {env_var}: {description}")
        
        if any(var in ["LOGIN_KEY", "PASSWORD_KEY"] for var, _ in missing_required):
            logging.info("To configure authentication credentials:")
            logging.info("   Run: python CredsManager.py")
        
        if any(var == "SECRET_KEY" for var, _ in missing_required):
            logging.info("To generate SECRET_KEY:")
            logging.info("   Run: python utils/generate_random_key.py")
            logging.info("   Then add the generated key to your .env file")
        
        return False
    
    return True

def check_credentials():
    """Check credentials files"""
    creds_files = {
        "Auth/login.dat": "Login credentials file",
        "Auth/password.dat": "Password credentials file"
    }
    
    all_exist = True
    for creds_file, description in creds_files.items():
        if not Path(creds_file).exists():
            logging.error(f"{description} '{creds_file}' not found")
            all_exist = False
        else:
            logging.info(f"{description} '{creds_file}' found")
    
    if not all_exist:
        logging.info("To create credentials files:")
        logging.info("   Run: python CredsManager.py")
        logging.info("   This will create the required authentication files")
        return False
    
    return True

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

def display_startup_info():
    """Display startup information"""
    app_host = os.getenv('APP_HOST', '127.0.0.1')
    app_port = os.getenv('APP_PORT', '8000')
    hub_type = os.getenv('HUB_TYPE', 'Azure')
    database_url = os.getenv('DATABASE_URL', 'sqlite:///./database/secrets_scanner.db')
    
    print("\nStarting Secrets Scanner...")
    print(f"Application URL: http://{app_host}:{app_port}")
    print(f"Database: {database_url}")
    print(f"Repository hub type: {hub_type}")
    print(f"Backup directory: {os.getenv('BACKUP_DIR', './backups')}")
    print("Authentication: Configured via CredsManager.py")

def main():
    # Setup logging first
    logger = setup_logging()
    
    print("Secrets Scanner Startup Check")
    print("=" * 50)
    
    # Step 1: Check required files
    print("\nChecking required files...")
    if not check_files():
        logging.error("Please ensure all required files are present before starting.")
        logging.info("Make sure you have main.py, requirements.txt, and CredsManager.py")
        sys.exit(1)
    
    # Step 2: Check and create directories
    print("\nChecking directories...")
    check_directories()
    
    # Step 3: Check dependencies
    print("\nChecking Python dependencies...")
    if not check_dependencies():
        logging.error("Required dependencies not installed.")
        logging.info("Please run: pip install -r requirements.txt")
        sys.exit(1)
    
    # Step 4: Check environment configuration
    print("\nChecking environment configuration...")
    if not check_env_config():
        logging.error("Environment configuration incomplete.")
        logging.info("Please complete the configuration steps shown above.")
        sys.exit(1)
    
    # Step 5: Check credentials
    print("\nChecking authentication credentials...")
    if not check_credentials():
        logging.error("Authentication credentials not configured.")
        logging.info("Please run CredsManager.py to set up authentication.")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    logging.info("All startup checks passed!")
    
    # Display startup information
    display_startup_info()
    print("\n" + "=" * 50)
    
    # Start the FastAPI application
    try:
        app_host = os.getenv('APP_HOST', '127.0.0.1')
        app_port = int(os.getenv('APP_PORT', '8000'))
        
        import uvicorn
        from main import app
        
        print("Starting application server...")
        uvicorn.run(
            app, 
            host=app_host, 
            port=app_port, 
            log_level="info",
            access_log=True
        )
        
    except ImportError as e:
        logging.error(f"Import error: {e}")
        logging.info("Please run: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error starting application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()