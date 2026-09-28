# 個人研究 UI 隔離啟動器（2026-09-28）

## 用途與界線

`scripts/qa_personal_research_ui.py` 供受控 QA 使用：以已固定的 repo-ignored SQLite snapshot 建立一份可寫複本，再以真正的 `ui_qt.main.MainWindow` 啟動個人研究畫面。它不建立預製推薦結果、不啟動排程、不呼叫訓練或升級流程；`prepare` 子命令不建立 `QApplication`，也不顯示視窗。只有明確執行 `launch` 才會顯示主視窗。

固定來源為 `output/qa/personal_daily_product_20261006/real_source_validation_runs/formal_source_snapshot_v2/twstock.db`，SHA-256 `c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08`，長度 3,827,728,384 bytes。旁邊的 `snapshot_receipt.json` SHA-256 必須為 `15e1f66f496865f55f97e6e76d1bb291cb1cb842d42d29ee42b7e8905f5b0e83`，且 receipt 內 schema、23 張資料表、逐表筆數及 SQLite `PRAGMA quick_check=ok` 必須相符。這是 quick check，不是完整 `integrity_check`。程式拒絕任意 DB 路徑或不符的 receipt。

程式會把來源以一般新檔案複製到新的 QA run root，讀回整份 working DB SHA，並以唯讀 SQLite 連線重驗 schema 與逐表筆數。來源和目的檔案身分必須不同；目的檔案不得是 symlink 或 hardlink。副本路徑由 `TWStockConfig` 真正解析後核對，固定為 `PROFILE=test` 下的 `run_root/data/_test/sqlite/twstock.db`。產品輸出根為 `run_root/output/_test`，個人 policy 檔固定為 `run_root/app_config/personal_use_policy.json`。

個人候選清冊根必須以絕對路徑明確提供，且其 `recommendation_learning` 子目錄已存在並位於 repo-ignored `output/qa/` 之下。它可與產品 run root 同在 `output/qa/` 下，但不得與 run root、固定 snapshot 路徑重疊或互為祖先；正式 D: 路徑會在檢查檔案前即被 QA-root 邊界拒絕。啟動前會在最多 10,000 個項目、單檔 512 MiB、總量 2 GiB 範圍內計算唯讀樹 pin；UI 關閉後再次計算並核對。此 launcher 不會在 learning root 寫入檔案。候選內容及 runtime eligibility 仍由個人候選清冊與既有 consumer 驗證，樹 pin 不取代它們。

產品資料、輸出、policy 與收據工作目錄均限制在 `output/qa/personal_daily_product_20261006/` 內，產品 DB 是固定 snapshot 的獨立可寫複本；learning root 是另一個 repo-ignored QA 子樹。launcher 本身不把 `D:/Min/Python/Project/FA_Data` 設為執行根，也不開啟該正式 DB。不過推薦頁的「個人研究來源 SQLite」欄位是另一個明示路徑選擇器，launcher 不會技術性鎖住它；本次隔離驗收必須在該欄位選用固定 `formal_source_snapshot_v2/twstock.db`，不得選 D: 正式 DB 或可寫的 working copy。其他明示路徑即使能通過一般唯讀來源檢查，也不屬於本次固定快照驗收。首次準備需保留至少 snapshot 長度加 1 GiB 空間。失敗的 prepare 可能留下不完整 run root，程式不會自動刪除；請另選新的 run root，不要覆寫或連結舊目錄。

此入口本身不保證可見操作驗收。`launch` 命令雖會顯示標題為「個人研究 QA｜隔離資料工作區」的真正 MainWindow，但選擇候選、確認 policy、操作推薦及保存讀回仍須由獨立操作者以可見桌面完成；`prepare`、pytest 或 offscreen 測試都不算 native UI 通過。操作者只在推薦分析流程內進行核驗，不按資料更新或其他會連外的操作。

## 操作方式

先設定三個互相隔離的絕對路徑。`run-root` 必須是全新的目錄；`learning-output-root` 是位於共同 repo-ignored `output/qa/` 下的候選 shadow output root，其下必須已存在 `recommendation_learning`，並與 run root、固定來源 snapshot 路徑分離。若 fit/replay 正在寫入候選目錄，請等它自然結束後再執行 `prepare`；launcher 會將候選樹 pin 到 manifest，後續若內容改變就拒絕啟動。policy 路徑必須固定在 run root 的 `app_config` 下。

```powershell
$repo = 'C:\Projects\PythonProjects\technical_analysis'
$run = Join-Path $repo 'output\qa\personal_daily_product_20261006\personal_research_ui\run_20260928_01'
$snapshot = Join-Path $repo 'output\qa\personal_daily_product_20261006\real_source_validation_runs\formal_source_snapshot_v2\twstock.db'
$snapshotReceipt = Join-Path (Split-Path $snapshot) 'snapshot_receipt.json'
$learning = 'C:\Projects\PythonProjects\technical_analysis\output\qa\pc-fit-v7'
$policy = Join-Path $run 'app_config\personal_use_policy.json'
```

第一步只準備隔離複本，不開 UI：

```powershell
.\.venv\Scripts\python.exe scripts\qa_personal_research_ui.py prepare `
  --run-root $run `
  --source-snapshot $snapshot `
  --snapshot-receipt $snapshotReceipt `
  --learning-output-root $learning `
  --policy-config-path $policy
```

`prepare` 成功時會列印 `manifest_path`、working DB SHA、SQLite table count 與 `learning_root_tree_sha256`；逐項核對這些摘要與 `receipts/isolation_manifest.json`、三個實際隔離根都符合預期後，才明確啟動可見 UI：

```powershell
.\.venv\Scripts\python.exe scripts\qa_personal_research_ui.py launch `
  --run-root $run `
  --learning-output-root $learning `
  --policy-config-path $policy
```

`launch` 會重新驗證來源 snapshot receipt、QA working DB bytes/schema/逐表筆數、`PROFILE=test` 實際落點、policy 路徑及 learning tree pin；任一不同就停止，不會退回環境預設正式根目錄。關閉 UI 後會新增 `receipts/visible_mainwindow_*.json`，記錄程序退出碼與 learning tree 前後 pin。只有 working DB bytes 仍與固定 snapshot 完全相同，才可對同一工作區再次執行 `launch`。UI 初始化或操作若已改動 working DB，launcher 會拒絕重啟；保留舊 run 及收據，另用全新的 `run-root` 執行 `prepare` 和 `launch`，不要覆寫或修補舊工作區。policy 檔可在此 QA run 內由 UI 建立或更新，其他路徑不會被用來補回 policy。

## 測試與限制

已登錄的 `tests/test_qa_research_journey_subprocess.py` 含此入口的 tiny SQLite 複製、PROFILE=test 實際 DB 路徑、create-only、hash mismatch 與 learning tree pin 測試。這些測試只使用暫存資料，不複製 3.8 GiB snapshot、不匯入 Qt 視窗，也不讀寫正式資料。2026-09-28 的實測中，`run_02` 首次建立 MainWindow 後 working DB 已偏離 snapshot pin，因此後續對該 run 的 `launch` 被正確拒絕；另建的 `run_03` 已成功啟動且程序持續執行。可是 CUA 的 apps/windows 清單為空，未能點按或操作視窗，所以狀態仍是 `NOT_ACCEPTED_NATIVE_INTERACTION`，不視為原生 UI 操作通過。
