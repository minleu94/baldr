# Baldr 讀取 session 中央審核（2026-10-08）

這份記錄涵蓋 P01 的固定來源索引核心，以及 H20 私有 SQLite 副本的設定與 provider 介面。兩者尚未完成 UI 接線、新候選打包或真人接受；不表示完整補完計畫已完成。

## P01 固定來源索引

中央在原生 Windows 的獨立隔離暫存執行 `tests/test_daily_market_technical_universe_v4_read_session.py`，結果 **7 passed / 46.49 秒**，程序 exit 0。四個 owned 檔案的 mypy 通過。原始輸出保留於 ignored `output/qa/p01_root_review_20261008_b.log`。

同一凍結核心的舊 query、stock 與 bookmark 相鄰回歸另為 **13 passed / 302.31 秒**，程序 exit 0，輸出於 ignored `output/qa/p01_root_neighbors_20261008_a.log`。這是整個測試組耗時，不是單次產品查詢延遲。核心下一輪 selection／materializer 修改必須另行重驗，不能沿用這次凍結版本的通過結果。

測試使用真 public producer、repository 與 store 的合成來源：17 股納入、257 股排除，驗證完整索引的 AND／OR、全域排序與分頁、Decimal／同值／空值排序、選股下鑽、空母體／全排除／partial、來源不符、索引預算、取消、child 篡改，以及 fresh 收藏重驗與新程序 strict 還原。這不是 1000+ 股票或真市場 full-N 的效能證據。

session 固定建立時完成核驗的版本；它不宣稱來源後續仍未變動。頁面與個股會精確重開選取的 child artifact；新收藏重新完整核驗來源，跨來源比較仍各自使用 strict reader。64 MiB 是 canonical serialized index 的預算，不是 Python RSS 限制。

初次中央審核發現 `read_stock_snapshot` 先讀 origin page，再重讀選取的 child artifact，要求保留來源與 origin page 身分驗證的去重方案。後續修正證據列於下一段；原實際來源的下鑽延遲仍待另行驗收。

後續 selection／materializer 增量已完成中央 **14 passed / 52.96 秒**、程序 exit 0，四檔 mypy 通過，雜湊與代理凍結值一致。輸出於 ignored `output/qa/p01_selection_root_20261008_a.log`。新介面先全域篩選排序一次，分頁切固定索引；個股與 fresh 收藏共用同次頁面／snapshot 讀取，避免同操作重讀 artifact。明示空 eligibility 回零筆專屬結果，不把舊 query 的空 filter 解讀為零；包含建立 selection 最後取消 gate、身份篡改、空頁、取消與精確 artifact 核驗。原相鄰 query／stock／bookmark 最新回歸另在執行，尚未宣稱通過；尚未接 UI、官方排序或證明真 N 的效能。

## H20 設定與 provider 介面

中央新測試 `test_personal_h20_sqlite_read_config.py` 與 `test_ml_current_observed_read_copy.py` 共 **10 passed / 1.32 秒**。中央另跑既有 bootstrap、historical provider 與 current-observed capture 回歸，共 **85 passed / 3.89 秒**，程序 exit 0；輸出在 ignored `output/qa/h20_stage1_root_regression_20261008_b.log`。

明示設定 `PERSONAL_H20_SQLITE_READ_ROOT` 為絕對路徑，未設定維持 `None`；設定解析不建立目錄，frozen 模式拒絕程式包內路徑。實際 copy session 負責驗證既有私有根與固定來源的隔離。

provider 的 opt-in session 分支核對原來源路徑與 SHA，重用私有副本既有唯讀交易，保持原 provenance、feature 與 row hash；不另開來源 SQLite 連線、不再雜湊原 DB，也不提交或關閉呼叫端交易。未傳 session 的既有路徑保持相容。測試包含錯誤路徑／SHA、已關閉與取消的 session 拒絕，以及原合成 DB 與 sidecar 起訖 hash／stat 不變。

實際 H20 public verifier、feature replay、entry observation 與 Main 尚待接線。原 4 GB 封存來源的保護、等待提示、2382 下鑽時間、收藏新程序重開與新候選資格均未由這些合成測試證明。

## 真人驗收狀態

### H20 點擊路由增量

