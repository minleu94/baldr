# Freshness 與 Quick 收據身分綁定（2026-10-01）

## 目的與界線

Freshness probe 原先只讀取 Quick 的 `status` 與完成時間，並以日期／時間判斷新鮮度；它沒有把該次終態綁到 Quick 的 `run_id` 或 append-only history。這次加入唯讀的收據身分 sidecar，讓 Freshness 輸出能指出它讀到的 Quick status bytes、終態 run 與 history record 是否一致。

綁定狀態 `verified` 的範圍明確是 `terminal_receipt_identity_only`：它只證明讀到的 status 與同一 run 的唯一終態 history record 相符，不證明該 run 寫入 DB、不證明資料已可用、不代表 PIT 可得性，也不授予 Formal credit。Freshness 仍是獨立的唯讀 DB／交易日檢查，不成為 Quick 的相依任務。

綁定失敗或舊 Quick payload 缺少 `run_id`／history 時，輸出標為 `unverified` 並附原因；原有 Freshness warning、Quick failed 判讀、status 時間與 `available_at` 規則維持不變。即使 failed Quick 的收據身分可驗證，Quick 仍維持 failed 與原有品質警告。Probe 只讀取一次 Quick status bytes，從同一 buffer 計算 SHA-256 並解析；不追讀被替換的 `latest_status.json`，也不等待較新的 run。

Probe 僅接受 Quick status 的固定 canonical 路徑，以及該 status 同目錄的 `history.jsonl`；不依 status payload 指定的任意路徑開檔。status/history 皆使用 strict JSON 解析，拒絕重複欄位及 NaN／Infinity，並將過深內容轉成 unverified 診斷。status 上限為 2 MiB；history 使用現有 8 MiB 上限，另限制每列 512 KiB 與 10,000 列。讀取會檢查路徑無 symlink/reparse point、regular single-link 檔案及讀取前後檔案身分。Freshness PowerShell wrapper 明確把 canonical Quick status path 傳給 probe。

## 變更範圍

- `scripts/scheduled/data_freshness_probe.py`：新增 bounded same-buffer status snapshot、history record 重建與比對、run/task/status/timestamp 驗證，以及 `checks.data_update_quick_receipt_binding` 輸出。未改 DB、可得性、Freshness maturity 或 Formal 計算。
- `scripts/scheduled/run_daily_data_freshness_check.ps1`：傳入既有 Quick `latest_status.json` 固定路徑；未觸發或變更排程。
- `tests/test_scheduled_data_freshness_probe.py`：涵蓋 latest 在讀取後被替換、failed Quick、legacy 缺件、Quick 輸出目錄缺失、history tamper、任意 history path、status/history/row 大小上限、同 run 重複終態、status/history 重複欄位與非有限數、過深 JSON 及 wrapper 路徑。

## 驗證

在 repository 工作副本執行：

```powershell
.venv\Scripts\python.exe -m pytest tests\test_scheduled_data_freshness_probe.py -q -o addopts= -p no:cacheprovider -rs
.venv\Scripts\python.exe -m py_compile scripts\scheduled\data_freshness_probe.py tests\test_scheduled_data_freshness_probe.py
.venv\Scripts\python.exe -m mypy scripts\scheduled\data_freshness_probe.py
git diff --check -- scripts/scheduled/data_freshness_probe.py scripts/scheduled/run_daily_data_freshness_check.ps1 tests/test_scheduled_data_freshness_probe.py
```

結果：`25 passed, 1 skipped`；Python 語法檢查、probe scoped mypy 與上述檔案的 `git diff --check` 通過。唯一 skip 是 `test_quick_status_link_is_rejected_before_read`：此 Windows 環境建立 symlink 時回報 WinError 1314（呼叫端未持有建立 symlink 所需權限）；其餘 bounded read、file identity、strict JSON 與 tamper cases 已執行。

## 隔離正式輸入唯讀驗收

Root 審核核准後，於實際時鐘 2026-09-30 23:56:40.295099 UTC（Pacific 16:56:40.307225）執行 probe，結束於 23:56:41.953109 UTC（Pacific 16:56:41.953109）。執行沒有日期／時鐘注入。Python 以 `-X utf8 -` 啟動，Freshness probe 以 `sqlite_journal_mode=wal`、`sqlite_query_only=1` 讀 DB；在 calendar 模組的 `safe_request` 網路 fallback 上安裝拒絕 stub。實際 fallback 次數為 0。TWSE 年度快取在 probe 前以真實 UTC 再驗證有效期與 file hash，probe 的 10 筆 calendar records 均回報同一個 pinned cache hash；快取檔在前後 fingerprint 一致。

Quick 綁定結果為 `verified`、`quick_terminal_receipt_and_append_record_match`，範圍仍只限 `terminal_receipt_identity_only`。讀到的 Quick `run_id=20260930-32560`、status=`passed_with_warnings`、status bytes=358,115、SHA-256=`sha256:090b51920e6523570730e1b46ac592f0879a63631661817cd558042301775180`；history `record_id=duh_fb4c13ceeed0c2ddb36a8692`、record SHA-256=`e7c3997f34717c147a08578290adf656e806aa560f5a3f91d50840b0258e7c93`。`db_write_attribution=false`、`historical_pit=false`、`formal_credit=false`。

Probe exit code 為 0，整體 Freshness 狀態為 `degraded`，沒有 errors。完整 warnings 保留為：

