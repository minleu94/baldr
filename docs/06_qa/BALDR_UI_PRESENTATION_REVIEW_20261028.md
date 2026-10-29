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
| P2 | Research Timeline：本地搜尋呼叫 `_render_entries`，每列最多重建 4 個儲存格；完整 Journal 搜尋另有 250 ms debounce，顯示最多 500 筆。 | **搜尋設定與清單／詳情曾缺少可見分區標題，已補標題及控制分組；回歸 17 passed。** | 原生 GUI 尚待確認不同寬度下 splitter 可讀性；如實測 500 筆鍵入有明顯停頓，再 profile 後決定是否調整模型。回歸入口：`tests/test_ui_qt_research_timeline_view.py`。 |
| P2 | Smart Money：[`smart_money_flow_view.py`](../../ui_qt/views/smart_money/smart_money_flow_view.py) 摘要卡與控制列原本都使用水平捲動區。 | **已修正版面風險**：摘要卡按寬度排 4／2／1 欄；掃描控制按寬度排單列／雙列／三列；掃描動作與觀察清單在首列，週期／範圍／圖表和搜尋／列數／品質各自成組，移除這兩處水平捲動容器。 | 保留既有市場摘要母體、搜尋範圍、掃描與表格契約；原生 GUI 視覺仍待人工確認。回歸入口：`tests/test_ui_qt_smart_money_flow_view.py`、`tests/test_ui_qt_market_layout.py`。 |
| P2 | Recommendation 結果表：結果載入先前呼叫 `resizeColumnsToContents()`；長理由會參與整欄寬度估算。 | **已修摘要表欄寬風險**：摘要欄採穩定初始寬度、理由欄初始 260 px，欄寬可拖曳；完整理由由詳情與儲存格提示閱讀，擴展欄位維持原資料。推薦版面／保存讀回測試 16 passed。推薦投資組合結果測試在 Qt WebEngine 建立回測圖表時觸發 Windows fatal exception，該測試未完成。 | 原生 GUI 視覺與 Owner UAT 尚待人工驗收；回歸入口：`tests/test_ui_qt_recommendation_layout.py`、`tests/test_ui_qt_saved_recommendation_compact_layout.py`、`tests/test_ui_qt_recommendation_portfolio_results.py`。 |
| P2 | Backtest 診斷：[`analyst_diagnostics_widget.py`](../../ui_qt/views/backtest/analyst_diagnostics_widget.py#L271) 同步重建月度矩陣；`_MAX_MONTHLY_DISPLAY_MONTHS=1200` 是補齊日期缺口的跨度門檻，不是 1,200 個表格列。13 欄矩陣按年作列；連續門檻範圍最多約 100 年列，超過跨度時只列有觀測年份（`L94–95,303–335`）。 | **先前把 1,200 個月誤記為 1,200 個表格列，已依程式修正判讀。**目前可確認是同步重建；尚無證據顯示一般資料量造成可感知延遲。診斷頁本身在既有可捲動結果頁內，沒有必要因這個靜態估算再增加分頁或操作。 | 保留觀察；若 Owner 實際遇到長跨度載入停頓，再以對應 DTO/profile 量測後決定是否優化。回歸入口：`tests/test_ui_qt_research_lab_mode_driven_ui.py`。 |
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
