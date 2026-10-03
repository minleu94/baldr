@echo off
setlocal EnableExtensions

rem Read-only inventory with schtasks as the compatibility path and a
rem Task Scheduler COM enrichment/fallback. The Python inspector sends exact
rem root task paths and keeps query failures as unknown rather than missing.
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%" || exit /b 2
set "BALDR_SCHEDULED_REPO_ROOT=%REPO_ROOT%"

if defined BALDR_PYTHON set "PYTHON=%BALDR_PYTHON%"
if not defined PYTHON if exist "%REPO_ROOT%\.venv\Scripts\python.exe" set "PYTHON=%REPO_ROOT%\.venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python"

"%PYTHON%" "%REPO_ROOT%\scripts\inspect_scheduled_task_registration.py" --repo-root "%REPO_ROOT%"
exit /b %ERRORLEVEL%
