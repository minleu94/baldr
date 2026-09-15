from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import ml_module.recommendation_calibration_authority as authority_module
from app_module.recommendation_learning_evidence_projection_service import (
    LearningHorizonProjection,
    LearningLaneProjection,
    RecommendationLearningEvidenceProjection,
    RecommendationLearningEvidenceProjectionService,
    _capture_surface,
    _horizon_scope_lane,
)
from ml_module.recommendation_calibration_authority import (
    RecommendationNaturalEvidenceComparison,
    RecommendationNaturalEvidenceScope,
    RecommendationNaturalEvidenceVerification,
    verify_natural_evidence_read_only,
)
from ml_module.recommendation_calibration_evidence import (
    RecommendationPredictionCaptureVerification,
    verify_prediction_capture_read_only,
)
from ml_module.recommendation_cost_scenario import cost_scenario_from_metadata


def _candidate_metadata(candidate_id: str) -> dict[str, object]:
    return {
        "schema_version": "recommendation-calibration-candidate.v1",
        "candidate_id": candidate_id,
        "model_id": candidate_id,
        "dataset_id": "dataset-fixture",
        "dataset_hash": "sha256:" + "1" * 64,
        "manifest_hash": "sha256:" + "2" * 64,
        "artifact_hash": "sha256:" + "3" * 64,
        "feature_registry_hash": "sha256:" + "4" * 64,
        "feature_schema_hash": "sha256:" + "5" * 64,
        "label_registry_hash": "sha256:" + "6" * 64,
        "candidate_freeze_hash": "sha256:" + "7" * 64,
        "candidate_frozen_at": "2026-09-01T01:00:00+00:00",
        "training_as_of": "2026-08-31",
        "horizon_trading_days": 20,
        "fixed_round_trip_cost_bp": 50,
        "shadow_only": True,
        "production_action_allowed": False,
    }


def _synthetic_projection_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    learning_root = tmp_path / "learning"
    candidate_root = learning_root / "runs" / "2026-09-14" / "candidate-fixture"
    capture_path = learning_root / "captures" / "2026-09-14" / "capture.json"
    receipt_path = learning_root / "evidence" / "candidate" / "2026-09-14.json"
    candidate_root.mkdir(parents=True)
    capture_path.parent.mkdir(parents=True)
    receipt_path.parent.mkdir(parents=True)
    candidate_id = "candidate-fixture"
    metadata = _candidate_metadata(candidate_id)
    (candidate_root / "candidate.json").write_text(json.dumps(metadata), encoding="utf-8")
    capture_path.write_text(
        json.dumps(
            {
                "schema_version": "recommendation-prediction-capture.v2",
                "capture_id": "capture-fixture",
                "candidate_id": candidate_id,
                "capture_as_of_date": "2026-09-14",
                "rows": [{"row_id": "fixture-row", "symbol": "1101"}],
            }
        ),
        encoding="utf-8",
    )
    receipt_path.write_text(
        json.dumps(
            {
                "source_capture_ids": ["capture-fixture"],
                "source_capture_paths": [str(capture_path)],
                "capture_path": str(capture_path),
            }
        ),
        encoding="utf-8",
    )
    status_path = learning_root / "latest_status.json"
    status_path.write_text(
        json.dumps(
            {
                "schema_version": "daily-recommendation-learning-receipt.v1",
                "cli_schema_version": "daily-recommendation-learning-cli-result.v3",
                "status": "completed",
                "decision": "retain_current",
                "decision_reason": "natural_forward_evidence_receipt_missing",
                "decision_date": "2026-09-14",
                "candidate_id": candidate_id,
                "challenger": {
                    "candidate_id": candidate_id,
                    "candidate_root": str(candidate_root),
                    "status": "pending",
                },
                "natural_evidence": {
                    "status": "matured",
                    "evidence": {"receipt_path": str(receipt_path)},
                },
                "active_pointer": {"status": "rule_only"},
                "live_capture": {
                    "candidate": {
                        "status": "captured",
                        "capture_path": str(capture_path),
                        "row_count": 1,
                    }
                },
                "evaluation": {"untouched_test_sample_count": 4},
            }
        ),
        encoding="utf-8",
    )
    return learning_root, status_path, candidate_id


