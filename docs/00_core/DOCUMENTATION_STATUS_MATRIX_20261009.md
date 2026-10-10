# 文件整理狀態矩陣（2026-10-09）

> 本矩陣記錄一次可追溯的全目錄盤點基線，不宣稱所有文件已完成逐篇內容審閱。分類、正文核讀、入口連結與待修候選分開計數；目錄可達不等於內容正確。當前狀態與主題權威仍依 [Scoped SSOT 覆蓋地圖](DOC_COVERAGE_MAP.md) 判讀。

## 盤點基線與範圍

- 初始審閱基線：`9b8e0ea45294d89cd08c5185478f0b8c51e0f54e`（2026-10-09），當時有 **1,473** 個已追蹤 `docs/` 路徑。
- 文件 commit `217115f2` 的目錄角色表共 **1,478** 個已追蹤路徑；相較 `9b8e0ea4` 初始基線增加 5 個：本矩陣、排程修正 QA、共用排程稽核 Runbook、封存的 morning-check 原文副本與 Agent workflow 歷史快照。本次逐目錄角色分類與 QA／Archive 計數固定在 HEAD `47a2e15e`；本批文件修訂 commit `21881d97` 沒有新增或移除路徑，目前 `docs/` tracked paths 仍為 1,478。舊 morning-check 路徑保留短導引，不另增加該路徑數；其他本機未追蹤檔不計入。後續平行開發 commits `45d138b7`、`963b04ea` 的內容未納入原固定正文審閱或圖譜基線。
- 此處範圍只含 Git 追蹤的 `docs/` 路徑；由 `git_exclusions.md` 排除的本機／ignored 狀態檔（例如 `docs/agents/shared_state/`）不計入，亦不作為文件完整性或現況證據。
- 2026-10-10 另盤點 repository 中 `docs/` 外的 26 個 Git 追蹤 Markdown；它們維持獨立附錄計數，不加進 `docs/` 的 1,478 路徑統計。長篇文件的抽查與逐篇全文審查仍分開記錄。
- 使用者已確認 `e6f79063` 的排程修正可納入本次文檔整理。已完整閱讀 `BALDR_SCHEDULE_REMEDIATION_20261009.md` 與 `BALDR_SCHEDULED_AUDIT_RUNBOOK.md`，並核對 QA README、Index、Snapshot、Manual、Guides README 及排程操作指南中的相關段落與互相連結。原基線時 F03 follow-up 有未提交變更，故該批未覆寫；後續已提交 QA 增量 `577210b1` 本輪只作摘要核對並同步 Snapshot／QA index。再次發現的 F03 QA／程式未提交變更仍排除於本批，不覆寫、不納入目前接受狀態。
- 分類是目錄層級角色盤點，不等於逐檔正文核實。內容審閱深度只計入可由審閱記錄明確證實的路徑或數量；未留下深度記錄者標為「不可還原」，不推定已讀或未讀。
- QA／Archive 舊有正文核讀數據，是先前 `0c9f84bb` 基線的歷史下限；其他目錄的分類與連結抽取多依 `9b8e0ea4` 初始基線。本表另列本輪分類基線的追蹤路徑數及其後 `21881d97` 的路徑計數複核，以及本次可具名追溯的補充閱讀；舊連結抽取結果不冒充全庫最新驗證。

## 各目錄角色盤點

以下「目錄總數」是各列互斥角色欄位的加總。「權威／工作規範」指限定主題範圍的權威文件，不代表全域操作權威；例如 `02_features/` 的功能行為參考與專題指南仍不取代完整 Manual。支援／導覽、QA 葉節點等較寬分類只表示主要用途，不替代逐檔內容審核。

| 目錄 | 追蹤路徑 | 權威／工作規範 | 導覽／支援 | 指南／計畫 | QA／證據 | 混合 | 歷史／轉址 | 資產／模板 | 備註 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `docs/` 根目錄 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 專案文件入口 README。 |
| `00_core/` | 18 | 8 | 5 | 0 | 0 | 0 | 5 | 0 | 原 17 份核心文件的逐檔核讀深度不可還原；本矩陣為新增並全文檢視的支援文件。 |
| `01_architecture/` | 224 | 10 | 5 | 36 | 141 | 2 | 30 | 0 | 目標架構套件含 139 份日期化實作／審查／checkpoint 證據；另 30 份才列為歷史／轉址。17 份文件的舊核讀深度不可還原。 |
| `02_features/` | 9 | 5 | 1 | 0 | 0 | 0 | 3 | 0 | 功能權威與入口文件居多。 |
| `03_data/` | 17 | 3 | 1 | 0 | 4 | 0 | 8 | 1 | 另有一份月營收可得性 CSV 欄位模板，不是實際公告日期資料。 |
| `04_broker_branch/` | 6 | 1 | 1 | 0 | 0 | 0 | 4 | 0 | 主要為歷史指南／快照。 |
| `05_phases/` | 15 | 0 | 2 | 0 | 0 | 0 | 13 | 0 | 13 份舊 Phase 轉址頁；轉址頁仍需保留舊入口。 |
| `06_qa/` | 564 | 0 | 6 | 0 | 491 | 0 | 67 | 0 | 5 份主索引及 1 份子目錄 README；67 份符合精確三行 Archive redirect 規則；其餘 QA／證據尚未逐篇語義分類，含 11 個非 Markdown 路徑。 |
| `07_guides/` | 20 | 4 | 1 | 8 | 0 | 2 | 5 | 0 | Manual、安裝／速查、專項 Runbook 與歷史導引並存；18 份全文、Manual 與 Supplements 局部核讀。 |
| `08_technical/` | 7 | 2 | 1 | 0 | 0 | 0 | 4 | 0 | 含一份已做全文核對的圖表渲染文件。 |
| `09_archive/` | 406 | 0 | 8 | 0 | 0 | 0 | 398 | 0 | 8 份導覽／來源清冊，其餘為歷史文件與附屬資產；共含 399 個 Markdown 路徑。 |
| `agents/` | 21 | 11 | 9 | 0 | 0 | 0 | 1 | 0 | 工作流程權威、角色入口與歷史相容文件。 |
| `strategies/` | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 兩份使用者策略說明依其 README 為非權威參考；策略規格與程式登錄才是權威。 |
| `superpowers/` | 167 | 0 | 97 | 1 | 0 | 0 | 69 | 0 | 96 份舊路徑轉址加 README，共 97 導覽項；1 份目前 task plan；69 份保留歷史原文。 |
| **合計** | **1,478** | **44** | **139** | **47** | **497** | **4** | **746** | **1** | 角色分類依 HEAD `47a2e15e`；路徑數在後續 `21881d97` 複核仍為 1,478。 |

