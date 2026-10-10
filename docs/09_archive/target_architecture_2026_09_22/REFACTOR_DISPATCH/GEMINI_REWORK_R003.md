> **歷史封存警語（2026-10-10）：**本文保留當時的回修派送內容；其中 SHA（如有）、scope、角色、指令與狀態僅代表原快照，不得據此重派、重跑或視為目前任務／授權。現況請以 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md) 與 [REFACTOR_MODEL_ASSIGNMENTS](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_MODEL_ASSIGNMENTS.md) 為準；後續 Wave 1 狀態見 [WAVE1_R007_TZNAME_CHECKPOINT](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE1_R007_TZNAME_CHECKPOINT.md)。

# GEMINI_REWORK_PACKET — R003

本次狀態為 CHANGES_REQUIRED。請在同一 R003 scope 內修補 SOL findings，保留已通過的測試與既有 working-tree changes；完成後更新原 implementation report。下面先列最新 SOL review，再附完整原始任務封包。若兩者有細節差異，以最新 review 的修補要求為準，架構與 scope 仍以原封包為準。

目前交付基線：`tests/test_recommendation_execution_state_characterization.py` SHA-256 `58570C03BBCE9EFE4FE3DEB6298184C48DCF0674D6573FC1F8A98E83D3452E10`；`REFACTOR_REPORTS/R003_IMPLEMENTATION_REPORT.md` SHA-256 `36E6F55896854BB1A05EA229D0D9289B7DB9437949108D517E81881C3B7C12C0`。本輪只修這兩檔，保留其他 worker 與原有 dirty paths。

# R003 SOL 審查

## 判定

`tests/test_recommendation_execution_state_characterization.py` 的 6 個新案例與既有 execution coordinator／TaskWorker suite 在 SOL 重跑時共 26 passed。實作沒有修改 production。但新案例尚不足以達到 R003 的 acceptance criteria，實作報告所稱「所有終端狀態」、「stale callback」及「worker close」都沒有對應的可判定 oracle。

## 必須修正的項目

1. `tests/test_recommendation_execution_state_characterization.py:109` 的 A/B 測試使用兩個分離的 `FakeRecommendationService`，只證明兩個 `TaskWorker.finished` signal 都送達；沒有延後讀 A 的 `last_*`、沒有呼叫 `RecommendationView` 的 request correlation callback，也沒有驗 stale callback 不覆寫 last-good display。請用 deterministic event/barrier 加實際 UI callback seam 建立這些 assertions；不得以 sleep 製造順序，也不得為通過測試修改 production。
2. 同檔 `:109` 名稱聲稱 worker close，但沒有 `deleteLater`、native thread completion 或受管 worker registry 的 assertion。請驗證目前 close/lifecycle 可觀察行為，必要時把現況差距列為 gap。
3. `:44` 的 completed-empty 與 `:80` 的取消都以 `[]` 表示。現有 Fake service 的 call count/return value 不能區分 terminal outcome；請至少以 worker finished/error/cancelled signal、service 呼叫事件與 UI 狀態分離 completed-empty、failed、cancelled、validation rejection。`validation_error()` 單獨回字串不能代表 worker rejection event。
4. `:144` 只測 request input 的一個 nested alias；沒有回傳物被原輸入或 caller 再次修改後的可見性，也沒有 A/B 同一服務 hidden-state 汙染測試。請在兩側加明確 mutation oracle，將現況違反 INV-08 的證據和未來要求分開。
5. 缺 progress callback shape、ML receipt side-effect 在 cancel/failure 後的可見順序、last-good result 與完整事件矩陣。這些都在原 R003 spec／Gemini packet 的 required behavior；可以用 fake receipt/progress spy，不可載入正式模型或寫 repository。
6. `R003_IMPLEMENTATION_REPORT.md` 只記 6 個新測試；須補起始／結束 HEAD 與 dirty baseline、每個 terminal event sequence、現況 gap、實際 changed files、既有 `test_recommendation_execution_coordinator.py` 與相關 Qt worker/stale focused tests 的命令與結果、`py_compile` 和 `git diff --check`。目前 `UNRESOLVED RISKS: 無` 與上述缺口不符。

允許變更仍限 R003 專用新測試與 R003 實作報告；若必須動 production 或另一 R-task 檔案，停止並附證據回報。完成後重跑 V-EXEC，交 SOL 查實際 diff。Wave 2 仍 blocked。


