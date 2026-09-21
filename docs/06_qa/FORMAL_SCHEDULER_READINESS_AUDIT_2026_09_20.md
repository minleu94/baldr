# Formal Scheduler Current Readiness Audit — 2026-09-20

本 QA 是一次 current-only、唯讀的正式 scheduler readiness 檢查。觀測時間為 `2026-09-20T15:05:49+08:00`，`decision_date` 取同一個實際 Asia/Taipei aware clock 日期 `2026-09-20`。它不代表下一個交易日已通過，也不改判 2026-09-18 的歷史 decision。

## 執行邊界

檢查直接呼叫 `data_module.recommendation_calibration_source_contract.inspect_source_contract()`（`data_module/recommendation_calibration_source_contract.py:1913`），輸入為正式 `D:\Min\Python\Project\FA_Data\sqlite\twstock.db`、正確的 `D:\Min\Python\Project\FA_Data_Shadow` source artifact root、正式 caller 使用的兩個 authorized output roots，以及 7 個 eligible symbols：`1103, 1436, 1437, 1438, 1529, 1560, 1569`。沒有呼叫 `write_source_contract()`、learning CLI 或 scheduler；沒有寫入 formal DB、formal output、capture、pointer 或 receipt。

compact 原始結果保存在 [current readiness JSON](../../output/qa/formal_scheduler_readiness_20260919/current_readiness.json)，可重現 probe 在 [readiness probe](../../output/qa/formal_scheduler_readiness_20260919/readiness_probe.py)。第一次普通 sandbox `mode=ro` 開啟 3.6 GB SQLite 回報 `OperationalError: unable to open database file`；同一 `mode=ro`、未使用 immutable／nolock、沒有 writer 的唯讀權限檢查成功讀取 `HistoricalRawSnapshot`。這是執行環境 ACL 差異，不是以 bypass 取得資料。

## 呼叫鏈與已讀證據

正式路徑為：

`scripts/scheduled/run_recommendation_calibration_learning.cmd` → `scripts/scheduled/run_daily_recommendation_learning_pipeline.py` → `scripts/scheduled/run_daily_data_update_quick.py` → `scripts/scheduled/run_daily_recommendation_learning.py`。

BankTaiwan lane 由 `scripts/scheduled/run_banktaiwan_recommendation_learning_daily.cmd` → `scripts/scheduled/run_banktaiwan_recommendation_learning_daily.py` 啟動；該 runner 的 source policy（`scripts/scheduled/run_banktaiwan_recommendation_learning_daily.py:584-598`）明確標示 `technical_refresh_in_this_task=false`，只讀取既有 quick publication。daily learning 的 source artifact root 接線在 `scripts/scheduled/run_daily_recommendation_learning.py:1336-1337,1525-1537`，live capture gate 在 `scripts/scheduled/run_daily_recommendation_learning.py:2668-2733`。

quick runner 已有計算 witness reuse 與 publication：`scripts/scheduled/run_daily_data_update_quick.py:804-822` 讀取 verified witness，`scripts/scheduled/run_daily_data_update_quick.py:927-945` 發布 technical receipt。正式 quick 最新 receipt 是：

`D:\Min\Python\Project\FA_Data\output\scheduled\technical_indicator_publication\2026-09-18\1a73fe8c06df13f9\receipt.json`

它的 `run_id=20260919-2092`、`available_at=2026-09-19T04:30:45-07:00`、source window 為 `2026-09-15..2026-09-18`、technical step `passed`、computation evidence `verified`；technical output 為 7,826 rows、1,975 symbols，7 個 eligible symbols 均存在。receipt file SHA256 為 `05ed2faa0f8a19e5efaaebfc133a9cda53fc63e6c92feb4134e5699fa3a1ff57`。

## Current readiness 結果

source receipts 的日期、時間 cutoff、symbol coverage、receipt lineage 與 7-row prospective feature snapshot 均可讀且通過：`missing_source_symbols=[]`、`missing_technical_symbols=[]`、`technical_source_receipt_lineage_verified=true`、`prospective_feature_snapshot_verified=true`。

目前真正未通過的是 technical output value binding。已發布 receipt 宣告的 technical output 是：

