# 文件整理狀態矩陣（基線 2026-10-09；持續補充至 2026-10-11）

> 本矩陣記錄一次可追溯的全目錄盤點基線，不宣稱所有文件已完成逐篇內容審閱。分類、正文核讀、入口連結與待修候選分開計數；目錄可達不等於內容正確。當前狀態與主題權威仍依 [Scoped SSOT 覆蓋地圖](DOC_COVERAGE_MAP.md) 判讀。

## 盤點基線與範圍

- 初始審閱基線：`9b8e0ea45294d89cd08c5185478f0b8c51e0f54e`（2026-10-09），當時有 **1,473** 個已追蹤 `docs/` 路徑。
- 目錄角色分類的原固定基線為 HEAD `47a2e15e`，共有 **1,478** 個已追蹤 `docs/` 路徑；相較初始 `9b8e0ea4` 增加的 5 個路徑見既有基線記錄。依目前 Git index 重算，`docs/` 有 **1,487** 個 tracked paths（1,468 Markdown、19 非 Markdown）；本輪發現舊表少列 1 個 `06_qa/` 路徑，已按路徑 metadata 更正數量。原分類基線保留作歷史比較；正文核讀、QA 路由及狀態修正另見 Coverage History。
- 此處範圍只含 Git 追蹤的 `docs/` 路徑；由 `git_exclusions.md` 排除的本機／ignored 狀態檔（例如 `docs/agents/shared_state/`）不計入，亦不作為文件完整性或現況證據。repository 中 `docs/` 外目前有 26 個 Git 追蹤 Markdown，維持獨立附錄計數，不加進 `docs/` 的 1,487 路徑統計。長篇文件的抽查與逐篇全文審查仍分開記錄。
- 使用者已確認 `e6f79063` 的排程修正可納入本次文檔整理。已完整閱讀 `BALDR_SCHEDULE_REMEDIATION_20261009.md` 與 `BALDR_SCHEDULED_AUDIT_RUNBOOK.md`，並核對 QA README、Index、Snapshot、Manual、Guides README 及排程操作指南中的相關段落與互相連結。Entry 184 當時只依已提交 QA 增量 `577210b1` 同步 F03 摘要；其後 commit `8945df89` 加入 F06 呈現層與回歸測試證據，本輪據此更新 Snapshot／QA index。盤點時 F03 QA 文件在共享工作樹有未提交修改；本輪未讀寫該文件或其差異，也未納入接受狀態或提交。
- 分類是目錄層級角色盤點，不等於逐檔正文核實。內容審閱深度只計入可由審閱記錄明確證實的路徑或數量；未留下深度記錄者標為「不可還原」，不推定已讀或未讀。
- QA／Archive 舊有正文核讀數據，是先前 `0c9f84bb` 基線的歷史下限；其他目錄的角色分類仍依固定分類基線。本表另列以 `53b13fa4` 核對的路徑數、各輪可具名追溯的補充閱讀與目前可重算的 QA／Archive 路由；舊 repo-wide 連結抽取仍是歷史基線，不冒充目前 HEAD 的最終驗證。

## 各目錄角色盤點

以下「目錄總數」是各列互斥角色欄位的加總。「權威／工作規範」指限定主題範圍的權威文件，不代表全域操作權威；例如 `02_features/` 的功能行為參考與專題指南仍不取代完整 Manual。支援／導覽、非索引 QA 目的頁等較寬分類只表示主要用途，不替代逐檔內容審核。

| 目錄 | 追蹤路徑 | 權威／工作規範 | 導覽／支援 | 指南／計畫 | QA／證據 | 混合 | 歷史／轉址 | 資產／模板 | 備註 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `docs/` 根目錄 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 專案文件入口 README。 |
| `00_core/` | 18 | 8 | 5 | 0 | 0 | 0 | 5 | 0 | 原 17 份核心文件的逐檔核讀深度不可還原；本矩陣為新增並全文檢視的支援文件。 |
| `01_architecture/` | 224 | 10 | 5 | 36 | 141 | 2 | 30 | 0 | 目標架構套件含 139 份日期化實作／審查／checkpoint 證據；另 30 份才列為歷史／轉址。17 份文件的舊核讀深度不可還原。 |
| `02_features/` | 9 | 5 | 1 | 0 | 0 | 0 | 3 | 0 | 功能權威與入口文件居多。 |
| `03_data/` | 17 | 3 | 1 | 0 | 4 | 0 | 8 | 1 | 另有一份月營收可得性 CSV 欄位模板，不是實際公告日期資料。 |
| `04_broker_branch/` | 6 | 1 | 1 | 0 | 0 | 0 | 4 | 0 | 主要為歷史指南／快照。 |
| `05_phases/` | 15 | 0 | 2 | 0 | 0 | 0 | 13 | 0 | 13 份舊 Phase 轉址頁；轉址頁仍需保留舊入口。 |
| `06_qa/` | 572 | 0 | 6 | 1 | 374 | 0 | 180 | 11 | 6 個 QA 導覽入口、1 份待真人驗收計畫、374 份其他非 stub 內容 Markdown（其中 1 份使用者進行中的文件只按 Git 路徑計入，未讀正文或連結）、180 份歷史相容 redirect，以及 11 個非 Markdown 路徑；入口可達不代表正文均已核讀。 |
| `07_guides/` | 20 | 4 | 1 | 8 | 0 | 2 | 5 | 0 | Manual、安裝／速查、專項 Runbook 與歷史導引並存；18 份全文、Manual 與 Supplements 局部核讀。 |
| `08_technical/` | 7 | 2 | 1 | 0 | 0 | 0 | 4 | 0 | 含一份已做全文核對的圖表渲染文件。 |
| `09_archive/` | 407 | 0 | 8 | 0 | 0 | 0 | 399 | 0 | 8 份導覽／來源清冊，其餘為歷史文件與附屬資產；共含 400 個 Markdown 路徑。 |
| `agents/` | 21 | 11 | 9 | 0 | 0 | 0 | 1 | 0 | 工作流程權威、角色入口與歷史相容文件。 |
| `strategies/` | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 兩份使用者策略說明依其 README 為非權威參考；策略規格與程式登錄才是權威。 |
| `superpowers/` | 167 | 0 | 97 | 1 | 0 | 0 | 69 | 0 | 96 份舊路徑轉址加 README，共 97 導覽項；1 份目前 task plan；69 份保留歷史原文。 |
| **合計** | **1,487** | **44** | **139** | **48** | **519** | **4** | **721** | **12** | 原角色分類基線為 HEAD `47a2e15e` 的 1,478 paths；現行差異及 QA 分類更正見 Coverage History Entry 215、216 與 223。 |

## 正文核讀覆蓋

| 範圍 | 可證實的核讀狀況 | 尚未確認／限制 |
|---|---|---|
| `00_core/`（18） | 18/18 份已全文閱讀；前三輪標為局部的 `DOC_COVERAGE_MAP.md`、`EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` 與本矩陣已在本輪完成全文複核。 | 全文閱讀只證明已逐篇核讀，不代表文件內引用的外部狀態已重新取得；Blueprint 外部 repo 與來源接受狀態仍未重新查核。 |
| `01_architecture/` + `07_guides/`（244） | `01_architecture/` 224 份的可重算舊基線為 82 全文、23 局部、119 未讀（根層 8 全文；target bundle 21 全文；REFACTOR_TASKS 32 全文；REFACTOR_REPORTS 2 全文／23 局部／119 未讀；DISPATCH 19 全文）。`07_guides/`：18 份全文、Manual 與 Supplements 2 份局部核讀；另核對 Manual、Guide README 與排程操作指南的相關段落及連結。封存 morning-check 原文只計入 Archive，不重複計入這 244 份。 | 01／07 共 244 份 Markdown 的舊連結掃描為 1,370 個連結、missing=0、bad anchors=0；此為歷史掃描。REFACTOR_REPORTS 另按 144 paths 分成索引 1、相容 redirect 4、日期化實作／審查／決策證據 139。此前對 18 份高風險直開文件做局部核讀並加上時點／狀態提示；本批又從舊未讀清單全文核讀 74 份報告。由於早前 C1／R001–R007 批次未留下逐檔清冊，無法確認與新批次的交集，故 82／23／119 與 2／23／119 僅保留為已記錄基線，不據此推算目前總數或剩餘篇數。另修正 R029 的歷史提交狀態句、將 R026 的 9/25 checkpoint 明確限定為 snapshot；system architecture §16 的 10/10 複合研究入口已核實穩定責任落在 §§3、8，現況仍看 Snapshot；手冊 §14 後 1,358 行日期化記錄已封存，104 個舊標題仍保留轉址，但搬移不等於逐項重新驗證全文。 |
| 根 `docs/README.md`、`02_features/`、`03_data/`、`04_broker_branch/`、`05_phases/`、`08_technical/`（55） | 22 份非 stub Markdown 已全文核讀：根目錄 README 1、02_features 6、03_data 8、04_broker_branch 2、05_phases 2、08_technical 3；另完整閱讀 `03_data/` 月營收 CSV 欄位範本。02_features 的 9/9、04_broker_branch 的 6/6、05_phases 的 15/15、08_technical 的 7/7 tracked paths 均已閱讀或逐路徑核對；各目錄 Archive redirect stub 只代表導向已核對，不等於原文全文閱讀。 | `docs/03_data/` 月營收 CSV 是欄位範本，不是實際公告日期資料。六份 README 抽出 109 次 Markdown 連結、82 個正規化唯一本機目的地；本輪 01／07 的 244 文件連結掃描仍是歷史基線，不代表目前 HEAD 全量通過。 |
| `agents/`、`strategies/`、`superpowers/`（191） | `agents/` 21/21 全文、`strategies/` 3/3 全文；`superpowers/` 全目錄 167 路徑分類、96 個舊路徑 stub 的 136 個 Archive 連結逐一核對，README 與 8 份代表文件作全文／重點核讀；另抽查 5 份保留授權／worker 指令的計畫與 handoff 原件並加歷史警語。 | Superpowers 的代表性核讀不代表 69 份歷史原文均已全文閱讀。Entry 185 記錄 Antigravity 文件 Agent 的 Coverage Pass 摘要與權威規則不一致，已更正；另限定 execution Agent 的 Git 回滾範例，避免覆蓋他人未提交變更。External Validation Register 的歷史性已在 README 明確標出，當前狀態導回 Snapshot／近期 QA。|
| `06_qa/`、`09_archive/`（979） | 舊基線 `0c9f84bb` 有明確記錄下限：全文 10 份（QA 5、Archive 5），局部核讀至少 2 份 QA；Entry 181–184 另有具名全文或局部閱讀。本輪完整閱讀 QA README 與四個主題索引，並檢查六份此前無路由 QA 收據的標題／範圍；不把開頭確認算成全文審讀。 | QA README 加四份主題索引的 357 targets 為舊 link scan 基線；此前矩陣記錄的 README 遞迴可達 553/553 是有界遍歷的歷史結果，但解析規則未充分留存，尚無法重現為全域完整可達率。QA-only 資料夾內 BFS 為 318/553，下限不含跨資料夾連結、reference-style／HTML 等解析，不能取代全域掃描。五個主要入口 current bounded link parse 為 201/556 個根層證據路徑；此分母與 553 個安全 Markdown 不同。另遍歷 400 個 Archive Markdown。Archive README 對 267/267 根層非索引路徑有直達連結，另有 43/43 個非 Superpowers 巢狀路徑受 README 導覽；總體可達 407/407 個 tracked Archive paths。Archive root 共有 263 份 Markdown，最新閱讀快照為 57 份全文、206 份待讀；`APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md` 僅讀至第 120 行，仍列待讀。舊 6,231 links／anchors 為歷史基線，不代表目前 HEAD 全量通過。 | 本輪排除一個共享工作樹 QA 檔案的正文與連結，只納入 Git 路徑 metadata；安全內容範圍仍為 564 paths（553 Markdown、10 JSON、1 HTML），另有 1 個受保護路徑只按 Git metadata 計數。553 是內容頁分母，不含六個索引與一份真人驗收計畫。QA 舊快照 205 份全文、4 份局部、344 份未讀（合計 553）是未具名舊基線，不得與本輪具名增量相加；QA／Archive 仍持續審閱。67 個精確三行歷史轉址仍計入 Markdown 路由分母。2026-10-10 唯讀 inventory audit 掃到 `tests/` 下 1,463 個 filesystem `.py` paths（Git index 1,461，另有 2 個 filesystem-only paths）、registry 1,303 筆、未登錄 160、stale 0；未做 pytest collection。P0 register §7 的 DEV-66 limited 決議與 §14 的 `limited=0` machine 總數仍有未調和差異，不能將後者外推為目前全域狀態。 |

