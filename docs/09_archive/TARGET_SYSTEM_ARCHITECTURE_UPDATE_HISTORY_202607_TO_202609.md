# 目標系統架構歷史更新記錄（2026-07-11 至 2026-09-25）

> 本頁保存 [目標架構背景文件](../01_architecture/target_system_architecture.md) 原「更新記錄」區塊。日期化狀態只描述當時的架構導覽與 R031 工程範圍，不代表目標能力已實作或所有 blocker 已解除。

目標實作設計看 [FINAL_TARGET_ARCHITECTURE](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)，目前模組邊界看 [system architecture](../01_architecture/system_architecture.md)，目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。R031 驗收與保留限制見 [R031 final closeout](../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)。來源區塊與雜湊見 [Coverage History Entry 159](DOC_COVERAGE_HISTORY_2026.md#coverage-entry-159)。
## 更新記錄

- 2026-09-25：同步 R026 bounded NP1／NP2 runtime migration 與 C2 acceptance；C3 exact-import edges 已修復，但 11 個既有 shadow-boundary diagnostics 仍由 owners 列管。C4 union 為 2,446P／2F／5S／35W，root 接受 named boundary baseline；R031 工程範圍完成，target 仍要求其餘合法 profile/model graph adapters 與 parity evidence。

- 2026-09-22：導向完成紅隊裁決的六份 FINAL 文件；本入口保留背景與權限導覽，工程目標決策統一由 FINAL_TARGET_ARCHITECTURE 管理。

- 2026-09-22：加入七份工程架構設計分冊入口；補足執行契約、局部擴充與保守 ML 遷移設計，不代表 production code 已變更。

- 2026-09-14：補上 content-first Workbench 可與 V4 formal evidence 並行的目標邊界、既有
  Journal／Evidence／Portfolio ledger identity 重用原則，以及既有 daily shadow policy 的
  自動採用／回退；V6 個人化保留為後續 target capability。
- 2026-09-06：校正八卡已落地工程與 Current → Target 差距，保留 PIT、真實 fills、自然時間、具名 review、正式 migration／writer 等獨立 Gate。

- 2026-07-11：初版建立 Current → Transitional → Target 架構；定義 15 個產品／領域邊界、6 張核心流程圖、degraded behavior、正式決策權限與不自動交易政策。
