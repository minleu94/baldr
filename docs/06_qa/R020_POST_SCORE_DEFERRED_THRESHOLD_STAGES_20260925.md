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

## Replay provider 初版接線收據（2026-09-25；歷史狀態）

本節保留初版實作 QA 的原始 `358 passed, 1 skipped`／`27 passed` 收據與當時 scorer 邊界。後續責任轉移已擴大為所有 custom／override scorer v1-only，最新 provider cutover 與副作用對照見本文末尾；本節不代表 current gate。

後續 replay-only adapter 已接入 `RecommendationDataFrameProvider`。內建
`StrategyConfigurator` 在 typed `as_of_date` 呼叫中收到不含 `filters` 的 call-local config，
只負責產生非空 scored row；原始 filters 由 provider 建立 request-bound facts，交給 staged
post-score evaluator 逐規則投影與裁決。provider 仍在 scorer 後呼叫既有 diagnostics
observer，以保留 warning/counter 順序；interactive/live 路徑不改。自訂 scorer 不宣稱
built-in canonical post-score 結果：RSI-only filter 會保留 v1 row 並關閉 canonical child，
既有 fast-filter compatibility route 則保留原 typed child 邊界。

Focused route：`tests/test_r020_post_score_threshold_metric_pairing.py`
與 `tests/test_r020_real_scorer_filter_stage.py` 為 `27 passed`；全 R020 route 為
`358 passed, 1 skipped`。此收據只證明 replay provider 的 bounded cutover 與 identity
fail-closed 行為，不宣稱完整 same-mode parity、所有資料源 freshness 或 R020/C2 完成。

## Concrete replay post-score cutover 初版收據（2026-09-25；平台 P2 修補前歷史記錄）

33 個 `tests/test_r020_*.py` 加上 `tests/test_recommendation_evaluator_replay_staged.py`、`tests/test_recommendation_replay_prefilter.py`、`tests/test_recommendation_replay_numeric_projection.py` 的 fresh TEMP route 為 `432 passed, 1 skipped in 17.61s`。TEMP root 為 `C:\Users\archi\AppData\Local\Temp\r020_final_postscore_627326433c164890a3d54da420ab6631`；`PROFILE=test`，`DATA_ROOT`、`OUTPUT_ROOT` 與 pytest `basetemp` 均位於此根目錄。唯一 skip 是 `tests/test_r020_numeric_runtime_differential.py:685`：本 runtime 的 `longdouble` mantissa 未寬於 float64，較寬分支未覆蓋。精確命令見 [R020 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R020_IMPLEMENTATION_REPORT.md) 的同名 current cutover 區段。

本次將原先 built-in scorer 的 post-score 篩選移至 replay-only typed evaluator；config filters 從 scorer call-local copy 移除，threshold 仍依原 alias normalization 與 staged request 延遲解析。只有 exact built-in scorer 且 typed `as_of_date` 呼叫可建立 canonical outcome/child。Injected、subclass、override scorer 非空輸出保留 v1 rows、`scoring_outcomes=None` 且不建立 canonical child；合法 zero-row empty execution 仍可保留。沒有改 interactive path、v1 wire 或 codec。

Side-effect parity test 固定兩類高風險 native 行為：float16／float32 `price_change_max=1e100` 在 `over="warn"` 下，native observer＋final Pandas filter 與 replay observer＋typed pair projection 都依序產生兩個相同的 `RuntimeWarning: overflow encountered in cast` 並保留 row；`over="raise"` 則兩路都在首個 diagnostic comparison 失敗，replay 未進 pair projection，provider 以既有 `SKIPPED_SCORER_EXCEPTION` boundary 吸收。Price reject 後 invalid int64 RSI string 仍先記 price warning／counter，再以同一 Pandas TypeError 結束；replay provider 以 scorer-exception terminal fail closed，不產生 row。測試只固定這些合成 scalar/dtype，其他 NumPy runtime、Pandas extension/object scalar 與 warning quota 仍需獨立驗證。

