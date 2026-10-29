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

### 2014–2019 官方明細年度／市場抽樣補驗（2026-10-29）

為補上舊版 QA 所列的年度值頁抽查缺口，從 2014–2019 SII／OTC F22 harvest 中每年各選一筆上市、一筆上櫃明細，共 **12 頁**；以 Scrapling `Fetcher.get` 普通 GET 取得。11 頁首取 HTTP 200，2018／9960 首次逾時後只重試一次並 HTTP 200；沒有使用 Remote Desktop、代理或 challenge 處理。12 頁都核對公司名稱／代碼、民國期別、單位「新台幣仟元」及「本月」欄；**12/12 本月值與固定 MOPS snapshot 完全相同**，原始 HTML SHA-256 讀回一致，無拒絕頁或數值差異。

樣本：1762／2014-05=94,471、6175／2014-10=154,956；1707／2015-02=463,368、3581／2015-02=43,491；2547／2016-11=338,413、3594／2016-02=86,094；2477／2017-06=277,316、3272／2017-04=261,784；1516／2018-12=30,343、9960／2018-11=44,574；2029／2019-04=892,533、4580／2019-06=171,611（單位均為新台幣仟元）。原件、逐列 SHA／manifest 與 readback receipt 保存在 repo ignored scratch：`.tmp_mops_historical_spotcheck_2014_2019/`。

此抽樣補足 2014–2019 的 F22 公司／期別、單位與目前頁面值解析 sanity check；不外推為 108,360 列逐頁驗證，也不證明目前明細頁是原公告當時版本。固定 snapshot 與正式 DB 全列同鍵數值相等、該範圍 108,072 `observed`／288 `degraded` 的 guarded recovery 已另行完成；剩餘 288 列沒有已保存的精確公告事件，不能由值頁抽樣替代公告時間證據。舊段落記錄的是當時尚未完成抽樣／回填的歷史狀態，現況以本補驗及本節後續 guarded apply／readback 收據為準。

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

10/27 與 10/28 排程收據顯示，TWSE 1,088 列與 TPEx 893 列 OpenAPI 原件皆 HTTP 200、hash 可讀；候選隨後將 `出表日期` 送入歷史公告日期 builder。該 builder 正確拒絕 TWSE／TPEx 的 report-level date 作為 issuer-period announcement evidence；舊候選程式卻將此預期拒絕升級為整批失敗，因而沒有保存 normalized snapshot CSV。修正後，daily capture 保存原件與標準化研究快照；availability CSV 保留空表及明確狀態 `not_emitted_no_issuer_period_announcement_evidence`，manifest 記錄 report-level date 語義及擷取時間，不把它轉成 `announced_date` 或正式可得日。此修正不回寫正式 DB；10/29 手動 CLI capture 已以新程式成功讀回，結果及 scheduler 現況見下方「10/29 排程與修復後候選實跑」。

回歸收據：歷史公告 builder＋候選／recovery／排程稽核 suite **86 passed、1 skipped**；Update Workbench **98 passed**；資料更新 tab validator **25 passed、0 failed、4 skipped**。Task Scheduler 註冊後以其本機 XML 與逐次 capture receipt 重新核實，結果見下方；Task Scheduler Operational event log 權限不足，因此不宣稱已取得 Windows event log 層級的啟動主體證明。

### 2026-10-29 F22 公告映射 guarded apply 與正式讀回

使用既有 `apply_monthly_revenue_recovery.py` 對 2026-07..09 執行 partial-scope apply：全 snapshot 5,585 列中，接受與唯一 F22 crosswalk 精確對應的 5,584 列，明確排除缺事件鍵 6884／2026-08。套用前唯讀 planner 確認 mapping 5,584 新增、0 conflict／diagnostic；snapshot accepted 5,584 列、source-version 全部與正式 DB 完整版本字串一致、`formal_apply_eligible=true`。mapping 的 `available_date` 固定為 2026-10-30，公告日／秒級 `announced_at` 只作事件沿革，不提前數值可見日。

正式 apply receipt：`.tmp_mops_recovery_20261029/recovery_f22_v2.json`，status `applied`、mapping added 5,584、normalized 5,584、excluded 1、rollback false；mapping SHA 從 `fdd95f3c0a75c3c9395d045295dbd62962f9295a7610c78fb8adccd0e0a73b7e` 更新至 `46c4859f15ad458bf1db64900de55f2de4f238c28be980e730dfc4befa9113e4`。guarded writer 以 SQLite online backup 先保存正式 DB（約 4.15 GB），並在 transaction 內要求 source／Decimal 值相等、保留 `created_at`；本次 numeric value mismatch 0、event date／available date／quality mismatch 0。

讀回正式 SQLite 與 mapping 後，7 月 1,861 列、8 月 1,862 列、9 月 1,862 列中 5,584 列為 `observed`，6884／2026-08 1 列仍 `degraded`；全正式月營收表 251,189 `observed`／727 `degraded`。品質 reader 的 7／8／9 月 missing announcement count 為 0／1／0。唯讀 `FundamentalSQLiteProvider` 驗證 2330：decision date 10/29 最新仍是 2026-06；10/30 才選到 2026-09、`available_date=2026-10-30`、announcement date 10/08。故本次確認頁面最早於 10/30 顯示 7–9 月；沒有提前曝光。完整 raw crosswalk、候選與 backup／receipt 均留在被忽略的 `.tmp_mops_recovery_20261029/` 任務 scratch，不納入 Git。

針對剩餘缺口，另以 Scrapling 一般 POST 查 OTC F22 的 2026-09-01..15 視窗；HTTP 200、907 筆，沒有 6884／115 年 8 月事件。原始回應保存在 `.tmp_mops_recovery_20261029/mops_f22_otc_20260901_15_6884_check.json`，SHA-256 `1f55e1b4c4e187bf1ceeb0f76fab725220560af7704e37be96cd971ec5500623`。這是限定半月窗口的抽查；完整 2026 harvest crosswalk 亦沒有 6884／2026-08，只有 2026-07 與 2026-09 兩期事件。由於缺少該期公告 event，不推造公告日；該一列維持 `degraded`，後續若有可核實 MOPS 公告原件可再建立新 mapping revision。

### 2026-10-29 排程與修復後候選實跑

唯讀檢查 `C:\Windows\System32\Tasks\baldr-data-update-quick-daily` XML：task `Enabled=true`，每天 04:20，動作為 repo 的 `scripts/scheduled/run_daily_data_update_quick.cmd`。該 `.cmd` 預設加上 `--capture-monthly-revenue-research-candidate`，僅 `BALDR_CAPTURE_MONTHLY_REVENUE_RESEARCH_CANDIDATE=0` 才關閉；排程註冊及程式接線均存在。正式資料根 `output/scheduled/data_update_quick/research_capture_receipts/` 的最新排程收據為 10/28 run `20261028-36584`：Quick core `passed_with_warnings`，候選子程序 `rejected`，原因是舊版仍把報表層級 `出表日期` 當公告證據；最新排程收據檢查到 10/28 為止。10/29 00:33 PDT（07:33 UTC）在修復後直接執行同一候選 CLI 成功，這是在下一個 04:20 排程觸發前的手動驗收，不冒稱為 scheduler-launched run。

修復後 candidate run ID `20261029T073307505471Z-a444187d09724152bd139d827aacb11d`；manifest SHA-256 `afdb15d2d4fc5c790aa7c54ea76c88e1e385c8d45879d6c7c4c5548e9bded36b`，status `research_observation_only_created`／readback `verified`。TWSE HTTP 200／1,088 rows／607,634 bytes／SHA-256 `a58c04b3bdc2b94632027018ca4f09f6ad053848addb7b9580b372626542fc17`；TPEx HTTP 200／893 rows／496,597 bytes／SHA-256 `a27fea120daa8ef4543bcbf6e31426cad2e0201111ee8d97916fbb5fce2727a6`。標準化現況 snapshot 1,981 rows、hash readback 成功；availability 0 row 且 reason `not_emitted_no_issuer_period_announcement_evidence`。正式 apply、單位接受與 historical PIT 均為 false，無正式 DB 寫入。原件、candidate 與 receipt 位於 `output/fundamental_research_candidates/20261029T073307505471Z-a444187d09724152bd139d827aacb11d/`（repo `output` 本機產物，不納入 Git）。

#### 727 筆 degraded 現況的唯讀逐鍵分類

重新只讀查詢正式 SQLite，總數仍為 251,189 observed／727 degraded。逐列以 `(stock_code, period)` join 本機三批歷史 `sii`／`otc` harvest：**690** 無事件（既有 689 舊缺口加上 6884／2026-08 一筆）；**36** 有事件但 announced date 晚於固定 snapshot `available_date=2026-06-18`；**1** 為 8942／2026-04，事件 timestamp `2026-06-18T14:11:43+08:00` 晚於該列 snapshot capture `2026-06-16T23:02:24Z`。36 late-event keys 分布為 6111×9、3041×6、2392／2608／3712／6776 各×4、3437／3466／4304／5460／8101 各×1。晚期事件 raw 沒有對應時點數值或該版本 detail page；不能把後來公告日套到 6/16 舊數值列。

