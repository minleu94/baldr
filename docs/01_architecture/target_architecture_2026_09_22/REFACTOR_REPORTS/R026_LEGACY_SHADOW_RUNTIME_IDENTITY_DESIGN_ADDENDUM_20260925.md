# R026 strict／legacy-shadow runtime identity 設計補充

**日期：** 2026-09-25
**狀態：** strict／legacy-shadow／no-model typed runtime contract、source-contract pure evidence path、service default wiring 與 typed post-calibration handoff 已實作並獲 bounded engineering acceptance。Root 已接受 R026 支援 production caller/profile 遷移範圍，`TMP-ML-01` 定義的正常 `RecommendationService` 遷移條件已 `CLOSED`。C2 為 `ACCEPTED_WITH_NAMED_QA_BASELINE`：union route 1860 passed／5 skipped／34 warnings，Update validator Windows `WinError 32` cleanup 保留為具名 QA baseline；整體不宣稱全 profiles、所有 R026 source-evidence scope、正式資料或 model promotion 已接受。
**權威範圍：** 僅補 `PreparedMLRuntimeInputV1` 的身份表示、source-contract handoff 與支援邊界；不改 FINAL、模型拒絕政策、artifact、receipt schema 或正式資料。

## 裁決

`PreparedMLInput.v1` 與 `ModelBindingV1` 保持原 ABI 和嚴格驗證，不用 sentinel、假值或 alias 補 `release_id`、artifact-declared class path、quarantine、permission、transform 或 references。舊 artifact manifest v1 沒有 release/class 宣告；同次 resolution facts 也明確把這些欄位保留為 `None`／`UNKNOWN`。`model_id`、candidate ID、`created_run_id`、artifact hash 或實際載入的 Python class 都不能替代缺少的 artifact 宣告。

新增的 app-owned `PreparedMLRuntimeInputV1` 使用明確 tagged identity union：

- `StrictPreparedMLIdentityV1(prepared_input: PreparedMLInput)`：完整 strict V1 身分；必須符合原有非空 rule/ML references 與完整 `ModelBinding` 規則。
- `LegacyShadowIdentityV1(...)`：表示同次 safe-loader 已接受、且基線既有政策允許 shadow projection 的 legacy artifact。攜帶 `RecommendationModelResolutionEvidenceV1`、其原始 `UnknownModelBindingFieldsV1`、真正的同次 ML `SnapshotReference` tuple，以及明確 rule identity。此 variant 不建立 `ModelBinding`，不增加任何權限，也不得把 UNKNOWN 轉成可用狀態。
- `NoModelShadowIdentityV1(...)`：只記錄同次 fresh baseline reload 明確回傳 `rule_only` 且實際 `_model is None` 的終止結果，包含 blocker、pointer status 與該次實讀 pointer bytes（缺 pointer 時保留 `None`；raw bytes hash 由 typed value 計算）。不建立 ModelBinding、model-resolution evidence 或 loaded runtime class。只有原 active identity 缺席時可嘗試此 resolver；active identity 存在但 active capability 失敗，不可降格為 NoModel。

`LegacyShadowIdentityV1` 的 `artifact_declared_qualified_class_path` 維持 `None`；另以 `LoadedModelRuntimeClassV1(module, qualified_name)` 記錄 safe loader 實際載入物件的 runtime 類別。兩欄語義不得合併。缺少 rule references 時只接受固定的 `LegacyUnboundRuleIdentityV1(reason="legacy_source_identity_unbound")`；不可建立虛構 `SnapshotReference`。同次 historical snapshot custody 可產生真正 ML reference；`source_revision` 未由已驗證來源證據支持時保持 `None`，availability、quality、scope 仍保持 `UNKNOWN`。

Runtime envelope 重用既有 `RecommendationMLPreparationFactsV1` 作為有序 candidate/features/schema/hash 來源，並攜帶 service 當次實際 aware `decision_clock`、opaque invocation-local model capability、`PreparedMLProjectionContextV1`、immutable `PreparedInferenceProvenanceV1`，以及可選的 `VerifiedSourceContractEvidenceV1`。不可從 `decision_date` 推算 `decision_at`。Capability 不得複製、序列化、寫入 receipt 或跨 invocation 保留。

