# C1 重開派工基線

> 本文是 2026-09-23 的歷史派工快照；下列 C1 reopened／Wave 6 blocked 只屬當時狀態。後續 [C1 checkpoint](C1_CHECKPOINT.md) 已記錄 C1 Engineering PASS／Wave 6 released；本頁不代表目前 release 或產品授權。

- 基線日期：2026-09-23
- 分支：`dev`
- HEAD：`dcc27a42a37c2f69ad83fecee6c245177a457e01`
- C1 狀態：`REOPENED_CHANGES_REQUIRED`（Finding：`CHANGES_REQUIRED`）
- Wave 6：`BLOCKED`，原釋出已撤回
- 新 task release：**無**

> 本文件只記錄派工與工作樹基線，不建立修復工作契約、不授權 R-task 開始，也不更改已核准的目標架構。

## 1. 判讀依據與狀態校正

重開後的最新狀態以 [C1_CHECKPOINT.md](C1_CHECKPOINT.md) 與 [C1_CONTRACT_COMPLETENESS_FINDING.md](C1_CONTRACT_COMPLETENESS_FINDING.md) 為準。任務名義 owner 與 wave release 取自 [REFACTOR_MODEL_ASSIGNMENTS.md](../REFACTOR_MODEL_ASSIGNMENTS.md)，波次依賴取自 [REFACTOR_EXECUTION_ORDER.md](../REFACTOR_EXECUTION_ORDER.md) 與 [REFACTOR_TASKS/README.md](../REFACTOR_TASKS/README.md)，驗收 gate 取自 [REFACTOR_VALIDATION_MATRIX.md](../REFACTOR_VALIDATION_MATRIX.md)。

C1 原本的 `PASS` 與 Wave 6 release 已被撤回。原 bundle 的測試結果仍是其實際執行範圍內的證據（核心 213 passed、3 skipped、2 warnings；focused ML 93 passed；相關 natural fixture 76 passed），但未覆蓋 sealed execution 的既有 consumer 必需欄位與異質歷史讀取，因此不能作為目前 C1 通過或 Wave 6 可開始的依據。校正 fixture 的獨立複審只涵蓋日期修復，不解除 C1。

[R014_IMPLEMENTATION_REPORT.md](R014_IMPLEMENTATION_REPORT.md) 的 `TASK_STATUS: ARCHITECTURE_BLOCKER` 是 R014 worker 在當時原 scope 內遇到資料缺口後停止的歷史紀錄；依最新 C1 finding，program 層現行判定為**已核准架構的實作完整性缺口（CHANGES_REQUIRED）**，尚未證明目標架構不可行。R014 報告中的舊 C1 PASS 前提已失效。不得把該 task 內狀態提升成新的 architecture escalation，也不得因舊 PASS 繼續接線。

`docs/agents/shared_state/active_task.yaml` 只作歷史對照；其中舊 refactor 狀態不是目前 C1 gate 來源。本基線以最新 C1 文件、模型分派表、wave checkpoint、實作報告及本輪調度指示為準。

## 2. 工作樹與 Git index 快照

以下是建立本文件前的 `git status --short`。未提交項目均原樣保留；本文件不將它們歸屬給任何 worker。

```text
 M app_module/__init__.py
 M app_module/dtos/__init__.py
 M app_module/recommendation_repository.py
 M app_module/recommendation_service.py
 M data_module/__init__.py
 M decision_module/__init__.py
 M docs/00_core/DOCUMENTATION_INDEX.md
 M docs/01_architecture/README.md
 M docs/01_architecture/target_system_architecture.md
 M tests/test_recommendation_service_calibration_integration.py
 M tests/test_task_loop_03_contract.py
 M tests/test_update_service_import_contract.py
?? =
?? app_module/recommendation/
?? data_module/contracts/
?? data_module/result_artifact_store.py
?? decision_module/recommendation/
?? docs/01_architecture/target_architecture_2026_09_22/
?? docs/06_qa/REFACTOR_BASELINE_R001_20260922.md
?? docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md
?? ml_module/prepared_input_contract.py
?? tests/test_data_market_contracts.py
?? tests/test_prepared_ml_input_contract.py
?? tests/test_r004_recommendation_persistence_characterization.py
?? tests/test_r008_decision_numeric_enum_rework.py
?? tests/test_r012_recommendation_artifact_persistence.py
?? tests/test_recommendation_contracts.py
?? tests/test_recommendation_execution_codec.py
?? tests/test_recommendation_execution_state_characterization.py
?? tests/test_recommendation_execution_use_case.py
?? tests/test_recommendation_replay_characterization.py
?? tests/test_refactor_ml_compatibility_baseline.py
```

