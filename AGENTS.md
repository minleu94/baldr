# baldr 共用 Agent 入口

本檔是 Codex 自動讀取入口。跨平台共用安全與工程硬規則唯一來源為 [`docs/agents/shared_context.md`](docs/agents/shared_context.md)；角色路由唯一人類入口為 [`docs/agents/skills_registry.md`](docs/agents/skills_registry.md)。

## 開工順序

1. 閱讀 `docs/agents/shared_context.md` 的共同安全規則。
2. 閱讀 `docs/00_core/PROJECT_SNAPSHOT.md` 的目前狀態摘要與當前風險；日期化交接只在任務涉及該主題時讀取。
3. 依 `docs/agents/skills_registry.md` 選角色並閱讀對應權威卡；多階段或需交接的工作遵循 `docs/agents/skills/team.md`。
4. 產品方向、工程優先序、架構、目標設計與使用者操作依任務範圍讀取各自 Scoped SSOT。文件同步依 `docs/00_core/DOC_COVERAGE_MAP.md`、`docs/00_core/FEATURE_DOCUMENT_MAP.json` 與 `docs/00_core/PRODUCT_CHANGE_WORKFLOW.md`。
5. Stage 或 commit 前閱讀 `docs/agents/git_exclusions.md`。

閱讀時沿[任務上下文流程](docs/00_core/PRODUCT_CHANGE_WORKFLOW.md#任務上下文與漸進閱讀)使用既有 `document_control context`：先定位路徑／標題／symbol，依 Level 0–4 深入。Feature Map／Manifest 由工具處理，不全文載入；Context 不取代共用硬規則、正文與原始 QA。閱讀領域不等於履職 kind，`--inspect-file` 不等於修改範圍，Unknown／預算略過須明示。

## 條件式權威文件

- 產品能力、產品 Gate、現行資料來源優先序：`docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md`。
- 六個月工程順序：`docs/00_core/ROADMAP_6M_ENGINEERING.md`；長期版本階梯或舊工作承接另讀對應 roadmap。
- 現行模組邊界與資料流：`docs/01_architecture/system_architecture.md`；目標領域背景與目標實作設計依任務讀 `target_system_architecture.md` 及 `target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md`。
- UI、操作流程、參數、結果判讀或安全限制：依 `docs/07_guides/README.md` 的操作手冊章節地圖，讀取 `APPLICATION_MANUAL.md` 相關章節。
- 外部專案或候選資料源研究：`docs/00_core/EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md`。
- Obsidian vault 導覽、文件關聯圖、Canvas 或 Properties：讀取 [baldr-obsidian-workflow](.agents/skills/baldr-obsidian-workflow/SKILL.md)；產品狀態與契約仍以各自 Scoped SSOT 為準。

## 載入與文件責任

- Codex 原生任務入口為 [baldr-product-workflow](.agents/skills/baldr-product-workflow/SKILL.md)，按任務載入共同流程；Skill 是薄調用入口，不另定義角色或授權。
- Codex 依本檔載入共用入口；`docs/agents/*.md` 是權威角色卡，`skills_registry.md` 是唯一人類角色路由入口。
- `GEMINI.md` 僅處理 Gemini CLI／Antigravity 的平台差異；`.agent/rules/*.md` 是具有效 trigger 的按需適配，不得複製共同硬規則或完整必讀清單。
- 修改程式或使用者可見行為時，依已授權範圍完成必要 QA 與文件同步；不得把未執行項目寫成已通過。高風險複核與交付由 root 負責。
- 多階段任務狀態使用 `output/tasks/<task_id>/task.json`；遷移與並行寫入規則見 `docs/agents/shared_state/README.md`。

## 專案入口

- 主要 UI：`ui_qt/main.py`。
- 資料根目錄：由 `data_module/config.py` 的 `TWStockConfig` 管理，預設 `D:/Min/Python/Project/FA_Data`，可由 `DATA_ROOT` 覆蓋。
- 本機產出、正式資料、量化精度、未來函數、Python 驗證程序、Git 與未提交變更等硬規則一律以 `docs/agents/shared_context.md` 為準。
