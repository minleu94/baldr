@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

if not defined DATA_ROOT set "DATA_ROOT=F:\Min\Python\Project\FA_Data"
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

set "LAUNCHER_LOG_ROOT=%OUTPUT_ROOT%\scheduled\ml_raw_pit_refresh\launcher_logs"
if not exist "%LAUNCHER_LOG_ROOT%\" (
  mkdir "%LAUNCHER_LOG_ROOT%" >nul 2>&1
  if errorlevel 1 goto :launcher_log_failed
)
if not exist "%LAUNCHER_LOG_ROOT%\" goto :launcher_log_failed

set "LAUNCHER_UTC="
set "LAUNCHER_TIMEZONE="
for /f "tokens=1,2 delims=|" %%A in ('powershell.exe -NoLogo -NoProfile -NonInteractive -Command "$now=[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmss.fffffffZ'); $zone=[TimeZoneInfo]::Local.Id; Write-Output ($now + '|' + $zone)" 2^>nul') do (
  set "LAUNCHER_UTC=%%A"
  set "LAUNCHER_TIMEZONE=%%B"
)
if not defined LAUNCHER_UTC goto :launcher_log_failed
if not defined LAUNCHER_TIMEZONE goto :launcher_log_failed

set "LAUNCHER_RUN_DIR=%LAUNCHER_LOG_ROOT%\%LAUNCHER_UTC%_%RANDOM%_%RANDOM%"
if exist "%LAUNCHER_RUN_DIR%\" goto :launcher_log_failed
mkdir "%LAUNCHER_RUN_DIR%" >nul 2>&1
if errorlevel 1 goto :launcher_log_failed
if not exist "%LAUNCHER_RUN_DIR%\" goto :launcher_log_failed
set "LAUNCHER_LOG=%LAUNCHER_RUN_DIR%\launcher.log"

>"%LAUNCHER_LOG%" echo task=baldr-ml-raw-pit-refresh-daily
if errorlevel 1 goto :launcher_log_failed
>>"%LAUNCHER_LOG%" echo started_at_utc=%LAUNCHER_UTC%
if errorlevel 1 goto :launcher_log_failed
>>"%LAUNCHER_LOG%" echo local_timezone="%LAUNCHER_TIMEZONE%"
if errorlevel 1 goto :launcher_log_failed
>>"%LAUNCHER_LOG%" echo repository_root="%REPO_ROOT%"
if errorlevel 1 goto :launcher_log_failed
>>"%LAUNCHER_LOG%" echo data_root="%DATA_ROOT%"
if errorlevel 1 goto :launcher_log_failed
>>"%LAUNCHER_LOG%" echo output_root="%OUTPUT_ROOT%"
if errorlevel 1 goto :launcher_log_failed
>>"%LAUNCHER_LOG%" echo python_executable="%PYTHON%"
if errorlevel 1 goto :launcher_log_failed
>>"%LAUNCHER_LOG%" echo child_stdout_stderr_begin
if errorlevel 1 goto :launcher_log_failed

"%PYTHON%" "%REPO_ROOT%\scripts\scheduled\run_ml_raw_pit_refresh.py" ^
  --data-root "%DATA_ROOT%" ^
  --output-root "%OUTPUT_ROOT%" ^
  --database "%DATA_ROOT%\sqlite\twstock.db" %PROSPECTIVE_CAPTURE_ARGS% %DAILY_SOURCE_ROW_PROJECTION_ARGS% >>"%LAUNCHER_LOG%" 2>&1
set "LAUNCHER_CHILD_EXIT=%ERRORLEVEL%"

set "LAUNCHER_COMPLETED_UTC="
for /f "usebackq delims=" %%T in (`powershell.exe -NoLogo -NoProfile -NonInteractive -Command "[DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmss.fffffffZ')" 2^>nul`) do set "LAUNCHER_COMPLETED_UTC=%%T"
if not defined LAUNCHER_COMPLETED_UTC set "LAUNCHER_COMPLETED_UTC=clock_unavailable"
>>"%LAUNCHER_LOG%" echo child_stdout_stderr_end
if errorlevel 1 goto :launcher_finalize_failed
>>"%LAUNCHER_LOG%" echo completed_at_utc=%LAUNCHER_COMPLETED_UTC%
if errorlevel 1 goto :launcher_finalize_failed
>>"%LAUNCHER_LOG%" echo child_exit_code=%LAUNCHER_CHILD_EXIT%
if errorlevel 1 goto :launcher_finalize_failed
if "%LAUNCHER_COMPLETED_UTC%"=="clock_unavailable" goto :launcher_finalize_failed
exit /b %LAUNCHER_CHILD_EXIT%

:launcher_finalize_failed
>&2 echo launcher log finalization failed; child_exit_code=%LAUNCHER_CHILD_EXIT%
if not "%LAUNCHER_CHILD_EXIT%"=="0" exit /b %LAUNCHER_CHILD_EXIT%
exit /b 73

:launcher_log_failed
>&2 echo launcher log setup failed; Python was not started.
exit /b 73
