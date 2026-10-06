# Evidence dry-run read-only and Exit business-date QA — 2026-10-02

## Confirmed issues

The controlled Evidence dry-run changed the source SQLite file despite creating no evidence events or outcomes. `EvidencePipelineRunner._build_importers` constructed `DecisionDeskSnapshotRepository` with its default writable mode; construction ensures schema and replaces its schema-version row. The dry-run date also came from the Pacific wrapper clock, while the Exit producer correctly derives its effective date from its own real UTC clock converted to Taipei. On a Pacific afternoon, the dates can differ, causing the strict artifact verifier to reject an otherwise current Exit artifact.

## Changes

All `EvidenceEventRepository` instances created by the runner now receive `read_only=True` during a dry-run, covering capture, outcome calculation, and summary. `_build_importers` receives the run mode and opens `DecisionDeskSnapshotRepository` read-only for dry-runs. The confirmed/write path retains writable repositories.

The wrapper still keeps its Pacific `decision_date` for Evidence and report naming. When Exit is requested, its artifact filename is derived from the wrapper's real aware UTC clock converted to Taipei. The child CLI and strict verifier remain unchanged: there is no historical date switch, the producer keeps its real UTC `generated_at`, and verifier checks the child run's Taipei date, output filename, hashes, and artifact bytes. `latest_status.json` now records both the requested Exit as-of date and the producer's actual as-of date, and labels a date that differs from Evidence `decision_date` as `current_outcome_sidecar`.

## Verification

- `tests/test_evidence_pipeline_runner.py`: 20 passed. Its new regression creates an isolated SQLite source, snapshots the complete database bytes and every `schema_version` row, runs the dry-run path with an explicit source DB, and asserts both are byte/value-identical afterward.
- `tests/test_scheduled_evidence_pipeline_dry_run_wrapper.py`: 39 passed, 1 skipped. Coverage includes a normal 05:15 Pacific same-date run and a Pacific/UTC October 2 to Taipei October 3 divergence, true UTC `generated_at`, Taipei-named artifact, status sidecar role, and rejection of UTC/Pacific filenames or as-of dates by the unchanged verifier.
- `mypy app_module/evidence_pipeline_runner.py scripts/scheduled/run_scheduled_evidence_pipeline_dry_run.py`: passed.
- `py_compile` for the changed runner, wrapper, and tests: passed.

On this Windows host, pytest's default temp directory under `<USER_HOME>\AppData\Local\Temp` is outside the no-follow file-handle permissions needed by recommendation artifact tests. The full focused suites passed with isolated `--basetemp` directories under the repository's ignored QA output. Pytest also reported that it could not update the existing `.pytest_cache` due to permission restrictions.

Before-edit bytes are retained under `output/qa/integration_20261002/evidence_readonly_date_before/` and hash-checked before this patch. No formal source database was changed by these tests. Root-owned controlled operational readback after the fix remains pending; this note records engineering tests only.
