# 產業題材頁探索與卡片優先呈現（2026-10-28）

## 現況與比較範圍

Baldr 產業與題材頁原已提供五張完整覆蓋觀察卡、題材漲跌格、成交金額面積圖、題材排行、產業鏈卡片目錄；選定題材後另有指標卡與明細、成員表、分類階層、共用成員鄰域、版本並列比較及來源限制。這些內容呈現已載入的本機研究快照，不是全市場即時總覽。

DannyQuant 公開題材總覽可見今日盤勢摘要、法人買賣排行、熱門題材成交金額卡及產業鏈目錄；輪動頁另有期間選擇、題材資金流向與共用持股連線。參考頁面：[題材總覽](https://www.dannyquant.com/industry-map/themes)、[板塊輪動](https://www.dannyquant.com/industry-map/rotation)。其公開呈現會隨頁面更新；本文件不比較延遲、會員資料或各自資料資格。

本次檢查沒有發現 Baldr 缺少圖卡或數據視覺化。較明確的體驗差距是原本要先滑過漲跌格、面積圖、排行及目錄，才看到主要題材篩選／搜尋、個股反查及選定題材明細。

## 變更

在保留原觀察卡緊接快照摘要的位置後，將題材／產業鏈選擇、題材名稱搜尋、股票反查、所選題材摘要、分類／重疊探索及指標／成員明細移到完整圖表之前。將排行預設呈現為可操作的題材卡，九項指標預設呈現指標卡，成員預設呈現可選取的股票卡；完整排行與成員表仍能切換，九項指標原表可展開。卡片保留原值、成員覆蓋、分類依據與來源提示，成員選取後沿用既有「研究選取股票」入口。視窗變寬時依比例擴大指標欄，卡片欄數隨寬度重排。

漲跌格、成交金額面積圖、產業鏈目錄、雙版本比較及來源限制仍可沿頁面下段使用。這次只改 Qt 呈現與操作手冊；未改 DTO、欄位、來源、計算、缺值或快照身份規則，未新增綜合題材分數，也未將本機快照描述成 DannyQuant 的全市場當日總覽。

## 驗證

| 項目 | 結果 |
|---|---|
| `tests/test_ui_qt_industry_theme_map_view.py -q -o addopts=`（含區塊順序、卡片預設、成員卡片選取與排行卡片定位回歸） | passed：61 |
| 專案指定 Workbench UI：`tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | passed：97 |
| `scripts/qa_validate_update_tab.py`，隔離日誌目錄 | passed：25、failed：0、skipped：4 |
| `mypy ui_qt/views/industry_theme_map_view.py` | passed |
| 修改 Python 檔 `py_compile` | passed |
| 專案指定 repo-wide mypy | failed：既有 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻止後續檢查；該檔未修改 |
| 原生 GUI／Owner UAT | not_run |

UI 與更新驗證均由既有 Windows owned-process Job runner 執行，Job 限制讀回 8 GiB committed memory／12 個程序，結束時程序自然退出、Job 關閉。原先 Update validator 嘗試寫入 `output/qa/update_tab/RUN_LOG.txt` 時，因 `output/qa` junction 在此沙箱不可寫而失敗；使用其 `BALDR_UPDATE_TAB_QA_LOG_DIR` 支援改到 `.pytest-owned-temp/theme_page_layout_20261028/update_tab_logs_card_ui` 後完成驗證。最終 UI 與 Update validator 輸出均保留於本機隔離目錄，未覆寫 repo 外正式資料或既有 QA 原件。

## 版本選擇清單增量

使用者反映版本區只有資料夾／manifest 挑選入口且無法判斷可選項。本增量在頁面內新增已驗證版本下拉、選取載入、刷新與版本庫位置標籤；只有切換非標準版本庫時才開資料夾選擇器。清單掃描在背景執行，列出 price-v1／flow-v2 的資料日、型別及身份摘要；載入選取版本時以預期manifest SHA重讀。沒有版本、候選拒絕、讀取失敗、清單受限及資料夾不存在都有不同提示。MainWindow 預設使用設定輸出根下的 `theme_research_snapshots`；該資料夾不存在時，開發版回退到已知的 `output/tasks/baldr-post-completion-execution/snapshots`，不搜尋其他任務目錄。

本機上述具名目錄可見兩份 manifest（2026-10-16 price-v1、2026-10-19 flow-v2）。`output` 是指向 `F:\Min\Python\Project\BaldrStorage\repo-output` 的junction，依既有reader契約先解析到實際儲存目標再核驗；不得把junction路徑直接當版本庫。以解析後的root呼叫 catalog API，結果為2個schema候選、1個已驗證可讀版本（2026-10-16 price-v1）；2026-10-19 flow-v2 因其 institutional artifacts 參照到caller明選版本庫之外而拒絕。頁面預期只呈現已驗證的10/16版本，並提示另有1個候選未通過驗證；停留在狀態文字可看manifest路徑與reader拒絕原因。這是reader現有路徑邊界的結果，不藉擴大root或放寬檢查納入外部依賴。

| 項目 | 結果 |
|---|---|
| 題材版本選擇、題材頁及入口 UI：`tests/test_ui_qt_theme_catalog_loading.py tests/test_ui_qt_industry_theme_map_view.py tests/test_industry_theme_main_navigation.py` | passed：79 |
| 修改檔 targeted mypy：catalog service、題材頁及 MainWindow | passed |
| 專案指定 Workbench UI：`tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | failed：21 passed／76 failed；失敗測試建立的 `_TestableUpdateView` 缺少 `_choose_monthly_revenue_snapshot`，來源 `ui_qt/views/update_view.py` 未由本增量修改 |
| `scripts/qa_validate_update_tab.py` | passed：25、failed：0、skipped：4 |
| repo-wide mypy | failed：未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤 |
| 修改 Python 檔 `py_compile` | passed |
| `tests/test_theme_snapshot_catalog.py` | passed：10、skipped：1；使用專案owned-process runner |
| 原生 GUI／Owner UAT | not_run |

受控命令輸出保留於 `.pytest-owned-temp/theme_catalog_picker_final4_20261028`、`theme_catalog_service_elevated_20261028`、`theme_catalog_real_versions_resolved_retry1_20261028`、`theme_catalog_picker_targeted_mypy_20261028` 及 `theme_catalog_picker_required_20261028`；owned runner Job 結束時程序與 handles 均關閉。Update validator 使用本機隔離日誌目錄。
