# Track B 金融資料交付契約

## R8 六包複核補充（優先於以下歷史觀測）

本次具名結果見[六包複核](../06_qa/BALDR_TRACK_B_SIX_PACKAGE_REVIEW_20261023.md)。Legacy 7/88僅證custody，不能推導歷史PIT；81筆仍拒絕。回傳`effective_custody_verification_tier`與`custody_evidence_basis`，呼叫者明示允許集合仍須符合。Weekly例外限定固定10/19 run、terminal及D/F完整原件pins，不授同根新收據遷移權限。

Forward baseline政策必須由真實事件canonical hash、有效research capture context及本輪cutoff上限建立，讀回使用已登記context與resolver，不接受payload自帶cutoff自授權。`qualification_event_id/hash/context_hash/price_date/context_basis`與context ID必須保存；outcome另用outcome_realization。Research context不授盤前自然證據或正式金融PIT；沒有外部用途接受及逐列availability仍拒絕。

Track C須讀每筆market/period/issuer/sourceversion、raw/row/revision SHA、五類時鐘、尺度證據及其scope，currency保持unknown；月營收矩陣9,423列是coverage盤點，ML、歷史Backtest、正式Scoring與Paper不因此合格，OOS及訓練保持false。Track A可唯讀展示來源原值、有效custody tier、unknown與拒絕原因，不把版本日期當生效順序，也不將6443兩版本指定勝負。正式runtime與Paper帳戶/cash/mark/Ledger仍Owner尚未選定。

本契約約束 Track B 對 Track C（ML 資料）與 Track A（唯讀研究展示）的交付。它不建立來源接受、不啟動訓練、不改 Ledger，也不取代各來源的用途契約。2026-10-22 實際觀測、具名狀態矩陣及工程缺口見 [Track B 驗收](../06_qa/BALDR_TRACK_B_DATA_OPERATIONS_20261022.md)。

## 共通身份與資格

每個交付單位必須帶以下欄位；缺件保留 null／unknown 及具名拒絕原因，不能補零或選取鄰近版本。

| 欄位組 | 必要內容與判讀 |
|---|---|
| Source | source family／source ID、venue、endpoint、parser/schema version、用途接受 reference 與外部 SHA；公開授權不等於金融用途接受 |
| Version／Custody | 原始 bytes artifact reference／SHA、revision ID／parent revision、原件取得／保存時間、custody 根／DB 身份；file-byte SHA 與 canonical content hash 顯名區分 |
| Time | decision timestamp／timezone、source date／period、available_at 及其依據、cutoff、capture completion、persisted_at；未知官方發布時間不得用本機時間冒充 |
| Coverage | requested／eligible／observed／missing／excluded／unknown 的分母、代號與日期範圍；無明確分母不能由 row count 宣稱全市場完整 |
| Quality | 欄位／單位、缺值／重複／日期衝突／修訂／staleness 及 blocker；金額與決策運算維持 Decimal／整數契約 |
| Execution | exact task、run／parent ID、aware started/completed、terminal receipt 外部 SHA、code version、exit code；latest 僅是 locator |
| Consumer | consumer 名稱／版本、同 run/date/artifact 的唯讀讀回、warnings／reject reason；上游 passed 不推導 consumer accepted |
| Qualification | Engineering、Natural Scheduled Execution、Source Qualification、Data Coverage、PIT Validity、Consumer Readiness、External Dependencies 分列；每用途獨立判定 |

Codex heartbeat的具名native turn可證明監測執行，不能代替被監測的producer／consumer或金融資格。10/22兩個target的completed／error=null已讀回；名義05:30／06:20 Pacific與實際18:09 UTC dispatch分列，原因與準時性UNKNOWN。Recommendation同次原artifact的eligible date 10/20與decision date 10/22已按固定SHA讀回，Paper frozen拒絕是stale來源守衛，不將eligible date改成當日來放行。

Root 新增的修訂 custody profile 只處理三份精確修訂 run 的舊資料庫身份、兩份市場來源與16份錯日排除來源定位。它固定原 hash 鏈與新唯讀保護狀態，**不是這些原件逐檔搬遷 SHA 通過的證據**。原修訂、來源取得時間、禁止歷史 PIT 及訓練資格不變；新 rollback、未知 marker、替換 DB、原 D 資料重現或 hash 漂移均重新拒絕。

