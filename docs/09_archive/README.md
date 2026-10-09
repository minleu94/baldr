# 歸檔文檔目錄

> **歷史記錄和總結文檔（歸檔）**
> **最後整理**：2026-10-09

本目錄包含歷史記錄、總結報告等歸檔文檔。這些文檔主要用於記錄歷史，不影響日常使用。
歸檔文件中的狀態、下一步、Phase 或完成度描述，若與 Snapshot、6M Roadmap、版本 Roadmap 或 Architecture 衝突，一律以 active authority 為準。

## 2026-10-08 Coverage Map 歷史清冊

- [逐批文件整理與歸檔沿革](DOC_COVERAGE_HISTORY_2026.md)：收錄 Coverage Map 移出的日期化批次記錄、原路徑／封存路徑與 hash 證據。
- 現行權威邊界、文件同步矩陣與 DoD 仍由 [DOC_COVERAGE_MAP](../00_core/DOC_COVERAGE_MAP.md) 維護；本清冊只供追溯。

## 2026-10-09 文件治理規則與舊計畫索引

- [DOCUMENTATION_STRUCTURE 原第 4／6 節整理決策與更新流水帳](DOCUMENTATION_STRUCTURE_CHANGELOG_20261009_HISTORY.md)：保存抽離前的原文區塊；現行生命週期規則回到 [`DOCUMENTATION_STRUCTURE.md`](../00_core/DOCUMENTATION_STRUCTURE.md)。原區塊與完整快照 bytes／SHA 見 [Coverage History Entry 109](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-109)。
- 同一清冊補記既有的 [UI Qt roadmap audit](UI_QT_DEVELOPMENT_ROADMAP_AUDIT_2026_05_19.md)、[refactoring migration plan](REFACTORING_MIGRATION_PLAN_2025.md) 與 [safe refactoring report](SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md) 來源路徑及 SHA；這些都是歷史參考，不是目前計畫或狀態依據。

## 2026-10-09 平行工作流 plan／prompt 歷史

- [平行系統執行 master plan](superpowers/plans/2026-07-13-parallel-system-execution-master-plan.md) 與[工作流啟動 prompts](superpowers/prompts/2026-07-13-parallel-workstream-start-prompts.md)：保存 2026-07-13 的工作拆分、handoff 與當時 Git 操作流程。這些歷史原文不證明工作已完成，也不構成目前工作或 Git 寫入授權；舊路徑保留導引。bytes／SHA 與依賴範圍見 [Coverage History Entry 110](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-110)。

## 2026-10-09 Coverage Map 舊更新流水帳

- [Coverage Map 整理前更新記錄與快速索引快照](DOC_COVERAGE_MAP_CHANGELOG_20261009_HISTORY.md)：保存精簡前的全部日期化變更與逐批索引；現行權威、同步矩陣與 DoD 回到 [`DOC_COVERAGE_MAP.md`](../00_core/DOC_COVERAGE_MAP.md)，逐批原路徑／目的地／雜湊回到 Coverage History。來源區塊與快照雜湊見 [Entry 111](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-111)。

## 2026-10-09 備份保留稽核日期快照

- [Backup Retention Audit（2026-07-06）](BACKUP_RETENTION_AUDIT_2026_07_06_HISTORY.md)：保留當日 repo／FA_Data 備份來源、容量掃描與清理候選；其中 retention 規則摘要仍見每日資料更新指南，資產用途／恢復以較新的 [Storage Asset Register](../03_data/STORAGE_ASSET_REGISTER_20261006.md) 為準。歷史候選不構成目前搬移或刪除授權；原 QA／操作引用可經舊路徑短導引抵達。原件 bytes／SHA 與引用清單見 [Coverage History Entry 112](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-112)。

<a id="2026-10-09-r029-retirement-preflight"></a>
## 2026-10-09 R029 retirement preflight 歷史

- [R029 retirement gate 草稿](R029_RETIREMENT_GATE_DRAFT_20260925_HISTORY.md) 與[唯讀 caller／alias 預檢清冊](R029_RETIREMENT_PREFLIGHT_INVENTORY_20260925_HISTORY.md)：保留 2026-09-25 裁定前狀態與當時有限搜尋證據，不代表目前 caller 完整性或 cleanup 授權。現行裁定看 [implementation/acceptance report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R029_IMPLEMENTATION_REPORT.md) 與 [FINAL_MIGRATION_SEQUENCE](../01_architecture/target_architecture_2026_09_22/FINAL_MIGRATION_SEQUENCE.md)；原 QA 路徑保留相容導引，逐檔 bytes／SHA 見 [Coverage History Entry 098](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-098)。

<a id="2026-10-09-qa-historical-snapshots-scheduler-health-and-ux08-controller"></a>
## 2026-10-09 歷史 QA 快照：排程 health 與 UX08 controller handoff

- [Scheduler Health & Observability（2026-08-27）](SCHEDULER_HEALTH_OBSERVABILITY_REPORT_20260827_HISTORY.md)：保存當日五個邏輯任務的 read-only 狀態；不是目前 scheduler health。產生器只有在明確傳入 `--markdown-output` 時才寫檔，沒有固定 QA 路徑 consumer；現況以 Snapshot 與近期排程 QA 為準。
- [A 線正式與相鄰 lane latest-status review（2026-09-17）](A_OPERATIONS_LATEST_STATUS_REVIEW_2026_09_17_HISTORY.md)：保存當日 Formal／isolated Paper、BankTaiwan、official-events 與 Raw PIT 的唯讀狀態及未完成 Gate；reader 隔離修正未代表正式 job 已重跑。現況以 [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md) 與 [近期排程 QA](../06_qa/README.md) 為準；QA 舊路徑保留導引，原件 bytes／SHA 見 [Coverage History Entry 113](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-113)。
- [UX08 純 chart viewport controller handoff（2026-10-06）](UX08_CHART_VIEWPORT_STATE_QA_20261006_HISTORY.md)：保存整合前 controller API、測試與 owner 邊界；後續產品按鈕接線看 [UX08 viewport integration QA](../06_qa/UX08_VIEWPORT_INTEGRATION_20261006.md)，Native／真人驗收仍未完成。原 QA 路徑保留相容導引，hash 見 [Coverage History Entry 099](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-099)。

<a id="qa-historical-process-failure-review-20261009"></a>
## 2026-10-09 QA 歷史流程與失效分析

- [Branch/worktree 整理紀錄](BRANCH_WORKTREE_CONSOLIDATION_20260927_HISTORY.md)：保存 2026-09-27 當時的本機分支與工作樹盤點；目前 Git 狀態看實際 checkout 與 `PROJECT_SNAPSHOT`。
- [文件整併審查](DOCUMENTATION_CONSOLIDATION_20260927_HISTORY.md)：保存 2026-09-27 的文件盤點數字與整理方法；不是目前文件數量或現行索引。
- [舊推薦學習失效回顧](LEGACY_RECOMMENDATION_LEARNING_FAILURE_REVIEW_2026_09_21_HISTORY.md)：保留當日 read-only failure review 與 BankTaiwan capture 邊界；目前行為與狀態以 Snapshot、Architecture 及近期 QA 為準。

來源 `docs/06_qa/` 路徑保留短導引；原始 bytes／SHA 與其餘待覆核候選的處置見 [Coverage History Entry 097](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-097)。

- [唯讀服務合作式取消 QA（2026-09-30）](READ_ONLY_SERVICE_CANCELLATION_QA_20260930.md)：保留當次 cancellation suites 19 passed，以及另一組 service contracts 125 passed／1 failed 的原始分層結果。V5 readability acceptance 另有 fixture 調整後的通過收據，不改寫 9/30 結果。raw pytest logs 位於 ignored `output/qa/ui_shutdown_20260930/`，沒有封存進 repository；現行行為看 [`sqlite_read_only.py`](../../app_module/sqlite_read_only.py) 與 [取消回歸測試](../../tests/test_read_only_service_cancellation.py)。QA 舊路徑保留導引，逐檔 bytes／SHA 見 [Coverage History Entry 104](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-104)。

<a id="2026-10-09-qt-shutdown-teardown-bounded-qa"></a>
## 2026-10-09 Qt MainWindow shutdown teardown bounded QA

- [Qt MainWindow shutdown teardown 修正 QA（2026-09-15）](QT_SHUTDOWN_TEARDOWN_FIX_QA_2026_09_15.md)：保存 production MainWindow 在 `QApplication.exec()` 返回後的 Qt teardown hang 修正與 bounded 驗收。它沒有證明舊 memory-write popup 同根因，也沒有驗收仍在 QA 的 [Native crash read-only follow-up](../06_qa/QT_NATIVE_CRASH_READONLY_FOLLOWUP_2026_09_15.md) 或獨立 [SQLite inspector shutdown probe](../06_qa/QT_SQLITE_INSPECTOR_SHUTDOWN_PROBE_2026_09_15.md)。原 QA 路徑保留短導引；原文 bytes／SHA 與引用核對見 [Coverage History Entry 100](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-100)。

<a id="2026-10-09-position-health-calendar-cache-isolation-qa"></a>
## 2026-10-09 Position Health calendar-cache 測試隔離 QA

- [Position Health Source Provider Calendar Cache 隔離 QA（2026-09-15）](POSITION_HEALTH_SOURCE_PROVIDER_CALENDAR_CACHE_ISOLATION_QA_2026_09_15.md)：保留測試把年度 calendar cache 移至 isolated `tmp_path` fixture 的 bounded 修復收據。現行 test helper 仍在 [`tests/test_position_health_source_providers.py`](../../tests/test_position_health_source_providers.py)；這份歷史 QA 不代表 Position Health source-backed transition Gate 已結案。原 QA 路徑與歷史 Catalog 引用保留相容導引；逐檔 bytes／SHA 見 [Coverage History Entry 101](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-101)。

<a id="2026-10-09-ml-formal-input-candidate-snapshot"></a>
<a id="ml-dated-readiness-evidence-20261009"></a>
## 2026-10-09 ML Formal input candidate-only 歷史快照

