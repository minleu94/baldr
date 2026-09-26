# R020 replay 共用 evaluator 與版本化 policy 實作進度

## 目前 checkpoint（2026-09-25）

Root 已接受 R020 bounded engineering scope，並裁定 `TMP-REC-04` `CLOSED`。C2 current union route 為 **1860 passed／5 skipped／34 warnings**、102.75 秒、exit 0，141 個測試路徑前後 229 hashes unchanged；log `C:\Users\archi\AppData\Local\Temp\c2s_bcd34f\pytest.log` SHA-256 `193EF45EA69B984A356F238CFAD4D00D714AB2B026E01CE89887260E59604687`。Workbench 84 passed，broad mypy 724 files／0 issues；Update validator 的 Windows `WinError 32` cleanup failure 保留為具名 baseline（25 passed／1 teardown failure／4 skipped、exit 1），因此 C2 是 `ACCEPTED_WITH_NAMED_QA_BASELINE`，非全綠。`TMP-NUM-01` 仍 `BLOCKED_WITH_OWNER`（decision recommendation／app codec），其獨立數值支援與 caller parity 範圍不由 R020 closeout 關閉。此接受不代表正式資料或 model promotion 已完成。細節見 [C2 mandatory UI/static gate 現況收據](../../../06_qa/C2_MANDATORY_UI_STATIC_GATES_20260925.md)。

## 歷史切片狀態與範圍

下列逐切片記錄保留各 frozen snapshot 時的狀態、限制與 bounded receipts；其中較早的 `IN_PROGRESS`、`ACTIVE`、`尚待 C2` 等語句不是本 checkpoint 的 current status，也不改寫各 slice 原 acceptance 範圍。

- R020 整體狀態：`IN_PROGRESS`。C0、C1a、C1b、C1c、requested-as-of transport、`ReplayExecutionPolicyV1`、typed scorer candidate／evaluator ranking 與 provider first-slice 等 bounded slices 均已記錄於下文。Concrete provider typed scorer→canonical child handoff、獨立 replay parent 與 Research Run Registry lineage sidecar 已有合成整合；generic v1 row→canonical child builder 已移除，custom／legacy provider 只保留 v1 rows 與 transient parent、canonical child 為 `None`。`<20` rows 的 count-only preflight 已 bounded accepted；空白 code active-filter compatibility slice 依 R023 frozen SHA 的獨立 review（156 passed、無 P1/P2）已 bounded accepted。兩者都不建立 canonical assessment／child，完整 V-REPLAY parity 仍待收口，TMP-REC-04 不可退休。
- C1c 將 provider 的 fast-filter 比較交由 pure evaluator；app 仍按舊次序產生 metric、lazy 解析 `float(raw)` 門檻並正規化 volume threshold，以 request ID 在候選呼叫區域保存 raw scalar，並保留 requested-as-of 與 best-effort trace。C1c 原始接線 review 的 bounded runtime 證據限 Windows NumPy 2.3.5；後續 2026-09-24 `TMP-NUM-01` follow-up 已在 Windows NumPy 1.26.4 與 2.3.5 profile 對各自 native-operator oracle 重跑 provider route（見下文）。這些證據仍未覆蓋其他 runtime、完整 row-level PIT／V-REPLAY parity；`TMP-REC-04` 與 `TMP-NUM-01` 維持 `ACTIVE`。
- Concrete provider handoff 將同次 scorer outcome 與 v1 recommendation rows 一起交給 replay service；可驗證的 typed outcome 供 canonical child 使用，投影失敗仍保留 v1 row 並不產生不完整 child。Generic v1 row→canonical child builder 已刪除；custom／legacy provider 仍可回傳 v1 rows 與 transient parent，但 canonical child 固定為 `None`。Portfolio invocation 的 parent ID 與 Research Registry `run_id` 分離；child artifact 以 R012 create-only 保存，sidecar 及 manifest 由 Registry staging／readback 驗證。新的 2-child synthetic UI→R012→Registry route 已驗證 child bytes 與損毀 child 的全批次 fail-closed。先前五檔 cross-store recovery route 為歷史證據（77 passed／4 skipped）；另有目前 UI 同 `run_id` 重試測試 10 passed，僅涵蓋 Registry pre-insert failure 後重試與 replay-lineage／R012 child bytes。該測試不涵蓋 failed/noncommitted Registry row retry、portfolio-result sidecar 或完整 DTO readback；後續已有 3 個 hard-exit crash 點與 1 個 committed child 缺檔情境的 bounded recovery evidence（見本報告下文），但完整 recovery、跨 store 原子復原與自動重建仍未驗證。Stage C 完整 DTO readback與 Stage D 專屬入口均已 bounded accepted。legacy history dropdown 只列舊 repository records。
- Registry portfolio-result integration 的最新狀態：Stage A codec、Stage B1 repository CAS、Stage B2 Registry publish、Stage C strict DTO／child readback 與 Stage D BacktestView UI／Manual 各自 bounded `ACCEPTED_SCOPE`。最新 B2 service/repository/tests SHA 為 `DC47816C62D1249629B2CE6303608B52503E3735882EAD74A68C75AF7D7B00CF`／`8AA0454D124615B0CD783C83826A678A04CCD54BC47740571E825446729AE503`／`CA18D12AF9F483C8302BF3C146D915B272BE42E79AED4A81C88AE9BE46B6D1C1`，R015 fresh TEMP non-UI route 70 passed、mypy 0、compile 通過。Stage D 由 R023 frozen-source 獨立 bounded accepted：7-file fresh TEMP route 95P；Workbench 84P；broad mypy 712 files／0；compile／diff-check 通過。Stage D 整合 route 為 82P。Update QA 分列實作者 R027 的 `25P/0F/4S` exit 0，以及 reviewer R023 的 `25P/1F/4S`，其唯一失敗是 WinError32 TEMP SQLite teardown、非功能 assertion，不計 reviewer pass。零 snapshots 不呼叫 child persistence、不發布空 lineage sidecar，改以相同 parent ID 標記 `unavailable`；讀回保留空 DTO 並明示沒有 recommendation snapshots／canonical child 不可用。Stage D 先保存有可驗 child 的 R012 artifacts 再呼叫 B2；若 Registry metadata 本身無效，B2 的 guard 在 Registry writes 前拒絕，但不能撤回已保存 child，BacktestView 尚無一個涵蓋所有 metadata failure 的上游 preflight。以上不代表 R020、`TMP-REC-04`、`TMP-NUM-01` 或 C2 完成。
- Same-mode 固定向量 parity 有 bounded acceptance：原 16-file receipt 固定在當時 test SHA-256 `9A274320B298C6C4BE659FD35A607187E9A455556FDF4CA453ADD872F66F8BC1`（211 passed、24 個既有 warnings、scoped mypy 4/0、compile 通過）；後續新增 next-open PIT 向量後，當前 test SHA-256 為 `3AC9E5CE3EB9FA303857CB577258518C9AE7AE68C2F20EF71A2ACAB192FA7030`，其六檔 fresh TEMP route 74 passed。兩筆都是固定 scorer/reason 的 synthetic evidence，不是完整 V-REPLAY corpus 或所有 caller/mode parity，也不關閉 `TMP-REC-04`、`TMP-NUM-01` 或 C2。
- R019 evaluator-core dependency 已滿足。`RecommendationSnapshotDTO.recommendations` v1 live compatibility projection、portfolio／factor-manifest consumers 仍需保留；C0 不改該 projection 或 R005 replay 行為。
- 2026-09-25 concrete replay post-score cutover 的平台修補切片已由 R015 獨立複審並獲 root bounded `ACCEPTED_SCOPE`：只在 typed `as_of_date`、精確 built-in `StrategyConfigurator` 與 active filters 的 replay 呼叫走 typed post-score evaluator；所有 injected／subclass／overridden scorer 的非空列維持 v1-only、沒有 canonical child。Win32／Python 3.11.9／Pandas 2.3.3 下 NumPy 1.26.4 與 2.3.5 各自 route 為 `455 passed, 1 skipped`；R015 另對兩個 runtime 各跑定向 11P，並完成 5-file mypy／compile／guard／diff checks。唯一 skip 是此環境的 `longdouble` mantissa 未寬於 float64。接受僅限已測 runtime/capability 與該切片，不關閉完整 V-REPLAY、TMP gate 或 C2。
- 本 slice 只用 fresh TEMP／`PROFILE=test` synthetic tests；未讀寫正式資料、正式 SQLite、正式 replay snapshots 或 artifacts。

## Frozen evidence identity

| Input | SHA-256 |
|---|---|
| C0 frozen source | `B1A63D65582453112E767FF109A8F2B64FDB986DA2C0EA220EE5D4FB7A53AD28` |
| C0 frozen tests | `00FB6ECE16647297A2CE6F3EE3D3823D4A4F517EB732BA8B40DE21D3E9FAABD9` |

以上雜湊識別此次 C0 審核的 frozen source／test inputs，不代表整個共享工作樹或 repository HEAD；不把後續未凍結變更歸入該次結果。

## C1a frozen evidence identity

| Input | SHA-256 |
|---|---|
| Legacy fast-filter oracle：`tests/test_r020_c1a_fast_filter_legacy.py` | `83313D3160C7CAF7F0635C3CF869A1BF0324751BADBCB5B13DB724DF3A671C4A` |
| Provider with opt-in shadow trace：`app_module/recommendation_dataframe_provider.py` | `8052E0A27F491663EF37D10B6943C5A01144DB096B1797E5E57A3FD7111B2982` |
| Shadow trace tests：`tests/test_r020_c1a_fast_filter_shadow.py` | `DD5938EF8E3E45C250911B6E0A96017898497037415108090D589755F420D4EC` |

以上雜湊只識別 C1a review 使用的 frozen inputs，不代表整個共享工作樹或 repository HEAD。

## C1b frozen evidence identity

| Input | SHA-256 |
|---|---|
| Pure replay prefilter contract：`decision_module/recommendation/replay_prefilter.py` | `A7793DD01A8B0ED09B1194ED6E29F410D042577F929A4FB8465C7A6D252530A6` |
| Final pure contract tests：`tests/test_recommendation_replay_prefilter.py` | `B41BCC610E9575120345DD41E181A96A7F17700B194D6804A66A412AF6D29D32` |

以上雜湊只識別 C1b bounded review 的 frozen inputs，不代表整個共享工作樹或 repository HEAD。

## C1b staged pure evaluator frozen evidence identity

| Input | SHA-256 |
|---|---|
| Shared replay evaluation constants：`decision_module/recommendation/evaluation_constants.py` | `C01E42448BAD418D41B35AD3540A2B871CC2D6011DE6B6042C89A142738A7BF1` |
| Staged evaluator：`decision_module/recommendation/evaluate.py` | `48F9627CD6F489CA689A8A4A6E428A7CBB39E0C2BAA7B01BA284E466771FCEB1` |
| Prefilter helper：`decision_module/recommendation/replay_prefilter.py` | `35807B754BA4B9DE5AF52DDAA9C9BC475485FF23CAEDDD69BF3DE1F481828749` |
| Staged replay tests：`tests/test_recommendation_evaluator_replay_staged.py` | `82E88BFFF50EF34D538582309026282E6E49BC06985C6A3ACFF31771BE826010` |

這組 SHA 識別 C1b staged evaluator gate 的 frozen inputs；較早的 C1b threshold-contract SHA 繼續識別其先前 bounded gate，不視為本次檔案版本。

## C0 contract 與 look-ahead 限制

`evaluate_replay_prefilter` 是 no-I/O helper，只根據呼叫端傳入的 typed observations 與 `ReplayFastFilterPolicyV1` 做 prefilter 判斷。它可檢查傳入的 maximum row date 與 availability date 不晚於 cutoff；它不讀取資料，也不執行逐列 point-in-time 過濾，不能取代 provider 的 row-level PIT。

C1 的 provider adapter 必須由 app/provider 在 cutoff frame 上建立 observations，保留決策時點與 availability 條件，再交給 pure helper；不能以 helper 的 cutoff-summary 判斷取代逐列 point-in-time 資料檢查。C1c 已完成 bounded provider 接線並把比較交給 evaluator，但這不代表 full row-level PIT、所有 runtime profile 或整體 replay parity 已驗收。

## C0 QA 證據

| Gate | 證據與限制 |
|---|---|
| C0 + R005 | owner、root、reviewer 各自以 fresh TEMP 執行 C0／R005 combined route，記錄 `23 passed`；此為 bounded slice evidence，不是 R020 全驗收。 |
| Type／syntax | scoped mypy `1 file, 0 issues`；`py_compile` 通過。 |

## C1a legacy characterization 與 shadow trace

C1a 固定 R005 fast-filter 的舊比較邊界，並在 provider 上提供呼叫端明確傳入 `capture_sink` 才啟用的診斷 trace。Trace 可記錄計算值、有效門檻及 NaN／無限值狀態；每次 invocation 使用新的 sink。Trace 僅作觀測，既不提供 pass/reject 結果，也不取代或影響舊比較。

無效 threshold 的行為刻意保留：若舊比較在 filter path 轉換門檻時拋錯，shadow trace 標成 unavailable（先前已記錄的 partial events 不代表完整 trace），再原樣重拋；該 filter 呼叫仍位於 scorer 的 per-stock `try` 外。診斷 wrapper 會在 traceback 增加 shadow instrumentation frame，這是已知診斷限制；不得把 traceback frame parity 當作本 slice 的輸出 parity。C1a 不切換 evaluator、不改 provider 的決策結果，也不代表 production replay 已接線。此句描述 C1a gate 的當時範圍；後續 C1c 已把 fast-filter 比較切到 staged pure evaluator，trace 仍只作 opt-in 診斷。

| Gate | 證據與來源 |
|---|---|
| Owner focused route | C1a／R005 owner 回報 `79 passed`；scoped mypy `705 source files, 0 issues`。 |
| Root fresh TEMP route | root 回報相關 route `126 passed`。 |
| Independent reviewer fresh TEMP route | reviewer 回報 `88 passed`。 |
| Local characterization + R005 | frozen legacy oracle 與 R005 characterization `31 passed`；`py_compile` 通過。 |

各項是不同範圍的 bounded evidence，不將 pass 數相加或推論為完整 R020 parity。QA 使用 fresh TEMP／`PROFILE=test` synthetic fixtures；不涵蓋正式資料或 production cutover。

## C1b pure volume-threshold contract

C1b 在 `ReplayFastFilterPolicyV1` 純契約內明確區分 raw ratio threshold 與 effective change-percent threshold，兩種表達互斥。已是 effective 的門檻不再做第二次 normalization；unordered 與正／負無限值以明確 typed status 表示，再由 pure evaluator 按舊比較語意處理。這個 slice 不讀 frame、不轉接 provider，也不發布 replay result。

Raw `Decimal` 本身不保證重現 legacy `float()` coercion 的 ULP。若後續 adapter 接收舊設定並要保留 exact behavior，必須依 legacy conversion 次序先完成等價 float coercion／raw normalization，再把有效值標示為 effective；不能再次 normalization，也不能只因新契約使用 Decimal 就宣稱與 R005 完整 parity。

| Gate | 證據與來源 |
|---|---|
| Owner | fresh TEMP pure contract route `84 passed`；scoped mypy `705 source files, 0 issues`。 |
| Root | fresh TEMP 9-file route `131 passed`。 |
| Independent reviewer | fresh TEMP 9-file route `130 passed`，未發現 P1/P2。 |

這些是 pure contract 範圍的獨立 bounded evidence，不證明 provider/evaluator 接線、逐列 PIT 或 full replay parity。

## C1b staged pure evaluator

`RecommendationEvaluator` 會依 policy 與觀測狀態逐步回傳 typed request。filter 已啟用但 observation 是 `NOT_REQUESTED` 時，會依 legacy lazy order 回傳 `NEED_FACT`；例如先 request price metric，再按結果 request min/max thresholds，之後才可能 request volume metric／threshold。`NeedCandidateScoring` 是另一個 typed terminal request，pure evaluator 不執行 scorer。`evaluate_replay_prefilter` 仍是唯一比較 helper；staged evaluator 管理請求／狀態與 helper 呼叫，不建立第二套 filter comparison。

測試固定 19 rows 在任何 filter fact 前結束、20 rows 可略過 volume window 並前進 scorer request、21 rows 才依 price filter 完成後 lazy request volume，且 row／availability date 不能越過 cutoff。預設 `MISSING_COLUMN` 表示已觀測到來源欄位不存在；未來 app adapter 不可用它代表「尚未讀取」或「尚未要求」，必須正確投影 `NOT_REQUESTED`，再由 evaluator 發出 typed request。

| Gate | 證據與來源 |
|---|---|
| Owner | fresh TEMP staged route `113 passed`；mypy `706 source files, 0 issues`；import 與 compile checks 通過。 |
| Root | fresh TEMP replay／portfolio 9-file route `142 passed`；R019 route `159 passed`。 |
| Independent reviewer | focused route `74 passed`，未發現 P1/P2。 |

此 gate 僅接受 staged pure request/evaluation contract。C1c 後續已將 provider 接入 staged evaluator，並在收到 `NeedCandidateScoring` 後交回既有 app scorer；R005 的 raw float threshold conversion 次序仍須保留，invalid float threshold 必須在原 fast-filter/scorer try 邊界外拋出，不能轉成「unsupported／missing」後吞掉或延後。C1c 的 bounded 證據與未完成項見後文。

## C1b pure numeric-domain contract（bounded ACCEPTED_SCOPE）

此 pure contract 將數值來源（`ReplayNumericOrigin`）與 legacy coercion 後的有效比較域（`ReplayComparisonDomain`）分開記錄。有限值使用約分後整數 numerator／denominator 表示；無限值與 unordered 使用 typed component 狀態。唯一的 `evaluate_replay_prefilter` comparator 以精確整數交叉相乘比較 real operands，不在 pure decision core 新增裸 `float` 決策或匯入 NumPy。

Contract 可描述 exact-rational 與具格式／精度／exponent bounds 的 binary-real domain；NumPy complex 比較按 real component 優先、real 相等時再比較 imaginary component。Python complex ordering 依原運算子及 operand 順序重現原生 `TypeError`。metric／threshold effective domain 不一致時明確 raise `ReplayComparisonDomainMismatchError`，不轉成 pass 或 reject 結果。

| Frozen input | SHA-256 |
|---|---|
| Prefilter numeric-domain contract：`decision_module/recommendation/replay_prefilter.py` | `9AD37757E9D7DD8535A944E39D7302F0EB4DC7F7C0A8163DAB0F2732BD456292` |
| Staged evaluator：`decision_module/recommendation/evaluate.py` | `A0F684E53BD880320253E18538504A370F2B99B816C586D4E2984C374F842728` |
| Pure numeric-domain tests：`tests/test_recommendation_replay_prefilter.py` | `02C525A180DE682B50F4D1029D1A6F35FB695272636B489D207AC2AA2156BA1D` |
| Staged evaluator tests：`tests/test_recommendation_evaluator_replay_staged.py` | `80E7B3BECD4C304AE51ADCF14C30A03D83915977CB0758FB9F0F6092FCC766B7` |

以上 SHA 僅識別此 bounded pure-domain gate 的 frozen inputs，不代表整個共享工作樹或 repository HEAD。

| Gate | 證據與來源 |
|---|---|
| Owner | fresh TEMP 13-file route `172 passed`；mypy `706 source files, 0 issues`。 |
| Root | replay／portfolio 12-file route `175 passed`；R019 route `161 passed`。 |
| Independent reviewer | focused route `77 passed`，未發現 P1/P2。 |

這只接受 origin／effective-domain 資料契約與純比較語意。後續 C1b projector gate 固定同域 operand 投影，C1c 再依 evaluator 的 lazy fact requests 配對 operands 並接入 provider；C1c 在受限 profile 下獲 `ACCEPTED_SCOPE`，但不代表 full replay output parity 或 R020 retirement gate 完成。`TMP-REC-04` 與 `TMP-NUM-01` 仍為 `ACTIVE`。

## C1b app numeric projector（bounded ACCEPTED_SCOPE；Windows NumPy 2.3.5）

此 bounded slice 將舊流程計算的 metric scalar，及已完成舊 `float()`／成交量 normalization 的 Python float threshold，投影成相同 effective comparison domain 的 typed operands。Projector 不重算 metric、不正規化門檻、不比較 operands，也不選擇 pass／reject；當時 provider 舊比較仍是唯一篩選決策，後續 C1c 才將 paired operands 交給 staged evaluator。

| Frozen input | SHA-256 |
|---|---|
| App numeric projector：`app_module/recommendation/replay_numeric_projection.py` | `EA88A370E3485A3199BD7EBBF78F2E70CDA960C301D16B4D7F9B1BFF1E500D3C` |
| Projector tests：`tests/test_recommendation_replay_numeric_projection.py` | `8695F7EBE44AC199463C48BCD7C7E22169BCBF822FF7AD196EFA4BA6DEACE5D6` |
| Numeric dtype legacy oracle：`tests/test_r020_c1b_numeric_dtype_legacy.py` | SHA-256 `8825AF480B59A18843EA429D387E74F099F5FAA2C94AAFE1B7CACEE3BCC426E2`；與 R005 fresh TEMP combined route `38 passed`。 |

