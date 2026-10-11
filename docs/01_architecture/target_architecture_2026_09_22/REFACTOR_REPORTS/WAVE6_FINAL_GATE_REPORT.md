# Wave 6 最終工程 gate 報告

> **歷史時點／現況導覽（2026-10-11）**：本文是 2026-09-23 的工程 gate 快照；下方 R015 unfinished、Wave 7 blocked 等結論是當時狀態。R031 2026-09-27 current overlay 更新了 R013–R017、C1 及後續任務的 bounded disposition，請看 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 與 [R031 final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)。本文所記 42-file／656-test combined run 仍是當時未完成的歷史執行，不因後續 relevant regression acceptance 而回寫成通過。有界工程接受不等於正式資料、ML promotion 或 production deployment 驗收；其餘歷史 gate 證據見 [C1 checkpoint](C1_CHECKPOINT.md)、[Wave 7–10 bounded release checkpoint](WAVE7_10_R020_BOUNDED_RELEASE_CHECKPOINT_20260924.md) 與 [Model Assignments](../REFACTOR_MODEL_ASSIGNMENTS.md)。

執行日期：2026-09-23
範圍：C1 與 R013／R014／R016／R017 synthetic／engineering closeout
SOL 裁決：R013、R014、R016、R017 均 `ACCEPTED_SCOPE`；Wave 7 `RELEASED_FOR_IMPLEMENTATION`
資料範圍：合成資料、pytest fixture 與 TEMP 隔離根；未觸碰正式 `DATA_ROOT`

## 裁決與工程證據

| 切片 | 最終裁決／獨立複審 | 可查證驗證結果 | 範圍限制 |
|---|---|---|---|
| C1 | `C1 ENGINEERING GATE PASS`；independent reviewer `Accept C1 engineering gate for SOL decision` | C1 checkpoint 列示 V-REC 69 passed、V-EXEC 112、V-CODEC 29、V-PERSIST 99 passed／3 skipped、focused V-ML-SMALL 118、完整 readiness 115 passed／1 skipped，以及 R017 readiness + R005 22 passed。changed Python compile、scoped mypy、`git diff --check` 亦通過。 | C1 綜合數字與最終裁決以 [C1 checkpoint](C1_CHECKPOINT.md) 為準；4 個 symlink／reparse 負例因 Windows `WinError 1314` 未能建連結，不計為 pass。ML 僅 synthetic／小型 fixture。 |
| R013 | SOL `R013_ACCEPTED_SCOPE`（synthetic／engineering）；independent reviewer `Accept with nonblocking notes` | Qt focused suite 48 passed；強制 Update View workbench 84 passed；Update Tab QA 25 passed、4 skipped、0 failed；指定 broad mypy 678 source files 無 issue；changed-file `py_compile` 成功。詳見 [R013 report](R013_IMPLEMENTATION_REPORT.md)。 | Update Tab QA 的 4 個 skip 依其 QA 腳本安全設定，為下載／資料合併等項目；不計為 pass。R013 acceptance 不包含未完成的 Wave 6 combined run。 |
| R014 | SOL `ACCEPTED_SCOPE`（synthetic／engineering）；independent reviewer `Accept R014` | `test_scheduled_recommendation_snapshot_wrapper.py` + `test_task_loop_03_contract.py`：39 passed、2 warnings；TEMP 合成 `validate_isolated_recommendation_loop`：6 passed、0 failed、0 skipped；changed-file `py_compile` 成功。詳見 [R014 report](R014_IMPLEMENTATION_REPORT.md)。 | 2 warnings 為既有 `decision_module/scoring_engine.py:437` pandas dtype `FutureWarning`。沒有執行正式 scheduler/main、production data 或完整 QA CLI。獨立 reviewer 結論由本次 gate review 留錄，repo 未保存獨立 R014 review report。 |
| R016 | SOL `ACCEPTED_SCOPE`（synthetic／engineering）；independent reviewer `ACCEPT WITH NONBLOCKING NOTES`，無 R016 P1/P2 | 最終 16-file consumer/query gate：227 passed、1 skipped；U4 專用獨立 suite：49 passed；U4 合併測試：110 passed、4 skipped；R016 scoped mypy、`py_compile`、`git diff --check` 通過。詳見 [R016 consumer report](R016_CONSUMER_CUTOVER_IMPLEMENTATION_REPORT.md) 與 [U4 report](R016_LEGACY_QUERY_PROJECTION_IMPLEMENTATION_REPORT.md)。 | 上述 suite 相互重疊，不應加總。單一 R016 skip 及 U4 4 skips 是 Windows symlink/reparse 建立權限限制；未宣稱有 OS 層 symlink 實測或完成整個 repository 的 raw-reader closure。 |
| R017 | SOL `ACCEPTED_SCOPE`（synthetic／in-memory bridge）；independent review `ACCEPTED_SCOPE`（相同 bounded scope） | Bridge focused 21 passed；bridge + characterization 34 passed；V-REPLAY／readiness/history/backtest suite 96 passed、24 warnings；`py_compile`、scoped mypy 與 `git diff --check` 通過。詳見 [R017 report](R017_IMPLEMENTATION_REPORT.md)。 | 24 warnings 是既有 same-day-close idealized backtest 假設提示。沒有保存 production child artifacts；TMP-REC-04 仍由 R020 退役。 |