---

# GEMINI_TASK_PACKET — R003

## ROLE

你是受控重構 implementation agent。架構已定案；你負責建立 terminal outcome、取消與 hidden-state 的 characterization coverage，不負責設計新 execution contract。

## TASK ID

R003 — terminal outcome、取消與 hidden-state characterization（Wave 1）。

## PURPOSE

在 R008/R011 建立 canonical execution 之前，以可控測試凍結現有 request validation、progress、cooperative cancellation、stale callback、last-good display、worker close、A/B invocation 與 ML receipt side-effect 可見順序。必須分辨 completed-nonempty、completed-empty、validation rejection、failed、cancelled，不能用空 list 代表所有 terminal outcome。

## CURRENT SYSTEM CONTEXT

- `RecommendationService.run_recommendation()` 回傳 list，並寫多個 `last_*`；目前沒有統一 terminal result contract。
- `ui_qt/views/recommendation/execution_coordinator.py` 把 bound callable 交給 worker。
- `ui_qt/workers/task_worker.py` 提供 cooperative cancellation 與 finished/error/cancelled signals。
- `ui_qt/views/recommendation_view.py` 管理 request correlation、last-good 顯示及 callback；本 task 只能唯讀觀察。
- R001 已 PASS。基線位於 `docs/06_qa/REFACTOR_BASELINE_R001_20260922.md`，記錄 41 個 caller/test 命中、現有 `last_*` 與 worker/UI caller。起始 HEAD 為 `391b057c92037ec7a19cab2bf951d6029d29b020`、branch `dev`；開始工作時必須重新記錄實際 HEAD/dirty state，因其他 Wave 1 tasks 可能同時新增各自檔案。

## AUTHORITATIVE ARCHITECTURE

只使用下列 authority，不得重新設計：

- `REFACTOR_TASKS/R003.md`：完整 task contract。
- `FINAL_DATA_FLOW.md` §2、§6：一次 invocation 的完整結果與 UI 投影／保存一致性。
- `FINAL_ARCHITECTURE_INVARIANTS.md`：INV-07、INV-08、INV-09、INV-10、INV-16。
- `FINAL_MIGRATION_SEQUENCE.md` Block 1–2：先 characterization，再 contract/capture；不先修改 engine。
- `REFACTOR_VALIDATION_MATRIX.md` 的 `V-EXEC` 與 R003 row。

## RELEVANT INVARIANTS

- 每個 execution identity 只能代表一次 invocation；A/B 交錯不得讀到彼此 hidden state。
- completed-empty 是合法完成狀態；failed/cancelled 不得冒充 completed。
- 封存後的 nested mutable input/output alias 必須可被測試揭露。
- UI 只接受當前 request 的 callback；stale callback 不得覆寫 last-good result。
- 本 task 只建立 oracle，不先加入新的 status class 或 production behavior。

## COMPLETED DEPENDENCIES

R001：PASS。Caller、worker、UI、ML receipt 與 TMP 基線已登錄；外部 callers／binary class paths 的 unknown 不影響本 task。沒有其他 R-task 可視為完成。

## ALLOWED SCOPE

- 新增專用 execution-state characterization tests、deterministic barriers、test doubles 與最小 fixtures。
- 唯讀檢查 `recommendation_service.py`、execution coordinator、TaskWorker 與 recommendation view callbacks。
- 如需共享 test helper，只能放在 R003 新測試旁，且必須說明不供 production 使用。
- 新增 `REFACTOR_REPORTS/R003_IMPLEMENTATION_REPORT.md`。

## OUT OF SCOPE

- 不新增或修改 production status／execution class。
- 不改取消、progress、UI 顯示、service state、receipt 或 persistence 行為。
- 不修已觀察到的 product gap；以測試／gap table 記錄。
- 不修改 R002、R004、R005、R006、R007 的檔案；不開始 R008 以上工作。
- 不 stage、commit、push、reset、clean 或處理既有 unrelated dirty changes。

## FILES LIKELY INVOLVED

- 新增 `tests/test_recommendation_execution_state_characterization.py` 或同等單一專用測試檔。
- 既有 read-only context：`app_module/recommendation_service.py`、`ui_qt/views/recommendation/execution_coordinator.py`、`ui_qt/workers/task_worker.py`、`ui_qt/views/recommendation_view.py`。
- Existing tests：`tests/test_recommendation_execution_coordinator.py` 與由 repository search 確認的 Qt worker/stale callback focused tests。

