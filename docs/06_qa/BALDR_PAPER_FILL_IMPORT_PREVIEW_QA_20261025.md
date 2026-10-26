# Paper 成交 CSV 無效預覽明細 QA（2026-10-25）

## 範圍

Gate 4 的 Paper 成交 CSV 匯入在驗證失敗時，現在會開啟可捲動的唯讀明細，顯示總列數、有效／無效列數、來源 SHA-256、依欄位錯誤分類的影響列，以及逐列行號與繁體中文錯因。無效預覽直接結束匯入流程；不會出現確認寫入提示，也不會建立或修改 Paper Trade Ledger。錯誤代碼仍保留在明細中供追查。

有效預覽仍沿用原有完整 hash-bound 預覽、二次明確確認與 append-only Paper Trade Ledger 路徑；本切片未改動匯入契約或金融計算。

## 驗證結果

- 無效 UI 預覽、有效二次確認匯入及 `PaperTradeImportService` 測試：9 passed。
- 無效 CSV fixture 含有效列與無效列，確認列數、欄位錯因、CSV 行號及「沒有寫入 Paper Ledger」提示；Ledger 檔案不存在。

## 限制

- 這只改善拒收資料的修正回饋，不會產生真實成交、執行證據、費用或 turnover。
- Gate 4 仍需真實 Paper fills、人工 review 與各項週報／基準／Stress evidence；完整 Portfolio UI regression、GUI 重啟及 Owner UAT 尚未完成。
