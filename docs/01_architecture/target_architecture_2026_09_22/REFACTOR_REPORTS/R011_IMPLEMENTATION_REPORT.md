# R011 實作報告

> **狀態時點提示（2026-10-11）：** `READY_FOR_REVIEW` 及本文後段「review 尚未完成」是實作者交付快照，已由後續獨立 review 與 SOL 整合 gate 覆蓋。R031 現行 disposition 為 `ACCEPTED_WITH_RETAINED_COMPATIBILITY`；本文 TMP 表格中的後續 owner／待移除描述，請以 [R029 report](R029_IMPLEMENTATION_REPORT.md) 與 [FINAL migration ledger](../FINAL_MIGRATION_SEQUENCE.md) 的後續裁定判讀。複審見 [Luna final review](R011_LUNA_FINAL_REVIEW.md) 與 [SOL acceptance](R011_SOL_INTEGRATION_ACCEPTANCE.md)；現況見 [R031 31-task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 及 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md)。本報告保留原始實作證據。

TASK_STATUS: READY_FOR_REVIEW

## 範圍與呼叫路徑

R011 保留公開介面 `RecommendationService.run_recommendation(...) -> list[RecommendationDTO]`。舊 DTO list 由同一次 invocation 的 capture 投影而來；推薦計算 body 只執行一次。

```text
RecommendationService.run_recommendation
  -> execute_recommendation(service, config, cancel?, progress?)
       -> 建立本次 invocation 的 service view
       -> 呼叫 _run_recommendation_body(...) 一次
       -> 深拷貝本次 DTO 與 legacy last_* 狀態
       -> 建立並凍結 RecommendationExecution
  -> 在鎖內成組發布本次 last_* 狀態
  -> 由同一 execution/capture 投影 legacy list
```

Body 例外會產生 `FAILED` execution 及錯誤事件，舊 façade 再重拋原始例外。驗證若在 body 清除 buffer 前失敗，不發布 invocation view，先前 `last_*` 保持不變；清除後的錯誤則發布本次已清除或累積的狀態，維持舊有時序。空結果仍是 completed execution 和空 decision。開始前取消不呼叫 body；body 完成後取消則保留 receipt/evidence 事件但不發布 decision。

Canonical execution 保存 typed items、assessments、quality、context 和 receipt bindings。舊 DTO 才有的欄位、原數值型別及精度順序由短命同次 sidecar 保留。Parity oracle 鎖定 `np.float64(91.5)`、`Decimal("70.0100")` 及 tie 順序；現有策略、評分、排名、top-N、篩選和 ML provider/build/infer 呼叫仍在原計算 body，未改演算法。只有 typed contract 邊界會以 `Decimal(str(value))` 轉成 canonical 數值，legacy list 保留原型別和值。

Execution evidence 使用嚴格 allowlist：mapping key 必須是精確 `str`；Python bool/int/float、`Decimal`、日期時間、字串及 list/tuple 有明確處理；支援的 NumPy bool/integer/floating/string scalar 也有明確轉換。所有數值必須有限，非有限 `Decimal`、float、NumPy 浮點值會拒絕封存；既有字串 `"nan"` 仍以字串保留。DataFrame、callback、自訂物件、非字串 key（包括字串化後會碰撞的 key）皆 fail closed，不會被轉成 repr 文字。

不會把舊 source 名稱或 fingerprint 冒充 typed source/data snapshot reference；目前以 `legacy_source_identity_unbound` 明示尚無可驗證的來源身分。只有 invocation context 已提供 universe policy/snapshot identity 和 members hash 時才帶入對應 universe reference。

## Invocation 狀態、side effects 與臨時元件

每個呼叫在隔離 service view 中更新可變 `last_*`，execution 與 sidecar 在 worker 返回前複製。Façade 在 service state lock 內成組發布 capture，避免 A/B 混合狀態。`_personalization_execution_clocks` 由 body 每次重新指派並隨同次 capture 保存。Fundamental SQLite provider 維持跨 run lazy cache；invocation view 委派到原 service 的鎖定 accessor，避免改成每次呼叫各自初始化。

Calibration 繼續沿用原 consumer、builder、inference、receipt 呼叫順序。Capture 記錄候選 identity、確切 receipt path/hash/payload、create-only 寫入結果、readback 驗證、建立時間及 post-write identity 驗證。Execution 僅綁定本次讀回且 hash 驗證的 receipt，包含本次 result ID、日期、candidate、cost hash 及 stock codes。若寫入後候選 identity 發生 race，execution 仍保留綁定到已驗證 payload 的 receipt evidence/ref，ML availability 標示 unavailable；不掃目錄或重讀 latest pointer 猜測綁定。R011 未發布新 artifact，也未修改 repository/save 路徑。