## CURRENT BEHAVIOR TO PRESERVE

Request validation、progress callback shape、cooperative cancellation、stale request correlation、last-good display、worker close、A/B invocation isolation，以及 receipt 已發生但主 run 取消／失敗時的目前可見順序。若現況和 FINAL 的未來要求不同，明示為 current gap，不在 R003 修正。

## IMPLEMENTATION REQUIREMENTS

- 用 deterministic event/barrier 控制 A 完成、B 開始、延後讀 A、取消前後與 late callback；禁止用 sleep 製造時序。
- 案例表至少涵蓋 completed-nonempty、completed-empty、validation rejection、raised failure、cooperative cancellation、stale callback、worker close。
- 明確斷言 terminal outcome，不得只斷言 `[]`。
- 從原輸入與回傳物兩端嘗試 nested mutation，記錄目前 alias behavior；不得為了通過測試修改 production。
- 對現況已支援行為建立通過測試；對 FINAL 要求但現況缺失的部分，使用清楚命名的 gap evidence，不得加入永久紅燈或 `xfail(strict=False)` 掩蓋。

## NUMERICAL COMPATIBILITY

不得改 score、filter、ranking、order、Decimal、float precision、missing values 或任何計算。Fixtures 只需足以觀察狀態與 identity，不建立新的數值 oracle。

## PERSISTENCE COMPATIBILITY

不得寫 RecommendationRepository 或正式 store。測試需確認 partial/cancelled 不被觀察成 completed，但不實作新的 writer policy。

## REPLAY COMPATIBILITY

不修改 replay、historical snapshot 或 portfolio backtest。若共用 worker tests 涵蓋其他頁面，只執行相關 assertion，不改 replay policy。

## ML COMPATIBILITY

只 characterize receipt side-effect 的可見時序；不得載入／訓練模型、改 projection、receipt schema、candidate identity 或 provider timing。`ML_COMPATIBILITY_RISK` 應列為 receipt ordering characterization only。

## REQUIRED TESTS

- 新增 R003 專用 characterization tests。
- `tests/test_recommendation_execution_coordinator.py`。
- Repository search 找到的直接 TaskWorker／stale callback focused tests；在報告列出精確檔案與選擇理由。
- Changed Python `py_compile`、`git diff --check`。
- 若測試觸及 Qt，使用既有 offscreen／fixture 慣例，不開啟正式 GUI 或 production workflow。

## ACCEPTANCE CRITERIA

- 所有 terminal cases 有可判定 oracle，completed-empty 不與 failed/cancelled 混淆。
- A/B interleave、cancel、late callback 與 last-good 行為由 deterministic barrier 覆蓋。
- Nested mutable alias 風險被明確測試／記錄。
- Production code 零修改；無 sleep-based timing test；無其他 R-task scope。
- 實作報告逐項列事件序列、目前可保留行為、現況 gap、tests 與 rollback。

## STOP CONDITIONS

- 必須修改 production 才能寫 characterization。
- 無法用 barrier／fake clock／signal spy 建立穩定 oracle。
- 發現架構 authority 與實際 code 存在使 R003 無法安全完成的重大矛盾。
- 需要寫正式 data/store、啟動 scheduler、載入模型或觸碰另一 active task 的檔案。

遇到前述情況，停止並在 report 中給出證據；不要自行修 architecture 或 product bug。

## REQUIRED IMPLEMENTATION REPORT

建立 `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R003_IMPLEMENTATION_REPORT.md`，包含起始／結束 HEAD 與 dirty baseline、changed files、事件矩陣、現況 gaps、commands/results、acceptance verdict、rollback，末行只能是：

`IMPLEMENTATION_STATUS: READY_FOR_REVIEW`

或 `IMPLEMENTATION_STATUS: CHANGES_REQUIRED`

或 `IMPLEMENTATION_STATUS: ARCHITECTURE_BLOCKER`

Do not redesign the architecture.

Do not perform unrelated cleanup.

Do not silently fix unrelated bugs.

Do not begin another R-task.

If repository evidence contradicts this task specification in a way that prevents safe implementation, stop and report ARCHITECTURE_BLOCKER with evidence.
