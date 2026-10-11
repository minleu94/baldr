# R026 PreparedMLRuntimeInput 純型別 API 草案（2026-09-25）

**狀態：** pure types 與 focused contract tests 已實作，等待獨立覆核；未接入 production route。
權威設計依 `R026_LEGACY_SHADOW_RUNTIME_IDENTITY_DESIGN_ADDENDUM_20260925.md`。

## 檔案邊界

- 新增純 leaf：`ml_module/prepared_source_contract.py`，只放 source-contract feature-row 與 verified
  evidence types 及純 bytes builder。
- 新增 app-owned contract：`app_module/recommendation/prepared_runtime_input.py`，只放 strict／legacy
  identity tagged types 與 runtime envelope。
- 新增 contract-only tests：`tests/test_prepared_runtime_input.py`。`PreparedMLInput.v1`、
  `ml_adapter.py`、service、consumer、provenance 舊 verifier 均留給既有 owner／後續 codec。

## `prepared_source_contract.py` constructors

```python
SourceContractFeatureRowV1(
    symbol: str,
    decision_date: str,
    feature_as_of_date: str,
    feature_available_date: str,
    feature_ids: tuple[str, ...],
    feature_values: tuple[int | None, ...],
    snapshot_hash: str,
)
```

日期保留 preparation 已正規化後的原文字值；feature IDs、values 與 consumed rows 都是有序 tuple。
只檢查 immutable typed shape（例如 feature ID／value 長度一致與 feature value 為 int 或 None，且不接受
bool），不得在 leaf 另加現有 preparation／`verify_source_contract_binding()` 沒有的日期 canonicalization、
`snapshot_hash` 格式或非空要求。現有 normalization 將 `snapshot_hash` 轉成字串且允許空字串，必須原樣保留。

```python
VerifiedSourceContractEvidenceV1(
    binding_payload_json: bytes,
    contract_file_bytes: bytes,
    contract_path: str,
    contract_file_sha256: str,
    contract_content_sha256: str,
    decision_date: str,
    symbols: tuple[str, ...],
    source_database: str | None,
    source_database_original: str | None,
    history_start_date: str | None,
    feature_registry_hash: str,
    feature_schema_hash: str,
    feature_builder_schema_hash: str | None,
    feature_snapshot_content_sha256: str,
    feature_snapshot_rows_sha256: str,
    consumed_feature_rows: tuple[SourceContractFeatureRowV1, ...],
)
```

Factory 固定介面為設計補充指定的
`build_verified_source_contract_evidence_v1(*, binding_payload_json, contract_file_bytes, contract_path, decision_date, symbols, source_database, source_database_original, history_start_date, feature_registry_hash, feature_schema_hash, feature_builder_schema_hash, consumed_feature_rows)`。
此型別不得提供可讓 caller 指定 `evidence_sha256` 的公開建構路徑；採 `init=False`／私有 validated
constructor，僅由下列 factory 建立。`__post_init__`（或等價私有建構路徑）仍須驗證 bytes、rows 與
evidence digest 的一致性，不能因參數型別正確就略過內容斷言。factory 不接收 Mapping、不讀檔、不自行
建立或推測證據；以收到的 bytes／typed rows 驗證 normalized binding、原始 contract file hash、contract
content self-hash 與既有 source-contract assertions，並計算 `evidence_sha256`。
驗證欄位需保持 `verify_source_contract_binding()` 的語義：schema version、historical PIT=false、
prospective lane=ready、decision date、symbols、source DB/history start（呼叫端提供時）、feature
snapshot content/self-hash、registry/schema、rows hash、逐 symbol row coverage、timing 與 feature values。
不得添加原驗證器沒有的拒絕條件；例如 normalized row 的 `snapshot_hash` 可為空字串或 opaque string，
日期比較沿用原有前十字元及 `_date_text` 的位置語義，builder 不得自行要求更嚴格格式。feature IDs 及
其他 row 值依同次已完成 normalization 的 shape 保留，由既有 rows-hash/source assertions 綁定。

