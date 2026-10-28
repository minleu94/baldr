# Watchlist MainWindow 首次候選快照背景載入 QA（2026-10-27）

## 範圍與行為

MainWindow 建立的 Watchlist 先完成基本介面，再由 `TaskWorker` 背景讀取唯讀候選 review snapshot（相容服務才讀 `get_stocks()`）及展示用股票名稱；snapshot 和名稱讀取都不操作 Qt widgets。GUI 執行緒收到結果後才建立表格模型與狀態。頁面在讀取期間顯示載入中，讀取錯誤清空候選模型並留在頁內；名稱查詢失敗時沿用收藏名稱，沒有名稱可用時顯示「名稱未提供」。

MainWindow 路徑忽略舊 generation，關閉時以合作式、非等待方式取消工作並拒絕晚到套用。直接建構 `WatchlistView` 的預設仍同步；手動刷新及現有寫入後同步 reload 也維持原行為。候選 snapshot、revision、保存格式、來源身份與正式資料均未變更。

## 驗證

| 驗證 | 結果 | 證據 |
|---|---|---|
| Watchlist layout／初次載入測例 | 12 passed；含真實 `TaskWorker` 背景執行緒、GUI signal 套用、generation 失效、關閉合作取消、錯誤 inline 與名稱 fallback | `output/tasks/watchlist-startup-snapshot-async-20261027-01/evidence/single_owned_qa_ace6b66a5c0f4f5aa10bf3868af8e1d7/receipt.json`，SHA-256 `2825f966c8b6e9f211c6a03577de853c66f88306f2e256a702b17a8dcfd4df78` |
| 必要 Workbench UI regression | 97 passed | `output/tasks/watchlist-startup-snapshot-async-20261027-01/evidence/single_owned_qa_7471edafee25492996595865ea83a808/receipt.json`，SHA-256 `13c7863e506a9e77d22edb45ed452643bdd8ad05b9ea527794c37cd0946eecaa` |
| Update tab validator | 25 passed／0 failed／4 skipped | 同上；原始 stdout 保存在同目錄 `stdout.log` |
| 全指定應用範圍 mypy | **blocked**：`data_module/mops_t164_pdf_disposition_bridge.py:411` 有既存語法錯誤 `Unexpected character after line continuation character`，mypy 因而未能檢查全範圍 | 同上；沒有改動該檔 |
| 變更檔 targeted mypy | 2 個來源檔無問題；使用 `--follow-imports=skip`，不能取代全指定應用範圍 mypy | `output/tasks/watchlist-startup-snapshot-async-20261027-01/evidence/single_owned_qa_01d6a18eea2e4570ad8abeca2d51f44f/receipt.json`，SHA-256 `d167e2835c1649a205c165be2ad18e605377e25bb31c02761a4cb5c1a4ffae5d` |
| 修改 Python 檔 `py_compile` | 3 個變更檔通過 | Workbench regression wrapper 同上 |
| 變更檔 `git diff --check` | 通過 | Workbench regression wrapper 同上 |
| 最終 context、修改文件 `git diff --check` 與新增 QA 文件／索引 document-control check | context、diff check 通過；QA 文件與索引 scoped check 0 errors | `output/tasks/watchlist-startup-snapshot-async-20261027-01/evidence/single_owned_qa_7c830d6df2fb474f9a64d96a7ccefefe/receipt.json`，SHA-256 `d73ed93ccbae25aa3356ced3b65e0363745f4ec8070420c9707afb5214e2ae62` |
| 所有本任務文件 document-control check | 6 errors；逐項均已存在於 `HEAD`：Snapshot 有 4 個既存錨點缺件，decision/research architecture 與 Watchlist 手冊各有 1 個既存 `output/` 越界連結。新 QA 文件／索引的 scoped check 通過 | `output/tasks/watchlist-startup-snapshot-async-20261027-01/evidence/single_owned_qa_59e3686d41e044f080f6dcc90d422e18/receipt.json`，SHA-256 `700e5e853d49659581140e026191f721fb564881147f93197562c02943a1fdfe`；原始輸出 `document_control_check.json` 保存於同一 evidence 目錄 |

每次執行皆使用 task evidence 中的 root runner；Windows Job 的 kill-on-close、12 個程序上限及 8 GiB committed-memory 上限讀回成功，啟動前可用 RAM 高於 8 GiB，完成時剩餘 Job 程序為 0，無強制清理。工作樹範圍外既有錯誤未修改。

## 尚未驗證與資料界線

未執行完整 MainWindow 原生 GUI／Owner UAT，也未量測實際啟動延遲；受控測例只證明服務讀取在線程外執行、結果由 GUI thread 套用。既有 `_refresh_storage_status()` 等其他初始化讀取仍可能同步執行。候選資料讀取仍沿現有 service 與 snapshot 語意；本切片不寫正式資料、不改 Gate、PIT、ML 或來源資格。