全體文件沒有一個可支持「已逐篇讀完」的比例。上述數字只表達可追溯的審閱證據；正文審閱數、入口連結覆蓋及分類完成度是不同指標，不能互相代替。e6 排程 QA 與 Runbook 已納入補充閱讀；全 repo 最終 link／anchor 掃描與 Graphify 刷新仍待所有目錄內容審核及修訂完成後進行。

### `09_archive/` 巢狀目錄核讀補充

| 範圍 | 可證實核讀狀況 | 判讀與處理 |
|---|---|---|
| `09_archive/` 直屬 Markdown（263） | 57 份全文、206 份待讀；`APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md` 僅讀至第 120 行，仍列待讀。 | Archive 直屬原件尚未讀完。 |
| `09_archive/target_architecture_2026_09_22/`（30） | 30/30 全文；其中 18 份過時 dispatch／review prompt／checkpoint 已加直開歷史警語。 | 舊 SHA、Git 授權與 Wave 狀態屬歷史；警語保留原驗收／計畫正文，現況回到 Snapshot、Model Assignments 與具名後續 checkpoint。 |
| `09_archive/broker_branch/`、`phase3_5_research/`、`project_status_2026_08_14/`（13 paths） | 11 份 Markdown 全文、1 份 JSON 全文、1 份 HTML 靜態 body 核對。 | Archive README 增加 Phase 3.5 歷史索引；broker README 標出舊刪 CSV 建議、`c=E` URL 與未重驗腳本／步驟風險。Phase 3.5 固定門檻不代表目前 Gate；專案狀態報告保留 8/14 快照範圍。 |
| `09_archive/superpowers/`（96） | 96/96 全文：65 份 plan、30 份 spec、1 份 prompt。 | 已確認其 manifest 與大部分狀態導覽相符；9 份含可重送 prompt、舊 Git 授權或 rollback／`--apply` 操作的文件已加上直開警語。原始封存 bytes／SHA 保留作來源核對，manifest 附記另列目前版本雜湊；Superpowers README 的最後整理日已校正為 2026-10-10。 |

上述巢狀路徑合計 139 個 tracked paths（137 Markdown、2 個非 Markdown）；加上直屬 268 paths（263 Markdown），對應 `09_archive/` 共 407 tracked paths／400 Markdown。巢狀目錄核讀不代表直屬 206 份待讀原件已完成審查。

### `00_core/` 逐檔分類與本輪核讀

| 文件 | 角色／生命週期 | 本輪核讀深度與判讀 |
|---|---|---|
| `AI_CONTEXT_PACK.md` | 歷史相容入口；原文已封存，現況轉看 Snapshot。 | 全文；不作目前狀態權威。 |
| `DEVELOPMENT_ROADMAP.md` | 現行 Roadmap Hub，負責導覽權威文件，不保存目前進度。 | 全文；與 Snapshot／6M Roadmap 職責相符。 |
| `DOCUMENTATION_CATALOG_20261006.md` | 日期化歷史目錄快照入口，不是即時清冊。 | 全文；日期與歷史定位明確。 |
| `DOCUMENTATION_GRAPH_GUIDE.md` | 現行 Graphify 導覽與維護指南，不是內容／驗收權威。 | 全文；固定基線、CLI 故障與抽取限制有標示。 |
| `DOCUMENTATION_INDEX.md` | 現行文件位置與導航權威，不是狀態權威。 | 全文；定位及主要 Core／Guide 導覽已核對。 |
| `DOCUMENTATION_STATUS_MATRIX_20261009.md` | 日期化整理基線與覆核紀錄，不取代 Scoped SSOT。 | 全文；分開標示角色分類、正文閱讀、導覽可達與內容覆核限制。 |
| `DOCUMENTATION_STRUCTURE.md` | 現行文件生命週期、目錄歸屬及歸檔規則。 | 全文；與 Index／Archive 導覽及生命週期分類相符。 |
| `DOC_COVERAGE_MAP.md` | 現行跨文件 Scoped SSOT、同步矩陣與 DoD 權威。 | 全文；修正中央 Index 與領域 README／主題索引要求互相矛盾，並把 Blueprint 限定為候選來源研究細節。 |
| `EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` | 外部專案與候選資料源研究 companion，不是現況、來源優先序或交付順序權威。 | 全文；區分 2026-07-11 研究基線與 2026-08-14 具名來源審查，現行來源優先序導回 Product Roadmap §11；未重新查核外部 repo／接受狀態。 |
| `LEGACY_ROADMAP_CARRYOVER.md` | 2026-06-15 歷史移交／結案記錄；目前工程順序回到 6M Roadmap，現況回到 Snapshot。 | 全文；將 fixed／quantile Gate 明確限定為 10 檔 pilot，不推定完整股票池已驗收。 |
| `NEXT_ACTION_PLAN.md` | 已封存一次性計畫的相容入口。 | 全文；明確導回現行 Snapshot／Roadmap。 |
| `PRODUCT_ROADMAP_POST_REFACTOR.md` | 現行產品方向與產品 Gate 權威，不負責目前進度。 | 全文；方向、產品 Gate 與 Snapshot／6M 權責相符，基線日期 2026-09-17 有標示。 |
| `PROJECT_SNAPSHOT.md` | 現行唯一狀態入口。 | 全文；已把 Index 從「完整文件清單」改為導覽，並分連歷史目錄快照與本矩陣。 |
| `README.md` | Core 區導航頁，不取代主題權威。 | 全文；Scoped Authority 導覽相符。 |
| `ROADMAP_6M_ENGINEERING.md` | 現行六個月工程順序、Gate 與驗收權威；進度看 Snapshot。 | 全文；相對月份、Gate 與 Snapshot 的目前進度分工一致。 |
| `V4_COMPLETION_PLAN_2026_09_07.md` | 已封存完成計畫的歷史入口。 | 全文；日期及目前狀態入口明示。 |
| `VERSION_ROADMAP_V1_1_TO_V2_0.md` | 已封存版本路線的相容入口。 | 全文；明確排除作為目前工作順序。 |
| `VERSION_ROADMAP_V2_1_TO_V4_0.md` | 現行長期 maturity 權威；工程順序看 6M、現況看 Snapshot。 | 全文；maturity 門檻與產品／工程 Roadmap 的權責分工清楚。 |

### `02_features/` 逐檔角色與本輪核讀

| 文件 | 角色／生命週期 | 本輪核讀與判讀 |
|---|---|---|
| `README.md` | 目錄導覽；Application Manual 才是操作權威。 | 全文；分類邊界清楚。 |
| `BACKTEST_LAB_FEATURES.md` | Backtest Lab 功能與回放契約參考。 | 全文；修正 sizing／市場限制仍列待辦的過時狀態；保留未單獨核實的成本模型切換項目；區分 Phase 3.5 的 10 筆 UI 前置檢查與 Registry Lifecycle 20 筆最低門檻，並限定圖表 benchmark 說明不代表 Registry readback 會回抓。未完成清單所稱「與推薦分析整合」範圍仍含糊，保留待釐清。 |
| `SCORE_EXPLANATION.md` | 評分規則／結果解釋參考。 | 全文；未發現和本輪核對的 Scoped SSOT 明確衝突。 |
| `STRATEGY_DESIGN_SPECIFICATION.md` | 策略設計參考，不取代 Registry／程式契約。 | 全文；舊 Promote 流程維持 2026-01-02 歷史快照；新增研究提案／示例不代表現行實作的界線，標明 MVP 日期與門檻及前向填充只是設計建議。 |
| `UI_FEATURES_DOCUMENTATION.md` | UI 行為參考，不是操作或即時狀態權威。 | 全文；更新整理日期至 2026-10-07、刪除重複窄版敘述，將無來源 `3/3 ready` 改為動態 projection 說明，並將 Gate 4 文字改成驗收範圍而非即時狀態。 |
| `USER_GUIDE.md` | 推薦／回測／資料治理的進階教學，不是操作權威。 | 全文；移除無研究依據的預期回撤數值，校正風險分數分級，移除未見程式實作的 p-value 判讀，標示舊推薦送回測流程，改用 `DATA_ROOT`，撤掉固定 37 分點與舊節流／重試保證；另標明「最新」優化記錄日期，補正 SQLite 優先、CSV fallback 的回測資料讀取順序。 |
| `BACKTEST_LAB_CHECKLIST.md` | Archive 歷史原文的相容導引。 | 全文核對短導引與目標位置，不把 stub 當 Archive 正文核讀。 |
| `BACKTEST_LAB_FAQ.md` | Archive 歷史原文的相容導引。 | 全文核對短導引與目標位置，不把 stub 當 Archive 正文核讀。 |
| `RESEARCH_RUN_REGISTRY_SPEC.md` | 2026-06-14 歷史 schema／API 提案的相容導引。 | 全文核對短導引與目標位置；目前契約改看功能文件、架構、Manual 及 service／repository。 |

### `agents/` 與 `strategies/` 逐檔角色及核讀狀態

`agents/` 有 20 份現行協作文件及 1 份封存 Cursor 定義；本輪各文件狀態如下。全文閱讀、局部核對與狀態宣稱掃描分開記錄，不以角色摘要代替全文閱讀。

| 文件 | 角色／生命週期 | 本輪核讀與判讀 |
|---|---|---|
| `README.md` | Agent 總入口與工作規範。 | 全文；10/09 P0 速記改為 10 檔 pilot 範圍，較廣狀態導回 Snapshot。 |
| `skills_registry.md` | 角色選擇與協作導覽。 | 全文；不是第二份產品狀態權威。 |
| `shared_context.md` | Agent 共用規範／限制。 | 全文；新增現有 Sharpe／Sortino／Monte Carlo 範圍說明。CSV／Parquet 摘要較簡化，因缺少可追溯的具體儲存契約，本輪列低信心候選而未改。 |
| `git_exclusions.md` | 本機輸出排除及 stage 安全規範。 | 全文；提交前已核對，未更動。 |
| `data_audit_agent.md` | 資料稽核角色操作規範。 | 全文；`--force-all` 已標退役，未發現與資料稽核邊界衝突。 |
| `data_cleanup_agent.md` | 資料清理角色操作規範。 | 全文；原始資料保護及需先檢查風險的界線明確。 |
| `documentation_agent.md` | 文檔同步角色規範。 | 全文；Coverage Pass／Patch Pass 順序明確，已確認 Coverage 後才改動清單內文件。 |
| `execution_agent.md` | 受控執行角色規範。 | 全文；回滾範例已補充先保存未提交差異、不得覆蓋共享工作樹中他人變更。 |
| `tech_lead.md` | 技術決策角色與 prompt 範本。 | 全文；Codex／Cursor 自動讀取範圍與根目錄入口描述已校正。 |
| `testing_qa_agent.md` | QA 路由／驗證角色規範。 | 全文；六個高頻 UI 測試路由與測試清冊相符；Manual 的九個頂層工作區是另一計數口徑。 |
| `multi_agent_workflow.md` | 協作流程。 | 全文；與 shared context 的變更保護及工作樹協作規則一致。 |
| `skills/team.md` | 協作方式補充指引。 | 全文；團隊協作規則與 shared context 相容。 |
| `skills/quant_defense_guard.md` | 量化未來函數防線。 | 全文；T-1 限制比根 AGENTS 的一般「決策當下可取得」規則更嚴，屬 guard 範圍，不是產品衝突。 |
| `antigravity/README.md` | Antigravity 角色導覽。 | 全文；定位清楚。 |
| `antigravity/data_audit_agent.md` | Antigravity 資料稽核角色規範。 | 全文；路徑／DB 安全界線相容。 |
| `antigravity/data_cleanup_agent.md` | Antigravity 清理角色規範。 | 全文；原始資料保護邊界清楚。 |
| `antigravity/documentation_agent.md` | Antigravity 文件同步角色規範。 | 全文；已移除「可略過 Coverage 確認」的例外摘要，改為遵循權威兩階段流程。 |
| `antigravity/execution_agent.md` | Antigravity 執行角色規範。 | 全文；未發現狀態衝突。 |
| `antigravity/handoff_template.md` | Antigravity 交接模板。 | 全文；與根目錄規範相容。 |
| `antigravity/tech_lead_agent.md` | Antigravity 技術總管角色規範。 | 全文；相對月份不冒充日曆／完成狀態。 |
| `archive/CURSOR_SKILLS_DEFINITIONS.md` | 舊 Cursor skills 歷史原文。 | 全文；僅作歷史紀錄，不取代現行 Codex／Antigravity 入口。 |

