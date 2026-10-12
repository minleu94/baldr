# Agent 規則處置映射

本頁記錄本次角色與流程整理，原件路徑、bytes 與 SHA 見[逐檔清冊](DISPOSITION_MANIFEST.json)。共同硬規則由 [shared_context](../../agents/shared_context.md)維護；[registry](../../agents/skills_registry.md)是唯一人類路由，JSON 為工具讀取投影。

| 原內容 | 現行落點／處置 | 保留的契約 |
|---|---|---|
| 根 AGENTS、AGENT_CONTEXT、GEMINI 的重複必讀與規則 | 根入口按任務讀；GEMINI 只適配平台 | 共用資料保護、精度、look-ahead、程序限制與 Git 所有權留 shared_context；未削弱高風險授權 |
| 六角色的長 prompt、重複 checklist | 六份角色卡統一觸發／輸入／輸出／授權／完成／交接 | Tech Lead 決策；Audit 唯讀品質證據；Cleanup 精確引用與復原性；Execution 實作；Documentation 同步；QA 驗證 |
| Audit／Cleanup／QA 詳細規則 | 各角色卡補條件式方法 | SQLite key/index/duplicate、跨源日期/欄位/NULL/PIT；動態引用／registry／打包；QA 不執行正式 writer |
| 多份協作入口 | Team 流程與 registry | 同一 Agent 可依序履職；獨立委派須有實際調用與授權，root 負責整合 |
| Antigravity 角色副本、`.agent/rules` | 薄適配，Testing QA 補齊 | 只引用同一共用與角色權威，不維護另一套路由；trigger/description 明示平台用途 |
| `docs/agents/skills/team.md` 被當作原生 skill | 新增 `.agents/skills/baldr-product-workflow/SKILL.md` 薄入口 | Team 仍是流程正文；原生 Skill 連回共同文件，不宣稱角色 Markdown 會自動啟動 Agent |
| 舊 singleton task／handoff | 保留原 owner，新增 task ID 隔離狀態 | 不遷移、覆寫或刪除既有 singleton；新本機狀態在 ignored `output/tasks/<id>/task.json` |
| `auto_state_sync.py` 共寫狀態 | 無參數唯讀；明示 `--task`／`--owner` 更新指定 task | owner/schema/ID/path 驗證、原子替換、保留其他欄位；相容 renderer 不作預設 writer |
| 每個任務各寫零散更新記錄 | 功能關聯地圖與產品變更流程 | 開工列 coverage，交付核 current 契約／Manual／QA／狀態；漏同步、缺理由或失敗不能標 done |

角色路由的結構測試與獨立明示 Skill 前測見[驗收摘要](../../06_qa/DOCUMENTATION_PRODUCTIZATION_ACCEPTANCE_20261012.md)。原生主機的隱式 discovery、Antigravity 執行與真安裝不由 Markdown 或本次模擬前測證明。
