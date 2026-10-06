# Gemini 獨立審查：R006 Luna 回修

## ROLE／TASK ID／PURPOSE

你是 R006 的獨立 Gemini reviewer。請在 `C:\Projects\PythonProjects\technical_analysis` 唯讀審查實際三檔、source 與受控測試，對照下面完整 R006 規格、報告、QA 清冊及 SOL 審查紀錄。SOL 初審可送 review，不等於 R006 最終 PASS。不要修改 repository。

## CURRENT SYSTEM CONTEXT／COMPLETED DEPENDENCIES

R001 已 PASS；Wave 1 的 R002、R004、R007 已 PASS；R003、R005 的 Luna 回修亦各自待 Gemini 正式 review。Wave 2–14 blocked。HEAD 基線 `391b057c`，有其他既存 dirty files。R006 原先 Gemini 實作經 SOL 判 `CHANGES_REQUIRED`，Luna 僅在原 R006 scope 修正；前兩輪 SOL 精確 findings 與回應如下完整附錄。

## AUTHORITATIVE ARCHITECTURE／RELEVANT INVARIANTS

`FINAL_ML_COMPATIBILITY_CONTRACT.md` §3–§8、`FINAL_ARCHITECTURE_INVARIANTS.md` INV-01／05／06／14／15／18、`REFACTOR_VALIDATION_MATRIX.md` 為權威。既有 calculated data、schema、dtype、feature order、mask、checkpoint、source identity、模型 class paths 與權限邊界不得在本重構中被暗改。R006 僅唯讀盤點與受控 fixture；不能藉測試重訓、重建、載入未知 serialized model 或發布任何正式權限。

## CHANGED-FILE／DIFF SCOPE

只審查 `tests/test_refactor_ml_compatibility_baseline.py`、`docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md`、`docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md`。SOL 凍結 SHA-256 依序為 `ee182953773ebbf3e8e4d77632454bba8ee45bd7f9f0124a4e2d2634e9372f0e`、`f3c609ecc79398c5863ec03c2015036ef5b83e41eed34b9b960130c8db90ffd2`、`be26a22c42e6133711d0ebabc869922d17d5848570f8c6155cc7c7eca97df4b7`。先核對目前 bytes；若 drift，停止本輪審查，請 SOL 重凍結。不可改正式 DATA_ROOT、source list、production code、manifest、pointer、checkpoint 或 unknown binary。

## REQUIRED REVIEW／TESTS ALREADY EXECUTED

SOL 獨立重算 QA 表的 15/15 Direct source raw bytes/size/hash，均相符；SOL 於最終 Python 測試版本獨立重跑 R006 新測試 `8 passed`，exit 0。Luna 執行 ABI 對照 affected focused tests `21 passed, 1 warning in 137.69s`；更早完整 10 檔 focused suite 為 `73 passed, 1 failed in 477.36s`，唯一失敗是原有 shadow boundary 的四條 production→ML import。該 failure 沒有被修補、allowlist 或改 production；不得把完整 suite 說成 PASS。精確命令在實作報告。

請檢查 acceptance criteria、ML/numerical compatibility 的證據強度、source-declared／controlled-fixture／artifact-readback／unknown 分帳、15-path stable identity 與 runtime loaded-code 區別、歷史 20 欄、OOC/Direct tuple/mask/carry/refs、正式 artifact hash/class path、safe loader 受控 fixture、權限與 read-only 邊界、未觀察的 hidden state、依賴方向、scope creep 和測試不足。請特別避免從 DummyModel、test-created joblib 或 JSON metadata 推論真實舊模型已相容。

只回報 R006 原 scope 的精確 findings；不可要求為了 review 載入未知 pickle/joblib、修改正式 DATA_ROOT 或重做完整市場資料。最終狀態必須恰好一項：`REVIEW_STATUS: PASS`、`REVIEW_STATUS: CHANGES_REQUIRED`、`REVIEW_STATUS: BLOCKED`。

## 原始 R006 task specification（完整）

# R006 — ML compatibility／artifact ABI 基線

## TASK CONTEXT

ML有Historical 20欄schema、Direct/OOC binary與checkpoint、joblib models、recommendation projection receipts及15條source identity dependencies。第一輪重構必須把它們當相容consumer。

## WHY THIS TASK EXISTS

R010/R026/R027不能只依source常數推論磁碟資產；移檔、re-export或class path變更可能使舊data/model不可用。

## AUTHORITATIVE ARCHITECTURE REFERENCES

- [FINAL_ML_COMPATIBILITY_CONTRACT §3–§8](../FINAL_ML_COMPATIBILITY_CONTRACT.md)
- [FINAL_ARCHITECTURE_INVARIANTS INV-14、15、18](../FINAL_ARCHITECTURE_INVARIANTS.md)

## DEPENDENCIES

R001。

## ALLOWED SCOPE

唯讀manifest/artifact inventory；新增小型ABI tests與QA報告；使用現有fixtures。

## OUT OF SCOPE

反序列化未知來源、重訓、rebuild、修復/回填、改source list、搬凍結檔。

## CURRENT BEHAVIOR TO PRESERVE

ordered IDs/dtype/unit、None→NaN、imputer/scale、HGB mask、OOC endianness/field order、row/fold refs、Direct carry/checkpoint、manifest/library/class paths、quarantine/promotion gates。

## IMPLEMENTATION OBJECTIVE

建立source contract與實際可見artifact兩層清冊；記錄stable identity與runtime integrity；每個unknown資產有保留策略。

## ARCHITECTURAL INVARIANTS

INV-01、05、06、14、15、18。

## ML COMPATIBILITY REQUIREMENTS

ML_COMPATIBILITY_RISK：盤點本身不得load未知joblib。只有repo受控fixture可以走safe loader。15路徑與原hash不變。

## PERSISTENCE COMPATIBILITY REQUIREMENTS

所有artifact唯讀；不生成sidecar追認unknown availability，不更新active pointer/checkpoint。

## TEST REQUIREMENTS

historical snapshot/feature、model manifest/loader、direct dependency/checkpoint、shared reuse、shadow boundary focused tests。

## ACCEPTANCE CRITERIA

清冊含schema/order/dtype/scale/mask/row refs/class paths/source IDs；所有讀取未改bytes；未知項清楚。

## EXPECTED DELIVERABLES

ML baseline報告、small fixtures、ABI→test mapping、R027輸入清單。

## POST-TASK REPORT REQUIREMENTS

報告artifact counts、unknown/unsupported、safe-loader結果、沒有執行的重工作。

## ROLLBACK / FAILURE CONDITIONS

任何工具欲寫正式root、載入未知pickle或耗用full rebuild即停止。回滾移除新增文件/tests。