| 項目 | 已發布 receipt | current formal DB 唯讀 snapshot |
| --- | --- | --- |
| source DB | `D:\Min\Python\Project\FA_Data\sqlite\twstock.db` | 相同 |
| 日期範圍 | 2026-09-15 至 2026-09-18 | 相同 |
| rows | 7,826 | 7,826 |
| covered symbols | 1,975，7 個目標均存在 | 1,975，7 個目標均存在 |
| content hash | `sha256:da98d5962839b16e450ed31aacb969a003fc47b7e58e386a1556a62c6481879d` | `sha256:271979ddf865e383fa528e3259472f5868ee82fd82da00c21d39240d852e07f7` |
| rows hash | `sha256:2f67730ee109f7a586111e624e88b328e4ba08b6829feb465579b436c4c40f9e` | `sha256:830cdf5af003c43d07b25ce32425cd69b193070c8fee23db6731e5d246b94620` |

因此 current proof 的 `technical_output_value_binding_verified=false`、`technical.prospective_available=false`，price-up lane 的 prospective blocker 仍是 `technical_prospective_source_not_ready`。formal technical contract 的 `verified=false`（`recommendation_source_contract_missing`）是另一個 formal lane 狀態；corporate adjustment custody 的 prospective proof 為 true，但 formal verified 仍是 false，不能把兩者混成同一個 technical source blocker。

正式 DB 的檔案 mtime 為 `2026-09-19T05:53:28-07:00`，晚於 publication `available_at`；這只能證明 DB 檔案後來被寫過，不能單獨證明 technical table 是重算、哪些 rows 改變，或是哪個 writer 造成 hash drift。下一個 bounded audit 才會沿已知 quick/background status 與 writer path 追查，不在本 QA 內重發布或重算。

## 結論與邊界

本次 proof 證明 source receipt 與 7-symbol coverage 已可被正式 read-only contract reader 找到，也證明目前不能把該 receipt 當成可供自然 capture 的 current technical binding。必須先釐清 receipt 後的 technical output hash drift，再由實際 scheduler 以當下 checked clock 重新建立 source contract；本 QA 不預測下一交易日結果、不回填 2026-09-18、不產生 natural credit。

`f48908a1` 的背景 publication 修正仍是 `ui_qt/views/update_view.py:4049` 的 UI background route；它不能被描述成已改動正式 scheduler。正式 scheduler 是否能在下一個實際交易日完成 current binding，仍以新的 quick receipt、source contract 與 live capture artifact 為準。

## 2026-09-21 bounded technical child routing follow-up

本段記錄 hash drift 根因調查後的最小 scheduler routing 修補；它不回填 2026-09-18，也沒有在正式資料上重算、重發布或改寫 DB。直接證據仍是 9/19 shadow caller 的 technical child 與正式 `DB_PATH` 共用，但 `OUTPUT_ROOT` 指向 shadow；同一 caller 的 quick child 因而可能在正式 quick receipt 後再次取得 technical writer。`f48908a1` 只涵蓋 UI background route，未涵蓋這條 scheduler child routing。

`run_daily_recommendation_learning_pipeline.py:164-342,588-728` 現在只把 technical child 的 custody root 固定到與 `data_root` 對應的 `<data-root>/output`，並同步 child 的 `OUTPUT_ROOT`、`RECOMMENDATION_LEARNING_OUTPUT_ROOT`、`--output-root`、`--formal-output-root` 與 `--status-path`；official、snapshot、learning 仍使用 caller 的 shadow output。`source_db` 若不是 `<data-root>/sqlite/twstock.db`，technical child 在呼叫 quick writer 前 fail closed。quick 的既有 canonical capacity lock 仍由 quick runner 依 formal output root 選取，pipeline 沒有另造 lock 名稱。

正常 refresh 不以既有 receipt 作為啟動前置條件：formal latest status 只提供 bounded window hint。只有在 `start <= end`、`end == caller decision_date`、available time 不在未來且 Asia/Taipei 日期相符，並由既有 `reuse_verified_technical_computation_receipt()` 重新驗證成功時，才沿用該多日 window；missing、stale、future 或驗證失敗均回到 caller 的 decision-date refresh，保留原本的 recovery 語意。明確 `--skip-technical-refresh` 同樣必須通過 current-day window 與既有 reuse verifier，不能以任意舊 receipt 宣稱 skip 成功。

