# 功能文檔目錄

> **系統功能相關文檔**

本目錄包含系統的功能說明和使用指南。

## 依工作區查找 UI 契約

[UI 功能文件](UI_FEATURES_DOCUMENTATION.md)先按目前九個工作區列出互動契約、搜尋詞與手冊入口；操作步驟與安全限制以手冊為準，模組責任見[目前架構分冊](../01_architecture/current/README.md)，目前狀態與 QA 範圍分別見 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 與[產品 UX QA 索引](../06_qa/PRODUCT_UX_QA_INDEX.md)。

| 工作區 | UI 契約 |
|---|---|
| 決策工作台 | [決策工作台](UI_FEATURES_DOCUMENTATION.md#workspace-decision-workbench) |
| 市場探索 | [市場探索](UI_FEATURES_DOCUMENTATION.md#workspace-market-exploration) |
| 推薦分析 | [推薦分析](UI_FEATURES_DOCUMENTATION.md#workspace-recommendation) |
| 策略回測／Research Lab | [策略回測](UI_FEATURES_DOCUMENTATION.md#workspace-backtest-research-lab) |
| 觀察清單 | [觀察清單](UI_FEATURES_DOCUMENTATION.md#workspace-watchlist) |
| 個股研究 | [個股研究](UI_FEATURES_DOCUMENTATION.md#workspace-stock-research) |
| 持倉管理 | [持倉管理](UI_FEATURES_DOCUMENTATION.md#workspace-portfolio-management) |
| 數據更新 | [數據更新](UI_FEATURES_DOCUMENTATION.md#workspace-data-update) |
| Runtime Observatory | [Runtime Observatory](UI_FEATURES_DOCUMENTATION.md#workspace-runtime-observatory) |

## 📄 文檔列表

- **`UI_FEATURES_DOCUMENTATION.md`**
  - UI 行為、各 Tab 功能與參數的參考文件
  - 不作逐步操作權威；使用步驟、結果判讀、安全限制與排錯以 Application Manual 為準

- **`USER_GUIDE.md`**
  - 推薦、回測與資料治理的進階專題教程
  - 數據更新工作台、推薦分析、策略參數最佳化、Walk-forward 驗證等；不取代目前操作手冊

- **`../07_guides/APPLICATION_MANUAL.md`**
  - 使用者操作的唯一權威：目前 9 個頂層工作區的完整操作手冊
  - 安裝、操作、參數、結果判讀、安全限制與排錯

- **`BACKTEST_LAB_FEATURES.md`**
  - 策略回測標籤的完整功能說明

- **歷史回測 Lab 清單與 FAQ**
  - 舊功能清單含已過期的待實作狀態，舊 FAQ 保留早期資料路徑與操作建議；兩份原文已移至[歷史封存](../09_archive/README.md#2026-10-08-backtest-lab-checklist-and-faq-snapshots)，不作目前功能或操作依據。

- **`SCORE_EXPLANATION.md`**
  - 評分系統說明
  - buy_score 與 sell_score 的詳細說明

- **`STRATEGY_DESIGN_SPECIFICATION.md`**
  - 策略設計規格書
  - Baseline Score Threshold Strategy 的完整設計規格

- **Research Run Registry 設計規格（2026-06-14，歷史）**
  - [封存原文](../09_archive/RESEARCH_RUN_REGISTRY_SPEC_2026_06_14_HISTORY.md)：Month 1 schema／API 提案，只保留設計脈絡，不是現行契約。
  - 目前功能看 [Backtest Lab 功能文件](BACKTEST_LAB_FEATURES.md)、[系統架構](../01_architecture/system_architecture.md)、[Application Manual](../07_guides/APPLICATION_MANUAL.md)、[`ResearchRunService`](../../app_module/research_run_service.py) 與 [`ResearchRunRepository`](../../app_module/research_run_repository.py)。舊檔名路徑保留相容導引。

## 🔗 相關目錄

- `../00_core/` - 核心文檔
- [歷史 Phase 文件目錄](../05_phases/README.md)
- `../strategies/` - 策略文檔

