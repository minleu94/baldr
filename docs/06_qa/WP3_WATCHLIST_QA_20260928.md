# WP3 Watchlist／跨頁旅程 QA（2026-09-28）

## 本次驗證

本次在 offscreen Qt 下合跑個人推薦 UI 與跨頁決策旅程測試。命令使用 repository ignored 的短 basetemp 與 TEMP/TMP，避免 Windows 對巢狀測試路徑的限制：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:TEMP='C:\Projects\PythonProjects\technical_analysis\output\qa\wt28'
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -m pytest tests/test_cross_page_decision_journey_mainwindow.py tests/test_ui_qt_personal_recommendation_choice.py -vv -o addopts= -p no:cacheprovider --basetemp output/qa/wp3b28 --tb=short
```

結果：32 passed in 37.57s，exit 0。完整 stdout 存於 `output/qa/personal_daily_product_20261006/wp2_ui_industry_observation_20260928/closeout_01/wp3_modules.log`；其 SHA-256 記在同目錄的 freeze receipt。

`test_exact_saved_result_load_then_selection_and_choice_roundtrip` 走真 canonical save、以新 View 輸入 exact result ID 單筆讀回、選取股票、寫入 Watchlist 並讀回。測試核對 Watchlist 的 `result_id`、股票代號、決策日與 sealed universe snapshot ID/hash；重複加入顯示未新增，原來源連結不變。相同保存身份下也讀回 adopt choice；outcome 狀態仍是 `not_requested`，因此本測試不表示自然成熟結果已接通。

同次 mandatory 檢查結果：

| 檢查 | 結果 |
|---|---|
| `tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | 84 passed in 2.59s，exit 0；pytest cache 寫入警告不影響結果 |
| `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped，exit 0；跳過實際下載與全量合併，輸出報告在 `output/qa/update_tab/VALIDATION_REPORT.md` |
| 全指定目錄 mypy | 734 source files，0 issues |
| changed Python `py_compile` | exit 0 |
| whitespace-aware `git diff --check` | exit 0 |

## 歷史 TEMP 診斷

較早一輪 WP3 結果為 29 passed／3 failed，當時 pytest 的 TEMP parent 是 `<USER_HOME>\AppData\Local\Temp`，`tmp_path` 落在該 AppData TEMP 下；目前保留的歷史摘要沒有記錄更深的 pytest 子目錄。本 agent 在本輪故障歸因時，曾以 fresh repository basetemp 對同三個失敗 node 執行 archived HEAD 與有界 overlay 對照；每次記錄均為 3 passed。這些對照沒有保留獨立 stdout、receipt 或 hash，故只作 agent 診斷記錄，不列為 hash-backed QA 證據，也不足以單獨裁定根因。最終可核驗的本輪回歸證據是上述兩模組 32 passed 的 stdout 與 freeze receipt。

本次第一次重跑也曾使用過深的 repository basetemp（`output/qa/personal_daily_product_20261006/wp2_ui_industry_observation_20260928/pytest_wp3_first_failure`）。`test_candidate_inventory_uses_learning_shadow_resolver_not_product_output` 在測試 setup 建立深層 `FA_Data_Shadow/recommendation_learning/...` 時收到 `FileNotFoundError [WinError 3]`；該節點尚未呼叫 RecommendationView 的 observation 顯示邏輯。其後使用短路徑 `output/qa/wp3b28` 與 `output/qa/wt28` 合跑全模組，32 項全通過。另一次過長 basetemp 合跑超過兩分鐘無輸出，由 owner 中止，保留 exit 1 診斷；不計為完成測試結果。

## 限制

以上是 offscreen Qt 自動化，不是可見原生視窗點按或真人互動驗收。個人結果的採用選擇和 Watchlist identity 有真 service／persistence／readback 測試；自然成熟 outcome、正式排程與官方 PIT 資料可得時間不在本次驗收範圍。

## 2026-09-28 Recommendation／Journal choice follow-up

本增量在 Journey 加入唯讀個人決定歷史表，保留採用、拒絕與推翻理由的同結果身份核對及時間順序；MainWindow 測試沿 RecommendationView 的 typed choice／Journal writer 做保存、讀回、跨頁顯示與冷啟動讀回。測試 producer 是明確隔離的 synthetic UI fixture；保存和讀回沿真實應用 caller。此證據不代表自然行情／自然 outcome、OS 桌面前景，亦不代表 WP3 全旅程已完成。

| 驗證 | 結果 |
|---|---|
| `tests/test_ui_qt_decision_outcome_journey.py -q -o addopts=` | 11 passed、1 skipped（scheduled result smoke 為 opt-in） |
| `tests/test_ui_qt_decision_continuity_controls.py -q -o addopts=` | 3 passed |
| `tests/test_ui_qt_personal_recommendation_choice.py -k exact_saved_result_load_then_selection_and_choice_roundtrip -q -o addopts= --tb=short` | 1 passed、28 deselected |
| `tests/test_cross_page_decision_journey_mainwindow.py::test_actual_mainwindow_cross_page_decision_journey_round_trip -q -o addopts= --tb=short` | 1 passed；同一 MainWindow 三態寫入、跨頁 readback 與冷啟動 Journey rows 相同 |
| `tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | 84 passed |
| `scripts/qa_validate_update_tab.py`（輸出導向新 TEMP，不覆寫既有報告） | 25 passed、0 failed、4 skipped |
| 當時三個 production source targeted mypy、changed Python `py_compile`、`git diff --check` | 均通過；同一早期共享工作樹的首次全指定目錄 mypy 有 28 個其他 owner dirty source 錯誤；最終凍結重跑已全過，見本文末「Freeze rerun」 |

