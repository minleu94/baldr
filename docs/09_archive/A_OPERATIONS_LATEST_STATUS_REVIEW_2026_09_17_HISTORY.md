# A 線正式與相鄰 lane latest-status 唯讀 review（2026-09-17）

本 artifact 只讀六個已命名 `latest_status.json` 及其檔案 metadata；沒有啟動
scheduled job、沒有修改 Task Scheduler、沒有寫入正式 `D:\Min\Python\Project\FA_Data`
或任何 SQLite。日期採 receipt 的 `decision_date`／`as_of_date`，檔案時間只作定位。

| Lane | 最新 clock／status | 新 cause／工程判讀 |
|---|---|---|
| Formal Paper | `decision_date=2026-09-07`；`passed`；`paper-main-20260907` | 正式 terminal receipt 是舊日快照，仍需合法時段正式 recovery run 驗證。 |
| Repository isolated Paper | `decision_date=2026-09-14`；`passed`；`paper-main-20260914` | isolated latest 也是舊 terminal；`run_state/latest.json` 不存在，A QA 不可替代正式運行證據。 |
| BankTaiwan | `decision_date=2026-09-17`；`completed_waiting_natural_maturity` | `natural_forward_evidence_receipt_missing`；matured `0`、pending `18`、formal order false。這是自然成熟等待，不是 failure。 |
| Legacy 05:45 | `decision_date=2026-09-17`；`passed_with_warnings` | `snapshot_cohort_degraded_screening_quality`；degraded `186`、eligible `14`、missing `0`；learning `retain_current`，原因仍是自然 forward evidence 未成熟。 |
| Official events | `as_of_date=2026-09-17`；`failed` | receipt cause `prior canonical raw lineage missing`；修正前 reader 未聚合 parent raw lineage。A 已以正式 artifact 隔離修正／驗證：current raw `52`、ancestor lineage `43`、canonical events `28636`、coverage gap `0`；active SQLite 未寫，formal last-known-good publication preserved，latest receipt／pointer 未重跑更新。 |
| Raw PIT | `2026-09-17 05:05:02–05:08:40 -07:00`；`failed` | `raw_pit_builder_failed:2`；quality `quarantine_required`，candidate `17858`、invalid `7`、unavailable `16913`；`ro/query_only`、source 不寫入。 |

Official events lineage probe 使用正式 D latest artifact 的 verified 40 段 parent chain
（latest manifest file hash `sha256:6052829c4f477c2a902513356d01aa25ac98d324a828144036d9137b492b49b0`；
canonical hash `sha256:07ee170332b220a416080773db2327987c7c4204e9d17651e0bf41c9d4f35fe6`）。
隔離副本的 positive 讀取 `28636` events、current raw `52`、ancestor lineage `43`、
coverage gap `0`；再用副本中 2026 四個 raw response 建立下一代
`official-market-events-8f81f86a04341d690a2d585f`，`new_events=0`、raw `95`、
canonical `28636`，95 個 response bytes 全部驗證相符。斷 parent manifest 與祖先 raw
tamper negative 分別回傳 `prior canonical raw lineage missing` 與
`prior raw response hash mismatch`；所有操作只寫暫存隔離副本。

工程分類：

- **仍需正式運行驗證**：Formal Paper 9/7 與 repository isolated Paper 9/14；repository isolated wrapper 在合法時間窗與 fresh source/calendar 前置條件滿足時可做隔離驗證，正式 D task recovery 如涉及既有 owner hold 或 D 寫入，依該 hold 執行並唯讀核對 terminal phase receipts、run-state、state head 與 source bytes hash。
- **reader 修正後仍待正式運行驗證**：official-events latest receipt 仍是修正前的 `prior canonical raw lineage missing`，正式 pointer 尚未由本輪重跑更新；raw PIT 缺 source receipt time 且品質分類要求 quarantine；BankTaiwan 與 legacy 的自然 forward evidence 尚未成熟。
- **核准 hold**：涉及正式 D 寫入或既有 owner hold 的 Paper recovery、任何 scheduler/DST 調整、formal promotion 或 broker action 都未因本 readback 自動放行；各 latest receipt 仍保留 `formal_order_allowed=false`／`production_action_allowed=false` 等 gate。repository isolated wrapper 若合法時間與 fresh source/calendar 前置條件滿足，仍可作隔離驗證。

此 artifact 不宣稱 EXIT、formal completion、候選升級或正式 D source repair；也不把 stale Paper 快照解讀成未接線。1418 identity／entry custody 仍依 A QA 原判定維持 unproven。
