from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from app_module.evidence_weekly_approval_input import build_weekly_approval_input
import app_module.evidence_weekly_history_decision_bridge as decision_bridge
from app_module.evidence_weekly_history_decision_bridge import (
    load_and_validate_weekly_review_decision_artifact,
)
from app_module.evidence_weekly_review_decision import write_weekly_review_decision_artifact


def _sidecar(path: Path) -> None:
    coverage = {
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
                "sha256:" + "a" * 64,
                "pending_human_review",
                json.dumps({
                    "last_trading_date": "2026-10-22",
                    "human_approval_required": True,
                    "source_coverage": coverage,
                }),
                "2026-10-26T12:00:00+00:00",
            ),
        )


def _artifact(tmp_path: Path) -> tuple[Path, Path]:
    sidecar_path = tmp_path / "weekly-sidecar.sqlite"
    _sidecar(sidecar_path)
    packet = build_weekly_approval_input(
        sidecar_path,
        owner_role="portfolio_owner",
        reviewer_role="independent_reviewer",
    )
    artifact_path = tmp_path / "decision.json"
    write_weekly_review_decision_artifact(
        packet,
        sidecar_path,
        collection_id="ewc-1",
        owner_name="Owner Example",
        owner_role="portfolio_owner",
        reviewer_name="Reviewer Example",
        reviewer_role="independent_reviewer",
        decision="follow_up",
        note="已檢查來源與品質缺口，待補來源證據。",
        output_path=artifact_path,
        reviewed_at="2026-10-26T12:30:00+08:00",
    )
    return sidecar_path, artifact_path


def _validate(artifact_path: Path) -> dict:
    return load_and_validate_weekly_review_decision_artifact(
        artifact_path,
        expected_period_start="2026-10-19",
        expected_period_end="2026-10-25",
    )


def test_validates_current_decision_and_returns_raw_artifact_sha(tmp_path: Path) -> None:
    sidecar_path, artifact_path = _artifact(tmp_path)
    original_sidecar = sidecar_path.read_bytes()
    raw_artifact = artifact_path.read_bytes()

    result = _validate(artifact_path)

    assert result["artifact_sha256"] == "sha256:" + hashlib.sha256(raw_artifact).hexdigest()
    assert result["artifact_path"] == str(artifact_path.resolve())
    assert result["decision"] == "follow_up"
    assert result["owner"] == {"name": "Owner Example", "role": "portfolio_owner"}
    assert result["reviewer"] == {
        "name": "Reviewer Example",
        "role": "independent_reviewer",
    }
    assert result["candidate_only"] is True
    assert result["formal_credit_authorized"] is False
    assert result["production_scheduler_allowed"] is False
    assert result["approved_projection_emitted"] is False
    assert sidecar_path.read_bytes() == original_sidecar


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("formal_credit_authorized", True, "safety flag is invalid"),
        ("production_scheduler_allowed", True, "safety flag is invalid"),
        ("weekly_history_written", True, "safety flag is invalid"),
        ("decision", "approved", "decision must be reviewed"),
    ],
)
def test_rejects_tampered_decision_contract(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    _, artifact_path = _artifact(tmp_path)
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload[field] = value
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _validate(artifact_path)


def test_rejects_period_mismatch_before_attachment(tmp_path: Path) -> None:
    _, artifact_path = _artifact(tmp_path)

    with pytest.raises(ValueError, match="exactly match weekly report period"):
        load_and_validate_weekly_review_decision_artifact(
            artifact_path,
            expected_period_start="2026-10-18",
            expected_period_end="2026-10-25",
        )


def test_rejects_stale_sidecar(tmp_path: Path) -> None:
    sidecar_path, artifact_path = _artifact(tmp_path)
    with sqlite3.connect(sidecar_path) as connection:
        connection.execute(
            "UPDATE evidence_weekly_collections SET created_at = ?",
            ("2026-10-26T12:01:00+00:00",),
        )

    with pytest.raises(ValueError, match="sidecar SHA-256 is stale"):
        _validate(artifact_path)


def test_rejects_uncheckpointed_wal_sidecar_before_rebuilding_packet(tmp_path: Path) -> None:
    sidecar_path, artifact_path = _artifact(tmp_path)
    wal_path = Path(str(sidecar_path) + "-wal")
    wal_path.write_bytes(b"uncheckpointed evidence")

    with pytest.raises(ValueError, match="must be checkpointed"):
        _validate(artifact_path)


def test_rejects_wal_mutation_during_packet_rebuild(tmp_path: Path, monkeypatch) -> None:
    sidecar_path, artifact_path = _artifact(tmp_path)
    original_builder = decision_bridge.build_weekly_approval_input

    def _mutating_builder(*args, **kwargs):
        packet = original_builder(*args, **kwargs)
        Path(str(sidecar_path) + "-wal").write_bytes(b"concurrent wal change")
        return packet

    monkeypatch.setattr(decision_bridge, "build_weekly_approval_input", _mutating_builder)
    with pytest.raises(ValueError, match="sidecar changed while rebuilding"):
        _validate(artifact_path)


def test_rejects_artifact_for_a_different_explicitly_selected_sidecar(tmp_path: Path) -> None:
    _, artifact_path = _artifact(tmp_path)
    other_sidecar = tmp_path / "other-sidecar.sqlite"
    _sidecar(other_sidecar)

    with pytest.raises(ValueError, match="does not match the explicitly selected sidecar"):
        load_and_validate_weekly_review_decision_artifact(
            artifact_path,
            expected_period_start="2026-10-19",
            expected_period_end="2026-10-25",
            expected_sidecar_path=other_sidecar,
        )


def test_hash_covers_exact_serialized_artifact_bytes(tmp_path: Path) -> None:
    _, artifact_path = _artifact(tmp_path)
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["note"] = "different"
    artifact_path.write_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    result = _validate(artifact_path)
    assert result["note"] == "different"
    assert result["artifact_sha256"] == "sha256:" + hashlib.sha256(
        artifact_path.read_bytes()
    ).hexdigest()