## R006 implementation report（完整）

# R006 實作報告

- TASK：R006
- IMPLEMENTER：Luna Max
- BASELINE HEAD：`391b057c92037ec7a19cab2bf951d6029d29b020`（`dev`）
- SCOPE：只更新 R006 核准的測試、ML ABI QA baseline 與本報告；未改 production code、allowlist 或正式 artifact。

## 實作結果

修正原 R006 證據中的過度宣稱，將 source-declared contract、實際磁碟 bytes、Direct 穩定計算身份、runtime dependency snapshot、受控 fixture 載入和未知 serialized artifacts 分開。詳細清冊在 `REFACTOR_ML_ABI_BASELINE_R006_20260922.md`（開發收據見dev）。

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

## R006 QA ABI baseline（完整）

# ML 相容 ABI 基線（R006）

- 盤點日期：2026-09-22
- 基線 HEAD：`391b057c92037ec7a19cab2bf951d6029d29b020`（`dev`）
- 狀態：已盤點，可供審查；未知序列化資產仍維持未載入

本文件分別記錄來源宣告的合約、直接讀取的原始檔案位元組、Direct 穩定計算身份、目前資產引用，以及受控測試樣本的結果。這些證據不能互相替代：manifest 中繼資料不表示模型已反序列化；檔案 SHA 不表示模型 class path 已知；Direct identity 也不表示 `SafeShadowModelArtifactLoader` 綁定了 Direct paths。

## 基線與可觀察範圍

檢查開始時 HEAD 為上述 commit，工作目錄有 96 個 dirty paths（5 個 tracked modified、91 個 untracked）。本任務的三個核准目標檔當時已存在且帶有未提交內容；修改時保留並在這三個目標內修正。其他 93 個 dirty paths 不屬於本任務。15 個 Direct source paths 在 Git status 中為 clean；其下表 SHA 是目前磁碟讀到的原始 bytes 雜湊，不是 Git blob 雜湊。Windows CRLF 使部分磁碟 bytes 雜湊與 Git blob 不同，不能據此判定 source 檔已變更。

本次對 DATA_ROOT 中下列精確路徑取得了讀取及雜湊結果；這只證明本次程序成功讀取這些檔案，不是 Windows ACL 或整個資料根目錄的權限稽核。未嘗試寫入正式資料根目錄、重建資料、補 sidecar 或載入未知 pickle/joblib。

## Direct 15 條來源路徑原始位元組與 identity

下列路徑按 `_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS` 宣告順序列出。大小是本次讀到的位元組數；SHA-256 是對該檔案原始位元組計算。責任欄說明程式碼模組的功能歸屬，不代表其具有正式 DATA_ROOT 寫入許可。

| # | Direct dependency 路徑 | 位元組數 | 原始 source SHA-256 | 來源模組責任／程式角色 |
|---:|---|---:|---|---|
| 1 | `data_module/portfolio_ml_direct_numeric_store.py` | 240,272 | `sha256:017ae82cc6dd3466a6a1e3a17eca1edc88a94d114f03783acb4c14f90cc41509` | Direct store 建置、checkpoint/identity 維護及 provenance 復原。 |
| 2 | `data_module/portfolio_ml_dataset_assembler.py` | 198,677 | `sha256:f8fd70c43bf18a3e507e0b44325aaf45a856a537829af7d7d0f2a0c7d6cf3b91` | `PortfolioMLDatasetAssembler`：組裝 dataset、features 與 labels。 |
| 3 | `data_module/portfolio_ml_out_of_core_store.py` | 61,094 | `sha256:11ab46b71e81b0d72b6a39ec587454a9d332dc7360e53eb58d745c66ab09225a` | `PortfolioMLOutOfCoreStoreBuilder`：年度數值陣列、mask、target、label 與 fold index 發布。 |
| 4 | `data_module/ml_storage_capacity.py` | 82,443 | `sha256:60202f419c06015a1d283579fd8ce204f6f7218a2348f3d74f4ec3fabdc4bb15` | 儲存容量預檢、資源預算與 storage gate。 |
| 5 | `data_module/ml_pit_shared_block_resolver.py` | 31,682 | `sha256:1ec0b283a5fa8a1eb9c69e87cdca25ccbf04381743944c62a1df6fc8e90e2709` | 驗證並解析 PIT shared shard／publication 參照。 |
| 6 | `data_module/ml_direct_shared_block_resolver.py` | 20,198 | `sha256:9972bcd53fdc2a02abea47487f8c62f92b62895afde93e32212bd1661b98a4c4` | 驗證 Direct shared block 參照與年度重用。 |
| 7 | `data_module/formal_portfolio_ledger.py` | 24,107 | `sha256:1859ba515a4c4a33e61b139bb2a2b72eed93802f6c9ad00d81333bf74967112f` | 正式投資組合 ledger／持倉狀態資料來源。 |
| 8 | `data_module/rule_champion_snapshot_service.py` | 34,744 | `sha256:99c45420050e0ac78c17341dc4f9cc530435882b78fa0cc9f4a2dd5726b05645` | Rule champion snapshot 的建立與讀取服務。 |
| 9 | `data_module/teacher_input_source_producer.py` | 34,715 | `sha256:68bca304f7d2505d3f6a394f44a20b0507e99169600e790d119f171a9e11d5ad` | Teacher input source row 與 provenance 產生。 |
| 10 | `ml_module/allocation_training_service.py` | 84,519 | `sha256:b898d97cbcc7033ff53fe34c4f3ffedf53542942718a257a2db6a733f62881f6` | Allocation 訓練服務與模型 artifact 建立流程。 |
| 11 | `ml_module/allocation_contracts.py` | 23,660 | `sha256:dd18d81a5409b8aa176e77d89cbcd515da41e8140ae7f9b248c4ca526fc84343` | Allocation feature、label、weight 與輸出資料型別／驗證合約。 |
| 12 | `ml_module/allocation_teacher.py` | 23,302 | `sha256:c34f6ce1023ab1eb8f3899819cbb93701ab198c0f5bfcc20287d8e36f75477f1` | Causal allocation teacher policy、候選狀態與結果產生。 |
| 13 | `ml_module/immutable_ml_block_store.py` | 39,379 | `sha256:cd14ef0b8da2af8e1953f2f28c299277a779a9ffb1f06fb5f6d86057f7ac3400` | Immutable content-addressed ML block 發布與載入。 |
| 14 | `ml_module/purged_walk_forward.py` | 3,895 | `sha256:345edaccddfcc658d63bd1e0a69508594954eb9d72e2c48e1d9944c5e487ff4a` | Purged walk-forward fold 切分。 |
| 15 | `data_module/ml_price_availability_contract.py` | 11,019 | `sha256:6d503e6c2d77a16b0a49efdddb3770971b774be9d563d9668235a84e0bf6af9b` | 價格欄位可用日期與缺失狀態合約。 |

