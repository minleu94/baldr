# 月營收全用途研究管線（後繼 Source）

Owner 已授兩具名OpenData來源全部研究用途；此頁說明新Source的工程入口，不代表既有固定RC已包含，亦不代表全部金融Gate已通。實際範圍看[驗收](../06_qa/MONTHLY_REVENUE_FULL_SCOPE_ACCEPTANCE_20261021.md)，授權／單位／PIT契約看[全用途契約](../03_data/MONTHLY_REVENUE_FULL_SCOPE_CONTRACT.md)。Native停止保持，這些CLI不操作桌面或券商，不修改正式SQLite／資金／排程。

依 2026-10-28 Owner 研究取用指示，不能只因 MOPS／TWSE／TPEx 端點條款或自動化授權尚未裁定，就停止明確要求的公開資料研究取用；此為執行流程指示，不代表來源接受或法律裁定。依一般公開存取方式取得原件並記錄 URL、擷取時間、response metadata、bytes 與 SHA。不得繞過登入、CAPTCHA 或其他技術存取限制。取得、公告 timestamp、數值版本橋、PIT 與下游 Gate 是分開狀態，依[全用途契約](../03_data/MONTHLY_REVENUE_FULL_SCOPE_CONTRACT.md#owner-研究取用指示2026-10-28)判讀。

## 離線規劃歷史範圍

在repo根目錄執行：

```powershell
.\.venv\Scripts\python.exe scripts/monthly_revenue_archive.py plan-history --start-period 2007-01 --end-period 2026-09
```

這只產生月份／市場清冊、最多四組市場月份的chunk及固定plan SHA，不連線。一次範圍最多240個月，長期資料可再明選其他範圍及獨立歸檔分片；不以latest或檔案排序選版本。

## 明選一個歷史chunk

以規劃回傳的plan SHA代入；capture-root必須是repo `output`下全新目錄：

```powershell
.\.venv\Scripts\python.exe scripts/monthly_revenue_archive.py --report output/monthly-revenue/attempt-01.json capture-history-chunk --start-period 2026-07 --end-period 2026-08 --plan-sha256 <plan_sha256> --capture-root output/monthly-revenue/history-01 --transport-mode redirect_chain_v1
```

`redirect_chain_v1`依官方POST→popup→HTML流程，`direct_static_v1`只做靜態URL取得；模式由caller明選，失敗不自動fallback、不重試、不繞challenge。每次讀取以八秒期限的剩餘時間設socket timeout並檢查monotonic；HTTP程式庫內部若遭slow-trickle header／trailer，這不是已證明的八秒硬wall-clock上限，執行時仍須外層owned Job期限。逐跳／合計原件及收據都有byte上限。新capture收據保留實際HTTP、Transfer-Encoding、EOF及經HTTP高層transfer decoding的entity bytes或觀測前綴；沒有完整EOF的前綴不能當完整response SHA。先前誤讀底層wire framing的失敗收據保持原貌，不回頭剝標記重封成功原件。

MOPS 靜態月報頁首的「出表日期」屬整份報表的日期觀測，不是每家公司、每月份的原始公告 timestamp。靜態報表可能在多年後重出或更新；capture 會記錄 `availability_at=null`、`retrospective_capture_only`、`historical_pit_eligible=false`。不能把它傳給歷史公告 mapping builder 當 `announced_date`／`available_date`。只有具公司、月份與原始公告時間的公告事件資料，才可建立月營收公告候選；Owner 對公告 timestamp 的授權不改變靜態報表欄位語意。

新的 MOPS F22 月營收公告 mapping 還必須提供 `target_source_version`，其值須與要套用日期的 `fundamental_monthly_revenues.source_version` 完全相等。loader 拒絕缺少目標版本的 MOPS mapping；provider 對版本不符的列不套用 mapping，避免只憑公司＋月份把公告時間套到其他快照。此欄位是明確的套用範圍，不是版本證據本身；candidate 仍須保存原始 MOPS 事件 response、唯一公司／月份／公告時間、數值內容與修訂關聯，才能證明公告事件與目標數值快照的對應。F22 頁面人工可讀不等於 HTTP response custody，mapping merge 也不會自動回寫正式 SQLite。

Research Console 的月營收品質摘要也會讀這份 mapping；只有 `formal-availability.v2`、官方公告 hash 與公司／期別／公告日／target source version 精確吻合時，才把相應 SQLite 靜態列自「日期待核實」數扣除。這只改善可追溯性顯示，不代表其他公司、期間、單位、修訂或 MOPS 授權已核實，也不授 PIT／Gate／ML 資格。已匹配的 2330／2026-05、06 與摘要實際計數見[資料品質 QA](../06_qa/BALDR_DATA_QUALITY_INVENTORY_20261025.md#2026-10-27-mops-f22-2330-q2-monthly-exact-version-backfill)。

### 每日 OpenAPI 月營收快照與公告日期分流（2026-10-29）

`scripts/capture_monthly_revenue_research_candidate.py` 是排程候選採集器。TWSE／TPEx OpenAPI 的 `出表日期` 是報表層級欄位，不能直接當成每家公司的公告事件；程式保存完整 raw response、normalized snapshot CSV、response hash、source version 和 capture clock，availability CSV 留空並標示缺少 issuer-period 公告證據。修復後 CLI 於 2026-10-29 實跑 readback verified：兩個市場 1,981 列，availability 0 row；這是成功保存現況 research snapshot，不代表 formal mapping、正式 DB 更新或 historical PIT。`baldr-data-update-quick-daily` Task XML 已確認每日 04:20 啟用並呼叫 Quick `.cmd`；`.cmd` 預設開啟此候選採集旗標，最近排程 receipt 10/28 的 child 使用修正前版本而 rejected，10/29 CLI 手動實跑成功，須以後續排程 receipt 確認更新後的排程執行結果。歷史公告時間仍由 MOPS F22 事件流另行取得；numeric snapshot 的可得日依實際保存／固定快照政策，不以公告時間前移。2026-07..09 正式表 5,585 列中，F22 mapping 已以完整 DB `source_version` 精確綁定 5,584 列並 guarded apply；這 5,584 列 `observed`，`available_date=2026-10-30`，缺 6884／2026-08 仍 degraded。以 10/30 為 cutoff 才可看到 2026-09。詳[候選修復與現況 QA](../06_qa/MOPS_MONTHLY_REVENUE_CONFLICT_REAUDIT_20261028.md#2026-10-29-排程與修復後候選實跑)。

`next_cursor`只代表尚未嘗試的後續chunk；失敗項仍列在failures，不因游標前進而算取得。續接時帶同range／plan SHA及`--cursor <next_cursor>`，另用新目錄／report，原失敗資料保持。退出碼2或`data_status=capture_failed`都不能當成功。MOPS歷史授權／單位與PIT仍獨立核，捕獲成功也不自動成金融輸入。

已成功保存的單一歷史capture，可用另外固定的artifact SHA匯入候選歸檔；reader會重核三跳、entity bytes與逐列原件，不把取得成功當用途接受：

```powershell
.\.venv\Scripts\python.exe scripts/monthly_revenue_archive.py --report output/monthly-revenue/history-import-01.json import-history-capture --capture-file <absolute_capture_path> --capture-sha256 <capture_artifact_sha256> --archive-root output/monthly-revenue/history-archive-01
```

追加同樣明選`--parent-sha256`。歷史HTML仍保持獨立`mops.history.*` source，不能引用兩具名OpenData的授權包放行；依 Owner 2026-10-28 指示，條款／授權未裁定不得單獨阻擋明確要求的公開研究取用，狀態須如實記錄。單位Unknown、PIT=false 等資料資格仍各自判定，不因擷取成功改變。

## 重用已保存的官方OpenData原件

`import-opendata-capture`接受已保存的雙市場capture目錄（`receipt.json`與`raw/twse.json`、`raw/tpex.json`），要求外部固定receipt SHA，重新核原HTTP／EOF／raw SHA及parser：

```powershell
.\.venv\Scripts\python.exe scripts/monthly_revenue_archive.py --report output/monthly-revenue/import-01.json import-opendata-capture --capture-directory <capture_directory> --receipt-sha256 <receipt_sha256> --archive-root output/monthly-revenue/archive-01
```

追加另帶`--parent-sha256 <archive_sha256>`；這是明選immutable parent，沒有mutable head或跨程序CAS。raw以內容hash只保留一次，新index create-only，原index保持。來源或hash不符時拒絕，不能改label補成MOPS。原金額維持未知單位，不換算TWD；Unknown百分率仍為None，不補零。

## 讀回固定版本

```powershell
.\.venv\Scripts\python.exe scripts/monthly_revenue_archive.py query --archive-root <archive_root> --archive-sha256 <archive_sha256> --market twse --stock-code 2330 --period 2026-09 --cutoff-at 2026-10-22T12:00:00+08:00
```

cutoff須有時區。先核index與全部原件再選版；結果保留市場、來源、原始欄位／單位狀態、capture與實際歸檔可見時鐘。若尚未到實際落盤向上整點，回`not_visible_by_cutoff`，不能改時鐘解鎖。相同可見時間不同內容／不同修訂明確拒絕，不隨機挑選。

`observation_as_of_verified`只代表這份本機觀測版本在該cutoff可見；`formal_pit_eligible=false`仍不能給歷史回測、ML訓練或正式交易用途。source/use資格reader與下游研究service的整合仍按上述驗收分軌，正式Scoring、Paper／Forward及Promotion各自保留Gate。

## 以固定資格包執行當期百分率研究

`research-current`要求兩市場各自的資格包路徑及外部SHA。資格包須由既有來源接受revision、授權／品質／PIT文件與官方dataset／license／raw原件組成；不是填入用途字串便可放行。每次操作重讀並核hash，證據被改動、來源失配、未到可用時間或接受時間時拒絕。

```powershell
.\.venv\Scripts\python.exe scripts/monthly_revenue_archive.py --report output/monthly-revenue/research-01.json research-current --capture-directory <capture_directory> --receipt-sha256 <receipt_sha256> --binding twse <twse_binding_path> <twse_binding_sha256> --binding tpex <tpex_binding_path> <tpex_binding_sha256> --metric revenue_yoy_percent --minimum <明選百分率下限>
```

`--metric`可選原公布YoY、MoM或累計YoY百分率；不以未知金額反算。`--minimum`沒有預設值，省略便不執行條件篩選。`--cutoff-at`須帶時區，省略時使用本次操作時間。輸出原值、Unknown及拒絕原因、原件身份、可見時鐘，以及各市場分開的shadow研究排名；此排名不改正式ScoringEngine權重，不代表投資建議或Paper成交資格。輸出保留機關顯名與授權連結；資格包只覆蓋固定raw批次，後續新批次須另核品質與版本。

`--report`是全域參數，必須放在子命令前；目的地僅限repo `output`的新檔，已存在時拒絕覆寫。`rejected`或退出碼2應依`error`處理；不能透過改時鐘、重寫原件或取消SHA核對解鎖。

MOPS 完整 HTML 若宣告 Big5 且含 CP950 擴充，transport 只對 exact 官方 MOPS host 提供 strict CP950 相容路徑，不使用 replacement decode；原 bytes、宣告與 SHA 保留。不完整 EOF 仍不能匯入。已有完整三跳而舊解析失敗時，可由工程流程從固定 SHA 原件離線重建、用既有 reader 重驗後再以 `import-history-capture` 匯入新的隔離 archive；不重抓、改原 FAIL 或倒填官方可用時間。2026-06 的新隔離候選及尚未接受的單位／用途界線見 [全用途資料契約](../03_data/MONTHLY_REVENUE_FULL_SCOPE_CONTRACT.md)。

六月兩份固定HTML另有獨立scale-only proof，工程API建立／讀回都必須重驗原capture；僅能標示「原報表千元尺度、幣別未知」，不能放入archive既有完整unit proof欄位、改unit_status或直接乘1000換算TWD。它只覆蓋具名產業表與五個金額欄，不影響三個原公布百分率、兩個OpenAPI、既有research-current資格或歷史PIT。空存託憑證表與全市場合計不計公司coverage；精確原件／proof SHA及實際QA見[Track B驗收](../06_qa/BALDR_TRACK_B_DATA_OPERATIONS_20261022.md)。

## 固定快照公告 mapping 回填（2026-10-29）

2020–2025 固定 MOPS snapshot 已透過 `scripts/apply_monthly_revenue_recovery.py` 的 guarded recovery 流程正式回填。snapshot 數值的 `available_date` 為 2026-06-18；F22 公告事件的 `announced_date`／`announced_at` 另行保留，兩者不可互相替代。reader 依 `available_date` 執行 PIT cutoff，因此公告較早不會令事後取得的 snapshot 提前可見。

同版本數值相同時 recovery writer 只更新 availability／quality 欄位並保留 `created_at`；來源版本或 Decimal 數值不同即中止。此次 126,359 列轉為 observed，540 列因缺事件／市場標籤不一致／事件晚於 snapshot 仍 degraded。執行前備份與候選 readback 收據見[月營收回填 QA](../06_qa/MOPS_MONTHLY_REVENUE_CONFLICT_REAUDIT_20261028.md#2026-10-29-正式回填與讀回)。這是固定範圍 recovery，不會由一般 mapping CSV merge 自動更新正式 SQLite，也不代表其他 source versions 可直接沿用此例外。

截至 2026-10-29，同一固定 snapshot recovery 已涵蓋 2014-04..2026-04 共 242,651 列，其中 241,925 observed、726 degraded。5236／8908 共 290 筆原先因 snapshot `market` 與 F22 event market 不同而排除的唯一 code／period 鍵，經 2014-04 MOPS 明細原件核對後已正式映射。仍 degraded 的 726 列由 689 無 harvest event、36 公告晚於 2026-06-18 snapshot available date、1 公告晚於 row capture 組成；應先查缺期事件／申報適用性及晚期版本關係，再決定是否有新 evidence 可用。這些列的數值 snapshot 自 2026-06-18 起仍可顯示，公告完整性 quality 維持 degraded；不得把 capture-only baseline 誤當公告 mapping。完整範圍、收據與剩餘理由見[最終 MOPS QA](../06_qa/MOPS_MONTHLY_REVENUE_CONFLICT_REAUDIT_20261028.md#2026-10-29-市場標籤裁決與最終剩餘缺口)。
