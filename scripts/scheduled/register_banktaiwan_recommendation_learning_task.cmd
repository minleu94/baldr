@echo off
setlocal EnableExtensions

rem Manage only the single BankTaiwan research Task Scheduler task.
rem Do not call aggregate registration or modify existing 05:40/05:45 tasks.
set "MODE=%~1"
if "%MODE%"=="" set "MODE=dryrun"
if /I not "%MODE%"=="dryrun" if /I not "%MODE%"=="register" if /I not "%MODE%"=="query" goto usage

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "TASK_NAME=baldr-recommendation-calibration-learning-banktaiwan-shadow-daily"
set "TASK_TIME=05:50"
set "TASK_SCRIPT=%REPO_ROOT%\scripts\scheduled\run_banktaiwan_recommendation_learning_daily.cmd"
set "TASK_ACTION=cmd.exe /c ""%TASK_SCRIPT%"""
if not defined BALDR_SCHTASKS_EXE set "BALDR_SCHTASKS_EXE=schtasks.exe"
if not defined BALDR_POWERSHELL_EXE set "BALDR_POWERSHELL_EXE=powershell.exe"

set "LOCAL_TIME_ZONE="
for /f "delims=" %%Z in ('tzutil /g 2^>nul') do set "LOCAL_TIME_ZONE=%%Z"
if /I not "%LOCAL_TIME_ZONE%"=="Pacific Standard Time" (
  echo Registration blocked: Windows timezone must be Pacific Standard Time; detected "%LOCAL_TIME_ZONE%".
  exit /b 2
)

echo Mode: %MODE%
echo Task: %TASK_NAME%
echo Schedule: DAILY %TASK_TIME% Pacific local time
echo Taipei mapping: 20:50 PDT / 21:50 PST; after the 05:10 snapshot and 05:45 legacy learning hooks
echo Action: %TASK_ACTION%
echo Lane root: DATA_ROOT parent ^+ FA_Data_Shadow_BankTaiwan, override BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT
echo Snapshot root: DATA_ROOT\output, override BANKTAIWAN_SNAPSHOT_OUTPUT_ROOT
echo Source custody root: canonical legacy sibling FA_Data_Shadow, override BANKTAIWAN_SOURCE_ARTIFACT_ROOT
echo Research sizing: 1000 shares by default, explicitly not a user position

if not exist "%TASK_SCRIPT%" (
  echo Wrapper missing: %TASK_SCRIPT%
  echo Wrapper preflight failed. No scheduled task was created.
  exit /b 2
)

if /I "%MODE%"=="dryrun" (
  echo Dryrun only. No scheduled task was created.
  exit /b 0
)
if /I "%MODE%"=="query" goto query_task

set "QUERY_OUTPUT=%TEMP%\baldr_banktaiwan_learning_query_%RANDOM%.txt"
call "%BALDR_SCHTASKS_EXE%" /Query /TN "%TASK_NAME%" /FO LIST >"%QUERY_OUTPUT%" 2>&1
set "QUERY_EXIT=%ERRORLEVEL%"
if "%QUERY_EXIT%"=="0" goto existing_task
findstr /I /C:"cannot find" /C:"not found" "%QUERY_OUTPUT%" >nul
if errorlevel 1 (
  echo Scheduler query failed; refusing to create or change %TASK_NAME%.
  type "%QUERY_OUTPUT%"
  del /q "%QUERY_OUTPUT%" >nul 2>&1
  exit /b 2
)
del /q "%QUERY_OUTPUT%" >nul 2>&1
echo Task not found; creating the single BankTaiwan research task.
call "%BALDR_SCHTASKS_EXE%" /Create /TN "%TASK_NAME%" /SC DAILY /ST %TASK_TIME% /TR "%TASK_ACTION%" /F
if errorlevel 1 exit /b %ERRORLEVEL%
set "TASK_CREATED=1"
goto apply_new_settings

:existing_task
del /q "%QUERY_OUTPUT%" >nul 2>&1
echo Existing task found; checking IgnoreNew before changing only trigger and action.
call "%BALDR_POWERSHELL_EXE%" -NoProfile -Command "$task=Get-ScheduledTask -TaskName '%TASK_NAME%' -ErrorAction Stop; if ([string]$task.Settings.MultipleInstances -ne 'IgnoreNew') { Write-Error 'Existing task must use MultipleInstances=IgnoreNew'; exit 3 }"
if errorlevel 1 exit /b 2
call "%BALDR_SCHTASKS_EXE%" /Change /TN "%TASK_NAME%" /ST %TASK_TIME% /TR "%TASK_ACTION%"
if errorlevel 1 exit /b %ERRORLEVEL%

:apply_new_settings
if not "%TASK_CREATED%"=="1" goto query_task
call "%BALDR_POWERSHELL_EXE%" -NoProfile -Command "$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; Set-ScheduledTask -TaskName '%TASK_NAME%' -Settings $settings | Out-Null"
if errorlevel 1 (
  echo Registration incomplete: could not apply IgnoreNew / two-hour execution limit to the new task.
  exit /b 2
)

:query_task
echo.
echo Registered BankTaiwan research task readback:
call "%BALDR_SCHTASKS_EXE%" /Query /TN "%TASK_NAME%" /V /FO LIST
exit /b %ERRORLEVEL%

:usage
echo Usage: scripts\scheduled\register_banktaiwan_recommendation_learning_task.cmd dryrun^|register^|query
exit /b 2
