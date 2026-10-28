# 個股研究歷史持倉警示摘要轉換量 QA（2026-10-27）

## 範圍與變更

個股研究報告兩個 render 路徑都會呼叫 `_historical_portfolio_alert_summary()`。摘要只顯示第一筆符合條件的事件；本輪保留原篩選條件、來源順序、展示 builder 與輸出字串，只把 singleton event 傳給 builder，避免為不會顯示的後續事件建 row、detail、raw tooltip 與 outcome tooltip。

此修改不改資料查詢、事件 DTO、日期／來源資格或完整事件表。驗收測試需證明摘要完全相等，且 builder 只收到第一筆符合事件。

## 效能量測

`output/tasks/stock-research-alert-summary-20261027/evidence/benchmark_alert_summary.py` 以 2,000 筆合成警示事件比較原全量轉換與現行 helper，各暖身 3 次並交錯量 30 次；p50/p95 使用 nearest-rank，並比較摘要 SHA-256。這是展示轉換 helper 的合成微基準，只隔離 CPU／配置成本，不含 Qt render、事件查詢或正式資料。

結果：全量轉換 p50 26.93755 ms、p95 27.6163 ms；只轉換第一筆 p50 0.0235 ms、p95 0.0260 ms。摘要 SHA-256 兩組皆為 `23e26e72f8834767cd60d0278c4c8309869042f7a8dac29c93a84a7d3ce90b80`，p50 約快 1,146 倍。只可解讀為此合成事件數下的 helper CPU／配置成本；不能推論實際頁面或正式資料載入也快 1,146 倍。

## 驗證與限制

| 項目 | 狀態 | 結果／證據 |
|---|---|---|
| 個股研究 UI 聚焦測試 | passed | 82 passed；`output/tasks/stock-research-alert-summary-20261027/evidence/focused_stock_research_ui.log` |
| 必要 Workbench UI regression | passed | 97 passed；`output/tasks/stock-research-alert-summary-20261027/evidence/mandatory_ui_regression.log` |
| Update tab validator | passed | 25 passed，0 failed，4 skipped；`output/tasks/stock-research-alert-summary-20261027/evidence/update_tab_validator.log` |
| 變更檔 targeted mypy | passed | 1 source file，0 issues；`output/tasks/stock-research-alert-summary-20261027/evidence/changed_file_targeted_mypy.log` |
| Repo-wide mypy | failed | 未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` syntax error；未能進一步檢查；`output/tasks/stock-research-alert-summary-20261027/evidence/repository_mypy.log` |
| 變更 Python 編譯 | passed | 兩個變更 Python 檔通過；`output/tasks/stock-research-alert-summary-20261027/evidence/changed_python_compile.log` |
| Diff whitespace check | passed | 最終 scoped `git diff --check` 通過；`output/tasks/stock-research-alert-summary-20261027/evidence/final_diff_check.log` |
| Helper 合成微基準 | passed | 2,000 events、30 次量測、摘要 SHA 相同；細節見上表；`output/tasks/stock-research-alert-summary-20261027/evidence/alert_summary_microbenchmark.log` |
| Scoped document control | failed | 63 個既有錯誤、60 個文件來源：PROJECT_SNAPSHOT 四個日期錨點缺件，其餘 59 個是既有 ignored `output/` 連結；本輪新增連結未列缺件。`output/tasks/stock-research-alert-summary-20261027/evidence/final_document_control_check.log` |
| Native GUI／Owner UAT | not_run | 不在本輪自動化範圍 |
| 正式資料端到端延遲 | not_run | 未接觸正式 DB 或行情來源 |

全域 mypy 因未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤而提早中止。Scoped document_control 的 63 個問題都是工作樹中既有的 Snapshot 日期錨點及 ignored `output/` 連結；新 QA 索引與 Snapshot 連結沒有被列為缺件。局部測試或合成微基準不代表整個產品、真實資料載入或使用者端延遲 Gate 通過。

首輪聚焦執行曾因新增測試少填必填 `decision_date`、獨立微基準 import path 未設定而失敗；修正後又調整摘要預期值為直接以原全量 builder 基線組字。最終聚焦測試與微基準重跑通過。另有一次受控 QA 在啟動 child 前因可用記憶體低於 runner 的 8 GiB 保留門檻而未開始；後續滿足門檻後的正式 QA 自然完成、無殘留 Job process。
