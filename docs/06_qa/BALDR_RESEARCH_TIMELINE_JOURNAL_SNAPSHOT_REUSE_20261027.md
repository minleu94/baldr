# Research Timeline Journal Snapshot Reuse QA

## Scope

Research Timeline refresh previously read and parsed the same Journal JSONL separately for the manual, price, report, and theme lanes. When the four production readers share the same `JournalService`, a refresh now takes one immutable Journal history snapshot and projects each lane from those in-memory records. The report reader still performs its lane-specific validation; price and theme retain their continuity-revision checks; manual entries retain the existing active-entry projection and default portfolio filter.

If a shared snapshot cannot be obtained, refresh falls back to the existing independent lane readers. Errors raised while decoding an individual lane remain isolated and are shown in the existing status text. Custom readers backed by a different `JournalService` keep their original independent read paths. The display limit, ordering, references, warnings, source identities, cancellation checks, and UI worker path are unchanged.

## Verification

- `tests/test_research_timeline_service.py`, `tests/test_ui_qt_research_timeline_view.py`, the three typed-note suites, personal Journal storage, and required Workbench UI regression: **214 passed**.
- Targeted mypy: 6 changed source modules clean. `py_compile`: 10 changed Python files passed.
- Integration test compared a four-reader legacy read against the shared-history path with 600 legacy entries and a saved report note. It confirmed the same visible entries, warning state, and truncation flag while JSONL reads fell from 4 to 1.
- UI A/B used 6,000 synthetic local Journal entries, two warm-ups per path, and 30 alternating samples per path. Timing ran from `ResearchTimelineView.refresh()` through `resultReady` after `_receive` applied the table model, with Qt offscreen. Legacy p50/p95: **610.6/737.5 ms**; shared snapshot p50/p95: **335.1/436.3 ms**. Median latency fell **45.1%**; read count fell 4→1. All outputs matched SHA-256 `fd31d3106ea1626c158df11952e309c0d352f4a9e75a47fece987c7ed2914ce9`.
- The benchmark measures a local synthetic JSONL workload and offscreen Qt. It does not measure production Journal size, native Windows painting, owner acceptance, or DannyQuant website latency.

## Evidence

- Focused and mandatory regression receipt: `output/tasks/research-timeline-journal-snapshot-20261027/evidence/single_owned_qa_e8f7485c936f42aeab440c01cf9e3c78/receipt.json`.
- A/B timing and read-count receipt: `output/tasks/research-timeline-journal-snapshot-20261027/evidence/single_owned_qa_0f4a16300abf41be897030263d38c5dd/receipt.json`.
- Targeted mypy and compile receipt: `output/tasks/research-timeline-journal-snapshot-20261027/evidence/single_owned_qa_6c0d4478a2f44abb8df2faca22b6ab6d/receipt.json`.

This engineering result changes no Journal payload, source qualification, PIT status, saved research content, or product Gate.
