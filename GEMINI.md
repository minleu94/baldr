# Gemini／Antigravity 專案規則

> 共用 repo 規則由 `AGENTS.md` 維護。Gemini CLI 透過下方匯入載入；Antigravity 會自動發現根目錄 `AGENTS.md`。本檔只保留平台適配規則，避免複製第二份必讀清單。

@./AGENTS.md

## 平台適配

- Gemini CLI 的 `GEMINI.md` 階層與 Antigravity 的規則目錄是不同載入機制；不要假設其中一方會自動讀取另一方的專案規則檔。
- Antigravity 任務依 `docs/agents/skills_registry.md` 選擇角色，並依工作範圍讀取對應的 Agent 權威文件。
- `.agent/rules/*.md` 是按任務載入的補充規則；每份都必須有有效 YAML `trigger` 與 `model_decision` 所需的 `description`。把跨任務不變原則放在 `AGENTS.md`，不要在規則檔重複完整權威清單。
- 若平台自動載入行為或格式變更，先以官方文件核實，再同步更新本檔與 `docs/agents/antigravity/README.md`。
