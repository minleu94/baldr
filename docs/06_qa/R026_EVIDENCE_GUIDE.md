# R026 證據家族導覽

> 本頁只提供閱讀路徑，不是新的 QA 收據、Gate 裁定或 ML qualification。26 份日期化證據原件均保留在本目錄。

## 先看範圍與狀態

1. [R026 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R026_IMPLEMENTATION_REPORT.md)：先讀開頭的「目前 runtime handoff checkpoint」。它接受的是明確 supported caller/profile 的 bounded typed handoff；不代表所有 R026 source-evidence slices、profiles、custom models 或整體 refactor gate 都已通過。
2. [R031 task report index](R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 的 R026 列與 [FINAL migration sequence](../01_architecture/target_architecture_2026_09_22/FINAL_MIGRATION_SEQUENCE.md)：核對 `TMP-ML-01` 對 supported caller/profile 的遷移範圍與保留的相容邊界。
3. [R026 exact allowlist QA](ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md)：確認受支援路徑的明確 allowlist。

部分 leaf receipts 保留各自日期及切片中的 `R026 IN_PROGRESS`／`TMP-ML-01 ACTIVE` 描述；這些字樣是原始證據的範圍快照。不得用單一 leaf 的狀態推論 supported runtime handoff 的狀態，也不得把該 bounded handoff 接受擴大成所有 R026 source evidence 或所有 ML 能力結案。需要目前判讀時，回到 implementation report 開頭的 checkpoint、FINAL migration sequence 與 Snapshot。

## 證據閱讀順序

### 1. Capability 與模型身分（7 份）

- [Candidate JSON captured bytes](R026_CAPABILITY_CANDIDATE_JSON_CAPTURED_BYTES_20260925.md)
- [Model manifest captured bytes](R026_CAPABILITY_MODEL_MANIFEST_CAPTURED_BYTES_20260925.md) → [獨立覆核](R026_CAPABILITY_MODEL_MANIFEST_CAPTURED_BYTES_INDEPENDENT_REVIEW_20260925.md)
- [Capability pointer captured bytes](R026_CAPABILITY_POINTER_CAPTURED_BYTES_20260925.md)
- [Invocation model capability](R026_INVOCATION_MODEL_CAPABILITY_20260925.md)
- [Model artifact same-bytes loader](R026_MODEL_ARTIFACT_SAME_BYTES_20260925.md)
- [Model resolution facts](R026_MODEL_RESOLUTION_FACTS_20260925.md)

### 2. Preparation 與 typed handoff（3 份）

- [Ordered preparation facts](R026_ORDERED_PREPARATION_FACTS_20260925.md)
- [Prepared runtime input types API 設計](R026_PREPARED_RUNTIME_INPUT_TYPES_API_DESIGN_20260925.md)
- [Post-calibration typed handoff API](R026_POSTCALIBRATION_TYPED_HANDOFF_API_20260925.md)

### 3. Live calibration、source identity 與 SQLite lease（5 份）

- [Live calibration source identity](R026_LIVE_CALIBRATION_SOURCE_IDENTITY_20260925.md)
- [Live calibration SQLite read-lease wiring](R026_LIVE_CALIBRATION_SQLITE_LEASE_WIRING_20260925.md)
- [Live source identity shadow capture](R026_LIVE_SOURCE_IDENTITY_SHADOW_20260925.md) → [投影後 sidecar recheck](R026_LIVE_SOURCE_IDENTITY_POST_PROJECTION_20260925.md)
- [SQLite read-lease 試作](R026_SQLITE_READ_LEASE_20260925.md)

### 4. Market/source revision rows 與 aggregate（3 份）

- [Source revision evidence aggregate](R026_SOURCE_REVISION_EVIDENCE_AGGREGATE_20260925.md)
- [TAIEX market index row evidence](R026_TAIEX_MARKET_INDEX_ROW_EVIDENCE_20260925.md) → [獨立複審](R026_TAIEX_MARKET_INDEX_ROW_EVIDENCE_INDEPENDENT_REVIEW_20260925.md)

### 5. Daily-price receipt、namespace 與 custody（6 份）

- [Daily-price receipt link characterization](R026_DAILY_PRICE_RECEIPT_LINK_CHARACTERIZATION_20260924.md)
- [Direct daily-price typed receipt](R026_DIRECT_DAILY_PRICE_TYPED_RECEIPT_20260925.md)
- [Excluded daily-price namespace Slice 5 紅測基線](R026_EXCLUDED_DAILY_PRICE_NAMESPACE_SLICE5_20260925.md)
- [Excluded daily-price Slice 5B atomic-replace QA](R026_EXCLUDED_DAILY_PRICE_SLICE5B_ATOMIC_REPLACE_RED_20260925.md)：原件保留修補前紅測與後續 bounded 證據，逐段依原文範圍判讀。
- [Historical raw snapshot custody](R026_HISTORICAL_RAW_SNAPSHOT_CUSTODY_20260925.md)
- [TWSE daily-price SQLite row evidence](R026_TWSE_DAILY_PRICE_SQLITE_ROW_EVIDENCE_20260925.md)

### 6. Historical replay 與版本一致性（2 份）

- [Per-call cutoff characterization](R026_HISTORICAL_REPLAY_PER_CALL_CUTOFF_20260925.md)：保留整輪 observation lease 修復前的歷史行為，不作修補後行為證明。
- [Cross-call mixed-version characterization](R026_HISTORICAL_REPLAY_CROSS_CALL_MIXED_VERSION_20260925.md)：連同文件內的 whole-replay observation lease follow-up 閱讀，判斷修補後邊界。

## 邊界

- 每份 QA 只證明其標示的日期、輸入、來源 namespace、profile 與切片；`ACCEPTED_SCOPE` 不等於整個 R026 或 ML Gate 通過。
- 本頁沒有搬移或改寫任何原始 QA、SHA、log、測試輸出或 migration status。
- R026 的整體狀態、supported caller/profile handoff 與 source-evidence 子切片是不同判讀面；若後續證據改變，更新相應權威狀態文件與本頁閱讀提示，不回寫歷史收據。
