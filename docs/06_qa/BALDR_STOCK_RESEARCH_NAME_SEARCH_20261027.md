# 個股研究代號／名稱搜尋

## 範圍

在個股研究搜尋欄輸入代號或公司名稱片段。名稱以目前 `companies.csv` 為唯讀名錄，唯一結果由使用者確認後轉成代號載入；多筆與無結果說明候選或可行的修正方式。搜尋不讀行情表、不改報告服務；最終載入仍走既有來源身份守衛。名稱是目前名錄名稱，不作歷史 PIT 身份。

此工作與 [DannyQuant 公開頁面參考](BALDR_DANNYQUANT_REFERENCE_20261027.md)的個股研究名稱搜尋線索對照。DannyQuant 公開頁可見代號／名稱搜尋輸入，但公開擷取沒有可重複的結果完成事件；因此不宣稱其搜尋或頁面速度數字。

## 驗證

- `tests/test_ui_qt_stock_research_report.py`：89 passed；涵蓋唯一名稱確認／取消、同代號別名去重、同名候選、無結果提示、代號直載、代號與名稱片段重疊時優先直載、題材來源身份拒絕名稱切股，以及欄位提示、無障礙名稱與 64 字元輸入上限。收據：`output/tasks/stock-research-name-search-20261027/evidence/single_owned_qa_918da67644c3477fb1f6872037da9f32/receipt.json`。
- 必要 Workbench／Update UI 回歸：97 passed。Update validator：25 passed、0 failed、4 skipped。`stock_research_report_view.py` 與 `smart_money_semantic_service.py` targeted mypy 通過；4 個變更 Python 檔 `py_compile` 通過。受控結果：`output/tasks/stock-research-name-search-20261027/evidence/required_ui_qa_results.json`。
- Repo-wide mypy 未通過：被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤中止，與本次變更無關；同一收據保留完整命令及結果。
- Scoped `document_control check --task` 加七個變更文件路徑通過。無 `--path` 的全量文件檢查仍回報其他既有 Snapshot 錨點及 `output/` 越界連結；錯誤不在本次修改文件。

## 限制

這是 Qt offscreen／合成 `companies.csv` 回歸，未走原生 GUI／Owner UAT，也未量測正式名錄讀取、完整報告載入或外部網站端到端延遲。搜尋只證明目前名錄名稱能協助找到股票；不授予歷史身份或來源資格。
