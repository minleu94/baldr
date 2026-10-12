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

On this Windows host, pytest's default temp directory under `C:\Users\archi\AppData\Local\Temp` is outside the no-follow file-handle permissions needed by recommendation artifact tests. The full focused suites passed with isolated `--basetemp` directories under the repository's ignored QA output. Pytest also reported that it could not update the existing `.pytest_cache` due to permission restrictions.

Before-edit bytes are retained under `output/qa/integration_20261002/evidence_readonly_date_before/` and hash-checked before this patch. No formal source database was changed by these tests. Root-owned controlled operational readback after the fix remains pending; this note records engineering tests only.

## 2026-10-12 實際產物讀回補記

以下是 2026-10-12 的日期化補記；上文的 `pending` 保留其 10/02 記錄時點，不代表本次查核尚未讀回。完整治理議題裁決見[本輪治理 QA 收據](DOCUMENT_GOVERNANCE_ISSUE_RESOLUTION_20261012.md)。

- 正式輸出根下的 `D:\Min\Python\Project\FA_Data\output\scheduled\evidence_pipeline_dry_run\latest_status.json` 為 545,899 bytes，SHA-256 `69CC0C025E67998A9C4A5768CDDEAE8EC05BA1D7C4F5AD49F55D2956EEC6552F`。該 wrapper status 為 `failed`、exit code 2，沒有獨立 `run_id` 欄位。內嵌 Exit 子程序回傳 0，typed status 為 `degraded`，requested／as-of date 均為 `2026-10-12`，`historical_backfill=false`；子程序 exit 0 不會覆蓋外層 failed。
- Exit artifact `D:\Min\Python\Project\FA_Data\output\exit_effectiveness\20261012.json` 為 2,816 bytes，SHA-256 `B0EEFC8D9B75E0E075C1080DA3E83A7837E89E904009A9597994338A1D9BF31C`，與 wrapper 及 producer receipt 所列 bytes hash 相符。原始 JSON `generated_at` 字串為 `2026-10-12T12:15:04.412987+00:00`。Artifact status 為 `degraded`，`transition_count=0`、warning `no_exit_transition_rows`、`research_only=true`；沒有正式效果 credit、Exit 有效性結論、自動退出或 broker order。
- 同次 log `D:\Min\Python\Project\FA_Data\output\scheduled\evidence_pipeline_dry_run\20261012_051502_214993_exit_effectiveness.log` 為 3,620 bytes，SHA-256 `09B0A3835C418795E10CF37FB7EB2021A58940CB746DCC9BB263653CFE1A7A37`，記錄相同 artifact path、hash、as-of date、evidence hash `c10c82eb0a7500eb8105f41623bb8e0f62fba21110fb3d115fbb67b4c750a1b4` 與 degraded status。Wrapper latest 沒有獨立 run ID，因此精確 hash／日期 readback 不等於獨立 trigger/run attestation，也不改變 degraded／failed 結果。
- Root-host 的 Exit 窄契約驗證為 38 passed、1 個環境 symlink skip、28 deselected（1.56 秒）。這只證明限定工程契約回歸；不把 synthetic tests 或 artifact identity readback 升格成自然／真人 outcome、資格或產品接受。
