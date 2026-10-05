# UX16 唯讀來源契約與 UX02 Native 中文驗證（2026-10-05）

## 最新延伸：UX18 既有日特徵的實際研究 consumer

基線 `50f45ce692703d8b80be91c3c6f8bf2ed2a32e17`。本包依原計畫第8.7／10／11節，完成 current-observed 研究模式的有限垂直切片：`daily_market_feature_snapshot.py` 投影已讀到的 close／MA20／MA60，`StockResearchReportReadService.read_report()` 實際呼叫並將結果交給研究理由與首屏。不是新增 CLI 或未使用的矩陣；不新增公式、方法、分數、排名、SQL、producer或持久化 writer。

契約 `daily-market-feature-snapshot.v1` 保存股票、決策日、單股scope、實際資料日、單位 TWD/share、來源／每列fingerprint、實際DTO內容hash與snapshot identity。Decimal比較輸出 `match／no_match／unknown`，above／below／equal是既有觀察，equal屬no_match。同輸入共用immutable snapshot；同日價格或指標內容、來源hash、scope、決策日、契約版本變動會使cache失效。每service的RLock／LRU最多4筆；`to_dict()`建立新的mapping，不讓caller改動cache。

暖機沿用既有 `calculate_causal_indicators` 的SMA20／60必要條件：截止當下最後一段連續有效、正值、範圍一致的OHLC。缺值／壞值會中斷，不跳過缺口湊筆數；未來日、重複／壞日期、缺最新收盤、技術來源日期／品質／identity不符則具名unknown。最多120筆既有報告窗口能證明有限SMA的**必要observed-prefix**，不證明原producer計算等價、官方交易日曆完整、EMA遞迴暖機或歷史PIT。原technical table數值只投影，不重算。官方availability與calendar completeness保持unknown，historical_pit_eligible=false。

新DTO欄位 `shared_daily_features` 是加法相容；舊DTO預設空mapping保留原呈現。新報告研究理由與首屏讀同一三態；若暖機／來源未確認，顯示尚無法判讀，不能再由首屏自行比較而得出另一結論。投影故障保留錯誤與unknown，取消仍傳遞。RSI／MACD／ADX及既有Advice／原排名不改。

### 依賴裁定與原計畫狀態

原第10節把階段1列為整體階段2前置；沒有把Backtest20%單獨列成每個唯讀constructor的硬gate。第8.7明示可用「准許研究」來源及具名partial research，父層最新授權本包有限consumer接線。因此本切片可完成，**不宣稱階段1／2全過，也不放行UX19正式發布**。Backtest18.62%／20%仍未達，不調門檻或重測湊數。

| 原計畫項目 | 狀態／下一個實際依賴 |
|---|---|
| UX16 | 唯讀來源契約已交付；完整universe、官方availability、歷史成員／PIT仍partial。 |
| UX17 | 效能partial；Backtest子gate未達，既有數字凍結。 |
| UX18 | close／MA20／MA60版本、單位、暖機、三態、cache與研究consumer已接；完整feature dictionary／固定method契約／選股consumer／增量與全量等價仍待。 |
| UX19 | 待工程：既有owner的有界producer、decision manifest、整批完整性、原子發布、重播／修訂、容量與成長預算。這些不能稱為等待自然成熟。 |
| UX04／05 | 待共用snapshot的完整契約及其他consumer接線；本包僅個股首屏／理由。 |
| UX20／21／ML | 沿原自然capture／outcome與資格契約累積；歷史PIT及natural maturity不足限制其用途，不阻止本包研究工程。 |

benchmark未用於本包price-vs-MA觀察；未提供benchmark證據不會偽造值，也不新增此切片的依賴。後續相對特徵需工程核驗版本／窗口／cutoff。歷史PIT、官方時鐘與自然成熟是證據缺件，與可修的source／warmup／manifest工程分列。

測試結果與commit讀回記錄於本章末的「UX18驗證收尾」；下列UX16／Native資料保留其原版本與來源，不借用為新consumer的真實Native證據。

### UX18驗證收尾

- Root backend定向bundle：51 passed／2 failed；兩個失敗是短Temp祖先的no-follow handle無法錨定，導致既有Advice測試降級。只把這兩項改用repo隔離QA basetemp重驗，2 passed；53個不同測試皆有通過證據，不稱首輪全過、不改安全guard。XML：`output/qa/ux18_shared_features_20261005/final_backend.xml`／`advice_recheck.xml`。
- Root UI定向50 passed，含共用unknown／equal／日期不符／壞mapping及舊DTO原行為；Workbench85 passed；validator25 passed／4 skipped／0 failed。pytest預設cache寫入警告不影響斷言；後續bundle停用cacheprovider。UI XML：`ui_focused.xml`／`workbench.xml`。
- full mypy最後769 source files通過；首輪新module3個型別錯已修（selected_metric型別與latest_row None narrowing）。7個changed Python檔compile、quant guard通過。Agent新backend9 passed；其首輪future fixture誤設cutoff的1失敗修正後通過。Consumer4 passed，另含舊PIT readback的一跑4 passed是重疊證據，不累加。
- 真實consumer測試使用小型隔離SQLite，實際 `read_report()`→shared snapshot→DTO／rule_reasons；驗證同源object reuse、同日來源修訂identity失效、20／60暖機、短歷史／日期不符、投影故障fail closed與取消。沒有實際learner、正式DB／registry、Native1477、效能重跑或市場producer；validator既有12列受控指標fixture不是正式producer運行。
- 原plan保持原bytes前綴，append-only追加本包done／partial／pending與依賴；本地precommit／commit_readback保存逐檔raw SHA、Git blob、HEAD／parent／status。raw output與本機active_task依git排除規則不stage。未知paper檔未讀／hash／改／stage，C:/ta_iso_1005映射未動，未清理或push。完成commit／核驗後停止交父層。

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
