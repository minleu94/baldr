# 文件整理狀態矩陣（2026-10-09）

> 本矩陣記錄一次可追溯的全目錄盤點基線，不宣稱所有文件已完成逐篇內容審閱。分類、正文核讀、入口連結與待修候選分開計數；目錄可達不等於內容正確。當前狀態與主題權威仍依 [Scoped SSOT 覆蓋地圖](DOC_COVERAGE_MAP.md) 判讀。

## 盤點基線與範圍

- 初始審閱基線：`9b8e0ea45294d89cd08c5185478f0b8c51e0f54e`（2026-10-09），當時有 **1,473** 個已追蹤 `docs/` 路徑。
- 本次目錄角色表依目前 `dev` HEAD `3079a43a8d00d3e8f403f42310454dc8eecbbec0` 統計，共 **1,476** 個已追蹤路徑。增加的 3 個路徑是本矩陣、排程修正 QA 與排程稽核 Runbook；本機未追蹤檔不計入。
- 使用者已確認 `e6f79063` 的排程修正可納入本次文檔整理。已完整閱讀 `BALDR_SCHEDULE_REMEDIATION_20261009.md` 與 `BALDR_SCHEDULED_AUDIT_RUNBOOK.md`，並核對 QA README、Index、Snapshot、Manual、Guides README 及排程操作指南中的相關段落與互相連結。F03 follow-up 的未提交正文仍屬其他工作的進行中內容，本輪不覆寫。
- 分類是目錄層級角色盤點，不等於逐檔正文核實。內容審閱深度只計入可由審閱記錄明確證實的路徑或數量；未留下深度記錄者標為「不可還原」，不推定已讀或未讀。
- QA／Archive 舊有正文核讀數據，是先前 `0c9f84bb` 基線的歷史下限；其他目錄的分類與連結抽取多依 `9b8e0ea4` 初始基線。本表另外列出目前 HEAD 的追蹤路徑數，以及本次可具名追溯的補充閱讀；舊連結抽取結果不冒充全庫最新驗證。

## 各目錄角色盤點

以下「目錄總數」是各列互斥角色欄位的加總。支援／導覽、QA 葉節點等較寬分類只表示主要用途，不替代逐檔內容審核。

| 目錄 | 追蹤路徑 | 權威／工作規範 | 導覽／支援 | 指南／計畫 | QA／證據 | 混合 | 歷史／轉址 | 資產／模板 | 備註 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `docs/` 根目錄 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 專案文件入口 README。 |
| `00_core/` | 18 | 8 | 5 | 0 | 0 | 0 | 5 | 0 | 原 17 份核心文件的逐檔核讀深度不可還原；本矩陣為新增並全文檢視的支援文件。 |
| `01_architecture/` | 224 | 10 | 5 | 36 | 2 | 2 | 169 | 0 | 指南／執行契約與歷史設計材料數量多；17 份文件的核讀深度不可還原。 |
| `02_features/` | 9 | 5 | 1 | 0 | 0 | 0 | 3 | 0 | 功能權威與入口文件居多。 |
| `03_data/` | 17 | 3 | 1 | 0 | 4 | 0 | 8 | 1 | 另有一份月營收可得性 CSV 欄位模板，不是實際公告日期資料。 |
| `04_broker_branch/` | 6 | 1 | 1 | 0 | 0 | 0 | 4 | 0 | 主要為歷史指南／快照。 |
| `05_phases/` | 15 | 0 | 2 | 0 | 0 | 0 | 13 | 0 | 13 份舊 Phase 轉址頁；轉址頁仍需保留舊入口。 |
| `06_qa/` | 564 | 0 | 5 | 0 | 527 | 0 | 32 | 0 | 5 份主索引、32 份歷史相容轉址，其餘是 QA 葉內容／附屬資產；其中含 11 個非 Markdown 路徑，葉節點尚未逐篇語義分類。 |
| `07_guides/` | 20 | 4 | 1 | 9 | 0 | 2 | 4 | 0 | 手冊章節、作業指南與少數混合型歷史補充；新增的排程稽核 Runbook 已全文閱讀。 |
| `08_technical/` | 7 | 2 | 1 | 0 | 0 | 0 | 4 | 0 | 含一份已做全文核對的圖表渲染文件。 |
| `09_archive/` | 404 | 0 | 8 | 0 | 0 | 0 | 396 | 0 | 8 份導覽／來源清冊，其餘為歷史文件與附屬資產；共含 397 個 Markdown 路徑。 |
| `agents/` | 21 | 11 | 9 | 0 | 0 | 0 | 1 | 0 | 工作流程權威、角色入口與歷史相容文件。 |
| `strategies/` | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 兩份使用者策略說明依其 README 為非權威參考；策略規格與程式登錄才是權威。 |
| `superpowers/` | 167 | 0 | 97 | 1 | 0 | 0 | 69 | 0 | 96 份舊路徑轉址加 README，共 97 導覽項；1 份目前 task plan；69 份保留歷史原文。 |
| **合計** | **1,476** | **44** | **138** | **48** | **533** | **4** | **708** | 角色欄位加總與目前 HEAD 的追蹤路徑總數一致。 |