個人選擇 Journey 的三個 focused passing 命令以上為當時實際執行結果；該次並發共享工作樹的跨頁完整檔案並未全綠。工作樹當時的完整命令為：

```powershell
python -m pytest tests/test_cross_page_decision_journey_mainwindow.py -q -o addopts= --tb=long
```

結果為 1 passed、3 failed。完整 trace 在 `<USER_HOME>\AppData\Local\Temp\wp3_cross_page_failures_64c3c68109e947cf9920ca633bafcf6d.log`（SHA-256 `86a4524aa472c52b7437eef3dbbfe6983d2808318e1a3837a21ac39c939471a9`）。三個單獨重跑的 current-test 與 HEAD-test-source-copy 完整 stdout 及 SHA-256：

| Failure node | Current test log（SHA-256） | HEAD test source copy log（SHA-256） |
|---|---|---|
| `test_actual_mainwindow_journey_fail_closed_for_missing_future_and_conflict` | `<USER_HOME>\AppData\Local\Temp\wp3_current_test_actual_mainwindow_journey_fail_closed_for_missing_future_and_conflict_88fc39dafb4344f3814a0c4c5e89a924.log` (`1dc7f7196a7ed881b099406d8c6153b4bf942021abe2f8e1a808fd5e7971c0ba`) | `<USER_HOME>\AppData\Local\Temp\wp3_headtest_test_actual_mainwindow_journey_fail_closed_for_missing_future_and_conflict_215e0308cb4d4ece9ddf43b6c149c754.log` (`39f07f73c010f72c73b12beCD6a329692c5552e2c03e1159d1663b3410c78ec4`) |
| `test_portfolio_exact_route_keeps_same_stock_positions_separate` | `<USER_HOME>\AppData\Local\Temp\wp3_current_test_portfolio_exact_route_keeps_same_stock_positions_separate_d06b3e9146fb44c8a5971d1ffabb264c.log` (`c2dfdf042ffd185db3dc2287eee5f2211aee7396962f926f7562b8560e8168f6`) | `<USER_HOME>\AppData\Local\Temp\wp3_headtest_test_portfolio_exact_route_keeps_same_stock_positions_separate_a2f1ae44b20e41698f487df451ca3f7a.log` (`68c7b57365941977571abc6f9bc6a3d7fda887a1a5e2872396d85080f7a97767`) |
| `test_portfolio_bilingual_saved_stock_alias_conflict_fails_closed` | `<USER_HOME>\AppData\Local\Temp\wp3_current_test_portfolio_bilingual_saved_stock_alias_conflict_fails_closed_ea91c7ef2e1b4df9b82ba1084e751259.log` (`bccd325899fbcc52844a12e590498903fc6813e65bdbbe635f0d61c0d2c45428`) | `<USER_HOME>\AppData\Local\Temp\wp3_headtest_test_portfolio_bilingual_saved_stock_alias_conflict_fails_closed_e7845e4dbaee4db98638d6810e0e7b12.log` (`057ab6db66f89bc8a2a65d28648c304fc1c03b79899a18d663127b0409eaee42`) |

