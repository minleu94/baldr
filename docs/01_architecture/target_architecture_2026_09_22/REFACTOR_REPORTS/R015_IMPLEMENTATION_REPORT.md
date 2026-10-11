# R015 personal recommendation producer/save/ACK migration report

> **2026-10-11 status route:** The `Wave 7–14 remain BLOCKED` line below is the R015 report-time snapshot. The later R031 current overlay records R015 as `ACCEPTED_WITH_PERSONALIZATION_IDENTITY_SCOPE`; R029 and the migration ledger record `TMP-REC-03` as retired with legacy JSON exact-retry/read compatibility retained. This bounded acceptance does not establish natural ML inference, formal data acceptance, model promotion, or production rollout. See the [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md), [R029 report](R029_IMPLEMENTATION_REPORT.md), and [migration ledger](../FINAL_MIGRATION_SEQUENCE.md).

## Status and baseline

- Task: R015 personalization producer/save/ACK migration.
- Implementer: Codex GPT-6 agent.
- `IMPLEMENTATION_STATUS: ACCEPTED_SCOPE` (root bounded gate; synthetic engineering scope only).
- Start/end `HEAD`: `777c06d039a7676475f7f6eecebf9a24bb790692` (unchanged; no commit).
- Dirty baseline: shared Wave 6/Wave 7 worktree was already dirty with parallel R013/R014/R016/R017/R021/R027 work. This report lists only R015-owned changes; it does not attribute unrelated dirty files to R015.
- Dependencies: R011 execution/codec and R012 save/query were available; R013 Qt and R014 scheduled caller migrations had reached `ACCEPTED_SCOPE` before this slice started.
- Data scope: all new tests and CLI probes use `pytest tmp_path` or a fresh `%LOCALAPPDATA%\Temp` root with `PROFILE=test`. No formal market data, model promotion, training, production database, stage, commit, or push operation was performed. Wave 7–14 remain `BLOCKED`; this scoped acceptance does not release subsequent waves or formal/production work.

## Implementation

The personal producer now owns one sealed invocation from execution through persistence. `scripts/run_personalization_recommendation.py` calls `RecommendationService.execute_recommendation(...)`; its postprocess callback receives the invocation-local candidate rows and producer context. `PersonalizationRecommendationSaveAdapter.captures_from_invocation(...)` derives typed personal captures from those exact candidates, their calibration provenance, and the immutable projection receipt. The producer path does not read `producer.last_run_context`, construct a new legacy result DTO, or query an active model pointer. Receipt path/hash/result/candidate identity must resolve before the callback can emit a capture.

The callback's typed scope and generated captures are sealed as the existing R011-permitted `personalization_delivery_capture` event. The CLI verifies its six ordered producer clocks (`run_started_at <= personalization_scope_declared_at <= available_at <= captured_at <= decision_at <= receipt_created_at`), `available_at <= decision_at`, decision clock parity with the execution, source cutoff parity, and natural-cutoff request parity before a write or ACK. The R011 `MLReceiptBinding` supplies receipt hash, result/date, candidate ID, stock codes and optional cost hash; the projector requires exactly one matching binding and compares its candidate/cost identity to the hash-verified receipt. Model/dataset IDs and optional dataset hash are compared between the capture and receipt. Training provenance and its hash fields are read from that same receipt whose exact hash is in the binding; the typed binding does not define separate training-hash slots, so this slice neither adds schema fields nor infers missing provenance. Missing or contradictory inputs fail closed; calibration provenance is never filled from a later lookup.

Before save, execution encoding is decoded and compared for exact typed equality. Canonical persistence is create-only through R012 `save_service.save_execution`. Exact readback then verifies result ID, execution equality, payload and raw artifact hashes, label, index status, and generated capture identities. ACK runs only after this readback; it is an append-only Journal CAS command and is excluded from the execution/event hash.

The artifact contains the original `generated` capture and its generated `capture_hash`. A `persisted` capture hash and a `delivered` capture hash are derived lifecycle views after save/ACK; their hashes differ because status and lifecycle timestamps are part of capture identity. Neither derived hash is written back into execution, and neither is used to claim parity with the original generated hash. The CLI returns all three hash sets distinctly.

Scope criterion: only a result carrying a validated personal scope and its generated capture event can receive a personal ACK. A regular Qt manual recommendation has no personal scope/capture and remains an ordinary canonical save with zero personal ACK rows. If the personal CLI's same-invocation callback cannot produce a valid capture (for example, receipt lineage is missing), it fails before calling the canonical writer and emits no ACK.