`strategies/` 的三份 tracked 文件均已全文核讀：`README.md` 是範圍導覽；`momentum_aggressive_v1.md` 與 `stable_conservative_v1.md` 是非權威策略說明。兩策略文件明示 `risk_level` 不等同實證風險，並未宣稱績效保證；衝突源是 `USER_GUIDE.md` 原有的預期回撤數值，已在該教學移除。本輪對齊 Documentation Agent、Antigravity 規則與策略 README 的新增文件導航要求；中央 Index 改採條件式更新。另於 Entry 185 修正 Coverage Pass 例外摘要及 rollback 保護文字。

### `06_qa/` 與 `09_archive/` 分層盤點

| 範圍 | 追蹤路徑與互斥角色 | 導覽／來源追溯 | 核讀深度與限制 |
|---|---|---|---|
| `06_qa/`（565） | 6 份導覽：`README.md`、`DATA_ML_GOVERNANCE_QA_INDEX.md`、`INTEGRATION_QA_INDEX.md`、`OPERATIONS_TESTING_QA_INDEX.md`、`PRODUCT_UX_QA_INDEX.md`、`project_status_2026_08_14/README.md`；1 份真人驗收計畫；67 份歷史轉址；491 份其餘 QA／證據（含 11 個非 Markdown）。 | 五個主要入口的 current bounded link parse 為 201/556 個安全範圍根層證據路徑；舊 200/555 結果保留為歷史基線。此前記載的 README 553/553 遞迴可達是尚未充分記錄解析規則的有界歷史結果；QA 資料夾內 BFS 318/553 僅是下限，不能推論全域可達率。本輪也為 dated test inventory snapshots、未對帳數字與 Gate projection 加註時間邊界。 | 受保護共享工作檔只計 Git 路徑 metadata，不讀其正文或連結；安全範圍為 553 Markdown、10 JSON、1 HTML。最新核讀快照為 205 全文、4 局部、344 未讀。357 個入口 Markdown link targets 是舊掃描值，未重跑 parser；上述限定入口解析不是完整 Markdown parser。201/556 與 553 Markdown 的分母口徑不同。67 個精確三行 redirect 仍計入歷史路由分母；82 個短頁與 30 個「已歸檔」標題可能重疊，不與 67 相加，也不一概視為 stub。可達不等於逐篇正文審查。 |
| `09_archive/`（407） | 6 個子目錄群：根目錄 268、`broker_branch/` 6、`phase3_5_research/` 4、`project_status_2026_08_14/` 3、`superpowers/` 96、`target_architecture_2026_09_22/` 30；其中 400 Markdown、7 份其他資產。 | 8 個現行導覽／清冊角色為 6 份 README 加 `DOC_COVERAGE_HISTORY_2026.md`、`SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md`；各頁目的地重疊，聯集可達 407/407 tracked Archive paths。Archive README 直連 267/267 根層非索引項目，另有 43/43 個非 Superpowers 巢狀項目有 README 導覽。`DOCUMENTATION_REORGANIZATION_MANIFEST_20261006.md` 是另外的歷史整理／恢復記錄，不列入 8 個現行導覽角色，但連到其中 4 個 Archive paths。 | Archive 標頭與入口複核發現 8 份原件的歷史狀態容易脫離 README 脈絡；Entry 193 已加檔首警語並修正兩個現行權威路由。既有 6,231 個 QA／Archive link／anchor 結果是歷史基線，不代表目前 HEAD。QA／Archive 的兩份同 blob 文件是明文記錄的刻意 mirror：`DATA_COMPLETION_2026_09_09.md`／`_HISTORY.md`，以及 `POST_V1_EVIDENCE_PIPELINE_MULTI_DAY_DRY_RUN_RECORD.md` 的 QA 路徑／Archive 凍結副本。 |

### `09_archive/` 根層內容初篩（審閱基線 HEAD `53b13fa4`）

- 根層有 267 個 tracked 路徑（262 Markdown、2 JSON、3 TXT，含 README）；排除 README 後為 266 個。對這 266 個非 README 路徑執行現況詞彙初篩，並對檔名未帶明顯日期／歷史標記的 38 份 Markdown 閱讀開頭 8 行；另對 9 份候選文件抽核相關區段。這是風險分流，不是 267 份原文全文審查，也未遍歷 `superpowers/` 子樹。
- 可確認的直開風險：`SOLUTION_SUMMARY.md` 把舊 `ui_app/` 寫成 UI 入口；`API_INVESTIGATION_REPORT.md` 的「今天／本週」待辦，日期要到正文較後處才出現。Archive README 已補上其歷史時點與現行入口提醒。`BACKTEST_LAB_CHECKLIST.md`、`BACKTEST_LAB_FAQ.md`、`POST_V1_EVIDENCE_SCHEDULER_APPROVAL_SOP.md` 及 Task Loop 01／02／04／05 的 Archive 導覽已明示歷史用途或不要照舊建議操作；原件與 hash 記錄保持不變。
- 以上候選代表原文直開時的時間標示風險；不等於已證實原內容曾是錯誤或目前程式／操作相反。Archive 原件屬追溯來源，本批只補導覽警語，不改寫原件。

`06_qa/` 11 個非 Markdown 路徑為：10 個 JSON（`BALDR_PAPER_AUTOMATION_UPDATE_REQUEST_20260925.json`、`BALDR_SCHEDULER_RECONCILIATION_20260925.json`、`BOUNDED_TECHNICAL_ROUTING_VERIFICATION_2026_09_21.json`、`C3_C4_RELEVANT_SUITE_DRAFT_MANIFEST_20260925.json`、`C4_FINAL_RELEVANT_SUITE_MANIFEST_20260925.json`、`C4_FINAL_UNION_RECEIPT_20260925.json`、`R027_TECHNICAL_PUBLICATION_ML_IDENTITY_EVIDENCE_20260923.json`、`R030_EXTENSIBILITY_FIXTURE_QA_MANIFEST_20260925.json`、`WAVE14_CANDIDATE_CHANGE_MANIFEST_20260926.json`、`project_status_2026_08_14/artifact.json`）及 1 個 HTML（`project_status_2026_08_14/report.html`）。這些都按 QA／證據資產計入，不作 Markdown 正文核讀統計。

### `01_architecture/` 與 `07_guides/` 分層盤點

| 範圍 | 追蹤路徑／組成 | 角色與生命週期 | 本輪核對／待辦 |
|---|---|---|---|
| `01_architecture/` 根層 | 8 份；目標架構 bundle 另有 216 份。 | 現行架構權威、導覽、任務契約、日期化證據與歷史轉址並存。 | 本輪 8/8 全文核讀。確認並修正 §16 10/03–10/07 增量及 10/08 M2 補記的導覽描述；為目標架構 Current status、UI 設計基線及 Runtime 檢查表補上現況判讀界線。 |
| `REFACTOR_TASKS/` | 32 份：1 README + 31 task specs。 | README 覆蓋所有 31 份任務規格；任務契約不等於目前待辦清單。 | 本輪 32/32 全文閱讀；`R001.md` 建立時未提交／未追蹤狀態加上 2026-09-22 快照界線；`R028.md` 的提交前敘述改為歷史快照，指出後續 commit `d77ba23f`。 |
| `REFACTOR_REPORTS/` | 144 份：1 README、139 份日期化實作／審查／checkpoint 證據、4 個 Archive redirect stub。 | 證據與歷史導引分列；日期化證據不是目前狀態。 | 本輪 README、R028 全文；R020、R026、R029、R016 及 18 份高風險直開報告／checkpoint／派工基線局部；119 份未讀。README 對 143 個同層文件均有索引連結（146 次連結引用、0 個缺失目標）；簡易時點掃描標出 78 份正文未見完整日期、88 份開頭 16 行未見清楚時點／狀態界線，這是篩選訊號，不等於逐篇語義審閱。R029、R026、本批高風險文件與 R008 result-ID bounded acceptance 均已補上時點／狀態界線。 |
| `REFACTOR_DISPATCH/` | 19 份：1 README、2 份完整舊 Gemini prompt／review 證據、16 個 Archive redirect stub。 | README 定義現行分派 gate；完整舊 prompt 是歷史證據，不能依其正文派工。 | 本輪 19/19 全文核讀；README 26 個本機 Markdown 連結目標存在（未檢查錨點）。兩份完整舊 prompt 的直接開啟警語與 README 路由已同步修訂；原 prompt 主體保留。 |
| 目標架構直接文件／FINAL 草案 | bundle 21 個直接文件中有 6 個 FINAL 替代草案相容 stub；另 32 個 task index/spec 已列上方。 | FINAL 設計權威、執行契約、日期化證據、歷史評估與相容轉址並存。 | 2026-10-10 新建逐檔基線：21/21 全文核對；舊 10/3/8 摘要沒有具名清單，不能映射原先未讀名單。發現 Wave 9 的 R027→R028 條件、Model Assignments 的 Wave 7/9/14 狀態快照與 9/27 後續接受裁定不一致，已加時點／scope overlay；System Architecture Assessment 已補直開歷史界線。 |
| `07_guides/` | 20 份文件，逐檔分類見下表；含現行操作權威、入門／速查、開發指南、受限操作 Runbook 及歷史導引。 | Guide README 導航目前操作權威；兩個舊路徑 stub 保留相容入口。 | 18 份全文閱讀；Manual 局部核對安裝、資料位置、每日更新、觀察清單與回測入口，Supplements 僅核對前言、章節日期及歷史定位。四項已核實的速查、安裝、CLI 標示與重複文字問題已修正，詳見 Entry 182。 |

01／07 合計 244 份 Markdown 的舊 link scan 為 1,370 個連結、0 個 missing local target、0 個 bad anchor。這只證明當次掃描到的本機連結可達，不代表 244 份正文均已審核；本輪未重跑該目錄全量 link scan。

### `target_architecture_2026_09_22/` 直接文件逐檔分類與核讀

