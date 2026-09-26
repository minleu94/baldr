# R020 typed provider → replay handoff 獨立複核（2026-09-25）

## 結論與範圍

對 frozen typed-handoff slice 的 bounded review：candidate carrier、同次 replay scorer/evaluator handoff、v1 projection、built-in/custom provider routing 與 row/child parity guard 的實作符合指定邊界，未發現候選 tuple 與 v1 rows 之間的排序或值錯接。這個結論只涵蓋本報告固定的 40-test／6-source route，不代表 R020、TMP-REC-04、TMP-NUM-01、完整 V-REPLAY 或 C2 通過。

signed `top_n` 的 child Request metadata 是既有明文限制，不是本 slice blocker：R017 已規定 `Request.top_n` 只記錄明確正整數，負值不造出虛假的 request 欄位。此處確認的是 compatibility rows 與 canonical child items 的輸出切片一致；不宣稱 canonical Request 保留非正值。

本 reviewer 的 runtime provenance 由 root session metadata 確認：`gpt-6-luna`、reasoning effort `max`。未讀取或輸出任何 auth/key 資料。

## Frozen 輸入與獨立回歸

| 項目 | 固定值／結果 |
|---|---|
| Manifest | `C:\t\r020_typed_child_union_abd24a427bbb4204bea398cca1ec4d16\manifest.json` |
| Manifest SHA-256 | `C57627D0CF545920C10A5E43C2DB20861A17FA1C814C275D867EDCE5C1BC79F7` |
| 綁定 HEAD | `bec423eef1d9e9d4a32410dac96cd233304489aa` |
| Inputs | 40 test paths、6 production source paths，共 46 個逐檔 SHA-256 entries；兩次執行前後均與 manifest 相符，HEAD 與 manifest SHA 亦未漂移 |
| Runtime 邊界 | Windows、Python 3.11.9、Pandas 2.3.3；NP1 NumPy 1.26.4，NP2 NumPy 2.3.5 |
| NP1 | `517 passed, 1 skipped, 35 warnings`；23.33 秒；exit 0；fresh TEMP `C:\Users\archi\AppData\Local\Temp\r020_luna_review_np1_0bb77ccf7a9b47d3923ef4c56f8e6671` |
| NP2 | `517 passed, 1 skipped, 32 warnings`；24.00 秒；exit 0；fresh TEMP `C:\Users\archi\AppData\Local\Temp\r020_luna_review_np2_6688cd50e7b34f4e8b813a554305b096` |
| 唯一 skip | `tests/test_r020_numeric_runtime_differential.py:685`：此 host 的 `longdouble` mantissa 未寬於 float64，較寬 mantissa 分支不適用；不把 skip 計入 pass，也不宣稱其他平台／runtime 已驗 |

兩次均以各自 TEMP、TMP、DATA_ROOT、OUTPUT_ROOT 與 pytest basetemp 執行；`PROFILE=test`、`PYTHONDONTWRITEBYTECODE=1`、Python `-B`、停用 pytest cache。NP1 使用 `C:\Users\archi\AppData\Local\Temp\r020_num01_win_np1264_ad276b8ab2e643b993dc2e4493cf730c\venv\Scripts\python.exe`；NP2 使用 repo `.venv\Scripts\python.exe`。測試輸出包含既有 NumPy native-comparison warnings 與 portfolio same-day-close idealized-assumption warnings；無失敗或 error。

重跑命令（在 repository root、每一 runtime 各自指定 `$run` 與 `$python`）：

```powershell
$manifestPath = 'C:\t\r020_typed_child_union_abd24a427bbb4204bea398cca1ec4d16\manifest.json'
$m = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$tests = @($m.tests | ForEach-Object { $_.path })
$run = 'C:\Users\archi\AppData\Local\Temp\r020_luna_review_np1_0bb77ccf7a9b47d3923ef4c56f8e6671' # NP2 改用上表的 NP2 root
New-Item -ItemType Directory -Force -Path $run | Out-Null
$env:TEMP = $run
$env:TMP = $run
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
$env:PYTHONDONTWRITEBYTECODE = '1'
& $python -B -m pytest @tests -q -rs -o addopts= -p no:cacheprovider --basetemp (Join-Path $run 'pytest') --tb=short
```

Manifest source set 與 hashes：

