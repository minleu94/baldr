# V4 有效性與資料來源工程驗收（2026-09-08）

本輪完成的是可重播的工程底座與資料來源隔離，**不代表 V4 投資有效性已完成**。
自然前瞻觀測、成熟 outcome、正式三路輸入與 promotion 仍依
`docs/00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md` 的門檻累積。

## 本輪交付

### V4 cohort effectiveness read model

- 新增 `app_module/v4_effectiveness_evaluator.py` 與
  `app_module/v4_effectiveness_read_model.py`。
- 輸入依 `horizon_days`、`strategy_version`、`universe_id`、`cost_model`、
  `benchmark_id` 分 cohort；每個決策日獨立排序 top-k，不把日期、策略或成本政策混在一起。
- `ready` 才進成熟分母；`pending`、`missing`、未知狀態、缺 score／return 或衝突重複列均保守排除並留下 warning。
- Precision@K、hit rate、coverage 與平均值以整數 basis points 輸出；benchmark／industry coverage 以成熟列數揭露。
- read model 固定 `read_only=true`、`manual_review_required=true`、
  `production_scheduler_allowed=false`、`auto_trading=false`。

唯讀 CLI：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_v4_effectiveness.py --sample --format markdown
.\.venv\Scripts\python.exe scripts\inspect_v4_effectiveness.py --input <EVIDENCE_JSON_OR_JSONL> --format json --output <REPORT_JSON>
.\.venv\Scripts\python.exe scripts\inspect_v4_effectiveness.py --db-path <EVIDENCE_SQLITE> --window-days 5 --format markdown
```

`--db-path` 只以 SQLite `mode=ro`／`PRAGMA query_only` 讀取 `evidence_events` 與
`evidence_outcomes`；事件 metadata 沒有明確 `universe_id` 時保留 warning，不能用目前股票池猜測補值。
指定 `--window-days` 時，沒有該成熟 outcome 的事件仍會保留為 `missing`，不因
SQL 篩選而消失；同一事件的其他 `return_basis` 不會混入，預設只讀
`close_to_close_event_date`。事件若明確保存 `horizon_days`，可在未指定 outcome
時提供缺件 row 的 horizon；未宣告 horizon 會留下 warning 並維持無效 cohort。
大量相同的 row-level 輸入錯誤會以 `rows_<code>:<count>` 彙總，避免正式資料
缺欄時產生數千個重複訊息；未知狀態與 cohort 衝突仍保留明確 warning。

2026-09-09 以正式 D 槽資料做唯讀 probe：`evidence_events=51,866`、
`evidence_outcomes=0`，並觀測到事件沒有明確 `universe_id`，因此輸出為空 slices、
`no_valid_cohort_rows` 與計數 warning。這是目前 Evidence producer／outcome 尚未接通的
實際結果，不以現有股票池、replay 或 fixture 補值。

### FinMind 現金流候選

新增 `data_module/finmind_cashflow_candidate.py` 與
`scripts/fetch_finmind_cashflow_candidate.py`。FinMind 官方 Data API 與
`TaiwanStockCashFlowsStatement` dataset 的請求格式依官方文件；帶 token 的服務限制以
[FinMind Quick Start](https://finmind.github.io/en/quickstart/) 為準，執行器預設每小時 480 次，保留餘裕。

每列保存 `source_row_hash`、`observed_at`、`source_version`、科目代碼／名稱、季度與原始數值；
因 API 列沒有可驗證的官方公告／可得日，`available_date_candidate` 保持空白，
`eligibility=numeric_only`。候選只供與 MOPS 官方現金流量表交叉核對，不寫正式 SQLite、
availability mapping、ML PIT 或 scoring。批次必須明確指定股票，或以 `--all-raw-stock-codes --resume`
明確同意可續跑批次；token 不會輸出到報告。

### 備份、容量與每日更新

- 正式 SQLite schema／季度 statement／TPEX price／valuation／evidence migration 的備份改用
  SQLite online backup，完成 `quick_check` 後才以暫存檔原子替換；還原同樣走 online backup，
  避免 Windows 開啟讀者與 WAL 遺漏造成不一致。
- `run_daily_data_update_quick.py` 在任何網路或 SQLite writer 前取得與 Raw／Direct／OOC 共用的
  `output-root/release_v4/.ml_heavy_chain.lock`，再以中央 200 GiB reserve 做容量 preflight；忙碌或不足即 fail closed。
- 每日更新會在 `PHASE3C_CANDIDATE_DB_PATH` 明確設定時執行 institutional／credit（週一加最新 TDCC）
  candidate-only 更新；未設定時以 skipped 明示，不猜測資料庫路徑。status／history 保存 lock、candidate path、
  reservation 與 preflight payload。

## 驗收命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_v4_effectiveness_evaluator.py tests\test_v4_effectiveness_read_model.py tests\test_finmind_cashflow_candidate.py tests\test_finmind_cashflow_candidate_cli.py tests\test_data_source_capability_registry.py -q -o addopts=
.\.venv\Scripts\python.exe -m pytest tests\test_backup_retention.py tests\test_fundamental_migration.py tests\test_fundamental_statement_backfill.py tests\test_tpex_daily_price_backfill.py tests\test_valuation_metrics_backfill.py tests\test_evidence_event_repository.py tests\test_evidence_event_cli.py tests\test_scheduled_data_update_runner.py -q -o addopts=
```

通過條件還包括變更 Python 檔案 `py_compile`、`git diff --check`，以及不把
candidate／fixture／隔離回放改標成正式資料或投資成果。本輪定向功能／來源／排程測試為
初次定向功能／來源／排程測試為 `26 passed`；補入排程例外與 freshness 回歸後，受影響整合集合為
`81 passed`，freshness fixture 為 `7 passed`，test inventory 為 `12 passed`。完整套件首輪為
`5087 passed / 4 failed / 4 skipped`，四個失敗（新測試登錄與 wall-clock fixture）已修正，受影響測試重跑全數通過。

## 尚未關閉的 V4 門檻

這次交付不會製造自然時間或來源授權：現金流仍要以官方公告可得日補齊，
正式 PIT／Paper causal ledger／成本後 benchmark、drift／pruning、OOS 與 rollback champion
仍須由真實 producer 累積並逐項讀回。沒有成熟 outcome 時，evaluator 會保持
`insufficient_decision_days` 或 `insufficient_mature_outcomes`，不授予 alpha、promotion 或 broker 權限。
