# C1 — R012 後的驗證計畫（已執行；SOL C1 工程 gate PASS）

本計畫依 `REFACTOR_VALIDATION_MATRIX.md` 的 C1 gate。R012 獨立審查及 Wave 5 checkpoint 通過後曾執行；Wave 6 readiness 後發現 sealed execution 的既有 consumer 欄位缺口，當時重開 C1 並撤回原放行；這是歷史狀態。修補後完整工程 QA 已重新執行，完整 readiness batch 為 115 passed、1 skipped（Windows `WinError 1314`）；完整命令、各 bundle 結果與 static checks 見 [C1_FULL_GATE_VALIDATION_REPORT.md](C1_FULL_GATE_VALIDATION_REPORT.md)。獨立 reviewer 結論為 `Accept C1 engineering gate for SOL decision`，SOL 最終裁決為 `C1 ENGINEERING GATE PASS`，Wave 6 為 `RELEASED FOR IMPLEMENTATION`；最終狀態見 [C1_CHECKPOINT.md](C1_CHECKPOINT.md)。該 QA 報告是 final QA 執行時的驗證快照，未納入其後獨立 reviewer/SOL 的最終 gate 判定；最終狀態以 checkpoint 為準。V-PERSIST 與 readiness 的 4 個 Windows symlink/reparse 負例仍未實證、不計為 pass。此裁決僅限工程驗證，不授權正式資料接受、ML promotion 或 production deployment。所有保存測試只用 `tmp_path`，不寫正式資料根目錄。

| Bundle | 測試範圍 |
|---|---|
| V-REC | `test_task_loop_03_contract.py`、`test_recommendation_run_support.py`、`test_recommendation_v1_7_negative_evidence.py`、`test_recommendation_exclusion_payload.py`、`test_recommendation_fundamental_filters.py`、`test_recommendation_ranking_service.py`、`test_recommendation_ranking_pipeline.py`、`test_recommendation_percentile_ranker.py`、`test_recommendation_market_data_provider.py`、`test_recommendation_market_frame.py`、`test_recommendation_refactor_characterization.py`。 |
| V-EXEC | `test_recommendation_contracts.py`、`test_recommendation_execution_state_characterization.py`、`test_recommendation_execution_coordinator.py`、`test_recommendation_execution_use_case.py`。 |
| V-CODEC | `test_recommendation_execution_codec.py`、`test_recommendation_dto_roundtrip.py`。 |
| V-PERSIST | `test_r004_recommendation_persistence_characterization.py`、`test_recommendation_save_coordinator.py`、R012 新增的 store/save/query 測試、`test_recommendation_capture_source_binding.py`、`test_recommendation_training_lineage.py` 的 receipt/readback 案例、`test_recommendation_service_calibration_integration.py` 的保存案例。 |
| focused V-ML-SMALL | `test_refactor_ml_compatibility_baseline.py`、`test_ml_historical_snapshot_provider.py`、`test_ml_historical_feature_computation.py`、`test_ml_model_artifact_manifest.py`、`test_ml_model_artifact_loader.py`、`test_recommendation_calibration_source_contract.py`、`test_recommendation_calibration_contract_guards.py`、`test_recommendation_training_lineage.py`、`test_ml_shadow_projection_boundary.py` 及上述 calibration integration。 |

實際執行時記錄每個 bundle 的完整命令、通過／失敗數、耗時與失敗 stack；去重的測試檔可以同批執行，但不得因先前 focused run 已通過而跳過 checkpoint。跑 changed-file `py_compile`、相關 scoped mypy、`git diff --check`，並核對 import DAG、TMP 退休 owner、legacy readback、新 writer 不調用 legacy replace、artifact/hash/metadata/index 恢復、無 service `last_*` 反向讀取。

既有 `tests/test_recommendation_service_calibration_integration.py` 六個 fixture 失敗在 `tests/natural_session_source_fixture.py:130`，原 `evaluation_day="2026-06-22"` 早於 exact-20 endpoint；R011 驗收已記錄為原測試基線。C1 先確認仍是同六項，再以具名 C1 測試資料修復調整合成日期，不改 shared maturity guard 或 production。實際 diff、獨立複審與整檔 12 passed 分別見 [修復報告](C1_ML_FIXTURE_REPAIR_REPORT.md)、[獨立複審](C1_ML_FIXTURE_INDEPENDENT_REVIEW.md)及 [C1 checkpoint](C1_CHECKPOINT.md)。

正式資料重建、完整 ML fit、scheduler 實跑及 model promotion 不屬此 gate 的自動操作。獨立確認 R012 新格式未寫非暫存根目錄，且任何失敗不改原始／歷史 artifact bytes、ID、hash。
