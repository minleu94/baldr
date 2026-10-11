# Paper EOD 非交易日 gate 修正 QA（2026-09-25）

> 本文狀態截至 2026-09-25；文中年度休市 cache 已於 9/28 到期。後續 Paper gate 與自然排程狀態須另查更新的具名收據，不能沿用本次 direct gate 結果。

本次 bounded 修正只處理 Paper dependency gate 的官方休市分類。9/25 的 TWSE 年度休市 cache 以 exact target date、完整年度、raw response hash、content hash、available/captured 時間鏈與 freshness window 驗證；只有 verified `schedule[target] is False` 才回傳 `status=not_trading_day`、`ready=true`、`adapter_noop=true`。這個結果由既有 retry runner 的 no-op 分支消費，因此不進 isolated Paper adapter 或 writer。

gate 使用 `data_module.official_trading_calendar_cache.load_verified_twse_calendar_cache`，production default cache root 是 `output/paper_execution_eod_replay/calendar_cache`。open、cache missing、expired、tampered 或其他驗證失敗都不產生日曆 no-op，繼續走原有 quick、freshness、source file、SQLite readback 與 blocker 規則。quick updater 沒有修改；其真實 technical failure 仍保留在原始 receipt。Legacy alias 造成的 technical 真錯誤也不在本修正範圍。

實際 9/25 direct gate read-only inspect 於 `2026-09-25T13:43:47.003317Z` 回傳：

- `status=not_trading_day`、`ready=true`、`reason=twse_holiday_schedule_cache_closed`、`adapter_noop=true`。
- blocker 為空；`query_only=true`、`source_db_written=false`、`source_files_written=false`、`formal_credit=false`。
- gate 同時保留 upstream quick receipt 的 `status=failed`、SHA-256 `e8569f423021a8dd482f689ccef7f3c1c01032a5fd3cb85bc95364552759e898` 與 `error_count=1`，沒有把 technical failure 投影成 quick success。
- cache 為 `output/paper_execution_eod_replay/calendar_cache/twse_holiday_schedule_2026_20260921T231502556070Z_4784f9cff832.json`，file SHA-256 `2b145dacedbd267eef4df7f9043e0534eaa8d19a76ed6532c5218397bb5605c1`，有效至 `2026-09-28T23:15:03.981649Z`；9/25 row 是 TWSE 中秋節休市，source response hash 為 `7644c1a8af784c09f54670fd7413f536b13eb76c54d658058e8873d1aee32117`。
- 未重播 scheduler、retry runner、producer、writer 或 adapter；未改 quick receipt、正式 binding、market DB、Paper ledger 或 credit。
- `scripts\scheduled\paper_execution_dependency_gate.py --help` 與 `-m scripts.scheduled.paper_execution_dependency_gate --help` 均以 exit code 0 通過；直接檔案路徑啟動已補 repo-root import bootstrap，沒有因此呼叫 writer 或改檔。

忽略型 direct inspect proof 在 `output/qa/paper_eod_holiday_gate_fix_20260925/readback.json`，SHA-256 為 `7314DA4F2D5AC64DDE4B4286E705A6FE9E96EC4785E51CE2A004E92B3FFF40EE`，JSON parse 通過。

隔離測試只使用 `tmp_path` 建立 synthetic annual cache、quick receipt、freshness receipt 與 SQLite：

```text
\.\.venv\Scripts\python.exe -m pytest tests\test_paper_execution_dependency_gate.py tests\test_paper_execution_retry_runner.py -q -o addopts=
43 passed
```

測試涵蓋 verified weekday holiday 在上游 receipt 缺失或 failed 時仍安全 no-op、open/missing/expired/tampered cache 維持原 blocker，以及 runner 不呼叫 adapter。新增 isolated subprocess `--help` case 會移除 `PYTHONPATH`、切換至獨立 cwd，確認直接檔案路徑啟動可 import 且沒有產生輸出檔。`py_compile` 與 `git diff --check` 通過；pytest 僅有既有 `.pytest_cache` 權限 warning，沒有測試失敗。

targeted mypy 的 production gate 與 dependency gate test 均通過；retry runner test 保留原有 4 個既知型別錯誤（第 187、219、357、645 行），本次沒有新增錯誤。

event capture 的另一個 blocker 仍是固定 `2026-09-09` runtime config 過期；既有 roll-forward 已產生 candidate `output/v4_next_formal/formal_daily_runtime_config_v6/2026-09-29.json`，但正式 binding 仍指向 9/9，這次沒有切換或修改 binding。自然 scheduler run、operational receipt 與 writer 結果仍待 root 審查後的下一次受控驗收。
