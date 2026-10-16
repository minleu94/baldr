# Baldr 每日快照政策與 P03 隔離驗證（2026-10-14 UTC）

本輪依使用者決議恢復[原補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)，不另立總計畫。本輪跨使用者時區10/13–14；各收據原UTC時間保留。完整 P00–P14／G0–G4 尚未接受，舊 FAIL、P08 私有候選與其他 owner 的 singleton 保留。

## Increment64：P07W底正常回測與當次訊號保存

**解除的交付阻礙**：Increment63只有可執行核心，正常清單無入口，也沒有當次訊號保存／pure規則讀回。本輪沿原StrategyRegistry、BacktestService、ResearchRun／VersionService接回原單股／歷史／返回／fresh；不另造撮合、金融公式或儲存。原§5.3幾何／進出場假說不改，新增明示numeric metadata與獨立`single-backtest-w-bottom-execution.v1`。起始HEAD `ad05644841b73533ae5cf4f63a060a8f074fcd12`，固定0f644faa預覽與V1四旅程不替換。

- 原selector與規則卡呈現W底1.0.0、等待5／10／20列；當次frame只讀測試窗一次，`prior_rows=0`且不帶訓練段幾何／episode。保存原spec／effective rules、逐日close／ready／signal／state／兩谷與頸線證據、runtime、Broker config、input fingerprint及9個source-file hash，不套BB上下軌／180日指標context或generic50分。
- pure reader核known schema、strategy／version／params／fingerprint／來源集合、兩谷／頸線原值、右一列確認日、意圖episode、實際窗與qualification；不借current Registry或executor重建。來源hash識別檔案，未對照目前工作樹作歷史資格，也不是官方權威／PIT證明。原baseline v1、兩策略v2與布林schema保持；目前1.0.0 reader在未來改版前仍須保留具名版本分支。
- service／wrapper在載入前拒close、加碼與ATR停損停利；service與reconciliation均不授研究版正式晉升，即使SOP回true或樣本達10亦拒絕。原Broker的next-open、股數／成本、零量／停牌／漲跌停／未成交守衛維持，W意圖episode不是已成交持倉；無固定持有期限或虛構期末平倉。
- peer指出metadata builder可接受獨立錯params及source finalize取消空窗，Root另核requested/actual期間。以原11FAIL重現後，新增W專屬比對：identity／股票／策略參數、原本金、所有Broker輸入與requested/actual bounds，錯配拒存；metadata按實際窗、原請求留raw_params，缺費率不補0。來源回填report前再查取消。其他schema的metadata口徑不在此改寫，舊run原件不遷移。

| QA | 限定結果與原FAIL | outer SHA-256 |
|---|---|---|
| 379 | 路由／context：6來源7628字／12232bytes；新reader未自動擷取、部分heading-only由Root讀正文，無關推薦tests仍unknown | `bc06756c8503c4e4910e24cf08c41936a62717824471afa04b785b59ab15c712` |
| 380 | compile12；因果／新保存與受改舊schema／promotion217PASS；UI102含Workbench85、八roots mypy1042／validator25 PASS、0 FAIL、4 protected skips及原float guard | `102756fab351a3ae5d844eff32a07763862fff7ae55a9ab75d1ff32fb785d4f7` |
| 381 | peer收尾修正前Main33856→fresh29472正常保存／原規則／返回限定PASS，原證據保留，不代替後續最終source | `a931fb883a4a981bed4a7d45fd73b937c349a4a8723dd1a1d10949d029e37cc0` |
| 382 | 9項獨立錯輸入、1項最後source讀取後取消、1項實際窗被請求窗覆蓋，共11個原FAIL保留；未降低斷言 | `15ef8d39f1ca383a0fd97908e55135d12570796055d33c60512caa2cebdd6a71` |
| 383 | 修後compile、受改核心／保存／舊schema及原promotion228PASS；UI102含85、八roots mypy1042與validator25/0/4，原11案恢復PASS | `97492a7c33f8f560394d200bc370fc0fbfd790fb3df8adfd310181bda51bf02e` |
| 384 | 最終Main39460→fresh45296，保存前畫面等待20→5仍讀當次20；獨立query-only SQLite核419列原訊號／指標，來源及20試用輸入不變 | `6f57fe2319a8c763589d65119189eee4ed7a344fc0a19f88ca14529078b761fa` |

最終Main使用原四股副本的2317／2025-01-02至2026-09-23，正常選策略／規則／執行／原保存對話框，再明選pending保存版本1.0.1的來源run（執行器仍1.0.0），開規則／原結果／Watchlist返回及fresh。fresh禁止create/update版本、save run、目前Registry metadata／executor及重算，仍同run／規則／419日原結果；原Registry、附件、JSON bytes／SHA／mtime／ctime不變，Python socket零。實際保存419觀測／346可判讀／73不可判讀、10個進場意圖／10出場意圖與10組完成配對；不是勝率／策略有效性或歷史PIT接受，原metrics只原樣保存。獨立收據SHA `be201de219d29a15b2861fad96a29fb4bc4ca111298f1befff9c3dced06685d7`。

以上各組單一Job8GiB／12程序／kill-on-close／workspace mutex串行，啟動RAM至少8GiB，三PID清冊自然空且handles／鎖關閉；15秒UI／120秒phase／270秒driver不改。mypy既有UI ignore不證強型別。這是source正常單股旅程，不授批次／參數研究／Walk-forward、完整形態家族／雙策略績效、來源用途／歷史PIT、Native／EXE、真人或自然成熟，完整P00–P14／G0–G4仍未接受。指南同步實際入口、參數、保存前改設定、期間與排錯；下一葉沿原P03必要財報／前期比較，先核既有capture／reader及attempt帳本，不盲重抓MOPS／重設舊額度。

## Increment63：P07W底因果可執行核心與確認日

**解除的交付阻礙**：原P07形態家族只有全段圖形原料，整段極值／平均ATR與缺值填補不能直接作逐日可知策略；第二谷`end_idx`也不是可觀測確認日。本輪Root在原計畫§5.3定版自有`baldr_w_bottom_basic_v1@1.0.0`完整入出場假說，實作固定契約、純Decimal因果核心與StrategyExecutor；原圖形辨識不改。這是通往正常入口的必要核心，尚未登記selector、接保存／Main／fresh，不能列成已完成的使用者功能或P07 Gate。起始HEAD `76a4359068fe5b7c1a1e23d34f6bee4df67c99d7`，固定0f644faa預覽與V1四旅程不改。

- 三點收盤谷於右一列確認，只取相鄰兩谷、3–20列間距、第一谷前5列跌勢；兩谷差以第一谷5%為基準，頸線取中間最高收盤且須嚴格高兩谷1%。候選保留首組，前後收盤跨過凍結頸線才發一次意圖；5／10／20列等待含期限邊界，低於floor／超期先失效，當列不重建進場。
- 進場意圖episode固定頸線，後日跌回才發出場意圖，不自認成交或持倉；原Broker零量、漲跌停、下一有效開盤、資金／lot與未成交政策保持。缺OHLC清候選／暖機，已有episode保留原頸線但不造當日訊號；測試窗前不帶入幾何、候選或episode。無固定持有期或強制期末平倉。
- 原價轉Decimal後只用整數乘法／比較，60位context隔離呼叫者精度；28位價格／小數12位邊界有正指數反例。內核只保留27列，不使用全段`find_peaks`、`bfill`、ATR或未來極值。逐列證據含兩谷日／價、頸線日／價、第二谷確認日、原因／狀態與當日訊號；這些目前尚未沿正常Registry保存，不冒稱immutable證據。
- 重用同一Luna靜態peer，核心未發現阻斷；其提醒`unavailable`含暖機／重啟及上游float精度不可還原，Root記入架構與後續producer驗收。來源單位／availability、歷史PIT與績效資格仍未接受；沒有正式資料／版本、Task、maintainer或網路操作。

| QA | 限定結果 | outer SHA-256 |
|---|---|---|
| 374 | 原kind路由及context；4來源6592字／11196bytes，pattern/contracts簽名超預算由Root讀原正文，未相關推薦tests仍unknown，不宣稱重跑 | `0868702af13b106db545a1fa36b84f859cfcfdc2e5b025b81e6d54f3f73a8dcf` |
| 375 | compile四檔；新因果／原Broker共72PASS，八roots mypy1041及原金融float邊界檢查；後者白名單不單獨證新核心 | `8676706bfedcaa7d134fd5082087c315111b0f121d81e9f191061e3e2c7833ec` |
| 376 | 明確修正正指數表達邊界後，compile及核心／原Broker74PASS，新增三來源裸float AST反例與1E27／1E28，三來源mypy通過 | `2f45a3f70bcc7e95176aa26ab6e06d5ee7d93c4a10daf88a754b3f5d2964014a` |
| 377 | 補peer已成交持倉延續至期末不強制賣出、1E-12接受端點；Root另將Decimal rounding／exponent／traps改為固定獨立context，受改核心／原Broker76PASS、compile及三來源mypy通過 | `d5c6ad2e263ee547f0d5bd75052698ea07c5c3be858b338e769fb47924cfecb2` |

反例包括每個prefix／未來追加、確認日不回標、幾何無突破、平台／同價頸線、谷距2／3／20／21、不可略過中間谷、5%與1%邊界、首候選不替換、期限／floor、OHLC缺值、episode不等於成交、測試窗清狀態、日期及OHLC拒絕、spec漂移、輸入與caller precision／rounding／exponent limits／flags不變。已成交未平倉只估值，不虛構期末出售；與末列待執行訊號無成交是兩個案例。等待敏感度只保存合成訊號數0／1／1，不選最高績效。所有組均由Root單一Job8GiB／12程序／mutex串行執行，三PID陣列自然空且handles／mutex關閉。

未改UI／原註冊及shared ports，本輪不重跑未受影響Workbench／validator／Main，也不借舊PASS授本W底正常旅程。下一步在原P07接當次producer／規則與訊號source binding、selector、保存／返回／fresh及研究資格拒絕；Native／EXE、完整家族／雙策略績效、來源權威／PIT與自然成熟仍各自保留。指南明列未開放狀態，原完整範圍與舊FAIL原件維持。

## Increment62：P07布林基礎研究策略正常執行與訊號保存

**解除的交付阻礙**：P07布林家族只有當日「收盤高於上軌」filter，沒有具名進出場、可執行StrategySpec與正常保存訊號出口。本輪由Root在原計畫§5.2定版自有`baldr_bollinger_basic_v1@1.0.0`研究假說，沿原Registry／selector／Broker／保存與歷史規則卡完成基礎版，不把filter-only或unknown卡片當完整策略，也不冒稱進階壓縮／VCP／共振。起始HEAD `9a473df66a8280db0c131a7cb6cfae40dec1f166`；固定0f644faa預覽與四條V1範圍不改。

- 固定沿既有causal BBANDS30/2/SMA分析邊界，Decimal比較首次由前列<=上軌至當列>上軌；連續1／2／3列確認日才發一次進場意圖，收盤<中軌發出場意圖。缺OHLC不補值、重新暖機；拒重複／逆序／盤中／含時區日期及缺成交股數。executor不自認成交、買賣成本與股數不另造公式，訊號與完成配對分開。
- 首輪peer指出直接executor有prefix，正常producer卻只載測試窗。Root補通單次只讀前180曆日、最多31筆prior觀測，實際trim後完整frame納入fingerprint；test_start重設確認／持倉，裁切後才撮合、計績效與保存訊號。缺少足夠prior仍重暖機，不把觀測列當完整官方日曆。
- 新`single-backtest-bollinger-execution.v1`保存原spec／effective rules、每個測試日的close／bands／ready／signal／意圖理由、input_context與分析套件版本；十個源碼hash包括原指標、executor、producer、Broker、fill policy與金融units。原baseline v1／兩策略v2不換版；pure reader只核保存來源，不查現在Registry或重跑。SHA是識別，不是來源權威或歷史availability接受。
- 原next_open、漲跌停／零量／資金／lot／cost與原風控保留；close／加碼／ATR等未核路由在載入前拒絕。UI只顯可用／不可用與進出場意圖日數，不製造分數／門檻。研究版另阻擋SOP單項或直接Registry正式晉升；PIT／performance資格旗標變True的反例均拒絕。

| QA | 限定結果與原FAIL | outer SHA-256 |
|---|---|---|
| 365 | compile成功，22PASS／2fixture FAIL保留：未來樣本close1生成Low0被原OHLC守衛拒、trade-list實用中文欄；修fixture，不放寬原守衛 | `4cb4e08f6899ad390d39a3077a9be7a4fc5a6f7653ff264fa1a265ef871cd9d5` |
| 366 | 92PASS／1fixture FAIL保留：誤把進場意圖後第一開盤當必成交；原嚴格漲停拒前兩開盤，第三有效開盤才成交。原守衛保留，另加明示無limit的相反例 | `eb109f6ca46f2aae0122813e4f092505a5d822b890f996772cfb15a653a47661` |
| 367 | 因果／保存及舊策略規則94PASS；UI96含Workbench85、八roots mypy1038／validator25 PASS、0 FAIL、4 protected skips | `c9d3a76578188dc82e86154b0afd4b9bec2ad6aa49d205baea991bb225bea1c0` |
| 368 | prefix修正前Main／fresh有限旅程PASS，原收據保留，不能替代後續正常窗前暖機驗證 | `7d97423e99353c64bdee22f12986ab99f3df9c56c9996450da6fb80ca154c064` |
| 369 | peer prefix修正後核心102PASS、UI96含85／mypy1038／validator25/0/4；Main21024→25548原419日保存／規則／結果／返回／fresh | `44d9427da6513be73ba9866f49bdf4665454abd03416f78aea1c0f4423933cf5` |
| 370 | 研究資格與原promotion補償54PASS，五個受改核心mypy通過；SOP can_promote=true仍不授新研究策略晉升 | `2ef26997dd93774c38f8eaadc84e35d0ebef4dbe92454ef8a278ee609ba5f07a` |
| 371 | 最終來源Main13180→fresh33308，再核禁用晉升；performance／input-context兩案PASS，獨立query-only SQLite讀回實際保存訊號／原metrics | `8fa8c0ee51135b3f37cb3f0756f8ad2cc7e1541ca407238c43560736615ca0dd` |

最終Main沿原四股副本正常選新策略／看原規則／執行／保存，改目前確認日數後明選原run與pending保存聲明1.0.1，重開原1.0.0規則／419日結果、Watchlist返回及fresh。新程序禁止現在Registry metadata／executor、回測、save_run和版本create/update；同run、版本／規則卡、JSON／DB／Parquet bytes／SHA／mtime／ctime一致，原20試用輸入及市場副本不變、Python socket0。每UI階段15秒、phase120秒／driver270秒，真PID／named Job守衛保留；這是offscreen工程QA，不是Native真人或同版EXE。

獨立保存讀回 `increment62_actual_signal_readback.json` SHA `7b0f4ef30cda37725126f2438091932d2105dcfa618dd36e1ce0fd1d195146a1` 以本次private DB的原hash與`mode=ro/query_only`核實419列、31筆窗前觀測、十個來源hash、原訊號日期及metrics，DB原bytes不變。這些是該固定副本／期間的實際研究結果，不授策略有效性、成本權威或historical PIT。1／2／3確認對一次假突破的敏感度fixture分別1／0／0進場意圖；原樣保存於pytest隔離根，不挑最好績效或以此要求調低門檻。

該份實際保存為389列指標可用、30列未達可用條件（含重暖機）、15個進場意圖及6組已完成配對；原returns等metrics照存，不重算或與其他策略合計。意圖／成交限制／完成配對及研究資格仍分開，缺件沒有補0。

Root單寫金融規格、共用ports、整合／QA／文件；只重用同一Luna做presenter＋新測試葉片及靜態peer，原handoff SHA／三份note和採納處置保存本owner，累計10/10、無新agent／children或worker Python。每組啟動RAM≥8GiB、8GiB committed／12程序／KOC／workspace mutex；前組三PID陣列空、handles關閉／mutex釋放才續組，未終止他人程序或用強制清場當成功。UI mypy既有ignore仍不證強型別；新核心未新增ignore。

文件閉鎖QA372核九份正文／12features及metadata31來源，errors=[]；outer SHA `03bb3b26aafded8a1fac5576d072ef0d00eb7f6d9576f67906441915ccdb2c4f`。Context實讀4來源6592字元11196bytes，無關推薦測試預算略過、兩個新檔因未提交不自動擷取；Root另直接讀完新executor／reader並由Luna靜態peer核對，不把Context略過算已讀或重跑無關測試。

完整策略家族、進階壓縮／形態／VCP／族群／共振、其他回測模式／OOS／Walk-forward、來源完整文件／單位版本／用途與歷史PIT、真N、完整雙策略績效、Native／EXE與自然成熟仍各自待。無正式資料／版本寫入、無新增行情或官方資料抓取（僅唯讀官方概念文件查證）、正式Task／maintainer變更、push、發布或交易。下一葉回原P07形態的確認時間與完整規格；固定試用入口不變，完整Gate保持未接受。

## Increment61：P07/P08版本新建保留前版與失敗補償

**解除的交付阻礙**：原版本建立器的秒級ID與`os.replace`可覆寫前版，固定`.tmp.json`會互相截斷且被catalog讀取；Registry回填成功後若evidence失敗，原補償還會刪掉已引用版本。這些會破壞原保存／重開旅程，沿原服務窄修，不另造儲存層、策略或V1前置。來源HEAD `caf82ce01e51e045a2edf8de9d650c5c7be71137`；所有QA只寫本owner隔離目錄，正式版本、舊task／原spec與固定0f644faa預覽保留。

- 新建ID保留時間前綴並加UUID；explicit ID核安全basename，碰撞拒絕且原bytes／mtime／ctime不變。私有exclusive `.tmp`完整flush/fsync後採Windows rename／其他平台hard-link create-only發布；不吞flush錯誤、不overwrite fallback。只清本次成功建立暫存，清理OSError記log而不遮蔽原錯誤／已發布結果。Windows分支實測，其他平台分支只靜態核對既有專案模式，未宣稱跨平台QA。
- catalog只列檔名與payload ID一致的JSON；舊暫存原件保留，明確update仍是既有可變聲明。不是不可變歷史版本庫，不遷移或自動修復舊檔。
- promotion回填／evidence失敗時讀回exact backlink：已回填或狀態未知保留版本，僅確認未引用才補償本次新建；待核對狀態由既有掃描列出。狀態寫入也失敗時保留原錯誤／JSON與log，不能僅靠`synced`判evidence完整。沒有跨store transaction、自動重試／修復或門檻放寬。舊fallback callers在mark失敗後的孤兒行為未擴修。

| QA | 原結果與限定驗證 | outer SHA-256 |
|---|---|---|
| 359 | 原建立器四個反例全FAIL：同秒碰撞、explicit覆寫、未發布誤列、flush失敗仍發布；原失敗保留 | `e60dfddb63b1cdbe15d70b0afbeb6fce325d3766e97ebdaf063795ed5a6e8488` |
| 360 | 新建完整性16PASS；原caller的evidence失敗／commit後拋錯兩案FAIL，均留下backlink指缺檔；保留原斷言後修產品 | `c116799d9c453db3bc5b2d57c2f5e0d44032cf11e36f2ed0f60966bcfa312416` |
| 361 | compile、受影響核心／保存roundtrip／promotion／原規則reader79PASS；八roots mypy1035通過，既有UI ignore不證強型別 | `f5cb0e4a00eea9391025e931c14e6ed68352870657648d4f63f957e59d883307` |
| 362 | 原Main38168→fresh45408兩既有策略新自動ID明選、原規則／原結果與返回；原15秒UI／120秒phase／270秒driver不變 | `3e72970dc74e57f02bc6e480c6c979230442f93053a86572d9bb49ce25d50edb` |
| 363 | peer清理例外三案與受影響lifecycle守衛47PASS、compile與兩服務mypy通過；不重跑未受影響UI | `d997d147bfc425734cefac543502adf933eeb30a325ea22248723e7fbff07cab` |

QA362沿原四股只讀副本正常執行／保存兩個1.0.0策略，QA版本聲明僅pending的1.9.3／2.7.1，不走promotion、不用低門檻fixture取得資格。新程序禁止目前Registry／executor、回測、save_run及版本create/update；同run、規則卡、原419日曲線、JSON／DB／Parquet bytes／SHA／mtime／ctime一致，市場副本與20試用輸入不變，Python socket0。其後peer只補清理錯誤分支，QA363定向驗證；正常旅程不外推為金融權威、Native／EXE或真人接受。

文件閉鎖QA364核七份正文／12features、context metadata31來源，errors=[]；outer `single_owned_qa_1507bea8fd7740aabf5e518df9c57518/receipt.json` SHA `d93efa46c2ca012f9cf4b410c32331b707aea9f2f89c5749b289d4db6448b5d7`，三PID陣列空、handles關閉／mutex釋放。其後只加本收據註記與owner交接，不重跑未受影響runtime；原始stdout／收據與當次SHA另留本owner，結構核驗不替代Root正文複核。

Root單寫產品、測試、QA與文件，重用同一Luna靜態peer（累計10/10、無新agent／children）；原note與採納處置保存於owner。QA361 Context實讀4來源6592字元11196bytes，預算略過兩服務的AST與無關推薦測試；兩服務另直接讀完整正文，無關推薦測試不宣稱已重驗。每組8GiB committed／12程序／KOC／同workspace mutex、啟動RAM≥8GiB，前組三PID陣列空／handles關閉／mutex釋放才起下組；各組自然關閉、無強制清場成功。

指南同步保存碰撞／失敗與待核對狀態，feature map補回兩原服務與測試關聯；UI、金融公式、來源／PIT／成本／lifecycle資格與V1四條旅程不改。原P03完整文件／單位版本、來源用途與歷史PIT、真N、完整策略家族／雙策略績效、同版Native／EXE及自然成熟仍各自待；下一葉回原P07具名策略規則與訊號出口，不再擴張保存前置。未寫正式資料、無新HTTP、正式Task／maintainer變更、push、發布或交易；完整Gate保持未接受。

## Increment60：P07保存策略版本明選與來源研究

**解除的交付阻礙**：原VersionService有保存／exact讀回，正常回測畫面卻只能選目前Registry策略，沒有明選保存版本並回原run的出口。本輪沿原service／歷史reader／SavedRuleCard與結果dialog接通，不新增策略、writer、promotion、金融公式或第一版前置。固定0f644faa預覽、4b530窄版與舊結果保留；本增量尚未建Native／EXE。

Root保留新reader、public exact metadata selector、取消／預算透傳、Backtest整合、QA與文件單寫；只重用同一Luna靜態定位／兩個widget葉片與peer。原handoff兩檔SHA及pending=false另存`increment60_worker_handoff.json`，Root接回後補分頁；累計10/10，沒有新agent／子代理或worker Python。

- 保存生命週期版本與source run執行器版本分開；promotion config是來源摘要，不作原StrategySpec。只核原策略／params、來源種類／run、parameter contract／data fingerprint／execution／sizing及既有backlink，不把當前Registry或版本聲明當資格。
- `ResearchHistoryLookup.select_registry_run`按單run選取，原resolve保持metadata／context／artifact守衛。版本canonical聲明在列出、開啟及讀回後重核，漂移拒絕；不掃latest、不重寫版本或來源。此hash非歷史不可變／權威接受證明。
- 清單沿原service排序分頁，每頁200，可正常到較早版本；沒有要求使用者挑原檔。peer指出research_forward屬metadata-only卻會先啟用按鈕，Root已在列表階段保留診斷／source=None，反例通過。
- widget與Main共享原source reader、原結果callback及規則dialog；換選、取消、owner execution generation及關閉不套舊回覆，原窗口等待native worker收尾。

| QA | 限定結果與原FAIL | outer SHA-256 |
|---|---|---|
| 353 | 角色路由與context3來源5853字元／10457bytes，unverified_unknown=[]；不作功能或來源接受 | `7bdfb77f8b12118688c2dab187379e73e594b5859a498e1a4c35fd16e83fd70c` |
| 354 | compile、真版本服務／Registry與受改原reader100PASS，mypy3；兩原策略v2無current Registry／executor讀回 | `9446f8dfb594c566b73e0bcbf3d4c82c5455117baacabf552ad226e5f97e38ce` |
| 355 | widget／原規則UI／版本binding及Workbench123PASS含85；八roots mypy1035／validator25PASS、0FAIL、4protected skips | `45a85fbcd0c0a3c7d0c128915ccf29d2c108c181d655597a82c3d1ed52293a18` |
| 356–357 | 分頁／metadata-only與UI109PASS／1新fixture FAIL保留：兩個promoted_at實際皆2026-10-15T18:05:29.175351，測試誤認先後create必不同。保留原排序斷言，明示fixture下一秒後該案PASS；未重跑已PASS109案。mypy1035／validator25/0/4及原Main旅程另通過 | 356 `d7af8758cdd3d6be9534f1b40037357bcf5322d203615261c9aa8bd77653d376`；357 `d8f241751a79d31f7a03a6c292b8ca774be4c0409622639ef72343f04287e64b` |

正常Main父 **34996→fresh9400**：以原四股私人副本，兩個原策略真正執行／保存後，沿原writer另存明示pending QA版本1.9.3／2.7.1，來源執行版仍1.0.0。正常明選→原規則→419日原結果→Watchlist返回→新程序重開，完整版本聲明SHA、run／card身份、Registry／Parquet／版本JSON的bytes／SHA／mtime／ctime相同；20原V1輸入與原行情不變，socket0。fresh禁止回測、save、create/update version及目前Registry／executor；沒有執行promotion，QA pending不能當真人策略或完整雙策略績效。UI15秒／phase120秒／driver270秒保持。

各組8GiB committed／12程序／KOC／workspace mutex，起前RAM≥8GiB，前組三PID陣列自然空、handles關閉／mutex釋放才續組；原FAIL與原spec留在本owner。既有UI mypy ignore不證強型別。靜態peer原件及Root處置在`increment60_peer_disposition.json`，新直接取消回歸與文件核驗結果以owner最新具名收據／integrity核對，不加總成Gate。

原完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4、策略家族定義／逐日prefix、來源權威／歷史PIT、真N、完整雙策略／自然成熟／Native／EXE與真人接受仍待。下一葉優先隔離證實既有秒級version_id及replace的覆寫風險，沒有改正式版本、Task、maintainer、HTTP scope、push／發布或交易；unknown卡片仍不算完整功能。

## Increment59：試用回報固定候選與同版出口

**解除的交付阻礙**：58只有source，且正常視窗查出四股按使用者順序輸入會被核心拒絕；57兩策略v2規則封存還缺EXE可讀的原始來源。本輪只補原UI集合正規化與打包來源，交獨立後續開發預覽，不新增V1旅程或資料前置，不修改策略、費率、風控或SOP。Root履行Execution／Tech Lead／QA／Documentation，重用既有Luna靜態複核，累計10/10、pending writes=false。

固定來源`0f644faa0d48417fa21d7c05c59b965cd06fc884`，archive SHA `2881c025a91886cbea32b1e96299873f26876fbc64c76b1f5f9d248b49eb42c8`。候選`dist/candidate_0f644faa0d48_5a011727/baldr/baldr.exe`為56,210,840 bytes，SHA `d88d9ee9e6097bb0cdcb77bc8f9d209848ab3d1e0a32a05c80adaf4ababc5b99`；入口`output/trial/Baldr-Feedback-Preview-59/Launch-Baldr.cmd`。此包包含先前第二階段增量，原4b530窄版、9fa、50ddb、ed422中間候選及active_delivery不覆寫，build receipt的built_not_validated不回填為PASS；驗證另存收據。

- 原spec四份執行來源新增兩executor與metadata wrapper，metadata按AST literal宣告完整加入三hash；舊spec與註解路徑不冒稱。實際包中七份回測來源及原兩份technical kernels逐一核對export／resource hash，固定export未修改。
- `_parse_stock_filter`通過原格式／重複檢查後排序才送既有query；後端仍拒未排序集合，沒有放寬來源／時間／精度守衛。新回歸以真保存來源驗任意順序、同來源結果及重複拒絕；舊9fa／4b530手動輸入須用`2317,2330,2382,2454`，原指南未發現這項缺陷的紀錄保留。
- 正常Windows Native來源 **6260→5452**、同版EXE **47952→42772**：原四股來源查詢／strict載入／使用者四碼套用、2330原價格／缺方向說明、空QA帳持倉表位置／進階切換／返回，兩原1.0.0策略正常執行／保存對話框／歷史規則卡／原結果／Watchlist返回／fresh。每策略419日，5.5%停損／15%停利核原精確比例與舊整數投影；保存後改目前門檻，fresh禁止目前Registry／executor／回測／保存，仍讀原run。每runtime內原件bytes／hash／mtime／ctime不變，兩runtime的金融內容hash與規則投影一致；不跨不同run偽比全metadata身份。
- UI操作沿15秒、phase120秒／driver270秒；實際windows平台、曝光／祖先裁切／Qt命中／Win32點位PID與named Job／creation-time守衛。QA窗口明示置頂以避免其他程式遮蔽，只擷取該窗口；沒有終止其他owner程序。這是原生自動化，非真人／跨機接受。

| QA | 真正結果與原FAIL |
|---|---|
| 338–340 | 338原相關63PASS／六個新fixture漏mandatory icon FAIL保留；補fixture後六案PASS及mypy1033。peer的文字搜尋誤認宣告問題改AST後compile／packaging27PASS與mypy1；舊四來源行為保留。 |
| 341–345 | ed422中間包建成，342／343按鈕被其他前景窗口遮住FAIL；344證實點位PID屬其他程式，未kill。345只置頂QA窗口後持倉順序通過，catalog因harness將extended-prefix路徑交config而FAIL。原helpers／specs／收據保留，每次有具體修因而非盲重跑。 |
| 346–348 | plain技術root恢復catalog及四股strict載入，346暴露真UI未排序filter FAIL；347真來源回歸RED保留。修UI排序後348 compile2、價格widget＋必跑Workbench共99PASS、八roots mypy1033、validator25PASS／0FAIL／4protected skips。既有UI ignore_errors不證UI強型別。 |
| 349 | 新commit另建固定候選，不在ed422 export補檔或覆寫舊包。outer SHA `3c2c867d6d47f5300dd16ca46db8551f8460819425e47d0e290dcdc330d13593`。 |
| 350 | 固定來源Native正常旅程／保存／返回／fresh通過；outer SHA `3dc976cd5c4a3a0073d2b26be05e8fc486db7464f67e5dac9c96f695b816d5fc`。 |
| 351 | 同版EXE上述旅程及原verify_same_version的archive／依賴鎖／共同啟動與journey/model/H20隔離probe通過；outer SHA `9cc71e012249cdf1a9990b382d378b0d91e0aaf8742a4a5ac23338f647d8e640`。共同probe不等於所有UI／金融功能接受。 |

新入口六份行情副本另存，7,098檔bundle清冊保留；技術研究仍唯讀引用20原輸入的原身份根。新output／Registry／LOCALAPPDATA空白，沒有搬使用者持倉或研究紀錄。交付準備曾誤把全部Python resources當七份（另有兩原technical kernels），該assert失敗另存，保留已產清冊、改以七回測＋二技術明確分組核對，未重建包或降低原來源守衛。

各組起前RAM≥8GiB、8GiB committed／12程序／KOC／workspace mutex，三PID清冊自然空、process／Job handles關閉及mutex釋放才續組。338起全部原FAIL與收據在本owner task具名保留；未重跑未改市場／觀察清單journey，也不加總案例當Gate。個股漲跌缺方向屬D品質仍不可用，使用者0交易所在區塊／run尚未證實，原摘要六配對SOPFAIL保留；原完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4、官方權威／用途／歷史PIT、真N、完整雙策略績效與自然成熟繼續。沒有正式資料／Task／maintainer、新HTTP、push、發布或交易，後續回原產品包，不把長tab重排擴成第一版前置。

## Increment58：試用回報與持倉表前移

**解除的操作阻礙**：9fa試用指南省略「查詢版本」，使用者無法選價格研究來源；持倉表被健康區塊推至下方。本輪Root保留原補完工作，僅重用一名Luna做有限靜態定位及Portfolio單寫，Root接回金融裁定、整合、QA與文件；累計10/10，沒有新建agent。持倉新要求不擴V1四流程，source修補尚未打入固定9fa／4b530／50ddb包。

- 真正 `manual_account_panel` 全寬接四卡／活躍摘要後；上方 `portfolio_focus_summary`、原手動交易操作列及分帳可見性不改。健康與詳細頁保留進階，Root修切換時操作列須主動刷新方向；不是搬摘要冒充表格。
- 價格研究改人類可辨標題、單一來源批次與股票代碼篩選；三步指引仍要求原strict核驗，不自動產製或下載。舊版立即操作是「查詢版本→選四股保存批次→嚴格核驗並載入→篩代碼／套用條件→選結果」，指南原漏步驟已補。整個長tab重排明列後續具體方案，未聲稱已重做。
- QA331唯讀原四股行情私人副本：方向欄 `漲跌(+/-)` 存在，12,390列中11,378列為 `missing_change_direction`；最近六列均空白，2330在2026/09/23價差40而無方向。原prepare85逐行原bytes→文字SQLite，沒有從收盤推算或修寫方向。本輪只補表格下方缺件說明；沒有宣稱正式DB或使用者目前執行output已全面查核。
- 貼出的回測摘要明列6完成配對，1–9樣本不足及無WF均符合原守衛。使用者所見0屬哪個區塊／run仍未證實，不改原結果或門檻；高損益金額也未擅自判為本金錯誤。Worker舊guide混版推論由Root disposition拒收，不能當現況事實。

| QA | 真正結果與原FAIL | owner outer receipt／SHA |
|---|---|---|
| 331 | compile audit、四股唯讀原值及完整性；v2正向saved source status四案PASS。文件因Root誤列不存在test失敗保留，移除錯關聯，未改測試強度；metadata檢查當組未執行。 | `single_owned_qa_d00db7583db3405b9e46e6a1dc8040a3/receipt.json`／`56ec906888af5680e6f019763601cab913955ae72b4f1c77c8e5b576480ce5bc` |
| 332–333 | compile5、Portfolio／price widget／stock report／Workbench193PASS含85，原1280進階動作列方向1FAIL保留。333改寬度判斷仍同1FAIL、87PASS，未放寬斷言或重造測試。 | 332 `single_owned_qa_44400952b7dc440094ec9bbb95f8f584/receipt.json`／`75d142329bbd4beb16c747c0efda4b18d3bf19151206c0b1a1aa1160c54852e1`；333 `single_owned_qa_223e862d48dd41a59e9d5b2809b7b901/receipt.json`／`65d9a85f25e15b35b0b99d6fc5650bd547c6223df162e5eafbdb776c6fd6e059` |
| 334–335 | 334測得window1280、view1072、持倉表1034，切進階未更新方向，force才變直列；Root改切換顯式刷新。335原可達性／寬窄／順序及Workbench共88PASS；mypy因v2成本兩loop同名int／optional變數FAIL，保留後只改局部名稱。 | 334 `single_owned_qa_250b13e560604467bbb846324b209110/receipt.json`／`39cae5a2a09a05e9cdfd7d27fd3dd0f57fbab233e0ff6ddad6b20de86765f32a`；335 `single_owned_qa_c68078ebb1034aafacdef3f3dd4160b7/receipt.json`／`df878f971ac1decc6f6b65530c5ff9f2968a629edbf6abd20ddb4f32429d20a2` |
| 336 | compile1、八roots mypy1033與先前跳過的validator25PASS／0FAIL／4protected skips通過；不重跑未受影響的股票／價格結果。既有UI ignore_errors不證UI強型別。 | `single_owned_qa_2c2122ede3e14a6b93d28570e48c33a5/receipt.json`／`7481e77c2568d6695d8bee29c22c9619f5729c1a97acdef41ff4b37ed62435a0` |

