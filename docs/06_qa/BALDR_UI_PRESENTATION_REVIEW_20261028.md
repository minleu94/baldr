# Baldr UI 資料呈現與響應性盤點（2026-10-28）

## 範圍與判讀方式

唯讀檢視市場探索、個股研究、產業題材、Smart Money、Workbench／投資組合／研究時間軸、Recommendation／Backtest／Research Lab、Update／Runtime／Storage 等主要工作區。這是依目前原始碼與既有測試做的跨頁盤點，沒有切換使用者畫面，也沒有進行原生 GUI 視覺驗收。下列「靜態風險」是由同步 UI 工作量或版面設定推得，沒有實測延遲或窄窗截切證據時不視為已發生的缺陷。

## 本輪已修正

- **共用收合分區的控制層級與互動狀態**：多工作區共用的 `CollapsibleSectionPanel` 原用膠囊標題與獨立按鈕外框並列，控制視覺權重接近內容標題。現在標題回到段落標題層級，展開／收合改為透明底行內文字與方向箭頭，保留動作名稱、方向、勾選狀態及呼叫端無障礙名稱；懸停／按下／鍵盤聚焦另有清楚但緊湊的狀態樣式。不改分區內容和觸發時機。元件＋比較證據、Workbench、選股及策略庫呼叫案例 **8 passed**。
- **Research Console 唯讀重讀控制與狀態**：全程式 1.5×畫面發現「重新載入唯讀 projection」獨佔整列，將動作和下一行載入狀態切開。現在狀態與自然寬度按鈕同列，長狀態文字可換行；無障礙名稱和 tooltip 明示只重讀、不更新或保存。完整 Research Console UI：**55 passed**；MainWindow Workbench 子頁改動後在兩種 DPI、三種尺寸均為 **39 子頁／scale、0 failures／0 coverage gaps**。
- **Workbench Advice 完整判讀可讀到底**：`advice_presentation_detail` 改為唯讀、換行的文字窗，保留 150–300 logical px 可視高度；內容超出時使用文字窗的垂直捲軸，避免長判讀被卡片高度裁掉。卡片展開狀態只更新前一張與目前這張卡；相同展開狀態直接返回，避免重複更新按鈕、樣式與版面。展開卡仍需重新排版以維持全寬列，沒有做延遲或效能宣稱。
- **個股研究保存 Advice 摘要窄窗裁切**：移除 `summary_saved_advice_label` 的 72 px 高度上限，文字依目前寬度自然換行增高；完整五問仍透過「展開五問證據與限制」查看。
- **每日研究條件結果清單分組**：將代號搜尋、狀態篩選、局部列數摘要、排序與原始排名控制收進表格前的「結果清單」區塊；「更新研究快照／重讀已發布快照」留在獨立快照操作列。每日快照最多 16 檔，因此原先對此頁重建表格成本的擔憂不能外推為實際卡頓，這次只修正資訊位置與閱讀關聯，沒有加入 debounce 或改動資料篩選語義。`tests/test_ux04_05_daily_market_research_view.py`：**4 passed**，含控制項分組斷言。
- **研究時間軸清單與查找操作分組**：把來源篩選、股票／result ID 搜尋及重新讀取收入「查找已保存研究紀錄」區；左右窗格分別標示「研究紀錄清單」與「所選紀錄與延伸操作」，讓歷史清單和選取後的原件／對照功能有明確標題。`tests/test_ui_qt_research_timeline_view.py`：**17 passed**。完整歷史搜尋已有 250 ms debounce；本次不調整搜尋資料或 500 筆呈現上限。
- **研究時間軸詳情面板密度**：所選原文是主要閱讀內容；目前資料對照、Paper 條件與後續旅程合併至「延伸核對與後續結果」，預設收合，避免延伸工具把原件閱讀切成多段。新增收合／展開與操作回歸，受控測試尚未重跑；原生 GUI／Owner UAT 尚未完成。
- **Update 狀態卡長來源文字**：額外資訊標籤啟用自然換行並允許縮小寬度，避免已匯入期別、可用期別、coverage 等長欄位被單行撐開。只改文字呈現；資料狀態語義不變。必要 Update UI 回歸：**98 passed**。
- **排程成熟分布小字**：圖例、成熟計數及未知訊息由 8 pt 提至 9 pt；色義及數值不變。`tests/test_ui_qt_evidence_review_dashboards.py`：**60 passed**。
- **題材成員長卡片清單**：預設成員卡片從單欄直向堆疊改為依可用寬度排 1／2／3 欄，每頁上限仍是 50 位；資料表切換、同快照分頁與選取操作保留。50 位窄／中／寬三種佈局斷言及完整題材頁 UI 回歸：**62 passed**；Main 成員導覽回歸另 **8 passed**。
- **持倉摘要卡窄窗壓縮**：四張核心狀態卡原本固定同列，視窗窄時仍被擠在一起。改為依頁面寬度排 4／2／1 欄，保留卡片與數值順序；定向版面回歸 **2 passed**。只調整排版，不改帳本、估值或數據。
- **推薦來源詳情資訊過載**：原本把核驗狀態、下一步、來源定位、完整欄位與雜湊放在同一段長文字。新增首屏來源摘要，先交代狀態、時間限制與下一步；核驗不足時使用警示色，完整來源欄位由緊湊文字操作展開，限制在可捲動區，所有原追溯欄位仍保留；理由展開也改為緊湊文字操作，減少整列按鈕對閱讀的切斷。推薦版面、保存讀回與來源追溯回歸共 **18 passed**。完整個人推薦測試檔曾有 11 個測試因 sandbox 目錄讀取／immutable receipt 硬連結權限與來源 fixture 失敗（23 passed），需在可讀寫測試目錄的環境重跑完整套件。
- **策略庫判讀與動作位置**：將策略內容／風險與資料／資格分組；「以此設定回測」移到右側固定面板底部，閱讀長說明時不必先捲到內容末端找入口。策略庫 UI 回歸 **12 passed**；只改資訊分組和動作位置，不啟動回測。
- **自選清單結果閱讀順序**：候選列數／不同代號數與更新狀態移到候選表前；個人查看狀態分布移到表後，讓搜尋後先看清單和載入狀態，再讀附加統計。只調整呈現順序，統計仍來自同一讀取快照。
- **綜合選股條件捷徑窄版擠壓**：MA、K／D、MACD 三個研究線索篩選按鈕由固定水平列改為 3／2／1 欄響應式分組，依可用寬度排列。來源選擇、收藏停用原因及篩選動作不變。新舊快捷列回歸 **2 passed**；完整 UI 檔 **25 passed**，另 1 項失敗、2 項 setup error 都因 sandbox tmp 目錄解析拒絕（WinError 5），非斷言失敗。
- 操作說明已同步至 [`APPLICATION_MANUAL.md`](../07_guides/APPLICATION_MANUAL.md) 與[個股研究手冊](../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md)。

## 其他優先檢視項目

