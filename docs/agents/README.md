# Agent 文件入口

共用規則與角色路由只有一份：

1. [`shared_context.md`](./shared_context.md)：所有角色必須遵守的安全與工程硬規則。
2. [`../00_core/PROJECT_SNAPSHOT.md`](../00_core/PROJECT_SNAPSHOT.md)：目前狀態摘要與當前風險；日期化停點只在相關任務中讀取。
3. [`skills_registry.md`](./skills_registry.md)：唯一人類角色路由入口，依任務選讀角色權威卡。
4. 多階段或需交接時讀 [`skills/team.md`](skills/team.md)；各角色依指定輸入完成自己的階段，root 負責全程整合與交付。

## 六份角色權威卡

- [Tech Lead](./tech_lead.md)：技術決策、架構與風險評估。
- [Data Audit](./data_audit_agent.md)：資料完整性、一致性與品質證據。
- [Data Cleanup](./data_cleanup_agent.md)：清理目標、依賴及復原性盤點。
- [Execution](./execution_agent.md)：已授權的實作、驗證與所需交付同步。
- [Documentation](./documentation_agent.md)：覆蓋分析、文件修訂與一致性。
- [Testing / QA](./testing_qa_agent.md)：測試路由、QA 計畫與結果判讀。

角色卡格式一致：觸發、輸入、輸出、授權邊界、完成條件與交接。它們不重複共用安全規範或固定必讀長清單。

## 其他入口

- [Git 排除清單](./git_exclusions.md)：Stage／commit 前閱讀。
- [多 Agent 協作流程](./multi_agent_workflow.md)：分支、工作樹與整合邊界。
- [Antigravity 適配入口](antigravity/README.md)：平台差異、角色適配及交接模板。
- [Shared state 使用與遷移](shared_state/README.md)：以 task ID 隔離的本機任務狀態及既有 singleton 的所有權規則。
- [Coverage Map](../00_core/DOC_COVERAGE_MAP.md)：文件同步範圍；任務工作流見[產品變更流程](../00_core/PRODUCT_CHANGE_WORKFLOW.md)。
- [Quant Defense Guard](skills/quant_defense_guard.md)：金融核心變更時的靜態檢查入口；共同硬規則及領域時間契約仍回 shared context 與對應 Scoped SSOT。

## 文件關聯怎麼讀

角色卡是按任務載入的行為契約，不是各自獨立運作的 Agent，也不需要彼此全部互連。正常閱讀鏈是「本頁 → 角色路由 → 共用角色卡 → 本次輸入與交接」；Antigravity 另沿「平台入口 → 適配卡 → 同一份共用角色卡」。路由只選必要角色，連結存在不代表每次都要全文閱讀。

圖中的孤點須先回查正文：反引號內的路徑、JSON 路由及命令是文字／機器關聯，不一定形成 Obsidian 或 Graphify 的文件邊。角色／適配卡指向規則、輸入及交接角色的已知關係應使用可點擊相對連結；清單、模板或日期化交接可以是葉節點。Obsidian 圖譜篩選與舊 Graphify snapshot 也不能證明目前檔案無引用，應核現行 links／backlinks 及 Git 來源。

## 歷史參考

[舊 Cursor Skills 定義](archive/CURSOR_SKILLS_DEFINITIONS.md)只供平台遷移追溯；其中舊必讀流程與停止條件不再是現行角色規則。日期化 resume prompt 由其原任務及 [shared state 所有權規則](shared_state/README.md)管理，不為消除圖上孤點而改寫歷史內容。

## 更新記錄

- 2026-10-14：補角色、適配與條件式工具的真實連結，明確區分按需角色、歷史及圖譜孤點。
- 2026-10-12：縮為共用規則、Snapshot、唯一角色路由及必要協作入口。
