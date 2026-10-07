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


## H20 獨立摘要與完整操作旅程中央封存

`h20_universe_ui_root_1.log`：96 passed in 60.61s，包含必備workbench85、完整母體3、H20 journey／panel／既有cohort integration8。`h20_update_root_1.log`：25 passed、0 failed、4 protected skips；`h20_global_mypy_root_1.log`：870 source files、0 error；五個changed Python py_compile通過。H20 journey五個案例涵蓋真公開保存來源→cohort→MainWindow選取→報告TaskWorker→公開product reader；成功+12.34%／10/6預測／10/5來源／10/2特徵，報告失敗仍獨立顯示、切來源晚到拒收、明示原來源重新核驗與pointer變動保持原清單／排序／選取。panel另驗父workspace暫時隱藏時仍可保留retry狀態。模型contract port是明示合成且未fit、未推論的測試邊界；不稱canonical模型品質或原真人2382通過。

控制流程修正：保存H20隨activeContextChanged獨立讀取，不再等reportLoaded成功；讀回cache只供相同context／reference使用。首屏新「保存的個人 H20 研究預測」位於整個個股研究報告上方，顯原gross與三個日期、實際結果尚無已核驗結果，失敗仍有原因／診斷與明示「重新核驗保存預測」。不同model／manifest／capture／stock／配置、取消、切來源或關閉的舊回呼不覆寫。重新核驗不切latest；返回重讀若pointer改變先拒絕，再保留原名單與選取，不先換表格才報錯。H20研究收藏仍未接，不套用每日規則收藏。

原慢測原因已撤回production reader／Qt執行緒缺陷判定：同一保存fixture直接公開reader約1s、TaskWorker0.609s，最小Main handler的publish／UI setter均在GUI thread；完整pytest原QTest.qWait pump使cohort123s、product75s，`h20_report_failure_thread_trace_run_escalated_20261007.log`失敗201.18s。重用同一fixture，僅改event pump為processEvents後time.sleep(0.01)讓出Python執行緒，完整route3.78s；新fixture單測3.39s、葉片完整8例9.43s。原失敗、JSONL及fair-pump probe保留；未用加timeout或放寬source guard換通過。stack dump檔為0 bytes因修正後未達15s觸發，不當作堆疊證據。完整母體測試同樣讓出執行緒後仍由上述中央96例重驗。

保存來源fixture偽TWStockConfig先前缺既有`__dataclass_fields__`介面，改為真正dataclass/default_factory隔離root，未修改production輸出守衛。各Windows strict resolve／longpath失敗root、原4failed1passed等輸出均保留，不把sandbox缺件當真人設定缺失。原共享收據中「一般報告失敗H20不啟動」是修正前行為，本節為目前dev工程狀態；新candidate／同版比較／Native及三真策略仍未完成。

本輪修改main／stock_research_workspace、新增H20 journey／panel測試、調整完整母體測試pump；回滾用git revert本輪整合提交，先保護後續修改，撤回後保存H20重新受一般報告成功限制。main原其他errorhook與所有資料／模型／原exe／Task保持。沒有正式DB讀寫、模型訓練、啟用、交易或發布。


### 新候選同版與保存 H20 實際讀回（2026-10-07）

候選版本 `2026.10.06+c589bc71e8f1`，固定 commit `c589bc71e8f19d947ad414675cb140432d75f90c`，exe `dist/candidate_c589bc71e8f1_8e967bc9/baldr/baldr.exe`，SHA-256 `3806b87099475e20a136062ba406aa78263fb05be064d79e632fdd65f97ef801`。原 exe／正式資料／私人設定／Task 未替換。共用設定與四用途／模型／H20呈現的固定 archive Python／exe 比較收據：`output/qa/baldr_same_version_c589bc71e8f1_fb047fce/same_version_receipt.json`，狀態 passed_isolated_fixture；其中 H20 呈現案例不是 canonical reader。

另外重用原保留的隔離2382 source／activation／capture／manifest，以真正 public source reader、MainWindow methods 與 TaskWorker 走「原保存名單→2382→一般報告失敗→獨立 H20 摘要→重新核驗」；固定 archive Python 與 exe 結果逐值相等，收據 `output/qa/h20_candidate_saved_source_27b127de/receipt.json`。模型 verifier 仍為明示 synthetic contract，不是原真人模型核驗。首屏實際讀回 +12.34% 與決策10/06、來源10/05、特徵10/02，實際結果保持未核驗；不得把合成數值當真人2382預測。所有 fixture files bytes／size 不變，source DB／WAL 與 immutable artifacts mtime 不變；SQLite readonly 連線只更新 SHM mtime，原 bytes／size 不變，收據明列。先前sandbox拒絕Temp guard、controller編碼與過度嚴格SHM mtime失敗收據均保留，沒有放寬產品守衛。

