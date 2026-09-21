# 晨間排程、資料接線與 Evidence 契約修復 QA（2026-09-21）

## 範圍與結論

本輪修復 04:20–05:15 晨間鏈路：quick data update、freshness、recommendation snapshot、
Evidence dry-run，以及其 Paper／Position Health／Exit 衍生來源。Windows Task Scheduler 五項
既有 action 未重註冊，因為都已指向 repository canonical CMD wrapper；最終五項皆
`Ready`、`LastTaskResult=0`。

Evidence Windows task 於 12:52 與 12:54 Pacific 連續兩次同日實跑均 exit 0。第二次重跑後
`position_health_transitions_v2.sqlite` 仍為 5 筆 proposal，所有已驗證 position 的
`persistence=idempotent`，沒有 transition blocker。`latest_status.json` 為 `degraded` 而非
`failed`；這是人工 thesis／position lineage 與自然 maturity 尚未完成，不是工程接線失敗。

## 已修正的工程問題

1. 隔離 Paper 外層 status 改用 canonical `paper-portfolio-daily-status.v1`；隔離 scope version
   另存 `isolated_scope_schema_version`。consumer 以共用 helper 驗證 canonical schema，並只對
   同時符合 research-only、no-broker、isolated path flags 的舊 receipt 提供 bounded compatibility。
2. Evidence 預設 Paper status path 改為
   `output/paper_execution_eod_replay/scheduled/paper_portfolio_isolated/latest_status.json`。
   CMD 與 PowerShell wrapper 都委派同一 scheduled orchestrator；PowerShell 不再維護另一套 child
   參數。
3. Frozen Rule consumer 接受 producer 實際發布的 `rule_source_bundle_created`／
   `rule_source_bundle_reused`，不再因舊 status token 誤擋。
4. Position Health market source 將 quick/freshness degradation 投影到明確 lane：daily price／
   technical 核心皆 current，quick warning 只能屬 Phase3C candidate step，freshness warning 只能是
   明列的 fundamental current-observation gap；未知 warning 仍 fail closed。
5. Exit Effectiveness bounded timeout 由 120 秒調整為 300 秒；主 pipeline 與 child log 改用每次
   run 的唯一 timestamp。log write error 會落入結構化 status／非零 exit，不再讓 wrapper 留下
   未處理 traceback。
6. 市場 `source_snapshot_hash` 改綁 selected market rows，不把 capture clock、baseline receipt bytes
   或 whole-file stat 當成資料快照 identity；完整 custody 仍保留在 immutable receipt。
7. Position Health proposal 使用 semantic identity v2，排除 capture timestamp、artifact path 與
   receipt-only file hash，但保留 position、condition、metrics、policy 與 semantic source hashes。
   新事件寫入 `position_health_transitions_v2.sqlite`；舊 v1 DB 原封不動保留。舊庫唯讀盤點為
   10 筆 proposal、0 筆 human approval，未刪除、未覆寫、未提升 credit。
8. 05:30 Codex heartbeat 保留原 schedule、thread 與 read-only 邊界，只補判讀規則：Phase3C
   candidate lane、fundamental current-only／formal PIT 邊界、由 status pointer 讀唯一 log，以及
   Position Health degraded 但無 engineering blocker 的分類。automation prompt 仍不傳入 pipeline，
   不可能改變 Windows task 執行結果。

## 實質資料接線驗證

### Phase3C 官方來源與 candidate DB

- TWSE T86、TWSE MI_MARGN、TPEx institutional／margin 官方 endpoints 已以專案 fetcher 實讀。
- HTTP 200 但 `stat`／明細 table 尚未發布時，fetcher 最多做 3 次、每次 30 秒 semantic retry；
  日期 mismatch 與 schema mismatch 不重試掩蓋。
- candidate DB：`D:/Min/Python/Project/FA_Data_candidate/phase3c_candidate.db`，唯讀
  `PRAGMA quick_check=ok`。
- institutional latest=`2026-09-21`、total rows=`428431`、latest rows=`23704`，同時含
  `twse-official-T86`／`tpex-official-3itrade`。
- credit latest=`2026-09-21`、total rows=`42111`、latest rows=`2216`，同時含
  `twse-official-MI_MARGN`／`tpex-official-margin_bal`。
- freshness probe 改以明確 candidate DB 的 `mode=ro`／`query_only` 驗證日期、source versions、
  duplicate natural keys 與 row count，不再讀正式 DB 的舊 candidate table 判斷 quick step。

### 月營收 current observation

- 官方 snapshot：
  `D:/Min/Python/Project/FA_Data/output/monthly_revenue_mops_snapshots/mops_monthly_revenue_snapshot_2026-08_2026-08_2026-09-11.csv`。
- 受控 apply 共 1841 rows（TWSE 980、TPEx 861），先建立備份並通過 quick check；evidence receipt：
  `output/fundamental_current_refresh/monthly_2026-08_apply.json`。
- 契約仍是 `current-observed-only; no historical announcement evidence`。這些 rows 不會自動
  promotion 到 formal PIT table。

## 刻意保留的非工程 blocker

freshness 最終只有四個 fundamental warning：

- `monthly_revenue_expected_period_not_available`
- `quarterly_statement_expected_period_not_available`
- `source_freshness_degraded:fundamental.current_monthly_observations`
- `source_freshness_degraded:fundamental.current_statement_observations`

formal monthly table 仍停在 2026-06、expected 2026-08；formal statements 仍停在 2024-Q1、
expected 2026-Q2。必須由資料 owner 提供 official announcement、available-at 與 revision lineage，
不能把 current observations 直接複製成 historical PIT。

Evidence 最終 5 個 actionable warning 是：portfolio alert not ready、持倉 thesis 人工欄位、
1418 position identity/entry lineage 未證明、risk prompt not ready，以及 risk prompt 繼承 degraded
portfolio alert quality。它們保留 `manual_action_required=true`，但 wrapper／Scheduler exit 0；
沒有寫 Evidence DB、沒有 formal credit、沒有 broker order 或自動 action。

## 驗證

- focused regression：`198 passed`。
- Python `py_compile`：通過。
- targeted mypy（4 個核心 source files、`--follow-imports=skip`）：通過。
- scoped `git diff --check`：通過；僅有 repository 既有 LF→CRLF 提示。
- pytest 唯一 warning 是 `.pytest_cache` 權限，與產品行為無關。

## 安全與資料邊界

- 沒有使用 Evidence `--confirm`，`writes_evidence_db=false`。
- 沒有修改 Windows task action／trigger；只觸發既有 dry-run task做驗收。
- 沒有刪除或覆寫原始資料、舊 transition DB 或 Paper ledger。
- 月營收 apply 有本機備份：
  `output/fundamental_current_backups/before_monthly_20260921T192035818211.db`。
- 本輪結果不構成投資有效性、alpha、正式 Advice 或交易指令。
