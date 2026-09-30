from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import uuid
from zoneinfo import ZoneInfo

import pytest

from app_module.portfolio_condition_monitor import (
    PortfolioConditionResult,
    PortfolioCurrentSnapshot,
)
from app_module.position_health_service import PositionHealthState
from app_module.position_health_state_machine import PositionHealthMetric
from app_module.position_health_transition_evaluator import (
    DailyPositionHealthTransitionEvaluator,
    DailyPositionHealthTransitionRequest,
    PITConditionObservation,
    _captured_daily_source_suffix_matches,
    _is_captured_daily_source_path,
    _read_hashed_legacy_file,
    _reread_legacy_artifacts,
    _same_snapshot_history_rollover,
    _verify_legacy_same_snapshot_reuse,
    evaluate_baseline_file,
)
from app_module.recommendation.persistence import ExecutionArtifactIntegrityError
from app_module.position_health_transition_repository import (
    PositionHealthTransitionRecord,
    PositionHealthTransitionRepository,
)
from app_module.position_thesis_contract import (
    PositionInvalidationRule,
    PositionThesisContract,
)
from app_module.strategy_lifecycle_service import GateStatus


TAIPEI = ZoneInfo("Asia/Taipei")


@pytest.fixture
def workspace_qa_tmp(request: pytest.FixtureRequest) -> Path:
    workspace = Path(__file__).resolve().parents[1]
    qa_root = workspace / ".tmp_scheduler_all_repair_20260930" / "qa_evidence"
    qa_root.mkdir(parents=True, exist_ok=True)
    target = qa_root / f"pytest_health_{uuid.uuid4().hex}"
    target.mkdir()
    if target.resolve().parent != qa_root.resolve():
        raise AssertionError("temporary Health test directory escaped QA root")
    request.addfinalizer(lambda: shutil.rmtree(target))
    return target


def _observed() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _request_date(observed: datetime) -> str:
    return observed.astimezone(TAIPEI).date().isoformat()


def _position(*, state: str = "WATCH", position_id: str = "position-2330") -> dict[str, object]:
    return {
        "position_id": position_id,
        "stock_code": "2330",
        "paper_shares": 1_000,
        "state": state,
        "entry_lineage_status": "same_snapshot_verified",
        "source_trace": ["paper_snapshot:paper-main-20260908"],
    }


def _provenance() -> dict[str, str]:
    return {
        "snapshot_id": "paper-main-20260908",
        "snapshot_rows_sha256": "sha256:rows",
        "baseline_sha256": "sha256:baseline",
    }


def _thesis(decision_date: str, *, action: str = "exit") -> PositionThesisContract:
    return PositionThesisContract(
        position_id="position-2330",
        stock_code="2330",
        entry_date=decision_date,
        decision_date=decision_date,
        available_date=decision_date,
        entry_thesis="Human-authored thesis",
        holding_horizon_trading_days=5,
        next_review_date=decision_date,
        source_trace=("manual_thesis:position-2330",),
        invalidation_rules=(
            PositionInvalidationRule(
                metric_id="drawdown_pct",
                operator="gt",
                threshold=Decimal("10"),
                action=action,
            ),
        ),
    )


def _condition(observed: datetime, *, status: str = "valid") -> PITConditionObservation:
    result = PortfolioConditionResult(
        stock_code="2330",
        status=status,
        label="condition",
        source_label="verified-current-condition",
    )
    return PITConditionObservation(
        result=result,
        current_snapshot=PortfolioCurrentSnapshot(
            current_regime="bull",
            current_total_score=Decimal("90"),
            current_price=None,
        ),
        source_id="condition-20260908",
        source_snapshot_hash="sha256:condition",
        as_of_date=observed.astimezone(TAIPEI).date().isoformat(),
        available_at=observed.isoformat(),
        quality="observed",
        source_trace=("condition_observation:20260908",),
    )


