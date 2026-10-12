# Gemini CLI／Antigravity 平台適配

共用 repo 規則唯一來源是根目錄 [`AGENTS.md`](AGENTS.md)。Gemini CLI 由下方匯入共用規則；Antigravity 依自己的規則載入方式使用根目錄規則及 `.agent/rules/` 適配。不要假設一個平台會執行另一個平台的匯入語法。

@./AGENTS.md

## 平台差異

- Gemini CLI 的本檔只負責匯入 `AGENTS.md`；不重複角色路由、必讀清單或共用安全規則。
- Antigravity 的任務細則位於 `.agent/rules/*.md`，角色適配位於 `docs/agents/antigravity/`。規則須使用平台支援的有效 `trigger`；使用 `model_decision` 時提供 `description`。適配文件只指回 `docs/agents/skills_registry.md` 與角色權威卡。
- 平台載入行為或格式變更時，先核實該平台當前官方文件，再同步此適配與 Antigravity README；不得據單一平台的匯入行為推論另一平台。
