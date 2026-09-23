from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from data_module import ml_daily_price_revision_technical_snapshot as snapshot


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _receipt(payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    value = dict(payload)
    value["receipt_sha256"] = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
    return value


def _db(path: Path, *, revised: bool) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        'CREATE TABLE technical_indicators '
        '("證券代號" TEXT NOT NULL, "日期" TEXT NOT NULL, "MA5" REAL, '
        '"開盤價" REAL, "ADX" REAL, PRIMARY KEY ("證券代號", "日期"))'
    )
    connection.execute(
        'INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)',
        ("1234", "20260520", 10.0 if revised else 9.5, 10.0 if revised else 9.0, 3.0),
    )
    connection.commit()
    connection.close()


def _fixture(root: Path) -> dict[str, Path]:
    paths = {name: root / filename for name, filename in {
        "database": "snapshot.db", "backup": "before.db", "manifest": "plan.json",
        "technical_pending": "technical_pending.json", "technical_receipt": "technical_receipt.json",
        "price_pending": "price_pending.json", "price_receipt": "price_receipt.json",
    }.items()}
    _db(paths["database"], revised=True)
    _db(paths["backup"], revised=False)
    manifest = {"plans": [{
        "symbol": "1234",
        "updates": [{"date": "20260520", "changed_columns": ["MA5"], "new": {"MA5": 10.0}}],
        "source_copy_plan": {"updates": [{
            "row_identity": {"date": "20260520"}, "column": "開盤價", "column_ordinal": 0, "new": 10.0,
        }]},
    }]}
    _write_json(paths["manifest"], manifest)
    paths["technical_pending"].write_text(json.dumps({
        "schema_version": snapshot.TECHNICAL_RECEIPT_SCHEMA,
        "status": "receipt_written", "source_date": snapshot.TARGET_DATE,
    }), encoding="utf-8")
    paths["price_pending"].write_text(json.dumps({
        "schema_version": snapshot.PRICE_RECEIPT_SCHEMA,
        "receipt_kind": "historical_price_spike_repair_pending",
        "status": "applied_receipt_written", "source_date": snapshot.TARGET_DATE,
    }), encoding="utf-8")
    price_payload = _receipt({
        "schema_version": snapshot.PRICE_RECEIPT_SCHEMA,
        "receipt_kind": "historical_price_spike_repair", "status": "applied",
        "source_date": snapshot.TARGET_DATE, "available_at": None,
        "historical_decision_time_available": False, "formal_training_allowed": False,
        "promotion_eligible": False,
    })
    _write_json(paths["price_receipt"], price_payload)
    technical_payload = _receipt({
        "schema_version": snapshot.TECHNICAL_RECEIPT_SCHEMA,
        "receipt_kind": "technical_indicator_repair", "status": "applied",
        "source_date": snapshot.TARGET_DATE, "available_at": None,
        "formal_training_allowed": False,
        "price_receipt_sha256": price_payload["receipt_sha256"],
        "technical_backup_sha256": snapshot._sha256_file(paths["backup"]),
        "dryrun_manifest_sha256": snapshot._sha256_file(paths["manifest"]),
        "operations_summary": {"operations": 2, "technical_indicator_cells": 1,
                                "technical_source_cells": 1, "technical_source_rows": 1},
    })
    _write_json(paths["technical_receipt"], technical_payload)
    return paths


def test_manifest_cells_are_read_back_against_snapshot_and_before_backup(tmp_path: Path):
    paths = _fixture(tmp_path)
    expected, counts = snapshot.collect_expected_cells(paths["manifest"])
    result = snapshot.verify_technical_rows(paths["database"], paths["backup"], expected)

    assert counts == {"symbols": 1, "affected_rows": 1, "indicator_after_cells": 1,
                      "source_after_cells": 1, "after_cells": 2}
    assert result["after_matches"] == 2
    assert result["after_mismatches"] == 0
    assert result["untouched_cells"] == 3
    assert result["untouched_mismatches"] == 0
    assert "SEARCH" in result["query_plan"][0].upper()


