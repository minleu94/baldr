# 階段1早期SQL取消與下一包依賴（2026-10-05）

本包基線 `2acdbe2ce509ad0dad92740a9e7987e781f37548`。沿用唯一原計畫 `output/plans/baldr_product_experience_plan_20261004.md`，優先補 Breadth／Relative Strength 早期 SQL 的合作取消。原stage1改善已獲父層接受，沒有為補速度百分比微調Backtest、重跑五次baseline或啟動新ML。

## 原計畫條件與上包凍結門檻核對

原plan第10節階段1交付是「有依據的延後初始化、共用查詢、有限cache／queue；狀態字典、上下文列與閱讀分層」，完成條件為初始負擔無量測可辨識回退、主要瓶頸有改善證據，切換閱讀層不改結果。UX17要求啟動各階段、程序樹資源、lazy頁面／模型與bounded cache／query，以同資料同機器比對，不能把計算搬到背景當成資源下降。共用語言仍是本階段待交付項，不以自然ML成熟作為UX17工程阻擋。

以下五跑值屬 `2acdbe2c` 收據；原始before與after summary不改，詳細來源、時鐘／資源範圍與hash見[上包收據](PRODUCT_STAGE1_PERFORMANCE_IMPROVEMENT_20261005.md)。

| 修改前凍結門檻 | 同條件before→after | 具體結果 |
| --- | --- | --- |
| 首屏median回退≤10% | 10.1482281→8.6417741s，-14.84% | 通過 |
| 四筆只啟動process-tree peakRSS median回退≤10% | 700,694,528→573,241,344 bytes，-18.19%；after範圍572,538,880–577,310,720 | 通過 |
| Loaded30＋close同操作場景peakRSS回退≤10% | 1,569,636,352→674,918,400 bytes，-57.00% | 通過限定場景；包含提前取消，不代表完整盤勢計算省57% |
| IndustryMapper分段median改善≥20% | 3206.3275→1841.5851ms，42.56% | 通過 |
| BacktestView分段median改善≥20% | 1097.9002→893.4496ms，18.62% | 未達；差1.38個百分點，父層接受部分改善，不調整原門檻 |
| 已載入30次distinct列高亮p95<300ms | 116.5995→49.6474ms（after max91.6721） | 通過；只代表選取高亮與repaint |

核對發現原 `STAGE1_INTAKE_AND_ROLLBACK.md` 凍結的是兩個瓶頸各自20%，不是任一達標就全過；上包QA文案已更正，原預算未放寬。不能宣告完整stage1／UX17或全部gate通過。

原>90秒loaded／close失敗確實已改善退出：上包同操作場景整個child elapsed13.3487311s，registered worker=0，五跑無78秒self-limit或90秒`COOPERATIVE_CLOSE` marker，10個launcher／Python PID均退出；不是僅UI消失。13.349s包含啟動與30次操作，並非單獨close latency。額外完整背景snapshot＋首次圖表探針29.9876s、選取後等待18.1705s、worker已結束，RSS1,451,900,928 bytes／CPU33.8125s／read4,512,968,456與提前關閉分開。原before沒有完整snapshot正常完成數據，因此不捏造完整計算加速比。

## 本包產品與驗證

產品只改四檔：`decision_desk_service.py`、`decision_market_frame.py`、`market_breadth_service.py`、`relative_strength_liquidity_service.py`。Builder→區段service→provider→共用loader完整轉傳單次worker的callback；兩個provider的獨立SQLite分支亦安裝連線專屬progress handler。沒有在loader instance／global儲存可變取消狀態。真正handler回傳1才將SQL例外轉為取消；取消例外不當作DEGRADED。舊單參數provider保持相容，無callback介面的外部provider仍僅前後檢查。

SQL每1000 VM步驟檢查；CPU轉換保留原Series.map／dtype／index／name／categorical語意，加有界checkpoint；股票群組／廣度迴圈亦可合作取消。沒有改Decimal計算、交易日window、cutoff、極值含tie規則、原排名或DTO身份。Look-ahead自查：所有SQL日期限制與當期／歷史分界原樣保留。本包證明內建Breadth／Relative Strength／Smart Money路徑，不宣稱所有外部provider與其他工作都能立即中止。

Focused四模組47 passed；root的決策頁／主工作區／shutdown整合50 passed，mypy766與7個變動Python檔compile通過。47首輪46pass／1fail僅因新breadth測試fixture缺既有SQL必要的「漲跌價差」欄，修fixture後新basetemp全47通過，產品未藉此改寫。未改UI main／view、原初始化優化與profiler；上包Workbench85／validator25及4skip屬未變UI工件，不再次跑完整重複驗證。

Native在同一唯讀QA資料、隔離output／settings、Windows platform串行跑兩個補充場景：

| 場景 | 實際證據 | 結果 |
| --- | --- | --- |
| 早期Breadth SELECT執行中關閉MainWindow | 真實SQLite trace→progress handler回傳1；close當下worker仍running且視窗可見；取消至native-finished32.77ms、至hidden131.31ms；snapshot仍None、worker0 | 通過，child整體9.780s，launcher／Python PID34524／19148均退出 |
| SELECT執行中取消→同來源按鈕重試 | 取消至native-finished15.30ms；沒有取消後完成snapshot；實際更新按鈕重試21.141s產生真實snapshot，沒有provider／SmartMoney error | 通過，child整體31.885s；PID36064／29220均退出 |

