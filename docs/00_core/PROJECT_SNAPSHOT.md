# PROJECT_SNAPSHOT（目前狀態）

> 更新基線：2026-10-12 接手版本 `b834f6116dff8316d45dae7c704f260738896325`。狀態由[10/11 補完 QA](../06_qa/BALDR_COMPLETION_PROGRESS_20261011.md)及[恢復交接](../agents/shared_state/BALDR_COMPLETION_RESUME_PROMPT_20261012.md)支持；後續進展按具名較新收據更新。局部 PASS 不代表整包或產品 Gate 完成。

## 現在有哪些入口

Baldr 有九個本機工作區，主程式入口是 `ui_qt/main.py`。以下依日常目的選擇入口；可操作不代表來源、候選版本或投資效果已驗收。

| 你的需求 | 可用入口 | 判讀限制 |
|---|---|---|
| 整理行情、確認資料日期 | 數據更新、資料狀態檢查 | 缺庫、缺表與日期落後分開判讀；來源資格未知時保留 unknown。 |
| 了解市場與個股 | 市場探索、個股研究 | 原始排名、來源與品質各自保留；unknown 不當成零。 |
| 比較候選與策略 | 推薦分析、策略回測／Research Lab | 歷史研究與 Paper 不代表正式投資有效或可交易。 |
| 保存名單、檢查持倉 | 觀察清單、持倉管理 | 真實帳務、聲明持倉與研究 Paper 帳分開；重開依精確保存來源判讀。 |
| 找日常重點、排查系統 | 決策工作台、系統狀態 | 顯示與導航不授自動交易、模型 promotion 或資料 writer 權限。 |

## 工程狀態與限制（接手基線）

| 項目 | 目前可支持的判讀 |
|---|---|
| P08 前向候選旅程 | 指定凍結候選為 **5 PASS／21.89 秒／native 0**；只支持該合成候選及其收據範圍，不代表最新版正式來源、完整 P08、績效或 Gate 已接受。 |
| P01 篩選效能 | 最新可用篩選 p95 為 **446.3604 ms**，未達原嚴格 `<300 ms` 門檻；不能宣稱 P01 效能 Gate 通過。 |
| Main lease 旅程 | 曾於 producer 期間發生 Windows native access violation（exit `3221225477`），未到 fresh 階段；根因仍未確認，該旅程不接受。 |
| M25／M26 | M25 closure 尚有 Phase3C CLI stale source，`execution_ready=false`；M26 僅待受限 CLI 重封與 focused regression 核對，不能當成已完成或可執行。 |
| Health 正式整合 | 合成／局部 QA 不等於正式提升；候選尚未套用，正式 UI、validator、型態與語法驗證仍待。 |
| 整體範圍 | 補完仍涵蓋 P00–P14、M1–M3、F01–F23、UX01–UX24、G0–G4；尚無完整工作包或產品 Gate 接受。 |

詳細證據、適用版本、原始失敗及安全接手順序請回到上述具名 QA 與恢復交接文件。本 Snapshot 提供產品入口與上述接手版本的受限狀態摘要，不把歷史日期流水複製成另一份權威。

## 產品與系統入口

- **產品方向與來源優先序**：[PRODUCT_ROADMAP_POST_REFACTOR](PRODUCT_ROADMAP_POST_REFACTOR.md)。產品 Gate 定義產品能力與接受證據，不是完成狀態。
- **目前架構**：[system_architecture](../01_architecture/system_architecture.md)及[目前架構分冊](../01_architecture/current/README.md)。
- **目標架構設計**：[FINAL_TARGET_ARCHITECTURE](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) 是目標實作設計唯一權威，不作 current 完成證明。
- **UI**：主程式為 `ui_qt/main.py`，共有九個頂層工作區；Daily Decision Desk 位於「市場探索 > 市場總覽」。完整操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。
- **正式資料路徑**：由 `data_module/config.py` 的 `TWStockConfig` 管理；`DATA_ROOT` 預設 `D:/Min/Python/Project/FA_Data`，SQLite 主要檔為 `<DATA_ROOT>/sqlite/twstock.db`。不得依 repo 相對目錄推定正式資料位置。

## 重要限制

- 不覆寫或刪除正式 raw data；所有來源候選、PIT、時間戳與 gate 原門檻照原收據判讀。
- 金融核心使用 Decimal 或整數單位；策略、回測、Recommendation、Portfolio 與 Exit 實作須先做 look-ahead 自查。
- Historical replay、readiness、dry-run、shadow、paper 與局部 UI／後端 PASS 不代表 forward／live evidence 或產品接受。
- Investment Advice 不授權 broker execution、自動平倉或自動策略升降級。

歷史快照與逐輪驗收原文已由文件治理封存在 [documentation_productization_20261012/originals](../09_archive/documentation_productization_20261012/originals/)；封存版本只供追溯，不能覆蓋本頁或最新具名 QA 收據。
