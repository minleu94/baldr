# Baldr 本機資料品質唯讀盤點（2026-10-25）

## 目的與範圍

釐清受控 Evidence replay 顯示的 fundamental source qualification gaps：本機正式資料庫是否完全沒有相關資料，或是資料存在但品質／來源資格尚不足。這是一次唯讀盤點，不改資料、不接受來源、不提供 Gate credit，也不代表完整市場覆蓋。

來源為 `F:/Min/Python/Project/FA_Data/sqlite/twstock.db`。以 SQLite `mode=ro`、`PRAGMA query_only=ON` 開啟；在 Windows Job Object 中執行，8 GiB 記憶體上限、12 個 process 上限、單一驗證 lock。資料庫大小約 4.11 GB。此次盤點只輸出 schema、列數、日期範圍、quality/source/version 分布，沒有匯出公司資料列。

## 發現

| Table | Rows | 日期範圍／最新值 | Quality 與來源摘要 |
|---|---:|---|---|
| `fundamental_monthly_revenues` | 246,331 | available date 2026-06-17 至 2026-07-15；as-of date 最晚 2026-06-30 | `degraded` 242,651（98.5%）、`observed` 3,680；單一來源 `mops.monthly_revenue_static_snapshot`；3 個 source versions。degraded 242,651 列全都缺 `announced_date`，集中在 2026-06-16 snapshot；3,680 個 observed 列都有公告日。 |
| `fundamental_statement_items` | 1,645,555 | available date 僅 2026-06-17；as-of date 最晚 2024-03-31 | 1,645,555 全為 `degraded`，公告日全缺；3 個 CSV source families；單一 source version `financial-data-statements-2026-06-17` |
| `fundamental_current_observations` | 319,893 | as-of date 最晚 2026-06-30；觀測時間最晚 2026-10-04 | 多個 MOPS／TWSE／TPEx endpoint 及靜態快照來源；`aggregate_feature_eligible=1` 為 0 列。`basis_verified=1` 有 140,300 列、其餘 179,593 列未驗證；此表沒有 `quality` 欄，不能由 row count 推定 qualified。 |
| `fundamental_valuation_metrics` | 1,671 | available/as-of date 最晚 2026-08-06 | 1,671 筆均為 `observed`，來源為 `daily_prices.pe`；僅此欄位概況不能證明授權、覆蓋或 PIT 合格 |
| `decision_desk_snapshots` | 58 | 2026-07-30 至 2026-10-23 | 有近期保存的 Decision Desk snapshots；本次未解讀 snapshot 內容或對其品質重新評分 |

資料庫內本次篩選到 5 張表，沒有名稱符合 `%watchlist%` 的表。`meta_data/fundamental_statement_availability.csv` 不存在。這只表示這個 SQLite 與指定路徑沒有該表／檔案；Watchlist 可能由獨立個人資料庫供應，不能據此宣稱產品 Watchlist 為空。

根因已能由程式與資料交叉核對：月營收與季報的舊 quality projector 都只在 `announced_date` 存在時標 `observed`，缺失就標 `degraded`。本機月營收可用日檔只有 1,832 個 key，與 242,651 個 degraded 月營收 key 沒有重疊；它只覆蓋已有公告日的新版本。舊財報 CSV 最後修改在 2024-04-17 UTC，季報 availability 對照檔不存在。不能用 period end、batch date 或 current `available_date` 偽造公告日。

另以當前 Decision Desk snapshot 的品質／狀態分組，只讀讀回 active snapshots：49 個 `degraded`、7 個 `estimated`（日期截至 2026-10-23）；這佐證資料資格缺漏已影響每日結果呈現。此項只讀 group count，未重算 snapshot 的 underlying inputs。

## 判讀與下一步

實際原始資料量不為零；目前真正問題是大量資料被標記為 `degraded`、可核對的來源可用日期偏舊，且來源接受所需的授權、來源契約、PIT 語義與市場／期間 coverage 證據尚未完成。Evidence Review 顯示「qualification gap」並不等於資料表空白；反過來，資料表有列也不等於來源可以進入策略或 Gate。

Decision Desk 的季報列現可把公告日缺漏筆數直接列出；月營收來源列也會顯示公告日缺漏數。這是根因揭露，不是把日期補成 observed。`fundamental_current_observations` 現有 319,893 列也全部未標 aggregate eligible，代表「目前有觀測值」與「已可進入 aggregate factors」是兩件事。

