# 文件產品化與 Agent 交付流程整合計畫

> 任務：`documentation-productization-20261012`。基線：`b834f6116dff8316d45dae7c704f260738896325`。使用者於 2026-10-12 授權實作、判定文件刪移並記錄、完成後提交至目前 `dev`；未要求推送或發布。

## 成果與驗收

| 工作 | 必須成立的成果 | 驗收方式 |
|---|---|---|
| 產品入口 | README 說明用途、主要流程與開始方式，連到可閱讀的現況、目標、架構、操作、移機 | 從根入口走讀；有效連結與正文核對 |
| 現況／架構／操作 | 原日期化紀錄退出初級正文；現行契約按主題可查，Current 與 Target 分開 | 原件 SHA、章節處置映射、功能關聯與內容審查 |
| Agent 流程 | 六角色短卡、唯一路由、按任務載入、總負責者與條件式複核 | 路由案例、角色引用、平台入口与獨立子 Agent 前測 |
| 文件同步 | 功能→需求／契約／程式／測試／操作／QA／狀態可達；開工與交付皆有 coverage | 關聯地圖、task.json 檢查、故意缺件負例 |
| 安裝移機 | fresh 與 owner-migration Prompt、可核對清冊、排程及時區差異、回滾／自然驗收界線 | 隔離清冊計畫、缺件／重複／衝突案例；不啟動正式 writer |
| 可重跑工具 | route、init-task、check、bootstrap-plan 可實際執行；不寫市場、模型或排程 | root 有界序列執行測試與 CLI；語意由來源審閱 |
| 整理與提交 | 逐檔保留／替換／主題拆分／刪除判定、來源與替代入口；只提交本任務 | 處置 manifest、archive 指紋、diff、commit tree |

文件整理的完成不代表全部產品 Gate 或自然排程已驗收。既有 PASS、FAIL、unknown、candidate／shadow 與正式資料安全邊界保持。

## 範圍與所有權

- `agent_workflow`：根 Agent 指令、六角色、Team／共用規則、平台適配；不改既有任務 singleton。
- `core_documents`：Snapshot、產品與工程方向、目前／目標架構導覽及目前架構主題分冊。
- `onboarding_operations`：README／Navigation／Inventory、日常操作、安裝／移機及排程使用文件。
- root：路由 JSON、功能關聯、工作流、工具與測試、原件／處置清冊、索引同步、審閱、驗證與提交。

子 Agent 均使用 Luna Max；最多同時三個，優先沿用。只做靜態讀取與候選編輯；Python 驗證由 root 按共用資源限制序列執行。不得覆寫他人變更。

## 原件與恢復

原件先保存於 `docs/09_archive/documentation_productization_20261012/originals/<原相對路徑>`。原 bytes 不加標頭、不改寫歷史結果。最終處置 manifest 只保留本次確實改動且需要恢復的原件；未使用的本輪副本可移除並記錄原因。封存原件的相對連結按原路徑語境解讀；現行入口另由 manifest 指向替代正文。

本機操作與 raw QA 在 ignored `output/doc_productization/`、`output/tasks/documentation-productization-20261012/` 保存。舊 `shared_state/active_task.yaml`／`handoff_log.md` 的既存工作由原 owner 維護，本次不覆寫。新的任務紀錄採不同 task ID，與產品狀態及正式 QA 分離。

## 執行順序

1. 保存基線與原件，檢查工作樹所有權。
2. 分工重整正文；root 建立路由／功能關聯／工作流與工具。
3. root 審查、修復引用與章節落點，完成處置 manifest。
4. 執行結構與行為檢查，獨立前測及負例；保留未驗證的 host 安裝／自然排程限制。
5. 核對所有成果及原件 SHA，完成正式 QA 摘要與索引，精確路徑提交。

## 執行紀錄

- 2026-10-12：三個 Luna Max 沿用完成入口、核心及 Agent 分工與獨立完整性／前測審查。71 份預備原件逐 bytes 核對，57 份保留、14 份未使用副本移除並記錄；51 行為案例、型態、語法、Skill 格式與 7 項清冊／CLI 核對通過。正式資料與其他任務保持；提交前以隔離 Git index 核原件與本任務完整正文，最後交付至 `dev`。
