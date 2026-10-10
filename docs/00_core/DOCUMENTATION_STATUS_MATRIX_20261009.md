# 文件整理狀態矩陣（2026-10-09）

> 本矩陣記錄一次可追溯的全目錄盤點基線，不宣稱所有文件已完成逐篇內容審閱。分類、正文核讀、入口連結與待修候選分開計數；目錄可達不等於內容正確。當前狀態與主題權威仍依 [Scoped SSOT 覆蓋地圖](DOC_COVERAGE_MAP.md) 判讀。

## 盤點基線與範圍

- 初始審閱基線：`9b8e0ea45294d89cd08c5185478f0b8c51e0f54e`（2026-10-09），當時有 **1,473** 個已追蹤 `docs/` 路徑。
- 本次整理完成後、截至文件 commit `217115f2` 的目錄角色表共 **1,478** 個已追蹤路徑；相較 9b 初始基線增加 5 個：本矩陣、排程修正 QA、共用排程稽核 Runbook、封存的 morning-check 原文副本與 Agent workflow 歷史快照。舊 morning-check 路徑保留短導引，不另增加該路徑數；其他本機未追蹤檔不計入。後續平行開發 commits `45d138b7`、`963b04ea` 的內容未納入本輪正文審閱或圖譜基線。
- 此處範圍只含 Git 追蹤的 `docs/` 路徑；由 `git_exclusions.md` 排除的本機／ignored 狀態檔（例如 `docs/agents/shared_state/`）不計入，亦不作為文件完整性或現況證據。
- 使用者已確認 `e6f79063` 的排程修正可納入本次文檔整理。已完整閱讀 `BALDR_SCHEDULE_REMEDIATION_20261009.md` 與 `BALDR_SCHEDULED_AUDIT_RUNBOOK.md`，並核對 QA README、Index、Snapshot、Manual、Guides README 及排程操作指南中的相關段落與互相連結。F03 follow-up 的未提交正文仍屬其他工作的進行中內容，本輪不覆寫。
- 分類是目錄層級角色盤點，不等於逐檔正文核實。內容審閱深度只計入可由審閱記錄明確證實的路徑或數量；未留下深度記錄者標為「不可還原」，不推定已讀或未讀。
- QA／Archive 舊有正文核讀數據，是先前 `0c9f84bb` 基線的歷史下限；其他目錄的分類與連結抽取多依 `9b8e0ea4` 初始基線。本表另外列出目前 HEAD 的追蹤路徑數，以及本次可具名追溯的補充閱讀；舊連結抽取結果不冒充全庫最新驗證。

## 各目錄角色盤點

以下「目錄總數」是各列互斥角色欄位的加總。「權威／工作規範」指限定主題範圍的權威文件，不代表全域操作權威；例如 `02_features/` 的功能行為參考與專題指南仍不取代完整 Manual。支援／導覽、QA 葉節點等較寬分類只表示主要用途，不替代逐檔內容審核。

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
| `07_guides/` | 20 | 4 | 1 | 8 | 0 | 2 | 5 | 0 | 手冊章節、作業指南與少數混合型歷史補充；包含一個已轉為 Archive 導引的舊路徑。 |
| `08_technical/` | 7 | 2 | 1 | 0 | 0 | 0 | 4 | 0 | 含一份已做全文核對的圖表渲染文件。 |
| `09_archive/` | 406 | 0 | 8 | 0 | 0 | 0 | 398 | 0 | 8 份導覽／來源清冊，其餘為歷史文件與附屬資產；共含 399 個 Markdown 路徑。 |
| `agents/` | 21 | 11 | 9 | 0 | 0 | 0 | 1 | 0 | 工作流程權威、角色入口與歷史相容文件。 |
| `strategies/` | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 兩份使用者策略說明依其 README 為非權威參考；策略規格與程式登錄才是權威。 |
| `superpowers/` | 167 | 0 | 97 | 1 | 0 | 0 | 69 | 0 | 96 份舊路徑轉址加 README，共 97 導覽項；1 份目前 task plan；69 份保留歷史原文。 |
| **合計** | **1,478** | **44** | **138** | **47** | **533** | **4** | **711** | **1** | 角色欄位加總與本次整理後的追蹤路徑總數一致。 |

