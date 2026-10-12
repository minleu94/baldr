# Team 任務工作流

> 本文件定義從接案到交付的單一流程，不另建角色路由或複製共用安全規則。角色選擇看 [`../skills_registry.md`](../skills_registry.md)，硬性安全規範看 [`../shared_context.md`](../shared_context.md)。Root 是每個任務的總負責者。

## 任務流程

### 1. Intake：理解任務並分類

- 用一段話寫出預期結果、驗收方式、Scope In／Out、平台／資料／Git 限制與已有工作區變更。
- 以 `scripts/document_control.py route --kind <kind> --request <request>` 初判；已知實際影響後補 `--changed-file <path>`。kind 與組合見 `ROLE_ROUTING.json`；`needs_classification` 或條件衝突時由 root 分類。
- 依 `skills_registry.md` 選適用角色，不全數啟用。預設同一 Agent 依序履行所需角色；只有明確授權時才委派獨立 subagent。
- 多階段、需恢復或交接的工作由 root 執行 `scripts/document_control.py init-task`，狀態存於 `output/tasks/<task_id>/task.json`；詳見 `shared_state/README.md`。不自動碰觸舊 singleton。

### 2. 影響分析與 QA 計畫

- Root 核對實際差異、依賴與範圍，再用 `FEATURE_DOCUMENT_MAP.json`、`DOC_COVERAGE_MAP.md`、測試路由及相關 Scoped SSOT 找出受影響的程式、文件、Manual、QA 與證據入口。
- 按 `ROLE_ROUTING.json` 完成該 kind 的必要角色覆蓋；再按實際影響設定額外複核。覆蓋判定可以得出不需新增測試或文件修訂，並記下驗收門檻及證據來源。
- 形成可執行的 QA 計畫：要驗證的行為、測試／手動檢查、執行環境、資源或資料限制、通過條件。未要求改程式的純查詢或文件任務，依範圍記錄不適用理由。
- Coverage Pass 是文件修訂的定位步驟。當原任務已授權完成該範圍時，直接安排 Patch Pass，不再為已授權的必要同步要求重複確認。

### 3. 實作

- Execution 僅修改核准 Scope，保持既有契約與架構；如發現需擴大範圍，先交 root 判斷。
- Data Audit 提供資料證據，Data Cleanup 提供精確候選與依賴盤點，Tech Lead 提供設計／風險決策；這些輸出本身不等於寫入或刪除授權。
- Root 持續掌握狀態、變更檔案與風險；委派工作回到 root 整合，不能把最後責任轉出。

### 4. 驗證

- Testing / QA 按影響分析執行或確認 QA 路由，結果逐項記為 pass、fail、not_run 或 not_applicable，附必要證據。
- Execution 修復本次範圍內可修復的失敗並重新跑適用檢查；不得隱藏失敗、放寬原門檻或將局部結果外推成產品整體接受。
- 高負載 Python 驗證由 root 依 `shared_context.md` 序列執行並確認程序終態。未執行的測試如實標示原因與風險。

### 5. 文件同步

- Documentation 依 feature map、Coverage Map 與 `PRODUCT_CHANGE_WORKFLOW.md` 完成受影響文件；Execution 已授權的實作交付包含所需同步，不只回報文件清單。
- 使用者可見的操作、參數、結果判讀、安全限制或排錯有變化時，更新 `APPLICATION_MANUAL.md` 相應章節及領域導航。
- Root 確認文件內容有實際程式／QA 證據支持，現況、產品方向、架構、目標設計與歷史敘述沒有混用。

### 6. 整合與交付

- Root 確認 diff 僅含本任務範圍、所有必要風險複核與 QA／文件交付已完成，並列出變更、驗證結果、未完成事項與限制。
- Stage／commit 只有在授權範圍內進行；操作前讀 `docs/agents/git_exclusions.md` 並核對工作區。整合不自動授權 push、發布或分支／工作樹清理。
- 任務需暫停或交接時，root 更新本 task 的 `task.json` 與交接摘要，說明目前狀態、已讀／改檔、驗證、阻塞與安全接手點。

## 必要交付欄位

交付摘要至少包括：任務與 Scope、角色／複核、變更檔案、QA 計畫及實際結果、文件同步、未完成事項、工作區／Git 狀態、下一步或安全接手點。不得把未讀、未跑或未修正項目標成完成。

## 更新記錄

- 2026-10-12：整合為 Intake → 影響與 QA 計畫 → 實作 → 驗證 → 文件 → root 整合交付的單一任務流程。