探針使用真實SQLite Connection子類觀測trace與progress handler返回值，不延遲／替代SQL、不fake DTO／finished。`early_close`的`--loaded-selections 1`只用來進入既有runner補充hook，沒有列高亮；原收據明示`not_measured`與selection_count0，不能當p95樣本。正常重試場景的整體peakRSS1,456,594,944 bytes／CPU33.90625s／read4,517,943,004；其起算點是重試按鈕，與上包「選取後等待」18.170s不同，不相減宣稱回退或加速。正常重試包括先取消一次，亦不和只啟動／提前關閉資源混算。

最後使用未改profiler一次同操作loaded30 spot check（非新五跑median）：首屏9.3496921s、首次Workbench資料9.2541812s、30 distinct高亮p95 54.173ms、peakRSS618,389,504 bytes、CPU14.03125s、read267,326,866、整體elapsed13.420869s；worker0、PID32908／35092均退出，無78／90秒關閉marker。首屏及RSS在原凍結before上限內、p95<300ms；單次值不貼成新五跑中位數，也不補造未達Backtest20%的改善。

三個Native場景均child／parent exit0、failure=null；全部6個launcher／Python PID退出，input guard每跑與最後通過。來源preflight除被精確允許的SHM mtime-only外與上包完全相同；Industry 212500 rows完整rowset SHA仍`sha256:ff055b018b425fab26ec633babf449c5fbc1ac91a98c22efe1cbdae1f7a03a08`，final30的reader 62728 rows、20260818–20261002、top50／1978與30個ids不變。大DB仍只做stat pin、WAL／SHM／小輸出與receipt有hash，不宣稱全大DB hash或正式source availability。

未變的Industry provider、Backtest兩檔、main與profiler五個blob已逐一比對2acd，因此重用上包版本明確的五跑資料；本包四個backend已另外focused／Native驗證，不把舊數字偷貼到新backend bytes。所有測量時Python SHA與新summary hash留`output/qa/product_stage01_20261005/stage1_sql_verified.json`。

原始證據：`baseline_agent/s1b_close`、`s1b_retry`的summary／run-01/sql_lifecycle.json（保留正常retry真實snapshot）、`s1b_loaded`的summary／input_integrity_final；`stage1_sql_ui.xml`；focused新basetemp `stage1_market_followup_a42fc06ecd834f9eb048b2b1805c8690`。首輪fixture失敗與首次Native長label複製超過Windows路徑長度保留；後者發生於小output seed複製、child尚未啟動，換短label後再跑，沒有刪除失敗目錄／改profiler／操作正式資料。

## 下一個原計畫可交付包

接續stage1／UX02共用語言：以現有Research Console狀態為起點，建立純呈現映射入口，分開載入結果、資料可用性、研究結論、正式資格與回測驗證狀態，保留未知碼，不把所有warning翻為同一「注意」。先接回 `ui_qt/views/research_console_view.py` 與 `ui_qt/views/backtest/presenter.py`，沿用 `ui_qt/widgets/session_context_strip.py` 的股票／決策日／資料日／結果ID／profile／來源／版本上下文與 `theme_widgets.py` 分層元件。既有測試入口為 `test_ui_qt_research_context_status.py`、`test_ui_qt_research_console_view.py`、`test_backtest_view_presenter.py`；需補跨頁映射／未知碼／切換顯示不改結果身份的驗證。這是下一包範圍，尚未實作，不擅自改九工作區導覽。

UX16的欄位、warm-up、availability、universe／PIT／benchmark缺口是新增UX18／19方法與快照的來源依賴；UX19的容量／有界producer亦另依既有reserve及writer授權。它們與本包取消工程、UX02純呈現切片分開，不因等待自然ML／樣本成熟而停止可完成的UI工程。UX01→UX16/17→UX18/19→UX04/05及UX19→UX20/21→UX22/23維持；本包不跳至新ML。

兩位原指定Luna Max分工：market lifecycle實作，startup代理僅唯讀診斷下一共用語言包；沒有再生代理。root統一Native／文件／Git。未push／全量訓練／producer／正式writer／大DBcopy／永久清理，未知paper檔與C:/ta_iso_1005映射未動；Native僅使用隔離QA視窗，桌面授權16:11UTC截止。

## 2026-10-11 後續 UX02 狀態

上方「下一個原計畫可交付包」記錄本 SQL 取消收據當時的待辦。其後 UX02 已另以[共用狀態詞彙有限切片](UX02_SHARED_STATUS_VOCABULARY_20261005.md)完成具名呈現映射、未知碼保留及研究狀態與正式資格分列。這只關閉該文件標示的 UX02 有界入口；不改本文件的原測量、Backtest 18.62% 未達 20% 門檻，也不表示完整 Stage 1／UX17、來源 gate 或所有 consumer 已驗收。