真人啟動新 helper `output/qa/baldr_completion_m2_20261007/start_h20_feedback_candidate.ps1` 核驗新 exe hash、向 child 提供原官方日曆及明確主機設定 JSON；尚未執行。Native真人2382、三個真策略、窄欄均待實測；H20收藏尚未實作，完整full-N v4新五規則與UI產製等仍在補完中。


### v4 單段固定查詢中央審核（2026-10-07）

新增 `app_module/daily_market_technical_parent_v4_query.py` 使用明示parent root、plan／receipt identity與兩份bytes SHA；真正parent strict reader及v4 repository重新核原child，canonical query可重開，不開原DB、不寫入、不挑latest。固定五規則狀態集合支援AND／OR、股票篩選、Decimal／日期／整數排序，升降序null置尾，股票碼stable tie-break，先篩選排序再分頁；partial的processed／pending和原排除理由保留。明示 `bounded_parent_v4`／`single_parent_segment`／`full_n_aggregation=False`，最多256納入＋256排除，不冒充完整母體。

中央修正兩個審核發現：取消檢查原本在真正child讀取前空跑，現改每批前後合作式檢查；有raw rows但規則unknown原先被混算missing，現missing只計raw_row_count=0，unknown_rule_count／unknown_rule_stock_codes另計唯一股票。固定parent初次strict核驗仍是同步邊界，取消不宣称可在任意單次I/O內搶占。

中央真writer回歸 `8 passed in 118.44s`，raw `output/qa/baldr_completion_m2_20261007/parent_v4_query_root_2.log`，mypy兩檔0、py_compile通過。測試包含17股16+1、兩排除與一股缺raw、Decimal排序／null尾、AND／OR／filter-before-page、fixed partial receipt、新程序且刪除自身合成DB後讀回、tamper／異日期／版本／缺receipt拒絕；另外真reader spy驗第一child讀完取消後第二child不讀，真40列NULLprice股票unknown但missing=0。前輪7 passed與Luna6 passed及失敗QA全保留。Full-N store／producer／aggregate query尚在施工，完整M2／UI產製／query收藏比較／Native未完成。


### v4 真讀回重驗成本與零child修正（2026-10-07）

完整all-excluded parent有complete plan／receipt，但無child、repository_output_root=None；公開reader先前額外重驗時把None建為repository而拋TypeError。修正版保留plan／chain／complete語義，零child明示無root；兩個原empty／all-excluded案例新增公開reader讀回、排除清冊及source bytes不變斷言。parent／正常caller先行回歸9 passed，raw `output/qa/baldr_completion_m2_20261007/parent_v4_zero_child_root_1.log`。

同一已保存17股／2child的cProfile發現public wrapper再次呼已完成的child verifier，且repository把from_json已核immutable snapshot再次to_dict／from_dict做語義重驗。現public wrapper直接回reader.read已核包；snapshot.from_json仍完整from_dict語義／identity核驗，再用immutable payload做canonical回轉比對；repo保留artifact bytes SHA／size、source／method／日期綁定與canonical layout，只去掉同份DTO二次轉換驗證。writer輸入artifact後再次讀檔以防capture期間變動的檢查保留；沒有新增全域可信cache，也不跳過每次重新開啟的真檔核驗。

固定同一parent plan／receipt的公開read profile由13.781s、45,464,235 calls改為1.969s、6,927,994 calls；2child的read_exact呼叫8→4、snapshot語義核驗272→34。原與修正profile分別 `parent_v4_read_profile_17.log/.prof`、`parent_v4_read_profile_17_after.log/.prof`，都位於上述QA目錄。這是同機診斷含cProfile overhead／同時其他QA程序，不能當已達真N產品效能Gate。

最新snapshot／repository／batchproducer／parent／normalcaller／query六套中央回歸 **67 passed／1 skipped，108.28s**，raw `v4_read_validation_root_1.log`；Windows無symlink建立權限skip，硬連結拒絕實際通過；targeted mypy4檔0、py_compile4檔通過。原錯誤raw與較早不同import版本的fullstore pytest保留；當前fullstore／producer／query／catalog仍在中央驗證與補完。Native待使用者四項，M2／M3與P00–P14未完成。