| Source | SHA-256 |
|---|---|
| `app_module/recommendation_dataframe_provider.py` | `E30BCF375C1256877F79E15FC87B4DECFDA83F9DB0E36608BD11A79BE44412EB` |
| `app_module/recommendation_replay_service.py` | `4B2897DB1CED80302AA0F1B706193C5FBE3E254CABEDFCD348008450A9A79903` |
| `app_module/recommendation/replay_numeric_projection.py` | manifest-frozen；與執行前後工作樹 bytes 相符 |
| `app_module/recommendation_portfolio_backtest_service.py` | manifest-frozen；與執行前後工作樹 bytes 相符 |
| `decision_module/recommendation/evaluate.py` | manifest-frozen；與執行前後工作樹 bytes 相符 |
| `decision_module/recommendation/replay_prefilter.py` | manifest-frozen；與執行前後工作樹 bytes 相符 |

此 route 包含 `tests/test_r020_typed_provider_child_handoff.py`、`tests/test_r020_real_scorer_filter_stage.py` 與同 manifest 的 replay/R005/timeline/portfolio tests。numeric evaluator 的相鄰 dependencies 已包含於凍結 source set；此複核不新增 numeric vectors 或 runtime 範圍。

## 程式複核

- `app_module/recommendation_dataframe_provider.py:154-205` 的 candidate 是 frozen/slots dataclass，排序後由 tuple handoff；其 freeze 是淺層，不宣稱任意 `selection_reason` opaque object 或整個 nested object graph 深度不可變。
- `ReplayProviderCallResultV1` 只儲存 candidate tuple；`.rows`、`.scoring_outcomes` 是每次由 candidate 投影的 properties。另有 parent 已接受的 `compatibility_scoring_outcomes` call-local、非 canonical audit tuple，沒有被 Snapshot、canonical child 或保存 payload 消費。這符合「候選與排序由 candidate tuple 表達；另保留非 canonical compatibility audit」的範圍，不構成平行成功候選 truth。
- `run_with_as_of_handoff` 以 invocation-local sinks 呼叫一次 scorer，回傳同一 cutoff 與原始 signed `top_n`；typed scorer requests 的 cutoff/invocation 身分在 handoff contract 驗證。
- `RecommendationReplayService.run_snapshot` 僅對 exact built-in provider 使用 typed handoff。service 從同一 handoff 的 typed candidate/outcome 組 canonical child；沒有 v1 row→child parser。custom、legacy、subclass 與 overridden provider 維持 v1-only/no-child；測試覆蓋 inherited as-of、overridden as-of 及三參數 `__call__` 分流。
- provider 排序先使用 `ordinals[:top_n]`；service 對 provider rows 與候選再各使用 `[:top_n]`，保留歷史 provider-then-snapshot signed slicing。對正常 sequence，child candidates 與 snapshot rows 的此兩層切片一致；零列可保留 completed empty child。現有非零負值 handoff route 主要用 custom scorer，因此不會建立 canonical child；負值 built-in child 的專項 test 沒有獨立案例，本次 code review 未見兩條切片分歧。
- 為補充 signed-child parity 直接證據，以 built-in `StrategyConfigurator` 和四檔 synthetic history 對 `top_n=-1`、`top_n=0` 做一次 fresh TEMP probe；兩種輸入的實際 `snapshot.recommendations` code sequence 都與 `child.decision.items` 完全相同。結果分別為 `-1: [SLICE-A, SLICE-B] == [SLICE-A, SLICE-B]`、`0: [] == []`。兩者 `child.request.top_n` 均為 `None`，符合 R017 明文 request boundary，非切片差異。
- child build 會驗 sequential `selected_ordinal`、非空唯一 stock code、same cutoff、item/outcome identity、Decimal score 與 ordering token。建立後，service 比對實際 `snapshot.recommendations`（已完成 `deepcopy`）和候選的 v1 投影；list/dict shape、精確型別和值不合即不 attach。float 按 binary64 bytes 比較；opaque payload 只接受同一物件。real-scorer failure-injection tests 污染 project rows 的 score/reason/order，rows 留存而 child fail closed。

## 已接受的 Request metadata 邊界

`ReplayExecutionPolicyV1` 明定 signed integer `top_n` 並用 Python slice（見 `decision_module/recommendation/replay_policy.py:127-178`）；實際輸出 slice 在 provider/service 邊界保留。canonical `Request.top_n` 只允許明確正整數，`top_n <= 0` 映射為 `None`（`app_module/recommendation_replay_service.py:157-160, 211-215`；`app_module/recommendation/contracts.py:1359-1387`）。R017 implementation report 第 24 行已明文記錄這個 request boundary，root 確認它是既有接受限制，不需擴 schema。signed output parity 另以本報告上的 built-in synthetic probe 確認；不把 `None` 說成原始 signed input 的等值表示。

## R020 / C2 完整收口清單

### 真正仍未滿足的 gate

