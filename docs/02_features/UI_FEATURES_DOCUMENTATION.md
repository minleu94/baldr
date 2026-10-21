# UI 功能文件（Qt）

## research07試用回報增量（固定12）

五項改善限定原旅程：明確一般查詢離開保存context並從原價庫辨識名稱；題材頁一鍵清除含草稿確認；價格原來源圖顯示同版收盤SMA20／60；原價格筆記可確認隱藏整篇修訂家族並保留Journal歷史；研究歷史分開績效／權益與保存逐日訊號。零成交不另加訊號拒絕條件，缺原訊號或共同價量仍拒絕。操作見APPLICATION_MANUAL及分冊，Source／EXE實際出口以[具名QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定12research07回報交付qa227234)為準；固定12已包含，舊11保留。

固定候選143回應139試用：基本面頁先列月營收數值再展開來源；巢狀價格頁依作用中頁自然高度捲動，代碼可單獨清空；收藏名稱與原保存身分分開，同源收藏直接開原個股再返回原查詢。定向、共同防線及正常Source Main通過；固定候選另驗新位置設定與同版雙程序，範圍按[143 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment143-setup-work-scheduling)判定，141c原固定包不因source改動而改版。

推薦頁初始化的跨視窗Tab順序、Qt自有連線清理及pandas相容性修復已納入115固定候選；原受影響回歸見[啟動修復QA](../06_qa/BALDR_STARTUP_WARNINGS_FIX_20261015.md)，固定EXE與具名限制見[Increment115 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment115-fixed-trial-delivery)。116只修舊回測保存的Decimal附註序列化，沒有改UI控制項或導航，已在同輪另交固定116候選；操作與精度界線見[保存格式說明](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#舊回測保存格式與精度)。

## 按九個工作區查找

V2 後繼 Python 候選新增同題材成員的上一檔／下一檔，來源版本與原選列必須保持；已保存報告不可切股。各股票行情與題材來源日分開判讀，缺價不借題材數值。QA096 正常 Main 與新程序的成員來回及選列變動拒絕已通過，固定 `2b164aede953` EXE 未含；新 `412ca3e5fe4f` 候選已通過 QA103 包內正常 Main first/fresh；操作及過期來源的處理見 [題材手冊](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#產業與題材後繼source)。

九個 workspace key 是 Feature Map、路由及來源上下文使用的穩定識別；V2 以四個主導覽群組和「系統管理」呈現，不代表後端頁面或責任已合併。共用個股 Detail 依來源身份隔離一般報告、價格研究及其他保存來源，返回時仍核對原上下文。V2 導覽與 QA023／024 的限定證據見[完整操作手冊 V2 導航](../07_guides/APPLICATION_MANUAL.md#v2開發分支導航尚非固定rc)；該證據不構成 RC、Native、真人或金融資格接受。

固定120將原三個計分策略另立1.1.0：正常單股fixed／next_open保留未知分數、另列已知／未知日數，成功才可保存。失敗報告停用保存／匯出／晉升並隱藏上次圖表，不把空交易表當零績效；明示`can_promote=False`即使SOP PASS仍停用晉升。兩策略對照須同一缺值方法版本；原版本與保存reader保留。1366px shell沿原520／600px兩欄驗收，不放寬既有幾何斷言。操作與資格邊界見[計分指南](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#計分策略110的缺值與保存後續候選)；來源／EXE的Qt功能不當Native／真人接受，119舊包不變。

| 工作區 | UI 功能契約 | 手冊／操作權威 | 可搜尋詞 |
|---|---|---|---|
| 決策工作台 | [決策工作台](#workspace-decision-workbench) | [每日決策](../07_guides/APPLICATION_MANUAL.md#8-每日決策-daily-decision-desk) | Daily Decision Desk、Advice、決策來源、來源追溯、唯讀 |
| 市場探索 | [市場探索](#workspace-market-exploration) | [資料與市場研究手冊](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md) | 市場總覽、指數、強勢／弱勢、主力流向、source date、unknown |
| 推薦分析 | [推薦分析](#workspace-recommendation) | [推薦與 Research Lab 手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md) | Profile、Why／WhyNot、每日研究、價格選股、篩選、收藏 |
| 策略回測／Research Lab | [策略回測](#workspace-backtest-research-lab) | [推薦與 Research Lab 手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md) | 單股、批次、Registry、run identity、完成配對、PF、Walk-forward |
| 觀察清單 | [觀察清單](#workspace-watchlist) | [觀察清單與持倉手冊](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md) | 手動觀察、bookmark、source ID、exact reopen、未連結 |
| 個股研究 | [個股研究](#workspace-stock-research) | [推薦與 Research Lab 手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md) | ResearchStockContextDTO、decision_date、saved／current、官方注意公告、ML |
| 持倉管理 | [持倉管理](#workspace-portfolio-management) | [觀察清單與持倉手冊](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md) | 手動帳、持倉、Paper、Health、配置研究、交易紀錄 |
| 數據更新 | [數據更新](#workspace-data-update) | [資料與市場研究手冊](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md) | freshness、正式／候選、CSV、SQLite、取消、唯讀 |
| Runtime Observatory | [Runtime Observatory](#workspace-runtime-observatory) | [系統狀態手冊](../07_guides/APPLICATION_MANUAL.md#11-系統狀態與決策擷取終態) | event、worker、receipt SHA、終態、過期回呼、unknown |

### 系統管理：儲存維護

儲存維護頁提供唯讀、有界的儲存位置及版本盤點。原始碼啟動只檢查明示的 repo／dist 版本容器；封裝啟動只檢查目前套件位置，不搜尋父磁碟或其他 Trial。磁碟容量欄代表整個磁碟，不是目錄用量；最多盤點 64 個版本及 4096 個項目，超限、不可讀或未跟隨內層連結時保留部分／不可用狀態。未盤點不等於零；沒有清理或刪除資格，引用、備份與回退未逐件核對的版本一律保留。操作及狀態判讀見[APPLICATION_MANUAL 儲存維護](../07_guides/APPLICATION_MANUAL.md#系統管理儲存維護)。後繼原始碼的定向、正常 Main 首次盤點及雙次刷新證據見[V2驗收紀錄](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md#儲存盤點缺件診斷qa058-起)；舊 e369 EXE 不含此修復。

首頁「最近研究」保留既有「開啟研究紀錄與覆盤」入口；只有保存原件為 report 且同時有來源資料日與來源身份時，另顯示「回訪原報告」。報告卡的行情日只取實際 `StockResearchReportNote.snapshot.report.price_points[-1].data_date`；原件型別不符、沒有價格列或末筆日期缺失時顯示原件未提供，不從 context 推算。新入口以同次讀取的 exact entry 選取時間軸，重用原件 reader 背景重核後才呈現保存時 snapshot；首頁來源返回首頁，時間軸原入口仍返回時間軸。過期 entry、缺 provenance、原件欄位不符或讀取失敗不會改開同 ID／同股的其他版本。保存時間、來源資料日、來源資格與當下行情各自判讀；保存 snapshot 不代表最新資料或投資建議。操作步驟及限制見 [APPLICATION_MANUAL V2 導航](../07_guides/APPLICATION_MANUAL.md#v2開發分支導航尚非固定rc)。本段描述目前原始碼接線，不宣稱 QA 已通過或既有 EXE 已包含。

研究時間軸另有「對照目前可讀資料」候選操作，以左右欄呈現原件與獨立讀取的目前來源及各自日期、來源限制，不計算差值。原件變更或身份不符時整體拒絕；重新讀取、換選、離頁或關閉會使舊結果失效。手動筆記無封存行情，題材筆記不含行情值且只對照明選目錄中的目前版本；價格重驗原來源，報告保留原保存投影。此操作不寫回 Journal、不計金融差值，也不提升 PIT 或資料資格。QA110 正常 MainWindow 首次／重開功能與 QA112 的 125% 雙欄同屏及長 SHA 換行已通過；固定 `412ca3e5fe4f` EXE 未包含此增量；新 `a65d2b2b4fd5` RC 已通過 QA117 包內正常 Main 保存／fresh 對照及 QA121 同筆記150%重開。五旅程 PARTIAL、Native停止／真人待驗與金融資格保持。

本頁說明 UI 呈現與互動契約；操作步驟、參數、安全限制、結果判讀及排錯以操作手冊為準。工作區責任與資料流見[目前架構分冊](../01_architecture/current/application_and_workspaces.md)，Recommendation、Backtest、Portfolio 計算責任見[決策、研究與 Portfolio](../01_architecture/current/decision_research_portfolio.md)。目前產品狀態以 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 為準，驗收範圍依各原 QA 收據判讀。

## 跨頁責任與搜尋入口

| 查找問題 | 正文入口 | 常用搜尋詞 |
|---|---|---|
| UI 輸入、呈現、取消與拒收過期結果 | 對應工作區及[UI Contract](#ui-contract) | DTO、generation、stale result、worker |
| 保存來源如何跨頁定位與返回 | [個股研究](#workspace-stock-research)、[觀察清單](#workspace-watchlist) | source identity、source pin、result ID、run ID、saved／current |
| Recommendation、Backtest、Portfolio 的計算責任 | [決策、研究與 Portfolio](../01_architecture/current/decision_research_portfolio.md) | application service、provider、Decimal、PIT、unknown |
| 使用者現在能用什麼、尚有哪些限制 | [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) | 固定版本、試用範圍、待辦、Gate、限制 |
| 有界驗收與原始證據 | [產品與個股研究 QA 索引](../06_qa/PRODUCT_UX_QA_INDEX.md) | feature、交付、Increment、source SHA、Native、fresh |

## 一、UI 定位

2026-09-21 候選池判讀呈現更新：首頁與每日決策的候選觸發提醒改列股票代號、指標變化原因、資料日期／品質及查看步驟；缺前次分數明示無法確認新轉強。首頁一般觸發提醒可直接前往候選池；獨立風險提示仍保留其原判讀入口。候選表以「推薦來源」的已連結／未連結／來源不一致狀態取代原始 `decision_identity` 字典，完整資料保留供原推薦與結果追溯，不改觸發規則或來源綁定。操作與排錯見完整手冊第 7.1 節。

Qt UI 不是單純顯示股票名單，而是把「資料更新、候選觀察、策略研究、推薦、持倉檢查、Agent runtime 觀測」串成可回溯的投資決策工作台。

目前入口為：

- `ui_qt/main.py`
- `ui_qt/views/`
- `ui_qt/widgets/`

主要設計原則：

- UI 只負責呈現、輸入、互動與事件轉接。
- 核心計算、資料讀寫與策略邏輯必須在 service / domain 層。
- Recommendation、Backtest、Portfolio 之間的交接必須保留來源 metadata。
- 策略、回測、績效、持倉與金融金額計算不得在 UI 內新增裸 `float` 核心計算。
- 涉及回測或推薦訊號時，必須維持 Look-ahead bias 防線。

---


## 二、頂層 Tab

<a id="workspace-data-update"></a>
### 1. 數據更新

主要 view：

- `ui_qt/views/update_view.py`
- `ui_qt/widgets/sqlite_inspector_widget.py`

主要能力：

- 每日股價、大盤、產業、券商分點與技術指標更新；每日股價一鍵更新包含 TWSE + TPEX，TPEX timeout 以 warning 呈現且不阻斷其他資料同步。
- TWSE 每日股價若明確回報失敗，單一來源流程會在 TPEX／SQLite／技術指標之前 fail-closed；只有已驗證的官方無交易日（`no_data_skipped_dates`）才允許後續流程繼續。
- 快速更新（跳過大型合併）與安全更新（CSV + SQLite）分流；兩者預設補齊結束日前最近 10 個工作日，快速更新跳過大型合併，安全更新保留完整 CSV 合併與 SQLite 同步。
- SQLite 狀態檢查、資料表檢視、唯讀 SQL preview，以及具有日期預設（單日今天、區間本月）、完整日期欄寬、穩定排序、重複顯示欄名防護、分頁控制與 stale-result 防護的檢視器分頁。
- 更新狀態卡只在 service 回傳明確的 `ok`／`success`／`current`／`normal` 時顯示綠色「最新」；`error`、`missing`、`empty`、`unavailable` 與部分狀態查詢失敗會顯示異常，不會因描述文字含「最新」而假綠。inline 摘要也會把 `success`／`current`／`normal` 統一顯示為中文「正常」。狀態 payload 缺少資料源時會清除上一輪卡片與 inline 摘要，避免殘留數字或「0 筆」被誤讀；全域檢查也會同步刷新六個核心與三個候選來源頁面的 inline 摘要；個別來源詳情查詢失敗時只標記該來源，不污染其他卡片；全域檢查失敗時九個來源摘要會同步清除舊內容並保留共同錯誤原因。尚未執行檢查的 placeholder 不會被解析成狀態，燈號維持「未檢查」。候選來源仍標示為 research-only，不會因此進入正式評分或交易流程。
- 更新頁所有「今日」日期控件都以台灣市場日期為基準，不受桌面作業系統時區跨日影響；localized `不可用` 會落到異常燈號，避免被誤讀為單純待更新。
- 更新流程的進度由外層 coordinator 統一映射，技術指標子流程固定落在外層區間內；每日資料合併會回報檔案／讀取批次／寫入批次，若沒有新 CSV 會以結構化 no-op 狀態揭露「資料已是最新」，CSV 匯出會回報查詢總筆數與已處理筆數，單一工作生命週期內不會倒退，最終資料狀態檢查完成且通過後才顯示 100%。所有 CSV／SQLite／合併／技術指標／匯出寫入工作具互斥保護，重複啟動會提示等待，唯讀來源詳情仍可並行查詢；合併／匯出取消均保留原子目標檔，不在半個檔案內提交。
- SQLite sync 在寫入前會將日期、股票代號與股票名稱的受治理中英文欄位別名正規化為 canonical 欄位，並統一日期／四碼代號格式；只處理寫入副本，不改 raw CSV，缺必要欄位仍維持 fail-closed。
- 快速／安全一鍵更新先驗證更新前總覽；核心資料源若明確回報 `error`／`failed`／`exception`，會在任何寫入前 fail-closed 並回傳失敗資料源，避免在基線已不可讀時繼續產生部分更新。
- SQLite Inspector 啟動與刷新採明確 `mode=ro`／`PRAGMA query_only=ON`；資料庫不存在、損毀或不可讀時保留頁面並顯示「SQLite 不可用」，不建立空資料庫，也不讓主視窗因 Inspector 初始化失敗而中止。若使用 immutable fallback，頁首會明示快照可能非即時。
- UpdateService 的 overview／detail／technical coverage 狀態查詢共用同一個 query-only adapter；不論資料庫是否已存在，狀態讀取都不建構可寫 `DBManager`、不初始化 schema 或切換 WAL。
- Portfolio 的目前價格／未實現損益投影也共用 query-only adapter；缺少正式 SQLite 時只降級讀取既有 CSV，不會因打開持倉頁而建立空 `twstock.db`。
- Windows 一般 read lock 不可取得時，狀態 payload 會帶 `read_mode=immutable_fallback` 與提醒；UpdateView 以黃色「待更新」及 inline `讀取模式`／`提醒` 揭露可能只到最後已提交內容，不把快照假裝成即時讀取。
- 每日股價分頁的 TPEX 背景補齊會在頁面內顯示 `尚未啟動`／`執行中`／`完成`／`失敗` 與最後更新時間；狀態 JSON 無法建立或讀取時會顯示錯誤並記錄日誌，無法可靠追蹤時不啟動背景程序，避免按鈕已顯示執行中但沒有可查進度的假狀態。日期範圍同步若發生例外也會保留可見日誌。
- UpdateView 內容使用可垂直捲動的工作區；窄版（小於 720px）會將來源導覽移到上方、六張核心狀態卡改為雙欄、候選卡改為單欄、操作按鈕改為直列，避免固定 160px 導覽與六欄卡片把資料更新畫面壓成不可讀細條。
- 券商分點資料更新、合併、長碼解密與品質狀態呈現；SQLite `broker_flows` 唯一鍵包含 `trade_type`，可保存同日買超 / 賣超榜單。
- 「三大法人」、「信用交易」、「集保股權」與「自動排程狀態」為唯讀治理頁；前三者只讀 SQLite 筆數／最新決策日期，`MISSING` 或 0 筆代表未接線或尚未匯入，不能解讀為中性數值，也不提供誤導性的下載控制。

文件同步重點：

- 更新流程改動需同步 `docs/03_data/` 相關指南。
- SQLite、CSV capture／projection 行為改動需同步 [目前系統架構](../01_architecture/system_architecture.md) 與 [每日資料更新指南](../03_data/daily_data_update_guide.md)；若影響使用者操作，再同步[操作手冊](../07_guides/APPLICATION_MANUAL.md)。

<a id="workspace-market-exploration"></a>
### 2. 市場探索

題材研究01固定候選新增「產業與題材」子頁，明選本機已保存manifest後顯示四類觀察卡、排行、產業鏈、題材、欄位覆蓋及成員；首頁入口接續同一頁。成員沿現有個股研究context往返，換股須回題材選取；來源版本與行情日期分開呈現，載入失敗不沿用舊成員。使用者判斷沿Journal追加修訂，原文唯讀，回訪核原SHA；資料缺件不補零。143原包不變；操作／限制見[題材研究](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#產業與題材後繼source)。

固定研究11另補預設收合的產業鏈卡片目錄（固定10未含；Source與同版EXE／新程序限定通過）：所有原鏈各一張卡，列題材數／去重成員數與名稱序最多三項捷徑，沿原filter／成員定位。具名QObject接收槽核原snapshot identity／忙碌／關閉，換版清舊控制；漲跌僅完整覆蓋且有限Decimal顯原值，缺件不補零，不新增來源或金融公式。

主要 views：

- `ui_qt/views/decision_desk_view.py`（「市場總覽」唯一 Decision Desk instance）
- `ui_qt/views/market_regime_view.py`
- `ui_qt/views/industry_theme_map_view.py`
- `ui_qt/views/strong_stocks_view.py`
- `ui_qt/views/weak_stocks_view.py`
- `ui_qt/views/strong_industries_view.py`
- `ui_qt/views/weak_industries_view.py`
- `ui_qt/views/smart_money/smart_money_flow_view.py`

子 Tab：

- 市場總覽
- 大盤指數
- 強勢個股
- 弱勢個股
- 強勢產業
- 弱勢產業
- 主力流向

主要能力：

- 市場總覽以 answer-first dashboard 顯示結論、焦點與來源可見性；Workbench「決策來源」只導向此唯一實例，不建立第二份 widget。
- 月營收、三大法人、信用交易、TDCC 與券商分點卡片保留 status、row count、available date、coverage 與 warning。`row_count=0`／MISSING／DEGRADED 表示缺漏，不是中性分數或業務數值為零，且不參與 action、focus、Score 或品質聚合。
- 原法人CLI可明選 `twse_institutional`，並以 `seal` 旁存成功批次小時／不可覆寫版本；正常「數據更新 → 三大法人」可用目錄、雙外部SHA與代碼唯讀重開。完整原件／品質／時間通過才呈現逐日三類整數股數與時鐘；錯誤／輸入變動清除舊結果，合作取消及新程序限定驗證。批次報表列數不是股票真N，無匹配不補零；仍candidate-only／用途未接受／PIT false，連買與原狀態卡資格不提升。固定9fa包未含；[操作及缺件](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#單獨保存-twse-法人候選)。
- Increment43新每日讀取要求原body明示股數單位與官方宣告合計，數字矛盾／證據缺件拒絕，舊原件不回填。真單日21,000報表列品質已核，原成功批次可用小時之前仍拒讀；不從單日或工程PASS推論來源用途、全股票母體或歷史／連買資格。
- Increment45已在實際可用小時後，沿同一真T86版本完成正常Main／fresh四代碼逐欄讀回及切頁返回；無HTTP／seal／apply，來源檔不變。這是候選事實檢視的真來源限定證據，授權及歷史資格仍分開，固定試用包不變。
- Increment46 原官方市場／處置頁可讀新 v3 pin 的 TWSE 英文原件，原 v2 保存語意不變；修正正向終止公文型別接線，停止與終止日期仍分開核。真名錄／處置配四股合成行情的正常Main／新程序同來源讀回通過，缺列維持unknown，原觀測不冒充今日或歷史PIT；[操作與排錯](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#官方處置原件重讀後續開發分支)。固定試用包不變。
- 「資料更新 > 全部資料」的月營收狀態卡分開顯示已匯入期別與依該期全部資料 `available_date` 判定的目前完整 PIT 可用期別；只要同一期仍有公司尚未生效，該期就會顯示在待生效數與完整可用起始日中，不會誤標成更新失敗。
- 市場 regime 判斷。
- 強弱勢股票與產業篩選。
- 強弱勢探索表格會在載入中、成功（筆數／掃描範圍）、空結果與失敗時顯示可見狀態；刷新失敗會清空過期模型，不把上一輪排名留在畫面上冒充目前資料。
- Smart Money Terminal：個股資金流向、分點進出追蹤、張數 / 金額品質標示。
- 券商 week／month／股票明細採背景查詢並具 stale-result guard；loading 與單一來源錯誤不凍結主 UI，錯誤以 fail-soft warning 呈現。
- 可把觀察標的送入候選池 / Watchlist。
- 候選池在載入中、成功、空清單與失敗時都顯示可見狀態；空清單／失敗使用真正的空模型，不插入 `-` 佔位列，避免把狀態提示誤讀為候選標的。
- V4.2 C 線的市場焦點卡接到共用 `DecisionPresentationDTO`，顯示研究動作、證據品質、理由、風險、資料日與來源追溯；市場焦點仍是研究輸入，不直接產生正式 Advice 或買賣指令。

### 固定法人與官方資料研究

Source的題材法人v2只消費明選TPEx同日原股數，缺價格／TWD／日曆不補值。首屏白話標示僅上櫃diagnostics與上市／興櫃／未知市場未納入；部分法人合計／家數／比例標示已覆蓋成員，零覆蓋家數顯示未提供與0/N，有觀察的原零值保持。完整排行仍只取全成員覆蓋，不將partial極值混入。QA200 compile／61PASS、2個環境symlink略過／85／25-0-4／mypy1082；UI既有ignore不證強型別。201a真v2原件、202e正常Source與209a固定10同版EXE／新程序已限定通過，09未含；[操作與限制](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#tpex法人題材診斷source-v2)。

法人長來源身份下的表格使用自然垂直下限，顯示／清除／錯誤後通知外層重新配置；不固定整頁高度、不縮刪來源／資格說明，也不改九個原整數股數。先垂直捲到表格底，再水平捲到最後欄。QA189b舊08裁切FAIL保留；Source QA190定向21、Workbench85、validator25／0／4及mypy1082，191a正常Main35948→28512逐欄可到達與重開通過，尚非新固定EXE／Native或真人接受。詳[法人表格修復](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#法人表格可操作性qa189191a)。

固定法人唯讀區可明選 TWSE 與 TPEx OpenAPI 批次；身份列顯示已核市場，九個股數值仍沿原 int 投影，不猜 market、不觸發資料取得或金融重算。來源錯誤、未到可用小時、pending 或輸入換版時清除舊結果，候選與 P0 資格邊界保留。操作見[TPEx 單日指南](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#tpex法人openapi單日版本後續開發分支)。

固定法人區的用途接受檔與 SHA 必須成對明選，沿原三參數 signal、不可變 request pin、owner worker、generation 與取消路由；只有 TPEx typed diagnostics 顯示接受 ID、SHA、時間與來源顯名。裸 True、錯市場或 scope 拒絕；無 pin 維持原 candidate 讀取，讀取不重寫來源或接受狀態，也不觸發抓取。操作見[用途接受指南](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#tpex法人用途接受與重開後續開發分支)。

文件同步重點：

- 籌碼、分點、資料品質語意改動需同步 `docs/04_broker_branch/`。
- Regime 或 scoring 輸出語意改動需同步 `docs/02_features/SCORE_EXPLANATION.md`。

<a id="workspace-decision-workbench"></a>

後續 Source 的每日候選明選控制項位於首頁候選列下方，無須展開技術工作台；多檔先選、單檔預選，來源／日期／逐列身份改變清選擇。context 攜原 result/source/snapshot/date，返回要求原首頁身份仍相符。stale 仍不能作今日候選，但可明示讀回精確原保存結果，沿推薦頁既有 single get／身份與取消守衛，不重跑或挑 latest。個股筆記沿原 candidate Journal，缺行情或ML不補值。固定03未含；具名 Source／真來源回放／正常入口界線見[本輪 QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#首頁真保存候選閉環qa118123)，操作見[每日決策](../07_guides/APPLICATION_MANUAL.md#8-每日決策-daily-decision-desk)。
### 2.5 決策工作台

主要 view / model：

- `ui_qt/views/workbench_view.py`
- `ui_qt/models/workbench_table_models.py`

主要能力：

- Phase 2 Unified Decision Workbench MVP shell，頂層分頁名稱為「決策工作台」。
- 總覽第一屏新增「今日行動中心」：只用既有 `WorkbenchDashboardDTO` 的資料狀態、review items、Advice DTO 與 Action Items，整理資料／市場／Advice／持倉四張行動卡與一個下一步按鈕。按鈕僅呼叫既有數據更新、Daily Decision、推薦分析或持倉管理導覽 callback；不讀 DB、不更新資料、不執行 Policy、不寫入持倉或交易。
- 主 shell 使用 `ui_qt/widgets/adaptive_workspace_stack.py`，只讓當前可見工作區貢獻尺寸提示，避免隱藏工作區的圖表／設定面板鎖死視窗最小尺寸；主視窗在窄桌面寬度會暫時收合左側導覽，但不改變 workspace、資料載入或 service 行為。
- Runtime 窄版（小於 720px）會把治理左右面板改為上下排列，並以內嵌垂直捲動保留完整診斷內容；Session context status strip 會依可用寬度截斷文字。主視窗明確窄版下限為 320px，避免 Runtime 的長路徑提示把視窗鎖在桌面尺寸。
- 第一版已從中文 read-only shell 推進到 background evidence feed / read-only Action Items 人工佇列體驗，並完成 Phase 2 read-only Operating Loop closeout：呈現 status strip、今日待判讀、背景證據流、依 severity / queue group / source 排序的只讀 Action Items、操作節奏、Evidence mode / data quality、Daily Checklist、warnings / degraded source。
- 只透過 `WorkbenchSourceService` 取得 `WorkbenchDashboardDTO`，或直接呈現呼叫端提供的 DTO；UI 不直接讀 SQLite、不讀 replay DB、不寫 DB、不啟用 scheduler。
- 主程式開啟後，Workbench 首次讀取與重新整理由受管 `TaskWorker` 在背景取得唯讀 DTO，不會在建構主視窗時同步讀資料；Research Console 只在第一次切入「研究證據」分頁時載入。SQL／artifact 讀取支援合作式取消；主視窗關閉會取消這兩項讀取並等待安全結束，舊日期／成本情境結果不會覆蓋最新請求。狀態與關閉診斷只記錄階段、耗時與 worker 數，不改 DTO、財務計算、正式資料 writer 或交易邊界。
- Workbench 的 current Decision Desk／Pre-V2／Evidence projection 以台灣市場今日為日期上限；正式來源若含 future snapshot，畫面保留 raw future date 的 warning／source gap，但不把它當成 current evidence 或完成 gate。
- 背景證據流只彙整既有 DTO / service payload：Daily Decision snapshot、Evidence Review readiness、Portfolio alerts 與可選 replay summary diagnostics；不在 UI 端重算任何 source gap、portfolio、scoring、backtest 或 lifecycle。
- 只讀 Action Items 只列人工待處理事項；每列必須帶 `severity`、`queue_group`、`source_label`、`source_trace`、`degraded_reason`、`sort_rank` 與 `drilldown_target`，且 `write_intent=false`。Qt model 只顯示 DTO payload，drill-down target 必須對齊舊頁導向（Daily Decision、Evidence Review、Portfolio），Workbench 不建立 action item repository、不 append DB、不自動標記完成。
- Read-only Operating Loop 只從 `WorkbenchDashboardDTO.operating_loop_steps` 顯示 daily first-look、manual queue、weekly review history、multi-day dry-run、manual review note 與 scheduler gate；每列必須帶 `source_trace`、`linked_item_ids`、`drilldown_target`、`guidance` 與 `write_intent=false`。Qt model 不標記完成、不寫 DB、不補 Phase 0 時間 gate。
- 若週期紀錄位於隔離 working-copy DB，Workbench 只會讀取 owner 明確提供的 `approved-weekly-history-projection.v1` 路徑，絕不掃描暫存目錄或合併 DB；projection 固定 `formal_credit_authorized=false`，僅顯示已具名核准的 weekly Gate 計數，不構成 formal clock credit、scheduler、交易或任何下游資格。
- Evidence Feed、Action Items 與 Operating Loop 空狀態必須說明「目前沒有 DTO rows」不等於 gate passed 或 actionable 建議；degraded 狀態只提醒人工覆盤資料不完整，不補值、不觸發 replay / scheduler / lifecycle。
- Advice 區以 `WAITING_FOR_ADVICE_DTO`、`NO_ELIGIBLE_ADVICE`、`ADVICE_DTO_ERROR` 分別呈現尚未載入、已載入但無合格建議、與 DTO 損毀／安全拒絕；來源降級但仍有有效 recommendation 時仍渲染表格與 warning，不得誤標為 DTO error。
- V4.2 C 線把決策工作台、Daily Decision／市場總覽、產業探索、觀察清單與持倉覆盤標成單一路徑：`市場總覽 → 產業／市場探索 → 關鍵股研究 → 觀察清單 → 持倉覆盤`。Workbench 提供市場、產業、觀察清單與持倉導覽；關鍵股研究則由市場焦點、觀察清單或持倉列選取個股後，透過 `ResearchStockContextDTO` 開啟個股研究報告。
- 後續 Source 候選的 Paper 健康區提供明選列導覽：「在持倉管理查看此 Paper 部位」。Workbench 只把已驗證的完整 `PositionHealthReadModel` 與唯一 `position_id` 傳給 Main；Main 先請 Portfolio 排入下一輪 refresh，接受後才切頁。Portfolio 自己呼叫 `read_latest`，只在完整 read model 與唯一部位列仍相同時切到 Paper 帳並定位；變更、缺件、失敗、取消、過期或關閉都保留既有帳本選擇，不回退到手動或聲明持倉的同股票列。一般持倉入口仍維持單純工作區導覽；左側可切回決策工作台，切頁本身不代表重新核驗。評估日、observed_at、available_at 不等於行情估值日，此功能也不重開歷史 saved receipt／snapshot。未納入固定03，正常 Source Main／新程序的控制資料往返與1280可視列已驗，真實 Paper 原件旅程尚未驗，不能據此宣稱 Paper 自然成熟、金融資格或真人接受；操作見[觀察清單與持倉手冊](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md)。
- 市場焦點、觀察清單分析、Advice、持倉詳情與個股報告共用 `DecisionPresentationService`／`DecisionPresentationDTO` adapter；所有畫面分開呈現排名分數、校準機率、成本後獲利機率、動作適合度、證據狀態／信心、樣本數、適用期間、理由、風險、失效條件、權重差距、決策日、資料日與來源追溯。排名只作排序，不能推導任何機率；缺值固定顯示未知／研究中並 fail-closed。
- 觀察清單以研究／等待與買進候選的既有來源理由、風險、失效條件為主；持倉則將既有 condition monitor 的 valid／warning／invalid 映射為持有／減碼候選／退出候選，並揭露 target／current／gap 權重與成本基準。這些都是唯讀判讀與候選分類，不是自動下單、調倉或平倉。
- 相關決策頁面均補上 status、decision/data-as-of date、source trace 與可返回來源的 context；研究報告沒有來源時隱藏返回控制，避免製造虛假導覽。表格採單列選取、禁止編輯、StrongFocus、Tab 導覽、交替列色與窄版捲動；完整證據移至可選列的詳情區，避免主表塞入低價值長文。
- 共用 adapter 對不支援的 Advice DTO 或非法 bp／機率欄位拒絕適配，不把 ranking score 轉成 probability，也不由 UI 補算權重差距或核心金融數值；契約測試涵蓋欄位分離、字串 bp 正規化與缺值狀態。
- Optional Historical Replay JSON summary 只作 simulated evidence input；若 DTO 帶 replay summary，data quality 區塊必須揭露 `simulated_scheduler`、source gap、payload gap、outcome maturity、benchmark coverage、missing industry benchmark 與 pending future-data。
- Workbench `Evidence` 子頁已由 placeholder 替換為唯讀 `ResearchConsoleView`：三區依序顯示固定 fail-closed Safety Boundary、Development Dataset V0 / Rule baseline / ML challenger / E2E frozen projection，以及 EV1–EV5、P0-13、獨立 Broker lane、P0 Data Source Control Center 與 Artifact Inspector。Control Center 固定保留 13 個 P0 source，顯示 contract、machine/audit、人工 decision、blockers 與 downstream eligibility；沒有 audit artifact 時明示 `contract_only`／`Not supplied`，不把缺資料誤顯示為 ready。資料只來自 `ResearchConsoleSourceService` 的 injected mapping 或顯式 sanitized JSON path；缺 artifact / 欄位顯示 Missing / Unknown，不補零、不讀 DB、不重算 domain logic。
- Research Console 不提供 Apply、Promote、Retrain、Blend、Accept Source 或 Trade；development / candidate / provisional / degraded / fixture / replay 以文字狀態與顏色共同區分，不能解讀為 formal OOS、forward evidence、source accepted 或 production ready。
- Research Console 頂端先顯示中文結論（Rule 使用中、ML 未參與、正式輸入缺漏或投影過期），原始 machine token 與技術診斷預設收合，按「顯示技術診斷」才展開；這只改變讀取順序，不改任何 gate。

防線：

- 不重算 scoring、recommendation、portfolio、backtest 或 lifecycle。
- 不產生買賣建議、不下單、不套用 lifecycle action。
- Phase 0 weekly history 與 multi-day dry-run 只顯示具名 owner-approved projection 提供的 readiness；計數會隨來源變更，本文件不固定保存 `3/3 ready` 等即時數值。`formal_credit_authorized=false` 時，read-only readiness 不構成 Formal evidence credit 或 production scheduler approval；pending sidecar 週期仍須 owner/reviewer 審核，不能用 fixture、手動改表或 replay 取代。最新狀態以 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 與具名 QA 為準。

### Gate 1 Advice（決策工作台）

決策工作台在 DTO 已提供 Advice 時，會顯示 mode、decision / data-as-of date、action、理由、資料品質、可成交性、source trace，以及 Portfolio 的 target/current/gap。畫面是唯讀：不會建立委託、寫入資料庫、套用 lifecycle 或重算 scoring / portfolio / backtest。

- Guided Mode 只接受 promoted strategy；Professional Mode 的 candidate 僅供研究檢視，不能混作 formal Advice。
- `NO_NEW_POSITION`、`RESEARCH`、`AVOID` 是資料、風險、可成交性或策略狀態不符合時的正常安全輸出，不表示系統故障。
- 平衡限制為最低現金 `2000 bp`、最多 8 檔、單檔上限 `1500 bp`；UI 只呈現 contract 結果。
- Advice 不保證報酬、不是 broker 指令，且不解除 weekly evidence、production scheduler 或其他產品 Gate。

<a id="workspace-backtest-research-lab"></a>
### 3. 策略回測

主要 views：

- `ui_qt/views/backtest_view.py`
- `ui_qt/views/backtest/config_panel.py`
- `ui_qt/views/backtest/result_panel.py`
- `ui_qt/widgets/fast_chart_widget.py`

主要能力：

- 單股回測、候選池批次回測、推薦組合回放。
- Strategy registry / preset / promotion 整合。
- Walk-forward、baseline comparison、overfitting risk、validation status。
- Fixed / quantile threshold mode UI 控制與無交易診斷。
- 結果保存已接入 Research Run Registry；Research Lab 內新增 Registry 比較子頁，可篩選、分頁、多選 2 至 5 個非推薦回放 run，顯示 comparability、參數差異、normalized equity、metrics、Regime 與保存 benchmark。推薦回放不由通用 metadata 比較授績效資格；選到推薦回放時停用「比較選中」，由兩筆 exact run 的完整期間診斷分列來源、日曆、幣別、成本與原觀測，缺件維持阻擋。推薦回放另要求完整 DTO 才能新存為 marked Registry run；單選可走 strict reader 開啟保存的 DTO 與已驗證 child，不重新執行，也不進 legacy portfolio history dropdown。舊 markerless Registry run 明示完整 DTO unavailable；marked DTO 沒有 canonical child 時，若保存 snapshots 有推薦列則保留並標明 child 不可用；snapshots 為空則顯示沒有推薦 snapshots、canonical child 不可用。損毀或錯誤 hash 不顯示 partial 結果。Registry-based Promote Gate 已接入 service 層，且 Month 6 起需通過 lifecycle gate；策略版本 JSON 與 Registry 回填具補償與 reconciliation 防線。
- 後續開發來源可在同一 Registry 恰選兩個原 `1.0.0` 基本策略，按「對照兩個基本策略」只讀並列同條件、同實際期間的原保存版本化摘要，逐側開原 run 明細並返回同一對選取；缺來源、成本或實際期間條件時不顯示並列值。通用「保存條件相同」標籤不授歷史績效／PIT資格；一般單股比較在成本或期間不符時清除數值區。此子旅程尚未納入固定 `ec5c95733608` 試用包，也未完成來源／成本權威及完整雙策略績效。
- 規格化 Excel 報告匯出：單股、批次及組合回放結果的背景原子匯出，缺值自動標記 N/A。
- Fast chart renderer：權益曲線、回撤曲線、報酬分佈、持有天數。
- 策略回測日期欄與 Research Lab 證據覆盤日期篩選採受控日曆 popup；回測日期開啟時定位今天，未設定的 evidence 日期篩選也定位今天，不落到 sentinel 年份。
- Research Lab「證據覆盤 > 排程狀態」會分開顯示 freshness warnings、pipeline warning 與 advisory 的 occurrences / unique types、pipeline overall status、推薦結果 research-only write 與 production evidence / trading write risk；pipeline degraded 時不會只因 exit code 0 顯示為 passed，`ready_with_advisories` 也不會被誤標 degraded。
- Research Lab「覆盤歷史」dashboard 採 query-only history repository；缺少 history DB／table 時顯示明確唯讀診斷與建立指引，不會因打開畫面而初始化空 schema。
- Research Lab 的 Paper 保存快照查找可選擇外部 artifacts root，沿用 Research Lab 策略版本來源，並要求明示策略、版本、帳戶命名空間與含時區截止時間，再列出最多 200 筆候選供使用者選取讀回；截斷時會明示。未設定或無效的 root 只停用 Paper 查找；不自動選取候選、不建立／更新資料。候選清單本身尚未核對；即使 exact 讀回成功，也不代表底層來源可得性或績效資格已驗證。關閉工作區時取消未完成查找並拒收過期回覆。

### 策略研究、保存版本與歷史卡

原P07新增「四均線多頭排列（研究）」1.0.0，固定四期、不套分數門檻；診斷顯示可判讀／不可判讀列及進出場意圖。執行、保存、查原規則／結果、返回與fresh沿正常單股入口，保存前後排列與10個來源SHA；缺件不回退舊Score診斷。原撮合／精度／來源與研究禁止晉升守衛保留；批次與參數研究未驗。操作見[四均線指南](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#四均線多頭排列研究)，實際平台範圍依[119 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment119-ma-alignment)。

後續 source 分支可在原策略回測清單加入「W 底頸線突破（研究）」1.0.0，參數為第二谷確認後等待 5／10／20 觀測列，預設 20；原規則、執行／保存、歷史與保存版本來源／結果、切頁返回與 fresh 沿原入口。摘要顯示可判讀／不可判讀及進出場意圖；已知 schema 缺件明示不可用，不回退為 50 分或布林 band；暖機、缺行情和失效重啟均不可判讀。保存前改畫面參數仍保存當次凍結 request；錯 identity／股票／期間／本金／成本／params 拒絕，requested 與實際窗分列，收尾取消不發布完整來源。研究不可正式晉升，原金融與來源守衛保持。操作見[W 底指南](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#w底頸線突破研究後續開發分支)。固定 0f644faa 預覽未含此增量；批次／參數研究／Walk-forward 與 Native／EXE 未驗。

後續 source 分支也可在原策略選單加入「布林基礎突破（研究）」1.0.0，僅顯示突破確認 1／2／3 交易列；原規則、執行／保存、歷史規則與結果、保存版本來源及返回沿原入口。摘要顯示可用／不可用觀測與進出場意圖日數，不套分數門檻；進場意圖、實際成交及完成配對分開。研究版阻止正式晉升；close／加碼／ATR 等未核設定明確拒絕，不暗自忽略。操作見[布林基礎指南](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#布林基礎突破研究後續開發分支)。正常 Main／fresh 的限定證據與操作見[布林基礎指南](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#布林基礎突破研究後續開發分支)；固定 0f644faa 預覽未含此增量，其他模式未驗。

已保存策略版本區可手動刷新、翻頁、明選後查看原規則或開原結果；保存版號與來源執行版號分列。缺件／metadata-only 不開啟；取消、換選、新研究及關閉拒收過期結果。沒有新增 promotion、執行舊版本或調參動作；保存狀態不代表資格。操作見[保存版本指南](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#已保存策略版本與來源研究後續開發分支)。Main／fresh 的限定證據、空清單與舊版排錯見[保存版本指南](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#已保存策略版本與來源研究後續開發分支)；固定 0f644faa 預覽未含此增量。

PF 摘要顯示有限無量綱值或具體不可用原因，None 不再中斷格式化；批次／最佳化表附狀態與語意，舊比較不把未版本化值當有效 PF。固定 9fa EXE 尚待窄版修補；QA262 正常 Main／fresh 成功不等於新 EXE 交付。操作見[PF 指南](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#獲利因子的可用性與舊結果)。

單股歷史卡區分新宣告版本與舊未版本化結果。新卡逐欄綁定所選 metadata、原指標與摘要，顯示原實際期間、單位及已完成配對；不以 0 推論勝率、平均或無期間 CAGR。qualification 維持 unknown，comparability 未評估；不是完整雙策略績效或原精度升級。查找、開啟結果、換頁返回與新程序沿同一 run。操作見[歷史指標指南](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#新單股保存結果的歷史指標後續開發分支)。固定第一版不改版。

### 單股結果語意與 1366px 版面

Increment71 將策略回測視窗整理為 1366px 下左設定、右結果；三種歷史／版本／Paper 查找預設收合並互斥展開，摘要文字可在自身區域捲動。固定 ec5c95733608 包不變，後續交付須看[Increment71 原 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment71真人試用回報的四流程可用性修正)與候選收據。

單股 next-open 結果不跳過未成交日的收盤估值／取消；預存 MACD 重用提供計分器正式別名，已有值可用，缺值與暖機維持未知。正常真 2317 低本金與有買入的高本金結果已保存並在新程序按原 run 讀回，舊結果不改寫。完成交易數是進出場配對，零配對顯示「尚無已完成交易」；即時結果分列原成交與期末持股，缺值為未提供，歷史頁不由空配對表推論零成交。缺分數／門檻不推論原因，未平倉估值不當已實現損益。固定 9fa EXE 正常保存／歷史返回／fresh 已驗，計算及保存格式不變。來源、成本與 PIT 資格不由本修復授予；詳[Increment36 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment36v1單股回測未成交日的金融正確性)及[Increment37 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment37v1回測零完成配對的正確判讀)。

回測防線：

- 回測訊號只能使用決策當下可取得的資料。
- `next_open` / `close` 撮合假設必須透過 metadata 或 warning 呈現。
- Quantile 模式的門檻需由策略執行器輸出，不應在 UI 或 service 端用完整期間重算。

文件同步重點：

- 回測邏輯變更需同步 `docs/02_features/BACKTEST_LAB_FEATURES.md`。
- 策略參數與門檻語意變更需同步 `docs/02_features/STRATEGY_DESIGN_SPECIFICATION.md`。

<a id="workspace-recommendation"></a>
### 4. 推薦分析

主要 view：

- `ui_qt/views/recommendation_view.py`

主要能力：

- Profile / mode / strategy config 推薦。
- Why / WhyNot / Explain panel。
- Explain 的圖形理由會顯示 rolling detector 已確認的型態名稱、方向與距確認日；若只有方向訊號而沒有型態名稱，會顯示保守的 generic 圖形訊號，不從分數臆測具體型態。
- Regime snapshot 與推薦 metadata 保存。
- 推薦結果保存與 round-trip 載入。
- 一鍵送策略回測。
- 送 Research Lab 批次回測。
- 推薦結果表的單股研究按鈕、雙擊與右鍵入口會建立 `ResearchStockContextDTO`，帶入股票、決策日、資料日、結果 ID、Profile 與來源 workspace；市場探索頁的共用 context strip 可顯示這些欄位並返回來源清單。
- 「官方市場與技術條件研究」是使用既有保存來源的獨立子頁，不執行推薦評分；支援技術、四均線、KDJ、波動率條件群與官方市場／處置外層條件，明示 AND／OR、未知政策、全域排序及每頁最多 256 列。資料缺件或可得時間未知時保留未知／來源限制，不推成 Advice、歷史 PIT 或交易資格。操作見 [APPLICATION_MANUAL §6.7](../07_guides/APPLICATION_MANUAL.md#67-官方市場與技術條件研究)。
- 保存母體的選版、篩選、翻頁及返回讀取沿受管背景 worker 執行合作式取消；取消保留最後已核結果，晚到結果不覆蓋新請求。已開始的檔案讀取會安全排空後收尾；等待狀態結束再重試，不強制終止執行緒。此接線不新增操作參數；千檔效能、完整 Main／原來源／同版 EXE 與真人驗收仍依具名 QA 分別判讀。
- 建立候選池 / Watchlist。
- Fixed / quantile 門檻模式與 eligible universe 橫斷面百分位排名。
- 可選月營收 YoY 最低值與 PE 最高值篩選；啟用時只讀 `available_date <= decision_date` 的 PIT 基本面版本，無法標準化決策日期、缺 PE／去年同期營收或不符門檻者寫入 screening matrix 的 `skipped` 原因，不補零也不讀未來資料。
- 目前推薦 Excel 報告匯出：包含今日配置、Regime 狀態與股票名單的背景原子匯出。

推薦防線：

- Quantile / percentile 推薦必須先固定當日 eligible universe。
- 母體不足時應拒絕降級並顯示可理解錯誤。
- 排序需穩定化，避免相同分數因輸入順序造成結果不可重現。

### 價格選股、來源回訪與結果篩選

Increment118把正常Main價格結果的已核驗stock／selection直接交給既有個股工作區，以獨立來源頁展示保存價量與原五規則；一般報告與H20頁留在另一容器，不把舊四股報告當成目前選股內容。原來源返回、比較籃及bookmark schema沿用，Main以外宿主保持原dialog；值只作展示投影，不補資料、重算指標或升格來源用途。操作見[同源個股研究](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#官方條件與價格研究)，實際接受範圍見[QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment118-price-stock-workspace)。

固定 ec5c95733608 本機候選將每日研究長頁拆成預設「價格選股」及每日快照／兩個進階母體子頁。價格選股保留原 catalog、嚴格來源核驗、query、比較、收藏及返回契約；首屏顯示資料日、母體、處理數和不可選原因，原路徑／SHA 可展開。單股回測同 run 摘要並列完成配對、成交、明細及期末持股；歷史缺欄維持未知。四股漲跌方向只在隔離試用價庫中，從同股同日、同收盤與同價差的正式唯讀列精確補接；舊包和正式資料不變，不授歷史 PIT 或完整績效。固定入口為 output/trial/Baldr-Daily-Research-66/Launch-Baldr.cmd；同目錄指南與已知問題列出四股及原技術來源路徑限制。受改 source 測試與 UI 共同防線、正常來源／同版 EXE Native Main 與新程序的限定旅程、真人試用及未接受範圍見[Increment66 原 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment66日常研究修正版候選依原計畫04)。

成功載入／套用後，價格選股收合條件表並將它移到結果區；表格上方保留修改條件、符合數、翻頁、逐股比較與收藏入口，完整分母／排除原因可展開。錯誤或取消保留原已核結果，翻頁、來源返回與收藏重開不套新的自動捲動；操作見[價格選股指南](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#官方條件與價格研究)及[Increment70 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment70價格選股載入後顯示結果)。

Increment71 價格結果列雙擊維持原保存來源的獨立研究視窗，不導向個股研究主頁；「顯示此來源全部股票」重設本頁篩選，摘要分列已處理與目前條件符合數。逐股比較須選取兩筆同來源資料，單筆選取可建立研究收藏；該收藏的保存來源及精確重開見[觀察清單](#workspace-watchlist)，個股研究身份與返回契約見[個股研究](#workspace-stock-research)。固定 ec5c95733608 包不變，是否交付新版以[Increment71 原 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment71真人試用回報的四流程可用性修正)與候選收據為準。

第一版價格研究窄結果區將每日研究頁的價格條件、規則篩選與比較操作直向排列；價格區和表格受可視寬度限制，不再依賴外層隱藏水平捲軸才能選股。保留原 widget／輸入／query／bookmark 及來源資格，獨立視圖仍沿原高度配置。固定候選 1024px 的套用、比較、個股返回、收藏、新程序 exact 重開已限定驗證，其他尺寸與真人未全驗；詳[Increment35 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment35v1價格條件在窄結果區可操作)。

文件同步重點：

- 推薦分數與百分位語意需同步 `docs/02_features/SCORE_EXPLANATION.md`。
- 推薦策略 contract 需同步 `docs/02_features/STRATEGY_DESIGN_SPECIFICATION.md`。

<a id="workspace-watchlist"></a>
### 5. 觀察清單

主要 view：

- `ui_qt/views/watchlist_view.py`

主要能力：

- 候選池 / watchlist 管理。
- 從 Market Watch、Recommendation、Backtest 取得候選標的。
- 支援後續送入 Backtest / Research workflow。
- 觀察清單單股下鑽會只讀保存結果 metadata 取得來源 ID／資料日／Profile，無保存結果時保留明確缺漏，不重新計算推薦或猜測來源。
- 支援官方市場與技術條件研究的專用收藏列；儲存原來源、查詢、頁面、選取與比較狀態，從列按「查看選中個股研究報告」或雙擊會沿固定來源重新核驗後重開，失配時不改讀最新來源。
- 選取標的時以共用呈現契約顯示既有保存的排名分數、排名百分位／方法、樣本數與理由；校準機率沒有合格來源時固定顯示研究中／不可用，不補值。
- `saved` 只代表有保存的研究結果，動作適合度仍為研究；`not_in_result` 不解讀為看空，也不轉成 0 分。

Increment71 可將價格選股的單一結果列存為研究收藏；來源 ID、日期與 query 仍沿本頁原 bookmark contract 保存。此情況不代表比較選取：逐股比較仍須兩筆同源選取，完整互動見[推薦分析價格選股契約](#workspace-recommendation)。

文件同步重點：

- Watchlist 語意若改為正式投組、研究候選池或交易候選池，需同步 Snapshot、User Guide 與 architecture。

<a id="workspace-portfolio-management"></a>
### 6. 持倉管理

Increment47 在同一「配置研究封存」新增首次策略／Health 成對來源：明示策略、版本與 namespace，載入候選後選來源及股票，比較並保存；未保存不能下鑽，保存後同步為同一 Paper 帳本並回原 target／個股／返回／重開。Main 僅在既有 PERSONAL／合約根可用時注入 provider。Increment68 將清單限於 Health 收據在評估日台北當天已保存者，標出原可得時刻與跨日排除數；比較以該原時刻重核 exact 帳本及 Health，保存仍沿 preview 時鐘重核。股票提示限同帳本已持有且具同源 Health／行情，未持有候選不補零。缺 thesis／條件／指標／日曆或未持有候選來源仍不可比較，v1 strategy 拒絕規則與原配置限制保留。正常 Main／fresh 已限定驗證合成來源，真來源、手動／聲明初次來源與完整 P06 尚待；固定 ec5 試用包不含此後續修正。

Increment44 補齊封存情境到個股的實際內容：保存後鑽取顯示原帳戶現金／NAV、股數、mark／市值、Health 及三情境 targets，保留 hash／時鐘與未知；預覽未保存會提示先另存。帳戶或來源不符拒絕，失敗／取消／換股清舊投影；完整帳本未持有候選股顯示 0 股，不用今日手動帳代替。正常 Main 與新程序同封存讀回已限定驗證；初次來源與完整 P06 仍待，固定試用包不變。

後續開發分支新增「配置研究封存」進階分頁，沿既有私人 scenario store 明選帳種／portfolio／artifact，讀回完整現金、NAV、股數與維持／等權／明示配置；可改原股票範圍內的整數 bp target，沿原事實、時鐘與同 policy hash 比較，再另存不可變研究假設。不是當前帳本或交易，缺初始 Health／現金／行情不補值。返回個股核同 artifact，新程序以保存 hash 明選重開；未配置／唯讀／空庫及版本錯誤各自顯示。固定 `9fa4518c` 試用包不變，完整 P06 尚待；詳[操作指南](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md#配置研究封存與另存假設)。

後續 Increment40 使回測／規則卡／Walk-forward／參數掃描保留真實登記版本，暴衝與穩健策略不再被新 run 錯標 `1.0`。未知或衝突版本在啟動前提示並拒絕；掃描整輪固定同一版本。正常 Main 保存／歷史返回／新程序 exact 重開兩策略已驗，舊 run 原樣保留；固定試用包與來源資格不變。詳[回測指南](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#選模式和研究範圍)。

Increment57沿原歷史「查看保存規則」提供兩策略fixed next_open新實驗的當次規則來源：顯示實際門檻、成本、風控及來源，改目前設定後仍讀同一保存run。錯來源／版本／成本拒絕，歷史只讀；正常Main及fresh已限定驗證。舊baseline v1與舊run不改，來源核對不授PIT／績效／正式資格，固定試用EXE尚未含此增量。

主要 view：

- `ui_qt/views/portfolio_view.py`

右側子 Tab：

- 交易歷史
- 覆盤日誌
- Paper Portfolio
- 情境壓力
- 策略與價格監控
- 生命週期回顧
- 籌碼監控

主要能力：

- 手動記錄交易並投影目前持倉。
- 「匯入交易 CSV」先做 UTF-8／CP950、欄位、買賣別、數值、日期與重複交易 ID 預覽；只有檔案 hash 未變更且使用者二次確認後，才由 `PortfolioService.record_trades()` 批次驗證並 append，取消或錯誤不寫入。
- 交易歷史提供常駐的「刪除選取交易」操作；只有選取一筆原始交易時才可按，經確認後交由 `PortfolioService.delete_trade` 驗證剩餘交易仍可重算合法持倉。持倉彙總列不會直接刪除整檔歷史。
- 保存 Recommendation / Backtest / Strategy Version 來源 metadata。
- 顯示目前價格、未實現損益、停損 / 停利與條件監控。
- 一般持倉／聲明持倉研究的日曆核驗預設使用即時 UTC（live_now）；只有明示注入歷史 clock 才用 historical_as_of。行情資料日、來源取得時間與有效期分開；歷史觀測不授 PIT，過期／缺件不補為新鮮。未新增模式切換控制項；操作與排錯見[持倉手冊](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md)。
- 已保存 Paper-main Health 提供明示選取、持倉列選擇與 exact receipt／snapshot 回訪；正常 Main 關閉後可在 fresh Main 重新核驗保存偏好。缺件與 WATCH 保留未知，不讀最新結果補件，也不由此入口執行 producer 或交易。操作依[已保存健康評估與回訪](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md#已保存健康評估與回訪)，服務契約依[目前架構](../01_architecture/current/decision_research_portfolio.md#saved-health-的-exact-consumer-與回訪偏好)；最新 QA 與完整工作包未接受範圍依 Snapshot。
- 決策工作台的 Paper 部位導覽是另一條 same-version 當前表定位路徑：Main 僅在 Portfolio 接受排入後切頁，Portfolio 下一輪刷新再用自己的 read model 比對全部版本與 position identity。它不取代已保存健康評估的歷史 exact 回訪，source mismatch 時不選同股票的其他帳本。此 Source 候選尚未納入固定03；正常 Main／新程序未驗證。
- 頂端摘要只顯示有最新價格持倉的「持倉市值（未含現金）」；缺價格會顯示 N/A 與缺漏股票，不把投入金額／已實現損益冒充完整 NAV。
- 情境壓力：由 `PortfolioStressLabService` 對已標記持倉套用固定、可重播的研究情境；缺價只做部分計算，輪動／來源中斷等缺少必要輸入時 fail-closed，不寫資料、不改持倉、不產生交易指令。
- Stress 歷史：按「保存研究快照」並經明確確認後，才由 `PortfolioStressHistoryRepository` 以 hash-idempotent append-only 方式保存目前情境結果；下方歷史表由 `PortfolioStressHistoryReadService` query-only 讀取，缺 DB 不初始化，固定揭露研究用途與 `writes_allowed=false`。
- Paper Portfolio：由 `PaperPortfolioReadinessService` 唯讀讀取 daily status、append-only snapshot 與可選 Equal Weight ledger；畫面顯示 raw 累積筆數與最新可採用 snapshot，遇到 future row 會保留 blocker／diagnostic、降級並排除於 current projection。缺 snapshot、benchmark 或成本帳時明示 `partial`／`degraded`／`not_computable`，不建立 schema、不把 paper 結果冒充正式持倉或投資績效。
- Paper Trade Ledger v1：由獨立 append-only contract 保存研究用 fill event，要求 requested／filled 數量、狀態、Decimal 成本、turnover、execution gap 與來源；Portfolio readiness 會唯讀顯示 ledger 狀態與 full／partial／reject／override 統計，缺欄位不放行 weekly report。
- Paper 成交 CSV：Paper Portfolio 分頁可先預覽完整 execution CSV，要求狀態、reference／fill price、Decimal 成本、turnover、execution gap 與來源事件；只有二次確認且檔案 hash 未變更才由 `PaperTradeImportService` atomic append 至 Paper Trade Ledger，不更新手動 Portfolio、snapshot 或 broker。
- Paper 成交範本：同一分頁可先匯出只含受治理欄位標題的空白 CSV 範本；範本不填入示例成交、拒絕覆寫既有檔案，也不建立 ledger。填入真實 execution 後仍必須回到 Paper 成交 CSV 的預覽／二次確認流程。
- Paper weekly evidence v1：Portfolio 的 Paper 分頁可按「計算最近週報」，以最近 snapshot 邊界唯讀讀取 Paper snapshot、Equal Weight ledger 與成本帳，顯示毛／淨報酬、benchmark、淨超額、成本、換手與觀測日數；未來 period／snapshot、期間邊界、成本欄位或 ledger 缺件時維持 `partial`／`degraded`／`not_computable`，不補值、不寫資料。Equal Weight builder 也會在 preview／apply 前拒絕 future snapshot。
- 顯示策略版本或推薦來源追蹤。
- 生命週期回顧：顯示 thesis 狀態、來源追溯、執行落差、訊號 / 市場 / 資料品質 attribution 與摘要 tokens。
- 籌碼監控：主力淨買賣、集中度、連續流向天數與風險級別。
- 從 Portfolio 下鑽至 Market Watch 的主力流向並定位個股。
- 持倉表整合共用呈現契約的動作適合度、目標／目前／差距權重（整數 bp）與失效條件；既有 Condition Monitor 的 `valid`／`warning`／`invalid` 只映射為持有／減碼候選／退出候選的唯讀分類。
- 權重差距只接受既有 Portfolio Advice 或持倉來源摘要明確提供的欄位；缺欄位顯示未知並保留警告，UI 不由目標減目前自行推導。
- 持倉條件監控的目前 Regime／分數只讀持倉來源摘要已提供的 current snapshot；缺資料時顯示待更新，不在 UI 掃描全市場或重建推薦分數。

### 手動帳、來源研究與配置研究入口

手動交易表單只在本機名冊有唯一完全符合時互補股票代號／名稱；矛盾或重複資料不猜配。未連結已保存研究的手動持倉，從持倉下鑽時明示使用當下個股研究 scope；已連結來源仍沿原 exact 守衛。資料與返回身份細節見[個股研究](#workspace-stock-research)。

手動帳持倉表全寬接在四卡／活躍持倉摘要後；手動帳重點與交易操作保留，Health／詳細頁放進階區，分帳與金融服務不變。此修補未納入固定 9fa／4b530；長 tab 整頁整理仍在後續版本範圍。價格研究增三步指引、區分來源批次與股票篩選，個股價格表說明缺價差或方向不補值；指南見[價格研究](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#官方條件與價格研究)及[手動帳](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md#手動帳)。

後續 source 分支的「配置研究封存」在 exact 已保存且沒有比較預覽時，可明確「登錄研究紀錄」。原研究 Registry 增加獨立配置研究區，輸入帳種／portfolio_id 並明選一筆後回 Portfolio 精確重開，再沿原個股與返回；不參與回測比較／升級、不假造績效。讀取換帳／關閉丟棄晚到結果，寫入等待收尾，原件或引用不符時拒絕。操作見[配置研究登錄指南](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md#登錄研究紀錄與跨頁重開)；此第二階段增量不改固定四流程試用候選。

持倉防線：

- 金額、成本、股數、PnL 必須使用 domain/service 層的 Decimal / 整數單位。
- UI 不應自行重算金融核心數值。
- 來源追溯不能被 UI 手動覆蓋成不可追蹤狀態。

Gate 4 的產品目標與驗收範圍涵蓋 Paper Portfolio cash-flow ledger、受控 Paper producer 的實際來源資料與人工 review、Equal Weight builder 的正式 output review，以及 Stress Lab 的正式 evidence 與跨期間 review。現有 UI 可揭露 Paper snapshot／cost ledger readiness、預覽／匯入 Paper fills、重建最近週報並保存研究用 Stress history；本段是功能／驗收範圍摘要，不是即時完成狀態。實際進度以 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)、[6M Engineering Roadmap](../00_core/ROADMAP_6M_ENGINEERING.md) 與最新具名 QA 為準。

文件同步重點：

- Portfolio 來源模型、條件監控、生命週期回顧或籌碼監控改動需同步 Snapshot、architecture 與 Manual。

<a id="workspace-runtime-observatory"></a>
### 7. Runtime Observatory

主要 view：

- `ui_qt/views/runtime_view.py`
- `ui_qt/bridges/runtime_event_bridge.py`

主要能力：

- 顯示 AI Runtime Subsystem 狀態。
- 觀測 FSM 狀態、health snapshot 與 event stream。
- 透過 Qt bridge 接收 runtime event bus。

後續開發分支在「系統狀態 → 日常排程 → 決策證據擷取 → 詳細」呈現同次 run 的核驗狀態、收據 SHA、完成時間、保存未知值、安全原因及未完成階段。切頁返回與被動刷新保留明選工作；換選其他工作或無型別舊結果清除舊診斷。逾時不顯假「未保存」，孤立 passed 不計已核成功；沒有新增啟動／重試控制。步驟及排錯見[終態指南](../07_guides/APPLICATION_MANUAL.md#11-系統狀態與決策擷取終態)。此功能尚未放入固定四流程 V1 或 50ddb 開發 EXE。

文件同步重點：

- Runtime 狀態、事件或治理規則改動需同步 `docs/01_architecture/runtime_observatory_rules.md`。

---


<a id="workspace-stock-research"></a>
## 個股研究（共用工作區）

後繼Source的「個股研究｜價格選股原來源」新增「我的判斷」：原文唯讀回訪、直接追加修訂、按下開啟時重驗原來源及合作關閉。保存綁既有bookmark、股票與原查詢，資料日與實際保存時間分開；一般即時報告與題材筆記不互換。缺原件仍可讀筆記但拒絕開啟／修訂；固定題材研究02未含本葉片。操作見[個股判斷](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md#原價格版本的個股判斷後繼source)，驗證見[QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#原價格版本的個股判斷qa62至qa70)。

後繼Source首屏保留有日期的行情事實，持倉關係另列；本次技術線索不以H5成熟狀態代替。明選且股票／原日期可綁定的保存推薦，才列當時支持與反對原句，與模型估計分開；缺資料維持不可用，完整原文仍在決策／歷史。這批Source及筆記前版比較尚未含於題材01固定包，限定驗證見[題材QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md)。

Increment132比較候選沿同一基本面分頁，先顯示2317／2330／2454的2026-H1／2025-H1／變化五列四欄；當期CSV與前期官方半年報分開列來源。營收同比用%，四率差用百分點；缺件／披露精度不穩定維持不可用。舊125及131仍是各自的當期五欄版本，新比較真可用小時與受改Main／EXE出口見[132 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment132-fundamental-comparison)，正常步驟與限制見[操作](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#三公司去年同期比較increment132開發候選)。

後續分支的基本面頁可沿原report port讀明選的2330／2026-H1營益固定版本，顯示五項原數值、來源／授權及前期缺件。只有這個發行人與版本接受目前研究；未明選、不完整、錯版或未到成功批次小時只隔離此來源。原價格／技術、返回與歷史來源守衛保持。配置與步驟見[具名營益固定版本](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#具名營益固定版本研究)，各平台驗證範圍見[Increment117 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment117-operating-summary)。

個股研究是 Recommendation、觀察清單、Portfolio 等流程共用的同一工作區，保存結果與當下市場研究的來源身份不可互換。操作步驟看[推薦與 Research Lab 手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md)。

### 保存來源、當下研究與返回守衛

第一版一般手動觀察股票若完全沒有保存來源身份，從候選池開啟報告會明示「目前既有行情研究」，並返回原代號。這條路徑不要求不存在的推薦圖表 artifact；有來源ID、決策日、snapshot或連結／衝突身份時仍保留原來源守衛，不用目前行情補保存研究。操作見[觀察清單手冊](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md)，限定驗證見[Increment34 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment34v1一般觀察股票下鑽與回訪)。

觀察清單、持倉共用的個股報告在綁定前重驗同股／run／日期／來源快照；完整封存但未入選的分析可保存其排除理由，未完成或失敗的空結果不能保存。切股及改來源會立即隱藏舊內容，再由 Qt 延後釋放，避免新表格與上一份提示重疊。「查看當下獨立 ML 研究（保留保存 Advice）」讓目前研究輸出與原保存 Advice 分別可讀，並可返回原來源；基點預測、H5 自然成熟、模型資格各自列示，不把研究輸出顯示成正式勝率。

報告另列持倉觀測日及行情資料日，Exit 使用現有持倉條件唯讀結果；歷史查詢不借今天持倉。基本面保留來源單位／期間基礎，官方目前估值與上市／交易狀態顯示來源時間及 partial／unknown 診斷。操作、參數與排錯見 [Manual 的本輪補充](../07_guides/APPLICATION_MANUAL.md#2026-10-04-保存來源當下研究與持倉日期)，實際驗收範圍見 [Astra 工程收尾](../06_qa/ASTRA_ENGINEERING_CLOSEOUT_20261003.md)。

未連結持倉的研究頁首沿用同部位、同股行情快照的資料日，不再回退最後交易日；已保存來源的日期與身份保留。市場總覽另分列判斷日與實際指數行情日，缺少得分或訊號強度時顯示未知，真實零值仍為 0。

### 決策到結果、Journal 與個人模型研究

左側日常導覽新增「個股研究」。既有下鑽在主程式內更新單一 `StockResearchWorkspace`，包含報告與「決策 → 結果」；返回來源只切頁並定位目前股票，保留來源篩選及報告內容。來源識別仍沿用 `ResearchStockContextDTO`，不以同股票替代 exact result identity。主程式關閉會同時取消報告與 Journey 的背景讀取。

推薦分析的個人採用、拒絕與推翻理由沿用唯一 typed Journal writer；「決策 → 結果」以唯讀、按時間排列的 append-only 歷史呈現已核驗的同結果／股票／日期／來源 snapshot 選擇。重複紀錄保留為歷史，不表示同時有效；identity 或 artifact 衝突時 fail closed，且不取代獨立的 Evidence／Outcome 狀態。操作步驟與限制見 [APPLICATION_MANUAL.md §9.9.1e](../07_guides/APPLICATION_MANUAL.md#991e-已保存推薦的個人決定與旅程回看2026-09-28)。

推薦分析另有個人模型評估唯讀區，要求使用者明確選擇目前已核驗結果的 personal capture 與 Stage C summary JSON；因目前沒有可信 result→summary 索引，UI 不掃描資料夾或猜 latest。服務重新驗證 canonical result、capture、政策、summary hash 與來源；pending／unknown、缺件及 null metrics 依 DTO 顯示，失配則拒絕並清除舊內容。這不執行 Stage C、不寫入資料、不代表自然績效，且非官方 PIT 或成交損益。操作與限制見 [APPLICATION_MANUAL.md §9.9.1f](../07_guides/APPLICATION_MANUAL.md#991f-個人模型評估摘要讀回唯讀)。

籌碼頁分列分點、法人、信用、集保持股分布與事件；級距 JSON 轉成持股範圍、人數、股數與比例，差異數調整／合計明確標示。事件顯示白話標籤，原始識別與可得時間可追溯，缺資料仍顯示缺資料，不轉成零值或評分。


> **最後整理**：2026-10-07
> **內容記錄範圍**：本頁先按九個工作區與跨頁責任整理 UI 契約，再保留日期化功能與工程紀錄；最新增量記錄至 2026-10-15（Increment71）。日期段落只證明其記載時點與範圍；目前狀態見 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，驗收範圍依各原 QA 收據判讀。
> **適用範圍**：`ui_qt/` 目前主要使用者介面。

### 官方注意公告與缺值顯示

後續開發分支的個股研究報告在市場狀態旁顯示獨立 TWSE 官方注意公告，原字串以 PlainText 呈現，另列來源日期、可用小時／basis、雙 SHA（tooltip 完整值）及限制。未知與查無此代碼分開；換股／清空會清除舊公告身份。三值固定版本設定、保存、重開與排錯見[單日官方注意公告](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#單日官方注意公告後續開發分支)。原固定9fa候選不變；不授 TPEx、歷史 PIT、處置或交易建議資格。
## 三、跨 Tab 工作流

### 市場觀察到候選池

1. 使用 Market Watch 找出強勢 / 弱勢 / 籌碼異常標的。
2. 加入 Watchlist / Candidate Pool。
3. 候選池可送 Backtest 或作為 Recommendation / Research workflow 的輸入。

### 推薦到回測

1. Recommendation 依 Profile、Regime、strategy config 產生推薦。
2. 使用一鍵送回測或送 Research Lab 批次回測。
3. Backtest 保存 run metadata，必要時 Promote 為策略版本。

### 回測到持倉

1. Backtest run 若符合條件，可建立或輔助建立持倉。
2. Portfolio 保存 `source_type`、`source_id`、strategy / recommendation metadata。
3. 持倉後續用價格、regime、score、籌碼監控做假設檢查。

### 持倉回到研究

1. Portfolio 顯示假設失效、停損 / 停利、籌碼惡化或來源策略資訊。
2. 使用下鑽回 Market Watch / Smart Money 查原因。
3. 回到 Backtest / Recommendation 調整研究假設。

---


<a id="ui-contract"></a>
## 四、UI Contract

### UI 可做

- 顯示資料、表格、圖表與警示。
- 收集使用者輸入並轉成 service config。
- 轉接跨 Tab 事件。
- 顯示 service/domain 回傳的 metadata、diagnostics 與 validation status。

### UI 不應做

- 不在 UI 內新增策略核心計算。
- 不在 UI 內重算金融金額、PnL、持倉 average cost。
- 不在 UI 內用完整期間資料重算回測門檻或推薦百分位。
- 不直接寫正式資料根目錄，必須透過既有 service / repository。
- Backtest / Research Lab 的新保存入口必須呼叫 `ResearchRunService.save_run()`；UI 只能送出已完成結果 DTO 與執行快照，不可保存 stale pending result。

---


## 五、早期缺口清單（現況待核）

> 以下是較早的缺口記錄，未逐項附上最新核對日期，僅供追溯，不代表目前未完成事項或目前工程優先序。現況與工程順序請查 [PROJECT_SNAPSHOT.md](../00_core/PROJECT_SNAPSHOT.md)、[ROADMAP_6M_ENGINEERING.md](../00_core/ROADMAP_6M_ENGINEERING.md) 及對應的具名 QA。

原清單列出的 UI 缺口：

- Phase 5 大表格分頁已完成 (SQLite 檢視器分頁)。
- 規格化 Excel 報告輸出已完成；PDF 仍待完成。
- Research Run Registry 的基礎保存入口、第一版跨 run 比較 UI 與 registry-based Promote service Gate 已完成；後續仍可補更完整的 reconciliation 操作 UI。
- Factor Layer、營收估值、三大法人資料加入後，需要新增可檢查資料品質與 available date 的呈現方式。

對應文件：

- [PROJECT_SNAPSHOT.md](../00_core/PROJECT_SNAPSHOT.md)
- [ROADMAP_6M_ENGINEERING.md](../00_core/ROADMAP_6M_ENGINEERING.md)
- [DEVELOPMENT_ROADMAP.md](../00_core/DEVELOPMENT_ROADMAP.md)
- [system_architecture.md](../01_architecture/system_architecture.md)
- [BACKTEST_LAB_FEATURES.md](BACKTEST_LAB_FEATURES.md)
- [USER_GUIDE.md](USER_GUIDE.md)
- [APPLICATION_MANUAL.md](../07_guides/APPLICATION_MANUAL.md)



<a id="date-history"></a>
## 日期化歷史與交付邊界

現行互動契約先見本頁工作區正文。日期區段提供當時來源、範圍、相容性與驗收依據；不得由日期順序推論目前產品接受狀態。固定包、產品 Gate 與目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，原始證據沿各區段指向的 QA 收據。

| 查找主題 | 功能正文 | 日期／證據索引 |
|---|---|---|
| 個股來源、決策到結果、模型讀取 | [個股研究](#workspace-stock-research) | [2026-10-04](#2026-10-04-個股來源與目前研究)、[2026-09-22](#2026-09-22-個股研究主頁整合) |
| 價格選股、來源收藏與窄版 | [推薦分析](#workspace-recommendation) | [Increment35](#2026-10-15-第一版價格研究窄結果區)、[Increment66 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment66日常研究修正版候選依原計畫04)、[Increment70 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment70價格選股載入後顯示結果)、[Increment71 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment71真人試用回報的四流程可用性修正) |
| 回測結果、歷史與版本相容 | [策略回測](#workspace-backtest-research-lab) | [Increment36](#2026-10-15-第一版單股回測結果修復)、[Increment38 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment38p08雙策略逐日原觀測明細) |
| 市場來源、官方資料與三態 | [市場探索](#workspace-market-exploration) | 依各原 UX／Increment 日期標題與其 QA 鏈結查找 |
| 手動帳、配置研究與持倉下鑽 | [持倉管理](#workspace-portfolio-management) | 依各原 P06／Increment 日期標題與其 QA 鏈結查找 |
| 數據更新與 Runtime | [數據更新](#workspace-data-update)、[Runtime Observatory](#workspace-runtime-observatory) | 依原日期標題與手冊／QA 鏈結查找 |

### 未分組前置增量的功能對照

原始前置段落依功能分別收斂至策略回測（W 底、布林基礎、保存版本、PF、歷史卡、Increment71 版面及單股結果）、推薦分析（Increment66／70／71 價格研究）、持倉管理（手動帳／配置研究）、市場探索（TWSE／TPEx）及 Runtime Observatory。Increment59 固定預覽路徑與已驗範圍留在本段 source 對照映射；原始 source 副本完整保全。

### Increment59 固定預覽與驗收範圍

上述試用回報修補另交固定 0f644faa0d48 預覽入口 output/trial/Baldr-Feedback-Preview-59/Launch-Baldr.cmd；價格研究修正合法代碼輸入順序造成 query 中斷，UI 送 query 前排序，核心拒錯／重複／來源守衛保留。正常 Native 來源及 EXE 各驗四股篩選、空 QA 帳持倉表前移、兩原策略保存／歷史／規則／返回／fresh；完整推薦長頁重排與使用者真帳未驗。原 9fa／4b530 不替換，四條 V1 範圍不擴。
## 2026-09-06 閉環契約更新

- 更新／市場頁消費 App 的決策日、有效日、quality 與 warnings；來源詳情查詢不寫 manifest，市場缺歷史或未來資料不補零。Regime 匹配度不是勝率。
- 推薦保存 `recommendation-context.v1` 的 Profile／設定、來源指紋與 Why Not；啟用因子缺值不補中性分數。歷史產業篩選缺 PIT 成分證據時拒用，歷史日期仍是服務接點，沒有新增 UI 日期選擇器。
- 推薦回放新預設 `next-session-open.v2`：收盤委託、後續可交易開盤成交，期末持倉與取消狀態明示。Registry 使用執行時 frozen 版本／成本；跨版本、cancelled／partial 不混排，缺檔／損毀停止比較，UI 不 reconcile。
- 候選池名稱由 App 查詢，JSON 損毀保留原檔並顯示錯誤；候選 SQLite／精確帳本只供明確注入與副本驗證，正式 JSON／JSONL 預設未切換。Daily Desk 區分有效空池與未知，舊日期回呼不覆蓋新請求；08-B 已接上保存推薦 provider、推薦加入候選的 current_result_id 及 Workbench 新來源欄位重載；未保存結果不捏造來源 ID。
- Runtime 顯示 UNKNOWN／read state／diagnostics，關閉 observer 解除訂閱；受限事件 ID 去重不是 durable queue，重啟不執行 task。Evidence review proposal 是 App 接點，沒有新增 UI 核准按鈕。

完整操作、參數與排錯以 [Application Manual](../07_guides/APPLICATION_MANUAL.md) 為準；實作與整合證據見 [TASK-08](../06_qa/TASK_LOOP_08_HANDOFF.md)。本輪不改 `action_required`／V4 Evidence Accumulation，不授予 Formal credit、來源 acceptance、scheduler、broker 或正式 writer 權限。

## 2026-10-03 資料更新 freshness、Formal／Candidate 與合作式取消

資料更新狀態卡將正式 SQLite 與隔離 Candidate DB 分成不同資料 lane。服務回傳的 `FORMAL_AVAILABLE`／`CANDIDATE_AVAILABLE` 是機器狀態 token，代表來源可讀性與所屬資料根；畫面分別顯示正式資料與候選資料的日期／筆數，candidate 不會因此進入正式評分、推薦或交易。Freshness receipt 只有在目前 `DATA_ROOT`、SQLite／Candidate DB 路徑、台北市場日、04:30 cutoff 與 receipt 的實際期別相符時才投影為來源狀態；跨過 cutoff 或 live period 已變動時顯示未知／需重新驗證，重新執行唯讀 freshness probe 後再判讀。

寫入型更新的「取消目前工作」採合作式取消，worker 會在安全單位邊界停止，不強制終止 QThread；已完成的安全提交可能保留，並應再做唯讀狀態檢查。錯誤仍以失敗顯示，不因取消而清除。MOPS 月營收候選抓取取消時可留下完整 raw HTML 作診斷，但不發布未完成的 candidate CSV；訊息所列「已解析資料」筆數不能當成已可用候選。

操作步驟及排錯見 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 第 4 節；狀態、取消及 TDCC checkpoint 邊界的當前證據見[整合修復紀錄](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)。本段說明 UI contract，不表示 native Windows 前景操作驗收已完成。

## 2026-10-03 推薦、研究與 Portfolio 顯示判讀

- Market Breadth 的多方／空方方向要求來源變動值與方向欄位相符；缺方向、未知或衝突欄位會保留未知，不用正負號代猜。
- 技術評分只使用父層與子指標均啟用的項目。所需行情 bars 隨啟用指標週期增加，至少 60 個有效交易 bars；缺少啟用指標資料屬不可計分，不等於零分或被門檻篩除。
- 推薦空結果分成「沒有可評估候選」、「候選不可計分／來源缺件」與「已評分但未通過目前篩選／排名條件」。只有最後一種是門檻篩選後為空；不要以降低門檻處理前兩種。
- 歷史 Portfolio Alert 顯示原事件日期與來源，是保存的歷史快照，不代表目前持倉；請回持倉管理確認現況。
- 個股研究報告沿用已保存上下文的 `decision_date` 作行情 cutoff。缺漏或不合法時阻擋歷史查詢，不以今天日期替代。
- Portfolio 目前投入、已實現與未實現金額以毛額呈現，未扣費稅。費稅僅彙整已記錄資料，依原幣別列出已記錄及缺值筆數；缺件不補零，不冒充完整淨損益。

Workbench 85 項測試與資料更新頁 validator 25 項通過、4 項需真下載／合併的測試略過；另有 138 項 focused tests、750 個來源檔案的 scoped mypy 與 20 個 Python 檔案 compile 通過。完整結果見 `output/qa/integration_20261002/phase3_luna_implementation_20261003/ui/REPORT.md`。Native Windows 可見操作仍待 root 驗收。完整操作與限制以 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 為準。

## 2026-10-06 首頁直達與個股限制

首頁「今日優先查看」四用途重用原工作區；4–6位股號搜尋與Enter是明示當下研究，原保存候選仍由原列下鑽並精確返回。大盤刷新保技術細節收合／展開，明示bool來源缺件為unknown、error不當預設Trend；匹配度不轉勝率。個股focus summary呈現原DTO最新一日漲跌／資料日與區塊可讀／缺件、ML限制；保存關注理由不授投資結論。更多來源／指標及六個子頁仍可下鑽。[操作手冊](../07_guides/APPLICATION_MANUAL.md)與[有限QA](../06_qa/BALDR_FIRST_WAVE_INTEGRATION_20261006.md)分報Native／真人與工程。

## UX13／18 具名母體盤勢與指標排序（2026-10-05）

市場探索新增研究母體盤勢，接收每日名單相同 verified snapshot，顯示明示≤16檔母體／行情日／source與方法身分，以及每固定方法三態分母。partial 缺件計未知且不偽造可開啟股票列；篩選不改盤勢分母。原排名未提供明示未知，名單按原 close／MA20／MA60 等值以 Decimal 排序，缺值固定尾端，不是投資分數。摘要短列日期、母體與方法 counts，完整來源／方法審計保留提示。操作見 [Manual共用投影](../07_guides/APPLICATION_MANUAL.md#2026-10-05-ux1318-具名研究母體盤勢與指標排序)。


### UX04／05 每日研究條件（2026-10-05）

Recommendation內切換每日研究條件與既有推薦研究來源。明示≤16股；close／MA20／MA60兩條既有條件AND／OR，符合／不符合／未知及原因分列；明確更新與read-only重讀分開。選股→個股沿同manifest與as-of，切股／返回保原清單，來源修訂顯未知與更新引導，不升格正式推薦。操作與排錯見[Manual日常研究flow](../07_guides/APPLICATION_MANUAL.md#2026-10-05-ux0405-每日研究條件與同源個股)。

### UX19 隔離研究快照來源（2026-10-05）

個股研究 service 可明示 snapshot root／cohort，經 verified reader 讀已發布 close／MA 研究快照，來源不符保留 unknown 與具名錯誤。CLI 支援同一路徑的實際 `read_report()` 讀回；桌面 UI 預設仍用 live 有限投影，本包未新增 UI 操作。來源身分／資格與操作見 [Manual UX19](../07_guides/APPLICATION_MANUAL.md#2026-10-05-ux19-隔離研究快照生產與讀回)。

## 2026-10-05 個股日特徵共用三態

正常個股研究載入後，首屏與研究理由共用既有close／MA20／MA60 snapshot的三態。暖機末段有效OHLC不足20／60筆、來源品質或日期未確認時顯示「尚無法判讀」，不再由首屏另行直比；一項未知保留另一項已確認觀察。沒有新按鈕、參數、公式或排名。舊DTO空mapping保留原呈現；必要observed-prefix不代表正式PIT／EMA／模型資格。操作與排錯見[Manual UX18](../07_guides/APPLICATION_MANUAL.md#2026-10-05-ux18-共用日特徵與個股觀察)，實際驗證見[既有QA收據新章](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。

## 2026-10-04 個股來源與目前研究

本節契約已收斂至[個股研究（共用工作區）](#workspace-stock-research)；原始正文與搬移對照保存在本任務 output 的 source 副本與 mapping。

### 2026-09-22 個股研究主頁整合

決策到結果、ResearchStockContextDTO、Journal、唯讀個人模型評估及缺值投影已整合至[個股研究（共用工作區）](#workspace-stock-research)，保留此舊日期錨點供相容導覽。

### 頁面內操作說明（2026-10-05）

各頁標題的「i」開啟可捲動、可選取文字的分區說明，內容對照目前控制項與結果欄位，涵蓋操作流程、欄位單位、表格／圖表判讀及載入狀態。說明採共用 `TAB_INFO.sections` 配置，開啟或關閉保留原頁設定與結果；回測明列進階策略門檻及最佳化參數入口。完整操作見 Manual「頁面的 i 說明按鈕」。
> **狀態判讀**：目前狀態以 `docs/00_core/PROJECT_SNAPSHOT.md` 為準；未來 6 個月工程方向以 `docs/00_core/ROADMAP_6M_ENGINEERING.md` 為準；本文件只描述 UI 功能與操作入口。
> **完整操作**：安裝、逐步操作、參數、結果判讀與排錯見 [APPLICATION_MANUAL.md](../07_guides/APPLICATION_MANUAL.md)。

---

## 2026-09-21 V5 日常操作與可讀性工程

本輪把既有 read-only DTO 重新安排成「先結論、再原因、最後進階細節」的日常路徑，版本名稱為「V5日常操作與可讀性工程」。首頁 guided summary、候選／報告／持倉摘要、分層導覽、回測／推薦進階切換與個股報告 lazy tabs 均屬呈現與導引工程；正式 V4／V5 gate、自然 learning maturity 與 V6 user-level personalization 仍依 scoped roadmap 保持 pending。

### 2026-09-21 個股研究來源日期與 candidate 邊界

個股研究報告的來源表逐列呈現 `來源`、`來源狀態`、`品質`、`資料日`、`資料可得時間`、`更新狀態`、`版本`、`筆數`、`更新週期` 與 `預期資料期`；區塊標題也保留該區塊的資料日／可得時間。價格、技術、broker、institutional、credit、TDCC 與 fundamental 不能共用單一「今天」日期。這讓 9/21 price／technical 與較早的籌碼或個別 broker coverage 可以同時被正確揭露。

freshness receipt 的 `candidate_only=true` 會維持 candidate／research-only 語意，不會被 UI 或 read service 視為 formal SQLite 的 current／fresh evidence。來源缺件、PIT stale、unknown、partial 或 broker coverage gap 會顯示為品質／狀態診斷；UI 不以 0 補值、不自行跨來源補日期、不將缺件改成正常或交易訊號。1418 Paper 的 blocked 狀態若缺 source lineage，仍保留 lineage／candidate 診斷；formal 9/21 price row 可獨立呈現。

本輪 bounded formal row counts、target stock evidence、source coverage 與 focused regression 見 [2026-09-21 個股研究資料鏈 Incident QA](../06_qa/STOCK_RESEARCH_DATA_INCIDENT_2026_09_21.md)。本節描述 UI 顯示契約，不宣稱所有正式資料在同一交易日 fresh，也不代表 V5／V6 formal closeout。

全市場價格跨日稽核另見 [2026-09-21 全市場跨日價格稽核](../06_qa/PRICE_JUMP_AUDIT_2026_09_21.md)：`漲跌價差` 的方向必須合併來源 sign 欄，報告 service 現在以 signed value 或 unknown fail-closed 呈現；UI 不從 close 跳幅自行判定價格合理，也不把 merged stale aggregate 當成 target-date evidence。

### 預設入口與分層

- 左側導覽分成「日常使用」（決策工作台、市場探索、推薦分析、觀察清單、個股研究、持倉管理）、「進階研究」（策略回測）與「系統維護」（數據更新、系統狀態）。保留既有 workspace key／Runtime alias；deep link 會展開所屬群組。
- 決策工作台預設先顯示「今日優先查看」與日期／資料日期／結論／下一步；「顯示進階工作台」才展開完整 workflow、來源、技術與研究證據。市場探索的 Daily Decision Desk 仍只有既有唯一實例。
- 候選池與持倉先顯示狀態、原因、來源可追溯性與下一步；完整研究、歷史、Journal、模擬／Paper／Stress 仍由進階入口進入。「選擇原推薦來源」保留在候選池的日常下一步，用來核對對應當次推薦來源後開啟原理由。

### 個股報告與結果閱讀

個股研究報告的「摘要」先列結論、證據、變化、風險、資料是否足夠與下一步；逐項證據與來源／各區塊日期由兩個進階切換控制。深層分頁進入時才建立內容；完整 OHLC 使用價格／成交量圖，缺少任一 OHLC 時使用 close chart fallback。圖表只使用 service 已提供的 DTO，不重新評分或補造資料。

UX08 原生圖安全切片：價格圖與 OHLC／量數值表共用 application 核對後投影，明示來源、截止日與實際資料範圍，保留 Decimal／整數及缺值。錯股 DTO、已知來源／日期／行指紋失配拒絕；未來與明示晚發布資料排除，缺可得時間仍未知。圖表初始化／填值失敗保留同源數值表。技術資料只有單日快照，不補歷史指標線或未核實交易標記；原生圖仍是 default，未整合 LWC／Hosted Widgets。

後續限定切片加入既存 MA20／MA60 歷史覆蓋線與同序列精確表：缺列／缺值處斷線，不補末值；保存來源缺合法歷史時明示缺件，不向 live 借值。單日技術快照仍獨立，歷史值未授予暖機／PIT資格；沒有新增縮放、平移、外部 bundle 或個人交易 markers。

推薦與回測的 guided summary 只翻譯現有參數與輸入母體。推薦保存仍保留 `result_id`、repository create-only、delivery ACK、Journal／readback 與 context binding；回測的研究模式、日期、策略、資金、費用、滑價、執行價格及停損停利值不因折疊進階而改變。結果頁的摘要、診斷、圖表、最佳化與 Walk-forward evidence 仍是原功能。

### 可讀性與安全契約

所有摘要均標出決策日／資料日／來源品質；缺件、來源不一致、身份衝突、讀取失敗與 last good data 以白話原因及恢復入口呈現。UI 僅讀取既有來源，沒有新增 collector、scheduler、正式 DB、Journal 或 learning writer；缺 cutoff 或 identity 時維持拒絕寫入與 fail-closed。完整 R1–R10 與 frozen QA evidence 見[封存的 V5 readability acceptance](../09_archive/V5_READABILITY_ACCEPTANCE_2026_09_21.md)。

### 本輪 UI 整合修正

- 左側導覽的群組標題與 workspace 項目共用左側內容起點；展開／收合 marker、keyboard focus 與 tooltip 保留，窄版不以置中標題壓縮內容。
- 個股報告換股時會先清除上一檔報告，避免在新股票載入失敗或進階分頁開啟時殘留 A 股內容；同一檔重新載入失敗或取消時保留明示的 last-good data，並把本次失敗原因與重新載入步驟放入 Journey。來源脈絡在日常摘要維持精簡，完整 identity／mapping／snapshot trace 仍在來源進階與 tooltip。
- 持倉頁把日常摘要、進階正文、Paper health、持倉明細與模擬／歷史資料分開呈現；整頁可垂直捲動，更新狀態顯示可讀日期並保留原始 timestamp tooltip，寬／窄版 splitter 不會把操作欄位壓成不可讀細條。
- 決策工作台首頁把 machine token 轉為白話下一步與市場缺件說明；頁面說明按鈕提供可存取名稱與操作限制提示。這些是呈現／導引修正，不改資料、評分、交易或 writer 邊界。

### 2026-09-29 跨工作區版面與內容可達性

主視窗初始位置依螢幕可用範圍置中限制；長頁面、結果面板與動態內容可透過垂直捲動繼續閱讀。可列資料的表格／清單以至少五筆可見資料列作為初始 viewport 目標；表格的水平捲動、欄寬與儲存格 tooltip 協助查看較寬或較長的欄位。窄版的控制列會改為直向排列，避免長標籤與按鈕被擠成細欄；部分控制列與技術細節面板（例如 SQLite Inspector 篩選、Market Regime layer3）亦可水平捲動。這些調整只改 UI 呈現，維持 workspace 對外 widget identity、資料來源及核心計算行為。

跨頁面主視窗尺寸、巢狀分頁、表格／清單與合成長內容已完成日期化 geometry audit；六格 offscreen MainWindow 矩陣全數通過。測試範圍、合成資料覆蓋及 OS 原生視窗限制見[歷史 UI Layout Audit 2026-09-29](../09_archive/UI_LAYOUT_AUDIT_20260929.md)。

### 2026-09-30 讀取期間的介面回應與安全關閉

Workbench 與首次開啟的 Research Console 唯讀來源載入改由受管背景 worker 執行，主視窗可先完成顯示與處理關閉事件；研究證據分頁採首次切入時才載入。SQLite progress handler 與 artifact 階段檢查合作式取消；關閉時仍會等讀取自然安全收尾，沒有強制中止 thread。關閉等待期間狀態列每數秒更新進度，完成後自動關閉；crash diagnostics 增加不含路徑／參數的生命週期階段記錄。這項修正只調整 Qt I/O 執行位置及退出協調，不改資料、績效或金融計算。

關閉回歸使用 production `main()` 與 MainWindow、隔離資料／輸出／個人政策路徑，以及各 500ms 的合成 Workbench／Research Console 慢讀。兩案例都確認讀取在背景執行緒（`Dummy-2`）、heartbeat 最大間隔 63ms、關閉事件延遲分別為 6ms／22ms、`close()` 耗時 16ms／15ms、`app.exec()` 與 OS 子程序自然退出碼皆為 0，且關閉時沒有剩餘受管 worker。此為 Qt offscreen 自動驗證，不等同於正式大資料量或 Windows 前景視窗手動驗收；可用 `scripts/qa_validate_ui_natural_shutdown.py` 重跑隔離情境。

## 更新記錄

- 2026-10-11：將未逐項核對的 UI 缺口清單標為歷史記錄，避免當成目前狀態；現況導回 Snapshot、6M Roadmap 與具名 QA。
- 2026-10-10：補入官方市場與技術條件研究子頁及 Watchlist 專用收藏重開能力；操作與安全限制見 Manual §6.7。

- 2026-10-05：內建Breadth／Relative Strength的共用與獨立SQLite讀取接入合作取消，視窗等native worker結束才退出；Native查詢中關閉及取消→正常重試通過，取消不冒充完成。四檔backend改動，UI main／view未改；原速度目標與Backtest未達項保留，見 [SQL取消收據](../06_qa/PRODUCT_STAGE1_SQL_CANCELLATION_20261005.md)。

- 2026-10-05：回測四張圖與推薦組合兩張圖延至首次結果頁使用建立；待顯示資料採快照且以最新結果取代，切回重用 widget。單張繪圖失敗保留資料、顯示提示並可再次進頁重試。盤勢關閉等待 native worker 結束；取消粒度與 Native 首次使用／效能驗證見 [階段1限定收據](../06_qa/PRODUCT_STAGE1_PERFORMANCE_IMPROVEMENT_20261005.md)，操作與排錯見 Manual。

- 2026-10-05：個股研究 ML 稽核按鈕依狀態切換展開／收合；current／saved／未知 scope 標題與日期分開，不把保存來源標成當前。歷史回顧呈現已讀回的所選日期；ML 品質降級保留具體原因，未提供時明示。操作與限制見 Manual；本輪 offscreen 與 consumer 測試不替代待驗 Native 流程。

- 2026-09-30：完成九個主工作區的長頁捲動、表格／清單五列 viewport 與主視窗幾何整合驗收；完整矩陣與 OS 原生驗收邊界見 UI Layout Audit。
- 2026-09-06：補上八卡 UI／App 契約、08-B 來源接線與正式來源／權限限制，操作細節指向完整 Manual。


## UX02 共用狀態詞彙有限切片（2026-10-05）

盤勢、持倉系統健康、選股與個股研究沿用既有DTO，透過 ui_qt/status_vocabulary.py 翻譯明確原碼；資料缺件、品質降級、載入、時間等待／休市、研究完成、研究資格與真實錯誤分開。專用詞彙保留fallback，未知碼保留，股票／持倉風險不由系統缺件推論；來源、日期及原始診斷沿既有詳情保留。Workbench與回測使用同一呈現邊界。操作、限制及排錯見APPLICATION_MANUAL的UX02段，驗證見 docs/06_qa/UX02_SHARED_STATUS_VOCABULARY_20261005.md；非全頁／全狀態重構。


## 2026-10-05 原研究收藏

「推薦分析 → 每日研究條件」選列後按「收藏此研究」，確認保存至既有觀察清單。書籤固定原來源／方法／日期／條件及排序偏好；重複相同收藏不寫，另一來源同股獨立保存。從觀察清單開個股、同查詢切股與返回都用exact書籤；無效來源不改成手動或latest。「以最新來源另開研究」只讀新研究，原書籤不變；精確移除可取消並在本程序還原。

完整參數、步驟、安全限制與排錯見[Manual](../07_guides/APPLICATION_MANUAL.md)，限定測試／Native／Library證據見[QA](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。本包不改推薦／持倉／自然ML資格，不宣告全計畫完成。


## 2026-10-05 UX04／05 固定方法預設與候選摘要

每日研究條件新增五個固定 MA20／60 查詢預設，選取後須明確套用；只篩選已核驗快照。手動條件／原來源回訪不自動覆蓋，切換預設或Decimal指標排序不改來源／日期／方法／研究資格。完整 declared 分母、已發布／缺件、組合三態、顯示／因篩選隱藏與具名原因可見；缺少 artifact 不造可開列，未知不當反證。原強弱排名未提供，選項停用；不造分數或勝率。選取摘要立即刷新，原方法identity保留詳情。

本包 final 43 affected passed、Workbench85、validator25／4skip／0fail、mypy779、compile／quant guard通過；已發布真D2382／1477 readonly offscreen及preset→收藏payload roundtrip→同源開啟／返回身份核對通過。未啟動正式／全量producer，沒有真實清單寫入／遷移、正式DBwrite、訓練、前景Native或鍵鼠；本包新增Native互動仍待下一使用者桌面時段。完整stage1–3未宣告完成，Backtest18.62%／20%未達及PIT／availability／自然ML／真人證據限制保留。詳見既有[UX16 QA](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)與[Manual](../07_guides/APPLICATION_MANUAL.md)。


### UX16／18 有界母體來源契約延伸（2026-10-05，基線7e11f5a8）

明示母體設定是隔離研究批次來源：ID／版本／截至日／原檔hash、納入／排除與理由、已知或未知設定分母。可選manifest extension納入原不可變identity，讀取與consumer重新核對來源revision／刪除／成員／date；舊無設定cohort保留來源與原始分母未知。清單、母體盤勢及候選摘要共享同一契約，設定不授予PIT或推薦資格，不計算新分數。CLI明示讀included，禁止無設定手動更新默默降格已綁來源。

原排名來源audit：原計畫指StockScreener本日／本週價量強弱排序（原公式不改）。ScreeningResultDTO有period／method／version／eligible count，但即時結果未有不可變run／完整成員排除／hash發布；strong_stocks_view僅記憶體快取。saved recommendation屬另一rank kind不能代用。有限currentDB schema唯讀未找到rank／screen tables，不推論全球不存在。原排名未知且停用；需原引擎不可變結果發布工程，不稱等待自然成熟。

本包無Native前景或使用者視窗操作，無訓練、全市場producer、正式DB／registry或真實書籤寫入；永久清理仍未執行。驗證與commit結果見同章最終收據補記。

最終驗證：104相關tests、WB85、validator25/4skip/0fail、mypy781、compile13及guard通過；真D三股隔離發布／2382讀回／offscreen同源通過。詳見UX16 QA最新最終驗證章；原排名publisher與Native仍pending，未push。


## 2026-10-05 原排名研究模式

每日研究條件可唯讀選擇日／週比較與強／弱模式，來源存在且核驗相容時啟用原排名排序。研究母體盤勢共用同一來源；MA條件與原名次分開，缺排名未知，不重編篩選後名次。舊Top／Bottom百分比不可當一般前幾％或勝率；來源只授有界研究。原排名收藏已另存 v2，舊非排名研究收藏沿原 v1 契約；詳見本文最新版本化章。隔離CLI發布與參數、解讀／排錯見[完整Manual](../07_guides/APPLICATION_MANUAL.md)，[QA](../06_qa/UX18_ORIGINAL_STOCK_RANKING_PUBLISHER_20261005.md)另列Native及剩餘工程。

- 2026-10-05 更新：同步原排名入口、來源限制與收藏相容性。

## 2026-10-05 原排名收藏與個股來源版本化（最新限定收尾）

已完成原排名選股→個股原排名／原 feature→版本化收藏→新程序 pinned 讀回→精確返回原收藏。v2 保存四模式、實際比較窗、原母體／方法／hash／排序／所選股；舊非 rank v1 內容與 bookmark/query/payload 雜湊不變，沒有真實清單遷移。缺件／錯版本／日期／股號／hash／來源修訂顯示原因，可明確另開最新個股研究，保留原證據。完整 Top/Bottom 字串照原 publisher 顯示，3–5 筆週 fallback 明示實際日期與非完整週，不反推 score／勝率。 完整入口、步驟、參數、限制與排錯見[Manual](../07_guides/APPLICATION_MANUAL.md)，[限定 QA](../06_qa/UX18_RANK_BOOKMARK_SOURCE_VERSIONING_20261005.md)。

其他原大盤／強弱 consumer 融合、完整 feature/method dictionary、正式合格母體／排程部署、長期 storage/growth 及其他 lifecycle crash 驗收仍是第一版工程。Backtest 18.62%／20% 未達保留。正式母體權威、official availability／歷史 membership／PIT，以及舊 Top/Bottom 口徑與 numeric score 暴露屬來源／方法版本決策。Native 鍵鼠／縮放／跨頁、完整 App startup 與 3–5 位真人驗收另待桌面時段；不把工程缺件稱為自然成熟。


### 2026-10-05 UX09 研究名單入選歷程

每日研究清單新增入選歷程欄；候選與選中個股摘要保留狀態、前次日期及理由。MA 查詢的背景唯讀比較與排序／顯示篩選分離，來源不足／修訂／改版保持未知；原排名不是新的入選 predicate。操作見完整 Manual 的 UX09 小節；[限定 QA](../06_qa/UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md)。


## 2026-10-05 UX09 歷史索引／分頁與有限版本復原（最新）

長期保存的研究manifest以可重建SQLite派生索引查詢，32 refs／頁、固定來源／query／generation游標、64頁滑動導航窗口且可持續向更早頁讀取。背景history／explicit rebuild保持當期個股與篩選主線可用；schema／來源／hash／cancel／故障不偽造完整，原immutable來源／舊收藏不遷移。索引最多64MiB，每頁串流重核全index SHA及頁內原manifest/artifact，年度calendar以4096entries／32MiB逐份驗證，不再32份正常累積即整批未知。

限定受影響79個不重複案例、Workbench85、validator25／4skip、mypy788、11變更Python編譯與精度／未來函數guard通過。真實已保存三股來源隔離offscreen回放：晚發布仍unknown、17來源hash與正式DBsize/mtime不變、worker0；沒有讀正式DB去重核current identity。130日×2修訂合成metadata全260refs走9頁，index159744 bytes、最大page JSON13814 bytes／tracemalloc1226583 bytes；不當自然樣本或正式長期總容量證明。

本包關閉UX09索引／分頁／索引程式內版本復原；第一版工程剩餘固定F1–F4，詳細終點與owner見收據。Backtest18.62%／20%仍差1.38百分點，不重測湊數或放寬。舊1477 Native已在6691ec78通過，較早「仍待1477」文字由此更正；新分頁／跨頁Native及3–5位真人另驗。1000×835 outer／125%已接受，不新增1000×800硬門檻。具名full-cohort與原完整Top/Bottom標籤沿現況，官方全市場／新百分位方法只有擴充時才要明確決定，不阻塞目前研究限定工程。

完整操作與排錯見 APPLICATION_MANUAL 的歷史索引小節；[詳細驗證、來源選項與F1–F4凍結清單](../06_qa/UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md)。


## 2026-10-05 F2／F3 原市場頁共享來源與已開能力矩陣（最新）

F2／F3 在已接受的 A／A 研究限定範圍完成：原大盤指數併列具名摘要，強勢個股、弱勢個股可明示切換至每日研究名單同一 immutable 來源；日／周 × 強／弱四模式保留原完整 eligible、Top／Bottom 標籤、實際比較窗及兩種排除。榜外與研究資料缺件分欄，來源變更／清除／過期回應拒絕，切返嚴格唯讀不啟 producer。既有全市場／產業來源、母體與可比較性仍獨立，沒有用三股取代全市場統計。

能力矩陣只登記 close／MA20／MA60、close_above_ma20／close_above_ma60，完整 field／unit／warmup／missing／availability／version／cost／source 與逐股 audit 可查；官方時點及未量測成本維持 unknown。完整只相對 named declared cohort；既有 feature v2／method hash／原引擎與收藏版本不變，沒有新增正式 B 母體或方法版本。

本批驗證：43 個不重複受影響案例有通過證據（根層首9＋相容29＋實際橋接新增1＋F2 focused4；最後11頁面相容重驗為既有案例不加總）、Workbench85、validator25／4skip／0fail、mypy790、12檔編譯及精度／未來函數 guard 通過。受控小型來源驗實際背景 consumer；真實既有三股保存來源驗能力投影與 offscreen 畫面，17 來源 hash 與正式 DB size／mtime 不變、worker 0；後者沒有開正式 DB 重核 current identity，不能宣稱自然跨日證據或 PIT。詳細來源、失敗保留及回滾見本批 QA 收據。

第一版工程剩 F1（18.62%／20%，差 1.38pp；不重測微調）及 F4（整條跨頁整合、部署、長期總容量）。新 Native／3–5 位真人另驗；舊1477 Native已在6691ec78完成，不重列待辦。1000×835 outer／125%沿已接受，不加1000×800硬門檻。工程缺陷不稱等自然成熟；source/capacity／Evidence 屬另一 owner，保留其變更並排除本批提交。沒有清理、正式資料寫入、訓練、前景視窗操作或 push。

[本批詳細收據](../06_qa/F2_F3_SHARED_CONSUMERS_AND_CAPABILITIES_20261005.md)


## 2026-10-05 明示 research source 啟動配置

MainWindow 啟動方可明示研究 snapshot root／cohort 與 original-rank root；快照 root/cohort 成對、非空，原排名 root 不能單獨配置。研究名單初始 cohort 同步明示值，啟動仍不自動讀取／採集；無參數沿原 defaults。操作依 [完整 Manual](../07_guides/APPLICATION_MANUAL.md) 的明示研究來源配置小節；雙來源跨頁與資源終驗依 [F4 QA](../06_qa/F4_RELEASE_INTEGRATION_AND_RESOURCE_ACCEPTANCE_20261005.md)，不以 offscreen 取代 Native／真人。
## 個人觀察清單明示啟用（2026-10-06）

候選池在成對設定 personal root／既有來源時顯示「建立並啟用個人副本」。按鈕先預覽來源、個人 DB、marker、receipt、來源備份與 rollback audit；取消不建立副本，確認後才 convert／activate。未啟用來源只讀；啟用後固定 personal writer，回滾停止 writer 並保留新歷史，不切回市場來源寫入。未設定仍沿既有模式。正式 root／真實遷移／Native 尚未執行；操作與排錯見 [完整手冊](../07_guides/APPLICATION_MANUAL.md)，驗證見 [個人儲存 QA](../06_qa/PERSONAL_STORAGE_SEPARATION_LANE_20261005.md)。


## UX10 方法與家族符合度（2026-10-06）

每日研究名單在同一 accepted snapshot 顯示唯讀母體與選取股票摘要：方法三態分母、符合方法數／去重家族數、方法版本與理由。雙 MA 命中為2方法1家族；缺第二合格獨立家族則跨家族未知，排名不加入方法count、不增加分數。partial／不相容來源與清除不留舊摘要；不觸發新運算或producer。整項UX10維持partial。[Manual](../07_guides/APPLICATION_MANUAL.md)／[QA](../06_qa/UX10_MULTI_METHOD_LANE_20261006.md)


## 個人 notes 與唯讀研究動作（2026-10-06）

研究筆記／個股研究動作、決策工作台 continuity、推薦個人選擇／ACK、outcome journey 使用同一獨立 notes selector。personal 使用個人 JSONL；legacy_read_only 顯示舊 notes，但控制器禁止保存研究動作，其他寫入也具名拒絕。缺 personal notes 不 fallback，不要求啟用 watchlist。未設定保留原 writer；正式 root／migration／Native 仍待批准。[Manual](../07_guides/APPLICATION_MANUAL.md)／[QA](../06_qa/PERSONAL_JOURNAL_LANE_20261006.md)


## 版本化規則說明卡（2026-10-06）

回測策略設定增加「查看版本化規則說明」按鈕；按需唯讀投影目前StrategySpec，顯示版本／此次參數／未知交易契約。來源與hash放收合核對區，開卡不初始化VersionService或executor，不用目前identity替舊run補章。操作及不可评估限制見完整Manual。


2026-10-06：研究Registry「查看單筆結果與規則」以背景讀取保存來源，結果類型／期間／成本／來源資格可讀，詳細ref及hash收合；錯身份拒絕連結、未知保留，換選取／取消不套舊回呼，不提供新績效算法。

### 2026-10-06 UX20 單批 MA 樣本限定整合

既有隔離 MA CLI 明示保存完整 matched/notmatched/unknown/excluded 單批capture＋receipt，再按原pin唯讀核對readiness；既有MA頁只呈現當期完整控制組投影並明示尚未保存。included≤16、超限拒絕；未知availability/calendar/outcomes不補PIT或訓練資格。Stage5／UX20 partial，多批parent／排程與Outcome接線仍是工程待辦。QA：`docs/06_qa/UX20_SAMPLE_CAPTURE_INTEGRATION_20261006.md`；操作以Manual同日章節為準。個人儲存／Journal程式已整合，只有正式migration／activation未做。


### 2026-10-06 UX20 多批母體有限整合

具名parent manifest已沿既有query-only source／producer／capture／readiness完成多批保存、新程序讀回、取消／失敗／安全重試；每批included≤16，完整母體最多16批，缺批與途中來源／方法改變不能complete。producer發布狀態與sample捕捉狀態分開，uncaptured另列。UI未改；Stage5／UX20仍partial，固定時鐘／排程留存、Outcome H5/10/20與母體UI瀏覽仍待工程；官方available-at／日曆及自然成熟另待證據。操作依APPLICATION_MANUAL最新多批章；收據：docs/06_qa/UX20_PARENT_CAPTURE_INTEGRATION_20261006.md。


### 2026-10-06 UX20 保存母體收據瀏覽

每日研究條件新增明示選取parent receipt的背景唯讀視窗，沿原writer/readiness核對；首屏列母體／資料日／方法、完整／uncaptured與每批producer/capture結果，技術身份折疊。重複點擊／取消／返回／stale回應不重跑producer或套舊資料；readiness拒絕時保留已驗envelope的發布記錄，母體資格未確認。15 offscreen測試、Workbench85、validator25/4skip、mypy806+final targeted2通過。Stage5／UX20保持partial；固定觀測日policy、漏日／修訂接受與owner容量部署仍待工程，UX21獨立lane未接受。QA：docs/06_qa/UX20_PARENT_RECEIPT_UI_20261006.md；操作依Manual最新章。


### 2026-10-06 UX20 固定觀測日接受限定完成

既有parent receipt→原readiness→child exact資料日→固定cutoff/窗口/expected dates接受policy→共用atomic writer→新程序唯讀日報已接線；隔離CLI預設preview，--accept明示保存。缺目標資料日不能借latest或前日補完整，同日不同revision保舊、相同policy/parent冪等、failure/partial安全重試。23不同案例、targeted mypy2/compile3/quant/diffcheck通過；UI未改不重跑前批gates。Stage5／UX20仍partial；正式daily owner/Task/cadence監控／容量留存部署與官方來源治理仍待工程/決策，UX21三檔獨占未接受。操作依Manual最新章與Supplements，QA：docs/06_qa/UX20_OBSERVATION_DAY_ACCEPTANCE_20261006.md。


### 2026-10-06 UX20 隔離daily owner可執行整合

新增明示runtime/target日期的isolated daily runner，直接沿既有producer/parent/observation接受串全鏈，preflight為預設；capacity/quota先檢，有限retry/合作cancel/漏日與revision監控，exact receipt重用。source/日期/配置一致才完成，producer已發布與capture拒絕分列保留；未配置不選生產值。17不同案例＋最後source/config兩例重核、targeted mypy2/compile3/quant通過；UI未改。Stage5/UX20仍partial，正式date-owner/calendar/Task/ACL/留存治理待工程/決策；UX21三檔未整合。QA：docs/06_qa/UX20_DAILY_OWNER_ISOLATED_20261006.md；操作依Manual。


## 2026-10-06 保存母體研究結果

每日研究條件→查看保存母體收據新增H5／H10／H20頁；選擇綁定原parent identity的明示研究輸入，背景唯讀核對exact children與原來源。逐方法完整分母及逐股毛／net／excess與資料不足／未成熟分列；清除／換收據清舊結果，取消／晚到callback不套用。成本／benchmark未知不補default，符合方法非交易入選，詳細診斷收合。JSON、公式、限制與排錯以[Manual](../07_guides/APPLICATION_MANUAL.md#2026-10-06-ux21-保存母體-h5h10h20-研究結果)為準，驗收見[UX21 QA](../06_qa/UX21_FORWARD_OUTCOME_20261006.md)。


### 2026-10-06 UX21 保存成效收據入口

母體收據→研究結果 tab「選擇結果輸入／保存收據」可讀新隔離 outcome receipt；背景 original parent/children/hash 核對，完整 H5/10/20 分母、毛/net/excess、未知或未成熟分列。主文明示目前觀察／年度計畫，保存版本不查較新 DB；錯 parent／損壞／取消／stale 仍拒絕。入口與操作：[Manual](../07_guides/APPLICATION_MANUAL.md)，實際市場背景收據：[QA](../06_qa/UX21_SOURCE_STORE_DAILY_20261006.md)。


### 2026-10-07 dev 完整保存母體瀏覽

推薦分析→每日研究條件新增完整保存母體區：明示選原保存來源，三個既有 v2／v3 條件全域 AND／OR 篩選排序後分頁，完整分母與排除／未知分列。原 child 下鑽等待背景核驗，再開個股；返回保留來源／query／頁碼／選取，取消及 query 變更撤回舊請求。瀏覽不產生研究；正常 UI 產製、v4五規則full-N、完整 query 收藏／比較與 candidate／Native尚未完成。入口、限制及排錯見[Manual](../07_guides/APPLICATION_MANUAL.md#2026-10-07-施工版完整保存母體瀏覽)，證據見[M2 QA](../06_qa/BALDR_COMPLETION_M2_20261007.md)。


2026-10-07 dev個股研究新增「保存的個人 H20 研究預測」首屏卡：active context獨立核驗原保存cohort，報告失敗仍可呈現gross／三日期／尚無已核驗實際結果；「重新核驗保存預測」沿原pins，不切latest。返回pointer漂移保留原名單／排序／選取，不換新來源；H20收藏尚未接。操作見[Manual](../07_guides/APPLICATION_MANUAL.md#2026-10-07-dev-修正h20-摘要獨立於一般個股報告)，中央96案例與合成contract／Native限制見[M2 QA](../06_qa/BALDR_COMPLETION_M2_20261007.md)。

### 10/14 官方條件與價格研究候選

推薦結果來源分頁新增價格範圍與四組條件共用完整母體的研究頁：Decimal上下限／inclusive／獨立未知價格政策、四組結果後共通AND、全域價排序與跨頁比較，並有V2 typed Watchlist保存／指定pins重開。首次view恢復等待range穩定並重核generation/result/page/選列後才發成功終態；不能用原payload或latest替代來源核驗。既有V1收藏保留。指定合成257股／雙parent的Main→新PID有限旅程、受影響UI與必要回歸已通過，真N／Native／同版EXE、來源或完整產品Gate未接受；詳見[操作說明](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#官方條件與價格研究)與[本輪QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。
### 10/14 Registry 雙 run 完整期間診斷

Backtest既有Registry新增恰好兩筆推薦回放的期間診斷，沿原保存／public reader，不重算策略。固定日曆原件、保存收據SHA與市場後比較，分列完整run／parent／策略版本、預期與實際日期、缺日及具名阻擋；返回保留選取。取消、來源／選取／研究世代變更與關閉拒收舊結果。候選日曆及unknown來源／幣別／成本不授績效，操作見[手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#registry-雙-run-完整期間診斷)，限定驗證見[本輪QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment20恢復後reader與正常registry旅程)。

Increment22原保存入口另保留本輪next-open執行輸入；None／0、submitted／effective lot與policy內容在Registry V3精確讀回，舊V1／V2不補值。合成Main保存階段後的焦點FAIL保留，重用兩筆run於父24812→新28756完成重開／比較／返回，9來源不變；這不授完整績效、Native或EXE資格。

Increment23原日曆控制新增「保存原件／每日批次」來源模式；daily固定雙SHA與獨立接受紀錄，缺接受時停用。背景仍用同一pair／public reader，結果顯示批次、原件與時鐘，來源欄或接受紀錄變更會取消並丟棄舊回覆。合成Main父33268→新17672重用17來源、開啟／比較／返回通過；正式Main未配置真接受紀錄，不宣稱真日曆用途接受或完整績效已完成。

Increment29已有正常Main的外部接受binding配置接點，原daily表單不變；缺設定或錯SHA保留具名原因，錯誤跨來源模式維持，只停用日曆用途。年度合成Main2440→fresh36248沿正常配置重開／比較／返回通過，真用途接受與正式配置仍待。設定與排錯見[操作手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#registry-雙-run-完整期間診斷)。

## 2026-10-15 第一版價格研究窄結果區

價格研究的窄結果區、來源與尺寸驗收範圍已收斂至[推薦分析](#workspace-recommendation)；原 Increment35 QA 錨點保留於該契約。

## 2026-10-15 第一版單股回測結果修復

單股 next-open、未成交日收盤估值、完成配對、即時與歷史摘要的未知值契約已收斂至[策略回測](#workspace-backtest-research-lab)；原 Increment36／37 QA 錨點保留於該契約。

## 第二階段：保存策略逐日訊號對照（Increment133固定候選）

固定133在原Registry明選2至5具名單股策略，比較同一實際研究窗的原保存訊號；新的canonical價量證據另綁execution／rule card，暖機不同不以整段指紋誤拒，缺舊證據不補造。新介面列各策略意圖數、逐日三態、策略／家族數、分頁與原保存規則，選取／metadata改變、取消或晚到清舊結果。沿原頁捲動到入口，對照視窗關閉回原列表；不重算／重存或用意圖當成交。來源Main44552→44732及新EXE9076→15412已限定驗保存／規則／原結果／返回／fresh，同419日金融輸出一致，包內附三筆示範；操作及非績效用途見[手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#保存策略逐日進場意圖對照)與[133 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment133-saved-signal-comparison)。

## 第二階段：雙策略逐日原觀測

研究Registry的完整期間頁沿同一public exact pair結果，另以100個實際日期／頁展示左右兩run原capture的股票、現金、持倉估值、權益與可選已實現／未實現損益；日期採實際聯集，缺該日為無觀測，原欄位None為未提供，不補0。金額保留原Decimal文字，分開列各側本金、期間、完成狀態與幣別，不加總或重算；來源／日期覆蓋／資格阻擋保持。返回、取消、換選取或重試清空舊明細。這是後續開發分支的P08可讀流程，不追加為固定9fa第一版的前置，也不代表完整雙策略績效、歷史PIT或Native／EXE已接受。操作見[Registry指南](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#registry-雙-run-完整期間診斷)。

## 後繼Source：一般報告保存與原文回訪

一般個股研究的外層「我的判斷」沿既有Journal保存完整當次report/context與原文；「保存時報告」獨立只讀呈現原內容，不重查producer或混入Main即時資料。可明選舊筆記、追加修訂、核對原報告與直接前版比較；保存時鐘與查詢截至分開。排名context暫不支援，原缺件／資格保持；固定02未包含，新Source旅程正在驗證。操作見[手冊](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md#一般整份報告的判斷後繼source)，結果見[具名QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#一般報告保存整合qa82起)。

## 第二階段：期限計畫與實際取價日期（固定134）

個股「決策→結果」沿同一原推薦／股票的精確唯讀旅程，逐期表分列原計畫目標日與實際取價日，並以中文分清計畫日缺價與尚待成熟。說明欄使用剩餘寬度，日期欄在正常視窗可見，長原因保留tooltip；選取／返回／fresh仍核同一原件。來源日期不明、非canonical或舊結果缺證據時維持未提供，不用舊價格列估計日或新日曆補算，不改報酬與金融資格。Source Main36184→48864、EXE15312→28164與定向回歸已驗，同原結果／日期及fresh一致，固定134已交；步驟見[期限判讀](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md#期限日期與缺價判讀increment134來源候選)，完整界線見[134 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment134-outcome-plan-price-dates)。

題材頁已交付固定05的已載入版本內股票反查：完整代號或名稱片段→明選股票／鏈／題材→定位原成員→原個股往返。多題材與同名不默選，換版／失敗／取消／關閉清舊選項；不讀新來源或補缺件。Source與固定EXE／新程序均有限定證據，操作與QA見題材研究手冊；固定04保持。

固定06的實際25鏈、90題材選項及每鏈一個代表題材成員已由獨立產品view／新程序QA158核對，雙擊原成員的股票signal一致；原映射與數值不變。這不等於25鏈完整Main報告／返回、法人／合格日曆或歷史PIT接受；Main未改接線沿05具名證據。

固定06修正原保存推薦首屏：已核讀、無新保存receipt的結果在720–899px結果欄寬度，只將來源與標題動作列改橫排；風險／其他列維持原900px規則，真正窄窗仍堆疊與可捲。成功讀回與fresh執行重算排版，失敗／取消保留原結果；同一控制實例、public port、來源身份及金融資格不變。正常1280×760真五股與CTA、新程序、舊讀回及取消已驗，固定06正常EXE／新程序亦已核；05保持。步驟見選股研究手冊，具名證據見本輪題材QA142–143。

固定06的期限表只對至少兩種期限、每列都共有的來源限制取交集，集中一次；逐期Display先列已連結期限的target／gap，非LINKED仍先列原阻擋原因。可選tooltip矩陣保留每列完整六欄原文，舊model呼叫維持相容；換context、loading／錯誤及空表清共享標籤。讀取、DTO、品質／成熟／採認判斷與日期不改，真八期限／Source新程序已有QA145–146b證據，固定06同版EXE／新程序由QA151核對；05保持。

後續Source的F07筆記保存改用同次fresh來源核對及Journal實讀清單，只有generation／股票／canonical bookmark一致、沒有pending load且非關閉中才套用；錯收據、缺保存時間拒絕，寫入不可取消。有界語義證明只省重複計算，保存／讀筆記／開原版仍完整fresh。同View／同query返回沿既有P01頁面重讀並比對新selection，無匹配state仍full重開，完整性失敗不回退舊DTO。QA167定向及共同防線、168正常Main／新程序三篇保存／修訂／返回／保存中關閉通過，均保留原15／240秒及原失敗。固定07已包含，06未含，見[具名QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#f07語義證明範圍qa163164)；固定07由173a另驗同版EXE，不授完整金融或真人接受。

固定08的題材雙向排行沿原四類排行加高／低排序；完整合格母體各取五名，四張高端摘要、成員定位及原個股返回保持，缺件不補值，固定07未含。排序原值精度與操作／接受邊界見[題材手冊](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#產業與題材後繼source)及[QA176起](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#題材雙向排行qa176177)。
