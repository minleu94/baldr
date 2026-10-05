# UX16 唯讀來源契約與 UX02 Native 中文驗證（2026-10-05）

## 最新延伸：UX18 兩條固定方法契約與 manifest 綁定

基線 c50cefcd，本包 root Sol 整合兩位明確授權 GPT6 Luna Max，僅補 `close_above_ma20`／`close_above_ma60` 研究觀察契約與拒絕讀回，不改公式或新增方法。Scope／回滾前置保存於 `output/qa/ux18_method_contract_20261005/rollback.md`；原計畫實作前137258 bytes、SHA256 `533846f7be6bc66dcda59033809a3e8d34ab16cffb6a5073f91d344b7ae96b7f`，僅追加本包。

方法 ID 為 `daily_market.close_above_ma20`／`daily_market.close_above_ma60`，家族 `close_vs_moving_average`，版本 `1.0.0`，固定窗口20／60、方向 above、必要欄位 close 與對應 MA。逐股結果保存決策日、可判讀資格與 unknown 原因；match／no_match 都只表示已有足夠觀察輸入，非選股勝率／alpha／正式資格。官方 availability／calendar unknown 與 historical PIT=false 保持。

方法規格於 feature 投影時捕獲並參與 input fingerprint／cache／snapshot identity；序列化不重新讀 live 規格。manifest v2 保存 `method_contracts`／`method_contracts_sha256`，inner artifact 與逐條結果必須同現行契約；pointer v1 容器只定位 immutable manifest，結構不變。錯方法／版本／參數／日期／hash 即使重算外層 pin 仍拒絕，實際 pinned StockReport 保 unknown、無 live fallback、無 Advice 替代。

manifest v1 具名拒絕，需要明確按更新重產；唯讀不改 schema／產物，producer 只在明示執行且舊原件 hash／canonical／identity 核驗後 fresh 投影。候選完整驗證後才 atomic latest；舊 immutable 保留，腐敗 hash 不列為正常升版。

最終有限 bundle **74 passed**（八個相關測試檔，含實際 producer→repository→screener→StockReport pinned 讀回與 UI bridge），`final_affected.xml` 為準，不將重疊的 agent62／12與 root15相加。六個產品檔 mypy clean，十一個改動 Python 檔隔離 py_compile、quant guard 與 diff check 通過；未改任何產品 UI blob，沒有重跑 Workbench／validator／全樹 mypy。初次 mypy 的 Literal 型別1錯已修；pytest早期 cache寫入警告保留，最終專用 cache 無警告。

受控 SQLite 的 Windows Native QTest 驗 `v2 正向讀回→v1 唯讀拒絕且 inventory 不變→明確更新恢復v2且舊 immutable 不變`；三張圖與收據在 `output/qa/ux18_method_contract_20261005/native_controlled_final/receipt.json`。App 同款 theme，1100×820，八個 code pins 前後一致、worker0、QA PID退出；只驗本研究契約相容性，非真實 D／全 App startup／Frozen 效能／真人投資有效性。首次 Native 的 QA assertion 誤以為 tooltip 會帶 error code而失敗，依真實中文 v1／v2 訊息修驗證；前兩輪與最終產物均保留，產品拒絕 guard 未放寬。

合法 registry version 改變：既有 v2 root 具名拒絕、不 reuse；新隔離 root 明示 fresh produce/readback 可保存新版本，沒有自動 v2→v2 migration。固定窗口 metadata 漂移至21違反既有 MA20公式，舊／新根均拒絕；feature cache fingerprint仍失效，不把 metadata 改動當新公式資格。

三張最終 Native 圖已保存 Library：正向 `libfile_309475ca1b308191b1327e33264419ee`，舊版拒絕 `libfile_1348669570848191b6ba69dacd8bcca6`，明確更新恢復 `libfile_57f96a9f76bc8191833c8f323f74637c`。來源均受控 fixture；Windows 缺 os.setxattr，未寫本機雲端身分標記，Library API 三項保存成功。

