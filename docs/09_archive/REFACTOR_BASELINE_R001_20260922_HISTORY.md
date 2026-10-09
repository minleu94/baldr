# R001 實作基線與 caller／artifact 清冊

日期：2026-09-22；任務：R001 — 凍結基線、caller 與 artifact 清冊。範圍為唯讀 repository inventory；未執行 production workflow、tests、資料寫入或 artifact 載入。

## 起始基線與保護點

HEAD：391b057c92037ec7a19cab2bf951d6029d29b020；branch：dev（相對 origin/dev ahead 161）。

~~~text
## dev...origin/dev [ahead 161]
 M docs/00_core/DOCUMENTATION_INDEX.md
 M docs/01_architecture/README.md
 M docs/01_architecture/target_system_architecture.md
?? =
?? docs/01_architecture/target_architecture_2026_09_22/
~~~

共 58 個起始 dirty paths：3 個已追蹤修改、根目錄空檔案 =、target_architecture_2026_09_22/ 下 54 個既有未追蹤架構檔。下表是開始時 hash manifest；完成時重新計算，58/58 相同。R001 未改動、清理或 stage 這些檔案。新增清冊與報告不屬起始 manifest。唯一 rollback point 是移除本任務兩份新文件。

| 起始 dirty path | SHA-256 |
|---|---|
| = | E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855 |
| docs/00_core/DOCUMENTATION_INDEX.md | D11A489071F8B4FC35C2A1386C5699761534B40AC521AD7778EE11A5E1980580 |
| docs/01_architecture/README.md | EE91AAFAF5EC291A01A0B07F3AB06529EF5C07696C0A67C4A8ABCCBACED3EE91 |
| docs/01_architecture/target_architecture_2026_09_22/ARCHITECTURE_INVARIANTS.md | 6E0CE986C075D1F97D4D3DC4B926C81E73305F3264294D1848096FCFBF7EEA0B |
| docs/01_architecture/target_architecture_2026_09_22/ARCHITECTURE_RED_TEAM_REVIEW.md | AEFEDDBD8065073CCB4DF0FB5161CC11BFBF1D23E01F89A4256F68B8B0061692 |
| docs/01_architecture/target_architecture_2026_09_22/ARCHITECTURE_REQUIRED_CHANGES.md | AE3BDB2FD2EB07430C8B876FE3145C518C351FE46C4A546A3E709531948ADE07 |
| docs/01_architecture/target_architecture_2026_09_22/EXTENSIBILITY_TEST.md | 06F07D906ED28A1D7FAF71AFC3358BD80C1C8BDA0D4EF119F8A00157D437346D |
| docs/01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md | 8A5FD6BBF9599ACCDBD30F54357560D4A0903828E75B4BE4997F0D879E037F35 |
| docs/01_architecture/target_architecture_2026_09_22/FINAL_DATA_FLOW.md | A41BC96695B5D7A3944825E8C9B76A4AA6B17E03B42320D3A6E296D58BD9E8C3 |
| docs/01_architecture/target_architecture_2026_09_22/FINAL_EXTENSIBILITY_MODEL.md | 264051825E93CD35C4E3AE9BFEA558F9275A6499E81CA5785870D30E38FD4284 |
| docs/01_architecture/target_architecture_2026_09_22/FINAL_MIGRATION_SEQUENCE.md | E1B7955F66C350C243CF5299DCD7E09889F0C2C96E9CD3DD55679E6ED7AE385F |
| docs/01_architecture/target_architecture_2026_09_22/FINAL_ML_COMPATIBILITY_CONTRACT.md | 4634C7B2CDB8D99FFCB4B7A4439C56118672DCD2D58A7B952E91A1A8E025D010 |
| docs/01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md | 423D08C760E55F6418A5B6105922D2168630D4134DC951B50B1C004758F7B053 |
| docs/01_architecture/target_architecture_2026_09_22/MIGRATION_STRATEGY.md | 91C511543278179BFD222AEF70BA18765F5F1B61A0CE2C9817FFA698E82FBA89 |
| docs/01_architecture/target_architecture_2026_09_22/ML_COMPATIBILITY_PLAN.md | F21F699053951D3439F93764B57DBA6CF86855F4493314741F281E6BCA65CEB3 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_DISPATCH/README.md | B7DE9B29C13F64F5D3C15BFB8DD11C36EAA9487874C51AC9B2B53FD023FDC639 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_EXECUTION_ORDER.md | BF87529013119E967D35BE1429E1D09B3C1D905393A65D57DEB6A554038F42F8 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_IMPLEMENTATION_DAG.md | D408737C585D2A3DC3C6DDADFB5711E0DF0298FB4718A27B08AC7ABB7B454E27 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_MODEL_ASSIGNMENTS.md | 685F5260EC80D56564E9219AB5646A8D68F64339F4F8C60CA254536C4893ED37 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/README.md | 23DB98D250B3CD25A4E969ECB526A2B08E3DBF018DFE4EB130F6DE45B1FC234B |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_RISK_REGISTER.md | E8B8208D9007E09D452C5588D262EC0CE4C556EBCEF9BDB74E74062096A4BBAC |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R001.md | 944311A91B92EBD721F3CAB3FA9A7233B8DA23256CB7A3C95DB52E04B7C9F392 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R002.md | 1028A8A8F78DFAF324EF25DF8D5AC5E89E7B903080DB900DAE82D13ECE32E885 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R003.md | CC12ABBC8A4A3CACC297344AD0A97A2F25881EF99B19D1A64163EC11443944B1 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R004.md | C56FA2E930F41FCF5C218A0F3CAE7C0C8B5D766F80EEDE908AA3E49475B7C3AE |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R005.md | D1E0E52A1A585F219FB9C8FC7E103F6B0D3D043C9EDAEE6C69AAA1545C94120A |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R006.md | 90DCDB8F297030EE31BDA2C3F4A72A14FF06D7BA181CD4DD684F7FEAD32C3C9F |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R007.md | F674EE402C1673C919BB29AD938E549A3FC5DA84D09C4D4661CA4AA60D1FB200 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R008.md | CC8B036BD1F9AD424D6E4214EDFDF32FE4D44C7FBD14834BB90B4C3636B170BE |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R009.md | CE9C25A70F4787823412CCD8A206BAFE3F96C9A31F6E5D8F481D81DBB8A0CC52 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R010.md | 755B0BB24B99C5DEE308D79BE4DE9C3B052AFDFC7B84D61125AD260C29F0606F |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R011.md | 63C2FDA62A44700B5B45934C3DE667A6CFBECB6F9EC46455F19E1C59322756AB |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R012.md | AB13B72A69C291F751CF1EFFB57D181CF2A7F1DBD77A7FA4846772C6AA5D9154 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R013.md | 05743084A04100C2A9F49FB78A135E68A5ED07569479FE5DC03F8A6C72964C1A |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R014.md | 2BF98C65F8F19FF93F788BEC9DFB2106793C22C270334B061E9F99069F5AA7DE |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R015.md | 900191140ACC98BA64B24F030C17243834E42706F7767BC3755AFD4AEA770579 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R016.md | 3E9235D93558BFE95CD1102895D2BB772070ACBA7558C6362DDDE52751E822F7 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R017.md | 388711D00718B02463E2D57F5F328E1BF81650B6854AA3F32AB0F3A9EFB4C00D |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R018.md | 223A7552014D70964A66D1ECA452A9C3958C766481DE4AFCB774539581078D1E |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R019.md | 2E33DFDE0F6AD9F68F9EC8717DB3D40BF43A14980C1439957D0F80D94AAFA160 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R020.md | 46D774AF560167398B079D8DFEB7B04073291F95CBEF837BC68EF1AB35AB27C5 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R021.md | 654B0ECCACB63BA856C5F19B7BD736982CFF20FCA9ECF3C25E6ED9D98E6CF039 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R022.md | 394ADE5603DEC40883DFF65B2F2E679B83F36C36F2B2E780D186DEC26D3AF60F |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R023.md | DF8BF248B340E798124F8006AFE21640D086E217C865053DCED919614A7DADBB |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R024.md | 14DFF6ACA0B6A27C3F7471BE860BCACC2F9272B845A5FD485F1BBF12D4FD103B |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R025.md | 54F4260991338B0BD7B66E08789C885BA6D8869DF3259D3A5D06D59FC6555EDF |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R026.md | B92203DB3AF29808B0877B95200C2EEFCA1286EC2902357A49299E3F500320BF |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R027.md | 58F3DF90E831D955DF15182B266E8EE7B6D2AF0D22AFD2AB3AA751EECFDE7E5B |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R028.md | 6F78815CFC4C7D5DBF7C1B1B7F7CC1D89D1812BB8E8560BD416FAAE9DB23BF3C |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R029.md | 07F52EB41E883FDB21BC69A0B7F63263B43DB33A1E19A87FFE031DA3BFF1C221 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R030.md | C7D1F7E2F68863580B52EECD0228F9916FE8EA231A31D3F3C8B04EB901C5BE40 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R031.md | 3D146EB9456C587D90F809CD2F80C31EF9B9C4278B305D8D1F2174EFD0249A26 |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/README.md | B6EFEFB25EC9F45A98FB4278AE0F8C74C11156B38E9B92D1AB3764AF5795786C |
| docs/01_architecture/target_architecture_2026_09_22/REFACTOR_VALIDATION_MATRIX.md | B43AE4AA882244A0362D95C463795D82EE460BAC7B03DA7647FFB12CC7833810 |
| docs/01_architecture/target_architecture_2026_09_22/SYSTEM_ARCHITECTURE_ASSESSMENT.md | 61993AB1D4C3DD1B21CE3105C4B6FC7F09BB131B1BCE0300548623A952267CFF |
| docs/01_architecture/target_architecture_2026_09_22/TARGET_ARCHITECTURE.md | ED6538BA0D51842CCE229F82EE1A326A88BA612046A7BC7287A9BFD8C2A1D305 |
| docs/01_architecture/target_architecture_2026_09_22/TARGET_DATA_FLOW.md | 2DE64695C2A4882FEDD25D3DCDDC010A1649B1BFB8DA90B36857A4E083C890D8 |
| docs/01_architecture/target_system_architecture.md | 4FE139276ABFF11D94B6CA2B84A9E7E755A176F710236A41DAD1C7DE90A8F557 |

