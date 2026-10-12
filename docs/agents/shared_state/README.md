# 任務狀態與遷移

## 新任務狀態

多階段、需暫停恢復或需交接的本機任務使用 `output/tasks/<task_id>/task.json`，由 `scripts/document_control.py init-task` 建立，並以 `scripts/document_control.py check` 檢查。確切欄位與命令行契約由該工具定義；不要在角色卡或 handoff prompt 再建立平行 schema。

此檔是被 Git 忽略的本機協作狀態，不是產品狀態、資料品質結果或 Scoped SSOT。產品與工程現況仍寫在相應權威文件；可分享的持久證據依文件治理流程另行保存。

## 所有權與並行任務

- 每個 task ID 只由一位 root／task owner 建立、更新及完成狀態。Root 負責 task JSON 與整合交付；協作者回報結果，不同時寫入同一份 task JSON。
- 若明確授權建立互相獨立的子任務，使用各自 task ID 與狀態檔，並由 parent root 保留總責任。Subagent 不替 parent 改寫狀態或擴張 scope。
- 交接需記錄目前階段、安全接手點、已改／已讀文件、驗證結果及未完成事項。只記實際發生的事件，不把待跑工作標為完成。
- 不因流程要求而自動寫入 Git 忽略目錄中的任務狀態以外檔案；`output/` 仍受 `git_exclusions.md` 管理。

## 舊 singleton 與遷移

現有 `active_task.yaml`、`handoff_log.md` 與 resume prompt 是原有任務的 singleton／交接資產，和 task-ID 狀態可並行存在。新增工作不自動搬移、覆寫、追加或刪除它們，也不假設它們代表新任務狀態。

遷移只能由現有資產 owner 明確安排，需保留原件、核對任務身分及證據來源、確認新狀態完整後再記錄遷移結果。新工具不得自動接管或清理既有 singleton；尚未遷移的舊任務依其 owner 指定的接手方式處理。

## 更新記錄

- 2026-10-12：定義 task-ID 本機狀態、單一 owner、並行工作及既有 singleton 的保留／遷移界線。
