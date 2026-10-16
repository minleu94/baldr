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

功能地圖中每個功能自己列出的 code／tests 代表入口，都必須命中自己的 `change_patterns`；別的功能有命中不代替本功能同步責任。`check` 會核對這項完整性。

## 交付條件

- 適用 QA 有真正的命令、結果與證據位置；`not_run`、失敗、未完成不得標 done。
- 所有必要文件已更新或具名說明不適用，使用者可沿入口到達。
- 必要角色與風險檢查沒有漏列；look-ahead、精度及原始資料規則仍依[共用規則](../agents/shared_context.md)。
- 未完成事項與安全接手點明確。工作狀態、工程通過、產品接受、正式資格與自然運行各自判讀。
- 只提交本任務成果；排除本機狀態、原始資料、Graphify 與 raw QA。

使用 `scripts/document_control.py check --task output/tasks/<唯一ID>/task.json` 檢查結構與記錄；總負責者另外核對正文、實際差異及證據內容。檔案存在、metadata 宣稱通過或所有連結有效，都不足以證明產品有效。

## 工具與例子

### 任務上下文與漸進閱讀

`context` 是依既有 Feature Map `reading_routes` 產生的暫時視圖，不是另一份產品摘要或索引資料庫。先以路徑、標題或 symbol 定位，再依需要擴大：Level 0 共用入口；1 領域路由；2 契約／狀態／已知問題；3 程式 AST 簽名與測試候選；4 明示歷史研究。十個閱讀領域為 `ui`、`bug`、`data_pipeline`、`technical_analysis`、`recommendation_research`、`portfolio_health`、`ml_model`、`scheduler_automation`、`architecture_refactor`、`documentation_qa`。它們選擇閱讀來源，不改變 `route --kind` 的履職、風險與授權規則。

每個路由提供代表性章節；其他功能沿輸出的 `related_paths` 與實際搜尋深入，不以代表性 selector 代替全領域覆核。`--inspect-file` 是閱讀來源，`--changed-file` 才產生同步核對清單。Level 3 預設只讀 Git HEAD 已有的文字來源之工作樹版本；ignored/private receipt、未提交新檔、symlink 與大型來源不自動擷取，須由 owner 在安全範圍另行核驗。CSV／JSON 清冊由程式處理，不全文送入 Context。

功能地圖與 Issue register 是本命令明示讀取的兩份治理 metadata，另列 HEAD blob、工作樹 SHA 與 XY；新 register 若尚未提交就明示 untracked/WIP，不作已提交事實。這個例外不允許自動閱讀其他 untracked 或 ignored evidence。同步影響使用同一次讀取的地圖，避免混入另一版 selector。

`--max-chars` 限制來源摘錄字元，不含 JSON metadata／包裝；整個命中放不下便列 `budget_omitted`，不截去安全限制。成功產生視圖不等於問題已解；必須檢查 `unverified_unknown`、`headings_only`、原始上下文與正文語意。`contains` 只選命中行，不能證明附近沒有反例；需要完整章節時回原始來源。輸出含 Task、Docs／Code／Contracts／Status／Tests、Issues、Constraints、Source Version、Unknown。字元與 UTF-8 bytes 是實測；`ceil(UTF8 bytes/3)` 僅是粗估 Token，不是模型 tokenizer、實際花費或人工時間。

```powershell
# 下列 Python 命令仍須依 shared_context 的 owned Job／mutex 執行，不是豁免資源守衛。
.\.venv\Scripts\python.exe scripts/document_control.py context --domain ui --level 3 --format text --request "找 Daily Decision Desk"
.\.venv\Scripts\python.exe scripts/document_control.py context --domain architecture_refactor --level 3 --inspect-file app_module/decision_desk_dtos.py --changed-file app_module/decision_desk_dtos.py
.\.venv\Scripts\python.exe scripts/document_control.py trace --inspect-file app_module/decision_desk_dtos.py --symbol DecisionDeskSnapshot
.\.venv\Scripts\python.exe scripts/document_control.py inventory --base HEAD~1
.\.venv\Scripts\python.exe scripts/document_control.py issues
.\.venv\Scripts\python.exe scripts/document_control.py archives --path output/qa/personal_daily_product_20261006
.\.venv\Scripts\python.exe scripts/document_control.py check --context-metadata
```

