# Baldr UI 資料呈現與響應性盤點（2026-10-28）

## 範圍與判讀方式

唯讀檢視市場探索、個股研究、產業題材、Smart Money、Workbench／投資組合／研究時間軸、Recommendation／Backtest／Research Lab、Update／Runtime／Storage 等主要工作區。這是依目前原始碼與既有測試做的跨頁盤點，沒有切換使用者畫面，也沒有進行原生 GUI 視覺驗收。下列「靜態風險」是由同步 UI 工作量或版面設定推得，沒有實測延遲或窄窗截切證據時不視為已發生的缺陷。

## 本輪已修正

- **Workbench Advice 完整判讀可讀到底**：`advice_presentation_detail` 改為唯讀、換行的文字窗，保留 150–300 logical px 可視高度；內容超出時使用文字窗的垂直捲軸，避免長判讀被卡片高度裁掉。卡片展開狀態只更新前一張與目前這張卡；相同展開狀態直接返回，避免重複更新按鈕、樣式與版面。展開卡仍需重新排版以維持全寬列，沒有做延遲或效能宣稱。
- **個股研究保存 Advice 摘要窄窗裁切**：移除 `summary_saved_advice_label` 的 72 px 高度上限，文字依目前寬度自然換行增高；完整五問仍透過「展開五問證據與限制」查看。
- 操作說明已同步至 [`APPLICATION_MANUAL.md`](../07_guides/APPLICATION_MANUAL.md) 與[個股研究手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md)。

## 其他優先檢視項目

