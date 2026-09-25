# R026 PreparedMLInput 與 transient runtime input 設計裁決

**日期：** 2026-09-24

**狀態：** 架構方向裁決；尚非 production 實作或驗收證據。

**關聯：** [R026 synthetic baseline 實作報告](R026_IMPLEMENTATION_REPORT.md)、`REFACTOR_TASKS/R026.md`、FINAL_ML_COMPATIBILITY_CONTRACT 與目標架構文件。

## 裁決

保留 `PreparedMLInput.v1` 作為既有純身份與 reference 相容契約，並保留歷史資料的可讀性。新增明確版本的 `PreparedMLRuntimeInputV1`，作為 inference projector 的唯一 runtime 參數。Runtime input 封裝深凍結的 `PreparedMLInput.v1` identity/reference 與本次 invocation 專屬的 private model/lineage capability；`PreparedMLInput.v1` 本身不承載 mutable model。這是補足 runtime contract 的完整性，不推翻 FINAL 設計，也不表示新路徑已在 production 實作或通過 parity gate。

`PreparedMLRuntimeInputV1` 至少須綁定以下同一次 invocation 的資料：

- `PreparedMLInput.v1` identity/reference；
- 舊 feature builder 產生的 ordered `tuple[int | None, ...]`、feature schema 與對應 hash；
- 綁定至同一 candidate 的識別資訊；
- preparation 階段透過既有 `SafeShadowModelArtifactLoader`，由已驗證 artifact 為本次 invocation 新載入的 resolved model 與 lineage capability。

Model/lineage capability 不屬於 `PreparedMLInput.v1` 的不可變資料圖；它是 `PreparedMLRuntimeInputV1` 內不對外暴露可寫欄位的 private invocation-scoped capability。不可重用 consumer model cache、外部提供的 model instance，或與其他 invocation 共享巢狀 mutable alias。若在安全 loader 載入後採用 clone，須另以測試證明 alias 隔離與 ABI 相容。Capability 不得跨 invocation 保留或寫入 execution、receipt、DTO。Projection 不得查詢資料庫、路徑或 active pointer，也不得呼叫 loader；Receipt identity、既有 side-effect 順序與 post-check 必須保留。

## 必須通過的接線 gate

在宣告新路徑可用前，須以隔離的 synthetic evidence 驗證：

1. **Model graph 隔離：** resolved model 與 lineage capability 僅供同次 invocation 使用；以含巢狀 mutable state 的 fake model/lineage 驗證 source alias、cache alias、A/B invocation 及外部 mutation 均不共享或污染。若採 clone，另驗其 alias 與 ABI 證據。
2. **Projector 無 I/O：** projector 只消費版本化 transient runtime input；測試須證明它不碰 DB、path、active pointer 或 loader。
3. **穩定 pointer parity：** 在 pointer 不變時，新舊路徑的 feature、model identity、projection 與 receipt identity 按既有契約一致。
4. **Source/pointer barrier：** 受控 source 或 active pointer 在 preparation/inference 邊界變動時，依契約 fail closed；不能把新舊來源混成一次結果。
5. **Artifact 安全：** quarantine、loader rejection、identity/lineage 不符與 artifact bytes 變動等情境皆維持安全拒絕與可診斷結果。
6. **A/B interleave：** 兩個 invocation 交錯執行時，feature、candidate、resolved model、lineage 與 receipt 不得互相串接。
7. **Bytes parity：** 比對 ordered feature values/schema/hash，以及 receipt identity 與穩定情境下的 receipt bytes；不得以重算基準或容差掩蓋差異。

任何 gate 未通過、無法觀測，或 parity 有差異時，維持 `TMP-ML-01` 舊路徑，不得切換 inference projector，也不得宣稱 R026 cutover 完成。R026 synthetic baseline 的 `ACCEPTED_SCOPE` 僅驗收舊 preparation 的既有行為，不代表以上 gate 已執行。

## 狀態與範圍

`R026` 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。本裁決只界定下一步 runtime contract 及驗收條件；不修改 production、FINAL 架構文件、模型、正式資料或 artifact，也不批准任何 production cutover。
