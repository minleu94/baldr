# Baldr 每日快照政策與 P03 隔離驗證（2026-10-14 UTC）

本輪依使用者決議恢復[原補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)，不另立總計畫。本輪跨使用者時區10/13–14；各收據原UTC時間保留。完整 P00–P14／G0–G4 尚未接受，舊 FAIL、P08 私有候選與其他 owner 的 singleton 保留。

## 接手核對

HEAD `10eb154af9c553354c73e57fcb2fafa724b82b8a`，開工工作樹只有原計畫增量。暫停清冊 50 份資產及兩份恢復後產品／觀測收據，共 52 份完整 SHA／大小相符；另保存 3,165 tracked source 的本輪基線（範圍為程式／JSON／TOML，非全庫 EOF）。私有 task 為 `output/tasks/baldr-completion-policy-20261014-01a1390b/`；既有 `active_task.yaml`／`handoff_log.md` 及前 owner task 不修改。

08:13 UTC重新核對時HEAD已由其他owner提交到 `5cedd65710db21d9d1863695dcfa4ee0edb872ec`，僅三份Direct排程文件，沒有改本輪程式候選。本Root未stage／commit。新文件記同次Direct未fit成功、teacher inputs缺件、自然terminal及具名owner授權只停用Direct maintainer；本輪保留該狀態，P12不自行重啟。52份原保護資產及9份新收據SHA／size已再核。Root首次readback JSON沿用固定舊HEAD，另存更正 `readback_20261014_head_correction01.json` SHA `889fc2e3a4c2d422d83f95609995a2e97fa73013890fe18d4097db08ada317b0`，保留錯誤原件與核驗結果，不冒稱舊HEAD仍current。

接手盤點 outer `single_owned_qa_93e31a5d7b4f49f181ae9bfe0b0515f0/receipt.json` SHA `5b9cfba06059000e7b829bcd26ab3b6390e66e67085c150569189e8b570d72f1`，位於 `output/qa/baldr_completion_20261011/root/`。本輪來源清冊與 `resume_audit.json` 保存在本 task。原 P08 同組合收據 `6e98adea` 為 **10 PASS／4 FAIL／0 SKIP**，observer DATA `72270c49` 只觀測 worker，不能將四個產品 FAIL 改寫成 PASS。P01 原篩選 385.9978ms／strict300ms FAIL 與暫緩其前置的決議保持。

## Scrapling 隔離環境

第一次受控安裝因沙箱 DNS `getaddrinfo failed` 失敗，原私有環境收據保留；outer `9ae470a6` 自然 PID0、handles 關閉與 mutex 釋放。依已授權隔離驗證，取得網路執行核准後另建 `scrapling_environment_network/venv`，不修改 `.venv` 或正式資料。