建議依序完成：

1. 對每個 source version 追查 `degraded` 的原始原因與其建立流程，先找出可安全重建的欄位／批次；不要批次改標成 `observed`。
2. 補上來源、授權／使用條款、可用日與 PIT、coverage 的可核驗原件，分來源、分用途接受。
3. 對更新後的資料重算 freshness、缺漏、唯一鍵衝突及各市場／期間 coverage；本次盤點未做完整鍵衝突或覆蓋分析。
4. 從產品目前實際使用的 Watchlist store 獨立盤點 pool 與欄位品質，並確認 Risk Prompt 各輸入的品質來源。
5. 在 Evidence Review 產品卡上分清「無原始資料」「資料存在但 degraded／stale」「資格證據未齊」三種狀態，再讓真人 reviewer 依 gate policy 判斷。

### 限制

- 日期與列數是 2026-10-25 當次本機資料庫的觀察，不保證此後未變。
- 未驗證來源授權、原始公告／價格原件、逐市場 universe coverage、資料數值正確性或每個下游用途的 eligibility。
- 本次沒有做完整 duplicate/key-collision、欄位缺漏與跨表 join 分析；schema 的 primary key 宣告不等於資料事實已獨立檢核。
- 伴隨的 notebook `baldr_data_quality_inventory_20261025.ipynb` 保存在本機 visualization 工作區；因專案 `.venv` 沒有 `nbconvert`／`nbclient`／`nbformat`，notebook 尚未由 Jupyter 執行。上表來自同一唯讀資料源、以受限 runner 執行的 SQL profile，查詢記錄保存在本機 scratch；notebook JSON 已讀回，但不視為已執行 notebook。

## Follow-up：決策台季財報可見性

Decision Desk 現有的唯讀市場資料可見性列新增 `fundamental_statement_items` 摘要：以 `available_date <= as_of_date` 且 `as_of_date <= as_of_date` 的資料列做 SQL aggregate，顯示列數、股票數、最新期間與最新可用日，並依原列 `quality` 標成 OBSERVED／DEGRADED。資格固定仍是 `research_only`，PIT 顯示未驗證，並明示 license／coverage／PIT 未由這個摘要驗收。此查詢不載入 164 萬列的數值 payload、不回填資料、不改下游決策。

- Market Data Visibility service 與 Decision Desk offscreen UI focused tests：公告日缺漏顯示切片 **61 passed**（3.69 秒），受 bounded Windows Job Object 執行。
- QA runner 啟動前可用記憶體 29.63 GiB；child 使用 8 GiB Job memory cap、12 process cap，正常退出，未強制清理。
- 正式本機 DB 的季報 SQL aggregate 讀回 1,645,555 列／1,567 檔、判為 `DEGRADED`／`research_only`，查詢耗時 0.607 秒；整個既有資料可見性 service 的當次 read 耗時 6.33 秒，沒有舊版基準，故不能把全部耗時歸因於這次新增查詢。
- 正式設定初始化因 sandbox 不允許建立 `output/application_state/logs/config.log`，退回 console-only；資料庫本身以唯讀方式成功開啟。
- 原生 GUI／正式資料庫互動耗時／Owner UAT：尚未執行。

## Official announcement evidence capture attempt

以既有唯讀 MOPS announcement collector 查詢 2026-Q2 TWSE／TPEx F26–F28 公告，分別保留原始成功 response custody 與 mapping，所有產物都在使用者 visualization scratch；沒有寫正式資料庫、沒有來源接受或 Gate credit。

- 初次 sandbox 擷取因 DNS `NameResolutionError` 產生 `unavailable` 收據；單一 31 天查詢則碰到 MOPS 1,000 列上限，因此不採用該次結果。
- 2026-07-01..31 以 7 天窗口擷取，24 個成功查詢、6 個官方明確無資料，產生 288 筆公告事件／projection row；0 failed、0 invalid，30 個 custody component 並完成 readback。候選目錄：`mops_statement_availability_q2_2026_jul_candidate_20261025`。
- 2026-08-01..31 以 7 天窗口、一次 retry 重跑後 30/30 查詢成功，產生 5,724 筆公告事件／projection row；0 failed、0 invalid、0 duplicate，30 個 custody component 並完成 readback。候選目錄：`mops_statement_availability_q2_2026_retry1_20261025`。
- 2026-09-01..30 同樣以 7 天窗口擷取，27 個成功查詢、3 個官方明確無資料，取得 123 筆事件／projection row；0 failed、0 invalid，30 個 custody component 並完成 readback。候選目錄：`mops_statement_availability_q2_2026_sep_candidate_20261025`。
- 2026-10-01..05 六個查詢均為官方明確無資料，沒有公告事件；工具依來源狀態輸出 `unavailable` 候選，不能解讀為查詢失敗或缺漏資料。候選目錄：`mops_statement_availability_q2_2026_oct_candidate_20261025`。