def _verification(receipt_path: Path, candidate_id: str) -> RecommendationNaturalEvidenceVerification:
    capture_path = receipt_path.parent.parent.parent / "captures" / "2026-09-14" / "capture.json"
    comparisons = (
        RecommendationNaturalEvidenceComparison(
            capture_row_id="row-1",
            symbol="1101",
            capture_as_of_date="2026-09-01",
            label_end_date="2026-09-29",
            label_available_date="2026-09-29",
            candidate_probability_bp=5_500,
            champion_probability_bp=5_000,
            upside_label=1,
            stock_return_bp=1_000,
        ),
        RecommendationNaturalEvidenceComparison(
            capture_row_id="row-2",
            symbol="2330",
            capture_as_of_date="2026-09-02",
            label_end_date="2026-09-30",
            label_available_date="2026-09-30",
            candidate_probability_bp=8_500,
            champion_probability_bp=5_000,
            upside_label=0,
            stock_return_bp=-1_000,
        ),
    )
    scope = RecommendationNaturalEvidenceScope(
        source_id="scheduled_forward_outcomes",
        source_kind="matured_forward_prediction_capture",
        capture_origin="scheduled_live",
        as_of_date="2026-09-14",
        capture_as_of_date="2026-09-02",
        captured_at="2026-09-02T01:00:00+00:00",
        candidate_frozen_at="2026-08-31T01:00:00+00:00",
        candidate_id=candidate_id,
        capture_id="capture-fixture",
        capture_hash="sha256:" + "8" * 64,
        candidate_freeze_hash="sha256:" + "7" * 64,
        same_date_same_cost=True,
        source_capture_ids=("capture-fixture",),
        source_capture_hashes=("sha256:" + "8" * 64,),
        source_capture_paths=(str(capture_path),),
        cost_basis="fixed_round_trip_bp",
        cost_scenario_id="legacy-fixed-round-trip-bp",
        cost_scenario_version="legacy-fixed-round-trip-bp-v1",
        cost_scenario_hash="sha256:" + "9" * 64,
        fixed_round_trip_cost_bp=50,
    )
    return RecommendationNaturalEvidenceVerification(
        evidence_id="natural-evidence-fixture",
        receipt_path=str(receipt_path),
        receipt_hash="sha256:" + "a" * 64,
        matured_sample_count=2,
        matured_unique_decision_date_count=2,
        observed_champion_brier_bp=2_500,
        observed_candidate_brier_bp=2_000,
        observed_brier_improvement_bp=500,
        observed_calibration_gap_bp=1_500,
        after_cost_evaluation_status="missing_liquidity_or_baseline",
        after_cost_matured_sample_count=0,
        observed_champion_after_cost_brier_bp=None,
        observed_candidate_after_cost_brier_bp=None,
        observed_after_cost_brier_improvement_bp=None,
        observed_after_cost_calibration_gap_bp=None,
        scope=scope,
        comparisons=comparisons,
    )


def test_projection_uses_verified_comparisons_and_separates_historical_replay(tmp_path: Path) -> None:
    learning_root, status_path, candidate_id = _synthetic_projection_fixture(tmp_path)
    receipt_path = learning_root / "evidence" / "candidate" / "2026-09-14.json"
    verification = _verification(receipt_path, candidate_id)

    def verify(*_args, **_kwargs):
        return verification

    projection = RecommendationLearningEvidenceProjectionService(
        latest_status_path=status_path,
        learning_root=learning_root,
        candidate_verifier=verify,
        capture_verifier=lambda _path: RecommendationPredictionCaptureVerification(
            capture_id="capture-fixture",
            candidate_id=candidate_id,
            capture_as_of_date="2026-09-14",
            captured_at="2026-09-14T01:00:00+00:00",
            capture_origin="scheduled_live",
            capture_hash="sha256:" + "8" * 64,
            row_count=1,
            cost_basis="fixed_round_trip_bp",
            cost_scenario_id="legacy-fixed-round-trip-bp",
            cost_scenario_version="legacy-fixed-round-trip-bp-v1",
            cost_scenario_hash=cost_scenario_from_metadata(
                _candidate_metadata(candidate_id), fixed_round_trip_cost_bp=50
            ).scenario_hash,
            fixed_round_trip_cost_bp=50,
            source_contract_status="ready",
        ),
        consumer=None,
        cost_lane="legacy_fixed_bp",
    ).inspect("2026-09-14")

    assert projection.status == "verified"
    assert projection.cost_lane == "legacy_fixed_bp"
    assert projection.data_recorded_status == "recorded"
    assert projection.candidate_lane.status == "verified"
    assert projection.candidate_lane.matured_sample_count == 2
    assert projection.candidate_lane.matured_decision_date_count == 2
    assert projection.historical_evaluation_sample_count == 4
    assert projection.historical_evaluation_status == "research_only_historical_replay"
    assert {item.target for item in projection.reliability_bins} == {"upside_probability"}
    assert all(item.sample_count == 1 for item in projection.reliability_bins)
    assert "ranking_score" not in json.dumps(projection.to_dict())


