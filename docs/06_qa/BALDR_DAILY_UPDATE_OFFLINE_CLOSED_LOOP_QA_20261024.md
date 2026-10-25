# Data Update 離線閉環與路徑防護 QA — 2026-10-24

## 結果摘要

本次修復讓隔離的 Data Update fixture 從 daily-price 同步一路寫入 SQLite、計算技術指標，再由資料狀態服務讀回；既有的 M73 決策品質範圍語義也完成聚焦回歸。這是合成資料上的工程閉環，不是正式資料來源驗收，也不表示 freshness、PIT、ML 或排程 Gate 通過。

## 修復內容

- `excluded_daily_price_revision` 改以逐層 `lstat` 檢查資料根目錄，拒絕 symlink、junction/reparse point 和非目錄元件，避免 Windows 沙箱下對有效路徑呼叫 `Path.resolve(strict=True)` 造成拒絕存取。
- `formal_technical_raw_alias_repair` 對 SQLite 檔逐層檢查路徑元件，拒絕連結／reparse point，並確認終點是一般檔案；不要求對活躍 SQLite writer 執行 Windows final-path query。
- `twse_daily_price_publication` 在缺少日期及 projection manifest 時回傳 `unknown / producer_manifest_missing`，不把缺來源證據寫成 publication failure 或成功證據。
- 新增兩項路徑回歸測試，並保留既有「legacy/skipped CSV sync 不產生新 evidence」測試。
- M73 延續既定 Owner 決策：股票篩選只作用於項目列表，分數卡仍顯示最新整體覆盤分數，最低分數門檻只過濾項目列，不重算分數。

## 驗證收據

- 路徑／publication 針對性回歸：3 passed。
- 決策品質 dashboard 聚焦測試：65 passed。
- Update Workbench 必要回歸：89 passed。
- `scripts/qa_validate_update_tab.py`：25 passed、0 failed、4 skipped。隔離 fixture 寫入 daily、market、industry 各 12 筆、broker 1 筆；技術指標 12 筆，status `ok`，fixture 日期 2026-07-16。四項跳過為真實 daily/market/industry 下載及 `merge_daily_data` 實際合併；沒有觸碰正式資料。
- mypy：1,144 個來源檔無問題；變更 Python 檔 `py_compile` 成功。
- 受控 Windows Job 收據顯示工作已結束，無殘留程序，未觸發強制清理。
- 較廣的 data guard／SQLite publication 測試批次**未通過**：50 failed、18 passed、1 skipped。已見錯誤集中於 Windows 沙箱建立／讀取深層 pytest 暫存路徑時的 `WinError 5`／`FileNotFoundError`。這是已觀察到的環境路徑錯誤，不能據此把該批測試標成通過；目前只有上述針對性回歸和閉環 validator 通過。

## 未接受的 Gate 與範圍

這次沒有連正式外部資料源，也沒有驗證真實來源日期、來源 manifest、完整歷史覆蓋、PIT sealed labels、ML walk-forward、模型 promotion、自然排程或 Owner UAT。缺 manifest 的案例仍是 `unknown`。要解開這些 Gate，需要各 Gate 要求的正式來源或成熟觀測證據；Owner 對產品方向的授權不能替代這些資料證據。

## 可重現入口

- `scripts/qa_validate_update_tab.py`
- `tests/test_excluded_daily_price_revision.py`
- `tests/test_formal_technical_raw_alias_writer_context.py`
- `tests/test_twse_daily_price_sqlite_publication.py`

## 10/25 官方查無資料警告修正

官方資料無列只證明當次請求沒有取得資料；不能單憑此結果推成休市或颱風。快速更新 warning 已改為「TWSE 官方當次查詢回覆無資料，已略過日期；休市狀態未由此回覆確認」，保留該日期為 skipped，不補值、不提升為完整行情。資料更新手冊已同步說明需用另外核驗的官方日曆判斷休市狀態。

受控 Windows Job 執行 `tests/test_scheduled_data_update_runner.py`：**32 passed、2 skipped**；runner 與測試檔 `py_compile` 通過。receipt SHA-256 `ABDA87D1FAEA62FCE00C82A8A9D4FF226EC9980C8FE3208F114260D5A459DA3B`；啟動前可用 RAM 24,782,254,080 bytes；Job limits read-back 為 kill-on-close、8 GiB、12 程序；自然結束、remaining processes 0、Job 關閉、執行鎖釋放，沒有強制回收。兩項 skipped 是測試在 Windows 沙箱解析 pytest 建立的輸出根目錄時遭拒，相關產業資料擷取測試依契約 fail closed；skipped 不計為通過。