中央修改 Main 的已核名單點擊路由，直接以原 cohort／selection／reference 開固定個股 context；由既有 selected reader 完成 manifest、capture、來源及終態 fresh 核驗，不再先重讀完整名單。返回仍沿原來源重新核名單。合成路由測試 **5 passed / 2.28 秒**，驗證沒有另開 cohort worker，以及忙碌／未知列／缺參照／關閉中拒絕下鑽。保存來源 Qt 旅程 **5 passed / 10.33 秒**，包含來源變動、報告失敗仍獨立讀 H20、取消／晚到結果與明示重試；這是隔離 host，不是 Native 或新候選驗收。

本輪 UI 強制 workbench **85 passed / 3.58 秒**，原生更新頁 validator **25 通過、0 失敗、4 跳過**，三個 owned Python 檔 compile／diff-check 通過。先前 sandbox fixture WinError 5、repo 內 fixture 被 activation-root-overlap 拒絕，以及舊旅程 harness 缺收藏 handler 的失敗均保留；以外部 OS TEMP fixture 並同步 harness 的 Main handler 後才通過。full mypy 先碰到另一代理正在實作的 P01 selection 欄位／名稱錯誤；待該核心暫停修改後中央重跑，**894 source files 通過**。P01 最新功能測試與安全副本接線仍另行驗證，不能發布或標整包完成。原始輸出與修改前備份在 ignored `output/qa/h20_direct_drill_root_20261008_a/`。

使用者回報舊 `0f25b8c6ee51` 名單最終出現，但等待很久且不清楚觸發時機；雙擊 2382 後反應慢，未確認能下鑽。此項仍未通過；不要求使用者重測舊版。下一候選完成原件保護與 Main 自動驗證後，才提供精確啟動檔及分開計時的名單／下鑽驗收步驟。

## 2026-10-08 中央後續回歸

P01 最新 query／stock／bookmark 相鄰回歸為 **13 passed / 320.09 秒**；程序 handle 47428 已結束，保留輸出於 ignored `output/qa/p01_selection_root_neighbors_20261008_b.log`。四個核心／測試檔 SHA 與先前 14 項 selection 測試凍結值一致。此時間包含合成來源產製，不代表頁面延遲；UI session 接線與 full-N 效能仍未完成。

H20 stage2a 中央獨立操作測試 **12 passed / 1.06 秒**；再以外部 OS TEMP 合成來源執行 daily、capture、outcome 與 operation 四組回歸，**46 passed / 2.62 秒，exit 0**。目前 public input replay 可透過 resolver 重用私有 copy；outcome 測試中既有 helper 的 input verifier／provider mock 只證明傳遞及同操作重用，不能宣稱完整 outcome source replay 端到端。UI cohort／個股 hooks 尚待接線，原始 4 GB 資料保護及 Native 等待提示、下鑽速度仍未驗收。

F17 新查詢純層中央 **24 passed / 0.69 秒，exit 0**。驗證 canonical criteria、來源 pins、membership／unknown truth、cutoff 與排序契約；尚未接 full-N reader、頁面、收藏或正常更新，不能當作 joined query 或完整產品通過。

中央 stage2a 五檔 compile／diff-check 通過。首次定向 mypy 因 scripts namespace 同檔雙 module name 停止，保留為 invocation failure；改用 `--explicit-package-bases` 後的結果另記，不藉新增 __init__.py 改變產品 package。F17 code review 另發現 pure sort 未核 technical row 決策日、future feature 與 missing-data旗標一致性；已退回 owner 補 guards／反例測試，原 24 passed 不代表此缺口已修復。
中央 `--explicit-package-bases` 五檔 mypy 後續發現匯入既有 `tests/test_current_observed_learning_capture.py` 的 28 個型態錯誤，因此這次五檔檢查未通過，不能沿用代理宣稱的五檔 clean。四個產品 source 的獨立檢查另行執行；不改其他 owner 的測試來掩蓋結果。

中央四個 H20 stage2a 產品 source 使用 `mypy --explicit-package-bases` 結果 **Success: no issues found in 4 source files，exit 0**。UI 的實際入口確認為 `scripts/scheduled/personal_h20_daily_hook.py`：cohort 與 selected reader 目前只有 `PersonalH20ReadSession` 的分組驗證，尚未建立 `PersonalH20SQLiteReadOperation`。因此必須把私有 copy resolver 接入 ports，並在既有 reference/capture/source 終態核驗之後、回傳 UI 結果之前完成 copy/source file-group finish；單接 scheduled daily CLI 不能證明 UI 已保護原始 SQLite。

