# Paper EOD credit candidate freshness policy QA（2026-09-22）

本輪只修正 Paper EOD consumer projection。`data_freshness_probe` 的 candidate-only
producer contract 不放寬，`institutional_flows` 也沒有新增 policy；正式 EOD writer、
adapter、scheduler、source producer 與正式資料庫都沒有重跑或寫入。

## 具名 policy

只有 `credit_transactions` 可以進入
`freshness_lane.not_required_for_paper_eod`，而且 source row 必須同時符合：

- `freshness_status` 是 `stale` 或 `partial`。
- `candidate_only=true`。
- `frequency="daily candidate source"`。
- `downstream=["candidate research only"]`。
- `update_entry="UpdateService.update_phase3c_candidate_range"`。
- `reason` 是非空字串。

投影保留原始 `source_diagnostic`、`freshness_status`、`candidate_only` 與 `reason`。
缺任一條件、欄位值改變、同一來源的 warning 未通過 policy，或狀態為
`failed`／`expected_wait`／`unknown`，都維持 blocked。TWSE／TPEx raw 到 SQLite 的
三個 required market source、日期、open rows、root guard 與 query-only checks 沒有變更。

## 隔離回歸

測試 fixture 不讀取正式 D 槽，today fixture 使用 `target=2026-09-22` 與已觀察的
candidate row shape。回歸覆蓋：

- exact credit candidate row 可投影，且 raw row、status、reason 仍可讀回。
- `frequency` mismatch 與 required `sqlite.daily_prices=partial` 各自留下 blocker。
- candidate-only、downstream、update entry、空 reason、帶 warning 的不符 contract
  案例仍 blocked。
- `failed`、`expected_wait`、`unknown` 與未具名的 `institutional_flows` candidate
  不會因 `candidate_only` 自動放行。
- `_phase3c_candidate_statuses()` 的 stale row 保留 `actual_period=20260921`、
  `expected_period=20260922`、`missing_periods=["20260922"]`、reason 與 consumer
  contract。

驗證命令與結果：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_paper_execution_dependency_gate.py tests\test_scheduled_data_freshness_probe.py -q -o addopts=
.\.venv\Scripts\python.exe -m py_compile scripts\scheduled\paper_execution_dependency_gate.py tests\test_paper_execution_dependency_gate.py tests\test_scheduled_data_freshness_probe.py
.\.venv\Scripts\python.exe -m mypy --explicit-package-bases scripts\scheduled\paper_execution_dependency_gate.py tests\test_paper_execution_dependency_gate.py
```

結果為 focused pytest `33 passed`，py_compile exit code `0`，mypy
`Success: no issues found in 2 source files`。pytest 只有既有 `.pytest_cache` ACL warning，
不影響測試結果。

## 今日唯讀 gate after inspect

以固定 `observed_at=2026-09-22T13:00:03Z` 重讀正式來源後，結果為
`status=ready_with_warnings`、`ready=true`、`target_date=2026-09-22`；
`freshness_lane.status=ready_with_warnings`、`lane_blockers=[]`，且
`credit_transactions` 已進入具名 `not_required_for_paper_eod` projection。輸出同時確認
`query_only=true`、`source_db_written=false`、`source_files_written=false`，required market
blocker 為空。這次 after inspect 沒有保存新的正式 output artifact，也沒有執行 producer 或
writer；它只驗證 consumer projection。此前舊 code 的 13:00:03 gate artifact 曾以
`freshness_lane_noncurrent_source_unattributed:credit_transactions:stale` blocked，該差異
就是本輪具名 policy 修正的範圍。

因此，下一個正常 scheduler run 仍需重新驗收 immutable execution receipt、event capture、
ledger readback 與 writer terminal result；本 QA 不宣稱今晚 EOD 已執行或已產生 Paper fill。
