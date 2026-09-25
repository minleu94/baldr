# C1 — R012 後 contract／execution／persistence 硬閘門

CHECKPOINT_STATUS: C1_ENGINEERING_GATE_PASS
WAVE6_STATUS: RELEASED_FOR_IMPLEMENTATION
INDEPENDENT_REVIEW: `Accept C1 engineering gate for SOL decision`
SOL_DECISION: `C1 ENGINEERING GATE PASS`

> **歷史紀錄（2026-09-23 C1 重開時；已由下方 final decision 取代）**：Wave 6 readiness 當時查出 canonical execution 尚未封存既有 consumer 必需的價格、分項分數、完整理由／設定，以及 legacy/new 統一讀取 seam。原測試與靜態檢查未覆蓋該契約完整性條件，因此當時撤回 PASS 並阻止 Wave 6，要求先修上游契約再重跑 C1。細節見 [C1 契約缺口](C1_CONTRACT_COMPLETENESS_FINDING.md)；修補後結果與後續裁決見本 checkpoint 及 [修補後 full-gate QA 報告](C1_FULL_GATE_VALIDATION_REPORT.md)。

本次依 `REFACTOR_VALIDATION_MATRIX.md` §3，在 Wave 5 的 R012 與獨立審查均 PASS 後執行。C1 的既有 calibration fixture 日期矛盾先以具名測試資料修復解除，未調整 production 或 maturity guard；[修復報告](C1_ML_FIXTURE_REPAIR_REPORT.md)與[獨立複審](C1_ML_FIXTURE_INDEPENDENT_REVIEW.md)分帳。所有測試只在 pytest 暫存根建立資料，未讀寫正式資料根、未執行完整 ML rebuild、scheduler 實跑或 model promotion。

## 最終 C1 工程 gate 裁決（2026-09-23）

獨立 reviewer 結論為 `Accept C1 engineering gate for SOL decision`；SOL 最終裁決為 `C1 ENGINEERING GATE PASS`，並將 Wave 6 狀態定為 `RELEASED FOR IMPLEMENTATION`。此 PASS 僅限本輪 scoped engineering validation，不代表正式資料接受、ML promotion 或 production deployment 已核准。

| Bundle | 修補後結果 |
|---|---|
| V-REC | 69 passed，0 skipped |
| V-EXEC | 112 passed，0 skipped |
| V-CODEC | 29 passed，0 skipped |
| V-PERSIST | 99 passed，3 skipped |
| focused V-ML-SMALL | 118 passed，0 skipped；僅 synthetic／歷史小型 fixture coverage |
| 完整 C1 readiness | 115 passed，1 skipped |
| R017 readiness + R005 replay | 22 passed（9 R017 + 13 R005；獨立列示的 focused batch） |

V-PERSIST 的 3 個及 readiness 的 1 個 symlink/reparse 負例因 Windows `WinError 1314` 無法建立測試連結，合計 4 個未實證案例，均未計為通過。其餘工程證據：44 個 changed/untracked Python files `py_compile` 成功；15 個 C1 production sources scoped mypy 無 issue；`git diff --check` exit 0；C1 import DAG／owner scan 完成；fixture manifest hashes 與 bytes readback 核對完成。完整命令、fixture SHA-256 及靜態證據見 [C1_FULL_GATE_VALIDATION_REPORT.md](C1_FULL_GATE_VALIDATION_REPORT.md)，尤見其 pytest 結果、fixture manifest、py_compile、mypy、diff check 與 import DAG 各節。該 QA 報告是 final QA 執行時的驗證快照，未納入其後獨立 reviewer/SOL 的最終 gate 判定；報告列示的測試數、skip、fixture/static evidence 仍是執行證據。

真 scheduled wrapper parity（R014）、production replay bridge（R017）與 TMP-REC-04 退場（R020）仍是後續工作，未列作已完成；依 [Wave 6 owner 與範圍](WAVE6_SCOPE_AND_OWNERSHIP.md) 及既有 task dependencies 推進。這次 Wave 6 implementation release 不授權讀寫正式資料、全市場 ML rebuild、模型訓練／推論或 promotion、production deployment。

## 重開前原必跑 bundle 結果（歷史記錄；以修補後 full-gate 報告為本輪結果）

| Bundle | 固定執行範圍與結果 |
|---|---|
| `V-REC`、`V-EXEC`、`V-CODEC`、`V-PERSIST` | 下列 22 檔單次完整批次：**213 passed、3 skipped、2 warnings**，exit 0，14.86 秒。包含 R004/R012、capture source binding 與 personalization save integration。 |
| focused `V-ML-SMALL` | 下列 10 檔單次完整批次：**93 passed**，exit 0，14.73 秒；其中 calibration integration 全 12 項通過。 |
| natural fixture 相關回歸 | `test_daily_recommendation_learning_loop.py`、`test_daily_banktaiwan_learning_cost.py`、`test_recommendation_natural_outcomes_cli.py`、`test_recommendation_learning_evidence_projection.py`：**76 passed**，exit 0，85.87 秒。共享 fixture 本身未改。 |
| R012 skip 查明 | `test_r012_recommendation_artifact_persistence.py -q -rs`：**44 passed、3 skipped**。三項均為此 Windows host 無暫存 symlink 建立權限，`WinError 1314`；未將 skip 計為通過，R012 對 reparse/symlink 的正向動態驗證仍有環境限制。 |