Root disposition `increment58_peer_disposition.json` SHA `cb783b397042078aaab0d57a1e46d0308822ebf0270a696edf85b93d4ef57700`；原audit `increment58_price_change_audit.json` 留own task。QA331只排除正由Luna寫且與該audit／v2／文件無關的兩個Portfolio pins，332重新綁回當前完整source及結果隔離目錄，沒有以舊spec覆寫或當新QA。每組仍8GiB／12程序／KOC／mutex、起前RAM≥8GiB，三PID陣列自然空、handles及mutex閉鎖才續組。沒有正式資料／Task／maintainer／HTTP／push／發布／交易，也沒有本增量Native／EXE或完整Gate。

## Increment57：P07/P08原兩策略的當次規則封存

**解除的交付阻礙**：原穩健／暴衝策略已能執行保存，歷史規則卡尚缺當次完整執行來源。本輪沿原typed執行器／service／broker／Registry新增fixed next_open的v2捕獲與讀回，不造新策略、撮合器或金融結果；baseline v1及舊run不改、不補章。原完整範圍與固定4b530 V1／50ddb開發EXE保留，這兩個包均尚未含本增量。

來源HEAD `e06a6e6f32ca1c5e550e5866b9365c163a108ddc`。producer只載一次行情，保留原request與equity/trades；metadata一次捕獲，門檻沿ScoreThresholdPolicy真值，另綁五具名來源hash。reader交叉核spec／metadata／資料／執行／成本，qualification兩個False不得被True／1／None替換。Luna靜態複核發現舊pct_to_bp其實ratio*100 HALF_UP而非真bp，Root保留DTO，改核精確broker/raw_params與舊整數投影；非整百分比不能用舊整數反推。未改原金融計算、參數或風控。

| QA | 結果與界線 | owner outer receipt／SHA |
|---|---|---|
| 325–326 | context三來源無budget unknown；trace因FeatureMap缺關聯exit2，保留並補原工作區關聯。原v1／B07／saved讀回105PASS、mypy1033。 | 326 `single_owned_qa_a64785f1eeb745e6aac8dff96e647275/receipt.json`／`0c8b3cb33e44eb63b2666fb6c16e5de1d78d60d07451cb44532a396e522e11ad` |
| 327–328 | compile5；127PASS含Workbench85、兩個完整DTO比較FAIL保留。原Registry把Decimal JSON葉轉精確字串，沿原metadata_sha256契約核完整DTO後定向兩案PASS；八roots mypy1033、validator25/0/4。 | 327 `single_owned_qa_18037be6086f4399930cb6ae8800e643/receipt.json`／`2aeeef9b5189032c722305ed5bd7b943c2277ca0f9bb54141570f8d86829109c`；328 `single_owned_qa_ceb053ad4a034400a9bfb9a4ac216aaf/receipt.json`／`3a91404cfa58ad49176f431d39dd78824a3c9b4c8a443e533c61fa9173a0ba28` |
| 329 | 正常Main38512→fresh36480兩策略各原419日、正常保存對話框／歷史規則卡／原結果／Watchlist返回；保存後改目前門檻99仍讀原0，fresh禁止目前Registry／executor／回測／save。DB／Parquet內容、bytes／mtime／ctime一致，20原V1輸入及私人原行情不變，socket0。 | `single_owned_qa_5d5acb64252342d59f0c891a31d28b90/receipt.json`／`1e1e56172eabd3b0fcd54704c18ad4c859c46692e51f81ccbc4a641e3c78c427` |
| 330 | peer非零風控單位阻礙窄修後compile2、受改core／saved／v2 UI44PASS，含None／0／0.05／0.055、錯整數與錯原比例反例；原FAIL與前收據不覆寫。 | `single_owned_qa_0144705dc64447d78c43684604ee958d/receipt.json`／`636d7986eba094c00609a2325f50b8077b6b5a83375ba863fbcd06ca76bd27b3` |

QA329父收據SHA `a28716a8a2ef9fa507cf20961f2aede32b66fe3e4f15283354fb8ce1dbb8621a`、fresh `75053166d5024d6882b0afd127b3326ea02328f9345d12b1cac4f041c3f80029`，路徑在owner `increment57_fixed_rule_main_fresh_a/`。原15秒UI／120秒phase／270秒driver、8GiB committed／12程序／KOC／mutex均保持，各組三PID陣列自然空、handles與mutex閉鎖。QA330後可用RAM22.19GiB。靜態Luna重用，累計10/10，沒有新建子代理。

**限制**：Main使用原四股私人副本，未授官方來源／歷史PIT、完整雙策略績效、Native／EXE或真人接受；原executor準備缺值有bfill／fill0，有限完整OHLCV的prefix不代表所有缺值因果安全。quantile／其他版本與非next_open不偽造v2，舊run保持原資格。沒有正式資料／Task／maintainer、新HTTP、push、發布或交易。使用者同時回報的9fa試用操作缺陷另由一名Luna處理，不阻擋原產品線推進；各有限PASS不加總成完整Gate。

## Increment56：P12決策擷取終態與正常系統狀態

解除原P12「通用passed字串被視為成功、原終態／階段診斷未接回正常頁」的操作阻礙。沿既有 `run_scheduled_decision_evidence_capture` 寫入契約與 `decision_snapshot_diagnostics`，新增application唯讀adapter，供原Runtime排程service與Workbench共同消費；原producer、正式Task、120秒child期限與30秒狀態輪詢未改。固定4b530四流程V1與50ddb開發EXE均不改版，不新增試用前置。

latest／receipt各1MiB、子stream各64KiB，核同run／schema／完整payload／canonical路徑／SHA／bytes及start≤complete≤觀測時鐘，沿regular-file／no-follow／hardlink／reparse與取消、讀後重驗。只有完整已核passed才計正常；已知child啟動前失敗可核其失敗終態，啟動後原件pending拒驗。snapshot保存或duplicate未知保留None；Workbench與正常「系統狀態→日常排程→決策證據擷取→詳細」保留失敗／timeout語意，只顯安全原因碼、固定階段、整數耗時與例外類型，私訊不進DTO。receipt不穩定綁data_root，故核驗只證執行原件一致，不證DB寫入、資料來源／歷史PIT／金融結果或自然成熟。

Root凍結共用API並整合，重用三名既有Luna靜態協作，累計10/10、無新增agent／子代理或worker Python。peer發現Runtime先通用無界read與Workbench遺漏prelaunch None失敗，Root已改成lane先分流有界reader及保留失敗／未知，超限反例與原prelaunch案例定向驗證。service無新cancel參數，reader保留ambient與顯式callback檢查；不能宣稱新增整個Runtime取消UI。

| QA | 實際限定結果與處置 | 具名outer receipt／SHA256 |
|---|---|---|
| 309–313 | 309只context／原producer trace；310 compile11通過，22 fixture因Windows長路徑發布失敗／33PASS。311短owner根30PASS／7FAIL：固定producer時鐘未同步reservation時鐘，原截止守衛阻擋。312單元時鐘同步後2PASS／5FAIL；313中性路徑仍5FAIL，定位新增test誤把安全例外類型當私訊。保留原金融／來源／期限守衛，修新test核固定reason:type且排除原例外訊息，所有FAIL原件不覆寫。 | 各原spec、log、receipt保存在本owner task，另存`increment56_qa_ledger.json`逐組SHA；不把這些失敗算通過。 |
| 314 | 五prelaunch反例PASS；Runtime／Workbench／composition共100PASS含必跑Workbench85；原13Main整合fixture缺現行初始化依賴FAIL。 | `single_owned_qa_018e5c2515bb4f38a774d34eabb1b1f6/receipt.json`／`ada8d457fe7ea16183f14cef56d4b3a0f87af571135a045075882b1bd8934985` |
| 315／316 | 315新reader12型別錯FAIL；316以顯式同型守衛收斂，原拒絕碼不改，compile／八roots mypy1033／validator25PASS、0FAIL、4protected skips通過。Main helper錯認bootstrap root而FAIL；未重跑已PASS UI，既有ui_qt ignore不證UI強型別。 | 316 `single_owned_qa_a3c3be71d90644f59de405e48bb1843b/receipt.json`／`328053143134cdba68c007a053f92e653129973a99e84ce79727974d6485fc9a` |
| 317／318 | 317受改reader16PASS；舊Main dummy缺現行推薦/cohort掛載13FAIL。318正常Main helper自設1024寬超過offscreen800螢幕而FAIL；原件保留，沒有冒稱1024／Native成功。 | 317 `single_owned_qa_d0af046eaaa34a6d90c758492a206dcc/receipt.json`／`b834086c717d8e9fe4e36b5833fe10a3cb5a1ff40a0189b35d7153a2017ce9a6` |
| 319 | 新隔離c沿既有640px可見座標命中、15秒UI／120秒phase／270秒driver，正常Main48720→fresh30816同run終態／詳細／切頁返回／重開通過；9原件內容與時間一致、Python socket0。 | `single_owned_qa_0608235c7ec546ae9a7d1717fa084a0a/receipt.json`／`fc61b9632ca82b3923e039cff2e121cdc1a6c7053ce9b812ca393b7a0a9ad1a2` |
| 320／321 | 320原Main dummy仍缺cohort reload／四signal協定13FAIL；321補完整fixture協定後compile與13PASS。原七頁順序及lazy loading守衛保留，expected新增現行第八研究母體盤勢及widget identity斷言，未改產品或遮蔽cohort接線。 | 321 `single_owned_qa_dcf9ad4fcf37495881decf1906919731/receipt.json`／`3a7c8291b5a27da1df8a23f86692851ad3f53caefb31b4e2e7b9c14151eb0ae0` |
| 322／323 | 322十文件／context metadata治理通過；Root最後複核把terminal限原producer十種值，避免published／completed借其他lane成功分類。323 compile2、reader／兩consumer40PASS含三個雙檔改hash反例及原timeout／prelaunch／取消／損毀／未知守衛，八roots mypy1033通過；未改UI／validator／Main沿前述收據。 | 323 `single_owned_qa_2b1f91b82ee648d6a6164b8912d4af80/receipt.json`／`39dbd8e5b93b16663c453f62a3aa6b643a43be03613daeb98c814c4e3f635719` |

QA319使用原context／artifact／finalizer保存合成成功與timeout事件，writer採真時鐘；保存舊run收據不變，fresh禁止run／create／persist／finalize。latest run為`20261015T235732260100Z-02765e88148e`，immutable receipt SHA為`892e5de85690c03257bea8daf0bb357569f8f7ebcf091b66fc55d2429aa3a71b`；parent收據SHA `93e94b57d42caa4877b710762b3974c6b1d7e6a59c41b4ff3af46bf1bf0f7f41`、fresh `68965d60f631ae2826263fa259d8ea088530bc0d1d46951d30fa8898ed024333`。這是隔離來源版offscreen自動化，未實跑120秒timeout、完整DB snapshot、依賴慢／效能原因、Native／EXE、真人、正式Task或自然run；P12原關閉條件仍保留。

原計畫§0.3／§9.5、Snapshot、架構、Feature Map／UI、手冊§11、指南章節地圖與排程運維同步。每組仍起前RAM≥8GiB、8GiB committed／12程序／KOC／同workspace mutex，三PID陣列自然空且handles／mutex閉鎖後才續組，沒有強制清場成功。無HTTP、正式資料／Task寫入、maintainer觸發、push／發布或交易；未受影響QA沿原收據，不相加宣稱Gate。

## Increment55：P13/P14固定候選Native與同版出口

**解除的交付阻礙**：第二階段法人用途與P06 Registry已有來源版正常Main證據，尚未確認實際固定EXE能走同一保存／讀回／返回流程。本輪不另造產品實作，只沿原build_windows／verify_same_version與兩個原旅程，固定commit另建候選並補Windows原生自動化。第一版4b530四流程包、原dist/baldr、active_delivery與原失敗／資料全部保留；這兩個出口不加入V1試用前置。

固定來源為50ddb6401238850f4c782f0d99494341d28ffc66，archive SHA為17cec1bfce8dd8847bb89e167d59a09a5a6e4b769be8312b3d9d744c63d62324；候選dist/candidate_50ddb6401238_9dfeb5e8/baldr/baldr.exe為56,188,224 bytes，SHA為84a14003fa9f1de5ae2856c950b6b66c1d469856b4218b9005c983b9c768c033。owner另存increment55_candidate_build_pin.json，SHA 528b57a5bde03a4426899a3f2a87d09d6f93fbf6ef320cbefd128c436d5a991a，原build receipt的built_not_validated保持，後續驗證用獨立收據描述，不回寫建置原件。沒有產品Python變更，故不重跑未受影響的Workbench／mypy；兩份Root新QA協調腳本已各compile。

Root履行QA／Tech Lead／Documentation，重用原Luna靜態核packaging與P06輸入，沒有新增agent（累計10/10）。Job均沿8GiB committed／12程序／kill-on-close／workspace mutex，每組啟動前至少8GiB可用，前組三PID陣列空、process／Job handles關閉、mutex釋放才續組。原15秒UI、120秒phase與270秒旅程driver未放寬，實際PID／creation time／named Job核驗及terminal等待保留；無跨owner程序終止。

| QA | 限定結果 | outer receipt SHA-256 |
|---|---|---|
| 302 | release角色路由與固定來源獨立建置通過；只是built，不授Gate | 75f34cfceea66af2fcbef6b7c6f018ddf2ebbf06853bfc466ffb5d20efd829ba |
| 303 | 真TPEx Native來源34120→44196，compile／三證券／返回／fresh通過 | a8cfe4504d0c3bd322dc5a60f786528ca5648f0bde9febaec1292d369a9a9b33 |
| 304 | 同版真TPEx Native EXE45356→14056，同原件與接受身份通過 | 959f469cb4969b9198a56a808646e967f1a34723a7b29d5edc100a36e0fcd11d |
| 305 | 原P06合成Native來源10664→42836，compile／明確登錄／exact Registry／個股返回／fresh通過 | 0a65d615a426b7695b991e94b2e4fa2393741bb5c5439a1fcd5734090fb50c65 |
| 306 | 同版P06 Native EXE33288→9400，禁止重算及fresh寫入，原金融投影／身份重開通過 | 412da39c03389bd622385526f1529b9be1d1e7907a45eb196a56a0ad15caa2dc |
| 307 | 原verify_same_version的完整archive／依賴鎖／根路徑／共同啟動與journey/model/H20隔離比較通過 | fc2ce14050e5e5a9d78a45c0e0ecd7c1c9b7c82b78e09ef9dc28896f7abe5b00 |

QA303–306用實際windows Qt平台、可見曝光／祖先裁切／QApplication命中與Win32 WindowFromPoint的PID守衛，沿既有Qt滑鼠事件操作；EXE從實際candidate啟動，關鍵產品模組必須來自其_internal，來源版必須來自固定archive，移除checkout／tests import路徑。這是原生自動化，不是人工滑鼠、真人接受、完整啟動UX或其他解析度／主機驗收。法人控制仍明選路徑／SHA，P06部分輸入及tab／股票還原沿原QA控制器，未宣稱全操作皆真人逐鍵。

法人使用原真898列及四文件接受，不新抓、不重seal或重寫接受；三證券6488／8069／00679B九原整數、來源版本／雙SHA、07:00資料小時與07:18:53接受時間／顯名跨source／EXE相同，12資料與用途檔bytes／SHA／mtime／ctime不變，Python socket零嘗試。只接受TPEx diagnostics，candidate_only仍true、P0整桶與歷史PIT false，連買／評分／交易保持不可用。

P06重用Increment47原合成封存，不重算金融引擎或append情境；parent僅明確登錄且重試同一entry，fresh封鎖登錄／引用append。7份隔離副本與原receipt21來源分別核驗不變；每組parent/fresh的scenario DB、Registry DB、reference SHA相同，source／EXE的artifact／comparison／stock projection相同。不同runtime各自登錄時間不同，因此不要求跨runtime Registry DB／引用SHA相同。原現金399884.98、NAV501884.98、2330數量1000／mark102／估值102000.00等投影未改，手動帳fallback禁止；實按原個股返回按鈕。這不授真帳本或缺現金／同來源Health／行情的manual/user_declared初次來源。

共同probe原收據output/qa/baldr_same_version_50ddb6401238_46214878/same_version_receipt.json，SHA 99e7feaee272e2ba37a2cbbc5f5f4ae5ff46cc49592f1777b5a80d43cf518b75，status passed_isolated_fixture；包含中文／空格設定與原錯設定拒絕，沿合成市場／模型，不證真模型與自然排程。空法人／P06隔離市場仍有companies.csv／SQLite缺件warning，沒有用正式DB補值。本輪無新HTTP、正式資料寫入、正式Task變更、maintainer啟用、push或發布。

