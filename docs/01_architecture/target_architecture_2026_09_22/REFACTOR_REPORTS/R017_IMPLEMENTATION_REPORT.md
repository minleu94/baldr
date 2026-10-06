# R017 replay canonical bridge 實作報告

## 狀態與範圍

- TASK：R017 replay canonical bridge
- IMPLEMENTATION_STATUS：`IMPLEMENTATION_COMPLETE_ACCEPTED_SCOPE`
- 裁決：R017 option 2 的 synthetic/in-memory implementation gate `ACCEPTED_SCOPE`；這不代表整體 Wave 6 pass
- OWNER：`RecommendationDataFrameProvider` / `RecommendationReplayService` / `RecommendationSnapshotDTO` 的 in-memory replay bridge
- CREATED_TEMPORARY_COMPONENT：`TMP-REC-04`
- REMOVES_TEMPORARY_COMPONENT：R020
- INDEPENDENT_REVIEW：`ACCEPTED_SCOPE`（僅 synthetic/in-memory implementation gate）
- SOL_BLOCKER_FOLLOW_UP：`ACCEPTED_SCOPE`

本次只在既有 replay snapshot 建立後，投影 typed child execution；provider 的篩選、分數、排序與回測 evaluator 均未修改。Child 存在於每個 `RecommendationSnapshotDTO` instance 的私有記憶體屬性，不是 dataclass field，不進 `asdict()`、portfolio `to_dict()` 或既有 `from_dict()` readback。沒有呼叫 codec、persistence、scheduler、正式資料或 ML inference。

## 來源至欄位盤點

| 既有來源 | Typed 對應欄位 | 規則與未知值處理 |
|---|---|---|
| `run_snapshot(as_of_date=...)` 已正規化 snapshot 日期 | `Request.as_of_date`、`Context.as_of_date` | 沿用 wrapper 日期；不另外解析歷史 row clocks。 |
| `run_snapshot(profile_id=...)` | `Request.profile_ref`、`Context.profile_ref` | 保留原 ID；沒有 profile version source，故 `version=None`。空白或無效 ID 不建立 reference。 |
| 傳入並 deep-copy 的 `config` | `Request.config_snapshot` 與其內容雜湊 `config_ref` | 只對 JSON object 可表示的 config 建 snapshot；以 UTF-8 JSON bytes 計算內容 hash。沒有另造外部 config registry/version。無法無損表示時維持 `None`。 |
| 傳入 config 中明確提供的 `_portfolio_max_stocks` | `Request.max_stocks` | 缺少 key 時為 `None`，不把 provider 預設 200 冒充來源值。明確 int、可由既有 `int()` 無損解析的整數字串與整數值 float，沿用 provider 既有 coercion；bool、非整數 float（如 `2.5`）或無效值維持 `None`，不把布林轉換或截斷稱為精確 typed 值。 |
| `run_snapshot(top_n=...)` | `Request.top_n` | 只記錄明確正整數；不替負值或非整數建立虛假 request 欄。 |
| 外層 snapshot 的 `regime` | `DecisionBatch.regime` | 原樣映射；不重新偵測 regime。 |
| provider candidate row `stock_code`、`stock_name`、`selection_reason` | `RecommendationItem.stock_code`、`stock_name`、`reason_text` | 只接受 contract 可表達的原始值。任何非 mapping row、缺少/非法/重複代碼或已知欄位型別不符，都使整個 typed child 維持 `None`；不略過候選、不產生部分 `COMPLETED` child。外層 legacy row 原樣保留。 |
| provider row `total_score` | `RecommendationItem.rule_score` | 只用 `Decimal(str(existing_value))` 保留既有 wire 數字表示；不重算或量化分數。來源缺少或明確為 `None` 時維持 `None`；有值但不能表示為有限 Decimal 時，整個 typed child 維持 `None`。 |
| `factor_scores.technical/pattern/volume` | `indicator_score` / `pattern_score` / `volume_score` | 只做欄名對應與 Decimal 表示轉換。缺少或 `None` 保持 unknown；已提供但不合法的分數不作部分降級，整個 typed child 維持 `None`。 |
| provider row `factor_scores.broker_flow/revenue` | 無 typed owner | 保持只在外層 legacy dict；不塞進任意 mapping 或錯配既有 factor 欄。 |
| close price、price change、industry、`recommendation_rank` 等無 typed owner 欄位 | 無 typed 值 | 保持只在 legacy row，不從 history 重讀、不重新排序或由順序推造 rank。`DecisionBatch.items` 按來源 candidate list 的原順序建立；已知 candidate/score 投影須與來源數量、順序及 Decimal 值完整一致。 |
| legacy/test injection 的 `stored_annotation`、row-level `available_at`、`source_refs` | 無 typed 欄位 | 僅外層 legacy dict 原樣保留；typed child 不把注入資料當 production source、ML projection 或 availability evidence。 |
| provider/replay 沒有提供 policy version、parent result ID、data snapshot/source identity、decision/created/available clock | `policy_ref=None`、`related_references=()`、空 source/data refs、clocks `None` | 不從 current model、今日資料、class 名稱、profile ID 或測試 fixture 偽造 lineage。 |
| provider/replay 無 ML output | 預設 `MLAvailability.UNKNOWN`，projection/receipt refs 為空 | 不執行或查詢 current model。 |

