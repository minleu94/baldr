"""隔離 technical row recovery 的合成 SQLite 驗證。"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from data_module.ml_daily_price_revision_recovery import (
    RECOVERY_CONFIRMATION,
    RecoveryError,
    apply_isolated_recovery,
    preview_isolated_recovery,
)
from data_module.ml_daily_price_revision_technical_snapshot import (
    PRICE_RECEIPT_SCHEMA,
    TECHNICAL_RECEIPT_SCHEMA,
    _canonical_hash,
    _sha256_file,
)


def _create_database(path: Path, rows: list[tuple[object, ...]]) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        'CREATE TABLE technical_indicators ('
        '"日期" TEXT, "證券代號" TEXT, "ADX" REAL, "Open" REAL, '
        '"Close" REAL, "Note" TEXT, PRIMARY KEY("證券代號", "日期"))'
    )
    connection.executemany(
        'INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?, ?)', rows
    )
    connection.commit()
    connection.close()


def _seal_receipt(payload: dict[str, object]) -> dict[str, object]:
    sealed = dict(payload)
    sealed["receipt_sha256"] = _canonical_hash(payload)
    return sealed


def _fixture(tmp_path: Path) -> dict[str, Path | str]:
    run_root = tmp_path / "isolated_run02"
    run_root.mkdir()
    before_db = tmp_path / "technical_before.db"
    target_db = run_root / "snapshot.db"
    _create_database(
        before_db,
        [
            ("20260520", "0050", 10.0, 93.0, 92.5, "before-row-a"),
            ("20260521", "0050", 11.0, 94.0, 93.5, "before-row-b"),
            ("20260520", "2330", 20.0, 50.0, 51.0, "outside-row"),
        ],
    )
    _create_database(
        target_db,
        [
            ("20260520", "0050", 99.0, None, 99.0, "writer-row-a"),
            ("20260521", "0050", 88.0, None, 88.0, "writer-row-b"),
            ("20260520", "2330", 20.0, 50.0, 51.0, "outside-row"),
        ],
    )
    manifest = tmp_path / "dryrun.json"
    manifest.write_text(
        json.dumps(
            {
                "plans": [
                    {
                        "symbol": "0050",
                        "updates": [
                            {"date": "20260520", "changed_columns": ["ADX"], "new": {"ADX": 12.0}},
                            {"date": "20260521", "changed_columns": ["ADX"], "new": {"ADX": 13.0}},
                        ],
                        "source_copy_plan": {
                            "updates": [
                                {"row_identity": {"date": "20260520"}, "column": "Open", "column_ordinal": 0, "new": 100.0},
                                {"row_identity": {"date": "20260520"}, "column": "Close", "column_ordinal": 0, "new": 101.0},
                                {"row_identity": {"date": "20260521"}, "column": "Open", "column_ordinal": 0, "new": 102.0},
                                {"row_identity": {"date": "20260521"}, "column": "Close", "column_ordinal": 0, "new": 103.0},
                            ]
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    price_receipt_path = tmp_path / "price_receipt.json"
    price_receipt = _seal_receipt(
        {
            "schema_version": PRICE_RECEIPT_SCHEMA,
            "receipt_kind": "historical_price_spike_repair",
            "status": "applied",
            "source_date": "20260520",
            "plan_hash": "plan-fixture",
            "allowlist_hash": "allowlist-fixture",
            "formal_training_allowed": False,
            "promotion_eligible": False,
        }
    )
    price_receipt_path.write_text(json.dumps(price_receipt), encoding="utf-8")
    technical_receipt_path = tmp_path / "technical_receipt.json"
    technical_receipt = _seal_receipt(
        {
            "schema_version": TECHNICAL_RECEIPT_SCHEMA,
            "receipt_kind": "technical_indicator_repair",
            "status": "applied",
            "source_date": "20260520",
            "formal_training_allowed": False,
            "promotion_eligible": False,
            "technical_backup_sha256": _sha256_file(before_db),
            "dryrun_manifest_sha256": _sha256_file(manifest),
            "price_receipt_sha256": price_receipt["receipt_sha256"],
            "operations_summary": {
                "operations": 6,
                "technical_indicator_cells": 2,
                "technical_source_cells": 4,
                "technical_source_rows": 1,
            },
        }
    )
    technical_receipt_path.write_text(json.dumps(technical_receipt), encoding="utf-8")
    technical_pending_path = tmp_path / "technical_pending.json"
    technical_pending_path.write_text(
        json.dumps(
            {
                "schema_version": TECHNICAL_RECEIPT_SCHEMA,
                "receipt_kind": "technical_indicator_repair_pending",
                "status": "receipt_written",
                "source_date": "20260520",
                "technical_backup_sha256": _sha256_file(before_db),
                "dryrun_manifest_sha256": _sha256_file(manifest),
                "price_receipt": price_receipt["receipt_sha256"],
            }
        ),
        encoding="utf-8",
    )
    price_pending_path = tmp_path / "price_pending.json"
    price_pending_path.write_text(
        json.dumps(
            {
                "schema_version": PRICE_RECEIPT_SCHEMA,
                "receipt_kind": "historical_price_spike_repair_pending",
                "status": "applied_receipt_written",
                "source_date": "20260520",
                "plan_hash": price_receipt["plan_hash"],
                "allowlist_hash": price_receipt["allowlist_hash"],
            }
        ),
        encoding="utf-8",
    )
    evidence = run_root / "evidence"
    return {
        "run_root": run_root,
        "before_db": before_db,
        "target_db": target_db,
        "manifest": manifest,
        "technical_receipt": technical_receipt_path,
        "price_receipt": price_receipt_path,
        "technical_pending": technical_pending_path,
        "price_pending": price_pending_path,
        "evidence": evidence,
        "target_sha256": _sha256_file(target_db),
    }


def _run_kwargs(fixture: dict[str, Path | str], *, evidence: Path | None = None, target_sha256: str | None = None) -> dict[str, object]:
    return {
        "database_path": fixture["target_db"],
        "expected_database_sha256": target_sha256 or fixture["target_sha256"],
        "before_backup_path": fixture["before_db"],
        "dryrun_manifest_path": fixture["manifest"],
        "technical_receipt_path": fixture["technical_receipt"],
        "price_receipt_path": fixture["price_receipt"],
        "technical_pending_path": fixture["technical_pending"],
        "price_pending_path": fixture["price_pending"],
        "allowed_output_root": fixture["run_root"],
        "evidence_directory": evidence or fixture["evidence"],
        "confirmation": RECOVERY_CONFIRMATION,
        "require_official_coverage": False,
    }


def _read_rows(path: Path) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(path)
    rows = connection.execute(
        'SELECT * FROM technical_indicators ORDER BY "證券代號", "日期"'
    ).fetchall()
    connection.close()
    return rows


def test_recovery_restores_rows_and_is_idempotent(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    preview = preview_isolated_recovery(**_run_kwargs(fixture))
    assert preview["status"] == "ready_for_review"
    assert preview["coverage"]["affected_rows"] == 2
    assert preview["planned_cell_diff"]["changed_cells"] == 8
    assert preview["row_hashes"]["plan_external_rows"] == 1
    assert _sha256_file(Path(fixture["target_db"])) == fixture["target_sha256"]

    report = apply_isolated_recovery(**_run_kwargs(fixture))
    assert report["status"] == "passed"
    assert report["rows"]["affected_rows"] == 2
    assert report["rows"]["rows_written"] == 2
    assert report["cell_diff"]["after_cells"] == 6
    assert report["cell_diff"]["changed_cells"] == 8
    assert report["post_commit_verification"]["untouched_mismatches"] == 0
    assert report["pending_state"]["changed"] is False
    rows = _read_rows(Path(fixture["target_db"]))
    assert rows == [
        ("20260520", "0050", 12.0, 100.0, 101.0, "before-row-a"),
        ("20260521", "0050", 13.0, 102.0, 103.0, "before-row-b"),
        ("20260520", "2330", 20.0, 50.0, 51.0, "outside-row"),
    ]
    receipt_path = Path(fixture["evidence"]) / "recovery_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    body = dict(receipt)
    recorded_sha = body.pop("receipt_sha256")
    assert recorded_sha == _canonical_hash(body)

    second_evidence = Path(fixture["run_root"]) / "evidence-second"
    second = apply_isolated_recovery(
        **_run_kwargs(
            fixture,
            evidence=second_evidence,
            target_sha256=_sha256_file(Path(fixture["target_db"])),
        )
    )
    assert second["status"] == "passed"
    assert second["rows"]["rows_written"] == 0
    assert second["cell_diff"]["changed_cells"] == 0
    assert second["database_sha256_after"] == report["database_sha256_after"]


def test_recovery_rolls_back_the_entire_transaction_on_write_failure(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    target = Path(fixture["target_db"])
    original_sha = _sha256_file(target)
    connection = sqlite3.connect(target)
    connection.execute(
        'CREATE TRIGGER stop_second_update BEFORE UPDATE ON technical_indicators '
        'WHEN OLD."日期" = "20260521" '
        'BEGIN SELECT RAISE(ABORT, "synthetic failure"); END'
    )
    connection.commit()
    connection.close()
    with_trigger_sha = _sha256_file(target)
    evidence = Path(fixture["run_root"]) / "evidence-rollback"
    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        apply_isolated_recovery(
            **_run_kwargs(
                fixture,
                evidence=evidence,
                target_sha256=with_trigger_sha,
            )
        )
    assert _sha256_file(target) == with_trigger_sha
    assert _read_rows(target) == [
        ("20260520", "0050", 99.0, None, 99.0, "writer-row-a"),
        ("20260521", "0050", 88.0, None, 88.0, "writer-row-b"),
        ("20260520", "2330", 20.0, 50.0, 51.0, "outside-row"),
    ]
    assert not evidence.exists() or not list(evidence.iterdir())
    assert original_sha != with_trigger_sha


def test_recovery_fails_closed_when_pending_state_does_not_match_receipts(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    pending = Path(fixture["technical_pending"])
    payload = json.loads(pending.read_text(encoding="utf-8"))
    payload["status"] = "cleared"
    pending.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RecoveryError, match="technical pending schema/kind/status/source_date"):
        preview_isolated_recovery(**_run_kwargs(fixture))

    assert _sha256_file(Path(fixture["target_db"])) == fixture["target_sha256"]