## 權威依據與重跑查詢

已依 R001 spec、FINAL_ARCHITECTURE_INVARIANTS（INV-01/02/15/17/18）、FINAL_MIGRATION_SEQUENCE Block 1/caller 起點/temporary retirement ledger、DAG R001、V-SOURCE/R001 validation row、RK-08/RK-19/RK-20/RK-25、MODEL_ASSIGNMENTS R001、REFACTOR_REPORTS/README，以及 AGENTS.md、git_exclusions.md、execution_agent 規範盤點。R001 無 dependencies；R002–R031 尚未 release。

以下由 repo 根目錄重跑。Source 搜尋只覆蓋允許目錄。Artifact census 僅列檔名與讀 manifest JSON metadata；不反序列化未知 joblib/pickle。
~~~powershell
git status --short --branch
git rev-parse HEAD
git branch --show-current
rg -n --glob '*.py' 'run_recommendation|last_calibration_projections|last_screening_matrix|last_excluded_candidates_json|last_why_not_payload_json|last_liquidity_gate_payload_json|last_exclusion_quality|last_exclusion_warnings_json|last_run_context' app_module ui_qt scripts runtime development_module tests
rg -l --glob '*.py' 'run_recommendation|last_calibration_projections|last_screening_matrix|last_excluded_candidates_json|last_why_not_payload_json|last_liquidity_gate_payload_json|last_exclusion_quality|last_exclusion_warnings_json|last_run_context' app_module ui_qt scripts runtime development_module tests
rg -n --glob '*.py' 'importlib\.import_module|__import__|qualified_name|class_path|python_module|estimator_class|model_class|joblib\.(load|dump)|pickle\.(load|dump)' app_module ui_qt scripts runtime development_module tests ml_module data_module
rg -n --glob '*.py' --glob '*.ps1' --glob '*.cmd' 'baldr-recommendation-snapshot-daily|run_recommendation_snapshot|run_scheduled_recommendation_snapshot' scripts tests
rg -n --glob '*.py' 'StrategySpec|StrategyRegistry|RecommendationResultDTO|RecommendationDTO|save_result_create_only|save_result\(|load_result\(' app_module ui_qt scripts runtime development_module tests
rg -n --glob '*.py' 'TMP-(REC|NUM|ML|STR)-[0-9]+' app_module ui_qt scripts runtime development_module tests
git diff --check
~~~