- [ML allocation Formal input readiness（2026-09-20）](ML_ALLOCATION_FORMAL_INPUT_READINESS_2026_09_20.md)：保存 9/21 自然日之前的 candidate runtime wiring、source pins 與當時缺件；沒有執行 validator、writer 或 scheduler，也不是 9/21 的實際驗收。同期 Natural Shadow weekly receipts 屬不同 lane，不能替代這份 Formal candidate snapshot。原 QA 路徑保留相容導引；目前 Gate／狀態看 [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md)、[Gate 7](../06_qa/GATE_7_ML_SHADOW_ENGINEERING.md) 與 [External Validation Register](../06_qa/GATE_2_TO_7_EXTERNAL_VALIDATION_REGISTER.md)，逐檔 bytes／SHA 見 [Coverage History Entry 102](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-102)。

## 2026-10-09 V4.2 Daily Recommendation Learning 9/13 歷史 QA

- [每日推薦自動學習與受控調整 QA（2026-09-13）](V4_2_DAILY_RECOMMENDATION_LEARNING_2026_09_13_HISTORY.md)：保存單一 learning task 註冊與 bounded CLI entrypoint 驗證，不代表 task 已執行、正式推薦權重變更、promotion 或 production evidence credit。現況看 [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md)，工程邊界看 [Gate 7](../06_qa/GATE_7_ML_SHADOW_ENGINEERING.md)，操作看 [Application Manual](../07_guides/APPLICATION_MANUAL.md)。舊 QA 路徑保留導引，bytes／SHA 見 [Coverage History Entry 105](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-105)。

## 2026-10-09 Weekly Natural Evidence 9/20 歷史快照

- [Weekly Natural Evidence Review（2026-09-20）](WEEKLY_NATURAL_EVIDENCE_REVIEW_2026_09_20_HISTORY.md)：保留 9/14–20 週期與 9/21 唯讀觀測；V2.2 collection、BankTaiwan capture、ML natural shadow 是不同 lane，pending 不等於 matured／promotion／Formal／human approval。現況看 [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md) 與 [Gate 7](../06_qa/GATE_7_ML_SHADOW_ENGINEERING.md)。舊 QA 路徑保留導引，原件 SHA 見 [Coverage History Entry 106](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-106)。

## 2026-10-09 Watchlist analysis／ML visibility 9/6 歷史 QA

- [觀察清單分析與 ML 可見性驗收（2026-09-06）](WATCHLIST_ANALYSIS_ML_HANDOFF_2026_09_06_HISTORY.md)：保留 Watchlist 摘要／導覽與當日 readiness inspection；`0/3` 與 stale projection 不是目前 ML 狀態，也沒有啟用訓練或 promotion。現行操作看 [Application Manual](../07_guides/APPLICATION_MANUAL.md)，來源邊界看 [system architecture](../01_architecture/system_architecture.md)，Gate／現況看 Gate 7／Snapshot。原 QA 路徑保留導引，SHA 見 [Coverage History Entry 107](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-107)。

## 2026-10-09 9/14 排程與週資料受託審查歷史

- [排程與週資料受託審查（2026-09-14）](SCHEDULED_OPERATIONS_OWNER_REVIEW_2026_09_14_HISTORY.md)：單次 `reviewed_with_follow_up` 記錄，正式採認未通過；保留 SQLite read-only 檢查與 warning／持倉證據的日期範圍，不代表 CSV／SQLite 全量一致、目前 scheduler 狀態或出場建議。現況看 [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md) 與近期排程 QA。原 QA 路徑保留相容導引，bytes／SHA 見 [Coverage History Entry 103](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-103)。

## 2026-10-08 V1.5／V1.9 plan/spec history

- [V1.5 Data Credibility plan](superpowers/plans/2026-07-04-v1-5-data-credibility.md) 與 [design spec](superpowers/specs/2026-07-04-v1-5-data-credibility-design.md)：保留完整原文；v1 closeout 範圍以 [QA 收據](V1_5_DATA_CREDIBILITY_CLOSEOUT_2026_07_04.md) 為準。原計畫未勾項目仍留作歷史，QA 未證明外部來源採用、調整後價格整合、ScoringEngine 或正式排程完成。
- [V1.9 Read-only Agent MCP plan](superpowers/plans/2026-07-06-v1-9-read-only-agent-mcp.md) 與 [design spec](superpowers/specs/2026-07-06-v1-9-read-only-agent-mcp-design.md)：唯讀 v1 closeout 依 [QA 收據](V1_9_READ_ONLY_AGENT_MCP_CLOSEOUT_2026_07_06.md) 判讀；計畫留有未勾項目，weekly evidence、人工 UI smoke、多日 dry-run、真實 workflow sample 等不視為由該 closeout 自動完成。歷史文件不授權 production scheduler 或寫入。
- 四份 `docs/superpowers/` 原位置保留短導引；目前狀態與架構分別看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 及 [system architecture](../01_architecture/system_architecture.md)。bytes、SHA-256、old→new 路徑與生命週期判讀見 [plan/spec archive manifest](SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md)。

## 2026-10-08 資料實作摘要

