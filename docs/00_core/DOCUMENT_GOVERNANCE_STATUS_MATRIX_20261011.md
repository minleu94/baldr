# 全 docs 文件治理狀態矩陣（2026-10-11）

> 本矩陣是本輪治理快照；現況權威仍依 Scoped SSOT。歷史文件保留追溯，未刪除或搬移原始文件。

## 全域狀態

- 稽核基準 HEAD：`a6aad0e8684e6607c750b6d1d1444d4074b0959b`。
- 基準 tracked 路徑：1489；其中 clean 且有逐檔核讀 ledger、OID／實體行數完全核對：1454；dirty status-only：34；受保護 status-only：1。
- clean eligible 文件 ledger 覆蓋率 100%；缺漏 0、過期指紋 0。dirty 與受保護路徑不讀正文、diff、OID、行數或分類；CSV 對這些路徑只列 `path` 與 `status`。
- 基準之外新增三份治理輸出（文件治理矩陣、逐檔 manifest、開發線路矩陣）後，目前 docs tracked 共 1492 條路徑；三份治理輸出在 CSV 中標為 `generated_self_reference_exempt`，不列入下方 1489 個治理對象的目錄分類統計。README、Graphify guide 與本輪已修訂文件的最終指紋列於 CSV。
- 基準 tracked 文件種類：.csv 1；.html 2；.json 13；.md 1470；.txt 3。三份治理輸出另增 .csv 1 與 .md 2，目前路徑種類合計為 .csv 2、.html 2、.json 13、.md 1472、.txt 3。

## 目錄分類矩陣

`clean` 是逐檔核對 OID 與物理行數的文件；每份 clean 文件依主要用途只計一類。導覽／證據的次要用途、衝突與權威界線寫在逐檔 CSV。目錄表統計 1489 個基準治理對象，不含三份 self-reference exempt 治理輸出；dirty／受保護計數只反映 Git status，沒有從正文推論分類。

| docs 目錄 | tracked | clean 已核對 | 權威 | 導覽 | 證據 | 歷史 | status-only |
|---|---:|---:|---:|---:|---:|---:|---:|
| `00_core` | 18 | 15 | 6 | 9 | 0 | 0 | 3 |
| `01_architecture` | 224 | 221 | 54 | 28 | 109 | 30 | 3 |
| `02_features` | 9 | 8 | 1 | 2 | 2 | 3 | 1 |
| `03_data` | 17 | 17 | 3 | 8 | 5 | 1 | 0 |
| `04_broker_branch` | 6 | 6 | 1 | 1 | 0 | 4 | 0 |
| `05_phases` | 15 | 15 | 0 | 15 | 0 | 0 | 0 |
| `06_qa` | 573 | 557 | 0 | 78 | 479 | 0 | 16 |
| `07_guides` | 20 | 19 | 10 | 6 | 1 | 2 | 1 |
| `08_technical` | 7 | 7 | 1 | 2 | 0 | 4 | 0 |
| `09_archive` | 408 | 399 | 0 | 13 | 0 | 386 | 9 |
| `agents` | 21 | 20 | 11 | 8 | 0 | 1 | 1 |
| `docs_root` | 1 | 1 | 0 | 1 | 0 | 0 | 0 |
| `strategies` | 3 | 3 | 2 | 1 | 0 | 0 | 0 |
| `superpowers` | 167 | 166 | 0 | 93 | 0 | 73 | 1 |
| **合計** | **1489** | **1454** | **89** | **265** | **596** | **504** | **35** |

全域 clean 分類：權威 89、導覽 265、證據 596、歷史 504。

## 權威、導覽、證據與歷史的使用界線

- **權威**：依根目錄 `AGENTS.md` 的 Scoped SSOT 使用；狀態看 `PROJECT_SNAPSHOT.md`，產品方向看 Product Roadmap，工程順序看 6M Roadmap，架構與 Manual 各自維持職責。分類不把舊 roadmap 升格為現況。
- **導覽**：README、索引、redirect、catalog 只負責找資料，內容結論回原始權威或收據核對。
- **證據**：QA／報告只支持其記錄的 commit、資料切片、日期、環境和驗收範圍；無 commit 或當前 receipt 時不當成現況證明。
- **歷史**：`09_archive/`、已結束階段與日期化設計留存原文；不代表現行授權、排程、功能或 gate 完成。Archive 中的 redirect stub 仍分類為導覽，並以 scope 標示其歷史用途。

## 未解衝突與邊界

