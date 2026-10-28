# Smart Money 主表範圍搜尋 QA（2026-10-27）

## 變更範圍

Smart Money 主表新增代號／名稱即時篩選，只檢查目前已載入的所選範圍列。符合數與品質摘要依搜尋後可見列更新；清除搜尋恢復該範圍。搜尋不呼叫服務、不載入額外股票、不改全市場 Summary Strip。若篩選隱藏目前選取列，清除選取及其右側明細，狀態明示被隱藏的股票。

空狀態明確區分尚未載入、成功但主表為空，以及非空範圍中零符合。搜尋框提供可存取名稱、說明與清除按鈕。這個介面也採用目前 [DannyQuant 個股研究頁](https://www.dannyquant.com/stock)公開呈現的「代號或名稱輸入」及符合／顯示數量線索；該參考只說明操作慣例，不代表已測 DannyQuant 內部效能或將 Baldr 搜尋擴至全市場。

## 驗證

2026-10-27 在 root-owned Windows Job（全 Job 記憶體上限 8 GiB、最多 12 個程序、kill-on-close，啟動前可用實體記憶體高於 8 GiB）依序執行：

- Smart Money view 與 async 測試：28 passed。
- 必要 Update Workbench UI regression：97 passed。
- Update validator：25 passed、0 failed、4 skipped。
- 修改檔 `py_compile`：通過。
- Smart Money view targeted mypy：1 source file，無問題。
- 指定 repository mypy：未通過；檢查在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇到既有語法錯誤 `Unexpected character after line continuation character`，因此無法完成後續全域檢查。
- `git diff --check`：通過。`document_control check` 未全通過，回報 Snapshot 內四個既有日期化 QA 錨點缺件；完整 task link scan 另列既有文件指向 ignored `output/` 的越界連結。本次搜尋 QA 報告與功能地圖新增連結沒有被列為缺件。
- 每個 root-owned Job 收尾時剩餘程序為 0，Job／程序 handle 已關閉，執行鎖已釋放。

聚焦回歸證據位於本機忽略目錄 `output/tasks/smart-money-scope-search-20261027/evidence/qa_run_20261027T145411Z/`；受控執行收據位於同 task 的 `single_owned_qa_005dd62d38a641ec8b34d69ffeb8a462/receipt.json`。完整任務狀態保留為 `verification`，全域 mypy 與既有廣域文件連結診斷尚未解除。沒有執行原生 MainWindow／Owner UAT；測試不證明正式資料下的實際搜尋延遲或視覺接受。

## 邊界

此次只改 UI、測試與文件；沒有改資料來源、正式資料、來源品質、策略／篩選資格、PIT、Gate 或 ML 狀態。沒有量測端到端載入或正式資料效能，因此不宣稱延遲改善。