## 正文核讀覆蓋

| 範圍 | 可證實的核讀狀況 | 尚未確認／限制 |
|---|---|---|
| `00_core/`（18） | 本輪已逐檔核對 18 份：11 份全文閱讀、7 份局部核讀；每份的角色、生命週期、核讀深度與衝突判讀見下方逐檔表。 | 既有 2026-10-09 審閱的歷史深度只可從舊記錄還原部分路徑；本輪表格另列實際閱讀範圍，不把段落抽查算成全文閱讀。 |
| `01_architecture/` + `07_guides/`（244） | 初始基線有 24 份具名段落核讀記錄、202 份索引／README／標題層級分類；補充全文閱讀新增排程稽核 Runbook 1 份及已封存 morning-check 原文 1 份。另核對 Manual、Guides README 與排程操作指南的 e6 相關段落及連結。 | 原 243 份文件中 17 份深度不可還原；其餘逐篇內容仍未全面覆核。 |
| 根 `docs/README.md`、`02_features/`、`03_data/`、`04_broker_branch/`、`05_phases/`、`08_technical/`（55） | 可明確證實 2 份全文核讀：`docs/05_phases/PHASE2_ARCHITECTURE.md`（6 行轉址頁）、`docs/08_technical/UI_QT_CHART_RENDERING.md`（70 行）；2 份局部核讀：`docs/05_phases/README.md` 第 15、21 行，`docs/02_features/BACKTEST_LAB_FEATURES.md` 第 340–360 行。 | 其餘文件未有可逐檔還原的正文核讀深度。六份 README 以 Markdown `](...)` 目標抽出 109 次連結、正規化後 82 個唯一本機目的地；本次重算未驗證目標存在或錨點。先前「55/55」連結數的原始檢查範圍不可還原，不用作全目錄連結覆蓋結論。 |
| `agents/`、`strategies/`、`superpowers/`（191） | 正文抽讀記錄：agents 20/21（以角色摘要／前段為主）；strategies 3/3；superpowers 9/167（README 與 8 份代表文件）。 | 這些數量是抽讀文件數，不等於全文閱讀數；其餘多依 README、manifest、標題或路徑分類。 |
| `06_qa/`、`09_archive/`（970） | 舊基線 `0c9f84bb` 有明確記錄下限：全文 10 份（QA 5、Archive 5），局部核讀至少 2 份 QA；本次再全文閱讀排程修正 QA 1 份、封存 morning-check 原文 1 份與 Agent workflow 舊版 1 份，故可具名全文閱讀至少 13 份（QA 6、Archive 7）。 | 舊有 7 份正文主張曾被核對但範圍不明，另有 7 份只檢視導覽／來源。這不是整個 QA／Archive 的最新全面覆核；F03 follow-up 工作樹正文仍略過。 |

全體文件沒有一個可支持「已逐篇讀完」的比例。上述數字只表達可追溯的審閱證據；正文審閱數、入口連結覆蓋及分類完成度是不同指標，不能互相代替。e6 排程 QA 與 Runbook 已納入本次補充閱讀，不再列為排除項目。

### `00_core/` 逐檔分類與本輪核讀

