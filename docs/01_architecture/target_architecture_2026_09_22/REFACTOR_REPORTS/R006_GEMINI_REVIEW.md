# Gemini 獨立審查報告：R006 Luna 回修

## 一、審查基本資訊與凍結 SHA 核對

- **審查任務**：`R006`（ML compatibility／artifact ABI 基線）
- **審查角色**：獨立 Gemini Reviewer
- **基線 HEAD**：`391b057c92037ec7a19cab2bf951d6029d29b020`
- **審查模式**：唯讀審查（Strictly Read-Only；未修改任何檔案、未反序列化未知二進位模型、未寫入正式資料目錄）

### 受審三檔凍結 SHA-256 驗證

依指示在審查前先獨立計算原始檔案位元組之 SHA-256：

| 檔案路徑 | SOL 凍結 SHA-256 | 目前磁碟實際 SHA-256 | 核對結果 |
|---|---|---|:---:|
| `tests/test_refactor_ml_compatibility_baseline.py` | `ee182953773ebbf3e8e4d77632454bba8ee45bd7f9f0124a4e2d2634e9372f0e` | `ee182953773ebbf3e8e4d77632454bba8ee45bd7f9f0124a4e2d2634e9372f0e` | **MATCH** |
| `docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md` | `f3c609ecc79398c5863ec03c2015036ef5b83e41eed34b9b960130c8db90ffd2` | `f3c609ecc79398c5863ec03c2015036ef5b83e41eed34b9b960130c8db90ffd2` | **MATCH** |
| `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md` | `be26a22c42e6133711d0ebabc869922d17d5848570f8c6155cc7c7eca97df4b7` | `be26a22c42e6133711d0ebabc869922d17d5848570f8c6155cc7c7eca97df4b7` | **MATCH** |

三檔 SHA-256 100% 精確吻合，無任何工作樹 drift，審查在穩定基線上進行。

---

## 二、詳細審查發現（Findings）

### 1. 檔案與變更範圍邊界（Scope Compliance）

- **核准範圍遵循**：本輪回修變更嚴格限制於上述核准之三個檔案。`git status` 與 diff 檢查確認無任何 production 原始碼變動、無正式資料庫寫入、亦無新增未授權之檔案。
- **語法與格式驗證**：
  - `python -m py_compile tests/test_refactor_ml_compatibility_baseline.py` 執行通過（exit 0）。
  - `git diff --check` 在三個受審檔案上完全無空白或換行錯誤（exit 0）。
  - QA 文件與測試註解已全數修正為繁體中文，保留必備之原文字面值（如 schema、欄位名稱、雜湊值及測試符號），符合 `AGENTS.md` 規範。

### 2. 15 條 Direct Dependency 路徑、計算身份與權限分帳

- **15 條路徑原始位元組與 SHA-256 核對**：
  獨立以 Python 讀取 `_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS` 列出之 15 個檔案，其大小與 raw bytes SHA-256 與 QA 清冊表記錄 15/15 完全一致。
- **計算身份與執行期快照分帳**：
  - `stable_direct_computation_identity_hash`: `sha256:1591edf147512bf07adad7311f1a3392bd8ddcdb09e60665746b9ef83032715c`
  - `runtime_dependency_snapshot_hash`: `sha256:0b23fbb44dc99c13f75c638aca1bc325f4585e714d018d2d8a223a15a20e7087`
  - 獨立重新計算所得數值與 QA 文件 §Direct 完全相符。報告已明確分帳：持久計算身份僅取決於排序路徑、source bytes 與 compiled fingerprint，排除執行期 module state 與動態常數。
- **程式宣告之 Reader/Writer 責任**：
  QA 清冊清楚列出各模組程式功能責任，並明確加註警示：「程式宣告之 reader/writer 僅為靜態程式碼路徑，不構成正式 DATA_ROOT 之作業授權或作業系統 Windows ACL 寫入許可」，邊界劃分客觀嚴謹。

### 3. Historical 20 欄 Feature Registry 與矩陣轉換 ABI

