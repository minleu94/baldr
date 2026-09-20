# Forward maturity calendar 接線 QA（2026-09-18）

本 QA 只處理 scheduled forward outcome 的「預計成熟日」診斷接線。它不改既有 close-to-close outcome、價格 row-offset、benchmark、cost、label、policy gate 或 natural learning credit，也沒有執行正式 scheduler／runner。

## 已確認的根因

原本 `app_module/forward_performance_service.py::_outcome_maturity()` 將 symbol 的 daily-price keys 當作 `trading_dates`；`_find_outcome_price()` 也以同一個 stock row offset 取得 outcome。`scripts/scheduled/run_scheduled_forward_outcomes.py` 原本沒有傳入官方 calendar，因此 9/17 receipt 的 h10/h20/h60 會出現 `waiting_for_calendar` 與 `next_maturity_date=null`，即使既有官方 annual cache 可用。

這次保留上述 actual-price contract。官方 calendar 只形成額外的 `planned_official_maturity_date` 與 custody 診斷，不會讓 `EvidenceOutcomeStatus.READY` 提前成立。

## Read-only 官方來源證據

實際檢查的 annual cache：

`output/paper_execution_eod_replay/calendar_cache/twse_holiday_schedule_2026_20260914T231502118687Z_e02efc5483b2.json`

以既有 `data_module/official_trading_calendar_cache.py::load_verified_twse_calendar_cache`，`observed_at=2026-09-17T23:59:00Z` 驗證通過：

- schema：`official-trading-calendar-cache.v1`
- `available_at/captured_at`：`2026-09-14T23:15:03.532140Z`
- `expires_at`：`2026-09-21T23:15:03.532140Z`
- cache file hash：`sha256:e0e0808d909ef82a94406ed99cbec2f53d8cff26413b38b74c995c0ae27514be`
- cache content hash：`sha256:546fd3a8babb14c25e688837c202b02e0227846cd0e4dec379650b77d05bd8be`
- TWSE response hash：`sha256:7644c1a8af784c09f54670fd7413f536b13eb76c54d658058e8873d1aee32117`
- coverage：完整 2026 年、365 日、`planned_annual_closures`
- annual cache 的 `temporary_closure_coverage`：`not_covered`

因此 9/17 的 annual cache 確實有有效的 available/expiry/version/hash/coverage。這不代表 9/18 以後永遠有效；每次 scheduled evaluation 都會以當次 `checked_at` 重新通過 loader。capture 在 evaluation 之後、過期、竄改、缺檔或年度 coverage 不足都會 fail closed 為 `waiting_for_calendar`。

## 實作邊界與輸出

`app_module/official_maturity_calendar.py` 是 bounded、唯讀的 cache adapter：

- 不建立 schema、不讀 SQLite、不依賴 market rows、不發網路請求。
- annual cache 只會輸出 `annual_plan_only`，並明示未配置的 temporary closure 是 `unconfigured_future_events_unknown`。
- 若明確配置 temporary-closure cache，invalid/truncated/missing 候選會讓 planned diagnostic waiting；有效事件會附 closure date 與完整 evidence provenance。
- metadata 會保留 legacy stock-row maturity（`expected_maturity_date_basis=symbol_price_series_row_offset_legacy`），另加 `planned_official_maturity_date`、status、剩餘 official sessions，以及 source path/hash/available/expiry/coverage。
- legacy expected date 與 official planned date 不一致時標成 `maturity_calendar_comparison=blocked_mismatch`；不靜默校正。health 會計數並加入 `maturity_calendar_comparison_blocked`。
- `health.next_maturity_date` 只取尚未到期的 pending outcome 的 planned date，並輸出 `next_maturity_date_basis`。已過 planned date 但仍沒有 exact outcome price 的 row 不會被假裝成下一個 future pending。

9/17 helper-only read-only evaluation（event price date `2026-09-10`、`as_of_date=2026-09-17`）得到：

| horizon | planned date | planned status | remaining sessions | calendar scope |
|---:|---|---|---:|---|
| 5 | 2026-09-17 | planned_reached | 0 | annual_plan_only |
| 10 | 2026-09-24 | planned | 5 | annual_plan_only |
| 20 | 2026-10-13 | planned | 15 | annual_plan_only |
| 60 | 2026-12-09 | planned | 55 | annual_plan_only |

這些日期是 annual calendar 的計畫診斷，不是未來價格，也不保證收益或可成交 entry。既有 5d actual outcome 仍只由既有 legacy symbol-price-row-offset outcome contract 決定。

針對缺一個 official session 的 regression，測試資料只有 `2026-09-02`、`09-03`、`09-04`、`09-08`、`09-09` 五個 weekday stock rows，刻意缺 `2026-09-07`。legacy symbol-price-row-offset outcome price 是 `2026-09-09`，actual outcome 仍為 `READY`、`return_basis=close_to_close_event_date`；official planned date 是 `2026-09-08`，因此只產生 `blocked_mismatch` 診斷與 health blocker，沒有偷偷改 return 或 label。row-offset 壓縮 horizon 的正式 return-basis 修復列為下一個獨立 contract。

## 驗證結果

- `.venv\Scripts\python.exe -m pytest tests/test_scheduled_forward_outcomes.py tests/test_forward_performance_service.py tests/test_outcome_maturity_service.py tests/test_official_maturity_calendar.py -q -o addopts=`：**27 passed**。pytest 另有既有 `.pytest_cache` permission warning，沒有測試失敗。
- `.venv\Scripts\python.exe -m mypy app_module/official_maturity_calendar.py app_module/forward_performance_service.py app_module/scheduled_forward_outcome_service.py scripts/scheduled/run_scheduled_forward_outcomes.py`：**Success: no issues found**。
- changed Python files `py_compile`：通過。
- raw pytest log：`output/qa/maturity_calendar_20260918/pytest_targeted.log`。
- 沒有執行 production scheduled forward、formal runner、scheduler trigger，也沒有寫入 `D:/Min/Python/Project/FA_Data` 或任何正式 SQLite。
