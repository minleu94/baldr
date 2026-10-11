# PIT 產業分類每日真實來源產製方案（2026-09-15）

> 研究日期：2026-09-15（Asia/Taipei）
> 性質：read-only source/design audit；本文件只提出下一個 implementation increment，不修改 production code、UI、scheduler、既有 artifact 或正式資料。
> 研究邊界：只查官方 TWSE、TPEx、data.gov.tw 公開頁與既有 repository entrypoint；未做 bulk crawl、歷史回填或正式資料寫入。

> **歷史提案／狀態補記（2026-10-11）：** 本文後段包含 2026-09-16 的 bounded probe 與 P0 工程狀態補報；當時 `5371` exact join 仍 blocked，沒有產生 taxonomy bundle。P0／P1 工作切片與來源建議是該時點方案，不代表目前來源接受、現行待辦或執行授權；現況依後續 QA 判讀。

## 結論

要讓正常日產物可被 `PITSectorMembershipReader` 消費，來源不能再由一份手寫 mapping 代替，至少要拆成三個可追溯角色：

1. **每日 membership**：沿用官方 `t187ap03_L`（TWSE listed）與 `t187ap03_O`（TPEx OTC）的 raw JSON capture。它確實有代號、產業代碼與出表日期，但沒有代碼名稱與 per-security type。
2. **靜態 taxonomy definition**：從官方 TWSE／TPEx 格式規格或分類修正文件保存原始 bytes，產生依市場、依有效日版本化的「產業代碼 → 顯示名稱」mapping。這是定義檔，不是每日 membership。
3. **每證券 security type**：技術上可用官方 TWSE ISIN all-securities 頁的 `Type of security`、`Market`、`Industrial Group`、`CFICode` 等欄位做 current-day shadow source；普通股票也可由官方 `Stocks` 段落的 section context，加上 `CFICode` 等同列證據，形成可重驗的型別判定，不必要求每列一定有文字為 `Type of security` 的儲存格。但該頁仍是現況快照，本輪沒有找到針對此查詢頁的明確再散布／正式使用授權條文。因此技術上可先產生 local research candidate／diagnostic；在 bulk completeness 與適用條款未被證實前，不能把它默認成正式 accepted source，也不推論本機研究一定需付費或被禁止。

獨立的 daily-price denominator 與 `scores_bp` 仍由 `formal_rule_source_producer` 及既有 denominator lane 提供；它是分母與 clock evidence，不是產業分類 producer，也不應被擴寫成 taxonomy 語意來源。

目前最小且能保留既有 parent clock／universe 的路徑是：**維持原本全 L/O rows、全市場 `universe_hash` 與 clock，再新增 market-scoped taxonomy schema，讓同一個 full sidecar 依 row 的 `market_scope` 選取官方 mapping。** 若一定要沿用現行 v2 reader，則必須產生不改動 parent 的 market-subset universe／clock／source-registry projection；不能只把全市場 hash 複製到較少 rows。兩種取捨在第 2.2 節說明。不應把 `t187` 的公司基本資料默認標成 `common_stock`。

## 1. Reader 的真實驗收契約

現行 `data_module/pit_sector_membership_reader.py` 已把 taxonomy 視為獨立、版本化、可重驗的 lineage。`pit-industry-taxonomy-identity.v2` 要求下列欄位全部存在且不可多欄位：

```text
schema_version
classification_version
source_id
source_version
source_hash
source_path
available_at
effective_from
classification_source_id
classification_source_version
security_source_id
security_source_version
universe_hash
symbols
mapping
security_type_by_symbol
mapping_hash
```

`taxonomy_source.json` 亦受 exact-schema `pit-industry-taxonomy-source.v1` 驗證，至少必須包含：

```text
schema_version
classification_version
source_id
source_version
available_at
effective_from
classification_source_id
classification_source_version
security_source_id
security_source_version
mapping
security_type_by_symbol
```

reader 會重新讀取 `source_path` 的 bytes、計算 `source_hash`，再比對 identity 與 source 的時間、版本、mapping、security map、universe 及 hash；只要有 warning，`taxonomy_verified` 就不成立。`industry_filter_usable` 還必須同時滿足 artifact accepted、rows 可用、taxonomy verified。

因此，以下做法都不符合契約：

- 把 `meta_data/companies.csv` 的現況 mapping 套到過去日期。
- 只在 identity 寫一個自報 `source_hash`，沒有同一份可讀 source bytes。
- 只填產業 code，不填 `security_type_by_symbol`。
- 用「這些是公司基本資料」推論每列一定是普通股。
- 把 HTTP `Date`、頁面上的 date-only label 或商品的預定產製時間當成實際 `available_at`。

2026-08-25 的真實 prospective artifact 已證明這個 fail-closed 邊界：它沒有可重建 universe hash 所需的 `scores_bp`，也沒有通過 reader 要求的獨立 taxonomy identity/source；不能因為 raw JSON 與 fixture hash 相符，就宣稱正式可消費。

## 2. 官方來源查核結果

下表的「查核日期」均為本次研究的 2026-09-15；`available_at` 的建議值一律是本機完成 HTTP response 讀取的 aware timestamp，而不是來源頁面宣稱的產製時間。