Canonical retry uses the exact query and never reruns the producer. If the exact query reports an unindexed artifact, the only recovery path calls the existing safe `store.read_artifact(result_id)`, strict `decode_execution_envelope`, verifies exact ID/payload hash and absence of a conflicting index or legacy identity, validates the same identity/clock/receipt contract, and passes that same decoded execution to the same create-only writer to repair the index. An indexed corrupt artifact remains query-fail-closed. A different request hash/limit for the same ID is rejected before producer, save, or ACK. Legacy personal JSON retry remains on its existing read-only `RecommendationRepository`/DTO decoder path; it ACKs the exact old capture without rewriting bytes or decoding legacy bytes through the canonical event path.

## Typed readback seam and legacy parity

`PersonalizationReadService.read_canonical_execution_exact(...)` exposes exact canonical readback through the R012 query. `inspect_scope(...)` dispatches canonical read models to typed projection while retaining the existing legacy JSON flow for legacy rows. `PersonalizationProjectionService.build_for_execution(...)` validates the typed capture event, candidate identity, scope, receipt binding, clocks, temporal context, and receipt provenance. `_resolve_execution_prediction(...)` only reads the receipt already bound to the saved execution. After those canonical-specific checks it calls the shared `_finish_verified_delivery(...)`, which uses the existing `_resolve_action(...)` and `_resolve_outcomes(...)` logic for both legacy and canonical projections; no second action/outcome business pipeline was added.

The added projector code is separated into: (1) `build_for_execution` for exact execution/capture/scope/ACK/clock/binding validation, (2) `_resolve_execution_prediction` for immutable candidate/model/training/dataset/receipt parity, and (3) the shared final projection dispatch. This typed validation is needed because canonical event rows are typed mappings inside an immutable execution and must not be coerced into a `RecommendationResultDTO` or legacy JSON object. Its parity fixtures are the CLI generated→persisted→delivered projection test, altered candidate-binding fail-closed test, existing legacy projection action/outcome fixtures, and calibration service save/readback receipt fixture. The read-service additions only route exact canonical models to this projector and preserve the existing legacy read route.

The adapter's new invocation capture, six-clock snapshot, and execution-event readback are necessary to build and validate the single callback's data without DTO conversion. Existing legacy adapter bind/decoder methods remain for old personal JSON read/retry compatibility. Their use in the new producer path is prohibited by the integration tests.

## Caller closure and TMP-REC-03 retirement

- Qt manual save (R013) and scheduled snapshot (R014) now pass frozen `RecommendationExecution` to the canonical save service; ordinary Qt manual save has no personal scope and emits no personal ACK.
- The personalization new-result caller now passes the sealed execution to canonical save, exact query and delayed ACK. Its only remaining `RecommendationRepository` use is the read-only legacy personal JSON retry branch documented above.
- Full repository Python-source search for `RecommendationSaveRequest`, `RecommendationSaveCoordinator`, and `recommendation_save_coordinator` returned zero hits. A separate exact-name search across scripts, Qt, QA, tests, and the application Manual also found no coordinator reference; historical task/sequence documents retain the TMP identifier as migration history. Direct runtime search for legacy `.save_result(...)` found only two synthetic QA scripts (`qa_validate_decision_loop.py`, `qa_validate_research_journey_qt.py`); the personal CLI legacy `save_result_create_only(...)` is not called by the new-result path and remains only in historical-fixture setup/tests.
- Removed `app_module/recommendation_save_coordinator.py`, its pure API-mirror `tests/test_recommendation_save_coordinator.py`, coordinator test inventory entry, and old coordinator annotation assertions. Legacy run-context/DTO decoder protections were preserved by converting compatibility seeds to direct legacy `RecommendationResultDTO` fixtures and retaining legacy exact-ID read/retry coverage.
- The prior fake Qt `SimpleNamespace` ACK test was replaced with a no-personal-scope/no-ACK assertion. Host/process readback tests now exercise canonical manual save and confirm no personal ACK. A canonical Qt writer-failure test confirms the prior artifact bytes remain unchanged and no ACK is appended. The old R004 watchlist-writer failure test was replaced with a canonical Qt watchlist-soft-failure test. The stale fake UI identity-only test was removed after the canonical Qt execution identity test covered the actual caller.
- `docs/07_guides/APPLICATION_MANUAL.md` R015 section documents canonical save/readback, delayed ACK, retry/orphan repair, legacy JSON retry, generated/persisted/delivered hash semantics, clocks, test-profile isolation, and troubleshooting. That section is frozen for R021's independent §5.2 addition.
- `FINAL_MIGRATION_SEQUENCE.md` now records TMP-REC-03 as retired and links this report. R027 may proceed with its own TMP ledger addition after this row freeze.

