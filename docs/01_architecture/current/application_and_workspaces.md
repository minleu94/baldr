# UI 與應用流程

儲存維護由 Main 明示盤點邊界：原始碼模式使用 repo 的 `dist` 版本容器；封裝模式使用目前 `sys.executable` 所在套件作單一項目，不向父目錄尋找其他版本。`inspect_storage` 只查三個設定位置的磁碟容量及明示盤點根；共用 4096 項／64 版本上限，內層連結不跟隨。回傳另含盤點位置、可用性與診斷，缺失或不可讀不能當成成功空清單；大小完整性與引用／清理資格分開。此後繼原始碼修復不在固定 e369 EXE，驗證範圍見 [V2 驗收紀錄](../../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md)。

V2 月營收結果的「開啟一般個股研究」由 view 產生不可變的 `RevenueStockResearchOrigin`，核對原來源、query、page request、page 與 row SHA。Main 只將股票及來源識別映射到原 `ResearchStockContextDTO`，一般報告另讀行情，不攜入月營收 facts 或推定其日期。返回只接受仍在當前已核快照的原頁原列，忙碌或身份改變即拒絕；此短期回返不代替收藏跨程序的磁碟原件核驗。

## research07操作邊界增量

V2 後繼 Python 候選以 `ThemeMemberNavigation` 固定已選題材的 snapshot 物件、SHA、成員順序、原選列及 selection revision；Main 核對來源後，Report 的上一檔／下一檔只替換 context 的股票代碼與名稱。行情仍由一般報告 reader 各自讀取，返回不移動原題材選列。換來源、篩選或選列後拒絕沿舊脈絡切股與返回；保存時報告仍不可切股。此接線已通過 QA096 正常 Main 與新程序的成員來回及選列變動拒絕，固定 `2b164aede953` EXE 未含；新 `412ca3e5fe4f` 候選已通過 QA103 包內正常 Main first/fresh，實際接受範圍見 [V2 驗收紀錄](../../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md)。

StockResearchWorkspace的一般查詢動作建立空名稱、無原保存ID／日期／SHA的explicit_latest_stock_research脈絡，由原一般報告service辨識名稱與行情；保存來源重讀仍走原來源。題材清除沿既有generation與worker取消，先處理筆記busy／草稿確認，modal確認後再核generation、snapshot與worker身份；不寫來源或已保存筆記。原價格圖的顯示用SMA邊界見decision_research_portfolio分冊。

本冊描述目前 PySide6 UI 與 application layer 的責任。系統全貌見[目前系統架構](../system_architecture.md)，操作步驟與畫面判讀見[Application Manual](../../07_guides/APPLICATION_MANUAL.md)。工作包完成度仍以 Snapshot 與具名 QA 收據為準。

## 入口與分層

### V2 開發分支導航（尚非固定 RC）

V2 分支的 ProductShell 將入口分為「今日總覽」、「探索與研究」、「我的投資」、「策略實驗室」四個主工作區，另以齒輪「系統管理」提供資料、執行狀態及診斷入口。此為目前導覽層，不取代現有九個頂層工作區契約，也不表示各子頁已完成整合。`main_window_coordinator.py` 將 market、themes、screener、lookup、lists、positions、paper、journal、strategies、backtests、performance、ml、data、operations、diagnostics、storage 等子路由交給既有 Views；PortfolioView 的新分區仍重用原持倉／Paper／Journal 元件與服務。

全域查詢由 `v2_shell.py` 的 Ctrl+K 搜尋列提供。Main 將 `companies.csv` 路徑交給 ProductShell，後者以 `read_stock_search_directory` 背景讀取公司名錄；名稱子字串或代號命中時，選單最多列 20 筆公司候選，明選後開一般個股資料。4–6 位數字代號也可直接明選一般可用資料。題材名稱、產業鏈及映射內股票則另由目前已載入的題材映射提供，題材選取攜帶版本身份；載入失效或版本改變時拒絕舊結果。名錄僅提供搜尋定位，不代表行情或歷史資格。一般報告與價格研究保留不同來源身份，日期／來源分開呈現，不以相同代號作資料拼接。

