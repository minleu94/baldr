# R026 投影後 sidecar shadow recheck

## 範圍與狀態

本切片只加強 invocation-local shadow identity 的 sidecar 觀察窗口，不切換既有 projection、DTO 或 receipt 行為。狀態為 **root bounded `ACCEPTED_SCOPE`**；接受僅限第三次 post-projection sidecar recheck 的 shadow 行為與 SQLite lease postcheck 順序。R026 仍為 `IN_PROGRESS`，`TMP-ML-01` 仍為 `ACTIVE`。

既有順序保留：第一次 sidecar evidence 在 SQLite lease 開啟後收集；provider 載入與 feature compute 後收集第二次，並在 projection 前驗證同一 schema、scope、cutoff 與摘要。新第三次收集在 `consumer.project_many()` 返回後、`lease.assert_unchanged()` 前。只有第三份 evidence 的完整 typed value 與前兩份相等、摘要相同，而且 SQLite lease postcheck 成功，才呼叫 shadow composer。

第三次 sidecar 收集失敗或觀察到變更時，shadow return 為 `None`；不加 warning、不撤銷已完成的 legacy projection，也不阻止既有 receipt 路徑。第三次收集後仍無條件執行 SQLite postcheck；若 SQLite 在 projection 期間改變，原本的 outer fail-closed 路徑仍撤回 projection、標為 unavailable 並略過 receipt。

## 驗證

Fresh short TEMP 命令：

```powershell
$env:PROFILE = 'test'
$env:DATA_ROOT = 'C:\t\r26sp_data'
$env:OUTPUT_ROOT = 'C:\t\r26sp_output'
.\.venv\Scripts\python.exe -m pytest `
  tests/test_r026_live_source_identity.py `
  tests/test_r026_sqlite_read_lease.py `
  tests/test_r026_historical_raw_snapshot_custody.py `
  tests/test_recommendation_service_calibration_integration.py::test_live_calibration_brackets_one_provider_snapshot_with_matching_source_evidence `
  tests/test_recommendation_service_calibration_integration.py::test_live_calibration_source_evidence_failure_keeps_rule_result_and_skips_ml `
  tests/test_recommendation_service_calibration_integration.py::test_live_calibration_revision_mismatch_fails_closed_and_scope_is_call_local `
  -q -o addopts= --basetemp C:\t\r26shadow_final\pytest_tmp
```

結果為 **32 passed／0 failed**。完整輸出記錄於 `C:\t\r26shadow_final\pytest.log`，SHA-256：`A3E416FA532299C349CD76071CCF20E9474F9230020D26E20F078423941D167A`。另一次 test-first 基線在 service 尚未有第三次收集時，三個新案例皆因只觀察到兩次 collector 呼叫而失敗。

新增案例固定：穩定時的順序為 sidecar 1 → provider load → feature compute → sidecar 2 → projection → sidecar 3 → SQLite postcheck → shadow compose → lease close → receipt；第三次 sidecar 改變及第三次 collector 例外都保留 projection/receipt 並回傳 `None`；projection callback 中的 SQLite commit 則仍由 lease postcheck fail closed。既有 pre-projection evidence mismatch 測試也在路由內通過。第三次 changed/raises case 的 receipt sink 是 mock；測試證明 receipt persist 呼叫與 persisted 狀態，不證明 receipt bytes 與 control run 逐 byte 相等。Source call shape 顯示 shadow identity 未傳入 receipt writer。

靜態檢查：`recommendation_service.py` 與 `live_source_identity.py` scoped mypy **2 files／0 issues**；三個變更 Python 檔 `py_compile` 通過；`scripts/quant_guard_linter.py` 的金融浮點與 look-ahead 檢查通過。包含兩個既有測試檔的較廣 mypy 命令回報 54 個測試碼 diagnostics；production scoped mypy 為乾淨結果，測試型別掃描不作為本切片通過證據。

## 限制

三次 sidecar 取樣是前後觀察，不是四個 namespace 的共同交易；第三次取樣後到 receipt 發布之間仍有時間窗口。短暫變更後還原的 ABA 不會被保證偵測；sidecar aggregate 與 SQLite lease 也沒有共同 generation 或原子提交。本切片不把 shadow identity 傳給 consumer、`PreparedMLRuntimeInputV1`、receipt、legacy capture 或 provenance，且不改變 `source_revision=None`、availability／quality／scope 的 `UNKNOWN`。這不是 runtime fail-closed cutover，也不關閉 R026／`TMP-ML-01`。

本次凍結 SHA-256：

- `app_module/recommendation_service.py`：`947BE55EA2F9A5B7B9325B6D544CD81AD97E9FDA39A9C6DC1F07932090DC8EF6`
- `app_module/recommendation/live_source_identity.py`：`3634E4E4FEE5D98B223CFA8598CBB47C14BB0009DDA9A747A48180AC31B2D2DE`
- `tests/test_r026_live_source_identity.py`：`184D79C728C0E782DB0C2C2C1A57F757FD0121B6502C49D57FE32E9646F93582`
- `tests/test_recommendation_service_calibration_integration.py`：`075B980B7BDC75AF9E25DAC239C1BB12167EAA10F61B25B1CDF896DF02EFA3F6`

## 獨立複核與接受界線

R023 獨立 fresh short TEMP 路由 `C:\t\r26post_d3f03293` 為 **32 passed／0 failed**，log `C:\t\r26post_d3f03293\pytest.log` SHA-256 `687396FFF60A3BC02217D76D8656A4836911A740FECFF751B98F7E48E71BFBF4`。Scoped mypy 2 source files／0 issues、`py_compile` 與 targeted diff-check 通過，未發現 P1/P2。Owner 路由為 32 passed；原 owner log `C:\t\r26shadow_final\pytest.log` SHA-256 `A3E416FA532299C349CD76071CCF20E9474F9230020D26E20F078423941D167A`。Root 依 frozen bytes 與獨立複核判本切片 bounded `ACCEPTED_SCOPE`。

此接受不涵蓋三個 sidecar namespace 與 SQLite 的原子快照、短暫變更後還原的 ABA，或第三次 sidecar sample 到 receipt 發布間的 TOCTOU；不代表完整 R026／`TMP-ML-01` 完成，也不授權 runtime handoff。
