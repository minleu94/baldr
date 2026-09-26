# R026 PreparedMLInput 與 transient runtime input 設計裁決

**日期：** 2026-09-24

**狀態：** 本文件保留 2026-09-24 的原契約裁決；目前實作與 bounded acceptance 狀態以本文件後續 checkpoint、[legacy-shadow runtime identity addendum](R026_LEGACY_SHADOW_RUNTIME_IDENTITY_DESIGN_ADDENDUM_20260925.md) 及 [implementation report](R026_IMPLEMENTATION_REPORT.md) 開頭為準。

**目前 checkpoint（2026-09-25）：** Root 已接受 exact NP1／NP2 supported profile 與實際 model-graph caller 的 bounded service default runtime 及 typed post-calibration handoff；`TMP-ML-01` 定義的正常 production `RecommendationService` 遷移條件已 `CLOSED`。C2 為 `ACCEPTED_WITH_NAMED_QA_BASELINE`（union 1860 passed／5 skipped／34 warnings；Update validator Windows `WinError 32` cleanup 為具名 baseline）。此狀態不外推至未列 profiles、custom consumers、任意 graph、所有 R026 source-evidence slices、正式資料或 model promotion；完整現況見 [R026 implementation report](R026_IMPLEMENTATION_REPORT.md) 開頭。

**關聯：** [R026 synthetic baseline 實作報告](R026_IMPLEMENTATION_REPORT.md)、`REFACTOR_TASKS/R026.md`、FINAL_ML_COMPATIBILITY_CONTRACT 與目標架構文件。

## 裁決

保留 `PreparedMLInput.v1` 作為既有純身份與 reference 相容契約，並保留歷史資料的可讀性。新增明確版本的 `PreparedMLRuntimeInputV1`，作為 inference projector 的唯一 runtime 參數。Runtime identity 是 tagged union：完整 strict V1 `PreparedMLInput.v1`、明示 UNKNOWN 的 typed `LegacyShadowIdentityV1`，或同次 reload 確認 `rule_only`／無 loaded model 的 `NoModelShadowIdentityV1`；不修改 strict V1 欄位或驗證。Runtime input 另封裝同次 invocation 的 frozen feature facts 與 private capability；`PreparedMLInput.v1` 本身不承載 mutable model。身份與支援邊界見 2026-09-25 [R026 legacy-shadow runtime identity addendum](R026_LEGACY_SHADOW_RUNTIME_IDENTITY_DESIGN_ADDENDUM_20260925.md)。

`PreparedMLRuntimeInputV1` 至少須綁定以下同一次 invocation 的資料：

- strict `PreparedMLInput.v1`、typed `LegacyShadowIdentityV1` 或同次確認 rule-only／無 loaded model 的 `NoModelShadowIdentityV1`；legacy lane 保留 missing release/class 為 `None`、未知安全狀態為原 `UNKNOWN`，rule references 無法證明時使用固定 `legacy_source_identity_unbound` reason，不造假 reference；
- 舊 feature builder 產生的 ordered `tuple[int | None, ...]`、feature schema 與對應 hash；
- 綁定至同一 candidate 的識別資訊；
- preparation 階段透過既有 `SafeShadowModelArtifactLoader`，由已驗證 artifact 為本次 invocation 新載入的 resolved model 與 lineage capability。

Runtime envelope 傳入 service 實際產生的 decision clock 原值；source custody、rule reference 與 UNKNOWN 的表示、source-contract bytes 的 typed handoff，以及目前 capability 的 exact runtime/model-graph 支援邊界，以 2026-09-25 設計補充為準。設定 `recommendation_source_contract_binding` 時必須在 preparation 驗證並帶入 immutable `VerifiedSourceContractEvidenceV1`；不得移除 binding 以避開 capability 的現有拒絕，也不得讓 projector 重讀檔案。舊 public `project()`／`project_many()` 仍作 compatibility API。

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

目前受驗 profile 限於 exact NP1／NP2 tuple與 versioned model-graph allowlist；Root 已接受 normal `RecommendationService` 在此有限支援集合內的 bounded default cutover，且 `TMP-ML-01` 的此項遷移條件已 `CLOSED`。未列 profile、unsupported graph 或 custom/test-injected consumer 的 capability `None` 仍沿用舊相容行為，不新增拒絕／unavailable。七 gate 的 bounded runtime acceptance 不代表所有 profiles／graphs 或其他 R026 source-evidence slices 都已驗證；C2 的 named QA baseline 與目前 caller/profile 收據見 implementation report checkpoint。七項 gate操作範圍與ownership見專用設計 addendum。

任何 gate 未通過、無法觀測，或 parity 有差異時，保留該未驗 profile／caller 的相容路徑，不宣稱 R026 cutover 完成。已接受 NP1／NP2 limited default switch不外推至未知profile/graph。R026 synthetic baseline 的 `ACCEPTED_SCOPE` 僅驗收舊 preparation 的既有行為，不代表以上 gate 已全數完成。

## 狀態與範圍

strict V1 ABI 不變；NP1／NP2 supported production caller/profile 的 runtime default 與 typed handoff bounded acceptance 已由 Root 確認，`TMP-ML-01` 遷移條件已 `CLOSED`。C2 `ACCEPTED_WITH_NAMED_QA_BASELINE` 不等於全 profiles／整體重構 PASS。此文件不批准正式資料 promotion 或 production deployment。