## 正文核讀覆蓋

| 範圍 | 可證實的核讀狀況 | 尚未確認／限制 |
|---|---|---|
| `00_core/`（18） | 新增的本矩陣已全文檢視；另針對 e6 排程修正閱讀 Snapshot 與 Index 的排程段落。 | 原 17 份核心文件的逐檔讀取深度仍不可還原；目錄角色盤點不能代替內容審核。 |
| `01_architecture/` + `07_guides/`（244） | 初始基線有 24 份具名段落核讀記錄、202 份索引／README／標題層級分類；補充全文閱讀新增排程稽核 Runbook 1 份。另核對 Manual、Guides README 與排程操作指南的 e6 相關段落及連結。 | 原 243 份文件中 17 份深度不可還原；其餘逐篇內容仍未全面覆核。 |
| 根 `docs/README.md`、`02_features/`、`03_data/`、`04_broker_branch/`、`05_phases/`、`08_technical/`（55） | 可明確證實 2 份全文核讀：`docs/05_phases/PHASE2_ARCHITECTURE.md`（5 行轉址頁）、`docs/08_technical/UI_QT_CHART_RENDERING.md`（109 行）；2 份局部核讀：`docs/05_phases/README.md` 第 15、21 行，`docs/02_features/BACKTEST_LAB_FEATURES.md` 第 340–360 行。 | 其餘文件未有可逐檔還原的正文核讀深度。五份目錄 README 加 `docs/README.md` 抽出 110 次連結出現、82 個去重路徑；此抽取未驗證目標存在或錨點。先前「55/55」連結數的原始檢查範圍不可還原，不用作全目錄連結覆蓋結論。 |
| `agents/`、`strategies/`、`superpowers/`（191） | 正文抽讀記錄：agents 20/21（以角色摘要／前段為主）；strategies 3/3；superpowers 9/167（README 與 8 份代表文件）。 | 這些數量是抽讀文件數，不等於全文閱讀數；其餘多依 README、manifest、標題或路徑分類。 |
| `06_qa/`、`09_archive/`（968） | 舊基線 `0c9f84bb` 有明確記錄下限：全文 10 份（QA 5、Archive 5），局部核讀至少 2 份 QA；本次再全文閱讀排程修正 QA 1 份，故可具名全文閱讀至少 11 份（QA 6、Archive 5）。 | 舊有 7 份正文主張曾被核對但範圍不明，另有 7 份只檢視導覽／來源。這不是整個 QA／Archive 的最新全面覆核；F03 follow-up 工作樹正文仍略過。 |

全體文件沒有一個可支持「已逐篇讀完」的比例。上述數字只表達可追溯的審閱證據；正文審閱數、入口連結覆蓋及分類完成度是不同指標，不能互相代替。e6 排程 QA 與 Runbook 已納入本次補充閱讀，不再列為排除項目。

