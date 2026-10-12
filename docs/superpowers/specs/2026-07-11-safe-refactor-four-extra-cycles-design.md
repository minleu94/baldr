# 安全重構四個延長循環設計

> **來源與生命週期核對（2026-10-12）**：本文 D–G 是四輪、每輪 Planner／Implementation／QA 各一支的 12 個設定；另一份 H–L 下午設計是五輪、共 15 個設定，兩者屬不同時段與 scope，不應合併或互相替代。追溯來源為 2026-09-25 的 [Codex automation inventory](../../06_qa/BALDR_CODEX_AUTOMATION_INVENTORY_20260925.json)：清冊列出兩組各自的 automation ID、當時狀態與 TOML 雜湊；目前 CODEX_HOME 內兩組 TOML 亦保存為 PAUSED。各 automation 的本機 `memory.md` 與 ignored `output/automation/version_loop/refactor_nightly_closeout_20260711.md`、`refactor_afternoon_closeout_20260711.md` 記錄了兩段執行交接鏈；closeout 的工作切片數與設定支數是不同單位，D–G 所屬當日 00:00–12:00 鏈記 6 個切片，H–L 記 4 個完成切片、J 輪為 `NO_SAFE_SLICE`。這些資料支持設定曾持久化及流程有執行記錄，但未找到獨立 Codex host event/audit receipt 以證明每次由排程器觸發，因此觸發來源仍未知。細節見 [本次治理核對收據](../../06_qa/DOCUMENT_GOVERNANCE_ISSUE_RESOLUTION_20261012.md)；本文計數是設計設定數，不是完成切片數，也不授權現在建立或執行 automation。現行操作依 [Application Manual](../../07_guides/APPLICATION_MANUAL.md) 與對應日期化 QA 判讀。


> **歷史設計（2026-07-11）**：本文記錄的一次性 automation、舊排程與 Git 操作不代表目前任務狀態或執行授權。現況看 [Snapshot](../../00_core/PROJECT_SNAPSHOT.md)、[6M Roadmap](../../00_core/ROADMAP_6M_ENGINEERING.md) 與現行協作規範。

## 目標

在既有 08:00 QA 後新增四個不壓縮的 Planner → Implementation → QA 循環，延長安全重構到 12:00，並維持現已歸檔為 `docs/09_archive/SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md` 的所有 Gate、產物追溯與 atomic commit/push 模式。

## 核准時段

| 循環 | Planner | Implementation | QA |
|---|---|---|---|
| D | 08:20 | 08:40 | 09:00 |
| E | 09:20 | 09:40 | 10:00 |
| F | 10:20 | 10:40 | 11:00 |
| G | 11:20 | 11:40 | 12:00 Final QA / Closeout |

## 交接設計

- 08:00 automation 從 Final Closeout 改為第三輪 QA，產生 `refactor_qa_YYYYMMDD_0800`，並交接 08:20 Planner。
- 每個 Planner 只讀總報告、上一 QA、對應 Implementation / Plan 與 Git，產生該輪 exact Plan。
- 每個 Implementation 只消費同輪 Plan，驗證 stage、日期、baseline 與 HEAD 後才可寫入。
- 每個 QA 只讀同輪 Implementation report、Plan 與 Git，獨立重跑關鍵 Gate。
- 12:00 QA 才產生 `refactor_nightly_closeout_YYYYMMDD`、latest QA 與 MORNING_README，交接次日 00:00。

## 安全邊界

- 不縮短任何 Planner、Implementation 或 QA 的既有角色責任。
- 不改既有 00:00–08:00 時段；只調整 08:00 的交接角色。
- 十二支新 automation 皆為 daily、ACTIVE、`gpt-5.6-terra`、high reasoning、local project、`dev`。
- 不新增固定 Slice queue；所有切片仍由總報告與上一 QA 動態決定。
- 不寫 production DB、不啟用 production scheduler、不交易、不改 lifecycle、ScoringEngine、threshold、profile weights、portfolio 或正式資料。
- 任何 cycle artifact stale、baseline 不符、未知 dirty、Gate 未通過或時間不足，必須停止，不得留下半成品。

## 成功準則

1. 08:00 prompt 的 handoff 改為 08:20 Planner，不再提前產生 nightly closeout。
2. 四輪共十二支新 automation 全部建立且時間正確。
3. 每輪 Planner、Implementation、QA 的 artifact stage 與 handoff 精確串接。
4. 12:00 是唯一新增的 Final QA / Closeout。
5. 原有總報告、安全邊界、模型、執行環境與 atomic commit/push 模式不變。