以上仍是隔離研究候選：`formal_oos_allowed=false`、`formal_credit_authorized=false`、`production_blend_alpha_bp=0`。公告候選不能單獨證明舊報表內容正確、完整 coverage 或授權，也未執行正式回填。將 8、9 月 mapping 按 response hash 回連 query manifest 的市場，再按市場／股票／報表種類對照本機 `fundamental_current_observations` 的 2026-Q2 current statement keys，唯讀結果如下：

| Market | Statement type | Current keys | Candidate keys | Matched | Current without event | Candidate without current row |
|---|---|---:|---:|---:|---:|---:|
| TWSE | balance sheet / income / cash flows（各類相同） | 1,084 | 1,096 | 1,084 | 0 | 12 |
| TPEx | balance sheet / income / cash flows（各類相同） | 891 | 888 | 885 | 6 | 3 |

合計 1,975 個 MOPS current HTML 子集股票身份中，1,969 檔有 7–9 月候選公告，仍有 6 檔 TPEx 股票未命中；TWSE 1,084 檔全數命中。另有 15 個候選股票代碼（TWSE 12、TPEx 3）沒有該子集的本機 Q2 對應列。差異對三種報表類型一致。這個比對只涵蓋 2026-07-01..09-30 公告查詢窗及 2026-06-30 的 MOPS current HTML 子集，不代表 MOPS 全市場／其他期間完整 coverage，也未驗證報表值、授權、歷史 PIT 或正式 `fundamental_statement_items` 的逐列正確性。這些結果應留在研究／Gate 3 人工審查，不得因公告匹配就批次補回正式資料。

### 來源授權邊界與後續採集路徑

2026-10-25 重新查核官方條款後，現有 MOPS EZSearch 自動採集路徑的授權範圍仍未證實。證交所網站使用條款第 6 節限制未經同意的自動化下載，第 8 節將已授權政府資料開放平台提供的資料列為例外；條款文字是否適用到獨立的 `mopsov.twse.com.tw` EZSearch 端點，現有證據不能裁定。因此：

- 已捕獲的 MOPS EZSearch 原件與逐筆 custody 繼續留在隔離候選中，僅作為既有研究觀測；不回填正式 DB、不給 source acceptance／Gate credit，也不再以新一輪自動擷取擴大這批資料，直到取得可指向該端點、該用途的明確授權或官方文件。
- 政府資料開放平台逐一列出的資料集具有自己的授權與下載資源。2026-10-25 查到下列四個一般業季度資料集皆列政府資料開放授權條款第 1 版、免費，並從各自的「資料資源下載網址」核出明列 CSV URL：

