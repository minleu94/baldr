# UX16 唯讀來源契約與 UX02 Native 中文驗證（2026-10-05）

基線 `dc14c080ed77ad1a314bb0aa17542993ee153def`。沿用唯一 `output/plans/baldr_product_experience_plan_20261004.md` 第8.7／11節，Root Sol整合兩位指定Luna Max；來源實作與Native QA分工不重疊。

## 可交付範圍與依賴

UX01→UX16／17→UX18／19→UX04／05的順序維持。階段1尚未全數達門檻：Backtest初始化改善18.62%，原門檻20%；本包不重跑效能、不調整門檻。UX16交付 current-observed 唯讀來源契約與快照前置檢查，讓明示範圍的當期研究可重讀；不啟用共用特徵producer、正式每日快照或新方法。

原計畫要求的完整universe、歷史產業成員、benchmark版本／窗口、特徵暖機、as-of／available-at證據仍須逐項核對。缺少歷史PIT不阻擋具名當期研究，但不能反推決策當時已知、正式訓練或模型資格。原Rule Champion snapshot owner維持責任，這份研究preflight不是第二個正式writer。

Native使用既有Windows中文字型與自有隔離Qt程序；不安裝字型、不改OS設定、不操作使用者既有視窗。四用途代表狀態的來源、畫面與限制分別記錄，受控DTO不冒稱真實自然資格。

## 實際交付與契約

