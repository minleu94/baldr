from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from scripts import technical_indicator_repair_apply_guard as apply_guard
from scripts.technical_indicator_repair_dryrun import run_dryrun
from tests.test_technical_indicator_repair_dryrun import (
    _apply_fixture_price_state,
    _make_fixture_db,
    _write_fixture_caches,
    _write_fixture_price_plan,
    _write_fixture_price_receipt,
)


def _prepare_apply_fixture(tmp_path: Path) -> dict[str, object]:
    """Build the existing two-symbol fixture without touching formal data."""
    data_root = tmp_path / "data"
    db_path = data_root / "sqlite" / "twstock.db"
    db_path.parent.mkdir(parents=True)
    dates, canonical = _make_fixture_db(db_path)
    _apply_fixture_price_state(db_path, canonical)

    price_plan_path = tmp_path / "price_plan.json"
    _write_fixture_price_plan(price_plan_path, db_path, canonical)
    price_plan = json.loads(price_plan_path.read_text(encoding="utf-8"))
    price_backup = tmp_path / "price_backup.db"
    shutil.copy2(db_path, price_backup)
    price_receipt_path = tmp_path / "price_receipt.json"
    _write_fixture_price_receipt(
        price_receipt_path, db_path, price_plan, price_backup
    )
    _write_fixture_caches(data_root, ["1001", "2002"], dates)
    manifest_path = tmp_path / "dryrun.json"
    run_dryrun(
        db_path=db_path,
        overlay_path=price_plan_path,
        output_path=manifest_path,
        data_root=data_root,
        symbols=["1001", "2002"],
    )
    return {
        "data_root": data_root,
        "db_path": db_path,
        "price_plan_path": price_plan_path,
        "price_receipt_path": price_receipt_path,
        "manifest_path": manifest_path,
        "receipt_dir": tmp_path / "technical_receipt",
        "lock_path": tmp_path / "release" / ".ml_heavy_chain.lock",
    }


def _apply(fixture: dict[str, object]) -> dict[str, object]:
    return apply_guard.apply_technical_plan(
        dryrun_manifest_path=fixture["manifest_path"],  # type: ignore[arg-type]
        price_plan_path=fixture["price_plan_path"],  # type: ignore[arg-type]
        price_receipt_path=fixture["price_receipt_path"],  # type: ignore[arg-type]
        data_root=fixture["data_root"],  # type: ignore[arg-type]
        receipt_dir=fixture["receipt_dir"],  # type: ignore[arg-type]
        lock_path=fixture["lock_path"],  # type: ignore[arg-type]
        confirm=apply_guard.CONFIRM_TOKEN,
    )


def _cache_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.reader(stream))


def test_second_cache_replace_failure_restores_first_cache_and_leaves_db_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _prepare_apply_fixture(tmp_path)
    db_path = fixture["db_path"]  # type: ignore[assignment]
    data_root = fixture["data_root"]  # type: ignore[assignment]
    receipt_dir = fixture["receipt_dir"]  # type: ignore[assignment]
    db_before = db_path.read_bytes()
    cache_paths = {
        data_root / "technical_analysis" / "1001_indicators.csv",
        data_root / "technical_analysis" / "2002_indicators.csv",
        data_root / "meta_data" / "all_stocks_data.csv",
    }
    caches_before = {path: _cache_rows(path) for path in cache_paths}
    original_replace = apply_guard.os.replace

    def fail_second_cache_publish(
        source: str | bytes | Path, destination: str | bytes | Path
    ) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if (
            destination_path.resolve()
            == (data_root / "technical_analysis" / "2002_indicators.csv").resolve()
            and source_path.name == "technical_2002.staged.csv"
        ):
            raise OSError("injected second cache replace failure")
        original_replace(source, destination)

    monkeypatch.setattr(apply_guard.os, "replace", fail_second_cache_publish)
    with pytest.raises(OSError, match="second cache replace"):
        _apply(fixture)

    assert db_path.read_bytes() == db_before
    assert {path: _cache_rows(path) for path in cache_paths} == caches_before
    pending = json.loads((receipt_dir / "pending.json").read_text(encoding="utf-8"))
    assert pending["status"] == "cache_rolled_back_before_db_commit"
    assert pending["formal_data_written"] is False
    published = {
        str(item["path"]): item["status"]
        for item in pending["cache_files"]
        if isinstance(item, dict)
    }
    assert published[str((data_root / "technical_analysis" / "1001_indicators.csv").resolve())] == "published"


