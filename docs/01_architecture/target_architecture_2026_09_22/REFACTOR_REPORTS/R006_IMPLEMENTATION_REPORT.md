> **歷史狀態導讀（2026-10-11）**：本文原始 `IMPLEMENTATION_STATUS: READY_FOR_REVIEW` 與 2026-09-27 的 inventory／retention 裁定，應依各自時點閱讀；R031 task index 將 R006 原 scope 列為 `CLOSED`。未知正式 model binaries 仍未 load／predict，保留為 RK-19 unsupported compatibility risk；本結案不宣稱模型或 prediction 相容。詳見 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 與 [R006 unknown-artifact retention addendum](../../../06_qa/R006_UNKNOWN_ARTIFACT_RETENTION_ADDENDUM_20260927.md)。

# R006 實作報告

- TASK：R006
- IMPLEMENTER：Luna Max
- BASELINE HEAD：`391b057c92037ec7a19cab2bf951d6029d29b020`（`dev`）
- SCOPE：只更新 R006 核准的測試、ML ABI QA baseline 與本報告；未改 production code、allowlist 或正式 artifact。

## 實作結果

修正原 R006 證據中的過度宣稱，將 source-declared contract、實際磁碟 bytes、Direct 穩定計算身份、runtime dependency snapshot、受控 fixture 載入和未知 serialized artifacts 分開。詳細清冊在 [`REFACTOR_ML_ABI_BASELINE_R006_20260922.md`](../../../06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md)。

15 個 Direct dependency paths 已逐檔記錄 bytes 與 raw SHA-256。穩定 identity `sha256:1591edf147512bf07adad7311f1a3392bd8ddcdb09e60665746b9ef83032715c` 與 runtime dependency snapshot `sha256:0b23fbb44dc99c13f75c638aca1bc325f4585e714d018d2d8a223a15a20e7087` 分帳；identity 使用 dependency path/source bytes/compiled-source fingerprint，不含 loaded-module state 或 runtime constants。檢查程序觀察到 14/15 loaded modules 的 loaded code fingerprint 與 source 相同；`data_module/teacher_input_source_producer.py` 在該程序中未載入，所以只列磁碟 bytes/hash，不宣稱 loaded-code match。

歷史 `core-long-history-features-v1` 的 20 個有序 feature IDs、整數 dtype、units、availability 與 missing policies 現在有明確斷言。測試確認模型矩陣邊界將 missing `None` 轉為 `NaN`，而觀測到的零仍為 `0.0`。這個歷史 20 欄 contract 與 Direct/OOC 持久化 manifest 的 62 欄資料分開記錄。

`SafeShadowModelArtifactLoader` 的成功案例使用 pytest 臨時目錄中剛建立的 joblib fixture、相符 manifest 與 loader 預設 deserializer，沒有注入 lambda。其測試 class path 為 `test_refactor_ml_compatibility_baseline.ControlledFixtureModel`；它只證明受控 fixture 可載入，不代表任何正式模型 class path。未載入未知 joblib/pickle。Direct pointer/checkpoint、OOC manifest、selected artifact 和兩個 sidecarless legacy pickle 的 metadata、檔案 SHA 與未知狀態分別列入 QA 清冊；正式資產的 18 個已清點檔案在工作前後重新雜湊均相同。

本次沒有進行 production inference、數值 parity 或 replay 執行，因此不宣稱業務行為、數值相容或回放相容已被端到端驗證。Direct/OOC 驗證限於 source/schema/reference metadata 與 read-only bytes/hash；沒有讀取未知 pickle/joblib 內部物件。

## 驗證

R006 新測試檔單獨執行：`8 passed`（0.22s）。修改後的 Python 測試檔 `py_compile` 通過。`git diff --check` exit 0；它對 tracked working-tree paths 給出既有 LF→CRLF 設定提示，沒有 whitespace error。另對三個 R006 目標檔檢查 UTF-8、結尾 LF 與 trailing whitespace，均通過。