- **20 欄有序 Schema**：
  測試 `test_historical_feature_registry_preserves_canonical_20_feature_abi` 精確斷言了 `CORE_LONG_HISTORY_FEATURE_REGISTRY`（`core-long-history-features-v1`）之 20 個特徵名稱、順序、整數 dtype（`int`）、單位（`turnover_amount_minor` 為 `minor_currency_unit`，其餘 19 欄為 `bp`）、缺失政策（`missing_is_not_zero`）與可用性政策（`feature_as_of_before_decision`）。
- **矩陣邊界 None→NaN 與零值保留**：
  測試 `test_historical_training_matrix_keeps_missing_distinct_from_zero` 透過 `HistoricalTrainingSample` 與 `_matrix`，驗證了缺失值 `None` 轉換為 `np.nan`，而觀測值 `0` 嚴格保留為 `0.0`，有效防止誤補零所導致的數值失真。

### 4. OOC Binary Store 與 Direct 資產合約

- **OOC Store 常數與欄位順序**：
  測試 `test_out_of_core_store_dtype_and_field_order_contract` 斷言了：
  - `VALUE_DTYPE == <i8`
  - `MASK_DTYPE == u1`
  - `TARGET_DTYPE == <i4`
  - `LABEL_DTYPE == <i4`
  - `ROW_REF_DTYPE == <i8`
  - `TARGET_FIELDS`（6 欄）與 `LABEL_FIELDS`（9 欄）之精確名稱與順序。
- **Fold Index Tuple 與因果時序分帳**：
  QA 清冊與報告如實區分：OOC 持久化 `(year_ordinal, local_row_index)` tuple 列為 `source-declared`（因尚未讀回正式 binary 逐列核驗）；合成資料之因果 fold 時序則獨立列為 `controlled-fixture verified`（由 `test_base_oof_and_meta_use_only_prior_mature_folds` 覆蓋）。未發生證據過度延伸問題。

### 5. SafeShadow Loader 與未知模型資產分類

- **受控真實 Joblib Fixture 載入**：
  新增測試 `test_safe_loader_accepts_controlled_joblib_fixture_after_contract_checks` 採用 pytest 暫存目錄、真實 `ControlledFixtureModel` 及原生 `joblib.dump`，透過 `SafeShadowModelArtifactLoader` 預設的 `joblib.load` 反序列化成功。該測試證明受控 fixture 合約檢查與載入流程暢通，並明確於報告記錄其 class path 為測試專用，不冒充正式模型。
- **注入 Lambda 範圍收斂**：
  原注入 lambda 的測試（`test_safe_loader_rejects_missing_manifest`、`test_safe_loader_rejects_hash_mismatch`、`test_safe_loader_rejects_schema_mismatch`）嚴格限定為 loader 政策拒絕分支之單元驗證。
- **未知外部資產政策**：
  正式環境中無 sidecar 之舊 pickle（`_EnsembleModel_model.pkl`、`2330_EnsembleModel_model.pkl`）與選定之 OOC joblib 檔案，僅記錄原始大小、SHA-256 與 JSON keys，全數忠實歸類為 `unknown`，未嘗試載入、未嘗試反序列化、未擅自補寫 sidecar 或移入隔離區。

### 6. 四級 ABI 證據矩陣強度審查

QA 文件之 `ABI 條款 → 測試／證據對照` 表，對各項特性採用 `source-declared`、`controlled-fixture verified`、`artifact-readback verified`、`unknown` 四級標準標註：
- 歷史 20 欄 schema、矩陣 None→NaN 轉換：`controlled-fixture verified`
- 歷史線性模型 imputer/scale、Allocation HGB mask：`source-declared`
- OOC / Direct 磁碟檔案 custody 與 hash：`artifact-readback verified`
- 正式模型實際 class path 與相容性：`unknown`
- 未將 metadata 存在性冒充為已驗證相容，分級客觀嚴謹，完全符合提供給 R010/R026/R027 作為相容性基線之要求。

---

## 三、測試執行結果與判定

