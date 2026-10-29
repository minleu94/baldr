# 產品與個股研究 QA 索引

[共用子頁導覽響應式排列（2026-10-29）](BALDR_UI_PRESENTATION_REVIEW_20261028.md#2026-10-29-第七輪共用工作區子頁導覽響應式排列)：寬版單列、中窄版雙欄、極窄版單欄，保留 route 選取。子頁／ProductShell 回歸 24 passed，py_compile 與 targeted mypy 通過；原生 GUI／Owner UAT 待確認。

[個股研究導覽與這檔操作分組（2026-10-29）](BALDR_UI_PRESENTATION_REVIEW_20261028.md#2026-10-29-第六輪個股研究導覽與操作分組)：完整名稱區分頁面導覽和股票操作，寬版保留報告首屏位置、窄版上下排列；相關回歸 14 passed，2 個來源 fixture 因 sandbox `WinError 5` 未能啟動。

[Recommendation 結果表初始欄寬（2026-10-28）](BALDR_UI_PRESENTATION_REVIEW_20261028.md#2026-10-28-第三輪recommendation-結果表初始欄寬)：理由欄初始 260 px，可拖曳；長文改由詳情／提示閱讀。推薦版面與保存讀回 16 passed；推薦投資組合結果測試遇 Qt WebEngine Windows fatal exception，未完成。尚待原生 GUI／Owner UAT。

[Storage overview 分區與欄位可達性（2026-10-28）](BALDR_UI_PRESENTATION_REVIEW_20261028.md#2026-10-28-第五輪storage-overview-分區與欄位可達性)：容量與明示根盤點分區，摘要位置／項目數；窄窗只在欄位溢出時水平捲動。版面 4 passed；原 worker 測試被 sandbox 目錄掃描拒絕（`WinError 5`），提權重跑受 QA 鎖讀取權限阻擋，尚待可驗證環境完成 worker 回歸。

[每日市場研究結果清單分組（2026-10-28）](BALDR_UI_PRESENTATION_REVIEW_20261028.md#本輪已修正)：代號搜尋、狀態篩選、列數摘要、排序與原始排名控制集中於表格前；快照更新／重讀保留獨立操作列。每日研究條件回歸 4 passed；原生 GUI／Owner UAT 待確認。

[研究時間軸清單與查找分組（2026-10-28）](BALDR_UI_PRESENTATION_REVIEW_20261028.md#本輪已修正)：來源、股票／result ID 搜尋集中於「查找已保存研究紀錄」；清單及選取紀錄詳情各有明確標題。研究時間軸 UI 回歸 17 passed；原生 GUI 窄窗驗收待確認。

[Update 狀態卡長文字換行（2026-10-28）](BALDR_UI_PRESENTATION_REVIEW_20261028.md#本輪已修正)：額外來源資訊允許在窄卡片換行並收縮；必要 Update UI 回歸 98 passed。

[排程成熟分布輔助字級（2026-10-28）](BALDR_UI_PRESENTATION_REVIEW_20261028.md#本輪已修正)：圖例、計數與未知訊息由 8 pt 提至 9 pt；聚焦 UI 回歸 60 passed，原生字型／DPI 待確認。

[題材成員卡片響應式網格（2026-10-29）](BALDR_UI_PRESENTATION_REVIEW_20261028.md#本輪已修正)：預設卡片依寬度排 1／2／3 欄，避免每頁 50 位全數直向堆疊；題材頁 UI 62 passed，Main 成員導覽 8 passed。

[Baldr 全工作區資料呈現與響應性盤點](BALDR_UI_PRESENTATION_REVIEW_20261028.md)：Workbench Advice 長判讀改為可捲動文字窗、個股研究摘要移除窄窗高度裁切；另分級列出市場研究、時間軸、Smart Money、Recommendation、Backtest、Storage、Update 與排程頁的改善候選及尚未量測的風險。使用者旅程補充新增 Advice 同筆來源直達、每日來源分段與研究歷史 ID 導覽；Smart Money 摘要／控制換列 36 passed；Advice／每日旅程／Research Timeline 64 passed，MainWindow 跨頁路由 1 passed，必要 Workbench Update UI 98 passed，核准後 Update validator 25 passed／0 failed／4 skipped；repo-wide mypy 受未修改 T164 bridge 語法錯誤阻擋。原生 GUI／Owner UAT 未執行。

[產業題材頁探索、卡片與版本選擇](BALDR_THEME_PAGE_EXPLORATION_ORDER_20261028.md)：題材排行與成員預設卡片、九項指標卡預設顯示，完整表格保留切換／展開；版本選擇改為頁內已核驗清單，載入時沿 manifest SHA 重讀。版本選擇、題材頁及入口回歸 UI 79 passed；snapshot catalog 10 passed／1 skipped；開發版實際清單驗證得到 1 個可讀版本（2026-10-16 price-v1），2026-10-19 flow-v2 因其依賴路徑超出明選版本庫而拒絕。Targeted mypy／py_compile 通過、Update validator 25／0／4。完整更新頁 UI 本輪 21 passed／76 failed（未修改的 `update_view.py` 缺少 `_choose_monthly_revenue_snapshot`）；repo-wide mypy 仍受未修改 T164 bridge 第 411 行語法錯誤阻擋。原生 GUI／Owner UAT 未執行。

[Gate 1 日常 Advice 與保存讀回](BALDR_GATE1_DAILY_E2E_20261028.md)：Workbench Advice 人工決定寫入隔離 journal，fresh controller 精確讀回；真 MainWindow 保存推薦跨頁讀回通過。正式推薦／排除事件同屬 `rec_bc108d4d483a46f4bd758706e6fb8d37`，但 snapshot 為 estimated／research-only、screening 品質 missing、無 formal credit；當前 Workbench 是否讀此正式快照與 Owner UAT 未驗。受控 runner 的 `busy_close` case 未通過。

[Workbench Advice 逐股比較資訊](BALDR_WORKBENCH_ADVICE_COMPARISON_FIELDS_20261028.md)記錄保存推薦比較欄位、逐股證據及圖卡易讀性改善：一般桌面雙欄、完整判讀可捲動，展開讀取不阻塞 UI。視覺調整前的比較欄位聚焦 tests 139 passed；本輪 Advice contract suite 16 passed，必要 Workbench UI 98 passed，Update validator 25／0／4；其他驗證與未驗證界線見該報告。

[可比產業超額圖卡清晰度](BALDR_INDUSTRY_STRENGTH_CARDS_20261028.md)記錄 3／2／1 欄產業小卡、明示相對基準方向、成分資料覆蓋率、期別 hover 與卡內詳情。Decision Desk／必要 Workbench UI 152 passed、Update validator 25 passed／0 failed／4 skipped、定向 mypy、py_compile、原生主程式畫面確認通過；repo-wide mypy 仍被未修改 T164 bridge 第 411 行語法錯誤阻擋。原生視窗載入快照品質降級；固定舊 EXE 與 Owner UAT 未驗。

[Gate 1 Advice 解鎖](BALDR_GATE1_ADVICE_UNLOCK_20261027.md)：策略升格、參數鎖定、揭露與作者契約不再作 Advice 輸出 Gate；未升格 Advice 保留限制提示。聚焦 suite 253 passed，1 項既有 MainWindow ML registry 初始化測試失敗／排除；必要 Workbench UI 97 passed、Update validator 25 passed／0 failed／4 skipped、py_compile 通過。全域 mypy 受未修改 T164 bridge 第 411 行語法錯誤阻擋；未驗正式資料端到端與原生 GUI／Owner UAT。

[Workbench Advice 摘要與候選卡](BALDR_WORKBENCH_ADVICE_CARD_LAYOUT_20261027.md)記錄 Advice／未升格 Advice／配置列數摘要、寬版三欄／中版雙欄／窄版一欄逐列網格、編號理由及點卡原地展開。聚焦 suite 99 passed，必要 Update UI 97 passed、validator 25／0／4、targeted mypy／py_compile 通過。Repo-wide mypy 受未修改 T164 bridge 語法錯誤阻擋；Offscreen fallback 字型無法供中文字體視覺判讀，原生 GUI／Owner UAT 未驗。

[Workbench Advice 快速判讀與窄版欄位](BALDR_WORKBENCH_ADVICE_QUICK_READ_RESPONSIVE_20261027.md)記錄 864 px 截圖中固定欄寬讓理由摘要只剩約 32 px，以及來源缺值與零配置列的語意；窄版收合風險／資料狀態欄、寬版恢復，並補上候選用途說明。Advice／契約聚焦測試 65 passed／4 failed（失敗為目前工作樹的範圍外舊斷言／導覽回歸），必要 Update Workbench UI 97 passed、Update validator 25／0／4、targeted mypy、py_compile 與 diff check 通過；全域 mypy 仍受既存 T164 bridge 語法錯誤阻擋。Offscreen 欄位切換通過；原生 MainWindow／Owner UAT 未驗。

[策略庫保存版本背景讀取](BALDR_STRATEGY_LIBRARY_RESPONSIVE_VERSION_LOAD_20261027.md)記錄保存版本檔讀取移出 Qt UI 執行緒、載入／錯誤／重試狀態、單一 latest-only 佇列及舊回覆拒收。聚焦頁面與必要 Workbench UI 回歸、Update validator、定向 mypy 與 py_compile 結果按該報告判讀；阻塞合成 reader 確認 UI 事件迴圈仍能響應。沒有宣稱底層版本全目錄掃描更快、正式版本數量或 DannyQuant 端到端速度相同。

[Research Timeline Journal 歷史快照重用](BALDR_RESEARCH_TIMELINE_JOURNAL_SNAPSHOT_REUSE_20261027.md)記錄四個唯讀 lane 共用一次 Journal JSONL 讀取、錯誤回退與單 lane 隔離；214 項時間軸／typed note／Journal storage／Workbench regression、6 模組 targeted mypy 與 10 檔編譯通過。6,000 筆合成 JSONL、offscreen Qt 的 30 次交替樣本 p50/p95 為 610.6/737.5 ms→335.1/436.3 ms，輸出 digest 相同、檔案讀取 4 次→1 次；不代表正式資料、原生繪製或 DannyQuant 網站速度。

[DannyQuant 公開頁面參考](BALDR_DANNYQUANT_REFERENCE_20261027.md)記錄公開可見的名單範圍／篩選／資料完整度標籤，並明示沒有可重複的外部完成事件，故不宣稱網站速度對比。

[Daily Research 局部篩選摘要](BALDR_DAILY_MARKET_RESEARCH_FILTER_CLARITY_20261027.md)記錄符合列／核驗列總數與作用中條件；4 項頁面測試及必要 Workbench UI 97 項通過，Update validator 25／0／4、4 模組 targeted mypy 與 8 檔編譯通過。全域 mypy 受未修改 T164 bridge 第 411 行語法錯誤阻擋；原生 GUI／Owner UAT 與正式資料延遲未驗。

[個股研究代號／名稱搜尋](BALDR_STOCK_RESEARCH_NAME_SEARCH_20261027.md)記錄目前公司名錄內的名稱片段搜尋、唯一結果確認、多筆／無結果提示與原來源身份守衛；個股研究 89 passed、必要 Workbench UI 97 passed、Update validator 25／0／4、targeted mypy、4 檔編譯與 scoped document-control 通過。Repo-wide mypy 受未修改 T164 bridge 第 411 行錯誤阻擋；未走原生 GUI／Owner UAT，也未量正式名錄或端到端延遲。

[Smart Money 事件日期索引重用](BALDR_SMART_MONEY_EVENT_DATE_REUSE_20261027.md)記錄已驗證來源順序的解析／排序捷徑與不確定來源的安全回退；57 項相關測試通過，14,400 筆合成事件 digest 相同，60 次交替樣本的 p50／p95 皆改善。這只量預載事件語意整理，不代表資料庫、Worker 或 UI 端到端延遲；repo-wide mypy 仍被未修改 T164 bridge 第 411 行阻擋。

[強勢個股逐列行情日](BALDR_STRONG_STOCKS_ROW_MARKET_DATE_20261027.md)記錄各列保留其選中來源行情日，與 DTO 整體資料日分開；22 項回歸、必要 Workbench UI 97 項、Update validator 25／0／4、targeted mypy 與編譯通過。全域 mypy 仍被未修改 T164 bridge 第 411 行阻擋；正式資料端到端延遲及原生 GUI／Owner UAT 未驗。

[市況總覽窄版響應式版面](BALDR_MARKET_REGIME_RESPONSIVE_LAYOUT_20261027.md)記錄 820 Qt logical px 以下由左右 3:2 切換上下順序，並在 560／720／1280 寬度確認來源條件欄可讀、寬版比例恢復及內容狀態不變。市況總覽 14 passed、必要 Workbench UI 97 passed、Update validator 25／0／4、定向 mypy、兩檔編譯與 scoped diff check 通過；全域 mypy 仍被未修改 T164 bridge 第 411 行語法錯誤阻擋。Scoped document control 有 4 個既有 Snapshot 錨點、task-wide 有 63 個既有連結／錨點問題，本次新增 QA 連結未列缺件。Offscreen 證據不代表原生 GUI／Owner UAT，也沒有 Danny Quant 延遲比較。

[TAIEX 歷史頁合成資料端到端延遲基線](BALDR_TAIEX_HISTORY_LATENCY_BASELINE_20261027.md)記錄實際 `TaiexHistoryView`／`TaskWorker` 以唯讀合成 SQLite 載入 120 筆歷史資料的 30 次量測：刷新呼叫至圖表 Paint p50 8.2659 ms、p95 8.6771 ms，DTO 與可見狀態 35 次一致。沒有改 SQL 或索引；正式資料、MainWindow 導覽和原生螢幕呈現未測。

[強勢個股目前清單本機搜尋](BALDR_STRONG_STOCKS_LOCAL_SEARCH_20261027.md)記錄原全市場模式的代號／名稱搜尋、僅代號的研究快照投影提示、目前已載清單筆數及未載入／空清單／零符合區分；原表排序與共用快照查詢不受影響。強弱勢 UI 與共享消費者 18 passed、必要 Workbench UI 97 passed、Update validator 25／0／4、targeted mypy／compile 通過；repo-wide mypy 受未修改 T164 bridge 第 411 行語法錯誤阻擋。Changed-path document control 回報 Snapshot 四個既有日期化錨點；本輪新增連結未列缺件。未驗原生 GUI／Owner UAT 或正式資料端到端延遲。

[Daily Decision Desk 資料脈絡優先版面](BALDR_DECISION_DESK_EVIDENCE_FIRST_LAYOUT_20261027.md)記錄總覽中的評估／判讀日、來源市場資料日、整體 quality 與警示摘要移至今日主結論之前；保存推薦與完整警示維持唯讀。Decision Desk UI 54 passed、必要 Workbench UI 97 passed、Update validator 25／0／4、定向 mypy、編譯與 diff check 通過。全域 mypy 被未修改 T164 bridge 第 411 行阻擋；未做原生 GUI／Owner UAT。

[Portfolio 交易歷史背景載入](BALDR_PORTFOLIO_TRADE_HISTORY_ASYNC_20261027.md)記錄自動刷新／股票篩選在背景讀取與建表、GUI thread 套用模型、快速換選丟棄舊回覆及同篩選暫留快照狀態。Portfolio UI 110 passed、必要 Workbench UI 97 passed、Update validator 25／0／4、targeted mypy／編譯／diff check 通過；repo-wide mypy 受未修改 T164 bridge 第 411 行語法錯誤阻擋。未驗正式帳本 latency、大量交易欄寬／繪製或原生 GUI。

[強勢個股背景載入與資料日](BALDR_STRONG_STOCKS_ASYNC_LOAD_20261027.md)記錄來源讀取移至受管背景 worker、GUI 執行緒更新模型、週期切換丟棄過期結果，以及 `effective_date`／快取資料日呈現。聚焦 UI 11 passed、共享市場消費者回歸 6 passed、必要 Workbench UI 97 passed、Update validator 25／0／4、targeted mypy／編譯／diff check 通過；repo-wide mypy 受未修改 T164 bridge 第 411 行語法錯誤阻擋。Scoped document control 回報 Snapshot 原有四個日期化錨點，全庫共 63 個既有文件問題；新增文件連結未列缺件。未量測正式資料端到端延遲或走查原生 GUI。

[強勢個股資料日呈現](BALDR_STRONG_STOCKS_EFFECTIVE_DATE_20261027.md)記錄強勢股頁保留 DTO `effective_date`、週期快取續顯原行情日，以及 missing date 明示。聚焦強弱勢 UI 9 passed、必要 Workbench UI 97 passed、Update validator 25／0／4、targeted mypy／編譯／diff check 通過；repo-wide mypy 受未修改 T164 bridge 第 411 行語法錯誤阻擋。Document control 的四個 changed-scope 錯誤是 Snapshot 既有錨點，新增 QA／手冊連結無缺件；全域另有既存 `output/` 越界連結。未驗原生 GUI／Owner UAT 或正式資料端到端延遲。

[Watchlist v3 revision cursor inventory](BALDR_WATCHLIST_REVISION_CURSOR_20261027.md)記錄保持全庫完整性驗證的 cursor 讀取、輸出與 late-corruption error-code 等價，以及 1,800 revisions／3,607 rows 合成 DB 的記憶體與延遲結果。27 項 storage tests、targeted mypy、編譯與 diff check 通過；repo-wide mypy 仍被未修改 T164 bridge 第 411 行擋住，document_control 有 63 個既有連結問題且新連結未列缺件。只確認約 1.34 MB peak allocation 減少，未證明正式 DB／端到端讀取延遲改善。

[個股研究歷史持倉警示摘要轉換量](BALDR_STOCK_RESEARCH_ALERT_SUMMARY_20261027.md)記錄只轉換第一筆符合事件的 helper 微基準，並核對摘要文字完全相同；個股研究 UI 82 passed、必要 Workbench UI 97 passed、Update validator 25／0／4、目標模組 mypy、編譯與 diff check 通過。全域 mypy 仍被未修改 T164 bridge 第 411 行既有語法錯誤阻擋；document_control 回報 63 個既有連結／錨點問題，本輪連結未列缺件。微基準不代表整頁或正式資料延遲；未驗原生 GUI／Owner UAT。

[Research Registry 背景載入與本機篩選](BALDR_RESEARCH_REGISTRY_ASYNC_LOAD_20261027.md)記錄首次載入／手動刷新改由背景 TaskWorker 執行、篩選重用已載入快照及載入／錯誤／符合筆數呈現。聚焦 UI 53 passed、必要 Workbench UI 97 passed、Update validator 25／0／4、兩個變更 UI 模組 targeted mypy 與 4 檔編譯通過；全域 mypy 仍被未修改 T164 bridge 第 411 行既有語法錯誤阻擋。未驗原生 GUI／Owner UAT，未量正式資料端到端延遲。Scoped document_control 仍回報 PROJECT_SNAPSHOT 四個既有錨點錯誤及 decision/research 分冊一個既有 `output/` 連結越界；本輪新增文件連結未列缺件。

[Smart Money 主表範圍搜尋](BALDR_SMART_MONEY_SCOPE_SEARCH_20261027.md)記錄目前已載入列內的代號／名稱搜尋、符合數與品質摘要、空狀態區分及隱藏選取列後清除明細。聚焦 Smart Money 28 passed、必要 Workbench UI 97 passed、Update validator 25／0／4、targeted mypy 與 compile 通過；指定全域 mypy 仍受未修改 T164 bridge 語法錯誤阻擋，原生 GUI／Owner UAT 未做，不宣稱正式資料延遲改善。

[Smart Money 主表欄寬重複量測快取](BALDR_SMART_MONEY_COLUMN_MEASUREMENT_20261027.md)記錄 1,600 列合成 offscreen 微基準：後續同模型 fit p50 由 47.3499 ms 降至 0.0107 ms，欄寬不變；首次 fit 約 50 ms，非端到端 UI 延遲。Smart Money view／async 26 passed、Update validator 25／0／4、targeted mypy 與編譯通過；必要 Workbench suite 55 passed、2 failed，Advice 測試失敗仍使 UI 回歸 Gate 待處理。未驗原生 GUI／Owner UAT。

[Watchlist 顯示名稱歷史列查詢優化](BALDR_WATCHLIST_DISPLAY_NAME_QUERY_20261027.md)記錄索引條件下按請求代號取得最新非空名稱、舊 schema fallback 與唯讀測試；聚焦測試 2 passed，契約測試檔 22 passed、targeted mypy／compile 通過。20,000／100,000／400,000 筆合成歷史列上，舊／新查詢 p50 為 1.375／0.722、2.730／0.689、7.105／1.182 ms，輸出 digest 相同；此為 service query 微基準，未測正式 DB／UI／啟動延遲，不能宣稱端到端使用者延遲優於 DannyQuant。

[Watchlist 候選池本機搜尋](BALDR_WATCHLIST_CANDIDATE_POOL_SEARCH_20261027.md)記錄目前已載入列的代號／名稱部分搜尋、符合列計數、重複來源列保留及載入狀態未知語意；Watchlist regression 14 passed。未驗原生 GUI／Owner UAT 或正式資料端到端搜尋延遲。

[Smart Money 主表資料品質摘要](BALDR_SMART_MONEY_VISIBLE_QUALITY_20261027.md)記錄目前顯示範圍內含估算、張數未知與分類未知列數的呈現；25 項 Smart Money 測試、必要 Workbench UI 97 項及 Update validator 25／0／4 通過。全域 mypy 仍被既有 T164 bridge 語法錯誤阻擋；未驗原生 GUI／Owner UAT，資料資格不變。

[2026-10-26 Gate 2 working-copy 與 Gate 3 現況觀測可見性](BALDR_GATE2_WORKING_COPY_AND_GATE3_OBSERVATION_VISIBILITY_20261026.md)記錄週報 working-copy 唯讀接線，以及 Decision Desk 對 current observations 的 SQL 分層計數；不代表實際 Owner UAT、來源接受、PIT、Gate 或 ML 資格通過。

[Opus→Antigravity UX 原始碼實作收尾](BALDR_OPUS_UX_IMPLEMENTATION_CLOSEOUT_20261023.md)整理排程啟動、Sol 複核、M1–M169 工程／審查／QA 切片、最後共同 QA 與未完成 Gate；逐輪原收據及圖片留在本機任務目錄，不能由提交推定產品正式驗收。

[Opus外部UI／UX審查](OPUS_BALDR_UI_UX_REVIEW_20261022.md)及[修正處置計畫](../superpowers/plans/BALDR_OPUS_UX_REMEDIATION_20261022.md)指出方向色、資訊層級、圖型、巢狀捲動與面向遮蔽問題；本輪Luna實作、root複核及未評頁面補證見[修正 QA](BALDR_OPUS_UX_REMEDIATION_QA_20261022.md)。既有與本輪工程QA均不等於美觀／直覺、金融或真人接受。

[UI／UX 外部審查包](BALDR_UI_UX_EXTERNAL_REVIEW_BRIEF_20261022.md)整理各使用路徑的現行呈現、視覺化進度、實圖位置與可交給Opus的獨立審查任務；不是新的設計合格或金融接受宣告。

[個股營收與籌碼視覺整合](BALDR_RESEARCH_VISUALIZATION_20261022.md)承接既有圖卡布局，記錄原值圖卡、指標分組與資料界線；最終視覺驗證狀態依該頁判讀。

[月營收原值表漸進展開](BALDR_STOCK_MONTHLY_REVENUE_DISCLOSURE_20261027.md)記錄只有在可見柱圖完整對應所有表格列時才預設收合原表；來源或圖表不完整時仍直接顯示原表，來源與金融資格維持不變。

[Watchlist MainWindow 首次候選快照背景載入](BALDR_WATCHLIST_INITIAL_ASYNC_LOAD_20261027.md)記錄首次唯讀 snapshot／名稱讀取移至 `TaskWorker`、generation 與關閉守衛、inline failure 和同步刷新相容性；Watchlist regression 12 passed、必要 Workbench UI 97 passed，完整 mypy 受既存 T164 bridge 語法錯誤阻擋。未驗原生 GUI／Owner UAT或實際啟動延遲，來源與產品資格不變。

[V2 圖卡優先研究體驗](BALDR_V2_CARD_EXPERIENCE_20261022.md)記錄首頁、個股同屏、選股與策略庫收合、題材缺件及研究時間展示的後繼 UI 增量；不改每日資料恢復或固定候選資格，進度按原文判讀。

[2026-10-25 產業方向摘要卡](BALDR_INDUSTRY_LEADER_CARDS_20261025.md)記錄題材領先／落後平均日漲幅卡的成員漲跌分布、有效分母、版面測試與字型／原生視覺限制；同頁記錄 MOPS Q2 timestamp crosswalk 為候選且正式資料實際解除 0 列，來源／Gate 接受未變。

[2026-10-26 產業卡法人分布與 Workbench 人工研究入口](BALDR_INDUSTRY_LEADER_CARDS_20261025.md#首屏法人淨額分布增量2026-10-25-root-驗證)及[Workbench Advice 人工研究決定入口](BALDR_WORKBENCH_ADVICE_SOURCE_BRIDGE_20261024.md#2026-10-26-workbench-advice-人工研究決定入口)記錄兩項 UI 增量與受控 QA；測試不等於原生 GUI／Owner UAT 或 Gate 資格通過。

V2後繼補完集中看[工程與整合驗收](BALDR_V2_FINAL_COMPLETION_20261021.md)：原始失敗保留，來源／Paper程式契約、真Main GUI、金融用途、Native及OwnerUAT各自列證據，不以正向fixture代替正式來源資格。

本次啟動 TabOrder、Qt model 連線清理與 pandas 相容性修正，見[主視窗啟動警告修復](BALDR_STARTUP_WARNINGS_FIX_20261015.md)；來源版限定驗證與公司名冊來源憑證缺件分開判讀。

V2 開發分支產品接受摘要：[BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md](BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md)；2026-10-21 Owner 已改採自動化優先，四軌驗收、各旅程範圍與金融缺件分開判讀。本索引不替代原始證據，也不代表 Native、Owner UAT 或完整金融資格通過。

可先讀[V2自動化驗收一頁摘要與截圖](BALDR_V2_AUTOMATED_ACCEPTANCE_20261021.md)，不要求Owner現在逐頁操作。

[2026-10-24 Workbench Advice 排程候選接線](BALDR_WORKBENCH_ADVICE_SOURCE_BRIDGE_20261024.md)記錄 verified 當日結果如何進入唯讀 Professional 研究候選、配置缺件如何 fail closed，以及較廣每日旅程測試被隔離 temp 路徑 artifact rename 錯誤阻斷的範圍；不代表正式來源或 Gate 通過。

[2026-10-25 Workbench Advice 空結果判讀](BALDR_WORKBENCH_ADVICE_EMPTY_STATE_20261025.md)記錄 UI 如何區分帶有來源／資格警告的空 DTO 與未附原因的空結果；完整原警告保留，來源、PIT、ML 與 Gate 資格不變。

[2026-10-25 Daily／Weekly 資料品質披露](BALDR_DAILY_WEEKLY_DISCLOSURE_QA_20261025.md)記錄 Workbench 候選品質摘要、Update Readiness 分欄及 weekly 收集需重收原因計數的唯讀投影；未改 Gate，GUI 重啟與 Owner UAT 尚未完成。

[2026-10-25 P0 來源決策清晰度](BALDR_P0_DECISION_CLARITY_QA_20261025.md)記錄已決議來源不再被要求重複輸入決策，並在 Update／Research Console 明示選取列的決策與剩餘證據缺口；不授予來源接受或下游資格。

[2026-10-26 Research Console 公告候選正式資料影響](BALDR_DATA_QUALITY_INVENTORY_20261025.md#2026-10-26-research-console-公告候選正式資料影響讀回)把候選數、正式 identity overlap、缺公告日項目列、精確版本連結及解除數放在同一頁呈現；實際 Q2 正式 overlap 與解除均為 0，明確保留內容版本橋接缺口，不推定資料已補齊。

[2026-10-25 weekly collection 明細](BALDR_WEEKLY_COLLECTION_DETAIL_QA_20261025.md)記錄 Update 內可唯讀展開既有週收集的期間、來源 hash、coverage、品質發現與完整性例子；新增官方收據先做 output_root containment、大小與 SHA-256 核驗再預覽，不核准、不寫 sidecar，也不授 Gate credit。

[2026-10-25 P0 來源特定契約查核提示](BALDR_P0_DECISION_CLARITY_QA_20261025.md#2026-10-25-後續來源特定契約查核提示)記錄各來源可得日、新鮮度、缺件、coverage、retry 政策及已登錄 acquisition route 的唯讀呈現；政策不是來源證據或接受決議。

[2026-10-25 Paper 成交 CSV 無效預覽明細](BALDR_PAPER_FILL_IMPORT_PREVIEW_QA_20261025.md)記錄驗證錯因中文分組、列數／行號提示，以及無效 CSV 不寫入 Paper Ledger 的 UI regression。

[2026-10-19..25 Weekly Review 候選複核](BALDR_WEEKLY_REVIEW_CANDIDATE_AUDIT_20261025.md)記錄新週行情候選的列數、16 列官方缺值與覆蓋未知，以及 working-copy smoke timeout、唯讀週報 blockers 和尚未具名審查的界線；沒有追加 history 或 Gate credit。

[10/18後繼題材研究](BALDR_THEME_DAILY_QA_20261018.md)另核每日聚合、首頁／題材／個股返回及Journal原判斷重啟回訪；[研究12回報修正](BALDR_THEME_DAILY_QA_20261018.md#固定12research07回報交付qa227234)包含清除、同版顯示均線、原價格筆記刪除與明確一般查詢，完整Gate接受範圍保持。

> [回 QA 證據導覽](README.md)。本索引只供導覽。每份收據仍須按自身日期、範圍與限制判讀；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。索引不代表 Gate 通過，也不改變 QA 原件的生命週期。

## 依功能、交付與 Increment 查找

下表只提供入口，不重述驗收狀態。原收據是 append-only；請在原段落判讀日期、scope、結果與限制。此索引不改變收據原結果或接受範圍。

| 功能 | 原收據錨點 |
|---|---|
| 個股研究下鑽與來源回訪 | [Increment34](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment34v1一般觀察股票下鑽與回訪)、[Increment71](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment71真人試用回報的四流程可用性修正) |
| 價格選股、窄結果區與套用後可見性 | [Increment35](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment35v1價格條件在窄結果區可操作)、[Increment66](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment66日常研究修正版候選依原計畫04)、[Increment70](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment70價格選股載入後顯示結果)、[Increment71](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment71真人試用回報的四流程可用性修正) |
| 單股回測結果與完成配對 | [Increment36](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment36v1單股回測未成交日的金融正確性)、[Increment37](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment37v1回測零完成配對的正確判讀) |
| Research Lab 雙策略逐日明細與版本 | [Increment38](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment38p08雙策略逐日原觀測明細)、[Increment40](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment40p07p08新實驗綁定真策略版本)、[Increment49](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment49p08新單股歷史指標版本與正常讀回)、[Increment50](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment50p08獲利因子語意與金融錯誤修正)、[Increment57](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment57p07p08原兩策略的當次規則封存) |
| Portfolio、Health 與配置研究 | [Increment44](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment44p06封存帳戶個股投影)、[Increment47](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment47p06初次策略帳來源與正常保存旅程)、[Increment52](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment52p06配置研究登錄與正常registry重開)、[Increment68](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment68p06-同日-health-收據的初次情境旅程) |
| 推薦回放金融判讀與基本策略比較 | [Increment67](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment67p08-推薦回放通用比較的金融判讀阻斷)、[Increment69](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment69p07p08-兩基本策略原保存對照與明細往返) |
| 固定試用交付與入口 | [Increment32](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment32先交可試用v1解除真實資料與比較按鈕阻斷)、[Increment55](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment55p13p14固定候選native與同版出口)、[Increment59](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment59試用回報固定候選與同版出口)、[Increment66](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment66日常研究修正版候選依原計畫04)、[Increment71](BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment71真人試用回報的四流程可用性修正) |

## 個股研究與產品 UX

| 主題 | 建議閱讀順序 | 範圍提示 |
|---|---|---|
| H20 個股研究 | [H20 gross model 契約](BALDR_A02_H20_GROSS_MODEL_20261006.md) → [研究 cohort](BALDR_H20_RESEARCH_COHORT_20261007.md) → [10/08 H20 candidate snapshot](BALDR_H20_CURRENT_CANDIDATE_93F9C57D_20261008.md) → [10/10 G 原保存來源 bounded Main 讀回](BALDR_PRODUCT_COMPLETION_STATUS_20261010.md) → [操作讀回](H20_READ_OPERATION_SESSION_20261007.md) → [圖表契約](H20_BOUND_CHART_CONTRACT_REVIEW_20261008.md) → [O attempt02 歷史失敗](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md) | G 只完成一次 2382 bounded 下鑽／返回；一般報告遭唯讀 guard 阻擋且完整四端點為 false，不能稱完整個股研究、p95 改善或 H20／ML 正式資格。O attempt02 是較早的失敗紀錄，檔案與 SQLite 真讀均未發生；模型研究、目前來源、保存與圖表仍屬不同驗收面。 |
| UX02–UX24 研究工作台 | [UX08 viewport 整合 QA](UX08_VIEWPORT_INTEGRATION_20261006.md) → [UX08 純 controller handoff 歷史](../09_archive/README.md#2026-10-09-qa-historical-snapshots-scheduler-health-and-ux08-controller) → [UX16 來源契約](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md) → [UX24 首版工程封存（bounded）](../09_archive/UX24_FIRST_VERSION_ENGINEERING_SEAL_20261006.md) → [UX21 Forward Outcome](UX21_FORWARD_OUTCOME_20261006.md) → [UX09 歷史索引](UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md) | UX24 僅關閉其七項有限工程終點，整體 UX／正式啟用／Native 真人／自然成熟仍待各自驗收；目前 UX08 也仍有 Native／真人與其他明列驗收未完成，單張 UX 收據只覆蓋其標示的卡與階段。 |
| BALDR 產品補完 | [10/09 恢復開發基線](BALDR_COMPLETION_RESUME_20261009.md) → [原暫停交接](BALDR_COMPLETION_HANDOFF_20261009.md) → [補完缺口再核對](BALDR_COMPLETION_GAP_REVIEW_20261008.md) → [First wave](BALDR_COMPLETION_FIRST_WAVE_20261006.md) → [B01–B14 收據](#baldr-b01b14) → [10/08 排程修復](BALDR_SCHEDULE_REPAIR_20261008.md) | 恢復 QA 保留首輪失敗與未驗證界線，不是產品完成或發布收據；lane 工程接線不代表全母體、自然累積或正式資格完成。First Wave QA 引用的兩張 Python／exe 截圖在 ignored 的本機 `output/qa/`，乾淨 checkout 不包含圖片。 |
| BALDR M2／H20 深化 | [M2 完整工程收據](BALDR_COMPLETION_M2_20261007.md) → [中央 cohort／Natural／BB UI 整合](BALDR_CENTRAL_COHORT_NATURAL_BBUI_INTEGRATION_20261007.md) → [推薦真人回饋](BALDR_RECOMMENDATION_HUMAN_FEEDBACK_20261007.md) | M2、自然樣本與真人／Native 驗收各有獨立限制；以缺口表及原收據判讀，不把局部工程結果視為產品結案。 |
| 來源資料日期呈現（P10） | [來源資料日呈現核驗](RESEARCH_SOURCE_DATE_PRESENTATION_20261008.md) | 只驗證明示日期的呈現與截止型別處理；不授予來源新鮮度、歷史 PIT 或交易資格。 |
| 技術完整母體保存來源 Main 旅程 | [正常 Main 旅程收據](TECHNICAL_READ_ROOT_MAIN_JOURNEY_20261007.md) | 合成 257 納入／1 排除來源上的 bounded MainWindow 查詢、保存與讀回；不代表真實市場資料、Native 或全產品接受。 |
| 個人研究筆記與儲存隔離 | [Personal Storage Separation](PERSONAL_STORAGE_SEPARATION_LANE_20261005.md) → [Personal Journal](PERSONAL_JOURNAL_LANE_20261006.md) | 正式儲存遷移、啟用與跨頁 readback 仍有未結 Gate；兩份收據範圍不同，請分別核對。 |
| UX20–UX23 固定觀測日與 ML Readiness | [UX20 觀測日接受政策](UX20_OBSERVATION_DAY_ACCEPTANCE_20261006.md) → [UX20 Daily Owner](UX20_DAILY_OWNER_ISOLATED_20261006.md) → [UX21 Benchmark source store](UX21_BENCHMARK_SOURCE_STORE_UI_20261006.md) → [UX22 同源公平比較](UX22_FAIR_COMPARISON_20261006.md) → [UX23 Registry read-only consumer](UX23_REGISTRY_INTEGRATION_20261006.md) | 這些收據記錄 bounded 隔離流程與來源限制；UX20／UX21／UX22／UX23 各自的 Stage、部署與模型資格不得互相推定。 |

## 近期與跨主題收據

| 要查的內容 | 證據入口 |
|---|---|
| 四用途 UX 結果、近期工程增量 | [B03 Update／Runtime](BALDR_B03_UPDATE_RUNTIME_20261006.md)、[B04 收藏](BALDR_B04_SELECTION_WATCHLIST_20261006.md)、[B05 圖表](BALDR_B05_CHART_INCREMENT_20261006.md)、[B06 投資組合摘要](BALDR_B06_PORTFOLIO_SUMMARY_20261006.md)、[B10 私人覆盤](BALDR_B10_PRIVATE_REVIEW_20261006.md)、[B12 隔離 runtime](BALDR_B12_DAILY_RUNTIME_20261006.md) |
| 個股研究的其他讀回 | [報告與 ML 分流](H20_REPORT_ML_SEPARATION_COPY_20261008.md)、[目前來源診斷](H20_SAVED_AND_CURRENT_SOURCE_DIAGNOSIS_20261008.md)、[獨立 current research](H20_INDEPENDENT_CURRENT_RESEARCH_20261008.md)、[載入 candidate](BALDR_H20_LOADING_CANDIDATE_421BC973_20261008.md) |
| BALDR／H20／UX 分支與 bounded 收據 | [36 份原件的分組導覽](BALDR_UX_EVIDENCE_GUIDE_20261009.md) | 依模型／自然結果、候選與發布、Registry／復原、圖表、研究工作台、capture 分組；逐份狀態仍以原件與較新 QA 判讀。 |

<a id="baldr-b01b14"></a>
### BALDR B01–B14

依產品補完缺口表選擇對應收據：B01 [歷史標籤邊界](BALDR_B01_HISTORICAL_LABEL_BOUNDARY_20261006.md)、B02 Windows COW 見 [closeout status 表](BALDR_CLOSEOUT_STATUS_20261006.md)、B03 [市場首頁](BALDR_B03_MARKET_HOME_20261006.md)／[Update runtime](BALDR_B03_UPDATE_RUNTIME_20261006.md)、B04 [選擇與收藏](BALDR_B04_SELECTION_WATCHLIST_20261006.md)、B05 [圖表](BALDR_B05_CHART_INCREMENT_20261006.md)、B06 [投資組合摘要](BALDR_B06_PORTFOLIO_SUMMARY_20261006.md)、B07 [規則歷史](BALDR_B07_RULE_HISTORY_20261006.md)、B08 [個人路由](BALDR_B08_PERSONAL_ROUTES_20261006.md)、B09 [個人投資組合](BALDR_B09_PERSONAL_PORTFOLIO_20261006.md)、B10 [私人覆盤](BALDR_B10_PRIVATE_REVIEW_20261006.md)、B11 [模型家族目錄](BALDR_B11_FAMILY_CATALOG_20261006.md)、B12 [每日 runtime](BALDR_B12_DAILY_RUNTIME_20261006.md)、B13 [模型輸入](BALDR_B13_MODEL_INPUT_20261006.md)、B14 [Shadow evidence](BALDR_B14_SHADOW_EVIDENCE_COMPOSITION_20261006.md)。

### 2026-10-06 至 10-09 收據直達索引

以下提供近期產品、研究與 UX 收據／計畫的直達入口。文件仍保留各自的範圍與時點；此索引不把它們合併成新的現況、完成度或待辦判定。

- **H20 研究來源與讀回**：[固定來源建置](BALDR_H20_FIXED_SOURCE_BUILD_REVIEW_20261009.md)、[來源清單環境橋接審查](BALDR_H20_SOURCE_MAP_SEAM_REVIEW_20261009.md)、[verifier 模組相容性 root review](BALDR_H20_VERIFIER_MODULE_COMPATIBILITY_ROOT_REVIEW_20261009.md)、[MA 固定合成旅程 root review](BALDR_MA_V9_CHILD_IDENTITY_ROOT_REVIEW_20261009.md)、[設定入口 L root review](BALDR_H20_L_CONFIG_SOURCEPORT_ROOT_REVIEW_20261009.md)、[WAL keeper root review](BALDR_H20_WAL_KEEPER_ROOT_REVIEW_20261009.md)、[Runtime root 契約](BALDR_H20_RUNTIME_ROOT_CONTRACT_REVIEW_20261008.md)、[Snapshot builder](BALDR_H20_SNAPSHOT_BUILDER_REVIEW_20261008.md)、[WAL snapshot](BALDR_H20_WAL_SNAPSHOT_REVIEW_20261008.md)、[版面 teardown 與窄控制](BALDR_LAYOUT_TEARDOWN_AND_NARROW_CONTROLS_20261008.md)、[Bookmark controls](H20_BOOKMARK_CONTROLS_20261007.md)、[Bookmark core](H20_BOOKMARK_CORE_20261007.md)、[凍結來源 root 修復](H20_FROZEN_SOURCE_ROOT_REPAIR_20261007.md)。另見 [M7 原來源 S4 Main bounded 旅程](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)：旅程及 120 筆 OHLC／684 bp 對照通過，來源 unchanged；不代表新 EXE、真人驗收或正式 PIT／收益資格。MA 收據仍依各自來源與範圍判讀。
- **推薦介面與個人工作區**：[推薦理由完整保存審核](BALDR_COMPLETE_REASONS_REVIEW_20261008.md)、[推薦鍵盤捲動](BALDR_RECOMMENDATION_KEYBOARD_SCROLL_20261008.md)、[推薦詳情目前捲動審查](BALDR_RECOMMENDATION_SCROLL_CURRENT_REVIEW_20261009.md)、[個人 Watchlist thread serialization](PERSONAL_WATCHLIST_THREAD_SERIALIZATION_20261007.md)、[推薦閱讀版面](RECOMMENDATION_READING_LAYOUT_20261007.md)。捲動審查使用合成資料與 offscreen 畫面，不是原始股票或真人接受；新版 EXE 與真人操作驗收仍待完成，H20 下鑽另有獨立關卡。
- **產品補完與發布**：[F17 正常 capture pair review](BALDR_F17_NORMAL_CAPTURE_PAIR_REVIEW_20261009.md)、[正常技術／官方來源聯合產製 UI review](BALDR_F17_NORMAL_PRODUCTION_UI_REVIEW_20261009.md)、[官方當下處置來源 leaf](SELECTION_OFFICIAL_DISPOSAL_SOURCE_20261007.md)、[平行工作交接](BALDR_PARALLEL_NEXT_WORK_20261009.md)、[portable configured bootstrap](BALDR_PORTABLE_CONFIGURED_BOOTSTRAP_20261006.md)、[portable Windows](BALDR_PORTABLE_WINDOWS_20261006.md)、[F07 固定候選](F07_FIXED_CANDIDATE_F2FBA4C7_20261008.md)、[F17 single graph integration](F17_SINGLE_GRAPH_INTEGRATION_20261008.md)。該 leaf 的 `available_at` 未知、`current_only`、`historical_pit_eligible=false`；F17 UI review 的正常來源增量已驗，但完整 Main 下鑽、全母體效能、跨程序聯合收藏與 EXE 接受仍未完成，不代表 PIT acceptance 或 F17 結案。
- **日期語義、篩選與 Universe**：[決策 Snapshot 日期語義](DECISION_SNAPSHOT_DATE_SEMANTICS_20261006.md)、[P01 篩選 Profile diagnostics](P01_FILTER_PROFILE_DIAGNOSTIC_CONTRACT_20261008.md)、[同次 Session metadata 效能候選](BALDR_P01_SESSION_METADATA_PERFORMANCE_CANDIDATE_20261009.md)、[路徑渲染候選 root review](BALDR_P01_PATH_RENDER_DESIGN_ROOT_REVIEW_20261009.md)、[1,000 檔效能失敗與下一 Gate](BALDR_1000_STOCK_PERFORMANCE_NEXT_GATE_20261009.md)、[單次頁面路徑 tuple memo](BALDR_P01_COMPONENT_TUPLE_MEMO_20261009.md)、[單頁路徑渲染 memo](BALDR_P01_PAGE_PATH_RENDER_MEMO_20261009.md)、[render-prefill 初版候選紀錄](BALDR_P01_RENDER_PREFILL_20261009.md)、[render-prefill root review](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)、[已簽發來源 DTO 重建](BALDR_P01_PROOF_GATED_REHYDRATION_20261009.md)、[技術規則視窗重用](TECHNICAL_RULE_WINDOW_REUSE_20261007.md)、[技術 Universe query stream](TECHNICAL_UNIVERSE_QUERY_STREAM_20261007.md)、[技術 Universe read root](TECHNICAL_UNIVERSE_READ_ROOT_20261007.md)。固定 85bc 六角色矩陣暖操作 p95 為翻頁 196.205 ms、排序 191.8186 ms、篩選 523.902 ms；篩選仍超過 300 ms。冷啟動至首頁 p95 為 20.0319 秒。這是隔離診斷矩陣，不是一般產品旅程驗收。

### F02／F03／F06／F12 功能驗收鏈（2026-10-10）

先看[產品補完缺口再核對](BALDR_COMPLETION_GAP_REVIEW_20261008.md)與[平行工作 root review](BALDR_PARALLEL_ROOT_REVIEW_20261009.md)掌握跨功能阻礙，再按下列收據追查各自範圍。這些是 bounded 工程證據，不等於完整 UI、EXE 或真人驗收，也不代表相關 Gate 已通過。

- **F12 月營收**：[來源審查](BALDR_F12_MONTHLY_REVENUE_SOURCE_REVIEW_20261009.md) → [index 整合複核](BALDR_F12_INDEX_INTEGRATION_REVIEW_20261009.md) → [全母體 query reader 驗收](F12_MONTHLY_REVENUE_QUERY_READER_20261009.md) → [saved-recipe root review](BALDR_F12_SAVED_RECIPE_ROOT_REVIEW_20261009.md) → [WAL exact reopen](BALDR_F12_WAL_EXACT_REOPEN_ROOT_REVIEW_20261009.md) → [durable raw archive v2](BALDR_F12_DURABLE_RAW_ARCHIVE_V2_20261009.md) → [archived finish root review](BALDR_F12_ARCHIVED_FINISH_ROOT_REVIEW_20261009.md) → [Main integration review](BALDR_F12_MAIN_INTEGRATION_REVIEW_20261009.md) → [D focused／Main root follow-up](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)。頁碼按鈕修補與 4 項按鈕回歸通過；最新 T10 focused 12 項通過，但完整 Main 仍在明示 Watchlist COW 啟用逾時，來源維持唯讀。Reader 的 current-only／未知來源時間界線保留，完整新程序收藏讀回、EXE 與真人驗收仍待完成。
- **F02 均線條件**：[四均線來源缺口與子模組根審（10/08）](F02_SAVED_FEATURE_GAP_20261008.md) → [fdopen guard 診斷](BALDR_F02_FDOPEN_GUARD_DIAGNOSIS_20261009.md) → [V4 oracle／supervisor review](BALDR_F02_V4_ORACLE_SUPERVISOR_REVIEW_20261009.md) → [M guard root review](BALDR_F02_M_GUARD_ROOT_REVIEW_20261009.md)。10/08 報告確認保存特徵缺口並記錄單一子模組驗證，不代表產品接線或驗收。完整 257 檔矩陣、正常來源、新 EXE、真人驗收與 MA20 上彎契約仍未完成；局部 guard／oracle 結果不可當成產品通過。
- **F03 KDJ 條件**：[full-population 整合計畫](BALDR_F03_FULL_POPULATION_INTEGRATION_PLAN_20261009.md) → [KDJ query contract](BALDR_F03_KDJ_QUERY_CONTRACT_20261009.md) → [MA／KDJ／Volatility group v2](BALDR_F03_MA_KDJ_VOLATILITY_GROUP_V2_20261009.md) → [多 parent 共同發行邊界計畫](BALDR_F03_MULTI_PARENT_GROUP_PUBLICATION_PLAN_20261009.md) → [multi-parent callback review](BALDR_F03_MULTI_PARENT_CALLBACK_REVIEW_20261009.md) → [prepare root follow-up](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)。截至已提交 commit `8945df89`，formal reader／group-session bounded publication slice 有 17 個節點取得通過證據（首輪 15 passed；僅重跑兩個 QA-overlay 修正節點）；固定 258/257/1 來源的窄窗 View G8 與收藏 identity C 亦各有 bounded 通過證據。這些不等於全域 query、正常 Main 或新程序收藏閉環驗收；本索引不納入後續未提交 QA 追加。
- **F06 波動條件**：[來源證據與方法缺口計畫](BALDR_F06_VOLATILITY_EVIDENCE_PLAN_20261009.md) → [composite query contract](BALDR_F06_COMPOSITE_VOLATILITY_QUERY_CONTRACT_20261009.md) → [Decimal 方法提案](BALDR_F06_DECIMAL_VOLATILITY_METHOD_PROPOSAL_20261009.md) → [collector contract](BALDR_F06_VOLATILITY_COLLECTOR_CONTRACT_20261009.md) → [presenter bounded integration evidence](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)。`8945df89` 提交 presenter 與 reader-issued observed／unknown 測試，2 項 focused tests 及記錄的強制檢查通過；目前無正式 UI 呼叫端、無 full-N reader-issued 結果，方法提案仍不是已採納產品規則。

### 2026-10-10 待真人實測

- **複合研究與收藏重開**：[真人驗收步驟](BALDR_COMPOSITE_HUMAN_CHECK_20261010.md)。原碼自動化旅程已通過，但真人結果尚未取得；此收據不代表完整 UI、EXE 或投資驗收。
- **BALDR／P08 有界工程收據**：[產品補完狀態快照](BALDR_PRODUCT_COMPLETION_STATUS_20261010.md)、[P08 價格證據切片](BALDR_P08_PRICE_EVIDENCE_SLICE_20261010.md)、[P08 現金種子切片](BALDR_P08_CASH_SEED_SLICE_20261010.md)。這些是 10/10 的狀態與有限工程證據，不代表 P08 或整體產品補完完成。

## 其他常用路徑

- **投資組合與 Paper**：[三帳摘要](BALDR_B06_PORTFOLIO_SUMMARY_20261006.md)、[個人 Paper producers](BALDR_PERSONAL_PAPER_PRODUCERS_20261006.md)、[個人 Paper ledgers](BALDR_PERSONAL_PAPER_LEDGERS_20261006.md)。
- **Watchlist 儲存與 COW 遷移（F4，2026-10-05）**：[revision retention](F4_ITEM_REVISION_STORAGE_AND_RETENTION_20261005.md) → [SQLite COW](F4_SQLITE_COW_CONVERTER_AND_ACTIVATION_20261005.md) → [Legacy JSON COW](F4_LEGACY_JSON_COW_AND_ACTIVATION_20261005.md) → [整合／容量驗收](F4_RELEASE_INTEGRATION_AND_RESOURCE_ACCEPTANCE_20261005.md)。這組隔離工程收據與正式資料 apply／activation 分開判讀，也不同於後續 B02 個人儲存工作包。
- **技術分析與圖表**：[BBANDS 上軌入口](BALDR_A01_BBANDS_UPPER_20261006.md)、[每日 BBANDS](BALDR_DAILY_BBANDS_CENTRAL_20261007.md)、[H20 圖表契約](H20_BOUND_CHART_CONTRACT_REVIEW_20261008.md)。
- **早期產品 QA（歷史）**：推薦分析與數據更新 Tab 的四份舊問題盤點／QA 摘要已移至[歷史封存入口](../09_archive/README.md#2026-10-08-early-recommendation-and-update-tab-qa)。原路徑保留短導引；其中的路徑、測試數字與待辦不代表目前實作或驗收結果。現行操作與排錯以 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 為準，測試範圍看 [Feature-to-test routing matrix](FEATURE_TEST_ROUTING_MATRIX_2026_06_23.md)。
- **Workbench 歷史 UI closeout**：[左側主導覽 IA（2026-07-07）](../09_archive/WORKBENCH_LEFT_NAVIGATION_IA_CLOSEOUT_2026_07_07_HISTORY.md)、[視覺層級 polish（2026-07-07）](../09_archive/WORKBENCH_VISUAL_HIERARCHY_POLISH_CLOSEOUT_2026_07_07_HISTORY.md)：保留當時 UI 與測試證據，不作目前狀態依據；現行操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。
- **Readability polish closeout（2026-07-07，歷史）**：[Archive 原文](../09_archive/README.md#2026-07-broker-flow-and-ui-closeout)；當時 formal-data waits 是該次快照，現況看 Snapshot／Manual。
- **Workbench 低流動性提示分流 QA（2026-09-21，歷史）**：[封存收據](../09_archive/WORKBENCH_LIQUIDITY_REVIEW_ROUTING_QA_2026_09_21_HISTORY.md)保留當日 read-only snapshot／UI route 與 `1121` liquidity、`10` weakness 的 bounded 結果；後續整合路由見[封存的 V5 readability acceptance](../09_archive/V5_READABILITY_ACCEPTANCE_2026_09_21.md)，目前操作仍以 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 為準。該收據不驗證 liquidity 資料品質或正式來源 Gate；本批封存來源 bytes／SHA 見 [Coverage History Entry 149](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-149)，低流動性收據原件見 [Entry 125](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-125)。
- **Position Health／Paper thesis 工程盤點（V4，2026-09-08）**：[source-to-caller gap map](V4_POSITION_HEALTH_SOURCE_CALLER_GAP_MAP_2026_09_08.md) → [transition evaluator contract](V4_POSITION_HEALTH_TRANSITION_EVALUATOR_CONTRACT_2026_09_08.md)。兩份原件記錄當時輸入盤點與 proposal-only caller 範圍，不代表目前 Gate 6 readiness 或投資有效性；現況看 Snapshot 與近期 QA。
- **UI geometry audit（2026-09-29，歷史）**：[封存收據](../09_archive/UI_LAYOUT_AUDIT_20260929.md)記錄六格 offscreen viewport 矩陣及合成 UI 覆蓋；這不證明 Windows 原生視窗行為，也未證實先前 native access violation 的根因或永久修復。原路徑保留相容導引，來源與替代入口見 [Coverage History Entry 151](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-151)。

## 補充收據索引（2026-10-10 治理補登共 85 份）

> 本區收錄經 2026-10-10 全量盤點查核之專屬 QA 驗收證據；各原件維持各自日期與範圍，不推升為目前全域狀態。

- [A03 個人模型每日保存與自然結果](BALDR_A03_PERSONAL_MODEL_DAILY_20261006.md)
- [BALDR B10 Notes Backup / Restore Adapter QA](BALDR_B10_NOTES_BACKUP_20261006.md)
- [B14 獨立 shadow control port 工程收據](BALDR_B14_SHADOW_CONTROL_20261006.md)
- [BBUI01 有限 BB 上軌第三條件 UI（2026-10-07）](BALDR_BBANDS_RESEARCH_UI_20261007.md)
- [c611 固定候選：建置及同版驗證](BALDR_C611_CANDIDATE_20261007.md)
- [固定 acd18a1e 候選與接受範圍](BALDR_CANDIDATE_ACD18A1E_20261008.md)
- [個人 Current-observed H20 每日入口：受驗保存與自然接線](BALDR_CURRENT_OBSERVED_H20_DAILY_20261006.md)
- [dev／main 兩用途整理與可恢復發布準備](BALDR_DEV_MAIN_RELEASE_PREPARATION_20261007.md)
- [Baldr 收尾差異：已授工程與未決事項（2026-10-06）](BALDR_ENGINEERING_DECISION_DELTA_20261006.md)
- [F03 KDJ 方法契約與缺口盤點](BALDR_F03_KDJ_CONTRACT_REVIEW_20261008.md)
- [Baldr 已授範圍最終穩定窗收據（2026-10-06）](BALDR_FINAL_AUTHORIZED_UNION_20261006.md)
- [原保存 2382：一次實際旅程計時方案（尚未執行）](BALDR_H20_2382_TIMING_PLAN_20261010.md)
- [H20N01 完整 cohort 自然結果 caller](BALDR_H20_NATURAL_BATCH_20261007.md)
- [本機 main 使用版 packaging 驗收](BALDR_LOCAL_MAIN_PACKAGING_20261007.md)
- [四均線正常來源入口：局部驗證與待完成項目](BALDR_MA_NORMAL_OPENER_REVIEW_20261008.md)
- [Baldr 下一波精確 ownership 派工收據（2026-10-06）](BALDR_NEXT_OWNERSHIP_DISPATCH_20261006.md)
- [下一次Task唯讀驗收與原24UX已知工程差異（2026-10-07）](BALDR_NEXT_RUN_AND_REMAINING_ENGINEERING_20261007.md)
- [P08 策略帳戶綁定切片（2026-10-10，未完成 P08）](BALDR_P08_ACCOUNT_BINDING_SLICE_20261010.md)
- [P08 快照來源紀錄切片（2026-10-10，P08 尚未完成）](BALDR_P08_SNAPSHOT_RECEIPT_SLICE_20261010.md)
- [BBP01 BBANDS30 上軌完整具名母體驗證（2026-10-07）](BALDR_PARENT_BBANDS30_UPPER_20261007.md)
- [個人 H20 模型中央接線與真候選核對（2026-10-06）](BALDR_PERSONAL_MODEL_ACTIVATION_INTEGRATION_20261006.md)
- [個人真模型啟用前讀回入口](BALDR_PERSONAL_MODEL_ACTIVATION_PREFLIGHT_20261006.md)
- [BALDR 產品可用性與 BUI-001 修復收據（2026-09-25）](BALDR_PRODUCT_USABILITY_20260925.md)
- [BALDR R01 Registry 有界同份讀取（2026-10-06）](BALDR_R01_REGISTRY_READ_BUDGET_20261006.md)
- [Baldr 讀取 session 中央審核（2026-10-08）](BALDR_READ_SESSION_CENTRAL_REVIEW_20261008.md)
- [1,000 檔合成保存研究產製與獨立讀回](BALDR_SYNTHETIC_UNIVERSE_1000_READBACK_20261008.md)
- [dev／main 分支整理與可恢復收據](BALDR_TWO_BRANCH_RECOVERY_20261007.md)
- [臺銀證券電子下單成本估算 QA（2026-09-14）](BANKTAIWAN_COST_ESTIMATE_2026_09_14.md)
- [C2 mandatory UI/static gate 現況收據（2026-09-25）](C2_MANDATORY_UI_STATIC_GATES_20260925.md)
- [C4 最終 mandatory UI/static gates 收據（2026-09-25）](C4_FINAL_MANDATORY_STATIC_GATES_20260925.md)
- [每日 Decision Evidence Capture 修復 QA（2026-09-18）](DAILY_CAPTURE_RECOVERY_2026_09_18.md)
- [Experiment V1 Preregistration Template](EXPERIMENT_V1_PREREGISTRATION_TEMPLATE.md)
- [Graphify 程式碼引用查核收尾（2026-09-17）](GRAPHIFY_CODE_REFERENCE_REVIEW_2026_09_17.md)
- [H20 同次來源圖表接線中央審查](H20_BOUND_CHART_INTEGRATION_20261008.md)
- [H20 返回來源：避免重複名單核驗](H20_RETURN_SINGLE_REFRESH_20261007.md)
- [H20 可見等待、取消終態與單一讀取](H20_VISIBLE_LOADING_SINGLEFLIGHT_20261008.md)
- [Journal 跨頁 worker gate 隔離診斷（2026-10-06）](JOURNAL_JOURNEY_WORKER_GATE_20261006.md)
- [Learning Evidence Denominator QA — 2026-09-18](LEARNING_EVIDENCE_DENOMINATORS_2026_09_18.md)
- [Learning Evidence Workbench QA 紀錄（2026-09-14）](LEARNING_EVIDENCE_WORKBENCH_2026_09_14.md)
- [m11 個人模型與自然結果評估（2026-09-28）](M11_PERSONAL_RESEARCH_OUTCOME_STAGEC_20260928.md)
- [Natural maturity calendar refresh wiring QA（2026-09-18）](MATURITY_CALENDAR_REFRESH_WIRING_2026_09_18.md)
- [Forward maturity calendar 接線 QA（2026-09-18）](MATURITY_CALENDAR_WIRING_2026_09_18.md)
- [2026-10-03 行情發布節奏與 Paper 研究隔離驗收](OPERATIONAL_QUALITY_AND_RESEARCH_ISOLATION_20261003.md)
- [Paper EOD credit candidate freshness policy QA（2026-09-22）](PAPER_EOD_CREDIT_CANDIDATE_POLICY_QA_2026_09_22.md)
- [Paper EOD freshness lane unknown projection QA（2026-09-21）](PAPER_EOD_FRESHNESS_LANE_QA_2026_09_21.md)
- [Paper EOD 非交易日 gate 修正 QA（2026-09-25）](PAPER_EOD_NON_TRADING_DAY_GATE_QA_2026_09_25.md)
- [Paper EOD scope manifest v2→v3 受控修正計畫](PAPER_EOD_SCOPE_MANIFEST_MIGRATION_PLAN_2026_09_21.md)
- [Paper event source capture failure diagnostics QA — 2026-10-02](PAPER_EVENT_SOURCE_CAPTURE_FAILURE_DIAGNOSTICS_QA_20261002.md)
- [Personalization real-source fit runner QA（2026-09-17）](PERSONALIZATION_FIT_RUNNER_QA_2026_09_17.md)
- [Personalization 真實來源唯讀入口 QA（2026-09-16）](PERSONALIZATION_READONLY_SOURCE_QA_2026_09_16.md)
- [個人日常產品交付工作包與驗收矩陣](PERSONAL_DAILY_PRODUCT_DELIVERY_20261006.md)
- [Personal Delivery Activation QA（2026-09-18）](PERSONAL_DELIVERY_ACTIVATION_2026_09_18.md)
- [m10 個人模型 Qt widget 驗收（2026-09-28）](PERSONAL_MODEL_QT_WIDGET_ACCEPTANCE_M10_20260928.md)
- [個人研究 UI 隔離啟動器（2026-09-28）](PERSONAL_RESEARCH_UI_ISOLATION_20260928.md)
- [Personal subtree 政策變更 lane](PERSONAL_SUBTREE_POLICY_LANE_20261006.md)
- [Position Health Increment 1 QA（2026-09-15）](POSITION_HEALTH_INCREMENT_1_QA_2026_09_15.md)
- [PRODUCT_STAGE01_SOURCE_MATRIX_20261005](PRODUCT_STAGE01_SOURCE_MATRIX_20261005.md)
- [階段1早期SQL取消與下一包依賴（2026-10-05）](PRODUCT_STAGE1_SQL_CANCELLATION_20261005.md)
- [Qt／Python 原生事件唯讀追查補充](QT_NATIVE_CRASH_READONLY_FOLLOWUP_2026_09_15.md)
- [R006 unknown artifact 與保留策略（2026-09-27 addendum）](R006_UNKNOWN_ARTIFACT_RETENTION_ADDENDUM_20260927.md)
- [Recommendation Learning Runtime Wiring QA — 2026-09-15](RECOMMENDATION_LEARNING_RUNTIME_WIRING_QA_2026_09_15.md)
- [Scheduler / Paper 空持倉與研究種子範圍修復 QA](SCHEDULER_PAPER_SCOPE_REPAIR_20260930.md)
- [Stage6／UX11 規則卡唯讀投影限定收據（2026-10-06）](STAGE6_RULE_CARD_READMODEL_20261006.md)
- [完整母體逐段核驗讀取 API](TECHNICAL_VERIFIED_PARENT_STREAM_20261007.md)
- [user_declared Holding Research Increment 2 QA](USER_DECLARED_HOLDING_RESEARCH_INCREMENT_2_QA_2026_09_15.md)
- [UX02 共用狀態詞彙有限切片（2026-10-05）](UX02_SHARED_STATUS_VOCABULARY_20261005.md)
- [UX07 圖表可行性調查（2026-10-05）](UX07_CHART_FEASIBILITY_20261005.md)
- [UX08 原生圖同源契約限定驗證（2026-10-05）](UX08_NATIVE_CHART_CONTRACT_20261005.md)
- [UX08 推薦 execution 保存圖表有限閉環（2026-10-06）](UX08_RECOMMENDATION_SAVED_CHART_20261006.md)
- [UX08 保存價格／MA20／MA60 同版本讀回（2026-10-06）](UX08_SAVED_CHART_READBACK_20261006.md)
- [UX09 研究名單入選生命週期有限包（2026-10-05）](UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md)
- [UX10 多方法共同符合：獨立 lane 限定交接](UX10_MULTI_METHOD_LANE_20261006.md)
- [UX11 保存結果與規則來源核對限定收據（2026-10-06）](UX11_SAVED_RESULT_RULE_READBACK_20261006.md)
- [UX18 原引擎排名不可變發布與同源讀回](UX18_ORIGINAL_STOCK_RANKING_PUBLISHER_20261005.md)
- [原排名收藏與個股來源版本化](UX18_RANK_BOOKMARK_SOURCE_VERSIONING_20261005.md)
- [UX19 儲存治理與發布復原有限收尾（2026-10-05）](UX19_STORAGE_AND_PUBLICATION_RECOVERY_20261005.md)
- [UX20 具名母體多批 capture 整合收據（2026-10-06）](UX20_PARENT_CAPTURE_INTEGRATION_20261006.md)
- [UX20 保存母體收據 UI 限定整合（2026-10-06）](UX20_PARENT_RECEIPT_UI_20261006.md)
- [UX20 固定 MA 研究樣本 capture 獨立 lane](UX20_RULE_SAMPLE_CAPTURE_LANE_20261006.md)
- [UX20 MA 完整控制組 capture 主線限定整合（2026-10-06）](UX20_SAMPLE_CAPTURE_INTEGRATION_20261006.md)
- [UX21 具名 benchmark 唯讀 adapter 獨立 lane](UX21_BENCHMARK_ADAPTER_20261006.md)
- [UX21 實際來源、隔離保存與日報限定收據](UX21_SOURCE_STORE_DAILY_20261006.md)
- [UX21 endpoint label → UX22 樣本／公平比較 readiness（2026-10-06）](UX22_LABEL_READINESS_20261006.md)
- [UX23 registry 唯讀 reader 隔離驗收（2026-10-06）](UX23_REGISTRY_READONLY_20261006.md)
- [UX23 隔離 shadow 最小工程狀態（2026-10-06）](UX23_SHADOW_ACCEPTANCE_20261006.md)
