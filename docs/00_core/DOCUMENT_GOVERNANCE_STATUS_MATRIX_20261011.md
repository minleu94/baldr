# 全 docs 文件治理狀態矩陣（截至 2026-10-12）

> 本矩陣檔名保留以維持既有導航連結；內容是截至 2026-10-12 的治理快照。現況權威仍依 Scoped SSOT。歷史文件保留追溯，未刪除或搬移原始文件。

## 全域狀態

- 內容覆核基準 HEAD（本輪逐檔覆核開始時）：`eb2e2cc27a13cc5801a5b3d7d0a5f6b1a6848937`。
- 本清冊涵蓋 `docs/` 全部 1493 個 tracked 路徑及 `docs/` 以外 26 個 tracked Markdown 文件，共 1519 條治理路徑。1516 份一般文件已逐檔讀至 EOF、分類、核對 HEAD blob OID 與物理行數；3 份治理輸出列為 self-reference exempt。
- 一般文件覆核覆蓋率 100%；缺漏 0、過期指紋 0、protected status-only 0。三份 self-reference exempt 輸出為本矩陣、逐檔 manifest、開發線路演進矩陣，不計入自身內容覆核或分類。`docs/` 檔案類型：.csv 2、.html 2、.json 13、.md 1473、.txt 3；外部補充範圍是 repo 根目錄 Markdown、`.agent/rules/*.md` 與其他目錄的 tracked Markdown，不含程式、設定、資料檔或 `.ipynb`。

## 目錄分類矩陣

`clean` 是逐檔讀至 EOF 並核對 OID 與物理行數的文件；每份文件依主要用途只計一類。導覽／證據的次要用途、衝突與權威界線寫在逐檔 CSV。下表只統計 `docs/` 的 1490 份一般文件；repo 其他 Markdown 另列於補充表，避免混淆目錄分母。本輪沒有 status-only 文件。

| docs 目錄 | tracked | clean 已核對 | 權威 | 導覽 | 證據 | 歷史 | status-only |
|---|---:|---:|---:|---:|---:|---:|---:|
| `00_core` | 18 | 18 | 7 | 10 | 0 | 1 | 0 |
| `01_architecture` | 224 | 224 | 55 | 28 | 111 | 30 | 0 |
| `02_features` | 9 | 9 | 1 | 2 | 2 | 4 | 0 |
| `03_data` | 17 | 17 | 3 | 8 | 5 | 1 | 0 |
| `04_broker_branch` | 6 | 6 | 1 | 1 | 0 | 4 | 0 |
| `05_phases` | 15 | 15 | 0 | 15 | 0 | 0 | 0 |
| `06_qa` | 573 | 573 | 0 | 78 | 495 | 0 | 0 |
| `07_guides` | 20 | 20 | 11 | 6 | 1 | 2 | 0 |
| `08_technical` | 7 | 7 | 1 | 2 | 0 | 4 | 0 |
| `09_archive` | 408 | 408 | 0 | 13 | 4 | 391 | 0 |
| `agents` | 22 | 22 | 12 | 9 | 0 | 1 | 0 |
| `docs_root` | 1 | 1 | 0 | 1 | 0 | 0 | 0 |
| `strategies` | 3 | 3 | 2 | 1 | 0 | 0 | 0 |
| `superpowers` | 167 | 167 | 0 | 93 | 0 | 74 | 0 |
| **docs/ 合計** | **1490** | **1490** | **93** | **267** | **618** | **512** | **0** |

## `docs/` 以外的 tracked Markdown 補充矩陣

| 範圍 | tracked Markdown | clean 已核對 | 權威 | 導覽 | 證據 | 歷史 | status-only |
|---|---:|---:|---:|---:|---:|---:|---:|
| Repo 根目錄 | 10 | 10 | 1 | 5 | 4 | 0 | 0 |
| `.agent/rules/` | 4 | 4 | 4 | 0 | 0 | 0 | 0 |
| 其他目錄 Markdown | 12 | 12 | 0 | 6 | 2 | 4 | 0 |
| **補充範圍合計** | **26** | **26** | **5** | **11** | **6** | **4** | **0** |

全治理範圍合計：1519 條 tracked 文件路徑、1516 份 clean 已核對、3 份 self-reference exempt；一般文件分類為權威 98、導覽 278、證據 624、歷史 516。逐檔狀態、HEAD blob OID、物理行數與分類見 [path manifest](DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv)。

## 權威、導覽、證據與歷史的使用界線

- **權威**：依根目錄 `AGENTS.md` 的 Scoped SSOT 使用；狀態看 `PROJECT_SNAPSHOT.md`，產品方向看 Product Roadmap，工程順序看 6M Roadmap，架構與 Manual 各自維持職責。分類不把舊 roadmap 升格為現況。
- **導覽**：README、索引、redirect、catalog 只負責找資料，內容結論回原始權威或收據核對。
- **證據**：QA／報告只支持其記錄的 commit、資料切片、日期、環境和驗收範圍；無 commit 或當前 receipt 時不當成現況證明。
- **歷史**：`09_archive/`、已結束階段與日期化設計留存原文；不代表現行授權、排程、功能或 gate 完成。Archive 中的 redirect stub 仍分類為導覽，並以 scope 標示其歷史用途。

