@echo off
rem Double-click to collect verification evidence into the reports folder.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\verify_windows.ps1"
echo.
echo Finished. See the reports folder.
pause
