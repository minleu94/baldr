# R014 — Scheduled snapshot 與 QA caller 遷移

TASK_STATUS: ACCEPTED_SCOPE
INDEPENDENT_REVIEW: `Accept R014`（synthetic／engineering scope；本次 Wave 6 gate review）
SOL_DECISION: `ACCEPTED_SCOPE`（synthetic／engineering）

## 結論

在 SOL 裁決 `C1_ENGINEERING_GATE_PASS`、Wave 6 `RELEASED_FOR_IMPLEMENTATION` 後，R014 已完成 scheduled recommendation wrapper 的 sealed execution 持久化切換，並將直接推薦 QA CLI 改為驗證同一 typed execution 的保存與 readback。實作沿用 R011 execution、R012 create-only store/query 與既有 forward candidate producer，沒有修改其 owner 檔案或增加推薦規則。

Scheduled 主路徑現在是：原始 caller config 快照 → 同次 `RecommendationExecution` → create-only save receipt → exact verified query/readback → forward producer 收取 typed saved-read。wrapper 不再讀取 worker 返回後的 shared `service.last_*`、手動重建 `RecommendationResultDTO`、以舊 repository 寫入第二份結果，或從舊 JSON 重讀決策時鐘。post-run result config、cohort、證據身分與時鐘由同一 invocation 的 postprocess capture 產生；saved execution 必須與本次 execution、receipt、payload hash、artifact location、config snapshots 和 clocks 完全一致，才會繼續向下游。

## 公開 composition seam

R013 可使用以下穩定入口；該 seam 只組合既有 store、persistence、save 與 query：

```python
from app_module.recommendation.composition import build_recommendation_composition

composition = build_recommendation_composition(config)
receipt = composition.save_service.save_execution(execution, label=None, notes=None)
read_model = composition.queries.get(execution.result_id)
```

- `build_recommendation_composition(config) -> RecommendationComposition`；`config` 提供 `resolve_output_path(subfolder) -> Path`。
- 保存根為 `config.resolve_output_path("recommendation/runs")`；artifact 根為 `runs_dir / "execution_artifacts"`，SQLite projection 為 `runs_dir / "recommendation_runs.db"`。
- `save_execution(...) -> SaveReceipt`；保存失敗、衝突或未索引依既有 R012 契約回報，不在 R014 包裝成成功。
- `queries.get(result_id) -> RecommendationExecutionReadModel | None`；不存在或完整性錯誤依既有 query 契約處理。R014 另外要求 receipt 為 `INDEXED` 且 readback 完整相符。

## Caller 與 side-effect 清冊

| Caller | 現況與 side effect |
|---|---|
| `scripts/scheduled/run_scheduled_recommendation_snapshot.py::main` | 已切換為 execute → create-only save → verified readback → typed forward producer。status/log/exit/help、calendar custody、`decision_at`、save-before-forward 次序保留。失敗仍由 wrapper 寫 `failed` status 並返回非零；save 或 query 失敗時不啟動 producer。 |
| `scripts/qa_validate_recommendation_tab.py` | 直接 service/filter/離線 look-ahead loop 改用 execution/readback；UI DTO 欄位驗證只使用正式 legacy projector 作相容投影。離線資料、DATA_ROOT、OUTPUT_ROOT 與報告皆在 TEMP/test 隔離根。 |
| `scripts/qa_validate_phase2_5.py` | 推薦、regime 與保存讀回檢查改驗同次 execution、create-only receipt、canonical query 與 typed item 分數。CLI 強制 `PROFILE=test` 且資料／輸出根須在 TEMP。 |
| `scripts/qa_validate_phase3_3b.py` | Why/Why Not、watchlist linkage 與另一推薦步驟改用 typed execution/readback；root gate 從 repo `output/master_goal/TASK-LOOP-04` 改成 TEMP，防止 QA 寫入 repo/formal output。此完整流程未執行。 |
| `scripts/qa_validate_pattern_opt.py` | 兩組推薦結果比較改用 typed execution/readback。效能時間包含 save/readback，故代表 end-to-end 路徑；比較雙方使用相同持久化步驟。CLI 強制 TEMP/test。此效能 CLI 未執行。 |
| `scripts/qa_validate_decision_loop.py` | 保留 synthetic legacy DTO writer，僅用作舊格式 consumer/Decision Desk 相容 QA fixture；它不呼叫推薦 producer，不是本次推薦執行 caller。 |
| `scripts/qa_validate_research_journey_qt.py` 與 Qt journey callers | Qt/UI 切片由其 owner 處理；本次未修改。現有 synthetic legacy DTO 用例屬舊 consumer 相容測試。 |
| `scripts/run_personalization_recommendation.py` | 保留給 R015；本次未改。 |
| service/unit characterization tests | 仍有多處直接呼叫 legacy `run_recommendation()` 來測試推薦 engine 行為。它們不負責 scheduled persistence 或本次直接 QA CLI 路徑，故保留。 |

已知 R016 下游依賴：`DailyInvestmentJourneyService._read_candidate` 原本直接讀 `runs/<result_id>.json`，對新 canonical artifact 路徑會回報 `recommendation_run_missing`；evidence/status 讀 legacy runs table 也可能看不到新結果。R016 consumer owner 正處理統一 query/read seam。R014 不另寫 legacy JSON，也不改該 consumer，避免破壞 create-only 唯一保存與 ownership 邊界。