## 正文核讀覆蓋

| 範圍 | 可證實的核讀狀況 | 尚未確認／限制 |
|---|---|---|
| `00_core/`（18） | 本輪已逐檔核對 18 份：11 份全文閱讀、7 份局部核讀；每份的角色、生命週期、核讀深度與衝突判讀見下方逐檔表。 | 既有 2026-10-09 審閱的歷史深度只可從舊記錄還原部分路徑；本輪表格另列實際閱讀範圍，不把段落抽查算成全文閱讀。 |
| `01_architecture/` + `07_guides/`（244） | `01_architecture/`：24 份具名段落核讀、202 份索引／README／標題層級分類、17 份深度不可還原；`07_guides/`：18 份全文閱讀、Manual 與 Supplements 2 份局部核讀。另核對 Manual、Guide README 與排程操作指南的 e6 相關段落及連結。封存 morning-check 原文只計入 Archive，不重複計入這 244 份。 | 目前對 244 份 Markdown 的本機連結掃描為 1,370 個連結、missing=0、bad anchors=0；架構長篇、Manual 全文、任務規格與歷史報告仍未逐篇全文覆核。 |
| 根 `docs/README.md`、`02_features/`、`03_data/`、`04_broker_branch/`、`05_phases/`、`08_technical/`（55） | 可具名證實 21 份全文核讀：02_features 6、03_data 8、04_broker_branch 2、05_phases 2、08_technical 3；另有 32 個 Archive 相容 stub 依導引核對。`docs/03_data/` 的月營收 CSV 是欄位模板，不是實際公告日期資料。 | `docs/README.md` 僅按入口／目錄導覽核對；stub 核對不計作原文全文閱讀。六份 README 抽出 109 次 Markdown 連結、82 個正規化唯一本機目的地；本輪 01／07 的 244 文件連結掃描另有明確存在性與錨點結果，兩種檢查不可混為一談。 |
| `agents/`、`strategies/`、`superpowers/`（191） | `agents/` 有 20 份現行文件及 1 份封存文件：4 份規範／索引全文、數份角色文件全文或局部核對，其餘只掃狀態宣稱；`strategies/` 3/3 全文；`superpowers/` 全目錄 167 路徑分類、96 個舊路徑 stub 的 136 個 Archive 連結逐一核對，README 與 8 份代表文件作全文／重點核讀。 | 抽讀數不代表其餘歷史原文已全文閱讀；`agents/` 的逐檔狀態與實際覆核深度見下方表格。Superpowers manifest 原有 7 列生命週期標記未跟上 10/09 已完成的搬移，本輪已修正；一份舊 QA 路線計畫加上歷史快照警語。 |
| `06_qa/`、`09_archive/`（970） | 舊基線 `0c9f84bb` 有明確記錄下限：全文 10 份（QA 5、Archive 5），局部核讀至少 2 份 QA；本次再全文閱讀排程修正 QA 1 份、封存 morning-check 原文 1 份與 Agent workflow 舊版 1 份，故可具名全文閱讀至少 13 份（QA 6、Archive 7）。2026-10-10 另局部核對 F03 最新 QA 摘要及現況導覽。 | 舊有 7 份正文主張曾被核對但範圍不明，另有 7 份只檢視導覽／來源。這不是整個 QA／Archive 的最新全面覆核；F03 長篇正文未逐節全文審閱。 |

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

### `02_features/` 逐檔角色與本輪核讀

