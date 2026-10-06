# 專案導航文件

## 2026-10-05 具名母體盤勢與指標排序

市場探索的研究母體盤勢 → 推薦分析每日研究條件 → pinned 個股研究，共用同一 verified 日快照。投影與數值排序入口為 `app_module/daily_market_cohort_projection.py`，呈現為 `ui_qt/views/daily_market_cohort_view.py`／`daily_market_research_view.py`，Main 只接訊號與導覽。方法 registry／manifest／producer 保持原版本；原排名未提供保持 unknown。完整操作見 [Manual](docs/07_guides/APPLICATION_MANUAL.md#2026-10-05-ux1318-具名研究母體盤勢與指標排序)。


### UX04／05 日常研究flow導航（2026-10-05）

讀模型與三態組合：app_module/daily_market_research_screener.py；來源UI：ui_qt/views/daily_market_research_view.py及RecommendationView；下鑽：MainWindow→ResearchStockContextDTO／session→StockResearchReportReadService→StockResearchReportView。原producer／repository復用，沒有第二套條件計算。操作見[Manual](docs/07_guides/APPLICATION_MANUAL.md#2026-10-05-ux0405-每日研究條件與同源個股)，來源／驗證見[QA新章](docs/06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。

### UX19 隔離研究快照入口（2026-10-05）

有界唯讀來源：`app_module/daily_market_snapshot_source.py`；發布：`daily_market_snapshot_producer.py`；核驗讀回：`daily_market_snapshot_repository.py`；實際 consumer：`StockResearchReportReadService.read_report()`；隔離 CLI：`scripts/produce_daily_market_research_snapshot.py`。既有 close／MA 投影仍由 `daily_market_feature_snapshot.py` 負責。操作與資格限制見 [Manual UX19](docs/07_guides/APPLICATION_MANUAL.md#2026-10-05-ux19-隔離研究快照生產與讀回)，[QA 收據](docs/06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)保存有限完成範圍。

**版本**：v1.4.10
**最後更新**：2026-10-05

本輪請先看 [目前狀態](docs/00_core/PROJECT_SNAPSHOT.md)、[V4.1 歷史方法包 QA](docs/06_qa/V4_1_HISTORICAL_METHOD_PACK_2026_09_12.md)、[Luna整合驗收](docs/06_qa/V4_LUNA_REVIEW_AND_WORKSPACE_CLOSEOUT_2026_09_08.md)及[工作區檔案說明](docs/06_qa/WORKSPACE_FILES_AND_CLEANUP_2026_09_08.md)。個股研究入口由持倉／觀察清單共用，操作與限制以 [Manual](docs/07_guides/APPLICATION_MANUAL.md) 為準。

UX08 原生個股圖的同源投影入口為 `app_module/stock_research_chart_payload.py`，consumer 為 `ui_qt/views/stock_research_report_view.py`：價格 points／精確表共用核對後輸入，source pin 與行指紋分開核對，保留 cutoff／缺可得時間邊界。沒有新 SQL、策略公式或外部圖商依賴；[限定 QA 與剩餘 UX08 項目](docs/06_qa/UX08_NATIVE_CHART_CONTRACT_20261005.md)。
2026-09-21 V5 日常操作與可讀性工程入口：先從「決策工作台」的每日優先摘要開始；日常使用、進階研究、系統維護的分層與個股研究報告按需 tab 由 [UI Features](docs/02_features/UI_FEATURES_DOCUMENTATION.md) 和 [V5 acceptance evidence](docs/06_qa/V5_READABILITY_ACCEPTANCE_2026_09_21.md) 對照。這是 bounded 工程進度，不取代 Snapshot／Product／6M／Version scoped authority。

## 2026-10-03 整合修復現況入口

- UX18有限consumer：`app_module/daily_market_feature_snapshot.py` 投影既有close／MA20／MA60，個股 `read_report()`、理由與首屏實際共用三態；來源／版本／日期綁identity，必要暖機不足保持unknown。操作見[Manual](docs/07_guides/APPLICATION_MANUAL.md#2026-10-05-ux18-共用日特徵與個股觀察)，依賴與驗證見[原QA收據新章](docs/06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。完整UX18／UX19發布仍待，Backtest子gate未改。

- UX16唯讀來源契約：`app_module/current_observed_source_contract.py` 重用 `DecisionMarketFrameLoader` 的opt-in時鐘欄位與strict SQL讀取，`scripts/inspect_current_observed_source_contract.py` 提供明示cohort／cutoff／rowset pin的研究preflight入口；[Manual](docs/07_guides/APPLICATION_MANUAL.md)與[限定收據](docs/06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)說明未知／拒絕與資格。沒有正式snapshot writer或新方法入口。

- 本輪四用途工程補全與完整驗收追蹤：[Astra 工程收尾](docs/06_qa/ASTRA_ENGINEERING_CLOSEOUT_20261003.md)。新現況來源由 `data_module/current_fundamental_snapshots.py`、`current_official_valuation.py`、`current_market_status_observation.py` 管理；個股 ML／Exit 唯讀接線在 `app_module/stock_research_report_provider_adapters.py`。同名 source 的日期、run 與 SHA 不可互換。

- 目前已確認狀態與仍待驗收事項：先讀 [PROJECT_SNAPSHOT](docs/00_core/PROJECT_SNAPSHOT.md)，再讀[三階段整合修復紀錄](docs/06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)。後者保留各次真實成功、失敗、原生 Task 與 QA 收據，不可用較早失敗段落覆蓋上方現況。
- current-restated 受控研究路徑與原 Legacy／Bank sidecar 操作、來源時鐘、hash 參數、cold-process 驗證及回退限制，見 [APPLICATION_MANUAL §7.0.1](docs/07_guides/APPLICATION_MANUAL.md)。主要實際入口為 `scripts/build_ml_pit_year_shards.py`、`scripts/build_ml_current_restated_outcome_store.py`、`scripts/train_bounded_restated_research.py` 及既有 Legacy／Bank scheduled wrapper 的明確 research-only opt-in。它不改推薦清單、不走 Formal／PIT、也不切正式模型指標。
- 同一研究流程的來源 context 由 `data_module.ml_daily_price_revision_gate.load_verified_current_restated_source_context()` 對 snapshot receipt、原 DB 與修訂依賴作 typed revalidation；context envelope 由 `ml_module.current_restated_research_bridge.save_verified_current_restated_context_file()` create-only 保存並再載入驗證。current 向量必須由 B immutable numeric loader 與 C 的 `verify_b_current_vector_against_core19()` 綁定來源 bytes／registry／日期後取得，不能手工拼造 JSON 或把它轉成歷史 PIT row。
- 每日 G9 的完整推薦 cohort 由 `scripts/scheduled/run_daily_recommendation_learning.py` 接入；`ml_module/current_observed_feature_snapshot_composer.py` 對 17–50 檔建立保留逐批來源的 v2，單批查詢仍不超過 16 檔。`recommendation_calibration_evidence.py` 公開 verifier 重播輸入來源，`recommendation_natural_outcome_service.py` 核驗之後二十個官方 session 的結果，`current_observed_natural_research_fit.py` 僅在隔離研究根擬合。原 capture 與後續結果各自保留日期、快照及雜湊，不授正式 PIT／promotion 資格；操作與排錯見 [APPLICATION_MANUAL](docs/07_guides/APPLICATION_MANUAL.md)。
- 資料更新頁分開顯示 Formal 與 Candidate 狀態；freshness 檢查需核對資料根、DB、cutoff、目前期別與 receipt。跨越 `America/Los_Angeles` 的 04:30 發布週期 cutoff 要重新 probe；此時區隨美西夏令時間變更，不是台北 04:30。取消是合作式停止，已完成的安全提交可能保留；TDCC candidate 只接受可重試的原子 row/checkpoint 結果。操作細節在[完整手冊第 4 節](docs/07_guides/APPLICATION_MANUAL.md)。
- 排程／heartbeat 的現況及唯讀職責見 [Evidence Scheduled Morning Check](docs/07_guides/EVIDENCE_SCHEDULED_MORNING_CHECK.md) 與 [scheduled README](scripts/scheduled/README.md)。

**目標讀者**：專案開發者、新加入工程師

---

## 1️⃣ 專案一句話定位

**baldr 是一套「可驗證、可回溯、可演化」的台股研究與投資決策工作台。**

系統提供完整的數據更新、市場觀察、股票推薦、策略回測功能，讓策略成為可被描述、被比較、被淘汰的研究對象。這不是單純的策略腳本，而是一個工具型系統。

產品北極星見 `docs/01_architecture/system_vision_specification.md`。Daily Decision Desk 的唯一實例位於「市場探索 > 市場總覽」；Workbench「決策來源」只導向同一畫面。現行開發仍以 `docs/01_architecture/system_architecture.md` 的模組邊界為準。

Evidence rehearsal 的唯讀工程預演底座已收口為 `engineering_rehearsal_complete`；它可重跑 replay / source shadow / ML shadow / lineage 的 coverage、quality、missingness 與 blocker 揭露，Workbench 只讀顯示、沒有 apply / promote。它不是 forward evidence，也不會把 External Validation Register 自動標為 complete；接手時先讀 `docs/06_qa/EVIDENCE_REHEARSAL_ENGINEERING_CLOSEOUT_2026_07_14.md`，再依 register 的 owner 與 completion rule 累積真實資料、授權、時間與人工 Gate。

本輪全專案整理與已知問題見[整併查核](docs/06_qa/PROJECT_CONSOLIDATION_REVIEW_2026_09_07.md)，上一輪三線背景見[LUNA 三線計畫](docs/09_archive/LUNA_PARALLEL_PLAN_2026_09_07.md)（歷史歸檔）。B 線環境與需求關係見[LUNA B 環境基線](docs/09_archive/LUNA_B_ENVIRONMENT_2026_09_07.md)（歷史歸檔）；可重跑的 repo map 與候選引用證據由 `scripts/audit_luna_b_repo_map.py` 產生到 `output/luna_B/`。本導航不再複製 dated headroom 或 preflight-only 為目前執行狀態；容量以實際目的卷探針與 `data_module/ml_storage_capacity.py` 為準，執行／驗收現況回到 Snapshot 與綁定產物。

2026-07-13 跨工作流工程整合入口為 `app_module/system_execution_blueprint_adapters.py`，純 JSON 驗證入口為 `scripts/verify_system_execution_blueprint.py`。兩者只組合／驗證 Evidence、PIT／source、ML shadow、dashboard 與 latency 的既有輸出，不改 Recommendation、Score、Advice、Portfolio 或 Exit。任一契約失敗時回到原 owner 修正；禁止在整合層補值、放寬 Gate 或把 `degraded` 改成 ready。

目前 roadmap 判讀已從舊線性 Phase 轉為 Scoped SSOT + Post-V1 版本節奏：目前狀態看 `docs/00_core/PROJECT_SNAPSHOT.md`，產品方向看 `docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md`，未來工程路線看 `docs/00_core/ROADMAP_6M_ENGINEERING.md`，目前／目標架構分別看 `docs/01_architecture/system_architecture.md` / `docs/01_architecture/target_system_architecture.md`；V1.1 至 V2.0 歷史節奏、V2.1 至 V4.0 長期成熟度與外部參考則依任務再讀對應 companion。`docs/05_phases/` 僅保留為歷史 Phase / 設計追溯，不作目前 roadmap。

---

## 2️⃣ 三層架構導航

### 2026-09-06 八卡閉環入口

| 要核對的契約 | 首要入口 |
|---|---|
| 更新／市場日期與品質 DTO | [update_loop_dtos.py](app_module/dtos/update_loop_dtos.py)、[market_loop_dtos.py](app_module/dtos/market_loop_dtos.py)；服務維持舊 API 相容，UI 不查 storage |
| 推薦決策切片／輸入指紋 | [recommendation_service.py](app_module/recommendation_service.py)；`recommendation-context.v1`、未知因子與歷史產業 PIT 拒用 |
| V4.1 歷史研究／候選方法包 | [v41_historical_method_pack.py](app_module/v41_historical_method_pack.py)、[build_v41_historical_method_pack.py](scripts/build_v41_historical_method_pack.py)；逐列 manifest、20／5 walk-forward、gap 分類與 frozen shadow-only artifact |
| T+1 版本撮合／研究成本 | [broker_simulator.py](backtest_module/broker_simulator.py)、[recommendation_portfolio_backtest_service.py](app_module/recommendation_portfolio_backtest_service.py)；v2 與 legacy 隔離 |
| Registry／Evidence lineage | [research_run_service.py](app_module/research_run_service.py)、[evidence_event_service.py](app_module/evidence_event_service.py)；query 不 reconcile，review 僅提案 |
| 候選 append 帳本／副本 migration | [portfolio_ledger_repository.py](data_module/portfolio_ledger_repository.py)、[portfolio_ledger_migration.py](data_module/portfolio_ledger_migration.py)；由 PortfolioService 明確注入，正式 JSONL 未切換 |
| 候選池／Desk 來源鏈 | [watchlist_repository.py](data_module/watchlist_repository.py)、[decision_desk_service.py](app_module/decision_desk_service.py)、[decision_desk_snapshot_repository.py](app_module/decision_desk_snapshot_repository.py)；預設 JSON 未切換，loop payload 保留來源 |
| Runtime 觀測／取消訂閱 | [event_bus.py](app_module/runtime_services/event_bus.py)、[snapshot_service.py](app_module/runtime_services/snapshot_service.py)；EventBus 非 durable queue，未知不當 IDLE |

中央組裝、完整來源 hydrate、QA inventory 與當輪整合結果見 [TASK-08 交接](docs/06_qa/TASK_LOOP_08_HANDOFF.md)；各卡入口由 [文件索引](docs/00_core/DOCUMENTATION_INDEX.md) 導覽。現況／目標差距以 [架構](docs/01_architecture/system_architecture.md) 與 [完整操作手冊](docs/07_guides/APPLICATION_MANUAL.md) 為準。八卡工程不改 V4 Evidence Accumulation／action_required，不啟用正式 writer、scheduler、broker 或 Formal credit。

### UI Layer（`ui_qt/`、`ui_app/`）

**主要入口**：`ui_qt/main.py`（PySide6 Qt UI，推薦使用）

**這一層不該做什麼**：
- 不包含業務邏輯
- 不直接操作數據
- 只負責：收參數、呼叫 Service、顯示 DTO

**Legacy UI**：`ui_app/main.py`（Tkinter UI，僅供參考）

---

### Application Service Layer（`app_module/`）

**這一層負責什麼**：
- Use case 編排（orchestration）
- UI 與 Domain 的解耦橋樑
- 數據轉換（DTO 處理）
- 服務組合（例如：回測服務組合策略執行器、績效分析器）
- 跨工作流只允許以 `system_execution_blueprint_adapters.py` 的中立 DTO／JSON composition 聚合既有輸出；app/runtime 不得反向 import `ml`，pure verifier 不得觸發寫入或 production action

**與 Domain 的關係**：
- 依賴 `decision_module/`，不依賴 `ui_app/`
- 所有業務邏輯都透過 `decision_module/` 取得

---

### Domain Layer（`decision_module/`）

**這一層放什麼**：
- 策略配置器（StrategyConfigurator）
- 股票篩選器（StockScreener）
- 打分引擎（ScoringEngine）
- 推薦理由引擎（ReasonEngine）
- 市場狀態檢測（MarketRegimeDetector）
- 產業映射（IndustryMapper）
- 回測分數門檻策略（ScoreThresholdPolicy）：fixed / Expanding T-1 quantile、60 個有效觀測暖機
- 推薦橫斷面百分位排名（Recommendation Percentile Ranker）：eligible universe empirical CDF

**為什麼它是核心**：
- 所有業務邏輯的實際實作都在這裡
- `app_module/` 服務層完全依賴它
- UI 層透過服務層間接使用它，或主程式直接初始化它

---

### Market Intelligence / Daily Decision Desk Layer（目前位於 `app_module/`）

**目前狀態**：Daily Decision Desk v1 已接上主 UI，唯一實例位於「市場探索 > 市場總覽」，尚未建立獨立 `market_module/`；目前透過 application services / DTO 聚合既有資料，不在 UI 重算 domain logic。

**目前責任**：
- Market Breadth
- Sector Rotation
- Relative Strength / Liquidity Ranking
- Watchlist Trigger
- Daily Decision Desk snapshot
- Portfolio Alert / Attribution
- Why Not / Risk Prompt

**目前替代位置**：
- `decision_module/market_regime_detector.py`
- `decision_module/stock_screener.py`
- `decision_module/industry_mapper.py`
- `decision_module/flow_signal_engine.py`
- `app_module/regime_service.py`
- `app_module/screening_service.py`
- `app_module/broker_flow_service.py`
- `app_module/market_breadth_service.py`
- `app_module/sector_rotation_service.py`
- `app_module/relative_strength_liquidity_service.py`
- `app_module/decision_desk_service.py`
- `app_module/decision_desk_risk_prompt_service.py`
- `app_module/decision_presentation.py`：V4.2 C 線共用唯讀呈現 DTO／adapter；不重算推薦、機率或權重

修改 Daily Decision Desk 時，必須維持 service / DTO 邊界，不能在 UI 直接複製上述 domain 計算。

---

### Evidence / Data Credibility Layer（`app_module/` + `data_module/`）

**目前狀態**：Post-V1 evidence layer、V1.5 data credibility gate、V1.6 cross-sectional factor pipeline、V1.7 screening matrix / negative evidence、Historical Evidence Replay、V2.0 Workbench formal read-only source adapter 與 Phase 2 Workbench background evidence feed / read-only Action Items / read-only Operating Loop 體驗已建立；這一層只保存 / 檢查 research evidence、source coverage、factor attribution、negative evidence、historical replay metadata、Workbench read-only source summary、依 severity / queue group / source 排序的人工待處理事項檢視、daily first-look / manual queue / weekly history / multi-day dry-run / manual review note / scheduler gate 操作節奏與資料政策，不產生投資結論、不啟用 production scheduler。

**主要檔案**：
- `app_module/evidence_event_*`、`app_module/evidence_capture_service.py`、`app_module/evidence_event_importers.py`
- `app_module/forward_performance_service.py`、`app_module/forward_performance_read_model.py`
- `app_module/evidence_pipeline_runner.py`、`app_module/evidence_scheduler_readiness.py`
- `app_module/historical_evidence_replay.py`
- `app_module/pre_v2_readiness_service.py`
- `app_module/agent_evidence_access_service.py`
- `app_module/workbench_source_service.py`
- `app_module/workbench_read_only_composer.py`
- `app_module/workbench_replay_summary.py`
- `app_module/evidence_source_coverage_service.py`
- `app_module/recommendation_service.py`、`app_module/dtos/__init__.py`（Recommendation result screening matrix / payload 保存邊界）
- `app_module/recommendation_calibration.py`
- `app_module/v41_historical_method_pack.py`
- `app_module/cross_sectional_factor_dtos.py`
- `app_module/cross_sectional_factor_repository.py`
- `app_module/cross_sectional_factor_pipeline.py`
- `app_module/cross_sectional_factor_attribution.py`
- `data_module/data_source_capability_registry.py`
- `data_module/corporate_action_policy.py`
- `data_module/microstructure_source_preflight.py`
- `data_module/cross_sectional_factor_migration.py`
- `scripts/inspect_cross_sectional_factor_snapshot.py`
- `scripts/inspect_pre_v2_readiness.py`
- `scripts/replay_historical_evidence_pipeline.py`
- `scripts/inspect_v2_workbench_prototype.py`
- `scripts/inspect_recommendation_calibration.py`
- `scripts/build_v41_historical_method_pack.py`

**如果我要改 evidence source coverage / data credibility**：先看 `docs/00_core/PROJECT_SNAPSHOT.md`、`docs/00_core/VERSION_ROADMAP_V1_1_TO_V2_0.md` 與 `docs/01_architecture/system_architecture.md`；程式改動優先從 `EvidenceSourceCoverageService` 或 `data_module/*policy/*registry` 切入，不要在 CLI、runner 或 UI 各自複製分級邏輯。

**如果我要改 V1.6 factor snapshots / attribution**：先看 `CrossSectionalFactorPipeline`、`CrossSectionalFactorRepository` 與 `scripts/inspect_cross_sectional_factor_snapshot.py`；新增 factor 或 concept metadata 仍必須先經 `FactorGate`、`available_date <= decision_date` 與 missing policy，不要直接改 `ScoringEngine`。

**如果我要改 V1.7 screening matrix / negative evidence**：先看 `RecommendationService`、`RecommendationResultDTO`、`RecommendationEvidenceImporter` 與 `EvidenceSourceCoverageService`；screening matrix 必須來自推薦當下保存的 payload，importer 不可事後重算或回補舊 result，也不可把 fail / degraded 變成自動 lifecycle action。

**如果我要改 Historical Evidence Replay**：先看 `HistoricalEvidenceReplayService`、`EvidencePipelineRunner`、`EvidenceCaptureService` 與 `ForwardPerformanceService`；replay DB 必須與 source DB 分離，recommendation result 必須受 `created_at <= decision_date` 限制，outcome price search 必須受 `data_as_of_date` 限制，replay metadata 必須保留 `historical_replay` / `simulated_scheduler`，且 replay 不得計入 production scheduler approval。

**如果我要做 V4.1 A 線歷史研究／候選方法包**：先看 `app_module/recommendation_calibration.py`、`app_module/v41_historical_method_pack.py` 與 [V4.1 歷史方法包 QA](docs/06_qa/V4_1_HISTORICAL_METHOD_PACK_2026_09_12.md)。使用 `scripts/build_v41_historical_method_pack.py` 以 query-only SQLite 或 deterministic sample 建立逐列 manifest；每列必須保留 decision／available-at、label maturity、strategy／universe identity、return／benchmark／cost、source hash 與 gap codes。20 日是 primary、5 日是 auxiliary；缺成熟 outcome、PIT membership 或 source lineage 時 fail-closed，輸出只可供 B 線 shadow，不能改正式推薦、scheduler 或 promotion。

**如果我要改 V2.0 / V2.1 Workbench read-only source adapter、background evidence feed、Action Items 或 Operating Loop**：先看 `WorkbenchSourceService`、`WorkbenchReadOnlyComposer`、`WorkbenchDashboardDTO`、`PreV2ReadinessService` 與 `AgentEvidenceAccessService`；adapter 只能讀受控 DB path / replay JSON summary，missing DB / table 要變成 diagnostics。背景證據流只能彙整既有 DTO / service payload；Action Items 只能顯示人工待處理事項，必須保留 severity / queue group / source label / source trace / degraded reason / sort rank / drill-down target。Operating Loop 只能從 DTO payload 串接 daily first-look、manual queue、weekly history、multi-day dry-run、manual review note 與 scheduler gate，必須保留 source trace / linked item ids / drill-down target / `write_intent=false`。首頁「今日行動中心」也只能讀這些既有 DTO，並只透過既有 drill-down callback 導向數據更新、Daily Decision、推薦分析或持倉管理；不得自行推導投資結論、寫 DB、更新資料或觸發任何 domain action。`AdaptiveWorkspaceStack` 只處理目前可見 workspace 的尺寸提示，不能改變 workspace registration、widget ownership 或資料載入。Evidence current 顯示必須同時區分 formal/canonical credit 未授予、歷史 working-copy 1/3、owner-approved UI projection 3/3、pending sidecar 10 與 multi-day 3/3；`formal_credit_authorized=false`、multi-day ready 不構成 scheduler approval，fixture／手動改表／replay 也不得補 official Gate。Drill-down target 必須對齊 Daily Decision、Evidence Review、Portfolio 舊頁導向，空狀態與 degraded 狀態文案不得暗示 gate passed、補值或建議，且不得建立 repository、寫 DB、讀 UI state、重算 scoring / portfolio / backtest、啟用 scheduler、套用 lifecycle 或產生交易建議。

**如果我要改 Workbench > Evidence / Research Console**：先看 `app_module/research_console_dtos.py`、`app_module/research_console_source_service.py`、`ui_qt/views/research_console_view.py` 與三個 `tests/test_*research_console*`。Source service 只可讀 injected sanitized mapping 或顯式 projection path；MainWindow 以 `RESEARCH_CONSOLE_PROJECTION` 注入，不可自動掃描 development／正式資料目錄。View 只能複製 DTO，必須維持 formal OOS false、production alpha 0、Rule-only formal path、P0-13 與 Broker lane 分離，以及所有 apply / promote / retrain / trade 控制不存在。

---

### AI Runtime Subsystem (`runtime/`)

**這一層負責什麼**：
- Governance-aware AI 執行環境與狀態管理
- FSM Lifecycle (IDLE -> THINKING -> VALIDATING -> APPROVED/ERROR/HALTED)
- DTO-first contracts 與 Append-only Audit Log
- 作為 AI-Native OS 的核心運作層，與 UI/Orchestration 解耦

**為什麼重要**：
- 保證 AI Agent 運作時的 Explainability 與 Governance
- 隔離 LLM Frameworks 與系統核心業務邏輯的污染
- 讓所有狀態流轉變得 Observable

---

### Gate 1 Advice 導航

Gate 1 的 application contract 依序為 `app_module/advice_dtos.py`、`app_module/advice_policy.py`、`app_module/advice_composer.py`，再經 `app_module/workbench_dtos.py`、`app_module/workbench_read_only_composer.py` 到 `ui_qt/views/workbench_view.py` 與 `ui_qt/models/workbench_table_models.py`。Policy / Composer 只接受注入 payload；UI 只呈現 `AdviceDashboardDTO`。變更時維持 `data_as_of_date <= decision_date`、source trace、整數 bp / `Decimal`、`2000/8/1500 bp` 限制及 Guided Mode fail-closed，禁止 DB write、核心重算、broker、scheduler 與 lifecycle action。

## 3️⃣ 專案主要入口

### ✅ 主要啟動方式（推薦）

```bash
python ui_qt/main.py
```

**這是什麼**：PySide6 Qt 圖形界面，包含 9 個頂層工作區：決策工作台、市場探索、推薦分析、策略回測、觀察清單、個股研究、持倉管理、數據更新、系統狀態。個股研究內嵌於主程式；Daily Decision Desk 不另佔頂層工作區；唯一實例位於「市場探索 > 市場總覽」，Workbench 只提供導覽。

---

### ⚠️ Legacy 啟動方式（僅供參考）

`ui_app/main.py` 是舊 Tkinter UI 的歷史入口，不作為目前安裝、操作、驗證或新功能開發依據。需要目前 UI 請使用 `ui_qt/main.py`。

---

### 已移除的舊入口

- `examples/main_example.py` 與 `recommendation_module_legacy/` 已於 2026-07-12 完成 consumer 歸零並移除；不要再以歷史路徑啟動或引用。

---

## 4️⃣ 「我要做 X，要去哪裡看？」功能導航

### 📌 Data Update（數據更新）

**從哪個 UI 進**：`ui_qt/views/update_view.py`（數據更新 Tab）

**對應的 Service**：`app_module/update_service.py`
- 負責：數據狀態檢查、更新流程編排

**目前 UI 形態**：
- `UpdateView` 已整理為維運工作台式布局：左側導覽、上方狀態摘要、右側資料來源頁、底部共享日誌與進度
- 日常維護建議使用「安全更新所有數據」，保守依序執行狀態檢查、每日股價、大盤指數、產業指數、券商分點、每日合併與技術指標計算
- 單一來源維護仍可從左側導覽切換到每日股價、大盤指數、產業指數、券商分點、技術指標或進階維護

**真正動邏輯的地方**：
- `scripts/batch_update_daily_data.py`：批量更新每日股票數據
- `scripts/merge_daily_data.py`：合併數據到 meta_data
- `scripts/batch_update_market_and_industry_index.py`：更新市場/產業指數
- `scripts/calculate_technical_indicators.py`：計算技術指標
- `app_module/broker_branch_update_service.py`：券商分點資料抓取、標準化與合併

**如果我要改數據更新邏輯**：先看 `app_module/update_service.py`，再看對應的腳本檔案。如果要改 SQLite 資料檢視器分頁或查詢邏輯，看 `app_module/sqlite_inspector_service.py` 與 `ui_qt/widgets/sqlite_inspector_widget.py`。

---

### 📌 Market Exploration（市場探索）

**從哪個 UI 進**：左側「市場探索」；「市場總覽」是 Daily Decision Desk 唯一實例，其他市場視圖位於 `ui_qt/views/`。
- `market_regime_view.py`：大盤指數
- `strong_stocks_view.py`：強勢個股
- `weak_stocks_view.py`：弱勢個股
- `strong_industries_view.py`：強勢產業
- `weak_industries_view.py`：弱勢產業

**對應的 Service**：
- `app_module/screening_service.py`：強勢/弱勢股篩選
- `app_module/regime_service.py`：市場狀態檢測

**真正動邏輯的地方**：
- `decision_module/stock_screener.py`：股票篩選邏輯（強勢/弱勢判斷）
- `decision_module/market_regime_detector.py`：市場狀態判斷（Trend/Reversion/Breakout）
- `decision_module/industry_mapper.py`：產業映射與產業指數處理

**如果我要改市場觀察邏輯**：先看 `app_module/screening_service.py` 或 `app_module/regime_service.py`，再看 `decision_module/` 對應的檔案。

**如果我要做 Daily Decision Desk / Market Breadth / Watchlist Trigger**：先看 `docs/01_architecture/system_vision_specification.md` 與 `docs/00_core/ROADMAP_6M_ENGINEERING.md` 的 Month 4；實作前先設計 `DecisionDeskSnapshot` / service 邊界，不要直接在 UI 層重算。

---

### 📌 Smart Money Terminal（市場探索子頁）

**從哪個 UI 進**：左側「市場探索」內的主力流向子頁；實作為 `ui_qt/views/smart_money/smart_money_flow_view.py`。

**對應的 Service**：`app_module/broker_flow_service.py`
- 負責：提供籌碼流向資料編排與查詢

**真正動邏輯的地方**：
- `decision_module/flow_signal_engine.py`：籌碼信號判斷邏輯（過濾、強度計算）
- `ui_qt/views/smart_money/terminal_delegate.py`：負責 UI 渲染細節（Row Intensity、Sparklines、Badges），不包含業務邏輯

**如果我要改籌碼邏輯**：
- 改信號或演算法判斷 → `decision_module/flow_signal_engine.py`
- 改畫面長相（顏色、趨勢線渲染） → `ui_qt/views/smart_money/terminal_delegate.py`

---

### 📌 Recommendation（推薦分析）

**從哪個 UI 進**：`ui_qt/views/recommendation_view.py`（推薦分析 Tab）

**對應的 Service**：`app_module/recommendation_service.py`
- 負責：策略配置編排、推薦結果生成、結果保存
- 推薦 Tab 也能把目前 Profile/Config 送到 Backtest Tab 的「推薦組合回測」，由回測頁在歷史日期重播推薦邏輯。

**真正動邏輯的地方**：
- `decision_module/strategy_configurator.py`：策略配置（技術指標、圖形模式設定）
- `decision_module/scoring_engine.py`：打分引擎（統一打分模型，0-100 分）
- `decision_module/indicator_parameter_registry.py`：指標參數 schema、版本、alias 與 Fail-Closed 驗證
- `decision_module/weight_contract.py`：推薦權重整數 bp 契約與 legacy migration
- `decision_module/recommendation_percentile_ranker.py`：推薦 eligible universe 橫斷面百分位

**門檻模式**：
- `fixed`：維持既有總分排序與 `top_n`
- `quantile`：先建立 eligible universe，再依 empirical CDF 百分位篩選；母體不足時拒絕降級
- `decision_module/reason_engine.py`：推薦理由生成（Why / Why Not）

**如果我要改推薦邏輯**：
- 改策略配置 → `decision_module/strategy_configurator.py`
- 改打分邏輯 → `decision_module/scoring_engine.py`
- 改推薦理由 → `decision_module/reason_engine.py`
- 改推薦結果 Excel 匯出 → `app_module/report_export_service.py` / `app_module/report_export_dtos.py`

---

### 📌 Backtest / Research Lab（策略回測 / 研究實驗室）

> 「策略回測」是頂層 Tab 名稱，「Research Lab」是其產品語意，支援單股回測、批次股票回測、固定組合回測、推薦系統回放與策略研究。

**從哪個 UI 進**：`ui_qt/views/backtest_view.py`（策略回測 Tab）

**對應的 Service**：
- `app_module/backtest_service.py`：單次回測
- `app_module/batch_backtest_service.py`：批次回測；負責 ProcessPool 工作分派、bounded in-flight queue、合作式取消與主行程集中保存
- `app_module/recommendation_replay_service.py`：歷史日期重播推薦邏輯
- `app_module/recommendation_portfolio_backtest_service.py`：推薦組合資金配置、持有期與績效彙整
- `app_module/recommendation_dataframe_provider.py`：推薦 replay 用資料提供與候選集 prefilter
- `app_module/recommendation_portfolio_dates.py`：台股資料日期解析工具，避免數字型 `YYYYMMDD` 誤判
- `app_module/walkforward_service.py`：Walk-forward 驗證
- `app_module/optimizer_service.py`：參數最佳化；使用 ThreadPool 與合作式取消
- `app_module/research_run_service.py`：Research Run Registry 保存 owner，協調 SQLite metadata、Parquet 明細、hash 與 crash reconciliation
- `app_module/research_run_repository.py`：Research Run SQLite schema、查詢、archive / promoted guard
- `app_module/research_run_legacy_adapter.py`：legacy Backtest / Recommendation Portfolio run 匯入 registry 的轉接層
- `app_module/research_run_comparison_service.py`：Registry run comparability、正規化 equity 交集與 benchmark attribution 比較
- `app_module/promotion_reconciliation_service.py`：Registry-based promote gate、Month 6 lifecycle gate、JSON Strategy Version 補償交易、applied lifecycle evidence 與 reconciliation 掃描
- `app_module/strategy_lifecycle_service.py`：Promote / hold / demote / retire rule engine、StrategyDriftDetector 與 Regime compatibility
- `app_module/strategy_lifecycle_repository.py`：append-only lifecycle evidence、current state projection 與 demote / retire proposed evidence 保存
- `app_module/exceptions.py`：跨服務共用的取消例外

**真正動邏輯的地方**：
- `backtest_module/strategy_tester.py`：策略測試器（執行策略邏輯）
- `backtest_module/performance_analyzer.py`：績效分析器（計算績效指標）
- `backtest_module/performance_metrics.py`：績效指標計算（包含 Walk-Forward 退化、一致性、過擬合風險）
- `backtest_module/broker_simulator.py`：券商模擬器（模擬交易執行）
- `decision_module/strategies/`：策略契約、唯一 registry 與策略執行器 owner；舊 `app_module/strategies/` 僅為 `TMP-STR-01` 薄相容 facade

**如果我要改回測邏輯**：
- 改回測流程 → `app_module/backtest_service.py`
- 改推薦組合歷史重播 → `app_module/recommendation_replay_service.py` / `app_module/recommendation_portfolio_backtest_service.py`
- 改績效計算 → `backtest_module/performance_metrics.py`
- 改策略執行 → `decision_module/strategies/` 對應的執行器
- 改 Walk-Forward → `app_module/walkforward_service.py`
- 改報告匯出或 Excel 結構 → `app_module/report_export_service.py` / `app_module/report_export_dtos.py`
- 改研究結果保存、hash、archive 或 legacy backfill → `app_module/research_run_service.py` / `app_module/research_run_repository.py` / `scripts/backfill_legacy_runs.py`
- 改跨 run 比較、comparability 或 benchmark attribution → `app_module/research_run_comparison_service.py` / `ui_qt/views/research_lab/run_registry_compare_widget.py`
- 改 registry-based promotion、補償交易或 reconciliation → `app_module/promotion_reconciliation_service.py` / `app_module/strategy_version_service.py`

**如果我要改回測圖表 / 視覺化**：
- 改圖表資料轉換 → `ui_qt/widgets/chart_payloads.py`
- 改 fast Canvas 渲染 → `ui_qt/widgets/fast_chart_widget.py`
- 改 Backtest Tab 圖表掛載 → `ui_qt/views/backtest_view.py`
- 查架構說明 → `docs/08_technical/UI_QT_CHART_RENDERING.md`
- 注意：fast widgets 透過 factory 建立；QtWebEngine 不可用時會 fallback 到 `ui_qt/widgets/chart_widget.py` 的 Matplotlib widgets。

**特殊功能**：
- **Walk-Forward 暖機期**：`app_module/walkforward_service.py` 的 `warmup_days` 參數
- **Baseline 對比**：`backtest_module/performance_metrics.py` 的 `calculate_baseline_comparison()`
- **過擬合風險提示**：`backtest_module/performance_metrics.py` 的 `calculate_overfitting_risk()`
- **Research Run Registry**：保存入口由 `ResearchRunService.save_run()` 負責；Cross-run Comparison 與 Registry-based Promote 已完成 Month 2 M2-C 第一版。Registry save 仍不等同策略升級，promotion 必須通過 registry gate、Month 6 lifecycle gate、Strategy Version JSON 補償交易、lifecycle evidence 與 reconciliation 防線。

---

### 📌 Agent / Codex / Antigravity 指引

**Codex 自動讀取入口**：`AGENTS.md`

**Agent / 開發者快速上下文**：`AGENT_CONTEXT.md`

**Antigravity 自動讀取入口**：`GEMINI.md`

**Antigravity 輔助規則**：`.agent/rules/`

**完整 Agent 架構**：`docs/agents/`

**使用規則**：
- Codex 會讀取 repo 根目錄 `AGENTS.md`。
- `AGENT_CONTEXT.md` 補充分支策略、文件權威與開發導覽；它不是強制規則，強制規則仍以 `AGENTS.md` 與 `docs/agents/` 為準。
- Antigravity 會讀取 repo 根目錄 `GEMINI.md`，並可搭配 `.agent/rules/` 的任務規則。
- `docs/agents/` 保存完整 Agent 職責、Prompt 與共用上下文，但不會單靠檔名自動成為 Codex 指令入口。
- 資料路徑請以 `data_module/config.py` 的 `TWStockConfig` 與 `DATA_ROOT` 為準，不要假設 repo 內一定存在正式 `data/` 目錄。

---

### 📌 Portfolio（持倉管理）

**目前狀態**：Portfolio 閉環已建立且完成主要深化：Portfolio Tab、domain/service/test、Recommendation/Backtest 來源追溯 metadata、策略與價格監控、生命週期回顧、目前價格對照、未實現損益、停損停利警示、籌碼監控與 Smart Money 下鑽皆已完成。V1.8 另新增 research-only portfolio construction / virtual execution trace sandbox；它只做研究配置與虛擬事件，不是正式持倉帳務或下單入口。V1.9 已新增 read-only Agent / MCP evidence access；它只查 evidence rows、quality、warnings 與 source trace，不寫 DB、不改策略、不下單。

**從哪個 UI 進**：`ui_qt/views/portfolio_view.py`（持倉管理 Tab）

**對應的 Service**：
- `app_module/portfolio_service.py`：Portfolio use case 編排
- `app_module/portfolio_condition_monitor.py`：條件監控（來源快照 vs 目前快照 Regime/TotalScore 對照）
- `app_module/decision_presentation.py`：把既有 Advice／Condition Monitor／持倉來源摘要投影成共用動作、權重與失效條件欄位
- `app_module/portfolio_chip_service.py`：持倉層籌碼監控與分點資料彙整
- `app_module/portfolio_feedback_service.py`：持倉 post-trade attribution / live-vs-research gap
- `app_module/portfolio_review_service.py`：Portfolio Review dashboard snapshot
- `app_module/portfolio_construction_service.py`：V1.8 research-only allocation / constraints / lot sizing sandbox
- `app_module/paper_portfolio_policy.py`：V2.4 核准紙上政策的唯讀再平衡判讀；只輸出 candidate / 拒絕理由，不讀持倉、不寫 DB、不下單
- `app_module/position_health_service.py`：V2.5 持倉健康狀態投影；只輸出 HEALTHY / WATCH / EXIT_CANDIDATE，不自動減碼或平倉
- `app_module/portfolio_execution_trace_service.py`：V1.8 virtual order lifecycle trace（created / submitted / partially_filled / filled / rejected）
- `app_module/agent_evidence_access_service.py`：V1.9 read-only Agent evidence access service
- `mcp_servers/evidence_access_server.py`：V1.9 `twstock-evidence-access` MCP server
- `app_module/journal_service.py`：交易/決策紀錄服務

**真正動邏輯的地方**：
- `portfolio_module/`：Portfolio MVP domain layer

**如果我要改持倉管理邏輯**：
- 改 domain 規則 → `portfolio_module/`
- 改服務編排 → `app_module/portfolio_service.py`
- 改條件監控 → `app_module/portfolio_condition_monitor.py`
- 改生命週期回顧 / post-trade attribution → `app_module/portfolio_feedback_service.py` / `app_module/portfolio_review_service.py`
- 改研究配置 sandbox → `app_module/portfolio_construction_service.py` / `app_module/portfolio_execution_trace_service.py`
- 改 UI → `ui_qt/views/portfolio_view.py`

---

### 📌 Watchlist（觀察清單）

**從哪個 UI 進**：`ui_qt/views/watchlist_view.py`（觀察清單 Tab）

**對應的 Service**：`app_module/watchlist_service.py`
- 負責：跨 Tab 共用候選池管理、JSON 持久化
- `app_module/watchlist_analysis_service.py`：唯讀取回保存推薦的分數、樣本與來源 metadata
- `app_module/decision_presentation.py`：觀察清單與研究報告共用呈現契約

**真正動邏輯的地方**：
- `app_module/watchlist_service.py`：觀察清單的完整邏輯都在這裡（沒有 Domain 層依賴）

**如果我要改觀察清單邏輯**：直接看 `app_module/watchlist_service.py`。

---

### 📌 AI Runtime Observatory (狀態機監控站)

**從哪個 UI 進**：`ui_qt/views/runtime_view.py`（Runtime Observatory Tab）

**對應的 Service**：
- `app_module/runtime_services/runtime_controller.py`
- `app_module/runtime_services/snapshot_service.py`
- `app_module/runtime_services/health_service.py`
- `app_module/runtime_services/event_bus.py`

**真正動邏輯的地方**：
- `runtime/store/local_file_store.py`：所有事件與狀態的實際 I/O 儲存。
- `ui_qt/bridges/runtime_event_bridge.py`：唯一的 Qt Signal 轉譯點。

**如果我要改 Runtime 邏輯**：
- 改 DTO 或 FSM 狀態 → `app_module/dtos/runtime_dtos.py`
- 改指標計算 → `app_module/runtime_services/health_service.py`
- 改架構規範 → 查閱 `docs/01_architecture/runtime_observatory_rules.md`

---

## 5️⃣ ⚠️ 高風險核心檔案（Do Not Touch Blindly）

### `decision_module/scoring_engine.py`
**為什麼風險高**：統一打分模型的核心，所有推薦分數都從這裡計算，改動會影響所有策略。

### `decision_module/strategy_configurator.py`
**為什麼風險高**：策略配置的核心，定義所有技術指標和圖形模式的參數，改動會影響所有推薦結果。

### `backtest_module/performance_metrics.py`
**為什麼風險高**：所有回測績效指標的計算邏輯，包含 Walk-Forward 退化、一致性、過擬合風險等核心計算。

### `app_module/backtest_service.py`
**為什麼風險高**：回測流程的編排核心，整合策略執行器、績效分析器、券商模擬器，改動會影響所有回測結果。

### `app_module/walkforward_service.py`
**為什麼風險高**：Walk-Forward 驗證的核心邏輯，包含暖機期處理、訓練/測試期分割，改動會影響驗證結果。

### `backtest_module/broker_simulator.py`
**為什麼風險高**：模擬交易執行的核心，包含手續費、滑價、停損停利等邏輯，改動會影響所有回測的實際交易模擬。

### `decision_module/stock_screener.py`
**為什麼風險高**：強勢/弱勢股篩選的核心邏輯，改動會影響市場觀察的所有結果。

### `decision_module/market_regime_detector.py`
**為什麼風險高**：市場狀態判斷的核心，改動會影響所有依賴 Regime 的策略和推薦。

### `data_module/config.py`
**為什麼風險高**：所有數據路徑和配置的核心，改動會影響整個系統的數據存取。

### `app_module/recommendation_service.py`
**為什麼風險高**：推薦分析的編排核心，整合策略配置、打分、理由生成，改動會影響所有推薦結果。

---

## 6️⃣ Legacy / Historical 區塊

### `ui_app/` 目錄

**角色**：Legacy Tkinter UI

**狀態**：
- 業務邏輯已遷移到 `decision_module/`
- 僅保留 Tkinter UI 相關代碼
- 不保證 Legacy UI 與目前 9 個工作區、資料契約或使用手冊同步

**使用建議**：新功能不應再引用 `ui_app/` 中的業務邏輯檔案（如 `strategy_configurator.py`、`stock_screener.py` 等），這些檔案已不存在或已遷移。

---

### 不應再被新功能引用的模組

- `ui_app/` 中的業務邏輯檔案（已遷移到 `decision_module/`）
- 舊版推薦引擎與 `examples/main_example.py` 已於 2026-07-12 完成 consumer 歸零並移除；推薦入口統一使用 `app_module/recommendation_service.py`

---

## 📚 相關文檔

- **目前狀態快照**：`docs/00_core/PROJECT_SNAPSHOT.md`
- **產品方向**：`docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md`
- **6 個月工程路線**：`docs/00_core/ROADMAP_6M_ENGINEERING.md`
- **目前／目標架構**：`docs/01_architecture/system_architecture.md` / `docs/01_architecture/target_system_architecture.md`
- **V1.1 至 V2.0 版本節奏**：`docs/00_core/VERSION_ROADMAP_V1_1_TO_V2_0.md`
- **V2.1 至 V4.0 長期版號階梯**：`docs/00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md`
- **baldr 產品北極星**：`docs/01_architecture/system_vision_specification.md`
- **Roadmap Hub**：`docs/00_core/DEVELOPMENT_ROADMAP.md`
- **舊 Roadmap 移交矩陣**：`docs/00_core/LEGACY_ROADMAP_CARRYOVER.md`
- **完整操作手冊**：`docs/07_guides/APPLICATION_MANUAL.md`
- **專案盤點報告**：`PROJECT_INVENTORY.md`（完整的專案結構盤點，與本文檔同層）
- **文檔索引**：`docs/00_core/DOCUMENTATION_INDEX.md`（所有文檔的索引）
- **External Evidence 執行入口**：`docs/superpowers/plans/2026-07-13-oos-exposure-custody-audit-execution-plan.md`
- **Terra 執行交接**：`docs/superpowers/prompts/2026-07-13-terra-external-evidence-execution-handoff.md`
- **歷史 Phase 設計追溯**：`docs/05_phases/README.md`（Historical / Reference，不作目前 roadmap）

---

**文件結束**

## 券商分點雙指標資料流

- 抓取與合併：`app_module/broker_branch_update_service.py`
- CSV 到 SQLite：`app_module/update_service.py`
- SQLite schema：`data_module/db_manager.py`
- Smart Money 張數讀取：`app_module/broker_flow_service.py`
- Portfolio Phase 4.2：`app_module/portfolio_chip_service.py`

資料契約：`c=E` 寫入張數，`c=B` 寫入仟元金額；legacy `buy_qty` 不得當張數。



## 更新記錄

- 2026-09-06：新增八卡 DTO／服務／儲存與整合交接導航，保持正式資料及 V4 外部 Gate。


## 2026-10-05 原排名研究導航

入口：每日研究條件的日／週及強／弱選項 → 相容不可變原排名 → 研究母體盤勢同源呈現。發布CLI為scripts/publish_original_stock_ranking.py；backend app_module/original_stock_ranking.py；呈現ui_qt/original_ranking_presentation.py。原feature／舊收藏不改，未提供來源未知。[操作](docs/07_guides/APPLICATION_MANUAL.md)、[QA及限制](docs/06_qa/UX18_ORIGINAL_STOCK_RANKING_PUBLISHER_20261005.md)。

- 2026-10-05 更新：新增原排名有限工程入口及接受邊界。

## 2026-10-05 原排名收藏與個股來源版本化（最新限定收尾）

已完成原排名選股→個股原排名／原 feature→版本化收藏→新程序 pinned 讀回→精確返回原收藏。v2 保存四模式、實際比較窗、原母體／方法／hash／排序／所選股；舊非 rank v1 內容與 bookmark/query/payload 雜湊不變，沒有真實清單遷移。缺件／錯版本／日期／股號／hash／來源修訂顯示原因，可明確另開最新個股研究，保留原證據。完整 Top/Bottom 字串照原 publisher 顯示，3–5 筆週 fallback 明示實際日期與非完整週，不反推 score／勝率。 入口：daily_market_research_bookmark.py 的 v2 factory／dispatch、original_stock_ranking.py 的 pinned reader、watchlist_service.py 的同 ledger 儲存、StockReport service／view 與 Main 路由。 [操作](docs/07_guides/APPLICATION_MANUAL.md)、[限定 QA](docs/06_qa/UX18_RANK_BOOKMARK_SOURCE_VERSIONING_20261005.md)。


## 2026-10-05 UX19 有界儲存與發布復原延伸

本批唯讀參照盤點與 dry-run 不提供永久刪除授權；歷史 manifest／artifact／v1-v2 收藏參照保留，未知 schema、缺件、來源不完整及超預算採保守保留。排名首次發布的缺件指標 CAS 與隔離跨程序復原收據、容量時點政策及驗證結果見 [限定收尾收據](docs/06_qa/UX19_STORAGE_AND_PUBLICATION_RECOVERY_20261005.md)。未改原引擎／排名／方法／日期，未重跑既有真實 publisher 或 ML。

真實 MainWindow 九工作區在空資料、隔離配置、offscreen 子程序最小啟動／正常關閉通過（PID 23772，worker 0，guard 無違規）；這不替代帶正式資料的 App 功能、Native 或真人驗收。其他 consumer／完整方法字典／正式母體與排程／其他 writer 生命周期／長期自然成長仍是工程待辦；Backtest18.62%／20%保持未達，來源 availability／PIT／自然資格另列。使用者其他對話的容量／Evidence 變更保留且不納入本批提交，中央政策以時點 pin 為準。


## 2026-10-05 UX09 有界 MA 名單入選歷程

既有兩條 MA 三態快照經純比較模型、有限歷史 reader 與背景 UI 呈現本次新入選／持續符合／重新入選／未再符合，並保存前次日期、理由與可回放來源身份；不是策略升降級服務。無效／缺件／漏日／同日修訂／版本或母體變更及回填保持未知，不在刷新時寫事件。日曆只讀現有快取，publication 前可得性核驗；現有真實來源只有同日，不能作跨日自然歷程證明。

此為原計畫 §8.1／UX09 的研究讀取切片；不更換母體權威或舊標籤、不啟動自然 capture／outcome 階段5，不宣告首版完成。完整方法字典、其他 consumer 融合、正式母體／排程與其他 writer 生命周期仍是工程待辦，Backtest18.62%／20%不變；Native與真人驗收另待桌面時段。詳見 [UX09 限定收據](docs/06_qa/UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md)。


## 2026-10-05 UX09 歷史索引／分頁與有限版本復原（最新）

長期保存的研究manifest以可重建SQLite派生索引查詢，32 refs／頁、固定來源／query／generation游標、64頁滑動導航窗口且可持續向更早頁讀取。背景history／explicit rebuild保持當期個股與篩選主線可用；schema／來源／hash／cancel／故障不偽造完整，原immutable來源／舊收藏不遷移。索引最多64MiB，每頁串流重核全index SHA及頁內原manifest/artifact，年度calendar以4096entries／32MiB逐份驗證，不再32份正常累積即整批未知。

限定受影響79個不重複案例、Workbench85、validator25／4skip、mypy788、11變更Python編譯與精度／未來函數guard通過。真實已保存三股來源隔離offscreen回放：晚發布仍unknown、17來源hash與正式DBsize/mtime不變、worker0；沒有讀正式DB去重核current identity。130日×2修訂合成metadata全260refs走9頁，index159744 bytes、最大page JSON13814 bytes／tracemalloc1226583 bytes；不當自然樣本或正式長期總容量證明。

本包關閉UX09索引／分頁／索引程式內版本復原；第一版工程剩餘固定F1–F4，詳細終點與owner見收據。Backtest18.62%／20%仍差1.38百分點，不重測湊數或放寬。舊1477 Native已在6691ec78通過，較早「仍待1477」文字由此更正；新分頁／跨頁Native及3–5位真人另驗。1000×835 outer／125%已接受，不新增1000×800硬門檻。具名full-cohort與原完整Top/Bottom標籤沿現況，官方全市場／新百分位方法只有擴充時才要明確決定，不阻塞目前研究限定工程。

完整操作與排錯見 APPLICATION_MANUAL 的歷史索引小節；[詳細驗證、來源選項與F1–F4凍結清單](docs/06_qa/UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md)。

程式入口：`app_module/research_membership_history_index.py`、`research_membership_history_view.py`；CLI：`scripts/manage_membership_history_index.py`；測試：`test_research_membership_history_index.py`、`test_ux09_history_recovery_consumers.py`、`test_ux09_history_browse_view.py`、`test_membership_history_cli.py`。


- 2026-10-05：[F2／F3 原市場共享來源及已開能力矩陣](docs/06_qa/F2_F3_SHARED_CONSUMERS_AND_CAPABILITIES_20261005.md)，A／A 限定完成；F1／F4 與新 Native／真人另列。


- 2026-10-05：[F4跨頁整合與資源終驗](docs/06_qa/F4_RELEASE_INTEGRATION_AND_RESOURCE_ACCEPTANCE_20261005.md)：actual三程序雙收藏讀回通過；20-session實測有效，120/250長保留因二次payload超現有預算blocked，F4未全關閉；F1／新Native／真人另列。

- 2026-10-05：[F4項目revision儲存與20／120／250實測](docs/06_qa/F4_ITEM_REVISION_STORAGE_AND_RETENTION_20261005.md)：新v3長留存與actual App通過，原預算不變；正式舊SQLite COW converter與切換仍待工程／核准。

- 2026-10-05：[F4 SQLite COW converter／明示activation終驗](docs/06_qa/F4_SQLITE_COW_CONVERTER_AND_ACTIVATION_20261005.md)：隔離工程完成；20→21→rollback20保留雙庫與target新歷史。正式store/mode與使用者apply批准另列，不讀真實JSON、不初始化缺失DB。


- 2026-10-05：[F4 Legacy JSON COW／原升級入口終驗](docs/06_qa/F4_LEGACY_JSON_COW_AND_ACTIVATION_20261005.md)：單JSON至獨立v3、新程序讀回及rollback保留新內容；正式apply另行批准，F1例外尚未批准，UX07未啟動。


- 2026-10-06：[個人觀察清單整合](docs/06_qa/PERSONAL_STORAGE_SEPARATION_LANE_20261005.md)：`app_module/personal_watchlist_service.py` 選擇服務，`personal_data_paths.py` 私人控制路徑與 CSV export manifest，config／App／CLI／候選池明示啟用；正式遷移未執行。


- 2026-10-06：[UX10 MA研究方法符合度](docs/06_qa/UX10_MULTI_METHOD_LANE_20261006.md)：`app_module/multi_method_research_consensus.py` 純readmodel／pinned adapter；每日研究名單沿同accepted快照呈現方法與家族counts，不增加排序分數或新方法。


- 2026-10-06：[Journal 個人路徑及 UI composition](docs/06_qa/PERSONAL_JOURNAL_LANE_20261006.md)：`personal_journal_paths.py` 明示 selector／JSONL adapter；config → Main writer/controller、Workbench continuity、推薦 Personalization 與 outcome journey。模式獨立 watchlist，未設定仍保留相容 writer；正式位置／migration 未批准。


2026-10-06：回測策略設定新增按需版本化規則說明（ui_qt/widgets/strategy_rule_card_dialog.py），唯讀目前Spec，不連既有run；操作及限制見docs/07_guides/APPLICATION_MANUAL.md，UX11仍partial。


2026-10-06：研究Registry新增單筆保存結果／規則来源核對，app_module/saved_strategy_rule_card.py＋既有RunRegistryCompareWidget；QA見docs/06_qa/UX11_SAVED_RESULT_RULE_READBACK_20261006.md。

### 2026-10-06 UX20 單批 MA 樣本限定整合

既有隔離 MA CLI 明示保存完整 matched/notmatched/unknown/excluded 單批capture＋receipt，再按原pin唯讀核對readiness；既有MA頁只呈現當期完整控制組投影並明示尚未保存。included≤16、超限拒絕；未知availability/calendar/outcomes不補PIT或訓練資格。Stage5／UX20 partial，多批parent／排程與Outcome接線仍是工程待辦。QA：`docs/06_qa/UX20_SAMPLE_CAPTURE_INTEGRATION_20261006.md`；操作以Manual同日章節為準。個人儲存／Journal程式已整合，只有正式migration／activation未做。


### 2026-10-06 UX20 多批母體有限整合

具名parent manifest已沿既有query-only source／producer／capture／readiness完成多批保存、新程序讀回、取消／失敗／安全重試；每批included≤16，完整母體最多16批，缺批與途中來源／方法改變不能complete。producer發布狀態與sample捕捉狀態分開，uncaptured另列。UI未改；Stage5／UX20仍partial，固定時鐘／排程留存、Outcome H5/10/20與母體UI瀏覽仍待工程；官方available-at／日曆及自然成熟另待證據。操作依APPLICATION_MANUAL最新多批章；收據：docs/06_qa/UX20_PARENT_CAPTURE_INTEGRATION_20261006.md。


### 2026-10-06 UX20 保存母體收據瀏覽

每日研究條件新增明示選取parent receipt的背景唯讀視窗，沿原writer/readiness核對；首屏列母體／資料日／方法、完整／uncaptured與每批producer/capture結果，技術身份折疊。重複點擊／取消／返回／stale回應不重跑producer或套舊資料；readiness拒絕時保留已驗envelope的發布記錄，母體資格未確認。15 offscreen測試、Workbench85、validator25/4skip、mypy806+final targeted2通過。Stage5／UX20保持partial；固定觀測日policy、漏日／修訂接受與owner容量部署仍待工程，UX21獨立lane未接受。QA：docs/06_qa/UX20_PARENT_RECEIPT_UI_20261006.md；操作依Manual最新章。


### 2026-10-06 UX20 固定觀測日接受限定完成

既有parent receipt→原readiness→child exact資料日→固定cutoff/窗口/expected dates接受policy→共用atomic writer→新程序唯讀日報已接線；隔離CLI預設preview，--accept明示保存。缺目標資料日不能借latest或前日補完整，同日不同revision保舊、相同policy/parent冪等、failure/partial安全重試。23不同案例、targeted mypy2/compile3/quant/diffcheck通過；UI未改不重跑前批gates。Stage5／UX20仍partial；正式daily owner/Task/cadence監控／容量留存部署與官方來源治理仍待工程/決策，UX21三檔獨占未接受。操作依Manual最新章與Supplements，QA：docs/06_qa/UX20_OBSERVATION_DAY_ACCEPTANCE_20261006.md。


### 2026-10-06 UX20 隔離daily owner可執行整合

新增明示runtime/target日期的isolated daily runner，直接沿既有producer/parent/observation接受串全鏈，preflight為預設；capacity/quota先檢，有限retry/合作cancel/漏日與revision監控，exact receipt重用。source/日期/配置一致才完成，producer已發布與capture拒絕分列保留；未配置不選生產值。17不同案例＋最後source/config兩例重核、targeted mypy2/compile3/quant通過；UI未改。Stage5/UX20仍partial，正式date-owner/calendar/Task/ACL/留存治理待工程/決策；UX21三檔未整合。QA：docs/06_qa/UX20_DAILY_OWNER_ISOLATED_20261006.md；操作依Manual。


### 保存母體 H5／H10／H20 研究結果（2026-10-06）

- 純DTO／Decimal契約：`app_module/rule_research_forward_outcome.py`。
- exact receipt＋明示JSON有界唯讀consumer：`app_module/rule_research_forward_outcome_reader.py`。
- 原每日研究母體視窗與TaskWorker：`ui_qt/rule_research_parent_receipt_dialog.py`。
- 邊界／新程序／取消與UI：`tests/test_rule_research_forward_outcome_reader.py`、`tests/test_ui_qt_forward_outcome_receipt.py`；[QA](docs/06_qa/UX21_FORWARD_OUTCOME_20261006.md)／[Manual](docs/07_guides/APPLICATION_MANUAL.md)。不作交易或ML target，原資料不寫。


### UX21 endpoint label→UX22 readiness（2026-10-06）

- 封存來源薄consumer：`app_module/rule_research_label_readiness.py`；重用HistoricalLabelSpec/Row，明示policy與固定時間窗，不fit。
- 可測試唯讀入口：`scripts/run_rule_research_label_readiness.py`，repeat exact parent/outcome receipts，輸出有界來源/hash/分母/缺件JSON。
- `tests/test_rule_research_label_readiness.py`／`tests/test_rule_research_label_readiness_cli.py`；[QA](docs/06_qa/UX22_LABEL_READINESS_20261006.md)／[Manual](docs/07_guides/APPLICATION_MANUAL.md)。既有learner／same-sample比較器缺完整特徵與prediction inputs時blocked；不造PIT/模型/Task。


### UX22 同源公平比較（2026-10-06）

- `app_module/rule_research_fair_comparison.py`：明示target／來源契約、CORE20 feature與整數shadow DTO共同樣本比較。
- `scripts/run_rule_research_fair_comparison.py`：預設白話摘要，--json保存有界研究收據；不fit或寫registry。
- focused／CLI／ML boundary tests與[QA](docs/06_qa/UX22_FAIR_COMPARISON_20261006.md)；[Manual](docs/07_guides/APPLICATION_MANUAL.md)列政策、分母／缺件及排錯。UX22保持partial。


### UX23 隔離 shadow 工程驗收（2026-10-06）

入口 `scripts/run_rule_research_shadow_acceptance.py`；consumer `app_module/rule_research_shadow_acceptance.py`；操作依 [Manual](docs/07_guides/APPLICATION_MANUAL.md)，工程／資料效果／未啟用三軸及未完項依 [UX23 QA](docs/06_qa/UX23_SHADOW_ACCEPTANCE_20261006.md)。不連 registry、不啟用正式行為。


### 2026-10-06 UX08 推薦保存圖表

推薦執行→同次frame capture→immutable execution→exact保存來源研究圖／精確表；helper為`app_module/recommendation_saved_chart.py`，接線service／execute／report read service，既有Qt consumer。使用流程見完整Manual，[範圍／測試／下一包接線](docs/06_qa/UX08_RECOMMENDATION_SAVED_CHART_20261006.md)。UX08整項仍partial，viewport／CSV lane待父層安排。


### 2026-10-06 UX08 viewport產品按鈕

app_module/chart_viewport_state.py接StockResearchReportView價格頁按鈕；範圍控制只切原DTO，原生paint/hover日期槽一致，精確表全量。流程見Manual，[scope／失敗基線／限制](docs/06_qa/UX08_VIEWPORT_INTEGRATION_20261006.md)。


### 2026-10-06 明示市場CSV CLI

scripts/export_market_csv.py提供唯讀preview、caller保存接受的preview後明示execute；app_module/market_csv_export.py只consumer，no Task/上傳/分享/根目錄啟用。Windows handles／來源與exact receipt核驗，實際流程看Manual，[synthetic範圍](docs/06_qa/MARKET_CSV_EXPORT_INTEGRATION_20261006.md)。
