# 全 docs 文件治理狀態矩陣（截至 2026-10-12）

> 本矩陣檔名保留以維持既有導航連結；內容是截至 2026-10-12 的治理快照。現況權威仍依 Scoped SSOT。歷史文件保留追溯，未刪除或搬移原始文件。

## 全域狀態

- 內容覆核基準 HEAD（本輪逐檔覆核開始時）：`eb2e2cc27a13cc5801a5b3d7d0a5f6b1a6848937`。
- 本清冊涵蓋 `docs/` 全部 1494 個 tracked 路徑及 `docs/` 以外 26 個 tracked Markdown 文件，共 1520 條治理路徑。1517 份一般文件已逐檔讀至 EOF、分類、核對 HEAD blob OID 與物理行數；3 份治理輸出列為 self-reference exempt。
- 五項修復基準：`d929e003a508a24e97611b73f282f5061f9b0c7b`；本輪覆核變更文件與新增收據，既有全檔覆核歷史保留，逐檔最終指紋同步提交內容。
- 一般文件覆核覆蓋率 100%；缺漏 0、過期指紋 0、protected status-only 0。三份 self-reference exempt 輸出為本矩陣、逐檔 manifest、開發線路演進矩陣，不計入自身內容覆核或分類。`docs/` 檔案類型：.csv 2、.html 2、.json 13、.md 1474、.txt 3；外部補充範圍是 repo 根目錄 Markdown、`.agent/rules/*.md` 與其他目錄的 tracked Markdown，不含程式、設定、資料檔或 `.ipynb`。

## 目錄分類矩陣

`clean` 是逐檔讀至 EOF 並核對 OID 與物理行數的文件；每份文件依主要用途只計一類。導覽／證據的次要用途、衝突與權威界線寫在逐檔 CSV。下表只統計 `docs/` 的 1491 份一般文件；repo 其他 Markdown 另列於補充表，避免混淆目錄分母。本輪沒有 status-only 文件。

| docs 目錄 | tracked | clean 已核對 | 權威 | 導覽 | 證據 | 歷史 | status-only |
|---|---:|---:|---:|---:|---:|---:|---:|
| `00_core` | 18 | 18 | 7 | 10 | 0 | 1 | 0 |
| `01_architecture` | 224 | 224 | 55 | 28 | 111 | 30 | 0 |
| `02_features` | 9 | 9 | 1 | 2 | 2 | 4 | 0 |
| `03_data` | 17 | 17 | 3 | 8 | 5 | 1 | 0 |
| `04_broker_branch` | 6 | 6 | 1 | 1 | 0 | 4 | 0 |
| `05_phases` | 15 | 15 | 0 | 15 | 0 | 0 | 0 |
| `06_qa` | 574 | 574 | 0 | 78 | 496 | 0 | 0 |
| `07_guides` | 20 | 20 | 11 | 6 | 1 | 2 | 0 |
| `08_technical` | 7 | 7 | 1 | 2 | 0 | 4 | 0 |
| `09_archive` | 408 | 408 | 0 | 13 | 4 | 391 | 0 |
| `agents` | 22 | 22 | 12 | 9 | 0 | 1 | 0 |
| `docs_root` | 1 | 1 | 0 | 1 | 0 | 0 | 0 |
| `strategies` | 3 | 3 | 2 | 1 | 0 | 0 | 0 |
| `superpowers` | 167 | 167 | 0 | 93 | 0 | 74 | 0 |
| **docs/ 合計** | **1491** | **1491** | **93** | **267** | **619** | **512** | **0** |

## `docs/` 以外的 tracked Markdown 補充矩陣

| 範圍 | tracked Markdown | clean 已核對 | 權威 | 導覽 | 證據 | 歷史 | status-only |
|---|---:|---:|---:|---:|---:|---:|---:|
| Repo 根目錄 | 10 | 10 | 1 | 5 | 4 | 0 | 0 |
| `.agent/rules/` | 4 | 4 | 4 | 0 | 0 | 0 | 0 |
| 其他目錄 Markdown | 12 | 12 | 0 | 6 | 2 | 4 | 0 |
| **補充範圍合計** | **26** | **26** | **5** | **11** | **6** | **4** | **0** |

全治理範圍合計：1520 條 tracked 文件路徑、1517 份 clean 已核對、3 份 self-reference exempt；一般文件分類為權威 98、導覽 278、證據 625、歷史 516。逐檔狀態、HEAD blob OID、物理行數與分類見 [path manifest](DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv)。

## 權威、導覽、證據與歷史的使用界線

