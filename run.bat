@echo off
setlocal enabledelayedexpansion
title J.A.R.V.I.S. Mark VII - Stark Industries
chcp 65001 >nul

cd /d "%~dp0"

echo ============================================================
echo   STARK INDUSTRIES J.A.R.V.I.S. MARK VII - LAUNCHER
echo ============================================================
echo.

:: 1. Detect Python executable
set "PY_CMD="

python --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PY_CMD=python"
    goto :python_found
)

py -3 --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PY_CMD=py -3"
    goto :python_found
)

py --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PY_CMD=py"
    goto :python_found
)

:: Check common Windows Python install locations
for %%D in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Program Files\Python312\python.exe"
    "C:\Program Files\Python311\python.exe"
    "C:\Program Files\Python310\python.exe"
) do (
    if exist %%D (
        set "PY_CMD=%%D"
        goto :python_found
    )
)

echo [ERROR] Python 3 was not found on your system!
echo Please install Python 3.10+ from https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:python_found
for /f "tokens=*" %%V in ('!PY_CMD! --version 2^>^&1') do set "PY_VER=%%V"
echo [SYS] Using !PY_VER! (!PY_CMD!)

:: 2. Verify .env file
if not exist ".env" (
    if exist ".env.example" (
        echo [SYS] No .env found. Initializing from .env.example...
        copy ".env.example" ".env" >nul
        echo [NOTICE] Created .env file. Please add your free API keys for full AI access.
    ) else (
        echo [WARNING] No .env file found. Operating in local offline mode.
    )
)

:: 3. Fast Dependency Check
!PY_CMD! -c "import webview, requests, pygame" >nul 2>&1
if !errorlevel! neq 0 (
    echo [SYS] Required packages missing. Installing dependencies...
    !PY_CMD! -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo [WARNING] Some dependencies failed to install. Attempting launch anyway...
    )
)

:: 4. Launch JARVIS
echo [SYS] Initializing Stark Mark VII Protocols...
echo.

if "%~1"=="" (
    :: Default: launch interactive launcher / HUD GUI
    !PY_CMD! main.py
) else (
    :: Forward passed CLI arguments
    !PY_CMD! main.py %*
)

set "EXIT_CODE=!errorlevel!"

if !EXIT_CODE! neq 0 (
    echo.
    echo ============================================================
    echo [NOTICE] J.A.R.V.I.S. exited with code !EXIT_CODE!
    echo ============================================================
    echo Press any key to close this window...
    pause >nul
)

exit /b !EXIT_CODE!