| 文件 | 角色／生命週期 | 本輪核讀與判讀 |
|---|---|---|
| `README.md` | 目錄導覽；Application Manual 才是操作權威。 | 全文；分類邊界清楚。 |
| `BACKTEST_LAB_FEATURES.md` | Backtest Lab 功能與回放契約參考。 | 全文；執行假設與組合指標有明示。未完成清單所稱「與推薦分析整合」範圍仍含糊，保留為待釐清，不推定與已存在的推薦回放互相矛盾。 |
| `SCORE_EXPLANATION.md` | 評分規則／結果解釋參考。 | 全文；未發現和本輪核對的 Scoped SSOT 明確衝突。 |
| `STRATEGY_DESIGN_SPECIFICATION.md` | 策略設計參考，不取代 Registry／程式契約。 | 全文；舊 Promote 門檻與按鈕流程已標示為 2026-01-02 歷史快照，導回現行文件。 |
| `UI_FEATURES_DOCUMENTATION.md` | UI 行為參考，不是操作或即時狀態權威。 | 全文；更新整理日期至 2026-10-07、刪除重複窄版敘述，將無來源 `3/3 ready` 改為動態 projection 說明，並將 Gate 4 文字改成驗收範圍而非即時狀態。 |
| `USER_GUIDE.md` | 推薦／回測／資料治理的進階教學，不是操作權威。 | 全文；移除無研究依據的預期回撤數值，校正風險分數分級，移除未見程式實作的 p-value 判讀，標示舊推薦送回測流程，改用 `DATA_ROOT`，撤掉固定 37 分點與舊節流／重試保證。 |
| `BACKTEST_LAB_CHECKLIST.md` | Archive 歷史原文的相容導引。 | 只核對導向，不把 stub 當正文核讀。 |
| `BACKTEST_LAB_FAQ.md` | Archive 歷史原文的相容導引。 | 只核對導向，不把 stub 當正文核讀。 |
| `RESEARCH_RUN_REGISTRY_SPEC.md` | 2026-06-14 歷史 schema／API 提案的相容導引。 | 只核對導向；目前契約改看功能文件、架構、Manual 及 service／repository。 |

### `agents/` 與 `strategies/` 逐檔角色及核讀狀態

`agents/` 有 20 份現行協作文件及 1 份封存 Cursor 定義；本輪各文件狀態如下。全文閱讀、局部核對與狀態宣稱掃描分開記錄，不以角色摘要代替全文閱讀。

| 文件 | 角色／生命週期 | 本輪核讀與判讀 |
|---|---|---|
| `README.md` | Agent 總入口與工作規範。 | 全文；10/09 P0 速記改為 10 檔 pilot 範圍，較廣狀態導回 Snapshot。 |
| `skills_registry.md` | 角色選擇與協作導覽。 | 全文；不是第二份產品狀態權威。 |
| `shared_context.md` | Agent 共用規範／限制。 | 全文；新增現有 Sharpe／Sortino／Monte Carlo 範圍說明。CSV／Parquet 摘要較簡化，因缺少可追溯的具體儲存契約，本輪列低信心候選而未改。 |
| `git_exclusions.md` | 本機輸出排除及 stage 安全規範。 | 全文；提交前已核對，未更動。 |
| `data_audit_agent.md` | 資料稽核角色操作規範。 | 局部核對狀態宣稱；`--force-all` 已標退役。 |
| `data_cleanup_agent.md` | 資料清理角色操作規範。 | 掃描狀態宣稱；未發現與資料根保護規範衝突。 |
| `documentation_agent.md` | 文檔同步角色規範。 | 局部核讀；Roadmap Hub 檢查項已移除短版 Next 要求。 |
| `execution_agent.md` | 受控執行角色規範。 | 局部核對 SSOT 指向；未發現衝突。 |
| `tech_lead.md` | 技術決策角色與 prompt 範本。 | 局部核讀；改正 Cursor／Codex 自動讀取範圍描述。 |
| `testing_qa_agent.md` | QA 路由／驗證角色規範。 | 掃描狀態宣稱；以 Snapshot 作現況入口。 |
| `multi_agent_workflow.md` | 協作流程。 | 掃描狀態宣稱；未發現產品狀態衝突。 |
| `skills/team.md` | 協作方式補充指引。 | 掃描狀態宣稱；未發現產品狀態衝突。 |
| `skills/quant_defense_guard.md` | 量化未來函數防線。 | 全文；T-1 限制比根 AGENTS 的一般「決策當下可取得」規則更嚴，屬 guard 範圍，不是產品衝突。 |
| `antigravity/README.md` | Antigravity 角色導覽。 | 全文；定位清楚。 |
| `antigravity/data_audit_agent.md` | Antigravity 資料稽核角色規範。 | 全文；路徑／DB 安全界線相容。 |
| `antigravity/data_cleanup_agent.md` | Antigravity 清理角色規範。 | 全文；原始資料保護邊界清楚。 |
| `antigravity/documentation_agent.md` | Antigravity 文件同步角色規範。 | 全文；指向 Scoped SSOT。 |
| `antigravity/execution_agent.md` | Antigravity 執行角色規範。 | 全文；未發現狀態衝突。 |
| `antigravity/handoff_template.md` | Antigravity 交接模板。 | 全文；與根目錄規範相容。 |
| `antigravity/tech_lead_agent.md` | Antigravity 技術總管角色規範。 | 全文；相對月份不冒充日曆／完成狀態。 |
| `archive/CURSOR_SKILLS_DEFINITIONS.md` | 舊 Cursor skills 歷史原文。 | 僅核對 Archive 角色與入口，未全文閱讀。 |

`strategies/` 的三份 tracked 文件均已全文核讀：`README.md` 是範圍導覽；`momentum_aggressive_v1.md` 與 `stable_conservative_v1.md` 是非權威策略說明。兩策略文件明示 `risk_level` 不等同實證風險，並未宣稱績效保證；衝突源是 `USER_GUIDE.md` 原有的預期回撤數值，已在該教學移除。

### `06_qa/` 與 `09_archive/` 分層盤點

