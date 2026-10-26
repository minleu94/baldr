# 產業方向摘要卡與公告時間對照 QA（2026-10-25）

## 產業方向卡

「產業與題材」首屏將平均日漲幅最高／最低的完整覆蓋題材並排呈現。寬版卡片各占兩欄；中窄版依可用欄數排列。卡片以紅／綠／中性三段比例條顯示題材成員漲／跌／平家數，並明列精確家數、有效成員數與可取得時的題材內上漲率。輔助描述提供與文字相同的分布值；比例條不只用顏色傳達方向。它只描述單一題材成員，不代表整體市場廣度。未提供比例時保留未知，不畫假資料條。

- `tests/test_ui_qt_industry_theme_map_view.py`：**41 passed**；本輪包含卡片文字、分段顯示、輔助描述與寬版欄位位置驗證。
- 與 MOPS 對照及研究頁回歸合併：**122 passed**。
- `tests/test_ui_qt_update_view_workbench.py`：**93 passed**。
- `scripts/qa_validate_update_tab.py`：**25 passed／0 failed／4 skipped**。預設輸出目錄位於沙箱不可寫的 `output/qa/update_tab`；改由既有 `BALDR_UPDATE_TAB_QA_LOG_DIR` 將 QA 報告寫至隔離 scratch 後通過。4 項跳過不計為通過。
- 全域 mypy：**1,150 個來源檔無錯**；本輪修改的 5 個 Python 檔 `py_compile` 通過。
- document-control 對 Feature Map、QA／設計／研究手冊共 12 個功能入口與 7 個指定文件來源檢查通過。涵蓋 `PROJECT_SNAPSHOT` 與 `APPLICATION_MANUAL` 的較廣連結檢查另遇既有 `output` junction WinError 5，指向舊 trial／task 路徑；沒有指向本輪新增錨點或 QA 連結。
- 以 Microsoft JhengHei 字型及一致的合成漲跌資料產生並目視檢查 1380×820 offscreen 截圖：最高／最低題材並排、比率條與家數一致、有效成員分母和非全市場提示同屏可讀；另以 UI 測試核對 1200／900／540 寬度的網格配置。這不是正常 Main 原生桌面視窗、其他 DPI／尺寸、固定試用 EXE 或 Owner UAT 驗收，這些仍未執行。

## 首屏法人淨額分布增量（2026-10-25 root 驗證）

領先／落後題材卡新增題材成員法人淨股數正／負／零的家數分段條，顯示淨股數覆蓋數與題材成員數。漲跌與法人兩種分布皆要求家數與 coverage 為 exact `int`、非負、coverage 大於零且不超過成員數，家數和與 coverage 一致才畫比例；其餘呈現未知並隱藏比例條。題材內上漲率僅在有限 `Decimal` 值介於 0 至 1，且等於上漲家數除以報酬 coverage 時顯示。文字及無障礙描述明示法人分布不是全市場廣度，也不是多家法人共同買進同一股票的統計。此項沿用 `ThemeDailyRow` 欄位，沒有新增金融指標或分母。

- 回歸斷言新增在 `tests/test_ui_qt_industry_theme_map_view.py`，涵蓋 count mismatch、負數、bool 型別、coverage 超分母／非 exact-int，以及上漲率非 Decimal、非有限、越界或與家數不符；零法人覆蓋時顯示未知且不畫比例條。
- 定向 UI 測試 `tests/test_ui_qt_industry_theme_map_view.py`：**41 passed**。另外 final 聚焦組涵蓋產業卡、MOPS crosswalk、Research Console、P0 source center，合計 **169 passed**。
- 強制 Workbench UI 回歸 `tests/test_ui_qt_update_view_workbench.py`：**93 passed**；Update validator **25 passed／0 failed／4 skipped**（4 項跳過不計通過）。
- 全域 mypy：**1,150 個來源檔無錯**；修改 Python 檔 `py_compile` 通過。受控 Windows Job 正常結束，剩餘程序 0、無強制清理，8 GiB／12 程序限制已讀回。
- 初輪失敗均保留於隔離 scratch；短 basetemp 後修正測試夾具與斷言，final 組通過。法人淨額增量沒有新 offscreen 截圖；前一節的漲跌卡截圖不能當作此增量的視覺驗收。
- 尚未以正常 Main 原生桌面視窗、其他 DPI／尺寸、固定試用 EXE 或 Owner UAT 驗收；自動化通過不代表 Gate、資料資格或真人可讀性接受。

## MOPS 公告時間候選對照

Owner 已確認 MOPS 顯示的公告日期與時間可直接作為公告時間戳，無須再次確認。本輪依此授權將原始公告 `announcement_at`（台北 `+08:00`）接入唯讀候選 crosswalk；對照鍵要求市場、公司代碼、報表種類與期間一致，候選保留事件 hash 與原回應 SHA。它只形成公告時間候選，沒有直接改正式 DB 或調整 Gate／來源接受資格。

- 2026-Q2 一般業 Open Data CSV 共 **3,878** 筆公司／報表 profile；MOPS 2026-07-01 至 2026-09-30 已封存窗口中 **3,864 筆有唯一公告時間候選、0 筆多版本歧義、14 筆在所選窗口未觀測**。未觀測不代表未申報。
- 正式 `fundamental_statement_items` 有 **1,645,555** 列，但期間僅到 2024-Q1，沒有任何 2026-Q2 列；因此此表本輪實際解除公告日缺漏降級為 **0 列**。
- `fundamental_current_observations` 雖有 2026-Q2 資料，但在 TWSE 1,084 家與 TPEx 891 家的三種 MOPS current statement HTML 報表中，每個公司／報表鍵各有 **3 個不同 source_version**（共 5,925 個公司／報表鍵）；MOPS 公告事件沒有連到其中任一報表內容 hash／版本的獨立對照鍵。只以公司、期間、報表種類回填會把同一公告時間套到不同報表版本，違反本次要求的同版本連接。這些觀測列也都仍為 `aggregate_feature_eligible=0`，且 basis／單位等其他條件未由公告時間解決。
- 月營收缺公告日列共 **242,651**；既有 availability mapping 的 1,832 個 key 與缺公告日的正式 DB 月別 key 精確交集為 **0**。目前沒有各舊月份對應的 MOPS 月營收公告原件，故本輪實際解除月營收缺公告日降級為 **0 列**，不以 2026-Q2 或其他月份日期代替。
- 正式 DB 是唯讀盤點；沒有寫入／重算。MOPS EZSearch endpoint 授權仍未有可指向該端點及用途的證據。公告時間授權不等於資料來源授權、報表版本接受、單位／basis 驗證、PIT、正式來源或 Gate 通過。

資料來源與查核細節、原始候選 hash、monthly key 結果及 MOPS 授權界線見[資料品質盤點](BALDR_DATA_QUALITY_INVENTORY_20261025.md#2026-10-25-mops-公告時間-crosswalk-與-q2-實際解除數)。所有 QA 僅由隔離 Windows Job 執行；沒有正式資料寫入，輸出日誌與 offscreen 截圖留在本機 scratch，不提交 raw QA。

## 待補的產品證據

領先／落後卡已比先前更容易讀方向，但尚未做到 DannyQuant 完整的市場方向 headline、全市場漲跌寬度和三點觀察摘要。Baldr 目前資料契約不能安全推出全市場廣度，也沒有同買／同賣統計圖；不得以題材成員家數或法人淨額代替。需在取得能證明市場 universe 與成員分母的資料前，將其維持為缺口。畫面工程測試通過不等於外觀比較、正常桌面 GUI、資料 Gate 或 Owner 視覺驗收。
