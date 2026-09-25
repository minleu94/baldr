# R023 基本面／月營收資料契約遷移報告

## 結果

月營收與 availability data records/diagnostics 現在只保存來源、日期、證據與 revision facts；FactorQuality、FactorDiagnostic 與 FactorRecord 的映射集中在 `decision_module/factors/fundamental_adapters.py`。SQLite schema、查詢條件、revision history、CSV parser 和 CLI v1 JSON 欄位維持相容。未讀取、重抓或回填正式資料；沒有修改 statement／valuation 計算、因子公式、threshold 或 ML features。

**目前 Gate：`ACCEPTED_SCOPE`（2026-09-23；R024 修復後恢復）。** R023 原 route 為 139 passed；之後 root 因六項 statement `.quality` runtime regression 重開 gate，該回歸由 R024 修復。R024 後的 R023 regression route 為 152 passed；root 另以 fresh TEMP／`PROFILE=test` 獨立執行 R024 完整 20-module route，107 passed，檢查擴充後的任意 `decision_module` import AST guard 與報告後，恢復 R023 並接受 R024 的 bounded engineering scope。六項原始失敗沒有保存 node IDs；其共通 failure signature、實際 parity 修復與測試證據見 [R024 實作報告](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R024_IMPLEMENTATION_REPORT.md)。兩項 scope acceptance 均不代表 Wave 7–14 釋出或正式資料接受。

## 舊／新 type 與輸出映射

| 契約 | 遷移前 | 遷移後與 parity |
| --- | --- | --- |
| `FundamentalAvailabilityResolution` | `available_date`、`FactorQuality`、`FactorDiagnostic` | `Availability` 與 `SourceDiagnostic`。Decision adapter 對 UNKNOWN／無公告日／有公告日映射回 MISSING／DEGRADED／OBSERVED。診斷 code、message、順序和舊 factor name 由 adapter 保留。 |
| `FundamentalAvailabilityOverride` 與 `revision_history` | 日期／來源／revision facts 加上 `FactorQuality` | 保留 announced/available dates、source/version、evidence class、hash、revision、parent 與 mode；移除 data-owned quality。revision chain 和排序未變。 |
| `MonthlyRevenueRecord` | Decimal revenue、日期、來源版本與 `FactorQuality` | revenue 仍為 `Decimal`，日期與來源版本不變。availability provenance 只在 parser 收到唯一明確 override 時保留；SQLite provider 不為 row 猜 revision。舊 SQLite quality 欄以未解讀 wire literal 保存，由 decision adapter 解讀為 FactorQuality。 |
| availability／revenue parser、history、merge、backfill、harvest diagnostics | `FactorDiagnostic` | `SourceDiagnostic` 帶 code/message、kind、market/period、source id/version/hash、evidence、availability date、revision、parent。Decision adapter 依 kind/market 轉回舊 FactorDiagnostic；保留 code/message/順序。 |
| 舊 DB 寫入 | 寫入 FactorQuality 的舊字串值 | 仍寫同一 SQLite `quality` literal；已讀取的六種舊 literal (`observed`, `estimated`, `degraded`, `missing`, `neutral`, `stale`) 均有 round-trip fixture。這是 persistence 相容欄位，不是新的 data quality enum。 |
| CLI／app 輸出 | `monthly-revenue-availability-merge.v1` 的 `diagnostics[].factor_name`、UpdateService FactorDiagnostic dict | data model 不含 factor name；apply CLI 與 UpdateService 在輸出邊界用 decision mapping 還原舊 v1 欄位。history CLI 的 `diagnostics_by_source` 改從 `market` 事實取值，既有 TWSE/TPEx key 不變。 |

月營收 provider 的 SQLite SQL 仍以 `available_date <= decision_date` 篩選，並保留原有 `(stock_code, period, as_of_date, announced_date, available_date)` mapping 關聯、source-version 內容衝突處理與排序。Decimal 金額、int/string 因子輸出、缺值 diagnostics 及 future-row skip 均由固定 synthetic fixtures 鎖定。

## 同日期多 revision 的 identity 邊界

同一 `(stock_code, period)` 的兩個正式 availability revisions 即使日期完全相同，`revision_history` 仍保留兩筆各自的 source version、hash、revision 和 parent revision。SQLite provider 沿用日期 tuple 關聯，並以「任一歷史 mapping revision 日期匹配」讀取已保存 row；`MonthlyRevenueRecord` 不會被填入其中一個 revision。兩筆 mapping 只能證明 key/date-level custody；若需要 row-level revision，資料 schema 必須新增能唯一識別 row 與 mapping revision 的 identity，現有日期 tuple 不足以唯一連結。

## Look-ahead 自查

- resolver 仍拒絕早於 period end 或 announcement 的 available date；無有效 date 時回傳 UNKNOWN 並保留相同 missing/invalid diagnostic。
- provider 保留 `available_date <= decision_date` SQL filter；決策層 FactorGate 對未來 available date 維持 skip。現有與新增 fixtures 分別涵蓋 provider 未來 row、future factor gate，以及 revision append 後的歷史決策。
- revision history 仍保留舊日期供歷史 decision 使用；較晚 revision 不回填成舊 decision 可見資料。相同日期多 revision 不推測哪一個 revision 屬於 SQLite row。
- 本次沒有新增計算或裸 `float`；月營收 raw value 與 revenue factors 繼續用 `Decimal`，既有 int/string factor output 未變。

