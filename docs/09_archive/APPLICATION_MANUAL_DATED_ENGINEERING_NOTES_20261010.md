# APPLICATION_MANUAL 日期化工程與操作快照（2026-10-03 至 10-08）

> 本檔保存原手冊第 14 節後的日期化工程／候選功能紀錄與當時操作描述。它們是歷史快照，不是目前操作或產品狀態依據。
> 目前操作請看 [Application Manual](../07_guides/APPLICATION_MANUAL.md)；目前狀態請看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，驗收範圍請看具名 QA。
> 手冊中的同名標題是舊錨點導引；本檔保留原文，並在標題前加入穩定連結識別碼。

<a id="manual-tail-001"></a>
### 個股研究來源恢復與現況基本面更新（2026-10-03）

觀察清單開啟個股後若顯示「部分可用」，進入「Rule / ML / 歷史」頁，明確選擇同股票且決策日不晚於查詢日的保存分析，再按「載入選定來源」。來源選擇器不自動套最新結果；切換股票會重新驗證，未入選股票只呈現該次篩選理由。沒有合適來源時按「前往推薦分析，分析代碼並保存」，確認推薦頁「指定研究股票」參數；空白仍分析完整股票池，最多200個四至六碼代碼，以逗號或空白分隔。執行、保存後返回報告並重新載入，明確選取新保存結果。獨立技術觀察只說明當日行情，不是推薦、勝率或正式ML推論。

更新頁月營收區可按「更新現況研究資料」：使用既有兩市場 raw/CSV 快照，全列與SHA驗證後以Decimal將千元轉TWD、備份及append-only套用current表。缺少raw、期間不符或資料遭修改會拒絕；不為此操作補歷史公告日，不解除正式回填precheck。weekly來源收集成功後另接current基本面writer；有互斥鎖或600秒逾時會回失敗／待回讀，不能當成功。

基本面現況可以更新至2026-08月營收／2026-Q2季報，而正式PIT仍較舊；兩者契約不同。現金流未明示期間不得作累計彙總；原OpenAPI單位未驗證的列保留但不顯示可判讀數值。Advice或ML仍缺時先查所選保存來源及來源資格；source revision quarantine必須完成正式歷史重建／接受，不能將研究模型當正式概率。排程exit0僅為程序結果，需核對報告、資料日期、兩市場版本、row counts及來源品質；週末官方未發布依cadence列自然等待。


Health排程使用臺北決策日，行情日另存market_data_date；週末沿用前一交易日必須由未過期hash-bound官方離線日曆驗證其間全部休市。缺日曆或跨過新交易日仍拒絕。控制回讀需同時指定精確保存推薦、非未來validation日期及獨立status path，Health／source／proposal／Exit寫入旁側controlled_runs；不要以控制測試代替自然排程收據或覆寫canonical同股同日提案。人類論點與入場身分仍需真實來源；degraded報告可閱讀，不代表可執行交易。

<a id="manual-tail-002"></a>
## 2026-10-03 行情日期、來源排除與 Paper 研究判讀

入口仍為 Daily Decision Desk／市場頁／觀察池／持倉與風險，以及排程 Evidence dry-run 報告。先看 Taipei 決策日，再看各區塊實際行情日與官方日曆來源；週末／假日最新行情日可早於決策日。日曆 unknown/過期、截止後真正 stale、缺行情仍須排錯，不能把只有排程 exit0 當成資料全正常。專案截止是 04:30 America/Los_Angeles（按 DST 換算），不是交易所發布時間證明。

廣度會顯示被排除的代碼與原因；原始「除權／除息」只有 custody hash、來源日期、取得時間與價格/股數相符才列非可比較排除，不算平盤。相對強度只使用至少 21 個有效觀測值，逐檔列出缺當日報價或歷史不足；無上市／交易狀態證據時，不推論停牌／下市。排名為有足夠來源的子集合，不能解讀為全部股票都可分析。

排程報告的普通持倉／風險與 Paper research 分開閱讀；Paper lane 有自己的 status、capture_ready、warnings/blockers 和 alerts/risk。1418 machine seed 與其他研究部位缺 entry identity／治理 thesis 時，顯示研究治理缺件，請勿為消除警告輸入虛構成交或人工 thesis。只有明確確認的使用者持倉且有待補欄位時，才列 user_actions/required_human_fields/manual_action_required；舊 manual 標籤本身不證明真實持倉歸屬。任何研究 proposal 都不會自動交易或更新正式持倉。

報告需分別閱讀 engineering_action_required（程式、接線／來源故障）、source_qualification_required/gaps（具名歷史／正式來源資格缺件）、research_qualification_required（Paper 研究治理）、自然 Forward/Exit 樣本，以及 wrapper exit_code、pipeline_exit_code、summary errors/status 和 report 存在／stdout SHA。Risk 的 estimated 保留上游估計品質與附註；真正 degraded/missing 上游不會被清除。整體 degraded 不等於使用者必須補人工 thesis。

目前 current 月營收/季報支援有來源覆蓋的當下個股研究；歷史 PIT、完整公司範圍、公告時點、季度未知 cash-flow basis 與正式 model/source revision 仍受原資格限制。遇到這些缺件，查看 source_id、actual/expected period 與 reason，不能全部解讀為週末等發布。實際收據與驗收見 [完整補驗報告](../06_qa/OPERATIONAL_QUALITY_AND_RESEARCH_ISOLATION_20261003.md)。

<a id="manual-tail-003"></a>
## 2026-10-04 保存來源、當下研究與持倉日期

本節描述本輪介面及來源契約，實際版本接受範圍見 [Astra 工程收尾](../06_qa/ASTRA_ENGINEERING_CLOSEOUT_20261003.md)。驗收尚未完成時，不以本節當作全系統已通過證據。

1. 從觀察清單或持倉開啟指定股票，在「Rule / ML / 歷史」選擇同股的保存來源，再按「載入選定來源」。候選同時核對股票、結果、決策日、行情日及來源快照識別；若清單載入後來源被改寫，必須重新取得清單，不能沿用舊選項。 保存來源的行情日不得晚於該來源本身的決策日或本次查詢日；非空但無法解析的日期也會被拒絕，不能藉較晚查詢日使用來源決策當時尚不存在的行情。
2. 沒有來源時，前往指定股票分析並執行。若分析正常完成、該股未入選，但有完整封存的篩選理由，仍可保存並在報告明確選取；它代表該次排除結果。未完成、取消、失敗或沒有封存證據的空結果不能保存；未入選紀錄不開放加入候選、回測或個人推薦決定。
3. 欲查看現在的模型觀測，按「查看當下獨立 ML 研究（保留保存 Advice）」。保存 Advice 的身分保留，ML 改查當下同股、同一行情列指紋的研究 run；按「返回此股已選保存來源與 Advice」回到原範圍。切股會清除舊股票內容並重新核對來源。
4. ML 若可讀，顯示模型／資料版本、run、行情日、實際推論時間、整數基點預測及 H5 狀態。基點是扣標準 80bp 成本後的 benchmark excess 研究目標，不是勝率；H5 尚未成熟時，實際報酬、成本與成功結果保持空值。缺來源、錯日期或不符 hash 時保留具體原因，不能借其他股票或其他保存決策的結果。

市場總覽的預設判讀日、主力流向的當下查詢日，以及資料更新的預設日期／「今天」與月營收預期期別，均使用 Asia/Taipei 的日期。主機在洛杉磯或 UTC 跨日時，不再將臺北日期截回主機的昨天；明確指定的歷史判讀日仍照原值查詢，資料日及發布截止另依各來源驗證。

市場總覽的「市場情緒」另列判斷日與行情日：判斷日是本次請求的生效日期，行情日是截日以內最後一筆有效指數收盤價的日期。例如週一盤前判斷可使用上週五已完成行情，兩個日期各自保留。行情日期缺漏、無法解析或晚於該段截止時顯示未知，不借廣度日期補填，也不改變原有盤勢計算及歷史轉換規則。得分或訊號強度未提供時亦顯示「未知」；真正的零值仍顯示 0。

若主力流向提示「台灣市場日期無法取得」，本次不啟動新的查詢；排除時區或系統時鐘問題後按重新整理。尚未取得 dashboard 日期時，個股／分點明細也不會先用主機日期查詢。資料更新若無法取得台灣日期，會停用初始日期欄位並顯示原因；先排除問題，再重新開啟程式恢復日期控制。按「今天」或執行更新時仍會重驗日期，失敗會中止該次工作，不推定另一個截止日。

從已完成且保存的未入選結果直接開啟個股研究時，頁首亦可顯示該筆已核驗行情日；必須同股票、同結果、同決策日且行情日不晚於決策日。已有非空日期不被另一日期覆寫，錯股／錯 run／錯日期仍拒絕。

持倉頁與個股報告分別標示「持倉觀測日」及「行情資料日」。現況數量、成本、曝險及未實現損益來自真實帳本與有日期的行情，損益使用 Decimal；最後交易日不充當行情日，週末行情日也不充當今天的持倉觀測日。只有價格與成本、沒有可評估進場假設時，保留價格／損益觀察，不能據此判斷假設仍符合或健康。行情過期或 freshness 未驗證時，報告仍列明資料日，但不產生當下 Health／Exit 判定。查歷史日期而沒有可核驗歷史持倉快照時，不顯示今天的數量、成本或 Exit。Exit 為現有持倉條件的唯讀解釋；缺真實 entry／thesis 身分依然揭露，不推導或執行賣出。

切股、改來源或重新載入時，舊報告提示與表格會立即隱藏，再顯示本次內容；不把尚未完成的新請求與上一份持倉內容混在一起。

手動持倉若沒有推薦、回測或策略來源，條件監控顯示「來源不足」並說明無法對照進場假設；已有來源但沒有可評估 thesis 時才顯示「待更新」及價格／成本僅供損益觀察。兩者都不因已有價格與成本而顯示「仍符合」。

從未連結推薦來源的持倉列開啟個股研究，頁首資料日取自同一次表格載入、同一部位與股票的行情快照。例如最後交易日為 7/31、最新行情為 10/2，頁首顯示 10/2；不把 7/31 或今天當作行情日。沒有有效行情日期時保留未知。已連結的保存推薦則保留該筆來源自己的日期與 run，不能用目前行情覆蓋；要取得更新行情，先重新整理持倉再開啟研究。

保存來源若缺少行情資料日，來源與 Advice 都保留未知，決策日仍獨立顯示。重新載入不會用決策日或今天日期補造行情日；請回查該筆保存結果的來源完整性，或為同一股票重新執行並保存新的分析，再明確選取新來源。無來源恢復亦維持此規則，不自動套用另一筆最新推薦。

持倉表新增「行情資料日」與「行情新鮮度」，條件監控明細亦列出該報價的資料日。持倉頁、市場總覽的持倉警報、個股報告及使用者宣告持倉研究，共用行情日期／來源指紋與官方市場節奏的核對。週末可使用最近已完成交易日的行情；無日期、缺值或過期價格僅保留損益觀察，不能單獨觸發停損／停利或顯示價格條件仍符合。若等待行情，先更新每日行情並重新整理，再核對日期與 freshness；不把最後交易日改填成行情日。歷史研究不借用今天的行情資格。

個股報告的新鮮度另核對 Freshness 收據的資料根與 SQLite。當下報告可沿用台北前一日或休市前的日價收據，但收據必須有不晚於本次讀取的明確時鐘，且收據的實際／預期期別、股票實際行情日，均符合官方日曆與 04:30 America/Los_Angeles 專案發布截止。即使收據是在今天產生，跨過下一個發布截止後也須重新核對；月季資料與歷史報告不因此取得跨日資格。缺日曆、錯誤根目錄／資料庫或期別不符時保留未知，不影響已知行情及損益數值的展示，也不補造 PIT、進場假設或 Health 結論。 若日價來源明示 `available_at`，它還必須包含時區且不晚於 Freshness 收據或本次讀取時鐘；錯誤值不作 freshness 證明，也不原樣顯示為合法取得時間。這個欄位來自已綁定 Quick 收據的完成／檢查時間，不代表上游公告時刻。欄位缺失或 null 則保留未知時間，日價 freshness 仍依實際行情與官方發布節奏判斷，不用 probe 時鐘補填。

若更新行情後仍顯示缺少新鮮度收據，先在「數據更新」檢查每日行情來源，再核對既有 Freshness 排程輸出的 `<OUTPUT_ROOT>/scheduled/data_freshness/latest_status.json`。頁面的「檢查此資料源狀態」只讀取狀態，不會重跑這個 probe。需要手動診斷時使用 `scripts/scheduled/data_freshness_probe.py --data-root <DATA_ROOT> --output-root <OUTPUT_ROOT> --db-path <TWStockConfig.db_file>`，必要時明示 `--calendar-cache-path` 及 `--temporary-closure-path`；它唯讀檢查資料庫並寫入本次狀態／日誌。收據必須由該資料根、資料庫及原始行情真正產生，不能複製另一環境的收據或改寫其路徑來解除未知。

市場總覽或 Evidence 呼叫持倉快訊時，若實際行情日晚於請求截日，會列出股票、行情日與截日，停用該行情的價格條件判定；來源日期與雜湊不會被改早。仍可看到現況價格觀察及品質警示，但不能把它當作歷史停損／停利事件或歷史 PIT 證據。正常同日查詢，以及週末使用已核實的最近交易日行情，維持原本判讀。

現況基本面列出單位與期間基礎：月營收是單月 TWD，損益表是年初累計，資產負債表是期末；現金流若來源未明示期間基礎，保留數值但禁止彙總及衍生比率。現金流目前供報告逐項觀察，既有推薦基本面 provider 與 CORE19／20 特徵沒有使用它，不能將期間基礎未知說成整條 ML 無法運作。`source_available_at` 是有實際 HTTP 完成證據的取得時間；缺此證據時保持未知，另列本機驗證時間。這兩個時間都不能代替歷史公告時間。

個股報告的法人區塊採用已核驗的最新現況修訂，保留原始 base、來源及實際觀測時鐘。後續官方數值回復原值時，新的修訂會明確反映回復，不繼續沿用較早差異。同一觀測時鐘、同股的九個法人買進／賣出／淨額欄位不一致時，reader 拒絕任意選一筆；每筆來源與內容雜湊仍分別核驗。僅 source_version 改變且九欄一致不新增現況修訂。發生衝突時核對原始 observation 與修訂紀錄，不能修改時間解決。這條現況路徑目前不參與推薦排名或 CORE19／20 特徵，也不取得歷史 PIT 資格。

自然執行的 PE／月營收條件只讀本次 invocation 截止時已取得的現況觀測。月營收年增率只使用同份官方當期報表的去年同月比較值；比較列須同股、同來源、市場、原件 hash、取得時鐘、TWD 單位及單月期間基礎，並綁定當期報表。原始千元先轉 TWD；先前曾觀測的舊年度報表不能代替缺失或被阻擋的同報表比較值。比較列保留當期報表及原始 hash 身分，並記錄其實際新增觀測時鐘，不宣稱它在去年即已可得。本輪原件有七筆沒有可用去年同期值，仍不產生年增率。指定截止日（包括明確指定今天）的執行維持正式 PIT 路徑，不借這些現況列。保存結果中的 `current_fundamental_lineage` 事件保留同次請求、數值、來源、日期與取得時鐘；月營收的來源版本內容雜湊與原 HTTP bytes 雜湊分開記錄，原列未保存後者時保持未知。

手動套用既有月營收快照時，使用 `scripts/apply_current_monthly_snapshot.py --snapshot <CSV完整路徑> --db-file <TWStockConfig.db_file> --backup-dir <備份目錄> --lock-path <OUTPUT_ROOT>/release_v4/.ml_heavy_chain.lock --evidence-file <本次獨立驗證JSON>`。鎖必須與該正式 DB 的 G6／Quick／Forward 使用同一 canonical 根；不能改成報告目錄或省略 `release_v4`。預設只做 preview，確認原件核驗、當期筆數及同期比較筆數後，加入 `--apply` 才新增現況觀測。原 HTML 預設位於 CSV 同層的 `raw_html`；若另存，明確加 `--raw-html-dir <原件目錄>`。它與自然排程共用同一 materializer，先核對 CSV／HTML、單位／期間及來源版本，再取得寫入鎖、檢查容量並備份。缺原件或不匹配時 blocked，正式歷史月營收表不變。若顯示 `apply_failed_readback_required`，先讀回該批資料及 receipt 確認是否已提交，不能逕自重試；每次使用獨立 evidence 檔案保留前次失敗證據。evidence 目的地若與輸入 CSV、資料庫及其 sidecar 相同，或落在 raw HTML 原件目錄內，程式會在規劃或寫入前拒絕；此時 stdout 明示沒有寫出 evidence。

官方 PE、PB 與殖利率由 `OUTPUT_ROOT/current_valuation/` 的原始回應及回執讀取，殖利率單位為百分比。估值日與行情資料日還必須符合官方日曆的最近已完成交易日，才可用於當下 ready 判讀；盤中不把尚未完成的當日當成收盤資料，週末可合法沿用上一交易日。較舊、超前或日曆無法核驗時保留各自診斷，不能因兩份資料同樣過期就視為新鮮。另一市場已成功擷取但沒有此股票列時標示不適用，不降級該股已核驗來源；真正擷取失敗、缺件或 hash 不符仍顯示限制。

自然選股的行情與 PE 共用 04:30 America/Los_Angeles 專案截止（台北夏令期間 19:30、冬令期間 20:30）及已驗證官方交易日曆。截止前仍使用前一完成交易日的行情與該日 PE；較新的當日估值檔不能遮蔽這個指定日來源。來源已在本次實際決策時鐘前取得才可使用，不能把「行情日期」當成其取得時間。指定日缺件或損壞時先重新擷取官方估值並重新分析，不能改日期或改選較舊來源來消除警告。手動擷取入口為 `scripts/capture_current_official_valuation.py --output-root <OUTPUT_ROOT>`；每次保留獨立 raw／receipt，不寫正式估值表。官方缺 PE 時保持缺值，不以零代填。 PE 必須為有限且大於零的 Decimal 才能通過 PE 上限條件；零、負值與非有限原值保留來源與診斷，但不因此成為低估值候選。正式與現況路徑各自先通過原有日期／來源資格，再套用相同數值規則。

上市／交易狀態只解釋官方名錄或公告已核實的現況，列來源、觀測時間、限制期間與部分來源失敗；缺報價本身不證明停牌或終止上市櫃。現況公告不回寫舊保存推薦的排名排除理由。排錯先核對所選股票與日期，再看該區來源回執；重新載入可重試。切股或更換來源時，上市／交易限制與來源明細立即清成「尚未載入本股」，取消或失敗也不保留前一筆內容；同股、同一來源的重新載入則可保留明示的上次可用報告。

官方擷取遇 HTTP 520 時，會與既有暫時性 HTTP 錯誤採相同的有上限重試。既有擷取契約只保存每個來源的最終回應，不宣稱保留每次網路重試的 body；先前已保存的失敗批次不會覆寫。若重試後仍失敗，該批維持部分來源失敗，不能將不同 run 的成功項目拼成一份完整批次。TPEx 終止上櫃表只有在欄位、日期、列長及總筆數相符時才採用；取得日與事件生效日分開保存。

官方來源 bundle 的每次 run 收據為不可變紀錄；程式呼叫端重用既有 `wrapper_run_id` 時會在啟動子程序前拒絕，發布時也不覆寫競態建立的收據。重試應建立新的 run，不刪除原失敗或部分檔案；只有完整寫出本次收據後才更新 latest 指標。

<a id="manual-tail-004"></a>
### 自動選股的官方基本面來源與結果目錄

`scripts/scheduled/run_scheduled_recommendation_snapshot.py` 與 `scripts/run_personalization_recommendation.py` 的 `--output-root` 是推薦結果目的地；若結果保存在 Shadow，官方 PE 與 MOPS 月營收仍應從 canonical 資料輸出根讀取。必要時以 `--current-fundamental-source-root <canonical output>` 指定來源。解析順序為明確 CLI 來源參數、`CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT`、獨立 `TWStockConfig(data_root=...).output_root`；最後一項遵循專案的 `OUTPUT_ROOT` 設定，通常預設為 `DATA_ROOT/output`。結果目錄參數不覆蓋來源設定。

05:10 snapshot wrapper 轉送獨立來源參數，05:45 pipeline 將其 canonical source root 傳入 snapshot child，再用該 child 的 exact result ID／cohort hash／stdout path 和 SHA 啟動學習。Bank 讀取已保存的 snapshot，不為它另造股票清單。若自訂環境把 `OUTPUT_ROOT` 用作 Shadow，應明確設定 `CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT` 指向官方 capture 所在根。

05:45 pipeline 先等待當日同一 G6 raw run，再依序處理 Quick、官方來源、推薦快照與學習。Quick 的鎖、收據與輸出都沿用 canonical source root；已驗證且對應行情日的技術收據可重用。等待使用三小時 pipeline 總期限，先保留 Quick 與 learning 各一個 child timeout 及五分鐘收尾，預設可等待約 55 分鐘。後續每個 child 也保留五分鐘收尾，learning 之前另留一個 learning timeout；額度不足的步驟不啟動，明確記為 timeout。未取得 exact G6 terminal path／SHA 時，Quick 與 current-observed learning 保持 blocked；獨立來源與快照步驟的完成不代表學習已通過。排錯須比對同一 raw run、terminal hash 與當日來源日期，不以後來的 latest 取代。

Pipeline 的 `--calendar-cache-path` 與 `--temporary-closure-path` 同時傳給 Quick 及 learning；直接呼叫 `run_daily_recommendation_learning.py` 時，臨時休市參數名稱為 `--temporary-closure-cache-path`。Learning 的年度日曆依序使用明確 CLI、`NATURAL_MATURITY_CALENDAR_CACHE_PATH`、既有 `ML_FORWARD_CALENDAR_CACHE_ROOT`，最後使用 repository 的 `output/paper_execution_eod_replay/calendar_cache`。臨時休市使用明確 CLI 或 `NATURAL_MATURITY_TEMPORARY_CLOSURE_PATH`。依賴檢查、特徵日期、當日 capture 與成熟結果必須使用同一來源；過期、損壞或涵蓋不足時更新既有官方日曆擷取，不能用價格列或自行建立的工作日清單取代。年曆上的預定開市日不保證當日行情已發布，也不表示不存在臨時休市。

目前 05:50 BankTaiwan wrapper 最多等待 10,500 秒取得同次 G9 terminal，在五小時總預算內保留兩小時 child 與五分鐘收尾。2026-10-04 已將既有 Bank task 的執行期限更新為 `PT5H`；本手冊較早日期的 1,800 秒等待描述是當時設定，不適用於本版。期限到達時保留具名失敗，不用其他 run 或尚未核實的 latest 繼續。

Quick 的資料日使用 G6 已驗證的 `source_date`，例如週日 10/04 決策可使用已完成的 10/02 行情；不要求把收據取得時間改成週日，也不要求交易所提供週日價格。重用仍核對原收據、實際來源及截止時鐘。需要寫入時，pipeline 先在保留預算內最多等待 30 秒完成同一 OS 鎖的交接；Quick 本身仍要重新取得鎖。逾時或又遇其他 writer 時保留原阻擋，不刪鎖或修改 ACL。

遇到 PE 或 YoY 缺失，先比對 snapshot receipt 的 `current_fundamental_source_root`、官方 capture 路徑、指定行情日與本次 cutoff，再檢查同股的 execution lineage。空 Shadow 目錄不是官方沒有資料的證據。來源已存在但讀不到屬接線或配置問題；錯日期、損壞的 raw／receipt 或 cutoff 之後才取得的資料仍拒絕，不能回退舊正式 PE 充當當日觀測。一般 UI 依自己的資料設定讀取；隔離 QA 來源不會成為正式資料根。

既有 scheduled default strategy 目前沒有開啟 PE／月營收 YoY 篩選；修正來源根不會替使用者或自然排程新增條件。需核對「當次已使用的條件」與「provider 可取得的資料」，不能將可讀資料說成已影響當次排名。

現況自動學習的自然樣本支線使用前一官方交易日特徵，以及同日收盤後核驗的收盤價作研究標籤基準；這不是可成交 entry 或當時可執行的交易績效。非交易日沒有同日收盤基準時保持 pending，不借上一日價格造樣本。正常交易日完成 capture 後，須再累積 **20 個官方交易日**及完整股票／TAIEX 來源證據，才可進隔離的自然研究 fit。這條支線沒有模型機率或交易權限，不給正式決策、forward evidence、promotion credit，也不建立 active pointer。個股 ML／Paper 的 H5 是其他既有五日觀測用途，不以此二十日 label 冒充 H5 成熟。

正常推薦仍使用原本的預設候選範圍與 `top_n=50`。Learning 必須涵蓋同一筆已保存推薦的全部 eligible 股票：1–16 檔沿用 v1；17–50 檔以 v2 記錄完整 cohort，依股票碼排序，每批最多查詢 16 檔。批次數、每批來源雜湊及整體組合身分都可在 source contract 中核對；不截掉第 17 檔以後的候選，也不把某一批當成整份 capture。超過上限、重複／缺漏股票、錯 result ID、stdout 原件或來源雜湊不符時，整份觀測停止，保留明確診斷。手動指定 17 檔以上而沒有同筆保存推薦證明，也不接受為正常排程 cohort。

盤前可取得前一交易日的特徵，但當日收盤基準尚不存在時，輸入 capture 仍為 pending；不能用先前收盤價補造已完成樣本。成熟結果使用之後取得的、獨立核驗的 G6 快照查原 capture 全部股票，保留原訊號日特徵與後續結果來源兩組身分；新一天的推薦股票組成或快照版本可以不同，不能把後來的價格或特徵回填原 capture。若批次查詢或來源驗證失敗，整份結果 blocked；來源有效而個別到期價格缺件，則該股票保持具名缺件，沒有成功標籤。

月營收 CLI `scripts/fetch_mops_monthly_revenue_snapshot.py` 的 `--output-dir` 是擷取基底目錄。輸出中的 `capture_dir`、`output_csv`、`raw_html_dir` 指向本次唯一 run，後續驗證或套用請使用該次回傳的完整 CSV 路徑，不自行拼接舊頂層檔名。候選選取兼容原頂層 CSV 與 `captures/run_<抓取日>_<UUID>/` 的單層 CSV，依資料期別、抓取日、mtime 與路徑穩定排序；不遞迴備份或任意子目錄，遇 symlink／junction／reparse 路徑拒絕使用。底層寫檔若目標已存在會拒絕覆寫，保留舊原件；應從正常擷取入口取得新的 run，而非刪除舊檔重試。`--no-save-html` 仍僅供數值候選，沒有原 HTML 的候選不能通過要求原件的現況套用驗證。

季報擷取若收到非 HTTP 200、redirect 或非預期回應網址，會保留上限 32 MiB 內完整收到的回應原文、實際 HTTP 狀態、網址、bytes、SHA 及回應完成時間，並將該批標為失敗。失敗回應不解析或套用，`source_available_at` 保持未知；請依本次 receipt 排查來源，不能將 HTTP 完成時間視為公告日或把失敗改成成功。

<a id="manual-tail-005"></a>
### 研究儲存位置與容量排錯

新研究產物由 repository 本機設定 `output/ml_research_storage.json` 指定位置；設定只接受 `schema_version` 與 `active_root` 兩個欄位，例如 `{"schema_version":"ml-research-storage.v1","active_root":"D:/Min/Python/Project/FA_ML_Research"}`。設定檔不納入 Git。缺席時仍使用 `<repo>/output/ml_research`；存在但內容或路徑不合法時停止，不悄悄換回舊位置。`active_root` 必須是絕對路徑，不能與 repository、正式資料、release 或學習 Shadow 根重疊，也不能經過 symlink／junction。

切換前停止研究 writer，核對目的地容量，再建立設定並重新啟動程式。所有新 G6 projection、B store、股票研究 snapshot／模型及 registry 寫入 active root；既有 C 槽產物仍按原絕對路徑與 hash 唯讀使用，不搬移、不重寫回執。UI 開頁只讀 registry，不啟動訓練。Raw operational status 仍在 canonical `OUTPUT_ROOT`，G9／Bank 的自然學習 capture、候選模型與結果仍在各自 Shadow root；不要把三者設成同一目錄。

研究 snapshot 的來源檢查允許一種空 WAL 中繼資料變動：收據與實際檔案皆為既存 0 bytes、空內容 SHA，僅跨次驗證的 mtime 不同。每次仍檢查路徑、非 reparse、大小、SHA 及讀取前後穩定性。WAL 新增任何內容、非空 WAL 改變或主 DB／snapshot pin 不符仍停止；先保留失敗收據，再依當前來源建立新 run，不能改寫舊 terminal 或手動 checkpoint 正式 DB 來通過。

同輸入重用另核對 SQLite shared-memory 的來源路徑、bytes 與 SHA；唯讀連線可能改動該鎖資訊檔的 mtime，因此只允許跨次觀測的合法整數 mtime 不同。缺欄位、路徑／大小／內容變動或不合法型別仍拒絕；主 DB、WAL 與其他來源身分不適用此 shared-memory 例外。Registry 的 SHA 可接受裸 64 位小寫十六進位或明確的 `sha256:` 前綴，正規化後仍須符合實際檔案內容。

Forward 的 5／10／20／60 日結果以已驗證官方日曆的交易 session 決定到期日，並讀取該日的實際收盤價。尚未到期時保持等待；已到期但官方缺收盤價時，顯示來源價格缺件，報酬、benchmark excess 與成功結果保持空值。系統不會跳過缺價日、改用更晚價格湊足筆數。排錯時核對 `planned_official_maturity_date`、`target_price_state` 及原始行情來源；`expected_maturity_date` 保留舊按有效價格列數計算的診斷，不是目前結果的到期依據。官方日曆未通過驗證時仍停止計算，不回退舊列數算法。

每次計算固定一個帶時區的執行時鐘。臺北 13:30 前，事件價、成熟度診斷與到期價查詢都排除當日資料，即使 DB 已存在當日列也不使用；當日才到期的結果仍等待收盤。13:30 後仍須有到期日的真實收盤價，沒有價格便回報來源缺件，不補值。明示較早的歷史 cutoff 保持該日收盤界線；未來日期或沒有時區的時鐘會被拒絕。收據的 `invocation_date_taipei` 是執行日期，`requested_data_as_of_date`／`effective_data_as_of_date` 是原始／正規化後的請求日期，`price_read_cutoff_date` 才是價格查詢上界，三者都不表示已有該日行情。例如週一盤前的查詢上界可以是週日，但實際最近行情仍是週五，實際結果日期另看 `event_price_date`／`outcome_price_date`。

排程 Forward 使用 `--windows`、`--lookback-calendar-days`、`--max-events` 限制視窗、查詢天數與事件數；明示 `--start-date`／`--end-date`／`--data-as-of-date` 仍須通過當次時間界線。`--calendar-cache-path`／`--temporary-closure-path` 指向既有可核驗日曆，未指定時使用 repo 既有 calendar cache；缺 cache 應更新官方來源，不能製造工作日清單。無 `--confirm` 時為唯讀 dry-run，不初始化 Evidence schema、不寫 outcomes，也不等待寫入鎖。

確認寫入正式 DB 時，Scheduled Forward 與 G6／Decision Capture 共用 canonical `OUTPUT_ROOT/release_v4/.ml_heavy_chain.lock`。Forward 最長等待 10,500 秒，且取得鎖須早於臺北日界前 3,600 秒；取得後再驗實際日期、來源及剩餘預算，未取得或已跨界便留下阻塞收據。Decision Capture 使用自己的 child 與收尾預算。`--output-root` 可將 Forward 收據另存，但不會改變正式 DB 的鎖根。遇到等待、timeout 或 release failure，先核對同 run 的 reservation／clock guard／terminal receipt，保留原收據，等原 writer 結束後重試；不要刪 lock metadata、改 ACL 或強制結束其他 writer。

手動 `scripts/calculate_forward_outcomes.py` 保留既有預設寫入行為；先以 `--dry-run` 及 `--decision-date`／`--start-date`／`--end-date`／`--windows`／`--limit` 核對範圍。其正式 DB 寫入遇鎖忙會立即回報 `blocked_writer_busy`，不套用排程的 10,500 秒等待；手動 Evidence pipeline 同樣先取得 canonical lease。隔離 replay 的每日 cutoff 保留為該重播日，不讀未來價格；重播 DB 不得覆蓋配置中的正式 DB。

手動 `scripts/capture_evidence_events.py` 預設 dry-run；以 `--source`、`--result-id`／`--decision-date` 及必要的 cutoff／capture mode 核對來源後，才使用既有 `--confirm` 寫入。正式 DB 的 confirmed capture 同樣先取得 canonical lease，busy 時回 `blocked_writer_busy`／exit 2，尚未建立可寫 repository；另存 `--output-root` 不會另開一把鎖。`--dry-run --confirm` 仍以 dry-run 為準，Evidence 與 Decision Desk 來源 repository 都維持唯讀；隔離 DB 不會鎖住正式資料根。

