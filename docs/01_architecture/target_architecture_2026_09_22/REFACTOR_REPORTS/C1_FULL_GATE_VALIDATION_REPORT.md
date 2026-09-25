# C1 Full Gate Validation Report（修補後 final QA）

執行日期：2026-09-23  
QA owner：獨立 Luna Max  
範圍：C1 U1–U5／SCHEMA／AB 修補後唯讀驗證；本報告取代本文件先前的修補前數字。

## 狀態與結論

**C1：NOT PASSED。Wave 6：BLOCKED。**

本輪指定的工程測試、scoped mypy、changed-Python py_compile、fixture hash/readback 與 C1 import DAG 檢查均有新結果，未沿用修補前數字。ML-P/N 現有驗證範圍只涵蓋小型 synthetic ABI／receipt fixtures。R17-N 修補後，正例與負例共用 exact pinned synthetic oracle；六種 mutation 負例要求 oracle 明確拒絕。獨立 reviewer 接受的範圍僅為「R17-N synthetic readiness」，並回報該範圍無剩餘 P1/P2；此接受不涵蓋 production replay bridge，也不代表完整 C1 review 或 SOL 最終 gate 已通過。完整 C1 獨立 review 與 SOL 最終 gate 尚待裁決，故本報告不宣稱 C1 PASS、Wave 6 放行或正式資料／模型 readiness。

沒有執行 UI、scheduler、scheduled wrapper main、正式資料更新、全市場 ML rebuild、模型訓練／推論或 promotion。沒有 stage／commit。QA 僅更新本報告；其餘共用工作樹變更由各 owner 維護。

## 隔離方式

每個 pytest bundle 使用不同 TEMP 根目錄設定 DATA_ROOT 與 OUTPUT_ROOT，並設 PROFILE=test。pytest 使用 Python -B、-p no:cacheprovider；py_compile 的 bytecode cache 導向 TEMP。C1 readiness 與 ML-P/N 僅使用合成 fixtures、pytest tmp_path 及隔離 artifact store。沒有測試指向正式資料根目錄。

## Pytest 結果與完整命令

所有 bundle 均以 -q -rs -o addopts= -p no:cacheprovider 執行；未列出的套件沒有 failure stack。

### V-REC

結果：69 passed，0 failed，0 skipped；2 個既有 pandas FutureWarning；4.01 秒。

    $env:DATA_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_vrec_data'; $env:OUTPUT_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_vrec_output'; $env:PROFILE='test'; & .\.venv\Scripts\python.exe -B -m pytest tests\test_task_loop_03_contract.py tests\test_recommendation_run_support.py tests\test_recommendation_v1_7_negative_evidence.py tests\test_recommendation_exclusion_payload.py tests\test_recommendation_fundamental_filters.py tests\test_recommendation_ranking_service.py tests\test_recommendation_ranking_pipeline.py tests\test_recommendation_percentile_ranker.py tests\test_recommendation_market_data_provider.py tests\test_recommendation_market_frame.py tests\test_recommendation_refactor_characterization.py -q -rs -o addopts= -p no:cacheprovider

兩個 warning 都來自 decision_module/scoring_engine.py:437 的 pandas incompatible-dtype assignment FutureWarning；未造成測試失敗。

### V-EXEC

結果：112 passed，0 failed，0 skipped；8.20 秒。包含 U1 contract、invocation capture 及 A/B interleave readiness。

    $env:DATA_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_vexec_data'; $env:OUTPUT_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_vexec_output'; $env:PROFILE='test'; & .\.venv\Scripts\python.exe -B -m pytest tests\test_recommendation_contracts.py tests\test_recommendation_execution_state_characterization.py tests\test_recommendation_execution_coordinator.py tests\test_recommendation_execution_use_case.py tests\test_recommendation_capture_source_binding.py tests\test_c1_invocation_capture.py tests\test_c1_execution_artifact_ab_interleave.py -q -rs -o addopts= -p no:cacheprovider

