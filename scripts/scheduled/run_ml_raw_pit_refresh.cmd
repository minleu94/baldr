@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

if not defined DATA_ROOT set "DATA_ROOT=D:\Min\Python\Project\FA_Data"
if not defined OUTPUT_ROOT set "OUTPUT_ROOT=%DATA_ROOT%\output"
if defined BALDR_PYTHON set "PYTHON=%BALDR_PYTHON%"
if not defined PYTHON if exist "%REPO_ROOT%\.venv\Scripts\python.exe" set "PYTHON=%REPO_ROOT%\.venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PROSPECTIVE_CAPTURE_ARGS=--capture-prospective-daily-price-candidate"
set "DAILY_SOURCE_ROW_PROJECTION_ARGS=--project-daily-source-rows"
if "%BALDR_ENABLE_ML_PROSPECTIVE_DAILY_CAPTURE%"=="0" set "PROSPECTIVE_CAPTURE_ARGS="
if "%BALDR_ENABLE_ML_PROSPECTIVE_DAILY_CAPTURE%"=="0" set "DAILY_SOURCE_ROW_PROJECTION_ARGS="
if "%BALDR_ENABLE_ML_DAILY_SOURCE_ROW_PROJECTION%"=="0" set "DAILY_SOURCE_ROW_PROJECTION_ARGS="

"%PYTHON%" "%REPO_ROOT%\scripts\scheduled\run_ml_raw_pit_refresh.py" ^
  --data-root "%DATA_ROOT%" ^
  --output-root "%OUTPUT_ROOT%" ^
  --database "%DATA_ROOT%\sqlite\twstock.db" %PROSPECTIVE_CAPTURE_ARGS% %DAILY_SOURCE_ROW_PROJECTION_ARGS%
exit /b %ERRORLEVEL%