| Gate | 證據與範圍 |
|---|---|
| Runtime boundary | Windows、NumPy `2.3.5`。 |
| Owner | merged focused route `74 passed`；mypy `707 source files, 0 issues`。 |
| Root | fresh TEMP focused route `74 passed`。 |
| Independent reviewer | fresh TEMP focused route `141 passed`，未發現 P1/P2。 |

測試覆蓋 float16／float32 price 與 volume、int64、NumPy complex 及 `np.seterr`／overflow 行為。Projector 按 NumPy 2 runtime dtype metadata 投影 metric 和已轉換 threshold，有限 component 保留精確 rational；complex domain 保留 NumPy lexicographic operands。成交量 threshold 必須由 caller 先完成既有 normalization，projector 不會代做。此為原始 C1b gate 的 runtime 範圍（Windows NumPy 2.3.5）；後續 `TMP-NUM-01` follow-up 已在 Windows NumPy 1.26.4／2.3.5 對同 runtime native oracle 驗證包含 projector 的 provider route，但不外推到其他 NumPy 1.x 或非 Windows 較寬 `longdouble`。

此 C1b gate 僅接受 operand projector；後續 C1c 已在 provider 的實際 fast-filter path 按 staged request 呼叫 projector，並回填 paired typed facts。該連線只在受限 runtime profile 獲 bounded acceptance；跨 runtime 與 full replay parity 尚未證明，`TMP-REC-04`／`TMP-NUM-01` 仍為 `ACTIVE`。

## C1c provider fast-filter staged cutover（bounded ACCEPTED_SCOPE；受限 NumPy profile）

`RecommendationDataFrameProvider` 現在把每個候選的 fast-filter policy／typed observations 交給 `RecommendationEvaluator.start_replay_prefilter`／`advance_replay_prefilter`。純 `evaluate_replay_prefilter` 是 fast-filter 唯一比較點；只有 evaluator 回傳 `NeedCandidateScoring` 時才交給既有 app scorer。此項把比較責任交給 pure decision owner，但沒有移除 provider 的資料讀取或重寫 recommendation scorer。

App 保留 R005 的 metric 算法與讀取時點，收到對應 threshold fact request 後才依序執行 `float(raw)`、volume threshold normalization，並呼叫 projector 形成 paired typed operands。候選呼叫區域的 raw-scalar map 以 request ID 關聯 metric 與 threshold，不跨候選或 invocation 共用。Call-local as-of context 進入 observations 與 typed requests；`capture_sink` trace 繼續 best-effort 記錄，不參與 pass／reject。

| Frozen input | SHA-256 |
|---|---|
| Provider：`app_module/recommendation_dataframe_provider.py` | `CE690D894BC8F01E6640A757191A692C141F37468B3F8423BE7055574B44E5A6` |
| Prefilter／pure comparator：`decision_module/recommendation/replay_prefilter.py` | `6D153C36FE53E1B5CE38D380DCA64B158D945E42B0F2871CA9A7E977845CF458` |
| Staged evaluator：`decision_module/recommendation/evaluate.py` | `74D5FD3083DC507CF1317077C89DB861475DE95CF905847E54CF48A8BD622A98` |
| Staged evaluator tests：`tests/test_recommendation_evaluator_replay_staged.py` | `DE5CD8C9F9C7923AD70A74B5E3E6E2955B025AEE1628FF8F5DB06A523E35A403` |
| Provider adapter tests：`tests/test_r020_provider_staged_prefilter_adapter.py` | `73E59676AF3D0138C5997AE42EF2FFE1DD7E39707B388E41A4F9B60FB89B66B8` |
| Test inventory（latest after policy/output characterization registration）：`qa/full_app_healthcheck/test_inventory.py` | `8FE767161F2F55CE17FB7C300B429B46AAE9E728ECD65AC3100EFE6E86F93B08` |

| Gate | 證據與範圍 |
|---|---|
| Root | 最新 fresh TEMP 11-file replay／portfolio route `192 passed`；mypy `707 source files, 0 issues`。與 pre-cutover HEAD 舊 fast-filter 的 synthetic differential `798 cases, 0 mismatch`。 |
| Independent reviewer R027 | fresh TEMP route `95 passed`，未發現 P1/P2；bounded `ACCEPTED_SCOPE` 限於受限 NumPy profile。 |
| Test inventory | staged prefilter、numeric projector、provider adapter、scorer output characterization 與 execution policy tests 已登錄 `service-oracle-recommendation`。 |

後續 test-only scorer output boundary characterization 已加入 provider→snapshot `top_n=-1`／`top_n=0` double-slice golden。最終測試檔 `tests/test_r020_provider_output_boundary_characterization.py` SHA-256 為 `4DBB2FCE09AE74230C37FB0949597970DF321AE51FEB13010C6F340AF5ABEEF6`；root fresh TEMP 4-file route `52 passed`。先前 B5 版本的 6-file `83 passed` 是不同版本與路由；兩組結果不累加，皆不屬於 C1c 凍結的 192 passed route。

此證據只接受當時受限 NumPy profile 下的 provider fast-filter staged cutover；798 cases 是 synthetic differential，並非完整 replay corpus。該 C1c gate 當時尚未驗 NumPy 1；後續 Windows NumPy 1.26.4／2.3.5 各自 native-oracle route 已見本報告 runtime update，其他 NumPy 1.x 與非 Windows 較寬 `longdouble` 仍未驗證。Row-level PIT、同 mode V-REPLAY、typed child projection、parent persistence 與 TMP retirement 仍待後續 gate。C1c 不代表 R020 完成，也不關閉 `TMP-REC-04`／`TMP-NUM-01`。

## ReplayExecutionPolicyV1 純 policy contract（bounded ACCEPTED_SCOPE；後續排序接線另列）

本節保留純 policy contract 首次驗收時的範圍：當時 `RecommendationDataFrameProvider` 尚未消費此 policy。後續 bounded ranking gate 已由 provider 建立 `ReplayExecutionPolicyV1`，將 typed score-order tokens 與 policy 交給純 evaluator；evaluator 現負責穩定排序及 provider 第一層 `top_n` slice。Policy 記錄 app 已轉換後的 signed lookback／max-stocks／top-N 值、20-row minimum、Python float key 排序、逐檔 scorer error silent-skip，以及 provider 與 snapshot wrapper 各自套用一次 Python slice 的 double-slice 語意；它仍不負責讀取資料、lookback／universe 選擇或呼叫 scorer。

| Frozen input | SHA-256 |
|---|---|
| Pure policy：`decision_module/recommendation/replay_policy.py` | `1D9EBC7B85EC0E3F36289F16C9D30A2DB1646148A1CFF69D3094515D213D940F` |
| Policy tests：`tests/test_recommendation_replay_policy.py` | `2A8C6AA112075609F0CAA781F13BE7B30E0B2067E67BD63F06B7E50E8BD863F3` |
| Test inventory at this earlier C1c/policy gate：`qa/full_app_healthcheck/test_inventory.py` | `8FE767161F2F55CE17FB7C300B429B46AAE9E728ECD65AC3100EFE6E86F93B08` |

| Gate | 證據與範圍 |
|---|---|
| Owner | fresh TEMP focused route `30 passed`。 |
| Independent reviewer | fresh TEMP focused route `88 passed`，未報 P1/P2。 |
| Root | fresh TEMP focused route `51 passed`；mypy `708 source files, 0 issues`。 |

此 acceptance 當時只涵蓋純 policy contract；後續的排序／first-slice 接線範圍與證據見下節。實際 cutoff/frame 的完整 parity、所有執行責任的移轉，以及 full V-REPLAY 仍待後續 gate；`TMP-REC-04`／`TMP-NUM-01` 保持 `ACTIVE`，R020 整體仍為 `IN_PROGRESS`。

## Typed scorer candidate 與 evaluator ranking／provider first slice（bounded ACCEPTED_SCOPE）

Provider 保留逐股資料準備、既有 scorer 呼叫與 per-stock exception skip；每個成功候選先組成 `_ReplayScoredCandidateV1`，保留原 v1 row 欄位、順序與 `float(...)` coercion。之後 provider 將已轉換分數標記為有限有理數、NaN 或正／負無限值 token，並與 `ReplayExecutionPolicyV1` 一起交給 `RecommendationEvaluator.rank_replay_candidate_ordinals`。純 evaluator 作穩定降冪排序並套用 provider 第一層 signed Python slice，provider 再依 ordinal 投影回原 v1 dict row。Snapshot/replay wrapper 的第二層 `top_n` slice 仍保留，因此既有 double-slice 語意不變。

這項接線沒有新增 app-side score sort：provider 的 `sort_values("日期")` 仍只排序單一股票的時間序列；跨候選 score order 與第一層 slice 僅由 evaluator 執行。測試將 native Python reverse sort 與 typed ordering token 對照，涵蓋 NaN、正／負無限、穩定 ties、finite values，以及 `top_n` 的正、零與負值。`operator.index(top_n)` 仍在候選 scorer／理由格式化完成後執行；synthetic `__index__` 例外驗證 scorer 與 formatter 已依序呼叫後才拋錯，保留舊錯誤時點。此 bounded gate 不接管 lookback、first-seen max-stock selection、filter、source/cutoff 或 scorer，亦不建立 child execution／parent lineage。

| Frozen input | SHA-256 |
|---|---|
| Provider typed candidate／ranking handoff：`app_module/recommendation_dataframe_provider.py` | `CF9504E6972FC6F9A81D765D19BA33104D0E454A80BCA7B2E1548A5101DDAFDA` |
| Evaluator ordinal ranking／first slice：`decision_module/recommendation/evaluate.py` | `AF0C2C6F178F23498021369762FD58FE44AAC06D2E2D6DC5AAABA1A079832A21` |
| Tagged score order／execution policy：`decision_module/recommendation/replay_policy.py` | `582635D9C99288AEA20F4ADB555A56F80CE862133BA0CE27727B3DD6BD7B298D` |
| Policy tests：`tests/test_recommendation_replay_policy.py` | `AAA827553ED499087E434AE1D4DCBA957C0CA8E595189402D2D110FBD7EA0F6C` |
| Evaluator ranking tests：`tests/test_recommendation_evaluator_replay_ranking.py` | `50E6FF241D413AE8CA98F44CEFA10B14761EA1875D145362D9153B219800A910` |
| Current test inventory：`qa/full_app_healthcheck/test_inventory.py` | `6A9911273C67C1A79641C63861E30089DA866937F4A2427B9B3FEC72C03B5057` |

| Gate | Evidence and scope |
|---|---|
| Root | Fresh TEMP 14-file route `225 passed`, with 24 expected warnings; mypy `708 source files, 0 issues`; `py_compile` and diff checks clean. |
| Independent reviewer R023 | Fresh TEMP focused route `46 passed`; no P1/P2. |
| Independent reviewer | Fresh TEMP 6-file route `73 passed`; no P1/P2 in read-only parity/error-timing review. |

這段記錄的 ranking gate 當時只接受 provider typed candidate 到純 evaluator 排序與第一層 slice，尚未包含 child／Registry 接線；後續 bounded integration 見本報告「Typed provider child handoff 與 Registry lineage」。新的 2-child synthetic route 已驗 child→v1／Registry readback 及實際 child bytes；完整 portfolio DTO readback、row-level PIT 及 full V-REPLAY parity 尚未完成。R020 仍 `IN_PROGRESS`；`TMP-REC-04`／`TMP-NUM-01` 保持 `ACTIVE`。

## C1b numeric dtype legacy oracle 與 C1c 後續處置

新增的 test-only legacy oracle 以現有 `RecommendationDataFrameProvider` 固定 NumPy dtype 對舊比較的影響；不呼叫 staged evaluator，也不改變決策路徑。

| Input / QA | 證據 |
|---|---|
| Frozen numeric dtype legacy oracle：`tests/test_r020_c1b_numeric_dtype_legacy.py` | 最新 SHA-256 `8825AF480B59A18843EA429D387E74F099F5FAA2C94AAFE1B7CACEE3BCC426E2`。 |
| Local fresh TEMP／`PROFILE=test` oracle + R005 | `38 passed`；oracle `py_compile` 通過。 |

測試固定 float16 的 1% 漲幅在 `price_change_min=1.0001` 時放行，而 float32／float64 拒絕；float32 在門檻 `1.00000001` 時放行，float64 拒絕。float16 對 `price_change_max=0.9999` 放行、float32／float64 拒絕。float16 `[0.01, 65]` 產生的價格變化為 `+INF`，在預設 error mode 下以 `price_change_max=1e100` 仍放行。另在 `np.errstate(over='raise')` 下確認 float16 1% metric 可安全算出，但該巨大門檻於舊比較時拋 `FloatingPointError`；`price_change_max='bad'` 先因 `float()` 拋 `ValueError`，price-min 已拒絕時則不解析／cast max，兩種 scorer 都未呼叫。成交量 `[100] * 20 + [101]` 配 `volume_ratio_min=1.01` 時 float16／float32 拒絕、float64 放行；另固定 `[100] * 20 + [110]` 的弱 cast 邊界：float16 raw ratio `1.09964`、float32 `1.1000000191734864` 同域門檻與 metric 相等而放行，float64 同 ratio 拒絕。這些是既有 provider 比較的 characterization，不是新 evaluator 的結果。

以下為 C1c provider cutover 前記錄的 numeric adapter 風險。R027 已依 C1c frozen source／tests 重審實際 provider path；在 Windows NumPy 2.3.5 bounded profile 內，該 gate 為 `ACCEPTED_SCOPE`，未發現 P1/P2。以下限制仍須保留，不能由 bounded acceptance 外推：

- C1c 的實際 provider path 已在 request ID 對應的 staged evaluator flow 中使用 numeric projector 產生 typed operands；opt-in shadow trace 仍是診斷資料，不是決策輸入。Trace 以 Python `float`／`Decimal.from_float` 表示有限值，不能代表 NumPy dtype-rounded operand，因此不得拿 trace Decimal 重建 evaluator 比較。
- C1c bounded route 覆蓋 NumPy complex operand 投影及 no-price-threshold overflow 的舊錯誤時序；trace unavailable 仍不代表拒絕。後續兩個 Windows NumPy profile 各自 native-oracle evidence 見本報告末尾；不代表 NumPy 1／2 輸出彼此相等，也不擴張到其他 runtime。
- 此 C1c review 當時只在 Windows NumPy 2.3.5；後續 Windows NumPy 1.26.4／2.3.5 各自 native-oracle evidence 見本報告末尾，仍未覆蓋其他 NumPy 1.x 的 promotion 行為或非 Windows 較寬 `longdouble`。成交量 normalization 仍由 caller 先完成。
- requested as-of/cutoff 已由 call-local transport 傳至 provider，C1c 將其帶入 observations 與 typed requests；這不等同逐列 `available_date` PIT 驗收，也不可由資料最大日期猜 cutoff 或以 C0 summary 代替 row-level PIT。

因此，C1c 僅接受 frozen evidence 所涵蓋的 provider staged cutover，並未授權 full production parity 或 retirement。fast-filter 比較已由 staged pure evaluator 作為唯一決策點；`TMP-REC-04`／`TMP-NUM-01` 保持 `ACTIVE`，full replay parity 未證明。

## C1b requested-as-of provider transport（bounded ACCEPTED_SCOPE）

此處記錄較早驗收的 call-local requested-as-of transport seam。後續 C1c provider staged flow 已將這個明示 cutoff 帶入 observations 與 typed requests；該切片仍不代表 row-level availability／PIT 與完整 replay parity 已驗收。

| Frozen input | SHA-256 |
|---|---|
| Provider：`app_module/recommendation_dataframe_provider.py` | `D0D49C9BDB77D7A0A0448609341463C34DC8F13E912F00352AFF7B6A1A8AEB35` |
| Replay service：`app_module/recommendation_replay_service.py` | `5ADB97F83DB87C4F92067CF1B68A7854C9317130F00B040C915F1A9A313DD5FE` |
| Final transport tests：`tests/test_recommendation_replay_as_of_provider.py` | `51EFE9B4652BCAD809680E92531D7E92D641F8AF140EF27C4BC9E4CF08687CD8` |
| Test inventory：`qa/full_app_healthcheck/test_inventory.py` | `E3C64A8DD5B527CF10A5BACA9169F9219DA487307FF52EAAE2E261414BC19C8E` |

以上 SHA 只識別此 bounded gate 的 frozen inputs，不代表整個共享工作樹或 repository HEAD。`tests/test_recommendation_replay_as_of_provider.py` 已列入 test inventory 的 `service-oracle-recommendation` 分類。inventory 全域仍有 shared-tree 既有的 `115 unregistered` 與 `2 count drift`；這不是該測試未登錄造成的結果。

| Gate | 證據與來源 |
|---|---|
| Owner | fresh TEMP route `75 passed`；mypy `706 source files, 0 issues`。 |
| Root | fresh TEMP 12-file route `162 passed`；補強後 3-file route `38 passed`。 |
| Independent reviewer | 原 7-file route `97 passed`；as-of／R005 補強 route `17 passed`，未發現 P1/P2。 |

`RecommendationReplayService` 以 invocation 的 requested date 截切 history，再先排除 `available_date` 缺值或晚於 cutoff 的資料，最後套用 universe；diagnostics 在 universe selection 前計數。as-of-aware provider 透過 `run_with_as_of(data, config, top_n, date)` 收到 requested date；週末 cutoff 保留請求的週日，即使 frame 最新列為週五。`RecommendationDataFrameProvider` 使用 frozen／slots 的 call-local context，不把 date 存於 provider instance；同一 provider 並行處理不同 cutoff 時各自隔離。一般三參數 provider 仍使用原 `provider(data, config, top_n)` 呼叫契約。

該 context 不新增 `RecommendationSnapshotDTO` wire 欄位，也不改既有 snapshot wire/hash；R005 舊 filter characterization 仍通過。requested-as-of transport 已由 C1c provider staged flow 消費，但這只接受 call-local cutoff transport 與受限 profile 的 fast-filter cutover，不表示 row-level PIT 或完整 numeric/replay parity 已完成。`TMP-REC-04` 為 `ACTIVE`、R020 為 `IN_PROGRESS`。

## Typed provider child handoff 與 Registry lineage（2026-09-24；bounded integration）

`RecommendationDataFrameProvider` 的 concrete handoff 在同一次 scorer pass 後同序回傳 v1 rows 與 typed scoring outcomes；`RecommendationReplayService` 以 typed outcomes 建立 canonical child，不從 v1 row dict 重建決策。R023 已移除 `RecommendationReplayService._build_canonical_replay_execution` generic row→child builder；custom／legacy provider 仍可回傳舊 list，並保留 transient parent，但 canonical child 固定為 `None`。失配或 typed item 投影失敗時保留 v1 recommendation row、child 不可用；成功／空結果的 concrete typed child 語意沿用既有 contract。此接線不改 `RecommendationSnapshotDTO.recommendations` 的欄位、順序及 v1 list／舊 portfolio JSON 形狀。

Portfolio replay invocation 起點建立獨立 `replay_parent_id`；各 snapshot child 有自己的 `result_id` 並帶 `REPLAY_PARENT` reference，Registry `run_id` 在 UI 保存時另外建立，兩者不得混用。Lineage coordinator 會先驗完整批次的 snapshot／child identity，再以 R012 persistence 對 child artifact 執行 create-only save 與 verified readback。Versioned sidecar 保存按日期排序的 child IDs、canonical payload hashes 及 parent/reference facts；child canonical payload bytes 本身仍存於各自 R012 artifact，不嵌入 sidecar。

`BacktestView` 對有 parent identity 的 `RecommendationPortfolioBacktestResultDTO` 呼叫上述 coordinator，並把 sidecar 傳給 `ResearchRunService.save_run`。Registry manifest descriptor 綁定 sidecar schema/revision、parent ID、相對路徑、raw SHA-256、canonical payload hash 與 child count。Registry 依 staging→files_ready→committed 發布，`load_run_data` 讀取時驗 Parquet、sidecar hash／schema 與 lineage descriptor；它不會自行重讀 R012 child payload bytes。child bytes、payload hash、日期及 parent/reference 的獨立驗證須另呼叫 `verify_replay_lineage_children`。此路徑只完成 Registry run readback，不代表重新建出完整 `RecommendationPortfolioBacktestResultDTO` 或把新 run 加入 legacy 推薦歷史下拉選單。若實際 DTO 有 parent 但沒有可驗 child（包括 `snapshots` 為空），UI 仍保存正常 v1 Registry run，manifest 記錄 `replay_lineage_status.status=unavailable`、`reason=canonical_child_unavailable`；不發布空 lineage sidecar、不合成 child 或假 hash。舊 legacy JSON 與其 decoder 不變。

