> **歷史封存警語（2026-10-10）：**本文保留當時的派送內容；其中 SHA（如有）、scope、角色、指令與狀態僅代表原快照，不得據此重派、重跑或視為目前任務／授權。現況請以 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md) 與 [REFACTOR_MODEL_ASSIGNMENTS](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_MODEL_ASSIGNMENTS.md) 為準；後續 Wave 1 狀態見 [WAVE1_R007_TZNAME_CHECKPOINT](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE1_R007_TZNAME_CHECKPOINT.md)。

# GEMINI_TASK_PACKET — R006

## ROLE

你是受控重構 implementation agent，專責 ML compatibility／artifact ABI 基線。架構已定案；你的任務是唯讀盤點、受控 fixture 驗證與 ABI→test mapping，不是清理或重建 ML。

## TASK ID

R006 — ML compatibility／artifact ABI 基線（Wave 1）。

## PURPOSE

建立 source contract 與實際可見 artifact 兩層基線，供 R010、R026、R027 判斷 existing calculated data、historical stores、models 與 checkpoints 是否仍可沿用。移檔、re-export 或 class path 變更在沒有此基線前不得進行。

## CURRENT SYSTEM CONTEXT

- Historical feature registry 有固定 20 個 ordered integer features、dtype/unit/missing/availability contract。
- Direct/OOC 有 binary stores、row/fold refs、carry/checkpoint、15 條 source identity dependencies 與 stable/runtime integrity。
- Recommendation calibration 有 snapshot provider、feature builder、model manifest/loader、projection receipts。
- R001 已 PASS，基線記錄 15 paths、manifest schemas、feature/label registry、11,559 manifest filenames、83,105 serialized filenames；unknown joblib/pickle 未被載入。兩個無 sidecar legacy `.pkl` 保持 opaque。
- 開始時重新記錄實際 HEAD/dirty state；不得修改 R001 baseline 或其他 Wave 1 task files。

## AUTHORITATIVE ARCHITECTURE

- `REFACTOR_TASKS/R006.md`：完整 task contract。
- `FINAL_ML_COMPATIBILITY_CONTRACT.md` §3–§8：schema、numerical、artifact、source identity、loader 與 experiment gates。
- `FINAL_ARCHITECTURE_INVARIANTS.md`：INV-01、INV-05、INV-06、INV-14、INV-15、INV-18。
- `FINAL_MIGRATION_SEQUENCE.md` 的 TMP-ML-01、TMP-ML-02 與 permanent compatibility readers/aliases。
- `REFACTOR_VALIDATION_MATRIX.md` 的 `V-ML-SMALL`、`V-ML-DIRECT` 與 R006 row。

## RELEVANT INVARIANTS

- 舊 artifact 先以原 bytes/hash 驗證，再建立 read view；不得重寫舊檔或偽造新 hash。
- Feature names/order、dtype、unit、scale、missing、normalization、mask、row/fold refs 與 source identity 不得改。
- Unknown binary 不得反序列化；只有 repository-controlled fixture 可走 safe loader。
- 必要 historical decoder/class alias 是永久 compatibility，不能當 temporary evaluator。
- Stable identity 與 runtime integrity 必須分開記錄。

## COMPLETED DEPENDENCIES

R001：PASS。已完成 source-level ML inventory 與 filename census，並保守標示 external artifacts/class paths unknown。R010/R026/R027 尚未開始；不得預設其 contracts 或 experiment verdict。

## ALLOWED SCOPE

- 唯讀 manifest/artifact inventory、source identity 計算的受控讀取、repo fixture safe-loader tests。
- 新增小型 ABI/compatibility tests與 `docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md` 或等價 bounded QA 報告。
- 使用既有 tmp fixtures；所有新增輸出留在 repository test temp／docs。
- 新增 `REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md`。

## OUT OF SCOPE

- 不反序列化未知 external joblib/pickle；不載入兩個無 sidecar legacy model。
- 不訓練、重訓、rebuild、回填、修復、promote、quarantine 變更或 active-pointer update。
- 不改 15-path allowlist、source files、hash、feature registry、checkpoint、model bytes、formal data 或 scheduler。
- 不建立 PreparedMLInput 或執行 R010/R026/R027。
- 不 stage、commit、push、reset、clean。

## FILES LIKELY INVOLVED

- Read-only：`ml_module/model_artifact_manifest.py`、`ml_module/model_artifact_loader.py`、historical snapshot/feature modules、recommendation calibration contracts／receipts。
- Read-only Direct boundary：`data_module/portfolio_ml_direct_numeric_store.py` 及其 `_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS` 所列 15 files、checkpoint/provenance readers。
- 新增專用 tests，例如 `tests/test_refactor_ml_compatibility_baseline.py`；不得修改 frozen production files。
- Existing tests：`test_ml_historical_snapshot_provider.py`、`test_ml_historical_feature_computation.py`、`test_ml_model_artifact_manifest.py`、`test_ml_model_artifact_loader.py`、`test_ml_direct_computation_dependency_guard.py`、`test_ml_direct_checkpoint_provenance_recovery.py`、`test_ml_direct_numeric_shared_reuse.py`、`test_ml_shadow_dependency_boundary.py`、`test_ml_shadow_projection_boundary.py`。