無事件缺口主要集中於 2867／4130／5371／8183 各 145 期、6806 共 88 期，另 21 個單筆鍵；目前抽到的 2026-04 明細頁三個值與正式 DB 一致、兩碼頁面顯示不再公開發行，但五頁都無公告日期／時間欄。EZSearch 的請求需區分市場模式與公司模式：`RADIO_CM=1` 是市場查詢，該模式下帶 `CO_ID=2867` 的 2014-05-12 查詢仍回上市市場 57 列，不能視為公司篩選；舊記錄 raw SHA-256 `f5a359438729571815e1a6f5c1bb5f38b32b3f928df39b129fa342de73a68265`。同一查詢介面的公司模式為 `RADIO_CM=2`，需先由 `step=05` 公司 autocomplete 選取代碼。2026-10-29 的 autocomplete 對 2867／5371／6806 均回空結果，正控制 2330 回傳台積電；以 2867 公司模式查詢 2014-05 則回「查無公司資料」。因此只能確認當前代碼選單／公司查詢未提供這些已下市代碼，不能推論 endpoint 完全不支援 `CO_ID`，也不能推論歷史公告不存在。另一個上市市場模式 2014-05-10..14 查詢回 62 列且無 2867，raw SHA-256 `0f24204adaf7ec8149aaf141f09b907a4a7a1a7e398fbd213584d8415686e450`；這些有限日期查詢不能代替歷史 crosswalk。

原三批歷史 harvest 僅涵蓋 SII／OTC。曾規劃以 10 秒限速、raw+SHA+manifest、checkpoint harvester 對 `rotc`／`pub` 做 2014–2026 全期 1,848 窗補採；先前僅對 6806／2019-02 做 12 窗試查。後續全期批次實際啟動後，在完成 **151 個 ROTC 窗**時停止：151/151 HTTP 200、0 rows，原始回應均為同一個 82-byte `查無公告資料` JSON（SHA-256 相同）；PUB 尚未開始。此結果只證明已查的 ROTC 窗回空，不能推論興櫃／公開發行全期沒有公告，也不能結案 689 個缺事件鍵。另以 Scrapling 在 OTC 市場模式查 2024-03-01..10，MOPS 回 `success`、746 筆；與本機同窗事件數相符，但沒有 4130。ROTC／PUB 自身的陽性控制仍未建立，因此未繼續耗費約 5 小時掃完其餘 1,697 窗；輸出目錄 `output/mops_harvest_rotc_pub_2014_2026/` 保留截至中止的原件、manifest 與 checkpoint。

#### 2026-10-29 公司模式正向控制與缺碼檢查

對五個主要長序列缺碼再核對 raw：2867、4130、5371、8183、6806 均未出現在三批 1,800 份 SII／OTC 原始 JSON 的 `data[].COMPANY_ID`，故不是 events.csv 正規化或期別 subject parser 漏列。已知上市正向控制 `2330` 的 MOPS autocomplete `step=05,inpuType=co_id` 回傳正常；同模式帶 `TYPEK=otc` 查 4130、帶 `TYPEK=pub` 查 6806，仍回空 `<div id="zoom"></div>`。把 4130 直接送入 `RADIO_CM=2`、OTC、F22、2024-03-01..10 公司模式後，MOPS HTTP 200 回 `status=fail`／`查無公司資料`；同窗 OTC 市場模式則成功回 746 列但沒有 4130。早先對 2867／5371／6806 的選單檢查亦回空；目前代碼選單不提供這些代碼，但不能因此推論歷史期間沒有 F22 公告。上述直接查詢只驗證當前選單行為，沒有寫入 DB。

這將 689 個無事件鍵的主要問題收斂到「目前 MOPS EZSearch 市場／公司選擇器及歷史申報範圍」而非本地事件解析。四個 145 期序列（2867／4130／5371／8183）與 6806 的 88 期數值仍存在正式 snapshot；現有 F22 事件路徑沒有對應公告時間。下一步應找能按歷史 issuer identity 回傳原始公告時間的 MOPS 歷史查詢／公告明細路徑，並先用正反控制驗證；未取得 issuer-period 時間證據前，維持 690 列 degraded，不以靜態 snapshot 的 report-level 出表日替代公告時間。

後續針對 6806 缺少 2019-01 期事件，以同一個有 10 秒間隔的 harvester 查 2019-02 全月、`rotc` 與 `pub` 各切六個日期窗，共 12 窗；全部 HTTP 200，MOPS JSON 均為 `status=fail`／`查無公告資料`，無事件列、無 6806 命中。這只表示該月份與兩市場查無資料，不能證明 6806 在該期不適用 F22，也不能替代其他月份或市場查詢。其 raw、manifest、checkpoint 保留於 `.tmp_mops_gap_probe_20261029/rotc_pub_2019_02_6806/`，未寫正式 SQLite。

故目前正式表 727 筆 degraded 中，690 筆仍缺可匹配公告事件；36+1 筆仍須版本同時點數值證據。現有證據不足以解除，不能以後來事件日期套用到舊 snapshot，也不能把目前未命中等同歷史不存在。一般個股研究報告會直接讀正式月營收列，按 snapshot 已知單位顯示原值、期別、可得時間及品質／來源限制；因子／策略使用的 `FundamentalSQLiteProvider.load_monthly_revenues` 則要求正式 availability mapping 與公告日通過 PIT 防線，未映射列會被排除。因此 degraded 數值在一般明細有顯示路徑，但仍不會進嚴格 PIT 因子／策略。應按缺口公司／期別找可用的歷史公告原件或公告當時頁面；缺期是否適用申報則須以該公司當時掛牌／申報身分判斷。

#### 五筆 late-event 同值候選的官方明細反證

曾有 5 筆 late-event 列的後續官方月報「去年同月」欄與固定 snapshot 值相同，故先列為待確認橋接候選。現以原始 harvest 的 F22 `detail_url` 逐一普通 Scrapling GET，HTTP 均為 200；頁面均標示公司／114 年月份／新台幣仟元，並可讀到「本月」營收。**5 筆公告明細值全部不同於 2026-06-16 snapshot**：

| 代碼／期別 | 固定 snapshot 值 | F22 detail 本月值 | F22 announced_at | 明細原件 SHA-256 |
|---|---:|---:|---|---|
| 6111／2025-06 | 462,453 | 324,051 | 2026-09-15 15:43:58 +08:00 | `327908ae1b9fc86a3a09cb975bc025a6f10967e24e7ac49c0b41255216dc216f` |
| 6111／2025-07 | 418,357 | 420,198 | 2026-09-15 15:44:20 +08:00 | `ed4438aaa8266089cb20536d513472e9ac593459fc73f8e8344addf5a830c4ab` |
| 6111／2025-08 | 973,016 | 973,856 | 2026-09-15 15:44:41 +08:00 | `f16885ee6efdf3c97ca7c6894312b6c9b0b411b8eca5714b55fc00030329dbfe` |
| 3041／2025-07 | 49,918 | 80,778 | 2026-09-15 19:48:36 +08:00 | `7aa0caa7c7f29542fe846d1912b5a62def5b78ebb3dbd71a296eacafcc5aaced` |
| 3041／2025-08 | 71,218 | 72,058 | 2026-09-15 19:49:12 +08:00 | `345b56290922f65cd98fb6458970c1d01a60cd2462e63687d8e2ea6dd9c55493` |

這些 detail 頁面值與原事件日期可精確配對，但與舊 snapshot 數值不同，故不能把 2026-09 的公告時間映射至舊 snapshot 版本。另有兩筆官方後續 snapshot 的去年同期比較值也不同：6111／2025-09 為舊值 963,054、比較值 914,835；3041／2025-09 為舊值 146,640、比較值 161,126。初次查核時其餘 29 個 late-event keys 尚無可比 detail 值；後續對全 37 鍵的頁面查核更新了該狀態，見下節。上述初次查核未改正式 DB；值差異列不能由晚公告事件解除 degraded，需保留舊值版本或建立帶更正時間的新 revision，並取得適用版本證據。

### 2026-10-29 晚公告 37 列 detail 原件比對補充