## 入口與本機連結檢查

- **Architecture + Guides：** 初始基線抽取 1,323 個 Markdown 本機連結（1,265 個相對連結、58 個 Windows `file://` 連結）；1,317 個指向基線追蹤目標，6 個未命中 Git 追蹤目標且都指向被忽略的 `output/qa/` 收據。e6 新增 Runbook 的 Index／Guide／Manual 入口已逐項核對；未重跑此範圍的全量連結抽取，錨點亦未全量驗證。
- **QA：** 初始基線的 5 份主索引連到 200 個去重目標，其中 195 個是 QA 目標；32 份歷史相容轉址皆指向追蹤中的 Archive 原文。e6 的排程 QA 現由 QA README、中央 Index、Snapshot 與 Manual 連入；不將該新增頁面追寫為初始基線的本地 QA 索引覆蓋數。舊基線 195/531（36.7%）是直接入口比例，不是全文審核比例，也不含其他 QA 文件間的轉介。
- **Archive：** 6 份 README、Coverage History 與 Superpowers manifest 的入口核對覆蓋 404/404 個追蹤路徑；這表示可由 Archive 導覽抵達，不表示 404 份正文都已審閱。
- **agents／strategies／superpowers：** README 直接 Markdown 連結數分別是 12/20、0/2、9/166；策略 README 以 inline-code 路徑列出 2/2。檢查到的相對檔案目標均存在；錨點未驗證。
- **其餘 README 抽取：** 只確認連結出現與去重路徑數，未確認全部目標存在；不合併為全庫解析率。

## 已確認的內容不一致與修正候選

以下分列已修正、仍待修與已撤回的候選。QA 收據與 SHA／PASS／FAIL／未驗證界線保持為證據；若需校正入口，修改導覽或加註判讀，不改寫原始收據。

### 已確認並於 Coverage History Entry 171 修正

1. `docs/05_phases/README.md` 已說明現行策略規格先引用舊路徑相容轉址頁；本目錄清單則直接連 Archive 原文。
2. `docs/superpowers/README.md:28` 與 Archive manifest 已區分 167 筆列示與 165 個唯一歷史來源路徑（96 個 Archive 原文 + 69 個仍在原處的歷史文件）；兩筆 Scheduler Approval plan/spec 在補充詳表重列。96 個舊路徑轉址頁、1 個目前計畫及 README 仍分別計數，未移除證據。
3. `docs/agents/skills/quant_defense_guard.md` 的三個策略檔案路徑已與檢查器使用的 `decision_module/strategies/` 一致。
4. `docs/agents/antigravity/tech_lead_agent.md` 的工作焦點已改為參照 Snapshot 與 6M Roadmap，並明確 Month 3=Gate 2+3、Month 4=Gate 4。

### 已確認並完成修正（Entry 172）

1. `docs/08_technical/UI_QT_CHART_RENDERING.md` 已翻譯並依目前程式校正延後建立位置、QtWebEngine／Matplotlib factory 條件、報酬樣本門檻、鍵盤操作及最多 200 列的文字替代。移除未有基準測量支持的「更快」效能主張；保留程式識別字及現有驗證命令，註明本次未執行測試。

### 已撤回：缺少程式依據的候選

- 先前草稿將 `docs/02_features/BACKTEST_LAB_FEATURES.md:340–360` 描述為 P8 TODO，並延伸出倉位、ATR stop、賣出量與成本模型缺口。重新核對目前 HEAD 後，該文件沒有 P8 標記，所指行段也不是該 TODO；此候選撤回，不改功能文件，也不將舊判斷當作專案現況。

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

**狀態：** 目錄角色與可追溯審閱基線已建立；Entry 171 修正 4 組明確內容漂移，Entry 172 更新至目前 HEAD 並納入 e6 排程文件覆核；P8 候選已撤回，圖表渲染說明已依程式修正。其餘待核候選、尚未核讀文件的逐篇審查、全庫錨點驗證及 Graphify 刷新仍未完成。
