from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from data_module import portfolio_ml_dataset_assembler as dataset_assembler
from data_module import ml_daily_price_source_quality as source_quality
from data_module.ml_daily_price_source_quality import DailyPriceSourceQualityError
from data_module.ml_storage_capacity import (
    SCHEDULED_REQUIRED_FREE_BYTES,
    SCHEDULED_SAFETY_RESERVE_BYTES,
)
from scripts import build_ml_pit_year_shards as pit_builder
from scripts.scheduled import run_ml_raw_pit_refresh as runner


_TAIPEI = ZoneInfo("Asia/Taipei")


def _write_formal_market_revision_run(
    database_path: Path,
    *,
    run_id: str,
    source_start_date: str = "2024-01-02",
    source_end_date: str = "2024-01-31",
    state: str = "applied",
    marker_database_path: Path | None = None,
) -> Path:
    from data_module.formal_market_revision import RECEIPT_DIR

    run_dir = database_path.parent.parent / RECEIPT_DIR / run_id
    run_dir.mkdir(parents=True)
    identity = str((marker_database_path or database_path).resolve())
    plan = {
        "schema_version": "formal-market-repair.v1",
        "database_path": identity,
        "source_start_date": source_start_date,
        "source_end_date": source_end_date,
    }
    plan_bytes = json.dumps(plan, sort_keys=True).encode("utf-8")
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    journal = {
        "schema_version": "formal-market-repair.v1",
        "plan_sha256": plan_hash,
    }
    marker: dict[str, object] = {
        "schema_version": "formal-market-revision.v1",
        "database_path": identity,
        "source_start_date": source_start_date,
        "source_end_date": source_end_date,
        "state": state,
    }
    (run_dir / "plan.json").write_bytes(plan_bytes)
    (run_dir / "journal.json").write_text(
        json.dumps(journal, sort_keys=True), encoding="utf-8"
    )
    if state == "applied":
        receipt_bytes = json.dumps(
            {
                "schema_version": "formal-market-repair.v1",
                "plan_sha256": plan_hash,
            },
            sort_keys=True,
        ).encode("utf-8")
        (run_dir / "receipt.json").write_bytes(receipt_bytes)
        marker["receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    elif state == "rolled_back":
        rollback_bytes = b'{"state":"rolled_back"}'
        (run_dir / "rollback.json").write_bytes(rollback_bytes)
        marker["rollback_sha256"] = hashlib.sha256(rollback_bytes).hexdigest()
    (run_dir / "revision.json").write_text(
        json.dumps(marker, sort_keys=True), encoding="utf-8"
    )
    return run_dir


def _configure_runnable_raw_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path]:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    _write_freshness_status(output_root)
    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"sqlite-placeholder")
    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )
    monkeypatch.setattr(
        runner,
        "_storage_preflight",
        lambda *_args, **_kwargs: {"within_minimum_free_space": True},
    )
    monkeypatch.setattr(
        runner,
        "_capacity_evaluation",
        lambda *_args, **_kwargs: SimpleNamespace(
            within_budget=True,
            as_dict=lambda: {"within_budget": True},
        ),
    )
    monkeypatch.setattr(
        runner, "_direct_chain_instance_lock_present", lambda _root: False
    )

    class _FakeLock:
        owner_pid = 424_242

        def authorize_child(self, _child_pid: int) -> None:
            return None

    fake_lock = _FakeLock()
    monkeypatch.setattr(runner, "_acquire_lock", lambda _path: fake_lock)
    monkeypatch.setattr(runner, "_release_lock", lambda _lock: None)
    return data_root, output_root, database


