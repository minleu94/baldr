# R011 — SOL 整合驗收

TASK_STATUS: PASS

## 凍結版本與實際範圍

主線 HEAD：`fbc4047b6d0e5c31d64164e95987a6ff1a15f104`。R011 僅修改 `app_module/recommendation_service.py`，新增 `app_module/recommendation/execute.py`、`tests/test_recommendation_execution_use_case.py` 與實作報告；未改保存 writer、consumer、ML ABI、正式資料或其他任務的檔案。三個程式／測試檔 SHA-256 依序為 `4C82F56243918A33034247BF51C2E671EBDD52F7CA0013B1A6801F5F5BA5EE90`、`5BFDF952AF5BC8E1A570CDE52BF06B21309A9586DD1B3F0F61150A2314486B5D`、`5626C56264588495A3D7515652FED059AD2380A96177BDC215A60E65FF6FCFC2`。

## 驗收結論

- 實際呼叫圖是舊 list façade → `execute_recommendation` → 單一 `_run_recommendation_body` → 同次 capture／深凍結 execution → 舊 DTO 投影；沒有遞迴或第二套計算。以基準 commit `5e2d2efcfdc91c5e29810eb823b1c582199a44cc` 的舊 `run_recommendation` 與新私有 body 做 AST 比對，兩者各 856 行且 AST 完全相同。
- R002 固定／quantile 數值、型別、Decimal exponent、排序和 result ID oracle 保持通過。TMP-REC-06 補上隔離的原 body／新 façade paired harness，使用兩個 service 與不同暫存根；TMP-REC-01／02／06、TMP-NUM-01 都有明示 owner 與退出條件。raw screening matrix 暫時同時存在 typed assessment 與 compatibility event，由 R019 收斂，不能視作兩份獨立事實。
- A/B invocation 的 execution 與舊 `last_*` 投影各自綁定；空結果、preflight error、body error、取消與巢狀變更不誤發布完成結果。來源無法證明 typed identity 時明示 `legacy_source_identity_unbound`，不猜測資料版本。
- ML 原有 build／infer／receipt 次序未更動。真實 create-only receipt 已寫入／讀回後遇到 active identity race 時，execution 保留同次驗證過的 receipt binding 與錯誤 event，ML availability 為 unavailable；不重讀最新 pointer 猜測。`_safe_contract_value` 對未知型別、非字串 key、循環與非有限 numeric 均 fail closed；原本文字 `nan` 仍是文字。
- 獨立 Luna 對最終四檔 SHA 的 [複審](R011_LUNA_FINAL_REVIEW.md) 為 `REVIEW_STATUS: PASS`。SOL 另跑 V-REC／V-EXEC、R008/R009 codec、校準來源／guard 的 14 檔批次：**155 passed**，兩則既有 pandas FutureWarning；R002/R003/R011 單獨批次 **30 passed**。真實 completed／cancelled／failed execution 均已做 encode/decode equality 與 canonical bytes roundtrip。changed Python `py_compile`、兩個 R011 source 的 `mypy --follow-imports=skip`、`git diff --check` 均通過。

## 已知基線缺口與界線

完整 `tests/test_recommendation_service_calibration_integration.py` 中 **6 passed、6 failed**；六個失敗全部在 `tests/natural_session_source_fixture.py:130` 建立 natural evidence 時發生，既有 `evaluation_day="2026-06-22"` 早於 exact-20 session endpoint，尚未進入 RecommendationService。該 fixture／測試檔未受 R011 修改；R011 的實際 ML receipt/race 測試及有效日期的 6 個 integration 測試通過。此既有 fixture 問題未被當成 R011 修復，也不能將全檔測試宣稱綠燈。它不改變本次 service／receipt 接線的 focused gate 結論，後續 C1 應繼續具名分帳。

R011 的來源與 ML prepare 完整抽離仍屬 R018／R026，legacy façade／`last_*` 退休屬 R029；本次 PASS 不宣稱那些後續任務已完成。未 stage、commit 或 push。
