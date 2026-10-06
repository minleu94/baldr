from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import pytest

import data_module.ml_daily_price_revision_research_dataset as research_dataset
from data_module.ml_daily_price_revision_research_dataset import ResearchDatasetError
from data_module.ml_daily_price_revision_gate import (
    DailyPriceSourceRevisionError,
    check_daily_price_source_revision,
)
from data_module.ml_daily_price_revision_recovery import RECOVERY_SCHEMA
from data_module.ml_daily_price_revision_technical_snapshot import (
    EVIDENCE_SCHEMA,
    PRICE_RECEIPT_SCHEMA,
    TECHNICAL_RECEIPT_SCHEMA,
    _canonical_hash,
)

DATE = "20260520"
OBSERVED = "2026-09-23T12:00:00+00:00"
SYNTHETIC_COVERAGE = {
    "symbols": 2,
    "affected_rows": 2,
    "indicator_after_cells": 2,
    "source_after_cells": 0,
    "after_cells": 2,
}


def _hash(path: Path) -> str:
    return research_dataset._hash_file(path)


def _seal(payload: dict[str, object], field: str) -> dict[str, object]:
    sealed = dict(payload)
    sealed[field] = _canonical_hash(payload)
    return sealed


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.setattr(research_dataset, "EXPECTED_COVERAGE", SYNTHETIC_COVERAGE)
    monkeypatch.setattr(research_dataset, "EXPECTED_UNTOUCHED_CELLS", 6)
    source_root = tmp_path / "source"
    repair_dir = source_root / "output" / "scheduled" / "daily_price_repair_receipts" / DATE / "historical_price_spike_20260921"
    run_root = source_root
    evidence_dir = run_root / "evidence"
    for directory in (repair_dir, evidence_dir, source_root / "sqlite"):
        directory.mkdir(parents=True, exist_ok=True)

    database = source_root / "sqlite" / "twstock.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE daily_prices (
            日期 TEXT NOT NULL, 證券代號 TEXT NOT NULL,
            開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER,
            PRIMARY KEY (日期, 證券代號));
        CREATE TABLE technical_indicators (
            日期 TEXT NOT NULL, 證券代號 TEXT NOT NULL,
            RSI REAL, MACD REAL, ADX REAL, PRIMARY KEY (日期, 證券代號));
        """
    )
    prices = (
        (DATE, "0050", "93", "93.5", "92.45", "92.5", 121650308),
        (DATE, "2330", "2050", "2060", "2040", "2055", 1000000),
    )
    connection.executemany("INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?)", prices)
    connection.executemany(
        "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)",
        ((DATE, "0050", 50.0, 1.2, 22.0), (DATE, "2330", 55.0, 3.0, 30.0)),
    )
    connection.commit()
    connection.close()

    rows = []
    for day, symbol, open_value, high, low, close, volume in prices:
        after = {
            "日期": day, "證券代號": symbol, "開盤價": open_value,
            "最高價": high, "最低價": low, "收盤價": close,
            "成交股數": str(volume),
        }
        rows.append({"date": day, "symbol": symbol, "before": {"收盤價": "1"}, "after": after})
    corrected_at = "2026-09-22T00:30:49.544569-07:00"
    price_final = _seal(
        {
            "schema_version": PRICE_RECEIPT_SCHEMA,
            "receipt_kind": "historical_price_spike_repair",
            "status": "applied",
            "source_date": DATE,
            "corrected_at": corrected_at,
            "available_at": None,
            "allowlist_count": len(rows),
            "allowlist_hash": "sha256:" + "a" * 64,
            "plan_hash": "sha256:" + "b" * 64,
            "historical_decision_time_available": False,
            "formal_training_allowed": False,
            "promotion_eligible": False,
            "rows": rows,
        },
        "receipt_sha256",
    )
    price_final_path = repair_dir / "receipt.json"
    _write_json(price_final_path, price_final)
    price_pending_path = repair_dir / "pending.json"
    _write_json(
        price_pending_path,
        {
            "schema_version": PRICE_RECEIPT_SCHEMA,
            "receipt_kind": "historical_price_spike_repair_pending",
            "status": "applied_receipt_written",
            "source_date": DATE,
            "created_at": "2026-09-22T00:30:49.586086-07:00",
            "available_at": None,
            "allowlist_count": len(rows),
            "allowlist_hash": price_final["allowlist_hash"],
            "plan_hash": price_final["plan_hash"],
        },
    )

    backup = source_root / "technical_before.db"
    backup.write_bytes(b"synthetic technical before snapshot")
    manifest = source_root / "repair_manifest.json"
    manifest.write_text('{"synthetic":true}\n', encoding="utf-8")
    price_body_hash = str(price_final["receipt_sha256"])
    technical_pending_path = repair_dir / "technical_pending.json"
    _write_json(
        technical_pending_path,
        {
            "schema_version": TECHNICAL_RECEIPT_SCHEMA,
            "receipt_kind": "technical_indicator_repair_pending",
            "status": "receipt_written",
            "source_date": DATE,
            "technical_backup_sha256": _hash(backup),
            "dryrun_manifest_sha256": _hash(manifest),
            "price_receipt": price_body_hash,
        },
    )
    operations = {
        "operations": 2,
        "technical_indicator_cells": 2,
        "technical_source_cells": 0,
        "technical_source_rows": 2,
    }
    technical = _seal(
        {
            "schema_version": TECHNICAL_RECEIPT_SCHEMA,
            "receipt_kind": "technical_indicator_repair",
            "status": "applied",
            "source_date": DATE,
            "available_at": None,
            "formal_training_allowed": False,
            "promotion_eligible": False,
            "price_receipt_sha256": price_body_hash,
            "technical_backup_sha256": _hash(backup),
            "dryrun_manifest_sha256": _hash(manifest),
            "operations_summary": operations,
            "after_cells_sha256": "sha256:" + "c" * 64,
        },
        "receipt_sha256",
    )
    technical_path = repair_dir / "technical_receipt.json"
    _write_json(technical_path, technical)

    diff_path = evidence_dir / "recovery_cell_diff.jsonl"
    diff_path.write_text('{"synthetic":"cell diff"}\n', encoding="utf-8")
    row_hashes_path = evidence_dir / "affected_row_hashes.jsonl"
    row_hashes_path.write_text('{"synthetic":"row hashes"}\n', encoding="utf-8")
    source_hashes = {
        "price_pending_file": _hash(price_pending_path),
        "price_receipt_file": _hash(price_final_path),
        "technical_pending_file": _hash(technical_pending_path),
        "technical_receipt_file": _hash(technical_path),
        "dryrun_manifest": _hash(manifest),
        "technical_before_backup": _hash(backup),
        "run02_before": _hash(database),
    }
    recovery = _seal(
        {
            "schema_version": RECOVERY_SCHEMA,
            "status": "passed",
            "mode": "isolated_research_snapshot_recovery",
            "database_path": str(database.resolve()),
            "allowed_output_root": str(run_root.resolve()),
            "database_sha256_after": _hash(database),
            "database_size_after": database.stat().st_size,
            "formal_data_written": False,
            "formal_training_allowed": False,
            "historical_pit_eligible": False,
            "promotion_eligible": False,
            "research_candidate_only": True,
            "coverage": SYNTHETIC_COVERAGE,
            "input_hashes": source_hashes,
            "pending_state": {
                "technical_status": "receipt_written",
                "price_status": "applied_receipt_written",
                "technical_pending_file_sha256": source_hashes["technical_pending_file"],
                "price_pending_file_sha256": source_hashes["price_pending_file"],
                "changed": False,
            },
            "rows": {
                "affected_rows": 2,
                "plan_external_before_sha256": "sha256:" + "d" * 64,
                "plan_external_after_sha256": "sha256:" + "d" * 64,
                "plan_external_rows": 0,
                "total_table_rows": 2,
            },
            "cell_diff": {"after_cells": 2, "untouched_cells": 6},
            "post_commit_verification": {
                "after_cells": 2, "after_matches": 2, "after_mismatches": 0,
                "missing_current_rows": 0, "untouched_cells": 6, "untouched_mismatches": 0,
            },
            "evidence_files": {
                "cell_diff": {"path": str(diff_path.resolve()), "sha256": _hash(diff_path),
                              "size_bytes": diff_path.stat().st_size},
                "affected_row_hashes": {"path": str(row_hashes_path.resolve()),
                                        "sha256": _hash(row_hashes_path),
                                        "size_bytes": row_hashes_path.stat().st_size},
            },
        },
        "receipt_sha256",
    )
    recovery_path = evidence_dir / "recovery_receipt.json"
    _write_json(recovery_path, recovery)

    actual_prices = [
        {"date": day, "symbol": symbol, "open": open_value, "high": high,
         "low": low, "close": close, "volume_shares": str(volume)}
        for day, symbol, open_value, high, low, close, volume in prices
    ]
    technical_rows = [
        {"日期": DATE, "證券代號": "0050", "ADX": "22", "MACD": "1.2", "RSI": "50"},
        {"日期": DATE, "證券代號": "2330", "ADX": "30", "MACD": "3", "RSI": "55"},
    ]
    input_paths = {
        "database_snapshot": database,
        "technical_pending": technical_pending_path,
        "technical_receipt": technical_path,
        "price_pending": price_pending_path,
        "price_receipt": price_final_path,
        "technical_backup": backup,
        "dryrun_manifest": manifest,
    }
    sidecars = {
        suffix: {"exists": Path(str(database) + suffix).exists(), "size_bytes": 0}
        for suffix in ("-wal", "-shm")
    }
    verifier_module = Path(research_dataset.__file__).resolve().with_name(
        "ml_daily_price_revision_technical_snapshot.py"
    )
    verification = _seal(
        {
            "schema_version": EVIDENCE_SCHEMA,
            "status": "passed",
            "purpose": "late_obtained_research_source_evidence_only",
            "formal_pit_gate_changed": False,
            "historical_available_at": None,
            "availability_status": "late_obtained",
            "snapshot": {
                "path": str(database.resolve()),
                "sha256_before": _hash(database),
                "sha256_after": _hash(database),
                "size_bytes": database.stat().st_size,
                "sidecars_before": sidecars,
                "sidecars_after": sidecars,
            },
            "inputs": {
                name: {"path": str(path.resolve()), "sha256": _hash(path),
                       "size_bytes": path.stat().st_size}
                for name, path in input_paths.items()
            },
            "receipt_identity": {
                "technical_receipt_file_sha256": _hash(technical_path),
                "technical_receipt_body_sha256": technical["receipt_sha256"],
                "price_receipt_file_sha256": _hash(price_final_path),
                "price_receipt_body_sha256": price_final["receipt_sha256"],
                "technical_price_receipt_identity_match": True,
            },
            "coverage": {
                **SYNTHETIC_COVERAGE,
                "after_matches": 2,
                "after_mismatches": 0,
                "missing_current_rows": 0,
                "untouched_cells": 6,
                "untouched_mismatches": 0,
            },
            "provenance": {
                "tracked_verifier_module_sha256": _hash(verifier_module),
                "original_qa_verifier_imported": False,
                "rerun_uses_tracked_verifier_module": True,
            },
        },
        "evidence_sha256",
    )
    verification_path = evidence_dir / "technical_snapshot_verification.json"
    _write_json(verification_path, verification)
    return {
        "database": database,
        "pending": price_pending_path,
        "final": price_final_path,
        "technical_pending": technical_pending_path,
        "technical": technical_path,
        "backup": backup,
        "manifest": manifest,
        "recovery": recovery_path,
        "verification": verification_path,
        "output": tmp_path / "research-output",
        "actual_prices": actual_prices,
        "actual_technical": technical_rows,
    }


def _build(paths: dict[str, object], *, observed_at: str = OBSERVED):
    return research_dataset.build_revision_aware_research_dataset(
        database_path=paths["database"],
        pending_receipt_path=paths["pending"],
        final_receipt_path=paths["final"],
        technical_pending_path=paths["technical_pending"],
        technical_receipt_path=paths["technical"],
        technical_backup_path=paths["backup"],
        dryrun_manifest_path=paths["manifest"],
        recovery_receipt_path=paths["recovery"],
        technical_verification_path=paths["verification"],
        output_root=paths["output"],
        observed_at=observed_at,
    )


def test_builds_verified_late_obtained_source_and_keeps_training_gates_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths = _fixture(tmp_path, monkeypatch)
    original_db = paths["database"].read_bytes()
    source = _build(paths)
    manifest = json.loads(source["manifest_path"].read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in source["rows_path"].read_text(encoding="utf-8").splitlines()
    ]
    assert source["row_count"] == 2
    assert manifest["authoritative_identity"]["run_id"] == source["run_id"]
    assert manifest["coverage"]["daily_price_rows_matched"] == 2
    assert manifest["coverage"]["technical_rows_matched"] == 2
    assert manifest["price_row_quality"] == {
        "total_rows": 2,
        "complete_ohlc_rows": 2,
        "missing_ohlc_rows": 0,
        "missing_ohlc_symbols": [],
        "excluded_from_fit_reason_counts": {"missing_ohlc_source": 0},
    }
    assert manifest["source_revision"]["pending_marker_preserved"] is True
    assert manifest["source_revision"]["pending_marker_still_blocks_formal_pit"] is True
    assert manifest["eligibility"]["research_only"] is True
    assert manifest["eligibility"]["formal_training_allowed"] is False
    assert manifest["eligibility"]["formal_oos_allowed"] is False
    assert manifest["artifact"]["model_training_input_compatible"] is False
    assert manifest["artifact"]["feature_contract_status"] == "not_assessed"
    assert manifest["artifact"]["label_maturity_status"] == "not_materialized"
    assert "revision_aware_research_lineage" not in json.loads(
        paths["technical"].read_text(encoding="utf-8")
    )
    assert all(row["source_revision"]["historical_available_at"] is None for row in rows)
    assert all(row["source_revision"]["availability_status"] == "late_obtained" for row in rows)
    assert all(row["label_status"] == "not_materialized" for row in rows)
    assert all(row["technical_indicators"]["RSI"] for row in rows)
    assert paths["database"].read_bytes() == original_db
    with pytest.raises(DailyPriceSourceRevisionError, match="blocks this PIT prefix"):
        check_daily_price_source_revision(
            database_path=paths["database"], decision_date="2026-09-23", symbols=("0050",)
        )


def test_recovery_or_verifier_evidence_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths = _fixture(tmp_path, monkeypatch)
    recovery_path = paths["recovery"]
    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
    recovery["status"] = "failed"
    _write_json(recovery_path, recovery)
    with pytest.raises(ResearchDatasetError, match="body hash does not match"):
        _build(paths)
    assert not paths["output"].exists()

    paths = _fixture(tmp_path / "second", monkeypatch)
    verification_path = paths["verification"]
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    verification["status"] = "failed"
    _write_json(verification_path, verification)
    with pytest.raises(ResearchDatasetError, match="body hash does not match"):
        _build(paths)
    assert not paths["output"].exists()


def test_price_source_mismatch_and_pre_correction_observation_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths = _fixture(tmp_path, monkeypatch)
    connection = sqlite3.connect(paths["database"])
    connection.execute(
        'UPDATE daily_prices SET "收盤價"=? WHERE "日期"=? AND "證券代號"=?',
        ("99", DATE, "0050"),
    )
    connection.commit()
    connection.close()
    with pytest.raises(ResearchDatasetError, match="recovered database hash/size differs"):
        _build(paths)

    paths = _fixture(tmp_path / "second", monkeypatch)
    with pytest.raises(ResearchDatasetError, match="predates corrected source data"):
        _build(paths, observed_at="2026-09-21T03:00:00-07:00")