個股詳情的 Alt+Left 沿原來源返回，並經既有來源上下文守衛核對身份；若原身份失效則不應回訪錯誤來源。主視窗寬度約 1280 像素時左側 rail 自動收合。今日總覽使用原 Workbench readmodel 與元件整理為單一可捲頁，另保留完整工作台及研究證據入口；不建立第二份首頁 readmodel。首頁「最近研究」直接投影同一次 ResearchTimelineView read result，最多三筆，卡片呈現研究類型、代號、保存時間、資料日及摘要；資料日或來源身份缺少時由提示說明原件未提供並引導至研究紀錄核對，並非額外來源欄位。卡片讀取失敗或取消時清空，late result 由 generation 守衛拒收；mount ownership 保證沿用同一時間軸 view 與讀取結果，不另造 read model。按「開啟研究紀錄與覆盤」以同次結果的 entry 物件身份選取原項目；若 entry 已過期即拒絕，不以相同 ID 搜尋或替換新版本。Stock Research 以明確動作切換研究內容、保存判斷及成果追蹤，仍維持一般報告快照和價格選股來源的不同身份、日期及回訪路徑。

「我的投資 > 自選與名單」把純自選、候選與其他來源、已保存股票代碼清單、保存研究與查詢、來源內比較／返回原研究分區呈現。純自選新增與移除仍經既有 WatchlistService；其他來源及未能核對的舊收藏保留原列與操作。股票代碼清單僅保存代碼，不是研究條件或資料版本快照。保存研究與查詢沿已核對的原來源回訪；來源內比較只把已保存的來源內比較交回原研究，不提供建立或編輯獨立比較清單的功能。

最近研究的一般報告另列「原研究來源日」與「行情日」，後者只從 typed `StockResearchReportNote` 保存快照末筆價格取得，缺件不回填 context 日期。report 具來源日與身份時提供「回訪原報告」：Main 先以同次 entry 物件選取時間軸，再沿既有 `read_original` 背景重核及 canonical snapshot 呈現。detail origin 限定為首頁或時間軸；返回前仍核原件、可見保存快照及目前 origin，過期或晚到結果不套用。QA075 正常 Main fresh 已驗同報告開啟、首頁返回、同卡與 Journal 保持；不新增 readmodel、DTO 或持久化格式。推薦頁延後版面更新由該 View 自有單次 QTimer 執行，成功關閉停止、銷毀時取消，避免 deferred delete 後存取已刪除 viewport；QA073 歷史推薦 first/fresh 自然關閉已驗。

Stock Research 詳情頭部另提供純自選、來源內比較與準備回測。純自選由 Main 重驗目前可見的 `ResearchStockContextDTO` 後，僅以股票代號／名稱寫入預設 Watchlist，不保存研究 Query 或來源 bookmark。比較只接受母體價格選股詳情攜帶的原 `DailyMarketTechnicalUniversePriceSelectionV1`；Main 還會以原價格 view 的當前 query／page 重建 selection 並逐欄比對，通過才將原選列加入其既有比較籃，來源變動則拒絕、不替換其他版本。回測入口僅接受與 workspace 當前 live general report context 完全相同的 `explicit_latest_stock_research` context；`BacktestView.prepare_stock_research` 只切單股模式並預填代號，不保存清單、不帶入原報告價格或啟動執行。保存報告、歷史 context 與原價格來源不符合此入口資格。

