# Paper EOD freshness lane unknown projection QA（2026-09-21）

本次驗證只讀既有正式 freshness payload，沒有執行 Paper writer、quick update、正式 DB
寫入、receipt 產生或 credit 授予。驗證程式逐一讀取 payload bytes、計算 SHA-256，呼叫
`scripts/scheduled/paper_execution_dependency_gate.py` 的
`_paper_eod_freshness_projection()`；不使用正式 SQLite，也不以 `inspect_dependency()`
取代來源 payload 的投影驗證。

機器明細保存在已由 Git 排除的
`output/qa/paper_eod_unknown_projection_20260921/real_payload_projection.json`。本次
讀取時間為 `2026-09-21T11:40:09Z`。

| 目標日 | 正式來源 | SHA-256 | aggregate | projection | blockers | warnings / errors |
|---|---|---|---|---|---|---|
| 2026-09-15 | `D:\Min\Python\Project\FA_Data\output\scheduled\data_freshness\20260915_data_freshness.log` | `sha256:496bedfeaca04ac335c0e64257c0443af8f42d84b6c517bf6f4ec4803eb11b5b` | `degraded` | `degraded_non_eod_only` | `[]` | `6 / 0` |
| 2026-09-16 | `D:\Min\Python\Project\FA_Data\output\scheduled\data_freshness\20260916_data_freshness.log` | `sha256:094373653c98118f8009f5f5e1cb5af327294a17b8dc7a0d8256ea464fd9e00b` | `degraded` | `degraded_non_eod_only` | `[]` | `6 / 0` |
| 2026-09-17 | `D:\Min\Python\Project\FA_Data\output\scheduled\data_freshness\20260917_data_freshness.log` | `sha256:6a31d4ce6f83b4bd0c54d8945906081c579be2ff41253f6158efc854161cf1c9` | `degraded` | `degraded_non_eod_only` | `[]` | `6 / 0` |

三日投影中唯一被標示為 `not_required_for_paper_eod` 的來源都是：

- `tdcc_shareholding`：保留原始 `freshness_status=unknown`、4047 rows、actual
  `20260904`、`expected_period=null` 與「official rows ingested; per-market coverage
  and availability must be checked before declaring complete」；分類為
  `weekly_candidate_completeness_not_proven`／`tdcc_p0_candidate_shadow`。
- `fundamental.statement_availability_map`：保留原始 `freshness_status=unknown`、
  `reason=file_missing` 與 `file_exists=false`；分類為
  `fundamental_pit_mapping_missing`／`fundamental_pit_availability`。

這個 projection 只隔離 Paper EOD 的 consumer 邊界；它沒有把任一來源改成 `current`，
也沒有放寬 TDCC 候選或 Fundamental/PIT 自己的 fail-closed 規則。其他 unknown、
required source、malformed、failed、expected-wait、aggregate error 與日期／raw／SQLite
reconciliation blocker 仍會阻擋 Paper。三日結果只證明這份 freshness projection 通過，
不代表完整 historical gate 已 ready，也不重新授權 writer、Formal publication 或任何
credit。

## Portable regression fixture

pytest 不讀取正式 D 槽，也不依賴正式檔案是否存在。`tests/test_paper_execution_dependency_gate.py`
的 `test_historical_payload_shape_fixture_classifies_two_non_eod_unknown_sources` 以三個
目標日建立小型 fixture，欄位和值取自上述三份真實 payload，驗證兩個 unknown 的排除集合
與 `blockers=[]`；另有任意 unknown 與 explicit source `failed` 的 fail-closed 反例。

## 驗證命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_paper_execution_dependency_gate.py tests\test_paper_execution_retry_runner.py tests\test_scheduled_paper_execution_wrapper.py tests\test_scheduled_data_freshness_probe.py -q -o addopts=
.\.venv\Scripts\python.exe -m mypy --explicit-package-bases scripts\scheduled\paper_execution_dependency_gate.py tests\test_paper_execution_dependency_gate.py
.\.venv\Scripts\python.exe -m py_compile scripts\scheduled\paper_execution_dependency_gate.py tests\test_paper_execution_dependency_gate.py tests\test_paper_execution_retry_runner.py
```

結果為 focused pytest `38 passed`、mypy `Success: no issues found in 2 source files`、
`py_compile` exit code `0`。pytest 僅有既有 `.pytest_cache` ACL warning。

## 真實時間 Paper EOD gate 驗收（2026-09-21）

在真實時間 `2026-09-21T12:01:07+00:00`（台北
`2026-09-21T20:01:07+08:00`）以 commit `a7e18c7e` 的
`paper_execution_dependency_gate.inspect_dependency()` 做完整唯讀驗證。原始 gate
JSON 保存在被 Git 排除的
`output/qa/paper_execution_dependency_gate_20260921/gate_real_now.json`，檔案 SHA-256
為 `dc24e66ae3bc03ff8ec18f88e10d14380cfcf421e5a468bd102be427539a6925`。

驗證目標日為 `2026-09-21`，結果為 `status=ready_with_warnings`、`ready=true`、
`blockers=[]`，原因為同日 quick、freshness、SQLite 與 raw source hash reconciliation
通過。三個 Paper EOD required source 都是 `current`：
`twse.daily_prices.raw`、`tpex.daily_prices.raw`、`sqlite.daily_prices`；TWSE
`1093/1093`、TPEx `875/875` source rows 與 SQLite readback 全部匹配，SQLite market
observation 為 `ro/query_only`、1968 open rows。freshness aggregate 仍原樣保留為
`degraded`，`errors=[]`；六個非 EOD warning 只投影為 Paper lane warning。

`fundamental.statement_availability_map` 與 `tdcc_shareholding` 的 `unknown` 仍保留在
`not_required_for_paper_eod` 診斷中，沒有被改成 `current`、刪除或放寬其自身契約。
這次 gate 的 `query_only=true`、`source_db_written=false`、`source_files_written=false`、
`formal_credit=false`、`broker_order_allowed=false`；沒有執行 EOD writer、正式 DB
寫入、credit 授予或任何 production producer。此結果只證明當下 Paper EOD freshness
lane 可帶 warning 通過，不代表其他 historical／Formal gate 或自然 evidence 已成熟。