| 原項目 | 本包範圍與下一依賴 |
|---|---|
| UX18 | 兩條既有方法契約及實際 consumer 方法結果為本包限定範圍；整體 partial，其他 feature／方法與原排名／跨 consumer 共用待工程。 |
| UX19 | manifest 方法綁定及舊 schema 受控更新為本包限定範圍；整體 partial，完整母體／排程／長期容量／跨程序崩潰待工程。 |
| UX04／05／06 | 沿既有列表→pinned 個股讀回補身分驗證；強弱／原排名／收藏閉環尚未完成。 |
| UX17／stage1 | Backtest18.62%／20%仍未達，不重測／放寬；不阻擋獲准的研究切片。 |
| UX20–24 | 自然樣本／歷史 PIT／真人證據各自等待；新規則 outcome／ML 串接的工程缺項另列，不由本契約自動完成。 |

原排名／市場共用超出小改：`ScreeningService` 的 day／week、排序方法、來源版本、母體／top-N 與 `ScreeningResultDTO` 需先有完整來源契約，再固定讀模接入同一發布結果。現研究快照沒有原排名，不能從 MA 條件創分數；下一包由父層安排。

未改產品 UI，不重跑既有 Native1477／Frozen 效能／全量回歸；只有限 fixture producer／consumer，不訓練／寫正式 DB／registry／清理／push。未知 paper 檔與 C:/ta_iso_1005 還原映射未動；本地 commit/blob/status 核驗後停止。

## 最新延伸：UX04／05 日常研究名單與同源個股

基線695797ec，原plan§6.2／6.4、8.6／8.7、stage2→stage3與UX04／05／06／15。本包將既有close／MA研究快照接入Recommendation日常來源tab與個股研究，不以隔離CLI完成取代使用入口。來源仍是明示研究cohort，不與已保存推薦混合；沒有新策略／score／排名／推薦或自然ML資格。

預設研究區為repo `output/research_snapshots/daily_market`，不沿TWStockConfig正式output或資料根；app開啟／read-only重讀／條件切換只查現有快照，按「更新研究快照」才沿同一bounded source／producer產生，保留16股／120列／200GiB reserve／64MiB／4096項與candidate→atomic latest。不更動WindowsTask或正式market DB，不自動清理失敗／歷史產物。

條件只使用已存在的close_above_ma20／close_above_ma60；AND／OR採三態組合，每條unknown與理由獨立保留。例如OR已有一項符合、另一項未知時整體可符合，但未知欄不被寫成false；AND有不符合亦保留其他unknown。表列why／why-not、符合／不符合／未知計數、研究日與每股資料日，不把cohort count稱全市場覆蓋。

下鑽固定manifest hash／stable ID、root／cohort、條件／組合及decision date。StockReport按當前有限來源hash核驗pinned版本，每股保相同snapshot/input identity與判斷；來源修訂、缺件／錯股／錯日保持unknown與中文更新提示，不fallback live假stored成功。session event／store／reducer及Main coerce保留metadata；切股資料日來自新股核驗結果，返回要求原manifest，不以同股的新清單或保存推薦替代。

完整UX18／19仍缺更多feature／method、原排名與全母體融合、其他consumer、正式排程、長期storage治理與跨process崩潰驗收。Backtest18.62%／20%及自然PIT／ML限制維持；這是授權有限研究flow，不宣告完整stage2／3或正式推薦放行。本包定向／Native與commit證據見下列完成收據；舊章保持原版本。

### UX04／05 完成收據（2026-10-05）

已關閉有限 UX04 日常研究名單／UX05 既有兩條件 AND／OR 與三態原因／UX06 同源個股路徑。新增來源分頁曾擠壓舊 personal input（25px＜30px），已以結果區 scroll size policy 修正，沒有放寬測試；初輪 141 pass／1 fail 收據保留。最終整合144 pass／2 fail：QA長路徑令 create-only artifact os.link 遭 WinError3；僅這2案例改短 repo QA basetemp 重驗2 pass，合計 146 個不同定向測試有通過證據。Workbench 85 pass，update validator 25 pass／4 skip／0 fail，mypy 774 source files、10 個產品 Python 編譯、量化精度／未來函數 guard 與 diff check 通過。

獨立 Windows Qt Native QTest 實際 Recommendation／Main 路由／StockReport 及正式 D 唯讀 service：2382／1477 明示更新成功，AND 符合名單 0、OR 2；選取 2382 的判斷與 why／why-not 與原列相同，切 1477、重載、返回仍固定 manifest／決策日、保留篩選與選取。唯讀重載與條件操作未新增快照。正式 main／WAL source pins 與10模組 code hashes 前後一致；此 Native scope 只初始化兩個實際工作區，不宣告完整 Main startup、人工驗收或 frozen 效能。

