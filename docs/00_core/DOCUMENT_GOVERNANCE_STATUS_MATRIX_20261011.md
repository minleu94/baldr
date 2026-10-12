# 全 docs 文件治理狀態矩陣（截至 2026-10-12）

> 本矩陣檔名保留以維持既有導航連結；內容是截至 2026-10-12 的治理快照。現況權威仍依 Scoped SSOT。歷史文件保留追溯，未刪除或搬移原始文件。

## 全域狀態

- 內容覆核基準 HEAD（本次矩陣／清冊更新前）：`d1348963f6e8acf42b30b22a75fa7a3178d21db9`。
- 目前 docs tracked 路徑：1493；其中 1487 條 eligible 文件都有逐檔 EOF 覆核、分類、目前 HEAD blob OID 與物理行數；3 條受保護路徑只查 Git status；3 份治理輸出列為 self-reference exempt。
- eligible 覆核覆蓋率 100%；缺漏 0、過期指紋 0。受保護路徑不讀正文、diff、OID、行數或分類；CSV 僅列 `path` 與 `status`。本矩陣涵蓋 1490 條治理路徑（1487 eligible + 3 protected），另 3 份治理輸出不計入文件分類。
- Protected status-only 路徑：`docs/06_qa/BALDR_COMPLETION_PROGRESS_20261011.md`、`docs/superpowers/plans/baldr_product_completion_plan_20261006.md`、`docs/agents/shared_state/BALDR_COMPLETION_RESUME_PROMPT_20261012.md`。
- 三份 self-reference exempt 輸出為本矩陣、逐檔 manifest、開發線路演進矩陣。檔案類型總數：.csv 2、.html 2、.json 13、.md 1473、.txt 3。

## 目錄分類矩陣

`clean` 是逐檔核對 OID 與物理行數的文件；每份 clean 文件依主要用途只計一類。導覽／證據的次要用途、衝突與權威界線寫在逐檔 CSV。目錄表統計 1490 條治理路徑，不含三份 self-reference exempt 治理輸出；3 條 protected 只保留狀態，不由正文推論分類。

| docs 目錄 | tracked | clean 已核對 | 權威 | 導覽 | 證據 | 歷史 | status-only |
|---|---:|---:|---:|---:|---:|---:|---:|
| `00_core` | 18 | 18 | 7 | 10 | 0 | 1 | 0 |
| `01_architecture` | 224 | 224 | 55 | 28 | 111 | 30 | 0 |
| `02_features` | 9 | 9 | 1 | 2 | 2 | 4 | 0 |
| `03_data` | 17 | 17 | 3 | 8 | 5 | 1 | 0 |
| `04_broker_branch` | 6 | 6 | 1 | 1 | 0 | 4 | 0 |
| `05_phases` | 15 | 15 | 0 | 15 | 0 | 0 | 0 |
| `06_qa` | 573 | 572 | 0 | 78 | 494 | 0 | 1 |
| `07_guides` | 20 | 20 | 11 | 6 | 1 | 2 | 0 |
| `08_technical` | 7 | 7 | 1 | 2 | 0 | 4 | 0 |
| `09_archive` | 408 | 408 | 0 | 13 | 4 | 391 | 0 |
| `agents` | 22 | 21 | 12 | 8 | 0 | 1 | 1 |
| `docs_root` | 1 | 1 | 0 | 1 | 0 | 0 | 0 |
| `strategies` | 3 | 3 | 2 | 1 | 0 | 0 | 0 |
| `superpowers` | 167 | 166 | 0 | 93 | 0 | 73 | 1 |
| **合計** | **1490** | **1487** | **93** | **266** | **617** | **511** | **3** |

全域 clean 分類：權威 93、導覽 266、證據 617、歷史 511。

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
| G03 | MOPS limited 數值待核 | `docs/09_archive/P0_MOPS_OWNER_PACKET_REFRESH_2026_08_28.md` 與 `docs/06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md` §7 的 DEV-66 `limited` 決議，和該 register §14 的 `limited=0` 總數口徑不一致。§14 的 2026-10-10 調和註記已確認仍缺原始 audit artifact／registry 比對；保留兩筆歷史證據，不推定任何一方代表全域目前授權。 |
| G04 | Portfolio／Exit 兩個 raw caller cutover 未收斂 | `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R016_CONSUMER_CUTOVER_IMPLEMENTATION_REPORT.md` 指出 `user_declared_holding_research.py:774-807` 與 `portfolio_view.py:2947-3000` 尚有直接讀取；既有 R029/R031/REC02/05 未涵蓋這兩個 exact caller。 |
| G05 | Phase 3.3B headline 與 checklist 狀態不一致 | 實際文件是 `docs/09_archive/PHASE_3_3B_IMPLEMENTATION_PLAN.md`；歷史標題的三 Epic 100% headline 與 Epic 2 MVP2 pending、Epic 3/Epic 1 unchecked 清單狀態衝突。該文件已加「完成度待核」歷史 erratum；未取得同範圍收據前不宣稱完成。 |
| G06 | R002 測試覆蓋類別總數不一致 | `docs/09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R002.md` 概述稱 8 tests、清單列 9 個覆蓋類別；保留為歷史審查證據，數字未裁定。 |
| G07 | 補完計畫狀態未驗正文 | `docs/09_archive/README.md` 內嵌的補完計畫狀態聲明無法以受保護計畫正文核對；受保護路徑僅保留 Git status，矩陣不把該聲明當已驗證現況。 |
| G08 | 外部參考藍圖中的未日期能力清單 | `docs/00_core/EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` §7 已明示能力列表是研究比較摘要、未逐項核對目前 HEAD／runtime／QA，不可作現況或正式驗收證明。此界線已充分標註；逐項現況仍未核，應保留為研究／歷史內容，不因缺少逐項 receipt 而刪除。 |
| G09 | 現行架構主文混有日期增量 | `docs/01_architecture/system_architecture.md` §16 同時保留 2026-10-03 至 10-08 增量與穩定契約；文件已將目前狀態導回 Snapshot，沒有未限定的現況錯誤。本輪不拆改主文；後續若要降低維護負擔，可把已結束增量移入 QA／歷史並保留穩定架構責任。 |

