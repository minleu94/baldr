# R026 live source identity shadow capture（bounded `ACCEPTED_SCOPE`）

## 範圍

本切片在既有 live calibration 呼叫中建立一份 invocation-local、不可變的 shadow join，將三類事實保持分欄：

- `HistoricalRawSnapshotCustodyFactsV1`：同次 `MLHistoricalSnapshotProvider.load()` 實際回傳列的 row-content hash、row-key hash、正規化 query scope 與 schema facts。
- `ValidatedSourceEvidenceV1`：同一次 calibration scope/cutoff 下，四個 sidecar namespace 的 before/after aggregate；第二次 collect 在 feature compute 後、model projection 前。只在兩者相等時組合，表示兩次 sample 相等。
- `SQLiteReadLeaseObservationV1`：service 在 `lease.load()`、feature/model projection 後呼叫 `lease.assert_unchanged()` 並返回的 invocation-local 記錄；其檢查點在 model projection 後、receipt persistence 前。它不是 SQLite durable generation、DB instance ID 或持久 source revision。

因此兩種檢查的窗口不同：第二次 sidecar collect 後到 receipt 的 sidecar 變更未再收集，不會被 sidecar aggregate 偵測；較晚的 SQLite lease postcheck 不會延長 sidecar sample interval。Receipt publication 也不與 sidecar/SQLite 檢查構成共同 transaction。

`HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1` 是版本化的邏輯 provider contract label：`twstock-historical-sqlite-four-table.v1`。它只描述四表讀取契約，不從 path、fingerprint 或測試值推導。Provider 將它以 optional kw-only 欄位傳在 `HistoricalRawSnapshot`；欄位不參與 equality/repr，預設 `None` 以維持舊 positional constructors。Custody capture 要求 production-carried ID，並驗 query scope source ID 完全相等；不提供或不匹配即拒絕新 shadow capture。

服務的私有 `_apply_recommendation_calibration()` 現在回傳 `LiveCalibrationSourceIdentityV1 | None`，同一呼叫點由實際 provider snapshot、before/after sidecar facts 與 projection 後的 lease postcheck 組出並回傳；目前唯一 production caller 不消費此回傳值。這提供可測的 invocation-local seam，尚未交給 runtime model consumer、`PreparedMLRuntimeInputV1`、receipt、legacy capture 或 provenance。新 composer 失敗只讓此 shadow return 為 `None`，不改既有推薦投影／receipt 行為。

## 驗證

Fresh short TEMP 命令：

```powershell
$qaRoot = 'C:\r26q\siu_99dad16c'
$env:PROFILE = 'test'
$env:TEMP = $qaRoot
$env:TMP = $qaRoot
$env:DATA_ROOT = Join-Path $qaRoot 'd'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'o'
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_live_source_identity.py `
  tests/test_r026_historical_raw_snapshot_custody.py `
  tests/test_ml_historical_snapshot_provider.py `
  tests/test_ml_historical_feature_builder.py `
  tests/test_ml_historical_feature_computation.py `
  tests/test_prepared_ml_input_contract.py `
  tests/test_r026_sqlite_read_lease.py `
  tests/test_recommendation_service_calibration_integration.py `
  -q -o addopts= --basetemp (Join-Path $qaRoot 'pt')
```

結果為 **79 passed／0 failed／12.51 秒**。Log：`C:\r26q\siu_99dad16c\pytest.log`，SHA-256 `6BA71D8DEB72802E5D20FFE7BAA68ECF61AF51F89D297810921F16A4908379F4`。新測試包含 provider-carried ID 對錯誤／缺失 source ID 的拒絕、query scope/sidecar/lease 身分不符負測、資料列 value 變更時 content hash 改變但 row identity hash 不變、以及 service 真實 lease/load 呼叫建立 shadow return。Composer 成功與合成失敗兩路均驗證推薦投影、模型欄位、receipt 呼叫與序列化 context 不受 shadow capture 影響。

靜態檢查：四個 production source 的 scoped mypy（`--follow-imports=silent`）**0 issues**；變更 Python 檔 `py_compile` 通過；`scripts/quant_guard_linter.py` 的 financial-float 與 look-ahead checks 通過；targeted `git diff --check` 通過。新測試已在 `qa/full_app_healthcheck/test_inventory.py` 登錄一筆 `service-oracle-recommendation` entry；未宣稱全庫 inventory guard 通過。

R015 對最終 source/test/inventory SHA fresh short TEMP 獨立重跑相同八檔 route，**79 passed**，log SHA-256 `C4E42E7942C58F575AB6D1BE2875971FC86152B05311BF1F4754B7CC1AAE6734`；scoped mypy 4 files／0 issues、compile 與 quant/look-ahead guard 通過，未發現 P1/P2。Root 判定此 live source identity shadow capture 為 bounded `ACCEPTED_SCOPE`；不是 R026/TMP-ML-01 完成或 runtime handoff 證據。

有一次較長系統 TEMP 路由為 75 passed／3 failed，失敗在三個既有 immutable receipt publication assertions：`test_real_consumer_producer_advice_workbench_ui_path`、`test_public_service_real_builder_saves_result_and_reverse_reads_receipt`、`test_real_consumer_independent_after_cost_baseline_reaches_advice_presentation`。該次沒有保留底層 OSError／path instrumentation。使用 `C:\r26q` 短 TEMP 後同一八檔路由通過；這與已知本機長路徑 receipt 問題相符，但不能將此重跑當成前次失敗根因的直接證明。前次失敗不計入通過。

## 限制與 gate

這份 shadow join 的證據界線是 service 內實際 `lease.load()`、同次 rows 的 custody builder、before/after sidecar collector 與 `lease.assert_unchanged()` 呼叫順序。`SQLiteReadLeaseObservationV1` 和 snapshot/evidence dataclass 也能被 Python caller 手工建構，型別本身不會密碼學證明同次呼叫；不能把任意手工物件說成 provider/lease provenance。

`SnapshotReference.source_id` 使用邏輯 provider contract ID；`source_revision` 仍為 `None`，availability/quality/scope 仍是 `UNKNOWN`。Raw SQLite rows、四 namespace digest 與 lease observation 各自分開，沒有將 sidecar digest 冒充 SQLite row generation。此切片不證明四 namespace 與 SQLite 是原子快照、不排除跨資源 ABA、receipt persistence 的 postcheck TOCTOU，亦不涵蓋 replay 中多次 provider calls 使用相同 durable generation。

本切片已 bounded `ACCEPTED_SCOPE`；不是 `PreparedMLRuntimeInputV1` handoff，也不改既有 projection、receipt、output bytes 或 model eligibility。第二次 sidecar sample 後的變更、跨資源原子性/ABA、receipt postcheck TOCTOU 與 replay 多次 provider call 仍未解。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## 後續 supported handoff 狀態（2026-10-10）

上列 `TMP-ML-01` 是本 shadow-capture slice 的 2026-09-25 checkpoint。依 [R026 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R026_IMPLEMENTATION_REPORT.md)，正常 `RecommendationService` NP1／NP2 supported caller/profile 遷移條件後續已 `CLOSED`；該結果不表示此 invocation-local shadow join 已交給 runtime model consumer、`PreparedMLRuntimeInputV1` 或 receipt。本文列出的跨資源、ABA 與 replay 限制仍在，R026 整體仍 `IN_PROGRESS`。