在自己 ignored task output 保存 Context 和命令，將實際閱讀路徑另記 `read_files`／`inspection_scope`，記錄來源 HEAD、工作樹 SHA、selector／行號與未讀部分；工具不自動改他人 task。接手時重建視圖並核差異，不永久貼一份完整摘要。查詢程式存在或簽名用 `trace`；它不執行測試、不 import 產品，也不證明文件與行為相等。測試及 Evidence 是候選入口，原 receipt 的 commit、source pins、run／資料／環境適用性必須另核。

### 現況、Issue 與增量驗收

`inventory` 動態取 Git HEAD tracked tree；預設給分類統計、工作樹 XY 狀態及可選 base→HEAD delta，`--details` 才給文件逐檔 HEAD blob／工作樹 hash。Archive、Target、QA/navigation 的路徑分類只是機械候選，不替代文本權威判斷。ignored DB／models／Graphify／秘密資產不掃描內容，untracked 另列；固定 1,520 路徑[歷史 Manifest](DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv)保持原樣，不能把新分母或 hash 當成新全庫 EOF 覆核。

G01–G10 的已解範圍與外部證據界線由[結構化 Issue register](DOCUMENT_GOVERNANCE_ISSUES.json)追蹤，正文判定回其原始矩陣／QA。沒有 owner 證據便保留 null；Git 作者不是 owner。治理 G09 與排程 G9／H20 不同。已解問題不重開；新的外部資格結果另核來源與 resolution criteria。

冷封存先查[既有資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md#查詢已登記的冷封存)與 `archives`。已登記的外部證據仍要區分目前是否可讀，以及內容是否另有核驗；不能當成新發現的未追蹤資料。

`check` 將精確登記且 Junction 目標相符的引用另列為 `registered_external_references`，保留 `availability` 與 `content_verified=false`。未登記越界、目標漂移及內部跳脫仍拒絕；登記不等於內容驗證通過。

閉環順序為：分類任務 → 最小 Context → 正文／程式／證據 → 授權工作 → 適用 QA → diff／Coverage → 需要時同步章節與狀態 → metadata／link／task check → Root review → scoped commit。實作看 Git／source；WIP 看工作樹與 owner task；QA 看原始 run；產品接受看 Gate。Snapshot 只摘要實質改變，不為每次測試重寫；README 保持穩定使用入口。Graphify 沿[現有指南](DOCUMENTATION_GRAPH_GUIDE.md)供導航，來源版本不符時回 Feature Map／Git，保護原圖及歷史原件。本輪固定五題與驗收見[治理 QA](../06_qa/DOCUMENT_CONTEXT_GOVERNANCE_ACCEPTANCE_20261013.md)。

從 repository 根目錄執行。下面以新的 UI 任務示範；換成自己的 task ID、owner 與修改範圍，既有 ID 不會被覆寫：

```powershell
.\.venv\Scripts\python.exe scripts\document_control.py route --kind ui --changed-file ui_qt/views/update_view.py
.\.venv\Scripts\python.exe scripts\document_control.py init-task --task-id my-ui-task --owner root --kind ui --changed-file ui_qt/views/update_view.py
.\.venv\Scripts\python.exe scripts\document_control.py check --task output/tasks/my-ui-task/task.json
```

`scripts/auto_state_sync.py` 無參數時只唯讀列出 Git 狀態，不更新任何任務狀態。只有明確成對提供 `--task output/tasks/<task_id>/task.json --owner <exactowner>`，並通過 schema、路徑及 owner 核對，才會以原子替換更新該 task 的 `git_status`；不寫入其他 task，也不觸碰舊 `active_task.yaml`、`handoff_log.md` 或 resume prompt。

其他工具只依標準函式庫讀文件與 source 常數。`route` 不 spawn Agent；`bootstrap-plan` 不建立 Task Scheduler、不搬資料或呼叫 producer。範例移機清冊見 [公開範例](../../examples/machine_bootstrap_manifest.example.json)，實際私人內容放 ignored output 並另作安全備份。

本輪文件重整的計畫與處置見[整合計畫](../superpowers/plans/documentation_productization_plan_20261012.md)及[處置入口](../09_archive/documentation_productization_20261012/README.md)。
