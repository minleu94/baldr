# Portfolio 交易歷史背景載入 QA（2026-10-27）

## 變更範圍

MainWindow 的 Portfolio 持倉刷新已在背景取得 `PortfolioDTO`，但套用 DTO 後原本仍會在 GUI 執行緒同步呼叫 `PortfolioService.list_trades()`、過濾目前股票並建立交易歷史 DataFrame。本次把自動刷新及股票篩選使用的交易讀取與 DataFrame 投影移入 `TaskWorker`；`PandasTableModel`、`QTableView` 及欄寬調整仍在 GUI 執行緒。

每次讀取記錄目前股票篩選與 request generation。快速換選持倉時，較早結果不會覆寫新篩選；更換篩選會先清除舊股票交易列。同篩選刷新可暫留前次列，狀態明示筆數；讀取中暫停交易表選取與刪除。失敗時，同篩選的前次資料會保留並標示刷新失敗；新篩選沒有可信結果時維持空表並顯示失敗原因。關閉時以合作式方式取消 worker。刪除最後一筆目前篩選股票交易的判斷改用已顯示的篩選結果，避免為此在 GUI 執行緒再次完整讀取交易帳本。

交易來源、過濾欄位、排序、DTO、表格欄位、刪除／匯入寫入契約均未改。同步呼叫模式仍保留給既有嵌入端及測試。

## 驗證結果

| 檢查 | 結果 |
|---|---|
| `tests/test_ui_qt_portfolio_view.py -q -o addopts=` | 110 passed；含背景 thread、GUI timer 響應、快速換選與舊回覆淘汰 |
| 必要 UI 回歸 `tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | 97 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped |
| `mypy ui_qt/views/portfolio_view.py` | 通過，1 個來源檔無問題 |
| Repo-wide mypy | 未通過：未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 有語法錯誤，後續檢查未能繼續 |
| 修改 Python 檔 `py_compile` | 通過 |
| `git diff --check` | 通過；Git 另提示其他既有 dirty 檔案有 CRLF 正規化警告 |
| Scoped document control（6 份文件） | 未通過：5 個既有問題，含 4 個 Snapshot 日期化錨點及手冊既有的 ignored `output/` 越界連結；本輪新增連結未列為錯誤 |
| Repo-wide document control | 未通過：63 個既有文件連結問題 |
| `document_control check --task .../task.json` | 任務結構、角色與 Coverage 無錯誤；整體仍回報相同 63 個 repository 文件問題 |

背景測試以阻塞的假 `list_trades()` 驗證 GUI timer 在讀取期間仍能執行，並記錄服務 thread ID 不等於 GUI thread；第二個股票篩選的結果套用後，較早讀取完成也不能替換它。受控 QA 命令輸出與 Job 收據位於 `output/tasks/portfolio-trade-history-async-20261027/evidence/`。Document control 的 5 個 scoped 問題都是原有的日期錨點或越界 `output/` 引用；repo-wide 共 63 項，本輪新增 QA／手冊連結未列為錯誤，task 結構及 Coverage 通過。

## 限制與未驗事項

- 沒有用正式交易資料或大量歷史紀錄量測讀取、模型套用及 click-to-idle 延遲；測試證明執行緒隔離及事件迴圈可回應，不代表來源讀取本身變快。
- `resizeColumnsToContents()`、Qt model 套用與表格繪製仍在 GUI thread；極大量交易下的欄寬／渲染時間尚未驗證。
- CSV 交易匯入預覽仍沿既有同步 `list_trades()` 路徑；本次聚焦在頁面自動刷新和股票篩選。
- Scoped document control 回報四個既有 Snapshot 日期錨點及一個手冊既有 `output/` 越界引用；repo-wide 有 63 個既有問題，本輪新增連結未造成缺件。
- 未執行原生 Windows GUI 手動走查或 Owner UAT。
- Repo-wide mypy 受上述未修改 T164 bridge 語法錯誤阻擋，不能記為通過。
