# 文件覆蓋與同步規則

本頁定義每類變更必須核對的正文與交付條件。實際任務依[產品變更流程](PRODUCT_CHANGE_WORKFLOW.md)，角色依[路由](../agents/skills_registry.md)，文件位置依[索引](DOCUMENTATION_INDEX.md)。日期化處置另存[Coverage History](../09_archive/DOC_COVERAGE_HISTORY_2026.md)。

## 各種資訊保存在哪裡

| 主題 | 權威 |
|---|---|
| 目前狀態、優先事項與限制 | [Snapshot](PROJECT_SNAPSHOT.md) |
| 產品能力、成立條件、來源優先序 | [Product Roadmap](PRODUCT_ROADMAP_POST_REFACTOR.md)，來源優先序§11 |
| 近期工程依賴、交付與Exit Criteria | [6M](ROADMAP_6M_ENGINEERING.md) |
| 長期產品成熟度 | [V2.1–V4.0](VERSION_ROADMAP_V2_1_TO_V4_0.md) |
| 外部參考與候選研究 | [External Blueprint](EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md)，不決定現行來源接受 |
| 舊工作處置 | [Legacy Carryover](LEGACY_ROADMAP_CARRYOVER.md) |
| 現行責任、資料流與技術契約 | [目前架構](../01_architecture/system_architecture.md)及current分冊 |
| 目標背景／目標設計 | [Target導覽](../01_architecture/target_system_architecture.md)／[FINAL](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) |
| North Star、原則與成功標準 | [System Vision](../01_architecture/system_vision_specification.md) |
| 操作、參數、判讀、安全與排錯 | [Manual](../07_guides/APPLICATION_MANUAL.md)及manuals分冊；維運依適用Runbook |
| 角色與共同硬規則 | [角色／路由](../agents/skills_registry.md)、[shared context](../agents/shared_context.md) |
| 固定版本、日期與scope的驗收 | [QA](../06_qa/README.md)與具名原收據 |
| 位置／生命週期 | [Index](DOCUMENTATION_INDEX.md)／[Structure](DOCUMENTATION_STRUCTURE.md) |

同一功能涉及多種資訊時各自更新其owner；其他文件引用正文，不重複一份會漂移的狀態表。工程完成、功能可操作、正式資格、自然成熟與產品接受不能互相推論。

## 變更與必須核對的文件

| 變更 | Must：完成有必要的正文修訂 | 條件式檢查 |
|---|---|---|
| 使用者操作、入口、參數、結果或安全限制 | Manual對應主題、功能文件、適用測試與指南 | 狀態改變更新Snapshot；資料流改變更新架構 |
| 策略、推薦、回測、Portfolio、Exit | owner契約、操作／結果判讀、來源與量化防線、具名QA | 方向改變才改Product；接受狀態改變才改Snapshot |
| API、DTO、依賴或資料流 | 架構相應主題、導航、契約與測試 | 目標設計改變同步FINAL；不把current寫成target-only |
| 格式、根路徑、source／SQLite讀寫、availability | 資料文件、架構分冊、操作／維運與QA | 安裝受影響同步bootstrap；來源接受改變更新Snapshot |
| 排程、模型、私人資產設定或恢復 | 排程／移機Runbook、CLI、資產用途、安全及驗收 | 自然run與模型資格按原scope收據，不以設定完成升格 |
| 狀態、目前優先事項、阻礙 | Snapshot與支持該主張的具名來源 | 6M／Product／Version僅在其標準或順序改變時更新 |
| 新增、拆分、刪移或改權威 | 領域索引、處置紀錄、入站引用與anchor | 主入口或跨領域權威改變再更新中央Index |
| Agent角色、工作流或平台適配 | 共同角色／路由、根入口、薄適配及行為案例 | 不複製安全規則與必讀清單或另建平行權威 |
| 不改行為的小修或純內部重構 | 明示影響分析與適用驗證 | 操作／契約確未改時可記not_required及理由 |

README只在產品用途、主要流程或開始方式改變時修訂；Roadmap Hub只在導航變化時修訂。一次QA log不貼進所有概覽。

## 開工與交付Gate

按[功能地圖](FEATURE_DOCUMENT_MAP.json)及實際diff列Coverage。地圖以九工作區穩定key與平台流程作查找入口，code／tests是代表入口，完整功能及測試沿領域契約與QA清冊核對。未匹配的新增功能由owner分類並補關聯，不能直接判為沒有文件影響。

完成前逐項記錄 updated 或 not_required＋具體理由；pending、失敗、無證據或仍有待辦不能標done。驗證記錄 passed／failed／not_run／not_required，免驗理由與實際scope須可核對；JSON與命令契約以 scripts/document_control.py 為準。

check可核路由、關聯、連結／anchor、task Coverage及驗證紀錄，不能證明正文語意或某測試真通過。Root另閱diff、正文與receipt，必要時獨立review。共同強制QA與資源限制依shared context，本頁不維護第二套命令。

Feature Map列出的每個code／tests入口須命中所屬feature的同步pattern；共用檔案逐feature核對，不能由其他feature的pattern遮蔽。已登記冷封存由[資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md#查詢已登記的冷封存)與機器清冊追蹤，check另列外部引用及可用性，不把ignored證據重報為新失管檔案；這不替代原內容SHA或產品驗收。

閱讀範圍使用既有工具的 `context`／`trace`，HEAD／工作樹增量用 `inventory`；新增或更改閱讀 selector／Issue metadata 時執行 `check --context-metadata`。用法與 Level 0–4 的界線集中於[任務上下文](PRODUCT_CHANGE_WORKFLOW.md#任務上下文與漸進閱讀)，不將閱讀清單當成必要同步清單。

### Manual完整性

- 工作區入口與前置條件清楚。
- 步驟、參數、保存／讀回與取消可查。
- 日期、來源、品質、unknown／missing與警告有判讀。
- 寫入範圍、安全限制、常見失敗與排錯可查。
- 安裝、進階研究與維運連到相應指南，日常正文沒有逐輪流水。

## 證據與歷史

搬移前保存原bytes、SHA與原路徑，處置清冊記原因、目前落點與恢復。唯一plan或原失敗receipt不能因ignored／dated就刪除；private／raw evidence按Git exclusion保存並另作備份。QA截图不在repo時明示可重驗限制。

以前全庫EOF覆核是[日期化治理基線](DOCUMENT_GOVERNANCE_STATUS_MATRIX_20261011.md)，不代表本次重新覆核全庫。本輪處置與驗收見[原件](../09_archive/documentation_productization_20261012/README.md)、[驗收](../06_qa/DOCUMENTATION_PRODUCTIZATION_ACCEPTANCE_20261012.md)。
