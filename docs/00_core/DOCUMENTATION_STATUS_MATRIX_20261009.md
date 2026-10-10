# 文件整理狀態矩陣（2026-10-09）

> 本矩陣記錄一次可追溯的全目錄盤點基線，不宣稱所有文件已完成逐篇內容審閱。分類、正文核讀、入口連結與待修候選分開計數；目錄可達不等於內容正確。當前狀態與主題權威仍依 [Scoped SSOT 覆蓋地圖](DOC_COVERAGE_MAP.md) 判讀。

## 盤點基線與範圍

- Git 基線：`9b8e0ea45294d89cd08c5185478f0b8c51e0f54e`（2026-10-09）。
- 盤點對象：基線中已追蹤的 `docs/` 路徑，共 **1,473** 個；不把本機未追蹤文件算入總數。
- 當時尚有另一個 agent 的產品補完工作。以下工作樹文件不作正文審查，也不覆寫：`docs/00_core/DOCUMENTATION_INDEX.md`、`docs/00_core/PROJECT_SNAPSHOT.md`、`docs/07_guides/APPLICATION_MANUAL.md`、`docs/07_guides/README.md`、`docs/07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md`、`docs/06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md`，以及未追蹤的排程 remediation QA/runbook。它們可能在此基線之後再有變化，後續需另行核對。
- 分類是目錄層級角色盤點，不等於逐檔正文核實。內容審閱深度只計入可由審閱記錄明確證實的路徑或數量；未留下深度記錄者標為「不可還原」，不推定已讀或未讀。
- `docs/06_qa/` 與 `docs/09_archive/` 的正文核讀數據，是先前 `0c9f84bb` 基線的歷史下限；路徑總數則依本矩陣的 `9b8e0ea4` 基線。不得把舊基線的核讀數據描述成最新 HEAD 的完整覆核。

## 各目錄角色盤點

以下「目錄總數」是各列互斥角色欄位的加總。支援／導覽、QA 葉節點等較寬分類只表示主要用途，不替代逐檔內容審核。

| 目錄 | 追蹤路徑 | 權威／工作規範 | 導覽／支援 | 指南／計畫 | QA／證據 | 混合 | 歷史／轉址 | 資產／模板 | 備註 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `docs/` 根目錄 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 專案文件入口 README。 |
| `00_core/` | 17 | 8 | 4 | 0 | 0 | 0 | 5 | 0 | 4 份是支援性核心文件；個別正文核讀深度沒有留下逐檔紀錄。 |
| `01_architecture/` | 224 | 10 | 5 | 36 | 2 | 2 | 169 | 0 | 指南／執行契約與歷史設計材料數量多；17 份文件的核讀深度不可還原。 |
| `02_features/` | 9 | 5 | 1 | 0 | 0 | 0 | 3 | 0 | 功能權威與入口文件居多。 |
| `03_data/` | 17 | 3 | 1 | 0 | 4 | 0 | 8 | 1 | 另有一份月營收可得性 CSV 欄位模板，不是實際公告日期資料。 |
| `04_broker_branch/` | 6 | 1 | 1 | 0 | 0 | 0 | 4 | 0 | 主要為歷史指南／快照。 |
| `05_phases/` | 15 | 0 | 2 | 0 | 0 | 0 | 13 | 0 | 13 份舊 Phase 轉址頁；轉址頁仍需保留舊入口。 |
| `06_qa/` | 563 | 0 | 5 | 0 | 526 | 0 | 32 | 0 | 5 份主索引、32 份歷史相容轉址，其餘是 QA 葉內容／附屬資產；其中含 11 個非 Markdown 路徑，葉節點尚未逐篇語義分類。 |
| `07_guides/` | 19 | 4 | 1 | 8 | 0 | 2 | 4 | 0 | 手冊章節、作業指南與少數混合型歷史補充。工作樹 Manual／README／排程文件略過。 |
| `08_technical/` | 7 | 2 | 1 | 0 | 0 | 0 | 4 | 0 | 含一份已做全文核對的圖表渲染文件。 |
| `09_archive/` | 404 | 0 | 8 | 0 | 0 | 0 | 396 | 0 | 8 份導覽／來源清冊，其餘為歷史文件與附屬資產；共含 397 個 Markdown 路徑。 |
| `agents/` | 21 | 11 | 9 | 0 | 0 | 0 | 1 | 0 | 工作流程權威、角色入口與歷史相容文件。 |
| `strategies/` | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 兩份使用者策略說明依其 README 為非權威參考；策略規格與程式登錄才是權威。 |
| `superpowers/` | 167 | 0 | 97 | 1 | 0 | 0 | 69 | 0 | 96 份舊路徑轉址加 README，共 97 導覽項；1 份目前 task plan；69 份保留歷史原文。 |
| **合計** | **1,473** | **44** | **137** | **47** | **532** | **4** | **708** | **1** | 角色欄位加總與追蹤路徑總數一致。 |

