@echo off
setlocal EnableExtensions

rem Daily close-to-close research outcome producer.  This task is deliberately
rem separate from the evidence capture task: it only upserts evidence_outcomes
rem after a bounded, current-date calculation.  It never changes events,
rem recommendations, Paper/Formal state, or broker state.
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%" || exit /b 1

set "PYTHON=%REPO_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
if "%DATA_ROOT%"=="" set "DATA_ROOT=D:\Min\Python\Project\FA_Data"
if "%OUTPUT_ROOT%"=="" set "OUTPUT_ROOT=%DATA_ROOT%\output"
if "%DB_PATH%"=="" set "DB_PATH=%DATA_ROOT%\sqlite\twstock.db"
if "%FORWARD_OUTCOME_WINDOWS%"=="" set "FORWARD_OUTCOME_WINDOWS=5,10,20,60"
if "%FORWARD_OUTCOME_LOOKBACK_DAYS%"=="" set "FORWARD_OUTCOME_LOOKBACK_DAYS=120"
if "%FORWARD_OUTCOME_MAX_EVENTS%"=="" set "FORWARD_OUTCOME_MAX_EVENTS=2500"
if "%FORWARD_OUTCOME_EVENT_TYPE%"=="" set "FORWARD_OUTCOME_EVENT_TYPE=recommendation_included"

"%PYTHON%" "scripts\scheduled\run_scheduled_forward_outcomes.py" ^
  --data-root "%DATA_ROOT%" ^
  --output-root "%OUTPUT_ROOT%" ^
  --db-path "%DB_PATH%" ^
  --windows "%FORWARD_OUTCOME_WINDOWS%" ^
  --lookback-calendar-days "%FORWARD_OUTCOME_LOOKBACK_DAYS%" ^
  --max-events "%FORWARD_OUTCOME_MAX_EVENTS%" ^
  --event-type "%FORWARD_OUTCOME_EVENT_TYPE%" ^
  --require-cohort-identity ^
  --confirm ^
  --allow-production-db-confirm
exit /b %ERRORLEVEL%
