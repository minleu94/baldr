> **歷史封存警語（2026-10-10）：**本文保留當時的審查派送內容；其中 SHA（如有）、scope、角色、指令與狀態僅代表原快照，不得據此重派、重跑或視為目前任務／授權。現況請以 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md) 與 [REFACTOR_MODEL_ASSIGNMENTS](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_MODEL_ASSIGNMENTS.md) 為準；後續 Wave 1 狀態見 [WAVE1_R007_TZNAME_CHECKPOINT](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE1_R007_TZNAME_CHECKPOINT.md)。

# GEMINI REVIEW PACKET — R002

## ROLE

你是 R002 的獨立 cross-model reviewer。這是唯讀 review；不要修改 production、tests 或任何 unrelated code。請核對 Luna Max 建立的推薦語意／數值 characterization 是否忠實、精確且足以保護 R011/R018/R019，並特別審查 SOL gate 授權的三個既有 test-only repairs 是否正確，沒有掩蓋行為漂移。

## REVIEW TARGET

R002 — 推薦語意與數值 characterization，Wave 1。Implementer：LUNA_MAX；reviewer：GEMINI。R001 已 PASS；R011/R018/R019 尚未開始。

## ORIGINAL R002 SPECIFICATION

### Task context and purpose

`RecommendationService.run_recommendation()` 同時做資料準備、篩選、計分、ranking、negative evidence 與 ML annotation。既有測試尚未形成獨立於未來 helper 的完整重構 oracle。R011/R018/R019 會改核心路徑，必須先凍結 filter 順序、rounding、null、order 與 degradation。

### Allowed scope

新增專用 characterization tests/fixtures；重用公開入口與小型 expected values；可補 test support，但不能抽 production helper。不得修改推薦、修 product bug、改數值型別、把新結果覆寫成 golden 或使用正式資料。

### Current behavior to preserve

normal fixed、quantile、empty、missing score、degraded source、fundamental unavailable、PIT industry 拒絕、volume/liquidity filter、partial stock exception、stable sort/tie-break、Decimal quantum 與現有 legacy float 輸出。

### Implementation objective and compatibility

- 建立固定輸入到 recommendations、screening matrix、why-not、liquidity、warnings、context identity 的可讀 oracle。
- `result_id` 等可變值必須結構化處理，不能以寬鬆 snapshot 掩蓋差異。
- INV-05、INV-06、INV-09、INV-13。
- Rule selection 與 ML annotation 分開 assert；缺模型時降級不改，不載入正式模型。
- 不寫 repository；若 roundtrip 只用 tmp fixture。
- 跑 task-loop-03、run-support、negative-evidence、fundamental、ranking tests；加入 order/rounding/missing 改變時會失敗的 assertions。
- 每個高風險語意至少一正一反例；expected 不呼叫待抽出的新 helper。
- 報告列 cases、exact/tolerance 欄、既有 gap、commands/results。

## RELEVANT ARCHITECTURE INVARIANTS

- **INV-05**：訊號、特徵、母體、標準化與 benchmark 只使用 decision-time 可得資料；unknown availability 不當已知。
- **INV-06**：新核心計算使用 Decimal／具單位整數；重構不得偷改既有 precision、rounding、tie-break 或 ML matrix ABI。
- **INV-09**：completed/failed/cancelled、quality、ML availability、persistence outcome 分離；零候選可為 completed。
- **INV-13**：歷史顯示只讀原結果；歷史重算建立新 identity；mode policy 差異不得被共用 engine 偷改。

## IMPLEMENTATION REPORT

完整報告：`REFACTOR_REPORTS/R002_IMPLEMENTATION_REPORT.md`
SHA-256：`ECF9B08E502A7154454B442698069D553CE254E42CEA3D9ABDCC613D428C6250`

新 oracle 有 8 個 tests，涵蓋：

1. fixed mode 的候選處理順序、同分穩定性、top-N、recommendation DTO、screening matrix 與 why-not；
2. quantile 的 `50.0049/50.0050/50.0051`、bp half-up、percentile、threshold、stable order/code tie-break；
3. legacy `numpy.float64(91.5)` 與 Decimal `70.0100` quantum；
4. `None`、Decimal NaN/Infinity 為 missing，不當零分；
5. empty input 與零 eligible universe；
6. 同一執行內 pass、liquidity reject、single-stock exception、insufficient history 的不同 status/quality/reasons；
7. PIT industry verified 與 unavailable fail-closed；
8. temp SQLite fundamental available/future/missing/over-threshold 與 missing DB 不建立檔案；
9. 無 ML consumer 時 rule selection 保持、calibration fields 為 unavailable。