## Compatibility, negative cases, and look-ahead review

| Contract | Evidence |
|---|---|
| Same ID/hash retry reuses the exact artifact and does not rerun producer | `test_generation_cli_explicit_scope_save_ack_and_retry_use_custom_journal`; legacy exact retry has a separate read-only fixture. |
| Different request hash/limits for the same ID fail before write/ACK | CLI test retries with a changed `--top-n`, expects `write_attempted=False`, unchanged artifact/journal and no extra producer call. |
| File-only orphan repair is explicit, same-ID/hash, safe and no-recompute | CLI test deletes only the temp index row, proves ordinary exact query fails closed, retries and verifies recovered query, same artifact bytes/hash, same execution and no second ACK. R012 persistence tests cover artifact/index partial failures. |
| Indexed artifact/index integrity failures remain fail-closed | R012 `test_r012_raw_payload_and_identity_hash_mismatches_fail_closed` verifies corrupt bytes, tampered payload hash and identity mismatch; `test_r012_artifact_id_mismatch_unknown_revision_and_untrusted_index_name_fail_closed` adds result-ID/revision/index-path cases. CLI does not treat these as orphan repair. |
| ACK CAS failure and retry are separated from execution | CLI writer fake injects Journal's `journal_delivery_ack_stream_conflict` after save; failure leaves the artifact indexed and emits no ACK. Retry reuses the saved execution, does not rerun producer, leaves artifact bytes unchanged, and appends exactly one ACK. The underlying real `JournalService` stale-token rejection is separately covered by `test_journal_delivery_ack_stream_cas_rejects_stale_history_without_append`. `test_ack_retry_scope_cas_and_writer_failure_do_not_mutate_result` uses `_FailingAckJournal` for writer failure, then verifies retry idempotence, changed-clock conflict and unchanged bytes. |
| Qt manual without personal scope does not ACK | `test_qt_manual_save_without_personal_scope_does_not_ack`, host integration and real process probe assert exact canonical readback plus zero personal ACK. |
| Qt writer failure does not mutate existing identity | `test_qt_save_writer_failure_preserves_artifact_and_does_not_ack` byte-compares prior artifact and checks no personal ACK. |
| Candidate/model/training/receipt identity parity and fail-closed mismatch | CLI canonical readback asserts prediction, receipt result/hash, model, dataset, dataset/cost hashes, horizon, label/return/universe policy and training provenance; altered execution candidate binding yields `unavailable`. Calibration save/readback integration continues to validate the legacy receipt path. |
| Clock/look-ahead safety | CLI asserts source cutoff/request parity before write, six-clock ordering and `available_at <= decision_at`; temporal tests cover the allowed prior-day market cutoff and natural-vs-historical mode distinction. The projector rechecks scope/execution decision+available clocks and embedded receipt decision date on read. |

No R011 execution schema/codec, R012 persistence/query, delivery Journal schema, calibration/retraining, promotion, model registry, or formal data code was modified by R015. The personal event uses the already allowed event type/schema and execution codec exact roundtrip; ACK metadata remains outside the execution envelope.

## Independent review P2 closure

The independent review found that legacy JSON retry verified receipt/scope identity and optional clocks but did not bind the stored `temporal_mode`, `cutoff_selection`, and `cutoff_policy` to `--historical-research` before ACK. The legacy preflight now requires the exact tuple before repository/Journal writer construction:

| Request mode | `temporal_mode` | `cutoff_selection` | `cutoff_policy` |
|---|---|---|---|
| Natural (default) | `natural_producer_clock` | `producer_selected_latest_available_cutoff` | `source_latest_available_exact` |
| Historical | `historical_research_not_as_if_available` | `explicit_historical_cutoff` | `explicit_historical_research` |

