# 每日來源版本快照與小時可用性契約

本契約落實使用者於 2026-10-13（台北 10/14）採納的每日固定抓取政策，適用 P00／P03 的新保存來源及已接受的指定研究用途。施工順序仍由[原產品補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md#95-資料阻塞分流與下一批交付2026-10-14-調整)管理，實際驗證看[本輪 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。本頁不授正式資料寫入、排程變更、歷史回補或交易。

## 具名廣達月營收目前研究（Increment139）

`quanta-monthly-sales-2382-2026.v1`以既存TWSE公司原件的`2382／廣達電腦股份有限公司／www.quantatw.com`，綁完整HTTP 200／EOF的官方月營收HTML。TWSE原件只作`research_shadow`公司身分審核，不擴原名錄正式或散布資格；新用途接受僅涵蓋本機目前個股研究，與每日批次品質獨立。六件原件及manifest／receipt雙外部SHA重驗，完整HTTP、TWSE封存鏈、公司唯一性、網站網域、表頭、月序及同表比較基期均須吻合；原136驗證頁／缺件與正式資料保持。

產品只呈現2026同表調整後合併的最新月、前月、去年同月整數百萬元，以及官方0.1%月增／年增率。Decimal區間只核原披露率是否與同表基期相容，不取代披露值、提升金額精度、混另一年度表或推算累計。原件數值2026-09為325300／423971／184109百萬元、-23.3%／76.7%，不是回填歷史版。

新保存批次發八檔版本，pending／failure與集合不符拒讀，原件前後SHA保持；更正另存，不啟用正式writer或maintainer。沒有官方發布／更新timestamp，以`successful_batch_completion_fallback`保存批次及台北guard小時；本份為`2026-10-18T04:00:00+08:00`。Reader拒未來cutoff及未到小時，報告service只在目前日期且未指定舊context時投影，歷史PIT／特徵聚合／評分／策略／ML／交易維持false。來源用途與封存證據、成熟Main／fresh及EXE界線分列於[139 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment139-quanta-monthly-sales)，配置見[操作手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#廣達月營收固定版本來源分支139)。

## TWSE 日價方向文字版本（Increment128）

既有 `DataLoader.download_from_api` 的新下載採 `twse.mi_index.direction_text.v2`：三個既有方向欄別名共用文字正規化，接受明確正負符號及單次 HTML/entity 解碼，顏色不作方向證據。保存狀態為 `+`、`-`、空缺或非空 `unknown`；未知不能被 CSV 的 NA 轉換抹成空值，連價差為零也不自授平盤。金額仍由既有 Decimal reader 與矛盾方向守衛判讀，不由相鄰收盤補官方漲跌。

原始 body、首份 custody 收據及每次 observation 仍 create-only。同一 raw SHA 若早已由 `twse.mi_index.v1` 保存，首份 v1 原件與首見時間不變；新觀測另存 v2，projection／publication／列級 public reader 精確綁本次 observation 的 parser。v2 在發行與重開時逐列回綁原 body 的方向，不能只重算 CSV／manifest hash 或改 parser 標籤就冒用。v1 原投影按原版本讀取，不重新解釋或修改其數值；CSV 漂移仍拒讀。前瞻原件快照 reader 可讀這兩個明示版本，保留實際版本與時間，其餘來源／URL／單位／修訂守衛維持。

這是既有下載鏈的工程修復，不補抓或回寫歷史資料、不啟動 maintainer；首見與批次觀測不冒充官方發布時刻、歷史 PIT、每日用途接受或較早可用小時。原試用包、缺方向舊列及原失敗保留。受限驗證與未驗邊界見 [128 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment128-twse-direction-text)。

## 具名營益固定版本（Increment117）

此接受僅涵蓋[政府開放資料20762](https://data.gov.tw/dataset/20762)之`d9778530…b609`原CSV、2330／2026-H1的營收與四個利潤率；不是全資料集單位契約。Root以既存完整官方發行人PDF獨立核對幣別、半年累計基礎與顯示精度，產品數值只取開放CSV。營收原值`2404483.69`百萬元以Decimal轉TWD，四比率保留原百分比，不以PDF較低精度替換。其他公司、前期及PDF重展示用途未接受。

`twse-operating-summary-2330-2026h1.v1`沿既有DailySourceUseAcceptance保存精確source／schema／單位／current_research用途。批次另外保存原CSV、HTTP receipt、資料集頁、license及machine metadata的bytes／SHA；manifest與receipt各由caller提供外部SHA。Reader重驗具名原件及用途、pending／failure與讀取期間的檔案signature；不得只改外部SHA將其他公司、幣別或提前時鐘授資格。只有出表日期，官方發布timestamp仍未知，`successful_batch_completion_fallback`明示以本次成功保存小時為準；新版本另存，原attempt與正式庫不改。

目前僅供原個股基本面頁查閱及固定版本重開，P00/P03的這一葉不授P07/P12消費資格。前期比較不可用、歷史PIT／特徵聚合／交易flags為false；正常Main、新程序及固定EXE的實際狀態分別見[Increment117 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment117-operating-summary)。

## TWSE單日注意公告候選（Increment48）

`twse-attention-dated-report.v1` 限定官方 RWD `announcement/notice` 的 `querytype=1`、相同 startDate／endDate、sortKind=DATE、response=json；原 HTML、web-report.js 與 main.js 的固定 SHA 只證官方查詢契約。單日 JSON 須完整 EOF，stat=OK、八欄／params／title 精確相符，count／total 與完整唯一證券列各自相等。OpenAPI 無日期佔位拒作無公告證明；`編號` 不當唯一身份，`累計次數` 只保留原文，不推論連續日數。理由保留原 HTML 與限定紅色 font 的純文字投影；收盤價與 PE 不轉金融數值，市場資格不由列數推定。

`twse-attention-daily-manifest.v1` 固定原 raw、HTTP receipt、request／headers／cookies／worker job與result及三份文件的 bytes／SHA，`twse-attention-daily-receipt.v1` 綁 manifest 與實際 first-persisted／successful-completion／available-hour。原 HTTP receipt 沒有 worker-result SHA，新版本明示綁保存的 bytes，不補造舊 hash。只有公告日，官方發布小時保留 None；依 `daily-hour.v1` 使用成功批次 guard 小時及 `successful_batch_completion_fallback`，不拿 HTTP Date 作官方發布時刻。更正新目錄、pending／failure 拒讀、讀前後完整核驗與取消，版本保留來源用途未接受／歷史 PIT false。公開 reader 拒未來 cutoff，正常 report provider 將截止限在觀測時刻與報告台北日末較早者。保存與參數見[指南](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#單日官方注意公告後續開發分支)。

## 具名營益三公司目前研究（Increment125，固定125）

`twse-operating-summary-reviewed-2026h1.v1`是資料集20762固定原件的具名用途增量，僅2317／2330／2454、2026-H1、TWD與四率、`current_research`。各發行人文件只核半年合併期間、單位與CSV顯示精度；稅後率為合併本期損益而非母公司歸屬淨利率，PDF不作產品值或隨快照散布。原1055列／CSV版本不授全資料集用途、前期、歷史PIT、篩選、策略、ML或交易；2382未接受。

新外層沿原v1 public reader核7原件，另存用途manifest／成功receipt並保留原件於相對`base/`，不改原2330政策或首存時間。來源用途與每日可用性分開：新成功批次由真保存完成時間取台北guard小時，此前拒讀；沒有官方發布小時，不借HTTP Date或期末倒填。雙外部SHA、具型別schema、固定子路徑、原件完整性／讀前後身分、pending／failure及未來cutoff守衛保持。新scope不修改generic daily record或正式庫，來源與固定EXE正常GUI／fresh已限定驗同值、版本與時間；其餘待驗界線見[125 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment125-reviewed-fundamentals)。

## TPEx法人精確diagnostics用途接受（Increment54）

一次性來源用途重用`DailySourceUseScope`／`DailySourceUseAcceptance`，由`institutional_source_use`明選`source_use.json`絕對路徑＋外部SHA讀取。scope固定data.gov.tw:11856、tpex:openapi:3insti_daily_trading、TPEx、tpex-openapi-3insti-daily.v1、官方GET operation與resolved schema的canonical SHA `efda72f09eeea74a135dd63afd9c8fbc926d3464e9ba658144c7ab7d58f4e3cc`、shares與diagnostics；acquisition route明綁tpex.tpex_3insti_daily_trading。這是獨立精確契約，不輸出generic P0 limited，不改原v1決議hash或13來源分母。

Root已核四份官方原件的固定完整fingerprint：政府條款第1版、metadata11856／A45020000D-000309、資料集HTML與既存OpenAPI3。metadata CSV25欄／resourceAmount839不等於API20欄或市場真N；新契約只授既有parser已核九aggregate股數的diagnostics，不推自營細項、不授跨市場、連買、評分或交易。顯名保留提供機關、名稱／版本、年份與官方授權連結。機器契約不虛構human owner/reviewer或法律同意。

另存四文件及canonical接受檔，create-only／fsync／pending及failure隔離、原件與copy讀前後重核、取消及來源變更守衛沿既有檔案核心。正常CLI採真時間，接受不得早於最後必要metadata真收據2026-10-15T23:06:40.284879+00:00，也不得注入早於本次真保存開始的clock；不能回填接受資格。reader只讀同pin與文件版本，cutoff早於accepted_at拒絕。相同scope可跨每日批次重用，文件／parser／schema／市場／單位／用途改變須重核受影響來源契約；不每日重寫接受檔。

原每日批次仍獨立重驗其原件／品質／合計／單位／成功小時。明選合格用途pin時Read附typed source_use與source_use_accepted=True，限定diagnostics；無pin仍False，candidate_only=True／historical_pit_eligible=False不變。接受時間不能提前原07:00資料可用小時，原批次收據不改。TWSE wrapper不借此接受，通用P0 family／正式DB／排程資格不提升。步驟與排錯見[用途接受指南](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#tpex法人用途接受與重開後續開發分支)。

## TPEx法人OpenAPI明確單日（Increment53）

原法人 capture 新增明選 `tpex_openapi_institutional`，只用資料集11856對應的 `https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading`；不借T86 discovery、不讀TPEx舊web／信用或年度日曆。API沒有歷史日期參數，caller須明示原回應report日，sessions／max_lookback_days／max_attempts皆須為整數1，其他值在transport與建立output前拒絕。原 `legacy_all`／`twse_institutional` 不變；rebuild沿同一選定scope及原raw，不發HTTP。

`tpex-openapi-3insti-daily.v1` 是內部解析契約，非官方發布版本號。依既存Swagger與實際完整array的20個字串欄名（含原前置空白與拼字）逐欄核對；7位民國日明示3+2+2解析，全列同日、代碼唯一，拒重複JSON key、非字串數字、float／bool／缺欄或模糊suffix。原外陸資兩子群各核buy−sell=net及加總，再核三類aggregate與官方三大合計；只提供九個有證據的整數股數，不反推缺少的自營商自行／避險細項。股數意義來自資料集與Swagger欄位描述，不能借用TWSE的hints常數。完整原件與該版本欄位／來源／單位／合計不符時整包拒絕，原件仍保留。

新generic `seal_institutional_capture`／`read_institutional_daily_snapshot` 復用原create-only／完整EOF／雙SHA／原件重播／pending／failure／signature／取消與台北小時守衛，依原manifest明確scope驗市場；舊 `seal_twse_institutional_capture`／`read_twse_institutional_daily_snapshot` 仍只接受T86，不因新增市場擴權。Read DTO末尾 `market` 舊預設TWSE，TPEx固定為TPEx；正常UpdateService／原法人頁使用generic reader，未選市場或latest作fallback。

本次政府資料集HTML完整526503bytes與舊Swagger476923bytes、真API898原列／1151015，各自原件／SHA／HTTP EOF獨立保存。新版本重播已保存HTTP，capture metadata時鐘是本次重播完成，上游真HTTP時鐘另保留；首次daily成功保存使用真當下台北10/16 06:45:15，07:00才可用。沒有官方發布小時，basis仍為successful_batch_completion_fallback，不補歷史PIT。政府開放資料證據不代授整個institutional_flows來源桶、舊web或TPEx年度calendar；正式P0用途決策／排程／SQLite不變，candidate-only／source_use_accepted=false／historical_pit=false。正常操作見[TPEx單日指南](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#tpex法人openapi單日版本後續開發分支)。

## 後繼M1法人多股讀者（Source）

後繼M1提供`read_institutional_daily_snapshot_batch`：明選1–5000個唯一代號，以同一內核完整重驗一次固定批次，再取原列；原單股reader與TWSE wrapper簽名、DTO及守衛保持。`total_records`仍是完整原報表列數，未命中不補零，多日原列不混成單日。`TPExThemeFlowReader`只消費具原TPEx diagnostics用途pin的同日原股數，限caller由同版映射確認的TPEx股票；不授TWSE或跨市場合計。接受時間與批次小時取較晚者，來源身份保留raw／manifest／receipt／用途SHA，不以股價換金額。QA185–188已限定驗原API相容、舊898與新888原列、映射交集及新程序；後續Source已加flow-only v2入口，QA200限定測試通過、真資料與正常Main尚待；固定08沒有新batch API。10/19新資料另由固定08原法人頁驗讀，不修改原10/16題材或借日；詳[具名QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md)。


### 題材TPEx股數診斷版本（Source v2）

read_theme_research_snapshot保留原簽名／DTO與v1的同包mapping／prices；v1出現institutional欄位明確拒絕，不靜默忽略。新schema為baldr.theme_research_snapshot.tpex_flows.v2，精確五個頂層欄位schema／data_date／saved_completed_at／mapping／institutional，不接受prices或其他來源namespace。mapping只允許同包相對path與SHA、原完整CSV欄位與4MiB上限；同股跨題材market_type衝突拒絕，僅精確tpex（上櫃）納入，無eligible成員拒絕。

institutional精確含daily_directory／manifest_sha256／receipt_sha256／source_use_path／source_use_sha256；三SHA須小寫hex64、來源為既存絕對位置。原typed daily/use reader繼續完整核原件／品質／EOF／股數／時鐘／用途及讀中變動，metadata不能自授資格。這份descriptor不移位或重seal原批次，不能冒稱全包可攜來源。新descriptor仍核實際保存後台北向上取整小時，與原daily／接受時間各自守衛；新副本不倒填時間。原manifest／mapping前後hash保持，資料日必須沿本次明選來源，不借其他日價格或法人。價格／TWD金額／五日量能維持缺件，部分覆蓋只顯示已覆蓋成員的診斷合計；historical_pit_eligible仍false。QA200只證候選接線與邊界，真原件／正常Main／固定EXE接受分開，見[具名後續QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#題材法人接線sourceqa200)。
## TWSE法人候選成功批次（Increment42）

此為原 `institutional-credit-flows-candidate-bundle.v1` 的獨立 JSON companion，限定 `twse_institutional`／原T86／1–30個排序唯一日期。原 parser／source version、整數股數與 candidate 不變，不借 MOPS record 或另一 revision reader namespace 的接受。`institutional-daily-manifest.v1` 綁原 capture manifest 外部SHA、完整raw／metadata／candidate／readback的絕對路徑、bytes及SHA、原始官方時間文字／台北時間、來源時鐘與原報表列總數；這個總數不是股票 universe 或真N。

原transport以8MiB上限有界讀取，metadata的 `flow-http-body.v1` 保存EOF、body bytes、宣告Content-Length及encoding。新seal必須identity／完整EOF且宣告長度若存在須相等；壓縮回應只保留原capture相容，不冒稱原壓縮body的新seal證據。舊件缺EOF拒絕，不追補證據。逐分區核端點／市場／股數單位／版本／params、原parser重播、quarantine=0、accepted counts與candidate全文（含bool/int區別），不從SQL或目前資料補齊。Increment43另核原body的 `hints=單位：股`、唯一欄名與自營商／三大法人獨立宣告合計欄；metadata的常數shares不能代替原件單位證據。原parser有單位文字卻不符時拒絕，列內宣告合計與各分類重組不符時隔離；legacy缺欄候選仍保留原解析語意，但不可新seal／exact-open每日版本。

`seal_twse_institutional_capture` 只在明選run旁建立 `daily_snapshot`；拒正式／私人資料根，原件不改。pending及manifest exclusive-create並fsync／讀回後取首次保存時間，全部原件再核驗後取批次完成時間，首次與完成不得跨小時／倒退。`institutional-daily-receipt.v1` 綁manifest SHA、兩時鐘、時間政策及可用小時；官方時間向上取整與成功批次guard取較晚者，缺官方小時明示 `successful_batch_completion_fallback`。整點完成沿原guard留下一可用小時，決策cutoff本身不取整。

收據寫入讀回後再次核全部bytes／SHA／完整file signature，再取最終時鐘，確認仍早於可用小時並檢查取消，才移除pending。完成時鐘是上述批次驗證後的取樣，`completion_basis=durable_raw_candidate_manifest_and_pending_closed` 指檔案寫入handle已關閉，並非宣稱此刻已移除pending；不宣稱另存了最終unlink時間或OS crash原子持久性。失敗保留pending／failure並拒讀，更正另存，不覆寫版本。

`read_twse_institutional_daily_snapshot` 要求 caller 的絕對目錄與manifest／receipt雙外部SHA；讀前後拒pending／failure、重驗原capture全批原件／品質與manifest全文、重算小時並要求 `available_hour <= decision_cutoff`。返回前再次重讀bytes／signature及檢查取消；不掃latest或回落其他來源。只回所選證券代碼原列，零匹配不造零值。正常UpdateService／法人頁為純讀取consumer；`candidate_only=true`、`source_use_accepted=false`、`historical_pit_eligible=false`固定，沒有日曆連買／來源用途或歷史資格。限定離線Main／fresh、失敗及修正證據見[Increment42 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment42p03法人成功批次與正常唯讀頁)。

Increment43取得2026/10/15單日真T86原件、EOF及21,000列品質，保存批次於台北10/16 03:23，最早可用04:00；原件無官方發布小時，basis保留批次fallback。這不是21,000檔股票接受或歷史版本認證，不能為立即顯示而注入未來cutoff。真來源取得、單位／品質、用途／授權接受及正常Main／fresh是不同證據，進度見[Increment43 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment43p03真t86單日原件與宣告合計守衛)。

## 已存官方處置來源的版本相容（Increment46）

`selection-official-disposal-source-pin.v3` 與 `selection-official-disposal-parser.v3` 成對使用，新增 `twse-punish-openapi-row-contract.v1` 與原官方 Swagger SHA `06e1cea82448361e733a0ad1ae16e52f5d5d6b71905acd078472f852c32c0eb0`，兩者均入 identity。`/announcement/punish` 英文 JSON array 的 Number／Date／Code／Name／NumberOfAnnouncement／ReasonsOfDisposition／DispositionPeriod／DispositionMeasures／Detail／LinkInformation 十欄必須齊全且為字串；原 raw 與 canonical 原列分別留 SHA。公告晚於觀測、非法期間、缺欄／錯型別、重複事件拒收或隔離；空列與未命中仍 unknown，不發安全證書。

舊 v2 pin／parser 配對、keys、canonical identity 及英文 array 未確認的解讀保留；直接建構 v2 省略新增欄位亦相容。不把保存來源改寫成 v3；需要新版解析時以原 immutable run 另產新 pin／研究來源。新 pin 仍 current_only、official_available_at=None、historical_pit_eligible=false，來源 pin 不能補證原 HTTP EOF 或把日期當發布時分。來源用途／每日 validator 與前瞻可用小時依本契約原規則獨立核驗。

## 時間與版本

保存版本對應的官方發布／更新時間原文及解析結果，統一 `Asia/Taipei`。UTC 或其他 aware 時間可轉換；naive 時間須拒絕。會計期末、資料基準日期及其他版本的更新時間不能充當發布時間。

`available_hour = max(ceil_hour(official_version_timestamp), ceil_hour(successful_batch_completed_at))`。14:45 只能在 15:00 使用，整點不變。缺官方發布小時時只用成功批次完成小時，明示批次時間依據；不能填造官方時間。成功完成必須包含完整保存與品質驗證，部分成功、尚未保存及失敗批次不可供決策。Consumer 使用原 aware decision cutoff 比較，不向上取整 cutoff。

每份快照綁 source／dataset／市場／股票／資料期間、parser／schema／單位、官方時間原文、batch identity／開始與成功完成時間、首次保存時間、原件 hash、版本及快照 hash。更正另存新版本，舊原件與 manifest 不覆寫；相同版本衝突拒絕。研究保存與重開必須釘相同批次與版本，不自動換成 latest。

## 一次性接受與每日驗證

來源與用途接受紀錄綁官方 endpoint／document chain、source／dataset／market、parser／schema／單位、時間政策、授權範圍與具名接受證據。日常研究、歷史回測及績效資格分別接受。相同契約無變更時，成功批次沿原用途接受；來源、parser、schema 或用途改變才重做受影響範圍。

每日批次核對原件／snapshot hash、來源與版本、批次成功與完整性、股票／市場／期間、單位與有限值、缺值及用途必要的前期；時間因果仍不可放寬。失敗保存具體原因與原件於隔離候選中，不發布半批為完整母體，不補 0。Reader 重新核對同一份 batch validation receipt 及指定用途；共用收據不能跳過錯來源／錯版本／未來資料的拒絕。

首次成功保存後可建立前瞻可用性，缺完整歷史 PIT 不永久阻擋已驗證新快照的日常研究。首次取得日前的歷史決策仍須當時版本證據；本次取得的舊財報不能倒填成舊日可用。Forward label、Paper 成交與估值、自然成熟及正式來源資格沿各自原契約。

## 目前實作邊界

`data_module/daily_source_snapshot.py` 支援既有 MOPS 月營收 v1／v2 的 hash-bound 版本，以及本文下方具名 TWSE／TPEx OpenData 雙市場 profile；兩者沿 Recommendation current-fundamental reader 的明確 `pinned_daily_batch_id`／cohort 接入，但保留不同 source identity 與 transport／parser 契約。Reader 必須由 caller 提供可信用途接受錨點，與 manifest 完整比對；快照不能以自述接受紀錄授權自己。無 pin 的既有 caller 保留原資格，指定 pin 卻缺 port／版本時拒絕或排除，不混入 latest。其他資料的政策已定，ports／producer 接入仍依工作包逐項驗證。

收據持久化逐列 `available_hour`／basis，public reader 依固定時間政策重算核對。原件與 pending receipt 寫入後 `flush`／`fsync` 並關閉，再取得完成時鐘樣本；跨小時或超過發布 guard 的批次保存 raw／原因並隔離。若樣本恰整點而後面仍需發布寫入，採具名下一小時 publication guard，保留原樣本，不能冒充該整點已完成發布。這個保守發布限制不改官方原文時間，也不把 decision cutoff 向上取整。

保存為 create-only staging→批次目錄，成功版本不覆寫。中斷 staging 不自動重用同一 batch id，失敗改用新的 batch id 並保留隔離原件與原因；reader 不讀 staging／quarantine。這輪驗證檔案關閉／fsync、原子可見性與程序重開，未驗 OS crash 的目錄 metadata durability。正常 UI／更新服務／正式排程與來源接受仍按[本輪 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)的實際範圍判讀。

`.receipt.pending.json` 保留至發布後時鐘核驗通過；public reader 在讀前及投影完成後都拒絕帶 pending barrier 的批次。發布後時鐘失效、隔離目標碰撞／搬移失敗或 barrier 無法移除時，不得接受已 rename 的成功收據。完整 capture 的失敗隔離使用 quarantine v2，分開保存 canonical／HTTP body、hash、metadata 與比對結果；其 self-hash 不是信任錨點。沒有 capture 仍保留 v1 格式，壞 capture 不偽裝為完整傳輸證據；保存可用 canonical 原件並保留主拒絕及次級封存錯誤。

`app_module/monthly_revenue_daily_snapshot_update.py` 與 `UpdateService.save_daily_monthly_revenue_capture` 已提供明確 root／scope／接受錨點／batch 的保存入口，經 preparation、既有 Decimal normalizer、immutable writer，再以新 FileReader 精確讀回。唯讀狀態不選 latest、不改舊 CSV 或正式 SQLite。保存前及最後 rename 前有合作式取消 checkpoint；不聲稱取消與 rename 之間具原子保證。晚 materialization 的本機觀測守衛保留，provider 的可用時間取原觀測可用時間與 batch hour 的較晚者，不倒退到較早批次。雙市場 cohort pin、正常更新 UI／推薦 session 及真來源接受仍待接線驗證。

## 取得與接入

### 日曆完整JSON批次（Increment21）

`official_calendar_transport_v1` 保存TWSE年／TPEx月別的完整JSON body、原URL、HTTP狀態與有界標頭、EOF／長度、開始及body完成時鐘、raw SHA；不重編碼原件，不套月營收HTML transport或MOPS Record。HTTP Date／Last-Modified保留為傳輸證據，不借作官方版本發布時間。直接capture函式的10秒為socket／合作檢查，阻塞I/O內的絕對期限仍需Root受控取得程序，不宣稱可在函式內硬中斷。

`app_module/official_calendar_daily_snapshot_v1.py` 先fsync並關閉含原件的capture，再沿原evidence parser核兩市場必要年／月分區、schema與session dates；93日為inclusive上限，較長期間組合仍待。manifest綁capture及衍生日曆SHA，receipt保存首次持久化／成功批次完成與向上取整小時。無經接受官方timestamp欄位時明示僅用batch hour；整點採既有具名下一小時發布guard。跨小時、超guard、取消或pending解除失敗，保留原件／failure及barrier，不發可讀成功版本。合作取消在pending讀回後再檢查；取消與unlink之間仍無原子保證。只驗檔案fsync／關閉及新程序，不宣稱OS斷電目錄metadata durability。

Caller提供各市場獨立的 `DailySourceUseAcceptance`，scope明列calendar dataset／endpoint／parser／schema／session-date單位／prospective用途；來源封套的自述不授接受。Public reader要求指定批次的外部manifest及receipt SHA，重算原件／分區／日曆／時間，並於完成前重驗三檔及barrier；decision cutoff不取整、改正另存新batch。合成父6316→fresh13156讀回同原版與更正版的8檔不變，fresh不重跑producer；這不授真來源、歷史PIT、performance、formal clock或正常UI。既有V1日曆candidate資格保持false，原JSON codec、Registry與UI不自動切換新批次；詳[Increment21 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment21日曆完整傳輸與每日批次)。

Increment23另把daily exact reader接到原Registry雙run診斷：typed pin明列batch directory、manifest／receipt外部SHA、兩市場獨立接受tuple、市場／保護根及aware cutoff。固定版本時取一次當下UTC時鐘；同一pair operation前後各重驗完整批次與identity，不先轉存成另一個candidate artifact。結果保留batch ID、三檔SHA、first persist／successful completion／available hour與basis及本次cutoff。換來源、錨點或欄位會取消並清舊結果；原artifact路由不變。合成Main父33268→fresh17672讀回17來源不變已限定驗證，只有QA注入的合成接受紀錄；正式Main缺真接受錨點時仍阻擋，不能推定真日常批次或歷史PIT已接受。

### TPEx年度股票日曆候選解析

TPEx年度`bulletin/tradingDate`的`data.html`已有獨立有界結構解碼器及原`official_calendar_bundle`中的股票語義parser。它保留原件／HTML兩SHA、年度基準日期、跨列與說明文字；基準日期不提供發布或可用時間。合法省略cell end tag仍保存內容，EOF未閉合、錯欄位／跨度、未知名稱、日期／星期不合、異日重複節日或股票開休市衝突拒絕。僅股票最後交易列的明示日期可產生僅結算休市，三類債券列不得關閉股票市場。93日含首尾、candidate／歷史PIT／績效界線保持。這是新年度來源的候選解析，後續具名daily接線見本節末段；不得cast成舊月份boolean、共用舊用途錨點或以取得成功授權日常使用。詳[Increment24 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment24tpex年度原件的股票日曆解析)。

年度來源另有`OfficialCalendarTpexAnnualJsonTransportV1`：固定官方年度URL、POST及原ASCII form body，保存原response bytes／SHA與完整性／時鐘，codec使用獨立schema與有界canonical base64。它與舊monthly V1共用原完整body validator，舊V1 URL／kind／key／wire解讀不變；不提供monthly `to_response`或getter。後續年度evidence及具名daily接線見下段；transport不自授用途接受、批次成功或可用時間。

`PortfolioPeriodAnnualCalendarEvidenceV1`另保存年度雙市場原transport及各自session dates，使用獨立wire、32MiB上限與canonical SHA；缺年、重複／多餘分區拒絕，93 inclusive仍保留。Root衍生沿已驗TPEx股票parser，TWSE新年度用途另核exact四欄、ROC年份／日期順序、weekday、已知股票開休市／連續假日與春節僅結算缺日；舊TWSE／monthly解析器原義不改。公開日期保持ISO字串以相容原pair比較，captured_at只取完整body完成時鐘較晚者，四資格flags不可由wire提升。讀回重建原transports、重算日期／clock／hash，不信任自述expected dates。年度evidence本身不授daily成功，後續同一核心接線見下段；目前沒有真用途接受或新成功批次；正向完整跨年雙原件尚未驗，缺年拒絕已驗。

新年度用途另核兩份獨立表的同名國定假日日期集合一致；不一致以具名品質原因拒絕，不借另一市場填值。各市場股票最後交易／僅結算仍各自推導，不要求完整sessions相等。這是該年度schema用途的品質契約；未來官方版本若有差異，保留原件並另核用途，不靜默放行。缺補假列先實證FAIL，再沿原斷言修復；詳[Increment26 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment26年度雙市場期間證據)。

Increment27新增具名年度daily writer／reader與三個`official-calendar-annual-daily-*.v1` schema；原月別V1 public API、wire與scope保留。兩者使用同一私有read/write核心，原件先create-only／fsync／關閉，再衍生、manifest、pending、completion、receipt、發布guard、rename、pending exact reread／取消及解除、exact成功讀回；沒有第二套publisher。年度只收原TWSE年transport及新TPEx年度POST transport，分區為`twse:YYYY`／`tpex-annual:YYYY`，每年各一份、最多4份及93 inclusive；年度manifest重新核年度evidence schema及雙市場日期，不轉舊monthly codec。

年度用途scope明列`{market}.official_calendar.annual`、annual parser及各自stock_annual schema，沿原session-date單位與prospective用途。Public writer／reader仍要求caller提供兩市場Mapping接受錨點；pin保留原constructor與ordered tuple，由同一家族的scope／endpoint明選monthly或annual具名reader。混搭、順序、錯endpoint拒絕；來源封套不能自授信任，不以reader失敗切換來源。Pair沿最小唯讀Protocol及同一daily identity前後重驗，原Registry控制器表單沿用。已驗明示合成錨點的保存、public run reader與真控制器；真取得收據的保守完成觀測basis、一次性真用途接受、正式Main配置及年度Main／fresh仍待，既有PIT／performance／formal clock均false。詳[Increment27 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment27年度日曆沿原daily與registry接線)。

年度真取得的Root custody候選另保留原receipt、request／headers／worker job／worker result與raw的外部pins。原worker result雖有EOF、raw fsync／關閉及hash後的完成觀測，但原receipt沒有其SHA，不能事後補寫成當時已綁定。新候選以原receipt的controller `ended_at` 作保守完成觀測上界，另列worker原文／SHA佐證；`started_at`明示controller attempt-start，兩者均非socket精確時鐘或官方發布。TWSE原transport保持，保守觀測版另存，raw與其餘欄位不變。兩個程序已從同13外部pins重算年度codec／evidence一致；owner output只是custody候選，沒有解除public artifact保護根、發布成功daily或授用途。下一個真正daily成功版仍須獨立接受與實際首次保存／完成小時，不能回填本次取得前的歷史可得性。詳[Increment28 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment28真取得原件的保守完成觀測與custody)。

日曆一次性接受可由caller明示的`portfolio-calendar-acceptance-binding.v1`保存兩個ordered typed接受，再以獨立外部SHA載入。64KiB canonical UTF-8只含schema及接受清單，不含batch或自授資格欄位；整組monthly／annual scope與endpoint須一致。Reader沿原calendar單link／reparse／protected roots／handle與讀前後stat／外部SHA守衛，另限64KiB讀取上限，成長超界拒絕；原reader預設上限及既有呼叫保留。Public接受decoder重用原欄位解析並核canonical內容，不以時區正規化掩蓋配置漂移。

正常Main只從`ApplicationSettings`明示成對的`CALENDAR_DAILY_ACCEPTANCE_BINDING_PATH`／`CALENDAR_DAILY_ACCEPTANCE_BINDING_SHA256`讀取；resolve／apply不讀接受或batch，loader才exact讀檔，配置不得位於frozen包或受保護來源／輸出根。Main入口複製caller設定，再將接受tuple或具名短錯誤傳原BacktestView／Registry controller。畫面仍由使用者指定batch雙SHA及市場，不掃latest，不加可手填授權欄位。設定失敗跨來源模式保留原因，daily pin／比較保持停用，其他工作區仍啟動；來源或設定變更沿原取消與丟棄過期結果。真接受決策與每日批次validator仍各自獨立，單憑外部SHA、配置成功或合成Main／fresh不授官方用途／PIT／績效。詳[Increment29 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment29明示接受binding接正常main)。

### 年度日曆用途複核（Increment30）

Root已沿既存完整TWSE Swagger、[政府資料集11761](https://data.gov.tw/dataset/11761)、官方OpenAPI條款與政府資料開放授權鏈，接受 `twse.official_calendar.annual` 的 `prospective_daily_calendar_research` 用途；parser／內部schema／交易日單位與 `daily-hour.v1` 保持原契約。顯名、原件SHA版本與衍生解析標示須保留，metadata更新時間不借作內容發布時間；Swagger沒有宣告 `queryYear`，實際2026年度成功不授任意歷史年度查詢。

TPEx指定年度POST仍缺可核對的資料／自動取得方式授權；官方中文條款第5／7節實際頁面不能解讀為所有公開網頁均可自動下載。僅有原件、前端動作或其他TPEx開放資料集不足以發行此用途接受。雙市場原writer／reader仍須兩份獨立接受，故本輪不發binding、不發布日批、不改正式Main配置。新接受只存owner task，SHA `7f120b20e261d6173f2536ab206ddb4576b258954fc7839259ceb5adf84bf697`；[具名複核](../../output/tasks/baldr-completion-resume-20261014-01a13cf9/calendar_source_use_review_increment30.md)分列來源、schema差異、授權與時間限制。歷史PIT、績效及正式writer資格均未接受。

### 雙市場 cohort 與正常 invocation









`daily_monthly_revenue_cohort.py` 把 caller 明列的必要市場、同報告期／source／parser／schema／單位／用途及時間政策封成 immutable pin。每市場綁 batch、manifest／receipt／canonical／transport SHA、接受錨點 identity/hash、record count及時間依據；共用可用小時取所有必要市場的較晚者。Builder只讀指定 batch，不掃描或選 latest；缺任一必要市場不可發行整組。保存 pin 為有界 canonical/create-only 格式，讀回要求外部預期 cohort hash；self-hash 不授信任。

Cohort reader 固定各市場 root／trusted acceptance 的副本，每次使用都重驗全部必要快照；即使只讀上市股票，另一必要市場原件被替換也拒絕。Current provider 拒 scalar pin繞過整組、錯 cohort／port及提前 cutoff，逐列仍按股票／市場／期間／版本／hash核對。正常 `RecommendationInputPreparer` 可由 composition 明示注入該 reader，在 session固定 pin與原 invocation時鐘；只供 natural current路徑，歷史／select-latest不借此轉為日常快照。推薦 context另保存同pin/hash和逐股實際讀取狀態，未讀／無pin不新增tag，unknown／missing／unavailable不升格。

合成雙市場writer／reader／provider／正常session已限定驗證，後續正常Main父29512→新PID33656也由同一外部配置重建實際reader／推薦input與context，18來源檔案不變。這不是完整推薦執行、真來源接受、更新批次組自動發行或Native／EXE接受。既有SelectionFundamentalReadSession的source clock v1仍是current-only/unknown，尚未接cohort identity／finish守衛，不改其狀態為PASS。重複全組讀回的operation級共用可再收斂，但不能省略所有必要市場或finish前的來源核驗。

### 正常 Main 的固定版本配置

`daily_monthly_revenue_cohort_binding.py` 的binding v1在cohort manifest之外保存明示pin root／hash、必要市場snapshot roots及既有typed用途接受錨點。外部應用設定以成對的 `MONTHLY_REVENUE_COHORT_BINDING_PATH`／`MONTHLY_REVENUE_COHORT_BINDING_SHA256` 固定binding原bytes；loader先核外部hash，再解析64KiB有界UTF-8 JSON及exact fields、accepted scope，讀exact pin並重驗所有必要快照。stat後仍只讀上限加一byte，增長不導致無界配置讀取。相對路徑、symlink／Windows reparse、frozen包內artifact或其來源root、缺市場／錨點、scope／hash不符皆拒絕；無成對配置時保持既有非cohort路由，不掃latest。

純serializer只將caller已有的pin/readers及接受錨點序列化，不建立或授予接受、也不寫正式配置。每日新版本選擇沿既有accepted source×use範圍驗批次，不重新人工接受來源；將新batch/pin/binding接到自動更新服務與正式日常配置，仍依原精確資料／Task授權逐步驗證。設定hash是caller的信任入口，不是官方來源、單位、幣別或歷史PIT的簽章。

月營收傳輸橋以 manifest v2 分開保存 HTTP 原件 bytes／SHA 與既有 UTF-8 canonical payload／版本 SHA，不能把 UTF-8-SIG 重編碼檔冒稱傳輸原件。嚴格解碼必須沿 HTTP charset 或原件 meta 明示的 charset；兩種宣告衝突、錯長度、未完成 body、未綁精確用途 endpoint／document chain 或完成時鐘不符皆拒絕。無 Content-Length 時必須有具名 EOF 證據；body-completion clock 不等於官方發布時間。舊 manifest v1 仍可讀，明示僅 canonical payload，不能補造原件。

`monthly_revenue_daily_snapshot_preparation.py` 先核對報表標題／市場／月份、明示千元、完整表尾、表頭與列寬、重複列及有限／缺值，再重用原 parser；目前拒絕巢狀來源資料表，不能推論任意 MOPS layout 已支援。分區範圍為 `source_report_rows`，不以已觀察列數宣稱全市場 universe 完整。候選保留 `TWD-thousand` 原值副本；既有 normalizer 以 Decimal 乘1000後才是 TWD。Snapshot record 的 TWD 是 consumer 單位，不含原始金額。新程序的 materialized 前期比較同樣受 pinned 成功批次小時及其自身晚觀測時間限制。

TWSE JSON 使用獨立 `monthly_revenue_openapi_preparation.py`／`twse.openapi.t187ap05_L` 版本，不套 MOPS normalizer 或 manifest。它核完整原件、HTTP／EOF／長度、UTF-8、唯一股票／期間、日期、有限且有界 Decimal、JSON 深度／列數；缺百分比保留原因。Date-only 的批次小時依同一 `daily-hour.v1` 向上取整，與單位未核／用途未接受分開。此版只供 shadow／diagnostics，保存原值、不換算 TWD、不給 scoring／排程／歷史 PIT 或完整市場資格。44合成案例與真 partial 拒絕已驗；10/13既有完整原件另唯讀解析2330／11509並由不同PID讀回相同結果，原候選時間政策和 bytes 不改。這些證據不等於新每日快照已發布或正常 UI 已接入，詳本輪 QA。

TWSE／TPEx／MOPS 可用官方 API 沿用。P03 的 [Scrapling](https://github.com/d4vinci/Scrapling) 僅補 session、browser 或動態頁需求，先以 task-owned venv 限縮驗證 MOPS 清單→對應文件→該版官方 timestamp；安裝成功或 HTTP 200 不能代替完整鏈。WAF、無法解析、錯文件、時間缺件與品質缺件逐項記錄。

### TWSE／TPEx OpenData 月營收雙市場 profile（current-only）

OpenData profile 與既有 MOPS profile 並列，不以 TPEx endpoint 名稱或資料語義將其改標為 MOPS。TWSE source identity 固定為 `twse.openapi.t187ap05_L`／`https://openapi.twse.com.tw/v1/opendata/t187ap05_L`；TPEx 固定為 `tpex.openapi.mopsfin_t187ap05_O`／`https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O`。兩者各自保留市場、endpoint、`twse-tpex-openapi-monthly-revenue-parser.v1`、`twse-tpex-openapi-monthly-revenue-14-fields.v1`、`fundamental_current_observations.monthly_revenue`、TWD及 `recommendation_current_fundamental` 的精確用途範圍。跨市場 source／endpoint、parser、schema、單位或用途混搭均拒絕；既有 MOPS source identity 與用途契約不因新增 profile 收緊或改寫。

OpenData 快照必須隨 manifest 保存實際 HTTP response body 與 transport capture。Capture 綁原始 request／response URL、HTTP status、未改寫的 Content-Type／Content-Encoding／Content-Length header、body bytes 與 SHA、收取 byte 數、EOF／完整性旗標，以及 body completion／observation end clock。JSON 依 RFC 8259 strict UTF-8 解碼；`decoding_basis` 明示 `rfc8259_utf8`，不冒稱 HTTP charset 或 HTML meta charset。Public reader 從保存的 transport 原件重新解析整批 JSON，核對 endpoint、schema、期間、所有列身分、raw SHA、版本時間及快照列；缺 transport、raw 漂移或只靠 manifest 自述均拒讀。

官方欄位的金額單位須以具名 unit proof 核實後才能轉為 TWD。Proof artifact 保存官方文件原始 bytes、原件 SHA、明確的 14 欄 field map bytes 與 SHA，並由外部 typed `DailySourceUseAcceptance.document_chain` 固定 proof SHA、artifact reference 與官方文件 URL；每次讀取都讀回並重驗 proof artifact 及其中文件／mapping bytes。單位證據、market、source ID、endpoint、金額欄位映射或接受範圍有任何不一致即拒絕。沒有精確且外部固定的 proof 時，只能保留候選中的來源數值與來源單位，不得推定千元、不乘1000或標示 TWD。Proof 本身不代表用途接受；`accepted_at` 僅取外部 Owner 建立的 typed acceptance，程式不自行產生或回填。

取得與批次完整驗證完成時刻以實際 response body completion／批次完成證據保存；沒有來源發布時刻時不推造官方時間，可用性依 `daily-hour.v1` 將成功批次完成時間向上取整，決策 cutoff 本身不取整。這是明示的 current-only 前瞻資料路徑；不得回填過去決策、歷史 PIT、績效或訓練資格，`historical_pit_eligible` 保持 false。缺少完整 PIT 歷史不阻擋已接受來源的新 current snapshot，但每次使用仍須通過來源接受、可用小時與當下 cutoff 守衛。

`publish_openapi_monthly_revenue_snapshot` 只接受 caller 提供的官方 capture、外部 typed用途接受、artifact 路徑及其可信 SHA，重新解析全批、套用已核 proof，再呼叫既有 immutable daily snapshot writer；不建立 acceptance 或 `accepted_at`。雙市場 cohort／binding 沿既有 serializer、reader 與精確 allowlist 同時固定 TWSE／TPEx 接受與 snapshot；必須完整讀回兩市場並在 cohort 可用小時之後才可供 current provider 使用，不能由 scalar pin、單市場快照或 latest 選擇繞過。合成驗證只證明受控 reader pipeline 可接入，不代表任何真來源已獲 Owner 接受或正式資料已寫入；目前不得宣稱 live formal acceptance。

成功鏈沿既有更新服務與 data ports 接入原件／版本保存、解析與品質、public reader、正常 UI 及新程序。資料工作不成為其他補完包的新前置；正式 root 寫入與 Task 變更依原精確授權。不得由隔離測試推論正式日常批次已運作。

### Selection opt-in V2 與 V1 wrapper 邊界（2026-10-14）

`SelectionFundamentalReadSession.open(..., daily_monthly_cohort_reader=reader)` 在SQLite connect前要求provider port是同一exact typed reader並核全部必要市場；同session固定full immutable pin。逐批呼既有provider pinned port，V2 row identity另含batch／first-persist，finish再驗所有市場及最後publication cancel gate。`cohort_hour_bound`只表示固定批次時間依據已綁定，缺列／unavailable仍保留，cutoff不向上取整，current-only／兩PITfalse不變。Clock常數與市場文字要求exact built-in型別，不能自造相等物件宣稱資格。

V2 batch／clock／finished token獨立版本；未opt-in時V1 bytes、hash、unknown與provider kwargs不變。現行V1 snapshot wrapper在batch及finish明確拒絕V2並close，不丟pin轉V1。完整V2 snapshot及月營收consumer進度見下方；正常UI與每日新批次自動配置仍待，沒有宣稱Selection全consumer已完成。Reader的verify_cohort只有呼叫前後的合作式取消檢查，未提供市場驗證內部中斷；不以thread或額外程序規避。

### 完整 V2 snapshot 保存與 exact reference（同日接續）

`FundamentalReadSnapshotSessionV2` 共用原 copy owner、WAL／SHM／來源 byte pin、單連結／reparse／formal-root 與 owner-thread 關閉守衛；公開 V2 clock／finished manifest／reference 保留完整 immutable cohort pin、各市場接受／raw／transport／manifest／receipt／時間／單位身分及全股票 ledger。complete manifest 寫出後須讀回 canonical 原件，finished token 與 reference 綁實際原件 SHA；reference decode 另需 caller 提供外部 SHA，不把 self-hash 當來源接受。

一般 open 與 exact open 均要求 provider port 為同一 exact daily reader。發布前再驗所有必要市場及取消；發布後讀 reference 仍重驗來源、root及市場 pin，但不再呼已完成操作的取消 callback。相對 formal `DATA_ROOT` 依共用 validator 正規化後檢查重疊。既有 live-state exact 重開新 copy 仍核原 DB／capture pins、cutoff、declared stocks 及完成 ledger；原 DB 漂移仍具名拒收。另有下節的獨立 V2 自含封存入口，不能自動退回該路徑或把來源 reference 降為 V1。

V1 public decoder／wrapper繼續拒V2；不跨schema重算identity或降格丟pin。Root原14個整合案例、原V1受影響回歸及真新PID24716→9700限定讀回已驗，15來源檔不變；新增無值清冊時間守衛後已由新PID51228重新綁定同保存來源，未重產製parent。原首輪FAIL／symlink權限SKIP保留，詳[本輪QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。

### 月營收 V2 consumer 與有界每日選版（同日接續）

#### V2 自含原件封存入口（2026-10-14 後續）

`FundamentalReadSnapshotSessionV2.archive_monthly_raw_sources()` 發行獨立 `fundamental-monthly-raw-source-archive.v2`。固定 layout 為 `<archive_id>/saved_snapshot/<original_snapshot_id>/` 與 `<archive_id>/monthly_source/`；前者保存 captured／reader SQLite及存在的sidecars、snapshot_capture、finished_source_clock、attempt_status完整樹，後者保存該clock全部HTML／CSV。原V2 reference／clock的邏輯路徑與歷史pin不改寫，實體位置另行精確映射；更正版本不覆寫舊目錄。

`open_exact_archived()` 必須明示原封存reference與外部SHA、cutoff、完整股票清冊及同一daily reader。驗外部SHA、canonical manifest、全樹bytes／SHA／單連結／reparse／protected roots、complete狀態與兩個完成ledger後，才發行私有V2 verified subject與copy binding。新operation從saved captured bytes複製，不讀mutable原DB／原HTML或已移開的原snapshot；finish重驗封存證據、全市場pin及原ordered ledger。V1 archive／snapshot參照不能當V2封存；既有live-state exact不自動fallback。完整daily市場root與trusted acceptance仍必要，沒有宣稱這些root也可消失。

此入口保持current_observed_only、cohort_hour_bound及兩PIT false；自洽DTO不等於來源接受。建立中取消或失敗可留下未完成目錄，沒有自動回傳或發布reference，讀者仍須完整外部錨點及全樹驗證；不擴權清理原件。已封存replay不再重新封存為另一原始來源。Root合成16548→新1924驗證Decimal／full pin／ledger與12原件不變，詳本輪QA。月營收consumer、ReferenceV3 artifact、recipe及收藏的明示archive lane仍待接入，正常UI原有精確重開資格不由此延伸。

`DailyMarketMonthlyRevenueReadSessionV2` 使用V2 snapshot的public open／exact open／batch／finish，Fact保留原typed provider結果、Decimal金額／role／當期與比較期／reason，以及per-stock result SHA與full cohort pin。獨立source kind固定 `daily_monthly_revenue_cohort`；完整finish重驗全declared stocks，provider五態counts與observed／unknown／blocked的fact counts分開保存，缺值不丟分母。全missing／unavailable也不能略過 `cohort_pin.available_hour <= cutoff`；V2 clock／fact／issuer／V3 reference各自檢查，cutoff不ceil。

`DailyMarketMonthlyRevenueSourceReferenceV3` 綁exact upstream V2 reference及其canonical bytes SHA、cutoff／codes、雙ledger／counts、內容identity和full pin；outer decode亦要求外部SHA且只回Unverified。只有exact重讀、逐項相等與完整finish能發reader-issued token。原ReferenceV2是V1 raw archive路徑，未改其schema或自動升級。

`select_daily_monthly_revenue_series_v1` 要求外部固定trust configuration SHA、固定雙市場root及用途接受、明示報告月、1–64個exact候選pins，及cutoff或完整雙市batch IDs二擇一。各候選重讀hash-addressed pin並重驗全市場，錯版本／scope／unit／缺市場／未來批次回具名有界diagnostics，不選壞版本；cutoff模式選共同可用小時內的確定版本。exact batch無fallback且cutoff=None，只綁批次，實際consumer仍必須以自身cutoff驗時間。選中reader／pin固定，舊session不refresh；限定既有MOPS／current recommendation／TWD用途，TWSE不借接受錨點。

Root合成contract／consumer／selector及真selected-reader→provider→SQLite保存已驗；986mypy與精度守衛通過，原100PASS／7FAIL及3typing FAIL保留，詳QA。原F17月營收正常頁面的V2查詢／比較／書籤、正式日常批次、來源接受、歷史PIT、Native／EXE與全Gate仍待。沒有新增抓取、正式Data寫入或Task變更。

### YoY V2 投影、每日外部設定及 BOM 原件（同日後續）

`project_selection_monthly_revenue_yoy_v2`只消費exact FactV2，重驗provider結果identity與full pin；current／comparator EvidenceV2保留原時鐘、來源／版本／Decimal、批次與first-persist。原28位 `(current - comparator) / comparator`、percent乘100、method及呼叫端門檻不變。缺基期、未核版本／revision、期間晚於決策日期、錯來源／單位及未來可用時間仍拒絕或unknown。`DailyMarketMonthlyRevenueYoyIndexSessionV2`先完成public月營收session與full declared清冊，保存來源與projected各自ledger/count，finish逐筆取消poll及重投影後才發Index；V3 exact reference外部SHA與完整pin不可省略。

`daily_monthly_revenue_series_binding`將固定來源接受與mutable每日選版分開。外部SHA錨定的canonical binding至多64KiB，pointer至多4KiB；pointer內SHA固定exact canonical catalog bytes（至多64KiB、1–64個排序唯一pin hashes、明示報告月），pin只從trust指定root精確讀取。損壞pin具名隔離，其他候選仍須完整重驗；catalog/root/外部hash損壞或全部候選不可用時拒絕，不掃latest、不以檔案mtime選版。`MONTHLY_REVENUE_SERIES_BINDING_PATH/SHA256`成對設定，和固定cohort設定互斥。bootstrap與begin沒有來源I/O；自然invocation首次月營收使用才按frozen cutoff選版，clone同配置provider並綁同一reader。一般Exception留下失敗終態，同session後續不重試或回落未釘選provider；歷史／重播／不符clock不選daily series。

Daily V2的HTML捕獲只在原bytes SHA與canonical來源SHA不同時允許一次UTF-8 BOM封裝。它保留原檔bytes/stat/SHA，確認exact市場／期間、cohort raw SHA、bounded regular/no-reparse檔與前後pin，且只移除前三個BOM bytes後hash相等。原件不重寫，CSV／來源version守衛仍執行；V1原HTML bytes hash拒絕不變。這不接受任意編碼／換行正規化，也不授歷史PIT或來源用途資格。

真正常Main input/context與publicIndex的合成新PID讀回37740→45128、30份來源／V3參照不變已驗；先前BOM拒絕與private harness API FAIL均保留。原F17頁面的V2 query、比較、recipe/bookmark仍待；正式資料發布／排程、真來源用途接受、歷史版本、Native／EXE與完整Gate不因本批PASS而完成。詳[本輪QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。

### F17／月營收 V2 雙來源保存與 exact 重開（同日後續）

`daily_market_technical_official_disposition_revenue_query_v2`與SourceV2使用獨立typed月營收IndexV2；原V1不改schema、不降格新pin。完整F17 declared母體先逐列合併、核兩套分母與硬篩選，再全域排序及分頁；OR不能救回被row scope／股票／市場／官方處置硬篩選排除的列。來源事實blocked／observed／unknown和投影observed／unknown各自保留完整分母。query／result／page綁外部reference SHA、內容identity、full cohort SHA及monthly `cohort_hour_bound`；F17整體仍current_only／availability unknown／official time None／PIT false，不把月營收hour當成官方公告coverage。

正常SourceV2先exact-open一份F17，再取得其原cutoff／完整codes，才呼每日factory並clone同配置provider。`daily_market_monthly_revenue_reference_artifact_v3`在明示隔離root建立兩個exclusive-create檔，原reference先保存、descriptor最後提交；重讀前後核原件bytes／stat／SHA、同issued index與完整參照值。descriptor本身需caller外部SHA，decoder仍只回Unverified；錯錨、缺件、版本漂移、alias／hardlink及取消拒收，失敗只清理本次已辨識的owned檔案。

SavedRecipeV2保存完整pin／V3內容／descriptor與條件頁碼；reopen另強制caller的descriptor與reference雙外部SHA，按原pin重建reader並exact重讀，不重選新版。`read_daily_monthly_revenue_series_exact_pin_v1`沿外部binding SHA固定的trust／roots核原hash-addressed pin與全市場，不讀mutable pointer／catalog；期限與原件缺失仍拒絕。正常series factory不得用作舊保存的latest替代。外層BookmarkV2將原descriptor／reference雙外部SHA獨立綁定保存recipe；原頁面與Watchlist走獨立typed路由。Fresh operation可以發行新reference／descriptor，必須先用原雙SHA精確讀回，再比穩定content／full pin／cutoff／codes與兩套ledger，不能用新SHA取代原讀回錨；recipe的自填hash不授來源接受。

SourceV2 ExactRead與IndexV2的建立、翻頁和關閉保持owner-thread守衛；原頁面V2已用RevenueSourceActorV2在同一長駐工作階段建立、使用與關閉來源；候選投影成功且取消檢查通過才替換。分頁使用同issued result而不改來源目前頁，UI收藏以同issued page／request／recipe保存，取消不讓收藏漂至未套用的頁面；提交後的成功仍按原token套用，shutdown合作收尾。原V1短命worker路徑保留，不撤除V2守衛。Exact-pin factory前後檢查取消，但factory內部讀取仍須完成才回應取消。限定合成public source／原件／實際新PID證據見本輪QA，不接受正式來源、歷史PIT、Native／EXE或完整Gate。

#### Increment 17：Monthly／Index V2 封存 exact lane（2026-10-14）

後續新增 `DailyMarketMonthlyRevenueReadSessionV2.open_exact_archived()` 與 `DailyMarketMonthlyRevenueYoyIndexSessionV2.open_exact_archived()`。兩者都要求 caller 分別提供來源 `SourceReferenceV3` 與 `FundamentalReadSnapshotRawArchiveReferenceV2` 的外部 SHA、原 cutoff、完整股票清冊、同一個已驗證 daily cohort reader；會交叉核對原 source reference 所綁的 snapshot reference／SHA、full cohort pin、cutoff、股票清冊、provider-result ledger 與 fact ledger。全 required markets 重驗通過後才以保存的 snapshot bytes 開啟，不掃描、不選 latest；任何缺件、漂移或 crossbind 不符均拒絕，不回落 live exact 或 V1。一般 live exact 仍只走其原 pinned-source 路徑，也不自動切換到 archive lane；caller 必須明確選擇其中一種。

`DailyMarketMonthlyRevenueArchiveReferenceArtifactV4` 的 envelope 自含原 `DescriptorV3`、`SourceReferenceV3` 與 `ArchiveReferenceV2` 的精確 bytes。V4 reader 解析後仍只提供 `Unverified` artifact；呼叫端的 descriptor、source reference、archive reference 外部 SHA 才是跨程序錨點。新 `ArchivedSavedRecipeV3` 保留原始 `SavedRecipeV2`、原 ArtifactV3／ReferenceV3 錨點及 ArchiveReferenceV2 錨點；`with_page()` 只更新頁碼與頁大小，不以重新簽發的新 ReferenceV3 取代原來源錨點。

Monthly／Index V2 僅在完整 session finish 後可呼叫 `archive_monthly_raw_sources()`；會把 ArchiveReferenceV2 與原 snapshot reference 交叉核對，已封存的 replay 不能再次冒充原始 archive。公開 `open_daily_market_technical_official_disposition_revenue_archived_bundle_source_v3()` 由原 F17 bundle 與已完成的 Monthly／Index V2 核心建立封存 recipe；`reopen_daily_market_technical_official_disposition_revenue_archived_from_recipe_v3()` 以三組外部錨點重讀 V4 與 ArchiveV2，沿原 F17 query／cutoff／完整母體重建 Monthly／Index V2，並以相同 pin、cutoff、source-content identity、完整股票清冊及雙 ledger 驗證新發行的 ReferenceV3。新 ReferenceV3 是本次 exact operation 的新 snapshot reference；recipe 與 V4 中的原始 ReferenceV3／ArtifactV3 仍維持 origin identity。因封存引用保存了完整原件，此路徑可在原 DB、原 HTML／CSV、原 snapshot 目錄或原 ArtifactV3 漂移／移走後重開；仍必須提供完整 daily roots 與可信用途接受錨點，不能把 archive 自述當作來源接受。

這條封存 lane 保持 `source_scope=current_only`、外層 `availability_status=unknown`、月營收自身 `cohort_hour_bound`，且 historical／formal PIT 均為 false；月營收批次小時不宣稱 F17 官方資料覆蓋。V1 reader／recipe 不 cast 或降格接 V2。Root 已確認 Monthly 8、Artifact V4 8、Recipe 5、Source V3 8 個限定測試通過；Source V3 native 雙 PID 以父 PID 55252→新 PID 9188 通過：同一 named job、原 120-phase／270-driver 範圍，terminal 與 handles 關閉後才啟動 fresh process。原 DB、raw、snapshot、ArtifactV3 路徑漂移後，完整 258 股票、雙 ledger、full pin、頁 1、Decimal `22.006875`、origin RecipeV3 與 source identity 均保持；fresh ReferenceV3 重發 SHA 不同，原三個外部錨點不變，14 個封存／V4 pair／daily 檔及原 320 個 F17 assets 不變。這是限定 backend 雙 PID 證據，不代表 UI／Watchlist 收藏、EXE 或整體 Gate 已驗；這些仍待。

後續正式樹已把此 lane 接入正常 Main 的月營收研究頁：Main 明示選擇 archived SourceV3 路徑，使用共用 owner-thread actor；收藏與 Watchlist 使用獨立 `ArchivedBookmarkV3` typed 路由，V1／V2 仍走原嚴格 live 路徑。保存根的完整 protected-root／重疊檢查先於建立三個 sibling 子目錄 `monthly-references.v3`、`raw-archives.v2`、`archive-references.v4`；binding source roots 僅由凍結設定中具外部 SHA 的 binding metadata 讀取，不追隨 mutable pointer。V3 exact source 只向 owner thread 提供明確型別 getters：`query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2`、`result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2`、`request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2`、`page: DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2`、`f17_query: DailyMarketTechnicalOfficialDispositionQueryV1`、`monthly_reference: DailyMarketMonthlyRevenueSourceReferenceV3`、`monthly_cohort_pin: DailyMonthlyRevenueCohortPin`、`artifact_descriptor: DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4`、`source_pair_identity_sha256: str`、`monthly_sqlite_connection_closed: bool`；另明示 `source_scope: Literal["current_only"]`、`availability_status: Literal["unknown"]`、`monthly_availability_status: Literal["cohort_hour_bound"]`、`historical_pit_eligible: Literal[False]`、`formal_pit_eligible: Literal[False]`。解碼所得 Unverified DTO 仍不構成來源資格。Bookmark3 以四個 caller 外部錨點綁定原月營收 reference、原 ArtifactV3 descriptor、ArchiveReferenceV2、封存 ArtifactV4 descriptor。

新增限定證據為 Bookmark3 9 PASS、archive storage 27 PASS／1 protected-reparse SKIP、Watchlist3 5 PASS，以及 standalone 真 archived UI 流程 1 PASS（44.49 秒）：完整 258 股票與原 1000 YoY 數值、跨頁收藏，並在 DB／raw 漂移且原 snapshot／ArtifactV3 移開後精確重開，actor 關閉。正常 Main/native/fresh 限定合成流程亦由 Root 記錄通過：父 PID 54640→fresh PID 32420，父／fresh source SHA 分別為 `960e1ea04c719afca56ef4a580d38cf191cc40ea58d9cf4aca2996841b089c7e`／`a126fed641ed15584a48a97de74a107b12445b2e381ca11ee779793c4abfb1f3`，外層收據 `a9fd1398409b0c14f8510c4ed6e7e0ba3f20a3417f24dbc859b8a5c7d2fc063d` 已閉鎖。26 個固定來源在父／fresh bytes、SHA、mtime 相同，原 320 個 F17 assets 不變；保存及實際個股分析按鈕重開後保留頁 1、258 股票、1128 與 origin Recipe3／四錨點。父程序關閉後，私有 DB／raw 被更正、原 snapshot 與 `monthly-references.v3` 移開、mutable series pointer 改壞，fresh 仍由固定 binding metadata roots 精確重開完整母體。原 phase／driver 期限未改，且自然結束、handles 關閉後才進 fresh phase。此為限定合成與保存／重開證據：正式來源用途接受、完整 Recommendation、PIT、EXE 及整體 Gate 仍未驗；mypy 1003 PASS 不代表 UI 強型別已完整驗證，既有 `ui_qt.*` `ignore_errors=True` 仍限制其證據力。
