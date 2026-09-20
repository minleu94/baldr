from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from ml_module import natural_shadow_pruning_evidence as natural_evidence
from scripts import run_daily_ml_allocation_orchestration as orchestration
from scripts import natural_shadow_pruning_evidence_runner as runner
from scripts.natural_shadow_pruning_evidence_runner import (
    run_natural_shadow_pruning_evidence,
)


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _write_pending_sidecar(
    path: Path,
    *,
    credit_allowed: bool = False,
    include_partial_outcome: bool = False,
) -> None:
    observation_body: dict[str, object] = {
        "schema_version": "ml-allocation-shadow-observation.v1",
        "decision_date": "2026-09-08",
        "custody_hash": _hash({"custody": "runner-test"}),
        "revision": 1,
        "emitted_at": "2026-09-08T09:00:00+08:00",
        "promotion_day_credit_allowed": credit_allowed,
        "replayed": False,
        "backfilled": False,
        "synthetic_outcomes_used": False,
        "custody": {
            "model_hash": "sha256:" + "1" * 64,
            "dataset_identity_hash": "sha256:" + "2" * 64,
            "policy_hash": "sha256:" + "3" * 64,
        },
        "lanes": [
            {
                "slice_id": "alpha:0",
                "alpha_bp": 0,
                "lane_metrics": None,
            }
        ],
    }
    observation = {
        **observation_body,
        "record_hash": _hash(observation_body),
    }
    outcome = None
    if include_partial_outcome:
        outcome_body: dict[str, object] = {
            "schema_version": "ml-allocation-shadow-outcome.v1",
            "observation_hash": observation["record_hash"],
            "custody_hash": _hash(
                {"observation_hash": observation["record_hash"], "revision": 1}
            ),
            "revision": 1,
            "status": "partial_horizon_maturity",
            "completed_horizons_trading_sessions": [5, 10, 20],
            "latest_used_date": "2026-09-13",
            "downside_outcomes": [
                {
                    "symbol": "2330",
                    "horizon_trading_sessions": horizon,
                    "available_at": "2026-09-13T17:00:00+08:00",
                    "actual_downside": 0,
                }
                for horizon in (5, 10, 20)
            ],
        }
        outcome = {
            **outcome_body,
            "record_hash": _hash(outcome_body),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE shadow_observations (
                record_hash TEXT PRIMARY KEY,
                decision_date TEXT NOT NULL,
                custody_hash TEXT NOT NULL,
                revision INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE (decision_date, custody_hash),
                UNIQUE (decision_date, revision)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE shadow_outcomes (
                record_hash TEXT PRIMARY KEY,
                observation_hash TEXT NOT NULL,
                custody_hash TEXT NOT NULL,
                revision INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE (observation_hash, custody_hash),
                UNIQUE (observation_hash, revision)
            )
            """
        )
        connection.execute(
            "INSERT INTO shadow_observations VALUES (?, ?, ?, ?, ?)",
            (
                observation["record_hash"],
                observation["decision_date"],
                observation["custody_hash"],
                observation["revision"],
                _canonical(observation),
            ),
        )
        if outcome is not None:
            connection.execute(
                "INSERT INTO shadow_outcomes VALUES (?, ?, ?, ?, ?)",
                (
                    outcome["record_hash"],
                    outcome["observation_hash"],
                    outcome["custody_hash"],
                    outcome["revision"],
                    _canonical(outcome),
                ),
            )


def test_missing_sidecar_is_pending_but_not_normal_wait_and_status_is_immutable(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "missing" / "shadow_evidence.sqlite"
    result = run_natural_shadow_pruning_evidence(
        sidecar_database_path=sidecar,
        output_root=tmp_path / "run",
        as_of_date=date(2026, 9, 8),
    )

    assert result["status"] == "pending"
    assert result["integrity_state"] == "awaiting_source"
    assert result["pending_is_normal_wait"] is False
    assert result["pending_reason"] == "source_missing"
    assert result["exit_code"] == 0
    assert result["evidence_path"] is None
    assert result["pruning_action_performed"] is False
    assert result["promotion_action_performed"] is False
    daily_status = Path(str(result["daily_status_path"]))
    weekly_status = Path(str(result["weekly_status_path"]))
    assert daily_status.is_file()
    assert weekly_status.is_file()
    assert json.loads(daily_status.read_text(encoding="utf-8"))["status_hash"] == (
        result["status_hash"]
    )

    replay = run_natural_shadow_pruning_evidence(
        sidecar_database_path=sidecar,
        output_root=tmp_path / "run",
        as_of_date=date(2026, 9, 8),
    )
    assert replay["status_hash"] == result["status_hash"]
    assert replay["daily_status_write"] == "idempotent"
    assert replay["weekly_status_write"] == "idempotent"


def test_real_sidecar_projection_writes_hash_bound_daily_and_weekly_evidence(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "collector" / "shadow_evidence.sqlite"
    _write_pending_sidecar(sidecar)
    result = run_natural_shadow_pruning_evidence(
        sidecar_database_path=sidecar,
        output_root=tmp_path / "run",
        as_of_date="2026-09-08",
    )

    assert result["status"] == "pending"
    assert result["evidence_status"] == "pending_maturity"
    assert result["integrity_state"] == "verified"
    assert result["exit_code"] == 0
    evidence_path = Path(str(result["evidence_path"]))
    weekly_path = Path(str(result["weekly_evidence_path"]))
    assert evidence_path.is_file()
    assert weekly_path.is_file()
    assert evidence_path.read_bytes() == weekly_path.read_bytes()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["evidence_hash"] == result["evidence_hash"]
    assert result["daily_evidence_write"] == "inserted"
    assert result["weekly_evidence_write"] == "inserted"
    assert result["pruning_boundary"]["apply_action"] is False
    assert result["pruning_boundary"]["promotion_eligible"] is False
    assert result["pending_is_normal_wait"] is False
    assert result["pending_reason"] == "contract_blocked"
    classification = evidence["observation_classification"]
    assert classification["contract_blocked_observation_count"] == 1
    assert classification["unknown_blocked_observation_count"] == 0

    replay = run_natural_shadow_pruning_evidence(
        sidecar_database_path=sidecar,
        output_root=tmp_path / "run",
        as_of_date="2026-09-08",
    )
    assert replay["evidence_hash"] == result["evidence_hash"]
    assert replay["daily_evidence_write"] == "idempotent"
    assert replay["weekly_evidence_write"] == "idempotent"


def test_known_partial_h60_is_normal_time_wait_only(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "collector" / "shadow_evidence.sqlite"
    _write_pending_sidecar(
        sidecar,
        credit_allowed=True,
        include_partial_outcome=True,
    )

    result = run_natural_shadow_pruning_evidence(
        sidecar_database_path=sidecar,
        output_root=tmp_path / "run",
        as_of_date="2026-09-18",
    )

    assert result["status"] == "pending"
    assert result["pending_is_normal_wait"] is True
    assert result["pending_reason"] == "time_wait_only"
    assert result["exit_code"] == 0
    evidence = json.loads(
        Path(str(result["evidence_path"])).read_text(encoding="utf-8")
    )
    classification = evidence["observation_classification"]
    assert classification["matured_observation_count"] == 0
    assert classification["pending_observation_count"] == 1
    assert classification["time_wait_only_observation_count"] == 1
    assert classification["contract_blocked_observation_count"] == 0
    assert classification["unknown_blocked_observation_count"] == 0
    pending = evidence["pending_observations"][0]
    assert pending["promotion_day_credit_allowed"] is True
    assert pending["availability_state"] == "available"
    assert pending["pending_class"] == "time_wait_only"
    assert pending["reasons"] == [
        "completed_horizons_incomplete",
        "outcome_horizon_missing:h60",
        "outcome_not_matured_all_horizons",
    ]


def test_invalid_sidecar_is_degraded_and_does_not_become_pending(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "collector" / "shadow_evidence.sqlite"
    _write_pending_sidecar(sidecar)
    with sqlite3.connect(sidecar) as connection:
        connection.execute(
            "UPDATE shadow_observations SET payload_json = ?",
            ("{}",),
        )

    result = run_natural_shadow_pruning_evidence(
        sidecar_database_path=sidecar,
        output_root=tmp_path / "run",
        as_of_date="2026-09-08",
    )

    assert result["status"] == "blocked_integrity"
    assert result["integrity_state"] == "failed"
    assert result["pending_is_normal_wait"] is False
    assert result["exit_code"] == 2
    assert result["evidence_path"] is None
    assert result["pruning_action_performed"] is False
    assert result["promotion_action_performed"] is False


def test_related_forward_sidecar_is_diagnostic_only_and_hash_bound(
    tmp_path: Path,
) -> None:
    primary = tmp_path / "primary" / "shadow_evidence.sqlite"
    companion = tmp_path / "forward" / "shadow_evidence.sqlite"
    _write_pending_sidecar(primary)
    _write_pending_sidecar(companion)

    result = run_natural_shadow_pruning_evidence(
        sidecar_database_path=primary,
        output_root=tmp_path / "run",
        as_of_date="2026-09-08",
        related_sidecar_database_paths={"natural_forward_candidate": companion},
    )

    assert result["status"] == "pending"
    assert result["pending_reason"] == "contract_blocked"
    lanes = result["related_lanes"]
    assert isinstance(lanes, list)
    assert len(lanes) == 1
    lane = lanes[0]
    assert lane["diagnostic_only"] is True
    assert lane["promotion_authority"] is False
    assert lane["eligibility_contribution"] == "none"
    source = lane["source"]
    assert source["sidecar_file_hash"].startswith("sha256:")
    assert source["sidecar_size_bytes"] > 0
    assert source["read_cutoff_date"] == "2026-09-08"
    evidence = json.loads(
        Path(str(result["evidence_path"])).read_text(encoding="utf-8")
    )
    assert evidence["related_lanes"][0]["diagnostic_only"] is True
    assert evidence["observation_classification"][
        "natural_credit_eligible_observation_count"
    ] == 0


def test_corrupt_related_forward_sidecar_does_not_block_primary_projection(
    tmp_path: Path,
) -> None:
    primary = tmp_path / "primary" / "shadow_evidence.sqlite"
    companion = tmp_path / "forward" / "shadow_evidence.sqlite"
    _write_pending_sidecar(primary)
    _write_pending_sidecar(companion)
    with sqlite3.connect(companion) as connection:
        connection.execute(
            "UPDATE shadow_observations SET payload_json = ?",
            ("{}",),
        )

    result = run_natural_shadow_pruning_evidence(
        sidecar_database_path=primary,
        output_root=tmp_path / "run",
        as_of_date="2026-09-08",
        related_sidecar_database_paths={"natural_forward_candidate": companion},
    )

    assert result["status"] == "pending"
    lane = result["related_lanes"][0]
    assert lane["status"] == "blocked_integrity"
    assert lane["diagnostic_only"] is True
    assert result["exit_code"] == 0


def test_pending_wait_requires_known_time_only_cohort() -> None:
    assert runner._pending_wait_state(
        {
            "pending_observation_count": 2,
            "observation_classification": {
                "time_wait_only_observation_count": 1,
                "contract_blocked_observation_count": 0,
                "unknown_blocked_observation_count": 1,
            },
        }
    ) == (False, "blocked_unknown")
    assert runner._pending_wait_state(
        {
            "pending_observation_count": 0,
            "observation_classification": {
                "time_wait_only_observation_count": 0,
                "contract_blocked_observation_count": 0,
                "unknown_blocked_observation_count": 0,
            },
        }
    ) == (False, "not_time_wait_only")


def test_status_publication_stages_complete_bytes_before_atomic_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "status.json"

    def fail_fsync(_file_descriptor: int) -> None:
        raise OSError("simulated crash during fsync")

    monkeypatch.setattr(runner.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="simulated crash"):
        runner._create_only_bytes(target, b"complete-status")

    assert not target.exists()
    assert not list(tmp_path.glob(".*.tmp"))

    monkeypatch.undo()
    assert runner._create_only_bytes(target, b"complete-status") == "inserted"
    assert runner._create_only_bytes(target, b"complete-status") == "idempotent"
    with pytest.raises(runner.NaturalShadowPruningScheduleError, match="conflict"):
        runner._create_only_bytes(target, b"different-status")


def test_evidence_writer_crash_does_not_leave_partial_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sidecar = tmp_path / "collector" / "shadow_evidence.sqlite"
    _write_pending_sidecar(sidecar)
    evidence = natural_evidence.build_natural_shadow_pruning_evidence(
        sidecar,
        as_of_date="2026-09-08",
    )
    target = tmp_path / "evidence" / "projection.json"
    target.parent.mkdir()

    def fail_fsync(_file_descriptor: int) -> None:
        raise OSError("simulated evidence crash during fsync")

    monkeypatch.setattr(natural_evidence.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="simulated evidence crash"):
        natural_evidence.write_natural_shadow_pruning_evidence(target, evidence)

    assert not target.exists()
    assert not list(target.parent.glob(".*.tmp"))

    monkeypatch.undo()
    assert natural_evidence.write_natural_shadow_pruning_evidence(
        target,
        evidence,
    ) == "inserted"
    assert natural_evidence.write_natural_shadow_pruning_evidence(
        target,
        evidence,
    ) == "idempotent"


def test_orchestration_common_status_exit_binds_pruning_result_and_exit_code(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "scheduled" / "ml_allocation_copilot"
    status = {
        "schema_version": "fixture",
        "status": "passed_rule_only",
        "decision_at": "2026-09-08T08:30:00+08:00",
        "failed_reasons": [],
        "formal_oos_allowed": False,
        "production_action_allowed": False,
        "writes_source_database": False,
    }
    result = orchestration._write_status(run_root, status)

    pruning = result["natural_shadow_pruning_evidence"]
    assert isinstance(pruning, dict)
    assert pruning["status"] == "pending"
    assert pruning["exit_code"] == 0
    assert result["natural_shadow_pruning_evidence_exit_code"] == 0
    assert result["status"] == "passed_rule_only"
    assert json.loads(
        (run_root / "latest_status.json").read_text(encoding="utf-8")
    )["natural_shadow_pruning_evidence_exit_code"] == 0


def test_orchestration_status_selects_configured_forward_sidecar_as_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forward_root = tmp_path / "forward"
    _write_pending_sidecar(
        forward_root
        / "scheduled"
        / "ml_allocation_copilot"
        / "shadow_evidence_collector"
        / "shadow_evidence.sqlite"
    )
    monkeypatch.setenv("ML_FORWARD_OUTPUT_ROOT", str(forward_root))
    run_root = tmp_path / "scheduled" / "ml_allocation_copilot"
    result = orchestration._write_status(
        run_root,
        {
            "schema_version": "fixture",
            "status": "passed_rule_only",
            "decision_at": "2026-09-08T08:30:00+08:00",
            "failed_reasons": [],
            "formal_oos_allowed": False,
            "production_action_allowed": False,
            "writes_source_database": False,
        },
    )

    pruning = result["natural_shadow_pruning_evidence"]
    lane = pruning["related_lanes"][0]
    assert lane["lane"] == "natural_forward_candidate"
    assert lane["diagnostic_only"] is True
    assert lane["eligibility_contribution"] == "none"