### full-N 中央整合首輪與審核待修（2026-10-07）

中央 pytest session 4314 已回 terminal exit 1：store／producer 十項 **9 passed／1 failed，667.83s**，隔離 basetemp `C:/t/fullv4-root-20261007-n` 保留。唯一失敗是 `test_full_plan_rejects_changed_method_contract_and_json_float_or_duplicate_keys`：實際拒絕浮點值，exception.code=`technical_universe_v4_float_forbidden`，但 exception 文字是 `1.5`，測試 regex `float_forbidden` 未匹配。交原 leaf owner 改用具名 code 斷言，不放寬 float 拒絕；尚未重驗通過。此程序載入的是歷史 receipt graph 修正前的 store，pytest 結束時工作檔已更新，trace 顯示的工作檔行文不能當同版證據；也不以此首輪結果證明新歷史 prefix／CAS 已通過。

中央要求新增取消後續跑到 complete 仍可讀舊 receipt 的原 counts／refs，以及只移走後續 segment 的合成 parent 時，舊 prefix 仍可讀、complete pin 具名拒絕。版本 catalog 另須用 metadata bytes SHA 偵測同長度替換／mtime 還原造成的 stale cursor，語義解析只做 limit+1 列；全 inventory 掃描的100000 entries／64MiB成本需明示。這些為審核待修，不是完成結論。

中央新增 `daily_market_technical_universe_v4_stock.py`：先重核原 query 當頁，再沿明示 store／segment parent／child manifest pins 返回 snapshot 與原 query，不讀最新版本、不開行情 DB。獨立兩股真 producer／store／query 測試在刪除自身合成 DB 後仍讀回2382原40列與五規則，非當頁9999及 immediate cancel拒絕，**1 passed in 4.60s**；隔離根 `C:/t/stock-v4-root-20261007-b`。首輪 fixture scope 缺 source_database 參數的失敗留在 `...-a`，未放寬product。跨257分段、child缺件／tamper及UI連續操作仍待後續新版本驗證。

後續個股測試加入新程序讀回同 query／snapshot identity、manifest缺件與bytes改動拒絕並恢復，**1 passed in 8.46s**（`...-d`）。前輪 `...-c` 在測試直接用未轉換長路徑的 Path.read_bytes 失敗，保留；測試改用既有 to_internal_io_path，product守衛未更動。中央再整合 catalog／stock **5 passed in 17.67s**，session66845 terminal exit0，basetemp `C:/t/catalog-stock-root-20261007-a`；targeted mypy3檔0，stock兩檔py_compile通過。

catalog每次明示100000 entries／64MiB metadata inventory掃描，plan／receipt raw bytes SHA納入cursor fingerprint；metadata逐列解析至limit+1，損壞來源保留具名診斷。四項真producer/store案例覆蓋空清單／empty cohort區分、complete／cancelled、長路徑、刪自身DB後strict重開與新程序、同長度改寫還原mtime仍stale、超預算不冒稱全量。此catalog不是257效能或全N UI通過；五規則view已分工施工，入口／比較／收藏及其他原計畫包仍未完成。

中央新增 `DailyMarketTechnicalStockV4View` 個股詳情元件，顯示五規則三態、決策／截止／特徵日期、支持／反證／未知原因及可得時間未知限制，返回原 query signal 不重建條件。真兩股保存來源 offscreen Qt 展示與返回 **1 passed in 8.36s**（session68461 exit0，`C:/t/stock-ui-root-20261007-a`）；該測試同時覆蓋前述新程序／缺件／tamper。workbench **85 passed in 3.64s**，Update validator **25 passed／4 protected skips**，全域 mypy **876 files 0 issues**，元件與測試targeted mypy／py_compile通過。這是元件驗證，不代表每日研究入口已接好、800px像素驗收通過或Native交付；接線與完整旅程仍待驗。

後續每日研究入口已掛五規則view及嚴格個股signal→詳情dialog→原query返回，關機亦合作取消新view工作。中央原sandbox回歸85 passed／3 fixture PermissionError errors保留；C:/t隔離重驗 **88 passed in 56.98s**（session54478 exit0），validator25 passed／4 protected skips，全域mypy877檔0。此回歸含舊完整母體流程，不替代正在執行的新257股五規則Qt旅程；正常產製factory尚未接，query收藏／比較仍未完成。