`PreparedMLProjectionContextV1` 是 `project_many()` 既有非 feature 輸入的 typed immutable snapshot，不另造數值：ordered candidate row 逐項包含 `candidate_id`、`symbol`、原 `rule_probability_bp`、可選 `after_cost_rule_probability_bp`、`after_cost_rule_baseline_id` 與 `ranking_percentile_bp`；整體包含原 `rule_baseline_id`、`data_quality`、`selection_authority`、`selection_score_kind`、`selection_percentile_kind`、`top_n_changed_by_model`。Candidate IDs/symbols/order 必須與 `preparation_facts.candidates` 完全相同；codec 只複製同次已計算值，不重新計算或正規化。

`PreparedInferenceProvenanceV1` 封裝原 provenance 的明確 schema-version 與 canonical JSON bytes，完整保留原 `schema_version`、status、hash 與 payload。Projector 在既有 ML 相容邊界解碼後沿用原 mapping verifier／receipt serialization；不得改 provenance schema、hash、receipt bytes 或新增 generic dict contract。若存在 `source_contract_binding`，bytes 內必須保留其舊欄位，並與同一 runtime input 的 typed `VerifiedSourceContractEvidenceV1` 相符；evidence 不寫入 receipt。

## Source-contract handoff

設定有 `recommendation_source_contract_binding` 時，preparation 必須讀取該次所綁的原始 contract bytes、執行既有 path/file/content/self-hash、decision date、symbols、registry/schema、source/history、rows、availability 等驗證，再建立 immutable evidence。驗證失敗依既有 fail-closed 行為中止該次 projection；不得把 binding 當成未設定而跳過。

Pure leaf 由 capture owner 放在 `ml_module/prepared_source_contract.py`：

- `SourceContractFeatureRowV1(symbol, decision_date, feature_as_of_date, feature_available_date, feature_ids, feature_values, snapshot_hash)`；序列與數值皆凍結。
- `VerifiedSourceContractEvidenceV1` 欄位：`binding_payload_json: bytes`（既有 normalized binding 的 canonical bytes）、`contract_file_bytes: bytes`（實際讀取 bytes）、resolved `contract_path`、file/content SHA-256、decision date、symbols、source database/history start、feature registry/schema/builder hashes、feature snapshot content/rows hashes、有序 `SourceContractFeatureRowV1` tuple，以及 domain-separated `evidence_sha256`。
- 建構器固定介面：`build_verified_source_contract_evidence_v1(*, binding_payload_json: bytes, contract_file_bytes: bytes, contract_path: str, decision_date: str, symbols: tuple[str, ...], source_database: str | None, history_start_date: str | None, feature_registry_hash: str, feature_schema_hash: str, feature_builder_schema_hash: str | None, consumed_feature_rows: tuple[SourceContractFeatureRowV1, ...]) -> VerifiedSourceContractEvidenceV1`。`SourceContractFeatureRowV1` 的日期欄保留既有 ISO text，`feature_ids`／`feature_values` 為有序 tuple；hash 欄位使用實際來源值。
- 建構器只接收上述 immutable bytes/typed rows 與驗證上下文；不讀檔、不接收 generic dict、不合成 evidence。它驗證提供 bytes 與既有 binding hashes、contract assertions、當次 feature rows 相符。檔案 existence/symlink/讀 bytes 由 preparation owner 在同次呼叫完成，再把確切 bytes 傳入；舊 receipt 仍由 `binding_payload_json` 還原同一個 normalized binding payload。

Codec owner 修改既有 `ml_module/recommendation_inference_provenance.py`，新增接受 typed evidence 的 opt-in pure verifier；既有 `verify_source_contract_binding(mapping, ...)` 與舊呼叫端的檔案讀取、安全政策保留。Runtime path 傳遞 evidence，不把 raw binding mapping 交給目前會拒絕 filesystem-bound binding 的 invocation capability。Provenance/receipt 輸出仍序列化原有 binding 欄位，`source_contract_status`、receipt payload、identity 與 bytes 不變；evidence 只作同次 invocation 的驗證輸入，不寫入 receipt。

## Runtime 支援範圍

受驗 runtime profile 是有限精確集合：Windows／CPython 3.11.9／NumPy 2.3.5／scikit-learn 1.8.0／SciPy 1.16.3／joblib 1.5.2（NP2），以及 Windows／CPython 3.11.9／NumPy 1.26.4／scikit-learn 1.8.0／SciPy 1.16.3／joblib 1.5.2（NP1）。兩個 tuple 都必須配 exact `RecommendationCalibrationConsumer`、exact `SafeShadowModelArtifactLoader`、default `joblib.load`，以及 active/lineage nodes 符合 versioned graph allowlist。此界線不代表所有 deployment、custom deserializer 或任意 Python graph 都已驗證。