### V-CODEC

結果：29 passed，0 failed，0 skipped；1.03 秒。包含 SCHEMA-P/N compatibility suite。

    $env:DATA_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_vcodec_data'; $env:OUTPUT_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_vcodec_output'; $env:PROFILE='test'; & .\.venv\Scripts\python.exe -B -m pytest tests\test_recommendation_execution_codec.py tests\test_recommendation_dto_roundtrip.py tests\test_c1_schema_compatibility.py -q -rs -o addopts= -p no:cacheprovider

### V-PERSIST

結果：99 passed，0 failed，3 skipped；23.99 秒。

    $env:DATA_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_vpersist_data'; $env:OUTPUT_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_vpersist_output'; $env:PROFILE='test'; & .\.venv\Scripts\python.exe -B -m pytest tests\test_r004_recommendation_persistence_characterization.py tests\test_recommendation_save_coordinator.py tests\test_r012_recommendation_artifact_persistence.py tests\test_recommendation_capture_source_binding.py tests\test_personalization_save_integration.py tests\test_recommendation_training_lineage.py tests\test_recommendation_service_calibration_integration.py -q -rs -o addopts= -p no:cacheprovider

三項 skip 均因 Windows 測試 host 無權建立暫存 symlink/reparse point（WinError 1314），不計入通過：

- test_r012_root_and_file_symlinks_fail_closed：無法建立暫存目錄 symlink。
- test_r012_symlinked_artifact_is_not_followed：無法建立暫存檔案 symlink。
- test_r012_windows_artifact_reparse_is_rejected_by_open_handle：無法建立測試連結。

### focused V-ML-SMALL（含 ML-P/N）

結果：118 passed，0 failed，0 skipped；17.18 秒。只代表合成／歷史小型 fixture coverage，不代表 full-market rebuild、live inference 或 model promotion。

    $env:DATA_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_vml_repaired_data'; $env:OUTPUT_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_vml_repaired_output'; $env:PROFILE='test'; & .\.venv\Scripts\python.exe -B -m pytest tests\test_refactor_ml_compatibility_baseline.py tests\test_ml_historical_snapshot_provider.py tests\test_ml_historical_feature_computation.py tests\test_ml_model_artifact_manifest.py tests\test_ml_model_artifact_loader.py tests\test_recommendation_calibration_source_contract.py tests\test_recommendation_calibration_contract_guards.py tests\test_recommendation_training_lineage.py tests\test_ml_shadow_projection_boundary.py tests\test_recommendation_service_calibration_integration.py tests\test_c1_ml_abi_receipt_readiness.py -q -rs -o addopts= -p no:cacheprovider

### R017 readiness 與 R005 replay oracle

R17-N 修補後結果：22 passed，0 failed，0 skipped；1.08 秒。包含 R017 option-2 外層 annotation passthrough／typed-child 邊界，以及完整 R005 replay characterization。矩陣列出的三個 replay oracle 均在完整 R005 檔案中執行：test_replay_wrapper_preserves_provider_annotation_payload、test_portfolio_replay_pins_outer_snapshot_dates_and_factor_manifest、test_replay_full_snapshot_is_exact_and_future_append_does_not_change_it。

    $env:DATA_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_r017_r005_data'; $env:OUTPUT_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_r017_r005_output'; $env:PROFILE='test'; & .\.venv\Scripts\python.exe -B -m pytest tests\test_c1_replay_bridge_readiness.py tests\test_recommendation_replay_characterization.py -q -rs -o addopts= -p no:cacheprovider