- `monthly_revenue_expected_period_not_available`
- `quarterly_statement_expected_period_not_available`
- `source_freshness_degraded:fundamental.current_monthly_observations`
- `source_freshness_degraded:fundamental.current_statement_observations`

這些 warnings 屬於本次實際輸入的 fundamental period／source freshness 判讀；Quick identity binding 已通過，未清除上述資料品質警告。年度 cache 僅涵蓋計畫性年曆。現行 wrapper 沒有設定 temporary-closure path，本次 `temporary_closure_scope.status=not_captured`；不把這次日曆結果擴大解讀為臨時休市事件已完整覆蓋。repository cache 目錄另有 2026-07-10 closure cache，3,368 bytes、mtime `2026-09-07T20:00:50.478433Z`、SHA-256=`e547914241a29eb9e8b722b236159e583e95bceed14a0bb54b0c08c268681722`；該事件不在本次 10 個交易日區間，也未作為本次輸入。

實際輸入與前後檢查如下。所有列出的 fingerprint 均相同；DB 只比較 size／mtime 與既有 WAL／SHM 狀態，沒有為 3.8 GB DB 計算 hash。Phase3C candidate DB 是現有環境唯讀設定，不是本次輸出目標。

| 輸入 | 執行前 | 執行後 |
| --- | --- | --- |
| Data root `D:\Min\Python\Project\FA_Data` | 目錄，mtime `2026-08-14T23:06:44.694009Z` | 相同 |
| Output root `D:\Min\Python\Project\FA_Data\output` | 目錄，mtime `2026-09-30T19:10:57.132502Z` | 相同 |
| Quick latest status | 358,115 bytes，mtime `2026-09-30T11:34:06.259969Z`，SHA `090b5192…01775180` | 相同 |
| Quick `history.jsonl` | 111,363 bytes，mtime `2026-09-30T11:34:06.249968Z`，SHA `2c2e7d5b…4935bf46` | 相同 |
| 舊 Freshness latest status | 95,104 bytes，mtime `2026-09-30T12:00:20.783903Z`，SHA `8e52aa9d…564bff1` | 相同 |
| Production DB `D:\Min\Python\Project\FA_Data\sqlite\twstock.db` | 3,838,111,744 bytes，mtime `2026-09-30T12:25:58.344915Z` | 相同 |
| Production DB `-wal` / `-shm` | 分別 964,112／32,768 bytes；mtime `12:40:06.131395Z`／`23:00:21.460722Z` | 相同，兩檔仍存在 |
| Phase3C candidate DB `D:\Min\Python\Project\FA_Data_candidate\phase3c_candidate.db` | 414,334,976 bytes，mtime `2026-09-30T11:22:39.866890Z` | 相同 |
| Candidate DB `-wal` / `-shm` | 均不存在 | 仍不存在 |
| TWSE 2026 annual cache | 73,601 bytes，mtime `2026-09-28T23:15:03.967797Z`，SHA `cecb797f…1ad90e1` | 相同 |

TWSE annual cache 的完整輸入路徑為 `C:\Projects\PythonProjects\technical_analysis\output\paper_execution_eod_replay\calendar_cache\twse_holiday_schedule_2026_20260928T231502681965Z_30badfe7f239.json`，capture／available time 為 `2026-09-28T23:15:03.965191Z`，expiry 為 `2026-10-05T23:15:03.965191Z`。資料與輸出根目錄的環境變數 `DATA_ROOT`／`OUTPUT_ROOT` 當時皆未設定；`PHASE3C_CANDIDATE_DB_PATH` 指向上表 candidate DB。

## 隔離輸出與 runner 診斷

唯一成功驗收輸出位於 `C:\Projects\PythonProjects\technical_analysis\output\qa\freshness_quick_binding_preflight_76d4b930`：

- `status.json` 與 `probe.log` 各 96,289 bytes，SHA-256 均為 `c1ba517580bb040f8e0b4fdf8bea83a176adb925433cc2a3be8b89d7852ebfd6`。
- `stdout.txt` 94,133 bytes，SHA-256=`937d344fccb6428d7a9b556644aed859773e84ee6beb60c9021b61fe5c3e52ac`。
- `invocation.json` 8,181 bytes，SHA-256=`0820f5aaa332589ae1723a16916eba30c1bb3fda2e56ef24b5553ab956ec01c0`。
- `receipt.json` 19,888 bytes，SHA-256=`fbf891ad521344d68ccff57dbd7482a52eb5e5a0a6fcf7b0c6f8add8c669bdfe`。

第一個 runner 在 probe、calendar cache 驗證、Quick/history byte read 與 DB 連線前，因外層 inventory helper 把 `os.stat_result` 當成具有 `is_dir` 屬性的 Path 物件而 guard-abort，例外為 `AttributeError: 'os.stat_result' object has no attribute 'is_dir'`。沒有為該次失敗偽造 invocation／receipt；原隔離根 `output/qa/freshness_quick_binding_preflight_e9c21dfe` 保留為空目錄。修正 helper 後，以新 UUID 的成功輸出根重跑；另用小型離線 fixture 驗證相同 metadata helper 的穩定 snapshot 前後相等、尺寸變更會被偵測，且目錄 stat 不會誤讀檔案 size。此次沒有觸發或修改 Task，沒有寫入 Quick/history、兩個 DB、WAL/SHM 或 calendar cache；本報告不宣稱 DB attribution、PIT 或 Formal credit。
