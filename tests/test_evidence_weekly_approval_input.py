from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from app_module.evidence_weekly_approval_input import (
    APPROVAL_STATUS,
    build_weekly_approval_input,
    read_verified_official_receipt,
    render_markdown,
    validate_output_path,
    write_weekly_approval_input_packet,
)


def _create_sidecar(path: Path, source_path: Path) -> None:
    source_path.write_bytes(b"source")
    source_hash = "sha256:" + ("a" * 64)
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
        connection.executemany(
            """
            INSERT INTO evidence_weekly_collections (
                collection_id, period_start, period_end, source_path,
                source_hash, status, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "ewc-1",
                    "2026-08-03",
                    "2026-08-09",
                    str(source_path),
                    source_hash,
                    "pending_human_review",
                    json.dumps(
                        {
                            "last_trading_date": "2026-08-07",
                            "human_approval_required": True,
                            "source_coverage": {
                                "status": "degraded",
                                "trading_day_count": 2,
                                "observed_row_count": 3,
                                "duplicate_symbol_rows": 0,
                                "quality_findings": ["required_price_values_missing"],
                                "incomplete_row_count": 1,
                                "integrity_examples": [
                                    {
                                        "date": "2026-08-07",
                                        "symbol": "2330",
                                        "missing_fields": ["收盤價"],
                                        "activity": {"成交股數": 1000, "成交筆數": 12},
                                        "classification": "official_source_reports_missing_values",
                                        "official_ohlc": {
                                            "開盤價": "10",
                                            "最高價": "10",
                                            "最低價": "10",
                                            "收盤價": "--",
                                        },
                                        "official_receipt_sha256": "sha256:" + ("b" * 64),
                                    }
                                ],
                                "integrity_examples_truncated": False,
                            },
                        }
                    ),
                    "2026-08-10 01:00:00",
                ),
                (
                    "ewc-2",
                    "2026-08-10",
                    "2026-08-16",
                    str(source_path),
                    source_hash,
                    "collection_failed",
                    json.dumps({"last_trading_date": ""}),
                    "2026-08-17 01:00:00",
                ),
            ],
        )


def test_build_packet_is_read_only_and_excludes_failed_by_default(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    source_path = tmp_path / "source.db"
    _create_sidecar(sidecar_path, source_path)
    before = sidecar_path.read_bytes()

    packet = build_weekly_approval_input(sidecar_path)

    assert packet["packet_status"] == "needs_named_owner_reviewer"
    assert packet["record_count"] == 1
    assert packet["pending_human_review_count"] == 1
    assert packet["collection_failed_count"] == 0
    assert packet["formal_credit_authorized"] is False
    assert packet["write_performed"] is False
    assert packet["records"][0]["review"]["approval_status"] == APPROVAL_STATUS
    evidence = packet["records"][0]["runbook_evidence"]
    assert evidence["status"] == "incomplete_required_evidence"
    assert evidence["required_count"] == 11
    assert evidence["verified_count"] == 0
    assert evidence["partial_count"] == 2
    assert evidence["missing_count"] == 9
    evidence_by_id = {item["evidence_id"]: item for item in evidence["items"]}
    assert evidence_by_id["source_coverage_snapshot"]["status"] == "unverified"
    assert evidence_by_id["warnings_blocking_gaps"]["status"] == "partial"
    assert evidence_by_id["working_copy_smoke"]["status"] == "missing"
    assert packet["runbook_evidence"]["status"] == "incomplete_required_evidence"
    assert packet["runbook_evidence"]["verified_count"] == 0
    markdown = render_markdown(packet)
    assert "Runbook evidence checklist" in markdown
    assert "Working-copy smoke" in markdown
    assert "9 missing; 2 partial" in markdown
    assert "required_price_values_missing" in markdown
    assert "2026-08-07` / `2330" in markdown
    assert "收盤價" in markdown
    assert "official_source_reports_missing_values" in markdown
    assert "成交股數" in markdown
    assert "sha256:" + ("b" * 64) in markdown
    assert '"收盤價": "--"' in markdown
    assert sidecar_path.read_bytes() == before


def test_build_packet_can_include_failed_and_named_roles(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    source_path = tmp_path / "source.db"
    _create_sidecar(sidecar_path, source_path)

    packet = build_weekly_approval_input(
        sidecar_path,
        owner_role="evidence_owner",
        reviewer_role="independent_reviewer",
        include_failed=True,
    )

    assert packet["packet_status"] == "ready_for_human_review"
    assert packet["record_count"] == 2
    assert packet["pending_human_review_count"] == 1
    assert packet["collection_failed_count"] == 1
    assert packet["owner_role"] == "evidence_owner"
    assert packet["reviewer_role"] == "independent_reviewer"
    assert "pending" in render_markdown(packet)


def test_packet_fails_closed_on_invalid_source_hash(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    source_path = tmp_path / "source.db"
    _create_sidecar(sidecar_path, source_path)
    with sqlite3.connect(sidecar_path) as connection:
        connection.execute(
            "UPDATE evidence_weekly_collections SET source_hash = 'not-hashed'"
        )

    with pytest.raises(ValueError, match="immutable"):
        build_weekly_approval_input(sidecar_path)


def test_output_path_cannot_overwrite_sidecar_or_missing_parent(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    with pytest.raises(ValueError, match="overwrite"):
        validate_output_path(sidecar_path, sidecar_path=sidecar_path)
    with pytest.raises(ValueError, match="parent"):
        validate_output_path(
            tmp_path / "missing" / "packet.json",
            sidecar_path=sidecar_path,
        )


def test_packet_export_creates_new_file_and_never_replaces_existing(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    output_path = tmp_path / "packet.json"
    packet = {
        "schema_version": "evidence-weekly-approval-input.v1",
        "candidate_only": True,
        "formal_credit_authorized": False,
        "production_scheduler_allowed": False,
        "write_performed": False,
        "approved_projection_emitted": False,
        "records": [],
    }

    written = write_weekly_approval_input_packet(
        packet,
        output_path,
        sidecar_path=sidecar_path,
    )

    assert written == output_path.resolve()
    assert json.loads(output_path.read_text(encoding="utf-8")) == packet
    before = output_path.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        write_weekly_approval_input_packet(
            {**packet, "packet_status": "changed"},
            output_path,
            sidecar_path=sidecar_path,
        )
    assert output_path.read_bytes() == before


def test_packet_export_rejects_approval_or_write_flags(tmp_path: Path) -> None:
    packet = {
        "schema_version": "evidence-weekly-approval-input.v1",
        "candidate_only": True,
        "formal_credit_authorized": True,
        "production_scheduler_allowed": False,
        "write_performed": False,
        "approved_projection_emitted": False,
        "records": [],
    }
    with pytest.raises(ValueError, match="formal_credit_authorized"):
        write_weekly_approval_input_packet(
            packet,
            tmp_path / "packet.json",
            sidecar_path=tmp_path / "sidecar.sqlite",
        )


def test_receipt_preview_requires_containment_and_matching_hash(tmp_path: Path) -> None:
    authorized_root = tmp_path / "output"
    receipt_path = authorized_root / "scheduled" / "receipt.json"
    receipt_path.parent.mkdir(parents=True)
    raw = b'{"status":"captured"}\n'
    receipt_path.write_bytes(raw)
    expected = "sha256:" + hashlib.sha256(raw).hexdigest()

    result = read_verified_official_receipt(authorized_root, receipt_path, expected)

    assert result["sha256"] == expected
    assert result["text"] == raw.decode("utf-8")
    assert result["byte_count"] == len(raw)

    outside = tmp_path / "outside.json"
    outside.write_bytes(raw)
    with pytest.raises(ValueError, match="outside"):
        read_verified_official_receipt(authorized_root, outside, expected)

    receipt_path.write_bytes(b'{"status":"tampered"}\n')
    with pytest.raises(ValueError, match="does not match"):
        read_verified_official_receipt(authorized_root, receipt_path, expected)


def test_receipt_preview_rejects_invalid_hash_and_oversize(tmp_path: Path) -> None:
    authorized_root = tmp_path / "output"
    authorized_root.mkdir()
    receipt_path = authorized_root / "receipt.json"
    receipt_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed"):
        read_verified_official_receipt(authorized_root, receipt_path, "sha256:bad")

    expected = "sha256:" + hashlib.sha256(b"{}").hexdigest()
    with pytest.raises(ValueError, match="size limit"):
        read_verified_official_receipt(
            authorized_root,
            receipt_path,
            expected,
            max_bytes=1,
        )


def _write_runbook_artifacts(root: Path, *, period_start="2026-08-03", period_end="2026-08-09") -> Path:
    db_path = root / "working-copy.sqlite"
    fingerprint = "sha256:" + ("f" * 64)
    smoke = {
        "schema_version": "baldr-weekly-runbook-artifact.v1",
        "artifact_role": "working_copy_smoke",
        "period_start": period_start,
        "period_end": period_end,
        "decision_date": "2026-08-07",
        "idempotency_check": {"passed": True},
        "source_identity_stable": True,
        "source_write_performed": False,
        "working_copy_write_performed": True,
        "working_copy_db_path": str(db_path.resolve()),
        "working_copy_fingerprint_after": fingerprint,
        "fingerprint_method": "sha256_sqlite_file_set.v1",
        "blocking_gaps": [],
    }
    report = {
        "schema_version": "baldr-weekly-runbook-artifact.v1",
        "artifact_role": "weekly_review_report",
        "period_start": period_start,
        "period_end": period_end,
        "decision_date": period_end,
        "database_identity": {
            "role": "working_copy",
            "path": str(db_path.resolve()),
            "fingerprint_method": "sha256_sqlite_file_set.v1",
            "fingerprint_before": fingerprint,
            "fingerprint_after": fingerprint,
            "stable": True,
        },
        "report_payload": {
            "warnings": [],
            "manual_approval": {"blocking_gaps": []},
            "manual_lifecycle_candidates": [],
            "action_item_plan": {"action_items_planned": 0},
        },
        "safety_flags_verified": {
            "write_performed": True,
            "production_scheduler_allowed": True,
            "lifecycle_apply_action_all_false": True,
        },
        "production_scheduler_allowed": False,
    }
    dashboard = {
        "schema_version": "baldr-weekly-runbook-artifact.v1",
        "artifact_role": "evidence_review_dashboard",
        "period_start": period_start,
        "period_end": period_end,
        "database_identity": {
            "role": "review_store",
            "fingerprint_method": "sha256_sqlite_file_set.v1",
            "fingerprint_before": fingerprint,
            "fingerprint_after": fingerprint,
            "stable_during_read": True,
        },
        "payload": {
            "dashboard_verified": True,
            "cards": {"reviews_count": 1},
            "rows": [{
                "period_start": period_start,
                "period_end": period_end,
                "review_id": "review-1",
                "review_hash": "sha256:" + ("a" * 64),
            }],
            "pagination_complete": True,
            "diagnostics": [],
            "limitations": [],
        },
    }
    artifacts = []
    for role, payload in (
        ("working_copy_smoke", smoke),
        ("weekly_review_report", report),
        ("evidence_review_dashboard", dashboard),
    ):
        path = root / f"{role}.json"
        raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
        path.write_bytes(raw)
        artifacts.append({
            "artifact_role": role,
            "path": path.name,
            "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        })
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "schema_version": "baldr-weekly-runbook-manifest.v1",
            "collection_id": "ewc-1",
            "period_start": period_start,
            "period_end": period_end,
            "artifacts": artifacts,
        }),
        encoding="utf-8",
    )
    return manifest_path


def test_runbook_manifest_verifies_matching_artifacts_and_keeps_gate_roles_partial(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    _create_sidecar(sidecar_path, tmp_path / "source.db")
    manifest_path = _write_runbook_artifacts(tmp_path)

    packet = build_weekly_approval_input(
        sidecar_path,
        artifact_manifest_path=manifest_path,
        authorized_receipt_root=tmp_path,
    )
    record = packet["records"][0]
    evidence = {item["evidence_id"]: item for item in record["runbook_evidence"]["items"]}

    assert record["runbook_evidence"]["manifest_status"] == "matched"
    assert evidence["working_copy_smoke"]["status"] == "verified"
    assert evidence["weekly_review_report"]["status"] == "verified"
    assert evidence["evidence_review_dashboard"]["status"] == "verified"
    assert evidence["warnings_blocking_gaps"]["status"] == "verified"
    assert evidence["review_identity_and_history"]["status"] == "partial"
    assert evidence["backup_rollback_recovery"]["status"] == "missing"
    assert packet["formal_credit_authorized"] is False
    assert packet["production_scheduler_allowed"] is False


def test_runbook_manifest_identity_mismatch_is_not_applied(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    _create_sidecar(sidecar_path, tmp_path / "source.db")
    manifest_path = _write_runbook_artifacts(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["collection_id"] = "different-collection"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    packet = build_weekly_approval_input(
        sidecar_path,
        artifact_manifest_path=manifest_path,
        authorized_receipt_root=tmp_path,
    )
    evidence = packet["records"][0]["runbook_evidence"]
    assert evidence["manifest_status"] == "identity_mismatch_not_applied"
    assert evidence["verified_count"] == 0


def test_runbook_manifest_rejects_duplicate_roles_and_hash_mismatch(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "sidecar.sqlite"
    _create_sidecar(sidecar_path, tmp_path / "source.db")
    manifest_path = _write_runbook_artifacts(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"].append(dict(manifest["artifacts"][0]))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        build_weekly_approval_input(
            sidecar_path,
            artifact_manifest_path=manifest_path,
            authorized_receipt_root=tmp_path,
        )

    manifest["artifacts"].pop()
    manifest["artifacts"][0]["sha256"] = "sha256:" + ("0" * 64)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_weekly_approval_input(
            sidecar_path,
            artifact_manifest_path=manifest_path,
            authorized_receipt_root=tmp_path,
        )


def test_runbook_manifest_rejects_path_escape_and_writer_rechecks_same_manifest(tmp_path: Path) -> None:
    from app_module.evidence_weekly_review_decision import write_weekly_review_decision_artifact

    sidecar_path = tmp_path / "sidecar.sqlite"
    _create_sidecar(sidecar_path, tmp_path / "source.db")
    manifest_path = _write_runbook_artifacts(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["path"] = "../outside.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="stay below"):
        build_weekly_approval_input(
            sidecar_path,
            artifact_manifest_path=manifest_path,
            authorized_receipt_root=tmp_path,
        )

    manifest_path = _write_runbook_artifacts(tmp_path)
    packet = build_weekly_approval_input(
        sidecar_path,
        artifact_manifest_path=manifest_path,
        authorized_receipt_root=tmp_path,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["sha256"] = "sha256:" + ("0" * 64)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        write_weekly_review_decision_artifact(
            packet,
            sidecar_path,
            collection_id="ewc-1",
            owner_name="Owner",
            owner_role="Portfolio Owner",
            reviewer_name="Reviewer",
            reviewer_role="Independent Reviewer",
            decision="reviewed",
            note="Checked the attached evidence.",
            output_path=tmp_path / "decision.json",
            artifact_manifest_path=manifest_path,
            authorized_receipt_root=tmp_path,
        )


def test_decision_artifact_persists_revalidated_runbook_hash_bindings(tmp_path: Path) -> None:
    from app_module.evidence_weekly_review_decision import write_weekly_review_decision_artifact

    sidecar_path = tmp_path / "sidecar.sqlite"
    _create_sidecar(sidecar_path, tmp_path / "source.db")
    manifest_path = _write_runbook_artifacts(tmp_path)
    packet = build_weekly_approval_input(
        sidecar_path,
        artifact_manifest_path=manifest_path,
        authorized_receipt_root=tmp_path,
    )
    output_path = tmp_path / "decision.json"

    written = write_weekly_review_decision_artifact(
        packet,
        sidecar_path,
        collection_id="ewc-1",
        owner_name="Owner",
        owner_role="Portfolio Owner",
        reviewer_name="Reviewer",
        reviewer_role="Independent Reviewer",
        decision="reviewed",
        note="Reviewed the attached evidence package.",
        output_path=output_path,
        artifact_manifest_path=manifest_path,
        authorized_receipt_root=tmp_path,
    )

    artifact = json.loads(written.read_text(encoding="utf-8"))
    binding = artifact["source"]["runbook_manifest_binding"]
    assert binding["path"] == str(manifest_path.resolve())
    assert binding["sha256"] == "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert binding["status"] == "matched"
    assert binding["artifact_sha256_by_role"] == {
        entry["artifact_role"]: entry["sha256"]
        for entry in json.loads(manifest_path.read_text(encoding="utf-8"))["artifacts"]
    }


def test_decision_writer_rejects_tampered_runbook_artifact(tmp_path: Path) -> None:
    from app_module.evidence_weekly_review_decision import write_weekly_review_decision_artifact

    sidecar_path = tmp_path / "sidecar.sqlite"
    _create_sidecar(sidecar_path, tmp_path / "source.db")
    manifest_path = _write_runbook_artifacts(tmp_path)
    packet = build_weekly_approval_input(
        sidecar_path,
        artifact_manifest_path=manifest_path,
        authorized_receipt_root=tmp_path,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_path = manifest_path.parent / manifest["artifacts"][0]["path"]
    artifact_path.write_text('{"tampered":true}\n', encoding="utf-8")
    output_path = tmp_path / "decision.json"

    with pytest.raises(ValueError, match="hash mismatch"):
        write_weekly_review_decision_artifact(
            packet,
            sidecar_path,
            collection_id="ewc-1",
            owner_name="Owner",
            owner_role="Portfolio Owner",
            reviewer_name="Reviewer",
            reviewer_role="Independent Reviewer",
            decision="reviewed",
            note="Reviewed the attached evidence package.",
            output_path=output_path,
            artifact_manifest_path=manifest_path,
            authorized_receipt_root=tmp_path,
        )
    assert not output_path.exists()

