# R016 — saved-result consumer cutover 實作報告

TASK_STATUS: `ACCEPTED_SCOPE_SYNTHETIC_ENGINEERING`
OWNER: `Luna Max — R016 saved-result consumers`
DATA_SCOPE: `synthetic tmp roots / pytest tmp_path only`
QUERY_EXTENSION: `U4 ACCEPTED_SCOPE；independent verdict ACCEPT_WITH_NONBLOCKING_NOTES；read-time-only legacy integrity limitation applies`
INDEPENDENT_REVIEW: `ACCEPT WITH NONBLOCKING NOTES；no R016 P1/P2`
SOL_DECISION: `ACCEPTED_SCOPE（synthetic/engineering）`

## 範圍與目前狀態

R016 範圍限定於 Wave 6 saved-result consumers：Advice、Decision Desk、watchlist analysis、evidence import／replay、Daily Investment Journey，以及 SOL 明確追加的 evidence/status readers。各 consumer 透過 `RecommendationExecutionQueries` 的 canonical typed read view 或經 U4 驗證的 legacy original-payload projection 讀取結果。沒有宣稱全 repository raw-reader closure。

`DecisionOutcomeJourney.JsonRecommendationReadAdapter` 與專用測試由 query extension owner 平行接線；canonical projection 已將 `Decimal` 轉成精確文字、date/datetime 轉成 ISO，且驗證 `journey.to_dict()` 可用 `json.dumps(..., allow_nan=False)`。`source_snapshot_hash` 不從語義不同的 `universe_snapshot_hash` 假造；legacy exact original mapping 仍保留原欄位。U4 獨立 reviewer 與 R016 獨立 reviewer 均為 `ACCEPT WITH NONBLOCKING NOTES`；SOL 已裁決 R016 `ACCEPTED_SCOPE`（synthetic/engineering），沒有 R016 P1/P2。R016 最終 16-file gate 為 **227 passed、1 skipped**；獨立 reviewer 原先發現的唯一失敗是本檔 watchlist 測試的 Qt event-pump polling，現已改成 signal-aware harness 並通過。

## 已遷移的 consumers 與保留行為

| Consumer / 檔案 | 讀取路徑與預期輸出 |
|---|---|
| `app_module/advice_composer.py` | Advice 使用統一 saved-result view；保留舊結果的來源、日期及既有缺欄語意，不補即時資料。 |
| `app_module/decision_desk_service.py` | Decision Desk 從 query list/read view 建立既有桌面 read model，維持日期選擇及 result identity。 |
| `app_module/watchlist_analysis_service.py`、`tests/test_watchlist_stock_analysis_navigation.py` | Watchlist 分析依保存結果建立研究上下文與來源連結；R013 integration fixture 已改為正式 legacy `runs` schema，沒有放寬 production query。非同步 UI 測試在 worker 啟動前接上 finished/error/cancelled signals，使用 nested `QEventLoop` 等候真實結果；1 秒 QTimer 僅作原有等待預算的 hang guard，保留 saved output/date assertions。 |
| `app_module/evidence_event_importers.py`、`app_module/evidence_pipeline_runner.py` | Importer 使用 query `.get()`／`.list()` 和明確 latest selector；query／integrity 失敗以 `recommendation_query_failure` 類診斷 fail closed，不偽裝成來源缺失或改走 raw fallback。保持唯讀，不做 live lookup。 |
| `app_module/historical_evidence_replay.py` | Historical replay 透過 query read view；canonical 與 legacy mixed ordering 使用具名 selector：單一 namespace 沿用既有順序，混合來源只比較 aware timestamp 的 UTC instant 並以 result ID 穩定 tie；naive／未知時間明示 ambiguous。 |
| `app_module/daily_investment_journey.py` | Canonical rows 由 sealed read model 投影，rank 只取保存的 `item.rank`；registered/unindexed legacy rows 與 top-level source identity 使用 U4 exact frozen payload。ID、path、hash、integrity、source identity 衝突、讀間 bytes 變化或任一 unsupported row 都 fail closed；保留 `data_as_of_date`／`data_date`／`payload_date` 日期回退及原始欄位 trace。 |
| `app_module/evidence_source_coverage_service.py`、`app_module/pre_v2_readiness_service.py` | 新 canonical IDs 從 query list 取得；legacy 候選只以原有檔名 pattern 發現 ID，日期與內容必須由 exact-ID query projection 驗證後才能進 coverage／readiness inventory。 |
| `app_module/scheduled_evidence_status_service.py` | latest status、日期 inventory 與 manual fallback 使用 query read views／verified exact legacy projection。Canonical manual 需 completed 且 decision 可用、`execution.request.config_snapshot.manual_qt_snapshot is True`，日期需符合保存的 request/context as-of；scheduled 結果需明確 `scheduled_snapshot` 標記並與可用 as-of identities 一致。pure legacy 保留既有排序；pure canonical 依 index persisted order；mixed 時只在全部 clock aware 時比較 UTC，否則回報 ambiguous。檔名僅發現候選 ID，損毀、unsafe、symlink、ID/date mismatch 或 query failure 不增加觀測日期。Canonical 與同 ID unindexed JSON 衝突時也會診斷並排除該 ID，不讓 canonical 靜默通過。 |
| `app_module/saved_recommendation_queries.py` | 提供 R016 consumer 共用的 read-only query construction、typed projection/date helper 與 latest selection；completed/decision、來源 provenance、日期一致性檢查 fail closed。 |
| `app_module/decision_outcome_journey.py`（平行 owner） | `JsonRecommendationReadAdapter` 使用 query `.get()`／`.list()` 與 U4 exact payload；`path_for()` 回傳已驗證路徑而不偽造 canonical `runs/<id>.json`。Canonical payload 將 Decimal 轉精確文字、date/datetime 轉 ISO；要求 JSON finite-safe serialization，並對 integrity/completed-decision fail closed。Legacy exact mapping、來源 identity、rank、opaque fields parity 由專用測試覆蓋。`source_snapshot_hash` 不以 `universe_snapshot_hash` 代替；R016 owner 未修改該檔。 |

