# Natural maturity calendar refresh wiring QA（2026-09-18）

本輪只做 calendar refresh 路徑與 strict resolver 的 bounded review。沒有觸發
Windows Task Scheduler、沒有呼叫正式 runner、沒有寫入 D 槽正式資料庫或正式
calendar cache。

## 現行 refresh 路徑

年度 cache 的既有 producer 是
`scripts/scheduled/run_official_calendar_cache_refresh_daily.py`，底層使用
`data_module/official_trading_calendar_cache.py` 的 create-only refresh。它只在
現有 annual cache 的 `expires_at_utc` 不涵蓋下一個 forward cutoff 時發 bounded
official request；成功後建立 immutable cache 與 receipt，失敗保留舊檔並
fail closed。`scripts/scheduled/run_ml_allocation_forward_daily.cmd` 已把這個
refresh 當成 forward child 前置步驟；Paper isolated path 也有自己的同 root
calendar refresh receipt。

本機既有 read-only status
`output/v4_ml_forward_scheduler/calendar_cache_refresh/latest_status.json` 的
觀測時間為 `2026-09-17T23:15:02.193862Z`，狀態是
`cache_valid_for_forward_horizon`。它選到的 cache 為
`output/paper_execution_eod_replay/calendar_cache/`
下 2026-09-14 capture，`expires_at=2026-09-21T23:15:03.532140Z`，
`valid_count=1`、`invalid_count=1`；9/7 舊檔過期但沒有被當成有效來源。這證明
既有 refresh 已在共用 root 運作，並非本輪新增一條重複 refresh caller。

05:40 `baldr-forward-outcomes-daily` 與 05:45
`baldr-recommendation-calibration-learning-daily` 的 CMD caller 本身沒有再發
refresh request，只把既有 cache root 傳給 outcome／natural learning consumer。
這是對共用 refresh receipt 的 dependency；cache 缺失、過期、竄改時 consumer
仍保持 `waiting_for_calendar`／fail closed，不把過期檔當 valid。repository 的
registration plan 標示這兩個 task enabled 且維持 05:40→05:45 順序；本機
`Get-ScheduledTask` 與 `schtasks /Query` 讀回分別受到 Access denied／找不到
task path，故實際 host 的 Enabled、LastRun、NextRun 不能由本輪證據宣稱。

## 本輪修正

`data_module/natural_maturity_session_resolver.py` 原本以 lexicographic
ascending 後取前 64 個 annual immutable 檔案。當同年度檔案超過 64 個時，舊檔
可能佔滿候選窗口，新 capture 永遠不會被 loader 讀到，即使新檔本身有效。

現在 bounded discovery 以檔案 mtime/path 取最新 64 個候選；mtime 只用來限制
掃描範圍，不是 calendar authority。每個候選仍完整通過 bytes、content hash、
來源、coverage、expiry 驗證，最後由 `_load_annual` 以 verified
`captured_at` 選擇真正來源。這保留 exact session、expiry 與 fail-closed 契約。

新增隔離 regression：建立 64 個已過期舊檔與第 65 個有效新檔，確認候選仍維持
64 個且包含新檔；resolver 取得 `ready`、endpoint `2026-09-08`，並以
`verify_session_proof(expected_db_path=...)` 重讀通過。temporary closure 的
候選語意沒有在本輪改動。

## 驗證

```text
.\.venv\Scripts\python.exe -m pytest tests/test_natural_maturity_session_resolver.py -q -o addopts=
12 passed, 1 warning

.\.venv\Scripts\python.exe -m py_compile data_module/natural_maturity_session_resolver.py tests/test_natural_maturity_session_resolver.py
exit code 0

.\.venv\Scripts\python.exe -m mypy data_module/natural_maturity_session_resolver.py
Success: no issues found in 1 source file
```

raw output：
`output/qa/maturity_calendar_refresh_20260918/pytest_resolver_annual64_final.log`、
`py_compile_final.log`、`mypy_resolver_final.log`。pytest 的唯一 warning 是既有
`.pytest_cache` 權限，沒有測試失敗。
