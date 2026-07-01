@echo off
title Caipiao Generator - Setup

echo ==========================================
echo  Caipiao Generator - Environment Setup
echo ==========================================
echo.

if exist "venv\Scripts\python.exe" (
    echo Existing venv found. Updating dependencies...
) else (
    echo Creating virtual environment venv...
    python -m venv venv
    if errorlevel 1 (
        echo Failed to create venv. Make sure Python is installed and in PATH.
        pause
        exit /b 1
    )
    echo venv created successfully.
)

echo.
echo Installing dependencies...
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\pip.exe install -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo  Setup complete!
echo  You can now run run.bat to start the app.
echo ==========================================
pause
