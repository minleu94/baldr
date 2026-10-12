# R026 Post-calibration typed handoff

## 狀態

`POSTCALIBRATION_HANDOFF_ACCEPTED_FOR_NOMODEL_NP1`

此狀態只代表 typed handoff consumer/producer 整合 slice 已接受，後續 NoModel/NP1 繼續進行；不代表 R026、C1 或 Wave6 全體通過。

## 變更與保證

- 新增 `app_module/recommendation/ml_postcalibration_handoff.py`：immutable invocation facts、一次性 sink、既有 receipt references 與 availability 投影。
- 修改 `app_module/recommendation/execute.py`：只由 typed handoff 建立 ML availability、receipt refs 與 receipt event；不從 R011 capture 或共享 `last_run_context` 推導 ML truth。Execution wire/schema 與 `RecommendationBodyResult` 未變。
- 新增 `tests/test_ml_postcalibration_handoff.py`；修改 `tests/test_c1_execution_artifact_ab_interleave.py`，把 synthetic receipt producer 改為當次 typed sink，保留原 receipt bytes、identity、create-only save 與 readback assertions。
- 符合原 readback/result/date/path/hash/candidate/stocks 條件時，即使 `identity_verified=False` 仍保留 receipt/projection refs；`AVAILABLE` 另要求 identity 驗證成功。Receipt event 的 nested JSON 浮點仍以 `Decimal` 正規化並將 list 轉 tuple。

## 驗證結果

所有 pytest 均使用新 synthetic TEMP。C1 no-follow/readback route 以 escalated sandbox 執行，因 Windows no-follow handle 需開啟 `C:\Users\archi` 祖先目錄；`DATA_ROOT`、`OUTPUT_ROOT` 與 pytest temp 指向 TEMP。

| 路由 | 命令／結果 | Log 與 SHA256 |
|---|---|---|
| Handoff unit | `pytest tests/test_ml_postcalibration_handoff.py -q -o addopts= -p no:cacheprovider` — **38 passed** | `C:\Users\archi\AppData\Local\Temp\r26h_f85e12\pytest.log` — `F658304265018DF564CC5FC9ADC2DD76106F96FE38AE4ABAC438CEFE926FC7D4` |
| Consumer + C1 artifact/readback | `pytest tests/test_ml_postcalibration_handoff.py tests/test_recommendation_execution_use_case.py tests/test_recommendation_execution_codec.py tests/test_recommendation_contracts.py tests/test_c1_execution_artifact_ab_interleave.py tests/test_c1_ml_abi_receipt_readiness.py -q -o addopts= -p no:cacheprovider` — **162 passed in 6.96s** | `C:\Users\archi\AppData\Local\Temp\r26exec_ab0ff975\focused.log` — `1B8F66AAF3332F4192812C4349138B2DF1EC54A47FA50324EA37E33A3225A39F` |
| Producer failure + real service receipt save/readback + execution event | `pytest tests/test_recommendation_service_calibration_integration.py::test_active_projection_receipt_build_failure_withdraws_model_fields_but_keeps_rule_selection tests/test_r026_prepared_runtime_service.py::test_service_opt_in_prepared_runtime_persists_and_reads_receipt tests/test_recommendation_execution_use_case.py::test_verified_receipt_binding_survives_post_write_identity_race_without_a_b_cross_link -q -o addopts=` — **4 passed in 4.79s**; build-failure event has `attempted=False`, handoff attempt remains true | `C:\t\r026_servicehandoff_20260925_04\focused.log` — `6A3FFE47E29843091CF54DCD2C1F710DDC6F70DDD3C53B8132A2326C26FC1E71` |
| Service/coordinator/prepared-runtime | `pytest tests/test_recommendation_service_calibration_integration.py tests/test_recommendation_execution_coordinator.py tests/test_r026_prepared_runtime_service.py -q -o addopts= -p no:cacheprovider` — **21 passed in 14.45s** | `C:\Users\archi\AppData\Local\Temp\r26svc_0da3cc9f\service-focused.log` — `251E888BF2FA4426D33A7538B895B56442EB7ADC8E82D5455A974F142F27A849` |
| A/B fixture seam after final type-access edit | `pytest tests/test_c1_execution_artifact_ab_interleave.py::test_c1_ab_capture_create_only_save_and_single_readback_keep_identity -q -o addopts= -p no:cacheprovider` — **2 passed in 1.24s** | `C:\Users\archi\AppData\Local\Temp\r26ab_d006461c\ab.log` — `5BA7BD870147014507DC265AAC69E39B1CD6CD7A291FC859E301799BF56E7311` |
| Scoped static checks | `mypy execute.py ml_postcalibration_handoff.py test_ml_postcalibration_handoff.py` — clean; `py_compile` on those files plus the C1 fixture — exit 0; `git diff --check` on modified tracked files — exit 0 | Mypy log `C:\Users\archi\AppData\Local\Temp\r26finalcheck_ec7f43\mypy.log` — `281A094C39385B4D7B53E5DB635F52158036861433C2A4975B9039E77A627A24` |

### 初次失敗紀錄

首輪為 `147 passed, 15 failed`，log `C:\Users\archi\AppData\Local\Temp\r026exec_bc8be6b0\focused.log`，SHA256 `5D2C12DEE9D5DA78253844A06B0418E34DFBFC3ED0659EF23371A326DF737309`。兩個 A/B failure 是 fixture 只寫 R011 capture，已遷移為 typed sink；其餘 13 個 U4 failure 是 sandbox 無法開啟 no-follow ancestor handle（`CreateFileW failed for C:\Users\archi`, `Errno 5`），不是路徑長度。更正後的 escalated synthetic route 為上表 162 passed。

## 檔案 SHA256

- `app_module/recommendation/ml_postcalibration_handoff.py`：`22AF958D1978DCADFDE52A9110CB0FA3093D80138589856AD11AE9088F21C044`
- `app_module/recommendation/execute.py`：`401124F45A5E00302EF650F8BB501B48CA4474A81FA2C87AF0730095087E263F`
- `tests/test_ml_postcalibration_handoff.py`：`DA8822BB2EA609883D7FB1EDFEE08DDB622A0D61F5D21EE38612A54522B9335C`
- `tests/test_c1_execution_artifact_ab_interleave.py`：`CA1475488ECA057DCA9FFC20C0F507FA29464627CD8D8DF2567F280A366B2ABB`

## 後續 supported handoff 狀態（2026-10-10）

本文件 `POSTCALIBRATION_HANDOFF_ACCEPTED_FOR_NOMODEL_NP1` 記錄本 consumer/producer integration slice 的接受；當時 NoModel／NP1 的後續狀態不是目前整體 handoff 狀態。依 [R026 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R026_IMPLEMENTATION_REPORT.md) 與 [R031 final closeout](R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)，正常 `RecommendationService` 的 NP1／NP2 supported caller/profile typed handoff 遷移條件後續已 `CLOSED`。此結論不代表所有 runtime profiles、R026 source-evidence slices、C1 或 Wave6 全體通過。
