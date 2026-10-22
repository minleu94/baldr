# 月營收全用途研究管線（後繼 Source）

Owner 已授兩具名OpenData來源全部研究用途；此頁說明新Source的工程入口，不代表既有固定RC已包含，亦不代表全部金融Gate已通。實際範圍看[驗收](../06_qa/MONTHLY_REVENUE_FULL_SCOPE_ACCEPTANCE_20261021.md)，授權／單位／PIT契約看[全用途契約](../03_data/MONTHLY_REVENUE_FULL_SCOPE_CONTRACT.md)。Native停止保持，這些CLI不操作桌面或券商，不修改正式SQLite／資金／排程。

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

`next_cursor`只代表尚未嘗試的後續chunk；失敗項仍列在failures，不因游標前進而算取得。續接時帶同range／plan SHA及`--cursor <next_cursor>`，另用新目錄／report，原失敗資料保持。退出碼2或`data_status=capture_failed`都不能當成功。MOPS歷史授權／單位與PIT仍獨立核，捕獲成功也不自動成金融輸入。

已成功保存的單一歷史capture，可用另外固定的artifact SHA匯入候選歸檔；reader會重核三跳、entity bytes與逐列原件，不把取得成功當用途接受：

```powershell
.\.venv\Scripts\python.exe scripts/monthly_revenue_archive.py --report output/monthly-revenue/history-import-01.json import-history-capture --capture-file <absolute_capture_path> --capture-sha256 <capture_artifact_sha256> --archive-root output/monthly-revenue/history-archive-01
```

追加同樣明選`--parent-sha256`。歷史HTML仍保持獨立`mops.history.*` source，授權未接受、單位Unknown、PIT=false，不能引用兩具名OpenData的授權包放行。

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
