# Paper event source capture failure diagnostics QA — 2026-10-02

## Scope and finding

The daily paper event capture parsed an HTTP response before persisting its bytes. A rejected status, invalid source URL, truncated body, parse error, or timeout therefore left little or no evidence of the source attempt. The scheduler also removed temporary evidence before archiving it and reported temporary cleanup as successful even when cleanup could fail.

This change is limited to the capture boundary and its daily scheduler. It records bounded response bytes and a typed attempt receipt in isolated diagnostics before parsing or temporary cleanup. The diagnostics tree is separate from accepted durable captures and is not read as an EOD-usable capture or manifest.

## Behavior covered

- Response bytes are written create-only before response validation and parsing. Receipts include actual request start/completion timestamps, HTTP and content metadata where available, byte count, SHA-256, parser status, and typed failure details.
- Timeouts and other failures before a body is available still produce a request-attempt receipt and explicitly record that no raw body was received.
- Rejected or truncated responses are archived with their receipt before temporary state is cleaned. If archival fails, temporary state is preserved and the scheduler reports that state. Cleanup failures are surfaced in status.
- Retries keep each rejected attempt in a unique diagnostic directory. A later valid response can still become the only durable capture; rejected bytes do not enter the durable manifest.
- Existing successful parser output, canonical capture body, and hash custody remain unchanged.

## Verification

Focused verification on 2026-10-02:

- `tests/test_paper_formal_daily_source_chain.py`: 31 passed, 1 skipped, including the exact `"0000"` parser matrix and isolated EOD producer-to-durable-to-consumer flow.
- `tests/test_pit_preopen_schedule.py`: 23 passed, 1 skipped.
- Focused capture/replay selection: 11 passed.
- `mypy data_module/paper_event_source_capture.py scripts/scheduled/run_paper_event_source_capture_daily.py`: passed.
- `py_compile` for changed source, scheduler, and test files: passed.
- Capture-scope diff whitespace check: passed. The repository-wide check reports pre-existing trailing whitespace/EOF formatting in unrelated `app_module/update_service.py` and `docs/06_qa/ML_REVISION_AWARE_REBUILD_EXECUTION_PLAN_20261001.md`.

The existing isolated-chain fixture was using `scheduled_rec_*.json`, while the production exporter and isolated runner both use `paper_frozen_*.json`. Only the stale fixture basename was corrected; its payload identity and ID/hash/custody assertions remain intact.

## Before snapshots and acceptance boundary

Before-edit byte copies are retained under `output/qa/integration_20261002/paper_event_capture_failure_before/` and were hash-checked against the original files. This directory is local QA evidence and is not a source artifact.

These results establish engineering behavior through isolated tests. A natural scheduled capture run and its external source response have not been performed or accepted in this change; controlled operational acceptance remains with the repository owner.

## Observed TWSE status spelling

On 2026-10-02 at 23:18:22 UTC, a separately bounded diagnostic request returned HTTP 200 from the fixed MIS request URL. Its JSON body had exact string fields `rtcode: "0000"` and `rtmessage: "OK"`. The retained diagnostic sample is `output/qa/integration_20261002/source_responses_20261002T231812713663Z/twse_mis.bin` (SHA-256 `f659f3005644427e2fd83ff14424a26fee6cc7ec5542c3f596531b69b6eaf438`). Its quotes were timestamped after regular session and belong to 2026-10-02 while acquisition was on 2026-10-03 Taipei time. It is parser evidence only; it was not promoted to a session capture or durable source.

The shared `_parse_twse_mis_raw_rows` contract now accepts only exact string status values `"000"`, `"0"`, and the observed `"0000"`; non-string values and all other strings remain rejected. Existing parser version and durable receipt format are unchanged so previously valid v1 captures remain readable. The isolated EOD producer-to-durable-to-consumer regression now exercises `"0000"`; the prior string spellings and negative type/status matrix remain covered.

## Follow-up: retry cleanup failures remain visible

The bounded Sol High review reproduction at `output/qa/integration_20261002/phase1_patch_review/cleanup_reproduction.json` showed a rejected first attempt whose diagnostic was saved but whose TEMP cleanup returned `preserved` with a `PermissionError`. A second attempt then produced a readback-verified durable capture, while the scheduler incorrectly returned `source_capture_durable`, an empty blocker list, and exit code 0.

The scheduler now aggregates cleanup failures across all attempts. If a later attempt succeeds, its accepted durable capture, manifest, and raw response remain available, while the overall status is `blocked`, `capture_status` remains `source_capture_durable`, the wrapper returns exit code 2, and the blocker and `temporary_cleanup_errors` identify each attempt cleanup failure. The overall temporary-cleanup state reports `partial_failure` when some attempt roots were removed and another was preserved; preserved roots remain listed. Terminal capture failures also retain per-attempt cleanup blockers. Retry eligibility, parser rules, source window, and durable capture custody are unchanged.

Verification on 2026-10-02:

- The new `test_scheduled_event_capture_cleanup_error_survives_successful_retry` reproduced exit code 0 before the fix, then passed with the expected blocked status and exit code 2. It verifies the first diagnostic/raw bytes and preserved TEMP root, the second attempt's successful cleanup, the durable manifest/raw response, aggregate blocker, and exact status-file readback.
- `tests/test_paper_formal_daily_source_chain.py`: 32 passed, 1 skipped.
- `mypy scripts/scheduled/run_paper_event_source_capture_daily.py`: passed.
- `py_compile` for the scheduler and source-chain test: passed.
- Scoped `git diff --check` for the scheduler, source-chain test, and QA note: passed; Git only reported its existing LF-to-CRLF conversion warning for the two Python files.
- The current source, test, QA note, review reproduction JSON, and review pytest log were copied byte-for-byte before editing under `output/qa/integration_20261002/capture_cleanup_truthfulness_before/`; `before_manifest.json` records their SHA-256 hashes and sizes. The review JSON and log remain unchanged.

This verifies isolated wrapper behavior only. Natural scheduler execution and operational acceptance remain with the repository owner.