def _write_freshness_status(
    output_root: Path,
    *,
    status: str = "passed",
    daily_date: str = "2026-08-12",
    technical_date: str = "2026-08-12",
    completed_at: str = "2026-08-12T07:00:00+08:00",
) -> Path:
    status_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "status": status,
                "completed_at": completed_at,
                "steps": [
                    {
                        "name": "check_overview_after",
                        "result": {
                            "daily_data": {"latest_date": daily_date},
                            "technical_indicators": {
                                "latest_date": technical_date
                            },
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return status_path


def _write_raw_publication(
    raw_root: Path,
    *,
    decision_at: str = "2026-08-12T08:30:00+08:00",
) -> Path:
    publication_dir = raw_root / "runs" / "pit-test"
    dataset_dir = publication_dir / "all_field_enriched"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset = {
        "schema_version": "ml-pit-year-shard-dataset.v1",
        "stage": "raw_pit_observations",
        "format": "gzip_jsonl",
        "dataset_id": "all_field_enriched",
        "decision_at": decision_at,
        "history_start_date": "2014-01-01",
        "features": [],
        "safety": {
            "formal_dataset": True,
            "unreviewed_included": False,
            "excluded_leakage_included": False,
            "research_shadow_isolated": True,
            "raw_float_persistence_allowed": False,
        },
    }
    dataset["manifest_hash"] = dataset_assembler._sha256_json(dataset)
    dataset_path = dataset_dir / "manifest.json"
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")

    publication = {
        "schema_version": "ml-pit-year-shards.v1",
        "stage": "raw_pit_observations",
        "publication_id": "pit-test",
        "decision_at": decision_at,
        "history_start_date": "2014-01-01",
        "scope": {"all_universe": True},
        "datasets": {
            "all_field_enriched": {
                "manifest_path": "all_field_enriched/manifest.json",
                "manifest_hash": dataset["manifest_hash"],
            }
        },
    }
    publication["manifest_hash"] = runner._canonical_sha256(publication)
    publication_path = publication_dir / "manifest.json"
    publication_path.write_text(json.dumps(publication), encoding="utf-8")

    pointer_path = raw_root / "latest_manifest.json"
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(
        json.dumps(
            {
                "schema_version": "ml-pit-year-shards-pointer.v1",
                "publication_id": "pit-test",
                "manifest_path": "runs/pit-test/manifest.json",
                "manifest_hash": publication["manifest_hash"],
            }
        ),
        encoding="utf-8",
    )
    return publication_path


def _write_source_quality_report(
    path: Path,
    *,
    candidate_count: int = 0,
    candidate_sample_limit: int = 64,
    candidates: list[dict[str, object]] | None = None,
    full_candidates: list[dict[str, object]] | None = None,
    candidate_samples_truncated: bool | None = None,
) -> dict[str, object]:
    samples = [] if candidates is None else candidates
    full_rows = samples if full_candidates is None else full_candidates
    if candidate_samples_truncated is None:
        candidate_samples_truncated = candidate_count > len(samples)
    evidence_path = path.with_suffix(".candidates.jsonl")
    evidence_writer = source_quality._CandidateEvidenceWriter(
        evidence_path,
        source_roots=(),
    )
    for candidate in full_rows:
        evidence_writer.write(candidate)
    evidence_manifest = evidence_writer.finalize()
    report: dict[str, object] = {
        "schema_version": "portfolio-ml-daily-price-source-quality.v1",
        "status": "source_quality_pass" if candidate_count == 0 else "quarantine_required",
        "read_only": True,
        "repair_performed": False,
        "formal_training_allowed": candidate_count == 0,
        "source": {"sqlite_mode": "ro", "sqlite_query_only": True},
        "candidate_count": candidate_count,
        "candidate_sample_count": len(samples),
        "candidate_sample_limit": candidate_sample_limit,
        "candidate_samples_truncated": candidate_samples_truncated,
        "candidate_digest": evidence_manifest["candidate_digest"],
        "candidates": samples,
        "candidate_evidence": evidence_manifest,
    }
    report["report_hash"] = runner._canonical_sha256(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return report


def test_core_freshness_proof_requires_current_core_dates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_root = tmp_path / "output"
    status_path = _write_freshness_status(output_root)
    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )

    proof = runner._core_freshness_proof(status_path)

    assert proof.latest_core_date.isoformat() == "2026-08-12"
    assert proof.decision_at == "2026-08-12T08:30:00+08:00"
    assert proof.data_update_status == "passed"


def test_extract_source_quality_summary_keeps_only_bounded_builder_payload() -> None:
    summary = {
        "candidate_count": 4_476_508,
        "classification_counts": {
            "canonical_daily_row_missing": 1,
            "sqlite_row_mismatch_against_canonical_daily_csv": 1,
        },
        "samples": [{"symbol": "2330", "date": "2026-09-08"}],
    }

    extracted = runner._extract_source_quality_summary(
        "diagnostic line\n"
        + json.dumps(
            {
                "status": "blocked",
                "source_quality_summary": summary,
                "candidates": ["the full report is never emitted"],
            }
        )
    )

    assert extracted == summary


def test_builder_command_persists_per_run_source_quality_report_and_bound(
    tmp_path: Path,
) -> None:
    proof = runner._CoreFreshnessProof(
        latest_core_date=date(2026, 8, 12),
        decision_at="2026-08-12T08:30:00+08:00",
        completed_at=datetime(2026, 8, 12, 7, 0, tzinfo=_TAIPEI),
        data_update_status="passed",
    )
    report_path = tmp_path / "scheduled" / "source_quality" / "run-001.json"

    command = runner._builder_command(
        database=tmp_path / "twstock.db",
        raw_root=tmp_path / "raw",
        proof=proof,
        history_start_date="2014-01-01",
        batch_size=128,
        compression_level=6,
        daily_price_source_dirs=(tmp_path / "daily_price",),
        source_quality_report_path=report_path,
        source_quality_candidate_sample_limit=32,
    )

    assert command[command.index("--source-quality-report") + 1] == str(
        report_path.resolve()
    )
    assert command[
        command.index("--source-quality-candidate-evidence") + 1
    ] == str(report_path.with_suffix(".candidates.jsonl").resolve())
    assert command[
        command.index("--source-quality-candidate-sample-limit") + 1
    ] == "32"


def test_source_quality_evidence_readback_rejects_sample_count_above_total(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "source-quality.json"
    _write_source_quality_report(
        report_path,
        candidate_count=1,
        candidates=[
            {"date": "2026-08-12", "symbol": "2330"},
            {"date": "2026-08-13", "symbol": "2330"},
        ],
        candidate_samples_truncated=False,
    )

    readback = runner._source_quality_evidence_readback(
        report_path,
        expected_candidate_sample_limit=64,
    )

    assert readback["readback_status"] == "invalid"
    assert readback["reason"] == "source_quality_report_metadata_invalid"
    assert readback["candidate_rows_complete"] is False


def test_source_quality_evidence_readback_rejects_duplicate_sample_keys(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "source-quality.json"
    _write_source_quality_report(
        report_path,
        candidate_count=2,
        candidates=[
            {"date": "2026-08-12", "symbol": "2330"},
            {"date": "2026-08-12", "symbol": "2330"},
        ],
        candidate_samples_truncated=False,
    )

    readback = runner._source_quality_evidence_readback(
        report_path,
        expected_candidate_sample_limit=64,
    )

    assert readback["readback_status"] == "invalid"
    assert readback["reason"] == "source_quality_report_metadata_invalid"
    assert readback["candidate_unique_key_scope"] == "bounded_samples_only"


def test_source_quality_evidence_readback_rejects_missing_sidecar(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "source-quality.json"
    _write_source_quality_report(
        report_path,
        candidate_count=1,
        candidates=[{"date": "2026-08-12", "symbol": "2330"}],
    )
    report_path.with_suffix(".candidates.jsonl").unlink()

    readback = runner._source_quality_evidence_readback(
        report_path,
        expected_candidate_sample_limit=64,
    )

    assert readback["readback_status"] == "invalid"
    assert readback["candidate_evidence_status"] == "missing"
    assert readback["candidate_rows_complete"] is False


def test_source_quality_evidence_readback_rejects_tampered_sidecar(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "source-quality.json"
    _write_source_quality_report(
        report_path,
        candidate_count=1,
        candidates=[{"date": "2026-08-12", "symbol": "2330"}],
    )
    sidecar_path = report_path.with_suffix(".candidates.jsonl")
    sidecar_path.write_text(
        sidecar_path.read_text(encoding="utf-8")
        + json.dumps({"date": "2026-08-13", "symbol": "2330"})
        + "\n",
        encoding="utf-8",
    )

    readback = runner._source_quality_evidence_readback(
        report_path,
        expected_candidate_sample_limit=64,
    )

    assert readback["readback_status"] == "invalid"
    assert readback["candidate_evidence_status"] == "invalid"
    assert readback["candidate_rows_complete"] is False


def test_source_quality_evidence_identity_is_non_overwriting_across_retries(
    tmp_path: Path,
) -> None:
    started_at = datetime(2026, 8, 12, 8, 30, tzinfo=_TAIPEI)
    first_id, first_path = runner._new_source_quality_evidence_identity(
        run_root=tmp_path / "scheduled" / "ml_raw_pit_refresh",
        started_at=started_at,
    )
    second_id, second_path = runner._new_source_quality_evidence_identity(
        run_root=tmp_path / "scheduled" / "ml_raw_pit_refresh",
        started_at=started_at,
    )
    first_bytes = b"first-run"
    first_path.parent.mkdir(parents=True, exist_ok=True)
    first_path.write_bytes(first_bytes)
    second_path.parent.mkdir(parents=True, exist_ok=True)
    second_path.write_bytes(b"second-run")

    assert first_id != second_id
    assert first_path != second_path
    assert first_path.read_bytes() == first_bytes


def test_builder_quality_summary_bounds_candidates_and_keeps_report_hash() -> None:
    report = {
        "schema_version": "quality.v1",
        "status": "quarantine_required",
        "read_only": True,
        "repair_performed": False,
        "formal_training_allowed": False,
        "candidate_count": 4_476_508,
        "classification_counts": {
            "canonical_daily_row_missing": 4_476_507,
            "sqlite_row_mismatch_against_canonical_daily_csv": 1,
        },
        "affected_date_counts": {
            "2026-09-07": 4_476_507,
            "2026-09-08": 1,
        },
        "report_hash": "sha256:" + "a" * 64,
        "candidates": [
            {
                "symbol": "2330",
                "date": "2026-09-07",
                "classification": "canonical_daily_row_missing",
                "differing_fields": ["open"],
                "detector": {
                    "previous_close": "100",
                    "current_open": "10",
                    "next_open": None,
                    "threshold_factor": "10",
                    "policy_version": "guard.v1",
                    "future_source_row_used": False,
                },
                "canonical_file": {
                    "path": "D:/daily_price/20260907.csv",
                    "status": "missing",
                    "file_sha256": None,
                },
                "canonical_candidates": [
                    {
                        "row": {},
                        "file": {
                            "path": "D:/daily_price_tpex/20260907.csv",
                            "status": "valid",
                            "file_sha256": "sha256:" + "c" * 64,
                            "market": "TPEX",
                            "source_directory": "D:/daily_price_tpex",
                        },
                    }
                ],
            }
        ],
    }

    summary = pit_builder._compact_source_quality_summary(report)

    assert summary["candidate_count"] == 4_476_508
    assert summary["classification_counts"] == report["classification_counts"]
    assert summary["affected_date_count"] == 2
    samples = summary["samples"]
    assert isinstance(samples, list)
    assert len(samples) == 1
    assert summary["report_hash"] == report["report_hash"]
    assert "candidates" not in summary
    assert summary["samples"][0]["canonical_candidates"][0]["market"] == "TPEX"


def test_builder_cli_emits_compact_quality_summary_on_guard_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = {
        "schema_version": "quality.v1",
        "status": "quarantine_required",
        "read_only": True,
        "repair_performed": False,
        "formal_training_allowed": False,
        "candidate_count": 2,
        "classification_counts": {"canonical_daily_row_missing": 2},
        "affected_date_counts": {"2026-08-12": 2},
        "report_hash": "sha256:" + "b" * 64,
        "candidates": [
            {
                "symbol": "2330",
                "date": "2026-08-12",
                "classification": "canonical_daily_row_missing",
            }
        ],
    }

    def raise_quality_error(*_args: object, **_kwargs: object) -> object:
        raise DailyPriceSourceQualityError(
            "daily price source quality quarantine required: 2 candidate rows",
            report=report,
        )

    monkeypatch.setattr(pit_builder.PITYearShardExporter, "build", raise_quality_error)
    database = tmp_path / "source.db"
    database.write_bytes(b"sqlite-placeholder")

    exit_code = pit_builder.main(
        [
            "--database",
            str(database),
            "--output-dir",
            str(tmp_path / "out"),
            "--decision-at",
            "2026-08-12T08:30:00+08:00",
            "--symbols",
            "2330",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["error_type"] == "DailyPriceSourceQualityError"
    assert payload["source_quality_summary"]["candidate_count"] == 2
    assert "candidates" not in payload["source_quality_summary"]


def test_main_persists_bounded_source_quality_summary_on_builder_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    _write_freshness_status(output_root)
    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"sqlite-placeholder")
    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )
    monkeypatch.setattr(
        runner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(
            total=700 * 1024**3,
            used=100 * 1024**3,
            free=600 * 1024**3,
        ),
    )
    monkeypatch.setattr(runner, "_direct_chain_instance_lock_present", lambda _root: False)

    class _FakeLock:
        owner_pid = 424_242

        def authorize_child(self, _child_pid: int) -> None:
            return None

    fake_lock = _FakeLock()
    monkeypatch.setattr(runner, "_acquire_lock", lambda _path: fake_lock)
    monkeypatch.setattr(runner, "_release_lock", lambda _lock: None)
    monkeypatch.setattr(
        runner,
        "build_heavy_chain_reservation_handoff_environment",
        lambda _lock, *, environment, parent_pid: environment,
    )
    summary = {
        "candidate_count": 100,
        "classification_counts": {
            "canonical_daily_row_missing": 100,
        },
        "samples": [{"symbol": "2330", "classification": "test"}],
    }
    full_candidates = [
        {
            "date": "2026-08-12",
            "symbol": f"{index:04d}",
            "classification": "test",
        }
        for index in range(100)
    ]

    class _FakeBuilderProcess:
        pid = 424_243
        returncode = 2

        def communicate(self) -> tuple[str, str]:
            return (
                json.dumps(
                    {
                        "status": "blocked",
                        "error_type": "DailyPriceSourceQualityError",
                        "source_quality_summary": summary,
                    }
                ),
                "",
            )

    def fake_popen(command: list[str], **_kwargs: object) -> _FakeBuilderProcess:
        report_path = Path(
            command[command.index("--source-quality-report") + 1]
        )
        _write_source_quality_report(
            report_path,
            candidate_count=100,
            candidates=full_candidates[:64],
            full_candidates=full_candidates,
        )
        return _FakeBuilderProcess()

    monkeypatch.setattr(
        runner.subprocess,
        "Popen",
        fake_popen,
    )

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--database",
            str(database),
        ]
    )

    receipt = json.loads(
        (
            output_root
            / "scheduled"
            / "ml_raw_pit_refresh"
            / "latest_status.json"
        ).read_text(encoding="utf-8")
    )
    assert exit_code == 1
    assert receipt["status"] == "failed"
    assert receipt["builder_returncode"] == 2
    assert receipt["source_quality_summary"] == summary
    assert receipt["source_quality_evidence"]["readback_status"] == "verified"
    assert receipt["source_quality_evidence"]["candidate_count"] == 100
    assert receipt["source_quality_evidence"]["candidate_sample_count"] == 64
    assert receipt["source_quality_evidence"]["candidate_samples_truncated"] is True
    assert receipt["source_quality_evidence"]["candidate_rows_complete"] is True
    assert receipt["source_quality_evidence"]["candidate_evidence_row_count"] == 100
    assert receipt["source_quality_evidence"]["candidate_full_unique_key_count"] == 100
    assert receipt["source_quality_evidence"]["candidate_full_unique_key_count_verified"] is True


def test_source_revision_blocker_distinguishes_holds_from_receipt_validation(
    tmp_path: Path,
) -> None:
    decision_at = "2026-08-12T08:30:00+08:00"

    no_revision_db = tmp_path / "no-revision" / "sqlite" / "twstock.db"
    no_revision_db.parent.mkdir(parents=True)
    no_revision_db.write_bytes(b"sqlite-placeholder")
    assert runner._source_revision_blocker(no_revision_db, decision_at) is None

    future_revision_db = tmp_path / "future-revision" / "sqlite" / "twstock.db"
    future_revision_db.parent.mkdir(parents=True)
    future_revision_db.write_bytes(b"sqlite-placeholder")
    _write_formal_market_revision_run(
        future_revision_db,
        run_id="future",
        source_start_date="2099-01-02",
        source_end_date="2099-01-31",
    )
    assert runner._source_revision_blocker(future_revision_db, decision_at) is None

    rolled_back_db = tmp_path / "rolled-back" / "sqlite" / "twstock.db"
    rolled_back_db.parent.mkdir(parents=True)
    rolled_back_db.write_bytes(b"sqlite-placeholder")
    _write_formal_market_revision_run(
        rolled_back_db,
        run_id="rolled-back",
        state="rolled_back",
    )
    assert runner._source_revision_blocker(rolled_back_db, decision_at) is None

    pending_db = tmp_path / "pending" / "sqlite" / "twstock.db"
    pending_db.parent.mkdir(parents=True)
    pending_db.write_bytes(b"sqlite-placeholder")
    _write_formal_market_revision_run(
        pending_db,
        run_id="pending",
        state="pending",
    )
    pending_blocker = runner._source_revision_blocker(pending_db, decision_at)
    assert pending_blocker is not None
    assert pending_blocker["source_date"] == "2024-01-02"
    assert pending_blocker["error_type"] == "DailyPriceSourceRevisionError"
    assert "formal market source revision blocks historical PIT" in str(
        pending_blocker["error"]
    )

    missing_receipt_db = tmp_path / "missing-receipt" / "sqlite" / "twstock.db"
    missing_receipt_db.parent.mkdir(parents=True)
    missing_receipt_db.write_bytes(b"sqlite-placeholder")
    missing_run = _write_formal_market_revision_run(
        missing_receipt_db,
        run_id="missing-receipt",
    )
    (missing_run / "receipt.json").unlink()
    missing_blocker = runner._source_revision_blocker(
        missing_receipt_db, decision_at
    )
    assert missing_blocker is not None
    assert missing_blocker["blocker_kind"] == "receipt_validation_failure"
    assert str(missing_blocker["error"]).startswith("大盤來源修訂紀錄無法驗證：")

    broken_chain_db = tmp_path / "broken-chain" / "sqlite" / "twstock.db"
    broken_chain_db.parent.mkdir(parents=True)
    broken_chain_db.write_bytes(b"sqlite-placeholder")
    broken_run = _write_formal_market_revision_run(
        broken_chain_db,
        run_id="broken-chain",
    )
    journal_path = broken_run / "journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["plan_sha256"] = "0" * 64
    journal_path.write_text(json.dumps(journal, sort_keys=True), encoding="utf-8")
    broken_blocker = runner._source_revision_blocker(broken_chain_db, decision_at)
    assert broken_blocker is not None
    assert broken_blocker["blocker_kind"] == "receipt_validation_failure"
    assert "無法驗證" in str(broken_blocker["error"])

    mismatched_db = tmp_path / "mismatched" / "sqlite" / "twstock.db"
    mismatched_db.parent.mkdir(parents=True)
    mismatched_db.write_bytes(b"sqlite-placeholder")
    _write_formal_market_revision_run(
        mismatched_db,
        run_id="wrong-database",
        marker_database_path=mismatched_db.with_name("other.db"),
    )
    mismatch_blocker = runner._source_revision_blocker(mismatched_db, decision_at)
    assert mismatch_blocker is not None
    assert mismatch_blocker["source_date"] is None
    assert "無法驗證" in str(mismatch_blocker["error"])
    receipt_reference = mismatch_blocker["receipt_reference"]
    assert isinstance(receipt_reference, dict)
    assert receipt_reference["kind"] == "diagnostic_lookup_only"
    assert str(receipt_reference["path"]).endswith("revision.json")
    assert mismatch_blocker["receipt_reference_is_immutable_evidence"] is False


def test_source_revision_blocker_classifies_known_holds_and_unknown_rejections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"sqlite-placeholder")
    decision_at = "2026-09-30T08:30:00+08:00"

    def raise_guard(message: str) -> None:
        def _raise(**_kwargs: object) -> None:
            raise runner.DailyPriceSourceRevisionError(message)

        monkeypatch.setattr(runner, "check_daily_price_source_revision", _raise)

    raise_guard(
        "historical price repair receipt blocks this PIT prefix; "
        "source_date=2026-09-23"
    )
    temporal_blocker = runner._source_revision_blocker(database, decision_at)
    assert temporal_blocker is not None
    assert temporal_blocker["blocker_kind"] == "temporal_source_revision"
    assert temporal_blocker["source_date"] == "2026-09-23"

    raise_guard("unexpected revision policy rejection")
    generic_blocker = runner._source_revision_blocker(database, decision_at)
    assert generic_blocker is not None
    assert generic_blocker["blocker_kind"] == "generic_guard_rejection"
    assert generic_blocker["error"] == "unexpected revision policy rejection"


def test_main_classifies_source_revision_before_spawning_builder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root, output_root, database = _configure_runnable_raw_main(
        tmp_path, monkeypatch
    )
    run_dir = _write_formal_market_revision_run(
        database,
        run_id="applied-source-revision",
        source_start_date="2014-01-02",
        source_end_date="2026-09-23",
    )
    database_hash_before = hashlib.sha256(database.read_bytes()).hexdigest()
    marker_path = run_dir / "revision.json"
    marker_hash_before = hashlib.sha256(marker_path.read_bytes()).hexdigest()
    builder_called = False

    def fail_builder(*_args: object, **_kwargs: object) -> None:
        nonlocal builder_called
        builder_called = True
        raise AssertionError("builder must not start after the revision guard blocks")

    monkeypatch.setattr(runner.subprocess, "Popen", fail_builder)

    exit_code = runner.main(
        ["--data-root", str(data_root), "--output-root", str(output_root), "--database", str(database)]
    )

    status_path = (
        output_root
        / "scheduled"
        / "ml_raw_pit_refresh"
        / "latest_status.json"
    )
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert builder_called is False
    assert payload["status"] == "blocked_source_revision"
    assert payload["decision_at"] == "2026-08-12T08:30:00+08:00"
    assert payload["source_revision_gate"]["source_date"] == "2014-01-02"
    assert payload["source_revision_gate"]["error_type"] == (
        "DailyPriceSourceRevisionError"
    )
    assert payload["source_revision_gate"]["blocker_kind"] == (
        "temporal_source_revision"
    )
    assert payload["source_revision_gate"]["receipt_reference_is_immutable_evidence"] is False
    assert "historical PIT from 2014-01-02" in payload["error"]
    assert payload["source_quality_evidence"]["reason"] == "builder_not_started"
    assert not (output_root / "release_v4" / "ml_pit_year_shards" / "latest_manifest.json").exists()
    assert hashlib.sha256(database.read_bytes()).hexdigest() == database_hash_before
    assert hashlib.sha256(marker_path.read_bytes()).hexdigest() == marker_hash_before


def test_main_fails_closed_when_source_revision_guard_raises_unexpected_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root, output_root, database = _configure_runnable_raw_main(
        tmp_path, monkeypatch
    )
    builder_called = False

    def fail_guard(**_kwargs: object) -> None:
        raise RuntimeError("revision guard internal failure")

    def fail_builder(*_args: object, **_kwargs: object) -> None:
        nonlocal builder_called
        builder_called = True
        raise AssertionError("builder must not start when the guard fails")

    monkeypatch.setattr(runner, "check_daily_price_source_revision", fail_guard)
    monkeypatch.setattr(runner.subprocess, "Popen", fail_builder)

    exit_code = runner.main(
        ["--data-root", str(data_root), "--output-root", str(output_root), "--database", str(database)]
    )

    payload = json.loads(
        (
            output_root
            / "scheduled"
            / "ml_raw_pit_refresh"
            / "latest_status.json"
        ).read_text(encoding="utf-8")
    )
    assert exit_code == 1
    assert builder_called is False
    assert payload["status"] == "failed"
    assert payload["error_type"] == "RuntimeError"
    assert payload["error"] == "revision guard internal failure"


def test_core_freshness_proof_blocks_lagging_technical_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status_path = _write_freshness_status(
        tmp_path / "output",
        technical_date="2026-08-11",
    )
    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )

    with pytest.raises(runner._UpstreamNotReady, match="technical_indicators_lagging"):
        runner._core_freshness_proof(status_path)


def test_latest_raw_publication_is_pointer_and_safety_bound(tmp_path: Path) -> None:
    raw_root = tmp_path / "ml_pit_year_shards"
    publication_path = _write_raw_publication(raw_root)

    publication = runner._latest_raw_publication(raw_root)

    assert publication is not None
    assert publication.publication_id == "pit-test"
    assert publication.publication_manifest_path == publication_path.resolve()
    assert publication.dataset_manifest_hash.startswith("sha256:")


def test_refresh_needed_when_same_cutoff_was_published_before_update(
    tmp_path: Path,
) -> None:
    raw_root = tmp_path / "ml_pit_year_shards"
    publication_path = _write_raw_publication(raw_root)
    os.utime(
        publication_path,
        (
            datetime(2026, 8, 12, 6, 0, tzinfo=timezone.utc).timestamp(),
            datetime(2026, 8, 12, 6, 0, tzinfo=timezone.utc).timestamp(),
        ),
    )
    current = runner._latest_raw_publication(raw_root)
    assert current is not None
    proof = runner._CoreFreshnessProof(
        latest_core_date=datetime(2026, 8, 12, tzinfo=_TAIPEI).date(),
        decision_at="2026-08-12T08:30:00+08:00",
        completed_at=datetime(2026, 8, 12, 15, 0, tzinfo=_TAIPEI),
        data_update_status="passed",
    )

    assert runner._refresh_needed(current, proof) is True

    newer_mtime = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc).timestamp()
    os.utime(publication_path, (newer_mtime, newer_mtime))
    current = runner._latest_raw_publication(raw_root)
    assert current is not None
    assert runner._refresh_needed(current, proof) is False


def test_main_skips_when_current_publication_is_new_enough(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    status_path = _write_freshness_status(output_root)
    raw_root = output_root / "release_v4" / "ml_pit_year_shards"
    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"sqlite-placeholder")
    publication_path = _write_raw_publication(raw_root)
    mtime = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc).timestamp()
    os.utime(publication_path, (mtime, mtime))
    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )
    builder_called = False

    def fail_builder(*_args: object, **_kwargs: object) -> None:
        nonlocal builder_called
        builder_called = True
        raise AssertionError("builder must not run for current publication")

    monkeypatch.setattr(runner.subprocess, "run", fail_builder)

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--status-path",
            str(output_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"),
        ]
    )

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    refresh_payload = json.loads(
        (
            output_root
            / "scheduled"
            / "ml_raw_pit_refresh"
            / "latest_status.json"
        ).read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert builder_called is False
    assert payload["status"] == "passed"
    assert refresh_payload["status"] == "skipped_current"


def test_main_revision_guard_precedes_current_publication_skip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    _write_freshness_status(output_root)
    raw_root = output_root / "release_v4" / "ml_pit_year_shards"
    publication_path = _write_raw_publication(raw_root)
    current_mtime = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc).timestamp()
    os.utime(publication_path, (current_mtime, current_mtime))
    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"sqlite-placeholder")
    run_dir = _write_formal_market_revision_run(
        database,
        run_id="current-publication-applied-revision",
        source_start_date="2014-01-02",
        source_end_date="2026-09-23",
    )
    pointer_path = raw_root / "latest_manifest.json"
    database_hash_before = hashlib.sha256(database.read_bytes()).hexdigest()
    pointer_hash_before = hashlib.sha256(pointer_path.read_bytes()).hexdigest()
    marker_hash_before = hashlib.sha256(
        (run_dir / "revision.json").read_bytes()
    ).hexdigest()
    builder_called = False

    def fail_builder(*_args: object, **_kwargs: object) -> None:
        nonlocal builder_called
        builder_called = True
        raise AssertionError("builder must not start for an applied source revision")

    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )
    monkeypatch.setattr(runner.subprocess, "Popen", fail_builder)

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--database",
            str(database),
        ]
    )

    status_path = (
        output_root
        / "scheduled"
        / "ml_raw_pit_refresh"
        / "latest_status.json"
    )
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert builder_called is False
    assert payload["status"] == "blocked_source_revision"
    assert payload["source_revision_gate"]["source_date"] == "2014-01-02"
    assert payload.get("reason") != "raw_pit_publication_current"
    assert hashlib.sha256(database.read_bytes()).hexdigest() == database_hash_before
    assert hashlib.sha256(pointer_path.read_bytes()).hexdigest() == pointer_hash_before
    assert hashlib.sha256(
        (run_dir / "revision.json").read_bytes()
    ).hexdigest() == marker_hash_before


