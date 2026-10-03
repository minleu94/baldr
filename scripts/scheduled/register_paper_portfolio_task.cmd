@echo off
setlocal EnableExtensions

rem Keep the existing dryrun|register CLI. The default trigger is explicitly
rem Asia/Taipei 08:25 (+08:00); an optional second argument is an explicit
rem custom Windows-user-local HH:mm override.
set "MODE=%~1"
if "%MODE%"=="" set "MODE=dryrun"
if /I not "%MODE%"=="dryrun" if /I not "%MODE%"=="register" goto usage
set "CUSTOM_USER_LOCAL_TIME=%~2"
set "EXECUTION_TIME_LIMIT_OVERRIDE=%~3"
if not "%~4"=="" goto usage
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
if defined BALDR_PYTHON set "PYTHON=%BALDR_PYTHON%"
if not defined PYTHON if exist "%REPO_ROOT%\.venv\Scripts\python.exe" set "PYTHON=%REPO_ROOT%\.venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python"

"%PYTHON%" "%SCRIPT_DIR%register_paper_portfolio_task.py" "%MODE%" "%CUSTOM_USER_LOCAL_TIME%" "%EXECUTION_TIME_LIMIT_OVERRIDE%" --repo-root "%REPO_ROOT%"
exit /b %ERRORLEVEL%

:usage
echo Usage: scripts\scheduled\register_paper_portfolio_task.cmd dryrun^|register [HH:mm] [ISO-8601-duration]
echo Optional HH:mm selects a custom user-local trigger; timeout is preserved unless explicitly overridden.
exit /b 2