| 文件 | 角色／生命週期 | 本輪核讀深度與判讀 |
|---|---|---|
| `AI_CONTEXT_PACK.md` | 歷史相容入口；原文已封存，現況轉看 Snapshot。 | 全文；不作目前狀態權威。 |
| `DEVELOPMENT_ROADMAP.md` | 現行 Roadmap Hub，負責導覽權威文件，不保存目前進度。 | 全文；與 Snapshot／6M Roadmap 職責相符。 |
| `DOCUMENTATION_CATALOG_20261006.md` | 日期化歷史目錄快照入口，不是即時清冊。 | 全文；日期與歷史定位明確。 |
| `DOCUMENTATION_GRAPH_GUIDE.md` | 現行 Graphify 導覽與維護指南，不是內容／驗收權威。 | 全文；固定基線、CLI 故障與抽取限制有標示。 |
| `DOCUMENTATION_INDEX.md` | 現行文件位置與導航權威，不是狀態權威。 | 局部；已補上本矩陣直接入口。 |
| `DOCUMENTATION_STATUS_MATRIX_20261009.md` | 日期化整理基線與覆核紀錄，不取代 Scoped SSOT。 | 全文；仍需完成其他目錄的逐檔核對。 |
| `DOCUMENTATION_STRUCTURE.md` | 現行文件生命週期、目錄歸屬及歸檔規則。 | 局部；核對權威、生命週期與整理檢查段落，未全文審查。 |
| `DOC_COVERAGE_MAP.md` | 現行跨文件 Scoped SSOT、同步矩陣與 DoD 權威。 | 局部；核對權威表、DoD 與更新記錄；移除兩組重複 Must 條目。 |
| `EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` | 外部研究／資料源候選 companion，不是現況或交付順序權威。 | 局部；前言明示研究基準為 2026-07-11、未重新查核外部 repo；外部參考待後續刷新。 |
| `LEGACY_ROADMAP_CARRYOVER.md` | 2026-06-15 歷史移交／結案記錄；目前工程順序回到 6M Roadmap，現況回到 Snapshot。 | 全文；將 fixed／quantile Gate 明確限定為 10 檔 pilot，不推定完整股票池已驗收。 |
| `NEXT_ACTION_PLAN.md` | 已封存一次性計畫的相容入口。 | 全文；明確導回現行 Snapshot／Roadmap。 |
| `PRODUCT_ROADMAP_POST_REFACTOR.md` | 現行產品方向與產品 Gate 權威，不負責目前進度。 | 局部；核對前言、基線、Gap 與 Gate；基線日期 2026-09-17 有標示。 |
| `PROJECT_SNAPSHOT.md` | 現行唯一狀態入口。 | 全文；已把 Index 從「完整文件清單」改為導覽，並分連歷史目錄快照與本矩陣。 |
| `README.md` | Core 區導航頁，不取代主題權威。 | 全文；Scoped Authority 導覽相符。 |
| `ROADMAP_6M_ENGINEERING.md` | 現行六個月工程順序、Gate 與驗收權威；進度看 Snapshot。 | 局部；核對前言、相對月份、Gate 5／7 與 Closeout，未見明確狀態衝突。 |
| `V4_COMPLETION_PLAN_2026_09_07.md` | 已封存完成計畫的歷史入口。 | 全文；日期及目前狀態入口明示。 |
| `VERSION_ROADMAP_V1_1_TO_V2_0.md` | 已封存版本路線的相容入口。 | 全文；明確排除作為目前工作順序。 |
| `VERSION_ROADMAP_V2_1_TO_V4_0.md` | 現行長期 maturity 權威；工程順序看 6M、現況看 Snapshot。 | 局部；核對前言與權責，未見與 Snapshot／6M 的直接衝突。 |

## 入口與本機連結檢查

