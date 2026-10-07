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
