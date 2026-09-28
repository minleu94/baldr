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

較早一輪 WP3 結果為 29 passed／3 failed，當時 pytest 的 TEMP parent 是 `C:\Users\archi\AppData\Local\Temp`，`tmp_path` 落在該 AppData TEMP 下；目前保留的歷史摘要沒有記錄更深的 pytest 子目錄。本 agent 在本輪故障歸因時，曾以 fresh repository basetemp 對同三個失敗 node 執行 archived HEAD 與有界 overlay 對照；每次記錄均為 3 passed。這些對照沒有保留獨立 stdout、receipt 或 hash，故只作 agent 診斷記錄，不列為 hash-backed QA 證據，也不足以單獨裁定根因。最終可核驗的本輪回歸證據是上述兩模組 32 passed 的 stdout 與 freeze receipt。

本次第一次重跑也曾使用過深的 repository basetemp（`output/qa/personal_daily_product_20261006/wp2_ui_industry_observation_20260928/pytest_wp3_first_failure`）。`test_candidate_inventory_uses_learning_shadow_resolver_not_product_output` 在測試 setup 建立深層 `FA_Data_Shadow/recommendation_learning/...` 時收到 `FileNotFoundError [WinError 3]`；該節點尚未呼叫 RecommendationView 的 observation 顯示邏輯。其後使用短路徑 `output/qa/wp3b28` 與 `output/qa/wt28` 合跑全模組，32 項全通過。另一次過長 basetemp 合跑超過兩分鐘無輸出，由 owner 中止，保留 exit 1 診斷；不計為完成測試結果。

## 限制

以上是 offscreen Qt 自動化，不是可見原生視窗點按或真人互動驗收。個人結果的採用選擇和 Watchlist identity 有真 service／persistence／readback 測試；自然成熟 outcome、正式排程與官方 PIT 資料可得時間不在本次驗收範圍。