在 NP1／NP2 及受支援 graph 內，legacy metadata 缺欄由 `LegacyShadowIdentityV1` 表達；同次確定為 rule-only/no-model 時使用 `NoModelShadowIdentityV1`。Root 已接受這個有限 normal `RecommendationService` default cutover，並關閉此有限 caller/profile 集合的 `TMP-ML-01` 遷移條件。若 profile、loader、model graph 或 safe-loader eligibility 不符合，capability `None` 不得導出拒絕，也不得改變原合法 projection；service 沿用既有 `project_many()` 路徑。舊 public `project()`／`project_many()`、custom/test-injected consumers及 status-only learning-evidence reader保留為相容呼叫；不把它們或未列任意 profile描述為已驗證，也不把本次接受外推到未來新增的 production profile。

本設計不要求替歷史 corpus 補建 producer。只讀取當次已安全解析的 model facts；不可得欄位保持 `None`／`UNKNOWN`。若未來同次權威來源真的提供 release/class/permission 等證據，可由獨立 typed source binding 擴充；不得預先推定或批量填補。

## 七項 runtime gate

七 gate 僅在 C2 NP1/NP2 baseline freeze 後執行，使用 fresh isolated TEMP 與 synthetic evidence；不得接正式資料或執行 scheduler。

1. **Model graph 隔離：** same-call safe-loader、深層 alias、一次性 capability、A/B 巢狀 mutation；涵蓋 strict 與 legacy-shadow identity。確認 exact supported profile；其他既有合法 caller 在 adapter 完成前留在基線 production path，不把未測視為拒絕或 parity。
2. **Projector 無 I/O：** projector 只收一個 `PreparedMLRuntimeInputV1`；禁止 DB/path/loader/pointer 讀取。Source-contract bytes 只在 preparation 讀取，projector 以 typed evidence 純驗證；canonical provenance bytes 只在既有 ML 邊界解碼。
3. **穩定 pointer parity：** 在 exact supported profile 下，對基線允許的 strict 與 legacy-shadow synthetic cases 逐欄比對 features、model resolution、projection-context 原值、provenance payload/hash 與 receipt identity；不外推到 custom runtimes。
4. **Source/pointer barrier：** 驗證同次 source custody、既有 pre/post aggregate 與 pointer checks；任一變動依基線拒絕／降級。Source digest 不代表跨 medium atomicity 或無 ABA。
5. **Artifact／status 安全：** quarantine、permission、transform、loader、hash 或 source-contract mismatch 保留原拒絕／降級；UNKNOWN 不升級。Configured binding 驗證不得被略過。
6. **A/B interleave：** candidate order、feature facts、projection context、provenance bytes、model/lineage capability、source-contract evidence 與 receipt 不得跨 invocation 串接。
7. **Bytes parity：** exact feature/schema/hash 與穩定情境 receipt bytes 一致；包含 configured binding 的既有序列化形狀及 receipt failure side-effect order。

七 gate 的有限 NP1／NP2 service route 與 typed handoff 已取得 bounded engineering acceptance；C2 current union route 為 1860 passed／5 skipped／34 warnings，另以 `ACCEPTED_WITH_NAMED_QA_BASELINE` 保留 Update validator teardown failure。`TMP-ML-01` 的正常 supported production `RecommendationService` 遷移條件已 `CLOSED`。此裁定不表示所有 profile／graph、所有 R026 source-evidence slices 或整體 refactor gate 全部通過；也不宣稱跨來源／SQLite/model/receipt 原子性或 ABA，這些是 scope 限制，不另加為本任務 gate。正式資料 promotion/deployment 不在授權範圍。

## Ownership

- **capture：** 純 `ml_module/prepared_source_contract.py` leaf、app-owned `app_module/recommendation/prepared_runtime_input.py` tagged/runtime/projection-context/provenance-bytes types，以及 contract-only tests。
- **codec：** `recommendation_service.py` preparation/source bytes/decision clock/capability handoff、`ml_adapter.py` 新版 runtime protocol、`recommendation_calibration_consumer.py` projector wiring，以及 `recommendation_inference_provenance.py` opt-in typed pure verification；保留原 public API 與舊 verifier。
- **QA：** C2 baseline 完成後執行 exact profile 七 gate；另盤點現有合法 production profiles/model graphs，報告 adapter/parity 缺口。無 adapter 的既有合法 caller 保留基線行為，不以未驗證取代為拒絕。

本文件補充 [PreparedMLRuntimeInput 裁決](R026_PREPARED_RUNTIME_INPUT_DECISION_ADDENDUM_20260924.md) 與 [R026 task](../REFACTOR_TASKS/R026.md)。