| 文件 | 角色／生命週期 | 本輪核讀與判讀 |
|---|---|---|
| `README.md` | bundle 導覽 | 全文；權威分層與狀態入口清楚。 |
| `FINAL_TARGET_ARCHITECTURE.md` | 唯一目標架構設計權威 | 全文；2026-09-22 設計基線，不宣稱全域已完成。 |
| `FINAL_ARCHITECTURE_INVARIANTS.md` | 設計不變條件契約 | 全文；不當作實作完成證據。 |
| `FINAL_DATA_FLOW.md` | 目標資料流與執行模型 | 全文；與 FINAL 主文一致。 |
| `FINAL_EXTENSIBILITY_MODEL.md` | 目標擴充邊界 | 全文；未宣稱已新增產品功能。 |
| `FINAL_ML_COMPATIBILITY_CONTRACT.md` | ML 相容契約 | 全文；保留相容性與 promotion 邊界。 |
| `FINAL_MIGRATION_SEQUENCE.md` | 遷移 ledger／具名 scope 裁定 | 全文；日期化 overlay 保留原 strict 結果，9/27 revision B 與 R028 scoped acceptance 有明確記錄。 |
| `REFACTOR_IMPLEMENTATION_DAG.md` | 任務依賴與驗收契約 | 全文；規劃基線及 blocker 文字需依日期化裁定判讀。 |
| `REFACTOR_EXECUTION_ORDER.md` | Wave 順序與執行契約 | 全文；Wave 9 原 strict R027 條件加上 9/27 versioned revision overlay，未改寫原結果。 |
| `REFACTOR_MODEL_ASSIGNMENTS.md` | implementer/reviewer 分工與 Wave 狀態快照 | 全文；Wave 7/9/14 舊狀態已標日期並導向後續 migration/QA overlay。 |
| `REFACTOR_RISK_REGISTER.md` | 風險、owner 與處置 ledger | 全文；R027 strict 與 revision B、R028 scope 分開記錄。 |
| `REFACTOR_VALIDATION_MATRIX.md` | 驗證計畫 | 全文；屬計畫，不是 PASS 收據。 |
| `SYSTEM_ARCHITECTURE_ASSESSMENT.md` | 2026-09-22 歷史系統評估 | 全文；新增檔首歷史界線與現行架構／狀態路由。 |
| `ARCHITECTURE_RED_TEAM_REVIEW.md` | 歷史 review 輸入 | 全文；現有 FINAL 採納裁定路由清楚。 |
| `ARCHITECTURE_REQUIRED_CHANGES.md` | FINAL 前建議與採納索引 | 全文；明示不是現行待辦。 |
| `ARCHITECTURE_INVARIANTS.md` | 舊稿相容 redirect stub | 全文核對 stub；導向 Archive 與 FINAL。 |
| `EXTENSIBILITY_TEST.md` | 舊稿相容 redirect stub | 全文核對 stub；導向 Archive 與 FINAL。 |
| `MIGRATION_STRATEGY.md` | 舊稿相容 redirect stub | 全文核對 stub；導向 Archive 與 FINAL。 |
| `ML_COMPATIBILITY_PLAN.md` | 舊稿相容 redirect stub | 全文核對 stub；導向 Archive 與 FINAL。 |
| `TARGET_ARCHITECTURE.md` | 舊稿相容 redirect stub | 全文核對 stub；導向 Archive 與 FINAL。 |
| `TARGET_DATA_FLOW.md` | 舊稿相容 redirect stub | 全文核對 stub；導向 Archive 與 FINAL。 |

### `01_architecture/` 根層逐檔分類與核讀

| 文件 | 角色／生命週期 | 本輪核讀與判讀 |
|---|---|---|
| `README.md` | 架構目錄導覽 | 全文；修正 §16 混合增量與 10/08 M2 入口的歸檔範圍說明。 |
| `data_collection_architecture.md` | 已歸檔資料收集設計的相容導引 | 全文核對短導引；現行資料流回到 `system_architecture.md`，操作回到資料指南與 Manual。 |
| `runtime_observatory_rules.md` | Runtime 與 UI 整合治理規範／檢查表 | 全文；補充勾選不是目前實作證明，應以有日期的證據核對。 |
| `system_architecture.md` | 目前系統架構、模組邊界與資料流權威 | 全文；明示 §16 仍有 10/03–10/07 混合增量及 10/08 M2 入口，並標記其內部段落時點。 |
| `system_flow_end_to_end.md` | 已歸檔端到端流程藍圖的相容導引 | 全文核對短導引；目前流程回到 system／target architecture 與 Manual。 |
| `system_vision_specification.md` | North Star、產品原則、Evidence 與 Non-goals 權威 | 全文；2026-07-11 成功層級已明確標成歷史基線，現況導回 Snapshot。 |
| `target_system_architecture.md` | 目標領域背景與 Current→Target 導覽 | 全文；為第 10 節無一致快照日期的 `Current status` 加上判讀界線，現況回到 Snapshot／目前架構。 |
| `ui_design_system_midnight_analyst.md` | Midnight Analyst UI 設計規格 | 全文；標明第 8、11 節的完成／目前／後續敘述屬 2026-07-07 基線，現況回到 Snapshot。 |

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
| `03_data/`（17 路徑） | `README.md`（導覽）、`STORAGE_ASSET_REGISTER_20261006.md`（日期化資產證據）、`C_DRIVE_QA_COLD_ARCHIVE_20261009.md`、`C_DRIVE_QA_COLD_ARCHIVE_BATCH2_20261009.md`（封存收據）、`HISTORICAL_TEST_QUARANTINE_20261006.md`（未執行計畫）、`HOW_TO_UPDATE_DAILY_DATA.md`（操作導覽）、`daily_data_update_guide.md`（含明示的舊 CLI 教學）、`DATA_FETCHING_LOGIC.md`（取得流程參考）。 | `BACKUP_RETENTION_AUDIT_2026_07_06.md`、`DATA_FLOW_LOGIC.md`、`DATA_REBUILD_GUIDE.md`、`FUNDAMENTAL_SOURCE_INVENTORY.md`、`INDUSTRY_INDEX_UPDATE_SUMMARY.md`、`MERGE_AND_MARKET_INDEX_SUMMARY.md`、`SQLITE_STORAGE_GUIDE.md`、`TROUBLESHOOTING_DAILY_UPDATE.md`。 | `templates/monthly_revenue_availability.csv` 是欄位模板。正文修訂校正 Freshness 截止時區、列明安全更新含 TWSE／TPEX，並界定舊 CLI 的資料範圍與輸出；腳本位置不作完整 UI 流程的等價替代。 |
| `04_broker_branch/`（6） | `README.md`（安全導覽）、`BROKER_BRANCH_TESTING_AND_TROUBLESHOOTING.md`（停止執行通知與安全導覽）。 | `BROKER_BRANCH_DATA_MODULE_DESIGN_V2.md`、`BROKER_BRANCH_ERROR_DETECTION_IMPROVEMENT.md`、`BROKER_BRANCH_IMPLEMENTATION_SUMMARY.md`、`BROKER_BRANCH_PARSING_IMPROVEMENT.md`。 | 四份歷史內容只保留相容入口；README 提醒舊腳本可能連網或寫入正式 `DATA_ROOT`。 |
| `05_phases/`（15） | `README.md`（歷史／現況入口導覽）、`phase3_5_research/README.md`（歷史索引）。 | `EPIC2_MVP2_ARCHITECTURE_DESIGN.md`、`EPIC2_MVP2_IMPLEMENTATION_CHECKLIST.md`、`PHASE2_5_COMPLETION_STATUS.md`、`PHASE2_ARCHITECTURE.md`、`PHASE2_STRATEGY_LIBRARY.md`、`PHASE3_3B_RESEARCH_DESIGN.md`、`PHASE4_PORTFOLIO_DESIGN.md`、`PHASE4_STARTUP_SUMMARY.md`、`PHASE_2A_DATA_SOURCES_AUDIT.md`、`phase3_5_research/BENCHMARK_PRESENTATION.md`、`phase3_5_research/METRIC_INTERPRETATION_PRIORITY.md`、`phase3_5_research/PHASE4_ENTRY_CRITERIA.md`、`phase3_5_research/RESEARCH_ITERATION_PLAYBOOK.md`。 | 13 個舊階段文件是 redirect／Archive stub；README 明示舊 MVP 與現行 Gate 4 的差別。 |
| `08_technical/`（7） | `README.md`（技術導覽）、`RUN_WITHOUT_VENV.md`（受限環境補充指引）、`UI_QT_CHART_RENDERING.md`（圖表渲染主題參考）。 | `MCP_YFINANCE_OPENMARKETS_PATCH_MEMO.md`、`PARAMETER_DESIGN_IMPROVEMENTS.md`、`path_isolation_update.md`、`technical_analysis_optimizations.md`。 | 7/7 tracked paths 已全文閱讀或逐 stub 核對；4 份舊技術筆記保留 Archive stub。修正 Canvas 鍵盤操作僅支援淨值／回撤折線圖的描述，並將 System Python 命令改成明確日期範本及起訖範圍。 |

## 入口與本機連結檢查

- **2026-10-09 全 repo Markdown 掃描（固定基線，非最終覆核）：** Git tree `217115f2` 有 1,485 份 Markdown（`docs/` 1,459、`docs/` 外 26）。機器掃描排除另一 Agent 的 F03 follow-up 後，實際輸入為 1,484 份（`docs/` 1,458、`docs/` 外 26）。舊報告把掃描分區誤記為 `docs/` 1,468、其他 16；總輸入 1,484 正確。掃描只以本次整理工作樹中的 Graph Guide、Status Matrix、Coverage History 三份文件覆蓋固定基線內容，沒有包含 `217115f2` 之後其他文件的修改，因此結果不能代表目前 HEAD 的連結／錨點狀態。解析 9,432 個連結目標，其中 8,904 個一般本機目標、482 個外部連結及 532 個含錨點目標；缺少的本機目標 0、超出文件樹目標 0、未匹配錨點 0。GitHub `#L206` 行號錨點也依 576 行目標文件確認在範圍內。這是路徑與錨點檢查，不驗證外部網站或正文內容。完整本機結果位於忽略輸出的 `output/qa/baldr_documentation_reorganization_20261009/full_repo_documentation_link_anchor_check.json`。
- **Architecture + Guides：** 初始基線抽取 1,323 個 Markdown 本機連結（1,265 個相對連結、58 個 Windows `file://` 連結）；1,317 個指向基線追蹤目標，6 個未命中 Git 追蹤目標且都指向被忽略的 `output/qa/` 收據。e6 新增 Runbook 的 Index／Guide／Manual 入口已逐項核對；固定基線掃描補上當時的本機目標與錨點檢查，舊基線數字仍只代表固定快照。
- **QA：** 舊基線 `0c9f84bb` 的 5 份主索引，依 Markdown 本機連結解析並去重後，連到 246 個本機 Markdown 目的地，其中 200 個屬 `06_qa/`；排除 5 個主索引頁後，非索引 QA 連結目標為 195 個。基準 `217115f2` 的相同口徑為 248 個本機 Markdown、201 個 QA 目的地、排除索引後 196 個非索引 QA 連結目標。這些是歷史直接入口比例，不是全文審核比例，也不含其他 QA 文件間的轉介。舊基線的「32 個歷史 stub」口徑已無法重現，不再作目前 stub 總數；截至 HEAD `47a2e15e`，精確三行 redirect 規則找到 67 份，其餘 82 個歷史標題樣式及 30 個「已歸檔」標題標記可能重疊，保留在 QA／證據類直到另作語義分類。e6 的排程 QA 現由 QA README、中央 Index、Snapshot 與 Manual 連入；不將該新增頁面追寫為初始基線的本地 QA 索引覆蓋數。
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

### 2026-10-10 已核實並於 Coverage History Entry 186 修正

- `DOC_COVERAGE_MAP.md` 的新增／刪除文件規則曾要求每份文件都更新中央 Index，與本頁 DoD 和 `DOCUMENTATION_STRUCTURE.md` 的分層導航規則相衝突。現已統一為領域 README／主題索引逐份導覽；只有主要入口或權威邊界變更時才更新中央 Index，並同步 Codex／Antigravity 指引與策略 README。
- `EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` 曾同時列出來源優先序權威並註明 Product Roadmap 才是 post-refactor 優先序；其 7/11 研究基線也未區分 8/14 具名來源審查。現已限定為外部／候選來源研究與歷史參考，將現行優先序導回 Product Roadmap §11、工程順序導回 6M Roadmap，並明示兩個日期範圍及未重新查核的限制。
- Archive 根層初篩已在 Archive README 提醒 `SOLUTION_SUMMARY.md` 的舊 `ui_app/` 入口、`API_INVESTIGATION_REPORT.md` 的日期化待辦，以及 Backtest 歷史清單／FAQ；後續直開複核發現 `DEVELOPMENT_ROADMAP_LEGACY_2026_06.md`、三份 Architecture governance 備忘與兩份 Backtest 原件檔首仍缺時間／權威界線。本輪只在 8 份原件加歷史警語，並修正 Archive README 的 API 資料管線與 Architecture Lifecycle 導向；未重寫封存內容。

### 2026-10-10 已核實並於 Coverage History Entry 187 修正