- **權威**：依根目錄 `AGENTS.md` 的 Scoped SSOT 使用；狀態看 `PROJECT_SNAPSHOT.md`，產品方向看 Product Roadmap，工程順序看 6M Roadmap，架構與 Manual 各自維持職責。分類不把舊 roadmap 升格為現況。
- **導覽**：README、索引、redirect、catalog 只負責找資料，內容結論回原始權威或收據核對。
- **證據**：QA／報告只支持其記錄的 commit、資料切片、日期、環境和驗收範圍；無 commit 或當前 receipt 時不當成現況證明。
- **歷史**：`09_archive/`、已結束階段與日期化設計留存原文；不代表現行授權、排程、功能或 gate 完成。Archive 中的 redirect stub 仍分類為導覽，並以 scope 標示其歷史用途。

## 未解衝突與邊界

| ID | 議題 | 判定與處置 |
|---|---|---|
| G01 | 2025 永久 development-only 政策與 legacy locked-OOS verifier 能力不同 | 現行操作政策見 `docs/07_guides/HISTORICAL_ML_SHADOW_RUNBOOK.md`：2025 永久為 `seen_oos`／`development_data`，`formal_oos_allowed=false`，停用 `scripts/evaluate_ml_2025_oos.py` 及 `--oos-payload`；新 holdout 另由 `DevelopmentDataUsageDecision.jsonl:new_holdout_start` 管理。舊 `ml_module/locked_oos.py` 的 generic verifier 在呼叫者提供 `formal_oos_allowed=true`、確認、日期及 hash gates 時仍可通過；`tests/test_ml_2025_locked_oos.py` 55–64 行只以合成 true 測 unit preflight，67–92 行的 CLI 整合測試只驗 false 時 fail-closed，沒有 positive CLI integration test。這些測試只證明 legacy code capability，不是 owner 授權或 custody receipt；不可據此把 2025 升格為 formal OOS。未來 prospective holdout 是獨立 custody／owner／QA gate。 |
| G02 | 配置分母已裁決；觸發起源仍 unknown | D–G 四輪 12 個與 H–L 五輪 15 個配置範圍不同；27/27 現存 PAUSED TOML 與 9/25 inventory hash 相符，memory 及兩份 closeout 支持持久化配置／執行交接。配置數不等於完成切片數，缺 host trigger audit，不能重建全部建立事件或宣稱每次由 Scheduler 觸發。四份原文已加日期界線，詳見[五項裁決 QA](../06_qa/DOCUMENT_GOVERNANCE_ISSUE_RESOLUTION_20261012.md)。 |
| G03 | MOPS 分母差異已裁決 | 同期 canonical P0 13 contracts 含 pit.quarterly_financials、不含 DEV-66 EZSearch availability lane；P0 audit accepted=0／limited=0 與 EZSearch owner limited 不是同一分母。已取回 owner JSON 核 source／revision／hash，register／archive 已補註記；8/28、8/30 raw audit 仍缺件，不推定最新 registry 接受。research-only／alpha=0／禁 formal OOS、credit、scheduler 界線不變，詳見[五項裁決 QA](../06_qa/DOCUMENT_GOVERNANCE_ISSUE_RESOLUTION_20261012.md)。 |
| G04 | 保存 caller 工程回歸通過；Exit 資格有界 | 真 MainWindow 整檔 5 passed，未 mock Portfolio validator；修正 alias fixture 缺 lineage 及 fixture-owned FileHandler teardown。聲明持倉已經 canonical／registered legacy query，核 Request／Context profile、配置、日期與獨立 baseline，不再旁路 SQLite／JSON，exact caller 回歸通過。Exit 契約 38 passed／1 環境 skip；10/12 實際產物 hash／日期可核，仍 degraded／transition_count=0／no_exit_transition_rows，wrapper overall failed，無獨立 run_id attestation，不代表完整退出有效性接受。詳見[五項裁決 QA](../06_qa/DOCUMENT_GOVERNANCE_ISSUE_RESOLUTION_20261012.md)。 |
| G05 | 完成措辭已校準；歷史完整接受 unknown | Phase 3.3B 原三 Epic 完成文字標為未驗證歷史自述，日期及 MVP2 pending／unchecked 清單保留；兩份同範圍原始驗證報告缺件，TASK-LOOP-04／08 bounded QA 不替代三 Epic 完整接受。文件誤導已排除，不把 unchecked 單獨當未實作證明，詳見[五項裁決 QA](../06_qa/DOCUMENT_GOVERNANCE_ISSUE_RESOLUTION_20261012.md)。 |
| G06 | R002 pytest case 與語意覆蓋標籤曾被混成同一計數 | 來源有 6 個 pytest test functions，其中 missing-score 參數化產生 3 個 case，共 8 collected cases；review packet 的 9 項是語意覆蓋標籤，部分 test 同時覆蓋多項。計數單位不同，不構成測試數缺口；歷史數字保留並標明單位。 |
| G07 | 補完計畫、進度收據與 resume prompt 的狀態／授權語句 | 10/06 計畫正文描述歷史工作範圍與驗收清單；10/11 progress receipt 與 10/12 Snapshot 記錄治理期間暫停、沒有新完整工作包或 Gate 接受。resume prompt 原第 67 行「現在授權恢復」與當前暫停狀態衝突，已改為必須依接手時最新使用者指示確認是否恢復。Snapshot 原「下一步」曾將 10/09 恢復開發寫成現況並指向舊 10/09 矩陣；本輪已改成日期化歷史、明示 10/12 暫停，並連到本矩陣，舊矩陣標為歷史追溯。三份正文已 EOF 覆核；它們分屬 history、evidence、navigation，產品完成度仍以 Snapshot 和具名 receipts 判讀。 |
| G08 | 外部參考藍圖的研究能力與來源接受範圍 | `docs/00_core/EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` 已將原「P0 adapters 完成 shadow engineering」收窄為 P0/P13 bounded shadow-acquisition routes 已接線；這只證明隔離工程能力，不代表每個 probe 可用或來源已接受。§7 亦明示研究比較未逐項核對目前 HEAD／runtime／QA；現行來源順序以 Product Roadmap §11 為準。保留研究內容，不將其用作現況或正式驗收收據。 |
| G09 | 現行架構主文混有日期增量 | `docs/01_architecture/system_architecture.md` §16 同時保留 2026-10-03 至 10-08 增量與穩定契約；文件已將目前狀態導回 Snapshot，沒有未限定的現況錯誤。本輪不拆改主文；後續若要降低維護負擔，可把已結束增量移入 QA／歷史並保留穩定架構責任。 |
| G10 | 日曆 API 修復；自然 no-data 收據仍缺 | Quick explicit cache preflight 改單一 offline read operation，缺件／無效年度仍 fail closed，Quick 76 passed／同類候選 CLI 40 passed。正式 Quick 115 history rows／100 logs 定向搜尋未見 explicit no-data；最新同 run 為有資料回應，空 no_data_skipped_dates 不能當 no-data。仍需自然 explicit no-data producer receipt 與同 run consumer binding，不造回應或啟動正式 producer 補證，詳見[五項裁決 QA](../06_qa/DOCUMENT_GOVERNANCE_ISSUE_RESOLUTION_20261012.md)。 |