`evidence_sha256` 由 V1 固定 domain-separated canonical payload 計算，綁定以上 hashes、context 與
ordered rows，並同時綁定由 preparation 傳入的已解析 `source_database` 與 provenance 原字串
`source_database_original`；兩者必須同時存在或同時缺省，不在 leaf 解析路徑。不可由呼叫端任意提供。
舊 verifier 的 file/symlink/existence/read 行為不移入此 leaf；
preparation owner 讀取並傳入同次 raw bytes，codec 再用 typed evidence 執行 pure verification。

## `prepared_runtime_input.py` constructors

```python
StrictPreparedMLIdentityV1(prepared_input: PreparedMLInput)
LoadedModelRuntimeClassV1(module: str, qualified_name: str)
BoundRuleSnapshotsV1(snapshot_refs: tuple[SnapshotReference, ...])
LegacyUnboundRuleIdentityV1(reason: Literal["legacy_source_identity_unbound"])
LegacyShadowIdentityV1(
    model_resolution: RecommendationModelResolutionEvidenceV1,
    unknown_model_binding_fields: UnknownModelBindingFieldsV1,
    loaded_model_runtime_class: LoadedModelRuntimeClassV1,
    ml_snapshot_refs: tuple[SnapshotReference, ...],
    rule_identity: BoundRuleSnapshotsV1 | LegacyUnboundRuleIdentityV1,
)
PreparedCandidateProjectionInputV1(
    candidate_id: str,
    symbol: str,
    rule_probability_bp: int | None,
    after_cost_rule_probability_bp: int | None,
    after_cost_rule_baseline_id: str | None,
    ranking_percentile_bp: int | None,
)
MissingCandidateFeatureV1(
    symbol: str,
    selection_index: int,
    selected_item_sha256: str,
    reason: Literal["historical_price_row_missing"],
)
RecommendationMLSparsePreparationFactsV1(
    result_id: str,
    decision_date: date,
    feature_cutoff_date: date,
    feature_registry_id: str,
    feature_registry_hash: str,
    feature_schema: tuple[tuple[str, str, str], ...],
    feature_ids: tuple[str, ...],
    feature_schema_hash: str,
    feature_load_contract_hash: str,
    present_facts: RecommendationMLPreparationFactsV1 | None,
    missing_candidates: tuple[MissingCandidateFeatureV1, ...],
)
MissingCandidateProjectionInputV1(
    missing_feature: MissingCandidateFeatureV1,
    rule_probability_bp: int | None,
    after_cost_rule_probability_bp: int | None,
    after_cost_rule_baseline_id: str | None,
    ranking_percentile_bp: int | None,
)
PreparedMLProjectionContextV1(
    candidates: tuple[
        PreparedCandidateProjectionInputV1 | MissingCandidateProjectionInputV1, ...
    ],
    rule_baseline_id: str,
    data_quality: str,
    selection_authority: str,
    selection_score_kind: str,
    selection_percentile_kind: str,
    top_n_changed_by_model: bool,
)
PreparedInferenceProvenanceV1(canonical_json_bytes: bytes)
PreparedMLInvocationBindingV1(
    invocation_scope_id: str,
    expected_identity_canonical_json_bytes: bytes,
)
PreparedMLRuntimeInputV1(
    identity: StrictPreparedMLIdentityV1 | LegacyShadowIdentityV1,
    preparation_facts: RecommendationMLPreparationFactsV1
    | RecommendationMLSparsePreparationFactsV1,
    projection_context: PreparedMLProjectionContextV1,
    invocation_binding: PreparedMLInvocationBindingV1,
    inference_provenance: PreparedInferenceProvenanceV1 | None,
    decision_clock: datetime,
    invocation_capability: object,
    source_contract_evidence: VerifiedSourceContractEvidenceV1 | None = None,
)
```

