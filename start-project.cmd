@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-project.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. Check .runtime\logs.
  pause
  exit /b 1
)
echo.
echo Started. You can close this window.
pause