| 範圍 | 追蹤路徑與互斥角色 | 導覽／來源追溯 | 核讀深度與限制 |
|---|---|---|---|
| `06_qa/`（564） | 6 份導覽：`README.md`、`DATA_ML_GOVERNANCE_QA_INDEX.md`、`INTEGRATION_QA_INDEX.md`、`OPERATIONS_TESTING_QA_INDEX.md`、`PRODUCT_UX_QA_INDEX.md`、`project_status_2026_08_14/README.md`；67 份歷史轉址；491 份其餘 QA／證據（含 11 個非 Markdown）。 | 五個主題索引連結到 201 個 QA 目的地（含索引自身）及 39 個 Archive 目的地，抽取到的目標皆存在。 | 67 的可重現規則是 Markdown 第 1 行精確為 `# Historical QA path`、文件恰為 3 行並含 `../09_archive/` 連結。另有 82 個短頁符合歷史導引標題樣式、30 個標題標示「已歸檔」；兩組可能重疊且有短摘要，不與 67 相加，也不一概視為純 stub。其餘 491 路徑按 QA／證據角色計數，不代表已逐篇全文審查。 |
| `09_archive/`（406） | 6 個子目錄群：根目錄 267、`broker_branch/` 6、`phase3_5_research/` 4、`project_status_2026_08_14/` 3、`superpowers/` 96、`target_architecture_2026_09_22/` 30；其中 399 Markdown、7 份其他資產。 | 8 個現行導覽／清冊角色為 6 份 README 加 `DOC_COVERAGE_HISTORY_2026.md`、`SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md`；各頁目的地重疊，聯集可達 406/406 tracked Archive paths。`DOCUMENTATION_REORGANIZATION_MANIFEST_20261006.md` 是另外的歷史整理／恢復記錄，不列入 8 個現行導覽角色，但連到其中 4 個 Archive paths。 | 可達性不等於一對一語義來源核實或正文審查；本輪只新增全文閱讀 morning-check 原文及 Agent workflow 舊版等具名文件，其他正文仍未逐篇覆核。QA／Archive 的兩份同 blob 文件是明文記錄的刻意 mirror：`DATA_COMPLETION_2026_09_09.md`／`_HISTORY.md`，以及 `POST_V1_EVIDENCE_PIPELINE_MULTI_DAY_DRY_RUN_RECORD.md` 的 QA 路徑／Archive 凍結副本。 |

`06_qa/` 11 個非 Markdown 路徑為：10 個 JSON（`BALDR_PAPER_AUTOMATION_UPDATE_REQUEST_20260925.json`、`BALDR_SCHEDULER_RECONCILIATION_20260925.json`、`BOUNDED_TECHNICAL_ROUTING_VERIFICATION_2026_09_21.json`、`C3_C4_RELEVANT_SUITE_DRAFT_MANIFEST_20260925.json`、`C4_FINAL_RELEVANT_SUITE_MANIFEST_20260925.json`、`C4_FINAL_UNION_RECEIPT_20260925.json`、`R027_TECHNICAL_PUBLICATION_ML_IDENTITY_EVIDENCE_20260923.json`、`R030_EXTENSIBILITY_FIXTURE_QA_MANIFEST_20260925.json`、`WAVE14_CANDIDATE_CHANGE_MANIFEST_20260926.json`、`project_status_2026_08_14/artifact.json`）及 1 個 HTML（`project_status_2026_08_14/report.html`）。這些都按 QA／證據資產計入，不作 Markdown 正文核讀統計。

### `01_architecture/` 與 `07_guides/` 分層盤點

| 範圍 | 追蹤路徑／組成 | 角色與生命週期 | 本輪核對／待辦 |
|---|---|---|---|
| `01_architecture/` 根層 | 8 份；目標架構 bundle 另有 216 份。 | 現行架構權威、導覽、任務契約、日期化證據與歷史轉址並存。 | 根 README 已揭露 `system_architecture.md` §16 混有 10/03–10/07 增量；拆分整理仍待辦。 |
| `REFACTOR_TASKS/` | 32 份：1 README + 31 task specs。 | README 覆蓋所有 31 份任務規格；任務契約不等於目前待辦清單。 | `R001.md` 建立時未提交／未追蹤狀態加上 2026-09-22 快照界線；`R028.md` 的提交前敘述改為歷史快照，指出後續 commit `d77ba23f`。 |
| `REFACTOR_REPORTS/` | 144 份：1 README、139 份日期化實作／審查／checkpoint 證據、4 個 Archive redirect stub。 | 證據與歷史導引分列；日期化證據不是目前狀態。 | README／Archive 導引可達；大多數長篇報告本輪未全文閱讀。 |
| `REFACTOR_DISPATCH/` | 19 份：1 README、2 個現存 R008 packet/prompt、16 個 Archive redirect stub。 | 現行任務輸入與封存 dispatch 分開。 | Dispatch README 僅列目前 R008 packet 並提供歷史索引。 |
| 目標架構直接文件／FINAL 草案 | bundle 21 個直接文件中有 6 個 FINAL 替代草案相容 stub；另 32 個 task index/spec 已列上方。 | 目標設計權威與替代草案歷史導引並存。 | 六個草案 stub 可由入口抵達；未把它們當成目前設計權威。 |
| `07_guides/` | 20 份文件，逐檔分類見下表；含現行操作權威、入門／速查、開發指南、受限操作 Runbook 及歷史導引。 | Guide README 導航目前操作權威；兩個舊路徑 stub 保留相容入口。 | 18 份全文閱讀；Manual 局部核對安裝、資料位置、每日更新、觀察清單與回測入口，Supplements 僅核對前言、章節日期及歷史定位。四項已核實的速查、安裝、CLI 標示與重複文字問題已修正，詳見 Entry 182。 |