尚未由同範圍現行權威或可核對 receipt 解決的議題均保留待核；G08 已以研究範圍警語限制，不視為現況主張。G09 是結構整理候選，並非現況錯誤。本輪受保護的三條路徑維持 status-only，待使用者工作完成後另行核對。

## 已完成的窄幅修訂

| 處置 | 路徑與證據 |
|---|---|
| 已修訂 | `docs/09_archive/QA_RECOMMENDATION_TAB_ISSUES.md`：以 2026-10-11 日期註記保留 `volume_ratio_min=1.0` 的兩種歷史解讀，禁止推定缺失的修復細節；提交 `e8fbd9b9`。 |
| 已修訂 | `docs/09_archive/REFACTORING_MIGRATION_PLAN_2025.md`：日期化釐清舊 rename/相容層與 2026-07 後續移除屬不同階段，現況回到 Snapshot／架構；提交 `a6aad0e8`。 |
| 已加界線 | `docs/09_archive/PROJECT_SNAPSHOT_HISTORY_2026_09_08.md`：內嵌「current state」限定為 2026-09-08 快照；提交 `462b7b57`。 |
| 已修訂 | `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R006_GEMINI_REVIEW.md` 的三個本機絕對連結改為可攜相對連結，並在 `WAVE3_CHECKPOINT.md` 更正 facade/import 收尾描述；提交 `3933a176`。 |
| 已加界線／修正連結 | `docs/09_archive/DOCUMENTATION_CATALOG_20261006_HISTORY.md`、`DOCUMENTATION_INDEX_HISTORY_2026_09_27.md`、`SQLITE_STORAGE_GUIDE_HISTORY_20260602.md`、`TROUBLESHOOTING_DAILY_UPDATE_HISTORY.md`：修正錯誤相對連結並把歷史日期、刪除及重建命令限制在當時範圍；提交 `00779a42`。 |
| 已補日期界線 | `docs/09_archive/SQLITE_STORAGE_GUIDE_HISTORY_20260602.md`：把正文未加日期的「目前／現在」限定為 2026-06-02 假設；提交 `d1348963`。 |
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
| `2182f1df` | `docs/00_core/DOCUMENT_GOVERNANCE_STATUS_MATRIX_20261011.md`; `docs/00_core/DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv`; `docs/00_core/DEVELOPMENT_LINE_EVOLUTION_MATRIX_20261011.md`; `docs/00_core/DOCUMENTATION_GRAPH_GUIDE.md`; `docs/06_qa/README.md`; `docs/06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md`; `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_DISPATCH/WAVE2_GEMINI_REVIEW_PROMPTS.md` |
| `3933a176` | `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R006_GEMINI_REVIEW.md`; `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE3_CHECKPOINT.md` |
| `00779a42` | `docs/09_archive/DOCUMENTATION_CATALOG_20261006_HISTORY.md`; `docs/09_archive/DOCUMENTATION_INDEX_HISTORY_2026_09_27.md`; `docs/09_archive/SQLITE_STORAGE_GUIDE_HISTORY_20260602.md`; `docs/09_archive/TROUBLESHOOTING_DAILY_UPDATE_HISTORY.md` |
| `d1348963` | `docs/09_archive/SQLITE_STORAGE_GUIDE_HISTORY_20260602.md` |

## 核對方法與 Graphify

1. 先取 Git status 路徑清單，排除所有 dirty 路徑與受保護計畫，再以 exact clean path batches 取 HEAD blob OID，僅對 eligible OID 讀 blob 並計算物理行數。
2. 將結果與 JSONL audit ledger 對照；逐檔 manifest 保存分類、用途、時間／權威界線、衝突判讀、處置、基準與最終 OID／行數及來源 ledger。
3. 所有目錄核對完成、矩陣／清冊／導覽入口 exact-path commit 後，才刷新 Graphify。2026-10-12 的新輸出位於 ignored `output/qa/baldr_documentation_reorganization_20261012_final/`；build summary 記錄實際來源清單、工具版本、節點／邊／community 計數及診斷。使用本機 AST 與明示 Markdown links，沒有 semantic extraction 或 network transfer；根目錄 `graphify-out` 保留。Graphify 排除三條 protected 路徑與本矩陣／path manifest 兩份 self-reference 狀態輸出；開發線路演進矩陣保留為導航來源。

逐檔清冊：[DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv](DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv)。三條受保護路徑及三份 self-reference exempt 治理輸出只列 `path` 與 `status`；其餘 1487 條都列有分類、界線、衝突判讀、HEAD OID、物理行數及來源 ledger。