`scripts/smoke_evidence_pipeline.py` 僅供隔離測試資料庫，無論 dry-run 或 confirm 都拒絕配置中的正式 DB 及其別名路徑；它使用相同 verified calendar 與實際日期，缺日曆不會產生假 READY。以 `--db-path <隔離DB>`、`--recommendation-result-id <該QA根的保存結果ID>`、`--decision-date <決策日>` 指定測試，並將 `--data-root`／`--output-root` 指向獨立 QA 目錄；先使用 `--dry-run`，再核對摘要中的日曆阻塞數與實際結果。

`blocked_insufficient_storage` 是實際容量阻礙。研究 cycle 依 2026-10-05 使用者授權採中央 20 GiB reserve，另計來源 DB／WAL 快照上限、2 GiB 持久增量與 2 GiB 暫存；磁碟顯示仍有數百 GiB 不等於可通過。依 terminal 的 required／available bytes 排錯，可用空間須涵蓋完整工作用量加 reserve，不能只因磁碟尚有空間而跳過預算。專用目錄可使用 NTFS 標準壓縮繼承，但未量測的新資料不能套用舊壓縮率。停止 writer 後移除本次新增設定可回到舊預設；保留 D 槽產物及全部原始回執。2026-10-09 兩批歷史 QA 冷封存的終態與容量操作快照見[終態對照](../06_qa/C_DRIVE_QA_COLD_ARCHIVE_RECONCILIATION_20261009.md)；該快照不是目前可用容量，每次 cycle 仍須以當次 required／available bytes 判斷。

外層正式 raw-PIT bootstrap 依 2026-10-05 使用者授權改為 20 GiB reserve、35 GiB 持久預算及 40 GiB 暫存，共 95 GiB。它因空間不足而停止時，正式歷史建置仍未完成。G9 只有在 raw 的錯誤類型、bootstrap stage、指定輸出根、整數容量帳及唯一 headroom blocker 都吻合時，才繼續核對獨立研究支線；仍須讀回 exact completed G6 terminal 的自身容量、來源、快照、模型及 registry 證據。重用則沿新 terminal 核驗原 completed terminal 與其原容量證據。任何 child failed、錯 hash、不同容量 stage、少於收據政策規定的 reserve 或缺少證明都不能接受；獨立研究成功不會把外層正式狀態改綠。

重跑同一來源時會重新驗證行情、修訂、B 映射及股票範圍。觀察清單／持倉檔的路徑、bytes、mtime 和 hash 都屬來源身分；只有新 run ID 或 capture 時鐘不同才可重用。修改數量／成本或觸碰檔案時間均可能要求新 cycle。`skipped_same_inputs` 必須能追到完整舊模型的 exact terminal，不能只看外層 raw exit 0。

重用鍵也保留 WAL 的 mtime。即使兩次 WAL 皆為空檔且主 DB／特徵內容相同，空 WAL 被重新建立仍可使新 run 選擇完整建置；這是保守的重用失配，不能據此宣稱行情已改變。它與前述 snapshot 來源驗證的空 WAL 例外是不同檢查，完整建置仍須通過原容量與來源保護。


<a id="manual-tail-006"></a>
### 2026-10-05 Current-observed 自然研究的去重、標籤與狀態

既有每日推薦學習入口不變。不可變 capture／outcome 的重試可有不同檔案與觀測時鐘；內容、來源、日期、特徵與成本相同時，訓練入口採同一 semantic 樣本 ID，仍逐份再驗原 receipt，從已驗 capture＋outcome 重算 ID 並逐欄比對。來源、特徵、報酬或成本衝突時拒絕，不可改 ID 或取最新檔繞過。成熟筆數仍不足時維持 pending，不建立候選或正式寫入。

此路徑的 `upside_label` 沿用既有整數 bp 契約：Decimal 報酬以 ROUND_HALF_EVEN 取整後，`stock_return_bp > 0` 才為 1。因此極小正價差可能取整為 0bp，標籤為 0；原始買入／賣出價格與證據仍保留。它不是獲利機率，也不等於成本後獲利或超越 benchmark。

`fitted_research_only` 表示研究候選已完成該次 fit，不應顯示成樣本等待 pending；它仍不授予正式訓練、歷史 PIT、自然 promotion 或投資有效性。若重驗失敗，查看 exact capture／outcome 路徑、hash、日期與 cost scenario 診斷，保留失敗證據；不能以回放或受控驗收替代真實自然結果。


<a id="manual-tail-007"></a>
### 2026-10-05 個股研究首屏與資料稽核

從觀察清單／持倉或股票搜尋開啟既有個股研究後，先看「摘要」：本次行情判讀 → 最多三項關鍵依據 → 股票／持倉風險或反證 → 資料／模型限制 → 待驗證條件與下一步。價格與均線使用原 DTO，只有行情日與技術資料日相同才比較高低；日期不同會明示不直接比較。價格、均線與金額以兩位小數顯示，原值與計算精度不變，零值保留為 0.00、缺值仍為破折號。

持倉 `condition_result_missing`、來源缺件與回饋驗證失敗屬限制，不能當成已確認股票風險。現有 WATCH、Health／Exit 規則與動作權限不變。歷史警示保留事件日期與原始內容，在歷史資料稽核查看，不作當期結論；原保存 Advice 的風險也不借用成另一日期的當期風險。

「Rule／ML／歷史」先呈現 ML 估計、來源的期間標籤、基準／成本定義是否提供，以及研究／正式資格限制。−120bp 的成本後基準超額估計不是股價會跌 1.2%、獲利機率或已驗證收益。若來源沒有基準名稱、交易日／日曆日定義、成本情境或數值，畫面明示未提供，不猜填。H5 未成熟顯示簡短條件；blocked／failed／error 顯示驗證受阻，不能一律當等待。

按「展開資料稽核」查看完整 Run、模型／Dataset 版本、三個 SHA、原始目標、估計表、未成熟 H5 欄位、Rule 原理由與保存 Advice 完整來源追溯；按「展開歷史資料稽核」讀回原事件與後續結果。兩者預設收合，故障仍在限制區可見。摘要的稽核亦保留完整風險、限制與來源。來源選擇、當下獨立研究、返回保存 Advice、指定股票分析與保存重開仍沿原精確股票／日期／run／hash 契約，不自動套最新推薦。

ML 稽核展開後按鈕改為「收合資料稽核」，再次按下會收合。只有 DTO 明示當前研究 scope 時才標「當前ML研究」並顯示研究日；保存 scope 顯示「所選保存決策ML研究」與模型事件日，未識別 scope 維持中性標題。下段「歷史保存決策回顧」顯示已讀回的 Advice 或保存分析決策日，未提供所選日期時標示未選定。ML 品質降級呈現來源限制；未提供原因時明示「原因未提供」，不補猜。

此批程式與隔離 offscreen 受控渲染已核對，截圖位於 `output/qa/stock_research_readability_20261005/`；其價格／均線參考原廣達截圖，ML／歷史為測試情境，非真實模型或自然成功。它不替代尚待完成的原生 1477 取消→重試→保存→新程序重開。既有 1000×835 outer／125% 驗收及限制維持接受；1000×800 較小視窗要求仍未達成，不回溯撤銷既有接受，也不新增本批硬關卡。實際 learner→候選→receipt 已於 `0831633c` 通過受控小型工程驗證（180 筆 semantic 樣本；19 passed／1 Windows symlink skipped），含錯來源拒絕；capture／outcome 驗證器使用 fixture，非自然 producer／成熟度或正式模型資格。temporary 候選依 fixture teardown 回收，只保留 JUnit 身份與收據 hash 證據；不重開此工程 gate。


<a id="manual-tail-008"></a>
## 2026-10-05 受控效能診斷入口

日常啟動與九工作區操作沿用本手冊既有步驟，本批沒有新增產品參數或改變推薦／研究來源。維護者需要重跑效能量測時，使用[階段0效能基線](../06_qa/PRODUCT_STAGE01_PERFORMANCE_BASELINE_20261005.md)的固定QA入口；文件列出platform、run次數、列選取次數、label、輸入隔離、結果判讀與拒絕／排錯條件。它只接受既有QA資料，不能指向正式D根或覆寫舊量測目錄；Native窗口另需當次桌面授權。

此次列選取p95只代表高亮與repaint，首次資料查詢／背景工作／關閉仍須分開判讀。階段0觀察到的耗時worker已另以階段1限定修正包驗證，詳見[效能改善收據](../06_qa/PRODUCT_STAGE1_PERFORMANCE_IMPROVEMENT_20261005.md)；仍不能將單次高亮數據解讀為所有互動速度。來源完整性、可用時間與研究／正式資格不因量測或較快載入而改變。

<a id="manual-tail-009"></a>
## 2026-10-05 回測圖表首次開啟與盤勢關閉

依既有流程進入「回測實驗室」，執行回測後先讀摘要，再切至圖表頁查看資金曲線、回撤、報酬與持有天數分布。圖表在首次進入該頁時建立；頁面尚未開啟時收到的結果保留當次資料快照，後來的新結果會取代待顯示資料。再次切回同頁沿用圖表。推薦組合圖表亦在首次使用相關結果頁時建立。參數、回測計算、來源選擇與結果意義維持既有契約。

若單張圖表繪製失敗，頁面顯示錯誤提示，其他圖表仍可顯示；切離後再回到該頁可重試保留的資料。持續失敗時保留提示及該次結果，依既有排錯流程查看日誌，不能把缺圖解讀成沒有交易或績效為零。

背景盤勢更新期間關閉視窗，程式會等待工作執行緒合作退出，再完成關閉；尚未完成的查詢不能顯示為完成。內建 Smart Money、Market Breadth／Relative Strength 的價格 SQL 與批次計算現在可合作檢查取消，進行中查詢取消亦不當成完成或資料降級。關閉當下若worker仍在執行，視窗保留並顯示收尾狀態，完成後自動退出；不需要再按一次關閉。其他區段及沒有取消介面的外部provider仍按原流程等待區段結束，不宣稱所有工作立即取消。重開程式依原流程重新讀取來源，不沿用前一輪盤勢快取；日期、來源缺件、PIT 與模型資格限制照常顯示。驗證範圍、重試與未完成項目見[SQL取消收據](../06_qa/PRODUCT_STAGE1_SQL_CANCELLATION_20261005.md)。


<a id="manual-tail-010"></a>
## 2026-10-05 UX02 共用狀態判讀（有限入口）

入口仍為今日重點／盤勢、我的持倉、推薦分析、個股研究與 Research Console；沒有新增參數或執行方式。先看摘要狀態，再到既有來源、系統限制、ML 稽核及診斷區查看原始碼、資料日、研究日與結果身份。持倉健康的系統資料狀態與 HOLD／WATCH／REDUCE／EXIT 等股票／持倉判斷分開閱讀；資料缺件不能推論賣出。

| 摘要文字 | 判讀與下一步 |
|---|---|
| 資料缺件／來源缺件 | 查看具名缺件及來源；不補造數值，也不直接判股票高風險。 |
| 品質降級 | 已有內容仍可按限制研究；查看受影響來源及原始診斷，不當成整份都不可用。 |
| 載入中／載入完成／已取消 | 只描述本次載入；不證明行情最新或方法有效。 |
| 尚未到期／休市跳過 | 只在來源明確給出等待／休市狀態時顯示；pending 只譯待確認，未提供原因不能猜成自然成熟。 |
| 研究完成 | 只描述研究執行完成；不代表已獲正式資格。 |
| 正式資格未具備（研究限定） | 沿既有研究用途使用，不能當正式策略／下單核准。 |
| 執行錯誤／驗證未通過 | 依原始錯誤與驗證訊息排錯；驗證失敗與執行例外分開，不自動改成等待。 |
| 未知／未識別原碼 | 保留原碼查來源，不把未知畫成正常、零值或安全。 |

當期研究日、資料日、歷史事件日與所選保存決策日沿既有欄位分別標示；狀態翻譯不重綁日期／run／來源。不符合日期或來源身份仍拒絕。若畫面顯示「報告部分載入」，可以閱讀已提供區塊並查看缺件；若顯示真實錯誤，保留訊息後修復具名來源，不能以重新命名狀態授予資格。部分入口維持既有專用詞彙，這次沒有全頁全狀態改版。測試與真實唯讀離屏證據見 [UX02 收據](../06_qa/UX02_SHARED_STATUS_VOCABULARY_20261005.md)。

<a id="manual-tail-011"></a>
## 2026-10-05 UX16 唯讀研究來源契約

此preflight只核對來源。個股頁實際使用的close／MA20／MA60共用特徵與暖機觀察另見本文末UX18補充。

