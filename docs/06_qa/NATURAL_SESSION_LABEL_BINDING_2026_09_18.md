# Natural session label binding QA — 2026-09-18

## 範圍

本次只驗證 natural forward label 將 20 個官方交易 session 綁定到同一個唯讀 TAIEX SQLite source，並由個股 provider 精確讀取 `capture_date` 與 resolver 回傳的 `endpoint_date`。沒有人工改寫正式 capture、receipt、DB、pointer、scheduler 設定或 UI；wrapper／CLI 程式修正與既有排程自然產出的 readback 分開記錄。

主要程式位置：

- `ml_module/recommendation_natural_outcome_service.py:770`：`_outcomes_for_capture` 先取得 strict session resolution，再核對 provider SQLite path、`size`、`mtime_ns`，個股只接受 capture 日與 exact endpoint 日的單一正數收盤價；benchmark 僅使用 proof 的 baseline／endpoint TAIEX observation。
- `ml_module/recommendation_natural_outcome_service.py:988`：evaluation clock 必須為 aware datetime，Taipei 日期須等於 evaluation day，future clock 與缺 resolver 都 fail-closed；resolver 呼叫固定 horizon `20`。
- `ml_module/recommendation_calibration_evidence.py:1963`：source database 只由已驗證 capture source contract 取出；`verify_natural_maturity_session_proof` 固定拒絕非 20-session proof，再委派 B resolver 重驗同一 cache／SQLite bytes。
- `ml_module/recommendation_calibration_authority.py:1095`、`:1390`：receipt 必須含 aware `evaluation_at`、resolver identity 與每列 session proof；authority 以 verified capture contract 的 `source_database` 作 expected anchor，缺失、舊 receipt、偽造或不匹配 proof 不採用。
- `app_module/recommendation_learning_evidence_projection_service.py:467`、`:1314`：active read projection 只從既有 config `db_file` 傳 source anchor；沒有設定 anchor 時維持 blocked，不接受 receipt 自報路徑。

## 真實 bounded fixture

`tests/test_natural_outcome_session_binding.py` 建立唯讀測試 SQLite、官方 annual cache 與 `NaturalMaturitySessionResolver`，使用 20 個精確 official sessions。個股只寫入 capture 日與 20th session endpoint，中間個股日期缺列不會滑到下一筆；另覆蓋 endpoint 缺失與 evaluation clock 日期不一致。proof 驗證會重讀原始 annual cache／bounded TAIEX rows，並由 producer 使用同一 source snapshot。

`tests/natural_session_source_fixture.py` 提供共用的真實 source-contract fixture：
`make_verified_natural_fixture(tmp_path, capture_dates, evaluation_day, ...)` 會回傳
resolver、20-session proof、capture input、source binding 與 exact endpoint；
`make_verified_source_binding(...)` 可讓 cost fixture 綁定自己的既有 SQLite。daily-loop
fixture 先以 `candidate_day - 1 day` 篩除尚未可用的 label，再以同一 subset 計 dataset
hash、fit artifact 與 training lineage，沒有用 future label 或 no-op verifier 補通過。

## 執行結果

- C-owned daily-loop bounded slice：**25 passed / 2 deselected**（A 接手的 active monitor 與 daily-main 函式），1 個 pytest cache permission warning；原始輸出：[daily_owned_final.txt](../../output/qa/natural_session_binding_20260918/daily_owned_final.txt)。
- focused resolver + producer integration：**11 passed**；原始輸出：[focused_pytest.txt](../../output/qa/natural_session_binding_20260918/focused_pytest.txt)。
- 核心合併驗證（含 A daily-main、B cost 29 cases、resolver 11 cases、wrapper 與 source-contract coverage）：**168 passed**；原始輸出：[core_combined_final.txt](../../output/qa/natural_session_binding_20260918/core_combined_final.txt)。這是合併 suite 的總數，不能再把 component count 加回去。
- standalone natural CLI 真實 provider fixture：**3 passed**（strict resolver/source positive、missing calendar、historical evaluation-date mismatch）；原始輸出：[natural_outcomes_cli.txt](../../output/qa/natural_session_binding_20260918/natural_outcomes_cli.txt)。核心與 CLI 合計為 **171 passed**，兩者測試檔不重複。
- 2026-09-18 原排程 EOD research capture 的 bounded readback（觀測時間
  2026-09-18T12:26:13Z）為 status=`passed`／receipt=`complete`；run_id
  `20260918T122502797364Z-414cfa43c1b0`，兩個 child returncode=0、events
  `1098/1098`、duplicates=0、failures=0、snapshot saved=true 且
  sections_missing=[]。quality 為 degraded=1080、estimated=3、observed=15、warnings=702；
  receipt SHA-256=`95bc1d0addebe391e06be5b4a0b6353beca4c385ea493d7611c8dd8605cf2533`。
  這是 research-only capture、`natural_authority=false`，audit 未觸發 scheduler 或正式
  source 寫入；原始檔：[readback_20260918T1226Z.json](../../output/qa/decision_evidence_capture_readback_20260918/readback_20260918T1226Z.json)。