- `02_features/` 9/9 個 tracked paths 已全文閱讀或逐路徑核對；6 份內容文件全文核讀，3 份短 redirect stub 全文核對導向。與 Manual、Snapshot 及相關回測／lifecycle 程式對照後，修正 Backtest Lab 已實作的 sizing／市場限制仍列待辦，以及 User Guide 未說明 SQLite 優先、CSV fallback 的資料來源順序。Phase 3.5 `<10` 筆 UI 前置檢查與 Registry Lifecycle 最低 20 筆 Gate 已明確分開；2026-05-27 圖表文字限定於執行時畫面，不推論 Registry readback 會重抓 benchmark。
- Strategy Design Specification 新增設計提案、前向填充建議、2023 MVP 示例和門檻不代表目前實作或驗收的界線；User Guide 將 2025-12-22 的「最新優化」改成日期化歷史記錄。成本模型切換尚未單獨驗證，保留待查；「與推薦分析整合」範圍也未臆測成已完成或已過時。
- 後續路由複核發現該規格仍將已封存的 Phase 2 redirect 描述為現行可插拔架構細節。已改標為歷史參考，現行模組邊界連到 `system_architecture.md`；Phase stub 繼續保留舊路徑相容，不刪除原文或轉址。

### 2026-10-10 REFACTOR_REPORTS 索引及 Gate 時點補充（Coverage History Entry 192）

- 原指定 `docs/01_architecture/REPORTS/` 無 tracked 文件；實際報告目錄為 `target_architecture_2026_09_22/REFACTOR_REPORTS/`，共 144 paths：1 份導覽索引、4 份相容 redirect、139 份日期化實作／審查／決策證據。索引原列 140 個同目錄目標，漏列 4 個 Wave 1／2 redirect；現已獨立列出，不把 stub 算成實質報告。
- `C1_FULL_GATE_VALIDATION_REPORT.md` 將 2026-09-23 執行時的 C1 NOT PASSED／Wave 6 BLOCKED 容易讀成目前 gate。已在標題與結論加上執行時點並連至後續 `C1_CHECKPOINT.md`；保留原 QA 測試證據及限制。修改前報告索引的 142 個相對連結目標均存在；本次另新增 4 個 redirect stub 連結，anchors 與 repo-wide links 仍待最終掃描。

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
| **合計** | **26** |  | 與 `docs/` 目前 1,486 個 tracked paths 分開計數。 |

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

**狀態：** Entry 171–206 的整理及其歷史範圍見 [Coverage History](../09_archive/DOC_COVERAGE_HISTORY_2026.md)。Entry 179 校正固定基線計數與導覽口徑，Entry 180 完成 Core 18 份逐檔分類，Entry 181 補登小型目錄與 QA／Archive 分層盤點，Entry 182–197 登錄 Guides、repo 外 Markdown、F03 單項同步、QA／Archive 路由、權威邊界修正、`02_features/` 全文覆核與歷史 Phase 引用校正、Architecture 根層及 REFACTOR_REPORTS 核讀修訂、Archive／Superpowers 原件時點提示、QA 路徑／inventory 差異與歷史清冊快照更正、圖表／技術指南範圍校正、03_data 操作流程校正、過時派送材料與 Manual 歷史內容分流及舊標題轉址。Entry 198–204 補登待真人驗收與資料契約入口、REFACTOR_REPORTS／Archive 時點提示、Dispatch 舊 Gemini prompt 導覽校正、目標架構逐檔核對與 Wave 7/9/14 scope 衝突修訂、QA 可讀範圍增量與最新核讀進度、報告／Archive 原件的後續全文核讀及歷史範圍修訂；Entry 205–206 完成 Archive 巢狀目錄核讀、歷史操作警語及原始雜湊保全。`docs/` 目前有 1,486 個 tracked paths；小型目錄已列全檔路徑，Core、agents、strategies 逐檔列出；大型 Architecture、QA、Archive 與 Superpowers 依索引、清冊及分層計數記錄。這是分類與抽樣覆核基線，不代表所有正文已逐篇核實。P8 候選已撤回；仍有長篇任務／歷史證據、非索引 QA 目的頁、Archive 原文與 Superpowers 原文未全文閱讀，Archive 可達性也不等於逐筆語義來源核對。Graphify 最終刷新與目前 HEAD 的 repo-wide 連結／錨點驗證均待所有目錄內容治理與修訂完成後執行。現有 Graphify CLI 啟動器仍故障；固定基線新建的 AST／明示 Markdown link 導覽圖保存在 ignored QA 輸出，未做語義抽取且跨 chunk import 未 reconcile。舊 `graphify-out` 保持原狀。

**2026-10-10 增量：** Coverage History Entry 182 已登錄 Guides 20 份逐檔分類（18 全文、2 局部）、四項內容修正，以及 Superpowers 7 筆 Archive manifest 生命週期欄位修正與一份舊計畫的歷史定位標示。這些批次未刪除或移動文件；未跑測試、未刷新 Graphify。F03 follow-up 與根目錄 `$null` 仍保持未納入本批。

**2026-10-10 增量：** Entry 202 新增 target architecture bundle 21 份直屬文件的逐檔分類與全文核讀基線；修訂 Wave 9 原 strict R027 prerequisite 與 9/27 revision B／R028 scoped acceptance 的時點界線，並為 9/22 Architecture Assessment 加上直開歷史提示。Dispatch 舊 Gemini prompt 導覽／授權提示與 R008 result-ID acceptance 範圍提示同步完成。未執行測試、最終 repo-wide Markdown links／anchors scan 或 Graphify 刷新。

**2026-10-10 增量：** Entry 205 核讀 `09_archive/target_architecture_2026_09_22/` 30/30 份 Markdown，以及 broker、Phase 3.5、project status 三個小目錄 13/13 tracked paths；修訂 Archive 與 broker README，並為 18 份過時架構派送／報告原件加直開警語。Entry 206 全文核讀 `09_archive/superpowers/` 96/96 份歷史原文，為 9 份有舊派送授權或操作命令的文件加警語，校正 Superpowers README 日期，且在 manifest 保留原始封存 bytes／SHA 並增列加警語後的雜湊。各批沒有刪除文件或原始資料；未跑測試、Graphify 或最終全庫 links／anchors scan。

**2026-10-10 第二增量：** Coverage History Entry 183 已登錄 `docs/` 外 26 個 Markdown 的角色清冊與本批狀態修正，並補校目標架構分冊／DAG 將 9/22 設計時狀態誤當現況、R028 accepted slice 未同步、MOPS scratch 證據可攜性、舊 notebook 資料根及 UI workspace 清單。此次只核對具名矛盾與相關段落；全庫長篇正文仍有未讀區段。未刪除原始資料；未跑測試或刷新 Graphify。

**2026-10-10 第三增量：** Coverage History Entry 184 已登錄截至 commit `577210b1` 的 F03 bounded QA Snapshot／QA Index 同步。首輪 15 passed／2 個測試環境失敗；修正後僅重跑兩個節點並通過，未宣稱修正後全套重跑。另有新的未提交 F03 QA／程式變更未納入、未覆寫；產品 query、UI、收藏與跨程序閉環仍未完成。未跑測試或刷新 Graphify。

**2026-10-10 第四增量：** Coverage History Entry 185 已登錄以 HEAD `8945df89` 核對的六份 QA 收據索引補鏈、架構 R026／R029 日期狀態更正、Agent 流程摘要及 rollback 安全文字修正，以及 QA／Archive 路由複核。QA Markdown 目前由入口遞迴可達 553/553，Archive tracked paths 可達 406/406；這些是導覽結果，不代表正文全部已讀。`01_architecture/` 本輪 224 份中有 44 全文、7 局部、173 未讀；`agents/` 21/21 與 `strategies/` 3/3 全文。未刪除或搬移檔案，未執行測試，未刷新 Graphify；共享 F03 工作樹修改及根目錄 `$null` 保持未讀未動。全 repo 最終 link／anchor scan 與 Graphify 仍待所有目錄內容審查和修訂完成。

**2026-10-10 第五增量：** Coverage History Entry 186 修正中央 Index／領域索引責任衝突，收窄外部 Blueprint 的權威與日期範圍，並補足兩份 Archive 根層原文的直開提醒。Core 18/18 文件已全文核讀；Archive 根層完成 266 路徑詞彙初篩、38 份開頭抽讀及 9 份候選區段覆核，未遍歷 Archive 原文全體或 Superpowers 子樹。未刪除或搬移文件、未改寫封存原件，未執行測試或刷新 Graphify；全 repo 最終 link／anchor scan 仍待所有目錄治理完成。

**2026-10-10 第六增量：** Coverage History Entry 187 記錄 `02_features/` 9/9 tracked paths 的全文或逐路徑核對（6 份內容文件、3 份歷史 redirect stub），並修正 sizing／市場限制 backlog、SQLite 優先的資料載入說明、Phase 3.5 與 Registry Promote 門檻界線，以及設計提案／歷史示例的時點標示。成本模型切換尚未單獨核實，保留待查。未刪除或搬移文件，未執行測試、Graphify 刷新或最終 repo-wide link／anchor scan。

**2026-10-10 第七增量：** Coverage History Entry 188 記錄 `01_architecture/` 根層 8 份文件全文核讀；該目錄總數更新為 52 全文、7 局部、165 未讀。修正 Architecture README 對 §16 歸檔範圍的描述，標出 10/06 載入畫面段及 10/08 M2 入口時點，並為目標架構 Current status、Midnight Analyst 的 7/07 狀態基線與 Runtime 勾選表補上現況判讀界線。未刪除或搬移文件及原始資料，未執行測試、Graphify 刷新或最終 repo-wide link／anchor scan。

**2026-10-10 第八增量：** Coverage History Entry 189 記錄 `docs/08_technical/` 7/7 個 tracked paths 與根 `docs/README.md` 全文核讀；確認 75 個相對連結目標可達。修正回測 Canvas 鍵盤瀏覽範圍（僅淨值／回撤折線圖）、System Python 範本明確指定起訖日期，以及效能基準聲明的本文範圍。全庫小型目錄摘要改列 22 份非 stub Markdown 全文核讀、CSV 欄位範本全文核對，另分列已核對導向的 stub。未執行測試、Graphify 刷新或最終 repo-wide link／anchor scan。

**2026-10-10 第九增量：** Coverage History Entry 190 記錄 `docs/03_data/` 17/17 個 tracked paths 的閱讀深度（8 份 Markdown 正文、1 份 CSV 範本全文；8 個 Archive stub 只核對轉址），及 114 個本機連結目標均存在。修正 Freshness 截止為 04:30 America/Los_Angeles、UI 安全更新的 TWSE／TPEX 日檔步驟與 TWSE CSV 段落範圍，並將舊 CLI 的市場覆蓋、彙整輸出與 SQLite 同步限制寫清楚。未刪除或搬移文件及原始資料；未執行測試、Graphify 刷新或最終 repo-wide link／anchor scan。

**2026-10-10 第十增量：** Coverage History Entry 191 校正 `STRATEGY_DESIGN_SPECIFICATION.md` 將已封存 Phase 2 文件稱為現行架構細節的引用，改導向現行 `system_architecture.md` 及清楚標示歷史的封存原文；`05_phases/README.md` 同步說明舊路徑仍保留相容轉址。未刪除或搬移文件、未跑測試、未刷新 Graphify 或執行最終 repo-wide link／anchor scan。

**2026-10-10 第十一增量：** Coverage History Entry 193 為 8 份 Archive 原件補上歷史時點／權威警語，修正 Archive README 對資料管線及 Architecture Lifecycle 的 current authority 路由；原始封存正文未重寫。

**2026-10-10 第十二增量：** Coverage History Entry 194 更新 Superpowers 對 External Validation Register 的歷史定位，補列 T86 原始計畫，並為 5 份保留 worker／授權語句的 plan/handoff 加上非現行授權提示。仍有 69 份歷史原文未全文讀取。

**2026-10-10 第十三增量：** Coverage History Entry 195 將 QA 的 10/06 inventory 數字明確標為歷史快照，解釋 1284→1303 的同日版本差異；10/10 唯讀 inventory audit 發現 filesystem 1,463、registry 1,303、未登錄 160、stale 0。另將 9/5 Forward Clock projection 限定為日期快照，補入 8/30 Formal readiness archive link。未執行測試收集，未刷新 Graphify 或進行最終 repo-wide link／anchor scan。

**2026-10-10 補記（Coverage History Entry 192）：** 記錄 Architecture REFACTOR_REPORTS 144 paths 的角色分類、索引補列 4 個相容 redirect stub，以及將 C1 Full Gate QA 的 2026-09-23 not-passed／blocked 文案限定為當時執行快照並導向後續 checkpoint。未改動測試證據或歷史裁決；未跑測試、未刷新 Graphify 或執行最終 repo-wide link／anchor scan。