| 優先度 | 頁面與證據 | 判讀 | 建議下一步 |
|---|---|---|---|
| P2 | 每日市場研究：搜尋直接觸發可見列重建；每份 cohort 最多 16 檔、表格 13 欄。搜尋、狀態篩選、排序與來源更新操作曾分散於結果摘要和表格附近。 | **控制與結果已重組**：表格前新增「結果清單」組，操作列獨立；回歸測試確認控制項同組、更新／重讀不混入該組，4 passed。基於 16 檔上限，靜態程式量不足以證明有可感知延遲，不以此項推定卡頓。 | 原生 GUI／Owner UAT 尚待人工確認窄窗和實際掃讀；回歸入口：`tests/test_ux04_05_daily_market_research_view.py`。 |
| P2 | Research Timeline：本地搜尋呼叫 `_render_entries`，每列最多重建 4 個儲存格；完整 Journal 搜尋另有 250 ms debounce，顯示最多 500 筆。 | **查找、清單與詳情已分區；延伸核對／Paper 條件／後續旅程改為預設收合，原件是選取後主要閱讀內容。定向回歸 18 passed。** | 原生 GUI 尚待確認不同寬度下 splitter 可讀性與展開後操作高度；如實測 500 筆鍵入有明顯停頓，再 profile 後決定是否調整模型。回歸入口：`tests/test_ui_qt_research_timeline_view.py`。 |
| P2 | Smart Money：[`smart_money_flow_view.py`](../../ui_qt/views/smart_money/smart_money_flow_view.py) 摘要卡與控制列原本都使用水平捲動區。 | **已修正版面風險**：摘要卡按寬度排 4／2／1 欄；掃描控制按寬度排單列／雙列／三列；掃描動作與觀察清單在首列，週期／範圍／圖表和搜尋／列數／品質各自成組，移除這兩處水平捲動容器。 | 保留既有市場摘要母體、搜尋範圍、掃描與表格契約；原生 GUI 視覺仍待人工確認。回歸入口：`tests/test_ui_qt_smart_money_flow_view.py`、`tests/test_ui_qt_market_layout.py`。 |
| P2 | Recommendation 結果表：結果載入先前呼叫 `resizeColumnsToContents()`；長理由會參與整欄寬度估算。 | **已修摘要表欄寬風險**：摘要欄採穩定初始寬度、理由欄初始 260 px，欄寬可拖曳；完整理由由詳情與儲存格提示閱讀，擴展欄位維持原資料。推薦版面／保存讀回測試 16 passed。推薦投資組合結果測試在 Qt WebEngine 建立回測圖表時觸發 Windows fatal exception，該測試未完成。 | 原生 GUI 視覺與 Owner UAT 尚待人工驗收；回歸入口：`tests/test_ui_qt_recommendation_layout.py`、`tests/test_ui_qt_saved_recommendation_compact_layout.py`、`tests/test_ui_qt_recommendation_portfolio_results.py`。 |
| P2 | Backtest 診斷：[`analyst_diagnostics_widget.py`](../../ui_qt/views/backtest/analyst_diagnostics_widget.py#L271) 同步重建月度矩陣；`_MAX_MONTHLY_DISPLAY_MONTHS=1200` 是補齊日期缺口的跨度門檻，不是 1,200 個表格列。13 欄矩陣按年作列；連續門檻範圍最多約 100 年列，超過跨度時只列有觀測年份（`L94–95,303–335`）。 | **先前把 1,200 個月誤記為 1,200 個表格列，已依程式修正判讀。**目前可確認是同步重建；尚無證據顯示一般資料量造成可感知延遲。診斷頁本身在既有可捲動結果頁內，沒有必要因這個靜態估算再增加分頁或操作。 | 保留觀察；若 Owner 實際遇到長跨度載入停頓，再以對應 DTO/profile 量測後決定是否優化。回歸入口：`tests/test_ui_qt_research_lab_mode_driven_ui.py`。 |
| P2 | Storage overview：原兩張表格無區塊標題，欄寬依內容且水平捲軸固定顯示。 | **已調整版面方向**：分為磁碟容量與明示根項目兩區；摘要明示位置／項目數；欄位採掃讀寬度，水平捲軸僅於溢出時顯示，完整文字可由儲存格提示讀取。2026-10-29 新暫存路徑重跑：4 個 UI／版面測試通過；worker 測試在 `Path.resolve(strict=True)` 得到 `WinError 5 Access is denied`。對同一路徑在同一 Python 程序直接探測也重現，因此確認是目前 sandbox 對 pytest 建立之子目錄的讀取限制，不能當作應用盤點邏輯失敗或通過。 | 版面測試通過；worker 回歸仍需在允許讀取該測試目錄的環境完成；原生 GUI 視覺仍待 Owner 驗收。回歸入口：`tests/test_ui_qt_storage_overview.py`。 |
| P2 | Research Console：`重新載入唯讀 projection` 曾單獨佔滿內容列，載入狀態在其後一列。 | **已重排**：唯讀載入狀態與自然寬度重讀控制同列，長狀態可換行，動作名稱仍明確。完整 UI suite 55 passed；Workbench 子頁兩種 DPI／三種尺寸幾何均無 failure／gap。 | 保留只讀重讀契約；真實資料量與原生 Windows 前景視窗視覺仍待 Owner 確認。回歸入口：`tests/test_ui_qt_research_console_view.py`、`scripts/qa_validate_ui_layout.py --workspace workbench`。 |
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

- `tests/test_ui_qt_storage_overview.py`：**4 passed、1 failed**。2026-10-29 另用全新 repo 內 pytest 暫存路徑重跑，worker 在 `Path.resolve(strict=True)` 得到 `WinError 5 Access is denied`；直接用同一 Python 執行器探測同一目錄也得到相同拒絕，將失敗定位為 sandbox 測試目錄讀取限制。應用正確回報盤點未完成，沒有把不可讀路徑當成空清單。worker 回歸仍需在允許讀取該測試目錄的環境完成。
- Offscreen Qt 版面與唯讀控制檢查通過；尚未做原生 GUI／Owner UAT。

## 2026-10-29 第六輪：個股研究導覽與操作分組

個股研究原本把三個頁面切換與三個股票動作放在同一個標題列，按鈕縮寫為「內容／判斷／追蹤／回測」，容易把導覽和操作看成同一類。現在標題列只保留工作區名稱、一般查詢切換及說明；其下把導覽命名為「研究內容／保存判斷／成果追蹤」，把目前股票操作命名為「加入自選／加入比較／準備回測」。兩組以「研究區段／這檔操作」標籤區分，操作色彩保持低權重，選中的導覽用淡藍底和字重標出。寬版兩組同列，窄版上下排列；來源切換按鈕與這檔操作歸在一起。保留既有 signal、啟用條件、選擇狀態及資料行為。

- 新增窄版重排及控制項幾何斷言。三個相關 UI 測試檔合跑，sandbox 可執行的 **37 passed**；另 4 個需真實隔離暫存目錄的案例因 Windows sandbox 在 `Path.resolve(strict=True)` 遭 `WinError 5` 未能執行，不列為通過。首屏高度回歸由 204 px 修至 200 px，專項測試 **1 passed**。
- 必要更新頁 Workbench **98 passed**；三個變更 UI source py_compile 通過、scoped mypy **3 files / 0 issues**。未重跑 Update QA validator；此前本工作階段既有記錄為 **25 passed／0 failed／4 skipped**，不把它當成本輪 fresh 結果。
- 只以 offscreen Qt 驗證幾何時，仍不能宣稱原生 GUI 色彩、字型、DPI 或 Owner UAT 完成。
- 使用者回報的 Advice／推薦來源可理解性、每日來源詳情入口和歷史研究可發現性仍需沿各自頁面做跨頁閱讀檢查；這一輪先處理個股頁的混合導覽列。

## 2026-10-29 第七輪：共用工作區子頁導覽響應式排列

`WorkspaceSubnav` 原固定使用單列水平按鈕；最多四個子頁在窄視窗寬度下沒有換行或捲動容器，固定寬度按鈕可能離開可視範圍。改為按導覽容器寬度將子頁排成寬版單列、中窄版雙欄、極窄版單欄；選取路由、按鈕名稱與 Tab 順序不變。以「探索與研究」四個實際子頁名稱覆蓋 1200／600／280 px，斷言欄數、順序、目前選取和按鈕右緣均在容器內。

- `tests/test_ui_qt_v2_shell_widgets.py`＋`tests/test_ui_qt_v2_product_shell.py`：**24 passed**；涵蓋 1200／600／280 px 欄數、按鈕容器邊界、route selection 保留及 ProductShell 整合。
- 本輪 source／test `py_compile` 與 `mypy ui_qt/widgets/workspace_subnav.py` 通過；必要 Update UI **98 passed**，Update validator **25 passed／0 failed／4 skipped**。Repo-wide mypy 仍被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻止。
- Offscreen 幾何測試不代替原生 GUI 的字型／DPI視覺與 Owner UAT；其餘主工作區仍沿全程式盤點排序繼續檢查。

## 2026-10-29 第八輪：Gate 1 跨頁回歸重查

依使用者針對 1569／2026-10-28 的實際畫面回報，重新檢查 Advice 判讀、推薦來源詳情、每日來源詳情入口及研究狀態讀回的跨頁連結。既有 Gate 1 調整已把 Advice 摘要拆成理由／限制、證據狀態、執行限制、策略版本說明與逐股證據；來源明細保留摘要與分層追溯欄位；同筆 Advice 可導向來源詳情及研究時間軸。這次只記錄驗證狀態，不更改來源資格或研究決定契約。

- `tests/test_workbench_advice_contract.py`、`tests/test_ui_qt_research_timeline_view.py`、`tests/test_cross_page_decision_journey_mainwindow.py`、`tests/test_ui_qt_workbench_view.py`：**96 passed**。
- 加入 `tests/test_daily_investment_journey.py` 的 Gate 1 組合回歸：**122 passed、5 errors**。5 項都在 `_scheduled_base_execution` fixture 建立排程推薦時發生；輸出顯示 fixture 的 `companies.csv` 不存在，且推薦 execution artifact 發布失敗。失敗發生於 UI 斷言之前，不能算成 UI 通過，也不能據此判定來源資格。
- 使用者先前提供的同筆保存與讀回文字確認人工決定=已納入研究；Journal 紀錄=0、下次檢視未設定是當時實際保存值的回讀，不是交易紀錄。原生 GUI 上的層級、文字可讀性與按鈕主次仍須 Owner UAT 確認。
- 下一步 Owner UAT 依序核對：資料日期與來源摘要、候選篩選／排除、Advice 限制、人工決定、保存後精確讀回、由 Advice 回查來源及由研究時間軸找回同一 `result_id`。完成前不標示 Gate 1 整體接受。

## 2026-10-29 第九輪：Research Console 與綜合選股版面修正

延續全程式 MainWindow 版面盤點，確認兩個可重現的閱讀問題並修正：Research Console 表格原先以內容自動量寬，長來源欄把表格與說明區撐出外層畫面；綜合選股的三個研究線索捷徑原本平均填滿欄位，視覺上比真正的查詢動作更突出。前者改用緊湊初始欄寬、保留拖曳調欄，並讓兩段長說明換行；後者改為內容寬度、靠左排列，依寬度換成 3／2／1 欄。只改版面，不改來源查詢、篩選、推薦或金融邏輯。

- 新增 Research Console 無水平溢出與可調欄寬回歸；該測試 **1 passed**。條件捷徑幾何測試 **1 passed**，確認按鈕緊湊及寬版靠左。WorkBench 真實 MainWindow 定向版面稽核在 scale 1.0、1.5 各檢查 13 子頁，兩者均 **0 failures／0 coverage gaps**。
- 相關 UI 測試組 **249 passed**；另 1 failure、2 errors 全發生在 pytest 暫存路徑 `Path.resolve(strict=True)`，為 Windows sandbox `WinError 5` 權限拒絕，沒有進入測試斷言。以允許的視覺化暫存根目錄重試仍是相同環境錯誤，不能列為通過或產品缺陷。
- 必要 Update UI 包含在上述測試組；`scripts/qa_validate_update_tab.py` 本輪重跑 **25 passed／0 failed／4 skipped**。修改檔 `py_compile` 與兩個 source scoped mypy 通過；repo-wide mypy 仍先遇到未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤，無法檢查其餘模組。`git diff --check` 無 whitespace error；Git 回報既有 fsmonitor IPC 訊息與行尾轉換警告。
- MainWindow 全工作區壓力稽核雖涵蓋 9 個工作區、三種幾何與兩種 scale，但每個 scale 有重複的子頁可見性、標籤／控制項裁切、合成資料還原和水平捲動警告；須逐項區分真缺陷、隱藏子頁與 fixture／量測限制，不把統計總數當成缺陷數。Recommendation 定向稽核仍有已保存推薦、每日快照條件等 widget 幾何警告，待確認是否只在非作用中頁籤出現，再修復確認的問題。
- 尚未完成全程式 UI 盤點與原生 GUI／Owner UAT；offscreen 幾何結果不代表實際字型、色彩、DPI或閱讀體驗驗收。全工作區後續以跨頁資訊層級、主要動作與長內容可讀性逐一確認，不宣稱 Gate 1 整體接受。

## 2026-10-29 第十輪：排程成熟狀態未知訊息分層

Backtest 的「證據覆盤 → 今日決策 → 排程狀態」在來源缺件時，成熟度小卡會直接放入含完整檔案路徑的診斷字串，實際量測高 30 px、文字需要 45 px。完整來源原因原本已在下方原始明細；現改為長診斷在卡片顯示短提示、滑過提示保留原文，原始明細仍保留全診斷與路徑。沒有改變狀態分類或排程資料。

- `tests/test_ui_qt_evidence_review_dashboards.py`：**60 passed**；回歸確認長檔案診斷在卡片摘要、tooltip 與下方明細間正確分層。
- Backtest 真實 MainWindow 定向稽核(scale 1.0／1.5)不再回報 `wrapped_label_vertical_clip`；仍因 `backtestDailySignalsPage` 合成資料 fixture restore 的 header tooltip 警告及 7 個 coverage gaps 而整體非綠，需另行釐清工具與頁面覆蓋，不歸因於此 UI 修正。
- 這次新增 Python 檔 `py_compile` 通過；必要 `tests/test_ui_qt_update_view_workbench.py` **98 passed**；`scripts/qa_validate_update_tab.py` **25 passed／0 failed／4 skipped**；scoped mypy（3 個 UI source）通過。Repo-wide mypy 仍在檢查前被未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻斷。全程式 UI 稽核與原生 GUI／Owner UAT 仍未完成。

## 2026-10-29 第十一輪：複合選股查詢操作主次

離線 MainWindow 畫面顯示複合來源頁把「套用條件並重新全域查詢」橫跨整個內容區，清除與取消各占半列，操作面積打斷條件與結果的連結。現在將三項操作集中在條件下方一列，明確以 primary／ghost／secondary 區分查詢、清除、取消；寬版同列靠左，窄版改直排。控制項仍呼叫原 signals／slots，查詢條件與資料不變。

- `tests/test_ui_qt_technical_official_composite_view_v2.py::test_v2_query_actions_have_primary_hierarchy_and_reflow_without_stretching`：**1 passed**；確認寬版主次樣式與內容寬度、窄版直排且按鈕都在操作區內。
- 新操作列定向測試 **1 passed**；完整 `tests/test_ui_qt_technical_official_composite_view_v2.py` 執行約 15 分鐘沒有輸出，已中止 owned session，不能列為通過。必要 Update UI **98 passed**；`scripts/qa_validate_update_tab.py` **25 passed／0 failed／4 skipped**。修改 UI source scoped mypy **4 files / 0 issues**、Python `py_compile` 通過；repo-wide mypy 仍被未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤擋住。全程式 UI 盤點與原生 GUI／Owner UAT 仍未完成。

## 2026-10-29 第十二輪：技術母體結果操作分組

綜合選股的每日技術母體結果表上方，原本五個同權按鈕平均展開，將「開啟所選股票」和「比較清單」的動作混成一排。現在以「所選個股」和「比較籃」兩個區塊建立操作上下文；查個股證據和比較原研究作為主要動作，新增／收藏列次要、清空比較籃為低權重；寬版左右並列，窄版上下排列。沒有改查詢或保存行為。

- `tests/test_ui_qt_daily_market_technical_universe_v4_view.py::test_v4_result_actions_are_grouped_and_reflow_at_narrow_width`：**1 passed**；驗證兩種寬度下的分組、層級、內容寬度與容器邊界。
- 新操作列定向測試 **1 passed**；完整 V4 測試檔未在本輪執行。必要 Update UI **98 passed**、`scripts/qa_validate_update_tab.py` **25 passed／0 failed／4 skipped**。修改的 5 個 UI source scoped mypy **0 issues**，Python `py_compile` 通過；repo-wide mypy 仍被未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻斷。全程式 UI 盤點與原生 GUI／Owner UAT 仍未完成。

## 2026-10-29 第十三輪：Recommendation 捲動高度與控件裁切

Recommendation 結果頁原先把內層 layout 的水平與垂直 size constraint 一起設為 `SetNoConstraint`。MainWindow 窄版中，外層捲動區因此沒有取得內容所需的自然高度：保存來源選單被壓到 1 px，人工決定區高度不足。現在保留「水平不鎖寬」並恢復「垂直依內容延伸」，讓外層捲動承接長頁；查詢與保存行為不變。

- `tests/test_ui_qt_recommendation_layout.py::test_saved_recommendation_primary_controls_keep_their_readable_height`：**1 passed**；檢查寬／窄視窗保存來源、主要操作、研究決定與日期時間控件高度，並斷言水平／垂直 layout constraints。
- 稽核器誤報也一併修正：把 `QTimeEdit` 內部 `QLineEdit` 改按複合控件量測。`tests/test_qa_validate_ui_layout.py::test_spinbox_editor_is_audited_through_its_composite_control`：**1 passed**。
- 修正後 Recommendation 定向 MainWindow 稽核（scale 1.0、1400×800、46 子頁）：**0 failures／0 coverage gaps**；保存來源選單為 30×30 px，研究決定組高度問題不再出現。原九工作區多尺寸稽核未重跑；原生 GUI／Owner UAT 與全程式 UI 盤點仍未完成。

## 2026-10-29 第十四輪：全工作區現況基線

以目前版本重新跑 MainWindow 全九工作區、default 1400×800、scale 1.0：涵蓋 **325 子頁**。Recommendation 與 Workbench 各自的定向結果沒有再現前版 Recommendation 控件壓縮或 Workbench「研究證據」水平溢位；Workbench 研究證據內容寬度與 viewport 同為 1306 px、水平範圍 0。舊報告的這兩類告警不代表目前程式狀態。

- 全九工作區報告仍有 **8 failures／7 coverage gaps**：4 個 Backtest daily-signals 合成 fixture 在 header tooltip 還原核對失敗；3 個 Portfolio「配置研究封存」合成列的第 5 列未完整顯示；另有 7 個 Backtest replay／strategy-research 子頁在切換後仍未可見。這些項目目前不足以證明是使用者可見產品缺陷，仍作為盤點缺口，不宣稱全程式稽核通過。
- QA 原始輸出位於 ignored `.pytest-owned-temp/ui_audit_all_default_round14/`。本輪只做 default 尺寸、1.0 scale；未覆蓋 compact／最大化幾何、1.5 scale、原生 GUI 或 Owner UAT。

## 2026-10-29 第十五輪：Advice 空狀態診斷操作層級

Workbench 的「查看技術診斷」原占滿 Advice 空狀態卡寬度，讓次要技術動作看起來像主操作並切開狀態說明。現在改成卡片內靠左、依文字寬度排列的 ghost 操作；展開／收合與診斷內容不變。

- `tests/test_ui_qt_workbench_view.py` Advice 狀態與新幾何定向測試：**2 passed**；寬／窄尺寸均確認操作按鈕保持緊湊且靠左，原診斷展開／收合行為保留。
- 修正後 Workbench 定向 MainWindow 稽核（scale 1.0、1400×800、13 子頁）：**0 failures／0 coverage gaps**；首頁 Advice 空狀態診斷操作已恢復為內容寬度。
- 必要 Update UI **98 passed**；Update validator **25 passed／0 failed／4 skipped**；兩個修改 source targeted mypy **0 issues**，4 個 Python source／test `py_compile` 通過，`git diff --check` 無空白錯誤。
- Repo-wide mypy 仍在 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇未修改語法錯誤，未檢查其餘模組。Advice 原生 GUI／Owner UAT、全程式多尺寸盤點仍未完成。

## 2026-10-29 第十六輪：來源閱讀與查詢動作路徑

依使用者回報重新整理 Gate 1 的跨頁導覽與來源閱讀：Advice 的每日來源入口明示目的地為今日總覽；同筆研究狀態以明確的緊湊按鈕前往「研究紀錄與覆盤」，讀回文字也標出回查位置。每日來源詳情改為先呈現候選、日期、篩選／排除及證據狀態；來源 ID、snapshot、事件、學習與診斷欄位放入收合的「進階追蹤」。綜合選股的「套用全域查詢」不再橫跨整列，改為靠左的主要動作並加上條件變更提示。所有變更只調整操作呈現與文字，沒有改資料來源、篩選或保存行為。

- `tests/test_ui_qt_workbench_view.py`＋`tests/test_workbench_advice_contract.py`：**75 passed**；涵蓋 Advice 的來源導覽、歷史查找按鈕與保存位置文字、每日來源摘要及進階追蹤分層。
- `tests/test_ui_qt_daily_market_technical_universe_v4_view.py::test_v4_result_actions_are_grouped_and_reflow_at_narrow_width`：**1 passed**；更新頁 UI **98 passed**；Update validator **25 passed／0 failed／4 skipped**。
- Workbench 定向 MainWindow 稽核，scale 1.0／1.5：**13 子頁、0 failures／0 coverage gaps**。Recommendation 定向稽核，scale 1.0／1.5：**46 子頁、0 failures／0 coverage gaps**。推薦頁稽核畫面確認主要查詢按鈕改為緊湊靠左；offscreen 測試不取代原生 GUI 視覺或 Owner UAT。
- 兩個修改 UI source 的 scoped mypy 均 **0 issues**；修改 Python source／test `py_compile` 通過。全程式 9 工作區多幾何稽核目前仍有每個 scale **70 failures／21 coverage gaps**，集中於 Workbench 擴展情境的水平溢位、Recommendation 非作用中狀態的控件量測、Backtest 夾具還原／文字裁切與子頁覆蓋、Portfolio 合成列邊界，以及 3 個 child process 退出錯誤。Recommendation 與 Workbench 各自定向重跑為綠；整體告警尚未逐項重驗，不能據此宣稱全程式 UI 通過。
- `git diff --check` 無 whitespace error。尚未完成全部工作區的逐頁資訊層級盤點、原生 GUI 視覺檢查或 Owner UAT；Gate 1 整體接受仍待 Owner 核對。

## 2026-10-29 第十七輪：保存來源詳情的可掃讀分段

使用者提供的推薦來源內容同時含分類資格、公司名冊契約、產業指數觀察、來源警示及下一步；原本顯示為連續段落。現在在完整來源欄位中加上可掃讀的段落標題與留白，並用同一來源卡片樣式及純文字格式顯示，分段為公司名冊／分類資格、產業指數來源與列觀察、同次市場來源、來源提示和下一步。摘要仍先顯示核驗狀態及下一步；原始欄位、hash、日期、未知值與 PIT 限制均保留。

- `tests/test_ui_qt_personal_recommendation_choice.py::test_company_source_display_uses_only_the_matching_sealed_event`：**1 passed**；原來源資格、封存資料與 unknown 顯示斷言保留，新增分段標題和純文字檢查。
- Recommendation 定向 MainWindow 稽核於 scale 1.0／1.5：**46 子頁、0 failures／0 coverage gaps**。這是 offscreen 版面稽核，沒有驗證 Windows 原生視窗字型／DPI。
- 完整 `tests/test_ui_qt_personal_recommendation_choice.py`：**23 passed、11 failed**，不能列為整檔通過。失敗包含 runs 目錄不可讀或 fixture 未產生 replay samples、個人策略歷史讀回與預期不同、以及 `os.link` 暫存 receipt 權限拒絕；這些測試涉及來源／策略保存行為，未判成此次呈現變更的缺陷或通過。須獨立查清後才能將該測試檔列為綠燈。
- `recommendation_view.py` scoped mypy **0 issues**；修改 Python source／test `py_compile` 通過；全程式多工作區稽核的既有 70 failures／21 coverage gaps 每 scale 仍待分類與重驗。原生 GUI／Owner UAT、全程式 UI 盤點未完成。

## 2026-10-29 第十八輪：Advice 判讀摘要與完整依據收合

Gate 1 Advice 原本把主要理由、成熟度、信心、流動性、可成交性、選填作者說明及來源列全塞在同一張文字卡；完整判讀窗也一開始就占住垂直版面。現在卡片先呈現動作、最多兩項易讀理由、證據成熟度、決策信心和執行限制；未知／不足狀態使用警示色邊線提示，不代表交易許可。完整來源、策略作者選填說明、原始理由與共用證據內容改由「展開完整判讀與原始理由」載入；「展開校準機率來源」也會同步打開完整詳情。資料與政策契約未更動。

- `tests/test_ui_qt_workbench_view.py`＋`tests/test_workbench_advice_contract.py`：**75 passed**；涵蓋 Advice 摘要、完整資料仍可展開、原始理由保留、校準依據展開、來源與研究紀錄路徑。
- `tests/test_qa_validate_ui_layout.py`：總合執行 **121 passed、2 failed**；2 個失敗在 Windows 沙箱 temp 中 `os.replace` 寫入 JSON 被 `PermissionError` 拒絕，無法列為整檔通過。空白標題還原定向案例 **2 passed**。
- Portfolio 的持倉／目標／情境三張表加入五列可視高度。MainWindow Portfolio 定向稽核 scale 1.0／1.5、預設幾何：**0 failures／0 coverage gaps**。
- 全程式稽核修正為使用 Backtest 真正的「結果頁面」扁平選單逐路由走訪；Backtest 定向核對 **110 頁、0 failures／0 coverage gaps**。舊 21 個 `subpage_not_visible` 是稽核器沒有走產品路由造成的假缺口。修正後九工作區完整稽核：每個 scale 都跑 default／compact／actual_max 三種幾何，計 **27 workspace-visits、744 page-visits**；兩個 scale 合計 54／1,488，summary `passed/complete`、0 errors／0 coverage gaps。輸出位於 ignored `.pytest-owned-temp/ui_audit_full_round20_20261029/`；這是 offscreen 幾何與路由覆蓋，不等於原生 GUI／Owner UAT。
- 舊截圖中的 58 px icon-only sidebar 已由 MainWindow resize breakpoint 調整至 1260 px 以下收合、1340 px 以上恢復文字導航。改後用真實 MainWindow 重跑 1400×800、scale 1.0 的 Workbench／Portfolio targeted audit：`summary.status=passed`、0 errors／0 coverage gaps；側欄寬度讀回 **184 px**，不再 icon-only。Workbench Overview 約 2211 px 長的長頁閱讀仍留待資訊架構調整；Recommendation 與 Workbench 完整畫面仍需按使用者實際流程逐頁視覺覆核。
- `tests/test_portfolio_research_scenario_widget.py`＋`tests/test_portfolio_research_registry_open_widget.py`：**6 passed**。Portfolio widget `py_compile` 通過，scoped mypy **0 issues**；`scripts/qa_validate_ui_layout.py` `py_compile` 通過，但整檔 mypy 有 **87 個 typing diagnostics**，故不宣稱 validator mypy 通過。`git diff --check` 通過。Owner 原生 GUI UAT 尚未完成。

## 2026-10-29 第十九輪：桌面寬度保留導覽名稱

真實 MainWindow 1400×800 的畫面截圖顯示左側導覽仍是 58 px 純圖示 rail；在常見桌面寬度使用者需要猜圖示或先發現收合箭頭，與跨頁來源入口難找的回報一致。現在只有寬度 1260 px 以下才自動收合，系統自動收合後在 1340 px 以上展開；使用者手動收合仍保留自己的選擇。主頁寬度減少 126 px 後，Workbench 和 Recommendation 仍可讀，沒有幾何失敗。

- 修改後 Workbench＋Recommendation MainWindow 定向稽核，1400×800／scale 1.0：**59 子頁、0 failures／0 coverage gaps**；shell 左側導覽 184 px，工作區及導覽均在中央區域內。
- 新舊截圖對照確認四個主要工作區文字與系統管理標籤可見。Workbench Overview 仍約 2211 px 長；即使沒有幾何錯誤，首頁資訊密度和長距離閱讀仍是下一輪重整目標。

### 前一批 presentation 變更的 focused QA readback

針對本輪改動的 Workbench、Recommendation 來源詳情、Daily Market 查詢操作與 layout fixture，使用專案 `.venv` 在隔離 basetemp 執行 focused 測試：**79 passed**；修改 Python source／test `py_compile` 通過；3 個產品 UI source scoped mypy **0 issues**，`git diff --check` 通過。修改之 layout QA script 在單檔 mypy 下回報既有檔案內 86 個 typing diagnostics（包含多處 QWidget／QApplication 名稱與 optional 型別），不將該 validator 腳本記為 mypy 通過。

另執行五個受影響測試檔的廣泛回歸：**149 passed、14 failed、5 errors**。5 個 setup errors 及多個寫檔失敗指向 Windows sandbox 的系統 Temp 解析／原子替換／hardlink 權限；另有候選 inventory 測試在 sandbox 指定的 learning root 回報 unsafe-or-unreadable，未能驗證其預期樣本。此結果不是整檔通過；相關完整保存／來源行為尚需在可讀寫的受控 Windows Job 環境重跑。更新頁既有 98／25 測試收據另見第十六輪，不代表本次 5 檔廣泛回歸全綠。全九工作區稽核、原生 GUI 與 Owner UAT 仍未完成。

## 2026-10-29 第二十輪：Gate 1 首頁閱讀順序與全工作區截圖盤點

使用者回報 Advice、來源詳情與研究狀態散落在多個區塊。重排 Workbench 首頁為每日結論／資料日／候選摘要 → 警示與待處理摘要 → Advice → 一般研究捷徑 → 行動與持倉管理。這使資料脈絡先於建議，Advice 的同源捷徑也更明確標示「查看本次來源與篩選排除」；每日詳情入口改為「展開本次來源、篩選與排除」。保存、來源驗證及策略計算均未更動。

- Workbench 首頁與 Advice 定向測試：**22 passed**；含首頁 widget 順序、每日來源按鈕名稱、Advice 詳情契約與行動卡三種寬度重排。
- 真實 MainWindow Workbench 稽核，1400×800／scale 1.0：**13 子頁、0 failures／0 coverage gaps**；今日行動中心四張卡在桌面寬度排成一列、中等寬度兩欄、窄版一欄；預設桌面內容高度由 2211 px 降到 2077 px（減少 134 px）。重排改善閱讀順序並縮短次要操作區，但首頁仍約為視窗高度的 3 倍，長頁問題未解決。
- 檢視九個工作區既有 1400×800 offscreen 截圖：常見待整理項目包括空資料表佔據大片空白、同一頁多組主次不明的動作入口、資料來源與操作步驟混排。這是視覺初步盤點，不代表九個工作區已完成重新設計；後續優先逐頁整理 Recommendation 的空結果狀態與操作分組，再處理 Portfolio 空表與 Backtest 的設定／結果分區。
- `scripts/qa_validate_ui_layout.py` 在系統 Python 初次啟動缺少 pandas；改用專案 `.venv` 重跑成功。新報告位於 ignored `.pytest-owned-temp/ui_audit_workbench_round25_20261029/`。offscreen 幾何與截圖不能代替原生 GUI 或 Owner UAT。`git diff --check` 通過。

## 2026-10-29 第二十一輪：Recommendation 結果表空狀態

Recommendation 結果表原本在零列時只留下空白表面，上方狀態文字雖有原因，使用者仍難看出下方空區域的用途。現在空表格中央會顯示「目前沒有可顯示的列」及下一步提示，文字疊在既有表格內、不額外占用版面；有推薦列或同次篩選紀錄時提示隨列數自動消失。明確保留「未執行、有效空結果、歷史保存結果無推薦列」由上方摘要區分，不新增或推定結果狀態。

- `tests/test_ui_qt_recommendation_layout.py`＋`tests/test_ui_qt_recommendation_exact_saved_entry.py`：使用預設系統 Temp 首跑為 **28 passed、1 failed**，失敗發生在空結果 fixture 的 artifact `os.rename`；改以 repo ignored `.pytest-owned-temp/pytest_rec_ui_basetemp_round21/` 為 basetemp 後重跑 **29 passed**。空表提示模型切換定向測試亦在完整套件中。
- Recommendation MainWindow offscreen 稽核：**46 子頁、0 failures／0 coverage gaps**，scale 1.0／1400×800；報告 `.pytest-owned-temp/ui_audit_recommendation_round21_20261029/`。另外檢視空表 viewport 截圖 `.pytest-owned-temp/recommendation_empty_state_viewport.png`，可讀提示顯示於原表格中間，無額外版面高度。
- 此次只改結果表空狀態呈現，未改推薦計算、保存或來源契約。完整互動視覺與 Owner UAT 仍待原生 GUI 核對；全工作區操作分組、空狀態和頁高調整仍在盤點中。

## 2026-10-29 第二十二輪：Portfolio 首次讀取時收起空持倉表

Portfolio offscreen 首頁在背景持倉讀取完成前先顯示了可伸展、但尚無列的空表，形成大片無用途的空白；畫面其他狀態已表示資料尚未載入。現在持倉表在建立時先收起，待 `_load_positions_table` 取得有持倉 DTO 後才顯示；零筆或讀取失敗時維持收起，避免空白表切斷首屏內容。資料、帳本與 Advice 邏輯未變。

- `tests/test_ui_qt_portfolio_view.py`：**110 passed、1 failed**。失敗是既有 `test_stress_splitter_default_keeps_vertical_ratio_and_position_selection` 比例讀值 0.303 未達 0.35；單獨重跑仍相同。該測試建構同步讀取並在顯示前已完成持倉表載入，與「首次背景讀取時隱藏」變更無關；不列整檔通過。
- Portfolio MainWindow offscreen 稽核，1400×800／scale 1.0：`summary.status=passed`，13 頁、0 errors／0 coverage gaps；截圖確認首次資料尚未抵達時空表不再佔據版面。報告在 ignored `.pytest-owned-temp/ui_audit_portfolio_round22_20261029/`。
- 修改 Python source／test `py_compile`：通過；`tests/test_ui_qt_update_view_workbench.py`：**98 passed**。Update validator：**25 passed／0 failed／4 skipped**；首次預設輸出目錄因 `PermissionError` 不可寫，改用 ignored `.pytest-owned-temp/update_tab_round22/` 後通過，且實際下載／合併案例仍按腳本設計略過。
- 修補後 Portfolio MainWindow offscreen 稽核，1400×800／scale 1.0：**13 頁、0 errors／0 coverage gaps**；重看首頁截圖，首次讀取期間原 190 px 空表已收起。完整 `tests/test_ui_qt_portfolio_view.py` 為 **110 passed、1 failed**；單獨重跑失敗的既有 stress splitter 比例斷言仍讀得 0.303，門檻 0.35，該測試同步載入 DTO 後才開窗，與首次背景讀取收表無關。
- Portfolio view scoped mypy：**1 source、0 issues**。指定全程式 mypy 未完成：在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因語法錯誤停止。原生 GUI 與 Owner UAT 未執行。此次是 Portfolio 首次載入空白的局部修正，不代表整體 UI 盤點完成。

## 2026-10-29 第二十三輪：窄版 Portfolio 分頁高度隔離

窄版切到「情境壓力」時，QTabWidget 會把未選取的「配置研究封存」內容最小高度（1,212 px）套到整個 splitter；在 390×844 的視窗下，情境頁自身需要 489 px，但 splitter 被撐至 1,768 px，上方健康區比例落到 30%。現在配置研究封存放入可獨立捲動的分頁容器，讓長內容維持可達，但不再支配其他分頁的最小高度；資料與配置研究計算未變。

- `tests/test_ui_qt_portfolio_view.py`：**111 passed**；新增／修正後的窄版 stress splitter 比例及配置研究內部捲動案例通過，持倉選取仍保留。
- Portfolio compact MainWindow offscreen 稽核，scale 1.0：**13 頁、0 failures／0 coverage gaps**；390×844 情境壓力 split ratio 由 **0.303** 回到 **0.430**，配置研究內容 1,236 px 高時在分頁捲動區可捲動 649 px。報告位於 ignored `.pytest-owned-temp/ui_audit_portfolio_compact_round23_20261029/`。
- `tests/test_ui_qt_update_view_workbench.py`：**98 passed**；Update validator：**25 passed／0 failed／4 skipped**。修改 Python source／test `py_compile` 通過，Portfolio view scoped mypy **1 source、0 issues**。
- 指定全程式 mypy 仍被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻斷。原生 GUI／Owner UAT 尚未執行；全程式其餘工作區仍需依盤點排序逐步檢視。

## 2026-10-29 第二十四輪：Backtest Registry 窄版篩選與比較操作

Backtest Registry 原先把類型、策略、標籤、刷新狀態、分頁及三個比較動作塞在同一排；在 1400×800 下右側結果區的 Registry viewport 寬 627 px、內容寬 662 px，水平捲動被關閉，造成篩選與按鈕被裁切。現在篩選分為兩列，翻頁與比較動作分列；狀態欄改用可換行剩餘空間。相鄰的 Registry 目的說明原本重複，現只留下升級限制，完整比較範圍及不可補算邊界留在 Registry 自身說明。未改回測、Registry、比較或升級邏輯。

- `tests/test_ui_qt_backtest_product_layout.py`、Registry 分頁用途與窄欄回歸：**13 passed**。`tests/test_ui_qt_run_registry_compare.py` 完整檔案：**26 passed、1 failed**；失敗是基本策略對照測試的 `_basic_pair_worker` 超出測試自身 10 秒等待，單獨重跑仍未收尾；該檔不列全通過。
- Backtest MainWindow default／compact 首輪合併稽核：**110 頁、0 page errors／0 coverage gaps**；後續 banner 文案更新後，合併 runner 的 compact child 以 3221225477 非正常退出，default 頁面本身 0 error。compact 獨立重跑為 **110 頁、0 failures／0 coverage gaps**。最後截圖確認 Registry 篩選和比較動作不再裁切，內容水平 range 0；報告 `.pytest-owned-temp/ui_audit_backtest_compact_round24_retry/`。
- 共用 `tests/test_ui_qt_update_view_workbench.py`：**98 passed**；Update validator：**25 passed／0 failed／4 skipped**。三個修改 Python source／test `py_compile` 通過；兩個產品 UI source scoped mypy **0 issues**；`git diff --check` 無空白錯誤。指定全程式 mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇到語法錯誤而停止。原生 GUI／Owner UAT 尚未執行；全程式 UI 盤點仍在進行。

## 2026-10-29 第二十五輪：Registry 初始閱讀高度與選用區

Registry 初次開啟時，逐日訊號、兩個基本策略的對照明細，以及尚未比較前的績效說明都同時佔用垂直閱讀空間，主清單與下一步容易被分隔。現在逐日訊號及基本策略結果／來源改為清楚命名的預設收合區；基本策略操作後會自動展開其結果區。績效摘要與標準化權益只在按下比較後顯示，選擇 run 與讀取保存資料的行為不變。

- `tests/test_ui_qt_run_registry_compare.py` 排除基本策略 worker 逾時案例後：**26 passed、1 deselected**；新增畫面狀態斷言確認結果初始收起、比較後顯示、選用區可展開。該 worker 逾時案例本輪重跑仍超過測試自己的 10 秒等待，不能列為通過。
- Backtest MainWindow default 尺寸 offscreen 稽核：**110 子頁、0 failures／0 coverage gaps**；輸出位於 ignored `.pytest-owned-temp/ui_audit_backtest_registry_layout_round25/`。本輪只完成 default 尺寸，compact 幾何因 QA runner 的 process lock 權限錯誤未完成。
- 使用者手冊已補充收合區位置、展開方式與比較結果出現時機。原生 GUI／Owner UAT 尚未執行；其餘 Registry 比較資料契約未改。

## 2026-10-29 第二十六輪：Workbench 行動中心去重與入口分組

Workbench 的每日行動中心在 Dashboard 尚未載入時，四張卡都顯示同一個「重新整理狀態」，標題列另有重新整理及主要按鈕；卡片內的目的地操作又被做成整列寬按鈕，擠壓狀態文字。現在刷新只保留標題列的單一入口，卡片改顯示各自狀態與右側目的地：資料更新、市場總覽、推薦分析、持倉管理；載入完成後頂部主要動作回到建議下一步。沒有改 DTO、工作台刷新或策略邏輯。

- Workbench 今日行動中心與首頁可視頁定向測試：**4 passed**；檢查載入前只有單一刷新入口、四個路由各自明確、卡片按鈕受限為 148 px 並保留 28 px 可點高度，以及桌面至窄版網格重排。
- Workbench MainWindow default 尺寸 offscreen 稽核：**13 子頁、0 failures／0 coverage gaps**；檢視首頁滾動末端截圖，卡片內容／目的地按鈕左右分區，重複刷新按鈕已移除。整張今日總覽仍是長頁，本輪沒有宣稱已解決全頁捲動量。報告 `.pytest-owned-temp/ui_audit_workbench_actions_round26/`。
- `tests/test_ui_qt_workbench_home_single_page.py`、`tests/test_ui_qt_workbench_view.py`、`tests/test_workbench_advice_contract.py`：**82 passed**；必要 `tests/test_ui_qt_update_view_workbench.py`：**98 passed**。Update validator：**25 passed／0 failed／4 skipped**。修改 source／test `py_compile` 通過，Workbench view scoped mypy **0 issues**，`git diff --check` 通過。指定全程式 mypy 仍在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因語法錯誤停止。
- Owner 原生 GUI／UAT 與 Workbench 長頁下一階段盤點仍待完成。

## 2026-10-29 第二十七輪：Workbench 首頁主旅程與延伸區分層

Workbench 原本把「今日優先查看」、額外工作區捷徑、今日行動中心與 Paper 持倉健康一併放在每日來源及 Advice 後方，使用者必須沿同一長頁經過所有區塊。現在每日日期／來源脈絡、警示摘要、狀態計數與 Advice 保留在主閱讀流；「其他工作區捷徑、最近研究與持倉追蹤」收合為單一延伸區，包含原有捷徑、行動狀態、持倉健康；優先事項動作會先展開該區再定位原件。資料和回呼不變。

- Workbench 首頁、Advice 與 guided navigation 回歸：`tests/test_ui_qt_workbench_home_single_page.py`、`tests/test_ui_qt_workbench_view.py`、`tests/test_ui_qt_v5_workbench_guided.py`、`tests/test_workbench_advice_contract.py`：**87 passed**。候選原始理由只在其逐股詳情可用時顯示的測試斷言已對齊現行摘要契約：彙總顯示候選數，逐股代碼與來源說明由候選預覽檢視。
- `tests/test_baldr_b03_market_home.py` 獨立重跑：**10 passed、3 failed**。3 個失敗都在未修改的 `MarketRegimeView` 層級條件／折疊狀態斷言，不涉及 Workbench 延伸區；該檔不列全通過。
- Workbench MainWindow default offscreen 稽核：**13 子頁、0 failures／0 coverage gaps**；首頁與滾動末端截圖核對延伸區收合，Advice 與同源入口留在主要旅程。報告 `.pytest-owned-temp/ui_audit_workbench_section_round27/`。此項降低主畫面區塊數；未宣稱全頁閱讀已完成或原生 GUI／Owner UAT 通過。
- 必要 `tests/test_ui_qt_update_view_workbench.py`：**98 passed**；Update validator：**25 passed／0 failed／4 skipped**。本輪 5 個修改 Python source/test `py_compile` 通過；Workbench view scoped mypy **0 issues**，`git diff --check` 無 whitespace error。指定全程式 mypy 仍在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因語法錯誤停止，無法檢查其餘模組。

## 2026-10-29 第二十八輪：Workbench 等待狀態摘要去重

窄版首頁在今日工作台資料尚未載入時，上方每日旅程已顯示五項狀態為等待／未知；下方四張摘要卡又重複顯示同一組等待資訊，延後 Advice 出現。現在尚無可信資料（初次等待或沒有最後可信資料的讀取失敗）時收起重複摘要列；取得工作台資料後顯示摘要，更新失敗時保留最後可信摘要並標記為過期。Advice 與資料狀態的呈現未改，沒有變更資料或策略邏輯。

等待 Advice 時原先另外顯示摘要、警告與兩個目的地大按鈕，和等待卡內容重複。現在等待狀態收起這些重複列與導覽按鈕，只留一張含下一步說明的狀態卡及可選的技術診斷；每日結論使用「等待工作台資料載入」等一般語彙，不顯示 DTO 類別名稱。其他無建議、拒絕與讀取失敗狀態保留各自解釋與診斷入口。

- `tests/test_ui_qt_workbench_home_single_page.py`、`tests/test_ui_qt_workbench_view.py`、`tests/test_ui_qt_v5_workbench_guided.py`、`tests/test_workbench_advice_contract.py`：**88 passed**；必要 `tests/test_ui_qt_update_view_workbench.py`：**98 passed**；Update validator：**25 passed／0 failed／4 skipped**。
- Workbench compact／scale 1.5 MainWindow offscreen 稽核：**13 子頁、0 failures／0 coverage gaps**；首頁截圖確認重複摘要列與等待 Advice 的冗餘說明收起，首屏等待文案不再顯示 DTO 類別名。報告 `.pytest-owned-temp/ui_audit_workbench_compact_waiting_round28/`。
- 修改 Python source／test `py_compile` 通過；Workbench view scoped mypy **1 source、0 issues**；依硬規則的完整模組 mypy 在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇語法錯誤，未能檢查其餘模組。`git diff --check` 通過，只有既有 fsmonitor IPC 與行尾轉換警告。
- 原生 GUI／Owner UAT 未執行；這輪只處理初次等待時重複摘要，Workbench 全頁資訊架構與其他工作區盤點仍未完成。

## 2026-10-29 第二十九輪：首頁延伸區與多工作區版面複驗

將 Workbench 延伸捷徑／最近研究／持倉追蹤收進單一預設收合區；每日旅程、狀態摘要及 Advice 保留主閱讀流。今日行動卡在寬螢幕四欄、中版雙欄、窄版單欄排列；載入前只保留標題列重新整理，四張卡分別導向資料更新、市場總覽、推薦分析及持倉管理。Portfolio、Recommendation、Backtest Registry 保留前幾輪的空態收合、窄版操作排列與來源限制說明。同步更新首頁導覽、Recommendation 來源按鈕及 Registry 窄版操作手冊。

- `tests/test_ui_qt_workbench_home_single_page.py`：**7 passed**；`tests/test_workbench_advice_contract.py`：**16 passed**；`tests/test_ui_qt_v5_workbench_guided.py`：**4 passed**；首頁四欄／雙欄／單欄、收合區及導覽回歸通過。
- 補充單檔核對 `tests/test_ui_qt_workbench_view.py`：**60 passed**；受控 Windows Job 限制讀回 8 GiB／12 processes，程序樹及 child handles 正常關閉。
- `tests/test_ui_qt_portfolio_view.py`：**111 passed**；`tests/test_ui_qt_recommendation_layout.py`：**16 passed**；`tests/test_ui_qt_run_registry_compare.py`：**26 passed、1 deselected**。唯一排除項為先前已記錄會逾時的基本配對 worker 測試，本輪其餘 Registry 比較、收合與窄欄版面測試通過。
- `tests/test_baldr_b03_market_home.py`：**13 passed**。修正兩個舊斷言：來源缺值摘要實際有三項；檢測失敗會清空技術細節並收合區塊，測試改核對既有失敗契約。
- 必要 `tests/test_ui_qt_update_view_workbench.py`：**98 passed**；`scripts/qa_validate_update_tab.py`：**25 passed／0 failed／4 skipped**。本批 13 個修改 Python source／test `py_compile` 通過；5 個修改 UI source targeted mypy **0 issues**。
- 合併上述 UI 檔案的一次 pytest 執行在 **300 秒** runner 上限逾時（進度輸出 36%，未完成摘要）；後續依檔案分別執行並取得上述結果。repo-wide mypy 仍在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 報語法錯誤，未能檢查其餘模組。受控結果及 Job readback 保存在 ignored `.tmp_ui_finish_20261029/`。
- `document_control check` 的 MOPS QA 子集合已通過；Snapshot 廣域 check 仍受既存 output Junction `WinError 5` 與舊 anchor 問題影響，不記為通過。原生 GUI／Owner UAT 未執行；本輪只完成目前 source／offscreen 測試範圍。

## 2026-10-29 第三十輪：九工作區跨尺寸基線盤點

使用真實 MainWindow 與正式 theme，對 Workbench、Market Explore、Recommendation、Backtest、Watchlist、Stock Research、Portfolio、Update、Runtime 九個工作區跑 default／compact 幾何與 1.0／1.5 scale；每組幾何均檢查頁面、捲動容器、表格與清單可達性，合計 496 子頁。這是幾何及元件覆蓋基線，不是 Owner UAT、資料正確性或資訊易讀性的簽收。

- Default／compact × scale 1.0／1.5：**496 子頁、0 幾何失敗、0 coverage gaps**。輸出與截圖 `.pytest-owned-temp/ui_audit_all_workspaces_default_compact_round30/`。
- 縮放截圖的人工閱讀檢視仍發現 Recommendation 主研究區把規則條件、來源檢查、全域查詢、保存來源讀回、比較籃及結果表連續擺在同一頁；幾何雖無裁切，操作主次仍需要分層。後續依「每日操作主流程→來源核對→結果判讀→研究記錄」順序盤點，不把零幾何錯誤誤報為整體 UX 完成。
- 原生 GUI／Owner UAT 未執行；全程式文字、色彩對比、互動回饋與實際資料條件仍須另外檢視。
- 研究線索提示與收藏狀態文案同步後，`tests/test_ui_qt_unified_screener_workspace.py` 在受控 Windows Job **28 passed**；必要 Update UI **98 passed**、Update validator **25 passed／0 failed／4 skipped**，修改檔 `py_compile` 通過，unified screener source targeted mypy **0 issues**。初次 sandbox 執行為 **25 passed／1 failed／2 errors**，失敗皆涉及系統 Temp `WinError 5`；改用 repo basetemp 後同樣受 `Path.resolve(strict=True)` 權限阻擋，最後在可讀寫受控 Job 以原斷言通過。Repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因語法錯誤停止。受控收據位於 ignored `.tmp_ui_finish_20261029/screener_review_20261029_033806_52a8183d/`。

## 2026-10-29 第三十一輪：Recommendation 篩選捷徑與收藏狀態

Recommendation 入口將三個研究線索篩選捷徑放在來源頁與結果表之前，但「捷徑只設定條件、還要到來源頁按查詢」原先只在 Tooltip／下方狀態可見；無法收藏的來源按鈕仍顯示一般「儲存篩選條件」，原因藏在 Tooltip。現在捷徑旁直接說明下一步；來源未接收藏時按鈕標成「此來源未提供收藏」，來源已接通但暫時未符合條件時標成「目前無法收藏」，啟用時才顯示「儲存篩選條件」。收藏呼叫、來源 gating 與查詢流程不變。

- `tests/test_ui_qt_unified_screener_workspace.py` 與 `tests/test_ui_qt_recommendation_layout.py`：排除 3 個在 sandbox tmp path `resolve(strict=True)` 遇 WinError 5 的既有 fixture／整合案例後 **41 passed／3 deselected**；首輪原樣執行為 41 passed、1 failed、2 errors，3 個非通過均為同類型 temp path 權限問題。新增提示與收藏按鈕狀態斷言通過。
- Recommendation compact／scale 1.5 MainWindow offscreen 稽核：**46 子頁、0 failures／0 coverage gaps**；截圖核對捷徑提示可見且停用收藏有明確狀態文字。報告 `.pytest-owned-temp/ui_audit_recommendation_compact_round31/`。
- 必要 Update UI：**98 passed**；Update validator：**25 passed／0 failed／4 skipped**。修改 Python source／test `py_compile` 通過；Recommendation workspace scoped mypy **1 source、0 issues**。完整模組 mypy 仍在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤停止，無法檢查其餘模組。
- 使用者手冊同步說明捷徑查詢順序及收藏停用狀態；原生 GUI／Owner UAT 未執行，這次只改善 Recommendation 研究捷徑與收藏入口的可讀性。

## 2026-10-29 第三十二輪：Workbench 每日旅程移除重複下一步

offscreen 截圖檢視發現，Workbench 每日旅程摘要已列「下一步」，候選來源詳情又重複相同內容，增加首屏文字並切斷候選資訊與 Advice 的閱讀順序。現在候選來源詳情只列候選狀態、品質、來源日期、計數、母體限制與人工研究警語；下一步保留在每日旅程摘要。沒有改變 Advice、來源資格、候選篩選或保存行為。

- Workbench 相關 4 個測試檔：**88 passed**；必要 Update UI：**98 passed**。
- Update layout validator 因 owned QA runner 啟動前讀到可用實體記憶體低於規定的 8 GiB 而拒絕建立子程序；沒有放寬限制，也沒有執行 validator。
- 全域可讀性 runner 曾在 scale 1.25 已輸出 Workbench、Market Explore、Recommendation、Backtest 截圖後，於 Watchlist 頁以 `0x80000003` 中止；scale 1.5 未開始，沒有完整矩陣或結論。本輪此 runner 不列為通過。
- 本輪 `git diff --check` 對四個修改檔通過。Update validator、`py_compile` 與 repo-wide mypy 均在 owned QA runner 的 8 GiB 可用記憶體啟動門檻處被拒絕，未啟動子程序；不得視為已通過。Owner 原生 GUI／UAT 未執行，整體九工作區的操作理解與產品 Gate 仍未完成。

## 2026-10-29 第三十三輪：區分每日主要操作與證據追蹤

延續第 32 輪截圖覆核，旅程摘要內的研究 fallback 也用「下一步」標籤，與每日主要操作並列，造成兩個同名行動入口。現在主要操作保留「下一步」，fallback 後續改標「證據追蹤」，並保留建議動作、回看時間與不可推定機率／權重／買賣結論的限制。此修改只調整呈現標籤。

- Workbench 相關 4 個測試檔：**89 passed**；必要 Update UI：**98 passed**；Update validator：**25 passed／0 failed／4 skipped**。validator 的預設 `output/qa/update_tab/RUN_LOG.txt` 無法寫入，依腳本支援的 `BALDR_UPDATE_TAB_QA_LOG_DIR` 改導至 ignored `.pytest-owned-temp/ui_round33_update_validator_logs/`，隔離資料與 artifact 仍由 validator 自行建立。
- 修改 Python source／test `py_compile` 通過；Workbench source scoped mypy **1 file、0 issues**。repo-wide mypy 在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇語法錯誤，未能檢查其餘模組。
- `git diff --check` 通過。Owner 原生 GUI／UAT 未執行；仍需跨工作區實際資料流程的閱讀與操作覆核。

## 2026-10-29 第三十四輪：Recommendation 來源核對與查詢提示分層

Recommendation 首屏把「資料日期、來源版本」藏在泛稱的來源摺疊區，主狀態提示與技術條件捷徑也各自重複說明要再查詢。現在收合標題明列資料日期；主狀態提示引導核對所選來源／資料日並指出查詢按鈕位置；捷徑提示只解釋它會替換技術規則、不更動來源與其他條件，也不自動查詢。查詢、來源核驗、資料資格、收藏及金融邏輯未更動。

- Recommendation workspace＋layout：排除 3 個已確認在本 sandbox 以 `Path.resolve(strict=True)` 對測試暫存路徑遇 `WinError 5` 的 fixture 案例後，**41 passed／3 deselected**。未排除首輪為 **25 passed、1 failed、2 setup errors**；三個非通過均發生在暫存路徑的 strict resolve，沒有把它們記成產品測試通過。
- Recommendation 真實 MainWindow compact／scale 1.5 offscreen 稽核：**46 子頁、0 failures／0 coverage gaps**；截圖核對來源摺疊標題、來源／資料日核對提示與條件捷徑說明可見。報告 `.pytest-owned-temp/ui_audit_recommendation_round34/`。這是 offscreen 畫面證據，不等於原生 GUI／Owner UAT。
- 必要 Update UI **98 passed**；Update validator **25 passed／0 failed／4 skipped**。Validator 使用受支援的 `BALDR_UPDATE_TAB_QA_LOG_DIR` 將 log/report 寫入 ignored `.pytest-owned-temp/ui_round34_update_validator_logs/`，隔離資料及輸出仍由 validator 自己產生。
- 4 個修改 Python source／test `py_compile` 通過；兩個修改 UI source scoped mypy **0 issues**。repo-wide mypy 仍因未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤而停止。
- 手冊已同步新的收合區名稱與操作順序；Owner 原生 GUI／UAT、其他工作區逐頁資訊易讀性盤點仍未完成。

## 2026-10-29 第三十六輪：Backtest 來源假設入口併入結果導覽

Backtest 結果窗把「顯示完整來源與運算假設」獨立成橫跨結果欄的大型按鈕，讓結果頁選單、結果摘要和補充來源查找之間多出一整列操作區。現在結果頁選單與較低權重的「來源與假設」切換共用同一導覽列；展開的原始假設仍顯示於導覽列下方，僅在摘要／診斷／圖表頁可用，來源仍來自所選回測結果而非未保存草稿。

- `tests/test_ui_qt_backtest_product_layout.py`：**11 passed**；涵蓋導覽列共置、切換文字、原始結果來源及其他結果頁的顯示範圍。
- Backtest 真實 MainWindow compact／scale 1.5 offscreen 稽核：**110 子頁、0 failures／0 coverage gaps**；截圖 `.pytest-owned-temp/ui_audit_backtest_round35/scale_1_5/geometry_processes/compact/screenshots/scale_1_5/compact/backtest_entry.png` 確認大型按鈕列已移除並併入結果導覽。空結果表仍保留較大可視區，應以有結果情境另行審閱，沒有在本輪改其行為。
- 必要 Update UI **98 passed**；Update validator **25 passed／0 failed／4 skipped**，驗證輸出導至 ignored `.pytest-owned-temp/ui_round35_update_validator_logs/`。6 個修改 Python source／test `py_compile` 通過；三個修改 UI source scoped mypy **0 issues**；repo-wide mypy 仍在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因語法錯誤停止。
- 手冊同步結果頁與「來源與假設」的操作關係；原生 GUI／Owner UAT 未執行。

## 尚未完成的可理解性盤點優先序

幾何稽核覆蓋九工作區，但不證明資料齊全時的閱讀路徑、狀態顏色語意、主要操作是否就近，或新手能否完成流程。後續依下列順序逐項檢查，完成前不把 UI 整體盤點標成通過：

1. **Gate 1 Advice 資料情境**：Advice 展開後改為先核每日來源／保存結果，再讀理由限制、作者選填欄位與人工決定；完整判讀依內容展開並由 Workbench 外層頁面捲動，不再嵌套長文捲軸。合成 Advice 與跨頁 UI 回歸已覆蓋此順序；仍須以 canonical 保存結果走完來源核對、完整理由、人工決定、精確回查與 Journal，Owner 原生 GUI UAT 另由 Owner 執行。
2. **Recommendation 有結果情境**：合成載入結果已覆核並修正外層捲動被收合來源詳情攔截、保存來源 controls 垂直堆疊過長兩項版面問題；逐股來源詳情先呈現結論與下一步，推薦狀態列亦有語意色；條件捷徑現在會連動顯示尚未查詢／查詢中／完成／失敗，這段合成流程已有定向覆蓋。仍須用可核驗保存來源走完核驗、全域查詢、結果判讀／保存／比較，並完成 Owner 原生 GUI UAT。
3. **Backtest 成功／失敗結果**：空摘要與無交易列已收斂；成功閱讀順序先於原報酬、最大回撤、配對與成本卡；失敗狀態導讀以錯誤色標示，成功時復原。狀態測試與摘要幾何已覆蓋；仍須以已保存真實 run 複核摘要／明細、來源假設展開及補充查找的順序，原生 GUI／Owner UAT 未做。完整 layout 測試曾被 Qt WebEngine 原生例外中止，不能視為完整 suite 通過。
4. **其餘工作區資料情境**：Watchlist／Portfolio 的空態與載入列已做本地畫面／測試覆核；仍須以有內容的正式來源走主要旅程。Market Explore 已覆核空快照及有資料 synthetic DecisionDeskSnapshot 的摘要、警示、焦點與無產業列狀態；仍缺正式來源旅程及 Owner UAT。Stock Research 已修正無同源價格空卡並需再檢查有內容來源；Update 已修正寬版操作列並仍需正式來源旅程；Runtime 已收斂明細切換並仍需檢查有狀態色的多情境。全域 geometry／scroll coverage 不代替內容覆核。

## 2026-10-29 第九十二輪：市場焦點次要入口不再橫跨整列

Decision Desk 的市場焦點摘要後方原有「開啟焦點研究報告」與「查看完整市場資料」兩個全寬按鍵；後者又與下方「完整市場資料」收合分區重複。現在兩個次要導覽併入市場焦點底部同一短列，依文字自然寬度排列；個股研究仍沿用焦點日期／來源，完整資料捷徑仍展開原進階分區，分區本身的標題展開也保留。沒有變更快照、資料來源或決策邏輯。

- Decision Desk view＋MainWindow 導覽 targeted：**56 passed**；涵蓋兩個入口仍並列於焦點操作列、固定自然寬度，以及完整資料捷徑仍可展開分區。
- 1365×768 offscreen synthetic DecisionDeskSnapshot 已使用正式應用主題檢視；市場焦點下方入口保持短按鍵並列，沒有再切出兩整列主要內容；畫面 `.pytest-owned-temp/decision_desk_compact_actions_review/focus_actions_lower.png`。這不是正式來源旅程或 Owner UAT。
- 操作手冊與每日決策頁資訊提示已同步入口位置。必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**；修改的三個 Python 檔 `py_compile` 通過；Decision Desk／tab info scoped mypy **0 issues**。repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤停止；`git diff --check` 無 whitespace error（既有 fsmonitor IPC 與 CRLF 行尾提示）。UI feature／QA／手冊結構檢查 **12 features／5 link sources passed**；加入 Snapshot 的 task-wide 檢查另報既有 `output/` Junction `WinError 5` 與外部 task／trial 連結越界，未動那些連結。完整正式來源旅程與 Owner UAT 仍未完成。

## 2026-10-29 第九十三輪：Advice 來源先行與完整判讀單一外層捲動

展開 Advice 詳情時，最前面原本是完整判讀文字框，去「今日總覽」核對來源的入口在整段內容後面；長文另有自己的高度限制與捲軸，外層工作台還有第二個捲軸。現在把「核對每日來源與原始結果」放在詳情第一步，再讀完整理由／限制、作者選填說明，最後記錄人工研究決定。完整判讀文字窗依內容長度自動展開，禁用自己的捲軸並將高度回報外層頁面；內層章節取消第二套序號，保留清楚標題以免和外層閱讀步驟混淆；理由、來源值、作者欄位與保存契約不變。

- `tests/test_workbench_advice_contract.py`、Workbench 首頁、每日旅程、跨頁決定回查：**34 passed**；調整章節次序後來源／判讀順序和長文捲軸 focused 測例另 **2 passed**。涵蓋 Advice 章節順序、長文字、390 logical px 窄窗、內層捲軸為零及外層可捲動。修改 source/test `py_compile` 通過；`workbench_view.py` scoped mypy **0 issues**。
- 合成 Advice 使用正式應用主題 offscreen 生成 `.pytest-owned-temp/gate1_single_scroll_review/detail_and_actions.png` 與 `source_first.png`；詳情高度依內容擴張、內層捲軸最大值為 0，候選卡回報展開後高度。這只核合成 UI 幾何，不是 canonical 來源操作或 Owner UAT。
- 必要 Update UI：**102 passed**；Update validator：**25 passed／0 failed／4 skipped**；UI feature／QA document-control：**12 features／4 link sources passed**；`git diff --check` 無 whitespace errors（Git 仍回報既有 fsmonitor IPC／CRLF 提示）。Repo-wide mypy 仍被未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤阻止。操作手冊、Recommendation／Research Lab 手冊及 UI Feature 文件已同步。canonical 保存結果端到端與 Owner UAT 仍未完成。

## 2026-10-29 第九十四輪：研究時間軸窄版清單取消水平捲動

研究時間軸在窄窗會把來源、股票、保存時間與原文摘要四欄硬塞進清單表格；390 px offscreen 畫面出現表格自己的水平捲軸，時間和摘要被截斷，表格還留下無語意列號。現在清單表格不顯示列號；視窗寬度低於 1120 logical px 時暫藏原文摘要欄，保留來源、股票與完整台北保存時間。選取列後，下方詳情仍顯示完整原文與身份；寬版則恢復摘要欄。Journal、排序、結果搜尋和資料／來源語義不變。

- `tests/test_ui_qt_research_timeline_view.py`：**19 passed**，包含 390 px 隱藏摘要欄、無水平捲軸、列號隱藏及 1280 px 恢復摘要欄；原 Advice／Workbench 改善另見第九十三輪。
- 1366×768、900×700、390×844 合成 offscreen 畫面已核；390 px 畫面完整顯示來源、股票、保存時間，選取紀錄的原文在下方詳情閱讀。這只證明合成版面，不是原生 GUI／Owner UAT。
- 操作手冊與 UI Feature 文件已同步。時間軸測試 **19 passed**；必要 Update UI **102 passed**；隔離輸出 Update validator **25 passed／0 failed／4 skipped**；source/test `py_compile` 通過，`research_timeline_view.py` scoped mypy **0 issues**。Repo-wide mypy 仍被未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻止。UI Feature／QA document-control **12 features／2 link sources passed**；Manual check 唯有兩條既有 `output/trial/` 引用受 Junction `WinError 5 Access is denied` 阻擋，沒有改寫路徑。`git diff --check` 無 whitespace error（fsmonitor IPC／CRLF 提示仍在）。正式資料與金融判讀沒有變動；原生 GUI／Owner UAT 仍未完成。

## 2026-10-29 第九十五輪：Advice 無法核對同筆時仍可導覽至當日來源

先前只有 result ID／股票／日期精確吻合時，Advice 才有「今日總覽｜每日來源與排除」按鈕；吻合失敗時顯示純文字，使用者仍不知道每日來源在哪。現在若同筆捷徑不成立、但 Workbench 仍有可讀且非 stale 的每日來源，限制說明內提供緊湊文字連結「開啟今日總覽的來源核對」，明示只瀏覽當日內容、不代表已核對為本筆。沒有每日來源或資料 stale 時不提供連結；stale 切換會立即收起舊來源入口。精確同筆捷徑、來源資格、原 Advice 與保存／讀回契約未改。

- Advice contract＋Workbench 首頁／每日旅程／MainWindow 跨頁回查：**34 passed**，涵蓋精確同筆入口、非同筆的當日來源導覽及 stale 後撤除連結。修改 source/test `py_compile` 通過；`workbench_view.py` scoped mypy **0 issues**。
- 必要 Update UI **102 passed**；隔離輸出 Update validator **25 passed／0 failed／4 skipped**。Repo-wide mypy 仍由未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 既有語法錯誤阻止。UI Feature／QA document-control **12 features／2 link sources passed**；Manual 結構檢查唯一錯誤為兩份手冊中既有 12 條 `output/trial/` 引用受 Junction `WinError 5 Access is denied` 阻擋，未更動引用；`git diff --check` 無 whitespace error（fsmonitor IPC／CRLF 提示仍在）。操作手冊、Recommendation／Research Lab 手冊及 UI Feature 已同步。原生 GUI／Owner UAT 和完整程式 UI 盤點仍未完成。

## 2026-10-29 第九十六輪：共用收合區以文字、箭頭與狀態樣式減少視覺阻斷

跨工作區的 `CollapsibleSectionPanel` 原把內容標題做成膠囊標籤，旁邊再放固定寬、無文案的獨立按鈕；它讓可選來源與診斷分區的控制看起來像另一個主區塊。現在以段落標題搭配「展開／收合」文字和方向箭頭；常態透明底，懸停／按下及鍵盤聚焦分別可辨，控制尺寸維持緊湊。元件仍保留可程式設定的展開狀態、勾選狀態與呼叫端無障礙名稱；展開與收合只切換既有內容可見性，不改查詢、資料或條件。

- 共用元件與比較證據、Workbench、綜合選股、策略庫呼叫端：**8 passed**；較完整策略庫／Workbench／選股回歸 **43 passed／3 deselected**。原套件另揭露一項 Workbench 舊斷言仍要求重複候選筆數，已改為核對來源日及研究限制；三個被排除案例均在 sandbox `Path.resolve(strict=True)` 受 `WinError 5` 阻擋，未列通過。
- 必要 Update UI **102 passed**；隔離 log 的 Update validator **25 passed／0 failed／4 skipped**；修改 Python source/test `py_compile` 通過；`theme_widgets.py`／`workbench_view.py` scoped mypy **0 issues**。Repo-wide mypy 停於未修改 T164 bridge 第 411 行既有語法錯誤。`git diff --check` 無 whitespace errors（既有 fsmonitor IPC／LF→CRLF 提示）。
- 操作手冊補上共用收合控制與狀態提示說明；UI Feature 文件、Feature Map 與 Snapshot 同步。offscreen 測試不等同原生 GUI／Owner UAT；全程式 UI 盤點仍未完成。

## 2026-10-29 第九十七輪：Research Console 重讀動作併入載入狀態列

目前全桌面 1.5× offscreen 畫面顯示，Research Console 的「重新載入唯讀 projection」原本獨佔一整列，下一行才說明 projection 已載入；動作因此切開狀態與內容。現在把狀態和重讀按鈕放在同一水平列，狀態可換行、按鈕維持自然寬度；無障礙名稱及提示寫明只重讀既有唯讀投影，不執行更新或保存。沒有改來源、projection、資料或 gate。

- `tests/test_ui_qt_research_console_view.py`：**55 passed**；新增斷言核對狀態與按鈕同列父層、按鈕自然寬度及唯讀動作說明。
- MainWindow Workbench 全子頁版面稽核在 1.0×／1.5×、1400×800／1366×768／2293×912 三種 offscreen geometry：**39 子頁訪視／scale，0 failures、0 coverage gaps**。1.5×合成 Research Console 截圖 `.pytest-owned-temp/ui_audit_workbench_research_console_reload_20261029/scale_1_5/geometry_processes/default/screenshots/scale_1_5/default/fixture_workbench_scenario_synthetic_research_console.png` 已檢視；不代表 Windows 原生視窗框或 Owner UAT。
- 必要 Update UI **102 passed**；隔離 Update validator **25 passed／0 failed／4 skipped**；`research_console_view.py` scoped mypy **0 issues**、source/test `py_compile` 通過。Repo-wide mypy 仍停於未修改 T164 bridge 第 411 行既有語法錯誤。
- APPLICATION_MANUAL 與 UI Feature 說明已更新。UI Feature／QA／Manual／Snapshot document-control 核對列出 12 features／5 link sources；剩餘錯誤是既有 `output/` Junction 的 `WinError 5` 外部連結不可讀，沒有更動原引用。全程式 UI 盤點與原生 GUI／Owner UAT 持續中。

## 2026-10-29 第九十八輪：每日來源詳情分成日常核對與技術追溯

使用者回報推薦來源詳情一次列出契約 hash、SQLite 定位、rowset、時間與提示碼，閱讀入口也不清楚。現在第一層按「查看每日來源詳情」只列來源狀態、分類日期、適用範圍、產業來源狀態及 PIT 限制；第二層「查看技術追溯欄位」保留封存 hash、完整列觀察、儲存定位、時間戳及提示碼。兩層仍只讀同一個結果 ID 對應的 sealed snapshot，未知狀態不補值、不改來源資格或 Advice。

- 來源顯示／Recommendation layout **3 passed**，再加上 sealed source event 真正保存與精確讀回 **1 passed**；修改 source/test `py_compile` 通過。來源／版面兩檔完整測試曾執行 **39 passed／15 failed**；15 項中 13 項因 Windows sandbox 對 pytest 暫存讀寫／hard-link 的 `WinError 5` 拒絕而失敗，另 2 項為本次按鈕文案 assertion，修正後聚焦覆核通過。其餘來源持久化案例未因此記為已通過。
- 條件式 offscreen 截圖輸出在無中文字型的 sandbox 以方框顯示中文字，因此只確認區塊存在，不能作為文字可讀或原生畫面覆核；完整文案與分層由 assertion 核對，原生 Owner UAT 仍待。
- 必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**；`recommendation_view.py` scoped mypy **0 issues**。Repo-wide mypy 仍被未修改 T164 bridge 第 411 行既有語法錯誤阻擋。
- 操作手冊與 UI feature 說明已同步；原生 Owner UAT 與全程式 UI 盤點仍未完成。

## 2026-10-29 第三十五輪：Workbench Gate 1 首頁收合空態覆核

完成「下一步」與「證據追蹤」標籤分工後，以真實 MainWindow 對 Workbench compact／scale 1.5 重跑 offscreen 畫面與子頁稽核。空態首屏可同時看到每日旅程、分開的候選來源資訊及 Advice 載入狀態；Advice 不必先展開低優先級的「其他工作區捷徑」區塊。

- MainWindow Workbench compact／scale 1.5：**13 子頁、0 failures／0 coverage gaps**；截圖 `.pytest-owned-temp/ui_audit_workbench_round34/scale_1_5/geometry_processes/compact/screenshots/scale_1_5/compact/workbench_entry.png`。
- 這次截圖是「等待工作台資料載入」空態；它確認頁面閱讀層級與 Advice 入口位置，不驗證有資料 Advice、來源詳情或研究決定的原生 GUI 操作。Owner UAT 與載入資料情境的實際閱讀仍待完成。

## 2026-10-29 第三十七輪：Gate 1 Advice 展開詳情高度與操作密度

載入合成 Advice 後，展開卡片的判讀區重複顯示一份摘要；完整理由與機率來源按鈕橫跨整列；更關鍵的是詳情面板沒有把展開後高度回報給候選卡，來源文字、入口及研究決定會互相壓疊。現在卡片模式只保留卡面摘要，詳情操作改為緊湊並列；展開時依內容回報面板高度，讓外層工作台捲動承載後續來源與研究決定區，決定按鈕也維持靠左分組。表格選取模式仍顯示獨立摘要。沒有更動 Advice、來源資格、研究保存或讀回契約。

- Advice／Workbench 回歸（首頁、Workbench view、guided flow、Advice contract）：**89 passed**；必要 Update UI：**98 passed**；Update validator：**25 passed／0 failed／4 skipped**，輸出導至 ignored `.pytest-owned-temp/ui_round38_update_validator_logs/`。
- 以正式 QSS 與合成 Advice DTO 的載入畫面檢視，展開詳情高度由 368 增至 617 logical px；判讀文字結束後才接來源區，沒有再壓疊；摘要只留卡面一次，兩個判讀入口並列。截圖 `.pytest-owned-temp/gate1_advice_detail_round37.png` 及 `gate1_advice_detail_screen_round37.png`。這是合成資料與 offscreen 畫面，不核驗 canonical 來源或研究紀錄端到端，也不是 Owner UAT。
- Workbench compact／scale 1.5 MainWindow offscreen 稽核：**13 子頁、0 failures／0 coverage gaps**；scoped mypy **0 issues**，修改 Python 檔 `py_compile` 通過。必要 repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因語法錯誤停止。`git diff --check` 通過；Git 只提示兩份 Markdown 會由 LF 轉 CRLF，未列 whitespace error。
- 手冊已同步摘要去重及緊湊詳情入口；canonical 結果逐欄核驗、真實來源至 Journal 的完整端到端仍待執行，不能由合成畫面推定 Gate 1 或 Owner UAT 通過。

## 2026-10-29 第三十八輪：Recommendation 成功結果頁捲動與保存操作列

合成成功結果畫面暴露兩個首屏問題：收合的來源詳情內含另一個 `QScrollArea`，被外層判定為巢狀捲動而關掉結果頁捲軸，導致下方結果表與判讀區無法到達；保存來源控制項也曾垂直堆成多列，擠壓結果內容。現在只有實際可見的巢狀捲動區才會取代外層捲動；保存結果分為來源選擇列與操作列，窄版才垂直堆疊，取消讀取只在載入期間顯示。沒有改變來源選擇、推薦執行、保存、資格或金融邏輯。

- Recommendation 成功結果的合成 offscreen 畫面確認外層捲動範圍恢復、結果表可到達、操作列由多列收斂為兩列。此證據只驗版面，不代表 canonical 來源核驗或 Owner UAT。
- 兩個目標測試檔完整執行為 **41 passed、3 個受 sandbox Temp strict resolve 阻擋**（1 failed、2 setup errors，三者均 `PermissionError: [WinError 5]`）；精確排除這 3 個案例後 **41 passed／3 deselected**。必要 Update UI **98 passed**，Update validator **25 passed／0 failed／4 skipped**；兩個修改 UI source scoped mypy **0 issues**，Python source/test `py_compile` 與 `git diff --check` 通過。Repo-wide mypy 仍在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因語法錯誤停止。
- 使用者手冊已同步來源選擇／操作列分組、窄版排列與結果外層捲動提示；完整保存來源到結果判讀／比較的真實資料旅程仍待覆核。其他工作區、原生 GUI／Owner UAT 與全程式閱讀理解檢查尚未完成。

同輪補查 Backtest 合成結果頁發現，當次摘要為空時的文字框與無交易資料表仍各自佔據大塊空間，將交易細節推到下方。現在空摘要框收起，長摘要最高 320 logical px 並保留框內捲動；無交易列時表格改為一行空態，有列才顯示可捲動的交易表。這只改版面呈現，不改資料或交易邏輯。

- Backtest 空態／長摘要／有列切換測試加 Backtest product layout：**12 passed**。完整 `tests/test_ui_qt_backtest_layout.py` 因原生 `QWebEngineView` 初始化在 `fast_chart_widget.py:195` 觸發 Windows fatal exception `0x80000003`，尚未完成；略過首個觸發後第二個圖表初始化測試仍觸發相同例外，因此不把完整 suite 記為通過。
- MainWindow compact／scale 1.5 offscreen 幾何：**19 頁、0 failures／0 coverage gaps**。截圖 `.pytest-owned-temp/ui_audit_backtest_summary_round38c/scale_1_5/geometry_processes/compact/screenshots/scale_1_5/compact/backtest_entry.png` 確認空交易明細只留一行提示。已有合成保存結果截圖確認有資料表格仍能顯示列，但不是本次修改後的成功保存讀回或 Owner UAT。
- 本輪 Backtest Python source／test `py_compile`、兩個 Backtest UI source scoped mypy 與 `git diff --check` 通過；repo-wide mypy 同樣在未修改 T164 檔案語法錯誤停止。

## 2026-10-29 第三十九輪：Watchlist／Portfolio 空態與候選列閱讀

檢視兩個工作區的窄版 offscreen 畫面與空態程式路徑後，沒有發現需要再加一組空面板或重排按鈕的證據：Watchlist 在載入中、讀取失敗、已載入空清單和搜尋無命中時分別顯示未知／零列狀態，載入列仍有清楚的候選摘要和操作群；Portfolio 在零持倉時保留「活躍持倉 0 檔」及未讀取／未知說明並隱藏持倉表，有列才顯示表格。Portfolio 的破壞性清空動作屬進階區，非預設主列。沒有更動這兩個工作區。

- Watchlist empty/missing/unavailable 與已載入候選搜尋、Portfolio 空 DTO 後恢復持倉列、Paper 空態及分點明細空／有列共五個針對性測試：**5 passed**。
- 既有 compact／scale 1.5 offscreen 截圖供空態版面覆核；Watchlist 符合計數和 Portfolio table visibility 另由上述程式與測試驗證。這不是正式資料驗證或 Owner UAT；兩工作區的 canonical 有內容旅程仍需逐項覆核。
- 下一項盤點轉 Stock Research；Update、Runtime 的資料情境仍待檢查。

## 2026-10-29 第四十輪：Market Explore 無產業列時收起空操作列

以每日決策完整合成摘要檢視首屏及捲動底部：摘要、主結論、市況廣度、焦點及完整市場資料的層級可辨；但在可比產業資料缺件時，層級選單仍呈空白框，領先／落後定位按鈕雖停用卻仍佔一列。現在沒有產業列時隱藏空層級選單與整列不可用定位控制；資料摘要仍保留 `Unknown` 及非 0 限制。有列時恢復選單與定位列；全 Unknown 群組保留 Unknown 說明及群組切換。沒有改計算、來源或資格邏輯。

- `tests/test_ui_qt_decision_desk_view.py` 的含零／未知、多群組定位、無來源列清空與 all-unknown／partial-unknown 三個相關案例：**3 passed**。
- 以正式 QSS、合成 DecisionDeskSnapshot 在 1366×768 offscreen 檢視載入首屏、警示展開、焦點展開與捲動底部。捲動底部確認缺件時只保留產業標題與 Unknown 摘要，沒有空選單／停用定位列；這不是正式來源或 Owner UAT。
- 使用者市場手冊已說明無列、全 Unknown、有可比值三種呈現差異。其他工作區與 Market Explore 的真人操作仍待驗收。

## 2026-10-29 第四十一輪：個股研究無同源價格時收合空圖卡

個股研究合成載入畫面在價格來源／日期核驗失敗時，仍把沒有圖表的價格卡與五問摘要等高並列；未選股票時也預留空卡。卡片內的限制文字雖然正確，過大的空白區讓它看起來像尚未載入完成。現在只有有同源可核驗價格時才顯示圖表卡；沒有價格、核驗失敗或圖表無法呈現時，將價格及報酬狀態收合成五問摘要下方的一條訊息。未選股／切換中也用同一位置提示狀態。資料來源、價格投影、報酬計算和資格完全未改。

- 個股報告與摘要測試：**101 passed／1 deselected**，涵蓋未載入、股票身份不符、同來源價格缺件及可用價格圖表狀態切換。獨立重跑該 MainWindow ML registry 注入測試仍因隔離資料／輸出根目錄下的 `MLResearchOutputBoundaryError` 而得到 `registry is None`；首次使用系統 Temp 時另出現 Watchlist 原子替換 `WinError 5`。這個既有整合案例不因其他 UI 測試通過而視為已驗。
- 真 MainWindow compact／scale 1.5 offscreen 幾何與捲動稽核：**1 工作區、0 errors／0 coverage gaps**；畫面複核確認未選股時不再預留並排空價格卡，狀態訊息位於五問摘要下方。輸出 `.pytest-owned-temp/ui_audit_stock_research_round41/`。這只驗版面與合成服務狀態，不等於有資料研究旅程、正式來源核驗或 Owner UAT。
- 必要 Update UI **98 passed**、Update validator **25 passed／0 failed／4 skipped**；Stock Research view scoped mypy **0 issues**，修改 Python 檔 `py_compile` 與 `git diff --check` 通過。測試檔本身有既有型別錯誤，不納入 scoped mypy 通過宣稱。repo-wide mypy 仍因未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤而停止。整體盤點仍需繼續檢查 Stock Research 有內容操作、Update／Runtime 與其他工作區的真實資料旅程。

## 2026-10-29 第四十二輪：資料更新寬版操作列收斂

資料更新看板的寬版「立即操作」曾將快速更新、安全更新和狀態檢查三鍵按不同比例拉滿整列，按鈕重量壓過資料影響摘要與來源卡；下方唯讀時間軸、候選、P0 與 readiness 明細也都是整列大按鈕。現在寬版主要操作依文字自然寬度靠左排列，窄版保留滿寬直向操作以維持可點性；下方唯讀明細使用靠左、依狀態標示「展開／收合」的短文字入口。底部伸展空間保留作為剩餘高度承接，不再移除造成其他內容被垂直拉開。更新流程、按鈕作用、互斥與資料判讀完全未改。

- `tests/test_ui_qt_update_view_workbench.py`：**99 passed**，含寬／窄版主操作按鈕、唯讀明細入口尺寸策略與展開狀態回歸。必要 Update validator：**25 passed／0 failed／4 skipped**，最終本輪 log/report 導至 `.pytest-owned-temp/ui_round44_update_validator_logs/`。
- MainWindow Update compact／scale 1.5 offscreen 稽核：**1 工作區、0 errors／0 coverage gaps**；首屏截圖 `.pytest-owned-temp/ui_audit_update_round42c/scale_1_5/geometry_processes/compact/screenshots/scale_1_5/compact/update_entry.png` 與底部 `.pytest-owned-temp/ui_audit_update_round42d/scale_1_5/geometry_processes/compact/screenshots/scale_1_5/compact/update_scrollbottom.png` 確認主要操作靠左、唯讀明細不再拉滿整列。寬版畫面中的摘要、卡片與折疊診斷仍需依正式來源完成資訊閱讀覆核；未點擊更新，未做 Owner UAT。
- Update view scoped mypy **0 issues**；Stock Research／Update 修改 Python 檔 `py_compile` 通過，`git diff --check` 通過（Git 只有既有 fsmonitor IPC error 訊息與 LF→CRLF 提示）。repo-wide mypy 仍受未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻擋。全程 UI 盤點仍在進行。

## 2026-10-29 第四十三輪：Runtime 唯讀明細控制文字收斂

Runtime 頁三個唯讀明細切換原以「展開／收合」及整列按鈕呈現，在排程狀態與資料來源診斷之間形成第二層寬操作區。現在入口靠左依內容寬度排列，文案隨狀態明確切換「展開：…／收合：…」，tooltip 和可存取名稱說明只切換明細可見性，不重新讀取或啟動工作。資料狀態分布、分組、篩選及健康判讀不變。

- `tests/test_ui_qt_runtime_view.py`：**26 passed**，涵蓋開關文字、窄版主要版面及既有操作／治理事件呈現。
- Runtime MainWindow compact／scale 1.5 offscreen 幾何與捲動稽核：**1 工作區、0 errors／0 coverage gaps**；截圖 `.pytest-owned-temp/ui_audit_runtime_round43b/scale_1_5/geometry_processes/compact/screenshots/scale_1_5/compact/runtime_entry.png` 確認唯讀明細切換按鈕已靠左收斂；沒有啟動排程或治理工作。必要 Update UI **99 passed**，validator **25 passed／0 failed／4 skipped**；三個修改 UI source scoped mypy **0 issues**，六個 Python source／test `py_compile` 通過，`git diff --check` 通過。Repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤停止。Owner UAT 未做。

## 2026-10-29 第四十四輪：Advice 詳情閱讀順序與來源目的地

Advice 展開詳情原先把共用判讀、來源證據、作者說明及原始理由連成長段文字，三個回查入口也未在按鈕上指出目的地。現在詳情先列股票、推薦結果 ID、決策日與行情資料日，再依序標記判讀限制、同筆逐股來源、選填作者說明與原始理由；來源入口標出「今日總覽」「綜合選股」「研究紀錄與覆盤」目的地。詳情文字框可視高度調整為 200–480 px，降低內層捲動。保存、讀取、導航與資格邏輯未變。

- `tests/test_workbench_advice_contract.py`：**16 passed**；必要 Update UI：**99 passed**；Update validator：**25 passed／0 failed／4 skipped**，報告 `.pytest-owned-temp/ui_round44_advice_detail_validator_logs/VALIDATION_REPORT.md`。Workbench MainWindow compact／scale 1.5 offscreen 幾何與捲動稽核：**13 子頁、0 failures／0 coverage gaps**，報告 `.pytest-owned-temp/ui_advice_detail_round44/report.md`。修改 source／test `py_compile` 通過，Workbench view targeted mypy **0 issues**。repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇既有語法錯誤而停止；`git diff --check` 通過；Git 輸出既有 fsmonitor IPC 與 LF→CRLF 提示，沒有 whitespace error。
- 此輪只核對 Advice 詳情的合成 DTO／介面契約；不代表已核驗正式資料來源或完成 Owner UAT。整體 UI 盤點仍進行中。
## 2026-10-29 第四十五輪：綜合選股來源詳情身份與長文閱讀

使用者提供的來源詳情含 result ID、名冊契約／artifact hash、產業指數 rowset 證據與 PIT 限制；原面板在完整核驗區未先標本筆 result ID，且內層來源區上限 220 px，容易失去推薦身份並反覆捲動。現在完整來源區開頭列精確保存推薦 ID，可視高度上限提高至 420 px；保留逐項來源、hash、時間狀態與 unknown 提示，不改任何核驗／資格計算。

- `tests/test_ui_qt_personal_recommendation_choice.py::test_company_source_display_uses_only_the_matching_sealed_event`：**1 passed**。整檔測試 **22 passed／12 failed**；失敗為 Windows sandbox 系統 Temp 的 atomic replace/hardlink 權限錯誤，以及 learning root `unsafe_or_unreadable`，不是本次來源顯示斷言；此整檔不可列通過。必要 Update UI **99 passed**；Update validator **25 passed／0 failed／4 skipped**，`.pytest-owned-temp/ui_round45_update_validator_logs/VALIDATION_REPORT.md`。兩個 UI source scoped mypy **0 issues**；修改 4 檔 `py_compile` 通過，`git diff --check` 通過。Repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因既有語法錯誤停止。
- 這輪只呈現保存身份並增加閱讀高度；產業指數與公司名冊來源仍維持既有未知／未核驗狀態，不代表資料資格已通過。
## 2026-10-29 第四十六輪：研究歷史查找回饋與保存持續性

研究紀錄頁可由 Advice 以 result ID 直達，但搜尋區沒有直接說明歷史不依賴今日候選；少於 500 筆時，ID 篩選成空表也沒有清楚的零符合狀態。現在搜尋區直接說明 Journal 保存持續性與完整 ID 用法；placeholder 明示完整 result ID；狀態分開描述目前清單的符合數、完整 Journal 搜尋中／結果、完整已載入歷史的零符合。

- `tests/test_ui_qt_research_timeline_view.py`：**17 passed**；`tests/test_cross_page_decision_journey_mainwindow.py::test_actual_mainwindow_cross_page_decision_journey_round_trip`：**1 passed**，覆核 Workbench Advice 帶 exact result ID 導航至 Journal、讀回決定與同筆身份。必要 Update UI **99 passed**；Update validator **25 passed／0 failed／4 skipped**，`.pytest-owned-temp/ui_round46_update_validator_logs/VALIDATION_REPORT.md`。ResearchTimeline scoped mypy **0 issues**，本輪 6 個修改 Python 檔 `py_compile` 通過，`git diff --check` 通過。Repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因既有語法錯誤停止。
- 此輪只改搜尋提示及唯讀狀態文字，未修改 Journal 查詢、保存或排序契約；真實 Owner UAT 仍待執行。
## 2026-10-29 第四十七輪：Recommendation／來源流程回歸盤點

綜合選股來源詳情會先標本筆 `result_id`，展開來源區的可視上限 420 px。Recommendation 寬版／窄版操作與空態排版回歸 **16 passed**；完整來源顯示專項 **1 passed**，涵蓋保存 result ID、unknown／PIT 限制、摘要／詳情切換。統一選股工作區整檔在系統 Temp 與 workspace basetemp 兩種隔離位置都各得 **25 passed／1 failed／2 errors**；三個非通過都在 `Path.resolve(strict=True)` 的 sandbox 權限限制（系統 Temp 或 workspace temp subdirectory），不能列全檔通過。Recommendation source scoped mypy、4 檔 py_compile 與 `git diff --check` 在前輪通過；必要 Update UI／validator 最新收據見第 46 輪。來源資料與資格邏輯不變，成功結果含真實來源的 Owner UAT 尚未完成。
## 2026-10-29 第四十八輪：共用次要文字對比修正

共用 theme 的 `text_muted=#788496` 在最亮的共用底色 surface_3 (`#223047`) 只有 **3.50:1**，低於一般文字 4.5:1；次要、未知與中性說明在部分卡片上因此偏灰。現在調整為 `#909aaa`，於 app_bg／surface_1／surface_2／surface_3 的最低對比為 **4.67:1**；功能色與市場方向色不變。新增共用文字 token 對比回歸，防止之後再次低於門檻。

- `tests/test_ui_qt_theme.py`：**14 passed**；必要 Update UI **99 passed**；Update validator **25 passed／0 failed／4 skipped**，`.pytest-owned-temp/ui_round48_theme_validator_logs/VALIDATION_REPORT.md`。
- 4 個修改 UI source targeted mypy **0 issues**；本輪 8 個修改 Python source／test `py_compile` 通過；`git diff --check` 通過。repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇既有語法錯誤而停止。
- 對比測試只核對共用文字與四種 theme surface，未取代其他各頁的色彩語意盤點、原生 GUI 視覺覆核或 Owner UAT。

## 2026-10-29 第四十九輪：Backtest 執行錯誤留在結果工作區

Backtest worker 直接回報錯誤時，原流程只顯示一次 modal；關閉後摘要區仍空白，錯誤原因沒有留在使用者正在查看的結果工作區。現在錯誤會持續顯示於「實驗摘要」，明確標示沒有可判讀／可保存結果，並停用保存、匯出與升級入口；仍保留短錯誤提示。結果失敗 DTO 的原隔離路徑與交易明細空態不變，沒有改回測計算或資料來源。

- `tests/test_ui_qt_backtest_trade_diagnostics.py`、`tests/test_ui_qt_backtest_product_layout.py`：**43 passed**。必要 Update UI **99 passed**；Update validator **25 passed／0 failed／4 skipped**，報告 `.pytest-owned-temp/ui_round49_validator_logs/VALIDATION_REPORT.md`。Backtest view scoped mypy **0 issues**、source/test `py_compile` 與 `git diff --check` 通過。Repo-wide mypy 因未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 既有語法錯誤停止。
- 已同步操作指南，提醒關閉提示後可在「實驗摘要」讀失敗原因，解決來源／設定後重新執行。本輪驗 worker 錯誤回報及失敗 DTO 的摘要持續性與操作隔離；未完成整個 Backtest 工作區及整體程式 UI 盤點，原生 GUI／Owner UAT 未做。

## 2026-10-29 第五十輪：Backtest 摘要卡與詳情去重

成功回測的卡面已突出原總報酬、原最大回撤、完成配對數及成本假設，但下方文字又重列總報酬、最大回撤與配對數，讓同一結果在相鄰區塊讀兩次。現在 live summary 由卡面承擔這三個數值，文字區保留 SOP／零配對限制、年化／Sharpe／勝率／期望值等其他指標；成交筆數、交易明細列數和期末持股仍在獨立「當次執行觀測」列顯示。一般 `format_backtest_summary` 預設行為保持原樣，只有已有顯眼卡面的 UI 呼叫使用去重選項；未改計算或保存內容。

同一合成成功畫面也顯示頁面選單把使用者可讀的「實驗摘要」再拼上內部 route key，呈現為「實驗摘要 › summary」。現在單層頁面選單只顯示可讀頁名，內部識別仍只留在 route data。

- Backtest formatter、OutcomeSummary、product layout 與 live diagnostics：**57 passed**。隔離成功結果 offscreen 畫面 `.pytest-owned-temp/backtest_summary_round50.png` 已用正式 QSS 檢查：結果列顯示可讀頁名「實驗摘要」、卡面四項重點、文字區 SOP／其他績效／成交觀測；這不是 canonical 結果或 Owner UAT。
- 必要 Update UI **99 passed**；Update validator **25 passed／0 failed／4 skipped**，`.pytest-owned-temp/ui_round50_validator_logs/VALIDATION_REPORT.md`。三個修改 UI source scoped mypy **0 issues**；六個修改 Python source／tests `py_compile` 通過；`git diff --check` 通過。Repo-wide mypy 仍在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因既有語法錯誤停止。原生 GUI／Owner UAT 未做。
- 操作手冊已同步卡面／詳細文字分工及缺失成交觀測保持未知的閱讀順序。整體 UI 盤點繼續進行；此輪不構成 Backtest 全模式或程式整體驗收。

## 2026-10-29 第五十二輪：Recommendation 資料來源層級與狀態摘要

推薦頁原本用「查看資料與來源細節」和「查看完整來源欄位與核驗資料」兩個近似名稱，沒有說清楚前者是整次分析、後者是所選股票；頂端資料摘要與結果狀態也重複要求先閱讀理由／風險。左右分欄後，約 790 px 寬的結果欄仍把資料摘要旁的短切換按鈕堆到下一行，摘要區因此近百像素高。現在入口分別標成「本次資料日期與來源」及「查看此股完整來源與核驗資料」；摘要只列資料日與候選／未入選筆數，狀態列只說明分析狀態與選列可讀的理由、風險及來源。資料摘要與切換入口在結果欄至少 560 px 時並排，較窄才上下排列。此輪只調整呈現與引導，不改推薦、來源或資格判定。

- `tests/test_ui_qt_recommendation_layout.py`：**17 passed**，覆核全體資料 context 與逐股來源入口的名稱、顯示狀態，摘要／狀態分工及不同欄寬下的入口方向。必要 Update UI：**99 passed**；Update validator：**25 passed／0 failed／4 skipped**，報告 `.pytest-owned-temp/ui_round51_update_validator_logs/VALIDATION_REPORT.md`。
- 同步無障礙名稱後重跑兩個相關案例：**2 passed／15 deselected**；Recommendation source 與 tab help scoped mypy **0 issues**，3 個修改 Python source／test `py_compile` 通過。
- 1366×768 合成結果頁以正式 QSS 重拍 `.pytest-owned-temp/recommendation_success_round51.png`；結果欄 789 px 時，摘要與切換入口同列 29 px，表格可見高度由 222 px 增至 257 px，確認少一列控制項後把空間還給結果。合成狀態不代表真資料或 Owner UAT。
- Recommendation source scoped mypy、修改 Python 檔 `py_compile` 通過。Repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因既有語法錯誤停止；`git diff --check` 通過（Git 顯示既有 LF→CRLF 提示）。
- 操作指南已同步兩個來源入口的層級與狀態摘要分工。畫面證據為合成 UI；資料來源完整端到端、原生 GUI／Owner UAT 與全程式 UI 盤點仍未完成。

## 2026-10-29 第五十三輪：研究決定與註記數分開呈現

Owner 回報的保存回條顯示「Journal 紀錄：0 筆」，但 `active_note_count` 實際只計文字註記；已納入／略過決定是獨立的研究動作。把兩者共用「Journal 紀錄」會讓成功保存看起來像沒有留下任何資料。現在 controller 與決定面板改稱「另加註記」，明示不含研究決定，並獨立列「研究動作歷史」；Workbench 保存成功後標示「研究紀錄與覆盤｜查找這筆」及 exact result ID 查找路徑。保存、Journal schema、決定身份和行為均未改。

- Advice contract、Decision Continuity controls／controller 與 MainWindow Advice→研究決定→Journal 精確讀回跨頁案例：**34 passed**；必要 Update UI：**99 passed**；Update validator：**25 passed／0 failed／4 skipped**，報告 `.pytest-owned-temp/ui_round53_update_validator_logs/VALIDATION_REPORT.md`。
- 三個修改 UI／service source scoped mypy **0 issues**；7 個修改 Python source／test `py_compile` 通過；`git diff --check` 通過（既有 LF→CRLF 提示）。Repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因既有語法錯誤停止。
- 操作手冊已說明「註記 0 筆」不代表決定未保存，以及按 result ID 找回方式。該跨頁測試使用隔離 Journal fixture；正式資料保存紀錄與 Owner 原生 GUI UAT 仍依 Gate 1 檢核卡另行確認。

## 2026-10-29 第五十四輪：Advice 直達研究決定時解除舊來源篩選

Advice 的「研究紀錄與覆盤｜查找這筆」會把完整 `result_id` 傳到研究時間軸，但若該頁先前選的是手動筆記、報告等其他來源，舊來源篩選會把研究決定藏起來，讓精確導覽看似沒有找到。現在以 Advice 進入時自動切換到「研究決定」，再依完整 `result_id` 篩選／搜尋；一般手動查找仍可自行切換來源。沒有變更 Journal 查詢、保存或研究決定契約。

- `tests/test_ui_qt_research_timeline_view.py`：**17 passed**，包含先選「手動筆記」再由 result ID 查找時會切回「研究決定」並顯示同筆決定。必要 Update UI：**99 passed**；Update validator：**25 passed／0 failed／4 skipped**，報告 `.pytest-owned-temp/ui_round54_update_validator_logs/VALIDATION_REPORT.md`。
- `ui_qt/views/research_timeline_view.py` scoped mypy **0 issues**；兩個修改 Python 檔 `py_compile` 通過；停用 Git fsmonitor IPC 後 `git diff --check` 通過。Repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因既有語法錯誤停止。
- 本 QA 文件的 `document_control check` 通過（12 features／1 link source）；兩本手冊的檢查仍被既有 `output/trial/` Junction `WinError 5` 阻擋，非本輪新增連結；未觸碰封存路徑。
- 操作手冊已補充直達時會自動切到「研究決定」。此修正只關閉已辨識的跨頁可尋找性斷點，不代表整體研究記錄 UI 或 Gate 1 Owner UAT 完成。

## 2026-10-29 第五十五輪：Recommendation 技術母體空結果收合

Recommendation 的「每日研究／技術母體」未載入或查詢零符合時，空表仍撐滿結果區，單頁也保留停用的翻頁按鈕；多個換行標籤還分攤版面剩餘高度，讓空白區隔開查詢摘要和操作。現在零列時以一行、依文字高度排列的提示取代表格；尚未載入與查詢零符合會顯示不同提示，並沿用上方摘要區分來源未核驗及已核驗母體計數。資料表只在有列時顯示；只有多頁結果顯示翻頁操作。增加主版面底部伸展區，剩餘高度落在內容末端，不再拉高中間標籤。來源、查詢、母體、分頁資料及金融邏輯未改。

- `tests/test_ui_qt_daily_market_technical_universe_v4_view.py`：**11 passed**，涵蓋未載入提示、已核驗 257 檔多頁結果、精確個股下鑽、零符合與恢復結果。合成來源 fixture 的 `Path.resolve(strict=True)` 在 sandbox 內被 `WinError 5` 阻擋；取得受控本機路徑核驗後以隔離暫存根跑完原整檔，未排除案例。
- Recommendation MainWindow compact／scale 1.5 offscreen 稽核：**1 工作區、0 errors／0 coverage gaps**，報告與截圖在 `.pytest-owned-temp/ui_audit_recommendation_empty_round55b/`；空提示、比較籃及狀態標籤高度均為 **16 logical px**，先前會被拉到 141 px。這是 offscreen 合成工作區，不是 Windows 原生 GUI 或 Owner UAT。
- 必要 Update UI：**99 passed**；Update validator：**25 passed／0 failed／4 skipped**，`.pytest-owned-temp/ui_round55_update_validator_logs/VALIDATION_REPORT.md`。修改 view scoped mypy **0 issues**；兩個 Python 檔 `py_compile`、`git diff --check` 通過。Repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因既有語法錯誤停止。
- 使用者手冊已同步空結果提示、零符合摘要及單頁收合翻頁的判讀。Recommendation 有效保存來源端到端與原生 GUI／Owner UAT 仍未完成；這項 UI 改善不授予來源資格或 Gate 1 接受。

## 2026-10-29 第五十六輪：Recommendation 結果標題與操作分組

「推薦結果與風險判讀」標題列原先混放保存、觀察清單、個股研究與研究／匯出按鈕，閱讀標題會被多個操作入口打斷。現在標題列只保留標題及延伸欄位切換；各結果操作集中在下一列，再接結果狀態與表格。一般結果欄較窄時操作改垂直排列；已精確讀回的保存結果在足夠寬度時可並列。保存／讀取／研究動作本身未改，另保留既有 saved-result row 名稱供相關版面使用。

- Recommendation layout 與保存結果精確讀回版面：**19 passed**；新增斷言確認標題／操作／狀態次序、標題不承載個股研究操作，以及保存讀回前後控制列的響應排列。
- 必要 Update UI：**99 passed**；Update validator：**25 passed／0 failed／4 skipped**，日誌與報告在 `.pytest-owned-temp/ui_round56_update_validator_logs/`。validator 預設 `output/qa/update_tab/RUN_LOG.txt` 受工作區權限拒絕；使用既有 `BALDR_UPDATE_TAB_QA_LOG_DIR` 導至隔離目錄後完成。
- `recommendation_view.py` scoped mypy **0 issues**；2 個修改 Python 檔 `py_compile` 通過；`git diff --check` 通過（僅既有 LF／CRLF 警告）。Repo-wide mypy 仍在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因既有語法錯誤停止。
- 本 QA 文件 document-control **12 features／1 link source／0 errors**。Application manual document-control 仍受既有兩個 `output/trial/` junction 外部連結越界阻擋，與本輪新增操作說明無關。
- 畫面驗證為 Qt offscreen 合成測試，沒有執行原生 GUI／Owner UAT；Recommendation 正式保存來源端到端與全程式 UI 盤點仍未完成，本輪不構成 Gate 1 接受。

## 2026-10-29 第五十七輪：今日總覽每日來源詳情入口定位

每日來源詳情雖可由 Advice 精確同源直達，但今日總覽自己的入口仍和 Advice 判讀、觀察清單及證據成熟度按鈕混在同一操作列，且名稱「展開本次來源、篩選與排除」沒有直接沿用使用者尋找的「每日來源詳情」。現在把「查看每日來源詳情」放在候選來源摘要正下方，獨立成「來源核對」小列；選股與其他研究操作仍留在候選選擇列。Advice 同源直達仍展開同一區塊，來源摘要與資格邏輯不變。

- `tests/test_ui_qt_workbench_home_single_page.py`、`tests/test_workbench_advice_contract.py`、`tests/test_cross_page_decision_journey_mainwindow.py`：**28 passed**；首頁測試確認入口緊接候選來源摘要、獨立於其他動作列；Advice contract／MainWindow 跨頁案例確認精確同源展開仍可用。
- 必要 Update UI：**99 passed**；Update validator：**25 passed／0 failed／4 skipped**，輸出於 `.pytest-owned-temp/ui_round57_update_validator_logs/`。
- `workbench_view.py` scoped mypy **0 issues**；本輪 2 個修改 Python 檔 `py_compile` 通過。Repo-wide mypy 仍由未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤阻斷。
- 操作手冊已把入口位置更新為「今日總覽 → 候選來源摘要下方 → 查看每日來源詳情」，並保留只讀及未知狀態限制。
- 本輪只調整入口位置與文字，未更動正式資料、來源讀取、Advice identity 或金融邏輯；offscreen UI 測試不能代替 Owner 原生 GUI UAT。

## 2026-10-29 第五十八輪：每日來源摘要的身份與缺件判讀順序

每日來源詳情展開後，result ID 原本排在證據成熟度段落尾端；使用者要先辨識「這是哪一次結果」時，得先讀過其他區塊。空排除摘要的文字也只說「沒有可顯示摘要」，容易被讀成「沒有排除」；成熟度窗口仍用 `total/ready/waiting/missing` 技術欄名。現在先列本次結果與 result ID，再列篩選／排除及證據觀察；缺少摘要時明說來源未提供、不能推定沒有排除；窗口數字改以「總數、已就緒、待成熟、缺漏」顯示。來源原值、空值與事件仍維持唯讀且不補造。

- `tests/test_workbench_advice_contract.py`：**16 passed**；包含每日來源展開、結果身份順序、空排除摘要的未知語意與進階事件欄隔離。
- 必要 Update UI：**99 passed**；Update validator：**25 passed／0 failed／4 skipped**，輸出於 `.pytest-owned-temp/ui_round58_update_validator_logs/`。
- `workbench_view.py` scoped mypy **0 issues**；本輪 2 個修改 Python 檔 `py_compile` 通過。Repo-wide mypy 仍被未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤阻斷。
- 操作手冊已同步來源詳情的閱讀順序、窗口欄名及空摘要限制。
- 本輪不改來源擷取、資料資格、Advice 或金融邏輯；offscreen 測試不等同 Owner 原生 GUI UAT。

## 2026-10-29 第五十九輪：Advice 來源理由回歸判讀依據

Advice 詳情的文字流程先說明判讀、逐股來源證據和作者契約，最後才附上來源理由／論點；使用者需要在作者欄後回頭找建議根據。現在把來源理由放回第 1 節判讀與限制之內，再接第 2 節保存逐股證據和第 3 節作者選填說明，與詳情外層的四步操作標題保持同一閱讀方向。沒有刪除、重算或變更任何 Advice／來源欄位。

- `tests/test_workbench_advice_contract.py`：**16 passed**；新增斷言固定 Advice 判讀與來源理由、逐股證據、作者說明的先後順序。
- 必要 Update UI：**99 passed**；Update validator：**25 passed／0 failed／4 skipped**，輸出於 `.pytest-owned-temp/ui_round59_update_validator_logs/`。
- `workbench_view.py` scoped mypy **0 issues**；本輪 2 個修改 Python 檔 `py_compile` 通過。Repo-wide mypy 仍被未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤阻斷。
- 本 QA 文件 document-control 通過（12 features／1 link source）；Application manual check 仍只回報既有兩個 `output/trial/` Junction 連結越界，與本輪內容無關。

## 2026-10-29 第六十輪：窄版 Advice 操作列換行

Advice 詳情的完整判讀／機率依據、原始結果／每日來源，以及註記／下次檢視／重新讀取都固定使用水平列；390 px 窄窗可能讓固定寬度按鈕搶占內容空間。現在窄於 560 logical px 時前兩組導覽入口改垂直排列，後續操作改為兩欄；主要研究決定仍維持同列，桌面寬度保留單列緊湊操作。操作行為與保存契約未改。

- `tests/test_workbench_advice_contract.py`：**16 passed**；增加 390／1280 px 下入口方向及後續按鈕網格位置檢查。必要 Update UI：**99 passed**；Update validator：**25 passed／0 failed／4 skipped**，輸出於 `.pytest-owned-temp/ui_round60_update_validator_logs/`。
- `workbench_view.py` scoped mypy **0 issues**；本輪 2 個修改 Python 檔 `py_compile` 通過，`git diff --check` 通過。Repo-wide mypy 在掃描既有 `output/qa/.../origins` 路徑時遇到 `WinError 3`，未進入全域型別檢查。
- 操作手冊已補窄版操作列規則。新 QA／手冊 scoped document-control 未列本輪新錯誤；手冊檢查仍被兩個既有 `output/trial/` junction 的 `WinError 5` 阻擋。畫面 QA 為 offscreen，不等同 Owner 原生 GUI UAT。
- 本輪只調整 Advice 操作入口排列，不改操作行為、保存契約或資料／金融邏輯；也不代表 Advice 來源已核驗或 Gate 1 已接受。

## 2026-10-29 第六十一輪：F17／月營收來源與查詢流程分層

F17 月營收研究頁將多個完整來源路徑及六個滿版按鈕列在候選清單前，查詢後還要越過完整篩選群組才看到結果，造成來源設定、來源清單、條件和結果閱讀互相打斷。現在把必要來源路徑收在可展開設定面板（缺欄位時預設展開），清單更新／續頁入口放在清單旁；成功套用查詢後收起條件面板，保留「修改全母體查詢條件」入口和原值。只改顯示分組，不改核驗、查詢、金融或保存契約。

- 新增來源設定初始展開、收合／重開不清條件、成功查詢後收合的 focused Qt cases：**2 passed**。必要 Update UI **99 passed**；Update validator **25 passed／0 failed／4 skipped**。原完整 F17 保存／讀回 UI 流程在 sandbox 執行超過 9 分鐘無輸出後中止，結果為 `not_run`，不列通過；需另排除測試環境／整合流程停滯。
- `daily_market_technical_official_disposition_revenue_view.py` scoped mypy **0 issues**；兩個修改 Python 檔 `py_compile`、`git diff --check` 通過。Repo-wide mypy 在掃描既有 `output/qa/.../origins` 路徑時遇到 `WinError 3`，未進入全域型別檢查。QA 文件 document-control **12 features／1 link source／0 errors**；操作手冊檢查被 9 個既有 `output/trial/` junction 引用的 `WinError 5` 阻擋。
- 修改檔 `daily_market_technical_official_disposition_revenue_view.py` 與操作手冊已同步；offscreen 版面測試不等同 Windows 原生 GUI／Owner UAT。來源內容、月營收資料與可用資格未因版面收合而改變。

## 2026-10-29 第六十二輪：研究時間軸窄版查找與清單分區

研究時間軸的搜尋欄固定橫排，紀錄清單與詳情固定左右分割；窄窗時 result ID 搜尋入口及長文詳情容易被擠窄。現在窄於 760 logical px 時來源篩選與股票／result ID 搜尋改為兩列；窄於 900 時清單與詳情改上下分割；窄於 600 時詳情延伸操作也改為上下排列。放大後恢復桌面排列。版面切換保留正在輸入的搜尋內容、來源選取與紀錄狀態，不改 Journal 搜尋或保存語義。

- `tests/test_ui_qt_research_timeline_view.py`：**18 passed**；新增 390／1280 px 版面斷言，包含搜尋欄位置、splitter 方向、詳情操作排列及 result ID 輸入跨尺寸保留。Advice→Research Timeline exact result ID MainWindow 跨頁旅程：**1 passed**。
- 必要 Update UI **99 passed**；Update validator **25 passed／0 failed／4 skipped**；修改兩個視圖 scoped mypy **0 issues**；修改 Python 檔 `py_compile` 與 `git diff --check` 通過。指定多模組 mypy 仍被未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻止。
- 操作手冊已同步窄版查找步驟。QA 文件 document-control **12 features／1 link source／0 errors**；Application manual check 仍被兩個既有 `output/trial/` junction 引用的 `WinError 5` 阻擋。Offscreen 版面與跨頁合成測試不等同原生 GUI／Owner UAT；本輪不更動 Journal、Advice、資料來源或金融邏輯。

## 2026-10-29 第五十一輪：工作區提交前定向回歸核對

提交前重跑目前 dirty UI 變更的部分相關測試。單一 Workbench 四欄桌面／窄版案例 **1 passed**；Decision Desk **55 passed**、Recommendation layout **16 passed**、Research Timeline **17 passed**、Runtime view **26 passed**。個人推薦選擇測試 **8 passed／1 failed**，失敗於 learning `runs` 目錄安全讀取（`runs_directory_unsafe_or_unreadable`），在系統 Temp 與 repo `.tmp_` basetemp 都可重現；個股研究報告測試 **29 passed／1 failed**，失敗案例啟動 MainWindow 時 ML registry 因測試輸出路徑存取錯誤未建立。兩者不是本輪新增的顯示斷言，但仍列為未通過，不能將整檔標示為 pass。

同一進程執行 Backtest 相關測試時，Qt WebEngine 在 `fast_chart_widget.py::_create_webengine_view` 以 Windows native exception `0x80000003` 中止，沒有 pytest 結果；故 Backtest 相關 dirty 測試未獲完整驗收。非 Backtest 的合併 pytest 在遇到長時間 GUI 測試後手動中止，也不列為整體通過。MOPS/data tests 不屬本輪 UI QA；本次結果只支持上述明確列出的定向測試。原生 GUI 與 Owner UAT 尚未執行。

補充受控 runner 結果：Workbench v5 guided + Advice contract changed tests **22 passed**（8 GiB／12-process Job，exit 0、process tree／handles 已關閉）；Backtest 四檔合組於 35.1 秒以 exit code `2147483651`（`0x80000003`）原生中止，stdout 無 pytest 報告，Job 峰值約 1.35 GiB 且程序樹正常關閉。此為測試環境原生中止，不足以定位產品錯誤；仍需拆開不初始化 WebEngine 的 presenter／純 view 測試。使用者手冊 document-control 對既有 `output/trial/` 冷封存連結因 output junction 權限拒絕而未通過路徑檢查；UI QA 文件自身 document-control 通過，不能把外部連結拒絕解讀為手冊內容驗證通過。

## 2026-10-29 第六十三輪：Runtime 排程狀態列色彩掃讀

Runtime 的營運排程清單原本每列都使用相同文字色，雖然上方分布摘要已按狀態著色，仍需逐字讀每一列才能找到需要注意、未知或來源未確認的工作。現在清單列沿用既有語意色：正常 teal、安全邊界資訊藍、需注意 amber、無法判定／來源未確認灰、未知狀態 amber。每列仍明示中文狀態，原始狀態碼和來源資訊保留於 Tooltip；未改排程讀取或狀態判定。

- `tests/test_ui_qt_runtime_view.py`：**26 passed**；新增逐狀態前景色斷言，涵蓋正常、安全邊界、需注意、無法判定、來源未確認及未知代碼。必要 Update UI：**102 passed**。
- Runtime source scoped mypy **1 file／0 issues**；source／test `py_compile` 通過。QA 文件 document-control **12 features／1 link source／0 errors**。修改檔 scoped `git diff --check` 通過；全工作樹 `git diff --check` 另回報未修改的使用者 dirty `app_module/update_service.py` 第 728–742 行有 trailing whitespace，未改動該檔。
- Update validator 未執行：受控 runner 啟動前回報可用實體記憶體低於規定 8 GiB 而拒絕建立子程序。repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇到既有語法錯誤，未能檢查其餘模組。
- 色彩只作為掃讀輔助，文字標籤仍是判讀依據，並沿用手冊已定義的 Runtime 共用狀態色。不等同原生 GUI／Owner UAT，也不證明資料來源或排程執行已核驗。

## 2026-10-29 分批提交前分組回歸核對

為確認工作區目前 Advice continuity、timeline 導覽與空結果版面修改，分組重跑：`test_cross_page_decision_journey_mainwindow.py` **5 passed**；Decision Continuity controller／controls 與 Research Timeline **34 passed**；Workbench Advice contract **16 passed**；每日技術母體 view 與 Recommendation layout **28 passed**；Workbench 單頁日常來源詳情位置 **7 passed**。每日母體測試在一般 sandbox 初跑因 `Path.resolve(strict=True)` 無法解析系統／repo Temp（`WinError 5`）失敗；在提升執行權限、指定 repo 隔離 Temp 後完整通過。合併成單一長進程的初次嘗試出現環境錯誤且無進一步輸出，已停止；上述分組結果才是本次採用的測試收據。

強制 Update UI suite **99 passed**；Update validator **25 passed／0 failed／4 skipped**，輸出導向 ignored `.pytest-owned-temp/ui_commit_update_validator_20261029/`，使用隔離 QA data root。六個修改 source 檔 scoped mypy **0 issues**，13 個修改 Python source／test `py_compile` 通過，`git diff --check` 通過。Repo-wide mypy 仍因未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤，在其他檔案檢查前停止。QA 文件自身 document-control 通過；兩本操作手冊檢查仍因 `output/trial/` junction 的 `WinError 5` 無法讀取既存冷封存連結，本輪沒有新增該等連結。原生 GUI／Owner UAT 未執行。

## 2026-10-29 第六十四輪：Backtest 設定區標題與收合入口併列

Backtest 設定欄最上方原以整列寬按鈕「收合左側設定」開頭，動作與設定內容標題分離，按鈕也搶占設定欄的水平空間。現在加入「回測設定」標題，將收合入口作為同列的次要 ghost 操作靠右放置；按鈕寬度依文字需求，設定表單仍在同一捲動面板，切換至結果頁及回到設定的行為不變。MainWindow 截圖另發現「閱讀順序」兩行提示被垂直拉到 242 px，將摘要往下推；現限制提示依文字高度呈現，讀回高度 51 px。沒有改回測、結果、資料或金融邏輯。

- `tests/test_ui_qt_backtest_layout.py::test_windowed_backtest_keeps_summary_scrollable_and_optional_lookups_exclusive`：**1 passed**；檢查設定標題、按鈕與標題列的父子關係、按鈕不再填滿設定欄、判讀提示採自然高度，以及結果摘要／明細的既有顯示行為。`tests/test_ui_qt_backtest_product_layout.py`：**11 passed**。
- 真實 MainWindow default／scale 1.0 offscreen 稽核：**19 子頁、passed、0 coverage gaps**；輸出 `.pytest-owned-temp/ui_audit_backtest_config_header_round64b/`。更新後畫面截圖核對設定標題列和判讀提示不再佔用不必要的整欄／整段高度。
- 必要 Update UI：**102 passed**；Update validator：**25 passed／0 failed／4 skipped**。Backtest source scoped mypy **0 issues**，修改 Python source／test `py_compile` 通過。
- Repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因既有語法錯誤停止。原生 GUI／Owner UAT 未做；本次不代表 Backtest 成功／失敗正式結果旅程或全程式 UI 盤點完成。
- Recommendation／Research Lab 操作手冊已同步設定標題與收合入口位置；document-control 仍回報 9 個既有 `output/trial/` Junction 外部連結越界，未將其記為通過。

## 2026-10-29 第六十五輪：Recommendation 收藏狀態從按鈕改為提示

統一選股頁的來源收藏尚未接通或尚未滿足條件時，先前仍以與主要操作同樣大小的停用按鈕呈現；這讓不能執行的狀態也佔用操作列位置，且容易被看成可按入口。現在只有來源收藏可用時才顯示「儲存篩選條件」按鈕；未接通與暫時不可收藏改顯示帶有既有語意色的小型狀態標籤和 Tooltip。原生收藏按鈕代理、來源資格門檻及保存流程不變。

- `tests/test_ui_qt_unified_screener_workspace.py -k unified_save_filter`：**2 passed**，覆蓋原生收藏流程仍可用、暫時不可用顯示 warning、未接通來源顯示 info、V4 disabled gate 不呼叫來源收藏。整個模組執行為 **25 passed／1 failed／2 errors**；3 個非本次收藏案例在系統 Temp 的 `Path.resolve(strict=True)` 遇 `WinError 5`，與新增斷言無關。必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**，報告 `.pytest-owned-temp/ui_round65_update_validator_logs/VALIDATION_REPORT.md`。
- Recommendation 真實 MainWindow default／compact、scale 1.5 offscreen 稽核：**92 子頁 visits、0 failures／0 coverage gaps**；檢視 `recommendation_entry.png`，標籤已無邊框、單行著色，沒有停用按鈕外觀或額外換行高度。輸出 `.pytest-owned-temp/ui_audit_recommendation_save_state_round65c/`；offscreen 畫面不等同原生 GUI／Owner UAT。
- 修改視圖 scoped mypy **1 source／0 issues**、source/test `py_compile` 通過；QA 文件 document-control **12 features／1 link source／0 errors**。repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因既有語法錯誤停止。操作手冊 document-control 仍受 9 個既有 `output/trial/` Junction 引用的 `WinError 5` 阻擋；本輪同步說明按鈕及狀態提示的視覺行為。
- Recommendation／Research Lab 操作手冊已同步說明「可操作才顯示按鈕，否則顯示原因提示」。
- 本輪是持續 UI 盤點的一項修正，不代表 Recommendation 全流程、來源資格、Gate 1 Owner UAT 或整體 UI 盤點完成；未改來源資料、Advice 或金融邏輯。

## 2026-10-29 第六十六輪：共用主題修正停用變體按鈕仍像可用操作

全域 QSS 先定義 `QPushButton:disabled` 的中性樣式，但後續 `[variant="primary"|"secondary"|...]` 規則覆蓋了它；Recommendation 空結果頁因此仍把「套用全域查詢」、「讀取原保存個股證據」等停用主動作畫成亮藍色。現在將 primary、secondary、success、warning、danger、ghost 六種變體的停用外觀統一覆寫為 surface／muted 文字／subtle border；啟用態、資格條件及操作流程不變。

- `tests/test_ui_qt_theme.py::test_disabled_primary_button_has_a_distinct_muted_state` 與 V4 action layout case：**2 passed**。必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**，報告 `.pytest-owned-temp/ui_round66_update_validator_logs/VALIDATION_REPORT.md`。
- Recommendation 真實 MainWindow scale 1.5 default offscreen 稽核：**46 子頁、0 failures／0 coverage gaps**，報告 `.pytest-owned-temp/ui_audit_recommendation_disabled_primary_round66/`。檢視最終樣式截圖 `.pytest-owned-temp/ui_audit_recommendation_disabled_primary_round66b/scale_1_5/geometry_processes/default/screenshots/scale_1_5/default/recommendation_entry.png`，所有停用變體顯示為中性灰、主色只保留給可用查詢按鈕。round66b 重跑在截圖生成後於 QA runner `_synthetic_view_data` cleanup 發生 Windows access violation（`faulthandler.log`）；該次 runner 不列為完整通過，採用前一完整稽核的幾何收據及最終截圖的視覺核對。
- 修改 Python source／test `py_compile` 通過；`qss.py` 與 Recommendation workspace scoped mypy **2 source／0 issues**。本輪追加的 `recommendation_view.py` scoped mypy **1 source／0 issues**；repo-wide mypy 仍由未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤阻斷。Round 66 QA 文件 document-control **passed（12 features／1 link source／0 errors）**；Recommendation 手冊重核受 9 個既有 `output/trial/` Junction 引用、APPLICATION_MANUAL 重核受 2 個既有 `output/trial/` Junction 引用的 `WinError 5` 阻擋。`tests/test_ui_qt_personal_recommendation_choice.py` 變更案例 **1 passed**。此輪只改跨工作區按鈕狀態視覺，不改流程、來源、資料、Advice 或金融邏輯，也不等同原生 GUI／Owner UAT。

## 2026-10-29 第六十七輪：Recommendation 來源詳情先給結論與下一步

逐筆來源詳情原先先列公司契約 hash、artifact hash與產業指數列定位，使用者需要讀完大量技術憑據才看到來源限制及建議動作。現在在同一份唯讀詳情最前方先列結果 ID、來源資格結論、時間／PIT 限制與下一步，再展開公司契約、產業觀察列、市場來源與原始警告；所有原值仍保留，來源判定、Advice 與資料不變。

- `tests/test_ui_qt_personal_recommendation_choice.py::test_company_source_display_uses_only_the_matching_sealed_event`：**1 passed**；明確檢查結論／下一步排在契約 hash 前，且原有身份、日期、PIT 限制、hash、收合詳情與身分錯配拒讀仍成立。該測試檔整檔：**22 passed／12 failed**；失敗案例落在 learning root／系統 Temp 權限、`os.replace` 與 hardlink `WinError 5`，不是來源顯示斷言，故不列整檔通過。
- 必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**，報告 `.pytest-owned-temp/ui_round67_update_validator_logs/VALIDATION_REPORT.md`。修改的 source／test `py_compile` 通過，`recommendation_view.py` scoped mypy **1 source／0 issues**，`git diff --check` 通過。
- QA 文件 document-control：**12 features／1 link source／0 errors**。推薦操作手冊覆核仍有 9 個既有 `output/trial/` junction 連結因 `WinError 5` 無法讀取；主操作手冊另有 2 個既有相同權限錯誤，本輪未新增或改動這些引用。受影響的文件檢查合計 **12 features／2 link sources**，錯誤只來自無法讀取的既有 junction 目標。
- 指定 repo-wide mypy 在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇既有語法錯誤後停止；其餘模組未檢查。原生 GUI／Owner UAT、Recommendation 真實保存來源旅程及整體 UI 盤點仍未完成。本輪不改來源資格、資料或金融邏輯。

## 2026-10-29 第六十七輪：Advice 研究決定與後續追蹤區隔

Workbench 的 Advice 詳情把「人工納入／略過決定」與註記、手動下次檢視、狀態讀回分成兩區，加入每個操作的唯讀／不建交易提示；校準來源入口改為「查看機率依據」，策略作者欄位明確說明需前往回測頁建立版本。無法核對 result／股票／決策日／來源 snapshot 時，現在顯示原因與重查指引，不再隱藏狀態。相關操作仍沿用既有服務與身分核驗。

- 最後一次合併執行 `tests/test_workbench_advice_contract.py`、`tests/test_ui_qt_workbench_candidate_selection.py`、`tests/test_ui_qt_workbench_home_single_page.py`：**54 passed**。背景讀回案例以有限事件輪詢等待結果；非有效保存 ID 的狀態斷言改核對外層入口列是否隱藏。`workbench_view.py` scoped mypy **1 source／0 issues**，修改的 Python source／test `py_compile` 通過，`git diff --check` 通過。
- Update UI **102 passed**、Update validator **25 passed／0 failed／4 skipped**；repo-wide mypy 仍由未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻斷。`APPLICATION_MANUAL.md` document-control 重核仍有 2 個既有 `output/trial/` Junction 連結因 `WinError 5` 無法讀取；UI QA 文件的 document-control 為 12 features／1 link source／0 errors。
- Update UI **102 passed**、Update validator **25 passed／0 failed／4 skipped**；repo-wide mypy 仍由未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻斷。`APPLICATION_MANUAL.md` document-control 仍有 2 個既有 `output/trial/` Junction 引用遇 `WinError 5`。

## 2026-10-29 第六十八輪：Advice 操作分組與每日候選入口連續性

Advice 詳情把「查看機率依據」、前往策略回測建立新版本、記錄人工納入／略過決定，以及註記／手動檢視／讀回拆成目的明確的區塊，並在操作旁說明唯讀及不建立交易；身份或來源不足時將停用原因直接顯示。每日候選摘要中的逐股預覽改為唯讀，唯一選股入口移到每日來源詳情旁，原保存結果回訪另列為次要入口，避免主操作被收合卡片藏住或同頁重複。另合併同一 Advice 身分的併發讀回，避免重複選取事件取消第一筆查詢後留下「背景讀取中」。只調整操作呈現及重複讀回控制，不更改保存契約、來源判定、Advice、篩選或金融邏輯。

- `tests/test_workbench_advice_contract.py`、`tests/test_ui_qt_workbench_candidate_selection.py`、`tests/test_ui_qt_workbench_home_single_page.py`：**54 passed**；必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**，報告 `.pytest-owned-temp/ui_round68_update_validator_logs/VALIDATION_REPORT.md`。修改的 source／test `py_compile` 通過，`workbench_view.py` 與 `recommendation_view.py` scoped mypy **2 source／0 issues**。
- QA 文件 document-control **12 features／1 link source／0 errors** 通過。主操作手冊的 document-control 因 2 個既有 `output/trial/` 冷封存 Junction 引用出現 `WinError 5`／越界錯誤，未新增這些引用；文件正文已同步本輪候選入口位置。repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇既有語法錯誤而停止。
- 原生 GUI／Owner UAT 尚未執行；自動化檢查不會證明資料來源已合格，也不代表全程式 UI 盤點已完成。使用者仍需按實際每日結果做一次 Owner UAT；跨 Recommendation、Portfolio、Backtest 等工作區的整體視覺盤點仍依本文件優先序繼續。

## 2026-10-29 第六十九輪：Recommendation 選用模式收合與狀態摘要

空結果截圖顯示結果表／理由區已改成單一精簡空狀態，但「個人推薦模式」仍將長設定表單直接接在主要推薦閱讀區下方，讓設定蓋過結果。現在設定預設收合，標題旁仍常駐顯示目前模式／版本；設定載入無法驗證或一次性規則模式已確認時也有明確狀態。展開後保留個人模式設定、候選來源、來源時間信任及歷史版本控制；收合不變更保存或推薦行為。窄版與空狀態的新截圖確認主要結果區旁只剩短摘要。截圖另發現個人決定按鈕及中寬讀回按鈕排列偏重，後續於第七十輪調整。

- `tests/test_ui_qt_recommendation_layout.py`＋`tests/test_ui_qt_personal_policy_history_layout.py`：**20 passed**，涵蓋預設收合／摘要／展開、設定歷史幾何與多視窗尺寸；Recommendation 結果頁截圖已檢視。必要 Update UI：**102 passed**；Update validator：**25 passed／0 failed／4 skipped**，隔離輸出於 `.pytest-owned-temp/round70_update_validator_logs/`。
- 擴大的 Recommendation 個人模式套件合跑 **43 passed／11 failed**。失敗落於 candidate inventory fixture、Windows sandbox 的 `os.replace`／hardlink 寫入與 learning-root／temp 目錄讀取；不屬本輪新布局斷言，因此只採用版面／歷史列幾何的獨立 **20 passed**，個人模式整合流程仍未完整驗收。
- `recommendation_view.py` scoped mypy **1 source／0 issues**；修改 source／tests `py_compile` 通過，目標檔 `git diff --check` 通過。Repo-wide mypy 遍歷既有 `output/qa/.../origins` Junction 時遇 `WinError 3`，未完成。QA 頁 document-control **12 features／1 link source／0 errors**；操作手冊檢查有 **9** 個既有 `output/trial/` Junction 連結因 `WinError 5` 無法讀取，正文修改未新增這些連結。
- Offscreen 幾何與截圖不等同 Windows 原生 GUI／Owner UAT。使用者提出的「決定紀錄後續可找回」也仍需由真人確認實際保存結果是否能從歷史頁面重新找到；Gate 1 資料來源及整體接受狀態均未因此改變。

## 2026-10-29 第七十輪：個人決定與保存讀回操作列降噪

空白或尚未核驗結果時，個人採用／拒絕／推翻三個按鈕原本仍以停用狀態顯示，占滿整列。現在只顯示身份或資料狀態說明；保存結果與股票完成核驗後才出現決定按鈕，讀回重試狀態只顯示「重試讀回」。Recommendation 保存來源選擇和讀回操作列也只在結果 pane 小於 560 logical px 時直排；560 px 以上同列呈現，讓來源欄位、讀回動作及後續 Workbench 入口維持在同一操作脈絡。沒有改變保存、個人決定、讀取或委託語義。

- Recommendation layout＋個人模式歷史幾何＋個人決定控制項 targeted cases：**22 passed**；完整 `tests/test_ui_qt_decision_continuity_controls.py`：**10 passed**。另確認 1366×768 空結果及保存讀回截圖；未核驗時按鈕消失，摘要／阻擋原因留在原位；讀回動作在一般桌面同列，在小於 560 px 時直排。
- 必要 Update UI：**102 passed**；Update validator：**25 passed／0 failed／4 skipped**。Recommendation source 與個人決定 widget scoped mypy、修改 Python 檔 `py_compile` 和目標檔 `git diff --check` 於本輪最終變更後重跑。
- Repo-wide mypy 仍被既有 `output/qa/.../origins` Junction `WinError 3` 阻止檔案列舉，未完成；個人模式整合測試的 11 個 sandbox fixture／檔案權限失敗仍未解。UI 截圖和 offscreen 幾何不等同原生 GUI／Owner UAT；尚須真人確認真正讀回個人決定後可由「研究紀錄與覆盤」找回。全程式 UI 盤點仍持續中。

## 2026-10-29 第七十一輪：Backtest 結果解讀提示移至績效卡之前

成功結果頁先顯示原績效卡，之後才顯示「淨報酬 → 最大回撤 → 交易筆數 → 成本與資料限制」閱讀順序，讓導讀落在數值之後。現把同一提示移到原總報酬／回撤／配對／成本卡之前；成功結果仍先讀提示、再看主要數字，詳細摘要與交易明細照原順序接續。失敗結果的「回測未完成」、原停止原因、不可保存狀態和空交易明細行為不變。

- `tests/test_ui_qt_backtest_product_layout.py`＋結果摘要／失敗結果 targeted cases：**13 passed**，包含導讀先於主要指標卡、原始績效來源卡不重複寫回摘要、失敗結果不可保存／匯出／升級及舊圖表清除。
- 使用正式主題與合成成功結果複核 1366×768 offscreen 畫面，閱讀順序提示在四張主要結果卡之前；未開來源假設或查找面板。來源假設展開、成功 run 真實保存／重讀及 Owner UAT 仍需分別確認。
- `backtest_product_layout.py` scoped mypy **1 source／0 issues**；修改 Python source／test `py_compile`、目標檔 `git diff --check` 通過。QA 文件 document-control **12 features／1 link source／0 errors**；`APPLICATION_MANUAL.md` 的兩個既有 `output/trial/` Junction 連結因 `WinError 5` 無法讀取。
- 必要 Update UI suite 本輪因受控 runner 預檢發現可用實體記憶體低於 8 GiB，在建立 QA 子程序前拒絕啟動，故本輪未重跑 Update UI／validator；沿用既有收據不列成本輪重驗。
- 本輪未改回測值、資料、費用或交易契約；本項僅完成結果提示與卡片次序整理，不代表 Backtest 成功／失敗完整旅程或整體 UI 盤點已完成。

## 2026-10-29 第七十二輪：Backtest 失敗狀態導讀

失敗結果頁原本沿用「淨報酬／最大回撤／交易筆數」成功結果導讀，即使本次沒有可判讀績效；worker 直接錯誤時，結果工作區也沒有同步更新頂端判讀提示。現在在報告失敗和 worker 錯誤兩條路徑都將導讀改為先看停止原因與錯誤訊息，並指出沒有可判讀／可保存績效、空明細不等於零交易。成功回報會明確復原績效閱讀順序。

- `tests/test_ui_qt_backtest_trade_diagnostics.py`＋`tests/test_ui_qt_backtest_product_layout.py`：**44 passed**；涵蓋失敗提示、worker error 提示、成功提示復原、原績效卡次序，以及失敗結果不可保存／匯出／升級。必要 `tests/test_ui_qt_update_view_workbench.py`：**102 passed**；Update validator：**25 passed／0 failed／4 skipped**。
- 修改 Python source／test 的 `py_compile` 與本輪目標檔 `git diff --check` 通過。全域 mypy 因未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 既有語法錯誤停止，其餘模組未檢查；document-control 核對 12 features／2 link sources，但主操作手冊內 2 個既有 `output/trial/` Junction 引用因 `WinError 5` 無法讀取，整體檢查未通過，QA review 本身未報結構錯誤。
- 這輪只修失敗狀態的閱讀提示，不改回測值、資料、交易或保存契約。真實保存 run 的全旅程、來源假設展開及原生 GUI／Owner UAT 仍未核驗；全程式 UI 盤點持續進行。

## 2026-10-29 第七十三輪：Recommendation 來源憑據分段呈現

Recommendation 的來源摘要已有資格狀態與下一步，但使用者展開完整來源後，公司名冊、日期、雜湊、產業指數列觀察、PIT／可得時間及原始提示仍連成一大段灰色文字，主要限制和追蹤憑據視覺層級相同；展開內容也重複摘要。現將封存來源詳情改為分段標題與逐欄項目；公司名冊、產業列觀察、市場來源與來源警告各自成段。上方摘要保留結論、限制與下一步，展開區只列結果 ID 和來源憑據，不重貼摘要。Browser 內捲動保留 420 px 上限；封存值先 HTML-escape 後再以唯讀富文字呈現，且保留可複製純文字。來源狀態、時間資格、雜湊核對及下一步判斷邏輯未改。

- `test_ui_qt_personal_recommendation_choice.py` 的來源呈現與 canonical save → exact reload：**2 passed**；涵蓋分段標題、逐項資料、封存 rowset／observed_at、unknown／PIT 限制、canonical 狀態、活頁資料改變後仍讀封存值，以及 HTML injection 以純文字呈現。
- Recommendation layout＋exact saved entry：**30 passed／1 deselected**。另直接跑 exact-entry 全檔時 **12 passed／1 failed**；失敗發生在空 canonical fixture 的 artifact publish，Windows 回報測試目錄 write permission error，尚未到 UI 呈現斷言。
- 必要 Update UI：**102 passed**；Update validator：**25 passed／0 failed／4 skipped**；Recommendation view scoped mypy、兩個修改 Python 檔 `py_compile` 與本輪目標檔 `git diff --check` 通過。全域 mypy仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的語法錯誤停止；document-control 檢查 12 features／6 link sources，主手冊與研究手冊內共 11 個既有 `output/trial/` Junction 引用遇 `WinError 5` 無法讀取，UI feature／QA review 結構未報錯。
- 此輪只調整來源憑據的顯示結構，不改來源或 Gate 判定。Gate 1 仍待完整 owner 真實日常流程／人工決定／Journal 對照與原生 GUI UAT；整體程式 UI 盤點仍未完成。

## 2026-10-29 第七十四輪：Advice 完整判讀改為分區閱讀

Advice 展開區雖有段落標題，畫面仍把身份、判讀、來源與作者欄位塞在同一塊純文字框，顏色和區塊邊界不足，使用者仍需逐行找限制。現在改用唯讀富文字卡片呈現身份、Advice 判讀、同筆逐股來源與作者選填說明；各區有明確色彩和邊界，內容值先 HTML-escape 後顯示，保留文字選取、固定高度與長文捲動。資訊內容、排序／校準、來源資格和研究動作不變。

- 新增呈現 helper 測試：色彩區塊數量、章節標題及惡意 HTML 字串 escaping；Advice contract 對原始文字、唯讀及捲動的既有測試仍需本輪完整執行。
- 本輪尚未完成 Python QA：前一輪受控 runner 曾因啟動前可用實體記憶體低於 8 GiB 拒絕啟動；本輪以 venv Python 與 `cmd.exe` 分別呼叫 owned runner，記憶體守衛後 Windows `CreateProcess` 均回報 `WinError 2`，pytest 子程序沒有啟動。修改檔 `py_compile`、必要 Update UI／validator、全域 mypy均為 **not_run**；不繞過 owned runner。Owner UAT 尚未完成。
- 此輪只改 Advice 詳情的視覺層級，不改資料與金融邏輯；全程式 UI 盤點仍進行中。

## 2026-10-29 第七十五輪：每日候選摘要移除重複範圍計數

工作台每日旅程的狀態列與候選指標卡都呈現候選數／狀態；候選說明又重複列出這兩項，並把要求／降級／缺漏計數與全市場分母放在主閱讀流。現將候選數與狀態集中在候選指標卡，狀態列只留整體狀態與日期；候選來源摘要保留來源 ID、候選資料日與品質；候選範圍計數與分母移至「查看每日來源詳情」的「候選來源與範圍」，原文仍可讀。當來源追蹤原文缺件，但候選來源 ID、日期或計數有值時，詳情入口仍可用。沒有改候選資格、來源或推薦邏輯。

- `test_workbench_advice_contract.py` 的 Advice→每日來源詳情案例增加主摘要精簡、來源欄位保留、完整範圍計數與未知全市場分母斷言；尚未執行。
- 本輪受控驗證仍遇 Windows owned child `CreateProcess` `WinError 2`，pytest／py_compile／mypy／Update UI 與 validator 均 **not_run**；不使用未受控程序。目標檔 `git diff --check`：**PASS**；Owner UAT 未完成。
- 本輪只重排來源欄位的可見層級，未改來源、日期或金融邏輯；全程式 UI 盤點仍在進行中。

## 2026-10-29 第七十六輪：每日來源詳情增加分區導讀

每日來源詳情雖有章節標題，仍以單一同色純文字顯示；本次結果、候選來源範圍、篩選與排除、證據成熟度需要逐行掃讀。現在將這四段轉成共用唯讀卡片，標題以 accent 標出，「篩選與排除」用警示色提醒核對；來源原文全部先 escape，仍可在外層頁面捲動，不增設內層文字捲軸。Advice 詳情與每日來源詳情共用同一 HTML-safe 卡片 renderer。資料文字、篩選／排除判定與來源資格不變。

- 新增每日詳情 helper 測試，核對四個章節的視覺區塊、警示分區及 `<script>` 來源值 escaping；每日旅程整合測試加入 rich-text renderer 接線斷言。尚未執行。
- 受控 runner 在 sandbox 與 `require_escalated` 嘗試均於 Windows `CreateProcess` 回報 `WinError 2`，測試子程序未啟動。pytest、py_compile、mypy、Update UI／validator 均 **not_run**；不更換受控程序。目標檔 `git diff --check`：**PASS**。Owner 原生 GUI UAT 尚未完成。
- 本輪只改顯示結構與文字安全呈現，不改來源、資料或金融邏輯；全程式 UI 盤點仍在進行中。

## 2026-10-29 第七十七輪：研究紀錄詳情主次分層與主旅程回歸

研究時間軸選取紀錄後，原文與資料比較、Paper 條件、後續旅程原本同時佔據右側詳情；現在把延伸核對合併到「延伸核對與後續結果」收合區，預設先讀保存原文。Workbench 每日來源卡片維持摘要欄與詳情欄分工；事件雜湊和成熟樣本仍在進階追蹤，篩選排除及範圍計數留在一般來源詳情。僅改資訊層級，未改資料來源、資格、建議或金融邏輯。

- Research Timeline **18 passed**；Workbench Advice contract＋每日旅程 **22 passed**；建議／決定 controls＋Recommendation layout 合併回歸中其餘 **49 passed**，首輪唯一 UI 失敗是每日來源測試仍期待舊摘要文案，調整斷言到新分層後，Advice contract＋每日旅程重跑 **22 passed**。
- 必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**（日誌導向 ignored `.pytest-owned-temp/update_tab_logs/`）；14 個目前 dirty 的 Python source/test `py_compile` 通過；`research_timeline_view.py` targeted mypy **0 issues**。Repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇到既有語法錯誤，後續模組未檢查。
- 五檔較廣回歸 **70 passed／14 failed**；12 個個人推薦案例在 sandbox tmp 的讀取、原子替換或 hard-link 寫入受限，未到 UI 斷言；兩個每日旅程文案失敗已修正並聚焦重跑通過。個人模式寫入整合仍需可安全寫入的受控測試目錄驗證。
- `git diff --check` 目標檔通過。原生 GUI／Owner UAT、canonical 保存決定從 Advice 到完整歷史回找的實際操作，以及全工作區內容易讀性仍未完成；本輪不構成 Gate 1 接受。

## 2026-10-29 第七十八輪：共用收合分區標題與操作層級

Workbench、Decision Desk、Unified Screener、Strategy Library、Research Chart、comparison audit 與 Backtest period disclosure 共用同一收合面板。原標題以膠囊式背景與外框顯示，展開按鈕另外佔一塊視覺焦點；現在標題是一般段落標題層級，展開／收合使用無外框的行內文字、方向箭頭與相符的可存取動作名稱，收合內容仍依原始狀態與按鈕觸發切換。面板內文、預設展開狀態和來源／執行契約都未更動。

- 共用元件及 6 個代表工作區測例：**11 passed**，涵蓋可收合狀態、方向提示、呼叫端自訂無障礙名稱、比較稽核與選股工作區的窄控件不裁切行為及 controls／details 行為。
- 必要 Update UI：**102 passed**；Update validator：**25 passed／0 failed／4 skipped**；共用 widget 與新測試 `py_compile` 通過；`theme_widgets.py` targeted mypy **0 issues**。
- Repo-wide mypy 仍停在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤，後續模組未檢查；`git diff --check` 目標檔通過。原生 GUI／Owner UAT 及不同 DPI／窄寬頁面實際閱讀仍未驗；本輪僅為跨頁共用元件的受控 offscreen 覆蓋，不代表全程式 UI 盤點完成。

## 2026-10-29 第七十九輪：每日來源入口可辨識度與重載狀態

使用者指出「查看每日來源詳情」不知道從哪裡進入，且操作控件比資訊更搶眼。入口現改為「展開來源／範圍／排除」文字箭頭，放在候選來源摘要正下方的「來源核對」列；展開時箭頭朝下、文案提供收合動作，無障礙名稱與提示說明本次結果、候選範圍、篩選及排除。重新載入每日旅程時會一併重設可見詳情與入口狀態。來源內容、唯讀行為及資格判斷不變。

- 新增 UI 契約斷言：入口型別、文案、arrow、AutoRaise、詳情展開／收合及重載後重設。WorkBench home／daily journey／Advice contract **29 passed**；必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**；修改 Python 檔 `py_compile` 通過；`workbench_view.py` targeted mypy **0 issues**；目標檔 `git diff --check` 通過（Git 僅回報既有 fsmonitor IPC 與 CRLF 行尾警告）。Repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤停止。
- Owner 原生 GUI UAT 未執行；此輪不構成 Gate 1 接受，也不代表全工作區 UI 盤點完成。

## 2026-10-29 第八十輪：Advice 精確歷史回查強制讀取最新 Journal

重看「推薦更新後仍可找回舊研究決定」主旅程時發現，Advice 的 result ID 入口只有在研究時間軸已讀取上限 500 筆時才查完整 Journal；未達上限則直接篩選記憶體清單，可能漏掉時間軸載入後才保存的新決定。現在由 Advice 導航的精確 result ID 查找一律重新讀取 Journal，並先將來源篩選切至「研究決定」。跨頁整合測例移除手動刷新步驟，確認使用者入口自身就會重讀並找回保存決定。資料保存、決定狀態與來源資格均不變。

- `tests/test_ui_qt_research_timeline_view.py`：**19 passed**；新增未達 500 筆且精確結果在舊清單不存在時，回查後重新讀取並找回紀錄的案例。
- 隔離 MainWindow 跨頁決策旅程：**1 passed**；測試不再代替入口呼叫 timeline.refresh，確認從 Workbench Advice 導航時已重讀 Journal。首次跨頁嘗試失敗，追查後發現舊測例額外重啟 refresh 與新自動回查競態；移除重複刷新後重跑 **1 passed**。
- 必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**；目前 dirty UI source/test 編譯通過；`research_timeline_view.py` targeted mypy **0 issues**。Repo-wide mypy 仍被未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 既有語法錯誤阻擋。UI feature／QA review 的 document-control **12 features／2 link sources／0 errors**；納入 Manual 與 Snapshot 的檢查受既有 `output/` Junction `WinError 5` 拒讀而失敗，未修改外部引用或產物。目標檔 `git diff --check` 無 whitespace error（Git 回報 fsmonitor IPC 與 CRLF 行尾警告）。Owner 正式環境 UAT 仍待完成，這些隔離測試不代表 Gate 1 接受或全程式 UI 盤點完成。

## 2026-10-29 第八十一輪：今日策略建議常駐研究歷史位置

使用者擔心今日 Advice 換股後，已保存的研究決定會消失或無法找到。除了逐筆 Advice 的精確查找，Workbench「今日策略建議」標題下現在常駐一行導覽提示：歷史決定不隨今日候選更新，可在「我的投資 → 研究紀錄與覆盤」按股票代號或 result ID 找回。使用靜態文字而非增加操作按鈕，避免再加一個需要判斷的控制。資料保存、Journal 與 Advice 行為不變。

- Workbench home＋Advice contract **26 passed**；必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**；Workbench／Research Timeline 修改 source 及相關測試 `py_compile` 通過，兩個 view targeted mypy **0 issues**。Repo-wide mypy 仍在未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤停止。
- UI feature／QA review 的 document-control **12 features／2 link sources／0 errors**；Manual／Snapshot 合併檢查因既有 `output/` Junction `WinError 5` 拒讀而失敗，錯誤指向原有外部 trial/task 引用；沒有移除或改寫它們。`git diff --check` 無 whitespace error（Git 僅提示 fsmonitor IPC 與 LF→CRLF）。這只改善歷史位置發現性；原生 Owner UAT 與全工作區 UI 盤點尚未完成。

## 2026-10-29 第八十二輪：推薦結果先顯示狀態再顯示操作

推薦結果區原本先列「保存推薦結果／加入觀察清單／查看個股研究」等操作，再顯示當前狀態摘要。使用者需要先掃過操作按鈕才能知道現在是尚未分析、讀取保存結果或分析完成；這讓操作區打斷了狀態與結果的閱讀順序。現在調整為「標題 → 狀態與判讀摘要 → 保存／研究操作 → 結果表與逐股詳情」，並以左側 accent 線標出摘要層級。逐股來源摘要另把「來源判讀／時間判讀／建議下一步」做文字層級標示，注意色標出需核對處；完整雜湊仍在展開來源欄位。操作及狀態文字、保存行為和推薦計算不變。

- `tests/test_ui_qt_recommendation_layout.py`：**18 passed**；`tests/test_ui_qt_personal_recommendation_choice.py -k company_source_display_uses_only_the_matching_sealed_event`：**1 passed**，涵蓋摘要層級、語意標籤、HTML escaping 與原來源憑據完整性；必要 Update UI：**102 passed**；Update validator：**25 passed／0 failed／4 skipped**；修改 Python source／test `py_compile` 通過；`recommendation_view.py` scoped mypy **0 issues**。Repo-wide mypy 仍由未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤停止；`git diff --check` 無 whitespace error（Git 回報既有 fsmonitor IPC／CRLF 行尾警告）。
- 原生 GUI／Owner UAT 與可核驗正式保存來源流程仍待完成；本次只調整閱讀順序，不代表 Recommendation 情境或全程式 UI 盤點完成。

## 2026-10-29 第八十三輪：保存來源讀取狀態使用語意色彩

保存來源／單筆結果讀取會連續經過等待、完成、限制與錯誤狀態，但狀態列先前不分顏色，使用者需要細讀長句才能分辨是否核驗成功。現在這些流程以資訊藍、成功綠、注意黃、失敗紫紅作左側色條與底色，並保留狀態原文，避免只靠顏色辨識。沒有改來源核驗、保存、讀取結果或資格判定。

- Recommendation layout／state color **19 passed**；canonical 單筆讀回成功、拒絕缺件／舊格式／身份不符／損毀及來源摘要 **6 passed**；必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**；修改 source/test `py_compile` 通過；`recommendation_view.py` targeted mypy **0 issues**。Repo-wide mypy 仍因未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 既有語法錯誤停止；`git diff --check` 無 whitespace errors（Git fsmonitor IPC／CRLF 警告仍存在）。
- 原生 GUI／Owner UAT 與可核驗正式保存來源流程仍待完成；本輪不是 Recommendation 全流程驗收，也不代表全程式 UI 盤點完成。

## 2026-10-29 第八十四輪：條件捷徑查詢狀態緊貼操作並跟隨結果

綜合選股的條件範本按鈕和「尚未查詢」提示曾分居捷徑列與漏斗明細之間；而範本查詢後提示沒有從「尚未查詢」更新，可能把舊結果誤認為新條件結果。現在將提示移到捷徑正下方，條件說明只保留「技術規則替換、來源與其他條件保留」；選取範本後依來源頁實際旗標／背景工作狀態改顯示尚未查詢、查詢中、完成或失敗／取消，並用資訊藍、成功綠、錯誤紫紅標示。失敗時明示舊表格仍保留。沒有改查詢條件、執行時機、資料來源或資格邏輯。

- 條件捷徑流程契約測試 **1 passed**，核對尚未查詢 → 查詢中 → 失敗 → 完成狀態，並由 `refresh_funnel()` 輪詢整合路徑更新完成提示；來源掛載與導覽 **2 passed**。
- 統一選股完整 UI 檔在 sandbox pytest temp 中回歸 **25 passed／1 failed／2 errors**；三個未通過均為 `tmp_path.resolve(strict=True)` 的 `WinError 5`（workspace basetemp 亦相同），不是 UI 斷言。明確排除這三個只依賴該受限 temp path 的案例後重跑 **25 passed／3 deselected**；條件流程與來源導覽另有定向 **3 passed**。必要 Update UI **102 passed**、validator **25 passed／0 failed／4 skipped**；修改 Python 檔 `py_compile` 與 `unified_screener_workspace.py` targeted mypy **0 issues**。Repo-wide mypy 仍由未修改 T164 bridge 第 411 行語法錯誤停止；文件同步後 `git diff --check` 通過。
- 原生 Owner UAT 及可核驗來源的真實查詢仍待完成；本輪只改善狀態呈現，不代表整個選股成功旅程或全桌面 UI 盤點已通過。

## 2026-10-29 第八十五輪：Backtest 成功／失敗導讀的狀態色階

Backtest 結果頁已把閱讀順序放在主要績效卡之前，也會在本次錯誤時改寫成停止原因導讀；但導讀始終是低對比純文字，成功與失敗的視覺層級沒有分開。現在以同一個左側色條摘要區承載文字：正常結果用資訊藍，未完成結果用錯誤紫紅，並在成功結果回來時復原正常導讀。文字、指標、保存資格、來源及回測金融邏輯不變。

- `tests/test_ui_qt_backtest_trade_diagnostics.py`：**33 passed**，包含成功恢復資訊色、報告錯誤／worker 錯誤兩條路徑顯示錯誤色。
- `tests/test_ui_qt_backtest_layout.py::test_windowed_backtest_keeps_summary_scrollable_and_optional_lookups_exclusive`：**1 passed**，核對摘要導讀仍依內容高度、不擠壓版面。
- 該 layout 檔全套執行在 `fast_chart_widget.py::_create_webengine_view` 遇 Windows Qt WebEngine native exception `0x80000003` 中止，沒有 pytest 報告；未把整檔記為通過。修改檔 `py_compile` 通過，`result_panel.py`／`backtest_view.py` scoped mypy **0 issues**，必要 Update UI **102 passed**、Update validator **25 passed／0 failed／4 skipped**。Repo-wide mypy 仍由未修改 T164 bridge 第 411 行語法錯誤停止。
- 手冊已補充導讀區色彩語意。真實保存 run 的摘要／來源假設／查找全流程與 Owner UAT 仍待；本輪不代表 Backtest 全旅程或全程式 UI 盤點已完成。

## 2026-10-29 第八十六輪：Runtime 任務流程狀態語意色

Runtime 左側「任務狀態機」此前只有粗體狀態文字，和右側排程清單、治理健康摘要的狀態色不一致。現在依已觀測到的原始狀態以資訊藍（閒置／派送中／思考中／驗證中）、teal（已核准）、amber（恢復中）、orchid（錯誤／停止）呈現；未知狀態或讀取未確認用 amber 提醒核對。Tooltip 保留讀取狀態、原始狀態碼及診斷，沒有改任務狀態判讀或排程行為。

- `tests/test_ui_qt_runtime_view.py`：**27 passed**，涵蓋狀態色切換及讀取未確認；修改 source/test `py_compile` 通過，`runtime_view.py` scoped mypy **0 issues**。必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**。Repo-wide mypy 仍因未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤停止。
- 手冊已同步此狀態色與其限制。Runtime 原生 GUI／Owner UAT、其他狀態資料旅程及整體程式 UI 盤點仍未完成；此輪不等同使用者驗收或 Gate 通過。

## 2026-10-29 第八十七輪：Advice 保存／讀回動作的即時回應

Gate 1 使用者曾回報按下「記錄已納入研究」像沒有反應，之後才從確認文字發現已成功保存。原因是 Workbench 的研究決定 callback 同步執行，狀態列只在保存／讀回結束後更新。現在呼叫 callback 前先顯示並立即重繪「正在保存研究動作並核對同一筆」或「正在重新讀取同筆人工研究狀態」；完成後仍以既有精確讀回結果為準，不把處理中當成功，也不改 Journal／保存契約。

- Workbench Advice contract、每日旅程、MainWindow 跨頁決策回查：**27 passed**；測試確認 save callback 執行時狀態已先顯示處理中。必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**；修改 source/test `py_compile` 通過，`workbench_view.py` scoped mypy **0 issues**。Repo-wide mypy 仍因未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 既有語法錯誤停止；目標檔 `git diff --check` 無 whitespace error（Git fsmonitor IPC 警告仍在）。
- 操作手冊已同步處理中提示與成功判讀。此為同步 callback 的可見進度回饋；Gate 1 canonical Owner 原生 GUI UAT 和全程式 UI 盤點仍未完成。

## 2026-10-29 第八十八輪：Recommendation 保存結果回看步驟導讀

Recommendation「回看已保存結果」的來源選擇／來源讀取在第一列，而選取結果讀回在第二列；桌面上這兩個步驟只靠按鈕文字相鄰，沒有說明其先後關係。現在兩列之間顯示一行短導讀：先讀可用來源、再選取並讀回；今日排程結果則可直接查看。沒有增加按鈕，也不改來源清單、結果身份、讀取或推薦執行行為。

- Recommendation layout：**19 passed**，包含導讀在來源列與讀取列之間、存在於 1366×768／897×360／390×844 控制檢查中的 assertion；1366×768 offscreen 截圖 `.pytest-owned-temp/recommendation_step_hint/recommendation_saved_result_actions.png` 確認可視提示位於兩列控制之間。修改 Python source/test `py_compile` 通過，`recommendation_view.py` scoped mypy **0 issues**。必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**。Repo-wide mypy 仍因未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤停止；目標檔 `git diff --check` 無 whitespace error（Git 回報既有 fsmonitor IPC／行尾轉換提示）。
- 操作手冊與 UI 功能說明已同步。此提示只驗合成視窗幾何，不代表 canonical 保存來源操作或 Owner 原生 GUI UAT 通過；全程式盤點持續中。
- 變更檔 document-control 結構核對讀到 **12 features／4 link sources**；檢查 Manual／QA／Feature 文件時，其餘錯誤都指向既有 `output/` Junction `WinError 5 Access is denied`，未修改或重寫這些外部引用。

## 2026-10-29 第八十九輪：推薦來源與理由分段閱讀

「推薦理由詳情」外層同時放來源摘要、來源憑據、分數理由與限制，兩個展開控制也分散在同一長區，標題沒有說明內容順序。現在改稱「所選股票判讀」，並以「來源與資料日期」及「推薦理由與限制」做明確分段；來源憑據按鈕緊貼來源標題，理由展開鍵在其內容旁。兩段各自控制自己的詳情，原來源摘要、憑據、理由及資格狀態均不改。

- `tests/test_ui_qt_recommendation_layout.py`：**20 passed**；本輪定向來源／理由區測例再執行 **1 passed**，1366×768 offscreen 截圖 `.pytest-owned-temp/recommendation_source_reason_sections/recommendation_selected_stock_reading.png` 確認兩段標題與各自展開控制同列且可辨。
- 封存來源摘要核驗 `test_company_source_display_uses_only_the_matching_sealed_event`：**1 passed／33 deselected**。合併執行個人推薦來源整合 suite 為 **42 passed／12 failed**；未通過皆由 sandbox pytest temp `WinError 5` 造成目錄不可讀寫或 create-only hard link 失敗，與本次版面無關。必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**；py_compile 通過；`recommendation_view.py` scoped mypy **0 issues**。Repo-wide mypy 仍停在未修改 T164 bridge 第 411 行既有語法錯誤；`git diff --check` 無 whitespace errors（Git fsmonitor IPC／CRLF 行尾提示仍存在）。
- 手冊、UI feature contract 與 Snapshot 已同步。UI feature／QA `document_control check` 均通過（12 features／1 link source）；手冊與 Snapshot 檢查只因既有 `output/` Junction 回 `WinError 5 Access is denied` 而列出舊 trial/task 引用錯誤，沒有改寫這些路徑。Offscreen 幾何及合成來源核驗不代表原生 GUI／Owner UAT。
- 此輪解決推薦詳情內部的來源／理由混讀，不代表 Recommendation 全流程、Owner UAT 或全程式 UI 盤點完成。

## 2026-10-29 第九十輪：個股摘要卡把章節導覽降為次要動作

個股研究有內容時，摘要下的營收／法人／信用／集保卡各有一顆橫跨卡寬的「查看章節」按鈕，四顆同樣醒目的按鈕占用資訊區視覺權重。現在保留原卡片與精確章節跳轉，但改成卡片右側自然寬度的「查看 →」文字鍵，並維持完整無障礙名稱與 tooltip；使用者先讀原值、資料日與狀態，再選擇是否下鑽。未改資料計算、來源或資格。

- `tests/test_ui_qt_stock_research_product_summary.py` 與已載入報告首頁導覽案例：**9 passed**；原價格標籤回歸斷言同步修正為分別讀收盤價大字與漲跌／行情日標籤，符合目前畫面契約。資料日、原值、未知漲跌、四類摘要來源與多來源不混合均有覆蓋；直達按鈕型別、自然寬度、無障礙名稱與點擊後章節 index 也已核對。
- 1280×760 合成完整研究報告 offscreen 畫面 `.pytest-owned-temp/stock_research_populated_review/populated_stock_research.png` 已檢視：摘要先呈原值／資料日／狀態，四張卡的短「查看 →」靠右，不再各佔一整排按鈕視覺。必要 Update UI **102 passed**；Update validator **25 passed／0 failed／4 skipped**；py_compile 通過；`stock_research_report_view.py` scoped mypy **0 issues**。Repo-wide mypy 仍停在未修改 T164 bridge 第 411 行既有語法錯誤。
- 手冊與 UI feature contract 已同步；feature／QA `document_control check` 通過（12 features／1 link source）。Portfolio manual check 指向既有 `../../../output/trial/Baldr-Theme-Research-03/TRIAL_GUIDE.md` 越界；Snapshot check 受既有 `output/` Junction `WinError 5 Access is denied` 拒讀外部 trial/task 引用，均未改寫這些路徑。原生 GUI／Owner UAT 與其他工作區盤點仍未完成。

## 2026-10-29 第九十一輪：Portfolio 摘要不再重列持倉名單

有持倉時，首屏摘要結論與下方狀態卡已顯示持倉數／投入額，活躍持倉條與表格也列股票名稱；摘要理由和證據又複述持倉名稱、數量，讓同一資訊連續出現。現在保留估值日期限制、健康來源狀態與操作下一步，把持倉名稱留給下方名單／原表、從證據行移除重複筆數。帳本數值、健康判讀、損益或來源沒有變動。

- Portfolio populated fixture offscreen screenshot `.pytest-owned-temp/portfolio_populated_review/portfolio_populated.png` verified the final, non-repeating summary. `tests/test_ui_qt_portfolio_view.py` active summary＋dedup **2 passed**; py_compile passed; `portfolio_view.py` scoped mypy **0 issues**; required Update UI **102 passed**, validator **25 passed／0 failed／4 skipped**. Repo-wide mypy remains blocked at the unrelated, unmodified T164 bridge line 411 syntax error. UI feature／QA document-control passed (12 features／1 link source); Portfolio manual check reports the pre-existing `../../../output/trial/Baldr-Theme-Research-03/TRIAL_GUIDE.md` escape, and Snapshot references are unreadable through the existing `output/` Junction (`WinError 5`). `git diff --check` had no whitespace errors; Git emitted existing fsmonitor IPC／CRLF notices.
