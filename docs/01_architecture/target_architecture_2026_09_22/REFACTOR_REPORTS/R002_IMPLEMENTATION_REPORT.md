> **歷史狀態導讀（2026-10-10）**：本文日期為 2026-09-22，文末 `READY_FOR_REVIEW` 是當時狀態；R031 後續將 R002 列為 `ACCEPTED` 的有界 characterization。固定輸出與排序不替代 TMP-NUM-01 precision gate；目前 task disposition 看 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)與[final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)。

# R002 實作報告

- Task：R002 — 推薦語意與數值 characterization
- Wave：1
- 日期：2026-09-22
- 起始／結束 HEAD：`391b057c92037ec7a19cab2bf951d6029d29b020`
- Branch：`dev`（未切換）

## 範圍與工作樹

新增 R002 專用 characterization 測試及本報告，並依 SOL gate 的 test-only CHANGES_REQUIRED 修復三個既有 task-loop-03 測試失敗。沒有修改 production code、正式資料或模型，沒有 stage 或 commit。推薦市場資料及 PE SQLite 資料皆由測試在記憶體或 `tmp_path` 建立；`calibration_consumer=None`，沒有載入模型。輸入 result ID 使用固定 fixture 值，沒有用待抽出的 helper 生成任何預期值。

起始 dirty tree 已含三個 tracked 文件修改（`docs/00_core/DOCUMENTATION_INDEX.md`、`docs/01_architecture/README.md`、`docs/01_architecture/target_system_architecture.md`）、根目錄 `=`、未追蹤的 `target_architecture_2026_09_22/` 文件樹，以及 R001 baseline。工作期間共享工作樹另出現 `data_module/__init__.py`、`data_module/contracts/`、`tests/test_data_market_contracts.py`、`tests/test_r004_recommendation_persistence_characterization.py`；均非 R002 所有，未讀寫或整理。HEAD 與 branch 未變。

本任務 changed files：

- `tests/test_task_loop_03_contract.py`（test-only repair）
- `tests/test_recommendation_refactor_characterization.py`
- `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R002_IMPLEMENTATION_REPORT.md`

## Cases 與 invariant 對照

| Case | Characterization | 不變條件／風險 |
|---|---|---|
| Fixed 正常候選、同分、top-N | 固定處理順序；同分維持候選處理順序；逐欄檢查 DTO 與 screening matrix；超出 top-N 進入 why-not。 | INV-06；RK-01 |
| Quantile、Decimal 邊界與排序 | `50.0049`、`50.0050`、`50.0051` 鎖定 bp 半入；percentile、門檻、原始分數排序及同分 code tie-break 均精確檢查。 | INV-06；RK-01、RK-02 |
| Legacy float 與 Decimal quantum | 檢查 legacy `numpy.float64(91.5)` 輸出型別／值；Decimal `70.0100` quantum 保留至 DTO 與 matrix payload。 | INV-06；RK-02、TMP-NUM-01 evidence |
| Missing score | `None`、`Decimal('NaN')`、`Decimal('Infinity')` 均為 missing，不作零分排名；quality、reason code 與負面證據精確檢查。 | INV-06、INV-09；RK-01、RK-02 |
| Empty input | 合法空結果、零 eligible universe、空 screening/why-not、固定 result ID。 | INV-09 |
| 部分失敗、負面證據與 liquidity | 同一執行包含 pass、volume filter、單股 exception、歷史列數不足；鎖定順序、狀態、警告、why-not、excluded 與 liquidity payload。 | INV-09；RK-01 |
| PIT industry | verified fixture 只處理所屬股票；membership 不可用時 fail closed 且不呼叫 evaluator。 | INV-05、INV-09 |
| Fundamental | temp SQLite 鎖定可得 PE、未到 available date 的 PE、缺列、超門檻 PE；不存在 DB 時維持 missing 且不建立檔案。 | INV-05、INV-09 |
| Rule selection 與 ML annotation | 明確注入無 consumer；rule 排名及分數照常輸出，calibration 欄位維持 unavailable。沒有正式模型載入。 | INV-09；R002 ML compatibility requirement |
| Replay／read-only mode | 同一 V-REC 執行中既有 `test_explicit_cutoff_uses_readonly_db_window_not_global_latest` 與 `test_profile_replay_sends_frozen_config_and_pit_frame` 通過，提供 cutoff/read-only 與 replay fixture evidence。 | INV-05、INV-13 |

## Exact 與 tolerance 欄位