窄查詢共有 41 檔：14 個非 tests 檔、27 個 tests 檔。另以 direct import、bound callable、getattr、排程字串、repository reader/writer、manifest 名稱查詢分類；graphify 僅作導航，不作完成證據。

## Recommendation caller 與資料 authority

| Symbol/path | Mode、讀寫權限 | Owner | 後續 task／永久相容理由 |
|---|---|---|---|
| app_module/recommendation_service.py：RecommendationService.run_recommendation；141–148 八個 last_* | Engine 入口；寫候選、screening/exclusion/why-not/liquidity、quality/warnings、run_context、calibration projections；不直接保存 DTO | Recommendation service | R011；R013–R015 切 caller；R029 在 external support 確認後 retirement |
| app_module/application_ports.py：RecommendationServicePort | 靜態介面，宣告 run_context 與 last_* | App ports | R011/R013–R015；R029 保留需要的相容 façade |
| ui_qt/views/recommendation/execution_coordinator.py：bound run_recommendation | 動態 worker callable；呼叫服務、不擁有狀態 | UI recommendation | R013 |
| ui_qt/views/recommendation_view.py：RecommendationView | direct consumer；getattr 讀 last_*，組 snapshot/DTO，使用者保存時呼叫 repository | UI recommendation | R012 save contract / R013 Qt cutover |
| app_module/recommendation_save_coordinator.py：RecommendationSaveRequest.build_result/persist | 讀 last_*，組 DTO、呼叫 regime detection、save_result | Save coordinator | R012–R015 |
| scripts/run_personalization_recommendation.py；app_module/personalization_save_adapter.py：main/save_and_readback | CLI direct；動態選 save_result_create_only，缺此 API 時 fallback save_result；load_result readback 後 ACK Journal | Personalization | R012 save contract / R015 personalization cutover；保留 create-only 與 exact readback |
| scripts/scheduled/run_scheduled_recommendation_snapshot.py：main | scheduler direct；呼叫 service/save_result，輸出 receipts | Scheduler | R014；CLI/task name 是 string contract |
| scripts/inspect_scheduled_task_registration.py | task/path string inspector，read-only | Scheduler operations | R014 |
| scripts/qa_personalization_mainwindow_save_readback.py、scripts/qa_validate_phase2_5.py、qa_validate_phase3_3b.py、qa_validate_pattern_opt.py、qa_validate_recommendation_tab.py、qa_validate_research_journey_qt.py | QA direct callers 或 last_*/save boundary checks；非 production writer，未執行 | QA/UI | R013–R015；R029 前保留 |
| tests/ | 下列 27 檔涵蓋 direct call、DTO/readback、UI/worker、scheduler/calibration；test fixture/spy 為 test-only writer，未執行 | 各 consumer owner | 對應上述後續 task，作遷移 regression evidence |

