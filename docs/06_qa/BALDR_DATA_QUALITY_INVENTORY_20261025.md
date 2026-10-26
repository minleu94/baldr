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
- 2026-08-01..31 以 7 天窗口、一次 retry 重跑後 30/30 查詢成功，產生 5,724 筆公告事件／projection row；0 failed、0 invalid、0 duplicate，30 個 custody component 並完成 readback。候選目錄：`mops_statement_availability_q2_2026_retry1_20261025`。
- 2026-09-01..30 同樣以 7 天窗口擷取，27 個成功查詢、3 個官方明確無資料，取得 123 筆事件／projection row；0 failed、0 invalid，30 個 custody component 並完成 readback。候選目錄：`mops_statement_availability_q2_2026_sep_candidate_20261025`。
- 2026-10-01..05 六個查詢均為官方明確無資料，沒有公告事件；工具依來源狀態輸出 `unavailable` 候選，不能解讀為查詢失敗或缺漏資料。候選目錄：`mops_statement_availability_q2_2026_oct_candidate_20261025`。

以上仍是隔離研究候選：`formal_oos_allowed=false`、`formal_credit_authorized=false`、`production_blend_alpha_bp=0`。公告候選不能單獨證明舊報表內容正確、完整 coverage 或授權，也未執行正式回填。對 8 月 candidate 的早期對照曾見到 1,976 個 Q2 statement stock 中 109 個本機鍵沒有相符公告、另 10 個候選代碼在本機無對應列；9 月結果增加 123 個較晚事件，尚未完成將兩月候選逐報表種類與本機鍵重新合併的獨立 read-only 對照，故此處不宣稱 109 筆已被解釋或已補齊。