01／07 合計 244 份 Markdown 的 link scan 為 1,370 個連結、0 個 missing local target、0 個 bad anchor。這只證明當次掃描到的本機連結可達，不代表 244 份正文均已審核。

### `07_guides/` 逐檔分類與核讀

| 文件 | 角色／生命週期 | 本輪核讀與判讀 |
|---|---|---|
| `README.md` | 目錄導覽 | 全文；入口與角色分類清楚。 |
| `APPLICATION_MANUAL.md` | 現行操作權威 | 局部；核對安裝、資料根、每日更新、觀察清單及回測入口；已同步新使用者安裝方式並釐清正式資料根預設值。 |
| `APPLICATION_MANUAL_SUPPLEMENTS.md` | 歷史補充附冊 | 局部；核對前言、日期與歷史定位，未全文審查。 |
| `INSTALL_GUIDE.md` | 新使用者安裝與安全操作指南 | 全文；Windows x64／Python 3.11、runtime requirements、constraints、使用者自有空資料根及保護原始資料界線明確。 |
| `QUICK_START.md` | 上手流程 | 全文；安裝基線與資料根要求和 INSTALL_GUIDE 一致。 |
| `QUICK_REFERENCE.md` | 日常操作速查 | 全文；修正觀察清單可直接送 Research Lab 批次回測的入口說明。 |
| `scripts_readme.md` | 開發／維修腳本參考 | 全文；將「推薦」限縮為 CLI 替代入口，明示日常 UI／操作指南入口及執行前核對解析後的 `DATA_ROOT`／`OUTPUT_ROOT`。 |
| `tests_readme.md` | 測試入口與方法導覽 | 全文；定位為測試操作索引。 |
| `BALDR_SCHEDULED_AUDIT_RUNBOOK.md` | 受限排程稽核 Runbook | 全文；含工作範圍與唯讀界線。 |
| `EVIDENCE_REHEARSAL_RUNBOOK.md` | 隔離 working-copy 工程演練 Runbook | 全文；不與日常排程稽核混為一談。 |
| `HISTORICAL_ML_SHADOW_RUNBOOK.md` | 歷史 ML shadow 專項 Runbook | 全文；標示歷史證據與現行狀態界線。 |
| `ML_SHADOW_INFERENCE_OPERATIONS_RUNBOOK.md` | ML shadow inference 操作 Runbook | 全文；入口與操作界線清楚。 |
| `P0_DAILY_SOURCE_CANDIDATE_RUNBOOK.md` | P0 日更來源 candidate Runbook | 全文；candidate／正式來源界線清楚。 |
| `PHASE3C_CANDIDATE_REPAIR_RUNBOOK.md` | Phase 3C candidate repair Runbook | 全文；維持候選資料修復範圍。 |
| `PIT_HISTORICAL_DATA_REPAIR_RUNBOOK.md` | PIT 歷史資料修復 Runbook | 全文；保留歷史資料修復與正式資料界線。 |
| `PORTABLE_WINDOWS.md` | Windows 可攜交付操作指南 | 全文；去除兩段逐字重複的日誌位置說明與 verify_same_version 操作。 |
| `SCHEDULE_OPERATIONS_AND_MIGRATION.md` | 排程操作與遷移 Runbook | 全文；導回排程權威與安全界線。 |
| `V2_2_WEEKLY_REVIEW_RUNBOOK.md` | V2.2 每週 Review Runbook | 全文；保留週期性操作方法，舊 readiness 時點已在原段落標明。 |
| `EVIDENCE_SCHEDULED_MORNING_CHECK.md` | 已封存舊排程晨間檢查的相容導引 | 全文（短導引）；引至現行共用排程稽核入口。 |
| `LUNA_PARALLEL_PLAN_2026_09_07.md` | 已封存平行工作計畫的相容導引 | 全文（短導引）；現況依 Snapshot 與現行協作規範。 |

### `03_data/`、`04_broker_branch/`、`05_phases/`、`08_technical/` 逐檔角色

下表列出四個小型目錄的全部 tracked 文件。標為 Archive stub 的文件只核對了舊路徑與封存目的地，不表示全文已閱讀；CSV 是欄位模板，並非資料內容。