所有數值 assertions 為 exact；沒有 tolerance。`decision_at` 只驗證為 UTC-aware ISO，固定 fingerprints、universe IDs/hash 與 named matrix fields 分開 exact assert。

### SOL gate repair

新增 oracle 前 required bundle 有 45 passed、3 failed。SOL 不接受 Wave gate 留紅燈，授權唯一 test-only repair：

- `tests/test_task_loop_03_contract.py` 兩個 historical equality cases：內容比較排除每次 invocation 不同的 `result_id` 與 `decision_at`；兩邊 `decision_at` 仍各自解析並驗證 UTC offset。原本的 result ID 不相等 assertion 保留。
- 同檔 saved-result identity case：`SimpleNamespace` 補 `result_status_label`、`research_actions_toggle`、`research_actions_widget` mocks，並 assert `result_status_label.setText` 被呼叫；production empty-result branch 未改。

修復後完整 V-REC 為 64 passed、0 failed。Reviewer 必須判斷這些修復是否精確對齊原測試意圖，是否意外弱化 future-append 或 UI identity oracle。

## CHANGED-FILE / DIFF SCOPE

- `tests/test_recommendation_refactor_characterization.py` — 新增，SHA-256 `E438EE6B742D73C1676FEBAF85314F1B7048A1293D7C7D9605CC57EDFA8B37E5`。
- `tests/test_task_loop_03_contract.py` — test-only repair，SHA-256 `63F3630C1FFE869821E5F445D42988EE38C696669D7C08FBBEA1ADEED084F4E0`。
- `REFACTOR_REPORTS/R002_IMPLEMENTATION_REPORT.md` — 更新後 report，hash 如上。
- Production code 零修改；R004/R007 與既有 dirty paths 不屬於 R002 review。

## TESTS ALREADY EXECUTED

SOL 重跑：

```text
.\.venv\Scripts\python.exe -m pytest tests/test_task_loop_03_contract.py tests/test_recommendation_run_support.py tests/test_recommendation_v1_7_negative_evidence.py tests/test_recommendation_fundamental_filters.py tests/test_recommendation_ranking_service.py tests/test_recommendation_market_data_provider.py tests/test_pit_industry_callers.py tests/test_recommendation_refactor_characterization.py -q -o addopts= -p no:cacheprovider
```

結果：`64 passed, 2 warnings in 2.33s`。兩個 warnings 是既有 pandas dtype FutureWarning。新 oracle 單獨 `8 passed`；兩個 changed test files `py_compile` exit 0；`git diff --check` exit 0，只有 LF/CRLF warnings。

## REQUIRED REVIEW

請實際讀取三個 changed/report files 與必要 production context，逐項檢查：

- acceptance criteria 與 behavior preservation；
- fixed/quantile、processing order、stable tie-break、top-N 與 negative-evidence order；
- Decimal quantum、legacy float type/value、bp rounding、missing/NaN/Infinity 語意；
- PIT cutoff、future availability、missing DB、degraded/exception/liquidity distinctions；
- recommendation、screening matrix、why-not、liquidity、warnings、context identity 是否各自有精確 oracle；
- expected values 是否獨立，是否共用 production helper 或以 hard-coded fingerprint 造成環境不穩定；
- rule selection 與 ML unavailable annotation 是否分離，是否誤載正式模型／資料；
- SOL gate 對 `decision_at` 的排除是否只移除 invocation identity，其他 context 仍 full-equality；
- UI fixture repair 是否只補實際 dependencies，是否還保持 saved ID clearing 與 status update assertions；
- architecture compliance、dependency direction、persistence/replay/ML compatibility、hidden state、duplicated ownership、scope creep；
- tests 是否足以支撐 R011/R018/R019，或仍缺正反例／會放過順序、rounding、missing 變更。

## REVIEW OUTPUT

提供精確可定位 findings。若需修改，指出檔案、case、預期 assertion 與原因；不要重寫任何 code，也不要要求 unrelated cleanup。回覆最後必須且只能選擇：

`REVIEW_STATUS: PASS`

`REVIEW_STATUS: CHANGES_REQUIRED`

`REVIEW_STATUS: BLOCKED`