def test_opt_in_prospective_capture_precedes_current_revision_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    _write_freshness_status(output_root)
    raw_root = output_root / "release_v4" / "ml_pit_year_shards"
    publication_path = _write_raw_publication(raw_root)
    os.utime(
        publication_path,
        (datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc).timestamp(),) * 2,
    )
    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"sqlite-placeholder")
    run_dir = _write_formal_market_revision_run(
        database,
        run_id="capture-before-current-block",
        source_start_date="2014-01-02",
        source_end_date="2026-09-23",
    )
    pointer_path = raw_root / "latest_manifest.json"
    database_hash_before = hashlib.sha256(database.read_bytes()).hexdigest()
    pointer_hash_before = hashlib.sha256(pointer_path.read_bytes()).hexdigest()
    marker_hash_before = hashlib.sha256((run_dir / "revision.json").read_bytes()).hexdigest()
    events: list[str] = []
    builder_called = False
    original_blocker = runner._source_revision_blocker

    def capture(**kwargs: object) -> dict[str, object]:
        events.append("capture")
        assert kwargs["source_output_root"] == output_root.resolve()
        assert kwargs["source_date"] == "2026-08-12"
        assert kwargs["candidate_root"] == runner.REPO_ROOT / "output" / "ml_prospective_daily_price_candidates"
        return {
            "status": "captured",
            "candidate_id": "candidate-123",
            "candidate_path": "repo-candidate/manifest.json",
            "candidate_available_at": "2026-08-12T07:30:00+00:00",
            "candidate_capture_receipt_sha256": "sha256:" + ("a" * 64),
            "historical_pit_eligible": False,
            "formal_credit": False,
        }

    def blocker(*args: object, **kwargs: object) -> dict[str, object] | None:
        events.append("revision_guard")
        return original_blocker(*args, **kwargs)

    def fail_builder(*_args: object, **_kwargs: object) -> None:
        nonlocal builder_called
        builder_called = True
        raise AssertionError("raw builder must remain blocked")

    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )
    monkeypatch.setattr(runner, "capture_prospective_daily_price_candidate", capture)
    monkeypatch.setattr(runner, "_source_revision_blocker", blocker)
    monkeypatch.setattr(runner.subprocess, "Popen", fail_builder)

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--database",
            str(database),
            "--capture-prospective-daily-price-candidate",
        ]
    )

    status_path = output_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    log_text = (status_path.parent / "refresh.log").read_text(encoding="utf-8")
    assert exit_code == 0
    assert events == ["capture", "revision_guard"]
    assert builder_called is False
    assert payload["status"] == "blocked_source_revision"
    assert payload["prospective_daily_price_capture"]["status"] == "captured"
    assert payload["prospective_daily_price_capture"]["formal_credit"] is False
    assert payload["source_revision_gate"]["blocker_kind"] == "temporal_source_revision"
    assert "prospective_daily_price_capture" in log_text
    assert "candidate-123" in log_text
    assert hashlib.sha256(database.read_bytes()).hexdigest() == database_hash_before
    assert hashlib.sha256(pointer_path.read_bytes()).hexdigest() == pointer_hash_before
    assert hashlib.sha256((run_dir / "revision.json").read_bytes()).hexdigest() == marker_hash_before