- **2026-10-09 全 repo Markdown 掃描（固定基線，非最終覆核）：** Git tree `217115f2` 有 1,485 份 Markdown（`docs/` 1,459、`docs/` 外 26）。機器掃描排除另一 Agent 的 F03 follow-up 後，實際輸入為 1,484 份（`docs/` 1,458、`docs/` 外 26）。舊報告把掃描分區誤記為 `docs/` 1,468、其他 16；總輸入 1,484 正確。掃描只以本次整理工作樹中的 Graph Guide、Status Matrix、Coverage History 三份文件覆蓋固定基線內容，沒有包含 `217115f2` 之後其他文件的修改，因此結果不能代表目前 HEAD 的連結／錨點狀態。解析 9,432 個連結目標，其中 8,904 個一般本機目標、482 個外部連結及 532 個含錨點目標；缺少的本機目標 0、超出文件樹目標 0、未匹配錨點 0。GitHub `#L206` 行號錨點也依 576 行目標文件確認在範圍內。這是路徑與錨點檢查，不驗證外部網站或正文內容。完整本機結果位於忽略輸出的 `output/qa/baldr_documentation_reorganization_20261009/full_repo_documentation_link_anchor_check.json`。
- **Architecture + Guides：** 初始基線抽取 1,323 個 Markdown 本機連結（1,265 個相對連結、58 個 Windows `file://` 連結）；1,317 個指向基線追蹤目標，6 個未命中 Git 追蹤目標且都指向被忽略的 `output/qa/` 收據。e6 新增 Runbook 的 Index／Guide／Manual 入口已逐項核對；固定基線掃描補上當時的本機目標與錨點檢查，舊基線數字仍只代表固定快照。
- **QA：** 舊基線 `0c9f84bb` 的 5 份主索引，依 Markdown 本機連結解析並去重後，連到 246 個本機 Markdown 目的地，其中 200 個屬 `06_qa/`；排除 5 個主索引頁後，QA 葉節點目的地為 195 個。基準 `217115f2` 的相同口徑為 248 個本機 Markdown、201 個 QA 目的地、排除索引後 196 個 QA 葉節點。舊基線 `195/531` 的分母是排除 32 個歷史 stub 後的 531 個 QA 路徑，包含 5 個索引頁；這是直接入口比例，不是全文審核比例，也不含其他 QA 文件間的轉介。32 份歷史相容轉址皆指向追蹤中的 Archive 原文。e6 的排程 QA 現由 QA README、中央 Index、Snapshot 與 Manual 連入；不將該新增頁面追寫為初始基線的本地 QA 索引覆蓋數。
- **Archive：** 初始基線的 6 份 README、Coverage History 與 Superpowers manifest 曾核對 404/404 個追蹤路徑；新封存的 morning-check 與 Agent workflow 原文皆有 Archive README 直接入口。固定基線連結掃描沒有重算目前 manifest／目錄清冊與 406 個 Archive 路徑的一對一覆蓋；入口可達仍不代表正文均已審閱。
- **agents／strategies／superpowers：** README 直接 Markdown 連結數分別是 12/20、0/2、9/166；策略 README 以 inline-code 路徑列出 2/2。固定基線掃描確認當時納入範圍的本機目標與錨點均存在，但不代表內容已逐篇核實或目前 HEAD 仍通過。
- **其餘 README 抽取：** 初始基線只確認連結出現與去重路徑數；目前本機 Markdown 目標已納入 10/09 全 repo 掃描，不合併成正文審核比例。

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

### 已查證、確認維持現況

- `docs/01_architecture/target_system_architecture.md` §10.11 已標示其 `CANDIDATE` 是非即時狀態摘要，並導向 Snapshot 與最新 QA；此處是設計背景與實作摘要，不替代目前狀態，保留原文。
- `docs/07_guides/V2_2_WEEKLY_REVIEW_RUNBOOK.md` 是仍被 Guide README 與 Manual 引用的操作流程，不應因日期較早便搬入 Archive。它曾把 7/12 較早的 `0/3` readiness 快照放在安全條款內；已加上與較晚 Week 1 `1/3` QA 的時間界線，並把 10/04 `pending_human_review` 標成 sidecar collection 狀態，不折算為人工 history。最新人工週數未從舊文件推定。
- 舊 `EVIDENCE_SCHEDULED_MORNING_CHECK.md` 只檢查四個較早的 scheduled task，與目前 21-task 共用稽核流程重疊且範圍過時；全文保存在 Archive，舊路徑留導引，中央 Index、Manual、Project Navigation 與 Guide README 改連目前 Runbook。`EVIDENCE_REHEARSAL_RUNBOOK.md` 則描述隔離 working-copy 的工程演練，與日常排程稽核職責不同，並有 QA closeout 直接指向，保留為現行專項操作指南。
- `docs/00_core/LEGACY_ROADMAP_CARRYOVER.md` 的 fixed／quantile Gate 與 `docs/06_qa/WALK_FORWARD_COMPARISON_REPORT.md` 已明確限定為 10 檔、單一策略及固定成本組合的 OOS pilot；這與完整股票池仍有後續實證需求並存，不可將 pilot 推廣為全市場驗收。Legacy Carryover 已補上 pilot 範圍界線。

### 已查證並於 Coverage History Entry 176 完成第二輪修正