- [Month 5 Fundamental Source Inventory（截至 2026-08-12）](FUNDAMENTAL_SOURCE_INVENTORY_HISTORY_20260812.md)：保留基本面來源搜尋、available_date／PIT 缺口及候選工作歷史；目前狀態看 [Snapshot](../00_core/PROJECT_SNAPSHOT.md)，來源與接受判斷看 [近期基本面 QA](../06_qa/README.md) 及 current architecture。
- [產業指數更新摘要](INDUSTRY_INDEX_UPDATE_SUMMARY_HISTORY.md)：保留舊 CSV／API 更新步驟；現行操作看 [每日資料更新指南](../03_data/daily_data_update_guide.md) 與 [操作手冊](../07_guides/APPLICATION_MANUAL.md)。
- [合併與大盤指數實作摘要](MERGE_AND_MARKET_INDEX_SUMMARY_HISTORY.md)：保留舊 merge、CSV 路徑及欄位假設；現行架構看 [system_architecture](../01_architecture/system_architecture.md)，操作看每日資料更新指南與操作手冊。
- [SQLite 雙軌相容指南（2026-06-02）](SQLITE_STORAGE_GUIDE_HISTORY_20260602.md)：保留 v1.1 CSV-SSOT／SQLite-cache 描述、當時遷移步驟與效能聲稱；目前資料保存與同步邊界看 [system_architecture](../01_architecture/system_architecture.md)，操作看每日資料更新指南與操作手冊。
- [CSV 全量重建指南](DATA_REBUILD_GUIDE_HISTORY.md)：保留舊 `merge_daily_data.py --force-all`／`calculate_technical_indicators.py --force-all` 操作說明，不作目前修復程序；操作看 [每日資料更新指南](../03_data/daily_data_update_guide.md) 與 [操作手冊](../07_guides/APPLICATION_MANUAL.md)。
- [推薦分析資料流程（舊版）](RECOMMENDATION_ANALYSIS_DATA_FLOW_LOGIC_HISTORY.md)：保留舊 CSV／`ui_app`／`StrategyConfigurator` 流程；目前資料來源與指標重用邊界以 [system_architecture](../01_architecture/system_architecture.md) 為準。
- [每日更新故障排除指南（舊版）](TROUBLESHOOTING_DAILY_UPDATE_HISTORY.md)：保留已過時的 log／資料路徑與早期 API 排錯命令；目前更新操作看 [APPLICATION_MANUAL 第 4 節](../07_guides/APPLICATION_MANUAL.md#4-數據更新)，排錯看第 12 節。

### 2026-10-08 Backtest Lab checklist and FAQ snapshots

- [回測頁功能清單與進度快照](BACKTEST_LAB_CHECKLIST.md)：原文保留舊待辦，例如將已提供的報告匯出列為待實作；只供追溯，不代表目前功能缺口。
- [回測 FAQ](BACKTEST_LAB_FAQ.md)：保留早期路徑、流程與建議，其中一些已不適用目前架構及操作；不要照舊命令或策略建議操作。

目前功能契約以 [BACKTEST_LAB_FEATURES](../02_features/BACKTEST_LAB_FEATURES.md) 為準，操作、安全限制與排錯以 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 為準。原 `docs/02_features/` 路徑保留短導引。

## 2026-10-08 歸檔

### 2026-10-08 Data and source-owner receipts

- **資料／介面快照**：[Data Update display refresh（8/30）](DATA_UPDATE_DISPLAY_REFRESH_2026_08_30.md)、[Formal data reconciliation（8/06）](FORMAL_DATA_RECONCILIATION_2026_08_06.md)。這些是當日觀察，不是目前資料可得性或正式完成結論。
- **Source／owner bounded evidence**：[Owner production readiness（8/06）](OWNER_PRODUCTION_READINESS_2026_08_06.md)、[P0 license capture（8/28）](P0_LICENSE_EVIDENCE_CAPTURE_2026_08_28.md)、[P0 MOPS owner packet（8/28）](P0_MOPS_OWNER_PACKET_REFRESH_2026_08_28.md)、[TWSE T86 20-day pilot](TWSE_T86_20_DAY_CANDIDATE_PILOT_2026_07.md)。保留原授權、provenance、coverage 與 pilot 邊界；較新的 P0 handoff 見 [8/30 evidence refresh](../06_qa/P0_EVIDENCE_REFRESH_2026_08_30.md)，目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-08 Prospective Formal clock history

七份收據保存 2026-08-18 至 08-28 的 clock activation、execution、weekly update、calendar capture、staging 及失敗邊界。它們是當時的歷史證據，不代表目前已重啟、已產生 formal output 或取得發布授權；目前方向與時鐘契約仍看 QA 的 [Prospective Formal restart direction](../06_qa/PROSPECTIVE_FORMAL_RESTART_DIRECTION_2026_08_19.md)。8/26 staging 是一次性具名例外，不應泛化成常規流程。

- **啟動與執行紀錄**：[8/18 clock activation](PROSPECTIVE_FORMAL_CLOCK_ACTIVATION_2026_08_18.md) → [8/21 restart execution](PROSPECTIVE_FORMAL_RESTART_EXECUTION_2026_08_21.md) → [8/25 weekly update](PROSPECTIVE_FORMAL_RESTART_WEEKLY_UPDATE_2026_08_25.md)。
- **Staging／calendar 收據**：[8/26 named staging](PROSPECTIVE_FORMAL_RESTART_CLOCK_2026_08_26_STAGING.md)、[8/27 V3 staging](PROSPECTIVE_FORMAL_RESTART_CLOCK_2026_08_27_V3_STAGING.md)、[8/28 staging](PROSPECTIVE_FORMAL_RESTART_CLOCK_2026_08_28_STAGING.md)、[8/28 calendar capture](PROSPECTIVE_FORMAL_CALENDAR_CAPTURE_2026_08_28.md)。

### 2026-10-08 V2/V3/V4 dated readiness reports

這六份文件保存 2026-07 的 paper baseline、工程 readiness、人工驗證及 7/30 release-freeze 收據。V2.4／V2.5 首份 paper baseline 未達 formal closeout；V3.0 的 `ready_for_manual_validation` 與 `DEFER_ALL_PRUNING_DECISIONS` 僅是當時的工程／資料決議；7/30 V4 report 已明確標為 historical／superseded。它們均不代表目前 maturity、production readiness 或投資有效性；目前狀態回到 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，8/29 詳細歷史快照見 [Program Status Rebaseline 歸檔原文](PROGRAM_STATUS_REBASELINE_2026_08_29.md)。

- **V2.4／V2.5 paper baselines**：[V2.4](V2_4_PAPER_BASELINE_2026_07_12.md)、[V2.5 position health](V2_5_POSITION_HEALTH_BASELINE_2026_07_12.md)。
- **V3.0 engineering readiness／manual validation**：[automated readiness](V3_0_AUTOMATED_READINESS_2026_07_12.md)、[engineering candidate manual validation](V3_0_ENGINEERING_CANDIDATE_MANUAL_VALIDATION_REPORT_2026_07_08.md)、[Week 1 manual validation](V3_0_WEEK1_MANUAL_VALIDATION_2026_07_12.md)。
- **V4.0 dated release freeze**：[operational production closeout report](V4_0_OPERATIONAL_PRODUCTION_CLOSEOUT_2026_07_30.md)。
- **V2.4 paper-only approval decisions**：2026-07-12 的 [policy baseline 核准](V2_4_PAPER_POLICY_APPROVAL_2026_07_12_HISTORY.md) 與 [Portfolio Coach scope 開工核准](V2_4_SCOPE_APPROVAL_2026_07_12_HISTORY.md)；核准範圍限於工程與 paper／research simulation，沒有真實交易授權。舊 QA 路徑保留相容導引；目前唯讀操作邊界看 [Application Manual](../07_guides/APPLICATION_MANUAL.md) 與 [system architecture](../01_architecture/system_architecture.md)。

### 2026-10-08 Program Status Rebaseline snapshot

[Program Status Rebaseline（2026-08-29）](PROGRAM_STATUS_REBASELINE_2026_08_29.md) 記錄當時全專案七個 readiness lanes、Gate blockers 與 8/30 更新收據。報告中的 current／ready 數字是日期快照，現況以 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 為準；原 QA 路徑保留相容導引，內部連結分別指向仍留在 QA 的 P0／Evidence handoff 及 Archive 原件。

### 2026-10-08 ML storage retention cleanup custody

[ML Release v4 Storage Retention Cleanup（2026-08-29）](ML_RELEASE_V4_STORAGE_RETENTION_CLEANUP_2026_08_29.md) 保存使用者授權的一次性 release_v4 清理範圍、不可逆性、before／after inventory、保留鏈與 tombstone。它不是目前容量或 run inventory；現行 retention policy 看 [system architecture §11.1](../01_architecture/system_architecture.md#111-immutable-ml-publication-retention)，操作程序看 [Application Manual Supplements](../07_guides/APPLICATION_MANUAL_SUPPLEMENTS.md)。原 QA 路徑保留相容導引。

### 2026-10-08 Program readiness refresh details

- [Runtime／Performance Readiness Refresh（2026-08-30）](RUNTIME_PERFORMANCE_READINESS_REFRESH_2026_08_30.md)：保留當日容量、`preflight-only` 與 canary owner packet；不是目前 runtime readiness。
- [Paper Portfolio Readiness Refresh（2026-08-30）](PAPER_PORTFOLIO_READINESS_REFRESH_2026_08_30.md)：保留當日 snapshot／fills／cost ledger 盤點；不是目前 Paper 狀態。
- [Formal／ML Input Readiness Refresh（2026-08-30）](FORMAL_INPUT_READINESS_REFRESH_2026_08_30.md)：保留當日 strict `0/3` 與 owner-controlled input 證據；不是目前 validator 結果。

三份文件補充同日的 Program Status Rebaseline；目前狀態以 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 為準，QA 原路徑保留相容導引。

### 2026-10-08 BALDR September integration closeout and readiness history

以下文件保存 2026-09-25／26 的產品整合盤點、排程 inventory、evidence-model readback、technical parser closeout，以及已套用 automation prompt 的 before／after 與 request receipt。這些是已結束的日期快照；目前產品缺口、排程與 ML readiness 分別看 [QA 主題地圖](../06_qa/README.md) 與 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。舊 QA 路徑保留相容導引；原始 JSON request／inventory receipt 也在此封存，並非現行操作設定。

- [BALDR product integration acceptance（9/25–26）](BALDR_PRODUCT_INTEGRATION_ACCEPTANCE_20260925.md)：當時的跨線盤點及後續 closeout；不代表目前完成度。
- [Windows Scheduler reconciliation（9/25）](BALDR_SCHEDULER_RECONCILIATION_20260925.md) 與 [結構化 inventory JSON](BALDR_SCHEDULER_RECONCILIATION_20260925.json)：保留當時唯讀匯出與原始 hash。
- [Daily evidence-model readiness（9/25）](BALDR_DAILY_EVIDENCE_MODEL_READINESS_20260925.md)：當日 maturity／candidate readback，非目前模型資格。
- [Daily technical parse／partial-failure QA（9/25）](BALDR_DAILY_TECHNICAL_PARSE_DIAGNOSTIC_QA_20260925.md)：完成的隔離 bug-fix 驗證。
- [Paper automation prompt proposal（9/25）](BALDR_PAPER_AUTOMATION_PROMPT_PROPOSAL_20260925.md) 與 [update request JSON](BALDR_PAPER_AUTOMATION_UPDATE_REQUEST_20260925.json)：9/26 已套用並 read back；目前 prompt／task 狀態仍須看近期 inventory。

Product-integration baseline 與 Codex automation inventory 的大型 JSON 伴隨物是本機 ignored 檔，依排除規則沒有移動或提交；它們留在 QA 原路徑供當前工作樹中的歸檔報告連結。乾淨 checkout 可能不含這兩個本機 sidecar。

### 2026-10-08 V2.3 data-source decision receipts

- [V2.3 P0 Sources Batch Principle Approval（2026-07-12）](V2_3_BATCH_PRINCIPLE_APPROVAL_2026_07_12.md) 保存使用者核准 13 個 P0 source 的導入方向；下游 eligibility 當時仍為 `none`，不是來源接受或正式 ingestion 授權。
- [V2.3 FinMind Candidate Source Audit（2026-07-12）](V2_3_FINMIND_CANDIDATE_SOURCE_AUDIT_2026_07_12.md) 保存當時帳戶權限與 dataset / available-date 限制；帳戶方案可能改變，不把歷史權限當成目前狀態。

目前逐來源決議以 [P0 Source Acceptance Register](../06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md) 與 [近期資料來源 QA](../06_qa/README.md) 為準；兩份原 QA 路徑保留相容導引。

### 2026-10-08 LUNA three-line integration history

- [Luna A data／ML handoff（9/7）](LUNA_A_HANDOFF_2026_09_07.md) 與 [Luna C UI/UX handoff（9/7）](LUNA_C_HANDOFF_2026_09_07.md)：保留各線交付當時的範圍、未完成項、驗收限制及 rollback 邊界。
- [LUNA integration closeout（9/8）](LUNA_INTEGRATION_CLOSEOUT_2026_09_08.md)：整合缺陷、當時完整驗證及 Git 收尾的最終收據；其測試數字不代表目前 HEAD。

Luna B handoff 與 pre-integration [Project Consolidation Review](../06_qa/PROJECT_CONSOLIDATION_REVIEW_2026_09_07.md) 保留在 QA，因 repository inventory／repo-map audits 直接讀取這兩份原始文件；舊 QA 路徑仍保留導引。當前程式與狀態分別看 system architecture 與 PROJECT_SNAPSHOT。

### 2026-10-08 Decision workbench and continuity audit history

三份 2026-09-14／15 audit 記錄當時的全決策工作台整合證據、下一增量判讀及 continuity write-path 保存鏈缺口。另封存一份 pre-R1 continuity loop gap audit；它列出的 Workbench projection 缺口由後續 R1 QA 驗收，不能再當成目前待辦。內文中的日期化優先序不取代 Snapshot／Roadmap，也不直接授權後續工程；原 QA 路徑保留相容導引。

- [終極決策工作台整合缺口矩陣（9/14）](ULTIMATE_DECISION_WORKBENCH_2026_09_14.md)
- [終極目標產品完成度與下一增量稽核（9/15）](ULTIMATE_NEXT_INCREMENT_AUDIT_2026_09_15.md)
- [Decision Continuity write-path audit（9/14）](DECISION_CONTINUITY_WRITE_PATH_AUDIT_2026_09_14.md)
- [Continuity Review Loop pre-R1 gap audit（9/15）](CONTINUITY_REVIEW_LOOP_GAP_AUDIT_2026_09_15.md)：保留 R1 前的 gap baseline；後續 R1 acceptance 留在 [QA](../06_qa/CONTINUITY_REVIEW_WORKBENCH_R1_QA_2026_09_15.md)，完整跨頁旅程仍看留在 QA 的 [acceptance plan](../06_qa/CROSS_PAGE_DECISION_JOURNEY_ACCEPTANCE_PLAN_2026_09_15.md)。

### 2026-10-08 Early decision and industry journey receipts

八份 2026-09-14／15 收據保存當時的 bounded write-path、read-model、UI、watchlist 儲存啟用、MainWindow shutdown／child readback、日期化 daily investment snapshot、synthetic-fixture MainWindow acceptance 與 current-research industry smoke。Decision／Outcome 的後續 reader 證據看 [R1 Workbench QA](../06_qa/CONTINUITY_REVIEW_WORKBENCH_R1_QA_2026_09_15.md)，目前更完整的驗收範圍仍由 [open acceptance plan](../06_qa/CROSS_PAGE_DECISION_JOURNEY_ACCEPTANCE_PLAN_2026_09_15.md) 追蹤；產業 smoke 的 PIT eligible 為 0，較新 provenance、UI observation 與 source/caller gate 看 [WP2 current provenance](../06_qa/WP2_INDUSTRY_INDEX_CURRENT_PROVENANCE_20260928.md)、[WP2 UI observation](../06_qa/WP2_INDUSTRY_INDEX_UI_OBSERVATION_20260928.md)、[PIT taxonomy](../06_qa/PIT_TAXONOMY_DAILY_SOURCE_QA_2026_09_15.md) 與 [industry caller acceptance](../06_qa/PIT_INDUSTRY_CALLER_ACCEPTANCE_QA_2026_09_15.md)。MainWindow acceptance 使用 synthetic Market／Industry 與 Portfolio fixtures，不代表自然／正式 outcome 或 PIT qualification 已成立。screenshots、capture manifest、raw JSON 與 runner logs 均為本機 sidecar，未隨文件封存。

- [Decision Continuity Write Path Increment A QA（9/14）](DECISION_CONTINUITY_WRITE_PATH_QA_2026_09_14.md)
- [Decision Continuity Increment B QA（9/14）](DECISION_CONTINUITY_INCREMENT_B_QA_2026_09_14.md)：保留當時 isolated widget smoke、exact identity 與 explicit watchlist storage activation 驗收；測試數字不是目前基線。
- [Decision Continuity Increment C QA（9/14–15）](DECISION_CONTINUITY_INCREMENT_C_QA_2026_09_14.md)：保留當時 launcher／TPEX cancellation、MainWindow close lifecycle 與獨立 child readback；不代表完整跨頁 acceptance。
- [Daily Investment Journey QA（9/14）](DAILY_INVESTMENT_JOURNEY_2026_09_14.md)：唯讀資料、evidence／learning projection 與未完成項的日期快照；候選數與 maturity 數字不作目前狀態。
- [真實 MainWindow 跨頁決策旅程 acceptance（9/15）](CROSS_PAGE_DECISION_JOURNEY_MAINWINDOW_2026_09_15.md)：當時的 bounded path 使用 synthetic upstream fixture；完整目前驗收範圍仍看 QA 中的 open acceptance plan。
- [Decision → Outcome Journey read model QA（9/14）](DECISION_OUTCOME_JOURNEY_2026_09_14.md)
- [Decision → Outcome Journey UI QA（9/14）](DECISION_OUTCOME_JOURNEY_UI_2026_09_14.md)
- [產業強弱與產業→個股決策旅程 QA（9/14）](INDUSTRY_DECISION_JOURNEY_2026_09_14.md)

### 2026-10-08 Early QA closeouts

- **Evidence Rehearsal**：[工程 closeout](EVIDENCE_REHEARSAL_ENGINEERING_CLOSEOUT_2026_07_14.md) → [real E2E closeout](EVIDENCE_REHEARSAL_REAL_E2E_CLOSEOUT_2026_07_13.md)。現行操作步驟仍以 [Evidence Rehearsal Runbook](../07_guides/EVIDENCE_REHEARSAL_RUNBOOK.md) 為準。
- **Gate／ML bounded closeouts**：[Gate 1 Advice](GATE_1_ADVICE_CLOSEOUT_2026_07_12.md)、[Gate 2–7 pure engineering](GATE_2_TO_7_PURE_ENGINEERING_CLOSEOUT_2026_07_12.md)（External Register／Control Center 的舊引用由轉址承接）、[historical ML Shadow MVP](HISTORICAL_ML_SHADOW_MVP_CLOSEOUT_2026_07_15.md)。pure-engineering 收據不等於目前 external qualification；狀態回到 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 與 [External Validation Register](../06_qa/GATE_2_TO_7_EXTERNAL_VALIDATION_REGISTER.md)。
- **Healthcheck／PIT／project audit**：[Full App agent closeout](FULL_APP_HEALTHCHECK_AGENT_CLOSEOUT_2026_06_23.md)、[PIT historical data repair](PIT_HISTORICAL_DATA_REPAIR_CLOSEOUT_2026_07_15.md)、[PROJECT_SNAPSHOT audit](PROJECT_SNAPSHOT_AUDIT_2026_07_12.md)、[shim removal audit](SHIM_LEGACY_REMOVAL_AUDIT_2026-07-12.md)。目前測試覆蓋看 [Full App coverage mapping](../06_qa/FULL_APP_HEALTHCHECK_COVERAGE_MAPPING_2026_06_24.md)，目前狀態看 Snapshot。
- **文件治理／執行藍圖**：[Gemini documentation adjudication](GEMINI_DOCUMENTATION_CROSS_AUDIT_ADJUDICATION_2026_07_13.md)、[Superpowers date audit](SUPERPOWERS_PLAN_SPEC_DATE_AUDIT_2026_07_06.md)、[system execution blueprint closeout](SYSTEM_EXECUTION_BLUEPRINT_CLOSEOUT_2026_07_15.md)。目前文檔生命週期看 [DOCUMENTATION_STRUCTURE](../00_core/DOCUMENTATION_STRUCTURE.md)，目前架構看 [system_architecture](../01_architecture/system_architecture.md)。原 QA 路徑保留短轉址。

### 2026-10-08 Early Recommendation and Update Tab QA

四份早期產品 QA 問題盤點與摘要記錄推薦分析、數據更新 Tab 的舊程式路徑、測試快照及當時待覆驗事項。推薦分析摘要曾記錄所有測試配置皆回傳 0 筆推薦，因此不能把它解讀成目前已驗收或已修復；數據更新摘要中的測試數字也只屬當時結果。現行操作與排錯看 [Application Manual](../07_guides/APPLICATION_MANUAL.md)，測試範圍看 [Feature-to-test routing matrix](../06_qa/FEATURE_TEST_ROUTING_MATRIX_2026_06_23.md)。四份原文逐位元組保留，QA 原路徑提供相容導引。

- [Recommendation Tab issues](QA_RECOMMENDATION_TAB_ISSUES.md) · [Recommendation Tab summary](QA_RECOMMENDATION_TAB_SUMMARY.md)
- [Update Tab issues](QA_UPDATE_TAB_ISSUES.md) · [Update Tab summary](QA_UPDATE_TAB_SUMMARY.md)

### 2026-10-08 Source, clock and probability-learning audits

以下文件保存已完成的 2026-09-15／16 discovery、read-only source design 與有界機率學習 audit。來源／caller 的後續驗收仍留在 QA；clock 與 ML 原文中的日期狀態及當時建議只供追溯，現況回到 Snapshot、Manual 與 QA 主題地圖。原 QA 路徑保留短轉址。

- [Decision Desk／Evidence capture 真實時鐘 QA（9/16）](DECISION_EVIDENCE_CAPTURE_CLOCK_QA_2026_09_16.md)：保存 clock 修正、跨線 readback 與當時後續事項，不作目前排程狀態。
- [PIT 產業來源驗收 discovery（9/15）](PIT_INDUSTRY_SOURCE_ACCEPTANCE_DISCOVERY_2026_09_15.md)：source/wiring discovery baseline；後續 caller acceptance 與 taxonomy source QA 仍在 QA。
- [PIT taxonomy daily source plan（9/15）](PIT_TAXONOMY_DAILY_SOURCE_PLAN_2026_09_15.md)：read-only source/design proposal；後續實作與驗收看 QA 原件。
- [每日機率學習下一增量 audit（9/15）](DAILY_PROBABILITY_LEARNING_NEXT_INCREMENT_AUDIT_2026_09_15.md)：保存 P1 實作補報及審計界線，不代表目前 ML 待辦或 adoption。

### 2026-07 Broker Flow and UI closeout

- **Broker Flow dashboard 效能鏈**：[原始 dashboard failed gate](BROKER_FLOW_SQLITE_DASHBOARD_PERFORMANCE_2026_07_15.md) → [後續 semantics scoped pass](BROKER_FLOW_SEMANTIC_OPTIMIZATION_2026_07_15.md)。保留原始完整母體與失敗數據，以及後續針對語意批次的優化證據；後者不改寫前一 gate，也不代表目前整體效能資格。
- **Readability polish closeout**：[UI / UX 收據（2026-07-07）](UI_UX_READABILITY_POLISH_CLOSEOUT_2026_07_07.md)。保存當時 bounded UI slice 與 formal-data waits；目前 UI 行為看 [system architecture](../01_architecture/system_architecture.md)、操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)、目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。原 QA 路徑保留短轉址。

### 2026-10-08 R001, R006, R020 historical QA

- [R001 baseline inventory](REFACTOR_BASELINE_R001_20260922_HISTORY.md)：原範圍已在 [R031 task index](../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 標記 CLOSED；保留起始 inventory 與來源基線。
- [R006 ML ABI baseline](REFACTOR_ML_ABI_BASELINE_R006_20260922_HISTORY.md)：原 inventory／retention scope 已關閉；未知 formal artifact 仍未載入或預測，細節見 [R006 dated addendum](../06_qa/R006_UNKNOWN_ARTIFACT_RETENTION_ADDENDUM_20260927.md)。
- [R020 post-score deferred-threshold QA](R020_POST_SCORE_DEFERRED_THRESHOLD_STAGES_20260925_HISTORY.md)：2026-09-25 的 dated review；bounded R005 replay／recovery disposition 及範圍見 [R031 task index](../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)。三個 QA 原路徑保留短轉址；封存不擴大 task 的驗收範圍。

### 2026-10-08 V4 Data, Direct and stock-research handoff history

三份 2026-09-08 owner handoff 保存當時的資料更新 freshness／calendar evidence、Direct capacity gate／年度 consumer readback、個股研究報告 UI 與 source coverage 驗收。它們的日期數字與 next step 不代表目前狀態；後續資料收尾見 [10/03 data closeout](../06_qa/FINAL_DATA_CLOSEOUT_AND_COMMIT_20261003.md)，現行操作看 [Application Manual](../07_guides/APPLICATION_MANUAL.md)，ML／Direct 狀態以 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 為準。舊 QA 路徑保留相容導引。

- [V4 Data freshness handoff（9/8）](V4_DATA_FRESHNESS_HANDOFF.md)：保留 source matrix、官方交易日曆修補與當時月營收／季報 blocker。
- [V4 Direct／OOC／Release handoff（9/8）](V4_DIRECT_RELEASE_HANDOFF.md)：保留 Direct capacity gate、2014–2020 readback 與 release preflight 邊界。
- [V4 Stock Research Report handoff（9/8）](V4_STOCK_RESEARCH_REPORT_HANDOFF.md)：保留當時 UI／source coverage／操作與驗收證據。

### 2026-10-08 V4 NEXT handoff history

2026-09-08 的 Formal／Paper、ML／Effectiveness 與 Operations handoff 保存當時的 owner scope、證據與 rollback；內文的 Next 項目不代表目前授權或待辦。Formal 的 9/30 後續讀回見 [scheduler bootstrap repair](../06_qa/SCHEDULER_FORMAL_BOOTSTRAP_REPAIR_20260930.md)，目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。

- [V4 NEXT Formal／Paper handoff](V4_NEXT_FORMAL_HANDOFF_2026_09_08_HISTORY.md)
- [V4 NEXT ML／Effectiveness handoff](V4_NEXT_ML_HANDOFF_2026_09_08_HISTORY.md)
- [V4 NEXT Ops handoff](V4_NEXT_OPS_HANDOFF_2026_09_08_HISTORY.md)

### 2026-10-08 V4 9/8 workspace cleanup receipts

兩份 2026-09-08 工作區盤點與清理收尾記錄保留當日數字、路徑界線與實際清理限制；它們不是即時 inventory 或現行清理授權。逐檔 output manifest 當時留在 ignored 本機 `output/`，沒有提交或隨文件封存。原 QA 路徑保留短導引；目前檔案與清理規範須回核現行文件及 Git exclusion。

- [工作區檔案盤點](WORKSPACE_FILES_AND_CLEANUP_2026_09_08.md)
- [V4 工作區清理收尾](V4_WORKSPACE_CLEANUP_CLOSEOUT.md)

### 2026-10-08 workspace commit validation history

2026-09-26 的分批提交驗證是特定 HEAD／dirty worktree 的工程快照；報告明示 focused routes 和廣域 mypy 結果，不代表全 repository pytest、正式資料或排程驗收。root `.tmp_*`／`.obsidian` 忽略規則與 fixture 調整保留為當日處置證據；現況以 Snapshot、最新 Git state 與 git exclusions 為準。歷史 Catalog 的 QA 原路徑由短導引承接。

- [2026-09-26 工作區分批提交驗證](WORKSPACE_BATCHED_COMMIT_VALIDATION_20260926_HISTORY.md)

- **歷史 Phase／SOP 原文（2026-10-08）**：[Phase 2 architecture](PHASE2_ARCHITECTURE.md)、[Phase 2 strategy library](PHASE2_STRATEGY_LIBRARY.md)、[Phase 2A data source audit](PHASE_2A_DATA_SOURCES_AUDIT.md)、[Phase 2.5 completion](PHASE2_5_COMPLETION_STATUS.md)、[Phase 3.3b research design](PHASE3_3B_RESEARCH_DESIGN.md)、[Epic 2 architecture](EPIC2_MVP2_ARCHITECTURE_DESIGN.md)、[Epic 2 checklist](EPIC2_MVP2_IMPLEMENTATION_CHECKLIST.md)、[Phase 4 portfolio design](PHASE4_PORTFOLIO_DESIGN.md)、[Phase 4 startup summary](PHASE4_STARTUP_SUMMARY.md)、[研究迭代 Playbook](phase3_5_research/RESEARCH_ITERATION_PLAYBOOK.md)、[指標判讀優先順序](phase3_5_research/METRIC_INTERPRETATION_PRIORITY.md)、[Benchmark 呈現](phase3_5_research/BENCHMARK_PRESENTATION.md)、[Phase 4 進入條件](phase3_5_research/PHASE4_ENTRY_CRITERIA.md)。原 `docs/05_phases/` 路徑保留轉址，原文未改寫；目前狀態不由歷史 Phase 文件判讀。

### Post-V1 Evidence Pipeline QA

2026-07 的階段性 QA／working-copy smoke／scheduler readiness 收據，保存當時的驗證與限制；不作目前排程操作或產品狀態權威。目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 與本目錄的較新 QA 收據。`docs/06_qa/POST_V1_*.md` 舊路徑保留短轉址。

- **Evidence store／source／replay**：[Event Store](POST_V1_EVIDENCE_EVENT_STORE_QA_2026_07_01.md)、[Importers](POST_V1_EVIDENCE_IMPORTERS_QA_2026_07_02.md)、[Source persistence](POST_V1_EVIDENCE_SOURCE_PERSISTENCE_QA_2026_07_04.md)、[Historical replay](POST_V1_HISTORICAL_EVIDENCE_REPLAY_QA_2026_07_06.md)。
- **Forward outcome／review**：[Forward read model](POST_V1_FORWARD_PERFORMANCE_READ_MODEL_QA_2026_07_03.md)、[Dashboard](POST_V1_FORWARD_PERFORMANCE_DASHBOARD_QA_2026_07_05.md)、[Decision quality](POST_V1_DECISION_QUALITY_REVIEW_QA_2026_07_10.md)、[Review dashboards](POST_V1_EVIDENCE_REVIEW_DASHBOARDS_QA_2026_07_11.md)、[UI smoke](POST_V1_EVIDENCE_REVIEW_UI_SMOKE_CHECKLIST_2026_07_12.md)、[Live vs research gap](POST_V1_LIVE_RESEARCH_GAP_LINKAGE_QA_2026_07_08.md)、[Signal decay](POST_V1_SIGNAL_DECAY_MONITOR_QA_2026_07_09.md)。
- **Operations／scheduler**：[Weekly history run](POST_V1_EVIDENCE_OPERATIONS_WEEKLY_HISTORY_RUN_2026_07_03.md)、[multi-day dry run](POST_V1_EVIDENCE_PIPELINE_MULTI_DAY_DRY_RUN_RECORD.md)、[working-copy smoke](POST_V1_EVIDENCE_DECISION_DESK_WORKING_COPY_SMOKE_2026_07_03.md)、[approval checklist](POST_V1_EVIDENCE_PRODUCTION_SCHEDULER_APPROVAL_CHECKLIST_2026_07_07.md)、[approval SOP](POST_V1_EVIDENCE_SCHEDULER_APPROVAL_SOP.md)、[scheduler dry run](POST_V1_EVIDENCE_SCHEDULER_DRY_RUN_QA_2026_07_06.md)、[scheduled dry-run history](POST_V1_EVIDENCE_SCHEDULED_DRY_RUN_QA_2026_07_12.md)、[scheduled pipeline](POST_V1_SCHEDULED_EVIDENCE_PIPELINE_QA_2026_07_12.md)。
- **Versioned evidence operations**：[V1.3 operations](POST_V1_V1_3_EVIDENCE_OPERATIONS_QA_2026_07_03.md) · [V1.4 review history](POST_V1_V1_4_EVIDENCE_REVIEW_HISTORY_QA_2026_07_03.md)。

### V4 2026-09-07 bounded evidence

以下是 2026-09-07 的 bounded data recovery、machine review 與 ML release 收據，不代表目前 source acceptance、ML eligibility 或待辦狀態。資料後續收尾見 [10/03 data closeout](../06_qa/FINAL_DATA_CLOSEOUT_AND_COMMIT_20261003.md)；目前判讀看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 與後續 QA。

- [V4 data recovery record](V4_DATA_RECOVERY_2026_09_07.md)
- [V4 automated review](V4_AUTOMATED_REVIEW_2026_09_07.md)
- [V4 ML release bounded QA](V4_ML_RELEASE_2026_09_07.md)
- [三面向清查建議實作交接（2026-09-07）](THREE_PERSPECTIVE_IMPLEMENTATION_2026_09_07_HISTORY.md)：保存分析／交易與持倉證據、ML 容量／release、UI／UX 的當日工程驗收及未完成 Gate；當時的 0/3 Formal inputs 與 UI 人工驗收限制不代表目前狀態。現況看 [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md)、[Gate 7](../06_qa/GATE_7_ML_SHADOW_ENGINEERING.md) 與 [Application Manual](../07_guides/APPLICATION_MANUAL.md)。舊 QA 路徑保留導引，bytes／SHA 見 [Coverage History Entry 108](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-108)。

- [早期 Full App healthcheck（2026-06-16）](FULL_APP_HEALTHCHECK_2026_06_16.md)：保存當時 8 個 UI 工作區的人工 smoke 結果；目前 UI 架構看 [system_architecture](../01_architecture/system_architecture.md)，操作步驟看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。舊 QA 路徑保留轉址。

- [早期資料收集架構藍圖](DATA_COLLECTION_ARCHITECTURE_HISTORY.md)：保留 2026-06 資料/API 基線、2026-06-11 券商雙指標契約與 2026-10-03 freshness 補記；現行架構看 [system_architecture](../01_architecture/system_architecture.md)，操作看 [DATA_FETCHING_LOGIC](../03_data/DATA_FETCHING_LOGIC.md) 與 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。

- [路徑隔離更新 v1.3.0（2024-10-16）](PATH_ISOLATION_UPDATE_V1_3_HISTORY_20241016.md)：保留舊版路徑覆蓋、dry-run 與測試說明；原 `docs/08_technical/path_isolation_update.md` 路徑提供轉址。目前設定依 `TWStockConfig`、[系統架構](../01_architecture/system_architecture.md) 與 [操作手冊](../07_guides/APPLICATION_MANUAL.md) 判讀。


- [全文件目錄快照（2026-10-06）](DOCUMENTATION_CATALOG_20261006_HISTORY.md)：保留當日 tracked 文件清單；它不是即時清冊，目前導航看 DOCUMENTATION_INDEX 與各專區 README。


- [Workbench 左側主導覽 IA closeout（2026-07-07）](WORKBENCH_LEFT_NAVIGATION_IA_CLOSEOUT_2026_07_07_HISTORY.md) 與 [視覺層級 polish closeout（2026-07-07）](WORKBENCH_VISUAL_HIERARCHY_POLISH_CLOSEOUT_2026_07_07_HISTORY.md)：保留一次性 UI closeout 與當時 QA 證據；目前操作流程見 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)，目前狀態見 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

- [V4 完成計畫（2026-09-07）](V4_COMPLETION_PLAN_2026_09_07_HISTORY.md)：保留截至 2026-09-10 仍標示「進行中」的計畫與執行紀錄；這是當時狀態，不表示目前 V4 完成度。舊核心路徑保留導引頁。
- [V1.1–V2.0 歷史版本路線](VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md)：保留已完成版本的歷史演進；工程優先順序與目前狀態看 Snapshot／6M Roadmap。
- [V1.5–V2.0 里程碑 QA](#v15v20-qa-milestones)：將已結束的早期版本收尾與 V1 release checklist 集中歸檔；舊 `docs/06_qa/` 路徑留有轉址頁，既有目錄／歷史連結仍可開啟。
- [V2.1–V2.5 readiness／closeout 歷史](#v21v25-historical-readiness-and-closeout)：集中已結束的工程準備度與 closeout 報告；來源資格與 policy／approval 原件仍留在 QA。
- [舊 AI Context Pack（截至 2026-08-30）](AI_CONTEXT_PACK_HISTORY_20260830.md)：封存過期狀態包；目前 Agent／開發者入口改看根目錄 `AGENT_CONTEXT.md`。
- [6M Roadmap 歷史狀態與更新流水帳（2026-07 至 2026-09）](ROADMAP_6M_ENGINEERING_STATUS_HISTORY_20260712_TO_20260917.md)：保存首屏補記、單輪 handoff、Gate 7 狀態、Gate 校正與變更記錄；Gate 定義仍在核心 Roadmap。
- [產品 Roadmap 歷史狀態與行動草案（2026-07 至 2026-09）](PRODUCT_ROADMAP_STATUS_HISTORY_20260712_TO_20260917.md)：保存當時的工程／handoff 狀態與原始 30／60／90 日行動草案，不承擔產品方向或目前狀態權威。
- [Product Roadmap 日期化交接紀錄（2026-09-14 至 09-21）](PRODUCT_ROADMAP_HANDOFF_HISTORY_20260914_TO_20260921.md)：保存 V4.1／V4.2 工程觀測與 V5／V6 當時 handoff；產品原則仍看核心 Product Roadmap。
- [6M Roadmap Gate 3／4 歷史狀態（2026-08-26 至 08-28）](ROADMAP_6M_GATE_STATUS_HISTORY_20260826_TO_20260828.md)：保留原先留在 Gate 定義中的日期化 P0、Portfolio 與 Paper 工程觀測；目前狀態仍以 Snapshot 為準。
- [V2.1–V4.0 版本路線更新歷史（2026-07-11 至 09-15）](VERSION_ROADMAP_V2_1_TO_V4_0_UPDATE_HISTORY_20260711_TO_20260915.md)：保存成熟度文件曾附加的狀態快照與 handoff；版本 Gate 標準仍看核心版本 Roadmap。
- [V2.1–V4.0 工程交接紀錄（2026-09-15）](VERSION_ROADMAP_V2_1_TO_V4_0_ENGINEERING_HANDOFF_20260915_HISTORY.md)：保存當時工程分流與下一步；版本成熟度標準仍以核心 Roadmap 為準。
- [V2.1–V4.0 版本狀態快照（2026-07-12 至 2026-08-30）](VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md)：保存各成熟度版本曾附加的階段狀態；目前狀態以 Snapshot 為準。
- [系統架構更新歷史（2026-06 至 2026-10）](SYSTEM_ARCHITECTURE_UPDATE_HISTORY_202606_TO_202610.md)：保留原架構文檔第 16 節逐次狀態記錄、2026-09-27 邊界／資源 lifecycle 收據、2026-09-29 operational custody 與 2026-09-30 排程資料流切片，以及 2026-10-05／06 H20、ML custody、daily research snapshot／chart、private store 與 homepage dated updates；TechnicalIndicatorJob／IndustryMapper、SQLite connection lifecycle、ML initialization、H20 lineage、ML reader／loader、daily research snapshot／cohort／method／saved chart、homepage 與 private store routing 契約已留在 `system_architecture.md` 第 3、4、8、11 節。日期化接線與 guard 結果僅作歷史；當期驗收看 QA，現況看 Snapshot 與最新收據。
- [System Architecture R01 validation excerpt（2026-10-06）](SYSTEM_ARCHITECTURE_R01_VALIDATION_EXCERPT_20261006.md)：保存從架構主文抽出的逐次 QA 記錄全文（僅去掉段落分隔用的尾端空白）；R01 讀取預算契約已集中於 `system_architecture.md` 第 11 節，驗收現況看對應 QA 與 Snapshot。
- [舊端到端流程藍圖](SYSTEM_FLOW_END_TO_END_BLUEPRINT_HISTORY.md)：保存舊 feature store、signals／recommendation 路徑、過時模組位置與建議新增元件；現況請看 `docs/01_architecture/system_architecture.md`，目標請看 `target_system_architecture.md`。
- [文件編碼稽核（2026-06-16）](DOCUMENT_ENCODING_AUDIT_2026_06_16.md)：一次性 UTF-8／mojibake 掃描；保留當時結論，不代表目前 repo 的完整編碼檢查。
- [文件與 Roadmap 重整稽核（2026-07-03）](DOCUMENTATION_ROADMAP_REBASELINE_AUDIT_2026_07_03.md)：一次性文件治理稽核；Phase 歷史判讀已納入現行 `DOCUMENTATION_STRUCTURE.md`。
- [Pre-push 文件治理稽核（2026-07-06）](DOCUMENTATION_PRE_PUSH_AUDIT_2026_07_06_HISTORY.md)：保留該次一次性文件盤點；後續治理狀態看現行 Index／Snapshot 與日期版 rebaseline。
- [Pre-V2 非排程 readiness closeout（2026-07-06）](PRE_V2_NON_SCHEDULE_READINESS_CLOSEOUT_2026_07_06_HISTORY.md)：保留當時非時間型 V2.0 closeout 與仍待時間累積的限制；不得用來判定目前 readiness。
- [ML Shadow 推論操作 closeout（2026-07-15）](ML_SHADOW_INFERENCE_OPERATIONS_CLOSEOUT_2026_07_15_HISTORY.md)：保留受控工程操作層結論及當時真實 frozen artifact smoke blocker；操作步驟仍看現行 runbook，模型資格仍看 Snapshot／現行 QA。
- [SQLite inspector 關閉探測（2026-09-15）](QT_SQLITE_INSPECTOR_SHUTDOWN_PROBE_2026_09_15.md)：保留 bounded probe 收據；當時未重現問題，不代表排除所有競態。
- [Program Readiness 稽核（2026-08-27／28）](PROGRAM_READINESS_AUDIT_2026_08_27.md)：按 8/27 初版與 8/28 更新保留歷史盤點；容量與 readiness 後續已變更，目前狀態看 Snapshot。
- [Prospective Formal Restart 被拒絕的 V2 staging（2026-08-27）](PROSPECTIVE_FORMAL_RESTART_CLOCK_2026_08_27_V2_STAGING_HISTORY.md)：v2 calibration identity 綁定錯誤而遭拒絕；v3 是當時 successor。保留 staging／PIT hash 作歷史證據，不可採用此 clock，現況看 Snapshot。
- [測試資產盤點與結案（2026-09-17）](TEST_ASSET_CONSOLIDATION_CLOSEOUT_2026_09_17.md)：依結案報告、V2 方法補正、V1 撤回紀錄閱讀；139 組候選／1,107 檔是 bounded union，不是完整測試母體。

### V1.5–V2.0 QA milestones

- [V1.5 Data Credibility closeout](V1_5_DATA_CREDIBILITY_CLOSEOUT_2026_07_04.md)
- [V1.6 Cross-sectional Factor Pipeline closeout](V1_6_CROSS_SECTIONAL_FACTOR_PIPELINE_CLOSEOUT_2026_07_05.md)
- [V1.7 Negative Evidence closeout](V1_7_NEGATIVE_EVIDENCE_CLOSEOUT_2026_07_05.md)
- [V1.8 Portfolio Sandbox closeout](V1_8_PORTFOLIO_SANDBOX_CLOSEOUT_2026_07_05.md)
- [V1.9 Read-only Agent MCP closeout](V1_9_READ_ONLY_AGENT_MCP_CLOSEOUT_2026_07_06.md)
- [V1 Release checklist](V1_RELEASE_CHECKLIST_2026_06_30.md)
- [V2.0 Workbench Phase 1 closeout](V2_0_WORKBENCH_PHASE1_CLOSEOUT_2026_07_06.md)
- [V2.0 read-only source adapter closeout](V2_0_WORKBENCH_READ_ONLY_SOURCE_ADAPTER_CLOSEOUT_2026_07_06.md)

### V2.1–V2.5 historical readiness and closeout

- [V2.1 engineering readiness](V2_1_ENGINEERING_READINESS_2026_07_12.md) · [V2.1 formal closeout](V2_1_FORMAL_CLOSEOUT_2026_07_12.md) · [V2.1 Workbench Phase 2](V2_1_WORKBENCH_PHASE2_CLOSEOUT_2026_07_07.md)
- [V2.2 engineering readiness](V2_2_ENGINEERING_READINESS_2026_07_12.md) · [Evidence operating loop check](V2_2_EVIDENCE_OPERATING_LOOP_READONLY_CHECK_2026_07_07.md) · [simulated phase progress QA](V2_2_SIMULATED_PHASE_PROGRESS_QA_2026_07_07.md) · [Week 1 review](V2_2_WEEK1_REVIEW_2026_07_12.md)
- [V2.3 engineering readiness](V2_3_ENGINEERING_READINESS_2026_07_12.md) · [official source evidence pass](V2_3_OFFICIAL_SOURCE_EVIDENCE_PASS_2026_07_12.md)
- [V2.4 engineering readiness](V2_4_ENGINEERING_READINESS_2026_07_12.md)
- [V2.5 engineering readiness](V2_5_ENGINEERING_READINESS_2026_07_12.md)

These are completed, dated engineering/readiness records. Current source acceptance and the V2.2/V2.3 approval packages remain in `docs/06_qa/`; the V2.4 policy/scope approvals are dated history in the Archive section above. Current paper-only execution controls are documented in the Application Manual and system architecture.

## 📄 文檔列表

- [操作手冊更新歷史（2026-09-27）](APPLICATION_MANUAL_CHANGELOG_2026_09_27.md)：原手冊的逐次更新記錄；操作步驟保留於主手冊與附冊。

- [Roadmap Hub 整理前歷史（2026-09-27）](DEVELOPMENT_ROADMAP_HISTORY_2026_09_27.md)：原 Hub 的日期化狀態、Next 與更新紀錄；現行導航已收斂至核心 Hub，不以本頁判斷目前進度。
- [文檔索引整理前歷史（2026-09-27）](DOCUMENTATION_INDEX_HISTORY_2026_09_27.md)：保留舊索引的詳細分類與日期化摘要；目前閱讀入口以核心索引為準。
- [專案快照整理前歷史（2026-09-27）](PROJECT_SNAPSHOT_HISTORY_2026_09_27.md)：保存 9/8–9/26 的逐輪觀測、驗證數字與限制；最新範圍及未解除邊界留在核心 Snapshot。

- [PROJECT_SNAPSHOT歷史封存](PROJECT_SNAPSHOT_HISTORY_2026_09_08.md)：2026-09-08整理前的完整快照與時間順序；僅作追溯。

- **`DOCUMENTATION_UPDATE_SUMMARY.md`**
  - 文檔更新總結（歷史記錄）

- **`DOCUMENTATION_CLEANUP_REPORT.md`**
  - 文檔清理報告（歷史記錄）

- **`DOCUMENTATION_REORGANIZATION_PROPOSAL.md`**
  - 文檔重新整理建議（已執行）

- **`SOLUTION_SUMMARY.md`**
  - 解決方案總結（歷史記錄）

- **`API_INVESTIGATION_REPORT.md`**
  - API 調查報告（歷史記錄）

- **`ROADMAP_6M_ENGINEERING_V1_COMPLETION_RECORD_2026_07.md`**
  - 原 6M Roadmap 中 V1 / Month 1-6 / V1.1-V1.9 的詳細完工紀錄與更新流水帳；只作歷史追溯。

- **`UI_QT_DEVELOPMENT_ROADMAP_AUDIT_2026_05_19.md`**
  - 2026-05-19 `ui_qt` 對照舊 roadmap 的歷史審核報表；部分狀態已被後續 UI / Portfolio / Workbench 進度取代。

- **`PHASE_3_3B_IMPLEMENTATION_PLAN.md`**
  - Phase 3.3b 實施規劃（已執行，歷史歸檔）

- **`NEXT_ACTION_PLAN.md`**
  - 下一輪 Roadmap Rebaseline、技術治理與 Agent 交接行動計畫（已執行，歷史歸檔）

- **`REFACTORING_MIGRATION_PLAN_2025.md`**
  - 2025 年專案結構化與遷移計畫；各遷移步驟已完成，只作架構演進追溯

- **`SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md`**
  - Gate 0 行為不變安全重構的已完成執行紀錄、rollback 與 residual candidate companion

- **`DEVELOPMENT_ROADMAP_LEGACY_2026_06.md`**
  - 2026-06-13 前的完整 Roadmap，包含舊線性 Phase、歷史 Done、舊 Living Section 與歷史風險；只作追溯，不作目前狀態依據。

- **`readme_test.txt`**
  - 歷史測試文檔（已過時，保留作為參考）

- **`root_readme_legacy_2025_12.txt`**
  - 原根目錄 `readme.txt`，內容停留在舊 Phase、舊入口與舊路徑說明；2026-06-18 已移入歸檔，只作歷史追溯，不作目前狀態依據。

- **`dev_progress_note_legacy_2026_01.txt`**
  - 原 `docs/00_core/note.txt` 歷史開發進度筆記；2026-06-30 自核心目錄歸檔，只作追溯，不作目前狀態依據。

- **`ARCH_GOVERNANCE_CHECKLIST.md`**
  - 早期架構治理自檢清單；2026-06-24 自 `docs/00_core/` 歸檔。目前架構權威以 `docs/01_architecture/system_architecture.md` 為準。

- **`ARCH_GOVERNANCE_LIFECYCLE.md`**
  - 早期架構治理生命週期備忘；2026-06-24 自 `docs/00_core/` 歸檔。目前文件治理以 `docs/00_core/DOC_COVERAGE_MAP.md` 與 `docs/00_core/DOCUMENTATION_STRUCTURE.md` 為準。

- **`ARCH_VIOLATION_RESPONSE_POLICY.md`**
  - 早期架構違規處理政策備忘；2026-06-24 自 `docs/00_core/` 歸檔。目前架構邊界與高風險契約以 `docs/01_architecture/system_architecture.md` 為準。

- **`MASTER_GOAL_PLAYBOOK_2026_09_06.md`**
  - 2026-09-06 八卡任務拆解手冊（TASK-01～TASK-08）；01–07 的逐卡 bounded 工程交接見[歷史封存組](#2026-10-08-task-loop-01-07-historical-handoffs)，08-B 中央整合收據仍在 `docs/06_qa/TASK_LOOP_08_HANDOFF.md`。逐卡與中央工程整合不代表正式來源接受、自然前瞻、真實 Paper fills、具名 Formal review 或 V4 closeout 完成。

- **`LUNA_PARALLEL_PLAN_2026_09_07.md`**
  - 2026-09-07 Luna 三線平行規劃伴隨文件；該輪三線已於 2026-09-08 結案（見 `docs/09_archive/LUNA_INTEGRATION_CLOSEOUT_2026_09_08.md`）。

- **`LUNA_PROMPT_A_DATA_ML_2026_09_07.md`**、**`LUNA_PROMPT_B_ARCHITECTURE_2026_09_07.md`**、**`LUNA_PROMPT_C_UX_2026_09_07.md`**
  - 2026-09-07 給 Luna A/B/C 三位子代理的一次性任務 Prompt；任務已結案並整合，歷史提示詞歸檔。

- **`V4_THREE_LUNA_HANDOFF_PROMPTS_2026_09_08.md`**
  - 2026-09-08 給新 Luna A/B/C 三線的接手任務 Prompt；已在 `docs/06_qa/V4_LUNA_REVIEW_AND_WORKSPACE_CLOSEOUT_2026_09_08.md` 複核並提交入庫，歷史提示詞歸檔。

- **`LUNA_B_ENVIRONMENT_2026_09_07.md`**
  - 2026-09-07 Luna B 開發環境與依賴基線記錄快照；現行環境指引以 `docs/07_guides/INSTALL_GUIDE.md` 與 requirements 檔為準。

## 開發計畫與規格追溯

`docs/superpowers/plans/`、`specs/` 與 `prompts/` 中的大多數既有文件是歷史追溯資料；唯一目前明確列為進行中的例外是 [Baldr 產品補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)。[Superpowers README](../superpowers/README.md) 是該目錄的生命週期入口；原路徑、目的地、日期、QA evidence、bytes／SHA 與現行權威替代入口逐檔列於 [Superpowers plan/spec archive manifest](SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md)。已移動原文的 bytes 保存在 Archive，原始目錄保留短導引；未移動項目仍保留原路徑。計畫結果以對應 QA 收據、目前 Snapshot／Roadmap 與 Git 歷史為準。

### 2026-10-08 Post-V1 engineering plans and specs

13 份有完成計畫及具名 QA 收據的 Post-V1 plan/spec 原文已依原子目錄層次移至 `superpowers/plans/` 與 `superpowers/specs/`，舊路徑保留短導引。完整對應及雜湊見 [manifest](SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md)；執行結果見 [Post-V1 Evidence Pipeline QA](#post-v1-evidence-pipeline-qa)。Scheduler Approval plan/spec 配對仍保留原路徑，因既有測試會讀取它們的實際內容。

### 2026-10-08 Month 2 Registry／storage plan

[Month 2 Parameter & Run Storage Governance Plan 原文](superpowers/plans/2026-06-14-month-2-parameter-run-storage-governance.md) 已結案並移至本目錄；[舊路徑](../superpowers/plans/2026-06-14-month-2-parameter-run-storage-governance.md) 保留導引。原文 C4 驗證證據與 Definition of Done 記錄最終完成狀態；前段「等待核准」文字是過程快照，不能作為目前狀態。原始 bytes／SHA 與生命週期見 [plan/spec manifest](SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md)。

### 2026-10-08 Month 3 Factor Layer 歷史設計與實作材料

Factor Layer v1 的 [設計規格](superpowers/specs/2026-06-14-month-3-factor-layer-design.md)、[實作計畫](superpowers/plans/2026-06-14-month-3-factor-layer.md) 與 [Research Run 整合計畫](superpowers/plans/2026-06-14-month-3-factor-run-integration.md) 已依類型歸檔；原路徑保留導引。實作計畫的 Task 1–10 均勾選完成，但「Commit only after user approval」仍未勾選；Git history 有對應實作提交，歸檔保留該差異而不推定核准流程。設計、架構與目前狀態請回到 [系統架構](../01_architecture/system_architecture.md) 與 [專案快照](../00_core/PROJECT_SNAPSHOT.md)。原件路徑與 SHA 見 [plan/spec manifest](SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md)。
另外，[Factor Replay coverage plan](superpowers/plans/2026-06-15-month3-factor-replay-coverage.md) 與 [Recommendation factor feed plan](superpowers/plans/2026-06-15-month-3-recommendation-factor-feed.md) 是後續已執行的 Month 3 factor 擴充計畫；各自的 QA／lint 證據留在原文，現況仍以 Snapshot 與 Architecture 為準。

### 2026-10-08 Month 4 Daily Decision Desk closure plan

[Month 4 closure plan 原文](superpowers/plans/2026-06-16-month4-daily-decision-desk-closure.md) 已移至 Archive；[舊路徑](../superpowers/plans/2026-06-16-month4-daily-decision-desk-closure.md) 保留導引。原文前段載有結案摘要和驗證數字，後段 Task 1–7 的核取方塊仍未勾選；兩者差異原樣保留，現況以 Snapshot、Architecture 與 Manual 為準。完整 bytes／SHA 與 closeout commit 見 [manifest](SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md)。
### 2026-10-08 Safe Refactor continuation plan

[Safe Refactor continuation plan 原文](superpowers/plans/2026-07-11-safe-refactor-continuation.md) 已結案並移至 Archive；[舊路徑](../superpowers/plans/2026-07-11-safe-refactor-continuation.md) 保留導引。核准、shim／legacy removal audit、release healthcheck 與測試收據見 [原始 QA audit](../06_qa/SHIM_LEGACY_REMOVAL_AUDIT_2026-07-12.md) 和 [plan/spec manifest](SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md)；目前架構以 system architecture 為準。
### 2026-10-08 Month 3 Portfolio Replay history

Month 3 closure audit 與 8 份實作步驟全完成、各有 implementation commit 的 Portfolio Replay 計畫原文已歸檔：

- [Month 3 closure audit](superpowers/plans/2026-06-15-month3-closure-audit.md)
- [Cash-constrained orders](superpowers/plans/2026-06-15-portfolio-replay-cash-constrained-orders.md)、[cash ledger](superpowers/plans/2026-06-15-portfolio-replay-cash-ledger.md)、[credibility manifest](superpowers/plans/2026-06-15-portfolio-replay-credibility-manifest.md)
- [Execution costs](superpowers/plans/2026-06-15-portfolio-replay-execution-costs.md)、[gap-risk labels](superpowers/plans/2026-06-15-portfolio-replay-gap-risk-labels.md)、[liquidity gate](superpowers/plans/2026-06-15-portfolio-replay-liquidity-gate.md)
- [Lot sizing](superpowers/plans/2026-06-15-portfolio-replay-lot-sizing.md)、[unfilled orders](superpowers/plans/2026-06-15-portfolio-replay-unfilled-orders.md)

以上 8 份計畫的實作步驟均已勾選，且各有 implementation commit。Archive manifest 記錄原路徑、commit、bytes 與 SHA。現況仍看 Snapshot、Architecture、Manual 與具名 QA。

### 2026-10-09 Portfolio Replay weight/exposure plan 增補

[weight/exposure plan 原文](superpowers/plans/2026-06-15-portfolio-replay-weight-exposure.md) 已於 10/09 封存，來源路徑留下短導引。實作 commit `d8276f5b` 包含計畫、程式、測試、Snapshot、Roadmap 與 Manual；原計畫最後一個 diff／stage 檢查核取項目仍未勾選。保留此狀態差異，不推論為獨立 QA 結案或目前行為證明；bytes／SHA 見 [manifest](SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md)。
### 2026-10-08 V3 score effectiveness／ML readiness history

[V3 Score Effectiveness／ML Readiness design spec](superpowers/specs/2026-07-08-v3-score-effectiveness-ml-readiness-design.md) 與 [implementation plan](superpowers/plans/2026-07-08-v3-score-effectiveness-ml-readiness.md) 已依原類型歸檔，舊路徑保留導引。當時 V3 engineering candidate inputs 標示完成；計畫明確停在 read-only audit、shadow research 與 closeout readiness，不訓練或部署 production ML。此為 2026-07 判斷，目前 ML 狀態以 Snapshot、Architecture 與現行 QA 為準。

### 2026-10-08 UI readability polish plans

- [UI UX Readability Polish plan](superpowers/plans/2026-07-07-ui-ux-readability-polish.md) 與 [design spec](superpowers/specs/2026-07-07-ui-ux-readability-polish-design.md)
- [Workbench Visual Hierarchy Polish plan](superpowers/plans/2026-07-07-workbench-visual-hierarchy-polish.md) 與 [design spec](superpowers/specs/2026-07-07-workbench-visual-hierarchy-polish-design.md)

兩組計畫均有 closeout commit，原件及各自範圍外的未完成門檻均保留。現況 UI 行為以 Application Manual 為準。

### 2026-10-08 TPEX daily-price backfill plan

[2026-06 TPEX daily-price backfill plan](superpowers/plans/2026-06-16-tpex-daily-price-backfill.md) 已結案並移至 Archive，舊路徑保留導引。原計畫與 `8d02af91e` 文件 closeout 相符；它描述的 OpenAPI 流程早於後來新增的 official raw custody、capture metadata、CSV／DB preflight 與 PIT 限制。現行操作看 [Application Manual](../07_guides/APPLICATION_MANUAL.md)，後續正式驗收看 [2026-09-18 TPEX backfill QA](../06_qa/TPEX_SINGLE_DAY_PRECAPTURED_BACKFILL_2026_09_18.md)。

### 2026-10-08 Financial float boundary governance history

[金融 float 邊界治理 plan](superpowers/plans/2026-06-11-financial-float-boundary-governance.md) 與[配套設計 spec](superpowers/specs/2026-06-11-financial-float-boundary-governance-design.md) 已依類型歸檔，原路徑保留導引。計畫驗收項目全數勾選，Git closeout 為 `2d27d02bd`；此處只結束 2026-06 的實作計畫，不表示金融數值邊界政策失效。現行狀態看 [專案快照](../00_core/PROJECT_SNAPSHOT.md) 與 [系統架構](../01_architecture/system_architecture.md)。

### 2026-10-08 Documentation roadmap rebaseline plan

[Scoped SSOT／Roadmap rebaseline plan](superpowers/plans/2026-06-13-doc-governance-roadmap-rebaseline.md) 已完成並封存，舊路徑保留導引；結案檢查見 `76a30273f`、`d6533557f`，當期稽核見[文件與 Roadmap 重整稽核](DOCUMENTATION_ROADMAP_REBASELINE_AUDIT_2026_07_03.md)。現行職責看 [DOCUMENTATION_STRUCTURE](../00_core/DOCUMENTATION_STRUCTURE.md)、[DOC_COVERAGE_MAP](../00_core/DOC_COVERAGE_MAP.md) 與 [Roadmap Hub](../00_core/DEVELOPMENT_ROADMAP.md)。

### 2026-10-08 Legacy Test Governance history

[Legacy Test Governance 計畫](superpowers/plans/2026-06-14-legacy-test-governance.md) 與[設計規格](superpowers/specs/2026-06-14-legacy-test-governance-design.md) 已結案並封存，舊路徑保留導引。計畫 23 個工作項目全數勾選，並由 `c617a6104` 記錄 closeout；此資料只記錄 2026-06 的 API 遷移與 pytest collection 整理。現行測試清冊、分類與手動測試界線請看[最新測試清冊](../06_qa/TEST_INVENTORY_HEALTHCHECK_CLASSIFICATION_2026_06_23.md)、[QA 主題地圖](../06_qa/README.md) 與 [manual tests README](../../tests/manual/README.md)。

## 2026-10-06 治理入口整理原文快照

下列全文快照保存此次入口與狀態文案整理前的原始 tracked bytes；改寫後的目前入口仍以各自現行文件為準：

- [整理前 PROJECT_SNAPSHOT](PROJECT_SNAPSHOT_HISTORY_20261006.md)
- [整理前 DOCUMENTATION_INDEX](DOCUMENTATION_INDEX_HISTORY_20261006.md)
- [整理前 docs README 與索引前言](DOCUMENTATION_ENTRY_HISTORY_20261006.md)
- [文件重新整理 mapping 與處置清冊](DOCUMENTATION_REORGANIZATION_MANIFEST_20261006.md)

## 2026-10-08 Task Loop 01-07 historical handoffs

七份逐卡 handoff 記錄各自的 bounded 工程範圍、驗收與限制。08-B 後續完成中央整合並逐卡覆核；因此 01–07 移至 Archive，中央整合與外部 Gate 殘餘邊界仍由 QA 的 [TASK_LOOP_08_HANDOFF](../06_qa/TASK_LOOP_08_HANDOFF.md) 說明。這批歸檔只整理歷史證據，不把正式來源接受、PIT／自然前瞻、真實 Paper fills、具名 review 或 V4 maturity 標示為完成。舊 QA 路徑保留短轉址；原文 bytes 與 SHA-256 見 [Coverage History Entry 082](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-082)。

- [TASK_LOOP_01_HANDOFF.md](TASK_LOOP_01_HANDOFF.md)
- [TASK_LOOP_02_HANDOFF.md](TASK_LOOP_02_HANDOFF.md)
- [TASK_LOOP_03_HANDOFF.md](TASK_LOOP_03_HANDOFF.md)
- [TASK_LOOP_04_HANDOFF.md](TASK_LOOP_04_HANDOFF.md)
- [TASK_LOOP_05_HANDOFF.md](TASK_LOOP_05_HANDOFF.md)
- [TASK_LOOP_06_HANDOFF.md](TASK_LOOP_06_HANDOFF.md)
- [TASK_LOOP_07_HANDOFF.md](TASK_LOOP_07_HANDOFF.md)

## ⚠️ 注意

這些文檔主要用於記錄歷史，日常使用時請參考：
- `../00_core/DOCUMENTATION_INDEX.md` - 文檔索引
- `../00_core/PROJECT_SNAPSHOT.md` - 專案快照
- `../00_core/ROADMAP_6M_ENGINEERING.md` - 未來 6 個月工程路線
