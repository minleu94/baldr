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

### 2026-10-26 來源缺口呈現易讀性

Decision Desk「完整市場資料 → 資料可見性與擴充因子」改為每個來源分層顯示品質與列數、觀測／可得日期、PIT 可得時間狀態、資格，以及來源 warnings。已知 `historical_pit_unverified`、`observation_date_only`、`missing` 與 `research_only` 轉成繁體中文白話；未知狀態仍保留原值。下一步提示明列逐來源核對缺漏、可得時間、授權及覆蓋，並說明未核清前不拿來做歷史回測或 ML。呈現只讀既有 DTO，不新增資料或改 eligibility。

- `tests/test_ui_qt_decision_desk_view.py`：**53 passed**（3.54 秒）。
- `tests/test_ui_qt_update_view_workbench.py`：**93 passed**（3.87 秒）。
- `scripts/qa_validate_update_tab.py`：**25 passed／0 failed／4 skipped**；第一次預設輸出至 `output/qa/update_tab/RUN_LOG.txt` 被 Windows sandbox 拒絕，使用既有 `BALDR_UPDATE_TAB_QA_LOG_DIR` 改寫到隔離 scratch 後正常完成。跳過項目仍不計為通過。
- 修改的 view／test `py_compile` 通過；全域 mypy **1,145 個來源檔無錯**。pytest、validator、mypy 與 py_compile 均以 Windows Job 執行，readback 為 kill-on-close、8 GiB memory cap、12 process cap，執行後正常退出。
- `git diff --check` 通過。原生 GUI 目視與 Owner UAT 尚未執行；因此只確認 offscreen 回歸和程式靜態檢查，不能宣稱正常桌面視窗尺寸或真人操作已接受。
- Feature Map `change_patterns` 與 targeted document-control check（Feature Map、Snapshot、Operations index、output navigation registry／scope doc）通過，12 個功能入口映射無錯，目標文件 0 錨點／連結錯誤。舊 Snapshot 的精確 QA_RESULTS output 導航已加到既有 registry；只驗目標存在及路徑 metadata，未讀原件內容。其他文件的 output link 與全域 check 尚未清完。

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

### 2026-10-26 官方目錄欄位契約查核

