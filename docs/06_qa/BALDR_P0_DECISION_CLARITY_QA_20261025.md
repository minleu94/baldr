# Baldr P0 來源決策清晰度 QA（2026-10-25）

## 範圍

本次修正 P0 來源候選已記錄 `deferred`、`rejected`、`disabled` 等決策時，介面仍要求 Owner 再提供一次決議的誤導；並在 Update 與 Research Console 顯示選取來源的決策及剩餘阻擋原因。

目前列選取後的唯讀明細會分開呈現來源決策、Machine／License／PIT 狀態、下游資格、阻擋原因與下一步。已記錄的 `deferred` 等決策不再要求重複輸入 Owner 決定；Machine verified 仍明確不等於來源接受。此變更不新增來源接受、不改資料庫、不授予下游資格，也不解除 License、PIT 或資料品質證據要求。

## 驗證結果

- 聚焦 P0／Readiness／Workbench／Research Console 測試：193 passed。
- Data Update Tab validator：25 passed、0 failed、4 skipped。
- 全域 mypy：1,145 個來源檔，無錯誤。
- 13 個修改中的 Python 程式與測試檔 `py_compile` 通過。
- `git diff --check` 通過；`FEATURE_DOCUMENT_MAP.json` 可解析。文件控制器因外部 `output/` junction 權限受限，本次無法核完整倉庫連結；已登記本次新增的 feature 與 QA 關聯。

## 限制

- 未重啟 GUI，未完成 Owner 原生介面 UAT。
- 測試與機器驗證只證明投影及呈現行為，不代表候選來源已被接受或可用於正式資料／下游決策。
- weekly collection 逐筆唯讀明細已另於[Gate 2 QA](BALDR_WEEKLY_COLLECTION_DETAIL_QA_20261025.md)完成；附件路徑及開啟仍未接線。其他產品 Gate 與 ML 仍待後續階段。

## 2026-10-25 後續：來源特定契約查核提示

P0 選取列明細現在另列該來源的可得日政策與是否必填、新鮮度規則、缺件處理、覆蓋要求、重試政策，以及已登錄的 acquisition route（provider、market scope、availability evidence、evidence role、implementation status 與 endpoint）。例如 TDCC 週資料的可得日規則與 MOPS 季報公告／修訂日規則會分別呈現；政策和路徑僅說明應查什麼，不代表已取得證據。

- P0 Source Control Center、Update formatter、Workbench 與 Research Console 聚焦測試：182 passed。
- 未改任何 source decision、machine/license/PIT status、acquisition eligibility 或下游資格；沒有來源被標成 accepted。
- 本切片未重跑全域 mypy、Update validator 或原生 GUI／Owner UAT；前述驗證結果屬於前一節原始切片。