1. **完整 R005／V-REPLAY same-mode parity**：依 task 的 mode-specific oracle 驗 replay lookback、max stocks、minimum rows、fast/post-score filters、skip/exception、排序/tie、兩層 signed top-N、date/cutoff/row-level PIT、empty、factor manifest；只在受影響路徑驗 portfolio holdings/cash。合併 custom provider 與仍使用 v1 list 的 portfolio/factor-manifest consumers。當前 typed handoff 40-test route及既有 bounded parity 不足以宣告 full V-REPLAY。
2. **TMP-REC-04**：generic internal row-dict→canonical-child bridge 已移除；`<20` count-only preflight、blank-code lifecycle 與其 call-local noncanonical audit 已有 bounded acceptance。仍 ACTIVE 的退出條件是完整 R005/V-REPLAY parity。外層 `RecommendationSnapshotDTO.recommendations` v1 list 和現有 consumers 是刻意保留的 live compatibility output，不是待刪 bridge。
3. **TMP-NUM-01**：row-dict→canonical bridge 子範圍已隨 R020 移除；尚需此項獨立數值改造要求的同值／相容證據與 caller cutover，才可退休其餘既有浮點分數與 v1 projection boundary。已接受的 NumPy slice 限於 Windows/Python 3.11.9/Pandas 2.3.3、NumPy 1.26.4 與 2.3.5 各自 native oracle；唯一 skip 為較寬 `longdouble` mantissa 不存在。不要把此限定證據擴大成跨版本相等或所有平台已驗。
4. **Portfolio child/Registry 跨 store recovery**：Stage A codec、B1 CAS、B2 publish、Stage C strict DTO/child readback、Stage D Registry UI/Manual 已各自 bounded accepted；cross-store route 有 3 個 hard-exit crash points 及 1 個 committed child-missing case。full recovery 尚未涵蓋所有 partial-publish windows、R012 與 Registry 的共同原子交易／補償 rollback，亦不會自動重建原 execution；reconcile 只能在 writers quiescent 時明確執行。不要把已接受的 lineage sidecar readback稱作完整 legacy portfolio-result readback或 full recovery。
5. **C2**：依 validation matrix，須完成 C1 union 加 V-REPLAY、scheduled、personalization、saved-result readers 與 affected V-UI，並分類任何同模式 numeric/order 差異。現有 C2 80/54 manifest 已漂移，舊 1107P/5S 收據只是當時 bytes 的 preflight，不是 current full-gate pass。

### C2 再列單與完成程序

1. 等 `c1_codec` freeze；不要把中途漂移當正式 C2 route。
2. 由最新 bytes 重算並凍結：既有 C1 42 tests、C2 80 tests（已包含本 R020 40-test set，R020 test-path set diff 為空）、8-file historical/ML complement（按路徑去重新增 5 tests）、`tests/test_r019_scheduled_cutoff_provenance.py`、`tests/test_ui_qt_run_registry_compare.py` 及當前 R026 focused tests。對全部 tests/sources 記錄 manifest SHA、逐檔 SHA、HEAD，執行前後比對；R020 不再擴測試集合。
3. 使用兩個既有 runtime profile，各自 fresh TEMP、`PROFILE=test`、獨立 `DATA_ROOT`／`OUTPUT_ROOT`／pytest basetemp，`-rs` 保留 skip 原因；核對 tests 與 sources 的 exit code、warnings/skips 和任何 numeric/order 差異。
4. 只在該 combined C2 route、R020 剩餘 full V-REPLAY/TMP 退出證據與 full recovery gate 依規格關閉後，才裁定 R020/C2；本 report 的兩個 517P 收據不可替代它們。

### 僅待彙整或凍結的證據

- 本報告的 40-test R020 handoff route 已零 drift 並在兩環境獨立重跑；無需為 C2 再加一次 R020 test scope。
- Stage A–D 與 bounded recovery 已有各自 review receipts；C2 final report 需引用其 frozen identity 並指出 bounded scope，不能把這些 receipts 合併成尚未跑過的 full recovery。
- 本輪接受的 runtime boundary是上述兩個 Windows NumPy profile。除非正式支援矩陣或新的具體失敗要求，不新增「所有平台／所有 dtype／所有向量／full corpus」等無界 gate。

## 修改與安全邊界

本次未修改 production source、tests、fixtures 或 shared R020 report；未 stage、commit、push；未讀寫正式資料、正式 SQLite、scheduler、UI 或 model promotion。唯一新增檔為此獨立 reviewer report。

## 後續 C2 current baseline 與有限 recovery 更新（2026-09-25）

本節更新上方當時的「仍未滿足」快照；它不改寫原 40-test review route，也不宣稱 C2 final gate 已完成。

