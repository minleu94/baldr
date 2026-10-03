# QA 相關文檔目錄

- [V3.3 Engineering Closeout](V3_3_ENGINEERING_CLOSEOUT_2026_07_12.md)：15 capability、lineage verifier、operations handoff 與 external-only 清單。
- [V4 每日自然證據運行閉環 QA Handoff](V4_DAILY_EVIDENCE_LOOP_HANDOFF_2026_09_12.md)：scheduler、progress receipt、cohort identity、Paper ledger、自然成熟與外部阻塞的交接證據。

> **QA 驗證和問題文檔**

本目錄包含所有 QA 相關的文檔。

日期化的 QA 報告保存當次輸入、命令、結果與接受邊界；不同日期或不同範圍的報告即使主題相同，也不能當作重複檔案刪除。查目前狀態請讀 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，不要把歷史報告的「下一步」當成目前待辦。

## 近期證據入口（依主題）

| 要查的內容 | 證據入口 |
| --- | --- |
| 本次Windows／Codex排程修復、Gemini ML真實建置／訓練／推論及原Legacy／Bank受控讀回；產品收尾進度與保留限制 | [10/2–10/3整合修復紀錄](INTEGRATION_REPAIR_ACCEPTANCE_20261002.md) |
| 2026-09-30 排程修復、自然 Quick warning／Freshness degraded／Official events publication_scope=formal_historical／nested `corporate_action_adjustment_custody` `prospective_only=true`、`formal_source_contract_eligible=false`、`historical_pit_eligible=false`、Paper no-work、Evidence #3 engineering pass／business degraded、Bank#2 barrier pass／source failed、PIT／ML／fundamental blocker | [9/30 排程修復與執行驗收](SCHEDULED_OPERATIONS_REPAIR_20260930.md) |
| Windows 排程、來源契約與資料接線 | [9/29 全項審視及修復](SCHEDULED_OPERATIONS_REPAIR_20260929.md) |
| 重構驗收範圍與保留限制 | [R031 closeout](R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)、[C4 mandatory gates](C4_FINAL_MANDATORY_STATIC_GATES_20260925.md) |
| ML 邊界與 R026 後續驗證 | [R026 exact allowlist](ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md)、[source revision aggregate](R026_SOURCE_REVISION_EVIDENCE_AGGREGATE_20260925.md) |
| 正式行情修復及候選模型品質 | [正式資料修復](FORMAL_DATA_REPAIR_2026_09_23.md)、[修復來源候選驗收](REPAIRED_SOURCE_MODEL_CANDIDATE_QA_2026_09_23.md) |
| 個股研究與日常操作可讀性 | [V5 readability acceptance](V5_READABILITY_ACCEPTANCE_2026_09_21.md) |
| 跨工作區捲動、表格與視窗幾何 | [UI Layout Audit 2026-09-29](UI_LAYOUT_AUDIT_20260929.md) |
| 唯讀服務刷新取消與回歸 | [唯讀服務刷新取消驗證](READ_ONLY_SERVICE_CANCELLATION_QA_20260930.md) |
| 分支、工作副本與復原備份 | [本機分支整理](BRANCH_WORKTREE_CONSOLIDATION_20260927.md) |
| WP5 目前 HEAD 缺口與 19 筆 pending | [9/29 逐筆診斷與接續路由](WP5_HEAD_GAP_AND_PENDING_DIAGNOSIS_20260929.md) |
| 文檔重複的取捨與保留理由 | [文檔整理審查](DOCUMENTATION_CONSOLIDATION_20260927.md) |

完整文件分類見 [文檔索引](../00_core/DOCUMENTATION_INDEX.md)；本頁只提供閱讀路徑，不重新維護各報告的驗收數字。

## 📄 文檔列表

### 推薦分析 Tab QA
- `QA_RECOMMENDATION_TAB_ISSUES.md` - QA 問題
- `QA_RECOMMENDATION_TAB_SUMMARY.md` - QA 總結

### 數據更新 Tab QA
- `QA_UPDATE_TAB_ISSUES.md` - QA 問題
- `QA_UPDATE_TAB_SUMMARY.md` - QA 總結

### 全程式人工 Health Check 與測試路由
- `V1_RELEASE_CHECKLIST_2026_06_30.md` - v1.0.0-rc.1 / v1.0.0 發布前 release readiness gate，涵蓋乾淨 main、全新 clone、非破壞 healthcheck、MainWindow UI smoke 與人工 UI 驗證。
- `FULL_APP_HEALTHCHECK_2026_06_16.md` - 主 UI 人工 smoke test 母檔，包含數據更新、SQLite 檢視、TPEX 日價、券商分點、每日決策與跨工作區流程
- `FULL_APP_HEALTHCHECK_AGENT_CLOSEOUT_2026_06_23.md` - Testing / QA Agent + Full App Healthcheck Runner A-E 完成後的收束報告、可用邊界與下一階段選項。
- `TEST_INVENTORY_HEALTHCHECK_CLASSIFICATION_2026_06_23.md` - `tests/` 全量測試分類，定義哪些測試可直接橋接到非破壞式 release healthcheck runner、哪些只能作 oracle、哪些需保留 manual / dry-run。
- `FEATURE_TEST_ROUTING_MATRIX_2026_06_23.md` - Testing QA Agent 使用的 feature-to-test 測試路由與決策矩陣（測試知識庫），不包含 Agent 角色定義。

### Post-V1 Evidence QA
- `POST_V1_FORWARD_PERFORMANCE_READ_MODEL_QA_2026_07_03.md` - Forward Performance Read Model 與 importer-to-outcome smoke QA 紀錄

### 文件與工具稽核
- `DOCUMENT_ENCODING_AUDIT_2026_06_16.md` - repo 文件 UTF-8 / mojibake 掃描報告
- `DOCUMENTATION_PRE_PUSH_AUDIT_2026_07_06.md` - push 前 docs 全目錄位置、索引、archive 候選、版本治理與相對連結稽核
- `SUPERPOWERS_PLAN_SPEC_DATE_AUDIT_2026_07_06.md` - Superpowers plan / spec 日期與完成狀態稽核
- `SHIM_LEGACY_REMOVAL_AUDIT_2026-07-12.md` - Wave 6 shim／legacy removal 的 consumer、dynamic import、persisted class-path 與 release closeout 證據

### 已歸檔 QA
- `../09_archive/UI_QT_DEVELOPMENT_ROADMAP_AUDIT_2026_05_19.md` - 2026-05-19 UI Qt 對照舊 roadmap 的歷史審核報表；不作目前完成狀態依據

## 🔗 相關目錄

- `../02_features/` - 功能文檔
- `../03_data/` - 數據相關文檔
- `../09_archive/` - 已過時但仍有追溯價值的歷史文檔


2026-10-03後續驗證：見 `docs/06_qa/FINAL_DATA_CLOSEOUT_AND_COMMIT_20261003.md`。current fundamentals 為weekly成功後的獨立writer；current revision與正式PIT分離，decision date使用Asia/Taipei、market cutoff保留獨立日期；Evidence依child stdout/summary/report與來源品質驗收。個股研究提供明確保存來源／指定股票分析及獨立技術觀察，仍守正式ML來源修訂隔離。
