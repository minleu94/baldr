# Gate 1 策略 Advice 解鎖 QA

## 變更範圍

策略升格狀態、參數鎖定、揭露完整度及策略作者 Advice 契約，不再決定系統是否提供 Advice。`candidate`、未 `promoted`、欄位未核驗或作者說明缺漏的列仍進入 Advice；限制以 `why_not_reasons`／警告呈現。舊 `research_only` 呼叫參數與 `PROFESSIONAL_CANDIDATE` DTO 值保留相容，但不再把新產生的建議降成另一種「非正式／研究專用」產品。

Workbench 計數把未升格策略 Advice 納入 Advice 總數，另外標示未升格 Advice 列數；指定保存結果也明確標成 Advice。它沿用原決策日和資料日，不代表今日排程候選、來源已接受、具 PIT 資格或 Gate 已通過。

這次只改 Advice 輸出政策、分類及使用者可見說明；沒有改訊號、排名分數、排序、日期、回測、手動持倉計算或交易執行。

## 現在可解除的限制

- candidate／shadow／未 promoted 策略不再因生命週期狀態被 `NO_NEW_POSITION` 阻擋。
- 參數未鎖定、揭露不完整、作者契約缺漏或未核驗不再隱藏 Advice。
- Guided／Professional 不再區分「正式 Advice」與「研究專用 Advice」。Advice 是供使用者判斷與手動紀錄的系統建議；不連接真實帳戶，也不自動下單。
- 作者未提供的進場論點、失效條件、策略持有期間與檢視頻率仍明示未知，不由工程代填；這些缺漏不阻止 Advice。

## 仍保留的資料與安全限制

- 資料品質缺失、降級或未觀測時仍輸出 `RESEARCH` 並標記原因；不把缺值補成可用訊號。
- 來源身份、日期、result ID、cohort 或版本不符／缺漏時仍不混用資料，必要時回傳空 Advice 和診斷。
- 明確不可成交時仍輸出 `AVOID`；可成交性未知會保留未知，不會假裝已核驗。
- 未核驗來源、PIT、授權、資料覆蓋或 Gate 狀態仍不能標成已接受或已通過。這些正式資料資格需各自完成，不是 Owner 簽署策略作者欄位即可代替。
- 本次沒有新增真實券商帳戶、下單、個人化配置或投資績效承諾。

## 驗證結果

- Advice policy／composer／DTO／Workbench source／Advice UI／R016 聚焦 suite：**253 passed**。將 `tests/test_ui_qt_stock_research_report.py::test_mainwindow_injects_current_restated_ml_registry_read_provider` 排除後通過；完整執行中唯一失敗是範圍外的 ML registry 初始化測試（`MLResearchOutputBoundaryError`）。
- 必要 Workbench UI suite：**97 passed**。
- `scripts/qa_validate_update_tab.py`：**25 passed、0 failed、4 skipped**；其 log/report 導向隔離的可寫 QA 目錄。
- 修改 Python 檔 `py_compile`：通過。
- 指定全域 mypy：未通過，且在本次未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因語法錯誤停止檢查；因此不能聲稱全域型別檢查完成。
- 未驗正式資料端到端、原生 GUI 視覺驗收或 Owner UAT。此 QA 不代表 Gate 1 產品整體完成。