中央追加 UI call graph 發現收藏重開 `scripts/scheduled/personal_h20_bookmark_read_session.py::_read_ports` 同樣取得未綁 resolver 的來源 verifier，不能漏接；daily hook standalone prediction/manifest reader 及 natural hook／batch ports 也列入漏口盤點。設計必須區分 UI 的安全讀取與既有 scheduled 預設相容路徑，確保 fresh 收藏／新程序重開每次完成自己的私有副本與原來源終態核驗，不以名單或單股測試代替收藏證據。

## F17 列級 guard 補修中央驗證

純排序在接收技術列時，新增 decision_date、feature/previous 日期、cutoff、股票／source scope、snapshot/source-window SHA、rule keys與missing flag一致性檢查；pending／excluded 不得帶 processed technical row。中央對照既有 feature_snapshot_v4 的 lookahead 與 current-only `available_at_unknown` 契約，並獨立重跑 **37 passed / 0.71 秒、exit 0**、兩檔 mypy clean。reader issuer／generation／receipt／artifact exact pins 仍待 full join 層證明，不能由公開 DTO 格式檢查替代。

H20 stage2b 接線設計已經中央讀取，授權受控 UI hook／bookmark／Main 接線；代理先逐檔 dirty/preimage，保存 stage2a transport 差異，不重置其他 owner 檔。natural outcome batch 的逐列 publisher 終態語意仍是後續獨立接線項目，不能由 UI wrapper 通過推論 scheduled 全部安全。

## P01 UI 接線中的中央審核修正

中央讀取尚在實作的 view diff，發現 `load_selected` 的「嚴格核驗來源」傳入先前 `_read_session`；相同 catalog pins 會重用舊索引，不能證明明示重新載入當下來源未變。已要求 owner 將 load/reload 改為 fresh strict session，保留篩選、暖翻頁、同操作下鑽／返回的固定版本 cache。需新增非當頁 child 或 receipt 變動後重新 load 的拒絕反例；失敗時保留舊畫面，但不得發布新成功。此 WIP 尚未凍結或中央驗收。

P01 UI WIP 第二項中央修正：`_apply_query_result` 遇到成功的 empty selection（`page=None`）原先仍保留舊股票頁與cache，會讓新條件零結果和失敗混淆。已要求 owner 用 reader-issued query／selection呈現0列與新條件，清空表格、停用當前列下鑽／收藏，但保留來源session供修改條件重查；不得偽造v4Page。讀取失敗才保留舊可見state。要求真fixture零符合及恢復查詢反例；尚未宣稱補修通過。

### 接線中容量與空結果證據的中央修正

H20 capacity WIP 的每份 copy 上限大於所預留 main size；progress callback 重入再開其他來源，加上原來源 preflight 後增長，可能在終態拒絕前超過總預算峰值。已要求把每份 copy hard cap 綁本次預留容量，或完整預留該 hard cap，並加入反例；尚未宣稱修復通過。

P01 empty result WIP 使用 catalog entry.counts 補母體計數；catalog metadata 未獨立驗證，不能當作 strict source counts。已要求 owner 只用同來源已核 page counts 或公開 session typed counts，缺失時明示未核 metadata／計數未知，不假造全母體 page 或空資料證據。

P01 empty 計數解法已核定：ReadSession 原本持有 strict verified immutable state.counts，新增唯讀公開 `source_counts` getter 即可提供完整來源母體計數；不用由清冊metadata退讓，也不額外全母體重讀或暴露private state。已授權 core owner 在query.py與owned core test做此必要UI seam，先保存3b899160基線preimage，並補空／全排除／partial parity。核心變更後必須重跑新版本驗證，不沿用先前14／13項綠燈。UI成功零結果保存此已核counts且清空舊列，完整母體口徑與未知限制不改。

F17 full join設計已中央讀取 `output/qa/f17_full_join_query_design_20261007_a/DESIGN.md`；query/bundle/P01 exact pins、完整declared角色、membership與truth分母、排序後分頁、freshprocess／收藏新schema要求對齊。仍需補兩個公開接線契約：頁面materializer只回最多256 typed rows而不保留full snapshots；個股另沿exact公共讀取。compact sort須用公開scalar projector／compact排序API，不能存全N joined DTO或import私有helper冒稱輕量。bundle verifiedstate保存shard bytes的成本也須列入RSS。已要求owner修設計；沒有將設計視為reader或UI實作。

### H20 capacity 葉片中央結果