隔離 QA 使用既有 source-contract fixture 建立真實三日 computation witness，確認 `pipeline.main` 的 quick child arguments/window、formal env/status path 與其他 children 的 shadow env；另驗證 missing/stale receipt 回落至 2026-09-21、custom DB 不呼叫 quick writer 且 DB bytes/mtime 不變。`tests/test_recommendation_calibration_contract_guards.py` focused suite 為 20 passed，`tests/test_recommendation_calibration_source_contract.py` 為 7 passed，兩個修改檔案均通過 `py_compile` 與 `git diff --check`。pytest 僅有既存 `.pytest_cache` 權限 warning；沒有執行正式 scheduler。

## 2026-09-21 ML forward integrity readback 可見性 QA

本輪是 ML forward failure 的診斷可見性修復，不是 Paper coordination 根因修復，也不宣稱 natural capture、eligibility、promotion 或 credit 已恢復。既有 2026-09-21 child immutable record 位於：

`output/v4_ml_daily_derived_shadow_real_v2/natural_date_shadow/records/50d056970168ac75b60274e54ecd6dadd7c412b72f5896fee70ef9798b8b53d7.json`

該 record 的實際結果已足以定位 blocker：

| component | immutable child 結果 |
| --- | --- |
| formal market SQLite | `source.database.unchanged=true`；唯讀 source date evidence 仍為 `mode=ro`／`query_only=true` |
| repo Paper state | `unchanged=false`、`integrity_verified=false`、`change_class=unaccounted_change`；`state_read_view_stable`、`trade_ledger_read_view_stable`、`preopen_receipt_valid`、`paper_state_write_scope_valid` 均為 `false` |
| Paper transaction ledger | `unchanged=true` |
| frozen release | `release_manifest.unchanged=true`、`required_files_unchanged=true` |

因此本次 `failed_read_only_integrity` 的根因範圍是沒有可驗證 preopen coordination contract 的 Paper state 變更；不能把它歸因於 formal DB、release、ledger 或 sidecar。parent 的 immutable receipt `output/v4_ml_daily_derived_shadow_real_v2/scheduled/ml_allocation_forward/receipts/20260921T003038098583Z-4260.json` 當時只保存 child status 與 stdout digest，沒有把 child 已存在的 component source 帶到 scheduler readback。

本輪 runtime slice 只重用 child 的既有 immutable source／record identity：child 將已計算的 stat `changed_fields` 與 frozen release hash 的 before／after／`which_changed` 留在既有 source record；parent receipt 增加 bounded `child_read_only_integrity` projection，保存 record path／hash、四個 component 的固定 guard 欄位、release hash 摘要與 post-deadline sidecar 摘要。完整 component details 仍以 child immutable record 為準，舊 receipt 不覆寫。sidecar 以 `classification=parent_post_deadline_shadow_sidecar` 且 `formal_integrity_guard=false` 分開保存；合法的 research sidecar hash 變化不會被當成 formal integrity violation。

本輪保留 child `returncode=1`、parent `blocked_child_exit`、原有 read-only／Paper coordination guard、scheduler dependency／timeout／credit 邊界；沒有執行 production child、scheduler、writer、DB 或 credit。Paper coordination 的 runtime 根因仍待另一個受控修補與驗收。

### 本輪驗證證據