Replacing only the test source with `git show HEAD:tests/test_cross_page_decision_journey_mainwindow.py` did not remove the three failures; this comparison alone was not a clean-source baseline. Root then independently extracted clean `HEAD fd76b4e8` via `git archive` to ignored `output/qa/wp3_head_baseline_fd76` and ran the same three nodes against that source with the same `.venv`: all three passed under both `PROFILE=test` (17.26s) and unset/prod profile (16.13s). Therefore the current shared-tree failures are regressions relative to clean HEAD. Root／owners must finish a frozen-source overlay isolation to locate the responsible change. No unrelated Portfolio/Outcome production code was changed to mask them.

在該次並發共享工作樹快照中，完整 MainWindow journey file 有以上三個 failure；WP2/WP4 source 未 freeze 前沒有把原因歸給任一 owner。該快照全目錄 mypy 的 28 個錯誤來自其他 owner 工作檔：WP2 `data_module/twse_industry_index_capture.py` 與 `app_module/update_service.py`，以及 WP4 `app_module/personalization_read_service.py`。這些早期結果已由本文末的凍結重跑補充，不是最終狀態。

## 2026-09-28 個人模型評估 UI follow-up

RecommendationView 的「個人模型評估（唯讀）」已接上 WP4 `PersonalizationReadService.read_personal_model_assessment(result_id, capture_path, personal_capture_root, daily_summary_path)`。Stage C 沒有可信的 result→summary 索引，所以 UI 要求明確選取 capture JSON 與 Stage C summary JSON，不搜尋目錄、不猜 latest。`result_id` 僅取自目前 canonical saved-result readback；換結果、重跑推薦或換任一檔案會清掉舊內容。背景 worker 以 generation、結果與路徑三重檢查丟棄晚到回呼；native worker cleanup 不會覆蓋 pending 或拒絕狀態。

真實 m11 RecommendationView caller 測試唯讀載入保存結果，再由 UI 檔案選取按鈕提供兩個現存 QA 檔案。它顯示 0 筆成熟／19 筆待觀察、null metrics 與 after-cost unavailable；冷啟動後沒有沿用路徑，需再次明確選檔。負控重算 forged summary 外層 payload hash、只改同一 result row 的 capture identity，UI 明確拒絕且不保留先前明細。m11 capture 與原 summary 前後 SHA-256 相同。這是現有 QA artifact 的真 caller/readback，不代表自然 outcome 成熟或 OS 桌面前景操作。

另外新增不依賴本機 `output/qa` 的 isolated UI boundary 測試，覆蓋 success/error 終態在 native worker cleanup 後仍可見、路徑變更清除舊明細，以及切換 result 時拒絕舊 worker 的晚到結果。Stub DTO/service 只驗證 Qt 顯示與競態邊界，不作為產品 source、自然 evidence 或 Stage C readback 證據。

| 驗證 | 結果 |
|---|---|
| `tests/test_ui_qt_personal_model_assessment.py` | 2 passed；包含本機真 m11 readback 與無 output/QA 依賴的 isolated UI boundary test |
| `tests/test_cross_page_decision_journey_mainwindow.py::test_actual_mainwindow_cross_page_decision_journey_round_trip` | 1 passed；同一 MainWindow 從保存結果、三態 Journal choice、Watchlist 同結果 Journey 到 Portfolio exact source route，再至 Workbench／cold Journey readback |
| m11 capture／Stage C summary 原始 bytes | 測試前後 SHA-256 未變 |

跨頁 Journey 測試沿用既有獨立 exact identity 覆蓋：`tests/test_ui_qt_personal_recommendation_choice.py::test_exact_saved_result_load_then_selection_and_choice_roundtrip` 驗證新 View 精確讀回後寫入並 fresh-read Watchlist result/date/source snapshot；`tests/test_cross_page_decision_journey_mainwindow.py::test_actual_mainwindow_cross_page_decision_journey_round_trip` 驗證 MainWindow Watchlist exact identity、Portfolio `source_id`／source summary checksum、same result Journey 與冷啟動；同檔 `test_portfolio_exact_route_keeps_same_stock_positions_separate` 驗證同股票不同結果持倉不被合併。本輪把第一個 MainWindow roundtrip 延伸為同一 saved result 經 Watchlist 開 Journey 並回到 Portfolio。Portfolio 測試中的隔離 trade 僅是研究來源記錄，並非模型 outcome 或實盤成交證據。