容量cap已綁每次預留source_size，原來源預留後增長會在低層copy上限拒絕；取消／錯誤釋放預留，重入另一來源按剩餘預算計算。同identity只計一次，distinct groups／總copy bytes各自有界。中央合併capacity、operation、daily、capture、outcome回歸 **53 passed / 2.93秒、exit 0**；兩檔 `mypy --explicit-package-bases`（沒有skip imports或ignore）通過，SHA與owner凍結值一致。已讀真合成SQLite progress重入＋來源增長反例，其私有copies清理通過。UI明示50來源groups與64GiB總預算；這是容量／生命週期證據，不是4GB原件保護或效能通過。已釋出下一步UI安全接線，原件尚不重讀。

P01 `source_counts` getter 已實作為直接回傳 strict verified state 的 immutable counts，不重新掃描。代理 targeted run_003 已 terminal exit1：denominator 新測試通過，但 no-rescan 測試把 monkeypatch 放在 frozen/slotted instance，導致測試設定與teardown失敗；原失敗保留於 ignored run_003 log。代理改在 class method instrument後另開run_004，不能沿用此輪作getter全部通過或拿測試錯誤改產品immutable契約。root 尚待凍結版本中央驗證。

### P01 source_counts 新版中央回歸

代理run_004兩個定向測試實際terminal exit0（2 passed／9.62秒），query/test凍結後中央使用獨立OS TEMP完整回歸，root session73118 **15 passed／49.72秒、exit0**；兩檔mypy通過、SHA凍結吻合。計數parity涵蓋真synthetic空母體、全排除與cancelled receipt，getter immutable/no-rescan測試在class instrument後通過；原run_003失敗仍保留。這只補計數公共介面，UI零結果／freshreload測試與實際市場效能尚未驗收，不沿用核心結果宣稱產品完成。

P01 UI真257股旅程新增instrumentation已中央讀取：保留原public reader，計冷strict open與selection、暖翻頁／stock操作，驗成功zero-result清空與恢復條件、tampered receipt後fresh reload失敗保留舊state。代理已回報run_005实际handle36788 live，尚無terminal驗證；root不重啟同fixture，也不把source/test改動視為通過。待UI凍結後中央另跑完整view與三項UI強制作業。

H20 selected進度中央發現：Main僅connect `worker.progress`，普通TaskWorker只注入cancel，不自動注入progress；若未明示傳入hook回呼，實際讀取階段不會到label。已要求傳入progress_callback並測真訊息顯示；不以signal連線存在當進度功能通過。

P01 UI run_005代理持有36788實際terminal exit1，1failed/1teardown error、120.57秒。起點catalog沒有complete列，尚未進入讀取快取旅程；teardown既有extended-path清理另失敗。owner將增加status assertion診斷與新的獨立TEMP子樹重驗，原failure保留，不改guard也不將此輪算UI通過。

H20 收藏進度中央追加審核：`_on_open_progress` 原只檢查關閉與 operation，選取變更取消舊工作後的晚到進度仍可覆蓋取消提示。已要求沿 finished 相同的 worker identity、operation generation 與 selection generation 拒絕晚到訊息，並補反例。selected hook 的明示 callback 已接入 WIP，但仍待真來源與 Main 測試；使用者所述長時間不明等待與下鑽延遲沒有因此自動通過。

中央讀取 P01 run_006 原始 traceback：來源清冊找到完整列，隨後 strict load 等待逾時，整個案例 240 秒、terminal exit1。原 predicate 同時等待 worker 結束與成功頁面，沒有輸出失敗 label，不能從這份證據判斷真正 reader 延遲。run_007 已讓錯誤狀態提早結束並輸出 label；owner 持有 16394 live handle，待終態，不延長 timeout 當作修復。

H20 stage2b owner 原生 secure integration 為 2 passed／1 failed、17.25秒、handle67349 terminal exit1；中央已讀原始輸出。失敗位置是舊 `_double_click_selected_h20_row` helper 等候 `_personal_h20_cohort_worker`，與已改為直接 selected reader 的 f545 路由不符；真 double-click 與 researchRequested assertions 已先通過。已要求同步觀察 selected worker 與沒有額外 cohort 的預期，保留失敗後再跑完整旅程；不能用修改觀察條件取代來源或進度訊息的實際驗證。代理取消／換選取晚到進度兩參數通過，仍待中央凍結版本獨立驗證。

F17 compact helper WIP 中央發現：sorter 對 key 的市場／官方處置來源 pin 只有 SHA 格式檢查，未與 query 兩個來源 pin 比較；公開 DTO 即使保持 query identity 不變仍可混入其他來源 pin。已要求逐 key 比較兩個 pin 並補各自漂移反例。代理已回報補修，最終 source/test 重跑與中央獨立驗證尚待；純 compact key 檢查仍不能替代 full-N reader 的來源、issuer、generation 與 artifact exact 核驗。