def test_opt_in_prospective_capture_precedes_current_skip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    _write_freshness_status(output_root)
    raw_root = output_root / "release_v4" / "ml_pit_year_shards"
    publication_path = _write_raw_publication(raw_root)
    os.utime(
        publication_path,
        (datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc).timestamp(),) * 2,
    )
    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"sqlite-placeholder")
    events: list[str] = []

    def capture(**kwargs: object) -> dict[str, object]:
        events.append("capture")
        assert kwargs["source_date"] == "2026-08-12"
        return {
            "status": "captured",
            "candidate_id": "current-skip-candidate",
            "formal_credit": False,
        }

    original_blocker = runner._source_revision_blocker

    def blocker(*args: object, **kwargs: object) -> dict[str, object] | None:
        events.append("revision_guard")
        return original_blocker(*args, **kwargs)

    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )
    monkeypatch.setattr(runner, "capture_prospective_daily_price_candidate", capture)
    monkeypatch.setattr(runner, "_source_revision_blocker", blocker)

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--database",
            str(database),
            "--capture-prospective-daily-price-candidate",
        ]
    )

    payload = json.loads(
        (output_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json").read_text(
            encoding="utf-8"
        )
    )
    assert exit_code == 0
    assert events == ["capture", "revision_guard"]
    assert payload["status"] == "skipped_current"
    assert payload["prospective_daily_price_capture"]["candidate_id"] == (
        "current-skip-candidate"
    )