每次成功建立的 typed child 有新的 `replay-<uuid>` `result_id`；這是本次 in-memory execution identity，不代表 legacy snapshot 有 parent identity。Empty result 仍是 `COMPLETED` + 空 `DecisionBatch`。Provider 原有例外仍在 bridge 前直接拋出，error path 沒有改寫。

## TMP-REC-04 登錄

`FINAL_MIGRATION_SEQUENCE.md` 的 TMP 登錄已定義 `TMP-REC-04` owner、caller `RecommendationDataFrameProvider.__call__` → `RecommendationReplayService.run_snapshot`，以及 R020 退場條件；本報告確認 R017 建立的具體過渡形狀是 snapshot instance-only 的 typed child accessor 加 service-side row projection。沒有新增第二個 TMP ID 或永久 artifact。R020 在共用 evaluator 接入且 R005 mode-specific parity 通過後，依原登錄移除 dict bridge 與重複 row schema。

## 策略、數值與未來函數自查

- Replay wrapper/provider 原始 body、factor manifest builder、外層 recommendations payload 與 portfolio evaluator 均未改動；typed projection 發生於 legacy snapshot 建立之後。
- R005 cutoff、`available_date`、universe、lookback、stock cap、20 列門檻、fast filters、score fallback、stable sorting/tie、top-N、skip、empty 與 factor manifest 由既有 13 項 characterization 固定；V-REPLAY 原回歸組合亦通過。
- 核心金融計算沒有新增。分數只由既有 wire value 轉成 `Decimal(str(value))`；沒有裸 float 運算、rounding、重新評分或 candidate mutation。
- Look-ahead：child 只讀 `run_snapshot` 已按 `as_of_date` 與既有 `available_date` cutoff 過濾後的 provider rows；bridge 不讀取 cutoff 後資料、不生成新 clock、不查 current model、不擴大 universe、不重排候選。
- 限制：`Context.available_at` 與 source/data refs 維持 unknown/empty，因 production provider output 沒有對應來源。R020 若要加入此類資訊，須先取得正式 source owner 與版本契約。

## 驗證

| 命令 | 結果 |
|---|---|
| `DATA_ROOT` / `OUTPUT_ROOT` 指向 `%TEMP%\r017-blocker-data` / `%TEMP%\r017-blocker-output`，`PROFILE=test`；`\.venv\Scripts\python.exe -m pytest tests\test_recommendation_replay_bridge.py -q -o addopts= -p no:cacheprovider` | `21 passed` |
| 同一 TEMP 環境：bridge + characterization focused suite | `34 passed` |
| 同一 TEMP 環境：bridge、characterization、C1 replay readiness、historical replay/backtest regression suite | `96 passed, 24 warnings`；警告是既有 same-day-close idealized backtest 假設提示 |
| `\.venv\Scripts\python.exe -m py_compile app_module\recommendation_replay_service.py tests\test_recommendation_replay_bridge.py` | 通過 |
| `\.venv\Scripts\python.exe -m mypy --follow-imports=skip app_module\recommendation_replay_service.py` | `Success: no issues found in 1 source file` |
| scoped `git diff --check` | 通過；僅有 repo 既有 LF→CRLF checkout warning |

PowerShell 驗證命令：

```powershell
$env:DATA_ROOT = Join-Path $env:TEMP 'r017-blocker-data'
$env:OUTPUT_ROOT = Join-Path $env:TEMP 'r017-blocker-output'
$env:PROFILE = 'test'
\.venv\Scripts\python.exe -m pytest tests\test_recommendation_replay_bridge.py -q -o addopts= -p no:cacheprovider
\.venv\Scripts\python.exe -m pytest tests\test_recommendation_replay_bridge.py tests\test_recommendation_replay_characterization.py -q -o addopts= -p no:cacheprovider
\.venv\Scripts\python.exe -m pytest tests\test_recommendation_replay_bridge.py tests\test_recommendation_replay_characterization.py tests\test_c1_replay_bridge_readiness.py tests\test_historical_evidence_replay.py tests\test_recommendation_historical_replay.py tests\test_recommendation_portfolio_backtest.py tests\test_backtest_timeline_contract.py -q -o addopts= -p no:cacheprovider
\.venv\Scripts\python.exe -m py_compile app_module\recommendation_replay_service.py tests\test_recommendation_replay_bridge.py
\.venv\Scripts\python.exe -m mypy --follow-imports=skip app_module\recommendation_replay_service.py
```