def test_projection_fail_closed_for_stale_or_invalid_provenance(tmp_path: Path) -> None:
    learning_root, status_path, candidate_id = _synthetic_projection_fixture(tmp_path)
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    payload["decision_date"] = "2026-09-13"
    status_path.write_text(json.dumps(payload), encoding="utf-8")

    def verify(*_args, **_kwargs):
        raise ValueError("natural_evidence_receipt_hash_mismatch")

    projection = RecommendationLearningEvidenceProjectionService(
        latest_status_path=status_path,
        learning_root=learning_root,
        candidate_verifier=verify,
        consumer=None,
        cost_lane="legacy_fixed_bp",
    ).inspect("2026-09-14")
    assert projection.status == "stale"
    assert projection.candidate_lane.status == "stale"
    assert projection.reliability_bins == ()

    payload["decision_date"] = "2026-09-14"
    payload["candidate_id"] = "replacement-candidate"
    status_path.write_text(json.dumps(payload), encoding="utf-8")
    blocked = RecommendationLearningEvidenceProjectionService(
        latest_status_path=status_path,
        learning_root=learning_root,
        candidate_verifier=verify,
        consumer=None,
        cost_lane="legacy_fixed_bp",
    ).inspect("2026-09-14")
    assert blocked.candidate_lane.status == "blocked_provenance"
    assert blocked.reliability_bins == ()


def test_cost_lane_defaults_are_separate_and_banktaiwan_is_default(tmp_path: Path) -> None:
    config = SimpleNamespace(data_root=tmp_path / "FA_Data")
    bank = RecommendationLearningEvidenceProjectionService(config)
    legacy = RecommendationLearningEvidenceProjectionService(config, cost_lane="legacy_fixed_bp")
    assert bank.cost_lane == "banktaiwan_estimated_research"
    assert bank.learning_root == (tmp_path / "FA_Data_Shadow_BankTaiwan" / "recommendation_learning").resolve()
    assert legacy.cost_lane == "legacy_fixed_bp"
    assert legacy.learning_root == (tmp_path / "FA_Data_Shadow" / "recommendation_learning").resolve()