| ID | 議題 | 判定與處置 |
|---|---|---|
| G01 | 2025 OOS 證據使用順序未解 | `docs/09_archive/superpowers/specs/2026-07-13-parallel-evidence-ml-dashboard-design.md`、`docs/09_archive/superpowers/specs/2026-07-13-terra-development-dataset-v0-design.md` 與 `docs/superpowers/specs/2026-07-13-external-evidence-investment-validation-design.md` 對 2025 development/OOS 使用順序與 custody audit gate 有張力；在現行權威提供 signed custody/QA receipt 前，不推定 2025 可作正式 OOS。 |
| G02 | 自動化數量規格矛盾 | `docs/superpowers/specs/2026-07-11-safe-refactor-four-extra-cycles-design.md` 同一歷史設計列出 12 與 15；保留原文並標為歷史，不能拿來推定現行排程。 |
| G03 | MOPS limited 數值待核 | `docs/09_archive/P0_MOPS_OWNER_PACKET_REFRESH_2026_08_28.md` 的 `limited=0` 與另一接受清冊／矩陣有衝突；相關矩陣處於 dirty 狀態，本輪僅狀態列示，因此維持未解，待工作樹乾淨後核對。 |
| G04 | Portfolio／Exit 兩個 raw caller cutover 未收斂 | `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R016_CONSUMER_CUTOVER_IMPLEMENTATION_REPORT.md` 指出 `user_declared_holding_research.py:774-807` 與 `portfolio_view.py:2947-3000` 尚有直接讀取；既有 R029/R031/REC02/05 未涵蓋這兩個 exact caller。 |
| G05 | Phase 3.3B headline 與 checklist 狀態不一致 | `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/PHASE_3_3B_IMPLEMENTATION_PLAN.md` 的 10/10／三 Epic 100% headline 與 Epic 2 MVP2 pending、Epic 3/Epic 1 unchecked 的正文狀態衝突；未取得同一範圍收據前不宣稱完成。 |
| G06 | R002 測試覆蓋類別總數不一致 | `docs/09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R002.md` 概述稱 8 tests、清單列 9 個覆蓋類別；保留為歷史審查證據，數字未裁定。 |
| G07 | 補完計畫狀態未驗正文 | `docs/09_archive/README.md` 內嵌的補完計畫狀態聲明無法以受保護計畫正文核對；受保護路徑僅保留 Git status，矩陣不把該聲明當已驗證現況。 |
| G08 | 外部參考藍圖中的未日期能力清單 | `docs/00_core/EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` §7 的「目前已具備」列表缺少逐項日期／receipt；其餘文字已導回 Product／6M／Snapshot 權威，該列表仍有過時風險。 |

上述議題沒有以臆測消除；要解除需補上同範圍的現行權威或可核對 receipt。所有 dirty 文件（含正在同步的計畫）維持 status-only，待其工作樹乾淨後另行核對。

## 已完成的窄幅修訂

| 處置 | 路徑與證據 |
|---|---|
| 已修訂 | `docs/09_archive/QA_RECOMMENDATION_TAB_ISSUES.md`：以 2026-10-11 日期註記保留 `volume_ratio_min=1.0` 的兩種歷史解讀，禁止推定缺失的修復細節；提交 `e8fbd9b9`。 |
| 已修訂 | `docs/09_archive/REFACTORING_MIGRATION_PLAN_2025.md`：日期化釐清舊 rename/相容層與 2026-07 後續移除屬不同階段，現況回到 Snapshot／架構；提交 `a6aad0e8`。 |
| 已加界線 | `docs/09_archive/PROJECT_SNAPSHOT_HISTORY_2026_09_08.md`：內嵌「current state」限定為 2026-09-08 快照；提交 `462b7b57`。 |
| 已標示歷史界線 | Batch 4/5/6、Month 4、舊 Git staging/checkout 指令及舊環境／排程文件保留原文並加日期化界線；逐檔路徑提交保存於下表。 |

## 本輪精確路徑修訂提交

下列提交的 commit tree 均已逐一檢查，只包含列出的 docs 路徑：

