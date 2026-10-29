# MOPS 月營收衝突報告獨立複核（2026-10-28）

## 範圍與方法

獨立核對使用者提供的 `MOPS 月營收公告衝突逐筆排查、裁決與排除處置報告`、其 325 列處置清冊、輸入問題清單，以及本機正式 SQLite。輸入檔位於本任務的 Codex visualization scratch：`mops_f22_resolution_20261028/all_monthly_revenue_problem_rows.csv`；原報告／處置 CSV 位於 Antigravity scratch，均為唯讀來源。本紀錄補上直接開啟 MOPS F22 明細頁的觀察，不將瀏覽器 DOM 觀察冒稱為已保存的 HTTP 原件。

瀏覽器以問題清單中的官方 `mopsov.twse.com.tw/mops/web/ajax_t05st10_ifrs` 公司／月份 URL 開啟頁面，核對期別、單位、「本月」新台幣數值、功能性貨幣及換算率。公告時間沿用問題清單所列 F22 EZSearch 時間，並按 Owner 2026-10-28 研究取用指示視為該事件的公告時間。正式 SQLite 只讀查詢，沒有回寫資料庫或 availability mapping。

## 複核結果

### 問題列總數與原處置清冊範圍

原始問題清單共 **412 列**：

| 類別 | 列數 |
|---|---:|
| F22 事件晚於舊快照、原始明細未解析 | 4 |
| F22 數值與舊快照不同 | 32 |
| F22 數值相同、版本連結未證明 | 1 |
| 已審來源皆無本機值 | 251 |
| OpenAPI 值的單位／幣別／版本待核 | 124 |

所提供的處置清冊只有 **325 列**，最後一類只納入 37 列，漏掉其餘 **87 列** OpenAPI 待核項目，故不能稱為 412 列全量裁決。清冊的 251 列組成實為 122 家 KY（244 列）、2 家 DR（4 列）、7710（3 列），共 125 個代碼；報告所寫「123 家 KY + 2 家 DR + 7710」多算 1 家 KY。

### 37 列 OpenAPI 值的 MOPS 頁面核對

37 列都以民國 115 年 9 月的 MOPS F22 明細頁核對；其中 36 頁由本次瀏覽器讀取、1591 另有同一工作階段的直接頁面觀察。**35 列 OpenAPI 值等於 MOPS 表格的「新台幣」本月欄**；MOPS 表頭單位為新台幣仟元。這批值是新台幣欄，不應因功能性貨幣為人民幣、美元、新加坡幣或日圓而當成該功能性貨幣數值。

兩個例外：

| 公司／月份 | OpenAPI | 目前 MOPS 明細 | 判讀 |
|---|---:|---:|---|
| 1590／2026-09 | 空值 | 新台幣 3,810,653 仟元；功能性貨幣人民幣 806,179 仟元，換算率 4.7268 | MOPS 有值；OpenAPI 空值屬來源缺值，不是 MOPS 缺公告。 |
| 5543 桓鼎-KY／2026-09 | 212,703 | 新台幣 203,685 仟元；功能性貨幣新台幣，換算率 1.0000 | **數值衝突 9,018 仟元**。應採明細頁目前值作待核修訂候選，保留 OpenAPI 值與公告事件；不得把此列列為單位已核或版本已吻合。 |