對上述 36 個公告日晚於舊 snapshot available date 的鍵及 8942／2026-04，再用普通 Scrapling GET 讀取 37 個 MOPS detail URL。`late_event_value_samples/manifest.json` 與 37 份 HTML 原件位於 `C:\Users\archi\.codex\visualizations\2026\10\26\01a176a6-e5cf-7a92-8d1e-e77dc2eba235\mops_quality_tests_20261029\late_event_value_samples\`；唯讀重算確認 **37／37 SHA-256 相符、37／37 HTTP 200**。33 頁同時有可識別公司、期別及新台幣仟元營收值，其中 **32 筆與 2026-06-16 snapshot 數值不同、1 筆相同**；另外 4 頁為 3712 的子公司選擇頁，沒有單一公司／期別／營收值，不能比較。此結果擴大了「晚公告後官方目前頁面可能已更正」的直接反證；即使唯一相同值也不能證明該數值在較早時間已可用。

8942／2026-04 的舊 snapshot 值為 250,438，detail 頁目前本月值為 213,316；事件時間 `2026-06-18T14:11:43+08:00` 晚於該列擷取時間 `2026-06-16T23:02:24Z`。該原件 `raw/8942_2026-04.html` SHA-256 為 `956a95dcd852d385c3553edf4a123a5cec1a1c6455592d194591eedffa2222f0`。因此 36+1 列均不可只靠事件 timestamp 綁定舊數值版本；須取得晚公告對應的數值版本、公告時原件或涵蓋該歷史期別的後續數值 snapshot。此次僅增加唯讀查證，未修改 availability mapping 或正式 SQLite。

## 2026-10-29 t05st01 定向公告核驗與正式解除3筆

使用 Scrapling 一般 HTTP POST 查詢 MOPS 官方 `t05st01` 重大訊息清單及 `t05st01_detail`，以 2867、4130、5371、8183 的 2014–2026 年度窗及 6806 的 2019–2026 年度窗作 60 個定向查詢；原始回應、SHA、manifest 與 checkpoint 保存在 repo ignored scratch `.tmp_mops_t05_2014_2026/`。這不是全市場歷史掃描。另以 2330／2024 公告作正向控制，命中 12 筆月營收公告，證明 endpoint 和欄位可用。

三筆公告的明細原件皆 HTTP 200，身份、期別、仟元本月值與官方公告時間核對通過；且本月值與正式固定 snapshot 完全相同：

| 股票／期別 | 官方公告時間（台北） | snapshot／detail 本月值（仟元） | detail SHA-256 |
|---|---|---:|---|
| 2867／2026-03 | 2026-05-13 17:15:03 | -1,997,021 | `aedad9cad174786a110707628268c5fcb54fe048bb2d782b65ff0a1aa4fa09fa` |
| 6806／2025-09 | 2025-11-10 17:18:14 | 5,902,886 | `f4dee758f7ec870454e5d5e0301b82b915498179bc21d3087cf3f1af1ce71994` |
| 6806／2026-03 | 2026-05-15 17:15:51 | 2,909,432 | `a604e3f0a1d5039cd537780a4b86da4d04c8fedb61baddf7079c1fc156b1d94` |

Recovery planner 對上述 3 列回報 0 conflict／diagnostic、3 normalized、0 unmatched，候選可正式套用。guarded apply 收據 `.tmp_mops_t05_2014_2026/recovery_applied.json` 顯示 mapping 新增 3 列；其 SQLite writer 把列寫成 `|snapshot=mops-static-2026-06-16` 後綴版本。讀回後發現 canonical source version 仍 degraded，因此沒有把 apply 的 status 當成完成。利用收據所列正式 DB 備份 `F:\Min\Python\Project\FA_Data\meta_data\backup\twstock_mops_monthly_revenue_backfill_20261029T100157Z_37a68ecf309f4a588de0e053a033abfd.db`，以單一 SQLite transaction 逐鍵確認原 canonical degraded 列、精確公告日／值的 observed 後綴列皆唯一後，將公告日與 `quality=observed` 寫回 canonical row，保留原 revenue、`available_date=2026-06-18`、來源版本與 `created_at`，並刪除僅限該三鍵／版本／公告日／值的後綴列。沒有改變數值可得日或歷史 PIT 界線。

最後 readback：3 個 canonical rows 均為 observed、後綴 duplicate 為 0；整表品質由套用前 **251,189 observed／727 degraded** 變為 **251,192 observed／724 degraded**；正式 DB `PRAGMA quick_check=ok`。mapping after SHA-256 為 `2f7fde7bd9a4ece333619dcc065dc3895dfc16bdd1b4806ebf4fc5909e66337e`。歷史 snapshot scope 的 726 degraded 因此降為 723：686 個仍缺可匹配公告事件、36 個公告晚於 snapshot 可得日、1 個公告晚於該列擷取時間；另有 6884／2026-08 一列仍 degraded。8183／2014-07 清單命中「103年7月份…營收…(自願申報)」，但官方 detail API 回 HTTP 500 並稱該公司已不繼續公開發行，未建立候選或解除品質降級。4130／5371 的年度查詢未發現月營收標題命中；這些是有限 t05st01 查詢的結果，不能代表其他官方歷史管道不存在事件。

排程與 Update tab 靜態複核另由兩個只讀 agent 完成：daily Quick 呼叫預期期別的雙市場候選 child；每週路徑寫的是 `fundamental_current_observations`、明確不是 PIT。Update tab 已自動選候選、生成檔名，另提供候選檢查及 guarded formal apply；本次看到的舊截圖設定不是目前 source UI。最新正式排程 `latest_status.json` 仍是 10/28 舊版本，沒有修復後自然排程 receipt；因此只確認程式接線存在，尚未確認修復版自然排程成功。10/29 直接執行候選擷取的第一次 smoke 只留下空 run marker，沒有 receipt／CSV；第二次有完整 receipt，但 TPEx 866 列成功、TWSE 回報遠端強制關閉連線，整體 `status=rejected`、`candidate_csv=null`，未輸出雙市場 CSV，也未寫正式 DB。TPEx 原件為 `.tmp_mops_live_candidate_retry/monthly_revenue_mops_snapshots/captures/run_2026-10-29_454c26676b0b48a8b17ea2ad39c6581a/raw_html/tpex_2026-09.html`，SHA-256 `c343226a97cd8cc3a937d5b69d290901bf7097d334abe6947bbec321df21a13b`；收據 `capture_receipt.json` SHA-256 `df5b5344e72beb8deef617c5621c878d328ef44db925b838a579493373a528a8`。這次確認了 partial-result 守衛，沒有證明完整 live capture 成功。接下來仍須讀取修復版 Daily Quick 自然排程 receipt，並確認它產生的 candidate 被 Update tab selector 顯示。

### 2026-10-29 MOPS 暫時連線重試與正式候選 selector 讀回

針對上一節 TWSE `WinError 10054`，`data_module/monthly_revenue_snapshot_harvester.py` 加入保守重試：只對 `TimeoutError`／`ConnectionError` 及其 `urllib.URLError` 包裝型態多試 1 次，等待 10 秒；`HTTPError` 不重送，其他失敗照常留下診斷並阻止候選發布。此共用 harvester 同時供排程與 Update tab 使用。新增兩個回歸案例（連線 reset 一次後成功、HTTP 403 不重試）；在受控 Windows Job／同工作區 lock 下執行整個 `tests/test_monthly_revenue_snapshot_harvester.py` **11 passed**，兩個修改 Python 檔 `py_compile` 通過；Job 8 GiB／12 process limits readback verified、child exit 0、process tree／handles 關閉、無強制清理。收據目錄 `.tmp_mops_retry_validation_20261029/run_20261029_031008_cecda689/`。

套用修復後先在 ignored scratch 捕獲，再用同一支程式把正式候選寫到 `F:\Min\Python\Project\FA_Data\output\monthly_revenue_mops_snapshots\captures\run_2026-10-29_ff8681d75e804b2099cf256a694af9aa\`：期別 2026-09、SII 996 列＋OTC 866 列，共 **1,862 列**，0 diagnostics。原件 SHA-256：SII `6220d4fb93197736fbe34fe0f413b742eae887549ad4321f790cf01f2072f894`、OTC `c343226a97cd8cc3a937d5b69d290901bf7097d334abe6947bbec321df21a13b`；候選 CSV `mops_monthly_revenue_snapshot_2026-09_2026-09_2026-10-29.csv` SHA-256 `3148a7380d3000301a579e01e319f614a646e201113ffcf8bb3552d336d35107`；`capture_receipt.json` SHA-256 `3b1cb156e1ba557d8fb5fc964554836c0bd1ed39edc6148158f4af8ed1f16937`。候選選擇器的受控唯讀 readback 選中此完整發布標記綁定的 2026-09 CSV。這證實手動 live capture 到正式 output 及 selector 可見；候選仍標 `formal_database_written=false`、`availability_mapping_emitted=false`，沒有寫正式 SQLite 或 PIT mapping。Task Scheduler `latest_status.json` 仍停在 10/28，因此**修復版自然排程的實際成功尚未驗證**。

### 2026-10-29 20 個 singleton 缺口定向探查

針對剩餘 degraded 中此前未定向查過的 20 個 singleton 代碼／期別，使用 MOPS `t05st01` issuer／年度查詢逐筆查公告清單。**20/20 HTTP 200 且 API 查詢成功；另有一次 6561 詳頁請求；21 個請求的起始間隔至少 10.913836 秒。**20 份清單原始 JSON、manifest 與逐鍵 adjudication CSV 保存在 repo ignored `.tmp_mops_singleton_probe_20261029/`；20/20 清單 SHA-256 經 root readback 核對相符。未修改正式 DB、availability mapping 或程式碼。

| 代碼／期別 | 固定 snapshot 值（仟元） | t05st01 結果 |
|---|---:|---|
| 1528／2025-09 | 290,203 | 無精確月份月營收標題 |
| 1709／2022-10 | 1,098,776 | 無精確月份月營收標題 |
| 1735／2023-04 | 178,002 | 無精確月份月營收標題 |
| 2012／2022-10 | 814,191 | 無精確月份月營收標題 |
| 2207／2022-10 | 20,746,066 | 無精確月份月營收標題 |
| 2433／2022-10 | 257,446 | 無精確月份月營收標題 |
| 3219／2022-10 | 140,632 | 無精確月份月營收標題 |
| 3466／2022-10 | 96,473 | 無精確月份月營收標題 |
| 5205／2023-03 | 858 | 無精確月份月營收標題 |
| 5457／2022-10 | 1,838,900 | 無精確月份月營收標題 |
| 6111／2022-10 | 151,317 | 無精確月份月營收標題 |
| 6224／2022-11 | 239,770 | 無精確月份月營收標題 |
| 6561／2022-06 | 254,784 | 日期字串誤命中股東常會；詳頁確認不是月營收 |
| 6589／2022-06 | 108,521 | 無精確月份月營收標題 |
| 6645／2023-03 | 36,245 | 1 個泛營收標題，但期別不符 |
| 6823／2023-10 | 28,179 | 無精確月份月營收標題 |
| 6846／2025-09 | 59,169 | 無精確月份月營收標題 |
| 6859／2022-10 | 62,850 | 2 個泛營收標題，期別均不符 |
| 8034／2022-10 | 84,041 | 無精確月份月營收標題 |
| 8279／2025-08 | 177,697 | 無精確月份月營收標題 |

6561 詳頁原件於 `2026-10-29T10:31:59.821643Z` 取得，HTTP/API 200，SHA-256 `1314f599606e32b5d1207a017271ca79e4b0c786b5c4d5c912576b5e396350fe`；公告時間為民國 111/02/17 14:58:24，標題為股東常會，沒有月營收值。此次未有任何鍵取得可與 snapshot 綁定的精確月份月營收公告時間，20 列維持 degraded。結論僅限 `t05st01` 此次逐 issuer／年度清單查詢；它不能證明其他官方歷史頁／API 沒有公告資料。

#### 替代官方來源路徑判讀

離線檢視既有程式與本機原件後，確認 MOPS 歷史月營收表可透過 `POST https://mops.twse.com.tw/mops/api/redirectToOld`、`apiName=ajax_t21sc04_ifrs`、`TYPEK=sii0|otc0`、民國年／月份參數取得指定期別的全市場 HTML；此路徑可用於核對公司、期別、仟元本月值，但頁面是查詢時重新產生，並非當年公告時的原頁，沒有原始公告時間，不能替舊 snapshot 建 PIT mapping。TWSE／TPEx OpenAPI 目前只有最新月表，亦無歷史期別參數。這些路徑未在本次發出 HTTP 請求；需另做有界的數值核對或新增帶現今 capture time 的 revision，不能回填舊版公告時間。