完整 focused suite 使用下列 10 個檔案：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_refactor_ml_compatibility_baseline.py tests/test_ml_historical_snapshot_provider.py tests/test_ml_historical_feature_computation.py tests/test_ml_model_artifact_manifest.py tests/test_ml_model_artifact_loader.py tests/test_ml_direct_computation_dependency_guard.py tests/test_ml_direct_checkpoint_provenance_recovery.py tests/test_ml_direct_numeric_shared_reuse.py tests/test_ml_shadow_dependency_boundary.py tests/test_ml_shadow_projection_boundary.py -q -o addopts= -p no:cacheprovider
```

結果：`73 passed, 1 failed in 477.36s`。唯一失敗是已知 baseline `tests/test_ml_shadow_dependency_boundary.py::test_repository_respects_ml_shadow_dependency_boundary`，與 SOL review 記錄相同的四個 imports：

```text
production_imports_ml_module:app_module\personalization_projection.py:ml_module.recommendation_inference_provenance:read_inference_projection_receipt
production_imports_ml_module:app_module\personalization_save_adapter.py:ml_module.recommendation_inference_provenance:read_inference_projection_receipt
production_imports_ml_module:app_module\recommendation_calibration_consumer.py:ml_module.recommendation_calibration_training:RECOMMENDATION_RETURN_BASIS
production_imports_ml_module:app_module\recommendation_calibration_consumer.py:ml_module.recommendation_calibration_training:recommendation_label_contract_id
```

此既知 failure 僅記錄；沒有修改 allowlist、production source 或相關 boundary 行為。

## Dirty baseline 與範圍

開始時工作目錄有 96 個 dirty paths；三個核准的 R006 目標檔當時已是 untracked 且有內容。完成驗證時 HEAD 仍為基線 commit；工作目錄有 100 個 dirty paths。比對起始 status/bytes 後，88 個非 R006 既存 paths 保持不變；5 個非 R006 既存 paths 有內容變化，另有 4 個新 R003/R005 review paths。這些變更不屬於 R006，本任務沒有讀寫或還原它們：

- 既存內容不同：`docs/01_architecture/target_architecture_2026_09_22/REFACTOR_MODEL_ASSIGNMENTS.md`、`docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R003_IMPLEMENTATION_REPORT.md`、`docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md`、`tests/test_recommendation_execution_state_characterization.py`、`tests/test_recommendation_replay_characterization.py`。
- 新增 paths：`docs/01_architecture/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R003.md`、`docs/01_architecture/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R005.md`、`docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R003_SOL_REWORK_REVIEW.md`、`docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R005_SOL_REWORK_REVIEW.md`。

## 相容性與未決事項

| 項目 | 結果 |
|---|---|
| Direct source paths | 15/15 可讀；raw bytes/hash、穩定 identity 與 runtime snapshot 分開列出。14 個 loaded code 比對通過，1 個模組當次未載入。 |
| Historical feature ABI | 20 欄順序/dtype/unit/missing/availability 有測試斷言；不是模型數值 parity 驗證。 |
| Direct/OOC artifact references | pointer、checkpoint、manifest 與 selected Direct 2026 數值資產引用已核對；重新雜湊的 18 個清點檔案未變。 |
| SafeShadow loader | 一個 test-created joblib fixture 經預設 loader 載入成功；其他負向政策測試為 injected deserializer。Direct identity 不由此 loader 綁定。 |
| Production/legacy serialized models | 未載入；sidecarless pickle 與 selected OOC joblib 的 estimator class paths/相容性仍 unknown。未知 binary 是否會被 loader 拒絕或隔離未驗證。 |
| ML dependency boundary | 存在上述既知 4-import baseline failure；依任務限制保留，沒有改 allowlist/production。 |
| Behavior/numeric/replay compatibility | 沒有 production execution 或 prediction comparison，本次不作端到端相容性宣稱。 |

- **ARCHITECTURE_BLOCKER：** 無；source/artifact 清冊可在核准唯讀範圍內完成。
- **UNRESOLVED RISKS：** 未知 serialized artifact 的 class path 與實際相容性仍未檢視；既知 boundary failure 維持現狀。
- **BLOCKER STATUS：** None.

IMPLEMENTATION_STATUS: READY_FOR_REVIEW

## SOL 審查回修（2026-09-22）

本輪依 `R006_SOL_REWORK_REVIEW.md` 的四項 finding 完成本範圍回修，仍只修改核准的三個 R006 目標檔。QA 清冊已為 15 條 Direct source path 各列 source module 責任，並為 Direct、OOC、manifest-based SafeShadow 與 sidecarless legacy assets 分列程式宣告的 reader/writer 路徑；明確說明程式角色不等於 DATA_ROOT 寫入授權或 Windows ACL。ABI 對照表逐項涵蓋歷史 20 欄、`None → NaN`、imputer/scale、HGB mask、Allocation feature order/scale、OOC dtype/mask/fold refs、Direct identity/checkpoint/carry，以及 manifest/library/class path，並使用 `source-declared`、`controlled-fixture verified`、`artifact-readback verified`、`unknown` 四級狀態。QA 的說明文字與測試檔兩處英文註解已改為繁體中文；schema、欄位、hash、test symbol、class path 與四個證據狀態值保留原字面值。

### 本輪驗證

受影響的 focused 測試命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_refactor_ml_compatibility_baseline.py tests/test_ml_model_artifact_manifest.py::test_load_contract_rejects_registry_family_schema_and_library_mismatch tests/test_ml_model_artifact_loader.py::test_validated_fixture_is_deserialized_only_after_contract_checks tests/test_ml_historical_feature_builder.py::test_load_contract_freezes_registry_order_dtype_unit_and_schema_hash tests/test_ml_historical_feature_builder.py::test_missing_value_and_observed_zero_remain_distinct tests/test_ml_historical_training_service.py::test_training_uses_fold_only_preprocessing_and_freezes_both_model_families tests/test_ml_historical_training_service.py::test_all_missing_training_column_keeps_frozen_feature_shape_without_warning tests/test_ml_direct_checkpoint_provenance_recovery.py::test_stable_computation_identity_excludes_runtime_state tests/test_ml_direct_checkpoint_provenance_recovery.py::test_current_checkpoint_is_only_resume_candidate_after_full_readback tests/test_ml_direct_computation_dependency_guard.py::test_resume_requires_matching_dependency_snapshot tests/test_ml_direct_numeric_shared_reuse.py::test_carry_change_invalidates_later_year_shared_numeric_blocks tests/test_allocation_ooc_release_builder.py::test_minimal_ooc_release_attaches_calibrator_and_matches_direct_consumer tests/test_portfolio_ml_out_of_core_pipeline.py::test_base_oof_and_meta_use_only_prior_mature_folds tests/test_portfolio_ml_out_of_core_pipeline.py::test_hgb_fit_population_is_bounded_and_disclosed -q -o addopts= -p no:cacheprovider
```