校準 pipeline 新 run 將 official child 的完整 invocation stdout 保存為不超過 256 KiB 的 create-only artifact，傳遞其 publication ID、manifest file／logical hash、canonical events hash、stdout path／SHA 與 aggregate run ID。真正 source-contract reader 以 strict JSON、plain path／no-follow 有界讀取核原件，要求 stdout 位於該 aggregate 的固定 run 目錄，並將 expected pins 與實際讀到的 publication 比對；來源 manifest／canonical／raw custody 尚未通過時，不標 `consumer_binding_verified=true`。成功比對不授歷史 PIT 或正式來源資格；immutable contract／父 terminal 保存相應引用。

目前 recommendation mixed query 仍因88筆legacy data_path在核准runs root外而拒絕；33筆canonical index數不等於可交付33筆混合列表。88個F counterpart的新hash不是原搬遷同一性證明，原target SHA清冊沒有這88份逐檔entry；不建立通用alias、不改catalog或跳過legacy。原自然Decision診斷缺cause，當前readonly probe只證明現在的拒絕；新diagnostic metadata保留exception type及240字內reason，不含traceback／payload，也不補造path／原SHA。

官方 refresh 失敗時的既有 last-good 政策保持，明示 `last_good_fallback`、aggregate ID 與 `consumer_binding_verified=false`；它不是本次 child publication。10/22 舊自然收據沒有這項 invocation 綁定，不能事後補造「Decision evidence／校準確實使用了早一個 Task 的 publication」。Decision evidence 的 research-only、snapshot degraded 與 recommendation integrity warning 亦不因此解除。

## Track C：ML Data Readiness

資料集 manifest 應引用共通身份與資格，另明示 feature／label 名稱、資料期間、symbol universe、train／validation／test／OOS 分界、每筆決策 cutoff、feature available_at、label planned maturity／actual observation 及 purge／embargo 政策。沒有實際 manifest 與 consumer 讀回時，本文件只是交付要求，不是已交付可訓練資料集。

1. Feature 只取 `available_at <= decision_cutoff` 的版本；歷史值、current-observed、prospective-capture 與歷史 PIT 分開。月營收取得歷史數值不證明當年可得時間。
2. 改寫後的來源必須帶 revision lineage；目前表重算、重抓與 late correction 不回填過去 OOS 特徵。PIT 盤前 archive 依既有 Asia/Taipei 08:30 cutoff 與真實 capture completion 判定，盤後不可補抓冒充盤前。
3. 尚未成熟的 Forward label 為 null，附官方日曆的 planned maturity 與缺價理由；不得使用 row offset、近價或平盤補值。成熟標籤仍須具名價源版本／custody 與 source availability。
4. Raw PIT 上游 blocked、rule-only Copilot、candidate／shadow 或 Promotion evidence 的局部狀態不授 training／validation／OOS／promotion。Track B 不替 Track C 啟動大規模重訓。

2026-10-22 可交付的是原收據／現況與限定研究資料身份；Raw PIT 的當日來源階段未啟動，Formal compatible count=0，當日 cutoff 前 PIT capture 缺件。Forward 自然 run 有 172 筆 outcome 更新，但仍有缺價、未成熟與來源 lineage 限制，不是完整可訓練資料集。月營收 1,975 筆 YoY 的限定研究使用不能外推為正式 ML／歷史 PIT 資格。

### Forward 實際來源觀測接口

新排程 run 的 `source_observation` 引用 `forward-source-observations.v1`，含 run ID、相對 manifest 路徑與外部 SHA、query／row／chunk counts。Manifest 保存實際執行 SQL／參數、fetch 時間、原始回傳列的 canonical hash 與 create-only chunks，並將 cache reuse、event／window／outcome hash 綁到 query ID。SQLite 浮點值以 `sqlite_float` 字串觀測表示保存，不能將其當作新增決策計算格式。