Scrapling **0.4.15** 已安裝，PyPI metadata SHA `456b8182ae5cc71ae948a005184047a9364d895901f637662abc7cf0f0ccf9d4`；依賴鎖 SHA `ceb34616ae6fdc4ef4101d92f8398d94f6e4390f877e8babb4fa2db10dfe825c`。`pip_report.json` 保存每個下載 artifact hash。安裝 outer `2b9864f2` 自然 PID0、handles／mutex 關閉；這只證明隔離安裝成功，**MOPS 取得鏈尚未驗證**。工具使用邊界依 [Scrapling 官方 fetcher 文件](https://scrapling.readthedocs.io/en/latest/fetching/choosing.html)，不假設能突破 WAF。

## 施工與未驗範圍

一次 EZSearch→t57→附件探針已實際執行，**FAIL** 原因 `requests_request_timeout`：EZSearch 單次耗時20.781秒超過原20秒，HTTP200、442,065bytes原件完整保留，SHA `280cb374eac0d96eb75e50c891cc31606c07c2835854373fb38a3423758d9dd6`。保存內容為 `status=success`／1000列；server截斷／完整性未知，不能由目標未見推論公告不存在。未取得合格目標列，t57／附件未在此鏈執行，沒有重跑或放寬期限。`scrapling_static/true_probe_attempt01/probe-receipt.json` 保存逐請求表單、時間及原因；outer `69b5d076` 自然PID0／handles／mutex關閉，outer0只代表受控觀測完成。

另一個官方host的獨立單次Scrapling t57 session GET在9.031秒回HTTP200，5058bytes原件SHA `dc8d533ea747f62164aa452d4009cfe1477783145ec2db63d38672b7b8e77daa`。精確命中2330／115年第一季／中文IFRSs合併財報，列出 `202601_2330_AI1.pdf`、5,271,067bytes與官方時間原文 `115/05/15 14:43:02`（台北2026-05-15 14:43:02）。狀態是 **MATCHED_LISTING_ONLY_DOCUMENT_NOT_FETCHED**；沒有附件、官方用途接受或完整鏈PASS。原件與收據位於 `scrapling_static/t57_session_attempt01/`，outer `85f9ca4b` 自然閉鎖。Scrapling此模式先載入body後才核8MiB，非streaming early cap；Job committed-memory上限仍8GiB，不能稱為8GiB磁碟輸出上限。

保存t57原文的 `readfile2`／`fm2` form提供可核對的 `step=9` POST動作，下一個兩請求候選依此取得附件，不猜URL。原EZSearch的1000列／期限FAIL與t57單列資格分開，取得PDF仍須檔名／大小／hash／格式及版本、值／單位／前期品質核驗；browser／動態模式未驗，未證明可突破WAF。

後續附件探針已實際執行。第一次在發出任何request前因隔離venv缺`tzdata`失敗，原outer `b1a7be8b` 保留；補入與專案相同的tzdata2025.3後，來源腳本SHA及原期限保持，再執行尚未開始的兩請求探針。POST在1.141秒回HTTP200，491bytes原件保存，依返回的同源明示href得到官方下載位置；GET在20.016秒由curl28中止，報告只收925,696／5,271,067bytes。**完整t57附件鏈FAIL，沒有PDF可驗收**；Scrapling例外未回傳可保存的partial body，因此本次只保留POST原件、下載位置及錯誤，不宣稱925,696bytes原件已保存。

附件收據 `scrapling_static/t57_document_attempt01/receipt.json` SHA `57780289eb771f533c07dc3b3f0fa63f0394d1b659f940d5db41b7ec981cab2a`，控制收據 `t57_document_observation02/receipt.json` SHA `10f43ee179b8b42c41f0412d82a560ade841798d2ad594368d2547e833f3f78d`；outer `4aecb785` 自然PID0／handles／mutex閉鎖。實際共四個來源請求（EZSearch POST、t57 listing GET、表單POST、PDF GET），沒有browser、重試、WAF bypass或提高20秒限制。現行取得限制不能由小時政策或單列匹配改為PASS；來源scope、分期／前期品質、PDF內文、public reader與正常UI仍待。最終隔離套件鎖在 `t57_document_observation02/03_stdout.log`，SHA `3014208313d4b31d7e59ef006aa361785377a914575768bf38c95af0d19f2736`，原初次鎖與pip reports保持。

P00／P03 小時契約、immutable 原件／版本快照、用途接受與每日 validation，以及 Recommendation consumer 由 Luna 靜態施工，Root 審閱並執行 QA。MOPS probe 優先既有 EZSearch API 與 t57 文件清單；需要 session／動態頁才使用隔離 Scrapling。正常 UI／新程序、更新服務與 P12 批次投影、真來源品質、同版 EXE／Native／完整 Gate 仍待其實際證據。本頁隨本輪實際 QA 更新，不把未執行項目寫成通過。

Root sol 一次一組 8GiB／12 程序 Job，至少 8GiB 可用 RAM，前組自然歸零、handles 與 mutex 關閉後才下一組。此次新建三位 Luna Max，只做靜態工作、禁止子代理；上限 3 同時、10 新建。沒有正式資料寫入、全量回補、正式 Task 變更、push、發布或交易。

## 小時契約與 consumer 實際 QA

正式工作樹新增 `daily_source_snapshot.py`／專屬測試，修改現有 Recommendation current-fundamental provider／測試。此實作先限定 MOPS monthly v1／v2 的原件版本，真官方接受尚未在本輪簽發；fixture 可信錨點不算官方用途接受。來源／用途錨點、單位／schema／有限值／缺值／必要前期檢查、原件及版本 SHA、ROC 原文、台北時區、固定批次、不回填歷史與 quarantine 均在此窄契約處理。

早一版完成組 `hour_contract_qa05/receipt.json` SHA `8d083367aed02a701178b52520b24d9f81cdf7e911e65bfc73fbf4f125f26485`：同組三份套件 **61 PASS／0 SKIP，1.77秒**；包括1200列及真正子程序round-trip、caller trust anchor、錯版本／用途、兩時鐘ceil、cutoff不ceil、ROC原文、批次外壞列不污染指定批次、更正版本、receipt／availability tamper、缺成功receipt、晚接受、partial／單位／品質、跨整點及發布超過guard隔離。Changed-file compile、兩來源mypy、量化精度／look-ahead linter皆通過；context metadata check為12 features／29 link sources、errors空，只是結構檢查。

另外的真正writer→退出→新reader使用合成raw、公開file writer／reader及明示可信fixture錨點：writer PID25640、新reader PID41440，manifest SHA `77b7a11113d36a96b6daa29d649803416b60031e02fd57850b9a4fa4da4978be`；固定版本原件及11:00 gate、10:59:59拒絕皆核對。此為合成快照新程序證據，不算真來源、正常Main／UI或同版EXE。Outer `0209f149` 三組PID陣列空、process／Job handlesclosed、mutexreleased、無forced／deadline；8GiB／12程序readback保持。

原QA01的24FAIL／34PASS保留：接受時間判斷反向與Root選用深basetemp造成兩項Win206。QA02的26FAIL／35PASS保留：沙箱拒絕新建目錄的resolve核驗、兩個既有calendar fixture缺`observation_clock`。後者只補fixture的實際介面及同一aware observation斷言，未改產品calendar。QA03的2FAIL／59PASS保留：用途反例原先在fixture建構提前拒絕、invalid basis值被SQLite CHECK正確拒絕；改為真reader錯scope＋可信原scope錨點、可合法保存但normalizer必拒的NaN壞列，沒有放寬CHECK。QA04的61PASS但5個mypy錯誤保留；QA05只窄修反序列化型別縮窄後重驗，原斷言／守衛保持。各組原log、JUnit、receipt與outer完整保存在本task及既有Root QA根；不累加案例數為更多或包級接受。

正常 UI／固定批次每日 producer／P12批次投影、其他資料 ports、正式來源一次性接受、OS-crash recovery、P07／P08／P13／P14完整旅程及產品Gate仍未完成。P08原10PASS／4FAIL、P01原p95 FAIL、Paper／Forward自然成熟原要求不變。

## HTTP 原件橋與月營收接線增量

manifest v2 分開保存實際 HTTP body／SHA 與舊 MOPS v1／v2 使用的 UTF-8 canonical payload／SHA；v1兼容讀回明示canonical-only，不補造 transport。新 DTO 要求 HTTP200、完整 EOF／Content-Length、實長、明示 charset、strict decode、精確 trusted endpoint／document chain、body clock 與 v2 clock相等；reader 重新核對。Canonical 16MiB、transport16MiB、manifest48MiB／receipt24MiB上限明示。月營收 preparation 只證明來源報表列，不宣稱全市場 universe；候選原值千元，既有normalizer用Decimal乘1000。巢狀來源表目前拒絕，仍需實際layout證據才擴支援。

QA06為**80PASS／1FAIL**（原件篡改先被charset拒絕，診斷未命中既定SHA斷言）；Root把SHA身分檢查移至解析前，原斷言不變。QA07為**80PASS／1FAIL**，單一原子rename的WinError5；staging原件保留。新單案handle診斷無retry，三次獨占read-open皆成功並關閉，rename及原exact-hour斷言通過，收據outer `f2f6c543`；這只能說明診斷當下，原拒絕來源仍未知。QA08 compile／三來源mypy及真正writer成功，新reader揭露materialized YoY comparator漏成功批次hourgate，原FAIL保留。Root修為pinned comparator取自身兩時鐘與parent available_hour的max，晚觀測仍受自身cutoff約束。

QA09 `hour_contract_qa09/receipt.json` SHA `af46861a69bef629c5efbadedf24ee658fe2b2352c9f73caeaaf113f973e954c` 同組四套件**82PASS／0SKIP，2.48秒**，compile與三來源mypy通過；outer `badb45a7` 自然PID0／handlesclosed／mutexreleased。合成Big5→parser→原normalizer→只含2330的隔離DB→pinned public consumer的新PID旅程：writer49924、新reader51848，transport SHA `39e72afc6cce8b2e0e1193b1cd03117febb986a5bda07e3f336aada9855bb6d7`、canonical SHA `b7f1c6c4ec2170599ef534e24125255c414e040fd808bee9c3545719ab2ba838`，manifest `9d083b0d4dee6ffbf44fb4392920c53d039247d9a68d99d8943cd72927f886d7`，收據 `cc2a9a6a8de0d9f15320711a679df04c63f0879a03c1ad8c5a349533058ce80d`。來源1000千元→1000000TWD、前期800千元→800000TWD，16:00才可用、前1微秒拒絕，兩者formal PIT仍false。後續新增巢狀來源表反例單獨核驗preparation **12PASS／0SKIP，0.39秒**；不與82相加為包級接受。

月營收官方新probe依原API，TWSE／2026-09單份報表、consumer目標2330、三個請求上限。POST redirect在3.469秒取得378bytes，popup GET在1.859秒取得2964bytes；兩份原件及SHA保留，明示static連結至 `t21sc03_115_9_0.html`。最後GET HTTP200但僅保存**262144／448751bytes**，阻塞stream read返回後觸發20秒接受限制，實耗**24.547秒**，原件SHA `6fee295a06feadaabae289440f785d7fcab12e48276c4ffb7b73c00666951759`，未讀到EOF。**取得鏈FAIL、未建合格transport capture或snapshot**。此探針的20秒接受守衛不能在阻塞read中即時中斷，屬執行限制；不宣稱deadline按20秒硬中止。全鏈29.875秒、Root hard120秒subprocess限制保持，無重試。來源收據 `monthly_official_probe01/receipt.json` SHA `81f17f75f1774844f5f50887009c4386ff566faa0378ccf6f63e0fc42ccb2975`、control `7a436b1e212eefacddb33a5b9c5b9610fd6853d4af994b5a4202bd2abda2ee7d`，outer `f36a9748` 自然閉鎖。該三次請求屬獨立月營收scope，財報原六次預算及四次結果不改寫。

## P02 同 callback backend

重用原Luna進行獨立補完，不設Scrapling完成為其前置。V3 opt-in opener加入同 callback F07 fact/digest、reader-issued session與失敗poison，保持V2與F07原分類、Decimal、canonical digest。獨立靜態複核已檢查parent ledger／來源／日期／完整population及取消，不代替QA。首組compile通過，但pytest collection因錯誤volatility module import中止，原 `p02_v3_qa01/` 收據與outer `224cc7d9`保留；受控修正／重驗進行中。Composite query條件、正常UI／bookmark、新程序及包級Gate尚未完成。

修正import後QA02同組在原pytest subprocess **300秒 TimeoutExpired**，不延長／盲重跑；outer `3a534126` PID0／handlesclosed／mutexreleased。該舊runner在TimeoutExpired未保存partial stdout，是證據缺口；原runner／收據留存，新增private v2 runner以檔案串流保存輸出及owned child timeout回收事實。單案診斷保留原257股／兩parent完整斷言，30秒faulthandler只得到 `personal_data_paths._windows_utf16_units` 單frame／line0，60秒停止，根因仍未知。mypy另外定位13項新slots型別缺件，author已加明確annotations、未加ignore；受影響compile／mypy另驗。量化guard因mypy失敗尚未在此組跑到。V4固定256分段，使合法雙parent至少257股票；不能用更小母體冒稱原多parent接受。診斷outer `dd137882`自然閉鎖，但pytest child由明示timeout停止，不能說該產品驗證自然通過。

後續 `policy_governance_qa01/` 已核新版group compile、P02四來源mypy及全repo量化精度／look-ahead guard均PASS；最後task check因四份治理SSOT coverage漏列而FAIL，原outer `f3f1dddb`保留。補入依現行規則不需修改中央入口／流程／角色卡的具名理由後，只重驗治理，`policy_governance_qa02/` 為PASS：12 features／15 link sources、errors空；outer `0b9610fc`自然PID0／handlesclosed／mutexreleased、無forced cleanup。這不解除P02 runtime timeout、真來源取得、正常UI或完整Gate。最後source inventory／SHA及安全接手點保存在本task；本輪仍三名Luna Max重用，未增worker。

## P02 保存來源的受控重播

原257股案例的單次stage journal核到 `_write_prices` 約15ms，之後停在 `fixture_technical_producer`，尚未進入V3；60秒停止，outer `938c607c` 收據完整閉鎖，不能推論producer根因。原300秒失敗留下完整 `f17-bundle-v1-synthetic-19iy2zfr`，Root另外以公開metadata／Current source pins／store exact parent callback重新驗證，沒有重跑或縮小母體。此保存來源為258 declared、257 included、1 excluded、兩parent；來源coverage partial、current_only、historical PIT false仍保持。

唯讀重播QA01／02因harness的Windows長路徑掃描／解析失敗，原收據保留；修OS I/O渲染後QA03／04揭露V3內部byte counter誤觸外部immutable守衛，Root改用內部 `object.__setattr__`，沒有放寬外部守衛。QA05第一個success案例通過，poison案例揭露public V3 error漏傳既有Bundle `cause_code`；補原因傳遞，原錯來源斷言不改。兩次SHA參數誤拆的CLI失敗均在QA前退出，outer `1d51aafc`／`1d8e3ab8` 保留，不算產品執行。

`p02_saved_readonly06/receipt.json` 記錄**三個原consumer test function逐一通過**（非原producer pytest suite），包含單次bundle讀取／一store callback／兩parent／257原fact與Decimal／digest、第一列身分poison、取消清空且不得issue。原價格DB、technical／market／disposal／bundle來源簽章前後相同；manifest SHA `550cf2ae0c1f404164c6b8b5cb9c548531342bd485a2ce1ab03a784994979cb8`，bundle identity `b2c1eba0e5bcdd5dd68166495032afd9bd6f2f5aefa080d9fa774650855302db`，兩parent及其receipt／plan pins在原stdout完整保存。Outer `single_owned_qa_f2505f4be3734f59b81491c69b3433c1/receipt.json` SHA `fa892f0a6ad963006ede9eb452f5a1095a66b3bcc0ddf36a3c49f2ebfd3023e6` 自然PID0、handlesclosed／mutexreleased。這解除指定保存來源的V3 consumer缺陷，原producer300秒、正常UI／query／bookmark、新程序及P02完整Gate仍未接受。

## P08 正式工作樹接線與未完成QA

Root沿原P08候選精確forward-port到HEAD `5cedd657` 的工作樹：共享策略版本來源、可選外部Paper artifacts root、最多200筆明示帳戶的唯讀catalogue、選列後exact reader、Paper與Historical雙卡及合作式關閉。缺設定／壞設定只停用Paper入口，不擴為自動帳戶建立或任何writer。Account／ledger金融核心未改；catalogue候選仍未驗證、不可授績效資格。原14整合測試與六套canonical regression採入，候選來源重新釘SHA。

正式QA01 compile通過，七套件**85PASS／4FAIL**（37.55秒），Root把basetemp放在repo內而正確觸發外部artifacts來源守衛；原fail保留，改用專屬外部temp及明示隔離DATA_ROOT／OUTPUT_ROOT等。QA02為**87PASS／2FAIL／0SKIP**（85.30秒），兩個原10秒discover等待失敗，outer `4f96af61`自然閉鎖。時序journal定位worker停於exact binding與personal path驗證；首次faulthandler診斷另發生native `0xC0000005`，outer `fd9aa1ad`保留，不能稱原生診斷通過。

獨立pump觀測只在原 `QTest.qWait(10)` 後讓Python執行緒1ms，catalogue約1.406秒、exact card約2秒，apply與native cleanup皆在UI執行緒。Root僅補測試pump，原10秒期限／來源／bytes前後及所有原assert保持；原案例繼續揭露真reader card被widget拒絕。定點journal找到帳戶每日operation hash與ledger operation hash誤比；新增兩個具名hash域並各自綁定，未刪身分拒絕。QA03 compile通過，七套件**97PASS／5FAIL**（55.38秒）：四項新增反例的文字assert不符，另一項真card因新格式守衛錯把公開 `sha256:<hex>` 當裸hex而拒絕。原FAIL／診斷收據全保留；格式與新增文字assert已按原public契約窄修，Root重驗尚待。QA03在suite失敗後未跑到必須的Workbench／update validator／八roots mypy，不能宣稱已通過；正常Main／fresh、同版EXE、完整期間績效／來源可得性及P08完整Gate仍待。

## 有界單次HTTP工具的隔離QA

為處理原阻塞read超20秒的執行缺口，私有候選採一個真正worker／一request、絕對20秒包含啟動，controller逾期kill／wait／close，partial raw逐chunk保留；禁止redirect／retry，只有HTTP200、EOF、Content-Length／實長與byte cap全符才可成candidate。Controller及worker必須實際具名Job membership／PID讀回，環境變數非證明；整組PID0由Root outer收據核對，worker收據不冒稱controller仍存活時整組已空。20秒不包含後續hash／receipt I/O；同步程序啟動的最後兜底仍是outer Job期限。

本機loopback QA01 compile通過，**1PASS／8FAIL**（8.65秒），原TemporaryDirectory測試fixture已清除attempt sidecars，是保留證據缺口，沒有宣稱原件仍在。修為task-owned create-only持久fixture及具體診斷後，QA02仍**1PASS／8FAIL**（8.68秒），sidecars完整保存，Root核到每例均 `worker_job_pid_does_not_match_popen_child`：Windows venv launcher PID與實際worker不同。真worker會員與query handles已驗，但不能以只reap launcher當真正worker停止。Outer `e7224050`／`f139cd3d`整組自然PID0／閉鎖，這不折抵getter失敗。

候選已改為經hash驗證的實際base interpreter，`-S`停用base site初始化，僅明示controller隔離venv purelib／platlib並清除PYTHONHOME；Popen PID仍須與真worker sidecar一致，membership／after-reap守衛保留。Root runtime驗證尚待；本組僅loopback，沒有追加官方請求、來源用途接受、合格snapshot或正式寫入。原月營收三次與財報四次probe失敗及預算不改寫。

後續窄修完全依原public `sha256:<64 lower hex>` 格式，錯hash／缺hash／malformed拒絕仍保留。`p08_formal_qa04/receipt.json` 同組七套件**102PASS／0SKIP，50.11秒**，包括兩個原10秒Qt旅程；必要Workbench **85PASS，2.69秒**、update validator **25PASS／0FAIL／4protected skips**（實際下載與合併保護跳過）、八roots mypy **968來源檔PASS**及changed-file compile通過。Outer `single_owned_qa_c8fa57cc273d43cbbbf7e2ff9cf50d17/receipt.json` SHA `c34bbd6be8df16364008206db9bfc594a3de07989a0e6aed9ef55c6f6c2c4194` 自然PID0、handlesclosed／mutexreleased。不能加總85／102為產品Gate；正常Main／fresh／EXE及完整績效待其各自證據。

有界getter移除所有繼承的PYTHON*覆寫後只設定三個明示值，新增環境污染反例；loopback handler threads亦在關閉時join。`http_loopback_qa03/receipt.json` compile與**10PASS／0SKIP，8.59秒**，涵蓋headers卡流、body卡流保留prefix、長度不符、缺長度clean EOF、長度完整／Cookie延續且收據不曝值、byte cap、拒redirect／空body、假具名Job及Python環境污染。每次直接worker PID與Popen相等、實際named Job／binary hash核对、reap／handleclose／after-reap PID消失皆通過；outer `single_owned_qa_f2e1239818264c4f808b4592ea8ab494/receipt.json` SHA `7049c848364cf33f0ffd5a1185a3f1e9f80db34e7da0e071eacf60de16a16ddf` 整組自然PID0／闭锁。這只證明本機有界執行，尚未證官方取得或16MiB邊界；下一scope與預算依原計畫§9.5，沒有重試或延長原失敗期限。

## 最新限定旅程與取得結果

P08 `p08_main_fresh_qa01` 在Main建構前因harness誤用大寫mode而FAIL；原 `personal` 列舉守衛不改，只修harness，outer `095d525d`保留。QA02 changed helper compile及真 `ui_qt.main.MainWindow` 父26532→新PID43032旅程通過：使用正常Main共享StrategyVersionService與真cash-seed／daily writer建立兩個合成零成交帳戶，父程序由Research Lab導航→明示帳戶／版本／cutoff→候選選列→public exact reader讀A、B；關閉後新PID重開A，核對同operation／snapshot且未讀B。11份version／contract／binding／state DB／ledger DB的bytes与stat在讀取／close／fresh前後一致，Python socket API守衛記零嘗試；沒有OS-level網路擷取證據。推薦query／payload hashes與時鐘均是明示fixture，空market root不構成真行情旅程；source UNVERIFIED、NOT_QUALIFIED、metrics None／期間曲線不可用保持，不能推論兩策略同股盈虧／完整期間／Native／EXE接受。

旅程控制收據 `p08_main_fresh_qa02/receipt.json` 及兩phase完整stdout／stderr、外部留存 `C:/Users/archi/AppData/Local/Temp/baldr_p08_main_01a1390b_qa02/fixture/p08-fixture.json` 可追溯；outer `single_owned_qa_4c15dd29a24e4d8787a58490ceddc295/receipt.json` SHA `1602d92da2161f25a8dbcf3c7b5dbcd8ad0adf38b7db97ec9f77f3b312753c75` 自然PID0／handlesclosed／mutexreleased。每個discover／read原10秒保持，120秒phase／300秒總只為執行上限，不當效能Gate。

月營收單次scope的preflight先發現候選receipt SHA多一字元，**零request**退出，outer `55b2b3b6`保留；原receipt实际SHA仍 `81f17f75f1774844f5f50887009c4386ff566faa0378ccf6f63e0fc42ccb2975` 未變。只修候選拼寫後，`monthly_single_http_hard_deadline_01` 實際一GET／HTTP200，在20秒截止停止：保存**294912 bytes**，未EOF／body incomplete，**FAIL**；實際含kill／reap生命週期20.015秒，後續hash／receipt I/O不計入20秒。真正worker17132與Popen PID相同、named Job／binary hash核對、reap／handleclose／PID消失均通過，candidate false。沒有質量接受、DailyCapture、snapshot或正式用途接受；同scope create-only拒絕重跑，沒有retry或延長。

driver receipt SHA `5a13cf25ed8353eec66b8b6b3f9794fdc056fad83e635c31863b126156bc7f77`、partial原件SHA `8fe6a178cd806bc637345bf3de8bc7a1587b0d32005342e496fb42c04e2648a3`，位於 `monthly_single_http01/`；outer `single_owned_qa_ff2e158668a44db4aa782c86906951a2/receipt.json` SHA `70a62c5a24d519b82498f9231dd273059b5d1a8d53964cc40e44495c43863442` 整組自然PID0／闭锁，但driver／control exit2／1仍保留为失敗，不能用資源收尾成功改為來源PASS。

P08新增範圍的document_control Level0核兩份excerpt／679字、未驗unknown清單空；已登錄的G03／G05／G08既有raw／歷史接受／逐來源資格unknown仍保持，Level0不取代正文與原QA。治理QA03因PROJECT_NAVIGATION coverage漏列FAIL，原outer `adbb780d`保留；確認既有導航未變、現況在Snapshot／Manual與Feature Map後具名記not_required，只重驗治理。QA04為**12features／19link sources／errors空**，outer `4698ecb6`自然闭锁；不授產品Gate。update validator本輪報告另存 `p08_formal_qa04/update_validator_report.md` SHA `abf85e497b3b0f8fb3ad5b0010cebc78785633938ba99eac869bc6e40df06086`。

下一資料候選已有repo官方TWSE OpenAPI route與research-shadow／diagnostics scope，仍缺單位的官方強錨點與獨立JSON版本／parser契約；不把它改名為MOPS版本。政府[官方資料集 metadata](https://data.gov.tw/dataset/18420)列出出表日、本期／去年同月欄位及官方Swagger入口，但本次查閱未取得明示營收單位證據；出表日不是發布小時。不得直接套MOPS千元轉換或把shadow用途提升為推薦／正式scheduler。完整P00–P14／G0–G4及Paper／Forward自然成熟仍未完成。

## TWSE API 窄範圍原件診斷（接續批次）

同 scope `twse_t187ap05_L_2330_11509_schema_metadata_01` 最多兩GET，沒有重抓MOPS或擴至TPEx／全歷史。第一個官方Swagger GET為HTTP200、309960bytes、EOF及Content-Length一致、18.906秒，raw SHA `06e1cea82448361e733a0ad1ae16e52f5d5d6b71905acd078472f852c32c0eb0`。診斷腳本把task-relative raw ref誤接repo而FAIL，尚未發API；原driver receipt SHA `c269f91ddc959f4926eca1708c6fc6989e4679d0210453b23ce9870dd8a379ff`及outer `477cc4b9` SHA `b1d235ddfa9a412bee737b90450da03f8302d5d0aa6cc6f98be7a2953c37f431`保留。

修正診斷接線後只使用已保存metadata，消耗剩餘一個API GET，沒有再取Swagger。官方 `/opendata/t187ap05_L` metadata列有五營收金額、三百分比、公司／期間／出表日等文字欄位，未明示金額單位；saved metadata SHA `bf91865a9d81ab73eef6404c9af652561ebfbd21efbc59198b83f3d1241428a2`。API HTTP200，20秒停止於**507603／597961bytes、未EOF、FAIL**，真worker58608==Popen，kill／reap生命周期20.016秒，partial SHA `9d9371a3ea0f8d1b26b3ee3e6041a990314b98cf80cde3b60f290ef43a8f8b3a`。完成收據 `twse_api_finish01/receipt.json` SHA `ee528d5a70091a6827057105668efa5b4d923939cd7329e58d7241b786244a76`，outer `332f654e` SHA `be5d2da14d52a949dcfea51f4c5e323c65bcd18c06ab2f74efaa6863596d63aa`。兩outer三PID陣列空、process／Job handlesclosed、mutexreleased，資源收尾不折抵source FAIL；scope已用完，未發行capture/preparation成功、快照、consumer或source×use接受。

TWSE API傳輸完整度仍是A／D阻塞，官方單位證據是D品質阻塞；日期缺小時可依B政策取得成功批次小時，不能用它消除前兩種缺件。其後獨立JSON preparation leaf與P02增量的實際驗證如下；前述來源FAIL及請求預算不改寫。

## P02／TWSE 保存來源的受影響驗證

下表逐段列結果，不能相加成工作包或完整Gate。所有Python由Root同一受控wrapper串行，Job限8GiB／12程序；下列outer均三個終態PID陣列空、process／Job handles關閉、mutex釋放，沒有forced descendant cleanup或deadline事件。來源fixture仍是257個included／258個declared／一個excluded、兩段已保存parent，current-only／PIT false。

| 範圍 | 實際結果與證據 | 保留的限制／FAIL |
|---|---|---|
| 正常bundle V3 opener | `p02_normal_saved_result02.json` SHA `45500efc9880bba3f5649a57edb3b9f4dcec598b4dbd586893dee14482501429`：三個原consumer函式直接重播，正向／poison／cancel及來源簽章通過；compile／四來源mypy通過。outer `dcd0ac39` SHA `df56ba4230bcf2240beef338155ca7e8b90fc6df67a090ab2d4fce9188ab4657`。 | QA01取消回呼被錯誤包裝的FAIL保留，只在新normal path補取消檢查。不是原producer pytest suite或正常Main。 |
| V2 query／價格共通gate | `p02_v2_saved_backend_result03.json` SHA `fc524cb50abf02c468a2fc783622b0058e4aa05acc8f9db90be1731ee67b320a`：11個原consumer cases直接重播通過、兩來源mypy通過；涵蓋MA／KDJ OR與AND後共通價格gate，及四個replace＋重算digest仍被issuer anchor拒絕的反例。 | 控制QA01有30個型別錯誤、QA02 mypy argv錯誤均保留。QA03後段Root新JSON測試引用不存在的Result decoder而collection FAIL，整組exit1不寫PASS；outer `f52e38c3` SHA `3d348c758fb075a300241c6d55a0f24416b8b5174c3b43b8889d1ec68dd02851`。沒有因此盲重跑已通過11案。 |
| V1價格JSON邊界 | `price_json_twse_saved_qa02`：四個原新反例pytest **4PASS／0SKIP，0.30秒**，string-aware預檢、字串括號不誤判、既有zero-based深度邊界保持；不改schema／原4096bytes cap。 | 首輪fixture超舊byte cap形成3PASS／1FAIL，原FAIL保留；只縮反例輸入到原byte cap內，深度拒絕斷言不變。 |
| V2 presenter／bookmark | `p02_v2_saved_presenter_bookmark_result01.json` SHA `75dcf368e3835e3e01cca90d5853ada413b2a86a90277001184b36fd3ae92200`：三個presenter＋十個bookmark原case直接重播通過、来源簽章一致；Workbench **85PASS，2.92秒**，validator **25PASS／0FAIL／4protected skips**。報告另存 `p02_v2_presenter_bookmark_qa01/update_validator_report.md` SHA `b58950f6d284ff0bb88aac11742098ab4fe27742837a4fa043284a94e2c6d7b9`。 | QA01八roots mypy有19個bookmark錯誤，整組FAIL／outer `cedf1ff0` SHA `191c5dca112f93ff9a4edd0e619ca83c5985720a43d28ba15736496ad9ae5087`。未將consumer或Workbench PASS折抵typing失敗。 |
| bookmark窄修重驗 | 改型別收窄／具名factory參數／slot annotations，原測試及限制保持。`p02_v2_saved_bookmark_result02.json` SHA `a4c77cf62da16ea2af1a28c7f84016c061acd7704d7c50d33f2bc6d800074453`：只重驗受影響十案及compile；八roots mypy **972來源檔PASS**。outer `f46c5619` SHA `9f788ca81a21535cef5bbcc7cf07e2b35f64b540defadaeb570324f5dc3536e1` exit0。 | 未重跑不受影響presenter三案、backend十一案、Workbench或validator；正常Main／watchlist／持久保存／新程序尚未接線，沒有V2正常UI接受。 |
| TWSE JSON preparation | `monthly_revenue_openapi_preparation`獨立rawcapture／parser／preparation v1，**44PASS／0SKIP，0.50秒**、compile／mypy／financial-float與lookahead守衛通過；真API partial507603／597961bytes被拒絕。outer `467bf953` SHA `38559ceb1ab8d6385d2c1ec5b3f6e0e5b69308ee6d4f9bce62eab86e80bbd742`。 | 首輪非ASCII bytes literal compile FAIL保留，修測試UTF-8 encode。金額是原字串的bounded finite Decimal，單位仍unverified；不套MOPS千元換算，不發布snapshot／推薦／排程。 |

上述直接重播由Root逐一调用原test functions／原parametrization及必要fixture body，使用已保存真writer產物；不跳過或改寫原斷言，也不是再執行慢producer。原producer300秒／60秒FAIL與其成本原因未知仍留存，三組全域母體與來源守衛沒有縮減。

## 既有完整TWSE原件的唯讀／新PID解析

發現既有owner候選 `output/fundamental_research_candidates/20261013T114147003735Z-548312e36b0544d1b32324b17b6ef105` 的TWSE完整原件：484247bytes／869rows，raw SHA `fe46f95454ae4968f029ae0a6b2867d04d4f11d1ee99ce49f05daa45b714037e`；status SHA `f30b7513db5ea40aafc48bb88666555b4f615d44007f4e47a328b8e5df1cadfc`、manifest SHA `c3eb02d04db0044538736987b5a8c6a4c2599a5a459f0a7351ca9a439f2a6959`、capture_run SHA `9aceb88e5b5583afc89de78c28b6851dd94503d17ebf3ed530f3ed33f4506ed9`。四檔原bytes未變，本輪沒有GET、沒有驗TPEx／全市场或改owner的舊「capture次日」政策。

Root只驗2330／11509，嚴格company／期間／出表日／JSON來源版本及原件hash。舊capture v1沒有新版getter的native membership／EOF欄；完整body依原captured終態、Content-Length精確相等及完整JSON推得，明示為legacy完整度證據，不能冒充新真抓取。Last-Modified／HTTP Date／etag保存，但不是已驗公司發布小時。

父PID33056→新PID45600的parser payload、raw hash、source version及新validation batch時鐘一致，四檔原件仍未變。新批次完成時鐘 `2026-10-14T11:04:48.357119+00:00`，台北候選可用小時 `2026-10-14T20:00:00+08:00`；不倒填到10/13舊capture，不發布DailySourceSnapshot。`twse_saved_preparation01.json` SHA `cc4d663e8f4ab69f2ae8edda9af23b0e63625b279ea49d5f0e490b02c612a71d`；fresh SHA `f20c151f874d19434767255fe39dc92e7cf7dd11d861dc76eae266a6d7fd86be`。與四案價格JSON同組outer `8638c154` SHA `40bcfc19203e734016c20c8f6aaf14952dbd0adcdac5b9ff1c20e1e2ec1e055b` exit0。Python socket guard只是本程序API守衛，不是OS-level無網路證明。

這解除保存完整原件的隔離解析與日期缺小時卡住（B），並重用原件減少重複抓取／驗證（C）；當輪API未EOF（A／D）、同版本官方單位強證據（D）仍未解除。候選只供shadow／diagnostics，沒有×1000或source×use正式接受，scoring／advice／portfolio／scheduler及歷史PIT仍false。下一批沿原計畫§9.5，P02正常UI／保存重開與P03單位／ports並行，P08期間／執行／自然成熟保持獨立。

## P02 V2 收藏儲存與正常頁接線

新增獨立view-state v2 envelope／source，外層只綁內層canonical bytes／hash、股票、來源及storage identity，不複製basket／scroll。WatchlistService新增typed add/read及exact schema dispatch，原V1路由保持；V2不走generic context或latest。Root正常Main新增「官方條件與價格研究」頁，保存／重開依typed envelope選相同版本頁；關閉流程包含新view。來源缺件、錯stock/source/hash、未知schema及無法完整呈現的外部多排序鍵保留明確拒絕，不把保存payload當來源重核資格。

Storage QA01 preflight可用RAM7319904256bytes低於8GiB，**沒有child／Job啟動**、observed PID空／mutex釋放，exit125及outer `e7972471` SHA `0a59d865666a3824abe3af33183cf4ed3478f864077acb5d295c51d1ebdcad64`保留。Windows GlobalMemoryStatusEx唯讀讀回資源恢復後才執行；不降低門檻。實際QA01 compile PASS、mypy兩錯誤／consumer未跑，outer `840164d5` SHA `ae984f0bb6a280f45716d1cfd20cb8466a6e3f095c6fd40bb6176613af1ccdbe`保持FAIL。Root只修strict bytes/str guard之後的型別收窄及重複annotation，不改測試。

Storage QA02 compile／兩來源mypy及**14原consumer cases直接重播PASS**：八個envelope cases與六個Watchlist cases，包括JSON保存→新service讀回→隔離SQLite migration→新service讀回、移除／restore，以及stock/source/hash/unknown schema反例。來源完整簽章一致；這是task-owned私有資料，不授正式PERSONAL migration。Outer `b3a5ebc9` SHA `f1857514ed24d86f52bf7d124fedcc418d867b98cac42150187bcb93e97eaf26`自然PID0／handlesclosed／mutexreleased。

正常頁QA01 compile及八roots **974來源mypy PASS**，但Root轉接fixture誤把寬technical-output root交給舊walk helper，深子路徑WinError3，UI案例未跑；outer `e5c794ae` SHA `e788bfc4dfc4ef8f32a870aad5c668b3d0d64bf2cdafad0bebcc460a0ecf1d04`保持FAIL。轉接改回原fixture來源集合（price DB、store、雙parent、market、disposal），另有Root完整五樹before/after守衛，不改原test／來源／母體；QA02在new view錯import尚不存在的module而FAIL，outer `7bfeb669` SHA `2c855a717cbdaf745e9b27ce17d395cdb1e75937c6d8fff4279aa1a8e73aa557`保留。修正真module名後，本機import目標靜態檢查無缺件。

靜態複核另發現外層錯身分仍顯示「已收藏」、Main不處理restore False即切頁、外部多主鍵排序會只呈現第一鍵。Root已加入exact row label guard、restore拒絕時保留當前workspace及多排序鍵在任何view狀態變更／開來源之前拒絕，新增原子性與身分反例。QA03當版974mypy PASS、兩個原consumer（多排序鍵原子拒絕／Decimal獨立控制項）PASS；主UI旅程因counts標籤缺「原」字而FAIL，outer `1c798565` SHA `d335df555ae97237a4b68a7bbf6b1ab7bec39f7a2f81bd43020257b6689364d6`及result03 SHA `326c298d05df153ee748823d6623535033776607ef86832b73b6c84846f43919`保留。只修presenter標籤，讓四群原結果與後續AND gate清楚分開，沒有更動計數或原斷言。

QA04以原result03／spec SHA及未變的test／view／Main SHA具名重用兩個已PASS案例，只執行剩餘**七個原consumer cases PASS**，不是pytest skip或宣稱QA03整組通過。涵蓋完整257股／雙parent、價格全域排序與分頁、詳情／比較籃／保存pins重開、early cancel／poison、四個row label案例及Main拒絕不切workspace。當版compile／974mypy、Workbench **85PASS（2.63秒）**、validator **25PASS／0FAIL／4protected skips**亦通過；報告另存 `p02_v2_normal_ui_qa04/update_validator_report.md` SHA `56d129f3c3149a9d5014e68571602198b52deee0b2f4f5a154f5a2be306728df`。Outer `b9f73cd0` SHA `6fc9f3a6d14e5d08c7ebb9440a7fc80e99c2f734b6866e08e28f4117775ab099`自然閉鎖。兩組九個具名案例的覆蓋不相加成產品Gate，也不是慢producer suite、實際Main、新PID、Native或EXE證據。

實際Main／fresh隔離旅程QA01已建構Main，但Root要求900px超過真offscreen800×800，原viewport守衛拒絕；改回原640px後QA02因漏helper必要window keyword而FAIL。兩個舊Temp roots及outer `50af021c` SHA `eee33a08206f6fafa793e3543bfe614880739127bcae8da95d9596daaca2aaee`、`f0a07b35` SHA `5a467f5b25372552e001dfb859bdba460355c5a74e2d84191cccc5efa9872521`保留自然閉鎖FAIL，沒有source保存／fresh資格。Root已逐一核helper接口及原可見控件命中guard。

QA03在新私有Temp中，父PID **54060**完成真Main可見V2頁籤→257股／雙parent→價格bounds／inclusive／未知政策及全域價排序→兩頁選列／比較籃→正常typed saver→Watchlist可見按鈕→同Main exact重開。Parent receipt `C:/Users/archi/AppData/Local/Temp/baldr_p02_v2_main_01a1390b_qa03/fixture/p02-main-parent.json` SHA `6b8bd226eb2c9c40097d40963b55602e1c59ba28c4b5c9aa56f910b15a8181f4`，source完整簽章一致、Python socket零嘗試、current-only／PIT false；不授OS-level無網路、真行情、Native或EXE。

其後fresh不同PID已讀回同envelope、result JSON、pins、page、選股與basket，但精確scroll還原FAIL，後段controls／close結果未收成功收據。整組QA03及outer `6f0d2320` SHA `e755d67fdd4bf8cb4026e4d5228a5cc01412e48f23b60e5a002fa2941507868b`保持FAIL，outer自然PID0／handlesclosed／mutexreleased不折抵UI故障。這是新Main首次還原的D執行缺口，正在核layout／range延後更新；修後只續受影響fresh與UI回歸，父旅程與保存原件不盲重跑，也不放寬原scroll／來源／期限斷言。

## 新Main捲動恢復窄修與限定fresh成果

V2 view將首次還原的同堆疊setValue改為最多12次、每次16ms的layout／range穩定檢查。ticket綁revision、同result/page及operation/page/selected-row identities；目標可達、range連續兩次穩定且setValue讀回精確相等才發operationSettled成功。等待期間視為未完成；新query/navigation、取消或close使ticket失效，不能延後覆蓋另一個研究。沒有無界timer或改scroll斷言。

`p02_v2_scroll_fresh_qa01` changed compile、當版八roots **974mypy PASS**及兩個受影響原UI函式直接重播PASS：原完整257股／雙parent旅程，以及新增brand-new view前兩次range未達目標的反例。fresh PID13452實測expected/actual/max均1962、viewport528×289、content528×2251、window640×700，全部收藏條件／pins亦一致；關閉後Root錯假定唯讀fresh已有lazy saver registry而AttributeError，整組仍FAIL，outer `9548fb41` SHA `52b6f1d1bb67c0659d327390ba7aae013b9ac6294bc9d4a8ae71fa181884acaf`保留自然閉鎖。只修harness允許registry未建立或真empty set，不改view／native完成／source守衛。

`p02_v2_scroll_fresh_qa02`不重跑父旅程、同SHA的兩UI案或974typing；只編譯改動harness、沿Parent完整SHA重用原私有根並續fresh。新PID **34696**由正常Main的可見Watchlist typed路徑重開同envelope／result／pins／page／row／basket、價格bounds/inclusive/unknown/sort，scroll精確1962，current-only／官方availability None／PIT false保持；合作close與零saver workers通過。Source完整五樹bytes/stat在成功及finally仍相等，Python socket零嘗試，沒有OS-level網路證據。

fresh receipt `C:/Users/archi/AppData/Local/Temp/baldr_p02_v2_main_01a1390b_qa03/fixture/p02-main-fresh.json` SHA `f8ea6b041ec55a3503dfd4b3777df3310dfeaee0d5d7cb30c1215684cb1d70c8`，與Parent54060同envelope SHA `1be4d65ec12e247d634939742f8760405372114543dbd8a27e4270640905c89b`。Workbench **85PASS（2.78秒）**、validator **25PASS／0FAIL／4protected skips**及financial-float守衛通過；報告另存 `p02_v2_scroll_fresh_qa02/update_validator_report.md` SHA `c074303393301d690c91d04a05fbdb39361e040891a8f6e7b4ad9b280689e6ac`。Outer `0e23fd76` SHA `3a257bda7745b7f7b7b1174a853a808b1648acdc96d86e75ce4cd38f0687235f` exit0、三PID陣列空／handlesclosed／mutexreleased，沒有forced cleanup。

這是**指定合成來源的正常Main→新PID旅程限定成果**。當版完整來源／治理讀回接續執行；原producer300秒／60秒、P01 p95、所有原UI／harness／來源FAIL保持。不能推論真市場N、真來源資格、歷史PIT、Native、同版EXE、完整P02、P08期間績效或全產品Gate。

## 當版治理與保護資產讀回

`policy_increment_gov_readback01`治理為12features／20link sources／errors空，範圍是結構與紀錄。Source readback `source_readback_increment04.json` SHA `5c5b1a875db47d5038c05b48b409db9f04196396fef0c4d3f1fbe0c4ba21f771`完整核68個本任務source、52個保護資產、27個接續outer（26自然閉鎖及一個記憶體preflight未啟動child）、六個原outer及11個P08來源bytes/stat。P02父54060／fresh34696在各自actual Job observed PIDs中、同envelope與scroll1962，TWSE原四檔SHA及原partial FAIL保持。HEAD仍5cedd657，69個dirty中只有DOCUMENTATION_GRAPH_GUIDE在本任務範圍外、owner未知，Root未改。

Outer `fdd9d868` SHA `147f50f3e30d1e728c54cdba8d6690bedb73440cbaa4fe719c8577aa07fca63e`自然閉鎖。最初PowerShell inventory因ISO date自動轉本地時區而選到零項，保留 `outer_job_inventory_increment04.json`；只修為aware UTC比較後 `increment05`實際27項，SHA `997b3d37fd230002fed4da1407f8117ba81f660be4e28de4f79af43922fa4e56`，沒有修改原receipt時間或刪失敗。本文加入結果說明後，最後source綁定與閉鎖指標依本任務 `task.json.latest_source_readback/latest_closed_job` 讀回，不把治理或資源收尾當完整Gate。

## P03 saved-capture 更新端口與 P08 日期保存續推

MOPS新增 `monthly_revenue_daily_snapshot_update.py`，UpdateService 的 save/status 入口均要求caller明示root、scope、可信用途錨點與batch；不抓取、不授來源接受、不選latest、不寫正式SQLite。完整Big5 capture經preparation及既有Decimal normalizer核值，再immutable保存並由新FileReader讀回。Quarantine有完整capture時用v2保存HTTP/canonical双原件、hash與metadata；無capture保持v1，壞capture只保存可用canonical failure。主拒絕保留，次級封存錯誤附note。Pending receipt留到發布後clock核驗通過，reader前後拒pending；clock失效、隔離目標碰撞／symlink分支／搬移失敗／barrier unlink失敗皆不得誤授成功。合作式取消在保存前與rename前，無原子取消保證。

原quarantine qa01 spec在啟動前因新增取消hook而被替代，沒有child或Job。Qa02實際37PASS／1FAIL：工作區rename WinError5，原因未知；outer8574b819 SHA `67ce77006b9d82b7d18386f2029267f4cb9cf8bb6bfdba2357978fc5613a0c69`保留。修主錯誤保存後的專屬Temp qa03為40PASS與mypy1，outereeb294ef SHA `b72de5eff70589f9d6fa185fdebcf09b6421b396597d926aff2856de59c5349a`；沒有改原斷言或把WinError5改記PASS。其後ports／postpublish barrier／原monthly status四套76PASS（2.00秒）、mypy3，outerd189f4ab SHA `e58b2b221e59d5feae61a575eb53dc31dea2489ef764fbe1dfde378866c55ee4`。

父15480的真UpdateService合成保存收據SHA `d22448344b9a46237d27546af566d901509612a56757f36e58f45bad7a2b2caa`；outera1665a6c SHA `629c8beb4871a0bf99f5ad0a83f84e7c4ac645ecebf9a26e38b7d26b8f702405`。第一次fresh harness以合成10/02批次小時作cutoff，但既有normalizer真本機materialization在10/14，原守衛正確拒絕；outerab4bbe07 SHA `7163417263e3fce828d83fdf689c6eec41abf40891664601ccb112865d9aa2bb`仍FAIL，P08回歸未跑。Root保留Parent／DB所有bytes不重產，改從保存observed_at决定實際read cutoff，並修provider pinned metadata為max(原observed availability,batch hour)，新增晚current／comparator不可提前反例。

不同PID20956精確讀回同batch，fresh收據SHA `0e60c818df7085c9cb114278a1062f5156261524616db72d2bbd75bc768645c7`；同manifest `e39d5dac3f17d487fda61458a0f5f809ba06a6a7556eb6ab2ced50446decb0b0`、receipt `44fbb10b2c88bd8e0e086b224b4dc729499d5199ad3b0764e07aed9e0690b6a0`，五个source/DB files前後bytes/SHA/mtime相同。1,000千元→TWD1,000,000及同報表前期800,000，snapshot11:00與本機10/14觀測各自保留，不倒填歷史；未知pin與提前cutoff拒絕，正式DB未建立。這仍是synthetic，不是真來源接受或正常UI證據。

P08靜態producer核對確認一般回測curve日期只在index、原Registry index=False會丟失。新增窄dated equity copy及兩个一般save caller，不改推薦portfolio sidecar、metadata、通用writer或金融核心；原金額／attrs／curve不變，沒有從metadata推造舊run日期。六套Registry／date回歸及provider合計83PASS（6.25秒），Workbench85PASS（2.63秒）、validator25PASS／0FAIL／4protected skips、八roots mypy976檔PASS、financial-float guard PASS。Outer28591bb5 SHA `f206531740650aea3603ce8990203590cb4866973436902dc80ab087874e94fd` exit0；本批所有Job三終態PID陣列空、process/Job handlesclosed、mutexreleased，無強制清除／逾時。

TWSE exact官方unit/version proof尚未取得，既有原值shadow不換算；已耗GET scope不追加。P03雙市場cohort pin／正常UI與推薦session／真取得鏈、P08versioned金額與幣別／成本／completion／雙策略同股全期間真樣本、Native與EXE及完整Gate仍待。原所有FAIL及保護候選不變，最新當版完整來源／治理綁定依task.json讀回。
## P03 雙市場 cohort／正常 session 與 P08 精度契約

新增 immutable cohort pin，各市場綁scope／batch／四組原件與snapshot hash／acceptance identity/hash；required markets同報告期與用途，整組可用小時為各市場最大值。Builder及reader只用caller指定batch與外部expected hash；固定root／anchor副本、重驗全部必要市場，拒半批、scalar繞過整組、錯範圍與來源替換。Current provider／正常InputPreparer/default composition/session已接明示pin及凍結natural clock，推薦context保存同pin與每股實際read outcomes；legacy無pin及historical/select-latest原路由不變。這是合成雙市場真writer／reader／provider／session限定鏈，未含一般Main picker、cohort freshPID、Selection source-clock新版、真來源接受或正式排程。

P08新增獨立pure precision V2契約／strict bounded codec，直接保存producer明示的canonical Decimal text，使用整數係數驗精確identity及minor units，不受ambient Decimal context捨入、不從V1 float推值、不改金融核心。日期coverage／typed completion／source-clock/hash／currency語法及authority明列；unknown或缺件不成完整可比money，資格旗標全部False。`money_comparable`僅為結構齊備標記，不驗ISO成員或來源authority真實性，後續producer／exact Registry reader仍須獨立核權威。尚未接producer loop、Registry或UI，不是真期間樣本。

QA01 compile通過，八套件97PASS／4FAIL（5.51秒）。四FAIL為receipt fixture追加空白仍合法JSON但斷言期待syntax error、historical fixture漏必需as_of_date，以及兩個舊calendar stub未接現行observation_clock；原Guard及原斷言不改。Outer7a236831 SHA `f00f7422cfdcec07fe87fc0de024032bcec8fa5a47a230bdc9cd67f9d5a42c0e`保留FAIL。

QA02只修三個fixture/API檔：receipt改為真正syntax corruption、歷史案例補explicit cutoff、兩stub明示observation_clock且新增等於frozen/observed clock斷言；原四案精確4PASS（1.35秒）。Workbench85PASS（3.00秒）、validator25PASS／0FAIL／4protected skips；fullmypy六錯誤均在新precision DTO的finite Decimal exponent及list/tuple annotations，原收據仍FAIL。Outere2e5b145 SHA `6680c71d6142684d83d29abb23dd4bfd6e9a083f6461f0687f85a04c82ba44b0`。

Root只補finite exponent實際int guard與create入口tuple固定化，精確算式／原測試不改。QA03只重驗precision原22案PASS（0.34秒），fullmypy978檔PASS及financial-float guard PASS；P03原97PASS／四精確案與WB/validator同source證據重用、不盲跑101案。Outer2d6a7b7f SHA `999f0a22e4c22c83401e5d51b0ea5095b039ecdb43e0e1139863709627956554` exit0。三組actual Job均8GiB／12程序，三終態PID陣列空、process/Job handlesclosed、mutexreleased，無forced cleanup／deadline；下組須待本組閉鎖。83own／84dirty中的範圍外DOCUMENTATION_GRAPH_GUIDE owner仍未知、Root未改；當版來源／52保護資產與收據綁定依task.json.latest_source_readback讀回，完整Gate未接受。

### P03 雙市場 pin 保存與新程序 input 讀回（同日接續）

沿既有已通過的Big5雙市場合成fixture，Root新增私有create-only驗證，不連線、不寫正式資料。QA01在writer negative case停下：Root錯誤預期提前cutoff狀態為unavailable，現行provider明確回missing／daily_source_cohort_not_available_at_cutoff且無observations。原outer aaf49982 SHA `97ffed7691c6b149081e3dd227d28cb2729708177106e7c8265b371e4f5082c9`、腳本及未發布parent的fixture保留。QA02只修為精確missing並加具名原因碼斷言，其餘守衛不改，使用另一create-only fixture。

QA02父程序41848保存兩個market snapshot、hash-addressed cohort pin與normal-input-context；新程序48188另由已綁定QA source明示的synthetic trusted acceptance重建兩市FileReader，外部預期cohort hash取自精確parent receipt。兩市金額1000000／2000000 TWD、前期800000、共同2026-10-02T13:00+08:00、各市場batch／raw hash、normal input與推薦context完全相同；提前cutoff、換invocation cutoff、錯外部hash及缺半市場拒絕。11來源檔案bytes／SHA／mtime不改。父receipt SHA `f3fda63b3ecf8f9d8f39e8831ab55b6bf8d91dd2d4b589395951e86563bfef6e`，fresh SHA `b80a8ce2b545a2f23b3a5535cb602012c01ba1f8558830ad44e542d8b8d39f53`，fixture位於 `C:/Users/archi/AppData/Local/Temp/baldr_p03_cohort_fresh_01a1390b_qa02/fixture`。

QA02整組仍FAIL：driver最後把venv launcher PID與實際Python PID直接比較；outer c01c64a3 SHA `c656d6c6c5c6d7128e7daf5a7823c927687e982a7c9e5f4a4d41fcd02a42caf7`及原斷言／raw保持。Root不重跑已成功的writer／reader，而在獨立readback03核兩個實際PID均在該native Job observed members、不同PID、parent/fresh SHA、外部pin、原context與11檔案一致；限定PASS收據 `output/tasks/baldr-completion-policy-20261014-01a1390b/p03_cohort_fresh_readback03.json` SHA `494c14d3847eaacc4bd36e5140319c2c1c4dab8048a757f9f5fc3deb92553f65`，outer 0a8e7b55 SHA `53454d69db7e5ef7fb21a6f5d0af9af9f9bb76822b82abe51ace9d82a8e04499` exit0。三組Job均8GiB／12程序、三終態PID陣列空、handles關閉、mutex釋放、無強制排空；失敗不能改寫成成功。

僅Python socket hooks觀察零連線，沒有OS網路審計。此為合成current-observed來源及正常input port／context重開，不是真來源用途接受、不含完整RecommendationService執行／Registry結果保存、正常Main UI／Native／EXE；historical/formal PIT均false，完整Gate未接受。因本批產品來源未改，原978-source typing／已通過的受影響case／Workbench／validator同SHA證據重用；文件與83source／52保護資產的最新綁定以本task.latest_source_readback為準。三個原Luna只產生有限Main／Selection V2／P08 producer靜態接線備忘，Root已修正Main備忘中的過時provider參數假設；產品契約仍以實作與QA為準。

### 正常 Main 固定 binding 與原 producer Decimal 捕獲（同日接續）

已沿原計畫實作外部binding v1：純serializer只序列化既有pin/readers及typed用途接受錨點；normal settings成對解析MONTHLY_REVENUE_COHORT_BINDING_PATH／SHA256，Main讀external expected hash及完整必要市場後，decision composition在建立服務前重驗，注入同一reader至preparer/provider。相對／空／部分配置／wrong scope/market/purpose/unit/parser/schema/hash、缺批次、JSON duplicate/type/size/UTF-8、symlink／Windows reparse及frozen包內artifact/root拒絕；None保持legacy。Root又將讀取改為64KiB+1上限並驗stat後增長，原內容/hash不自授official quality、unit authority或歷史PIT。

P08原next-session-open.v2 loop在float曲線前直接建立typed每日cash／position value／equity的Decimal text，精確守恆／唯一股票身分有效才capture；所有source/order/holding/snapshot code必須同股。多股／需正規化或非法碼／列契約拒絕、無實際loop觀察均failclosed；取消只有已跑partial，fallback不造新觀察。R/U P&L仍None、無新損益公式；result新tuple不入V1 to_dict/from_dict或Registry wire shape，缺currency/source/calendar/cost仍captured_unqualified，不授績效可比。

QA01 compile通，原10套件118PASS／2FAIL／1SKIP（5.83秒）。兩新binding測試錯用snapshot.market，Root修為實際scope.market不改市場值斷言；outer86d04198 SHA `f54845f8e15c7f33e2e21413176865a087c77efd5839f409251c2ffabd56ddb4`保留。QA02只重兩案1PASS／1FAIL（0.61秒），同case另錯用snapshot.period，實際期間在records；outeraa86f1b7 SHA `3d0614f9275fe8885a32a37893b00f10f61c34138b2ee3d6e897b10d736d9355`保留。Root核全部DTO存取，改為非空records且每筆period等於pin，QA03只重剩案1PASS（0.33秒）；Workbench85（2.39秒）、validator25/0/4 protected skips、八roots979來源mypy與financial-float守衛PASS，outer525e3d1d SHA `598c12779d6f990cfc98329ee7b2e5bb658b62921203512d9182c83abcbcec3f` exit0。

新增bounded read/stat-growth guard後，QA04只重binding／settings／composition受影響套件46PASS／1SKIP（1.99秒）及binding單檔mypy PASS，outer0ce413dc SHA `c6cefb74d6dc2d1c5f4e13b3343e09079fc7e6dde0c7ea7e3779b96aa2768fe8` exit0；producer／V1／UI／其餘typing同source證據重用。原SKIP為WinError1314無symlink creation privilege，非測試通過；沒有取得UAC或改權限。後續真junction獨立驗證不改寫此SKIP。

Private真Main harness經原Luna靜態複核，補actual PID／creation FILETIME／named Job對應，launcher只診斷；等待依原phase絕對120秒remaining，所有成功終止分支都要求未過原期限，確認actual Python退出才啟動fresh。Query handles finally關閉；timeout回收只可核同creation／named Job的exact owned PID，成功未經強制終止。

實際Main父29512→fresh33656（另launcher1820／40680）從同Baldr config載入外部binding，真推薦工作區可見、actual RecommendationService/preparer/provider同reader；兩市input金額1000000／2000000、同cohort/context、全部必要市場及來源18檔bytes／SHA／mtime一致。父SHA `90658d067cb1cccb393f02256b64565dee9f774ed07a3eee808135e669d592c0`、fresh SHA `2a47ee973671f7c788369756eff1b4306c760a58c821ca96934b93f359c90798`；fixture `C:/Users/archi/AppData/Local/Temp/baldr_p03_cohort_main_01a1390b_qa01/fixture`。兩phase皆以真Windows junction驗reparse拒絕，原symlink SKIP仍保留。實際PID在outer2af0d84f native Job observed members，SHA `34abf638f72445f65a738cf6d806538a73ac69a6f875099f424c06f4ac1e03d3` exit0。

本批5個actual Job均8GiB／12程序、啟動可用RAM大於8GiB，三終態PID陣列空、process/Job handlesclosed／mutexreleased、無forced descendant／deadline。兩原FAIL保留，新建Luna仍3/10、重用原三位且全static。Main fixture缺companies／market_indices／industry_indices明示fallback，沒有完整行情或完整RecommendationService執行／結果保存；只Python socket guard零事件，OS網路審計未做。合成用途／current-observed-only及historical/formal PIT false不變；真正官方source×use接受、每日版本自動配置、Selection V2、V2 Registry／期間績效／Native／EXE及完整Gate均待。當版91來源／52保護資產與既有收據的完整綁定以task.latest_source_readback為準，不把多組PASS加總成包級接受。

## 2026-10-14 續批：P08 V2 Registry／實際Main新PID與Selection V2

Root保留原HEAD `5cedd65710db21d9d1863695dcfa4ee0edb872ec`／owner成果；重用原三位Luna Max，未新增Agent，subagent只有靜態候選與複核。Root單組串行8GiB／12程序、原期限／PIT／來源／斷言不變。Shared active_task／handoff_log未改，沒有正式資料／Task寫入、全量回補、push／發布或交易。

P08新增frozen producer descriptor、同一V2附件包原V1 canonical結果與精確capture／可選precision，Registry要求明示initial cents／requested日期／execution，真Parquet SHA＋策略identity交叉綁定；strict public reader復原原typed capture／status／reason。V1 codec／wire不變；策略或具名cost缺件保留capture但precision None，來源／currency／calendar及內容hash不補猜，money_comparable與三資格false。P03 Selection opt-in V2在DB connect前與finish核full pin及全部required markets，row hash另含batch／first-persist，current-only/PITfalse；V1 wrapper拒V2，防止丟pin降格，完整V2 wrapper／decoder仍待。

| Root組 | 原始結果與處理 | 外層收據SHA |
|---|---|---|
| Registry QA01 | compile10 PASS；pytest原stdout19 dots＋2F，隨後120秒成本案timeout，沒有完整pytest終態；命令owned child被期限回收，外層資源關閉。不得宣稱19完整PASS。 | `715f6ae7b1837e7a7eba11a9c9293445f150bb4bca92abf45bc24e7f63e92194` |
| 精確診斷QA02 | 未改首失敗案1FAIL／1.05s：Root metadata fixture漏required original_input.config。補齊fixture，來源守衛與斷言不變。 | `837b576598eaf824f197c315a0de47591a4ba908659f4a757323bec1e1e10194` |
| Registry／Selection QA03 | compile13 PASS；215PASS／1FAIL／12.45s。超大原本金／full-lot仍保留，以整數有界搜尋呼原成本，原RecordingPolicy `[200,199,50]`呼叫斷言FAIL；修最大／相鄰probe順序，不改斷言。type／float未執行。 | `63a0fad215cf1b3beaed64b2897dd5fc60ecf54cd76ed79857f20a14ff70667c` |
| QA04 draft | 靜態發現V1 wrapper可降格丟pin，未執行；spec保留且由QA05替代，不稱FAIL或PASS。 | 無Job |
| 受影響QA05 | compile6 PASS；93PASS／10FAIL／8.10s。原成本斷言通過；Root新增wrapper exact guard漏import，原十案NameError。type／float未執行。 | `39c5e60b89aefb6291106cdfd42e9621228f12092e2c87774d4836a00614cdf7` |
| 精確十案QA06 | 漏import修正後原十案10PASS／1.75s；981檔mypy三typing errors（Literal default／optional pin local／cost status annotation）；只修typing，float未執行。 | `ddf9be0928b140c9527305e6bc9cef2b81b58426d399113270cbe40446bcd1ad` |
| QA07 | compile2、全八roots981mypy及financial-float守衛PASS；Workbench＋portfolio UI87PASS／3.39s；validator25PASS／0FAIL／4原protected skips。 | `a38fb0a81ef32742d29631f2ce069553045b61eb974fff3e4efcc2585a686b7e` |
| Main QA01 | Root fixture將僅環境PROFILE錯放portable JSON，原config守衛拒絕於Main建構前；已保存的private fixture／FAIL留存，修fixture不改產品守衛。 | `3eb708e6e611f61cb7b7f51a47cb58fbd3168cb4644021a287578a584db11119` |
| Main QA02 | 同原phase120秒，實際Main父56200→fresh40264；真producer／Registry writer→strict reader→既有opener→新PID，五源byte/SHA/mtime不變，原Decimal本金9007199254740993.01精確，無新的source／calendar資格。 | `e1d94381c7ecf4ff685651a7dbe2f68dfeca84d35f607a1d4427742c97658148` |

Main fixture：`C:/Users/archi/AppData/Local/Temp/baldr_p08_registry_main_01a1390b_qa02/fixture`。parent raw SHA `8c4107483b9c4cb10fec1e05ba6d6c7ded8e1d35e79fa3f0a18b01daf4405c52`、fresh `f776d8338d5f455683540aa1af7601e32e3fbe7ed4166909702ab7dce6c77dba`。另launcher10408／55336僅診斷；actual PID、creation FILETIME／named Job、native membership query handles及phase退出順序由Root核對，兩phase均actual_pid_not_live後才續。outer7c62包含兩actual PID，三終態PID陣列空、process/Job handlesclosed／mutexreleased，成功無強制清理或deadline expired。

所有原FAIL／timeout／SKIP維持。超大買單搜尋仍原非負bps／BankTaiwan最低成本、日期與Decimal捨入，無新損益公式或延期；巨大full-lot費用判定少於100次且原股數／資金asserts保留。V2 Clock新增exact string literal拒spoof，V1 wrapper手動注入V2在batch／finish拒絕並close，無finished manifest。原V1 sources與lifecycle回歸納入，未推定所有consumer已完成。

Main缺companies及market/industry DB明示fallback；Python socket guard零事件，OS網路審計未做。正常導航／實際opener與結果panel可見，但直接呼opener，尚未驗Registry列表點擊或保存按鈕、兩策略同股實現／未實現全期間、真來源／單位／currency/calendar、Native／EXE。P03每日自動版本配置及完整V2 snapshot／finished consumer仍待；MOPS/TWSE已耗GET不重試，Scrapling不加為全計畫前置。原P01 p95／Forward／Paper自然成熟與完整P00–P14/G0–G4 Gate仍未接受；局部PASS不加總。

當版102own sources／52protected assets／全部既有與本批收據SHA，以task.latest_source_readback及最後closed Job為準。Root只修受影響失敗案或typing；所有命令原stdout／stderr／JSON／JUnit保留在task，QA01 timeout僅資源回收通過，非自然成功。

### 完整 V2 snapshot 保存／reference 與真新程序（同日接續）

HEAD仍為 `5cedd65710db21d9d1863695dcfa4ee0edb872ec`，開工核前版102來源、52保存資產及原closed Job SHA；另一owner的 `DOCUMENTATION_GRAPH_GUIDE.md` 保持。Root沿同一copy owner新增完整V2 facade／clock／finished manifest／exact reference，V1 schema與降格拒絕不變；全pin含市場接受、原件／transport／manifest／receipt、單位與時鐘，完整stock ledger／狀態分母保留。source/reference decoder要求外部SHA；complete manifest以實際canonical檔bytes綁token，不用self-hash授來源資格。

靜態複核發現並修正發布後callback轉True／拋錯／非bool會追溯失敗的窗口：發布前取消仍拒收，發布後reference重驗pin／來源／root但不呼原取消callback。相對formal DATA_ROOT依expanduser／abspath正規化再檢查重疊。新增反例也確認已完成後第二市場原件變動仍拒收；partial／取消不發reference，原庫變動不借保存reader DB當來源。尚未增加可容忍原DB漂移的V2 raw archive路徑。

| Root組 | 真實結果與限制 | 外層收據SHA |
|---|---|---|
| Snapshot QA01 | compile5 PASS；99PASS／9FAIL／1SKIP／16.70s。8個既有V1 archive反例在Windows長隔離路徑開檔失敗；1個新clock反例先改copy binding，先命中binding guard。原FAIL保存，type／float未執行。 | `7c06f384eed356ea594275c6f4b024906e6fbda15d56dbacb38eef5971d7b1c8` |
| Snapshot QA02 | 私有create-only短路徑；原clock regex不改，反例只改cutoff並另驗binding mismatch。原9項精確9PASS／2.38s；983来源mypy及financial float守衛PASS。原99PASS／1權限SKIP按未變來源重用，不相加成完整Gate。 | `08dcc0cbff4d275dc61b135b9463e46d5b8ad34412d8e43e59c5cc038e65a405` |
| Snapshot fresh QA01 | 父24716→真新PID9700；固定外部binding hash與V2 reference hash→同全市場pin→保存ledger exact重開。15sourcefiles bytes／SHA／完整stat不變；原phase120秒，actual PID建立FILETIME／named Job／native membership與真退出先後已核。不是正常UI、官方來源或EXE。 | `c766177bd500db2b92fbff48aba4e27b8be2719bff530e820ed1ae8b80b2010c` |

新14個Root整合cases於QA01全部通過：實際SQLite copy與typed reader、外部SHA、V1 decoder拒V2、錯reader／原庫漂移、第二市場發布前／完成後變動、發布前取消、晚取消三種狀態及relative formal-root、跨thread取消／owner關閉。純codec與V1回歸分開判讀；fixture來源接受為合成，兩PIT資格仍false。

fresh fixture為 `C:/Users/archi/AppData/Local/Temp/bv2fresh1/fixture`；parent SHA `ec66d61c97532a962dab8d6857200540dddcc2152dd08a6755bd46bcfa326013`、fresh `abd5d221d3cad47e814da144f1e1f373ad1899c8389efb5772ad3e772f3a3052`。launcher29824／10484只作診斷，兩actual均以same named Job核對並在下一phase前確認不存在；Python socket guard零事件不等於OS網路審計。三組外Job三陣列空、process/Job handlesclosed／mutexreleased，無強制清理／超期；原窗口8GiB／12程序不變。

下一批沿原plan§9.5補monthly consumer V2／SourceReferenceV3及有界每日選版，三個既有Luna只靜態候選，Root串行QA與接正常UI。舊monthly ReferenceV2是archive V1，不能用它包新pin或更改舊schema。官方TWSE單位、MOPS財報完整文件、歷史缺件、原P01 strict p95、Forward／Paper自然成熟及完整P00–P14/G0–G4仍未接受；已耗GET不重試，正式資料／Task不變。最新來源重新綁定及閉鎖以task的具名readback為準，前版102只是前版來源數。

### 月營收 consumer V2／V3、每日選版及 future-pin 全缺值反例（同日接續）

三個原Luna重用靜態實作／複核，新增六個source/test檔；Root另補真selected-reader→provider→SQLite snapshot案例，未新增agent或讓worker執行Python。獨立複核指出future pin若全missing會避開逐列clock檢查；新snapshot clock／pre-copy、monthly fact／issuer／V3 reference與session一律要求共同available_hour<=cutoff，包含沒有observations的清冊。舊Selection leaf/provider對未到時資料回missing的原斷言保持，較高V2完成／reference不授未來版本。

月營收source kind固定daily cohort，完整codes、per-stock provider／fact雙identity ledger及兩套counts分別保留，缺基期仍unknown／blocked。V3 outer與nested upstream reference都需外部SHA且decoder只出Unverified；exact讀回才發完成token。Series只使用外部固定MOPS用途trust／雙市場roots，明示報告月及最多64個pins，按cutoff或完整exact batch選一次；壞／未來候選具名排除，不掃latest，不混TWSE接受。正常UI與每日外部配置路由尚未接線。

| Root組 | 原始結果與處理 | 外層收據SHA |
|---|---|---|
| Monthly/series QA01 | compile12 PASS；100PASS／7FAIL／10.05s。三個全missing／unavailable完成案碰到新V2 clock錯誤的非空逐列capture限制；另clock反例cutoff先早於cohort hour、兩個scope反例在raises之外建構；來源mutation原receipt守衛已拒收，但反例漏具體DailySourceSnapshotError。type／float／rebind未執行。 | `02cb94ddf3e20bb5e5163a79e654eef65ea5451f225ff6f5e265195ccb7f91f0` |
| QA02 focused | 原7項精確7PASS／1.51s。僅逐列capture可為空，DB pins／full market raw/receipt/acceptance/time與原source guards仍強制；clock反例改為batch可用後、materialization前，原regex不改；scope建構移入原raises，mutation增加具體receipt錯誤類型，原source／complete／closed assertions不變。986mypy報3typing errors，float／rebind未執行。 | `ee16d55fd172313157254f72c7c460b01ed40494b79ca610013c01140ba5abd9` |
| QA03 type/rebind | LiteralFalse型別標註及exact str/bytes分流窄修，runtime PIT／原值守衛不变；compile2、986mypy及financial float guard PASS。只由新PID51228重讀先前已保存parent與exact V2 reference，15sourcefiles／完整result ledger及fullpin同原parent，不重產製來源。 | `37b3cb342aa1cf480335ae65b6db3a645f1687360dc87befd0e1435f6ffa5d0b` |

重綁原件 `C:/Users/archi/AppData/Local/Temp/bv2fresh1/fixture/fresh-rebind01.json`，SHA `bfd451c3838506bd7e66f743df6913b1fba8f7ab3586679f7559f84581f038cb`；actual PID51228／creation FILETIME／named Job及native query handles已保存，outer503384收錄actual並自然歸零，三PID陣列空、process/Job handlesclosed／mutexreleased，沒有deadline expired或強制清理。原parent24716／fresh9700原件未改。每組原8GiB／12程序、各命令原期限保留。

三份QA01／02／03原stdout、stderr與receipt均保存；100PASS依不變分支重用，7项另精確重驗，沒有重跑或加總成單組完整產品Gate。純DTO與真实provider/copy各自測試，正式來源接受與historical/formal PIT仍false；外部hash是完整性錨，不等於資料來源已被正式接受。112個本task來源／52保存資產及其他owner文件以最新Root讀回重新綁定；shared active_task／handoff_log保持原件。

下一批沿原plan接正常V2 YoY投影／月營收UI與穩定每日配置，再驗保存／返回／新程序；P07/P12只收真成功或具名隔離，P13驗受影響部分，P14待同來源版Native／EXE。官方TWSE單位、MOPS完整財報文件、歷史缺件、P01原p95、Paper/Forward自然成熟及完整P00–P14/G0–G4仍待，不以本批工程PASS消除任何原FAIL。沒有正式資料、全量回補、正式Task、push／發布或交易。

### P03 YoY V2、每日穩定設定與正常 Main 新 PID（同日 increment13）

本批沿原計畫補 `SelectionMonthlyRevenueYoYFactV2`／EvidenceV2／projector、`DailyMarketMonthlyRevenueYoyIndexSessionV2`，原method與28位Decimal公式及呼叫端門檻不改。投影重驗exact FactV2、full pin、源結果SHA、原始時鐘與非時間來源／derived version／期間守衛；provider/source observed與projected unknown可以並存，各自保存完整ledger/count，缺值不減分母。finish逐筆取消poll，最後發行核完整source token／V3 external原件SHA／投影identity。

`daily_monthly_revenue_series_binding`固定external binding hash／完整trust，只讓每天bounded pointer選定raw-SHA catalog及1–64個exact pin。壞pin具名隔離，其餘逐項重驗；catalog／root／anchor錯誤與全不可用拒絕。正常bootstrap／composition／Main注入lazy factory：startup與begin不讀來源，自然invocation首次月營收使用按未取整frozen cutoff選版並clone provider，舊session固定；一般Exception留失敗狀態，下一次同session不退回未釘選legacy。歷史／重播與clock mismatch不選live series。新固定series pair與原固定cohort pair互斥。

| 組次 | 原結果、具體修正與限定接受 | outer receipt SHA256 |
|---|---|---|
| consumer QA01 | compile13PASS；152PASS／1FAIL／1SKIP，9.18s。新future-pin test將五項fixture解包成四項，尚未觸發guard；原FAIL保留。 | `fc89fea76642a7c1202f4433da3a53a61bcdd6a4944f14e345c4c8799bf8a838` |
| consumer QA02 | 解包修正並補blocked-revision、future-period、RuntimeError失敗隔離及finish中取消反例；只重受影響36PASS，4.06s。989-source mypy4錯誤為Counter literal key／缺Path匯入，原FAIL保留。 | `5282db080b3f85c1b9c0e0e27020d52eba72675de5f2d7bf5654b762b0431b19` |
| consumer QA03 | 只補typing／Path import；compile、989來源mypy、金融float守衛PASS。Main變更所需Workbench85PASS，2.52s；更新validator25PASS／0FAIL／4原protected skips。 | `58b7e7e4e583a7c65c477182a1b55b7d5f4e1e7340f7a3f0db86d51033aecbce` |
| Main fresh QA01 | 真正常Main/input已接，V2 snapshot的原HTML bytes守衛拒絕harvester的BOM，未發完整旅程PASS；保留失敗fixture。 | `d1b3640cce04e0ce2c3e51b36fc64cd0d9399e9e87337c3e3ef1c4e9222b1bc2` |
| BOM QA01 | V2新增exact一次BOM封裝驗證：原件bytes/stat/SHA保留、canonical SHA必須等於完整cohort市場raw SHA，前後pin／取消／CSV及版本仍核；V1保留原拒絕。compile2PASS；50PASS／1FAIL，7.74s。新V1測試誤用不存在的finished屬性，原拒絕已觸發。 | `738682c84c100bfb64cb702a15e73fd4b757d04213b7db3f98d0ab3545f04e7a` |
| BOM QA02 | 只改該API斷言為未產生finished manifest且public reference拒發；精確1PASS，0.55s。989mypy及金融守衛PASS；原50PASS重用。 | `54da50d9306bf4d8a7666b597b599ae32e946e94dcb19f970d05efb21e42ebf4` |
| Main fresh QA02 | 已到Index finish；private harness把session的validated_entries呼在Index，保存FAIL；修正另核snapshot id位於clock.snapshot_binding，產品不改。 | `7776d3b42e75325e912530f411eaf408d1f0062c01da3380832535ef78458a7c` |
| Main resume QA03 | 保存原24檔bytes/SHA/mtime proof後重用同fixture，不重產製來源；正常Main37740→fresh45128，兩phase actual Python離場後才接下一phase。30來源檔／full pin／V3參照／source與projected ledger/count／Decimal YoY精確相等，合作關閉無TaskWorker。 | `dfed1eca086f4b22e2b522a26c3dcea66e619d4dd5a0d2b3dff5243cdd3edf85` |

Normal Main parent receipt SHA `a379f04ab5c2c784fff5ffc1d4f49ff79b5c7f92eb52b44cd901ee2964f68621`，fresh SHA `ae9ed7382a6088e1bfc45d6f305fc3084ca27d5903245267250c3235b7d6319c`，exact V3原件SHA `fd3c4f313a2fb22ebdf0c117a08cc592b2dc70352709d76ba54f91804549d3a1`。保留24檔resume proof SHA `a28b2e1b12813411d10b1714ca3dc5b5d08d0c796c6cb4e8b7338f3c87827773`。actual PIDs和建立時間／named Job native membership明示，launcher33824／28612只作診斷，不把launcher退出當actual退出；query handlesclosed。每phase120秒、外層命令270秒的原期限保留。Private Main資料缺companies與industry/market tables，啟動沿原降級；只有推薦input/context與publicIndex被檢查，沒有宣稱完整RecommendationService執行／正常保存按鈕或Registry列表。

三個原Luna重用、總新建仍3／10，只有靜態新增葉片及複核；無worker Python、QA、網路或child。Root修正RuntimeError回落及finish取消延遲，第二輪精確案例驗證；BOM static複核未見來源旁路。八組Root actual Jobs均8GiB／12程序，members_after_parent_exit／remaining／final三陣列空，process/Job handlesclosed、mutexreleased，無forced cleanup／期限超時；每組前RAM預檢通過後才啟動。舊FAIL及symlink privilege SKIP不刪，未重新跑既已通過且來源無影響的整套案例。

本批合成來源／accepted-fixture trust只證工程路徑，Python socket hooks觀察0連線，OS網路audit未執行；正式來源一次性接受、正式daily publisher／Task、V2 raw archive忽略原庫漂移、歷史PIT、原F17月營收頁面V2 query/presenter/比較/recipe/bookmark、完整Recommendation／兩策略全期間、真N、Native／EXE及完整P00–P14／G0–G4均未接受。沒有新GET／全量回補／正式DATA_ROOT寫入／正式Task改動／push／發布／交易。下一步沿原計畫§9.5完成原頁面typed V2 route；當版治理／121 own來源／52保護資產／前組及新Job完整閉鎖證據，以task.latest_source_readback為準，不將局部PASS相加成完整Gate。

### P03 F17／月營收 V2 後端與雙錨新程序（同日 increment14）

HEAD仍為`5cedd65710db21d9d1863695dcfa4ee0edb872ec`，三個原Luna重用且只做靜態葉片；Root單Job8GiB／12程序串行執行，下一組先核三個PID陣列空、process／Job handles關閉與mutex釋放。沒有新GET、正式資料／Task寫入或Git發布。

獨立QueryV2與原F17 read session新增typed V2接點，綁同一exact F17／MA及daily IndexV2。完整258 declared母體（257納入＋1明示排除）先合併、核來源blocked／observed／unknown與投影observed／unknown兩套分母，再全域排序與分頁；row scope、股票、市場／處置硬篩選不能被OR救回。另綁外部V3 SHA、內容identity、full pin與monthly `cohort_hour_bound`；F17整體仍current_only／availability unknown／official time None／PIT false。同數量但不同清冊在execute逐列join才拒絕，此前可能讀第一批P01／MA；不會發錯結果，此次未加額外清冊preflight。

SourceV2先取得一份exact F17 cutoff／codes，才呼daily factory並clone provider。ReferenceV3 artifact沿明示隔離root建立reference／descriptor兩個create-only檔，核bytes／stat／same issued index／完整參照值；public getter每次重發同值參照，發布前後比較完整值與canonical bytes，不要求同Python address。SavedRecipeV2沿caller另外固定的descriptor/ref雙SHA重開；固定series trust讀者核原pin與全市場，不讀mutable pointer/catalog。正常UI仍待owner-thread工作階段、typed V2展示／比較／外層bookmark與Watchlist，沒有撤除執行緒守衛。

| 受控執行 | 實際結果與修正 | outer receipt SHA256 |
|---|---|---|
| exact-pin QA01／02 | 新函式插到既有try/except中間，compile FAIL未跑pytest；邊界修正後compile3 PASS，35PASS／2FAIL／1SKIP2.36s。兩案抓到keyword-only trust呼叫，改`trust=`。 | `8f20125312bf222b54183e67d389e4eb39040a046aeb0a3ae10db41d36d22057`；`22f7495ac2292ec3945068cc11eccf18b07b8f6c5aac32ba504ce6ae350b4b30` |
| contracts QA01／query diagnostic QA02 | compile17 PASS；pytest180s到期124且有3個FAIL標記，沒有完整結果。新測試超16批次與tuple字串索引修正後縮檔診斷，6PASS／1FAIL132.63s；零active groups專用拒絕被正規化遮住，改先核caller原政策，仍拒該請求。setup130.08s促成重用既存來源，沒有延長期限。 | `36156c89a920a6448f53556516f2b5afe0929fcda9be26aa7215795bc20ee0f1`；`70df130242c777be363346a7ed09caea6775d452ff36af4ec096778907236d96` |
| saved query QA03／04b | 私有adapter未用Windows長路徑helper，setup ERROR0.86s。改adapter後12PASS20.65s；重用原320檔來源與mtime／SHA、hash-identical測試mirror，不再producer。當批monthly全unknown，完整母體258。 | `411413c4eecc35887f3bd3b8062bddd93b1c8a47614a07710aac646326bc264b`；`cae0eea3b44b4e0c8daf772df0c33eebe8769d0d4ef067d0783e4d308e9c2b48` |
| source/artifact QA01／02 | 第一個public保存案FAIL17.90s；修保存器object identity後22PASS／1SKIP111.58s。覆蓋full-N、雙external anchor／recipe、factory cutoff／clone、wrong port／future pin、取消close、create-only碰撞、hardlink、mutated bytes、深度／duplicate JSON及兩exact-pin設定。symlink建立缺權限是SKIP。 | `797e3ebd5a1f8edf892737ab7b1ab54160602e93a205bf18d46e41191ec3d15c`；`d870795a091bfd4266e77e7c330a8792f990ef83bbd093ea0d86e415e81ec470` |
| native backend fresh QA01 | compile harness PASS；actual49312→4680，同named native Job、建立時間、前phase退出及query handles關閉已核，原120s每phase／270s driver。11份daily／原參照及320份F17來源bytes／SHA／stat不變，full pin／原雙external SHA／recipe及前五頁相等。 | `634fb2185e0e2cd6ebe8e5bd9a10d0831083cbcc519a1652e8155b074e11c73d` |
| typing/V1 QA01／02／03 | 992來源39errors→3Optional errors→PASS，金融float guard PASS；slots欄位／Path／object窄化與F17 None的具名拒絕補齊。原V1 11PASS／1FAIL38.40s，FAIL為私有adapter漏store/scope；原pending斷言保留。 | `c9a359d5568151dfbaec3246fb24825f83d4c79c98223a195b38fd526c5168c8`；`15dab89805231b3fd9834213ec3e366dd4111812c4b2e07231693de6761de696`；`beb4e57134b7c129d4e6b043347ec5a4ac4fdae51381482c8f1c74548a86f054` |
| mixed full-N QA01／mixed＋V1 QA02 | 1PASS／1FAIL23.40s：新函式插入位置令原scope-tamper斷言落到新函式，NameError；原斷言移回未刪。之後mixed4PASS53.34s、原V1 pending單案1PASS25.47s。原parser／雙市場快照給1000精確YoY22.006875，各分母1observed／257unknown，9999仍在unknown；AND/OR、硬排除、全域排序、complete artifact／factory及partial store拒收均驗。 | `30c4a2fa7f8aa82121ef9cf67fe7834101ff1dc2b5029deb221fc9c4ab88b86b`；`2eafc0bc6b95ead6b8574745b542efcf460387c5874f890068e7a752873315f9` |

新程序parent收據SHA`89ec11d7d201cbca919afcbeb452f262f482347d04aef3dda7a0a782b57e2494`、fresh收據SHA`45996e43b766286b470958dbf53b283746e7ca54db67a2914812fd221a5ab712`，位於`C:/Users/archi/AppData/Local/Temp/bv2rfx1/fixture/`。launcher10976／11500只列診斷，未當actual PID。Native當批用全unknown合成來源；非空Decimal／AND/OR另由mixed4驗證，正常UI旅程仍待。Python socket audit events觀察0，OS網路audit未執行。contracts QA01的inner child因期限回收，outer沒有forced descendant cleanup且完成閉鎖；不得稱所有本批case自然PASS。

型別／Optional守衛變更後，以同原parent收據／原11資產只做fresh-only重綁，實際PID48104，`fresh-rebind.json` SHA`95247e3b66d27b398eda755cd0551e5d0a197c18464eccaa89b923d572aa4377`；outer SHA`845f76d99daf1cb7be582796f19847bf4b95181860c314f6cf77b76f26079a32`。同full pin／原雙外部SHA／五頁／完整分母及原件保持，current candidate source重新綁定；沒有再producer或parent。該新PID屬本次新Job，沒有聲稱與前次parent同Job。本任務outer清冊只含前版75份＋本批15份：90收據，其中1份原低RAM preflight125未起child／Job，89份native Jobs已閉鎖；10/11舊wrapper與其他任務同wrapper的收據排除。準備時全目錄版本519項的`outer_job_inventory_increment16.json`未作本任務接受清冊；exact清冊為`outer_job_inventory_increment16b.json`，SHA`78eecfb898e3b39d3528cddef93ad676ea1bc64bb0ef529f242afecd4966c7eb`。本段計數在最後治理Job開始前，該Job自己的最終收據另由task綁定。

來源一次性接受、正式daily publisher／Task、原庫漂移的V2 raw archive、MOPS PDF完整鏈、TWSE exact單位、品質／歷史缺件、自然成熟、完整Recommendation／雙策略期間、真N、Native／EXE及完整P00–P14／G0–G4仍未接受。下一步沿原plan§9.5在原F17頁面接同owner-thread工作階段、V2 presenter／比較／保存recipe／外層bookmark／Watchlist，再驗正常UI返回與新程序；Scrapling不成為其他工作的前置。127 own／52保護資產、歷史與新收據及最後Job閉鎖由task.latest_source_readback／final_closed_job具名核對。


increment14治理首輪：document_control12 features／20 link sources、errors=[]與compile audit PASS；私有audit import path缺少repo root，ModuleNotFoundError後未寫新source inventory。outer SHA`9fe71dffdcd2aa6edfccabc380e360e07d693b21a957ede63f209dc392fbf219`完整閉鎖，原結果保留；只補private script import path後再核對。

### Increment 15：原月營收 UI／V2 收藏與單一 owner-thread（2026-10-14 UTC）

沿原 plan §9.5 推進，沒有另立總計畫。沿用三個 Luna Max，新增代理總數仍為3／10；僅静態 leaf 實作與複核，所有 Python／QA 由 Root 串行。新增 BookmarkV2、PresenterV2、RevenueSourceActorV2 及各自測試，Root 將每日 SourceV2 接回原研究頁、正常 Main 組裝、Watchlist decoder／保存／typed 重開。完整母體、Decimal、雙外部 SHA、full pin、来源／投影兩套分母及 outer current-only／unknown／PIT false 均保留。

Actor 在一個長駐 QThread 建立、使用及關閉來源；候選 open／投影／取消檢查成功後才替換，失敗或取消保留舊來源。分頁沿同 issued result，先完成 projection 才套用 UI；提交前取消不變更原頁與收藏，提交後的成功依原 token 套用。比較不移動來源目前頁。V2 收藏固定原 descriptor／reference SHA，fresh exact 讀回後可發行新的 operation reference／descriptor，再核 stable content、full pin、cutoff、codes 與 fact/result ledgers。不得要求新發行 SHA 等於舊 SHA，也不得跳過原外部 SHA 讀回。Lazy base provider 的 exact reader clone 同 port 守衛保留；Main 明示保護設定檔的 DATA_ROOT 與 OUTPUT_ROOT。Exact reader factory 前後可取消，內部讀取目前沒有 cancel callback，須返回後才回應取消。

| Root 組別／外層 SHA | 實際結果與處置 |
|---|---|
| ui_typing_qa01／a62bf271d1611e3812eed7d841bd53be9b222054c6994e0b7d76468f70b643b7 | 新10檔 compile、八 roots mypy995 PASS。 |
| ui_contracts_qa01／5f14d3de80a04fd4bec4e5c807a4dc1b4f929c8ae5bd9838c8f0a6d0f8a48260 | Actor5 PASS／0.59s；書籤7 PASS、2 FAIL／135.85s。Fixture使用2330但原F17是1000起，且forge helper hash多納入衍生source欄。原FAIL保留。 |
| ui_contracts_qa02／61845e12bce152c3d98d85eb2c97b851e8bf8b5f78668abbd5585daf655579fa | 改用原parser的1000 fixture、正確canonical body，書籤9 PASS／137.91s。Presenter2 PASS、1 FAIL／19.90s：原Decimal尾零被測試誤限定顯示scale；Decimal值仍22.006875。 |
| ui_contracts_qa03／a31703fc64c3177e4cc0fc918fb128f4d271393b9db36712755a5f1754a317f2 | 精確值及原scale顯示通過後，Presenter2 PASS、1 FAIL／19.27s：六欄顯示是已觀測／未知中文標籤，原測試誤期待英文。原結果保留。 |
| ui_contracts_qa04／68dc549b4c80402459be8f2a8fb8616eb6febc6fc695a3fad69932bacec29314 | 原UI每日真port／fixture旅程1 PASS／50.37s；唯一受影響Presenter1 PASS、2 deselected／18.33s。258母體、22.006875、跨頁比較、分頁取消、保存／Watchlist解碼、原pin重開、不重新選批次及native QThread退出均核驗。此非正常Main或不同PID。 |
| regression啟動收據／995ec232129d21e8b1a2fe1e6dfeebef55a22c47f59083493154da6700e952d0 | Root誤傳SHA佔位，spec hash guard在任何命令前拒絕；未執行回歸，保留收據，完整閉鎖後以核實SHA重啟。 |
| ui_regression_qa03／7fdac8eeb1cdcda0f9532fe90c27cad3c89d818518c23fc806a607fc2bfbc196 | compile、995mypy、金融精度守衛PASS；原V1 UI 6 PASS／42.11s、Workbench85 PASS／2.84s、validator25 PASS／0 FAIL／4 protected skips。只有指定隔離資料，沒有下載或正式合併。 |
| normal_main_fresh_qa02／d8cfccd03d3d1f5da880ea22bee648b88718bc54c8303bd7e0f9691bb0596eef | 正常Main已構造，但私有harness漏選明示F17資料夾，未啟動catalog／來源查詢；90秒settle後FAIL。原120秒phase未放寬、自然退出，原fixture與收據保留。 |

原320份固定F17原件繼續以bytes／SHA／mtime核對，不重跑原producer。全庫未調整CRLF的git diff --check會指出此前UpdateService行尾；本批四個tracked程式以Windows CRLF規則限定diff check為0，未碰未受影響檔案或抹除原輸出。每組Job仍8GiB／12程序、前組三PID陣列歸零、process／Job handles關閉與mutex釋放才啟動下一組。來源接受、正式publisher／Task、MOPS PDF完整鏈、TWSE版本單位、原庫漂移raw archive、歷史缺件／自然成熟、真N、完整Recommendation／雙策略期間、Native／EXE及完整Gate仍未接受。
Increment15 normal_main_fresh_qa03 原第二份FAIL：outer `8051f44840b3cb4b66112bc138f6e3509b07ef3a5a8623d38333016c4f44b89a`。已明示F17後，原件guard發現私有fixture把provider來源base複製成多一層monthly_revenue_mops_snapshots，raw_html缺件遭拒；没有放寬source guard或改unknown为PASS。

修正精確來源佈局後 normal_main_fresh_qa04 PASS，outer `c92456d0457a900dadef7788be4c6cc5d932df420a41631b6a9b8ea896e6f947`。正常Main父實際54412→fresh47584，venv launcher2900／5408只是診斷；原120秒phase、native建立時間／同named Job／query handles關閉，兩個actual phase terminal均在下一phase前核對。原頁面完整258母體、1000的精確YoY、保存1128／頁1、正常Main typed saver與Watchlist實際「個股分析」按鈕路由重開均通過；不發latest／一般stockAnalysis。父收據SHA `0611265f46b95a7bd8f0c8af38cd75e4531b3141c55edc2d9288ebf224b9b703`，fresh `02abd2d1c25019e07dd7408950fc769186a3fd0fbb3f49776142ec234a6368fd`，位於 `C:/Users/archi/AppData/Local/Temp/bv2ui15c/fixture/`。16份固定來源bytes／mtime／SHA與320份原F17資產不變；原bookmark JSON／外層雙SHA／full pin／content／頁面codes／1128一致。新reference／descriptor operation identity可變，沒有改寫原收藏。正常Main及全部Source actor／TaskWorker合作關閉，Python socket attempts為0，OS網路稽核未執行。Main合成資料缺companies／indices的fallback提示仍保留，不宣稱完整推薦或全市場能力；這仍是合成保存來源旅程，真來源、Native／EXE與完整Gate未接受。

本批新增三個worker leaf與一個Root UI旅程，共135 own／136 dirty；唯一outside-own為DOCUMENTATION_GRAPH_GUIDE.md，Root未寫。最後來源audit須重核52保護資產、全部原proof／歷史FAIL與本批具名閉鎖收據，並同步feature map／20相關文件。shared active_task／handoff_log仍不改owner內容，只在本地task記進度。
### Increment 16：V2 自含原件封存及來源漂移後 exact 讀回（2026-10-14 UTC）

沿原plan§9.5推進；同三個Luna Max静態葉片與窄複核，沒有新增agent／Python／network／子代理。Root新IO及Core／Selection reader／V2 facade接線，純DTO與issuer不授來源資格；既有V1與live-state exact不變，原FAIL保留。新增6份程式／測試，原copy contract未修改，當版141 own；其他owner DOCUMENTATION_GRAPH_GUIDE.md仍不碰，shared active_task／handoff_log仍唯讀。

| Root組別 | 實際結果／處置 | outer receipt SHA256 |
|---|---|---|
| context01／02／03 | NetworkX未在project venv、修既有純lib路徑；domain data無效，改工具列出的data_pipeline。前兩FAIL保留；第三PASS，L2限定正文、daily guide僅headings未驗。既有9/29 graph只是定位參考，沒有重建或當新V2證據。 | 9cba5fbb6609a07cecba2bf899a316d379e82b04b94bce52ee6e20ee6ba6b7ef；5529598d0f5e4afdbc63d571502540b46c89f81ffef6b26d1816752ea09b46cf；84a14991501a47acac53153e28723f930e2db2ca4370fabcffc9b7ba01b7790d |
| archive_qa01 | Root在最後worker freeze前起Job，source SHA守衛拒絕，未執行命令；待凍結後重綁。 | 6276c0f42f65d58c2fd183bcd66e66e8c130b0a82af7861d8c43bd474cf664fc |
| archive_qa02 | compile9 PASS；6PASS／1FAIL1.30s，測試regex fixed layout與實際固定layout不符，窄修文字且拒收斷言不變。 | 80da0c5b73ef182fba38293308120f40bd98180a092e508c9b19661ae5bf10c8 |
| typing_qa01 | 998sources／7errors：union窄化、同名loop、False literal及weakref callback型別。逐項修正，沒有ignore或V2 cast成V1。 | 0b086180a117e4274be34bee0b2664aaba770914fff5a999b13cb77893118e2a |
| integration誤填SHA | Root誤填PLACEHOLDER，spec hash守衛拒絕、沒有執行命令；保留封套，改用核實SHA。 | ab75a7f1ab9e41c6f864dc2a9c9a40ba839edad9b06026566ae92f98c99e4f63 |
| integration_qa01 | 原DB／HTML變動及原snapshot移開的實際replay PASS；錯外部SHA已拒收，但例外漏包SnapshotError，1PASS／1FAIL2.05s，補公開例外契約。 | 4825e793ca8c71c032feab3661814675233bbfb3fbd65f882704d116abd1a810 |
| archive_qa03 | 19PASS／1FAIL／1deselected2.41s；12codec、5binding及2拒收通過，tamper fixture被產品唯讀屬性擋在寫入準備，僅精確chmod私有檔案再篡改。未撤唯讀或篡改guard。 | 895c106211143e7e292f9c9252c1f744da57aee2d3aa8a3b493c29097a5441db |
| archive_qa04 | 9PASS／1FAIL／1protected SKIP／3deselected4.54s。raw／SQLite／manifest篡改、缺檔／多檔／hardlink、錯pin／future cutoff／codes通過；取消正確拋既有Cancelled，測試誤catch Error，改exact Cancelled。平台reparse建立無權限SKIP保留。 | 09d608887e5f9949e9dba77c76d87142e6faf16fe1a4a43f725793ac8a1b713f |
| archive_qa05 | 剩餘取消＋真V1 typed／JSON3PASS1.69s；既有P03 copy/WAL／生命周期／V2 snapshot／Selection64PASS6.66s；compile10、八roots mypy998與金融float守衛PASS。 | 2d8366e7c83d9aa7e5df74e2abe3b4ed0760ad6650b7ffcae711b066d8d52c50 |
| archive_native_qa01 | 父實際16548→fresh1924，同named Job及建立時間；兩actual phase自然terminal／query handles關閉後才啟動下一phase，原120秒每phase及270秒driver。 | d669627ca0a9fecd205f26ea78c0495ed9827cf46199e6b49c6ff876ae9d5b16 |

新三葉測試合計34PASS／1protected SKIP，按上表已通過案例分段重用，不把FAIL改判或盲全重跑。native私有來源在 C:/Users/archi/AppData/Local/Temp/bv2ar16a/fixture/：parent SHA593969ea48bb763fd01e7ced19a992e4f353efcfa78ed15c68e6c073bdf28821；fresh SHA6b2709e7e0bb6c931de8ec5c1105422e5871dcce63577c4a8e319f22a86b4a25。venv launcher35064／39624僅診斷，fullJob observed actual PID另核。父先保存自含snapshot＋HTML／CSV、完整daily pin，再精確修改私有DB／HTML、rename原snapshot到保留目錄；fresh沒有重產製、沒有原snapshot路徑，仍回相同Decimal／source content／fullpin／三股完整ordered ledger、counts與12封存／daily檔的bytes／SHA／mtime／inode。新operation身份不同，original logical reference不改写。只禁Python socket連線，未執行OS網路稽核；不是正常UI或standalone Native／EXE，也不是正式來源接受。

archive建立中取消／失敗可保留不完整目錄；沒有回傳reference或自動發布，讀者仍要求caller external SHA及完整樹驗證。daily市場root／trusted acceptance仍需存在，不宣稱可連同該root一起移走。原庫漂移底層缺口已解除，consumer／artifact／recipe／收藏的明示archive lane尚缺；下一批沿原plan9.5交叉綁原ReferenceV3與archiveReferenceV2外部SHA後接正常UI與新程序。同時P08雙策略完整期間、真N及固定Native／EXE仍推進，MOPS PDF、TWSE版本單位、品質／歷史缺件／自然成熟保持獨立阻塞。完整P00–P14/G0–G4未接受，沒有正式資料寫入、Task變更、push、發布或交易。

封存發布邊界另兩案PASS／1.72s：完整批次後改archive HTML，finish拒收並close／無finished manifest；不完整declared ledger同樣拒收。Opaque registry另錨定完整snapshot binding與兩session id；僅重驗兩新案、compile3與998mypy。當前候選以原parent SHA／12原件fresh-only重綁，actual42420，fresh-rebind16b.json SHA336571c8e219b91e980538b2b99aa25d18564859eed07b0c29d8d35fdb5d48b6，outer ac970e3eb80c40b2a466ce0edbf60a94be25b56e42e05446144bcd39399da402。該fresh屬新Job，未宣稱與原parent同Job；實際建立時間／membership及outer三清冊歸零／handles關閉／mutex釋放皆核。沒有重跑parent或產製。最後來源inventory及具名全收據由task封存，原FAIL與全Gate未接受維持。

### Increment 17：明示封存 consumer／artifact／recipe／Source backend（2026-10-14 UTC）

沿原計畫§9.5與同三位Luna Max靜態分工，新增七份程式／測試，Root整合Source2的獨立archive branch與Source3公開入口。Monthly2／Index2要求原Reference3和RawArchive2各自外部SHA、完整daily pin、cutoff、codes及provider-result／fact ledgers；原live exact無fallback。Artifact4自含原Descriptor3／Reference3／RawArchive2精確bytes，reader仍unverified。Recipe3保留origin BaseRecipe2、外部anchors與原F17 query，翻頁不把新Reference3替換原來源；Source3新operation重發Reference3，穩定身份與原recipe保持。完整daily roots／trusted acceptance仍必要，F17外層availability unknown、月營收cohort_hour_bound與兩PIT false保留。

| Root組別 | 實際結果及處置 | outer receipt SHA256 |
|---|---|---|
| consumer_context_qa01 | data_pipeline L2限定context通過；daily guide僅headings，未作全文或runtime結論。沿用9/29 graph只定位，未重建。 | 22b07573a8ffac302ae6cd4d4d5cefc2b5b89efd3f0e3a74284c6248943305ee |
| consumer_qa01 | compile4；1PASS／1FAIL2.98s。Index fixture誤把provider ready期待為observed，依不同分母修正；原FAIL保留。 | d0a5475d09c3a96e46a66c957aaaefc9efd923b11cf07f23cb43d2efab531011 |
| consumer_qa02 | compile10；consumer剩餘7PASS4.54s。Artifact4首案FAIL1.29s，producer將typed pin／tuple送strict JSON parser；改producer序列化，parser及crossbind未放寬。 | 4697b030448e4e5aee9c2ae28a29a0e4abff03d0ce8b0fced226d75b85796e1c |
| artifact_v4_qa01 | compile；八roots mypy1001 PASS；Artifact4 7PASS／1FAIL7.42s。最後取消案已正確拒收且無發布，測試變數誤寫descriptor而fixture為_descriptor，窄修兩處。 | 50dc8086f27a279a93719f8819d1743edf5138b42a7904f86da606e0c668b732 |
| recipe_source_qa01 | Artifact4唯一未過案1PASS1.26s；Recipe3 5PASS18.46s，使用原320F17固定fixture。Source3首案ERROR16.18s：fixture未建立既有契約要求的artifact root；原guard保持，補私有目錄。 | 5a46c9ddb92cc0f33b2b923ca841c16de21b77eeca119bc0a5023b9b5301a385 |
| source_v3_qa01 | compile；Source3 full258來源漂移重開1PASS33.93s／7deselected。原DB/raw修改、原snapshot與Artifact3 rename保留後，原錨點／fullpin／雙ledger與頁1保持，fresh Reference3 SHA不同。 | fa9f57fcc3a179e43827b9d060e90a7ca16f62d8c7ba36f5552cf4f354752162 |
| source_v3_remaining_qa01 | native helper compile；錯三外部SHA、raw tamper、owner／paging 5PASS88.21s；真create-only提交後取消兩案2PASS59.94s。Root移除提交後重poll，提交前最後取消檢查仍由真publisher執行；未改斷言或來源守衛。 | b32caef857d2af3385e72b40810d9d0878a1dfc7adde8f80e7b9663637f0aa2e |
| source_v3_native_qa01 | helper compile；actual父55252→fresh9188，原每phase120秒／driver270秒，同named Job與建立時間；兩actual terminal核驗後才下一phase。 | 9b5c822c03b1eecad1ca45079bf96ba974d9a1f7057d26cfb1c7056df037f578 |
| backend_regression_qa01 | 最新受改測試compile；原Monthly／Index31PASS5.92s、原Source2 exact recipe1PASS34.31s／8deselected，金融float守衛PASS。沒有重跑固定F17 producer。 | b74ed0314b3dfb56bce834eab3df7e8642b872753371d11dada5a35ad6a20dcc |

新測試合計29PASS（Monthly8、Artifact4 8、Recipe3 5、Source3 8），分段重用已通過案例；原FAIL／ERROR／timeout／protected SKIP全部保存。沒有UI修改，未把上一批Workbench85／validator25/0/4當本批重跑。新增lane尚未接正常UI、Bookmark3、actor或Main，也未授正式source資格。

Native backend fixture在 `C:/Users/archi/AppData/Local/Temp/bv3ar17a/fixture/`：parent SHA `75bc95b212af1730246fb11c017477766ee29b45845c871aa8f0db3b5356b259`；fresh SHA `97f1d81492a12f443d24d36f03a9984881b8b946c004f240f8152d6a5102b26e`。venv launcher52668／29732只診斷；actual55252／9188在outer observed集合核對，actual建立時間／membership、query handles關閉及natural terminal均核。原DB、HTML／CSV、原snapshot及原Artifact3路径漂移後，完整258（257納入＋9999排除）、頁1、Decimal22.006875、雙ledger、fullpin、origin Recipe3與穩定Source3 identity保持；14封存／V4pair／daily檔bytes／SHA／mtime／inode及原320F17固定資產未變。Python socket禁止連線；OS網路稽核未執行，未宣稱正常Main或EXE。

P08另完成限定靜態缺口備忘：capture complete只是producer loop終止，fixture期間缺requested session而仍complete；Registry2單run精確Decimal不等於官方完整日曆或同股雙策略可比期間，Paper雙帳本不代替回測。下一批先接原F17明示archive正常UI／收藏／新程序，P08獨立補expected sessions、兩策略pair reader及正常歷史保存旅程；真來源完整鏈、單位品質、正式publisher／Task精確授權、歷史PIT、自然成熟、真N及Native／EXE仍待。當版148 own／149 dirty及52保護資產須由最後source audit核實；shared active_task／handoff_log與outside-own DOCUMENTATION_GRAPH_GUIDE.md保持唯讀。完整P00–P14／G0–G4未接受。

### Increment 18：正常 F17 封存來源收藏與資料漂移後新程序重開（2026-10-14 UTC）

沿原計畫§9.5，以原三個 Luna Max 靜態實作／複核；總新建仍3／10，無子代理再產生代理，Python／QA全由Root串行。新增 Bookmark3／storage3 與其測試、Watchlist3與原UI archived旅程。Source3五個getter改具名型別；未降低issuer／DTO來源守衛。正常Main明示archived lane，原V1/V2 strict-live收藏與共用actor生命周期保留。四個外部SHA綁原Reference3、原Artifact3 descriptor、ArchiveReference2、Artifact4 descriptor；完整正式／provider／F17／daily binding／operation roots先檢核才建三個 sibling 保存目錄。Binding metadata roots不選版、不讀mutable pointer，封存原件不覆寫。

| Root 組別 | 實際結果與處置 | outer receipt SHA256 |
|---|---|---|
| context UI QA01 | L2限定6文件／1671字元，runtime及Gate未知；Root依影響保留high risk。沒有重建9/29舊graph或當目前code證據。 | c7de7dfc7d9b29fdbd0d5bc3b40f594540cca204268c7d6adf88e9bbed43e42c |
| typing/storage QA01 | 10檔compile PASS；mypy1003來源4個storage窄化errors，storage未執行。補Path/str的已核窄化及tuple型別，未加ignore。 | aba02a2b80442853041ed046555be8ff19a7ab08513bc4938d859e04a8e2619e |
| typing/storage QA02 | compile／mypy1003 PASS；storage12 PASS／1 protected-reparse SKIP／1 FAIL。失敗為fixture誤用pin SHA作binding bytes SHA，產品外部SHA守衛正確拒收。 | b7eae87f7b242e5137c99a7fcea007c81b3cc61e8c99a2466f15817054f56b98 |
| storage metadata QA01 | compile PASS；9 PASS／1 FAIL／14 deselected。相對路徑正確拒收，但原測試regex期待不同具名原因；只更正exact reason，保留拒收斷言。 | 8ae1278722eef277fac19b7924921b87572eb1201de2f69ae39c7d51b1aca12e |
| contracts QA01 | storage其餘6 PASS，分段合計27 PASS／1 protected SKIP；Bookmark3 9 PASS／87.38秒。Watchlist1 PASS／1 FAIL：人工雙stock欄fixture只改英文alias、原view使用中文欄，修sole canonical欄且wrong-stock assertion保留。 | 0d0e94b0a95c0b6b41636fbec6b69457d11a1ff1ef7cdf99ddefe823fd3d231c |
| UI journey QA01 | Watchlist3 5 PASS／50.75秒；UI1 FAIL／28.12秒。原view adapter讀Source3不存在的page_request，修為公開request；Source3 getters具名。 | 3e1f4cbe571c832b2d3098b99166df5d3e5025dfa5c2705baa502dbc78e1a93c |
| UI journey QA02 | compile／current mypy1003 PASS；UI1 FAIL／27.18秒，Root私有測試誤傳WatchlistService constructor，改用原config port。 | 7f00b3e7274a1343a335a155702177fc321c0ba223bfbb3f8a039da51d465b18 |
| UI journey QA03 | compile PASS；UI1 FAIL／27.20秒，Root測試未unwrap Unverified DTO.reference；只取metadata，未把DTO升級qualified。 | 1268ba230cca8e919279654615f2fecf51e9a50685af83a8cb04ef457d7cdc8c |
| UI journey QA04 | compile／UI1 PASS／44.49秒：原full258／1000 YoY22.006875、翻頁／比較籃保留／收藏、Watchlist保存、DB/raw更正且原snapshot/Artifact3移開後精確重開、origin recipe及原件核對、owner-thread關閉。 | f0a021b6f809e10ac779627072f8c94db96c16f635ea6d18c838d498623fbc88 |
| normal Main native/fresh QA01 | 實際父54640→fresh32420；原120秒每phase／270秒driver，native建立時間／membership／query handles及actualphase自然terminal已核，下一phase才起。 | a9fd1398409b0c14f8510c4ed6e7e0ba3f20a3417f24dbc859b8a5c7d2fc063d |
| affected regression QA01 | 原V2 UI1 PASS52.45秒、V1 UI6 PASS42.89秒、錯收藏路由2 PASS1.09秒；Workbench85 PASS2.84秒；validator25 PASS／0 FAIL／4 protected skips；金融float守衛PASS。 | 026bda254ade9a7570f69fc09e54cedb69da801da4bc6711a17863c66ce28dc4 |

上述個別PASS不是單一合併suite；歷史FAIL、耗盡的真來源GET及原producer300／60秒FAIL均保留。本批全重用已釘定320 F17 assets，不重產製；UI2及UI1鏡像與原測試逐位元相同，僅conftest重用同public exact reader。mypy1003 PASS涵蓋既有八roots命令，但現行mypy.ini對ui_qt.*既有ignore_errors=True，不能據此宣稱UI強型別；實際原頁、正常Main、Watchlist路由及新PID證據另列。

正常Main私有旅程位於 C:/Users/archi/AppData/Local/Temp/bv3ui18a/fixture/：parent.json SHA `960e1ea04c719afca56ef4a580d38cf191cc40ea58d9cf4aca2996841b089c7e`；fresh.json SHA `a126fed641ed15584a48a97de74a107b12445b2e381ca11ee779793c4abfb1f3`。venv launchers33080／49576僅診斷，actual54640／32420才是native Job成員。原頁query/save及正常Watchlist「個股分析」實際按鈕讀回1128／頁1；父關閉後精確改私有DB/raw、rename原snapshot及monthly-references.v3到保留目錄、改壞mutable series pointer，fresh不重新選latest，仍full258／current_only／outer availability unknown／PIT false、相同origin Recipe3／四錨點／page codes。26固定來源bytes／mtime／SHA及320 F17原資產不變；fresh可另發operation Reference3，不改原Book3 JSON。Main全部Source actor／TaskWorker合作關閉，Python socket attempts0，OS network audit未執行；合成資料缺companies/indices的fallback提示保留，不冒稱全市場或完整推薦。

每組Job8GiB／12程序，前組三PID陣列歸零、process／Job handles關閉及mutex釋放才起下一組；原phase/command期限未放寬。封存建立失敗／取消可留下已擁有的空目錄，不自動清除或發行artifact。正式daily source roots／外部trust仍必需；raw封存不讓caller任意移走daily固定來源。154 own scope及52保護原件、shared active_task/handoff_log唯讀、唯一outside-own DOCUMENTATION_GRAPH_GUIDE.md未碰；最後source audit與治理收據由本地task.latest_source_readback綁定。

下一步沿原計畫推P08官方expected sessions／日曆provenance、同股雙策略完整期間pair reader及正常歷史保存／重開；[Increment18窄定位](../../output/tasks/baldr-completion-policy-20261014-01a1390b/p08_full_period_implementation_static_increment18.md)只作實作定位，沒有產品QA或新總計畫。MOPS完整PDF鏈、TWSE exact單位／版本品質、來源用途一次性接受、正式publisher／Task、歷史缺件、真N、完整Recommendation／績效、Native／EXE及自然成熟仍獨立；完整P00–P14／G0–G4未接受，沒有正式資料寫入、push、發布或交易。

Increment18治理首輪：12features／37link sources，兩個新手冊連結錨點與實際標題slug不符而FAIL；compile/source audit未執行、未產生source_readback_increment18。outer849171abfee84128addbc0d4f64ee62f SHA`eca85debb65d8f926aea76a8d22f6852ef4fb01c8820768fb9335fc061726342`已完整閉鎖。只更正兩個連結的日期前多餘hyphen；不改產品／測試／來源守衛，後續只重治理及尚未執行的source audit。

Increment18治理第二輪：12features／37link sources errors=[]、compile audit PASS；Root私有audit錯把前一輪治理FAIL列入必須PASS清單，原FAIL保留守衛正確拒絕，source inventory未發行。outer43249a252dba41528659ce56964dac57 SHA`17e0457dd2d393f6eecb7c18fa839d056eaf2e7091f57aa39c9e6e5aa82622a3`完整閉鎖。僅將失敗治理收據放回歷史FAIL清單並明示assert failed；產品、原測試與來源核驗不改。

### Increment19交接：靜態候選，所有產品QA未執行

使用者要求commit後轉新對話。三模組／三測試與public portfolio reader增量均已保存；Root靜態補策略metadata/precision交叉綁定及initial capital差異，沒有從float重算PnL。compile／mypy／三組pytest未啟動，可用RAM低於8GiB；最後只有Context L2三文件／3768字元／6862bytes，outer8f8ed3d0cf0546319f9c6d64ffe14512 SHA`8e2a365c23db27e135360a216f2a737d14b42f1c3994ab2e6c739830e570883c`已閉鎖，不是產品QA。未啟動QA02 spec SHA`471bbfcea0c2bd304fe78f3d3e741059b03596b9e5ffb7a02ab071e658113f4f`及完整七來源SHA、下一批Root串行與Luna靜態分工見[最新交接](BALDR_COMPLETION_HANDOFF_20261014_INCREMENT19.md)。交接新增文件／Feature Map的Python治理亦未執行；checkpoint不是PASS、正式來源接受或完整Gate。

交接stage核對：161份精確own files，outside-own未stage，ignored收據／資料／singleton未stage；tracked diff check為0，stage後含新增檔的whitespace check回2（17 EOF空行＋1註解尾空白），保持原source bytes與歷史QA pins，未將此項標PASS。輸出保留本機handoff_staged_diff_check.log；checkpoint不代表release接受。

### Increment20接手核驗與資源等待

使用者於 America/Los_Angeles 2026-10-14 恢復原補完工作，新Root接手HEAD為 `789f82565ce4c95d1ee7fe8b585382b2d2e60811`。起始工作樹僅有其他owner的 `docs/00_core/DOCUMENTATION_GRAPH_GUIDE.md`；其SHA及兩份singleton均符合交接原件，不修改／stage／revert。舊task、所有原FAIL及output原件保留。

新owner目錄為 `output/tasks/baldr-completion-resume-20261014-01a13cf9/`，不替代原計畫或舊task。Root以唯讀PowerShell核七個候選來源、QA02的12個pins、52份保護資產與142份outer收據的bytes／SHA；141個native Job的三PID清冊均空、process／Job handles closed且mutex released，另1份為歷史低RAM未起child。核驗收據 `resume_custody_01.json` SHA256 `11b041e86458ca400c73e0ef0b8d75ea1d20cf6f6fc8a428d2bc1c2ed17e7d99`，僅證保存資產與閉鎖，不是產品QA。

另重核原320份F17資產，以及正常Main父54640／fresh32420的26份固定來源bytes／SHA／mtime；兩份原parent／fresh收據SHA亦符合交接值，未重跑producer。`f17_saved_assets_custody_01.json` SHA256 `10595cb1dbb094decefc0e67e0a24cdb03c20c3db9d2e2eb240b5e5f2db368fd`只證保存資產仍一致，不替代當版產品旅程。

已將原commands v5 runner的TASK、外層wrapper路徑、spec HEAD／隔離env／create-only result directory另存到新owner並重綁SHA；原QA02 spec保持原件。新 `p08_increment19_initial_qa01_spec.json` SHA256 `81bf03919e98ba8e0ff4fcee3b5d23a1b2db6607de042d0f003c6537e0a20909`，七檔compile30秒、八roots mypy180秒及三組pytest120／120／180秒原命令未改。啟動前再次檢查來源、HEAD、前組閉鎖、結果目錄不存在與至少8GiB可用RAM；全Job仍8GiB committed／12程序、kill-on-close及同workspace mutex。

本session無可重用代理，按使用者授權新建三名Luna Max，跨交接累計6／10、同時3名；禁止再生子代理及執行Python／QA／network。單寫範圍各限新owner目錄內的日曆、Registry與Backtest接線報告，產品／測試均唯讀；Root保留金融判斷、共用ports、整合、QA與文件。日曆raw／hash鏈可證內部一致性，caller宣告的capture mode／時間不構成官方來源、發布或PIT資格；固定false eligibility保留。Registry複核指出V1 pair遺失已知parent，以及public Reader新metadata SHA／budget參數缺直接反例，待原候選QA後才作最小修正與補測。

三路報告均已完成、無pending writes，可在本session繼續重用。Backtest定位確認既有Registry widget可提供真run ID的雙選取，通用2–5筆比較仍未接P08 typed pair consumer；單筆opener接線不算正常保存按鈕旅程。後續需由Root先定版取消傳遞及明示calendar path／外部SHA／market注入，再分派單寫UI葉片；不重造歷史清單、不讓UI猜來源或從float摘要造績效。

首次可用RAM為6,679,724,032bytes；重綁後preflight為6,066,806,784bytes，均低於8,589,934,592bytes。沒有啟動Python／Job／compile／mypy／pytest，`document_control init-task`與Context重建亦尚未執行，沒有把手工intake當作工具建立的task.json。這是資源等待，並非QA FAIL或PASS。新文件治理未執行；待資源達標先初始化自己的task／Context，再完成原候選QA、受影響Reader回歸與正常Backtest保存／重開／比較／返回。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4未接受。

接手期間另一owner提交 `9e2c51dbc88d6eead2a235a1e5c382d770c3bd2e`，包含Graphify指南與本輪部分接手文件；本Root沒有操作該提交或修改指南。原HEAD守衛正確拒絕啟動，沒有Python child。Root核對checkpoint至新HEAD僅四份文件差異、Python／mypy設定無差異，12pins仍符；角色卡的新未提交變更只增加連結與導覽，全部保留。原01版spec／manifest不覆寫，另存綁新HEAD的02版及 `head_transition_01.json`。02版preflight於UTC 2026-10-15T00:41:33可用5,930,401,792bytes，仍未起Python或Job；現行runner入口是新owner的 `invoke_owned_qa02.ps1`，先執行 `bootstrap_context_qa02_spec.json`，完成閉鎖後才接 `p08_increment19_initial_qa02_spec.json`。

### Increment20使用者重開程式前暫停

使用者明示暫停，Root已停止新QA及程序清理，Worker B中斷、A/C完成。自己的task已由受控document_control建立；Context L2三文件／3768字元，bootstrap outer13c85b14fb8a495ea6902576b2534ea4 SHA `6b0ae61b3f413c9445331dca46bf08b460e33638f4c4ca82ea5e410d3ed96f0c`完整閉鎖。原七檔compile PASS後mypy1006兩個變數重用型別錯誤，原FAIL保留；只改TPEx month_key與configured_text，兩檔compile／mypy1006 PASS，日曆12PASS、artifact17PASS／2protected skips。Pair沙箱第一案os.link WinError5原FAIL保留；正常Windows權限、新owner temp、原180秒suite另12PASS／6.41秒，outer4853dd3315b547598ea9248ce501dedb SHA `ec8197b77c817f6bcc92052d1f754c8bf2f9fa2cec1e0e1ef3d5ce90817e0c1a`三PID清冊空、handles closed、mutex released，沒有待輪詢QA。

其後Root已窄修pair的V1已知parent保留／非支援artifact拒絕，尚未compile／測試；Worker B的直接Reader反例編輯在使用者暫停時中斷，保存現有bytes，不能宣稱完整或通過。原Reader回歸、共用取消／selection SHA／calendar pin注入、正常保存／重開／比較／返回及fresh仍待。程序唯讀盤點為43個Python、約7.59GiB私有記憶體，均有存活IDE父系，沒有確認為孤兒，終止數0；沒有因CPU低終止服務。Root未stage／commit／push，其他owner文件及舊task保持。精確HEAD、pins、未驗項目與恢復順序見自己task同目錄 `pause_for_restart_01.json`；完整產品Gate未接受。
### Increment20恢復後Reader與正常Registry旅程

重開後使用者明示繼續，RAM恢復約21GiB，沒有終止其他程序。HEAD為其他owner文件提交後的 `dfae21c5fec0b384f4295afa84ce5d86a6f97a80`；Root未stage／commit／push。原暫停記錄與FAIL保留。原session三路不可重用，按既有上限再建兩名Luna Max，跨交接累計8／10；後續同session重用，worker只做白名單靜態編輯／複核、無Python／network／子代理。Root單寫ports、整合、金融裁決與文件。

V1 pair保留已知parent並拒不支援artifact。既有public reader新增雙metadata SHA選取固定與typed取消，逐child取消不attach部分結果；真正integrity error不被取消旗標掩蓋。明示日曆path／外部SHA／market／protected roots的immutable pin只作結構驗證，不自行hash當前檔案。原93日inclusive、4MiB raw及最多8responses限制、來源/PITfalse及Decimal capture皆保留。

Root沿原Backtest／Registry加入完整期間診斷controller與葉片，不另造回測或結果writer。兩筆metadata deepcopy，背景worker持有至native finished，套用前重核token／generation／選取／日曆pin與兩筆metadata。換選取、來源或新研究清舊結果，關閉合作取消並納入Main等待；返回保留選取。正常保存揭露既有JSON finalize用Decimal與持久化字串直接比較的缺口；僅JSON_FIELD_MAP沿同staging codec比對，CAS／hash／manifest／純量守衛不改，原值保留、改一分拒絕。

| 收據組 | 限定結果 | outer收據SHA-256 |
|---|---|---|
| reader original QA06 | precision Registry19、artifact19、R020 Reader14 PASS | e5c18b2fec60b4cf74217d2c58dd2dc985860441be7a0d768ada4bd1b94b01a3 |
| reader／pair QA07 | compile、mypy1006、Pair17 PASS | b78249e7f3f87150a9510529f9fe3e0c257c98c7cd10802cfa1768cca734701e |
| ports QA08 | compile5、mypy1007 PASS | 819cf27dc517f667553eeb1dcbd790f5b05b0b6d78a46e0cc3c4372d3bbc8ade |
| Reader QA09 | Pair33、R020 Reader15、read budget33、lineage7 PASS | 254915782746d319c3d149b77a29ea8ec28677afc00415e70af87d95fb779784 |
| UI QA10 | compile、mypy1008、新葉片5／原Registry12／R020 UI12 PASS | b677655762e2ef0b955034f7b4426e3a4c55d79bd2bdedc6c0b3883efaf77a2e |
| Main QA11 | FAIL：隔離800px螢幕不符新harness 1366px要求，保存未開始；後改回原模板640px，不授1366／Native資格 | e9c4b3dcdc022c4e8670cee2e53c0f41bb71594eaf49347b0fb218247bf1c18d |
| Main QA12 | FAIL：正常保存Decimal JSON finalize表示誤比；原收據／私有staging保留 | d4406890fb97798141cc628c12c79130faf224c4fbadfe9c326c320ffaeb511b |
| CAS QA13 | 原suite加12個精確值／改一分反例共42 PASS；原V2 writer19 PASS | d3819f12b89df48d91f817dcf2db48ed4d88a8976fc9c0a59de8a384672d5b5c |
| Main QA14 | FAIL：harness以JSON list對原tuple比較；產品與精確值不改，兩邊同JSON表示後再驗 | cc9fa1852e91476366fcd16d5d429353b17df915de2a32758696f00ee7d4a91d |
| controller QA15 | 8PASS／1FAIL：Root新增metadata反例試改frozen DTO；改由repository回傳新的immutable DTO，Main未執行 | 5ec1743b5c58069de12e305df04dfde3096d896e0bb4987889a831db4d3c3384 |
| controller／Main QA16 | 真TaskWorker9 PASS；父30060→fresh38780正常保存按鈕／對話框／Registry重開／pair／返回，9來源不變 | e94729c6afeb71ac6e7a9e89c17b254977d1f41ef199b104b6eb644df1fbe469 |

以上不是合併suite或產品Gate。每組均自然結束，三PID陣列空、process／Job handles關閉、mutex釋放，無forced cleanup；下一組才啟動。每組全Job8GiB committed／12程序及至少8GiB available RAM門檻，原case／phase期限保持。pytest需要正常Windows hardlink權限，沒有削弱create-only或保護根斷言。UI mypy仍有既有ignore_errors=True，不證UI強型別。

QA16使用新owner原QA15尚未啟動的固定Main script，私有root `C:/Users/archi/AppData/Local/Temp/baldr_p08_pair_main_01a13cf9_qa15/fixture/`；parent.json SHA `eca9b69f44f101fdb62e47adb8c6e067f522c6f59f733a9a5bfd44bdfa6b8ccd`，fresh.json SHA `a628ae642789f9dae98f819517526c87e026b7d15606b6ea737a0e0227d19907`。兩次保存真writer、完整DTO/capture、雙run與日曆SHA一致；超過2^53的原本金與小數原樣保留。父程序結束後才啟fresh，同一named Job核實actual PID，9份設定／SQLite／Parquet／附件／日曆bytes、SHA及mtime一致。Python socket attempts0、OS network audit未執行；原資料缺companies／indices的合成fallback訊息保留。這輪按鈕為真Qt操作但部分以click()觸發，另補可見Registry頁籤與座標命中的讀回，不重產已保存來源。

完整官方文件鏈、單位版本／來源用途接受、historical PIT、source／currency／cost authority、完整雙策略績效、真N、Native／EXE及自然成熟各自仍待；日曆候選flags false、metrics None，unknown診斷不是完整功能接受。正式資料／全量回補／publisher／Task權限、已耗TWSE GET／partial MOPS、停用maintainer均未改。下一步沿原§9.5完成受影響UI必要QA／文件治理與可見讀回，再推來源資格及完整期間缺件；不另立競爭總計畫。
Increment20 QA17：compile本輪所有改動Python、Workbench85 PASS、validator25 PASS／0 FAIL／4 protected skips、八roots mypy1008 PASS及金融float邊界守衛PASS。另重用QA16原9份保存來源，正常Main新PID29356以可見Registry頁籤、ensureWidgetVisible及原座標命中helper操作單筆重開、固定日曆、pair與返回；`fresh-visible.json` SHA `ca66e451896338a22720c7c218d0b496b43e84e9ea25523289cba1c38f5df5d0`。原9來源bytes／SHA／mtime及parent／fresh原收據均不變，未重產producer。outer793c97e63d90433ba92984c598edd66c SHA `c44d21980ed952c6be3ab70235f3947f0d54c4e8fb0673765a5380351e5aafa7`自然閉鎖；隔離offscreen 640px讀回不授Native／1366px／EXE。文件治理與最後source讀回另驗，不把上述局部結果當完整Gate。
Increment20文件治理QA18原FAIL保留：四份治理必要Coverage漏列。補逐份not_required理由，未改角色／政策／中央索引或產品門檻；QA19核12features／8link sources errors=[]，outera9be039a6f00455c8e7e7c41dae7691c SHA `2ea5e794611a5292dd842af6009d3d3161ebea1984b4620a0f52051a0c75cc0a`自然閉鎖。這是文件結構／紀錄檢查，不代表完整Gate。後續沿原§9.5定位calendar實際capture／版本／批次時間與source／currency／cost資格缺件；仍維持候選資格與正式授權邊界。
### Increment21日曆完整傳輸與每日批次

沿原§9.5推進，不另立總計畫。新owner已保留Increment20的26來源鏡像及Increment21取消修正前5來源鏡像；後者manifest SHA `48d138ad64aaba18a95535c936074ab75e7cde4a2a00e99aab61ea3a1c7fccc6`。同session重用第9名Luna作靜態測試／複核，累計9/10，不產生子代理。Root保留shared ports、金融判斷、QA與文件單寫。

新增 `data_module/official_calendar_transport_v1.py` 的JSON原件／URL／EOF／Content-Length／hash收據，明示4MiB、identity encoding、aware開始／body完成時間；原字節保留，不借HTTP標頭授官方timestamp。直接capture的10秒是socket／合作檢查，不是阻塞I/O硬中斷。`official_calendar_daily_snapshot_v1` 沿原兩市場解析器與93日限制，把raw內嵌capture→manifest→pending→receipt→create-only發布；外部雙SHA與獨立用途接受錨點固定讀回，改正另存。共用artifact bytes helper抽取未改原V1 schema與保護根／reparse／hardlink／大小守衛。

| 組別 | 實際結果與限制 | outer receipt SHA256 |
|---|---|---|
| QA20 | compile3 PASS；mypy HTTP status `Any\|None`型別FAIL，pytest未跑。Root加明確int檢查，bool拒絕保留 | 60bc106ee1559116952da02d7e5b57606fca452d4ac37c59c48a17929d06c73c |
| QA21 | compile／mypy1009／transport24 PASS；原artifact17 PASS／2 protected skips；原bundle6 PASS／3 sandbox TEMP守衛FAIL | 8b9ae7550221d99da6168686562f1d2861332706cd77fb3c7d9fcb6c64f282af |
| QA22 | 正常Windows只驗原bundle9 PASS，保留原TEMP與protected-root守衛 | fe5e6c45f894d41d4d514f80c8ebd9b6f995057e4e81d8c8c73a26ab4b462da4 |
| QA23 | 新batch module compile、八roots mypy1010 PASS；當時行為未驗 | 487a95b1c4cd4896e711f30308f2e51863795012b712b70ca6bfe8e556a953fc |
| QA24 | 新batch測試compile／19 PASS：兩市場缺漏／重複／意外分區、93／94日、外部pin、來源／receipt漂移、取消／pending／時間與更正原件 | 923512b0d0dcbc7a85fe425e485d3b1a9f175d22191e69a286ca3ef789364d13 |
| QA25 | 合成父6316→fresh13156：同named Job、前phase退出後才啟fresh，原版與更正版8檔bytes／SHA／stat不變，外部pins／精確cutoff拒絕正確，fresh未重產producer | 346803366cb08bef97ce282d12d2de4084413dea3009d27f425b1eb26cc0fbf8 |
| QA26 | 靜態複核找到pending讀回期間取消空窗；Root於解除barrier前補查，新增與既有取消反例2 PASS、compile及mypy1010 PASS | a07d432c557f3899758a060988727a58c3680d9487c1ba4037634358d005cc5b |

QA25 private root `C:/Users/archi/AppData/Local/Temp/baldr_calendar_daily_01a13cf9_qa25/fixture/`，parent SHA `f7e40ad702dc615a42a554d217b7793f5a866de190868cad320f0393263bdf7f`／fresh SHA `a2a8068cd08b6e9a4f497d7a1edca3463602b08d061a5ec382d19cd91a0714ab`。synthetic錨點與歷史注入時鐘只驗機制；兩market holidays可不同，沒有把一市場日曆複製另一市場。PIT／performance／formal clock flags保持false，available hour只指明示用途的前瞻批次時間。新daily batch尚未接正常UI／真來源接受／正式publisher或Task；原Increment20 V1日曆UI不自動改版。

各組收據都保留原FAIL，三PID陣列空、process／Job handles關閉及mutex釋放，無forced cleanup；全Job8GiB／12程序、啟動至少8GiB available及原case期限不變。檔案fsync與新程序讀回不證OS crash目錄metadata durability；合作取消與最後unlink不具原子承諾。mypy legacy UI ignore限制仍在。此處沒有新網路request；舊Swagger原件讀回可定位官方年曆schema，但未宣稱queryYear參數獲該schema背書。月營收／TWSE既有已耗GET及MOPS partial缺EOF均未重觸發。

下一步先核日曆具名attempt與官方文件鏈，再以有界scope取得與解析真原件；沿原producer建立source／currency／cost／calendar authority，長期分段及完整雙策略績效、Native／EXE／真N與自然成熟仍各自待。unknown卡、局部PASS與案例加總均不代表P00–P14或任何完整Gate。

Increment21 QA27另依create-only具名scope `calendar_official_attempt_scope_01.json`（SHA `c75752f9b711c9fe8b4005dd211e916d90e09af010b59659daa851cf702d6c63`）取得TWSE2026年曆／TPEx202610各一次。新owner複製原hard-lifecycle helper，只改owner root並增加選定原header arrays及EOF/hash後body觀測時鐘；原helper SHA `6509eb7543c5a475e9926dd68a071e40469642f12b656c31f6c826f08cfd990c`保留。10秒／4MiB／無redirect／無retry／identity及named Job worker守衛維持，不重設月營收、Swagger、t187ap05_L或MOPS舊額度。

| 真原件 | 實際傳輸與品質 | raw SHA256／單次receipt SHA256 |
|---|---|---|
| TWSE `holidaySchedule?queryYear=115` | 3774bytes，200 JSON，1.031秒、EOF／Content-Length3774一致，實際Date為115年度；helper不是證明任意歷史queryYear支援 | raw `7644c1a8af784c09f54670fd7413f536b13eb76c54d658058e8873d1aee32117`；receipt `06db8144b1c92cc4e28cd4ac11b06a8aabf54b7d15ad1887887b0b63f99590b3` |
| TPEx `mktCalendar?ym=202610&lang=zh-tw` | 8760bytes，200 JSON，1.265秒、無Content-Length但EOF完整，calendar.status=success／total24；原parser驗必要weekday與月份 | raw `1fe745d5bef0c67d174f7fe4a2e2835154cd3f065cc94f116dfd2bea26ad8e73`；receipt `80a5b4f5a9b4541d35d35e543961638b5039226cdfd7f9dc1b0bdc30ba2c7890` |

兩完整typed transport及10月candidate evidence已另存 `calendar_official_attempts_01/`；parser結果兩市各20 sessions，evidence body SHA `c043051f94afb03dbfdea3ffb2e08936a35977940ccef5840945fe40e68c5587`。TPEx資料含4筆holiday及必要交易weekday，沒有因省略一般週末而補造交易日。HTTP Date／Last-Modified保留但不升格官方版本timestamp。來源scope結果receipt SHA `efc6ff6f1deb23059175c3c3587ed5b0115deedf3ac908fded19d3a8e92708b5`；outer `single_owned_qa_3614140e595d45cda0b4d19fd5ed5371` SHA `36cd437fd21ef29fc2e8280e86ae319fc859985d0be814a1195244faa5153f9f`。兩worker各自reaped／handle關閉／named Job清冊無該PID後才下一request，整組自然閉鎖、三PID陣列空，無forced cleanup。

這是本scope真傳輸／parser候選接受，不授官方完整文件鏈／一次性來源用途接受、daily發布或UI。TWSE既有Swagger完整原件可佐schema；TPEx用途文件鏈及兩市場schema／版本維持性仍需獨立裁決。`source_use_accepted=false`、`daily_batch_published=false`、PIT／performance／formal clock=false；不能用自造acceptance來發布真daily成功版。下一步優先沿已有producer定位真source／currency／execution／cost固定點，不從現在設定或新日曆替舊run補造權威。

Increment21文件治理QA28原FAIL保留：日曆daily新變更觸及storage／資料手冊責任，漏列兩份必要coverage。Root同步兩正文與task，未改治理規則或產品門檻；outer0d47a04e38c145ffb31f0882b1592e95 SHA a765ef3fca77d863620f1f21405b6e47b16a19db2ecffd46119d36f7a4162776自然閉鎖，後續只重文件治理。

### Increment22原producer執行輸入捕獲（進行中）

QA29文件治理12features／11link sources errors=[]，outer53008ee0dce34c049aabc5f49107eacb SHA `d2981c82575ab084ec85caab625e88cbc5ed5d0bbe74d444cbe51dfafca7136b`自然閉鎖；Increment21 readback SHA `4b0465b0b9ef3821a7e404f2092ff8b2a20c361c5f93b5954241578ebe494b92`記33本任務來源、408保護資產（62＋346 F17）、28閉鎖Job與20真日曆候選檔。保護資產bytes／SHA／當時mtime ticks逐一不變；原26份歷史mtime仍以原具名收據為準。

Root沿原§9.5與Luna五檔唯讀定位確認，BacktestService history loader只有唯讀SQLite／CSV及DataFrame切片，沒有raw／manifest／來源clock或currency權威，不能從股票／市場／cents猜造。原next-open producer具備actual fee/slippage/tax輸入、normalized lot及BankTaiwan policy.metadata；先以獨立 `RecommendationPortfolioExecutionInputsV1` 捕獲submitted與effective差異，None與明示0分列、policy metadata深層凍結、input SHA只識別輸入。原DTO多一個transient可選欄，V1／V2 wire與既有費率／撮合／算法不改；未保存此新欄到Registry前不宣稱新程序可還原。

QA30 compile3／mypy1011限定PASS，outer97fcdbb299864c439f92758da25b83c3 SHA `25397e785622cf7ecaa17439bd56fab78b3a4475df291078fafe9a24c618b38c`；來源三檔鏡像manifest SHA `b5214c7715818735d008b6f8597313da3f7aefb8b36dddc481ded206d2fd60ec`保留。其後Root另補policy/effective lot crossbind，尚待行為與最新typing；第9名Luna只寫新測試，未啟動QA。input identity不是execution/cost implementation digest，source／currency／calendar／cost authority與完整績效均仍待；additive artifact／Registry接線為下一葉，不能往舊V2補值。

Increment22 QA31：Root凍結第9名Luna測試（SHA d47005842c5a90994c2b31084aca73ecab0e6b12c96ef3453ec86cef3d29759c）後，compile4／mypy1011 PASS；新execution inputs14、原precision capture9、原BankTaiwan consumer7、V2 codec19與V2 Registry19各自PASS，金融float邊界守衛PASS。policy lot/effective lot交叉守衛及None／0不同identity、policy metadata深拷貝、原producer值與V1 DTO wire不變均有限定反例。outer123516426e5942caab0744e2737c12ce SHA 70e70187025115ca8ccf7b22051b9a24519b53e67af5a2ef022a8a063376690c自然閉鎖，三PID清冊空、process／Job handles關閉與mutex釋放，無forced cleanup；每suite原120／180秒期限保留。這是同一producer的記憶體增量，不證新欄已保存、新程序讀回、成本implementation authority或完整績效。下一葉沿原Registry staging／CAS使用additive artifact schema保存，不改舊V2或往舊run補值。

Increment22後續已接additive `recommendation-portfolio-result.v3`：封套保留原V1／V2 canonical文件及execution inputs，綁策略、run／parent／Parquet hash及原cost／lot；同一Registry staging／CAS／reconcile保存與public reader還原。UI原保存入口只在producer有新capture時明示opt-in；未提供時原V1／V2不變，舊run不補值。同ID不同None／0輸入拒絕，新增schema不授來源、幣別或implementation資格。

| 組別 | 實際結果與限制 | outer receipt SHA256 |
|---|---|---|
| QA32 | 文件治理12features／11link sources errors=[]；37來源鏡像與408保護資產readback另存 | f4327ebaa37a99b0bdd01ebbb5bc5828015f9e4052f412aeac14ae7cc03b59ad |
| QA33 | compile5 PASS；mypy1012一項union assignment FAIL；原service封存後以明確型別分支窄修 | 7b4fb9a6e17a7c7a749693616dd377477f739e410780b38f5bb055ac5f6afe5b |
| QA34 | service compile／mypy1012、原V2 Registry19／finalize42／public reader15／pair33／readbudget33各自PASS | a7d2512cda54ee2207a3d69adea8043362f22cc0a8c91d1703a6c82726a88c49 |
| QA35 | 新codec測試縮排FAIL，pytest未跑；Root凍結前漏看，原測試鏡像保留，原assert移回原block | 8c3b4956f6402b3dfba13b0075ee71431b0997171aedb3ce1ee5b8266f1d39b1 |
| QA36 | compile4、V3 codec17／Registry10各自PASS；含原V1多股base、None／0、crossbind、三個crash點恢復與壞staging隔離 | 4e87926838ea1097c7b72b563b9457d2699396e8458f490b36cdd9a2d04becd9 |
| QA37 | Workbench85／validator25-0-4 protected skips／mypy1012／金融守衛／R020 UI12／Registry UI12各自PASS；legacy UI ignore不證強型別 | 995f9b192fa5f60a7e3cd3f59288c37377b6fef28f33895c53e233a92fe0462b |
| QA38 | spec已保存但未執行；靜態複核發現V3預設sidecar讀取未設16MiB上限，保留原spec並另起修正QA | 未執行，無收據 |
| QA39 | 新public reader預設超大sidecar反例FAIL，證明會嘗試open；原service鏡像SHA `df9396f1a675de396bc8d1f59991e0c65b788e8edd01225e71fe31d12468d363` | 6add92e2e46539c0802cf4d652b51115f5a8123d3acc78b9eede387340c12e89 |
| QA40 | V3沿原V2讀前上限後compile2／mypy1012、V3 Registry11／原V2 Registry19／readbudget33／public reader15各自PASS，原反例斷言保留 | e6f5010599c625872378d87c264c9ae8d0fbd1a2b7da22f5566a106d34c13f5a |
| QA41 | Main正常保存兩run後，切Registry時active-window斷言FAIL；fresh未啟動，保存來源保留，未降低可見命中斷言 | 194d9cb3869de66e5133ab6b5716fe1901f66703c103d251fed28c0fd139b1a9 |
| QA42 | 父24812→fresh28756重用QA41兩筆run及9來源，禁producer／calendar重產；正常Registry開啟V3、同輸入／capture、配對／返回與新程序PASS | 011c1b1ee80e0e136d54b8af94e0246f4cf7ed6b2fe404b682ed4e22b3503b6c |

QA32來源readback SHA `65afaa5c8292f30acb0784d6af4d8e8dec50dbc47b470dc3f1cfe534495abc48`保留當版37來源鏡像、408保護資產、20真日曆候選檔與31閉鎖Job；不冒充後續V3來源。QA33 service鏡像SHA `a7f54050ad6edbda8013d52fadbf9c3a9b2b8fa921def02c7ce66c00ab2ac98e`、QA35原測試鏡像SHA `b2d5c1ccf28e1d00df451796a704d23894784d938edaf1e407e3304f3cb9f314`各自保留。

QA42收據另存本owner `increment22_main_reuse_phases_qa42/`，不寫QA41原fixture收據；parent SHA `b14f47d2eb4d7e8f06e1070a43336c511cf2814dbe65de3eb967e3b8c6dd0c7c`／fresh SHA `123e8cabfb85a8d8f8ffec1fbbac3c886f9e0bc5c3a17d53edc2a7119592e17c`。原9來源先獨立bytes／SHA／mtime ticks封存，兩phase再核bytes／完整stat一致。離開原對話框後以正常activate／raise恢復Main焦點，原visible／hit-test／兩run／返回及120秒phase／270秒driver斷言不變；原保存階段仍屬QA41整組FAIL，QA42沒有宣稱重驗保存按鈕。正常public opener還原同execution inputs與precision capture；calendar coverage完整時仍blocked／metrics=None、來源／currency／cost unknown，未提升績效或PIT。全組8GiB／12程序、至少8GiB available、三PID陣列自然空、handles關閉／mutex釋放，無forced cleanup。

這解除本葉「原執行輸入保存／精確重開」的限定工程缺口；Native／EXE、真來源用途接受、歷史PIT、真N、完整雙策略績效及P00–P14／M1–M3完整Gate仍待，不加總案例接受。下一葉沿原§9.5把明示daily batch及獨立acceptance anchors接原Registry期間診斷，不掃latest、不從manifest自授接受。

Increment22 QA43文件治理12features／11link sources errors=[]，outer21f043bb65a24a14a1ca867211a03a8a SHA `ecaa4200ffc26c533cc4bd700b04e27d4fa5d03c8ec6c6a37c36c249663ccb14`自然閉鎖。當版40來源鏡像、417保護資產（原408＋QA41保存9來源）、20真日曆候選檔與41閉鎖Job另存readback02 SHA `41fe9302acb72a3ca97db7d55cef08d3386bfc9633b23b50b748443df198fa0c`；原37來源鏡像與全部保護bytes／SHA／mtime ticks不變，原歷史收據的mtime權威仍保留。

### Increment23每日日曆版本接原Registry診斷

沿原§9.5與既有第9名Luna，無新建代理。Root凍結 `p08_daily_pair_api_06.md` 後單寫shared pin／pair／widget／金融判斷／QA／文件；Luna只靜態修改原controller與新daily controller測試，交回pending writes=false後Root接手。兩原始交付鏡像SHA為controller `0e6b9883372ffdb1517cc70764c16ae48e3c8318b895a20113a06b64dfce77fd`、測試 `7dde1e6d01a961c60b991f254b1a108dce1a1542694b0673c080c069c9b8d5eb`。Root只另修畫面文案與重複show，不改worker測試斷言；之後Luna唯讀複核Root shared ports／pair未發現具體可重現缺口。

新增typed daily pin固定批次目錄、外部manifest／receipt SHA、市場／保護根、兩市場獨立接受tuple及aware cutoff；新增pair `.read_daily`，仍沿同一metadata pins、public reader與缺日診斷。前後各讀同一daily batch並比完整identity，不建立臨時artifact、不掃latest。原 `.read(...)` 簽名與artifact路由保留。原Registry控制增加明示來源模式與receipt SHA；owner只可注入typed獨立接受，預設None使daily阻擋，不能從capture／manifest自授信任。每次固定使用當下UTC aware cutoff，不提供時間改寫欄位。換錨點／模式／欄位、市場、選取、研究世代或關閉會合作取消並拒收舊結果。

| 組別 | 實際結果與限制 | outer receipt SHA256 |
|---|---|---|
| QA44 | Root backend compile3 PASS；新daily pair12 PASS／1 FAIL：Root測試誤把讀取可更新的atime放入不變inventory；原pair尚未執行，原FAIL保留 | 855d615a92c04fc6755ca9776ec01df3e685da2742276b54bf64fd9f3bff97d1 |
| QA45 | compile7；原FAIL的TWSE一案PASS；原pair33／controller9、新daily controller16、widget5、Workbench85／validator25-0-4 protected skips／mypy1012／金融守衛各自PASS | 68495300aca6284cec2a6bb5ec8d2995c0e484f86f05a746629ca67d14436555 |
| QA46 | Main父33268→fresh17672，同named Job且前phase真正退出後才啟fresh；重用QA41兩run、QA25原版／更正日曆8檔，共17來源，原件及版本／非clock診斷不變，正常開啟／比較／返回PASS | f1678398a053e72d6ea409204a7a9e3bd82309dba1e3b83d47a9613b4a045cf8 |

QA44原測試鏡像SHA `7c45de7086769a4fe4b586f241962407f36ede404d604333f8502de525f74253`保留；修正只改inventory核對dev／inode／nlink／bytes／mtime_ns／ctime_ns／SHA，沿原來源守衛，不以可變access time當寫入事實。原12 PASS不重跑，原FAIL一案及尚未跑的舊pair各自執行；沒有降低原斷言、原120／180秒suite、120秒phase或270秒driver期限。

QA46收據另存 `increment23_daily_main_reuse_phases_qa46/`；parent SHA `98715709a69866728f2ef56aaa638f14686a0dd3652aeb99d31826c3b86003c7`／fresh SHA `d05de600c1357b2973b60c46b870686bba890bacd5258f713bd2dad45f3c0713`。QA25原parent外部SHA `f7e40ad702dc615a42a554d217b7793f5a866de190868cad320f0393263bdf7f`及其8來源先獨立核對，QA41原9來源另核原custody；兩phase再核17檔bytes／完整stat相同。禁止producer／calendar writer重產、socket guard無attempt。兩次固定版本各自保留真實當下cutoff，只有這項request clock不同；manifest／receipt／capture／接受IDs、日期與全部其他診斷相同。結果顯示同批次及收據，仍blocked／metrics=None、PIT／performance／broker false，未重驗已保存按鈕或生產新資料。

本葉只有隔離QA由Root注入合成接受紀錄；正式Main尚未配置真來源用途接受，沒有新官方接受、真日常成功批次、自動配置、正式publisher／Task或新network request。舊artifact入口與所有原FAIL、來源／幣別／implementation成本缺件維持。各Job8GiB／12程序、啟動至少8GiB available，三PID陣列自然空、handles關閉／mutex釋放，無forced cleanup；legacy UI ignore仍不證強型別。下一步仍沿原計畫處理官方完整用途鏈與明示配置、長期分段、原producer來源／currency／execution／cost權威、完整雙策略績效、真N、Native／EXE與自然成熟，不把unknown卡或局部案例加總為完整功能或Gate。

Increment23文件治理QA47核12features／11link sources errors=[]，outer64323a6758154d419b58ab0ec5ebf06a SHA `f4a179643398c3640ce03c56424fe38e58ed7e0f48f9aa00902337731bde115c`自然閉鎖。當版42來源鏡像、429保護資產、20真日曆候選與45閉鎖Job readback SHA `8c672a58b86496214010735e5a1b1b5bd112d90bd47ceb647fb953ec69565954`；這是下述官方文件取得之前的版本，原件與歷史FAIL不改。

後續Root核官方用途鏈：web工具直接開啟TPEx年度公告、PDF與開休市索引各403，service頁internal_error，原lookup SHA `e2a72f5abecf4265aec939a1e067a6cba7d1bc3fef798fdb88efd051781eaf07`保存。相同官方[開休市頁](https://www.tpex.org.tw/zh-tw/announce/market/holiday.html)改用既有browser session後可正常顯示115年度完整表；DOM宣告action `bulletin/tradingDate`，實際載入同官方host `/www/zh-tw/bulletin/tradingDate` 與 `tables.js`。這說明web工具403不能外推全部取得工具皆不可用，也不證任何WAF可突破；未解登入、captcha或安全警告。DOM觀測屬rendered證據，不冒充原HTTP bytes。

| 具名新scope | 實際取得與限制 | outer receipt SHA256 |
|---|---|---|
| QA48 `calendar_official_frontend_scope_01.json` | 只GET已觀測官方tables.js一次，10秒／1MiB／無redirect或retry；2.562秒、200、168139bytes、EOF完整，raw SHA `085fd65b4e15e2af4f3adb3f256f0058d0176dd2d98ce53217ede16667a04a90`。只靜態閱讀另存script，未在Root執行下載內容 | d4b01b874d16086a21cce3c5b0430658836892093d50cf66cf7c435d555c9abb |
| QA49 `calendar_official_tradingdate_scope_01.json` | 官方前端已保存的format-Y與POST契約定位後，只POST新端點一次，`date=2026&id=`、10秒／1MiB；200、8792bytes、EOF完整、stat=ok，raw SHA `c5cea6bd3a10bc7cd3e577d9ad78e600ae7d64508a1bc9b09be32fb396d0dc41`，data.html包含115年度表與閉合table | 7ffd28b046f55909d65af164d6e71fb5690d3c5e397fdba2b49ed0ad9df14d29 |

QA48／49各自沿原hard-lifecycle helper，不複製新取得機制或改原GET scope；worker reaped、process handle關閉、同named Job清冊無該worker後才下一組，outer三PID陣列自然空、handles／mutex閉鎖。原日曆兩GET與月營收／TWSE舊GET額度維持已用完，MOPS partial／缺EOF原FAIL保留。新scope原件／收據各自create-only保存，候選用途未接受；這兩次取得不代表parser、新daily成功版、正常UI、自動配置、歷史PIT或Gate已通過。

新TPEx回應是 `{stat,data.html,endDate}` 年度HTML JSON，HTML UTF-8 SHA `b7c0ae6990f4e14aff19decf1932243a0d867f1abbad51d5ebc28eb7c05d7432`；現有 `mktCalendar?ym=202610` 是另一個按日boolean月曆格式，不能cast、共用原source/use錨點或借endDate／HTTP Date作官方發布時間。下一葉沿原calendar parser／typed transport擴具名來源分支與必要反例，先核年度表的市場別、跨列／多日期／股票最後交易日與僅結算差異，再建立明示用途接受及配置；不重抓已保存候選、不補造歷史PIT。

### Increment24TPEx年度原件的股票日曆解析

沿原§9.5重用同一Luna9，累計9/10；單寫新`data_module/tpex_trading_date_html_v1.py`，交付SHA `7426e57c8b74bbaf6140945f647aa1597843f2ab370214c3b55e3a966603ab81`且pending writes=false。Root保留原`official_calendar_bundle.py`金融分類、測試、QA、文件及ports單寫。API07與amendment01均保存在本owner task，不覆寫舊API或原件。Root最初以要求完整`</td>`的靜態擷取誤判端午節缺說明；原件實有「依規定放假1日。」且只省略cell結尾，依[HTML標準](https://html.spec.whatwg.org/multipage/tables.html#the-td-element)於合法下一cell或`</tr>`邊界保留原文，未放寬HTTP EOF／JSON／未閉合table或row。

結構解碼重用原transport嚴格JSON decoder；exact fields／年／baseline、raw及HTML雙SHA、兩表標題／表頭、跨列與最多256列有界。Root分類核日期／星期、已知節日與連續補假組、股票最後交易及明示僅結算日期，三類債券另列ignored；unknown、缺必要列／說明、重複異日節日及股票開休市衝突拒絕。Luna唯讀複核發現異日重複節日可多關一天，Root於首次QA前補分組／計數守衛與反例。透過TYPE_CHECKING及函式內decoder import保留原transport→bundle依賴，沒有新增網路或改V1 monthly wire。

QA51b使用新spec／invoker／manifest與`qa_isolation_increment24_51`，先前51未啟動草案因隔離根字串未換完整而另存保留。compile3、新年度41案各自PASS；6份受影響舊suite共116PASS／1平台連結SKIP，mypy1013來源與金融精度守衛PASS。來源81pins前後一致。實際2026股票2/11開市、2/12–13僅結算、2/23復市，10月20 sessions；端午節原說明、跨列與多日期保留，第93日允許／第94日拒絕。原件8792bytes逐byte複製成fixture並保存獨立provenance，非合成重編碼或來源接受。

outer `single_owned_qa_1460680fff3840b3b76aa43ff569a855/receipt.json` SHA `f46ae834fc36d6b0d10f021cffdb1751a1db17cd366a1f76f157224281eb6356`，三PID陣列自然空、process／Job handles關閉、mutex釋放、無forced cleanup；原8GiB／12程序、啟動至少8GiB available及30／180／60秒期限維持。這只解除年度原件解析工程缺口，不授來源用途、日常成功batch、正式Main配置、歷史PIT、完整雙策略績效或產品Gate。下一葉沿原transport／daily具名版本接線，不能將annual HTML冒充舊monthly boolean或共用舊錨點。

Increment24文件QA52核12features／11link sources、errors=[]，outer SHA `d2953a5bc655e1b56c459fb58c73a1569d0cd1ce7e7d880b5007cbd593a21e46`。48來源create-only鏡像、429保護資產、原20份日曆capture／18份新文件capture／6控制與50已閉鎖Job全量讀回，readback SHA `f3e88057af20d5d87b6ed8c85327bd3f3e22a5fc6ddbfc919c8b458407bac8c1`；所有前版鏡像與原失敗不改。

### Increment25具名年度POST完整原件transport

沿原§9.5重用Luna9，API08限單寫`data_module/tpex_annual_calendar_transport_v1.py`，交付SHA `80cecc030bebed9e6d257b5068c9538b69ca4509b6a364579d7edd0c79a638a2`、pending writes=false。新frozen slots DTO固定年度URL／POST／ASCII `date={year}&id=`，response保留raw bytes／SHA、HTTP完整性與aware時鐘，獨立schema與有界canonical base64／exact fields codec；沒有getter、monthly `to_response`或舊V1 fallback。

Root將原transport V1的HTTP status、4MiB、byte count／EOF、SHA、headers／encoding／Content-Length、時鐘因果與嚴格JSON校驗抽成同一body helper。原V1仍先驗原URL，再保存同樣UTC時鐘及headers；舊kind／key／wire不改。Luna只唯讀對照Increment24原source mirror，未發現守衛遺漏。新完整transport不授application schema、用途接受或daily成功；只可沿已保存原件進入API07 parser，不重POST已耗scope。

| 組別 | 實際結果 | outer SHA256 |
|---|---|---|
| QA53 | compile3 PASS、新39PASS；另1個超大base64參數案例於pytest setup／teardown發生2 ERROR，測試值被自動放入PYTEST_CURRENT_TEST而超Windows32767字元；舊回歸／mypy／float未執行，原FAIL保留 | ce1e0939b914d58bb10627d91b0b82c97d62859a550d893f288dd98a708157e2 |
| QA54 | 只改該參數的短ID，6MiB原值及拒絕斷言保持；compile測試、該案1PASS、尚未跑的舊transport／bundle／daily共53PASS，mypy1014來源與精度守衛PASS；39已通過案例未重跑 | a700bafffdc038be06b450fcd07ed0ed84fb75fe292b7bda2a4990e5bf822da9 |

兩組85來源pins前後相同；原ERROR測試鏡像SHA `10b9365de1822196d99dd531693cec554bf79e9d886da993502f581349817f56`、原stdout及全部收據保存。兩組均自然PID清冊空、process／Job handles關閉、mutex釋放且無forced cleanup；原8GiB／12程序／至少8GiB available與期限不改。UI未變，不重跑已保存的UI資格；legacy UI ignore仍不證強型別。下一葉將年度雙市場原件衍生為具名期間證據，再沿原daily生命周期接writer／reader及明示配置；來源用途、首次成功版／小時、歷史PIT、完整雙策略績效、Native／EXE與完整Gate仍各自未接受。

Increment25文件QA55核12features／11links、errors=[]，outer SHA `bcb05abd67cfce3ee45a225040b826d09be3ee46dc737b9294dbeffb52496944`。50來源鏡像、429保護資產、原日曆／官方文件capture與53閉鎖Job（含原FAIL）完整讀回，readback SHA `9f810412f07910a2cb6d21f11e142722c55552d4291a35bd42473543ca0340d5`；未改原始資產或其他owner變更。

### Increment26年度雙市場期間證據

API09與amendment01沿原§9.5凍結，重用Luna9單寫新`recommendation_portfolio_annual_calendar_evidence_v1.py`，初版SHA `8eeeff5e399ad91ec9f59fd7d68c96cee990ca15ff3a099c265245885dd2812e`、pending writes=false。Root單寫原bundle金融衍生／測試／QA／文件，未改daily或pair ports。新evidence為獨立年度wire，保留兩市場typed transport，exact-bool資格、canonical bytes比較、32MiB及逐年完整分區；ISO公開日期與原pair相容，captured_at只從完整body clocks衍生，讀取再核日期／hash／transport凍結後漂移。

Root新年度TWSE用途核四個exact欄、ROC年份／嚴格日期順序、weekday、已知名稱／連續假日／春節最後及復市與僅結算缺日；TPEx沿Increment24股票parser。原TWSE marker與TPEx monthly路由不變，不把annual HTML轉monthly。QA27 TWSE3774bytes逐byte複製fixture並保留原raw SHA `7644c1a8af784c09f54670fd7413f536b13eb76c54d658058e8873d1aee32117`及原收據；測試中transport clock為合成，並非真取得或成功批次時間，不授來源用途。

| 組別 | 實際結果 | outer SHA256 |
|---|---|---|
| QA56 | Root已在首次compile前修一處sorted generator括號，保留worker原鏡像；compile3、新23／舊bundle-evidence-daily-pair74各自PASS；mypy1015檔兩處object.body_completed_at FAIL，float未跑，原FAIL保留 | 4cb86bfcf00549ce9e2a09c3047c29a52281e27d4b19708b1b607239fef30088 |
| QA57 | 只將兩市場完成時鐘各取typed tuple再相加，不cast或ignore；compile1、受影響正常codec／篡改讀回2案、完整8roots mypy1015及未跑金融精度守衛PASS；未重跑已PASS的23／74整組 | 2426f575e30b2a9ded1e5078566d863668e04861807463e7b1ec042dbb5e1ec1 |

92pins各組前後一致，QA56型別FAIL版鏡像SHA `6e236037306cf1997cc3c74f9ebf2e092693b9ce1a102c78c5ee9485aaef43b6`保留。每組8GiB／12程序、至少8GiB available與30／180／60秒期限，三PID陣列自然空、handles閉鎖、mutex釋放、無forced cleanup。正向完整跨年雙年度來源尚未驗；跨年缺年、缺市場／重複分區、93／94日、年度schema／weekday及範圍外未知列、bool/int旗標／自述clock／日期／hash／JSON漂移已限定驗證。

本葉尚未將新年度wire接daily writer／reader、原Registry ports或真用途接受；沒有新GET／POST、正式資料／Task變更或Native／EXE接受。下一葉沿原daily create-only／fsync／pending／clock／publish／exact reread生命周期及原pair共用診斷接線，不複製publisher或以舊V1失敗fallback年度。完整雙策略績效、source／currency／execution／cost authority、歷史PIT、自然成熟及整體Gate各自維持未接受。

Luna後續靜態複核找到TWSE少掉補假一列仍可被當開市的品質缺口。Root核真QA27的2/28說明只有放假1日，沒有2/27文字，不能由剩餘描述猜補；QA58刪1150227但保留1150228，更新合成變體hash／長度後，原候選得到DID NOT RAISE。outer `4f9332eeaf4f4fd586eefb0b30b67905` SHA `b480c5f6641e5457d8c5d41807da5c338eea72f6d1d1a51495797f1fed0fc74c`，原FAIL／bundle鏡像不改。

API09 amendment02由Root裁決：只在新年度用途，兩份獨立原件的同名國定假日日期集合必須一致，差異報`annual_calendar_holiday_dates_disagree`，不補任何市場值。各市場股票最後交易／僅結算仍獨立，未來版本若官方確有同名假日差異則隔離另核用途。QA59 compile2、原反例／正常codec／合成股票結算差異3案各自PASS，後者確認2/11可以只在TPEx出現；mypy1015及金融守衛PASS，93pins前後一致。outer `12cce6ec9aba41c2bb7e2e152f0f70df` SHA `56ae444af620a51ebdd87652d0e1f4cf30199d3c1a36f5ddf72db275e397fd32`，兩組均自然閉鎖、無forced cleanup。Luna唯讀複核確認未借另一市場填值／未強制整份sessions相等，pending writes=false。

### Increment27年度日曆沿原daily與Registry接線

API10由Root凍結；Root單寫原daily核心、最小evidence唯讀Protocol、原pin／pair、整合測試與文件。重用Luna9只新增年度保存測試，原交付SHA `273c5f998239ad52fead2d1312060d3080c7585386b790d0a5e432d86c2e8e36`鏡像保留；Root僅將兩個public helper呼叫的ordered接受tuple轉原API要求的Mapping，classifier tuple及原斷言保持。Worker後續唯讀對照Increment26四個相關baseline，未發現具體可重現守衛缺口，pending writes=false；本補完累計9/10，不新建代理。

新年度三檔schema／parser與月別V1分開；原public簽名、scope、wire與生命週期順序保留。私有固定codec及泛型snapshot共享原create-only／fsync／pending／completion／receipt／publish guard／rename／pending讀回取消／unlink／exact讀回；不複製publisher。年度保存兩市場原transport codec dict，原件不重編碼，逐年分區完整、93含首尾。Pin原constructor不變，以兩個外部typed用途接受的整組scope／endpoint決定具名reader，混搭／wrong order拒絕，不以V1失敗fallback。Pair沿同一public run reader與前後版本／identity重驗；新真控制器案使用實際保存兩run與daily三檔，只注入明示合成接受與時鐘，未stub composition／public reader。

| 組別 | 實際結果 | outer SHA256 |
|---|---|---|
| QA61 | compile6 PASS、新20PASS；真Registry控制器原5秒QTest輪詢等native finished FAIL，後續舊回歸／mypy未跑。新測試與產品候選原鏡像保留 | e860e766c1d9baf58f96e75bdd1295ba66187e750900e62d5c96dfed8abcd211 |
| QA62 | 原FAIL單案加4秒faulthandler，仍在原5秒內FAIL；stack顯示背景位於原exact reader的path lstat，主執行緒QTest.qWait輪詢；不作接受 | 9dbc4e6c286967c7875038cfcecb67e88c7ec3818fec77dac4d0e483ae2944fa |
| QA63 | Root新test改真正Qt event loop，仍5000ms；讀最終widget結果而非完成後清空的controller transient。compile1、原案1PASS／1.93秒；舊80PASS，另16案因同次選原controller又以plugin載入而fixture缺失ERROR；後續未跑 | 5110fbb79baa65782c77097ad7f14afbd13697703e02cc1c1dbfddfca66a64da |
| QA64 | Root嘗試預載-p，但tests路徑尚未建立而ImportError；未跑案例，原啟動命令與錯誤保存 | 5f7d518add606ed854ae5d147bd223918ae79336bd71a0056bb5f43fcc4e5a01 |
| QA65 | 完全沿原QA45已通過的daily-controller獨立命令，16PASS；Workbench85／validator25-0-4、8roots mypy1015與金融精度守衛各自PASS。沒有改原測試、產品守衛或期限；已PASS的20／80案不重跑 | bead936d306b99cea5649ad3ea31a321d9cc36efc9351771a6a6fff97365c27e |

每組110pins前後一致、8GiB committed／12程序、至少8GiB available及原30／180／60秒期限保持；三PID陣列自然空、process／Job handles關閉、mutex釋放，均無forced cleanup。QA61啟動available約21.08GiB。既有`ui_qt.* ignore_errors=True`仍不證UI強型別。各新案例涵蓋年度三檔／原raw、scope／schema隔離、兩市場／缺重複分區、93日、未來cutoff、exact hour、取消與pending、篡改／錯外部SHA、更正另存及pair讀後漂移／無monthly fallback。

這只完成年度工程接線的限定驗證，沒有新network、真來源用途接受、正式Main配置或年度Main／fresh證據；真收據`ended_at`只可作controller完成觀測上界，不偽稱socket EOF精確時間。下一葉先核原收據與全sidecars的來源custody／保守時間basis，再沿原pipeline推進一次性用途接受、明示配置與正常新程序。完整跨年成功原件、長期分段、來源／幣別／execution／cost authority、歷史PIT、真N、完整雙策略績效、Native／EXE、自然成熟與完整Gate各自未接受；不重觸已耗抓取scope、正式資料或停用maintainer。

Increment27文件QA66為12features／11link sources、errors=[]，outer SHA `4be645d2549f0e09a45b6629ffc6471bffb7bc29342077ae55ed1e4cfe9389f3`。56來源鏡像、429保護資產、20原日曆capture／18新官方capture／6控制及64閉鎖Job均讀回不變，readback SHA `8b6cc64b33a4548cfa3b052703f838b3277b0da6e0eb3122767c37a9ad6fdb99`。

### Increment28真取得原件的保守完成觀測與custody

沿原§9.5重用QA27 TWSE3774bytes與QA49 TPEx年度8792bytes原件，不新GET／POST。Root從Increment27已釘選readback取13份原receipt、request／headers／worker job／worker result、raw及原TWSE transport的外部SHA，另存`calendar_annual_observation_source_pins_01.json`，SHA `eee155ba38986fc9c643969665918c1ee1091a2573da370805e71328864d2b64`。沒有修改或補寫原收據、重置attempt額度、重新執行取得helper或公開資料發布。

重用Luna9唯讀複核原JSON，指出receipt雖記worker result路徑卻沒有其SHA。Root另讀原取得程式，確認worker觀測在EOF、raw flush／fsync／關閉及hash後，但不能把稍後釘選改稱當時receipt已綁定。新typed transports採原receipt的controller `ended_at`完成觀測上界，`started_at`明示controller attempt-start；custody分開保存兩原文、worker原文與SHA佐證、basis，沒有官方發布timestamp。TWSE原transport不動，新保守版僅完成觀測欄位不同；原bytes、headers、URL、method及payload仍按原codec核對。

| 組別 | 實際結果 | outer SHA256 |
|---|---|---|
| QA67 | 新Root harness compile PASS；讀原worker_job時誤取不存在的aggregate membership key而KeyError，未建立候選輸出，原harness鏡像SHA `575b10baafe4374643b5d65cbf6af427d41220e52eda975402749f97f6727de4`保存 | 579b9ddf224aa8c2c88de1f7a4287aba633db80fd209b2c4dcb3721cf87af346 |
| QA68 | 改逐項核原schema的query成功／membership／PID清冊／job name hash／handle閉鎖，保留原10秒取得與4MiB／1MiB上限；compile與build20552→fresh32736獨立程序各自PASS，原13來源bytes／SHA／stat不變；每phase重算相同16個記憶體反例，不把兩phase加總案例 | 0ee209202027d97bcaca669f70016b7bf10ff749065d474a8c0f0e0c52061b28 |

年度evidence SHA `005f8df9c0a4df2c5e0c8436baddb25e5f5b64bbcde6304cffa4a318069029d4`，custody SHA `130388c38e5a1f360355fde9b49a79d54537dc796114532e7570630a191ff75c`；10月兩市場各20 sessions，candidate=true／三資格false。Fresh依原外部source pins重算後逐byte核相同新檔，沒有從自填hash建立信任，也未重跑producer。反例涵蓋method、EOF、raw SHA、未來worker時計、未reap、bool status、錯payload及重複header；只改記憶體副本。

兩組123pins前後相同，原8GiB／12程序、至少8GiB available及30／60秒Root命令期限不變，三PID陣列自然空、handles關閉、mutex釋放、無forced cleanup。此葉只有owner output的來源custody與codec／evidence讀回，沒有繞過public artifact保護根、建立daily成功版、真用途接受或年度Main／fresh；原Main正常保存／新程序證據仍屬Increment22／23的合成範圍。下一葉核官方用途鏈與受限一次性接受、明示配置及原Main接點；所有歷史PIT、完整績效、Native／EXE、自然成熟及完整Gate界線保持。

Increment28文件QA69為12features／11link sources、errors=[]，outer SHA `bb056a157d908c0b2981253b7c96a0535dea9c14aaf536f87000dd564643d980`；56來源、429保護資產、67閉鎖Jobs及6份新增custody檔的readback SHA `e5a65b5eecb5f0ba33d0e203b9898334bcbceca7ab84e28f1abe64d579766106`。舊原件／收據／鏡像不改。

### Increment29明示接受binding接正常Main

Root凍結API12並單寫binding／共用接受codec／有界檔案reader／application bootstrap／Main／QA／文件；重用Luna9只改BacktestView、result_panel、原Registry controller及新UI測試，初版四檔鏡像保存，pending writes=false。沒有新建代理，累計9/10。

新`portfolio-calendar-acceptance-binding.v1`只序列化caller明示的ordered兩市場用途接受，canonical UTF-8上限64KiB；外部SHA先於解碼，原單link／reparse／handle／stat前後／protected roots守衛共用。原calendar reader新增optional小上限，預設64MiB與既有呼叫不變；原接受decoder被public classmethod重用並核canonical內容，沒有複製來源接受邏輯。Bootstrap只在明示成對設定中選path／hash，resolve／apply不讀接受或batch；Main才讀設定並將tuple或短錯誤沿原result_panel setter注入，畫面仍指定exact批次與雙SHA，不新增自授欄位或掃latest。

Luna唯讀未找到具體SHA／canonical／路徑／family繞過，另指出caller可改`ApplicationSettings.environment`原dict。Root局部處理：Main入口`dataclass_replace`持有自己的副本，不全域改舊settings契約；正常Main／fresh另改caller原dict，確認本視窗binding仍固定。共用檔案guard讀os.environ只增加保護根，未據此換binding。所有真來源用途接受仍為獨立裁決；本葉配置與時鐘都是明示合成fixture，不能當真接受或實際每日成功時間。

| 組別 | 實際結果 | outer SHA256 |
|---|---|---|
| QA70 | compile13、新binding／settings30PASS／1平台symlink SKIP；UI注入8PASS；舊snapshot／artifact／daily／bootstrap等145PASS／1平台連結SKIP；舊controller9／daily controller16、Workbench85／validator25-0-4、8roots mypy1016與金融精度守衛各自PASS | 6b24f945b69c65bc4fdc63d1cd931818636c47c87f06d34bb02d88468e1ad9cf |
| QA71 | 只建一次年度Main合成fixture，原annual writer保存3檔與獨立acceptance binding共4來源；不產生run。外部fixture parent SHA `0eabd3eea45772150642922cbcff4e05f5666b42283fca76cd31ec25b0bfb834`另存owner鏡像 | 2589a96c1faa16f76ad33859111c99ebeb50b82c529ae3af364b75f3200721eb |
| QA72 | 沿QA46 harness、原QA41兩個V3 run及原9保存來源，加入4年度合成來源；正常Main2440→fresh36248由外部binding載入接受，沒有呼controller setter作QA注入。重開／比較／返回、版本／非clock診斷與13來源bytes／SHA／stat相同，actual cutoff各自保留；Main局部副本驗證、Workbench85／validator25-0-4／mypy1016 PASS | be87efaceb684eeb7810bc0430fcf51754d8bb1ecd1f66d82fe3b17e4af3d7cb |
| QA73 | 正常Main34496以明示錯外部SHA啟動；其他工作區仍建立，日曆接受缺席且具名錯誤跨模式保持，不能固定daily pin或比較；同13來源不變，合作關閉無worker／無network | 03462c3d0c5c5dd998e4f631719c67f4c6b722c59c2c5ed9a7c5143630e218d8 |

QA72沿原offscreen Main的120秒phase／270秒driver／15秒UI期限；actual phase退出後才啟fresh，同named Job，原8GiB／12程序與至少8GiB available不變。各組三PID陣列自然空、process／Job handles關閉、mutex釋放，無forced cleanup。QA70為135pins，QA72為137、QA73為138，前後均一致；新runner v2只增加兩個可清除的calendar配置env鍵，原runner／三控制SHA、spec及收據保留。`ui_qt.* ignore_errors=True`仍不證UI強型別。

這解除正常Main明示接受配置與年度合成新程序的工程缺口，不代表已接受真官方用途或將本機正式Main配置到候選。沒有新抓取、正式資料／Task／排程寫入、重產既有run或發布。下一葉依原§9.5核官方完整用途鏈與受限一次性接受，再沿真原件版本→解析品質→實際成功保存→public reader→正常UI→新程序。歷史PIT、完整跨年與長期分段、source／currency／execution／cost authority、真N、完整雙策略績效、Native／EXE及自然成熟仍各自未接受，完整Gate維持未完成。

## Increment30：年度日曆用途複核與具名缺件

Root重讀舊task的完整Swagger原件，309960bytes／SHA `06e1cea82448361e733a0ad1ae16e52f5d5d6b71905acd078472f852c32c0eb0`，未重新下載。GET日曆path／四欄位及官方授權鏈已對上[政府資料集11761](https://data.gov.tw/dataset/11761)、[TWSE條款](https://www.twse.com.tw/zh/page/terms/use.html)與[政府資料開放條款](https://data.gov.tw/license)。保留Swagger response寫object、實際原件array的差異；`queryYear`未文件化、內部schema不是官方版本、metadata更新時間不是內容timestamp，未授任意歷史年度查詢或PIT。

Root發行單一TWSE年度股票日曆前瞻每日研究用途接受，原parser／schema／`trading_session_date`及`daily-hour.v1`不變；日常仍須完整validator與實際首次保存／完成時鐘，不每日重做人工用途審批。接受只存owner task `calendar_twse_annual_use_acceptance_01.json`，SHA `7f120b20e261d6173f2536ab206ddb4576b258954fc7839259ceb5adf84bf697`。這是Root的工程來源用途裁決，沒有對外簽約、購買、第三方聯絡或寫入正式配置。

TPEx中文[使用條款](https://www.tpex.org.tw/zh-tw/gtsm_disclaimer.html?l=zh-tw)已由瀏覽器DOM／AX實際讀到，第5節限制未經同意方式的自動下載，第7節例外限其授權政府開放平臺提供的資料。web工具同頁403、較早猜測terms路徑internal error分別保留；瀏覽器觀測沒有假報為完整HTTP原件。年度POST已有頁面動作與QA49原件，仍未找到覆蓋指定資料／取得方式的開放授權或同意證據；搜尋未找到不證不存在。其他TPEx開放資料集或「供研究參考」文字不能代授權。

因此不發TPEx接受或雙市場binding，不重抓年度POST、不發布雙市日批；此項歸D官方用途／文件缺件。觀測紀錄 `calendar_source_use_observation_03.json` SHA `17089e7327497f713a2b8fb15b3406c12223f3e33d4f77d53a1100a70d75dc6f`；[完整複核](../../output/tasks/baldr-completion-resume-20261014-01a13cf9/calendar_source_use_review_increment30.md)綁原Swagger、QA27／49原件與收據，舊scope額度不重置。Luna9重用唯讀核候選證據缺件，pending writes=false，累計9/10。

本輪無產品Python修改。QA75已通過新單市場接受canonical codec／原annual scope／review外部SHA與時間政策核對；只有TWSE接受時，原雙市場mode依原原因碼拒絕。文件治理12features／15link sources／errors=[]，只支持結構與紀錄檢查。outer `ce02714f845549a59069667e4b92a94a`／SHA `cc70dbc6a23c63a3d0dc5856cad1e66afd3f3a0f739ba0c09a968d9c93221398`，149pins前後一致，三PID陣列自然空、process／Job handles關閉、mutex釋放，無forced cleanup。接續原雙策略source／currency／execution／cost authority的可做工程葉片，金融及來源裁決保留Root；完整P00–P14／G0–G4、真N、Native／EXE及自然成熟仍未完成。

## Increment31：固定來源候選EXE與Registry同版旅程

Root將已限定驗證的本任務67檔保存為本機checkpoint `675bea262f8d25a1d5a8ade2762b7285fd11451b`，父HEAD `dfae21c5fec0b384f4295afa84ce5d86a6f97a80`。stage初次誤用autocrlf=false造成CRLF整檔差異，檢查中止；只重建本任務index、沿原autocrlf=true重stage後通過diff check，工作檔未重寫。另一owner封存文件未stage、未改；沒有push。checkpoint不接受完整Gate。

沿既有`packaging/build_windows.py --commit`／`baldr.spec`／依賴鎖建唯一候選`dist/candidate_675bea262f8d_07965800/baldr`，沒有安裝／下載依賴或另造打包系統。固定archive SHA `23e35b1788e559a4f067580bd865dc535887f5789c24c8330346f86783c05006`，EXE 55968248bytes／SHA `b05f96456f36dc44036ca0688399b0cb5a85262f4a073c74a879f5ea6c970e26`。沿原version規則顯示`2026.10.06+675bea262f8d`；metadata channel不是產品或交付接受。working lock與Git archive的換行bytes不同，各自SHA固定，內容版本全量比對通過；build metadata綁archive lock SHA `b1a3bb4bd03246c025f09bca3658104aff6c676983c878f46d118cec992df743`。

| 收據 | 實際結果與限制 | outer SHA-256 |
|---|---|---|
| QA76 | 原完整依賴鎖核對、固定commit建置成功；`built_not_validated`，不改舊包 | f29e419db8192f22cb710f000fea9bcb819e544f76f0795d24eceace6a924fbe |
| QA77 | 原同版harness的Python／EXE launch、journey、model、H20、直接Qt入口及錯設定拒絕通過；原180秒subcase期限保持，合成隔離用途 | b9d89b8cfe5ca6a7345a861548a5d72c192d7f0256d64711f4531899770ce9f2 |
| QA78 | 靜態預檢發現舊QA72整份test imports依賴未打包的pytest／QtTest且重插checkout path，規格及候選保留，沒有啟動Python或生成Job收據 | 不適用：未執行 |
| QA79 | 抽出原三個geometry／visible helper，改用候選內Qt滑鼠press／release事件；Root漏列QScrollArea匯入，固定來源parent在比較前FAIL；原輸出與收據不改 | fd668898a31afc55e9ae1c2a6c2b236011f082a44896af2c4a07487cfe31e918 |
| QA80 | 只補QA helper該匯入；全部原斷言及120秒phase／270秒driver／15秒UI保持。固定來源Main14068→11644、EXE38052→17332重用QA41兩run與QA71年度合成版本，正常binding→重開／雙run比較／返回→新程序；兩形態結果identity相同、13來源不變 | 829e62fb25b5665fdee60887b74165dfaf9d7fdfc72af876208802ab7200dff5 |

QA80四phase各核683個產品module origin，Python須來自固定archive、EXE須來自_MEIPASS，另核EXE路徑／SHA與build identity；沒有借checkout產品碼、venv測試工具或重產producer。原幾何helper正文逐字複用，保留祖先／viewport裁切、widgetAt命中、可見／active與頁籤捲動守衛。完整archive前後重驗；7272pins（含7089候選檔）前後一致。來源／成本／PIT仍blocked的原診斷按原值相同，不補精度或績效；取得原件與新用途接受亦未被合成錨點取代。

原同版收據`output/qa/baldr_same_version_675bea262f8d_5a3fcff1/same_version_receipt.json` SHA `200befbeba50de48c3d44f51b008dbb3793f2c1caa7389b6b67edac1308ffa6f`。新四phase收據在owner task `increment31_registry_fixed_phases_qa80_python`／`..._exe`；Python parent/fresh SHA各`136106acfb870ceea766fac2b9b6f0edb4c2d1192df2bc5fa363921cf1d5571f`／`4318431c0e73ee0191692fdc524fbbbd3086f21af5e6eb81f4973a53b6d013dd`，EXE各`9cc70b2a99873fc646bbae3e102bb49167fc177960c082029eeffd0048884dfb`／`35e6112fed6a399c5acc4529cf4c1e65c7f8d96fdd7aa82ee2f9916b96e6b9c6`，均經實際檔案SHA讀回核對。

各Job維持8GiB committed／12程序、kill-on-close與workspace mutex，三PID陣列自然空、process／Job handles關閉／mutex釋放；QA79失敗亦合作關窗自然終止，無forced cleanup。原交付五檔與active_delivery保持。QA81已核四phase／四Job實際SHA與文件一致，7275pins前後不變，文件治理12features／15link sources／errors=[]；outer `aefa837b1c2a46fdadd226e954ede551`／SHA `d2f83573aaf774e703ad684e8b4b4fb6b7b8ac49f536a5c7c8fb4619c54c33e6` 自然閉鎖。新增Python只有owner QA helpers，產品碼未再修改，因此不重跑已通過且來源未變的Workbench／validator／mypy。Luna9只做靜態複核、pending writes=false，沒有新增agent。

這完成指定候選的限定EXE同版與本輪新ports旅程，不是Native真人、正式安裝或其他主機資格。P03官方完整用途與單位／版本、TPEx指定授權、P08來源／幣別／執行／成本權威、完整跨年／長期分段、真N、完整雙策略績效、其他四用途完整保存及自然成熟仍各自開放；不改正式資料、Task、maintainer或交付，不授交易／發布或完整P00–P14／G0–G4。

## Increment32：先交可試用V1，解除真實資料與比較按鈕阻斷

使用者新決議已直接寫入原補完計畫§0.3：四條第一版旅程與出口凍結，完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4未完成項保留第二階段；新增需求與非阻斷優化不再擴大V1前置。此Increment目的只在解除V1啟動、資料及正常操作阻礙。

Root只讀既有正式stock_data_whole.csv、companies.csv與四份指標檔，在全新隔離根建立2317／2330／2382／2454四檔上市普通股副本，逐行核原CSV，12,390筆、2014/01/02–2026/09/23；四檔不是全市場。沿原V4 producer保存明示子集並由public catalog strict reader重驗。所有來源時間unknown、historical PIT=false；企業行動／還原價格未核，回測僅未調整日價研究假設，不授績效排名、Paper／Forward或交易資格。原正式DB未開啟／寫入，無新網路抓取。原件／hash／日期／rows與副本清冊保存在本owner `v1_real_trial_qa86.json`，外部隔離根另存data_provenance.json。

Native QA82第一點擊未命中原FAIL保留；QA83在原15秒期限觀察125ms曝光後命中，屬啟動診斷，不是旅程PASS。QA84 canonical path FAIL、QA85最後清冊長路徑FAIL（producer已完成）、QA86接續已保存來源與原CSV逐行核對PASS；QA87清冊長路徑FAIL、QA88 QA字串compile FAIL、QA89設定檔unsupported-key FAIL、QA90 test profile附加_test的空根FAIL均保存，未變產品守衛。QA91使用普通prod profile與明示隔離根，真正Native按鈕發現第二股加入後比較按鈕仍停用：舊test直接呼叫slot掩蓋enabled狀態，不能當正常操作完成。

最小修正只在價格研究view加入／清空比較籃後呼叫原_set_enabled_state；busy／closing、unknown、來源pin與精度邏輯不變。原test改用按鈕並檢查0／1／2欄與清空後enabled狀態。QA92 compile、受影響10案例與Workbench85共95 PASS，validator 25 PASS／0 FAIL／4 SKIP、原mypy1016檔PASS（既有UI ignore_errors=True仍不證UI強型別）；outer `single_owned_qa_18a7c06e87a8461c8f4ee2c482c82dfb/receipt.json` SHA `1b3a850274b3137236451714f5bfde3d55083c5aa671abe902563e22029edd43`，三PID陣列自然空、handles關閉、mutex釋放，無forced cleanup。Luna9僅靜態複核，pending writes=false；累計仍9/10，無新增agent。

目前為修復後固定候選建置前checkpoint；V1四旅程、直接啟動入口及最終已知問題仍待本輪完成，不用上述局部PASS宣稱第一版已交付。各原FAIL與外部隔離副本保留，不重觸發maintainer、不改正式Task、不push／發布。
Increment32接續：修復後c8fcc8a3候選由QA94以真實四股完成Native比較、個股返回、版本收藏及新PID 1968→30468 Watchlist exact重開，來源清冊不變；outer SHA `cf8abe7dc5e119491432f46d83046143f755c56407880bffe9a456b8ab13f98c`。QA95–96為QA市場子頁定位失敗，QA97–99為1440px Native螢幕命中診斷FAIL；Qt active與childAt可見但topLevelAt=None，沒有降低命中守衛。QA100在既有640px完整命中下大盤與個股真行情／技術歷史讀取成功，之後正常回測揭露真正V1-04 frozen阻斷：規則封存要讀取baseline executor原始檔，但包內沒有.py原件，執行以FileNotFoundError中斷；原FAIL保留。

必要修正限原封裝：納入baseline_score_executor、score_threshold_policy、broker_simulator、backtest_service四個原檔，build resource manifest綁四檔SHA並由既有frozen identity檢查拒絕缺件／改寫；沒有以假hash、跳過來源驗證或回落checkout解除錯誤。QA101原封裝與金融next-open對齊、交易成本整數分、損益分量化、Decimal保存共24 PASS；兩個新增frozen測試漏建立必需icon fixture而FAIL，未跑mypy。QA102只補該fixture，兩例缺件／篡改拒絕PASS，compile與單檔mypy通過；outer SHA `bb265e94bfac562a455b0b324fecf7bc1040f4dea74cd75bbebae062f6fe112c`。UI碼不再變更，不重跑QA92已通過的Workbench／validator／整庫mypy。下一步只重建固定候選並接續V1-04保存／重開，V1尚未宣告交付。
### Increment32最終V1候選交付（2026-10-15）

固定來源`4cfddca1d4b1e25e958b2b3dd988035a4d233b67`；候選`dist/candidate_4cfddca1d4b1_cb518ff9/baldr/baldr.exe`，55,968,569 bytes，SHA `e430c5c932ff028102548f15e934a4f0ec054d815c10e3c88681c452b380cb06`。QA103沿原建置管線與依賴鎖納入四份回測來源，原dist/baldr／active_delivery及舊候選不變。未簽章，不是發布或原完整Gate接受。

| 第一版出口 | 實際限定證據 |
|---|---|
| V1-01市場／個股／技術圖表／返回 | QA108獨立最終EXE Native PID47168，2330價格120筆、技術歷史120筆、末日2026-09-23，正常大盤子頁／載入／價格圖表／返回；outer SHA `f410270433260613c3de4066720f6c8b73d54b93d3bf251a3f0ded0cb4359f44`。 |
| V1-02價格條件／比較／個股返回／版本收藏 | QA94 c8候選真實四股Native閉環已PASS；封裝修復未改這些UI／ports，QA106最終4cf候選PID17552只重開原QA94收藏，query／page／選取／比較籃／原件不變，不重產producer。 |
| V1-03觀察清單／新程序回訪 | QA94 1968→30468原exact收藏重開，QA106最終候選新程序同版讀回；沒有搬移正式清單。QA106該子命令PASS，後續舊入口hash命令FAIL不能把整組記PASS。 |
| V1-04正常回測保存／歷史／返回／新程序 | QA104市場／個股及正常2330執行、保存與no-trade本金守恆完成後，因未收合設定導致history控制項height=0 FAIL。QA105不重跑producer，沿原「收合左側設定」接續同一run `single_backtest_20261015_000644_36de48c0`，PID41080→35336正常查找／開啟／返回／新程序，metadata／equity／trades身份一致；outer SHA `a5ca6ebf91470011f6c32e8e7fbd0f435a6ff14f3bfabcd90e9ea0e27fa613c9`。QA105 driver摘要繼承了V1-01標籤，但該組實際只驗Registry讀回；V1-01以獨立QA108為準。 |

入口QA106的Windows PowerShell無Get-FileHash命令，舊入口原件保留；QA107新`Launch-Baldr.cmd`改用內建.NET SHA，不繞過hash，實際`--check`讀回最終build／專用config／隔離DATA_ROOT、OUTPUT_ROOT與RESEARCH_STATE_ROOT通過。完整7093候選檔、20不可變輸入與103前組Job閉鎖清冊保存；outer SHA `19ab587bd693374b2c637eb4a6377f66ef42384373d4a02e115dcada9615b66c`。所有當輪Job維持8GiB／12程序與mutex，三PID陣列自然空、handles閉鎖、無forced cleanup；不終止其他owner程序。Luna只靜態複核，累計9/10、pending writes=false。

交付入口`output/trial/Baldr-V1/Launch-Baldr.cmd`，TRIAL_GUIDE.md／DELIVERY_RECEIPT.json列四旅程、SHA、來源及已知問題；BUNDLE_INVENTORY.json／INPUT_INVENTORY.json是完整檔案清冊。四股原價12390筆至2026-09-23，大盤副本至2026-10-14，沒有把兩域日期混用。企業行動／價格還原／來源發布時間仍未核，historical PIT=false與缺資料指標維持不可用。回測成本／next-open／Decimal保存沿QA101已過的金融案例，不反覆重跑。窄視窗查歷史先收合設定；1440px Native topLevelAt異常、真人與跨機未全驗，列已知限制而非隱藏。

第一版是可本機試用的固定候選；完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4未完成項、來源權威、TPEx、歷史PIT、真N、完整雙策略績效及自然成熟全部保留第二階段。後續先依這四條旅程的實際問題修正，新增需求與非阻斷優化不進V1。正式資料、Task、maintainer、push／發布與交易未變更或啟用。

QA109最後讀回交付8文件與11具名收據SHA、四旅程獨立scope及原計畫第二階段保留均通過；交付收據SHA 2037e135996423edb7ddb633a479443ffe3bf71f25bb1c593128a51b2dd7e0b2。此次5文件治理12features／errors=[]，不是產品完整Gate；outer SHA 1f4a7dd3bd2c9eb55366a2dfe6583a3bc526e35364a71df8e1095e594ee5abf3，自然閉鎖，無待執行Python／QA或worker writes。

## Increment33：V1實際啟動入口的關閉生命週期

本Increment只解除第一版共通交付風險：原QA107驗cmd --check、各旅程以EXE腳本入口建Main，尚未覆蓋無參數GUI的StartupController生命週期。QA110從已交Launch-Baldr.cmd無參數真正啟動、同Job Main可見，送WM_CLOSE後Qt event loop正常回0，但launcher finally再次dismiss已DeferredDelete的StartupView而RuntimeError，實際程序退出碼1。原FAIL outer SHA `ff124c36d30982aeabf750dfa59cb5d2f3e998abda0e09fd6190ce5d8c9b0629`；實際stdout／stderr另保存owner qa110_original_stdout.log／qa110_original_stderr.log，不以正常Qt返回0掩蓋最終錯誤。

最小修正僅StartupController.dismiss的重複清理狀態；ready／取消第一次仍hide＋deleteLater，finally再次進來不再碰已刪除的C++ wrapper。新增兩個真Qt DeferredDelete後重複dismiss回歸；QA111 compile、startup／launcher／必需Workbench共100 PASS，validator25／0／4、原mypy1016檔通過（UI既有ignore_errors不證強型別），outer SHA `dc510ceb633e00bcfe4017b21eaec1c89e4c307d18d159f6a5edd1a7671c109c`。無金融、資料、策略或來源守衛變更，不重跑已通過金融案例。

QA112只診斷既有1440px命中風險，沒有重跑旅程或放寬守衛。固定4cf候選同PID29956在640／1024／1440px比對Qt與Win32實際client、frame與WindowFromPoint；1920×1080、DPR1一致，640／1024控制項命中本Main，1440的[1318,133]命中其他程序HWND，Native前景亦非本Main。這證明當次螢幕點被其他程序覆蓋，不是按鈕尺寸或DPI錯位；未讀取其他程序視窗內容、未操控它或強搶前景。outer SHA `291fa0616fdfec9f55ba34cb38ec3153134d550d2395a9ffdc4ab65cf5492362`。不因此宣稱1440px整旅程或真人全驗；指南改列自動化遮蔽界線。

QA110–112各組都在8GiB／12程序Job與workspace mutex內，前組三PID陣列自然空、handles關閉／mutex釋放，無forced cleanup；QA110開始可用RAM約22.4GiB。當前交付4cf原候選／收據保留；待重建只含此修復的新固定候選並驗無參數GUI退出碼0後，再更新試用入口，不更動正式資料、Windows Task、maintainer或完整第二階段範圍。
Increment33交付更新：固定`505d56f1c1178323f8184e291b718966431c7b07`，候選`dist/candidate_505d56f1c117_76de3824/baldr/baldr.exe`，55,968,615 bytes，SHA `e443188ef6227bfbfcd145758b125ceb7e8e7909bb0f3508bd65f8bd8074b7a3`。QA113建置成功後，QA114從暫存版本化cmd入口無參數啟動實際Main PID2000，合作式關閉後真實程序exit0；outer SHA `6d4258d025553ef0b62400bd237b747b4903e28cf006759c9e01d593896b1cd3`。沒有用腳本注入Main或只看Qt event loop返回替代此結果。

先核原交付9檔與snapshot pins一致，才將原`output/trial/Baldr-V1/Launch-Baldr.cmd`更新到505；原4cf完整交付保留`output/tasks/baldr-completion-resume-20261014-01a13cf9/v1_delivery_snapshot_increment32`及其pins。QA115實際common入口--check讀回505、同一DATA_ROOT／OUTPUT_ROOT／RESEARCH_STATE_ROOT與專用config，7093候選檔、20不可變輸入與111前組Job閉鎖讀回通過；不可變輸入逐項與Increment32清冊相同，outer SHA `8c4d5f8b8ea131a474191c9c718c25d0601a1e5d56e7e5720697782989a45bac`。固定commit範圍runtime差異只有ui_qt/startup_view.py，金融與Reader／ports未變；沿用第一版四旅程具名接受，不重跑無影響案例，也不宣稱全Gate完成。

指南已將1440px命中失敗改述為已證外部程序遮蔽，而非未解產品按鈕／DPI問題。維持原螢幕命中斷言、原FAIL、未全尺寸真人與跨機界線，不操作其他owner視窗。完整第二階段與原計畫待辦未擴成V1前置；目前同一入口可試用505修復版。
QA116最後核原4cf交付snapshot與新505收據、18具名QA pins、8交付檔案及runtime單檔差異一致，實際GUI exit0證據已綁新候選；交付收據SHA `c472e1429363679a49373eaaa06e7d2a3482d95b0e5c22417815e844d9850432`。此次5份文件治理12features／errors=[]，不外推產品Gate。outer SHA `84da0aa0b317640b156f5a18506c0da4a1258450825a0465bc0a9a3a40b22330` 自然閉鎖，無active Python／QA；原完整計畫保持未完成、第一版四流程凍結，下一步以實際試用問題為優先。