# R026 跨資源 source revision identity 決策附錄

**日期：** 2026-09-24
**狀態：** 合成 TEMP 證據與架構裁決；Slice 1 純契約已實作並有 focused QA，尚待獨立 review；未接線、未驗 production cutover。
**關聯：** [R026 實作報告](R026_IMPLEMENTATION_REPORT.md)、[PreparedMLInput 與 transient runtime input 設計裁決](R026_PREPARED_RUNTIME_INPUT_DECISION_ADDENDUM_20260924.md)、`REFACTOR_TASKS/R026.md`、FINAL_ML_COMPATIBILITY_CONTRACT。

## 裁決摘要

`MLHistoricalSnapshotProvider` 的 SQLite read transaction 已在單次 provider 呼叫內固定資料庫查詢視窗，但 daily-price repair receipt 與其他 revision evidence 是 SQLite 以外的檔案來源。現有 checker 沒有將每個實際驗證的 sidecar bytes 身分帶回 provider；因此 SQLite `data_version` 與檔案 size/mtime guard 都不能證明跨資源 revision 在整次準備過程保持一致。多次 provider 呼叫也沒有共享同一來源版本的 durable identity。

下一個 R026 source gate 必須讓各 revision checker 回傳不可變的驗證摘要，摘要綁定 checker 實際讀取並驗證的 bytes，並把明確的空集合也表示成可比較身分。每個受保護的準備範圍要在工作前後取得摘要；只有身份相同且完整時才可繼續。身份缺失、讀取不完整或前後不同時，該次 ML input 必須標記 unavailable 並 fail closed。這項要求尚未實作；`R026` 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## 合成 TEMP 證據：receipt precheck 與 SQLite `BEGIN` 之間的間隙

使用既有 R026 synthetic SQLite fixture，將 `PROFILE=test`、`DATA_ROOT`、`OUTPUT_ROOT` 指向新建 TEMP 根 `<USER_HOME>\AppData\Local\Temp\r26_sidecar_c825fe`。在自動 repair receipt 路徑建立有效的 direct daily-price receipt，讓其來源日期 `2024-01-23` 晚於決策日 `2024-01-22`。透過 provider 模組的 checker wrapper 先呼叫真實 `check_daily_price_source_revision()`，確認並記錄其驗證摘要；checker 返回後、provider 執行 `BEGIN` 前，受控地把同一 receipt 改成來源日期 `2024-01-21`。

- precheck 當時讀到的 receipt SHA-256 為 `a379393ddacb983200b7bae7f9948599bca95de9177cbf52d2f699caa5eb021e`；改寫後檔案 SHA-256 為 `e91e088c2370e2783dba01e0df0eaecfa225b090c7c68c56e47be317720535d4`。
- 決策日為 `2024-01-22`。receipt 改寫後已涵蓋 cutoff；然而同一次 `load` 仍成功回傳，`feature_as_of_date` 為 `2024-01-21`。SQLite 大小與 mtime 未改，因這次 race 只改了 sidecar。
- 緊接著重新執行真實 checker，會因新 receipt 涵蓋 cutoff 而拒絕。這證明 precheck 曾驗證的 bytes 與 provider 後續完成的讀取不是同一個可證明的 revision。

此 probe 精確覆蓋「direct receipt precheck 已返回 → SQLite `BEGIN` 尚未開始」的間隙，並以 TEMP synthetic data 執行；沒有讀寫正式資料。因 provider 的 `source_fingerprint` 只反映 SQLite 路徑、size、mtime 與 schema，sidecar-only 改寫不會改變該 fingerprint。這是依目前 fingerprint 組成作出的限制判斷，不能把該 fingerprint 當成 sidecar 或完整來源版本的身分。

此證據不涵蓋 checker 在多個 sidecar 間逐一讀取時發生更新，也不證明 checker 讀取窗口本身原子一致；它只重現 direct receipt precheck 與 SQLite 交易開始之間的 TOCTOU。SQLite 同連線 `data_version` 檢查無法發現不觸碰 SQLite 的 JSON 更新。

## 現有 revision chain 與身份缺口

`check_daily_price_source_revision()` 不只檢查 direct daily-price receipt。它依序執行市場資料、歷史交易時段、排除日價格來源的 revision guards，之後才檢查 direct receipt candidates：

| Namespace | 現有檢查來源 | 身分傳遞限制 |
| --- | --- | --- |
| Market revision | `data_module/formal_market_revision.py` 的 `assert_market_revision_safe()`；掃描正式市場 revision marker，並驗 marker、journal、plan 與 receipt/rollback hash | 驗證成功回傳 `None`，呼叫端沒有收到實際驗證 bytes 摘要 |
| Historical session revision | `data_module/historical_session_revision.py` 的 `assert_session_revision_safe()`；讀 session revision marker、plan 及 receipt/rollback | 驗證成功回傳 `None`，沒有明確的已驗證集合身分 |
| Excluded daily-price revision | `data_module/excluded_daily_price_revision.py` 的 `assert_excluded_source_revision_safe()`，使用 `load_exclusion_evidence()` 驗 marker、plan、journal、receipt/rollback、source archive 與市場鏈 | evidence 內有多個 hash，但 guard 最後回傳 `None`；這些 hash 未形成呼叫端可比較的 immutable summary |
| Direct daily-price repair receipt | `data_module/ml_daily_price_revision_gate.py` 的 receipt candidate discovery 與 `_check_receipt()` | 有 direct receipt 時可回傳 receipt 摘要；沒有 direct receipt 時回傳 `None`，無法分辨「完整檢查後沒有 receipt」與「沒有可供下游確認的 revision identity」 |