Scoped mypy：provider、evaluator、real scorer filter tests 共 3 files／0 issues。三個 Python 檔 `py_compile` 通過；`scripts/quant_guard_linter.py` 的 financial float 與 look-ahead checks 通過；`git diff --check` 通過。測試檔已在 inventory 的 `service-oracle-recommendation` 分類，本次未修改 inventory。

目前 frozen SHA-256：provider `79B96627E40FAD39B6430B51E36F1D7A231E339E5C9F15A52233AA85012BA08`；evaluator `EAE0E2263DBDFC8A1C0BE4FDD0100C10186D5551FD0CB147E1DA56D514160EFD`；side-effect／real scorer test `F9A3FA8094B4A8BA7B1694D0FCBD34858F4B6CB1DA79486605A49BE1E92116FC`。此收據由實作者執行，等待 R015 獨立複審；R020 維持 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 維持 `ACTIVE`，C2 未放行，R028 `BLOCKED`。

## 2026-09-25 Pandas complex post-score 同模式修補（實作者收據；獨立複審待辦）

修補前 NP1 reproducer 顯示 `np.complex64(2+nanj) >= 1.0` 的原生 Pandas Series 篩選會拒絕，舊 typed comparator 曾接受並在 concrete provider 多輸出一列；另有舊 projector assertion 仍期待 `NUMPY_COMPLEX`。兩者均為修補前紅燈，不納入通過收據。另一次 merged NP1 full route 被 process-local 診斷 counter 污染；已在 real-scorer 測試 module 加 `monkeypatch` 隔離，沒有改 legacy oracle 的輸出預期。

修補將 NumPy complex post-score pair 標為 `PANDAS_COMPLEX_SERIES`，保留 NumPy 原 scalar provenance；任何 NaN component 均按 Pandas Series 的 unordered rule 拒絕。整個 complex domain（包括 real component 已決定方向、但不發 warning 的 `2+nanj`）都受 runtime capability gate。僅 Python 3.11.9、Pandas 2.3.3、NumPy 1.26.4 或 2.3.5，且 `_evaluate_standard` bytecode/location 符合已驗型態時可用；其他 profile/location 在 row/canonical child 前 fail closed。native oracle 使用相同 `RecommendationDataFrameProvider.__call__` provider wrapper 與 warning context；直接 `StrategyConfigurator` 僅作機制診斷。warning filter、category/message/location、default registry、`np.errstate` warn／raise／ignore／print／log／call 及 rule-local warning site 均有對照／負測。

fresh short TEMP 完整 route 含 33 個 `test_r020_*.py` 加 staged evaluator／prefilter／numeric projection 三檔：NP1 TEMP `C:\r20q\n1z_0000a41c` 為 `449 passed, 1 skipped, 9 warnings`；NP2 TEMP `C:\r20q\n2z_03e05150` 為 `449 passed, 1 skipped, 6 warnings`。兩 runtime 分別對自己的 native provider wrapper；warning summary 數量不可跨 NumPy 版本比較。唯一 skip 為 longdouble mantissa 不寬於 float64。完整重跑命令、四個 production／四個測試 SHA 及 scoped checks 已追加於 [R020 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R020_IMPLEMENTATION_REPORT.md)。

R015 對這一版 449 passed 收據判為 `CHANGES_REQUIRED`：complex capability 缺少非 Win32 fail-closed gate，且 NP1 重跑命令會在改寫 `$env:TEMP` 後由該變數錯誤組成 runner 路徑。本節收據保留作為修補前歷史，不作目前 gate。R020 `IN_PROGRESS`、`TMP-REC-04`／`TMP-NUM-01` `ACTIVE`、C2 未放行、R028 `BLOCKED` 均維持。

## Pandas complex 平台 gate 修補後 QA（2026-09-25；bounded acceptance）

R015 指出的平台 capability P2 已修：`_pandas_comparison_warning_location()` 現只允許 `sys.platform == "win32"`，並仍要求已驗 Python 3.11.9、Pandas 2.3.3、NumPy 1.26.4 或 2.3.5 及指定 bytecode/location。此證據只涵蓋已測 Win32 runtime profile，不宣稱所有 Windows OS/build；未驗平台與 runtime 在建立 row/canonical child 前 fail closed。

