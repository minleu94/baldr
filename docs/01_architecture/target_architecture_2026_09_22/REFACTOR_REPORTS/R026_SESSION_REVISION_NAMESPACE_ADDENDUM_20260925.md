# R026 historical-session revision namespace evidence Slice 4

> **時點／範圍提示（2026-10-10）：** 本文的 `R026 IN_PROGRESS`／`TMP-ML-01 ACTIVE` 是 2026-09-25 的單一 session namespace evidence slice 快照。後續 accepted scope 僅涵蓋 NP1／NP2 supported caller/profile 的有界 runtime migration；跨 namespace、ABA 與其他 source-evidence 範圍仍須分開判讀。現行範圍看 [R026 implementation report](R026_IMPLEMENTATION_REPORT.md) 與 [Model Assignments](../REFACTOR_MODEL_ASSIGNMENTS.md)，整體狀態看 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md)。

**日期：** 2026-09-25  
**狀態：** Root 以 fresh TEMP 六檔路由 **91 passed** 獨立判定本 session PIT evidence collector 為 bounded `ACCEPTED_SCOPE`。此接受不涵蓋 `validate_session_replacement()` 的 legacy scan、跨 namespace aggregate、ABA 或 ML 接線；R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

本附錄記錄 `data_module/historical_session_revision.py` 的單一 namespace evidence collector。它只摘要本次 session revision checker 實際驗證的檔案 bytes，不連接 provider、不建立跨 namespace aggregate，也不代表 PreparedMLInput 或 ML cutover 已完成。

## 契約與既有 API

新增 `collect_session_revision_evidence(database_path, decision_date) -> ValidatedNamespaceEvidenceV1`。collector 沿用 `_root(database_path) / RECEIPT_DIR` 與現行直層 `*/revision.json` run 佈局：

- 只有固定 receipt root 真正缺少路徑元件，或已成功完整掃描後沒有 revision marker，才回傳 `EMPTY`。
- 完整鏈結驗證成功後回傳 `PRESENT`。`pending` 包含 marker/plan；`applied` 包含 marker/plan/receipt；`rolled_back` 包含 marker/plan/rollback。合法 before-start pending 與 rolled-back 狀態都保留 `PRESENT` 語意。
- 每個 JSON 檔的 parse 與 SHA-256 都使用同一次 `read_bytes()` buffer；marker 的 UTF-8 decode 仍遵守舊解析方式。計畫與終態收據的 hash-link 與 JSON parse 使用相同 bytes。Rollback 維持原本 hash-link 驗證；沒有新增 rollback schema 或欄位要求。
- `role_id` 使用 receipt root 下 lexical run 相對路徑的 UTF-8、無 padding base64url，前綴 `run_`，不依列舉順序或檔案內容產生。相同 bytes 放在不同 run path 會有不同 role。
- 掃描錯誤、PermissionError、dangling link/junction、root 外解析、重複 resolved run alias、讀取前後 path identity 改變、壞鏈或 PIT cutoff 命中均 fail closed；失敗不回傳局部 evidence。

`_validated_plan(..., capture=...)` 是舊與新入口共用的鏈驗證路徑；`_plan(path, database_path)` 仍回傳原 `(marker, plan)` tuple。`assert_session_revision_safe(database_path, decision_date)` 成功時仍回傳 `None`，並沿用原 PIT cutoff 錯誤文字。`validate_session_replacement`、repair writer、CSV overlay 與其 public ABI 本 slice 未修改。

Windows junction 測試在目前環境實際建立並執行，沒有 skip：測 receipt-root/run dangling junction、root 外 junction、重複 resolved run alias、單一 root 內 alias 與 read-time retarget。單一 root 內 alias 保留 lexical role；兩個 immediate run entry 指向同一 resolved run 則拒絕。

## 驗證

Fresh TEMP 根：`C:\Users\archi\AppData\Local\Temp\r26_sess_fda23e19`。測試使用 `PROFILE=test`、`DATA_ROOT=<TEMP>\data`、`OUTPUT_ROOT=<TEMP>\output`，並以新 pytest basetemp 執行：

```powershell
$r026Temp = Join-Path $env:TEMP ('r26_sess_'+[guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $r026Temp | Out-Null
$env:PROFILE='test'
$env:DATA_ROOT=(Join-Path $r026Temp 'data')
$env:OUTPUT_ROOT=(Join-Path $r026Temp 'output')
python -B -m pytest `
  tests/test_r026_session_revision_evidence.py `
  tests/test_historical_session_repair.py `
  tests/test_daily_price_revision_write_guard.py `
  tests/test_daily_price_source_revision_overlay.py `
  tests/test_r026_market_revision_evidence.py `
  tests/test_r026_source_revision_evidence_contract.py `
  -q -o addopts= -p no:cacheprovider --basetemp (Join-Path $r026Temp 'p')
```

結果 **91 passed**，無失敗。Scoped mypy：`mypy data_module/historical_session_revision.py tests/test_r026_session_revision_evidence.py`，2 files / 0 issues；上述 source、test、inventory 三檔 `py_compile` 通過；R026 session 與並行 R020 scorer test 的 inventory membership 均存在；scoped `git diff --check` 通過。實作前 red route 的 12 個新 session tests 因 collector 尚不存在而失敗，該 red 僅記錄預期差異，不列為通過證據。

Frozen SHA-256：

- `data_module/historical_session_revision.py`: `EFB50151445DAC7DE02D6448CBD33193D80A093CF3D524BADAC834C8058DF20D`
- `tests/test_r026_session_revision_evidence.py`: `81AB2EC91E46CD70ED998E07BA250C5036C1527620401E5AE58326AFE858DA76`
- shared `qa/full_app_healthcheck/test_inventory.py`: `C8388DF198BDF5D681DF35C7EF8162D13F9AEEE7F37F28D60C86C59D9C74C463`；新增本測試 entry 前重新讀取 inventory，保留已存在的 R020 entry。

## 限制與剩餘 gate

此 slice 的完整掃描與 link containment 僅由新 evidence collector 使用。`validate_session_replacement()` 仍保留既有 `glob('*/revision.json')` 讀取路徑，並經 `_plan(..., capture=None)` 驗證；本 slice 沒有改變該 write/import guard 的 junction、PermissionError 或 incomplete-scan 行為，不能宣稱所有 session consumers 都已 fail closed。`assert_session_revision_safe()` 則使用新 collector，因此其不完整掃描會 fail closed。

讀前後 path resolve 只能比對兩次觀察到的身分，不能排除兩次檢查之間改指再還原的 ABA；多檔鏈沒有共同原子快照，跨 namespace 與跨資源仍無共同 transaction。這些限制、其他 namespace identity、provider 多次呼叫的同版本保證、active pointer/model race、receipt/readback 與 production PreparedMLInput 接線仍是後續 gate。不得以本 slice 關閉 `TMP-ML-01` 或宣稱 R026 完成。

**有界複核狀態：** 本 slice 已獲 root `ACCEPTED_SCOPE`（fresh TEMP 六檔 91P）；`validate_session_replacement()` legacy scan、跨 namespace aggregate、ABA 與 ML 接線仍未驗證，R026 維持 `IN_PROGRESS`、`TMP-ML-01` 維持 `ACTIVE`。