上述 owner 欄僅標示 source dependency 的模組責任；只有 source 中明確的讀寫函式才列為「程式宣告的 reader/writer」。函式存在不等於 DATA_ROOT 的作業許可或作業系統寫入權限。本次沒有對正式資料根目錄執行寫入。

### 資產 reader／writer 程式責任與本次邊界

| 資產類別 | source 宣告的 writer | source 宣告的 reader | 本次證據與邊界 |
|---|---|---|---|
| Direct numeric store、年度 carry、manifest 與 checkpoint | `data_module/portfolio_ml_direct_numeric_store.py` 的 Direct builder／年度發布與 checkpoint 程序。 | 同模組的 checkpoint/provenance/recovery 程序；`ml_module/allocation_out_of_core_training_service.py::_NumericStore` 可讀取並驗證 OOC/Direct 數值 store。 | 只讀 pointer、checkpoint、manifest、carry 與年度檔案 bytes/hash；未呼叫 builder、resume 或 recovery 寫入路徑，未解碼年度 array/carry 內容。 |
| 數值型 OOC store／fold indexes | `data_module/portfolio_ml_out_of_core_store.py::PortfolioMLOutOfCoreStoreBuilder.build`。 | `ml_module/allocation_out_of_core_training_service.py::_NumericStore` 載入 manifest、memmap 與 fold refs。 | R006 對 source 欄位/dtype 和選定年度檔案做唯讀核對；未建立正式 store。資產 hash readback 不等於讀取或驗證 array 值。 |
| OOC allocation model heads（`head-*.joblib`） | `ml_module/allocation_out_of_core_training_service.py` 的 expert 訓練／寫入流程使用 `joblib.dump`。 | `ml_module/allocation_ooc_release_builder.py::_load_joblib`。 | 僅讀取選定的 head 檔與 JSON sidecar 的 bytes/hash/keys；沒有呼叫讀取器，class path 仍為 unknown。 |
| 以 manifest 為依據的 SafeShadow 模型 | `ml_module/recommendation_calibration_training.py` 建立受控模型 bytes 與 `ModelArtifactManifest`；R006 測試則只在 pytest 臨時目錄用 `joblib.dump` 寫入 fixture。正式落盤 writer/執行權限不由 R006 推定。 | `ml_module/model_artifact_loader.py::SafeShadowModelArtifactLoader.load`；下游讀取端 透過此 loader 讀取。 | 一個測試自建 fixture 由預設 loader 實際載入；這只驗證受控 fixture 的 載入合約，不代表生產 artifact 已通過，也不代表 loader 綁定 15 個 Direct paths。 |
| `DATA_ROOT/models/` 兩個 legacy 沒有 sidecar 的 pickle | 未由 R001/R006 證據確認 owner 或受控 writer。 | 未由 R001/R006 證據確認受控 reader；SafeShadow 的適用性未知。 | 只讀檔案大小/hash，沒有讀取 pickle 內容或載入。class path、可載入性及相容性均為 unknown。 |

「程式宣告的 reader/writer」描述程式碼中可見的資料路徑，不構成誰獲准執行該路徑、誰有正式資產寫入權或 Windows ACL 的認定。除 pytest 臨時 fixture 外，本次只讀，沒有寫正式資產。

| 身份證據 | 值／解讀 |
|---|---|
| Stable identity schema | `portfolio-ml-direct-computation-identity.v1` |
| 目前穩定 Direct computation identity | `sha256:1591edf147512bf07adad7311f1a3392bd8ddcdb09e60665746b9ef83032715c` |
| 目前 runtime dependency snapshot hash | `sha256:0b23fbb44dc99c13f75c638aca1bc325f4585e714d018d2d8a223a15a20e7087` |
| 身份輸入 | 排序後的 dependency paths、原始 source hashes 與 compiled-source fingerprints；穩定 identity 不包含 loaded-module state 或 runtime constants。 |
| 執行期 loaded-code 觀察 | 隔離檢查程序載入 15 個模組中的 14 個，已載入模組的 code fingerprint 均符合當前 source。該次程序沒有載入 `data_module/teacher_input_source_producer.py`，因此不宣稱它有 loaded-code 比對結果。 |

穩定 identity 與 runtime snapshot 用途不同。目前 Direct pointer/checkpoint 記錄的穩定 identity 與 dependency snapshot，和唯讀 source 檢查結果相同。這不表示 15 個 paths 都曾載入，也不表示 SafeShadow loader 綁定了這些 source paths。

## 歷史 feature ABI

`ml_module/feature_registry.py` 宣告 registry `core-long-history-features-v1`（`sha256:1a2adbeee4aa4a3935be1e30bf31bfbc6136a8fa84d975a1429e5fee4326e4b6`）為有固定順序的 20 欄 schema。每欄 dtype 為 `int`，availability policy 為 `feature_as_of_before_decision`，missing policy 為 `missing_is_not_zero`。除了 `turnover_amount_minor` 使用 `minor_currency_unit`，其餘欄位單位都是 `bp`。這份歷史訓練 ABI 與目前 Direct OOC manifest 的 62 欄 store 是不同合約，欄數與 registry hash 不可互換。

| 順序 | Feature ID | dtype | unit |
|---:|---|---|---|
| 1 | `stock_return_1d_bp` | `int` | `bp` |
| 2 | `stock_return_5d_bp` | `int` | `bp` |
| 3 | `stock_return_20d_bp` | `int` | `bp` |
| 4 | `stock_return_60d_bp` | `int` | `bp` |
| 5 | `trailing_volatility_20d_bp` | `int` | `bp` |
| 6 | `high_low_range_20d_bp` | `int` | `bp` |
| 7 | `close_to_ma_5d_bp` | `int` | `bp` |
| 8 | `close_to_ma_20d_bp` | `int` | `bp` |
| 9 | `close_to_ma_60d_bp` | `int` | `bp` |
| 10 | `rsi_normalized_bp` | `int` | `bp` |
| 11 | `adx_normalized_bp` | `int` | `bp` |
| 12 | `macd_normalized_bp` | `int` | `bp` |
| 13 | `volume_ratio_5d_bp` | `int` | `bp` |
| 14 | `volume_ratio_20d_bp` | `int` | `bp` |
| 15 | `turnover_amount_minor` | `int` | `minor_currency_unit` |
| 16 | `market_return_5d_bp` | `int` | `bp` |
| 17 | `market_return_20d_bp` | `int` | `bp` |
| 18 | `market_return_60d_bp` | `int` | `bp` |
| 19 | `stock_minus_market_20d_bp` | `int` | `bp` |
| 20 | `industry_relative_return_20d_bp` | `int` | `bp` |