新增 oracle 沒有使用數值 tolerance；所有數值比較都是 exact。精確檢查欄位包含 recommendation 選取順序、分數與 runtime 數值型別、Decimal quantum、quantile percentile／eligible universe／排序 metadata、screening matrix 的 named columns、reason code／status／quality／stage、why-not 與 liquidity payload、警告、fundamental inputs、固定 `result_id`，以及 `market_data_fingerprint`、`data_fingerprint`、universe IDs/hashes。

執行時 `decision_at` 是可變 clock 欄位，測試檢查其為 UTC aware ISO timestamp，不將它與固定輸入快照比較。沒有用忽略任意欄位的寬鬆 snapshot；matrix 僅以測試內列明的欄位投影作 exact comparison，fingerprints 分開比對固定 golden 值。

## SOL gate 修復與驗證

R002 修改前先跑規定的五組既有測試：task-loop-03、run-support、negative-evidence、fundamental filters、ranking service，結果為 **45 passed、3 failed**。SOL gate 將三項分類為可在 R002 範圍內精確修復的 test-only `CHANGES_REQUIRED`，要求 Wave 1 required tests 全綠；這不代表 production bug 或 architecture blocker。

| 修復節點 | 修復內容 | 邊界 |
|---|---|---|
| `test_future_append_and_late_revision_preserve_historical_result`、`test_pe_future_append_candidate_quality_and_input_fingerprint` | context 比較排除每次呼叫都不同的 `result_id` 與 `decision_at`；兩次呼叫各自精確驗證 `decision_at` 可解析為 UTC-aware ISO timestamp。比較 helper 改名為 `_without_invocation_identity`。 | 僅修正既有 assertion；保留 result ID 差異檢查，不改 production clock 行為。 |
| `test_saved_result_identity_is_recorded_and_cleared_by_next_analysis` | `SimpleNamespace` 加入 `result_status_label=MagicMock()`，以及 empty completion 會用到的 `research_actions_toggle`、`research_actions_widget` mocks；斷言 `setText` 被呼叫。 | 僅補足 UI fixture；不改 production 完成流程。 |

修復後三個指定節點為 **3 passed**。最終 V-REC bundle 為 **64 passed、0 failed**；新增 oracle 獨立執行 **8 passed**。

執行命令與結果：

```text
.\.venv\Scripts\python.exe -m pytest tests/test_task_loop_03_contract.py tests/test_recommendation_run_support.py tests/test_recommendation_v1_7_negative_evidence.py tests/test_recommendation_fundamental_filters.py tests/test_recommendation_ranking_service.py -q -o addopts=
修改前：45 passed, 3 failed（上列三節點）

.\.venv\Scripts\python.exe -m pytest tests/test_task_loop_03_contract.py::test_future_append_and_late_revision_preserve_historical_result tests/test_task_loop_03_contract.py::test_pe_future_append_candidate_quality_and_input_fingerprint tests/test_task_loop_03_contract.py::test_saved_result_identity_is_recorded_and_cleared_by_next_analysis -q -o addopts=
3 passed

.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_refactor_characterization.py -q -o addopts=
8 passed

.\.venv\Scripts\python.exe -m pytest tests/test_task_loop_03_contract.py tests/test_recommendation_run_support.py tests/test_recommendation_v1_7_negative_evidence.py tests/test_recommendation_fundamental_filters.py tests/test_recommendation_ranking_service.py tests/test_recommendation_market_data_provider.py tests/test_pit_industry_callers.py tests/test_recommendation_refactor_characterization.py -q -o addopts=
64 passed, 0 failed

.\.venv\Scripts\python.exe -m py_compile tests\test_task_loop_03_contract.py tests\test_recommendation_refactor_characterization.py
exit 0

git diff --check
exit 0
```

Pytest 曾回報 `.pytest_cache` 無寫入權限的 warning；不影響測試結果。既有 scoring 測試另有 pandas `FutureWarning`，未修改相關程式或測試。`git diff --check` exit 0；Git 對 working-copy LF／CRLF 顯示 normalization warnings，沒有 whitespace error。

SHA-256 scope：下列 hashes 僅涵蓋本 task 的兩個 changed Python 測試檔；本報告不嵌入自身 hash，避免自我參照。沒有修正其他範圍外問題。

| Changed test file | SHA-256 |
|---|---|
| `tests/test_task_loop_03_contract.py` | `63F3630C1FFE869821E5F445D42988EE38C696669D7C08FBBEA1ADEED084F4E0` |
| `tests/test_recommendation_refactor_characterization.py` | `E438EE6B742D73C1676FEBAF85314F1B7048A1293D7C7D9605CC57EDFA8B37E5` |

IMPLEMENTATION_STATUS: READY_FOR_REVIEW