Every missing, non-string, unknown, or mismatched field fails closed. `test_legacy_historical_retry_requires_matching_temporal_identity` seeds a historical legacy JSON fixture, proves a natural-mode retry fails before `_writer` and leaves zero journal bytes/ACKs, unchanged JSON bytes, and no producer invocation, then retries with matching historical args and proves read-only artifact reuse plus one ACK. A parameterized test independently covers missing mode, unknown selection, and contradictory policy. The canonical retry path is unchanged.

## Changed R015-owned files

| File | Necessary change |
|---|---|
| `scripts/run_personalization_recommendation.py` | Sealed execution producer path, callback capture, codec parity, create-only save, exact readback, strict orphan repair, legacy retry routing, delayed ACK, separate lifecycle hashes. |
| `app_module/personalization_save_adapter.py` | Invocation-scoped typed capture and clock snapshot, canonical event capture reader, canonical readback input to the existing ACK operation; legacy adapter methods retained. |
| `app_module/personalization_read_service.py` | Exact canonical query seam and canonical inspect dispatch; legacy path unchanged. |
| `app_module/personalization_projection.py` | Typed canonical capture/receipt verification and shared projection finish; shared action/outcome resolution reused. |
| `scripts/qa_personalization_mainwindow_save_readback.py` | QA probe exercises canonical no-scope Qt readback and asserts it emits no personal ACK. |
| `tests/test_personalization_generation_cli.py` | Canonical chain, generated/persisted/delivered parity, typed receipt identity, orphan repair, changed-request refusal, ACK-CAS failure/retry, and legacy JSON retry fixtures. |
| `tests/test_personalization_save_integration.py` | Legacy compatibility fixture conversion, Qt no-scope/no-ACK, host/process canonical readback, writer failure immutability, ACK CAS/retry, watchlist soft failure. |
| `tests/test_personalization_read_service.py`, `tests/test_personalization_fit_runner.py` | Keep legacy personal rows as direct DTO/read fixtures after coordinator retirement. |
| `tests/test_recommendation_service_calibration_integration.py` | Preserve calibration receipt/save/readback regression with a direct legacy fixture and verify generated capture hash parity. |
| `tests/test_task_loop_03_contract.py` | Preserve legacy run-context/why-not DTO roundtrip fixture; remove superseded fake UI identity-only test. |
| `tests/test_r004_recommendation_persistence_characterization.py` | Move the old watchlist failure scenario to the canonical Qt integration fixture; keep remaining historical persistence characterization. |
| `tests/test_application_port_annotations.py`, `qa/full_app_healthcheck/test_inventory.py` | Remove references to the retired coordinator API/test. |
| `app_module/recommendation_save_coordinator.py`, `tests/test_recommendation_save_coordinator.py` | Delete the retired temporary coordinator and its API-only mirror tests. |
| `docs/07_guides/APPLICATION_MANUAL.md`, `FINAL_MIGRATION_SEQUENCE.md`, this report | Document operation and troubleshooting, close TMP-REC-03 ledger, and preserve compatibility/validation evidence. |

## Validation

All commands use the repo venv and a new TEMP directory per run; `PROFILE=test` isolates config roots. Commands/results after final pass will be frozen here.