此合約的 歷史訓練矩陣 形狀為 `(rows, 20)`。在模型輸入邊界，`_matrix` 將已觀測整數轉為 數值陣列，並把 `None` 轉為 `NaN`；觀測值 0 保留為 `0.0`，與缺值不同。ABI 測試固定檢查欄位順序、dtype、unit、missing/availability policy，以及缺值與零的區分；測試沒有比較正式模型的預測數值，也沒有載入正式模型。

## Direct store 與 OOC 資產參照

Direct store 宣告的 schema 為 `portfolio-ml-direct-numeric.v4`，checkpoint 為 `portfolio-ml-direct-checkpoint.v2`，dependency snapshot schema 為 `portfolio-ml-direct-computation-dependencies.v1`，stable identity schema 為 `portfolio-ml-direct-computation-identity.v1`。目前 latest pointer 指向 run `direct-ooc-dca07415569065ee4e35266b`。

| 目前 Direct 證據 | 唯讀觀察 |
|---|---|
| `latest_manifest.json` | 282 bytes；原始 SHA `sha256:39539fafdc4bc2dbc23331fc6e643a80a32e1cafae1b2fbc6f9391854456320c`；pointer 記錄的邏輯 manifest hash 為 `sha256:e0549d1f5d0e947ebf5080f2f87735ebeea9dee547dbef62b07207ff461dbaac`。這兩個 hash 的計算語意不同。 |
| 目前的 `manifest.json` | 229,571 bytes；原始 SHA `sha256:fbe15bac043b82f109227a29ec1d7c44785e75bc9fb77ea20788582982497895`；schema `portfolio-ml-ooc-store.v3`；狀態 complete；3,266,947 列、62 個 features、horizons `[5, 10, 20, 60]`；feature registry hash `sha256:8b0f831a94ecd503591a146d36412b2385397928b98fbd607a33fa6073630f27`。 |
| 目前的 `checkpoint.json` | 33,275 bytes；原始 SHA `sha256:2eba7be2088f51d9df0fa473c9c2c049e041530a3349ab2e92c970654be2964c`；狀態為 complete；其中 Direct 穩定 identity 與 runtime dependency hash 符合本次檢查結果。 |
| `year=2026/manifest.json` | 5,925 bytes；原始 SHA `sha256:419a6d0fac4a8438cade440f3599db39110f09c3bac499848a61f34080e5bde4`，與 checkpoint 記錄的 `manifest_file_hash` 相同；year schema 為 `portfolio-ml-ooc-year.v3`；153,180 列；feature shape `[153180, 62]`、target shape `[153180, 6]`、label shape `[153180, 4, 9]`。 |

目前 Direct 的 `year=2026` 目錄內下列八個檔案均已逐一計算原始位元組 SHA；實際大小與 hash 均符合 year manifest。沒有把 array 值載入模型。

| 檔案 | 位元組數 | SHA-256 |
|---|---:|---|
| `features.values.i64` | 75,977,280 | `sha256:12ae93b93b1aa7437b91469b39af12ae9cfe40ba791b5d089cc57fb74e0faf72` |
| `features.masks.u8` | 9,497,160 | `sha256:4fe1a576df270b23fd1df5f7856fc8cb33fb6062705c1bf7352d40341eb02bd2` |
| `targets.i32` | 3,676,320 | `sha256:b285284a408d561833a06f186f419e9d73fbeadb7518f74a7f1191e49da26811` |
| `labels.i32` | 22,057,920 | `sha256:174aa10a67e3f860334e3127b0c34b903e891d65345a27734684877518723e14` |
| `labels.masks.u8` | 5,514,480 | `sha256:8be8fff0fe33d0302230f186359e6feff8959997374cc73381a8b5286c479e00` |
| `rows.sqlite` | 53,784,576 | `sha256:a7c3dc9fd2e16a6727c84e4b8333b05048e249682b7f4db9a95341e2fd62eb71` |
| `replay_source.sqlite` | 45,785,088 | `sha256:c8852c9234cdb0c968534ded1ac210d06a5bc2b1fcb076dddddcdc4d676abbc6` |
| `carry.state.gz` | 4,984,350 | `sha256:c8c5a813d86bc9cbb654c8f9774484b437cd4e5a5a8d18064e9a951c38f01d3f` |

OOC store 宣告 `portfolio-ml-ooc-store.v3`、年度 manifest `portfolio-ml-ooc-year.v3`、checkpoint `portfolio-ml-ooc-checkpoint.v1` 及 fold index `portfolio-ml-ooc-fold-index.v1`。持久化 dtype 為 values `<i8`、feature masks `u1`、targets `<i4`、labels `<i4`、row references `<i8`。Target 順序是 `target_weight_bp`、`delta_weight_bp`、`risk_contribution_bp`、`risky_budget_bp`、`cash_bp`、`rebalance_worthwhile`；label 順序是 `benchmark_excess_return_bp`、`sector_excess_return_bp`、`downside_observed`、`mae_bp`、`mfe_bp`、`realized_volatility_bp`、`max_drawdown_bp`、`tail_loss_bp`、`fill_feasible_observed`。外層 fold 的 row references 使用 `(year_ordinal, local_row_index)`。R006 測試固定檢查 dtype 常數與 target/label 欄位順序；合成 OOC 測試另覆蓋 fold refs 使用流程，詳見下方 ABI 對照表。

最新 OOC training pointer 指向 `allocation-ooc-868b7e805f5c03c65dc303e4`。其 manifest 為 6,318,420 bytes，原始 SHA `sha256:f814e5b56180983f6bbed7e2334f9f58a709288b5fea992276b29356c904ef04`，schema 為 `allocation-ooc-training.v5`，狀態 complete，包含 3,353,096 列、62 個 features、41 個 folds、40 個 meta folds，且 `formal_oos_allowed=false`、`production_alpha_bp=0`。此 OOC manifest 依記錄的 store manifest hash 參照 Direct run `direct-ooc-505c6adaf3f71a0c8f0a274e`；它與目前 Direct pointer 指向的 `direct-ooc-dca07415569065ee4e35266b` 是不同 run。R010/R026/R027 不應以目前最新 Direct run 取代 OOC manifest 原本記錄的來源。

## SafeShadow loader 與資產分類