## 未解衝突與邊界

| ID | 議題 | 判定與處置 |
|---|---|---|
| G01 | 2025 永久 development-only 政策與 legacy locked-OOS verifier 能力不同 | 現行操作政策見 `docs/07_guides/HISTORICAL_ML_SHADOW_RUNBOOK.md`：2025 永久為 `seen_oos`／`development_data`，`formal_oos_allowed=false`，停用 `scripts/evaluate_ml_2025_oos.py` 及 `--oos-payload`；新 holdout 另由 `DevelopmentDataUsageDecision.jsonl:new_holdout_start` 管理。舊 `ml_module/locked_oos.py` 的 generic verifier 在呼叫者提供 `formal_oos_allowed=true`、確認、日期及 hash gates 時仍可通過；`tests/test_ml_2025_locked_oos.py` 55–64 行只以合成 true 測 unit preflight，67–92 行的 CLI 整合測試只驗 false 時 fail-closed，沒有 positive CLI integration test。這些測試只證明 legacy code capability，不是 owner 授權或 custody receipt；不可據此把 2025 升格為 formal OOS。未來 prospective holdout 是獨立 custody／owner／QA gate。 |
| G02 | 歷史 automation 實際建立／執行生命週期缺 receipt | D–G 四輪規格原始與目前正文都只記 12 支；另一份 H–L 五輪設計另記 15 支，但沒有證據證明它是 2026-10-11 差異提示中「15」的來源。該提示已更正；當時實際建立／執行數仍無 Scheduler receipt，故歷史設計只作方案，不推定現行排程或授權。 |
| G03 | MOPS limited 數值待核 | `docs/09_archive/P0_MOPS_OWNER_PACKET_REFRESH_2026_08_28.md` 與 `docs/06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md` §7 的 DEV-66 `limited` 決議，和該 register §14 的 `limited=0` 總數口徑不一致。§14 的 2026-10-10 調和註記已確認仍缺原始 audit artifact／registry 比對；保留兩筆歷史證據，不推定任何一方代表全域目前授權。 |
| G04 | Portfolio consumer cutover 有歷史 QA 收據，但本輪重跑未通過，其他 consumer 仍待接線／驗收 | R016 的日期化 overlay 所列 `portfolio_view.py:2947–3000` 已是 stress-history UI。現行 `ui_qt/views/portfolio_view.py:_validated_recommendation_result_id()` 走 `build_recommendation_execution_queries().get()`，並做 canonical integrity／identity 驗證。`docs/06_qa/WP3_WATCHLIST_QA_20260928.md` 記錄跨頁測試 1 passed、整檔 4 passed；但 2026-10-12 對兩項相關測試重跑為 2 failed、1 teardown error：MainWindow journey 在 recommendation save 階段（測試第 654 行）因 `cannot safely check saved artifact identity` 失敗，未抵達 Portfolio validator，teardown 又因 `config.log` 被占用而無法清除本輪臨時目錄；legacy alias 測試第 1672 行預期中文-only saved row 可回傳 `R1`，實際回傳空字串。故歷史通過收據不證明目前測試接受，canonical 的現行驗收仍待修復並重跑。測試原始碼中的 main journey 確有真方法成功／竄改摘要拒絕斷言；alias test 也直接測真方法，並非 monkeypatch。`tests/test_ui_qt_portfolio_view.py::test_linked_position_research_keeps_canonical_saved_dates` 才是 mock 此方法的 UI-context 測試。仍待治理的 caller 是 `app_module/user_declared_holding_research.py:_candidate_results()`（目前約 lines 787–844）直接讀 SQLite `runs.data_path` 與 JSON，尚無 exact caller cutover／接受收據；Exit operational readback 也是另一個未完成出口。 |
| G05 | Phase 3.3B headline 與 checklist 狀態不一致 | 實際文件是 `docs/09_archive/PHASE_3_3B_IMPLEMENTATION_PLAN.md`；歷史標題的三 Epic 100% headline 與 Epic 2 MVP2 pending、Epic 3/Epic 1 unchecked 清單狀態衝突。該文件已加「完成度待核」歷史 erratum；未取得同範圍收據前不宣稱完成。 |
| G06 | R002 pytest case 與語意覆蓋標籤曾被混成同一計數 | 來源有 6 個 pytest test functions，其中 missing-score 參數化產生 3 個 case，共 8 collected cases；review packet 的 9 項是語意覆蓋標籤，部分 test 同時覆蓋多項。計數單位不同，不構成測試數缺口；歷史數字保留並標明單位。 |
| G07 | 補完計畫、進度收據與 resume prompt 的狀態／授權語句 | 10/06 計畫正文描述歷史工作範圍與驗收清單；10/11 progress receipt 與 10/12 Snapshot 記錄治理期間暫停、沒有新完整工作包或 Gate 接受。resume prompt 原第 67 行「現在授權恢復」與當前暫停狀態衝突，已改為必須依接手時最新使用者指示確認是否恢復。Snapshot 原「下一步」曾將 10/09 恢復開發寫成現況並指向舊 10/09 矩陣；本輪已改成日期化歷史、明示 10/12 暫停，並連到本矩陣，舊矩陣標為歷史追溯。三份正文已 EOF 覆核；它們分屬 history、evidence、navigation，產品完成度仍以 Snapshot 和具名 receipts 判讀。 |
| G08 | 外部參考藍圖的研究能力與來源接受範圍 | `docs/00_core/EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` 已將原「P0 adapters 完成 shadow engineering」收窄為 P0/P13 bounded shadow-acquisition routes 已接線；這只證明隔離工程能力，不代表每個 probe 可用或來源已接受。§7 亦明示研究比較未逐項核對目前 HEAD／runtime／QA；現行來源順序以 Product Roadmap §11 為準。保留研究內容，不將其用作現況或正式驗收收據。 |
| G09 | 現行架構主文混有日期增量 | `docs/01_architecture/system_architecture.md` §16 同時保留 2026-10-03 至 10-08 增量與穩定契約；文件已將目前狀態導回 Snapshot，沒有未限定的現況錯誤。本輪不拆改主文；後續若要降低維護負擔，可把已結束增量移入 QA／歷史並保留穩定架構責任。 |
| G10 | 資料來源 no-data fail-closed 缺少自然執行收據 | `docs/07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md` 描述 no-data／source readiness 的契約與判讀，但本輪未找到同範圍自然 Task 的 producer＋consumer 同次 run receipt。文件中的 fail-closed 規則是操作契約，不等於 runtime 已依預期執行；待有界 no-data run 保存路徑、hash、status 與 consumer readback 後再核定。 |