def test_opt_in_capture_failure_is_logged_without_skipping_revision_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    _write_freshness_status(output_root)
    raw_root = output_root / "release_v4" / "ml_pit_year_shards"
    publication_path = _write_raw_publication(raw_root)
    os.utime(
        publication_path,
        (datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc).timestamp(),) * 2,
    )
    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"sqlite-placeholder")
    _write_formal_market_revision_run(
        database,
        run_id="capture-failure-still-blocks",
        source_start_date="2014-01-02",
        source_end_date="2026-09-23",
    )
    events: list[str] = []

    def fail_capture(**_kwargs: object) -> dict[str, object]:
        events.append("capture")
        raise RuntimeError("isolated candidate source rejected")

    original_blocker = runner._source_revision_blocker

    def blocker(*args: object, **kwargs: object) -> dict[str, object] | None:
        events.append("revision_guard")
        return original_blocker(*args, **kwargs)

    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )
    monkeypatch.setattr(runner, "capture_prospective_daily_price_candidate", fail_capture)
    monkeypatch.setattr(runner, "_source_revision_blocker", blocker)

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--database",
            str(database),
            "--capture-prospective-daily-price-candidate",
        ]
    )

    payload = json.loads(
        (output_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json").read_text(
            encoding="utf-8"
        )
    )
    assert exit_code == 0
    assert events == ["capture", "revision_guard"]
    assert payload["status"] == "blocked_source_revision"
    assert payload["prospective_daily_price_capture"]["status"] == "rejected"
    assert payload["prospective_daily_price_capture"]["error"] == (
        "isolated candidate source rejected"
    )
    assert payload["source_revision_gate"]["blocker_kind"] == "temporal_source_revision"