進階唯讀入口為 `scripts/inspect_current_observed_source_contract.py`，用於共用特徵／每日快照實作前核對來源，沒有新增主UI按鈕。先依 `TWStockConfig` 確認實際SQLite位置，再明示決策cutoff、臺北日期、讀取窗口與研究股票範圍。以下是日期化範例，使用時須改為實際截止時刻與來源，不可把範例當今天的資格：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_current_observed_source_contract.py --db-path D:/Min/Python/Project/FA_Data/sqlite/twstock.db --source-ref configured-main-daily-prices --decision-cutoff 2026-10-05T16:00:00+08:00 --as-of-date 2026-10-05 --window-trading-days 3 --symbols 2382 1477
```

| 參數 | 意義與限制 |
|---|---|
| `--db-path`／`--source-ref` | DB必填，使用mode=ro與query_only；ref為具名參照，不代替內容hash。省略ref會以絕對路徑與表名標識。 |
| `--decision-cutoff`／`--as-of-date` | 必填含時區ISO時刻與YYYY-MM-DD；日期須等於cutoff轉Asia/Taipei後日期，不接受未來cutoff。交易日不是官方availability證據。 |
| `--window-trading-days` | 必填1–60，指來源表最近N個不同交易日；不等於個股完整交易日曆或指標暖機。 |
| `--symbols` | 明示cohort分母；省略則分母unknown，讀到的股票數不冒稱全市場universe。 |
| `--source-pin-file`／`--expected-scope-identity`／`--expected-rowset-sha256` | 可選前次JSON source pin、股票範圍identity與scoped內容hash。任何不相符都拒絕，不借用其他日期／版本。 |
| `--feature-spec-file` | 可選JSON list或`{"features": [...]}`，每項具name、source_table、columns、window_sessions；可加version、unit、warmup_sessions。只記錄呼叫者宣告，不計算特徵或證明暖機；省略保持unknown。 |
| `--company-classification-csv` | 可選當期公司分類，記錄實讀rowset與時鐘限制；不建立歷史產業effective intervals。 |
| `--benchmark-evidence-file` | 可選宣告identity、source_ref、window_start／end；本工具不核驗benchmark，verified保持false。 |
| `--output` | 預設只輸出stdout；可選repo `output/qa/`下新的`.json`，create-only，不覆寫既有檔或正式資料。 |

讀回JSON後，先看`status`與`blockers`，再看source的實際scoped rowset hash、scope分母／missing_symbols、每檔窗口、availability、features與benchmark。`observed`只表示研究來源已觀測；`partial`保留具名缺件／重複／晚到原因；`rejected`不可當穩定來源，CLI返回2。明示股票全數出現不代表每檔窗口齊全、全市場完整、暖機通過或正式資格。晚於cutoff或無有效時鐘的列不進cutoff-screened子集；無availability仍可讀當期研究，但PIT、正式訓練與published_snapshot保持false。

遇`source_schema_read_failed`／`source_query_failed`，核對路徑、schema與執行環境權限，不自動下載或重建DB；`source_changed_during_read`表示來源／sidecar身份變動，保留收據並在來源穩定時另次讀取；錯日期／scope／rowset pin要回到原保存來源核對，不改pin繞過。JSON檔已存在時換新QA檔名；不清理原件。相關實作、定向測試與Native畫面來源見 [UX16限定收據](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。

<a id="manual-tail-012"></a>
## 2026-10-05 UX18 共用日特徵與個股觀察

此為預設live投影；明示隔離已發布快照的生產／讀回入口另見本文末UX19。

入口仍是「個股研究」或持倉／觀察清單下鑽。選股票及既有來源／決策日後，正常載入報告即可；沒有新增參數、按鈕或writer。首屏結論與三項依據讀同一份共用close／MA20／MA60研究快照，呈現收盤高於、低於或等於均線；equal表示未符合「高於」條件，不代表賣出或風險評級。

必要暖機以最後連續有效OHLC計算：MA20需20筆、MA60需60筆。缺值／無效範圍中斷連續段，不跳過缺口。資料日與技術日不一致、來源品質／身份不完整或暖機不足時，畫面顯示「尚無法判讀」，研究理由保留具名原因；一項未知不遮蔽另一項可讀觀察。原table均線值不重算，RSI／MACD／ADX、Advice與排名沿既有輸出。

進階稽核可從報告DTO的 `shared_daily_features` 查看contract版本、snapshot／input hash、股票scope、decision／market date、TWD/share單位、來源fingerprint、warmup_required_count／observed_count及conditions三態。cache僅此service最多4筆；相同輸入復用，來源內容／日期／scope／版本變化即重新投影，不沿用舊身份。舊DTO沒有該欄位時保持原呈現。

`sufficient_observed_prefix`只證明有限SMA的必要觀測窗口，官方交易日曆與available-at仍unknown、historical_pit_eligible=false；不證明歷史PIT、producer公式等價、遞迴EMA暖機或正式模型／勝率。首屏只是研究技術觀察。若不足20／60筆，核對實際末段OHLC及缺口；若日期／品質不符，核對所選來源，不能補假時鐘或略過guard。投影讀取故障保留原錯誤且條件未知，正常取消不變成成功。工程驗證與仍待項目見[QA新章](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md#最新延伸ux18-既有日特徵的實際研究-consumer)。

<a id="manual-tail-013"></a>
## 2026-10-05 UX18 兩條固定研究方法契約

入口沿用「推薦分析 → 每日研究條件」與同源個股研究，仍只有收盤價高於既有 MA20、收盤價高於既有 MA60 兩條觀察；參數固定為20／60筆窗口，不提供任意改窗口或新公式。AND／OR、符合／不符合／未知及原資料來源操作沿用；高於只是方向性描述，equal 仍不符合，不代表已驗證 alpha、買進／賣出或勝率。

已發布研究快照與報告 DTO 的進階稽核資料會保存方法 ID、家族、版本、固定參數、方向、必要欄位、決策日與當股可判讀資格／unknown 原因，並參與快照身分及 manifest 綁定。資格只描述本研究觀察的輸入是否足夠；暖機、官方可得時間、交易日曆、歷史 PIT、模型與正式推薦資格仍各自判定，不因本契約存在而升格。

方法／版本／參數／日期或雜湊不符時停止快照讀回，個股保留未知與具名錯誤，不轉用 live 值或保存推薦。舊版研究 manifest 缺少完整方法契約時拒絕讀取；在「每日研究條件」保留原股票母體與條件後，明確按更新，才能由既有來源在隔離研究區重新發布新契約。單純重讀／篩選不會升版或寫入，舊不可變產物保留；若來源、容量或新候選核驗失敗，原 latest 不被成功結果替代。

原排名／強弱與市場共用快照入口尚未接入此契約；沒有原排名的研究結果不能推造分數。驗證與實際完成範圍見 [UX18 方法綁定限定收據](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)，Backtest 18.62%／20% 未達與歷史 PIT／真人驗收限制維持。

已是 v2 卻出現錯方法／版本／參數／hash，更新仍會保護原件並拒絕，不能反覆重試或刪 store 當作修復。維運須先核對程式與來源，再以既有 CLI 在新的隔離研究 `--output-root` 明確重產；合法方法版本改版也不復用舊 v2，現包未提供 v2→v2 自動遷移。固定 window 改成21等不相容參數即使換新根也拒絕，不以 metadata 改寫 MA20／MA60 實際公式。

<a id="manual-tail-014"></a>
## 2026-10-05 UX19 隔離研究快照生產與讀回

進階入口是 `scripts/produce_daily_market_research_snapshot.py`，用既有SQLite唯讀資料在repo output明示隔離子目錄產生研究快照；沒有新增主UI按鈕或Windows排程。依TWStockConfig確認真實DB，選1–16股、cohort名稱及含時區cutoff，再執行。以下為日期化範例，應改為實際截止時間與隔離根，不把範例當當前來源資格：

```powershell
.\.venv\Scripts\python.exe scripts\produce_daily_market_research_snapshot.py --db-path D:/Min/Python/Project/FA_Data/sqlite/twstock.db --output-root output/qa/my_daily_snapshot --cohort-id research-2382-1477 --decision-cutoff 2026-10-05T21:00:00+08:00 --symbols 2382 1477 --read-stock 2382
```

| 參數／結果 | 意義與限制 |
|---|---|
| `--db-path` | 既有來源，mode=ro／query_only；不重抓資料或寫正式DB。最低price／MA schema不合即拒。 |
| `--output-root` | 必須repo output內明示隔離子目錄；不能repo output本身、來源DB或正式根。保存精簡immutable objects／manifests，latest最後原子切換。 |
| `--cohort-id`／`--symbols` | 明示研究母體ID與1–16不重複股票；完整只指此declared cohort，不是市場universe或正式篩選資格。 |
| `--decision-cutoff` | aware ISO時刻，轉Asia/Taipei日期；未來cutoff拒絕。交易日可讀不表示當時官方available-at已核驗。 |
| `--read-stock` | 可選cohort內一股，發布後由既有個股read_report核驗讀回，JSON附consumer與consumer_status；失效回傳2，不改走live假裝快照成功。 |
| reused／recomputed | 相同來源／日期／scope／版本重用核驗artifact；只有失效股票再投影原MA值。無更新不新建發布時間或identity。 |
| capacity_preflight | 實寫前實測容量，保留200GiB及新增／暫存／累積預算；不足停，不自動清理原資料／收據。 |

本包producer僅發布明示cohort完整版本；任何來源DTO載入或投影失敗即具名停止，保留上次latest。reader另能核驗具名partial research，不能把這項能力解讀為producer會自動略過缺股。

研究consumer可在隔離設定明示 `StockResearchReportReadService(..., daily_market_snapshot_root=隔離根, daily_market_snapshot_cohort_id=同cohort)`；兩者須一起提供。既有read_report來源與日期照原操作，新增 `shared_daily_features.readback` 保存已核驗manifest身份／完整性。沒有設定時沿live投影；此包未切換日常App預設，也未部署正式排程。

錯date／stock／scope／schema／版本／hash，或當前來源修訂造成input不一致，都拒絕快照並保留錯誤／unknown；核對實際DB、cohort／日期與來源後在新run重建，不改pin或減reserve求通過。writer失敗或中斷時上個latest仍可核驗，按舊manifest date／hash明示查看，不能標成今日成功。保留失敗／未完成診斷，不執行永久清理。`complete_declared_cohort`不代表MA暖機全過；仍查看每股warmup及condition unknown理由。

此為current-observed research-only；官方可得時間／calendar completeness保持unknown、historical_pit_eligible=false。不授benchmark、自然成熟、正式訓練或ML資格，沒有新增策略／公式／排名。版本、原子發布與實跑限制見[既有QA收據UX19新章](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。

<a id="manual-tail-015"></a>
## 2026-10-05 UX04／05 每日研究條件與同源個股

日常入口為「推薦分析」內的「每日研究條件」來源頁；既有推薦與策略研究保留原入口及資格。這份研究名單只涵蓋明示股票，不是全市場推薦或完整交易策略。來源區與狀態列先核對研究日、實際資料日、cohort與條件，不以ML候選或離線研究升格推薦。

1. 輸入1–16個不重複股票代碼與cohort名稱，選臺北研究日期／時間。預設是明示2382／1477小型cohort，可編輯；不會默默截取全市場前N名。
2. 「重讀已發布快照」只讀目前版本。初次缺快照或來源已修訂時，狀態清楚列出原因；明確按「更新研究快照」才產生這個小cohort的新版本。日期／時間須含臺北語意且不在未來；歷史日期仍是current-observed資料研究，不證明當時已可得。
3. 勾選「收盤高於MA20」及「收盤高於MA60」，選AND（全部符合）或OR（至少一項符合），再用全部／符合／不符合／未知查看。這些操作只查已發布條件，不重跑策略或全量計算，亦不改原排名。
4. 查看每股資料日、兩條三態、整體判斷及why／why-not。未知因暖機／來源缺件而保留；OR有一項符合可以整體符合，其他未知仍列示，不能把未知當反對證據或負樣本。
5. 選股票後開啟個股研究。報告使用相同manifest／stock／decision date／source與snapshot身分，支持與反證採同組條件。上一檔／下一檔沿原研究清單；資料日按當前股票更新。重新載入核驗原pinned版本，不偷換另一份最新推薦。
6. 返回來源清單會保留原篩選與選取，並要求相同manifest。清單已更新時，會提示原來源已變動，不能用同股替代；核對新來源後再明確下鑽。

預設研究快照保存在repo `output/research_snapshots/daily_market`，與TWStockConfig正式資料／output根分開。僅保留精簡不可變artifact與manifest，latest最後原子切換；上限16股／120列、64MiB／4096項、200GiB reserve與既有byte budgets維持。不足停止、不降reserve、不自動刪原資料或證據，沒有新增正式排程。

排錯：無快照時明確更新；股數／格式／未來時間不合時修正輸入；來源修訂或schema／hash不一致時重讀會拒舊來源，返回研究名單確認DB及cohort後明確更新。資料不足時查看每條未知原因與必要20／60觀測暖機，不略過guard。失敗保留舊manifest/date可追溯，畫面不能將舊版本說成新發布成功。取消／關閉只合作停止本頁工作，等待worker退出，不終止使用者其他程式。

本包仍research-only、available-at／calendar unknown、PIT=false；不授自然模型／勝率／正式推薦資格。限定驗證與完整待辦見[日常研究flow QA](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md#最新延伸ux0405-日常研究名單與同源個股)。
<a id="manual-tail-016"></a>
## 2026-10-05 UX13／18 具名研究母體盤勢與指標排序

入口為「市場探索 → 研究母體盤勢」，並可按「開啟同來源研究名單／明確更新」進入「推薦分析 → 每日研究條件」。盤勢接收名單已驗證的同一發布快照，不另查一份不同日期的行情或重算方法；首次切入只讀既有 latest。先在名單設定具名 cohort、最多16檔股票、決策日與截止時刻，再明確更新，盤勢便同步相同 manifest／方法契約身分。

名單保留兩條固定 close 高於 MA20／MA60 的 AND／OR 與三態篩選。新增排序依據為股票代碼、行情資料日、已保存 close／MA20／MA60 值及升冪／降冪；Decimal 值精確排序，未知數值固定置尾，同值以股票代碼穩定排列。完整 MA 數值可橫向捲動查閱，來源／方法完整身分保留提示，摘要直接列日期、母體與三態。這些指標排序與原強弱排名分開。舊feature快照未保存原排名，無相容排名來源時仍未知；新獨立排名來源見下方UX18章節。畫面列序、價格高低或條件符合數都不是綜合投資分數或勝率。

盤勢按每一固定方法分列符合／不符合／未知人數，分母固定為完整 declared cohort，名單篩選不改分母。合法 partial 的未發布股票計入未知，並列出缺件代碼；名單只提供有已驗證 artifact 的可開啟股票，不偽造缺件個股上下文。各股行情資料日與決策日分開呈現，來源／方法身分可核對；各方法統計不合併成全市場廣度或投資強弱分數。

由盤勢開啟名單，選股後開個股研究，切股、重載、返回均沿同一 manifest。重讀只核對既有快照；來源修訂、日期／hash 不符或舊 schema 拒絕時，盤勢與名單一起清空結果並保留未知／錯誤提示。只有明確更新成功、verified reader 讀回後才恢復兩頁；舊 immutable artifact 保留。v2 方法契約變更仍無自動遷移，處理方式沿下節方法契約維運限制。

此入口限定具名小母體當期研究，不宣告全市場、歷史 PIT、官方 availability、正式推薦、alpha／ML資格或真人驗收；原大盤指數、原強弱頁的獨立來源未改成此母體。驗證與工程完成範圍見 [共用投影收據](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。


<a id="manual-tail-017"></a>
## 2026-10-05 UX03／06／13 原研究收藏與返回

入口為「推薦分析 → 每日研究條件 → 收藏此研究」，保存到既有「我的觀察／觀察清單」。先選取有已核驗 artifact 的股票，再核對確認框中的原研究日期、cohort、條件與來源；取消不保存。書籤固定原 manifest identity／hash、快照根、資料日、方法契約及 hash、完整 declared cohort 與查詢／排序偏好，不是持倉或第二份 ledger。

在觀察清單選取「每日研究書籤」列，開啟個股研究會讀原固定來源。上一檔／下一檔只在同來源與同查詢的已保存書籤中切換，每股使用自身 bookmark identity；返回定位原書籤，不能用同代碼的手動列、Advice列或其他研究書籤替代。完全相同書籤重複收藏不新增、不覆寫；不同來源／查詢的同股書籤各自保留。重開程式仍讀回原書籤，不換為今天。

「以最新來源另開研究」是獨立明確操作，只讀已發布 latest，不更新原書籤、不啟動快照 producer。想產生新版本須自行到每日研究頁核對後明確更新。原來源缺件、修訂、方法／schema／日期／hash不符時，保留原身份並拒絕比較，查錯後另開研究；不補零、不改為手動或最新來源。

移除前可取消；研究書籤採 exact ID 移除，其他同股列保留。「還原剛移除的研究書籤」用原 payload／位置恢復，不授新資格。還原 token 僅保存在目前程序，每次按鈕回復最後移除的一張書籤；JSON 與SQLite原儲存邊界沿用，不自動遷移真實清單。書籤是個人研究工作流，不改 evidence／策略生命週期，也不授投資分數、自然 ML、正式資料或歷史PIT資格。

限定驗證與剩餘工程範圍見[收藏原來源 QA](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。

現有「升級觀察清單儲存」可處理已嚴格驗證、ID 不重複的同股研究書籤；一般列仍保留原重複保護。升級是明確操作，JSON 原件保留，書籤 extension 不另建第二份 ledger。本包只用隔離 fixture 驗證這條路徑，沒有升級使用者的真實清單。


<a id="manual-tail-018"></a>
## 2026-10-05 UX04／05 固定方法預設與候選摘要

入口仍為「推薦分析 → 每日研究條件」。先唯讀載入已發布快照，再選預設並按「套用預設」；只選下拉項不改查詢。初始「全部觀察」沿用兩條 MA 的 AND／全部，不自動蓋過手動條件、重讀、原來源返回或收藏查詢。

| 預設 | 查詢條件 | 顯示狀態 |
|---|---|---|
| 全部觀察（預設） | MA20、MA60，AND | 全部已發布列 |
| 任一均線之上 | MA20、MA60，OR | 符合 |
| 收盤價高於 MA20 | 固定 MA20，AND | 符合 |
| 收盤價高於 MA60 | 固定 MA60，AND | 符合 |
| 待檢視（未知） | MA20、MA60，AND | 未知的已發布列 |

手動勾選方法、AND／OR或顯示狀態仍可自由組合；精確等同既有預設時標明其名稱，其他組合標「自訂查詢」，不反向重設控件。沒有相容排名來源時，「原始強弱排名」停用；新獨立排名來源見下方UX18章節。MA未符合不代表弱勢、投資風險評級或勝率。排序仍是已保存股票代碼／資料日／close／MA20／MA60的Decimal指標值；未知置尾，原資格不變。

候選摘要以完整declared研究cohort為固定分母，分列已發布、缺件、符合、未符合、未知、目前顯示及因篩選隱藏人數。缺少artifact的股票算未知／缺件，不捏造可開列；「顯示未知」可以是零列，同時摘要仍有缺件未知。篩選隱藏只描述本次顯示條件，附原列原因，不代表股票被投資策略否決。畫面列出少量具名缺件、未知及排除原因，提示保留完整清單。

選取一列可看支持、明確未符合的反證、資料未知限制與決策／資料日期。缺件不當成反證，沒有的證據寫未提供；必要MA20／60暖機各為20／60有效觀測，固定參數不接受任意窗口。完整方法契約與來源identity保留提示／既有稽核入口。

套用、手動篩選及排序只查目前已核驗快照，不重讀來源或啟動producer，不改snapshot／date／method／qualification；選中股票仍可見且身份相同時保留選取。收藏保存實際條件／ANDOR／filter／sort，原來源返回仍按exact identity。沒有快照時套用停用；先重讀，缺件核對來源，只有自己明確更新才沿既有小cohort producer，不能用預設繞過guard。

本包僅背景tests及offscreen驗證，新增Native鍵鼠／縮放／跨頁互動仍待下一個使用者桌面時段；不能用offscreen替代真人驗收。research-only、available-at／calendar unknown、PIT=false與ML資格限制保留，工程待辦見[既有QA收據](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。


<a id="manual-tail-019"></a>
## 具名有界研究母體（UX16／18，2026-10-05）

每日研究清單、研究母體盤勢與候選摘要共用已核驗快照中的母體設定：ID、版本、截至日、設定來源 SHA256、納入股票、排除股票與理由。設定分母可為未知；發布涵蓋率的分母是設定納入檔數，篩選隱藏不改變它。設定排除與查詢篩選隱藏分開呈現。這是明確研究批次，不能當作全市場或完整合格投資母體。

來源由隔離 CLI 明確傳入 `--universe-config`；以設定內的納入股票作為唯一明示來源（不得同時傳 `--symbols`）；`--cohort-id` 可省略，明示時必須與設定 ID 相等，最多16股、每股最多120列。設定是研究用途，不授予歷史PIT、資料可用性或推薦資格。現有兩個MA方法與未知原因依原快照計算。無設定的舊快照仍可讀為宣告cohort，母體設定來源與原始分母保持未知。

已綁設定的快照在讀回時重新核對設定檔內容雜湊及截至日；設定刪除、修改、成員重複或不一致會拒絕來源。請保留原設定檔；需要新成員時建立明示新版本並重新發布隔離來源。圖形介面的手動更新不得把已綁母體默默降回無設定cohort，請用相同設定的隔離CLI。錯誤會保留既有來源，不能以畫面列數推估缺失母體。

原計畫的「原排名」指既有StockScreener本日／本週價量強弱公式。沒有相容不可變排名來源的舊快照維持未知及停用；已發布來源的操作與限制見下方「原引擎日／週排名發布與讀回」。MA、價位或其他推薦排名不能替代此來源。

本包僅背景及offscreen驗證，不代表Native鍵鼠、縮放、全App啟動或真人驗收；正式資料庫、真實書籤與模型registry不寫入。


設定檔範例（自行明確決定批次成員，檔案不超過32KiB；納入與排除合計最多32股）：

```json
{"schema_version":"daily-market-research-universe.v1","universe_id":"my-research-batch","version":"v1","as_of_date":"2026-10-05","method":"daily-market-close-ma.v1","included_stock_codes":["1477","2330","2382"],"excluded_stock_codes":[{"stock_code":"2317","reason":"本次研究批次明示排除"}],"population_count":4,"scope":"bounded_research_cohort","research_only":true,"complete_fixed_cohort":true}
```

`method` 是現有close／MA20／MA60觀察的相容性標記，並非原強弱排名方法。`as_of_date` 須與明示截止時間的台北日期一致，截止時間不得晚於執行當下。`version` 是批次設定版本；`population_count` 若已知必須等於納入與排除合計，未知用JSON `null` 且 `complete_fixed_cohort=false`；此值不是全市場數量。排除每股須有理由，重複或與納入重疊拒絕。`research_only` 必須為true，固定scope不得宣稱全市場或正式資格。

操作：保存設定 → 使用隔離output發布 → 檢查JSON結果的status／error／capacity → GUI設定同一隔離snapshot root，按「重讀已發布快照」 → 在名單／母體盤勢核對ID、截至日、納入分母、缺件及三態。CLI範例：

```powershell
.\.venv\Scripts\python.exe scripts\produce_daily_market_research_snapshot.py --db-path "<TWStockConfig的db_file>" --output-root "output/qa/my_research_batch" --decision-cutoff "2026-10-05T23:59:59+08:00" --universe-config "output/qa/my_research_batch/universe.json" --read-stock 2382
```

output必須為repo `output/` 的明示隔離子目錄。`--read-stock` 是納入股票中的可選讀回驗證。CLI不修改主要App預設root；整合測試／有權限的配置呼叫端須明示 `snapshot_root`，不要把隔離QA來源當正式來源。保留200GiB容量安全保留、每次新增／暫存各8MiB與既有retention界限；阻擋時不降低保留政策或自動刪除資料。


<a id="manual-tail-020"></a>
## 原引擎日／週排名發布與讀回（UX18，2026-10-05）

原排名來源獨立保存，綁定原研究快照完整manifest hash、母體設定、截至日、原引擎檔案hash／版本／參數及每股原始輸入指紋。日／週與強／弱是四個不同查詢身份；切換只讀取對應已發布來源，不跨期間比較或產生排名。舊feature快照與收藏內容不改寫；找不到對應排名時顯示不可用，不拿MA或價格排序替代。

原引擎輸出的「評分」實際是Top／Bottom舊標籤，百分比不可按一般「前幾％」或勝率解讀；內部數值評分已被覆寫，發布器不反推數值分數。顯示原生排名與該標籤，是明示研究母體中的相對排序，不是勝率、預期報酬、風險級別或正式買賣建議。日比較前一筆觀測；週在至少6筆時比較倒數第6筆，只有3–5筆時原引擎比較倒數第3筆，實際比較日期與窗口保留在來源明細，不將fallback冒稱固定完整一週。量能基準按原引擎先前20／5或更少筆既有規則保存。

操作：先備妥具有明示母體設定的已發布研究快照 → 以同一readonly DB與截止資料執行隔離publisher → 檢查published／unchanged、容量與readback → 在名單選擇日／週及強／弱 → 核對母體盤勢同一rank來源ID → 有相容來源時才選原排名排序。篩選只隱藏行，不重新編號排名或改變原eligible母體；原引擎未排名的股票顯示未知並列明missing rank，不補排名。候選摘要分開解釋MA條件與原排名。

CLI讀取既有資料，最多16股／每股120列，保留200GiB安全容量、每次新增及暫存各8MiB、64MiB／4096筆retention界限。沒有全市場收集、訓練、排程部署或正式DB寫入。排名output使用repo output明示隔離子目錄，與feature source可分開，避免改動舊來源inventory。來源修訂、日期／method／母體／hash不相容或中斷會拒絕發布或讀取，保留原指標來源；日／週來源缺件各自保持未知。

原排名收藏已另存明確 v2 身份，操作與錯來源排錯見下方「原排名收藏與個股原來源回看」。舊非排名 MA 收藏仍沿原 v1 語意，不能靜默換成原排名或股票代碼排序。Native 鍵鼠／縮放／跨頁互動仍待桌面時段驗收。

CLI範例（僅發布已有 feature 來源的對應模式；需要四模式時各自明示執行）：

```powershell
.\.venv\Scripts\python.exe scripts\publish_original_stock_ranking.py --snapshot-root "output/qa/my_research_batch" --ranking-root "output/qa/my_research_batch_ranking" --db-path "<TWStockConfig的db_file>" --cohort-id "my-research-batch" --decision-date "2026-10-05" --period day --direction strong
```

`--ranking-root` 是獨立排名根目錄；consumer 須明示相同 `original_ranking_root`，未配置時只查 snapshot root 下的 `original_rankings`，不自動搜尋其他QA來源。`--period` 可用 day／week，`--direction` 可用 strong／weak；引擎參數固定保存，不接受任意改公式。舊標籤與缺少數值評分是來源限制，若要更正其口徑需另做原引擎方法版本決策。完整證據見[原排名發布 QA](../06_qa/UX18_ORIGINAL_STOCK_RANKING_PUBLISHER_20261005.md)。

<a id="manual-tail-021"></a>
## 原排名收藏與個股原來源回看（2026-10-05）

入口：每日研究條件 → 核對日／週及強／弱原排名來源 → 選股 → 開啟個股研究 →「收藏此原排名研究」。確認原決策日、比較日期、原名次／舊標籤、母體及來源後保存到既有觀察清單，取消不寫入。也可從每日研究頁收藏相同來源。

新rank收藏格式保存publisher manifest hash／身份／根目錄、parent feature來源、期間方向、實際比較窗、原母體／方法參數、排序與選取股；同source/query/stock重複不增加，切mode另存不同研究身份。舊非rank格式保留原語意，不自動升級或改hash；缺少可信原排名不能保存為新rank研究，不能退為代碼排序。

重開程式後，在觀察清單選取原研究 → 個股報告讀原immutable排名和原feature → 返回精確原收藏。後來名單切mode、排序或發布新結果不改原收藏。Top／Bottom照原publisher標籤顯示，不反推不存在數值score或當作勝率。週只有3–5觀測的原fallback必列實際比較日期及非完整週；不改算法。

來源缺件、舊版不支援、stock／日期／hash／母體／方法不相容或來源修訂時，原排名不可用並列出原因；其他可讀行情不代表原排名有效。可明確另開最新個股研究，不覆蓋舊payload／證據，也不啟動producer。保留原snapshot/rank根目錄與母體設定原檔，查錯後另存新版本。

所有排名限明示有界研究，非全市場、正式推薦、numeric score、勝率或歷史PIT。新工程先驗backend/offscreen；Native鍵鼠／縮放／跨頁及真人驗收仍待桌面時段。隔離QA清單不等於已遷移用戶真實清單。


<a id="manual-tail-022"></a>
### 2026-10-05 每日研究鏈阻塞修正

- **容量**：排程入口維持整數 bytes 預算。正式 raw 本輪需求為持久 35 GiB＋暫存 40 GiB＋執行後餘量 20 GiB；研究 cycle 則為實際 DB/WAL 快照上限＋持久 2 GiB＋暫存 2 GiB＋餘量 20 GiB。更大的顯式餘量仍被尊重；未知用量或空間不足仍阻擋。預設可用空間不等於已成功建置、可連跑若干日或正式資格成立。既有 200 GiB 收據依原政策完整驗證，不改寫舊失敗。
- **Decision Evidence**：父 wrapper 取得 canonical heavy-chain reservation 後，對 Evidence child 登記一次性授權並傳遞既有驗證 lease。獨立 CLI 仍自行取得鎖；偽造 marker、鎖根錯誤或失效 owner 一律拒絕。snapshot 成功仍不能替代 Evidence stdout/summary。
- **G6 snapshot**：以 DB/WAL 實際 bytes/SHA、data_version、journal mode 與修訂證據驗證同次來源。空 WAL 與不存在的 WAL 不含交易頁，讀取引起的 mtime 改變不單獨拒絕；非空 WAL、DB 內容或 revision 改變仍停止。真正不一致時另存 snapshot_failure.json 的前後 pins，原成功 receipt 不產生。watchlist/holding 輸入仍保留原 mtime/hash 檢查。
- **G9／Bank**：須重新取得合格同日 G6 來源後才可恢復技術來源消費；舊 blocked run 不會被回溯改綠，snapshot 或獨立來源成功不代替學習成功。
- **Paper EOD**：具名「sector archive 未在決策前保存」且 retryable=false 的歷史拒絕，僅在 source、candidate、receipt 完整驗證且無 ledger 後視為 rejected 終態，保留於 queue.resolved_historical_receipts。已驗證且未選來源的 queue 診斷不建立 pending identity；原始問題收據仍逐筆檢查。未知 blocker、混合身份錯誤、遭修改的 candidate 或真正 pending 的錯過會期仍阻擋。不得補造舊 entry、追認成交、刪除舊收據或授予 formal credit。
- **排錯**：先看 exact immutable receipt 與 stdout，再看 snapshot_failure.json 或容量 required/free bytes。舊的 10/5 failed receipt 代表當時失敗；修正是否於自然排程生效，要以修正後新 run 的證據驗收。


<a id="manual-tail-023"></a>
## 2026-10-05 研究快照儲存唯讀診斷與發布復原

執行 ` .\.venv\Scripts\python.exe scripts/diagnose_research_snapshot_storage.py --snapshot-root <feature根目錄> --rank-root <rank根目錄> --watchlist-dir <實際清單檔所在目錄> `。這只盤點檔案與來源參照；不啟動 producer、不修改收藏或資料庫、不刪除檔案，也不提供清理批准。

參數：`--snapshot-root` 必填；`--rank-root` 省略時用 feature 根的 `original_rankings`；`--watchlist-dir` 應指向含完整 JSON 清單／SQLite extension 的實際 ledger 目錄，例如隔離 case 的 `watchlist/`，不能只傳再上一層。未提供或來源不完整時仍可看已讀取 bytes，但 references_complete 為 false、候選停用。`--watchlist-inventory-complete` 必須由操作者明示已列齊全部 current／history 清單來源；預設不宣稱完整，即使已讀完所提供目錄。隔離 ledger 不能代表正式全部清單，請省略此旗標。`--output` 選填且只接受 repository `output/qa/research_snapshot_storage_governance/` 下的收據；請用新名稱保留歷次結果。

結果判讀：`scan_complete` 表示有界檔案盤點完成；`references_complete` 表示所提供的完整清單來源與 hash／identity／parent 參照一致，僅相對於該明示目錄，不保證掌握別處收藏。既有所有 manifest 及其 objects 都保留；dry_run_candidates 只列無 manifest 參照的 object 或暫存供審閱，automatic_action 永遠 none，cleanup_authorized／permanent_delete_enabled 永遠 false。候選不等於安全刪除名單。不要把缺件、未知 schema、參照不完整或過量掃描當成清理理由。

限制：保留與掃描合計預算 64 MiB／4096 entries、讀取驗證 64 MiB；每批新增／暫存峰各 8 MiB，單檔亦有 schema 對應上限。中央容量 reserve 取當下 shared policy，收據記錄實際 bytes／GiB 與來源；within_budget 是此預檢結果，不是來源資格或 writer 授權。診斷不替代 verified reader、正式 DB source revision／PIT 或投資方法驗證。CLI exit 0 只代表 scan_complete，仍須讀 references_complete、issues、alerts 與 capacity。

成長推估目前 CLI 沒有自然歷史樣本時標 insufficient_history，不產生 7／30／90 日數字。API 可提供最多 90 筆 timezone-aware bytes 樣本與整數單批新增量；推估僅線性容量觀察，不是自然 producer 或模型成熟證據，盤點不完整時不推估。

排錯：缺根、hash／identity 不符、未知版本、symlink／Windows junction、writer lock／WAL／SHM／staging sidecar、未知清單子目錄或超預算時，查看具名 issues 並補正明示來源後重新診斷；不要移除舊快照或清單來取得 pass。容量不足先停 writer，再由使用者選擇儲存／政策方案，禁止診斷自動釋空間。

發布中斷後可使用同一明示來源與方法重試；feature 與 ranking 使用 OS lock、不可變 objects／manifest 與原子 latest 指標。指標替換前故障保留舊完整版本，替換後完整新版本可讀；舊 pinned 收藏仍按既有 source guards 檢查，過期／錯來源仍拒絕，不藉重試授予資格。並行發布 busy 或 pointer_changed 需等待同根程序完成後重新讀取，不覆蓋指標。參見 [本批驗證](../06_qa/UX19_STORAGE_AND_PUBLICATION_RECOVERY_20261005.md)。

可另執行 ` .\.venv\Scripts\python.exe scripts/qa_isolated_app_startup.py --output-root output/qa/<新的隔離目錄> ` 做空資料、真實 MainWindow 的 offscreen 最小啟動／關閉；只允許隔離配置，Python audit hook 不是 OS 級完整監控，也不代表 Native／正式資料／真人驗收。


<a id="manual-tail-024"></a>
## 2026-10-05 每日研究名單：入選歷程（UX09 有界切片）

入口仍是每日研究名單。唯讀載入已發布快照後，背景核對既有歷史；清單的「入選歷程」與候選／選中個股摘要顯示本次新入選、持續符合、重新入選、未再符合或無法比較／歷史不足，並列前次決策日與理由。選中列的提示保留觀測及來源身份，供稽核回放；首次可見不等於自上市首次入選。

選擇 close_above_ma20／close_above_ma60 和 AND／OR 會比較該固定查詢的完整觀測。排序、搜尋、顯示符合／未符合／未知只改畫面，不重讀同查詢、不產生新的歷程事件；明示「重讀已發布快照」重新核對來源。原始排名保留原引擎字串與獨立排序，不將名次變動當 MA 入選／退出，不新增 TopN 或數值分數。

只有相同方法／版本／參數／窗口政策、具名母體與核驗交易節奏的完整相鄰觀測才可判變化。缺件、未知、漏交易日、取消、失敗、母體變更、改版、同日修訂與晚到回填不是退出；重新入選須可證命中→有效未命中→再次命中，不能跨未知邊界。歷史不足時保持明示，自此保存的合格快照才能增加可比證據。

安全與排錯：歷程唯讀既有 artifacts 與已保存官方日曆，不寫正式 DB／registry、不隱性採集或補跑過去。日曆沿 config.official_calendar_cache_path，未指定則既有 output/paper_execution_eod_replay/calendar_cache；臨時停市來源沿 temporary_closure_path，沒有線上 fallback。日曆必須在固定 publication 時點已可取得且核驗；缺日曆、hash 不符或超出掃描預算時，摘要會顯示具體未知原因。取消歷程保留已核驗當期快照；明示重讀可重試。這是研究觀測比較，不授予 historical PIT、自然 ML、正式推薦或投資資格。限定驗證與回滾見 [UX09 收據](../06_qa/UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md)。

年度快取採 annual_planned_cache.v1，只核驗預期交易節奏。未設定額外停市 overlay 時沿用年度計畫；若明示設定的 overlay 缺失、毀損或尚未可得，保持未知。此計畫不證明當日實際開市，也不補上原始資料 available_at。掃描上限為 32 個歷史觀測、4096 個目錄項目、32 MiB JSON；長期歷史索引與分頁仍待工程實作。


<a id="manual-tail-025"></a>
## 2026-10-05 研究歷史索引、分頁與版本復原

入口：每日研究條件核對已發布快照，選中股票後按「查看選中股票歷史」。歷史另開視窗，固定當期 cohort／manifest 身份及其 publication 截至時點，每頁最多 32 個已保存觀測；「較早一頁」向前查、「上一頁」返回，主頁按鈕可回第一頁。只保存目前頁與最多 64 頁游標的滑動導航窗口，向更早頁讀取不受 64 頁限制。來源、股票或 MA／AND/OR 切換後，舊回呼與頁面失效，明示從第一頁重新核對；當期清單、原排名與收藏不被歷史頁覆蓋。

建立：第一次需要長歷史時，按「建立／重建歷史索引」。這是使用者明示的派生檔操作，背景逐 manifest 建立新 SQLite generation，完工核驗後原子啟用；刷新列表、查詢、排序與分頁都不自動建立索引、不產生歷程事件、不補跑過去。預設索引位於快照根旁 `<snapshot根名>_membership_history_index`，也可由服務的 history_index_root 明示配置，禁止放回 immutable source 裡。所有原快照、objects、母體設定與舊 generation 保留，不遷移真實 DB／收藏、不改 Windows 排程、不自動清理。歷史讀取與建立期間主線個股、既有清單、篩選仍可使用；取消只等待有界安全點，不能假顯示成功。

畫面判讀：歷史頁的「保存條件」是那次 immutable artifact 的 MA 查詢三態，列決策日、當次理由及發布時刻；來源提示保留 manifest／artifact hash、identity與 cutoff。同日不同 revision 各列，不能任選一筆拼連續性。晚發布、partial、未知或缺股明示未知，不算未命中。當期入選歷程只用本頁足以證明的有效相鄰觀測判持續／退出／重新入選；若尚有較早頁，最早觀測與連續期數僅覆蓋本頁，不能宣稱全歷史首次入選。缺日、方法／母體改版、錯來源／修訂及保存中斷仍形成未知邊界。source_available_at 未記錄維持未記錄，索引不授 historical PIT 或自然樣本資格。

相容性：index／pointer／cursor 只接受程式明載支持的 v1；目前 source reader 支援 manifest v2，原本就拒絕的 legacy manifest v1不隱性升級。合法 MA bookmark v1／原排名 bookmark v2仍按原 immutable refs讀回，不因索引故障改成 latest。未建立索引時舊小批次有界 reader可用；索引一旦存在卻損毀、不完整或 schema 未支持，具名拒絕而不冒充完整歷史。來源目錄新增／移除造成目錄 stat 變更時 stale cursor拒絕；本頁及固定當期 pin 的 manifest／artifact 逐一 hash 核驗。未讀到的 artifact 不作全域重掃，不能宣稱整個 archive 已全量驗證；明示重建後從第一頁開始。

復原：在啟用安全點前失敗／取消的新 generation不啟用，原完整 active與來源保留；啟用是不可拆的原子操作，晚到的取消可能已留下完整的新 active，應以 completed receipt 與 active generation核對，不能把完整啟用當未完成。修好相同來源後明示重建／重試。若當前 index版本或 pointer不可用，可明示重新建立受支持的派生索引，或回退至索引根內已完成、核驗且 source fingerprint仍相同的 generation。source 已變更則不能回退舊 generation當現況；先核對原 pinned來源，收藏仍另按原 guards讀取。索引 schema未知不能借回退免除來源核驗。

CLI（只管理派生索引，沒有 producer）：

```powershell
.\.venv\Scripts\python.exe scripts\manage_membership_history_index.py rebuild --snapshot-root "<既有研究快照根>" --index-root "<獨立派生索引根>"
.\.venv\Scripts\python.exe scripts\manage_membership_history_index.py rollback --snapshot-root "<同一研究快照根>" --index-root "<同一派生索引根>" --generation-id "<保留的已完成generation ID>"
```

`--snapshot-root` 必填；`--index-root` 未提供沿上述 sibling 預設；rollback 必須提供 generation ID，不接受任意還原路徑。completed／activated 只代表派生索引成功；not_completed具名 reason不改原資料。查看 receipts 的 generation ID／source fingerprint與 manifest count，再重新核對當期來源。舊 schema、hash／identity不符、source_changed、invalid_cursor、empty、cancelled及超預算皆有明示結果；不可刪除舊資料來換 pass。

資源限制與量測、故障點及有限版本回滾見 [UX09 長歷史收據](../06_qa/UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md)。保留所有generation的儲存會累積，按每次實體 index／staging與保留版本規劃容量；合成長歷史只驗工程，不是自然20日增長實證，永久刪除仍須逐次明確授權。

索引每個 generation 上限 64 MiB；每頁以 1 MiB chunk 重核整個 index SHA，manifest／artifact 頁讀合計上限 32 MiB；最多 32 refs（當期 pin 驗證可能另讀 1 manifest），browse 輸出上限 32 MiB。這些是程式硬預算，不能把預算拒絕改稱自然資料未成熟。年度交易日快取改為最多 4096 個目錄 entries、單年度 32 MiB 累積檔案預算，逐份驗證只保留最新有效版本；臨時休市 overlay 仍最多 32 份，超限回報未知，不擅自猜交易日。

<a id="manual-tail-026"></a>
## 2026-10-05 原盤勢／強弱頁共享研究來源與已開能力核對

原「大盤指數」「強勢個股」「弱勢個股」保留原全市場來源。強弱頁選「研究快照母體」讀每日研究名單已接受的 immutable 快照；大盤在指數面板併列獨立具名研究摘要。母體、決策日、方法契約及manifest/hash在共享部分相同，完整只相對 declared cohort。全市場／產業頁的既有統計依自己的來源、資料日與母體判讀，沒有共同成分身份時比較性未知，不能用三股研究母體代表全市場。

共享強／弱個股依「本日／本周」讀原publisher的四種獨立period/direction模式，全eligible保存列、原StockScreener完整標籤與每股實際比較窗；不重新計分，不反推未保存numeric score，也不把Top/Bottom當一般前幾％或勝率。原排名缺件／wrong source回報原因，不能當榜外；母體排除與原引擎未納入排名分別列出，未保存淘汰理由保持unknown。切頁、切模式、返回只讀既存來源，不觸發producer。shared mode的非版本化收藏不能取代既有同來源研究名單／個股版本化收藏流程。

歷史或研究來源變更、來源清除與模式切換，使先前cache／background回呼失效；重新核對strict snapshot與rank父source。讀取採有界背景工作，取消在安全點完成、過期回應不得改當期顯示；關閉時freeze pending並合作取消。不借來源故障偷偷換latest／全市場來源，也不自動capture或重建。

「研究母體盤勢」新增「查看已開能力與來源」明示audit，固定同一次核驗來源。只登記close／MA20／MA60與close_above_ma20／close_above_ma60的field、unit、warmup、missing、availability、version、cost與source，並保留逐股值／狀態／理由。MA暖機沿保存contract／觀測前綴；官方availability、未記錄時點及量測成本保持未知，不能猜秒數／交易成本。未開方法不在字典內，也不以索引、當期保存或shared接線授historical PIT／自然成熟資格。

能力audit是可讀的detached保存來源資料；清除來源後失效，既有收藏schema與原method/snapshothash不改。正式全市場名冊(B)、新TopN／更改百分位版本、source/capacity owner子責任不在本包；部署與整條跨頁整合F4另驗。

操作步驟：先在每日研究名單明示讀來源，再於強弱市場頁選「研究快照母體」及本日／本周；大盤頁查看併列的研究摘要，指數檢測仍為明示獨立操作。強弱頁以「載入數據／刷新」重核既存 pin；切來源或模式會合作取消前次讀取，等安全完成後啟新讀取。研究母體頁以「重讀同一研究來源」明示讀回。錯源／缺件依狀態原因核對原 manifest，不能自動採集補缺。能力入口先看五項矩陣（可水平捲動），再切逐股完整明細或查看 tooltip；來源清除後重新明示讀取。詳細證據見 [F2／F3 QA](../06_qa/F2_F3_SHARED_CONSUMERS_AND_CAPABILITIES_20261005.md)。


<a id="manual-tail-027"></a>
## 2026-10-05 明示研究來源配置與手動部署

研究模式目前為手動／按需。標準 `ui_qt/main.py` 無參數啟動沿原預設，不建立新的 Windows 排程，也不在啟動或切頁時發布快照。需要指定已保存來源時，啟動方傳入公開 `MainWindow` 參數：`daily_market_snapshot_root`、`daily_market_snapshot_cohort_id`、`original_stock_ranking_root`。前兩者必須成對；母體 ID 取自原 manifest，不猜 ID，也不把來源根目錄改成正式 DB。原排名來源保留其父 research source identity；bookmark v1／v2 仍沿原收藏契約。

明示 cohort 會成為研究名單的初始輸入；這只設定來源，不自動讀取或發布。先核對 manifest 的 cohort／date／hash 與排名父來源，再開研究名單明示讀取。個股檢視後，research v1 依既有操作返回研究名單再收藏；original-rank v2 可在個股原排名報告按「收藏此原排名研究」。兩者重新開啟／精確返回都核對當次來源身份；新程序用相同明示配置讀回收藏，不自動轉 latest。來源缺件、舊 manifest schema、wrong identity 或修改的資料身份拒絕讀回，依具名原因修正配置；不要用採集、刪檔或改 hash 來補通過。合法收藏 v1／v2 與來源 manifest 版本是不同契約，不能混為一談。

停止時透過主視窗正常關閉，背景工作合作取消後收尾；回到預設部署只撤回啟動方的三項自訂參數並開新程序，不移動／刪除保存來源或原收藏。本批 isolated QA 關閉的是自己 child，不操作使用者視窗。

發布前依既有治理工具作唯讀容量／引用診斷與 retention dry-run。實體、WAL、staging、索引及備份都須納預算；容量未知或引用盤點不完整不給 writer 授權。較長保留預估與自然成長分列，中央 reserve 以檢查當下 policy 為準。retention 候選不代表永久刪除授權。

詳細配置、案例、資源數值與限制見 [F4 QA](../06_qa/F4_RELEASE_INTEGRATION_AND_RESOURCE_ACCEPTANCE_20261005.md)。


<a id="manual-tail-028"></a>
### Watchlist 項目 revision 儲存（2026-10-05）

收藏入口仍為每日研究來源頁與個股研究 original-rank 報告，書籤v1/v2與來源／方法／個股身份不變。一般使用者沿原觀察清單操作；既有JSON／v1/v2不自動升級。只有明示建立的新／空canonical SQLite庫採schema3 `watchlist-item-events.v1`。舊v2 active庫仍按原格式保存，達原預算停止；v1唯讀，initialize=True對既有v1/v2會拒絕，避免改原資料。

保存新格式時，current是一份完整清單，歷史以不可變item與增量events保存；重複收藏不多寫，編輯／移除產生新revision，歷史保留精確來源身份。資料庫delete是tombstone，沒有清理舊revision。完整history hash需要逐版replay；治理scan_complete/reference_complete只表示unique source/chain/current核驗，不等於全部歷史payload已重播。

硬限制維持4MiB聚合payload（current＋unique item＋headers＋events）、32MiB DB、64MiB scan、4096rows，不增加上限；容量reserve讀當下中央policy，不以舊點時數字推斷。capacity_unknown／capacity_insufficient／payload_limit_exceeded／database_limit_exceeded時停止保存、保留last-good，先唯讀盤點容量與目前庫格式；不得清理來源、刪revision或降低reserve來繞過。unknown_schema_marker／object_hash_mismatch／delta/current ref或current_revision_source_hash_mismatch表示來源或儲存身份不能信任，保留原DB與錯誤，停止新增並交owner，不另建空清單掩蓋。取消與CAS衝突維持原版，重新讀取明確來源後再重試。

正式舊SQLite庫沒有apply／converter工具可用；本包的dry-run只是唯讀設計盤點。後續流程是固定舊庫hash/stat→新獨立副本→逐版IDs/metadata/bookmark/順序/完整payload hash核對→新舊庫/backup/暫存總容量驗證→父層審核→明確批准後才切activation/path，失敗回原path/marker、保留兩庫。不要把既有JSON copy工具當作SQLite v2 converter，也不要以新隔離250次通過批准正式遷移。

實際受控20／120／250總留存781,365／3,887,695／7,912,388 B；新v3 actual三程序App讀回通過，正式deployment／Native／自然資格另驗。[逐項數值、限制與回滾](../06_qa/F4_ITEM_REVISION_STORAGE_AND_RETENTION_20261005.md)。


<a id="manual-tail-029"></a>
### SQLite v1/v2 COW 遷移與明示啟用（2026-10-05）

此工具把明示指定的舊 SQLite v1/v2 轉成獨立 schema3 副本；不會改寫原庫、舊 `.active` 或 JSON。它取代前節「沒有 converter」的工程狀態。正式使用者來源與切換仍須另行核准；本批只授權生成 fixture 與已許可 QA fixture。不要直接套用以下示例到正式路徑。

入口 `scripts/watchlist_sqlite_cow.py`。`--source` 是舊 canonical SQLite 檔，`--destination` 是不存在的新獨立檔；兩者不能相同或共用 link。以下路徑只表示已核准的隔離 fixture：

```powershell
$source = 'C:\approved-fixture\watchlist\watchlists.db'
$target = 'C:\approved-fixture\watchlist\watchlists.v3-cow.sqlite'
.\.venv\Scripts\python.exe scripts\watchlist_sqlite_cow.py dry-run --source $source --destination $target
.\.venv\Scripts\python.exe scripts\watchlist_sqlite_cow.py convert --source $source --destination $target
.\.venv\Scripts\python.exe scripts\watchlist_sqlite_cow.py activation-preview --source $source --destination $target
.\.venv\Scripts\python.exe scripts\watchlist_sqlite_cow.py activate --source $source --destination $target
.\.venv\Scripts\python.exe scripts\watchlist_sqlite_cow.py status --source $source
.\.venv\Scripts\python.exe scripts\watchlist_sqlite_cow.py rollback --source $source
```

dry-run 唯讀檢查格式、完整歷史與容量，不建 target。convert 建獨立副本與 `<target>.cow-conversion.v1.json` 收據，逐版驗證精確 raw payload/hash、ID、revision number、metadata、時間、source hash、items 與順序；原 JSON whitespace、escape、key order、數字拼法也保留。v1 只有 current 時只建立明示 synthetic baseline，保留原 revision number，不偽造缺失歷史。正常新 revision 仍使用原 compact codec。服務 API 的 `cancel_check` 支援合作取消；CLI 中斷後若留下 staging/鎖，保留原檔與審計資訊，交 owner 確認狀態後處理，不自動清理或覆寫重跑。

activation-preview 檢查收據及來源／副本身份；activate 才寫 `<source>.cow-active.json`，並保存 `<source>.cow-rollback.<id>.json` 回復審計。`--receipt` 可明示 converter 收據；通常沿預設 sibling path。沒有 config 自動切換。以原 canonical path 建立的新 WatchlistService／新程序會辨識明示指向；不要在使用者操作期間切換。status 的 JSON 是目前指向檢查，blocked 時 CLI exit 2；成功 exit 0。轉換 ready 不等於已啟用，啟用成功不等於自然模型或 Native 資格。

rollback 回復原路徑／模式並保留兩庫、收據與審計。原 v1 回復後唯讀，原 v2 回復後可沿原格式正常保存。啟用期間 target 新增的 revision 保留在新庫，不會合併回舊庫；重新啟用已變動的 target 可能因原 prepared hash 不符而拒絕，需另行明示方案。active 期間允許正常 append，但原 baseline chain 必須一致。重複啟用／回復只接受已核驗狀態，未知指向拒絕；無效明示 marker 不回退 JSON writer 或建立空清單。

容量未知／不足、disk full、取消、busy writer／sidecar、來源 hash/stat 改變、錯 schema、壞 JSON／hash／歷史、target 已存在與 audit/pointer 不一致都拒絕。保留 last-good 與錯誤收據，不刪原庫、target、stage 或歷史來繞過。4MiB payload／32MiB DB／64MiB scan／4096 rows 及中央 reserve 不變；新舊庫、保留 staging、收據／marker 與備份需求納入點時 capacity。詳見 [COW QA](../06_qa/F4_SQLITE_COW_CONVERTER_AND_ACTIVATION_20261005.md)。


<a id="manual-tail-030"></a>
### 最終容量守衛收尾（2026-10-05）

啟用與回退發布 audit／marker 前重新核對當下中央 reserve；容量未知／不足具名拒絕並保留原指標、雙庫與內容。最終限定路由72 passed（focused_root_05.log；另有pytest cache唯讀警告），mypy793及CLI1通過，11檔compile／7產品檔精度與未來函數AST守衛0違規。14個獨立程序實際CLI回放全部exit0、隔離guard0違規，17份immutable來源及原20-session fixture SHA不變。最終case為output/qa/f4_cow_converter_activation_20261005/cli-roundtrip/run-615b305783f9；原失敗與中間收據保留，不替換為自然或正式驗收。


<a id="manual-tail-031"></a>
### Legacy JSON v1 COW 與原觀察清單升級入口（2026-10-05）

一般預設清單實際沿 legacy JSON v1 保存。原「升級儲存」按鈕是明示切換：只有單一 JSON 來源且沒有 canonical SQLite 時，建立獨立 `watchlists.v3-cow-<來源名>-<唯一ID>.sqlite`、核對完整來源後才啟用；不建立中間 v2 canonical。多份 JSON、已有歧義來源、錯 marker、容量或身份錯誤具名拒絕，保留原清單與錯誤。既有 canonical 的修復相容路徑另依原契約。

CLI 同一入口；只有 dry-run／convert 要指定 `--source-format legacy-json`，其餘步驟從轉換收據辨識格式。以下僅是已核准隔離 fixture 的示例，正式使用者來源與切換另行確認／批准：

```powershell
$source = 'C:\approved-fixture\watchlist\default.json'
$target = 'C:\approved-fixture\watchlist\watchlists.v3-cow.sqlite'
.\.venv\Scripts\python.exe scripts\watchlist_sqlite_cow.py dry-run --source $source --destination $target --source-format legacy-json
.\.venv\Scripts\python.exe scripts\watchlist_sqlite_cow.py convert --source $source --destination $target --source-format legacy-json
.\.venv\Scripts\python.exe scripts\watchlist_sqlite_cow.py activation-preview --source $source --destination $target
.\.venv\Scripts\python.exe scripts\watchlist_sqlite_cow.py activate --source $source --destination $target
.\.venv\Scripts\python.exe scripts\watchlist_sqlite_cow.py status --source $source
.\.venv\Scripts\python.exe scripts\watchlist_sqlite_cow.py rollback --source $source
```

來源必須是受支持的 UTF-8 JSON v1 object／items array；BOM、錯編碼、未支持版本或已知欄位型態／內容錯誤拒絕，不靠轉型猜值。原檔 bytes、合法未知巢狀欄位、項目順序、日期、理由、來源與書籤保留；沒有可驗證 revision ledger 的 JSON 只建立明示 synthetic baseline，opaque 歷史原樣保留。來源由唯讀鎖固定至發布，中央容量 reserve 與既有 payload／DB／scan 上限維持。

`<source>.cow-active.json` 綁定 JSON 來源與 target。成功啟用後以原來源設定開新程序，重核來源與收藏內容；保存沿 v3 revision。錯 marker／過期 writer 拒絕，不偷偷回 JSON。rollback 切回原 JSON，原 JSON 可按原模式繼續保存；target 期間新增內容、雙來源、conversion receipt 與 rollback audit 全保留，不自動合併或清理。具名拒絕時先核對 status、來源／收據身份和點時容量，保留 stage 與錯誤交 owner；不能刪檔／降 reserve 換成功。

本批只驗合成隔離來源；正式 default.json 未遷移、缺失 watchlists.db 未初始化，Native／自然資格另驗。詳見 [Legacy JSON COW QA](../06_qa/F4_LEGACY_JSON_COW_AND_ACTIVATION_20261005.md)。


<a id="manual-tail-032"></a>
## 個人觀察清單：明示選擇與獨立控制檔（2026-10-06）

使用者已批准 `DATA_ROOT/personal`（預設 `D:/Min/Python/Project/FA_Data/personal`），取代先前 `%LOCALAPPDATA%/baldr/personal` 候選。這只批准位置；真實 migration／activation 仍未批准，未遷移既有 JSON、未建立正式個人 DB，程式不自動啟用。

1. 在準備使用的啟動環境成對指定 `PERSONAL_DATA_ROOT` 與 `PERSONAL_WATCHLIST_SOURCE`（既有 JSON 或 SQLite 的絕對路徑）。`TWStockConfig.from_args` 亦接受 `--personal-data-root`／`--personal-watchlist-source`。兩者皆未設定時維持既有模式；只設一個會拒絕，不能藉此默默回到原來源 writer。市場包內只允許精確 `DATA_ROOT/personal`；其他市場子樹、ancestor、舊 output、程式套件與 link／hardlink 別名仍拒絕。
2. 開啟候選池頁，未啟用時只讀原來源；按「建立並啟用個人副本」查看來源、目標、標記、收據、來源備份及回滾紀錄路徑。取消不建立副本；明確選「Yes」才轉換、核對並啟用。來源內容與未知巢狀欄位保留。
3. 啟用後保存寫入 `PERSONAL_DATA_ROOT/watchlists/watchlists.v3.sqlite`。新程序沿個人 marker 重新核對 writer；錯來源、收據、hash、schema 或 marker 會拒寫，不能改寫來源來繞過。
4. CLI 每個動作可加 `--personal-root <絕對路徑> --market-root <絕對路徑> --legacy-output-root <絕對路徑>`，三者須齊全；`--source` 必須匹配選定來源。dry-run／convert／activation-preview／activate 的 `--destination` 必須是上述個人 DB；JSON 轉換另加 `--source-format legacy-json`。先 dry-run，再 convert、activation-preview，最後明示 activate；status 可查狀態。
5. 個人模式 CLI rollback 使用相同 source 與三個 root。回滾停止個人 writer，保留個人 DB 的新 revision／歷史及來源；不恢復市場來源 writer、不自動合併、不刪除。取消配置後重新使用舊模式也不是回滾步驟，須另行審查。

控制檔皆在個人 root：DB 同目錄的 `watchlists.v3.sqlite.cow-active.json`、其 `.lock`、`watchlists.v3.sqlite.cow-conversion.v1.json`；原 JSON bytes 備份為 `backups/watchlists/source.<來源絕對路徑的SHA256>.json`，備份內容 SHA256 另由 receipt 核對；rollback audit 為 `activation_backups/watchlists/rollback.<activation_id>.json`。設定目前由 runtime 欄位／環境提供，沒有新建設定檔。

排錯：缺一個選擇欄位、來源不存在／歧義、root 重疊、reparse/link/hardlink、來源或 target 身份改變、容量未知／不足、marker 損壞／已回滾時保留資料與收據，修正明示選擇或交由審查，不刪 target／備份／lock 來重試。個人模式啟用失敗不會退回原 JSON writer。

市場 CSV 已有明示 allowlist consumer／CLI；沿固定manifest與source／target handle identity核對，操作見後文市場 CSV 匯出章。JSON、SQLite、私人 output、重疊與 links/hardlinks仍拒絕；這不代表整包 FA_Data 可安全分享，也不授來源授權。Notes主UI已獨立接selector，Portfolio／ledger及DecisionQuality等剩餘私人caller仍待接線。詳見[個人儲存 QA](../06_qa/PERSONAL_STORAGE_SEPARATION_LANE_20261005.md)與[CSV整合 QA](../06_qa/MARKET_CSV_EXPORT_INTEGRATION_20261006.md)。


<a id="manual-tail-033"></a>
## 每日名單：MA 方法與家族符合度（2026-10-06）

入口為每日研究名單／候選摘要；先明示讀取既有已發布快照。摘要沿同一已接受的 manifest、日期、cohort、方法版本與逐股來源 hash，不啟 producer 或重算 MA；原有篩選、排序與返回方式保留。

母體摘要列出已提供方法、去重家族及每方法的符合／未符合／未知分母；選取股票後查看符合方法數、符合家族數，以及各方法狀態與理由。詳細方法 ID／版本／家族／來源身份在 tooltip 可查。MA20、MA60 同屬 `close_vs_moving_average`：兩個都符合是 **2 方法、1 家族**，不表示兩個獨立策略、勝率或提高投資分數；原排名沒有批准入選 predicate，不加入方法數。

缺第二個合格家族時，跨家族共同入選維持未知。缺 artifact／方法 metadata、partial cohort 或來源不可比也明示未知／無法投影；未知不當未入選、負樣本或退出。日期／來源／修訂／方法版本不符時，移除舊摘要而保留理由，不借 live 或另一日期補資料。清除快照同步清除摘要；篩選不改原完整分母。

排錯時查看來源與方法資格 tooltip，重新選擇可核驗的固定快照；不要更新 producer 或修改來源以湊交集。本功能限定 current-observed research，歷史 PIT／官方可得時間未證明；真正跨家族結果、其他方法、生命週期聯動與 Native／真人驗收仍待後續。詳見 [UX10 QA](../06_qa/UX10_MULTI_METHOD_LANE_20261006.md)。


<a id="manual-tail-034"></a>
## 個人 notes 明示選擇與舊來源唯讀（2026-10-06）

本功能接到既有研究筆記／個股研究動作、決策工作台、推薦個人選擇／delivery ACK 與 outcome journey。notes 選擇獨立於觀察清單轉換／啟用；不全域改市場 `db_file` 或 `OUTPUT_ROOT`，Portfolio trades／ledger 的位置保留。正式個人位置已批准為 `DATA_ROOT/personal`，notes migration／切換仍未批准；以下只說明已完成的程式契約，沒有套用真實 notes。

1. 未設定 `PERSONAL_JOURNAL_ROOT` 與 `PERSONAL_JOURNAL_MODE` 時，保留既有相容設定：notes 在 `OUTPUT_ROOT/portfolio/journal_entries.jsonl`，包含既有 writer；這不是全域禁寫。
2. 經批准選定位置後才成對設定絕對 `PERSONAL_JOURNAL_ROOT=P` 與 `PERSONAL_JOURNAL_MODE=personal`。Qt 主程式透過環境載入；使用 `TWStockConfig.from_args` 的工具可傳 `--personal-journal-root P --personal-journal-mode personal`。root 不能與市場／legacy output／程式目錄重疊，也不能經 junction、symlink 或 hardlink 別名。設定本身不建立 notes、watchlist 或搬移檔案。
3. 個人模式的所有 UI notes caller 使用同一 selector；新筆記／revision／ACK 保存於 `P/research_notes/journal_entries.jsonl`，OS lock 為同目錄 `.journal_entries.jsonl.lock`。讀取空的個人來源會顯示缺資料，不改讀 legacy，也不合併兩份歷史。首次 writer 操作才建立個人目錄／lock。
4. 若要明示看舊 notes，使用相同 root 與 `PERSONAL_JOURNAL_MODE=legacy_read_only`。固定讀 `OUTPUT_ROOT/portfolio/journal_entries.jsonl`；不建來源目錄／lock，不 append。研究動作控制器會顯示唯讀原因並停用寫入；一般筆記或個人選擇／ACK 保存也會明確拒絕，不能把拒寫當保存成功。
5. `P/backups/research_notes/`、`P/research_notes/audit/` 目前只是受守衛的預留路徑，沒有備份／migration producer；`config.create_backup` 不提供 personal root 的整體備份。不可只取消設定就把新內容視為已回滾或重新啟用舊 writer。真正搬移須另行批准來源、target、備份、停寫、驗證及回復方案。

排錯：root／模式缺一、錯模式或 unsafe path 會在設定或操作時拒絕。已設定 notes 模式卻漏傳 selector 的 Journal／Workbench／journey caller 也會拒絕，不回退 legacy；尚未接線的工具不能用此模式寫入。未知 record type、來源變更、CAS 衝突或取消時保留原歷史，檢查模式與 exact identity，勿刪 lock／資料重試。Notes 與 Evidence DB、DecisionQuality、DeskSnapshot 的獨立路由仍是後續工程；本次不是市場 SQLite 的分享資格證明。詳見 [Journal QA](../06_qa/PERSONAL_JOURNAL_LANE_20261006.md)。


<a id="manual-tail-035"></a>
## 2026-10-06 最新個人儲存位置決策

使用者已選擇 `D:/Min/Python/Project/FA_Data/personal` 獨立子目錄，取代先前 LOCALAPPDATA／FA_Data 外 root 提案。專用 SQLite 不與市場 `twstock.db` 共用。這次只批准位置，真實 migration／activation 仍未批准；尚未搬移／建立正式 personal store。精確 `data_root/personal` 契約已整合；其他市場子樹、ancestor、output 與 links/hardlinks 仍拒絕。必須明示設定 root／source 或獨立 notes root／mode，未設定不會自動啟用。市場分享只能按 explicit allowlist 排除 personal、舊 watchlist JSON 與其他私人來源，不能宣稱整包 FA_Data 可直接分享。


<a id="manual-tail-036"></a>
## 回測設定的版本化規則說明（2026-10-06）

在研究實驗室／回測的策略設定選擇策略後，按「查看版本化規則說明」。卡片唯讀呈現此次回測設定的策略版本、參數、來源已提供的適用範圍及規則；未連結任何執行結果。參數仍由原設定頁修改，再重新開卡核對；開卡不執行回測、不建立executor或啟動資料更新。

來源沒有完整入場／出場、成交時點、費稅、停損停利、部位、benchmark等契約時，畫面保留「未知」，完整交易規則與績效維持尚不可評估。Registry描述或參數schema不是執行資格，既有validated宣告也不是已核對績效。此次卡不能替歷史回測、自然forward或當期結果補身份；不同結果類型必須各自核對。

按「查看來源與版本核對」展開原欄位來源、精確version/hash、缺件與不相容原因；可選取複製文字。若尚未選策略，先選擇再開卡；版本不符或來源缺件時保留不可評估，不借最新版設定。不提供曲線、勝率、排名或自動套用動作。此為UX11有限說明consumer，完整execution／performance資格及Native真人驗收仍待辦。


<a id="manual-tail-037"></a>
### 從保存結果查看規則來源

研究實驗室→研究Registry，選取一筆保存run後按「查看單筆結果與規則」。背景核對完成後，卡片顯示歷史回測或研究追蹤類型、保存版本、期間、資料截止、標的、保存成交假設／費率及基準來源。此操作不執行回測或寫入來源，關閉卡片後仍保留列表與選取；換選取或關閉頁面時舊讀取不套用。

「保存身份已核對」只表示來源pin相容，正式資格未授予。版本／source／期間／成本不符、沒有保存Spec／pin時標不可評估；不借目前設定或default成本。未知benchmark及稅費保留未知，Registry說明／參數不當作完整執行契約。來源／hash／完整標的及檔案ref可展開核對。研究追蹤不稱live、機率或真成交。

讀取失敗會顯示「保存來源核對失敗」，可重試或重新整理；先核對保存來源，勿以重新分析替舊結果補章。一次只能開單筆，兩筆以上仍使用原比較入口。取消不會強殺正在讀檔的thread，完成後不套舊結果；不會改保存內容。

<a id="manual-tail-038"></a>
## 2026-10-06 UX20 單批 MA 研究樣本

每日研究條件載入已核驗快照後，「研究樣本」顯示該聲明母體（含排除）及 MA20／MA60 符合、不符合、未知、排除分母。這是純投影，未保存樣本；入選規則／來源當時可得／交易日曆／成熟結果未知，不授訓練、PIT或正式交易資格。

隔離 CLI `scripts/produce_daily_market_research_snapshot.py` 保留既有 db/output/cohort/cutoff/symbols 或 universe-config 參數；額外明示 `--capture-root output/qa/<專用子目錄> --capture-as-of observed-now` 才保存完整控制組。首次結果的 `sample_readiness.as_of` 是本次觀測時刻；重跑改用該完整 ISO 值，且相同母體、pin與來源才 duplicate。再次 observed-now 會成新觀測；同日來源修訂保存新包，舊包不覆寫。保存結果的 saved_verified 只表示 capture/receipt與snapshot pin一致，不代表自然資料成熟。

單批僅1–16檔不同 included，含 excluded最多32；更大母體尚無parent manifest，明示拒絕。capture根只接受 repo output/qa 或系統Temp子目錄，與snapshot來源不能重疊；200GiB reserve、256KiB/包及8MiB/128包留存不放寬。若容量不足、來源／as_of晚於或早於合法範圍、busy、partial或receipt壞，CLI返回rejected；保留原證據，先核對來源及容量，不自動清理／補時鐘。未加正式配置或排程，頁面瀏覽不會保存。

詳見 [UX20限定QA](../06_qa/UX20_SAMPLE_CAPTURE_INTEGRATION_20261006.md)。個人儲存／Journal程式已整合，正式migration／啟用尚未進行。

CLI capture階段失敗時返回碼2，但上游snapshot可能已發布；回傳保留producer的manifest/status，另列sample_capture_status=rejected。只有成功readiness才表示樣本讀回已驗，請勿把上游發布誤認為樣本成功。


<a id="manual-tail-039"></a>
## 2026-10-06 UX20 具名多批母體保存與唯讀讀回

較大母體已提供 parent CLI；上節「尚無parent」限制只屬前批單批入口。使用 scripts/produce_daily_market_research_snapshot.py，明示 --db-path、repo output內專用 --output-root、含時區 --decision-cutoff、--parent-universe-config、隔離 --capture-root、--capture-as-of observed-now。parent模式不接受 --symbols／--universe-config／--cohort-id／--read-stock。

配置 schema_version=daily-market-research-parent-universe.v1，填 universe_id/version/as_of_date、method=daily-market-close-ma.v1、scope=bounded_multibatch_research_cohort、included_stock_codes、excluded_stock_codes（stock_code/reason）、population_count，research_only與complete_fixed_cohort皆true。最多256 included、256 excluded、16批，每批仍≤16 included與≤16 excluded；若不能合法分批則拒絕，完整只指聲明母體。

首次保存後保留 sample_readiness.as_of 及 parent identity，重試改用該固定完整ISO時刻才去重。加入 --read-parent-identity <identity> 及同一配置/output/capture/cutoff/as_of可由新程序唯讀讀回；CLI仍要求db-path參數，但此模式不開DB。錯cutoff/as_of、來源pin或方法不符會拒絕，不借另一日補資料。

檢查 cohort status、captured/uncaptured分母與每批 production_status/sample_capture_status。producer可能已發布而sample拒絕；返回碼2不代表未寫任何來源。cancelled/incomplete parent envelope可完整保存，但不能稱母體完整。缺批成員列uncaptured，不當負樣本；available-at/calendar/outcome仍unknown，selected=0，不授PIT、訓練或正式资格。

容量與單store守衛不放寬，另限各root64MiB/4096 entries。busy/partial/hash錯誤保留原件；先核對明示配置、容量與來源。child保存中斷留下partial時，舊store拒絕重試；經確認使用新的隔離capture root，保留舊root供審查，不刪lock/partial繞過。沒有正式排程／自動清理。每日MA頁仍為原單批純投影，未提供parent瀏覽動作。詳見 [多批QA](../06_qa/UX20_PARENT_CAPTURE_INTEGRATION_20261006.md)。


<a id="manual-tail-040"></a>
## 2026-10-06 查看保存的多批研究母體

每日研究條件→「查看保存母體收據」→「選擇保存收據」，選取原隔離保存位置的 parents/<身份>/receipt.json。背景核對完成後，先看母體／版本／保存資料日、截止與觀測時刻、完整或缺批、已捕捉／未捕捉分母及MA方法計數。逐批快照產生結果與樣本保存結果分開：producer已發布不等於capture成功；顯示的是保存收據記錄，同identity沿用首次收據，重讀不推定最近一次CLI結果。

「重讀／重試核對」唯讀相同包，不產生資料。若未完整，先查看各批結果，再依上節隔離CLI沿相同固定as_of及來源重試；來源／方法變更要新明示保存；partial store保留，使用新隔離位置而非刪lock／原件。返回或取消會停止套用結果，背景讀取安全返回後才可重讀，取消不代表曾保存內容消失。

「展開來源與診斷」可看原配置、hash、receipt及逐批error，預設收合。保存包身份通過但readiness拒絕時，表格保留原記錄，母體完整資格未確認；envelope拒絕則清舊分母，核對選取來源後重試。缺批是未捕捉，未知不是負樣本，符合方法不等於正式入選；available-at／交易日曆／成熟結果仍未知，不授PIT、訓練或正式資格。頁面原單批樣本摘要仍明示未保存，不借parent包替另一單批來源核章。詳見 [收據UI QA](../06_qa/UX20_PARENT_RECEIPT_UI_20261006.md)。


<a id="manual-tail-041"></a>
## 2026-10-06 固定觀測日研究收據接受（隔離 CLI）

這是parent保存後的明示接受步驟，不啟producer、排程或正式DB。先準備UTF-8 policy JSON：schema_version=rule-research-observation-policy.v1、policy_id/version、timezone=Asia/Taipei、decision_cutoff_time、observation_start_time/end_time（HH:MM:SS且cutoff≤start≤end，不跨日）、expected_observation_dates（1–31個排序不重複ISO日期）、universe_template_source（既有parent母體JSON絕對路徑）、research_only=true。日期是明示觀測日，未知calendar不能推官方交易日。模板除日期外的全部成員／排除／版本須與每筆parent相同。

呼叫scripts/accept_rule_research_observation.py，傳--policy-config P --acceptance-root R --evaluated-at <含時區ISO時刻> --parent-receipt <parents/identity/receipt.json>；預設preview，不建接受目錄。核對candidate原cutoff/as_of、資料日、target_data_day_status與missing_target_data_members，明示再加--accept才寫研究接受或未完整記錄。R僅隔離output/qa或Temp子目錄，不能重疊producer/parent來源或包含配置來源；既有容量／留存守衛不放寬。

省略parent-receipt只讀日覆蓋報表，不開DB。evaluated-at不能晚於現在，不借後來parent。expected日窗口未到為not_due，窗口內awaiting，窗口結束仍缺完整包列missing_complete_observation；不以最新日、較早資料日或unknown補齊。parent保存完整不保證每股資料日正確，缺目標日只存recorded_incomplete_observation，不能算當日完成；方法符合不是正式入選，calendar/available-at/Outcome未知，不授PIT、formal或training。

相同policy/exact parent輸入duplicate沿首次receipt。同日不同revision/as_of保舊新包，日報列所有pin，不自動挑winner；policy bytes／方法或模板改變須明示版本處理，舊記錄不混算。退出0不表示無漏日，需看missing_observation_dates與日狀態；未完整候選/日報拒絕返回2。

失敗時核對receipt：acceptance_saved=true＋day_readiness_status=rejected表示接受包已寫、報表未核對；accept exception以unknown表示可能有殘件，不能當沒寫內容。容量不足且無partial可修正容量後原root重試；partial/busy保持fail closed，保留原件，經確認明示新的隔離root重試，不刪lock/partial繞過。沒有正式WindowsTask、自動清理或市場資料搬移。部署缺件與待決策見 [固定觀測日QA](../06_qa/UX20_OBSERVATION_DAY_ACCEPTANCE_20261006.md)。


<a id="manual-tail-042"></a>
## 2026-10-06 執行隔離每日研究 owner

<a id="manual-tail-043"></a>
### typed 日曆／上游 terminal 與多段執行

另可使用 scripts/scheduled/run_rule_research_daily_isolated.py --runtime-request <request.json>：預設只 preflight；明示 --execute-isolated 才做隔離執行；--task-review 只輸出 disabled、task_registered=false 的可審查包，不能與 execute 同用。runtime-request 不可混 runtime-config／target-date／outcome-root。完整 request schema 為 rule-research-daily-runtime-request.v1；各欄必填，duplicate keys 拒絕。

caller 須先核原 calendar／terminal bytes custody，再注入明示 identity/hash pins、coverage_start/end、完整且有序交易日、available_at、coverage_complete、target_date、decision_cutoff、expected_jobs、terminal complete/receipt/source-binding/completed_at、segments 的日期／runtime_path/hash，以及同一 coordination_root／timeout_seconds。未核日曆、coverage 未知、缺 terminal、錯目標日或 revision/hash 拒絕；非交易日不開 owner。synthetic 只供 offline_rehearsal=true 與 synthetic_offline 預演，不能用布林／自行填 hash 取得正式資格。所有 natural／PIT／formal／training 原 unknown/false 保留。

每段使用獨立且不重疊的四類輸出 roots；所有段共用 coordination_root 的單 writer lock。先預檢，execute 前後重驗 runtime/policy 與 source pins；preflight 與 observed/already_observed 必須明示 int 非 bool 的零 subprocess exit，缺欄或非零不能當成功。成功還須讀回 exact immutable owner receipt。timeout_seconds 為 1–3600 秒，stdout 上限2MiB、stderr64KiB；取消／超時停止本次 child，保留 partial，busy 不清他人 lock。CLI 0可能只是 preflight／非交易日，不代表自然接受。

容量沿原角色：snapshot 至少20GiB，parent/capture/observation/sample/status至少200GiB，owner另加工作／暫存預算。effective=max(原角色下限,明示接受override)，20–200GiB override 不降低 capture200GiB；低於20GiB拒絕，高override保持。未知容量拒寫，無自動清理。來源、舊segment、partial與收據保留，新revision另開明示segment，不選latest。深Unicode／emoji OS I/O使用內部renderer，公開identity/hash仍canonical；不改全域Windows設定。Task／account／ACL／正式根目錄與真來源啟用尚未准。[B12完整契約與限定驗證](../06_qa/BALDR_B12_DAILY_RUNTIME_20261006.md)。



入口scripts/scheduled/run_rule_research_daily_isolated.py。--runtime-config R與--target-date YYYY-MM-DD必須明示；未設定回unconfigured，預設preflight只讀，--execute-isolated才執行。無DATA_ROOT/OUTPUT_ROOT、today/latest或正式Task預設。

runtime JSON schema_version=rule-research-daily-owner-runtime.v1、mode=isolated_research、date_source=explicit_policy_dates；填絕對policy_config/source_db與snapshot_root/capture_root/acceptance_root/status_root、per_root_quota_bytes（正整數≤64MiB）、max_attempts（1–3）、retry_delay_seconds（整數0–5）及parent_universe_configs（目標日期→parent母體JSON絕對路徑，最多31）。policy是上節固定觀測日policy，沒有cutoff/window/expected dates即unconfigured。四根互不重疊，不含配置/來源檔，source也只能在output/qa或Temp，正式市場DB拒絕。本批沒有正式配置檔。

先preflight核對同一目標日/母體/來源pin/窗口和capacity，通過才明示execute。容量按批數保守預留，可能阻擋較大母體；reserve/8MiB/128包等守衛不放寬、不自行清理。窗口未到not_due，隔日遲到昨天目標missed_window＋missing日報，不改用今日或latest補資料。

結果observed表示隔離全鏈讀回完成；already_observed表示唯一exact source/policy/日期保存收據沿用，未重跑producer。每attempt各批快照產生與sample保存結果分列，已發布後sample拒絕不能當沒寫內容；parent/acceptance/owner receipt與day readiness分開。runtime/policy/revision途中改變blocked保留原件；owner status保存拒絕也保留前面實際結果。未完整資料日不算當日完成，方法符合仍非正式入選，official calendar/available-at/outcome未知，不授natural/PIT/formal/training。

retry最多配置次數與有限合作式delay；busy保留別人lock，cancel等待安全返回。partial需明示fresh隔離root，不刪除繞過。返回2不代表沒有producer artifact，請查attempt及receipt；容量不足可能只輸出stdout，勿期待藉status寫入突破容量。正式日期來源/Task/account/ACL/留存/通知仍待部署；三項有推薦值的決策見 [daily owner QA](../06_qa/UX20_DAILY_OWNER_ISOLATED_20261006.md)，現在未套用任何生產值。


<a id="manual-tail-044"></a>
## 2026-10-06 UX21 保存母體 H5／H10／H20 研究結果

每日研究條件→「查看保存母體收據」→選擇原 `parents/<身份>/receipt.json`，切到「H5／H10／H20 研究結果」，按「選擇研究結果輸入」。此操作只讀所選 exact parent、全部已捕捉 children、原快照與母體配置；不開市場 DB、不產生快照、不保存新 outcome、不選 latest。未提供輸入會顯示資料不足，未借即時行情或預設成本。

輸入為 UTF-8 JSON（最多 2MiB），頂層只能含 `schema_version=rule-research-forward-input.v1`、`parent_identity_sha256`（原收據資料夾身份）、`decision_date`（原母體資料日）、`as_of_date`（明示 ISO 評估日）、`calendar`、`prices`、`benchmark`、`cost_policy`。評估日不能晚於當前 UTC 日期，也不能早於已知保存／觀測時鐘的 UTC 日期；日期精度不是盤中可得性證明。

`calendar` 填 `trading_dates`（排序、不重複 ISO 日期，最多260）、`known/complete`（布林）、`coverage_start/end`、`source_identity`、`available_date`。未知日曆必須 known=false、complete=false、dates=[]、coverage/source=null；available_date 未知用 null。已知完整日曆須含決策日與第5／10／20個後續交易日；只宣告研究覆蓋，不能冒稱官方日曆／custody。H5等依明示交易日計數，缺日不跳過，未涵蓋標資料不足，尚未到期標未成熟。

`prices` 是逐 instrument/date 的點（每 instrument 最多21，母體最多512加一個基準）。每點填 `instrument_id`、`trade_date`、`state=available/missing/suspended/unknown`、`price`、`source_identity`、`currency`、`unit`、`price_basis`、`corporate_action_basis`、`available_date`；可另填 `content_identity_sha256`，有填就必須符合內容。available 的 price 必須為正有限 Decimal **字串**，例如 `"100.25"`，不是 JSON 數字；其餘 state 的 price 必須 null。只計算決策日與精確結束日，不用期間中間價代補；晚於評估日才可得的點不可用。來源可得日期未知時研究數值可算，但可得性仍未知，不能提升 PIT。

`benchmark` 可明示 null（超額未知），否則填 `instrument_id/currency/unit/price_basis/corporate_action_basis/source_identity`，並在 prices 中提供同期間基準端點。基準不能與母體股號衝突，點的來源及基礎需匹配 spec；幣別、價格及公司行動基礎未知或不相容時不計超額。基準 unit 可不同（例如指數點與每股價格），各 instrument 內的單位／基礎必須一致。

`cost_policy` 可為 null（成本未知），否則填 `version`、`formula_id=proportional_entry_add_exit_deduct.v1`、`target_entry_bp/target_exit_bp/benchmark_entry_bp/benchmark_exit_bp`；各成本須為0–10000的整數 bp 或明示 null。零成本也要明示，不補 default。毛報酬=end/entry−1；成本後=end×(1−出場bp/10000)/(entry×(1＋進場bp/10000))−1；超額為同期間 target−benchmark，成本兩邊完整才有成本後超額。畫面以 HALF_EVEN 整數 bp 顯示（100bp=1%）；精確 Decimal 與正負標籤在收合診斷，四捨五入0bp不代表精確報酬為零。

首屏每方法／H5、H10、H20 顯示可看毛報酬、未成熟、資料不足、缺價／停牌、排除、未捕捉人數；每方法分母包含全部聲明成員。以方法與 horizon 下拉查看逐股方法判定、結束日、毛／成本後報酬、毛／成本後超額及缺件。符合方法／不符合都可有研究報酬，兩者都不是交易 selected；選樣未知，未捕捉不是負樣本。成本未知保留可計毛報酬，相關成本後欄位為「—」。表格不算勝率、排名或組合績效。

「重讀／重試核對」重新核對同收據及同輸入；「清除結果輸入」回到未評估，切換另一母體收據清除前一輸入。選檔取消保留原選擇。取消／返回／關窗等待背景安全返回，不強殺 thread；晚到成功／錯誤不套用，完成後可沿同收據重試。輸入錯parent、未來評估日、重複鍵、非Decimal字串、成本／基礎不合法或途中修訂時拒絕；結果表清除，原各批保存記錄保留，技術理由在「展開來源與診斷」。先核對精確版本與缺件，保留原檔，不更新 producer 或刪資料繞過。

這是 endpoint-only research，沒有 MFE／MAE、期間停牌完整性、可成交性或真實交易績效；所有 PIT／formal／training／natural／execution flags 維持 false。工程接線已可用；官方 calendar／raw price custody、自然樣本、後續日期成熟與 Native／真人驗收分列未完成。不自動產生價格輸入、正式排程或 outcome store。詳見 [UX21 QA](../06_qa/UX21_FORWARD_OUTCOME_20261006.md)。


<a id="manual-tail-045"></a>
## 2026-10-06 UX21 實際來源與隔離結果保存／日報

前章明示 JSON 輸入仍可用；本章補上實際來源 adapter 與保存收據入口，取代前章「尚未提供 outcome store」的限制。研究限定：目前觀察的價格與年度計畫日曆，臨時休市／歷史可用時間未知，所有 PIT／formal／training／natural／execution 資格為 false。

1. 先用既有工具取得 exact parent receipt。新設定檔必須明示絕對路徑與評估截至日，不接受 latest 或未來日。以下欄位全部必填：

```json
{
  "schema_version": "rule-research-forward-isolated-runtime.v1",
  "parent_receipt": "C:/Projects/PythonProjects/technical_analysis/output/qa/<隔離capture>/parents/<identity>/receipt.json",
  "source_db": "D:/Min/Python/Project/FA_Data/sqlite/twstock.db",
  "calendar_cache": "C:/Projects/PythonProjects/technical_analysis/output/paper_execution_eod_replay/calendar_cache/<明示原檔>.json",
  "as_of_date": "2026-10-06",
  "cost_policy": null,
  "benchmark": null,
  "outcome_root": "C:/Projects/PythonProjects/technical_analysis/output/qa/<隔離outcome>"
}
```

`source_db` 只讀既存 daily_prices／technical_indicators 的相容 schema；每股最多 120 筆價格，僅取原決策日與 5／10／20 年度計畫 session 終點。原始決策價指紋不符、找不到 exact endpoint、重複或無效價格會保留資料不足，不用最近價。超過既有 120 列範圍不向更久歷史補查。`calendar_cache` 是已存在、freshness／raw／hash／全年完整性核對成功的單一 TWSE 年度檔，不能傳資料夾；跨年度範圍不完整則未評估，臨時休市仍未知。完整的是年度計畫範圍，不是實際交易 custody。

`cost_policy=null` 表示未知，不補 0。可明示物件：`version`、`formula_id="proportional_entry_add_exit_deduct.v1"`、`target_entry_bp/target_exit_bp/benchmark_entry_bp/benchmark_exit_bp`，每欄為 0–10000 整數 bp 或 null；0 必須是明示政策。已有 target entry/exit 成本才能顯 net。本 adapter 目前只接受 `benchmark=null`，不猜 market_indices 的品項或可比 basis，因此 excess 保持 null；原明示 JSON input 仍能提供已核定的同期間 benchmark。價格未調整，公司行動 basis 未知，不代表含息總報酬。

2. 在 repo 執行 `./.venv/Scripts/python.exe scripts/scheduled/run_rule_research_forward_isolated.py --runtime-config <絕對設定路徑>`，預設只有 preflight；檢查 status／qualification／source_contract／issues。只有明示加上 `--execute-isolated` 才在指定 root 保存，沒有啟用 Task 或市場 DB writer。root 必須是 repo output/qa 或 Temp 的獨立子目錄，不能與 capture／snapshot／設定或來源重疊。

3. 保存結果回傳 `receipt_path`、identity 與 published／duplicate。相同 runtime／parent／來源 revision／as-of／cost 重試是 duplicate；改來源、clock 或政策產生新版本，全部保留。不用 latest，也不覆蓋同日期舊結果。容量在建立目錄前檢查，沿 200 GiB reserve、256 KiB 保存 envelope、8 MiB／128 包界線；完整結果解壓最多 2 MiB，超限拒絕，不截斷母體。partial／busy／capacity 停止時保留原件，使用新隔離 root 重試或交 owner 處理，不自行刪歷史。

4. 日報可於同一命令加 `--policy-config <既存policy>` 與 `--acceptance-root <既存日期接受root>`，兩者須同時提供。每筆日期接受紀錄新增 `forward_status` 與 `forward_outcomes`，列出同 parent 所有保存版本；沒有結果是 awaiting_source_or_outcome，保存損壞／busy 是 unavailable_or_unverified，不當作報酬 0 或負樣本。既有 daily owner CLI 也可加 `--outcome-root <明示root>` 唯讀附加同欄位；不會自動執行 outcome producer。歷史 current-observed capture 不能回填固定日接受；未配置正式 owner／Task／cadence 仍未部署。

5. 在每日研究→母體保存收據選原 parent，再於 H5/H10/H20 研究結果頁按「選擇結果輸入／保存收據」，選剛回傳的 `<outcome-root>/<identity>/receipt.json`。背景核對 exact parent、children 及結果 hash 後顯完整分母與各股方法／gross／net／excess、缺件或未成熟。首屏明示目前觀察價格／年度計畫限制，source/version/clock 診斷可展開。保存結果重讀不查較新 DB；不同 parent 收據、hash 損壞或失效 child 拒絕。取消／返回不套用晚到結果，可重試相同收據；CLI 若取消時已發布會回報 saved=true 與 receipt_path，保存歷史保留。

source missing／expired calendar／原決策價 revision 時，先核對 exact 路徑、版本與截至日期；不要補 0、改日期、造 available-at 或用現價修舊保存。當日資料缺少仍列 incomplete observation；未成熟不能當失敗或負 label。endpoint-only，不提供 MFE/MAE／期間停牌／成交能力；研究毛報酬不作模型效果或個人投資收益證據。詳見 [實際來源／保存／日報 QA](../06_qa/UX21_SOURCE_STORE_DAILY_20261006.md)。


本批補正：保存收據首屏同時顯示已知價格缺件筆數與未成熟狀態，未成熟不隱藏原決策日缺價；明示未調整收盤價，非含息總報酬。完整source診斷仍可展開。


<a id="manual-tail-046"></a>
## UX21 endpoint label → UX22 公平比較 readiness（2026-10-06，有界研究入口）

入口為 `scripts/run_rule_research_label_readiness.py`。先選同一來源的原 parent 與保存 outcome `receipt.json`；準備自己的明示版本化 label policy 與 train/evaluation split JSON，再執行：

```powershell
.\.venv\Scripts\python.exe scripts/run_rule_research_label_readiness.py --receipt <parent-receipt.json> <outcome-receipt.json> --label-policy <label-policy.json> --split-policy <split-policy.json>
```

多批研究可重複 `--receipt PARENT OUTCOME`，最多32對，不能把同收據重複計入分母。政策／split省略會列未設定缺件，不代選目標、成本或基準。stdout JSON可用 `Out-File -Encoding utf8 <明示研究報告.json>` 保存；同樣的收據與政策用新程序重跑，核對report identity與逐列來源／分母，而非讀較新DB更新舊結果。輸入JSON上限64KiB、label列4096／報告2MiB，重複key／未知版本／超限拒絕，不截斷分母。

label policy範例只是格式，請按研究問題明示自己的值；不是使用者預設：

```json
{"schema_version":"rule-research-label-policy.v1","policy_id":"my-endpoint-target","version":"1","measure":"gross","horizons":[5,10,20]}
```

`measure`可為gross、net、gross_excess、net_excess；`horizons`是5／10／20非空唯一子集。gross取原毛報酬bp，net須有原封存成本政策，excess須有同endpoint可比基準；缺件保留null與原因，不當0。政策id／version及內容hash綁來源與樣本，不能混政策／方法分數。

split格式：

```json
{"schema_version":"rule-research-label-split.v1","split_id":"my-fixed-window","version":"1","train_start":"2026-01-01","train_end":"2026-06-30","evaluation_start":"2026-07-01","evaluation_end":"2026-09-30","training_as_of":"2026-06-30"}
```

日期只是格式範例，需依封存研究期間明示；train不能與evaluation重疊，training_as_of必須早於評估起點。label期末不能跨入評估，availability須在training_as_of可得；評估行不回流訓練。單決策日、未成熟／缺價格／未知availability會有空分區與原因，不冒充walk-forward fold。

結果保留全母體、matched／notmatched對照及excluded／unknown／uncaptured分母；符合方法不是交易selected。研究label bp與時間合格候選分開看；baseline readiness列既有learner／same-sample比較器缺的feature registry與決策時可得證據、完整return/downside映射、champion／challenger prediction身份及k。缺輸入就是不可評估，不宣稱模型勝出，也不把downside填0。

保存來源current-observed／年度計畫calendar的限制仍在；PIT、training、formal、natural authority及execution資格維持false。endpoint-only沒有MFE／MAE／期間停牌評估；本入口沒有fit、模型發布、Task／DB寫入。wrong parent／來源pin失配請重新選原exact配對；invalid policy／split請修正自己明示JSON；未成熟、成本或基準缺件需另有合法來源，不能靠改readiness旗標解決。詳[QA](../06_qa/UX22_LABEL_READINESS_20261006.md)。


<a id="manual-tail-047"></a>
## UX22 同源模型公平比較（2026-10-06，研究用 CLI）

先保存 exact parent／outcome 收據，準備上一節的 label／split JSON，再明示 comparison policy 與既有特徵／預測匯出 bundle：

```powershell
.\.venv\Scripts\python.exe scripts/run_rule_research_fair_comparison.py --receipt <parent.json> <outcome.json> --label-policy <label.json> --split-policy <split.json> --comparison-policy <comparison.json> --inputs-bundle <inputs.json>
```

預設白話摘要說明 ML 是否有可比較證據、共同樣本與流失；加 `--json` 輸出完整有界診斷／report identity，可另存研究報告並在新程序以相同輸入重讀。多批可重複 `--receipt`，最多32對；不得重複算母體。未提供政策／特徵／baseline／candidate，就是缺件／不可評估；不自動選模型或用空結果宣稱通過。

comparison JSON 格式如下；所有值必須由研究者明示，範例不是系統預設：

```json
{"schema_version":"rule-research-fair-comparison-policy.v1","policy_id":"my-common-target","version":"1","method_id":"daily_market.close_above_ma20","horizon":5,"metrics":"return_only","top_k":1,"downside_threshold_bp":null}
```

一次選定一個原方法與H5／10／20，必須包含於label政策。return_only只計報酬／排序；return_and_downside須明示整數bp門檻，endpoint報酬小於等於門檻才為downside，並非期間最大回撤。top_k須介於1與共同樣本數；不足時不可評估，不縮小k。排名指所選固定評估窗的共同樣本，不代表每日交易選股。

bundle為版本化JSON匯出：CORE20完整feature slots、dataset／feature schema與registry hash、逐樣本原來源hash、既有MLModelRecord及整數版MLShadowPredictionRecord、兩角色training audit／target_contract。模型的target_contract須對齊label政策／schema／measure／horizon／downside門檻／成本／benchmark；不把未標目標的模型自動當成相同目標。沿既有shadow request契約，特徵最大日期與available_date都須早於決策日；預測available_date可等於決策日。未知／缺槽保留缺件，不補0。兩模型必須使用同一feature snapshot和原決策來源hash。bundle的binding_sha256是事後標籤對齊封套，不能回寫為原始預測來源。

完整母體／方法行／所選目標／共同可評估樣本分母分開列；逐樣本保留缺label、feature、baseline／candidate prediction或不相容原因，兩角色只對同序共同sample IDs計分。同源、日期、split、成本、基準及標籤版本不相容時拒絕混算；報表的共同樣本coverage不代表全母體100%。MAE／Brier越小較好，precision／NDCG／bucket monotonicity越大較好，差異只描述研究樣本；沒有共同樣本就沒有優劣。

模型MAE指平均絕對預測誤差（bp），不是交易期間最大不利波動；precision是原計分器所定義的top-k正報酬比例。endpoint資料仍不能計算期間MFE／最大不利波動或停牌影響。

政策輸入64KiB、bundle／報告2MiB、label行4096；重複JSON key、未知版本、浮點／bool預測、超限或身份失配拒絕，不截斷。錯配請核對原exact配對與原匯出，不重跑來源或用最新DB補舊預測。來源current-observed／calendar及availability限制仍在，training／PIT／formal／natural／execution皆false、selection unknown；不fit／部署／載入模型pickle／寫registry、Task或正式DB。受控fixture只能驗工程，不能證明真模型改善。詳[QA](../06_qa/UX22_FAIR_COMPARISON_20261006.md)。


<a id="manual-tail-048"></a>
## UX23 隔離 shadow 工程狀態與收據（2026-10-06）

沿上一節 exact parent／outcome、label／split／comparison policy 與既有模型輸入 bundle，另明示 case-id 及 lifecycle DTO 匯出。這個 CLI 只驗研究投影能否執行、保存或回退；沒有啟用、正式推薦、重訓或排程操作。

```powershell
.\.venv\Scripts\python.exe scripts/run_rule_research_shadow_acceptance.py --case-id <具名研究案例> --receipt <parent.json> <outcome.json> --label-policy <label.json> --split-policy <split.json> --comparison-policy <comparison.json> --inputs-bundle <inputs.json> --lifecycle-export <lifecycle.json>
```

預設只預覽。預設摘要分三軸：「工程可執行／資料或效果未合格／未啟用」；缺候選模型、資料不相容或執行失敗會保留規則路徑。`--json` 才展開 comparison identity／binding、模型與來源版本、分母、lifecycle 和診斷。不把未知 availability 或零合格樣本改成通過，研究分數也不等於自然效果或採用接受。

`lifecycle.json` 明示 schema_version=`rule-research-shadow-lifecycle-export.v1`、model_id、dataset_id、artifact_hash、metadata（完整 candidate model_pin，須 canonical 相同）、events（既有 ModelLifecycleEvent 的 event_id／model_id／event_type／created_at／reason）。模型三個 pins 必須與 candidate 相同；事件依匯出原順序核對既有轉移規則。空事件表示尚無啟用事件，缺整份匯出則缺件。即使匯出含 activated_for_shadow，本入口仍未啟用任何實際 overlay；disabled／superseded／rollback_requested／review_required 使隔離投影停止。匯出是聲明，未驗真 registry 或模型訓練 lineage；不開啟資料庫。

需要保存時，在同一命令明示 `--save --store <隔離子目錄>`。store 只接受 repo output/qa 或系統 Temp 下的獨立子目錄；保存前後重新讀取全部輸入及 exact 來源並核對身份，沿既有同目錄 atomic capture＋receipt writer。保留 256KiB capture、128 筆／8MiB retention、200GiB 剩餘容量安全線，不提供繞過選項。同版重試 duplicate 保留第一次 observed_at；不是新自然預測。

```powershell
.\.venv\Scripts\python.exe scripts/run_rule_research_shadow_acceptance.py --store <同一隔離子目錄> --identity <保存回傳的64位SHA>
```

重讀只接受 store／identity 及可選 `--json`，不讀 latest、不查 registry／DB 或今天行情。收據凍結保存時的研究狀態，並非現在模型控制狀態。要留下停止判定，在原預覽命令加 `--stop-reason <原因>`，可明示保存一份新的停止收據；它只停止此隔離研究投影，不寫 disabled 事件、不改實際模型或舊收據。既有收據與停止收據都始終未啟用。

排錯：模型／資料集／artifact 版本失配、非法事件鏈、缺 candidate 或比較拒絕都回退規則路徑，核對原匯出與 exact 收據後另預覽；不要補最新資料或覆寫舊版。容量不足、來源修訂、writer busy、殘件或 hash 失配拒絕發布；取消不發布完成版，重試仍重驗來源。partial 證據保留且後續 fail closed，需人工檢視，不能用本入口清除。政策及 lifecycle 匯出各64KiB、bundle最多2MiB、合併輸入context最多2MiB＋128KiB；超限拒絕不截斷。CLI 參數／檔案／保存錯誤 exit 2，研究缺件摘要仍是安全研究結果，不能據 exit 0 宣稱效果合格。

UX23 只有有限工程 partial。自然預測封存、成熟讀回、漂移監控、具名採用條件、真模型優於基準、正式回退／啟用及真人驗收仍缺；training／PIT／formal／natural／execution 與 shadow_enabled 全 false、alpha 0、selection unknown。驗證與限制見 [UX23 QA](../06_qa/UX23_SHADOW_ACCEPTANCE_20261006.md)。


<a id="manual-tail-049"></a>
## UX08 推薦保存結果的同版價格／MA20／MA60（2026-10-06）

入口與操作：在「推薦」執行分析並保存該次結果；再從保存推薦的個股研究入口，或研究頁「使用這筆保存來源」，開啟價格／技術頁。新 writer 會連同該次推薦封存原來源價格、既有MA20／MA60，原生圖、精確價格表及MA歷史表共用同版列。重新載入與新程序重開都讀該結果版本；返回仍保留原来源。取消背景讀取保留已載入版本，可重試；舊callback不會覆蓋新請求。

參數與範圍：沒有新計算參數。每股最多最後120筆、最多64張圖、總capture 2MiB；完整推薦分母保留，超界或缺OHLC會明示缺圖，不改推薦結果。價格與均線使用Decimal保存值，精確表可查原小數；缺MA60／暖機資料顯示未提供並斷線，不自行重算。保存的行情截止日與scheduled決策日分開核驗，來源較早不會移到決策日。

結果判讀與限制：可見圖表只代表同版資料可重讀，不代表官方來源、當時已可得、PIT、方法有效、交易選擇或模型資格。來源明細使用 recommendation.market_frame／indicators；unknown可得時間維持unknown。其他區塊的原排名、基本面與方法仍各自核驗。圖表與完整精確表目前尚無產品縮放／平移／期間按鈕。

排錯：舊結果沒有artifact、原保存檔遺失、資料日／來源／版本失配或OHLC不完整時，原圖留缺件，不借今天資料。先確認選到正確保存結果／股票／決策日，可取消後重試；需要現況時明示按「另開最新研究」建立獨立來源，不修補原收據。不要手改保存artifact。保存圖有值而原方法／排名仍未知時，依各區塊缺件處理。Native／真人與舊結果補建尚未驗收。[工程證據](../06_qa/UX08_RECOMMENDATION_SAVED_CHART_20261006.md)。


<a id="manual-tail-050"></a>
## UX08 原生圖的縮放／平移／重設（2026-10-06）

原生圖支援鍵盤／十字線逐日期檢視；選取列與下方全量價格／MA 精確表同步，缺值顯示「未提供」，不補零。外部圖表只開啟已核對的五個來源 symbol（TWSE 2382、1477、00878、IX0001；TPEX 6488）；其他股票／未知來源停用，不能猜市場或沿舊回呼打開錯股。外連不授模型、PIT 或交易資格。

保存紀錄 marker 的工程 API 已接到 view，但主程式來源 reader 注入仍待完成。只有原保存紀錄的獨立 custody hash pins、精確股票／來源／結果／日期／cutoff／帳戶、明示 account kind 與 aware 保存時鐘均核對通過，才畫推薦確認／已記錄買入／已記錄賣出。推薦確認沿 research 帳，不等於實際成交；Paper、缺欄、naive 時鐘、失配或晚到來源拒絕，不借 report.events 或今天資料。舊手動 writer 的未知保存時鐘不補填，診斷 saved_record_clock_unknown；目前未接 reader 的畫面缺 marker，應先核中央來源接線，勿改原紀錄或降低 guard。[marker 與來源閉環證據](../06_qa/BALDR_B05_CHART_INCREMENT_20261006.md)。

入口：在個股研究「價格／技術」頁，原生圖下方按「放大」「縮小」「往較早」「往較新」「重設全部」。放大將可見日期槽約減半、縮小約加倍；平移約目前槽數四分之一，最少一筆；日期均是已核對來源已有資料，不補休市日。範圍列顯示可見日期及可見／總筆數，完整來源日期另標示，下方價格和MA精確表保持全量。

使用與判讀：游標移到目前圖上日期槽，可看當日原精度開高低收／成交量／既存MA。缺價格槽不壓縮日期，缺值顯示未提供並中斷折線；MA缺值同樣斷線。邊界或空資料會停用相應按鈕。反覆點擊不超出原資料，重設返回全量；沒有更改原artifact或重算均線。

重新載入與安全：只有完整同股／來源／版本／cutoff／context才保留可見日期交集，未知或改版自動全量重設。取消背景重讀保留原圖與範圍，重試同版本保留；返回保留來源，新開view從全量開始，不把viewport偏好寫到DB。缺保存圖仍不借live；需現況可另開最新研究。

排錯：若重畫失敗，圖與控制停用，下方全量精確表仍可查看；可重讀該來源重試。可得時間／暖機未知仍未知，可縮放不代表PIT／模型或交易資格。Native／真人及更多指標markers尚未驗收。[按鈕與來源驗證](../06_qa/UX08_VIEWPORT_INTEGRATION_20261006.md)。


<a id="manual-tail-051"></a>
## 明示市場CSV隔離預覽與執行CLI（2026-10-06）

入口為 `scripts/export_market_csv.py`，目前只有獨立CLI，不在App主選單自動啟用。必須使用Windows且可鎖定來源／目標完整目錄鏈。必填 `--market-root` 與 `--destination-root` 絕對路徑，`--file` 可重複但每次只明列一個相對CSV；目標必須全新、父目錄已存在，不接受整包FA_Data、glob或SQLite。`--personal-root` 預設market-root/personal、`--legacy-output-root` 預設market-root/output，兩者只解析與排除，不建立或啟用。

操作步驟：先不加execute執行preview，stdout JSON列出檔案、體積、來源版本／SHA-256及排除項，不寫目標。caller核對明列來源與預覽後，自行保存UTF-8 preview JSON到來源／personal／output／目標以外的隔離路徑；再同時明示 `--execute --accepted-preview <absolute-preview.json>`。單給接受檔不會隱性執行，來源修訂或hash失配會blocked，不自動接受新版本。此輪只完成synthetic fixture驗收，真來源匯出或分享仍未授權。

```powershell
# 只讀明示樣例預覽；請自行替換隔離fixture路徑，不使用真FA_Data整包。
.\.venv\Scripts\python.exe scripts/export_market_csv.py --market-root "<absolute-fixture-market>" --destination-root "<absolute-new-fixture-target>" --file daily_price/fake.csv
# caller已核對及保存preview後的明示fixture執行：
.\.venv\Scripts\python.exe scripts/export_market_csv.py --market-root "<absolute-fixture-market>" --destination-root "<absolute-new-fixture-target>" --file daily_price/fake.csv --execute --accepted-preview "<absolute-reviewed-preview.json>"
```

結果：preview不是來源hash接受或完成包；execute只有canonical `market-csv-export.v1.json` 精確檔名、原handle identity及bytes hash核驗後回傳completed與檔數／體積。收據只含明列市場檔metadata，不包含私人root／檔內容，不上傳或分享。白名單與hash不能證明每欄都非私人或有來源授權，真來源需另核對。

排錯與取消：Ctrl+C合作取消回傳130，blocked／IO回傳2；保留partial／pending，沒有本次canonical收據不能當完成。既有目標不覆寫，取消／失敗重試必須明示另一全新目標；來源pins不變可沿原接受preview，來源已改版需重新預覽核對。no-follow／sharing／來源版本不合或SQLite偽裝拒絕時依code處理，不降級copy、手改收據或清理原資料。長路徑canonical receipt錯名已修正並驗證；超Windows普通open限制的其他既有工具仍需短隔離fixture。此CLI不是personal migration／啟用／分享工具。[限定驗證](../06_qa/MARKET_CSV_EXPORT_INTEGRATION_20261006.md)。


<a id="manual-tail-052"></a>
## 私人覆盤與 notes 備份工程入口（2026-10-06）

這些入口目前供隔離工程驗證，尚未在主選單提供備份按鈕，也未批准真私人資料遷移或啟用。`personal_store_root/personal_store_mode` 只選一般私人 store；notes 仍須明示原 `personal_journal_root/personal_journal_mode`。私人覆盤 writer 必須由中央注入相同私人 TRADES 路由及帳戶的 Portfolio service，notes 必須同一 personal root；缺設定、錯帳戶或混用 roots 會拒絕，不借 legacy 或市場覆盤。市場 Evidence／Gap／Decay 僅唯讀引用，覆盤保留原來源 DB、事件身份與 hash；私人資料不寫入市場來源庫。

notes 備份 adapter 為 `PersonalNotesBackupAdapter(journal_paths, store_identity=..., max_bytes=...)`。identity 必須是 caller 已確認的 store 身份，byte budget 為本次接受的最大 notes 位元組數，不能省略或以未知容量代替。先呼叫 `backup(snapshot_path, receipt_path)` 做 dry-run：只讀原 notes，回傳 size／SHA256／預計 receipt，不建立輸出。兩個新檔必須直接位於原 selector 的 `backups/research_notes`，既有檔不覆寫。隔離 fixture 核對後加 `confirmed=True`，才以 create-only 建立 snapshot 與 receipt，並讀回驗 hash；正式來源仍須另有具體批准。

還原先取得並獨立保存原 receipt 的 SHA256 pin，再明示另一個 target `PersonalJournalPaths`，呼叫 `restore_into(target, receipt_path, expected_receipt_sha256=...)` 預演；核對 schema、identity、原 source 引用、snapshot 路徑／size／hash 後，隔離 fixture 才可加 `confirmed=True`。target 只允許該 selector 的精確 notes JSONL，必須尚不存在，不能覆寫既有筆記或複製整份市場 DB。成功後以同一 target selector 在新程序讀回，確認身份與內容。

排錯：pin／schema／identity／size／hash 失配先停下核對原收據；不可手改 hash、改用另一帳戶或借 latest。超 byte budget、超32KiB receipt、link／hardlink 或錯根目錄會拒絕。預演與操作前取消不建立輸出；開始建立後的取消或失敗會保留部分產物，不能稱完成，也不自動清理；再次操作需另選全新輸出。路徑根與父目錄須由 caller 控制，普通前後 fstat 不保證抵擋惡意競態。備份不授 PIT、模型、交易或正式啟用資格。[覆盤證據](../06_qa/BALDR_B10_PRIVATE_REVIEW_20261006.md)、[備份證據](../06_qa/BALDR_B10_NOTES_BACKUP_20261006.md)。

<a id="manual-tail-053"></a>
### UX23：明示 registry snapshot 的唯讀 metadata 核對（2026-10-06）

在既有 `scripts/run_rule_research_shadow_acceptance.py` 的 receipt／case／policy／bundle 輸入後，加 `--registry-snapshot C:/absolute/consistent-registry.db`，只允許明示絕對路徑。與 `--lifecycle-export` 互斥；後者只是匯出聲明，CLI 明示未連庫核對。`--json` 的 `diagnostics.registry_readback` 區分來源、狀態、SHA256、缺件原因與未驗 metadata 欄位。成功只表示 stored metadata 符合完整 candidate pin；training_audit／target_contract 仍未驗，模型資格未知、所有 eligibility false、未啟用。

缺件／鎖定／錯來源／schema 或 version 不符維持 rule-only fallback。WAL header 或 wal/shm/journal 殘件顯示需要受控一致 snapshot；不要藉本工具對真 DB checkpoint、改 journal mode 或移除 sidecar。工具不讀 artifact、不反序列化模型、不寫 registry、不 adopt／rollback。若需保存，沿用 `--save --store` 指定 output/qa 或 OS Temp 子目錄；保存前重讀變更則拒絕，新程序 `--store ... --identity <exact SHA>` 可讀同收據，不連庫或選 latest。取消可重試，不發布取消結果。此入口是 CLI 研究 consumer，非正式 shadow 啟用。驗收見 `docs/06_qa/UX23_REGISTRY_INTEGRATION_20261006.md`。


<a id="manual-tail-054"></a>
### 2026-10-06 工程能力字典與模型輸入介面

八族能力目錄供研究員查缺件：`list_rule_research_families()`／`get_rule_research_family(family_id)`（實際具名API以B11 QA與module為準）回唯讀能力、所需欄位、暖機、來源參照、成本與限制。未知id回unknown，不自選方法。現有MA20／60同屬一族；BBANDS30／2／2／SMA上軌有限比較仍是候選，三band保存與compression定義未具備，不能當第二family已開放或投資訊號。[B11能力與限制](../06_qa/BALDR_B11_FAMILY_CATALOG_20261006.md)。

`prepare_model_input`／`run_prepared_model_input` 是隔離工程API，無新GUI訓練／模型啟用按鈕。caller明示政策、時間切分、實際sessions、六份原bytes pins、同母體方法分母與training preprocessing audit；缺U2或未支持政策waiting，hash／成熟／split等失配reject_fit，兩者均不呼runner。僅synthetic://offline且明示endpoint gross return契約可ready；ready也不准fit、不載模型、不取得正式PIT／自然成熟或模型效果資格。結果只讀有界原receipt bytes並核身份／hash，不信runner旁路欄位。[B13精確參數與receipt schema](../06_qa/BALDR_B13_MODEL_INPUT_20261006.md)。

研究實驗室結果頁展開「研究歷史查找」，按「查找既有歷史」讀各來源，搜尋過濾已載入項目；選筆後重新核exact kind/run/hash/stock/context再開原結果。forward／unknown僅metadata，缺件不建庫／不補今天行情。每來源row上限200（介面可至1000），另有UI明示serialized讀取單檔64MiB／整輪256MiB預算，兩者用途不同；超限、來源變動、active SQLite sidecar需核原source後再查，入口不修來源。取消／切換／關閉父視窗拒晚到結果。原baseline fixed1.0／next_open執行保存規則可下鑽，但source-only／performance／PIT不升資格。[B07操作與排錯](../06_qa/BALDR_B07_RULE_HISTORY_20261006.md)。


<a id="manual-tail-055"></a>
### 2026-10-06 中央私人三帳與原紀錄圖表接線

`personal_store_root`／`personal_store_mode`須成對明示；blank或缺一項在legacy建目錄前拒絕。主程式將選定route與paths一起注入實際交易、聲明持倉、Paper唯讀服務，沿既有default與paper-main身份；未設定仍走原相容模式，不代表私人store已正式啟用。Paper固定state／benchmark／cost／status／baseline路徑，未知／缺件不借legacy env；精確ledger需caller另明示路徑與namespace，本入口不自建。[B09 API與custody](../06_qa/BALDR_B09_PERSONAL_PORTFOLIO_20261006.md)。

個股研究成功讀入後，原紀錄marker由背景工作載入，畫面context變動先清空並拒過期回傳。只用該次已核source／account／result／日期／snapshot及原保存rowpins；非同步不重跑推薦、不讀report.events當交易。原JSONL讀取限16MiB／5000列、每來源selected pins128，超限或來源變動明示diagnostic；只讀不建庫、lock或目錄。缺aware時鐘、source、actual帳戶宣告或exact lineage不畫標記；推薦確認與actual買賣分別呈現，Paper不冒actual。舊naive紀錄仍未知，新的手動交易保存aware觀測時間也不補來源或PIT資格。

目前標準UI確認保存仍漏source_id，不能藉row猜source而畫標記；三檔最小修補擴鎖遭automatic approval review拒絕，父層已向人類直接確認。已具原source_id的保存紀錄reader與中央接線工程已驗，不能把其有限通過解讀成所有UI確認都可畫。[中央整合與剩餘](../06_qa/BALDR_SECOND_WAVE_INTEGRATION_20261006.md)。

B14 `ShadowControlService.apply`預設預覽，execute需caller提供exact command／proof／原sourcepins／最後核准rule及獨立持久state custody；resume本包拒絕。只在新的synthetic namespace/root驗停止模型callback→exact rule route→freshprocess讀回，保存receipt不是正式模型控制核准。尾端receipt缺失／損壞、witness不符或CAS失配皆拒dispatch，不刪receipt假裝恢復。prediction成熟／漂移仍在獨立composition包，未知正式資格不提升。[B14純port操作](../06_qa/BALDR_B14_SHADOW_CONTROL_20261006.md)。


<a id="manual-tail-056"></a>
### 2026-10-06 B14 隔離預測封存與監測 API

入口為 rule_research_shadow_evidence_composition／store 的注入式 API；目前沒有新增 UI 按鈕或 CLI，也未接正式模型／Task。先沿 B13 公開 prepare/run 取得 synthetic offline 原結果，caller 明示 exact model revision、method、aware prediction availability／decision cutoff／timezone，再呼 freeze_shadow_evidence。原 result payload、六種 pins 及 metadata 不重造；來源 clock／資格不足不得補值。

操作順序：caller 獨立核 frozen binding 與持久 witness → ShadowEvidenceStore.create 明示全新 Temp／lane output absolute root 和 synthetic:// namespace → append(expected_revision=..., execute=False) 預覽；只有隔離工程確認後 execute=True 才發布 receipt → read_all 逐版本原bytes回驗。新程序使用公開 prepare 重建seal再run replay，不保存私有seal。預覽可能使用暫時exclusive lock，並非完全零I/O；不發布receipt。

監測參數必須明示 policy id/version、target/label/split hashes、完整method ids、exact監控model、最少成熟樣本與最大MAE整數bp。ReadonlyResearchPort回傳原label/fair reports bytes與原pins／available_at；evaluate_shadow_monitoring在cutoff核成熟、同股同日去重、完整分母及原candidate identity。未知來源availability／不足樣本／缺政策回waiting，不以0冒充成熟；超caller門檻為review_required。原wrapper目前unknown→waiting；另有synthetic known-clock工程閉環，不能互換資格。

控制預設execute=False。只有完整重驗monitoring、原prediction pins、caller獨立proof與已核最後rule後，apply_monitoring_control才交原ControlPort；synthetic spy與新程序已驗stop後不再呼模型、同rulehash。resume未准；全部正式／PIT／自然／訓練／執行資格false。

容量為隔離資源契約：128 receipts、每份16MiB、8192 label rows，原control pin容量另保留，不截斷大batch。取消／逾時在witness CAS前拒發布；CAS後完成發布與readback並回報真commit。若CAS後I/O發布失敗，witness領先receipt會使整namespace不可用、failclosed；保留殘件／獨立witness供排錯，不刪receipt假恢復、不自動清理或重用root。詳[完整API與兩路收據](../06_qa/BALDR_B14_SHADOW_EVIDENCE_COMPOSITION_20261006.md)。

<a id="manual-tail-057"></a>
## 2026-10-06 私人 Paper daily／benchmark 選取入口

本節對應P2已驗合成工程scope；正式私人writer啟用、migration與Task仍須既有明示授權。市場由TWStockConfig的DATA_ROOT/db_file或獨立 `--market-db` 唯讀來源提供，不從private或legacy output推導；市場main／journal/wal/shm及祖先不得為hardlink、symlink或junction，異常具名拒絕而不降級為可用。

已解析私人設定須成對明示 `PERSONAL_STORE_ROOT` 與 `PERSONAL_STORE_MODE=personal`，市場 `DATA_ROOT`、legacy `OUTPUT_ROOT` 仍各自獨立。以既有可信portfolio identity使用 `scripts/run_paper_portfolio_daily.py --portfolio-id <已解析帳戶> --decision-at <帶時區時間>`；selected模式的baseline/state/cost/status固定由同一Paper route＋paths選取，不採 `PAPER_EXECUTION_LEDGER_DB` 借legacy。此腳本是writer入口，未授權正式操作時只使用隔離synthetic資料，不因本節自行執行。

benchmark使用 `scripts/build_paper_equal_weight_benchmark.py --portfolio-id <同帳戶> --benchmark-id <已知benchmark身份>` 先preview；只有已授權caller明示 `--confirm-build-paper-benchmark` 才出版新ledger。benchmark身份獨立明示，不能由portfolio猜；既有output保留、競態目標不覆寫。preview/confirm=False/cancel不出版benchmark。legacy_read_only可讀preview但拒writer。

selected時可省略既有path override；若提供 `--baseline`、`--state-db`、daily的 `--ledger-db` 或benchmark的 `--output-ledger`，必須exact selected path。`--output-root`仍為config的legacy output定位，不能另選private writer。無route的legacy benchmark仍要求原baseline/state/market/output四參數。不得以resolve先掩蓋alias，不能自動搬庫或退回legacy。

daily passed只代表本次Paper snapshot流程結果，不等於真成交、投資有效性或來源正式資格；future／未知交易日不建state或提高資格。exit2先核root/mode成對、空值、帳戶／benchmark、精確override與main/sidecars/祖先aliases；selected失敗只回JSON，不補寫legacy status。不要以刪除可疑temporary、改ACL、migration或正式Task解決；原bytes/hash／未知diagnostic保留。[P2具名QA](../06_qa/BALDR_PERSONAL_PAPER_PRODUCERS_20261006.md)記錄工程驗收與限制。


<a id="manual-tail-058"></a>
### 9.9.1h H20 gross 每日收據與 BBANDS 上軌保存版別（2026-10-06）

單批大盤研究保存若需有限 BBANDS30 上軌比較，沿既有命令加 `--include-bbands30-upper`；預設不加仍為 v2。v3 保存原 BB_Upper，個股頁依已保存 manifest 讀回同版 fingerprint。close > upper 是有限比較，缺 band／30 根有效連續 OHLC 時為 unknown；不代表 compression 完成，也不授 PIT 或正式模型資格。parent-universe + 此旗標目前拒絕，請使用明示的單批範圍。

每日既有 canonical capture／自然 outcome 入口：

```powershell
.\.venv\Scripts\python.exe scripts/scheduled/run_personal_model_daily.py --request-json <絕對request路徑> --request-sha256 sha256:<raw64hex> --receipt-root <獨立receipt根> --gross-fit-receipt <可信原fit收據絕對路徑> --gross-fit-receipt-sha256 <已核raw64hex>
```

request schema 為 `personal-model-daily-request.v1`，必須明示 canonical recommendation root、個人 capture root、隔離 outcome root、原 market DB／calendar cache pins、aware evaluation_at 與 result_ids 或 capture_paths。欲讀 gross 加 `gross_model_contract_hash`，必須匹配由原 fit receipt 重建的契約；gross flags 不成對或身份不符會在每日 I/O 前拒絕。已有模型的 return head 以整數 bp 展示 H20 absolute/no-cost，不能從 probability 或 after-cost head 推導。自然 outcome 未達20交易日或官方 calendar 缺件時 pending／unknown，保留原資料，不補時間與結果。

今日十檔 current-observed 真模型推論已保存 QA，但尚未接成此 canonical 每日 ingress，也未啟用正式 Task。請勿把 QA 預測檔當 RecommendationResult、把 frozen 舊來源當今日資料，或改 source marker/PIT 來通過。預覽／來源核驗與正式啟用須保留 exact model、source、帳戶與 private-root 身份；有錯誤先核 request raw pin、來源 receipt、contract hash、模型／lineage 兩個 cutoff 及 no-follow 權限，禁止放寬 guard。


<a id="manual-tail-059"></a>
### 9.9.1i 個人 H20 每日研究預測、配置與回滾

已選私人模型根為 `{DATA_ROOT}/personal/recommendation_h20`，本機 `D:/Min/Python/Project/FA_Data/personal/recommendation_h20`；市場 DB 與其他個人領域維持原路徑，不搬移。不得整包匯出 FA_Data 而包含 personal 子樹。配置使用 `activation.json`，以 immutable revision 歷史備份及 expected-revision CAS 發布。`scripts/prepare_personal_h20_activation.py` 預設預覽；明示 `--execute` 才寫配置。啟用須可信 fit receipt 原 bytes SHA、模型 contract、scope 與精確 root；停用不依賴模型可讀，寫新 disabled revision，保存預測與歷史不刪。精確命令見 [中央整合 QA](../06_qa/BALDR_PERSONAL_MODEL_ACTIVATION_INTEGRATION_20261006.md)。

既有 Pacific 05:45 calibration-learning Task 的帳號、權限、trigger、action 與 settings 不變。cmd 在上述配置存在時傳 `--personal-h20-activation-config`，或採明示 `PERSONAL_H20_ACTIVATION_CONFIG`。disabled 不呼模型；enabled 只接同-run completed raw-cycle 原 pins，使用原 frozen H20 absolute/no-cost return head，不要求重新 fit 或 entry capture 已收盤。原 formal/global blocked 仍獨立揭露。

開啟「個股研究」摘要可查看個人 H20 gross 預測、精確 bp、決策日、來源日、特徵日與觀測時鐘。公開 reader 核原模型／來源／保存 raw pins，背景讀取不重算；切股、切來源、關閉或失敗的晚到結果不覆寫畫面。完整 cohort 保存並公開讀回成功，才發布只含指標的 daily manifest／product reference；預測原 bytes 唯一保存在 `h20_predictions`。缺列、錯 hash、來源不可核或錯模型顯示等待／不可用，不借舊數字冒充本次成功。保存預測不等於值得買或交易授權。

真時鐘跨午夜時，決策日可為 10/07、來源日 10/06、特徵日 10/05，三者分列，不回填前日。相同 cycle/model/symbol 重試讀第一次輸出，不造新自然樣本。自然結果需原 no-model entry/outcome 的 decision/cycle/source/features 精確一致及二十 session 成熟；缺 entry 如實 pending，不阻止日常推論。holdout Brier 2730 對 null 2500，劣於基線 230 bp，成本後效果未證明，持續揭露；未提升 formal/PIT/交易資格。

排錯先檢查原 raw-cycle completion、配置 revision、fit/contract raw pin 與 cohort 全範圍，不放寬 guard。回滾只發布 disabled 新 revision；不刪 receipt、不改既存預測。此 UI 已以合成 offscreen 驗證，未宣稱前景 Native／真人驗收。

<a id="manual-tail-060"></a>
#### H20目前用途與下一次排程（2026-10-07）

H20已真參與每日研究推論／原值保存，個股摘要讀其原預測；目前還沒有接入原推薦名單生成或排序。原推薦勝率／機率與ranking不變；H20 gross是未扣成本的20交易日毛報酬，不是勝率。日常H20 cohort研究列表／排序與exact下鑽返回、原entry/outcome自動pins接線仍需完成，不能用目前增量卡片宣稱模型選股已完成或全市場已預測。

既有05:45 Task下一次為Pacific10/07 05:45（當日UTC−07），UTC12:45、台北20:45；未手動啟Task。下一run應核新Task/source cycle identity、原manifest與prediction raw pins，不以舊產品指標或Task returncode單獨判H20成功。原global/formal blocked和personal success可分開為真；詳見 [下一run與工程差異QA](../06_qa/BALDR_NEXT_RUN_AND_REMAINING_ENGINEERING_20261007.md)。自然成熟不作工程gate，來源資格unknown不補。

<a id="manual-tail-061"></a>
### 2026-10-07 日常有限 BB 上軌版號接線補充

隔離研究 runtime 與 observation policy 可明示相同 feature_contract_version=daily-market-feature-snapshot.v3.bbands30-upper；缺欄保持原 v2。先整合 parent 新版 API，再依原明示 universe/source pins 執行 preview，核完整 declared cohort、同版 method hash，通過後才 execute。runtime/policy、各 segment 或保存 parent 異版會拒絕；請核配置兩處版號與原保存來源，不改舊 artifact 修補。缺件、30 根暖機不足或可得性未核保持未知。有限上軌比較不代表 compression 完成、不授正式/PIT/訓練資格。本中央接線尚待 BBP01 真保存鏈整合驗證，未修改正式 Task、配額或 200GiB capture reserve。H20 cohort 列表／gross 排序、自然結果批次 caller 與第三條件 UI 由三個排他 lane 續作，現有個股 H20 卡片不代表完整模型選股流程完成。

<a id="manual-tail-062"></a>
### 2026-10-07 中央整合：保存模型名單與自然結果

上述「目前用途」及三包待接敘述保留為整合前紀錄。推薦工作區已新增「個人模型選股研究（H20毛報酬）」分頁，讀既有私人 root 的 activation／product reference／完整 daily manifest，不重新推論。原 canonical 推薦勝率與排序仍有各自用途；模型分頁依已保存 H20 gross 排序選股研究。

1. 開啟推薦工作區的模型分頁，或按「讀取每日已保存模型名單」。背景核驗配置版本、模型 contract、cycle、manifest raw SHA 與每股原預測。配置未啟用或來源不可核時顯示不可用，不能用 QA／其他日期代替。
2. 選「預測毛報酬由高到低」或「由低到高」。數值用整數 bp 排序；同值按股票代碼，未知列後置且保留。母體是該 manifest 的完整 1–50 股，並非全市場。每列分列決策日、來源日、特徵日，跨午夜不改日期。
3. 選可核列按「研究選取股票」或雙擊。中央再次核同一份原 manifest／model／cycle／sample／prediction／capture pins 才下鑽；`sample_id` 不轉成推薦 `result_id`。個股報告沿該決策日，H20 卡核同一指標；指標已變更顯示不可用。
4. 由個股研究返回來源，先重讀再定位同一 selection。只恢復本次記憶中的 exact selection，跨母體、模型、日期、hash、缺件或關閉回呼明拒，不用同股最新結果冒充原列。重新啟動後先讀保存名單再選取。

H20 gross 是未扣成本的20交易日預測，不是獲利機率；高預測不代表買入。原候選的 Brier 2730 對 null 2500 僅是機率 head 品質揭露，gross 效果及扣成本效果另待自然資料成熟；不以此差異或未成熟作永久個人啟用 gate，不授自動交易、正式或 PIT 資格。

既有 daily invocation 取得新 manifest 後，沿原 no-model entry 保存結果呼完整 cohort caller。entry 的 cycle／decision／source／features 須由原 verifier 精確核對；成功後只在私人 `h20_natural_entry_bindings` 保存 manifest 與 entry pins 指標。未取到或跨午夜錯配仍回全員 pending，不登記錯誤 entry。未配置／disabled 不呼模型或自然 ports。

日後原流程取得受驗 outcome pins，用原 capture SHA 定址已登記 manifest，逐列呼原20-session verifier／projector；成熟 join 沿原 `h20_outcome_joins` create-only 保存，重試不重計、不複製預測、不掃 latest/glob。輸入與自然结果狀態分別見 learning 收據的 `current_observed_input_capture.personal_h20_natural`、`current_observed_natural_research.personal_h20_outcomes`。缺原登記保持 pending；不得事後借另一日期 entry 來補樣本。工程合成成熟案例不代表真自然品質已成熟。

排錯核 activation revision、manifest raw pin、完整 symbols、三日期與 entry/outcome 原 pins。變更指標後請重新選取；錯配不改舊 artifact／來源時間／hash。停用沿既有 disabled 新 revision，保存歷史不刪。原 Pacific05:45 Task 未改或手動觸發；下一自然 run 與實際效果需另核新 source cycle、manifest 和原預測，不能以工程測試當排程成功。

<a id="manual-tail-063"></a>
### 2026-10-07 BB 第三條件與收藏

每日研究條件頁新增「收盤價高於布林上軌（30）」，預設不勾。勾選先篩選該保存來源；明示按「更新研究快照」才 opt-in 產生 v3，重讀／排序／收藏／返回不計算新的指標。契約 timeperiod=30、上下2個標準差、SMA、strict above；等於上軌為不符合。30根有效 OHLC 暖機不等於官方 session 完整。

表格分列 BB 比較三態與原保存上軌值；v2未保存、缺件、暖機不足或方法未核顯示未知，來源參數 lineage 仍另列未知。AND／OR沿原規則；MA presets 會清除 BB 勾選。來源 tooltip 可查原 feature／warmup／manifest SHA，點股票沿原 exact DTO 下鑽返回。

BB 收藏沿原 Watchlist JSON 保留來源及查詢，重開核原保存 v3 manifest／完整股票母體／row／condition／方法 hash。v2 原收藏 body/hash 保持；缺來源、異版、錯 pin 不重算或讀 latest。可明示另查該 cohort 最新研究，但新版本不冒充原收藏。BBP01 parent-v3 完整日常保存鏈仍待直接使用者批准採入與中央增量驗證；本 UI 不代表該鏈已完成，compression／U1 未決不升格。所有 UI 驗證為 offscreen，未宣稱前景 Native。


<a id="manual-tail-064"></a>
### 2026-10-07 BB全母體日常v3採入補充

BBP01原parent producer／snapshot CLI已採入dev。隔離日常runtime與policy必須同時明示 `feature_contract_version=daily-market-feature-snapshot.v3.bbands30-upper`；CLI母體產製明示 `--parent-universe-config` 與 `--include-bbands30-upper`。未明示保持原v2，跨版policy不匹配時在產製前拒絕。保存後以原parent identity讀回三方法全母體分母；matched／notmatched／unknown／excluded／uncaptured分開，unknown不當0。UI BB預設不勾，明示更新後保存v3；收藏透過原Watchlist JSON重開，必須找到同SHA／日期／股票／條件，不以latest替代。

工程同版61案例及mandatory已通過，正式全市場自然日常run仍待原排程；不需改Task或手动trigger。前節等待BBP01批准為歷史狀態，現已依直接真人批准解除。私人資料不納入main發布包。


<a id="manual-tail-065"></a>
## Windows 可攜版啟動畫面

雙擊 baldr.exe 後顯示原背景與目前初始化階段；匯入套件時為不定進度，主視窗顯示後才完成。Esc 或 Alt+F4 可在安全階段邊界取消，程式會等待合作式 worker 退出；同步初始化呼叫須等返回。此進度不代表市場資料新鮮度或排程成功。載入失敗請看錯誤對話框指定的 log；缺背景圖仍有可讀文字與進度。應用程式與 exe 使用原圖示，既有 Windows 釘選快取未自動修改。完整首次設定、整個資料夾保留要求、圖示與排錯請見 [Windows 可攜版指南](../07_guides/PORTABLE_WINDOWS.md#啟動載入畫面與圖示)。

<a id="manual-tail-066"></a>
## 2026-10-07 真人回饋：摘要、收藏與推薦失敗

本章精確化真人驗收入口，並記錄原碼修正；其後獨立候選 `2026.10.06+2b6fda426b6f` 已通過同版隔離比較，原exe保留，不把工程回歸視為真人通過。候選與原日曆設定的啟動helper及證據見下方QA；helper只在使用者明示執行時開啟，沒有修改原設定或自動執行真人測試。

- H20：到「推薦分析 → 個人模型選股研究（H20毛報酬）」選取 2382，按「研究選取股票」（或雙擊原列），再看「個股研究 → 摘要 → 第一眼先看五個問題」。摘要應分開顯示未扣成本的20交易日預測、預測／來源／特徵日期、模型可用性與自然結果狀態；預測不是實際報酬。詳細來源在「顯示進階：來源與各區塊日期」。無法核驗或尚未成熟不得補零或借用其他日期預測。若一般個股報告讀取失敗，目前 H20 讀回不會啟動；本輪尚未證明 2382 的實際失敗原因。
- 返回：從上述原 H20 名單下鑽後，按「返回來源清單」，應返回相同保存來源並選取原股；其他來源各自核對自己的原身份。H20 **目前沒有本次驗收可用的研究收藏按鈕**，不能套用下一項流程。
- 收藏：「推薦分析 → 每日研究條件」載入已核驗快照並選股後，按「收藏此研究」，核對確認框才保存；重開到「觀察清單」核對原來源。原排名另可從個股研究按「收藏此原排名研究」。這兩者不等於 H20 cohort 收藏，也不表示加入持倉。
- 全股票推薦若顯示 `natural_market_official_calendar_unverified`／`official_calendar_unknown`，是共用官方交易日曆無法核驗；切換三個預設策略或放寬選股條件不能解決。修正版在主訊息說明日曆阻擋，完整例外保留於「詳細資訊」，未套用部分結果。
- 修正版 Python／exe 可透過共同 JSON 設定或環境變數 `OFFICIAL_CALENDAR_CACHE_PATH` 明示**絕對外部路徑**，使用原已保存官方日曆；環境變數優先於 JSON。未明示時沿 `RESEARCH_STATE_ROOT/output/paper_execution_eod_replay/calendar_cache`；直接 frozen 啟動也使用外部研究根，不找 bundle 內的本機 output。日曆讀取唯讀、不隱性下載；年度覆蓋、原 bytes hash、可得／捕捉時間及有效期限仍必須通過。缺件／過期由既有來源維護流程處理，不能手改時間或 hash、使用 fixture 或股票報價日期冒充官方日曆。
- 個人推薦模式的「已保存版本／讀取歷史版本／回退到所選版本」會依左側設定欄實際寬度改成上下排列。版本標籤可用工具提示讀完整文字，鍵盤 Tab 依序移動；回退仍建立新版本、保留歷史。

限定驗證與未驗項目見 [真人回饋 QA](../06_qa/BALDR_RECOMMENDATION_HUMAN_FEEDBACK_20261007.md)。


<a id="manual-tail-067"></a>
## 2026-10-07 施工版：完整保存母體瀏覽

本節描述 dev 原碼，尚未包含在現有候選 exe，尚未通過 Native 真人驗收。到「推薦分析 → 每日研究條件」上方完整保存母體區，按「查詢完整保存母體」，選來源再按「讀取所選母體」；「更多保存來源」繼續有界查詢。來源位置沿目前 OUTPUT_ROOT 的 research_snapshots/daily_universe，不查最新行情、不產生快照。沒有完整來源時會明示沒有完整保存母體，下方原單批研究仍可使用。

勾選價高於 MA20／MA60／布林上軌30，選 AND（全部符合）或 OR（至少一項符合）、狀態、排序方向及股票代碼後，按「套用全域查詢」。先以完整原母體篩選排序，再分頁；未知值雙向置尾。首屏分列宣告、納入、排除、已處理、待處理與缺資料數，排除與未知不當作不符合，單批個股來源不改完整母體分母。這三項為既有 v2／v3 條件，尚不是新 v4 五規則完整選股器。

選取列後按「開啟原保存個股研究」，沿原 parent／child 來源核驗；補充唯讀核驗結束後才開啟。按「取消」撤回待開啟請求；切來源／查詢或關閉時晚到結果不取代目前畫面。個股按「返回來源清單」保留同一份完整來源、查詢、排序、頁碼與選取。此完整 query 的收藏、比較與跨程序重開尚未接線，不能套用下方單批「收藏此研究」當完整 query 已保存。

來源缺件、身份／hash 不符或忙碌時保留原完成畫面與原因，不以 latest 或重新產生資料代替；先保留診斷並核對明示來源設定。正常 UI 產製入口、完整新五規則母體及新候選仍在施工，現階段不用真人重驗。


<a id="manual-tail-068"></a>
## 2026-10-07 dev 修正：H20 摘要獨立於一般個股報告

目前dev原碼已修正前節所述報告失敗不啟動H20的限制，現有候選exe尚未包含。到「推薦分析 → 個人模型選股研究（H20毛報酬）」讀保存名單，選2382（或其他可核驗列）按「研究選取股票」。個股研究最上方看「保存的個人 H20 研究預測」：未扣成本預測值、預測日、來源日、特徵截至日期分列；實際結果獨立寫明目前尚無已核驗結果，不能把預測當實際獲利。下方一般報告的「摘要 → 第一眼先看五個問題」仍顯示一般研究結論與限制。

一般報告讀取失敗時保留錯誤，原保存H20仍獨立核驗／顯示。讀取缺件或失敗會顯白話原因，完整診斷可看提示；按「重新核驗保存預測」只重讀目前選取原來源，不換成最新預測，不重新推論或訓練。原manifest／model／capture／stock或配置不符則拒絕；切股／切來源／關閉時晚到結果不覆寫。

按「返回來源清單」重核原版本後回到原股；若保存指標已變，保留原名單、排序與選取並說明無法精確返回，不以新名單替換。跨程序先重新讀保存名單再選股。H20目前沒有研究收藏入口；每日研究的「收藏此研究」及原排名收藏是另外的來源契約，不能替代H20收藏。此工程中央96項UI回歸通過，但新candidate／Native與真人原2382仍待後續，不要求現在重驗。


<a id="manual-tail-069"></a>
## 2026-10-07 新候選：H20 首屏修正與真人重測

前節「現有候選尚未包含」為施工時狀態；新候選 `2026.10.06+c589bc71e8f1` 已包含獨立H20摘要、完整v2／v3保存母體瀏覽與推薦窄欄修正。原exe仍保留。Windows PowerShell執行 `& "C:\Projects\PythonProjects\technical_analysis\output\qa\baldr_completion_m2_20261007\start_h20_feedback_candidate.ps1"` 可明示開啟新候選；helper只核exe SHA並向child提供原主機設定JSON與既有官方日曆，沒有修改設定或替換原exe。需保留候選整個資料夾；版本列核對上述版本。日曆仍須通過hash、coverage與期限，不能修改cache冒充成功。

這版真人重測四項：原H20名單2382下鑽後首屏「保存的個人 H20 研究預測」有數值／三日期／實際結果限制；返回原名單保留選取／排序；原三個預設策略逐一執行並確認成功或具名失敗；非全螢幕個人推薦保存版本／歷史／回退全文可讀可點。H20沒有收藏按鈕，不列此驗收。每日研究單批收藏仍沿前節原入口，完整母體query收藏與比較尚未接線。

固定原碼與exe的隔離同版及真保存source讀取流程通過，模型contract為明示合成邊界；合成2382的+12.34%不代表原私人2382數值。真人原來源與三策略尚未驗，這版不代表完整full-N新五規則或M2完成。收據與限制見[真人回饋QA](../06_qa/BALDR_RECOMMENDATION_HUMAN_FEEDBACK_20261007.md)。


新候選真人啟動補充（2026-10-07）：檔案總管開啟 `C:\Projects\PythonProjects\technical_analysis\output\qa\baldr_completion_m2_20261007`，雙擊 `start_h20_feedback_candidate.cmd` 會呼上述PowerShell helper啟動 `2026.10.06+c589bc71e8f1`，帶原主機設定與官方日曆，不需自行下指令；helper沒有自動執行。依前節四項核2382首屏、原名單返回、三個全股票預設策略、非全螢幕歷史控制項。H20收藏不列驗收；最新dev的full-N施工尚未包含於該候選。


<a id="manual-tail-070"></a>
### 五規則完整保存研究入口（dev施工，2026-10-07）

到推薦分析的每日研究頁，使用五規則保存來源區；讀取根為 output_root 下的 research_snapshots/technical_universe。按「查詢保存版本」，選版本後按「嚴格核驗並讀取」。清單列只是未核驗 metadata，不能直接當研究證據；取消／失敗版本仍列出原處理數與待處理數，不等於完整母體完成。

方法狀態、AND／OR、股票篩選與排序先對所選版本全部已完成分段套用，再分頁。排除、缺原始資料列、規則未知及待處理分開顯示；這些研究不授歷史 PIT／交易／績效資格。選列按「讀取原保存個股證據」查看五規則、決策截止、特徵日、理由、反證與限制；返回原名單保留原查詢，若原查詢已改變則提示重新確認，不改讀最新版本。

「產製新研究版本」需明示母體 JSON：schema_version 為 daily-market-technical-universe-v4-population-settings.v1，包含 universe_id、population_version、decision_date、raw_stock_codes、excluded_stock_codes、exclusion_reasons。截止為同日台北時間且不早於16:00。核對唯讀來源 db_file、分母與保存位置後確認；GUI只收設定及未核驗摘要，背景核驗通過才產製。取消準備不開始 producer。「續跑所選版本」固定原收據、母體、截止與來源；來源或 pins 不符、舊收據已有後續版本時拒絕，不自動改用最新。單次 child exact 讀取仍在返回後檢查取消。

「產製技術與官方來源研究」先選取已擷取的 `current_market_status_pointer.json`，再核對新研究母體與截止時間。背景工作先固定同版市場／處置來源，再產製技術母體；只有完整技術結果才保存聯合研究。來源觀測或發布晚於原截止時間、混版或缺件會拒絕，不會改日期來通過，也不會在此按鈕重新上網擷取。產製途中 pointer 更新不會替換已固定來源。

完成後「官方聯合研究已保存」會顯示資料夾、保存列數與來源涵蓋狀態；到「官方處置與市場對照研究（已保存資料）」按「選擇保存來源資料夾」選取該資料夾，再按「更新來源清單」、選取版本、嚴格核驗與讀取。來源涵蓋 partial 仍表示來源缺件，只供當下研究，不等於歷史 PIT／推薦或交易資格。若聯合保存失敗，畫面顯示「未完成」與原因；已完成的技術收據仍可在原清單查詢，不將它冒稱聯合研究成功。取消檔案選取不會建立產製請求；外部唯讀保存來源不啟用此按鈕。新入口仍在 dev 驗證階段，尚未包含於舊 EXE。

選列按「將所選股票加入比較」，可跨頁加入；兩檔以上按「比較原保存研究（2–256 檔）」。比較表列日期、截止、原始列數與五規則；選格後在下方閱讀支持、反證與未知原因。選欄返回會背景核驗其原查詢再選回原股票；失敗保留目前名單，跨來源不沿用舊日期資訊。

按「收藏目前查詢與比較籃」背景核驗原來源，成功後確認保存至觀察清單。比較籃須空白或2–256檔；只有一檔時請清空或補足，取消確認不保存。觀察清單「下一步」中的「完整母體技術研究收藏」可重新整理、選取並「重開所選研究」，還原原查詢、股票、捲動位置與比較籃，不用最新來源。來源缺件、身份或 SHA 不符時明示拒絕。背景忙碌時刷新會排隊一次；取消／關閉不套用晚到結果，原選取已刪除時不跳到其他收藏。移除收藏按精確身份處理，不以股票代碼刪除同股其他來源。

此入口仍在dev接受階段，未包含於0f25b8c6候選版。真保存來源／COW／新程序及實際按鈕路由已測；完整主視窗初始化、完整市場效能與Native仍待驗，不能據此宣告M2完成。

<a id="manual-tail-071"></a>
### 推薦理由閱讀修正（2026-10-07）

結果標題為「推薦結果與風險判讀」。選股後按「展開推薦理由」增加閱讀空間，「收合推薦理由」返回較小區域；不重算或切換來源。窄版個人推薦模式保留最低內容高度，歷史版本、來源與候選欄改垂直排列，透過外層捲動完整閱讀。此修正已含於0f25b8c6候選版，真人接受尚待。

<a id="manual-tail-072"></a>
### H20 打包版外部研究設定（2026-10-07）

打包版需要使用原保存研究根目錄時，由啟動環境明示 `BALDR_ML_RESEARCH_STORAGE_CONFIG` 為既有 `ml_research_storage.json` 的絕對檔案路徑。檔案保持 `ml-research-storage.v1` schema，只有 `schema_version` 與 `active_root` 兩欄；來源根目錄仍須通過原安全邊界。此設定只選擇既有研究儲存位置，不訓練或啟用模型，也不改個人模式資格。

未設定時維持原 repository 設定位置；明示設定不存在、空白、相對路徑、格式不符或不安全時停止讀取，不改讀其他根。打包資源內沒有機器專屬研究設定時，不應將未知列當作沒有預測。請先選取該列，在診斷區查看並複製完整原因，再核對明示設定與原保存檔案；研究按鈕仍只開啟已核驗來源。原檔／父路徑替換或 SHA 不符仍拒絕，同資料夾新增其他研究不再因父目錄時間改變而誤拒。

新候選版仍需同版核驗與真人重驗；c589 原候選版不支援此新增設定。

<a id="manual-tail-073"></a>
### 0f25 真人重驗後的閱讀與等待修正

真人已確認孤立的標題編號移除，個人模式窄版可讀；但推薦詳情仍被壓縮，H20 名單與2382下鑽等待過久。dev 的「展開推薦理由」現在按完整文件高度展開分數拆解、排名門檻、理由與限制，使用結果頁外層捲動；「收合推薦理由」恢復框內捲動，不重算推薦或更換來源。0f25 不包含此次再修正。

H20 分頁新增獨立等待提示：開始讀取後顯示尚未完成及已等待秒數，核驗返回後顯示股數與耗時，失敗顯示具名原因；「取消名單讀取」要求背景取消，晚到結果不套用。取消不代表目前正在進行的大檔驗證可立即中止。原來源庫共用核驗的效能修正仍在進行，不能以等待提示宣稱下鑽速度已改善。H20 收藏操作入口也仍待接線，尚不可列為真人驗收完成。

<a id="manual-tail-074"></a>
### H20 單次讀取核驗與階段提示（dev，2026-10-07）

名單讀取期間會顯示正在讀取保存指標、核驗來源／合約群組、讀取各筆預測及終態重新核驗的實際階段，並保留等待秒數。相同完整來源 binding 只在此次操作共用核驗，完成前仍重新核驗來源／合約、原名單與各筆預測；下次操作重新驗證。個股的保存 H20 證據也使用相同方式，報告讀取失敗仍可獨立顯示保存預測。這不會訓練、重算或改讀最新來源。

「展開推薦理由」讓詳情外層高度隨完整文件增長，分數拆解與排名門檻可透過結果頁捲動閱讀到最後一行。上述修正尚未包含於0f25候選，實際速度與正常視窗下鑽仍待新版驗證。原大檔 verifier尚無分塊取消，按取消後可能仍需等待目前核驗返回。

<a id="manual-tail-075"></a>
### d9 候選真人閱讀與H20重驗（2026-10-07）

檔案總管開啟 C:\Projects\PythonProjects\technical_analysis\output\qa\baldr_completion_m2_20261007，雙擊 start_h20_feedback_candidate_d9a115f6.cmd；確認視窗版本為2026.10.06+d9a115f67d2b。此啟動檔只傳遞既有外部日曆、研究根設定與主機設定，不改原exe，不訓練或啟用模型。0f25不包含本輪完整文件高度與H20核驗共用修正。

1. 推薦分析：使用任一預設策略分析全股票，選一檔股票後按「展開推薦理由」，用結果頁外層捲動閱讀分數拆解、排名門檻與理由最後一段；核沒有被裁切、卡住或只剩小框。非全螢幕亦應能完整閱讀。
2. 推薦分析→個人模型選股研究：等待名單完成，核實際階段與秒數提示有更新、十檔成員出現；雙擊2382，進個股研究頁最上方「保存的個人 H20 研究預測」。應看見未扣成本20交易日預測+6.84%、決策10/7／來源10/6／特徵10/5，以及實際結果尚待核驗的限制。請記錄雙擊到摘要出現的實際秒數；底層單次exe量測名單約24秒、stock evidence約19秒，不是Main總時間或速度保證。
3. 按「返回來源清單」，核回到原模型名單且2382仍選取、原排序保留；再縮小視窗核歷史版本／來源選擇欄仍可閱讀。H20收藏本輪尚未接進候選，請不要找其他收藏入口替代此項。

此候選已有原十股公開讀回、單股原預測、來源bytes不變與一般Python/exe隔離同版核驗；真人Native閱讀／可操作速度仍待上述重驗。完整母體同一保存query/bookmark精確同版資格、完整市場效能及其他P00–P14仍另列施工，不由本輪測試折抵。

<a id="manual-tail-076"></a>
### H20 原版本收藏保存（dev，尚未包含d9候選）

在「推薦分析→個人模型選股研究」讀取原名單，選擇可核原預測的股票，按「收藏原保存 H20 研究」。按鈕下方顯示重新核驗來源的進度，完成前尚未保存；若來源版本、選取或設定改變，請重新選取後再保存。未知列不能收藏；相同原版本與相同列表位置的收藏重複保存不增加項目。收藏保留原manifest/capture身份、排序與列表捲動位置，不保存交易指令，也不重算預測。

核驗期間關窗會要求取消並等待背景安全收尾；顯示正在保存後，已送出的個人清單寫入會安全完成。失敗原因顯示於按鈕下方，不以其他日期或新版模型取代原來源。開發版已接保存及觀察清單專用H20重開/返回入口，操作見下節；新程序與候選版接受仍待驗，也請勿使用d9候選尋找這個新按鈕。

<a id="manual-tail-077"></a>
### H20 收藏重開與返回（dev，尚未包含d9候選）

保存成功後，到左側「觀察清單」，找到「個人 H20 原保存研究收藏」。選取原日期與股票的收藏列，按「重開所選 H20 研究」，背景核驗完成後進入個股研究。頁面上方顯示原保存預測、決策日、來源日、特徵日與原觀察時間；目前模型停用或契約不同另行提示，仍保留原研究，不改讀最新模型。預測未扣成本，不能當作已實現績效；實際結果仍需另行核驗。

「重新核驗保存 H20 證據」沿原收藏身份重新核驗來源。缺件或身份不符時清除可用預測並顯示原因，不保留舊值冒充成功。若初讀與終態狀態不同，錯誤另保留所選列初讀與終態的原因，供核對最初來源拒絕；不代表其中任一狀態已通過。按「返回來源清單」回到觀察清單並選回同一收藏身份；若收藏已刪除或身份衝突，明示無法還原，不改選同股其他收藏。列表忙碌時會等待刷新完成再還原。

移除收藏先確認，預設為否；開始個人清單寫入後會安全完成，不宣稱可立即取消。此流程不交易、不訓練模型，也不更動原研究檔案。dev 的合成 MainWindow 路由已驗證，原實際來源、新程序、候選版與真人可用性仍分別驗收。

<a id="manual-tail-078"></a>
### 完整母體研究的獨立保存來源（dev，尚未包含d9候選）

需要讀取另一個已保存研究位置時，在portable設定JSON或啟動環境明示 `TECHNICAL_UNIVERSE_READ_ROOT`，值為包含原v4保存研究的絕對根目錄。`OUTPUT_ROOT`仍是目前程式的執行輸出位置。到「推薦分析→每日研究條件」的完整母體保存來源區，按「查詢保存版本」，選版本後「嚴格核驗並讀取」；原查詢、個股、比較與收藏都沿同一明示來源根及原pins，不改讀最新。此設定不建立或搬移研究檔案。

dev 基本面副本 session 的設定入口為 `FUNDAMENTAL_READ_SNAPSHOT_ROOT`：在 portable JSON 或啟動環境指定獨立絕對目錄，不得與 `DATA_ROOT`、`OUTPUT_ROOT` 或 frozen 程式包重疊。設定本身不建立副本；明示 caller 開 session 時才複製來源，連線僅開隔離 reader copy，結果保留原來源 clock。未設定、空白、相對或來源身份不符會拒絕，不改開原庫。這是工程入口，尚非完整 UI 基本面功能；來源仍 current-only、availability unknown，不授歷史 PIT 資格。

dev 個人收藏同一服務內的背景讀取與保存會依序執行，避免自身碰撞外部 marker lock。另一服務或程序正在操作時仍可顯示 `active_writer`；請等該操作結束，不刪 lock 或 activation 檔。此修正尚待新候選及原十檔 H20 載入／2382 下鑽真人驗證，不表示舊版延遲已通過。

外部保存根僅供讀取，產製新研究與續跑按鈕停用；產製仍使用原預設來源位置與既有寫入範圍。未設定時維持 `OUTPUT_ROOT/research_snapshots/technical_universe`。明示空白、相對路徑或frozen程式包內路徑拒絕；來源不存在、缺件或核驗失敗會顯示原因，不回退其他根。不要搬移或改寫原收藏中的來源根來遷移版本。此配置的完整Main／新程序／打包版接受仍待驗。

<a id="manual-tail-079"></a>
### 官方當下處置證據（dev 來源入口，尚未接完整選股 UI）

`CurrentOfficialDisposalReader.from_pointer` 讀取既有官方當下註記的固定保存版本；`from_exact` 以原 source pin 重開，不改讀最新。可明示 aware `cutoff_at`，來源發布、觀察與擷取時間均不得晚於截止時間，截止時間亦不得晚於本次讀取時間。未明示時使用本次 UTC 時間，不將缺列或空回應解讀為沒有處置。

結果分別保留公告日、處置起迄日及原觀察時間。資料是當下觀察證據，官方可得時間未知，不能當作完整歷史處置庫或回測 PIT 資格。schema／市場／原件身份不符顯示具名原因，不補安全狀態。這是工程來源入口，尚無新增 UI 操作按鈕；正常更新、全母體保存與條件／收藏接線仍待驗，請勿為測試手動觸發正式 Task。

<a id="manual-tail-080"></a>
### 最新工程驗證範圍（2026-10-07，dev）

獨立保存根已通過合成 257 納入＋1 排除的正常 MainWindow 旅程：查詢保存版本、原個股返回、兩股比較、收藏與精確重開，全程保留同一 query/source pins。H20 收藏亦已通過真 Main 父程序保存關閉、不同 PID 子程序重開摘要及返回同一收藏。以上補上前文尚待驗的部分工程路由；原實際市場、新固定候選、原十股 H20 的速度與 2382 真人下鑽、Native 仍分別待驗，不沿用舊 d9 宣稱包含新功能。


<a id="manual-tail-081"></a>
### H20 返回來源的重讀排程（dev，尚未包含 c611 固定候選）

從個股研究按「返回來源清單」回到原個人模型 H20 名單時，只排入一次帶原選取身份的完整來源核驗，避免程式切換分頁另觸發重複重讀。核驗完成後還原原 manifest、股票與選取；來源已變動或不符仍顯示原因，不換成其他名單。一般自行切換 H20 分頁仍會重新核驗。這不取消來源檢查，也不代表原十檔載入或 2382 雙擊已通過速度驗收；新候選與真人接受另行確認。

<a id="manual-tail-082"></a>
### H20 封存 SQLite 的私有讀取設定（dev 工程介面，2026-10-08）

`PERSONAL_H20_SQLITE_READ_ROOT` 可在 portable 設定 JSON 或啟動環境明示絕對路徑，未設定時為 `None`。明示空白、相對路徑或 frozen 程式包內路徑會拒絕；設定解析不建立目錄、不預選 TEMP／DATA_ROOT／OUTPUT_ROOT。實際安全讀取操作要求該私有根已存在，並核驗其與原封存來源的隔離及檔案身分；不得把原 SQLite 所在目錄指定為副本根。

這一輪只提供設定與 provider 的 opt-in 私有交易介面，尚未完成個人模型 H20 列表、下鑽及收藏的實際接線。新增設定本身不會使舊候選改用副本，也不代表等待時間已縮短。請勿自行啟動原件測試；新候選完成原件保護與 Main 驗證後才提供啟動檔與操作驗收。錯誤來源路徑／SHA、已關閉或取消的 session 會拒絕；缺件不得回退最新版本或以未知狀態宣稱已核驗。

<a id="manual-tail-083"></a>
### H20 名單點擊的個股讀取（dev，2026-10-08）

原保存 H20 名單已核驗且選取可用列後，按「研究選取股票」或雙擊同列，直接開啟該原保存版本的個股研究並顯示核驗中；點擊前不再額外重讀整份名單。個股 reader 仍重新核原 manifest、所選 capture、來源及終態身份，完成前不把名單 RAM 值當成已核預測。來源已變、缺件或讀取失敗時保留原來源身份並顯示原因，不套最新版本。名單正在載入、未知列、缺原來源參照或關閉中均不啟動下鑽。

「返回來源清單」仍重新核驗同一份原名單並還原選取；這項改動只移除點擊前的重複名單讀取。原十檔速度、安全副本接線及新候選真人接受尚待驗，不代表舊 0f25 或 c611 已包含此修正。

<a id="manual-tail-084"></a>
### H20 安全副本的畫面接線（dev，2026-10-08）

本節補充前述僅提供設定介面的施工狀態：目前 dev 的原保存 H20 名單、所選個股、收藏前核驗與收藏重開已明示要求 `PERSONAL_H20_SQLITE_READ_ROOT`。該根須已存在、為程式包外的隔離絕對路徑；沒有設定時會顯示拒絕原因，不能默默直讀原 SQLite。每次操作建立私有唯讀副本並重新核原來源；完成終態核驗後才顯示成功或保存收藏，不跨操作借用舊副本。

到「推薦分析 → 個人模型選股研究」讀取保存名單時，可查看目前階段與複製進度；選可核驗列按「研究選取股票」或雙擊，在個股頁上方「保存的個人 H20 研究預測」查看核驗進度與完成摘要。收藏入口仍是名單下方「收藏原保存 H20 研究」，重開入口為「觀察清單 → 個人 H20 原保存研究收藏 → 重開所選 H20 研究」。取消或換選取後，舊進度不得覆蓋取消提示或發布舊結果。預測、來源／特徵日期與未核實際結果仍分開判讀。

每次操作最多50組不同來源、SQLite主檔副本總量最多64GiB；非空WAL不支援，來源變動、容量超限、路徑不隔離、取消或hash不符均拒絕。請保留可見原因碼，不修改來源、checkpoint、補零或改指latest來繞過。限制不代表這些容量已實測，也不代表載入已達速度要求。

本輪合成讀取／Main旅程與UI強制檢查已通過；原4GB封存來源、實際十股與2382速度、新固定候選及真人驗收仍待。不要用舊0f25／c611啟動檔驗此改動，也不要自行重開原件測試；後續會交付新版的確切啟動位置。standalone／自然結果排程尚未全部採用此安全接線，本節只描述上述UI入口。

<a id="manual-tail-085"></a>
### 完整保存母體的同次讀取與零結果（dev，2026-10-08）

在推薦分析的每日研究頁查詢完整保存版本，選取可讀列後按「嚴格核驗並讀取」。這次會在背景完整核驗固定保存來源並建立讀取狀態；清冊metadata本身不等於已核結果。之後修改篩選／排序、翻頁及讀取原保存個股，都沿同一組保存來源；翻頁使用已排好的符合名單，再精確重讀該頁需要的保存資料。

符合條件為0時，股票表格清空，顯示已核完整母體計數與符合0筆，停用當頁個股、比較加入及收藏。修改條件後可再查詢；只清除股票代碼篩選不會同時清除原AND／OR、規則狀態或排序。0筆不表示原母體沒有股票，也不同於讀取失敗。

若要再次確認來源，選原保存版本按「嚴格核驗並讀取」會建立新的完整核驗；失敗或來源改動時保留先前已核畫面與明示錯誤。暖頁狀態不宣稱來源檔在核驗後未變，也不會改讀latest或新行情。收藏仍重新核原固定版本，重開不能借用記憶體當作持久化或fresh核驗證據。

此接線已通過合成完整來源、跨頁／個股、零結果恢復、來源漂移及UI檢查；實際1000／完整市場延遲與新候選真人接受仍待。來源資料可得時間未知時仍只供當下研究，不授歷史PIT或可交易資格。

H20 私有副本根存在卻無法建立操作目錄時，dev 會立即顯示建立失敗，避免 Windows 將權限拒絕反覆當成名稱碰撞。確實的名稱碰撞最多重試32次，重試之間可取消；不刪除已有目錄或繞過權限。遇到 `sqlite_read_session_private_directory_create_failed` 或 `sqlite_read_session_private_directory_collision_limit`，保留原因並檢查已明示副本根的可寫權限與可用空間，不修改原封存資料。此修正尚未包含已交付舊候選，不代表原來源載入速度已驗收。

H20 載入或下鑽時，等待提示會顯示核驗原封存資料、建立安全副本、核驗副本內容及確認原來源未變等階段。位元組進度只在整數百分比變化、階段切換、重新開始與完成時更新；階段準備訊息不冒稱位元組量測。畫面更新合併不減少逐區塊來源核驗或取消檢查，也不代表整個操作已完成。此為dev的新接線，原4GB來源速度、新候選及真人接受仍需另驗。

<a id="manual-tail-086"></a>
### 應用程式日誌與 H20 同次核驗檢視

應用程式日誌位於 `OUTPUT_ROOT/application_state/logs`，包括 config.log、db_manager.log、data_loader.log。既有 `DATA_ROOT/logs` 保留原位置與內容，不會自動搬移或刪除。Runtime readiness 的 Logs 與可寫檢查使用新執行日誌目錄；DATA_ROOT 本身仍只檢查可讀能力。若日誌目錄不可寫，檢查會提示 attention，請修正輸出目錄權限。

推薦分析 → 個人模型選股研究先完整核驗保存名單及安全 SQLite 副本，畫面顯示等待秒數、目前階段及核驗完成時間。選取股票並按「研究選取股票」或雙擊可用列後，下鑽沿用同次完整核驗結果，另核對保存版本指標；返回保留原名單與選取，不重複複製研究來源。摘要顯示原核驗時間，來源未持續監測。按「重新核驗」會重新完整讀取原保存版本；失敗、取消或版本變動不套用部分結果。收藏準備與跨程序重開仍重新核驗原來源，不沿用程序內檢視。未知列不可下鑽；個人 H20 預測不代表已實現報酬或交易資格。

<a id="manual-tail-087"></a>
### 推薦理由捲動與研究來源判讀（dev，2026-10-08）

結果表的推薦理由是保存標籤前三項摘要；選取股票後，詳情呈現當次保存的理由文字、逐因子貢獻、排名及合格母體日期。沒有提供的欄位顯示未知，不使用目前行情重算。舊紀錄若文字已截短，無法回推被刪文字；另存的完整理由標籤仍會顯示，缺少的貢獻符號不補推。此為 dev 修正，先前候選 EXE 尚未包含。

推薦分析選取結果後，展開推薦理由可閱讀分數拆解、排名門檻及「可能影響排名的因素」。整頁可向下捲動；若視窗或字型限制文字框高度，文字框也可捲到末行。驗收時請同時確認排名因素的最後一行可達，不能只看框是否變大。

dev 新增鍵盤閱讀：展開後點入理由文字，按 PageDown／PageUp 可捲動外層頁面，Home／End 或 Ctrl+End 可到頁面起點／末端；文字選取與 Ctrl+C 複製仍可使用。收合或文字框本身仍有捲動範圍時，維持框內原有鍵盤操作。此修正尚未包含於先前候選 EXE；新版真人驗收須在非全螢幕確認鍵盤及滑鼠都能讀到完整末行。

「篩選紀錄／未入選」用來查看策略在哪個條件停止，不代表已產生推薦分數或排名。量能門檻的觀測值與要求值以百分比顯示：例如 −31.23% 代表相對本次成交量基準量縮，要求 +50.00% 則代表策略要求放量至少 50%；此檢查在打分前停止。核對原證據的資料日期與策略條件後，再決定是否用另一策略研究；缺少或非有限數值不補寫具體量能原因。原原因碼與證據品質仍保留供排錯。

從個人 H20 名單或其收藏進入個股時，上方保存 H20 區顯示原預測及來源狀態；「個股報告 ML（與個人 H20 保存預測分開）」是另一份報告讀取結果。該區的「未提供」只表示沒有符合這份報告條件的 ML 估計，不會否定上方已讀回的 H20，也不能以 H20 數值補成報告 ML。未扣成本的 20 交易日預測與自然結果分開；缺少已核驗 outcome 時不顯示實現收益。這些文字與捲動修正尚未納入先前交付的 d9a115f67d2b 候選。


<a id="manual-tail-088"></a>
### 官方市場／處置保存研究（dev，2026-10-08）

<a id="manual-tail-089"></a>
#### 開啟已保存的官方市場／處置研究

在「推薦分析」的結果來源分頁選取「官方市場／處置研究」。這是讀取既有保存研究的獨立分頁，不會啟動市場更新、產製新研究或建立保存目錄。

若畫面尚未指定研究來源資料夾，按「選擇保存來源資料夾」，選一個已存在的絕對路徑。此處只選擇既有保存位置，不會建立資料夾，也不會搜尋其他磁碟或改用最新來源。選定資料夾後，按「更新來源清單」；若清單分頁尚有後續項目，再按「下一頁來源」。

清單列是供選擇的保存版本 保存版本資訊，尚未核驗研究內容。列上會顯示決策日、宣告／納入／排除數與來源覆蓋狀態；資訊不完整的列只供診斷，不能用來讀取結果。明確點選一個可讀的保存版本後，背景工作才會固定該版本身份並執行完整核驗與全母體查詢。畫面不會自動選取「最新」版本。核驗失敗時，狀態列會列出原因，原本已顯示的結果保持不變。

切換來源資料夾會清除舊來源的查詢結果、目前頁面、選取股票與比較清單，避免不同保存版本混用。已設定的條件控制項仍留在畫面，需在選取新版本後再確認或重新套用。背景工作執行期間不能切換來源資料夾。

<a id="manual-tail-090"></a>
#### 設定全母體條件與排序

「全母體條件」套用於所選保存版本記錄的完整 明示股票母體：先篩選及全域排序，再切分結果頁。每頁可顯示 1 至 256 列，預設 50 列；256 是單頁上限，不是保存母體的總數上限。這裡的「全母體」只指該保存版本明確列出的母體，不代表即時市場或官方全市場已完成驗證。

「列範圍」可選納入且已處理、納入但待處理、明示排除。畫面另外列出宣告、納入、排除、已處理、待處理、缺資料及待處理缺資料等母體計數。條件只改變符合列及頁面，不會改寫原始分母或把排除列當成不符合。

開啟「套用技術規則篩選」後，可對 MA5／MA20 金叉、K／D 金叉、MACD 金叉、量能比 20（含當日）及量能比 5（含當日）各自選「不指定」、「符合」、「不符合」或「未知」，再選「所有已選規則（AND）」或「任一已選規則（OR）」。規則說明依保存的方法契約顯示；介面只查詢已保存的事實，不會重新計算指標。每項規則目前只能選一種狀態；若保存的收藏要求同一規則同時選多種狀態，這個介面無法表示，會拒絕還原，不會只套用其中一種。

市場條件可查上市 TWSE、上櫃 TPEx 或未知；處置條件可查已公告尚未生效、公告處置中、僅有已經過的處置紀錄或未知。未知是獨立的資料狀態，不等於不符合，也不證明沒有處置。缺少來源列、來源覆蓋部分或證據衝突時，應以畫面顯示的未知、缺資料或 partial 狀態判讀，不得推成安全或否定結果。技術規則未知與原始資料缺件分開計數。

「只查指定股票代碼」目前只接受一個股票代碼。空白、格式錯誤，或未開啟篩選卻在欄位中留下代碼，都會拒絕套用。收藏要求多個股票代碼條件時，本 UI 無法完整還原，會拒絕整筆還原，不會只取第一個代碼。

排序使用可讀的欄位名稱，按「新增排序欄位」增加欄位，並分別選升冪或降冪。可排序股票代碼、決策日期、最新特徵日期、來源列數、各規則已保存的比率／分子／分母，以及市場／處置狀態與觀察時間等欄位。缺值在升冪與降冪都排在末端，股票代碼作穩定排序。按「套用條件」從第一頁執行；按「清除條件」會恢復未篩選狀態及股票代碼升冪排序。零筆符合會顯示 0 筆結果，與來源母體為空或讀取失敗不同。

<a id="manual-tail-091"></a>
#### 查看個股與比較

在結果表選取股票，按「查看個股」。詳情以一般文字呈現股票代碼、母體列範圍與處理狀態、決策日期與技術來源交易日、市場對照、處置事件與日期，以及五項已保存技術規則的狀態、支持事實、未符合事實與未知原因。方法契約未提供的計算方式會明示未提供，不會由畫面自行補公式。按「展開完整稽核資料」可查看原始稽核內容；按「返回原結果頁」回到原頁與原選取。

個股資料明示依原保存版本完成核驗，但來源不持續監測。此研究為 current-only；官方 available_at 未知，不具歷史 PIT 資格。技術列或官方列的未知狀態不構成投資建議、買賣指令或沒有風險的證明。

比較清單只接受已有技術事實的已處理列；待處理或排除列不能加入。可在不同結果頁加入股票，但所有項目必須來自同一保存來源及同一查詢條件。加入 2 至 5 檔後，按「比較已選股票（2–5 檔）」；比較內容重新按各股票的原結果頁核對，在獨立視窗中並列顯示，每檔可各自捲動。比較不會產生推薦或交易判斷。清除條件或切換來源會清空比較清單，避免混入不同研究。

<a id="manual-tail-092"></a>
#### 收藏與從觀察清單重開

在結果頁選取要收藏的股票，按 主程式顯示的「收藏原研究」。系統會把目前已核驗研究的固定來源身份、查詢、頁面、股票與比較清單保存到既有觀察清單；此保存操作本身不會重新開啟來源或再次核驗來源檔案。完成或失敗都會顯示狀態，不會改讀其他版本。之後從觀察清單重開時，系統才沿收藏記錄中的原來源身份重新核驗。

在「觀察清單」中找到標示「已收藏官方市場／處置研究｜股票〈代碼〉｜固定原來源」的列。選取該列後按「查看選中個股研究報告」，或雙擊該列，即會要求沿收藏固定的來源重新核驗並重開原研究；不會轉成一般最新個股研究。原查詢、頁面、選取股票與比較清單會在全部核對成功後一起還原。若任一來源檔案缺件或身份不符，整筆收藏不會部分套用。

這個收藏在本次開發版的 UI 測試中由同一程序建立及重開；新程序讀回證據與本手冊所述 UI 路由仍須分別驗收。觀察清單內另一個「完整母體技術研究收藏」控制區是不同書籤類型，不要以它取代上述官方市場／處置收藏列。

<a id="manual-tail-093"></a>
#### 重新核驗、取消與關閉

重新按「更新來源清單」只重新盤點 保存版本資訊；要重新核驗研究內容，請明確點選欲核對的保存版本。重開收藏時也會沿固定原來源重新核驗。條件變更會沿目前已核驗工作階段執行，不代表來源在工作階段建立後持續受到監測。

按「取消背景工作」會送出合作式取消，並保留原已核結果；取消不是立即中止保證。晚到的背景結果不會覆蓋取消後的畫面。關閉主程式 時會要求相關工作合作取消，並等候原生背景工作停止後完成關閉；大檔核驗期間可能需要等待。

<a id="manual-tail-094"></a>
#### 常見狀況

- 尚未選擇來源資料夾：選取包含既有保存版本的資料夾，再按「更新來源清單」。
- 清單沒有候選：確認選的是保存版本所在資料夾，而不是正式行情資料夾或其父目錄；按更新重新盤點。畫面不會自動猜測其他路徑。
- 清單列標示資訊不完整：該列只供診斷，不能讀取結果。請檢查保存版本及 manifest 是否完整；不要把它當成空母體。
- 選取後核驗失敗：依狀態列原因檢查原版本是否缺件、改動或身份不符。若要讀另一版，請回到清單明確選取該版本；不要以「最新」替代原選取。
- 條件無效：確認已選至少一個列範圍；啟用規則、市場、處置或股票篩選時，需選狀態或輸入單一有效代碼；每個排序列都要選欄位。
- 結果顯示未知或 partial：未知、缺資料、來源覆蓋部分與待處理列都須依原狀保留；它們不能當作不符合、否定證據或完整來源。
- 比較按鈕停用：至少加入兩檔已處理股票。比較最多五檔，且不可跨來源或查詢條件。
- 收藏無法還原：確認收藏未被移除，並檢查固定原保存版本是否仍完整、可讀且身份一致。多狀態／多股票代碼條件不在目前 UI 可表示範圍內；系統拒絕完整還原時，不會套用部分條件。

此保存研究入口已通過合成258檔主程式的跨頁比較、詳情返回、背景收藏與觀察清單原查詢重開；均為同一程序。新程序的完整UI旅程、正常來源產製、正式全市場資料、Native候選、效能與真人接受仍須分別驗收。來源僅為當下對照，官方資料可得時間未知，不具歷史PIT資格；資料部分、未知與待處理保持原狀。

<a id="manual-tail-095"></a>
### 2026-10-08 保存研究表格與完整查詢（dev來源版）

官方市場／處置研究及五規則完整保存研究頁使用 Qt 表格模型，只載入公開查詢完成後的當頁結果。排序以整份保存來源為範圍，再取頁；表格不另做當頁排序。欄位提示可顯示完整文字，切換頁面先清除舊選取，收藏還原則以股票代碼重新定位公開資料列。

每個技術規則可選符合／不符合／未知的任意非空組合，或不限制，再指定 AND／OR。股票篩選可輸入多個代碼，以逗號、全形逗號或空白分隔；重複、空逗號欄位、無效字元或超量輸入會拒絕整次查詢，保留原結果。收藏重開沿保存的完整條件，不套用部分條件。官方頁若遇到另嵌入的 technical_query.stock_filter，目前仍拒絕還原並保留原狀。

來源版已通過合成258檔主視窗的跨頁比較、詳情返回、收藏與新程序重開，合併9項測試通過。到「觀察清單」重開原保存研究收藏，應保留原來源、條件、排序、頁面、選股及比較籃；原來源缺件或身分不符時不改讀最新版本。此段更新前述單股輸入／多狀態尚不支援的 dev 說明；已發佈執行檔尚未包含本項，Native與真人仍待。

官方市場／處置研究的比較收藏需有2–5檔。比較籃只有1檔時，畫面會提示再加入一檔，或先清空比較籃，再收藏目前查詢與選取股票；不會自動丟棄比較籃或更換選取。來源僅為當下對照，官方資料可得時間未知，不具歷史PIT、Advice或收益資格。

<a id="manual-tail-096"></a>
### 2026-10-08 資料日呈現補件（來源版）

「市場觀察 → 大盤指數」的資料日期只呈現來源明示的正規日期；缺值、格式錯誤或只有時間戳時顯示「未知」，並提示核對來源。日期未知不會自動換成今天、決策日或最近開市日，亦不會改變原市場分類。

每日決策工作台的市場資料日另核對該區塊原判讀日；來源日較晚或判讀日期型別不符時保持未知。資料日和台北評估日仍分開顯示；週末來源日不自行搬到星期五。此補件不新增更新、補資料或日曆判定；需要資料時依原更新入口處理。尚未交付包含本補件的新固定執行檔。

<a id="manual-tail-097"></a>
### H20 名單的等待、取消與重試（dev來源版，2026-10-08）

到「推薦分析 → 個人模型選股研究（H20毛報酬）」會開始讀取原保存名單；也可按「讀取每日已保存模型名單」重新完整核驗。即使先前已捲到結果區底部，等待提示仍會進入可見範圍，顯示實際核驗階段與已等待秒數。大型來源庫首次核驗可能耗時；百分比不代替原來源完整核驗。

讀取期間，重新讀取按鈕、股票研究操作暫時停用；切換回同頁沿用同一背景讀取。按「取消名單讀取」後會顯示「已送出取消，仍在安全收尾」，到背景執行緒真正結束才顯示取消終態並解鎖。取消不套用未完成結果，亦不提前開始第二次讀取；終態後可按讀取按鈕重試。

完成後顯示「總列／可研究／未知」與耗時。這些計數只涵蓋原manifest成員，不代表全市場；未知列保留在表格和分母，選取後仍停用研究與收藏，原因見該列及診斷區。可研究列選取後按「研究選取股票」或雙擊開啟原保存研究；返回保留原選取與來源身分。來源設定變動或完整核驗失敗時，不會套用過期或部分結果，也不改讀其他日期。

若顯示「尚未設定安全副本目錄；本次讀取未開始」，核對可攜設定的 `PERSONAL_H20_SQLITE_READ_ROOT`；讀取失敗時查看下方完整原因。原保存估計與自然結果成熟度仍分開，這項等待提示補件不更改來源核驗、模型估計或金融計算。目前是來源版功能，含此補件的固定候選仍待驗證與交付。


<a id="manual-tail-098"></a>
### 2026-10-08 H20 等待候選真人入口

固定候選為 `2026.10.06+421bc973a891`；同版隔離 Python／exe 比較通過，真人尚待。檔案總管開啟 `C:\Projects\PythonProjects\technical_analysis\output\qa\recommendation_feedback_421bc973a891_20261008_a`，雙擊 `start_feedback_421bc973a891.cmd`。三項驗收：推薦結果選股後展開理由，以結果區右側整頁捲軸讀完分數拆解／排名門檻／排名因素；非全螢幕個人推薦模式控制項不重疊；H20 首次等待有階段與秒數，完成有總列／可研究／未知，2382 可研究時能下鑽及返回，取消收尾後才可重試。

首次名單核驗與單股下鑽分開計時。這版不宣稱加速；H20 與其他 rule／ML 目標的文字判讀、完整個股脈絡仍待補。完整步驟及候選 pins 見 [固定候選 QA](../06_qa/BALDR_H20_LOADING_CANDIDATE_421BC973_20261008.md)。


<a id="manual-tail-099"></a>
### H20 與個股 ML 缺值文案區隔（後續來源版）

H20 保存名單／書籤情境中的個股 ML 區，標題及缺值說明會明列「另一份個股 ML 報告（與上方 H20 毛報酬分開）」。該區未提供估計只指另一份報告；H20 是否可用及保存毛報酬請依上方 H20 區的來源核驗狀態判讀。未知 H20 不因此變成可用，其他模型估計不換算成 H20，H20 也不填入該模型。一般非 H20 報告維持原文。

這項後續文案不在已交付的 `421bc973a891` 候選內；來源版完整個股 UI 57 項及必要檢查通過，尚待新候選與真人接受。詳見 [分區文字 QA](../06_qa/H20_REPORT_ML_SEPARATION_COPY_20261008.md)。

<a id="manual-tail-100"></a>
### H20 原研究與目前行情分開查看（後續來源版）

推薦分析→個人模型選股研究→選可研究股票→「研究選取股票」。原 H20 估計核驗可用後，可按上方「查看目前個股行情與資料（獨立研究）」另開視窗。新視窗標題與說明會標示目前來源，使用自己的資料日期；不把目前價格、技術圖表或另一份 ML 輸出填回原 H20。按返回或關閉視窗後，原 H20 預測、日期、來源、選取股票與返回位置保留。

原報告若顯示「未綁定同版本價格／技術圖表」，表示該保存 H20 尚未攜帶可核驗的同版圖表，不代表市場資料庫不存在；單靠資料更新不能讓目前行情變成原版資料。未知 H20 的入口停用，先查看來源原因並重新核驗；來源設定已改變時會拒絕開窗。主程式關閉會取消並等待讀取結束。原 H20 同版圖表與讀取速度仍待補完，不把這個獨立入口當成原版本回補。

此入口尚不在已交付 `421bc973a891`；來源版中央完整 UI 65 項及必要檢查通過，新固定候選與真人接受仍待。詳見 [獨立目前研究 QA](../06_qa/H20_INDEPENDENT_CURRENT_RESEARCH_20261008.md)。

<a id="manual-tail-101"></a>
### 2026-10-08 93f9 獨立行情候選真人入口

前節打包待辦已更新：`2026.10.06+93f9c57d7995` 已建置並通過同版隔離 Python／EXE 比較，真人待驗。檔案總管開啟 `C:\Projects\PythonProjects\technical_analysis\output\qa\recommendation_feedback_93f9c57d7995_20261008_a`，雙擊 `start_feedback_93f9c57d7995.cmd`。主要驗完整推薦理由能捲到最後，以及可研究2382另開目前行情／關閉回原H20後，預測、日期、來源與選取保持。名單、單股及目前行情分開記時；目前行情缺件需回報該區原因。完整步驟見同目錄 `真人驗收說明.md`；資格與來源 pins 見 [候選 QA](../06_qa/BALDR_H20_CURRENT_CANDIDATE_93F9C57D_20261008.md)。

<a id="manual-tail-102"></a>
### 2026-10-08 H20 同份來源價格圖（來源版驗證中）

本節描述開發中的來源版，尚未加入前述 93f9 EXE。從「推薦分析 → 個人模型選股研究」讀取並核驗完整保存名單，選取可研究列後開啟個股研究；同次來源讀取與終態核驗都一致時，摘要另顯示 H20 原快照 OHLCV 圖及價格表，一般個股報告仍在等待時也可先查看此區。圖表截至原特徵日，最多呈現最近 120 筆，不補讀目前行情、不新增 MA 或預測；原資料可得時間仍未知，不能視為歷史 PIT 或可交易依據。

收藏重開後需按「重新核驗保存預測」取得本次圖表。來源設定改變、日期超出保存範圍、價格缺欄或核驗失敗時顯示缺件原因；圖表缺件不會把已核驗 H20 估計改為失敗。切換來源或股票會清除舊圖，避免把別股或別版資料留在畫面。原 H20 的研究估計與自然結果成熟狀態仍分別判讀，價格圖不代表估計已驗證。


<a id="manual-tail-103"></a>
### 2026-10-08 F17 保存版本單次核驗（來源版）

推薦分析的官方市場／處置保存研究仍先選明示保存版，再執行完整來源核驗。技術 parent 已改由同次核驗建立固定 session，不重讀同圖；取消或核驗失敗不發布新結果。這是來源版接線驗證，尚不保證等待時間或代表正常更新／全市場／歷史 PIT 已完成。

<a id="manual-tail-104"></a>
### 2026-10-08 原價格條件研究、返回與收藏（開發來源版）

主選股票可以同時留在比較籃：收藏保存並保留原比較順序，不需要另選第三檔。比較籃內同一選取項目不能重複；主選與籃內相同錨點的證據若互相矛盾，收藏會拒絕。重新開啟仍按保存的來源、條件、頁碼與股票重新驗證；此修正屬開發來源，f2fba4c7 候選 EXE 尚未包含。

本節描述已通過來源版功能整合的操作，尚未加入已提供的 `bd5d2f86367a` 候選執行檔；執行檔與真人驗收仍待，不表示已完成實際全市場或效能門檻。

入口在「推薦分析 → 每日研究條件」的「全母體條件與價格範圍」。先選取明示保存版本並載入核驗；版本清單只是來源目錄，載入成功才會替換表格。此入口只讀已保存的技術研究來源，不會替你產製資料或補讀目前行情。沒有保存版時先確認來源設定與既有產製結果，不要把空清單當成市場沒有股票。

價格下限、上限的單位是每股新臺幣，需輸入有限正數；留空表示不限制該側。各端點可選是否包含，以下限100、上限200且兩側包含為例，100與200都符合。兩側相等但任一側排他，是合法的空價格區間；缺價列仍依未知政策處理。技術規則可用全部符合／任一符合組合，股票條件及明示候選限制會先作用，再計算價格符合、不符合、未知數。

「未知價格」預設保留，也可明示排除或只看未知。未知不是價格零元；缺資料、日期或來源不符、重複觀測、無效OHLC都不能代入價格。價格採原快照的已核觀測日，畫面同時列決策日，兩者可能不同。排序先處理整份符合母體，再分頁；同價依股票代碼排序，缺價不論升降序都置尾。宣告、已處理、待處理、排除與缺件數分開呈現，不能把目前顯示列數稱為全市場。

雙擊已核驗結果開啟原價格條件個股研究。詳情頁顯示該股價格、觀測日、原條件、技術支持／反證／未知與來源限制；內容可向下捲動。按返回會按原保存版本重新核驗並還原條件、頁碼與股票；來源被修改或取消時保留已核舊表，明示拒絕，不改用最新資料。比較至少需兩筆，先加入比較籃，再執行比較；每欄保留自己的日期、條件與來源。不同保存來源可以並排，但不表示相同截止時間或歷史可交易資格。

收藏先選取一股，按「準備價格研究收藏」，核對確認視窗後保存至觀察清單。只會保存仍對應目前來源、頁面和選取的原查詢；確認期間條件或股票改變時拒絕保存。比較籃為空或至少兩筆才可保存；只有一筆時先清空或補足比較。取消確認不新增收藏。

重新開啟時到「觀察清單 → 原價格條件研究收藏」，選取原收藏並按「重開所選價格研究」，也可雙擊觀察清單中的價格收藏列。若列表正在載入或刷新，會等待完成後自動開啟指定收藏，不需再點一次；連續指定不同收藏只會開啟最後指定的一筆。取消或關閉會清除等待項目。重開會核驗原版本、原價格、頁面、股票與比較集合，再交回每日研究條件頁；不是一般個股報告，也不讀最新價格。收藏存在但無法核驗時，列表保留診斷，查看來源缺失或版本不符原因，不能用更新資料替代原證據。原JSON或已明示啟用的SQLite儲存模式沿既有觀察清單流程，不因使用價格收藏而自動升級。

資料可得時間仍未知，歷史PIT／交易資格不具備；這是研究條件，不是漲跌預測、勝率、Advice或買賣指令。1,000檔合成來源的完整冷暖測試已發現四類操作速度未達300毫秒門檻，不能把功能回歸通過當作等待速度已改善。取消須等背景工作安全結束；關閉主程式也會合作取消並等待，不發布半份結果。詳見 [價格研究接線與驗收紀錄](../06_qa/F07_PRICE_QUERY_CONTRACT_20261008.md)。

MA 複合研究收藏的儲存分派正在接線，尚無可使用的新版 UI 入口。觀察清單服務以獨立 `daily-market-technical-official-disposition-ma-bookmark.v1` schema 解碼，保留原查詢、選取與比較來源；不經舊 F17 收藏的 2 MiB decoder 截斷。格式不符或未知版本仍保留 MA 來源分類，不改成一般手動股票或 Advice。這類收藏必須由專用 exact reader 重開，透過一般個股 context 入口會拒絕並提示原查詢核驗需求；目前不應以此段當作操作驗收清單。

MA 畫面的入口為「推薦分析 → 四均線／官方對照研究」。選取明示的已保存來源版本並完成查詢後，選取股票；可跨頁加入比較，再按「準備收藏」。主視窗會把原查詢、頁面、選取與比較清單保存至觀察清單。於觀察清單選取「四均線官方處置研究收藏」，按「查看選中個股研究報告」重開原保存版本。保存不會再次讀取來源；重開會重新核驗原來源與完整查詢，再還原頁碼、選取、捲動及比較籃。未指定來源時不自動讀取；來源不存在、版本不符或核驗取消時，保留原研究並顯示失敗。損壞或未知版本的收藏仍識別為 MA 收藏，拒絕轉入一般個股報告。此結果僅供當下研究，來源 available_at 未知時不取得歷史 PIT 資格。真研究頁旅程、完整主視窗隔離啟動、Main／Watchlist 收藏重開及關閉已通過合成測試；新程序、新候選、原 H20 與真人驗收仍待完成。


## 2026-10-11 Manual 排程日期化狀態移存

> 以下原文由 Manual 的同名章節移入，保留 2026-09-30 與 2026-10-01 的原收據與狀態。這些資料是歷史快照，不作現行排程狀態或操作授權；現行入口依 Manual 與 Snapshot。

### 2026-09-30 排程執行與日期判讀

本輪七項排程問題的實際 Task、receipt、人工／自然觸發區別與未解 blocker，見[排程修復 QA](../06_qa/SCHEDULED_OPERATIONS_REPAIR_20260930.md)。Task 的 `LastResult=0` 只表示 wrapper 正常結束；仍要核對同次 status、source identity、artifact readback 與業務 `status`。本輪 Quick、Freshness、Recommendation 與 Evidence 的人工受控執行不會代替各自自然時鐘驗收。

正式 `baldr-recommendation-snapshot-daily` wrapper 在 `EXPORT_PAPER_FROZEN_SOURCE` 未設定時預設輸出 Paper frozen source；明確設為 `0` 才 opt-out。匯出只接受同次已完成且 indexed 的 canonical Recommendation，寫入 create-only `paper_frozen_<result_id>.json`，保留原 `result_id`、決策時間與來源雜湊；不改 selector／generic index、不補寫歷史日期。Python CLI 預設不匯出，Shadow learning 也不傳此旗標。此 artifact 是研究用的來源凍結，不會自行產生可執行 Paper session；它只能供下一個符合官方 session 的 consumer 驗證。

05:15 Evidence dry-run 的 Exit Effectiveness child 最長執行 300 秒，requested artifact 為 `OUTPUT_ROOT/exit_effectiveness/YYYYMMDD.json`。Producer 只 create-only 寫入；同日內容不同時以 `<YYYYMMDD>_<sha256前16碼>.json` 保存新 artifact，既有檔不改寫。wrapper 只在實際回傳路徑通過 exact root／檔名／台北業務日期驗證，並完成 32 MiB bounded no-follow readback、file SHA-256、schema、UTC `generated_at`、evidence hash、stdout 與 artifact 完整內容比對，以及 research-only／無 Formal／無自動 Exit／無券商下單旗標檢查後，才填入 `exit_effectiveness_artifact_path`。`exit_effectiveness_output` 保留 requested-path 相容語意，`exit_effectiveness_requested_output` 會明確重複標示它；下游應使用 verified actual path 與 `artifact_identity_status=verified`。Status 的 `exit_effectiveness_receipt.receipt.artifact_path` 只保留驗證後 actual path；原始 child stdout 收據在 `producer_receipt`，不能把其中未驗證的 path 當輸出依據。現行 v1 receipt 缺路徑、hash 或讀回不符會 blocked，不回退讀取同日舊檔；此產物不核准投資有效性、transition 套用或交易。

Paper execution queue 只能用同一 `portfolio_id`、execution session 與 frozen source file hash 的 verified terminal receipt 結案。已驗證且在本次觀測時鐘內的 `processed`／`superseded` 可關閉同一 hash 的較早 pending；較晚到達的 pending 不會重開已結案來源，future terminal 不可解除 stale pending，同 session 不同 processed hashes 則 fail closed。只有明確 safe-no-selection 狀態可標為 skip；naive clock、缺來源或 identity 衝突都應 blocked。9/30 新 frozen Recommendation source 僅供下一個官方 session 使用；缺少 9/29 有效 frozen source 時，不能回補成 9/30 已執行或已成交。

Position Health baseline 的 `decision_date` 表示 Paper source snapshot date。只有 `position-health-daily-refresh.v1` 在 source snapshot date 等於 decision date、baseline `as_of_date` 等於 requested as-of，且 source identity、clock、availability 與 coverage 都驗證通過時，才可把較舊 holdings 留作 `observation_only` degraded snapshot；這不能證明當日 Paper producer 成功。Legacy baseline 仍須日期吻合。只有已確認為使用者真實持倉的列，缺 entry source、thesis、invalidation、holding horizon 或 review date 才是待補使用者資料；machine-initialized Paper research seed 不可推論為使用者持倉，也不可要求使用者補其成交或 thesis。candidate／research flag 不代表成交或驗收。

2026-09-30 原 Paper EOD Task 的受控 no-work 結果為 `skipped_no_pending_recommendation`：這只表示該觀測時鐘下沒有已到期且可選取的來源，且本次 positions／ledger 沒有變動；它不是當日成交或 producer 處理來源的成功證據。當日新建的 `paper_frozen_<result_id>.json` 是下一官方 session 的研究輸入，不能回填成當日執行。Queue 的歷史診斷只在後續同 portfolio、result 與 source hash 的 processed receipt 及 ledger readback 完整驗證後結案；naive clock、source identity 缺漏或不一致仍 blocked。使用者已明確表示沒有 1418 持倉；`paper-main-20260930` 的 1418=3,000 股是 machine-initialized research seed，不是使用者持倉，不要求使用者補成交、entry 或 thesis。這也不代表其他持倉皆為空。機器 seed 仍須保留其研究身份／品質診斷，不得補造交易或降 gate。

Formal Input preflight 只有在 configured、same-run candidate 與 final 都指向預期日期的同一路徑，candidate manifest hash 與 final manifest/file SHA 相符，且 final `ready`、`compatible`、`consumer_verified` 全為 true 時，才可精確結案 `formal_rule_history_source_file_missing` 這一項。這不會解除其他 blocker、授予 Formal credit 或證明整個 Formal Input 通過；日期／路徑／hash 任一不符就維持 blocked。Freshness 的 current-only 月營收與季度觀測不得補成歷史公告／available-at 證據；expected period、官方 availability mapping 或 revision artifact 缺件時仍維持 warning／partial。

Paper isolated EOD wrapper 的來源選取 namespace 固定為 `paper_frozen_*.json`；一般 queue API 預設仍讀 `*.json`。namespace 只限制 candidate 選取，不略過、刪除或改寫 append-only queue receipts。任何 active pending source 都必須以完整 portfolio／result／檔案雜湊／aware 時鐘／execution session 身分精確唯一對回 scoped 或 legacy 來源；legacy fallback 會以 bounded、regular-file、no-follow 讀取驗完整目錄，找不到唯一符合者即 blocked，不讓新 frozen source 代替既有 pending。選取結果的 source path、hash、result、portfolio、日期與 fallback proof 會在 candidate／status hash 前固定；有 selection metadata 的 producer 在任何 effect 前重新讀取並比對同一份 bytes，若檔案被替換或改動即 blocked。直接呼叫既有 API 而沒有 selection metadata 時維持原契約，不假造 pin。

Position Health `position-health-daily-refresh.v1` 對同一來源日期、identity、來源 clock、coverage 與 `available_at` 作嚴格驗證；legacy baseline 日期不符仍拒絕。transition reuse 僅在完整 proof 確認 v2 研究內容身分完全相同時允許：保留原 transition event 與原 input hash，將本次 current input hash／available-at 寫入新的 append-only receipt。無法驗證一致或內容實質變更時仍 blocked、wrapper nonzero；Evidence #2 的 persistence identity conflict 即此類失敗。不得將其降成 warning/degraded，不覆寫舊內容，也不新增 SQLite schema。Health `observation_only` 表示用舊 Paper holdings 作當下研究觀察，不能推成同日 Paper producer 成功。

Formal denominator resolver 只有在 active config 的 `activation_trading_date` 等於 observed_at 的台北當日，且 aware clock／current archive 都通過驗證時，才可自動尋找當日 denominator；以 16 MiB 上限的 bounded no-follow regular-file reader 驗證原始檔案身分與 hash。環境或支援設定明確指定的 expected-universe pin 優先；明確無效或空 pin 也會 fail closed，不會由 auto-discovery 取代；coverage pin 同樣不自動換值。解析證據保留來源路徑、檔案 hash、日期與 resolver reason，不改寫 Rule archive、不取 universe intersection，也不把 14 份歷史 out-of-scope archive 算成 blocker。

BankTaiwan wrapper 先等待原 05:45 calibration Task 的同日 terminal run identity 與 immutable receipt；最多等待 1,800 秒，每 5 秒輪詢，30 秒輸出一次最多 4 KiB heartbeat。若已有 matching current-run terminal projection，且 native LastRun／runStart 的容差、completed/mtime、immutable receipt、canonical artifact、invocation/cohort 與 hash 的雙重讀回都通過，即使 Task state 是 Running 或 Ready 也可採用；只有缺少有效 matching terminal proof 且 Task 已停止、LastRun 改變或期限到達時 fail closed。native 時鐘容差不是唯一辨識條件，不能排除極短時間內再次觸發的 race。原 Task 總執行預算為 7,200 秒，包含前置檢查、等待與 child，並保留 300 秒 terminal flush reserve；child 的實際 timeout 依剩餘預算裁切，通常不超過 6,900 秒。snapshot source 與 operational JSON 各限 8 MiB，pipeline terminal receipt 限 64 KiB，child run receipt 與 raw CLI stdout artifact 各使用獨立 16 MiB 上限；raw stdout artifact create-only 並精確 hash/readback，不能用較大 cap 放寬既有 source scope 或把 raw output攤入 operational JSON。


### 2026-10-01 研究收集與排程狀態

既有 `baldr-v2-2-weekly-collection` Task 繼續呼叫 `scripts/scheduled/run_v2_2_weekly_collection.cmd`，本輪沒有新增 Windows Task。Weekly wrapper 只在 core collection exit 0 後啟動兩個分開的研究 child：MOPS statement availability child 預設啟用，可設 `BALDR_ENABLE_MOPS_STATEMENT_CUSTODY=0` 關閉；季度 OpenAPI research child 預設啟用，可設 `BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH=0` 個別關閉。兩者互不跳過；child failure 由其 per-run status/terminal 與 wrapper process output 檢查，不覆寫 core collection exit 或 `pending_human_review` 語意。

Statement availability child 使用最近完整台北 7 日窗口，輸出到 repo `output/research/mops_statement_availability/<run-id>/`；它保存公告研究事件，不是季度財報數值表，也不代表正式 availability mapping 已接受。季度 child 只以明確 `--capture` 執行，每次最多 2 個官方 catalog GET 加 24 個固定 TWSE／TPEx income/balance GET；每 URL 一次、0 retry，connect/read timeout 各 30 秒；60 秒/request 與 900 秒/run elapsed gates 都是在阻塞 read 返回後檢查，不宣稱硬牆鐘中止。Create-only candidate 放在 `output/mops_quarterly_openapi_research/<run-id>/`。成功 HTTP response 與 preview 仍是 current-observation research evidence，不能宣稱全市場 issuer coverage、一般金額單位、歷史 announcement available-at、PIT、Formal、訓練或 credit。實際 10/1 capture 有 8 列保留在 key/schema review；需看[季度 OpenAPI QA](../06_qa/SCHEDULER_QUARTERLY_OPENAPI_RESEARCH_CAPTURE_20261001.md)及[來源與單位盤點](../06_qa/FUNDAMENTAL_SOURCE_ACCEPTANCE_AND_QUARTERLY_CATALOG_20261001.md)。程式與 mock route 已驗，但 live capture 尚未由下一次自然 weekly Task 讀回驗收。

Daily Quick wrapper 的月營收 research child 只有 core phases／technical publication 與 terminal history/status 全部完成後才執行；`.cmd` 預設開啟，`BALDR_CAPTURE_MONTHLY_REVENUE_RESEARCH_CANDIDATE=0` 可停用，Python caller 未帶參數仍維持舊 ABI。它把官方 TWSE／TPEx response 保存至 `output/fundamental_research_candidates/<run-id>/`，不寫正式 CSV、DB 或 availability map。檢視 run status、raw、receipt、candidate manifest 與 readback；目前候選是 2026-08、完整 1,978-key research scope，date-only availability 為 source capture 台北次日 2026-10-02，單位／source acceptance 與 Formal apply eligibility 仍 false。第一次 sandbox WinError 10013 failure receipt 需保留，不和後續成功 run 混成一次執行；完整實測與限制見[基本面 bootstrap QA](../06_qa/SCHEDULER_FUNDAMENTAL_BOOTSTRAP_20260930.md)。

每日 ML source-row projection 已有獨立 no-write preflight 與 repo-local research candidate 實際 readback。runner／`.cmd` 預設同次執行 prospective daily-price capture 與 `--project-daily-source-rows`；`BALDR_ENABLE_ML_DAILY_SOURCE_ROW_PROJECTION=0` 可單獨停用 projection，`BALDR_ENABLE_ML_PROSPECTIVE_DAILY_CAPTURE=0` 會同時停用 capture 與下游 projection。runner 只在 core freshness proof 後、source-revision gate 前執行；只有同次 capture 回傳 `captured`／經驗證 `already_captured` 且 candidate readback/pins 通過才呼叫 projector。Capture 未 verified 時 child 不啟動；projection failure 只新增診斷，不覆寫 core／revision-hold／process exit。候選位於 `output/qa/ml_daily_source_row_research_projections/<source-date>/<projection-id>/`；wrapper 在同候選 create-only 寫入並讀回 bounded `runner_terminal_verification_receipt.json`，主 runner `output-root/scheduled/ml_raw_pit_refresh/latest_status.json` 另帶 `prospective_daily_source_row_projection` 的 terminal path/hash。只看 `completion_receipt.json` 的 `awaiting_terminal_revision_validation` 不代表成功。Hook/wrapper focused route 為 46 passed／1 skipped（Windows symlink privilege），py_compile 與 scoped mypy 通過；黑箱測試只呼叫短暫複製 wrapper 與 fake child，未執行正式 runner 或 natural Task，先前受控 CLI 結果不能當 hook 收據。下一個自然 05:05 Task 尚待同次 nested status 與 per-run terminal receipt 驗收。此 candidate 沒有 feature／label、unit claim、PIT、Direct/OOC 或 Formal credit。核對[hook QA](../06_qa/SCHEDULER_ML_DAILY_SOURCE_ROW_HOOK_20261001.md)及[單日投影 QA](../06_qa/SCHEDULER_ML_DAILY_SOURCE_ROW_PROJECTION_20261001.md)。

9/30 Pacific 16:15（10/1 Taipei 07:15）的 Paper Portfolio 與 ML forward Task 當次 terminal 尚未驗證：inventory `output/qa/scheduled_task_inventory_20261001T002916Z_940402272834.json`（52,144 bytes，SHA-256 `9bbe91e9c6b1cc723222e87cd92a9751e8ff9985de9f3d7f4f76c2946193e374`）於台北 08:29:16 檢查 21/21 exact root task paths、0 errors；兩個 Task 均 Ready、`LastTaskResult=3221225786`（`0xC000013A`），runtime `waiting_for_taipei_cutoff`／`terminal=false`、heartbeat stale，latest 仍是前一日。此清冊早於台北 08:30 cutoff 44 秒；Paper XML 未明列 ExecutionTimeLimit、ML forward 為 PT2H，兩者沒有 delay，operational logging disabled，但這些設定不能證明原因。原因尚未知；不以舊 latest 或 Paper execution EOD 06:00 no-work receipt 替代同次 terminal，待 same-run terminal／runtime receipt 可讀回後再判斷。

手動檢查既有 source candidate 可用 `scripts/project_ml_daily_source_rows.py`。不帶 `--write-candidate` 時只做 no-write preflight；manifest 路徑及 SHA 必須取自本次 readback：

```powershell
.\.venv\Scripts\python.exe scripts\project_ml_daily_source_rows.py `
  --candidate-manifest <verified-candidate-manifest.json> `
  --expected-manifest-sha256 sha256:<readback-file-sha256>
