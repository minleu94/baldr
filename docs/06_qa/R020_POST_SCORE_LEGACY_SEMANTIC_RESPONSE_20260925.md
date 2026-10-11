# R020 post-score legacy 語意回應切片（2026-09-25）

## 範圍

此 bounded slice 只在 pure post-score contract 與 app numeric projector 中表達兩組已凍結的
legacy facts，不接線 `RecommendationDataFrameProvider` 或修改 `StrategyConfigurator`：

1. `dtype=object` 的 Python `Decimal` metric 搭配 Python `str` threshold，舊 scorer 在 threshold
   解析前拋出原生 `TypeError`。Evaluator 現回傳 terminal `LEGACY_ERROR`，保留 exception type、
   exact message、rule 與 threshold hint；不建立 threshold request。Pure evaluator 不自行 raise。
2. `dtype=object` 的 scalar `pd.NA` 搭配 Python `str` threshold，舊 scorer 排除該列並產生一筆
   exact warning/counter 診斷。Evaluator 現回傳 `REJECTED` 與 immutable diagnostic event，包含
   exact warning text、filter code 與 counter delta；evaluator 不寫 log、不改 counter。

Projector 必須同時收到來源 Series dtype；只有 `series_dtype == object` 才可分類 `pd.NA`。
nullable `Int64` 的 `pd.NA`、其他 scalar/type 組合及非 Python-string threshold 保持
unsupported／staged threshold path，不由這兩例外推。Threshold hint 只保存 exact Python string
作為診斷文字，不保存任意 raw config object，也不執行 float/Decimal 轉換或數值比較。

## 獨立 legacy oracle 與 QA

`tests/test_r020_post_score_legacy_semantic_response.py` 直接呼叫既有
`StrategyConfigurator.screen_stocks` 固定 Decimal + `"bad"` 的原生 TypeError、object-dtype
`pd.NA` + `"bad"` 的空結果、warning 字串與 class counter；隨後分別檢查 pure evaluator 的 typed
terminal/event 並確認 evaluator 不產生 warning。另有既有
`tests/test_r020_post_score_unsupported_metric_legacy_characterization.py` 固定 missing-column
優先序與這兩種原生分歧。兩個 expected 皆以原生 scorer 行為為準，沒有從 staged response
反推。

新增四項專屬測試的首輪 red 在 API 尚不存在時於 collection 失敗，錯誤為 projector 缺少
`classify_legacy_post_score_metric_scalar`；此僅證明測試先於 API，原生 legacy expected 由上列
直接 scorer characterization 執行。修正實作後，fresh TEMP、`PROFILE=test` 六檔路由得到
`60 passed in 1.67s`。TEMP：
`C:\Users\archi\AppData\Local\Temp\r020-postscore-sem-frozen2-8f385993342e435890db56103ba48326`；
pytest log SHA-256：`8D4DB9AC5B5293D2CD8C849960D168116D579FAF4F374E58385B46198E654111`。

路由檔案：

- `tests/test_r020_post_score_legacy_semantic_response.py`
- `tests/test_r020_post_score_unsupported_metric_legacy_characterization.py`
- `tests/test_r020_post_score_legacy_policy_characterization.py`
- `tests/test_r020_post_score_diagnostics_characterization.py`
- `tests/test_r020_post_score_diagnostics_observer.py`
- `tests/test_r020_replay_post_score_evaluator.py`

`py_compile` 三個切片 Python 檔通過；`mypy --follow-imports=silent` 對 evaluator、projector、
新測試 `3 files, 0 issues`；完整 `quant_guard_linter.py` 通過，沒有新增裸 float 或 look-ahead
讀取。一般 scoped mypy invocation 另顯示 `app_module/recommendation_calibration_consumer.py:1177`
錯誤；這是並行 R026 工作樹錯誤，與本 R020 slice 無關，交 R026 owner 處理。

凍結 SHA-256：

- `decision_module/recommendation/evaluate.py`：
  `D19A386BAFA602DAB74CA95BB92CDF4BEA525B012DAE45544ACFF393FCF67F40`
- `app_module/recommendation/replay_numeric_projection.py`：
  `18ECD722160A4E09F45FA40DBC42009C7FD848041D9963C83BD9900EA2AE5C73`
- `tests/test_r020_post_score_legacy_semantic_response.py`：
  `D3CF255BCCB099D8B6C31BDC6EF53526E8310D409CDF2F1DF55D2D86A689962F`

## 獨立複審與接受界線

R027 以 frozen source/test bytes 獨立複審並建議 bounded `ACCEPTED_SCOPE`，未發現 P1/P2；
reviewer fresh TEMP 六檔路由 `60 passed`，scoped mypy `3 files／0 issues`，`py_compile` 與
quant guard 通過。R027 確認來源與測試 SHA 為上列值，並核對當時的 QA/report 文本；本 note
隨後只校正並行 R026 mypy 錯誤歸屬並加入此接受收據。Reviewer 未提供可引用的 log SHA，因此
不在此虛構；複審 TEMP 為
`C:\Users\archi\AppData\Local\Temp\r020_sem_review_c5604e04`。此接受只適用兩種 typed pure
response；不代表 provider 已套用 event 或重拋 error，也不代表 provider cutover、same-mode
parity 或 R020/TMP gates 完成。

新測試已登錄於 `qa/full_app_healthcheck/test_inventory.py`，分類為
`service-oracle-recommendation`。inventory guard 路由為 `6 passed／1 failed`：唯一失敗的全庫
exact-registration scan 發現 109 個其他未登錄 Python 測試檔；本切片新測試已分類，未出現在
missing 清單。這不構成全庫 inventory PASS，也未清理其他 agent 的登錄缺口。

## 邊界

Diagnostic event 是純資料；app 尚未套用 warning/counter，`LEGACY_ERROR` 也尚未由 provider
adapter 於 legacy 原呼叫點重拋。這兩個結果只讓 downstream adapter 能保留精確處理依據，
不代表 provider side-effect/error timing 已 parity。沒有修改 scorer config、provider、selection、
v1 rows、codec、portfolio 計算或 R026/ML 路徑；未驗 provider cutover、跨 runtime numeric、
完整 same-mode V-REPLAY 或 R005 全矩陣。此切片不改 R020 狀態：R020 `IN_PROGRESS`、
`TMP-REC-04`／`TMP-NUM-01` `ACTIVE`。

## 2026-10-11 後續 R020 disposition（保留本收據範圍）

本文件的 2026-09-25 typed response oracle 仍是該 slice 的歷史證據。後續 [R020 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R020_IMPLEMENTATION_REPORT.md) 記錄 post-score cutover 僅在已測 Win32／Python 3.11.9／Pandas 2.3.3／NumPy 1.26.4 與 2.3.5 profiles bounded accepted；[R029 ledger](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R029_IMPLEMENTATION_REPORT.md) 與 [R031 closeout](R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 將 R020 R005 replay/recovery bounded scope、`TMP-REC-04`、原範圍 `TMP-NUM-01` 列為已關閉，C2 為 `ACCEPTED_WITH_NAMED_QA_BASELINE`。

此後續裁定不表示此 evaluator/projector slice 已驗 provider event/error adapter、所有 runtime/profile/caller、無界 same-mode V-REPLAY 或完整 R005 全矩陣；原 `IN_PROGRESS`／`ACTIVE` 記錄保留為其當時狀態。