Manual 已同步排程狀態入口、結果判讀、安全限制與排錯。明確說明 legacy filename 只是 ID 候選 discovery；完成且有決策的 verified legacy/manual 或明確標記 canonical Qt manual 才能產生 `manual_observed`；scheduled marker 與日期不符時不推斷來源。

## Reader inventory 與範圍外殘留

下列是截至本報告的具名 reader inventory。Residual 代表 R016 沒有改寫其 domain owner；本表不構成 repository-wide closure 聲明。

| Exact path / caller | 目前讀法及風險 | 分類／後續 owner |
|---|---|---|
| `app_module/user_declared_holding_research.py:774-807`，`_candidate_results()`；由同檔約 `:840` 的 research assembly 呼叫 | SQLite 取 `data_path` 後直接 `resolve()`、`read_text()`、`RecommendationResultDTO.from_dict()`；對 symlink/path race、raw payload schema 與新 canonical artifacts 可見性採舊 runs-table 假設。 | Portfolio/Exit holdings research，R016 外；SOL 指示後續在 R029/R031 前另派 Portfolio/Exit saved-result query slice，具體 owner 尚未指派。 |
| `ui_qt/views/portfolio_view.py:2947-3000`，`_validated_recommendation_result_id()`；caller `:3056`、`:3107` | 直接打開 `recommendation/runs/<id>.json` 並比對 result/stock；canonical-only 結果目前不會由此 legacy path 發現。 | Portfolio tab / Exit，R016 外；後續 owner 尚未指派，等待 SOL 的 R029/R031 slice。 |
| `app_module/personalization_read_service.py:550-595`，`read_result()`（JSON load 約 `:580`） | 直接依 metadata/path 讀舊 JSON，並投影 personalization metadata；未改為 R016 query。 | R015 personalization producer/save/readback slice。 |
| `app_module/personalization_save_adapter.py:963-967`、呼叫約 `:408`、`:487` | 透過 `RecommendationRepository.load_result()` 做 personalization 保存後 readback；不是本 task 新增的 raw parser。 | R015 personalization save/readback。 |
| `scripts/run_personalization_recommendation.py:713`、`:864` | 建立 `RecommendationRepository` 並保存 personalization recommendation；此處是 producer/writer，非 saved-result consumer cutover。 | R015 producer。 |
| `scripts/qa_cross_page_mainwindow_readback.py:139-142` | QA harness 直接讀測試輸出的 recommendation JSON，再讀 watchlist/trades；不是產品 consumer，但仍有 raw test-reader 路徑。 | QA harness residual；尚未分配 owner。 |
| `scripts/qa_validate_decision_loop.py:112-120`（`:116` 建 repository writer，之後以 `SavedRecommendationDeskProvider` 讀回） | 本段寫入 legacy fixture，再用已遷移 Decision Desk provider 讀回；`:116` 是 writer setup，不是直接 JSON reader。 | QA writer/readback harness；現有 reader 已走 provider。 |
| `app_module/recommendation_repository.py:406-432` | 永久 legacy compatibility `load_result()` 仍直接 decode 舊 JSON 並呼叫 `RecommendationResultDTO.from_dict()`；作為相容實作保留。 | Legacy repository/decoder compatibility layer，不屬新的 domain consumer。 |
| `app_module/recommendation/codec.py:837,855` | `decode_*` 最後轉為舊 DTO decoder，是 query/codec compatibility boundary；R016 不改 codec。 | R012/R017 query/codec implementation owner。 |