```

只有明確加 `--write-candidate` 才建立 create-only research candidate；`--output-root` 限 repo 的 `output/qa/ml_daily_source_row_research_projections/` 子樹。Standalone CLI 完成時應保存最終 stdout JSON，並核對 `status=completed_research_only`、`verification_completed_at`、manifest／observations hashes 與 row count；wrapper 另需同候選 `runner_terminal_verification_receipt.json` readback 及主 runner nested status。中間 `awaiting_terminal_revision_validation` 不表示完成。拒絕／失敗時保留已寫候選，不可改 source hash 或 output root 以繞過驗證；每次手動執行的 stdout 和 native exit code 應存成唯一 QA receipt。

9/30 05:15 Evidence 的 machine seed `1418` identity／thesis warning 不代表使用者欠真實成交或 thesis；`portfolio_alert_snapshot_quality_not_ready` 與 `risk_prompt_snapshot_quality_not_ready` 仍需獨立來源排查。9/30 05:25 已成功持久化 `eod_research`／`research_only` capture 且 `natural_authority=false`，證明低階研究 event 可以在 seed degraded 時保存；這沒有解決 Health transition、verified lane 或 Formal qualification。Freshness 受控 probe 另已核對 Quick run/status/history identity，但 Freshness 仍 degraded 並保留四項 fundamental warnings；這也不代替自然 Task 驗收。整體最新事實與 receipts 見[排程修復 QA 後續 addendum](../06_qa/SCHEDULED_OPERATIONS_REPAIR_20260930.md)及[Snapshot](../00_core/PROJECT_SNAPSHOT.md)。

下列原章節已移至手冊附冊；入口、參數、步驟與限制保留，舊標題維持導向。

## 現行排程操作入口

上述 2026-09-30／10-01 收據只作歷史追溯。現行排程操作請看[21 個 Task 驗收 Runbook](../07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)；目前狀態請看 [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md)。


## 2026-10-11 Revision-Aware 研究早期操作模板移存

> 下列內容是早期研究模板與當時限制，完整保留作歷史證據；現行受控研究接受範圍請依 Manual §7.0.1 與具名 QA。不要將早期命令模板視為目前操作授權。

<a id="revision-aware-early-template-20261003"></a>

### 歷史：Revision-Aware 研究早期操作模板（2026-10-03）

本節保留本輪早期修復時的模板與當時限制，後續真實訓練／保存／新程序推論及Legacy／Bank已完成受控研究驗證。現行操作與接受範圍以7.0.1及[整合修復紀錄](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)為準；下方「仍待」只描述該早期檢查點，不能當目前狀態。

以下命令仍是參數模板，`<...>` 必須換成修後 CLI 及當次真實 readback；此刻不是全流程已通過宣告。固定使用 active research root 下的新輸出目錄與 aware 的真研究 freeze，不照抄 10/1 歷史截點。完整入口說明見 7.0.1；訓練、重新載入與 Legacy／Bank verified research context 的確切命令會在取得實跑證據後同步於此。

#### 1. 目的與安全邊界
市場歷史行情修訂後，正式 PIT 閘門依決策時點拒絕回填。研究流程保留 actual revision／current observation clock 與歷史 event／label 時鐘；研究使用不代表當年已可得或正式模型資格。
- **安全邊界**：
  - 所有產物一律標記 `research_only=true`、`formal_dataset=false`、`formal_oos_allowed=false`、`production_alpha_bp=0`。
  - 金融來源、策略與績效核心使用 `Decimal` 或整數基點／尺度。模型 array 的浮點轉換僅在已明確治理的分析邊界進行，仍須核對有限值、尺度、registry 與 masks。
  - 嚴禁輸出至 `release_v4` 或正式 `D:` 資料根目錄，`release_v4` pointer 保持不變。

#### 2. 路徑 A：年度 Shards -> Direct Numeric Store -> Raw-to-OOC 全鏈路操作

##### 步驟 A1：匯出修訂感知研究年度 Shards
目前修訂歷史的實跑入口是 `build_ml_pit_year_shards.py --current-restated-research`。先取得單一 readonly transaction 建立的一致副本與 receipt，核對副本／receipt 的 actual bytes SHA；原始來源路徑用來驗證修訂 namespace 與 dependency closure，不會寫入來源。此模式必須明列最多 20 檔 symbols，使用 active research root 下的新輸出目錄。

```powershell
.\.venv\Scripts\python.exe scripts\build_ml_pit_year_shards.py `
  --database <verified-consistent-snapshot.sqlite> `
  --output-dir <isolated-output-raw> `
  --decision-at <actual-aware-source-selection-clock> `
  --data-selection-as-of <same-aware-source-selection-clock> `
  --snapshot-database <verified-consistent-snapshot.sqlite> `
  --snapshot-receipt <verified-snapshot-receipt.json> `
  --expected-snapshot-database-sha256 <actual-snapshot-bytes-sha256> `
  --expected-snapshot-receipt-sha256 <actual-receipt-bytes-sha256> `
  --original-source-database <original-source-db-path> `
  --history-start-date 2022-10-01 `
  --symbols 2330 2317 `
  --years 2023 2024 2025 2026 `
  --current-restated-research
```