27 個測試檔：test_cross_page_decision_journey_mainwindow.py、test_forward_machine_policy_producer.py、test_pit_industry_callers.py、test_personalization_read_service.py、test_personalization_save_integration.py、test_personalization_generation_cli.py、test_personalization_fit_runner.py、test_recommendation_execution_coordinator.py、test_recommendation_fundamental_filters.py、test_recommendation_natural_outcomes_cli.py、test_recommendation_market_data_provider.py、test_recommendation_recomputation.py、test_recommendation_ranking_service.py、test_recommendation_v1_7_negative_evidence.py、test_recommendation_save_coordinator.py、test_recommendation_service_calibration_integration.py、test_scheduled_cmd_scripts_no_confirm.py、test_scheduled_scripts_exist.py、test_scheduled_cmd_scripts_exist.py、test_scheduled_recommendation_snapshot_wrapper.py、test_scheduled_cmd_scripts_task_names.py、test_scheduled_readme_no_production_confirm.py、test_task_loop_03_contract.py、test_ui_qt_p2_status_accessibility.py、test_ui_qt_research_context_status.py、test_ui_qt_v5_guided_readability.py、test_ui_thin_shell_boundaries.py。

測試 caller 的 owner/task/read-write 分組：test_recommendation_fundamental_filters.py、test_recommendation_recomputation.py、test_recommendation_ranking_service.py、test_recommendation_v1_7_negative_evidence.py、test_task_loop_03_contract.py 為 service/engine test consumers（test-only fixtures，R002 characterization、R011 execution capture、R019 evaluator）；test_pit_industry_callers.py 提供 PIT/input coverage（R018/R023 where applicable）。test_recommendation_execution_coordinator.py、test_ui_qt_p2_status_accessibility.py、test_ui_qt_research_context_status.py、test_ui_qt_v5_guided_readability.py、test_ui_thin_shell_boundaries.py、test_cross_page_decision_journey_mainwindow.py 為 UI/worker integration consumers（test-only spies，R013）；test_recommendation_save_coordinator.py、test_personalization_read_service.py、test_personalization_save_integration.py、test_personalization_generation_cli.py、test_personalization_fit_runner.py 為 save/readback/CLI consumers（test-only repository writer/readback，R012/R015）；test_recommendation_natural_outcomes_cli.py 為 scheduled CLI consumer（test-only fake producer/repository，R014）；test_recommendation_service_calibration_integration.py 為 calibration integration coverage（R010 contract、R011 capture parity、R026 explicit ML flow）；test_recommendation_market_data_provider.py 為 market-data/input provider coverage（R018）；test_forward_machine_policy_producer.py 與 test_scheduled_cmd_scripts_no_confirm.py、test_scheduled_scripts_exist.py、test_scheduled_cmd_scripts_exist.py、test_scheduled_recommendation_snapshot_wrapper.py、test_scheduled_cmd_scripts_task_names.py、test_scheduled_readme_no_production_confirm.py 為 scheduler/string consumers（test-only fake producer/repository，R014）。