目前另有 Research Timeline 的唯讀瀏覽 View、Strategy Library 的唯讀登記／版本 View，以及 Unified Screener 對現有來源計數的跨域狀態呈現。漏斗沒有分母時顯示未提供，不從可見列推算，亦不代表所有條件已接線；策略庫明選 ID／版本不等於回測執行。條件範本只經 V4 View 的 `apply_condition_recipe` 設定既有規則控件，以 AND／單規則符合替換原規則篩選；來源、其他條件與原結果仍保留，須使用者明確查詢。忙碌、未載入或未知方案拒絕，控件訊號不觸發查詢。Timeline 的「回訪原版本」由 Main 對明選 entry 排背景 fresh read，`ResearchTimelineService.read_original` 按 kind 呼叫原 note reader，核對 entry/reference 全欄及重新投影的一致性；price 另 fresh 驗證原 bookmark/source state，report 開保存 snapshot，theme 沿原 manifest identity。核驗失敗或選取／頁面已改時拒絕套用，不回退到同股最新來源；舊首頁 entry 也不能替換成新 entry。題材 catalog 預設只從設定目錄查找最新可讀 `price-v1`；`flow-v2` 保留明選歷史 manifest 的路徑，目錄設定只定位資料，不授予用途或資格。Storage 只盤點具名位置與有界 Trial 容量，引用未核一律保留，沒有刪除操作。QA023／024 分別核實一般報告與題材筆記的正常 Main 保存／新程序讀回；這些增量仍屬 V2 開發分支，尚無固定 RC、真人或完整五旅程驗收結論。

```text
使用者
  → ui_qt/main.py（視窗、工作區、表單與呈現）
  → app_module/（use case、service composition、DTO、repository）
  → decision_module/、backtest_module/、portfolio_module/、analysis_module/
  → data_module/（來源、reader、writer 與市場資料保存）
```

Windows 由 `baldr_launcher.py` 啟動；source 與 frozen 執行都交給既有 Qt composition。`ui_qt/main.py` 建立視窗與 widget，`app_module/` 的 composition factory 建立服務並以 DTO／明示 provider 注入 UI。Domain 與 Runtime 不反向依賴 Qt。

巢狀研究分頁共用`layout_helpers.CurrentPageSizeTabWidget`，只依作用中頁的自然高度配置外層捲動；Recommendation原私有類名保留相容別名。價格頁只在外層可捲宿主保留表格下限，獨立宿主的零尺寸延後還原守衛保持。F07收藏回訪沿同次verified state還原原頁後，用原選列開同源個股，不改讀一般價庫。

Watchlist的名稱查詢可從目前行情及`meta_data/companies.csv`讀唯一精確名稱，只作展示；清單及typed收藏的原名稱／身份／hash不重寫。此顯示補充不證名冊用途、來源clock、真N或歷史PIT；缺名維持未提供。

