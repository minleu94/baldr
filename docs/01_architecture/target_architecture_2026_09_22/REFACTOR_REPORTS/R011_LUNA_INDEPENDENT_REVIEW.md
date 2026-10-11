# R011 Luna independent review

> **狀態時點提示（2026-10-11）：** 本文 `REVIEW_STATUS: CHANGES_REQUIRED` 是較早凍結 SHA 的初次複審及 finding 記錄；後續 [R011 final review](R011_LUNA_FINAL_REVIEW.md) 對修正版為 PASS，並由 [SOL integration acceptance](R011_SOL_INTEGRATION_ACCEPTANCE.md) 接受 R011 有界範圍。R031 現行 disposition 為 `ACCEPTED_WITH_RETAINED_COMPATIBILITY`；後續相容／TMP 裁定見 [R029 report](R029_IMPLEMENTATION_REPORT.md) 與 [FINAL migration ledger](../FINAL_MIGRATION_SEQUENCE.md)。初次 finding 不再代表目前未解 blocker，原文保留。

REVIEW_STATUS: CHANGES_REQUIRED

## 審查基準

本次審查針對 R011 凍結產物，不把後續主線變更混入 R011 diff。審查時 HEAD 為 `85e2be8a2a93f5e0eef989710efa57f62bfe9109`，相對實作報告記錄的 `eaf3ad24ffee0f289bdf876fb9033845b1bb2632` 有前進；依派工者確認，該段改動不與 R011 路徑重疊。三個 R011 檔案 SHA-256 與指定凍結值相同：

| 檔案 | SHA-256 |
|---|---|
| `app_module/recommendation_service.py` | `4C82F56243918A33034247BF51C2E671EBDD52F7CA0013B1A6801F5F5BA5EE90` |
| `app_module/recommendation/execute.py` | `4158BB333F76B8EBC92230F5908BE457260F8062018133C974C2FD24C1FAF83E` |
| `tests/test_recommendation_execution_use_case.py` | `AC39441086DB4A4380BC2DDF8CEDB6487CEC5E86AB8F7587D916BE53C4269C4A` |

已檢查 R011 task、implementation report、FINAL_ARCHITECTURE_INVARIANTS、FINAL_MIGRATION_SEQUENCE、實作呼叫圖及 R002/R003/R008/R009 測試。未發現需要改架構的證據；以下兩項必須在原 R011 scope 內修正或補足，之後以新 SHA 重審。

## 必須修正

### R11-REV-01 — unknown evidence 型別被字串化，繞過明確拒絕

`app_module/recommendation/execute.py:829–853` 的 `_safe_contract_value` 對一般未知物件執行 `str(value)`；同一函式 `:838–839` 也把所有 mapping key 轉成字串。這削弱了 `decision_module/recommendation/contracts.py:97–108` 的封存規則：canonical mapping key 必須本來就是 `str`，不支援的型別必須拒絕。ExecutionEvent 與 CandidateAssessment 因而看不到原始型別錯誤，會把錯誤輸入接受為看似合法的文字 evidence。非字串 key 轉字串還會合併不同 key 並遺失資料。

最小可重現路徑已實際執行：將 `pd.DataFrame({'secret': [42]})` 和 callback 放入 `last_screening_matrix` row，交給 `_assessments` 與 `_capture_events`；兩者都成功，DataFrame 及 callback 的 repr 分別進入 `FilterOutcome.evidence` 與 `ExecutionEvent.details.screening_matrix`。另外 `_safe_contract_value({1: 'integer-key', '1': 'string-key'})` 回傳 `{'1': 'string-key'}`，整數 key 的值被靜默丟棄。此路徑沒有把 DataFrame/callback 的可變物件 alias 留在 execution；問題是把不允許的型別洗成合法字串並掩蓋型別／來源錯誤。

這是 INV-11 的 contract bypass，也違反 INV-08 對結果封存白名單的意圖。Production 的 `matrix_row` 目前將已知欄位轉成 str/list/int (`app_module/recommendation_run_support.py:19–55`)，所以沒有證據顯示一般資料路徑已注入 DataFrame；但 adapter 本身應 fail closed，不能依賴上游永不出錯。

最小修正與驗收：只保留明示允許的 primitive、Decimal/date/datetime、受控 float/NumPy scalar 轉換、str-key Mapping 與 list/tuple 遞迴；mapping key 必須要求 `type(key) is str`；其他型別一律 `TypeError`。新增 DataFrame、callback、任意自訂物件及 `{1: ..., '1': ...}` 的拒絕測試，並確認合法舊 matrix、NumPy scalar 與目前 execution codec roundtrip 仍通過。不要把未知物件 repr 存成文字。

### R11-REV-02 — TMP-REC-06 被宣稱完成，但沒有 legacy/new 雙路隔離比較

`FINAL_MIGRATION_SEQUENCE.md:34,160` 將 TMP-REC-06 定義為測試中的 legacy/new 隔離雙路比較 harness：同一 Block 1 固定輸入、各自隔離 side effects，不對正式 UI/scheduler 暴露第二 engine。R011 implementation report `:40` 卻以 R002/R003 characterization 與 R011 use-case tests 宣稱此項已有 parity evidence。

實際測試不是雙路比較：R002/R003 characterization 在 R011 變更後透過目前 public façade 執行；R011 的 façade parity test 則是 façade 投影同一個 `execute_recommendation` invocation capture。兩個測試都很有價值，但目前沒有一組 test 讓 legacy oracle 與 new execution 在隔離 fixture 上以同一固定輸入分別執行、再逐欄位比較。因此不能把目前測試描述成 TMP-REC-06 dual-path harness，也不能以新 façade 與它呼叫的 execute 互相比對來證明獨立 parity。

