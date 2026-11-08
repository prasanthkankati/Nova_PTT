@echo off
title NOVA Installer
cd /d "%~dp0"
echo ===================================================
echo             Installing NOVA Voice Dictation
echo ===================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_nova.ps1"
if %ERRORLEVEL% NEQ 0 (
    echo Installation encountered an error. Press any key to exit.
    pause >nul
)
exit
