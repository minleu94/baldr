# Gate 2 週報 Owner 覆核入口 QA（2026-10-26）

## 範圍

把已保存的 Evidence Operations 週報接到產品內的具名人工覆核入口。覆核只追加到獨立的 `approved-weekly-history-projection.v1` JSON；不寫正式 SQLite、不修改週報快照、不啟用 production scheduler、不接受資料來源，也不提供 Gate／ML credit。

投影追加前會重新讀取歷史紀錄，確認 `review_id`、完整 `review_hash`、`period_start`、`period_end` 一致；確認操作者填寫姓名／識別、Owner 角色、理由並明確勾選後，以鎖定加原子替換方式追加。既有週期不可覆寫或重複核准。Owner 身分是操作者自我聲明，系統不驗證登入帳號。

## 實作

- 歷史 read model 與詳情新增週報 SHA-256。
- projection 未設定或歷史列沒有 hash 時，覆核按鈕停用；投影路徑使用既有 `WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH` 設定。
- Owner 覆核對話框要求覆核者姓名／識別、角色、理由與二次確認，提示核准範圍與不授予的資格。
- 新增 `WeeklyReviewApprovalService`，驗證歷史 pin、安全拒絕正式 SQLite 路徑、維持 `formal_credit_authorized=false`，並將姓名及理由保留在 projection。
- 更新使用手冊、UI 行為文件與 Feature Map。

## 驗證

Windows owned Job：8 GiB memory cap、最多 12 個 processes、kill-on-close；執行前可用 RAM 約 18.5 GiB。pytest 臨時目錄設在隔離 scratch。

| 驗證 | 結果 |
|---|---|
| `tests/test_weekly_review_approval_service.py`、`tests/test_evidence_operations_history_dashboard_service.py`、`tests/test_ui_qt_evidence_review_dashboards.py`、`tests/test_data_governance_consolidation.py` | 86 passed |
| `tests/test_ui_qt_update_view_workbench.py` | 93 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed／0 failed／4 skipped |
| 全域 mypy（ui_qt、app_module、data_module、analysis_module、backtest_module、decision_module、portfolio_module、runtime） | 1,146 source files，無錯誤 |
| 修改的 11 個 Python 檔 `py_compile` | 通過 |
| `document_control.py check --path docs/00_core/FEATURE_DOCUMENT_MAP.json` | 通過，12 features，無 errors |

第一次 pytest 使用 sandbox 不允許的預設 `%LOCALAPPDATA%\Temp`，在臨時檔原子替換遇到 WinError 5；改用隔離 scratch 的 `--basetemp` 後，完整聚焦組 86 passed。這兩次失敗原始 log 保留在隔離 scratch。`document_control check --path docs/07_guides/APPLICATION_MANUAL.md` 被既有 `output/trial/.../TRIAL_GUIDE.md` Junction 的 WinError 5 阻擋；兩個連結均不屬本次修改，沒有更動該 junction。`document_control check --task output/tasks/baldr-daily-product-completion-20261025/task.json` 同樣因 repo `output` junction WinError 5 無法讀取；task ledger 本體已原子更新並回讀，結構 check 未能執行。

## 未驗證與 Gate 狀態

- 沒有啟動正式 UI 做原生目視或由真正 Owner 執行覆核；沒有建立／改寫任何實際 projection 或正式資料庫。
- 沒有完成任何新增的真實週期核准。2026-10-19..25 候選仍待具名 Owner 檢查來源、覆蓋及警告。
- Gate 2 仍缺至少三個真實週報期間、三個操作日 evidence record、真實 action-item 後續節奏、backup／restore、rollback／disable-first recovery 演練及 scheduler 獨立明確 approval artifact。
- Gate 3 的來源授權、PIT、完整 coverage、單位／basis 及來源逐筆接受不受此流程變更影響；ML 仍不得進入正式推薦或 Portfolio Advice。

因此本次只完成「Owner 能對一份已保存且 hash 固定的週報留下可追溯人工覆核」的產品能力，不表示 Gate 2、Gate 3、Gate 7 或產品整體已通過。