目前明細頁例：[5543／115 年 9 月 MOPS F22](https://mopsov.twse.com.tw/mops/web/ajax_t05st10_ifrs?encodeURIComponent=1&step=1&firstin=1&off=1&keyword4=&code1=&TYPEK2=&checkbtn=&queryName=co_id&inpuType=co_id&TYPEK=all&isnew=false&co_id=5543&year=115&month=09)。頁面目前值與問題清單的 OpenAPI 值不一致，證明不能只用「單位／幣別不明」概括所有 37 列，也不能由目前頁面倒推原公告當時的歷史值。

### Gemini Scrapling F22 公告事件批次複核

repo 內 `scripts/harvest_mops_monthly_revenue_events.py` 使用 Scrapling `Fetcher.post` 查 MOPS EZSearch F22 事件端點；這不是頁面明細數值擷取器，也沒有使用 stealth browser、proxy 或 CAPTCHA/challenge 處理。它按市場與日期切窗，預設請求間隔 10 秒，HTTP 403／429 時停止。其既有產物在 `output/mops_harvest_2026/`：

- `manifest.csv` 共 **120 個視窗**，全部 HTTP 200；涵蓋 2026-01 至 2026-10-29，單一視窗最高 787 列，低於 1,000 列警戒值。
- `raw/` 下 120 份 JSON 原件逐一通過檔案存在、位元組數及 SHA-256 核對；重新解析後每份 `data` 列數均與 manifest 相同，合計 **19,983 列**，與 `events.csv` 列數相同。
- 對照本清單 412 列，全部 **412/412** 以公司代碼、期別、`announced_at` 與 `detail_url` 精確匹配到獨立批次事件；因此這批公告時間／明細連結已由保存的官方 F22 event raw 支持，不必為相同年份與範圍重複抓取。
- 批次中有兩筆事件沒有解析出 `announced_at`，但不在這 412 個目標列中。32 筆「數值不同」對應的 EZSearch 主旨均是一般期別月營收文字，擷取器的更正關鍵字欄對這些列均為 `FALSE`；整批 19,983 列也未命中更正關鍵字。這份 F22 批次本身不足以證明報告所稱的「32 筆已證實更正／重編」；需要逐筆看明細修訂證據與版本差異。

因此，Gemini 這種 Scrapling 批次**有助於一次取得並封存公告事件、核對公告時間及明細 URL**，且這 412 列的事件工作已完成。`events.csv` 沒有 F22 明細的「本月」數值、單位或功能性貨幣，故不會補上缺失的月營收列，也不能解除 251 個空值或 124 個 OpenAPI 單位／版本待核。後續值資料應優先一次取得官方的全市場／月份資料集，先核對市場與代碼覆蓋、月份、列數、重複／缺列及單位欄，再按市場、月份與幣別類型抽樣讀 F22 明細。只有資料集未涵蓋、欄位不一致或比對出差異的列，才逐列開明細。已核完整的 2026 F22 公告事件窗不需重抓。

我另以同一 `.venv-scrapling` 的普通 `Fetcher.get` 對 7710／2026-07 F22 明細做單次 GET（不使用 stealth headers、proxy 或 challenge 處理）。MOPS 回 HTTP 200、6,465 bytes；回應包含本月欄、單位「新台幣仟元」及 352,807，沒有安全拒絕頁。這證明 Scrapling 可以直接讀明細值的 URL，不只事件查詢頁；單次成功不代表 375 頁已完成，也不據此繞過任何後續 403／429／安全拒絕。

未來再用此腳本前，應補強兩個收據邊界：目前 HTTP 200 後即標成功，即使 JSON decode 失敗也可能以空 `parsed_json` 寫出零列成功收據；另外 `acquired_at_*` 在發送請求前記錄，代表請求開始，不是 body 完成時間。本次既有 120 份產物經獨立重解析後沒有此類列數差異；這是未來執行的程式護欄缺口，不推翻本次已核實產物。

### 251 列「本機無值」的可取得性核對

問題清單中的 251 個 F22 URL 都指向具體公司與月份，且帶有 F22 公告時間。這表示「本機原件／值缺失」，不等同「MOPS 沒有資料」。本次從 251 個 URL 開始直接核對；前 100 個嘗試中，**88 個頁面呈現該月份營收表格，12 個頁面回傳 MOPS 安全拒絕頁**，其餘 151 個未嘗試。已呈現頁面單位均標示新台幣仟元，且同時顯示功能性貨幣與換算率；例如：

| 公司／月份 | MOPS 新台幣本月值（仟元） | 功能性貨幣／換算率 |
|---|---:|---|
| 1591／2026-07 | 42,489 | 新台幣／1.0000 |
| 1591／2026-08 | 53,841 | 新台幣／1.0000 |
| 1590／2026-07 | 3,994,281 | 人民幣／4.7520 |
| 1590／2026-08 | 3,707,549 | 人民幣／4.7541 |
| 5543／2026-07 | 273,764 | 新台幣／1.0000 |
| 5543／2026-08 | 227,256 | 新台幣／1.0000 |

安全拒絕自 2248／2026-07 開始出現，錯誤頁明示「因為安全性考量，您所執行的頁面無法呈現」。這是此次瀏覽存取遇到的技術限制，不代表相關公告不存在；本次沒有嘗試繞過，也沒有把安全拒絕列標成「無資料」。完整尚未查核範圍為 12 個安全拒絕頁及 151 個未嘗試頁。

正式 SQLite 唯讀查詢 `fundamental_monthly_revenues` 得到 2026-07、2026-08、2026-09 **各 0 列**。因此這 251 列目前不可能由正式月營收表顯示；它們不能靠改善日期 mapping 解決，必須先有對應數值資料進入隔離候選／適用的來源版本，再按既有流程評估是否投影到正式資料。這次只觀察頁面 DOM，未保存這 88 頁完整 HTTP response bytes／headers／hash，因此沒有產生可匯入的正式候選包。

### 舊快照衝突、選擇頁與 DB 對照

- 32 列「數值不同」與 1 列「數值相同」的既有 MOPS 明細原件均有 SHA；逐筆比對的本月數值與原始明細相符。對應正式 SQLite 的 33 列舊快照值亦逐筆相同，來源版本為 `mops-static-snapshot-monthly-revenue-2026-06-16`、品質為 `degraded`。這支持「舊快照列不能被晚期公告覆寫」；**不支持將較晚的更正版本永久排除**。更正應保留獨立修訂與公告事件時間，再建立新版本候選。
- 4 列 3712 回應是選擇／中介頁，不能當單一營收明細值套用；應待其指向的實際發行人／報表明細能精確確認後處理，不應推廣成所有投控公司資料都不可取得。
- 正式庫本次未被修改；沒有建立修訂 2、沒有解除正式 degraded，也沒有聲稱頁面已修復。這些限制是本次資料庫寫入授權與原件保存範圍的邊界，不是「不信任 MOPS」或「來源條款未定」的結論。

## 修正後結論與下一步

原報告把 325 列說成完整裁決、把 251 列「本機沒有原件」直接排除、把 37 列一概標為單位待核，這三項說法均不成立。Scrapling 事件批次已精確核對全部 412 個事件時間與明細 URL；MOPS 明細頁另可直接補出至少 88 個無本機值列的當期頁面值。OpenAPI 37 列中有 35 列目前與 MOPS 新台幣仟元欄一致、1 列 OpenAPI 空值但 MOPS 有值、1 列實際數值衝突；正式 DB 目前沒有 2026-07 至 2026-09 的月營收列。

尚未完成的是一次取得並保存覆蓋 2026-07 至 2026-09 的官方數值資料集，核明其對 251／124 個目標鍵的實際覆蓋，再以少量分層樣本驗證值欄與單位；對未覆蓋鍵及 5543 數值差異等例外再逐列取證。之後才按來源版本與產品資料流程接線。MOPS 事件時間沿用問題清單與已核 raw event；時間本身不會產生營收列，也不能把目前明細頁值冒充歷史原公告版本。瀏覽器批次遇到安全拒絕後不再重複請求；已驗證 Scrapling 單頁普通 GET 可取明細，後續按有界的來源批次與抽樣策略執行，收到拒絕即停止。

## 2026-10-28 月營收排程與全市場快照線路複核

更新依使用者要求核對每日排程、MOPS 數值抓取與 Update Tab，未使用問題清單逐筆重抓。截圖顯示正式 `fundamental_monthly_revenues` 最新期為 2026-06、MOPS 靜態候選至 2026-08；本次唯讀重查正式 DB，2026-07 至 2026-09 仍各 0 列。

每日快速排程 wrapper 預設傳入 `--capture-monthly-revenue-research-candidate`，只有 `BALDR_CAPTURE_MONTHLY_REVENUE_RESEARCH_CANDIDATE=0` 停用。10/28 實際排程收據證明它確有呼叫 TWSE／TPEx OpenAPI，兩份回應均 HTTP 200 並完整保存；候選期別為 2026-09，分別 1,088／893 原始列。但子流程最後標 `rejected`，因把報表層級 `出表日期` 交給 issuer-period announcement availability builder，造成「availability coverage is incomplete」後整份候選不發布。故排程有抓當期值，卻把值候選與 PIT 日期資格綁成同一成功條件；該 OpenAPI 子步驟並不補 2026-07 至 08 舊月，也不寫正式月營收表。Windows 工作排程管理器查詢在此環境被 CIM 權限拒絕；日誌與 receipt 證實實際執行，但不能據此證明之後每次排程都會成功。

另以既有 `scripts/fetch_mops_monthly_revenue_snapshot.py` 對官方 MOPS 靜態端點作一次全市場、三月份、兩市場的批次擷取，未抓 F22 單股頁；候選與原始 HTML 僅存於隔離 Codex visualization scratch，沒有寫入正式 `OUTPUT_ROOT` 或 SQLite：

- 2026-07 至 09 合計 **5,585 列**；各期 TWSE 996 列，TPEx 865／866／866 列；期間／市場／代碼鍵皆唯一，本月值皆非空，6 份原始 HTML 零 parser diagnostics。
- 對 251 筆「已審來源仍缺值」清單以 `(stock_code, period)` 批次比對，命中 **3 列**，即 TWSE 7710 的 2026-07、08、09；另 124 列 OpenAPI 單位／版本待核項目在此 MOPS 靜態快照命中 0 列。這表示 MOPS 大盤資料可補部分現況數值，但不是 375 個目標鍵的通用來源。
- 官方 F22 事件時間仍是另一個取得管線。此次快照回應於 2026-10-28 UTC 完成（台北時間 10/29），`source_available_at` 是本次來源回應完成時間；不得把它當成 2026-07 至 09 歷史決策時已可得時間或直接生成 PIT mapping。
- `plan_current_revenue` 與 CLI preview 對 CSV／6 份原件、hash、期別、市場、千元單位及列數全量重驗通過：5,585 個營收列轉成 11,146 筆現況觀測（含同期比較列），`formal_pit_eligible=false`、`formal_monthly_table_written=false`。preview 明確回報 `database_written=false`。
- 對該精確候選執行既有 `scripts/apply_current_monthly_snapshot.py --apply` 時，安全 preflight 因 DB 磁碟可用空間 **173,657,477,120 bytes**，低於既定 **214,748,364,800 bytes** 保留線而阻擋；收據為 `status=blocked`、`database_written=false`。寫入前後唯讀核對此候選的 `fundamental_current_observations` 列皆 0，正式 7–9 月表也仍 0。未改用 UI 服務繞過容量／共享鎖，也未降容量底線。

Update Tab 已將「正式歷史回填」與「只更新現況研究」分開；CSV 改用選擇器、版本標籤唯讀且無法辨識時清空，正式寫入按鈕只有在同一組輸入通過 dry-run 後才啟用，輸入路徑或檔案內容改變即失效並要求重檢。另補上 UI 現況觀測寫入的 200 GiB 容量預檢與共用 heavy-chain 鎖，避免 GUI 路徑繞過安全 CLI；manual 已同步[操作說明](../07_guides/APPLICATION_MANUAL.md#42-快速更新與安全更新)。自動驗證：Update Tab UI **98 passed**、current materialization／service guard **9 passed**、validator **25 passed／0 failed／4 skipped**、修改檔 `py_compile` 與 `git diff --check` 通過；repo-wide mypy 未能開始檢查本次修改，因既存 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤使整批 mypy 退出。正式 2026-07～09 月營收列、公告 mapping、PIT／Gate 未變；原生 GUI／Owner UAT 未執行。

### 2026-10-28 容量阻擋與 2020–2025 公告批次複核

使用者指出固定 200 GiB 保留線不應阻擋三個月的小批次後，將「只更新現況研究」的容量檢查改為動態預留：完整 SQLite 備份大小加 64 MiB 備份餘裕；資料庫所在磁碟再加 max(256 MiB, DB 大小 5%) 交易餘裕；備份與 DB 同磁碟時兩者合併計算。仍保留完整 SQLite backup、`quick_check`、共用 heavy-chain 鎖及不足容量時拒寫。正式歷史回填未調整。

另唯讀檢查 `output/mops_harvest_2020_2025`：864 個 MOPS F22 查詢窗口均為 HTTP 200；`manifest.csv` 合計 134,981 列與 `events.csv` 列數相同，單窗口最高 798 列；864 份 raw JSON 均存在且 manifest 的 byte count／SHA-256 全部吻合。事件涵蓋公告日 2020-01-02 至 2025-12-23，月營收期別 2015-07 至 2025-11；上市 74,306 列、上櫃 60,675 列，事件鍵無重複。12 列沒有公告時間，只有公告日期；本批 `is_correction` 為 false 的列不代表公告系統沒有更正，需按公告標題／逐公司事件再判定。這是公告事件資料，不包含月營收數值。可用來建歷史公告候選，但在接正式 availability mapping 前仍須按 `(stock_code, period)` 對齊目標數值版本；沒有對應來源版本的時間證據不能直接解除 PIT degraded。

此時再次唯讀查詢正式 `fundamental_monthly_revenues`，2026-07～09 仍各 0 列；但現況觀測表已有 2026-07 的 1,851 筆與 2026-08 的 8,279 筆（其中含多個 source version），2026-09 為 0 筆。故原先「7～9 都未進任何資料表」不再符合目前讀回狀態。新的 7～9 月 MOPS 現況候選與既有 7、8 月數值大多相同，少數列不同；寫入前應以版本化現況觀測保留差異，不能把這批晚期快照回填成歷史正式 PIT。資料庫本次只讀，未執行現況寫入。

後續依使用者明確授權，以 `scripts/apply_current_monthly_snapshot.py --apply` 使用按批次容量預檢及既有共用鎖完成 2026-07～09 現況觀測追加。備份 `current-revenue-before-6181f48ee518475db77307a62220f2ba.sqlite` 完成 `PRAGMA quick_check=ok`；收據 `current_monthly_applied_202607_202609_20261028_capacity_adjusted.json` 為 `status=applied`、`database_written=true`，新增 11,146 列。依原件版本讀回核對六個市場／月份值群共 5,585 個營收值，空值 0；正式 `fundamental_monthly_revenues` 的 7～9 月仍為 0 列，現況觀測不具有歷史 PIT 資格。UpdateService 狀態讀回已是目前查閱期別 2026-09、現況觀測 24,972 筆、歷史 PIT 至 2026-06。F: 可用空間原約 172.8 GB；本次實際備份 4,131,082,240 bytes，固定 200 GiB 底線已移除，改按完整 DB 備份及交易空間動態預留。

同日對容量修正執行 current materialization 測試 **10 passed**、Update Tab UI **98 passed**、Update validator **25 passed／0 failed／4 skipped**、定向 mypy 3 個 Python 檔 clean、`py_compile` 與本次檔案 `git diff --check` 通過。原歷史 200 GiB guard 測試已替換為「低於 200 GiB 但可容納本次完整備份與交易時允許寫入」及「實際備份空間不足時先拒寫」。

候選 CSV：`C:\Users\archi\.codex\visualizations\2026\10\26\01a176a6-e5cf-7a92-8d1e-e77dc2eba235\monthly_revenue_mops_snapshots_20261028\captures\run_2026-10-28_afab3676ee9b4c2fbcb4e2a89971e4a5\mops_monthly_revenue_snapshot_2026-07_2026-09_2026-10-28.csv`；apply 阻擋收據：`...\current_monthly_applied_202607_202609_20261028.json`。

### F22 明細值分層抽查補充

另以普通 HTTP GET 讀取官方 F22 公司／月份明細頁，保存 18 份原始 HTML、HTTP 狀態、byte count 與 SHA-256。其中 12 筆按 2020–2025 年、上市／上櫃各抽一筆，另 6 筆是代表性正式列。18/18 頁均 HTTP 200；頁面公司代碼、公司名稱／市場、期別、`本月` 欄與「新台幣仟元」單位均符合目標鍵，頁面值與正式 SQLite 相同 `(stock_code, period, source_version)` 數值完全一致，沒有抽樣差異。12 筆分層樣本每年涵蓋兩市場；另 6 筆為 2330／2020-10、2330／2024-12、6443／2025-01、6488／2025-11、6884／2025-11、6743／2024-01。18 個目標鍵各自只對到一筆保存的 F22 事件；16 筆事件有時分，6884／2025-11 與 6743／2024-01 只有公告日期。

**判定：抽樣通過值一致性核對，但本次解除 `degraded` 為 0 列。** 明細頁是本次重新取得的現行頁面，不是公告當時封存版本；事件鍵唯一、一般公告標題及更正關鍵字未命中，且在已保存的 2026 F22 harvest 中未找到這 18 個鍵的後續事件，仍不足以證明 harvest 涵蓋所有更正，也不足以證明目前頁值就是初始公告值。尤其本報告前段已核到 32 筆正式舊快照值與現行 MOPS 頁面值不同，證明來源確有值版本差異；事件標題未標更正，不能取代修訂沿革。18 筆結果不能外推到其餘約 126,881 列。正式資料的 `announced_date` 仍為空；候選 mapping 不會改寫正式列，quality reader 的缺公告日統計也不因 mapping 而消失。正式 SQLite provider 需要公告日、可得日及精確 `target_source_version` 對齊；quality 又會傳入月營收因子品質，因此只改 quality 標籤不能替代 PIT／修訂核驗。舊快照數值的可得時間不得早於其 2026-06-16 捕獲後的可得日。

抽查原始收據（HTML 與 manifest）保存在 Codex visualization scratch：
`C:\Users\archi\.codex\visualizations\2026\10\26\01a176a6-e5cf-7a92-8d1e-e77dc2eba235\mops_f22_stratified_value_spotcheck_20261028_2a57e77e`（12 筆分層樣本）及 `C:\Users\archi\.codex\visualizations\2026\10\26\01a176a6-e5cf-7a92-8d1e-e77dc2eba235\mops_f22_value_spotcheck_20261028_a317194a`（6 筆代表性樣本）。本次只讀查核，沒有寫正式 availability mapping 或 SQLite。

另為 18 筆建立隔離 candidate 與 partial-scope manifest，執行兩次 `scripts/apply_monthly_revenue_recovery.py` 唯讀預覽，沒有執行 `--apply`：

- 將靜態數值版本可得日設為快照規則推得的 2026-06-18：mapping merge 本身 18 added／0 conflict，但 availability validator 對 18/18 列判為 `available_date_unreasonably_late`（資料期末後超過 45 日），`ready_for_apply=false`。
- 將可得日設為 F22 公告日 + 1：mapping merge 0 diagnostics，但 backfill 對 18/18 列判為 `snapshot_capture_after_available_date`（2026-06-16 靜態快照晚於每筆聲稱可得日），`ready_for_apply=false`。

因此正式管線不接受「晚期快照數值 + 原始公告日」直接組成同一 PIT 列，這個 fail-closed 是目前可重現的阻擋。解除需提供公告當時封存的數值版本／明確修訂時間線，或另行設計並驗證「只在快照捕獲後可用」的版本契約；不能把 `available_date` 倒填為公告後一天，也不能單純放寬 45 日限制。candidate、accepted snapshot、scope manifest、18 列雙時點 dry-run 輸出均留在上述 `mops_f22_value_spotcheck_20261028_a317194a\formal_candidate_18` scratch。正式 DB 仍為 126,899/126,899 degraded，本次正式 degraded 解除數為 **0**。

### 2026-10-28 靜態數值快照與 F22 全量鍵交叉核對

找到正式資料根保留的官方 MOPS 原始 CSV：`F:\Min\Python\Project\FA_Data\output\monthly_revenue_mops_snapshots\mops_monthly_revenue_snapshot_2014-04_2026-05_2026-06-16.csv`。SHA-256 為 `1efc088ad72b81beb55b779281e76535e41aeecf097fd9b9bbad71702dccf025`，244,499 列、244,499 個唯一 `(stock_code, period)` 鍵、1,848 家公司、2014-04 至 2026-05 連續 146 個月份；營收欄無空值。CSV 本身沒有單位欄；18 筆 F22 明細抽查都顯示新台幣仟元並與該快照值相同，但不能把這 18 筆說成逐列 F22 值核驗。

正式 SQLite 中，這 244,499 個快照鍵的營收值全部逐列相同；另有 1,832 個正式庫鍵不在此 CSV，均為 2026-06。2020-01 至 2025-12 子集為 126,899 列、1,848 家、72 個月份，全部仍是 `quality=degraded`、`announced_date=NULL`，且使用正式版本 `mops-static-snapshot-monthly-revenue-2026-06-16`。原 CSV 的列版本卻是 `mops-static-2026-06-16`，因此不能忽略版本標籤差異或直接假設 writer 會產生既有 target version。

將全量 F22 事件以 `(stock_code, period)` 和快照鍵比對，事件鍵交集 **126,595**、未命中 **8,386**；其中 8,368 個未命中鍵的 140 個代碼整體不在快照，另有 18 個鍵是快照雖有該代碼但缺該期別（4195 有 17 期、5475 有 1 期）。故正式列中有 **304** 個公司／期別鍵沒有 F22 事件。交集有 144 筆市場標籤不同，集中於 5236、8908；這些代碼／期別鍵及值存在，市場差異不能當成資料缺列，也不應猜測原因。2020–2025 harvest 的 126,595 個匹配鍵與已保存的 2026 F22 harvest 19,983 個唯一鍵再比對，後續同鍵事件 **0 筆**；這降低了可見的重複事件，但不代表 MOPS 明細沒有被修訂。

快照 CSV 的 `fetched_at` 換算台北日期為 2026-06-17；目前 `_snapshot_session_available_date()` 對 date-only 資料採台北日的下一個曆日，故來源程式規則推得數值快照首次保守可用日為 **2026-06-18**。正式 SQLite 目前存為 2026-06-17，早一天，需由正式資料 owner／既有 recovery 流程裁定修正，不能由 F22 公告日期替代數值快照可得時間。

**本次仍未批次解除 degraded。** 全量鍵交集證明公告事件和同公司／期別的靜態數值可對齊，且原始 CSV 與 DB 數值相同；但事件檔沒有數值，目標版本字串不同，CSV 無單位欄，現在的 F22 明細頁也不是公告當時版本。已知 32 筆正式舊快照值與現行明細不同，證明存在版本差異；只用首次公告時間映射至舊 snapshot 會把修訂語意混在一起。要安全減少這 126,899 列的 degraded，仍須定義 snapshot source-version normalization／exact target-version writer，將可見公告與具體數值版本分開保存，處理 32 筆已知差異、144 市場標籤差異及 304 個無事件正式鍵，並讓 candidate／partial-scope manifest、backup、SQLite readback 與品質摘要按同一版本契約通過。僅重抓公告事件不會補上數值版本橋。本節唯讀，未新增 mapping、未改正式 SQLite。

## 2026-10-29 正式回填與讀回

依使用者授權，完成 2020-01 至 2025-12 固定 MOPS 數值快照回填。先前段落記載的「正式庫 126,899/126,899 degraded」「解除 0」及「304 個正式列缺事件」是寫入前歷史狀態，現由本節更新；304 是混用母體後錯算。正確 crosswalk 為 126,899 個目標鍵中 126,518 個找到事件；排除 15 個公告晚於 snapshot available date、144 個市場標籤不一致後，126,359 個公告 mapping 可正式套用。其餘 540 列由 381 個無事件、144 個市場不一致及 15 個晚期事件構成，保留 degraded。

18 筆按年度與市場分層的 MOPS F22 明細抽樣全部核對公司／期別／新台幣仟元單位／本月值。寫入前固定 CSV 與同版本 SQLite 的 126,899 列數值逐列相同；writer 交易內再次以來源版本及 `Decimal` 值做相等守衛。寫入後正式 recovery receipt 為 `applied=true`、無衝突；精確 source version 與 2020–2025 範圍的 SQLite 分組讀回：`observed` 且有公告日、`available_date=2026-06-18` 共 **126,359**；`degraded` 且無公告日、同 available date 共 **540**。所有 126,899 個數值列保持原值；只有 availability／quality mapping 狀態被更新。

公告時間與數值 snapshot 可得時間是不同欄位。此次 126,359 列公告日只是事件證據；其較晚取得的固定數值 snapshot 統一從 2026-06-18 起可用，不回填為公告當日 PIT 值。9 列有公告日期但無時分，`announced_at` 保持空值。15 個晚於快照可得日的事件不套用，避免公告事件晚於數值版本的反向連結。

Recovery receipt：`C:/Users/archi/.codex/visualizations/2026/10/26/01a176a6-e5cf-7a92-8d1e-e77dc2eba235/mops_snapshot_recovery_2020_2025_20261028/recovery_applied.json`。完整 DB 備份為 `F:/Min/Python/Project/FA_Data/meta_data/backup/twstock_mops_monthly_revenue_backfill_20261029T025431Z_03f74e34b9ef48919eb7497de141426d.db`；mapping 原件備份為同目錄 `monthly_revenue_availability_monthly_revenue_merge_20261029T025431Z_d30c093674ce44b89f0de7d551840045.csv`。writer 建立的備份通過 `PRAGMA quick_check`；完整 live DB 的 post-write quick_check 因耗時未完成，因此此 QA 不宣稱 live quick_check 通過。定向測試 43 passed、1 skipped、1 deselected；修改 Python 檔 `py_compile` 通過。

正式狀態已更新，但 540 列仍需事件補齊或市場標籤／晚期版本的可靠裁決後才可能解除公告品質 degraded。18 筆抽查是值解析／單位 sanity check；它不等於逐頁重查全部列，也不改變 snapshot 只從 2026-06-18 可用的時間限制。

## 2026-10-29 全歷史 harvest 與正式資料狀態複核

使用者提供的 harvest 完成摘要經唯讀核對：`output/mops_harvest_2014_2019` 為 816/816 窗口 HTTP 200、111,872 events；2020–2025 為 864/864、134,981 events；2026 為 120/120、19,983 events。三批共 1,800 個 raw JSON 的存在、byte count、SHA-256 與 manifest 列數均吻合，events 合計 266,836 筆。公告事件原件確已完整取得，可作為事件核對候選來源；但這些 harvest 不含公告數值或單位，原件完整不等於資料值逐列正確，也不等於可直接寫入所有 availability mapping。

### 對 Gemini 統計的修正

- 三批 `is_correction` 旗標皆為 false，公告主旨更正關鍵字亦未命中。報告所稱 4,115 筆更正是以「期別到公告日 lag 超過一個月」推算；這只能標記延後公告候選，不能定性為更正／重編。
- 2014–2019 有 6 筆、2020–2025 有 12 筆、2026 有 2 筆沒有 `announced_at`，共 20 筆僅有公告日期，不能稱所有事件都有秒級 timestamp。
- 事件 harvest 範圍不是數值 coverage 本身；2014–2019 harvest 的營收期別為 2012-01..2019-11，2019-12 事件需併用後續 harvest。

### 正式 DB 與事件鍵交叉盤點

唯讀 DB 查詢的 source version 為 `mops-static-snapshot-monthly-revenue-2026-06-16`，現有 `degraded` 共 116,291 列：

| 範圍 | DB degraded | 事件鍵命中 | 缺事件 | 狀態 |
|---|---:|---:|---:|---|
| 2014-04..2019-11 | 106,698 | 106,415 | 283 | 尚未回填；現有 available_date 為 2026-06-17 |
| 2019-12 | 1,662 | 1,657 | 5 | 不在 Gemini 宣稱的 2014-05..2019-12 公告視窗範圍內，需明確併案 |
| 2020-01..2025-12 | 原始範圍 126,899 | 126,359 已寫入 | 540 仍 degraded | 已依前節完成受限回填 |
| 2026 年 | 7,391 | 尚未完成全範圍安全寫入判定 | — | 需按 available_date、值版本與市場標籤再裁決 |

2014-04..2019-12 共 108,360 列中有 108,072 個公司／期別事件鍵命中，288 列缺事件。缺口集中於 2867、4130、5371、8183（各長期缺期）與 6806（2019-01..11；2019-12亦在 5 列缺口中）。這些代碼需核對公司歷史／市場與 harvest scope，不能為追求 100% 直接補假事件。跨全部 degraded 列，有 37 個匹配事件日期晚於現有 available_date，不可只憑 key match 套用。

### 寫入前尚缺的證據

2014–2019 的年度／市場 MOPS 明細值抽樣尚未完成：專案 runtime 對普通官方 F22 明細 GET 嘗試 7 次均未取得頁面，錯誤為 DNS 解析失敗／連線逾時；web open 亦回報 endpoint 不可存取，沒有使用登入、challenge 或繞過方式。這是本機網路取證限制，不能推論 MOPS 拒絕存取。事件 raw 與 target key 已核對，仍未以這批年份的代表頁確認數值解析／單位；故本次沒有對 2014–2019 執行正式 mapping／SQLite write。唯讀 recovery dry-run 已完成：108,360 列同版 DB 值逐列相等，0 duplicate／invalid／unmatched／conflict／diagnostics；107,934 列可建立公告 mapping，426 列保留 capture-only baseline（288 無事件、138 市場標籤不一致），`ready_for_apply=true`。其正式列現有 `available_date=2026-06-17`，候選依固定快照契約採 2026-06-18 並驗證 row capture；在年度抽樣取證完成前沒有套用正式 DB。

前節「126,359 observed／540 degraded」只描述 2020–2025 已套用的固定範圍，不代表 116,291 全域 degraded 已清除。


## 2026-10-29 2014–2019 回填候選預檢

具名候選與預檢收據位於 `C:/Users/archi/.codex/visualizations/2026/10/26/01a176a6-e5cf-7a92-8d1e-e77dc2eba235/mops_snapshot_recovery_2014_2019_20261029/`。候選固定 MOPS snapshot SHA-256 為 `1efc088ad72b81beb55b779281e76535e41aeecf097fd9b9bbad71702dccf025`；正式 target source version 為 `mops-static-snapshot-monthly-revenue-2026-06-16`。108,360 列（2014-04..2019-12）同鍵數值與正式 SQLite 精確相同，且 event raw SHA、事件鍵唯一、mapping merge 0 conflict。預檢生成 107,934 筆正式公告 mapping 和 426 筆 snapshot-only baseline；後者含 288 無事件、138 市場標籤差異。candidate scope 的 recovery dry-run 無診斷且 `formal_apply_eligible=true`。

此 dry-run 不是 DB 寫入；2014–2019 的年度／市場值頁抽查因本機 DNS／連線不可用尚未完成，故候選保持隔離，正式列未更新。拿到可重驗的代表頁原件後，可直接重跑固定候選 preflight；不需要重抓已驗證的 1,800 個事件視窗。

## 2026-10-29 市場標籤裁決與最終剩餘缺口

後續 Scrapling ordinary `Fetcher.get` 成功取得 5236 凌陽創新與 8908 欣雄的 2014-04 MOPS F22 明細原始 HTML。兩頁均為 HTTP 200，明示「上市公司」、單位「新台幣仟元」；本月值分別為 89,869／490,546，與同鍵固定 snapshot、正式 SQLite 數值完全相同。保存原件及 manifest：`C:\Users\archi\.codex\visualizations\2026\10\26\01a176a6-e5cf-7a92-8d1e-e77dc2eba235\mops_market_label_adjudication_5236_8908_20261029\raw_f22_samples\`。兩個代碼的唯一 F22 事件鍵在 2014-04..2026-04 共 145 期／檔，事件市場均為 `sii`；靜態數值 CSV 的 market 欄卻標成 `tpex`。抽查頁與 event key 支持這是市場 metadata mismatch，不是公司／期別鍵不明，因此不再因該欄位不同而排除公告 mapping。

將 5236／8908 的 290 個唯一 `(stock_code, period)` mapping 候選從三個分段整合為一個 partial-scope batch。候選值與正式同版 SQLite 逐列相等，事件鍵唯一，公告皆不晚於 2026-06-18 snapshot 可得日，0 diagnostics／0 conflicts／0 unmatched，`formal_apply_eligible=true`。正式 apply 後兩家公司各 145 列 canonical target version 均為 `observed`，公告日期範圍分別為 2014-05-09..2026-05-06 及 2014-05-09..2026-05-08；兩組原營收值未變。

操作中曾以未正規化的 accepted snapshot row lineage 執行一次 apply，因 CSV 內版本字串不同而暫時新增 290 個 `|snapshot=mops-static-2026-06-16` 後綴版本。讀回發現 canonical 列仍 degraded 後，將候選 row lineage 正規化成精確 target source version，重新執行 guarded recovery 更新 canonical 290 列；再以明確 290 個 key、來源、值、公告日期、可得日及 quality 等值守衛，在 SQLite transaction 中只刪除該次建立的後綴 duplicate。最終讀回確認後綴版本列數為 0、canonical 290 列全部 observed。前次 apply 備份及更正後 apply 備份分別為：

- `F:\Min\Python\Project\FA_Data\meta_data\backup\twstock_mops_monthly_revenue_backfill_20261029T060214Z_11166204c6694b98905332c6c34d3a6b.db`
- `F:\Min\Python\Project\FA_Data\meta_data\backup\twstock_mops_monthly_revenue_backfill_20261029T060412Z_c9c79fdab0464a9b8e700a6e4bf6ba50.db`

更正後 recovery receipt：`C:\Users\archi\.codex\visualizations\2026\10\26\01a176a6-e5cf-7a92-8d1e-e77dc2eba235\mops_market_label_adjudication_5236_8908_20261029\recovery_canonical_applied.json`；mapping backup：`F:\Min\Python\Project\FA_Data\meta_data\backup\monthly_revenue_availability_monthly_revenue_availability_merge_20261029T060214Z_2fe5614dbfe449ce8b9f38fdab75846f.csv`。正式 mapping 與 DB 變更均使用 guarded recovery；最後 duplicate 清理為上述 key/value guards 下的單一 SQLite transaction。沒有對 live DB 宣稱完整 `quick_check` 通過。

### 最終正式庫讀回

| MOPS snapshot source version | observed | degraded | 說明 |
|---|---:|---:|---|
| 全資料庫 | 245,605 | 726 | 含其他來源版本；本批只改指定固定 snapshot |
| `mops-static-snapshot-monthly-revenue-2026-06-16` | 241,925 | 726 | 2014-04..2026-04 scope；每列 snapshot available date 為 2026-06-18 |

本批分段明細為 2014-04..2019-12 **108,072/288**、2020-01..2025-12 **126,503/396**、2026-01..04 **7,350/42**（依序 observed/degraded；最後一段包含 1 筆原先已 observed 列）。全批三段共 242,651 列。

剩下 726 列仍 degraded，原因可完整對上：**689** 個目標鍵在目前保存的 1,800 個 sii／otc harvest 視窗中無事件；**36** 個事件日晚於固定數值 snapshot 的 2026-06-18 可得日；**1** 個精確公告 timestamp 晚於該 snapshot row 的擷取時間。所有 290 個市場標籤 mismatch 已裁決／回填。另對 2026-10-01..10 的 sii／otc／rotc／pub 四個市場各作一次普通 EZSearch 查詢，五個長期缺事件代碼仍無命中；這只是該十日窗口的結果，不能外推為歷史期間不存在公告。689 列目前可見的主要代碼是 2867、4130、5371、8183、6806 與 21 個零星代碼；須補到對應期間公告事件，或判定該期確實沒有適用 F22，才可解除公告品質 degraded。36+1 列要有不晚於 snapshot／row capture 的同版本事件或數值版本證據；不能只放寬時間守衛。

因此這次已把整段官方固定數值 snapshot 以 2026-06-18 起可用寫入／校正，並把有唯一且時間安全的公告 mapping 轉為 observed；剩餘 726 列不會造成營收數值欄位消失，但公告完整性品質仍標 degraded。無事件鍵、晚公告鍵與任何修訂版本不能靠重跑相同的 1,800 個 harvest 窗口解決；下一步要查對缺期事件來源／適用性，及公告晚於數值擷取的來源版本沿革。

### 採集器可靠性修正與驗證

複核 harvest 程式時發現 HTTP 200 但 JSON 解碼失敗、頂層型別錯誤或 `data` 列表格式錯誤，先前可能被當成成功的空視窗。本次改為回報解析錯誤並進入既有重試；只有驗證成功的 HTTP 200 才寫入原件、manifest 與 checkpoint。另將 `acquired_at_utc`／台北時間移到回應解析成功後記錄，欄位代表回應取得完成時間；最終重試失敗時不再多等一次 15 秒。

驗證收據：受控 Windows Job Object（8 GiB 記憶體／12 程序上限，readback verified）內執行三個 Python 檔 `py_compile` 與指定測試，**43 passed、1 skipped**，exit 0。輸出位於 `C:/Users/archi/.codex/visualizations/2026/10/26/01a176a6-e5cf-7a92-8d1e-e77dc2eba235/mops_quality_tests_20261029/final_20261029T061235Z/`。這是程式與回歸測試通過；不代表正式 live DB 的完整 `PRAGMA quick_check` 已通過，亦不把有限測試外推成全產品 QA。

## 2026-10-29 每日 OpenAPI 候選保存修復與 7–9 月現況

正式 DB 唯讀讀回確認 `fundamental_monthly_revenues` 的 2026-07／08／09 分別為 1,861／1,862／1,862 列，合計 **5,585 列**；來源版本均為 10/28 MOPS static snapshot，數值 `available_date=2026-10-30`，`announced_date` 空白且品質 `degraded`。同鍵 F22 crosswalk 有 5,584 個唯一公告事件，缺少 6884／2026-08；事件 timestamp 留在 sidecar，正式表沒有 `announced_at` 欄。Crosswalk snapshot lineage 與這 5,584 列 DB source version 的 snapshot lineage 相符，但這不改變 numeric snapshot 於 10/30 才可見的界線；當時 5,585 列仍 degraded 是本次 apply 前基線，後續正式回填結果見下節。

10/27 與 10/28 排程收據顯示，TWSE 1,088 列與 TPEx 893 列 OpenAPI 原件皆 HTTP 200、hash 可讀；候選隨後將 `出表日期` 送入歷史公告日期 builder。該 builder 正確拒絕 TWSE／TPEx 的 report-level date 作為 issuer-period announcement evidence；候選程式卻將此預期拒絕升級為整批失敗，因而沒有保存 normalized snapshot CSV。修正後，daily capture 只保存原件與標準化研究快照；availability CSV 保留空表及明確狀態 `not_emitted_no_issuer_period_announcement_evidence`，manifest 記錄 report-level date 語義及擷取時間，不把它轉成 `announced_date` 或正式可得日。這個修正不會回寫 DB 或解除 7–9 月 `degraded`；須待下一次自然排程成功讀回候選，再核對正式 scheduler 註冊狀態。

回歸收據：歷史公告 builder＋候選／recovery／排程稽核 suite **86 passed、1 skipped**；Update Workbench **98 passed**；資料更新 tab validator **25 passed、0 failed、4 skipped**。本機排程狀態查詢回報 `TASK_NOT_FOUND_OR_SCHEDULER_UNAVAILABLE`，因此尚無法確認 Windows Task Scheduler 註冊是否有效。這一節記錄程式修正與現況讀回，不宣稱下一次排程已執行。

### 2026-10-29 F22 公告映射 guarded apply 與正式讀回

使用既有 `apply_monthly_revenue_recovery.py` 對 2026-07..09 執行 partial-scope apply：全 snapshot 5,585 列中，接受與唯一 F22 crosswalk 精確對應的 5,584 列，明確排除缺事件鍵 6884／2026-08。套用前唯讀 planner 確認 mapping 5,584 新增、0 conflict／diagnostic；snapshot accepted 5,584 列、source-version 全部與正式 DB 完整版本字串一致、`formal_apply_eligible=true`。mapping 的 `available_date` 固定為 2026-10-30，公告日／秒級 `announced_at` 只作事件沿革，不提前數值可見日。

正式 apply receipt：`.tmp_mops_recovery_20261029/recovery_f22_v2.json`，status `applied`、mapping added 5,584、normalized 5,584、excluded 1、rollback false；mapping SHA 從 `fdd95f3c0a75c3c9395d045295dbd62962f9295a7610c78fb8adccd0e0a73b7e` 更新至 `46c4859f15ad458bf1db64900de55f2de4f238c28be980e730dfc4befa9113e4`。guarded writer 以 SQLite online backup 先保存正式 DB（約 4.15 GB），並在 transaction 內要求 source／Decimal 值相等、保留 `created_at`；本次 numeric value mismatch 0、event date／available date／quality mismatch 0。

讀回正式 SQLite 與 mapping 後，7 月 1,861 列、8 月 1,862 列、9 月 1,862 列中 5,584 列為 `observed`，6884／2026-08 1 列仍 `degraded`；全正式月營收表 251,189 `observed`／727 `degraded`。品質 reader 的 7／8／9 月 missing announcement count 為 0／1／0。唯讀 `FundamentalSQLiteProvider` 驗證 2330：decision date 10/29 最新仍是 2026-06；10/30 才選到 2026-09、`available_date=2026-10-30`、announcement date 10/08。故本次確認頁面最早於 10/30 顯示 7–9 月；沒有提前曝光。完整 raw crosswalk、候選與 backup／receipt 均留在被忽略的 `.tmp_mops_recovery_20261029/` 任務 scratch，不納入 Git。

針對剩餘缺口，另以 Scrapling 一般 POST 查 OTC F22 的 2026-09-01..15 視窗；HTTP 200、907 筆，沒有 6884／115 年 8 月事件。原始回應保存在 `.tmp_mops_recovery_20261029/mops_f22_otc_20260901_15_6884_check.json`，SHA-256 `1f55e1b4c4e187bf1ceeb0f76fab725220560af7704e37be96cd971ec5500623`。這是限定半月窗口的抽查；完整 2026 harvest crosswalk 亦沒有 6884／2026-08，只有 2026-07 與 2026-09 兩期事件。由於缺少該期公告 event，不推造公告日；該一列維持 `degraded`，後續若有可核實 MOPS 公告原件可再建立新 mapping revision。
