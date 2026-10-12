---
trigger: model_decision
description: "在 Antigravity 任務選擇 repo 入口、Scoped SSOT 或 Agent 角色時載入。"
---

# Antigravity 專案入口規則

- 共用 repo 流程依根目錄 `AGENTS.md`；Gemini CLI 由 `GEMINI.md` 匯入，Antigravity 自動發現根目錄規則。
- Use `docs/agents/skills_registry.md` to select a role and its authoritative `docs/agents/*.md` guide. Do not keep a second copy of the full required-reading list here.
- Use `AGENT_CONTEXT.md` only as quick navigation. Current state and topic-specific conclusions belong to the scoped authorities named in `AGENTS.md`.
- Keep this rule limited to entry and routing. Put code, documentation, and Git procedures in their task-specific rules.
