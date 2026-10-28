# Smart Money 主表資料品質摘要（2026-10-27）

## 範圍與結果

Smart Money 範圍選單旁新增三個目前主表列數：含至少一筆 estimated 事件、含至少一筆 unavailable 事件，以及事件分類計數無法判定的列數。三種計數以 scope 篩選後的訊號 DTO 為準；估算與張數未知可同時計入同一檔。分類計數合計為零、含負值或無法轉為整數時列為未分類，避免將缺少分類誤讀成零估算或零未知。

提示只描述目前表格列，並非市場母體涵蓋率。摘要卡仍沿用全市場掃描摘要；週期、資料日、來源判定、張數計算、Gate／PIT／ML 資格均未改變。初始「尚未載入」、成功空結果及刷新保留舊表格的行為維持各自原狀；刷新失敗時品質數描述畫面仍顯示的舊列。

## 驗證

- `pytest tests/test_ui_qt_smart_money_flow_view.py tests/test_ui_qt_smart_money_flow_async.py -q -o addopts=`：25 passed。
- 必要 Workbench UI 回歸 `pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=`：97 passed。
- `scripts/qa_validate_update_tab.py`：25 passed、0 failed、4 skipped；詳細報告在 `output/qa/update_tab/VALIDATION_REPORT.md`。
- 修改的兩個 Python 檔 `py_compile`：passed。
- 指定全域 mypy：未通過，先被既有 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻擋；該檔不屬於本次修改。
- `document_control.check_task`：passed；變更文件的連結檢查僅回報 Snapshot 內四個既有失效錨點，新增 QA／手冊連結通過。全庫 `document_control check --task` 另列多筆既有 `output/` junction 越界連結；未擴大修復其他功能文件。
- Root-owned Windows Job 收據與完整 stdout／stderr 位於 `output/tasks/smart-money-visible-quality-20261027/evidence/`；Job memory 上限 8 GiB、程序上限 12、kill-on-close 及 limits readback 均通過，結束時無殘留 Job process，未強制清理。

## 未驗範圍

沒有執行原生 MainWindow／Owner UAT，也沒有實測正式資料庫的計數內容或畫面延遲。自動化檢查只驗證標籤依 DTO 與 Top／Bottom／All 顯示範圍更新，以及摘要卡與資料日保持不變；不代表整體視覺接受或產品 Gate 通過。
