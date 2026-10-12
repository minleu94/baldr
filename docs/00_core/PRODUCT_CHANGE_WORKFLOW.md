# 產品變更與文件同步

每項工作由一個總負責者從需求到交付接續處理。人類與 Agent 使用同一份[角色路由](../agents/skills_registry.md)及[功能關聯](FEATURE_DOCUMENT_MAP.json)，角色不替代使用者授權或正式產品 Gate。

## 開始一項工作

1. 確認任務範圍、目前 HEAD、他人變更及產品狀態。
2. 以 `scripts/document_control.py route --kind <類型> --changed-file <相對路徑>` 產生角色與檢查要求；不確定的文字輸入保持待分類。
3. 根據功能關聯列出需要閱讀的需求、契約、操作、程式與測試。地圖使用現行九工作區 key；深層功能以其原有功能 ID 與領域文件追溯，不能把代表性測試當完整覆蓋。
4. 開工前完成 Coverage，界定須更新的章節與 QA；有風險時先由 Tech Lead／Data Audit 核對。Coverage 是定位步驟；原請求已授權範圍內的必要 QA 與文件同步直接完成，不因 Patch Pass 重複要求確認；超出原範圍才交 root 判斷。
5. 中大型或需交接任務使用 `init-task --task-id <唯一ID> --owner <owner> --kind <類型> --changed-file <路徑>`，建立 `output/tasks/<唯一ID>/task.json`。此本機狀態不取代 Snapshot。

`scope_files`／`--changed-file` 只列預期或實際修改；唯讀調查的閱讀來源另列 `read_files`／`inspection_scope`，不因讀過架構或手冊就要求改它。關聯地圖的治理與安裝規則只匹配其專題入口，一般手冊修訂不觸發全套移機文件；未知變更仍須留下影響判斷或補上相應功能關聯。

## 執行與同步

Execution 完成授權範圍的程式變更、必要測試與文件同步；QA 負責驗證路由與結果解讀，Documentation 負責 Coverage 與正文正確性。一般工作可由同一 Agent 依階段履職；獨立複核必須記錄實際 reviewer 與證據，不能只更換自稱角色。參見 [Team 流程](../agents/skills/team.md)。

| 改變 | 必須核對 |
|---|---|
| 操作入口、參數、結果或安全限制 | 工作區手冊、功能文件及適用 QA |
| 資料流、模組或契約 | 現行架構主題正文、功能導航、測試 |
| 接受狀態、限制或下一步 | Snapshot 與支持該範圍的具名 QA |
| 根路徑、排程、安裝或移機 | 安裝與移機 Runbook、排程操作及驗收 |
| 文件新增、刪移、權威改變 | 領域索引、必要的中央索引與處置紀錄 |

每個 Coverage 項目必須標 `updated`，或標 `not_required` 並寫具體理由。不要求每次重寫所有權威；需要同步的章節不能以「程式已完成」略過。更新現行章節並連具名證據，日期化過程放 QA／歷史，不堆在概覽前面。

## 交付條件

- 適用 QA 有真正的命令、結果與證據位置；`not_run`、失敗、未完成不得標 done。
- 所有必要文件已更新或具名說明不適用，使用者可沿入口到達。
- 必要角色與風險檢查沒有漏列；look-ahead、精度及原始資料規則仍依[共用規則](../agents/shared_context.md)。
- 未完成事項與安全接手點明確。工作狀態、工程通過、產品接受、正式資格與自然運行各自判讀。
- 只提交本任務成果；排除本機狀態、原始資料、Graphify 與 raw QA。

使用 `scripts/document_control.py check --task output/tasks/<唯一ID>/task.json` 檢查結構與記錄；總負責者另外核對正文、實際差異及證據內容。檔案存在、metadata 宣稱通過或所有連結有效，都不足以證明產品有效。

## 工具與例子

從 repository 根目錄執行。下面以新的 UI 任務示範；換成自己的 task ID、owner 與修改範圍，既有 ID 不會被覆寫：

```powershell
.\.venv\Scripts\python.exe scripts\document_control.py route --kind ui --changed-file ui_qt/views/update_view.py
.\.venv\Scripts\python.exe scripts\document_control.py init-task --task-id my-ui-task --owner root --kind ui --changed-file ui_qt/views/update_view.py
.\.venv\Scripts\python.exe scripts\document_control.py check --task output/tasks/my-ui-task/task.json
```

`scripts/auto_state_sync.py` 無參數時只唯讀列出 Git 狀態，不更新任何任務狀態。只有明確成對提供 `--task output/tasks/<task_id>/task.json --owner <exactowner>`，並通過 schema、路徑及 owner 核對，才會以原子替換更新該 task 的 `git_status`；不寫入其他 task，也不觸碰舊 `active_task.yaml`、`handoff_log.md` 或 resume prompt。

其他工具只依標準函式庫讀文件與 source 常數。`route` 不 spawn Agent；`bootstrap-plan` 不建立 Task Scheduler、不搬資料或呼叫 producer。範例移機清冊見 [公開範例](../../examples/machine_bootstrap_manifest.example.json)，實際私人內容放 ignored output 並另作安全備份。

本輪文件重整的計畫與處置見[整合計畫](../superpowers/plans/documentation_productization_plan_20261012.md)及[處置入口](../09_archive/documentation_productization_20261012/README.md)。