另以專用微型受控 SQLite 做15列暖機缺資料 → unknown；只改此 fixture 的同日 close 後，個股舊 pin 與名單 readonly 重載皆拒絕，unknown 中文引導且快照 inventory 未變；明示更新後新 manifest 可恢復，未碰正式來源。窗口由本包開啟並關閉，worker count 回零，driver 正常退出。真實資料與受控情境各自留圖，非模型或自然成熟證據。

診斷收據保留：新表格 AccessibleText API 已改 Qt 資料角色；Native 初版 QTest.qWait 阻擋 Python worker 的 GIL，thread dump 顯示卡在 SQLite progress callback，改為 QA driver 的10ms短 sleep＋processEvents後重驗，沒有修改產品效能或 frozen 門檻。直接 py_compile 寫入舊 session __pycache 遭本機權限拒絕，改 py_compile 指定本包10個獨立 cfile 通過，未放寬權限或清理舊快取。實看截圖又修 active source page size hints，避免另一保存來源頁撐高每日表格；有效研究 context 的狀態文案改回每日研究來源。

收據：`output/qa/ux04_ux05_snapshot_flow_20261005/native_140743/receipt.json`；同目錄7張 Native PNG；`output/qa/ux04_ux05_snapshot_flow_20261005/affected_final.xml`、`workbench.xml`、`mypy_final.txt`、`update_validator.txt`、`commit_after.json`。正式DB未寫、未 ML／全市場／WindowsTask／大DB複製／清理／push，未知 paper 與還原映射保留。完整 UX18／19、stage2／3與既有 Backtest18.62%／20%門檻仍未關閉。

## 最新延伸：UX19 隔離研究快照生產／讀取閉環

基線 `3a975e3cb487577a13487b704de8cdefabd956d9`。本包明確授權開發並以小型既有readonly來源在隔離output實跑producer，不沿用前包「不producer」的scope-out阻擋新授權。原plan第8.7的既有特徵、manifest驗證與最後原子切換映射到UX18的 `DailyMarketFeatureSnapshotService`、既有StockReport查詢／DTO與research canonical JSON；不建立第二個正式Rule／Evidence writer，不部署Windows排程或修改正式market／evidence DB。

`SQLiteDailyMarketSnapshotSource` 在同一query-only SQLite read transaction中沿用既有價格／technical查詢，明示股票每股最多120列；schema最低必要欄位不合即拒。source scope綁resolved DB path、實讀schema identity及股票，input hash綁完整有限DTO；main／WAL身份在讀取與發布前驗穩定，SHM索引metadata不作immutable內容資格。可得時間／官方日曆未知仍可作current-observed研究，不偽造historical available-at。

`DailyMarketSnapshotProducer` 明示cohort最多16股，僅投影既存close／MA20／MA60；每股輸入、來源與版本未變就重用核驗過的artifact，失效範圍才project。immutable object／manifest以canonical JSON內容hash命名，manifest保存aware臺北cutoff／decision date、cohort ID與明示分母identity、來源refs／schema／input／snapshot／artifact pin、feature／existing-observation版本、counts／完整性／缺件及publish time。producer 本包僅發布明示 cohort 完整版本，來源缺件即具名停止；reader 另可核驗具名 partial research。完整性只指declared cohort artifact presence，不授全市場、feature、PIT或模型資格。

candidate manifest／每股artifact先由同一reader核驗，latest pointer最後atomic replace；writer互斥、重複觸發／無更新保持穩定身份。失敗保留前次可讀版本，沒有半份artifact冒充latest。容量實寫前重驗，沿用200GiB reserve及有界新增／暫存／累積保留預算；不足具名退出，不降reserve或自動清理。精簡artifact不保存完整raw歷史。

`DailyMarketSnapshotRepository.load_latest()` 每次核驗pointer→manifest→全部declared artifact，並重讀pointer拒讀取期間換版；沒有reader cache跳過驗證。錯stock／date／scope／schema／版本／hash／policy均拒絕，snapshot stable identity重算；`load_manifest()`可按hash唯讀核驗candidate／舊版本。StockReport新增明示snapshot root／cohort opt-in，實際既有read_report以當前有限來源hash核對後讀已發布snapshot；失效或錯來源保留unknown／具名error，不fallback成假stored-success。預設live path維持原行為。

