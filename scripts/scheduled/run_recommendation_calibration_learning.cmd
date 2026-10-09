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
if not defined CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT (
  if defined OUTPUT_ROOT set "CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT=%OUTPUT_ROOT%"
  if not defined CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT set "CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT=%DATA_ROOT%\output"
)
if "%RECOMMENDATION_LEARNING_OUTPUT_ROOT%"=="" (
  for %%I in ("%DATA_ROOT%\..") do set "RECOMMENDATION_LEARNING_OUTPUT_ROOT=%%~fI\FA_Data_Shadow"
)
echo Recommendation learning shadow root: %RECOMMENDATION_LEARNING_OUTPUT_ROOT%
echo Current-observed raw status root: %CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT%
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
if "%RECOMMENDATION_CURRENT_OBSERVED_WAIT_MAX_SECONDS%"=="" set "RECOMMENDATION_CURRENT_OBSERVED_WAIT_MAX_SECONDS=10500"
if "%RECOMMENDATION_CURRENT_OBSERVED_WAIT_POLL_SECONDS%"=="" set "RECOMMENDATION_CURRENT_OBSERVED_WAIT_POLL_SECONDS=15"
if "%RECOMMENDATION_CHILD_TIMEOUT_SECONDS%"=="" set "RECOMMENDATION_CHILD_TIMEOUT_SECONDS=3600"
rem 保留兩個 1h child 與 5min terminal 預算後，仍須等候 G6 真實研究鏈。
if "%RECOMMENDATION_PIPELINE_TIMEOUT_SECONDS%"=="" set "RECOMMENDATION_PIPELINE_TIMEOUT_SECONDS=14400"

set "SYMBOL_ARGS="
if not "%RECOMMENDATION_LEARNING_SYMBOLS%"=="" set "SYMBOL_ARGS=--symbols "%RECOMMENDATION_LEARNING_SYMBOLS%""
rem Existing archi/Interactive/Limited Task and 05:45 trigger remain unchanged.
rem Only an explicit, validated activation descriptor enables personal H20.
if not defined PERSONAL_H20_ACTIVATION_CONFIG set "PERSONAL_H20_ACTIVATION_CONFIG=%DATA_ROOT%\personal\recommendation_h20\activation.json"
set "PERSONAL_H20_ARGS="
if defined PERSONAL_H20_ACTIVATION_CONFIG if exist "%PERSONAL_H20_ACTIVATION_CONFIG%" set "PERSONAL_H20_ARGS=--personal-h20-activation-config "%PERSONAL_H20_ACTIVATION_CONFIG%""
"%PYTHON%" "scripts\scheduled\run_daily_recommendation_learning_pipeline.py" ^
  --data-root "%DATA_ROOT%" ^
  --output-root "%RECOMMENDATION_LEARNING_OUTPUT_ROOT%" ^
  --current-observed-source-output-root "%CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT%" ^
  --current-observed-wait-max-seconds "%RECOMMENDATION_CURRENT_OBSERVED_WAIT_MAX_SECONDS%" ^
  --current-observed-wait-poll-seconds "%RECOMMENDATION_CURRENT_OBSERVED_WAIT_POLL_SECONDS%" ^
  --child-timeout-seconds "%RECOMMENDATION_CHILD_TIMEOUT_SECONDS%" ^
  --pipeline-timeout-seconds "%RECOMMENDATION_PIPELINE_TIMEOUT_SECONDS%" ^
  --source-db "%DB_PATH%" ^
  --max-stocks "%RECOMMENDATION_SNAPSHOT_MAX_STOCKS%" ^
  --top-n "%RECOMMENDATION_SNAPSHOT_TOP_N%" ^
  %SYMBOL_ARGS% ^
  %PERSONAL_H20_ARGS% ^
  --history-start-date "%RECOMMENDATION_LEARNING_HISTORY_START_DATE%" ^
  --fixed-round-trip-cost-bp "%RECOMMENDATION_LEARNING_COST_BP%" ^
  --max-decision-dates "%RECOMMENDATION_LEARNING_MAX_DECISION_DATES%" ^
  --official-max-attempts "%RECOMMENDATION_OFFICIAL_MAX_ATTEMPTS%" ^
  --official-timeout-seconds "%RECOMMENDATION_OFFICIAL_TIMEOUT_SECONDS%" ^
  --official-retry-delay-seconds "%RECOMMENDATION_OFFICIAL_RETRY_DELAY_SECONDS%" ^
  --official-request-delay-seconds "%RECOMMENDATION_OFFICIAL_REQUEST_DELAY_SECONDS%"
exit /b %ERRORLEVEL%