## DTO、repository 與 persistence contract

- Qualified paths：app_module.dtos.RecommendationDTO、app_module.dtos.RecommendationResultDTO，定義於 app_module/dtos/__init__.py。move/re-export/serialized support 對應 R009/R016/R029。
- RecommendationDTO.to_dict 保留中文 keys：證券代號、證券名稱、收盤價、漲幅%、總分、指標分、圖形分、成交量分、推薦理由、產業、Regime匹配；及 score_percentile_bp、eligible_universe_size/date、ranking_method、threshold_mode、ranking/calibration/evidence keys。calibration keys 包含 ranking_score_bp、calibrated_probability_bp/status、after_cost_profit_probability_bp/status、evidence_confidence、sample_size、cost_basis_bp、calibration_model_version、calibration_dataset_version、calibration_horizon/status/source/warnings/source_trace、calibration_probability_transform_id、calibration_probability_baseline_id/kind/probability_bp、calibration_raw_probability_bp、calibration_raw_after_cost_probability_bp、calibration_provenance。quantile mode 另有百分位、母體數、排名日期、排名方法、門檻模式。from_dict 接受英文及歷史中文 keys。
- RecommendationResultDTO.to_dict keys：result_id、result_name、config、recommendations、regime、created_at、notes、excluded_candidates_json、screening_matrix_json、why_not_payload_json、liquidity_gate_payload_json、exclusion_quality、exclusion_warnings_json、run_context。舊 config 可帶 _recommendation_run_context；沒有 schema_version。
- app_module/recommendation_repository.py：runs_dir=resolve_output_path('recommendation/runs')；SQLite recommendation_runs.db / runs 欄位 result_id PK、result_name、regime、stock_count、config(JSON)、notes、created_at、data_path；索引 idx_created_at、idx_regime。
- Writer authority：save_result 使用 BEGIN IMMEDIATE、JSON + INSERT OR REPLACE；personal capture/orphan guards 阻止舊 writer 覆寫受保護記錄。save_result_create_only 使用 BEGIN IMMEDIATE + INSERT，只建立一次並保留安全 retry orphan。personalization adapter 負責 load_result readback/ACK；load_result 讀 JSON 並以 RecommendationResultDTO.from_dict 還原。歷史檔不覆寫、不遷移。

## Replay、strategy、regime、ML 與 artifact support

