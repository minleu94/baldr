# R020 後置過濾的延遲 threshold stage contract

## 範圍

本切片只在 `RecommendationEvaluator` 新增純 staged post-score 輸入契約。它讓 app
先提供「哪些 threshold 尚未解析」的順序清單，再由 evaluator 一次要求當前規則的
threshold。app 可在收到 request 後才解析該值；解析若依舊流程拋錯，例外仍在 app
resolver 的呼叫點發生。

此變更沒有接線 `RecommendationDataFrameProvider`、`StrategyConfigurator` 或其他 live
route，沒有改 scorer、DataFrame、浮點核心計算、wire/codec 或交易邏輯，也沒有宣告
R020、TMP-REC-04、TMP-NUM-01 或完整 V-REPLAY 已驗收。

## 契約與保留的行為

- `ReplayPostScorePolicyV1` 維持原 eager 契約，仍拒絕 `PENDING` threshold。
- 新的 `ReplayPostScoreDeferredPolicyV1` 以既有 eager policy 表示已解析值，另以依序
  的 `deferred_rules` 表示設定存在但尚未解析的欄位。deferred slot 必須先留在 disabled
  狀態，不能偷偷塞入 raw config 或非 typed 值。
- `NeedReplayPostScoreThresholdV1` 綁定同一 `NeedCandidateScoring` 與一個 rule。只有該
  request 可由 `ReplayPostScoreThresholdResponseV1` 回填；deferred response 只接受
  `ENABLED` 或明示 `UNSUPPORTED`，不可用 `DISABLED` 清除已宣告存在的 filter，也不可仍 pending。
- staged 與 eager API 共用單一 `_evaluate_replay_post_score_rule` comparator path，且保留
  price min、price max、volume、RSI min、RSI max 順序。較早規則拒絕後仍會要求後續
  deferred threshold，對應 legacy 後續比較仍可能執行並拋錯的特性。
- 只有真正 `MISSING_COLUMN` 的 metric 可略過 deferred threshold；欄位存在但 metric
  `UNSUPPORTED` 時，evaluator 先要求該 threshold，再於回填後回傳 unsupported terminal。
  RSI 欄位缺失時不必解析 RSI threshold。request/response 錯接候選或 rule 會 fail closed。

## Legacy 證據與測試

舊行為由既有 characterization 提供獨立基準：`test_diagnostic_warning_precedes_final_empty_rsi_error`
固定 price-min diagnostic warning 先發生，之後 final filter 在空列上遇到無效 RSI
threshold 仍拋 `TypeError`；`test_diagnostic_price_warning_and_counter_precede_empty_volume_error`
固定空 Series 上的後續 volume threshold 錯誤與 warning/counter 順序。兩者均在本次相鄰
路由中執行，pure staged tests 不重建或取代這些 legacy oracle。

新增測試驗證：

1. evaluator 先要求 price-min，再要求 price-max；price-min 已拒絕時仍保留其 outcome，
   app resolver 只在 price-max request 到達時才解析該值。
2. 缺少 RSI 欄位時不產生 RSI threshold request，並回傳 `SKIPPED_MISSING_COLUMN`。
3. 回填 request 必須符合同候選與同 rule。
4. 所有 deferred threshold 完成解析後，staged outcome 等於既有 eager policy outcome。
5. present-but-unsupported metric 仍先發出 threshold request；resolver 例外在該 request
   呼叫點浮現，成功回填後則維持 `UNSUPPORTED` terminal。
6. deferred response 的 `DISABLED` 與 `PENDING` 均被拒絕，不能清除已宣告存在的 filter。

測試先行的首輪在 API 尚不存在時，三個新案例因缺少 staged contract import 而失敗
（`3 failed, 13 deselected`）；加入 API 後，fresh TEMP／`PROFILE=test` 四檔相鄰路由
`49 passed`。路由包括 staged evaluator、legacy policy、legacy diagnostics 與真實 scorer
filter characterization。Scoped mypy（`evaluate.py` 與 staged evaluator test）為 `2 files,
0 issues`；兩檔 `py_compile` 通過。使用的 TEMP：
`C:\Users\archi\AppData\Local\Temp\r020_deferred_final_c2486902096849ad8e8fd714b1235d3a`。
測試檔原已登錄於 `service-oracle-recommendation`，本切片未改 inventory。可重跑命令：

```powershell
$env:PROFILE='test'
$env:DATA_ROOT='<fresh-temp>\data'
$env:OUTPUT_ROOT='<fresh-temp>\output'
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r020_replay_post_score_evaluator.py `
  tests/test_r020_post_score_legacy_policy_characterization.py `
  tests/test_r020_post_score_diagnostics_characterization.py `
  tests/test_r020_real_scorer_filter_stage.py `
  tests/test_r020_post_score_unsupported_metric_legacy_characterization.py `
  -q -o addopts= -p no:cacheprovider --basetemp '<fresh-temp>\pytest' --tb=short