| 目錄 | 全文核讀／現行角色 | 歷史導引或 stub（僅核對導向） | 其他／本輪判讀 |
|---|---|---|---|
| `03_data/`（17 路徑） | `README.md`（導覽）、`STORAGE_ASSET_REGISTER_20261006.md`（日期化資產證據）、`C_DRIVE_QA_COLD_ARCHIVE_20261009.md`、`C_DRIVE_QA_COLD_ARCHIVE_BATCH2_20261009.md`（封存收據）、`HISTORICAL_TEST_QUARANTINE_20261006.md`（未執行計畫）、`HOW_TO_UPDATE_DAILY_DATA.md`（操作導覽）、`daily_data_update_guide.md`（含明示的舊 CLI 教學）、`DATA_FETCHING_LOGIC.md`（取得流程參考）。 | `BACKUP_RETENTION_AUDIT_2026_07_06.md`、`DATA_FLOW_LOGIC.md`、`DATA_REBUILD_GUIDE.md`、`FUNDAMENTAL_SOURCE_INVENTORY.md`、`INDUSTRY_INDEX_UPDATE_SUMMARY.md`、`MERGE_AND_MARKET_INDEX_SUMMARY.md`、`SQLITE_STORAGE_GUIDE.md`、`TROUBLESHOOTING_DAILY_UPDATE.md`。 | `templates/monthly_revenue_availability.csv` 是欄位模板。正文修訂已移除動態 37 分點數，並將腳本改列為實作位置而非日常操作推薦。 |
| `04_broker_branch/`（6） | `README.md`（安全導覽）、`BROKER_BRANCH_TESTING_AND_TROUBLESHOOTING.md`（停止執行通知與安全導覽）。 | `BROKER_BRANCH_DATA_MODULE_DESIGN_V2.md`、`BROKER_BRANCH_ERROR_DETECTION_IMPROVEMENT.md`、`BROKER_BRANCH_IMPLEMENTATION_SUMMARY.md`、`BROKER_BRANCH_PARSING_IMPROVEMENT.md`。 | 四份歷史內容只保留相容入口；README 提醒舊腳本可能連網或寫入正式 `DATA_ROOT`。 |
| `05_phases/`（15） | `README.md`（歷史／現況入口導覽）、`phase3_5_research/README.md`（歷史索引）。 | `EPIC2_MVP2_ARCHITECTURE_DESIGN.md`、`EPIC2_MVP2_IMPLEMENTATION_CHECKLIST.md`、`PHASE2_5_COMPLETION_STATUS.md`、`PHASE2_ARCHITECTURE.md`、`PHASE2_STRATEGY_LIBRARY.md`、`PHASE3_3B_RESEARCH_DESIGN.md`、`PHASE4_PORTFOLIO_DESIGN.md`、`PHASE4_STARTUP_SUMMARY.md`、`PHASE_2A_DATA_SOURCES_AUDIT.md`、`phase3_5_research/BENCHMARK_PRESENTATION.md`、`phase3_5_research/METRIC_INTERPRETATION_PRIORITY.md`、`phase3_5_research/PHASE4_ENTRY_CRITERIA.md`、`phase3_5_research/RESEARCH_ITERATION_PLAYBOOK.md`。 | 13 個舊階段文件是 redirect／Archive stub；README 明示舊 MVP 與現行 Gate 4 的差別。 |
| `08_technical/`（7） | `README.md`（技術導覽）、`RUN_WITHOUT_VENV.md`（受限環境補充指引）、`UI_QT_CHART_RENDERING.md`（圖表渲染主題參考）。 | `MCP_YFINANCE_OPENMARKETS_PATCH_MEMO.md`、`PARAMETER_DESIGN_IMPROVEMENTS.md`、`path_isolation_update.md`、`technical_analysis_optimizations.md`。 | 4 份舊技術筆記保留 Archive stub；全文閱讀的圖表文件已移除無基準測量支持的效能主張，並標出測量限制。 |

## 入口與本機連結檢查

- **2026-10-09 全 repo Markdown 掃描（固定基線，非最終覆核）：** Git tree `217115f2` 有 1,485 份 Markdown（`docs/` 1,459、`docs/` 外 26）。機器掃描排除另一 Agent 的 F03 follow-up 後，實際輸入為 1,484 份（`docs/` 1,458、`docs/` 外 26）。舊報告把掃描分區誤記為 `docs/` 1,468、其他 16；總輸入 1,484 正確。掃描只以本次整理工作樹中的 Graph Guide、Status Matrix、Coverage History 三份文件覆蓋固定基線內容，沒有包含 `217115f2` 之後其他文件的修改，因此結果不能代表目前 HEAD 的連結／錨點狀態。解析 9,432 個連結目標，其中 8,904 個一般本機目標、482 個外部連結及 532 個含錨點目標；缺少的本機目標 0、超出文件樹目標 0、未匹配錨點 0。GitHub `#L206` 行號錨點也依 576 行目標文件確認在範圍內。這是路徑與錨點檢查，不驗證外部網站或正文內容。完整本機結果位於忽略輸出的 `output/qa/baldr_documentation_reorganization_20261009/full_repo_documentation_link_anchor_check.json`。
- **Architecture + Guides：** 初始基線抽取 1,323 個 Markdown 本機連結（1,265 個相對連結、58 個 Windows `file://` 連結）；1,317 個指向基線追蹤目標，6 個未命中 Git 追蹤目標且都指向被忽略的 `output/qa/` 收據。e6 新增 Runbook 的 Index／Guide／Manual 入口已逐項核對；固定基線掃描補上當時的本機目標與錨點檢查，舊基線數字仍只代表固定快照。
- **QA：** 舊基線 `0c9f84bb` 的 5 份主索引，依 Markdown 本機連結解析並去重後，連到 246 個本機 Markdown 目的地，其中 200 個屬 `06_qa/`；排除 5 個主索引頁後，QA 葉節點目的地為 195 個。基準 `217115f2` 的相同口徑為 248 個本機 Markdown、201 個 QA 目的地、排除索引後 196 個 QA 葉節點。這些是歷史直接入口比例，不是全文審核比例，也不含其他 QA 文件間的轉介。舊基線的「32 個歷史 stub」口徑已無法重現，不再作目前 stub 總數；截至 HEAD `47a2e15e`，精確三行 redirect 規則找到 67 份，其餘 82 個歷史標題樣式及 30 個「已歸檔」標題標記可能重疊，保留在 QA／證據類直到另作語義分類。e6 的排程 QA 現由 QA README、中央 Index、Snapshot 與 Manual 連入；不將該新增頁面追寫為初始基線的本地 QA 索引覆蓋數。
- **Archive：** 初始基線的 README／清冊曾核對 404 個追蹤路徑；截至 HEAD `47a2e15e`，6 個 Archive README 與 2 份現行追蹤清冊的本機連結聯集可達 406/406 個 tracked paths。另有一份歷史整理／恢復 manifest 連到 4 個 Archive paths，不列入現行導航角色。入口可達仍不代表一對一來源語義已核實或正文均已審閱。
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