建立本文件前，`git diff --cached --name-status` 為空，index 沒有 staged paths。目標檔案建立後仍維持未 stage；由於其父目錄目前整體為 untracked，Git status 以 `?? docs/01_architecture/target_architecture_2026_09_22/` 顯示，不另列目錄內單檔。

## 3. C1 缺口與目前修復前置工作

C1 finding 將缺口定義為既有消費者契約未完整封存在 canonical execution：

- R014 scheduled forward candidate 需要從已保存 artifact 取得同次推薦列的價格、漲幅、總分與分項分數、理由、industry、完整 config，以及 created／decision／available clocks；execution、保存、ML receipt 與 forward consumer 必須能核對同一 result identity。
- R016 歷史 Advice／Desk／watchlist／evidence 顯示需要保留 legacy runs 與 canonical execution 的讀取 seam。舊結果只按保存值顯示，缺欄不能 live lookup 或重算。
- R017 replay 需保留舊 snapshot 的 typed historical annotation 與 parent/date references，不能用任意擴充字典或推測 parent identity。

目前正在進行兩份**唯讀審查**，作為後續裁決輸入；兩者都不持有 production code／測試修改權：

| 工作流 | 範圍 | 現況 |
|---|---|---|
| `consumer_inventory` | 逐項盤點 R013／R014／R016／R017 consumer 所需欄位、來源、可得時間及單位，核對 canonical／receipt／legacy read path | 執行中；唯讀 |
| `compat_audit` | 核對 R008／R009／R011／R012 schema revision、舊 revision 與原 bytes/hash readback、ML receipt identity／ordered ABI 風險 | 執行中；唯讀 |

兩份審查尚待結果；目前沒有 C1 修復 implementation owner，沒有新的具名修復 task，也沒有任何 R-task release。C1 gate 持續封鎖。

## 4. R001–R031 名義 owner 與現行狀態

下表的「名義 owner／reviewer」忠實記錄模型分派表；它不代表當前已派工。歷史 PASS 僅表示當時 task／wave 證據已驗收，不表示新的 consumer completeness gate 已通過。

