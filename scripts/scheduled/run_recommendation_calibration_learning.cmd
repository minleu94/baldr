@echo off
setlocal EnableExtensions

rem Daily recommendation calibration loop.  This shadow-only task refreshes
rem bounded technical/official source custody, writes the normal recommendation
rem snapshot, then accumulates immutable learning artifacts under one durable
rem recommendation-learning shadow root.
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%" || exit /b 1

if defined BALDR_PYTHON set "PYTHON=%BALDR_PYTHON%"
if not defined PYTHON if exist "%REPO_ROOT%\.venv\Scripts\python.exe" set "PYTHON=%REPO_ROOT%\.venv\Scripts\python.exe"
if not defined PYTHON (
  echo No governed Python interpreter found. Set BALDR_PYTHON or install %REPO_ROOT%\.venv\Scripts\python.exe.
  exit /b 2
)
if not exist "%PYTHON%" (
  echo Governed Python interpreter does not exist: %PYTHON%
  exit /b 2
)
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
echo Governed Python: %PYTHON%
if "%DATA_ROOT%"=="" set "DATA_ROOT=D:\Min\Python\Project\FA_Data"
if "%RECOMMENDATION_LEARNING_OUTPUT_ROOT%"=="" (
  for %%I in ("%DATA_ROOT%\..") do set "RECOMMENDATION_LEARNING_OUTPUT_ROOT=%%~fI\FA_Data_Shadow"
)
echo Recommendation learning shadow root: %RECOMMENDATION_LEARNING_OUTPUT_ROOT%
if "%DB_PATH%"=="" set "DB_PATH=%DATA_ROOT%\sqlite\twstock.db"
if "%RECOMMENDATION_LEARNING_HISTORY_START_DATE%"=="" set "RECOMMENDATION_LEARNING_HISTORY_START_DATE=2014-01-01"
if "%RECOMMENDATION_LEARNING_MAX_DECISION_DATES%"=="" set "RECOMMENDATION_LEARNING_MAX_DECISION_DATES=100"
if "%RECOMMENDATION_LEARNING_COST_BP%"=="" set "RECOMMENDATION_LEARNING_COST_BP=50"
if "%RECOMMENDATION_SNAPSHOT_MAX_STOCKS%"=="" set "RECOMMENDATION_SNAPSHOT_MAX_STOCKS=200"
if "%RECOMMENDATION_SNAPSHOT_TOP_N%"=="" set "RECOMMENDATION_SNAPSHOT_TOP_N=50"
if "%RECOMMENDATION_OFFICIAL_MAX_ATTEMPTS%"=="" set "RECOMMENDATION_OFFICIAL_MAX_ATTEMPTS=4"
if "%RECOMMENDATION_OFFICIAL_TIMEOUT_SECONDS%"=="" set "RECOMMENDATION_OFFICIAL_TIMEOUT_SECONDS=30"
if "%RECOMMENDATION_OFFICIAL_RETRY_DELAY_SECONDS%"=="" set "RECOMMENDATION_OFFICIAL_RETRY_DELAY_SECONDS=2"
if "%RECOMMENDATION_OFFICIAL_REQUEST_DELAY_SECONDS%"=="" set "RECOMMENDATION_OFFICIAL_REQUEST_DELAY_SECONDS=1"

set "SYMBOL_ARGS="
if not "%RECOMMENDATION_LEARNING_SYMBOLS%"=="" set "SYMBOL_ARGS=--symbols "%RECOMMENDATION_LEARNING_SYMBOLS%""
"%PYTHON%" "scripts\scheduled\run_daily_recommendation_learning_pipeline.py" ^
  --data-root "%DATA_ROOT%" ^
  --output-root "%RECOMMENDATION_LEARNING_OUTPUT_ROOT%" ^
  --source-db "%DB_PATH%" ^
  --max-stocks "%RECOMMENDATION_SNAPSHOT_MAX_STOCKS%" ^
  --top-n "%RECOMMENDATION_SNAPSHOT_TOP_N%" ^
  %SYMBOL_ARGS% ^
  --history-start-date "%RECOMMENDATION_LEARNING_HISTORY_START_DATE%" ^
  --fixed-round-trip-cost-bp "%RECOMMENDATION_LEARNING_COST_BP%" ^
  --max-decision-dates "%RECOMMENDATION_LEARNING_MAX_DECISION_DATES%" ^
  --official-max-attempts "%RECOMMENDATION_OFFICIAL_MAX_ATTEMPTS%" ^
  --official-timeout-seconds "%RECOMMENDATION_OFFICIAL_TIMEOUT_SECONDS%" ^
  --official-retry-delay-seconds "%RECOMMENDATION_OFFICIAL_RETRY_DELAY_SECONDS%" ^
  --official-request-delay-seconds "%RECOMMENDATION_OFFICIAL_REQUEST_DELAY_SECONDS%"
exit /b %ERRORLEVEL%
