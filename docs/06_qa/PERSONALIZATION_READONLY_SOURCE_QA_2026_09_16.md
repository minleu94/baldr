# Personalization 真實來源唯讀入口 QA（2026-09-16）

## 目的與範圍

本次驗收把 fixture-only projection／evaluator 以 bounded read-only composition 接到既有來源：

- Recommendation JSON 與 `recommendation_runs.db` metadata：exact `result_id + stock_code`。
- `portfolio/journal_entries.jsonl`：既有 continuity revision、technical delivery ACK 與帶 personal envelope 的新 action。
- EvidenceEvent／EvidenceOutcome SQLite：exact result／symbol identity；event 與 outcomes 在同一 SQLite read transaction 讀取。
- Embedded、declared-path 與既有 receipt 目錄：只驗證已保存 hash，不重算 recommendation。

入口是 `scripts\inspect_personalization_sources.py`；它不建立 writer-oriented repository／Journal constructor，不 mkdir、DDL、lock、append、learner、promotion、global pointer、scheduler 或 order。

## 受控 regression

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_personalization_read_service.py `
  tests/test_personalization_action_recorder.py `
  tests/test_personalization_projection.py `
  tests/test_personalization_contract.py `
  tests/test_personalization_calibration.py -q -o addopts=
.\.venv\Scripts\python.exe -m mypy `
  app_module/personalization_read_service.py `
  app_module/personalization_action_recorder.py `
  app_module/personalization_projection.py `
  tests/test_personalization_read_service.py --explicit-package-bases
.\.venv\Scripts\python.exe -m pytest `
  tests/test_personalization_generation_cli.py `
  tests/test_recommendation_service_calibration_integration.py -q -o addopts=
.\.venv\Scripts\python.exe -m mypy `
  app_module/recommendation_service.py `
  scripts/run_personalization_recommendation.py `
  app_module/personalization_contract.py `
  app_module/personalization_projection.py `
  app_module/personalization_read_service.py `
  app_module/personalization_save_adapter.py `
  app_module/personalization_action_recorder.py --explicit-package-bases
```

本次 read-service regression 覆蓋 exact bounded Journal、malformed source、cache reset、WAL snapshot 與 normal action entry；generation CLI 與真實 RecommendationService temporal integration 另覆蓋 producer → save/readback → ACK、自然 source-latest T-1、舊 cutoff fail-closed 與 explicit historical tier。

時間欄位分成 `prediction_decision_at`（producer 推論）、`delivery_at`（technical ACK）與 `human_decision_at`（最後一筆 recorded action revision 的 `action_at`）。ACK 晚於推論不會被誤判為 late；只有 ACK 晚於明確 human anchor 才標 `late_delivery_no_natural_credit`，並從 `evaluation_row_count`／`action_utility_count` 排除。請交叉核對 `natural_forward_count`、`evaluation_row_count`、`cohort.included_evaluation_row_count` 與 `cohort.excluded_reason_counts`。active candidate 的 `label_registry_hash`、`label_contract_id`、`return_basis` 必須可從 verified training lineage／candidate provenance custody 回讀，且與 receipt row 一致；缺漏／mismatch 由 consumer 與 receipt producer fail-closed，不以全域現行常數替舊 candidate 補值。

| case | 驗收 |
|---|---|
| missing output／journal／evidence root | 只回傳 diagnostic，root 與 parent 均不建立 |
| result JSON 在 read 後被改寫、reader 仍回傳舊 payload | `source_bytes_unchanged=false`、`source_consistency_status=invalidated`、evaluation／rows 不產生、cohort 不為 ready |
| bounded result inventory | `available/selected/excluded/truncated` 與選取順序可追溯；日期型最新 result 不會被升序切片漏掉 |
| bounded candidate inventory | `available/selected/excluded/truncated` 與 exclusion reason 可追溯 |
| 重用同一 read service | reset cache 後可看見新 recommendation inventory，不沿用舊 JSONL／evidence／receipt cache |
| SQLite WAL／並行 outcome | event decode 時 commit 的新 outcome 不會混入已開始的 read snapshot；reset 後才可讀到新 outcome；`-wal/-shm` 進 manifest |
| exact event bound | 先以 persisted result identity 篩選，再套 `max_events`；target 在 symbol 的前 N 外仍可讀，conflicting alias 保留給 projection fail-closed |
| normal action CLI | 明示 scope／result／stock／action／request 後，先完成唯讀 delivered exact preflight 才追加既有 Journal；retry 保留原 revision；缺 projection、不完整 source 或缺 scope 不建立 writer files |