def _complete_request(
    *,
    observed: datetime | None = None,
    condition_status: str = "valid",
    metric_value: str = "1",
    action: str = "exit",
    previous_state: str = "HEALTHY",
    repository: PositionHealthTransitionRepository | None = None,
) -> tuple[DailyPositionHealthTransitionEvaluator, DailyPositionHealthTransitionRequest]:
    observed = observed or _observed()
    decision_date = _request_date(observed)
    position = _position(state=previous_state)
    request = DailyPositionHealthTransitionRequest(
        decision_date=decision_date,
        observed_at=observed,
        positions=(position,),
        previous_positions={"position-2330": {"state": previous_state}},
        thesis_by_position={"position-2330": _thesis(decision_date, action=action)},
        conditions_by_position={
            "position-2330": _condition(observed, status=condition_status)
        },
        metrics_by_position={
            "position-2330": (
                PositionHealthMetric(
                    metric_id="drawdown_pct",
                    value=Decimal(metric_value),
                    available_date=decision_date,
                ),
            )
        },
        feedback_status_by_position={"position-2330": GateStatus.PASS},
        trading_dates=(decision_date,),
        provenance=_provenance(),
    )
    return DailyPositionHealthTransitionEvaluator(
        transition_repository=repository
    ), request


def test_complete_inputs_write_proposal_and_are_idempotent(tmp_path: Path) -> None:
    repository = PositionHealthTransitionRepository(tmp_path / "transitions.sqlite")
    evaluator, request = _complete_request(repository=repository)

    first = evaluator.evaluate(request)
    second = evaluator.evaluate(request)

    assert first["status"] == "passed"
    assert first["positions"][0]["proposed_state"] == PositionHealthState.HEALTHY.value
    assert first["positions"][0]["transition_event"]["persistence"] == "written"
    assert second["status"] == "passed"
    assert second["positions"][0]["transition_event"]["persistence"] == "idempotent"
    assert len(repository.list_for_position("position-2330")) == 1


def test_same_semantic_inputs_are_idempotent_across_receipt_recapture(tmp_path: Path) -> None:
    repository = PositionHealthTransitionRepository(tmp_path / "transitions.sqlite")
    first_observed = datetime(2026, 9, 8, 13, 5, tzinfo=timezone.utc)
    evaluator, first_request = _complete_request(
        observed=first_observed,
        repository=repository,
    )
    first_request = replace(
        first_request,
        provenance={
            **dict(first_request.provenance),
            "condition": {
                "source_id": "condition-20260908",
                "source_snapshot_hash": "sha256:condition",
                "available_at": first_observed.isoformat(),
                "path": "first-condition.json",
                "file_sha256": "sha256:first-file",
            },
        },
    )
    first = evaluator.evaluate(first_request)

    second_observed = first_observed + timedelta(minutes=1)
    second_request = replace(
        first_request,
        observed_at=second_observed,
        conditions_by_position={
            "position-2330": _condition(second_observed, status="valid")
        },
        provenance={
            **dict(first_request.provenance),
            "baseline_sha256": "sha256:recaptured-baseline",
            "condition": {
                "source_id": "condition-20260908",
                "source_snapshot_hash": "sha256:condition",
                "available_at": second_observed.isoformat(),
                "path": "recaptured-condition.json",
                "file_sha256": "sha256:recaptured-file",
            },
        },
    )
    second = evaluator.evaluate(second_request)

    assert first["status"] == "passed"
    assert second["status"] == "passed"
    assert second["positions"][0]["transition_event"]["persistence"] == "idempotent"
    assert (
        second["positions"][0]["transition_event"]["event_id"]
        == first["positions"][0]["transition_event"]["event_id"]
    )


def test_machine_policy_thesis_is_traceable_but_remains_proposal_only() -> None:
    evaluator, request = _complete_request()
    machine = replace(
        request.thesis_by_position["position-2330"],
        entry_thesis="machine_policy_candidate:fixture; source-bound observation; no human investment rationale supplied",
        source_type="machine_policy",
        source_actor="forward_position_policy_producer",
    )
    result = evaluator.evaluate(
        replace(request, thesis_by_position={"position-2330": machine})
    )
    row = result["positions"][0]
    assert result["status"] == "passed"
    assert row["thesis_source_type"] == "machine_policy"
    assert row["thesis_source_actor"] == "forward_position_policy_producer"
    assert row["human_approval_required"] is True
    assert row["auto_action_allowed"] is False
    assert row["transition_event"]["decision_kind"] == "proposal"