### 2026-10-29 官方 ezSearch 前端 API 與公告時間衝突抽查

按官方 ezSearch SPA 前端程式讀取實際表單路徑（一般唯讀 HTTPS，Scrapling，未使用 Remote Desktop）：月營收彙總表呼叫 `ajax_t21sc04_ifrs`；「歷史重大訊息」以 `companyId`、`year`、`month` 呼叫 `t05st01`，公告列再以 `t05st01_detail` 讀詳情。這不是新的月營收數值來源，而是 MOPS 的公司重大訊息入口。

- 正向控制 `2330／2026`：官方重大訊息清單回傳 154 列，其中 10 筆標題能精確辨識為 2025-12 至 2026-09 月營收公告；每列均含發言日期與秒級時間。對照同公司 F22 harvest，10 個期別均同日，但公告時間全部不同。例如 2026-09：重大訊息列為 `2026-10-08 13:54:04`，F22 月營收事件列為 `2026-10-08 14:51:19`，相差 57 分 15 秒。
- 重大訊息詳情明載 2026-09 合併營收「新台幣 5,118 億 5,700 萬元」；正式 snapshot row 為 `511857399` 仟元，而該公告四捨五入後等於 `511857000` 仟元，差 399 仟元。故此公告雖證明同一期公司曾發布營收資訊，仍不是正式 F22 精確數值的同一筆公告；不可把較早的重大訊息時間直接套到精確 snapshot 值上。日期粒度仍同為 2026-10-08。
- 缺漏控制 `1528／2025`：ezSearch 回傳 21 列，沒有月營收公告標題；其 `result` 與既有 MOPS `t05st01` 原始回應完全相同，只有每次查詢自動產生的 `datetime` 欄位不同。以 Scrapling 換查官方網頁 host 沒有改變資料結果，不能用前端換 host 解決這個缺口。
- 早期批次也抓到修訂訊息：`2392` 有 2026-03／04 更正公告，以及 2026-01 至 08 更正公告；`2608` 有 2026-01 至 07 重編公告。它們必須依各自公告詳情的期別、精確數值及公告時間裁決；公告存在本身不等於可回填舊版 snapshot。

原始 JS、JSON 回應、接收時間、HTTP 狀態及 SHA-256 保留於 repo ignored `.tmp_ezsearch_probe_20261029/`。完整缺漏公司年度查詢結果與本次正式回填結果如下。

### 2026-10-29 缺漏公司批次查詢完成與兩筆正式回填

- 對正式庫 724 筆 degraded row 去重後的 96 個公司／公告年度查詢鍵完成盤點：76 個新查詢，另重用 20 個既有原始回應；每次請求間隔至少 10 秒，零自動重試。96 個結果中 95 個為 HTTP/API 200，1 個 `6806／2019` 為 HTTP 200、API 406。結果有 81 個查詢年度未找到月營收標題、11 個年度找到 1 筆、4 個年度找到 2 筆；清單的 10 個候選事件逐筆請求詳情，9 筆成功、`8183／2014` 詳情回 API 500（公司已不繼續公開發行）。
- 可與舊 snapshot 精確值、公告期別和公告日期同時對上的只有兩列：`2392／2026-03`，更正公告時間 `2026-05-15 19:04:16`、更正後月營收 `8,015,155` 仟元；`3712／2026-03`，時間 `2026-05-15 17:35:01`、更正後月營收 `3,383,462` 仟元。兩筆均早於 snapshot，且詳情值與 snapshot 完全一致；更晚的 2026-10 更正事件不得回寫至 2026-06 snapshot。
- 依治理回填流程只新增上述兩筆 mapping，採用官方 snapshot 與 mapping 備份後套用。套用後以精確鍵、金額、公告日及可用日守衛交易，將既有 canonical rows 更新為 observed，並清除本次流程產生的兩筆完全相同 suffix duplicate。正式 DB readback：兩列均為 canonical `mops-static-snapshot-monthly-revenue-2026-06-16`、available `2026-06-18`、quality `observed`；全表品質數由 251,192 observed／724 degraded 變成 **251,194 observed／722 degraded**；`PRAGMA quick_check=ok`。DB 與 mapping 備份收據記錄於 ignored `.tmp_ezsearch_probe_20261029/recovery_applied.json`。
- 按先前 724 筆逐鍵裁定分類，兩筆回填後餘額為：**684** 筆沒有可配對的公告事件、**36** 筆公告時間晚於 snapshot 可得日、**1** 筆公告時間晚於該列擷取時間，另有 **1** 筆 `6884／2026-08` 特殊缺口。四類合計 722；不能藉由放寬日期規則將後三類混入舊 snapshot。
- 其餘候選均不符合舊 snapshot 回填條件：`2608`、`3437`、`4304`、`5460`、`8101` 的修正晚於 snapshot，或詳情只覆蓋累計值／數字與舊 snapshot 不同；`8183` 只有自願申報公告列表，詳情 API 拒絕回傳；`6806／2019` API 406。這些列仍 degraded，不能只因有公告標題便推定精確值與可用時間。
- `1528／2025` 換用官方 ezSearch 前端 host 後，結果仍與既有 MOPS `t05st01` 回應相同，未找到月營收標題；因此換 host/Scrapling 解決了入口探測，但沒有補出缺失事件。`2330` 控制組則證明重大訊息與 F22 數值公告時間不同、金額精度亦不同，不能混用公告時間。

本次沒有以 Remote Desktop 操作；讀取使用官方 ezSearch 一般唯讀 HTTPS 前端 API。這輪排查已結束，後續工作應轉向對剩餘 722 列分群判斷缺少的是事件原件、公司／市場範圍、舊值版本或單位證據，再以可驗證的精確證據逐批解除 degraded；不能宣稱一次性抓取已解決所有缺值。

### 2026-10-29 剩餘缺漏集中度與替代市場 F22 探測

正式 SQLite 目前 722 筆 degraded 中，**665 筆（92.1%）集中在五家公司**：4130 健亞 145 期、5371 中光電 145 期、8183 精星 145 期、2867 三商壽 144 期、6806 森崴能源 86 期。這是跨多年的 issuer／事件路徑缺口，不是零散的單月缺列；其餘 57 筆分散於其他公司與期別。這五碼的快照 market 欄分為 TWSE（2867、6806）及 TPEx（4130、5371、8183），所以不能用單一市場 selector 的空結果替代查核。

以 Scrapling 對官方 MOPS `ezsearch_query` 的 F22 市場模式發出 6 個受限窗口：`pub`／`rotc` 各查 2014-05-01..15、2024-04-01..10、2026-05-01..15。6/6 HTTP 200，均為零列、相同 82-byte「查無公告」JSON（SHA-256 `416900c0bedd419e17635d2d44d06c1d79200907efbff484987d0296df40f6da`）。再以 8183 自願申報日 2014-09-10 作正向對照：同日 `pub` F22 回零列；`otc` F22 成功回 327 列但無 8183。這確認該日市場 F22 query 正常，亦表示 8183 的自願「各項產品業務營收統計表申報」不能直接視為 F22 月營收公告或同一筆精確數值。原件、時間及 SHA 收據留在 ignored `.tmp_ezsearch_probe_20261029/market_scope_probe/`。

此探測當時沒有找到新的 issuer-period 公告證據，正式 DB 解鎖數為 0。範圍只覆蓋上述日期窗，不能推出五家公司其餘歷史期間均沒有公告。後續改測官方舊版 `t05st01` 路徑，新增證據與回填見下節。

### 2026-10-29 官方舊版 t05st01 解鎖 6806／2026-04

以 Scrapling POST 官方 MOPS 舊版 `https://mopsov.twse.com.tw/mops/web/ajax_t05st01`，先取得 issuer／年月公告清單，再依清單內 `seq_no=1`、`spoke_date=20260515`、`spoke_time=171551` 取詳細頁。詳情顯示 6806 森崴能源於 **2026-05-15 17:15:51** 更正「採用 IFRSs 後之月營業收入申報資訊」：更正後 2026-03 累計為 **4,189,858 仟元**，2026-04 累計為 **5,242,331 仟元**。兩個同單位、同一更正頁的累計值相減為 **1,052,473 仟元**，與 2026-06-16 固定 snapshot 的 6806／2026-04 當月營收完全一致。該官方頁因此同時提供精確期別、可核對值及可得公告秒數；不使用稍晚的 F22 日期，也沒有從任意現值推測公告日。