目前257股固定來源profile（session39338 exit0）建立query17.258s，page含cProfile203.435s、717349037 calls、repository.read_exact199次、snapshot.from_json3079次；`.prof`及exact pins保存在 `output/qa/baldr_completion_m2_20261007/full_v4_query_current.prof`／`full_v4_query_current_pins.json`，probe同目錄。這不是無profile產品延遲。發現parent reader剛read_exact後投影helper又read_exact，中央改僅該同次reader投影使用已核artifact，writer預設capture變動重讀不變；四套回歸session7913仍執行，尚未列通過。後續需同pins重驗成本，不授效能Gate。

上述四套中央回歸session7913其後terminal exit0，**18 passed in 52.23s**，包含真parent／正常producer／query／個股Qt讀回，隔離根 `C:/t/v4-once-read-root-20261007-a`。同保留257股來源的第二profile另存 `profile_full_v4_query_after.py`／`full_v4_query_after_pins.json`，session19963仍live；query.create目前量到7.592s，page尚未完成，不宣告整頁達標。正常產製setup factory已交Luna下一包，完整母體設定、截止與原receipt續跑須明示；收藏／比較、1000／真N與Native仍未驗完。

第二profile session19963其後terminal exit0，同一來源page含cProfile **130.254s**、460537975 calls，repository.read_exact116次、snapshot.from_json1796次；原profile203.435s／199／3079分別保留，兩份pins亦保留。主要剩餘成本在full query為取得全段rows而重建bounded query及再次讀parent，交query owner去除中間查詢，保留lightweight global candidates、原完整pins及逐child取消；新碼尚未驗完，不能授效能Gate。

中央新增每日研究入口真兩股保存來源的signal→詳情→返回驗證，**1 passed in 7.70s**，`C:/t/stock-ui-entry-root-20261007-a`；config外殼只提供隔離output根，資料由真producer／store／query核得，確認正常入口的store根、原query與2382選取保留。新257 Qt背景旅程仍live，這項小型dispatch驗證不能替代其跨分段／取消／stale／窄窗及Native要求。

移除full query中間bounded query後，中央當前碼catalog／stock Qt入口回歸 **5 passed in 16.76s**（session35547 exit0，`C:/t/direct-query-stock-root-20261007-a`），targeted mypy query／stock兩檔0、py_compile通過；新257整頁profile82916及完整query新程序仍待完成。Luna首輪257 Qt session86664為 **1 failed／1 passed，431.56s**，initial全母體strict read已完成，但來源摘要未明示availability unknown／historical PIT false／current-restated用途，屬可見限制說明缺口；補繁中可見說明後須重驗，不能把SHA呈現當限制說明已完整。

第三profile82916已terminal exit0，同來源page含cProfile **88.594s**、318826225 calls，repository.read_exact83次、snapshot.from_json1283次；固定pins與 `.prof` 分別另存 `full_v4_query_direct_pins.json`／`full_v4_query_direct.prof`。三輪203.435→130.254→88.594s僅證明剖析中的結構去重，非無profile延遲或效能Gate完成。

store歷史prefix／graph-head CAS最終凍結版，Luna全檔22439 exit0 **6 passed in 523.65s**，最後加強的257真parent案例39070 exit0 **1 passed in 459.41s**，覆蓋partial與cancelled兩種舊pins遇後續child／parent缺件仍讀原內容、complete具名拒絕，舊pin寫入拒絕且不落新receipt；mypy兩檔／py_compile／diff-check通過。store SHA=`4E45C606F03853929E504537434920A272A55B8966D970E4833F7C292DF19CAC`、test SHA=`23D438A8B829E1DACD0B427CFEFC47799C573E960CB0AAF1CF602B083BE25C05`，中央實檔比對一致；摘要在 `output/qa/fn4/universe_store_final_20261007/validation_summary.txt`，原首紅與preimages保留。中央目前producer五项新程序20564仍執行，不以歷史producer結果代替當前store整合。

為保留前三輪profile的原absolute source refs，Luna已將自身58206合成fixture備份至 `output/qa/fn4/fixture_58206_uv4query_wcx8nthv`：307 files／21402462 bytes，原前／後及副本inventory SHA一致，bytes不改、307副本唯讀，origin manifest記錄原root。已授權停止該agent自己的obsolete58206／95604測試，須保留中止terminal，不計pass；當前完整query9924保留。這不是正式資料備份或清理，其他來源不動。

