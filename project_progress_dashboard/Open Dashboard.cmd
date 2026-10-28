@echo off
setlocal
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" project_progress_dashboard\serve_dashboard.py --open
) else (
  python project_progress_dashboard\serve_dashboard.py --open
)
if errorlevel 1 pause
