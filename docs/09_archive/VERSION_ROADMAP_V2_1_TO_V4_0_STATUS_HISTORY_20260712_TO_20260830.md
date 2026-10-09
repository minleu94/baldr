# V2.1–V4.0 歷史狀態快照（2026-07-12 至 2026-08-30）

> 本檔保存成熟度版本各節曾附加的日期化狀態；內容描述當時工程與證據，不作目前狀態或優先順序依據。

## V2.1：Daily Usable Workbench

**目前版本狀態（2026-07-12）**：V2.1 已於 2026-07-12 14:51:42 -07:00 獲 release owner 明確 `approve`，正式 closeout 狀態為 `formal_closeout_complete`。已驗證的 bounded / read-only Daily Usable Workbench 行為為：Guided 僅接受 `promoted`、parameters locked 與 disclosure complete 的策略；`max_positions` 只允許 `1..8`；Professional candidate 僅 `RESEARCH` 並與正式 Advice 分區。focused suite 為 `94 passed in 2.91s`，engineering readiness 與 approval record 分別見 `docs/06_qa/V2_1_ENGINEERING_READINESS_2026_07_12.md`、`docs/06_qa/V2_1_FORMAL_CLOSEOUT_2026_07_12.md`。此狀態不改變本文件的 maturity 定義，亦不代表投資有效性、broker execution、production scheduler、P0 source acceptance 或後續版本 Gate 已完成。

## V2.2：Evidence Operating Loop

**目前版本狀態（2026-07-12）**：V2.2 的 weekly review CLI、append-only history 操作介面、working-copy runbook 與 scheduler approval package 已具 engineering readiness；2026-07-06 至 2026-07-12 的 Week 1 已以隔離 working-copy 完成 repeat=2 idempotency smoke、人工 review 與 append-only history，weekly history 為 `1/3 waiting_for_time`。multi-day dry-run 已為 `3/3 ready`，scheduler 未獲核准且 `production_scheduler_allowed=false`。因此不得建立 V2.2 formal closeout，也不得將 replay、fixture、raw scheduled report 或單次 smoke 解讀為 Week 2 / Week 3。Week 1 證據見 `docs/06_qa/V2_2_WEEK1_REVIEW_2026_07_12.md`；三週人工操作格式詳見 `docs/07_guides/V2_2_WEEKLY_REVIEW_RUNBOOK.md`。本狀態不代表 production trading、lifecycle action 或投資有效性。

## V2.2：Evidence Operating Loop

**現況補充（2026-08-30）**：上述 `1/3` 是歷史 working-copy 層，不是唯一 current
counter。現況必須同時列出 formal/canonical credit 未授予、歷史 working-copy=`1/3`、
owner-approved UI projection=`3/3`、正式 sidecar pending=`10`、multi-day=`3/3` 與
`formal_credit_authorized=false`。因此 V2.2 仍未 closeout，但真正下一步已轉為 10 期具名
review、formal credit、backup／rollback／recovery 與 scheduler approval；不得再裸寫一個
`X/3` 代表全部 Evidence 狀態。

## V2.3：P0 Data Credibility

**目前版本狀態（2026-07-12）**：V2.3 已建立工程 readiness 與完整 Gate 3 P0 source-by-source 人工接受台帳，見 `docs/06_qa/V2_3_ENGINEERING_READINESS_2026_07_12.md`、`docs/06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md`。除權息 / 除權、未登錄的減資 / 分割 / 面額變更與停牌 / 復牌、其他交易限制、三大法人、信用交易、TDCC 與 PIT fundamentals 目前全部是 `requires_human_acceptance`，且 `downstream eligibility=none`；每列保留 source version、as-of / available date、rate limit、freshness / coverage、quarantine / retry、evidence / review / rollback 與分離 owner / date。`decision_ready_candidate` 只屬診斷結果，不是 accepted feature；既有 `corporate_action.ex_dividend_timeline` 不涵蓋未登錄 corporate-action 事件。V2.3 formal closeout 尚未建立，必須等待逐來源完成 license、quality、PIT / available-date、missing / outage 與具名 owner / date 的 accepted / limited / rejected / deferred 決議。本狀態不改變本節 maturity definition，亦不代表正式 ingestion、`ScoringEngine` 接線、Advice / Portfolio eligibility、scheduler approval 或投資有效性。

## V2.3：P0 Data Credibility

**現況補充（2026-08-30）**：P0 已由 contract-only 推進到 13/13 machine evidence，8/30
bounded retry 為 `1 verified / 9 degraded / 3 official_no_data`，3/3 唯一官方條款頁
candidate 可取得；accepted／limited 仍為 0、downstream eligibility none。未完成項目是
publication／獨立 coverage denominator／decision-time PIT／license acceptance 與 13 筆具名
決議，不應把 machine evidence 或條款頁 hash 當成 V2.3 closeout。

## V2.5：Position Health Foundation

**目前版本狀態（2026-07-12）**：V2.5 已有 read-only `PositionHealthService` 與 sample report，將既有 condition、feedback 與 source trace 投影為 HEALTHY / WATCH / EXIT_CANDIDATE，固定 `auto_action_allowed=false`。缺 condition 或 source trace 時維持 WATCH；它不讀實際持倉、不寫 DB、不自動減碼或平倉。工程 readiness 詳見 `docs/06_qa/V2_5_ENGINEERING_READINESS_2026_07_12.md`；真實 thesis、人工 state transition 與 decision journal 尚未累積，故 formal closeout 尚未建立。

## V2.5：Position Health Foundation

**Paper 現況補充（2026-08-30）**：已累積 21 snapshots 與 21 Equal Weight observations，
但 Paper Trade Ledger 仍 missing、fills／cost records=`0`，weekly=
`not_computable_cost_ledger_missing`。Import、Decimal 成本與 reconciliation contract 已存在，
repo 內仍沒有自然產生真實 Paper fills 的 producer；因此 V2.4／V3.1 缺口是 execution
producer 與真實 partial-fill／override／execution-gap evidence，不是再增加一個 snapshot。

## V3.0：Signal Effectiveness & Pruning

**目前版本狀態（2026-07-12）**：V3.0 focused suite 重新驗證 26 passed，artifact readiness 為 complete 且無程式 blocking gap；sample evidence 仍有樣本不足、產業 benchmark 缺口及舊 screening-matrix payload gap。故狀態維持 `ready_for_manual_validation`，任何正式 effectiveness、pruning 或版本 closeout 均未成立。

## V3.3：ML Shadow / Champion-Challenger

**目前版本狀態（2026-08-30）**：Formal validator 對整個 output 的 `19,942` manifests
做 exact-schema cross-check 後仍為 owner-controlled inputs `0/3`；causal=`0`、Rule=`0`、
PIT=`1`，且唯一 PIT 是 prospective diagnostic-only。PIT／Direct／OOC immutable shadow chain
與 owner handoff 工程存在，storage headroom 亦已恢復，但 `formal_oos_allowed=false`、alpha=0、
promotion／broker=false。容量通過不構成 V3.3 formal closeout，更不構成 V4.0。