- C2 current frozen union 已由 Root 接受為 pytest baseline：136 個 tests、78 個 sources，manifest SHA-256 `64D7EB0FD2A7E7ED9E775562650B58E6D8B51EE5E99722785CD9EB113CDF0291`，NP2 為 `1793 passed／5 skipped／34 warnings`；log `C:\Users\archi\AppData\Local\Temp\c2n2_fix_luna\pytest.log` SHA-256 `BD4A7AC06C28C7B5950D09A9BF4458C774B650F531A5DD68C38B1AB6E1BA3A96`。執行前後 214 個 manifest inputs 與 HEAD 均零漂移。詳細 skip、NP1 profile failures 和 UI bytes-continuity 見 [C2 current pytest baseline](C2_CURRENT_UNION_PYTEST_BASELINE_20260925.md)。C2 final Workbench、Update validator、broad mypy 尚待目前 implementation 穩定後補跑，再於 C2 release cleanup 前完成；R031／C4 final regression 另依矩陣執行。
- 原 NP1 18 個失敗中，17 個是 R026 capability tests 對 NumPy 1.26.4 的明確 unsupported-profile rejection；餘下 owner-packet case 的錯誤由 `TEMP` 與 pytest basetemp 分離造成，修正隔離根後該單點 `1 passed`。不把原 NP1 整體 route 改列 pass，也未重跑完整 NP1。
- 新增 Registry hard-exit recovery route 位於 [R020 process-crash recovery QA](R020_PROCESS_CRASH_RECOVERY_HARD_EXIT_QA_20260925.md)：五種新增 distinct persisted states、既有三個 hard-exit 點與 child-missing 負例保留；兩檔 targeted route `42 passed／0 skipped`，log SHA-256 `96A9ADEF040AD62F0D299FC489868C5D2DCD3C160C40DE75E4B758FCBAA65448`。新增 finalized-but-staging failure case fail closed；四個 `files_ready` partial/full publish hard exits 均 strict-reconcile/read back、完整 DTO `to_dict()` parity，並驗同 hash retry／異內容拒絕覆寫及 child raw bytes 不變。`after_lineage_rename`／`before_final_commit` 是同一持久狀態，未重複增加案例。
- R020 已列的 R005 policy vectors 與 V-REPLAY vectors由 `tests/test_recommendation_replay_characterization.py:456-604,613+`、`tests/test_r020_replay_pipeline_composition.py:252-387`、`tests/test_r020_replay_mixed_terminal_composition.py:210-375`、`tests/test_r020_typed_provider_child_handoff.py:180-421`、`tests/test_r020_concrete_portfolio_parity.py:91-179,481-1116` 和 Bank Taiwan cost test 覆蓋，並包含於本次 C2 union。沒有發現應新增的既有 R005 vector、額外 R020 recovery state 或尚未達成的 same-mode assertion。
- R020-specific typed handoff／V-REPLAY／有限 recovery 已無具體測試缺口可辨識；R020 closeout 建議等待 C2 最終必要 UI／validator／broad-mypy receipts 後交 Root 裁定。generic v1 row→canonical-child builder 的 R020 子範圍已移除；`TMP-NUM-01` 其他既有 numeric compatibility/caller cutover 是獨立 active gate，不擴張成本輪 R020 blocker。跨 store 共同 transaction、補償 rollback、自動重建 execution 與未列支援的所有 OS/runtime 不在授權條件內。

**Console log 限制：** 前述 reviewer 的獨立 40-test NP1／NP2 rerun 未保存 console-log files；本報告不補造其 log path/hash，也不為重建該歷史收據重跑。上方 C2 136-test NP2 log 提供其凍結 manifest 時點 R020 test bytes 的 readback 收據；新 recovery test bytes 另有上述 targeted log。新 recovery test SHA-256 為 `AEE58FA99D089DDA40D368062299871333D4BD104C477BA1B1256611BFB3A998`，因此 C2 manifest 和後續 recovery route 按各自凍結身份分開引用。

### Root 最終複核裁定（2026-09-25）

Root 已讀回 C2 manifest／NP2 log，確認 136-test route 為 `1793 passed／5 skipped` 且 214 inputs 零漂移；並複核新 recovery report、42-pass log/hash 與完整 DTO／child-byte assertions，未見 P1／P2。Root 接受本報告列明的有限 closure checklist：目前沒有剩餘 R020-specific recovery state 或既有 R005 vector 缺口。`TMP-REC-04` 的 R020 子範圍可在 C2 mandatory UI／validator／broad-mypy gates 通過後關閉；`TMP-NUM-01` 其他獨立 numeric gate 不反向阻塞 R020。C2 final gates 與 Root 對 R020／Wave 的最終裁定仍 pending。本附記不改寫本報告歷史的 `NOT PASSED`／pending snapshots，也不把 C2 pytest baseline 升格成 C2 final pass。