2026-10-12 五項逐一裁決：G02／G03 分母與 G05 完成措辭已修正，G04 caller 及 G10 日曆工程缺陷已修復並驗證。歷史觸發起源、Phase 3.3B 完整接受、Exit 非退化資格及自然 no-data 同 run 收據仍是外部證據界線，不把缺件改寫成完成。G01 的 2025 development-only 政策已明確，legacy verifier capability 不構成授權；未來新 holdout 需獨立證據。G06 計數單位已釐清；G07 文件狀態與授權語句已調和，但產品工作仍暫停；G08 已以研究範圍警語限制，不視為現況主張；G09 是結構整理候選，並非現況錯誤。

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
3. 所有內容與清冊修訂提交後，Graphify 以最終 HEAD 的 Git blobs 建立受控 snapshot，逐筆核對來源 path／blob OID／SHA-256，再驗證來源數、連結、節點端點與 root `graphify-out` 未變更。Graphify 排除本矩陣與 path manifest 兩份自我參照輸出；開發線路演進矩陣及補完計畫納入導覽來源。前輪與本輪產物／驗收收據分別保存在 ignored `output/qa/gf613_verification/` 與 `output/qa/gov5gf/`，不得以舊 HEAD 圖譜代替。

前輪定版 d929e003 的 Graphify 驗收為 PASS：1517 份文件、1087 個 production Python 檔、11355 條明示 Markdown links、未解析本機文件／程式連結 0，收據保存在 output/qa/gf613_verification/graphify_final_verification.json。本輪新增裁決收據並修復 caller，提交後於 output/qa/gov5gf/graphify_final_verification.json 重新核對固定 HEAD、1518 份文件及 1087 個 production Python 檔、全部 bytes／blob 指紋、連結及端點；不將舊 AST 當作新程式碼。nodes／edges／communities 與未解析 AST 診斷以新 JSON 收據為準，只有 passed=true 才代表本輪定版圖驗收。使用 Graphify 0.9.11 本機 AST 與明示 Markdown links，無 semantic model 或網路；root graphify-out 不變核對也列入收據。補完計畫納入導覽不代表產品 Gate 接受。

逐檔清冊：[DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv](DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv)。`docs/` 下 1491 份一般文件，以及 `docs/` 外 26 份 tracked Markdown，都有分類、界線、衝突判讀、HEAD OID、物理行數及來源 ledger；本矩陣、path manifest 與開發線路矩陣 3 份治理輸出保留自我參照豁免。
