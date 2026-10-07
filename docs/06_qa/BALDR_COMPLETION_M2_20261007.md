# Baldr M2 施工與驗證紀錄

本輪沿用[單一產品補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)的 P01／P02／P04 與使用者回饋，持續由 Luna Max 葉片實作、中央審核。本文件保存工程證據；M2、完整選股器、Native 真人與原計畫全部工作包仍未完成。

## 已完成的局部驗證

| 項目 | 證據與範圍 | 限制 |
|---|---|---|
| 全母體產製與既有父層 | 中央隔離回歸 `31 passed in 226.73s`；raw：`output/qa/baldr_completion_m2_20261007/producer_parent_root_1.log`。包含 17／257／1,000 檔、全排除、取消、跨新程序續跑、來源修訂拒絕與原 parent 測試。 | 這次程序載入的是長路徑整合前的版本；後續 I/O 修改須另重驗，不能引用此結果證明新路徑完成。 |
| 技術來源與封裝 | 中央 `52 passed in 6.73s`；raw：`output/qa/baldr_completion_m2_20261007/kernel_source_root_1.log`。17 項來源測試加 35 項封裝／版本測試，包含兩份 kernel 原件 SHA、缺件／篡改拒絕與合成 frozen 根。 | 合成 frozen 根只證明契約，未建置或驗證包含此 adapter 的新 exe。日期無效列的 SQL 邊界另在補強，須再驗。 |
| 受控保存 preflight | 明示 `ResearchCaptureWriteScope` 的來源不符、範圍外輸出、沒有 scope 的外部輸出皆拒絕，且未建立設定輸出根。 | 實際 17 股正常外部保存最初失敗；不能由拒絕測試通過推導正常流程可用。 |
| 長路徑與受控根整合完成 | 中央 `managed_scope_root_7.log`：4 passed；後續 `managed_engine_root_1.log`：80 passed、2 skipped，包含原 capture／parent、managed scope 與長路徑閉環。17 股兩批實際保存、全域查詢及新程序唯讀重開通過，來源 DB bytes／mtime 保持。 | 兩項 skip 為 Windows 一般 symlink 建立權限限制；hardlink 替換檢查實際執行。這是底層工程完成，正常 UI 產製／完整 query 收藏與新 exe 未因此完成。 |
| 技術來源日期 guard 後重驗 | 中央 `kernel_source_root_2.log`：59 passed in 6.46s，包含來源24項及封裝／版本35項；targeted mypy／py_compile 通過。 | SQL 未知日期、日線 cutoff 及合成 frozen 契約皆受驗；仍不是正常 UI、保存 v4 或實際 exe 的證據。 |
| 技術來源時區 guard 最終重驗 | 中央 `kernel_source_root_4.log`：61 passed in 6.50s，來源26項及封裝／版本35項。 | aware timestamp 先換台北日期再核 cutoff；naive date 維持本地日期。先前誤用不存在測試檔的 collection 失敗保存在 `kernel_source_root_3.log`，未算通過。實際新 exe 尚待建置。 |

## 正常研究保存的長路徑缺陷

原 capture writer 只允許 QA／Temp，無法支撐正常設定輸出根。新增明示 scope，派生 `{configured_output_root}/research_snapshots`，只允許其嚴格子路徑。來源 DB 以 query-only 開啟核對，DB／WAL 不得位於輸出根；沒有 scope 時原隔離限制保留。唯讀 writer 可重開既有保存來源，但必須在序列化、mkdir 或 lock 前拒絕寫入。

中央整合案例以合成 SQLite 產製 17 股兩個 batch，輸出在 repository 的 `output/ms<唯一識別碼>/research_snapshots`，刻意位於 QA／Temp 之外。沒有放寬 verifier，也沒有縮短測試根來掩蓋真實路徑問題：