def test_same_identity_different_input_is_rejected(tmp_path: Path) -> None:
    repository = PositionHealthTransitionRepository(tmp_path / "transitions.sqlite")
    evaluator, request = _complete_request(repository=repository, metric_value="1")
    assert evaluator.evaluate(request)["status"] == "passed"

    changed_evaluator, changed = _complete_request(
        repository=repository,
        metric_value="2",
    )
    result = changed_evaluator.evaluate(changed)

    assert result["status"] == "blocked"
    assert "transition_proposal_persistence_blocked:ValueError" in result["blockers"]
    assert result["positions"][0]["transition_event"]["persistence"] == "blocked"
    assert len(repository.list_for_position("position-2330")) == 1


def _same_snapshot_rollover_fixtures() -> tuple[
    dict[str, object], dict[str, object], dict[str, object], dict[str, object]
]:
    position_id = "paper:paper-main:2330:entry-fixture"
    prior_id = "paper-main-20260922"
    current_id = "paper-main-20260930"
    old_position: dict[str, object] = {
        "position_id": position_id,
        "stock_code": "2330",
        "paper_shares": 1000,
        "state": "WATCH",
        "historical_prior_source_snapshot_id": prior_id,
        "entry_thesis": "human thesis fixture",
    }
    current_position = copy.deepcopy(old_position)
    current_position["historical_prior_source_snapshot_id"] = current_id
    old_source_position = copy.deepcopy(old_position)
    current_source_position = copy.deepcopy(current_position)
    empty_hash = "sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    old_provenance: dict[str, object] = {
        "source_snapshot_id": current_id,
        "source_snapshot_date": "2026-09-30",
        "source_snapshot_rows_sha256": "sha256:snapshot-rows",
        "source_data_version": 1,
        "previous_source_snapshot_id": prior_id,
        "previous_source_snapshot_date": "2026-09-22",
        "positions": [old_source_position],
        "entry_lineage_source": {
            "status": "ready",
            "row_count": 0,
            "event_count": 0,
            "rows_sha256": empty_hash,
            "file_sha256": "sha256:ledger-file",
            "window_start_exclusive": "2026-09-22",
            "window_end_inclusive": "2026-09-30",
        },
        "entry_lineage_verified_codes": ["2330"],
        "warnings": ["position_health_daily_refresh_does_not_evaluate_transition", "paper_position_entry_lineage_not_verified"],
        "position_identity_source": {
            "status": "degraded",
            "state": {"selected_snapshot_rows_sha256": "sha256:snapshot-rows"},
            "ledger": {
                "rows_sha256": empty_hash,
                "file_sha256": "sha256:ledger-file",
            },
        },
        "official_calendar": {"years": {"2026": {"source_hash": "sha256:calendar-source"}}},
    }
    current_provenance = copy.deepcopy(old_provenance)
    current_provenance["previous_source_snapshot_id"] = current_id
    current_provenance["previous_source_snapshot_date"] = "2026-09-30"
    current_provenance["positions"] = [current_source_position]
    current_provenance["entry_lineage_source"] = {"status": "not_needed"}
    current_provenance["entry_lineage_verified_codes"] = []
    current_provenance["warnings"] = [
        item for item in old_provenance["warnings"] if item != "paper_position_entry_lineage_not_verified"
    ]
    old_payload: dict[str, object] = {
        "position": old_position,
        "previous": {"state": "WATCH"},
        "thesis": {"entry_thesis": "human thesis fixture"},
        "condition": {"status": "valid", "source_snapshot_hash": "sha256:condition"},
        "feedback_status": None,
        "metrics": [{"metric_id": "drawdown_bp", "value": "100"}],
        "forward_position_thesis_binding": None,
        "trading_dates": ["2026-09-30"],
        "provenance": old_provenance,
        "decision_date": "2026-09-30",
        "policy_hash": "sha256:policy",
    }
    current_payload = copy.deepcopy(old_payload)
    current_payload["position"] = current_position
    current_payload["provenance"] = current_provenance
    return old_payload, current_payload, old_provenance, current_provenance


