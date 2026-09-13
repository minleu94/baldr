@echo off
setlocal EnableExtensions

rem Daily recommendation calibration loop.  This task is shadow-only: it reads
rem the market DB in SQLite read-only mode and writes immutable datasets,
rem candidates, captures, natural evidence, receipts and active-pointer
rem recovery state under the dedicated recommendation-learning shadow root.
rem It does not write recommendation runs,
rem evidence DB rows, portfolio state or broker orders.
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

set "SYMBOL_ARGS="
if not "%RECOMMENDATION_LEARNING_SYMBOLS%"=="" set "SYMBOL_ARGS=--symbols "%RECOMMENDATION_LEARNING_SYMBOLS%""
set "REPLAY_START_ARGS="
if not "%RECOMMENDATION_LEARNING_REPLAY_START_DATE%"=="" set "REPLAY_START_ARGS=--replay-start-date "%RECOMMENDATION_LEARNING_REPLAY_START_DATE%""
set "REPLAY_END_ARGS="
if not "%RECOMMENDATION_LEARNING_REPLAY_END_DATE%"=="" set "REPLAY_END_ARGS=--replay-end-date "%RECOMMENDATION_LEARNING_REPLAY_END_DATE%""

"%PYTHON%" "scripts\scheduled\run_daily_recommendation_learning.py" ^
  --data-root "%DATA_ROOT%" ^
  --output-root "%RECOMMENDATION_LEARNING_OUTPUT_ROOT%" ^
  --source-db "%DB_PATH%" ^
  %SYMBOL_ARGS% ^
  --history-start-date "%RECOMMENDATION_LEARNING_HISTORY_START_DATE%" ^
  %REPLAY_START_ARGS% ^
  %REPLAY_END_ARGS% ^
  --fixed-round-trip-cost-bp "%RECOMMENDATION_LEARNING_COST_BP%" ^
  --max-decision-dates "%RECOMMENDATION_LEARNING_MAX_DECISION_DATES%" ^
  --replay-selection-policy latest_eligible_dates
exit /b %ERRORLEVEL%
