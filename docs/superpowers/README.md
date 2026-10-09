# Superpowers Specs / Plans 目錄

> **最後整理**：2026-10-06
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

## 維護規則

- 目前已存在的 plan/spec/prompt 原 bytes 與原路徑保留；本輪不搬檔、不改其正文。位置、日期標籤、生命週期判讀與現行權威替代關係逐檔列在 [`../09_archive/SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md`](../09_archive/SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md)。
- 檔名日期是里程碑或計畫日期，不一定等於完成日期；不依檔名推定完成。個別結果以 Snapshot、Roadmap、對應 QA 收據與 Git 記錄為準。
- 新增仍在推動中的 spec / plan 時，若會被日常引用，應同步加入 [文件索引](../00_core/DOCUMENTATION_INDEX.md)；完成或 superseded 後更新 manifest 的狀態與 evidence 路徑。
- 原始輸出、暫存報告與本機執行產物不應放入本目錄；需要保存結論時整理為 `../06_qa/` 摘要。

## 相關入口

- [文件索引](../00_core/DOCUMENTATION_INDEX.md) - 已納入索引的主要 spec / plan。
- [Plan/spec archive manifest](../09_archive/SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md) - 原路徑保留表與生命週期判讀。
- [Plan/spec 日期與狀態稽核（2026-07-06）](../06_qa/SUPERPOWERS_PLAN_SPEC_DATE_AUDIT_2026_07_06.md)。
- [歷史 push 前文件稽核（2026-07-06）](../09_archive/DOCUMENTATION_PRE_PUSH_AUDIT_2026_07_06_HISTORY.md)。