## 驗證

測試只使用 pytest `tmp_path` synthetic roots；執行相關命令前設定 `DATA_ROOT`、`OUTPUT_ROOT` 指向 `%TEMP%` 下的專用目錄並設 `PROFILE=test`。未讀正式資料，未執行 scheduler、full ML 或 promotion。

R016 最終核心與整合 gate，包含 Journey adapter 與 U4 query projection：

```powershell
$taskTemp = Join-Path $env:TEMP 'r016-final-gate-after-qt-wait-20260923'
$env:DATA_ROOT = Join-Path $taskTemp 'data'
$env:OUTPUT_ROOT = Join-Path $taskTemp 'output'
$env:PROFILE = 'test'
.\.venv\Scripts\python.exe -m pytest tests\test_advice_composer.py tests\test_decision_desk_service.py tests\test_watchlist_stock_analysis_navigation.py tests\test_r016_saved_result_query_consumers.py tests\test_evidence_source_coverage_service.py tests\test_pre_v2_readiness_service.py tests\test_scheduled_evidence_status_service.py tests\test_historical_evidence_replay.py tests\test_recommendation_evidence_importer.py tests\test_recommendation_exclusion_payload.py tests\test_v4_cross_day_evidence_contract.py tests\test_daily_investment_journey.py tests\test_decision_outcome_journey.py tests\test_ui_qt_research_context_status.py tests\test_r016_legacy_query_projection.py tests\test_c1_legacy_query_readiness.py -q -o addopts= -p no:cacheprovider
```

```text
227 passed, 1 skipped in 8.46s
```

這批包括 synthetic canonical-only、legacy parity、same-ID canonical/unindexed collision、同日 mixed aware/naive clock、corrupt/symlink/ID/date mismatch 不增 observation date、保存 bytes/hash 未變、DecisionOutcomeJourney JSON serialization，以及 importer/query error fail-closed cases。獨立 reviewer 原本在 `tests/test_watchlist_stock_analysis_navigation.py::test_saved_analysis_reads_exact_source_and_rejects_future_without_writing` 遇到 UI text polling 不穩；測試現於 worker start 前觀察其 finished/error/cancelled signals，nested event loop 等待 worker 完成後仍斷言實際畫面理由與日期。具名測試 **1 passed in 0.80s**；完整 gate **227 passed、1 skipped**，沒有產品碼變更。R013 提報的 `tests/test_ui_qt_research_context_status.py::test_watchlist_drilldown_reads_saved_metadata_and_keeps_source_id` 已把合成 SQLite fixture 修正為正式 legacy `runs` 欄位形狀，保留 `result-1` source identity，現為 1/1 通過。單一 skip 是 Windows symlink 權限限制下的既有 symlink 測試；更完整的 U4 skip 與 host 限制記錄於 query extension report。

具名 Qt harness check 使用獨立 TEMP root：

