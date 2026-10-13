---
name: baldr-product-workflow
description: "在 baldr repository 開發、修復、整理文件、驗證功能或安排首次安裝與移機時，依任務影響選擇專案角色並完成測試、文件同步及交接。"
---

# baldr 產品工作流程

先依 repository 的 `AGENTS.md` 與使用者授權工作。本 Skill 是調用入口；共同規則及角色權威仍保存在 repository。

1. 讀 [角色路由](../../../docs/agents/skills_registry.md)，由總負責者依實際目標明示任務類型。可用 `scripts/document_control.py route --kind <類型> --changed-file <相對路徑>` 取得必要角色與風險檢查。混合文字辨識不明時自行核對需求與上下文；不能把提示當成授權。
2. 載入本次必要角色卡及 [Team 流程](../../../docs/agents/skills/team.md)。不要讀取所有歷史、每張角色或所有功能文件。以[功能關聯](../../../docs/00_core/FEATURE_DOCUMENT_MAP.json)找到相關契約、操作及測試。
   若任務要用 Obsidian 整理 vault、檢查文件關聯或建立 Canvas，再讀同層的 [baldr-obsidian-workflow](../baldr-obsidian-workflow/SKILL.md)；不要因此改動產品 SSOT 的責任邊界。
3. 在授權範圍內完成必要實作、驗證與文件同步，依 [產品變更流程](../../../docs/00_core/PRODUCT_CHANGE_WORKFLOW.md)記錄 Coverage。純說明任務按其證據交付，不執行無關寫入。
4. 中大型或需交接任務以唯一 task ID 建立 `output/tasks/<task_id>/task.json`；不覆寫其他任務的 singleton。工具 `check --task <相對路徑>` 只核結構，總負責者須另外審閱正文及真正證據。
5. 依使用者授權與可用能力安排獨立 Agent，記錄實際調用及回報。角色切換不等於已經有另一位 reviewer。未完成事項保留安全接手點，不以局部 PASS 宣稱完整產品或自然排程通過。

首次安裝或移機時讀 [Prompt](../../../docs/07_guides/FIRST_INSTALL_PROMPT.md)及 [Runbook](../../../docs/07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md)。`bootstrap-plan` 只產出核對計畫，不註冊、啟用或觸發排程；真正執行依已核清冊、契約及使用者授權。