- `docs/00_core/AI_CONTEXT_PACK.md` 已直連封存原文；Archive README 原有封存清單入口保留。
- Graphify recorded interpreter 可載入 `graphifyy 0.9.11`；`graphify --version` 的 uv trampoline 啟動器失敗，`uv tool list` 因本機工具鎖檔權限不足失敗。受控本機 API 以固定 HEAD `217115f2` 的 Git blobs 建出導覽圖：1,475 份 Markdown／文字文件、1,069 個 Python 檔，35,299 個節點、102,233 條邊、990 個 communities。manifest SHA-256 為 `e92d4b74e4f4d8f9180bdc317e6d35e0830190d5fadeb83a063e5349b1583f75`；語義抽取停用、token 0、未傳出網路。跨 chunk import 未 reconcile，8,116 條無法解析端點的 AST 邊已列入診斷並從最終圖過濾。完整新圖只保存在 ignored `output/qa/baldr_documentation_reorganization_20261009/graphify_runs/system_graph/`；原 `graphify-out` metadata 前後一致（7,000 files、26 directories、645,610,308 bytes、metadata SHA 相同），未覆寫。
- Codex 與 Antigravity 的根目錄指令現列出完整條件式必讀文件；Agent README、Antigravity 入口與 handoff template 改為遵循各自根目錄清單。`multi_agent_workflow.md` 已依 `dev` 主線與 shared context 更新，並保存舊版原文快照供追溯。

### 已核實並於 Coverage History Entry 177 完成時間標示修正

- `docs/01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md` 原結尾把 2026-09-24 設計交付時的「下一個安全接手點」留在長青設計文件，容易被讀成目前待辦。已明確標示該節及接手點屬歷史時點；目標設計內容與現況／驗收判斷未改，仍以 Snapshot 與最新具名證據為準。

### 已核實並於 Coverage History Entry 178 補齊 Superpowers 導引

- `docs/superpowers/` 的 96 個歷史相容 stub 都能連回對應 Archive 原文；其中 6 個此前缺少直達 Scoped SSOT 的入口，現已補上 Snapshot 及相符的 QA／產品方向／架構導覽。這只更新舊路徑入口，不修改封存原文或舊驗收結論。覆蓋由 90/96 提升為 96/96。

## 後續整理順序與完成定義

1. 先完成本矩陣列出的逐檔內容衝突核對；每批只改核實過的乾淨文件，保留另一 agent 的工作樹變更。
2. 每次搬移、改名或改入口時，同步更新對應目錄 README／主題索引、中央 Index（若入口或權威邊界受影響）與 [Coverage History](../09_archive/DOC_COVERAGE_HISTORY_2026.md)。
3. QA 與 Archive 從入口可達、正文已讀、狀態與證據仍有效四方面分開統計；不把舊 QA 快照重寫成新結論。
4. 固定基線的連結／錨點掃描與受控 Graphify 建置只作為歷史導覽基線；它們不代表本次內容治理完成，也不涵蓋後續提交的變更。待所有目錄的文件分類、正文衝突／過時檢查與修訂批次完成後，才執行並驗證最終 repo-wide 連結／錨點掃描及 Graphify 刷新。

**狀態：** 目錄角色與可追溯審閱基線已建立；Entry 171 修正 4 組明確內容漂移，Entry 172 更新排程文件覆核並校正圖表指南，Entry 173 校正 Recommendation ML 與 Allocation Gate 7 的證據連結，Entry 174 校正 V2.2 weekly review 文件的狀態時點，Entry 175 封存舊 morning-check 指南，Entry 176 建立固定 HEAD 的入口、Agent workflow、連結／錨點與 Graphify 導覽基線，Entry 177 標明目標架構交付查核的歷史時點，Entry 178 補齊六個 Superpowers stub 的 Scoped SSOT 入口。P8 候選已撤回；尚未核讀文件的逐篇正文審查與 Archive 清冊一對一覆蓋仍未完成。Graphify 最終刷新與目前 HEAD 的 repo-wide 連結／錨點驗證均待所有目錄內容治理與修訂完成後執行。現有 Graphify CLI 啟動器仍故障；固定基線新建的 AST／明示 Markdown link 導覽圖保存在 ignored QA 輸出，未做語義抽取且跨 chunk import 未 reconcile。舊 `graphify-out` 保持原狀。