`SafeShadowModelArtifactLoader` 是以 manifest 為依據的 joblib 讀取器。呼叫 deserializer 前，它先確認 artifact root 位於 DATA_ROOT 之外、要求並解析 `manifest.json`、驗證 manifest 與相容性合約、限制 artifact filename 留在指定 root 內，並核對 artifact hash。載入後再檢查 model/dataset/family identity 與 shadow-only flags。它不綁定 `_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS`；Direct checkpoint identity 是另一套機制。ML manifest 沒有宣告完整 Python estimator class path。

R006 測試會在 pytest 臨時目錄建立一個小型 `ControlledFixtureModel` joblib，依實際 20 欄 registry contract 寫入相符 manifest，再使用未注入替代 deserializer 的 `SafeShadowModelArtifactLoader`。這只驗證受控 `joblib.load` 能在 loader 完成檢查後成功。測得的 fixture class path 為 `test_refactor_ml_compatibility_baseline.ControlledFixtureModel`（以 pytest 執行時的 module import 名稱為準）；它只描述測試 fixture，不代表 repository 或正式模型。其他 R006 政策測試 仍以 注入的 lambda 驗證 manifest/hash/family 的拒絕分支，不作為實際 joblib 反序列化證據。

| 資產證據 | 分類 |
|---|---|
| R001 對預設 DATA_ROOT/output 的盤點快照 | 94,664 個檔名：11,559 個 manifest JSON 名稱、83,105 個 joblib/pkl/pickle 名稱。這是 R001 當時的快照，R006 沒有重新遞迴計數；R001 沒有反序列化未知檔案。 |
| `release_v4/direct_numeric_fixture` | R001 記錄 6 個 manifests、0 個 serialized files。 |
| `portfolio_ml_direct_numeric_production_v4` | R001 記錄 0 個 manifests、0 個 serialized files。 |
| `portfolio_ml_direct_numeric_production_v4_v2` | R001 記錄 630 個 manifests、0 個 serialized files。 |
| `portfolio_ml_direct_numeric_production_v4_v2-source-rebuild-79dccf8b7f0b` | R001 記錄 7 個 manifests、0 個 serialized files。 |
| `portfolio_ml_direct_ooc_training_production_v4_v5` | R001 記錄 10,501 個 manifests、83,100 個 serialized files。這些數量代表盤點時記錄的檔名，不表示 loader 接受這些檔案或已知其 class identity。 |
| 一個選取的 OOC `artifacts/b/fold-001/p-1f2fd7f5d830/h10-hgb/head-00.joblib` | 64,912 bytes；原始 SHA `sha256:2eb120d7a5da1e964fe1adb7d727ff897d18853e3f0af1020ae165dd028a6b89`。相鄰 JSON sidecar 為 6,011 bytes，原始 SHA `sha256:446c62a5d2b51305d3cb12ee465ccac798702820a1dafbbe4c12de9b8df1e22d`。檢查 sidecar keys 未見 class-path 欄位。未反序列化該 binary；class path 與 SafeShadow 相容性仍 unknown。 |
| `models/_EnsembleModel_model.pkl` | 3,030,277 bytes；原始 SHA `sha256:2bb8ffd4aee0048409e8e6ec7ddb6da8f836fcba9edcbee0b07ad1b2c285f9e5`。R001 未見 sidecar；未載入 binary；class path unknown。 |
| `models/2330_EnsembleModel_model.pkl` | 2,715,314 bytes；原始 SHA `sha256:064271e3948718300267a51bcb5d9d163d629aea4a3c5c671f30d66e4d971904`。R001 未見 sidecar；未載入 binary；class path unknown。 |

本表不宣稱 SafeShadow 曾拒絕、隔離或封存上述未知資產；R006 沒有對它們呼叫 loader。R001 metadata keys 與所選 OOC sidecar 都沒有提供 estimator class path。由於未反序列化任何未知 binary，其內部序列化 class reference、可載入性及執行期相容性仍未確認。沒有 sidecar 的 legacy 檔案維持 `unknown（內容與安全性尚未檢查）`，不能作為相容性證據。

## ABI 條款 → 測試／證據對照

下表用四種狀態分開標示證據強度。`source-declared` 表示只確認 source 中宣告的規格或程式路徑；`controlled-fixture verified` 表示只在測試自建的資料／artifact 上實際執行；`artifact-readback verified` 表示正式資產的 bytes/hash/manifest 交叉核對通過，並不表示解碼或執行了內容；`unknown` 表示目前證據不足。若同一條 ABI 的程式宣告與正式資產意義不同，狀態分開列，不提升較弱的一側。

