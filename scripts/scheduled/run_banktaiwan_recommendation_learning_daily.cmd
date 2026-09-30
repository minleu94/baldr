@echo off
setlocal EnableExtensions

rem Daily BankTaiwan electronic-cost research lane.
rem Reuse existing snapshot/source custody; do not rerun producer stages.
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
if "%DATA_ROOT%"=="" set "DATA_ROOT=D:\Min\Python\Project\FA_Data"
for %%I in ("%DATA_ROOT%\..") do set "DATA_PARENT=%%~fI"
if "%BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT%"=="" set "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT=%DATA_PARENT%\FA_Data_Shadow_BankTaiwan"
if "%BANKTAIWAN_SOURCE_ARTIFACT_ROOT%"=="" set "BANKTAIWAN_SOURCE_ARTIFACT_ROOT=%DATA_PARENT%\FA_Data_Shadow"
if "%BANKTAIWAN_SNAPSHOT_OUTPUT_ROOT%"=="" set "BANKTAIWAN_SNAPSHOT_OUTPUT_ROOT=%BANKTAIWAN_SOURCE_ARTIFACT_ROOT%"
if "%BANKTAIWAN_SOURCE_DB%"=="" set "BANKTAIWAN_SOURCE_DB=%DATA_ROOT%\sqlite\twstock.db"
if "%BANKTAIWAN_HISTORY_START_DATE%"=="" set "BANKTAIWAN_HISTORY_START_DATE=2014-01-01"
if "%BANKTAIWAN_MAX_DECISION_DATES%"=="" set "BANKTAIWAN_MAX_DECISION_DATES=100"
if "%BANKTAIWAN_COST_POLICY_ESTIMATE_DATE%"=="" set "BANKTAIWAN_COST_POLICY_ESTIMATE_DATE=2026-01-01"
if "%BANKTAIWAN_RESEARCH_ORDER_QUANTITY_SHARES%"=="" set "BANKTAIWAN_RESEARCH_ORDER_QUANTITY_SHARES=1000"
if "%BANKTAIWAN_CHILD_TIMEOUT_SECONDS%"=="" set "BANKTAIWAN_CHILD_TIMEOUT_SECONDS=7200"

rem 僅固定 Bank 排程等待同日上游 Task 的 terminal projection，最多 30 分鐘。
set "BANKTAIWAN_UPSTREAM_PROJECTION_WAIT_SECONDS=1800"

echo Governed Python: %PYTHON%
echo BankTaiwan lane root: %BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT%
echo Snapshot source root: %BANKTAIWAN_SNAPSHOT_OUTPUT_ROOT%
echo Source custody root: %BANKTAIWAN_SOURCE_ARTIFACT_ROOT%
echo Research sizing: %BANKTAIWAN_RESEARCH_ORDER_QUANTITY_SHARES% shares (not user position)

"%PYTHON%" "scripts\scheduled\run_banktaiwan_recommendation_learning_daily.py" ^
  --data-root "%DATA_ROOT%" ^
  --output-root "%BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT%" ^
  --snapshot-output-root "%BANKTAIWAN_SNAPSHOT_OUTPUT_ROOT%" ^
  --source-artifact-root "%BANKTAIWAN_SOURCE_ARTIFACT_ROOT%" ^
  --source-db "%BANKTAIWAN_SOURCE_DB%" ^
  --history-start-date "%BANKTAIWAN_HISTORY_START_DATE%" ^
  --max-decision-dates "%BANKTAIWAN_MAX_DECISION_DATES%" ^
  --cost-policy-estimate-date "%BANKTAIWAN_COST_POLICY_ESTIMATE_DATE%" ^
  --research-order-quantity-shares "%BANKTAIWAN_RESEARCH_ORDER_QUANTITY_SHARES%" ^
  --child-timeout-seconds "%BANKTAIWAN_CHILD_TIMEOUT_SECONDS%" ^
  --upstream-projection-wait-seconds "%BANKTAIWAN_UPSTREAM_PROJECTION_WAIT_SECONDS%"
exit /b %ERRORLEVEL%