| Command | Result |
|---|---|
| Fresh TEMP, `PROFILE=test`: focused 11-file personalization/R012/calibration/Qt suite listed below | `173 passed, 3 skipped, 2 warnings` in 27.99s. Warnings are existing pandas `FutureWarning`s from `decision_module/scoring_engine.py:437` in TASK-03 parameterized scoring cases. |
| Fresh TEMP, `PROFILE=test`: `pytest tests/test_personalization_generation_cli.py -q -o addopts=` | `9 passed` in 2.49s. |
| Fresh TEMP, `PROFILE=test`: required `pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | `84 passed` in 2.67s. |
| Required `python scripts/qa_validate_update_tab.py` | Passed: 25 checks, 0 failures, 4 skips. The script used its own temporary data/output tree and QA config, then wrote its QA report to the script's fixed local `output/qa/update_tab/VALIDATION_REPORT.md` destination. |
| Fresh TEMP, `PROFILE=test`: `python -m py_compile scripts/run_personalization_recommendation.py tests/test_personalization_generation_cli.py` after P2 | Passed; these are the only Python files changed by the P2 follow-up. The prior 13-file R015 compile gate passed before the follow-up. |
| Scoped mypy: `python -m mypy --follow-imports=skip app_module/personalization_projection.py app_module/personalization_read_service.py app_module/personalization_save_adapter.py scripts/run_personalization_recommendation.py` after P2 | `Success: no issues found in 4 source files`. |
| Broad mypy: `python -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime` after R023 final freeze and P2 | `Success: no issues found in 680 source files`. An earlier broad attempt before R023 repair reported three errors in non-R015 availability diagnostic callers; R023 repaired that contract and the required rerun was clean. |
| `git diff --check` after P2 | No whitespace errors; output contains only repository-wide LF→CRLF checkout warnings. |

PowerShell commands (the TEMP assignment was refreshed for each pytest/UI run):

```powershell
$env:TEMP = Join-Path $env:LOCALAPPDATA ('Temp\r015-final-' + [guid]::NewGuid().ToString('N'))
$env:PROFILE = 'test'
\.venv\Scripts\python.exe -m pytest tests\test_personalization_generation_cli.py tests\test_personalization_save_integration.py tests\test_personalization_read_service.py tests\test_personalization_projection.py tests\test_personalization_fit_runner.py tests\test_personalization_fit_cli.py tests\test_recommendation_service_calibration_integration.py tests\test_r012_recommendation_artifact_persistence.py tests\test_r004_recommendation_persistence_characterization.py tests\test_task_loop_03_contract.py tests\test_ui_qt_recommendation_execution.py -q -o addopts=
\.venv\Scripts\python.exe -m pytest tests\test_ui_qt_update_view_workbench.py -q -o addopts=
\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py
\.venv\Scripts\python.exe -m py_compile app_module\personalization_projection.py app_module\personalization_read_service.py app_module\personalization_save_adapter.py scripts\run_personalization_recommendation.py scripts\qa_personalization_mainwindow_save_readback.py tests\test_personalization_generation_cli.py tests\test_personalization_save_integration.py tests\test_personalization_read_service.py tests\test_personalization_fit_runner.py tests\test_recommendation_service_calibration_integration.py tests\test_task_loop_03_contract.py tests\test_application_port_annotations.py tests\test_r004_recommendation_persistence_characterization.py
\.venv\Scripts\python.exe -m mypy --follow-imports=skip app_module\personalization_projection.py app_module\personalization_read_service.py app_module\personalization_save_adapter.py scripts\run_personalization_recommendation.py
\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
\.venv\Scripts\python.exe -m pytest tests\test_personalization_generation_cli.py -q -o addopts=
```

## Acceptance and residual scope

- Production new-result personalization path does not read `producer.last_run_context`: satisfied by direct call-path scan and canonical CLI fake invocation.
- Save and ACK outcomes are separated and ACK is outside execution hash: satisfied by immutable generated capture hash checks plus ACK retry/CAS cases.
- Scope, clock, candidate/model/training/receipt identity parity: satisfied by callback/readback checks and negative typed projection fixture.
- Create-only, same-ID/hash retry, different-hash refusal, orphan/index recovery and legacy no-rewrite: covered by CLI and R012 focused tests.
- Qt, scheduled and personalization TMP-REC-03 caller closure: verified by source/import/caller searches and R013/R014 accepted reports; module deleted.
- ML risk: the implementation only consumes the candidate provenance and receipt already present in the invocation/execution. It never promotes, re-resolves an active model, retrains, changes calibration, or backfills candidate provenance. Test receipts are synthetic; no production training/promotion result is claimed.
- Remaining compatibility: legacy `RecommendationResultDTO` decoding/repositories remain for old artifacts and consumer fixtures; direct writes in QA scripts are synthetic compatibility probes. They are not live callers of the retired recommendation save coordinator.
- Rollback: if review finds identity/hash/CAS/parity failure, revert only the R015-owned hunks and restore the coordinator only if a remaining TMP-REC-03 caller is demonstrated. Preserve parallel-agent hunks in shared files. No rollback should overwrite legacy artifact bytes.

P2 implementation, focused tests, compile, scoped mypy, and broad mypy are complete. The earlier three broad-mypy errors belonged to concurrent R023 availability-diagnostic changes and were corrected by that owner before the clean run. The required UI gates were green before this CLI-only follow-up and no UI code changed in P2. Root final gate: bounded `ACCEPTED_SCOPE` for the synthetic engineering slice; TMP-REC-03 is retired as recorded in the migration sequence. This does not mark the combined 42-file suite as passed, release Wave 7–14, or establish formal data, natural-effect, production scheduler, training, or model-promotion acceptance.