def test_same_snapshot_history_rollover_is_narrow_and_decision_equivalent() -> None:
    old, current, old_provenance, current_provenance = _same_snapshot_rollover_fixtures()
    assert _same_snapshot_history_rollover(
        old_input_payload=old,
        current_input_payload=current,
        old_provenance=old_provenance,
        current_provenance=current_provenance,
        position_id="paper:paper-main:2330:entry-fixture",
        decision_date="2026-09-30",
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["position"].update(paper_shares=2000),
        lambda payload: payload["position"].update(position_id="paper:paper-main:other"),
        lambda payload: payload["previous"].update(state="EXIT_CANDIDATE"),
        lambda payload: payload["thesis"].update(entry_thesis="changed human thesis"),
        lambda payload: payload["condition"].update(source_snapshot_hash="sha256:changed-condition"),
        lambda payload: payload["metrics"][0].update(value="200"),
        lambda payload: payload.update(policy_hash="sha256:changed-policy"),
        lambda payload: payload.update(trading_dates=["2026-09-29", "2026-09-30"]),
        lambda payload: payload["provenance"]["position_identity_source"]["ledger"].update(rows_sha256="sha256:changed-ledger"),
    ],
    ids=("quantity", "position-id", "prior-state", "human-thesis", "condition", "metric", "policy", "calendar", "ledger"),
)
def test_same_snapshot_history_rollover_rejects_decision_bearing_changes(mutation) -> None:
    old, current, old_provenance, _current_provenance = _same_snapshot_rollover_fixtures()
    mutation(current)
    assert not _same_snapshot_history_rollover(
        old_input_payload=old,
        current_input_payload=current,
        old_provenance=old_provenance,
        current_provenance=current["provenance"],
        position_id="paper:paper-main:2330:entry-fixture",
        decision_date="2026-09-30",
    )


@pytest.mark.parametrize("corruption", ["missing", "tampered", "future", "schema"])
def test_legacy_reuse_requires_a_valid_bounded_original_result(
    workspace_qa_tmp: Path,
    corruption: str,
) -> None:
    output_dir = workspace_qa_tmp / "formal" / "position_health_transition"
    output_dir.mkdir(parents=True)
    result_path = output_dir / "transition_20260930.json"
    observed = datetime.now(timezone.utc).replace(microsecond=0)
    if corruption != "missing":
        result: dict[str, object] = {
            "schema_version": "position-health-transition-evaluation.v1",
            "status": "degraded",
            "decision_date": "2026-09-30",
            "observed_at": observed.isoformat(),
            "research_only": True,
            "apply_transition": False,
            "auto_action_allowed": False,
            "broker_execution": False,
            "formal_credit": False,
            "provenance": {},
            "positions": [],
        }
        if corruption == "future":
            result["observed_at"] = (observed + timedelta(days=1)).isoformat()
        elif corruption == "schema":
            result["schema_version"] = "position-health-transition-evaluation.v999"
        encoded = json.dumps(result).encode("utf-8")
        result_path.write_bytes(b"{broken" if corruption == "tampered" else encoded)

    record = PositionHealthTransitionRecord.proposal(
        event_id="stored-event",
        position_id="position-2330",
        decision_date="2026-09-30",
        previous_state=PositionHealthState.WATCH,
        proposed_state=PositionHealthState.WATCH,
        reasons=("fixture",),
    )
    current_payload: dict[str, object] = {
        "position": _position(),
        "provenance": {"observed_at": observed.isoformat()},
    }
    assert _verify_legacy_same_snapshot_reuse(
        output_dir=output_dir,
        current_input_payload=current_payload,
        current_input_hash="sha256:" + "0" * 64,
        current_observed=observed,
        current_record=record,
        existing_record=record,
    ) is None


