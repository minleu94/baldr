# 2026-10-19..25 Weekly Review 候選複核

## 行情週收集候選

唯讀檢視隔離候選 `weekly-current-period-candidate-20261025/scheduled/v2_2_weekly_collection/v2_2_weekly_collection_20261025.json`，SHA-256 為 `3b5b8610cd3f8e8008c62f5bc8171248bb4c7aa4bc824cd757953ed5d66631a9`。Collection ID 為 `ewc_6d44f2be666d127a`，source hash 為 `sha256:74324dbc7a6b3bf0dfd6ed656f6452958f959de97550e59cc0500dfff262f2e1`，期間 2026-10-19..25，最後交易日 10/22。

- 觀察到 7,859 列、1,987 個股票代碼、4 個交易日、0 重複列；日分布為 1,965／1,965／1,965／1,964 列。
- 16 列缺 OHLC（10/19 5 列、10/20 3 列、10/21 1 列、10/22 7 列）在候選中對應同日 TWSE custody receipt，來源回報 `--`；沒有以其他價格補值。
- 四個交易日的 TWSE receipt 都是 HTTP 200；逐一依 receipt 相對路徑讀取原始 payload，4 個 raw SHA-256 均與 receipt 相符。receipt 的 available time 是收盤後，`historical_pit_status=prospective_capture_only` 且 `formal_source_contract_eligible=false`，所以這些 receipt 可說明官方缺值原因，不能充作歷史 PIT／Formal 資格。
- 覆蓋口徑是 `observed_daily_prices_rows_only`；expected universe 為 null，未宣稱全市場完整。Quality 為 `degraded`，collection 與 Gate credit 狀態都是 `pending_human_review`。
- Collection payload 的 `source_write_allowed=false`、`write_intent=false`；候選未追加正式 sidecar。

此候選已足以供人核查本週行情列、已知官方缺值與覆蓋界線，但不是 V2.2 weekly review history，也不足以給 Gate 2 credit。

接著使用 `build_evidence_weekly_approval_input.py` 從該週隔離 sidecar 產生非核准型 packet。Packet SHA-256 為 `ead885ac2e579b8a2990f51042e856bbc5d3213fbf9f0bbece482b8be9b695fc`，綁定的 sidecar SHA 為 `sha256:8be28042ee627e225733b399c8e839b81b532645ee673631e28a34ea9429b728`；1 筆 pending row 為 `reviewable_candidate`、packet status 為 `needs_named_owner_reviewer`，reviewer／owner role 仍空白。`write_performed=false`、`formal_credit_authorized=false`、`production_scheduler_allowed=false`。這讓新週候選進入可供具名人員逐筆檢視的 packet，但不等於 runbook 的完整 weekly review。

## Runbook 配套實際檢查

依 [V2.2 Weekly Review Runbook](../07_guides/V2_2_WEEKLY_REVIEW_RUNBOOK.md) 建立 4.15 GB working copy，確認 source DB 與副本路徑不同，並只在副本執行操作。第一輪 Evidence Pipeline report 的 run ID 為 `epr_439216bf5090`，執行參數記錄 `dry_run=false`、`confirm=true`；其來源覆蓋指出 `recommendation_persisted_missing`、`watchlist_trigger_snapshot_quality_not_ready`、`risk_prompt_snapshot_quality_not_ready`，scheduler readiness 為 `not_ready`。兩輪 smoke wrapper 在 180 秒上限逾時，receipt 為 `timed_out=true`、`forced_cleanup=true`，所以沒有可用的兩輪 idempotency 結果；不宣稱 smoke 通過。正式 source DB 的大小及修改時間在執行前後相同。

隨後在同一副本產生唯讀週報 `weekly-review-working-copy-20261025/weekly-review-report.md`，SHA-256 為 `2734ad0b7ce113a60e0b7579cce0b6bc9a6576ffa1e7fd192fbf35d280ef615f`。結果為 `coverage_only`、scheduler readiness `not_ready`、`production_scheduler_allowed=false`、`write_performed=false`、action item plan `dry_run=true` 且未建立項目。Blocking gaps 為 `production_scheduler_approval_missing`、`recommendation_persisted_missing`；warnings 包含 liquidity gate、screening matrix、why-not payload 缺件。該週報沒有 review，也沒有建立 history。

## 尚缺條件與裁定

依 runbook，完整週 review 尚缺可核對的 scheduled/manual dry-run 與 dashboard 配套、smoke 兩輪完成結果、warnings/blocking gaps 判讀、具名 reviewer 的 reviewed/dismissed/follow-up、action owner，以及 backup/rollback/recovery 演練。既有正式 weekly sidecar 的 17 筆舊列仍是 `recollection_required`；新週候選目前只在隔離 sidecar 的 packet 中可審，尚未 append 到正式 sidecar，也沒有人工審查結論。

本次只產生收集候選及非核准型唯讀週報，未執行 `--confirm-action-items`、`--save-history`，未更新正式 sidecar、Gate credit 或 production scheduler。下一步是補齊同週 runbook 配套並交具名 reviewer 判讀；真正的三週 history 仍須由各週真實時間證據逐週形成。
