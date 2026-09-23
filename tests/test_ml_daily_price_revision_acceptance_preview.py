from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import data_module.ml_daily_price_revision_acceptance_preview as preview


OBSERVED = "2026-09-22T23:59:34.214725+00:00"


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_sha(path: Path) -> str:
    return _sha(path.read_bytes())


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _seal(value: dict[str, object], field: str) -> dict[str, object]:
    result = dict(value)
    result[field] = _sha(_canonical(value) + b"\n")
    return result


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, historical_claim: bool = False) -> tuple[Path, str]:
    root = tmp_path / "archive"
    root.mkdir()
    repo_root = tmp_path / "workspace"
    (repo_root / "output" / "qa").mkdir(parents=True)
    for relative in preview.CONTRACT_SOURCE_PATHS:
        contract = repo_root / relative
        contract.parent.mkdir(parents=True, exist_ok=True)
        contract.write_text("synthetic contract source\n", encoding="utf-8")
    monkeypatch.setattr(preview, "REPO_ROOT", repo_root)
    monkeypatch.setattr(preview, "EXPECTED_ROWS", 2)
    monkeypatch.setattr(preview, "EXPECTED_DATASET_ID", "research_shadow_daily_price_revision_recovered_source_20260922")
    monkeypatch.setattr(preview, "EXPECTED_RUN_ID", "7e2f19cc5a00f20ba5b3890a")
    snapshot_bytes = b"synthetic immutable sqlite snapshot"
    snapshot_hash = _sha(snapshot_bytes)
    monkeypatch.setattr(preview, "EXPECTED_SNAPSHOT_SHA256", snapshot_hash)
    coverage = dict(preview.EXPECTED_FULL_REPAIR_COVERAGE)

    files: dict[str, Path] = {}
    for relative in preview.REQUIRED_ARCHIVE_PATHS.values():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        files[relative] = path
    for relative in preview.RECOVERY_INPUT_METADATA_PATHS.values():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic archived recovery input")
        files[relative] = path
    for suffix, payload in (("-wal", b""), ("-shm", b"s" * 32)):
        relative = preview.REQUIRED_ARCHIVE_PATHS["snapshot"] + suffix
        path = root.joinpath(*relative.split("/"))
        path.write_bytes(payload)
        files[relative] = path
    files[preview.REQUIRED_ARCHIVE_PATHS["snapshot"]].write_bytes(snapshot_bytes)

    price_body = {
        "schema_version": "historical-price-spike-repair-20260921.v1",
        "receipt_kind": "historical_price_spike_repair",
        "status": "applied",
        "source_date": "20260520",
        "corrected_at": "2026-09-22T07:30:49.544569+00:00",
        "available_at": None,
        "historical_decision_time_available": False,
        "formal_training_allowed": False,
        "promotion_eligible": False,
    }
    price_receipt = _seal(price_body, "receipt_sha256")
    _write_json(files[preview.REQUIRED_ARCHIVE_PATHS["price_receipt"]], price_receipt)
    _write_json(files[preview.REQUIRED_ARCHIVE_PATHS["price_pending"]], {
        "status": "applied_receipt_written", "source_date": "20260520",
    })
    technical_body = {
        "schema_version": "technical-indicator-repair-20260921.v1",
        "receipt_kind": "technical_indicator_repair",
        "status": "applied",
        "source_date": "20260520",
        "available_at": None,
        "formal_training_allowed": False,
        "promotion_eligible": False,
        "price_receipt_sha256": price_receipt["receipt_sha256"],
    }
    technical_receipt = _seal(technical_body, "receipt_sha256")
    _write_json(files[preview.REQUIRED_ARCHIVE_PATHS["technical_receipt"]], technical_receipt)
    _write_json(files[preview.REQUIRED_ARCHIVE_PATHS["technical_pending"]], {
        "status": "receipt_written", "source_date": "20260520",
    })

    recovery_body = {
        "schema_version": "ml-daily-price-revision-isolated-recovery.v1",
        "receipt_kind": "isolated_research_recovery",
        "status": "passed", "research_candidate_only": True,
        "formal_data_written": False, "formal_training_allowed": False,
        "historical_pit_eligible": False, "promotion_eligible": False,
        "database_sha256_after": snapshot_hash,
        "input_hashes": {
            "price_pending_file": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["price_pending"]]),
            "price_receipt_file": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["price_receipt"]]),
            "technical_pending_file": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["technical_pending"]]),
            "technical_receipt_file": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["technical_receipt"]]),
            **{
                key: _file_sha(files[relative])
                for key, relative in preview.RECOVERY_INPUT_METADATA_PATHS.items()
            },
        },
        "pending_state": {"changed": False},
        "rows": {"plan_external_before_sha256": "sha256:out", "plan_external_after_sha256": "sha256:out"},
    }
    recovery = _seal(recovery_body, "receipt_sha256")
    _write_json(files[preview.REQUIRED_ARCHIVE_PATHS["recovery"]], recovery)
    verifier_body = {
        "schema_version": "ml-daily-price-revision-technical-snapshot-evidence.v1",
        "status": "passed", "purpose": "late_obtained_research_source_evidence_only",
        "formal_pit_gate_changed": False, "historical_available_at": None,
        "snapshot": {"sha256_after": snapshot_hash},
        "coverage": coverage,
        "receipt_identity": {
            "price_receipt_file_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["price_receipt"]]),
            "technical_receipt_file_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["technical_receipt"]]),
            "price_receipt_body_sha256": price_receipt["receipt_sha256"],
            "technical_receipt_body_sha256": technical_receipt["receipt_sha256"],
            "technical_price_receipt_identity_match": True,
        },
    }
    verification = _seal(verifier_body, "evidence_sha256")
    _write_json(files[preview.REQUIRED_ARCHIVE_PATHS["verification"]], verification)

    observed_rows = []
    symbols = (("0050", "complete_ohlc", []), ("2321", "missing_ohlc_excluded_from_fit", ["open"]))
    for symbol, status, missing in symbols:
        row_revision = {
            "availability_status": "late_obtained",
            "historical_available_at": "2026-05-20T00:00:00+08:00" if historical_claim else None,
            "historical_decision_time_available": False,
            "source_db_snapshot_sha256": snapshot_hash,
            "observed_at": OBSERVED,
            "repair_receipt_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["price_receipt"]]),
            "isolated_recovery_receipt_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["recovery"]]),
            "technical_repair_receipt_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["technical_receipt"]]),
        }
        observed_rows.append({
            "schema_version": "ml-daily-price-revision-research-row.v1",
            "dataset_id": preview.EXPECTED_DATASET_ID,
            "date": "20260520", "symbol": symbol,
            "price_row_status": status, "missing_source_fields": missing,
            "source_revision": row_revision,
            "technical_indicators": {"Date": "20260520", "RSI": "55.0"},
            "feature_contract_status": "not_assessed", "label_status": "not_materialized",
        })
    rows_bytes = b"".join(_canonical(row) + b"\n" for row in observed_rows)
    files[preview.REQUIRED_ARCHIVE_PATHS["rows"]].write_bytes(rows_bytes)
    rows_hash = _sha(rows_bytes)
    monkeypatch.setattr(preview, "EXPECTED_ROWS_SHA256", rows_hash)
    monkeypatch.setattr(preview, "EXPECTED_MANIFEST_SHA256", "pending")

    manifest = {
        "schema_version": preview.MANIFEST_SCHEMA,
        "dataset_id": preview.EXPECTED_DATASET_ID,
        "run_id": preview.EXPECTED_RUN_ID,
        "status": "accepted_research_source_snapshot", "created_at": OBSERVED,
        "authoritative_identity": {
            "dataset_id": preview.EXPECTED_DATASET_ID, "run_id": preview.EXPECTED_RUN_ID,
            "content_sha256": "sha256:identity",
        },
        "artifact": {
            "row_count": 2, "sha256": rows_hash, "feature_contract_status": "not_assessed",
            "labels_materialized": False, "label_maturity_status": "not_materialized",
            "model_training_input_compatible": False,
        },
        "snapshot": {
            "sha256": snapshot_hash, "size_bytes": len(snapshot_bytes),
            "sqlite_mode": "read_only_query_only", "sidecars": {"-wal": 0, "-shm": 32},
        },
        "source_revision": {
            "source_date": "20260520", "corrected_at": price_body["corrected_at"],
            "availability_status": "late_obtained", "historical_available_at": None,
            "historical_decision_time_available": False, "pending_marker_preserved": True,
            "pending_marker_still_blocks_formal_pit": True,
            "final_receipt_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["price_receipt"]]),
            "pending_receipt_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["price_pending"]]),
            "technical_pending_marker_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["technical_pending"]]),
        },
        "technical_repair_evidence": {
            "receipt_file_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["technical_receipt"]]),
            "recovery_receipt_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["recovery"]]),
            "recovery_receipt_body_sha256": recovery["receipt_sha256"],
            "tracked_verification_file_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["verification"]]),
            "tracked_verification_evidence_sha256": verification["evidence_sha256"],
            "recovery_cell_diff_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["recovery_cell_diff"]]),
            "recovery_row_hashes_sha256": _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["recovery_affected_rows"]]),
        },
        "coverage": {
            "affected_rows_expected": 2, "daily_price_rows_matched": 2,
            "technical_rows_matched": 2,
            "full_repair_window_after_cells_verified": coverage["after_cells"],
            "full_repair_window_untouched_cells_verified": coverage["untouched_cells"],
        },
        "price_row_quality": {
            "total_rows": 2, "complete_ohlc_rows": 1, "missing_ohlc_rows": 1,
        },
        "eligibility": {
            "research_only": True, "formal_training_allowed": False,
            "formal_oos_allowed": False, "historical_pit_allowed": False,
            "promotion_eligible": False, "production_alpha_bp": 0,
            "labels_available_for_fit": False,
        },
    }
    _write_json(files[preview.REQUIRED_ARCHIVE_PATHS["manifest"]], manifest)
    manifest_hash = _file_sha(files[preview.REQUIRED_ARCHIVE_PATHS["manifest"]])
    monkeypatch.setattr(preview, "EXPECTED_MANIFEST_SHA256", manifest_hash)
    _write_json(files[preview.REQUIRED_ARCHIVE_PATHS["gate_probe"]], {
        "dataset_manifest_sha256": manifest_hash, "dataset_rows_sha256": rows_hash,
        "snapshot_sha256": snapshot_hash,
        "results": [
            {"call": "check_daily_price_source_revision", "status": "blocked",
             "error_type": "DailyPriceSourceRevisionError", "symbols": [symbol]}
            for symbol in ("0050", "1256", "1477")
        ] + [{"call": "validate_research_training_publication", "status": "blocked",
              "error_type": "ValueError", "error": "unsupported research union manifest schema"}],
    })

    transfer_files = []
    total_size = 0
    for relative, path in files.items():
        size = path.stat().st_size
        total_size += size
        transfer_files.append({
            "destination_relative_path": relative,
            "size_bytes": size,
            "sha256": _file_sha(path),
        })
    transfer = {
        "schema_version": preview.TRANSFER_SCHEMA,
        "created_at_utc": "2026-09-23T00:16:50Z",
        "purpose": "immutable research and audit custody; not a model release or formal data source",
        "destination_preexisted": False,
        "destination_root": str(root.resolve()),
        "total_file_count": len(transfer_files), "total_size_bytes": total_size,
        "files": transfer_files,
    }
    _write_json(root / "transfer_receipt.json", transfer)
    return root, _file_sha(root / "transfer_receipt.json")