## 正文核讀覆蓋

| 範圍 | 可證實的核讀狀況 | 尚未確認／限制 |
|---|---|---|
| `00_core/`（17） | 取得了目錄角色盤點與核心權威邊界資料。 | 原審閱記錄未保留逐檔讀取深度；17/17 深度不可還原，不能將角色盤點算成內容審核。 |
| `01_architecture/` + `07_guides/`（243） | 24 份有具名段落核讀記錄；202 份僅有索引／README／標題層級分類。 | 17 份深度不可還原；沒有具名全文核讀記錄。已排除工作樹中另一 agent 正在改的 Guides 文件。 |
| 根 `docs/README.md`、`02_features/`、`03_data/`、`04_broker_branch/`、`05_phases/`、`08_technical/`（55） | 可明確證實 2 份全文核讀：`docs/05_phases/PHASE2_ARCHITECTURE.md`（5 行轉址頁）、`docs/08_technical/UI_QT_CHART_RENDERING.md`（109 行）；2 份局部核讀：`docs/05_phases/README.md` 第 15、21 行，`docs/02_features/BACKTEST_LAB_FEATURES.md` 第 340–360 行。 | 其餘文件未有可逐檔還原的正文核讀深度。五份目錄 README 加 `docs/README.md` 抽出 110 次連結出現、82 個去重路徑；此抽取未驗證目標存在或錨點。先前「55/55」連結數的原始檢查範圍不可還原，不用作全目錄連結覆蓋結論。 |
| `agents/`、`strategies/`、`superpowers/`（191） | 正文抽讀記錄：agents 20/21（以角色摘要／前段為主）；strategies 3/3；superpowers 9/167（README 與 8 份代表文件）。 | 這些數量是抽讀文件數，不等於全文閱讀數；其餘多依 README、manifest、標題或路徑分類。 |
| `06_qa/`、`09_archive/`（967） | 舊基線 `0c9f84bb` 有明確記錄下限：全文 10 份（QA 5、Archive 5），局部核讀至少 2 份 QA；另有 7 份正文主張曾被核對但範圍不明。 | 這是舊基線下限，不是最新 HEAD 完整覆核。另有 7 份僅做導覽／來源文件檢視；不得把連結盤點當正文審核。F03 follow-up 的工作樹內容依指示略過。 |

全體文件沒有一個可支持「已逐篇讀完」的比例。上述數字只表達可追溯的審閱證據；正文審閱數、入口連結覆蓋及分類完成度是不同指標，不能互相代替。

## 入口與本機連結檢查

- **Architecture + Guides：** 抽取 1,323 個 Markdown 本機連結（1,265 個相對連結、58 個 Windows `file://` 連結）；1,317 個指向基線追蹤目標，6 個未命中 Git 追蹤目標且都指向被忽略的 `output/qa/` 收據。工作區外的輸出可能存在；未檢查錨點。
- **QA：** 5 份主索引連到 200 個去重目標，其中 195 個是 QA 葉目標；32 份歷史相容轉址皆指向追蹤中的 Archive 原文。以 531 個非轉址項為分母，主索引直接涵蓋 195 個（36.7%）；這是直接入口比例，不是全文審核比例，也不含其他 QA 文件間的轉介。
- **Archive：** 6 份 README、Coverage History 與 Superpowers manifest 的入口核對覆蓋 404/404 個追蹤路徑；這表示可由 Archive 導覽抵達，不表示 404 份正文都已審閱。
- **agents／strategies／superpowers：** README 直接 Markdown 連結數分別是 12/20、0/2、9/166；策略 README 以 inline-code 路徑列出 2/2。檢查到的相對檔案目標均存在；錨點未驗證。
- **其餘 README 抽取：** 只確認連結出現與去重路徑數，未確認全部目標存在；不合併為全庫解析率。

## 已確認的內容不一致與修正候選

