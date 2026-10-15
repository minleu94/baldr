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
