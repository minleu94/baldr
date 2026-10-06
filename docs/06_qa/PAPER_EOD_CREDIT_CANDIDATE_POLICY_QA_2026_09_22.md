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

## 時鐘邊界與今日唯讀 gate

固定 `observed_at=2026-09-22T13:00:03Z` 的結果只能稱為舊 code 的歷史時鐘參數
projection replay，不能當作實際今日 gate ready 驗證。它保留在 before artifact
`output/paper_execution_eod_replay/dependency_gate/dependency_gate_20260922T130003311323Z_attempt1.json`，
當時為 `status=blocked`、`ready=false`，含
`freshness_lane_noncurrent_source_unattributed:credit_transactions:stale` 與
`freshness_status_not_passed:degraded`。

之後以真實目前時鐘執行一次完整 `inspect_dependency()` 唯讀檢查，沒有重跑 producer、
adapter、scheduler 或 writer，也沒有改用固定 observed time。實際觀測時間為
`2026-09-22T13:46:41+00:00`（台北 `2026-09-22T21:46:41+08:00`），最小原始摘要保存於被
Git 排除的
`output/qa/paper_eod_candidate_policy_20260922/real_now_gate_summary.json`。結果為
`status=ready_with_warnings`、`ready=true`、`target_date=2026-09-22`、
`freshness_lane.status=ready_with_warnings`、`freshness_lane_blockers=[]`，且
`credit_transactions` 已進入具名 `not_required_for_paper_eod` projection；整體
`blockers=[]`。摘要同時保存 `query_only=true`、`source_db_written=false`、
`source_files_written=false` 及 before/after boundary。這只證明該真實觀測時刻的 gate
consumer 結果，不宣稱 EOD writer 已執行。

因此，下一個正常 scheduler run 仍需重新驗收 immutable execution receipt、event capture、
ledger readback 與 writer terminal result；本 QA 不宣稱今晚 EOD 已執行或已產生 Paper fill。