**2026-10-10 第十四增量：** Coverage History Entry 196 更新 Index 的日期與 M2 QA 時點說明；將 system architecture §16 的 10/10 複合研究段導回 §§3、8 與 Snapshot；修正 Dispatch 中已過時的 Gemini 派送流程，並替 R008 歷史 prompt／packet 與紅隊審查加上直開界線。另在 P0 register 保留並標示 DEV-66 與 8/28 machine audit 的未調和數字；quick guides 的 Promote／資料來源文字有窄幅校正。未刪除或搬移文件、未執行測試、Graphify 刷新或最終 repo-wide link／anchor scan。

**2026-10-10 第十五增量：** Coverage History Entry 197 將 Manual 第 14 節後 1,358 行日期化開發／候選快照移入 Archive，原文 bytes／SHA 已記錄；Manual 保留 104 個同名標題導引，並更新指南與 Archive 導覽。角色盤點路徑增為 1,479；也修正角色表合計欄，使 QA／證據與歷史／轉址的總數符合逐目錄互斥分類。未逐項重驗歷史內容，未執行測試、Graphify 刷新或最終 repo-wide link／anchor scan。

**2026-10-10 第十六增量：** Coverage History Entry 198 為 10/10 複合研究待真人驗收收據補上 QA README 與 Product/UX 索引入口；並在 Superpowers 主題表補列 Wave 1／2A、Terra V0 與舊自動化提案，原 plan/spec 及其 manifest 雜湊未改。P0 Register 的 DEV-66 limited 決議與 8/28 machine audit limited=0 差異仍待底層 registry 調和。QA／Archive 與 Architecture 大量證據原文仍未逐篇全文閱讀；未執行測試、Graphify 刷新或最終 repo-wide link／anchor scan。

**2026-10-10 第十七增量：** Coverage History Entry 199 將 Manual 的 TWSE no-data 分類條件對齊程式與資料指南，並為舊 system-Python 排錯段、CSV mapping 範本列及回歸基準策略標出界線；Architecture §8 的 2026-06 資料筆數改列歷史快照。小型資料／指南目錄完成逐篇或逐路徑核對，未把文件內記載的冷封存／quarantine 主張視為重新驗證證據。未執行測試、Graphify 刷新或最終 repo-wide link／anchor scan。

<a id="named-review-batches-20261010"></a>
## 2026-10-10 新增具名核讀清單（Entry 207–208）

以下清單逐檔記錄本輪新增的完整閱讀證據，方便後續按路徑去重。由於先前 QA 與 Archive 彙總批次未保存完整逐檔 manifest，這些清單**不直接加進既有全文／未讀累計**；舊總數維持原值，待可重建的路徑基線後再調整。

### `docs/09_archive/` 根層：本批全文核讀 20 份

| 路徑 | 角色／處理 |
|---|---|
| `DATA_REBUILD_GUIDE_HISTORY.md` | 舊全量重建操作；已加現行操作入口與不可直接執行提示。 |
| `DATA_UPDATE_DISPLAY_REFRESH_2026_08_30.md` | 日期化 QA 快照；既有檔首已限定時點。 |
| `EVIDENCE_REHEARSAL_ENGINEERING_CLOSEOUT_2026_07_14.md` | 工程演練收尾證據；保留原範圍。 |
| `EVIDENCE_REHEARSAL_REAL_E2E_CLOSEOUT_2026_07_13.md` | E2E 工程驗收證據；保留原範圍。 |
| `FORMAL_DATA_RECONCILIATION_2026_08_06.md` | 正式資料對帳日期快照；不推論現況。 |
| `FULL_APP_HEALTHCHECK_AGENT_CLOSEOUT_2026_06_23.md` | 舊 QA 工具鏈收束；已加測試數字／命令的時點界線。 |
| `GATE_1_ADVICE_CLOSEOUT_2026_07_12.md` | Bounded Advice Contract closeout；已限定驗收範圍。 |
| `GATE_2_TO_7_PURE_ENGINEERING_CLOSEOUT_2026_07_12.md` | 純工程收尾證據；原文已有工程／產品 Gate 範圍界線。 |
| `GEMINI_DOCUMENTATION_CROSS_AUDIT_ADJUDICATION_2026_07_13.md` | 歷史文件裁決；已將 `Snapshot=current` 限定為當時快照。 |
| `HISTORICAL_ML_SHADOW_MVP_CLOSEOUT_2026_07_15.md` | ML shadow 驗收快照；保留既有日期與限制。 |
| `LUNA_B_ENVIRONMENT_2026_09_07.md` | 舊環境／套件版本快照；已連回 requirements 與安裝指南。 |
| `LUNA_PROMPT_A_DATA_ML_2026_09_07.md` | 舊工作提示與授權；已標示不可重送。 |
| `LUNA_PROMPT_B_ARCHITECTURE_2026_09_07.md` | 舊工作提示與授權；已標示不可重送。 |
| `LUNA_PROMPT_C_UX_2026_09_07.md` | 舊工作提示與授權；已標示不可重送。 |
| `OWNER_PRODUCTION_READINESS_2026_08_06.md` | Owner readiness 日期快照；保留原範圍。 |
| `P0_LICENSE_EVIDENCE_CAPTURE_2026_08_28.md` | 授權條款 probe 證據；保留原結論與日期。 |
| `P0_MOPS_OWNER_PACKET_REFRESH_2026_08_28.md` | 候選與 owner handoff 快照；保留原範圍。 |
| `PIT_HISTORICAL_DATA_REPAIR_CLOSEOUT_2026_07_15.md` | 歷史 PIT repair 工具／coverage 收據；保留限制。 |
| `POST_V1_EVIDENCE_PRODUCTION_SCHEDULER_APPROVAL_CHECKLIST_2026_07_07.md` | 人工核准清單；原文已區分尚待人工核准。 |
| `V4_THREE_LUNA_HANDOFF_PROMPTS_2026_09_08.md` | 舊工作提示與 Git 授權；已標示不可重送或沿用。 |

### `docs/06_qa/` 內容文件：本批全文核讀 8 份

| 路徑 | 核對結果／處理 |
|---|---|
| `BALDR_1000_STOCK_PERFORMANCE_NEXT_GATE_20261009.md` | 813／1208／879 ms 屬不同固定來源／操作基線，不與 Snapshot 六角色矩陣數字混為一談；保留原 scope。 |
| `BALDR_A01_BBANDS_UPPER_20261006.md` | 後續中央整合已接續部分 wiring；已補範圍界線。 |
| `BALDR_A02_H20_GROSS_MODEL_20261006.md` | 後續整合已有 H20 consumer／lineage wiring 與 bounded readback；已補資格界線。 |
| `BALDR_A03_PERSONAL_MODEL_DAILY_20261006.md` | 舊中央 caller 待辦已由後續收據接續；已補命令時點及授權界線。 |
| `BALDR_B01_HISTORICAL_LABEL_BOUNDARY_20261006.md` | 固定 lane 回退命令；已補重核工作樹與所有權提醒。 |
| `BALDR_B03_MARKET_HOME_20261006.md` | Manual 待辦已由手冊附冊承接；已補路由，保留真人／Native 驗收限制。 |
| `BALDR_B04_SELECTION_WATCHLIST_20261006.md` | 早期 session-only 狀態被同文後段持久化 API 更新；已補時序導讀。 |
| `BALDR_B14_SHADOW_CONTROL_20261006.md` | 合成 control-port 證據與條件式 Gate 一致；保留原 scope。 |

QA 既有 205 全文／4 局部／344 未讀與 Entry 203 的 36／6／511 分批數字互不相符，且舊清冊沒有足夠路徑資料解決重疊；本批 8 份只記在具名清單，不改 aggregate。受保護 QA 文件未讀、未搜尋、未 diff。

### `REFACTOR_REPORTS/`：本批全文核讀 13 份

| 路徑 | 判讀／處理 |
|---|---|
| `C1_CODEC_REPAIR_IMPLEMENTATION_REPORT.md` | U2 子階段 `BLOCKED` 為舊整體狀態；已補後續 checkpoint。 |
| `C1_CONTRACT_REPAIR_IMPLEMENTATION_REPORT.md` | U1 子階段 `BLOCKED` 為舊整體狀態；已補後續 checkpoint。 |
| `C1_CROSS_BOUNDARY_READINESS_REPORT.md` | 合成切片的 reopened 狀態過時；已補整體 Gate 時點。 |
| `C1_FORWARD_CONSUMER_READINESS_IMPLEMENTATION_REPORT.md` | U5a 範圍保留，整體 blocked 狀態已更新路由。 |
| `C1_INVOCATION_CAPTURE_IMPLEMENTATION_REPORT.md` | U3 範圍保留；已補後續 C1 Gate 與 R014 限制。 |
| `C1_PERSISTENCE_QUERY_IMPLEMENTATION_REPORT.md` | U4 範圍保留；已補後續 checkpoint。 |
| `C1_ML_FIXTURE_INDEPENDENT_REVIEW.md` | 僅 fixture 複審，不裁定整體 Gate；已補路由。 |
| `C1_ML_FIXTURE_REPAIR_REPORT.md` | 僅 synthetic fixture 修正；已補路由。 |
| `C1_CONTRACT_COMPLETENESS_FINDING.md` | 明確日期化的歷史 finding；原文保留。 |
| `C1_ML_ABI_RECEIPT_READINESS_REPORT.md` | 已有日期／範圍警語；原文保留。 |
| `C1_REOPEN_DISPATCH_BASELINE.md` | 明確日期化的 dispatch baseline；原文保留。 |
| `C1_CONSUMER_READINESS_TEST_MATRIX.md` | 與目前 checkpoint 一致；原文保留。 |
| `C1_VALIDATION_PLAN.md` | 已明確指向最終 rerun／checkpoint；原文保留。 |

原先 Architecture／REFACTOR_REPORTS 累計也缺少可用於交叉去重的完整路徑基線，本批不重算舊總數。以上只補日期、範圍及權威路由，未改寫驗收證據；本批未刪除／搬移文件、未執行測試、Graphify 或最終 repo-wide links／anchors scan。

**目前進度（Coverage History Entries 207–211）：** Entry 207–208 有具名全文核讀 41 份；本次 Entry 209–211 再增加具名全文核讀 48 份（Archive 根層 20、QA 內容文件 13、REFACTOR_REPORTS 15）。加上 B09 時點核對與 Manual §10 狀態修正，以及 BBANDS 操作章節補充。由於更早 QA／Archive／REFACTOR_REPORTS 累計缺少可去重的逐檔 manifest，僅能確認這 89 份具名清單內未重複，不以此推算整體完成率或未讀總數。本次新增歷史／範圍提示與 Manual 修正共涉及 36 份原件，另更新 Archive README、Coverage History 與本矩陣；沒有刪除／搬移文件或資料。測試、最終全 repo links／anchors scan 與 Graphify 刷新尚未執行。

### 第二批具名核讀（Coverage History Entries 209–211）

以下新增清單保留逐路徑核讀證據；不將缺 manifest 的舊累計數字視為可去重總數。

#### `docs/09_archive/` 根層第二批：20 份