`--years` 在此模式依歷史 event 年份分片，`--history-start-date` 是來源歷史起點。`decision-at`／`data-selection-as-of` 是本次來源選取時鐘，必須帶時區；它們不是實際模型 fit cutoff。receipt 觀測、修訂 dependency 驗證、raw 衍生及完成各保存真正時鐘，後續 fit 必須晚於實際可得的全部輸入。未開研究 opt-in 的正式預設與來源 guard 保留；`--allow-source-revision-research`／`--research-candidate` 不會自行把 unknown availability 變成歷史 PIT。

**產物與判讀**：`<isolated-output-raw>/runs/<publication-id>/manifest.json` 明列實際發布的 dataset，current-restated 模式使用 `ml-current-restated-year-shards.v1`／`ml-current-restated-observation.v1`、int64 加十進位 exponent 與明確 masks。原公告／可得日未知則保持 null。raw 包含大盤／產業 context，row count 不能當股票訓練 sample count；有產業指數也不等於已有 verified 股票產業對應。必須再完成實際 Direct／模型消費驗收。

UTC 10/3 第三次受控 raw 執行 exit0，四個 2023–2026 shards 已由 root 全文讀回：73,234 observations／281,699 values 的 hash、筆數、數值格式、masks 與時鐘相符；合法千分位 parser 與成交金額 TWD unit 已修，原全空價格保持缺值。首次 NameError／exit1 與舊版本限制保留。當前 Direct 已完成後續建置／讀回，CORE19／模型仍在修復，詳見 [整合修復紀錄](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)。價格缺件或 quarantine 必須保存日期位置，不能補零或壓縮掉日期；遇到來源／receipt pin mismatch、naive clock、缺契約或不足空間時先修具體原因，以新輸出根重試，不改舊 immutable 產物或降低保護。