### F17 compact helper 中央凍結驗證

補修兩官方 pin 比較後，中央同凍結 SHA 完整 pure query 測試 **45 passed／0.83秒、exit0**，兩檔 mypy 通過，compile／diff-check 通過。先前中央兩檔 mypy 發現新測試 direction 為 str／Literal 不符；owner 僅補型別註記，保留案例及功能，該失敗不隱藏。source SHA `5A318037549556AD950DDCB4D2CC79440112DF8EC806E9ED3493E1645C3B53E1`，test SHA `87D2B2AA381BE771183531590EB42F8493458161585F4DD2E0729D72E0992A76`。

已讀 scalar DTO 與 parity 測試：每個允許技術／官方排序欄位都有 asc／desc 對照原完整列排序，另驗多欄、精確極端 Decimal、null 置尾及穩定股票 tie-break；key 不保存 joined row／snapshot。每次最多100000項、canonical JSONL總量64MiB，這是序列化預算而非程序RSS上限。取消在投影、分批核驗、排序及回傳前檢查；reader exact驗證、完整joined reader／正常更新／UI／收藏及真N效能仍未完成。

P01 run_007 已由 owner 實際 terminal exit1、128.11秒；中央已讀 status：完整 session／query 建立後，UI `_query_matches_entry` 裸 `Path.resolve(strict=True)` 無法處理長路徑而回 WinError3。已核定只改UI，使用同次 reader-issued session 的公開同源與canonical root契約，加上原entry exact pins；不縮fixture、不import私有helper、不弱化底層path guard。原257案例 run_008 handle76343 正在執行，尚未通過。

### H20 stage2b 相容性與後續接線審核

代理 controls/readers run_e（78466 terminal exit1）的原始輸出實際為 **38 passed／8 failed、139.84秒**，不是先前訊息的46 passed另加8 failed。中央已對照raw及test diff，沒有刪案例。失敗為legacy custom reader不接受新增progress_callback；修為只有明示secure-copy路徑傳新參數，Main仍明示root、require=True與進度回呼，未降回原庫直讀。run_f為**46 passed／18.81秒**；最終首屏文字另改白話後，Main／secure integration run_h **5 passed／16.54秒**，合併run_i **51 passed／36.46秒**。owner之後補測試型態窄化，需以最終SHA再驗；中央尚未以這些代理結果宣布通過。

P01 run_009（54178 terminal exit1）已走過長路徑載入、exact entry正反例、冷strict計數、暖頁／個股與零結果；恢復查詢預期錯寫257，原OR/rule條件沒有清除，實際及先前相同條件皆為255。中央已讀source對照，核定只修測試預期，保留全母體257／符合條件255的區別。run_010 handle49218已啟動；仍待完整終態，不能用部分assertions當整條通過。

F17任意有序≤256列materializer設計已中央完整讀取；目前P01 `_validate_selection`會重算full-N selection identity，因此每batch成本還含O(N)完整性檢查，不能只宣稱O(B logN)。已要求保留完整性guards並如實列成本，實際1000／真N效能另驗。待目前UI凍結後，下一葉片提供公開rows-only批次與精確identity；不保留full snapshots、不import private index，也不以先加孤立DTO代替完整joined reader。

### H20 stage2b 中央獨立驗證

owner最終run_j **51 passed／37.38秒、exit0**。中央對凍結十個owned source/test逐一核SHA相等，獨立短OS TEMP執行五個測試檔，root handle75667 **51 passed／40.42秒、exit0**。真source port與source/input讀取保留，模型contract是合成邊界；cohort／selected／prepare／bookmark每操作各自一份私有copy，原SQLite connect guard、file-group hash/stat不變、semantic finish先於copy finish以及無網路均由合成案例驗證。Main真雙擊selected路由、進度到可見摘要、來源漂移／關閉取消，以及controls late-progress反例通過。

UI強制作業：workbench **85 passed／4.30秒**；原生更新頁validator **25通過、0失敗、4跳過**；全域mypy **895 source files通過**。另七個production檔使用`--explicit-package-bases`且不略imports的mypy通過，十個owned Python檔compile、tracked diff-check通過。owner完整touched-set mypy仍有匯入既有`tests/test_ui_qt_h20_saved_source_journey.py`的22項型態錯誤；不把source檢查通過說成全部測試檔clean。九項warning是既有pct_change FutureWarning及Qt斷線RuntimeWarning，原輸出保留。

