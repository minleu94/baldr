# PIT 產業歸屬來源驗收與接線 Discovery

> 日期：2026-09-15
> 範圍：市場 → 產業 → 個股的 point-in-time（PIT）產業歸屬來源、授權、時間語意、歷史可用性，以及既有 Industry Strength / Recommendation / Decision Desk 接線。
> 性質：獨立來源驗收調查（discovery baseline）；本文件所記錄的調查不修改 production code、UI、shared roadmap、Manual 或既有資料，也不啟動正式 pipeline / scheduler。

> 閱讀界線：本文件保留 discovery 階段的 artifact／wiring baseline；後續 bounded reader 與 caller acceptance 結果，見 [PIT_INDUSTRY_CALLER_ACCEPTANCE_QA_2026_09_15.md](PIT_INDUSTRY_CALLER_ACCEPTANCE_QA_2026_09_15.md)。

## 結論先行

目前只有「官方來源的 prospective / current-natural-day machine evidence」具備程式驗證與可重驗 artifact；本輪沒有把任何 candidate 宣告為正式 accepted，不能宣稱已具備 2014–2026 歷史 PIT 產業歸屬。

1. 程式上已支援、且已有可重驗 raw 的 prospective 路徑是：
   - TWSE t187ap03_L（上市）與 TPEx t187ap03_O（上櫃）的官方 OpenAPI JSON；
   - data.gov.tw dataset 18419、25036 指向的官方 CSV，作為獨立 expected-universe 分母；
   - raw response、HTTP completion timestamp、source hash、canonical rows hash、schema、license evidence 與 universe hash 一起保存。
2. TPEx 興櫃 t187ap03_R 已在官方 source definition 中存在，但目前 machine producer 與 prospective denominator 只要求 TWSE listed + TPEx OTC，尚未形成可接受的 emerging 來源契約。
3. t187ap03 的官方資料列有「出表日期 / Date」，沒有可由 payload 直接證明的官方發布時間。既有 machine 將該日期組成午夜 publication_at；這只能是 date-only label，不能冒充官方發布時刻。真正可綁定的可得時間是 HTTP response 完成的 captured_at / available_at。
4. machine publication 的 effective_from 是實際抓取自然日，effective_to 為空，政策是 official_source_first_observed_only；這是新觀測的 candidate，不是 current registry 的歷史回填。
5. 既有正式 publisher 要求台北時間 08:30 cutoff、獨立分母、完整交易日 coverage、raw archive custody、license scope 與 assembler readback。在本輪查閱的 repository output path，production-like output 只有 blocked receipts；依 `TWStockConfig` 對正式 data root 的只讀搜尋，另找到一份 2026-08-25 的 prospective manifest，但沒有同名的 `formal_daily_publications` 正式 sidecar。這是本輪搜尋範圍的觀察，不是對所有外部或其他 production location 的全域否定；可重驗路徑與時間見「本地 artifact 觀察」。測試 fixture 可通過的 formal publisher 不等於已接受外部歷史資料。
6. IndustryStrengthService 仍以 meta_data/companies.csv + explicit mapping 做 current research，固定回報 historical_pit_eligible=False；RecommendationService 在有 decision cutoff 且指定產業時，會 fail closed 為 industry_membership_pit_unavailable。這是正確的安全邊界，但尚未接上 accepted PIT membership read model。
7. TWSE T97、TWSE TWT58U、TPEx T30 是有機會補歷史的官方付費候選來源；現況沒有已購買、授權決策、原始交付檔、交付時間、格式版本與 hash lineage，因此仍是 candidate，不能用來宣稱歷史 coverage。

因此本增量的決策是：

- prospective：程式支援可直接進入 read-only reader / diagnostics；本輪 candidate 仍在 acceptance queue，只有被 read model 明確標成 accepted 的日期 / market 才能進 prospective consumer scope；
- historical：blocked / unavailable；
- current companies.csv：只能 current research，禁止轉名為 historical PIT；
- industry recommendation / Decision Desk：在 accepted PIT source 未接線前維持缺件、警告與負證據，不得 silent fallback。

## 調查方法與證據界線

本調查以以下內容交叉比對：

- repository agent SSOT、architecture、roadmap、Manual 與 [ULTIMATE_NEXT_INCREMENT_AUDIT（2026-09-15 歷史）](../09_archive/ULTIMATE_NEXT_INCREMENT_AUDIT_2026_09_15.md)；
- graphify 對 source producer、machine publisher、formal publisher、Industry Strength 與 Recommendation 的 read-only 關係查詢；
- data_module/、app_module/、ml_module/ 與 tests 的靜態閱讀；
- TWSE、TPEx、MOPS、data.gov.tw 官方頁面與格式 / 商品說明；
- repository 內 output/formal_daily_publications/ 和 output/pit_registry_probe_20260908/ 的只讀 artifact inspection；
- 依 `data_module/config.py::TWStockConfig` 解析 `D:\Min\Python\Project\FA_Data`（data root）與其 `output` 的只讀搜尋，並檢查適用的 latest PIT / shadow manifest。搜尋只涵蓋上述 data root、repository output 與明確列出的子樹，不延伸到其他磁碟、外部主機或未列出的 production location。

本文件不把以下內容當作歷史證據：

- 現行 companies.csv 的 date / download_time；
- 今天重新抓到的 current snapshot；
- webpage 顯示的 current industry dropdown；
- 第三方網站、第三方整理、推導出的 industry mapping；
- scrape time、HTTP Date 或 Last-Modified 被誤寫成官方 publication time；
- 沒有 owner license decision 的付費商品說明；
- 測試 fixture 或 synthetic archive 被誤報成外部來源 custody。

## 官方來源矩陣