| Gate | 證據與限制 |
|---|---|
| Root merged route（先前證據） | fresh TEMP／`PROFILE=test` 19-file route `278 passed`、`24 warnings`；UI update view `84 passed`；mypy `710 source files, 0 issues`。此為先前較窄 route，保留作為獨立歷史證據。 |
| Prior consolidated route | fresh TEMP／`PROFILE=test` 24-file route `321 passed, 1 skipped, 24 warnings`；此為早於最新 root route 的獨立擴大路由，不與其他 route 相加。另有互動 UI 新增測試 `4 passed`，獨立記錄。 |
| 最新 root route | fresh TEMP／`PROFILE=test` 23-file route `308 passed, 1 skipped`；另一路 agent 10-file route `137 passed`；full mypy `710 source files, 0 issues`。這些是分開執行的 route，不相加。 |
| Dedicated R020 route（較早） | root-reported fresh TEMP route `33 passed, 1 skipped`；含 typed handoff、lineage service 與 UI→Registry checks，保留為早期 route 證據。 |
| UI／Registry lineage local route（先前） | fresh TEMP offscreen route `21 passed, 1 skipped`；含 `test_r020_ui_replay_lineage_save.py`、既有 UI save 與 Registry lineage tests；`py_compile`／`git diff --check` 通過。此為先前單一 child 的 UI save/readback route。 |
| R027 多 child lineage readback | fresh TEMP synthetic route `5 passed`；兩個 snapshot child 經 UI→R012→Registry 新讀回 service 驗證，並以 `verify_replay_lineage_children` 驗實際 child bytes；單一 child 損毀時整批 fail closed。這不驗證完整 portfolio DTO 重建或跨 store 復原。 |
| R027 custom／legacy no-child integration | synthetic route `6 passed`；custom／legacy provider 經 portfolio service→UI Registry→新讀回 service 保留 v1 rows 與 parent，但不產生 canonical child、sidecar 或假 artifact，manifest 標示 `lineage unavailable`。此 route 與前一個 2-child `5 passed` route 分開，不相加。 |
| Stage A portfolio-result codec | R027 frozen SHA 獨立複審 bounded `ACCEPTED_SCOPE`：`app_module/recommendation_portfolio_result_artifact.py` SHA-256 `559EAEFD1CAF3D4193D3499BCC6F64B66AF64733C93769F9DCB30DE97C5B4736`；`tests/test_r020_portfolio_result_artifact.py` SHA-256 `C7975D1A39888B46011BC4B12B1148431816112A5781017D15DECF0E28D529CC`；fresh TEMP `42 passed`、24 個既有 warnings，無剩餘 P1／P2。此 row 僅記 codec acceptance；Stage B1/B2/C/D receipts 分列如下。 |
| Stage B1 repository finalize CAS | B1 已 bounded `ACCEPTED_SCOPE`。專用 repository command 僅允許指定 `recommendation_portfolio` run 仍在 `staging/pending` 且 base `payload_hash` 相符時，以單一 transaction 固定 manifest／descriptor 與 final hash；保留原 manifest keys， committed／files_ready／failed 不可經此命令改寫。專項 CAS tests：`tests/test_research_run_portfolio_finalize.py` SHA-256 `15297F1E205F0FA396FAD3D55D8D944195A287881730E71D0599DBF07A8DC89C`。此列記錄先前 bounded acceptance，不另推算 pass 數。 |
| Stage B2 Registry opt-in publish/readback | R015 對最新 frozen B2 bytes 獨立 bounded `ACCEPTED_SCOPE`：service SHA `DC47816C62D1249629B2CE6303608B52503E3735882EAD74A68C75AF7D7B00CF`、repository SHA `8AA0454D124615B0CD783C83826A678A04CCD54BC47740571E825446729AE503`、tests SHA `CA18D12AF9F483C8302BF3C146D915B272BE42E79AED4A81C88AE9BE46B6D1C1`；fresh TEMP non-UI route 70 passed，mypy 0／compile 通過。B2 驗明示 `portfolio_result` 的 marked path、Parquet／sidecar bytes、metadata hash、sidecar identity 與 parent 綁定，並以 guarded state transitions 發布。此 gate 的拒絕發生在 Registry writes 前；不保證呼叫者在先寫 R012 child 前已驗好所有 Registry metadata。 |
| Stage C strict DTO materialization／child-integrated readback | R023 frozen-source 獨立 bounded `ACCEPTED_SCOPE`：reader SHA-256 `812ED626377812F53650EBDEA0E587A036AC6BED80E060CF532B085E18ADFACB`、tests SHA-256 `1C5E68904A4956C9416EE99B2986EABD78C36752A9C7C4C193462832EA02D124`；14 passed，交叉 route 79 passed／1 skipped。完整 DTO 僅在 artifact、manifest 與所有 declared R012 child bytes 驗證成功後回傳；舊 markerless run typed unavailable，marked corruption fail closed。此為 Stage C bounded gate，不代表 UI／V-REPLAY 全驗收。 |
| Stage D BacktestView Registry 專屬 save/open | R023 frozen-source 獨立 bounded `ACCEPTED_SCOPE`，無 P1／P2：7-file fresh TEMP route `95 passed`；Workbench `84 passed`；broad mypy `712 source files, 0 issues`；compile／diff-check 通過。實作者 R027 的 Update QA 為 `25 passed／0 failed／4 skipped`、exit 0；R023 另一次 Update QA 為 `25 passed／1 failed／4 skipped`，唯一失敗是 WinError32 TEMP SQLite teardown，不是功能 assertion，故不列為 reviewer pass。Stage D 整合 route 保留 `82 passed` receipt。Registry save 僅接受當次完整 `RecommendationPortfolioBacktestResultDTO`，傳 `portfolio_result` 並保留可選 R012 lineage；零 snapshots 走 parent-bound `unavailable`、不發布空 lineage sidecar。新 run 由 Registry 單選開啟，不進 legacy dropdown。讀回錯誤不套用部分結果；Registry 畫面不抓目前 benchmark overlay。 |
| B2 caller 與 reconcile boundary | `BacktestView` 現已傳入當次完整 `portfolio_result` 並使用 Registry 專屬入口；非 DTO 在 child／Registry 寫入前拒絕。DTO/parent 的上游檢查先於 child write，但 metadata builder/B2 guard 的部分驗證晚於 R012 create-only write；metadata 不合法可能留下可依同 ID 同 bytes 重試的 orphan child，這是已知 UI preflight residual。`reconcile_incomplete_saves` 是明確操作，呼叫前必須確認 writers quiescent；若 live staging writer 與 reconcile 競賽，reconciler 可 fail closed 將該 row 標 failed，沒有 lease／自動協調保證。 |
| R023 prior five-file cross-store recovery route | 歷史 frozen receipt：`tests/test_r020_cross_store_recovery.py` SHA-256 `9A72105242CF2DBD55E16DC9F40D8B93EF5419CC50C64C4ACD487DDFDE11FEA6`；fresh TEMP 五檔 route `77 passed, 4 skipped`。涵蓋 child2 failure/retry、Registry staging/files_ready reconcile 與 post-commit child corruption fail-closed。 |
| Earlier BacktestView same-run retry receipt | `tests/test_r020_cross_store_recovery.py` SHA-256 `7ADFA4CAE25BAEE6637E249A90E405E84BFECFDF692F1E694AA69CC2A6C0E2FC`；root fresh TEMP／`PROFILE=test` single-file route `10 passed`。經 UI save path 注入 Registry `before_temp_write` pre-insert failure，再以相同 `run_id` 重試；斷言失敗時 R012 child bytes 已存在而 Registry row／lineage sidecar 不存在，成功重試後 lineage descriptor、sidecar 與 child bytes 可驗且 child artifact 未重寫。這不是 failed/noncommitted Registry row retry，也不是 portfolio-result sidecar 或完整 DTO readback；process crash、child missing 與完整 DTO readback仍未覆蓋。 |
| R015 process-crash／missing-child bounded receipt | `tests/test_r020_process_crash_recovery.py` SHA-256 `07C2A71B44CB5A3462D0A800FE7EE9F793A6CFA19A487CE7846681352AF39C63`；R027 獨立 fresh TEMP 7-file route `142 passed, 3 skipped`，scoped mypy `7 source files／0 issues`、py_compile 通過。精確範圍為 **3 個 `spawn`／`os._exit` 真正 crash 點**（R012 child artifact 發布後／index 前、所有 child 完成後／Registry save 前、Registry `files_ready` CAS 後／artifact publish 前）加 **1 個 committed child 缺檔情境**；後者不是第四個 hard-exit。缺檔後 strict readback fail closed，並由測試明確重發同 hash 原 `RecommendationExecution` 驗證修復；同 ID／同 bytes retry 可恢復，異 bytes 不得覆寫。 |
| Required update-tab QA | 本輪在 fresh isolated TEMP 執行 `scripts/qa_validate_update_tab.py`：`25 passed, 0 failed, 4 skipped`，exit 0；未遇 WinError32。 |

本報告所列 QA 使用隔離 TEMP／synthetic fixtures；未讀寫正式資料或正式 Registry。Stage C 與 Stage D 均已各自 bounded `ACCEPTED_SCOPE`；Stage D 的獨立 review 證據與 Update QA teardown 例外見上表。R012 child store 與 Research Run Registry 不是同一 transaction。上表新增的 process-crash／missing-child receipt 僅證明列明的 3 個 crash 點與 1 個 committed child 缺檔情境，不代表完整 recovery gate：未覆蓋所有 partial-publish 窗口，兩個 store 沒有共同原子交易或補償 rollback，也不會自動重建原 execution；child 缺失後需明確以同 hash 原 execution 重發。`reconcile_incomplete_saves` 是顯式操作，只能在確認 writers quiescent 後執行；同 ID／同 bytes retry 可恢復，異 bytes 拒絕覆寫。`<20` count-only gate 不代表 CandidateAssessment；blank-code compatibility path 保留 v1 row/scorer，但不建立 canonical child；custom／legacy provider 亦無 canonical child。legacy history dropdown 只列舊 repository records。R020 維持 `IN_PROGRESS`；`TMP-REC-04`、`TMP-NUM-01` 為 `ACTIVE`，C2 未放行，R028 仍 `BLOCKED`。

## 尚待處理的 parity 與 integration risks

- C1a 已以 characterization／shadow tests 固定 NaN 邊界與 legacy float normalization，包括 denominator fallback、比較順序、lazy threshold conversion 及 `float(1.1)` 正規化後門檻值 `10.000000000000009`。C1c 另以 provider adapter tests 與 798-case synthetic differential 驗證受限 profile 下的 staged cutover；完整 V-REPLAY corpus parity 仍未完成。
- C1b pure contract 固定 raw/effective 分流及 staged lazy requests；C1c 已由實際 provider 建立 observations、lazy facts／thresholds，呼叫 projector 配對 staged evaluator，並在需要時交給既有 scorer。需保留 threshold comparison order、`float()` coercion 與 normalization 次數，成交量 normalization 由 caller 完成；C1a `Decimal.from_float` trace 不可作為 evaluator operand。Invalid threshold 的拋錯時機仍須在 scorer try 外。Windows NumPy 1.26.4／2.3.5 各自 native-oracle evidence 見末尾 follow-up；其他 NumPy 1.x 版本與非 Windows 較寬 `longdouble` 尚待驗證。Row-level PIT 及完整 replay parity 仍待後續 gate。
- parent／child typed handoff、Registry sidecar、完整 `RecommendationPortfolioBacktestResultDTO` readback 與 Registry UI 重啟入口均有 bounded synthetic coverage。R012 child bytes 在 readback 全批次驗證，child corruption fail closed；兩個 artifact stores 仍沒有共同 transaction。process-crash／missing-child 已有本報告記載的有限情境測試，但 full recovery gate 尚未證明。依 scope addendum，新 Registry run 不投影到 legacy history dropdown；該 dropdown 只列舊 repository records，屬隔離回歸條件。Registry 保存不表示 legacy JSON 已更新。

## Lineage persistence 的設計依據與目前實作界線

以下列出原唯讀調查提出的設計，並標示目前 bounded implementation；它不代表 `TMP-REC-04` 已退出，或所有 Registry／legacy reader 已統一。

- Portfolio service 已在 invocation 起點建立與 Registry `run_id` 分離的 parent ID；snapshot children 以各自 `result_id` 及 `REPLAY_PARENT` reference 表達。Coordinator 在寫入前檢查所有 child，避免缺件時只保存 lineage 一部分；實際 child bytes 存在 R012 artifact store，sidecar 只保存其 identity、references 與 canonical hash。
- Research Run Registry `data_manifest` 連結 versioned sidecar descriptor；staging／commit/readback 已由 2-child synthetic route 驗證，且 route 另行讀回並驗證 child payload bytes。Registry readback 不等於完整 portfolio DTO 已重建，也不等於舊 portfolio repository 已載入此 run或舊 JSON 有新增 sibling extension。舊 portfolio JSON schema 和 legacy decoder 維持未變。
- 完整 DTO 的保存／重啟／讀回已有 bounded Stage C/D synthetic route，涵蓋 multi-date child bytes、損毀 fail-closed、old markerless unavailable、stale open 與不回抓目前 benchmark；Stage C/D 均已 bounded `ACCEPTED_SCOPE`。跨 R012 child store 與 Registry 的 process-crash／child-missing recovery 有限度覆蓋為 3 個 hard-exit crash 點及 1 個 committed child 缺檔情境；這不等於完整 recovery gate，仍未覆蓋所有 partial-publish 窗口、跨 store 原子性或原 execution 自動重建。持倉／現金／交易／equity／v1 row 的完整同 mode parity 仍由 V-REPLAY／R005 gate；legacy history dropdown 保持只列舊 repository records。

## 2026-09-24 空白 code active-filter bounded slice

空字串及全空白 `stock_code` 在 active filters 下現在使用明確的 `ReplayCompatibilityPrefilterObservationsV1` 與 invocation-local `ReplayCompatibilityCandidateKeyV1`。一般 `ReplayPrefilterObservations`、`NeedCandidateScoring` 與 `RecommendationItem` 的非空 identity 驗證維持嚴格。compatibility observations 進入與有效 code 共用的 pure `evaluate_replay_prefilter` 和同一 numeric-pair projector；app 不再為空白 code 執行另一套 `<`／`>` 規則。`NeedCompatibilityScoring` 只允許既有 scorer 執行，terminal reject/unsupported 沒有 `assessment`；raw code 不 trim、不替換、不進持久化 identity。成功、空結果、scorer 例外與 row projection 例外均回填 identity-bound compatibility terminal outcome；稽核 tuple 僅留在單次 provider handoff，不進 SnapshotDTO、child 或保存 payload。被選取的空白 row 保留原 v1 `stock_code`、scorer output、order 與 top-N；canonical `scoring_outcomes` 仍為 `None`，因此不建立 canonical child。無 filter 的既有 compatibility path 未改。

`<20` rows 的 production loop 已改用 `RecommendationEvaluator.preflight_replay_history` count-only gate；19 rows 被略過、20/21 rows 照既有 route 繼續。這個結果是 typed minimum-history preflight，不是 CandidateAssessment，也不建立 canonical child。空白 code negative/positive min/max/volume、lazy conversion、invalid threshold exception、cutoff 前裁切、mixed valid/blank order/top-N、raw identity、scorer handoff 與 no-child 邊界由新 synthetic suite 固定。

本次 fresh TEMP／`PROFILE=test` route 在 `C:\Users\archi\AppData\Local\Temp\r20b_eebaf3` 執行，12-file suite `151 passed`：

```powershell
$run=Join-Path $env:TEMP ('r20b_'+[guid]::NewGuid().ToString('N').Substring(0,6)); $env:PROFILE='test'; $env:DATA_ROOT=Join-Path $run 'data'; $env:OUTPUT_ROOT=Join-Path $run 'output'; .\.venv\Scripts\python.exe -m pytest tests/test_r020_blank_code_active_filter.py tests/test_r020_history_preflight.py tests/test_r020_provider_staged_prefilter_adapter.py tests/test_r020_provider_scorer_handoff.py tests/test_r020_provider_output_boundary_characterization.py tests/test_recommendation_replay_prefilter.py tests/test_recommendation_evaluator_replay_staged.py tests/test_recommendation_evaluator_replay_scoring.py tests/test_recommendation_replay_characterization.py tests/test_recommendation_replay_as_of_provider.py tests/test_recommendation_replay_bridge.py tests/test_r020_concrete_portfolio_parity.py -q -o addopts= -p no:cacheprovider
```

驗證另以 `.\.venv\Scripts\python.exe -m mypy app_module/recommendation_dataframe_provider.py decision_module/recommendation/replay_prefilter.py decision_module/recommendation/evaluate.py` 得 `Success: no issues found in 3 source files`；四個 Python 檔案 `py_compile`、追蹤檔 `git diff --check` 與新測試 whitespace scan 均通過。Frozen implementation identity：provider `06FF5520BB60F82BD2918BE56772CD8484A6A217BDB5FEAE1EF500A735071BEC`、prefilter `5977EAD607719AC9732EEC6D2950ED6BFB6864EE2982418D471CB01999D18A0B`、evaluator `B80F9D9B60FDA694F7401E6F7221C2F9E45ECD4C1E5CBCD57F4AAD977E9905D4`、new tests `7A621E5ACA6185B9A87D14E47B66F92A8291A2DFE326DAC3E6134D7CD196AE19`；測試時 HEAD 為 `e16f92928980a025d24bd5b023eeadf9d6a31daa`。以上為 bounded synthetic evidence，待獨立 review；不宣稱完整 V-REPLAY／REC-04／NUM-01 parity 或 R020 acceptance。

## 2026-09-24 compatibility scorer terminal P2 修正

獨立 review 指出空白-code `NeedCompatibilityScoring` 雖交給舊 scorer，原先成功／空結果／例外後沒有完成 evaluator state。現在同一 evaluator 以 request-bound response 關閉為 `COMPLETE`，支援 `SCORED`、`SKIPPED_EMPTY`、`SKIPPED_SCORER_EXCEPTION` 與 `SKIPPED_PROJECTION_EXCEPTION`。Compatibility outcome 不含 `RecommendationItem`、`CandidateAssessment` 或 score；call-local audit tuple 不與 canonical scoring outcomes 混用，也不流入 child、SnapshotDTO 或保存 bytes。canonical `scoring_outcomes` 空白 row slot 維持 `None`，v1 row、scorer 次序、例外 skip 邊界、排序與 child 建立條件保持原樣。跨候選／invocation 回覆由 evaluator fail closed。

重新驗證使用 fresh TEMP `C:\Users\archi\AppData\Local\Temp\r020compatfinal_92770c83`、`PROFILE=test`，12-file R005/R020 focused route 為 `156 passed`（涵蓋 success／empty／scorer exception／projection exception terminal）。命令：

```powershell
$run=Join-Path $env:TEMP ('r020compatfinal_'+[guid]::NewGuid().ToString('N').Substring(0,8)); $env:PROFILE='test'; $env:DATA_ROOT=Join-Path $run 'data'; $env:OUTPUT_ROOT=Join-Path $run 'output'; .\.venv\Scripts\python.exe -m pytest tests/test_r020_blank_code_active_filter.py tests/test_r020_history_preflight.py tests/test_r020_provider_staged_prefilter_adapter.py tests/test_r020_provider_scorer_handoff.py tests/test_r020_provider_output_boundary_characterization.py tests/test_recommendation_replay_prefilter.py tests/test_recommendation_evaluator_replay_staged.py tests/test_recommendation_evaluator_replay_scoring.py tests/test_recommendation_replay_characterization.py tests/test_recommendation_replay_as_of_provider.py tests/test_recommendation_replay_bridge.py tests/test_r020_concrete_portfolio_parity.py -q -o addopts= -p no:cacheprovider
```

Mypy 為 3 個 source files／0 issues；`py_compile` 與所列 source/test paths whitespace check 通過。R023 frozen review SHA-256：provider `722E4B7167D6C4882D69232DA4612B359F638C0F9E5F5D05CDB16532996777B7`、evaluator `88B55FC4F450230ADFB92E46C7BC30ABD67A28AF4FC83C31138D8A96EC73F6CC`、blank-code tests `BC34D96E6FD5E62321BB4C360A8540B999B759463370DCB97E3EA7FEC37FC155`。該 frozen route 為 156 passed，獨立 review 無 P1/P2；空白 code compatibility scorer terminal slice bounded accepted。此 acceptance 不建立 canonical assessment／child，也不替代完整 V-REPLAY parity；`TMP-REC-04` 仍須保持 `ACTIVE`。

## Remaining R020 gates

R023 已獨立 bounded 接受 same-mode 固定向量測試；其當時 frozen `tests/test_r020_concrete_portfolio_parity.py` SHA-256 為 `9A274320B298C6C4BE659FD35A607187E9A455556FDF4CA453ADD872F66F8BC1`。原 fresh TEMP 16-file R005／V-REPLAY／R020 route `211 passed`、24 個既有 warnings，scoped mypy 4 files／0 issues，compile 通過。該歷史 receipt 固定 scorer/reason 與 synthetic vectors；不等於完整 V-REPLAY parity，也不關閉 `TMP-REC-04`、`TMP-NUM-01` 或 C2。2026-09-24 後續 next-open PIT 向量與最新 test SHA 見下段。

