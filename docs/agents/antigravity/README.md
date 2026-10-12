# Antigravity Agent 入口

> 給 Antigravity 使用的角色分流入口。專案權威仍維護在 `docs/agents/` 與 `docs/00_core/`。

## 平台規則載入

- Gemini CLI 依 `GEMINI.md` 的階層載入上下文；根目錄 `GEMINI.md` 匯入 `AGENTS.md`，讓共用 repo 規則只有一份來源。
- Antigravity 會自動讀取工作區根目錄及目標目錄祖先中的 `AGENTS.md`、`GEMINI.md` 與規則目錄。此 repo 保留舊版相容位置 `.agent/rules/*.md`。
- 規則目錄中的每個 Markdown 都必須以 YAML frontmatter 宣告有效 `trigger`：`always_on`、`model_decision`、`glob` 或 `manual`。`model_decision` 另需 `description`；未宣告或值無效時，Antigravity 會靜默忽略該規則。
- 一般細則使用 `model_decision` 以按需載入；跨任務的短而穩定原則放在 `AGENTS.md`。修改規則格式前，核對[官方 Antigravity Rules 文件](https://antigravity.google/docs/rules/)及[Gemini CLI GEMINI.md 文件](https://google-gemini.github.io/gemini-cli/docs/cli/gemini-md.html)。

## 先讀什麼

Antigravity 開工的完整必讀順序與條件式文件以根目錄 [`AGENTS.md`](../../../AGENTS.md) 為準；`GEMINI.md` 供 Gemini CLI 匯入同一份規則。本頁負責角色分流與交接，不另維護一份縮短版必讀清單；每項適用的權威文件都要先讀，再依下表選擇角色文件。

若依任務範圍略過條件式文件，請在交接模板的「不適用項目」欄說明原因。

## 角色選擇

| 任務類型 | 使用角色文件 | 原始權威文件 |
|---|---|---|
| 架構判斷、是否該做、風險評估 | `tech_lead_agent.md` | `docs/agents/tech_lead.md` |
| 功能實作、Bug 修復、測試補強 | `execution_agent.md` | `docs/agents/execution_agent.md` |
| 文檔 Coverage、索引與 Snapshot / Roadmap Hub / 6M Roadmap / 長期版本階梯 / Carryover / Architecture / Manual 同步 | `documentation_agent.md` | `docs/agents/documentation_agent.md` |
| 資料完整性、資料對比、資料品質 | `data_audit_agent.md` | `docs/agents/data_audit_agent.md` |
| 清理、移除、整理、未使用檔案判斷 | `data_cleanup_agent.md` | `docs/agents/data_cleanup_agent.md` |
| 測試路由、功能驗證、QA healthcheck 結果解讀、feature-to-test matrix 判讀 | - (無適配層，直接使用權威文件) | `docs/agents/testing_qa_agent.md` |

## 使用方式

在 Antigravity 中開新任務時，直接貼上：

```text
請依照 GEMINI.md 與 docs/agents/antigravity/README.md 工作。
本次任務類型是：[Tech Lead / Execution / Documentation / Data Audit / Cleanup / Testing QA]。
請先閱讀必讀文件，再執行任務。
```

## 跨工具協作原則

- Codex、Antigravity 與使用者可能同時留下未提交變更；任何 Agent 都不得覆寫非自己產生的變更。
- 若任務要平行開發，優先使用獨立 branch 或 worktree。
- 若只是在同一個根目錄輪流切換工具，先確認目前工具已停止工作，再交給下一個工具。