結果：`21 passed, 1 warning in 137.69s`。唯一 warning 是 joblib/loky 在 Windows 無法判定實體核心數，改用邏輯核心數；測試通過。`tests/test_refactor_ml_compatibility_baseline.py` 全檔包含在此命令中。

本輪 Python assertions 與測試語意沒有變動，只將原有兩處註解翻成繁體中文。因此未重跑 10 檔長測；上輪實際結果仍是 `73 passed, 1 failed in 477.36s`，其中唯一 failure 為 `tests/test_ml_shadow_dependency_boundary.py::test_repository_respects_ml_shadow_dependency_boundary` 的四條已知 import，詳見前段。這項 baseline failure 仍只記錄，未改 allowlist、production code 或 boundary 行為。

本輪 `py_compile` 通過；`git diff --check` exit 0，只對工作樹其他既有 tracked paths 顯示 LF→CRLF 設定提示，沒有 whitespace error。三個目標檔最終均通過 UTF-8、結尾換行及 trailing whitespace 檢查。沒有讀取未知 joblib/pickle，沒有寫入正式 artifact 或 DATA_ROOT。

- **ARCHITECTURE_BLOCKER：** 無；SOL 四項 finding 均可在原核准 scope 內修正。
- **本輪測試語意變更：** 無；只有測試註解語言修正。
- **IMPLEMENTATION_STATUS：** READY_FOR_REVIEW（保留一項已知 shadow-boundary failure）。

