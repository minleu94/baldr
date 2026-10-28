# 強勢個股背景載入與資料日 QA（2026-10-27）

## 變更範圍

強勢個股頁將篩選服務呼叫移至受管 `TaskWorker`。資料讀取與篩選在背景執行，Qt 表格模型只於 GUI 執行緒更新。請求 generation 在週期切換、切換共用研究來源或關閉頁面時失效，因此較早查詢的回應不會覆寫目前頁面。刷新期間若暫留前次成功結果，狀態列明示暫留筆數及其資料日；新週期沒有快取時顯示空狀態。錯誤仍清除舊表格並顯示 `Universe: unavailable`，避免舊排名被誤認為當前結果。

服務 DTO 的 `effective_date` 與掃描母體數隨成功結果及週期快取保存。成功、快取與刷新暫留狀態都呈現同一快照的資料日；切回日／週快取時同步恢復對應 `Universe` 及掃描範圍，避免沿用另一週期的母體數。來源未提供日期時明示「資料日未提供」，不以本機刷新時間替代。舊服務回傳格式仍可載入，但沒有 DTO 日期時會顯示缺日期。

## 驗證結果

| 檢查 | 結果 |
|---|---|
| `tests/test_ui_qt_weak_market_views.py -q -o addopts=` | 11 passed；涵蓋 worker thread 執行、GUI thread 更新、快取日期／母體數恢復及慢速舊週期結果淘汰 |
| `tests/test_shared_market_research_consumers.py tests/test_f2_f3_main_consumer_bridge.py -q -o addopts=` | 6 passed |
| 必要 UI 回歸 `tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | 97 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped |
| `mypy ui_qt/views/strong_stocks_view.py` | 通過，1 個來源檔無問題 |
| Repo-wide mypy | 未通過：未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 有語法錯誤，後續檢查未能繼續 |
| 修改 Python 檔 `py_compile` | 通過 |
| `git diff --check` | 通過 |
| Scoped document control（6 份文件） | 未通過：4 個既有 Snapshot 日期化錨點缺件；本輪新增 QA／手冊連結未列為錯誤 |
| Repo-wide document control | 未通過：63 個既有錯誤，含上列 4 個 Snapshot 錨點與 ignored `output/` 越界連結 |
| `document_control check --task .../task.json` | 任務結構、角色與必要 Coverage 無新增錯誤；整體仍回報相同 63 個 repository 文件連結問題 |

受控 QA runner 的命令輸出與收據位於 `output/tasks/strong-stocks-async-load-20261027/evidence/`。聚焦測試以 thread identity 驗證服務呼叫不在 GUI 執行緒，並確認模型更新在主 GUI 執行緒；這證明同步讀取不再佔用事件處理執行緒，但沒有量測正式資料上的完成時間或端到端延遲。Document control 的四個 scoped 錯誤都指向原有 Snapshot 日期化錨點；repository-wide 的 63 個錯誤另含 ignored `output/` 越界連結。本輪新增文件連結未列為錯誤，task 檢查沒有 Coverage 或結構錯誤。

## Danny Quant 參考觀察

使用者指定的 [Danny Quant 每日選股](https://www.dannyquant.com/signal-lottery-preview)公開頁面列出資料日、更新頻率及現價延遲提示；[產業地圖](https://www.dannyquant.com/industry-map)列出行情日期、更新時間、公司／產業範圍，以及「當日無成交、收盤沿用前筆」的資料說明。這些是可供 Baldr 後續資料清晰度比較的介面線索，不是對資料準確性、效能或策略表現的獨立驗證。此切片完成了 Baldr 的非阻塞載入與資料日保留；尚未補上行情更新時間／延遲提示，也沒有與 Danny Quant 做同環境速度基準。

## 限制與未驗事項

- 未執行原生 Windows GUI 手動走查或 Owner UAT。
- 未使用正式資料資料庫驗證實際查詢時間、更新頻率或資料正確性。
- 未完成瀏覽器與 Baldr 的可比性能測量；背景化不代表服務查詢本身變快。
- Repo-wide mypy 受上述未修改 T164 bridge 語法錯誤阻擋，不能記為通過。
- Scoped document control 有四個既有 Snapshot 錨點錯誤；repository-wide check 有 63 個既有文件問題。修復它們不屬於本次強勢股 UI 範圍。