##### 步驟 A2：建置隔離研究 Direct Numeric Store

當時的 outcome-only checkpoint：入口需要 A1 已實際發布的 manifest 及外部 actual bytes pins，明確列出研究股票，並使用全新隔離輸出。UTC 10/3 `03:21:47Z` 真建置完成，`03:23:16Z` public loader 與獨立原價重算接受1,796股票觀測／49來源特徵／8 folds／6,709 labels。此段記錄模型鏈完成前的歷史狀態；目前受控研究接受範圍與限制以本手冊 §7.0.1 及[整合修復紀錄](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)為準。

```powershell
.\.venv\Scripts\python.exe scripts\build_ml_current_restated_outcome_store.py `
  --raw-publication-manifest <isolated-output-raw>/runs/<publication-id>/manifest.json `
  --expected-raw-publication-manifest-sha256 <publication-actual-bytes-sha256> `
  --expected-core-dataset-manifest-sha256 <core-child-actual-bytes-sha256> `
  --output-dir <new-repo-output-ml_research-directory> `
  --benchmark-entity-id TAIEX `
  --target-symbols 2317 2330 `
  --minimum-train-dates 125 `
  --test-date-count 63 `
  --purge-trading-days 60 `
  --embargo-trading-days 5
```

`minimum-train-dates` 在此新入口是 purge 後的實際訓練日期數，最低125；test最低63、purge最低60、embargo最低5，而且須有至少四個合格 folds。T+1 使用下一個真實 benchmark session 的開盤價，5／10／20／60日標籤使用該 event 後第 H 個 session 的收盤價；缺價格必須保留日期位置並阻擋受影響標籤。股票與 benchmark 的 return 欄為 gross，`benchmark_excess_return_bp` 已扣買25／賣55、共80基點，manifest 的 `outcome_cost_contract` 揭露此語意。下游不能把它當 gross 再重複扣同一費用。

