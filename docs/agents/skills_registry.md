# baldr 角色路由

> 本頁是唯一人類可讀的角色路由入口。六份 `docs/agents/*.md` 是各角色行為權威；`ROLE_ROUTING.json` 是供 `scripts/document_control.py route` 使用的機器可讀投影，兩者由同一規則維護。若工具回報 `needs_classification`，由 root 根據任務與影響範圍分類，不猜選角色。

## 先載入

所有任務先讀：

1. `docs/agents/shared_context.md`：共同安全與工程規範。
2. `docs/00_core/PROJECT_SNAPSHOT.md`：目前狀態摘要與當前風險。
3. 本頁：選擇任務需要的角色，再讀其權威卡。

多階段、需交接或跨多角色的任務另讀 `docs/agents/skills/team.md`。產品、工程、架構、目標設計及操作文件按任務條件載入，遵循根目錄 `AGENTS.md` 的 Scoped SSOT 導航。

## 角色選擇

| 任務訊號 | 主要角色 | 權威卡 |
|---|---|---|
| 技術選型、架構邊界、風險、是否該做 | Tech Lead | `docs/agents/tech_lead.md` |
| SQLite／CSV／原始資料完整性、來源比較、品質 | Data Audit | `docs/agents/data_audit_agent.md` |
| 刪除、搬移、清理或依賴精簡的影響盤點 | Data Cleanup | `docs/agents/data_cleanup_agent.md` |
| 已授權的功能實作、修錯、UI／測試修改 | Execution | `docs/agents/execution_agent.md` |
| 文件覆蓋、索引、手冊及專題文件同步 | Documentation | `docs/agents/documentation_agent.md` |
| 測試路由、QA 計畫、健康檢查或結果判讀 | Testing / QA | `docs/agents/testing_qa_agent.md` |

任務可由同一位 Agent 依序戴上多個角色處理；這是預設方式。只有使用者或適用指令明確授權獨立 subagent 時才委派，並為其指定有限輸入、輸出與檔案範圍。Root 始終是任務負責者，負責整合與交付，不因委派而轉移責任。

以下 `kind` 是文件工具的選擇值，不是另一套路由規則。完整條件與角色組合以 `ROLE_ROUTING.json` 為準；可使用 `scripts/document_control.py route --kind ... --request ...` 初判，再用 `--changed-file` 納入實際變更影響：`query`、`documentation`、`implementation`、`ui`、`data_audit`、`data_write`、`architecture`、`cleanup`、`bootstrap`、`release`。未分類或條件衝突時停止自動選擇，交由 root 裁決。

## 必要複核

Root 對 Scope、風險複核、驗證狀態與最終交付負責。依實際風險加入複核角色：

- 介面、模組邊界、資料流或目標設計改變：Tech Lead 在實作前審查設計；契約實際改變時再核對整合影響。
- 資料來源、品質、SQLite／CSV 一致性：Data Audit 提供唯讀證據；任何寫入另須明確授權與 Execution 的受控變更。
- 刪除、搬移或依賴清理：Data Cleanup 先交付精確盤點、引用與復原路徑；Execution 只執行已授權項目。
- 實作／UI／資料寫入等變更 kind：按 `ROLE_ROUTING.json` 保留 Testing / QA 與 Documentation 覆蓋階段；它們依實際影響判定所需驗證及文件修訂，無須擴成六角色全開。
- 其他使用流程或專題文件改變：依實際影響加入 Testing / QA、Documentation 或其他角色，並按文件覆蓋地圖完成同步。
- 高風險變更或發布交付：Root 確認指定複核、證據、未解風險及 Git 範圍都齊備後才交付。Stage／commit 前讀 `docs/agents/git_exclusions.md`。

路由要求的角色需完成其適用覆蓋判定；覆蓋判定可得出不需額外測試或文件修訂。角色不因跨階段而延後已授權範圍內的必要 QA 或文件同步。共享硬規則見 `docs/agents/shared_context.md`；協作步驟見 `docs/agents/skills/team.md`。

## 更新記錄

- 2026-10-12：收斂為唯一人類路由入口，明確區分同一 Agent 分階段履職、明確授權的 subagent，以及 root 的持續責任。