| ABI 條款 | source 位置 | 對應測試或唯讀證據 | 狀態 | 範圍限制 |
|---|---|---|---|---|
| 歷史 20 個 feature 的 ID 順序、dtype、unit、missing/availability policy | `ml_module/feature_registry.py::CORE_LONG_HISTORY_FEATURE_REGISTRY`、`ml_module/historical_feature_builder.py::HistoricalFeatureBuilder.load_contract` | `tests/test_refactor_ml_compatibility_baseline.py::test_historical_feature_registry_preserves_canonical_20_feature_abi`；`tests/test_ml_historical_feature_builder.py::test_load_contract_freezes_registry_order_dtype_unit_and_schema_hash`、`test_missing_value_and_observed_zero_remain_distinct` | `controlled-fixture verified` | 測試 row 為合成輸入；只固定 schema/vector contract，不表示正式訓練流程讀取同一份資料。 |
| `_matrix` 的 `None → NaN`，以及已觀測的零保留為 `0.0` | `ml_module/historical_training_service.py::_matrix` | `tests/test_refactor_ml_compatibility_baseline.py::test_historical_training_matrix_keeps_missing_distinct_from_zero` 使用 20 欄合成 `HistoricalTrainingSample`。 | `controlled-fixture verified` | 驗證矩陣轉換；沒有比較任何 production model 預測。 |
| 歷史線性模型的中位數補值與標準化縮放 | `ml_module/historical_training_service.py::HistoricalTrainingService._fit_family`：`SimpleImputer(strategy="median", keep_empty_features=True)`、`StandardScaler()` | `tests/test_ml_historical_training_service.py::test_training_uses_fold_only_preprocessing_and_freezes_both_model_families`、`test_all_missing_training_column_keeps_frozen_feature_shape_without_warning` 對合成 fold 驗證 fit/test 隔離與全缺值欄位寬度。 | `source-declared` | 測試沒有逐一檢查已 fit imputer/scaler 的內部參數或 production preprocessing state；確切設定以 source 為準。 |
| Allocation `hist_gradient_boosting` 的 missing mask 欄位 | `ml_module/allocation_training_service.py::_pack_matrix`：HGB 矩陣將 value 欄與 mask 欄併排，並按 `feature.scale` 正規化已觀測值；`ml_module/allocation_out_of_core_training_service.py::_NumericStore.read_feature_batch` 將儲存 mask 解為 missing NaN。 | `tests/test_portfolio_ml_out_of_core_pipeline.py::test_hgb_fit_population_is_bounded_and_disclosed` 覆蓋 HGB OOC fit 路徑的受限樣本數量；source 程式碼是 mask 欄位形狀與填值規則的直接證據。 | `source-declared` | 該測試不逐欄比對 HGB mask bit pattern；本次沒有用正式矩陣執行 HGB。不能將此項視為 production mask data 已讀回。 |
| Allocation feature pack 順序與整數 scale 轉換 | `ml_module/allocation_training_service.py::_validate_feature_packs`、`_pack_matrix`；`data_module/portfolio_ml_out_of_core_store.py::_feature_packs`、`_feature_scales`；`ml_module/allocation_out_of_core_training_service.py::_NumericStore.feature_positions_for_pack`、`read_feature_batch` | `tests/test_allocation_ooc_release_builder.py::_rows_from_store` 依 manifest `feature_ids` 順序與 `feature_scales` 組成受控 row；`test_minimal_ooc_release_attaches_calibrator_and_matches_direct_consumer` 驗證合成 OOC release 流程。 | `controlled-fixture verified` | 此證據來自測試建立的受限 fixture，不是本次讀取的 62 欄正式 Direct 資料；正式資產只核對 manifest shape 與 bytes/hash。 |
| OOC 持久化 dtype、target/label order、feature mask 檔案 bytes | `data_module/portfolio_ml_out_of_core_store.py::{VALUE_DTYPE,MASK_DTYPE,TARGET_DTYPE,LABEL_DTYPE,ROW_REF_DTYPE,TARGET_FIELDS,LABEL_FIELDS}` | `tests/test_refactor_ml_compatibility_baseline.py::test_out_of_core_store_dtype_and_field_order_contract` 固定 source constants；Direct `year=2026/manifest.json` 與 8 個年度檔案的實際大小/raw SHA 逐項相符。 | `source-declared`；檔案 custodian 為 `artifact-readback verified` | R006 沒有將正式 memmap 以指定 dtype 開啟或檢查陣列值；artifact hash 一致只驗證 bytes custody，不驗證內容語意。 |
| OOC 持久化 row/fold tuple 編碼 `(year_ordinal, local_row_index)` | `data_module/portfolio_ml_out_of_core_store.py::_build_fold_indexes`、`ROW_REF_DTYPE`；`ml_module/allocation_out_of_core_training_service.py::_NumericStore.open_fold_refs` | source 以 `struct.pack("<qq", ordinal, int(local_row_index))` 寫出二個 int64；`tests/test_refactor_ml_compatibility_baseline.py::test_out_of_core_store_dtype_and_field_order_contract` 只斷言 dtype 常數，沒有逐值斷言已持久化 tuple。 | `source-declared` | 沒有讀回正式 fold-index binary，也沒有測試逐列 `(year_ordinal, local_row_index)` 編碼；此項只確認 source 宣告。 |
| 因果 fold 時序與合成 fold-reference 使用 | `ml_module/allocation_out_of_core_training_service.py::_NumericStore.open_fold_refs`；`data_module/portfolio_ml_out_of_core_store.py::_build_fold_indexes` | `tests/test_portfolio_ml_out_of_core_pipeline.py::test_base_oof_and_meta_use_only_prior_mature_folds` 在合成 OOC store 上檢查先前 fold 的來源、fold 成熟度與 OOF dtype；該測試證明 fold 時序，不逐欄斷言已持久化 tuple 編碼。 | `controlled-fixture verified` | 此狀態只涵蓋合成資料的因果 fold 時序／使用流程，不證明正式 row-ref binary 的 tuple 編碼或內容。 |
| Direct source identity、checkpoint/manifest provenance 與 resume gate | `data_module/portfolio_ml_direct_numeric_store.py::_stable_direct_computation_identity_payload`、`_load_checkpoint`、`inspect_direct_checkpoint_provenance` | `tests/test_ml_direct_checkpoint_provenance_recovery.py::test_stable_computation_identity_excludes_runtime_state`、`test_current_checkpoint_is_only_resume_candidate_after_full_readback`；`tests/test_ml_direct_computation_dependency_guard.py::test_resume_requires_matching_dependency_snapshot`；目前 Direct pointer/checkpoint/year manifest 的唯讀 hash 與 identity 欄位比對。 | 正式 metadata 為 `artifact-readback verified`；合成 resume 行為為 `controlled-fixture verified` | Direct 15-path raw bytes/hash 已逐檔核對；這不表示 R006 重新執行了正式 build/resume。 |
| Direct carry schema 與跨年度失效傳遞 | `data_module/portfolio_ml_direct_numeric_store.py::_read_year_carry`、`_year_carry_file_hash`、`_checkpointed_year_is_valid` | `tests/test_ml_direct_numeric_shared_reuse.py::test_carry_change_invalidates_later_year_shared_numeric_blocks`；目前 2026 `carry.state.gz` 原始 bytes/hash 與 checkpoint/manifest 記錄相符。 | 合成 carry 失效為 `controlled-fixture verified`；正式 carry 檔案 custody 為 `artifact-readback verified` | 正式 carry 壓縮內容沒有解壓或解碼；它代表的事件內容仍未檢視。 |
| SafeShadow manifest/hash/schema/library contract 與受控模型載入 | `ml_module/model_artifact_manifest.py::ModelArtifactLoadContract.validate`；`ml_module/model_artifact_loader.py::SafeShadowModelArtifactLoader.load` | `tests/test_ml_model_artifact_manifest.py::test_load_contract_rejects_registry_family_schema_and_library_mismatch`；`tests/test_ml_model_artifact_loader.py::test_validated_fixture_is_deserialized_only_after_contract_checks`；R006 `test_safe_loader_accepts_controlled_joblib_fixture_after_contract_checks` 使用預設 `joblib.load`。 | `controlled-fixture verified` | 只驗證測試建立的 joblib fixture 與其版本與 manifest；不表示選定的 OOC head 或 legacy model 符合此 contract。 |
| 正式/legacy estimator 的實際 library compatibility 與 Python class path | SafeShadow manifest 沒有 qualified estimator class field；選定的 OOC JSON sidecar 沒有 class-path keys；legacy pickle 沒有可核實 sidecar。 | 選定的 OOC head 與兩個沒有 sidecar 的 pickle 只讀取大小/hash/JSON keys；未知 serialized bytes 沒有載入。 | `unknown` | class path、pickle compatibility、實際會否被某個 loader 拒絕或隔離都未驗證；R006 不載入未知 artifact。 |

## 測試與交接