R017 readiness 從 fixture_manifest.json 驗證 fixture ID、UTF-8 raw bytes 長度與 SHA-256，並比較讀取前後 bytes。manifest 將來源值明確標為 test-fixture injection；production annotation source 與 parent result ID 保持 unknown。正例對 typed child 欄位逐項比對 pinned fixture oracle；六種負例 mutation（stock code、候選順序、stock name、rule score、indicator score、reason text）共用該 oracle，並各要求 AssertionError。clock/reference 有正例 exact compare，但沒有 clock/reference 負例 mutation；不擴大宣稱其負例覆蓋。獨立 reviewer 接受 R17-N synthetic readiness only，未審定 production bridge 或整體 C1。

### 完整 C1 readiness（R014/R016/R017、SCHEMA、AB、ML-P/N、R005）

R17-N exact-oracle 修補後結果：115 passed，0 failed，1 skipped；5.80 秒。包含 ML-P/N、AB fingerprint、SCHEMA、R014/R016 consumer readiness、R017 option-2 及 R005 oracle。此為目前完整 C1 readiness batch 結果；不等同獨立 C1 review 或 SOL gate 核准。

    $env:DATA_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_readiness_repaired_data'; $env:OUTPUT_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_readiness_repaired_output'; $env:PROFILE='test'; & .\.venv\Scripts\python.exe -B -m pytest tests\test_c1_forward_consumer_readiness.py tests\test_c1_legacy_query_readiness.py tests\test_c1_replay_bridge_readiness.py tests\test_c1_schema_compatibility.py tests\test_c1_execution_artifact_ab_interleave.py tests\test_c1_invocation_capture.py tests\test_c1_ml_abi_receipt_readiness.py tests\test_recommendation_replay_characterization.py -q -rs -o addopts= -p no:cacheprovider

唯一 skip：test_c1_legacy_reader_rejects_symlinked_result_file，Windows host 建立暫存 symlink 回傳 WinError 1314。此項不計為通過。沒有其他 failure 或 skip。

### Import-contract 補充測試

結果：35 passed，0 failed，0 skipped；0.82 秒。

    $env:DATA_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_import_data'; $env:OUTPUT_ROOT=Join-Path $env:TEMP 'technical_analysis_c1_final_import_output'; $env:PROFILE='test'; & .\.venv\Scripts\python.exe -B -m pytest tests\test_data_market_contracts.py tests\test_prepared_ml_input_contract.py -q -rs -o addopts= -p no:cacheprovider

## Fixture manifest、hash 與 bytes readback

pytest 前後重算下列 manifest entries；所有 entry 的 byte_length 與 SHA-256 均吻合 manifest。各測試亦檢查其隔離 artifact/read view 的 bytes、hash、identity 或 R017 fixture readback；不把沒有可信歷史 digest 的 legacy raw file 解讀為歷史防竄改證據。

| Fixture 或 manifest | Bytes | SHA-256 |
|---|---:|---|
| c1_consumer_readiness/fixture_manifest.json | 1,456 | 91a1d4def60b5b612bd834dcb64bbde669700d4a3874e9ad457b6b70df638892 |
| c1_consumer_readiness/r014_fixture_manifest.json | 1,181 | 96ef4df92d1232de00fe85844e2a32ed1a97a82a08986ac1291b3341097b4f40 |
| c1_consumer_readiness/r014_saved_execution.json | 11,700 | ebe481f425be3efa1c3635a71df5ba7c3e1b4054662b53fb980426fe79c11099 |
| c1_consumer_readiness/r016_execution_rev1.json | 5,033 | dbd3c2194ef53c2fee3e41e772187d2453c52237328aa179833282e0cc76a52b |
| c1_consumer_readiness/r016_execution_rev2.json | 4,302 | 0ef36ebabc8277ed5cf27a764dc359164cb3e27a6bc8d41111b4426f7e04e2f2 |
| c1_consumer_readiness/r016_legacy_run_zh.json | 469 | f625d43792688b35beb78ea1e93e965e79858ee94293c786351d6511f9de5552 |
| c1_consumer_readiness/ml_abi_manifest.json | 2,230 | c143b1c545319d2e3092e5d4a23ee45d86919be0093c8b889a5866a1e86b1f05 |
| c1_cross_boundary/fixture_manifest.json | 1,035 | 2d01afed6389142863725d4594d16c48eafc89059aac8a92ea09c740cd157bf1 |
| c1_cross_boundary/schema_rev1.json | 5,033 | dbd3c2194ef53c2fee3e41e772187d2453c52237328aa179833282e0cc76a52b |
| c1_cross_boundary/ab_interleave_scenarios.json | 1,480 | 5112d36aafb67e323bb14759e7cfbda6b5d448cc8a008fd764d2ae63a7d500e3 |
| c1_replay_bridge/fixture_manifest.json | 1,524 | 836f67e51e770d160cfd60efda16bbacee160db4ea0def523ce15bf29150ee0a |
| c1_replay_bridge/r017_stored_annotation_snapshot.json | 2,563 | bea89c9d6e11e024a9a8481550e7161d1dc068b2e44a8db9038a130319215e3d |