以下是可追溯候選，尚不表示本批已修正。QA 收據與 SHA／PASS／FAIL／未驗證界線保持為證據；若需校正入口，修改導覽或加註判讀，不改寫原始收據。

### 已確認，排入後續內容修正批次

1. `docs/05_phases/README.md:15` 將 Strategy Design Spec 說成直接連到 Archive；實際先連到保留的 `PHASE2_ARCHITECTURE.md` 短轉址頁，再到 Archive。修正 README 的描述即可，保留舊路徑。
2. `docs/superpowers/README.md:28` 將 167 寫成歷史文件數；manifest 有 165 個唯一歷史來源（96 個 Archive 原文 + 69 個仍在原處的歷史文件）。另有 96 個轉址頁、1 個目前計畫與 README；兩筆 Scheduler Approval 補充列會使全文 grep 計數重複。應釐清計數口徑，不移除轉址頁或證據。
3. `docs/02_features/BACKTEST_LAB_FEATURES.md:340–360` 的 P8 TODO 不能整段標成已完成：風險百分比倉位與 ATR stop 的引擎語義仍有不一致；賣出量上限目前明確關閉；成本可設定佣金／滑價，但沒有可選成本模型，賣出稅仍固定。後續只校正 TODO 的精確範圍，不把未完成項寫成完成。
4. `docs/08_technical/UI_QT_CHART_RENDERING.md` 的實作位置與條件有漂移：圖表 widget 在 `result_panel.py` 建立，`backtest_view.py` 只初始化 result panel；報酬分布圖需至少 10 筆交易才用零中心圖；替代文字最多呈現 200 筆並標示省略數。翻譯／更新時保留程式識別字與限制，避免把未量測的效能描述寫成事實。
5. `docs/agents/skills/quant_defense_guard.md` 白名單仍寫 `app_module/strategies/`，目前 look-ahead 檢查器掃描 `decision_module/strategies/`。
6. `docs/agents/antigravity/tech_lead_agent.md` 的 Month 3／4 預設焦點與現行 6M Roadmap Gate 2+3、Portfolio Coach v1 不一致；更新時以 Roadmap 權威為準。

### 需第二輪逐段確認後再決定

- `docs/01_architecture/README.md` 對 Gate 7 的範圍可能窄於產品 Roadmap；`system_architecture.md` 的 Recommendation Shadow 與 Allocation 共用 Gate 7 QA 引用，但目前證據偏 Allocation。需先分清產品承諾、目前實作與 QA 覆蓋。
- `docs/01_architecture/target_system_architecture.md` 的 §10.11 含易變狀態描述，應核對是否有 Snapshot／QA 導引。
- `docs/01_architecture/V2_2_WEEKLY_REVIEW_RUNBOOK.md` 日期較早，需明確界定是否為歷史流程或仍生效程序。
- 兩份 `EVIDENCE_*` runbook 同時描述證據與執行步驟，確認保留混合定位或拆開入口。
- `docs/00_core/AI_CONTEXT_PACK.md` 是歷史轉址頁，但可能缺少直達 Archive 原文的連結。
- `docs/00_core/DOCUMENTATION_GRAPH_GUIDE.md` 指定 `graphifyy 0.9.11`，須重新確認版本與命令後才可作現行操作步驟。
- Agent README／交接模板的條件式必讀入口、`multi_agent_workflow.md` 的 `dev` 整合與 worktree 生命週期說明，需對照根 `AGENTS.md` 及 shared context 後再修。

## 後續整理順序與完成定義

1. 先完成本矩陣列出的逐檔內容衝突核對；每批只改核實過的乾淨文件，保留另一 agent 的工作樹變更。
2. 每次搬移、改名或改入口時，同步更新對應目錄 README／主題索引、中央 Index（若入口或權威邊界受影響）與 [Coverage History](../09_archive/DOC_COVERAGE_HISTORY_2026.md)。
3. QA 與 Archive 從入口可達、正文已讀、狀態與證據仍有效四方面分開統計；不把舊 QA 快照重寫成新結論。
4. 全部目錄候選清理完後，再做全庫連結與錨點檢查、複核矩陣數字，最後刷新並驗證文件圖譜。圖譜刷新不代表正文審核已完成。

**狀態：** 目錄角色與可追溯審閱基線已建立；內容衝突修正、尚未核讀文件的逐篇審查、全庫錨點驗證及 Graphify 刷新仍未完成。