def test_public_natural_verifier_preserves_artifacts_and_rejects_bad_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reuse the existing end-to-end capture/evidence fixture so this test hits
    # the authority's real verifier rather than a parallel fake implementation.
    from test_daily_recommendation_learning_loop import _candidate, _natural_receipt

    _, candidate_root, metadata = _candidate(
        tmp_path,
        shift=0,
        candidate_day="2026-06-01",
    )
    natural = _natural_receipt(
        tmp_path,
        root=candidate_root,
        candidate_day="2026-06-01",
        evaluation_day="2026-07-20",
    )
    receipt_path = Path(natural.receipt_path)
    before = {
        path: path.read_bytes()
        for path in (receipt_path, candidate_root / "candidate.json")
    }
    verified = verify_natural_evidence_read_only(
        natural,
        decision_date="2026-07-20",
        candidate_id=str(metadata["candidate_id"]),
        candidate_root=candidate_root,
        candidate_metadata=metadata,
    )
    assert verified.status == "verified"
    assert verified.matured_sample_count == len(verified.comparisons)
    assert all(path.read_bytes() == content for path, content in before.items())

    with pytest.raises(ValueError):
        verify_natural_evidence_read_only(
            replace(natural, receipt_hash="sha256:" + "0" * 64),
            decision_date="2026-07-20",
            candidate_id=str(metadata["candidate_id"]),
            candidate_root=candidate_root,
            candidate_metadata=metadata,
        )

    with pytest.raises(ValueError):
        verify_natural_evidence_read_only(
            replace(natural, receipt_path=str(tmp_path / "outside-receipt.json")),
            decision_date="2026-07-20",
            candidate_id=str(metadata["candidate_id"]),
            candidate_root=candidate_root,
            candidate_metadata=metadata,
        )

    capture_path = tmp_path / "captures" / "2026-06-01" / "00.json"
    capture_verification = verify_prediction_capture_read_only(capture_path)
    assert capture_verification.candidate_id == str(metadata["candidate_id"])
    original_capture_bytes = capture_path.read_bytes()
    tampered_capture = json.loads(capture_path.read_text(encoding="utf-8"))
    tampered_capture["rows"][0]["candidate_probability_bp"] = 4_999
    capture_path.write_text(json.dumps(tampered_capture), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_prediction_capture_read_only(capture_path)

    # Restore the capture only so the following race test exercises the
    # authority receipt, not the intentionally tampered capture.
    capture_path.write_bytes(original_capture_bytes)
    original_verify = authority_module._verify_natural_evidence

    def verify_then_mutate(*args, **kwargs):
        result = original_verify(*args, **kwargs)
        receipt_path.write_text("{}", encoding="utf-8")
        return result

    monkeypatch.setattr(authority_module, "_verify_natural_evidence", verify_then_mutate)
    with pytest.raises(ValueError, match="natural_evidence_receipt_changed_after_verification"):
        verify_natural_evidence_read_only(
            natural,
            decision_date="2026-07-20",
            candidate_id=str(metadata["candidate_id"]),
            candidate_root=candidate_root,
            candidate_metadata=metadata,
        )


def test_capture_surface_blocks_missing_date_history_and_cost_mismatch(tmp_path: Path) -> None:
    learning_root = tmp_path / "learning"
    capture_path = learning_root / "captures" / "2026-09-14" / "capture.json"
    capture_path.parent.mkdir(parents=True)
    capture_path.write_text("{}", encoding="utf-8")
    candidate_id = "candidate-fixture"
    expected_scenario = cost_scenario_from_metadata(
        _candidate_metadata(candidate_id), fixed_round_trip_cost_bp=50
    )
    valid = RecommendationPredictionCaptureVerification(
        capture_id="capture-fixture",
        candidate_id=candidate_id,
        capture_as_of_date="2026-09-14",
        captured_at="2026-09-14T01:00:00+00:00",
        capture_origin="scheduled_live",
        capture_hash="sha256:" + "8" * 64,
        row_count=1,
        cost_basis=expected_scenario.cost_basis,
        cost_scenario_id=expected_scenario.scenario_id,
        cost_scenario_version=expected_scenario.scenario_version,
        cost_scenario_hash=expected_scenario.scenario_hash,
        fixed_round_trip_cost_bp=50,
        source_contract_status="ready",
    )
    base = {
        "status": "captured",
        "capture_path": str(capture_path),
    }

    def surface(
        verification: RecommendationPredictionCaptureVerification,
    ) -> tuple[str, str]:
        return _capture_surface(
            base,
            candidate_id=candidate_id,
            learning_root=learning_root,
            requested_date="2026-09-14",
            date_status="current",
            conflict_symbols=(),
            expected_cost_scenario=expected_scenario,
            capture_verifier=lambda _path: verification,
        )

    assert surface(valid)[0] == "recorded"
    assert surface(replace(valid, capture_as_of_date=""))[0] == "blocked_provenance"
    assert surface(replace(valid, capture_origin="historical_replay"))[0] == "blocked_provenance"
    assert surface(replace(valid, cost_scenario_hash="sha256:" + "0" * 64))[0] == "blocked_provenance"

    def changed_rows(_path: Path) -> RecommendationPredictionCaptureVerification:
        raise ValueError("capture_content_hash_mismatch")

    status, reason = _capture_surface(
        base,
        candidate_id=candidate_id,
        learning_root=learning_root,
        requested_date="2026-09-14",
        date_status="current",
        conflict_symbols=(),
        expected_cost_scenario=expected_scenario,
        capture_verifier=changed_rows,
    )
    assert status == "blocked_provenance"
    assert "capture_content_hash_mismatch" in reason


def test_valid_capture_without_receipt_remains_pending_not_verified(tmp_path: Path) -> None:
    learning_root, status_path, candidate_id = _synthetic_projection_fixture(tmp_path)
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    payload["natural_evidence"] = {
        "status": "pending",
        "reason": "natural_forward_evidence_receipt_missing",
    }
    status_path.write_text(json.dumps(payload), encoding="utf-8")
    scenario = cost_scenario_from_metadata(
        _candidate_metadata(candidate_id), fixed_round_trip_cost_bp=50
    )
    verification = RecommendationPredictionCaptureVerification(
        capture_id="capture-fixture",
        candidate_id=candidate_id,
        capture_as_of_date="2026-09-14",
        captured_at="2026-09-14T01:00:00+00:00",
        capture_origin="scheduled_live",
        capture_hash="sha256:" + "8" * 64,
        row_count=1,
        cost_basis=scenario.cost_basis,
        cost_scenario_id=scenario.scenario_id,
        cost_scenario_version=scenario.scenario_version,
        cost_scenario_hash=scenario.scenario_hash,
        fixed_round_trip_cost_bp=50,
        source_contract_status="ready",
    )
    projection = RecommendationLearningEvidenceProjectionService(
        latest_status_path=status_path,
        learning_root=learning_root,
        capture_verifier=lambda _path: verification,
        consumer=None,
        cost_lane="legacy_fixed_bp",
    ).inspect("2026-09-14")
    assert projection.data_recorded_status == "recorded"
    assert projection.candidate_lane.status == "pending"
    assert projection.candidate_lane.reliability_bins == ()
    assert projection.candidate_lane.horizons[0].status == "pending"


def test_requested_date_is_required_for_freshness_and_stale_capture_is_not_recorded(
    tmp_path: Path,
) -> None:
    learning_root, status_path, candidate_id = _synthetic_projection_fixture(tmp_path)
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    payload["decision_date"] = "2026-09-01"
    payload["natural_evidence"] = {
        "status": "pending",
        "reason": "natural_forward_evidence_receipt_missing",
    }
    status_path.write_text(json.dumps(payload), encoding="utf-8")
    projection = RecommendationLearningEvidenceProjectionService(
        latest_status_path=status_path,
        learning_root=learning_root,
        requested_date_resolver=lambda: "2026-09-14",
        consumer=None,
        cost_lane="legacy_fixed_bp",
    ).inspect()
    assert projection.requested_date == "2026-09-14"
    assert projection.learning_decision_date == "2026-09-01"
    assert projection.status == "stale"
    assert projection.candidate_lane.status == "stale"
    assert projection.data_recorded_status == "stale"
    assert projection.verified_lane is None


def test_weekend_resolution_uses_supplied_official_session_without_calendar_day_inference(
    tmp_path: Path,
) -> None:
    learning_root, status_path, candidate_id = _synthetic_projection_fixture(tmp_path)
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    payload["decision_date"] = "2026-09-12"
    payload["natural_evidence"] = {
        "status": "pending",
        "reason": "natural_forward_evidence_receipt_missing",
    }
    status_path.write_text(json.dumps(payload), encoding="utf-8")
    scenario = cost_scenario_from_metadata(
        _candidate_metadata(candidate_id), fixed_round_trip_cost_bp=50
    )
    capture_verification = RecommendationPredictionCaptureVerification(
        capture_id="capture-fixture",
        candidate_id=candidate_id,
        capture_as_of_date="2026-09-12",
        captured_at="2026-09-12T01:00:00+00:00",
        capture_origin="scheduled_live",
        capture_hash="sha256:" + "8" * 64,
        row_count=1,
        cost_basis=scenario.cost_basis,
        cost_scenario_id=scenario.scenario_id,
        cost_scenario_version=scenario.scenario_version,
        cost_scenario_hash=scenario.scenario_hash,
        fixed_round_trip_cost_bp=50,
        source_contract_status="ready",
    )
    projection = RecommendationLearningEvidenceProjectionService(
        latest_status_path=status_path,
        learning_root=learning_root,
        requested_date_resolver=lambda: "2026-09-12",
        capture_verifier=lambda _path: capture_verification,
        consumer=None,
        cost_lane="legacy_fixed_bp",
    ).inspect()
    assert projection.requested_date == "2026-09-12"
    assert projection.status == "pending"
    assert projection.data_recorded_status == "recorded"
    assert projection.candidate_lane.status == "pending"


def test_unknown_default_date_never_promotes_receipt_to_current(tmp_path: Path) -> None:
    learning_root, status_path, _candidate_id = _synthetic_projection_fixture(tmp_path)
    projection = RecommendationLearningEvidenceProjectionService(
        latest_status_path=status_path,
        learning_root=learning_root,
        requested_date_resolver=lambda: None,
        consumer=None,
        cost_lane="legacy_fixed_bp",
    ).inspect()
    assert projection.requested_date is None
    assert projection.status == "unknown"
    assert projection.candidate_lane.status == "unknown"
    assert projection.data_recorded_status == "unknown"


def test_stale_capture_is_never_reported_as_recorded_or_verified(tmp_path: Path) -> None:
    learning_root, status_path, candidate_id = _synthetic_projection_fixture(tmp_path)
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    payload["natural_evidence"] = {
        "status": "pending",
        "reason": "natural_forward_evidence_receipt_missing",
    }
    status_path.write_text(json.dumps(payload), encoding="utf-8")
    expected_scenario = cost_scenario_from_metadata(
        _candidate_metadata(candidate_id), fixed_round_trip_cost_bp=50
    )
    stale_capture = RecommendationPredictionCaptureVerification(
        capture_id="capture-fixture",
        candidate_id=candidate_id,
        capture_as_of_date="2026-09-01",
        captured_at="2026-09-01T01:00:00+00:00",
        capture_origin="scheduled_live",
        capture_hash="sha256:" + "8" * 64,
        row_count=1,
        cost_basis=expected_scenario.cost_basis,
        cost_scenario_id=expected_scenario.scenario_id,
        cost_scenario_version=expected_scenario.scenario_version,
        cost_scenario_hash=expected_scenario.scenario_hash,
        fixed_round_trip_cost_bp=50,
        source_contract_status="ready",
    )
    projection = RecommendationLearningEvidenceProjectionService(
        latest_status_path=status_path,
        learning_root=learning_root,
        capture_verifier=lambda _path: stale_capture,
        consumer=None,
        cost_lane="legacy_fixed_bp",
    ).inspect("2026-09-14")
    assert projection.status == "stale"
    assert projection.data_recorded_status == "stale"
    assert projection.candidate_lane.status == "stale"
    assert projection.verified_lane is None


def test_candidate_and_active_cost_scope_mismatch_fail_closed(tmp_path: Path) -> None:
    learning_root, status_path, candidate_id = _synthetic_projection_fixture(tmp_path)
    candidate_scope = RecommendationLearningEvidenceProjectionService(
        latest_status_path=status_path,
        learning_root=learning_root,
        consumer=None,
        cost_lane="banktaiwan_estimated_research",
    ).inspect("2026-09-14")
    assert candidate_scope.candidate_lane.status == "blocked_provenance"
    assert "blocked_cost_scope:selected=banktaiwan_estimated_research" in candidate_scope.candidate_lane.reason

    active_root = tmp_path / "active-learning"
    receipt_path = active_root / "evidence" / "active.json"
    receipt_path.parent.mkdir(parents=True)
    scenario = cost_scenario_from_metadata(
        _candidate_metadata(candidate_id), fixed_round_trip_cost_bp=50
    )
    receipt_path.write_text(
        json.dumps({
            "evidence_id": "active-evidence",
            "comparisons": [],
            **scenario.metadata(),
        }),
        encoding="utf-8",
    )
    active_status_path = active_root / "latest_status.json"
    active_status_path.write_text(
        json.dumps({
            "decision_date": "2026-09-14",
            "active_pointer": {"status": "active", "candidate_id": "active-candidate"},
            "active_model_natural_evidence": {"evidence": {"receipt_path": str(receipt_path)}},
        }),
        encoding="utf-8",
    )

    class FakeActiveConsumer:
        def reload(self, *, decision_date: str | None = None) -> str:
            return "active"

        def active_identity(self, *, decision_date: str) -> dict[str, str]:
            return {"candidate_id": "active-candidate", "model_id": "active-model"}

    active_scope = RecommendationLearningEvidenceProjectionService(
        latest_status_path=active_status_path,
        learning_root=active_root,
        consumer=FakeActiveConsumer(),  # type: ignore[arg-type]
        active_verifier=lambda *_args, **_kwargs: None,
        cost_lane="banktaiwan_estimated_research",
    ).inspect("2026-09-14")
    assert active_scope.active_lane.status == "blocked_provenance"
    assert "blocked_cost_scope:selected=banktaiwan_estimated_research" in active_scope.active_lane.reason


def test_candidate_verifier_failure_keeps_failure_branch_typed(tmp_path: Path) -> None:
    learning_root, status_path, candidate_id = _synthetic_projection_fixture(tmp_path)
    expected_scenario = cost_scenario_from_metadata(
        _candidate_metadata(candidate_id), fixed_round_trip_cost_bp=50
    )
    capture_verification = RecommendationPredictionCaptureVerification(
        capture_id="capture-fixture",
        candidate_id=candidate_id,
        capture_as_of_date="2026-09-14",
        captured_at="2026-09-14T01:00:00+00:00",
        capture_origin="scheduled_live",
        capture_hash="sha256:" + "8" * 64,
        row_count=1,
        cost_basis=expected_scenario.cost_basis,
        cost_scenario_id=expected_scenario.scenario_id,
        cost_scenario_version=expected_scenario.scenario_version,
        cost_scenario_hash=expected_scenario.scenario_hash,
        fixed_round_trip_cost_bp=50,
        source_contract_status="ready",
    )

    def fail_verifier(*_args, **_kwargs):
        raise ValueError("natural_evidence_receipt_hash_mismatch")

    projection = RecommendationLearningEvidenceProjectionService(
        latest_status_path=status_path,
        learning_root=learning_root,
        candidate_verifier=fail_verifier,
        capture_verifier=lambda _path: capture_verification,
        consumer=None,
        cost_lane="legacy_fixed_bp",
    ).inspect("2026-09-14")
    assert projection.candidate_lane.status == "blocked_provenance"
    assert "natural_evidence_receipt_hash_mismatch" in projection.candidate_lane.reason
    assert projection.candidate_lane.capture_status == "recorded"


def test_candidate_and_active_horizons_keep_separate_scope() -> None:
    candidate_horizon = LearningHorizonProjection(
        horizon_days=20,
        capture_count=20,
        recorded_row_count=20,
        matured_sample_count=20,
        matured_decision_date_count=2,
        status="matured",
        reason="candidate verifier",
    )
    active_horizon = LearningHorizonProjection(
        horizon_days=20,
        capture_count=10,
        recorded_row_count=10,
        matured_sample_count=10,
        matured_decision_date_count=10,
        status="matured",
        reason="active verifier",
    )
    candidate_lane = LearningLaneProjection(
        lane_id="candidate_natural",
        label="候選 natural evidence",
        status="verified",
        reason="candidate",
        model_version="candidate-model",
        cost_scenario_id="candidate-scenario",
        horizons=(candidate_horizon,),
    )
    active_lane = LearningLaneProjection(
        lane_id="active_model_natural",
        label="active model natural evidence",
        status="verified",
        reason="active",
        model_version="active-model",
        cost_scenario_id="active-scenario",
        horizons=(active_horizon,),
    )

    selected = _horizon_scope_lane(candidate_lane, active_lane)
    projection = RecommendationLearningEvidenceProjection(
        schema_version="test",
        status="verified",
        requested_date="2026-09-14",
        learning_decision_date="2026-09-14",
        checked_at=None,
        decision="retain_current",
        decision_reason="test",
        candidate_id="candidate",
        candidate_model_version="candidate-model",
        candidate_training_as_of="2026-09-01",
        data_recorded_status="recorded",
        data_recorded_reason="test",
        next_gap="test",
        adoption_reason="test",
        candidate_lane=candidate_lane,
        active_lane=active_lane,
        horizons=selected.horizons,
        horizon_scope_lane_id=selected.lane_id,
        horizon_scope_label=selected.label,
        horizon_scope_model_version=selected.model_version,
        horizon_scope_cost_scenario_id=selected.cost_scenario_id,
    )

    assert candidate_lane.horizons[0].matured_sample_count == 20
    assert candidate_lane.horizons[0].matured_decision_date_count == 2
    assert active_lane.horizons[0].matured_sample_count == 10
    assert active_lane.horizons[0].matured_decision_date_count == 10
    assert projection.horizon_scope_lane_id == "active_model_natural"
    assert projection.horizons == active_lane.horizons
    assert not any(
        item.matured_sample_count == 20 and item.matured_decision_date_count == 10
        for item in projection.horizons
    )
