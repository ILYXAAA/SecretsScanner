@echo off
setlocal enabledelayedexpansion

:: Secrets Scanner Startup Script
:: This script sets up and starts the Secrets Scanner application

echo ===============================================
echo         Secrets Scanner Startup
echo ===============================================
echo.

:: Change to script directory
cd /d "%~dp0"

:: Check if git is available and update if needed
echo [1/7] Checking for updates...
git --version >nul 2>&1
if !errorlevel! equ 0 (
    echo Git found, updating repository...
    git fetch --all
    git pull
    if !errorlevel! neq 0 (
        echo Warning: Failed to update repository
        echo Continuing with existing code...
    ) else (
        echo Repository updated successfully
    )
) else (
    echo Git not found, skipping repository update
)
echo.

:: Create virtual environment if it doesn't exist
echo [2/7] Setting up Python virtual environment...
if not exist venv\ (
    echo Creating new virtual environment...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo ERROR: Failed to create virtual environment
        echo Please ensure Python is installed and accessible
        pause
        exit /b 1
    )
    echo Virtual environment created successfully
) else (
    echo Virtual environment already exists
)
echo.

:: Activate virtual environment
echo [3/7] Activating virtual environment...
call .\venv\Scripts\activate.bat
if !errorlevel! neq 0 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)
echo Virtual environment activated
echo.

:: Upgrade pip
echo [4/7] Upgrading pip...
python -m pip install --upgrade pip --index-url http://our.nexus:8080/repository/pypi-all/simple --trusted-host our.nexus --quiet
if !errorlevel! neq 0 (
    echo Warning: Failed to upgrade pip, continuing...
) else (
    echo Pip upgraded successfully
)
echo.

:: Install wheel
echo [5/7] Installing wheel...
pip install wheel --index-url http://our.nexus:8080/repository/pypi-all/simple --trusted-host our.nexus --quiet
if !errorlevel! neq 0 (
    echo Warning: Failed to install wheel, continuing...
) else (
    echo Wheel installed successfully
)
echo.

:: Install dependencies
echo [6/7] Installing project dependencies...
if exist requirements.txt (
    pip install -r requirements.txt --index-url http://our.nexus:8080/repository/pypi-all/simple --trusted-host our.nexus
    if !errorlevel! neq 0 (
        echo ERROR: Failed to install dependencies
        echo Please check requirements.txt and network connectivity
        pause
        exit /b 1
    )
    echo Dependencies installed successfully
) else (
    echo ERROR: requirements.txt not found
    pause
    exit /b 1
)
echo.

:: Create required directories
echo [7/7] Creating required directories...
if not exist database\ (
    mkdir database
    echo Created database directory
)
if not exist backups\ (
    mkdir backups
    echo Created backups directory
)
if not exist Auth\ (
    mkdir Auth
    echo Created Auth directory
)
if not exist tmp\ (
    mkdir tmp
    echo Created tmp directory
)
echo Directory setup complete
echo.

:: Check if .env file exists
echo Checking configuration...
if not exist .env (
    echo WARNING: .env file not found
    if exist .env.example (
        echo You can copy .env.example to .env and configure it
        echo.
        choice /c YN /m "Do you want to copy .env.example to .env now"
        if !errorlevel! equ 1 (
            copy .env.example .env
            echo .env file created from example
            echo Please edit .env file and configure your settings
            echo.
        )
    ) else (
        echo .env.example file also not found
    )
) else (
    echo Configuration file .env found
)
echo.

:: Check if credentials are configured
echo Checking authentication setup...
if not exist Auth\login.dat (
    echo WARNING: Authentication not configured
    echo You need to run CredsManager.py to set up login credentials
    echo.
    choice /c YN /m "Do you want to run CredsManager.py now"
    if !errorlevel! equ 1 (
        python CredsManager.py
        echo.
    )
)

:: Final status
echo ===============================================
echo          Setup Complete
echo ===============================================
echo Virtual environment: ACTIVE
echo Dependencies: INSTALLED
echo Configuration: READY
echo.

:: Start the application
echo Starting Secrets Scanner...
echo.
echo ===============================================
python run.py

:: Keep window open if there was an error
if !errorlevel! neq 0 (
    echo.
    echo ===============================================
    echo Application exited with error code: !errorlevel!
    echo Check the logs above for details
    echo.
    echo To manually start the application:
    echo   1. Activate venv: call .\venv\Scripts\activate.bat
    echo   2. Run application: python run.py
    echo ===============================================
    pause
)