## Import owner 與 caller 清冊

| Caller | 遷移前 | 遷移後 |
| --- | --- | --- |
| `fundamental_availability.py`、`fundamental_availability_sources.py`、`fundamental_availability_entrypoint.py`、`fundamental_data.py` | 直接建立或回傳 decision factor diagnostics/quality | 回傳 pure availability/source contracts；唯一月營收 factor 映射在 decision adapters。 |
| `monthly_revenue_availability_history.py`、`monthly_revenue_availability_merge.py`、`monthly_revenue_backfill.py`、`monthly_revenue_recovery.py`、`monthly_revenue_snapshot_harvester.py` | diagnostics 是 FactorDiagnostic；backfill/recovery 從 FactorQuality 寫舊欄位 | 回傳 SourceDiagnostic；persistence writer 使用舊 wire serializer，不再把 factor enum 放進 data record。 |
| `fundamental_sqlite_provider.py` 月營收路徑 | 讀 DB row 時建立 FactorQuality | 只保存舊 quality wire literal 並產生 source record；月營收 helper 沒有 decision factor import。 |
| `decision_module/factors/fundamental_adapters.py` | 直接消費帶 FactorQuality 的 data record | 消費純 data records，映射 availability quality、source diagnostics 與既有 FactorRecord；factor 計算與輸出欄位保持原樣。 |
| `apply_monthly_revenue_availability_candidate.py`、`build_monthly_revenue_availability_history.py` | 讀 FactorDiagnostic.factor_name 統計或序列化 | 由 SourceDiagnostic.market/kind 投影原 CLI wire name/key，data contract 不回傳 factor name。 |
| `UpdateService.dry_run_mops_monthly_revenue_backfill` | 呼叫 FactorDiagnostic.to_dict | 在 app 邊界經 decision adapter 產生相同四欄 diagnostics dict。 |

## R024 與後續 owner

R024 已完成 statement／valuation source contracts、availability facts、diagnostics 與 factor policy 的 owner 搬移；上述 R024 檔案清單及各 caller、SQLite／CLI 相容性、PIT 與 gate evidence 見 [R024 實作報告](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R024_IMPLEMENTATION_REPORT.md)。statement 原有 quality／diagnostic parity 由 decision adapter/output boundary 還原；source records 不反向依賴 decision。

R023/R024 以外仍有 `company_registry.py` 與 `tpex_daily_price_backfill.py` 的 data→decision/factor imports，應由相應 owner 排定；不推定為 R024 scope。ML compatibility 及 company registry／TPEx 來源行為未在 R023/R024 本次變更。

## 驗證

所有測試使用新的 TEMP `PROFILE=test`、獨立 `DATA_ROOT`／`OUTPUT_ROOT`，沒有觸碰正式資料路徑。目標路由涵蓋 fundamental data/availability/source/provider、statement shared-resolver 相容、factor adapter/revenue pack、history/merge/backfill/recovery/harvester、UpdateService 與 CLI wire fixtures。

- 測試範圍是 R023 vertical 與必要的 statement shared-resolver、UpdateService/CLI wire compatibility tests；沒有執行完整 repository pytest。Fresh TEMP 路由命令：

```powershell
$profileRoot = Join-Path $env:TEMP ('r023-profile-test-' + [guid]::NewGuid().ToString('N'))
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $profileRoot 'data'
$env:OUTPUT_ROOT = Join-Path $profileRoot 'output'
New-Item -ItemType Directory -Path $env:DATA_ROOT -Force | Out-Null
New-Item -ItemType Directory -Path $env:OUTPUT_ROOT -Force | Out-Null
& .\.venv\Scripts\python.exe -m pytest tests\test_fundamental_data.py tests\test_fundamental_availability.py tests\test_fundamental_availability_sources.py tests\test_fundamental_availability_entrypoint.py tests\test_fundamental_sqlite_provider.py tests\test_fundamental_factor_adapters.py tests\test_revenue_factor_pack.py tests\test_r023_fundamental_contract_characterization.py tests\test_r023_fundamental_dependency_guard.py tests\test_fundamental_statement_availability_sources.py tests\test_monthly_revenue_availability_history.py tests\test_monthly_revenue_availability_history_cli.py tests\test_monthly_revenue_availability_merge.py tests\test_monthly_revenue_backfill.py tests\test_monthly_revenue_recovery.py tests\test_monthly_revenue_snapshot_harvester.py tests\test_update_service_monthly_revenue_status.py -q -o addopts= -p no:cacheprovider
```

- Fresh TEMP 目標路由：`139 passed`。
- Broad mypy 命令：`python -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`，`680 source files`，無 errors。
- 所有本次變更的 Python 檔通過 `py_compile`。
- `git diff --check` 通過。

沒有改變產品 UI 或操作步驟；CLI JSON schema 仍為 v1 並保留舊 diagnostics wire fields，因此不需改操作手冊。本任務也沒有編輯由 R015 管理的 `APPLICATION_MANUAL.md`。