原始清單 `legacy_t05_release_windows/6806_115_05.html` SHA-256 `fafee4ef1f1b923a6347e1ec594e2f885d84e750a5037122110f7e5238d6e01a`；詳情 `legacy_t05_release_windows/6806_20260515_171551_detail.html` SHA-256 `610d7eeab592a82527f82ca28adbf6d4cd22d0100b44d00531952e3004658095`。candidate mapping 綁定詳情 hash、`announced_at=2026-05-15T17:15:51+08:00` 與目標 snapshot 版號。Planner 回報 1 列、0 conflict、0 diagnostics、1 normalized，正式套用先備份 mapping／SQLite；交易 journal 一度停在 `mapping_applied`，按同一 operation identity 恢復後完成 DB 寫入。之後以 exact-key guarded transaction 將唯一 observed suffix row 正規化成 canonical row並移除該 suffix duplicate。SQLite readback 為 6806／2026-04、`revenue=1052473`、`announced_date=2026-05-15`、`available_date=2026-06-18`、canonical source version、`quality=observed`；`PRAGMA quick_check=ok`。正式品質數由 251,194 observed／722 degraded 變為 **251,195 observed／721 degraded**。

同一舊版端點亦成功回傳 5371／民國 103 年 5、6 月及 2867／民國 103 年 5、6 月公告清單，但這四個代表月份沒有精確月營收標題；6806／民國 108 年 5 月清單為空，該結果僅是單一月份，不能推論整段歷史。原先「5 碼歷史 issuer 路徑都沒有資料」的判斷需修正：舊版路徑能查回公司公告，但只有逐列核出精確收入值與時間才能解除對應 degraded。此批只新增 6806／2026-04 一列，不表示其他歷史缺口已解決。

### 2026-10-29 利用更正明細累計值再解鎖 3712／2026-04

檢視已保存、SHA 已核對的 MOPS 官方 3712／2026-05-15 詳情頁（原始 API JSON SHA-256 `00a4b4fa92765cec12eb8ec24ff42e72c5901d00f0fbcf603d63055061eb6792`），發現標題雖寫「更正 3 月營收及 3 月及 4 月累計營收」，先前 parser 只將 3 月列為候選，漏掉可由詳情精確還原的 4 月。更正後 3 月累計 **5,952,952 仟元**、4 月累計 **7,594,522 仟元**，差額 **1,641,570 仟元**與固定 snapshot 3712／2026-04 `current_month_revenue` 完全一致。公告時間為 **2026-05-15 17:35:01**，早於該 snapshot capture；因此以同一公告作為 4 月值的時間證據成立。

Recovery planner 對 3712／2026-04 回報 1 列、0 conflict、0 diagnostic、1 normalized；正式 apply 先備份 mapping／SQLite。canonical row exact-key readback 後為 `revenue=1641570`、`announced_date=2026-05-15`、`available_date=2026-06-18`、`quality=observed`，`PRAGMA quick_check=ok`。加上本節上一筆 6806／2026-04，正式數由 251,194 observed／722 degraded 變為 **251,196 observed／720 degraded**；目前五家集中數為 664/720（92.2%），其餘分類為 682 無已配對事件、36 晚於 snapshot 可得日、1 晚於 row capture、1 筆 6884／2026-08 缺公告。

反例也一併記錄：同一批官方 2392／2026-05-15 明細的 3 月與 4 月累計差為 6,222,375 仟元，但固定 snapshot 4 月值是 6,222,374 仟元，差 1 仟元。此列沒有精確相等，不納入 mapping、不解除 degraded。這證明累計差額只在與目標 snapshot 完全一致時才可回填，不能以近似或四捨五入替代逐列核對。

### 2026-10-29 官方明細累計值擴展解鎖 8101／2026-04

對官方 `t05st01` 年度清單中 8101／2026-05-19、更正 2025-12 至 2026-04 累計營收的公告取 MOPS 明細（`companyId=8101`、`marketKind=sii`、`enterDate=1150519`、`serialNumber=2`）。HTTP 200 原件 SHA-256 `e3fe8c1f91d786454ea213c32e34000b02ac14a662d5929570f8054e3929fd82`。明細當期／累計表列 2026-04 當期 **30,409 仟元**、截至 4 月累計 **112,511 仟元**；這與固定 snapshot 8101／2026-04 的 `current_month_revenue=30409`、`cumulative_revenue=112511` 逐欄完全一致，公告時間 **2026-05-19 17:20:59** 早於 snapshot capture。Recovery planner 1 列、0 conflict、0 diagnostics，正式回填後 canonical row 為 `announced_date=2026-05-19`、`revenue=30409`、`available_date=2026-06-18`、`quality=observed`，`PRAGMA quick_check=ok`。

時間版本守衛仍有效：8101／2026-08-07 的官方後續更正將 2026-04 當期改為 **34,038 仟元**，其 F22 時間晚於 2026-06-16 snapshot；因此保留舊 snapshot 在 2026-05-19 可知的 30,409，不把 8 月修訂覆寫到舊值或舊公告時間。加上 3712／2026-04 與 6806／2026-04，正式表由 251,196 observed／720 degraded 變為 **251,197 observed／719 degraded**。剩餘分類為 681 無可配對事件、36 晚於 snapshot 可得日、1 晚於 row capture、另 6884／2026-08 一列缺公告；五家主要集中仍為 664 列（92.4%）。

### 2026-10-29 MOPS 晚公告明細新版本寫入與 PIT 讀回

37 個保存的官方 F22 明細頁原件再次驗證後，33 頁具有可核對公司、期別、單位及本月值；4 頁是 3712 子公司選擇頁，不能當單一公司營收值。對 33 個可讀值逐鍵比較正式表，2 鍵已由既有正式資料涵蓋，故本次只新增 **31 個**數值版本。每筆明細頁 HTML SHA、對應 F22 事件原始檔 SHA、公司／期別／新台幣仟元與本月值均通過核對。

這批頁面是在 2026-10-29 才實際擷取，不能證明目前頁面上的數值在原 F22 公告秒數已經存在。故新版本以 `mops.monthly_revenue_f22_detail_revision` 寫入，`available_date=2026-10-30`；每筆使用綁定明細 SHA 的獨立 `source_version`，並在 availability mapping 綁定官方 F22 事件身分與來源 hash。舊 `mops-static-snapshot-monthly-revenue-2026-06-16` 值、品質與歷史可得日皆未覆寫。

正式寫入收據及讀回：新增 31 列、mapping 新增 31 列；SQLite `PRAGMA quick_check=ok`。PIT provider cutoff 驗證為 **2026-10-29 不可見、2026-10-30 31/31 精確值可見**。SQLite 物理列品質目前為 **251,228 observed／719 degraded**：observed 增加 31，但舊 snapshot 的 degraded 標記仍保留，因而底層 degraded 計數不變。這 31 個鍵於 10/30 之後有可用的新觀察版本；不能稱舊 snapshot 被回填，也不能把其更正值回寫到更早時間。DB 與 mapping 備份、逐筆寫入／provider 驗證收據保存在正式資料根目錄 `meta_data/backup/` 及本次 ignored scratch `.tmp_mops_late_revision_20261029/`。

整表讀回亦確認目前 `fundamental_monthly_revenues` 共 **251,947 列、收入值空白 0 列**；719 個 degraded canonical rows 的 `announced_date` 全部空白，observed rows 則公告日期均有值。因此目前的 719 筆不是缺少營收數字，而是缺可供正式 PIT 使用的公司別公告時間證據；報表仍可顯示舊快照數字及 degraded 品質，但正式 PIT provider 不會把沒有公告 mapping 的舊列當可用歷史特徵。

後續又加入更嚴格的 mapping validator 規則：新 source version 內的 16 位明細 SHA 前綴必須與 `source_hash` 相符，capture date 必須是可得日的前一日。以正式 mapping 重跑驗證為 **valid、250,069 accepted、0 diagnostics**；mapping SHA-256 `5b76f1b383c715ece53fa51ff8e7338a077ad3d2e191f4aae203004e0c1def5a` 與寫入收據一致。使用目前程式直接對正式 SQLite／mapping 重跑 `FundamentalSQLiteProvider`：31 鍵在 2026-10-29 cutoff **0 筆可見**，2026-10-30 cutoff **31/31 精確值可見、0 mismatch**。因此次序與 hash binding 在現行 reader 上也通過實讀，並非只通過測試 fixture。

此處置將 36 個晚於舊 snapshot 可得日事件及 1 個晚於原列擷取時間事件中的 31 個鍵，補成「目前頁面值、於本次實際觀察後可用」的新版本；其餘晚公告鍵仍需可識別的單一公司營收明細，尤其 3712 的選擇頁不能代替子公司資料。原分類的 681 個缺少已配對事件、未解的晚公告鍵及 6884／2026-08 特殊缺口仍須繼續逐類處理。這不是 719 個 degraded 全數解除，也不代表歷史公告版本都已還原。

### 2026-10-29 6806 歷史公告缺口離線交叉核查

對目前集中缺口的 6806 做唯讀比對。四批既存 MOPS F22 `events.csv`（`mops_harvest_2013_2019`、`2014_2019`、`2020_2025`、`2026`）合計 **267,777 列**，以公司代碼精確搜尋皆為 **0 筆 6806 事件**；逐檔 SHA-256 分別為 `927e45f5e099b06523c2d7e39923dae1f71a6ab9ddff73da4e82a731e3cdf9f1`、`d04bad914fa19a1467465358ab09c2b6d4f4c0ac4f227072bc94a1f8fb6829b6`、`c0c6eadd04872e3ca44a85eff88bb99ae844e74d04ff3c1e8f255c53cbf6944f`、`1da9b9fc85197f1545efdd6da1ca5e7c224ac2e66fbba1c63bbf20abbc6b2176`。既有 6806／民國 108 年 `t05st01` 原件 HTTP 200，但 API code 406「查無相符資料」、0 列、89 bytes，SHA-256 `3e87b377fbcd68d73065b3389f2f57320abb4b9a05b443995d24c80720aa7199`。這只表示該公司年度查詢未回資料，不能推定當期沒有公告。

