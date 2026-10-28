# 個股研究月營收原值表漸進展開 QA（2026-10-27）

## 範圍

基本面／營收頁在月營收柱圖逐列對應全部原表列時，將重複原值表預設收合，並提供可鍵盤操作的展開鈕。原表仍保留完整原值、期間、可得時間及逐列提示中的資料日、品質與來源。

收合條件採保守判定：目前頁面必須有且只有一張成功建立的月營收柱圖，且圖表期間／原值與將顯示的每一原表列完全相符。來源分組不唯一、部分列無法畫圖、重複期間歧義或圖卡建立失敗時，原表直接顯示。只變更呈現密度，不改 DTO、數值、資料查詢、來源資格或金融判讀。

## 驗證

| 檢查 | 結果 | 證據 |
|---|---|---|
| 個股研究報告、視覺整合與圖表回歸 | 通過，105 passed | `output/tasks/stock-monthly-revenue-table-disclosure-20261027-01/evidence/single_owned_qa_d32c9d493a534209904c6315a6e3d53c/stdout.log` |
| 必要 Update UI 回歸 | 通過，97 passed | 同上受控 QA 收據 |
| Update Tab validator | 通過，25 passed／0 failed／4 skipped | `output/tasks/stock-monthly-revenue-table-disclosure-20261027-01/evidence/update_tab_validator/VALIDATION_REPORT.md` |
| 修改 view targeted mypy | 通過，1 file | `output/tasks/stock-monthly-revenue-table-disclosure-20261027-01/evidence/single_owned_qa_b20f45e2b1e0413a80455357be849ec8/stdout.log` |
| 全應用 mypy | 未通過；未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 有既有語法錯誤，阻止進一步檢查 | `output/tasks/stock-monthly-revenue-table-disclosure-20261027-01/evidence/single_owned_qa_d32c9d493a534209904c6315a6e3d53c/stdout.log` |
| 修改檔案 `py_compile` | 通過 | 同上受控 QA 收據 |
| `git diff --check` | 通過 | 同上受控 QA 收據 |
| `document_control check --task` | 未通過；回報既有 Snapshot 歷史錨點及多筆外接 `output` junction 路徑診斷，未指向本次新增 QA 報告或產品文件 | `output/tasks/stock-monthly-revenue-table-disclosure-20261027-01/evidence/single_owned_qa_b20f45e2b1e0413a80455357be849ec8/stdout.log` |

尚未進行原生 GUI／Owner UAT；本 QA 不驗證正式月營收來源或產品 Gate 資格。全應用 mypy 及既有文件診斷保留原狀，未擴大修改範圍處理。