manifest 中列出的 R014、R016、SCHEMA、AB、R017 fixtures 均在 pytest 前後維持相同長度與 SHA。ML manifest 的固定 digest/長度及讀取前後 byte equality 由 test_c1_ml_abi_receipt_readiness.py 驗證。R017 的 hash 是合成 fixture pin，不是 production artifact 的 trust authority。

## Static、import DAG 與 owner 檢查

### Changed-Python py_compile

結果：44 個 modified/untracked Python files 編譯成功，exit 0；PYTHONPYCACHEPREFIX 指向 TEMP。清冊由下列 PowerShell 收集，涵蓋 tracked diff 與 untracked source/test files：

    $paths=@(git diff --name-only --diff-filter=ACMRT; git ls-files --others --exclude-standard) | Sort-Object -Unique; $py=@($paths | Where-Object { $_ -match '\.py$' -and (Test-Path -LiteralPath $_) }); $env:PYTHONPYCACHEPREFIX=Join-Path $env:TEMP 'technical_analysis_c1_final_pyc_post_r17n'; Write-Output "changed_python_count=$($py.Count)"; & .\.venv\Scripts\python.exe -B -m py_compile $py

### Scoped mypy

結果：15 個 C1 production sources，Success: no issues found in 15 source files，exit 0。

    $env:PYTHONPYCACHEPREFIX=Join-Path $env:TEMP 'technical_analysis_c1_final_mypy_pyc_post_r17n'; & .\.venv\Scripts\python.exe -B -m mypy --follow-imports=skip --cache-dir (Join-Path $env:TEMP 'technical_analysis_c1_final_mypy_cache_post_r17n') app_module\recommendation\__init__.py app_module\recommendation\contracts.py app_module\recommendation\codec.py app_module\recommendation\execute.py app_module\recommendation\ml_adapter.py app_module\recommendation\persistence.py app_module\recommendation\ports.py app_module\recommendation\queries.py app_module\recommendation\save.py app_module\recommendation_service.py app_module\forward_position_thesis_candidate_producer.py data_module\contracts\market.py data_module\result_artifact_store.py decision_module\recommendation\contracts.py ml_module\prepared_input_contract.py

U1 原兩項型別錯誤已不再出現；AB scenario fingerprint 以 manifest 與測試 pinned hash 一致。

### git diff --check

結果：exit 0，無 whitespace error。Git 只列出工作樹 LF 之後可能轉為 CRLF 的提示，沒有 whitespace 診斷。

    git diff --check

### V-SOURCE：source scan、import DAG 與方向