### 1. R006 新測試套件獨立執行

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_refactor_ml_compatibility_baseline.py -q -o addopts= -p no:cacheprovider
```
- **執行結果**：`8 passed in 0.19s`（Exit Code: 0）。

### 2. ABI 對照受影響 Focused 測試套件執行

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_refactor_ml_compatibility_baseline.py tests/test_ml_model_artifact_manifest.py::test_load_contract_rejects_registry_family_schema_and_library_mismatch tests/test_ml_model_artifact_loader.py::test_validated_fixture_is_deserialized_only_after_contract_checks tests/test_ml_historical_feature_builder.py::test_load_contract_freezes_registry_order_dtype_unit_and_schema_hash tests/test_ml_historical_feature_builder.py::test_missing_value_and_observed_zero_remain_distinct tests/test_ml_historical_training_service.py::test_training_uses_fold_only_preprocessing_and_freezes_both_model_families tests/test_ml_historical_training_service.py::test_all_missing_training_column_keeps_frozen_feature_shape_without_warning tests/test_ml_direct_checkpoint_provenance_recovery.py::test_stable_computation_identity_excludes_runtime_state tests/test_ml_direct_checkpoint_provenance_recovery.py::test_current_checkpoint_is_only_resume_candidate_after_full_readback tests/test_ml_direct_computation_dependency_guard.py::test_resume_requires_matching_dependency_snapshot tests/test_ml_direct_numeric_shared_reuse.py::test_carry_change_invalidates_later_year_shared_numeric_blocks tests/test_allocation_ooc_release_builder.py::test_minimal_ooc_release_attaches_calibrator_and_matches_direct_consumer tests/test_portfolio_ml_out_of_core_pipeline.py::test_base_oof_and_meta_use_only_prior_mature_folds tests/test_portfolio_ml_out_of_core_pipeline.py::test_hgb_fit_population_is_bounded_and_disclosed -q -o addopts= -p no:cacheprovider
```
- **執行結果**：`21 passed in 138.54s`（Exit Code: 0）。

### 3. ML Shadow Boundary 既知違規查驗

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ml_shadow_dependency_boundary.py -v -o addopts=
```
- **執行結果**：`1 failed, 10 passed in 3.17s`（Exit Code: 1）。
- **失敗明細確認**：
  - `production_imports_ml_module:app_module\personalization_projection.py:ml_module.recommendation_inference_provenance:read_inference_projection_receipt`
  - `production_imports_ml_module:app_module\personalization_save_adapter.py:ml_module.recommendation_inference_provenance:read_inference_projection_receipt`
  - `production_imports_ml_module:app_module\recommendation_calibration_consumer.py:ml_module.recommendation_calibration_training:RECOMMENDATION_RETURN_BASIS`
  - `production_imports_ml_module:app_module\recommendation_calibration_consumer.py:ml_module.recommendation_calibration_training:recommendation_label_contract_id`
- **判定**：此 4 條違規為專案既有之 ML guard baseline failure，非 R006 所引致。Luna 依架構不變條件（[INV-14](../FINAL_ARCHITECTURE_INVARIANTS.md#L20)）忠實記錄此失敗，未擅自擴大 allowlist 偽造全綠，亦未修改 production code。報告對長測結果之表述為 `73 passed, 1 failed`，完全符合事實。

---

## 四、審查結論

R006 經過 Luna Max 的兩輪回修，先前 SOL 指出的過度宣稱、責任模糊、虛構測試欄位、注入假模型及語言規範等缺點已全數獲得徹底修正：
1. 15 條 Direct 相依路徑之 SHA-256、責任歸屬及計算身份分帳精確可信。
2. 歷史 20 欄與 OOC 常數皆已建立嚴格之受控測試斷言。
3. 採用真實受控 Joblib fixture 驗證 loader 合約，未知模型維持未載入與 unknown 狀態，堅守安全防線（[INV-01](../FINAL_ARCHITECTURE_INVARIANTS.md#L7)、[INV-18](../FINAL_ARCHITECTURE_INVARIANTS.md#L24)）。
4. 四級 ABI 證據矩陣界線分明，完全達到供 R010/R026/R027 使用之交付標準。
5. 嚴格遵守檔案修改邊界，未動任何 production 檔案或正式資產。

本審查認定 R006 Luna 回修已完全符合任務驗收標準，判定為 PASS。

REVIEW_STATUS: PASS