def test_preview_reports_late_source_and_keeps_fit_and_pit_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, transfer_sha = _fixture(tmp_path, monkeypatch)
    result = preview.build_revision_acceptance_preview(
        archive_root=root, training_as_of="2026-09-23T00:00:00Z",
        expected_transfer_receipt_sha256=transfer_sha,
    )
    output = json.loads(Path(result["output_path"]).read_text(encoding="utf-8"))
    assert result["row_count"] == 2
    assert result["complete_ohlc_rows"] == 1
    assert result["missing_ohlc_rows"] == 1
    assert output["rows"][0]["source_revision"]["historical_available_at"] is None
    assert output["rows"][0]["source_revision"]["late_obtained"] is True
    assert output["rows"][0]["labels"][2]["horizon_end_date"] is None
    assert output["rows"][0]["labels"][2]["label_available_at"] is None
    assert output["rows"][0]["labels"][2]["maturity_status"] == "pending_evidence"
    assert output["decision"]["future_research_candidate_accepted"] is False
    assert output["decision"]["historical_pit_eligible"] is False
    assert output["decision"]["formal_training_allowed"] is False
    assert output["decision"]["fit_performed"] is False
    assert output["archive_provenance"]["full_26_file_content_hashes_recomputed"] is False


def test_transfer_hash_mismatch_fails_closed_without_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = _fixture(tmp_path, monkeypatch)
    with pytest.raises(preview.AcceptancePreviewError, match="transfer receipt SHA-256"):
        preview.build_revision_acceptance_preview(
            archive_root=root, training_as_of="2026-09-23T00:00:00Z",
            expected_transfer_receipt_sha256="sha256:" + "0" * 64,
        )
    assert not list((preview.REPO_ROOT / "output" / "qa").rglob("acceptance_preview.json"))


def test_historical_available_at_claim_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, transfer_sha = _fixture(tmp_path, monkeypatch, historical_claim=True)
    with pytest.raises(preview.AcceptancePreviewError, match="historical-availability claim"):
        preview.build_revision_acceptance_preview(
            archive_root=root, training_as_of="2026-09-23T00:00:00Z",
            expected_transfer_receipt_sha256=transfer_sha,
        )


def test_preview_output_is_create_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, transfer_sha = _fixture(tmp_path, monkeypatch)
    kwargs = {
        "archive_root": root,
        "training_as_of": "2026-09-23T00:00:00Z",
        "expected_transfer_receipt_sha256": transfer_sha,
    }
    first = preview.build_revision_acceptance_preview(**kwargs)
    original = Path(first["output_path"]).read_bytes()
    with pytest.raises(FileExistsError, match="create-only preview already exists"):
        preview.build_revision_acceptance_preview(**kwargs)
    assert Path(first["output_path"]).read_bytes() == original
