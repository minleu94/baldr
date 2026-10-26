# Baldr 週 Evidence 收集明細 QA（2026-10-25）

## 範圍

Data Update 的整體 Readiness 區新增「檢視週收集明細（唯讀）」。按下後只讀取設定的 weekly collection sidecar，使用既有 `build_weekly_approval_input` 進行 hash／狀態檢查，將最多 30 筆待人工審查記錄整理為可讀文字。每筆顯示期間、collection ID、source hash、收集與審查性狀態、最近交易日、覆蓋基準與統計、品質發現，以及最多 5 筆不完整列例子。

明細不提供核准或寫入動作。可選擇例子中的官方收據並按「核驗並預覽收據」；程式先把實際解析路徑限制在設定的 `output_root` 內，再檢查 regular file、256 KiB 大小上限與收集時記錄的 SHA-256。只在全部通過後，以已核 hash 的同一批 bytes 顯示 UTF-8 文字。路徑逃逸、缺失／錯誤 hash、內容變動、過大或非 UTF-8 一律拒絕預覽。此流程不執行收據內容，也不會改寫 sidecar。來源雜湊只綁定收集當時的來源快照，不代表 full-universe coverage、品質、PIT、License 或人工審查通過，也不授 Gate credit。

## 驗證結果

- Weekly approval input + Data Update workbench focused tests：99 passed（附件核驗增量）。
- Data Update Tab validator：25 passed、0 failed、4 skipped；report 寫至隔離 scratch，正式 `output/qa` 未改動。
- 全域 mypy：1,145 個來源檔，無錯誤。
- 本增量 3 個 Python 程式與測試檔 `py_compile` 通過。
- `git diff --check` 通過；`FEATURE_DOCUMENT_MAP.json` 可解析。
- 文件控制器回報既有 `output/` junction `WinError 5`，並列出歷史外部連結／錨點問題；無法完成完整倉庫連結檢查。本次新增的 UI／QA 關聯已登記，新增文件間的相對連結已人工確認。

## 限制

- 未重啟 GUI，未完成 Owner 原生介面 UAT。
- 預覽只涵蓋 collector 已保存路徑與 receipt hash 的官方收據例子；不代表其他 payload 附件已接線或驗收。
- 此功能僅讓現有收集結果可被看見及人工核對；舊收集缺來源／coverage 時仍需重新收集，不能由 Owner 核准補出證據。

## 2026-10-25 附件核驗增量

新增 `read_verified_official_receipt`，UI 只使用明確設定的 `output_root` 作授權根目錄；先解析路徑並驗證 containment，再以有界讀取比對 SHA-256，之後才預覽文字。Focused tests 99 passed、Update validator 25 passed／0 failed／4 skipped、全域 mypy 1,145 檔、3 個 Python 檔 `py_compile` 通過。未重啟 GUI、未完成 Owner 原生介面 UAT，亦未提供正式來源 acceptance 或 Gate credit。文件控制器結果需待此次文件同步後補記。