### 2026-10-10 已核實並完成修正（Coverage History Entry 182）

- `07_guides/` 的 20 個 tracked 文件已逐檔分類；18 份全文核讀、`APPLICATION_MANUAL.md` 與 `APPLICATION_MANUAL_SUPPLEMENTS.md` 局部核讀。核實並修正四項：QUICK_REFERENCE 對 Watchlist → Research Lab 回測入口的錯誤說明；Manual 與新使用者 Python 3.11／runtime constraints 安裝流程及個人空資料根的落差；腳本索引把 CLI 替代入口寫成日常優先推薦的語氣；`PORTABLE_WINDOWS.md` 的兩處重複段落。
- `docs/superpowers/` 全目錄 167 路徑的角色數與 README 分類一致：96 個舊路徑 stub、69 份保留原路徑的歷史原文，以及 1 個目前 task plan 和 README；96 個 stub 的 136 個 Archive 連結都有效。Archive manifest 有 167 列、165 個唯一歷史來源，Scheduler Approval plan/spec 各有一列重複登錄。另修正 SQLite pagination、Post-V1 evidence importer、V1.1 Decision Workflow 及 V2.2 simulated-phase 的 7 個 manifest 列，明確標成舊路徑 stub → Archive 原文。未全文審閱 69 份歷史原文。
- `2026-06-23-testing-qa-agent-super-healthcheck-roadmap.md` 保留原路線內容，檔首新增日期化歷史快照警語，界定舊「目前完成度」、test count 與可複製接手 prompt 不代表現況或執行授權，並導回目前 Snapshot／QA／Agent 文件。

## Repository tracked Markdown outside `docs/`

本附錄將 repo 根目錄及其他工作目錄下的 Markdown 納入文件治理範圍，與上方 `docs/` 目錄角色表分開計數。共 26 個 tracked paths；此表是角色盤點與本輪重點段落審核，不宣稱每份長篇文件均已全文核讀。

| 角色群 | 數量 | 路徑 | 本輪核讀範圍／判讀 |
|---|---:|---|---|
| 平台／專案指令 | 2 | `AGENTS.md`、`GEMINI.md` | 根目錄權威入口；遵循指令並核對文件工作規範，未把專案指令算成產品現況文件。 |
| Antigravity 規則 | 4 | `.agent/rules/00_project_entry.md`、`10_development_execution.md`、`20_documentation_sync.md`、`30_git_safety.md` | 00 entry 優先清單已全文核對並改回 Scoped SSOT；其餘三份列為工作規範，正文未逐篇全文審閱。 |
| 專案入口／導覽／盤點 | 4 | `AGENT_CONTEXT.md`、`README.md`、`PROJECT_NAVIGATION.md`、`PROJECT_INVENTORY.md` | 導覽角色已分類；`PROJECT_NAVIGATION.md` Daily Decision Desk roadmap 指向已修正；Inventory 的 9 個 UI workspace 清單與程式核對。其餘內容未作全文審閱。 |
| 外部資料研究報告 | 4 | `EXTERNAL_DATA_SOURCE_GAP_AUDIT.md`、`GEMINI_EXTERNAL_DATA_AUDIT_REVIEW.md`、`MOPS_PIT_FEASIBILITY_CODEX_REVIEW_PACKET.md`、`MOPS_PIT_FEASIBILITY_PROTOTYPE_REPORT.md` | Gap Audit summary、registry、candidate matrix、P0/P1 與 verdict 已按獨立 review 修正；MOPS 報告補上本機 scratch evidence 不可攜限制。未重新取得或重跑 scratch 原始證據。 |
| 模組／工具指南 | 5 | `app_module/README.md`、`examples/README.md`、`mcp_servers/README.md`、`runtime/README.md`、`scripts/scheduled/README.md` | `app_module` 的 Month 6.1 清單已移除並導回 Snapshot/Roadmap。其他目錄依用途分類；`scripts/scheduled/README.md` 約 1,370 行，本輪僅抽查／局部檢視，不計全文核讀。 |
| 歷史 notebook 程式匯出 | 2 | `notebooks/01_stock_data_collector.md`、`notebooks/02_technical_calculator.md` | 屬舊程式／輸出示例，含 2025-04 輸出與硬編碼資料根；已補歷史示例及執行前核對路徑警語，不把它們當目前 API 或操作手冊。 |
| 測試與 fixture provenance 指南 | 3 | `tests/manual/README.md`、`tests/fixtures/p0_official_sources/README.md`、`tests/fixtures/security_lifecycle/README.md` | 依其目錄功能列作測試／來源 provenance 導覽；僅作角色及相關段落抽查，未逐份全文審閱。 |
| UI 指南 | 2 | `ui_app/README.md`、`ui_qt/README.md` | `ui_qt/README.md` workspace 清單已對齊 `WORKSPACE_DEFINITIONS` 的 9 個入口，並說明 Daily Decision Desk 唯一位置；完成／backlog 不再另列未出現在 Roadmap 的 Month 6.1。`ui_app` 作 legacy UI 導覽，未全文審閱。 |
| **合計** | **26** |  | 與 `docs/` 的 1,478 個 tracked paths 分開計數。 |