對 app_module、data_module、decision_module、ml_module 全部 620 個 Python files 以 AST 檢查 import/from-import edges，0 syntax parse errors。另對程式、UI、scripts、fixtures 與 C1 架構文件搜尋 direct、dynamic import、qualified string/serialized path 及 legacy caller references。相關 rg 查詢：

    rg -n "app_module\.recommendation|data_module\.result_artifact_store|data_module\.contracts\.market|decision_module\.recommendation\.contracts|ml_module\.prepared_input_contract" app_module data_module decision_module ml_module ui_qt scripts -g "*.py" -g "!**/graphify-out/**"

    rg -n "import_module|__import__|importlib\.util|app_module\.recommendation|data_module\.result_artifact_store|decision_module\.recommendation|ml_module\.prepared_input_contract" app_module data_module decision_module ml_module ui_qt scripts tests/fixtures docs/01_architecture/target_architecture_2026_09_22 -g "*.py" -g "*.json" -g "*.md" -g "!**/graphify-out/**"

    rg -n "last_[A-Za-z0-9_]+|RecommendationRepository|save_result\(" app_module/recommendation data_module/result_artifact_store.py app_module/forward_position_thesis_candidate_producer.py

C1 新 owner import 方向核對結果：

- app_module/recommendation contracts、codec、execute、persistence、queries、save、ports 維持 app 層；其跨層依賴指向 data、decision 或 ML contracts/store。
- decision_module/recommendation/contracts.py 只依賴 data_module/contracts/market.py 的 SourceRef／availability leaf。
- data_module/contracts 與 data_module/result_artifact_store 沒有反向 import app_module、decision_module 或 ml_module。
- ml_module/prepared_input_contract.py 沒有 app_module／decision_module import。
- C1 runtime/direct caller 是 app 層內部、forward producer、legacy DTO codec delegation 與新 readiness tests；沒有新增 UI、scheduled script 或其他 consumer cutover。
- 唯一 canonical execution codec 在 app_module/recommendation/codec.py；query seam 負責 legacy/rev1/rev2 read view。app_module/dtos/__init__.py 的舊 DTO decode delegate 到此 codec，未新增第二個 execution writer。
- execute.py 的 last_* 取值限於同次 invocation-private legacy capture；A/B interleave 與 invocation capture tests 通過。scheduled wrapper 仍有舊 RecommendationResultDTO mapping/last_excluded_candidates_json read（scripts/scheduled/run_scheduled_recommendation_snapshot.py:746-754），該 wrapper 未修改或執行；真 scheduled parity 仍由 C1 後 R014 gate 驗證。
- TMP-REC-04 由 R017 建立、R020 負責移除；目前 readiness 僅驗 synthetic option-2 passthrough，不宣稱 production bridge 已遷移。TMP-REC-03 舊保存 caller adapter 的移除 owner 為 R015。此輪沒有關閉或重指派 temporary component。

### 全 package 的非 C1 反向依賴範圍

AST inventory 同時顯示 repo 全 package 尚有下列既有 cross-package reverse edges。這些 source files 不屬 C1 owner/change scope；C1 的方向結論只適用上列新 C1 owner，不延伸為整 repo 已符合單向 DAG。