| Symbol/path | Mode/authority | Owner | 後續 task／永久相容理由 |
|---|---|---|---|
| app_module/recommendation_replay_service.py：RecommendationReplayService.run_snapshot | 歷史 replay wrapper；依決策日期／可得日期／universe 篩選後呼叫 provider，回傳 RecommendationSnapshotDTO（recommendations 欄位承載 provider rows）；不寫 repository | app research／recommendation | R005/R017/R020；目前 wrapper 呼叫現行 legacy provider；TMP-REC-04 bridge 尚未建立（R017 建立、R020 移除） |
| app_module/recommendation_dataframe_provider.py：RecommendationDataFrameProvider.__call__ | portfolio/replay DataFrame provider；獨立 legacy scoring/filter/sort policy；回傳 List[Dict[str, Any]] recommendation rows（含 total_score/factor_scores）；不寫 repository | app research／recommendation | R005/R017/R020；現行 legacy list[dict] provider 與 mode-specific policy 仍 active；TMP-REC-04 bridge 尚未建立（R017 建立、R020 移除） |
| app_module/strategy_spec.py：StrategySpec.to_dict/from_dict；app_module/strategy_registry.py：StrategyRegistry | direct import/lookup；JSON/YAML 保存 strategy_id/spec，不是 executor class path；registry 是 mutable runtime registry | Strategy/backtest | R025 relocation owner；R007 是 data leaf contract，R008 是 recommendation/execution contract；保留歷史 spec |
| app_module/strategies/{baseline_score_executor.py,momentum_aggressive_executor.py,stable_conservative_executor.py} | import-time registration；qualified paths 為 app_module.strategies.baseline_score_executor.BaselineScoreExecutor、app_module.strategies.momentum_aggressive_executor.MomentumAggressiveExecutor、app_module.strategies.stable_conservative_executor.StableConservativeExecutor | Strategy/backtest | R025 relocation owner；R007/R008 各自仍負責 data leaf 與 recommendation/execution contract；若 serialized/worker consumer 需保留 alias |
| app_module/backtest_service.py、batch_backtest_service.py、optimizer_service.py、walkforward_service.py、recommendation_service.py、ui_qt/views/backtest_view.py | direct StrategySpec/Registry callers；Qt 還直接讀私有 StrategyRegistry._registry.get | Strategy/UI | R025 relocation owner；R007 是 data leaf contract，R008 是 recommendation/execution contract；private access 為 known coupling |
| decision_module/market_regime_detector.py：MarketRegimeDetector/RegimeService | output_dir/regime_history.json reader/writer；載入 history，hysteresis 更新／保存；save coordinator 呼叫 detect_regime | Decision/regime | R022 state owner；R012/R015 是 save-time prerequisites；R021 負責 StockScreener I/O |
| app_module/recommendation_service.py calibration path | 呼叫 MLHistoricalSnapshotProvider.load、HistoricalFeatureBuilder.compute；消費 candidate/projection，寫 projection receipt/run_context | Recommendation calibration | R010/R026；app_module/recommendation/ml_adapter.py 尚不存在 |
| ml_module/model_artifact_manifest.py：ModelArtifactManifest；ml_module/model_artifact_loader.py：SafeShadowModelArtifactLoader.load | 驗證 JSON manifest 後 joblib load；schema ml-model-artifact-manifest.v1 含 model/dataset/family、feature/label hashes、ordered schema、library versions、format、filename/hash；不含 estimator qualified class path | ML artifact | R006/R027；保留 manifest/joblib ABI |
| ml_module/recommendation_calibration_training.py | training/publish writer，產生 joblib + manifest；預設 recommendation_learning path 不存在 | Calibration ML | R010/R026；R001 不訓練 |
| Readers：app_module/allocation_release_adapter.py::_load_joblib_object、ml_module/allocation_ooc_release_builder.py、ml_module/allocation_promotion_reference.py、app_module/ml_allocation_inference_service.py；writers：ml_module/allocation_training_service.py、allocation_out_of_core_training_service.py、allocation_v3_linear_release.py、allocation_ooc_release_builder.py | allocation/OOC artifact read/write；binary 未載入 | Allocation ML | R006/R027；舊 class paths 保持 unknown |
| Direct 15-path identity allowlist | store/checkpoint/identity/hash 讀寫權威；hash 不變更 | Direct ML data | R006/R027；R028 條件項；identity ABI 相容 |

Direct dependency allowlist（source 順序）：data_module/portfolio_ml_direct_numeric_store.py、data_module/portfolio_ml_dataset_assembler.py、data_module/portfolio_ml_out_of_core_store.py、data_module/ml_storage_capacity.py、data_module/ml_pit_shared_block_resolver.py、data_module/ml_direct_shared_block_resolver.py、data_module/formal_portfolio_ledger.py、data_module/rule_champion_snapshot_service.py、data_module/teacher_input_source_producer.py、ml_module/allocation_training_service.py、ml_module/allocation_contracts.py、ml_module/allocation_teacher.py、ml_module/immutable_ml_block_store.py、ml_module/purged_walk_forward.py、data_module/ml_price_availability_contract.py。

