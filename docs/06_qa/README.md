# QA 相關文檔目錄

- [UX16／UX18 固定方法與 UX13 共用母體盤勢收據](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)：兩條既有觀察、方法／參數／日期／hash 拒絕、舊 schema 明確更新、具名母體盤勢／值排序與真實兩股閉環；整體 UX13／18／19 仍 partial。

- [V3.3 Engineering Closeout](V3_3_ENGINEERING_CLOSEOUT_2026_07_12.md)：15 capability、lineage verifier、operations handoff 與 external-only 清單。
- [V4 每日自然證據運行閉環 QA Handoff](V4_DAILY_EVIDENCE_LOOP_HANDOFF_2026_09_12.md)：scheduler、progress receipt、cohort identity、Paper ledger、自然成熟與外部阻塞的交接證據。

> **QA 驗證和問題文檔**

本目錄包含所有 QA 相關的文檔。

日期化的 QA 報告保存當次輸入、命令、結果與接受邊界；不同日期或不同範圍的報告即使主題相同，也不能當作重複檔案刪除。查目前狀態請讀 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，不要把歷史報告的「下一步」當成目前待辦。

## 近期證據入口（依主題）

- [UX16來源契約／UX18日特徵consumer／UX19隔離閉環／UX04與UX05日常同源flow與UX02 Native中文](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)：唯讀API／CLI、既有close／MA共用三態與實際個股接線、scoped hash／時鐘／資格未知、四用途代表畫面及工程／證據依賴。

| 要查的內容 | 證據入口 |
| --- | --- |
| 最新有限驗收、native 未通過情境、容量／正式資格阻礙與 checkpoint 提交邊界 | [最小續接清單（2026-10-05，Batch9）](MINIMAL_CONTINUATION_HANDOFF_20261005.md) |
| 四用途來源接線、現況基本面／估值、研究 ML 自動路徑與同版原生 UI 的本輪實作及驗收 | [Astra 工程收尾（2026-10-03 至 05）](ASTRA_ENGINEERING_CLOSEOUT_20261003.md) |
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


## 2026-10-05 收藏原研究

[UX03／06／13收藏原來源收據](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)：限定保存／精確返回／同查詢切股／錯來源拒絕與Library Native證據，與完整stage／自然資格分開。


## 2026-10-05 原排名發布驗證

[UX18原引擎排名不可變發布與同源讀回](UX18_ORIGINAL_STOCK_RANKING_PUBLISHER_20261005.md) 記錄四模式 bounded publisher、拒絕／中斷、同源consumer、背景實D讀回及剩餘工程／來源／Native決策。

- 2026-10-05 更新：新增原排名有限工程入口及接受邊界。

## 2026-10-05 原排名收藏與個股來源版本化（最新限定收尾）

[原排名收藏與個股來源版本化](UX18_RANK_BOOKMARK_SOURCE_VERSIONING_20261005.md)：已完成原排名選股→個股原排名／原 feature→版本化收藏→新程序 pinned 讀回→精確返回原收藏。v2 保存四模式、實際比較窗、原母體／方法／hash／排序／所選股；舊非 rank v1 內容與 bookmark/query/payload 雜湊不變，沒有真實清單遷移。缺件／錯版本／日期／股號／hash／來源修訂顯示原因，可明確另開最新個股研究，保留原證據。完整 Top/Bottom 字串照原 publisher 顯示，3–5 筆週 fallback 明示實際日期與非完整週，不反推 score／勝率。 受影響測試 136 首輪通過＋1 項定向修正後通過（合計 137 個案例）；Workbench 85；更新頁 validator 25 通過／4 略過；mypy 783 檔；18 個 Python 檔語法與 quant guard 通過。 既有 publisher QA 的「原排名收藏尚待」僅是上一版本狀態；本批僅補 consumer／收藏，未重跑 publisher。


## 2026-10-05 UX19 有界儲存與發布復原延伸

本批唯讀參照盤點與 dry-run 不提供永久刪除授權；歷史 manifest／artifact／v1-v2 收藏參照保留，未知 schema、缺件、來源不完整及超預算採保守保留。排名首次發布的缺件指標 CAS 與隔離跨程序復原收據、容量時點政策及驗證結果見 [限定收尾收據](UX19_STORAGE_AND_PUBLICATION_RECOVERY_20261005.md)。未改原引擎／排名／方法／日期，未重跑既有真實 publisher 或 ML。

真實 MainWindow 九工作區在空資料、隔離配置、offscreen 子程序最小啟動／正常關閉通過（PID 23772，worker 0，guard 無違規）；這不替代帶正式資料的 App 功能、Native 或真人驗收。其他 consumer／完整方法字典／正式母體與排程／其他 writer 生命周期／長期自然成長仍是工程待辦；Backtest18.62%／20%保持未達，來源 availability／PIT／自然資格另列。使用者其他對話的容量／Evidence 變更保留且不納入本批提交，中央政策以時點 pin 為準。


