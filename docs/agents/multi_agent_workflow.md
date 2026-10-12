# 多 Agent 協作邊界

> 任務階段順序與交付欄位見 [`skills/team.md`](skills/team.md)；角色由 [`skills_registry.md`](skills_registry.md) 路由；共同安全規則見 [`shared_context.md`](shared_context.md)。本頁只補充分支、工作樹與協作者所有權。

## 責任與委派

- Root／任務主 Agent 對 Scope、風險判斷、必要複核、驗證狀態、整合及最終交付全程負責。
- 預設由同一 Agent 按階段承擔多個角色。只有使用者或適用指令明確授權時才使用 subagent；每位協作者需取得有限目標、輸入、檔案範圍、允許操作與交付格式。
- 不同 Agent 不共寫同一 task state。Root 是 task owner，負責 `output/tasks/<task_id>/task.json`；協作者回報結果與自身啟動程序終態給 root。
- 角色輸出是分工證據，不取代 root 的必要風險複核。高風險工作依路由完成 Tech Lead、Data Audit、Testing / QA 等適用關卡後才能交付。

## 分支與工作樹

| 名稱 | 用途 | 邊界 |
|---|---|---|
| `dev` | 開發整合主線 | 整合成果不代表取得 push 授權。 |
| `main` | 穩定版本 | 不直接開發；修改或發布需明確授權。 |
| `codex/*`、`ag/*` | 短期治理或實作工作 | 遵循任務指定基線，不推定新 branch 必須建立。 |
| `research/*` | 實驗性研究 | 需另經整合審查才是產品交付。 |

- 開始前確認目前 HEAD、工作目錄與 dirty tree，辨識他人變更；優先重用合適工作樹。建立隔離工作樹、切換目錄與清理依任務授權處理。
- 若同一檔案已有其他人的修改，先讀懂後以增量方式編輯；不為了乾淨狀態而 revert、覆寫或刪除。
- Branch／worktree 的提交、整合與生命週期依 `shared_context.md` 及任務授權；清理前確認使用者、其他聊天與程序已停止使用且成果可還原。

## 衝突與整合

- 先說明衝突檔案、可查證差異、相容需求及可能的遷移路徑，再由 root 決定如何整合；不得自行重寫對方成果。
- 整合前核對程式邊界與契約、QA 證據、文件相對連結／領域導航及 Scoped SSOT；依風險記錄尚未驗證項目。
- Agent 不自行合併到 `main`。Stage、commit、push、發布或清理僅在明確授權範圍內進行；Git 排除項目見 `git_exclusions.md`。

## 更新記錄

- 2026-10-12：聚焦 root 持續負責、有限委派、task state 單一 owner，以及 branch／worktree 整合邊界。
