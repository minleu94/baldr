# 文檔索引

本索引只指向主題權威與目錄入口，不複製 QA 收據、測試數字或目前狀態。判讀衝突時使用下列 Scoped SSOT；日期化驗收內容保留於各自 receipt。

- UX16研究來源preflight／UX18既有日特徵與固定方法綁定／UX13共用母體盤勢與指標排序／UX19隔離發布閉環／UX04與UX05日常同源flow／UX02中文Native代表畫面：[來源契約與限定驗證](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。

- 原產品計畫階段 0 首包：[來源能力矩陣](../06_qa/PRODUCT_STAGE01_SOURCE_MATRIX_20261005.md)、[效能基線與下一包依賴](../06_qa/PRODUCT_STAGE01_PERFORMANCE_BASELINE_20261005.md)。
- 原產品計畫階段 1 限定修正：[啟動、盤勢價格批次與首次圖表驗證](../06_qa/PRODUCT_STAGE1_PERFORMANCE_IMPROVEMENT_20261005.md)。
- 階段1接續：[早期SQL取消、凍結門檻與下一共用語言包](../06_qa/PRODUCT_STAGE1_SQL_CANCELLATION_20261005.md)。

## 權威入口

| 主題                     | 權威                                                                                                          |
| ---------------------- | ----------------------------------------------------------------------------------------------------------- |
| 目前狀態、本週優先事項與高風險區       | [PROJECT_SNAPSHOT](PROJECT_SNAPSHOT.md)                                                                     |
| 產品方向、產品 Gate、Non-goals | [PRODUCT_ROADMAP_POST_REFACTOR](PRODUCT_ROADMAP_POST_REFACTOR.md)                                           |
| 六個月工程里程碑與驗收            | [ROADMAP_6M_ENGINEERING](ROADMAP_6M_ENGINEERING.md)                                                         |
| Roadmap 導覽             | [DEVELOPMENT_ROADMAP](DEVELOPMENT_ROADMAP.md)                                                               |
| V2.1–V4.0 長期成熟度        | [VERSION_ROADMAP_V2_1_TO_V4_0](VERSION_ROADMAP_V2_1_TO_V4_0.md)                                             |
| 舊工作移交                  | [LEGACY_ROADMAP_CARRYOVER](LEGACY_ROADMAP_CARRYOVER.md)                                                     |
| 外部參考與 V1.5–V2.0 版本形狀   | [EXTERNAL_REFERENCE_VERSION_BLUEPRINT](EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md)                             |
| 目前架構、模組邊界與資料流          | [system_architecture](../01_architecture/system_architecture.md)                                            |
| 目標架構                   | [FINAL_TARGET_ARCHITECTURE](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) |
| 使用者操作、安全與排錯            | [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)                                                    |
| 文件覆蓋與生命週期              | [DOC_COVERAGE_MAP](DOC_COVERAGE_MAP.md)、[DOCUMENTATION_STRUCTURE](DOCUMENTATION_STRUCTURE.md)               |

## 其他正式入口

- UX08原生圖同源投影、截止日／精確表格／fallback及個人資料分離設計：[限定工程驗證](../06_qa/UX08_NATIVE_CHART_CONTRACT_20261005.md)。

- 四用途既有功能的有限工程缺口、Luna Max 分工與當次驗收：[Astra 工程收尾](../06_qa/ASTRA_ENGINEERING_CLOSEOUT_20261003.md)。是否完成以該文件最後接受與 Snapshot 為準。

- 理想目標架構與 Current → Target 演進：[target_system_architecture.md](../01_architecture/target_system_architecture.md)
- Formal input readiness 最新查核：[FORMAL_INPUT_READINESS_REFRESH_2026_08_30.md](../06_qa/FORMAL_INPUT_READINESS_REFRESH_2026_08_30.md)
- 2026-09-29 跨工作區 UI 版面、捲動與幾何驗收（六格 MainWindow offscreen 矩陣通過）：[UI_LAYOUT_AUDIT_20260929.md](../06_qa/UI_LAYOUT_AUDIT_20260929.md)
- 2026-09-30 七項排程問題修復、Task identity、真實 Quick／freshness receipts 與尚存資料缺口：[SCHEDULED_OPERATIONS_REPAIR_20260930.md](../06_qa/SCHEDULED_OPERATIONS_REPAIR_20260930.md)
- 2026-09-30 唯讀服務合作式取消與 repository contract 驗證：[READ_ONLY_SERVICE_CANCELLATION_QA_20260930.md](../06_qa/READ_ONLY_SERVICE_CANCELLATION_QA_20260930.md)
- 2026-10-01 Gemini ML revision-aware rebuild 交接與建置證據（獨立整合驗收另列）：[ML_REVISION_AWARE_REBUILD_EXECUTION_PLAN_20261001.md](../06_qa/ML_REVISION_AWARE_REBUILD_EXECUTION_PLAN_20261001.md)

- 2026-10-02 三階段整合修復、排程／automation 實際設定與受控執行驗收：[INTEGRATION_REPAIR_ACCEPTANCE_20261002.md](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)
- 2026-10-03 weekly controller、canonical locator、child readback 與 partial／review 判讀：[APPLICATION_MANUAL §2026-10-03 週度研究採集與讀回](../07_guides/APPLICATION_MANUAL.md#2026-10-03-週度研究採集與讀回)

## 領域目錄

- [架構文件](../01_architecture/README.md)：現況架構、target 導覽與系統設計。31 個 refactor task specs 是執行契約，不表示完成；實際狀態以 Snapshot 與 QA receipts 為準。
- FINAL 目標架構規範：[資料流](../01_architecture/target_architecture_2026_09_22/FINAL_DATA_FLOW.md)、[擴充模型](../01_architecture/target_architecture_2026_09_22/FINAL_EXTENSIBILITY_MODEL.md)、[ML 相容契約](../01_architecture/target_architecture_2026_09_22/FINAL_ML_COMPATIBILITY_CONTRACT.md)、[架構不變條件](../01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md)、[遷移順序](../01_architecture/target_architecture_2026_09_22/FINAL_MIGRATION_SEQUENCE.md)。
- [功能文件](../02_features/README.md)、[資料文件](../03_data/README.md)、[券商分點文件](../04_broker_branch/README.md)、[歷史 Phase](../05_phases/README.md)、[QA receipts 與主題入口](../06_qa/README.md)、[操作指南](../07_guides/README.md)、[技術備忘](../08_technical/README.md)。
- [Agent 規範](../agents/README.md)、[策略文件](../strategies/README.md)、[Superpowers 設計與執行追溯](../superpowers/README.md)、[歷史封存](../09_archive/README.md)。
- 根目錄導覽：[README](../../README.md)、[PROJECT_NAVIGATION](../../PROJECT_NAVIGATION.md)、[PROJECT_INVENTORY](../../PROJECT_INVENTORY.md)、Codex 指令入口 [AGENTS.md](../../AGENTS.md)。

Archive、QA receipt、FINAL 設計分冊及 31 份 task specs 仍保留原文件；本索引不重述其結果或狀態。

整理前的日期化摘要與詳細分類保存在 [歷史索引](../09_archive/DOCUMENTATION_INDEX_HISTORY_2026_09_27.md)，只作文件演進追溯。

- 2026-10-05 UX02：[共用狀態詞彙有限切片與驗證](../06_qa/UX02_SHARED_STATUS_VOCABULARY_20261005.md)。


## 2026-10-05 收藏原研究入口

- [完整Manual](../07_guides/APPLICATION_MANUAL.md)：每日研究收藏、觀察清單exact回看、精確移除／還原、latest另開與排錯。
- [限定QA](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)：114項相關／WB85／validator／mypy778、Native閉環、Library IDs與未解除限制。


## 2026-10-05 原排名工程收據

- [UX18原引擎排名發布與同源讀回](../06_qa/UX18_ORIGINAL_STOCK_RANKING_PUBLISHER_20261005.md)：有限研究四mode、來源拒絕、原標籤語意、offscreen與剩餘工程；操作入口仍以Application Manual為準。

- 2026-10-05 更新：新增原排名有限工程入口及接受邊界。

## 2026-10-05 原排名收藏與個股來源版本化（最新限定收尾）

[原排名收藏與個股來源版本化](../06_qa/UX18_RANK_BOOKMARK_SOURCE_VERSIONING_20261005.md)：已完成原排名選股→個股原排名／原 feature→版本化收藏→新程序 pinned 讀回→精確返回原收藏。v2 保存四模式、實際比較窗、原母體／方法／hash／排序／所選股；舊非 rank v1 內容與 bookmark/query/payload 雜湊不變，沒有真實清單遷移。缺件／錯版本／日期／股號／hash／來源修訂顯示原因，可明確另開最新個股研究，保留原證據。完整 Top/Bottom 字串照原 publisher 顯示，3–5 筆週 fallback 明示實際日期與非完整週，不反推 score／勝率。 受影響測試 136 首輪通過＋1 項定向修正後通過（合計 137 個案例）；Workbench 85；更新頁 validator 25 通過／4 略過；mypy 783 檔；18 個 Python 檔語法與 quant guard 通過。 既有 publisher QA 的「原排名收藏尚待」僅是上一版本狀態；本批僅補 consumer／收藏，未重跑 publisher。


## 2026-10-05 UX19 有界儲存與發布復原延伸

本批唯讀參照盤點與 dry-run 不提供永久刪除授權；歷史 manifest／artifact／v1-v2 收藏參照保留，未知 schema、缺件、來源不完整及超預算採保守保留。排名首次發布的缺件指標 CAS 與隔離跨程序復原收據、容量時點政策及驗證結果見 [限定收尾收據](../06_qa/UX19_STORAGE_AND_PUBLICATION_RECOVERY_20261005.md)。未改原引擎／排名／方法／日期，未重跑既有真實 publisher 或 ML。

真實 MainWindow 九工作區在空資料、隔離配置、offscreen 子程序最小啟動／正常關閉通過（PID 23772，worker 0，guard 無違規）；這不替代帶正式資料的 App 功能、Native 或真人驗收。其他 consumer／完整方法字典／正式母體與排程／其他 writer 生命周期／長期自然成長仍是工程待辦；Backtest18.62%／20%保持未達，來源 availability／PIT／自然資格另列。使用者其他對話的容量／Evidence 變更保留且不納入本批提交，中央政策以時點 pin 為準。


## 2026-10-05 UX09 歷史索引／分頁與有限版本復原（最新）

長期保存的研究manifest以可重建SQLite派生索引查詢，32 refs／頁、固定來源／query／generation游標、64頁滑動導航窗口且可持續向更早頁讀取。背景history／explicit rebuild保持當期個股與篩選主線可用；schema／來源／hash／cancel／故障不偽造完整，原immutable來源／舊收藏不遷移。索引最多64MiB，每頁串流重核全index SHA及頁內原manifest/artifact，年度calendar以4096entries／32MiB逐份驗證，不再32份正常累積即整批未知。

限定受影響79個不重複案例、Workbench85、validator25／4skip、mypy788、11變更Python編譯與精度／未來函數guard通過。真實已保存三股來源隔離offscreen回放：晚發布仍unknown、17來源hash與正式DBsize/mtime不變、worker0；沒有讀正式DB去重核current identity。130日×2修訂合成metadata全260refs走9頁，index159744 bytes、最大page JSON13814 bytes／tracemalloc1226583 bytes；不當自然樣本或正式長期總容量證明。

本包關閉UX09索引／分頁／索引程式內版本復原；第一版工程剩餘固定F1–F4，詳細終點與owner見收據。Backtest18.62%／20%仍差1.38百分點，不重測湊數或放寬。舊1477 Native已在6691ec78通過，較早「仍待1477」文字由此更正；新分頁／跨頁Native及3–5位真人另驗。1000×835 outer／125%已接受，不新增1000×800硬門檻。具名full-cohort與原完整Top/Bottom標籤沿現況，官方全市場／新百分位方法只有擴充時才要明確決定，不阻塞目前研究限定工程。

完整操作與排錯見 APPLICATION_MANUAL 的歷史索引小節；[詳細驗證、來源選項與F1–F4凍結清單](../06_qa/UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md)。


- 2026-10-05：[F2／F3 原市場共享來源及已開能力矩陣](../06_qa/F2_F3_SHARED_CONSUMERS_AND_CAPABILITIES_20261005.md)，A／A 限定完成；F1／F4 與新 Native／真人另列。


- 2026-10-05：[F4跨頁整合與資源終驗](../06_qa/F4_RELEASE_INTEGRATION_AND_RESOURCE_ACCEPTANCE_20261005.md)：actual三程序雙收藏讀回通過；20-session實測有效，120/250長保留因二次payload超現有預算blocked，F4未全關閉；F1／新Native／真人另列。

- 2026-10-05：[F4項目revision儲存與20／120／250實測](../06_qa/F4_ITEM_REVISION_STORAGE_AND_RETENTION_20261005.md)：新v3長留存與actual App通過，原預算不變；正式舊SQLite COW converter與切換仍待工程／核准。

- 2026-10-05：[F4 SQLite COW converter／明示activation終驗](../06_qa/F4_SQLITE_COW_CONVERTER_AND_ACTIVATION_20261005.md)：隔離工程完成；20→21→rollback20保留雙庫與target新歷史。正式store/mode與使用者apply批准另列，不讀真實JSON、不初始化缺失DB。


- 2026-10-05：[F4 Legacy JSON COW／原升級入口終驗](../06_qa/F4_LEGACY_JSON_COW_AND_ACTIVATION_20261005.md)：單JSON至獨立v3、新程序讀回及rollback保留新內容；正式apply另行批准，F1例外尚未批准，UX07未啟動。

- 2026-10-05：[UX07 圖表可行性調查](../06_qa/UX07_CHART_FEASIBILITY_20261005.md)：官方授權／台股覆蓋、外部連結／Widgets／LWC／原生基線比較與 repo 入口；調查已交付，選型／原型／UX08 整合未完成，正式 JSON 套用及 F1 例外仍另列。


- 2026-10-06：[個人儲存 lane 與 App 整合](../06_qa/PERSONAL_STORAGE_SEPARATION_LANE_20261005.md)：opt-in 路徑、private COW 控制檔、原來源唯讀與回滾停止 writer；正式 root／遷移／Native 另列。


- 2026-10-06：[UX10 多方法 readmodel 與 consumer](../06_qa/UX10_MULTI_METHOD_LANE_20261006.md)：同pin三態、股票與family去重；雙MA=2方法1家族，跨family未知，UX10 partial。