此接口明示 `source_availability=unknown`、`pit_qualified=false`、`training_eligible=false`、`cross_read_snapshot_consistency=not_guaranteed`。同一次讀取的列證據不能證明原發布時間，也不宣稱各 query 是同一交易快照。下一次自然 run 才可能產生新 manifest；10/22 原 172 筆結果不回填來源引用。Recorder 單次使用，產物先持久化並讀回，再允許 outcome upsert；超限、重用或保存失敗即拒絕該輪寫入。

**剩餘來源工程：逐筆價格版本與可得時間映射。** 現行 `daily_prices` 只有市場欄位及 `(symbol, date)` 主鍵，沒有 source version、revision ID 或 available_at；同鍵更新不保留舊版本。現有 revision gate 只作全域 cutoff／修訂風險檢查，不能替 Forward 同次 fetched rows 授逐筆來源資格。合格接口須將 `(symbol, date, row content／source_row_id)` 綁至已接受的不可變官方 payload／revision ID／SHA、可信發布及本機可得時間，並保留被替換版本。相同價格值、交易日期、全域 gate 或目前 DB hash 均不能代替此映射；目前沒有可安全接用的合格 resolver，不改正式表或回填歷史來製造資格。

單 chunk／manifest 上限各 512 KiB，每 run 64 MiB／128 chunks／500,000 rows／4,096 queries／10,000 outcomes；保留目錄達 4,096 runs 或 12 GiB 即拒絕，不自行清理。Consumer 應依 manifest／chunk SHA 讀回，仍須另外取得來源用途、availability、revision／custody 及 OOS 資格，不能只憑此引用授訓練或正式績效。

上游新增TPEx同次逐列projection／SQLite publication，與既有TWSE列證據分開；只有本次raw、原列ordinal、parser重建17欄、CSV／merged唯一鍵及readonly SQLite全部吻合才產生映射。後續來源身份接線如下；這仍不是Forward金融合格resolver，不能把觀測時刻填成官方availability或補回舊172筆。

#### 同次 fetched row 的來源身份接線

Quick僅將本輪SQLite同步回傳的captured TWSE／TPEx publication descriptor保存成`daily-price-source-bundle.v1`；create-only run檔以外部SHA固定，`latest.json`僅為精確locator，不掃目錄或補選舊publication。`quick_execution_passed`只表示Quick結果；`natural_success=false`固定，不由passed推定自然排程。Bundle保存DB相對路徑與檔案device／inode；來源家庭、完整列、raw／parser／custody仍由consumer另外核對。

Forward從`config.output_root`／`config.data_root`讀來源bundle，與本輪artifact output root分離；可由caller明選bundle descriptor，不從DB父目錄猜來源根。正常價格SELECT在同一次fetch取17欄，計算仍只沿原日期與close；binder不重讀SQLite、不按相同收盤價搜尋來源。每列只能有一個family的完整投影吻合；兩者吻合、缺descriptor／欄位、列漂移或來源證據無效均為具名unknown。TWSE原raw ordinal由固定parser重建，明示`derived_verified_raw_ordinal`，不改舊artifact。來源證據的本輪快取不替代每列內容比對。

有逐列binding時，manifest為`forward-source-observations.v2`，保留原query／outcome／cache-reuse關聯與actual rows hash，另記`source_bindings_sha256`；`forward-source-observation-bound-chunk.v2`把rows和bindings按相同位置分chunk。無binding的既有呼叫仍發v1。原512KiB／64MiB等預算不放寬；binding bytes一併計入。Track A可唯讀展示`source_identity_bound`及原件SHA／ordinal，不能顯示來源已接受；Track C不得從此狀態授訓練、OOS或label資格。

所有結果仍為`source_use_accepted=false`、`available_at=null`、`source_published_at=null`、PIT／training=false。尚缺可信發布／可得時間、來源用途接受及完整歷史修訂版本；同鍵被替換前尚未保存的歷史不能由新接線恢復。定向QA與自然生效狀態以[Track B驗收](../06_qa/BALDR_TRACK_B_DATA_OPERATIONS_20261022.md)為準。