| 市場／報表 | 開放資料集 | 目錄列出的 CSV 資源 |
|---|---|---|
| TWSE 資產負債表 | [94831](https://data.gov.tw/dataset/94831) | `https://mopsfin.twse.com.tw/opendata/t187ap07_L_ci.csv` |
| TWSE 綜合損益表 | [91998](https://data.gov.tw/dataset/91998) | `https://mopsfin.twse.com.tw/opendata/t187ap06_L_ci.csv` |
| TPEx 資產負債表 | [91967](https://data.gov.tw/dataset/91967) | `https://mopsfin.twse.com.tw/opendata/t187ap07_O_ci.csv` |
| TPEx 綜合損益表 | [94853](https://data.gov.tw/dataset/94853) | `https://mopsfin.twse.com.tw/opendata/t187ap06_O_ci.csv` |

這項明列授權只支援以上資料集及其目錄資源的評估／採集，不能推廣成所有 MOPS／OpenAPI 端點的通用授權。這四份資源只代表一般業，不能代表其他產業或全市場財報；欄位雖有「出表日期」，官方目錄沒有說明它等同逐筆首次公告或可得時間，一般金額單位亦未確認。因此下一步可從這四個明列 CSV 做隔離候選並保留原始 bytes／hash／response metadata，再逐項核 schema、更新時點、單位、coverage 和修訂語意；它們仍不得自動進正式 DB、PIT 或 Gate。
- 既有季度 OpenAPI collector 曾完成 24 個數值 endpoint 的隔離研究擷取，原始回應與 review items 已有 2026-10-01 QA 紀錄。該批資料標記一般金額 `unit_unknown`、`available_at=null`，含 8 個未納入 preview 的 key/schema review 列，且不含現金流量表／權益變動表；不能因此視為完整季度來源或正式可用。不得將 OpenAPI 端點改名或合併成 MOPS EZSearch。

本節記錄目前可核驗的來源範圍與工程採集守則，不作法律裁定。官方依據：[TWSE 使用條款](https://wwwc.twse.com.tw/zh/terms/use.html)；[data.gov.tw 18420](https://data.gov.tw/dataset/18420)。

### 2026-10-26 開放資料季報 CSV 候選與 coverage 對照

使用政府開放平台各資料集頁面明列的 CSV 資源 URL，對四個一般業季報資源各執行一次 GET。四個回應均 HTTP 200，原始 bytes 寫入隔離 scratch 並逐檔 SHA-256 readback；CSV 可解析，沒有正式 DB 寫入、source acceptance 或 Gate credit。原始候選、manifest 與內容稽核位於：

`C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/open-data-quarterly-csv-candidate-20261026retry1/`

| 市場／報表 | data.gov.tw dataset | 列數／唯一代碼 | 期別 | 出表日期 | 原始 bytes | SHA-256 |
|---|---|---:|---|---|---:|---|
| TWSE 資產負債表 | [94831](https://data.gov.tw/dataset/94831) | 1,051 | 115-Q2 | 1151026 | 257,355 | `96cd65e1c5ad1251772bbcf3fae3491c0ce1a60e29a8f2e63f989fd9b99196eb` |
| TWSE 綜合損益表 | [91998](https://data.gov.tw/dataset/91998) | 1,051 | 115-Q2 | 1151026 | 287,750 | `c89fc3db5db5850af8867b81ef12fb53c905facdf0d98d2e7fe51176492c1233` |
| TPEx 資產負債表 | [91967](https://data.gov.tw/dataset/91967) | 888 | 115-Q2 | 1151026 | 207,730 | `94e23dfa43d8accf62dea0d339f924d484d0ee93db9146e3d521dcb53aa7280c` |
| TPEx 綜合損益表 | [94853](https://data.gov.tw/dataset/94853) | 888 | 115-Q2 | 1151026 | 231,938 | `690ee762106602db2b0e3a1d431ba836ed0cea4c039ebdda1f65413843d0fb62` |

四檔 CSV 的公司代碼及 `(公司代號, 年度, 季別)` 都沒有重複；同市場資產負債表與綜損的代碼集合相同。每列欄位數與 header 相符，沒有額外欄或短列。欄位中有大量空字串，但沒有 `-`／`--`／`N/A` 等字面 placeholder；空值究竟代表不適用、未揭露或資料缺漏，官方語意仍未知，不將它轉成 0。四檔都有 `出表日期`，該欄逐列為 1151026；它只證明這次輸出所標的日期，不證明逐筆首次公告／可得時間或修訂歷史。一般金額單位、財報 basis 與歷史 PIT 仍未核定。

另以政府開放平台列出的上市／上櫃公司基本資料資源建立近時點目錄候選：TWSE [18419](https://data.gov.tw/dataset/18419) 有 1,097 個唯一代碼，TPEx [25036](https://data.gov.tw/dataset/25036) 有 894 個唯一代碼，兩檔出表日期皆為 1151025；bytes/hash 及 readback 收據在：

`C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/open-data-company-directory-candidate-20261026/`

目錄比一般業 CSV 晚／早一日的觀測差，故不是完全同日分母。以目錄 `產業別` 欄做集合對照：TWSE 有 46 個目錄代碼不在一般業 CSV（其中產業碼 17 有 31、91 有 10，其他碼合計 5），一般業 CSV 代碼全都在目錄中；TPEx 有 8 個目錄代碼不在一般業 CSV（產業碼 17 有 7、26 有 1），另有兩個 CSV 代碼 `6898`、`6938` 不在前一日目錄。這些差異尚未按全部產業的季報資源及歷史上市狀態裁定，不能宣稱已完整覆蓋或視為來源錯誤。

再與本機 `fundamental_current_observations` 的 2026-Q2、`as_of_date=2026-06-30` MOPS current-HTML 子集唯讀對照：TWSE 子集 1,084 檔中 1,049 檔命中一般業 CSV（35 檔不在一般業集合）；TPEx 子集 891 檔中 883 檔命中（8 檔不在一般業集合）。反向有 2 檔 TWSE、5 檔 TPEx 一般業 CSV 公司代碼沒有該本機子集列。此子集不是正式 issuer denominator，且其觀測時間早於兩份新候選；結果只用來定位差異，不用來判定缺漏、接受來源或補正式資料。

### 2026-10-26 全產業季度 CSV 候選補採與 issuer 對照

依政府資料開放平台各資料集頁面所列資源 URL，追加擷取 19 個非一般業季度 CSV；每項均單次 GET、禁止自動跟隨 redirect、每個 response 上限 32 MiB，原始 body 寫入 scratch 並逐檔 hash/readback。19/19 回 HTTP 200 且原始 bytes 與 readback SHA-256 一致；沒有正式 DB 寫入、來源接受或 Gate credit。完整 manifest、原始檔與集合對照：

`C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/open-data-industry-quarterly-candidate-20261026/`

TWSE 共採資產負債表／綜合損益表各五個產業資源；TPEx 採目錄列出的資產負債表四個及綜合損益表五個產業資源。各市場同一產業的兩種報表有效代碼集合相符：

| 市場／產業 | 季報目錄資產負債表／損益表 dataset | 各表有效代碼 | 觀察 |
|---|---|---:|---|
| TWSE 銀行業 | [94829](https://data.gov.tw/dataset/94829)／[91995](https://data.gov.tw/dataset/91995) | 10 | 115-Q2，出表日 1151026 |
| TWSE 證券期貨業 | [94830](https://data.gov.tw/dataset/94830)／[91996](https://data.gov.tw/dataset/91996) | 3 | 115-Q2，出表日 1151026 |
| TWSE 金控業 | [94832](https://data.gov.tw/dataset/94832)／[91999](https://data.gov.tw/dataset/91999) | 13 | 115-Q2，出表日 1151026 |
| TWSE 保險業 | [94833](https://data.gov.tw/dataset/94833)／[92000](https://data.gov.tw/dataset/92000) | 5 | 115-Q2，出表日 1151026 |
| TWSE 異業 | [94834](https://data.gov.tw/dataset/94834)／[92001](https://data.gov.tw/dataset/92001) | 4 | 115-Q2，出表日 1151026 |
| TPEx 銀行業 | [91965](https://data.gov.tw/dataset/91965)／[94850](https://data.gov.tw/dataset/94850) | 0 | HTTP 200，但沒有有效代碼／年度／季別列 |
| TPEx 證券期貨業 | [91966](https://data.gov.tw/dataset/91966)／[94852](https://data.gov.tw/dataset/94852) | 7 | 115-Q2，出表日 1151026 |
| TPEx 金控業 | [91968](https://data.gov.tw/dataset/91968)／[94854](https://data.gov.tw/dataset/94854) | 0 | HTTP 200，回應僅 78 bytes 表頭／空列 |
| TPEx 保險業 | 無另列資產負債表資源（[94867](https://data.gov.tw/dataset/94867) 保險資料集欄位只見損益項目）／[94855](https://data.gov.tw/dataset/94855) | 0 | 損益資源列為不定期更新；本次沒有有效代碼／年度／季別列 |
| TPEx 異業 | [91970](https://data.gov.tw/dataset/91970)／[94856](https://data.gov.tw/dataset/94856) | 0 | HTTP 200，回應僅 78 bytes 表頭／空列 |

所有非空產業表均只有 115-Q2、出表日 1151026；各檔有效 issuer 代碼無重複。TPEx 空回應只證明本次 response 沒有有效季報列，不能推論產業「沒有公司」或來源已完整。保險業損益目錄頁標示不定期更新；其餘新增目錄頁列政府資料開放授權條款第 1 版／免費與每三月更新。資料集主要欄位清單列出欄名，未提供財報金額單位或合併／個別 basis 說明；例如[一般業](https://data.gov.tw/dataset/94831)與[金融業](https://data.gov.tw/dataset/94829)頁只在股數欄明列「單位：股」，金額單位仍不能由數值推斷。以上授權只支持這些明列資源的研究採集。

對四個一般業與 19 個產業資源再做結構剖析：16 個檔案有有效財報列，合計 3,962 個「報表 × 公司」列；`(公司代號, 年度, 季別)` 重複鍵為 0，觀察欄位的空白值為 31,077／97,708（31.8%），檢查的 `-`、`--`、`N/A`、`NA`、`null`、`NULL` 文字 placeholder 為 0。3,962 是跨報表列數，不是唯一公司數；31.8% 空白可能是格式／適用性／缺漏，官方語意未明，不補零。欄位數在不同報表／產業間從 5 到 64 欄不等，需建立逐報表欄位與單位映射，不能直接拼成一張同質資料表。稽核結果在同一候選目錄 `content_audit_all_quarterly.json`；原始 response、readback hash 與逐來源資料集 ID 在 `capture_manifest.json`。

以 1151025 的 TWSE／TPEx 公司目錄作近時點分母，將四份一般業資源和本次有效產業列去重後：

- TWSE：季報資源聯集 1,086 代碼；目錄 1,097 代碼中 11 個不在該聯集。普通產業代碼 `1589` 的缺列已由官方交易所公告解釋為未依限申報 115 年第一、二季財報；此為官方非申報，不是抓取失敗，也不是資料完整，必須保留缺件／降級狀態。另十個未命中代碼均為目錄產業別 91，原因仍待查。不能因剩餘差異看似小就接受完整 coverage。
- TPEx：季報資源聯集 895 代碼；目錄 894 代碼中 `3718` 不在季報聯集，季報候選另有 `6898`、`6938` 不在前一日目錄。官方公告說明 `3718` 是由 `5371` 中強光電轉換成立的新控股公司，轉換生效日為 2026-09-03，`5371` 自 2026-08-24 停止上櫃交易；因此 `3718` 不是 2026-Q2 季末 issuer。候選 Q2 CSV 也未含 `3718` 或 `5371`。此差異要求以歷史 issuer universe／公司沿革對照並查核前身的 Q2 申報狀態，不能把當前目錄直接當作 Q2 分母，也不能判成 `3718` 漏報。
- 目錄與季度 CSV 的出表日相差一天；這是近時點對照，不是相同觀測時點的正式 denominator。公司目錄也不提供歷史上市狀態或季度財報義務判斷。完整差異代碼與每個檔案 hash 在上述 scratch `scope_reconciliation.json` 與 `capture_manifest.json`。

此補採縮小了「一般業以外都未核對」的未知範圍，但仍未完成來源契約：`出表日期` 不等於逐筆首次公告／available-at；單位、合併／個別 basis、空值語意、修訂歷史、歷史 PIT、產業母體與其餘目錄差異都未解決。候選不得匯入正式 DB，不授予 Gate 3／來源接受或 ML 訓練資格。

### 2026-10-26 issuer 例外查核

- `1589`：TWSE 官方[公告](https://accessibility.twse.com.tw/zh/announcement/announcement/detail.html?id=C4DFB886C2F211F19A80005056BE3760)指出永冠-KY未依限申報 115 年第一、二季財務報告，並公告其上市有價證券預計於 115-11-18 終止上市。該公告足以解釋本次 Q2 CSV 未見該代碼；資料缺件仍須呈現為非申報／降級，不能推估、補零或把來源宣稱為完整。
- `3718`／`5371`：TPEx 官方[公司轉換公告](https://www.tpex.org.tw/storage/eb_data/11508/11500050581.html)記載 `5371` 轉換為新設控股公司 `3718`，於 2026-09-03 生效，`5371` 自 2026-08-24 停止上櫃交易。當前公司目錄含 `3718` 不代表其應出現在 2026-Q2 季末母體；目前 Q2 CSV 候選兩碼皆無，仍需按歷史 issuer 身分核實 `5371` 的 Q2 財報及來源歷史涵蓋。這不是來源接受或 coverage 通過證據。

本次官方查核只把兩個代碼差異分類得更準確；TWSE 其餘十個目錄代碼、TPEx `6898`／`6938` 的時間／母體差異，以及 issuer 沿革完整交叉表仍未解決。沒有正式資料寫入、Gate credit 或 ML 資格變更。