既有 focused test 結果為 `41 passed`（pytest 僅有既存 `.pytest_cache` 權限 warning）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_daily_ml_allocation_derived_shadow.py tests/test_ml_forward_scheduled_wrapper.py -q -o addopts=
```

changed Python 與測試檔的 `py_compile` exit code 為 `0`：

```powershell
.\.venv\Scripts\python.exe -m py_compile scripts\run_daily_ml_allocation_derived_shadow.py scripts\scheduled\run_ml_allocation_forward_daily.py tests\test_daily_ml_allocation_derived_shadow.py tests\test_ml_forward_scheduled_wrapper.py
```

兩個 changed runtime scripts 的 targeted mypy 結果為 `Success: no issues found in 2 source files`：

```powershell
.\.venv\Scripts\python.exe -m mypy scripts\run_daily_ml_allocation_derived_shadow.py scripts\scheduled\run_ml_allocation_forward_daily.py
```

`git diff --check` 通過；Git 的 LF→CRLF 提示是既有工作樹換行警告，不是 whitespace error。

## 2026-09-21 Paper ledger schema readiness bounded QA

本段記錄 Paper EOD writer 的 schema 初始化／回讀路徑、fail-closed 邊界與一次受控 schema-only maintenance。修補前的正式 runtime 觀測是 `output/paper_execution_eod_replay/paper_trade_ledger.sqlite` 已有 8 筆 fill、尚無 `paper_trade_transitions` table；2026-09-21 03:58:09 PDT 重查 Task 為 `Ready`、相關 writer PID 為空、距下一次 task 約 121.8 分鐘後，才執行 maintenance。沒有執行正式 scheduler、formal DB writer、replay、capture 或 credit。

maintenance receipt 位於 [paper ledger schema repair receipt](../../output/qa/paper_ledger_schema_repair_20260921/20260921T105811703640Z_38b952cb/maintenance_receipt.json)，同一目錄保存 [before](../../output/qa/paper_ledger_schema_repair_20260921/20260921T105811703640Z_38b952cb/before.json)、[SQLite backup manifest](../../output/qa/paper_ledger_schema_repair_20260921/20260921T105811703640Z_38b952cb/backup.json) 與 [after](../../output/qa/paper_ledger_schema_repair_20260921/20260921T105811703640Z_38b952cb/after.json)；正式 caller 參數的 [bounded reader probe](../../output/qa/paper_ledger_schema_repair_20260921/20260921T110618198719Z_reader_probe_bounded/reader_probe.json) 另存於新目錄。SQLite backup 使用 source `mode=ro`，只呼叫 `ensure_paper_ledger_schema()`；canonical ledger 的 8 筆 fill row hash 與 aggregate 前後一致（aggregate `543b3ef581f75a084a2539be1bceda43f5fc2139acbab3399edb42a5680e0d34`），新建的 `paper_trade_transitions` 為 0 rows，`historical_transition_evidence_inferred=false`。formal DB 與 repository Paper state DB 的 pre/post signature 相同。

這次只把未來 writer 所需 schema 補齊，沒有補造舊 9/8 fills 的 transition evidence。正式 caller 參數的 bounded probe 於 `2026-09-21T11:06:18.198719Z` 以實際 `decision_date=2026-09-21` 執行；official calendar 與 preopen coverage 均通過，reader window 為 `2026-09-14..2026-09-21`（end exclusive），state 只有 9/14、9/18 兩個 snapshots，缺 9/15、9/16、9/17 的正式 session boundaries。該 current window 的 fills 與 transitions 都是 0，尚未進入 transition validation；reader 以缺 session boundary fail closed。舊 9/8 rows 的全歷史觀測不能當作 current window blocker；current window 與後續 ML readiness 必須使用正式 caller 參數另驗，沒有重跑 ML child 或追認 2026-09-21 decision。

focused pytest（涵蓋 legacy 8-row fixture、schema idempotence、malformed table、preview/no-fill 不寫入、empty queue/no-fill routing、錯誤 path、缺 table reader 與 fills-without-transitions reader）為 `73 passed`：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_paper_daily_execution_producer.py tests/test_paper_execution_isolated_scope.py tests/test_ml_allocation_shadow_evidence.py -q -o addopts=
```

exit output：`73 passed, 1 warning in 2.92s`；warning 是既有 `.pytest_cache` 權限提示。

changed runtime modules 的 mypy 為 `Success: no issues found in 4 source files`：

```powershell
.\.venv\Scripts\python.exe -m mypy app_module/paper_trade_ledger.py app_module/ml_allocation_shadow_evidence.py data_module/paper_daily_execution_producer.py scripts/scheduled/run_paper_execution_daily_isolated.py
```

changed Python 與測試檔的 `py_compile` exit code 為 `0`（無輸出）：

```powershell
.\.venv\Scripts\python.exe -m py_compile app_module/paper_trade_ledger.py app_module/ml_allocation_shadow_evidence.py data_module/paper_daily_execution_producer.py scripts/scheduled/run_paper_execution_daily_isolated.py tests/test_paper_daily_execution_producer.py tests/test_paper_execution_isolated_scope.py tests/test_ml_allocation_shadow_evidence.py
```

`git diff --check` 通過；Git 的 LF→CRLF 提示是工作樹換行提示，不是 whitespace error。focused pytest、mypy 與 py_compile 證據如上；maintenance receipt 另保存真實時間、backup、逐列 hash、schema readback 與外部 DB/state unchanged 結果。
