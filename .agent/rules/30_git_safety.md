---
trigger: model_decision
description: "準備 stage、commit，或處理共用工作樹與產出檔案時載入。"
---

# Antigravity Git 適配

- Stage／commit 前閱讀 `docs/agents/git_exclusions.md`，確認 `git status --short`，只處理本任務檔案。
- 共用工作樹、分支與交接依 `docs/agents/multi_agent_workflow.md`；禁止覆寫或清除他人的未提交變更。
- Stage、commit、push、發布、資料清理與分支／工作樹清理都需符合 `docs/agents/shared_context.md` 的授權與安全邊界。
- 不在本規則維護第二份排除清單或通用安全規則。
