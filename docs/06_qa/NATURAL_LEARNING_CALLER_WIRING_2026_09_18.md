# Natural learning caller 接線 QA（2026-09-18）

本 QA 只記錄 `scripts/scheduled/run_daily_recommendation_learning.py` 對自然成熟度
resolver 的受控接線。沒有執行 production learning、正式 runner、scheduler trigger、
network refresh 或 SQLite 寫入；沒有把 replay 研究結果當成 natural credit。

## 接線契約

- candidate 與 active model 兩條 natural lane 都建立同一個
  `NaturalMaturitySessionResolver`，使用實際 `source_db` 與同一次
  `checked_clock`；沒有 resolver 時不在 caller 內 fallback 到舊 maturity 行為。
- annual cache 預設為
  `output/paper_execution_eod_replay/calendar_cache`，可由
  `--calendar-cache-path`、`NATURAL_MATURITY_CALENDAR_CACHE_PATH` 或既有
  `ML_FORWARD_CALENDAR_CACHE_ROOT` 明確覆蓋。
- temporary closure cache 預設為 `None`，只有
  `--temporary-closure-cache-path` 或 `NATURAL_MATURITY_TEMPORARY_CLOSURE_PATH`
  明確配置時才傳入；annual cache 不被當成 temporary closure 來源。
- 每日 payload 保存 resolver id/version、source DB path、annual／temporary cache
  path、完整 aware `evaluation_at`、clock source 與日期相符判定。
- `verify_active_model_evidence_payload` 的 `expected_db_path` 綁定實際 source DB，
  不接受 evidence 自報另一個來源。
- `--decision-date` 與實際 Taipei checked clock 日期不同時，natural candidate、
  active evidence 與 active performance 都保持 pending／skipped mismatch；不以
  synthetic 23:59 或當日 clock 授予 historical natural credit。既有 replay research
  流程仍可按其原契約運作。
- annual cache 缺失、過期或驗證失敗會由 service 保持
  `natural_maturity_session_waiting_for_calendar` pending，不轉成 emergency rollback。
  caller 不自動 refresh cache；freshness updater 是另一個明確排程／命令，未在本輪觸發。

## 隔離驗證

以下只選本輪新增的三個 caller／resolver cases，沒有宣稱整個
`test_daily_recommendation_learning_loop.py` 通過：

```text
.venv\Scripts\python.exe -m pytest tests\test_daily_recommendation_learning_loop.py -k "natural_maturity_caller_binds_source_clock_and_explicit_calendar_paths or natural_maturity_calendar_gap_stays_pending_without_credit" -q -o addopts= --tb=short
3 passed, 24 deselected, exit 0

.venv\Scripts\python.exe -m py_compile scripts\scheduled\run_daily_recommendation_learning.py tests\test_daily_recommendation_learning_loop.py
exit 0

.venv\Scripts\python.exe -m mypy scripts\scheduled\run_daily_recommendation_learning.py
Success: no issues found in 1 source file

git diff --check -- scripts/scheduled/run_daily_recommendation_learning.py tests/test_daily_recommendation_learning_loop.py
exit 0；無 whitespace error
```

三個 focused case 覆蓋：default／explicit annual 與 temporary path、source DB 與
aware clock 傳遞、日期不相符診斷，以及 missing／expired annual cache 在真 SQLite
TAIEX baseline 下保持 waiting/pending。raw command output 保存在
`output/qa/natural_learning_caller_20260918/pytest_caller_wiring.txt`、
`py_compile.txt` 與 `mypy_caller.txt`；`.pytest_cache` 權限 warning 不影響 exit 0。

daily loop 其餘 legacy/adoption fixture 沒有在本 QA 重新宣稱通過；它們需要依
strict source/proof contract 使用對應 fixture 與 trusted source anchor，由其 owner
另行收斂。

## 2026-09-18 唯讀自然進度觀測

於 `2026-09-18T11:40:23.507455Z`（台北 `19:40:23.507455+08:00`）以
SQLite URI `mode=ro` 加 `PRAGMA query_only=ON` 讀取正式資料庫；`query_only=1`。
`daily_prices` 與 TAIEX `market_indices` 的最大日期均為 `20260918`，表示市場資料
已到 9/18。正式 decision-evidence `latest_status.json` 仍是
`decision_date=2026-09-17`、`status=failed`；shadow learning 與 BankTaiwan
scheduled learning latest 也仍是 9/17，沒有讀到 9/18 的 capture／learning receipt。

BankTaiwan `recommendation_learning/captures` 目前 3 個 capture（9/15、9/16、9/17）。
以 `verified_source_database_for_capture` 與既有
`verify_prediction_capture_read_only` 重驗，source anchor 與 capture verifier 均為
**3/3 passed**，三者 source DB 都指向正式 `D:\Min\Python\Project\FA_Data\sqlite\twstock.db`。
這只證明現有 capture 的來源與格式可重驗，不代表 9/18 已新增 capture，也不代表
natural maturity、promotion 或 calibration credit 已成立。

原始觀測輸出保存於
`output/qa/natural_learning_progress_20260918/inspect_progress.txt`；本次沒有執行
runner、refresh、scheduler 或任何正式資料寫入。

## 限制與回滾

本輪沒有正式自然日 receipt，因此不能宣稱 resolver 已取得 20 個 official sessions、
natural outcome 已 ready 或 promotion gate 已升級。下一次合法排程才會實際讀取目前
工作樹的 caller；仍須以該次 immutable receipt 驗證 source、clock、calendar freshness
與 pending／ready 結果。

若 root review 不接受，回滾時只針對本輪已識別的 caller 接線與 focused-case hunks
製作精確反向 patch，保留同檔其他 agent 的變更；不以整檔 checkout 覆蓋 caller、
daily-loop tests、B resolver 或 C service，也不回滾正式資料與 scheduler。