R006 focused tests 驗證受控 fixture 載入、政策拒絕分支、歷史 20 feature 順序/dtype/unit/missing contract、numeric matrix 的 缺值與零的轉換，以及 OOC 宣告的 dtype/欄位順序。較廣的 focused test 結果與既知 ML shadow boundary failure 記錄於 `REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md`。

R001 來源證據為 `docs/06_qa/REFACTOR_BASELINE_R001_20260922.md`。R001 的數量與狀態保留為當日盤點快照；R006 的 Direct hashes 與所選資產觀察是 2026-09-22 的新增唯讀結果。

## 原始 SOL review（完整）

# R006 SOL 審查

## 判定

`tests/test_refactor_ml_compatibility_baseline.py` 只有 4 個以 `DummyModel` 和注入的 `deserializer=lambda` 建立的 loader-policy 測試。它們可以證明這個受控 fixture 的 manifest／hash／family 拒絕分支，不能證明既有 historical 20 欄、Direct/OOC store、checkpoint、真實 joblib class path 或外部舊模型相容。`REFACTOR_ML_ABI_BASELINE_R006_20260922.md` 將多個未檢查項標為 `Verified Compatible`，超過實際證據；必須修正後才能供 R010/R026/R027 使用。

## 必須修正的項目

1. QA 報告 §1 列對了 `_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS` 的 15 個名稱，但沒有逐條 source byte SHA-256、存在性與 owner，也沒有 stable computation identity 和 runtime loaded-code integrity 的分帳。§1 說這 15 個路徑「由 `SafeShadowModelArtifactLoader` 嚴格綁定」不符合 source：該 loader 在 `ml_module/model_artifact_loader.py` 驗證 shadow model manifest/artifact；Direct path identity 在 `data_module/portfolio_ml_direct_numeric_store.py:122` 及 `:5362` 等實作。請更正責任、建立唯讀 hash/identity 清冊，不改 source list 或檔案 bytes。
2. `tests/test_refactor_ml_compatibility_baseline.py:17` 用虛構兩欄 `A/B float32` schema。它不是 `CORE_LONG_HISTORY_FEATURE_REGISTRY` 的 20 個有序欄位，也未驗 dtype/unit、`None→NaN`、imputer/scale、HGB mask、OOC `<i8`/`u1`/row-fold refs、Direct carry/checkpoint、source revisions。請從既有權威 contract 與 repository-controlled fixtures 建立 ABI→test mapping，必要時加小型 exact oracle；每項區分 source-declared、fixture-verified 與未驗證。
3. `:37` 的「legal load」透過注入 lambda 回傳 `DummyModel`，並沒有真正反序列化受控 joblib。這可保留為 loader gate 單元測試，但報告不得據此宣稱歷史模型或序列化 class path `Verified Compatible`。若能找到 repository-controlled safe fixture，依既有 safe loader 做 read-only 成功與拒絕驗證；未知 external pickle/joblib 絕不可載入。
4. QA 報告缺第二層實際安全可見 artifact/manifest inventory、artifact counts、producer/version/schema/shape/source refs/checkpoint/class path evidence、reader/writer authority、unknown/unsupported 理由及 raw bytes/hash readback。R001 只做 filename census（11,559 manifest、83,105 serialized filenames）且保留 unknown；R006 不能用四個新 fixture 代替既有資產清冊。
5. QA 報告 §3–4 把「未知 binary 均被拒絕與隔離」、「沒有 sidecar 的 production model 將被拒絕」、「未來可依清冊決定重新建立」當成既定結論。這次沒有載入或檢查所有外部資產，也沒有 quarantine action；請依證據改寫成 verified rejected by policy、unsupported/unknown、not inspected for safety，不授權重訓、rebuild、移檔、補 sidecar 或 promotion。
6. `R006_IMPLEMENTATION_REPORT.md` 須列起始／結束 HEAD/dirty baseline、兩層清冊對照、15-path bytes/identity、safe-loader 實際與注入測試差異、正式 artifact 未改的驗證範圍、R010/R026/R027 可用輸入與 unknown、所有 required `V-ML-SMALL`／`V-ML-DIRECT`／shadow focused suite 命令與結果、changed Python `py_compile` 及 `git diff --check`。目前 `UNRESOLVED RISKS: 無` 與「Verified Compatible」均缺乏證據。

## SOL 獨立驗證

SOL 以 `-p no:cacheprovider` 重跑 R006 新測試及九個要求的 historical snapshot/feature、model manifest/loader、Direct dependency/checkpoint/shared reuse、shadow boundary suites：`69 passed, 1 failed in 495.81s`。唯一失敗為 `tests/test_ml_shadow_dependency_boundary.py::test_repository_respects_ml_shadow_dependency_boundary`；guard 目前回報四條 production→ML import：

```text
app_module/personalization_projection.py -> ml_module.recommendation_inference_provenance.read_inference_projection_receipt
app_module/personalization_save_adapter.py -> ml_module.recommendation_inference_provenance.read_inference_projection_receipt
app_module/recommendation_calibration_consumer.py -> ml_module.recommendation_calibration_training.RECOMMENDATION_RETURN_BASIS
app_module/recommendation_calibration_consumer.py -> ml_module.recommendation_calibration_training.recommendation_label_contract_id
```

這四項在既有 shared-state 已列為原有 ML guard baseline；R006 沒有修改上述 production files。報告必須保留 exact failure、既有 owner 與限制，不得把 required suite 記為全通過，不得為了 R006 放行擴大 allowlist。

Changed Python `py_compile` 與 `git diff --check` 由 SOL 執行均 exit 0；後者只有 LF/CRLF normalization warnings。

允許範圍僅為 R006 專用測試、ML baseline QA 文件和 R006 實作報告；所有正式 artifact/manifest/checkpoint/pointer 唯讀，未知 binary 不反序列化。若需要 full rebuild、修改 Direct source bytes 或載入未知模型，立即停止並回報。

REVIEW_STATUS: CHANGES_REQUIRED

## SOL Luna 回修 findings（完整）

# R006 Luna 回修之 SOL 審查

## 判定

R006 已把先前過度宣稱改為分層證據，且 15/15 Direct source raw bytes/size/SHA-256 已由 SOL 對目前工作樹獨立核對一致；受控 joblib fixture、歷史 20 欄與 OOC dtype/field order 有新增測試。但 QA 文件仍缺原審查要求的逐項 owner 和 ABI→test 對照，且大段英文敘述及兩處英文程式註解違反 repository 的繁體中文規範。這些均可在 R006 原 scope 修正，不構成 architecture blocker。

## 必須修正的項目