```powershell
$taskTemp = Join-Path $env:TEMP 'r016-watchlist-signal-test'
$env:DATA_ROOT = Join-Path $taskTemp 'data'
$env:OUTPUT_ROOT = Join-Path $taskTemp 'output'
$env:PROFILE = 'test'
.\.venv\Scripts\python.exe -m pytest tests\test_watchlist_stock_analysis_navigation.py::test_saved_analysis_reads_exact_source_and_rejects_future_without_writing -q -o addopts= -p no:cacheprovider
```

Scoped static checks（含 Journey adapter）：

```powershell
$taskTemp = Join-Path $env:TEMP 'r016-final-gate-after-qt-wait-20260923'
$env:DATA_ROOT = Join-Path $taskTemp 'data'
$env:OUTPUT_ROOT = Join-Path $taskTemp 'output'
$env:PROFILE = 'test'
.\.venv\Scripts\python.exe -m mypy --follow-imports=silent app_module\advice_composer.py app_module\decision_desk_service.py app_module\watchlist_analysis_service.py app_module\evidence_event_importers.py app_module\historical_evidence_replay.py app_module\evidence_source_coverage_service.py app_module\pre_v2_readiness_service.py app_module\scheduled_evidence_status_service.py app_module\daily_investment_journey.py app_module\decision_outcome_journey.py app_module\saved_recommendation_queries.py
.\.venv\Scripts\python.exe -m py_compile app_module\advice_composer.py app_module\decision_desk_service.py app_module\watchlist_analysis_service.py app_module\evidence_event_importers.py app_module\historical_evidence_replay.py app_module\evidence_source_coverage_service.py app_module\pre_v2_readiness_service.py app_module\scheduled_evidence_status_service.py app_module\daily_investment_journey.py app_module\decision_outcome_journey.py app_module\saved_recommendation_queries.py tests\test_r016_saved_result_query_consumers.py tests\test_daily_investment_journey.py tests\test_decision_outcome_journey.py tests\test_scheduled_evidence_status_service.py tests\test_ui_qt_research_context_status.py tests\test_r016_legacy_query_projection.py tests\test_watchlist_stock_analysis_navigation.py
git diff --check -- tests\test_watchlist_stock_analysis_navigation.py app_module\daily_investment_journey.py app_module\scheduled_evidence_status_service.py docs\07_guides\APPLICATION_MANUAL.md
```

```text
Success: no issues found in 11 source files
py_compile: exit 0
```

U4 query extension's independently reviewed combined result is recorded in `R016_LEGACY_QUERY_PROJECTION_IMPLEMENTATION_REPORT.md` (`110 passed, 4 skipped`; skips are Windows symlink-creation privilege constraints); its dedicated projection suite is `49 passed`. U4 independent verdict is `ACCEPT_WITH_NONBLOCKING_NOTES` and SOL scope acceptance. R016 final combined consumer/query gate reran in a fresh TEMP root after the watchlist harness fix and Journey adapter JSON normalization: `227 passed, 1 skipped`. Scoped mypy (11 source files), py_compile, and selected `git diff --check` pass. R016 independent review is `ACCEPT WITH NONBLOCKING NOTES`; SOL `ACCEPTED_SCOPE` is limited to synthetic/engineering evidence.

## Compatibility, integrity, and remaining gate

- Old JSON display remains a read-only compatibility path; canonical views do not trigger live data/model lookup, annotation, scoring or inference. Missing fields remain unknown; unsupported legacy shapes get a diagnostic rather than consumer-side fallback parsing.
- For legacy artifacts without a separately trusted historical digest, U4 hash records bytes read at that time only (`legacy_read_time_hash_only`). It cannot prove that mutable legacy bytes were not replaced before this read.
- SOL accepted this R016 implementation scope for synthetic/engineering use; the independent reviewer returned `ACCEPT WITH NONBLOCKING NOTES` and no P1/P2. The combined tests cover DecisionOutcomeJourney canonical/legacy fixture and source trace parity plus finite-safe JSON serialization. The previously failing watchlist test was a Qt test-harness wait issue only; fixed test now waits on worker signals and retains assertions for the saved UI result.
- No stage, commit, or push was performed.
