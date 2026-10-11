# USER_GUIDE 歷史更新收據（2026-06-11 至 2026-10-06）

> 以下內容由 docs/02_features/USER_GUIDE.md 移入 Archive，保留原日期化功能與工程狀態紀錄。它們是各自記錄時點的歷史快照，不代表目前驗收或操作狀態；現行操作請依完整 Application Manual。

**歷史更新：2026-06-11（Phase 4.2 完成：持倉籌碼監控、主力下鑽定位高亮連動、SQLite 股數精準度校正、pytest 全量崩潰修復）**

## 券商分點資料重新補抓

2026-06-11 前的既有資料可能只有 MoneyDJ `c=B` 仟元金額。這些資料不會被當成 0 張：

- 有當日有效收盤價：折算為估計張數，UI 顯示「金額估算」並依覆蓋率調降信心度。
- 無有效收盤價：標記為不可用，只排除該事件。
- 新更新資料會同時抓取 `c=E` 與 `c=B`，並保存兩榜各自排名。

一般使用者不需要為本次遷移重新下載歷史網頁；重新合併與 SQLite 同步即可由現有檔案補回 observed/rank 契約。



## 更新記錄

- 2026-09-06：補上推薦指紋、未知因子、T+1／Registry 判讀及候選來源邊界；更新舊 Promote 與強制平倉說法。


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


## 個人 notes 模式（2026-10-06）

notes 的 root／mode 選擇獨立 watchlist activation；personal writer與全部 UI notes reader 共用單一來源，legacy_read_only 不寫來源。缺 personal 檔案不混讀舊 notes；未設定仍保留相容 writer。位置已選 FA_Data/personal；精確 root guard 已整合，必須明示設定；migration／activation 未批准。參數、操作限制及排錯見 [完整 Manual](../07_guides/APPLICATION_MANUAL.md)。


## 查看策略的規則來源

回測策略設定按「查看版本化規則說明」，可核對此次版本與參數。來源未提供的交易條件會顯示未知，卡片尚未連結執行結果，不能當獲利或可交易證明；來源核對區可展開。操作詳見[完整Manual](../07_guides/APPLICATION_MANUAL.md)。


保存研究結果可在研究Registry選單筆按「查看單筆結果與規則」，核對保存版本、期間及費率；身份吻合不代表正式資格。若缺來源或成本則不可評估，不自動改保存結果；操作與排錯見完整Manual。

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
