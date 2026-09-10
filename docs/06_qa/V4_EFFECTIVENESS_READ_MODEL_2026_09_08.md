# V4 有效性與資料來源工程驗收（2026-09-08）

本輪完成的是可重播的工程底座與資料來源隔離，**不代表 V4 投資有效性已完成**。
自然前瞻觀測、成熟 outcome、正式三路輸入與 promotion 仍依
`docs/00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md` 的門檻累積。

## 2026-09-10 跨日證據身份修正

本節是本文件中 V4 evidence identity 的最新契約；後面的歷史段落保留當時驗收
脈絡，不覆寫正式資料或替舊事件補身份。

- `universe_policy_id/hash` 是可跨日比較的政策身份，只包含市場範圍、選擇演算法版本、
  產業／資格設定、`max_stocks`、來源 provider 與明確 requested universe；不包含決策日或
  動態政策每日選出的代號。
- `universe_snapshot_id/hash` 是不可變的每日快照身份，保存決策日、當日 selected codes、
  selected-count 與 `universe_snapshot_selected_codes_hash`。它保留每日組成差異，但不再作為
  evaluator 的跨日 cohort key。
- `strategy_config_id/hash` 綁定重要策略設定、`max_stocks` 與 `top_n`；`horizon_days`、
  cost model、benchmark、`return_basis` 與 evidence tier 都是獨立的比較身份。不同設定、
  口徑或 `forward`／`replay` lane 不混算。
- Recommendation snapshot → importer → `evidence_events.metadata_json` → outcome metadata →
  SQLite read model → evaluator 全鏈保留上述欄位。缺新版 policy／snapshot 任一件會 fail closed；
  舊事件只保留 legacy／缺件診斷，不以目前股票池、profile 或新政策回填。
- evaluator 會以 policy／strategy／horizon／cost／benchmark／return-basis／tier 分組，並另外
  揭露 `universe_snapshot_count`、快照清單與組成變化次數。工程正例的跨日累積只證明接線，
  不授予 V4 或投資有效性信用。

每日 forward producer 維持 120 個曆日／2,500 events 上限，但在 SQL bounded query 中先把
未完成 outcome 排到前面，再以完整 cohort identity 過濾後套用相同上限；舊 pending 事件因此不會
被當日新事件長期餓死。receipt 的 `health` 會列出最新合格事件日、完整身份事件數、cohort／日數、
各 horizon 的 ready／pending／missing、capture／outcome／evaluation 時間、下一成熟日與 blocker，
並分類 `normal_completion`、`normal_no_new_outcomes`、`waiting_for_natural_maturity`、
`actionable_engineering_blocker`、`external_source_missing`。UI 只讀顯示這些欄位。

## 2026-09-10 B 線唯讀盤點與 receipt 可靠性修正

本次以 `TWStockConfig` 回傳的正式 `DATA_ROOT=D:\Min\Python\Project\FA_Data` 與其
`OUTPUT_ROOT` 唯讀檢查；沒有執行正式 DB writer、資料重建或歷史回填。盤點結果如下：

- `evidence_events` 仍有每日 capture；2026-08-20～09-10 每日事件約 1,650～1,700 筆，
  `recommendation_included` 合計 217 筆，2026-09-10 有 2 筆。這證明 capture／importer
  端持續產生事件，但不等於 outcome 已成熟。
- `evidence_outcomes` 目前唯讀聚合為 5／10／20／60 各 2 筆，全部是
  `insufficient_future_data`／`missing`，ready=0；2026-09-10 forward receipt 的
  summary 只建立 8 筆 pending outcome。receipt 原先是 `passed_with_warnings`、
  `blockers=[]`、`exit_code=0`，但 `health.classification` 已是
  `actionable_engineering_blocker`，且 bounded selection 跳過 215 筆不完整 identity。
