@echo off
title Caipiao Generator
echo Starting Caipiao Generator...

if not exist "venv\Scripts\python.exe" (
    echo Virtual environment not found. Please run create_venv.bat first.
    pause
    exit /b 1
)

.\venv\Scripts\python.exe main.py

if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)