本輪 focused pytest：personalization/action/save 20 passed、UI update/workbench 84 passed、training/lineage 17 passed、讀取／projection／generation 62 passed、RecommendationService real integration 12 passed；受影響模組 `mypy` 11 files 亦通過。pytest cache 的既有環境寫入 warning 不影響結果。沒有執行正式 scheduler、full runner 或資料重建。

## 正常使用者 action entry

`scripts\record_personalization_action.py` 是受控的新增 action 入口，不會自己創建 scope，也不會把舊的 accepted／skipped 或其他 legacy action 改寫成 personal action。使用者需明示 `scope_id`、`result_id`、`stock_code`、研究 action、`decision_kind`、唯一 `request_id` 與 `actor`；省略 `action_at` 時取實際 UTC clock。命令先呼叫 `PersonalizationReadService.inspect_scope()`，要求 `source_consistency_status=verified`、`source_completeness_status=verified`、exact projection 為 `linked_prediction`、delivery 為 `delivered`，並再次核對 scope、prediction、receipt、horizon、cost、label／return identity。

唯讀 preflight 通過後，才委派既有 `JournalService.record_research_action()`，把完整 `PersonalizationActionEnvelope` 放在既有 revision payload；沒有新增 personal ledger。append 後會 reset read cache，再用 read service 驗證 exact action revision。相同 request 的 retry 不重複追加；preflight 失敗時 `write_attempted=false`、exit `2`，不建立 output／Journal writer artifacts。

首筆 personal prediction 可用 `scripts\run_personalization_recommendation.py`：caller 明示 data／output／strategy config 與 scope／delivery identity，命令執行既有 RecommendationService；自然模式由 producer 從實際來源選取最新可得 cutoff，`--as-of-date` 僅是 exact assertion，若 caller 強行指定舊 cutoff 而與 producer 選擇不一致，會在 save 前 fail closed。producer context 與 durable projection receipt 產生實際 scope clocks，CLI clocks 只作可選 assertion，再經 RecommendationSaveRequest／RecommendationRepository create-only save/readback，最後追加 technical delivery ACK。沒有 durable projection receipt、temporal contract 或 decision／horizon anchor 時不保存普通結果；ACK 後才可使用上方 action command。`--as-of-date` 是市場資料 cutoff，合法 T-1 cutoff 可在下一個 `Asia/Taipei` 市場日執行；明確舊 cutoff 必須加 `--historical-research`，並與自然 tier 分離。

隔離驗收由 `tests/test_personalization_read_service.py` 的 CLI、exact Journal bound、overflow、malformed、正常 action/outcome 與遲交 action readback cases 覆蓋：遲交 revision 的 `action_conflict_count=1`、`natural_forward_count=1`，但 `evaluation_row_count=0` 且 exclusion reason 明確為 `late_delivery_no_natural_credit`。`tests/test_personalization_action_recorder.py` 另驗證 pre-delivery action 不升格、ACK 後正常 action，以及多 revision 以最後 recorded revision 的 `action_at` 作 human anchor；`tests/test_personalization_save_integration.py` 驗證只有 producer inference／ACK 時不誤報 late，並以獨立 process 的正式 `MainWindow()` probe 驗證真實 save button、window-owned Journal／Repository、ACK、read projection 與 close／worker 收尾。`tests/test_personalization_generation_cli.py` 另覆蓋 producer → save/readback → custom Journal ACK、optional clock assertions、immutable result／receipt retry、自然舊 cutoff fail-closed 與 explicit historical tier；`tests/test_recommendation_service_calibration_integration.py` 則以真實 RecommendationService／real receipt 驗證 source-latest 的 T-1、三時鐘、verified label custody、missing／mismatch fail-closed 與歷史模式隔離。正式 D 槽目前仍只有 `population_only`，因此沒有對 D 槽呼叫 action 或 generation writer；這是保護正式資料與避免偽造使用者決策的預期行為。