`RecommendationMLSparsePreparationFactsV1` 讓合法缺少 historical price row 的候選留在全序列中；
只有真實 present rows 交給既有 V1 builder，缺列只保存原選取位置、exact selected-item hash 與固定原因碼，
不虛構 feature vector、row hash 或 candidate ID。全缺時 `present_facts=None`。Projection context 仍依
全候選順序保存所有原有 rule／after-cost／ranking 值。Legacy identity lane 支援 sparse facts；strict
`PreparedMLInput` lane 目前明確不支援 sparse facts，因 strict opaque candidate ID 無法由缺列資料安全綁定。

`PreparedCandidateProjectionInputV1` 保存 service 同次傳入的每個 candidate rule probability、after-cost
probability/baseline 與 ranking percentile。`PreparedMLProjectionContextV1.candidates` 必須與
preparation facts 的 candidate ID／symbol 同順序；所有值原樣保存，不重算、不正規化。`decision_date`
與 `feature_values_by_symbol` 可由 facts 取得，所以不重複保存；rule baseline ID、data quality、selection
authority／score kind／percentile kind、`top_n_changed_by_model` 則由 context 明確保存。

`PreparedInferenceProvenanceV1` 保存既有 provenance 的 canonical UTF-8 JSON bytes，保留 schema/status、
content/provenance hashes 與 normalized payload；相容邊界才 decode 給既有 verifier／receipt 路徑。
`None` 是明確合法值，以保留原 `project_many()` 對未提供 provenance 的 per-symbol fallback。若 bytes
內配置 source binding，必須與同一 runtime input 的 typed `source_contract_evidence` 一致。

`PreparedMLInvocationBindingV1` 的 expected identity 也是 canonical UTF-8 JSON object bytes，編碼採既有
`_hash_payload` 同規則（`ensure_ascii=False`、sorted keys、compact separators）；它與同一 input 上的
scope 一起交 capability 比對，契約不 import consumer。

`PreparedMLRuntimeInputV1` 重用 preparation facts 作為唯一有序 candidate／features／schema／hash
來源，不另做可變矩陣副本。Strict identity 包裝既有 `PreparedMLInput` 並保留其 V1 驗證；legacy identity
不建立 `ModelBinding`，且 `unknown_model_binding_fields` 必須與 model facts 原值一致。Runtime class
只記錄實際已載入物件的 `type.__module__`／`type.__qualname__`，不可回填 artifact-declared class path。

`BoundRuleSnapshotsV1` 只接受真實非空 reference tuple；缺少時僅接受固定 reason 的
`LegacyUnboundRuleIdentityV1`，不可合成 `SnapshotReference`。ML references 必須是同次 historical
custody 產生的真實 `SnapshotReference`；source revision／availability／quality／scope 未有證據時保持
既有 `None`／`UNKNOWN`。

Envelope 保存 service 當次提供的 aware `decision_clock`，以固定 offset 凍結可變 `tzinfo`，不從 date、execution created time 或時區轉換
推導。Strict branch 必須與 `PreparedMLInput.decision_at` 相符，並核對 result/date/cutoff 及相同順序的
feature schema／完整 `(candidate_id, symbol)` pairs；strict + sparse 組合明確拒絕。Legacy branch 核對 model-resolution decision date、ordered candidate
facts、ML refs 與 rule identity，不填造 metadata。

`invocation_capability` 為必填且 opaque，以 `repr=False` 隱藏，不加入 payload／receipt；runtime envelope
自身禁止 copy、deepcopy 與 pickle。純型別不因 profile 不相符而拒絕輸入或判定舊合法 caller unavailable；
profile/runtime graph gate 屬 preparation adapter／evidence 的後續 codec 範圍。舊 `project()`／
`project_many()` 相容入口與目前合法 production 路徑保持不變，直到 adapter/parity gate 另行裁決。

## Contract-only 驗證範圍

- strict variant 保留 `PreparedMLInput` 完整 ABI；測既有物件包裝、candidate ID/symbol exact alignment、deep-freeze reference 與 mismatch
  rejection，不合成當前不存在的 artifact/release/class metadata。
- legacy variant 的 missing release／artifact-declared class、quarantine／permission／transform
  status 保留 `None`／`UNKNOWN`；observed runtime class 不會改變 unknown declaration。
