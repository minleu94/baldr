# Superpowers Specs / Plans 目錄

> **最後整理**：2026-10-09
> **定位**：本目錄保存 Superpowers 流程產生的設計規格、實作計畫與 execution artifacts。既有文件通常是歷史追溯資料；目前例外是已由 Snapshot／Index 明確接續的 [Baldr 產品補完計畫](plans/baldr_product_completion_plan_20261006.md)，其工作狀態仍以 Snapshot 與對應 QA 為準。

目前專案的狀態與方向仍以 scoped authority 判讀：

- 目前狀態、本週優先事項與高風險區看 [專案快照](../00_core/PROJECT_SNAPSHOT.md)。
- 未來 6 個月工程路線看 [6M 工程 Roadmap](../00_core/ROADMAP_6M_ENGINEERING.md)。
- V1.1–V2.0 已完成版本演進看 [歷史歸檔](../09_archive/VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md)。
- V2.0 之後的長期版號階梯看 [V2.1–V4.0 版本 Roadmap](../00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md)。
- 架構與模組邊界看 [目前系統架構](../01_architecture/system_architecture.md)。

## 子目錄

| 目錄 | 放什麼 | 判讀方式 |
|---|---|---|
| `specs/` | 功能或治理增量的設計規格、邊界、資料契約與非目標 | 歷史設計追溯；是否已完成仍以 Snapshot、QA closeout 與 Git closeout 為準。 |
| `plans/` | 實作計畫、工作拆分、驗收 gate 與文件同步清單 | 除非 Snapshot／Index 明確接續，否則視為歷史 execution trace；計畫本身不代表目前優先順序。 |
| `prompts/` | 一次性工作拆分與 handoff prompt | 歷史指派紀錄；不能直接當成現行工作授權。 |

## 主題閱讀入口

先依序看 [目前狀態](../00_core/PROJECT_SNAPSHOT.md)、對應的 scoped authority 與 [QA 主題地圖](../06_qa/README.md)，再按需要回查下表中的歷史 plan／spec。下表只降低找文件的成本，不代表其中計畫仍有效、已完成或獲得目前授權；165 份歷史文件的原路徑、實際位置與雜湊以 [archive manifest](../09_archive/SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md) 為準。已封存原文包括 13 份有具名 QA 證據的 Post-V1 plan/spec、1 份已完成的 Month 2 governance plan、4 份 Month 3 implementation plan 和 1 份設計規格、1 份 Month 4 Daily Decision Desk closure plan，以及 1 份已結案 Safe Refactor continuation plan、9 份 Month 3 Portfolio Replay implementation plans 及 1 份 closure audit、3 份已結案 V3 ML／UI polish plans 和 3 份配套 design specs，另有 1 份 TPEX daily-price backfill plan、1 組 financial float boundary plan/spec、1 份 documentation-roadmap rebaseline plan 與 1 組 Legacy Test Governance plan/spec。

