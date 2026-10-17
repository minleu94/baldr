# 快速開始

若你要使用目前指定的141c試用包，先讀[目前試用版指南](TRIAL_VERSION_GUIDE.md)。首次啟動前放妥完整資料夾，再雙擊`Launch-Baldr.cmd`；首次設定本機實測約8分34秒，請保留命令視窗。後續使用本包state並保留保存內容；已用state不可直接搬動。這只驗全新包在本機新位置的出口，完整新電腦安裝與私人環境搬移仍按下方流程處理。

第一次使用前，先選擇執行方式：

- source 版需要 Windows x64／Python 3.11 和新的虛擬環境，依[安裝指南](INSTALL_GUIDE.md)設定。
- Windows 可攜版直接使用完整的 `baldr` 資料夾，依[可攜版指南](PORTABLE_WINDOWS.md)設定。
- 舊環境搬機或接手排程，先依[機器啟動 Runbook](MACHINE_BOOTSTRAP_RUNBOOK.md)盤點；不要把舊環境整包複製成新機設定。

## source 版最短啟動

在專案根目錄以同一個 PowerShell 視窗執行：

```powershell
$env:PYTHONUTF8 = "1"
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt -c requirements-py311-windows.constraints.txt
$env:DATA_ROOT = Join-Path $env:LOCALAPPDATA "baldr\data"
$env:OUTPUT_ROOT = Join-Path $env:LOCALAPPDATA "baldr\reports"
.\.venv\Scripts\python.exe ui_qt\main.py
```

`DATA_ROOT` 與 `OUTPUT_ROOT` 是兩個獨立的絕對路徑；這些環境值只作用於目前 PowerShell。`.env.example` 是欄位示意，程式不會自動讀取 `.env`。不要使用開發者的資料路徑，也不要把別人的資料庫、持倉、模型或憑證複製到自己的 roots。

## 第一次打開

1. 在左側選「數據更新」，按「檢查數據狀態」。記下資料日期、缺庫／缺表及 warnings。
2. 只有在確認資料來源、授權與目標日期後才執行更新。日常補近期資料可用「快速更新（跳過大型合併）」；需重建完整 CSV 時才使用「安全更新（完整 CSV + SQLite）」。
3. 確認行情、技術指標與研究基準日，再查看「市場探索」、「推薦分析」或「策略回測」。
4. 按 [完整操作手冊](APPLICATION_MANUAL.md) 查看各工作區步驟與結果判讀。

missing、unknown、stale、partial、零筆及已完成是不同狀態。沒有來源資料時保留缺件，不填零；安裝完成不代表資料完整、模型通過、排程已註冊或自然執行已驗收。個人資料、私有模型與排程都需 owner 明確選擇。