provider 在 `load` 與 `load_forward_price_window` 將這些 checks 放在 SQLite read transaction 外；`list_trading_dates` 不檢查 daily-price sidecar。已接受的 provider transaction slice 只保證單一 SQLite connection 的 query window，不能替代上述檔案鏈的身份證明。

## 下一個 gate 的身份契約

1. **checker 回傳已驗證 bytes 的不可變摘要。** 每個 namespace 的摘要必須在同一次讀取中，以 checker 實際解析及驗證的 bytes 建立；不可先驗證檔案、再另外重讀計算 hash。summary 至少識別 namespace、版本與所驗證檔案／bytes 的內容 hash，並保留 checker 原有 validation result。
2. **明確表示空集合。** 沒有 marker、receipt、排除範圍或其他 evidence，也要產生 namespace 及 schema 有界的空集合 identity。不能用 `None` 同時表示「驗證通過但沒有 evidence」、「checker 沒回傳版本」或「未能取得 identity」。
3. **前後 identity 完全相等才可繼續。** 在受保護工作開始前及完成後比較各 namespace summary；任何 namespace 缺摘要、讀取失敗、bytes 變動或摘要不一致，都必須 fail closed，將 ML input 標記 unavailable，不發布新的 ML inference receipt。摘要比較不得使用時間容差或只比較 mtime/size。
4. **與內容 hash 分開保存。** `PreparedMLInput.SnapshotReference.source_revision` 是 optional text 欄位，現行契約允許將有 namespace/version 的 evidence digest 放在這個欄位。可用時，它承載跨資源 revision identity；`content_hash`、`row_identity_hash` 仍分別識別已捕獲資料內容與列身份，不可用 sidecar digest 取代或重算它們。任何新增語意須明確版本化與驗證，不得偷偷改寫已發布的 v1 receipt bytes 或 schema。
5. **多次 provider 呼叫需要 invocation-scoped 共版。** 單次 checker token 或 SQLite connection `data_version` 只能涵蓋自己的讀取範圍，不能證明一個 inference invocation 的多次 provider call 使用相同 revision。後續切片必須採 invocation-owned read session／不可變來源 artifact，或由所有相關 writer 遵守的 durable generation protocol；consumer 必須證明取得的資料與該版本 identity 對應。不可用 process-global cache 或可變的 `last_*` 欄位傳遞 token。
6. **跨資源 atomicity 與 ABA 仍是明示限制。** pre/post digest 能偵測一般更新，但在沒有共同交易、共用鎖或所有 writer 都遵循的 generation protocol 時，不得宣稱 SQLite 與多個 sidecar 原子一致，也不得宣稱已排除改寫後還原 bytes 的 ABA。若契約需要這些保證，必須以新的 writer 協定或不可變 generation 設計另行驗收。

## 尚未通過的 gate

- 目前 TEMP probe 證明 direct receipt precheck→`BEGIN` 存在可重現間隙；尚無 production 修復或新的 pre/post summary gate。
- Market/session/excluded revision chains 尚未把實際已驗證 bytes 的 immutable identity 回傳給 provider；空 evidence 亦無可比較 identity。
- 尚未證明 checker 跨多檔讀取的一致性、不同 provider calls 的 invocation-wide 同版本、並行 writer/race、pointer/model identity 交叉綁定或 active artifact 更新安全。
- 不修改既有 receipt schema/bytes，也未授權 inference projector cutover。必須維持舊路徑，直到上述 identity gates 與 R026 其餘 parity/security gates 都有可審查證據。

因此，R026 與 `TMP-ML-01` 仍為 open/active；本附錄是 source-identity contract decision，不是 production acceptance 或 migration completion。

## Slice 1 實作狀態

`data_module/contracts/source_revision.py` 已加入純不可變的 `ValidatedEvidenceFileV1`、`ValidatedNamespaceEvidenceV1` 與 `ValidatedSourceEvidenceV1`。實作固定四個 namespace，要求明確 `present`／`empty`、排序與唯一性，並驗證嚴格小寫 SHA-256、scope、cutoff。`role_id` 僅接受英數字起始、由 ASCII 英數字／底線／句點／連字號構成的相對識別字元，可用 `/` 分層；控制字元、換行、URI scheme、百分比編碼、反斜線與非 ASCII 分隔符均拒絕。契約提供 canonical digest。`tests/test_r026_source_revision_evidence_contract.py` 已登錄 inventory；fresh TEMP focused route（新契約與既有 market contract tests）為 37 passed，兩個契約模組 mypy 2/0，三個 Python 檔案 `py_compile` 通過。

此 slice 沒有讀取或驗證任何 revision sidecar bytes，沒有修改 checker／provider／PIT exporter，亦未接入 `PreparedMLInput.SnapshotReference.source_revision`。契約本身尚不能證明呼叫端提交的 hash 來自實際解析 bytes；此能力須由後續 checker slices 建立並獨立驗收。`R026` 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`，沒有授權 inference cutover。