成功時 CLI 會列 `manifest_path`、actual bytes SHA、feature registry SHA 與 fold 數；還須經 public verified loader 核對 raw、數值 arrays、來源 closure、實際時鐘與標籤，才可交模型消費。`blocked` 時先依同次錯誤查來源映射、價格缺件、成熟標籤、容量或 pins，修正後使用新輸出重試，保留原失敗。此 store 不建立 allocation teacher／ledger，不具有歷史 PIT、正式訓練或投資效果資格。研究 symbol cohort 與當日推薦 cohort 分開判讀。

以下是既有 PIT／allocation schema 的模板。目前新 current-restated raw 的正確下游為受控 outcome consumer，正在完成實跑接線；不能僅以 `--allow-research` 將它宣稱成完整 allocation／teacher Store。
```powershell
.\.venv\Scripts\python.exe scripts\build_portfolio_ml_direct_numeric_store.py `
  --raw-manifest <path-to-all_field_enriched-manifest.json> `
  --output-dir <isolated-output-direct> `
  --training-as-of <actual-aware-research-freeze> `
  --benchmark-entity TAIEX `
  --allow-research
```
**切分限制**：未帶 `--allow-research` 時仍拒絕研究 Shards。opt-in 不授權降低 horizon 所需 purge／embargo；不足真成熟歷史或完整 stack 的 fold 數時維持 typed不足，不以相鄰 70/30 切分製造評估。

##### 步驟 A3：建置 Out-Of-Core 研究訓練 Store
使用 `build_portfolio_ml_ooc_from_raw.py` 並傳入 `--allow-research`：
```powershell
.\.venv\Scripts\python.exe scripts\build_portfolio_ml_ooc_from_raw.py `
  --raw-manifest <path-to-all_field_enriched-manifest.json> `
  --output-dir <isolated-output-ooc> `
  --training-as-of <actual-aware-research-freeze> `
  --benchmark-entity TAIEX `
  --years 2024 2025 2026 `
  --allow-research