手冊與原計畫§0.3／§9.5同步；候選使用邊界見[可攜指南](../07_guides/PORTABLE_WINDOWS.md#後續開發候選的限定驗證)。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4保留，限定Native不能抵銷真來源、PIT、真N、完整績效、真人與自然成熟。下一葉接原P12受控terminal→status reader→正常系統狀態出口，不觸發正式Task或maintainer。
## Increment54：P00/P03法人精確來源用途與每日驗證分離

**解除的操作阻礙**：新TPEx每日原件已可檢視，但缺少能精確保存／重用指定端點用途的正常入口。Root沿既有DailySourceUseScope／DailySourceUseAcceptance及同daily-hour核心，另存固定文件版本的diagnostics用途artifact；正常法人頁明選path／外部SHA，原daily reader再驗每天的原件、schema、合計、股數及成功小時。不把此契約轉成generic institutional_flows的limited決議，不改P0 v1 payload／hash、13來源分母或既有機器maturity／coverage守衛；歷史PIT／真N與完整F09仍各自未完成。這是第二階段，不增加固定4b530四流程試用前置。

Root依現行角色另履行Tech Lead／Data Audit／整合／QA／文件單寫，重用三既有Luna靜態工作，累計10/10，沒有新agent／子代理。peer定位曾提出clock可回填的條件風險，Root補真保存started_at下限並新增反例；同時仍不可早於必要metadata真收據。UI葉保留原三參數signal、immutable requested pin、generation／取消／shutdown，slot只在非None傳新kw，相容舊service stub；裸True、錯市場或scope拒絕，資格只由Root public reader返回。

政府[授權條款第1版](https://data.gov.tw/license)已單次完整HTTP200／EOF，484470bytes／SHA `f36301ecb6ba3ac2cac5b820276e3fd2d4c7d12755afa1f49bf5379d6b3ce3f2`。官方[metadata11856](https://data.gov.tw/api/v2/rest/dataset/11856)本次4205bytes／SHA `b807cf7f19d04f19ff6e445463ac86e9380d85d0fadc880e482563dfd518fe5f`，完整EOF且Content-Length相等。metadata含先前web inaccessible累計第2次，本scope只增1次、總上限2，禁止盲重試。原資料集526503bytes及Swagger476923bytes沿Increment53，不重抓資料API或既耗月營收／TWSE／MOPS scope。metadata確認A45020000D-000309／上櫃股票三大法人買賣明細資訊、license1／free與官方OAS連結；原metadata的http授權連結與本次直取https條款分別保留，不改原文。CSV25欄／resourceAmount839與API20欄／真898列差異明示，不推真N或缺少自營分項。

新精確scope固定TPEx／shares／tpex-openapi-3insti-daily.v1／diagnostics，官方GET operation＋resolved schema canonical SHA `efda72f09eeea74a135dd63afd9c8fbc926d3464e9ba658144c7ab7d58f4e3cc`，機器識別不虛構human reviewer或法律同意。四原件固定fingerprint、copy另存、canonical接受檔、外部SHA、pending／failure、fsync／讀回、reparse／hardlink／讀取中變更與取消守衛保持。讀取只用相同契約，不每日重寫接受；變版或用途不同才重核，原件不改。

| QA | 限定結果 | outer receipt／SHA256 |
|---|---|---|
| 290／291 | 290誤把domain當kind，route未知而FAIL、context未執；291按現行registry用implementation，Root另DataAudit／TechLead。data_pipeline Level2讀4來源7050字元／11559bytes，daily guide headings_only；Root僅另核當前法人相關段，不宣告全舊指南已讀。 | 290 `single_owned_qa_807c5e9676db4e588c9cdbc032baf2c0/receipt.json`／`13494853605b48bc7f241b8fd84244da3993ca18ce8bde729c88fb4ca8335f86`；291 `single_owned_qa_2e24759bdf6d4508bc51b26aba2d60f8/receipt.json`／`ea1b1a7a3b5ddbb6ef30d93327c603cb19d20a8f23a92f488a5af10bbbdb7ade` |
| 292 | 原有界HTTP工具，兩個指定官方文件各1次、20秒／8MiB／無retry／redirect，原件與worker／Job終態完整。 | `single_owned_qa_962ded89a3c5460c81959a77b2315394/receipt.json`／`09e14fb290846369cb340eb75a882e12dd4570b7ec4da16803d82ce224c522e5` |
| 293／294 | 293 helper誤用Swagger2 response.schema而FAIL；294依真OpenAPI3 content.$ref解析同components，四文件與身分／版本／20字串schema／CSV25欄差異核驗通過，無HTTP。 | 293 `single_owned_qa_06bceada5ceb47a39de79d84a61d6628/receipt.json`／`906bd93052ea5d18187aa2678cf1b26c75a93cf8675fa0710acea08b201cc786`；294 `single_owned_qa_d44929fa9e054d80ba65f99f2a1c3200/receipt.json`／`cba05c724c4d8c55174ffb6d418e687ef330ddf90c21c117fa9470de8b7d71a4` |
| 295／296 | 295 compile8，173PASS含Workbench85／受改daily／新舊UI，2FAIL保留：壞用途fixture先被共用DTO擋而未到reader、final recheck變更誤差型別。296直接損壞wire保留同斷言，公開錯誤轉接後兩反例PASS；mypy1032另3個object→int型別FAIL，validator未執。 | 295 `single_owned_qa_86c730ac8067431b967a60a4b9fc740a/receipt.json`／`ea881b6e27d83285f585b7c0c0484a9dcad08840abacf2c02bd5b5d93cba9e4f`；296 `single_owned_qa_e8700d42dcb74538bca63ea90b4dbc89/receipt.json`／`db6095801859a530252f6efefdeaf06189dbd21175567637003da13a614d55f1` |
| 297 | DocumentPolicy改TypedDict，peer回填風險補真started_at下限；只重驗受改writer19PASS，mypy1032、validator25PASS／0FAIL／4protected skips通過，不重跑未改Workbench。既有ui_qt ignore不證UI強型別。 | `single_owned_qa_5275d805bb9948958cd0a747535fd5cc/receipt.json`／`f4ad89b4a3425319ead8a4dc4ec04680a3f70013f39eafad9fad8006f802a4ab` |
| 298／299 | 298正常CLI真四文件create-only接受保存通過；Root read helper把socket class換function使ssl import FAIL。299沿既有connect／DNS／sendto guard修helper，只讀已存接受與原daily，同三證券九原值／接受前cutoff拒／舊TWSE拒TPEx，12檔不變；不重做成功producer。 | 298 `single_owned_qa_da9d76fd56c44d71a4bfd52f297490f5/receipt.json`／`8ef6885ad3e9201b9b275af00a620bb4a278a73d19c448a54a9b500ca02f834b`；299 `single_owned_qa_73d5a2c3db62439fadb4ff39f803aeee/receipt.json`／`497daa92cd74fd5d23475cd4ed7377cf423f3336a5712fdbc7393707049d321e` |
| 300 | 正常Main36096→fresh47452明選原898批次＋同一用途pin；6488／8069／00679B九原整數、接受ID／SHA／07:18:53／顯名及切頁返回／重開一致。12檔bytes／SHA／mtime／ctime不變；禁止HTTP／capture／seal／接受重寫，無未來clock。 | `single_owned_qa_95234d74a4e345029c5e94f8318f4453/receipt.json`／`773b9fb763576b73d203056439cf87cbac1952288d12da6e5a3ba2fd5f3c1daa` |

本次真接受時間為台北2026-10-16 **07:18:53.078273**，接受檔 SHA `b9dc0d4b99615a93c53aa9c6ad75f501786bac361d2294a28410f7cd6e3fff83`；早於它的cutoff拒絕，不回填資格。原每日可用時間仍07:00，原first-persisted／receipt及九數值不改，qualified只增typed source_use與source_use_accepted=True／diagnostics。candidate_only=True／historical_pit_eligible=False，未給formal來源／P0整桶／策略／Native／EXE或完整Gate。QA300沿原640px／可見控制器與15秒UI／120秒phase／270秒driver期限；空隔離market root的companies.csv／SQLite缺件警告保留，不冒充完整行情或真人接受。

指南、來源契約、總／current架構、功能地圖／UI、Snapshot及原計畫同步；下一葉推既有Native／打包驗收，不再增加本來源前置。正式DB／Task／maintainer未改，無push／發布／交易。每組仍8GiB／12程序／kill-on-close／同workspace mutex、起前RAM≥8GiB；前組三PID陣列自然空、process／Job handles閉、mutex釋放後才下組，無強制清場成功。原完整範圍、FAIL、歷史缺件與自然成熟保留。

## Increment53：P03明選TPEx法人OpenAPI與每日版本

**解除的流程阻礙**：原TPEx法人web parser不能讀政府資料集11856對應OpenAPI的完整三類aggregate，而原capture的T86 discovery又成為其他市場前置。此葉沿原P03/F09增量補明選最新單日、原件／品質／成功版本／public reader與正常頁；固定V1已交付，不增試用前置，不重造取得框架。Root金融／共用ports／整合／QA／文件單寫；重用三名既有Luna Max靜態葉片，累計10/10，無新agent或子代理。

Root先核原attempt與Increment45既存11856線索，重用 `output/pit_registry_probe_20260908/tpex_swagger.raw` 476923bytes／SHA `05af7755d0d528626c104f7a8ccd7b00c6a0cf228d30bcb4669020e514eb0c7e`，不重抓。政府[資料集11856](https://data.gov.tw/dataset/11856)明列每日股數與政府資料開放授權第1版、指向TPEx OpenAPI／Swagger；本輪完整HTML526503bytes／SHA `4bb3a58a6dd708cf7d49a2cb3943feb85896184ca3a3748702db559ffef771c5`。這是指定資料集的證據，不能授TPEx年度calendar、T86或舊web整個來源桶。metadata API透過web工具未成功，另保留為無raw EOF觀測，不以搜尋摘要代原件。

新scope只允許 `https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading` GET一次、無query／redirect／retry、20秒含worker啟動／8MiB。真原件851715bytes／SHA `62c079377da617bee40ef62614530085fcd61961233d3178a046cc169aab529a`、898列／1151015、HTTP200／EOF。原HTTP收據SHA `8c8f3d3b1090bac7cfa9d8c980ea63f2438e1578a1d8afda49a1f803ea8b3f4a`；資料集文件與API共兩個新request，舊月營收／TWSE Swagger及t187ap05_L已耗額度、MOPS partial缺EOF及TPEx年度calendar授權缺件均未重置。

新parser按原20個字串欄名核schema，含原空白／拼字，不suffix猜欄；明示ROC3+2+2、同日唯一代碼，拒float／bool／數字token／null／缺欄與重複JSON key。外陸資不含自營＋外資自營逐項加總核aggregate，三類各核buy−sell=net與官方三大合計，只顯示有來源的九原整數股數；未提供的自營商自行／避險分項不反推，ETF等原證券列保留，不算真N。新scope只接受明示report日、sessions／lookback／attempts整數1，不查歷史、不T86 discovery或其他來源fallback。原TWSE與legacy_all不變；新增generic daily ports沿原全部守衛，舊TWSE wrappers仍拒TPEx，Read DTO末尾market有相容預設。

| QA | 限定結果 | outer receipt／SHA256 |
|---|---|---|
| 276 | route通過，Root另履行DataAudit／TechLead；政府資料集原件單次GET完整保存。 | `single_owned_qa_9d89792ce541468bb4e8921bfc91947f/receipt.json`；`c7ec58325ebf0209221915ba5853e634f5d327930bfbe2f3113896e44f836c5c` |
| 277 | 指定TPEx OpenAPI單次GET／898列完整保存，尚不授品質／用途。 | `single_owned_qa_a960ce311bfe4ad8bc7ab5d4c0df834b/receipt.json`；`0ab26b37b0475dccc4cad922e79f996e68c910678d3dd9bd5161082cca772b17` |
| 278 | compile通過，原generic日期helper把7位民國日誤當較短西元格式而FAIL，未成功seal；原件／a保留。 | `single_owned_qa_5a3379f02ac54abdbc572f6a54d90d92/receipt.json`；`bb396ab35d4bb1d9f9217d924bf4b36ab5c7760630b5a25829c898d016189986` |
| 279 | 新parser只改明示民國日解析，不改全庫舊helper；真898列品質、同原件重播／成功seal／真提前小時拒讀通過，無HTTP。 | `single_owned_qa_43c832242a1542fbb5c0701e1177e2d2/receipt.json`；`78d1e55379d6b26e524541bdf2d5c5136fd5b1eec165b1982fb3de74749333f8` |
| 280 | 全部葉片凍結後compile9檔＋Main helper；199PASS含新舊capture／rebuild／daily／兩UI與Workbench85，1新測試誤讀grouped source端點欄而FAIL；原斷言保留。data_pipeline Level2讀4來源7050字元，daily guide為headings_only，Root另核現行法人段，非全篇覆核。 | `single_owned_qa_22e7473df39c47eaadddae2c73320def/receipt.json`；`626083f161a049176bebb1d22b2781e9769886b453f8c05bac60b18d3a012957` |
| 281 | 只將新測試的端點／版本／單位斷言移至原raw metadata位置，定向1PASS／compile；八roots mypy1031、validator25PASS／0FAIL／4protected skips通過。未重跑199已過項，UI legacy ignore不證強型別。 | `single_owned_qa_2a4a149df07e47f2840942efc2e98cfa/receipt.json`；`00d139625c82e0d87b2f3e6fb3fa453446f706d201b751145894b18d2f6624ca` |

本次daily重播已保存且核過EOF的原HTTP，capture metadata時鐘是重播讀回完成，真正上游HTTP時鐘仍留原receipt；沒有假裝新增網路或回填首次保存。新成功版本以真台北10/16 **06:45:15** 保存，完成同小時，**07:00**才可用／successful_batch_completion_fallback；提前真cutoff已正確拒讀。manifest SHA `9772e459b8d9b9bdf88f792cdbae7c458e094aa6ec9dff9ff891aeb6bec44435`，receipt SHA `7bfdf0c416a59a3326d29ee57b5f2dc3ae98b862c00c8f9d81baedf3406aefb7`；不改原HTTP／文件／Swagger內容與時間。**QA288真07:00後正常Main32628→fresh37900已通過**：沿原左側導航→數據更新→三大法人，明選同pin的6488／8069／00679B，九原int／898母體／版本／原SHA／時間依據、切至Watchlist再返回及新程序重開一致。7批次檔與17上游HTTP／文件／Swagger的bytes／SHA／mtime／ctime不變，socket0，capture／transport／apply／seal均禁止；沒有未來clock。空隔離market root的companies.csv／SQLite缺件警告原樣保留，不冒充完整行情。保留原15秒UI／120秒phase／270秒driver期限與native Job membership終態；這是正常Qt offscreen旅程，不授Native／EXE或完整F09。


QA282已驗10同步正文／12features、context metadata30來源，errors=[]；outer `single_owned_qa_78d22314243c45ada80568ce76f0993d/receipt.json`／SHA `2f20e84e32bc5038fd105f26cf86a5c7c3f445c5c20c4424bbd764de4f913ed1`。Root指南複核另將新TPEx CLI的報告日改為必填，缺值在capture／今日猜測前拒絕，其他scope原今日預設不變。QA283、287僅備妥未執行，spec保留；QA284因本owner可變task.json在spec後補註記，preflight SHA拒絕，Python／Job未起，新spec僅移除本owner可變state pin、舊task與來源守衛保留。QA285 compile通過，但五新CLI案例的basetemp指向未執行284的父目錄，collect後setup五ERROR，案例未開始；outer `single_owned_qa_0ca6c29963d24bd182790adf273cafdb/receipt.json`／SHA `909f8982afeafaeb85314dd24495608c9e28b07849238a50b2e07b6efcebf11e`。QA286只改新有界temp後定向5PASS／36 deselected，outer `single_owned_qa_1f7eda0ed3f04f2393b45737f92b2b7b/receipt.json`／SHA `006f1c226c7ee15e9c8b2f68a00dead4c406da4e03eae0ee7bf5fb9d2beabab3`，未重跑199已過路徑。QA288 compile現轉接與真Main／fresh通過，outer `single_owned_qa_f8f845a20f1246528b5f0ffd745e654f/receipt.json`／SHA `369f59164c662b1374f6c8385a5527f593a4d392803e3f5cd9b1eb17577e2be1`。

操作指南、來源契約／current資料架構、功能地圖／UI文件及原計畫同步。source_use_accepted=false／historical_pit=false維持P0邊界，未寫正式來源決策或SQL、未啟Task／maintainer、未push／發布／交易；不限期將TPEx所有資料當同一授權，也不把candidate facts當完整F09或Gate。各Job固定8GiB／12程序／kill-on-close／同workspace mutex、啟動RAM≥8GiB，下組先查三PID陣列自然空、process／Job handles關閉及mutex釋放，沒有強制清場成功。原完整範圍與原FAIL繼續保留。

## Increment52：P06配置研究登錄與正常Registry重開

**解除的流程阻礙**：第二階段已有完整情境原件，卻無法從正常 Registry 找回。沿原 §7.1／§9.5 增加明確登錄及 exact 重開，不重造情境引擎。第一版四流程已固定交付，此增量不增加試用前置，也不混入 `4b530a7e` EXE。手動／聲明缺全帳現金聲明及同源 Health／行情仍歸 D；不以成本／預設零／Paper 證據補 NAV。

Root 保留金融／共用 ports／整合／QA／文件；重用三名既有 Luna Max 靜態寫兩個 UI 葉及定向測試，累計仍 10/10、沒有新 agent／子代理。設計為同一原 Registry SQLite 的 additive typed context table，原 research_runs v2 與 scenario v3／store v1 不換版。引用 8KiB／正常清單25筆、有界 query-only、外部 selection SHA 與原件帳種／portfolio／artifact／snapshot／decision／保存時間／input hash 交叉綁定。登錄是 explicit create-only 動作，重試保留首時間；失敗不刪原件，不產生假本金／成本／空 equity/trades 或新績效。原 callback generation、取消與 native worker 終態保留。

| QA | 實際限定結果 | outer receipt／SHA256 |
|---|---|---|
| 270 | route 為 execution／testing／documentation／tech lead／data audit；portfolio_health Level2 讀3來源6073字元，unknown=[]。只作定位。 | `single_owned_qa_b169cf9b0ab1479daf5f140ec24f93ab/receipt.json`；`81e4dbe578cb04bf6f8775e21602d0f586ee0a2e744df78fe1ca5da26eb7af77` |
| 271 | core compile與原 reader 78案通過，但沿用清冊含仍由已知 worker 編輯的 UI，最後 source pin 檢查 FAIL；整組不作候選接受。原 log／receipt 保留。 | `single_owned_qa_1884d01be8e546569a23b50102539a47/receipt.json`；`65eb3a088d12e10a8f0073b580fb6c25ccf66398cf5cd01bef734bc1b7365e45` |
| 272 | 全部葉片停止寫入後重綁 SHA：11個產品／測試檔與 helper compile；218 PASS含新登錄／兩個 UI、原 Registry service／repository、scenario／initial widget 與 Workbench85；八roots mypy1030、validator25 PASS／0 FAIL／4 protected skips通過。UI legacy ignore不證強型別。 | `single_owned_qa_01fb44dfecd446c18bdc149096d34bbe/receipt.json`；`71c6a2ee4f9509644f845e245bf945b7ba7782b41d3bc2ed4ae574fb27c1099c` |
| 273 | helper誤要求1024px而offscreen只有800px，在原可用螢幕斷言 FAIL；尚未登錄。保留a與隔離輸出。 | `single_owned_qa_56cc414fd7ac4b7a9727082e083e0eb4/receipt.json`；`245409eceab664e5a9497d42fd4fcecc139c7e063eb751d19cb4ccb27674991c` |
| 274 | b恢復原47的640px及全部曝光／裁切／15秒UI、120秒phase、270秒driver斷言。正常 Main5648→fresh44328，明確登錄／重試／Registry選取／P06 exact／個股／返回通過。 | `single_owned_qa_6151d5d764024ee4b9665d99be1500a4/receipt.json`；`0ce0478d4b2ca9b60752962d8e066bfeedc4234867dc6a5e86f5f598b9d7e181` |

QA274只複製並重用47既存完整合成原件，不再造 account／Health 或重算情境；兩階段都禁止 `compare`／scenario `append`，fresh另禁 `register_saved`／Registry append。原 artifact `sha256:2818ab728bd6fe708ae4a6b6e80f116a01be25f467f6d4e73e8afa4f095cf9f0`、1000股／mark102、原現金／NAV／targets與個股投影一致；引用 SHA `sha256:3c507be3eaa12afbba0fdfeaee3dd3510c401051ed108a0ccfb02680cfec717e`。scenario DB原hash `8303d7ae64781335e19dacf2ad61a2fbe79942581f5e149330bac3f5ce7f277a`，新 Registry `ac1d1318e872eeeca4d983e8dbf8af929cebfbc42289eaaa0f0f24c679d6d6bf`，fresh相同；7副本來源及21舊來源 bytes／SHA／mtime／ctime不變，socket0。不是 Native／EXE 或真來源驗收。

全部 Python 由 Root 串行受控 Job 執行，8GiB committed／12程序／kill-on-close／同workspace mutex；下組先查三PID陣列空、process／Job handles關閉與mutex釋放，沒有以強制清場當成功。正式資料、舊 task／收據、固定試用包與其他 owner 原件保留。操作指南、功能地圖與 current 架構同步；下一葉回原 P03 必要資料缺件及既有來源用途鏈，避免在此 Registry 限定出口持續增加前置。原完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4、歷史 PIT／真 N／完整雙策略績效／自然成熟仍未接受，無新 HTTP、正式寫入、Task變更、maintainer重啟、push、發布或交易。

Increment52文件閉鎖：QA275十份正文／12features及metadata30來源檢查 errors=[]，outer `single_owned_qa_ea331997ecea45f5a8f748345b75d760/receipt.json` SHA `aafbb819864813aef908e7cfa28e702febfdc5e851a470389511f7022e224490`。三PID陣列空、handles關閉與mutex釋放。之後僅補本收據註記與owner交接，不重跑未改runtime。

## Increment51：V1獲利因子窄版候選

最後交付閉鎖：QA268已核7093候選檔，20輸入的Windows長路徑因helper未用extended-length讀法而FAIL，原件保留；新b沿原Native相同長路徑讀法、原bytes／SHA／root斷言，QA269全部通過，未改EXE或重跑原生旅程。outer `single_owned_qa_27601deec05d47319895b28578b2a938/receipt.json` SHA `a973cad5b22158836cf6b615a3601b0c18c99de10c909ed828ee5eb19b9dcb6a`（FAIL），QA269 `single_owned_qa_a2a0bcb95c244715a74f4133689f7163/receipt.json` SHA `c18f2a8f4e5bc1a05d25dc68f020f6a278062a5e388f4faf8c916dbbb394ff0d`。新交付 `FINAL_VERIFICATION.json` SHA `4fe9e0a010e9bf60e106e1a1de93f427c26ebfd58b8d3f71b42c6e9d3e1fa974`：7093檔、20輸入、原9fa EXE及保護檔、同入口--check與五文件／12features核對；Native真PID37704→32700，三PID清冊空、handles關閉、mutex釋放。僅追加本收據註記，不外推真人／所有流程同EXE重跑或完整Gate。

**解除的交付阻礙**：Increment50已修開發分支，但固定9fa EXE仍有相同金融誤讀；本輪只回移PF必要變更至9fa，不整批帶回49七欄schema／metrics狀態、策略登記或其他第二階段功能。受管理worktree由本chat擁有，原工作樹HEAD `0ef77a8d87eb643fc02dec999a25aeb0fc92b9dd`不切換。Root修四個不適用hunk、保全rej原件，補9fa的PerformanceMetrics匯入與PF專屬status；原FIFO／分量化不換法，Decimal60隔離是本輪PF精度所需，不改策略／撮合／訊號時序。Luna靜態原note另保留，金融裁決由Root負責。

固定source候選 `ad606e7649bb531f5a4720f12c9ecbca8dae82ec` 的12個Python變更及必要六文件，QA264 compile／八roots mypy1016／162PASS含Workbench85、validator25/0/4與float守衛通過。3233 pins中3227份Python前後一致，產品import只准匯出source，禁止混用dev。最後文件檢查發現舊Snapshot超連結指向ignored本機output而在export缺件，保留FAIL；原件路徑改普通文字，doc-only commit `4b530a7e929f31dc0f7d7edfba790d011aeb1bfc`，所有Python與前候選相同，不重跑未受影響runtime。QA265六文件／12features通過，依原1800秒上限從該固定commit建獨立EXE，archive SHA `34c6122702a2220d1663c70d51758386b41e449570d040702a21255669fbf3ce`，EXE55,978,104bytes／SHA `68e92c92adf30e479a798052e812f0d965d0f40c2e2e841610ab628191330f37`。建置不是Gate。

| QA | 限定結果 | outer receipt／SHA256 |
|---|---|---|
| 264 | 固定來源runtime全部通過，歷史output超連結缺件FAIL保留。 | `single_owned_qa_4cdbc7926841414ebdf01260f6eab763/receipt.json`；`585a2e1e4c25a4d37efd21d1fb41f80f83ac8a3e16f0b5eb92bd188ab5f32214` |
| 265 | 只修portable docs、六正文檢查與固定source建置通過。 | `single_owned_qa_1d43d2ce43794305a79221e2dc943306/receipt.json`；`8f9ace3ddb92bacdf8f51690328fae89718e43bc0da28614ec31696d9fef5575` |
| 266 | Native harness誤預期nested binding，讀Root flat buildpin前KeyError，未啟動EXE；FAIL保留。 | `single_owned_qa_e6396ccdea37453abef2a66a7b5c3967/receipt.json`；`7eabd37185a04899384fd9a57cbfe37e6ade3ffce06a6533ad7f4d2312ef364e` |
| 267 | 新b按同外部固定SHA結構讀取，原Native GUI／保存對話框／exact歷史／返回／fresh通過；原15sUI／120sphase／270s driver不放寬。 | `single_owned_qa_e8a4f7e52dd7460f99442f08b09790ff/receipt.json`；`b36268b687211b366c210c4be39daba32d270b174b57708e44855c4aacbe868e` |

QA267使用原四股來源的2317真行情，原419日／100萬元／手續費14.25bp／滑價5bp固定門檻操作，1筆買入5000股、0完成配對；成本176138分、期末現金83238.62／權益1363238.62與前版一致，PF None／no_closed_pairs／語意版本及正常摘要具體原因通過。fresh精確重開同run／metadata／equity／trades，20輸入與行情DB不變，Python socket零；Win32實際PID／曝光／裁切／click來源與frozen product origins原守衛保留。不是合成市場資料、真人或完整金融資格。

新試用入口 `output/trial/Baldr-V1-PF/Launch-Baldr.cmd`，附config、指南、已知問題、BUILD_INFO、20輸入清冊及candidate檔案清冊；新output／registry／私人狀態獨立，唯讀沿用原四股資料／technical pin，原9fa包與舊結果保留。其他三流程沿未改路徑具名證據，不冒充本EXE全部重跑。舊schema缺PF語意仍不可用，不新增DB遷移；TPEx、來源用途／歷史PIT、真N、完整雙策略、Native真人／跨機與自然成熟及原完整計畫仍待。無新HTTP／正式資料／Task／maintainer／push／發布或交易。每組8GiB／12程序／KOC／workspace mutex／RAM≥8GiB，三PID清冊自然空、handles關閉及mutex釋放後才起下一組；累計10/10僅重用靜態Luna，沒有新子代理。

## Increment50：P08獲利因子語意與金融錯誤修正

**解除的交付阻礙**：原 analyzer 在沒有虧損時把獲利金額當獲利因子，零配對／全平也給假0；None沿摘要格式化會中斷。Root沿原已完成FIFO配對淨損益修正，沒有新增未來資料、策略、交易價格或配對算法。起點 `22831953eb6bc9ae23a52b830d76c00cfba3a303`。固定9fa也受此錯影響，但其EXE尚未修補；下一交付是V1-04窄版backport，不將第二階段新功能混回四條凍結流程。

PF有總虧損才算無量綱有限比率，純虧損的0有效；無完成配對、無虧損而有獲利、全平分別None及具名狀態，不用inf或金額。原分量化／FIFO保留，以獨立Decimal Context60隔離caller prec／Inexact trap，再沿原analytics DTO數值邊界。新report附 `closed-pair-net-pnl-ratio.v1`／status；共用projection拒未版本化、bool、負值、非有限值及矛盾狀態。單股、batch兩路、最佳化與匯出保留可用性，新舊repository schema不變，未定義保存NULL；舊比較／promotion摘要不升格原值，舊保存列／舊run不重算或回填。歷史七指標schema仍不包含PF。

| QA | 限定結果 | outer receipt／SHA256 |
|---|---|---|
| 259 | Increment48真可用小時後正常Main／fresh，見下段。 | `single_owned_qa_8f7fb463846b4ae3af51c770a8ade1ae/receipt.json`；`ba110c6a017c497abd76d37df39d3ee3962784210d290a0d07e18b650da280dc` |
| 260 | compile12／八roots mypy1028通過；177PASS含Workbench85／1FAIL，缺值仍留$字元。原FAIL保留，validator／float守衛尚未執行。 | `single_owned_qa_4764cb6a9aa448d592af6c041f836a70/receipt.json`；`2a379a01cc9a6db57d273f9964b588ea93a958d6486e68755096c5047be9ab06` |
| 261 | 缺值移除貨幣符號後定向1PASS及compile；validator25PASS／0FAIL／4protected skips、金融float邊界守衛通過。不重跑未受影響177案。 | `single_owned_qa_e47538ec831a4758af4c065adafdd3af/receipt.json`；`52a3b5273c278f26a60007a79864a7d6a81659b546b04e53d9fe9d9d4dc465bf` |
| 262 | 原引擎正常Main17676→fresh48528兩run，正確None原因／保存／版本歷史卡／原結果／返回通過。 | `single_owned_qa_9716820406b04c469f1e0b0b27282738/receipt.json`；`3c4dc30f230732c4a3458dfaf6df17a51ee6f36b2719a804deaf07b842270662` |

QA260涵蓋真Trade費用／滑價／部分FIFO、獲利與虧損、縮放不變、caller精度／trap、舊值投影、隔離SQLite新NULL／舊列不變／schema不變與optimizer摘要，另受影響原numeric／metadata／歷史UI／batch／optimizer／匯出。QA262延用49原Main harness另存50a，只注入30筆合成價格I/O，原策略、broker、analyzer及正常Main slot／保存命令不替換；非保存對話框點擊驗收。父原收據 `increment50_metrics_main_fresh_a/parent.json` SHA `8d6b6eabf7fb06776d7c0090b3ac9384cd497531e0c80dd774130e99799658c6`，fresh SHA `1e8b80d8f6350533d2f486d7c1eee57c256072f6e295cfd2f7360198c47ff4bb`。14完成配對全贏與0配對的PF各自不可用且正常摘要不中斷；保存後的七欄卡不反推PF。fresh禁止回測／保存，同兩run原檔／時間一致、socket0，非真市場績效或Native／EXE。

**Increment48真時鐘補驗**：QA259父44872在真2026-10-15T22:00:05 UTC後讀入台北10/16 06:00才可用的既有版本，fresh33944同pin；2308原價1630.00／PE51.88、權證053040原價1.73／PE-----、2330當日查無各自保留原意，正常返回Watchlist。13快照原件bytes／SHA／mtime／ctime不變，沒有新HTTP／seal／未來時鐘或正式寫入。父／fresh SHA `521832aeafe543839d05125521f8303efc6d41c8b9070a1218647d4ecb9ea1cf`／`f60151f36960a11bd2f4a373690e125591e61efa0ccd7b8204b478209ed6c920`；owner `increment48_actual_main_acceptance.json` SHA `9e1c2e25d5f2d67770ae32a1ff9df77e0f8b69adb9ee768bdff8f528e304d350`。原48待驗Main步驟已解除，來源用途／歷史PIT／TPEx／完整F16仍各自未接受。

各組8GiB committed／12程序／KOC／workspace mutex、啟動RAM≥8GiB，三PID清冊自然空、process／Job handles關閉與mutex釋放後才起下一組，無forced cleanup。累計10/10僅重用Luna Max靜態單寫測試／presenter，Root金融／共用ports／整合／QA／文件單寫；新worker pending writes=false。既有ui_qt ignore_errors不證UI強型別。操作／current架構／功能／Feature Map／Snapshot／原§9.5同步；固定V1／正式資料／Task／maintainer不改、未push／發布或交易，完整計畫繼續。

## Increment49：P08新單股歷史指標版本與正常讀回

**解除的交付阻礙**：原單股引擎已有可定位的七指標，但新保存結果的歷史卡仍一律顯示未提供。本葉沿原 Backtest／Registry／歷史頁補保存契約與唯讀投影，不另建引擎，不改固定 V1 `9fa4518c2aca87beaddef75a2b29165722da6a6c`。起點 HEAD `538a873eed0b2c4ce84b5ff07f858bc780a620f1`。

原 analyzer 只新增 observed／unavailable 狀態；原公式與數值不重算。新 `single-backtest-performance.v1` 綁七原值、狀態、代碼、實際計算期間、完成配對數、equity 列數與雙層 SHA。新 schema 保存前保留真正日期並核原表；public exact reader 與 UI 各自重核契約。舊 run 缺版本仍不可用，不回填；零完成配對的勝率／期望值、零變異 Sharpe、安全條件不足的指標維持未提供。原浮點 analytics 是既有分析邊界，不代表 Decimal 核心、投資資格、可比較性或排名；獲利因子不在七欄保存資料內，仍未提供。

| QA | 限定結果 | outer receipt／SHA256 |
|---|---|---|
| 251 | compile4／mypy、原 numeric／metadata／reader14PASS及精度邊界守衛。 | `single_owned_qa_e7724c9818c94345a567f8660f25745b/receipt.json`；`34dfe15c912594c2a4ad768fc1e1b1e4f76897d00ca7953b82c2ba3e9734419d` |
| 252 | 新 codec15PASS／2FAIL為錯誤文字比對，保留原FAIL後修測試的精確原因，數值拒絕守衛不放寬。 | `single_owned_qa_76726d00f8664c2183090ea25aecaf8e/receipt.json`；`a662a54ff0574b68e9a3443f1b3808c473a06f2de9904d908dc66f54f7b85b11` |
| 253 | 八roots mypy1028通過；140PASS（含Workbench85）／7FAIL，float與Decimal同值hash、原DatetimeIndex保存及一項舊狀態預期不符均保留。validator尚未執行。 | `single_owned_qa_61d977e7d6ab470e822b1e2727aef624/receipt.json`；`1acf8fc86bc6eb89e98576e91f8955ce7cae0f9bee78bc5093e00b50ad0edbc9` |
| 254 | 以canonical decimal文字核同值、新schema保存日期，定向codec17／reader6／UI4／原接線4共31PASS，compile／型別及validator25/0/4通過；未重跑未受影響140案。 | `single_owned_qa_3a7d53baaddf493ab7024dd277504477/receipt.json`；`1e530949eac278ac1e5a6eb04d40ce72415b9a64d5910143e4275eddd43dbbed` |
| 255 | harness PERSONAL誤放package內被原路徑守衛拒絕，FAIL保留；新b移至明示Temp隔離根。 | `single_owned_qa_c7eeba06c9bb495eaa5fba4ec6875d8a/receipt.json`；`c210763b6442201f450ff127b98d736e3bd590bf63473a44ad18676ceb8e07df` |
| 256 | 正常Main啟動；harness1440寬超過實際offscreen800螢幕，實體可見性斷言拒絕，FAIL保留。新c使用640及原收合控制，無假幾何或放寬期限。 | `single_owned_qa_d07f990219f5425c923b139570585285/receipt.json`；`8a890471a2e54e7e32d4b734fa6b20959ab5ee07e63c4495207619c0630c9a87` |
| 257 | 正常Main38288→fresh44116兩run保存／歷史卡／原結果開啟／Watchlist返回及精度守衛通過。 | `single_owned_qa_4f054f154f53454aaa053adf8d6dd2c7/receipt.json`；`5613fe56e1486e308446af1bf8620cbf4d64e3d48d5f9f4bfb679fc79e7d80ee` |

QA257只注入30筆合成OHLCV，策略／broker／原analyzer／版本capture不替換；父程序以程式呼叫正常Main完成slot與保存命令，非保存對話框點擊驗收。歷史finder與原按鈕有實際座標／祖先／hit檢查。兩種baseline參數產生14完成配對與0配對結果；fresh禁止回測及保存，原metadata／parquet／DB／合成輸入bytes、SHA與時間一致，Python socket0。父／fresh原收據在owner `increment49_metrics_main_fresh_c/parent.json` SHA `2d0e70b8060ba6d365ca98577975f7284029f27ad263912eba359b5fe7e080c5`、fresh SHA `dc841bd0afd3570d49f474670aa769ffb71a6c0be53f6470633a6259e32a3af9`。這是source Main的合成工程旅程，非Native／EXE、真市場績效或完整Gate。

每組仍8GiB committed／12程序／KOC／workspace mutex與啟動RAM≥8GiB；前組三PID陣列自然空、handles關閉及mutex釋放後才起下一組，無強制清場。只重用三名Luna Max靜態單寫葉片，無Python／network／子代理；pending writes=false，累計10/10。既有ui_qt ignore_errors=True不證UI強型別。

同步操作主冊／Research Lab分冊、current／總架構、功能／Feature Map、Snapshot與原§9.5。原手動帳交易缺完整現金及同源Health／行情，不能取default initial_cash=0、成本推NAV或借Paper來源，保持D缺件。P03注意原件待真可用小時後正常Main；舊獲利因子無虧損時誤回金額的金融問題另沿原引擎處理。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4、來源用途／歷史PIT／真N／完整雙策略／Native／EXE與自然成熟保留；未新增HTTP、正式資料／Task／maintainer、push、發布或交易。

## Increment48：P03單日官方注意公告與固定版本

本葉解除原 F16 沒有可核驗官方注意原件、每日版本及正常個股投影的工程缺口，屬第二階段；固定9fa及四條第一版旅程不變。不是增加試用前置，也不將unknown卡片算完整功能。HEAD起點 `dbcbeae57fc251cad6b347117874a6db29d3f6a5`，Root Sol，重用 Luna Max，累計10/10不新建。原 task／singleton／原FAIL不變。

Root先核689份舊／新HTTP收據；沒有重抓已耗完的月營收GET／Swagger或MOPS缺EOF文件。五次各一個有界GET依次為TWSE OpenAPI notice、官方notice HTML、頁面實際引用的web-report.js、main.js與依該契約構造的單日RWD查詢；沒有重試、全歷史或正式寫入。第一份132 bytes完整HTTP只得到無日期placeholder（SHA `4bd0ac94f01d8731e1e4407c90af24f3d16d4ff24e13e09b9247e92e5160e216`），保持不合格，不當沒有注意公告。第五份明示20261015單日全TWSE證券query，4,931 bytes／宣告18證券／18原列／完整EOF，raw SHA `1e6458ff3b5458707e4d1fec87bb7fdc1d6ef8db752f069e49b3eea7e22cc4c8`，HTTP原收據 SHA `48bf7add8d9838cbfc0df8c22115709f24a8d6d6efbe0f5b04d2bb1488999a55`。包括053040權證，不能稱18股票或真N。編號與原累計次數不拿來推論唯一事件或連續日數；原理由HTML／純文字、收盤價及PE各自保留。

`selection_official_attention.py` 嚴格核schema、八欄、params／title／同日、唯一代碼、宣告筆數與JSON品質。`official_attention_snapshot.py` 另存完整raw與HTTP／worker／request／headers／cookie／三官方文件原bytes；MOPS／T86 schema不冒用。原receipt沒有worker-result SHA，新manifest明示現在才綁保存bytes。create-only／fsync／pending／實際批次時鐘與明選雙SHA reader沿原守衛，禁止讀未來cutoff；沒有official發布時分則保留None與成功批次小時fallback，不把HTTP Date當發布時間。正常report service＋獨立typed DTO／PlainText顯示，不回流交易限制、Advice或金融計算；環境三值錯誤僅隔離此區塊。操作與排錯已同步[指南](../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#單日官方注意公告後續開發分支)。

QA240–244五個HTTP Job皆自然閉鎖，raw取得不授來源用途。QA245 runner新增env清除欄位不在舊白名單，未執行產品命令；QA246編譯通過，owner probe漏repository import路徑而失敗，尚未seal；兩個FAIL原件保留。新owner runner v3只增三個注意env清除名稱，probe b只補import路徑。QA247完成真時鐘seal：manifest SHA `77a8ecdae561cfe6dfcaab46adcd63b2349fec8691cfd8ec7ce1c3cdbdd05475`，receipt SHA `77a30154c67473dc2a1d6e120df896ca89fe0b1c626e667b0a221cad833c89f7`；11份原件bytes／mtime／ctime一致，首次保存台北05:26，最早06:00可用，before-hour正確拒讀。23 parser／UI測試通過；outer `single_owned_qa_3b6d3a74aabc4e9cb12cfdeda1a36759/receipt.json` SHA `6fee41cc9b8701bd28b35d5f9b1a266b24b361c8f32698b3bc90db40dcde484d`。

QA248：新來源trace與可用公告限制修訂後，受改report service／provider contracts／舊個股UI／公告UI與Workbench合組213 PASS（含原Workbench85）；validator25 PASS／0 FAIL／4 protected skips；八roots mypy1027 PASS。既有 `ui_qt.* ignore_errors=True` 不證UI強型別。outer `single_owned_qa_5fbe9a013c754da48642921a6c911fe9/receipt.json` SHA `1c2b68c966dc645cf38fef3db6deec527b7a4ac53d25c4419cad8021a38331b8`。上述Job都8GiB／12程序／kill-on-close／mutex，三PID陣列空、handles關閉與mutex釋放、無強制清除。

QA249：snapshot拒絕／self-contained／不可覆寫／取消／讀中變更及report provider日期／原字串／固定身份／失敗隔離與service接線，共23 PASS；compile、保存命令help及金融float邊界守衛通過。單測transport及三份小文件明示合成，文件pins與now在單測中替換，不授真時間旅程。outer `single_owned_qa_e9420224d4344d2b91a4cee2401a457e/receipt.json` SHA `5f09b91d05ce4b7d349718eb44570277c000d3c76e294422a409ee30a77dbf44`，同資源限制且自然閉鎖。

仍待真可用小時之後的同版正常Main／返回／fresh，具名driver已compile，不以未來clock提前真旅程。官方文件只證查詢契約，未授來源用途／歷史PIT／TPEx或完整F16，Native／EXE與自然成熟仍各自保留；接續原P06手動／聲明初次來源，不以此等待阻擋整線。

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

## Increment34：V1一般觀察股票下鑽與回訪

本Increment解除原凍結V1-03交付阻礙。QA94／106證明的是版本研究收藏重開，不能代表一般股票手動新增→個股→返回→新程序讀回。QA117在505固定EXE實際新增2330並保存，但下鑽後價格／技術歷史為空而FAIL；手動列被預設為recommendation，reader正確要求已保存圖表來源，因而沒有讀取現有行情。原FAIL outer SHA `0e6d6e7e77c35f04b3c18c137b66e18a0111b78a120fab70061fad2f96e7d9e2`保留，不能把舊收藏PASS當此流程接受。

最小修正只在手動列明示opt-in、source_id空白、identity=unknown且無result／決策日／snapshot身份時建立目前個股研究context；任何連結、衝突或保存來源仍走原路由，沒有失敗後改讀最新的fallback。未改金融核心、reader、保存格式、來源時間／精度或收藏守衛。Luna僅靜態核對；普通手動返回按代號定位，與同股其他來源並存時不宣稱精確列級返回。

QA118只準備未執行，靜態核對DTO後將新增測試價格斷言改為Decimal再釘選QA119。QA119 compile、手動列→真SQLite reader與保存／衝突反例、舊導航及保存圖表守衛、必要Workbench共186 PASS；validator25／0／4與mypy1016通過（UI既有ignore_errors不證UI強型別），outer SHA `857f398c68031625c06fd894e2bb4868adf10273f8d4d7da7d836a121191ecfb`。每組仍8GiB／12程序、workspace mutex與RAM≥8GiB，三PID陣列自然空、handles關閉、mutex釋放，無forced cleanup。新版固定EXE的正常GUI／fresh旅程及交付更新待下一具名收據；原505候選與原FAIL保留，未升格完整Gate。

QA120從已驗固定commit `5d98187d5d148076c8cc0204255b1cc291eea084`另建候選，EXE SHA `8d8297ab71973f8cc7af8de9d0be2987c8c16d102c174d639c8eae5d3cc003da`。QA121在新EXE以真四股資料完成一般2330新增／保存／個股120價格＋120技術歷史／返回／新PID37276→33956再讀同一manual列，原JSON SHA `801a0c38cb0282d68c296398dbfd748aed2fc9cb3f9e14da64ba7732b921e1d7`一致；重複新增與無效0000不改寫。試用者清單及行情DB bytes不變，outer SHA `dca17917219b57653393a405e535f7d1b3a14a0071b86b770eb0f744527a05c9`。普通回訪不冒充exact行情版本或同股多來源的精確列級身份。505→新候選執行碼差異只有Watchlist，金融、reader及public ports不變。

QA94原為預設無價格上下限查詢，故另補原凍結V1-02的實際條件套用及受改Watchlist收藏重開，不新增實作。QA122在1024px套用按鈕命中None、QA123載入按鈕祖先裁切、QA124在1440px查詢按鈕topAt=None而childAt仍是目標，三組FAIL各自保留（outer SHA依次 `8cffc4c7c4d13319f14251ed5c68520fb402458b77c0ab850b0428d9c42f2136`、`9f6e1c55e3557ec474e01dd595e606cdc00a80c6da13d0a29ed288ede3eb6bfc`、`8d7853c8b1c0c5de1b04703971431c9552f23b4bb919db51f9764ec0f7138fc0`）。不以直接呼叫slot、縮減斷言或拉長15秒UI／120秒phase期限代替可見操作。

QA125只讓owned測試Main暫時置頂，1440px沿原曝光／裁切／命中守衛，另對9個父程序與1個fresh按鈕點核Win32 WindowFromPoint所屬PID。原來源查詢／嚴格載入／實際收盤價下限341.5→3符合1排除0未知→比較／同版個股返回／收藏→新PID39640→18796讀回同query／page／basket及bookmark JSON；V4來源bytes不變，outer SHA `038ce5e593fbddeb12c5a0ac7c36be60082710eae658e62fe9f0588bcc5eafa6`。這是本機指定候選的限定工程證據；產品未改置頂旗標，1024px裁切與全尺寸真人／跨機仍未接受，指南要求放大視窗、切到前景並捲到操作列。未重跑未受影響市場、回測、金融及Startup案例。

QA126因Root拿LF Git blob裸bytes對比git archive依本機core.autocrlf輸出的CRLF而在修改前FAIL，outer SHA `12c1ea50060321653c19ecaa25f1f837d810a00e09de4864635ae19e9fb66288`。QA127改核archive原bytes／commit comment／Git path-filtered blob，保存505交付九原件後更新同一入口，--check與7093候選檔清冊及具名旅程核對通過；但Root將預期會更新的交付檔誤列入immutable pins，runner事後守衛正確拒絕，整組仍FAIL（outer SHA `c4dbbfa232bb37ffec6b9b2614f44e1f7ff968cee82930cb1ccd1ce763d5c1c4`），不改守衛、不重跑更新程序。舊505收據SHA `c472e1429363679a49373eaaa06e7d2a3482d95b0e5c22417815e844d9850432`原件已保存owner的v1_delivery_snapshot_increment33；目前新交付收據SHA `60d141c720a0bf7a3761d288f5ddde9d718c05e0854839901165fd900337092d`，待獨立只讀QA128結案。以上每組自然PID0、handles關閉、mutex釋放、無forced cleanup，沒有擴張V1範圍或正式寫入。
QA128為獨立只讀結案：新收據SHA `60d141c720a0bf7a3761d288f5ddde9d718c05e0854839901165fd900337092d`、8交付檔案／33 QA pins、舊505九原件、普通清單及真價格條件雙程序身份均一致；8份文件治理12features、errors=[]。outer SHA `4506138c21e673786ff8ea978d4bb2ae9a7d09a706ff7982d1bd47c244655871`，自然PID0／handles關閉／mutex釋放，無forced cleanup。固定5d98187d已可從同一入口試用；無active Python／QA或pending worker writes。這解除V1-03實際阻礙及V1-02原條件驗收證據缺口，沒有新增第五條流程、正式寫入、push、發布或交易；原完整第二階段及全部FAIL保留。
## Increment35：V1價格條件在窄結果區可操作

本Increment只解除V1-02已存在的操作阻礙，不新增功能或視覺優化前置。QA129在已交5d98187d固定EXE、owned QA視窗置頂後，1024px的來源查詢及載入可點，但套用按鈕中心[1075,814]仍超出Main frame[24,24,1024,731]，原15秒命中FAIL。這與先前1440px外部遮蔽不同，確認六欄控制區水平溢出。原FAIL outer SHA `331339a718a639d10d088ebdd4bc75826932e92819d8a0ae50027dc32eaeb446`及自身視窗圖／診斷保留。

修復只在既有外層可垂直捲動的結果頁，按可用寬度重排同一批條件widget、規則combo與比較操作；套用按鈕移到窄版獨立靠左列。來源combo以有限顯示寬度呈現，原完整來源文字／pins與信號連線不變。沒有修改query、金融核心、來源時間／精度、reader、bookmark格式或public API；獨立視圖沿原高度分配。Luna只讀複核三檔定位及候選diff，零寫入／Python／QA／network。

QA130新520px幾何案與其他原案共10 PASS；760px在resize後立即捲動時幾何尚未穩定、獨立520×170收藏表格受長式排列擠壓，兩FAIL保留（outer SHA `2cc0c1b1f38ac831bdb97df2f2665f64b51fe3e96dbedaf130c00f08e2e464b0`）。修復限制到已有垂直scroll的結果頁；新幾何案在原15秒內以實際捲動等待整個按鈕可見，保留原收藏3秒期限與所有原斷言。

QA131原10＋新2價格UI案、來源版Main1024px正常查詢／載入／套用3符合1排除0未知、必要Workbench85、validator25／0／4與mypy1016各自通過（UI既有ignore_errors不證強型別）。來源Main PID45684按鈕Win32 PID及Qt裁切守衛一致，未保存新收藏或重跑完整旅程；只是WIP來源證據，不冒充固定EXE接受。outer SHA `4e4cfabb7ae83a8ab0c8d3cd07af7c1fb983a3cfae322234d138c442d70c48d1`自然PID0、handles關閉／mutex釋放、無forced cleanup，沿8GiB／12程序Job與RAM≥8GiB。下一步只對新固定候選重驗受改價格比較／收藏／fresh；未受影響市場、普通清單、回測與Startup沿原收據。
QA132已建第一個7bd6a229候選（outer SHA `a36b3bed4ab64ce71b212a0172a024522618c5494e495855cd8765d83efa3b64`），尚未替換交付。QA133在固定EXE1024px正常套用已過，但比較前表格列命中FAIL（outer SHA `31eb6603fae6047d5fa5cfed28aa8f5464360c0ce0fb165f341985e72748b314`）：同頁其他研究區的最小寬度使價格表格仍超出viewport，外層水平捲軸已隱藏。增補只將價格區寬度限定在可用viewport並靠左，不重排同頁其他區塊；表格自己的可見水平捲動仍保留。

QA134相同12個價格UI案通過，來源Main已套用、選股、比較並開啟個股，但Root新增全矩形檢查越過QDialog實際頂層去核logical owner的viewport，導致返回前FAIL（outer SHA `83a9193c9be6038e4c4c2672c7e81e08fab150a55a231d13451360c1314e92af`）。QA135只修Root額外矩形檢查到實際window；原中心／裁切／Win32 PID及15秒期限仍保留，不重跑已過且未變的12案。新增一案真合成來源＋寬兄弟元件回歸通過；來源版Main父34396→fresh38640完成1024px真價格341.5→3符合1排除、比較、個股返回、收藏與同query／page／basket新程序重開，外層hidden horizontal值0、固定V4來源bytes不變。Workbench85、validator25／0／4、mypy1016另通過，outer SHA `33241374320f66917283b0ea20120ca2e6095007e623eec8fd64eb822aeedb8a`。這仍是WIP來源證據，固定新EXE與交付另待具名收據；原所有FAIL及7bd候選保留。各組自然PID0、handles關閉、mutex釋放、無forced cleanup，沒有擴大四旅程或金融／來源資格。
最終固定來源為 `3d072ca44543ea5d834bbd4550febd4c4fefd56a`，QA136另建候選（outer SHA `5cde74a88d1540b6aebb36472d132182e43fc22bebe5dff811552a6f6aba66fc`），EXE SHA `c6510a0366ecded69dd7a8bc285f1b8f057000f854eed7223f492e89ae1a0ea3`。QA137在新EXE1024px父33052→fresh49920完整通過同一受改價格旅程；341.5→3符合1排除0未知、比較、個股返回、收藏與同query/page/basket重開，固定V4 bytes不變、外層hidden horizontal=0，Qt／Win32 PID及原15秒UI／120秒phase守衛均保留。outer SHA `d07af53ca79ebdb164ab71727ee8fded15281c702d17551c5f558682264c548f`自然閉鎖。owned QA視窗暫時置頂只排除既有外部遮蔽，產品未加置頂旗標；不授真人／所有尺寸／跨機或完整Gate。

QA138先核舊交付SHA `60d141c720a0bf7a3761d288f5ddde9d718c05e0854839901165fd900337092d`及九原件，保存owner的v1_delivery_snapshot_increment34，才更新同一common啟動入口、指南、收據與7093候選檔清冊。原config／20不可變輸入／行情及清單位置不變；common --check讀回新固定候選與原隔離根。交付檔明示為本命令輸出，不誤列immutable來源pins；控制器與來源守衛維持。新交付收據SHA `20fa82f61ee3cf363db938333fcbdd2b39536822dd571071b1503bf2ba7a5408`，outer SHA `b32142662696168972fba3bfd1a900a97cad4251f77f83b97ec24dc01006de97`。原1024px裁切列為具名已修，原FAIL與所有舊快照仍保留；其餘三旅程、金融、reader及Startup沿原未受影響收據，不增加V1流程或正式寫入／發布前置。
QA139最後只讀helper誤要求fresh收據含父程序才記錄的price_counts，KeyError中止；原outer SHA `4f1f37da608b3bdbdc47b08f14eebcd21dc3db7acd189783536dad7d67ad76d4`及spec／helper保留，未改產品或重跑旅程。QA140新helper依原schema核父程序3／1／0及fresh同query／page／basket，8交付檔、45QA pins、九舊交付原件、EXE／來源身份／保護檔與七文件12features結構核對通過；outer SHA `27169a5c5729874a49dc270ce80b2a76b72fd945c1436f0fd8bb2a22dce5075a`，final check為owner的v1_final_check_qa140.json。兩組均三PID陣列空、handles關閉／mutex釋放、無forced cleanup；未終止其他owner程序。Increment35解除的第一版阻礙只限V1-02窄結果區操作與表格可達性，固定3d候選已可試用；其他尺寸／真人／跨機、來源用途與原完整Gate未接受，完整第二階段保留。

## Increment36：V1單股回測未成交日的金融正確性

本Increment只解除V1-04錯誤金融結果的既有阻礙。QA141六個新反例在原撮合器全FAIL：unfilled分支continue漏掉當日收盤估值、原有反向取消與mark更新；除資金／量能不足日漏曲線外，限價買單可能在收盤反向後仍於隔日成交，賣單也可能依過期收盤持續被拒。原outer SHA `f5224bc62e4eedb4fc4093bdd21298f5dafd33bce4d209716ff0b595db3f770b`與完整原輸出保留，未改原試用者資料。

Root先核Look-ahead及精度：成交只用原訊號、當日開盤及前一已完成收盤；修復將原fill block置於非unfilled分支，兩路再走原收盤取消／風控／估值，不改成本算式、Decimal邊界、漲跌停、量能、整手或partial-fill既有語意。重用Luna只讀三檔複核，無阻斷、pending writes=false；金融裁決與整合由Root。未新增API、UI或來源用途資格。

QA142新反例五PASS及八受影響既有時間／成本／fill守衛PASS；future追加案因Root測試fixture的index無date名稱而FAIL，原frame equality斷言保留，outer SHA `64ce3051ec2447f355f0d39d9558bae49fdb13440413867b681376e82e87f221`。QA143將fixture日期索引明示沿producer的date名稱，六新反例PASS，mypy單一受改檔及financial float boundary guard PASS；未重跑已過且未變的八原案，outer SHA `910241889b6975462c578af85ec25894b49f8df9ae889bf6c57aea2e7e71d15f`。所有組仍8GiB／12程序／RAM≥8GiB、三PID陣列空／handles關閉／mutex釋放，無forced cleanup。當前試用入口仍固定3d；新固定候選的正常Main保存／fresh回訪及交付接線待驗，尚不授新版EXE接受、真人或完整Gate。原完整第二階段與四流程凍結不變。

QA144已建固定6ebe候選，outer SHA `aac5032e1415886b904830b42fef75be03199fb117b2021240f6a47c5dafffa6`。QA145正常UI的17日情境沒有有效分數；QA146延長至419筆仍全未知，兩FAIL保留（outer SHA依次 `2711f5a5acdd62fcdced48cc8f2ba97b25d66d781fc88cd70641c5e34d7e2616`、`89123bc167ebd3195dbc810c489173ef0a301a5a7770b0404aec9e2c61790748`），不是暖機不足已定論。QA147沿6ebe EXE唯讀真2317／419列確認：原known score=0，原MACD_signal有419觀測，只在記憶體將同一欄加MACD_Signal別名後known=392，DB bytes不變；原件v1_macd_alias_qa147.json。原重用已停用重新計算，卻未提供重算既有的正式別名；新反例1FAIL／2PASS，outer SHA `3a7e67ec8d450a99cc032058ec7b61a65d5f57720852457d89733383be2fd243`。

只在原indicator_reuse別名map補MACD_Signal→MACD_signal，既有欄存在不覆寫、來源NaN不補、參數／版本／觀測門檻與scorer完全不改。這解除同一V1-04實際無法形成有效訊號的接線阻礙；不新增資料或放寬缺值。QA148原5＋新3重用測試、單檔mypy及float boundary guard PASS，outer SHA `e78cc57cd6f0e7b895730f0ac0e863c4d945afb30a56c312afdd9b18dde5c3a3`；同一Luna僅靜態三案／四必要檔複核，pending writes=false。6ebe候選與所有失敗保存，新固定來源／EXE正常保存／fresh仍待；不修改已保存舊run、不升格來源／PIT或完整Gate。

QA149已另建最終固定`42b0d1dde8ec9569ae74b45120fd33ca6a83b5be`（outer SHA `fca51be0529eb73d81ddbdbc82844d5af3547e79a8e0d191aebfa680c47f4131`），EXE SHA `e1c2adefb0fc469cf6b7d4566f94b351713c0c99b891242db2735275a2a67cf5`。QA150真2317已驗419日期／392有效分數及低本金未成交帳務，但Root提前收合保存按鈕所在設定而曝光FAIL；QA151恢復先保存，低本金正常保存／歷史／返回成功後，Root又誤把隱藏collapse當expand而FAIL。兩outer SHA `3cbd73c38881cc7a7fdd3efc65aac3ab55453c5ee76f636c946668533a46f1d9`、`b9d713960218ade8c61d7a7733bdb8e5cf41d2d07a4e0d4772fdf5cdbedf7c22`保留，產品沒有為此修改或放寬原15秒UI／120秒phase及Qt裁切／Win32 PID。

QA152重用QA151已正常產製／保存的低本金run `single_backtest_20261015_015855_4085625d`，不重跑producer；用原「展開左側設定」接續高本金真買入run `single_backtest_20261015_020048_38eab90e`，父44272→fresh16568讀回兩筆相同metadata／equity／trades。各419日與真資料日期逐一一致；10000本金零成交／零成本／期末10000，高本金原費率14.25bp／滑價5bp的1筆實際買入、成本176138分、現金83238.62、期末含未平倉估值1363238.62均守恆。不是完成進出場配對或已實現獲利，歷史PIT與來源／金融權威仍未接受。20不可變輸入及行情DB bytes不變，未接網路、未寫試用者清單；outer SHA `473c20f381a142ef43dcb3c5fa6d5cf31975b97881e8c7e941bbdcaf1a93fce2`。

QA153先核3d交付SHA `20fa82f61ee3cf363db938333fcbdd2b39536822dd571071b1503bf2ba7a5408`，保全九原件到v1_delivery_snapshot_increment35，核新archive／Git path-filtered blob、候選資源與7093檔清冊，更新原common入口並--check讀回42b及原隔離根；outer SHA `b159dbdbaa61b7f2fabbf611a83f5ac0c94e4c6d310e53a408e9a292f1cb955e`。初次新收據SHA `71dd8d8f603a28773021a2bd63e884da5d7b94f8f2963f5e808a7e8a1b256f72`與指南另保全v1_delivery_snapshot_increment36_initial，才補列已發現的既有「無任何交易」文字判讀問題，重綁新收據SHA `3d3bcc9ea65856ebe9b0e99ee0ffe3a254a88725946a3cdcfac0693f6aaa43e4`。數值／EXE／啟動器／資料與四流程不變；交易次數仍按完成配對，未平倉時文字不精確已明示，沒有以文字修飾把0配對變成交或把估值變已實現。其餘三旅程及Startup沿原未受影響收據，完整第二階段保留；最後獨立只讀及文件結案另驗。

QA154獨立只讀結案通過：固定42b／EXE、新收據SHA 3d3bcc9ea65856ebe9b0e99ee0ffe3a254a88725946a3cdcfac0693f6aaa43e4、8交付檔／63具名pins、舊3d九原件與QA153初次兩原件、兩run及原保護檔一致；九文件12features結構核對errors=[]。outer SHA 04416e2f9ccf34017cc94b6f229710b1a807974d044b5d3568a944b41cbcfec3，自然三PID陣列空、handles關閉／mutex釋放，無forced cleanup。沒有待輪詢Python或worker寫入；本Increment解除既有V1-04兩個阻礙，未增加V1流程或原完整Gate資格。

## Increment37：V1回測零完成配對的正確判讀

本Increment只解除V1-04既有金融結果判讀阻礙：`total_trades`是完成進出場配對數，原畫面對已有買入／期末持股的零配對誤稱「無任何交易」。依原計畫§7.2改為「尚無已完成交易」，即時報告另列原明示成交筆數及期末持股；缺欄位為「未提供」，不由空配對表補零。歷史頁保留既有保存格式，只說明零配對不能推論無成交。未平倉權益不是已實現損益；原SOP、Promote、時間、精度、金融計算及Registry契約不變。

QA155十個反例在原程式全部FAIL，outer SHA `4761b14be6769e202ec258ac3d08c8611b43169d6f7de3f5cf0124774b8f9ca9`。初修QA156新10＋原presenter3＋Workbench85共98 PASS，validator25／0／4及mypy1016通過，outer SHA `1f57c3688824ca559490f8e3f0594605cc788deb51bf3c1e8aa000d6f95eeb8d`。重用Luna靜態複核指出缺門檻／NaN仍可能誤判；補反例的QA157保留1FAIL／102PASS（presenter格式化None中斷），outer SHA `1b24d03fab2c3a68639483cc0b246eb827d5e22d60b3bd4749956d717ffb54d6`。修復後QA158原斷言及新缺門檻／未知模式／缺持股與分位數觀測共103 PASS；compile四檔、validator25／0／4、八roots mypy1016通過，outer SHA `4a65cd6a8e4d10bddae5145e9bc4d2f892c62fd386c10c5ebc7fa48fa287a965`。既有ui_qt ignore_errors不證UI強型別。

只有明示零成交、零期末持股、有效分數及完整門檻觀測才保留既有研究診斷；不以預設門檻臆測原因。各Job8GiB／12程序、RAM≥8GiB、自然三PID陣列空／handles關閉／mutex釋放，無forced cleanup。固定新EXE的受改回測保存／新程序重開待本Increment後續具名收據；未受影響三旅程與金融案例不重跑，第一版仍四旅程、第二階段及所有原FAIL保留。

QA159因Root建置argv下標錯誤，在argparse階段拒絕、尚未建置，原FAIL outer SHA `eb36d9130bbc198b8237f749b61cf60784c02068bf411d75af61566197e0f5a2`保留。QA160另用完整明列argv建固定來源 `9fa4518c2aca87beaddef75a2b29165722da6a6c`，EXE SHA `3b0c93147979b72bd4560b4bd1262e23e86b68d8ae8e8df4357d7d213f6e06fe`，outer SHA `daffe28e4a93d8eadbaeb7675f74cba972fdb6ba357c096be3912bbadf4fe902`。與42b執行碼差異只有BacktestView及presenter，金融核心／reader／ports／保存格式不變。

QA161新固定EXE正常2317、2025/01/02–2026/09/23、本金1000000、費14.25bp／滑價5bp、buy/sell0及確認1：419日、1筆買入5000股、0完成配對、成本176138分、現金83238.62、期末權益1363238.62與原42b真情境一致。即時摘要明示成交1／持股5000／尚無已完成交易／未平倉估值，沒有無任何交易或降低門檻診斷；正常保存run `single_backtest_20261015_022340_ef5b443e`，父30640→fresh48700沿歷史／返回讀回同metadata/equity/trades，identity `4db5e4598323aafef3aa6f26e80be8a12d3facdf7bf4add801106e3bb37b425b`。歷史摘要只標完成配對與零配對不等於零成交。20輸入及實際行情DB bytes不變，禁止自動連線，原15秒UI／120秒phase／270秒driver及Qt裁切／Win32 PID守衛保留；outer SHA `5b9b8709279a2ffa6ec512915f61a04173f9568773b128e9cd6b8b92f95f1a19`。

QA162先核42b交付SHA `3d3bcc9ea65856ebe9b0e99ee0ffe3a254a88725946a3cdcfac0693f6aaa43e4`及九原件，保存owner的v1_delivery_snapshot_increment36；才更新同一啟動入口、指南、build收據及7093檔清冊。common --check讀回9fa及原隔離設定通過，新交付SHA `0cc49abbf81d24981ba06841948f9ee7352699d22eb165a0f85a51d56feb804e`，8交付檔／75 QA pins；outer SHA `b37231441b7e033478be69cf8b68afbcd369809370e3ea270980c513062abd0f`。以上自然三PID陣列空／handles關閉／mutex釋放，無forced cleanup。Luna最終只讀複核確認主要阻斷已修，pending writes=false、累計9/10；另指出矛盾的quantile觀測邊界未全面防護，明列第一版非主要驗收／不作績效調參依據，留第二階段，不擴張本次固定門檻旅程。主架構已複核：純摘要顯示，模組邊界與資料流無需變更；其current分冊、操作手冊、功能、Snapshot、portable及原計畫同步。真人試用及原完整Gate仍未接受，沒有正式寫入、push、發布或交易。

## Increment38：P08雙策略逐日原觀測明細

使用者澄清試用與原完整補完須並行；先前等待真人回饋才繼續的判斷撤銷，歷史audit01–03保留但不再作阻塞。固定9fa第一版與收據不變。此Increment為第二階段原P08／§7.2解除「已有逐日精確capture，正常比較頁卻只列身份／缺日」的產品使用缺口，不追加為V1前置，也不是全線停留的另一個視覺小修。

沿原public exact pair結果，在同頁新增13欄逐日原觀測：日期及左右各自股票、現金、持倉估值、權益、原可選已實現／未實現P&L。日期用兩run實際聯集、每頁100日期，不從expected calendar補造；Decimal文字逐字保存，不經float／差額／報酬計算，缺日為「無觀測」、None為「未提供」。本金、幣別、期間與completion各自標示；資格、blocked原因、metadata雙SHA、generation/cancel／Registry wire與金融核心不變。返回、重選、重試、取消或新結果清除舊明細。Root凍結API、Luna重用僅寫widget與新測試，原測試未改；最終pending writes=false。

QA164角色／context核對通過，outer SHA `54cd8a22160f7215652a212ab1efefe659fc5c868c0e429819b5482536f4793b`。QA165兩檔compile及新3案、既有widget/controller14、Workbench85共102PASS；Root把fixture插件模組與消費它的daily測試併跑，造成16 fixture errors、整組FAIL保留（outer SHA `edcadeb56119a8c71f55e75a2a4c720d2fb49d97902e69cd51c9e768b9bbaf76`）。QA166按原pytest_plugins契約單獨跑daily16PASS，補未跑validator25／0／4及八roots mypy1016通過；不改產品／測試、不重跑102案，outer SHA `0d1367e3a7b21e8694d571396e4c55a1d83bdad5e1334d137d6471f6146fe88e`。新三案包含超2^53小數、負P&L、None、異股／缺日、extra expected date不補入、201日三頁及清空／換選取；這些不是完整P08 Gate，既有UI ignore_errors不證強型別。

QA167正常來源版Main父15212→fresh39456，重用QA41兩個原V3 run與QA72年度合成binding，不呼producer、不再保存或抓取。正常Registry單筆重開→雙選／固定原年度批次→public pair→新逐日明細→返回→新程序同身份完成；13份config／Registry／附件／年度來源的bytes／SHA／stat一致。3日×13欄父子完全一致；原本金9007199254740993.01與9007199254740994.01、期末現金5.16／6.16及各自權益按原capture文字讀回，P&L缺值未補。來源／幣別／日曆／績效資格仍blocked，沒有宣稱兩策略獨立盈虧、完整成本／PIT、Native／EXE或真來源已接受。原15秒UI／120秒phase／270秒driver及actual PID建立時間／named Job membership／自然terminal守衛保留，outer SHA `51ddb405690681053126ff8d7b91551f19c5c0c01ffd70426963353eab312e11`。以上每組8GiB／12程序、RAM≥8GiB，三PID陣列自然空、handles關閉、mutex釋放、無forced cleanup。

操作主手冊、Registry指南、功能、current架構與原計畫同步，明示此為後續開發分支，固定9fa試用包不含新明細。另一路P06靜態複核已定位既有project_rule_only、精確估值、帳本identity與現金／Health／quote時間缺口；先核來源路由，不能將分帳selector當作已載入snapshot、缺Health當HEALTHY或缺cash當0。這是下一段正常帳本→研究情境→真保存／重開的實作輸入，並非已完成P06。Luna累計10/10、兩名本輪worker均無pending writes，後續優先重用，禁止新建。正式資料、交易、Task、maintainer、push／發布及原完整Gate均未變。

## Increment39：P06 封存情境接正常 Portfolio 與 target 另存

本增量解除原 P06「完整情境已有計算／精確估值／canonical 封存，但正常 Portfolio 無入口」的使用阻礙。屬第二階段原產品出口，與真人試用並行，不新增 V1 前置；固定 9fa 試用包及交付 SHA `0cc49abbf81d24981ba06841948f9ee7352699d22eb165a0f85a51d56feb804e` 保留。

沿既有 `PortfolioResearchScenarioService`、`PortfolioResearchValuation`、v3 artifact／v1 private store；新 workspace 只組合 exact 開啟、原事實的明示 target 比較、原 append 另存。只改 explicit_weights，原 account、完整 context、candidate universe、cutoff、source hash 與 turnover 不變；所有原情境 allocation_policy_hash 必須等於現行，否則可讀但拒絕重算。保存再核原件及預覽 canonical bytes，不寫交易、Paper、Health、正式市場或 Task。不建立另一套 Registry。

Root 實作／金融、時間、Data Audit 與文件單寫；復用 Luna9 只寫新 UI 葉片及其測試，Luna10 只讀 workspace。累計 worker 10/10、無再新建，worker 無 Python/import/compile/QA/network。Luna10 實讀後未見 blocker，確認同政策與 preview 全文守衛；hash 證明封存內部一致，不是重新核外部 Paper receipt、Health 或行情權威。SQLite append 開始後不可取消，UI 等待保存終態；read/compare 取消不寫入。

- QA169 route/context：high risk；Execution、TestingQA、Documentation、TechLead、DataAudit 及四防線。首個 shell 因前組收據誤填 output/qa 路徑在 Get-FileHash 即拒絕，未啟動 Python/Job；核原件在 owner task 後沿同 spec 真啟動 PASS。outer `single_owned_qa_ee7d809a174d4ab888e17dea125dbf0d/receipt.json`，SHA `b8c4539d5b7ce99d2aaef87fbdaf195ca2373831d641229e5ff74adf73d90824`。
- QA170 backend：修改三檔 compile、workspace／既有 artifact-store／P06 scenario 101 PASS。覆蓋原件保持、new target／新 hash exact 重開、錯帳／未選股票拒絕、取消不保存、偽造 preview 拒絕及 policy 改版只讀。outer `single_owned_qa_a990cb29414e4c2692ec488be9dd62f6/receipt.json`，SHA `a754bd0ed7d27284267a14101b6265550ee2150595193b93090d1b32634e3e3d`；preflight 27,331,739,648 bytes available。

以上 outer 路徑均在 `output/tasks/baldr-completion-resume-20261014-01a13cf9/`。兩組沿原 8GiB committed／12 processes／kill-on-close／workspace mutex，三 PID 陣列自然空、process／Job handles 關閉且 mutex 釋放，無 forced cleanup。正常 UI／Main-fresh 及文件終驗仍在此增量後續收據；尚未執行的項目不當 PASS。

界線：此輪從既有完整封存重研究，空庫不造樣本；初次帳本／Health／行情可得性 public reader 組合與原 Registry 交叉入口仍未完成。TPEx、歷史 PIT、真 N、完整雙策略、正式資料、自然成熟、Native／EXE 與全 P00–P14／G0–G4 各自未接受。

Increment39 UI 收據補充：

- QA171 compile 通過；UI 兩個新案例停在等待，其餘 123 PASS（含原 Portfolio 與 Workbench85）。整組 FAIL 保留，validator／mypy尚未執行。outer `single_owned_qa_6c2acb77c62940608eb2eac763666b00/receipt.json`，SHA `8fd93abd4f43546ffd6adee2ddebf3d0595c4723d0dd26070ac21266a1f066de`。
- QA172 有界直接 Qt 診斷：同 workspace 載入／tuple result／native finished／清單都正常，PASS。outer `single_owned_qa_93dcbce5678c4378a4052cafabd87c98/receipt.json`，SHA `fb0faf5a05b6a40fd62c6364bb1b960870ea02ce9a74e93aa599349c4ed3c385`。
- QA173 保留原 pytest 斷言及 8 秒，只在失敗時輸出狀態，FAIL：worker 仍在等待，無錯誤回呼。outer `single_owned_qa_ac6f93e1fa6948cea9596f35db65d374/receipt.json`，SHA `db6c61e0233c4054a148c1d98529d205a28abd1c6043b17bdc169f4aa5241dfd`。Root 定位新測試 QTest.qWait 的 GIL 排程問題，改成 time.sleep(0.005) 讓真 TaskWorker 執行；原 8 秒期限與斷言保留，產品程式不變。
- QA174 新 UI 三項 PASS、一項 FAIL；原件 mark_price 由既有估值 canonical 化為 `100`，測試誤期待 `100.00`。未改 UI 補尾零；Root 改測試同時核原 DTO 與畫面為 `100`，保留其餘精確現金／NAV／市值及回訪斷言。outer `single_owned_qa_af014811e7034adf8a452a65b1f00b8b/receipt.json`，SHA `c3a0135b9dc12914aeae910c2d83f97974a813b5a0054cf1e81a886a4b834eac`。
- QA175 只重驗該案例 1 PASS，未重跑既過 123／3；validator 25 PASS／0 FAIL／4 SKIP，八 roots mypy 1018 檔通過。原 ui_qt.* ignore_errors=True 不證 UI 強型別。outer `single_owned_qa_d3b8969706ec47d69f107e32c5d2ec79/receipt.json`，SHA `8e30952faf4e1e438ba3962af06b9b98771eb5b08cbfabe89abc3ba858593622`。

上述診斷／失敗／恢復均保留原輸出，沒有放寬資料、斷言或期限；五組三 PID 清冊自然空、handles 關閉及 mutex 釋放，無 forced cleanup。未以案例加總授完整產品 Gate。

QA176 正常 Main／fresh 已限定通過：父 actual PID42420 以正常 Portfolio 分頁明選原 paper/account-a 封存，調 2330=1200bp／2382=800bp／cash=8000bp，比較並按另存，再由實際個股入口返回同 artifact；正常關閉後 fresh actual PID38196 以同帳與 hash 明選重開，原／新 comparison canonical 內容、精確現金900000.00／NAV1000000.00、股數、原時鐘一致。fresh 將 compare／append 改為拒絕以證只讀，scenario DB hash 起訖不變；錯 artifact restore 拒絕。640px 主視窗及真可見按鈕座標命中、合作關閉與0受管worker通過，Python socket 零嘗試；沒有 OS 網路稽核或 Native／EXE接受。初始完整情境由隔離fixture寫入，不冒充已完成正常UI首次建立來源。

Root helper `p06_scenario_main_fresh_39_a.py` 重用原隔離 root／socket guard 與 exact native Job membership／PID建立時間／程序退出核驗；parent→fresh 前核 actual process terminal。同 named Job、原8GiB／12程序與mutex。outer `single_owned_qa_2955d34bb69149f48fd2710dcb3e29bf/receipt.json`，SHA `a709434c4d086fa8abecb856b5c2dc9195ee69a6bf8a1484ca2b1d5886f9507f`；三PID陣列自然空、handles閉鎖、mutex釋放，無forced cleanup。原始 parent/fresh 在 owner `increment39_scenario_main_fresh_a/`；parent SHA `1a6fe9f0ed5a1c4ab0075e0a7710614f25032ef829473fd86245bcc1f9a3220e`、fresh SHA `9f619be0b8c7d2d8a5cada86624f144a40e70614038c77028c1ea1144c2d22f3`。

文件已同步主手冊／持倉分冊的入口、明選帳本、bp參數、原證據判讀、另存／返回／重開、取消與空庫／唯讀／政策錯誤；更新current兩分冊、功能文件、Feature Map、Snapshot、開發導航與原計畫§7.1。無新增配置／store schema／安裝／Task變更，安裝移機文件及固定V1指南不需修改。下一段仍沿原計畫推進，不等真人試用回饋；沒有完整 Gate 接受。

QA177文件終驗 PASS：12 features／10本輪來源，context metadata 30 links sources，errors=[]。outer `single_owned_qa_59641b01383143819c1db0c1ba0c0e47/receipt.json`，SHA `e8b0869ce4b0aa395a7dfc9c978da89d6ea6a357c72c31398eb732a2b4bf4bae`。Root另核QA169–177九組收據SHA／自然空PID／handles／mutex及8GiB／12上限，固定V1指南與收據、舊task及其他owner原件SHA一致；完整Gate仍未接受。

## Increment40：P07／P08新實驗綁定真策略版本

此增量解除新回測、規則卡、Walk-forward 與參數掃描把兩個實際登記 `1.0.0` 策略寫成 `1.0` 的版本錯誤；會造成規則卡失配及新保存 run 身分失真。沿原 P07／P08 修正，屬第二階段，與真人試用並行，不新增 V1 前置或重打固定9fa。原完整範圍、來源權威／PIT、完整雙策略績效與自然成熟仍各自保留。

Root 共用 `registered_strategy_spec()` 只讀 public `StrategyRegistry.get_strategy_meta()`，核 id 與唯一明確版本，深複製原 config；不造 executor、fallback版本或新的金融邏輯。BacktestView 三個原 StrategySpec caller 共用；Optimizer 在讀行情及提交組合前凍結本輪版本。基準仍1.0，暴衝／穩健各1.0.0。舊 run 原樣；原 params、成本、風控與時序不變。Root金融／資料／整合與文件單寫；重用 Luna9 僅寫新UI測試，Luna10只讀P06來源，累計10/10，無新建或子代理。

以下 outer 收據路徑均在 `output/tasks/baldr-completion-resume-20261014-01a13cf9/`：

- QA178 route/context PASS，outer `single_owned_qa_2b3a779f910146ccab7095b97a5c3b03/receipt.json`，SHA `95a70cbd840a5613638ba925bca1df7fd4ac70dbc9194146bfee2adc03c5eadc`。
- QA179 compile與核心69 PASS，涵蓋真版本、7類無效metadata、deep config隔離、Optimizer開始前凍結及取消、既有規則卡／執行協調與run metadata。outer `single_owned_qa_599700f41c504ec4bbba34ca8aafccc0/receipt.json`，SHA `5945d2b6391aef87e7e2ea5100ea491118646ef61f9a86a4c6c9d3f8388f9bfd`。既有取消fixture原策略id不存在，改為真登記基準id，原取消／in-flight斷言保留。
- QA180 UI與Workbench 90 PASS／3 FAIL：新測試在改UI設定後，第二次請求卻仍誤期待第一次config。outer `single_owned_qa_29e2ba11ed52437c9624ea865dedf975/receipt.json`，SHA `831a63abfdca767ca7472b10c2f74fe178ce823cbb3ca869fb5d483f9b456608`。Root改成第二次使用當前設定且第一次spec維持不變，產品不變。QA181只重驗該3項PASS、補validator25/0/4及八roots mypy1019 PASS，outer `single_owned_qa_67577f89442a4acc94088b94e6cde933/receipt.json`，SHA `c44b80155b15434825cdf383bf2e06dcf274e4a4f3775768b912835f7bcff801`；沒有重跑已過69／90。既有ui_qt.* ignore_errors=True不證UI強型別。
- QA182 FAIL於Main之前：QA誤用舊QA86對mutable runtime DB／指標cache的初始pins，bytes已非該版。outer `single_owned_qa_22e42aa31221452488317beabf80eee4/receipt.json`，SHA `afac0fa790b5d9da4a4dc71e8c59fe57020ccf9a4d31c09514beb7f13fd6e72e`；保留a helper／partial fixture，沒有重綁或覆寫舊spec。
- QA183 改用當前固定交付收據SHA `0cc49abbf81d24981ba06841948f9ee7352699d22eb165a0f85a51d56feb804e` 所綁INPUT_INVENTORY SHA `172d65e241418963f16beffc76ea5e25b7f53247e512df054367e0f2ca0b175d` 的20不可變輸入。只複製四市場CSV與原source price.sqlite到b隔離副本，原DBManager建表前後逐列價量相同；不讀取／修改使用者試用mutable DB。正常回測並保存後，QA錯要求即時保存按鈕停用而FAIL，outer `single_owned_qa_8dc894f5a11a4ded91e361310bd41706/receipt.json`，SHA `0f7d7e2dcc83926dc47fd87487d476d7a4b8c73220274f8ee657ff55b7f4e52b`。原產品即時結果可另存，exact歷史才禁止重新保存；原b產物／FAIL保留。
- QA184 獨立c helper只修保存等待為run存在；其後完整metadata/equity/trades、歷史停用保存、419日與整數分現金守恆、20來源及所有期限／裁切／PID守衛保留。正常Main父42996→fresh22092 PASS：兩策略規則卡版本1.0.0／無registry_version_mismatch，正常執行→保存→歷史精確重開→Watchlist返回，新程序禁止producer仍同完整內容。momentum run `single_backtest_20261015_114050_dd4e08d8` identity `39700a010f1a2c963714123ae13c73fde6303d835229a0d6162fc9348ef89a65`；stable run `single_backtest_20261015_114050_eea7ef2f` identity `33b30384f80459c9a923256c02d9562bbc21c95b9ae7a1ceba70b8f40aad65b2`。父receipt SHA `0f903f5ea39c0b4c367661a2632a837977a8553768cbce01558191fc01a7dc31`、fresh SHA `e027e992c7dee1ae5d43b105953df2bb9b195e09baa3f4c13897231f1ffc06b7`，位於owner `increment40_strategy_version_main_fresh_c/`；outer `single_owned_qa_7a713c3127884a1292c5ef6b6740f2a8/receipt.json`，SHA `194b1b1c45bbc76504e2ee20c74a3e515311178e8febe8dce3a4ace490d78b50`。

QA184以2317、2025/01/02–2026/09/23、本金1000000、fee14.25bp／slippage5bp與固定0門檻作版本保存工程驗證；不是策略效果接受。四股原始行情衍生於私人副本，20來源及準備後副本DB hash不變、Python socket零嘗試、合作關閉且0受管worker。非OS網路稽核、Native／EXE、正式來源PIT或完整雙策略績效。各組8GiB committed／12程序／kill-on-close／同workspace mutex、RAM≥8GiB，三PID清冊自然空、process／Job handles閉鎖、mutex釋放，無forced cleanup。

主手冊與回測分冊同步入口、版本判讀、另存與歷史重開、缺版本排錯；current架構分冊、功能、Feature Map、導航、Snapshot與原計畫同步。架構全貌仍沿原UI→app→Registry／executor，未新增資料schema、設定、正式Task或安裝依賴；固定V1指南不改，因9fa包未變。P06 Health exact reader只有paper-main identity／股數／Health，缺精確現金／NAV／marks，不能以bp反推或混策略帳；初次來源組合繼續沿原repository查核，不以unknown卡結案。

QA185文件終驗PASS：12 features／9本輪來源與context metadata30 sources，errors=[]；outer `single_owned_qa_16e5a9f615b04122989b1fb433fefa84/receipt.json`，SHA `3c671cb76f6a3c2bf8bf02cda14fd297275b0329924a70dc52a6da5163c85722`。Root另核QA178–185八組完整收據SHA／自然閉鎖與固定V1收據／指南／20輸入清冊、舊task及其他owner原件不變，保存owner `increment40_final_integrity.json`，SHA `cddd4a3cd996d80aafaf417372899e302ebc8b40b9f3d011352aded2b9b78262`。這是限定交付證據，未授完整Gate。

## Increment41：P03法人候選取得解除跨來源前置

原 `capture_recent_flows` 必須在同輪取得 TWSE／TPEx法人與兩個信用來源，讓TPEx授權／回應及非必要信用缺件拖住單一TWSE法人來源。此增量沿原P03／F09解除這個取得阻礙，新增明選 `capture_scope=twse_institutional`／CLI `--capture-scope`，只用既有T86與parser／create-only保存，不另建資料框架或getter。未指定仍保留原 `legacy_all` 四來源。屬第二階段，與試用並行，不增加V1前置；固定9fa／交付清冊不變。

Root API凍結於owner `p03_institutional_scope_api_41.md`，Root單寫service／CLI／資料與金融裁決／整合／文件；重用Luna10只寫新測試，交回SHA `95c2c26d7367469c512e84d423a4cf691dc6c5fe5ee196540b55cfdd18a76337`。Root接手後補5個篡改／分區反例及舊無scope相容，未改原測試。Luna9只讀定位，已指出候選與revision reader之來源版本不一致、欄位available_at與正式schema差距，以及原daily snapshot限MOPS／HTML，不能拿來硬cast法人JSON。總新建10/10，無新代理、worker無Python或網路。

manifest／readback新增具名scope，明列markets、source_ids、endpoint_ids、excluded_endpoint_ids與selected_endpoints_only；未要求信用不產生0筆資料集。TWSE-only discovery沿原T86，實際抓取重用該回應，每日期一次；不呼TPEx／信用。scoped rebuild核scope全文、endpoint source／market／version／unit與各日期完整分區，缺件／重複／擴市場拒絕，原raw及manifest不改。舊無scope封套保留原重播語意。無金融公式、數量單位換算、正式apply或downstream資格變更。

Root先核歷史attempt資產：`output/data_completion_20260909/flows/runs/20260909T051132394061Z/manifest.json` SHA `2c25065e529e38a23dc6e773a236a05bd7a681cc37fafbeeb239d4cfdfba548a`、`manifest_with_observed_at.json` SHA `308169e7b42b65b0614bf08dd74942d925b1caeed380a67eadc9bb97625a4e41`；原10日、candidate-only及需用途接受保持。guard另存owner `increment41_legacy_capture_guard.json`；沒有重抓、改舊件、重置月營收或TWSE舊GET已耗scope。這輪全部注入離線fixture，不是新官方HTTP成功證據。

- QA186 route／data_pipeline context PASS：medium risk Execution／TestingQA／Documentation，Root另履行DataAudit／TechLead。context只摘錄部份正文與代表入口，未讀項不當已核；Root另外讀現行資料指南相關正文。outer `single_owned_qa_836217e07acd40c8b370997d986eb626/receipt.json`，SHA `51d75e04fc4845b9fd2182c475992b5997dd009a7155248a31edf42b9718355c`。
- QA187 三個修改Python compile、新scope／CLI／rebuild及原service共15PASS、兩來源mypy PASS。涵蓋每日期一次T86、原bytes/hash、整數買賣超守恆、非法scope在output／transport前拒絕、無TPEx／信用、原件保持、重播範圍、舊default與無scope相容，以及市場／單位篡改、缺／重複分區／多報日期在新保存前拒絕。outer `single_owned_qa_ba1bcc8e56e849cfac7994a632743d65/receipt.json`，SHA `73e389bc6a651751c4c6161901488457032d1657203a860ccf812ff6cbfe5ebc`。原4案未修改，沒有UI變更，不重跑已過Workbench／八roots UI防線。

各組8GiB committed／12程序／kill-on-close／workspace mutex、起始RAM≥8GiB，三PID清冊自然空、process／Job handles閉鎖、mutex釋放、無forced cleanup。只證明選定候選取得／重播工程，不授來源單位或用途接受、完整市場、當期資料、自然更新、歷史PIT、Native／EXE與完整Gate。

操作主手冊、資料分冊、每日更新指南、current資料架構、Feature Map、功能、Snapshot及原§9.5同步。未改模組邊界、正式schema、Task、排程或安裝依賴；主架構與固定V1指南不需改。下一段沿單一TWSE原件→品質／成功批次保存小時→固定版本public reader→正常UI/fresh。原candidate available_at只代表個別response／官方時間，尚非新daily-hour，不能回填歷史或直接送另一版本的revision reader；本選項不算完整F09，缺值不造零。

Luna9最終只讀複核未見本次範圍內回歸或阻斷，確認TWSE-only、無未要求零值、scoped重播及舊版相容，pending writes=false。QA188文件終驗PASS：12 features／9本輪來源及context metadata30sources，errors=[]；outer `single_owned_qa_04e6435a7ba1469c981afb85c1c34281/receipt.json`，SHA `9bdc155f80f2f9caf370b569d6bb8a93a27db279cdfcc42d0dd0a79211231c22`。準備曾因Root誤用task欄位在PowerShell拒絕，當時無spec／Job／Python；改用現行scope_files才啟動，本機task保留紀錄。未執行真來源或UI/fresh，不以文件與案例通過授完整F09／Gate。

## Increment42：P03法人成功批次與正常唯讀頁

此增量解除原P03／F09候選只能capture／rebuild，缺成功保存小時、固定public reader與正常數值出口的交付阻礙。沿Increment41原T86／parser／candidate及既有create-only／時間policy，沒有另建取得引擎、金融公式或讓Scrapling成共同前置。屬第二階段；真人可繼續試用固定9fa，回饋不是其他補完工作的前置。

Root凍結owner `p03_institutional_daily_api_42.md`，單寫transport／共用ports／金融裁決／整合／QA／文件。重用Luna9測試與Luna10純widget，無新代理、總10/10、無子代理／Python／network；Root收回ownership後補實際worker測試、整數／原件／時間及取消反例。widget最初交回SHA `7de9ac2a40fb04de879abe57182a5f9a865609b0e0d4a1b3cc99370e93ff65e2`，後由Root加載入清舊結果、資格守衛、時鐘文字與原件tooltip；最終來源pins另存owner spec與integrity。

原transport改有界stream並保存EOF／宣告長度／encoding證據，上限與原retry／deadline保留；壓縮舊capture仍可讀decoded body，新seal拒壓縮而不冒稱原HTTP bytes。`institutional_daily_snapshot` 重播原parser、核原scope／單位／版本／全日期、quarantine=0、candidate全文及readback，拒舊件缺EOF、body或來源漂移。只在指定候選run旁create-only保存daily manifest／receipt，原capture不改；原件前後重讀bytes／SHA／完整signature，mtime還原也無法繞過。成功保存clock沿台北小時政策，最終完整再核驗後取clock且須早於可用小時；取消／跨界失敗保留pending／failure，雙外部SHA reader拒讀。批次完成欄位是檔案handle關閉／驗證後取樣，不宣稱另存最終unlink時間或OS crash原子性，詳來源契約。

正常UpdateView法人區沿原TaskWorker → UpdateService → exact reader；widget無I/O／金融運算，只呈現選定代碼的11欄（日期／代碼＋三類9個整數股數）、雙SHA、時鐘／basis與來源tooltip。變更輸入／取消有世代守衛、清除舊結果並合作收尾；成功零匹配與未載入分開，無補零／latest fallback。報表列總數可含非股票證券，不是股票universe或真N；source_use_accepted=false／historical_pit_eligible=false／candidate-only保持。沒有日曆連買、正式apply或既有狀態卡升格。

以下outer receipt均在 `output/tasks/baldr-completion-resume-20261014-01a13cf9/`，不改舊task／spec／結果：

| QA | 限定結果 | outer receipt／SHA256 |
|---|---|---|
| 189 | UI medium route／context通過，Execution／TestingQA／Documentation；Root另履行DataAudit／TechLead。context預算略過項明示，相關資料指南正文另讀。 | `single_owned_qa_39bc70439a7146b29a7c054117cb0e30/receipt.json`；`31a84367cf474ed3128c83780d75f64bd6bdf4dd212e62cb642908b47dd60938` |
| 190 | compile5通過，核心21PASS／9FAIL保留。Root adapter誤把原分區品質定位在grouped source，實際在sessions.merged；失敗未抹除。 | `single_owned_qa_bdbab7848ae0412aa1b838c83c6a886b/receipt.json`；`9e5ca31f45e42f540db7a7095da4ecb8d379cd93e08c778482acb6347949558a` |
| 191 | 修正到原schema品質位置，不降斷言；新核心19PASS、compile2。重驗原先被早期錯誤遮住的反例，另加pending、mtime還原但bytes變動、整點guard、大整數。原15舊scope／service回歸在190已PASS，未重跑。 | `single_owned_qa_bbd1c57ee1274a3c9f4746b2229200c2/receipt.json`；`3804d1f30d020f9c8e3816179f31470dbf7f43f8de5863bc0da7691dda7054ba` |
| 192 | 90PASS＝新正常UpdateView4＋Workbench85＋壓縮舊transport相容1；compile、validator25PASS／0FAIL／4protected skips、八roots mypy1021通過。既有ui_qt.* ignore_errors=True不證UI強型別。 | `single_owned_qa_a9090a7d49f0410b8d28aa144235aab6/receipt.json`；`25990c61fd3f92352e7cee61afb2c020676c3961c4d5a3fca3ae5c2f1daae9a3` |
| 193 | 正常Main父36272→fresh33544限定離線旅程通過；雙SHA、2日期／2330九項整數及時鐘一致，切Watchlist返回保留，再新程序只讀同pin。 | `single_owned_qa_5131cad75bc145979a3d46b1ebaa481e/receipt.json`；`96d938cd0c0c08a55eb19799690cf7db7a08be1fe14d62d9ddd3b20e67331a69` |
| 194 | 最終檔讀取期間才取消的seal／reader兩反例，加完整再核驗跨可用小時1例，共3PASS；compile2／單來源mypy通過。 | `single_owned_qa_c2925ff7a57d492faed3e752fd3ab8f7/receipt.json`；`4ad38b97a0fe22f10ef0b13371daadb1e7f6b38ef5a379ae447afb381b4ec4a4` |

QA193 owner `increment42_institutional_main_fresh_a/` 的parent／fresh SHA分別 `e5d496036150f0b7e099e469cbaeb3879166a540b6aaf13a552d6bcfd972867d`／`72ceea649fc7ffa93402a9f573e6424dc412f09387b32d474b54e1d2fe9cc8d0`。合成transport／時鐘／兩日期原件經真正capture及seal，正常Main實際法人tab／可見開啟按鈕與新程序走public reader，未以fake reader代替；10原件bytes／SHA／mtime／ctime不變，Python socket零嘗試、worker0且合作關閉。私有Main缺行情DB／company的warnings保留，不用其他資料fallback。固定15秒UI／120秒phase／270秒driver、實際PID／ctime與同named Job檢查不變。這是offscreen source版證據，不是Native／EXE、真HTTP、來源用途或PIT接受。其後只補最後取消與clock取樣順序，受影響三反例於QA194定向驗，沒有把QA193冒稱最終byte版完整Main重跑。

本輪期間既有外部checkpoint `9a769a1294feec594ca4a371be5ae60885329709` 保存了部分WIP及其他owner歷史文件；Root不修改或revert其內容。QA194 spec已核該HEAD及當時11個實際byte pins，finalguard／UI／transport改良及兩測試檔另在本輪整合。保護的其他owner原件SHA仍為 `0e7c4314251277ac900afd4a0d2d5b575005af869af2d012ce865f989ba06983`。不把這筆commit當QA或完整Gate。

各輪Job 8GiB committed／12程序／kill-on-close／workspace mutex，啟動RAM≥8GiB；三PID清冊自然空、process／Job handles關閉、mutex釋放，沒有forced cleanup。只驗受改路徑，不重跑未受影響F17／Backtest等既有PASS。來源契約、current架構、功能、Feature Map、導航、操作主冊／資料分冊／每日指南、Snapshot及原§9.5同步。

尚缺真官方取得及指定用途／欄位單位接受、日常固定成功批次運轉、兩市場日曆／連買／歷史PIT、全市場真N、Native／EXE與完整產品Gate。既有舊月營收／TWSE Swagger／t187ap05_L scope不重抓；T86先核其自身attempt與官方證據，不能把別的scope耗盡或合成PASS當其資格。P06原snapshot實有cash／marks，但缺mark可得性及估值一致性證據，不從股數反推或混策略帳；其餘原包持續，不把unknown卡當功能交付。固定V1四旅程與收據／20不可變輸入不改，正式資料／Task／maintainer不碰。
QA195文件終驗通過：12features／12本輪文件及context metadata30sources，errors=[]；transport最終版本compile通過。outer `single_owned_qa_1cea14067e4d4e76a6052e470cd5f02c/receipt.json`，SHA `8bfbbab0bcfa5ce577fab649dbb8b581f2607bfd929ccf1892a286c88837c864`。Root另核QA189–195七組收據與自然閉鎖、八個最終來源pin、固定V1 EXE／20不可變輸入、舊task／兩版capture及其他owner原件不變；owner `increment42_final_integrity.json` SHA `5e1bb8ebb453dc8ab341711892f805983e4f78025d8383dd19bab79458516455`。文件檢查後只追加本段收據／完整性記錄，不授產品Gate。

## Increment43：P03真T86單日原件與宣告合計守衛

本葉解除Increment42只驗合成資料、未有本輪真T86原件的阻礙，同時修原parser未核官方獨立宣告合計／raw單位的金融品質缺口。沿原P03／F09取得→原件→品質→seal／public reader，不另造框架、不擴TPEx／信用、不新增固定V1前置。固定9fa四旅程及原完整計畫仍保留。

Root先核208個具名attempt／scope／acquisition／ledger檔，未找到本次T86精確scope；原兩run共11份T86 metadata日期為2026/08/26–09/08，沒有本次10/15。清冊 `increment43_t86_legacy_attempts.json` 另存於owner，不改舊原件；月營收GET、TWSE Swagger／t187ap05_L已耗scope與MOPS partial／缺EOF保持，不重置。新 `increment43_t86_scope_a.json` SHA `cda78ba64b892c17d84f223af35e7865b7323c527e7a67107e7d553b3e75d598` 限原 `/fund/T86?response=json&date=20261015&selectType=ALL` 一次GET、8MiB、包含worker啟動20秒、零retry／redirect。原discovery可能迭代前日，owner transport在第二次呼叫前硬拒絕，沒有第二次網路請求。QA196只準備未啟動；Root靜態補HttpResponse必填attempts後另存QA197，不覆寫原spec或消耗額度。

QA197真取得於本機10/15 12:23:44–12:23:48（UTC19:23、台北10/16 03:23），3.718秒完成：HTTP200、identity body、2,709,038bytes、完整EOF、無Content-Length（以EOF為完整性證據）。原受控helper的實際worker／named Job membership、PID退出／handle關閉均核；沒有browser／cookie延伸／WAF重試。HTTP收據 `increment43_t86_official_a/attempt01/receipt.json` SHA `ecd98a422fe9862dfe29af5e56c63ab24c60ca70d2ba5a7e845cfebc22a853c9`，raw SHA `32742e7c2e4d70ff9c79449dd6259a8e9564b06a13932d1a6d50adc16b28edcb`。本輪所有相對產物均位於owner `output/tasks/baldr-completion-resume-20261014-01a13cf9/`。

原 `capture_recent_flows` 重用該同一回應，保存run `increment43_t86_official_a/candidate/runs/20261015T192344979347Z/`；capture manifest SHA `fb63e56af7ae3af00878cb36ac712257839ee82c0f7d4ec81126f153543f9b6f`，21,000 accepted／0 quarantine。daily pin為該run的 `daily_snapshot`，manifest SHA `75684454b233dd6e0f05f142007774b0660b233053b154f7c995231d1ed7d582`、receipt SHA `f882fb50339ece3288b8f519513be7cbcfdd1841755a0f3c0ef80ecdd3901c8b`。首次保存台北03:23:50.596781、完成03:23:50.614531，無官方publicationTime，明示successful_batch_completion_fallback，最早04:00可用。QA197以真正當下cutoff得到正確提前拒讀，不注入未來時鐘；保存不等於立即可用或歷史PIT。

QA198獨立只讀核原全部21,000列：19唯一欄、股單位、唯一證券代號、每類買減賣、外資自營／自營自行及避險、官方自營合計及三大合計、全candidate九個整數值皆一致；2330／2317／2454／0050留原數值，15個來源／取得檔bytes／SHA／mtime／ctime不變。原body含ETF等證券，這是報表列總數，不是股票universe或真N。原notes的統計範圍及未按錯帳更正調整限制保留，單日買超不推連買。

原parser只驗重組後買賣差額，可能忽略另列合計矛盾；本次加獨立宣告自營／三大合計交叉核驗，原body有hints卻非「單位：股」即拒絕。每日seal／exact reader還要求原body單位、唯一欄名與兩個合計欄，metadata的shares常數不能自證單位。legacy缺欄候選原解析相容，但不能新seal或exact-open每日版本，舊artifact不改寫。新8反例涵蓋2錯合計、3錯單位及3缺原證據；錯誤原件保留，無成功manifest／daily產生。共享合成fixture原三大合計69與55+10+5矛盾，修70並加原件股單位；所有原斷言及9007199254740993精度案不變，不降低守恆。

| QA | 限定結果 | outer receipt／SHA256 |
|---|---|---|
| 197 | 單次真取得、原capture／品質／seal及提前真clock拒讀，helper compile通過；未授用途接受。 | `single_owned_qa_97e32ab56c554c949a5493e82761d81c/receipt.json`；`678d4f3a732ae4b9608acbb6ed2cfec8c1d4106fe9df78d1e97db69b7dab2c68` |
| 198 | 全21,000列獨立原始分類／合計／candidate核對與15來源不變通過，無HTTP。 | `single_owned_qa_fa0ef899b14749c4981e3fb010230997/receipt.json`；`b5207ad7a1ef6cb26e7c370814e930df0022427984e66550fd99e4bd17659254` |
| 199 | 新8反例＋受影響原service／scope／daily／UpdateView讀回共50PASS、compile5、兩來源mypy通過。 | `single_owned_qa_6606cc5cbc6d41889f06e92bdecca001/receipt.json`；`b780b6f1d20ecdf85b4116985527263b1f57d657948f1740a60d67f2767afe12` |

本增量無UI程式／共用ports／金融公式變更；已過且未受影響的Workbench85、validator25/0/4、八roots mypy沿QA192，不反覆重跑；ui_qt.*既有ignore_errors仍不證UI強型別。QA199有關Qt session未載Main的teardown提示保留，該組僅UpdateView，不能當Main驗收。真來源新Main／fresh需到真可用小時後沿同pin做，不能拿42合成旅程代替，也不重抓同一scope。各Job仍8GiB／12程序／kill-on-close／同workspace mutex、RAM≥8GiB，三PID陣列自然空、process／Job handles關閉、mutex釋放，無forced cleanup。

來源用途接受由Root保留裁決；Luna9只讀核既有SourceAcceptanceDossier／Governance／decision registry／intake，無寫入、Python或網路，pending writes=false，總worker10/10不新增。人工limited需要license／quality／PIT evidence IDs及intake綁定；PIT ID只代表需實質審查的證據引用，程式沒有全歷史年限要求，不能因欄位名永久阻擋前瞻研究，也不能填字串冒稱歷史已合格。現registry來源級決議沒有T86 source version強綁定，現有machine scope不含T86，不能借月營收接受或偽造human actor；本次不append正式registry或自授accepted。下一步沿原dossier準備真單位／品質／前瞻時間與獨立授權證據，來源／用途／schema版本一次接受及每日自動validator分開，不把一次接受誤解為單batch只能用一次。

用途／授權、真來源正常UI／fresh、真股票母體、日曆連買與完整歷史PIT、Native／EXE及完整Gate仍待。沒有正式資料／DB apply／Task／maintainer變更、push、發布或交易；固定V1不改。原資料契約、current分冊、功能、操作主冊／分冊／每日指南、Snapshot與原§9.5同步；模組邊界、安裝、排程與Feature Map關聯未變，無需新增入口或測試清冊關聯。
QA200新版public reader以真cutoff台北03:30:46核同批，正確拒絕04:00前使用，7個capture／daily原件不變，無網路；governance原dossier診斷為deferred，程式證據清單無缺，authority具體缺license owner／status／redistribution policy，沒有append registry或把歷史PIT設永久前置。helper compile及9份文件／12features、metadata30sources errors=[]通過。outer `single_owned_qa_8b777a7d909f4f1b93c2ce232f7e777d/receipt.json` SHA `9c0d61636459fe13f89188317af09c0474c4a02bb0fd6766730f5c66f5999934`。準備階段曾因PowerShell陣列錯pin路徑拒絕，無Job／Python／HTTP；修正後才啟動。Root核四組收據／自然閉鎖、tested source pins及真capture／daily雙pin、V1 EXE／20輸入、舊task／capture與其他owner原件不變；owner `increment43_final_integrity.json` SHA `628071a5780a23b0be265429105ec4ad7f3e499f9607e39cda99bba98e113c64`。此為限定進度，真來源正常Main／fresh與用途接受仍待，不授完整Gate。

## Increment44：P06封存帳戶個股投影

本葉解除原 P06 完整封存雖可比較／另存，但進個股只有 artifact 標籤、沒有原帳戶內容的操作阻礙。沿既有 scenario workspace／repository，不造新帳本或金融引擎；固定 V1 四旅程不變，第二階段與真人試用並行。

Root 先核原 Paper daily producer：`source_result_id` 沿 baseline ID 重用，不能證明每天所選價格的原件、時間或 hash；不從 ID、latest_status 或 receipt 時間虛構行情證據，初次來源仍獨立保留。此輪先交可修的已保存來源 consumer：新增 typed 帳種／portfolio／artifact 參照，正常 Main 注入同一 private workspace，exact 重讀再核 canonical bytes hash、外層 account source hash、原決策日期與現在時鐘。投影原 cash／NAV／quantity／mark／market value／Health／targets，沒有重算、今日手動帳 fallback、新 Advice 或 Exit；完整帳本未持有候選股的 0 股與缺件分開，mark 時間缺欄仍未提供。未保存 target 預覽須先另存，避免冒用舊 artifact。失敗／取消／換股清除舊投影；普通持倉與 H20 沿原路徑。

兩名既有 Luna Max 各單寫一個新測試及 UI 葉片，無 Python／QA／network／子代理，回報後 pending writes=false；Root 整合共用 DTO／ports、金融守衛與 QA。另一輪靜態複核找到 Mapping 可繞過 DTO source_kind 綁定，Root 已補入口拒絕及三反例；累計仍 10/10，沒有新建代理。

| QA | 限定結果 | outer receipt／SHA256 |
|---|---|---|
| 201 | route 通過；context domain 誤寫 portfolio，失敗保存。 | `single_owned_qa_6508a9d12eb245cdbec5e167f8823d14/receipt.json`；`c10ef9b75b0bcb85ca91d492a720992ae9a79667ce2f96f79e75f44b0c234b30` |
| 202 | 正確 portfolio_health context、compile9通過；62PASS／4FAIL，canonical hash 函式誤留 TYPE_CHECKING 導致 NameError。 | `single_owned_qa_6f0245b803df491ba7dc77b9081cdde6/receipt.json`；`35c60c723e62584290a96a70a55f82acd44a6161636a09deee95e5b489e2dc00` |
| 203 | 移至執行期匯入後，四失敗案例＋新 UI 六案及受影響原持倉／取消／換股／summary 共18PASS；compile11、Workbench85、validator25/0/4、八roots mypy1022通過。未重跑未受影響62PASS。 | `single_owned_qa_9d9ba32d6a784670b2fc61f8d3a970cc/receipt.json`；`f0352fc3ef3a8b48d43a312554fee97c5566b8a4d869c53307905172b396ebb6` |
| 204 | Mapping跨綁定3PASS、受改service mypy／compile；正常Main10288保存新target→個股原投影→返回，fresh18608明選同版重開，完整投影及scenario DB hash一致。fresh禁止 compare／append，當前手動帳查詢0、Python socket0，自然關閉。 | `single_owned_qa_166e2a60046b46799e7fca36815caa74/receipt.json`；`bd11997b294f64e327e4d4ca15524f3cad885ee7a9a262bf856f61f44cfd14b7` |

Main 原收據位於 owner `increment44_scenario_main_fresh_a/parent.json` SHA `0b1a20c124bad5b162270dfc3a5e1f14c01f22a98c62b2943564d2120eb9160c`、`fresh.json` SHA `4273bbe91b000a7d182ae66ee1b313a087249a636985cc15a81f5f7e4d0e37f8`，均為隔離合成來源、source Main，沒有 Native／EXE 或完整 P06／Gate 接受。既有 ui_qt ignore_errors 不證 UI 強型別。各組 8GiB／12程序／KOC／workspace mutex、RAM≥8GiB，三 PID 陣列自然空、process／Job handles 關閉、mutex 釋放，無 forced cleanup。

使用者操作與結果判讀已同步主手冊、Portfolio／Research Lab 分冊、功能、current 架構／總架構、Feature Map、Snapshot 及原計畫 §7.1／§9.5。初次 account／Health／quote source、獨立行情可得時間、Registry 交叉入口及原完整包繼續，不以 unknown 或本輪案例加總結案；正式資料／Task／maintainer、push、發布及交易均未變。

QA205 十份本輪文件／12features 與 context metadata30sources errors=[]通過，outer `single_owned_qa_250e330a224448b2846ce88993a1fe01/receipt.json` SHA `55d611f187ca4f499578abcba165439ee2c26068811e00a6a4961c5d505fd183`。Root 另核五組原收據與自然閉鎖、11最終來源pin、真T86／舊capture、固定V1 EXE／20不可變輸入、舊task與其他owner檔案不變；`increment44_final_integrity.json` SHA `1986cd9c2044bd237f1c189961f9e88b417f5b8cee9064e7481122ef41c451f8`。文件檢查後只追加本段收據註記，不外推完整 Gate。

## Increment45：P03真T86正常畫面與新程序

本葉只解除 Increment43 真資料尚未到可用小時、正常 UI／fresh 未驗的出口。沿原取得→原件→品質→成功保存→public reader→正常 UI→新程序，同一批次及雙 SHA，沒有新金融公式、框架或固定 V1 前置。期間同步核 P07 與 P12 已有接點，初次 P06 來源及其餘原包不等待真人試用。

Root 於 UTC2026/10/15 20:00:07（台北10/16 04:00:07）確認時間已到才啟動。QA206 的 pin 複製了絕對路徑，invoker 在 preflight 拼接失敗，沒有 Job／Python／HTTP，原 spec 與 `increment45_qa206_preflight_failure.json` 保存；另存207的 workspace 相對 pin，所有原 SHA／HEAD不變，未覆寫206或重抓。

QA207 helper compile及正常 Main5752→fresh43792通過，原每phase120秒／UI15秒／driver270秒期限保持。兩程序各以真正當下cutoff（UTC20:00:33及20:00:42）開正常「數據更新 → 三大法人」固定批次，逐一讀2330、2317、2454、0050。四列九個買／賣／淨額整數與獨立raw quality原值一致，保留負淨額；2330外資買13,293,478、賣47,404,843、淨-34,111,365股，沒有轉張或浮點回流。每列是2026/10/15資料，母體明示21,000報表列，不能當股票真N。

同manifest／receipt SHA、原件 SHA／twse-T86.v1、首次保存／成功完成、台北04:00與successful_batch_completion_fallback都在原正常widget讀回；官方發布時分缺件保持未提供。切至Watchlist再返回同值；fresh重新明選同pin，四列／identity／tooltip與父程序相同。capture／seal／apply／candidate update明確禁用、Python socket0，7個原capture／daily來源 bytes／SHA／mtime／ctime不變；兩程序正常關閉，沒有新HTTP或原件寫入。

outer `single_owned_qa_d17cb06fb304476ca81d93a90248c100/receipt.json` SHA `b032e47f1cf7392dde5971e8eeb75fad55f735473653949347d1ab97f47b4500`。原父收據 `increment45_t86_main_fresh_a/parent.json` SHA `ee6be76fe743af92802b09683d9aab7261f88627d18bad17dc4204287689cb64`、fresh SHA `61e4dbafc5b071775cc356335882806b928caef07b77116c1f556cf7bd2420f4`。Job保持8GiB／12程序／KOC／同workspace mutex，三PID陣列自然空、process／Job handles關閉、mutex釋放，無forced cleanup。此為source Main、真來源配隔離帳本／市場root；隔離fixture缺companies／market SQLite的原提示保留，不授其他市場頁或Native／EXE。未改UI／product Python，未受影響50案、Workbench／validator／mypy及其他旅程沿原具名證據，不重跑。

本輪只做官方授權線索發現：[TWSE使用條款](https://wwwc.twse.com.tw/zh/terms/use.html)保留政府開放資料例外，但沒有據此自授T86用途。另[政府資料集11856](https://data.gov.tw/dataset/11856)明列上櫃法人資料及開放授權；這是該精確資源後續版本核驗線索，不是其他TPEx日曆、T86或正式來源的接受證據。線索另存 `increment45_official_license_discovery.json`，屬web頁面閱讀，沒有完整HTTP原件／EOF／raw hash，沒有更新正式registry。

既有Luna Max窄讀確認 P07 原保存StrategySpec／rule pin及public rule reader已接歷史「開啟規則」與Registry比較；目前設定卡本來就標明目前設定，不另造接線。Root窄核P12既有bounded stage trace、timeout／unknown／failed terminal與共用frame取消／reset；無修改、無QA或真排程接受，不重觸發已停maintainer。詳owner `increment45_parallel_static_notes.md`，workers累計10/10、pending writes=false。

正常真資料唯讀出口現已驗證；來源用途／授權、連買、歷史PIT／真N、初次帳本與完整雙策略、Native／EXE及原完整Gate仍分開未完成。指南、功能、current資料分冊、Snapshot及原§9.5同步；產品契約／模組／Feature Map／安裝／正式Task無變，不另立總計畫。固定9fa四旅程、原FAIL及所有舊task／原件保留。

QA208 八份本輪文件／12features errors=[]，outer `single_owned_qa_ea9af9bb143d475eaf75c40a85ab1f71/receipt.json` SHA `4aa4afe7e13cf469993f75d5c231a59333ad10aa9bf9a25e1fd2f89b8484c132`。Root另核207／208自然閉鎖、31個tested來源pin、原capture／T86／舊task與其他owner保護檔、V1 EXE及20輸入不變；`increment45_final_integrity.json` SHA `47dc5f9ca7b8c65c677ba0a3b3701ced1988bdfff44feec18ad64f5844671207`。檢查後只追加本段原收據註記，不授來源或完整Gate。

## Increment46：P03真TWSE處置與終止公文讀回

本葉解除原 F17 真 TWSE 英文 JSON array 全變 unknown，及同一保存鏈的市場 reader 錯比終止事件型別兩個實際阻礙；沿既有 reader／bundle writer／正常 Main，不另造系統或新增 V1 前置。固定9fa四旅程繼續可試用，第二階段與真人試用並行。

Root 唯讀既存 CMS run `20261015T115218380271Z-a6499c4c0d`，pointer SHA `2207b8f0708204aa3aef1a7599e1fd4f8d7d4f92dcb3c31445b388da0524a491`、snapshot SHA `df78b7efbb2d58e4e20dfebceb7213eb99e57937426d169d3f78e560f3857035`、manifest SHA `bde0615786b0480214259005a20d5768e53f17eeb5481ac988615f644f98e69e`。TWSE原raw 16,203bytes／12列，SHA `f6dd9e71b1ceed83259e5eee4cd49bfcc90092004e3722aaab4e324d41af150f`；重用舊task完整官方 Swagger 309,960bytes，SHA `06e1cea82448361e733a0ad1ae16e52f5d5d6b71905acd078472f852c32c0eb0`。沒有新HTTP、重置耗盡scope或改正式capture。原保存capture的HTTP EOF無法由本pin證明，`http_original_eof_proven=false`；CMS自報parsed／partial=false不作完整官方文件鏈接受。

新 source pin／parser v3 成對，identity 加 TWSE row contract 與 Swagger SHA；十欄字串、民國公告日／生效期間、原列SHA／raw SHA分開核。原v2 wire keys／identity／英文array未知語意保留；Luna靜態複核另指出直接v2 constructor的新增欄位預設相容缺口，Root改預設None、僅v3 builder填證據，guard不放寬。舊258列bundle identity `5f66f62f7ea2608ec67bac8d633918e7a31d1c19b328a3fc7919e77b513bc838`、manifest SHA `f8551ac1cd794cf7b09bcc96d5bb826204487079319f0df20dd68d68ebced4c1` exact讀回相同，未重產原全producer。真12列的名稱／理由／措施／內容／期間與raw逐欄一致；同代碼不同公告期間保留，未命中／空列不發安全證書，官方發布時分仍None、current_only／PIT false。

QA214揭露 `market_assignment_termination_source_evidence_mismatch`，QA218定位272筆正向終止證據中只有8183不合。Root查同一原公文，明載9/23停止、10/1終止，raw SHA `ea077acc6b05a8d4e61985d06e1ffe25894e7bf2d38db51c75e47722e03ef1e6`；原因是consumer誤比 `terminated`，原parser實際回 `listing_termination`，不是原件日期矛盾。本葉修單一型別接線；仍逐筆核raw／source／symbol／date，純停止不算終止、改snapshot日期並重綁hash亦拒絕。原QA214／218失敗及診斷不改寫。

| QA | 限定結果 | outer receipt／SHA256 |
|---|---|---|
| 209 | data_pipeline context通過但budget略過正文由Root補讀；helper誤對Observation呼to_dict失敗，先保存的v2 pin有效。 | `single_owned_qa_b452b72d3bd9498c8d2641053a07e757/receipt.json`；`a1af48d2b22b25d9e666ca56f90ed39e4a945fd21d9d7bc74f049a913b5eb58d` |
| 210 | 原public reader真1709/2466/2492均unknown，18來源不變，基線確認。 | `single_owned_qa_0a359881239540dd8fc69ba0140348ab/receipt.json`；`9f706a87a986fefd43c33c7ee8b2285dd1bd172ff9bc9c3d3cba3d60f05fa4dc` |
| 211 | compile通過；原來源加全bundle suite於原140秒逾時，沒有final PASS；後續mypy/helper未執行。 | `single_owned_qa_7e858ad9ac004c5ebf44738d68e5339c/receipt.json`；`83449bb7423007217d630f8edfb406a24f13f914a394dd5395c62bffac15f15b` |
| 212 | 38PASS／1既有受保護TPEx精確環境SKIP、單來源mypy與compile；真12列、v2及舊258列相容。 | `single_owned_qa_c0d01dd4759147b192af2d253e66d03e/receipt.json`；`3728b78ef5a9d7d4d6c170c110897ca5f4d4f8f072c6ead418d1ee4a70a36c03` |
| 213 | helper當日04:00技術cutoff被原收盤守衛拒絕，保留FAIL。 | `single_owned_qa_ebe17ab6a7d24c3c9578b8a0f359bf90/receipt.json`；`ab7631ae1a735156d663505a04ad19453a3d70ca42f3de5f81c70ffb963d79fc` |
| 214 | 有效技術cutoff後被真8183終止證據型別接線拒絕，保留FAIL。 | `single_owned_qa_1dd7ee804ec34e468fc76caef7c96ad0/receipt.json`；`2b21d9d65243ba5c4290b1ae8d1a83d8fc964206d2f5dbe5ecc762eaedbef478` |
| 215 | 改明示合成market隔離驗TWSE，但helper漏research_snapshots層，scope守衛拒絕。 | `single_owned_qa_4a0de3259bd74731b6a9c987db557318/receipt.json`；`54c9d0606f09166236c1bdbf04b2b9065671de10c7d2df952a42630fb2f7ada6` |
| 216 | Main已載入；helper誤對QLabel用toPlainText失敗，另存正確text讀法。 | `single_owned_qa_4c67f5ff688f472aa3b955238349bbc8/receipt.json`；`8afce679d3f013245544f7bd20bfed1997da062f5f9a679953a39bb9c869a775` |
| 217 | 真TWSE配明示合成名錄／行情，Main9944→fresh48140限定通過，不是真名錄接受。 | `single_owned_qa_f6a0c778c74d405d82bf3db9188b5cd6/receipt.json`；`13d8d11dd8a3eea719396b54c412b4f172f4b84e76d696fd4f1eaa95dabae507` |
| 218 | 唯讀定位272筆終止證據、1筆8183衝突，18來源不變，不修寫snapshot。 | `single_owned_qa_dd5d7f8c3f8e4f038706d67d24dd9af9/receipt.json`；`10cda88e3dc048b3dabb5f5b080220be93ffd383d9c6f13bd8ec4fcfb225c2db` |
| 219 | 修直接v2建構相容及終止型別；38PASS／1原SKIP、兩來源mypy／compile通過。 | `single_owned_qa_9fa2bbe268ff493d8de8fa1ac0481b06/receipt.json`；`5f8d776a8132a1d8a4385e97318fe0e7ffd0c0425f6e43c45eec2047ad32bd20` |
| 220 | 真名錄及真TWSE配四股合成行情，原writer保存、正常Main39920→fresh34548同pin／明細／返回通過。 | `single_owned_qa_6d099579a3c84d8693b5d459300a411f/receipt.json`；`e2b6d4d157ab6e01c002435c32ff6953dafde19abac0f11e068b0d3f4e1dc11c` |
| 221 | 新增三公文反例及受影響原市場reader共15PASS，compile通過。 | `single_owned_qa_f5554dbfb594484c874c38cb4469ece4/receipt.json`；`e936bd2f5bbec2ce081308724b95e832a77173c9ac25dcccf6e98833f32363c2` |

QA220原父／fresh收據為owner `increment46_f17_main_fresh_f/parent.json` SHA `54419d5528955ece965aa8c34f71c8ce1ac79bc648c36737d1960a8b1036a968`、fresh SHA `b716be31dee3d678efcd6c4c3581c298836c055159e60d9656965bcdbd22756c`。使用原immutable真市場pin及v3處置pin，四股行情明示合成、不是全市場真N；1709／2466／2492原raw與明細一致，8183保持正向終止衝突排除。原bundle writer只寫owner隔離root；fresh禁止重產與保存，正常頁選來源／三股明細／返回及Watchlist往返後保持同值。18正式來源bytes／SHA不變，Python socket0；隔離fixture缺companies／market DB原提示保留，非Native／EXE或其他頁接受。

各組仍8GiB committed／12程序／kill-on-close／同workspace mutex、RAM≥8GiB，三PID清冊空、process／Job handles關閉、mutex釋放後才起下一組。QA211逾時不能當成功或完整suite PASS；成功組自然關閉，沒有全機kill。未改UI程式／金融公式／共用ports，未受影響Workbench85／validator25/0/4／八roots mypy沿原具名證據，不反覆重跑；既有ui_qt ignore_errors不證UI強型別。單名既有Luna只靜態單寫兩個測試與窄複核，無Python／network／子代理、pending writes=false，累計10/10不新增。

版本契約、current資料分冊、功能／Feature Map、操作主冊／資料分冊、Snapshot及原§9.5同步。真HTTP完整鏈、來源用途／授權、F16注意名單、歷史PIT／真N、初次P06來源／完整雙策略、Native／EXE與原完整Gate繼續；已驗新快照的前瞻研究不以缺舊歷史永久阻擋。沒有正式資料／Task／maintainer、push、發布或交易變更，固定V1不改。

QA222九份本輪文件／12features與context metadata30sources errors=[]通過，outer `single_owned_qa_f49a3f451329405daea514a2d7f72a03/receipt.json` SHA `d048c6e9e0131ccc6a9478d84401818028710890e6f0d6e7b1edec302fe5c4c3`。Root核14組原收據／閉鎖、28最終來源pin、18正式原件bytes／SHA／mtime／ctime、320舊F17資產、V1 EXE及20輸入、舊task／capture與其他owner保護檔不變；owner `increment46_final_integrity.json` SHA `bc72ea692cd4c17afdd9a8c243018b92316cb871c1766ccaffe7f0c9fc4463a9`。文件檢查後僅追加本收據註記，不授完整Gate。

## Increment47：P06初次策略帳來源與正常保存旅程

**解除的交付阻礙**：原 P06 只有完整封存的重研究入口；strategy namespace 尚無可配對的 Health 保存鏈，也沒有首次來源→比較→保存的正常畫面。本增量沿原帳戶／Health／金融引擎與 scenario store 增接這條限定出口，不增加固定 V1 的前置或另立總計畫。固定 `9fa4518c2aca87beaddef75a2b29165722da6a6c`、20 試用輸入與原完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 範圍保留。

- 同次 public exact checkpoint 投影完整現金／NAV／股數／權重、原 mark 的資料日／來源 hashes／獨立寫入時鐘，以及可證開倉 lineage。原 Health rows hash 只抽為共用函數，bytes 契約不換版；seed 舊持倉無可證 lineage 仍不可用。
- ledger 公開 exact reader 可選要求 allocation prefix；在同一 route-bound query-only transaction 核完整前綴與原 operation rowset SHA，決策前有後續 operation（包括零成交）拒絕沿舊 checkpoint 研究。週換手沿原 common-price weights／canonical turnover、rolling 7 日且排除決策日；fill gross 欄位不充政策週換手。未知 liquidity／cooldown 沿原配置守衛，不補 0。
- additive strategy Health v2 核 namespace／帳戶／snapshot／rows／行情／baseline／evaluator result 與實際時鐘，來源日期固定在 receipt，另存 create-only 版本及原 canonical bytes，receipt 最後寫。原 v1 strategy 拒絕守衛不放寬。缺 thesis／condition／metrics 等仍 degraded WATCH，provider 不當已知健康；官方資料小時政策、歷史 PIT 與來源資格不由此授予。
- `run_strategy_position_health.py` 明選五項身分，沿既有 PERSONAL／版本根／合約根與原 evaluator 生成 v2，補足可操作的來源建立入口；缺件結束碼 2 並保留具體原因，不改帳本、不自啟 Task。正常 Main 只在既有條件齊備時注入同 provider。
- 原 workspace 增首次候選／比較／保存；保存以原 preview cutoff 重核來源及 canonical 內容再交原 append。UI 明選來源及代碼、generation 拒過期回呼、未保存不能借舊 artifact 下鑽，保存期間不可取消／切帳。首次保存同步原帳種／portfolio，回原 target／個股／返回／重開。原 scenario service 的等權 construction 外層改獨立 Decimal 60 精度，不繼承 caller prec/traps。

### QA 與原 FAIL

來源 HEAD `e7d11124fecb4dfef1212335f40b3055b1bcc505`；本任務 QA223–238 的完整 outer receipts／SHA 位於 `output/tasks/baldr-completion-resume-20261014-01a13cf9/increment47_qa_receipts.json`，manifest SHA `a8a8123d969b5e098d2b3d888364078e44e34eed84546ec88fa185de6b61d975`。各 spec／runner／隔離 env／result directory 均另存自己 owner；不覆寫舊 task 或 spec。

| 檢查 | 真正結果與界線 |
|---|---|
| QA223–224 | 原帳戶／daily Health 21、新 source 6 PASS；這是初始來源葉片，非正常旅程完成。 |
| QA225–226 | mark JSON iterable 型別 FAIL 保留；明確 list 守衛後 compile／mypy3、原帳戶＋新 source＋availability 37 PASS。 |
| QA227–231 | 新 provider Decimal union 型別 FAIL、借舊 shadow gross 定義 FAIL、source bundle 覆蓋 provenance schema FAIL、等權 construction 繼承 caller prec3 FAIL 各保留。依序窄修；QA228 原 ledger／workspace 等35 PASS，QA229 source／v2 11 PASS，QA230 prefix／取消／外SHA等11 PASS，QA231 定向精度及原情境／workspace32 PASS。案例不加總為完整 Gate。 |
| QA232–234 | 初次 preview 非 canonical 候選順序導致保存回呼拒絕：原2 FAIL保留，沿原codec正規化後兩案PASS；原UI／個股等15 PASS保留。再補首次保存同步同帳戶，該鎖定案PASS。QA234 Main 已至個股；harness 誤限 Decimal 字面尾零的 FAIL 保留。 |
| QA235 | b harness 保留 Decimal 真值斷言，另逐字核原 snapshot canonical 文字，不改金融值或期限；正常 Main／fresh 通過，金融 float 邊界守衛通過。 |
| QA236–238 | 原 public checkpoint reader 30 PASS／1 concurrent adapter FAIL保留；未要求 prefix 時維持原呼叫，不附新 None kwarg，該 concurrency 案定向PASS。新CLI1 PASS／1 fixture PROFILE=test路徑FAIL保留，明示 fixture 自身隔離prod後該案PASS。最終 Workbench85／validator25 PASS、0 FAIL、4 protected skips／八roots mypy1024及CLI mypy1各通過。既有 ui_qt ignore_errors=True 不證 UI 強型別。 |

正常 Main 父 **5668 → fresh34132** 以原 account writer／實際 checkpoint、原 evaluator 與明示合成 QA thesis／condition／metric／calendar 建立來源；從正常頁面選來源／2330／比較／保存，開個股再返回。artifact `sha256:2818ab728bd6fe708ae4a6b6e80f116a01be25f467f6d4e73e8afa4f095cf9f0`，來源原 mark 日仍 **2026-08-03**，不改成 Health 或 snapshot 日期；1000 股、原 Decimal mark 102 與完整現金／NAV 一致。fresh 禁止 `compare`／`append`，重用同原 artifact／帳戶／情境／個股投影；21 來源檔 bytes／SHA／mtime／ctime 一致、scenario DB hash 一致、Python socket 0。各 UI 階段15秒、phase120秒／driver270秒原期限不放寬。這是合成 offscreen 工程驗證，不是 Native、真來源或 EXE 交付。

QA235 outer `single_owned_qa_d2db78c266024c0589a6ab3c36eeaa2a/receipt.json` SHA `e2d8e13cd9da71092f5bb4a40e4266b79524e78f74d1807f478396d427124b69`；QA238 outer `single_owned_qa_2de9741a8e7846cc9514ea35ad668b21/receipt.json` SHA `d6b398d40259c9cc413e6ee451c159593c6892bb1e5301c3424ccfd87b2b5829`。各組8GiB committed／12程序／kill-on-close與workspace mutex固定；下一組前均查三PID陣列空、process／Job handles關閉與mutex釋放，沒有強制清場成功。QA238 啟動前可用 RAM 21,248,950,272 bytes；沒有終止其他 owner 程序。Workers仍累計10/10，只有重用靜態Luna，無新子代理。

**仍未完成**：手動／聲明帳本初次來源、未持有候選完整 Health／行情、原 Registry 交叉入口及完整 P06；官方來源用途接受／歷史 PIT、真 N、完整雙策略績效、Native／EXE與自然成熟各自保留。沒有正式資料寫入、新 HTTP、Task變更、maintainer重啟、push、發布或交易。下一葉沿原 P03 F16 注意名單：已有 Swagger 契約而無 endpoint 資料原件，通用 attention_reasons 不算官方注意名單；靜態筆記 `increment48_f16_static.md` SHA `06a4027dd7f5cfb0fa566d2ecdd87646ff7612a7dcc6915c282da98b2f1c613f`，只作定位，不授抓取或功能完成。
Increment47 文件閉鎖：QA239 八份正文／12features 與 metadata30sources 檢查 errors=[]；portfolio_health Level2 實讀3來源6073字元、unverified_unknown=[]，不取代原正文／QA／金融判斷。outer `single_owned_qa_34e962a874b8447a90da5d6df3e2b1ab/receipt.json` SHA `506cbbae71985650b611f1e26ba5c4fba3bc3594f8711122e14bc2eeda4774e5`，三PID陣列空／handles關閉／mutex釋放。之後僅追加本收據註記及 owner 交接狀態，未重跑未受影響runtime。

## Increment66：日常研究修正版候選（依原計畫§0.4）

**解除的交付阻礙**：0f固定預覽的價格研究入口埋在長頁，四股保存價差多缺方向，回測貼文六組配對卻容易被別區塊的零交易說法混淆；Increment60–64的已驗保存修正尚無同版試用包。此輪仍只處理第一列完整使用流程，不加第五條V1旅程、不重造來源或金融公式。

- 日常研究頁以「價格選股」為預設子頁，舊每日快照／兩個進階母體另分頁；價格來源的日期、母體、已處理／待處理及不可選原因顯示在首屏，原路徑／metadata／核驗SHA收在可展開詳情。原catalog明選、嚴格載入、PIT、條件、比較、收藏及返回守衛不放寬。
- 單股回測當次摘要明列完成配對、實際成交、明細列與期末持股；保存歷史顯示精確run ID，舊件沒有的成交／持股欄位標未提供。六配對測試保留樣本不足與Walk-forward原FAIL；使用者原run尚未取得，不宣稱已重現。
- 原0f試用價庫四股12,390列只在新隔離副本補正負號：與正式資料唯讀的同股同日收盤價及無號價差Decimal精確相等，且正式欄位明示`+/-`才補。正式12,442列原rowset SHA `866241ff90af9e8a38ca336788389129bf4ffaa76b78e164c934cb468c2da391`；新副本SHA `5bc5b40de16078713af51cc4994fda5287fa522e4232d59095987e29dbc179fd`，補11,378、原有35、缺明確方向977，錯配／衝突0。四股末日2026-09-23皆精確對上，public reader回`2317 +3`、`2330 +40`、`2382 -0.5`、`2454 +5`；舊試用原件／正式資料不寫，歷史PIT仍false。詳owner `increment66_trial_market_overlay/receipt.json`。
- QA391 audit腳本import路徑FAIL、QA392／393 sandbox `Path.resolve`拒訪FAIL各保留；原讀回已成功，未當產品FAIL或PASS。QA394在同規格受控Job下：changed Python compile、四股public reader、受影響pytest **77 PASS**、Workbench **85 PASS**、validator **25 PASS／0 FAIL／4保護SKIP**、八roots mypy **1042 files success**；ui_qt既有ignore_errors=True，不視為UI強型別證據。原收據 `output/tasks/baldr-completion-resume-20261014-01a13cf9/single_owned_qa_0030af84a6bf4d64ac5ce4cb5ebde069/receipt.json` SHA `e5616a600a5e2036837a0236e5031abca549cd973e3adafdcfeebbeb37faf268`，三PID清冊空、handles關閉、mutex釋放。

**QA394 當時尚待交付驗證**：隔離多持倉正常頁、價格選股→比較／個股→保存／回訪→返回的正常 Main／fresh、同版 Native／EXE 及新固定入口與指南收據。QA394 只證來源候選；後續 QA400／402／403 與本節末的交付收據才解除這項工程阻礙。原 TPEx／來源權威／歷史 PIT／真 N／雙策略完整績效／Paper 與 Forward 自然成熟和 P00–P14／G0–G4 各自保留；無正式資料寫入、maintainer 啟動、push、發布或交易。

文件核對QA395誤帶原Increment59 create-only launch check，因既有收據而FAIL，保留 `single_owned_qa_a1a6c75cfcce40d09d61ae3219ce78ea/receipt.json` SHA `5470f989552950a7862de5de2092a5085a38715b6ba25fe216853caac7f3f9aa`。QA396只跑本輪task／11文件／12features與context metadata31來源，兩項 `errors=[]`；outer `single_owned_qa_fddc6603ef74442f9a92a621d9994d1b/receipt.json` SHA `f4028ea438231c1e6d26d443ae4048c4c9580afef9fc0002f9484e4789f75a7d`，自然三PID清冊空、handles關閉、mutex釋放。結構檢查不代替本段語意、Native或產品Gate驗收。

### Increment66 固定本機候選、Native／EXE 與試用入口

固定來源 commit 為 `ec5c9573360891595bb395fa7bbb934077c6d4c0`，版本 `2026.10.06+ec5c95733608`。EXE 位於 `dist/candidate_ec5c95733608_44024cd5/baldr/baldr.exe`，SHA-256 `f6eb269748fe8bf711535bac7811507dc61cb889929dee4fc30f3d73e4514494`，56,285,502 bytes；來源封存 SHA-256 `1f892a7b30b337b26afb2620d05b2fdd1953023216d64fe8da565b84c6b2efcb`。build pin 位於 owner task `increment66_candidate_build_pin.json`，SHA-256 `858dfd5b7205d24a05751bcf02fd04d2b8d3323474aa949ade2fdeda80af3712`。原 `9fa`、`4b530`、`0f644faa` 試用包保留；本輪試用副本 `output/trial/Baldr-Daily-Research-66/` 使用獨立 `state/`，沒有搬入使用者真帳。原技術封存仍需本機絕對路徑作嚴格身份核對，這份入口不是移機包。

| QA | 實際結果 | outer receipt／SHA-256 |
|---|---|---|
| 397 | 準備規格仍綁舊 HEAD，preflight 拒絕；無 Python／Job 執行，保存失敗。重綁固定來源後才執行建包。 | 原 preflight 原件保存在 owner task；不算 PASS。 |
| 398 | 固定 ec5 來源建立 EXE，候選本身未由 build 動作授 Native 接受。 | `single_owned_qa_4f30445db323477fafaa7a7b908bec78/receipt.json`；`ee3ae1b2ae16c00b62561cb264c63673a99381031bf9b107db42a347f86740cc` |
| 399 | 來源 Main 已保存；驗證腳本等到查詢後過早讀收藏，比非同步籃子恢復早，該輪 FAIL 保留。 | `single_owned_qa_7018d960b63d49f0835011569a152bca/receipt.json`；`4b1a6caa06c0356598809ccf11f9a34ecc9789a341555205b489e3b781aed476` |
| 400 | 修驗證等待條件後，來源 Windows Main → fresh 的四股篩選、兩股比較、收藏／觀察清單同來源重開、個股返回、兩筆隔離測試持倉及兩原 `1.0.0` 策略保存／歷史／返回通過。 | `single_owned_qa_030835226b654a329aac2769041eb158/receipt.json`；`2613b5b8a57baf67c2badcf392e13700bc549b260ad9863e1027b7a43e9d6aca` |
| 401 | EXE 驗證腳本直接 import 包內未收的 `PySide6.QtTest`，在產品啟動前 FAIL；改用已驗證的原生 UI helper，不以此宣稱產品失敗或成功。 | `single_owned_qa_a2ddc6029220410b803a1e9790803dae/receipt.json`；`cb17855489453139549503892c9f9bb5b66757449e44d3614703556bb7a3701a` |
| 402 | 同版 EXE Windows Main → fresh 上述旅程通過；`verify_same_version.py` 的隔離 fixture 身份／載入檢查通過，receipt SHA-256 `5b4434834df74de3ee7ee001e8327de6814a6ab3c83ad3ddb8fc581619ada1f4`。 | `single_owned_qa_b002e61be41a48d982c72d0f4d2d5c60/receipt.json`；`e6e5ae833e570892025f679a17998faf89e1659403c36b048ed6997fa9b25ce1` |
| 403 | 新試用包 `Launch-Baldr.cmd --check`、五份隔離輸入、價庫副本、環境根與 build 身份核對通過；這一步未另開 GUI。 | `single_owned_qa_451e43e560a742c9abd829af84b2b290/receipt.json`；`0cc78ec16656275bf1c3189bad51f90e8d2310e945bec0fce8fdc4f55a1b9654` |

QA400 原始 parent／fresh SHA-256 `371ecaf7910430c51e228ee7d1926765113d9f786cd820d268e3700883159986`／`b79463d581e910a174e840f27489da29769fc5001855fb20f2bae5ba0036a2db`；QA402 EXE parent／fresh SHA-256 `87d47ca3b83e1c381348dd81daccb944b759fbec4d7afccad6757a7e87daaa43`／`51d90be959665f562921ecf875ab51857c64b9f7b8bb7b6b11265e7756743ccf`。各組均在 8 GiB committed／12 程序、kill-on-close、同 workspace mutex 下啟動，起跑 RAM 大於 8 GiB；成功組三 PID 陣列空、process／Job handles 關閉、mutex 釋放，無強制清理。原 QA399／401 失敗保存，不覆寫成通過；QA400／402 有獨立新 script、spec、隔離狀態及收據。

交付入口為 `output/trial/Baldr-Daily-Research-66/Launch-Baldr.cmd`，操作見同目錄 `TRIAL_GUIDE.md`，限制見 `KNOWN_ISSUES.md`，create-only `DELIVERY_RECEIPT.json` SHA-256 `1f8df5505c892af87a1a0dc288e79d8bd2f21a4744dd58783eb28b8ce5d989a2`。它只接受指定四股日常研究、同源收藏回訪、隔離兩持倉版面與兩原策略正常回測保存／讀回的工程出口；原四股資料截至 2026-09-23，大盤截至 2026-10-14，977 列漲跌方向仍缺正式明確符號。使用者貼的六配對原 run 未取得；原 SOP 樣本不足、Baseline FAIL、Walk-forward 缺件不變。真人試用、TPEx/MOPS 權威、來源用途、歷史 PIT、真 N、完整雙策略績效、Paper／Forward 自然成熟及原完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 仍各自待驗；未改正式資料、正式 Task、maintainer、push、發布或交易。

交付文件閉鎖 QA404：本輪 task／11 文件／12 features 與 context metadata 31 來源檢查各 `passed=true`、`errors=[]`；outer `single_owned_qa_8f2d14c390e94caab12065ca34fb04c1/receipt.json` SHA-256 `4257b0ac5b9bde31994114cab72150a4e7dc78fb527ca38a5de4063f32d4ecf7`，自然三 PID 陣列空、process／Job handles 關閉及 mutex 釋放。結構與連結檢查不代替 Root 對文字語意、使用者試用或完整 Gate 的判斷；本句為該檢查後追加的收據定位。

## Increment67：P08 推薦回放通用比較的金融判讀阻斷

**解除的交付阻礙**：原計畫§0.4第四列的同頁一般「比較選中」只核舊 Registry metadata，可將兩筆推薦回放標為「可直接比較」，並排 metrics／benchmark 與標準化權益；嚴格雙 run 期間 reader 同時因來源、日曆、幣別或成本未知而阻擋。使用者可能將未核數值當成可排名策略結果。此輪在原 `ResearchRunComparisonService` 對任一推薦回放回 incompatible，UI 停用通用比較並明示「固定日曆版本→比較完整期間」；服務直接呼叫亦阻擋。其他 run 的原規則與兩筆 exact reader／原觀測保留，不補造金融值、PIT 或資格。

QA405 對四個受改 Python 檔 compile 通過；服務及 Registry widget 直接回歸 19 PASS／1 FAIL。FAIL 是既有跨頁選取提示預期以「已選 2 / 5」開頭，新提示覆蓋該前綴；原斷言及 `single_owned_qa_f5b8a1ceff6a415bbcfaaf32f4d24e14/receipt.json` SHA-256 `80e607ab5e114de393d4100fe8a385c65c1db19a3be29fdb083bc08c576c8aed` 保留。只修 UI 提示，維持原已選數和推薦回放下一步；QA406 重驗兩個受影響案例 2 PASS、Workbench 85 PASS、validator 25 PASS／0 FAIL／4保護SKIP、八roots mypy 1042 files success，`ui_qt.* ignore_errors=True` 仍不證 UI 強型別。outer `single_owned_qa_e2ebb31690eb4488876de218d70143c7/receipt.json` SHA-256 `f5859e23e9a163d9d017137c4b3c5146920f6dd02a82e1055db5ec73fdab46a6`；兩組 8 GiB／12 程序、kill-on-close、RAM≥8 GiB，三PID清冊空、handles關閉、mutex釋放，無forced cleanup。

這是開發來源的防錯修復，未更新固定 `ec5c95733608` 試用包；完整雙策略期間成本／source authority／PIT／績效及 Native／EXE 仍待，不能由 19＋2 案加總當 Gate。正式資料與私人原件未寫入，無 maintainer／Task、push、發布或交易。

文件閉鎖 QA407：本 task 與七份受改正文的連結／結構檢查 `passed=true`、`errors=[]`、12 features；outer `single_owned_qa_8cc5dfebfe434db492acf29d159ec613/receipt.json` SHA-256 `9d64806727edc8987013d2552917272c42f0274459e8f618c0df5cb50586167e`。原收據三 PID 陣列自然空、handles 關閉且 mutex 釋放；檢查不證文義或完整產品 Gate，本句為檢查後的收據定位。

QA408 啟動前發現固定試用目錄的 `TRIAL_GUIDE.md` 暫時缺失，來源 pin 檢查即停止，沒有啟動 Python／Job；不列為通過。下一次核對時指南已在原路徑，10,413 bytes／SHA-256 `d5f814f34c5afc16cf95f84d26965fc31f0d880baac45d4733fa4b344f4a6739`，與當時讀到的交付收據 guide 欄位一致，因此未執行 create-only 恢復腳本、未寫恢復副本。交付收據檔自身由先前記錄的 6,274 bytes／SHA-256 `1f8df5505c892af87a1a0dc288e79d8bd2f21a4744dd58783eb28b8ce5d989a2` 變為 6,275 bytes／SHA-256 `16bb4f511e5ecb21dff6667a5a38fa7aa73d298bf951ea69c0ce85b42e128eb1`；改寫原因與原始位元差異未裁決，原歷史 pin 不改寫。QA409 另建 spec／隔離根並重新綁定現況，受影響測試檔 compile 與兩個 UI 案例 **2 PASS**；outer `single_owned_qa_8935d7b0c6cb4223ae8c74da306ec835/receipt.json` SHA-256 `1d24d29a5ea4668f10ca3beb6ead7b3a2940be884bd4199de4ca7b731a497224`，三 PID 清冊自然空、handles 關閉且 mutex 釋放。此結果僅證現況 pin 下的開發來源回歸，不證試用包原收據位元不變或完整 Gate。

## Increment68：P06 同日 Health 收據的初次情境旅程

**解除的交付阻礙**：原首次策略帳來源清單列出舊評估日 Health，但正常比較預設以現在時鐘重核，造成可選卻必定日期不符；未持有候選也容易被誤認為可直接補零研究。本輪不換 scenario service、artifact、帳本或 Health 公式。清單只列原 v2 收據在評估日台北當天已保存的 checkpoint／Health 對，另顯示跨日才保存數；比較先有界核精確收據 reference／SHA 及其 `available_at`，再只以該原時刻 exact 重核帳本、Health、mark 與候選，避免以今日帳本的後續 operation 先行否定舊快照。保存仍用 preview 時鐘／canonical bytes 重驗。晚到的帳本、Health、行情、跨日收據及未持有候選缺同源 Health／mark 仍拒絕；不倒填歷史 PIT 或新增裸 float。UI 指明目前只輸入原帳本已持有股票。

QA410 changed Python compile 通過，來源與 widget 合跑有 7 PASS／6 FAIL，六案均因 owner pytest `--basetemp` 的 Windows 深路徑無法建立 fixture 目錄，原 FAIL 保留；outer `single_owned_qa_c237c467c3004b148dc433f08d51103e/receipt.json` SHA-256 `486dfcc7652a69487ff59a3a2a51dc0bae406388627973282831250cad421c7d`。QA411 改短的 `.t` 暫存路徑後仍 7 PASS／6 FAIL，原因是 sandbox 對 `_contained_regular_path` 的 `resolve(strict=True)` 回 `WinError 5`；outer `single_owned_qa_50ae672e1b9e4a19b0bcdd1ab65c9bea/receipt.json` SHA-256 `4797e22fcd447911aa15537dce08512c0bce848d45aa7cebfef1031f9332db83`。QA412 改 pytest 預設系統暫存則 sandbox Temp 路徑過長，仍 7 PASS／6 FAIL；outer `single_owned_qa_8b4c61fa6c9d48c69357e6570b7d0964/receipt.json` SHA-256 `beab5c8b8638fff4b41c898d0958efcf366ea7fa85356c05b65d9c7c6eb4f2ff`。三輪均未進來源案例的產品斷言，不改為 PASS。

QA413 在**同規格受控 Job**、短獨立暫存及較完整檔案權限下，原受影響來源與 widget **13 PASS**；包含原帳本不變、比較→保存→exact 重開、同原收據截止時間、跨日排除／直接拒絕、未持有及缺 Health 拒絕。outer `single_owned_qa_7bfb0bfb564845eeabe0900ce092c1dc/receipt.json` SHA-256 `ac094731469166efbaf249911f363cf6e82f85d3a8e920a056dbdb2a8cb9bdd2`。QA414 Workbench **85 PASS**，但 validator 在 sandbox Temp 的離線 daily_price 同步遇 `WinError 5`，得到 **21 PASS／3 FAIL／4 SKIP**，mypy 尚未啟動；outer `single_owned_qa_e2a3b097f575459d9884591af461ec5c/receipt.json` SHA-256 `dea8303c5ae247603528f961a0cbc81b35a93774d8bc3f7b10b2375875b7a051`，FAIL 保留。QA415 以相同 Job／隔離根補驗 validator **25 PASS／0 FAIL／4保護SKIP**、八 roots mypy **1042 files success**；既有 `ui_qt.* ignore_errors=True` 不證 UI 強型別。outer `single_owned_qa_1f41023c0cca4917bdf32698df98a850/receipt.json` SHA-256 `da856f61f06389711b5a7e3f68ba1d3507f56968e2aa9b982b21b2d0eba145da`。

QA416 復用原已驗正常腳本，僅換 create-only 隔離根；同一 source 版 Windows Main 父 **37860 → fresh37696** 從正常持倉頁明選成對來源／2330，比較、保存、個股返回，再由新程序同 artifact exact 重開。parent／fresh 原件 SHA-256 `534663de25581ef4d5bcf5c88d2fcdb2bc54b6a1e5e6e42a597075a02e5d7cd8`／`8e6caf6dcd2cceb29df7795ed96933a617619fcf685c264ba57a4cf58b4b933f`；21 個來源 pin 前後不變、情境 DB hash 相同、fresh 禁比較／append，Python socket 0。outer `single_owned_qa_8413c828586f4eab8433a7100fd0d5b0/receipt.json` SHA-256 `9387d4fadeef7559dda4a0abc49a123d72114dda7bab7ac248e82975dc889779`。各組皆 8 GiB committed／12 程序／kill-on-close／workspace mutex，起跑 RAM≥8 GiB；三 PID 陣列自然空、process／Job handles 關閉、mutex 釋放，未以強制清除當成功。

這是合成來源的 P06 子旅程工程驗證，非固定 `ec5c95733608` 試用包、真私人帳、未持有候選、Native／EXE、歷史 PIT、完整雙策略績效或 P06／產品 Gate 接受。MOPS 文件 partial／缺 EOF 的基本面第二列仍按原§0.4保留；手動／聲明帳缺完整現金與同源 Health／mark，以及真帳研究接受各自待補。沒有正式資料、私人原件、正式 Task／maintainer、push、發布或交易寫入。

文件 QA417 對七份正文／12 features 發現本輪計畫新增連結的錨點拼字錯誤，FAIL 收據 `single_owned_qa_e6adeb95c920423780edc2385d4dca74/receipt.json` SHA-256 `98b8e1f8adbdd5495dcd22c9e7e32021dacbfd8e4cf6c3caa773ad269d8e0be1` 保留。只改該錨點後，QA418 同範圍 `passed=true`、`errors=[]`；outer `single_owned_qa_de2ae29e04524b19abd1a28a34d87d4d/receipt.json` SHA-256 `ae8831481447df15bdc3a436d0cad62810f641690fbc157aad73b069d9cfdc7c`，三 PID 陣列自然空、handles 關閉、mutex 釋放。本句為檢查後收據定位；結構檢查不授正文文義或產品 Gate。

QA413／416 是初版時間鏈的階段性結果。Root 複核發現初版先以現在時鐘執行完整 Health exact reader 來找原收據時間，可能因後續帳本 operation 拒絕原時刻有效的 checkpoint；遂改為現在時鐘只讀有界收據 metadata，先核同帳戶、checkpoint、receipt ID／SHA 與同日可得時間，再於該原時刻執行完整 exact reader。QA419 對此修正的 13 案為 **12 PASS／1 FAIL**：偽造同 receipt ID 的 SHA 雖被拒絕，錯誤碼卻失去原 `external_receipt_hash_mismatch` 判定；原 `single_owned_qa_4534fabf416e43869c2c19e3c4defd71/receipt.json` SHA-256 `4ae30f5f879a42add8c6b16fcfbadd8680eada2cd8d3505f001677294beff517` 保留。恢復該精確錯誤碼後，QA420 changed Python compile、來源與 widget **13 PASS**、受改來源模組 mypy 及金融 float 邊界檢查通過；outer `single_owned_qa_303d0773b1394ff080c490d44bebb2dc/receipt.json` SHA-256 `59646e55b4d52fed414baec80b619431edea855e5fcb1273accc9fadc602571f`。既有 UI `ignore_errors=True` 及先前八 roots mypy 的限制維持。

QA421 在最終程式下重新跑來源版正常 Windows Main 父 **34292 → fresh37092**：成對來源明選、比較／保存、個股返回及新程序同 artifact exact 重開通過，fresh 沒有再比較或追加；parent／fresh SHA-256 `55c78fdac94cb27e47b28c58995358c4b2f21ef4d9e85dfb9abc7b2448d9af7b`／`cb92ce78e7fe4e2ffae871084226060a07f3d4f1085339f5ad86ba5f718f8003`。21 個隔離來源 pin 前後不變、情境 DB hash 相同、Python socket 0；外層 `single_owned_qa_f730b9aa41ff4f5c810fbde27e4baa16/receipt.json` SHA-256 `95e8a797b4eb61612c783b8d095c73db5ab19cc87ab50ff826dc56a2549bbe51`。QA419–421 都依前組自然 PID0／handles 關閉／mutex 釋放後才起新組；各組 8 GiB committed／12 程序／kill-on-close／同 workspace mutex，起跑 RAM≥8 GiB，無 forced cleanup。此限合成來源與 source Main，不授真私人帳、固定 EXE、歷史 PIT、雙策略完整績效或完整 P06／產品 Gate。

文件 QA422：本 task 與七份受改正文／12 features 結構及連結 `passed=true`、`errors=[]`；outer `single_owned_qa_0d95739e11d24ada9c62c01d4a76ae81/receipt.json` SHA-256 `7bc4e0ba63767a9c582552b9b8072626988da75be0770240146d262cf3fbde78`，三 PID 陣列自然空、handles 關閉、mutex 釋放。QA 後只追加本收據定位；結構檢查不證正文語意或完整 Gate。

## Increment69：P07/P08 兩基本策略原保存對照與明細往返

**解除的交付阻礙**：原計畫 §0.4 第四列的兩個固定 `1.0.0` 單股策略各可保存及歷史重開，但使用者不能從同一 Registry 連續核對兩筆原結果、開各自明細再返回；通用 metadata「可直接比較」亦易被誤讀為歷史績效資格。本輪沿原服務加只讀 `BasicStrategySavedPairReader`，恰選穩健／積極各一筆，核原輸入、股票、要求與保存權益實際期間、data fingerprint／cutoff、成交與成本及共同來源 hash，逐筆以 exact 歷史 reader、版本化指標與保存規則卡核原件。缺欄位、條件不符、來源變動或取消均不並列數值。原 `performance_status=not_evaluable`、`historical_pit_eligible=false` 不改；不重跑、補值或升級。一般 Registry 的可比較標籤改為「保存條件相同（績效資格另核）」；一般單股成本或期間 Caution 清除數值區。

QA423 changed Python compile、策略／Registry／presenter **42 PASS**、Workbench **85 PASS**、validator **25 PASS／0 FAIL／4保護SKIP**，但全量 mypy 在新服務 `source_hashes` 的型別縮窄報錯，原 `single_owned_qa_7279089a5f384944ad57a62d2b687bf0/receipt.json` SHA-256 `10e1bb0093f03503427c0ac87914080cca324609621af6125ebd987e14dd798c` 保留。修正型別局部變數後，QA424 全量 mypy **1043 files success**、金融 float 邊界通過；`single_owned_qa_3fbe844604ee474b9d40f81fe87f4355/receipt.json` SHA-256 `c8a9fd1858c057aaebd5cffe719834a77e111c2963428e1a28409779ba775eb2`。既有 `ui_qt.* ignore_errors=True` 不代表 UI 強型別。

QA425 UI **14 PASS**，但隔離根置於 repo 導致個人資料根與產品 package 重疊，正常 Main 在啟動前由 `PersonalStoreRouteError` 拒絕；原 `single_owned_qa_8f165de96be546b49aedecf7ce057312/receipt.json` SHA-256 `f08c974bd33bf5fcbe436a68be2ab5192f8afd782e84b212bdc2beabefe654c0` 保留。QA426 改獨立 Temp 後兩筆正常保存通過，但在 640px 視窗「對照兩個基本策略」按鈕被祖先裁切，原 `single_owned_qa_77dad3dcaa494fd7aab1ddad536aa1e9/receipt.json` SHA-256 `6e059185090186e367f2e42b1ffd28fc328fac14f20357219b3e4506fd6f87b9` 保留。QA427 嘗試 1280px，offscreen Qt 實際僅 800px，尺寸 preflight 拒絕、未測產品，原 `single_owned_qa_d7d77567b31942e5a4f985a0f71b20cf/receipt.json` SHA-256 `613ea4bf822c999a01a42d50072358d0240ec46f807edfd27b80d470bf3ebc81b` 保留。QA428 將對照按鈕移至頁首後對照通過，兩個明細按鈕仍被裁切，原 `single_owned_qa_75a1a4bf22e54fc9907a2905c2d37eba/receipt.json` SHA-256 `338a1a75bef6e328577baf7b768892b8956b248c753433a89dae4a8c449d0dbd` 保留。這些是不同具名腳本／隔離根，不覆寫失敗。

QA429 將明細按鈕也放在可見控制列後，UI **14 PASS**，來源正常 Main 父 **24452→fresh35896** 完成兩策略各保存、exact 對照、各開原明細、返回同一對選取與新程序重開；每筆 419 日原曲線。20 個試用來源 pin、隔離價庫前後相同，fresh 前後 Registry inventory 同一組，Python socket 0；outer `single_owned_qa_e45235f93bad40c18d80722d9a89c422/receipt.json` SHA-256 `dd84665927115af87b057ff847c9002f57c50a48161f5832b912f696462f1d04`。此收據早於最後「保存權益實際期間須明示且相同」守衛，不代表最終來源完成。

QA430 新增守衛反例後，受改單股 **24 PASS**、changed Python compile 通過；最終來源正常 Windows Main 父 **41348→fresh23784** 重新完成兩筆各自保存→Registry exact 對照→逐側原明細→返回→新程序同 run 讀回，父／fresh 原件 SHA-256 `9b8f30bca1b5a2bc5703db74a7ed13500c581366085d76e27e3d166d16ab70e9`／`c45cfea737ca8a2faaad682763e1f52d8f329519646798e20a94af9e82402d80`。來源 20 pin 與隔離價庫未改，fresh Registry inventory 同一組、未重跑 producer／新存、Python socket 0；outer `single_owned_qa_0116f7d3518e4d2898893699f183da39/receipt.json` SHA-256 `2c3e6a1a35ab11eaaca2935e1fbf7588b5e33f878fa5a2f4a36bbb67cbb93c11`。QA423–430 均按 8 GiB committed／12 程序、kill-on-close、同 workspace mutex 與起跑 RAM≥8 GiB；前組三 PID 陣列空、handles 關閉與 mutex 釋放才起下一組，無強制清理當成功。

這只接受**隔離合成來源的 source Main 子旅程**；固定 `ec5c95733608` 試用 EXE 不變，也未驗 Native／EXE 新對照、真人、真成本／幣別／來源權威、完整獨立策略帳本、歷史 PIT 或可排名績效。§0.4 第四列完整出口及 P08／G0–G4 均保持未完成；第二列 MOPS 完整財報鏈的來源缺件仍隔離處理。沒有正式資料、私人原件、正式 Task／maintainer、push、發布或交易寫入。

靜態複核發現明細開啟後若改選 Registry run，對照會失效但摘要的「返回兩策略對照」仍留著；同輪補接失效回呼隱藏按鈕。QA431 新增此跨頁 UI 回歸後 **15 PASS**，最終來源 Main 父 **47260→fresh5808** 再驗兩筆保存／對照／逐側明細／返回／精確重開，父／fresh SHA-256 `a5d203394afddcb7f8bd122a4e6aa2de3bd93169a02eaca660be6aafc0c03452`／`5b6f5a1b0fe1136d1c3ca35eddbefca08b8dc4bef4bc85cd35e6ccbb7ff34415`。changed Python compile、Workbench **85 PASS**、validator **25 PASS／0 FAIL／4保護SKIP**、八 roots mypy **1043 files success**、金融 float 邊界通過；本 task／七份正文的文件檢查 `passed=true`、`errors=[]`、12 features。outer `single_owned_qa_e95780d0508f46c8b19e52278d0987dd/receipt.json` SHA-256 `d1c779803ca8dbc4e18b34858f0a157843f5f22e06a87e18d849653d607b703a`，三 PID 清冊自然空、process／Job handles 關閉、mutex 釋放，無 forced cleanup。`ui_qt.* ignore_errors=True` 與文件結構檢查的限制不變；本段收據定位在該檢查後追加。

## Increment70：價格選股載入後顯示結果

**解除的第一列交付阻礙**：使用者回報推薦分析難懂、無法找到可選股票。靜態核查發現「價格選股」已有單一來源、條件、結果、比較與收藏，但窄視窗的長表單將表格推到下方。互動式嚴格載入或套用條件在原 `_PriceViewState` pins 成功後，收合條件和長母體摘要，按當次 generation/state 將「步驟 3」結果定位於外層可視區；結果保留符合數、翻頁、逐股比較及收藏，長計數與來源 SHA 各有明示展開入口。失敗／取消不收合或搬動原已核結果；翻頁、原來源返回及收藏重開不套此互動式定位。原 catalog、strict source、query／排序、Decimal、PIT、basket、bookmark及資料原件未改。

QA432 changed Python compile及價格選股 UI **16 PASS**，涵蓋窄結果區可見、逐股加入比較籃、修改條件與錯誤保留原查詢，以及既有收藏捲動／取消回歸。`increment32_qa432/receipt.json` 僅為命令收據；outer `single_owned_qa_74d1c2a11411469780d8aee1f7501313/receipt.json` SHA-256 `c6f9e08dcc8b10af4eb02c0ab0f9bd520f10a40daf9acd052e69bbf76d499b3b`。QA433／434 的隔離 Main runner 先後因 `tests` package 及測試目錄未加入匯入路徑而 **FAIL**，尚未執行產品斷言；失敗收據保留於本 task，修正 runner 後未降低斷言。QA435 隔離合成來源 Main **1 PASS**，涵蓋選來源、價格條件及多頁結果、兩股比較、收藏、取消、fresh PID 重開；Workbench **85 PASS**、validator **25 PASS／0 FAIL／4 保護 SKIP**、八 roots mypy **1043 files success**、changed Python compile 與文件結構檢查 `passed=true`／`errors=[]`。QA435 outer `single_owned_qa_f504a6c60dbf458e81a0231bcedfb881/receipt.json` SHA-256 `321d13ef9cf22ff3678aefb97d60a68877b3123b403ed57f46ffa32d7fa5b3b0`；Main 父／fresh 收據 SHA-256 `1e322ef9ffbc3991cc1f986d31ee8dada647b473c7c48320d73585794159514f`／`ee69263e5ba97d6f6d97c31f56228ecf9c8b7c992d490e1fa0be75d2b53d3447`，原本落在中立 `output/qa` 的具名 attempt 已逐位元複本另存本 task，原件未覆寫。前後來源 pins相同，8 GiB／12程序Job、三PID陣列空、handles及mutex關閉、無forced cleanup。固定 `ec5c95733608` EXE 不變，真人易讀性、真 N／來源權威／歷史 PIT、完整第一列與 G0–G4 不由此局部測試接受；`ui_qt.* ignore_errors=True` 仍不證 UI 強型別。

## Increment71：真人試用回報的四流程可用性修正

**解除的第一版交付阻礙**：使用者在固定 `ec5c95733608` 試用 A／B／C／E 可用，D 的價格結果卻只看到一列、不能比較或收藏；結果列雙擊開原價格研究獨立視窗，固定指南誤寫為主個股頁。手動持倉下鑽到主個股頁後，價格／技術空白且重載仍空白；回測 1366px 視窗把設定堆到上方，三個選用查找難辨且長摘要不易看完。本輪不重做財務資料、策略或多個產品線：價格結果區加同一保存來源的「顯示此來源全部股票」、分列來源處理數與條件結果數，單檔選取也可收藏；兩檔比較仍須逐檔加入同源比較籃。手動交易以已載本機公司名冊唯一代號／名稱互補，歧義或矛盾拒絕；未連結保存研究的手動持倉下鑽明確走目前個股研究 scope，保存結果仍走原核驗。回測中寬視窗保留左右排列，三個查找預設收起、最多展開一個，摘要本身可捲動。雙擊價格結果的既有獨立視窗行為不改，以手冊勘誤；舊固定試用包與收據原件不覆寫。

QA436 價格視圖 **16 PASS／1 FAIL**：失敗是新摘要把「找到 3 筆」改寫為「來源已處理 4 檔，目前條件留下 3 檔」後，舊測試文字斷言未更新，產品結果仍為 3 檔；outer `single_owned_qa_d1dfa80bc5fe489095dff880ac1228fa/receipt.json` SHA-256 `b0543252abc1e029f3c60e2757c7880b4a12b8eb14467031db2d0920fb28697a`。QA437 修正斷言後價格 **17 PASS**、持倉定向 **9 PASS／29 deselected**、個股重載 **2 PASS**，但 1366px 版面測得結果區 588px 低於原測試 600px 門檻，回測 **6 PASS／1 FAIL**；outer `single_owned_qa_18c3893f1174414097b0668f4760627c/receipt.json` SHA-256 `000f8f492cd30629a539a70cfb61a3db80ecab74f217692457bfa3f7e8ff984d`。縮減設定區固定寬度並使初次 resize 套用後，QA438 回測 **7 PASS／2 deselected**、歷史接線 **13 PASS**、Workbench **85 PASS**、validator **25 PASS／0 FAIL／4 保護 SKIP**、八 roots mypy **1043 files success**、八受改 Python compile 通過；outer `single_owned_qa_e22f53578b25480b99741c6f32562c77/receipt.json` SHA-256 `043641c061ac92f6e6e58db601327baedff1ff0ef1c2d603dfda956aabe65916`。既有 `ui_qt.* ignore_errors=True` 不證 UI 強型別，offscreen 幾何與真人視覺接受分開。

固定試用包原技術來源的唯讀核對先有四份腳本失敗：QA439 模組搜尋路徑未設、QA440 Windows 260 字元路徑、QA441 把擴展路徑直接傳公開 reader 遭安全路徑契約拒絕；QA442 正常 strict reader 已列出四檔，但腳本誤假設按代號排序而 **FAIL**。各原 FAIL 收據保留在本 task。QA443 啟動時同工作區 mutex 正被其他驗證持有，exit 125／**未啟動產品 child**；outer `single_owned_qa_efda55897bc0427596e22ea388c9a2bb/receipt.json` SHA-256 `7d53711ad0fb35548e6571d00a37e159ac2a2e9ec9d64614c647ece344326c13`。QA444 在鎖可用後按公開 reader 原 canonical 路徑重驗：固定完成批次 `processed_count=4`、無條件 `matching_count=4`，原頁按價格排序列出 2317／2382／2330／2454；plan 與三 receipt JSON 前後 hash 相同，來源 identity `cb6af7092315f9c163fcefd134c490f95b3d650ce4d785f5f3c2ff8af8ca5afb`。outer `single_owned_qa_f8fe92514e43412b9e64143f64fdcfbc/receipt.json` SHA-256 `280d838498a4e9247584bb6a6c540bf6a1992ad00b92b18d40c73c36d44b1a08`。此證明原保存來源有四檔，不證使用者當次 UI 的具體篩選狀態；新增按鈕讓同源無條件重查。

QA445 在最終受改程式重驗隔離合成來源的正常 Windows Main／fresh 價格旅程 **1 PASS**：選源、條件與多頁結果、兩股比較、收藏、取消及新程序 exact 重開仍可用。outer `single_owned_qa_c96ac4ce3d5a42d38e09779e71e4bb61/receipt.json` SHA-256 `d398f5eef77db3a40c578b87048b86a71d7fa8b94814c1fa2d6f6be9f4974e85`。上述各有實際 Job 的輪次均以 8 GiB committed／12 程序、kill-on-close 與工作區 mutex 運行，前後三 PID 清冊自然空、process／Job handles 關閉、mutex 釋放，無 forced cleanup。尚未有本 Increment 同版 Native／EXE、真人新版、真私人帳或完整 Gate 接受；原 `ec5c95733608` 可繼續試用，不把來源／歷史 PIT、完整雙策略績效或外部缺件升格。

QA446 本 task 與八份受改正文的連結／結構檢查 `passed=true`、`errors=[]`、12 features；outer `single_owned_qa_a3fd7822ff634d3d8daebbc330d36c17/receipt.json` SHA-256 `cc29b6e99d93dd99d24c0022627921a3d9fa288031f38dd64fdce62c17d20d5d`。這只核對文件結構與任務紀錄，不證文義、真人可用或產品 Gate。

**固定候選交付**：來源 commit `f9b4e7d1214967f86d9ae90b1e462bde11b73f3f` 建出 EXE SHA-256 `df10c0404863e255e317e02adfd872348510618d966432bf1a1999ad43568a90` 與 source.zip SHA-256 `091dc857d3e06dadd54239f41f3ba4cb692aa8cb5bd0b59a3825e26593285b9f`。QA447 建置本體完成，但建置期間另一 owner 修改 `FEATURE_DOCUMENT_MAP.json`，廣域 post-pin 因此 **FAIL**；outer `single_owned_qa_5f7cc7eb165641aca59caef53087babc/receipt.json` SHA-256 `ab95467940d819cdc1f8b0ba292923767a50b4678afe4f8ca18ae1f647fabb30` 保留。重新以固定來源／EXE／鎖檔及必要來源 pins 啟動 QA448，同版封存、程式與 EXE 隔離比較 **PASS**；outer `single_owned_qa_9d99276fde194dd39c4eaee7ee84b106/receipt.json` SHA-256 `9e72c4a217531f8dfb751cd613b811eba75779e04fee9a9cdcc0950e7f9fa358`。不把 QA447 原 FAIL 改寫成 PASS，也不據此推定其他 owner 工作樹已穩定。

Native／EXE 先後保留 QA449／450 的 frozen `Path.resolve` 存取拒絕，QA451／452 的來源 strict reader `technical_parent_v4_child_path_invalid`；同一固定來源的來源版 public reader 在 QA444 已列四股，改以相同 8 GiB／12 程序、同 workspace mutex、隔離 state 的受控非沙箱 Job 執行 QA453，來源載入／單股篩選／顯示全部／兩股比較／收藏已走通。QA453 把持倉跳頁與價量合成一個等待條件而 **FAIL**；QA454 證明自製滑鼠雙擊事件未觸發持倉表訊號，QA455 企圖使用打包版未提供的 QtTest 方法而 **FAIL**；這些測試工具失敗各自保留，沒有降低來源或金融斷言。QA456 用持倉表 `doubleClicked` 訊號驗證正式接線、一般個股價量與再次載入，正常 EXE 父 PID `35516` → fresh PID `40464` 通過兩個原 `1.0.0` 單股策略各自保存、原規則卡、歷史精確讀回與返回；fresh 禁止再跑回測，原20份 source輸入與隔離市場價量前後不變。父／fresh 收據 SHA-256 `a74fc84b6c918298f0df6865efcd985fb39f36da734e698f651c8a536129c807`／`e1172efbd3987111c4a40de749d11957940437abe7f1b691ce6d8e20190223e9`；outer `single_owned_qa_9c15e7835e574347abff168ef4f4e6ac/receipt.json` SHA-256 `2c5ed1bc0444041b24e4ad143e76a13615a34914d4bb807074a9c41cc53bd3b1`。雙擊的真人滑鼠手勢仍待試用，不以 Qt 訊號測試冒充。

QA457 把 `cmd.exe` 直接交給只接受 Python child 的既有 runner，未啟動產品 child 且 **FAIL**，收據保留；QA458 改由 Job 內 Python 檢查 `Launch-Baldr.cmd --check`，啟動版本、EXE SHA 與五份複本 market 輸入 SHA 前後一致，**PASS**，outer `single_owned_qa_67486f9b2ddc4d6eb7f59f75e6b56ce8/receipt.json` SHA-256 `1511284b7c592d7e4d056a72b26e5a0d5613ee959bb539a7737b0aff0bef4673`。所有實際 Job 的三 PID 陣列終態為空、process／Job handles 關閉、mutex 釋放，無 forced cleanup。新獨立試用入口為 `output/trial/Baldr-Daily-Research-71/Launch-Baldr.cmd`，指南與已知問題同目錄；`DELIVERY_RECEIPT.json` SHA-256 `524eaa0038d5c15f9241bfb7e66d8094c777601b0fa4207b1b2278aac7e85dca`。Paper root 在本試用啟動檔停用；原六配對 run／真人持倉與手勢、外部來源權威、歷史 PIT、真 N、完整策略績效、Native 跨主機與 G0–G4 保持各自未完成，不以候選與局部 PASS 當完整 Gate。

## Increment72：舊回測歷史缺件與空交易表的金融判讀

**解除的第一版交付阻礙**：回測歷史的舊「比較選中／雙擊原結果」入口，遇到保存欄位為 `NULL` 或缺失時，原程式以零作績效預設或對 `None` 乘 100 而中斷；摘要記有完成配對但明細檔遺失／讀取失敗時，只留下空表，容易被誤認為零交易。這與已驗新 Registry 歷史卡是不同入口，不能靠後者通過替代。現在只在舊入口的顯示邊界把有限原值格式化；缺件／非有限值明示「未知／未提供」，真零保留。舊 run 缺本金／手續費／滑價時不帶入目前預設值。摘要並列完成配對與原明細列數；有配對而明細不可讀時明示空表不代表零交易，數量不同時只提示核對原 run 與明細語意。原資料、引擎、SOP、成本與保存件均不重算或改寫。

QA460 以本 task 新 spec、pins、隔離環境及 result directory，在受控 Job 串行 compile 三檔與回測診斷／presenter **23 PASS**；新增反例覆蓋「六組配對但明細缺件」、「真零配對」及舊比較欄位缺失。outer `single_owned_qa_2525265c85ac4a8697a56ad4d5e3ebdb/receipt.json` SHA-256 `7812c8f009dae44a918f189fe93b9931a9e427e2dc825ef86a8171aeec7e6e5a`。QA461 接續在前組 PID0／handles／mutex 閉鎖後執行，共同 Workbench **85 PASS**、更新頁 validator **25 PASS／0 FAIL／4 保護 SKIP**、八 roots mypy **1043 files success**；outer `single_owned_qa_d00d8aa2d54e49c89ac9314591b4f760/receipt.json` SHA-256 `54b72823f3b273d78edd14ac8e68817f523305d0691c8a88f6343e5390cfb8c0`。各組 Job 為 8 GiB committed／12 程序、kill-on-close、啟動 RAM ≥8 GiB，三 PID 清冊自然空、process／Job handles 關閉、mutex 釋放，無 forced cleanup。既有 `ui_qt.* ignore_errors=True` 不代表 UI 強型別。

目前此修正只在開發來源，**不在固定 `f9b4e7d12149` 試用 EXE**，未用原使用者六配對 run 做資料級重現，也未新增 Native／EXE 或真人接受。原 run 在 `Baldr-Daily-Research-66/state/output/backtest/runs/backtest_runs.db` 的 read-only 清冊為 0 列，只能證該精確檔無保存 run，不能推論使用者沒有執行回測。來源／成本權威、歷史 PIT、完整雙策略績效、TPEx／MOPS缺件及 P00–P14／G0–G4 仍保留；無正式資料寫入、Task變更、maintainer、push、發布或交易。

Root 再核同一舊入口的保存參數後，把缺本金／手續費／滑價的原預設值移除，新增「真零與原參數仍保持」反例。先前 QA460–462 保留為補正前收據；**最終 QA463** 對當前四份文件與受改來源重新固定 SHA，changed Python compile、定向 UI／presenter **23 PASS**、Workbench **85 PASS**、validator **25 PASS／0 FAIL／4保護SKIP**、八 roots mypy **1043 files success**、文件四來源／12 features `passed=true`、`errors=[]`。outer `single_owned_qa_a9e1f803065d4dc68839ad8400fb6e6f/receipt.json` SHA-256 `241ff8a4ed0143ab2407286408f305ec8128f3bdee4f44c7561366fc5abe415f`；本組三 PID 清冊自然空、process／Job handles 關閉、mutex 釋放、無 forced cleanup。文件檢查不證文義或完整 Gate；目前 `APPLICATION_MANUAL.md` 同時有另一 owner 的未提交整理，本輪只追加自己的回測判讀段，不 stage 其餘 hunk。

## Increment73：P07 原生 EXE 來源封存與獨立研究預覽

**解除的第二階段交付阻礙**：布林基礎突破與 W 底頸線突破在來源版已各自完成單股 Main、保存、版本與新程序讀回，但固定 `f9b4e7d12149` EXE 缺執行來源原檔。QA464 在原生 Main 執行布林策略時，對 `baldr_bollinger_executor.py` 取 SHA 因封裝檔不存在而中斷；outer `single_owned_qa_4e7b4b3aa2324e3196abbb08c9cf3460/receipt.json` SHA-256 `19e2e18ea4dd8cb0125c7627bd3f2fea16115db8205b6e7ac2aa0a0ccdb1dd92` 保留。此為 EXE 打包缺件，未改策略算法、價量、成本、SOP 或舊保存結果。

固定來源 `90e9a4f7adcb65cab4c5842b13cb6f2586d85e1f` 明示打包兩策略 executor／contract、W 底因果觀測、技術日期支援、成交限制與精確單位共八份原始檔；建置 metadata 將八份 SHA 加入 resource manifest，宣告不全或原檔缺失即拒絕。正常研究 run 仍取實際執行來源位元 SHA，啟動時核固定資源，沒有合成缺件 hash。QA465 changed Python compile、封裝／建置身分定向 **31 PASS**、該模組 mypy 成功；outer SHA-256 `77d198bbd597089170c8343164f125007958da3a6d17f80cb426280dd8b0ac2a`。QA466 從精確 commit 建獨立 EXE，八檔封裝位元都與 metadata 相符；outer SHA-256 `b0a48f7a49758b807900faf0430a19ad932112171fb2699dc4b6d0379ffa4545`。候選 EXE SHA-256 `53138a905415af76d6046bb5d055b8af6bc6f1d97d91f8c50718e7c6f8535e62`；來源封存 SHA-256 `f1ec7991c2d2368d0535b9e56c4f95029e9ef56d5a75da00b699e7fbf94c9a85`。

QA467 先通過固定 Python／EXE 的 launch／journey／model／H20 同版隔離比較，再於原生 EXE 正常 Main 用 `2317`、`2025-01-02` 至 `2026-09-23` 各執行一筆布林與 W 底。核 `1.0.0` 規則卡、419 筆交易日權益列、非零實際成交、現金＝本金＋賣出－買入－成本、來源 SHA／逐日訊號、`can_promote=false`，再保存、歷史精確重開、返回及不同 PID fresh 只讀原 run。父 PID `46488` → fresh `41472`；父／fresh 收據 SHA-256 `68fe09a28a72e69e97cd1e81085d38ba05179a8acc08760563c3794a135e76d2`／`103cd34439a9686794ee30aca67b0f398b8ef6e74fd9aa02a17573f26802f105`。原20份試用來源與隔離市場價量起訖相同，Python socket 0；fresh 禁 producer／save。outer SHA-256 `680dff597e1647766863746010dc601aab3aa5d9209adf73ac20538ab56728ec`。

獨立預覽 `output/trial/Baldr-P07-Research-73/Launch-Baldr.cmd` 使用全新 `state/` 與五份已核四股市場副本，不搬移日常研究71或正式持倉。QA468 對實際啟動器 `--check` 核來源 commit／EXE、隔離設定及市場副本 SHA 前後相同；outer SHA-256 `92f60a1cdceace131b46ca2ade53736c4503f29765ba848d4d121f5e9d30f0bc`。預覽 `DELIVERY_RECEIPT.json` SHA-256 `9fa1fe061748b80d6b946e11a8004b27ed6b40191ccebf96f097dff40f1809a4`，同目錄有試用步驟與已知問題。QA464–468 各組均以前組三 PID 陣列自然空、process／Job handles 關閉與 mutex 釋放才啟動，Job 為 8 GiB committed／12 程序／kill-on-close，沒有以強制回收當 PASS。

本增量只解除 P07 兩條研究策略在 Windows EXE 不能執行的工程阻礙。未接受四股以外真 N、歷史 PIT、來源用途、完整雙策略績效、Walk-forward／OOS、真 Paper／Forward 成熟或 P07／G0–G4 全 Gate；原六配對使用者 run 仍無 exact 身分。固定第一版71 EXE／收據保持原樣；Increment72 的舊歷史顯示修正雖隨新來源進此預覽，不改寫71包或原失敗。未寫正式資料、正式 Task，未重觸發 maintainer、push、發布或交易。

## Increment74：P12 決策擷取終態的固定 EXE 讀回

**解除的第二階段交付阻礙**：Increment56 已讓來源版正常主視窗顯示決策證據擷取的具名失敗原因、保存未知與最後階段，但同一流程在固定 Windows EXE 與新程序仍缺證據。本輪不修改產品程式、不啟動正式排程，也不重跑使用者已驗的日常研究71；以 Increment73 已建固定來源 `90e9a4f7adcb65cab4c5842b13cb6f2586d85e1f`、EXE SHA-256 `53138a905415af76d6046bb5d055b8af6bc6f1d97d91f8c50718e7c6f8535e62` 驗原 P12 的唯一新增出口。

QA470 先用原 producer context／artifact／finalizer helpers 在隔離目錄建立一筆合成成功與一筆合成 snapshot timeout 終態，來源程序確認成功件的收據可讀；父 PID `46484` 與 fresh PID `16132` 再各由固定 EXE 啟動正常 Main，沿「系統狀態 → 日常排程 → 決策證據擷取 → 詳細」讀出同一 run ID／收據 SHA、`snapshot_cli_timeout`、未完成 `snapshot` 與「已保存：未知」，切到觀察清單後返回仍是同一終態。兩個 EXE 程序均唯讀，原九件以上的隔離原件內容與時間在建立後、父程序、fresh 程序前後一致，Python socket 嘗試 0；未呼正式 producer、另存、Task 或 maintainer。受控 spec 固定 11 個來源／候選 pin，QA Python 語法檢查與同版 EXE 主頁／fresh 命令均 exit 0。父／fresh 收據 SHA-256 `23d6a94e8bd8b1a0ddabf563fe971afe1f8c1bcdb0a71d095faaf5e57407bc4c`／`450546fb1ea4e79967485c35d50cc95c2345882137e1dcd6ebc4bb5b195c1962`；外層 `single_owned_qa_645fe9da3c1542f0affc1e8515b2a307/receipt.json` SHA-256 `1ba2f3c041e4a0b77a583032a8e60237eef306831c69fded2ac23b941de2350e`。啟動前可用 RAM 21.10 GB；同 workspace mutex、8 GiB committed／12 程序／kill-on-close，三 PID 陣列自然空、process／Job handles 關閉、mutex 釋放，無強制清理。

隔離測試目錄沒有公司名冊及市場 SQLite，主頁在其他工作區顯示缺件降級訊息；本案例只驗 P12 終態讀回，不以此核市場功能。timeout 是**合成事件**，未實跑原 120 秒超時、慢依賴、完整 DB snapshot 或自然排程，也未證正式資料來源與真人操作。原正式快照 Task 逾時與 P12 全出口仍 open；不因這筆固定 EXE 的局部 PASS 改成完整 Gate。固定日常研究66／71與 P07 預覽73 均未修改，沒有正式資料寫入、全量回補、正式 Task 變更、push、發布或交易。

## Increment75：P03 個股月營收金額單位顯示守衛與既有 QA 缺口

**解除的第二階段交付阻礙**：個股研究原 `fundamental_monthly_revenues` 讀取器只有既有 `mops.monthly_revenue_static_snapshot` 明確以原件千元乘 `Decimal(1000)`，卻把其他月營收來源的原值也直接標成 `TWD`。現改為只有該 MOPS 路徑且原值是有限 Decimal 時顯示 TWD；其餘月營收值明示「來源單位未核實」或「金額無法解析」、數值不可用，並把來源／區塊標為部分資料及停用該報告列的聚合／正式 PIT 資格。原 SQLite row、來源版本、可得日與既有時間查詢條件不改。這是報告顯示邊界，未替 TWSE、TPEx 或舊 CSV 接受單位，也不改正式資料。

定向回歸使用同股已核 MOPS、未核 TWSE、無效 MOPS 及查詢日後才可得的 row：只顯示已核 MOPS 的 `300000 TWD`，其他金額不可用，未來 row 不出現。QA475 changed Python compile 通過，服務／UI 整組 **96 PASS／5 FAIL**；其中一個 `os.replace` 在沙箱預設 TEMP 遭 Windows 存取拒絕。QA476 改 task 暫存後 **97 PASS／4 FAIL**；QA477 因短路徑父目錄未先建立而 **101 setup ERROR**，原收據均保留。QA478 以已建立的短路徑 **97 PASS／4 FAIL**；兩項舊 Advice 讀取與兩項 Qt 等候未通過，不能算整組通過。QA479 的 Workbench **85 PASS**，但更新頁 validator 在沙箱內寫隔離 fixture 的 `data` 目錄遭 `WinError 5`，**21 PASS／3 FAIL／4 SKIP**；QA480 換短 TEMP 後相同。這些環境失敗沒有改成 PASS。

同一來源 pins 在受控較高權限 Job 重驗：QA481 服務／UI **100 PASS／1 FAIL**，唯一失敗為既有 Enter 鍵搜尋測試 2.5 秒內未等到載入；changed Python compile 通過。QA482 更新頁 validator **25 PASS／0 FAIL／4 保護性 SKIP**、八 roots mypy **1043 files success**、新增月營收反例 **1 PASS**；單獨執行上述 Qt 鍵盤測試時子程序以 `3221226505` 異常退出，故仍列未解，不以單獨重試抹掉 QA481 失敗。Workbench 由同一未改產品程式的 QA479 接受；`ui_qt.* ignore_errors=True` 不證 UI 強型別。QA475–482 的外層具名收據均在本 task，最後 QA482 外層 `single_owned_qa_dd3445c9450249e0ad2051130b06283e/receipt.json` SHA-256 `a8a116c4478b6c984d3e5bf0cce793be17d83160581403915b122c2f96159bd3`。每組實際 Job 都使用 8 GiB committed／12 程序、kill-on-close、同 workspace mutex 與起跑 RAM≥8 GiB；三 PID 清冊終態空、process／Job handles 關閉、mutex 釋放，無強制清理當成功。QA481 首次啟動前因前組收據 SHA 手抄少兩字元即拒絕，未啟動 QA child，修正綁定後才執行。

同輪來源調查：舊 TWSE 2026/09 候選原值與官方公司月報及該公司公告量級相符，只構成交叉檢查，尚無同 API 版本／schema 的單位權威綁定；不得把千元推論升成正式 TWD 轉換或用途接受。P01 舊 1,000 檔合成來源原 page/filter/sort p95 FAIL 仍是歷史結論；現版診斷 QA472–474 分別在 Windows 長路徑列舉、腳本 import、舊 deep fixture 的 canonical child path 守衛止步，**沒有**取得新的可比較延遲樣本，未放寬 canonical 路徑或重造來源。固定日常研究71 EXE 與 P07預覽73沒有包含此來源修正；真人、正式來源、歷史 PIT、真 N、完整雙策略績效及 G0–G4 保留原狀。

補充鍵盤失敗定位：QA483 對同一整組重驗仍 **100 PASS／1 FAIL**，原 2.5 秒 Enter 測試期限未調整；測試用 Qt app／焦點調整後已回復測試來源，不把嘗試算修復。QA484 診斷腳本 module path 失敗保留；QA485／486 的隔離鍵盤訊號與 `activeStockChanged` 均已發出，3 秒時背景 worker 仍在一般唯讀報告路徑。QA487 延長**診斷觀測**至 15 秒而不改原測試期限，2330 在 3.453 秒載入 `100.00 TWD`，無 `reportFailed`，worker 歸零；這證明該隔離案例不是永久卡住，但不證真人持倉手勢或原 2.5 秒測試通過。QA486／487 outer 收據 SHA-256 分別為 `338594d3aaadec5d5c8303d36f33292a45a070930f36b176e73d91de1865c771`／`7dc6f3f68bf01d08862247d175436c0283e08a07e211c87f9450fd867e09148b`，兩組自然 PID0／handles／mutex 閉鎖，未改產品程式。

## Increment76：P03 舊財報與估值表缺單位的報告顯示守衛

**解除的第一版錯誤金融結果阻礙**：舊 `fundamental_statement_items` 與 `fundamental_valuation_metrics` 表保存 `value`，卻沒有單位及欄位基準欄。原個股報告將數字直接放入「基本面／營收財報」，可能讓金額、每股值與估值比率被誤讀為同一單位。此增量只在既有報告投影邊界將兩類舊表數值設為不可用，明示原因、來源品質降級並取消該列聚合／正式 PIT 資格；仍保留原 row、來源／版本、公告／資料期與 `available_date <= cutoff` 查詢。具獨立單位與時間契約的現況快照不走這個舊表分支。沒有自行推斷來源單位、補零、計算前期變動或改正式 SQLite。

QA488 的 changed Python compile 通過，但 pytest 的 `--basetemp` 父目錄未建立，43 案全在 setup 報 `WinError 3`；外層 `single_owned_qa_f66842fab476402dad88b787be851bf7/receipt.json` SHA-256 `188417bc1cf79c6f41963c093a35a60b775f51542401f4a15288670471785cee` 原樣保留。僅修隔離測試路徑後，QA489 同版來源 pins 下 changed Python compile、完整個股報告服務 **43 PASS**、實際 Qt 報告 consumer **1 PASS**、單檔 mypy **success**；新增反例核舊財報與估值值欄不可用、來源降級及未來期別不進報告。outer `single_owned_qa_ec6b59853756419b8911320068a3c22f/receipt.json` SHA-256 `66fb6a240d69e7fcc73a9f042413586d2cb7f0250451b39688422c089a8bc6c7`，前後三 PID 陣列自然空、process／Job handles 關閉、mutex 釋放；8 GiB committed／12 程序／kill-on-close，啟動 RAM ≥8 GiB，無 forced cleanup。未修改 Qt 來源，前版 Workbench／validator 成功僅作未受影響參照，不宣稱本增量重跑 UI 全套或 UI 強型別。

本增量是來源版守衛，未重新包固定日常研究71或 P07預覽73。MOPS財報完整附件／EOF、同來源前期與單位接受、TWSE月營收單位、歷史 PIT、真 N、完整雙策略績效與 G0–G4 仍各自待驗；缺值不是零，不把此限定 PASS 當財報流程或完整產品接受。

## Increment77：P06 初次配置研究的已核策略帳明選入口

**解除的第二階段第三列交付阻礙**：既有 Paper checkpoint＋Health 初次情境已能比較、保存、重開，但畫面先要人自行查找三個內部識別碼，無法從正常頁面直接找到同帳本起點。本輪沿原 `StrategyPaperAccountService.list_accounts()` 增加唯讀、有界的已核帳戶清單；使用者在「配置研究封存」按「找出已核策略帳」並明選後，只帶入原策略 ID、版本 ID、namespace。其後仍須另選同日 Health 收據、輸入原帳本已持有股票、比較並明確保存。手動輸入原路保留；已核帳戶不代表 Health、行情、用途或績效可用。原帳本／Health exact reader、金融公式、持久化 artifact、Registry 與第一版候選均未改。

QA490 在 8 GiB committed／12 程序／kill-on-close 的同 workspace Job 下，changed Python compile 通過；四個受影響服務／Qt 測試檔合計 **15 PASS／6 FAIL**。六個舊 P06 來源案例均在 `Path.resolve(strict=True)` 解析測試自建 `strategy-health` 目錄時遇 Windows `WinError 5`，未進入業務斷言，外層 `single_owned_qa_87d7a43272e14d958979a11f0bb39044/receipt.json` SHA-256 `bef3abc936aae5c46e0a73094ac6a5659ce9a8a86481907715b3563843cb4688` 保留。QA491 僅將六例換專案已用過的短暫存路徑，仍 **6 FAIL** 於同一權限邊界；outer `single_owned_qa_172cb40cf4774bec83334f8c9c028a16/receipt.json` SHA-256 `e224a0c36f766661ea13caf622091565468524bd515e665f7ed68535d6628745` 保留。QA492 只重驗兩個新增的精確帳戶發現／明選案例 **2 PASS**，服務兩檔 mypy success；outer `single_owned_qa_4256f9df5bb143ecbc9228a716773d02/receipt.json` SHA-256 `dab81d161d3b3b29758ffa65ef6d826d8fe676b3bf23965f57f34e3f840c3ad8`。一次 QA492 啟動前的手抄前收據 SHA 缺字元而被 launcher 拒絕，未起 Python／Job；修正綁定後才執行。

QA493 在相同隔離來源、同一受控 Job 規格及較完整檔案權限下只重驗上述六個 setup 失敗案例，**6 PASS**；outer `single_owned_qa_8133b5fdb8874fbf9c0dfed35e20ee69/receipt.json` SHA-256 `e2635152bb6f62b4c11af7df11bb27585a3b874cc41d77ac172915c3715d9547`。各次實際 Job 前組三 PID 陣列空且 process／Job handles 與 mutex 關閉才啟動，終態亦自然空、無 forced cleanup；啟動 RAM 守衛 ≥8 GiB。15／2／6 的局部結果不能相加成完整 P06 Gate；沒有正常 Main／fresh、固定 EXE、真私人帳或未持有候選同源 Health／行情的本輪驗證。原固定日常研究71、P07預覽73、正式資料／Task／maintainer、歷史 PIT 與 G0–G4 不變。

補充真 reader 接線：QA494 在原已通過的精確來源旅程增加 `list_initial_accounts()` 斷言，確認既有真策略帳 binding 經 `list_accounts()` 產生同一策略／版本／namespace，再沿原 Health 比較、保存與 exact 重開，**1 PASS**。outer `single_owned_qa_0d253c313fb742db92e716970186b8cc/receipt.json` SHA-256 `6e017f19fd771a7873b3f361ba1d0717844e41f1d7501ae50a59a0e6750501d8`；前組閉鎖及本組自然 PID0／handles／mutex 關閉，無 forced cleanup。此為隔離來源與 Qt offscreen 的工程驗證，尚非正常 Main／EXE 或真人入口接受。

## Increment78：P06 明選帳戶的正常 Main／新程序讀回

**解除的第二階段第三列阻礙**：Increment77 的帳戶入口已有精確 reader 與元件驗證，尚缺正常主視窗下的完整操作。QA495 首次 Main 測試把隔離個人根目錄放在應用套件內，既有 `personal_root_overlaps_application_package` 保護於視窗初始化前拒絕；這是測試根目錄錯置，不是帳戶／情境業務斷言失敗。失敗原件 `single_owned_qa_7d090b621fd24bb2b043117dbfb3cc43/receipt.json` SHA-256 `2e20ddc55425b091409d8c341d9ee2f0fac4dd97cf663b5ad44d14c85d0d6a4d` 保留，未重用 result directory。

QA496 改在套件外的獨立 Temp 根目錄建立同一隔離合成策略帳／Health／行情，固定 16 份程式與測試來源 SHA、21 份來源原件 bytes／SHA／mtime／ctime。正常 Main **34688** 由「找出已核策略帳」實按載入、有界清單不自選、明選既有策略／版本／namespace，再明選成對 Health、比較、保存、開個股並返回；新程序 **23784** 不重算或再保存，以同一 artifact ID、comparison、scenario DB SHA 與個股投影精確讀回。腳本 compile 與整條旅程退出碼均 0，`increment78_qa496/receipt.json` 及 outer `single_owned_qa_5490bbbde8f54a9d88068036bca53b63/receipt.json`（SHA-256 `4aab357b453842b2d84ffa73abdabdf920d148d8a2fc4ebdbea7674b76520eb7`）；前組與本組三 PID 陣列自然空、process／Job handles 關閉、mutex 釋放，8 GiB committed／12 程序／kill-on-close，無 forced cleanup。原 `parent.json` SHA-256 `884c77b4382ceee638693968152591ec07b983df58e0bc68e8bbd8ce09621739`、`fresh.json` SHA-256 `bca8e63a8faf79e6353685b7014548b1390fe9dc00b81d456c4452592e8e43e0`。

此出口只接受合成 offscreen Main／fresh，不代表固定 EXE、真私人帳、未持有候選 Health／行情、來源用途、歷史 PIT、績效或完整 P06/Gate。固定試用71與預覽73未改；正式資料、Task、maintainer、push、發布與交易均未觸及。

## Increment79：P11 決策到結果的正式原件唯讀回訪

**解除的第二階段第五列阻礙**：既有「個股研究 → 決策 → 結果」reader 可讀保存推薦與 Evidence 事件，但其 adapter 建構 `EvidenceEventRepository` 時未設 `read_only`，讓唯讀路徑持有可寫 repository；成熟期限的來源原因碼也直接顯在主表。本輪將該 repository 鎖為唯讀，並只在畫面把已知原因碼譯成中文；原推薦、事件、期限、狀態、時間、金額與個人紀錄不重算、不改寫，未知原因碼保留原文。這修正誤寫風險與結果判讀，**不是**補發自然結果或承認績效。

QA497：缺 DB 不建立檔案、repository 拒絕 schema 寫入、既有來源不變與 Qt 入口 **3 PASS**，服務檔 mypy success；outer `single_owned_qa_d33819470cc44c6aa04911403d301cc3/receipt.json` SHA-256 `240f05a60b5795c2d953f6519d8b936d67942fc6ecf1d398cf06c76879b13df6`。首次正式原件煙測 QA498 因 runner 只允 task 內來源根而在啟動前拒絕；QA499 的隔離腳本缺 `tests` import path；QA500 用內嵌 pytest 時原 12 秒 UI 等候逾時，三筆均保留 **FAIL**。QA501 獨立唯讀計時：原結果讀取 0.0283 秒、1712 個事件 0.0499 秒、四個期限結果 0.0018 秒、完整投影 0.1496 秒，來源未變；此只定位 DB reader，不能抹掉 UI 逾時。QA502 改用同 Job 內標準 `python -m pytest` 路由，原 12 秒門檻下正式原件畫面 **1 PASS**；QA503 新中文原因單測初次誤以原 tuple 首列是 5 日，實為 UI 排序後首列，該測 **FAIL**，更正測試期別後 QA504 **新 UI 單測 1 PASS＋正式唯讀畫面 1 PASS（10.64 秒）**，原門檻未改。QA504 outer `single_owned_qa_63989ecac7ef4353843067ee553b20a9/receipt.json` SHA-256 `54e992c9ef01dfa80dea4d46c0a6fa165d7223c06d4560dc5e8e7a693b5b9617`；畫面原件 `increment79_real_smoke_c.png` SHA-256 `aaf26b1bba2ec589353e9c6489dfac6f2224a3e55aba1a5227254b5dcdcc2eac`。

正式根既存推薦 `scheduled_rec_20260914_051003.json` 為 554342 bytes、SHA-256 `2d946a89ebdfe2b3ea66fa246b2fbfb2e685de4d02745db7b0f34eaf5aeb353c`；Evidence DB 為 4079554560 bytes。QA504 前後兩原件的 bytes、mtime、ctime 與結果 SHA 相同；畫面同一 1528 原結果的 5／10／20 日期限為來源標示 `ready`，60 日為待成熟，沒有把來源 ready 當成實際成交損益、個人決定或自然成熟驗收。其他期限與資料品質仍按原證據逐件判讀。

UI 共用檢查 QA505 Workbench **85 PASS**；validator 在隔離 TEMP 自建 `data` 目錄遭 `WinError 5`，**21 PASS／3 FAIL／4 保護性 SKIP**，故 mypy 未啟動，outer `single_owned_qa_210c73d46fc54232b8e473eaaecbf373/receipt.json` SHA-256 `b6eefb2d293fcd1be57ac65e36fce3f8c4af5a59a2285349f65bf8bccc29294c`。只重驗該環境失敗與未跑項目的 QA506 在相同 8 GiB committed／12 程序、kill-on-close、同 workspace mutex Job 和可用 RAM≥8 GiB 下，validator **25 PASS／0 FAIL／4 保護性 SKIP**，八 roots mypy **1043 files success**；outer `single_owned_qa_0b938837005a4b4b81af347f894c6c9d/receipt.json` SHA-256 `e92d58d3b375befb9510468224b3540941f2fcc5779c93d3904e89fd080f506c`。各組的三 PID 陣列自然空、process／Job handles 關閉、mutex 釋放、無 forced cleanup；`ui_qt.* ignore_errors=True` 不代表 UI 強型別。

操作與判讀已寫入[個股研究指南](../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md#決策到結果的回訪後續開發分支)，主手冊原有個股研究入口連到該指南；另一 owner 的主手冊未提交變更未併入本包。這仍是來源版 offscreen 與既存正式資料**唯讀**案例，未做正常 Main／新程序／Native／EXE、真人、正式自然排程觸發、歷史 PIT、完整來源接受或 P11／G0–G4 Gate。固定日常研究71及預覽73未改，無正式資料寫入、全量回補、Task 修改、push、發布或交易。

## Increment80：P08 兩個基本策略的固定 EXE 比較候選

**解除的第二階段第四列交付阻礙**：兩個原 `1.0.0` 基本策略在來源版已有各自 run 與對照 reader，但缺可供真人試用的固定 EXE、Windows 原生 Main 操作及新程序精確讀回。本輪不另造策略或改金融公式；以原四股已封存的 20 份來源 pin，在隔離副本逐一執行 `momentum_aggressive_v1`、`stable_conservative_v1`，各保存原 run，恰選兩筆在「研究 Registry」核對同股票／期間／本金／費率／滑價／執行設定與保存規則，開各自原明細並返回，再由 fresh 程序讀相同 run ID。每筆原曲線 419 個交易日；核原現金＝本金＋賣出－買入－原成本、原 Registry bytes／mtime／ctime 只讀不變、來源副本 SHA 不變。這是保存研究值的比較，`performance_status=not_evaluable`、歷史 PIT 不合格；未作跨帳本或正式績效排名。

QA507 Windows Native Main 父 PID `40456` → fresh PID `47944` 完成上述限定旅程，兩筆各 `1.0.0`；外層 `single_owned_qa_e5b415b8f79c404881580ae15ba4fc6d/receipt.json` SHA-256 `65d7430b97cd242787e32af3150f1496ca002de1d35ed1f2e79d95317b8215c0`。該輪 pin 了當時尚有另一 owner 未提交修改的 `ui_qt/main.py`，只作當次工作樹證據，不能冒充固定 commit。QA508 從精確 `f53bc5e62a3aaf3efa00aac11ecdbaa1ec208152` 建 EXE，outer `single_owned_qa_6afbf5d856624c2d95b56c25d3764976/receipt.json` SHA-256 `fe43dd18a05bd2e479fe5ce6b9d70714056aac71198c1fc012e4254ebf9ebf18`；建置當下的 `built_not_validated` 保留。QA509 同版檢查在 EXE model probe **FAIL**：固定 Python 先用 PID 命名 `spawn_38500`，Windows 後來把同 PID 配給 EXE，原 probe 的同名目錄造成 `FileExistsError`；原 `same_version_receipt.json`、stderr 與 outer `single_owned_qa_a4ad647ceabe48b4b9e3f5decf276e47/receipt.json` SHA-256 `c40571217dfea025774943d0843bfc158e3f405d9be960adc93bd6d81c780cee` 不改寫。QA509 另有兩次 PowerShell 5.1 啟動器相容性失敗，均在 Job／產品 child 啟動前；後續用既有 PowerShell 7。這些 FAIL 不加總成 PASS。

為讓同版驗證不受 PID 重用影響，`packaging/portable_probe.py` 的隔離 spawn 目錄加上 `python`／`exe` 形態，沒有改產品啟動或模型。修正單檔提交 `37231290e3bfcddaf44f7e6e263833ac4374a6cd`。QA510 `py_compile` 通過，建置指令因誤用縮寫 commit 被既有完整 SHA 守衛拒絕，外層 `single_owned_qa_e3db129c4b3c4e7cbbdc7382a3d94733/receipt.json` SHA-256 `9248728bc12e079b450b53e24e72e90029b6d64910cfa11cb7fa3f685332dc35` 保留。QA511 用完整 SHA 建出固定 EXE，SHA-256 `ecac010a1f925fbdeadbf25032830fc392875f31d5a6b6559983678214a3cc76`、source.zip SHA-256 `1bd8724f19899a47365607b1d18be0c0858f94a7a50a6a4492591e84da6390af`；外層 `single_owned_qa_94cab19b80be4c4aa621c4dd0e97cedc/receipt.json` SHA-256 `5411ff09302586b76a3a4d723c37c60ca058d637bfe6fe8ca648255d7cdcc003`。QA512 在固定 archive／EXE 的 launch、journey、model、H20 及無效設定比較 `passed_isolated_fixture`；外層 `single_owned_qa_ec296e74d4a8485b9139700396c66da5/receipt.json` SHA-256 `c928deadb656b39318ecb5aeafe4a56514b0ac1c4d62b678d87ffe7b76c51570`。H20 僅是呈現 fixture，不作自然或正式模型接受。

QA513 用此固定 EXE 在 Windows 正常 Main 父 PID `36592` 各跑及保存兩策略，fresh PID `37712` 禁止重跑或再保存，恰用原兩個 run ID 成對核對、逐筆明細／返回；原 20 份來源、隔離市場資料、Registry 原件與 419 日曲線前後相同，Python socket 嘗試 0。父／fresh 收據 SHA-256 `c2b320f6204c4e7845c58abbd0ae5b9bed2ec51d141e10b05094f20877b1296d`／`68c0985b089a3e7a1beb0ff2c4b57cd0b28d6a4665aa55f4c077649e3d6c96e4`；外層 `single_owned_qa_33173e7a456b4afca6ec546aeaa66eb6/receipt.json` SHA-256 `12dd41826dad9b81383554e1b752dfeb08ce740d84d3a989ace1b4e8a8b34b14`。QA514 對新獨立[試用版 80](../../output/trial/Baldr-Daily-Research-80/TRIAL_GUIDE.md)的實際 `Launch-Baldr.cmd --check`、commit／EXE 身份與五份隔離市場副本前後 SHA 通過；outer `single_owned_qa_b462661e562c4991a852002e1d5affad/receipt.json` SHA-256 `e78cbbcf4594b72b0b4c343d12eebfa619c9e11fa1fafcb59e53ce0103ed925e`。交付收據 `output/trial/Baldr-Daily-Research-80/DELIVERY_RECEIPT.json` SHA-256 `837dc4247dbb01b0fca7f300eca9ba76458a5c900e4e718007a80899ba2359c2`；71 與 73 原件未覆寫。

各組實際 Python／QA 均在 8 GiB committed／12 程序、kill-on-close 與同 workspace mutex 的 Windows Job 執行，啟動前可用 RAM ≥8 GiB，前後三 PID 清冊自然空、process／Job handles 關閉、mutex 釋放，無 forced cleanup。只重驗新增的同版及 P08 Native／EXE 路徑，未反覆跑未受影響 Workbench／validator；既有 `ui_qt.* ignore_errors=True` 不證 UI 強型別。試用版是未簽章、不可攜、四股子集，真人尚未試；來源／幣別／成本權威、完整期間雙策略績效、歷史 PIT、Paper 獨立帳本、真 N、TPEx／MOPS 缺件、自然成熟及 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 各自待驗。沒有正式資料、Task Scheduler、maintainer、push、發布或交易操作。

## Increment81：P08 兩策略原保存輸入與撮合設定交叉核對

**解除的第二階段第四列阻礙**：兩筆 `1.0.0` 基本策略 run 的原輸入互相比對及原規則卡核對已存在，但同時錯記相同本金、費率或部分撮合選項時，兩筆仍可能看似「保存條件相同」。現在對每筆 run 先用 `Decimal` 精確核原提交本金與保存 `capital_cents`、原費率／滑價與保存整數單位，再核原提交與保存 `broker_config` 的費率、風控、部位、成交量限制、執行價格及布林選項。任一內部不一致即阻擋對照；不借目前預設、不改原 run 或金融公式，也不把保存條件通過升成來源／幣別／成本權威或績效資格。

受影響 `app_module/basic_strategy_saved_pair.py` 與回歸測試 `tests/test_single_backtest_rule_execution_v2.py`。新案例將兩筆保存 metadata 的同一欄**同時**改壞，涵蓋本金、費率、非有限本金、參與率、漲跌停旗標、撮合滑價、最大持倉及重新進場旗標，確保不能靠兩筆彼此相同而通過。Look-ahead 自查：只讀原保存 metadata／execution，沒有新增行情讀取、訊號、交易日期、資金或回測運算；精度自查：比較用 `Decimal(str(...))` 與保存整數單位，拒絕布林、非有限與不等值，不做裸浮點決策。

QA517 在七份來源 SHA 與 HEAD `c39876af9040c8ae0b7503369bd424b135fc878f` pin 下，`py_compile`、定向 pytest **25 PASS**、單檔 mypy **success**；outer `single_owned_qa_675f0f2a055a417ba4601be7f854974e/receipt.json` SHA-256 `15be3a58444e4d8837727576b1963721ce3a499a7de4d88c77772c4cf8402477`。其後補非有限輸入斷言及 `DecimalException` 防線，QA518 重新綁來源 SHA，三項同樣通過；原始 `increment81_qa518/receipt.json` SHA-256 `73f45e2e5a55e7ce1916b5a0837f24bb5ea73967528843f7396eee0c282ae3f3`，outer `single_owned_qa_0adc5b8aff314e4cba5488283ef63eb0/receipt.json` SHA-256 `4589000145e3c6eec70c4ade78c15327d01a6fa3d6f909165a37829f96a4ca1f`。QA518 啟動前可用 RAM 約 22 GiB；Job 上限讀回 8 GiB committed／12 程序、kill-on-close、同 workspace mutex，三 PID 清冊自然空、handles 關閉、mutex 釋放、無 forced cleanup。這是開發來源的後端阻擋驗證；UI 未改，沿用未受影響的 Workbench／validator 收據，未做新候選 Native／EXE 及真人操作。

手冊已在[兩個基本策略對照](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#兩個基本策略的原保存研究對照後續開發分支)明示此開發版阻擋及固定試用版80未納入。主 `APPLICATION_MANUAL.md` 現有入口仍連該章節，且屬另一 owner 未提交修改，本輪未改；`PROJECT_SNAPSHOT.md` 同由另一 owner 修改，現況以本具名 QA 與原計畫 §0.4 為準。原試用版66回報對應的可見修正已在固定版80，這次沒有重包或覆寫66／71／73／80。來源用途／幣別權威、可比較的獨立期間績效、歷史 PIT、真 N、自然成熟及完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 仍各自待驗；沒有正式資料、Task、maintainer、push、發布或交易操作。

## Increment82：第一列一般視窗回測結果可讀性

**解除的第一版試用阻礙**：使用者在固定66回報回測視窗模式將設定放在結果上方、三種補充查找擠住摘要且無法讀完。固定80已把補充查找收起並讓摘要捲動，但內容寬度低於1150px仍上下排列。本輪只修 `BacktestView` 版面：一般視窗寬度900／1024／1280px的設定與結果左右並列，極窄內容小於680px維持上下排列；中等寬度讓結果忽略原過大的水平 size hint、設定可水平捲動與手動收合。原回測、策略、保存／讀回、來源、時間及金融數字完全未動。固定80的 EXE 尚未納入此開發來源修正。

受改 `ui_qt/views/backtest_view.py`、`tests/test_ui_qt_backtest_layout.py`。定向幾何涵蓋三種一般視窗、右側摘要文字捲動及設定收合／再展開；QA522 **4 PASS／8 deselected**，outer `single_owned_qa_166ff551a8ae483faf740bf743f5f254/receipt.json` SHA-256 `099f49c89d9e335a94068974a25bc0680898944670bf80add547bc3c1ba604fb`。QA523 共用 Workbench **85 PASS**，但 validator 在沙箱暫存 `data` 路徑 `Path.resolve` 遭 `WinError 5`，造成 **21 PASS／3 FAIL／4 SKIP**，mypy未執行；outer `single_owned_qa_8fa46a5bbf9743d5ad887c16ec0d1ab5/receipt.json` SHA-256 `e5e84029f18032a42542018af38903deb6345e58c98835ad31c3b08ef7eee82a`。只重驗這兩項的 QA524 在固定來源 SHA、隔離根與同一受控 Job 限制下，validator **25 PASS／0 FAIL／4 保護性 SKIP**、八 roots mypy **1043 files success**；outer `single_owned_qa_e1a2e8e1c99e4b71b19a4faa78e9dcf6/receipt.json` SHA-256 `8b10d3730e7581067960c830213401433cdcf080bdfd3f59759746681176dd44`。`ui_qt.* ignore_errors=True` 仍不證 UI 強型別。

原失敗另存：QA520 完整版面測試於既有圖表頁 `QWebEngineView.setHtml` 的離屏 Windows `0x80000003` 中止，尚未執行新中等視窗案例；outer SHA-256 `3064bbcc6ce279aeddbace92e88d77fd975e27a1b1d03f24dfe1bc7b7d7cb7a3`。QA521 首次新幾何斷言揭出結果面板原最小寬度擠壓設定欄，三例 FAIL；改 Qt 水平 size policy 後 QA522 通過，原 QA521 outer SHA-256 `d713ebf400cf6de59c6b43281252735696b9ea50ba4b756f4b8cb1fc68c64a51` 保留。完整 `tests/test_ui_qt_backtest_layout.py` 未被宣稱通過；未受改圖表實體另待合適 QtWebEngine 環境驗證，不把單一離屏崩潰當產品運行失敗。

隔離 Qt 畫面探針 QA526／527 精確量到900px視窗左／右為265／417px、1024px為314／492px、1280px為400／662px，摘要皆有垂直捲軸；QA527 使用應用中文字型擷取三張畫面於 owner task `increment82_visual_font/`，outer `single_owned_qa_8987a228ee3f48eeb705fbd13f553fb8/receipt.json` SHA-256 `55542537692595d1adc22badb7474886dd128fbeac955575972522c7fe7228f1`。較窄設定欄仍需水平捲動，此可用性限制保留。各輪啟動前 RAM ≥8GiB，Job 限制讀回8GiB committed／12程序、kill-on-close、同workspace mutex，結束後三PID清冊自然空、process／Job handles關閉、mutex釋放，無 forced cleanup。原66的價格研究雙擊開獨立視窗是既有行為；固定80已有清篩顯示四股、單股收藏、手動持倉唯一名稱互補及一般個股價量重載，真人仍應用80新版確認。主 `APPLICATION_MANUAL.md`／`PROJECT_SNAPSHOT.md` 為其他 owner 未提交修改，本輪不觸及；操作補充於既有手冊分冊，主手冊原入口已連到它。原第一版範圍與第二階段全部缺件、SOP／Walk-forward原判、完整 Gate 均維持，無正式資料、Task、maintainer、push、發布或交易變更。

**固定試用候選82**：來源 checkpoint `f67d59654655c30669ffdd64f562b131e28211ed` 封存建置於 `dist/candidate_f67d59654655_9af5788e/baldr/baldr.exe`，EXE SHA-256 `ef45c63ad44cdb84cec896cb97fd554695d88613bab024cb0ba2c79a88bd4760`，source.zip SHA-256 `5d66b270285a2ad900e3aebe834501c52eac9d6edfda55f040d80adb52291082`，建置收據 SHA-256 `f440b345529e6eec440c1c6a0aecd712a4539bacfc0b037e51f24d981ea7c320`。QA529 外層 `single_owned_qa_37f225aac1c4477c8d79eb51bddeefe4/receipt.json` SHA-256 `724e322e39e4112e99cf55dd32d89afb0ad25e251aad53f8efa74ca023769867`；QA530 對固定 archive／EXE 的 launch、journey、model、H20 作同版隔離比對通過，outer `single_owned_qa_bba94d85f75c4097a19e79aed52f08ae/receipt.json` SHA-256 `b10c80bb341c9a4cf110065f2fd2d2abbcfa3965a5b7a87d61f13d0ef8c50a37`。H20 是測試 fixture，無正式模型資格。

QA531 以固定 EXE 的 Windows 正常 Main 父 PID `37456`、fresh PID `30104`，在主視窗 900／1024px 量到設定／結果寬度 `363／444`、`363／568`，摘要文字區均可垂直捲動；同一四股隔離副本的原兩個 `1.0.0` 基本策略各得419日曲線，從正常 UI 保存、恰選原兩 run 對照、開原明細／返回及 fresh 精確讀回。20份原來源前後不變、Python socket嘗試0；父／fresh JSON SHA-256 `62e6319d8baa1e506bed510697bf9d5940f91696dabd594856db00b72d2a3717`／`70ad0796122b6ac11ef832c9f6b5731bbee8c1a08c02db9c69991d2a1508c660`，outer `single_owned_qa_eb9b8d2d9f3849dcb80283fd0c1215ae/receipt.json` SHA-256 `9f5d350aeabc2638dd52676da1505fcfc0b5d84322db6bef59e12b09b29fe365`。這些量測不代表成交表現、完整期間或歷史 PIT 已接受。

新獨立[試用版82指南](../../output/trial/Baldr-Daily-Research-82/TRIAL_GUIDE.md)、[已知問題](../../output/trial/Baldr-Daily-Research-82/KNOWN_ISSUES.md)與 `DELIVERY_RECEIPT.json` 已固定；交付收據 SHA-256 `d1d9033506cfaf0639c5a257213ff3435a719440a62ee2c105220d735ffab1fa`。它只複製原80收據逐檔核對過的五份市場檔到自己的 `state/`，原持倉／收藏／回測狀態不搬移。QA532 實際 `Launch-Baldr.cmd --check` 核 EXE、來源 commit、隔離設定及五份市場副本前後 SHA 通過；outer `single_owned_qa_7be02538a6b741b187ae5f3c3f9d7add/receipt.json` SHA-256 `eea2875de43f66c36ff0429061196d6e6caaed5ace1ef8e4bc534b74f167c853`。所有新增 Python／EXE 組維持前組自然 PID0、handles與mutex關閉才啟動，8 GiB committed／12程序、kill-on-close及啟動可用 RAM ≥8GiB，無 forced cleanup。真人 82 的價格研究雙擊、四股比較／收藏、持倉手勢與視窗版面仍待回報；更小視窗與不同縮放未驗。原66／71／80及 P07 預覽均保留。P03 完整文件／單位與 TPEx 授權、來源用途、真 N、完整雙策略績效、歷史 PIT、SOP／Walk-forward、Paper／Forward自然成熟及全 Gate 不因固定試用版升格；未動正式資料、Task、maintainer、push、發布或交易。

## Increment83：P11 固定 EXE 唯讀決策結果回訪

**解除的第二階段第五列阻礙**：Increment79 已把「個股研究 → 決策 → 結果」的 Evidence adapter 鎖成唯讀並改善期限原因，但只驗來源版離屏 widget；固定 Windows EXE 的正常 Main／fresh 能否同樣讀原推薦與 Evidence 未證。本輪復用來源 commit `f67d59654655c30669ffdd64f562b131e28211ed`、EXE SHA-256 `ef45c63ad44cdb84cec896cb97fd554695d88613bab024cb0ba2c79a88bd4760`，不改產品程式。隔離市場沿試用版82五份已核副本；既存正式推薦 `scheduled_rec_20260914_051003.json` 精確複製到隔離 output，原 SHA-256 `2d946a89ebdfe2b3ea66fa246b2fbfb2e685de4d02745db7b0f34eaf5aeb353c`，正式 Evidence DB 只經 `EvidenceRepositoryReadAdapter(read_only=True)` 讀取。正常 Main 的明確 `1528／恩德` context 由原 `_open_stock_research_context` 進頁，切到「決策 → 結果」，返回原來源後再重開；fresh 程序重讀同一 result，不重跑推薦、不建立或改寫 Evidence。這是受控接線與 context 注入，不代表試用版82的四股入口已包含1528，也未驗真人從推薦清單點選或正式根預設配置。

QA534 父 PID `42608`、fresh PID `26168` 各在 Windows 固定 EXE 正常 Main 讀到 **2 筆 Evidence**，journey 投影 SHA-256 均為 `199ecac18285414781a9bb953216c06c32bcc4217c60e4ab6008fef556774cd0`；畫面判為「已連結；尚待結果成熟（未有足夠未來資料），不是實際成交損益」。兩次返回／重開一致，沒有 socket 嘗試或錯誤對話框，五份試用來源 hash 與正式推薦原 hash 不變；Evidence DB 4,079,554,560 bytes 的 mtime／ctime 前後相同（未做整庫 SHA，不宣稱以此證明其全部內容逐位元不變）。父／fresh 收據 SHA-256 `92f6a35b6e8772b3135dd9888892b81b81c71d213ef17ccb1a7d069cf4f221e0`／`d1dba90b7b5896f009e57f4808b0735859ae95bbb36a5764d5ce4286763f3dbe`，截圖 `increment83_p11_exe_main_fresh/parent-p11-main.png`；outer `single_owned_qa_d4ce9b4adf1a437297f48060af815821/receipt.json` SHA-256 `fb1ee7d13c9dae664cb60d2c1755ba170e89053c34cd7213002090d7a906251f`。前組 QA533 後三 PID 陣列自然空、process／Job handles 與 mutex 關閉，QA534 啟動可用 RAM ≥8GiB、8 GiB committed／12程序、kill-on-close，父／fresh actual process handle 各自然終止，結束三 PID 清冊空且無 forced cleanup。

來源狀態表內的 `ready` 是原來源標示，不能取代 journey 的成熟／成交判斷；顯示「尚待結果成熟」及資料日未知均保留，不補造價格、績效或前瞻結果。既存正式推薦／Evidence 僅唯讀，受控 QA 的隔離 output 有副本與畫面收據；未寫正式資料、私人紀錄、Task、maintainer，未觸發自然排程、push、發布或交易。尚缺推薦清單真人下鑽、完整同源價量／來源用途、自然成熟與後續期限收據、正式配置及其他主機驗收；局部 Native／EXE PASS 不等於 P11、G0–G4 或原全範圍 Gate。

## Increment84：真注意公告固定 EXE 讀回與選用 Paper 根啟動降級

**解除的第二階段阻礙**：已保存的 2026-10-15 TWSE 注意公告在固定試用82來源 `f67d59654655c30669ffdd64f562b131e28211ed`、EXE SHA-256 `ef45c63ad44cdb84cec896cb97fd554695d88613bab024cb0ba2c79a88bd4760`，原先僅有 Native Main／fresh 限定證據。本輪以原 `increment48_actual_snapshot_a_pin.json` 的 manifest／receipt SHA-256 `77a8ecdae561cfe6dfcaab46adcd63b2349fec8691cfd8ec7ce1c3cdbdd05475`／`77a30154c67473dc2a1d6e120df896ca89fe0b1c626e667b0a221cad833c89f7`，在固定 EXE 正常 Windows Main 從觀察清單明確開個股研究，驗 2308 原公告原因及價值字串、053040 權證 `-----` 本益比、2330 同日無公告列，再返回並於新程序精確重讀。QA537 父 PID 41104、fresh PID 53024 的三個 case 完全一致，原 13 件來源與試用82五份市場副本 SHA／大小／時間戳不變，socket 嘗試 0；父／fresh 收據 SHA-256 `1545c4d2ef44745ce81cc7f1bab35a70d8a3afeb07b018646d1abaa69f5bac31`／`8c36ee7438242b4b00eefb7ea1f9b4f215036819cfd550e5738e7e8be4ed0b6a`，外層 `single_owned_qa_4e48901db0754fc8b19edf8c98dda809/receipt.json` SHA-256 `da0337562036f6f82e7756482a2d5979df54c16e531a184db83cb5eb4a1a540a`。這是固定 EXE 的**受控注入／指定日期讀回證據**，試用82啟動器未新增注意公告綁定；來源用途尚未接受、歷史 PIT 不合格、TPEx 與其他日期未判，不能當日常完整注意／處置功能。

QA536 原樣失敗保留：隔離環境同時配置無關的選用 `PAPER_CONTRACT_ARTIFACTS_ROOT`，固定 EXE 主視窗在 `Path.resolve(strict=True)` 遭 Windows `PermissionError` 而中止，外層 SHA-256 `d0f4babad564889b3e3d3484a3a53de4da457cef0082be6e3a51c98cf223b920`。QA537 在 F16 測試配置明示停用該無關 Paper 選項後成功，沒有藉此宣稱原固定 EXE 已修補帶有不可解析 Paper 根的啟動情形。開發來源另在 `PaperCheckpointAccountInputs.from_selection` 將選用根解析失敗與驗後消失降為 Paper 停用原因，保留路徑、外部套件邊界與 exact 來源守衛；正常 Main 其餘工作區不應因選用查找而停止。新單元反例在 QA538 通過，原 15 例整組為 **11 PASS／4 FAIL**，四失敗均在沙箱測試暫存根解析；QA539 換短外部暫存仍為 **4 FAIL／11 deselected**，兩輪不抹除。正常 Windows 權限 QA540 的原四例為 **2 PASS／2 FAIL**；兩個後者沿舊 UI 假設 Paper 群組預設可見，與現版「先點 Paper 快照」相衝突。保留原查找、讀回與取消斷言並改為點現行按鈕後，QA541 定向 **2 PASS／13 deselected**；其他兩個原正常根案例沿 QA540 的 **2 PASS**，新增拒絕根與其他未改案例沿 QA538 的 **11 PASS**。未把跨輪加總寫成單次整組 PASS。

QA541 同一已釘來源執行 changed Python compile、Workbench **85 PASS**、更新頁 validator **25 PASS／0 FAIL／4 保護性 SKIP**、八 roots mypy **1043 files success**；外層 `single_owned_qa_393c617fc073403dafecb442c08ed46b/receipt.json` SHA-256 `436a4081029f365dc5b72a60ba938bbf4abc74086297e5468750b2f76a6da9cc`。`ui_qt.* ignore_errors=True` 不證 UI 強型別。所有 QA 組啟動可用 RAM ≥8 GiB，同 workspace mutex、8 GiB committed／12 程序、kill-on-close；前組及各組終態三 PID 陣列空、process／Job handles 關閉、mutex 釋放，沒有把 forced cleanup 當成功。固定試用82仍是原 EXE，開發來源的 Paper 啟動修補尚未封裝；真人試用、來源用途／每日 validator、歷史 PIT、完整財報與 P00–P14／G0–G4 各自未接受。沒有正式資料寫入、舊 GET 重抓、Task／maintainer、push、發布或交易。

## Increment85：P06 已選策略帳全部持股的初次配置研究

**解除的第二階段第三列操作阻礙**：原入口已能明選策略帳及同日 Health，卻仍要求使用者手抄原帳本持股代碼才能開始比較。本輪在「持倉管理 → 顯示進階 → 配置研究封存」加入明確的「使用所選帳本全部持股」選項；勾選後由所選 exact checkpoint 帶入股號，不讀目前手動帳或全域最新清單，手動指定部分持股仍可用。兩種模式都沿原收據時鐘、同帳戶 Health／mark、Decimal 配置、保存前重核與 canonical artifact；空持股、缺 Health／mark 仍拒絕，未持有候選不補造。沒有改策略或績效公式、正式帳本、資料寫入權限或歷史資格。

變更為 `app_module/portfolio_research_initial_source.py`、`app_module/portfolio_research_scenario_workspace.py`、`ui_qt/widgets/portfolio_research_scenario_widget.py` 及兩個受影響測試檔；操作與排錯同步 `docs/07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md`。主 `APPLICATION_MANUAL.md` 原入口已指向該分冊，本輪該檔及 current 架構分冊均有其他 owner 未提交修改，沒有同檔覆寫；來源／artifact schema、現行資料流與主手冊入口均未改。

QA543 在同一具名受控 Job 下，改動 Python 語法通過，兩份來源／UI 測試合計 **17 PASS**（包含全部持股保存、讀回、手動與全持股互斥、缺 Health 拒絕），Workbench **85 PASS**，更新頁 validator **25 PASS／0 FAIL／4 保護性 SKIP**，八 roots mypy **1043 files success**；runner 收據 SHA-256 `c6eb3dac15ad8ed9997e7bd19f8ab69497afc21868412b7f40bbd1a9c950fdbc`，外層 `single_owned_qa_db026fe735fa492a9a8fc7e5f4934d72/receipt.json` SHA-256 `10f3cb83f06bfce81ae97a60bf36916981a9d5f1f147d2a893db28c5b3d5345a`。`ui_qt.* ignore_errors=True` 仍不證 UI 強型別。

QA544 在隔離合成 Paper 帳與真正 Windows Main 父 PID **49180** 勾選全部持股，從原同日來源比較、保存，再開 2330 個股、返回；新 PID **400** 重開同一 artifact `sha256:1ee647c8de83a1fc78ed2a1e1b4f38e31b6adf036cae904507c5abc977daec9e`。兩程序的候選均為原帳本 `2330`、比較與 DB SHA 相同，21 份原來源前後 pin 不變、沒有借手動帳；父／fresh 原收據 SHA-256 `4edd164d1e55a0f45d445fee83f588a34e4715efe48f19de1a47fabbacc4cc66`／`53f9187babca1b95825ae2e2bdd7cb78513d5d8a1764ffe7f55951fa4da8cea0`，runner SHA-256 `3ca3a09a8d2e181a4bc611cc095e75af175c1eb08bd0ee4be49656b02c321759`，外層 `single_owned_qa_488a0b8e26744e5f8d4c869c27abc798/receipt.json` SHA-256 `340b4dd261466bd7515cccb26e64f670f9f0ed49beecc1b1ba30962b989b382d`。兩組均在啟動可用 RAM ≥8 GiB、8 GiB committed／12 程序、kill-on-close／同 workspace mutex 下執行；前後三 PID 清冊自然空，process／Job handles 關閉、mutex 釋放，無 forced cleanup。

這是**開發來源的合成帳本操作出口**，固定試用82 EXE 未納入；真私人帳、未持有候選的同源 Health／行情、完整 P06、Native／EXE、來源權威、歷史 PIT 和 G0–G4 仍各自待驗。季度官方 26-route 觀測已有原件，但一般金額單位及逐筆可得時間仍未知；不借政府資料集 EPS「元」推論營收單位，基本面第二列維持隔離。沒有重抓耗盡的舊 GET、寫正式資料／私人原件、改 Task／maintainer、push、發布或交易。

## Increment86：P11 逐期來源狀態與待成熟並列

**解除的第二階段第五列判讀阻礙**：先前同一 candidate 只要任一期 `insufficient_future_data`，頁首就整筆顯示「尚待結果成熟」，遮蔽其他期限已由來源標示 `ready` 的事實。`ui_qt/widgets/decision_outcome_journey_widget.py` 現在從原唯讀 `OutcomeMaturityRecord` 逐期歸組：只有精確連結的期限才列來源 `ready`／`observed`，資料不足、未知及連結異常各自提示；衝突優先保留。這是展示判讀，不更改 Evidence、來源結果、報酬或成熟資格。`ready` 仍只是來源標示，不能據此宣稱已核准績效或實際成交。受改 UI 回歸新增 5／10／20 `ready` 與 60 待成熟的混合案例，以及衝突期限不可冒充 `ready` 的反例；操作同步主手冊與個股指南。固定試用82 EXE 沒有此開發來源修正。

QA546 受控 Job 的改動 Python compile 通過、`tests/test_ui_qt_decision_outcome_journey.py` **13 PASS／1 SKIP**、Workbench **85 PASS**；其更新頁 validator 在隔離 TEMP 的 `data` 目錄遭 Windows `Access is denied`，停於 **21 PASS／3 FAIL／4 SKIP**，原樣保留；runner／outer 收據 SHA-256 `8dde931f3d8d4c12dc91146db4bcbd98054bee76854b4fd85c9f76dee0544539`／`386c9786ca1de2dff53c5e178cc0e06b4ea6f7d5553cce58c73b2133f5652314`。QA547 改用 task 內另一隔離 TEMP，仍在同一暫存目錄權限檢查得相同 **21／3／4**，沒有把失敗重試抹去；runner／outer SHA-256 `ba50f7d8695bcc712e76bb97fa236a3edae575a79ade0eba573d58e55d9ac620`／`64fb447073847270338ccee823ff017586416779d6ecde3c3fd1d2027e0968c5`。兩輪均尚未執行 mypy；失敗來源是原離線日價 fixture 的 WinError 5，其他三種 fixture 同步成功，非 P11 計算斷言。

QA548 保留相同來源 pin、前組自然關閉收據及 8 GiB committed／12 程序、kill-on-close／workspace mutex，改在正常 Windows 權限執行同一 validator 與未執行的 mypy：validator **25 PASS／0 FAIL／4 保護性 SKIP**，八 roots mypy **1043 files success**。runner／outer SHA-256 `c1c54f9bf4d0fbc9fee8af51cc0a680f608d7d8aee003486db8174be2e8ec6e0`／`0d7a9dc6bdd6fec0fd81c3c1a79bbc80242c8dc526ff1f28015f9046d9c39dd6`；前後三 PID 清冊空、process／Job handles 關閉、mutex 釋放，無 forced cleanup。`ui_qt.* ignore_errors=True` 仍不證 UI 強型別。尚未以正常 Main／fresh 或固定 EXE 驗此版頁首，真人從推薦清單進入、正式來源預設接線、自然成熟與 P11／G0–G4 均維持未接受；未寫正式資料、Task、maintainer，未 push、發布或交易。