| 主題 | 目前閱讀入口 | 可選的歷史 plan／spec | 判讀提示 |
|---|---|---|---|
| 研究 Lab 與 Registry | [Application Manual](../07_guides/APPLICATION_MANUAL.md)、[目前架構](../01_architecture/system_architecture.md)、[QA 主題地圖](../06_qa/README.md) | [Research Lab workbench plan](plans/2026-06-04-research-lab-workbench-v1.md)、[workflow redesign plan](plans/2026-06-04-research-lab-workflow-redesign.md)、[同名 redesign spec](specs/2026-06-04-research-lab-workflow-redesign.md)、[Month 2 registry／storage 歷史計畫](../09_archive/superpowers/plans/2026-06-14-month-2-parameter-run-storage-governance.md)；另有[Registry 設計規格](../02_features/RESEARCH_RUN_REGISTRY_SPEC.md) | plan 與 spec 分開保存；同名不代表內容重複，現行行為看 Manual、Architecture 與具名 QA。 |
| Month 3 Portfolio Replay／execution credibility | [目前架構](../01_architecture/system_architecture.md)、[Application Manual](../07_guides/APPLICATION_MANUAL.md)、[QA 主題地圖](../06_qa/README.md) | [Portfolio Replay 計畫群與 closure audit](../09_archive/README.md#2026-10-08-month-3-portfolio-replay-history)；[weight/exposure 原文](../09_archive/superpowers/plans/2026-06-15-portfolio-replay-weight-exposure.md) | 9 份 implementation plan 與 1 份 closure audit 原文均在 Archive。weight/exposure 有實作 commit，但最後 diff／stage 核取項目仍未勾；此差異保留，不推定有獨立 QA closeout。 |
| Factor Layer 與 Research Run 追溯 | [目前架構](../01_architecture/system_architecture.md)、[Registry 設計規格](../02_features/RESEARCH_RUN_REGISTRY_SPEC.md)、[QA 主題地圖](../06_qa/README.md) | [Factor Layer v1 設計規格](../09_archive/superpowers/specs/2026-06-14-month-3-factor-layer-design.md)、[實作計畫](../09_archive/superpowers/plans/2026-06-14-month-3-factor-layer.md)、[Research Run 整合計畫](../09_archive/superpowers/plans/2026-06-14-month-3-factor-run-integration.md)、[Factor Replay coverage plan](../09_archive/superpowers/plans/2026-06-15-month3-factor-replay-coverage.md)、[Recommendation factor feed plan](../09_archive/superpowers/plans/2026-06-15-month-3-recommendation-factor-feed.md) | 歷史契約與步驟只供追溯；現況依 Snapshot、Architecture 與現行 QA 判讀。原計畫保留未勾選的提交核准核取方塊，勿從 archive 推定授權。 |
| 策略評分與推薦 | [Score Explanation](../02_features/SCORE_EXPLANATION.md)、[Strategy Design Specification](../02_features/STRATEGY_DESIGN_SPECIFICATION.md)、[目前架構](../01_architecture/system_architecture.md) | [總治理 plan](plans/2026-06-13-strategy-scoring-governance.md)、[Backtest 切片](plans/2026-06-13-strategy-scoring-governance-a-backtest.md)、[Recommendation 切片](plans/2026-06-13-strategy-scoring-governance-b-recommendation.md)、[治理 spec](specs/2026-06-13-strategy-scoring-governance-design.md) | 文件只保留設計脈絡；是否進入正式評分或推薦，以現行實作與 QA 核對。 |
| ML 與前瞻證據 | [Architecture ML 閱讀路徑](../01_architecture/README.md)、[ML／Shadow QA 主題地圖](../06_qa/README.md) | [Historical ML Shadow MVP plan](plans/2026-07-13-historical-ml-shadow-mvp.md)、[外部證據主計畫](plans/2026-07-13-external-evidence-investment-validation-master-plan.md)、[外部證據 spec](specs/2026-07-13-external-evidence-investment-validation-design.md)、[V3 Score Effectiveness／ML Readiness 歷史 plan](../09_archive/superpowers/plans/2026-07-08-v3-score-effectiveness-ml-readiness.md) 與 [design spec](../09_archive/superpowers/specs/2026-07-08-v3-score-effectiveness-ml-readiness-design.md) | 7 月主計畫內的 Wave 授權文字是歷史記錄，不是目前任務授權；狀態及 Gate 看 Snapshot／現行登記。 |
| V1.5 Data Credibility／V1.9 Read-only Agent MCP | [目前狀態](../00_core/PROJECT_SNAPSHOT.md)、[目前架構](../01_architecture/system_architecture.md)、[QA 主題地圖](../06_qa/README.md) | [封存 plan/spec 導覽](../09_archive/SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md)；原路徑留有導引頁 | V1.5／V1.9 有具名 v1 closeout QA，但原計畫保留未勾項目，V1.9 的 pre-V2.0 後續驗收亦分開判讀；不把 closeout 擴張成外部來源採用、正式評分或 production scheduler 完成。 |
| 基本面與估值 | [Fundamental Source Inventory](../03_data/FUNDAMENTAL_SOURCE_INVENTORY.md)、[目前架構](../01_architecture/system_architecture.md)、[QA 主題地圖](../06_qa/README.md) | [估值資料層 plan](plans/2026-06-16-month5-valuation-data-layer-v1.md)、[估值呈現政策 plan](plans/2026-06-16-month5-valuation-presentation-policy.md) | 歷史計畫不代表資料覆蓋、PIT 可得性或估值已納入正式評分；依現行資料與 scoring contract 判讀。 |
| Portfolio 與 Watchlist | [Application Manual](../07_guides/APPLICATION_MANUAL.md)、[保存治理架構](../01_architecture/system_architecture.md)、[F4 Watchlist COW QA](../06_qa/README.md) | [Recommendation Portfolio optimization plan](plans/2026-05-26-recommendation-portfolio-optimization.md)、[Watchlist Trigger plan](plans/2026-06-15-decision-desk-watchlist-trigger.md) | 區分每日研究提示、Portfolio 政策與使用者 Watchlist 儲存；歷史轉換工程不等於已套用正式資料。 |
| UI readability／presentation history | [Application Manual](../07_guides/APPLICATION_MANUAL.md)、[目前架構](../01_architecture/system_architecture.md) | [UI readability polish 歷史資料](../09_archive/README.md#2026-10-08-ui-readability-polish-plans)，含 [plan/spec 導覽](../09_archive/SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md) | 歷史設計與核取結果只供追溯；目前使用者操作看 Manual，現況架構看 system architecture。 |
| TPEX 行情回補 | [Application Manual](../07_guides/APPLICATION_MANUAL.md)、[TPEX backfill QA](../06_qa/TPEX_SINGLE_DAY_PRECAPTURED_BACKFILL_2026_09_18.md) | [2026-06 原始計畫](../09_archive/superpowers/plans/2026-06-16-tpex-daily-price-backfill.md) | 原計畫記錄較早的 OpenAPI 補入流程；目前 custody、PIT 與 apply 操作依 Manual／後續 QA。 |
| 金融數值邊界治理 | [目前架構](../01_architecture/system_architecture.md)、[專案快照](../00_core/PROJECT_SNAPSHOT.md) | [已結案 plan/spec](../09_archive/README.md#2026-10-08-financial-float-boundary-governance-history) | 2026-06 的計畫與設計已封存；歸檔不代表金融數值防線停用。 |
| 測試收集與手動測試邊界 | [QA 主題地圖](../06_qa/README.md)、[最新測試清冊](../06_qa/TEST_INVENTORY_HEALTHCHECK_CLASSIFICATION_2026_06_23.md)、[manual tests README](../../tests/manual/README.md) | [Legacy Test Governance plan/spec](../09_archive/README.md#2026-10-08-legacy-test-governance-history) | 2026-06 遷移紀錄只供追溯；目前收集數量與測試分類依最新 QA 清冊。 |
| Recommendation Profile 與 Regime lifecycle | [Application Manual](../07_guides/APPLICATION_MANUAL.md)、[目前架構](../01_architecture/system_architecture.md)、[Full App healthcheck 歷史收據](../09_archive/FULL_APP_HEALTHCHECK_2026_06_16.md) | [Healthcheck Batch 3 plan](plans/2026-06-23-healthcheck-batch3-recommendation-profile-regime.md) | 實作已提交；原人工 QA 的 R-002–R-005 與 issue 001–004／008 仍標為「已修正待驗證」，不推定使用者重測完成。 |
| Safe Refactor／shim lifecycle | [目前架構](../01_architecture/system_architecture.md)、[shim／legacy removal QA audit](../06_qa/SHIM_LEGACY_REMOVAL_AUDIT_2026-07-12.md) | [已結案 Safe Refactor continuation plan](../09_archive/superpowers/plans/2026-07-11-safe-refactor-continuation.md) | 原文保留 Wave 6 核准與 release healthcheck 歷史證據；目前模組邊界看 system architecture。 |
| 資料更新與 UI 工作台 | [Application Manual](../07_guides/APPLICATION_MANUAL.md)、[UX／產品 QA 主題地圖](../06_qa/README.md) | [Data Update Workbench plan](plans/2026-05-20-data-update-workbench.md)、[設計 spec](specs/2026-05-20-data-update-workbench-design.md)、[非破壞 healthcheck runner](plans/2026-06-23-non-destructive-release-healthcheck-runner.md)、[Month 4 Decision Desk closure](../09_archive/superpowers/plans/2026-06-16-month4-daily-decision-desk-closure.md) | 操作以 Manual 為準；日期化 plan 和 healthcheck 分別代表設計、工程或驗收，不互相替代。 |
| Post-V1 Evidence Pipeline | [QA 主題地圖](../06_qa/README.md)、[Post-V1 QA receipts](../09_archive/README.md#post-v1-evidence-pipeline-qa) | [已執行 plan/spec 封存導覽](../09_archive/README.md#2026-10-08-post-v1-engineering-plans-and-specs) | 原始 plan/spec 與完成證據成組保存；現行操作看 Manual，狀態看 Snapshot。Scheduler Approval 配對文件保留原路徑，依其測試內容契約判讀。 |

下列歷史內容特別容易被搜尋後誤用，引用時先回到本 README 確認生命週期：

- [平行系統執行 master plan 原路徑](plans/2026-07-13-parallel-system-execution-master-plan.md) 與[工作流啟動 prompts 原路徑](prompts/2026-07-13-parallel-workstream-start-prompts.md)現為導引 stub；逐位元組原文分別保存在 [Archive plan](../09_archive/superpowers/plans/2026-07-13-parallel-system-execution-master-plan.md) 與 [Archive prompts](../09_archive/superpowers/prompts/2026-07-13-parallel-workstream-start-prompts.md)。這是 2026-07-13 的歷史任務拆分和工作指令，不代表已完成、目前優先序、工作授權或 Git commit／push 授權；現況看 Snapshot／Roadmap。
- [Plan/spec 日期與狀態稽核](../06_qa/SUPERPOWERS_PLAN_SPEC_DATE_AUDIT_2026_07_06.md) 是 7 月稽核收據；其中的 `Next Action` 保留當時結論，不是目前待辦。

## 維護規則

- 不刪除歷史 plan/spec/prompt 原文。13 份具名 QA 證據的 Post-V1 plan/spec（另含 V1.5、V1.9 兩組 closeout plan/spec）、1 份 Month 2 結案 plan、4 份 Month 3 implementation plan、1 份 Month 3 設計規格、1 份 Month 4 Daily Decision Desk closure plan、1 份已結案 Safe Refactor continuation plan、8 份 Month 3 Portfolio Replay implementation plans（步驟核取項目全勾）與 1 份 Month 3 closure audit、3 份已結案 V3 ML／UI polish plans 和 3 份配套 design specs，以及 2026-07-13 平行系統執行 master plan／啟動 prompts 的原文 bytes 保存在 `docs/09_archive/superpowers/{plans,specs,prompts}/`，原路徑留短導引；另有第 9 份 weight/exposure plan 已封存，但保留最後 diff／stage 核取項目未勾的原始狀態。完整 old→new、日期標籤、生命週期、QA evidence 與雜湊逐檔列於 [archive manifest](../09_archive/SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md)。其餘歷史文件保留原路徑，唯一目前進行中的 Baldr 計畫維持原入口。
- 檔名日期是里程碑或計畫日期，不一定等於完成日期；不依檔名推定完成。個別結果以 Snapshot、Roadmap、對應 QA 收據與 Git 記錄為準。
- 新增仍在推動中的 spec / plan 時，若會被日常引用，應同步加入 [文件索引](../00_core/DOCUMENTATION_INDEX.md)；完成或 superseded 後更新 manifest 的狀態與 evidence 路徑。
- 原始輸出、暫存報告與本機執行產物不應放入本目錄；需要保存結論時整理為 `../06_qa/` 摘要。

## 相關入口

- [文件索引](../00_core/DOCUMENTATION_INDEX.md) - 已納入索引的主要 spec / plan。
- [Plan/spec archive manifest](../09_archive/SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md) - 原路徑、封存目的地、bytes／SHA 與生命週期判讀。
- [Plan/spec 日期與狀態稽核（2026-07-06）](../06_qa/SUPERPOWERS_PLAN_SPEC_DATE_AUDIT_2026_07_06.md)。
- [歷史 push 前文件稽核（2026-07-06）](../09_archive/DOCUMENTATION_PRE_PUSH_AUDIT_2026_07_06_HISTORY.md)。
