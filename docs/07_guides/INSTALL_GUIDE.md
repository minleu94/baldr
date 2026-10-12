# 安裝與環境設定

source 版的目前 Windows 驗證基線是 Windows x64／Python 3.11。一般使用只需 runtime dependencies；不要依賴開發者既有 `.venv`。若要委託 Codex 完整處理首次安裝或 owner 移機，先從[首次安裝 Prompt](FIRST_INSTALL_PROMPT.md)和[機器啟動 Runbook](MACHINE_BOOTSTRAP_RUNBOOK.md)開始；本頁集中說明 source GUI 環境。若希望不安裝 Python，請使用[整包 Windows 可攜版](PORTABLE_WINDOWS.md)。

## 建立 source 環境

在 repo 根目錄用同一個 PowerShell 視窗執行：

```powershell
$env:PYTHONUTF8 = "1"
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt -c requirements-py311-windows.constraints.txt
$env:DATA_ROOT = Join-Path $env:LOCALAPPDATA "baldr\data"
$env:OUTPUT_ROOT = Join-Path $env:LOCALAPPDATA "baldr\reports"
.\.venv\Scripts\python.exe ui_qt\main.py
```

需要修改程式碼的開發者另裝 `requirements-dev.txt`。`requirements.txt` 是完整開發環境的相容入口；constraints 是 Windows Python 3.11 直接依賴快照，不是跨平台完整 lock file。`TA-Lib` 或 `fastdtw` 安裝問題需使用相容 wheel 或 compiler，不使用來源不明的個人 wheel。

## 設定自己的資料路徑

- `DATA_ROOT` 放行情資料與 SQLite；`OUTPUT_ROOT` 放報告、狀態與部分研究輸出。兩者分開設定，改其中一個不會連動另一個。
- 使用自己的空目錄作為新環境起點。正式資料根設定權威是 `data_module/config.py` 的 `TWStockConfig`；repo 範例值不是個人資料備份或新機預設。
- `PROFILE=test` 會分別在兩個 root 加上 `_test`。一般啟動不要沿用 test profile。
- `.env.example` 只說明欄位；應用程式不會自動載入 `.env`。同名環境變數會優先於可攜版 JSON 設定。
- 個人資料、已保存持倉、模型與憑證需由使用者明確設定與驗證。首次啟動不要啟用別人的 `PERSONAL_*` 或模型路徑。

建構設定與開啟程式會建立必要的資料夾並初始化日誌。第一次啟動後到「數據更新」查看來源狀態，再依所需官方資料來源補齊缺件。不要刪除既有 DB、WAL、SHM 或手動修表來處理空畫面。

## 排程不屬於 GUI 安裝步驟

安裝 source 或 portable GUI 不會註冊、啟用或替換 Task Scheduler action。新機排程需先依[機器啟動 Runbook](MACHINE_BOOTSTRAP_RUNBOOK.md)完成清冊和唯讀核對，再依[排程運維與搬機指南](SCHEDULE_OPERATIONS_AND_MIGRATION.md)處理各平台與專用 lane。

不要用舊的 [`register_baldr_scheduled_tasks.cmd`](../../scripts/scheduled/register_baldr_scheduled_tasks.cmd) 做移機註冊：它仍以 05:30 建立 `baldr-ml-direct-chain-maintainer`，與目前 checker 及 PowerShell helper 的 10:00 基準衝突。現行 [`register_baldr_scheduled_tasks.ps1`](../../scripts/scheduled/register_baldr_scheduled_tasks.ps1) 也只涵蓋定義的子集；它的 `DryRun` 輸出不是完整 desired-versus-observed 差異，也不能證明冪等。未完成全清冊唯讀核對、差異審閱與適用範圍授權前，不要註冊；完成後要逐項精確讀回。

## 安裝問題

- 安裝失敗時，記下 Python 版本、CPU 架構、套件名稱與完整錯誤型別，再查相容依賴；不要抄用其他電腦的 venv。
- 圖表空白時，核對 QtWebEngine／Matplotlib 相容性及來源是否有可用日期。
- 資料為空時，先確認啟動程式的同一 shell 中 `DATA_ROOT`、`OUTPUT_ROOT` 與 profile；畫面空白不等於來源中存在零值。
- 使用者操作見[快速開始](QUICK_START.md)與[完整操作手冊](APPLICATION_MANUAL.md)；source 版和可攜版的差異見[可攜版指南](PORTABLE_WINDOWS.md)。