def test_full_evidence_keeps_formal_gate_closed_and_binds_all_inputs(tmp_path: Path, monkeypatch):
    paths = _fixture(tmp_path)
    monkeypatch.setattr(snapshot, "EXPECTED_COVERAGE", {
        "symbols": 1, "affected_rows": 1, "indicator_after_cells": 1,
        "source_after_cells": 1, "after_cells": 2,
    })
    monkeypatch.setattr(snapshot, "EXPECTED_UNTOUCHED_CELLS", 3)

    evidence = snapshot.verify_revision_snapshot(
        database_path=paths["database"], technical_pending_path=paths["technical_pending"],
        technical_receipt_path=paths["technical_receipt"], price_pending_path=paths["price_pending"],
        price_receipt_path=paths["price_receipt"], technical_backup_path=paths["backup"],
        dryrun_manifest_path=paths["manifest"],
    )

    assert evidence["schema_version"] == snapshot.EVIDENCE_SCHEMA
    assert evidence["status"] == "passed"
    assert evidence["formal_pit_gate_changed"] is False
    assert evidence["historical_available_at"] is None
    assert evidence["snapshot"]["sha256_before"] == evidence["snapshot"]["sha256_after"]
    assert evidence["coverage"]["after_matches"] == 2
    assert evidence["coverage"]["untouched_cells"] == 3
    assert evidence["snapshot"]["sidecars_after"]["-wal"]["size_bytes"] == 0
    assert evidence["provenance"]["original_qa_verifier_imported"] is False
    assert evidence["provenance"]["original_qa_verifier_reference_sha256"] == snapshot.ORIGINAL_QA_VERIFIER_REFERENCE_SHA256
    assert evidence["evidence_sha256"].startswith("sha256:")


def test_nonproduction_coverage_cannot_be_used_as_evidence(tmp_path: Path):
    paths = _fixture(tmp_path)
    with pytest.raises(snapshot.SnapshotEvidenceError, match="dry-run manifest coverage"):
        snapshot.verify_revision_snapshot(
            database_path=paths["database"], technical_pending_path=paths["technical_pending"],
            technical_receipt_path=paths["technical_receipt"], price_pending_path=paths["price_pending"],
            price_receipt_path=paths["price_receipt"], technical_backup_path=paths["backup"],
            dryrun_manifest_path=paths["manifest"],
        )


def test_nonempty_wal_is_rejected_before_main_file_hash_is_accepted(tmp_path: Path):
    paths = _fixture(tmp_path)
    Path(str(paths["database"]) + "-wal").write_bytes(b"uncheckpointed pages")
    with pytest.raises(snapshot.SnapshotEvidenceError, match="非空 WAL"):
        snapshot.verify_revision_snapshot(
            database_path=paths["database"], technical_pending_path=paths["technical_pending"],
            technical_receipt_path=paths["technical_receipt"], price_pending_path=paths["price_pending"],
            price_receipt_path=paths["price_receipt"], technical_backup_path=paths["backup"],
            dryrun_manifest_path=paths["manifest"],
        )


def test_database_bytes_are_checked_after_the_indexed_readback(tmp_path: Path, monkeypatch):
    paths = _fixture(tmp_path)
    monkeypatch.setattr(snapshot, "EXPECTED_COVERAGE", {
        "symbols": 1, "affected_rows": 1, "indicator_after_cells": 1,
        "source_after_cells": 1, "after_cells": 2,
    })
    monkeypatch.setattr(snapshot, "EXPECTED_UNTOUCHED_CELLS", 3)
    original = snapshot.verify_technical_rows

    def change_snapshot_after_readback(database_path, backup_path, expected):
        result = original(database_path, backup_path, expected)
        with database_path.open("ab") as stream:
            stream.write(b"changed")
        return result

    monkeypatch.setattr(snapshot, "verify_technical_rows", change_snapshot_after_readback)
    with pytest.raises(snapshot.SnapshotEvidenceError, match="snapshot bytes/stat 改變"):
        snapshot.verify_revision_snapshot(
            database_path=paths["database"], technical_pending_path=paths["technical_pending"],
            technical_receipt_path=paths["technical_receipt"], price_pending_path=paths["price_pending"],
            price_receipt_path=paths["price_receipt"], technical_backup_path=paths["backup"],
            dryrun_manifest_path=paths["manifest"],
        )


def test_technical_mismatch_is_not_accepted(tmp_path: Path):
    paths = _fixture(tmp_path)
    connection = sqlite3.connect(paths["database"])
    connection.execute('UPDATE technical_indicators SET "MA5"=99')
    connection.commit()
    connection.close()
    expected, _ = snapshot.collect_expected_cells(paths["manifest"])
    result = snapshot.verify_technical_rows(paths["database"], paths["backup"], expected)

    assert result["after_mismatches"] == 1
    assert result["untouched_mismatches"] == 0