| Commit | 路徑 |
|---|---|
| `ec22f28b` | `docs/02_features/SCORE_EXPLANATION.md` |
| `7f2d5412` | `docs/02_features/BACKTEST_LAB_FEATURES.md`; `docs/02_features/USER_GUIDE.md` |
| `f7f27ef6` | `docs/agents/data_cleanup_agent.md`; `docs/agents/testing_qa_agent.md` |
| `74d1bfc3` | `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R011_IMPLEMENTATION_REPORT.md` |
| `863e0f96` | `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R016_CONSUMER_CUTOVER_IMPLEMENTATION_REPORT.md` |
| `334d9bbd` | `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R022_IMPLEMENTATION_REPORT.md` |
| `2407fb0e` | `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE3_CHECKPOINT.md` |
| `16ffd38b` | `docs/07_guides/PIT_HISTORICAL_DATA_REPAIR_RUNBOOK.md` |
| `525a4d3d` | `docs/07_guides/PORTABLE_WINDOWS.md` |
| `e1e463a1` | `docs/09_archive/superpowers/plans/2026-06-14-month-2-parameter-run-storage-governance.md` |
| `0baff98a` | `docs/09_archive/BROKER_FLOW_SQLITE_DASHBOARD_PERFORMANCE_2026_07_15.md` |
| `c4df3815` | `docs/09_archive/DAILY_BANKTAIWAN_LEARNING_COST_2026_09_14_HISTORY.md` |
| `af2374f0` | `docs/superpowers/specs/2026-07-07-workbench-left-navigation-ia-design.md` |
| `d570c2de` | `docs/09_archive/DATA_REBUILD_GUIDE_HISTORY.md` |
| `015675f1` | `docs/09_archive/DECISION_EVIDENCE_CAPTURE_CLOCK_QA_2026_09_16.md` |
| `ce059ce1` | `docs/09_archive/DOCUMENTATION_ROADMAP_REBASELINE_AUDIT_2026_07_03.md` |
| `7020b761` | `docs/09_archive/superpowers/plans/2026-06-16-month4-daily-decision-desk-closure.md` |
| `5f66c2f8` | `docs/09_archive/superpowers/plans/2026-06-23-healthcheck-batch4-research-lab-results.md` |
| `7f347fe2` | `docs/09_archive/superpowers/plans/2026-06-23-healthcheck-batch5-performance-operations.md` |
| `ce22c238` | `docs/09_archive/superpowers/plans/2026-06-23-healthcheck-batch6-closeout-regime-researchlab.md` |
| `1b472313` | `docs/09_archive/superpowers/plans/2026-07-02-v1-1-decision-workflow-integration.md` |
| `9f7fd708` | `docs/09_archive/superpowers/plans/2026-07-05-v1-8-portfolio-sandbox.md` |
| `a5ffac5c` | `docs/09_archive/superpowers/plans/2026-07-06-v1-9-read-only-agent-mcp.md` |
| `6060b5fa` | `docs/09_archive/superpowers/plans/2026-07-14-daily-update-non-trading-day-recovery.md` |
| `4677ddc1` | `docs/09_archive/superpowers/specs/2026-06-04-research-lab-workflow-redesign.md` |
| `69cb6826` | `docs/09_archive/superpowers/specs/2026-07-03-post-v1-forward-performance-read-model-design.md` |
| `0344c243` | `docs/09_archive/superpowers/specs/2026-07-07-workbench-visual-hierarchy-polish-design.md` |
| `864f83e4` | `docs/09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/README.md` |
| `1cfe5966` | `docs/09_archive/EVIDENCE_REHEARSAL_REAL_E2E_CLOSEOUT_2026_07_13.md`; `docs/09_archive/FORMAL_DATA_RECONCILIATION_2026_08_06.md` |
| `667cdc47` | `docs/09_archive/POST_V1_FORWARD_PERFORMANCE_DASHBOARD_QA_2026_07_05.md` |
| `37ca71be` | `docs/09_archive/POST_V1_SIGNAL_DECAY_MONITOR_QA_2026_07_09.md` |
| `68fa013d` | `docs/09_archive/NATIVE_1477_RETRY_READBACK_ACCEPTANCE_20261005_HISTORY.md` |
| `c331993e` | `docs/09_archive/MCP_YFINANCE_OPENMARKETS_PATCH_MEMO_HISTORY.md`; `docs/09_archive/MINIMAL_CONTINUATION_HANDOFF_20261005_HISTORY.md`; `docs/09_archive/ML_RELEASE_V4_STORAGE_RETENTION_CLEANUP_2026_08_29.md` |
| `462b7b57` | `docs/09_archive/PROJECT_SNAPSHOT_HISTORY_2026_09_08.md` |
| `e8fbd9b9` | `docs/09_archive/QA_RECOMMENDATION_TAB_ISSUES.md` |
| `a6aad0e8` | `docs/09_archive/REFACTORING_MIGRATION_PLAN_2025.md` |
| `b19b6d83` | `docs/00_core/README.md`; `docs/00_core/DEVELOPMENT_LINE_EVOLUTION_MATRIX_20261011.md` |
| `977063ba` | `docs/06_qa/SCHEDULER_ML_DAILY_SOURCE_ROW_PROJECTION_20261001.md`; `docs/00_core/DEVELOPMENT_LINE_EVOLUTION_MATRIX_20261011.md` |
| `71e72aa6` | `docs/00_core/DEVELOPMENT_LINE_EVOLUTION_MATRIX_20261011.md`; `docs/00_core/DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv`; `docs/00_core/DOCUMENT_GOVERNANCE_STATUS_MATRIX_20261011.md`; `docs/00_core/ROADMAP_6M_ENGINEERING.md`; `docs/02_features/BACKTEST_LAB_FEATURES.md`; `docs/06_qa/PRODUCT_UX_QA_INDEX.md` |

## 核對方法與 Graphify

1. 先取 Git status 路徑清單，排除所有 dirty 路徑與受保護計畫，再以 exact clean path batches 取 HEAD blob OID，僅對 eligible OID 讀 blob 並計算物理行數。
2. 將結果與 JSONL audit ledger 對照；逐檔 manifest 保存分類、用途、時間／權威界線、衝突判讀、處置、基準與最終 OID／行數及來源 ledger。
3. 所有目錄核對完成、矩陣／清冊／導覽入口 exact-path commit 後，才刷新 Graphify。新輸出位於 ignored `output/qa/baldr_documentation_reorganization_20261011/`；build summary 記錄實際來源清單、工具版本、節點／邊／community 計數及診斷。使用本機 AST 與明示 Markdown links，沒有 semantic extraction 或 network transfer；根目錄 `graphify-out` 保留。

逐檔清冊：[DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv](DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv)。dirty／受保護路徑只含 `path` 與 `status`；兩個新治理文件為 self-reference exempt。