六月歷史HTML的獨立scale-only proof只證明固定兩個raw的逐表金額欄為千元尺度、百分率不乘1000；currency仍unknown，原archive的unit_status／金融unit proof不改。它不授ML金額特徵、歷史PIT或OOS，亦不外推兩個OpenAPI，詳[月營收契約](MONTHLY_REVENUE_FULL_SCOPE_CONTRACT.md#2026-10-22-track-b-歷史原件增量)。

## Track A：唯讀研究展示

透過既有 read model／DTO 與 provider port 讀取，保持 `mode=ro`／`query_only`、固定 artifact 身份及明確 source/data/decision 日期；不要求 UI 直接解析正式 DB、原始 receipt 或私人 binding。新增 UI 欄位沿 typed interface 另行接線，Track B 不修改 UI。

展示至少保留 source identity/version、資料截止日、available_at 依據、品質、coverage、各用途資格及拒絕原因。`current`／`stale`／`unknown`、`candidate`／`research_only`／`formal_qualified` 分別顯示；不可由 Task result=0 或資料檔存在變成「今日正式可用」。

月營收目前可展示具名雙市場原值、百分率／YoY與原unknown；兩個OpenAPI金額不標TWD、不推定千元或乘1000。六月固定HTML可依獨立proof標示「原報表千元尺度、幣別未知」，仍不換算TWD。Paper的舊cash／mark、研究sizing或500,000 TWD契約數字不可展示成真帳戶當日資金。Forward的未成熟欄位保持null及目標日，不宣稱績效或交易權限。

讀回不得寫行情 DB、來源檔、Ledger 或正式控制路徑；Research Run、使用者筆記的既有保存能力依原本獨立契約。金融 source gate 失敗可展示原因，不把一條線缺件擴成其他獨立研究資料的全域禁止。

## R7 獨立複核交付界線

R6 只是接任工作宣稱，不能當完成接受；原件保持。本次 R7 位於 `output/tasks/baldr-track-b-succession-review-20261022/`，含外部 SHA、拒絕理由與精確來源引用。實測與七維狀態以[獨立驗收](../06_qa/BALDR_TRACK_B_DATA_OPERATIONS_20261022.md#接任交付獨立複核-r7原完成裁決不成立)為準；不得宣告 `DATA_PIPELINES_ENGINEERING_COMPLETE_AWAITING_MATURITY`。

Track C 必須逐筆取得 source ID/version、raw/custody/projection SHA、原可得時間依據、revision、coverage/品質、用途接受外部 SHA、decision cutoff、label outcome cutoff、PIT 與 OOS 分界。Forward 明確配置需同時給外部 binding path/SHA、role/cutoff 與 exact bundle run/path/SHA；只重算內文 SHA 不授資格。版本閉包只表示本機已保存 publication，非官方全歷史。缺任一條件維持 training/validation/OOS/promotion=false，不自行啟動大規模重訓。

Scheduled目前僅接`outcome_realization`且cutoff不晚於checked_at；`decision_baseline`仍缺每事件decision cutoff/價格日上下文，明確拒絕。固定bundle primary可消除同源同完整列的重複發布歧義，但不能跳過ledger的真修訂檢查。

四個月 HTML 的 scale-only proof 可逐份外部 SHA 讀回，千元乘數1000、currency unknown。TPEx 863共同公司相符不包含其餘30/3家；TWSE 6443兩欄差異保留，cross-verified scale未成立。歷史樣本 not_visible_by_cutoff，正式Scoring gate=false；不得將取得歷史值改成取得歷史可用時間。既有限定百分率研究資格依原包，不被單一無關缺件全域停用。

Track A 只經原typed provider/read model展示。Legacy弱custody限顯式audit envelope，保留research_only/custody_verified/reason；不可轉普通推薦DTO而丟失資格。有限Git原件adapter逐筆核固定commit/blob/rawSHA/完整原文，再核DB row及當前原件SHA。清冊16/28/44不是自動授權，總121不作查詢成功標準。正式來源未選定時顯示具名unknown/candidate；不用預設500k或舊cash當真帳戶。

`qualification_proof_sha256`是完整性校驗，不是簽章；Consumer須用同一外部resolver、role/cutoff及修訂帳本重驗。舊v1觀測保持相容，v2對每chunk/row/binding/count/hash、路徑與有界讀回逐項驗證。Task=0、process exit=0與事後scale證明均不能提升金融用途。