這項驗證只核安全副本UI接線；原4GB來源保護、原十股／2382實際等待速度、固定新候選Python/exe、新程序及Native仍須另外通過。standalone與natural-outcome batch預設尚未改安全composition；不宣稱全部H20 SQLite路徑安全，完整P00–P14／M3亦維持未完成。

### P01 UI read-session 中央接受範圍

代理原257＋1完整旅程run_011 **1 passed／125.49秒**。中央獨立全view回歸handle71854 **7 passed／142.80秒、exit0**，含真完整保存來源、跨頁／原股、比較、收藏與恢復、取消、診斷清冊與worker設置；原source/test SHA分別為`77816FA0AB4A0059F8649664880CA0BCF035FA26FFF8E22EECEE25D0B893CFF1`／`460443AA5DD3AB34D7E7C83D75FE5EFC9265B3C5EC55C2EFEA04F2787AF986CD`。

中央兩檔mypy另發現test既有QApplication.instance回傳QCoreApplication及重複_selected_row不能窄化的兩錯；僅補cast及同義非None local assertion，view無變。最終test SHA為`D85E81AEF215FA89ABDFFFEA0FF12A06D733F8D798CBFC8E85F6E05768EBFF83`，owner受影響bookmark案例1 passed／6.12秒，中央新版同案例 **1 passed／5.39秒**，兩檔mypy／compile通過；不稱原全7是在新test SHA上執行。UI強制85 workbench／validator25-0-4／mypy895均在同一最終production view上通過，沒有為純型別修正重造257來源。

成功零結果清空舊頁、保留strict session已核完整母體counts、停用當頁研究／收藏；恢復條件仍保留原OR/rule篩選。明示load/reload建立fresh strict session，來源篡改拒絕後保持舊state；相同來源篩選、暖翻頁與個股操作沿既有selection，不重掃來源／重排全母體。Windows長路徑比對沿公開reader canonical root與same-source契約，不裸resolve。測試原失敗與fixture-only extended-path bytes修正均保留於ignored QA。

這些耗時包含fixture產製，不是UI頁面延遲。1000／實際N／冷暖p95、最新版正常Main／固定候選／新程序與Native仍待；F17 rows-only materializer尚未實作，不能用本UI接線通過宣稱F17 join完成。


### 固定 7b 候選建置與同版隔離比較

來源 commit `7b21e0d4076bee10dbd32855542100cb00f17487` 的獨立建置 root handle74749 terminal exit0。候選 exe 為 `dist/candidate_7b21e0d4076b_98fff903/baldr/baldr.exe`，53,308,626 bytes，SHA256 `13f979cc2b44096bcbeed470f6e3cd510b21f3b09ffafed26b0b79b3365562b8`；固定 source archive SHA256 `81167d43b3625d684097ebfc869328464245313d4c58b074087faae87ab08beb`。建置只使用 commit archive，未包含 materializer／F17 reader WIP。BUILD_INFO 保留 built_not_validated，不覆寫建置事實。

首次同版比較 handle88943 在啟動 probe 前因終端中文編碼 UnicodeEncodeError 失敗，兩種入口 results 均空；失敗收據 `output/qa/baldr_same_version_7b21e0d4076b_3480e22c/same_version_receipt.json` 保留。僅設定 parent PYTHONIOENCODING=utf-8 後，以同一候選另開 QA attempt，handle34241 terminal exit0；中央讀回 `output/qa/baldr_same_version_7b21e0d4076b_0294cc33/same_version_receipt.json` 為 passed_isolated_fixture。兩種入口 launch、journey、model、h20、invalid_config 的可觀察結果一致；直接 Qt script／module 入口亦一致。

H20 比較只涵蓋呈現 fixture，推薦只涵蓋 synthetic execution display；canonical 保存推薦 nofollow 限制、原十股來源／4GB安全副本、完整母體 Main／新程序、Native 真人與效能仍未驗收。原交付 exe SHA256 `ab0c72ef1c98f906e3d7ef14d440490ea4bf238aa53f959597636ddc2b1b263e`、main `305635642ecdf5f1331a24a0c81566d07f36cb0d` 於建置前後均核對不變。

H20 新 ignored controller 的中央靜態審查另發現兩項來源初始 pin／preflight 時限落差，以及 shutdown 未終態仍可能維持 passed 的測試判定缺口，已交 owner 修正；尚未授權啟動原來源旅程。真人先不重測 0f25；新候選未交付。