## SOL 第二輪精確分帳修正（2026-09-22）

QA inventory 已將 R001 記錄的 7 個 manifests 精確歸回 `portfolio_ml_direct_numeric_production_v4_v2-source-rebuild-79dccf8b7f0b` 目錄。OOC `(year_ordinal, local_row_index)` 的 persisted encoding 現獨立列為 `source-declared`：`_build_fold_indexes` 以 `struct.pack("<qq", ordinal, int(local_row_index))` 寫出 tuple，`ROW_REF_DTYPE` 宣告 `<i8`；現有 R006 測試只檢查 dtype 常數，沒有逐列斷言 tuple 編碼，也沒有讀回正式 fold-index binary。`test_base_oof_and_meta_use_only_prior_mature_folds` 另列為 `controlled-fixture verified`，僅支持合成資料的 causal fold 時序／使用，不延伸為 persisted tuple 證據。檢查未發現可逐值驗證 persisted tuple 的測試。

本輪只改 QA 清冊與本報告，沒有測試斷言或 production 變更。重新執行 `tests/test_refactor_ml_compatibility_baseline.py`：`8 passed in 0.20s`；`py_compile` 通過；`git diff --check` exit 0，僅有工作樹其他既存 tracked paths 的 LF→CRLF 設定提示。上一輪 21 個受影響 focused 測試（含 causal fold 測試）仍是 `21 passed, 1 warning in 137.69s`，本輪未重跑該組，因本次只有文件分帳修正。上輪 10 檔長測 `73 passed, 1 known failure` 同樣保留，failure 為既知 shadow-boundary 四條 import，未改 allowlist／production。

- **本輪 ARCHITECTURE_BLOCKER：** 無。
- **本輪未決事項：** 正式 fold-index binary 的每列 tuple 尚未讀回或測試驗證，狀態維持 `source-declared`。

## 2026-09-27 unknown artifact retention 狀態補充

依 R006 原文，未知來源反序列化明列 OUT OF SCOPE；acceptance 要求 class paths/source IDs及 unknown 狀態清楚、唯讀 bytes不變，objective 要求每個 unknown 有保留策略。新 root symbolic probe 對兩個 legacy pickle 僅做 opcode stack/memo 解析（各81,620 ops、10個 external refs、unresolved=0），未 import globals、未執行 reducer、未 load/predict；前後 SHA 相同。OOC 僅對10個精確selected run paths驗bytes/hash；單一 head 在 bounded zlib/pickle-prefix scan 到269 opcodes後因 ndarray raw block停止，狀態仍 `PARTIAL`，未驗 class path或 prediction。兩個 legacy pickle 與 selected OOC head 的 unknown／partial scope與retention均列於 [R006 unknown artifact addendum](../../../06_qa/R006_UNKNOWN_ARTIFACT_RETENTION_ADDENDUM_20260927.md)。

此更新只裁定 R006 inventory/retention 原 acceptance 範圍；不改寫本報告歷史 73P/1F、21P focused run或未知正式模型狀態。RK-19仍追蹤 formal unknown binaries/class paths 的unsupported compatibility risk；沒有任意 pickle load、prediction或完整83k recursive inventory通過聲明。

## 2026-09-27 scoped disposition crosslink

R006 scoped inventory與unknown-retention依原任務範圍已達；原規格將未知來源反序列化列為OUT OF SCOPE，並要求未知項狀態與保留策略明確。正式未知binary仍未load/predict，維持RK-19 unsupported compatibility risk；這不構成本R006 inventory task的未完成工程。細節與bounded raw evidence見 [R006 unknown artifact retention addendum](../../../06_qa/R006_UNKNOWN_ARTIFACT_RETENTION_ADDENDUM_20260927.md)。本狀態不改寫歷史73P/1F或21P focused receipts。