- 規則 refs 可為 bound 或固定 legacy-unbound；不接受虛構 reference、其他 reason、空的 ML custody refs。
- preparation facts 中候選順序、feature vectors／schema／hash 必須保持；外層 tuple/list alias mutation
  不可改已建 input。
- decision clock 要求 aware datetime、凍結自訂 mutable tzinfo offset，strict identity clock 不一致拒絕；不得用 `decision_date` 推 clock。
- projection candidate context 與 preparation facts 的 candidate ID／symbol 順序必須一致；原 rule/after-cost/
  percentile 值與 selection metadata 不可變或重算；inference provenance canonical bytes round-trip 不變，None
  保留舊 per-symbol fallback；invocation identity bytes 是 canonical JSON object 且 capability scope 一致。
- source evidence 僅接受 exact immutable evidence type；不接受 Mapping 替代。`source_contract_evidence`
  有無不改輸出 provenance／receipt 的序列化形狀。
- capability 不出現在 repr，且 runtime input copy／deepcopy／pickle 都拒絕；不得序列化或跨 invocation
  保留。

本草案只固定 pure constructors／不變量；profile eligibility、actual source bytes 讀取、source contract
pure verification、projector／service 接線與 production cutover 都由後續 codec／QA gates負責。

## Pure contract 驗證紀錄（2026-09-25）

- focused tests：`11 passed`；命令為 `\.venv\Scripts\python.exe -m pytest tests\test_prepared_runtime_input.py -q -o addopts= -p no:cacheprovider --basetemp=C:\Users\archi\AppData\Local\Temp\r26p0925c\pytestbasetemp`。
- 語法檢查：`\.venv\Scripts\python.exe -m py_compile ml_module\prepared_source_contract.py app_module\recommendation\prepared_runtime_input.py tests\test_prepared_runtime_input.py` 通過。
- scoped 型別檢查：`\.venv\Scripts\python.exe -m mypy --explicit-package-bases --follow-imports=silent ml_module\prepared_source_contract.py app_module\recommendation\prepared_runtime_input.py tests\test_prepared_runtime_input.py` 通過，3 files。
- 獨立執行同一組 mypy 且允許檢查所有 imports 時，pure files 無錯；c1cross 尚在編輯的 projector、service、consumer 另有 27 個 errors，已個別通知其 owner，不能算成本 slice 通過或 production integration gate。
- strict dense 候選以 `(candidate_id, symbol)` 配對；strict+sparse 明確不支援。Legacy sparse 與 all-missing contract tests 通過。
- Root 獨立驗收以 fresh TEMP 再跑 11 tests，`0.24s`、exit 0；log SHA-256 `8982682D27D7B2AA6FBE3C43615A38AB0FD5D16D8FAAFDA5B824FACDF5BDC1C4`，收據目錄 `C:\Users\archi\AppData\Local\Temp\r26pure_2215669e`。
- Root 驗收時三個 pure source/test SHA-256：`prepared_source_contract.py` `9568839F471AA341C7F7CEEB97BBC325FDF5D6B31D547582A07384AC59F1FACF`；`prepared_runtime_input.py` `C09E6AD887A0575ABA1A0645E01496A31A9B2CC7425718F6031B2003FE258EB9`；`test_prepared_runtime_input.py` `8391E9C61604F6CE2F9CCDCD0885A931EC4998E4499F43C5E5A69D0662AD83BE`。

## 2026-10-11 後續 handoff 狀態核對

本文狀態行是 2026-09-25 純型別設計與 contract tests 的當時快照。後續 `R026_IMPLEMENTATION_REPORT.md` 與 `R031_TASK_REPORT_INDEX_DRAFT_20260925.md` 已將正常 `RecommendationService` 的 NP1／NP2 allowlisted caller/profile typed preparation 與 post-calibration handoff 記為 bounded accepted，`TMP-ML-01` 對該集合 closed。這只更新已支援的精確 tuple／caller 範圍；其他 profiles、custom consumers、任意 model graph、R026 其他 source-evidence slices 與 production promotion 仍不在接受結論內。
