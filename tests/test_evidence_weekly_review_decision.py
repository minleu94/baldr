from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from app_module.evidence_weekly_approval_input import build_weekly_approval_input
from app_module.evidence_weekly_review_decision import (
    SCHEMA_VERSION,
    write_weekly_review_decision_artifact,
)


def _create_sidecar(path: Path, *, source_coverage: dict | None = None) -> None:
    coverage = source_coverage or {
        "status": "degraded",
        "trading_day_count": 2,
        "observed_row_count": 3,
        "duplicate_symbol_rows": 0,
        "quality_findings": ["required_price_values_missing"],
        "incomplete_row_count": 1,
        "integrity_examples": [],
        "integrity_examples_truncated": False,
    }
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE evidence_weekly_collections (
                collection_id TEXT PRIMARY KEY,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                error_type TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO evidence_weekly_collections (
                collection_id, period_start, period_end, source_path,
                source_hash, status, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ewc-1",
                "2026-10-19",
                "2026-10-25",
                str(path.with_name("source.json")),
                "sha256:" + ("a" * 64),
                "pending_human_review",
                json.dumps(
                    {
                        "last_trading_date": "2026-10-22",
                        "human_approval_required": True,
                        "source_coverage": coverage,
                    }
                ),
                "2026-10-26T12:00:00+00:00",
            ),
        )


def _packet(sidecar_path: Path) -> dict:
    return build_weekly_approval_input(
        sidecar_path,
        owner_role="portfolio_owner",
        reviewer_role="independent_reviewer",
    )


def _write(
    packet: dict,
    sidecar_path: Path,
    output_path: Path,
    *,
    decision: str = "reviewed",
    reviewed_at: str | None = "2026-10-26T12:30:00+08:00",
) -> Path:
    return write_weekly_review_decision_artifact(
        packet,
        sidecar_path,
        collection_id="ewc-1",
        owner_name="Owner Example",
        owner_role="portfolio_owner",
        reviewer_name="Reviewer Example",
        reviewer_role="independent_reviewer",
        decision=decision,
        note="已檢查來源、品質缺口與後續處置。",
        output_path=output_path,
        reviewed_at=reviewed_at,
    )


@pytest.mark.parametrize("decision", ["reviewed", "dismissed", "follow_up"])
def test_writes_candidate_only_decision_without_changing_sidecar(
    tmp_path: Path, decision: str
) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    output_path = tmp_path / f"decision-{decision}.json"
    _create_sidecar(sidecar_path)
    sidecar_before = sidecar_path.read_bytes()
    packet = _packet(sidecar_path)

    written = _write(packet, sidecar_path, output_path, decision=decision)

    artifact = json.loads(written.read_text(encoding="utf-8"))
    assert written == output_path.resolve()
    assert artifact["schema_version"] == SCHEMA_VERSION
    assert artifact["decision"] == decision
    assert artifact["source"]["collection_id"] == "ewc-1"
    assert artifact["source"]["source_hash"] == "sha256:" + ("a" * 64)
    assert artifact["source"]["period_start"] == "2026-10-19"
    assert artifact["source"]["period_end"] == "2026-10-25"
    assert artifact["source"]["sidecar_sha256"] == packet["sidecar_sha256"]
    assert artifact["candidate_only"] is True
    assert artifact["review_decision_recorded"] is True
    assert artifact["decision_artifact_written"] is True
    assert artifact["sidecar_written"] is False
    assert artifact["weekly_history_written"] is False
    assert artifact["formal_database_written"] is False
    assert artifact["formal_credit_authorized"] is False
    assert artifact["production_scheduler_allowed"] is False
    assert artifact["approved_projection_emitted"] is False
    assert artifact["gate_credit_status"] == "pending_human_review"
    assert "不等於 Gate 2 通過" in "".join(artifact["limitations"])
    assert sidecar_path.read_bytes() == sidecar_before


def test_rejects_stale_sidecar_and_does_not_create_output(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    output_path = tmp_path / "decision.json"
    _create_sidecar(sidecar_path)
    packet = _packet(sidecar_path)
    with sqlite3.connect(sidecar_path) as connection:
        connection.execute(
            "UPDATE evidence_weekly_collections SET created_at = ?",
            ("2026-10-26T12:01:00+00:00",),
        )

    with pytest.raises(ValueError, match="SHA-256 is stale"):
        _write(packet, sidecar_path, output_path)

    assert not output_path.exists()


def test_rejects_tampered_packet_even_when_sidecar_hash_is_unchanged(
    tmp_path: Path,
) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    output_path = tmp_path / "decision.json"
    _create_sidecar(sidecar_path)
    packet = _packet(sidecar_path)
    packet["records"][0]["period_end"] = "2026-10-26"

    with pytest.raises(ValueError, match="does not match the current sidecar"):
        _write(packet, sidecar_path, output_path)

    assert not output_path.exists()


def test_rejects_collection_that_requires_recollection(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    output_path = tmp_path / "decision.json"
    _create_sidecar(sidecar_path, source_coverage={"quality_findings": []})
    packet = _packet(sidecar_path)

    with pytest.raises(ValueError, match="not a reviewable candidate"):
        _write(packet, sidecar_path, output_path)

    assert not output_path.exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("owner_name", " ", "owner_name is required"),
        ("reviewer_name", " ", "reviewer_name is required"),
        ("note", "  ", "note is required"),
        ("decision", "approved", "decision must be reviewed"),
        ("reviewed_at", "2026-10-26T12:30:00", "must include a timezone"),
    ],
)
def test_rejects_incomplete_or_invalid_human_decision(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    output_path = tmp_path / "decision.json"
    _create_sidecar(sidecar_path)
    packet = _packet(sidecar_path)
    kwargs = {
        "owner_name": "Owner Example",
        "owner_role": "portfolio_owner",
        "reviewer_name": "Reviewer Example",
        "reviewer_role": "independent_reviewer",
        "decision": "reviewed",
        "note": "已檢查來源、品質缺口與後續處置。",
        "reviewed_at": "2026-10-26T12:30:00+08:00",
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=message):
        write_weekly_review_decision_artifact(
            packet,
            sidecar_path,
            collection_id="ewc-1",
            output_path=output_path,
            **kwargs,
        )

    assert not output_path.exists()


def test_rejects_existing_sidecar_and_formal_database_output_paths(
    tmp_path: Path,
) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    _create_sidecar(sidecar_path)
    packet = _packet(sidecar_path)

    with pytest.raises(ValueError, match="must not overwrite the source sidecar"):
        _write(packet, sidecar_path, sidecar_path)

    formal_dir = tmp_path / "FA_Data" / "sqlite"
    formal_dir.mkdir(parents=True)
    formal_db_path = formal_dir / "twstock.db"
    with pytest.raises(ValueError, match="formal database path"):
        _write(packet, sidecar_path, formal_db_path)


def test_refuses_existing_output_without_replacing_it(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    output_path = tmp_path / "decision.json"
    _create_sidecar(sidecar_path)
    packet = _packet(sidecar_path)
    output_path.write_text("prior artifact\n", encoding="utf-8")

    with pytest.raises(ValueError, match="already exists"):
        _write(packet, sidecar_path, output_path)

    assert output_path.read_text(encoding="utf-8") == "prior artifact\n"

\n