- data_module → app_module：5 個 source files；22 個去重 import names。files：data_module/formal_daily_input_producer.py、data_module/fubon_shadow_candidate_repository.py、data_module/paper_daily_execution_producer.py、data_module/prospective_technical_shadow_producer.py、data_module/watchlist_repository.py。
- data_module → decision_module：19 個 source files；27 個去重 import names。files：data_module/company_registry.py、data_module/fundamental_availability.py、data_module/fundamental_availability_entrypoint.py、data_module/fundamental_availability_sources.py、data_module/fundamental_data.py、data_module/fundamental_sqlite_provider.py、data_module/fundamental_statement_availability_entrypoint.py、data_module/fundamental_statement_availability_sources.py、data_module/fundamental_statement_backfill.py、data_module/fundamental_statement_data.py、data_module/monthly_revenue_availability_history.py、data_module/monthly_revenue_availability_merge.py、data_module/monthly_revenue_backfill.py、data_module/monthly_revenue_snapshot_harvester.py、data_module/statement_semantic_mapping.py、data_module/tpex_daily_price_backfill.py、data_module/valuation_data.py、data_module/valuation_metrics_backfill.py、data_module/valuation_source_policy.py。
- data_module → ml_module：17 個 source files；63 個去重 import names。files：data_module/bounded_official_market_restatement.py、data_module/formal_daily_input_producer.py、data_module/formal_portfolio_ledger.py、data_module/formal_simulated_portfolio_ledger.py、data_module/ml_all_field_snapshot_provider.py、data_module/ml_direct_shared_block_resolver.py、data_module/ml_pit_shared_block_resolver.py、data_module/ml_pit_year_shard_exporter.py、data_module/ml_research_causal_ledger_overlay.py、data_module/ml_research_shadow_union.py、data_module/ml_research_shadow_union_bounded.py、data_module/ml_restatement_current_capture.py、data_module/ml_restatement_current_inputs.py、data_module/paper_daily_execution_producer.py、data_module/portfolio_ml_dataset_assembler.py、data_module/portfolio_ml_direct_numeric_store.py、data_module/recommendation_calibration_source_contract.py。
- decision_module → data_module：6 個 source files；8 個去重 import names。其中 C1 decision_module/recommendation/contracts.py → data_module/contracts/market.py 是本次明定的 SourceRef leaf dependency；5 個非 C1 files 為 decision_module/factors/fundamental_adapters.py、decision_module/factors/statement_factor_adapters.py、decision_module/industry_mapper.py、decision_module/market_regime_detector.py、decision_module/stock_screener.py。
- ml_module → app_module：1 個非 C1 source file；2 個去重 import names。file：ml_module/restated_h5_training_runner.py。
- ml_module → data_module：19 個非 C1 source files；121 個去重 import names。files：ml_module/allocation_base_expert_comparison.py、ml_module/allocation_confirmatory_runner.py、ml_module/allocation_ooc_release_builder.py、ml_module/allocation_oos_portfolio_replay.py、ml_module/allocation_oos_replay_input_builder.py、ml_module/allocation_out_of_core_training_service.py、ml_module/allocation_v3_linear_release.py、ml_module/allocation_v3_readback_bundle.py、ml_module/bounded_restated_research_consumer.py、ml_module/historical_feature_builder.py、ml_module/historical_label_builder.py、ml_module/immutable_ml_block_store.py、ml_module/natural_shadow_pruning_evidence.py、ml_module/pit_archive_consumer.py、ml_module/recommendation_calibration_evidence.py、ml_module/recommendation_historical_replay.py、ml_module/recommendation_natural_outcome_service.py、ml_module/restated_h5_training_runner.py、ml_module/restated_v3_source_custody.py。

AST scan 沒有找到 decision_module → app_module 或 decision_module → ml_module edges。import name counts 是依 source-file／qualified imported-name 去重後計算。上述非 C1 inventory 僅界定本次檢查範圍，沒有嘗試修復或驗收這些 reverse dependencies。

## 未執行項目與 gate 限制

- symlink/reparse 的 4 個負例因 Windows WinError 1314 無法建立測試連結；未計為 pass。
- 不檢查或反序列化正式 DATA_ROOT/output 下資產；測試全部以 TEMP redirect 與 synthetic/tmp_path 完成。
- 未跑 UI tests；此 QA 任務明確排除 UI。
- 未執行 scheduled wrapper main。C1 R014 只測 synthetic saved execution/query/producer oracle；真 wrapper parity 另留 R014。
- 未執行 full-market ML rebuild、訓練、inference 或 promotion。ML-P/N 僅是 synthetic readiness。

以上證據支持已完成的 scoped engineering tests 與靜態檢查結果；R17-N synthetic readiness 已由獨立 reviewer 接受，但 symlink host skip、完整 C1 獨立 review 與 SOL 最終裁決仍未收口。C1 維持 NOT PASSED，Wave 6 維持 BLOCKED。
