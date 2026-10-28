# Storage Overview metadata reuse QA

## Scope and change

`app_module/storage_overview.py::_is_reparse` now classifies symlinks from the existing `DirEntry.stat(follow_symlinks=False)` result and Windows reparse-point attribute. This removes one repeated metadata lookup per entry while preserving the existing inventory result and safety boundary. The benchmark used only a temporary synthetic tree.

## A/B result

- Fixture: one synthetic Trial version with 4,000 files and one Windows directory junction to a target outside the inventoried root.
- Warm-up: 4 baseline/candidate pairs. Measurement: 40 interleaved pairs.
- Complete `StorageOverview` digest matched: `8e6aa63c3bb73df1a3a5f0f553c0e76469e727459127ac7faea731a3d4dd3caa`.
- Instrumented metadata operations: `DirEntry.stat` stayed at 4,002 calls; `Path.is_symlink` fell from 4,003 calls to 0.
- Uninstrumented p50: 90.8447 ms baseline, 12.1794 ms candidate (−86.59%).
- Uninstrumented nearest-rank p95: 97.8380 ms baseline, 14.1697 ms candidate (−85.52%). Both exceeded the preset 5% improvement threshold.

Detailed samples: `output/tasks/storage-overview-stat-reuse-20261027/evidence/benchmark_storage_stat_reuse_result.json`.

## Regression and receipts

- Focused `tests/test_storage_overview.py`: 14 passed, 1 skipped. The skip is the existing real-symlink test because this Windows account lacks symlink privilege (`WinError 1314`). The A/B fixture exercised a directory junction; the new metadata classifier test covers `S_IFLNK`, the reparse attribute and an ordinary file without that privilege.
- A/B receipt: `output/tasks/storage-overview-stat-reuse-20261027/evidence/single_owned_qa_a5ed46cd945b4b0b891cad6b36ad0754/receipt.json`.
- Focused regression receipt: `output/tasks/storage-overview-stat-reuse-20261027/evidence/single_owned_qa_781895975c0946c68a28d8cd4b8390c0/receipt.json`.
- Two runner bootstrap attempts and two reparse-fixture attempts failed before producing benchmark results; their receipts remain preserved in the task evidence.
- Scoped document-control check of the new QA/index/Feature Map paths passed. The default 67-source task-wide check still reports 63 pre-existing anchor/output-path issues; no new link from this change was listed. `git diff --check` passed for changed tracked files, and new QA files have no trailing whitespace.

## Limits

This is a local temporary-filesystem result, not a production, formal-data, network or whole-application latency claim. A real symbolic link could not be created under this account. The metadata semantics and output digest were verified on the synthetic junction fixture.