尚未由同範圍現行權威或可核對 receipt 解決的事項保留待核；G02、G03、G04、G05、G10 仍有生命週期、測試或 acceptance receipt 缺口。G01 的 2025 development-only 政策已明確，legacy verifier capability 不構成授權；未來新 holdout 需獨立證據。G06 計數單位已釐清；G07 文件狀態與授權語句已調和，但產品工作仍暫停；G08 已以研究範圍警語限制，不視為現況主張；G09 是結構整理候選，並非現況錯誤。

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
| `78393dec` | `docs/00_core/DOCUMENT_GOVERNANCE_STATUS_MATRIX_20261011.md`; `docs/00_core/DOCUMENTATION_INDEX.md`; `docs/00_core/DOCUMENTATION_GRAPH_GUIDE.md` |
| `5c1f22e9` | `docs/00_core/DOCUMENTATION_INDEX.md` |

## 核對方法與 Graphify

1. 先取 tracked docs 路徑清單，再以 exact path batches 讀取每個文件正文至 EOF，記錄主要用途分類、範圍／權威界線、衝突、處置、HEAD blob OID 與物理行數。
2. 將結果與 JSONL audit ledger 對照；逐檔 manifest 保存分類、用途、時間／權威界線、衝突判讀、處置、基準與最終 OID／行數及來源 ledger。
3. 所有內容與清冊修訂提交後，Graphify 以最終 HEAD 的 Git blobs 建立受控 snapshot，逐筆核對來源 path／blob OID／SHA-256，再驗證來源數、連結、節點端點與 root `graphify-out` 未變更。Graphify 排除本矩陣與 path manifest 兩份自我參照輸出；開發線路演進矩陣及補完計畫納入導覽來源。最終產物與驗收收據保存在 ignored `output/qa/gf613_final/`，不得以舊 HEAD 圖譜代替。

2026-10-12 最終 Graphify 驗收：PASS。來源包含 1517 份文件及 1087 個 production Python 檔；明示 Markdown links 11355 條，其中文件 10450、程式碼 313、未解析本機文件／程式連結 0。最終圖為 36094 nodes、106054 edges、1011 communities，dangling edges 0、missing endpoints 0；8309 條跨來源 AST 未解析邊另列診斷，不當作已解析關聯。Graphify 0.9.11 使用本機 AST 與明示 Markdown links，未使用 semantic model 或網路；根 `graphify-out` metadata 前後一致。逐項固定 HEAD、來源指紋及檢查結果見 `output/qa/gf613_final/graphify_final_verification.json`。補完計畫僅作為可追蹤文件納入，不代表產品 Gate 已接受。

逐檔清冊：[DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv](DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv)。`docs/` 下 1490 份一般文件，以及 `docs/` 外 26 份 tracked Markdown，都有分類、界線、衝突判讀、HEAD OID、物理行數及來源 ledger；本矩陣、path manifest 與開發線路矩陣 3 份治理輸出保留自我參照豁免。