| Task | Wave | 名義實作 owner | 名義 review／final gate | 目前狀態 | 狀態來源 |
|---|---:|---|---|---|---|
| R001 | 0 | LUNA_MAX | SOL | 歷史完成；Wave 0 PASS | MA §3；R001 SOL review／erratum review |
| R002 | 1 | LUNA_MAX | GEMINI | 歷史完成；Wave 1 PASS | MA §3；Wave 1 checkpoint |
| R003 | 1 | GEMINI | SOL | 歷史完成；Wave 1 PASS | MA §3；Wave 1 checkpoint |
| R004 | 1 | LUNA_MAX | GEMINI | 歷史完成；Wave 1 PASS | MA §3；Wave 1 checkpoint |
| R005 | 1 | GEMINI | SOL | 歷史完成；Wave 1 PASS | MA §3；Wave 1 checkpoint |
| R006 | 1 | GEMINI | SOL | 歷史完成；Wave 1 PASS | MA §3；Wave 1 checkpoint |
| R007 | 1 | LUNA_MAX | SOL | 歷史完成；Wave 1 PASS | MA §3；Wave 1 checkpoint 與 R007 勘誤驗收 |
| R008 | 2 | LUNA_MAX | 獨立 LUNA_MAX → SOL | 歷史完成；Wave 2 PASS | MA §3；Wave 2 result-id／schema-range checkpoints |
| R009 | 3 | LUNA_MAX | 獨立 LUNA_MAX → SOL | 歷史完成；Wave 3 PASS | MA §3；WAVE3_CHECKPOINT.md |
| R010 | 3 | LUNA_MAX | 獨立 LUNA_MAX → SOL | 歷史完成；Wave 3 PASS | MA §3；WAVE3_CHECKPOINT.md |
| R011 | 4 | LUNA_MAX | 獨立 LUNA_MAX → SOL | 歷史完成；Wave 4 PASS | MA §3；WAVE4_CHECKPOINT.md |
| R012 | 5 | LUNA_MAX | 獨立 LUNA_MAX → SOL | 歷史完成；Wave 5 PASS | MA §3；WAVE5_CHECKPOINT.md |
| R013 | 6 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 6 停止；未派工、未開始 | MA §3；C1 checkpoint／finding：未釋出 |
| R014 | 6 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 6 停止；原 worker 報告未改 production code；待上游修復及重驗 | C1 finding；R014_IMPLEMENTATION_REPORT.md（僅 task 內停止紀錄） |
| R015 | 7 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 7 blocked；未派工 | MA §3；C1 checkpoint |
| R016 | 6 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 6 停止；改檔前停止 | C1 finding；MA §3 |
| R017 | 6 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 6 停止；改檔前停止 | C1 finding；MA §3 |
| R018 | 9 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 9 blocked；未釋出 | MA §3；C1 checkpoint |
| R019 | 10 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 10 blocked；未釋出 | MA §3；C1 checkpoint |
| R020 | 11 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 11 blocked；未釋出 | MA §3；C1 checkpoint |
| R021 | 7 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 7 blocked；未釋出 | MA §3；C1 checkpoint |
| R022 | 8 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 8 blocked；未釋出 | MA §3；C1 checkpoint |
| R023 | 7 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 7 blocked；未釋出 | MA §3；C1 checkpoint |
| R024 | 9 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 9 blocked；未釋出 | MA §3；C1 checkpoint |
| R025 | 7 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 7 blocked；未釋出 | MA §3；C1 checkpoint |
| R026 | 11 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 11 blocked；未釋出 | MA §3；C1 checkpoint |
| R027 | 7 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 7 blocked；未釋出 | MA §3；C1 checkpoint |
| R028 | 9 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 9 blocked；另受 R027=PASS 前置條件 | MA §3；C1 checkpoint |
| R029 | 12 | LUNA_MAX | 獨立 LUNA_MAX → SOL | Wave 12 blocked；未釋出 | MA §3；C1 checkpoint |
| R030 | 13 | LUNA_MAX | SOL | Wave 13 blocked；未釋出 | MA §3；C1 checkpoint |
| R031 | 14 | SOL_ONLY | 獨立 LUNA_MAX → SOL | Wave 14 blocked；未釋出 | MA §3；C1 checkpoint |

**狀態來源代碼：** MA = `REFACTOR_MODEL_ASSIGNMENTS.md`；C1 = `C1_CHECKPOINT.md` 與 `C1_CONTRACT_COMPLETENESS_FINDING.md`。Wave 7–14 沒有釋出任何 task；其 BLOCKED 是 wave release 狀態，不等於各 task 已個別執行或驗收失敗。

Wave 1 的 R003／R005／R006 分派表保留 Gemini 原始實作記錄；依後續分派紀錄，三項因 SOL 要求修正而由 LUNA_MAX 回修，最後均已歷史驗收。上表「名義實作 owner」記原分派，不代表目前仍有人持有這些已完成 task。

## 5. 派工結論

- 修復仍在 C1 前置裁決／唯讀盤點階段；等 `consumer_inventory` 與 `compat_audit` 結果，再由 SOL 確認 typed owner、最小修補範圍與驗收條件。
- 本基線沒有建立 implementation report，也沒有為任何 R-task 指派實作者。
- C1 完整 consumer-readiness 正反例與全部必要驗證尚未完成；在新的 C1 最終驗收通過前，Wave 6 不得重釋，Wave 7–14 繼續 blocked。
- `WAVE6_SCOPE_AND_OWNERSHIP.md` 僅記錄未來重新釋出時的預定檔案 owner，不構成目前 release。
- 本文件是調度狀態記錄；**無新 task release**。

## 參考文件

- [C1 契約缺口](C1_CONTRACT_COMPLETENESS_FINDING.md)
- [C1 checkpoint](C1_CHECKPOINT.md)
- [C1 驗證計畫](C1_VALIDATION_PLAN.md)
- [Wave 6 owner 預案](WAVE6_SCOPE_AND_OWNERSHIP.md)
- [Wave 5 checkpoint](WAVE5_CHECKPOINT.md)
- [模型分派與 wave release](../REFACTOR_MODEL_ASSIGNMENTS.md)
- [執行順序](../REFACTOR_EXECUTION_ORDER.md)
- [驗證矩陣](../REFACTOR_VALIDATION_MATRIX.md)
- [R001–R031 任務索引](../REFACTOR_TASKS/README.md)