def test_disabled_prospective_capture_preserves_legacy_status_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    status_path = _write_freshness_status(output_root)
    raw_root = output_root / "release_v4" / "ml_pit_year_shards"
    publication_path = _write_raw_publication(raw_root)
    os.utime(
        publication_path,
        (datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc).timestamp(),) * 2,
    )
    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"sqlite-placeholder")
    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )
    monkeypatch.setattr(
        runner,
        "capture_prospective_daily_price_candidate",
        lambda **_kwargs: pytest.fail("opt-out runner must not invoke candidate capture"),
    )

    exit_code = runner.main(
        ["--data-root", str(data_root), "--output-root", str(output_root)]
    )

    payload = json.loads(
        (output_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json").read_text(
            encoding="utf-8"
        )
    )
    assert exit_code == 0
    assert payload["status"] == "skipped_current"
    assert "prospective_daily_price_capture" not in payload
    assert json.loads(status_path.read_text(encoding="utf-8"))["status"] == "passed"


def test_main_runs_builder_and_validates_new_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    status_path = _write_freshness_status(output_root)
    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"sqlite-placeholder")
    raw_root = output_root / "release_v4" / "ml_pit_year_shards"
    publication_path = _write_raw_publication(raw_root)
    published = runner._latest_raw_publication(raw_root)
    assert published is not None
    publication_path.unlink()
    current_results = iter((None, published))
    monkeypatch.setattr(runner, "_latest_raw_publication", lambda _root: next(current_results))
    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )
    monkeypatch.setattr(
        runner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(
            total=SCHEDULED_REQUIRED_FREE_BYTES + 10_000,
            used=10_000,
            free=SCHEDULED_REQUIRED_FREE_BYTES + 1_000,
        ),
    )
    observed: dict[str, object] = {}

    class _FakeBuilderProcess:
        pid = 999_991
        returncode = 0

        def communicate(self) -> tuple[str, str]:
            return "builder ok", ""

    def fake_popen(command: list[str], **kwargs: object) -> _FakeBuilderProcess:
        observed["command"] = command
        observed["kwargs"] = kwargs
        report_path = Path(
            command[command.index("--source-quality-report") + 1]
        )
        _write_source_quality_report(report_path)
        return _FakeBuilderProcess()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--database",
            str(database),
            "--batch-size",
            "1024",
        ]
    )

    refresh_path = output_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"
    refresh_payload = json.loads(refresh_path.read_text(encoding="utf-8"))
    command = observed["command"]
    assert isinstance(command, list)
    assert exit_code == 0
    assert refresh_payload["status"] == "completed"
    assert "--all-universe" in command
    assert "--source-quality-report" in command
    assert "--source-quality-candidate-evidence" in command
    assert refresh_payload["source_quality_evidence"]["readback_status"] == "verified"
    assert refresh_payload["source_quality_evidence"]["candidate_rows_complete"] is True
    assert refresh_payload["source_quality_evidence"]["candidate_count"] == 0
    assert command[command.index("--decision-at") + 1] == "2026-08-12T08:30:00+08:00"
    assert command[command.index("--database") + 1] == str(database.resolve())
    source_flags = [
        command[index + 1]
        for index, value in enumerate(command)
        if value == "--daily-price-source-dir"
    ]
    assert source_flags == [
        str((data_root / "daily_price").resolve()),
        str((data_root / "daily_price_tpex").resolve()),
    ]
    assert refresh_payload["daily_price_source_dirs"] == source_flags
    assert json.loads(status_path.read_text(encoding="utf-8"))["status"] == "passed"