本次另以 Scrapling 普通 HTTPS POST 對同一官方 `t05st01` 入口做一次即時重試，DNS 解析失敗，沒有收到 HTTP 回應；失敗收據位於 ignored `.tmp_mops_gap_scout_6806_20261029/`。沒有替換解析器、代理或使用 Remote Desktop。現有 F22 harvest 事件欠缺是來源事件未取得，非本地 market/date 欄位配對錯誤；這 85 個目前仍 degraded 的 6806 keys 沒有可安全解除列。還需從另一條能取得其歷史公告的公開官方路徑查核，或補得能綁定精確公司、期別、數值及當時可得時間的原件。原件集合與摘要保留於上述 ignored scratch；正式 DB／mapping 未修改。

另用程式庫既有官方月表 redirect chain（`redirectToOld → ajax_t21sc04_ifrs → static report`）對 `tpex／2019-01` 做一個單窗歷史數值探測。POST 在第一跳 DNS `getaddrinfo failed`，尚未取得 HTTP 回應或月表原件；失敗收據位於 ignored `.tmp_mops_6806_historical_month_probe_20261029/failure_receipt.json`。因此本次仍沒有 6806 數值或公告時間新證據，也沒有安全解除列。這個月表路徑若日後可連線，可能核對目前可觀察的官方歷史月值；它本身不含當年公告 timestamp，必須以實際擷取時間建立新觀察版本，不能回填成原公告可得時間。

### 2026-10-29 current degraded 719 keys crosswalk reconciliation

以正式 SQLite 中目前 719 個 `degraded` canonical keys，重新和四批保存的 F22 `events.csv` 以 `(stock_code, period)` 精確交叉比對，並另外對照 37 個 F22 detail revision manifest keys 與既有 `t05st01` 原件線索：**686 keys 沒有精確 F22 event；33 keys 有精確 F22 event，但事件時間晚於 2026-06-16 舊 snapshot row capture**。兩組合計正好 719；市場標籤正規化及事件時間解析沒有額外找回 key。686 個無 F22 鍵中，5 個另帶不完整 `t05st01` 線索，不能精確配對到 issuer-period 數值與公告事件；其餘 681 個沒有其他已知公告身份。`6884／2026-08` 在這 681 個之內，是特殊待查子集，不是額外一列。故本節以這次 current exact-key crosswalk 為現況口徑，較早段落的分項數不得再加總套用。

這 5 keys 為 `2867／2025-01`、`2867／2025-02`、`2867／2026-01`、`2867／2026-02`（同一 2026-04-14 17:00:38 更正公告標題涵蓋多期，但候選期別空白，無法逐鍵裁決），以及 `8183／2014-07`（清單標題為自願申報，詳情 API 500，未取得可驗證的月營收數值）。它們目前都沒有精確 F22 event candidate，故不能只憑公司年度或標題解除 degraded。

平行補查顯示，2867 四期線索可用舊版 `t05st01` 詳情參數 `companyId=2867, marketKind=pub, enterDate=1150413, serialNumber=1` 再取原公告，但一次有界 Scrapling 重試仍在 DNS 名稱解析逾時，沒有收到詳情原件；清單原件 SHA-256 為 `0caeb29085e28dd334640aa494abdefd0239f867e14f6ac16b11dd0148dc2856`。4130、5371 的本機 issuer-year 清單沒有月營收公告標題；8183 的唯一自願申報詳情則回 API 500。這些是目前可取得原件的範圍，不足以推論公告不存在；下一個有最高資訊價值的查核是連線恢復後重取 2867 更正詳頁，再逐期核對四列的數值、期別及公告秒數。

