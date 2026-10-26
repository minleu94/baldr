# Baldr 週 Evidence 收集明細 QA（2026-10-25）

## 範圍

Data Update 的整體 Readiness 區新增「檢視週收集明細（唯讀）」。按下後只讀取設定的 weekly collection sidecar，使用既有 `build_weekly_approval_input` 進行 hash／狀態檢查，將最多 30 筆待人工審查記錄整理為可讀文字。每筆顯示期間、collection ID、source hash、收集與審查性狀態、最近交易日、覆蓋基準與統計、品質發現，以及最多 5 筆不完整列例子。

明細不顯示本機來源／附件路徑或任意 payload，不提供開附件、核准或寫入動作。官方收據只顯示雜湊供人工核對。來源雜湊只綁定收集當時的來源快照，不代表 full-universe coverage、品質、PIT、License 或人工審查通過，也不授 Gate credit。

## 驗證結果

- Weekly approval input、collector、formatters 與 Update UI focused tests：126 passed。
- Data Update Tab validator：25 passed、0 failed、4 skipped。
- 全域 mypy：1,145 個來源檔，無錯誤。
- 4 個修改中的 Python 程式與測試檔 `py_compile` 通過。
- `git diff --check` 通過；`FEATURE_DOCUMENT_MAP.json` 可解析。
- 文件控制器回報既有 `output/` junction `WinError 5`，並列出歷史外部連結／錨點問題；無法完成完整倉庫連結檢查。本次新增的 UI／QA 關聯已登記，新增文件間的相對連結已人工確認。

## 限制

- 未重啟 GUI，未完成 Owner 原生介面 UAT。
- 附件路徑與附件開啟尚未接線；目前只顯示已記錄的收據 hash。需另有根目錄限制與開啟前 hash 驗證，才可安全呈現可開附件。
- 此功能僅讓現有收集結果可被看見及人工核對；舊收集缺來源／coverage 時仍需重新收集，不能由 Owner 核准補出證據。