| 來源 | 官方位置與 raw 形狀 | 可見欄位 / 市場 | 官方時間資訊 | 授權與歷史判定 |
|---|---|---|---|---|
| TWSE t187ap03_L | [TWSE OpenAPI JSON](https://openapi.twse.com.tw/v1/opendata/t187ap03_L)；[MOPS CSV resource](https://mopsfin.twse.com.tw/opendata/t187ap03_L.csv)；[data.gov dataset 18419](https://data.gov.tw/dataset/18419) | JSON：公司代號、產業別、出表日期；market=twse_listed | payload 只有出表日期；data.gov 頁面標示更新頻率每月 | data.gov metadata 標示政府資料開放授權條款第 1 版；可作 prospective row custody / 分母比對；沒有歷史快照。 |
| TPEx t187ap03_O | [TPEx OpenAPI JSON](https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O)；[MOPS CSV resource](https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv)；[data.gov dataset 25036](https://data.gov.tw/dataset/25036) | JSON：SecuritiesCompanyCode、SecuritiesIndustryCode、Date；CSV 對應 公司代號、產業別、出表日期；market=tpex_otc | payload 只有 Date；data.gov 頁面標示每日更新 | 政府資料開放授權條款第 1 版；可作 prospective row custody / 獨立分母；沒有歷史快照。 |
| TPEx t187ap03_R | [TPEx emerging OpenAPI JSON](https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R)；[MOPS CSV resource](https://mopsfin.twse.com.tw/opendata/t187ap03_R.csv)；[data.gov dataset 28568](https://data.gov.tw/dataset/28568) | 同 O 的英文字段；market=tpex_emerging | data.gov 頁面標示每日更新 | 官方 source definition 已列出，但 machine / denominator 尚未納入；先視為 contract gap，不能把 emerging 混進 OTC 或宣稱全市場。 |
| TWSE TWT58U | [證券及產業別對照表](https://eshop.twse.com.tw/zh/product/detail/000000006e0bbe8d016f18269c59032c) | 股票代號 \| 產業別代碼；每日檔案 TWT58U；TEXT / CSV | 每交易日 22:00；資料起始日 2019-12-23 | 官方付費商品；內部 NT$500/月、外部 NT$1,000/月，並受網路訂購條款約束；可作 2019-12-23 之後歷史候選，尚無本專案購買與 raw custody。 |
| TWSE T97 | [漲跌幅度表檔](https://eshop.twse.com.tw/zh/product/detail/75ce5fd1ad574df49ad9ff82209ca837) | 股票代號、上次交易日、交易方式、處置 / 注意註記、產業別代碼、證券別代碼等；每日 T97；TEXT / CSV | 每交易日 23:30；次一交易日參考；資料起始日 2014-01-06 | 官方付費商品；內部 NT$1,500/月、外部 NT$3,000/月；單筆歷史訂購最多五年；最接近 TWSE 歷史 membership + security status 的候選，但尚未取得授權、交付檔與版本化 custody。 |
| TPEx T30 | [上櫃股票漲跌幅度表](https://eshop.tpex.org.tw/zh/product/detail/BCDDCDFD315841EC011ED99B91DD528E)；[TPEx 收市後格式說明](https://www.tpex.org.tw/storage/regular_system/%E6%96%B0%E7%89%88%E6%94%B6%E5%B8%82%E5%BE%8C%E4%BA%A4%E6%98%93%E8%B3%87%E8%A8%8A%E6%A0%BC%E5%BC%8F%E8%AA%AA%E6%98%8E%28V1.32%E7%89%88%29.pdf?t=202312221705) | T30 上櫃股票漲跌幅度表，TXT；格式說明含產業別代碼表與版本變更 | 每日 07:50、21:30；資料起始日 2008-11-01；可訂購上個月以前歷史 | 官方付費商品；內部 / 外部使用均受會員申購條款約束；可作 TPEx OTC 歷史候選，但 exact raw record、format version、delivery timestamp 與 license decision 尚缺。 |
| data.gov 授權文件 | [政府資料開放授權條款第 1 版](https://data.gov.tw/license)；TWSE [Swagger](https://openapi.twse.com.tw/v1/swagger.json)；TPEx [Swagger](https://www.tpex.org.tw/openapi/swagger.json) | 用來驗證 dataset、resource、endpoint、schema path 與 attribution scope | license document 自身需保存 raw bytes / hash；不把 webpage keyword 當判定 | 現有 pit_prospective_denominator.py 會固定 license document fingerprint；程式的 formal_acceptance_granted 是 machine policy，不等於法律意見。 |

### 本輪查閱時間與 evidence 類型

- 官方 webpage / 商品說明的欄位、更新頻率、價格與格式描述：2026-09-15 本輪頁面查閱（頁面查閱本身未持久化 HTTP raw timestamp）；這些是 page description，不等於本輪重新下載的 raw bytes。
- 可重驗的 repository fetched raw：`output/formal_daily_publications/pit_denominator/2026-09-08-run8/` 下的 `tpex_t187ap03.raw.json`、`twse_t187ap03.raw.json`、兩個 CSV、`dataset_18419.json`、`dataset_25036.json`、`government_open_data_license.html`、兩份 Swagger 與 `denominator.json`；該 run 的 license HTTP capture 是 `2026-09-07T17:01:09.464538+00:00`，`coverage_start=2026-09-08`，source publication dates 是 TPEx `2026-09-07`、TWSE `2026-09-06`。這些檔案與 hash / metadata 是 fetched raw evidence，不是 webpage 描述。
- 可重驗的 machine raw / receipt：`output/formal_daily_publications/pit_candidate_archive/2026-09-07/05cfa45cd06221a6-5c0f35d14dbd4e90/archive_manifest.json` 的 capture 是 `2026-09-07T23:45:45.470485+08:00`；最新本輪 pre-open status 另指向 `output/formal_daily_publications/pit_candidate_archive/2026-09-15/0114791e4de4d346-6d417badff58bcab/archive_manifest.json`，manifest `captured_at=2026-09-14T16:00:43.534461-07:00`、`effective_from=2026-09-15`、`row_count=1985`，仍為 `candidate_only=true`。
- 舊 probe evidence：`output/pit_registry_probe_20260908/` 的 `dataset_18419.raw`、`dataset_25036.raw`、`emerging.raw`、`license.raw`、CSV / Swagger / terms 檔案是 2026-09-08 source discovery / diagnostics probe；不得與上面的 denominator raw 或任何 accepted artifact 混稱。

下表把官方矩陣中的「描述」與「實際 fetched raw / old probe」逐列對齊；沒有 raw HTTP completion 的地方明確保留 unknown，不用商品頁時間補寫：

| 來源 | 本輪頁面描述查閱 | HTTP / raw observation | 可重驗位置與本輪判定 |
|---|---|---|---|
| TWSE t187ap03_L | 2026-09-15；只確認官方 endpoint、欄位與 data.gov 月更新描述 | repository denominator 的 source capture date 是 2026-09-08；同一 source 的 candidate machine operational `available_at=2026-09-07T15:45:45.470485+00:00`（台北 2026-09-07 23:45:45.470485），這是 response-completion / custody time，不是官方 publication time | `output/formal_daily_publications/pit_denominator/2026-09-08-run8/twse_t187ap03.raw.json`、`twse_t187ap03.csv`、`denominator.json`；可重驗 prospective raw，仍不是本輪正式 accepted artifact |
| TPEx t187ap03_O | 2026-09-15；只確認官方 endpoint、欄位與 data.gov 每日更新描述 | 同一 candidate operational capture 的 `available_at=2026-09-07T15:45:45.470485+00:00` 包含 TPEx raw custody；denominator `source_capture_dates=2026-09-08`；不把 HTTP Date / Last-Modified 當 publication time | `output/formal_daily_publications/pit_denominator/2026-09-08-run8/tpex_t187ap03.raw.json`、`tpex_t187ap03.csv`、`denominator.json`；可重驗 prospective raw，仍不是本輪正式 accepted artifact |
| TPEx t187ap03_R | 2026-09-15；只確認官方 R endpoint、dataset 28568 與每日描述 | `output/pit_registry_probe_20260908/emerging.raw` 是舊 discovery / diagnostics probe，沒有本輪 machine denominator 或 accepted sidecar 的 HTTP / custody observation | 目前只能判定 source definition / probe 存在；R 不進 L/O prospective lane |
| TWSE TWT58U / T97、TPEx T30 | 2026-09-15；只確認商品欄位、規格、時間與起始日描述 | 本輪 `D:\Min\Python\Project\FA_Data` 與 repository output 的 scoped search 沒找到已購買的對應 raw delivery / order / hash custody；沒有可填的 delivery HTTP time，不以商品頁時間代替 | 只保留官方商品頁作 future candidate description；不構成 historical artifact |
| data.gov license / Swagger | 2026-09-15；只確認官方 license / API documentation page | license raw 的 HTTP capture 是 `2026-09-07T17:01:09.464538+00:00`；Swagger / metadata bytes 與 hash 由同一 denominator run 保存 | `output/formal_daily_publications/pit_denominator/2026-09-08-run8/government_open_data_license.html`、`dataset_18419.json`、`dataset_25036.json`、`twse_swagger.json`、`tpex_swagger.json`、`denominator.json`；machine scope evidence，不是 legal opinion |

### 官方分類版本不能被 current mapping 取代

TPEx 官方格式與公告已證明產業 taxonomy 會變更：

- [TPEx 2013/2014 文化創意業代碼 32 公告](https://www.tpex.org.tw/storage/eb_data/10208/1020500085.htm)；
- [TPEx 2023-07-03 分類調整公告](https://www.tpex.org.tw/storage/eb_data/11205/1120500358.html)；
- [TPEx 收市後格式說明版本變更與產業代碼表](https://www.tpex.org.tw/storage/regular_system/%E6%96%B0%E7%89%88%E6%94%B6%E5%B8%82%E5%BE%8C%E4%BA%A4%E6%98%93%E8%B3%87%E8%A8%8A%E6%A0%BC%E5%BC%8F%E8%AA%AA%E6%98%8E%28V1.33%E7%89%88%29.pdf?t=20251127)。

2023-07-03 起，TPEx 新增綠能環保、數位雲端、運動休閒、居家生活，並調整 / 併入電子商務、貿易百貨及觀光事業名稱。這代表「產業代碼 → 顯示名稱」必須綁定 classification_version、官方文件 hash 與生效日；不能以目前中文名稱往回覆蓋歷史。

## Repository 內既有契約與實際接線

### Source producer 與 denominator

data_module/prospective_official_pit_source.py：

- 已定義 twse、tpex、emerging 三個官方 source definition；
- 只接受 caller 明確提供的官方 raw UTF-8 JSON bytes，不讀 companies.csv；
- parser 會驗證 symbol、兩碼 sector code、同一來源一致的 publication date、duplicate 與 expected universe coverage；
- source registry 會保存 source_id、dataset_id、endpoint、license、raw hash、canonical rows hash、publication date、available_at、effective_from、clock / universe hash；
- source_version 現在是 dataset_id:publication_date，尚不是獨立 taxonomy / format version；
- effective_from 早於 current capture date 會被拒絕，因此不允許歷史回填。

data_module/pit_sector_membership_machine.py：

- schema：pit-sector-membership-machine-publication.v1 / pit-sector-membership-machine-receipt.v1；
- _SOURCE_MARKETS = ("twse", "tpex")，要求同時提供上市與上櫃；
- emerging 雖在共用 official definition，但本 machine lane 尚未納入；
- effective_from 綁定 Taipei natural capture date；effective_to=None；
- publication_time_precision=date_only，且 official_publication_time_claimed=false；
- receipt / publication 明確標記 candidate_only=true、formal_consumer_compatible=false、historical_backfill_claimed=false；
- default license scope 是 declared_official_open_api_identity，允許 research shadow / diagnostics，不代表 formal/legal acceptance。

data_module/pit_prospective_denominator.py：

- 目前只接受 TWSE dataset 18419 + TPEx dataset 25036；
- 會重新驗證 JSON、data.gov CSV、dataset metadata、Swagger path、HTTP status / completion timestamp、政府 license raw document 與固定 fingerprint；
- JSON / CSV mapping 必須完全相同，但兩者 publication date 可因不同 cadence 而不同，且兩個日期都保留在線索；
- coverage_start 必須不早於最新 raw response capture date；
- companies.csv 不可作分母，archive 也不可反推分母；
- formal_acceptance_granted=true 代表程式的 government-open-data-pit-scope.v1 machine policy，legal_acceptance_inferred=false，不能取代 owner / legal decision；
- 目前是 prospective only，historical_backfill_claimed=false。

### Formal handoff 與既有 downstream consumer

data_module/formal_pit_history_handoff.py 與 data_module/formal_pit_sector_publisher.py 已形成很清楚的 gate：

- archive 必須有 raw custody、publication / receipt / operational bytes；
- expected universe 必須來自獨立分母且 hash-bound；
- 每個需要的 official trading date 都要有自然日 observation；
- available / archived timestamp 必須早於 Taipei 08:30 cutoff；
- 同一自然日多個不同 capture / content hash 會 fail closed；
- publisher 只寫 create-only sidecar，並用 data_module.portfolio_ml_dataset_assembler._spool_sector_memberships readback；
- sidecar scope 仍是 prospective_pit_sector_membership，historical_backfill_claimed=false、formal_oos_allowed=false、promotion_eligible=false、production_action_allowed=false。

data_module/portfolio_ml_dataset_assembler.py 已有可重用的 membership row contract：

- symbol、sector_id、available_at、effective_from、effective_to；
- status=accepted、source_id、license_id、source_hash；
- available_at <= training / decision time；
- effective_from <= decision_date <= effective_to（或 effective_to 為空）；
- current_companies_snapshot 來源會被拒絕為 historical PIT；
- 沒有 membership 時產生 pit_sector_membership_unavailable_at_decision，而不是把 current snapshot 填進去。

這個 assembler contract 是後續 Industry Strength / Recommendation 應共享的 read model 邊界；不應再造一套沒有 hash / availability / effective interval 的產業表。

### Industry Strength / Decision Desk

app_module/industry_strength_service.py 的實際行為：

- SQLiteIndustryStrengthDataProvider 以 SQLite read-only 讀產業指數、TAIEX、日價與 companies.csv；
- mapping_source_id=meta_data.companies.csv、mapping_version=tw-industry-explicit-map.v1；
- 使用 exact category → pure industry index mapping，將 aggregate / leaf 分開，排除報酬、槓桿、反向與 proxy index；
- type 必須與目前 hard-coded market scope 一致，否則列入 market scope exclusion；
- 代表股是 current registry members 中按 5 / 20 日相對表現排序的 deterministic top-N；
- mapping observed / available 不足時會回報 warning 或沒有 rows；
- summary 固定帶 historical_pit_eligible=False、mapping_mode=current_research_only、pit_history_status=unavailable_current_research_only；
- summary 沒有 per-row accepted PIT source hash、classification version、listing status 或 security type。

app_module/decision_desk_builder_factory.py 把 IndustryStrengthService 當作 sector rotation service；DecisionDeskSnapshot / SectorRotationSummary 會展示產業 ranking、coverage、代表股與 warnings，但沒有獨立的 accepted PIT membership lineage。這是 read-model wiring gap，不是應以 current registry 補洞的理由。

### Recommendation

app_module/recommendation_service.py：

- _decision_frame 會依 cutoff 過濾 market price 日期，若有 available_date 也會只保留 available_date <= cutoff，同一 stock/date 取最後可得版本；
- 有 cutoff 時，last_run_context["warnings"] 加入 industry_membership_not_point_in_time；
- 有 cutoff 且 filters.industry 不是「全部」時，對所有候選建立 missing matrix，reason code 為 industry_membership_pit_unavailable，並回傳空推薦；
- 無 cutoff 時才使用 IndustryMapper.filter_stocks_by_industry 和 get_stock_industries；
- industry reason 仍來自 current IndustryMapper 的 current industry index performance；歷史 cutoff 不會呼叫該 reason path。

這表示 Recommendation 已經安全地拒絕未驗證歷史產業 membership，但尚未有「accepted PIT provider → industry filter → run context / result lineage」的接線。

## PIT 時間與資料語意驗收表

| 欄位 / 問題 | 目前官方證據 | 現有實作 | 驗收規則 |
|---|---|---|---|
| publication date | t187 JSON / CSV 的 出表日期 / Date | parser 讀 date；machine 將其組成 Taipei 午夜 publication_at | 只能稱為 publication date label；沒有官方 timestamp 時不得宣稱 precise publication time。 |
| publication time | T97 / TWT58U / T30 商品頁提供產製時間；實際檔案仍需保存 | current t187 lane 不使用商品頁時間推導 | 付費歷史檔須同時保存檔案日期、官方格式版本、官方 production-time spec hash 與實際交付 / download completion。 |
| available_at | HTTP response 完成時間、raw archive capture time | machine / denominator 保存 captured_at；TPEX / TWSE HTTP Date / Last-Modified 只作 metadata | decision_at 只能消費 available_at <= decision_at；scrape time 不是 publication time；HTTP header 不能取代 response completion。 |
| effective_from | t187 current snapshot 本身沒有有效起始區間 | machine 設為自然日 capture date；不許早於 capture date | 只有 first-seen current-day candidate；正式 interval 要由連續 accepted observations 或官方 effective-date notice 建立。 |
| effective_to | t187 current snapshot 沒有終止日 | None | 下一個 accepted source version / official change notice 通過後，才可封閉前一段；不能因 current row 消失就猜測 end date。 |
| source_version | 現在是 dataset + publication date | t187ap03_L:YYYY-MM-DD 類型 | 後續需增加 format / classification version 與文件 hash，不能只靠 payload date。 |
| classification_version | TPEx 官方公告與格式文件顯示 2014、2023 等變更 | current explicit map 不具 historical taxonomy version | 每個 membership row / envelope 要帶 classification version、mapping artifact hash、effective date；分類名稱不可向歷史回填。 |
| market | L=TWSE listed、O=TPEx OTC、R=TPEx emerging | machine 只有 L/O；industry service hard-code twse scope | market scope 必須是 row-level 欄位；L/O/R 分開驗收、分母、coverage 與結果，不可把 R 併入 O。 |
| listing / trading status | 18419 / 25036 basic data 不是完整歷史 status stream；T97 有上次交易日、交易方式及處置 / 注意等欄位 | current registry 沒有完整 effective status interval | status / security type 必須有獨立官方來源或明確 nullable / missing state；退市、暫停、處置不可以 silently carry forward。 |
| security identity | basic data 有公司 / 證券欄位，但沒有完整 corporate-action identity history | current code 以 symbol 為主鍵 | symbol rename、合併、分割、上市 / 上櫃轉換要有官方 event / identity source；不能把同一 symbol 當作永遠同一證券。 |
| aggregate / ETF / inverse / leverage | industry index 是 benchmark / ranking input，不是 company membership | service 已排除部分 proxy index | index、ETF、槓桿、反向、權證、TDR / 特殊證券等不得直接當一般產業個股；要有 security-type gate。 |
| missing / suspended | source 或 price 可能缺件；T97 有部分交易狀態欄位 | industry service 會 partial coverage / representative missing；assembler 會 missing reason | 缺件、停牌、沒有當日價格要降級或排除；不得拿 current membership / 最近一筆 price 補齊歷史。 |

## 本地 artifact 觀察

### Prospective denominator 與 machine capture

只讀檢查 output/formal_daily_publications/ 的結果：

| Artifact / 日期 | source coverage | row / universe | 重要 metadata |
|---|---|---:|---|
| pit_denominator/2026-09-08-run8 | TWSE 1,094；TPEx 890 | 1,984 | coverage_start=2026-09-08；TWSE JSON publication date=2026-09-06、TPEx=2026-09-07；source capture date=2026-09-08；machine license scope verified，legal acceptance inferred=false。 |
| pit_denominator/2026-09-08-run9 | TWSE 1,094；TPEx 890 | 1,984 | 同一 prospective scope 的重跑；raw response completion / hash / CSV / metadata / Swagger / license 均各自保存。 |
| pit_denominator/2026-09-10-* | TWSE 1,094；TPEx 890 | 1,984 | 兩市場 JSON publication date 均為 2026-09-09；coverage_start=2026-09-10。 |
| pit_denominator/2026-09-11-* | TWSE 1,094；TPEx 891 | 1,985 | 兩市場 JSON publication date 均為 2026-09-10；symbol count 變化被保留，而非補成固定 current universe。 |
| pit_candidate_archive/2026-09-07、09-08、09-10、09-11、09-15 | TWSE + TPEx machine archive | 1,984、1,985 | 每筆 archive manifest / raw / receipt 都標記 candidate_only、formal_consumer_compatible=false、historical_backfill_claimed=false；2026-09-08 有多個不同 capture。 |

一個具體 archive manifest 範例：

- output/formal_daily_publications/pit_candidate_archive/2026-09-07/05cfa45cd06221a6-5c0f35d14dbd4e90/archive_manifest.json；
- captured_at=2026-09-07T23:45:45.470485+08:00、effective_from=2026-09-07、row_count=1984；
- TPEx raw completion 是 2026-09-07T23:45:45.470485+08:00，TWSE raw completion 是 2026-09-07T23:45:41.466340+08:00；
- HTTP Date / Last-Modified 與 response completion 不是同一語意；
- producer code hash、raw hash、publication content hash 都被保存，但仍是 candidate。

這些 artifact 證明「prospective custody 可以被重驗」，不證明「某個更早日期的 membership 在當時已可得」，更不證明 2014–2026 的歷史狀態。

### Formal publisher 的實際 blocker（限本輪搜尋範圍）

在 repository 的 `output/formal_daily_publications/` 搜尋範圍內，`pit_sector_membership_formal/` 目前觀察到的都是 `blocked-receipt-*.json`，沒有成功的 production formal `sidecar.json + receipt.json` readback。可重驗的最新 scheduler 狀態是：

- `output/formal_daily_publications/scheduler/pit_preopen_capture/latest_status.json`：`status=machine_verified_candidate`、`candidate_only=true`、`formal_consumer_compatible=false`、`historical_backfill_claimed=false`；`observed_at=2026-09-14T16:00:06.163748-07:00`，archive path 指向 2026-09-15 candidate archive，denominator refresh 因 TPEx data.gov CSV DNS failure 而 `blocked`。
- `output/formal_daily_publications/scheduler/pit_sidecar/latest_status.json`：`status=blocked`、`formal_ready=false`，blocker 是 `verified PIT denominator is missing for 2026-09-15`；`observed_at=2026-09-14T18:00:02.01461-07:00`。

在同一 repository output path 的 blocked receipts，阻擋原因包括：

- pit_formal_decision_before_current_day_cutoff；
- pit_formal_handoff_coverage_incomplete / pit_formal_history_missing_natural_days；
- pit_formal_multiple_distinct_captures_for_natural_day；
- archive producer code hash 不是 current 或 audited legacy hash；
- pit_formal_archive_universe_binding_failed / publication_rows_do_not_cover_expected_universe；
- calendar unknown 或 required trading dates empty。

這些 blocker 是正確的 fail-closed 行為，不能透過把 current registry 或 scrape time 寫進 sidecar 來消除。上述結論只描述本輪實際搜尋到的 repository output path；不能外推為所有外部或其他 production location 都沒有 artifact。

### `TWStockConfig` data root 交叉檢查

依 `data_module/config.py::TWStockConfig` 的預設值，於 2026-09-15 額外只讀檢查 `D:\Min\Python\Project\FA_Data` 與 `D:\Min\Python\Project\FA_Data\output`，並以 `pit`、`sector`、`membership`、`sidecar`、`receipt` 關鍵字搜尋適用的 latest artifact。結果如下：

- 找到一份可重驗的 prospective artifact：`D:\Min\Python\Project\FA_Data\output\formal_prospective\clock-20260825\pit_sector_membership\manifest.json`。讀取 `manifest` 內層後，`schema_version=pit-sector-membership-prospective-manifest-v1`、`scope=prospective_only`、coverage=`2026-08-25` 單日、`status=complete`、`row_count=1932`、`formal_consumer_compatible=true`、`historical_backfill_claimed=false`、`promotion_eligible=false`。source registry 的 `available_at` 為 `2026-08-24T14:17:05.498298-07:00`（台北時間 2026-08-25 05:17:05.498298），TPEx / TWSE publication date 分別為 2026-08-24 / 2026-08-23，並保存 raw / canonical / universe hash。
- 另以原始檔位元組直接執行 `Get-FileHash -Algorithm SHA256` 核對 registry：`staging/activation_20260825_0513/tpex_t187ap03_O.raw.json` 為 `sha256:4f055c3c035d84c75b299211f36ef2dbe01b700c58c2115aeb6630c7628ce835`，`twse_t187ap03_L.raw.json` 為 `sha256:9e6f88f30420552e435951193dc44094d726412c8d917d8a975581d8ae083c97`，均與 manifest 的 `raw_hash` / `source_hash` 完全相符。這項 raw custody 不能用重序列化 JSON 的 digest 代替。
- 上述 `formal_consumer_compatible=true` 只表示 sidecar 形狀可供 prospective consumer 使用；raw、rows、universe、clock 與 cutoff 會由新 reader 逐層重驗。本輪仍不把它判定為 historical accepted，也沒有從它推導 current 2026-09 的正式 acceptance。
- 在這個 data-root output 搜尋範圍內，沒有找到同名的 `formal_daily_publications/`、`pit_sector_membership_formal/` 或 `pit_candidate_archive/` 子樹。因此 repository candidate archive 與 data-root prospective artifact 必須分開記錄，不能互相冒充。
- data root 目前最新適用的 ML raw pointer 是 `D:\Min\Python\Project\FA_Data\output\scheduled\ml_allocation_copilot\raw_pit_publications\latest_manifest.json`，指向 `runs/pit-d1fd51da99511b1932be8e1b/manifest.json`；其 `schema_version=ml-pit-year-shards.v1`，membership `source_id/source_version/observed_at/available_at/effective_from/source_hash` 都是 null，且 scope 只有 11 個指定 symbol，不能視為 PIT sector membership receipt。
- 同一 data root 最新 shadow sidecar `D:\Min\Python\Project\FA_Data\output\scheduled\ml_allocation_copilot\sidecar\20260909_eca160b5e21f3f20_shadow.json` 的 `record_type=daily_shadow_lane_observation`、`schema_version=ml-allocation-copilot.v1`、`decision_at=2026-09-08T17:30:00-07:00`、failure=`promotion_evidence_missing`，沒有 membership source / effective interval 欄位，因此也不是本題的 PIT sector sidecar。`D:\Min\Python\Project\FA_Data\output\release_v4\pit_historical_coverage.json` 是另一套 historical coverage audit，沒有顯示 PIT sector membership acceptance，不能代替本題 receipt。

以上 data-root 結論只涵蓋 `TWStockConfig` 指向的 output subtree、repository `output/formal_daily_publications/` 與上述明確檔案；沒有搜尋所有檔案系統、外部主機、雲端或未列出的 production location。因此「未找到」是 scoped absence，不是全域不存在；已找到的 2026-08-25 prospective raw custody 則已按位元組 hash 驗證，不再列為 source hash mismatch。

### Probe raw 的地位

output/pit_registry_probe_20260908/ 有 dataset_18419.raw、dataset_25036.raw、emerging.raw、license.raw、TWSE / TPEx CSV、Swagger、terms 等檔案；它是 source discovery / diagnostics probe，沒有 formal acceptance decision、完整歷史 coverage 或 owner license custody。不能把 probe directory 當成已驗收 source registry。

## 明確的 wiring gap 與建議邊界

下列工作是下一個 implementation increment 的具體邊界，本文件不在本次實作：

### 1. 共用 accepted PIT read model

優先重用既有 pit-sector-membership-sidecar-v1 與 assembler loader，或在 owner / data reviewer 同意後做向後相容的版本升級；不要新建另一個不帶 hash 的 SQLite current industry table。最少要能輸出：

- symbol、market_scope、sector_id；
- classification_version；
- listing_status / security_type（若來源沒有，顯式 missing，不猜）；
- available_at、effective_from、effective_to；
- source_id、source_version、row / envelope source hash、canonical rows hash；
- universe_hash、license_id、quality / missing reason；
- envelope 的 scope：prospective、historical、current-research-only、candidate。

任何 reader 都必須要求 available_at <= decision_at、日期 interval 命中、source status accepted、universe / hash / license gate 通過。

### 2. Industry Strength provider

把 accepted PIT reader 作為新的 provider boundary，輸入 as_of_date + decision time，輸出：

- accepted PIT membership 的 source / version / hash / market scope；
- classification version 與 coverage；
- leaf / aggregate 規則；
- unmapped、duplicate、ambiguous、missing / suspended、price coverage；
- historical_pit_eligible 真實值。

current companies.csv 只能保留為 current-research provider；如果 PIT reader 缺件，必須回現有 missing / warning，不得 silent fallback。

代表股規則應固定為：

- 先以 accepted membership 決定當日成員；
- 再以同一 decision date 可得的價格、交易狀態、5 / 20 日 window 計算；
- 只在同一 leaf industry、同一 market scope 內排序；
- 無足夠價格或 suspended 時，標記 degraded / missing，不換成別的產業或 market；
- benchmark TAIEX 與 industry index 是 performance benchmark，不是 membership source；
- index、ETF、槓桿、反向與其他特殊證券永不進一般 industry stock representative。

### 3. Recommendation caller

在 RecommendationService 的 industry filter gate 前接同一個 accepted PIT provider：

- as_of_date 有值時，先驗證 membership source；
- 成功時才依當日 accepted members 過濾；
- last_run_context、RecommendationResultDTO、screening matrix 要帶 scope、PIT eligibility、source id / version / hash、classification version、quality；
- source 缺件、未到 available_at、interval 不命中或 market / security type 不明時，保留 industry_membership_pit_unavailable 類負證據；
- 無 cutoff 的 current research 不可被誤標成 historical PIT。

### 4. Decision Desk

Decision Desk 不應自己再讀 companies.csv。它應消費 Industry Strength summary 的同一份 lineage，至少顯示：

- as-of / decision time；
- market scope 與 classification version；
- PIT source id、source hash、available / effective interval；
- coverage、missing、quality、代表股規則；
- current-research 或 accepted PIT 的 lane。

這可保持既有 UI / DTO 形狀，但使市場 → 產業 → 個股 → Recommendation 的來源可追溯。

### 5. Emerging、security status 與 corporate actions

在把 R source 納入 production / formal 前，必須單獨決定：

- emerging 是否是本產品的 eligible market；
- emerging 的 independent denominator、license scope、historical source；
- 上市 / 上櫃 / 興櫃 / 管理股票 / ETF / 權證 / TDR 等 security type 分類；
- symbol rename、合併、分割、下市、轉板的 official identity / event source；
- suspended / last-trading-day 的有效區間與 missing policy。

不可以因為 R endpoint 存在就把它併入 O，也不可以因為 current basic data 有上市日期欄位就推導完整歷史 listing interval。

## 下一個 implementation increment 的 concrete file scope

這個 scope 可在不碰本輪其他 agent 未提交變更的前提下實作；本文件只定義邊界，不在本次建立或修改 production code：

- 新增 `data_module/pit_sector_membership_reader.py`：read-only 讀取既有 `pit-sector-membership-sidecar-v1` / prospective manifest，統一檢查 `available_at`、effective interval、market、source status、hash、universe 與 missing reason；明確分開 `programmatically_supported`、`artifact_status`、`accepted`，不寫 DB、不改 raw。
- 修改 `app_module/industry_strength_service.py`：加入可注入的 PIT membership provider；有明確 accepted available date / market 時才用 PIT 成員計算，其他日期、market 或 security type 缺件時回 explicit missing / degraded；`companies.csv` 只留 current-research lane。
- 修改 `app_module/recommendation_service.py`：在 historical industry filter 前呼叫同一 reader，成功時帶入 membership lineage；不可用時保留 `industry_membership_pit_unavailable`，不 fallback 到 current `IndustryMapper`。
- 修改 `app_module/decision_desk_composition.py` 或 `app_module/decision_desk_service.py` 的既有 summary wiring：只傳遞 Industry Strength 已產生的 PIT scope / source / hash / quality，不另建產業來源。
- 新增對應的 `tests/test_industry_strength_pit_acceptance.py`、`tests/test_recommendation_industry_pit_caller.py`、`tests/test_decision_desk_industry_pit_lineage.py`，覆蓋 accepted available date / market 與其他日期 explicit missing。
- 本 increment 明確不修改 `app_module/user_declared_holding_research.py`、`ui_qt/views/portfolio_view.py`、`docs/07_guides/APPLICATION_MANUAL.md` 或 `data_module/portfolio_ml_dataset_assembler.py`；assembler 只作既有 row contract 的 read-model 參考。

### 第一個可執行的 acceptance slice

### Slice A：prospective，限定 current-natural-day

1. 第一 slice 不等待 2014–2026 付費資料，也不把 free official read-only source 的技術消費設成 owner / legal approval blocker。沿用 L/O 的 source producer + data.gov denominator machine lane；法律解釋仍與程式驗證分開，不在本文件做法律結論。
2. reader 對每個日期 / market 只消費 read model 已明確標成 accepted 且 `available_at <= decision_at`、interval 命中的 artifact；沒有該日期或 market 的 artifact 就回 explicit missing，不用 current snapshot 補洞。本輪觀察到的 candidate 不因為這個實作計畫而自動變成 accepted。
3. 從下一個實際 capture 日開始保存：
   - 官方 raw JSON；
   - requested / final URL、HTTP status、content type、response completion captured_at；
   - official publication date（date-only）；
   - raw / canonical row / envelope hash；
   - schema / producer code hash；
   - market、universe、license、classification mapping version。
4. 同一自然日若有不同內容 hash，不挑一筆「看起來最完整」的，而是 fail closed；重試且內容相同才可視為同一觀測。
5. 使用 data.gov CSV + metadata + Swagger + license document 做獨立分母與來源 mapping；不使用 companies.csv。
6. 08:30 後再做 formal handoff；不把同日 08:30 前尚未可得的 snapshot credit 給該日。這是 formal publisher gate，不是第一 slice 的歷史資料 prerequisite。
7. 在 Industry Strength 與 Recommendation 接線前，先只輸出 read-only lineage / diagnostics，不改 production decision。

### Slice B：歷史，optional future expansion，不是 Slice A prerequisite

1. TWSE：購買 / 取得 T97 的 2014-01-06 起原始檔，保存訂單 / 條款 / 用途、每檔 raw bytes、官方 format version、production date/time、delivery completion、hash。
2. TPEx：取得 T30 的 2008-11-01 起原始檔與格式說明，保存每次分類碼版本、公告生效日與檔案 hash。
3. 對每一日重建 effective_from / effective_to，只使用檔案本身可支持的 date / official change notice；不可用 2026 current mapping 回填 2014。
4. 補做 symbol identity、listing / delisting、security type、suspension / last-trading-day 與 corporate-action crosswalk。
5. 明確宣告 market coverage：T97 + T30 仍不自動包含 TPEx emerging；若沒有 R 的歷史來源，歷史 lane 必須標明「TWSE + TPEx OTC only」，不可寫成全台股。
6. 付費購買與 licensed custody 是後續 historical expansion；本輪沒有購買，也不以此阻擋 Slice A。只有提出 historical request 時，才維持 historical lane blocked / missing；prospective accepted available date / market 仍可獨立消費。

## 驗收測試與 QA 路由

### 既有測試應作為固定 gate

- tests/test_prospective_official_pit_source.py：官方 source parser、market、publication date、expected symbols、license / source lineage；
- tests/test_pit_sector_membership_machine.py：raw custody、hash、future capture、duplicate market symbol、natural-day effective_from、candidate-only receipt；
- tests/test_pit_prospective_denominator.py：JSON / CSV 對照、data.gov metadata、Swagger、license fingerprint、coverage_start、source independence；
- tests/test_formal_pit_candidate_archive.py：archive custody、readback、candidate archive integrity；
- tests/test_formal_pit_history_handoff.py：natural day、available / archive cutoff、calendar coverage、missing date；
- tests/test_formal_pit_denominator_handoff.py：independent universe、universe hash binding、license scope、current-day cutoff；
- tests/test_formal_pit_sector_publisher.py：formal sidecar / assembler readback 與 blocked conditions；
- tests/test_portfolio_ml_dataset_assembler.py：accepted row fields、available_at、effective interval、current snapshot poison、missing reason；
- tests/test_sector_rotation_service.py：current mapping 的 market scope、duplicate / ambiguous、future observation、benchmark、代表股與 partial coverage；
- tests/test_task_loop_03_contract.py：historical industry filter 必須 fail closed 為 industry_membership_pit_unavailable。

### 下一個 implementation increment 應新增的測試

建議新增但本次不建立：

- tests/test_industry_strength_pit_acceptance.py
  - accepted membership 只在 available_at <= decision_at 且 interval 命中時可用；
  - L/O/R scope 分離；
  - classification version 變更不向前套用；
  - missing / suspended / no price 只降級，不換成 current member；
  - leaf / aggregate、benchmark、代表股 deterministic；
  - source hash / universe hash / quality 進 summary。
- tests/test_recommendation_industry_pit_caller.py
  - Recommendation historical industry filter 消費同一 reader；
  - context / DTO 帶 source lineage；
  - unavailable、future available_at、invalid interval、unaccepted source 都保留負證據；
  - 不允許 fallback 到 IndustryMapper current registry。
- tests/test_decision_desk_industry_pit_lineage.py
  - Decision Desk 維持 sector summary 的 PIT scope / hash / classification / quality；
  - current-research 與 accepted-PIT lane 在 UI payload 中可區分。

測試 fixture 只證明 parser / contract / fail-closed semantics；不能當成外部歷史 evidence。真正的 historical acceptance 必須以 owner-approved、raw-byte、timestamp、license 與 hash-bound artifact 驗收。

## Decision table

「程式上已支援」與「本輪 artifact 是否已驗收」分開列示；candidate 不等於 accepted。

| Lane | 程式上已支援 | 本輪 artifact / acceptance 狀態 | 允許用途 | 不允許用途 |
|---|---|---|---|---|
| t187ap03_L + data.gov 18419 | source producer + prospective denominator 已支援 | 本輪有 machine-scope / candidate raw；沒有把 candidate 宣告為正式 accepted | reader 只可消費 read model 明確 accepted 的 prospective 日期 / market；其餘 explicit missing | historical backfill、正式 OOS、production broker action |
| t187ap03_O + data.gov 25036 | source producer + prospective denominator 已支援 | 本輪有 machine-scope / candidate raw；沒有把 candidate 宣告為正式 accepted | 同上；L/O scope 分開，不互補缺件 | historical backfill、正式 OOS、production broker action |
| data-root 2026-08-25 prospective manifest | sidecar envelope 可由 prospective reader 解析 | `status=complete`、`formal_consumer_compatible=true`、單日 prospective、`historical_backfill_claimed=false`；本輪未作 formal acceptance decision | 若後續 read-model policy 明確接受該日期 / market，可作 2026-08-25 prospective consumption；其他日期仍 missing | historical coverage、current 2026-09 推論、正式 OOS |
| t187ap03_R / data.gov 28568 | 只有共用 source definition；machine / denominator reader lane 未支援 | 本輪只有舊 probe，沒有 accepted artifact | source discovery、parser fixture、待驗收 | 直接併入 TPEx OTC 或全市場 coverage |
| companies.csv | current research provider 已支援 | `current_research_only`，不是 PIT artifact | current Industry Strength / UI research | historical PIT、Recommendation historical industry filter |
| TWSE TWT58U / T97 | 官方商品頁可作 future source definition | 本輪未購買、未找到 raw delivery / order / hash custody | optional future procurement / format acceptance | 任何 historical claim |
| TPEx T30 | 官方商品頁與格式文件可作 future source definition | 本輪未購買、未找到 raw delivery / order / hash custody | optional future procurement / format acceptance | 任何 historical claim |
| machine archive | custody / diagnostic readback code 已支援 | `candidate_only=true`、`formal_consumer_compatible=false`、非 historical | custody / diagnostic readback | formal sidecar、historical credit |
| formal publisher output | blocked-state / fail-closed path 已支援 | 本輪 repository output path 只有 blocked receipts；data-root search 另有 scoped prospective manifest，未找到同名 formal sidecar | blocker evidence | 把 blocked receipt 當成功 acceptance，或外推為全域 production absence |

## 未解決且需外部 owner / data reviewer 決策（只針對 formal / future expansion）

1. data.gov license 的 machine policy 與 legal acceptance 如何分工；目前 code 明確把兩者分開。這個未決項不阻擋 free official read-only source 的技術 reader / prospective diagnostics，也不把 machine policy 當法律意見。
2. 未來是否購買 T97 / T30，誰是 owner、可否在本專案內保存 raw bytes、可否供 Recommendation / Decision Desk / ML 使用；這是 optional historical expansion，不是第一個 prospective implementation slice 的 prerequisite。
3. T97 / T30 每日檔案的 exact publication / delivery timestamp、format version 與版本變更 archive。
4. TPEx emerging 是否納入 product universe；若納入，R 的 prospective 與 historical source、denominator、calendar、status contract。
5. classification version / industry code crosswalk 的官方 SSOT、有效日與 hash。
6. listing / delisting / suspension / special security / corporate-action identity 的官方 source 與 missing policy。
7. historical lane 是否先限定 TWSE + TPEx OTC；若不包含 emerging，所有 API / UI / report 必須明示 coverage scope。

## 最終判定

這次 discovery 成功確認了「官方 prospective source → raw custody → independent denominator → candidate archive → formal handoff → assembler」的程式骨架，也確認了「Industry Strength / Recommendation / Decision Desk 尚未消費本輪 PIT membership」的實際 wiring 缺口。2026-08-25 manifest 的 raw custody 已證實與 registry 相符；是否可由 caller 消費仍須通過 reader 的 rows、universe、clock、available/effective interval、market、taxonomy 與特殊證券檢查。程式支援與 artifact acceptance 仍分開：prospective accepted 不等於 historical accepted、formal OOS 或 production promotion。

尚未完成的不是把 current mapping 再包一層，而是取得並驗收具有：

- official publication / available time；
- effective interval；
- classification version；
- market / listing / security status；
- source / row / universe hash；
- license / owner decision；
- missing / corporate-action policy；
- historical date coverage；

的單一可重驗 source contract。

下一個 implementation increment 可以先做 free L/O 的 read-only reader 與 Industry Strength / Recommendation / Decision Desk lineage wiring：只消費 read model 已接受且在 decision time 可得的日期 / market，其餘日期、market、R 與 status 不明資料明確回 missing。付費資料與 2014–2026 historical coverage 是 optional future expansion；在它們完成前，歷史推薦仍保持 blocked / missing，current research 保持 current-research-only。不得宣稱 V4 historical PIT、完整 2014–2026 coverage、或已完成 Recommendation / Decision Desk 的 PIT wiring。
