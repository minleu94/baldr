# R021 Implementation Report — StockScreener concrete I/O boundary

## Status

`GATE_STATUS: ACCEPTED_SCOPE`

Root and the independent reviewer accepted the bounded R021 scope. The report's recorded evidence includes 24 focused passes, 28 affected Decision Desk UI passes, 84 required UpdateView workbench passes, Update QA at 22 passed / 0 failed / 5 skipped, and broad mypy at 680 source files with no issues. The Manual edit was limited to §5.2 after the R015 freeze; its personalization section was not edited. This individual scope acceptance does not release Wave 7–14 or establish formal-data acceptance. No files were staged or committed.

Root's gate readback additionally reports that a concurrent `tmp_path` failure-isolation rerun passed. The exact test node and aggregate count are not present in this report, so this remains supplemental root-reported evidence and is not counted as a separate suite result.

## Ownership change

| Responsibility | Before | After |
|---|---|---|
| Recent stock / industry SQLite frame | `decision_module.stock_screener_sqlite_reader.py`, imported by `StockScreener` and the app provider module | `data_module.stock_screener_reader.py`; `app_module.decision_data_providers` exposes recent frame adapters |
| Legacy stock fallback | `StockScreener` opened `DBManager`, ran the `daily_prices` / `technical_indicators` LEFT JOIN, scanned `technical_dir/*_indicators.csv`, and read each file | `data_module.stock_screener_reader.load_stock_fallback_frames()` owns path, SQL, CSV decoding, grouping and source diagnostics; an app adapter is injected |
| Legacy industry fallback | `StockScreener` opened `DBManager`, read `industry_indices`, resolved configured / technical / metadata CSV paths, and called `read_csv` | `data_module.stock_screener_reader.load_industry_fallback_frame()` owns those reads and path precedence; an app adapter is injected |
| Provider defaults | Recent providers were wired in the Qt composition; service and legacy UI constructors could still leave the decision object to self-load | `app_module.decision_service_composition.build_stock_screener()` creates all four concrete provider callables. `build_decision_service_composition()`, `ScreeningService`'s default path, and `ui_app/main.py` use this factory |
| Decision module | Imported the concrete reader and contained SQLite / DBManager / Path / CSV fallback | Consumes injected recent frames and fallback frames only. A direct constructor without providers no longer creates a hidden concrete reader |

`decision_module.stock_screener_sqlite_reader.py` was removed after a repository-wide caller search. Its only production references were the StockScreener seam and the Application adapters, both migrated here; its test was moved to the data reader. No external production caller remains, so no temporary alias or temporary-ledger entry was created. R029 does not need to retire a compatibility shim.

## Production and test caller inventory

| Caller | Before | After |
|---|---|---|
| Qt `MainWindow` composition | `build_decision_service_composition()` injected recent stock / industry adapters; legacy fallbacks remained inside `StockScreener` | Composition builds the screener through `build_stock_screener()` and injects recent plus fallback adapters before passing it to `ScreeningService` |
| `ScreeningService(config, industry_mapper)` without a supplied screener | Constructed a provider-free `StockScreener` that self-loaded | Calls the Application composition factory and receives all concrete providers |
| Legacy `ui_app/main.py` | Direct `StockScreener(config, industry_mapper)` | Calls `build_stock_screener(config, industry_mapper)` |
| `scripts/qa_validate_phase2_5.py`, `scripts/qa_validate_phase3_3b.py` | Use the `ScreeningService` default construction path | Continue through the now-composed `ScreeningService` factory path |
| `scripts/qa_validate_market_loop.py` | Direct construction with deterministic injected stock-frame providers | Unchanged. Both instances exercise frame/as-of contracts with fixture frames and do not represent a real-data acquisition path |
| Tests | Some direct constructions relied on implicit fallback | Fast-path tests inject recent providers; fallback tests inject explicit fallback providers; SQLite-first tests use the composition factory |

The search was `rg -n "StockScreener|stock_screener_reader" --glob "*.py"` plus a constructor-specific search over `app_module`, `ui_app`, and `scripts`. The remaining `decision_module/__init__.py` occurrence is a lazy class export, not construction or I/O. No other production constructor was found.

## Fallback and result matrix

| Recent provider outcome | StockScreener behavior | Data provider behavior |
|---|---|---|
| Non-empty `DataFrame` | Uses the existing recent-frame calculation branch | Returns the selected recent SQLite columns in their existing order and pandas dtypes |
| Empty `DataFrame` | Treats the read as successful; returns the existing empty result and does not call fallback | No legacy query or CSV scan is attempted |
| `None` | Calls the injected fallback provider | Recent reader returns `None` for disabled SQLite, missing DB, no recent dates, or query error; the fallback adapter then applies the legacy source order |
| Stock fallback SQLite has rows | Existing strong/weak fallback calculation receives grouped, sorted frames and the same source count | Read-only `daily_prices` / `technical_indicators` LEFT JOIN, duplicate columns removed, date and numeric normalization retained |
| Stock fallback SQLite unavailable, empty, or failed | Uses the existing per-stock fallback branch | Scans `technical_dir/*_indicators.csv`; retains file count and per-file read-skip logging |
| Industry fallback SQLite has rows | Existing strong/weak industry calculation receives the normalized frame | Read-only `SELECT * FROM industry_indices ORDER BY 日期 ASC` |
| Industry fallback SQLite unavailable, empty, or failed | Uses the existing industry frame calculation with CSV, or preserves the missing-source empty behavior | Candidate priority remains configured `industry_index_file`, `technical_dir/industry_index.csv`, then `meta_data_dir/industry_index.csv`; strong-side missing/unreadable warnings remain |