- fixture／daily test `py_compile`：exit 0；原始輸出：[py_compile_fixture.txt](../../output/qa/natural_session_binding_20260918/py_compile_fixture.txt)。
- scoped mypy（natural service、calibration evidence、authority、projection、resolver）：`Success: no issues found in 5 source files`；原始輸出：[mypy_final.txt](../../output/qa/natural_session_binding_20260918/mypy_final.txt)。
- scoped production mypy：核心 12 files `Success: no issues found`；原始輸出：[mypy_12_final.txt](../../output/qa/natural_session_binding_20260918/mypy_12_final.txt)。standalone CLI script 另以 explicit package bases 驗證 clean；原始輸出：[cli_mypy_final.txt](../../output/qa/natural_session_binding_20260918/cli_mypy_final.txt)。
- CLI script／test `py_compile` exit 0；原始輸出：[cli_compile.txt](../../output/qa/natural_session_binding_20260918/cli_compile.txt)。
- float／look-ahead quant guard exit 0；global ML shadow boundary 只讀檢查 518 files 時保留 4 項既有跨層 import residual，exit 1，沒有以本輪 allowlist 掩蓋；原始輸出：[quant_guard_final.txt](../../output/qa/natural_session_binding_20260918/quant_guard_final.txt)、[shadow_boundary_final.txt](../../output/qa/natural_session_binding_20260918/shadow_boundary_final.txt)。
- 原始 affected baseline 的 73 tests 及早期 **60 passed / 13 failed** 只保留為修復前歷史基線；收集證據：[affected73_collect.txt](../../output/qa/natural_session_binding_20260918/affected73_collect.txt)。目前以 168 core + 3 standalone CLI 為準，不再把該歷史失敗描述成現況。
- B 的 29 cost cases 與 11 resolver cases 已包含在核心 168 passed；compact／ISO `BETWEEN` 格式／長度限制、canonical bounded guard 與跨年等價 regression 均以 compact fixture 驗證，沒有以改成 ISO 繞過來源契約。

## 核心合併與 standalone CLI 驗證檔案清單

核心 168-case runner 已在同一 working tree 執行下列範圍；standalone CLI 3-case
另以真實 `MLHistoricalSnapshotProvider` fixture 獨立執行：

1. 原 affected 73 tests：
   - `tests/test_daily_banktaiwan_learning_cost.py`
   - `tests/test_daily_recommendation_learning_loop.py`
   - `tests/test_recommendation_learning_evidence_projection.py`
2. 新 strict session／producer tests：
   - `tests/test_natural_maturity_session_resolver.py`
   - `tests/test_natural_outcome_session_binding.py`
3. wrapper／caller coverage：
   - `tests/test_scheduled_decision_evidence_capture.py`
   - `tests/test_scheduled_forward_outcomes.py`
   - `tests/test_recommendation_natural_outcomes_cli.py`
4. 原 B maturity／calendar 與 source-contract compatibility coverage：
   - `tests/test_forward_performance_service.py`
   - `tests/test_outcome_maturity_service.py`
   - `tests/test_official_maturity_calendar.py`
   - `tests/test_recommendation_calibration_contract_guards.py`
   - `tests/test_recommendation_calibration_source_contract.py`
5. 對應 production compile／mypy scope（12 files）：
   - `app_module/forward_performance_service.py`
   - `app_module/official_maturity_calendar.py`
   - `data_module/natural_maturity_session_resolver.py`
   - `ml_module/recommendation_natural_outcome_service.py`
   - `ml_module/recommendation_calibration_evidence.py`
   - `ml_module/recommendation_calibration_authority.py`
   - `app_module/recommendation_learning_evidence_projection_service.py`
   - `app_module/scheduled_forward_outcome_service.py`
   - `scripts/scheduled/run_scheduled_decision_evidence_capture.py`
   - `scripts/scheduled/run_scheduled_forward_outcomes.py`
   - `scripts/scheduled/run_daily_recommendation_learning.py`
   - `scripts/scheduled/run_recommendation_natural_outcomes.py`

## 邊界與後續

舊 mature receipt 可以被讀取作歷史診斷，但缺 resolver proof 不得進入新 natural adoption。沒有 official calendar、TAIEX baseline／endpoint、stock exact endpoint、source contract anchor 或 evaluation clock 時維持 pending／blocked；不以 row offset、weekday fallback、self-reported DB path 或 synthetic proof 補 credit。