- `app_module/current_observed_source_contract.py` 的 `build_current_observed_source_contract()` 接收aware cutoff、臺北as-of、1–60來源交易日窗口、可選明示cohort／source pin／rowset pin／feature宣告／當期分類。拒絕未來cutoff、錯日期／scope／來源版本；不計算策略、特徵或金額。
- `DecisionMarketFrameLoader.load()` 新增opt-in `include_source_timing`／`raise_sql_errors`，cache模式分開，預設caller欄位／回退維持既有行為。SQL故障在contract具名拒絕，取消例外不吞掉。
- manifest保存schema、讀前後main／WAL／SHM身份、實際scoped rowset hash、cohort分母與缺件、正規化股票／交易日判重、每檔觀測窗口，以及known／unknown／invalid來源時鐘。WAL變動仍拒絕；SHM僅mtime變動明示為共享索引metadata，不授immutable內容資格。
- cutoff-screened子集只收有效市場日、明示且不晚於cutoff的available_at、無無效或晚到observed_at的列；欄名與可解析時鐘不代表官方可得日核驗，`official_availability_verified=false`。沒有source clock的當期列仍可觀測，PIT／正式訓練／published_snapshot始終false。
- feature spec／暖機與benchmark是caller-declared unverified；沒有證據保持unknown，warmup_qualified／benchmark verified不會授予。當期分類具有rowset hash，`cutoff_qualified_rows=0`，不建立歷史industry membership。
- `scripts/inspect_current_observed_source_contract.py` 實際呼叫API，預設stdout UTF-8；可選create-only repo QA JSON，不覆寫來源或舊收據。錯輸入JSON類型返回具名invalid_request。完整參數、判讀與排錯見 [Manual](../07_guides/APPLICATION_MANUAL.md#2026-10-05-ux16-唯讀研究來源契約)。

## 真實有界來源讀取

最終 `real_probe_final.json`／`real_probe_final_execution.json`：2026-10-05 12:34:13–12:34:15 UTC，正式D `sqlite/twstock.db`、明示2382／1477、3個來源交易日，CLI RC0／status observed。Loader回傳5886列，再按明示cohort取6列；此為返回窗口界限，不聲稱量測SQL總IO或全市場資格。

| 項目 | 實際結果與限定 |
|---|---|
| 明示scope | 分母2，兩檔各3列／3個不同市場日，2026-10-01至10-05；missing／duplicate／invalid date均0。每檔正式日曆完整性與market universe completeness仍unknown。 |
| scoped內容pin | `efb41e6325b7867c20c0fa2032d9e19488dcd700ab9d0855a68ae8a316413f3a`；只hash所讀內容，不hash或複製4GBDB。 |
| schema pin | `e53098872a25f2df918f8ac86b0468f823cf2a10793cb5e843c067895ae9c19a`；daily_prices沒有available_at／observed_at，source availability unknown、cutoff-screened 0列。觀測時刻不補成歷史available-at。 |
| 檔案穩定性 | main 4,052,119,552B，device／inode／size／mtime前後一致；WAL0B身份一致；SHM32,768B僅mtime變動。這些stat不是整庫內容hash。 |
| 當期公司分類 | companies.csv 2列，1477紡織纖維、2382電腦及週邊設備業；date2026-08-10、download_time2026-08-11 08:13:44。rowset `a235c14a1e63139fddb6d1b7076c3edfe500a49c8be1f47a2157bdfb9f1012a5`；官方可得日與歷史effective intervals unknown。 |
| 特徵／benchmark | 本次未提供feature／暖機／benchmark證據，皆unknown；不能拿當期scope齊全當方法暖機或正式訓練資格。 |

兩次前置拒絕保留：`real_probe.json`是沙箱模式schema OperationalError，不能解讀成來源缺價；`real_probe_readonly.json`解除讀取限制後因WAL／SHM從缺席變存在而拒絕，主DB身份未變，沒有繞過guard。最終來源身份不同於較早UX02記錄DTO的DB stat，兩份證據各自保留identity，不合併成同版資料。本包未讀Phase3C／法人lane，沒有把9/29個股與10/2aggregate宣告同版，也不自動fetch。

## Native中文代表畫面

成功run `native_visual/run_20261005T123018645Z/`，四張完整View PNG皆1580×942、DPR1.0。Root與Native agent均以view_image檢查，中文清楚無豆腐字；只是代表性呈現驗證，不是全頁全狀態／主程式端到端／幾何門檻或新自然資格驗收。

| 圖 | 代表狀態與來源 |
|---|---|
| `01_decisiondesk.png` | 受控盤勢DTO：研究判讀、資料缺件／原始診斷、判讀日與產生時間分開。 |
| `02_portfolio.png` | 受控持倉DTO：系統來源缺件與EXIT研究提案分列，skipped_non_trading_day中文及原碼可見；不代表真實使用者持倉。 |
| `03_recommendation.png` | 受控execution／presenter：研究完成、ML unavailable、正式資格限制及歷史市場日期分列；新增中文display欄不改machine欄。 |
| `04_stock_research_report.png` | 記錄的真實唯讀DTO：2382、as-of10/5、價格331.0、ML unavailable且無run/event；當期上市來源10/4／觀測時刻與價格日分開，詳情／來源區展開。不是此run即時DB讀值。 |

字型為Windows既有Microsoft JhengHei（msjh.ttc），app-level載入。PySide6 6.10.1此runtime沒有QFontDatabase.supportsCharacter；receipt採writingSystems含TraditionalChinese與所有指定中文字元QFontMetrics.inFontUcs4=true，加上實際視覺檢查，不捏造不存在的API結果。未更改OS字型／設定。

Stock記錄DTO來源 `output/qa/ux02_status_20261005/report_observation.json` 的SHA `6034d5478f1c3f31ebdce6d2762c42878eca73698a183a6d64cf9fa147809bb0`，hydration→to_dict完全相等、檔案identity前後一致；既有120列price rowset SHA `94619978e24847c05cc3487745a5abddce0176a6d325c020f77f2b0c696c32be`不當成今天新核驗。成功Native run沒有查DB。前三輪失敗為import path、沙箱read_report未取得331、不合法float fixture；失敗收據／logs均保留。第二輪沒有可信DB前後statguard，不聲稱來源缺價或資料未變。四輪driver／launcher PID均核對已不存在，成功PID36288／35512。

## 驗證與下一依賴

- Agent定向來源／loader21 passed；首次分類輸出缺欄失敗後修正。Root加明示source clock不等於官方verification欄及numeric-boundary標記後，以新短Temp跑同兩模組：**21 passed／1.32s**，`final_focused.xml`。組別有重疊，不加總。
- 最終mypy 3 source files無issue、4個changed Python py_compile及量化防禦linter通過。人工核對無新增金融運算；float.hex只在DTO來源序列化邊界保留既有REAL值身份。時鐘與scope拒絕、partial／unknown、rowset改版、cache模式相容、SQL故障／取消、WAL guard、分類／暖機／benchmark資格與Windows UTF-8 CLI均有定向覆蓋。
- 9個產品UI與dc14c080 blob相同，`reused_ui_checks.json`保留比較；沿用上一包Workbench85與validator25／4skip，不重跑。Native只補QA driver／fonts／receipt，未改產品UI。

下一包先由父層裁定stage1未達門檻的處置與UX16尚缺證據；再按§8.7選具版本、單位與暖機依據的最小共用feature dictionary，核對增量／完整計算等價。UX19仍需decision manifest／原universe凍結、整批完整性、原子發布、idempotency／revision與容量guard；本preflight沒有writer能力，不放行新方法、自然ML訓練或正式snapshot。歷史PITunknown不阻擋具名當期研究，工程缺件也不以等待自然成熟帶過。

## 證據保管

原始QA位於 `output/qa/ux02_native_source_contract_20261005/`，不提交output。`intake.json` 記錄輸入／輸出與責任；`plan_before.md` 保留唯一原計畫修改前bytes；`active_task_before.yaml` 保留本機shared state前像。量化防禦linter通過，仍須以cutoff／來源／型別測試與人工審查判讀，不視為完整正確性證明。

本包禁止正式DB／registry寫入、producer／訓練、大DBcopy、全量重複回歸、Native1477重開與永久清理。未知 `paper_event_source_capture.py`、C:/ta_iso_1005隔離／還原映射保持原樣；本地commit與blob/status核驗後停止交父層，不push。