| 臨時元件 | R011 狀態 | Caller／證據 | 移除 owner |
|---|---|---|---|
| `TMP-REC-01` | `app_module/recommendation/execute.py` 中的 invocation-scoped body/capture | `RecommendationService.run_recommendation` | R019 以直接組裝 canonical execution 取代 capture 重建。 |
| `TMP-REC-02` | Legacy list façade 與 `last_*` 相容狀態仍保留 | `ui_qt/views/recommendation_view.py` 讀 context/negative evidence（2537、2621–2627、2676、2833、2894）；`app_module/recommendation_save_coordinator.py` 讀 negative evidence（89–104）及 context（124–137）；`app_module/application_ports.py` 宣告 state port（16–22）。 | R029，待 caller 遷移及相容性檢查完成。 |
| `TMP-REC-06` | 僅測試使用的 paired harness 以固定輸入與 clock，分別在不同 service 和 `tmp_path` 執行 preserved legacy body 與 execute façade；比較 DTO payload/type/order、result/context 及 negative-evidence 狀態。不做 production dual-run 或正式資料寫入。 | `test_tmp_rec06_paired_legacy_and_execution_lanes_match_with_isolated_side_effects` | R029；caller cutover 後依 ledger 保留單一路徑 regression oracle。 |
| `TMP-NUM-01` | Legacy numeric-to-typed 邊界在 sidecar 保留原 DTO 數值，canonical contract 使用 decimal-string 轉換；原計算與 rounding 不變。 | Legacy `RecommendationDTO` façade 與 typed `RecommendationItem` | R019/R029；必須等獨立數值 gate 通過，否則繼續列管。 |

未修改 application port；其 legacy 欄位待 caller 遷移後處理。未修改 provider、evaluator、persistence writer、consumer、ML ABI 或正式資料。

目前 raw screening matrix 同時放在相容事件 `legacy_negative_evidence_capture`，並作為 typed `CandidateAssessment` 的來源。這是 TMP-REC-01 過渡期間的重複表示，不是兩個權威結果庫。R019 負責合併 ownership：由 engine 單次產生 assessments，只在仍需支援 legacy façade/caller 時保留額外矩陣證據，並於 caller 遷移後移除重複的 raw matrix event payload。

## 測試與驗證

R011 在 `tests/test_recommendation_execution_use_case.py` 新增 9 項測試：execute/body 單次呼叫和 façade parity；不遞迴及 deep-freeze；未知物件、非字串 key、非有限 numeric 的 fail-closed 與 NumPy scalar 轉換；TMP-REC-06 paired harness；empty/pre-start cancel；preflight state 與 body exception；post-body cancel；A/B interleave；以及真實 create-only receipt/readback、post-write identity race、另一 invocation binding 和 receipt 後取消。

| 驗證 | 結果 |
|---|---:|
| R002 characterization + R003 execution-state characterization + R011 use-case tests | **30 passed**（8 + 13 + 9） |
| R008 contracts/enum + R009 codec + R004 persistence + R006 ML baseline + data/ML contract interfaces | **121 passed** |
| Calibration source-contract 與 contract-guard tests | **33 passed** |
| Calibration integration 中不使用已知錯誤日期 fixture 的測試 | **6 passed，6 deselected** |
| `py_compile`：service、execute、R011 test | **passed** |
| `mypy --follow-imports=skip`：兩個 R011 source files | **passed，2 files 無問題** |
| `git diff --check` 及新 Python 檔 trailing-whitespace scan | **passed** |

完整 `tests/test_recommendation_service_calibration_integration.py` 曾得到 6 passed、6 項既有 fixture failure；失敗發生在 recommendation service 執行前。測試為 `test_real_consumer_producer_advice_workbench_ui_path`、`test_public_service_real_builder_saves_result_and_reverse_reads_receipt`、`test_active_training_label_contract_missing_or_mismatched_fails_closed`、`test_active_training_label_contract_missing_from_provenance_fails_closed`、`test_real_consumer_rejects_future_research_candidate_context`、`test_real_consumer_independent_after_cost_baseline_reaches_advice_presentation`。共同 stack 由 `test_daily_recommendation_learning_loop.py:236` 進入 `tests/natural_session_source_fixture.py:130`，其中 `evaluation_day="2026-06-22"` 早於至少一個 exact-20-session endpoint。這些 test/fixture 不在 R011 scope，均未修改。新的 R011 receipt test 使用較晚且有效的 evaluation date，會實際執行 service receipt writer 和 readback。

一般 scoped mypy 另有四個 R011 外既有錯誤：`analysis_module/technical_analysis/technical_indicators.py:198,200,205` 的 TA-Lib enum argument type，以及 `app_module/update_service.py:152` 缺少區域型別註記。`--follow-imports=skip` 隔離兩個 R011 source 後通過。

## 凍結範圍與 rollback

凍結時 shared main HEAD：`fbc4047b6d0e5c31d64164e95987a6ff1a15f104`；由 R011 指派 HEAD `5e2d2efcfdc91c5e29810eb823b1c582199a44cc` 前進的其他變更不在本任務 scope。R011 開始前 service clean baseline SHA-256 為 `7578D7EE6E1EF6128E895092E44C0416CB98B3E00558C880B551445F30B756D3`。

Rollback 僅限 R011 diff：將原 body 還原為 `RecommendationService.run_recommendation`，移除 invocation hook/provider lock change，刪除 execute module 和 use-case tests，以及本報告。不得 reset、clean 或 revert 其他 working-tree changes；未 stage、未 commit。

`READY_FOR_REVIEW`；本報告不代表 R011 PASS。獨立複核與 SOL integration gate 尚未完成。