中央 producer session20564 已 terminal exit0，當前 store／parent reader 整合 **5 passed in 95.47s**，隔離根 `C:/t/full-producer-current-root-20261007-a`；取代上述仍執行狀態，不取代尚未完成的全 N UI／查詢與效能 Gate。

保存研究比較 reader 新增於 `app_module/daily_market_technical_universe_v4_comparison.py`。各欄保留原查詢與完整來源 pins，逐原頁公開 strict reader 重開，只保留所選 rows；明示混合 cutoff／方法／來源時鐘，不計算交易或績效、不授 historical PIT。中央真兩股 producer 保存 fixture 移除自建行情 DB 後，驗證兩個原頁比較、五規則、原查詢保留、重複欄／跨頁錯選／取消拒絕，以及 manifest bytes 篡改拒絕。與個股／Qt 原來源返回同一測試 **1 passed in 8.29s**，session8537 exit0，隔離根 `C:/t/comparison-stock-root-20261007-c`；comparison mypy 1 file 0、兩檔 py_compile 通過。前兩次 sandbox 原生路徑 PermissionError setup／scope 失敗保留，不以其結果判定產品功能通過。此為 reader 完成證據，尚未有比較 UI、收藏比較或完整母體效能驗收。

正常 TWStockConfig 每日研究入口已注入明示產製 factory；隔離讀取用設定外殼仍不提供產製能力。中央 session1863 exit0：必要更新工作台、factory、真保存個股比較三檔 102 passed in 15.06s（C:/t/technical-factory-entry-root-20261007-a）；全域 mypy 879 source files 0、shared entry py_compile 通過。更新頁 validator sandbox 首次 21通過／3失敗／4跳過（原生路徑 PermissionError），失敗報告另存 output/qa/fn4/update_tab_factory_entry_sandbox_failure_20261007.md；隔離非sandbox重驗25通過／0失敗／4保護性跳過。factory 正常入口構造專項仍待owner補驗；resume factory在GUI同步strict read可能昂貴，已列改進，不能宣告完整N操作與回應性完成。

中央比較呈現 widget（daily_market_technical_comparison_v4_view.py）以原保存列並排五規則／日期／版本，顯示未知可得時間與口徑差異，原欄 query 返回 signal 不換最新。真兩股保存來源＋Qt 呈現／第二欄返回，session2892 exit0：1 passed in 10.43s，C:/t/comparison-view-root-20261007-a；全域 mypy880檔0、py_compile通過。此widget尚未接主入口選取比較，不能宣告比較完整旅程完成。factory owner正常TWStockConfig入口17 passed in3.87s；小型2股母體續跑strict讀cancelled0.032s／complete0.110s，不能支持全N回應性，已安排兩階段背景核驗。全query9924首輪terminal1：7passed／1failed804.50s，sort fixture實有兩筆null，原test僅預估一筆；owner保留首紅log，只重驗修正的真null-tail案例20159，產品query未改。

比較呈現進一步依固定 rule key 對應五規則，不依 DTO tuple 的位置猜測；每格提示沿原保存 cutoff／feature date／版本／支持／反證／未知原因與原query pins。target mypy／compile通過。主入口比較basket交原view owner，待最後257 UI測試terminal後施工，避免改動live來源。factory兩階段契約已審核：GUI收有界設定與metadata未核驗摘要，worker才做canonical scope／selected exact qualification／request；取消至少在exact讀前後檢查，中途合作取消尚待reader接口。

全母體Qt owner session56637最終terminal0：2 passed in414.15s（同一真257保存fixture背景旅程）；保留431.56s來源限制缺口首紅及404.56s OR fixture預估錯誤第二紅，不以本wall time宣告效能Gate。root比較widget選格可讀證據區、固定鍵對應與返回tuple(query,stock)通過真來源session66382：1passed8.84s。最後widget來源全域mypy880檔0、compile通過，validator25通過／4保護跳過；背景比較basket與deferred qualification仍施工。

root正常每日入口已接 comparisonReady→比較dialog；第二欄origin tuple(query,stock)交public restore_origin背景strict讀回，成功恢復原頁及9999選取，shutdown關閉自己dialog。真兩股保存＋正常入口＋必要workbench，session15770 terminal0：86passed11.28s（C:/t/comparison-entry-root-20261007-a），不代替跨257basket旅程。固定原257完整receipt pins非profile單次讀取session93163 terminal0：35.8078331s，counts258declared257inc1exc257processed0pending1missing、頁5stock原碼一致；receipt output/qa/baldr_completion_m2_20261007/full_v4_query_plain_measurement_20261007.json。querySHA6e853049ecbb2d4b1bed753f0d1e716402061c3f069650248e9e9540a80e536e；同時有其他QA，非冷暖30互動或真N效能Gate，結果明示尚不符合可順暢互動，續作結構去重不可跳原guard。

