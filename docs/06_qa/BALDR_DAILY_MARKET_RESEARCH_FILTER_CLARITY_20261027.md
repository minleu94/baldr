# Daily Research 局部篩選摘要 QA

## 範圍與行為

每日研究條件頁的局部摘要現在列出畫面符合列數／完整核驗列總數，以及目前啟用的代號搜尋和狀態篩選。清除條件會還原清單。局部篩選只重繪已載入快照，不重讀來源、不改變原始來源分母或符合／不符合／未知計數。

## 驗證結果

- `tests/test_ux04_05_daily_market_research_view.py`：4 passed，涵蓋未套用、狀態、代號、零符合及清除後還原。
- 必要 Workbench UI regression：97 passed。
- `scripts/qa_validate_update_tab.py`：25 passed／0 failed／4 skipped；資料與輸出位於該驗證腳本建立的隔離暫存根。
- Daily Research、Strong Stocks、Stock Screener 與 Storage Overview 四個相關模組 targeted mypy：無錯誤。
- 本輪 8 個修改 Python 檔 `py_compile`：全部通過。
- 指定全域 mypy 未完成型別掃描：被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻擋。
- 新 QA／索引與 Feature Map 的 7-source scoped document-control check 通過。12-source 變更文件檢查另列出 4 個既有 PROJECT_SNAPSHOT 錨點缺件；預設 67-source task-wide check 有 63 個既有錨點／`output/` 越界問題，本輪新連結未列缺件。
- 受改檔案 `git diff --check` 通過；新 QA 文件未發現尾端空白。

主要 pytest receipt：`output/tasks/daily-market-research-filter-clarity-20261027/evidence/single_owned_qa_73f75048e3db4904998cdc448fcb7640/receipt.json`。共同驗證 receipts 亦保存在同一 task evidence；首次 DMR runner 的 console encoding 收尾失敗已保留原收據，第二次以 UTF-8 正常完成，子測試均為 4 passed。

## DannyQuant 參考比較

公開參考頁只用來校準資訊層級：DannyQuant 把每日名單、篩後列、資料完整度及解鎖列分開顯示，個股頁另標符合總數與目前列數；Baldr 本輪在每日研究摘要明示局部符合數／完整核驗分母與作用中的條件。逐列行情日的對照另見[強勢個股逐列行情日 QA](BALDR_STRONG_STOCKS_ROW_MARKET_DATE_20261027.md)。比較範圍與速度限制見[DannyQuant 公開頁面參考](BALDR_DANNYQUANT_REFERENCE_20261027.md)。

## 限制

未做原生 GUI／Owner UAT，未量正式資料端到端延遲。DannyQuant 公開頁的本次讀取沒有可重複的瀏覽器完成事件或會員負載，故不宣稱兩系統速度相當。

