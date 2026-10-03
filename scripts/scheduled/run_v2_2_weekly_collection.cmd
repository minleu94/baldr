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

rem 控制器只包裝既有 core/child CLI，維持既有開關與 core exit code。
"%PYTHON%" "scripts\scheduled\weekly_collection_controller.py" --source-db-path "%SOURCE_DB_PATH%" --sidecar-db-path "%SIDECAR_DB_PATH%" --output-root "%OUTPUT_ROOT%"
set "CORE_EXIT=%ERRORLEVEL%"
if not "%CORE_EXIT%"=="0" exit /b %CORE_EXIT%

rem 核對剛發布的父收據後更新現況研究；不回填正式歷史PIT或改core review。
if not defined BALDR_ENABLE_CURRENT_FUNDAMENTAL_UPDATE set "BALDR_ENABLE_CURRENT_FUNDAMENTAL_UPDATE=1"
if /I "%BALDR_ENABLE_CURRENT_FUNDAMENTAL_UPDATE%"=="0" exit /b %CORE_EXIT%
"%PYTHON%" "scripts\scheduled\run_current_fundamentals_scheduled.py" --output-root "%OUTPUT_ROOT%" --db-path "%SOURCE_DB_PATH%"
exit /b %ERRORLEVEL%
