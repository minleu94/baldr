# Baldr UI 資料呈現與響應性盤點（2026-10-28）

## 範圍與判讀方式

唯讀檢視市場探索、個股研究、產業題材、Smart Money、Workbench／投資組合／研究時間軸、Recommendation／Backtest／Research Lab、Update／Runtime／Storage 等主要工作區。這是依目前原始碼與既有測試做的跨頁盤點，沒有切換使用者畫面，也沒有進行原生 GUI 視覺驗收。下列「靜態風險」是由同步 UI 工作量或版面設定推得，沒有實測延遲或窄窗截切證據時不視為已發生的缺陷。

## 本輪已修正

- **Workbench Advice 完整判讀可讀到底**：`advice_presentation_detail` 改為唯讀、換行的文字窗，保留 150–300 logical px 可視高度；內容超出時使用文字窗的垂直捲軸，避免長判讀被卡片高度裁掉。卡片展開狀態只更新前一張與目前這張卡；相同展開狀態直接返回，避免重複更新按鈕、樣式與版面。展開卡仍需重新排版以維持全寬列，沒有做延遲或效能宣稱。
- **個股研究保存 Advice 摘要窄窗裁切**：移除 `summary_saved_advice_label` 的 72 px 高度上限，文字依目前寬度自然換行增高；完整五問仍透過「展開五問證據與限制」查看。
- **每日研究條件結果清單分組**：將代號搜尋、狀態篩選、局部列數摘要、排序與原始排名控制收進表格前的「結果清單」區塊；「更新研究快照／重讀已發布快照」留在獨立快照操作列。每日快照最多 16 檔，因此原先對此頁重建表格成本的擔憂不能外推為實際卡頓，這次只修正資訊位置與閱讀關聯，沒有加入 debounce 或改動資料篩選語義。`tests/test_ux04_05_daily_market_research_view.py`：**4 passed**，含控制項分組斷言。
- **研究時間軸清單與查找操作分組**：把來源篩選、股票／result ID 搜尋及重新讀取收入「查找已保存研究紀錄」區；左右窗格分別標示「研究紀錄清單」與「所選紀錄與延伸操作」，讓歷史清單和選取後的原件／對照功能有明確標題。`tests/test_ui_qt_research_timeline_view.py`：**17 passed**。完整歷史搜尋已有 250 ms debounce；本次不調整搜尋資料或 500 筆呈現上限。
- **Update 狀態卡長來源文字**：額外資訊標籤啟用自然換行並允許縮小寬度，避免已匯入期別、可用期別、coverage 等長欄位被單行撐開。只改文字呈現；資料狀態語義不變。必要 Update UI 回歸：**98 passed**。
- **排程成熟分布小字**：圖例、成熟計數及未知訊息由 8 pt 提至 9 pt；色義及數值不變。`tests/test_ui_qt_evidence_review_dashboards.py`：**60 passed**。
- **題材成員長卡片清單**：預設成員卡片從單欄直向堆疊改為依可用寬度排 1／2／3 欄，每頁上限仍是 50 位；資料表切換、同快照分頁與選取操作保留。50 位窄／中／寬三種佈局斷言及完整題材頁 UI 回歸：**62 passed**；Main 成員導覽回歸另 **8 passed**。
- 操作說明已同步至 [`APPLICATION_MANUAL.md`](../07_guides/APPLICATION_MANUAL.md) 與[個股研究手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md)。

## 其他優先檢視項目