| 路徑 | 核對結果／處理 |
|---|---|
| `DOCUMENTATION_CLEANUP_REPORT.md` | 保留歷史刪除報告；內文可核對為第 4 節列 15 項、另列 `CURRENT_STATUS.md` 1 項，合計 16。83（81 MD + 2 TXT）是 2026-01-03 歷史盤點範圍，未用原始收據驗證刪除操作。 |
| `DOCUMENTATION_ENTRY_HISTORY_20261006.md` | 舊 README 快照，導回現行 Archive README。 |
| `DOCUMENTATION_INDEX_HISTORY_20261006.md` | 舊 Core Index 快照，導回現行權威入口。 |
| `DOCUMENTATION_REORGANIZATION_PROPOSAL.md` | 舊提案；保留問題與其歷史狀態。 |
| `DOCUMENTATION_UPDATE_SUMMARY.md` | 2025-12 歷史摘要，不作現況依據。 |
| `MASTER_GOAL_PLAYBOOK_2026_09_06.md` | 加過期任務卡／prompt 直開警示；不將 playbook 當現行派工。 |
| `PHASE_3_3B_IMPLEMENTATION_PLAN.md` | 「全部 epic 100%」與未完成清單並存，保留為未解內部差異。 |
| `POST_V1_EVIDENCE_DECISION_DESK_WORKING_COPY_SMOKE_2026_07_03.md` | 加明確 confirm 會寫 working-copy 的歷史操作提示。 |
| `POST_V1_EVIDENCE_IMPORTERS_QA_2026_07_02.md` | 加舊 importer 限制及命令的時點界線。 |
| `POST_V1_EVIDENCE_OPERATIONS_WEEKLY_HISTORY_RUN_2026_07_03.md` | 加 `--save-history` 會寫指定工作副本 DB 的提示。 |
| `POST_V1_EVIDENCE_SCHEDULED_DRY_RUN_QA_2026_07_12.md` | 保留 wrapper policy blocked 歷史狀態，路由至後續 QA。 |
| `POST_V1_SCHEDULED_EVIDENCE_PIPELINE_QA_2026_07_12.md` | 加 Scheduler register／unregister 副作用與舊任務數提示。 |
| `POST_V1_V1_3_EVIDENCE_OPERATIONS_QA_2026_07_03.md` | 加 `--confirm-action-items` 寫 DB 的歷史操作提示。 |
| `POST_V1_V1_4_EVIDENCE_REVIEW_HISTORY_QA_2026_07_03.md` | 日期化 QA 數字保留為歷史快照。 |
| `PROJECT_SNAPSHOT_AUDIT_2026_07_12.md` | 加 dated gate／weekly audit 界線，不取代現行 Snapshot。 |
| `PROSPECTIVE_FORMAL_CALENDAR_CAPTURE_2026_08_28.md` | 加 `--confirm-network` 會呼叫網路並產生候選輸出的提示。 |
| `PROSPECTIVE_FORMAL_CLOCK_ACTIVATION_2026_08_18.md` | 保留原有勿重用 clock／勿重建回填提示。 |
| `PROSPECTIVE_FORMAL_RESTART_CLOCK_2026_08_26_STAGING.md` | 加一次性 activation／舊 override 與 rollback 的過期提示。 |
| `PROSPECTIVE_FORMAL_RESTART_CLOCK_2026_08_27_V3_STAGING.md` | 保留原有不可重試 one-shot 提示。 |
| `PROSPECTIVE_FORMAL_RESTART_EXECUTION_2026_08_21.md` | 保留舊 execution handoff 非現行排程或授權的界線。 |

#### `REFACTOR_REPORTS/` R001–R005：15 份

| 路徑 | 核對結果／處理 |
|---|---|
| `R001_IMPLEMENTATION_REPORT.md` | 舊 READY 狀態導回 R031 CLOSED；保留日期範圍。 |
| `R001_SOL_ERRATUM_REVIEW.md` | 舊 Wave 1 未完成敘述導回後續 checkpoint 與 R031。 |
| `R001_SOL_REVIEW.md` | 保留 9/22 review PASS，標明現況以 R031 為準。 |
| `R002_GEMINI_REVIEW.md` | 保留 review-only PASS，補 R031 bounded scope 入口。 |
| `R002_IMPLEMENTATION_REPORT.md` | 導回 R031 bounded acceptance，保留 TMP-NUM-01 限制。 |
| `R002_SOL_INTEGRATION_REVIEW.md` | 保留日期化 PASS，補 R031 路由。 |
| `R003_IMPLEMENTATION_REPORT.md` | 導回 R031 ACCEPTED_WITH_BOUNDED_SCOPE，保留舊缺口。 |
| `R003_SOL_FINAL_PRE_REVIEW.md` | 將等待 review 限定為 pre-review 時點並導回 R031。 |
| `R003_SOL_INTEGRATION_REVIEW.md` | 保留 bounded integration PASS，補 R031 路由。 |
| `R003_SOL_REVIEW.md` | 將舊 CHANGES_REQUIRED／blocked 導回後續重作與 review。 |
| `R003_SOL_REWORK_REVIEW.md` | 將等待 Gemini 限定為 pre-review 狀態。 |
| `R004_GEMINI_REVIEW.md` | 保留 PASS；導回 R031 CLOSED_AS_CHARACTERIZATION，未推論 R012 writer acceptance。 |
| `R004_IMPLEMENTATION_REPORT.md` | 將舊 READY 導回 CLOSED_AS_CHARACTERIZATION。 |
| `R004_SOL_INTEGRATION_REVIEW.md` | 保留日期化 PASS，補 R031 路由。 |
| `R005_IMPLEMENTATION_REPORT.md` | 導回 R031 bounded replay；保留 R017／R020 與 profile／precision 限制。 |

#### `docs/06_qa/` B03–B14 第二批：13 份

| 路徑 | 核對結果／處理 |
|---|---|
| `BALDR_B03_UPDATE_RUNTIME_20261006.md` | Manual 已涵蓋主要操作；保留 bounded lane 與歷史測試範圍。 |
| `BALDR_B05_CHART_INCREMENT_20261006.md` | 加舊結論／鍵盤 marker 操作及 rollback 命令的時點與核對提示。 |
| `BALDR_B06_PORTFOLIO_SUMMARY_20261006.md` | 加中央 caller 後續接線與 B09／P2 範圍路由。 |
| `BALDR_B07_RULE_HISTORY_20261006.md` | 保留歷史 eligibility／performance flags，不推升為投資資格。 |
| `BALDR_B08_PERSONAL_ROUTES_20261006.md` | 路由 contract 與未遷移／未啟用限制一致，保留原文。 |
| `BALDR_B09_PERSONAL_PORTFOLIO_20261006.md` | 將初始待接線文字限定於當時，導回有限中央 wiring；明示 producer／formal 未完成。 |
| `BALDR_B10_NOTES_BACKUP_20261006.md` | 加 confirmed backup／restore 的 create-only 寫入提示。 |
| `BALDR_B10_PRIVATE_REVIEW_20261006.md` | 將舊 B09 狀態導回後續證據；不推論所有 B10 caller／production writes 完成。 |
| `BALDR_B11_FAMILY_CATALOG_20261006.md` | 加 BBANDS 未採納提案、無執行／資格授權及歷史 rollback 提示。 |
| `BALDR_B12_DAILY_RUNTIME_20261006.md` | 加 synthetic／offline 與執行／task-review 路徑可能寫產物的提示。 |
| `BALDR_B13_MODEL_INPUT_20261006.md` | 加 synthetic／offline、formal／training false 與歷史 rollback 提示。 |
| `BALDR_B14_SHADOW_EVIDENCE_COMPOSITION_20261006.md` | 加 synthetic scope 及 create／append execute 寫入副作用提示。 |
| `BALDR_BBANDS_RESEARCH_UI_20261007.md` | 將「中央接線待辦」限定於 10/07 handoff，導回目前 Manual；保留 formal daily／parent acceptance、自然成熟限制。 |

QA 舊累計缺少逐檔路徑資料，本批 13 份只增加具名證據，不調整 QA aggregate；P2／M03 receipt 是交叉核對來源，不列入此內容文件 manifest。Manual §10 將 B09 狀態由「待接線」改為有限 route／paths 注入與 query-only readback 已有證據，並明示 Paper producer 全鏈、正式啟用、migration 及排程授權未完成；§9.9.1h 補入 BBANDS 的保存來源、快照更新、參數、結果與未知狀態說明。所有原始驗收正文與歷史命令仍保留；本批沒有刪除或搬移文件。

### 2026-10-11 Archive 根層補充具名核讀（Coverage History Entry 222）

本批核讀下列 9 份 Archive 根層文件；這是具名增量清單，不併入缺少早期逐檔 manifest 的舊累計，也不代表 Archive 根層或全 repo 全文核讀完成。

| 路徑 | 核對結果／處理 |
|---|---|
| `APPLICATION_MANUAL_CHANGELOG_2026_09_27.md` | 日期化變更記錄範圍清楚，未見需更正的現況宣稱。 |
| `DEVELOPMENT_ROADMAP_HISTORY_2026_09_27.md` | 兩個 repo 絕對路徑改為相對連結，方便在其他 checkout 閱讀。 |
| `DOCUMENTATION_REORGANIZATION_MANIFEST_20261006.md` | 限定為 10/06 整理基線；全文件核讀、最終連結／錨點掃描與 Graphify 刷新另計。 |
| `SUPERPOWERS_PLAN_SPEC_DATE_AUDIT_2026_07_06.md` | 標明日期化盤點，不作目前完整清冊或現況。 |
| `V4_WORKSPACE_CLEANUP_CLOSEOUT.md` | 修正「可回滾」的範圍：可重建輸出不等同逐位元組還原原件。 |
| `TWSE_T86_20_DAY_CANDIDATE_PILOT_2026_07.md` | 補 9/21、10/03 後續觀察與 P0 source acceptance register；候選觀察不等於來源採納。 |
| `POST_V1_EVIDENCE_SCHEDULER_APPROVAL_SOP.md` | 明示原件未記建立日期、非現行核准，連到 Manual 與唯讀 Runbook。 |
| `PHASE2_5_COMPLETION_STATUS.md` | 說明後續 10 檔單策略 Walk Forward pilot 不等於全市場或策略優越性驗收。 |
| `PHASE4_STARTUP_SUMMARY.md` | 歷史啟動摘要範圍清楚，未見需更正的現況宣稱。 |

其中 `V4_ML_RELEASE` 長文件（1,432 行）不在本批核讀範圍。七份需澄清的文件及 Archive README 已補範圍／日期／後續證據入口；沒有刪除或搬移文件。未執行測試、Graphify 或最終全 repo links／anchors scan。

**2026-10-10 第十八增量（Coverage History Entry 212）：** 由接手的 Agent 以命令字串風險分流掃描 `09_archive/` 根層，50 份含 `--apply`／`--confirm`／`git`／`schtasks` 命令，其中 12 份缺檔首警語者已補歷史操作警示（`V4_NEXT_FORMAL`、`V4_TDCC`、`V4_NEXT_OPS`、`V4_AUTOMATED_REVIEW`、`NEXT_ACTION_PLAN`、`FUNDAMENTAL_SOURCE_INVENTORY` 與 6 份 Post-V1 QA）。此批閱讀深度為檔首與命令段落，不是全文審閱，不改 Archive 全文／待讀總數；`LUNA_C_HANDOFF` 全文核讀後無需修改。未刪除或搬移文件，未執行測試、Graphify 刷新或最終 repo-wide link／anchor scan。

**2026-10-10 第十九增量（Coverage History Entry 213）：** 以狀態字樣掃描 REFACTOR_REPORTS 26 份候選，10 份會被直開誤讀成目前 disposition 者已加導向 R031 index／final closeout／Snapshot 的時點導覽，其餘 16 份保留。閱讀深度為檔首與狀態字樣行，不是全文審閱，不改該目錄全文／未讀彙總；未驗證各 task 的 R031 逐項 disposition。未刪除或搬移文件，未執行測試、Graphify 刷新或最終 repo-wide link／anchor scan。

**2026-10-10 第二十增量（Coverage History Entry 214）：** 以命令字串掃描 `06_qa/` 根層，16 份候選中 15 份為窄範圍 `git revert`／已限定 ownership 的回滾說明而保留，1 份（`PROJECT_CONSOLIDATION_REVIEW_2026_09_07.md`）的 `Remove-Item` 回滾表已加歷史回滾警示。命令字串類風險分流在 Archive 根層、REFACTOR_REPORTS 與 QA 根層已各掃描一輪；語意層的過時狀態、正文衝突與全文審閱仍未完成，不得視為內容治理完成。未刪除或搬移文件，未執行測試、Graphify 刷新或最終 repo-wide link／anchor scan。