def test_main_fails_closed_when_builder_does_not_write_source_quality_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    _write_freshness_status(output_root)
    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"sqlite-placeholder")
    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )
    monkeypatch.setattr(
        runner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(
            total=700 * 1024**3,
            used=100 * 1024**3,
            free=600 * 1024**3,
        ),
    )
    monkeypatch.setattr(runner, "_latest_raw_publication", lambda _root: None)
    monkeypatch.setattr(runner, "_direct_chain_instance_lock_present", lambda _root: False)

    class _FakeLock:
        owner_pid = 424_242

        def authorize_child(self, _child_pid: int) -> None:
            return None

    fake_lock = _FakeLock()
    monkeypatch.setattr(runner, "_acquire_lock", lambda _path: fake_lock)
    monkeypatch.setattr(runner, "_release_lock", lambda _lock: None)
    monkeypatch.setattr(
        runner,
        "build_heavy_chain_reservation_handoff_environment",
        lambda _lock, *, environment, parent_pid: environment,
    )

    class _FakeBuilderProcess:
        pid = 424_243
        returncode = 0

        def communicate(self) -> tuple[str, str]:
            return "builder ok", ""

    monkeypatch.setattr(
        runner.subprocess,
        "Popen",
        lambda _command, **_kwargs: _FakeBuilderProcess(),
    )

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--database",
            str(database),
        ]
    )

    receipt = json.loads(
        (
            output_root
            / "scheduled"
            / "ml_raw_pit_refresh"
            / "latest_status.json"
        ).read_text(encoding="utf-8")
    )
    assert exit_code == 1
    assert receipt["status"] == "failed"
    assert receipt["builder_returncode"] == 0
    assert receipt["error"] == "source_quality_evidence_readback_failed"
    assert receipt["source_quality_evidence"]["readback_status"] == "missing"
    assert receipt["source_quality_evidence"]["candidate_evidence_complete"] is False
    assert receipt["source_quality_evidence"]["candidate_rows_complete"] is False