def test_legacy_source_hash_and_no_follow_are_required(workspace_qa_tmp: Path) -> None:
    root = workspace_qa_tmp / "source"
    root.mkdir()
    path = root / "condition.json"
    path.write_text("{\"status\":\"valid\"}", encoding="utf-8")
    raw_hash = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert _read_hashed_legacy_file(
        role="condition",
        path=path,
        root=root,
        expected_hash=raw_hash,
        max_bytes=1024,
        proofs=[],
    ) == path.read_bytes()
    with pytest.raises(ValueError, match="source hash changed"):
        _read_hashed_legacy_file(
            role="condition",
            path=path,
            root=root,
            expected_hash="sha256:" + "0" * 64,
            max_bytes=1024,
            proofs=[],
        )


def test_legacy_source_caps_reject_oversized_and_symlinked_files(
    workspace_qa_tmp: Path,
) -> None:
    root = workspace_qa_tmp / "source_caps"
    root.mkdir()
    oversized = root / "oversized.json"
    oversized.write_bytes(b"0123456789")
    with pytest.raises(ExecutionArtifactIntegrityError, match="大小上限"):
        _read_hashed_legacy_file(
            role="condition",
            path=oversized,
            root=root,
            expected_hash="sha256:" + hashlib.sha256(oversized.read_bytes()).hexdigest(),
            max_bytes=4,
            proofs=[],
        )

    outside = workspace_qa_tmp / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ExecutionArtifactIntegrityError):
        _read_hashed_legacy_file(
            role="condition",
            path=outside,
            root=root,
            expected_hash="sha256:" + hashlib.sha256(outside.read_bytes()).hexdigest(),
            max_bytes=1024,
            proofs=[],
        )
    linked = root / "linked.json"
    try:
        linked.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"此 Windows 環境無法建立測試 symlink：{type(exc).__name__}")
    with pytest.raises(ExecutionArtifactIntegrityError):
        _read_hashed_legacy_file(
            role="condition",
            path=linked,
            root=root,
            expected_hash="sha256:" + hashlib.sha256(outside.read_bytes()).hexdigest(),
            max_bytes=1024,
            proofs=[],
        )


def test_captured_daily_source_requires_exact_date_and_suffix_hash(
    workspace_qa_tmp: Path,
) -> None:
    root = workspace_qa_tmp / "daily_sources"
    root.mkdir()
    raw = b'{"captured":"immutable"}'
    suffix = hashlib.sha256(raw).hexdigest()[:16]
    captured = root / f"condition_20260930_{suffix}.json"
    captured.write_bytes(raw)

    assert _is_captured_daily_source_path(
        captured,
        root=root,
        stem="condition",
        date_key="20260930",
    )
    assert _captured_daily_source_suffix_matches(
        captured,
        raw,
        stem="condition",
        date_key="20260930",
    )
    assert not _captured_daily_source_suffix_matches(
        captured.with_name("condition_20260930_0000000000000000.json"),
        raw,
        stem="condition",
        date_key="20260930",
    )
    assert not _is_captured_daily_source_path(
        captured,
        root=root,
        stem="condition",
        date_key="20260929",
    )
    assert _captured_daily_source_suffix_matches(
        root / "condition_20260930.json",
        raw,
        stem="condition",
        date_key="20260930",
    )


def test_legacy_source_reread_rejects_change_after_reconstruction(
    workspace_qa_tmp: Path,
) -> None:
    root = workspace_qa_tmp / "source_recheck"
    root.mkdir()
    path = root / "metrics.json"
    initial = b'{"value":"same"}'
    path.write_bytes(initial)
    expected = "sha256:" + hashlib.sha256(initial).hexdigest()
    _read_hashed_legacy_file(
        role="metrics_current_capture",
        path=path,
        root=root,
        expected_hash=expected,
        max_bytes=1024,
        proofs=[],
    )
    path.write_bytes(b'{"value":"changed"}')

    with pytest.raises(ValueError, match="source hash changed"):
        _reread_legacy_artifacts(
            [("metrics_current_capture", path, root, expected, 1024)]
        )