## 正式資料唯讀 probe

執行的 bounded command（stdout 只在 shell 內摘要，沒有寫報告檔）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.inspect_personalization_sources `
  --scope-id local_research_scope_v1 `
  --as-of 2026-09-16 `
  --evaluation-cutoff-at 2026-09-16T23:59:00+00:00 `
  --output-root D:\Min\Python\Project\FA_Data\output `
  --result-id scheduled_rec_20260916_051003 `
  --max-results 1 --max-candidates-per-result 10 --max-evidence-events 10
```

結果：

| 欄位 | 實際值／判讀 |
|---|---|
| CLI | exit `0` |
| scope／as-of | `local_research_scope_v1`／`2026-09-16` |
| selected result | `scheduled_rec_20260916_051003`；2 個 candidates：`1727`、`1568` |
| inventory | available `81`、explicit selected `1`、reported excluded `80`；explicit result scope 下 `truncated=false`；metadata inventory 標為 lower-bound，未把有限 inventory 宣稱全量 |
| source consistency | `verified`、`source_bytes_unchanged=true` |
| source completeness | `verified`；bounded Journal／Evidence scan 完整，personal scope／delivery 缺件另以 `scope_missing_population_only` 呈現 |
| source manifest | `sha256:98dd8efe630fb0389df38f535c0440b8470e90f9a076b4545ce31b9238a2b207` |
| fingerprint coverage | 8 paths：journal、selected recommendation JSON、recommendation metadata DB 及其 `-wal/-shm`、Evidence SQLite 主檔及其 `-wal/-shm`；主 Evidence DB `3,580,071,936` bytes，probe 前後 size／mtime／hash 相同 |
| denominators | `population_only=2`；`prediction_available=0`；action recorded／conflict／not recorded、outcome ready／pending／matured missing／invalid、natural／paper／declared／replay／synthetic、utility 與 evaluation rows 皆 `0` |
| cohort／evaluation | `pending_or_insufficient`；evaluation `null`，沒有 fit artifact，沒有宣稱 evaluated |
| diagnostics | 两個 candidate 都是 `scope_missing_population_only`；另有 `fit_artifact_missing:evaluation_not_run` |

正式資料中的最新 Recommendation JSON 沒有可驗證的 personal scope／delivery capture；空的正式 Journal 也沒有 personal action。全域 EvidenceEvent 的 provider/source rows 不因 `source_id` 猜成 result identity，因此不能補成 personal prediction 或 natural outcome。這是「入口可操作、正式樣本仍 pending／missing」的預期結果，不是零效果結論。

## 安全結論與後續

目前可接受的是 read-only source diagnosis、exact matched row assembly，以及通過 preflight 後由使用者明示的 `PersonalizationDecisionRecorder` action entry。只有新的 producer path 先保存完整 scope、prediction、receipt、horizon、cost、label／return contract，再在 delivery ACK 後以 `action_at >= delivered_at` 寫入既有 Journal revision，才可進入後續 cohort；舊 action 不 retrofit。正式 natural effect、utility、adoption、promotion 與交易授權仍未達成，應等待真實 scope-linked decision／mature outcome，而不是用 fixture、Paper 或 user-declared context 代替。

## 2026-10-11 後續個人 V2 路徑範圍

上方 2026-09-16 的唯讀 probe 數字與 scope 缺件仍限於該次正式來源、identity 與 as-of；後續 [M10 widget receipt](PERSONAL_MODEL_QT_WIDGET_ACCEPTANCE_M10_20260928.md) 使用獨立固定 snapshot 與 user-declared-source-time policy，完成 bounded candidate inference、canonical save/readback 與 capture v3。M10 Stage C 仍是 mature 0／pending 19，`official_historical_pit_verified=false`，最終 policy 為 `rule_only`；該路徑不追溯連結本次 probe 的 rows，也不證明 natural credit、global promotion、正式資料寫入或 OS foreground／真人驗收。