1. `managed_scope_root_1.log`：快照已發布，capture 的最終 `capture.json` 路徑達 275 字元，Windows 寫入／讀回失敗。
2. `managed_scope_root_2.log`：capture I/O 修正後，父層容量掃描仍對深層普通路徑呼叫 stat。
3. `managed_scope_root_3.log`～`managed_scope_root_5_diagnostic.log`：只有在短 root 先轉 I/O 路徑仍不夠，深層路徑需要逐層轉換。FileNotFoundError 的實際呼叫位置另保留在各具名 Temp fixture 的 `io_errors.json`。
4. `managed_scope_root_6.log`：父層完成後，聚合 run 的段檔 temporary filename 再度超出 Win32 路徑限制。
5. 修正逐層 OS I/O 邊界及短 temporary filename 後，`managed_scope_root_7.log` 的實際產製／新程序重開全過；整合提交前另完成 `managed_engine_root_1.log` 的 80 passed、2 skipped。原失敗沒有刪除或改寫。

上述 raw 都位於 `output/qa/baldr_completion_m2_20261007/`。失敗研究輸出、partial、原始來源與診斷保留。擴展路徑前綴僅用於 OS I/O，不寫入保存 identity、manifest 或使用者設定；容量、連結、來源 hash、取消與原子發布的守衛均須維持。

## H20 下鑽查核

新測試走保存來源、公開 cohort reader、股票選取、exact cohort 再驗、MainWindow、實際報告 service、TaskWorker 與公開 H20 reader。使用合成研究來源，模型 contract port 的隔離邊界另明示，沒有訓練或偽造完成的 fit 收據；因此不稱 canonical 模型全鏈驗收，也不取代使用者原 2382 的 Native 驗收。

一次觀察 wrapper 的 `**kwargs` 改變 signature，導致 TaskWorker 注入取消參數再轉送給原函式。加上 `functools.wraps` 後該問題消失，**已撤回 production 缺陷判定**；沒有因此修改正式 reader API。

最終 `tests/test_ui_qt_h20_saved_source_journey.py`：2 passed in 246.84s，原 log `C:/t/h20journey_20261007_final2.log`。成功路徑決策日 10/6、來源日 10/5、特徵日 10/2，各自核對 report／context／H20 evidence；摘要顯示 +12.34% 保存預測、未扣成本及自然結果尚未成熟。詳細 label 位於預設折疊的來源區，驗可見性的是首屏五問結論及狀態 panel。

報告 service 失敗時，H20 reader 目前不會啟動，原因在狀態／限制可見；這項測試只證明現有失敗行為，不能宣稱有效 H20 可獨立於一般報告失敗呈現。一般價格列不混入保存 H20 context 是既有來源隔離政策，不能由 `price_points=()` 判定 H20 原件不存在。使用者原 2382 畫面與開啟版本仍待核對。

## 新技術來源的日期與計算契約

adapter 只唯讀 `daily_prices`，最多保留 120 列原始 OHLCV，核對主檔／WAL／schema 與逐列原始 token 指紋。沒有來源 lineage 的舊 `technical_indicators` 不借用。既有純記憶體因果 kernel 的浮點只在隔離分析邊界，輸入規則前轉為 Decimal；不修改程序 OUTPUT_ROOT，不初始化資料庫或額外 logger。

SQL 使用與 Python 相同的完整日期解析器；NULL、空值、非法及部分非法日期列優先納入有界結果，不能因篩掉壞列而跨過未知日期計算。帶時區的日期／時間先換算台北日期，無時區日期沿原本地日期；合法 cutoff 之後日期排除。未知日期使 observation prefix 不可核、規則結果為 unknown，raw token 與來源 bytes／pin 保留。

原日期篩選只比 day，09:00 cutoff 也可能拿到同日收盤資料。現在新 adapter 明確採日線收盤研究契約：台北 16:00 前，在資料庫解析／開啟／計算前拒絕；16:00 及等值 UTC 有回歸。`daily-close-research-cutoff.v1` 納入原窗口指紋、source identity 與輸出。16:00 是這項研究 API 的門檻，**不是官方收盤或來源可得時間證據**；`source_available_at=None`／availability unknown 保留，未授 PIT、回測、訓練或正式 Advice 資格。

