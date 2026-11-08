@echo off
title Uninstall NOVA
echo ===================================================
echo             Uninstalling NOVA Voice Dictation
echo ===================================================

:: Stop running processes
taskkill /F /IM whisper-server.exe >nul 2>&1
python -c "import psutil, os; [p.kill() for p in psutil.process_iter(['pid','name','cmdline']) if p.info['pid']!=os.getpid() and ('python' in (p.info['name'] or '').lower() and any('right_alt_ptt.py' in str(a).lower() for a in (p.info['cmdline'] or [])))]" >nul 2>&1

:: Remove shortcuts
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\NOVA.lnk" >nul 2>&1
del "%USERPROFILE%\Desktop\NOVA.lnk" >nul 2>&1
del "%USERPROFILE%\Desktop\Right-Alt Push-to-Talk.bat" >nul 2>&1

echo NOVA has been cleanly uninstalled from Startup and Desktop shortcuts.
echo Your project directory remains intact.
pause
exit