負測以真實 `RecommendationDataFrameProvider`→`RecommendationReplayService.run_snapshot` 路徑驗 Linux、Darwin、unknown platform 上的 `np.complex64(2+nanj)`：即使此原生比較不發 invalid warning，呼叫仍 fail closed，沒有 recommendation row 或 canonical child。相同測試另確認一般 `np.float32` scalar 在 Linux 不受 complex capability gate 影響，仍可得到 row 與 child。

33 個 `tests/test_r020_*.py` 加 staged evaluator、replay prefilter、numeric projection 三個相鄰檔，在各自 fresh short TEMP／`PROFILE=test`、DATA_ROOT／OUTPUT_ROOT／pytest basetemp 隔離下：

| Runtime | TEMP root | 結果 |
|---|---|---|
| Python 3.11.9／NumPy 1.26.4／Pandas 2.3.3 | `C:\r20q\n1_platform_final_327f5450` | `455 passed, 1 skipped, 11 warnings`；log SHA-256 `697E1D71160AA9ACF4DC19735C3760A2C136F360676FA83CB88996D86B9B88B5` |
| Python 3.11.9／NumPy 2.3.5／Pandas 2.3.3 | `C:\r20q\n2_platform_final_5a9fb6e3` | `455 passed, 1 skipped, 8 warnings`；log SHA-256 `01CCE08C8E92B819BF04D84A0EA29080D5E2CDEA28F61BFC5599BA9C9399A091` |

唯一 skip 是 longdouble mantissa 未寬於 float64。Scoped mypy 以 `--follow-imports=silent` 覆蓋四個 production 檔與 real scorer filter test，`5 files／0 issues`；四個 production 與四個測試檔 py_compile 通過；quant guard 的 financial-float/look-ahead checks 通過，`git diff --check` exit 0。完整可重跑命令見 R020 implementation report；NP1 interpreter 以 `$env:LOCALAPPDATA` 下的固定 venv 路徑定位，不依賴先前被 NumPy 2 runner 改寫的 `$env:TEMP`。

R015 前一輪獨立 log `C:\r20q\r015n1_e13c120d\pytest.log` SHA-256 `0624082127BA3014F1BF24A6A24B42BC7311C53B5AE88E43D6380041B8463E0A`、`C:\r20q\r015n2_74b1c717\pytest.log` SHA-256 `E984E71EC42F53DAB4A03B6D145FFDF1C8D074A2AF0C945D57909B5F622197AB` 為平台修補前的 449 passed／1 skipped 歷史收據，不是本次通過證據。R015 對修補後 NP1／NP2 各完成定向 11P，5-file mypy 為 0 issues，compile／quant guard／diff checks 通過；root 對本平台切片給予 bounded `ACCEPTED_SCOPE`。接受只涵蓋已測 Win32／Python 3.11.9／Pandas 2.3.3／NumPy 1.26.4 或 2.3.5 與 complex fail-closed capability gate，不代表其他 runtime、Windows OS/build、Pandas extension/object scalar 或完整 V-REPLAY parity。R020 `IN_PROGRESS`、`TMP-REC-04`／`TMP-NUM-01` `ACTIVE`、C2 未放行、R028 `BLOCKED` 均維持；未驗 profile 與 full V-REPLAY 不作通過宣稱。

## 擴大 V-REPLAY 合成 route（2026-09-25；bounded ACCEPTED_SCOPE）

此補充 route 為 R005/provider、staged evaluator、timeline、portfolio 與 Bank Taiwan cost 測試建立同一凍結輸入集合，沒有改動 production/tests。Manifest `C:\r20q\x11_4750a051\manifest.json` SHA-256 `3D27664FDB98E2607C57E6F85A2CD0DF4F17B8BFD5BC9D9E5768CC15390A63F2`，列出 40 個 test paths 與逐檔 SHA（33 個 `test_r020_*.py`、三個 staged evaluator/prefilter/numeric adjacent、R005 replay characterization、timeline、portfolio、Bank Taiwan cost），以及 6 個 replay/provider/evaluator/portfolio source SHA。綁定 HEAD `bec423eef1d9e9d4a32410dac96cd233304489aa`；兩個 profile 執行前後 46 個 source/test entries 與 HEAD 均一致。