```
**目前限制**：研究 opt-in 的旗標傳遞與 consumer 正在整合；此命令模板尚不是完整研究 OOC 建置通過證據。缺上下文、成熟標籤或 teacher 時應回具體阻擋，不能僅憑 `lane="research_shadow"` 宣稱已產出完整訓練資料集。

#### 3. 路徑 B：單日投影／候選資料適配與消費操作

針對每日夜間前瞻捕獲（Prospective Daily Capture）或來源列投影（Daily Source-Row Projection）產物：
```powershell
.\.venv\Scripts\python.exe scripts\adapt_ml_research_direct_ooc.py `
  --raw-candidate-manifest <path-to-projection-or-candidate-manifest.json> `
  --expected-candidate-manifest-bytes-sha256 <actual-source-manifest-bytes-sha256> `
  --output-dir <isolated-output-adapted> `
  --training-as-of <actual-aware-research-freeze> `
  --benchmark-entity TAIEX `
  --consume-direct-store <isolated-consumer-store-dir>
```
**收據與驗證**：
- `adapter_receipt.json`：包含來源候選 SHA-256、row count、market revision digest。
- `consumption_receipt.json`：須綁實際已保存並經 loader 讀回的整數、尺度、missing mask、feature registry 與來源 bytes pins；自填未動 pointer 欄位不證隔離，也不證 train-ready。

UTC 10/3 `01:15:57Z` 的生產 CLI 真來源驗收已讀回 1,962 筆／7,658 個值，全部通過來源分母尺度與新十進位 exponent 的獨立 Decimal 比對。此結果為 `verified_numeric_observations_ready`，仍是 `historical_pit_eligible=false`、`blocked_insufficient_context_or_mature_history`；沒有建立 fold 或訓練模型。當次命令與 receipt 見 [整合修復紀錄](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)。

#### 4. 重型維護鏈研究模式穿透
旗標須傳到每一層實際 consumer；研究續跑不得呼叫正式 release coordinator，不能只把 flag 傳到 Direct Store 就說訓練接通。缺 teacher／ledger／PIT provenance 時保留具體阻擋；有界 base outcomehead 研究與正式 allocation／promotion 資格分開，不能偽造 teacher allowed。


#### 5. 現行操作入口

本節僅保存 2026-10-03 的歷史模板與當時限制。實際操作請回到 [APPLICATION_MANUAL.md §7.0.1](../07_guides/APPLICATION_MANUAL.md) 與[整合修復 QA](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)，並依當前證據重新核對；本節命令不是現行操作授權。