- 本切片把 health 終端狀態接回 receipt：confirmed run 遇到
  `actionable_engineering_blocker` 或 `external_source_missing` 會是 `blocked`／2，並保留
  `blocking_reason`、`next_action`、`next_maturity_date` 與
  `recovery_verification`；同輪已寫入的 outcome 仍受 `(event_id, window_days, return_basis)`
  冪等鍵保護。自然未成熟仍是 `passed_with_warnings`／0，不能用人工補值或未來價格消除。
- Canonical isolated Paper（repository operation root）截至 2026-09-10 有 6 個持倉、現金
  `161526.11`、總值 `482526.11`；ledger 有 8 筆（6 filled、1 partially filled、1 rejected），
  費稅合計 `1373.89`。以 Decimal 逐筆重算後現金與 snapshot 一致，沒有發現 accounting mismatch；
  readiness 仍為 `partial`，因 Equal-Weight benchmark 與週報 benchmark observations 缺失。
- `schtasks.exe /Query` 在本次受限環境對目標 task 回報找不到系統路徑，因此不能以本次 shell
  宣稱實機註冊／最近成功已驗證；receipt 也不能取代 Task Scheduler live query。正式
  scheduler／Formal OOS／broker 旗標維持關閉。

恢復判定以 receipt 的 machine-readable checks 為準：工程阻塞須看到 bounded selection 的
`events_skipped_incomplete_identity=0`、`source_preflight.ready=true`、無 historical backfill，
再確認 outcome natural key 重跑不重複；自然成熟則等待官方交易日可見價格，確認
`data_as_of_date` 非 future、outcome 變為 ready 或明確 pending。上述修正只改程式與隔離測試，
不把現有 8 筆 pending、Paper 隔離資料或 replay／fixture 提升為 V4／Formal credit。

跨日整合驗收位於 `tests/test_v4_cross_day_evidence_contract.py`，涵蓋真實 DTO/importer/
evidence SQLite/outcome/read model/evaluator 接線、動態成分變化、身份隔離、舊 schema 診斷、
冪等與 bounded 長 horizon 優先順序。這些資料是隔離 fixture，不是正式 D 槽自然證據。

## 本輪交付

### V4 cohort effectiveness read model

- 新增 `app_module/v4_effectiveness_evaluator.py` 與
  `app_module/v4_effectiveness_read_model.py`。
- 輸入依 `horizon_days`、`strategy_version`、`strategy_config_id`、穩定
  `universe_policy_id/hash`、`cost_model`、`benchmark_id`、`return_basis` 與 evidence tier
  分 cohort；每個決策日獨立排序 top-k，不把日期、策略或成本政策混在一起。
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
`evidence_outcomes`；新版事件 metadata 必須同時有 policy 與 snapshot 身份，缺件時保留 warning，
不能用目前股票池猜測補值。只有沒有新版 schema 標記的舊 bare `universe_id` 才以 legacy
相容模式讀取，並不宣稱符合新版跨日契約。
指定 `--window-days` 時，沒有該成熟 outcome 的事件仍會保留為 `missing`，不因
SQL 篩選而消失；同一事件的其他 `return_basis` 不會混入，預設只讀
`close_to_close_event_date`。事件若明確保存 `horizon_days`，可在未指定 outcome
時提供缺件 row 的 horizon；未宣告 horizon 會留下 warning 並維持無效 cohort。
大量相同的 row-level 輸入錯誤會以 `rows_<code>:<count>` 彙總，避免正式資料
缺欄時產生數千個重複訊息；cohort identity 欄位只接受純量文字，list／mapping／bool
形式會以 `rows_incomplete_cohort_identity` fail closed；未知狀態與 cohort 衝突仍保留
明確 warning。

### 新推薦事件的身份綁定