2026-09-24 增補 next-open 實際 portfolio caller 的 PIT 固定向量：`tests/test_r020_concrete_portfolio_parity.py::test_next_open_portfolio_caller_keeps_pit_snapshot_factor_golden`。此案例在 `NEXT_OPEN_CONTRACT` 下以 once 再平衡驗 19／20／21 可用列、缺失／未來／不可解析的 `available_date`、cutoff 後資料列，並逐欄固定有序 v1 rows、`unavailable_rows_excluded:3`、完整 factor snapshot／contributions、canonical child request/context cutoff 與 scorer 收到的日期；9/4 訊號只於下一交易日 9/7 建立買入。預期 rows、scorer 日期與 manifest 均為測試內手寫常數。此處只驗 next-open 自身的訊號／執行時點，不把 holdings、cash 或 P&L 與 legacy-close 比較。

fresh TEMP `C:\Users\archi\AppData\Local\Temp\r020_nextopen_route_2cab172804944a61921cac1a1df8265f`、`PROFILE=test` 六檔 route 為 `74 passed in 2.28s`；測試檔 SHA-256 `3AC9E5CE3EB9FA303857CB577258518C9AE7AE68C2F20EF71A2ACAB192FA7030`。命令：

```powershell
$run = Join-Path $env:TEMP 'r020_nextopen_route_2cab172804944a61921cac1a1df8265f'
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
.\.venv\Scripts\python.exe -m pytest tests/test_r020_concrete_portfolio_parity.py tests/test_recommendation_replay_characterization.py tests/test_recommendation_replay_as_of_provider.py tests/test_recommendation_replay_prefilter.py tests/test_recommendation_evaluator_replay_staged.py tests/test_r020_provider_staged_prefilter_adapter.py -q -o addopts= -p no:cacheprovider
```

`py_compile tests/test_r020_concrete_portfolio_parity.py` 通過；新測試已在 `qa/full_app_healthcheck/test_inventory.py` 登錄，不需變更 inventory。此 route 只新增一組 next-open caller 向量，不代表所有 V-REPLAY callers、所有 runtime profile 或完整 R005 corpus 已驗收；`TMP-REC-04`、`TMP-NUM-01` 仍為 `ACTIVE`。

### Next-open 同模式帳務與 parent reference 補充

2026-09-24 在同一 9/4 signal、9/7 next-open fill 的 synthetic PIT scenario 增加手寫帳務 golden。B/A 各有 500,000 配置預算；以 181/111 開盤買入 2,762/4,504 股，支出 499,922/499,944，零成本後餘額 134。依 9/7 起可見的 180/110 收盤價，持倉市值 992,600、期末現金 134、equity 992,734；golden 固定逐筆 fills、持倉列、cash ledger、equity curve 與摘要中的合約、狀態、開倉數、結餘、成本、已實現／未實現損益及報酬／回撤欄位。另驗唯一 typed child 的 `REPLAY_PARENT` reference 指向本次 portfolio parent，且 parent 與 child ID 不同。數值 expected 為測試內常數，沒有用 production 演算法回算 expected。

Look-ahead 邊界維持不變：9/4 scorer 最晚只收到 9/4 rows；9/7 開盤只用作後續成交價，9/7–9/9 close 不回流訊號或因子。這組 golden 只固定 `NEXT_OPEN_CONTRACT` 自身帳務，不要求與 legacy same-day-close 結果相等，也不涵蓋完整資金生命週期、費用模型、open-price 缺失、完整 V-REPLAY 或所有 replay caller。

fresh TEMP `C:\Users\archi\AppData\Local\Temp\r020_nextopen_ledger_b613efe2bc7b4c50a5fa92c2b757fac3`、`PROFILE=test` 六檔 route 為 `74 passed in 2.30s`；更新後測試檔 SHA-256 為 `0FA60D46126308E12E48B1B29099C34227EB04A176FEE4D653755B8B0B249BE2`。命令：

```powershell
$run = Join-Path $env:TEMP 'r020_nextopen_ledger_b613efe2bc7b4c50a5fa92c2b757fac3'
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
.\.venv\Scripts\python.exe -m pytest tests/test_r020_concrete_portfolio_parity.py tests/test_recommendation_replay_characterization.py tests/test_recommendation_replay_as_of_provider.py tests/test_recommendation_replay_prefilter.py tests/test_recommendation_evaluator_replay_staged.py tests/test_r020_provider_staged_prefilter_adapter.py -q -o addopts= -p no:cacheprovider
```

此 bounded 增補不關閉 `TMP-REC-04`／`TMP-NUM-01`，不代表整體 R020、C2 或完整 portfolio parity 已接受。

兩個 production path 現已有 bounded evaluator handoff：`<20` rows 呼叫 count-only minimum-history helper，19 rows reject、20/21 rows 不 reject；此 count-only slice 已獨立 bounded accepted，reject 不代表 CandidateAssessment。空白 code active filters 使用獨立 compatibility-only observations/key、共用 prefilter comparison core 與完整 scorer terminal；保留原始 v1 row，但不建立 canonical stock identity／assessment／child。此 compatibility terminal slice 依 R023 frozen 156P 獨立 review（無 P1/P2）bounded accepted；完整 V-REPLAY parity 未完成，`TMP-REC-04` 必須維持 `ACTIVE`。

1. 在已接受的受限 profile cutover 之外，完成同 mode V-REPLAY／R005 parity 與完整 cutoff／row-level availability 驗證；目前跨 runtime provider route 僅覆蓋 Windows NumPy 1.26.4／2.3.5，其他 NumPy 1.x 版本與非 Windows wider `longdouble` 仍需明確支援範圍及 parity evidence。沿用 C1a/C1b oracles，維持 19/20/21-row、lazy conversion、invalid-threshold exception order 及成交量 normalization 次序。
2. 擴展目前 bounded ranking handoff 的 caller parity：確認 app-owned signed lookback／max-stocks／source/cutoff／逐股 scorer skip，evaluator provider first-slice 與 snapshot wrapper second-slice 的完整組合符合 R005／V-REPLAY caller 行為。現有 gate 僅將 typed score order 與第一層 slice 交給 evaluator，不代表整份 replay execution policy 或資料準備責任已移轉。
3. 擴增 typed scorer outcome→child→v1 projection parity，涵蓋成功、空結果、非有限分數、projection failure 與每候選順序，不影響現有 portfolio／factor-manifest consumers。
4. 在既有 2-child synthetic Registry readback 證據上，完成完整 portfolio DTO 的保存／重啟／讀回；明確區分 Registry metadata/equity/trades/lineage sidecar readback、R012 child bytes 驗證、完整 portfolio DTO 與 legacy JSON reader，並驗證兩個 artifact stores 間 failure recovery。依 scope addendum，legacy history dropdown 保持只列舊 repository records；此為隔離回歸條件，不是待新增功能。
5. 通過 V-REPLAY 與 R005 同 mode exact parity，涵蓋既有 fast filters、cutoff／future／PIT、排序、empty、factor manifest，以及受影響的 portfolio output。

`TMP-REC-04` 保持 `ACTIVE`。`<20` count-only evaluator gate 已 bounded accepted，但不能證明 count reject 具有 canonical assessment/child；blank compatibility scorer lifecycle slice 依 R023 frozen 156P 獨立 review（無 P1/P2）bounded accepted，但不建立 canonical assessment/child。REC-04 還要求完整 V-REPLAY/R005 同 mode parity、caller 與全部 row/cutoff/ordering 組合驗證。Generic v1 row→canonical child builder 移除本身不構成退出證據。`TMP-NUM-01`、`C2` 與完整 R020 均未結案。本報告不宣稱 R020 完成或 replay parity 完成。

## 2026-09-24 TMP-NUM-01 runtime evidence update

- R015 對 frozen NumPy 1／2 修補給 `ACCEPTED_SCOPE`，無 P1/P2。Provider `app_module/recommendation_dataframe_provider.py` SHA-256 `F0B50C21D08D7867BE2B59D4F9B54D1A33C9E9CCD17A6788FAB2FDFBCDFC6630`；差異 oracle `tests/test_r020_numeric_runtime_differential.py` SHA-256 `D792F2B4AED996474FA4086C20F8C7C4CD63891C9606B639C297262AF1B01157`；C1b native-domain tests `tests/test_r020_c1b_numeric_dtype_legacy.py` SHA-256 `F6954D4E19607304F4F8D5C4A4C9CAF923686A387A431D5171795B61A48739AF`；provider adapter native-terminal test `tests/test_r020_provider_staged_prefilter_adapter.py` SHA-256 `568E73E4C6DF26959F3A331C668DECF630A85EF4C3ADEA9AEC510D05896908C2`。
- 根因與最窄修法：NumPy 1.26.4 將 `RankWarning` 放在 `np.RankWarning`，但沒有 `np.exceptions.RankWarning`；provider 原本在 scorer `try` 區內直接讀後者，缺屬性被捕捉成 scorer exception，候選因此遭靜默略過。Provider 現先解析 `np.exceptions.RankWarning`，缺少時才讀 `np.RankWarning`，仍只忽略 `RankWarning`。API-shape tests 證明 NumPy 2 優先分支不會碰舊 alias、NumPy 1 才走 lazy fallback；真實 no-filter provider 測試驗 scorer 被呼叫、v1 row 留存且 typed disposition 為 `SCORED`。沒有改 scorer 例外語意、比較式或公式。
- 同一 15-file R005／R020 provider route 在隔離 Windows profiles 均通過：NumPy 1.26.4／Pandas 2.3.3 為 `216 passed, 1 skipped`；NumPy 2.3.5／Pandas 2.3.3 為 `216 passed, 1 skipped`。獨立 4-file differential/C1b/provider adapter/scorer-handoff route 在兩個 runtime 各 `58 passed, 1 skipped`（R015 receipts：NumPy 1 log SHA-256 `CC719394E8C6B96818802B92C32F0EAEB532E0B792891CBBB0E26B91E318CB9D`；NumPy 2 log SHA-256 `7C479D5862F5C130539DB06D98DE3AEDB2110E5DA9590262005D811E17D63074`）。單獨差異檔 `tests/test_r020_numeric_runtime_differential.py` 在兩個 profile 各 `24 passed, 1 skipped`。相關 15-file 測試為 numeric differential、C1a legacy/shadow、C1b dtype、numeric projection/prefilter/evaluator、history preflight、provider adapter/handoff/blank-code/output boundary、as-of provider 及 concrete portfolio parity。
- NumPy 1 隔離 profile 的早期安裝曾因 `fastdtw==0.3.4` source build 找不到 `longintrepr.h` 而中止。後續只在 TEMP venv 中，先驗證 repo `.venv` 已安裝純 Python `fastdtw 0.3.4` 的 RECORD hashes，再連同 `dist-info` byte-for-byte 複製；沒有修改 repo `.venv`、依賴宣告或 production source。TEMP provenance JSON SHA-256 `D5006DEE131E0552CA479AA66A4AC625A80B426D7A8C5DD27C17D29FA054EC74`，路徑 `C:\Users\archi\AppData\Local\Temp\r020_num01_win_np1264_ad276b8ab2e643b993dc2e4493cf730c\full-runtime-install\logs\fastdtw-temp-copy-provenance.json`；TEMP venv 的 package import 路徑與功能 smoke 已核對。早期 provider fail route 是修補前 evidence，不能再描述為目前 collection blocker。
- 兩個 full-route runtime fingerprints 均為 Windows 10／CPython 3.11.9／Pandas 2.3.3。Windows NumPy 1.26.4 與 NumPy 2.3.5 各自對 native-operator oracle 通過；這只證明各 runtime 符合自身舊 native 行為，沒有要求或宣稱 NumPy 1 與 2 得到同一數值。NP1 route 保留三個 complex-NaN native comparison RuntimeWarnings；NP2 route 無 warnings。Windows `longdouble` 在兩個 profile 都是 `<f8`、8 bytes、52-bit mantissa；Linux／非 Windows wider `longdouble`、其他 NumPy 1.x versions 與其他 platforms 均未驗。
- `py_compile`、完整 prescribed mypy（712 source files／0 issues）與 `git diff --check` 通過；所有測試使用 fresh TEMP、`PROFILE=test`、獨立 `DATA_ROOT`／`OUTPUT_ROOT`。15-file logs：NumPy 1 `C:\Users\archi\AppData\Local\Temp\r020_rankwarning_np1_final2_0d7672080c6b4c65893049ec66c6fb86\logs`、NumPy 2 `C:\Users\archi\AppData\Local\Temp\r020_rankwarning_np2_final2_9db8d37795ab43b29b2cf2dfce224262\logs`；獨立 4-file logs 由上列 R015 receipt SHA 定位。舊 `tests/test_recommendation_replay_numeric_projection.py` overflow bounded evidence也仍顯示 `np.seterr(over="raise")` 下 NumPy 2 兩路都拋 `FloatingPointError`、NumPy 1 兩路都回 `True`；這是同 runtime parity 而非跨版本等值。

因此 `TMP-NUM-01` 與 `TMP-REC-04` 維持 `ACTIVE`，R020 維持 `IN_PROGRESS`；C2 未放行，R028 維持 `BLOCKED`。尚未驗完整 V-REPLAY／所有 caller parity、其他 NumPy 1.x versions、Linux 或 wider `longdouble` runtime。不得由兩個 Windows runtime 的 bounded acceptance 推論完整跨 runtime parity，也不得因 test-environment-only fastdtw provenance 改變依賴宣告。

`IMPLEMENTATION_STATUS: IN_PROGRESS` — C0 pure prefilter、C1a legacy characterization／opt-in shadow trace、C1b pure threshold／staged evaluator／numeric-domain contracts、Windows NumPy 1.26.4／2.3.5 provider-native numeric profile evidence、requested-as-of provider context transport、C1c provider staged fast-filter cutover、`ReplayExecutionPolicyV1` 純 policy contract，以及 typed scorer candidate／tagged ordering／evaluator ranking、provider first-slice、concrete typed child handoff、2-child synthetic Registry／R012 bytes readback、`<20` count-only evaluator preflight 與空白 code compatibility scorer terminal 均有 bounded evidence；generic v1 row→canonical child builder 已移除。Count-only reject／blank compatibility rows 不帶 canonical assessment／child；count preflight 已獨立 accepted，blank compatibility terminal slice 已依 R023 frozen 156P 獨立 review（無 P1/P2）bounded accepted；custom／legacy provider 仍無 canonical child。Stage C 完整 portfolio DTO readback 與 Stage D Registry 專屬 UI/readback 各自 bounded `ACCEPTED_SCOPE`；Stage D 由 R023 7-file fresh TEMP route `95P` 獨立接受，Workbench `84P`、broad mypy `712/0`、compile／diff-check 通過。Update QA 另分列 R027 `25P/0F/4S` exit 0 與 R023 `25P/1F/4S`（WinError32 TEMP SQLite teardown，非功能 assertion，不計 reviewer pass）。零 snapshots 會以 parent-bound `unavailable` 保存、不發布空 lineage sidecar；讀回空 DTO 時明示沒有 recommendation snapshots／canonical child 不可用。Process-crash／missing-child 已有 R015 frozen test `07C2A71B…` 的 bounded receipt（3 個真 hard-exit crash 點＋1 個 committed child 缺檔情境、R027 獨立 7-file `142P/3S`、mypy `7/0`、compile）；此數字不是「四個 hard-exit」。Full recovery gate 仍開啟：尚未覆蓋所有 partial-publish 窗口、跨 store 原子交易／補償 rollback 或原 execution 自動重建；reconcile 僅在 writers quiescent 後明確執行。row-level PIT 與 V-REPLAY parity 尚待完成；legacy history dropdown 依 addendum 保持 legacy-only 並以隔離 regression 驗證，非待合併功能。`TMP-REC-04`／`TMP-NUM-01`／C2 仍未結案，R028 維持 `BLOCKED`。

## 2026-09-24 signed 選股上限與 cutoff 組合固定向量

新增 `tests/test_r020_selection_cutoff_composition.py`，以 concrete provider 經 `RecommendationReplayService.run_snapshot` 固定 lookback、first-seen max-stocks、availability cutoff 與最小歷史列數在同一次呼叫中的舊次序。合成資料以 2026-09-24 為 cutoff：first-seen `P19` 在 positive 20-calendar-day lookback 範圍有 20 個來源列、其中一列缺 `available_date`，可用列為 19；`A` 在相同 lookback 範圍有 21 列、其中一列 `available_date` 晚於 cutoff，可用列為 20；`B` 在範圍內有 21 個可用列。另含 `C` 的 9/25 source row，該列在 provider 選股前被 service cutoff 移除。缺失與未來 availability diagnostics 固定為 `unavailable_rows_excluded:2`。

- `_portfolio_lookback_days=20`、`_portfolio_max_stocks=2` 固定 first-seen cap 先取 `P19`、`A`，再做 history gate：P19 因 19 列未呼叫 scorer，但先佔一席；21-row 的 B 因 cap 不呼叫 scorer。A 的完整 scorer dates、v1 row、canonical item／assessment 與 parent reference 均以測試常數斷言。
- 同 lookback、max-stocks=3 時，scorer 依來源順序收到 A 20 列、B 21 列；v1 rows 與 canonical items／assessments 均固定排名為 B、A。
- 負 lookback `-5` 沿舊規則不裁歷史日期；負 max-stocks `-1` 保留 Python `unique()[:-1]`，選入 P19/A/B 並排除最後 first-seen 的 C。A/B 的舊日期仍到達 scorer，結果 rows／child 順序及 parent reference 固定為 B、A。

這是單一合成組合的 bounded evidence，不替代所有 caller／universe／fast-filter 組合或 full V-REPLAY；不改 production。Fresh TEMP `C:\Users\archi\AppData\Local\Temp\r020_selection_cutoff_70e7fb53df214ca5ae318b1c316a8a79`、`PROFILE=test` 的五檔 route 為 `54 passed in 2.38s`，log 保存在該 TEMP 的 `pytest.log`。命令：

```powershell
$env:PROFILE = 'test'
$env:TEMP = 'C:\Users\archi\AppData\Local\Temp\r020_selection_cutoff_70e7fb53df214ca5ae318b1c316a8a79'
$env:TMP = $env:TEMP
$env:DATA_ROOT = Join-Path $env:TEMP 'data'
$env:OUTPUT_ROOT = Join-Path $env:TEMP 'output'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r020_selection_cutoff_composition.py tests/test_recommendation_replay_characterization.py tests/test_recommendation_replay_policy.py tests/test_r020_typed_provider_child_handoff.py tests/test_r020_concrete_portfolio_parity.py -q -o addopts= -p no:cacheprovider
```

新測試 SHA-256 為 `FA49C538B90CF88252B48E5803D6B45A462C77725F463FD50791A4A0A34BD647`；inventory 已登錄於 `qa/full_app_healthcheck/test_inventory.py`。測試及三個相關 replay source 的 scoped mypy 為 4 files／0 issues；新測試 `py_compile` 與 whitespace check 通過。`TMP-REC-04`、`TMP-NUM-01` 仍為 `ACTIVE`，R020 維持 `IN_PROGRESS`，不據此宣告 R020 acceptance 或 V-REPLAY full parity。

## 2026-09-24 混合 scorer terminal 與雙層切片固定向量

前一個 signed-selection／cutoff slice 已由 R015 獨立接受：fresh TEMP 五檔 route `54 passed`，無 P1/P2；該 receipt 只涵蓋 signed lookback、first-seen cap、availability cutoff 與 19/20/21 列組合，本段新增 scorer terminal／投影終端組合，不擴張為完整 V-REPLAY parity。

新增 `tests/test_r020_replay_mixed_terminal_composition.py` 三個 concrete provider→`RecommendationReplayService.run_snapshot` 案例：

- 第一個 `top_n=-1` 案例在同一次 invocation 依序完成成功、empty scorer、scorer exception、typed projection exception 與成功候選。固定 evaluator terminal 順序及 disposition；兩層切片前 provider handoff 保留 `HI, SELECTED_PROJECTION, MID, SECOND_SLICE_PROJECTION`，provider 首次切片已排除 `FIRST_SLICE_TAIL`，snapshot 第二次切片再排除 `SECOND_SLICE_PROJECTION`。最終 v1 rows 明確固定為 `HI, SELECTED_PROJECTION, MID`；被選中的 projection failure 使 canonical child 整體不建立，v1 相容列仍保留。
- 第二個案例把唯一 projection failure 放在 provider 首次切片後末位，讓 snapshot 第二次切片排除該列。最終 rows/items/assessments 同序為 `HI, MID, LO`，canonical child 成功並保留 parent reference。這固定 projection failure 只在它留於最終 snapshot 時阻止 child。
- 第三個案例沿用既有 provider native-sort characterization 的 `list.sort(reverse=True)` 固定預期 `NAN, POS_INF, TWENTY, TEN, NEG_INF`，逐列驗 NaN 與正負無限值仍保留於 v1 row；非有限 canonical score fail closed，不建立部分 child。其他 R005 frozen replay behavior 由此段 focused route 中的 R005 characterization／concrete portfolio parity 路徑驗證。