| Runtime | fresh TEMP／PROFILE=test／DATA_ROOT／OUTPUT_ROOT／pytest basetemp | 結果 | log SHA-256 |
|---|---|---|---|
| Python 3.11.9／NumPy 1.26.4／Pandas 2.3.3 | `C:\r20q\x11_n1_effe0fd3` | 512 passed, 1 skipped, 35 warnings；pytest 19.66s（外層 wall time 22.38s） | `EDC9A16A146E9501092847E7970216A2FEDEF3BFBECF21194AFFD87CF5E5F12A` |
| Python 3.11.9／NumPy 2.3.5／Pandas 2.3.3 | `C:\r20q\x11_n2_edacd620` | 512 passed, 1 skipped, 32 warnings；pytest 18.91s（外層 wall time 21.61s） | `25E3F631F8323EAF75686B971FD07C57265FE8C28ACDA77A3D3075B7BE061B6B` |

R015 獨立複審確認 manifest／HEAD／46 個 test/source SHA 完全相符。複審 fresh TEMP NP1 log `C:\t\x11np1r\pytest.log` SHA-256 `C90DB3934A494EE669E7A8621E6F3FAB48B8501140AED086D2118F44434D9EDE` 為 512 passed、1 skipped、35 warnings；NP2 log `C:\t\x11np2r\pytest.log` SHA-256 `4B5022D4ED7AE00230F8F749EC78C9F460EBD93F85C6DC3566AB2BDCCF991BE6` 為 512 passed、1 skipped、32 warnings。另有 6-file accounting/PIT route 56 passed、4 warnings，log `C:\t\x11r1r\pytest.log` SHA-256 `5D4F88775EB4CF88E75ACE19D6E43EFC7A84CE15AEE97D6D8A15246DD1A19E6A`。Root 對這些合成測試範圍給予 bounded `ACCEPTED_SCOPE`，不擴張到 C2。

每個 profile 唯一 skip 是 `tests/test_r020_numeric_runtime_differential.py:685` 的較寬 `longdouble` mantissa 分支，本機 mantissa 未寬於 float64。warning summary 是各 runtime 自己與 native wrapper 對照的結果，跨 NumPy profile 的計數不同不代表 parity 失敗或通過。

本 route 的 ordered v1 row、score fallback/stable sort/tie、top-N 與 factor survivors 以 R005 `tests/test_recommendation_replay_characterization.py:456-604,613+` 為 oracle；provider/snapshot 雙層切片、mixed terminal、diagnostics、factor scores 與 child 邊界由 R020 pipeline/handoff tests 固定；legacy-close 與 next-open 各自有 PIT、factor/parent 及帳務手算向量，且明確不跨 execution contract 比較帳務。精確證據位置、檔案 SHA、PowerShell invocation 與 manifest 欄位說明見 [R020 implementation report 的 expanded route](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R020_IMPLEMENTATION_REPORT.md)。

這項 bounded expanded route 已由 R015 獨立複審接受，並包含歷史 32-file subset 未同次執行的 cross-store recovery、process-crash recovery、UI replay-lineage 三檔。它仍不包含 R026 source-backed historical replay；scheduled、personalization、saved-result/UI consumer 的完整 C2 矩陣也未重跑。故本收據不宣稱完整 V-REPLAY、R020、`TMP-REC-04`、`TMP-NUM-01` 或 C2 完成；R020 `IN_PROGRESS`，兩個 TMP `ACTIVE`，C2 未放行，R028 `BLOCKED`。

## 2026-09-25 concrete provider typed-only child handoff（等待獨立複審）

