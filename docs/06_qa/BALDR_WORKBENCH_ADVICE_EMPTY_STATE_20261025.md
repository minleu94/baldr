# Workbench Advice 空結果判讀 QA — 2026-10-25

## 問題與修正

Advice DTO 沒有輸出正式建議、Professional 研究候選或配置列時，UI 先前一律顯示泛用的「無符合條件」及推測可能原因。這會把「DTO 同時回報資料／資格警告」和「DTO 沒回任何警告的空結果」混成同一種狀態。

現在有警告時，空狀態會列出最多三則原因，並提示警告不會自動補資料或取得資格；超過三則的項目仍由下方完整原警告保留。已知 Advice 診斷碼在摘要中有白話說明，未知值保留原文。無警告時，UI 明示 DTO 沒提供空結果原因，不推定資料完整或風險解除。摘要會 escape 來源文字，避免 DTO 內容被當作 HTML 解讀。

## 驗證

- `tests/test_workbench_advice_contract.py` + `tests/test_ui_qt_workbench_view.py`：**51 passed**。
- `tests/test_ui_qt_update_view_workbench.py`：**89 passed**。
- `scripts/qa_validate_update_tab.py`：**25 passed、0 failed、4 skipped**。日誌及報告導向本次隔離 QA 目錄；測試只建立合成資料，不讀寫正式資料。4 項 live download／merge 仍依腳本設定跳過。
- 全來源 mypy：**1,144 個來源檔無問題**。
- 受改 Python 檔 `py_compile` 通過；`git diff --check` 通過；Feature Map JSON 可解析。
- 測試由受控 Windows Job 執行：8 GiB 記憶體／12 程序上限讀回、kill-on-close；Job 自然結束、沒有殘留程序且執行鎖已釋放。Qt session cleanup 提示因 `ui_qt.main` 未載入而保留原視窗；測試程序仍以 return code 0 結束。
- `document_control check`：本 QA 收據與 Operations／Product UX 兩索引通過。Application Manual 與 Snapshot 的檢查受本機 sandbox 阻止讀取 repo 的 `output` Junction（WinError 5）；Snapshot 另有既存連結越界診斷。此環境結果不證明那些 Junction 目標遺失。

## 限制

此修正改善空結果的可讀性與來源文字安全，不產生候選、不補行情、不替來源取得正式資格，也不解除 Gate 1／PIT／ML／自然 evidence。依共用規範建立 `output/tasks/.../task.json` 也因同一 Junction 存取限制未成功。`qa_validate_update_tab.py` 支援的 `BALDR_UPDATE_TAB_QA_LOG_DIR` 已將本次 log 導入隔離目錄後完成驗證。
