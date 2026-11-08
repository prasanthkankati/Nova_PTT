@echo off
title FlowVoice Starter
cd /d "C:\Users\Prasa\RightAlt-PTT"

:: Kill any existing whisper server or python PTT processes before starting
taskkill /F /IM whisper-server.exe >nul 2>&1
python -c "import psutil, os; [p.kill() for p in psutil.process_iter(['pid','name','cmdline']) if p.info['pid']!=os.getpid() and (('python' in (p.info['name'] or '').lower() and any('right_alt_ptt.py' in str(a).lower() for a in (p.info['cmdline'] or [])) and not any('-c' in str(a) for a in (p.info['cmdline'] or []))) or 'whisper-server' in (p.info['name'] or '').lower())]" >nul 2>&1

:: Brief pause to ensure ports are freed
ping 127.0.0.1 -n 2 >nul

:: Launch the updated FlowVoice version
start "" pythonw "C:\Users\Prasa\RightAlt-PTT\right_alt_ptt.py"
exit
