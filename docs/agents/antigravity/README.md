# Antigravity 平台適配入口

本目錄只保存 Antigravity 適配及交接格式。共同安全規則在根目錄 `AGENTS.md` 引入的 `docs/agents/shared_context.md`；唯一人類角色路由在 `docs/agents/skills_registry.md`；六份 `docs/agents/*.md` 是角色權威卡。

## 平台規則

- Gemini CLI 透過根目錄 `GEMINI.md` 匯入 `AGENTS.md`；Antigravity 依其自身規則載入機制讀取 repo 規則及適用的 `.agent/rules/*.md`。不要假定 Gemini CLI 的匯入語法等於 Antigravity 的規則觸發方式。
- `.agent/rules/*.md` 只保存按需的平台細則，須符合 Antigravity 當前支援的 frontmatter／trigger 格式；`model_decision` 規則需有 `description`。共同流程與完整必讀清單只由 `AGENTS.md` 維護。
- 調整載入行為或 frontmatter 格式前，先核實官方文件；完成後同步 `GEMINI.md` 與本頁的平台差異說明。

## 角色入口

由 `docs/agents/skills_registry.md` 選取本次需要的角色，再閱讀對應的共同權威卡與此目錄同名的輕量適配卡：

- `tech_lead_agent.md` → `../tech_lead.md`
- `data_audit_agent.md` → `../data_audit_agent.md`
- `data_cleanup_agent.md` → `../data_cleanup_agent.md`
- `execution_agent.md` → `../execution_agent.md`
- `documentation_agent.md` → `../documentation_agent.md`
- `testing_qa_agent.md` → `../testing_qa_agent.md`

## 任務交接

多階段或需交接的任務按 `../skills/team.md` 完成 Intake、影響／QA 計畫、實作、驗證、文件與 root 整合。交接摘要格式見 [`handoff_template.md`](handoff_template.md)；task-ID 狀態與 legacy singleton 所有權見 [`../shared_state/README.md`](../shared_state/README.md)。
