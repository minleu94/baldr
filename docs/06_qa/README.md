# QA 證據導覽

- [產業題材頁探索與卡片優先呈現（2026-10-28）](BALDR_THEME_PAGE_EXPLORATION_ORDER_20261028.md)：排行與成員預設卡片、九項指標改以指標卡閱讀，完整表格可切換／展開；主要題材探索及明細前移。題材 UI 61 passed，必要 Workbench UI、Update validator、定向 mypy 與編譯結果及 repo-wide mypy 阻塞均有記錄。
- [Gate 1 日常 Advice 與保存讀回證據（2026-10-28）](BALDR_GATE1_DAILY_E2E_20261028.md)：隔離 MainWindow／journal readback、busy-close 與 500 筆上限外的歷史查找已通過；凍結資料／策略／Advice policy 的完整推薦至 Advice deterministic replay 也通過。正式來源仍 estimated/missing、research-only 且無 formal credit；Owner 原生 GUI UAT 尚未完成。
- [2026-10-27 Evidence Review 內保存候選處置與 SQLite WAL 防競態](BALDR_GATE2_WORKING_COPY_AND_GATE3_OBSERVATION_VISIBILITY_20261026.md#2026-10-27-evidence-review-內保存候選處置與-sqlite-wal-防競態)：候選處置可由 UI 綁到明選 working-copy weekly history，完整重驗 SQLite file set 並讀回 ID/hash；Owner UAT 與 Gate 2 真實週期仍未完成。

- [MarketSessionCadence 與 Evidence dry-run 修正（2026-10-26/27）](BALDR_MARKET_SESSION_TEMPORARY_CLOSURE_CADENCE_20261026.md)：讀取臨時休市 sidecar、歷史 replay 以決策日驗證日曆，並以 hash-verified TWSE 原始方向符分類 Breadth；完整隔離流程無 pipeline blocker，已知官方不可比排除保留數量並列 advisory，Forward summary 仍 degraded。
- [Forward 來源觀察 chunk 上限修正（2026-10-26）](BALDR_FORWARD_SOURCE_OBSERVATION_CHUNK_CAP_20261026.md)：修復 128 chunk 上限早於 query／manifest／run-byte 契約失敗，129 個小型 query 回歸通過；正式自然 Forward run 尚待驗。
- [Opus／Antigravity UX 工程收尾](BALDR_OPUS_UX_IMPLEMENTATION_CLOSEOUT_20261023.md)：Opus 起始、Antigravity 接手審查的來源核對，Sol／Luna M1–M125 切片、同源警示與持倉報價日期的隔離 QA，以及尚未接受的正式 Gate。M 編號是切片序號，不是功能數。

- [Track B 六包交付獨立複核](BALDR_TRACK_B_SIX_PACKAGE_REVIEW_20261023.md)：七筆 Legacy、Weekly 遷移信任範圍、Forward 每事件政策、9,423 筆版本矩陣與精確 output 導航登記；不授正式來源接受。

- [Track B 金融資料與營運補完](BALDR_TRACK_B_DATA_OPERATIONS_20261022.md)：10/22 新自然收據、修訂 custody 語義核驗、Formal immutable terminal、七維狀態矩陣及 Track A/C 契約；金融接受與新自然執行另判。
- [每日營運恢復觀測（2026-10-21）](BALDR_DAILY_OPERATIONS_RECOVERY_20261021.md)：21 個 Windows task readback、六軌操作觀測、Freshness／Evidence same-run 收據契約與各分支未驗條件；設定 readback、有限只讀 scope 與候選修復不代表自然 run 或金融 Gate 通過。
- [V2 Release Closeout](BALDR_V2_RELEASE_CLOSEOUT_20261021.md)：唯一 Source／EXE、Windows 全發現、Codex 設定讀回與恢復邊界；自然運行、金融資格及真人接受分軌。

- [月營收全用途整合](MONTHLY_REVENUE_FULL_SCOPE_ACCEPTANCE_20261021.md)：雙市場原件、版本歸檔、逐用途資格與研究接線；Source 工程與正式金融接受分別判讀。
- [MOPS 月營收衝突報告獨立複核（2026-10-28）](MOPS_MONTHLY_REVENUE_CONFLICT_REAUDIT_20261028.md)：逐類對照 412 列問題與 325 列處置清冊、核對 37 列 OpenAPI 值、直接檢視可達的 F22 明細頁及正式 SQLite 月份覆蓋；區分本機缺件、MOPS 頁面觀察、來源版本衝突與正式 DB 尚未載入。
- [MOPS 每日月營收候選排程 QA（2026-10-29）](MOPS_DAILY_SNAPSHOT_CAPTURE_QA_20261029.md)：Daily Quick 獨立抓取雙市場 MOPS 候選、完整發布 marker、期別週末順延及待下一次自然排程核實的狀態。

- [V2工程補完與整合](BALDR_V2_FINAL_COMPLETION_20261021.md)：具名月營收來源、人工確認Paper producer、真Main歷史來源保存重開與五旅程五軌判讀；不取代原金融批准或Native／Owner驗收。

- [10/18 後繼題材每日研究](BALDR_THEME_DAILY_QA_20261018.md)：M1定向驗證、真實資料工程量測、M2接線及各自未驗界線；[研究12](BALDR_THEME_DAILY_QA_20261018.md#固定12research07回報交付qa227234)另核research07五項回報、固定EXE／新程序及交付，原完整Gate不變。

- [2026-10-25 產業方向圖卡與公告時間對照](BALDR_INDUSTRY_LEADER_CARDS_20261025.md)：領先／落後卡成員方向圖及 Q2 公告時間候選匹配、實際 formal 解除數；不宣稱全市場寬度、正式資料寫入或來源／Gate 接受。

- [2026-10-26 產業卡與人工研究決定 UI 增量](BALDR_INDUSTRY_LEADER_CARDS_20261025.md#首屏法人淨額分布增量2026-10-25-root-驗證)、[Workbench Advice 收據](BALDR_WORKBENCH_ADVICE_SOURCE_BRIDGE_20261024.md#2026-10-26-workbench-advice-人工研究決定入口)、[保存研究結果交接](BALDR_WORKBENCH_ADVICE_SOURCE_BRIDGE_20261024.md#2026-10-26-手動保存研究結果交接至-workbench)：題材法人家數分布、精確 Advice 人工研究記錄及 canonical 保存結果的手動讀取流程；不建立交易或連線帳戶、不授 Gate credit。

- [2026-10-26 promoted 策略研究候選降級](BALDR_WORKBENCH_ADVICE_SOURCE_BRIDGE_20261024.md#2026-10-26-promoted-策略缺接受證據時保留研究候選)：正式採用／鎖參／揭露證據缺漏時保留 RESEARCH 候選、絕不升格正式 Advice；Gate 1 狀態未變。

- [2026-10-26 Gate 2 weekly collection 匯出與 working-copy 證據](BALDR_GATE2_WORKING_COPY_AND_GATE3_OBSERVATION_VISIBILITY_20261026.md#2026-10-26-gate-2-weekly-candidate-review-packet)：更新頁可匯出唯讀候選 JSON，人工 review、history 與 Gate credit 仍未接通。
- [2026-10-27 Gate 2 候選處置綁定週報 history](BALDR_GATE2_WORKING_COPY_AND_GATE3_OBSERVATION_VISIBILITY_20261026.md#2026-10-27-candidate-disposition-綁定週報-history)：candidate artifact 先綁入 working-copy history，再核對精確 hash 由 Owner append-only approval；真實週期與 Gate 2 條件仍待完成。

- [2026-10-25 本機資料品質唯讀盤點](BALDR_DATA_QUALITY_INVENTORY_20261025.md)：fundamental 資料現況、Open Data 季報候選及 MOPS 公告時間 crosswalk；另記 2026-10-26 2330／2026-Q2 MOPS 公告與 T57 上傳時間分欄的候選 builder，以及 2026-10-28 T164 PDF disposition bundle 完整性重驗。原始 DB 以唯讀核查，不能由 candidate matches 推成正式資料資格。

> 本目錄保存日期化驗收、調查與交接證據。它們描述各自的範圍與時間點；目前專案狀態請看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，產品操作請看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。主題相同不代表證據可互換，舊報告中的待辦也不自動成為目前待辦。

## 先從這裡開始

1. [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)：目前狀態、未成熟項目與阻礙。
2. [10/08 產品補完缺口再核對](BALDR_COMPLETION_GAP_REVIEW_20261008.md)：近期補完範圍與缺口入口。
3. [10/08 排程修復](BALDR_SCHEDULE_REPAIR_20261008.md)：近期排程修復的證據入口；查更早時點再讀 [9/30 排程修復](SCHEDULED_OPERATIONS_REPAIR_20260930.md)。
4. [10/09 排程與 Codex automation 修正](BALDR_SCHEDULE_REMEDIATION_20261009.md)：21 個 Task 的回讀結果、仍未解除的來源缺口與回復資訊；producer 結果與排程 exit code 分開判讀，共同只讀操作規則見 [排程稽核 Runbook](../07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。
5. [10/09 產品補完恢復開發基線](BALDR_COMPLETION_RESUME_20261009.md)：記錄 checkpoint 後的工作分工與首輪驗證；不是產品完成或發布收據。原暫停點見 [10/09 交接](BALDR_COMPLETION_HANDOFF_20261009.md)。
6. [10/10 複合研究真人驗收](BALDR_COMPOSITE_HUMAN_CHECK_20261010.md)：自動化旅程已通過，但真人結果尚未取得；只完成逐步真人操作並留下結果後才算驗收。
7. [10/10 補完進度](BALDR_PRODUCT_COMPLETION_STATUS_20261010.md)、[P08 行情證據](BALDR_P08_PRICE_EVIDENCE_SLICE_20261010.md)與[前向現金開戶](BALDR_P08_CASH_SEED_SLICE_20261010.md)：完整待辦範圍、同次唯讀取值及版本專屬空帳戶；不代表 daily／策略績效資格完成。
8. 按下方主題地圖選擇索引；需要操作步驟時回到 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。

- [10/12 補完恢復增量](BALDR_COMPLETION_RESUME_PROGRESS_20261012.md)：治理後 M27 封套、Root 串行 QA、Main 原生診斷及 Health 來源重封；按具名收據判讀，不授完整工作包或 Gate 接受。
- [10/14 補完暫停 checkpoint](BALDR_COMPLETION_CHECKPOINT_20261014.md)：P01 效能暫緩、P08 六組限定 PASS、未封存共同接線、Root 全量來源讀回與恢復順序；完整 Gate 尚未接受。

<a id="主題地圖"></a>
## 主題地圖

| 主題 | 入口 | 範圍 |
|---|---|---|
| 產品、個股研究與 UX | [產品與個股研究索引](PRODUCT_UX_QA_INDEX.md) | H20、BALDR B01–B14、功能驗收鏈、Watchlist、投資組合與圖表。 |
| 資料、ML 與來源治理 | [資料與 ML 索引](DATA_ML_GOVERNANCE_QA_INDEX.md) | R026／R031、ML Shadow、前瞻證據、PIT、基本面與來源接受。 |
| 跨工作流整合 | [整合索引](INTEGRATION_QA_INDEX.md) | WP1–WP5、Task Loop、Continuity／Decision Journey、LUNA 與跨工作流收據。 |
| 程式規模與產品落差研究 | [2026-10-12 固定研究基線](../09_archive/product_research_baseline_20261012/README.md) | 行數、長檔案／函式、精確 AST 候選與產品交付診斷；重構前沿用，未做效能或完整產品驗收。 |
| 營運與測試 | [營運與測試索引](OPERATIONS_TESTING_QA_INDEX.md) | 排程、資料更新效能、測試路由、固定路徑與維運證據。 |
| 儲存與冷封存 | [C 槽冷封存狀態對照（2026-10-09）](C_DRIVE_QA_COLD_ARCHIVE_RECONCILIATION_20261009.md) | 第一批 6/6、第二批 28/28 已按終態收據完成；摘要未重新計算全量 SHA，容量數字是時間點快照。 |

## 相容深連結

<a id="ml-shadow-與前瞻證據"></a>
### ML Shadow 與前瞻證據

前瞻與 ML 收據請從[資料與 ML 索引](DATA_ML_GOVERNANCE_QA_INDEX.md)進入；目前模型狀態依 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 判讀。

<a id="排程與自動化"></a>
### 排程與自動化

排程修復、稽核與測試收據請從[營運與測試索引](OPERATIONS_TESTING_QA_INDEX.md)進入；全排程共用操作見 [BALDR Scheduled Audit Runbook](../07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。

<a id="h20-個股研究"></a>
### H20 個股研究

個股研究與 H20 收據請從[產品與個股研究索引](PRODUCT_UX_QA_INDEX.md)進入；目前狀態依 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 判讀。

<a id="wp1wp5-package-evidence-index"></a>
### WP1–WP5 工作包收據索引

工作包收據已移至[整合索引](INTEGRATION_QA_INDEX.md#wp1wp5-package-evidence-index)。保留此錨點供既有連結使用；原收據仍保留各自範圍，不代表全部工作包已通過。

<a id="baldr-b01b14"></a>
### BALDR B01–B14

功能收據已移至[產品與個股研究索引](PRODUCT_UX_QA_INDEX.md#baldr-b01b14)。保留此錨點供既有連結使用；依產品補完缺口表判讀各自範圍。

## 閱讀與歸檔規則

- QA 原文保存當時輸入、失敗、結果、回滾與接受邊界；入口摘要只供導覽，不改寫證據結論。
- **生命週期**：日期或「完成」標籤不代表可搬移。仍有未解 Gate／重驗、活躍文件引用、測試／腳本依賴或固定輸出路徑的收據留在本目錄；只有結案、替代入口明確且依賴解除後才歸檔，保留舊路徑導引與原件 bytes／hash。詳見 [DOCUMENTATION_STRUCTURE](../00_core/DOCUMENTATION_STRUCTURE.md#qa-evidence-retention)。
- 超長報告先讀標題、開頭的範圍／結論及本頁入口，再依問題查原始章節；不要把整份 terminal dump 當成目前狀態。
- 全 repository 的文件分類、逐檔核讀狀態與未解矛盾見 [全 docs 文件治理狀態矩陣](../00_core/DOCUMENT_GOVERNANCE_STATUS_MATRIX_20261011.md) 及[逐檔 manifest](../00_core/DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv)；矩陣不是產品現況 SSOT，產品狀態仍以 Snapshot 為準。四個主題索引與冷封存對照表提供 QA 內容文件導覽；逐篇核讀進度與尚未完成的覆蓋核對見矩陣及 Coverage History。索引可達不代表正文已核讀或驗收通過。
- G02／G03／G04／G05／G10 的逐項裁決、修復與未驗收界線見[五項治理問題收據（2026-10-12）](DOCUMENT_GOVERNANCE_ISSUE_RESOLUTION_20261012.md)；工程回歸與自然排程事件、完整產品接受分別判讀。
- **2026-08-14 BALDR 本機狀態報告**：JSON 與 HTML 原件已逐位元組封存至 [歷史報告套件](../09_archive/project_status_2026_08_14/README.md)；[舊 QA 路徑相容導引](project_status_2026_08_14/README.md)保留原路徑入口。這是當日 CPU／MCP／Git／QA 快照，不代表目前狀態；現況看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，來源 bytes／SHA 與依賴檢查見 [Coverage History Entry 117](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-117)。
- 其他 JSON 收據與機器／報告伴隨物，仍須與對應說明文件一起判讀；不要只憑檔名把它們當作獨立產品文件。
- 歷史 archive 的定位與規則見 [docs/09_archive README](../09_archive/README.md)；完整文件分類見 [DOCUMENTATION_INDEX](../00_core/DOCUMENTATION_INDEX.md)。
- 已歸檔 QA： [文件編碼稽核（2026-06-16）](../09_archive/DOCUMENT_ENCODING_AUDIT_2026_06_16.md)、[文件與 Roadmap 重整稽核（2026-07-03）](../09_archive/DOCUMENTATION_ROADMAP_REBASELINE_AUDIT_2026_07_03.md)、[Pre-push 文件治理稽核（2026-07-06）](../09_archive/DOCUMENTATION_PRE_PUSH_AUDIT_2026_07_06_HISTORY.md)、[Pre-V2 非排程 readiness closeout（2026-07-06）](../09_archive/PRE_V2_NON_SCHEDULE_READINESS_CLOSEOUT_2026_07_06_HISTORY.md)、[ML Shadow 推論操作 closeout（2026-07-15）](../09_archive/ML_SHADOW_INFERENCE_OPERATIONS_CLOSEOUT_2026_07_15_HISTORY.md)、[SQLite inspector 關閉探測（2026-09-15）](../09_archive/QT_SQLITE_INSPECTOR_SHUTDOWN_PROBE_2026_09_15.md)。