All SQLite connections in the new data reader use the `mode=ro` URI and `PRAGMA query_only=ON`. The migration does not write to the configured DB, alter its schema or data, or change CSV contents. Scoring, thresholds, date windows, filtering, ranking, reasons, output columns/order, and the existing strong/weak calculation branches were not changed. Reader warning/debug/info logging and fallback source counts remain in the data boundary.

## QA evidence

All pytest runs below used a fresh temporary `TEMP`/`TMP`, `PROFILE=test`, and `DATA_ROOT` / `OUTPUT_ROOT` under that temporary root unless the QA script created its own isolated double root.

| Gate | Result |
|---|---|
| `test_stock_screener_sqlite_reader.py`, `test_stock_screener_sqlite_first.py`, `test_stock_screener_provider.py`, `test_task_loop_02_contract.py`, `test_decision_data_providers.py`, `test_decision_service_composition.py`, `test_stock_screener_import_guard.py` | 24 passed, including integrated `None` → legacy SQLite stock JOIN / industry fallback, exception-log boundedness, and industry CSV priority |
| `test_ui_qt_decision_desk_main_integration.py` after fixture repair | 13 passed |
| Decision Desk affected UI batch: `test_main_window_coordinator.py`, `test_ui_qt_dashboard_view.py`, `test_ui_qt_weak_market_views.py`, `test_ui_qt_market_regime_view.py`, `test_ui_qt_decision_desk_main_integration.py` | 28 passed |
| Required UpdateView workbench smoke, `test_ui_qt_update_view_workbench.py` | 84 passed |
| `qa_validate_update_tab.py`, executed from a temporary script copy so existing `output/qa/update_tab` artifacts were not overwritten | 22 passed, 0 failed, 5 skipped |
| R021-module mypy with `--follow-imports=skip` | 5 files, no issues |
| `py_compile` on changed Python modules/tests | Passed |
| `git diff --check` | Passed |
| Required broad mypy over `ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime` | Passed after R015 and R023 freeze: 680 source files, no issues. |

### Independent review P2 remediation

The independent reviewer found that the strong/weak fallback exception handlers interpolated `data_item` into an f-string. After the extraction, `data_item` is a `DataFrame`, so a rare row-processing exception could emit the full table and lose its source filename. Both handlers now log a bounded `fallback_data.source:stock_code` label via logger arguments; calculation, returned schema, and skip-count behavior are unchanged. `test_stock_fallback_error_log_names_source_without_dumping_frame` injects a synthetic reason-generation error, verifies the `csv:2330` source label, and asserts a unique DataFrame sentinel is absent from the log.

The reviewer also suggested locking the existing industry CSV precedence. `test_industry_csv_fallback_prefers_configured_file_over_technical_and_metadata` creates all three candidate files simultaneously and confirms the configured path wins over technical and metadata paths. After these changes, the fresh-temp R021 focused suite passed 24 tests, the affected Decision Desk UI batch passed 28 tests, scoped mypy passed for 5 files, py_compile passed, and `git diff --check` passed. The bounded logging and precedence repairs are included in the accepted scope.

### Ambient UI fixture repair and initial red result

The initial UI batch was **15 passed / 13 failed**. The first named failure was `test_main_window_owns_one_decision_desk_as_market_overview_index_zero`. Each of the 13 failures in `test_ui_qt_decision_desk_main_integration.py` came from `_build_main_window()` using `MainWindow.__new__` and bypassing normal initialization, leaving three now-required `StockResearchWorkspace` inputs absent: `stock_research_report_service`, `decision_outcome_journey_service`, and `decision_continuity_controller`. This occurs before the R021 provider composition path; `ui_qt/main.py` was not changed by R021.

As a separate ambient QA fixture repair, the test fixture now supplies those three minimal service stubs and its navigation expectation includes the existing `個股研究` workspace. No product code or additional product behavior was changed. The integration file then passed 13/13 and the full affected UI batch passed 28/28. The initial red counts and their attribution remain recorded here rather than being relabeled as an R021 baseline.

## Manual update

After R015 froze `docs/07_guides/APPLICATION_MANUAL.md`, §5.2 “強勢與弱勢個股”'s existing “效能邊界” paragraph was replaced with the recent SQLite-first outcome semantics, empty `DataFrame` versus `None`, stock JOIN → indicator CSV order, industry SQLite → configured / technical / metadata CSV priority, read-only guarantee, and 0-row diagnosis steps. Existing entry steps and ranking interpretation were preserved. No R015 personalization text was changed.

## Final verification after Manual update

Focused tests were run with fresh `TEMP`/`TMP`, `PROFILE=test`, and `DATA_ROOT` / `OUTPUT_ROOT` set under the new temporary root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_stock_screener_sqlite_reader.py tests/test_stock_screener_sqlite_first.py tests/test_stock_screener_provider.py tests/test_task_loop_02_contract.py tests/test_decision_data_providers.py tests/test_decision_service_composition.py tests/test_stock_screener_import_guard.py -q -o addopts=
```

Result: **24 passed**. Broad static check:

```powershell
.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
```

Result: **680 source files checked, no issues found**. R021 scoped mypy checked 5 changed source files with no issues; `py_compile` on changed Python modules/tests and `git diff --check` also passed. Root and the independent reviewer subsequently accepted the bounded R021 scope; the Wave 7–14 release status remains governed by the existing C1/Wave 6 checkpoint.