操作與排錯見[Manual UX19](../07_guides/APPLICATION_MANUAL.md#2026-10-05-ux19-隔離研究快照生產與讀回)。本包最小close／MA研究閉環不等整個UX18／19：其他feature／method／選股融合、全母體producer、正式排程、growth／長期reserve治理及自然PIT／ML資格仍分列待辦；Backtest18.62%／20%未達保持原門檻，未作效能微調。下列歷史收據保留其原版本。

### UX19 真實兩股唯讀閉環收據

以正式 D `twstock.db` 的2382／1477，在隔離 `output/qa/ux19_snapshot_loop_20261005/real_store_063021` 發布；cutoff為 `2026-10-05T21:30:21+08:00`。main為4,052,123,648 bytes，WAL為0 bytes；兩跑前後 size／mtime_ns／inode／device pins一致，沒有複製或全庫hash。實跑收據為同目錄上層 `real_loop_063021.json`，只作本地可讀證據，不宣稱跨環境可讀。

首次 `published_complete`、重投影兩股；相同輸入再跑為 `unchanged`、重用兩股、重投影0股、新增0 bytes，檔案inventory與hash完全相同。manifest SHA256 `f458a73deeecf6ff727d66c11a79fa7be5072c9fc13045f0340ead311079a1da`，stable identity `8f92208e9169251bc33b34694665d4a153affcef51b891117b377d6808439048`，兩跑一致。新增immutable bytes7,647，連latest保留7,785 bytes；沒有長期storage／全市場容量合格的外推。

實跑前當次C free236,507,041,792、D free294,142,619,648 bytes。producer在immutable寫入前與pointer切換前各重測；切換前C free236,507,029,504、reserve214,748,364,800、required214,765,142,016 bytes，within_budget=true。固定邊界為16股／120列、artifact64KiB／manifest1MiB／pointer4KiB、每run新增與暫存各8MiB、保留64MiB及最多4096項；不足停止，不清理。這是當次容量觀測，不沿用先前自然ML容量。

兩次既有StockReport `read_report("2382")` 都為verified發布讀回：收盤331.0低於MA20 338.07499999999993、高於MA60 330.8749999999999，原值按Decimal比較，不重算均線或排名。兩股資料日10-05、必要MA暖機觀測60筆；仍僅 current-observed research-only，official availability／calendar unknown，PIT=false，非歷史可得時間、公式producer重算等價或模型資格。約1.30秒的兩次CLI操作時間不是Frozen效能基線或Backtest gate重測。

半途寫入失敗證據限於受控故障注入與Windows原子提交邊界；不宣稱硬體斷電、其他OS或全母體部署驗收。初版integration有missing_stocks契約／未定義clock helper失敗，修正後consumer四項通過；初版CLI隔離測試fixture誤放在允許output內已修正，失敗收據保留。


### UX19 最終工程驗證

凍結產品版本後重新綁定6個執行模組raw SHA256，最終兩跑前後code_stable=true；前一 `real_loop_062647.json` 留作首版成功收據，最終依 `real_loop_063021.json`。定向pytest **106 passed／4.80秒**，涵蓋producer8、reader18、實際consumer4及既有feature／StockReport服務／provider契約；使用fresh `final_1334` basetemp與JUnit收據，不是全套回歸。772 source files mypy、9檔py_compile、精度與look-ahead guard及git diff check通過。

故障／revision驗證包含同輸入no-op、單股修訂只投影失效股且artifact／identity與fresh full等價、候選寫入中斷或來源guard拒絕保留old latest、容量不足／壞pointer／未來cutoff／DTO邊界、同root第二instance busy、consumer同日來源修訂／錯date／cohort與reader schema／hash／stock拒絕。busy測試為同process獨立instance重入，不外推跨process死鎖／崩潰或硬體斷電完整驗收。

19個指定產品／測試／文件進本地commit，原plan append-only與raw／Git blob／status核驗收據保存於本包output。UI code blob相對3a975e3未變，沿用該版UI85／validator25+4skip gate；本包不重跑UI或Native。沒有正式資料庫寫入、全市場producer、ML訓練、效能微調、清理或push；paper與還原映射未動。

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
