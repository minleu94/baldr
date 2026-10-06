from __future__ import annotations

import os
from pathlib import Path

import pytest

from data_module import monthly_revenue_snapshot_selection as snapshot_selection
from data_module.monthly_revenue_snapshot_selection import (
    inspect_monthly_revenue_snapshot,
    select_latest_monthly_revenue_snapshot,
)


def test_select_latest_snapshot_uses_period_not_file_size(tmp_path) -> None:
    snapshot_dir = tmp_path / "monthly_revenue_mops_snapshots"
    snapshot_dir.mkdir()
    old = snapshot_dir / "mops_monthly_revenue_snapshot_2014-04_2026-05_2026-06-16.csv"
    new = snapshot_dir / "mops_monthly_revenue_snapshot_2026-07_2026-07_2026-08-28.csv"
    old.write_text("x\n" * 500, encoding="utf-8")
    new.write_text("x\n", encoding="utf-8")

    assert select_latest_monthly_revenue_snapshot(snapshot_dir) == new.resolve()


def test_snapshot_selection_ignores_backup_and_exposes_filename_metadata(tmp_path) -> None:
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    backup = snapshot_dir / (
        "mops_monthly_revenue_snapshot_2026-07_2026-07_2026-08-28"
        ".before_apply.csv"
    )
    backup.write_text("x\n", encoding="utf-8")
    path = snapshot_dir / "mops_monthly_revenue_snapshot_2026-06_2026-06_2026-07-14.csv"
    path.write_text("x\n", encoding="utf-8")

    info = inspect_monthly_revenue_snapshot(path)
    assert info.start_period == "2026-06"
    assert info.end_period == "2026-06"
    assert info.fetch_date == "2026-07-14"
    assert select_latest_monthly_revenue_snapshot(snapshot_dir) == path.resolve()


def test_snapshot_selection_checks_legacy_and_one_level_capture_runs(tmp_path) -> None:
    snapshot_dir = tmp_path / "snapshots"
    legacy = snapshot_dir / "mops_monthly_revenue_snapshot_2026-06_2026-06_2026-07-14.csv"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("legacy\n", encoding="utf-8")
    captures = snapshot_dir / "captures"
    older_run = captures / f"run_2026-07-14_{'a' * 32}"
    newer_run = captures / f"run_2026-07-14_{'b' * 32}"
    older_run.mkdir(parents=True)
    newer_run.mkdir(parents=True)
    nested = older_run / "mops_monthly_revenue_snapshot_2026-07_2026-07_2026-08-28.csv"
    latest = newer_run / "mops_monthly_revenue_snapshot_2026-07_2026-07_2026-08-28.csv"
    nested.write_text("older run\n", encoding="utf-8")
    latest.write_text("newer run\n", encoding="utf-8")
    os.utime(nested, ns=(1_000_000_000, 1_000_000_000))
    os.utime(latest, ns=(2_000_000_000, 2_000_000_000))

    arbitrary_nested = captures / "unrecognized" / "mops_monthly_revenue_snapshot_2030-01_2030-01_2030-02-01.csv"
    arbitrary_nested.parent.mkdir()
    arbitrary_nested.write_text("must not scan arbitrary subtrees\n", encoding="utf-8")

    assert select_latest_monthly_revenue_snapshot(snapshot_dir) == latest.resolve()


def test_snapshot_selection_rejects_reparse_capture_parent_and_leaf(tmp_path) -> None:
    snapshot_dir = tmp_path / "snapshots"
    captures = snapshot_dir / "captures"
    captures.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    external_file = external / "mops_monthly_revenue_snapshot_2026-07_2026-07_2026-08-28.csv"
    external_file.write_text("external\n", encoding="utf-8")
    linked_capture = captures / f"run_2026-08-28_{'c' * 32}"
    try:
        linked_capture.symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlink/reparse creation is unavailable")

    assert select_latest_monthly_revenue_snapshot(snapshot_dir) is None

    linked_capture.unlink()
    actual_run = captures / f"run_2026-08-28_{'d' * 32}"
    actual_run.mkdir()
    linked_leaf = actual_run / external_file.name
    try:
        linked_leaf.symlink_to(external_file)
    except (OSError, NotImplementedError):
        pytest.skip("file symlink/reparse creation is unavailable")

    assert select_latest_monthly_revenue_snapshot(snapshot_dir) is None


def test_snapshot_selection_rejects_reparse_root_capture_parent_run_and_leaf(
    tmp_path, monkeypatch
) -> None:
    snapshot_dir = tmp_path / "snapshots"
    captures = snapshot_dir / "captures"
    run_dir = captures / f"run_2026-08-28_{'e' * 32}"
    run_dir.mkdir(parents=True)
    snapshot_file = run_dir / "mops_monthly_revenue_snapshot_2026-07_2026-07_2026-08-28.csv"
    snapshot_file.write_text("candidate\n", encoding="utf-8")

    for reparse_path in (snapshot_dir, captures, run_dir, snapshot_file):
        monkeypatch.setattr(
            snapshot_selection,
            "_is_reparse_point",
            lambda path, expected=reparse_path: Path(path) == expected,
        )
        assert select_latest_monthly_revenue_snapshot(snapshot_dir) is None

