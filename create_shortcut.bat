@echo off
title Create J.A.R.V.I.S. Desktop Shortcut
chcp 65001 >nul
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_desktop_shortcut.ps1"

echo.
pause
