#!/usr/bin/env python3
"""
Startup script for Secrets Scanner
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def check_files():
    """Check if required files exist"""
    required_files = {
        'main.py': 'Main FastAPI application',
        'requirements.txt': 'Python dependencies',
        '.env': 'Enviroment settings file'
    }
    
    missing_files = []
    for file, description in required_files.items():
        if not Path(file).exists():
            missing_files.append(f"{file} ({description})")
        else:
            print(f"✅ {file} found")
    
    if missing_files:
        print("\n❌ Missing required files:")
        for file in missing_files:
            print(f"  - {file}")
        return False
    
    return True

def check_env_config():
    """Check environment configuration"""
    load_dotenv()
    
    # Check if .env file exists
    if not Path('.env').exists():
        print("⚠️  .env file not found. Using default configuration.")
        print("   Create a .env file for custom configuration (see .env.example)")
    else:
        print("✅ .env configuration file found")
    env_vars = ["DATABASE_URL", "MICROSERVICE_URL", "APP_HOST", "APP_PORT", "HUB_TYPE", "BACKUP_DIR", "BACKUP_RETENTION_DAYS", "BACKUP_INTERVAL_HOURS", "LOGIN_KEY", "PASSWORD_KEY"]
    
    for env_var in env_vars:
        if not os.getenv(env_var):
            if env_var in ["LOGIN_KEY", "PASSWORD_KEY"]:
                print(f"❌ Missing required env variable: {env_var}")
                print(f"Please launch CredsManager to set login and password for Auth")
            else:
                print(f"❌ Missing required env variable: {env_var}")

    # Check credentials file
    creds_files = ["Auth/login.dat", "Auth/password.dat"]
    for creds_file in creds_files:
        if not Path(creds_file).exists():
            print(f"⚠️  Credentials file '{creds_file}' not found.")
            print("   To configure credentials, exec `python CredsManager.py`")
            return False
        else:
            print(f"✅ Credentials file '{creds_file}' found")
    
    return True

def main():
    print("🔍 Secrets Scanner Startup")
    print("=" * 40)
    
    # Load environment variables
    load_dotenv()
    
    # Check required files
    if not check_files():
        print("\n❌ Please ensure all required files are present before starting.")
        sys.exit(1)
    
    # Check environment configuration
    if not check_env_config():
        print("\n❌ Please configure authentication before starting.")
        sys.exit(1)
    
    print("\n✅ All checks passed!")
    
    # Get configuration from environment
    app_host = os.getenv('APP_HOST', '127.0.0.1')
    app_port = int(os.getenv('APP_PORT', '8000'))
    hub_type = os.getenv('HUB_TYPE', 'Azure')
    
    print(f"\n🚀 Starting Secrets Scanner...")
    print(f"📍 Application will be available at: http://{app_host}:{app_port}")
    print(f"🔑 Use credentials from {os.getenv('CREDENTIALS_FILE', 'creds.txt')} to login")
    print(f"🌐 Repository hub type: {hub_type}")
    print("\n" + "=" * 40)
    
    # Import and run the FastAPI app
    try:
        import uvicorn
        from main import app
        uvicorn.run(app, host=app_host, port=app_port, log_level="info")
    except ImportError:
        print("❌ Required dependencies not installed.")
        print("Please run: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error starting application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()