| 角色 | 官方來源 | 本輪確認的欄位／例子 | 真正能證明的內容 | 時間、授權與限制 |
|---|---|---|---|---|
| TWSE 每日 membership | [TWSE `t187ap03_L` OpenAPI](https://openapi.twse.com.tw/v1/opendata/t187ap03_L)、[data.gov dataset 18419](https://data.gov.tw/dataset/18419)、[MOPS CSV resource](https://mopsfin.twse.com.tw/opendata/t187ap03_L.csv) | `公司代號`、`產業別`、`出表日期`；metadata 還列公司名稱、上市日期、普通股／TDR 股數等公司基本資料 | 可作 raw membership observation、產業 code、date-only label | data.gov metadata 標示政府資料開放授權條款第 1 版、免費；頁面標示每 1 月更新，不能以 metadata 頻率保證每個交易日都有新 snapshot；沒有 numeric code → name map、per-security type、歷史 interval 或發布時刻 |
| TPEx 每日 membership | [TPEx `t187ap03_O` OpenAPI](https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O)、[data.gov dataset 25036](https://data.gov.tw/dataset/25036)、[MOPS CSV resource](https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv) | `SecuritiesCompanyCode`、`SecuritiesIndustryCode`、`Date`；CSV 對應公司代號、產業別、出表日期 | 可作 TPEx OTC raw membership observation、產業 code、date-only label | data.gov metadata 標示政府資料開放授權條款第 1 版、免費、每 1 日；同樣沒有 numeric code → name map、per-security type、歷史 interval 或發布時刻 |
| TPEx emerging | [TPEx `t187ap03_R` OpenAPI](https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R)、[data.gov dataset 28568](https://data.gov.tw/dataset/28568) | 同 O 的英文欄位形狀，scope 是 `tpex_emerging` | source definition 存在，可作日後獨立 emerging source candidate | 現行 machine producer／denominator lane 只要求 listed + OTC；不能把 R 靜默併入 OTC 或宣稱全市場 |
| 每證券 current type／market | [TWSE ISIN all securities](https://isin.twse.com.tw/isin/e_single_main.jsp) | `ISIN Code`、`Security Code`、`Security Name`、`Market`、`Type of security`、`Industrial Group`、`Date Stock Listed`、`CFICode`、`Remarks`；官方結果可見 `ETF`、`Listing Warrants` 等 type，普通股票位於 `Stocks` 區段 | 技術上可用來區分普通股票與 ETF、權證等特殊商品，並做 market／代號完整性檢查；若普通股票列的 type 儲存格為空，可保留 `Stocks` section context 與同列 `CFICode` 作為型別證據 | 是當下全市場查詢快照，不是 PIT interval；沒有本輪可採的 numeric industry code 或官方 effective-from。應保存 response bytes、request/final URL、status、content type、response completion；頁面現況日期不能回填歷史。已查到的 [TWSE 交易資訊使用頁](https://www.twse.com.tw/zh/products/information/use.html) 是一般交易資訊使用規章／契約／收費入口，但本輪沒有證明它明確適用於 ISIN public query；故不推論本機研究必須付費或被禁止，只把 ISIN 的 license／再散布 scope 記為未確認 |
| TWSE listed equities current page | [TWSE ISIN listed equities](https://isin.twse.com.tw/isin/e_C_public.jsp?strMode=2) | `Security Code & Security Name`、`ISIN Code`、`Date Listed`、`Market`、`Industrial Group`、`CFICode`、`Remarks`；查核結果帶 `Date Stock Updated: 2026/09/15`，例如 1101／Cement／`ESVUFR` | 可作 current listed-equity cross-check；`Stocks` 章節是來源語意上的股票群組 | 沒有 `Type of security` 欄；不能單靠此頁補 reader 要求的 per-symbol type，也不能把 `Industrial Group` 英文名稱當作 t187 numeric code map |
| TPEx current page | [TPEx listed equities](https://isin.twse.com.tw/isin/e_C_public.jsp?strMode=4)、[emerging page](https://isin.twse.com.tw/isin/e_C_public.jsp?strMode=5) | 同一類 ISIN、market、industry group、CFI、listing date 欄位 | 可作 current market／listing observation | 仍是 current snapshot；本輪未確認完整 type 欄與可供 PIT 的歷史有效區間；不替代 all-securities type source |
| TWSE 靜態 classification crosswalk | [TWSE 證券商作業手冊頁](https://dsp.twse.com.tw/brokerManual/list) → B12.00 base PDF、[TWSE 2023 format change notice](https://eshop.twse.com.tw/zh/news/detail/0000000087e9b84901886b8d96940024)、B12.13 revision history PDF、現行上市公司產業分類法規頁 | 四份官方 raw component 重算 B12.12 target mapping：B12.00 base 29 碼，加上 2023 公告的 code 16 rename／35–38 additions，再由 B12.13 原始歷程逐段確認 B12.00–B12.12 只有 B12.07 改 Appendix 3，最後以現行法規頁交叉核對 33 名稱；safe boundary `2026-05-01` | 可作 TWSE bounded code → display name definition；runtime 必須保存四份 raw bytes/hash、component completion、current revision、`effective_date_basis`／evidence 與 component lineage。B12.13 本身是 115/12 future evidence，不直接作 target-date mapping | 四份檔案分別是 base／change／history／cross-check，不是每日 symbol membership；2023 公告不能取代完整 base map，B12.13 Appendix 3 不作 target mapping source。官方索引中的 B12.12 historical URL 本次 redirect 至 root，沒有採用的單一 B12.12 PDF；但 composite 已可由四份官方 raw 重算 |
| TPEx 靜態 classification crosswalk | [TPEx 上櫃股票 IP 行情網路規格書 V.12.18（115/05/18 生效）](https://dsp.tpex.org.tw/storage/regular_system/%E4%B8%8A%E6%AB%83%E8%82%A1%E7%A5%A8IP%E8%A1%8C%E6%83%85%E7%B6%B2%E8%B7%AF%E8%A6%8F%E6%A0%BC%E6%9B%B8%28V.12.18_TCPIP%29.pdf)、[TPEx 產業類別修正對照表](https://www.tpex.org.tw/storage/eb_data/11203/112005542811-2.pdf) | V.12.18 附錄列 `02 → 食品工業`、`16 → 觀光餐旅`、`35 → 綠能環保`、`36 → 數位雲端`、`80 → 管理股票` 等；舊／修正文件可追蹤分類變更 | 可作 TPEx 的靜態 code → display name 定義與生效版本 | 規格書／修正對照表是 static definition；IP feed 本身不是本輪已取得的免費 raw membership。來源路徑若因網站改版失效，要以官方新版本重新 capture，不可手寫補 map |
| TWSE 歷史／security status 候選 | [TWT58U 證券及產業別對照表](https://eshop.twse.com.tw/zh/product/detail/000000006e0bbe8d016f18269c59032c)、[T97 漲跌幅度表檔](https://eshop.twse.com.tw/zh/product/detail/75ce5fd1ad574df49ad9ff82209ca837) | TWT58U 有股票代號與產業別代碼；T97 有股票代號、上次交易日、交易方式、處置／注意／委託限制、產業別代碼、證券別代碼、股票名稱等 | 可能補 2019-12-23 或 2014-01-06 以後的歷史／status lane | 官方付費商品；T97 商品頁列每日 23:30、起始日 2014-01-06、內外部月費與歷史訂購限制。未取得訂單、交付 raw、實際交付時間、格式版本與 hash；不是本次免費最小方案 |
| TPEx 歷史／security status 候選 | [TPEx T30／收市後資料購買](https://www.tpex.org.tw/zh-tw/service/data/product/post.html)、[TPEx 收市後格式說明](https://www.tpex.org.tw/storage/regular_system/%E6%96%B0%E7%89%88%E6%94%B6%E5%B8%82%E5%BE%8C%E4%BA%A4%E6%98%93%E8%B3%87%E8%A8%8A%E6%A0%BC%E5%BC%8F%E8%AA%AA%E6%98%8E%28V1.32%E7%89%88%29.pdf?t=202312221705) | T30 格式含產業別／證券別相關欄位，官方規格也有產業 code 與 security code 表 | 可能補 TPEx OTC 歷史 membership、security/status | TPEx 資料購買頁列上櫃股票基本資料為付費資料；本輪沒有購買或 raw delivery custody，不可作歷史 coverage 宣稱 |
| 免費授權證據 | [政府資料開放授權條款第 1 版](https://data.gov.tw/license)、[TWSE OpenAPI Swagger](https://openapi.twse.com.tw/v1/swagger.json)、[TPEx OpenAPI Swagger](https://www.tpex.org.tw/openapi/swagger.json) | 可保存 dataset metadata、resource、Swagger path、license 原始文件與 hash | 支持 t187／data.gov machine scope 的技術來源身份 | machine `formal_acceptance_granted` 不是法律意見；ISIN 查詢頁的再散布範圍仍需獨立確認 |

### 2.1 欄位真實性矩陣

| reader 需要的欄位 | 官方來源真正提供的資料 | 建議保存方式 | 缺口／安全規則 |
|---|---|---|---|
| `symbol`、`sector_id` | t187 L/O 的公司代號與產業代碼；TWSE 是 `公司代號`／`產業別`，TPEx 是 `SecuritiesCompanyCode`／`SecuritiesIndustryCode` | 保存原始 JSON bytes、解析後 canonical rows hash、source hash | 只作當次 observation；不得由股票代號前綴推回產業或市場。TWSE 已說明自 2023-02-13 起新編碼去除產業／市場原則，見[股票代碼說明](https://www.twse.com.tw/zh/products/code/stock-code.html) |
| `classification_version`、code → name | TWSE／TPEx static format、分類修正公告／對照表 | 版本化保存官方文件 bytes、source URL、format version、官方 effective date、`effective_date_basis`／結構化 evidence、下載完成時間、hash；PDF runtime 先核對封面 current revision 再核對該版實施紀錄 | TWSE 與 TPEx 的同一 numeric code 可能有不同官方名稱；不能用一張無市場維度的手寫 map；未知 current PDF 只能 research parse，不能以 config backdate 解鎖 |
| `security_type_by_symbol` | ISIN all-securities current page 有 `Type of security`；listed-equities page 有官方 `Stocks` section、market、CFI 等同列證據；t187 L/O 沒有 | 保存 raw HTML／JSON、response metadata、actual completion time、hash，以及每列的 section／explicit type／CFI evidence。型別 adapter 可採「explicit allowed type」或「`Stocks` section + 通過白名單的 CFI／market tuple」兩條明確規則，轉成內部 common-equity token | 缺一列、section/CFI 組合不一致、type 是 ETF／權證／TDR／特別股／外國證券／管理股票，或完全沒有可重驗 type evidence，都應 fail closed；不從 t187 的「公司基本資料」推論普通股。CFI 代碼本身不應未經定義就單獨推論型別 |
| `source_hash`、raw custody | 現有 producer 可保存 response bytes 與 SHA-256；formal archive 也會 readback raw；current v3 reader 對 TWSE composite 會逐一重驗四個 classification raw component | 來源原始 bytes create-only；identity 的 `source_hash` 對應可讀 `taxonomy_source.json` bytes；composite 的 primary base HTTP metadata、三個 component HTTP metadata、lineage hash 與 derived completion 分開保存 | 現行 taxonomy source exact schema 仍沒有獨立 `security_source_hash`／raw path 欄位；若未來 acceptance 要求 security raw 也由 schema 宣告並由 reader 逐一綁定，需新增 contract，不能偷偷加入未知欄位 |
| `available_at` | 本機完成讀取 response 的 aware timestamp | 每一 source response 以完成時間入 registry；HTTP `Date`、`Last-Modified` 只當 metadata | 必須 `available_at <= decision_at`，且 live capture 早於台北 08:30；商品頁的 22:00／23:30 是生產規格，不是本次檔案可得時間 |
| `effective_from` | static taxonomy 有官方公告／格式生效日；t187 current capture 只有 observation date | static source 用官方 effective date，並保存 `effective_date_basis`／`effective_date_evidence`；daily membership 用 capture natural date 的 first-seen policy | 不可把 current snapshot 向前套到舊日期，不可把 HTTP／頁面更新日當 classification effective date；月份精度的實施紀錄在該月內保持 unknown，至少到次月 1 日才可作 no-early-use 判定 |
| `universe_hash`、denominator | daily-price producer 的 `universe_identity.json` 與 `scores_bp`；taxonomy 必須覆蓋相同 symbols | 先驗證 denominator identity，再以相同 hash／sorted symbols 產 taxonomy identity | 沒有 scores 的真實 identity 不能重建 hash；taxonomy symbols 少一列或跨 market 混列就不可用 |

TWSE 的 [FIX/FAST 資訊傳輸手冊](https://www.twse.com.tw/downloads/en/products/FIXFAST_manual-Eng.pdf) 也把「產業別」與「證券別」列為不同欄位，並說明產業碼可涵蓋具產業特性的普通股／部分特別股，而 ETF、權證、TDR、外國股票等非同一類商品另有處理。這支持兩個安全結論：sector code 不能單獨證明 common stock；ISIN 的 `Stocks` section／CFI context 需要作為獨立型別 evidence 保存與重驗。

### 2.2 為何必須 per-market taxonomy

本次查閱的官方格式表已顯示 TWSE 與 TPEx 同一 code 的顯示名稱不一定相同，例如：

- code `17`：TWSE 格式是「金融保險」，TPEx 格式是「金融業」；
- code `22`：TWSE 格式是「生技醫療業」，TPEx 格式是「生技醫療」；
- code `31`：TWSE 格式是「其他電子」，TPEx 格式是「其他電子業」。

現行 reader v2 的 `mapping` 是單一 `dict[code, name]`，沒有 `market_scope → mapping` 維度。把兩市場 rows 合在一個 identity 會產生不可證明的碰撞；把名稱自行正規化成第三種文字也不再是官方 crosswalk。

更重要的是，**分市場 sidecar 也不能直接沿用 parent 全市場的 `universe_hash`**。現行 reader 會要求 `universe_identity.symbols == rows.symbols`，並要求 clock、manifest、source registry 的 universe hash 互相一致；全 L/O parent identity 若有 1,984 個 symbols，單一 TWSE sidecar 只放其中 1,094 列就一定被拒絕。不能為了繞過這個檢查而改寫 frozen parent identity。

因此有兩個具體選項：

**選項 A（推薦，保留 parent identity 的最小語意變更）**：維持現有全 L/O sidecar、全市場 scored `universe_identity`、clock、handoff 與 source registry 原樣；新增 `pit-industry-taxonomy-identity.v3`／對應 source contract，使 taxonomy identity 的 `mapping_by_market` 至少包含 `twse_listed` 與 `tpex_otc`，每個 market 另有 classification version/source lineage，`security_type_by_symbol` 仍覆蓋全 L/O symbols。v3 reader 以 row 的 `market_scope` 查對應 mapping，並要求 taxonomy symbols 與 parent 全 rows 完全相同，這樣不用衍生第二個 universe hash，也不會改 frozen parent clock。這是現有 daily handoff 最少的資料拓撲改動，但需要一次 reader／schema upgrade。

**選項 B（短期維持 v2 的代價方案）**：保留 parent full identity／clock 不變，另外由已驗證 parent artifact **衍生**每市場 projection：按 parent rows 的 market scope 取 sorted subset，從 parent `universe_hash_symbols`／`scores_bp` 取同索引分數，依現行 `manual-rule-only-universe.v1` hash 公式計算新的 market-subset `universe_hash`；另產生 universe identity、market-scoped clock、source registry projection，並在其中保存 parent identity hash、parent clock hash、subset membership hash 與 derivation record。subset sidecar 的 rows、manifest、sources、clock 必須全部使用這個新 hash；parent full identity 只作 immutable parent evidence，不能被覆寫。這可讓 v2 reader 的集合檢查有機會通過，但需要處理 derived clock loader、source registry hash 與 handoff split，工作量與誤接線風險都高於選項 A。

所以「每市場一份」本身不是解法；若沒有選項 A 的 market-scoped schema，或選項 B 的完整 subset identity／clock／source projection，就不應發佈分市場 sidecar。不能在 v2 中塞 composite key、把全市場 hash 直接掛到 subset rows，或增加 reader 未定義的欄位。

## 3. 現有 repository 接點與缺口

| 現有位置 | 目前行為 | 對下一個 publisher increment 的意義 |
|---|---|---|
| `data_module/prospective_official_pit_source.py:55-83` | 已定義 TWSE L、TPEx O、TPEx R 的 source id、endpoint、symbol／sector／publication fields | 可直接重用 L/O membership adapter；R 仍應保持獨立 scope，不在本 increment 靜默併入 |
| `data_module/formal_daily_input_producer.py:2011-2159` | `_produce_pit_candidate` 在 preopen fetch L/O raw bytes，保存 HTTP metadata，建立 machine candidate | 這是每日 membership raw capture 的既有入口；taxonomy fetch 必須共用同一 observed/cutoff 與 custody boundary，不應另開盤後 refetch |
| `data_module/formal_daily_input_producer.py:2162-2224` | `capture_pit_candidate_before_cutoff` 是唯一 live capture；台北 08:30 後禁止新抓取 | security type page 與 static source 的當日 capture 若要給當日 PIT credit，也必須完成於同一 cutoff 前 |
| `data_module/formal_daily_input_producer.py:6792-6820` | `_fetch_official_source` 有 bounded GET、final URL、HTTP 200、非空 body、`captured_at` 完成時間 | 可作 HTTP custody pattern；ISIN HTML 不能直接當 JSON，需新 parser／content-type policy，且保留 8 MB bounded-read 類似防線 |
| `data_module/formal_daily_input_producer.py:2542-2724` | `_archive_pit_candidate` create-only 保存 publication、receipt、operational 與 publication 參照的 raw inputs，readback hash | 可擴展為同 archive 下的 taxonomy raw files；不得讓同日 retry 覆寫不同來源 bytes |
| `scripts/scheduled/run_pit_sector_membership_preopen_capture.py:262-283` | 先 reuse 當日 archive，缺件才進唯一 live capture，再 refresh PIT denominator | 最小 wiring 應在 denominator 驗證完成後呼叫獨立 taxonomy publisher；已存在但 invalid 的 archive 仍 fail closed，不可用新抓取掩蓋 |
| `data_module/pit_sector_membership_machine.py:140-340` | 將 L/O raw JSON 建成 machine publication；目前 `candidate_only=true`、不含 taxonomy | 保持 machine membership producer 單一責任；可由旁邊的 taxonomy publisher 消費其 raw／rows，不把分類語意硬塞進 unrelated machine schema |
| `scripts/scheduled/run_formal_pit_sidecar_postcutoff.py:250-288` | 盤後只讀 preopen archive，建立 history handoff，再呼叫 `publish_formal_pit_sector_sidecar` | 這裡只能讀已 custody 的 taxonomy bundle；taxonomy 缺件時寫 blocked receipt，不得盤後重新查 ISIN／t187 |
| `data_module/formal_pit_sector_publisher.py:49-160` | 驗證 handoff／denominator 後建 sidecar，再做 assembler readback | 應加入 taxonomy bundle lookup／reader gate；目前沒有 taxonomy input，不能把 `_build_sidecar` 產出的 `formal_consumer_compatible=true` 視為 industry-filter accepted |
| `data_module/formal_pit_sector_publisher.py:561-616` | `_build_sidecar` 只有 manifest、source registry、rows、universe／rows hash，沒有 taxonomy identity/source | 這是正式 wiring 的主要 extension point；推薦保留 full sidecar／parent hash，改由 market-scoped taxonomy schema 提供兩市場 mapping；若堅持 v2，必須另做完整 subset identity／clock／source projection，不能只切 rows |
| `data_module/pit_sector_membership_reader.py:69-105,1366-1690` | exact taxonomy identity/source、available/effective、mapping、安全 security type、raw hash 都會重驗 | publisher 的輸出應以 reader 的 verified result 作為 acceptance gate；不可只以 writer 自己重算的 hash 宣稱通過 |
| `data_module/formal_rule_source_producer.py:1625-1813` | 產生 daily price rule source bundle、clock、`universe_identity.json`、`scores_bp`、universe hash | 只提供獨立 denominator／scores／clock evidence；不要把產業分類、ISIN或 static taxonomy責任混入此 producer |

## 4. 建議的最小每日 source publisher

### 4.1 Artifact topology

為避開 reader v2 的跨市場 mapping collision，先固定兩種 topology 的取捨；推薦先採保留 parent full identity 的選項 A，只有在必須維持 v2 相容時才採選項 B：

**推薦的選項 A（full sidecar + v3）**：

```text
pit_sector_membership_formal/YYYY-MM-DD/
  pit_sector_membership/
    sidecar.json
  clock/
    manifest.json                 # parent full-L/O clock，immutable
  metadata/
    universe_identity.json        # parent full scored identity，immutable
    universe_symbols.json
    taxonomy_identity.json        # market-scoped taxonomy schema v3
    taxonomy_source.json          # market-scoped source schema v2
    raw_manifest.json
  raw/
    t187ap03_L.raw.json
    t187ap03_O.raw.json
    twse_listed_industry_definition_base_definition.pdf
    twse_listed_industry_definition_change_notice.html
    twse_listed_industry_definition_revision_history.pdf
    twse_listed_industry_definition_current_regulation.html
    tpex_industry_definition.pdf
    twse_isin_all_securities.html
    tpex_isin_all_securities.html
```

這個路徑是刻意把 `sidecar.json` 放在 `YYYY-MM-DD/pit_sector_membership/`：現行 reader 的 auto lookup `artifact.parent.parent / metadata` 會落在 `YYYY-MM-DD/metadata`，而 clock 的 auto lookup 會落在 `YYYY-MM-DD/clock`，正好保留原 full-universe parent evidence。v3 reader 應要求 identity symbols 等於 full sidecar rows，並依 rows 的 `market_scope` 尋找 `mapping_by_market[market_scope][sector_id]`；不需要另造 subset hash。

**選項 B（v2 compatibility projection）** 的 topology 才是每市場一份：

```text
pit_sector_membership_formal/YYYY-MM-DD/
  twse_listed/
    pit_sector_membership/sidecar.json
    clock/manifest.json           # derived subset clock，非 parent clock 的覆寫
    metadata/
      universe_identity.json      # derived subset scored identity
      universe_symbols.json
      taxonomy_identity.json      # v2，symbols == TWSE rows
      taxonomy_source.json
      raw_manifest.json
    raw/...
  tpex_otc/
    pit_sector_membership/sidecar.json
    clock/manifest.json           # derived subset clock，非 parent clock 的覆寫
    metadata/
      universe_identity.json      # derived subset scored identity
      universe_symbols.json
      taxonomy_identity.json      # v2，symbols == TPEx rows
      taxonomy_source.json
      raw_manifest.json
    raw/...
```

選項 B 的 parent full identity／clock 必須另以 immutable path/reference 保存，不能被 subset 檔案覆寫；每個 subset 的 `universe_hash`、clock hash、source registry hash 都要重新計算並互相綁定。這不是把 full hash 複製到 subset rows，而是由 parent scores 做可追溯 projection。`raw_manifest.json` 是 publisher 的 custody／source-component manifest，不應把 reader v1 exact taxonomy source schema 擴充成未定義欄位。

### 4.2 Preopen capture 順序

1. 由既有 `run_pit_sector_membership_preopen_capture.run_capture` reuse 或唯一 live capture L/O t187 raw response；保留每一 response 的 requested/final URL、HTTP status、content type、`http_date`、`http_last_modified`、`captured_at`、raw hash。
2. 同一台北 08:30 cutoff 前，執行一個**獨立、bounded 的 security source adapter**。第一候選是 `e_single_main.jsp` 的官方 all-securities HTML；adapter 要先證明頁面／分頁能完整且可重複取得，再保存 raw bytes。若頁面超過 bounded size、分頁不完整、URL／status 改變或出現 duplicate symbol，當日只輸出 candidate／diagnostic。
3. 以已驗證的 daily-price denominator 作 exact join：選項 A 使 `taxonomy symbols == full rows == full denominator symbols`；選項 B 才使 `taxonomy symbols == market-subset rows == derived subset denominator symbols`。選項 B 必須從 parent identity 的 `scores_bp` 產出 subset identity／clock／source projection，並保存 parent hash reference；不得用 ISIN current page 的全體列當 denominator，也不得以 t187 symbol union 取代 daily-price identity。
4. 使用已保存的官方 static definition bytes 產生該市場當日適用的 code → name map。TWSE B12.12 target 使用四元件 composite：B12.00 base PDF、2023 change notice、B12.13 B12.00–B12.12 bounded history 與 current-regulation cross-check；四份 raw／hash／completion／lineage 都要 custody，且 B12.13 Appendix 3 不直接作 target mapping。分類檔可跨日重用，但 identity 的 `available_at` 必須早於當次 decision；`effective_from` 必須是分類／附錄的官方適用日，不得取 HTTP `Date`、`Last-Modified`、頁面更新日或下載完成時間。PDF source config 必須同時提供 `effective_date_basis` 與結構化 `effective_date_evidence`；未知 current revision 一律 runtime fail closed，若 as-of 日期早於 static 文件 effective date，必須選已核驗較舊版本或回 missing。只做 mapping shape 研究時，須明確標示 research-only parser。
5. security adapter 逐列保存 section、explicit type（若有）、market、CFI、source row context；對普通股票可用「官方 `Stocks` section + 通過白名單的 CFI／market tuple」判定 common-equity，但這條轉換規則本身要有固定 parser、source hash 與 negative tests，不能只看 CFI 字串。只有每一 symbol 的 type evidence、每一 row 的 sector mapping、raw custody／hash／時間／所選 full 或 subset universe 都通過，才建立 taxonomy identity/source；缺一列就保持 candidate，不以 `common_stock` default 補齊。

### 4.3 Identity／source 的最小內容

**選項 A 的 proposed v3** 不應假裝是現行 v2；它要保留 full parent 的 `universe_hash`／symbols／clock binding，並新增 market-scoped 欄位，至少包括：

```text
mapping_by_market:
  twse_listed: {"01": "水泥工業", ...}
  tpex_otc:    {"02": "食品工業", ...}
classification_version_by_market
classification_source_by_market   # id/version/hash/effective_from
security_type_by_symbol            # full L/O symbols
```

v3 仍需保留 `source_id`、`source_version`、`source_hash`、`source_path`、`available_at`、`universe_hash`、`symbols`、`security_source_id/version`、`mapping_hash` 等 lineage；`taxonomy_source` 也要有對應的 market-scoped source schema。v3 reader 的核心驗證是：

- full identity symbols 與 full sidecar rows 完全相同；
- 每一 row 用自己的 `market_scope` 選 mapping、classification version、effective date；
- taxonomy source bytes 的 hash、parent full universe hash、clock hash、source registry 全部一致；
- `security_type_by_symbol` 覆蓋 full L/O symbols，並由同一 security evidence contract 驗證。

這是推薦的 schema delta；在 v3 實作完成前，下面這個 v2 shape 只適用於選項 B 的 subset projection，不能放到 full sidecar 以外的 rows：

```json
{
  "schema_version": "pit-industry-taxonomy-identity.v2",
  "classification_version": "<market-scoped-official-effective-version>",
  "source_id": "<publisher-taxonomy-source-id>",
  "source_version": "<publisher-source-version>",
  "source_hash": "sha256:<taxonomy_source_json_bytes_hash>",
  "source_path": "taxonomy_source.json",
  "available_at": "<aware HTTP/custody completion timestamp>",
  "effective_from": "<official classification effective date>",
  "classification_source_id": "<official TWSE or TPEx definition source>",
  "classification_source_version": "<official format/notice version>",
  "security_source_id": "<official security-type source>",
  "security_source_version": "<captured page/source version>",
  "universe_hash": "sha256:<market-subset-denominator-hash>",
  "symbols": ["<sorted exact market-subset symbols>"],
  "mapping": {"01": "<official name>"},
  "security_type_by_symbol": {"<symbol>": "common_stock"},
  "mapping_hash": "sha256:<identity-without-mapping_hash>"
}
```

`taxonomy_source.json` 要完全符合現行 reader v1 exact fields，並由 publisher 從實際保存的 official static bytes + security raw bytes 確定性產生；不可手動輸入一份 mapping 再宣稱 official certification。`source_hash` 是 reader 可讀 source file 的 bytes hash；分類 PDF、ISIN HTML 各自的 raw hash 應另存 `raw_manifest.json`，由 publisher 在發佈前驗證。

現行 reader v2 沒有 `security_source_hash`／`security_source_path`。所以有兩種清楚的處理方式：

- **最小技術 candidate**：把四個 TWSE classification component 與 security raw component 的 hash、URL、completion 放進 publisher 的 `raw_manifest.json`，而 reader 驗證 combined `taxonomy_source.json`。這可以先建立真實日 source custody，但 lineage 對各 security raw 的獨立重驗仍是 publisher-only。
- **正式強化前置條件**：若正式 acceptance 政策要求 reader 自己逐一重驗 classification raw 與 security raw，先新增 reader/schema 支援（例如 v3 identity/source contract）；不要在 v1 exact source 裡偷偷增加欄位，因為現行 reader 會以欄位集合不相等拒絕。

### 4.4 盤後 formal wiring

`run_formal_pit_sidecar_postcutoff.py` 只可載入 preopen 已保存的 taxonomy bundle，然後由 `formal_pit_sector_publisher`：

1. 讀取 handoff、denominator、parent full clock／universe、market-scoped taxonomy identity/source 與 raw custody；若採選項 B，則讀取完整 subset identity／clock／source projection 及 parent references。
2. 先把 rows 補上或驗證 `market_scope`、`classification_version`、`security_type`；補值只能來自同一份已 hash-bound taxonomy identity，不可來自 `companies.csv`。選項 A 的 rows 仍保留 full L/O，選項 B 才能只放 subset rows。
3. 以對應版本 reader 重驗 sidecar、universe、source registry、taxonomy 及時間邊界；失敗則保留 blocked receipt／candidate 狀態。
4. 只有 reader 的 `industry_filter_usable=true` 且 assembler readback rows／hash 一致時，才把正常日 artifact 標成可供 industry filter 消費；`promotion_eligible`、正式 OOS、broker action 仍維持 false。

## 5. 驗收與 fail-closed gates

| Gate | 正常日要成立的條件 | 任何一項失敗時 |
|---|---|---|
| G0 raw custody | 每一官方 response 是原始 bytes；request/final URL、status、content type、completion、actual SHA-256 都保存；archive readback 相同 | candidate／blocked，不可重抓後覆蓋 |
| G1 denominator | `universe_identity.json` schema 正確、`scores_bp` 存在且可重建 hash；taxonomy symbols 與 row symbols 完全相同且 sorted unique | unavailable；不以 t187 row count 當分母 |
| G2 static taxonomy | 每個 row sector code 有同市場官方 mapping；classification version、source bytes hash、current revision、`effective_date_basis`／applicability evidence 與 effective date 可重驗；未知 current PDF 僅限 research parse | `taxonomy_verified=false`；不以 current mapping 補歷史、不以 HTTP／頁面更新日 backdate |
| G3 security type | 每個 symbol 有同一 capture 的官方 explicit type，或通過固定 parser 的 `Stocks` section + CFI／market tuple；只接受 reader 的 common-equity token；ETF、ETN、權證、TDR、特別股、外國證券、管理股票、未知 context 全部阻擋 | partial denominator／industry filter unavailable |
| G4 PIT timing | t187、security source、必要 custody 在台北 08:30 前完成；`available_at <= decision_at`；static `effective_from <= as_of_date` | 當日不給 credit；盤後不准 refetch |
| G5 market isolation | 推薦是 full sidecar + v3 `mapping_by_market`，且每 row 依 market 選官方 map；或選項 B 完整產生 subset universe／clock／source projection；兩者都不得發生同 code 不同官方名稱碰撞 | 不能把 full hash 直接掛到 subset rows；保持 blocked，或完成 schema／projection upgrade |
| G6 consumer revalidation | reader canonical hash、source raw hash、universe、taxonomy identity/source、rows interval 均 verified；assembler readback count/hash 一致 | 寫 blocked receipt，不宣告 formal consumer compatible |

具體 negative cases 包括：ISIN source 少一個 denominator symbol、同 symbol 多筆 conflicting market/type、頁面只證明 current snapshot 但 completion 晚於 cutoff、static 文件 effective date 晚於 as-of、security type 是 `ETF` 或 `Listing Warrants`、TWSE/TPEx code 17 名稱碰撞、taxonomy source hash 只存在 identity 沒有檔案，以及任何試圖由 2026-08-25 或 `companies.csv` 補出缺件的行為。

## 6. 目前缺少的實作與優先順序

本輪已完成 bounded TWSE／TPEx definition adapter、TWSE B12.12 四元件 composite applicability contract、security evidence adapter、daily producer、reader／publisher／industry caller wiring、preopen／postcutoff timing seam 與 negative QA。2026-09-16 已在隔離 research root 以實際 parent producer 產生並 readback 一份 1,932-symbol score-bearing parent；composite definition component probe 已實際解析 TWSE 33／TPEx 31 並完成 component revalidation，但同日 company exact join 仍因 `5371` 缺件 fail closed，因此尚未產生 full taxonomy bundle 或取得自然時序 credit。本輪不回填 frozen parent，也不把 `5371` 缺件轉成 drop。

2026-09-16 chain probe 的完整收據為：

`C:\Projects\PythonProjects\technical_analysis\output\research_qa\pit_taxonomy\2026-09-16\score-bearing-parent-probe-20260916-r1\taxonomy_chain_research_receipt_20260916.json`

實際研究 config 為：

`C:\Projects\PythonProjects\technical_analysis\output\research_qa\pit_taxonomy\2026-09-16\score-bearing-parent-probe-20260916-r1\pit_taxonomy_research_config_20260916.json`

### P0：下一個可執行 increment

1. **已完成 engineering**：新增與 `pit_sector_membership_machine` 同責任層的 `pit taxonomy source producer`；另在 `formal_rule_source_producer` 增加僅供 research caller 的 resolved output-root preflight，正式 scheduler 仍維持原 date-scoped default。整體包含 static definition adapter、bounded ISIN security adapter、raw manifest、market-scoped taxonomy source writer、full-parent identity binding、reader-facing validation。
2. **已完成 engineering**：producer 已接到 `run_pit_sector_membership_preopen_capture.py` 的 denominator 驗證之後，共用當日 observed/cutoff；一日僅允許一份 immutable taxonomy capture。
3. **已完成 engineering**：`formal_pit_sector_publisher`／呼叫層已接 taxonomy bundle input，保留 full L/O sidecar 並使用 v3 `mapping_by_market`；缺 taxonomy 時保持 blocked，不用 rows 內手寫 `industry_category` 救援。
4. **已完成 research-shadow／實際鏈路 probe**：以 `e_single_main.jsp` 建立 security adapter，並將 bulk 完整性、同日 exact `5371` query、ISIN 使用／再散布未確認與 applicability/source config 缺件記成明確 status；2026-09-16 台北 00:32–00:50 實際產生 1,932-symbol score-bearing parent 並完成 machine readback，TWSE composite definition component probe 也完成 33／31 mapping revalidation，但完整 company exact join 因 `5371` current snapshot 缺件 blocked，未建立 taxonomy bundle。獨立 MOPS lifecycle raw 已核驗 `5371 → 3718` 事件，尚待 lifecycle／warm-up caller 接線，不改 frozen parent 或 legacy price。研究 caller 的 output-root preflight 也以 mismatch negative test 驗證會在 reads／writes 前 fail closed；artifact 仍只標 candidate／diagnostic，industry filter 回 unavailable/degraded。

### P1：正式 source contract／品質補強

1. 決定 security source 的正式授權範圍；若 ISIN page 不適用，購買並 custody T97/T30 或尋找有明確開放授權、明確 per-security type 的官方替代來源。
2. 若需要 reader 自己驗證分類與 security raw component 的獨立 hash，升級 taxonomy identity/source schema；保留 v2 reader 以讀取既有格式，並建立新 contract 的 negative tests。
3. 將 TPEx emerging R 做成獨立 denominator、independent source registry、static map、security type 與 sidecar；完成前維持 `tpex_emerging` missing，不寫成全市場。
4. 若未來要支援歷史 membership，才研究 T97/T30 的交付時間、format version、公告 effective date、退市／停牌 interval 與 corporate-action symbol crosswalk；不可由本日 source 向前推導。

### 明確不做的事

- 不把 `companies.csv` 改名成 historical PIT source。
- 不用目前 ISIN page、目前 mapping 或目前公司清單回填 2026-08-25 以前的日期。
- 不把 fixture、自己寫入的 mapping hash 或重序列化 JSON digest 當成官方 certification。
- 不啟動 scheduler、pipeline、UI、formal OOS、production recommendation 或 broker action。
- 不因為 source page 公開可查，就自行做法律授權結論。

## 7. 交付判定

本方案完成的是 source design 與現有 wiring audit，不是 acceptance。下一個 implementation increment 的可交付判定應是：

1. 至少一個新的自然日由真實 preopen L/O raw source + independent scored denominator + static official taxonomy bytes + security source capture 產出，而不是 handwritten fixture。
2. 兩個市場各自能被 reader 定位；每個 identity/source 的 exact fields、bytes hash、available/effective、universe、mapping、security type 都可 readback。
3. 若 security source 的授權或 bulk completeness 尚未證實，artifact 明確是 candidate／diagnostic，並帶具體 blocker；不能將技術完成誇大成 formal accepted。
4. 第一個成功日只給該次 capture 的 prospective credit；不重寫既有 2026-08-25 artifact，也不宣稱 2014–2026 歷史 coverage。
