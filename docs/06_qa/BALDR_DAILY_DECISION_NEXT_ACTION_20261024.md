# 每日決策旅程與推薦 artifact 可用性 QA — 2026-10-24

## 結果摘要

每日決策旅程的缺件「下一步」已改為指向程式內可見的資料更新、每日來源詳情、市場探索或證據成熟度入口。擴展回歸期間也修復了 Windows 上推薦 artifact 的路徑檢查與 create-only 發布阻塞，讓相同的每日旅程與保存／讀回測試能在此 Windows 執行環境通過。

## 修復內容

- `app_module/daily_investment_journey.py`：不同缺口狀態指向實際介面入口，保留 stale、缺值、身份及自然成熟語義。
- `data_module/result_artifact_store.py`：路徑完整性改成逐層檢查 symlink／reparse component，不再依賴此 Windows 環境會回 `WinError 5` 的 `Path.resolve(strict=True)`。Windows artifact 以同目錄原子 `os.rename` 發布，目的檔已存在時拒絕覆寫；POSIX 保留 hard-link create-only 行為。
- `app_module/recommendation/queries.py`：legacy runs root 用逐層 lstat preflight；檔案仍由既有 Windows／POSIX no-follow reader 開啟，不再用 final-path resolve 代替身份驗證。
- 新增回歸：七種每日旅程缺件分流、resolve 權限受限仍可保存／讀回，以及模擬 reparse ancestor 在發布前 fail closed。3 個需要真實建立 symlink 的案例因 Windows host 不允許建立暫存連結而跳過。create-only 發布失敗注入測試按平台攔截 rename 或 hard link。
- 手冊、UI 功能說明、Feature Map 與 Snapshot 已同步。

## 驗證收據

- `tests/test_r012_recommendation_artifact_persistence.py` + `tests/test_daily_investment_journey.py`：**70 passed、3 skipped**。
- Workbench 必要回歸：89 passed；離線 Data Update validator：25 passed、0 failed、4 skipped（真實下載／合併項目跳過）。
- 全域 mypy：1,144 個來源檔無問題。
- 本輪變更的六個 Python 檔 `py_compile` 成功。
- 受管 Windows Job：啟動可用 RAM 約 24.7 GiB；Job 限制 readback 為 8 GiB、12 個程序。唯一回報 PID 已退出，Job handle 關閉、執行鎖釋放，未強制清理。
- `git diff --check` 通過；Feature Map JSON 可解析。

## 未接受的 Gate 與界線

這些修復讓推薦結果保存／讀回與每日旅程的工程路徑在本機回歸可用，沒有提供正式來源覆蓋、資料授權、PIT、ML sealed labels／walk-forward、自然排程成熟或 Owner UAT 證據。這些產品 Gate 狀態不變。

## 可重現入口

- `tests/test_r012_recommendation_artifact_persistence.py`
- `tests/test_daily_investment_journey.py`
- `tests/test_ui_qt_update_view_workbench.py`
- `scripts/qa_validate_update_tab.py`