核心批次使用 `python -B -m pytest <以下 22 檔> -q -o addopts= -p no:cacheprovider`：

```text
test_task_loop_03_contract.py
test_recommendation_run_support.py
test_recommendation_v1_7_negative_evidence.py
test_recommendation_exclusion_payload.py
test_recommendation_fundamental_filters.py
test_recommendation_ranking_service.py
test_recommendation_ranking_pipeline.py
test_recommendation_percentile_ranker.py
test_recommendation_market_data_provider.py
test_recommendation_market_frame.py
test_recommendation_refactor_characterization.py
test_recommendation_contracts.py
test_recommendation_execution_state_characterization.py
test_recommendation_execution_coordinator.py
test_recommendation_execution_use_case.py
test_recommendation_execution_codec.py
test_recommendation_dto_roundtrip.py
test_r004_recommendation_persistence_characterization.py
test_recommendation_save_coordinator.py
test_r012_recommendation_artifact_persistence.py
test_recommendation_capture_source_binding.py
test_personalization_save_integration.py
```

所有名稱以 `tests/` 為根。focused ML 批次用相同 pytest 參數、以下 10 檔：

```text
test_refactor_ml_compatibility_baseline.py
test_ml_historical_snapshot_provider.py
test_ml_historical_feature_computation.py
test_ml_model_artifact_manifest.py
test_ml_model_artifact_loader.py
test_recommendation_calibration_source_contract.py
test_recommendation_calibration_contract_guards.py
test_recommendation_training_lineage.py
test_ml_shadow_projection_boundary.py
test_recommendation_service_calibration_integration.py
```

原 calibration integration 有 6 個測試在 `tests/natural_session_source_fixture.py:130` 進入服務前失敗，因原評估日 2026-06-22 早於最晚 exact-20 endpoint 2026-07-24。C1 具名修復只調整六個整合測試的合成評估／採納／時鐘／來源與前瞻事件日期：候選與訓練資料不變，2026-07-27 評估已成熟；台北跨日、T-1、20-session label、receipt identity 與所有 fail-closed 斷言保持。獨立 Luna 複審為 PASS；SOL 核對實際 diff 並重跑全 93 項 focused ML，沒有把原紅燈當成綠燈。

## 架構與相容性核對

- `data_module/result_artifact_store.py` 沒有 app import；新保存路徑維持 app save／port／persistence → data store 的單向依賴。獨立 Luna 靜態審查未發現新增 reverse edge、結果 owner 混淆或 central-file ownership 漂移。
- 新 artifact create-only、同 ID/hash 冪等、異 hash 拒絕、索引重建、metadata rename 與 legacy bytes/readback 由 R012 測項覆蓋。舊 JSON decoder/read path 保留為永久歷史相容，不作新 writer fallback。
- `TMP-REC-03` 仍是尚未切換的舊保存 caller adapter，刪除 owner 為 R015；`TMP-REC-04` 由 R017 建立、R020 刪除；其餘既有 TMP 按 `FINAL_MIGRATION_SEQUENCE.md` 列管。C1 沒有提前清理或增設無 owner adapter。
- `INV-05/06/07–13/15/17` 未發現新 drift：決策日可得性、原數值／排序、完整 execution、canonical codec、新舊 artifact 讀取、ML ordered ABI 與歷史來源均依前述測試／靜態審查保持。完整 domain／UI／replay cutover 是後續 wave 的工作，不在 C1 宣稱已完成。

靜態檢查：`git diff --check` exit 0；R012 七個變更 Python 檔與 calibration integration 測試 `py_compile` exit 0；五個新 R012 模組的 `mypy --follow-imports=skip` 無 issue。兩個 pandas `FutureWarning` 出自 `decision_module/scoring_engine.py:437` 的既有 dtype 寫入。Windows symlink/reparse 與斷電耐久的未驗證範圍延續 R012 驗收限制，不宣稱已在此 host 實證。

## 原放行撤回與 C1 重開原因（歷史紀錄；後續已修復並重新裁決）

R001–R012 與 Wave 0–5 的原 task 測試與驗收仍留存；首次 C1 bundle 雖 exit 0、具名基線 fixture 也已修復，Wave 6 consumer readiness 後仍發現 sealed execution 缺少既有業務讀取所需資料，故當時撤回原 Wave 6 放行並要求修復、重跑 C1。此段只記錄重開時的歷史狀態；上游修復、final QA、獨立 reviewer 接受與 SOL 最終 PASS 已完成，當前狀態以上方「最終 C1 工程 gate 裁決」為準。此 engineering gate 不授權 formal／promotion／production。
