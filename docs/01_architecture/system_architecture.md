# 目前系統架構

research07增量沿既有工作區與Journal：明確一般查詢建立獨立context，原來源圖只做顯示用SMA，題材清除不寫來源，原價格筆記追加tombstone隱藏家族；績效與訊號reader契約保持。操作生命週期見[current工作區](current/application_and_workspaces.md#research07操作邊界增量)，投影／刪除語義見[current決策](current/decision_research_portfolio.md#research07顯示與保存增量)與[儲存分冊](current/data_storage_runtime.md#原價格筆記邏輯刪除research07)。

> 本文件是 current 模組、資料流與責任邊界的入口，不記錄逐日進度。完成度看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，產品方向看 [Product Roadmap](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md)，目標實作設計唯一權威是 [FINAL_TARGET_ARCHITECTURE](target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)。

## 系統用途

月營收全用途Owner授權已成立；來源資格仍由raw capture、版本歸檔、用途policy及外部固定SHA的qualification reader分開履行。新研究service沿原FactorGate／CrossSectionalFactorPipeline供明示shadow分析，正式Scoring與歷史PIT不能由研究入口升格。長期歷史分批、原件與修訂時間見[全用途契約](../03_data/MONTHLY_REVENUE_FULL_SCOPE_CONTRACT.md)；本輪實際接線／QA仍按[驗收](../06_qa/MONTHLY_REVENUE_FULL_SCOPE_ACCEPTANCE_20261021.md)判讀。

V2保存研究的人工確認模擬經Main原件核驗、獨立對話框及application composition接入既有Paper帳本。外部SHA證據reader分別核現金／行情／日曆用途、原策略帳戶與唯一seed，再以同一唯讀交易取得帳本列和CAS；producer在人工確認後依原政策／費用建立fill、transition和operation marker，同交易保存。月營收另有具名TWSE／TPEx OpenData profile，沿原daily snapshot publisher／reader及exact cohort binding，不改標MOPS。責任、限制及接受邊界見[增量決策](BALDR_V2_SOURCE_PAPER_INTEGRATION_20261021.md)。

研究時間軸新增原件與獨立現況的唯讀對照；原件核驗、來源 reader 與非持久化展示契約分開，Main 管理背景讀取及離頁取消。詳見[工作區](current/application_and_workspaces.md)及[決策研究分冊](current/decision_research_portfolio.md)。這不變更研究保存或金融資格契約。

三段轉折收縮沿原單股producer／Broker／Research Registry接線，同次保存12來源SHA、轉折與原量能證據；reader只核原件，不查目前executor補舊規則。歷史價格合法千分位解析版另隨新run保存，不修改來源資料或舊run；責任見[current決策分冊](current/decision_research_portfolio.md#三段轉折收縮的同次保存)。

計分策略另以1.1.0分版修正缺指標回填，保留舊executor與保存件；沿原producer／Broker／Registry保存v3逐日證據，不另造撮合或儲存。版本metadata查詢、分析邊界及唯讀比較見[current決策分冊](current/decision_research_portfolio.md#計分策略的版本化因果輸入)；交付與金融資格各依具名QA。

四均線基礎研究沿原策略Registry、單股producer、Broker、保存與歷史reader接線；新schema綁同次四MA與前後排列，不查目前executor補舊規則，不新增儲存或金融公式。責任與61列前置窗見[current決策分冊](current/decision_research_portfolio.md#四均線研究的同次來源與唯讀回訪)。

具名營益版本沿原個股 report service／DTO／基本面分頁讀取；原件、用途及小時守衛在 application reader，UI只呈現。精確範圍與非歷史用途見[current資料分冊](current/data_storage_runtime.md#具名營益目前研究版本)。

原回測PF以有語意版本的nullable分析值傳遞，零分母／無配對不顯假零或金額；batch／optimizer／保存與舊比較隔離沿[current分冊](current/decision_research_portfolio.md)，不遷移正式資料或升級舊值。

新單股研究結果沿原 analyzer、Registry 保存與歷史卡讀回；七項原指標以 `single-backtest-performance.v1` 綁原值、狀態、實際計算期間與表格證據。舊資料缺版本不回填，新版本不授績效資格或 Decimal 核心精度；詳見[決策與研究 current 分冊](current/decision_research_portfolio.md)。

baldr 是台股研究與投資決策系統。它收集與治理市場資料，提供市場觀察、推薦、回測、研究證據與持倉檢視。Advice、Paper、Live 與 broker execution 是不同權限；架構中有研究或 shadow 模組不等於產品 Gate 已通過。

## 分層與實際模組

決策擷取的終態 reader 位於 application 層，重用原 producer receipt／artifact 與檔案守衛，供 Runtime 營運狀態及 Workbench 共用；Qt 不自行讀檔或根據 passed 字串授成功。原件、時鐘、讀取預算、取消及保存未知的契約見[Runtime 與排程](current/data_storage_runtime.md#runtime-與排程)，不改正式 Task 或資料根。

```mermaid
flowchart TD
    User[使用者]
    UI[PySide6 UI<br/>ui_qt/]
    App[Application services / DTO / repositories<br/>app_module/]
    Decision[決策與分析<br/>decision_module/ · analysis_module/]
    Backtest[回測與模擬<br/>backtest_module/]
    Portfolio[Portfolio domain<br/>portfolio_module/]
    Data[資料來源、讀取與保存<br/>data_module/]
    Runtime[Runtime 與營運狀態<br/>runtime/ · app_module/runtime_services/]

    User --> UI --> App
    App --> Data
    Data --> App
    App --> Decision
    App --> Backtest
    App --> Portfolio
    App --> Runtime
```

`financial_module/` 提供金融數值單位；`ml_module/` 與 `development_module/` 承載受限制的研究／模型流程。這些 package 在 repo 中存在，但其產品資格仍須按 Snapshot、產品 Gate 與具名 QA 判讀。

後繼題材研究沿`ThemeDailyService`／`SQLiteThemeMarketReader`／`read_theme_research_snapshot`投影到既有市場探索工作區；UI不計算金融值或自行讀正式DB。新聚合不改原分類萃取，缺來源、方向或合格日曆保留不可用；原金融與歷史PIT資格不因技術驗證升級。[契約及證據](../02_features/INDUSTRY_THEME_MAP_DESIGN.md#53-後繼每日研究實作2026-10-18)

R104的`theme_member_navigation` Python候選只處理已載入題材snapshot內的成員導覽，沿原成員列及篩選版本核對selection revision；報告切換股票時由既有行情reader載入該股資料，返回恢復原題材選列。來源或選列漂移會拒絕導覽，已保存報告不可切股。候選的正常Main／新程序導航已於QA096通過，固定2b EXE未含；新412ca3候選已由QA103驗正常frozen Main first/fresh；QA092的定向檢查不等於整輪驗收。

原價格版本的個股判斷由`PinnedStockResearchNoteService`沿既有Journal／CAS追加，綁既有F07 bookmark與public exact reader。一般報告則由`StockResearchReportNoteService`保存版本化完整projection與判斷，仍走同一本Journal；重開時核驗canonical SHA，在獨立只讀ReportView呈現，不接Main即時providers。兩路來源不混用，沒有新增金融producer或第二筆記帳本；各自QA與固定交付範圍見[契約](current/decision_research_portfolio.md#價格研究個股與-portfolio-跨頁接線)。

後續F07 Source由Main將同一筆記服務的有界語義證明範圍接至原完整來源reader與筆記worker，每次動作仍核當前全部原件並還原本次DTO，新程序重新冷驗。它不快取原來源狀態、不擴P01資格或更動保存時鐘；邊界與具名驗證見[資料架構](current/data_storage_runtime.md)及[QA163–168](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#f07語義證明範圍qa163164)，未收入固定06。

依賴方向由 UI 經 application 到領域與資料邊界。Qt 不成為 domain 計算 owner；資料 reader 不自行決定 Advice；Runtime 不持有推薦公式。`ui_qt/main.py` 是 Qt 主程式入口，Windows 啟動由 `baldr_launcher.py` 導入既有 composition。[`decision_module/industry_theme_map.py`](../../decision_module/industry_theme_map.py) 作為獨立之 L2 產業鏈與題材萃取對應模組，僅讀取 `TWStockConfig` 解析 `<DATA_ROOT>/meta_data/` 路徑並產出產業檔案、題材檔案與股票對應檔案，目前不介入既有 UI 或每日選股流程；詳見[L2 產業鏈與題材設計文件](../02_features/INDUSTRY_THEME_MAP_DESIGN.md)。

法人固定批次唯讀路徑沿 UpdateView → UpdateService → `institutional_daily_snapshot` → 原capture／parser，原件、時鐘及資格由application reader核驗，widget只呈現。TPEx可另明選`institutional_source_use`的外部SHA契約，重用DailySourceUseAcceptance，固定官方文件／市場／schema／股數／diagnostics；一次接受與逐批品質小時分離，generic P0 v1決議及其他來源資格不變。具體保存／讀回界線見[資料架構](current/data_storage_runtime.md#讀寫與保存契約)。

## 九個工作區與閱讀路徑

保存母體的四路同 callback Projection Group V3 是 application backend 的 opt-in seam；MA／KDJ／volatility 與 F07 facts 共用 exact verified parent，來源 ledger、population 及 canonical digest 綁同 session。既有 V2、UI／query／bookmark 仍依各自入口，未由新增 backend 宣稱完整比較工作流完成。責任邊界見[UI 與應用流程](current/application_and_workspaces.md)。

目前 route 定義保留九個穩定 workspace keys：`workbench`、`market_explore`、`recommendation`、`backtest`、`watchlist`、`stock_research`、`portfolio`、`update`、`runtime`，供既有 route、context 與來源回訪識別。V2 導覽將這些頁面呈現在「今日總覽」、「探索與研究」、「我的投資」、「策略實驗室」四個主導覽群組，另以系統管理承載系統子頁；呈現分組不改寫後端 key 或領域責任。個股 Detail 是共用呈現入口，仍以各自 source kind、source workspace、版本／日期與有效上下文隔離來源；相同股票代號不構成跨來源互換。Daily Decision Desk 位於「探索與研究 > 市場總覽」；決策工作台的來源導覽回到同一畫面。操作細節見 [Application Manual V2 導航](../07_guides/APPLICATION_MANUAL.md#v2開發分支導航尚非固定rc)。

首頁明選 Paper 健康部位的 Source 接線沿同一工作區系統，以原 read model／唯一部位交接，持倉頁獨立刷新核同版本後才定位；不合併手動帳或代替歷史保存評估。契約見[工作區邊界](current/application_and_workspaces.md#九個頂層工作區)。

首頁較早推薦另沿明選 exact-result 接既有推薦 single-get／候選 Journal，今日日期守衛保持；詳[研究資料流](current/application_and_workspaces.md#九個頂層工作區)，不建立第二套研究保存或推薦管線。

依問題閱讀：[UI 與應用流程](current/application_and_workspaces.md)、[決策、研究與 Portfolio](current/decision_research_portfolio.md)、[資料、保存與 Runtime](current/data_storage_runtime.md)。使用者操作流程以 [Application Manual](../07_guides/APPLICATION_MANUAL.md) 為準。

## 主要資料流

```text
TWSE／TPEX 與其他明示來源
  → data_module/ 的 raw source／SQLite 更新
  → app_module/ provider 與 use case
  → decision_module／analysis_module／backtest_module／portfolio_module
  → DTO、Research Run／Evidence 或受控保存結果
  → ui_qt/ 工作區呈現
```

更新、查詢、推薦、回測與持倉各走明示 application service。Recommendation 與市場 read model 先核對決策日、資料可得日、品質與來源，再交給領域計算；UI 呈現已形成的 DTO，不暗中補資料或重算。保存研究以 manifest、source identity 與原始 bytes 綁定，重讀指定版本，不以最新資料取代舊結果。

配置研究封存的個股路徑共用 Main 注入的 scenario workspace，以帳種、portfolio、artifact 三項參照讀取原帳戶投影；不經目前手動持倉補值。已保存情境可明確追加 typed reference 至既有 Registry SQLite 的獨立配置研究表，正常 Registry 選列以引用 SHA 及原件重新交叉核對再回 Portfolio；不假造回測 metadata 或改舊 run。canonical hash、來源及原時鐘守衛見[決策／研究／持倉分冊](current/decision_research_portfolio.md)。

## 儲存與排程

正式資料路徑以 `data_module/config.py` 的 `TWStockConfig` 為準。`DATA_ROOT` 預設 `F:/Min/Python/Project/FA_Data`，可由 `DATA_ROOT` 覆蓋；主要市場資料庫是 `<DATA_ROOT>/sqlite/twstock.db`。`OUTPUT_ROOT` 也由同一設定管理。SQLite-first 是一般讀取優先序，raw CSV 保留來源、備份及明示 fallback。repo 的大型產出與 pytest 暫存路徑位於 `F:/Min/Python/Project/BaldrStorage`，本機 repo 以 junction 保留既有路徑。

Windows Scheduler 與受控 CLI wrappers 分別執行資料更新、Evidence dry-run 或經批准的工作。Runtime Observatory 只讀 Runtime 與排程狀態，不啟動任務。正式市場資料寫入、Evidence write-mode、策略 lifecycle 與 broker execution 使用分離權限；排程狀態或零錯誤碼不授予產品接受。

儲存、source cutoff、snapshot identity、SQLite 讀寫與 runtime custody 的穩定細節見[資料、保存與 Runtime 分冊](current/data_storage_runtime.md)。

每日新來源保存的小時可用性、批次／版本釘定與來源用途接受依[每日快照契約](../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md)；接入沿既有 data reader／更新服務邊界，隔離抓取成功不等同正常 UI、正式排程或完整產品接受。

Research Lab Registry的雙run期間診斷由application exact reader負責metadata／附件／日曆版本核對，Qt controller只固定選取與背景讀回世代，不擁有PnL計算或來源資格；詳[研究與Portfolio邊界](current/decision_research_portfolio.md)。

日曆用途接受可由正常Main明示的外部SHA固定binding注入；配置只固定既有typed錨點，仍由原表單選exact batch，失敗只隔離daily用途。Main設定副本與worker生命週期見[主程式邊界](current/application_and_workspaces.md#研究畫面與保存身份)。

原next-open執行輸入沿正常保存入口明示寫入additive V3附件，內嵌原V1／V2文件並重用同一Registry staging／CAS／恢復流程；public reader讀回原None／0、有效成本與lot，pair沿原capture比對。V3預設讀前16MiB上限與取消／完整性守衛保留；輸入hash不授金融來源或implementation資格。

日曆完整JSON transport與daily batch沿原calendar parser分層：data保存HTTP完整原件識別，application提供create-only批次與外部manifest／receipt SHA、獨立用途接受錨點的exact reader。原Registry頁可明示artifact或daily source；daily pin固定雙SHA、兩個typed接受錨點與aware cutoff，沿同一pair reader前後讀回。正常Main／fresh已用隔離合成錨點限定驗證，真來源接受與正式Main配置仍缺；批次小時不授歷史PIT／績效資格，詳[每日版本契約](../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md#日曆完整json批次increment21)。

## 重要不變條件

- 不破壞正式 raw source；資料遷移或全量重建走備份、確認及可復原流程。
- 未知或晚於決策日的來源保持 unknown／missing；不得以未來資料回填歷史決策。
- 策略、回測、Portfolio、成本與風控等金融核心使用 Decimal 或整數單位；float 只在隔離的分析／展示邊界。
- UI 不重做領域計算；唯讀畫面不建立資料庫、schema、producer 或 scheduler。
- Replay、OOS、shadow、forward、paper、live 與 production 是不同證據狀態；局部 QA 不代表產品 Gate 通過。
- Investment Advice 不建立 broker order、不自動平倉、不自動 Promote／Demote／Retire。

## 舊書籤導向

以下相容錨點接住曾引用 current 架構內文的連結；穩定細節已整理到主題分冊。逐日增量與驗收流水由文件治理封存副本及對應 QA 收據追溯。

<a id="daily-decision-desk"></a><a id="4-daily-decision-desk"></a>[Daily Decision Desk 工作區與 UI 邊界](current/application_and_workspaces.md#工作區責任)

<a id="homepage-navigation-and-research-context-boundary"></a>[首頁導航與研究 context 邊界](current/application_and_workspaces.md#九個頂層工作區)

<a id="personal-h20-artifact-and-lineage-boundary"></a><a id="ml-lineage-reader-dependency-boundary"></a><a id="natural-maturity-proof-and-model-loader-boundary"></a>[模型研究、來源與證據權限](current/decision_research_portfolio.md#evidence-與模型權限)

<a id="111-immutable-ml-publication-retention"></a>[不可變研究 artifact 與保存身份](current/data_storage_runtime.md#讀寫與保存契約)

---

## 歷史與目標架構

- 日期化架構變更、當時狀態與具名 QA 摘要：`docs/09_archive/documentation_productization_20261012/originals/docs/01_architecture/system_architecture.md` 的原 bytes；效力與替代入口由同批治理 manifest 說明。
- Current → Target 領域背景：[target_system_architecture.md](target_system_architecture.md)。
- Target package、契約、依賴與遷移設計：[FINAL_TARGET_ARCHITECTURE.md](target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)。Target-only 設計不代表 current package 已存在或已完成。