Direct observed constants：direct-numeric.v4、checkpoint.v2、dependency identity v1、computation identity v1、carry v2。CLI scripts/build_portfolio_ml_direct_numeric_store.py；provenance inspector scripts/inspect_ml_direct_checkpoint_provenance.py。Direct/OOC manifest schemas：allocation-ooc-expert.v5、allocation-ooc-meta.v3、allocation-ooc-training.v5、portfolio-ml-corporate-action-custody.v1、portfolio-ml-direct-computation-dependencies.v1、portfolio-ml-direct-computation-identity.v1、portfolio-ml-direct-numeric.v4、portfolio-ml-official-trade-restriction-custody.v1、portfolio-ml-ooc-fold-index.v1、portfolio-ml-ooc-store.v3、portfolio-ml-ooc-year.v3、portfolio-ml-replay-source.v1。Observed declared feature_registry_hash：sha256:8b0f831a94ecd503591a146d36412b2385397928b98fbd607a33fa6073630f27；未與程式碼重算比較。

CORE_LONG_HISTORY_FEATURE_REGISTRY ID core-long-history-features-v1，20 ordered int features：stock_return_1d_bp、stock_return_5d_bp、stock_return_20d_bp、stock_return_60d_bp、trailing_volatility_20d_bp、high_low_range_20d_bp、close_to_ma_5d_bp、close_to_ma_20d_bp、close_to_ma_60d_bp、rsi_normalized_bp、adx_normalized_bp、macd_normalized_bp、volume_ratio_5d_bp、volume_ratio_20d_bp、turnover_amount_minor、market_return_5d_bp、market_return_20d_bp、market_return_60d_bp、stock_minus_market_20d_bp、industry_relative_return_20d_bp。除 turnover_amount_minor 單位 minor_currency_unit 外均為 bp；missing_is_not_zero；availability=feature_as_of_before_decision；不含 broker/fundamental。CORE_LONG_HISTORY_LABEL_REGISTRY ID core-long-history-labels-v1：relative_return_20d_bp、maximum_adverse_excursion_20d_bp、downside_20d_flag、cross_sectional_top_quintile_20d_flag；20 trading-day horizon，末兩者 boolean_int；missing=pending_is_not_zero；availability=available_on_horizon_end；downside_threshold_bp=-500。

## Artifact census、scheduler string 與 TMP ledger

Artifact census 日期 2026-09-22，僅列檔名/metadata：
- Python 3.11.9；selected versions：numpy 2.3.5、pandas 2.3.3、scikit-learn 1.8.0、joblib 1.5.2、PySide6 6.10.1、pydantic 2.12.5、pytest 9.0.2、scipy 1.16.3、pyarrow 22.0.0。requirements-runtime.txt 定義 Windows/Python 3.11 baseline。
- DATA_ROOT、OUTPUT_ROOT、RECOMMENDATION_LEARNING_OUTPUT_ROOT 未設定；data_module/config.py 預設 DATA_ROOT=D:/Min/Python/Project/FA_Data，output 在此 root 下；recommendation_learning 預設路徑不存在。
- 預設 DATA_ROOT/output 有 94,664 個 manifest 或 joblib/pkl/pickle 檔名：11,559 manifests、83,105 serialized。output/recommendation/runs 有 87 個 JSON 和 recommendation_runs.db；未讀 JSON/SQLite 內容。
- release_v4 counts（manifest/serialized）：direct_numeric_fixture 6/0；portfolio_ml_direct_numeric_production_v4 0/0；portfolio_ml_direct_numeric_production_v4_v2 630/0；portfolio_ml_direct_numeric_production_v4_v2-source-rebuild-79dccf8b7f0b 7/0；portfolio_ml_direct_ooc_training_production_v4_v5 10,501/83,100。
- DATA_ROOT/models 有 _EnsembleModel_model.pkl（3,030,277 bytes）、2330_EnsembleModel_model.pkl（2,715,314 bytes）；source 無同名引用且無 sidecar manifest，均未載入；內部 estimator/class path unknown。
- Direct/OOC JSON metadata 未命中 qualified_class、class_path、estimator_class、model_class、python_module、qualified_name、module_path；不能推論 binary pickle/joblib 無 qualified paths。