這個 bounded slice 將 concrete replay provider 的一次排序候選 tuple 作為 typed child 與外層 v1 rows 的共同來源。`ReplayProviderCallResultV1.candidates` 是 handoff 的內部來源；`.rows`／`.scoring_outcomes` 保留讀取相容 projection，不再存兩份可錯接的平行列表。`RecommendationReplayService` 只從 candidate 的 typed scorer outcome 建 `DecisionBatch`，不解析 v1 dict 反造 item 或 assessment；建立 `RecommendationSnapshotDTO` 後，另逐列比對實際 `snapshot.recommendations` 與同一批 candidates 的 v1 projection，欄位、型別、列序或值不相符時保留該 v1 rows、但不附 canonical child。此比對只作 fail-closed sidecar parity gate，不以 rows 作 canonical 輸入。自訂／覆寫 provider 保留 v1-only/no-child 邊界；原有 zero-row completed empty child 仍由空 typed decision 表達。

新增負測先重現三個投影失配：v1 projection 的 total score、reason 被改寫或順序交換時，原 service 仍會附 canonical child；修後三個 case 均保留 v1 rows 並拒絕 child。另有 built-in child 正例、candidate/outcome corruption 負測、fresh v1 projection alias isolation、single scorer pass，以及既有 concrete portfolio parity。測試修改限已登錄檔 `tests/test_r020_typed_provider_child_handoff.py` 與 `tests/test_r020_real_scorer_filter_stage.py`，未改共享 inventory。

凍結 HEAD 為 `bec423eef1d9e9d4a32410dac96cd233304489aa`。同一 frozen manifest `C:\t\r020_typed_child_union_abd24a427bbb4204bea398cca1ec4d16\manifest.json` SHA-256 `C57627D0CF545920C10A5E43C2DB20861A17FA1C814C275D867EDCE5C1BC79F7`，包含 40 個 R020/R005/replay/timeline/portfolio tests 與 6 個 provider/service/evaluator sources；兩 profile 執行前後 46 個 entries 與 HEAD 相同。

| Runtime | fresh TEMP | 結果 | pytest log SHA-256 |
|---|---|---|---|
| Python 3.11.9／NumPy 1.26.4／Pandas 2.3.3 | `C:\t\r020_typed_union_np1_af24dca3a63e4fb6bf015dfd8893e914` | 517 passed, 1 skipped, 35 warnings；pytest 21.99s | `DDD9A3D0563DF8200BC38650D353DEED73D705483D972F2488D3386595E3C0F3` |
| Python 3.11.9／NumPy 2.3.5／Pandas 2.3.3 | `C:\Users\archi\AppData\Local\Temp\r020_typed_union_np2_b36104ece9974570a68a81c5b60638d3` | 517 passed, 1 skipped, 32 warnings；pytest 22.14s | `56BFC29C0BD8B0E3585FB5BDE023D83EBA8981A95197AD96C77E48152E129A06` |

唯一 skip 是 NumPy longdouble mantissa 未寬於 float64；warnings 由各 runtime 的 native oracle 與 portfolio warning 產生，數量不要求跨 profile 相同。另以 fresh TEMP 跑 source-backed historical replay 與 historical snapshot provider 鄰接測試，共 16 passed，log `C:\t\r020_typed_source_adj_e551a7c932b845268d422ed7384497c6\pytest.log` SHA-256 `898716FFC8292A8792590AC5CE1591C74038286C38416BD659A8B184C52895E8`。核心 5-file route 為 65 passed、4 warnings；py_compile、provider/replay service scoped mypy（2 files／0 issues）、quant financial-float/look-ahead guard、scoped `git diff --check` 均通過。測試使用 synthetic history 與 fresh TEMP，未讀寫正式資料。

凍結 SHA-256：provider `E30BCF375C1256877F79E15FC87B4DECFDA83F9DB0E36608BD11A79BE44412EB`；replay service `4B2897DB1CED80302AA0F1B706193C5FBE3E254CABEDFCD348008450A9A79903`；typed handoff test `6672592231ABE0294CDA3CAA7AEC282EB5FA4F0D36A70F4F02C1D07BA8EE77A5`；real scorer filter test `92F4FEEA22EFD43CD6AB9922200F610A9CE4450C1BF1499F1C0E724E7943F6D7`。此為實作者 bounded 收據，等待 R023 獨立複審；R020 維持 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 維持 `ACTIVE`，C2 未放行，R028 `BLOCKED`。
