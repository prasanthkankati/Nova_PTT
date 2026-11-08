# Install script for NOVA Push-to-Talk (Windows)
$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "       Installing NOVA Push-to-Talk     " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppDir

# 1. Install Python requirements
Write-Host "`n[1/3] Verifying Python requirements..." -ForegroundColor Yellow
python -m pip install -r requirements.txt --quiet

# 2. Download Whisper engine & models if missing
Write-Host "[2/3] Checking offline Whisper engine & model..." -ForegroundColor Yellow
python setup_whisper.py

# 3. Create Windows Shortcuts (Startup & Desktop)
Write-Host "[3/3] Registering auto-start and system shortcuts..." -ForegroundColor Yellow

$WshShell = New-Object -ComObject WScript.Shell
$TargetScript = Join-Path $AppDir "right_alt_ptt.py"
$PythonW = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $PythonW) {
    $PythonW = "pythonw.exe"
}

# Startup shortcut (Auto-runs silently on Windows boot!)
$StartupFolder = [Environment]::GetFolderPath("Startup")
$StartupShortcut = $WshShell.CreateShortcut((Join-Path $StartupFolder "NOVA.lnk"))
$StartupShortcut.TargetPath = $PythonW
$StartupShortcut.Arguments = "`"$TargetScript`""
$StartupShortcut.WorkingDirectory = $AppDir
$StartupShortcut.Description = "NOVA Push-to-Talk Voice Dictation"
$StartupShortcut.Save()
Write-Host "  -> Registered in Windows Startup: Starts automatically on login!" -ForegroundColor Green

# Desktop shortcut
$DesktopFolder = [Environment]::GetFolderPath("Desktop")
$DesktopShortcut = $WshShell.CreateShortcut((Join-Path $DesktopFolder "NOVA.lnk"))
$DesktopShortcut.TargetPath = $PythonW
$DesktopShortcut.Arguments = "`"$TargetScript`""
$DesktopShortcut.WorkingDirectory = $AppDir
$DesktopShortcut.Description = "NOVA Push-to-Talk Voice Dictation"
$DesktopShortcut.Save()
Write-Host "  -> Created Desktop shortcut: NOVA" -ForegroundColor Green

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   NOVA Successfully Installed! ✨      " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting NOVA now..." -ForegroundColor Yellow

Start-Process -FilePath $PythonW -ArgumentList "`"$TargetScript`"" -WorkingDirectory $AppDir
Write-Host "NOVA is active in the background. Hold [Right Alt] anywhere to dictate!" -ForegroundColor Green
