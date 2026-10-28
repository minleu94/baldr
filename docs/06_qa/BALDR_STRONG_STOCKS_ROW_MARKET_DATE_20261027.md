# 強勢個股逐列行情日 QA

## 範圍

強勢個股排名列保留該股票被選中的最新來源列日期 `行情日`。整體 `ScreeningResultDTO.effective_date` 繼續表示來源資料框的最新日期，不用它覆寫個股列日期。弱勢結果 schema 保持不變；不從日期推論停牌、無交易或補價狀態。

## 驗證結果

- `tests/test_stock_screener_provider.py` 與 `tests/test_ui_qt_weak_market_views.py`：22 passed。
- 必要 Workbench UI regression：97 passed。
- `scripts/qa_validate_update_tab.py`：25 passed／0 failed／4 skipped；腳本使用隔離暫存資料，下載及正式資料合併步驟依自身規則略過。
- 4 個相關產品模組 targeted mypy：`Success: no issues found in 4 source files`。
- 8 個本輪修改的 Python 程式／測試檔 `py_compile`：全部通過。
- 指定全域 mypy 未完成型別掃描：被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻擋。
- 新 QA／索引與 Feature Map 的 7-source scoped document-control check 通過。預設 67-source task-wide check 有 63 個既有錨點／`output/` 越界問題；本輪新連結未列缺件。
- 受改檔案 `git diff --check` 通過；新 QA 文件未發現尾端空白。

程式與合成來源證據：`output/tasks/strong-stocks-per-row-market-date-20261027/evidence/source-date-contract.md`；pytest receipt：`output/tasks/strong-stocks-per-row-market-date-20261027/evidence/single_owned_qa_3bd49e10d2da4787a4d8563e1932083e/receipt.json`。共同 UI、validator、mypy 與 compile receipts 保存在 Daily Research 任務證據目錄，並由此輪整合 QA 索引列示。

## 判讀界線

合成案例中 2330 的最新列日期為 2026-10-25、2317 為 2026-10-26，而 DTO 整體日期為 2026-10-26；UI 對缺少或空白的列日期顯示「未提供」。本次未讀寫正式資料，未做原生 GUI／Owner UAT，也未量正式資料端到端載入延遲。日期顯示不是交易日期資格或缺件推論。