## 2026-10-05 UX09 有界 MA 名單入選歷程

既有兩條 MA 三態快照經純比較模型、有限歷史 reader 與背景 UI 呈現本次新入選／持續符合／重新入選／未再符合，並保存前次日期、理由與可回放來源身份；不是策略升降級服務。無效／缺件／漏日／同日修訂／版本或母體變更及回填保持未知，不在刷新時寫事件。日曆只讀現有快取，publication 前可得性核驗；現有真實來源只有同日，不能作跨日自然歷程證明。

此為原計畫 §8.1／UX09 的研究讀取切片；不更換母體權威或舊標籤、不啟動自然 capture／outcome 階段5，不宣告首版完成。完整方法字典、其他 consumer 融合、正式母體／排程與其他 writer 生命周期仍是工程待辦，Backtest18.62%／20%不變；Native與真人驗收另待桌面時段。詳見 [UX09 限定收據](UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md)。


## 2026-10-05 UX09 歷史索引／分頁與有限版本復原（最新）

長期保存的研究manifest以可重建SQLite派生索引查詢，32 refs／頁、固定來源／query／generation游標、64頁滑動導航窗口且可持續向更早頁讀取。背景history／explicit rebuild保持當期個股與篩選主線可用；schema／來源／hash／cancel／故障不偽造完整，原immutable來源／舊收藏不遷移。索引最多64MiB，每頁串流重核全index SHA及頁內原manifest/artifact，年度calendar以4096entries／32MiB逐份驗證，不再32份正常累積即整批未知。

限定受影響79個不重複案例、Workbench85、validator25／4skip、mypy788、11變更Python編譯與精度／未來函數guard通過。真實已保存三股來源隔離offscreen回放：晚發布仍unknown、17來源hash與正式DBsize/mtime不變、worker0；沒有讀正式DB去重核current identity。130日×2修訂合成metadata全260refs走9頁，index159744 bytes、最大page JSON13814 bytes／tracemalloc1226583 bytes；不當自然樣本或正式長期總容量證明。

本包關閉UX09索引／分頁／索引程式內版本復原；第一版工程剩餘固定F1–F4，詳細終點與owner見收據。Backtest18.62%／20%仍差1.38百分點，不重測湊數或放寬。舊1477 Native已在6691ec78通過，較早「仍待1477」文字由此更正；新分頁／跨頁Native及3–5位真人另驗。1000×835 outer／125%已接受，不新增1000×800硬門檻。具名full-cohort與原完整Top/Bottom標籤沿現況，官方全市場／新百分位方法只有擴充時才要明確決定，不阻塞目前研究限定工程。

完整操作與排錯見 APPLICATION_MANUAL 的歷史索引小節；[詳細驗證、來源選項與F1–F4凍結清單](UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md)。


- 2026-10-05：[F2／F3 原市場共享來源及已開能力矩陣](F2_F3_SHARED_CONSUMERS_AND_CAPABILITIES_20261005.md)，A／A 限定完成；F1／F4 與新 Native／真人另列。


- 2026-10-05：[F4跨頁整合與資源終驗](F4_RELEASE_INTEGRATION_AND_RESOURCE_ACCEPTANCE_20261005.md)：actual三程序雙收藏讀回通過；20-session實測有效，120/250長保留因二次payload超現有預算blocked，F4未全關閉；F1／新Native／真人另列。

- 2026-10-05：[F4項目revision儲存與20／120／250實測](F4_ITEM_REVISION_STORAGE_AND_RETENTION_20261005.md)：新v3長留存與actual App通過，原預算不變；正式舊SQLite COW converter與切換仍待工程／核准。

- 2026-10-05：[F4 SQLite COW converter／明示activation終驗](F4_SQLITE_COW_CONVERTER_AND_ACTIVATION_20261005.md)：隔離工程完成；20→21→rollback20保留雙庫與target新歷史。正式store/mode與使用者apply批准另列，不讀真實JSON、不初始化缺失DB。


- 2026-10-05：[F4 Legacy JSON COW／原升級入口終驗](./F4_LEGACY_JSON_COW_AND_ACTIVATION_20261005.md)：單JSON至獨立v3、新程序讀回及rollback保留新內容；正式apply另行批准，F1例外尚未批准，UX07未啟動。


- [UX21 Forward Outcome](UX21_FORWARD_OUTCOME_20261006.md)：lane採納、exact保存母體consumer／H5/10/20畫面、完整分母、成本／缺件／pending與cancel/stale/new-process限定驗收；整項partial，非自然或正式交易資格。