def test_feedback_status_changes_input_hash_and_event_id(tmp_path: Path) -> None:
    repository = PositionHealthTransitionRepository(tmp_path / "transitions.sqlite")
    evaluator, request = _complete_request(repository=repository)
    first = evaluator.evaluate(request)

    changed = DailyPositionHealthTransitionRequest(
        **{
            **request.__dict__,
            "feedback_status_by_position": {"position-2330": GateStatus.FAIL},
        }
    )
    result = DailyPositionHealthTransitionEvaluator(
        transition_repository=repository
    ).evaluate(changed)

    first_event = first["positions"][0]["transition_event"]
    changed_event = result["positions"][0]["transition_event"]
    assert first_event["input_hash"] != changed_event["input_hash"]
    assert first_event["event_id"] != changed_event["event_id"]
    assert result["status"] == "blocked"
    assert "transition_proposal_persistence_blocked:ValueError" in result["blockers"]


def test_concurrent_same_payload_is_idempotent(tmp_path: Path) -> None:
    repository_path = tmp_path / "transitions.sqlite"
    _, request = _complete_request(
        repository=PositionHealthTransitionRepository(repository_path)
    )

    def run_once() -> dict[str, object]:
        return DailyPositionHealthTransitionEvaluator(
            transition_repository=PositionHealthTransitionRepository(repository_path)
        ).evaluate(request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _: run_once(), (0, 1)))

    assert {item["status"] for item in results} == {"passed"}
    assert {
        item["positions"][0]["transition_event"]["persistence"]
        for item in results
    } == {"written", "idempotent"}
    assert len(
        PositionHealthTransitionRepository(repository_path).list_for_position(
            "position-2330"
        )
    ) == 1


def test_concurrent_different_payload_same_identity_is_rejected(tmp_path: Path) -> None:
    repository_path = tmp_path / "transitions.sqlite"
    _, request_one = _complete_request(metric_value="1")
    _, request_two = _complete_request(metric_value="2")

    def run_once(request: DailyPositionHealthTransitionRequest) -> dict[str, object]:
        return DailyPositionHealthTransitionEvaluator(
            transition_repository=PositionHealthTransitionRepository(repository_path)
        ).evaluate(request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(run_once, (request_one, request_two)))

    assert sorted(item["status"] for item in results) == ["blocked", "passed"]
    assert len(
        PositionHealthTransitionRepository(repository_path).list_for_position(
            "position-2330"
        )
    ) == 1


def test_exit_condition_has_priority_over_reduce_candidate() -> None:
    evaluator, request = _complete_request(
        condition_status="invalid",
        metric_value="11",
        action="reduce",
    )

    result = evaluator.evaluate(request)
    row = result["positions"][0]

    assert result["status"] == "passed"
    assert row["proposed_state"] == PositionHealthState.EXIT_CANDIDATE.value
    assert any("condition" in reason for reason in row["reasons"])
    assert "invalidation_triggered:drawdown_pct" in row["reasons"]


def test_missing_thesis_and_condition_is_degraded_watch(tmp_path: Path) -> None:
    repository = PositionHealthTransitionRepository(tmp_path / "transitions.sqlite")
    observed = _observed()
    decision_date = _request_date(observed)
    request = DailyPositionHealthTransitionRequest(
        decision_date=decision_date,
        observed_at=observed,
        positions=(_position(state="HEALTHY"),),
        previous_positions={"position-2330": {"state": "HEALTHY"}},
        provenance=_provenance(),
    )
    result = DailyPositionHealthTransitionEvaluator(
        transition_repository=repository
    ).evaluate(request)
    row = result["positions"][0]

    assert result["status"] == "degraded"
    assert row["proposed_state"] == PositionHealthState.WATCH.value
    assert "condition_observation_missing" in row["reasons"]
    assert "thesis_contract_missing" in row["reasons"]
    assert row["transition_event"]["persistence"] == "written"
    assert row["review_required"] is True