此缺口影響 R011 對 R002/R003 行為、DTO/negative evidence/context/result_id/排序數值 parity 的獨立證據，對應 INV-06、INV-07、INV-09、INV-17 及 FINAL_MIGRATION_SEQUENCE 的 Block 1／TMP-REC-06 驗證。最小補足是在測試 scope 建立 paired harness：兩路使用同一固定輸入與不同 `tmp_path`/service/副作用 fixture；legacy lane 使用凍結的 pre-R011 baseline body 或獨立保存的 legacy expected snapshot，new lane 執行 `execute_recommendation`；比較 DTO 欄位及數值型別／Decimal quantum、排序、result_id、matrix/negative-evidence/context 與 side-effect receipt identity。若 legacy lane 是固定 snapshot 而不是 executable baseline，測試及報告須明確標示 snapshot-oracle lane，不能稱為雙 engine 執行。保留現有單路回歸 fixture，不能讓兩路共用新 helper 後宣稱相等。

## 過渡重複與範圍判斷

`_assessments` (`execute.py:492–556`) 對每個 stock code 取 legacy screening matrix 的摘要 row，將該 row 的最終 `stage/status/reason_codes` 表示為一個 `FilterOutcome`；service 的 `matrix_row` 是每股票摘要列，會隨後續 gate 更新該列。因此它保留目前 legacy matrix 表達的最終 gate summary，並未證明也不應宣稱保存每個內部 filter 的逐步結果。未見 R011 相對目前 legacy 輸出丟失一份既有 per-filter log 的證據。

有一項明確但可接受為過渡的重複表示：同一完整 raw matrix row 同時放入 typed `CandidateAssessment.FilterOutcome.evidence` (`execute.py:519–526`) 和 `ExecutionEvent.details.screening_matrix` (`:425–449`)；event 還攜帶從 matrix 派生的 excluded/why-not/liquidity payload。這增加 execution payload 並形成雙份資料表達。暫時保留可以支援 legacy fidelity，但 implementation report／退休帳應把它明列為 TMP-REC-01 capture/assembly bridge 的殘餘風險，移除 owner 為 R019 的 direct canonical execution assembly：保留 typed assessments，event 只保留無法由 typed contract 表達的 legacy-only payload；完成前不得把兩份內容視為不同來源的獨立證據。

## 其餘審查結果

- `run_recommendation → execute_recommendation → _run_recommendation_body` 只執行一次；execute 不呼叫 public façade。公開 list 從相同 invocation capture 投影。`copy(service)` 的 mutable last-state 欄位在 body reset/rebind 後於 invocation view 寫入；`_personalization_execution_clocks` 在 body 內重綁後才寫入；共用 fundamental provider initializer 是刻意沿用原 service 的受鎖 lazy cache。未發現本次可見的 shallow-copy last-state alias 越界。
- legacy DTO 保留在同次 sidecar，因此 `np.float64(91.5)`、`Decimal('70.0100')` 與 tie order 可由 façade 原值回傳；typed execution 的 Decimal 轉換不改 façade 數值。R002 的固定輸出測試與 R011 parity 用例通過。
- R011 對來源 identity 未能型別證明時保留 `legacy_source_identity_unbound`，沒有從 live pointer/path 猜造 typed source ref。receipt 在同次 invocation capture 寫入 payload/hash/readback；post-write identity race 維持已驗證 receipt binding 並將 ML 標 unavailable，沒有事後掃描或讀 latest pointer。未發現 receipt 時序或 A/B cross-link 的具體反例。
- R008 deep-freeze 的巢狀 mutation、R011 A/B interleave、preflight/body failure、empty/cancel、recursion guard 測試已執行。另以真實 service 產生的 execution 執行 R009 `encode_execution`／`decode_execution`，結果 equality 通過（9909 bytes、2 events、2 assessments）。
- 全量 calibration integration 重跑為 6 passed、6 failed；六個失敗均在 `test_daily_recommendation_learning_loop.py:236` → `tests/natural_session_source_fixture.py:130` 建立 fixture 時發生，因 `evaluation_day="2026-06-22"` 未晚於 exact-20 session endpoint，尚未進入 RecommendationService。未修改該 fixture；有效日期子集 6 passed。

## 實際驗證

- R002/R003/R011 execution/coordinator focused suite：30 passed。
- Recommendation contracts、codec、R004 persistence、R006 ML baseline、prepared-ML/data contracts：95 passed。
- Calibration integration：6 passed；另 6 個上述既有 fixture failure 發生於 service 呼叫前。
- R011 source/test `py_compile`：passed；`mypy --follow-imports=skip`：2 個 R011 source files 無錯誤。
- 以 service 實際 execution 做 codec encode/decode roundtrip：passed。
- 輸入 DataFrame/callback 到 assessment/event 的 fail-open 最小重現：passed（即確認 finding）；非字串 key 碰撞／遺失最小重現：passed（即確認 finding）。

## 重審條件

修正 R11-REV-01，補上或如實限定 TMP-REC-06 的獨立 parity 證據，並將 raw matrix 雙重表示列入具名 TMP-REC-01／R019 退休條件後，請依新檔案 SHA 重跑受影響 focused tests 並重新獨立審查。此狀態只適用上述凍結 SHA；本報告沒有要求改動架構，也沒有標記 R011 PASS。