固定Windows候選由commit archive建置，不與工作目錄拼接來源；執行收據需讀的raw sources由spec明示datas，metadata逐檔核資源身份。兩原策略v2另帶executor／wrapper三檔，AST只解析literal宣告而不執行spec；缺檔／partial拒建metadata，舊四來源版本不追補hash。包與固定export、正常Native保存／fresh及金融投影各別核驗，細節見[研究邊界](decision_research_portfolio.md#模組責任)與[候選指南](../../07_guides/PORTABLE_WINDOWS.md#試用回報修正預覽increment59)。

## 九個頂層工作區

固定研究11在原題材頁加入可收合的全產業鏈卡片目錄，僅投影既有ThemeResearchPresentation.chains。卡片題材捷徑由Qt具名slot讀建立時的snapshot identity與原chain/theme，通過當前identity／忙碌／關閉守衛後沿原篩選器定位；不另開工作區或查來源。名稱序前三項不是金融排名，完整覆蓋與有限Decimal顯示守衛保持；固定10未含此UI增量；固定11的同版EXE與新程序限定證據見QA215–219a。

後繼Source的「市場探索 → 產業與題材」重用同一市場分頁及`ResearchStockContextDTO`，由application層讀明選的本機snapshot與聚合。載入開始即清除舊可操作來源；成員下鑽攜原manifest身份與資料日，返回前核同一身份並保留原view篩選／捲動。一般個股價庫與題材版本各標日期，不將兩份行情混接。原萃取模組與143固定包不改；契約與驗證狀態見[每日題材研究](../../02_features/INDUSTRY_THEME_MAP_DESIGN.md#53-後繼每日研究實作2026-10-18)。

首頁題材入口只選回上述現有widget，接收snapshotChanged作短摘要；不重讀來源。個股以明確current_stock_research讀一般行情，題材日期／hash只作原探索脈絡；換股必須回題材明選。研究判斷以既有Journal追加，保存時鐘與資料日分開，新程序回訪核原文與原SHA。

首頁候選沿原 selector／context，控制項移至日常候選列下方，保留結果、快照及日期；返回要求同一原首頁身份。較早候選不放寬今日 guard，而以明示按鈕交 Main 呼叫 `RecommendationView.open_saved_recommendation_result(result_id)`，排入既有 single-get worker 後才切推薦工作區。它不經整體 list／latest，不產製推薦；canonical 身份、matching pointer 日期／筆數、generation／取消及關閉守衛保持。筆記沿原 candidate Journal，與整份報告保存分開。

市場探索的保存來源 backend 提供明確 opt-in 的 Projection Group V3 opener：同一次 verified-parent callback 產生 MA／KDJ／volatility／F07 Decimal price facts，完整 exact cohort 核對後才發行 session，price digest 進入 group identity。V2 opener 與既有價格分類沿原契約；V3 不另讀價格母體，也不自行接 UI、query predicate 或 bookmark。實際驗證與未完成範圍見[本輪補完 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。

1. 決策工作台
2. 市場探索
3. 推薦分析
4. 策略回測／Research Lab
5. 觀察清單
6. 個股研究
7. 持倉管理
8. 數據更新
9. Runtime Observatory

Daily Decision Desk 沒有第二個頂層 widget；它位於「市場探索 > 市場總覽」，決策工作台的「決策來源」只導向同一個畫面。`StockResearchWorkspace` 是主視窗中的單一工作區，會以明示的研究 context 在報告、結果與來源之間導覽。

Source 候選另有首頁明選 Paper 健康列的同版本導覽：Workbench 將既有 `PositionHealthReadModel` 與唯一 `position_id` 交給 Main，持倉頁先排入下一次刷新，再由自己的 reader 核對完整同版本及該部位，才切 Paper 帳與健康列。來源變更、失敗或過期回呼不回退手動帳同股；返回「決策工作台」沿既有工作區保留首頁上下文，不自動刷新。這條路徑不建立帳本、不產製評估，也不取代歷史 exact receipt 重開；驗證界線見[QA108／112](../../06_qa/BALDR_THEME_DAILY_QA_20261018.md#首頁-paper-同版本部位導航qa108112)。

<a id="daily-decision-desk"></a>
<a id="4-daily-decision-desk"></a>
## 工作區責任

| 層 | 主要責任 | 不負責 |
|---|---|---|
| `ui_qt/` | 收集參數、送出 application 請求、顯示 DTO／圖表／狀態、工作區導航及 worker lifecycle | 評分、策略、撮合、資料資格判斷與直接維護正式資料 |
| `app_module/` | 組合 use case、選擇來源、整理 DTO、管理保存流程與服務協調 | 持有 UI 狀態或複製領域計算 |
| `ui_qt/workers/` | 在背景執行長任務，回報進度及結果；透過取消與請求世代拒收過期結果 | 成為資料或決策權威 |

View 只把已驗證的 application 結果投影到畫面。來源、時間、狀態不明時保留 unknown／degraded；呈現層不補值、不把研究訊號升級為正式 Advice。

## 主要資料流

### 更新市場資料

```text
數據更新工作區
  → UpdateService／來源更新服務
  → TWSE、TPEX 或其他明示來源
  → raw CSV／市場 SQLite sync
  → 技術指標 job（由父程序單一 writer 發布）
  → 更新結果 DTO 與來源品質提示
```

更新步驟與錯誤處理由 `app_module/` 的服務與 `ui_qt/views/update/` coordinator 分工；UI 收集日期、來源與選項，不能繞過明示 write path。狀態與詳情查詢保持唯讀，SQLite 不存在或不可讀時顯示 diagnostics。

### 市場觀察與推薦

```text
既有 market frame／來源 observations
  → application composition 與 RecommendationService／ScreeningService
  → decision_module 的 regime、screening、scoring 與 reasons
  → recommendation／Decision Desk DTO
  → 市場探索、推薦分析與 Workbench 呈現
```

服務先依決策日、資料可得日與來源資格界定輸入，再執行計算。Recommendation 結果保存來源、設定、母體與負面證據 metadata；畫面、報告與重開都讀取已產生或已保存的 DTO，不在 UI 重新評分。

### 研究與持倉

回測、批次、最佳化、Walk-forward 與推薦組合回放由 application service 協調 `backtest_module/` 與既有策略；UI 呈現結果或提交保存請求。持倉管理把手動帳務、使用者聲明研究持倉與 paper research lane 分開；名稱相似不代表來源身份可互換。見[決策、研究與 Portfolio 分冊](decision_research_portfolio.md)。

Portfolio 的「配置研究封存」沿 Main 中央私人 store route 注入既有情境 repository；明選帳種／帳本／artifact 後可重開、研究新 target 及另存。這條舊證據研究路徑與當前手動帳刷新獨立，返回個股核同 artifact，worker 於 native finished 後才釋放；操作與未完成界線見[手冊](../../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md#配置研究封存與另存假設)。

Research Lab 的 Paper 保存快照查找使用可選的外部 artifacts root；根目錄未設定或無效時，只停用 Paper 查找，不阻斷其他研究工作。版本來源沿用 Research Lab 的策略版本選取，查找仍需明示策略、版本、帳戶命名空間及含時區的截止時間，不自動改選最新版本。查找先列出最多 200 筆有限候選並明示截斷，再由使用者選取保存快照讀回卡片；不自動挑選最新項目、不建立或更新保存資料，也不授予候選驗證或績效資格。關閉工作區時會合作式取消未完成查找，並拒收過期回覆。

## 研究畫面與保存身份

價格選股在正常Main的下鑽沿既有PriceV1 reader-issued stock與selection：`DailyMarketResearchView`通過原query／頁核驗後發`priceStockResearchRequested`，Main呼叫`StockResearchWorkspace.show_price_research`，不轉成一般report context或查最新價庫。既有詳情視圖核stock／row／snapshot／source／選取身份，僅把最多120列保存OHLCV投影到原圖表與明細；五規則與unknown照原件呈現。工作區以stack隔離一般報告／H20和原價格來源，返回由`restore_price_research_origin`沿原`restore_origin`恢復頁與選取；非Main宿主保留dialog。未修改來源、保存schema、指標計算、來源用途或歷史PIT，工程驗證見[Increment118](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment118-price-stock-workspace)。

F07後續Source在Main組裝時，將同一`PinnedStockResearchNoteService.source_read_scope`交給收藏controls與價格view。factory於排程前擷取，僅在原full-reader worker內啟用；錯誤／取消亦退出範圍，generation／選取／晚到／關閉守衛不變。查詢、翻頁與單股投影不新增scope。這只重用repository發行的有界語義證明，每次原件仍fresh，新程序冷驗；完整旅程與固定包界線見[QA163–168](../../06_qa/BALDR_THEME_DAILY_QA_20261018.md#f07語義證明範圍qa163164)。

Main的日曆接受配置沿原`ApplicationSettings`→BacktestView→result_panel→Registry controller。明示外部path／SHA只載入已有的兩市場typed用途接受，來源家族在binding與pin分別核對；不讀batch、不自建接受或選latest。Main複製caller設定並固定本視窗接受tuple；缺設定或讀取失敗只停用daily用途，錯誤跨模式保留。原worker native-finished、世代／pin／metadata重驗及關閉取消流程不變。配置與時間契約見[每日來源契約](../../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md#tpex年度股票日曆候選解析)。

市場研究畫面消費具來源版本、日期、母體、方法與 hash 的 snapshot／manifest。Daily Research、候選摘要、研究書籤與跨頁投影沿同一已核驗來源和 query；readback 按保存的 source identity 重開，不搜尋 latest、不在 UI 重算指標或重新執行 producer。來源缺件、修訂、方法不相容或日期不可判定時保留 unknown／拒絕，不能套用舊投影或改讀一般即時行情。

原生個股排名是獨立研究來源，須以已驗證的 feature snapshot 與明示母體作 parent。原排名發布者、reader、每日研究 consumer 與 pinned 個股 context 保留同一 manifest／artifact 身份；版本化收藏保存方法、比較窗、母體、排序與所選股票。舊 v1 收藏維持原 bytes／identity 語意，rank context 走明示 v2。另開 latest 個股研究是不同路由，不改寫原收藏；收藏也不造新的 Recommendation `result_id` 或持倉 ledger。

保存母體的多 artifact reader 只有在呼叫端明確 opt-in、且原 TaskWorker 能發行綁定原 worker／取消 event／callback／執行緒的一次性能力時，才可使用合作式取消 probe。能力 claim 只可成功一次；callback、執行緒或封印不符時不提供 probe，該次 claim 已消耗並退回序列讀取。只有明確支援此能力的 task 可取得它；取消 callback 存在但 reader 沒有該能力時不得平行讀取。合格讀取最多保留 8 個未完成 future，結果與回呼依原 artifact index 順序消費。取消或錯誤時停止提交後續工作，並等待已啟動讀取自然收尾；不強制終止 worker／future，也不把取消當成 rollback。

固定篩選 preset 和 multi-method summary 是唯讀投影，只讀已發布候選與完整 declared denominator，不新增資料來源、打分方法或正式資格。現行條件若來自同一方法家族，不按不同均線數量冒充獨立證據家族；跨來源／跨方法資料不足時留 unknown。使用者確認後才可把來源和 query 存入既有收藏；單純套用 preset 不改變收藏的方法身份。

保存的 Recommendation 圖表使用原次 request 的 prepared market frame、選中範圍與同次指標，不讀最新行情、不補算缺失均線。Stock Research 的切股、返回及 viewport 投影都要先核 source/context/generation identity；來源變更或過期 worker 回應不能覆蓋目前選取。共用狀態顯示 helper 只翻譯已知狀態，未知值保留原碼與明細，不改 DTO/domain 資格。

## 邊界與導覽

技術封存恢復沿 `technical_source_copy` 的closed映射及原strict reader。恢復期間可保留初次完整SHA已驗的原件bytes，每檔最多256KiB、總計最多384MiB且不超過原複製預算；中途讀取仍核預期SHA與身分，開始寫入前及發布收據前重新從實體來源／目的讀取完整清冊與SHA。一般複製與收藏的封存檢查預設不保留這些bytes；不增加I/O執行緒、程序或Root Job上限。這是既有首次設定的內部讀取修正，是否解除600秒阻礙另依[具名QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment140-archive-byte-reuse)，不授整包可攜或P14接受。

`trial_first_setup`保留v1讀取，v2才允許明選月營收封存及單一市場狀態歷史原件；兩者沿原件SHA複製，不接評分或重建原數值。來源及資料副本於設定發布前再核，預設正式根的拒寫不因DATA_ROOT環境值消失。provider專用key不寫入共同config，由啟動器明選環境；月營收資格及可得小時仍由原個股public reader裁決，首次設定的bytes核對不替代來源接受；固定包實際出口見[141 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment141-full-trial-exe)。

- QWidget 不直接查詢 Runtime store；Runtime Observatory 顯示透過 application／Runtime DTO 注入的狀態。
- 保存後重新開啟結果時，應按保存 identity、版本與 source pins 讀回，不隱式改讀最新資料。
- 產品操作與安全限制以 Manual 為準；架構契約不代表按鈕已開啟、資料來源已接受或 Gate 已通過。
- 舊相容錨點 `system_architecture.md#4-daily-decision-desk` 仍由目前架構首頁導向本節。

P02補完候選在推薦結果來源分頁新增「官方條件與價格研究」，保留既有官方市場條件頁與V1收藏。新頁使用同一sealed V3 group的四組與價格facts，價格作共通AND、全域排序後分頁；Main按V1/V2 typed envelope選相對應的Watchlist writer／reader與頁面，拒絕restore時保持目前workspace。指定合成257股／雙parent的Main父→新PID已有限驗證，來源／歷史PIT／真N／Native／EXE及完整Gate另判。操作見[官方條件與價格研究](../../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#官方條件與價格研究)，證據見[本輪QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。

題材頁後續Source的股票反查只使用已讀snapshot.mapping與既有成員索引；選項攜snapshot identity／股票／鏈／題材，定位核同版本及成員代號後沿原stockSelected。公開signal、DTO、Main與reader不改；不新增來源查詢或跨版本快取。