| 優先度 | 頁面與證據 | 判讀 | 建議下一步 |
|---|---|---|---|
| P2 | 每日市場研究：[`daily_market_research_view.py`](../../ui_qt/views/daily_market_research_view.py#L301) 把 `textChanged` 直接接至 `_render_rows`；`L2393–2495` 每次清空並重建最多 13 欄的可見表格，逐列重新建立 item 與提示。 | **同步工作明確；實際卡頓未量測。** | 以較大名單量測輸入期間的 GUI 事件阻塞，再評估短 debounce、預先快取呈現文字，或改為 model/proxy 篩選。回歸入口：`tests/test_ux04_05_daily_market_research_view.py`。 |
| P2 | Research Timeline：[`research_timeline_view.py`](../../ui_qt/views/research_timeline_view.py#L197) 本地搜尋即時呼叫 `_render_entries`；`L312–327` 逐列重建最多 500 筆的表格。 | **同步工作明確；實際卡頓未量測。** | 用 500 筆搜尋情境量測，再評估 debounce 或 QTableView model；保留搜尋結果語義。回歸入口：`tests/test_ui_qt_research_timeline_view.py`。 |
| P2 | Smart Money：[`smart_money_flow_view.py`](../../ui_qt/views/smart_money/smart_money_flow_view.py#L197) 摘要區以水平捲動承載四張固定橫排卡；[`summary_strip.py`](../../ui_qt/views/smart_money/summary_strip.py#L43) 標題使用 11 px。控制列也是單一水平列（`smart_money_flow_view.py:L211–309`）。 | **窄窗資訊發現與控制列擠壓風險；尚未確認實際失焦。** | 在受控窄寬度核對可見性；如確認擠壓，讓摘要卡換列、提高輔助文字字級，並為控制區提供換行或明確的次要條件區。回歸入口：`tests/test_ui_qt_smart_money_flow_view.py`。 |
| P2 | Recommendation 結果表：[`recommendation_view.py`](../../ui_qt/views/recommendation_view.py#L5817) 與 `L5885` 載入時呼叫 `resizeColumnsToContents()`。 | **大結果或長字串量欄寬的同步成本風險；未量測。** | 量測大量候選載入；考慮固定摘要欄寬、伸縮理由欄，將最佳欄寬改成使用者明選動作。回歸入口：`tests/test_ui_qt_recommendation_layout.py`、`tests/test_ui_qt_recommendation_portfolio_results.py`。 |
| P2 | Backtest 診斷：[`analyst_diagnostics_widget.py`](../../ui_qt/views/backtest/analyst_diagnostics_widget.py#L271) 更新時清表並逐列插入；年範圍上限可形成最多 1,200 月列、每列 13 欄（`L94–95,303–335`）。 | **上限情境的同步建立成本；不是常見使用量，也未量測。** | 先 profile 實際長區間；只有確認延遲時才改 model／批次更新或調整展示範圍。回歸入口：`tests/test_ui_qt_research_lab_mode_driven_ui.py`。 |
| P2 | Storage overview：[`storage_overview_view.py`](../../ui_qt/views/storage_overview_view.py#L34) 以兩張表格呈現，欄寬依內容，水平捲軸固定顯示。 | **呈現形式確認；窄窗截欄為靜態風險。** | 核對窄窗欄位可達性；可補每個位置的容量摘要／比例，並讓捲軸只在內容溢出時顯示。回歸入口：`tests/test_ui_qt_storage_overview.py`。 |
| P2 | Update 狀態卡：[`update_view.py`](../../ui_qt/views/update_view.py#L170) 的 `extra_label` 未設定換行，窄版仍以兩欄排列（來源約 `L1637–1650`）。 | **文字欄位設定確認；是否溢出未做 GUI 核對。** | 另行核對長覆蓋率／期別提示的窄窗呈現，再決定是否加換行。該檔在盤點時已有其他未提交修改，本輪未改動。回歸入口：`tests/test_ui_qt_update_view_workbench.py`。 |
| P3 | 排程成熟分布：[`scheduled_evidence_status_view.py`](../../ui_qt/views/scheduled_evidence_status_view.py#L318) 使用 8 pt 圖例、計數及提示（另見 `L393–399`、`L428–433`）。 | **字級偏小的來源可確認；未做原生字型驗收。** | 視覺核對後可提高至輔助文字字級並保留數字對齊。 |
| P2 | 題材成員：[`industry_theme_map_view.py`](../../ui_qt/views/industry_theme_map_view.py#L4725) 每頁最多 50 筆，換頁時同時建卡片與表格，即使其中一種呈現隱藏。 | **額外元件建立可確認；效益未量測。** | 量測換頁成本後再考慮延後建立未選的呈現方式。題材頁本身已有排行卡、指標卡及成交額 treemap；沒有找到與 Advice 相同的長文剪切證據。回歸入口：`tests/test_ui_qt_industry_theme_map_view.py`。 |

Backtest 結果圖表已採需要時建立，這輪未找到需立即重做的證據；Runtime 已有窄版單欄與可折疊診斷，也未找到高於上述項目的明確缺陷。Smart Money 正負流量色與價格方向色屬不同語意，本輪沒有把法人買賣正負直接改成台股紅漲綠跌。

## 驗證與限制

- `tests/test_workbench_advice_contract.py`、`tests/test_ui_qt_workbench_view.py`、`tests/test_ui_qt_stock_research_evidence_summary.py`：**86 passed**。
- 必要 `tests/test_ui_qt_update_view_workbench.py`：**98 passed**。
- 6 個本輪變更 Python source/test 檔 `py_compile`：通過。
- 本輪兩個修改 source 檔 targeted mypy：通過；repo-wide mypy 被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` line-continuation 語法錯誤阻止。
- `scripts/qa_validate_update_tab.py`：未能完成；建立 `output/qa/update_tab/RUN_LOG.txt` 時收到 `PermissionError 13`，受限工作區不能寫入 repo output。
- `tests/test_recommendation_service_calibration_integration.py` 另選 3 項整合測試：**3 failed**，兩項因 sandbox `os.link` 回傳 `WinError 5`，一項在 Advice 呈現前即因 fixture 的 `AAA` calibration projection 缺少而 `KeyError`；它們沒有驗證到本輪的捲動 UI。其餘尚未做原生 GUI／Owner UAT。這些失敗保留為未解，不外推為整個 UI 已驗收。
- `document_control init-task` 無法建立本輪 task JSON：repo `output` 儲存根目錄不可讀。沒有碰觸該目錄或其他 Agent 的未提交修改。

## 2026-10-28 使用者旅程補充

依使用者實際回報的 1569／2026-10-28 Advice 保存與讀回畫面，發現「可保存」和「可理解、可回找」是兩個不同的驗收點：使用者雖已讀回「已納入研究」，卻要在 Advice、來源說明與每日詳情之間自行拼接；每日來源內容也把判讀摘要、欄位代碼與技術追蹤混成長段文字。此補充延伸上方全工作區靜態盤點，不代表原生 GUI／Owner UAT 已完成。

### Gate 1 首輪結構調整

- Advice 選列詳情按「判讀依據 → 原始結果與來源 → 策略作者說明（選填）→ 研究決定與追蹤」排列。
- 「已納入研究／略過」作為主要操作；註記、重新讀取、下次檢視放在後續操作列。
- 結果 ID、股票、決策日、資料日與目前每日候選完全吻合時，Advice 顯示「查看來源與排除」入口；點擊後切到總覽、展開同一份每日來源詳情並捲至明細。不吻合或資料過期時入口隱藏。
- 每日來源明細改以「本次結果、候選篩選與排除、證據狀態、進階追蹤資料」分段；source ID、snapshot、事件 ID 和診斷仍保留在技術欄位。
- 有保存結果 ID 的 Advice 增加文字連結，可直接打開「研究紀錄與覆盤」並以該 ID 篩選；超過 500 筆時沿原有搜尋完整歷史路徑查找。查無匹配時不宣稱未保存，也不把記錄補回今日清單。
- 長 Advice 詳情可視高度維持 120–240 logical px；內容較長仍可在內部文字窗捲動。這是版面限制，不宣稱已證明最佳高度。
- 只改呈現、分組和導覽，未改 Advice 輸出、來源資格、金融邏輯、Journal 寫入契約。

### 補充驗證

- Workbench Advice contract＋每日旅程＋Research Timeline：**64 passed**。
- MainWindow 跨頁決策旅程改驗 Advice 歷史連結傳遞精確 result ID：**1 passed**。
- 必要 Workbench Update UI：**98 passed**。
- `scripts/qa_validate_update_tab.py`：受控核准後完成，**25 passed／0 failed／4 skipped**；首次在工作區權限下嘗試時未能建立固定 log，之後通過核准的受控執行完成。
- 本輪 4 個修改 source targeted mypy：通過；repo-wide mypy 仍因未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤，在檢查其他模組前停止。
- 原生 GUI／Owner UAT 和全 16 路由逐頁視覺驗收未執行；其他工作區仍依本報告「其他優先檢視項目」排序。