所有案例在歷史資料附加 2026-09-25 poison row，並斷言每次 scorer input 的最後資料日均為 2026-09-24 cutoff。Expected row order、terminal order、factor fields、scores、selection reasons 與 parent identity 均由測試常數直接斷言；沒有變更 production 或 R005 oracle，也未新增核心數值計算。

Fresh TEMP `C:\Users\archi\AppData\Local\Temp\r020_mixed_terminal_final_e8af387689e24a7fbb4939466e7869b8`、`PROFILE=test` 的七檔 route 為 `50 passed in 2.76s`，log 位於該 TEMP 的 `pytest.log`。覆蓋檔案：新 mixed-terminal test、selection/cutoff composition、provider output boundary、scorer handoff、typed provider child handoff、R005 replay characterization、concrete portfolio parity。新測試與 provider/service 的 scoped mypy 為 3 files／0 issues；`py_compile`、本檔 inventory membership/category check 及 `git diff --check` 通過。重跑命令：

```powershell
$run = 'C:\Users\archi\AppData\Local\Temp\r020_mixed_terminal_final_e8af387689e24a7fbb4939466e7869b8'
$env:TEMP = $run
$env:TMP = $run
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r020_replay_mixed_terminal_composition.py tests/test_r020_selection_cutoff_composition.py tests/test_r020_provider_output_boundary_characterization.py tests/test_r020_provider_scorer_handoff.py tests/test_r020_typed_provider_child_handoff.py tests/test_recommendation_replay_characterization.py tests/test_r020_concrete_portfolio_parity.py -q -o addopts= -p no:cacheprovider
.\.venv\Scripts\python.exe -m mypy app_module/recommendation_dataframe_provider.py app_module/recommendation_replay_service.py tests/test_r020_replay_mixed_terminal_composition.py
.\.venv\Scripts\python.exe -m py_compile tests/test_r020_replay_mixed_terminal_composition.py
```

新測試 SHA-256 為 `78BC83D226C5FD963DB74FF280CA648E42B33D799DEF671E0D19E857F651C067`；`qa/full_app_healthcheck/test_inventory.py` SHA-256 為 `2B1B2AC5CE68C83BD78135CA5132750BDB56A055CA67332EB1DAD402A0F9EF51`。

同次附帶執行全庫 `tests/test_full_app_healthcheck_test_inventory.py` 時，該 inventory audit 的 `test_all_python_files_are_registered_exactly_once` 因 shared worktree 中其他尚未登錄的新增 Python 測試而失敗（合併 route `56 passed, 1 failed`）；失敗列表不含本次新檔，本次新檔已列入 `qa/full_app_healthcheck/test_inventory.py` 並通過直接 category check。未擴大修改其他 agent 的 inventory entries。

本段只接受這三組 synthetic mixed-terminal 向量，不證明所有 scorer projection failures、NaN permutations、signed top-N、caller 或 runtime 組合。`TMP-REC-04`、`TMP-NUM-01` 保持 `ACTIVE`，R020 維持 `IN_PROGRESS`；不宣告 V-REPLAY full parity、R020 acceptance 或 C2 放行。


## 2026-09-24 聯合 provider／snapshot 切片固定向量

新增 `tests/test_r020_replay_pipeline_composition.py`，以同一個 concrete `RecommendationDataFrameProvider`→`RecommendationReplayService.run_snapshot` call path 和一份 cutoff history，按固定 case matrix 串接 provider 首次排序／切片、snapshot 第二次切片、v1 row 相容投影與 typed child all-or-none 判定。所有 expected code order、v1 欄位與 scorer call rows/date 均為測試內固定常數；非有限排序沿用已凍結 R005/provider-native stable reverse-sort 向量，不從 staged 結果計算 expected，也未改 production 或 R005 oracle。

- 每個 case 均含 first-seen `P19`（availability 後 19 rows、不得呼叫 scorer）、`HI`（20 rows）、其餘至少一檔 21 rows，三筆 unavailable rows 與 2026-09-07 future poison；cutoff 為 2026-09-06 星期日，scorer 只收到截至 2026-09-04 的可用列，snapshot diagnostics 固定為 `unavailable_rows_excluded:3`。
- case matrix 固定 `top_n=-1` 的 provider／snapshot 雙負切片、`top_n=0` 的空結果、`top_n=2` 的正切片，以及含 NaN／正負 Infinity 的 native v1 排序。每案斷言同次 scorer 順序、空回應與 RuntimeError skip、handoff row/outcome identity、兩階切片後的 v1 rows；selected projection failure 與只在第二次切片被排除的 projection failure 分別驗證 child 整體拒絕與成功 child 的 items／assessments 同序及 parent reference。
- 這是 provider→service 的合成組合 characterization，不是獨立重跑歷史 native provider 的第二次 scorer oracle，也不涵蓋完整 portfolio holdings/cash/equity/trades 全流程；full V-REPLAY／R005 caller matrix 與跨 runtime gate 仍未完成。

Fresh TEMP `C:\Users\archi\AppData\Local\Temp\r020_joint_c4873ebf`、`PROFILE=test`、獨立 `DATA_ROOT`／`OUTPUT_ROOT`、offscreen Qt route；log 為該 TEMP 下 `pytest.log`：

```powershell
$run = 'C:\Users\archi\AppData\Local\Temp\r020_joint_c4873ebf'
$env:TEMP = $run
$env:TMP = $run
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r020_replay_pipeline_composition.py tests/test_r020_replay_mixed_terminal_composition.py tests/test_r020_concrete_portfolio_parity.py tests/test_r020_typed_provider_child_handoff.py tests/test_recommendation_replay_characterization.py tests/test_r020_selection_cutoff_composition.py -q -o addopts= -p no:cacheprovider --tb=short
```

結果為 `37 passed in 2.66s`，exit 0；scoped mypy 命令 `.\.venv\Scripts\python.exe -B -m mypy app_module/recommendation_dataframe_provider.py app_module/recommendation_replay_service.py tests/test_r020_replay_pipeline_composition.py` 得 3 files／0 issues，`py_compile tests/test_r020_replay_pipeline_composition.py` 與 `git diff --check` 通過。新測試 SHA-256 為 `FD82378DA1D1C163034A7B3813E96FF129DD8F4846A15EE4E6C14606119BF74B`；inventory SHA-256 為 `4E2A398EE13B4D2120AB11BA37AA2E4E202A355D9202A1607D0D219946B30416`。本 slice 僅補一組跨切片固定向量，`TMP-REC-04`／`TMP-NUM-01` 仍為 `ACTIVE`，R020 仍為 `IN_PROGRESS`；不據此宣告 V-REPLAY full parity、R020 acceptance 或 C2 放行。

## 2026-09-24 portfolio caller 帳務與 replay 混合終端固定向量

新增 `tests/test_r020_portfolio_joint_matrix_composition.py`，在同一次 `RecommendationPortfolioBacktestService.run_portfolio_backtest` invocation 中，將 19/20/21 可用列、availability cutoff、mixed scorer terminal、v1 row projection、canonical child all-or-none 與 portfolio 帳務接在一起。測試重用既有合成歷史及 R005 v1 row shape；expected rows、診斷、holdings、cash ledger、equity curve、trades 與摘要欄位均以固定值斷言，未改 production 或 R005 oracle。

- 截止日為 2026-09-04；P19 有兩列不可用，保留 first-seen 名額後以 19 列 history gate 排除；HI 有一列不可用，20 列送入 scorer；其餘候選各有 21 列。scorer call 的代碼／列數／最後日期均固定，且逐列檢查 scorer input 不含 2026-09-07；該日期只供已持倉出場使用。
- 此 portfolio wrapper 在目前 Windows／Pandas 環境的 scorer encounter order 固定為 `SELECTED_PROJECTION, BROKEN, SECOND_PROJECTION, EMPTY, TAIL, MID, HI`。這是 portfolio caller 先依日期排序後觀察到的順序，與 direct `run_snapshot` caller 不同；本測試只限定目前 runtime 的 portfolio caller，不推廣為跨 runtime 排序契約。
- top-2 v1 rows 固定為 HI、SELECTED_PROJECTION，保留 opaque legacy reason row；該 selected projection failure 讓 canonical child 整體不存在。兩列仍進入同日收盤組合回測：HI 以 100 進、110 出，損益 +50,000；SELECTED_PROJECTION 以 200 進、180 出，損益 -50,000。固定 assertions 覆蓋兩筆 holdings、四筆 cash ledger、三列 equity curve、四筆 trades、期末現金 1,000,000 與零報酬摘要。

Look-ahead 自查：provider scorer 僅收到日期不晚於 2026-09-04 且已通過 available-date cutoff 的資料；2026-09-07 價格不出現在 scorer input，只作 cutoff 後持倉出場觀測。此 case 證明一個 mixed-terminal portfolio caller 組合，不是完整 R005/native provider 雙執行比較、V-REPLAY 全矩陣或跨 runtime scorer order 證據。

Fresh TEMP `C:\Users\archi\AppData\Local\Temp\r020_portfolio_joint_final_cc28ce3e58e44148938d11593218588f`、Python 3.11.9／NumPy 2.3.5／Pandas 2.3.3、`PROFILE=test`、獨立 DATA_ROOT／OUTPUT_ROOT 的八檔 focused route 為 `44 passed in 3.66s`，exit 0；完整輸出位於該 TEMP 的 `pytest.log`。路由檔案為新測試、`test_r020_replay_pipeline_composition.py`、`test_r020_replay_mixed_terminal_composition.py`、`test_r020_selection_cutoff_composition.py`、`test_r020_concrete_portfolio_parity.py`、`test_r020_typed_provider_child_handoff.py`、`test_recommendation_replay_characterization.py`、`test_r020_provider_output_boundary_characterization.py`：

```powershell
$run = 'C:\Users\archi\AppData\Local\Temp\r020_portfolio_joint_final_cc28ce3e58e44148938d11593218588f'
$env:TEMP = $run
$env:TMP = $run
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r020_portfolio_joint_matrix_composition.py tests/test_r020_replay_pipeline_composition.py tests/test_r020_replay_mixed_terminal_composition.py tests/test_r020_selection_cutoff_composition.py tests/test_r020_concrete_portfolio_parity.py tests/test_r020_typed_provider_child_handoff.py tests/test_recommendation_replay_characterization.py tests/test_r020_provider_output_boundary_characterization.py -q -o addopts= -p no:cacheprovider --tb=short
```

Scoped mypy（provider、replay service、portfolio service、新測試及其 pipeline helper）為 5 files／0 issues；新測試 `py_compile`、inventory category check 與 whitespace check 通過。Static-check TEMP 為 `C:\Users\archi\AppData\Local\Temp\r020_portfolio_static_final_3aa56a9f6a4a48c8907d6dd0a3795764`，執行命令：

```powershell
$run = 'C:\Users\archi\AppData\Local\Temp\r020_portfolio_static_final_3aa56a9f6a4a48c8907d6dd0a3795764'
$env:TEMP = $run
$env:TMP = $run
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = Join-Path $run 'pycache'
.\.venv\Scripts\python.exe -B -m mypy --cache-dir (Join-Path $run 'mypy_cache') app_module/recommendation_dataframe_provider.py app_module/recommendation_replay_service.py app_module/recommendation_portfolio_backtest_service.py tests/test_r020_portfolio_joint_matrix_composition.py tests/test_r020_replay_pipeline_composition.py
.\.venv\Scripts\python.exe -B -m py_compile tests/test_r020_portfolio_joint_matrix_composition.py
```

Inventory category check 確認新路徑映射至 `service-oracle-research-backtest`；`git diff --check` 未報 whitespace error。Inventory 分類為 `service-oracle-research-backtest`。

新測試 SHA-256 為 `9C0E6ADCE5B8C2DD36BDAF9E39DF3E33E00C94DEEE0D40BC9233D0B13F9F5290`；本次工作樹 inventory SHA-256 為 `6316634757F24E0487430F1180E0D0827280229CDEE408954A896DF6A643EE5C`。本證據只補 portfolio caller 的一個同次 v1／child／帳務 fixed vector；`TMP-REC-04`／`TMP-NUM-01` 仍為 `ACTIVE`，R020 仍為 `IN_PROGRESS`，不宣告 V-REPLAY full parity、R020 acceptance 或 C2 放行。

R015 獨立 review 對此 bounded portfolio caller slice 判定 `ACCEPTED_SCOPE`：獨立八檔 `44 passed`、新測試單檔 `1 passed`、scoped mypy `5 files／0 issues`，未發現 P1/P2。此 receipt 僅接受上述一組 same-invocation portfolio／v1／child／帳務固定向量；`TMP-REC-04`、`TMP-NUM-01`、完整 V-REPLAY、R020 與 C2 仍未結案。

## 2026-09-24 V-REPLAY／TMP-REC-04 closure evidence ledger

本 ledger 對照 `REFACTOR_TASKS/R020.md` 的 V-REPLAY full relevant、R005 exact parity、cutoff／future／PIT／empty、受影響 portfolio output 與第二 replay engine 搜尋要求。每一列是獨立 bounded receipt；不同 SHA、不同 caller 或不同 route 的結果不合併成一個 full-pass。通過某一列只接受該列標示的 fixture／runtime／行為。

| Required gate | Immutable receipt／測試及來源快照 | 狀態與剩餘範圍 |
|---|---|---|
| 安全的 V-REPLAY relevant 子集 | fresh TEMP `C:\Users\archi\AppData\Local\Temp\r20242c11`；runtime Windows 10 build 26200／CPython 3.11.9／NumPy 2.3.5／Pandas 2.3.3；`pytest-32-file-route.log` SHA-256 `584ECB118465584B2CFDFA58DAEB9D900549E4B4AA0A0661CFC672AAA2CBEC89`；32-test/source manifest `sha256-manifest.txt` SHA-256 `CD49DFACF1AEAE709154D29FC7B027D9FAC7BB53D698A17AB8DE97CD2C8D7CE8`，記錄 HEAD `e16f92928980a025d24bd5b023eeadf9d6a31daa` 及完整測試、來源檔 SHA；`436 passed, 1 skipped, 24 warnings`。主要來源 SHA：provider `F0B50C21D08D7867BE2B59D4F9B54D1A33C9E9CCD17A6788FAB2FDFBCDFC6630`、replay service `56DE1CC986D139C08512F7413F05D235405C418039B739662A6706A987AD7CF8`、portfolio service `FB4C9DBFF55B5E96B0B5659AE985999F46728AE4781CBC7C377A77597DEE84BA`、evaluator `88B55FC4F450230ADFB92E46C7BC30ABD67A28AF4FC83C31138D8A96EC73F6CC`、prefilter `5977EAD607719AC9732EEC6D2950ED6BFB6864EE2982418D471CB01999D18A0B`。 | bounded 32-file route 通過；**不是** V-REPLAY full relevant acceptance。`test_r020_cross_store_recovery.py`、`test_r020_process_crash_recovery.py`、`test_r020_ui_replay_lineage_save.py` 未包含在這個同次 route；它們的獨立收據列於下方，不能合併宣稱同一個 35-file/full route 通過。 |
| R005 selection／cutoff／19-20-21 rows、signed lookback／cap | `test_r020_selection_cutoff_composition.py` SHA-256 `FA49C538B90CF88252B48E5803D6B45A462C77725F463FD50791A4A0A34BD647`；五檔 fresh TEMP route `54 passed`；上列 provider、service、portfolio source SHA；R015 獨立 `ACCEPTED_SCOPE`。 | bounded accepted。固定一個同次 selection/cutoff 組合，包括 19 rows 先佔 first-seen 名額再被 gate 排除、availability 缺失／晚於 cutoff、負 lookback 與 Python 負切片；不代表全 caller／universe 矩陣。 |
| provider 首次排序／top-N 與 snapshot 第二次切片 | `test_r020_replay_pipeline_composition.py` SHA-256 `FD82378DA1D1C163034A7B3813E96FF129DD8F4846A15EE4E6C14606119BF74B`；R005 characterization `test_recommendation_replay_characterization.py` SHA-256 `F572128AFC270E7C865EF6533B5DEBFA2B1608AEFADDD946E473E547F4D35A21`；同次 concrete provider→`run_snapshot` 六檔 route `37 passed`；來源 SHA 如 safe-route manifest；R015 獨立 `ACCEPTED_SCOPE`。 | bounded accepted。固定 cutoff、availability、19/20/21、signed／zero top-N、兩層切片及 child all-or-none 的一組合成向量；不涵蓋全部 R005 模式與所有 portfolio callers。 |
| scorer 終端、projection failure 與 native non-finite row order | `test_r020_replay_mixed_terminal_composition.py` SHA-256 `78BC83D226C5FD963DB74FF280CA648E42B33D799DEF671E0D19E857F651C067`；七檔 route `50 passed`；R015 獨立 `ACCEPTED_SCOPE`。 | bounded accepted。固定成功／empty／exception、選中與第二層切片排除的 projection failure，以及一個 NaN／±Inf native-sort vector；不覆蓋所有排列、runtime 或 caller。 |
| 受影響的 portfolio 同次 caller／帳務 | `test_r020_portfolio_joint_matrix_composition.py` SHA-256 `9C0E6ADCE5B8C2DD36BDAF9E39DF3E33E00C94DEEE0D40BC9233D0B13F9F5290`；R005 characterization `test_recommendation_replay_characterization.py` SHA-256 `F572128AFC270E7C865EF6533B5DEBFA2B1608AEFADDD946E473E547F4D35A21`、fixed-vector `test_r020_concrete_portfolio_parity.py` SHA-256 `0FA60D46126308E12E48B1B29099C34227EB04A176FEE4D653755B8B0B249BE2`；八檔 route `44 passed`，另新測試單檔 `1 passed`；來源 SHA 如 safe-route manifest；R015 獨立 `ACCEPTED_SCOPE`，scoped mypy 5 files／0。 | bounded accepted。固定一組 portfolio caller 的 v1 rows、child all-or-none、holdings、cash、equity、trades 與摘要；其 scorer encounter order 僅是目前 Windows／Pandas caller 證據，不是跨 runtime 保證或全 portfolio parity。 |
| `<20`、blank-code 與 custom/legacy provider bounded paths | `<20` preflight test `tests/test_r020_history_preflight.py` SHA-256 `1BF8021BF473D7EDD05CD8D2CD05E2A0215FBA18CBCFD8591E84F89074D0ED87`；blank test `tests/test_r020_blank_code_active_filter.py` SHA-256 `BC34D96E6FD5E62321BB4C360A8540B999B759463370DCB97E3EA7FEC37FC155`；custom/typed handoff tests `tests/test_r020_replay_parent_identity.py` `FB7272D7CAC7E4706518691C375FA6664B9DE3D71446F25FF3DF6E6E6EB704E6`、`tests/test_r020_typed_provider_child_handoff.py` `3B4D56AFAFCAEC439F582FF7CDC1774C1C21CE5994BE844AE6D0894865EEF31B`；來源 provider `F0B50C21D08D7867BE2B59D4F9B54D1A33C9E9CCD17A6788FAB2FDFBCDFC6630`、evaluator `88B55FC4F450230ADFB92E46C7BC30ABD67A28AF4FC83C31138D8A96EC73F6CC`、prefilter `5977EAD607719AC9732EEC6D2950ED6BFB6864EE2982418D471CB01999D18A0`，上述 SHA 亦列於 safe-route manifest；`<20` count-only handoff 獨立 bounded accepted；blank lifecycle R023 frozen `156 passed` 獨立 bounded `ACCEPTED_SCOPE`。 | bounded exception，不是 full child parity：19 rows 只產 history-count reject、不產 assessment／child；blank code 保留 v1 row並產 noncanonical compatibility terminal／call-local audit；custom／legacy provider 僅保留 v1 rows＋transient parent，canonical child 為 `None`。 |
| Registry／sidecar 保存、讀回與 UI 入口 | Stage A artifact codec：`app_module/recommendation_portfolio_result_artifact.py` `559EAEFD1CAF3D4193D3499BCC6F64B66AF64733C93769F9DCB30DE97C5B4736`、測試 `C7975D1A39888B46011BC4B12B1148431816112A5781017D15DECF0E28D529CC`，R027 bounded `42 passed`；B2 Registry：`research_run_service.py` `DC47816C62D1249629B2CE6303608B52503E3735882EAD74A68C75AF7D7B00CF`、repository `8AA0454D124615B0CD783C83826A678A04CCD54BC47740571E825446729AE503`、測試 `CA18D12AF9F483C8302BF3C146D915B272BE42E79AED4A81C88AE9BE46B6D1C1`，R015 bounded `70 passed`；Stage C reader `812ED626377812F53650EBDEA0E587A036AC6BED80E060CF532B085E18ADFACB`、測試 `1C5E68904A4956C9416EE99B2986EABD78C36752A9C7C4C193462832EA02D124`，獨立 `14 passed`、交叉 `79 passed, 1 skipped`；Stage D 最新 empty-snapshot 修正 BacktestView `71D3C400A42049F93CD56AC0274B05016B2AFF103D44992536981A496122AEEC`、result panel `EA871AC0DD0DEB9F2CA328BE90AFAA79ED109254B6976A464AE0983321CC4C10`、compare widget `24854B480E7B7624012AC2374282ADEF0183A9A18442EFDF7B284C79858C4DA5`、UI/restart test `BF37F1CCDC77613995D0512A12FCF9793C351FD26D7C206E26B306AC78A8A9E3`、cross-store test `BE801428A36893E6F18441A260021ADBD8E23517960B8C81A8249ABD016FC92B`；R027 六檔 route `82 passed`、Workbench `84 passed`、Update QA `25 passed／0 failed／4 skipped`、broad mypy `712／0`。Update QA 另有 R023 獨立 `25 passed／1 failed／4 skipped`；唯一 failure 是 WinError32 TEMP SQLite teardown，非功能 assertion，不列為 pass。 | 各自 bounded 保存／strict readback／UI receipts；Stage D 另有先前 R023 7-file `95 passed` receipt，但它早於 empty-snapshot 修正，不與最新六檔 `82 passed` receipt 混算。Stage D 路由不代表 32-file V-REPLAY route。空 snapshots 明示 parent-bound unavailable，不建立空 lineage sidecar。 |
| Cross-store／process-crash recovery | Cross-store regression `test_r020_cross_store_recovery.py` 最新 frozen SHA `BE801428A36893E6F18441A260021ADBD8E23517960B8C81A8249ABD016FC92B`；process-crash `test_r020_process_crash_recovery.py` SHA `07C2A71B44CB5A3462D0A800FE7EE9F793A6CFA19A487CE7846681352AF39C63`，R027 七檔 route `142 passed／3 skipped`。另早期五檔 cross-store route `77 passed／4 skipped`、舊測試 SHA `9A72105242CF2DBD55E16DC9F40D8B93EF5419CC50C64C4ACD487DDFDE11FEA6` 僅保留歷史，不替代最新 SHA。 | recovery 各有 bounded failure／retry／fail-closed evidence，未證明所有 partial-publish windows、跨 store 原子交易／補償 rollback 或自動重建 execution。`reconcile_incomplete_saves` 僅可在 writers quiescent 時顯式呼叫；不得把分開路由合併成完整 recovery pass。 |
| TMP-NUM-01 runtime parity | 同一 15-file route：Windows CPython 3.11.9／Pandas 2.3.3 下 NumPy 1.26.4 與 2.3.5 各 `216 passed, 1 skipped`；獨立四檔 native differential/C1b/provider route 各 `58 passed, 1 skipped`，log SHA 與 provider/test SHA 詳見本報告 `TMP-NUM-01 runtime evidence update`（`:377-386`）。 | 只接受各 runtime 對自身 native oracle 的 bounded parity；不表示 NumPy 1／2 數值相同。公開 OS／Python／NumPy／Pandas 支援政策尚未定案；Linux／wider `longdouble`、其他 NumPy 1.x／OS 未驗，TMP-NUM-01 保持 ACTIVE。 |

