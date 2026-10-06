# 歷史原文：docs/README.md

> 2026-10-06 封存；原文曾含 2026-10-07 作業標記，日期不重寫。狀態：superseded-by [README.md](../README.md) 的現況摘要。原始 bytes 另保存在本輪 ignored 稽核 original_bytes；原 SHA256 `f396041cc59e3d0485ca2b4cda47e9adedcb8cdb16d1cffd3657274e1f1da793`。下文只調整搬移後相對連結，不刪需求、不授予完成資格。

# 文件入口

目前狀態與本週優先事項請讀 [專案快照](../00_core/PROJECT_SNAPSHOT.md)。本頁只提供文件入口；不重複維護容量、Gate、測試數字或當前待辦。

## 權威閱讀順序

1. [專案快照](../00_core/PROJECT_SNAPSHOT.md)：唯一目前狀態入口。
2. [Roadmap Hub](../00_core/DEVELOPMENT_ROADMAP.md)：依主題導向產品、工程與版本路線。
3. [產品方向](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md)與[未來六個月工程路線](../00_core/ROADMAP_6M_ENGINEERING.md)。
4. [目前系統架構](../01_architecture/system_architecture.md)；未來架構請看[FINAL 目標架構](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)。
5. 使用者操作請看[完整操作手冊](../07_guides/APPLICATION_MANUAL.md)。
6. 各領域文件由[文檔索引](../00_core/DOCUMENTATION_INDEX.md)導覽；日期化驗收見[QA 目錄](../06_qa/README.md)，歷史紀錄見[Archive](README.md)。

## 文件分類

| 目錄 | 用途 | 導覽 |
|---|---|---|
| `00_core/` | Scoped SSOT、路線圖與文件治理 | [核心文件](../00_core/README.md) |
| `01_architecture/` | 現況架構、目標架構與模組邊界 | [架構文件](../01_architecture/README.md) |
| `02_features/` | UI、功能、策略與研究說明 | [功能文件](../02_features/README.md) |
| `03_data/` | 資料流程與維護 | [資料文件](../03_data/README.md) |
| `04_broker_branch/` | 券商分點與籌碼資料 | [資料夾索引](../04_broker_branch/README.md) |
| `05_phases/` | 歷史 Phase 設計 | [Historical / Reference](../05_phases/README.md) |
| `06_qa/` | 測試、驗收與問題追蹤 | [QA 導覽](../06_qa/README.md) |
| `07_guides/` | 安裝、操作與測試指引 | [指南](../07_guides/README.md) |
| `08_technical/` | 技術備忘 | [技術文件](../08_technical/README.md) |
| `09_archive/` | 已完成或過期文件的歷史追溯 | [封存目錄](README.md) |
| `agents/`、`superpowers/`、`strategies/` | Agent 規範、設計追溯、策略說明 | [Agent](../agents/README.md)、[Superpowers](../superpowers/README.md)、[策略](../strategies/README.md) |

根目錄 `AGENTS.md` 是 Codex 指令入口；[PROJECT_NAVIGATION.md](../../PROJECT_NAVIGATION.md) 是開發者功能導航。文件生命週期與更新責任見[DOCUMENTATION_STRUCTURE](../00_core/DOCUMENTATION_STRUCTURE.md)及[DOC_COVERAGE_MAP](../00_core/DOC_COVERAGE_MAP.md)。


## 2026-10-05 UX09 有界 MA 名單入選歷程

既有兩條 MA 三態快照經純比較模型、有限歷史 reader 與背景 UI 呈現本次新入選／持續符合／重新入選／未再符合，並保存前次日期、理由與可回放來源身份；不是策略升降級服務。無效／缺件／漏日／同日修訂／版本或母體變更及回填保持未知，不在刷新時寫事件。日曆只讀現有快取，publication 前可得性核驗；現有真實來源只有同日，不能作跨日自然歷程證明。

此為原計畫 §8.1／UX09 的研究讀取切片；不更換母體權威或舊標籤、不啟動自然 capture／outcome 階段5，不宣告首版完成。完整方法字典、其他 consumer 融合、正式母體／排程與其他 writer 生命周期仍是工程待辦，Backtest18.62%／20%不變；Native與真人驗收另待桌面時段。詳見 [UX09 限定收據](../06_qa/UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md)。


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