三個 pytest 命令依序結果為 `21 passed`、`34 passed`、`96 passed, 24 warnings`。

測試只用合成 DataFrame 與記憶體物件；沒有正式資料、SQLite、檔案 artifact、scheduler、full ML 或 promotion 操作。Bridge 測試覆蓋 known-field mapping、result identity、未知 annotation/parent/policy/source/clocks、外層 DTO byte roundtrip、from-dict unknown state、empty result、缺少來源 max stocks、candidate list 與 score 的精確順序/值 parity、rank 僅保留在 outer legacy row、非法或重複 stock code、非 mapping row、不可表示分數與已知欄位型別錯誤 fail-closed，以及 provider exception passthrough。

## SOL blocker 修正（獨立複審 scoped acceptance）

- `_effective_max_stocks` 不再將來源缺少的 `_portfolio_max_stocks` 投影成 provider 的預設 200；typed request 保持 `None`。明確 int、整數字串及整數值 float 沿用 provider `int()` 的有效值；bool、非整數 float（例如 `2.5`）及不可解析值不投影，避免 `True→1` 或小數截斷被稱為來源精確值。Provider 的原始執行與預設值未改動。
- Candidate projection 改為 all-or-none。任何 row 非 mapping、`stock_code` 缺少/非字串/空白/重複，已知 name/reason 欄位型別不符、`factor_scores` 非 mapping，或已提供但無法轉成有限 Decimal 的已知分數，均不附加 typed child；legacy snapshot、recommendations rows 與外層 `asdict()`/`to_dict()` 行為保持原樣。
- 新增逆序 `recommendation_rank` fixture，證明 typed item order 跟隨 legacy candidate list，而不按未擁有的 rank 重排；candidate code/order 及 `Decimal(str(source score))` 逐項比對。新增 explicit max-stocks coercion 測試，涵蓋 int、整數字串、whole float、2.5 與 bool。
- 獨立 R016 consumer owner 對本 R017 in-memory/synthetic implementation gate 給予 `ACCEPTED_SCOPE`；接受範圍不涵蓋整體 Wave 6 gate，也不改變 R020 後續 evaluator 整合責任。
- 未驗證限制：真實 producer 若提供 bridge 未知的 opaque 欄位，仍只存在 legacy row，沒有 typed owner；此 patch 不將未知欄位回填到 execution。未跑 scheduler、正式資料、完整 ML 或 portfolio evaluator 自身的實盤等效驗證。
- 變更限於 `app_module/recommendation_replay_service.py`、`tests/test_recommendation_replay_bridge.py` 及本報告；沒有 stage/commit。

## 回滾清單

### 變更檔案清單

| 檔案路徑 | 變更類型 | 變更摘要 | 回滾方式 | 回滾風險 |
|---|---|---|---|---|
| `app_module/recommendation_replay_service.py` | 修改 | 增加 in-memory typed child projection | 先確認 diff 只包含 R017 hunks，再從任務 TEMP 備份還原 | 會移除本次 bridge；若檔案後續含其他工作，不可整檔還原 |
| `app_module/recommendation_portfolio_dtos.py` | 修改 | 增加不參與 dataclass serialization 的 instance child accessor | 先確認 diff 只包含 R017 hunks，再從任務 TEMP 備份還原 | 會移除本次 accessor；若檔案後續含其他工作，不可整檔還原 |
| `tests/test_recommendation_replay_bridge.py` | 新增 | synthetic R017 bridge roundtrip/error/empty tests | `Remove-Item -LiteralPath tests/test_recommendation_replay_bridge.py` | 無；只移除本次新增測試 |
| 本報告 | 新增 | R017 欄位盤點、TMP 登錄與驗證記錄 | `Remove-Item -LiteralPath docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R017_IMPLEMENTATION_REPORT.md` | 無；只移除本次新增報告 |
| `docs/agents/shared_state/active_task.yaml`、`docs/agents/shared_state/handoff_log.md` | 修改 | 記錄本次高風險任務狀態與交接 | 只移除唯一鍵 `refactor_execution_wave6_r017_implementation_20260923` 及本次新增交接段落 | 需保留其他並行任務紀錄 |

### 回滾步驟

1. 核對兩個 source 檔 diff，確認沒有其他 Agent/使用者新增的 hunks。
2. 只在 diff 確認為本任務內容時，將兩個 source 檔從任務開始前保存於 `%TEMP%\r017_replay_bridge_20260923_before` 的原始副本還原。
3. 以表格中的精確 `Remove-Item -LiteralPath` 命令移除本任務新增測試與報告；從 shared state 只移除本任務唯一 YAML key 與交接段落。
4. 重跑 R005 characterization 與 V-REPLAY 組合，確認 legacy replay 恢復原狀。

沒有 stage、commit 或 push。