**2026-10-10 第二十一增量（Coverage History Entry 215）：** 接手 Agent 完成全庫基線與生命週期核對。`docs/` 範圍核實為 1,486 個 tracked paths（1,467 份 Markdown、19 份非 Markdown）；全 repository 為 4,686 個 tracked paths、1,493 份 Markdown，另有 `docs/` 外 26 份 Markdown。排查並查明舊基線（1,351 份、Archive 314、QA 533、History 128）為前期未計入巢狀與局部子集之粗估數。完成 QA 主題索引的一批集中補登：將原先未被 4 個主題索引收錄的 172 份 QA 內容收據依主題完整補登至 `PRODUCT_UX_QA_INDEX.md`（85 份）、`DATA_ML_GOVERNANCE_QA_INDEX.md`（54 份）、`INTEGRATION_QA_INDEX.md`（17 份）與 `OPERATIONS_TESTING_QA_INDEX.md`（16 份），其 100% 可達宣稱已依 Entry 216 複核撤回；同步修復架構紅隊審查與 Archive 手冊筆記之相對斷鏈；產生 `docs/` 1,467 份 Markdown 的生命週期清冊草稿；草稿分類尚待逐檔校正，不據此計算成熟度。未刪除或搬移文件，未執行破壞性變更。


**2026-10-11 增量（Coverage History Entry 217）：** 解除 Entry 203 對 F06／F12 的兩項暫列待修候選。F06 原料方法提案與 P07 收斂／突破規則屬不同範圍；F12 的 8 項通過只覆蓋合成 reader，不能代表 UI／跨程序收藏／產品接受。兩份原件的限制足以避免誤讀，無須改寫。

### 2026-10-11 QA 具名全文核讀增量（Coverage History Entries 223–225）

本批依檔名區段全文核讀 QA 原件；逐檔名單留在 Coverage History。過往無檔名聚合不抵扣，這些新增清單先作具名證據，不直接重算缺少完整 manifest 的 QA 全域全文／未讀總量。

- **E–H，51 份全文**（Entry 223）：E／F／G／H 均完成小批逐篇閱讀。問題已修正：F4 schema-v3 新容量通過與正式 v1/v2 轉換待辦分開；多份日期化 QA 加上現況路由；H20 較早狀態改標階段歷史；F02「葉模組」改為「子模組」；H20 圖表收據限定固定 commit；Scheduler audit 最新追加日標為 9/21。QA index 對活躍 E–H 文件未見漏列。
- **F03/F12 後續收據，10 份全文**（Entry 224）：F03 多 parent 計畫的「尚未實作」狀態由 17 節點 bounded publication 證據更新；F12 attempt04 的歷史待終態句連回已記錄的 1 passed。產品完整 query／Main constructor／EXE／收藏資格仍分開標示未完成。
- **S–T，51 份全文**（Entry 225）：34 份 QA 內容文件及 17 份歷史 redirect stub；34 份內容文件均有 QA 主題索引入口，17 個 stub 的 Archive 目標均存在。修正投影 QA 過時的排程 hook 待辦時點與 9/15 inventory triage 的歷史數字提示；修正 9 個測試清冊理由欄位完全重複的文字。Entry 222 已核讀的 Archive 原件不重複計入本批 QA 路徑清單。

上述修改只調整狀態說明、導覽及重複文字；沒有搬移／刪除原始 QA。受保護的使用者進行中文件仍未讀正文、未搜尋或 diff。未執行測試、Graphify 或最終 repo-wide link／anchor scan。
### `docs/09_archive/` 根層補充具名核讀：10 份（2026-10-11）

| 路徑 | 核對結果／處理 |
|---|---|
| `AI_CONTEXT_PACK_HISTORY_20260830.md` | 在舊 main-centric 協作章節加上就地取代提示，直連現行 multi-agent workflow／shared context。 |
| `API_INVESTIGATION_REPORT.md` | 明確 Selenium 等替代方案與待辦只是歷史提案，不代表已核准或實作。 |
| `ARCH_GOVERNANCE_CHECKLIST.md` | 歷史自檢清單已有非現行強制 gate 界線；保留原文。 |
| `ARCH_GOVERNANCE_LIFECYCLE.md` | 早期提案與現行治理流程界線清楚；保留原文。 |
| `ARCH_VIOLATION_RESPONSE_POLICY.md` | 歷史政策已有非現行 enforcement 界線；保留原文。 |
| `BACKTEST_LAB_CHECKLIST.md` | 釐清 v1.1／v1.0 日期為版本記錄，2026-05-27 為後續補充。 |
| `BACKTEST_LAB_FAQ.md` | 將 10 筆明確限定為歷史 UI 前置檢查，連回現行 Manual 的 Registry Promote 20 筆門檻。 |
| `BACKUP_RETENTION_AUDIT_2026_07_06_HISTORY.md` | 備份輪替、歷史候選與禁止推定刪除授權等界線足夠；保留原文。 |
| `BALDR_DAILY_EVIDENCE_MODEL_READINESS_20260925.md` | 增加 9/25 時點提示與 Project Snapshot 現況入口。 |
| `BALDR_DAILY_TECHNICAL_PARSE_DIAGNOSTIC_QA_20260925.md` | 已清楚限定 synthetic QA、日期、hash 與未涵蓋範圍；保留原文。 |

Archive 根層本批只補五份歷史原件的時點／權威提示；不調整缺逐檔 manifest 的舊 aggregate。逐篇判讀見 Coverage History Entry 226。未刪除或搬移文件，未執行測試、Graphify 或最終 repo-wide links／anchors scan。

另依 Entry 227 修正 `docs/06_qa/H20_INDEPENDENT_CURRENT_RESEARCH_20261008.md` 的固定版候選描述：區分早期 `421bc973a891` 與後續後代 `bd5d2f86367ae8adb3d110f7e2b83fb829a620cf`，並限定後者的同版收據只覆蓋圖表範圍。未推定獨立研究入口已通過固定版驗收。

依 Entry 228，Manual 的 10/09 排程驗收摘要已標記為當日狀態快照，並連到現行 21-task Runbook 與 Project Snapshot；沒有讀取或修改使用者進行中的完成進度文件。

依 Entry 229，Manual 的 9/30 排程執行與 10/1 研究收集狀態兩段已逐位元組移入 Archive 日期化工程筆記；Manual 保留同名章節錨點與現行 Runbook／Snapshot 入口。Guide 目錄仍待 Manual／Supplements 全面核讀與剩餘日期段分類。

### `docs/09_archive/` 根層補充具名全文核讀：10 份（Entry 230）

| 路徑 | 判讀／處理 |
|---|---|
| `BALDR_PRODUCT_INTEGRATION_ACCEPTANCE_20260925.md` | 9/25 唯讀基線與 production／writer 未授權界線清楚；保留。 |
| `BALDR_SCHEDULER_RECONCILIATION_20260925.md` | 21 tasks／48 automations 為 9/25 快照；Ready／exit-zero 不視為產品證據。 |
| `BRANCH_WORKTREE_CONSOLIDATION_20260927_HISTORY.md` | 只記 9/27 Git 狀態，不作現況或清理授權；Archive README 有現況導向。 |
| `BROKER_FLOW_SEMANTIC_OPTIMIZATION_2026_07_15.md` | 7/13 scoped performance gate 收據；不代表整體 dashboard 通過。 |
| `BROKER_FLOW_SQLITE_DASHBOARD_PERFORMANCE_2026_07_15.md` | 保留整體 gate 未通過數據，與後續 scoped 修正分開。 |
| `CONTINUITY_REVIEW_LOOP_GAP_AUDIT_2026_09_15.md` | 已有 10/10 後續增量與剩餘 journey 限制提示。 |
| `CROSS_PAGE_DECISION_JOURNEY_MAINWINDOW_2026_09_15.md` | Synthetic bounded acceptance，不推論 broker order／實際成交。 |
| `DAILY_BANKTAIWAN_LEARNING_COST_2026_09_14_HISTORY.md` | 成本與 smoke 範圍清楚，未證自然成熟。 |
| `DAILY_BANKTAIWAN_OPERATIONAL_2026_09_14_HISTORY.md` | 專用歷史 shadow task 與當次執行，不授予交易或 broker action。 |
| `DAILY_INVESTMENT_JOURNEY_2026_09_14.md` | 9/14 readonly snapshot；後續 R1 不等於自然成熟或完整產品驗收。 |

本批 10 份在現有具名 manifest 未見全文紀錄；Entry 204 的 74 份報告早期批次無逐檔 manifest，故不據此宣稱全歷史零重疊、不累加舊 aggregate。逐檔引用與限制見 Coverage History Entry 230。

依 Entry 231，Manual 中 2026-10-03 的 Revision-Aware 早期操作模板已移入 Archive；Manual 保留同名標題與指向現行 §7.0.1／整合修復 QA 的短導引。10/03 weekly 收據段與 10/02 Paper／quote 安全操作段仍待分別判斷是否保留或拆分。

**2026-10-11 QA K–R 批次（Coverage History Entry 232）：** 已具名全文複核 10 份 QA 內容文件；10 份皆有主題索引路由。歷史數字、日期化交接與 ML 命令模板需依原文件時點及 R031 收據判讀，不視為即時狀態／現行操作授權。因舊 QA aggregate 缺逐檔 manifest，不調整累計總數。受保護的完成進度文件未納入本批；本批未改 QA 原文、未執行測試、Graphify 或最終 repo-wide links／anchors scan。


## 2026-10-11 新增具名全文核讀與修訂批次

以下是本輪可由 Coverage History 逐路徑核對的新增清單。這些具名增量不與缺少逐檔 manifest 的舊 aggregate 相加，也不代表各目錄剩餘文件已讀完。

| 目錄 | 新增全文核讀 | 本次修訂 | 判讀與待處理 |
|---|---:|---:|---|
| 01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/ | 46 | 27 | R006／R007／R008 增量見 [Entry 233](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-233)，R024–R029 新批見 [Entry 239](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-239)。另具名核讀 R010–R012 八份見 [Entry 254](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-254)；舊 74 份聚合無清單，故不加算。保留原 verdict；舊 82／23／119 基線不重算。 |
| 01_architecture/target_architecture_2026_09_22/（非 REFACTOR_REPORTS） | 0 net（10 份具名再核對） | 2 | 10 份已包含於先前 21/21 的分類基線；本次補具名路徑及驗收矩陣定位，見 [Entry 245](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-245)。 |
| 06_qa/ | 55 | 23 | U–Z、A–J、B03–B07、先前 7 份、WP1–WP4 八份及 P01／P08 十份皆核對主題索引入口；修訂後續日期／範圍的直開誤讀。見 [Entry 235](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-235)、[237](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-237)、[241](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-241)、[248](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-248)、[251](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-251) 與 [255](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-255)。QA 舊 aggregate 缺逐檔 manifest，不重算全文總數；使用者進行中的完成進度文件排除。
| 03_data/ | 0 net（9 份再核對；7 份重疊、2 redirect） | 1 | `daily_data_update_guide.md` 的舊 TWSE 技術細節已標歷史；既有 8 份全文／2 redirect 基線不重算。具名清單與判讀見 [Entry 246](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-246)。 |
| 09_archive/ 根層 | 23 | 9 | 第五至八批具名全文核讀見 [Entries 236](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-236)、[240](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-240)、[249](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-249) 與 [256](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-256)。本批 8 路徑先前未在具名清單出現，但早期 aggregate 無清單，故不以此推算去重總數；另加六份時點／狀態提示。
| 09_archive/ 子目錄 | 10 | 5 | Archive 子目錄第七批見 [Entry 242](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-242)。另具名再核對 target architecture／Dispatch 八份及 Archive Superpowers 八份，分見 [Entries 252](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-252) 與 [253](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-253)，均已包含於既有 30/30、96/96，不加算。券商舊操作文件有檔首提示；Phase 4 原件補充 checklist 時點界線。 |
| superpowers/ retained originals | 69 | 44 | 69 份 retained originals 均已具名全文核讀；最新三份及總量口徑見 [Entry 250](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-250)，前批新增與警語見 [Entries 234](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-234)、[238](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-238)、[243](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-243)、[244](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-244) 與 [247](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-247)。原 105 估算已由目前逐檔分類取代；README 保留風險路由。 |

REFACTOR_REPORTS、QA 與 Archive 歷史總量仍是「具名增量＋不可還原舊基線」，不可把本表的新數字加到舊全文／未讀數作為精確現況。所有目錄完成內容複核與修訂前，不執行 Graphify 刷新或最終 repo-wide link／anchor scan。