## 尚未關閉的 TMP-REC-04／R020 gate

- **Single evaluator／post-score filters：bounded cutover accepted，完整 V-REPLAY 仍 open。** Provider 在 scorer 前將 prefilter 送 evaluator（`app_module/recommendation_dataframe_provider.py:681-809`）；R015 對平台修補後 source 做兩個 runtime 的定向 11P 複審，root 接受此有限切片。cutover 只適用 typed `as_of_date`、精確 built-in `StrategyConfigurator` 與 active filters；injected／subclass／overridden scorer 的非空列仍是 v1-only、沒有 canonical child。原始 config 保留作 versioned policy／receipt，interactive `StrategyConfigurator` 與 `RecommendationService` source／API／預設行為不改。原先 R015 `CHANGES_REQUIRED` finding 因非 Win32 complex fail-closed gate與 NP1 runner 路徑修正而關閉；完整 R005/caller/mode parity、支援矩陣內其他 runtime 與所有尚未驗的 numeric/profile 行為仍是 gate。
- **Bounded compatibility terminals 不等同 canonical replay closure。** `<20` history count-only preflight 已 accepted，但 reject 不產生 `CandidateAssessment`／child；blank `stock_code` compatibility route 即使 scorer success／empty／exception／projection exception，也只產 identity-bound noncanonical terminal／call-local audit，不進 canonical assessment／child；custom／legacy provider 保留 v1 rows＋transient parent，canonical child 為 `None`。這些是明示例外，不得當成已證明所有 provider 都產生同一 canonical child。
- **32-file safe subset 的三個 caller/recovery 檔缺口已由後續 route 取代。** 歷史 32-file route 未同次執行 `test_r020_cross_store_recovery.py`、`test_r020_process_crash_recovery.py`、`test_r020_ui_replay_lineage_save.py`；2026-09-25 的 40-file expanded route 已包含這三檔，並由 R015 對凍結 manifest、NP1／NP2 logs 與額外 accounting/PIT route 獨立 bounded accepted（詳下節）。此修正只關閉該 route-combination 缺口；scheduled、personalization、saved-result consumers 與 affected UI 的 C2 union 尚未執行，R026 source-backed historical replay 亦未納入。完整 V-REPLAY／C2 gate 還要求同 mode 的 fast-filter、cutoff／future／PIT、排序／empty、factor-manifest、portfolio output、consumer parity 與 repo 搜尋，不能把不同 route 拼成未驗範圍的 PASS。
- **TMP-NUM-01 support policy 仍需產品／工程 owner 決定。** 本 ledger不把單一 Windows constraints snapshot解讀為排除 Linux 或鎖定全部使用者至兩個 Windows profile；在支援矩陣正式定義並對矩陣內所需 runtime補齊 evidence 前，numeric gate保持 ACTIVE。
- R020 仍 `IN_PROGRESS`；`TMP-REC-04`、`TMP-NUM-01` 均 `ACTIVE`；C2 未放行，R028 維持 `BLOCKED`。本 ledger 不宣稱 R020 acceptance、V-REPLAY full PASS 或 REC-04 retirement。

## 2026-09-24 Replay-only post-score evaluator scope decision

root 依 frozen characterization `tests/test_r020_post_score_legacy_policy_characterization.py` SHA-256 `3BC8A019D4C9AADEBB80108854B38DD27403BCF5DB95E94A23AD039322A312BC`、`tests/test_r020_real_scorer_filter_stage.py` SHA-256 `FC7C689F9B1ABF7D801705DFA4198CC85131AF33D5E0EE13CDC6B522941904A2`，及 R023 獨立架構複核意見作成此裁定。前者凍結 19／20／21 rows、兩個 volume aliases、RSI、price alias、invalid-threshold 順序及 cutoff 負例；後者以真實 scorer 固定 20-row volume fallback、21-row pass 與 RSI-only skip。兩份均是 bounded characterization，不是遷移後 parity receipt。

核准的下一步只限 replay：使用原 config 建 versioned policy／receipt，以 call-local 無 `filters` config 取得 scorer 輸出，再由既有 `RecommendationEvaluator` 的新增 typed post-score phase 唯一決定 replay 篩選；interactive `RecommendationService` 與 `StrategyConfigurator` 預設路徑保持不變。custom／overridden scorer 無法形成 typed handoff 時必須維持 v1-only／無 canonical child 或 fail closed。實作與獨立 same-mode parity review 尚未完成，R020 `IN_PROGRESS`、`TMP-REC-04`／`TMP-NUM-01` `ACTIVE`、C2 未放行、R028 `BLOCKED` 均維持；本裁定不代表 FINAL 架構的跨模式全域統一完成。

## 2026-09-24 replay-only typed post-score pure phase（尚未接線）

新增 `RecommendationEvaluator.evaluate_replay_post_score()` 與版本化 `ReplayPostScorePolicyV1`／`ReplayPostScoreFactsV1` contracts。輸入只接受同一 `NeedCandidateScoring` 的 scored terminal、candidate-scoped typed metric operands 與 app boundary 已投影的門檻；不讀原始 filter dict、不做 volume ratio 正規化，也不含 DataFrame／I/O。固定規則順序為 price minimum、price maximum、effective volume-change percent minimum、RSI minimum、RSI maximum；inclusive 邊界沿用既有唯一 numeric comparator。缺欄明確 skip、unordered/NaN 明確 reject、domain mismatch 與 Python complex ordering errors 由共用 comparator 傳出。任一拒絕後仍走完其餘啟用規則，保留後段錯誤可達性；此 phase 沒有重現 Pandas empty-Series dtype error 的承諾。

本 slice 只建立 pure API，**沒有**修改或呼叫 provider、`StrategyConfigurator`、interactive `RecommendationService`、legacy diagnostics、warning/counter、filter normalization、wire、codec 或 child publication。未解析門檻以 typed `UNSUPPORTED` 表示；未來 adapter 仍須在正確 legacy 邊界維持原 threshold parsing／Pandas exception 類型與時點。`rsi_source_column` 僅記錄 app 已按 `RSI` → `rsi` → `RSI_14` 選出的欄位；本 slice 不負責讀取／選欄。Look-ahead 自查：facts 綁定 scorer request 的 `as_of_date`，pure phase 不再取任何資料；日後接線仍須證明 facts 來自該 request cutoff 內同次 scorer 的 latest row。

前置 frozen oracle 保持原 bytes：`tests/test_r020_post_score_legacy_policy_characterization.py` SHA-256 `3BC8A019D4C9AADEBB80108854B38DD27403BCF5DB95E94A23AD039322A312BC`、`tests/test_r020_real_scorer_filter_stage.py` SHA-256 `FC7C689F9B1ABF7D801705DFA4198CC85131AF33D5E0EE13CDC6B522941904A2`、`tests/test_r020_post_score_diagnostics_characterization.py` SHA-256 `0B7A9B7FF9E60044AD3D4FE2BE049F5F4F802123DB467041DA12A15CDD8A3988`。後者 QA receipt SHA-256 `BDD9AEFBC55FE6C936A48E8034B3A4BEB1F86A0F60F88B2CC39EB5F14CE52064`，diagnostics suite 14 passed、含 legacy 三段呼叫順序／warnings／counter 與後段 invalid-filter 錯誤。以上皆是 pre-cutover characterization；新 pure phase 不改診斷行為。

新測試 `tests/test_r020_replay_post_score_evaluator.py` 起初在 API 尚未新增時，以缺少 `ReplayPostScoreDispositionV1` 的 import error 收集失敗；實作後單檔 8 passed。最終七檔 fresh TEMP／`PROFILE=test` 路由（含三份 frozen post-score oracle、R019 staged evaluator、C1 prefilter 與 numeric projector）為 107 passed in 5.30s，exit 0；TEMP `C:\Users\archi\AppData\Local\Temp\r020_postscore_freeze_fb0bf58e58b9425a8824b22e0fa9908f`：

```powershell
$run = 'C:\Users\archi\AppData\Local\Temp\r020_postscore_freeze_fb0bf58e58b9425a8824b22e0fa9908f'
$env:TEMP = $run
$env:TMP = $run
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r020_replay_post_score_evaluator.py tests/test_r020_real_scorer_filter_stage.py tests/test_r020_post_score_legacy_policy_characterization.py tests/test_r020_post_score_diagnostics_characterization.py tests/test_recommendation_evaluator_replay_staged.py tests/test_recommendation_replay_prefilter.py tests/test_recommendation_replay_numeric_projection.py -q -o addopts= -p no:cacheprovider --tb=short
```

同一隔離 TEMP 中 scoped mypy `decision_module/recommendation/evaluate.py decision_module/recommendation/replay_prefilter.py tests/test_r020_replay_post_score_evaluator.py` 為 3 files／0 issues；上述三個 Python 檔 `py_compile` 通過，inventory membership 驗證通過，`git diff --check` 對 inventory／本報告 exit 0。新測試 SHA-256 `8C30E9857D4541590B3E70F92F649EA26AD9147C841F04D70F34221B1EB21308`；evaluator SHA-256 `14353F882B62FA5A8D4B3BBCE6C1847AD2E424BA93DB5F01B9AF6FBE8157A5C8`；prefilter SHA-256 `C12E07C5EAF638BB86EF50D2A98D4D37EBE05652FB78FB6473E7FA189D22439A`；inventory SHA-256 `61A322FB7C46A79DFD2DA953A2E05B09862ADAB7C690527E849B3CCE2E0D53C1`。本 slice 尚待獨立 review。`TMP-REC-04`、`TMP-NUM-01` 仍 `ACTIVE`，R020 `IN_PROGRESS`；provider cutover、legacy diagnostic parity、invalid-threshold exception parity 與同模式輸出仍待後續 gate，C2 未放行、R028 `BLOCKED`。本 slice 不宣告 R020 bounded acceptance。

## 2026-09-25 post-score NumPy complex unordered-status correction

修正本純 phase 的 NaN 狀態判斷：原 `_replay_operand_is_unordered()` 只要 NumPy complex imaginary component 為 NaN 就拒絕，會略過共用 comparator 的 lexicographic real-first 規則。`ReplayComparisonResult` 現由唯一 directional comparator 同次回傳 `matched` 與此次比較是否真正遇到 unordered component；既有 bool comparator API 保持不變。Post-score evaluator 以 comparator 回傳狀態決定 `unordered_value`，Python complex ordering 與 domain mismatch 仍先由 comparator 拋錯。沒有新增裸 `float` 核心運算或 provider 接線。

新增 regression 透過既有 app numeric projector 對照目前 NumPy native operator 與 shared comparator：`np.complex64(2+nanj) >= 1.0` 必須通過；實部相等的 `np.complex64(1+nanj) >= 1.0` 必須拒絕並記 `unordered_value`。修正前單檔 red route 為 1 failed／9 passed，失敗只在實部已決定結果的第一案；修正後單檔 10 passed。Look-ahead 自查：純 evaluator 仍只使用同一 `NeedCandidateScoring` request 綁定的 typed facts，不讀日期序列或新來源；本次修正只有數值比較狀態判讀。

fresh TEMP `C:\Users\archi\AppData\Local\Temp\r020_postscore_freeze_4aad2546f1a240899910b5ba4e51b88d`、`PROFILE=test` 的七檔 route 為 109 passed in 3.62s。Root 另以獨立 fresh TEMP 重跑相同七檔 route，109 passed，並獨立核對 frozen source/test/report SHA。Route 含本 post-score evaluator regression、三份 R015 post-score legacy characterization、R019 staged evaluator、fast-prefilter 與 numeric projection tests；scoped mypy 為 3 files／0 issues，三個修改範圍 Python 檔 `py_compile` 通過，`git diff --check` 通過。Inventory 已有本 test membership（`qa/full_app_healthcheck/test_inventory.py:378`），本次不修改共享 inventory。

本次 frozen SHA-256：`decision_module/recommendation/evaluate.py` `32527C68CD1CDB5157D31820B14246115CB54691DC3A1D337A1141F4FC7AA845`；`decision_module/recommendation/replay_prefilter.py` `DD150FF858AECC413A12A5ACAC42FBB31EA30BD1E3EE2CF04323E9CF355795BD`；`tests/test_r020_replay_post_score_evaluator.py` `FE4031F14A048291FA61DBE2F1D102F95FB22524F36DB028F5E85C7278AB966E`；inventory `61A322FB7C46A79DFD2DA953A2E05B09862ADAB7C690527E849B3CCE2E0D53C1`。Root 依獨立複核將此 replay-only pure post-score phase 判為 bounded `ACCEPTED_SCOPE`。接受範圍僅限純 evaluator API；pure phase 尚未接 provider，diagnostics、invalid-threshold exception timing 與 same-mode output parity 仍未接線／驗收。`TMP-REC-04`／`TMP-NUM-01` 仍 `ACTIVE`，R020 仍 `IN_PROGRESS`、C2 未放行、R028 `BLOCKED`。

## 2026-09-25 scorer-row-ready pre-item pure entry（root bounded ACCEPTED_SCOPE）

為讓未來 replay provider 能在理由、v1 row 與 `RecommendationItem` 投影前執行同一 post-score 規則核心，新增 `ReplayScoredRowReadyV1(request, facts)` 與 `RecommendationEvaluator.evaluate_replay_post_score_ready(ready, policy)`。Ready contract 只含同一 `NeedCandidateScoring` 和 `ReplayPostScoreFactsV1`，建構時驗證 facts request 完全相符；不含 `RecommendationItem`，亦不以虛構 item 作為 ready 標記。原 item-bearing `evaluate_replay_post_score(scoring, facts, policy)` 保留 `SCORED`／item 與 stock identity 驗證，再委派共用 request/facts/policy 核心；比較器、規則順序、threshold contract 與 wire/codec 均未更動。此純 contract 仍由日後 app boundary 負責只在實際 scorer 回傳非空 row 後建立；dataclass 本身不證明 scorer 執行，且目前沒有 provider 呼叫已走此入口。

新測試先以 import error 確認 no-item API 尚不存在，再固定 no-item price reject、request/facts 與 policy invocation 錯配 fail-closed，以及 ready entry 與既有 item-bearing entry 在相同 facts 下結果相同。使用 `PROFILE=test`、獨立 TEMP/DATA_ROOT/OUTPUT_ROOT，執行 `tests/test_r020_replay_post_score_evaluator.py`、三份 post-score characterization、R019 staged evaluator、C1 replay prefilter 與 numeric projector共七檔路由，`112 passed in 2.36s`；TEMP `C:\Users\archi\AppData\Local\Temp\r020-row-ready-final-d0119e295db548e3ba265ef3dcf6aa58`。Scoped mypy `decision_module/recommendation/evaluate.py decision_module/recommendation/replay_prefilter.py tests/test_r020_replay_post_score_evaluator.py` 為 3 files／0 issues；evaluate/test `py_compile` 與三個變更檔 trailing-whitespace scan 通過。Frozen source/test SHA-256：`decision_module/recommendation/evaluate.py` `715DD97BFF94923B7A584A419FE06C67CC35D55D0BC05D295B13B64EE7E0A376`；`tests/test_r020_replay_post_score_evaluator.py` `98A6799B314E916F230B845EAEC683CCACDCC3B1F035280CF3483F5E989A9CEE`。Inventory 已登錄此測試，未改 inventory。Root 獨立核對上述 source/test SHA，並以另一 fresh TEMP 執行七檔相關路由：`tests/test_r020_replay_post_score_evaluator.py`、`tests/test_r020_real_scorer_filter_stage.py`、`tests/test_r020_post_score_legacy_policy_characterization.py`、`tests/test_r020_post_score_diagnostics_characterization.py`、`tests/test_recommendation_evaluator_replay_staged.py`、`tests/test_recommendation_replay_prefilter.py`、`tests/test_r020_numeric_runtime_differential.py`，`116 passed / 1 skipped`；唯一 skip 是 numeric differential 案例，與本 pure API 無關。Root 對本切片給予 bounded `ACCEPTED_SCOPE`。Look-ahead 自查：純入口只接已綁定 `NeedCandidateScoring` request 的 typed facts，不讀歷史資料；未來 provider 必須從該 request cutoff 內同次 scorer 的非空末列建構 ready envelope。此 slice 只擴充純 evaluator contract，不接 provider／`StrategyConfigurator`，不覆蓋 diagnostics、threshold coercion/error timing、20-row feature fallback、same-mode output 或 child parity；R020 `IN_PROGRESS`、`TMP-REC-04`／`TMP-NUM-01` `ACTIVE`、C2 未放行、R028 `BLOCKED`。

## 2026-09-25 nullable `min_return_pct=pd.NA` scorer characterization（R015 bounded ACCEPTED_SCOPE）

R015 獨立複核此 test-only legacy oracle，未發現 P1/P2，root 判為 bounded `ACCEPTED_SCOPE`。合成 21-row case 直接呼叫原生 `StrategyConfigurator.generate_recommendations`，並經 concrete `RecommendationDataFrameProvider` 再呼叫一次；兩次均記錄原有 nullable 漲幅警告。Provider scorer 實收 21 rows，回傳 v1 rows 與 scoring outcomes 皆空，terminal 為 `SKIPPED_EMPTY / scorer_empty_result`。三檔 fresh TEMP／`PROFILE=test` adjacent route（post-score diagnostics、legacy policy、real scorer）為 32 passed；不修改 provider、Strategy、evaluator 或 inventory。

凍結識別：`tests/test_r020_post_score_legacy_policy_characterization.py` SHA-256 `6B27AB51C7BE478375DD9496B5DF8F04FEEE8AE26275559C15AFEEB0AD9186D6`；QA `docs/06_qa/R020_POST_SCORE_LEGACY_POLICY_CHARACTERIZATION_20260924.md` SHA-256 `CF06AA64A6E0ACD8CA1B2A2694CC27AA068FD6DFE97E486BD427B7EC02F44C96`。本 oracle 只固定原生 scorer 對 `pd.NA` alias 的警告與空結果，不代表 provider/evaluator cutover、full same-mode parity 或完整 PIT gate；R020 仍 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 仍 `ACTIVE`，C2 未放行，R028 `BLOCKED`。