def test_main_records_upstream_block_without_running_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    _write_freshness_status(output_root, status="running")
    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
        ]
    )

    payload = json.loads(
        (
            output_root
            / "scheduled"
            / "ml_raw_pit_refresh"
            / "latest_status.json"
        ).read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert payload["status"] == "blocked_upstream_not_ready"


def test_main_blocks_before_builder_when_storage_is_below_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    _write_freshness_status(output_root)
    monkeypatch.setattr(
        runner,
        "_taipei_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=_TAIPEI),
    )
    monkeypatch.setattr(
        runner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100, used=95, free=5),
    )
    builder_called = False

    def fail_builder(*_args: object, **_kwargs: object) -> None:
        nonlocal builder_called
        builder_called = True
        raise AssertionError("builder must not run without filesystem headroom")

    monkeypatch.setattr(runner.subprocess, "run", fail_builder)

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
                "--minimum-free-space-bytes",
                str(SCHEDULED_SAFETY_RESERVE_BYTES),
        ]
    )

    refresh_payload = json.loads(
        (
            output_root
            / "scheduled"
            / "ml_raw_pit_refresh"
            / "latest_status.json"
        ).read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert builder_called is False
    assert refresh_payload["status"] == "blocked_insufficient_storage"
    assert refresh_payload["storage_preflight"]["free_bytes"] == 5
    assert refresh_payload["storage_preflight"]["minimum_free_space_bytes"] == (
        SCHEDULED_SAFETY_RESERVE_BYTES
    )


def test_main_records_locked_without_starting_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    status_path = output_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps({"status": "running", "process_id": 999}), encoding="utf-8")
    _write_freshness_status(output_root)
    monkeypatch.setattr(runner, "_acquire_lock", lambda _path: None)
    monkeypatch.setattr(
        runner,
        "_storage_preflight",
        lambda _path, minimum_free_space_bytes: {
            "total_bytes": 400 * 1024**3,
            "used_bytes": 0,
            "free_bytes": 300 * 1024**3,
            "minimum_free_space_bytes": minimum_free_space_bytes,
            "within_minimum_free_space": True,
        },
    )

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--status-path",
            str(status_path),
        ]
    )

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "skipped_locked"
    assert payload["reason"] == "another_raw_pit_refresh_is_running"


def test_raw_direct_custody_guard_blocks_live_owner_and_allows_stale_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "release_v4"
    states = iter([("verified", 2468), ("stale", 2468)])
    monkeypatch.setattr(
        runner.direct_chain_runner,
        "_maintenance_lock_state",
        lambda _training: next(states),
    )
    monkeypatch.setattr(
        runner.direct_chain_runner.maintenance,
        "_target_processes",
        lambda _root: [],
    )

    assert runner._direct_chain_instance_lock_present(release_root) is True
    assert runner._direct_chain_instance_lock_present(release_root) is False


def test_raw_direct_custody_guard_blocks_live_continuation_after_owner_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "release_v4"
    monkeypatch.setattr(
        runner.direct_chain_runner.maintenance,
        "_target_processes",
        lambda _root: [(8642, "continue_ml_direct_v3_refresh_chain.py")],
    )
    monkeypatch.setattr(
        runner.direct_chain_runner,
        "_maintenance_lock_state",
        lambda _training: (_ for _ in ()).throw(
            AssertionError("live continuation should be sufficient custody")
        ),
    )

    assert runner._direct_chain_instance_lock_present(release_root) is True
