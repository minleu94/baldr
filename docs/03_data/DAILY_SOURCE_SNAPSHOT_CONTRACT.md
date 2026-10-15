# 每日來源版本快照與小時可用性契約

本契約落實使用者於 2026-10-13（台北 10/14）採納的每日固定抓取政策，適用 P00／P03 的新保存來源及已接受的指定研究用途。施工順序仍由[原產品補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md#95-資料阻塞分流與下一批交付2026-10-14-調整)管理，實際驗證看[本輪 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。本頁不授正式資料寫入、排程變更、歷史回補或交易。

## 時間與版本

保存版本對應的官方發布／更新時間原文及解析結果，統一 `Asia/Taipei`。UTC 或其他 aware 時間可轉換；naive 時間須拒絕。會計期末、資料基準日期及其他版本的更新時間不能充當發布時間。

`available_hour = max(ceil_hour(official_version_timestamp), ceil_hour(successful_batch_completed_at))`。14:45 只能在 15:00 使用，整點不變。缺官方發布小時時只用成功批次完成小時，明示批次時間依據；不能填造官方時間。成功完成必須包含完整保存與品質驗證，部分成功、尚未保存及失敗批次不可供決策。Consumer 使用原 aware decision cutoff 比較，不向上取整 cutoff。

每份快照綁 source／dataset／市場／股票／資料期間、parser／schema／單位、官方時間原文、batch identity／開始與成功完成時間、首次保存時間、原件 hash、版本及快照 hash。更正另存新版本，舊原件與 manifest 不覆寫；相同版本衝突拒絕。研究保存與重開必須釘相同批次與版本，不自動換成 latest。

## 一次性接受與每日驗證

來源與用途接受紀錄綁官方 endpoint／document chain、source／dataset／market、parser／schema／單位、時間政策、授權範圍與具名接受證據。日常研究、歷史回測及績效資格分別接受。相同契約無變更時，成功批次沿原用途接受；來源、parser、schema 或用途改變才重做受影響範圍。

每日批次核對原件／snapshot hash、來源與版本、批次成功與完整性、股票／市場／期間、單位與有限值、缺值及用途必要的前期；時間因果仍不可放寬。失敗保存具體原因與原件於隔離候選中，不發布半批為完整母體，不補 0。Reader 重新核對同一份 batch validation receipt 及指定用途；共用收據不能跳過錯來源／錯版本／未來資料的拒絕。

首次成功保存後可建立前瞻可用性，缺完整歷史 PIT 不永久阻擋已驗證新快照的日常研究。首次取得日前的歷史決策仍須當時版本證據；本次取得的舊財報不能倒填成舊日可用。Forward label、Paper 成交與估值、自然成熟及正式來源資格沿各自原契約。

## 目前實作邊界

`data_module/daily_source_snapshot.py` 目前先支援既有 MOPS 月營收 v1／v2 的 hash-bound 版本，沿 Recommendation current-fundamental reader 的明確 `pinned_daily_batch_id` 接入。Reader 必須由 caller 提供可信用途接受錨點，與 manifest 完整比對；快照不能以自述接受紀錄授權自己。無 pin 的既有 caller 保留原資格，指定 pin 卻缺 port／版本時拒絕或排除，不混入 latest。其他資料的政策已定，ports／producer 接入仍依工作包逐項驗證。

收據持久化逐列 `available_hour`／basis，public reader 依固定時間政策重算核對。原件與 pending receipt 寫入後 `flush`／`fsync` 並關閉，再取得完成時鐘樣本；跨小時或超過發布 guard 的批次保存 raw／原因並隔離。若樣本恰整點而後面仍需發布寫入，採具名下一小時 publication guard，保留原樣本，不能冒充該整點已完成發布。這個保守發布限制不改官方原文時間，也不把 decision cutoff 向上取整。

保存為 create-only staging→批次目錄，成功版本不覆寫。中斷 staging 不自動重用同一 batch id，失敗改用新的 batch id 並保留隔離原件與原因；reader 不讀 staging／quarantine。這輪驗證檔案關閉／fsync、原子可見性與程序重開，未驗 OS crash 的目錄 metadata durability。正常 UI／更新服務／正式排程與來源接受仍按[本輪 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)的實際範圍判讀。

`.receipt.pending.json` 保留至發布後時鐘核驗通過；public reader 在讀前及投影完成後都拒絕帶 pending barrier 的批次。發布後時鐘失效、隔離目標碰撞／搬移失敗或 barrier 無法移除時，不得接受已 rename 的成功收據。完整 capture 的失敗隔離使用 quarantine v2，分開保存 canonical／HTTP body、hash、metadata 與比對結果；其 self-hash 不是信任錨點。沒有 capture 仍保留 v1 格式，壞 capture 不偽裝為完整傳輸證據；保存可用 canonical 原件並保留主拒絕及次級封存錯誤。

`app_module/monthly_revenue_daily_snapshot_update.py` 與 `UpdateService.save_daily_monthly_revenue_capture` 已提供明確 root／scope／接受錨點／batch 的保存入口，經 preparation、既有 Decimal normalizer、immutable writer，再以新 FileReader 精確讀回。唯讀狀態不選 latest、不改舊 CSV 或正式 SQLite。保存前及最後 rename 前有合作式取消 checkpoint；不聲稱取消與 rename 之間具原子保證。晚 materialization 的本機觀測守衛保留，provider 的可用時間取原觀測可用時間與 batch hour 的較晚者，不倒退到較早批次。雙市場 cohort pin、正常更新 UI／推薦 session 及真來源接受仍待接線驗證。

## 取得與接入

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