另由 [MoneyDJ 的 MOPS 公告轉載](https://www.moneydj.com/kmdj/news/newsviewer.aspx?a=56485e5a-0001-47e2-b1f9-3fbf170cea59)找到這份更正公告的完整文字，頁面標示 2026-04-14 17:03 發布；本機官方 MOPS `t05st01` 清單記錄的公告秒數為 17:00:38。轉載所列更正後值與固定 snapshot／DB 比對如下（單位均為仟元）：2025-01 **5,737,205 vs 11,927,835**、2025-02 **8,805,355 vs 11,020,170**，兩列不符；2026-01 **6,481,761** 與 2026-02 **7,723,798** 則各自完全相符。因此 2025 兩列不能把公告時間套到舊 snapshot 數值上；2026 兩列是官方詳頁取回後可評估的候選，但轉載只能作查找線索，不能取代缺失的 MOPS 詳情原件。正式 mapping／DB 本次未修改。

37 個 late-detail manifest keys 中，另 4 個（`2392／2026-03`、`3712／2026-03`、`3712／2026-04`、`8101／2026-04`）已不屬目前 degraded 集合；其餘 33 個才與本次 degraded 母體相交。31 個於 2026-10-29 成功讀取並寫成 2026-10-30 才可用的新觀察版本；另兩鍵仍未形成可讀的單一 issuer detail revision。這些新版本不會追溯改寫舊 snapshot row 的 degraded 狀態。

因此目前頁面月營收金額並未缺值（全表 251,947 rows 中空白值 0）；真正未結案的是舊列的公告時間／PIT 證據。正式舊列的安全解除數仍為 **0**；31 個新版本於 2026-10-30 起應按新 source version 讀取，不能追溯視為舊 snapshot 的解除。另 688 個 keys 尚無可供舊列採用的精確事件／修訂時間證據；其中 `6884／2026-08` 屬 686 個無精確 F22 配對鍵。後續優先補查 686 個無 F22 精確配對鍵的歷史官方公告與適用性，並處理餘下兩個 late-detail key；不能重抓同一批既有窗口取代缺失來源證據。

### 2026-10-29 F22 revision 在個股研究報告的金額顯示修復

發現 `StockResearchReportReadService` 先前只將 `mops.monthly_revenue_static_snapshot` 視為已核實的「新台幣仟元」來源；因此 31 筆已有官方 F22 明細、hash binding、available date 與逐筆值核驗的 `mops.monthly_revenue_f22_detail_revision`，即使 2026-10-30 cutoff 後可由 DB 查到，也會在報告 DTO 被設為 `value=None`。現已把這個精確 revision source type 加入單位契約白名單，只按原件仟元乘 1,000 顯示 TWD；未知來源及無法解析值仍維持不可用及 degraded，不擴大到泛用 MOPS／OpenAPI 來源。

修復只改個股研究報告的展示換算，不動正式 SQLite、availability mapping、available date、公告時間、舊 snapshot 或 `FundamentalSQLiteProvider` 的 PIT 守衛。報告仍依 row available date 篩選，並保留 source version、公告日、available date 與 row quality。兩個聚焦測試（F22 revision 顯示換算、OpenAPI 未核單位仍不顯示）**2 passed**；沒有重跑整套報告 QA，也沒有進行原生 UI UAT。

### 2026-10-29 2867 兩期月營收回補及 PIT provider 讀回

對 `2867／2026-01`、`2867／2026-02`，本機官方 MOPS `t05st01` list 原件 SHA-256 `0caeb29085e28dd334640aa494abdefd0239f867e14f6ac16b11dd0148dc2856` 記錄更正公告時間 `2026-04-14T17:00:38+08:00`，標題涵蓋民國 114／115 年 1–2 月。固定官方 MOPS snapshot 捕獲於 2026-06-16，值分別為 6,481,761、7,723,798 仟元；MoneyDJ 轉載公告所列這兩個更正值相同，僅作二次佐證，不作主要來源。官方詳情 API 的 Scrapling 重試因 DNS 失敗未取回詳頁；對 `2867／2025-01、2025-02`，轉載更正值分別為 5,737,205、8,805,355 仟元，與舊 snapshot 的 11,927,835、11,020,170 不同，因此只解除兩個數值精確相符的 snapshot key，不將同一公告時間套用至不同數值版本。

受控 recovery dry-run 接受 2 列、mapping 新增 2 列、0 conflict／0 diagnostics；跨檔 apply 使用任務備份目錄 `F:/Min/Python/Project/FA_Data/meta_data/backup/mops_2867_20261029/`，DB 2 列新增為 observed 版本，mapping SHA-256 從 `5b76f1b383c715ece53fa51ff8e7338a077ad3d2e191f4aae203004e0c1def5a` 變為 `5b9f71ec2caf453b713ba76ff669161a24e23a48244d2b16698182bb9d8e576a`。寫後 PIT 實讀首次發現 provider 不顯示兩筆：writer 將 SQLite target `source_version` 正規化成 `mops-static-snapshot-monthly-revenue-2026-06-16|snapshot=mops-static-2026-06-16`，而初版 mapping target 少了此後綴。現已為同一事件 hash 追加 revision 2，精確綁定實際 SQLite source version；不改 DB 數值或公告／可得日。對 2867／兩期的回歸檢查 49 passed，修改檔 `py_compile` 通過；修正後正式 availability validator 為 **250,069 accepted、0 diagnostics**，mapping SHA-256 `dff119b7c0112a683b2ae735e42fb5f8b65e5ea1db447c6999179fa69f6f7222`，SQLite `PRAGMA quick_check=ok`。`FundamentalSQLiteProvider` cutoff 2026-06-17 回傳 0 筆，6/18 精確回傳兩期值及公告日，確認 PIT 可見時間未提前。

截至 2026-10-29 cutoff，正式表中 246,331 個已可見公司／期別有 716 個缺公告日；在原 degraded key 集合內，718 個有可見版本，其中只有剛回補的 2867 兩期已有公告 mapping，另 `6884／2026-08` 的 observed 金額列要到 10/30 才可見。以 2026-10-30 cutoff 重新讀取，31 個晚公告 detail revision 轉為可見，6884／2026-08 也進入可見範圍；251,916 個已可見公司／期別中仍有 686 個缺公告日。故「686」是 10/30 cutoff 的剩餘值，不能當作 10/29 已修復數；2 個 2867 mapping 已於 6/18 生效。這 686 個 10/30 cutoff 缺公告鍵高度集中：4130 健亞 145、5371 中光電 145、8183 精星 145、2867 三商壽 142、6806 森崴能源 85，前五家共 **662／686（96.5%）**；其餘 24 鍵分散於其他公司。舊 snapshot degraded 原列仍保留，物理列為 251,230 observed／719 degraded。2025 年兩列及其他未有精確、可用公告證據的鍵維持待查。Recovery 與 mapping writer 的 apply receipts、DB／mapping 前備份及 hash 均保存在正式資料根目錄備份和 ignored `.tmp_mops_2867_2026_jan_feb_20261029/`；沒有納入 Git。

### 2026-10-29 月營收最新狀態複核與 Update tab 缺候選修正

以唯讀 SQLite inspector 重新查核 `fundamental_monthly_revenues`：**251,230 observed、719 degraded，251,949 列的 `revenue` 空值為 0**；719 列皆缺 `announced_date`。這是公告時間／PIT 證據缺口，不是金額欄位缺值。2026-07 至 2026-09 為 5,585 列：7 月 1,861 observed；8 月 1,861 observed、`6884` 1 列 degraded；9 月 1,862 observed。四組的 `available_date` 均為 2026-10-30，需以該日期為 cutoff 才能讀取，不得提前曝光。

重新驗證 2014–2019、2020–2025、2026 三批 SII／OTC harvest：共 1,800 個 raw JSON 視窗、266,836 個事件列；每個 raw 的檔案存在、byte count、SHA-256、JSON payload 列數均與 manifest／`events.csv` 對得上。payload 分別為 652/816、707/864、100/120 個有資料視窗，其餘為來源回覆「該窗無公告資料」，不是抓取成功覆蓋事件的證據。另 151 個 `rotc_pub` 視窗 HTTP 200 但 payload 全空、events.csv 為 0 列，不能算興櫃／公開發行全期覆蓋。

719 個缺公告日鍵的最新精確 crosswalk 仍是 686 個沒有保存的精確 F22 event、33 個事件時間晚於 2026-06-16 舊 snapshot row capture；不能把晚公告時間套給舊值。先前對 `8183` 的官方公司月表抽查只驗證金額，頁面未提供公告時間，故不解除 degraded。Scrapling 已對官方 MOPS ezSearch 的 `2867／2026-04-14` 做範圍探測（含客戶端自動重試）；本機 DNS 解析逾時，未收到 HTTP response。這僅表示目前連線無法驗證，不表示公告不存在；此環境沒有使用 Remote Desktop。

排程線路仍分兩種：每日 Quick 的 MOPS／OpenAPI 擷取是當期候選，並不追補舊期或直接寫正式 PIT；週排程的月營收工作是現況觀測，不能替代歷史 availability mapping。Task Scheduler 已啟用只證明排程註冊存在；修復版下一次自然執行的 receipt 尚待查核。

Update → 月營收頁已修正：無候選檔時不再把 snapshot 輸出資料夾填入 CSV 路徑；路徑留白會引導使用者先抓候選，寫入時自動挑選最新的實際 CSV。服務端現在拒絕資料夾及非 CSV 檔，且仍要求正式歷史回填走獨立確認流程。歷史可得日 mapping 與自動命名改為清楚標示；現況更新按鈕另行說明。

本次程式驗證：`tests/test_ui_qt_update_view_workbench.py` **102 passed**；`tests/test_update_service_monthly_revenue_status.py` **12 passed**；`scripts/qa_validate_update_tab.py` **25 passed、0 failed、4 skipped**；修改檔 `py_compile` 通過；`mypy` 對 3 個修改的 Python 檔通過。這些是自動測試／靜態檢查，未執行桌面原生 UI UAT；自然排程證據見下節補錄。

### 2026-10-29 自然 Daily Quick MOPS capture 與殘餘缺口覆核

正式排程產物已從資料根唯讀讀回：Daily Quick run `20261029-41720` 於 2026-10-29 04:20 PDT 啟動，核心於 04:50 完成 `passed_with_warnings`；MOPS child receipt 於 04:51 PDT 終結為 `captured`、return code 0、diagnostics 空。候選期別是 2026-09，上市 996 列、上櫃 866 列，共 1,862；receipt 明示 `candidate_only=true`、`formal_database_written=false`、`availability_mapping_emitted=false`、`formal_pit_eligible=false`。這證明每日擷取自然執行成功，不代表正式資料庫或 PIT mapping 由排程更新。

已核對 child receipt SHA-256 `bfbd50d8d44e9cc500f89076da322b5e0e448f7b266862c687d1ed30fcd64bc7`、候選 CSV SHA-256 `db3d86262e442c290ef4737a0fb4b90e5b3e9aabd64427b2fb88003ac98c28ef`；實際 CSV 讀得 1,862 列。兩個 raw HTML 原件均存在，byte count 與 SHA 分別符合 receipt：TWSE 468,513 bytes／`f5222dde4362a4ed9ef11a375c4c76e2f7a28655a8eea5748ffd368e3a702495`，TPEx 406,653 bytes／`ccf1665aef3d2ed83ca415914b10d137fa9dc2efcb6bd90428b9b442af58c37c`。`capture_complete.json` 的候選與 receipt hashes 也相符。以正式 snapshot selector 對資料根執行唯讀選檔，回傳這個 2026-09 候選；因此更新頁自動選檔現在有真實自然產物可供讀取。核心 `latest_status.json` 留存的是發布 child 前的 `pending_after_core_publication`，child receipt 才是此次 MOPS 擷取終態的權威收據；不把核心狀態 JSON 的舊欄位解讀成 child 失敗。

週排程不是同一條成功線：唯讀收據顯示最新 `weekly_d161c8...` parent run 在 2026-10-26 逾時，狀態為 `core_process_timeout`／`blocked`，月營收 statement child 因 core 非零結束而 skipped；`current_fundamentals` 最近一次 terminal 為 2026-10-19 `failed`、exit code 1。DB 內有 `fundamental_current_observations` 月營收列，不足以歸因為週排程成功。Task Scheduler 當前註冊狀態本輪因 CIM 權限拒絕未能重新讀回；因此 Daily Quick 有自然成功證據，Weekly current-observation 線仍未驗過成功。

本輪再次核對 `.tmp_mops_event_crosswalk_20261029/degraded_crosswalk.csv` 與唯讀正式 DB，719 個 degraded keys 完全相符；4 個已保存 F22 event CSV 合計 267,777 rows／266,836 unique stock-period keys。交叉比對結果仍為 686 個 `no_event`、33 個 `event_after_row_capture`；33 個事件時間全部晚於 2026-06-16 舊 snapshot capture，不可套給舊值。三個主要歷史 harvest（2014–2019、2020–2025、2026）的 1,800 個 raw JSON 已逐檔重算 SHA、byte count、JSON row count，並確認與 manifest／events.csv 相符，raw mismatch 0。

額外檢查官方舊版 MOPS `t05st01` issuer-year 清冊：4130 與 5371 民國 103–115 年各 13/13 年份回 HTTP/API 200，但公告清單沒有月營收標題；8183 同為 13/13 年份 200，唯一 103 年 9 月自願申報詳情 API 500，精確期別金額未取回。精星[官方營運報告頁](https://www.psaitc.com/investors/operate_state)的 2014-07 月營收為 245,529 仟元，與 DB 值相同；頁面沒有公告日期／時間，而 MOPS 清單標題僅寫自願申報，詳情 API 500，尚不能證明該詳情就是同一合併月營收數值，因此只列為交叉來源候選、不解除 PIT degraded。6806 在 108–115 年 7/8 個年份回 API 200、108 年 API 406；僅 2025-09、2026-03 有營收公告標題，均已不屬目前 degraded keys。官方舊版 EZSearch／市場分流 probe 未找到可補進現有 4130／5371／8183／6806 gap 的精確事件。22 個 singleton 子集合中，18 個沒有精確 F22 event；另 4 個雖有晚期明細，但公告更正數值與 2026-06-16 snapshot 不同，不能解除舊列。

Scrapling 對官方 `mops.twse.com.tw/mops/api/t05st01` 的當次 bounded probe 最終為 DNS resolution error（自動重試亦未收到 HTTP）；前一輪 `mopsov.twse.com.tw` ezSearch probe 也在 DNS 階段失敗。Genovate、Coretronic、精星及森崴官方頁面的 Scrapling GET 也因 DNS 解析逾時而無 HTTP response。DNS 失敗只描述本機連線，不能推論公告不存在；沒有使用 Remote Desktop。既有公司官方月營收表能交叉核對部分數值，但若頁面未提供公告時間，仍不能代替公告 timestamp 或 PIT mapping。故本輪**新增安全解除 0 keys**，正式 DB 與 availability mapping 未修改；需要恢復官方端點連線或找到逐期可驗證的第一方公告時間／值證據，才能再裁決剩餘 719 個物理 degraded 舊列。

### 2026-10-29 Weekly core 逾時門檻調整

唯讀檢視 `scripts/scheduled/weekly_collection_controller.py` 與正式終端收據，確認 2026-10-26 的 `core_process_timeout` 是 controller 對本機 SQLite／sidecar core 設定 30 秒 `subprocess.run` 硬上限後觸發；該次 stdout/stderr 均為空，無法證實內部哪一步耗時。這個 core 非月營收抓取器，但 timeout 會使月營收 statement 與後續 `current_fundamentals` 子流程跳過。為避免短暫磁碟／SQLite 負載剛超過 30 秒就整週漏跑，將有限 core 上限提高至 90 秒，並同步將 pending watchdog 總界線從 1,170 秒調為 1,230 秒；月營收 statement 每次 30 秒、6 次查詢、不重試，其他子流程界線不變。這是有界容忍度調整，不代表已證實 10/26 根因為資源負載，也不宣稱排程已自然成功；仍需下一次自然 weekly receipt 驗證是否跨過 core 並執行後續子流程。

`tests/test_weekly_collection_controller.py` 使用 repo 內短路徑 `--basetemp=.pytest-owned-temp/wc_timeout90` 驗證 **40 passed、1 deselected**；排除項是具名本機遷移原件 hash 綁定測試，該檢查目前本機返回 False，與 timeout 常數無關。首次使用系統 Temp 有 6 個案例遇 Windows `WinError 206` 路徑長度錯誤，短 basetemp 後受控案例全通過；具名遷移檢查仍是獨立未通過項，不宣稱整個測試檔全通過。`py_compile` 通過。repo-wide mypy 仍被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻止，不能作為本次檔案的 mypy 結果。

### 2026-10-29 晚間 MOPS PIT cutoff 與 Scrapling PUB 定向重試

依使用者指示使用 Scrapling 普通 HTTPS，沒有使用 Remote Desktop、登入、代理或 challenge 處理。對官方 `https://mopsov.twse.com.tw/mops/web/ezsearch_query` 只送出一次 `TYPEK=pub`、`PRO_ITEM=F22`、`115/09/10` 單日查詢，12 秒 timeout、停用重試；本機 DNS 解析逾時，沒有收到 HTTP status 或 response body。這次只能記為連線未完成，不能推論 PUB 市場當日沒有公告。既有文件所列的 151 個全空視窗是 ROTC 探測；全期 PUB 視窗仍未完成，待官方端點可連線後再跑有界批次並以 manifest/raw hash 驗收。

同時以正式 SQLite 唯讀查詢重核 2026-07..09：5,585 列都在正式表，全部 `available_date=2026-10-30`；2026-10-29 cutoff 可見 **0** 列，2026-10-30 cutoff 可見 **5,585** 列。當中 5,584 列有公告日／`observed`，唯一缺公告日的 `6884／2026-08` 為數值 `184914` 仟元、`degraded`；值已存在，缺的是可核對的官方 F22 公告時間。SQLite inspector 讀回的 source version 綁定 2026-10-29 TPEx 2026-08 靜態快照 raw SHA `4057158db90c002dc521f8b1e28ba32fe38dc0170f7d82a55a75110c038d01a7`。未以搜尋引擎摘要或第三方轉載替代官方公告原件，也沒有因此新增 mapping／寫入。

截至此查核，歷史舊 snapshot 的 719 個 physical degraded rows 與 10/30 PIT cutoff 的 686 個缺公告日 keys 是不同集合、不能相加：前者 crosswalk 為 686 個 no-event 加 33 個 event-after-capture；其中 31 個 late-event keys 已有 10/30 才可用的新明細版本，另外 2 個未形成可讀 revision。7–9 月新資料內另有唯一 `6884／2026-08` degraded key。Weekly 修復後自然成功 receipt 尚未取得，Update Tab 的自動選檔有自然候選收據但原生 UI 真人 UAT 尚未執行。正式 SQLite／availability mapping 本次均唯讀未改。

### 2026-10-29 6884／2026-08 缺失 F22 公告的來源定位

重新解析官方 harvest 原件 `output/mops_harvest_2026/raw/ezsearch_F22_otc_1150906_1150908.json`：payload 329 列、HTTP/API `success`，原件 SHA-256 `864b1de8fbc09df54ba203d9923a122be9a34001712b4721db2979d54e395018` 與 manifest 一致；329 列中 `COMPANY_ID=6884` 為 **0**。因此 6884／2026-08 的缺事件已存在於官方 OTC EZSearch 原始回應，不是 `events.csv` parser 漏列。該期 6884 的 `mopsfin`／MOPS 現況值仍是 184,914 仟元。

另外逐份掃描現存 2013–2019、2014–2019、2020–2025、2026 四批 `events.csv`，上市／上櫃 harvest 都未含 6884 的 F22 event。這排除現存 SII／OTC harvest parser 或事件檔少併入的可能；尚未排除的是未採集的 PUB 市場視窗，因而不能拿這個 0 筆結果當作沒有公告。

第三方 MoneyDJ／第一銀行轉載頁將相同金額標為 2026-09-07 23:59 發布（[第一銀行頁面](https://wealth.firstbank.com.tw/investment-tips/trend-insight/news/news-detail?id=%7B184CEDB8-C5E8-4E18-A441-504E87000030%7D)）。此只提供下一個官方查詢日期線索，不是 MOPS 原始公告時間，不用於 availability mapping。針對 2026-09-07 的官方 PUB F22 單日窗口再以 Scrapling 普通 HTTPS POST 查一次，12 秒 timeout、單次請求；本機 DNS 解析逾時、沒有 HTTP response。失敗收據保存在 ignored `.tmp_mops_pub_6884_probe_20261029/failure_receipt.json`。故本輪未新增 mapping、未改正式 DB；網路恢復後應先重試該單日 PUB 窗口，再確認公告詳情中的 issuer、period 與 value，才能裁決 6884／2026-08。

### 2026-10-29 MOPS 6884 官方新站端點補查

使用 Scrapling 對官方 MOPS 新站作普通 HTTPS 唯讀查詢，未使用 Remote Desktop、登入、代理或 challenge 處理。對 `POST https://mops.twse.com.tw/mops/api/t05st01` 查詢 `companyId=6884, year=115, month=all`，HTTP/API 200，但僅回傳最近 20 筆公告（115/02/04 至 115/08/19）；再帶入 `firstDay=115/09/01,lastDay=115/09/30`，仍回同樣 20 筆、相同 5,722 bytes，表示這組日期欄位未形成可用的九月歷史篩選。第二次原件 SHA-256 為 `914277f70994bbaa85619ab2a36fba2075c2547286b2f638c1b3a623de2f185d`。不能把「最新 20 筆未含九月」解讀成九月沒有公告，也不能再用這個端點的空結果裁決 6884。

同日官方 EZSearch `TYPEK=pub, PRO_ITEM=F22, SDATE=EDATE=115/09/07` 以 Scrapling 收到 HTTP 200、API `fail／查無公告資料`、0 列，原件 82 bytes，SHA-256 `416900c0bedd419e17635d2d44d06c1d79200907efbff484987d0296df40f6da`。此是該官方端點、該市場類型與單日窗口的有效負結果，但只排除這個查詢窗口回傳 6884，不能排除其他公告查詢路徑、不同日期或歷史索引結果。MOPS 新站 `t51sb10` 則是「最新財務／營收報表」頁，頁面模組呼叫 `home_page/t51sb10` 並呈現財報報表清單；它不是 issuer-period F22 公告事件查詢，故不把它當作公告時間證據。原始回應及收據留在 ignored `.tmp_mops_6884_t05_20261029/` 與 `.tmp_mops_home_20261029/`。

因此本次來源路徑補查**沒有新增可安全套用的公告時間或 mapping**，沒有改正式 SQLite／availability mapping，`6884／2026-08` 仍 degraded。下一步應尋找可按歷史日期／期別完整查詢並能回傳公告明細的官方路徑，或取得對應 F22 公告原件；不得將這次 t05st01 最近 20 筆結果當成完成歷史查核。

### 2026-10-29 Weekly MOPS child 實跑：編碼與 output junction 修復

隔離手動執行 Weekly controller 時先重現兩個可修故障：核心 collector 在 Windows `cp1252` stdout 輸出含中文 JSON 時拋 `UnicodeEncodeError`；修正為子程序自行重設 UTF-8 後，core 已能正常完成。接著 `fetch_mops_statement_availability.py` 把已由 output guard 驗證的輸出路徑 `resolve()` 後再檢查是否位於 repo；本機 `repo/output` 是指向 `F:/Min/Python/Project/BaldrStorage/repo-output` 的既定 junction，故被誤判為越界。現在以固定 repo 內預設路徑做詞法範圍驗證，再由既有 output guard 確認解析後位置不在正式 `DATA_ROOT`。

修正後以隔離 controller receipt 實跑成功：core `exit_code=0`、sidecar readback verified、未逾時；MOPS 財報公告研究 child `captured_research`，6/6 查詢成功、失敗 0、無效事件 0，成功回應 custody 6 件且 source readback verified。研究 run `run_20261029T142745954121Z`，artifact SHA-256 `1ae1a1cfce9a9f143311dc12a5f786a7d7c91a928292da0de5a45891475f5058`。本次明確停用無關的 quarterly OpenAPI child，只執行 controller，未呼叫外層 `current_fundamentals` writer；`formal_database_write_performed_by_controller=false`。注意這個 child 查詢的是財報公告 F26–F28，與月營收 F22 歷史缺口不同；此為手動隔離驗證，不代表 Task Scheduler 自然週排程已成功。

修改的週核心 CLI 在 `PYTHONIOENCODING=cp1252` 下回歸測試通過；CLI／output-path focused checks **8 passed**，Weekly controller **40 passed／1 個具名遷移測試 deselected**，py_compile 通過。較大的三檔合併測試另有 8 個環境失敗（MOPS custody fixture 輸出目錄問題與 `cmd.exe` wrapper 執行結果 99）；因此不宣稱三檔測試全通過。此修復沒有解除任何月營收 `degraded` mapping。
