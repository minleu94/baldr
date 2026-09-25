# R026 Live Calibration SQLite Read-Lease Wiring

日期：2026-09-25  
範圍：live recommendation calibration 單次 SQLite snapshot 與 sidecar projection 的 lease 協調。這是 bounded service slice；R026 與 TMP-ML-01 仍未結案。

## 實作與來源

`RecommendationService._apply_recommendation_calibration` 現在在同一個 `MLHistoricalSnapshotReadLease` 內依序執行來源 evidence before、`lease.load()`、feature build、來源 evidence after、active identity/cost/baseline reads、`project_many()`，再呼叫 `lease.assert_unchanged()`。lease 成功離開後才發布 projection/context 並嘗試寫 receipt。來源 identity、aggregate digest 或 lease postcheck 發生例外時，lease 先關閉；服務丟棄 local projection、保留 rule score、清除 DTO 與 context 中的 model projection 欄位，標記 unavailable，不嘗試寫 receipt。

本切片檔案 SHA256：

| 檔案 | SHA256 |
| --- | --- |
| `app_module/recommendation_service.py` | `B66C6BF37A8EF63798FF6AAF2EB25603852BEEBB23C4378920425F804EB3D0EF` |
| `data_module/ml_historical_snapshot_provider.py`（未修改） | `0223A3665B68DB950CF806D87F7C3CC3BBE925277813D083F7AFBB3A2A8E3928` |
| `tests/test_r026_calibration_legacy_preparation_baseline.py` | `66326C921F7882A7D82EC479CF012BE171577F99BA7FD07FDEA8C960EC40F2C5` |
| `tests/test_recommendation_service_calibration_integration.py` | `FE4DC7EF45D47A52E9A9F37BCB5671C387222D230DEBE2289FFCEF747AE95FF7` |

## 驗證收據

環境：Python 3.11.9、Windows 10 build 26200、NumPy 2.3.5、Pandas 2.3.3、SQLite 3.45.1。每個 pytest 路由使用獨立短 TEMP 根目錄，並將 `PROFILE=test`、`TEMP`、`TMP`、`DATA_ROOT`、`OUTPUT_ROOT` 指向該目錄。

聚焦回歸命令：

```powershell
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_calibration_legacy_preparation_baseline.py::test_live_source_update_after_snapshot_load_fails_closed_before_receipt_publication `
  tests/test_r026_calibration_legacy_preparation_baseline.py::test_live_source_update_during_project_many_discards_projection_and_skips_receipt `
  tests/test_recommendation_service_calibration_integration.py::test_live_calibration_brackets_one_provider_snapshot_with_matching_source_evidence `
  tests/test_recommendation_service_calibration_integration.py::test_live_calibration_source_evidence_failure_keeps_rule_result_and_skips_ml `
  tests/test_recommendation_service_calibration_integration.py::test_live_calibration_revision_mismatch_fails_closed_and_scope_is_call_local `
  tests/test_r026_calibration_legacy_preparation_baseline.py::test_provider_public_read_entries_release_connections_on_success_and_error `
  -q -s -o addopts= -p no:cacheprovider
```

結果：16 passed。log：`C:\t\r26lease03315b65\focused.log`，SHA256 `DC0E53F9D6F4A03AF9348AD261912F00BEF5ACFAB80F2B7C48E3EA92CD230CE6`。

三檔相鄰路由命令：

```powershell
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_sqlite_read_lease.py `
  tests/test_r026_calibration_legacy_preparation_baseline.py `
  tests/test_recommendation_service_calibration_integration.py `
  -k 'not slow' -q -s -o addopts= -p no:cacheprovider
```

結果：39 passed in 11.85s。log：`C:\t\r26fulld02dd078\three-file.log`，SHA256 `BE6B430002782267E2D19836F502744CC141919C8EB21892D42C8F36555BDB7D`。

另執行：

- `python -m py_compile`：service、provider、兩個測試檔通過。
- `python -m mypy app_module/recommendation_service.py data_module/ml_historical_snapshot_provider.py`：2 source files，0 issues。
- `git diff --check`：通過；Git 僅提示既有 LF/CRLF 轉換警告。

有一次較長 TEMP 路徑的三檔試跑讓三個 receipt writer 測試遇到 Windows `os.link` 的 `FileNotFoundError`；相同測試改用短 TEMP 根目錄後通過。本 note 的驗收數字只採用上列短路徑新進程結果。

## 關鍵測試證據

- `test_live_calibration_brackets_one_provider_snapshot_with_matching_source_evidence` 固定 lease open、來源 evidence、load、feature、projection、postcheck、close 與 receipt 的順序。
- `test_live_source_update_after_snapshot_load_fails_closed_before_receipt_publication` 保留已捕獲 snapshot 的資料觀察，同時驗證讀取期間來源變更會在 receipt 發布前 fail closed。
- `test_live_source_update_during_project_many_discards_projection_and_skips_receipt` 在 `project_many()` 中更新來源；驗證 postcheck 在 callback 返回後、projection 發布前執行，並丟棄 local DTO/context projection，不呼叫 receipt writer，rule total 不變。
- source-evidence failure 與 provider read-entry success/error 測試驗證失敗和一般返回都關閉 lease。

歷史測試 `test_legacy_source_update_after_snapshot_load_uses_captured_snapshot_and_still_attempts_projection` 已遷移為上列 fail-closed 現行預期；保留的 captured-snapshot/hash 觀察僅說明修補前行為，不代表目前仍會投影或寫 receipt。

## 限制

lease postcheck 能在同一 SQLite connection/read transaction 的生命週期內偵測本切片測得的來源變更。source evidence aggregate 本身不是 SQLite generation token；本 slice 不保證跨 connection、WAL/ABA 或多資源原子性。`lease.assert_unchanged()` 與 receipt persistence 之間仍有時間窗口，receipt 檔案寫入也不與 SQLite transaction 原子提交。此證據只涵蓋 live 單次 load/projection；不涵蓋 historical replay 多次 provider call，也不關閉 R026/TMP-ML-01。

## 獨立複核與 bounded gate

R015 以 fresh TEMP 重跑本 note 所列三檔路由，結果 39 passed，未發現執行期 P1/P2；root 另獨立重跑 39 passed，並確認 service/provider source mypy 與 `py_compile` 通過。此結果接受的是 live calibration 中單次 provider `load()` lease：sidecar 前後 identity 與 SQLite postcheck 通過後才發布 model projection、再嘗試 receipt。

Frozen source 與 integration test SHA 見「實作與來源」表；R015 獨立 route log SHA 為 `BE6B430002782267E2D19836F502744CC141919C8EB21892D42C8F36555BDB7D`。Root 的 39P 是另一份獨立執行結果，不與 R015 數字合併。

此接受不關閉 R026 或 `TMP-ML-01`。`assert_unchanged()` 與 receipt persistence 間仍有 TOCTOU；sidecar aggregate 與 SQLite 不在共同交易，`data_version`／stat 不保證 durable generation 或排除 ABA；亦未驗證 historical replay 的多次 provider call 共用同一來源版本。