## 2026-09-25 deferred post-score threshold P2 獨立複審（bounded ACCEPTED_SCOPE）

R027 以 frozen bytes 獨立複審 staged deferred-threshold 修補，無 P1／P2，範圍 bounded `ACCEPTED_SCOPE`。`decision_module/recommendation/evaluate.py` SHA-256 為 `203BC9E972B8D092D3549FF83377B893886DE1717C55C43339488D5AA114E5E4`；`tests/test_r020_replay_post_score_evaluator.py` SHA-256 為 `053E2B2CB71AFDAB903D0A2B7B924E4190EB44DD12EC86EAC81C4A78FD29C4A8`。複核確認：present-but-unsupported metric 會先要求 deferred threshold；只有 `MISSING_COLUMN` 略過 threshold；deferred response 只允許 `ENABLED`／`UNSUPPORTED`，`DISABLED`／`PENDING` fail closed；eager 與 staged 共用 `_evaluate_replay_post_score_rule`，response 綁定目前 candidate 與 rule。

獨立 reviewer 使用 fresh TEMP `C:\Users\archi\AppData\Local\Temp\r2psdab1786e`、`PROFILE=test` 跑五檔 route，`55 passed in 1.49s`。路由包含 pure post-score evaluator、legacy policy／diagnostics、real scorer filter 與 unsupported-metric legacy characterization；TEMP、`DATA_ROOT`、`OUTPUT_ROOT` 與 pytest basetemp 均隔離。可重跑命令：

```powershell
$run = 'C:\Users\archi\AppData\Local\Temp\r2psdab1786e'
$env:TEMP = $run
$env:TMP = $run
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r020_replay_post_score_evaluator.py tests/test_r020_post_score_legacy_policy_characterization.py tests/test_r020_post_score_diagnostics_characterization.py tests/test_r020_real_scorer_filter_stage.py tests/test_r020_post_score_unsupported_metric_legacy_characterization.py -q -o addopts= -p no:cacheprovider --basetemp (Join-Path $run 'pytest') --tb=short
```

此 acceptance 僅涵蓋 pure deferred API 與上述 focused route，不代表原生 Pandas／object `Decimal`／`pd.NA` 診斷、副作用或 threshold coercion/error timing 完全 parity，也不代表 provider cutover 或完整 V-REPLAY 已通過。R020 維持 `IN_PROGRESS`；`TMP-REC-04`／`TMP-NUM-01` 維持 `ACTIVE`；C2 未放行、R028 `BLOCKED`。

## 2026-09-25 post-score diagnostics observer 抽取（bounded ACCEPTED_SCOPE）

R015 對 frozen diagnostics observer slice 做獨立唯讀複核，未發現 P1/P2；root 亦獨立重跑相同六檔路由並回報 `43 passed`。此 bounded acceptance 僅限抽出 `StrategyConfigurator.screen_stocks` 的既有診斷副作用：observer 在診斷副本上依序執行價格／成交量 pass、保留 warning/counter 與例外時序，不回傳 eligibility；`screen_stocks` 仍對原始 frame 執行唯一的 `filter_completed_frame` 並決定結果。Frozen SHA-256：`decision_module/strategy_configurator.py` `1758FC07654E744A218D04EE193F627C9D1379D88D27EF00EBEA997EC53D3100`；`tests/test_r020_post_score_diagnostics_observer.py` `AD3A8D22C31B710C36946B9D24A13876250F0EAE2F8CB6451A1CC5FB0B856CE0`；完整 QA 與獨立 fresh-TEMP 收據見 [R020 post-score diagnostics observer QA](../../../06_qa/R020_POST_SCORE_DIAGNOSTICS_OBSERVER_20260925.md)。

此接受不證明 legacy Pandas native diagnostics 與 replay typed post-score evaluator 的完整數值／錯誤時序 parity，也不接線 provider 或宣告 same-mode output parity。R020 維持 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 維持 `ACTIVE`；C2 未放行，R028 維持 `BLOCKED`。

## 2026-09-25 scorer 後置 filter alias／量能 normalization helper（bounded ACCEPTED_SCOPE）

`StrategyConfigurator.generate_recommendations` 原有 alias／量能 threshold 映射已抽為
`normalize_recommendation_filter_aliases()`，原 scorer 後置呼叫位置保留。此限定接受只涵蓋
映射責任共用與既有行為：`min_return_pct` 先映射、明確 `price_change_min` 再覆寫；
`min_volume_ratio` 優先於 `volume_ratio_min`；直接量能 alias 保留 `-50 <= value <= 10`
inclusive conversion boundary；NumPy scalar native type、`None`／`pd.NA` 及 conversion exception
時序均以 focused characterization 覆蓋。沒有新增裸 float 計算、輸出規則或資料讀取。

R027 獨立複審對此 bounded slice 判定 `ACCEPTED_SCOPE`，無 P1/P2；正確 fresh TEMP 相鄰路由
為 `84 passed`，scoped mypy／py_compile 通過。該 route 使用 inventory 中單一
collection-status 測試搭配相鄰 scorer/filter 路由。複審前誤將整個 inventory 模組納入的
全域 guard 路由為 `89 passed／1 failed`，不作本切片功能失敗或接受依據；QA note 記錄此
校正和作者原先九檔 `59 passed` 收據。

凍結識別：`decision_module/strategy_configurator.py` SHA-256
`3C11ED4402C4A39C65AD93FB8EE958658D0C82CE63B3B17B26BA1515E14F9F8B`；
`tests/test_r020_strategy_filter_normalization.py` SHA-256
`FF71B2D0C1B267728860B0EE6D787706C9FF3C04385D85BECF64323F29540E8F`；QA 詳見
[R020 strategy filter normalization QA](../../../06_qa/R020_STRATEGY_FILTER_NORMALIZATION_20260925.md)。
此 helper acceptance 不接 provider／evaluator，不移除 scorer filters，也不驗 post-score same-mode
parity；R020 維持 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 維持 `ACTIVE`，C2 未放行，
R028 維持 `BLOCKED`。

## 2026-09-25 post-score legacy scalar response（bounded ACCEPTED_SCOPE; cutover open）

新增 pure typed response，以保留兩個已由原生 `StrategyConfigurator.screen_stocks` 直接固定的
scored-row 語意：object-dtype Python `Decimal` + Python-string price-min threshold 回傳
`LEGACY_ERROR`，含 exact `TypeError` type/message、rule 與原字串提示，不發出 threshold request；
object-dtype scalar `pd.NA` + Python-string threshold 回傳 `REJECTED` 與 exact warning/counter
diagnostic event。App numeric projector 必須明示來源 Series dtype；僅在 dtype 為 `object` 時分類
`pd.NA`，其他 dtype 不從此案例推廣。純 evaluator 不 raise、不寫 warning、不更新 counter；event
保留為可供 app adapter 套用的 immutable facts。

R015 fresh TEMP `PROFILE=test` 六檔相鄰路由 `60 passed in 1.67s`，receipt log SHA-256
`8D4DB9AC5B5293D2CD8C849960D168116D579FAF4F374E58385B46198E654111`，TEMP
`C:\Users\archi\AppData\Local\Temp\r020-postscore-sem-frozen2-8f385993342e435890db56103ba48326`；
`py_compile` 通過，`mypy --follow-imports=silent` 三檔／0，`quant_guard_linter.py` 通過。一般
scoped mypy 命令另回報 `app_module/recommendation_calibration_consumer.py:1177` 錯誤；這是並行
R026 工作樹錯誤，與本 R020 slice 無關，交 R026 owner 處理。詳細路由、獨立 oracle、限制及 frozen SHA 見 [R020 post-score
legacy semantic response QA](../../../06_qa/R020_POST_SCORE_LEGACY_SEMANTIC_RESPONSE_20260925.md)。

R027 獨立複審核對 frozen source/test SHA，fresh TEMP 六檔 `60 passed`，scoped mypy
`3 files／0 issues`，`py_compile`／quant guard 通過，未發現 P1/P2，建議 bounded
`ACCEPTED_SCOPE`。複審時 QA note SHA 為 `CAAB5BB2E230672BBC3852D08C56FFD0678E36DF7F2F493B1C416BEA45560666`、
report SHA 為 `629C6D4669E15882C9B4E1BCE0A1AB75296A29CAE819CCFD89471F67168450F2`；reviewer 未提供
log SHA；複審 TEMP 為 `C:\Users\archi\AppData\Local\Temp\r020_sem_review_c5604e04`。其證據僅記錄此
受控六檔 route，不擴大到其他 caller。隨後只勘誤 mypy 錯誤歸屬並登錄專屬測試至
`service-oracle-recommendation`。更新後的 inventory guard 為
`6 passed／1 failed`；唯一失敗的全庫 exact-registration scan 列出 109 個其他未登錄 Python
測試檔，本切片新測試不在 missing list。此處只維護本測試 entry，不代表全庫 inventory PASS。

此 bounded acceptance **不接線 provider**：app 尚未於舊呼叫點重拋 `LEGACY_ERROR`，也尚未
套用 diagnostic event 的 warning/counter。因此不能宣稱 provider side-effect/error timing、
same-mode v1 output 或 full V-REPLAY parity；保留 `StrategyConfigurator`、live provider 與
wire/codec 不變。R020 維持 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 維持 `ACTIVE`，C2 未放行。

## 2026-09-25 replay provider post-score cutover 初版收據（歷史狀態）

以下保留初版接線時的原始數字與邊界敘述；後續實作與獨立複審前 QA 已更新於本報告末尾。本節所載 `358 passed`／`27 passed` 與 RSI-only/custom scorer 描述是歷史收據，不是目前 code 的最終行為或 acceptance。

`RecommendationDataFrameProvider` 已完成受控 replay-only 接線：當呼叫帶有 typed
`as_of_date`、使用內建 `StrategyConfigurator` 且有 active filters 時，provider 會以移除
`filters` 的 call-local config 取得非空 scored row，再以同一 scorer request 建立
`ReplayScoredRowReadyV1`／`ReplayPostScoreFactsV1`，透過 staged evaluator 逐一投影
price、effective volume-change 與 RSI threshold。原始 filters 僅留在 adapter 供 alias
normalization、legacy diagnostic observer、threshold hint 與 native exception timing 使用；
interactive `StrategyConfigurator` 與 `RecommendationService` 路徑不改。post-score
`REJECTED`／`UNSUPPORTED`／`LEGACY_ERROR` 不會產生 v1 row；`ACCEPTED` 才進入既有 typed
scorer handoff。自訂／override scorer 不會被假裝成 built-in post-score evaluator；RSI-only
post-score filter 走 v1-only／無 canonical child，fast-filter 相容路徑維持原 typed child
邊界。`ReplayPostScoreFactsV1` 的 dataclass copy 會重新發行 opaque identity token，避免
staged response 被 `dataclasses.replace()` 的舊 facts 接受。

驗證：`tests -k r020` 為 `358 passed, 1 skipped`（pytest cache 權限 warning 僅環境噪音）；
R020 provider／post-score focused route 為 `27 passed`。這是 bounded replay cutover evidence，
不等同所有資料源、interactive output 或完整 V-REPLAY parity 已完成；R020 仍維持
`IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 維持 `ACTIVE`，C2 未放行，R028 維持 `BLOCKED`。

## 2026-09-25 concrete replay post-score cutover（修補前實作者收據；由下節更新）

在 typed `as_of_date` replay 呼叫中，只有精確 built-in `StrategyConfigurator` 與 active filters 會採新的責任分工：provider 複製 config 並移除 `filters`，取得非空 scored row 後，再依同次 `NeedCandidateScoring` 以 `ReplayScoredRowReadyV1`／`ReplayPostScoreFactsV1` 逐項呼叫 staged evaluator；原始 filters 留在 call-local adapter，維持 alias normalization、legacy diagnostic observer、lazy threshold conversion 與原生例外順序。通過的 typed outcome 才能投影 v1 row 與 canonical child。無 filters 的既有 built-in route 維持舊 handoff。所有 injected、subclass、override scorer 的非空輸出一律保留 v1 row、`scoring_outcomes=None`，不建立 canonical child；沒有非空列時仍可保留合法 empty canonical execution。Interactive `StrategyConfigurator`／`RecommendationService` 路徑與 v1 wire／codec 未改。

Side-effect 差異以 synthetic scored-row 對照固定於 `tests/test_r020_real_scorer_filter_stage.py`：float16／float32 且 `price_change_max=1e100` 時，native 舊路徑的兩次 `filter_completed_frame` cast 與 replay 的 diagnostic pass 加 paired numeric projection 各產生兩個順序相同的 `RuntimeWarning: overflow encountered in cast`，兩者都保留一列；`np.errstate(over="raise")` 時兩者都在第一個 diagnostic filter comparison 遇到 `FloatingPointError`，replay 的既有 provider exception boundary 將它記為 `SKIPPED_SCORER_EXCEPTION` 並不輸出 row，paired projection 未執行。另固定 price reject 後的 invalid RSI 字串：price warning/counter 先發生，空 int64 RSI 比較仍以同一 TypeError 結束；provider boundary 以 scorer exception terminal 吸收，沒有 v1 row。這些受控例涵蓋 dtype／例外路徑，不能外推至所有 NumPy runtime、Pandas extension/object scalar 或所有 legacy warning quota 狀態。

Fresh TEMP `C:\Users\archi\AppData\Local\Temp\r020_final_postscore_627326433c164890a3d54da420ab6631`、`PROFILE=test`、獨立 `DATA_ROOT`／`OUTPUT_ROOT`／pytest `basetemp`，以 33 個 `tests/test_r020_*.py` 加三個 staged evaluator／prefilter／numeric projector 路由重跑：`432 passed, 1 skipped in 17.61s`。唯一 skip 是 `tests/test_r020_numeric_runtime_differential.py:685`：此執行環境的 `longdouble` mantissa 未寬於 float64，較寬 runtime 分支未覆蓋。Scoped mypy（provider、evaluate、真實 scorer filter tests）為 3 files／0 issues；三檔 `py_compile` 通過；`scripts/quant_guard_linter.py` 的 financial float 與 look-ahead checks 通過；`git diff --check` 通過。該測試檔原已登錄 `service-oracle-recommendation`，本次未修改 inventory。

可重跑命令：

```powershell
$run = 'C:\Users\archi\AppData\Local\Temp\r020_final_postscore_627326433c164890a3d54da420ab6631'
$env:TEMP = $run
$env:TMP = $run
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
$env:PYTHONDONTWRITEBYTECODE = '1'
$r020Files = @(rg --files tests | Where-Object { $_ -like 'tests\test_r020_*.py' })
.\.venv\Scripts\python.exe -B -m pytest @r020Files tests/test_recommendation_evaluator_replay_staged.py tests/test_recommendation_replay_prefilter.py tests/test_recommendation_replay_numeric_projection.py -q -rs -o addopts= -p no:cacheprovider --basetemp (Join-Path $run 'pytest') --tb=short
```

目前檔案 SHA-256：`app_module/recommendation_dataframe_provider.py` `79B96627E40FAD39B6430B51E36F1D7A231E339E5C9F15A52233AA85012BA08`；`decision_module/recommendation/evaluate.py` `EAE0E2263DBDFC8A1C0BE4FDD0100C10186D5551FD0CB147E1DA56D514160EFD`；`tests/test_r020_real_scorer_filter_stage.py`（本輪修改）`F9A3FA8094B4A8BA7B1694D0FCBD34858F4B6CB1DA79486605A49BE1E92116FC`；`tests/test_r020_post_score_threshold_metric_pairing.py` `D12AF21C0733283F320310B64ACF716B584B48585C7F64F378C88BE9977A594F`；`tests/test_r020_replay_post_score_evaluator.py` `053E2B2CB71AFDAB903D0A2B7B924E4190EB44DD12EC86EAC81C4A78FD29C4A8`；inventory `qa/full_app_healthcheck/test_inventory.py` `73C1389DCFA3C5EC453C8395A0AE293007D53F85314CF9461A04EBDF7C5F0077`（現有 membership 驗證，未修改）。QA 明細與重跑命令見 [R020 post-score deferred threshold QA](../../../06_qa/R020_POST_SCORE_DEFERRED_THRESHOLD_STAGES_20260925.md)。

此處收據記錄 complex-Pandas 修補前的實作者路由，不宣告 R020 bounded acceptance、full V-REPLAY parity 或 TMP 退休；最新同模式收據見下節。R020 維持 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 維持 `ACTIVE`，C2 未放行，R028 `BLOCKED`。

## 2026-09-25 Pandas complex post-score same-mode 修補（平台 P2 修補後 bounded acceptance）

### 修補與 parity 邊界

修補前的 NumPy 1.26.4 differential repro：`np.complex64(2+nanj) >= 1.0` 經原生 Pandas Series 篩選拒絕，但舊 typed comparator 接受，實際 provider 多輸出一列。修補前 R015 單項失敗 log SHA-256 為 `E9A04BFD2DE87608D7530C06E887D5755A9B685C5F493FE3796A5AE805462AD6`；該紅燈是歷史證據，不算通過。舊 projector unit test 仍期待 post-score pair 使用 `NUMPY_COMPLEX`，亦已按 post-score Pandas Series 語意改為 `PANDAS_COMPLEX_SERIES`，保留 NumPy scalar origin、dtype、threshold/domain 與 imaginary-zero 驗證。

`project_legacy_post_score_comparison_pair` 現把 NumPy complex operands 放入 `PANDAS_COMPLEX_SERIES` comparison domain，保存 NumPy provenance；含 NaN component 依原生 Pandas Series unordered 結果拒絕。runtime capability guard 包含整個 complex domain，即使 real component 已決定方向且 native 不發 invalid warning（例如 `2+nanj`）。僅 `sys.platform == "win32"`、Python 3.11.9／Pandas 2.3.3／NumPy 1.26.4 或 2.3.5，且 Pandas `_evaluate_standard` bytecode 與 warning line/module/path 符合驗證，才可建立 row。非 Win32、未知平台、其他 runtime、bytecode shape 或 warning site 無法確認時，`ReplayNativeEffectProjectionUnavailableError` 會在 canonical row/child 前 fail closed。這是已測 Win32 profile 的 bounded evidence，不宣稱所有 Windows 版本或 build 均已驗，也不是對 `requirements-runtime.txt` 全部 Pandas/NumPy 版本的 parity 承諾。

Evaluator 只輸出 rule-bound immutable NumPy invalid effect；app adapter 按目前 `np.errstate` 投影 effect，無第二 eligibility comparison。`warn` 路徑使用原生 Pandas module globals、`__warningregistry__`、category/message/filename/line，並尊重 module warning filter 與 default 重複抑制。`raise` 保留 `FloatingPointError` type/message 並位於 scorer 外層相同 error boundary；`ignore`／`print`／`log`／`call` 有 same-provider 對照。每個 pending rule 重新清空並取得 warning capability；`test_unsupported_rule_cannot_reuse_previous_complex_warning_capability` 以 synthetic future effect 負控證明 unsupported rule 不會誤用前一 rule 的 site。當 profile/location 不可驗證時，整次 replay 呼叫 fail closed，而不是回傳 generic skipped scorer outcome。

舊路徑 oracle 為同一 concrete provider 的 `provider(history, config, top_n)`；新路徑為同 instance 的 `provider.run_with_as_of_handoff(...)`，各自使用相同 warning context 與 native config。直接呼叫 `StrategyConfigurator` 僅作 scorer／原生例外機制診斷，不用於跨呼叫比較 warning count。已固定 complex min/max、real component 1 與 2、NaN component、native warning location／filter／registry 及 errstate channel。float16／float32 overflow case 仍逐 runtime 比較原生 wrapper 與新 adapter，不將 NumPy 1、2 的 warning 數視為應跨版相同。測試用 autouse `monkeypatch` 隔離 `StrategyConfigurator` 的 process-local diagnostic counters，避免影響後續 legacy characterization；沒有改動那些 characterization 的預期輸出。

### Fresh TEMP 完整路由

兩個 runtime 各用 fresh short TEMP；`TEMP`、`TMP`、`PROFILE=test`、`DATA_ROOT`、`OUTPUT_ROOT`、pytest `basetemp` 皆指向該 runtime 獨立根目錄。路由包含 33 個 `tests/test_r020_*.py` 加 staged evaluator、replay prefilter、numeric projection 三個相鄰 test files：

| Runtime | TEMP root | 結果 |
|---|---|---|
| Python 3.11.9／NumPy 1.26.4／Pandas 2.3.3 | `C:\r20q\n1_platform_final_327f5450` | 455 passed, 1 skipped, 11 warnings in 18.61s；log SHA-256 `697E1D71160AA9ACF4DC19735C3760A2C136F360676FA83CB88996D86B9B88B5` |
| Python 3.11.9／NumPy 2.3.5／Pandas 2.3.3 | `C:\r20q\n2_platform_final_5a9fb6e3` | 455 passed, 1 skipped, 8 warnings in 17.69s；log SHA-256 `01CCE08C8E92B819BF04D84A0EA29080D5E2CDEA28F61BFC5599BA9C9399A091` |

R015 首次獨立複審對前一版各 449 passed／1 skipped 收據判為 `CHANGES_REQUIRED`：缺少非 Win32 fail-closed gate，且 NP1 runner 會在 NP2 改寫 `$env:TEMP` 後從該變數錯誤組成路徑。舊 owner log SHA `31FA13F71AC4EB4054E8B819ECDD93DF04B5A5B48269E7AAA68E91652E11AF72`／`660C8972301EDCB9F82904CF9EB8FC6DC3DC07204F7A259F470BD7D284798279`，以及 reviewer log SHA `0624082127BA3014F1BF24A6A24B42BC7311C53B5AE88E43D6380041B8463E0A`／`E984E71EC42F53DAB4A03B6D145FFDF1C8D074A2AF0C945D57909B5F622197AB` 均為平台修補前歷史收據，不作此版 gate。新增負測證明 Linux、Darwin 與未知 `sys.platform` 的 `2+nanj` concrete replay 在產生 row／child 前 fail closed；另證一般 `np.float32` replay 在 Linux 仍可產生 row／child。

兩個 warning summary 數不同是 runtime-specific 測試 oracle／NumPy 行為差異；每個 provider cutover assertion 都比較同一 runtime 的原生 provider wrapper 與 replay。兩邊唯一 skip 均是 `tests/test_r020_numeric_runtime_differential.py:685`：`longdouble` mantissa 未寬於 float64，較寬分支未覆蓋。沒有聲稱跨 runtime 行為一致。

可重跑命令：

```powershell
# NumPy 2.3.5（先建立全新短 TEMP）
$base = 'C:\r20q'
$null = New-Item -ItemType Directory -Force -Path $base
$run = Join-Path $base ('n2_' + [guid]::NewGuid().ToString('N').Substring(0,8))
$null = New-Item -ItemType Directory -Path $run
$env:TEMP = $run
$env:TMP = $run
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
$env:PYTHONDONTWRITEBYTECODE = '1'
$r020Files = @(rg --files tests | Where-Object { $_ -like 'tests\test_r020_*.py' })
.\.venv\Scripts\python.exe -B -m pytest @r020Files `
  tests/test_recommendation_evaluator_replay_staged.py `
  tests/test_recommendation_replay_prefilter.py `
  tests/test_recommendation_replay_numeric_projection.py `
  -q -rs -o addopts= -p no:cacheprovider `
  --basetemp (Join-Path $run 'pytest') --tb=short

# NumPy 1.26.4（以穩定的 LocalAppData 路徑定位預建隔離 venv，不依賴已改寫的 $env:TEMP）
$py = Join-Path $env:LOCALAPPDATA 'Temp\r020_num01_win_np1264_ad276b8ab2e643b993dc2e4493cf730c\venv\Scripts\python.exe'
$base = 'C:\r20q'
$null = New-Item -ItemType Directory -Force -Path $base
$run = Join-Path $base ('n1_' + [guid]::NewGuid().ToString('N').Substring(0,8))
$null = New-Item -ItemType Directory -Path $run
$env:TEMP = $run
$env:TMP = $run
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
$env:PYTHONDONTWRITEBYTECODE = '1'
$r020Files = @(rg --files tests | Where-Object { $_ -like 'tests\test_r020_*.py' })
& $py -B -m pytest @r020Files `
  tests/test_recommendation_evaluator_replay_staged.py `
  tests/test_recommendation_replay_prefilter.py `
  tests/test_recommendation_replay_numeric_projection.py `
  -q -rs -o addopts= -p no:cacheprovider `
  --basetemp (Join-Path $run 'pytest') --tb=short