```

## 未覆蓋邊界

此 pure contract 只延後最終 post-score rule 的 threshold projection。既有 scorer diagnostic
warning/counter 仍由 `StrategyConfigurator` 產生；當 replay provider 未來移除傳給 scorer 的
filters 時，如何保留其 diagnostic pass 順序與 side effects 尚未在此切片解決。Pandas
原生比較、`pd.NA`、legacy alias／20-row volume fallback、threshold parser 的 exact native
exception type、跨 runtime numeric parity 與 live provider wiring 仍須分別有 adapter
characterization 與 gate。不能僅憑此 API 宣稱 threshold/warning 時序已完整遷移。

本切片不變更 R020 狀態：R020 `IN_PROGRESS`；TMP-REC-04 與 TMP-NUM-01 `ACTIVE`；C2
未放行；R028 `BLOCKED`。

## Deferred response 修補收據

針對 response 可用 `DISABLED` 清除 deferred filter、以及 unsupported metric 被錯當成
missing column 而跳過 threshold request 的兩個 P2，先新增 regression tests；首輪結果為
`3 failed, 17 deselected`，分別重現 unsupported 沒有 request、disabled response 被接受，並
確認 pending response 原本已拒絕。修補後 fresh TEMP 四檔路由 `52 passed in 1.32s`：

- TEMP root：`C:\Users\archi\AppData\Local\Temp\r20g610fe42920`
- pytest log SHA256：`A3A141128F86831F315480A735298BFDDB4026FBE8B96E94AAAE425B4361580A`
- frozen `evaluate.py` SHA256：`203BC9E972B8D092D3549FF83377B893886DE1717C55C43339488D5AA114E5E4`
- frozen staged test SHA256：`053E2B2CB71AFDAB903D0A2B7B924E4190EB44DD12EC86EAC81C4A78FD29C4A8`
- 新增測試：`test_deferred_post_score_requests_threshold_for_present_unsupported_metric`、
  `test_deferred_post_score_response_cannot_clear_present_filter[disabled]`、
  `test_deferred_post_score_response_cannot_clear_present_filter[pending]`。
- scoped mypy：`2 source files, 0 issues`
- `py_compile` 與 `git diff --check` 通過。

此 staged API 的 unsupported terminal 尚不等於原生 pandas diagnostics parity。R015 的新
characterization 指出，object `Decimal` metric 會在舊 diagnostic threshold 投影前比較並拋
`TypeError`；object-dtype `pd.NA` 則會走不同的篩選與 warning/counter 路徑。本修補只固定純
evaluator 對 deferred request 的順序，不代表已解決這些 native ordering/side-effect 差異；
provider cutover 仍須維持封鎖，直到 adapter 與 legacy characterization gate 完成。

R015 新增獨立 legacy characterization 後，將該檔加入 expanded route 再驗一次：五檔 fresh
TEMP 路由 `55 passed in 1.48s`，log SHA256
`A9E283267F27B0F6CFA45B02422D4052EA0DC2FB6C8106AEE750C56A571073AD`；TEMP root 為
`C:\Users\archi\AppData\Local\Temp\r20u327b811137`。新增 legacy test SHA256
`E2AD5E161B5B8CED0A3BF6F9AB9DBA386804A06DF8616AB30F3830BC0D03FEC1`。該 characterization
確認缺少 price 欄位時無效門檻不比較且候選保留；Decimal object metric 的原生診斷比較在
threshold projection 前拋 `TypeError`；object-dtype `pd.NA` 則原生篩空並發 warning/counter。
這些測試只呼叫 legacy `screen_stocks`，是獨立 oracle，沒有呼叫 staged evaluator。

## R027 獨立複審（2026-09-25）

R027 對本 staged deferred-threshold P2 修補給予 bounded `ACCEPTED_SCOPE`，未發現 P1／P2。凍結 SHA-256：`decision_module/recommendation/evaluate.py` `203BC9E972B8D092D3549FF83377B893886DE1717C55C43339488D5AA114E5E4`；`tests/test_r020_replay_post_score_evaluator.py` `053E2B2CB71AFDAB903D0A2B7B924E4190EB44DD12EC86EAC81C4A78FD29C4A8`。

獨立 reviewer 在 fresh TEMP `C:\Users\archi\AppData\Local\Temp\r2psdab1786e`、`PROFILE=test` 重跑五檔相鄰路由，`55 passed in 1.49s`。確認 present-but-unsupported metric 先要求 deferred threshold、`MISSING_COLUMN` 可略過、`DISABLED`／`PENDING` 回覆 fail closed，且 eager/staged 共用同一規則核心。完整路由及重跑命令見 [R020 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R020_IMPLEMENTATION_REPORT.md) 的本次複審紀錄。

此 bounded acceptance 僅適用 pure deferred API；不代表原生 Pandas/object-dtype comparison、diagnostic warning/counter side effects、threshold coercion/error timing 或 live provider cutover parity 已完成。R020 仍 `IN_PROGRESS`；`TMP-REC-04`／`TMP-NUM-01` 仍 `ACTIVE`；C2 未放行，R028 `BLOCKED`。