這些是彼此有範圍界線的切片證據，不代表 656-test combined suite 已完成，也不代表全庫或產品正式驗收。

## 未完成的 combined suite 與 R015 deferred failure

先前規劃的 42-file／656-test combined pytest invocation 未完成：執行中途遭中斷，沒有完整 pytest summary，因此不能標為 pass 或 fail，也不能把 collect-only 結果當成測試通過。此未完成 run 不計入上表各 owner 已完成的獨立 scoped gate。

另行在 `PROFILE=test`、fresh TEMP `DATA_ROOT`／`OUTPUT_ROOT` 隔離根執行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_recommendation_save_coordinator.py tests\test_personalization_save_integration.py -vv -x --tb=short
```

結果為 **12 passed、1 failed**。失敗測試：`tests/test_personalization_save_integration.py::test_ui_owned_save_ack_reader_projection_and_missing_action`。此 fixture 仍以舊 Qt view／`service.last_*` 呼叫與 ACK 契約建構，缺少 R013 cutover 後所需的 `current_execution`；歸屬 R015 deferred personalization save／ACK 測試遷移，不是 R013 正常無 scope Qt 手動保存 gate。Qt 手動保存不發 Journal ACK；delivery ACK authority 與剩餘個人化 CLI caller 由 R015 處理。同檔其他舊 Qt ACK／probe assertions 也須由 R015 依新 caller 契約重分類，不能以恢復 legacy DTO 或把一般 Qt save 當 ACK 修補。

## 已知限制與 Wave 7 邊界

- 本次所有接受結果都限 synthetic／engineering scope。沒有讀寫正式 `DATA_ROOT`，沒有 production scheduler 執行、full-market ML rebuild／training／inference／promotion，也沒有 deployment。
- Windows symlink／reparse 測試的權限 skip 是未驗證案例，不是成功案例。C1、R016、U4 的計數各自屬不同、部分重疊的 suite，不能相加當成 unique coverage。
- R015 尚未完成 `TMP-REC-03` personalization CLI／ACK caller migration 與舊 Qt ACK/probe tests；R017 的 `TMP-REC-04` 仍由 R020 退役。R016 對無 trusted digest 的 legacy payload 維持 read-time-only trust boundary。
- Wave 7 `RELEASED_FOR_IMPLEMENTATION` 僅代表可以依後續 task owner／dependency 開始工程實作。正式資料接受、投資效果宣稱、ML promotion 與 production deployment 仍須各自獨立 gate。

沒有 stage、commit 或 push。
