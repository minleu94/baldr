# Agent 文件入口

共用規則與角色路由只有一份：

1. [`shared_context.md`](shared_context.md)：所有角色必須遵守的安全與工程硬規則。
2. [`../00_core/PROJECT_SNAPSHOT.md`](../00_core/PROJECT_SNAPSHOT.md)：目前狀態摘要與當前風險；日期化停點只在相關任務中讀取。
3. [`skills_registry.md`](skills_registry.md)：唯一人類角色路由入口，依任務選讀角色權威卡。
4. 多階段或需交接時讀 [`skills/team.md`](skills/team.md)；各角色依指定輸入完成自己的階段，root 負責全程整合與交付。

## 六份角色權威卡

- [Tech Lead](tech_lead.md)：技術決策、架構與風險評估。
- [Data Audit](data_audit_agent.md)：資料完整性、一致性與品質證據。
- [Data Cleanup](data_cleanup_agent.md)：清理目標、依賴及復原性盤點。
- [Execution](execution_agent.md)：已授權的實作、驗證與所需交付同步。
- [Documentation](documentation_agent.md)：覆蓋分析、文件修訂與一致性。
- [Testing / QA](testing_qa_agent.md)：測試路由、QA 計畫與結果判讀。

角色卡格式一致：觸發、輸入、輸出、授權邊界、完成條件與交接。它們不重複共用安全規範或固定必讀長清單。

## 其他入口

- [Git 排除清單](git_exclusions.md)：Stage／commit 前閱讀。
- [多 Agent 協作流程](multi_agent_workflow.md)：分支、工作樹與整合邊界。
- [Antigravity 適配入口](antigravity/README.md)：平台差異、角色適配及交接模板。
- [Shared state 使用與遷移](shared_state/README.md)：以 task ID 隔離的本機任務狀態及既有 singleton 的所有權規則。
- [Coverage Map](../00_core/DOC_COVERAGE_MAP.md)：文件同步範圍；任務工作流見 `PRODUCT_CHANGE_WORKFLOW.md`。

## 更新記錄

- 2026-10-12：縮為共用規則、Snapshot、唯一角色路由及必要協作入口。