1. `docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md` 的 Direct 15-path 表只有路徑、bytes、SHA；前次 SOL finding 要求每條 path 的 source owner／責任。請補明確 owner 欄或相鄰逐項表；再為 Direct、OOC、SafeShadow、legacy serialized asset 列出 reader／writer authority 與本次只讀範圍。不得把 source 所屬 module 簡稱為已驗證的正式 writer 權限。
2. 同文件缺可直接交 R010/R026/R027 的 `ABI 條款 → 測試／證據` mapping。請將 historical 20 欄、`None→NaN`、imputer/scale、HGB mask、allocation feature order/scale、OOC dtype／mask／row-fold refs、Direct carry/checkpoint/source identity、manifest/library/class path 分別列出來源位置、對應測試或唯讀資產證據、狀態 `source-declared`／`controlled-fixture verified`／`artifact-readback verified`／`unknown`。未獲本次驗證的項目保持 unknown 或 source-declared，不新增超出 scope 的 production 執行或未知模型載入。
3. QA 文件第 45、74、78、87、100、102、108、122、126 行等含完整英文敘述段落，測試檔第 192、235 行有英文註解。`AGENTS.md` 與 `docs/agents/shared_context.md` 要求文件和註解使用繁體中文。請將敘述與註解改為繁體中文，保留必需的英文字面 schema、欄位、hash 和 class path 原值，不改數值內容。
4. `R006_IMPLEMENTATION_REPORT.md` 同步更新本次修正的證據、狀態、精確驗證命令／結果與未決項。報告不得把 `73 passed, 1 failed` 寫成全綠；已知 shadow-boundary 四條 import 仍只記錄，不改 allowlist 或 production。
5. 第二輪讀回發現 QA 資產計數表把 R001 的 `portfolio_ml_direct_numeric_production_v4_v2-source-rebuild-79dccf8b7f0b` 縮成不精確的 `...-source-rebuild`；請用 R001 實際路徑更正，勿將 7 個 manifest 錯歸到不存在的根目錄。另將 OOC row/fold reference `(year_ordinal, local_row_index)` 的證據與 causal fold fixture 分開標示：現有 `test_base_oof_and_meta_use_only_prior_mature_folds` 證明 fold 時序，不直接逐欄斷言 persisted row-ref tuple。若另有精確 test 請引用其斷言，否則該 tuple 僅列 `source-declared`。

允許改動仍只限 R006 專用測試、ML ABI QA 文件與 R006 實作報告。SOL 初查 15-path 表全數 size/hash 相符；無須改 source bytes、正式 artifact、pointer、checkpoint 或外部模型。完成後重跑 R006 新測試、相關 affected focused tests、`py_compile`、格式／diff checks，回報結果。正式 10 檔長跑若 code/test assertions 未變，可引用上輪 `73 passed, 1 known failure`，明確標示未在本次文字修正後重跑；若有任何測試語意改動則重跑對應 affected suites。

REVIEW_STATUS: CHANGES_REQUIRED

## SOL 最終初審（完整）

# R006 Luna 回修之 SOL 初審完成

## 判定

R006 原有的相容性過度宣稱已改成可追溯的分層清冊。SOL 前兩輪 findings 均已在 R006 原範圍修正；目前可送 Gemini 獨立審查，但不是最終 PASS 或 Wave 1 release。唯一既知 shadow-boundary 測試失敗仍保留為既有 baseline，沒有被 allowlist 或 production 修改掩蓋。

## 實際檔案與證據

- 只變更 `tests/test_refactor_ml_compatibility_baseline.py`、`docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md`、`REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md`。凍結 SHA-256 依序為 `ee182953773ebbf3e8e4d77632454bba8ee45bd7f9f0124a4e2d2634e9372f0e`、`f3c609ecc79398c5863ec03c2015036ef5b83e41eed34b9b960130c8db90ffd2`、`be26a22c42e6133711d0ebabc869922d17d5848570f8c6155cc7c7eca97df4b7`。HEAD 保持 `391b057c`。
- SOL 對 QA 表 15 條 Direct source 逐檔獨立重算原始 bytes size 與 SHA-256，15/15 與目前工作樹相符。QA 同時列出 source owner、Direct stable identity 與 runtime snapshot 分帳、14/15 loaded-code 觀察限制及 reader/writer 程式責任；這些沒有被宣稱為正式 DATA_ROOT 寫入授權。
- Historical 20 欄順序/dtype/unit/missing、`None→NaN` 與零值區別有新增斷言；受控 joblib fixture 經預設 SafeShadow loader 實際載入。另有 source-declared／controlled-fixture／artifact-readback／unknown 的 ABI→test 對照，明示 imputer/scale、HGB mask、OOC persisted tuple 與正式 class path 的證據界線。
- R001 的 7-manifest source-rebuild 目錄在 QA 中使用完整 `portfolio_ml_direct_numeric_production_v4_v2-source-rebuild-79dccf8b7f0b` 名稱。OOC persisted `(year_ordinal, local_row_index)` 只列 `source-declared`；合成 causal fold 另列 `controlled-fixture verified`。未知 pickle/joblib 沒有反序列化，也沒有補 sidecar、移檔或寫正式 artifact。

## SOL 驗證與限制

SOL 在最終 Python 測試版本重跑 `.\.venv\Scripts\python.exe -m pytest tests/test_refactor_ml_compatibility_baseline.py -q -o addopts= -p no:cacheprovider`，結果 `8 passed in 0.21s`，exit 0；最終兩輪只有 QA／報告文字與測試註解變動，測試斷言語意未變。Luna 對 ABI 對照所指的 affected focused cases 執行 `21 passed, 1 warning in 137.69s`；更早的完整 10 檔 focused suite 真實結果為 `73 passed, 1 failed in 477.36s`，其中唯一 failure 是已知 `test_repository_respects_ml_shadow_dependency_boundary` 四條 production→ML import。不可把本次描述為完整 suite PASS。changed Python 的 `py_compile` 與 `git diff --check` exit 0；格式檢查通過。

## Gemini 獨立審查焦點

請驗收清冊是否足夠供 R010/R026/R027 使用且未把 source/manifest metadata 當模型相容證明；檢查 15-path identity、歷史 20 欄、OOC/Direct refs、safe loader／未知資產分帳、18 個所選資產 hash 保全、權限描述與四條既有 guard failure 的歸屬。對任何超出 R006 scope 的兼容缺口只要求具名記錄，不要求載入未知 binary 或修 production。

REVIEW_STATUS: AWAITING_GEMINI_REVIEW

Do not redesign the architecture.

Do not perform unrelated cleanup.

Do not silently fix unrelated bugs.

Do not begin another R-task.

If repository evidence contradicts this task specification in a way that prevents safe implementation, stop and report ARCHITECTURE_BLOCKER with evidence.