固定建置 metadata 新增 `technical_indicators.py` 與 `indicator_kernels.py` 的 resource SHA，spec 隨包保存這兩份計算原件。frozen adapter 必須核 `_MEIPASS`、有界 metadata、release／clean build identity、成對 resource keys 與 bytes SHA；缺件或篡改拒絕。source 模式讀本身的原件。合成 frozen fixture 不取代後續真候選同版比較。

## 仍須完成

受控根的底層產製→完整 run→全域查詢→新程序重開已在具名隔離案例通過；接著仍須正常 UI 的產製入口、完整 query 的收藏／比較／返回，以及新 technical 保存版本。原 v2／v3 產物不可事後補欄或套新公式。新固定來源技術engine候選已完成下節真Python／exe同版probe；正常UI全流程candidate仍須另驗。既有候選與正式exe保留。

目前未讀寫正式市場 DB、未更動私人模型／持倉、未觸發 Task、未交易，也未 push／更新 main／取代原 exe。真人驗收入口沿[推薦回饋 QA](BALDR_RECOMMENDATION_HUMAN_FEEDBACK_20261007.md)；目前不要求使用者重複驗尚未完成的 M2 流程。

## 固定來源技術 adapter 的實際 exe 同版比較

固定 `e5026b3a5afa2501da1f2d5956211d74130898e3` 新候選位於 `dist/candidate_e5026b3a5afa_abeea6de/baldr/baldr.exe`，52,502,536 bytes，SHA-256 `f6bbfb316e3db53787171722d49f369346d3827534c3e54d3021a3f1e9b879ef`。Python 使用同 commit archive，exe 使用實際 frozen kernel bytes與metadata；同一合成日線SQLite的65列窗口、排除未來列、計算身份及完整JSON逐值一致，來源SHA／mtime保持、網路禁止。收據 `output/qa/baldr_completion_m2_20261007/technical_same_version_b7fa6b8e/comparison.json`，SHA-256 `215633b406a3ace1d70ea7834a1d4de389521257ac19412318d497da3e755b70`。

建置本身與建置收據已成功，CLI最後輸出中文時曾因host cp1252出UnicodeEncodeError；沒有重新build或覆寫候選，先核原receipt／exe hash再執行上述真同版比較。build_windows另補UTF-8輸出，原失敗保留。這份engine probe不證H20獨立panel、正常UI產製、v4保存或Native真人可用；各候選及原exe保留，未更新active delivery。

## 共享唯讀日線交易快照

中央 `technical_session_root_1.log`：69 passed in 6.95s（原技術來源26、共享session8、打包／版本35），targeted mypy／py_compile通過。17股16+1批共用一條query-only connection、一個BEGIN及一次schema alias map；load_batch只累積raw rows、不回傳窗口。只有finish關閉read交易／connection、核main+WAL與共用計算版本、完成全部股後再核source pin及取消，才一次交付immutable tuple。來源update／rollback／schema WAL變動均拒絕完成，duplicate／原exception／late cancel均清理connection；clock核原pin與台北日期。

舊單股public loader維持原輸出欄位／source identity／計算身份，改包裝一股session；新v4 clock十一欄只給新session與保存版本，不寫入舊單股to_dict。沒有以legacy technical_indicators schema冒充日線來源。v4快照semantic verifier仍有volume結果任意改unknown且重hash可被接受的紅測，尚在修正，不能把session通過視為v4保存或完整UI完成。

另用同一合成DB與相同實體kernel bytes，獨立載入變更前preimage（SHA `130713c5e0a2a636bb942757a6ca77d60ee8f5d75f8dfe005258187eeca022a8`）及新API，完整to_dict逐值相同，shared session結果亦同，DB SHA／mtime不變。收據 `output/qa/baldr_completion_m2_20261007/technical_same_version_b7fa6b8e/session_preimage_compat.json`。初次直接拿工作樹對固定archive比失敗：technical_indicators.py工作樹為CRLF、archive為LF，kernel原bytes SHA不同使calc identity不同；換行正規化後內容一致。沒有用正規化SHA放寬production guard，亦未冒稱那次直接比較通過；該失敗probe `technical_session_compat_probe.py` 及原工具輸出保留。固定e5026b3a Python／exe使用同archive原bytes的具名比較仍成立。