### 本批已修正的 repo 外文件衝突

- `.agent/rules/00_project_entry.md` 的固定優先事項清單已撤換為 Snapshot／Roadmap 導向，避免把舊 Strategy & Scoring、文件治理及 Phase 5 項目誤認成目前狀態。
- `app_module/README.md`、`ui_qt/README.md` 的 Month 6.1 及 lifecycle backlog 語句已移除，工程待辦改由 Snapshot 與相對 Gate Roadmap 統一提供。
- `PROJECT_NAVIGATION.md` 原將 Daily Decision Desk 指向 Month 4，已改為現在實例位置及 Gate 1／2 後續工作入口。
- `ui_qt/README.md` 原列 8 個且混淆「市場觀察／每日決策」的頂層工作區；已依程式定義列出 9 個，補上「個股研究」。
- `EXTERNAL_DATA_SOURCE_GAP_AUDIT.md` 原稱 institutional/credit formal table 空白、ezSearch 可解 OOS、免費資料可完整補歷史、自然成熟可解釋 outcome；已分別修正為有列數但 freshness/governance 未證、PIT 僅 bounded 候選、全歷史免費覆蓋未證、M11 pending 原因未逐筆拆解。
- MOPS 可行性報告引用的本機 `scratch/` 檔案不是 repo 內證據；兩份報告已明示此可攜性限制。Notebook 的舊資料根也新增歷史示例警語。

### 審閱限制

26 份已全部納入路徑清冊及主要角色分類；本輪不是 26 份全文內容審查。長篇排程 README、兩份 notebook、外部 MOPS 報告與其他測試／模組說明仍有未讀全文區段；local `scratch/` 證據未取得。未覆核項目不推定為正確或過時，後續依查詢風險與實際使用範圍優先補讀。

## 後續整理順序與完成定義

1. 先完成本矩陣列出的 `docs/` 與 `docs/` 外逐檔內容衝突核對；每批只改核實過的乾淨文件，保留其他工作的工作樹變更。
2. 每次搬移、改名或改入口時，同步更新對應目錄 README／主題索引、中央 Index（若入口或權威邊界受影響）與 [Coverage History](../09_archive/DOC_COVERAGE_HISTORY_2026.md)。
3. QA 與 Archive 從入口可達、正文已讀、狀態與證據仍有效四方面分開統計；不把舊 QA 快照重寫成新結論。
4. 固定基線的連結／錨點掃描與受控 Graphify 建置只作為歷史導覽基線；它們不代表本次內容治理完成，也不涵蓋後續提交的變更。待所有目錄的文件分類、正文衝突／過時檢查與修訂批次完成後，才執行並驗證最終 repo-wide 連結／錨點掃描及 Graphify 刷新。

**狀態：** Entry 171–178 的既有整理及其歷史範圍見 [Coverage History](../09_archive/DOC_COVERAGE_HISTORY_2026.md)。Entry 179 校正固定基線計數與導覽口徑，Entry 180 完成 Core 18 份逐檔分類，Entry 181 補登 Feature／Data／Agent／Architecture 修正及 QA／Archive 分層盤點。`docs/` 目前有 1,478 個 tracked paths；小型目錄已列全檔路徑，Core、02_features、agents、strategies 逐檔列出；大型 Architecture、QA、Archive 與 Superpowers 依索引、清冊及分層計數記錄。這是分類與抽樣覆核基線，不代表所有正文已逐篇核實。P8 候選已撤回；仍有長篇任務／歷史證據、QA 葉節點、Archive 原文與 Superpowers 原文未全文閱讀，Archive 可達性也不等於逐筆語義來源核對。Graphify 最終刷新與目前 HEAD 的 repo-wide 連結／錨點驗證均待所有目錄內容治理與修訂完成後執行。現有 Graphify CLI 啟動器仍故障；固定基線新建的 AST／明示 Markdown link 導覽圖保存在 ignored QA 輸出，未做語義抽取且跨 chunk import 未 reconcile。舊 `graphify-out` 保持原狀。

**2026-10-10 增量：** Coverage History Entry 182 已登錄 Guides 20 份逐檔分類（18 全文、2 局部）、四項內容修正，以及 Superpowers 7 筆 Archive manifest 生命週期欄位修正與一份舊計畫的歷史定位標示。這些批次未刪除或移動文件；未跑測試、未刷新 Graphify。F03 follow-up 與根目錄 `$null` 仍保持未納入本批。

**2026-10-10 第二增量：** Coverage History Entry 183 已登錄 `docs/` 外 26 個 Markdown 的角色清冊與本批狀態修正，並補校目標架構分冊／DAG 將 9/22 設計時狀態誤當現況、R028 accepted slice 未同步、MOPS scratch 證據可攜性、舊 notebook 資料根及 UI workspace 清單。此次只核對具名矛盾與相關段落；全庫長篇正文仍有未讀區段。未刪除原始資料；未跑測試或刷新 Graphify。

**2026-10-10 第三增量：** Coverage History Entry 184 已登錄截至 commit `577210b1` 的 F03 bounded QA Snapshot／QA Index 同步。首輪 15 passed／2 個測試環境失敗；修正後僅重跑兩個節點並通過，未宣稱修正後全套重跑。另有新的未提交 F03 QA／程式變更未納入、未覆寫；產品 query、UI、收藏與跨程序閉環仍未完成。未跑測試或刷新 Graphify。