def test_known_exit_is_not_suppressed_by_missing_evidence() -> None:
    evaluator, request = _complete_request(previous_state="EXIT_CANDIDATE")
    request = DailyPositionHealthTransitionRequest(
        **{
            **request.__dict__,
            "thesis_by_position": {},
            "conditions_by_position": {},
            "metrics_by_position": {},
            "trading_dates": None,
        }
    )

    row = evaluator.evaluate(request)["positions"][0]
    assert row["previous_state"] == PositionHealthState.EXIT_CANDIDATE.value
    assert row["proposed_state"] == PositionHealthState.EXIT_CANDIDATE.value


def test_future_condition_is_blocked_and_not_persisted(tmp_path: Path) -> None:
    repository = PositionHealthTransitionRepository(tmp_path / "transitions.sqlite")
    evaluator, request = _complete_request(repository=repository)
    future_date = (date.fromisoformat(request.decision_date) + timedelta(days=1)).isoformat()
    condition = _condition(request.observed_at if isinstance(request.observed_at, datetime) else _observed())
    future_condition = PITConditionObservation(
        result=condition.result,
        current_snapshot=condition.current_snapshot,
        source_id=condition.source_id,
        source_snapshot_hash=condition.source_snapshot_hash,
        as_of_date=future_date,
        available_at=condition.available_at,
        quality=condition.quality,
        source_trace=condition.source_trace,
    )
    changed = DailyPositionHealthTransitionRequest(
        **{**request.__dict__, "conditions_by_position": {"position-2330": future_condition}}
    )

    result = evaluator.evaluate(changed)
    assert result["status"] == "blocked"
    assert result["positions"][0]["transition_event"]["persistence"] == "not_requested"
    assert repository.list_for_position("position-2330") == ()


def test_future_metric_is_blocked() -> None:
    evaluator, request = _complete_request()
    future_date = (date.fromisoformat(request.decision_date) + timedelta(days=1)).isoformat()
    changed = DailyPositionHealthTransitionRequest(
        **{
            **request.__dict__,
            "metrics_by_position": {
                "position-2330": (
                    PositionHealthMetric(
                        metric_id="drawdown_pct",
                        value=Decimal("1"),
                        available_date=future_date,
                    ),
                )
            },
        }
    )

    result = evaluator.evaluate(changed)
    assert result["status"] == "blocked"
    assert "input_integrity_blocked:metric_future_dated:drawdown_pct" in result["blockers"]


def test_missing_position_identity_is_degraded_without_event() -> None:
    evaluator, request = _complete_request()
    changed_position = dict(request.positions[0])
    changed_position.pop("position_id")
    changed = DailyPositionHealthTransitionRequest(
        **{**request.__dict__, "positions": (changed_position,)}
    )

    result = evaluator.evaluate(changed)
    row = result["positions"][0]
    assert result["status"] == "degraded"
    assert row["position_id"] is None
    assert row["transition_event"] is None
    assert "position_identity_missing" in row["reasons"]


def test_baseline_file_bridge_is_executable_and_degraded_without_sources(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        '{"as_of_date":"2026-09-08","source_snapshot_id":"snapshot-1",'
        '"source_snapshot_rows_sha256":"sha256:rows",'
        '"positions":[{"position_id":"p1","stock_code":"2330",'
        '"paper_shares":1000,"state":"WATCH",'
        '"entry_lineage_status":"same_snapshot_verified"}]}',
        encoding="utf-8",
    )
    output = tmp_path / "transition-output"

    result = evaluate_baseline_file(
        baseline_path=baseline,
        output_dir=output,
        observed_at=_observed(),
        decision_date="2026-09-08",
        transition_repository_path=output / "position_health_transitions.sqlite",
    )

    assert result["status"] == "degraded"
    assert result["positions"][0]["proposed_state"] == PositionHealthState.WATCH.value
    assert (output / "latest.json").exists()
    assert (output / "latest_status.json").exists()
    assert result["positions"][0]["transition_event"]["persistence"] == "written"