兩階段設定factory中央原碼審核及重驗：GUI fixed metadata+bounded settings，background prepare_request才canonical source/scope+exact receipt和逐欄pins/count/source核對；讀前後取消，不授exact讀中即時取消。root隔離整檔21passed3.19s（C:/t/deferred-setup-root-20261007-a），target兩檔mypy／compile通過。正常view仍待factory union和worker接線，不能以此宣告GUI完整background qualification已啟用。原同步factory保留兼容，不把21項獨立API通過當完整旅程。

中央審查比較跨來源返回發現新的顯示缺口：_show_page無新source_clock payload時可能沿用前一來源payload，在新query SHA旁標為已核驗；已交view owner於live23951 terminal後修正，跨source需清舊payload，同source查詢可保留，不重新讀行情。這是未修缺口，不由同來源返回綠燈關閉。root比較首屏已直接顯示decision cutoff／raw row count，不依hover；session31154 exit0，86passed10.58s（C:/t/comparison-cutoff-root-20261007-a），全域mypy881檔0、compile通過、validator25通過4保護跳過。

P09中央watchlist擴充施工：固定新schema分派decoder、新source namespace与payload identity helper，沿既有add/get/idempotency/revision/COW caller、不另建store；新增typed fullN bookmark state重開，旧context入口具名拒絕新kind。既有每日／排名／personal watchlist三檔16passed5.96s；真保存收藏首輪發現旧WatchlistItem.from_mapping把空股票名稱補成代碼，造成同identity重存conflict，已限定新source保留未知空名，不改旧來源fallback；首紅隔離根C:/t/fulln-watchlist-integration-root-20261007-a保留。當前真保存新收藏與旧兼容整合50834仍待terminal；source targetmypy/compile通過。

50834其後terminal0：17passed18.25s，C:/t/fulln-watchlist-integration-root-20261007-b；真fullN bookmark經既有WatchlistService保存、重存idempotent、重建service重開原query/stock/比較集合，旧每日/排名/personal兼容皆通過。這是isolated legacy JSON route，仍需COW啟用route、新Python程序以及正常UI收藏按鈕旅程，不授私人既存資料寫入或P09完成。

COW新增重驗首輪C:/t/fulln-watchlist-cow-root-20261007-a失敗：原converter拒空stock_name。按P09 readonly migration邊界，不改converter／COW容量或驗證；中央adapter改以stock_code作Watchlist顯示標籤，fullN payload.stock_name仍未知空字串，匹配只接受此固定標籤。撤回前輪限定空名讀法與migration空名例外，原WatchlistItem／JSON migration guard恢復原契約。新64359包括真COW原JSON bytes保留與新Python讀原收藏query，待terminal後記結果。

64359其後terminal0：17passed20.80s，C:/t/fulln-watchlist-cow-root-20261007-b。真合成保存来源→Watchlist JSON→明示COW→原JSON bytes unchanged→新Python程序exact fullN收藏query重開及比較pins通過，source DB已移除，原每日／排名／personal兼容同run通過；target mypy/compile通過。仍未有正常UI收藏／移除復原／錯kind／COW stale revision完整矩陣，不宣告P09完成。

COW收藏移除／復原矩陣中央追加：首輪5915 terminal1（1failed16passed13.00s）指出restore重試仍比payload未知名稱，已令外層身份統一用固定code顯示標籤，未改payload或COW guard。82287 terminal0：17passed20.74s（C:/t/fulln-watchlist-restore-root-20261007-b），移除只動具名ID、完整收藏內容復原、revision追加、第二次復原already_present且不增revision，新程序source讀回與旧來源兼容同run通過。跨257比較owner23951 terminal0：3passed592.10s；全N來源clock修正與deferred worker仍另驗，時間不授效能Gate。

中央已讀owner原log：query20159排序單案terminal0，1passed423.34s（不是整份suite重跑）；9924其餘7case原通過仍保留首紅。bookmark25165 terminal0：3passed12.22s。當前query／bookmark兩模組與兩測試＋WatchlistService共5檔mypy0，parent Callable實檔import已核；新parent verified-context變更另由owner驗證，不據此完成fullN性能。