## v4 技術快照語義與計算來源補強

中央 `v4_snapshot_root_3.log`：65 passed in 7.72s，包含原 source 26、共享 session 8、方法契約 4、v4 快照 27。先前把已知量比任意改成 unknown 並重算快照 SHA 的紅測已修正：讀回用保存的最近兩日事實與原量能列重驗完整五項規則結果，不能只核 JSON hash。方法版本、參數、交叉狀態、暖機不足、量比及未知日期均保留 fail-closed。

新 v4 calculation 同時封存兩份 kernel 原 bytes SHA、NumPy／pandas／TA-Lib 版本及固定參數，整份 binding 必須對上原 calculation identity。保存讀回不重讀目前 kernel 或套件；重 hash 外層快照仍不能任意更換原 binding。新欄位只存在記憶體來源窗口及 v4 保存版，舊 public to_dict 欄位保持。中央 targeted mypy 四個來源／session／v4 模組與 changed Python 語法檢查通過。

同實體 kernel／同既有合成 DB 的變更前 preimage 比較重驗通過，舊 public／新 public／共享 session 完整 to_dict 相同，DB SHA／mtime 不變、網路禁止。新收據 `output/qa/baldr_completion_m2_20261007/technical_same_version_b7fa6b8e/session_binding_preimage_compat.json`，raw `technical_binding_preimage_root_1.log`。初次直接執行 script 因缺 repo 匯入路徑失敗，改 runpy 保留匯入路徑；未將該失敗視為來源差異。另 `v4_snapshot_root_2.log` 的 65 errors 是短 basetemp 父目錄未建立，建立另一獨立父目錄後才有上述 65 passed，原失敗保留。

這批完成的是 immutable projection 與來源契約；v4 repository／producer／parent、正常 UI 全母體五規則與新 candidate 尚待整合。H20 獨立 reader／重新核驗面板的旅程仍有失敗正在定位，不能援引本節宣稱使用者 2382 畫面已可用。


## 完整保存母體瀏覽與真正個股下鑽

中央 `ui_universe_root_7.log`：88 passed in 75.52s，包含既有 Update workbench 與三個完整母體案例；`update_root_7.log`：25 passed、0 failed、4 skipped（受保護寫入案例）；`ui_mypy_root_3.log`：868 source files、0 error，另 changed Python py_compile 通過。新增頁讀取既有完整 run，完整納入257／排除1的原保存來源先全域 AND／OR 篩選排序，再取第六頁8列；實際 DailyMarketResearchView 發出原 child 的 stockResearchRequested，返回保留原母體、頁碼、查詢、選取及完整分母。明示取消按鈕與等待期間 query 改變都不開啟舊結果。

原直接頁面測試未涵蓋 DailyMarketResearchView 補充核驗 worker；加入真路由後 `ui_universe_root_4.log` 出現開啟事件0次。原因是接受 child 時啟動來源核驗，立即開啟請求被 busy guard 拒絕。現在保留有來源身份的待開啟請求，worker 結束後重核來源／query，再開原保存 child；取消、切來源或關閉清除請求。原失敗保留。`ui_universe_root_2.log` 的隔離 root 錯配亦保留，改對齊 child TEMP／TMP 與 basetemp，未放寬原 guard。

800px offscreen 截圖 `universe_layout_800_fonts.png` 使用既有中文 font bootstrap，控制項文字可讀且按鈕達 sizeHint；首次未載入字型的 `universe_layout_800.png` 出現方框，不能作中文字形驗收。此頁目前仍是 v2／v3 三個既有條件：價高於 MA20／MA60／布林上軌30；沒有以它宣稱新 v4 五規則、正常 UI 產製、完整 query 收藏／比較或真 N 已完成，也不代表新 candidate／Native 真人通過。

回滾範圍：新增 daily_market_universe_selection、daily_market_universe_view 及其測試；修改 daily_market_research_view 接線；文件只追加本輪具名內容。整合提交可用 git revert 該提交恢復本輪，先保存後續未提交變更；不還原其他聊天檔案、不刪原保存來源。撤回後新完整母體瀏覽入口不可用，原單批來源保持；不改正式 DB／Task／模型／原 exe。