R014 的實作範圍限於 scheduled wrapper、四支直接推薦 QA CLI、wrapper 測試、新 `app_module/recommendation/composition.py`、QA execution/readback helper 與本報告。cutover 接受後另窄幅同步 `scripts/scheduled/README.md` 的目前輸出／查詢路徑，歷史範例保持原樣。沒有修改 Qt、R016 readers、R017 replay、R012 store/save/query、`decision_service_composition.py`、calendar/scheduler registration、forward producer 或推薦/ML business policy。沒有新增裸 `float` 計算。

## Look-ahead 自查

本切片沒有新增訊號、特徵、篩選、分數、停損或績效邏輯。postprocess capture 只讀同次 execution 傳入的 screening matrix、推薦列與 typed context 身分；`decision_at` 取自封存 execution context。forward calendar observation 必須證明 captured time 不晚於該 `decision_at`，且 checked/readback 後才交給 producer。離線 QA 的延遲修訂測試以既有 `available_date` cutoff 驗證同一 as-of 結果及負面證據不變。

## 驗證

最終命令使用 `%TEMP%\r014-final-qa` 作環境根，`PROFILE=test`：

```powershell
$qaRoot = Join-Path $env:TEMP 'r014-final-qa'
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $qaRoot 'data'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'output'
.\.venv\Scripts\python.exe -m py_compile app_module\recommendation\composition.py scripts\recommendation_execution_qa_support.py scripts\scheduled\run_scheduled_recommendation_snapshot.py scripts\qa_validate_recommendation_tab.py scripts\qa_validate_phase2_5.py scripts\qa_validate_phase3_3b.py scripts\qa_validate_pattern_opt.py tests\test_scheduled_recommendation_snapshot_wrapper.py
.\.venv\Scripts\python.exe -m pytest tests\test_scheduled_recommendation_snapshot_wrapper.py tests\test_task_loop_03_contract.py -q -o addopts=
```

結果：`py_compile` 成功；`39 passed, 2 warnings in 3.43s`。兩個 warning 是既有 `decision_module/scoring_engine.py:437` pandas dtype `FutureWarning`，與本切片無關。wrapper tests 覆蓋原始 caller config/hash、post-run config/typed identity、created/available/decision clocks、create-only save 與 query failure injection、save → query → producer 順序、calendar cache/refresh custody 與 decision-time cutoff、legacy format query readback、狀態與 help bootstrap。未執行 production scheduler/main、全流程 phase 3.3b、pattern-opt 效能 CLI、正式資料、ML rebuild 或 promotion。

另以 `%TEMP%` 合成行情直接執行 `qa_validate_recommendation_tab.validate_isolated_recommendation_loop`，結果 6 passed、0 failed、0 skipped；涵蓋同次 execution/query roundtrip、舊 as-of 延遲修訂不影響結果/負面證據、empty as-of 與來源 fixture hash 未變。該次 `PROFILE=test`，資料和 artifact 根皆在 `%TEMP%`。

此前曾以 repo `.tmp-r014-data` / `.tmp-r014-output` 環境變數執行 wrapper focused tests（10 passed）；該次 root 設定不符 TEMP 要求，因此已在 `%TEMP%` 隔離根重新執行並以 13 個 wrapper tests 通過。root agent 後續 `Get-Item` 查無兩個 repo 暫存目錄；未對共享 workspace 執行清理。

## 變更檔案與回滾範圍

- `app_module/recommendation/composition.py`（新增）
- `scripts/recommendation_execution_qa_support.py`（新增）
- `scripts/scheduled/run_scheduled_recommendation_snapshot.py`
- `scripts/qa_validate_recommendation_tab.py`
- `scripts/qa_validate_phase2_5.py`
- `scripts/qa_validate_phase3_3b.py`
- `scripts/qa_validate_pattern_opt.py`
- `tests/test_scheduled_recommendation_snapshot_wrapper.py`
- `scripts/scheduled/README.md`（同步目前 canonical artifact、runs DB/index、status/log 與 save-before-forward 說明；舊歷史檔唯讀）
- `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R014_IMPLEMENTATION_REPORT.md`

首次 wrapper focused 命令錯用 repo 相對暫存根，已於上節如實記錄；其餘測試根均由 pytest TEMP fixtures 或明確 `%TEMP%` 環境提供。沒有 stage、commit 或 push。共享工作樹中其他 owner 的 dirty/untracked paths 保持原狀。

## Final gate addendum — 2026-09-23

- 獨立 reviewer 結論為 `Accept R014`（synthetic／engineering scope）；SOL 裁決 R014 `ACCEPTED_SCOPE`。此 reviewer 結論由本次 Wave 6 gate review 記錄；repo 內沒有獨立持久化的 R014 review report。
- Owner focused wrapper／contract tests 為 **39 passed、2 warnings**；兩項 warning 是既有 `decision_module/scoring_engine.py:437` pandas dtype `FutureWarning`。TEMP 合成推薦 loop QA 為 **6 passed、0 failed、0 skipped**。原命令、隔離環境與未執行項目見上方「驗證」。
- 這是 scoped engineering acceptance；沒有執行 production scheduler/main、正式資料、full-market ML、promotion 或 deployment。R015 personalization CLI／delivery ACK 仍是獨立遷移範圍。