| 優先度 | 頁面與證據 | 判讀 | 建議下一步 |
|---|---|---|---|
| P2 | 每日市場研究：搜尋直接觸發可見列重建；每份 cohort 最多 16 檔、表格 13 欄。搜尋、狀態篩選、排序與來源更新操作曾分散於結果摘要和表格附近。 | **控制與結果已重組**：表格前新增「結果清單」組，操作列獨立；回歸測試確認控制項同組、更新／重讀不混入該組，4 passed。基於 16 檔上限，靜態程式量不足以證明有可感知延遲，不以此項推定卡頓。 | 原生 GUI／Owner UAT 尚待人工確認窄窗和實際掃讀；回歸入口：`tests/test_ux04_05_daily_market_research_view.py`。 |
| P2 | Research Timeline：本地搜尋呼叫 `_render_entries`，每列最多重建 4 個儲存格；完整 Journal 搜尋另有 250 ms debounce，顯示最多 500 筆。 | **搜尋設定與清單／詳情曾缺少可見分區標題，已補標題及控制分組；回歸 17 passed。** | 原生 GUI 尚待確認不同寬度下 splitter 可讀性；如實測 500 筆鍵入有明顯停頓，再 profile 後決定是否調整模型。回歸入口：`tests/test_ui_qt_research_timeline_view.py`。 |
| P2 | Smart Money：[`smart_money_flow_view.py`](../../ui_qt/views/smart_money/smart_money_flow_view.py) 摘要卡與控制列原本都使用水平捲動區。 | **已修正版面風險**：摘要卡按寬度排 4／2／1 欄；掃描控制按寬度排單列／雙列／三列；掃描動作與觀察清單在首列，週期／範圍／圖表和搜尋／列數／品質各自成組，移除這兩處水平捲動容器。 | 保留既有市場摘要母體、搜尋範圍、掃描與表格契約；原生 GUI 視覺仍待人工確認。回歸入口：`tests/test_ui_qt_smart_money_flow_view.py`、`tests/test_ui_qt_market_layout.py`。 |
| P2 | Recommendation 結果表：結果載入先前呼叫 `resizeColumnsToContents()`；長理由會參與整欄寬度估算。 | **已修摘要表欄寬風險**：摘要欄採穩定初始寬度、理由欄初始 260 px，欄寬可拖曳；完整理由由詳情與儲存格提示閱讀，擴展欄位維持原資料。推薦版面／保存讀回測試 16 passed。推薦投資組合結果測試在 Qt WebEngine 建立回測圖表時觸發 Windows fatal exception，該測試未完成。 | 原生 GUI 視覺與 Owner UAT 尚待人工驗收；回歸入口：`tests/test_ui_qt_recommendation_layout.py`、`tests/test_ui_qt_saved_recommendation_compact_layout.py`、`tests/test_ui_qt_recommendation_portfolio_results.py`。 |
| P2 | Backtest 診斷：[`analyst_diagnostics_widget.py`](../../ui_qt/views/backtest/analyst_diagnostics_widget.py#L271) 更新時清表並逐列插入；年範圍上限可形成最多 1,200 月列、每列 13 欄（`L94–95,303–335`）。 | **上限情境的同步建立成本；不是常見使用量，也未量測。** | 先 profile 實際長區間；只有確認延遲時才改 model／批次更新或調整展示範圍。回歸入口：`tests/test_ui_qt_research_lab_mode_driven_ui.py`。 |
| P2 | Storage overview：原兩張表格無區塊標題，欄寬依內容且水平捲軸固定顯示。 | **已調整版面方向**：分為磁碟容量與明示根項目兩區；摘要明示位置／項目數；欄位採掃讀寬度，水平捲軸僅於溢出時顯示，完整文字可由儲存格提示讀取。新增窄窗版面測試通過；worker 測試遇 sandbox 目錄掃描 `WinError 5 Access is denied`。提權重跑在開啟 QA 子程序前被鎖檔讀取權限拒絕。 | 需在可讀取測試目錄且可使用 QA 鎖的環境完成 worker 回歸；原生 GUI 視覺仍待 Owner 驗收。回歸入口：`tests/test_ui_qt_storage_overview.py`。 |
| P2 | Update 狀態卡 `extra_label` 顯示覆蓋率、期別與狀態補充資訊。 | **已啟用換行並允許標籤收縮；**文字仍由原來來源資訊組成，未改狀態／資格。必要 Update UI 回歸入口：`tests/test_ui_qt_update_view_workbench.py`。 |
| P3 | 排程成熟分布：圖例、成熟計數及未知訊息。 | **8 pt 提為 9 pt；**既有正負色義、計數、Unknown 語義保留，聚焦回歸 60 passed。 | 原生字型及 DPI 驗收仍待人工確認。 |
| P2 | 題材成員：[`industry_theme_map_view.py`](../../ui_qt/views/industry_theme_map_view.py#L4523) 預設卡片每頁最多 50 張。 | **已改為 1／2／3 欄響應式網格；**仍保留 50 位分頁及資料表切換。50 位三寬度斷言＋完整題材頁 UI：62 passed，Main 成員導覽 8 passed。卡片／表格仍同時建立屬隱藏元件成本，尚無換頁延遲證據，不據此宣稱卡頓。 | Owner 原生 GUI 確認窄／寬視窗卡片文字和可讀高度；回歸入口：`tests/test_ui_qt_industry_theme_map_view.py`。 |

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

## 2026-10-28 第二輪：Smart Money 控制與摘要分組

Smart Money 的四張摘要卡按可用寬度改排 4／2／1 欄，不再要求橫向捲動；掃描器控制區在寬版採單列，中版分成「標題／主要動作」與「條件／狀態」兩列，窄版再分成標題動作、掃描條件、結果狀態三列。開始掃描與觀察清單留在標題操作列，週期、範圍、圖表選項、搜尋、列數與品質提示按使用順序排列。主表計算、摘要母體與篩選語義沒有改變。

- `tests/test_ui_qt_smart_money_flow_view.py`＋`tests/test_ui_qt_market_layout.py`：**36 passed**；包含 390、600、1400、2293 px 視窗尺寸下控制元件幾何仍在容器內、摘要欄數與控制列數切換。
- Offscreen Qt 版面測試核對控制元件幾何與換列；這不能代替原生字型視覺檢查或 Owner UAT。

## 2026-10-28 第三輪：Recommendation 結果表初始欄寬

Recommendation 結果載入不再按候選內容逐欄自動量寬。代號、名稱、價格與分數採初始摘要寬度；理由欄初始 260 px，並可由使用者拖曳調整。長理由在結果詳情與儲存格提示閱讀；展開延伸欄位仍保留原資料欄與排序，不改推薦內容、來源資格或保存契約。

- `tests/test_ui_qt_recommendation_layout.py`＋`tests/test_ui_qt_saved_recommendation_compact_layout.py`：**16 passed**，涵蓋理由欄寬、全文 tooltip、延伸欄切換及讀回版面。
- `tests/test_ui_qt_recommendation_portfolio_results.py` 與前述測試同批執行時，Qt WebEngine 在 `fast_chart_widget.py` 建立圖表時觸發 Windows fatal exception；另行隔離推薦版面／保存讀回後通過。組合測試未驗收。
- Offscreen Qt 驗證通過；尚未做原生 GUI 視覺確認或 Owner UAT。

## 2026-10-28 第四輪：Workbench Advice 判讀摘要分組

「所選建議判讀」由連續欄位長段落改成「主要理由／限制、證據狀態、執行限制、策略版本說明、保存來源逐股證據」分組，並以短項目呈現前三項理由；常見英文代碼在摘要中改用中文，完整原文仍保留在提示、詳情與無障礙描述。完整理由、風險、失效條件與來源追溯仍保留在下方共用證據詳情。未提供與明示未知維持原語意，不補值或改 Advice 動作。摘要加上 accent 左側標記，提示這是目前選取列的判讀卡。

- 摘要分組版本 `tests/test_ui_qt_workbench_view.py`＋`tests/test_workbench_advice_contract.py`：**74 passed**；涵蓋分組、選填作者欄位、未知信心／成熟度、完整理由和來源提示。
- 隨後加入常見代碼中文化與摘要色彩標記；py_compile 與 targeted mypy 通過，但受控 QA 啟動器因可用實體記憶體低於 8 GiB 拒絕重跑，這些最後變更尚未取得測試結果。
- Offscreen Qt 測試通過；尚未做原生 GUI 字型視覺確認或 Owner UAT。

## 2026-10-28 第五輪：Storage overview 分區與欄位可達性

儲存維護頁將磁碟容量與明示根項目分組，分別顯示位置數、項目數及大小完整／不完整筆數。移除內容自動量寬與常駐水平捲動，改為可拖曳的掃讀欄寬、溢出時捲動，儲存格提示保留完整路徑與狀態。容量仍是整顆磁碟容量，不跨位置相加；盤點與保留契約不變。

- `tests/test_ui_qt_storage_overview.py`：**4 passed、1 failed**。失敗在原 worker 測試；sandbox 對測試目錄列舉回傳 `WinError 5 Access is denied`，應用因此明示盤點未完成。提權重跑在讀取專案 QA 鎖時被拒絕，worker 尚未驗證。
- Offscreen Qt 版面與唯讀控制檢查通過；尚未做原生 GUI／Owner UAT。