Scheduler/CLI string chain 共 18 個節點：scripts/scheduled/register_baldr_scheduled_tasks.ps1（baldr-recommendation-snapshot-daily → scripts/scheduled/run_recommendation_snapshot.cmd）、scripts/scheduled/register_baldr_scheduled_tasks.cmd、scripts/scheduled/run_recommendation_snapshot.cmd、scripts/scheduled/run_scheduled_recommendation_snapshot.py、scripts/inspect_scheduled_task_registration.py、scripts/scheduled/unregister_baldr_scheduled_tasks.cmd、scripts/scheduled/unregister_baldr_scheduled_tasks.ps1、scripts/scheduled/query_baldr_scheduled_tasks.cmd、scripts/scheduled/README.md；測試/操作 contract：tests/test_forward_machine_policy_producer.py、tests/test_recommendation_calibration_contract_guards.py、tests/test_scheduled_cmd_scripts_no_confirm.py、tests/test_scheduled_cmd_scripts_exist.py、tests/test_scheduled_cmd_scripts_task_names.py、tests/test_scheduled_readme_no_production_confirm.py、tests/test_scheduled_recommendation_snapshot_wrapper.py、tests/test_scheduled_scripts_exist.py、tests/test_banktaiwan_recommendation_learning_operational.py。Owner scheduler operations；R014 是整個 scheduler/string chain 的 migration owner，舊 task name/CLI behavior 是 support contract；未啟動排程。

| TMP | Baseline 狀態 | Owner | 後續 task／處置 |
|---|---|---|---|
| TMP-REC-01 | 舊 engine body 存在；invocation capture 尚未建立；recommendation/execute.py 不存在 | Recommendation execution | R011 建立、R019 retirement |
| TMP-REC-02 | run_recommendation 舊 list API 仍 active；canonical-delegating TMP-REC-02 compatibility facade 尚未建立（R011 建立） | Execution/callers | R011/R013/R014/R015 cutover；R029 外部 callers 收斂後 retirement |
| TMP-REC-03 | RecommendationSaveRequest.build_result/persist 舊呼叫形狀仍 active；TMP-REC-03 canonical-execution 保存 adapter 尚未建立（R012 建立） | Save coordinator | R012–R015 readback/cutover |
| TMP-REC-04 | 尚未建立；現行 RecommendationDataFrameProvider.__call__ legacy list[dict] 路徑仍 active | app research／recommendation | R017 建立、R020 移除 |
| TMP-REC-05 | DTO 仍定義於 app_module/dtos/__init__.py；搬移 shim 未建立 | DTO/persistence | R009/R016/R029；需要 serialized/external support 時永久 alias |
| TMP-REC-06 | isolated dual-run parity harness 未建立；R001 僅 inventory | QA | R011 creator；R029 remover |
| TMP-NUM-01 | float score/dict boundary 仍在 engine/replay/DTO | Numerical execution | R002/R009 提供 characterization/codec evidence；R011 建立 named boundary；R019 退休 rule 子路徑、R020 退休 replay 子路徑；R029 依 independent numeric gate 最終 close/retain |
| TMP-ML-01 | RecommendationService 仍呼叫 MLHistoricalSnapshotProvider.load、HistoricalFeatureBuilder.compute；ml_adapter.py 未建立 | Calibration ML | R010/R026 |
| TMP-ML-02 | Direct identity dependency/checkpoint/hash path active | Direct ML data | R006/R027；R028 視規格 |
| TMP-STR-01 | 僅 architecture conditional；source/runtime 無 marker/alias，尚未建立，非 runtime 現況 | Strategy | 若 R025 建立，才由 R029 移除或轉永久 alias |

## Known gaps 與限制

未知包括外部部署 DATA_ROOT、external/dynamic Python caller support、joblib/pickle binary 內部 qualified class paths、無 sidecar 舊模型 ABI。依 RK-08/RK-19/RK-20/RK-25 登錄；artifact/class-path unknown 對應 R006/R027，external/dynamic caller support 由 R029 處理（R001 已完成 inventory）；unknown 不視為不存在。feature hash 僅抄錄 manifest 聲明，未重算。未知模型不載入；未跑 pytest、CLI、scheduler、backtest、ML training 或 production workflow。依 INV-01/02/15/17/18 保留現行相容邊界與 writer authority，未修改 business、numerical、persistence 或 replay semantics。