抽查 TWSE 一般業及金融業資產負債表[資料集 94831](https://data.gov.tw/dataset/94831)、[資料集 94829](https://data.gov.tw/dataset/94829)：目錄列有年度、季別、公司代號與財報欄位，標示每三月更新、免費及政府資料開放授權條款第 1 版；股數欄有標明「單位：股」，但目錄沒有說明財報金額單位，也沒有清楚宣告合併／個別 basis。94831 詮釋資料更新時間為 2023-07-25，94829 為 2026-06-30，這些是目錄 metadata 時間，不能當成逐列可得時間。

目前隔離候選每檔的有效列都只有同一個 `出表日期=1151026`；原件 HTTP `Last-Modified` 是整份 CSV 的 response metadata。兩者都不能證明每家公司每個欄位的首次公告時間或後續修訂時序。這一批只有單次 current snapshot，沒有歷史版本可比較，因此無法由候選自身產生 row-level available-at、修訂鏈或 point-in-time 歷史。這些是來源契約缺口，不以 `出表日期`、HTTP `Last-Modified` 或當前值推定；若找不到有授權的歷史原件／公告時間來源，該來源仍不得拿來作歷史回測或 ML 特徵。

### 2026-10-26 P0 季報逐資源／逐欄位唯讀稽核接線

P0「研究證據 → P0 Data Source Control Center」新增使用者明選候選目錄後的離線 CSV 稽核。一次只讀一個目錄；一般業與產業資源分別選取，不合併根目錄或資源。稽核支援目前兩種 capture manifest schema，核對 manifest 安全旗標、逐筆 HTTP／readback 收據、檔案 SHA-256、資源路徑與 CSV 結構，再按市場／報表／產業／資料集逐項呈現有效列、重複業務鍵、欄位空白／非空及精確已知 placeholder 計數。表格不輸出財務儲存格值；目錄選擇只在本次執行有效，啟動預設可由 `P0_QUARTERLY_CANDIDATE_ROOT` 設定。未連網、不匯入、不建立 DB／schema，也不把讀取結果保存成產品資料。

以現有封存的兩個 scratch 根目錄做唯讀重算：一般業 4/4 CSV 可解析，產業資源 12/19 可解析、7/19 是空回應，23 項中缺檔 0、驗證無效 0；可解析列共 3,962 個「報表 × 公司」財報列，`(公司代號, 年度, 季別)` 重複鍵 0。逐欄彙總 31,077 空白、66,631 非空（placeholder 已包含在非空內），檢查的 `-`、`--`、`N/A`、`NA`、`null`、`NULL` token 為 0。這些與前節原內容稽核結果一致；行數不是唯一公司總數或全市場 coverage，跨報表欄位合計也不是統一 schema。空白語意、未申報與不適用仍未知；`available` 在 UI 只譯為「候選檔可解析」，不表示資料源可用或接受。

在 P0 Source Control Center 的 PIT quarterly row 可查看稽核摘要；選資源可看原始財務欄位計數及實檔 SHA 完整提示。欄位表的 placeholder 是非空值子集，不應與非空相加。壞目錄會顯示明確 invalid 原因並維持 candidate-only 邊界。無論計數結果如何，`source_acceptance=false`、`gate_credit=false`、`downstream_eligibility=none`。最終驗證為稽核／來源中心／Research Console focused 105 passed、強制 Workbench 93 passed、Update validator 25 passed／0 failed／4 skipped、全域 mypy 1,148 檔 clean、8 個修改 Python 檔 `py_compile` 通過；Feature Map／code path 與 QA／架構文件 check 通過。Snapshot／Manual link check 仍被既有 `output` junction 的 WinError 5 阻擋，列出的都是舊 trial／task 輸出連結，沒有新稽核章節錯誤。原生桌面 Owner UAT 未執行；沒有改變來源接受、Gate 3、正式回測或 ML 狀態。兩個候選目錄 parser 完整 readback 摘要在 task scratch `quarterly-audit-qa/real-candidate-readback-v3.log`。

2026-10-26 增加逐公司／期別空白剖面、欄位空白率橫條及逐資源下一步指引：選取資源後可依公司代碼、名稱或期別篩選，按空白格數排序，並查看原始空白欄名、出表日期與 placeholder token 計數；公司名稱衝突會明示，不任選名稱。profile 只序列化鍵與計數、不含財務值，每資源最多輸出 5,000 個 key，另提供掃描數及截斷／完整旗標。欄位空白率按空白／(空白+非空) 計算並以無品質門檻色義的橫條展示；placeholder 留在非空分母中，無有效列時顯示 N/A。逐資源指引按可解析／空回應／缺檔／無效提供相應核查路徑；明確提示空回應不等於市場無申報，缺檔／無效修復需另建候選並保留原件。兩個原始候選重讀共輸出／掃描 3,962 個資源內 issuer-period profile（一般業 3,878、產業 84），沒有觸及上限或名稱衝突；profile 計數仍合計 31,077 空白、66,631 非空，與逐欄總數一致。這是資源內有完整 issuer／年度／季別鍵的 CSV 觀測，不是全市場分母；空白／placeholder 語意仍未定。最後驗證：focused suite 115 passed、WorkBench 93 passed、Update validator 25 passed／0 failed／4 skipped、全域 mypy 1,148 檔 clean、3 個修改 Python 檔 `py_compile` 通過、5 條相關程式／測試／QA／架構路徑文件檢查通過。原生 GUI／Owner UAT 與 Gate／ML 資格仍未完成。

### 2026-10-26 季報候選與公司名錄差異可見性

Research Evidence 的 P0 Source Control Center 新增獨立公司名錄候選選取器，呼叫端明選根目錄後，離線核對名錄 capture manifest 的 candidate-only 安全旗標、TWSE 18419／TPEx 25036 來源分母、GET／HTTP 200／未跟隨 redirect／readback 收據、檔案 bytes／SHA、CSV 代號／名稱／產業／出表日期欄及逐市場列數與唯一代號。名錄讀取沒有網路、DB、資料保存或自動套用；路徑只在當次 UI state 有效，`P0_ISSUER_DIRECTORY_CANDIDATE_ROOT` 可作啟動預設。

當季度 CSV 與名錄候選都通過驗證時，服務逐市場 union 目前已完整輸出的 issuer profile 與目錄代號，顯示兩邊都有、名錄有而目前候選未見、目前候選有而名錄未見；表格預設只看差異，可切換全部並依代號／名稱／產業碼篩選。對照明確限定於目前選取的季報根目錄；空回應、缺檔、無效、profile 截斷等會標示結果不完整。`rows` 與摘要只描述兩份明選候選在各自出表時點的觀測，不把目錄當歷史分母，不將「未見」推成漏抓、未申報或應申報。

隔離回歸以 temp CSV／manifest 核 hash 改動與 source-acceptance 邊界拒絕，並以合成季度資料確認差異計數、表格預設差異篩選及全表切換。第一次 focused run 為 51 passed／1 failed；唯一失敗是測試預期值的市場排序與實際排序不同，修正測試排序後結果 **52 passed**；最後納入日期摘要與啟動環境隔離更新後再跑，結果 **54 passed**。強制 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；`scripts/qa_validate_update_tab.py` **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；14 個修改 Python 檔 `py_compile` 通過。最終收據位於工作區 scratch `quarterly-coverage-qa/focused3.log`、`workbench3.log`、`validator3.log`、`mypy3.log`、`py_compile3.log`；Python 命令由 bounded QA runner 在 8 GiB／12 process 上限下執行並自然排空。

此增量不修改或重新擷取名錄／財報原件；沒有把既有官方 issuer 例外映射成自動狀態，也沒有接受來源、改 Gate 3、正式資料、回測或 ML。名錄與財報快照日期不一致；目前季報選擇仍一次只比一個根目錄。已完成 offscreen GUI 自動化，原生桌面畫面及 Owner UAT 尚未完成。document-control 對架構段、QA 清單與 QA 索引的 scoped check 通過；涵蓋 Snapshot／Manual 的較廣檢查仍被既有 `output` junction WinError 5 阻擋，錯誤只涉及舊 trial／task 引用，沒有指向本次新增章節。

### 2026-10-25 MOPS 公告時間 crosswalk 與 Q2 實際解除數

Owner 已授權把 MOPS 顯示的公告日期與時間直接作為對應公告時間戳。本輪更新候選 crosswalk，保留 MOPS 原始 `announcement_at` 的台北時區、事件 SHA 與來源回應 SHA；候選鍵按市場、公司、報表種類及期間比對，不只沿用日級 projection。這項授權已用於時間候選，不等於 MOPS EZSearch 自動採集授權或正式資料寫入許可。

對 2026-Q2 四份一般業 Open Data CSV 的 **3,878** 個公司／報表 profile，對照 2026-07-01 至 2026-09-30 的三組已封存 MOPS 窗口，**3,864** 筆有唯一時間戳候選、**0** 筆有多個公告版本候選、**14** 筆在所選窗口未觀測。未觀測不表示未申報。候選根目錄和 JSON／CSV SHA 留存於本機 `open-data-quarterly-csv-candidate-20261026retry1` 與 `mops_statement_availability_q2_2026_*_20261025`；crosswalk 明確為 candidate-only，`formal_db_write=false`、`source_acceptance=false`、`gate_credit=false`。

將其接回正式資料時，實際結果是 **0 列品質解除**：

- `fundamental_statement_items` 有 1,645,555 列且公告日全缺，但資料期間僅到 2024-Q1，沒有 2026-Q2 目標列。這批公告候選無法回填至不存在的 Q2 財報列。
- `fundamental_current_observations` 有 Q2 資料，但 MOPS current statement HTML 在 TWSE 1,084 家、TPEx 891 家公司與三種報表中，每個公司／報表鍵各有 3 個 `source_version`，合計 5,925 個公司／報表鍵、306,067 列。精查現有候選契約：公告 event hash 綁公告時間、報表項目、detail URL、期間與代碼；`source_sha256` 綁 MOPS 公告查詢 response，不是 filing／財報 HTML bytes。現況 `source_version` 則綁 current statement HTML bytes SHA 及 `captured_at`，`source_available_at` 是擷取時間；公告事件沒有 filing content hash／不可變文件 ID，也沒有寫進現況表的 `announcement_at` 欄。因此 event 到 `source_version` 沒有精確橋。僅以公司、期間、報表類型 join 會把同一時間套到多個報表快照版本；來源擷取時間或相同數值也不能證明它就是公告版。該表全體 `aggregate_feature_eligible=0`，unit／basis 等其他門檻也不會因公告時間而自動解除。因此沒有修改任何一列 Q2 觀測，正式可解除仍為 **0**。
- `fundamental_monthly_revenues` 有 242,651 列缺公告日；現有 1,832 個月營收 availability key 與缺公告日正式 DB key 的精確公司／月份交集為 **0**。沒有各舊月份對應公告時，不拿 2026-Q2 或其他月份時間代填；實際解除 **0 列**。

以上正式 DB 均以唯讀方式檢查，本輪未寫入或重算正式資料。公告匹配候選不能視為 quality projector 已接受的事件映射；要安全解除品質，仍需取得具報表內容版本關聯的公告證據，或 source acceptance 審核建立該連結。MOPS EZSearch endpoint 使用授權、季度 CSV 金額單位／basis、歷史 PIT、舊月營收逐月公告以及其他缺值仍未解。原始 crosswalk 摘要、候選 hash 與唯讀查詢值由 bounded QA runner 產生，詳[本輪公告時間及圖卡 QA](BALDR_INDUSTRY_LEADER_CARDS_20261025.md)。

### 2026-10-26 Research Console 公告候選正式資料影響讀回

Research Console 已把公告候選與正式季報資料的影響摘要接在同一公告對照區。Reader 以唯讀 SQLite 開啟設定資料庫，只查 `fundamental_statement_items` 的公司／報表／期間聚合：版本數、項目列數與缺公告日列數；不選取財務值、不寫 DB。正式表沒有 market 欄，因此 overlap 僅為 identity-only；MOPS 候選事件亦沒有正式 `source_version`／內容 hash 橋接，精確版本連結與公告對照可解除列數不會由身份相同推算。

以已封存 2026-Q2 一般業季報候選及 2026-07-01 至 2026-09-30 三組 MOPS 候選，在本機正式 DB 做實際 reader readback：狀態 `observed`、公告候選唯一鍵 **3,864**；正式 identity overlap **0**、overlap 範圍正式版本 **0**、項目列 **0**、缺公告日項目列 **0**、精確版本連結 **0**、本次可解除 **0**。缺公告日列為 0 是因為這個期間／候選 identity 沒有對應的正式 `fundamental_statement_items` 列，不代表資料庫其他期間已補齊。Reader blockers 為 `formal_table_has_no_market_column_identity_only_overlap` 與 `candidate_event_to_content_version_bridge_missing`。這與前節實際解除 0 列的結果一致，並讓操作頁可直接呈現原因；沒有回填正式資料或改動來源、Gate、PIT、ML 資格。

QA：公告 reader／crosswalk／P0 Source Control Center／Research Console focused suite **125 passed**；必要 Workbench 回歸 **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,151 source files clean**；9 個變更 Python 檔 `py_compile` 通過。實際資料讀回由 8 GiB／12 process 有界 Windows Job 執行，正常退出、Job 無殘留程序。document-control 對 inventory、QA 索引與 README 的 scoped check **12 features／4 link sources／0 errors**。含 PROJECT_SNAPSHOT／APPLICATION_MANUAL 的較廣檢查仍受既有 `output` junction WinError 5 影響，故不能將它記成通過；兩文件新增內容已同步，本輪未跑原生桌面 GUI 或 Owner UAT。

### 季報公告 crosswalk 增加按財報期別摘要

Research Console 的季報公告候選對照，現在對每個選取 CSV 資源按財報所屬期別分列 `profile_resource_rows` 數，以及唯一候選、多筆歧義、查詢窗口內未觀測、查詢窗口不完整與身份缺漏。統計單位明確是資源列／profile；同一公司在不同資源或期別可能重複，因此不代表唯一公司數。查詢窗口內未觀測只表示所選窗口沒有找到對照候選，不等於未申報。

本切片只聚合已選取的離線候選 crosswalk，不新增公告採集、正式資料讀取或寫入，也不改來源接受、Gate、PIT 或 ML 資格。本輪以合成案例驗證期別排序、狀態分桶、缺期身份及跨資源分開計數，沒有重新讀回實際封存候選，因此這份 QA 不提供本機實際候選的期別分布或新的正式資料解除筆數。

QA：crosswalk 與 Research Console focused tests **55 passed**；必要 Workbench 回歸 **93 passed**；全域 mypy **1,151 source files clean**；修改的 2 個 Python 檔 `py_compile` 通過。`scripts/qa_validate_update_tab.py` 因既有 `output/qa/update_tab/RUN_LOG.txt` junction 權限錯誤未能執行完成；bounded Windows Job 正常退出、無殘留程序。offscreen 合成 UI 測試通過；原生桌面 UI／Owner UAT 及實際封存候選 readback 未執行。

### 正式月營收缺公告日按月份唯讀讀回

Research Console 新增正式月營收按期別的公告日欄位品質摘要。Reader 以 SQLite `mode=ro` 和 `PRAGMA query_only=ON` 讀 `fundamental_monthly_revenues`，只按 `period` 聚合列數、缺公告日列、distinct stock code 與 source version；不取營收欄位，也不載入 availability mapping。

本機正式 DB 讀回 147 個月份，期間為 **2014-04 至 2026-06**，共 **246,331 列**、其中 **242,651 列缺公告日**。145 個月份（**2014-04 至 2026-04**）各月所有正式列都缺公告日；2026-05 的 1,848 列與 2026-06 的 1,832 列均有公告日。資料根期間與 mapping coverage 不應混為一談：先前讀回的 availability 檔只覆蓋 2026-06 的 1,832 個 key，與缺公告日正式列精確 overlap 仍為 0。這次沒有回填／重算正式資料；未將公告日完整解讀成單位、口徑、來源接受或 Gate 完整。

實際只讀讀回由 bounded Windows Job 執行，8 GiB memory／12 process 上限 readback 通過，正常退出且無殘留 PID。Receipt：`C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/industry-theme-qa/owned-qa-20261025-8b72bdac6e6e4daea5e4b7da4dbb7433/single_owned_qa_086af2ad67e64b7b995edf2e3adf92f3/receipt.json`，SHA-256 `0ab887fec479114c9440697efc4cde7bea33894b2354c1224276e3634092716`。本切片 reader、P0 DTO/service、crosswalk 與 offscreen UI 整合 focused 執行共 **138 passed**；另有兩個既有 MOPS freshness 測試在 pytest 暫存目錄 `os.replace` 遇到 Windows `WinError 5`，不屬於本次新增資料 reader 路徑。必要 Workbench 回歸 **93 passed**、全域 mypy **1,152 source files clean**、本次修改的 5 個 Python 檔 `py_compile` 通過。Update validator 無法寫入既有 `output/qa/update_tab/RUN_LOG.txt` junction，未完成。額外 shell focused 執行受該 shell Python 缺 PySide6／pytest 套件影響，故不取代 bounded runner 結果。Bounded runner 正常退出且無殘留程序；原生 GUI／Owner UAT 未執行。

### 2026-10-26 MOPS 靜態月報日期語義與月營收公告 mapping 防線

Owner 已授權把 MOPS 顯示的「公告日期／時間」當作相符公告事件 timestamp；它不把整份歷史靜態月報頁首的「出表日期」改成公司別公告時間。本次讀取官方 MOPS 2026-04 月報頁：TWSE 頁顯示「出表日期：115/10/25」，TPEx 頁顯示「出表日期：115/10/24」；這是報表層級的回溯日期，不是每家公司 2026-04 的原始公告時間。來源：[TWSE 2026-04 靜態月報](https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_115_4_0.html)、[TPEx 2026-04 靜態月報](https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_115_4_0.html)。

因此，`monthly_revenue_availability_history` 載入靜態 MOPS 報表時改標為 `mops.monthly_revenue_static_report`／`retrospective_static_report_date`；候選 mapping builder 只記一次該市場／月份的診斷，不把此日期建立成 `announced_date` 或 `available_date`。正式月營收仍保持缺公告日，直到取得公司＋月份＋原公告時間的逐筆事件證據；報表靜態日期、available_date 或當前擷取日期不能替代它。


### 2026-10-19 最新季度 OpenAPI 候選 readback

截至 2026-10-26，repo 已有季度 OpenAPI 最新候選為 `quarterly-openapi-20261019T010111865027Z-19cecc8bee1f483493329969f441c91b`（2026-10-19 UTC 擷取），位於 `output/mops_quarterly_openapi_research/`。終端狀態為 `completed_with_review_items`；唯讀 terminal readback 驗證 26 份 request receipt、3,962 筆數值原始列與 3,954 筆 preview 列。24 個 endpoint 中，16 個為 `observed_row_array`、6 個為 `key_review_required`、2 個為 `schema_review_required`；8 筆待審列未進 preview。16 個可解析 endpoint 的報表期別均為 2026-Q2。preview 的欄位空值計數合計 31,001（欄位值缺漏數，不是公司列數）；這是候選觀測，不代表正式品質清除或全市場 coverage。

該 run 將 `available_at` 留空、`formal_pit_eligible=false`、`issuer_coverage_complete=false`；endpoint 的 `Date`／`出表日期` 不被視為逐列公告時間。官方 OpenAPI catalog 與 Open Data 季報頁提供路由、欄位與季度期別資訊，但不足以確認一般金額單位、合併／個別報表 basis、逐列首次可得時間或修訂版本歷史。相關證據與限制見[季度 OpenAPI 擷取 QA](SCHEDULER_QUARTERLY_OPENAPI_RESEARCH_CAPTURE_20261001.md)及[來源採用與季度目錄 QA](FUNDAMENTAL_SOURCE_ACCEPTANCE_AND_QUARTERLY_CATALOG_20261001.md)；官方來源包括 [TWSE OpenAPI catalog](https://openapi.twse.com.tw/v1/swagger.json)、[TPEx OpenAPI catalog](https://www.tpex.org.tw/openapi/swagger.json)、[TWSE 季報資料集 94831](https://data.gov.tw/dataset/94831)與[TPEx 季報資料集 91967](https://data.gov.tw/dataset/91967)。因此該批資料仍為隔離研究候選，沒有正式 DB 寫入、source acceptance、Gate credit 或 ML 資格變更。
