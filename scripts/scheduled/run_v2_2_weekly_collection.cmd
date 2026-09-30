@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%" || exit /b 1

set "PYTHON=%REPO_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
if "%DATA_ROOT%"=="" set "DATA_ROOT=D:\Min\Python\Project\FA_Data"
if "%OUTPUT_ROOT%"=="" set "OUTPUT_ROOT=%DATA_ROOT%\output"
if "%SOURCE_DB_PATH%"=="" set "SOURCE_DB_PATH=%DATA_ROOT%\sqlite\twstock.db"
if "%SIDECAR_DB_PATH%"=="" set "SIDECAR_DB_PATH=%OUTPUT_ROOT%\scheduled\v2_2_weekly_collection\evidence_scheduler.db"

call "%PYTHON%" "scripts\collect_v2_2_weekly_evidence.py" --source-db-path "%SOURCE_DB_PATH%" --sidecar-db-path "%SIDECAR_DB_PATH%" --output-root "%OUTPUT_ROOT%"
set "CORE_EXIT=%ERRORLEVEL%"
if not "%CORE_EXIT%"=="0" exit /b %CORE_EXIT%

rem Keep the independent MOPS research capture off the Quick/core path. It is
rem enabled by default for this weekly wrapper and can be disabled explicitly.
if not defined BALDR_ENABLE_MOPS_STATEMENT_CUSTODY set "BALDR_ENABLE_MOPS_STATEMENT_CUSTODY=1"
if /I "%BALDR_ENABLE_MOPS_STATEMENT_CUSTODY%"=="0" exit /b %CORE_EXIT%

call "%PYTHON%" "scripts\fetch_mops_statement_availability.py" --last-complete-taipei-7-days
set "RESEARCH_EXIT=%ERRORLEVEL%"
if not "%RESEARCH_EXIT%"=="0" echo MOPS weekly research capture failed with exit code %RESEARCH_EXIT%; inspect the per-run weekly_research_status.json or process output.

rem Preserve the existing core collection result and pending_human_review semantics.
exit /b %CORE_EXIT%