## v4 repository／batch producer／parent 中央整合

`v4_parent_repository_root_1.log`：92 passed、1 skipped in 72.48s；包含 source 26、read session 8、method 4、snapshot 27、repository／producer 24與 parent 4。Windows symlink 權限不足跳過一例，hardlink 拒絕仍實際執行。真 SQLite→一次 finish→16+1 stock batch→immutable parent→刪除測試自有 synthetic DB後新程序唯讀重開，並涵蓋取消續跑、錯 clock／cohort／date、語義與 bytes tamper、長路徑和舊新 schema 隔離。這只證有界底層保存鏈；正常 orchestration、v4 query 與完整市場聚合尚在下一包，不能把256股上限改稱 M2 全市場完成。


### v4 保存底層 API 審核封存

中央另執行 repository／batch producer／parent 三模組 mypy 與六個 changed Python py_compile，皆通過。batch API 接 finish 後窗口，不開來源 DB；保存於獨立 daily_market_technical_v4 store，manifest 最後發布並完整讀回。read_exact 必須給原 manifest 路徑，可核外部 bytes／cohort／clock／method／日期 pins。單股256KiB、artifact batch4MiB、manifest4MiB、retention64MiB；普通寫入僅 QA／Temp，正常根必須明示 ResearchCaptureWriteScope。Windows extended path 僅用於 I/O，保存身份仍 canonical。

parent API 接全部完成窗口建 immutable plan，最多256納入／256排除、16股一批；start／record_verified_batch／mark_terminal／resume／complete 產生 append-only receipts。read 需原 plan identity、receipt identity 及 receipt bytes SHA，重驗 chain、全 child manifest 與逐股保存證據，不開 DB、不選 latest。取消保存 partial／cancelled，不能當完整；只有全 batch 核驗才 complete，全排除／空母體可真零完成。此256上限是有界 child parent 契約，不是市場母體或選股名單上限。正常 orchestration、full-N v4 aggregate 及 UI 尚未封存。

本輪新增三模組與三測試，未修改舊 v2／v3 reader／writer 或資料格式；回滾可 git revert 本輪整合提交，先保護後續修改與新 consumer，相依新功能會不可用。原 artifact／partial／QA 及舊 reader 保留，不刪資料恢復乾淨。批次 scope 是 preflight 驗證，不能描述為每次 OS 寫入皆獨立重驗；後續正常 caller 仍需逐批檢查範圍。


## 正常 v4 parent 產製 caller 中央整合

`parent_v4_orchestration_root_1.log`：20 passed in 86.69s，涵蓋實際 batch producer、parent writer及新增正常caller；root targeted mypy兩檔及py_compile通過。API `produce_daily_market_technical_parent_v4` 明示來源DB、完整bounded cohort、aware cutoff、child／parent roots、scope及取消；單一read session載全部納入，只finish後窗口建plan，真batch writer→verified parent record→全部完成才complete。取消在finish之前沒有plan／receipt；之後明示取消狀態，partial／失敗及原child不刪。17股16+1保存後明示原receipt續跑，重核同plan／clock／cohort／method與可選外部rawSHA，不尋latest；新程序刪除測試自有合成DB後仍可唯讀原完整收據。

每批前、child返回後記parent前及complete前重驗main／WAL source pin、scope與兩個root；合成DB在child保存後改變時保留verified child、保存failed receipt、阻止complete。外部resume SHA若未提供，計算exact原receipt rawSHA只供讀取競態守衛，不冒充獨立外部pin證據。另一來源clock續跑拒絕，原收據不改；全排除真零納入完成。測試短root由命令TEMP／TMP指定，版本化fixture沿tempfile.gettempdir，不硬寫主機C:/t。

新增 parent producer／測試兩檔，舊reader／writer未修改；回滾用git revert這輪caller提交，先保護後續consumer／未提交修改，原artifact與QA不刪。此caller仍至多256納入，不是全市場終點；完整N獨立store／aggregate/query、正常UI產製與candidate尚在下一包，M2未完成。
