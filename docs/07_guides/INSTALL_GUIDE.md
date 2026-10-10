# 安裝與環境設定

Windows x64／Python3.11 是目前驗證基線。新的使用者從全新 venv 安裝，不依賴開發者既有 `.venv`。

```powershell
$env:PYTHONUTF8 = "1"
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt -c requirements-py311-windows.constraints.txt
$env:DATA_ROOT = Join-Path $env:LOCALAPPDATA "baldr\data"
$env:OUTPUT_ROOT = Join-Path $env:LOCALAPPDATA "baldr\reports"
.\.venv\Scripts\python.exe ui_qt\main.py
```

一般使用裝 requirements-runtime；開發者另裝 requirements-dev。requirements.txt 仍是相容完整開發入口。PYTHONUTF8需在安裝前設定。constraints不是完整跨平台lock；TA-Lib／fastdtw需相容wheel或compiler，不使用來源不明或個人機器wheel。

DATA_ROOT 用於行情／SQLite；OUTPUT_ROOT 用於報告／狀態，兩者獨立。PROFILE=test 會在兩個 root 加上 _test；第一次使用保留預設 prod 並使用自己的空目錄。`.env.example` 不會自動生效，環境設定必須在啟動的同一 shell；供應商 token 只保留本機。

```powershell
.\.venv\Scripts\python.exe -c "import pandas, numpy, PySide6; print('core imports OK')"
```

三個imports只是初步確認，不取代完整UI啟動。建構config會建立目錄及logging，不是只讀檢查。啟動後到數據更新看來源狀態，缺DB/table保持缺件；更新只對自己的roots，不刪既有DB/WAL/SHM或手工改表。

安裝失敗先記錄套件／錯誤型別與Python架構；圖表異常檢查QtWebEngine及Matplotlib相容性；資料為空檢查同shell的兩root及PROFILE。研究／Evidence unknown需具名來源及lineage，不能用別人的模型或synthetic資料補資格。

WSL／CodeRabbit及其他審查服務是可選開發工具，不是首次使用依賴。完整操作見 [Manual](APPLICATION_MANUAL.md)，流程見 [快速開始](QUICK_START.md)。