### 跨頁三失敗診斷補正

上方記錄的並發期間 `1 passed／3 failed`、trace、node logs 與 hashes 全數保留為歷史收據。Root 後續以 clean `HEAD fd76b4e8` archive 對三個失敗節點做乾淨 source baseline，`PROFILE=test` 與 unset/prod 各為 3 passed；UI-only overlay 與 WP4-only overlay 也各為 3 passed。另一次以當時完整 shared source 跑整檔為 4 passed／0 failed／35.03 秒。這些結果表示舊三失敗是並發開發期間的瞬時狀態，但 responsible cause 未證，不能歸因至任何單一 owner。此補正不刪除或改寫先前失敗收據；本次延伸後的同一 journey node 又以 1 passed 單獨重跑。

### 待驗項

- 全量 Watchlist／Portfolio／Journey suite 仍待整體獨立驗收；本輪跨頁檔案已在 freeze rerun 以 4 passed／0 failed 通過，但未涵蓋所有相關 suite。
- m11 summary 仍為 `insufficient_data`、pending 19／matured 0，after-cost unavailable；未驗證自然成熟 outcome、正式 D、官方 PIT、模型效果或採用政策。
- 上述測試是 offscreen Qt，不等於 native desktop 前景點按；synthetic MainWindow producer fixture 不得解讀成行情自然採用或成交損益。
- 本增量未修改 Stage C writer／producer、Portfolio／Outcome production code 或 WP2 source writer；Manual 新增操作、interpretation、source mismatch 與安全限制說明。

### Freeze rerun（2026-09-28）

下列結果是本次 WP3 freeze 前的最終驗證；上文「首次」並發狀態、初次 type-check 判讀及三失敗記錄仍保留作歷史收據，不代表本次最終狀態。

| 驗證 | 最終結果 |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_personal_model_assessment.py -q -o addopts= --basetemp=output/q` | 2 passed（本機 m11 真來源 caller + self-contained UI boundary） |
| `.\.venv\Scripts\python.exe -m pytest tests/test_cross_page_decision_journey_mainwindow.py -q -o addopts= --basetemp=output/qa/wp3_cross_page_final_20260928` | 4 passed in 40.09s |
| `.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_decision_outcome_journey.py tests/test_ui_qt_decision_continuity_controls.py tests/test_ui_qt_personal_recommendation_choice.py tests/test_ui_qt_personal_model_assessment.py -q -o addopts= --basetemp=output/q` | 45 passed、1 skipped；改用短 basetemp 後通過。先前深 basetemp 的 setup `FileNotFoundError` 不涉及產品 caller，保留為暫存路徑限制 |
| UI mandatory: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts= --basetemp=output/qa/wp3_update_workbench_20260928` | 84 passed in 2.48s |
| UI mandatory: isolated copy of `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped。為免覆寫先前 `output/qa/update_tab` 收據，僅在 ignored `output/qa/wp3_updateqa_isolated_20260928` 執行副本，副本只將 log/report 目的地改至隔離目錄，實際 imports 與驗證流程仍指向此 repository |
| UI mandatory: `.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime` | 735 source files，0 issues |
| changed WP3 Python files `py_compile`；`git diff --check` | 均通過；diff check 只有 Git 的 LF→CRLF 提示，沒有 whitespace error |

真實 m11 caller 依賴 ignored、非版本控制的 `output/qa` capture／summary receipts；沒有這些本機檔案的乾淨 checkout 會略過該來源 smoke。它不是 CI 唯一回歸證據：同檔的 self-contained Qt boundary 測試不依賴任何本機 QA output，涵蓋成功／錯誤 terminal label、native worker cleanup、換路徑清除舊內容、換 result 丟棄舊 callback。`output/qa` raw receipts 是可選的隔離來源驗收資料，不能當成 tracked fixture 或自然 outcome。
