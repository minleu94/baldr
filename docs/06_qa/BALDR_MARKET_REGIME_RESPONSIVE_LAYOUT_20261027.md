# 市況總覽窄版響應式版面 QA

日期：2026-10-27
任務：`market-regime-responsive-layout-20261027`
範圍：調整大盤指數頁的市場結論層（Layer 1）與來源條件層（Layer 2）排版。視窗寬度低於 820 個 Qt logical px 時上下排列，Layer 1 在前；寬版維持左右 3:2。沒有改資料來源、條件文字、Regime 判斷、金融計算、Gate 或寫入行為。

## 驗收

- 舊版合成 offscreen 基線中，Layer 2 條件文字欄在 1280／720／560 px 分別為 388／57／36 px；條件狀態標籤最小寬度是 60 px，窄版因此無法清楚閱讀。
- 新版在 1280 px 維持水平 3:2，條件文字欄寬 388 px。
- 新版在 720 px 改為垂直 1:1，結論與條件卡寬 646 px、條件文字欄寬 562 px。
- 新版在 560 px 改為垂直 1:1；頁面 viewport 受垂直捲軸影響為 546 px，兩層寬 472 px、條件文字欄寬 388 px。條件列仍完整可讀，窄版改以頁面垂直捲動容納內容。
- 寬度 819／820 px 的轉換邊界、縮窄後回復寬版的方向與 3:2 stretch，以及條件文字、狀態和無障礙摘要不變，皆由聚焦測試檢查。

合成版面截圖與原始量測留在 ignored 任務證據目錄：`output/tasks/market-regime-responsive-layout-20261027/evidence/`。主要圖檔為 `after_1280x850.png`、`after_720x850.png`、`after_560x850.png`；前版量測在 `single_owned_qa_d6d31aeb83d14a159d8af12833f9575b/stdout.log`，新版量測在 `single_owned_qa_1cb478e0804d427493ce8d9560d4a278/stdout.log`。這些畫面使用合成 Regime DTO 與註冊後的繁中字型。

## 驗證結果

| 檢查 | 結果 |
|---|---|
| `pytest tests/test_ui_qt_market_regime_view.py -q -o addopts=` | 14 passed |
| 必要 Workbench UI：`pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | 97 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped |
| 定向 mypy：`ui_qt/views/market_regime_view.py` | Success，1 source file |
| 全域 mypy：`ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime` | 未完成；未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 既有語法錯誤使檢查提前停止 |
| 修改 Python 檔 `py_compile` | 通過，2 檔 |
| Scoped `git diff --check` | 通過；新 QA 報告也檢查 0 個尾端空白 |
| Scoped document control | 未通過；PROJECT_SNAPSHOT 有 4 個既有日期化錨點缺件，本次新增 QA 連結無缺件 |
| Task-wide document control | 未通過；12 個功能、62 個連結來源共 63 個既有連結／錨點問題，包括指向 ignored `output/` 的連結；本次新增 QA 連結不在錯誤清單 |
| Native Windows GUI／Owner UAT | 未執行 |

Python 驗證均由本任務 root-owned bounded QA runner 序列執行；Job 的 8 GiB 記憶體／12 程序限制讀回相符，各次結束時沒有剩餘程序。Danny Quant 網址僅作資料呈現清晰度參考；本 QA 沒有比較兩個產品的延遲，也不把 offscreen 截圖當成原生螢幕或使用者驗收。

## 文件同步

UI 功能說明與資料／市場研究操作手冊已補上窄版排列及閱讀順序；PROJECT_SNAPSHOT、產品 UX QA 索引與 `workspace:market_explore` 的 Feature Map 已連結本收據。現行架構、資料儲存與市場 Regime 契約未變。