```

Scoped mypy（四個 production 檔與 real scorer filter test，以 `--follow-imports=silent` 隔離並行 R026 模組）為 `5 files／0 issues`；四個 production 與四個測試檔 `py_compile` 通過；`scripts/quant_guard_linter.py` financial-float／look-ahead 檢查通過；`git diff --check` 通過。此平台 P2 只新增 fail-closed 測試，並將既有 `np.errstate` 測試 action 收窄為 `Literal` 型別；沒有改一般 scalar／threshold 行為。

凍結 SHA-256：

| 檔案 | SHA-256 |
|---|---|
| `decision_module/recommendation/replay_prefilter.py` | `B7B7AF5FA0359523FCADD4547A0C23D59A981F961AD8304ABD603C85BCB795FF` |
| `app_module/recommendation/replay_numeric_projection.py` | `A32AB4F23E0C16B3C768DB801BEF7B64793E7D81D25ADDA48FB74A88A9D49381` |
| `decision_module/recommendation/evaluate.py` | `588569069C44C2B4AFE3608BB44EE98FDA2348416575C9A6E6CA441C6DDE9AA9` |
| `app_module/recommendation_dataframe_provider.py` | `0CF7C8B60FCD1BB6B51D9398213B93A1A1EABD5E7A1569AF1F053485F66C95B3` |
| `tests/test_r020_post_score_threshold_metric_pairing.py` | `DFBBE3347AD08CB677901594DC656AEFD0FB9B7A487C8E5A6C85BE3DCBEB78CB` |
| `tests/test_r020_replay_post_score_evaluator.py` | `DD19BAF6DC9DD2C3017C164BCBCC0F2C44BADCB453B18C97EF89362C5281CD78` |
| `tests/test_r020_real_scorer_filter_stage.py` | `23E5DF76E728EE889A59FB31E18808896A4793C44F008A9FE33479D8EDEEFA00` |
| `tests/test_r020_post_score_native_numeric_projection.py` | `62B1659145120E5DFB7C174FB78AD4167F22BDA8529F3CAF5D6843015237F0AE` |

R015 獨立複審對 NP1／NP2 各完成定向 11P，5-file mypy 為 0 issues，compile／quant guard／diff checks 通過；root 對此平台 P2 修補切片給予 bounded `ACCEPTED_SCOPE`。接受範圍限上述已測 Win32 profile與 complex capability fail-closed 行為，不代表其他 Python／Pandas／NumPy profile、其他 Windows OS/build、其他 complex scalar、Pandas extension/object scalar 或 full V-REPLAY parity 通過。R020 維持 `IN_PROGRESS`；`TMP-REC-04`／`TMP-NUM-01` 維持 `ACTIVE`；C2 未放行，R028 `BLOCKED`。

## 2026-09-25 擴大 V-REPLAY 合成 parity route（bounded ACCEPTED_SCOPE）

此 route 在已接受的平台切片之外，把相關合成 replay、timeline、portfolio 與交易成本測試放入同一個短 TEMP 路由；它仍不是完整 V-REPLAY/C2 gate。凍結輸入 manifest 位於 `C:\r20q\x11_4750a051\manifest.json`，SHA-256 `3D27664FDB98E2607C57E6F85A2CD0DF4F17B8BFD5BC9D9E5768CC15390A63F2`，綁定 HEAD `bec423eef1d9e9d4a32410dac96cd233304489aa`、40 個測試檔（33 個 `tests/test_r020_*.py` 加 7 個相鄰檔）及 6 個 provider/replay/evaluator/portfolio 核心來源的逐檔 SHA-256。兩次執行前後均比對同一 manifest，沒有測試、來源或 HEAD 漂移。

| Runtime | fresh TEMP／PROFILE=test | 結果 | pytest log SHA-256 |
|---|---|---|---|
| Python 3.11.9／NumPy 1.26.4／Pandas 2.3.3（實作者） | `C:\r20q\x11_n1_effe0fd3` | 512 passed, 1 skipped, 35 warnings；pytest 19.66s | `EDC9A16A146E9501092847E7970216A2FEDEF3BFBECF21194AFFD87CF5E5F12A` |
| Python 3.11.9／NumPy 2.3.5／Pandas 2.3.3（實作者） | `C:\r20q\x11_n2_edacd620` | 512 passed, 1 skipped, 32 warnings；pytest 18.91s | `25E3F631F8323EAF75686B971FD07C57265FE8C28ACDA77A3D3075B7BE061B6B` |

每個 runtime 的 `TEMP`、`TMP`、`PROFILE=test`、`DATA_ROOT`、`OUTPUT_ROOT` 與 pytest `--basetemp` 都指向各自新建的短 TEMP 根。每邊唯一 skip 是 `tests/test_r020_numeric_runtime_differential.py:685`：該 runtime 的 `longdouble` mantissa 沒有寬於 float64，較寬分支未覆蓋。warnings 數量因 NumPy/Pandas runtime 與各測試原生 oracle 而異，不把跨 profile 的 summary 數量當作 parity 要求。

### 覆蓋證據與邊界

- R005 原生 provider 固定 v1 row 欄位、score fallback、穩定排序/tie、top-N、過濾與 per-stock 例外、factor survivors：`tests/test_recommendation_replay_characterization.py:456-604,613+`。
- Provider 與 snapshot 的雙層切片、mixed scorer terminal、ordered v1 rows、diagnostics、factor scores、typed child/空 child/child fail-closed：`tests/test_r020_replay_pipeline_composition.py:252-387`、`tests/test_r020_replay_mixed_terminal_composition.py:210-375`、`tests/test_r020_typed_provider_child_handoff.py:180-421`。內建 scorer 正例建立 canonical child；自訂或 override scorer 保留 v1 rows，但不把 rows 偽裝成 canonical child。
- Legacy-close portfolio 固定推薦列、diagnostics、factor manifest、空日/例外日與帳務：`tests/test_r020_concrete_portfolio_parity.py:91-179,481-728`。Next-open caller 固定 PIT rows、factor manifest、開盤成交日、cash/equity/summary 與 parent：同檔 `:731-1116`。兩種 execution contract 各自對照獨立手算 oracle，沒有要求彼此帳務相等；Bank Taiwan cost route 另由 manifest 中的 `tests/test_recommendation_portfolio_banktaiwan_cost.py` 覆蓋。
- 完整清單及每一測試/來源的精確雜湊只由上述 manifest 定義；兩個逐次 pytest log 位於各自 TEMP 根，SHA 見表格。重跑時須使用同一 manifest，並在執行前後拒絕任何 path/hash/HEAD 漂移。
- R015 獨立複審確認 manifest、HEAD 與 46 個 test/source SHA 完全相符，沒有漂移；複審 fresh TEMP receipts：NP1 `C:\t\x11np1r\pytest.log` SHA-256 `C90DB3934A494EE669E7A8621E6F3FAB48B8501140AED086D2118F44434D9EDE`（512 passed、1 skipped、35 warnings），NP2 `C:\t\x11np2r\pytest.log` SHA-256 `4B5022D4ED7AE00230F8F749EC78C9F460EBD93F85C6DC3566AB2BDCCF991BE6`（512 passed、1 skipped、32 warnings）。R015 另以 fresh TEMP 跑 6-file accounting/PIT route，56 passed、4 warnings，log `C:\t\x11r1r\pytest.log` SHA-256 `5D4F88775EB4CF88E75ACE19D6E43EFC7A84CE15AEE97D6D8A15246DD1A19E6A`。Root 對此 expanded synthetic route 給予 bounded `ACCEPTED_SCOPE`，無 P1/P2；三份複審收據分開記錄，不與實作者 logs 疊加計數。

可重跑的 pytest invocation 由 manifest 的 40 個 `tests[].path` 作位置參數；例如從 repo root 依序設定 profile 環境後執行：

```powershell
$manifestPath = 'C:\r20q\x11_4750a051\manifest.json'
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$testFiles = @($manifest.tests | ForEach-Object { $_.path })
$runtimes = @(
  [PSCustomObject]@{ name = 'np1'; python = (Join-Path $env:LOCALAPPDATA 'Temp\r020_num01_win_np1264_ad276b8ab2e643b993dc2e4493cf730c\venv\Scripts\python.exe') },
  [PSCustomObject]@{ name = 'np2'; python = 'C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe' }
)
$frozenEntries = @($manifest.tests) + @($manifest.sources)
foreach ($runtimeEntry in $runtimes) {
  if ((git rev-parse HEAD).Trim() -ne $manifest.head) { throw 'HEAD drift' }
  foreach ($entry in $frozenEntries) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $entry.path).Hash -ne $entry.sha256) { throw "Manifest drift: $($entry.path)" }
  }
  if (-not (Test-Path -LiteralPath $runtimeEntry.python)) { throw "Missing interpreter: $($runtimeEntry.name)" }
  $run = Join-Path 'C:\r20q' ('x11_' + $runtimeEntry.name + '_' + [guid]::NewGuid().ToString('N').Substring(0,8))
  $null = New-Item -ItemType Directory -Path $run
  $null = New-Item -ItemType Directory -Path (Join-Path $run 'data')
  $null = New-Item -ItemType Directory -Path (Join-Path $run 'output')
  $env:TEMP = $run
  $env:TMP = $run
  $env:PROFILE = 'test'
  $env:DATA_ROOT = Join-Path $run 'data'
  $env:OUTPUT_ROOT = Join-Path $run 'output'
  $env:PYTHONDONTWRITEBYTECODE = '1'
  $pytestArgs = @($testFiles) + @('-q', '-o', 'addopts=', '--basetemp', (Join-Path $run 'pt'))
  & $runtimeEntry.python -m pytest @pytestArgs 2>&1 | Tee-Object -FilePath (Join-Path $run 'pytest.log')
  if ($LASTEXITCODE -ne 0) { throw "$($runtimeEntry.name) pytest failed with $LASTEXITCODE" }
  foreach ($entry in $frozenEntries) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $entry.path).Hash -ne $entry.sha256) { throw "Post-run manifest drift: $($entry.path)" }
  }
  if ((git rev-parse HEAD).Trim() -ne $manifest.head) { throw 'Post-run HEAD drift' }
}
```

此 expanded route 的 R015 獨立複審與 root bounded acceptance 已完成，但它不包含 R026 source-backed historical replay，也未把 scheduled／personalization／saved-result consumers 與 affected UI 合併為 C2 matrix。平台證據仍限已驗 Win32 Python 3.11.9、Pandas 2.3.3、NumPy 1.26.4／2.3.5；longdouble 寬 mantissa、其他 OS/runtime/object-dtype profile 仍未驗。故 R020 維持 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 維持 `ACTIVE`，C2 未放行，R028 `BLOCKED`。

## 2026-09-25 typed-only replay child handoff parity（實作者 bounded 收據；等待 R023 獨立複審）

本 slice 延續 concrete replay provider 的 typed scorer cutover，讓一份排序後 `_ReplayScoredCandidateV1` tuple 作為 typed child 與 v1 compatibility rows 的共同來源。`ReplayProviderCallResultV1.candidates` 是 handoff 儲存欄位；`.rows`、`.scoring_outcomes` 保留舊讀取形狀作 properties，每次從 candidates 投影，避免 row/outcome 平行清單錯接。`RecommendationReplayService._build_canonical_replay_execution_from_handoff` 只讀 candidate 的 typed `ReplayCandidateScoringOutcomeV1.item`／assessment 建立 `DecisionBatch`，未由外層 row dict 反造 canonical state。

在建立 child 前，service 會將已 deep-copy 到 `RecommendationSnapshotDTO.recommendations` 的實際 v1 rows 與同次 child candidate 的 `to_v1_row()` 結果逐列比對；欄位、值、型別或順序不符時維持 compatibility rows、拒絕 canonical child。原 v1 row scoring 欄位不供 child builder 使用。對 primitive row scalar 要求 exact type/value，float 以 binary64 bytes 核對；opaque compatibility payload 只接受同一物件，且不符合 typed reason contract 的候選本身不會建立 child。這是 sidecar parity guard，不改 v1 rows。自訂／legacy／override provider 仍 v1-only/no-child；既有 zero-row empty canonical decision 保留。

先加三個故障注入測試，改動 `project_v1_rows()` 所產生列的 score、reason 或順序。修補前三個測試均紅：snapshot 雖保留污染後 rows，仍錯誤附加 child；修補後 rows 原樣保留、child 均為 `None`。現有 candidate 欄位/outcome corruption、built-in scorer typed child 正例、v1 row projection alias isolation、single scorer pass、negative/zero double slicing、custom provider boundary 與 portfolio same-mode golden 一併納入 route。

同一 frozen manifest `C:\t\r020_typed_child_union_abd24a427bbb4204bea398cca1ec4d16\manifest.json` SHA-256 `C57627D0CF545920C10A5E43C2DB20861A17FA1C814C275D867EDCE5C1BC79F7`，綁定 HEAD `bec423eef1d9e9d4a32410dac96cd233304489aa`、40 個 R020/R005/replay/timeline/portfolio test paths 與 6 個 production source paths（46 個 path/SHA entries）。NP1／NP2 都在 fresh short TEMP、`PROFILE=test`、獨立 `DATA_ROOT`／`OUTPUT_ROOT`／pytest basetemp 執行；執行前後所有 entries 與 HEAD 一致：

| Runtime | 結果 | pytest log SHA-256 |
|---|---|---|
| Python 3.11.9／NumPy 1.26.4／Pandas 2.3.3，TEMP `C:\t\r020_typed_union_np1_af24dca3a63e4fb6bf015dfd8893e914` | 517 passed, 1 skipped, 35 warnings；pytest 21.99s | `DDD9A3D0563DF8200BC38650D353DEED73D705483D972F2488D3386595E3C0F3` |
| Python 3.11.9／NumPy 2.3.5／Pandas 2.3.3，TEMP `C:\Users\archi\AppData\Local\Temp\r020_typed_union_np2_b36104ece9974570a68a81c5b60638d3` | 517 passed, 1 skipped, 32 warnings；pytest 22.14s | `56BFC29C0BD8B0E3585FB5BDE023D83EBA8981A95197AD96C77E48152E129A06` |

唯一 skip 為 longdouble mantissa 未寬於 float64。兩 profile warning summary 由各 runtime native-oracle／portfolio warnings 決定，不要求 warning 計數相同。另 fresh TEMP 跑 R026 source-backed historical replay 與 snapshot provider adjacent route 為 16 passed，log SHA-256 `898716FFC8292A8792590AC5CE1591C74038286C38416BD659A8B184C52895E8`；這是鄰接相容檢查，不替代 R026 source/availability gates。核心五檔 route 65 passed／4 warnings；scoped mypy 2 source files／0 issues，py_compile、quant financial-float/look-ahead guard 與 scoped `git diff --check` 通過。

凍結 SHA-256：provider `E30BCF375C1256877F79E15FC87B4DECFDA83F9DB0E36608BD11A79BE44412EB`；replay service `4B2897DB1CED80302AA0F1B706193C5FBE3E254CABEDFCD348008450A9A79903`；`tests/test_r020_typed_provider_child_handoff.py` `6672592231ABE0294CDA3CAA7AEC282EB5FA4F0D36A70F4F02C1D07BA8EE77A5`；`tests/test_r020_real_scorer_filter_stage.py` `92F4FEEA22EFD43CD6AB9922200F610A9CE4450C1BF1499F1C0E724E7943F6D7`。完整路由與重跑方式見 [typed-handoff QA note](../../../06_qa/R020_POST_SCORE_DEFERRED_THRESHOLD_STAGES_20260925.md)，此次追加後該 note SHA-256 為 `7A6C97AFC8BFB2072F0C150712AD09E205DFA952AF45A926D6AFB08967DCF50C`。此 frozen typed-handoff slice 曾待獨立複核；其後由 2026-09-25 root finite closeout 裁定更新，見下節。

## 2026-09-25 root finite closeout 裁定

Root 複核 R005 policy vectors、V-REPLAY bounded route、40-test typed handoff 與五個 distinct process-crash recovery states，裁定 **沒有剩餘的 R020-specific recovery/R005 vector gap**。Current C2 union 已接受：141 unique tests／88 sources，1,860 passed／5 skipped／34 warnings、exit 0；229 frozen inputs 的 pre/post SHA 完全一致。C2 狀態為 `ACCEPTED_WITH_NAMED_QA_BASELINE`；Update validator 的 WinError 32 TEMP SQLite teardown 是具名既有 QA baseline，不改寫成全綠。詳見 [C2 current union receipt](../../../06_qa/C2_CURRENT_UNION_PYTEST_BASELINE_20260925.md)、[C2 mandatory gates receipt](../../../06_qa/C2_MANDATORY_UI_STATIC_GATES_20260925.md) 與 [hard-exit recovery QA](../../../06_qa/R020_PROCESS_CRASH_RECOVERY_HARD_EXIT_QA_20260925.md)。

因此退休帳中的 **`TMP-REC-04` bounded replay/recovery scope 已 CLOSED**；這不宣稱所有 runtime、平台與任意 caller 的無界 parity。`TMP-NUM-01` 仍為獨立 `BLOCKED_WITH_OWNER` numeric gate，且不反向阻塞 R020 bounded closeout。既有歷史快照中「C2 未放行／`TMP-REC-04` ACTIVE／full R005 vectors 待驗」的文字只記錄當時狀態，由本節及 current retirement ledger supersede。跨 store 共同原子交易、補償 rollback、自動重建原 execution 不是已承諾能力，不列為本次 closeout 前置。