## CURRENT BEHAVIOR TO PRESERVE

Ordered feature/label IDs、dtype/unit、`None→NaN`、imputer/scale、HGB mask、OOC endianness/field order、row/fold refs、Direct carry/checkpoint、manifest/library/class paths、safe-loader rejection、quarantine/promotion gates、receipt identity 與 source fingerprints。

## IMPLEMENTATION REQUIREMENTS

- 產出兩層清冊：source-declared contract；實際可安全觀察的 repository-controlled artifact/fixture。
- 每個項目列 schema/order/dtype/unit/scale/missing/mask/row refs/source ID/class path evidence、reader/writer authority、safe loader status、unknown/unsupported handling。
- 15-path identity 逐一列 path、存在性、目前 hash/fingerprint證據與 downstream owner；不得更動順序或檔案。
- 只對 repository-controlled fixture 呼叫 existing safe loader，並測試合法 load 與 hash/schema/class rejection。
- External artifacts 只做 filename/manifest metadata/hash 的安全讀取；不能由 JSON 沒 class field 推論 binary 無 qualified path。
- 建立 ABI→test mapping，明確交給 R010/R026/R027 哪些證據可用、哪些仍 unknown。

## NUMERICAL COMPATIBILITY

`ML_COMPATIBILITY_RISK: CRITICAL`。Exact preserve feature order、integer values、dtype、unit、NaN/missing、scale、mask、endianness、row order、fold refs、carry/checkpoint。不得重新量化、轉 float、容忍數值漂移或重新生成 store 來配合新測試。

## PERSISTENCE COMPATIBILITY

所有正式 artifact、manifest、checkpoint、pointer、receipt 唯讀。不得新增 sidecar 追認 unknown availability，不得改 mtime/bytes，不得寫 formal DATA_ROOT。受控 fixture 只能在 `tmp_path`。

## REPLAY COMPATIBILITY

不修改 replay。若 Direct/OOC fixture 涵蓋 historical rows，驗證 row/fold/source refs 可讀且不被重算；不執行 portfolio replay 或產生新 evidence。

## ML COMPATIBILITY

這是本 task 核心。舊 data/model 是否可用只能由既有 reader/safe loader 和已知 fixture 證明；unknown 保持 unknown。報告需區分：verified compatible、verified rejected by policy、unsupported/unknown、not inspected for safety。

## REQUIRED TESTS

- 新增 bounded ABI baseline tests。
- `tests/test_ml_historical_snapshot_provider.py`
- `tests/test_ml_historical_feature_computation.py`
- `tests/test_ml_model_artifact_manifest.py`
- `tests/test_ml_model_artifact_loader.py`
- `tests/test_ml_direct_computation_dependency_guard.py`
- `tests/test_ml_direct_checkpoint_provenance_recovery.py`
- `tests/test_ml_direct_numeric_shared_reuse.py`
- `tests/test_ml_shadow_dependency_boundary.py`
- `tests/test_ml_shadow_projection_boundary.py`
- Changed Python `py_compile`、`git diff --check`；必要時執行既有 quant/dependency guard，但不得啟動 full rebuild。

## ACCEPTANCE CRITERIA

- 兩層清冊與 ABI→test mapping 完整，15 paths、registries、manifest/loader、row/fold/checkpoint、class path evidence 均有狀態。
- 所有正式／external bytes 未改，未知 binary 未載入。
- Controlled safe-loader fixture 的成功與拒絕行為有測試。
- Existing focused ML tests 通過，或既有 baseline failure 有 exact evidence/owner；不得用 allowlist 掩蓋。
- R010/R026/R027 有明確輸入清單與 unresolved unknowns。

## STOP CONDITIONS

- 任一工具將寫入 formal DATA_ROOT、artifact、checkpoint、pointer、receipt 或 scheduler state。
- 完成任務必須載入 unknown joblib/pickle、full rebuild、重訓、改 15-path list 或修改 frozen production source。
- 發現 authority 與實際 ABI 有重大矛盾，使 existing calculated data 無法依核准邊界安全解讀。
- 資源成本會變成全市場 rebuild／長時間 production workflow。

立即停止並回報 `ARCHITECTURE_BLOCKER` 或明確 scope blocker；不要發明新 identity 或 compatibility adapter。

## REQUIRED IMPLEMENTATION REPORT

建立 `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md`，包含 HEAD/dirty baseline、changed files、artifact counts、verified/unknown matrix、safe-loader results、15-path identity、tests/results、未執行重工作、rollback 與 R010/R026/R027 handoff。末行只能是：

`IMPLEMENTATION_STATUS: READY_FOR_REVIEW`

或 `IMPLEMENTATION_STATUS: CHANGES_REQUIRED`

或 `IMPLEMENTATION_STATUS: ARCHITECTURE_BLOCKER`

Do not redesign the architecture.

Do not perform unrelated cleanup.

Do not silently fix unrelated bugs.

Do not begin another R-task.

If repository evidence contradicts this task specification in a way that prevents safe implementation, stop and report ARCHITECTURE_BLOCKER with evidence.