def test_final_receipt_failure_leaves_pending_and_resume_closes_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _prepare_apply_fixture(tmp_path)
    db_path = fixture["db_path"]  # type: ignore[assignment]
    receipt_dir = fixture["receipt_dir"]  # type: ignore[assignment]
    original_write = apply_guard._write_json_atomic

    def fail_final_receipt(
        path: Path, payload: dict[str, object], *, replace: bool
    ) -> None:
        if (
            path.name == "receipt.json"
            and payload.get("receipt_kind") == "technical_indicator_repair"
        ):
            raise OSError("injected final receipt write failure")
        original_write(path, payload, replace=replace)

    db_before = db_path.read_bytes()
    monkeypatch.setattr(apply_guard, "_write_json_atomic", fail_final_receipt)
    with pytest.raises(OSError, match="final receipt write"):
        _apply(fixture)

    pending_path = receipt_dir / "pending.json"
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    assert pending["status"] == "db_committed_receipt_pending"
    formal_data_written = pending["formal_data_written"]
    assert not (receipt_dir / "receipt.json").exists()
    assert db_path.read_bytes() != db_before

    monkeypatch.setattr(apply_guard, "_write_json_atomic", original_write)
    resumed = apply_guard.resume_technical_receipt(
        pending_path=pending_path,
        lock_path=fixture["lock_path"],  # type: ignore[arg-type]
        confirm=apply_guard.CONFIRM_TOKEN,
    )
    assert resumed["status"] == "applied"
    assert (receipt_dir / "receipt.json").is_file()
    closed_pending = json.loads(pending_path.read_text(encoding="utf-8"))
    assert closed_pending["status"] == "receipt_written"
    assert formal_data_written is True


def test_cache_expected_null_drift_is_rejected(tmp_path: Path) -> None:
    cache_path = tmp_path / "1001_indicators.csv"
    cache_path.write_text(
        "日期,證券代號,SMA30\n20260520,1001,7.0\n",
        encoding="utf-8",
    )
    before = cache_path.read_bytes()

    with pytest.raises(
        apply_guard.TechnicalApplyError, match="cache before-cell drift"
    ):
        apply_guard._stage_cache_file(
            path=cache_path,
            operations=[
                {
                    "symbol": "1001",
                    "date": "20260520",
                    "column": "SMA30",
                    "column_ordinal": 0,
                    "new": 2.0,
                    "cache_expected_old": None,
                }
            ],
            staging_dir=tmp_path / "staging",
            label="null-drift",
        )

    assert cache_path.read_bytes() == before
    assert not (tmp_path / "staging" / "null-drift.staged.csv").exists()


def test_resume_restores_published_caches_after_process_crash_before_db_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _prepare_apply_fixture(tmp_path)
    db_path = fixture["db_path"]  # type: ignore[assignment]
    data_root = fixture["data_root"]  # type: ignore[assignment]
    receipt_dir = fixture["receipt_dir"]  # type: ignore[assignment]
    cache_paths = {
        data_root / "technical_analysis" / "1001_indicators.csv",
        data_root / "technical_analysis" / "2002_indicators.csv",
        data_root / "meta_data" / "all_stocks_data.csv",
    }
    db_before = db_path.read_bytes()
    caches_before = {path: _cache_rows(path) for path in cache_paths}
    original_replace = apply_guard.os.replace

    def crash_before_second_cache_publish(
        source: str | bytes | Path, destination: str | bytes | Path
    ) -> None:
        if (
            Path(destination).resolve()
            == (data_root / "technical_analysis" / "2002_indicators.csv").resolve()
            and Path(source).name == "technical_2002.staged.csv"
        ):
            raise KeyboardInterrupt("simulated process crash")
        original_replace(source, destination)

    monkeypatch.setattr(apply_guard.os, "replace", crash_before_second_cache_publish)
    with pytest.raises(KeyboardInterrupt, match="simulated process crash"):
        _apply(fixture)

    pending_path = receipt_dir / "pending.json"
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    assert pending["status"] == "cache_publishing"
    assert pending["formal_data_written"] is False

    monkeypatch.setattr(apply_guard.os, "replace", original_replace)
    recovered = apply_guard.resume_technical_receipt(
        pending_path=pending_path,
        lock_path=fixture["lock_path"],  # type: ignore[arg-type]
        confirm=apply_guard.CONFIRM_TOKEN,
    )

    assert recovered["status"] == "recovered_before_db_commit"
    assert db_path.read_bytes() == db_before
    assert {path: _cache_rows(path) for path in cache_paths} == caches_before
    closed = json.loads(pending_path.read_text(encoding="utf-8"))
    assert closed["status"] == "recovered_before_db_commit"
    assert closed["formal_data_written"] is False