`RecommendationService` 在完成實際 universe 選擇後，產生穩定的
`recommendation-universe-policy.v1` `universe_policy_id/hash`，並另產生保存決策日與
實際成分的 `recommendation-universe-snapshot.v1` `universe_snapshot_id/hash`，兩者都保存於
run context。舊 `universe_id/hash` 欄位保留為每日 snapshot alias，不能再拿來作跨日政策 key。
每日 research-only
推薦 snapshot 固定帶 `strategy_version_id=scheduled-recommendation-default-v1`、
`cost_model_id=gross-close-to-close-no-cost-v1`、`benchmark_id=TAIEX` 與
`horizon_days=20`。其中 20 是 V4 主要 cohort 標籤，不是持有保證；no-cost identity
明確表示尚未扣除手續費、稅費、滑價或流動性成本，evaluator 會留下
`cost_model_not_cost_adjusted` warning。`RecommendationEvidenceImporter` 只接受 result
config／run context 中已存在的 strategy、cost、benchmark、policy／snapshot universe 與 positive horizon
欄位，寫入 event 欄位及 metadata；不以 profile、symbol、目前股票池或推薦結果列推導
缺件，也不替既有事件回填。
因此這是後續 producer 的可追溯身份接線，不是現有資料的 V4 credit。

### 每日 forward outcome producer

新增 `app_module/scheduled_forward_outcome_service.py`、
`scripts/scheduled/run_scheduled_forward_outcomes.py` 與
`scripts/scheduled/run_forward_outcomes_daily.cmd`。`baldr-forward-outcomes-daily`
固定在 Decision/Evidence capture 後的 05:40 執行，預設只處理最近 120 個曆日、最多
2,500 個帶身份契約的 `recommendation_included` 事件及 5／10／20／60 交易日觀察窗；
`FORWARD_OUTCOME_EVENT_TYPE` 可受控切換事件類型。價格查詢以當次台北
`data_as_of_date` 為上限，固定使用 `close_to_close_event_date`，不做 historical
backfill 或未來價格補值。

入口先用 SQLite `mode=ro`／`PRAGMA query_only=ON` 確認
`evidence_events`、`evidence_outcomes`、`daily_prices` 三個來源存在。未加 `--confirm`
只產生 dry-run receipt；正式 DB 還需 `--allow-production-db-confirm`。排程 wrapper 才會
明確帶入兩個旗標，並只呼叫既有 `ForwardPerformanceService` 的 outcome upsert；事件、
推薦、Paper／Formal、模型與券商狀態都不在寫入範圍。每輪保存
`scheduled/forward_outcomes/latest_status.json` 與不可覆寫的 `runs/<run_id>.json`，
自然未成熟仍以 `passed_with_warnings`／`degraded` 揭露；但 confirmed run 若 health 判定
工程阻塞或外部來源缺失，會以 `blocked`／`exit_code=2` fail closed，並留下 blocking reason、
next action、next maturity 與 recovery verification。

排程 wrapper 同時帶入 `--require-cohort-identity`；沒有明確策略、成本、benchmark、
universe 或正整數 horizon 的舊事件會被計入 `events_skipped_incomplete_identity`，不會
寫入不可被 V4 cohort 消費的 outcome。

Outcome upsert 的自然鍵是 `(event_id, window_days, return_basis)`；重跑只更新該鍵下的
價格、成熟度、品質與 warning，保留第一次建立的 `outcome_id`，讓下游引用在重算後仍穩定。

`ScheduledEvidenceStatusService`、`ScheduledEvidenceStatusView` 與 Workbench 背景證據流
會唯讀呈現這份 receipt 的 status、掃描／寫入／待成熟計數與
`forward_outcome_writes_evidence_db`；缺少 receipt 時顯示 source gap，不會以其他排程
payload 推估 outcome。

隔離驗收涵蓋 dry-run 不改 DB、production confirm 缺旗標時阻擋、明確 confirm 只新增
outcome、必要來源表缺失阻擋，以及未來 `data_as_of_date` 拒絕；測試為
`tests/test_scheduled_forward_outcomes.py`。本次沒有對正式 D 槽執行 writer，因此正式
盤點的 `evidence_outcomes=0` 仍維持原狀，待下一個自然排程產生第一筆可讀回結果。

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
