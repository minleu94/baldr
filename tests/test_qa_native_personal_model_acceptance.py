"""小型 runner 契約測試；只含 offscreen Qt modal harness，不讀模型或正式 DB。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from app_module.recommendation.personal_use_policy import (
    PersonalCalibrationCandidateV1,
    PersonalSourceFileIdentityV1,
    PersonalSourceReplayScopeV1,
    PersonalSourceTimeBindingProposalV1,
)
from app_module.recommendation.ml_postcalibration_handoff import (
    _normalize_event_value_v1,
)
from scripts import qa_native_personal_model_acceptance as qa


def _binding_fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], Path, Path, dict[str, int]]:
    source_db = tmp_path / "source.sqlite"
    source_db.write_bytes(b"isolated source identity fixture")
    source_stat = source_db.stat()
    identity = {"device": int(source_stat.st_dev), "inode": int(source_stat.st_ino)}
    candidate_root = tmp_path / "learning" / "candidate"
    candidate_root.mkdir(parents=True)
    candidate = {
        **qa.CANDIDATE_PINS,
        "candidate_root": str(candidate_root.resolve(strict=True)),
    }
    replay_scope = {
        "dataset_ids": ["recommendation-dataset-0123456789abcdef"],
        "decision_dates": [
            (date(2026, 1, 1) + timedelta(days=offset)).isoformat()
            for offset in range(64)
        ],
        "symbols": [f"{2300 + offset}" for offset in range(8)],
        "sample_count": 512,
    }
    slice_hash = qa.EXPECTED_SOURCE_SLICE_SHA256
    proposal = {
        "schema_version": "personal-source-time-binding-proposal.v1",
        "basis": "user_declared_source_time",
        "source_database_path": str(source_db.resolve(strict=True)),
        "file_identity": identity,
        "source_slice_sha256": slice_hash,
        "candidate": candidate,
        "replay_scope": replay_scope,
        "research_only": True,
        "official_historical_pit_verified": False,
    }
    confirmed_at = "2026-09-28T12:00:00+00:00"
    trust = {
        "schema_version": "personal-user-declared-source-time-trust.v1",
        "basis": "user_declared_source_time",
        "confirmed_at": confirmed_at,
        "source_database_path": str(source_db.resolve(strict=True)),
        "file_identity": identity,
        "source_slice_sha256": slice_hash,
        "candidate": candidate,
        "replay_scope": replay_scope,
        "research_only": True,
        "official_historical_pit_verified": False,
    }
    policy = {
        "schema_version": "recommendation-personal-use-policy.v2",
        "mode": "personal_calibrated_probability",
        "confirmed_at": confirmed_at,
        "candidate": candidate,
        "source_time_trust": trust,
    }
    return policy, proposal, source_db, candidate_root, identity


def _source_proposal_dto(
    tmp_path: Path,
    *,
    sample_count: int = 512,
    date_count: int = 64,
    symbol_count: int = 8,
) -> tuple[PersonalSourceTimeBindingProposalV1, Path, Path]:
    source_db = tmp_path / "source.sqlite"
    source_db.write_bytes(b"isolated source identity fixture")
    source_stat = source_db.stat()
    candidate_root = tmp_path / "learning" / "candidate"
    candidate_root.mkdir(parents=True)
    candidate = PersonalCalibrationCandidateV1(
        candidate_id=qa.CANDIDATE_ID,
        candidate_root=str(candidate_root.resolve(strict=True)),
        candidate_json_sha256=qa.CANDIDATE_PINS["candidate_json_sha256"],
        candidate_manifest_hash=qa.CANDIDATE_PINS["candidate_manifest_hash"],
        candidate_artifact_hash=qa.CANDIDATE_PINS["candidate_artifact_hash"],
        candidate_freeze_hash=qa.CANDIDATE_PINS["candidate_freeze_hash"],
        dataset_hash=qa.CANDIDATE_PINS["dataset_hash"],
    )
    replay_scope = PersonalSourceReplayScopeV1(
        dataset_ids=("recommendation-dataset-0123456789abcdef",),
        decision_dates=tuple(
            (date(2026, 1, 1) + timedelta(days=offset)).isoformat()
            for offset in range(date_count)
        ),
        symbols=tuple(f"{2300 + offset}" for offset in range(symbol_count)),
        sample_count=sample_count,
    )
    proposal = PersonalSourceTimeBindingProposalV1(
        source_database_path=str(source_db.resolve(strict=True)),
        file_identity=PersonalSourceFileIdentityV1(
            device=int(source_stat.st_dev), inode=int(source_stat.st_ino)
        ),
        source_database_size_bytes=source_stat.st_size,
        source_slice_sha256=qa.EXPECTED_SOURCE_SLICE_SHA256,
        candidate=candidate,
        replay_scope=replay_scope,
    )
    return proposal, source_db, candidate_root


def test_initial_source_proposal_reads_real_replay_scope_dto_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, source_db, candidate_root = _source_proposal_dto(tmp_path)
    monkeypatch.setattr(qa, "CANDIDATE_ROOT", candidate_root)

    verified = qa._verify_initial_proposal(proposal=proposal, db_path=source_db)

    assert verified["source_slice_sha256"] == qa.EXPECTED_SOURCE_SLICE_SHA256
    assert verified["replay_scope"] == proposal.replay_scope.to_dict()
    assert verified["replay_scope"]["sample_count"] == 512
    assert len(verified["replay_scope"]["decision_dates"]) == 64
    assert len(verified["replay_scope"]["symbols"]) == 8


@pytest.mark.parametrize(
    ("sample_count", "date_count", "symbol_count"),
    [(511, 64, 8), (512, 63, 8), (512, 64, 7)],
)
def test_initial_source_proposal_rejects_wrong_replay_scope_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sample_count: int,
    date_count: int,
    symbol_count: int,
) -> None:
    proposal, source_db, candidate_root = _source_proposal_dto(
        tmp_path,
        sample_count=sample_count,
        date_count=date_count,
        symbol_count=symbol_count,
    )
    monkeypatch.setattr(qa, "CANDIDATE_ROOT", candidate_root)

    with pytest.raises(qa.AcceptanceError, match="source preview"):
        qa._verify_initial_proposal(proposal=proposal, db_path=source_db)


def test_initial_source_proposal_requires_replay_scope_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, source_db, candidate_root = _source_proposal_dto(tmp_path)
    monkeypatch.setattr(qa, "CANDIDATE_ROOT", candidate_root)
    malformed_mapping = proposal.to_dict()
    malformed_mapping["replay_scope"] = None
    malformed = SimpleNamespace(
        basis=proposal.basis,
        research_only=proposal.research_only,
        official_historical_pit_verified=proposal.official_historical_pit_verified,
        candidate=proposal.candidate,
        source_database_path=proposal.source_database_path,
        file_identity=proposal.file_identity,
        source_database_size_bytes=proposal.source_database_size_bytes,
        source_slice_sha256=proposal.source_slice_sha256,
        replay_scope=proposal.replay_scope,
        to_dict=lambda: malformed_mapping,
    )

    with pytest.raises(qa.AcceptanceError, match="source preview"):
        qa._verify_initial_proposal(proposal=malformed, db_path=source_db)


def test_source_time_binding_requires_same_database_and_candidate_identity(
    tmp_path: Path,
) -> None:
    policy, proposal, source_db, candidate_root, identity = _binding_fixture(tmp_path)

    assert qa._source_binding_mismatches(
        policy=policy,
        proposal=proposal,
        config_db_path=source_db,
        expected_candidate_root=candidate_root,
        actual_file_identity=identity,
    ) == []


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("source_path", "source_database_path_mismatch"),
        ("file_identity", "runtime_file_identity_mismatch"),
        ("source_slice", "source_slice_sha256_mismatch"),
        ("candidate_pin", "proposal_candidate_pins_mismatch"),
        ("official_flag", "official_pit_marker_mismatch"),
    ],
)
def test_source_time_binding_rejects_drifted_proof(
    tmp_path: Path,
    mutation: str,
    expected_reason: str,
) -> None:
    policy, proposal, source_db, candidate_root, identity = _binding_fixture(tmp_path)
    other_db = tmp_path / "other.sqlite"
    other_db.write_bytes(b"different isolated source")
    if mutation == "source_path":
        proposal["source_database_path"] = str(other_db.resolve(strict=True))
    elif mutation == "file_identity":
        proposal["file_identity"] = {**identity, "inode": identity["inode"] + 1}
    elif mutation == "source_slice":
        proposal["source_slice_sha256"] = "sha256:" + "1" * 64
    elif mutation == "candidate_pin":
        proposal["candidate"] = {
            **proposal["candidate"],
            "candidate_artifact_hash": "sha256:" + "1" * 64,
        }
    elif mutation == "official_flag":
        policy["source_time_trust"]["official_historical_pit_verified"] = True

    reasons = qa._source_binding_mismatches(
        policy=policy,
        proposal=proposal,
        config_db_path=source_db,
        expected_candidate_root=candidate_root,
        actual_file_identity=identity,
    )
    assert expected_reason in reasons


class _TableModel:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def getDataFrame(self) -> pd.DataFrame:
        return self._frame


class _ResultsTable:
    def __init__(self, model: _TableModel) -> None:
        self._model = model

    def model(self) -> _TableModel:
        return self._model

    def objectName(self) -> str:
        return "recommendationResultsTable"


def _view(frame: pd.DataFrame) -> SimpleNamespace:
    model = _TableModel(frame)
    return SimpleNamespace(recommendations_model=model, results_table=_ResultsTable(model))


def _verified_projection_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[SimpleNamespace, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    from app_module import personalization_contract
    from ml_module import recommendation_inference_provenance

    candidate_root = tmp_path / "learning" / "candidate"
    candidate_root.mkdir(parents=True)
    monkeypatch.setattr(qa, "CANDIDATE_ROOT", candidate_root)
    source_db = tmp_path / "working.sqlite"
    source_db.write_bytes(b"isolated working database")
    source_info = source_db.stat()
    source_identity = {"device": int(source_info.st_dev), "inode": int(source_info.st_ino)}
    source_path = str(source_db.resolve(strict=True))
    source_slice = qa.EXPECTED_SOURCE_SLICE_SHA256
    cost_hash = "sha256:" + "c" * 64
    cost_id = "fixed-cost-v1"
    inference_source_hash = "sha256:" + "d" * 64
    inference_pit_hash = "sha256:" + "e" * 64
    feature_rows_hash = "sha256:" + "f" * 64
    projection_rows_hash = "sha256:" + "a" * 64
    result_id = "rec-fixture-20260928"
    decision_date = "2026-09-28"
    receipt_hash = "sha256:" + "b" * 64
    confirmed_at = "2026-09-28T12:00:00+00:00"
    fixed_candidate = {
        **qa.CANDIDATE_PINS,
        "candidate_root": str(candidate_root.resolve(strict=True)),
    }
    source_proof = {
        "source_database_path": source_path,
        "source_file_identity": source_identity,
        "source_slice_sha256": source_slice,
        "candidate_pins": fixed_candidate,
    }
    source_trust = {
        "basis": "user_declared_source_time",
        "confirmed_at": confirmed_at,
        "source_database_path": source_path,
        "file_identity": source_identity,
        "source_slice_sha256": source_slice,
        "candidate": fixed_candidate,
        "research_only": True,
        "official_historical_pit_verified": False,
    }
    expected_policy = {
        "schema_version": "recommendation-personal-use-policy.v2",
        "mode": "personal_calibrated_probability",
        "revision": 1,
        "policy_sha256": "sha256:" + "1" * 64,
        "confirmed_at": confirmed_at,
        "candidate": fixed_candidate,
        "source_time_trust": source_trust,
    }
    inference = {
        "status": "verified",
        "decision_date": decision_date,
        "source_database": source_path,
        "source_fingerprint": "sha256:" + "2" * 64,
        "cost_scenario_hash": cost_hash,
        "cost_scenario_id": cost_id,
        "inference_source_hash": inference_source_hash,
        "inference_pit_hash": inference_pit_hash,
        "feature_rows_sha256": feature_rows_hash,
    }
    training = {
        "status": "verified",
        "cost_scenario_hash": cost_hash,
    }
    lineage = {
        "kind": "active_model",
        "candidate_id": qa.CANDIDATE_ID,
        "model_id": qa.CANDIDATE_ID,
        "cost_scenario_hash": cost_hash,
        "baseline_id": "null_benchmark_50pct_v1",
        "baseline_kind": "null_benchmark",
        "transform_id": "recommendation-probability-transform.v2",
    }
    candidate_identity = {
        "candidate_id": qa.CANDIDATE_ID,
        "candidate_root": fixed_candidate["candidate_root"],
        "candidate_manifest_hash": fixed_candidate["candidate_manifest_hash"],
        "candidate_artifact_hash": fixed_candidate["candidate_artifact_hash"],
        "candidate_freeze_hash": fixed_candidate["candidate_freeze_hash"],
        "dataset_hash": fixed_candidate["dataset_hash"],
        "probability_lineage": [lineage],
        "feature_transform_contract": {
            "canonical_schema": [
                {"name": "feature_a", "dtype": "decimal", "scale": 4},
                {"name": "feature_b", "dtype": "decimal", "scale": 2},
            ],
            "float_parameter": 0.5,
        },
    }

    def projection_row(
        symbol: str, *, status: str, probability: int | None, model_version: str | None
    ) -> dict[str, Any]:
        return {
            "stock_code": symbol,
            "status": "active_candidate" if status == "active_effective" else "rule_fallback",
            "calibrated_probability_status": status,
            "calibrated_probability_bp": probability,
            "model_version": model_version,
            "cost_scenario_hash": cost_hash,
            "cost_scenario_id": cost_id,
            "probability_baseline_id": "null_benchmark_50pct_v1",
            "probability_baseline_kind": "null_benchmark",
            "probability_transform_id": "recommendation-probability-transform.v2",
            "provenance_status": "verified",
            "inference_provenance": dict(inference),
            "training_provenance": {
                **training,
                "source_time_basis": source_trust["basis"],
                "source_time_confirmed_at": confirmed_at,
                "source_time_source_database_path": source_path,
                "source_time_slice_sha256": source_slice,
                "source_time_research_only": True,
                "official_historical_pit_verified": False,
            },
        }

    rows = [
        projection_row(
            "2330",
            status="active_effective",
            probability=7312,
            model_version=qa.CANDIDATE_ID,
        ),
        projection_row(
            "2317",
            status="fallback_rule",
            probability=None,
            model_version=None,
        ),
    ]
    payload = {
        "result_id": result_id,
        "decision_date": decision_date,
        "candidate_identity": candidate_identity,
        "cost_scenario_hash": cost_hash,
        "projection_rows_sha256": projection_rows_hash,
        "inference_provenance": inference,
        "training_provenance": training,
        "provenance_compatibility": {"status": "verified"},
        "projections": rows,
    }
    run_root = tmp_path / "run"
    run_root.mkdir()
    receipt_path = (
        run_root
        / "app_config"
        / "inference_projection"
        / decision_date
        / qa.CANDIDATE_ID
        / f"{receipt_hash.split(':', 1)[1]}.json"
    )
    receipt_event = {
        "attempted": True,
        "persisted": True,
        "readback_verified": True,
        "identity_verified": True,
        "receipt_body_hash_verified": True,
        "result_id": result_id,
        "decision_date": decision_date,
        "candidate_id": qa.CANDIDATE_ID,
        "candidate_identity": _normalize_event_value_v1(candidate_identity),
        "receipt_hash": receipt_hash,
        "path": str(receipt_path),
        "cost_scenario_hash": cost_hash,
        "cost_scenario_id": cost_id,
        "projected_stock_codes": ("2330", "2317"),
        "projection_rows_sha256": projection_rows_hash,
        "inference_source_hash": inference_source_hash,
        "inference_pit_hash": inference_pit_hash,
        "feature_rows_sha256": feature_rows_hash,
    }
    execution = SimpleNamespace(
        result_id=result_id,
        status=SimpleNamespace(value="completed"),
        context=SimpleNamespace(
            decision_at=datetime(2026, 9, 28, 12, tzinfo=timezone.utc),
            as_of_date=date(2026, 9, 28),
        ),
        items=(SimpleNamespace(stock_code="2330"), SimpleNamespace(stock_code="2317")),
        events=(SimpleNamespace(event_type="ml_projection_receipt_capture", details=receipt_event),),
    )
    event = {
        "requested_mode": "personal_calibrated_probability",
        "effective_mode": "personal_calibrated_probability",
        "policy_snapshot": expected_policy,
    }
    monkeypatch.setattr(
        personalization_contract,
        "read_personal_use_policy_snapshot_event",
        lambda *_args, **_kwargs: event,
    )
    reader_calls: list[dict[str, Any]] = []
    readback_identity = {"receipt_hash": receipt_hash, "receipt_path": str(receipt_path)}

    def read_receipt(path: Path, **kwargs: Any) -> SimpleNamespace:
        reader_calls.append({"path": Path(path), **kwargs})
        return SimpleNamespace(
            payload=payload,
            receipt_hash=readback_identity["receipt_hash"],
            receipt_path=readback_identity["receipt_path"],
        )

    monkeypatch.setattr(
        recommendation_inference_provenance,
        "read_inference_projection_receipt",
        read_receipt,
    )
    return execution, expected_policy, source_proof, event, {
        "run_root": run_root,
        "payload": payload,
        "receipt_event": receipt_event,
        "reader_calls": reader_calls,
        "readback_identity": readback_identity,
    }


class _Label:
    def __init__(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text


class _Combo:
    def __init__(self, data: Any, text: str) -> None:
        self._data = data
        self._text = text

    def currentData(self) -> Any:
        return self._data

    def currentText(self) -> str:
        return self._text


class _CheckBox:
    def __init__(self, checked: bool) -> None:
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked


def _failed_execution_view(
    *,
    requested_mode: str,
    effective_mode: str,
    policy_snapshot: dict[str, Any],
    items: tuple[Any, ...] = (),
) -> SimpleNamespace:
    decision_at = datetime(2026, 9, 28, 13, 0, tzinfo=timezone.utc)
    config = {
        "data_date": "2026-09-24",
        "filters": {
            "price_change_min": 0.0,
            "price_change_max": None,
            "volume_ratio_min": 1.0,
            "rsi_min": 0,
            "rsi_max": 100,
        },
        "signals": {"ma": {"enabled": False}, "macd": {"enabled": False}},
    }
    execution = SimpleNamespace(
        result_id="rec-result-diagnostic",
        status=SimpleNamespace(value="completed"),
        context=SimpleNamespace(
            decision_at=decision_at,
            as_of_date=date(2026, 9, 24),
            warnings=("sealed invocation warning",),
            universe_identity=SimpleNamespace(
                snapshot=SimpleNamespace(
                    universe_snapshot_spec_json=json.dumps(
                        {
                            "selected_count": 8,
                            "selection_mode": "top_max_stocks",
                        }
                    )
                )
            ),
        ),
        request=SimpleNamespace(
            as_of_date=date(2026, 9, 24),
            profile_ref=SimpleNamespace(reference_id="profile-explicit"),
            config_snapshot=SimpleNamespace(
                raw_config_json=json.dumps(config), raw_json_sha256="sha256:" + "a" * 64
            ),
            max_stocks=8,
            top_n=8,
        ),
        items=items,
    )
    service = SimpleNamespace(
        last_run_context={
            "result_id": "rec-result-diagnostic",
            "decision_at": decision_at.isoformat(),
            "decision_date": "2026-09-28",
            "as_of_date": "2026-09-24",
            "data_date": "2026-09-24",
            "personal_use_requested_mode": requested_mode,
            "personal_use_effective_mode": "stale-base-service-value",
            "calibration_projection_status": "stale-base-service-projection",
            "warnings": ["must not be used as invocation warning"],
            "universe_spec": {"selected_codes": ["9999"], "selection_mode": "stale"},
        }
    )
    view = SimpleNamespace(
        current_execution=execution,
        recommendation_service=service,
        _execution_state="completed",
        execution_status_label=_Label("推薦已完成"),
        result_status_label=_Label("無符合條件的推薦結果"),
        current_profile=None,
        is_beginner_mode=True,
        profile_combo=_Combo(None, "請選擇 Profile..."),
        current_config=SimpleNamespace(**config),
    )
    for name in (
        "ma_check", "adx_check", "macd_check", "rsi_check", "kd_check",
        "bollinger_check", "atr_check", "pattern_w_bottom",
        "pattern_head_shoulder_bottom", "pattern_double_bottom",
        "pattern_v_reversal", "pattern_rounding_bottom", "pattern_flag",
        "pattern_wedge", "pattern_rectangle", "pattern_triangle",
        "pattern_head_shoulder_top", "pattern_double_top", "pattern_rounding_top",
    ):
        setattr(view, name, _CheckBox(False))
    return view


def test_active_execution_diagnostic_separates_mode_clock_and_empty_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module import personalization_contract

    expected = {
        "schema_version": "recommendation-personal-use-policy.v2",
        "mode": "personal_calibrated_probability",
        "revision": 1,
        "policy_sha256": "a" * 64,
        "confirmed_at": "2026-09-28T12:00:00+00:00",
    }
    event = {
        "requested_mode": "personal_calibrated_probability",
        "effective_mode": "rule_only",
        "policy_snapshot": expected,
    }
    monkeypatch.setattr(
        personalization_contract,
        "read_personal_use_policy_snapshot_event",
        lambda *_args, **_kwargs: event,
    )
    view = _failed_execution_view(
        requested_mode="personal_calibrated_probability",
        effective_mode="rule_only",
        policy_snapshot=expected,
    )

    with pytest.raises(qa.AcceptanceError, match="effective_mode") as caught:
        qa._verify_active_execution(view, expected)

    diagnostic = caught.value.diagnostic
    assert diagnostic["event_predicates"] == {
        "requested_mode_matches_personal_calibrated": True,
        "effective_mode_matches_personal_calibrated": False,
        "policy_snapshot_matches_saved_v2": True,
        "policy_snapshot_mismatch_keys": [],
        "actual_requested_mode": "personal_calibrated_probability",
        "actual_effective_mode": "rule_only",
    }
    assert diagnostic["execution"]["delivered_row_count"] == 0
    assert diagnostic["execution"]["projection_status_from_sealed_items"] == "no_delivered_rows"
    assert diagnostic["execution"]["active_candidate_row_count"] == 0
    assert diagnostic["execution"]["fallback_or_rule_row_count"] == 0
    assert diagnostic["execution"]["selected_universe_count"] == 8
    assert diagnostic["execution"]["as_of_date"] == "2026-09-24"
    assert diagnostic["execution"]["request_profile_reference_id"] == "profile-explicit"
    assert diagnostic["policy_clock"]["confirmed_at_not_after_decision_at"] is True
    assert diagnostic["base_service_context_observation"]["evidence_scope"] == (
        "base_service_only_not_invocation_evidence"
    )
    assert diagnostic["base_service_context_observation"]["calibration_projection_status"] == (
        "stale-base-service-projection"
    )
    assert diagnostic["sealed_invocation_warnings"] == ["sealed invocation warning"]
    assert diagnostic["sealed_request_config"]["filters"]["price_change_min"] == 0.0
    assert diagnostic["ui"]["current_profile"] is None
    assert diagnostic["ui"]["profile_combo_current_data"] is None
    assert diagnostic["ui"]["profile_combo_current_text"] == "請選擇 Profile..."
    assert diagnostic["ui"]["selected_signal_widgets_live_ui_only"]["ma_check"] is False
    assert diagnostic["ui"]["current_config_filters_live_ui_only"]["price_change_min"] == 0.0


def test_active_execution_diagnostic_identifies_policy_snapshot_only_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module import personalization_contract

    expected = {
        "schema_version": "recommendation-personal-use-policy.v2",
        "mode": "personal_calibrated_probability",
        "revision": 1,
        "policy_sha256": "a" * 64,
        "confirmed_at": "2026-09-28T12:00:00+00:00",
    }
    event = {
        "requested_mode": "personal_calibrated_probability",
        "effective_mode": "personal_calibrated_probability",
        "policy_snapshot": {**expected, "revision": 2},
    }
    monkeypatch.setattr(
        personalization_contract,
        "read_personal_use_policy_snapshot_event",
        lambda *_args, **_kwargs: event,
    )
    view = _failed_execution_view(
        requested_mode="personal_calibrated_probability",
        effective_mode="personal_calibrated_probability",
        policy_snapshot=expected,
        items=(SimpleNamespace(calibrated_probability_status="fallback_rule"),),
    )

    with pytest.raises(qa.AcceptanceError, match="policy_snapshot") as caught:
        qa._verify_active_execution(view, expected)

    predicates = caught.value.diagnostic["event_predicates"]
    assert predicates["requested_mode_matches_personal_calibrated"] is True
    assert predicates["effective_mode_matches_personal_calibrated"] is True
    assert predicates["policy_snapshot_matches_saved_v2"] is False
    assert predicates["policy_snapshot_mismatch_keys"] == ["revision"]
    assert caught.value.diagnostic["execution"]["delivered_row_count"] == 1
    assert caught.value.diagnostic["execution"]["fallback_or_rule_row_count"] == 1
    assert caught.value.diagnostic["execution"]["projection_status_from_sealed_items"] == (
        "fallback_or_rule_only"
    )
    assert caught.value.diagnostic["execution"]["selected_universe_count"] == 8


def test_sealed_ml_projection_diagnostic_reads_bounded_receipt_event_and_row_counts() -> None:
    error = "RecommendationProvenanceError: " + ("x" * 500)
    execution = SimpleNamespace(
        events=(
            SimpleNamespace(
                event_type="ml_projection_receipt_capture",
                details={
                    "attempted": False,
                    "persisted": False,
                    "readback_verified": False,
                    "identity_verified": False,
                    "error": error,
                    "projected_stock_codes": ("2330", "2317"),
                    "cost_scenario_hash": "",
                },
            ),
        ),
        items=(
            SimpleNamespace(
                calibrated_probability_status="active_effective",
                provenance_compatibility={"status": "verified"},
                cost_scenario_hash="a" * 64,
            ),
            SimpleNamespace(
                calibrated_probability_status="unavailable",
                provenance_compatibility={"status": "blocked"},
                cost_scenario_hash=None,
            ),
        ),
    )

    diagnostic = qa._sealed_ml_projection_diagnostic(execution)

    assert diagnostic["evidence_scope"] == "sealed_execution_events_and_items_only"
    assert diagnostic["receipt_event_count"] == 1
    assert diagnostic["receipt_events"] == [
        {
            "event_type": "ml_projection_receipt_capture",
            "attempted": False,
            "persisted": False,
            "readback_verified": False,
            "identity_verified": False,
            "error": error[:300],
            "projected_stock_code_count": 2,
            "projection_rows_sha256_present": False,
            "cost_scenario_hash_present": False,
        }
    ]
    assert diagnostic["row_status_counts"] == {
        "active_effective": 1,
        "unavailable": 1,
    }
    assert diagnostic["compatibility_status_counts"] == {
        "blocked": 1,
        "verified": 1,
    }
    assert diagnostic["cost_hash_presence_counts"] == {"missing": 1, "present": 1}
    assert diagnostic["distinct_cost_hash_count"] == 1
    assert diagnostic["items_with_projection_metadata"] == 2


def test_sealed_ml_projection_diagnostic_marks_unavailable_row_metadata() -> None:
    diagnostic = qa._sealed_ml_projection_diagnostic(
        SimpleNamespace(
            events=(),
            items=(SimpleNamespace(stock_code="2330"),),
        )
    )

    assert diagnostic["receipt_event_count"] == 0
    assert diagnostic["receipt_events"] == []
    assert diagnostic["row_status_counts"] == {}
    assert diagnostic["compatibility_status_counts"] == {}
    assert diagnostic["cost_hash_presence_counts"] == {"missing": 1, "present": 0}
    assert diagnostic["items_with_projection_metadata"] == 0
    assert diagnostic["row_projection_metadata_available"] is False


@pytest.mark.parametrize(
    ("receipt", "return_code", "expected_reasons"),
    [
        (
            {
                "process_id": 71,
                "status": "FAILED",
                "error": "canonical execution event 驗收失敗：effective_mode",
            },
            2,
            [
                "phase_receipt_pid_mismatch",
                "phase_receipt_not_pass",
                "child_return_code_nonzero",
            ],
        ),
        (
            {"process_id": 71, "status": "PASS", "error": ""},
            0,
            ["phase_receipt_pid_mismatch"],
        ),
    ],
)
def test_phase_receipt_diagnostic_preserves_child_error_and_pid_guard(
    receipt: dict[str, Any],
    return_code: int,
    expected_reasons: list[str],
) -> None:
    rejection = qa._phase_receipt_rejection(
        receipt,
        phase="activate",
        expected_pid=72,
        return_code=return_code,
    )

    assert rejection is not None
    assert rejection["rejection_reasons"] == expected_reasons
    if receipt["status"] == "FAILED":
        assert "canonical execution event" in str(rejection["child_error"])


def test_phase_receipt_acceptance_still_requires_exact_child_pid() -> None:
    assert qa._phase_receipt_rejection(
        {"process_id": 72, "status": "PASS", "error": ""},
        phase="activate",
        expected_pid=72,
        return_code=0,
    ) is None


def test_phase_receipt_accepts_verified_venv_redirector_child_identity() -> None:
    assert qa._phase_receipt_rejection(
        {
            "process_id": 730,
            "parent_process_id": 72,
            "runtime_executable": r"C:\project\.venv\Scripts\python.exe",
            "status": "PASS",
            "error": "",
        },
        phase="activate",
        expected_pid=72,
        return_code=0,
        venv_redirector_verified=True,
        expected_executable=r"C:\project\.venv\Scripts\python.exe",
    ) is None


@pytest.mark.parametrize(
    ("receipt", "verified", "expected_executable"),
    [
        (
            {
                "process_id": 730,
                "parent_process_id": 73,
                "runtime_executable": r"C:\project\.venv\Scripts\python.exe",
                "status": "PASS",
                "error": "",
            },
            True,
            r"C:\project\.venv\Scripts\python.exe",
        ),
        (
            {
                "process_id": 730,
                "parent_process_id": 72,
                "runtime_executable": r"C:\project\.venv\Scripts\python.exe",
                "status": "PASS",
                "error": "",
            },
            False,
            r"C:\project\.venv\Scripts\python.exe",
        ),
        (
            {
                "process_id": 730,
                "parent_process_id": 72,
                "runtime_executable": r"C:\other\.venv\Scripts\python.exe",
                "status": "PASS",
                "error": "",
            },
            True,
            r"C:\project\.venv\Scripts\python.exe",
        ),
    ],
)
def test_phase_receipt_rejects_unverified_redirector_parent_or_executable(
    receipt: dict[str, Any], verified: bool, expected_executable: str
) -> None:
    rejection = qa._phase_receipt_rejection(
        receipt,
        phase="activate",
        expected_pid=72,
        return_code=0,
        venv_redirector_verified=verified,
        expected_executable=expected_executable,
    )
    assert rejection is not None
    assert "phase_receipt_pid_mismatch" in rejection["rejection_reasons"]


def test_windows_venv_redirector_detection_requires_scripts_and_pyvenv_cfg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(qa.os, "name", "nt")
    scripts_dir = tmp_path / ".venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    executable = scripts_dir / "python.exe"
    executable.write_bytes(b"test executable placeholder")
    (scripts_dir.parent / "pyvenv.cfg").write_text("home = python\n", encoding="utf-8")
    assert qa._is_windows_venv_redirector(executable) is True
    assert qa._is_windows_venv_redirector(tmp_path / "python.exe") is False


def test_active_execution_reads_run_local_bounded_projection_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, policy, source_proof, _event, fixture = _verified_projection_fixture(
        tmp_path, monkeypatch
    )
    verified = qa._verify_active_execution(
        SimpleNamespace(current_execution=execution),
        policy,
        run_root=fixture["run_root"],
        expected_source_proof=source_proof,
    )

    assert verified["result_id"] == execution.result_id
    assert verified["delivered_row_count"] == 2
    assert verified["projection_receipt"]["delivered_symbols"] == ["2317", "2330"]
    assert verified["active_probability_rows"] == [
        {
            "symbol": "2330",
            "probability_bp": 7312,
            "model_version": qa.CANDIDATE_ID,
            "baseline_id": "null_benchmark_50pct_v1",
            "baseline_kind": "null_benchmark",
            "cost_scenario_hash": "sha256:" + "c" * 64,
        }
    ]
    assert fixture["reader_calls"] == [
        {
            "path": Path(fixture["receipt_event"]["path"]),
            "expected_receipt_hash": fixture["receipt_event"]["receipt_hash"],
            "expected_decision_date": "2026-09-28",
            "expected_candidate_id": qa.CANDIDATE_ID,
            "expected_result_id": execution.result_id,
            "expected_cost_scenario_hash": "sha256:" + "c" * 64,
            "max_receipt_bytes": qa.MAX_PROJECTION_RECEIPT_BYTES,
        }
    ]


def test_candidate_identity_canonicalization_preserves_strict_scalar_types() -> None:
    from decimal import Decimal

    receipt_identity = {
        "probability_lineage": [{"model_id": qa.CANDIDATE_ID}],
        "feature_transform_contract": {
            "canonical_schema": [{"name": "feature_a", "scale": 4}],
            "ratio": 0.5,
        },
        "enabled": True,
        "sample_count": 512,
    }
    event_identity = _normalize_event_value_v1(receipt_identity)

    assert qa._canonical_identity_value(receipt_identity) == qa._canonical_identity_value(
        event_identity
    )
    assert qa._canonical_identity_value(True) != qa._canonical_identity_value(1)
    assert qa._canonical_identity_value(1) != qa._canonical_identity_value(Decimal("1"))
    assert qa._canonical_identity_value(0.5) == qa._canonical_identity_value(
        Decimal("0.5")
    )


def test_deferred_clicks_allow_timer_to_handle_real_nested_save_and_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    driver = object.__new__(qa._PersonalModelJourneyDriver)
    driver.app = app
    driver.window = SimpleNamespace(close=lambda: None)
    driver.phase = "activate"
    driver.run_id = "qt-modal-test"
    driver.stage = "start_save"
    driver.started = time.monotonic()
    driver.step_started = driver.started
    driver.status = "RUNNING"
    driver.exit_code = 0
    driver.actions = []
    driver._failure_details = {}
    driver._deferred_click_pending = False
    driver._save_name = "isolated result"

    save_dialog = QInputDialog()
    save_dialog.setWindowTitle("保存推薦結果")
    save_dialog.setLabelText("隔離結果名稱")
    save_dialog.setInputMode(QInputDialog.InputMode.TextInput)
    save_dialog.setTextValue("isolated result")
    success_dialog = QMessageBox()
    success_dialog.setText("canonical readback 驗證完成")
    success_dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
    rollback_dialog = QMessageBox()
    rollback_dialog.setText("確認回退")
    rollback_dialog.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    state: dict[str, Any] = {
        "input_ticks": 0,
        "success_ticks": 0,
        "rollback_ticks": 0,
        "outer_save_clicked": False,
        "input_accepted": False,
        "success_acknowledged": False,
        "rollback_clicked": False,
        "rollback_accepted": False,
        "errors": [],
    }

    class SaveButton:
        def isEnabled(self) -> bool:
            return True

        def isVisible(self) -> bool:
            return True

        def click(self) -> None:
            state["outer_save_clicked"] = True
            state["input_accepted"] = (
                save_dialog.exec() == QDialog.DialogCode.Accepted
            )
            if state["input_accepted"]:
                    success_dialog.exec()
                    state["success_acknowledged"] = (
                        success_dialog.clickedButton()
                        is success_dialog.button(QMessageBox.StandardButton.Ok)
                    )
            driver.stage = "rollback_ready"

    class RollbackButton:
        def isEnabled(self) -> bool:
            return True

        def isVisible(self) -> bool:
            return True

        def click(self) -> None:
                state["rollback_clicked"] = True
                rollback_dialog.exec()
                state["rollback_accepted"] = (
                    rollback_dialog.clickedButton()
                    is rollback_dialog.button(QMessageBox.StandardButton.Yes)
                )

    save_button = SaveButton()
    rollback_button = RollbackButton()
    timer = QTimer()
    timer.setInterval(10)
    watchdog_timer = QTimer()
    watchdog_timer.setSingleShot(True)

    def tick() -> None:
        try:
            modal = app.activeModalWidget()
            if driver.stage == "start_save":
                driver._click_in_stage(
                    "waiting_save_dialog",
                    save_button,
                    "排程點擊真 canonical 保存按鈕",
                    expected_modal=None,
                )
            elif isinstance(modal, QInputDialog) and driver.stage == "waiting_save_dialog":
                state["input_ticks"] += 1
                assert driver._dismiss_modal() is True
            elif (
                isinstance(modal, QMessageBox)
                and driver.stage == "waiting_save"
                and "canonical readback 驗證" in modal.text()
            ):
                state["success_ticks"] += 1
                assert driver._dismiss_modal() is True
            elif driver.stage == "rollback_ready":
                driver._click_in_stage(
                    "waiting_rollback_confirmation",
                    rollback_button,
                    "排程點擊真 V2 rollback 按鈕",
                    expected_modal=None,
                )
            elif (
                isinstance(modal, QMessageBox)
                and driver.stage == "waiting_rollback_confirmation"
            ):
                state["rollback_ticks"] += 1
                assert driver._dismiss_modal() is True
            elif state["rollback_accepted"] and driver.stage == "waiting_rollback_save":
                timer.stop()
                app.quit()
        except Exception as exc:  # surfaced below instead of escaping a Qt slot
            state["errors"].append(f"{type(exc).__name__}: {exc}")
            modal = app.activeModalWidget()
            if modal is not None:
                modal.reject()
            timer.stop()
            app.quit()

    def watchdog() -> None:
        state["watchdog_fired"] = True
        modal = app.activeModalWidget()
        if modal is not None:
            modal.reject()
        app.quit()

    timer.timeout.connect(tick)
    watchdog_timer.timeout.connect(watchdog)
    timer.start()
    watchdog_timer.start(4000)
    app.exec()
    timer.stop()
    watchdog_timer.stop()
    for dialog in (save_dialog, success_dialog, rollback_dialog):
        dialog.close()

    assert state["errors"] == []
    assert state.get("watchdog_fired") is not True, (
        f"state={state}; driver_stage={driver.stage}; actions={driver.actions}"
    )
    assert state["outer_save_clicked"] is True
    assert state["input_accepted"] is True
    assert state["success_acknowledged"] is True
    assert state["rollback_clicked"] is True
    assert state["rollback_accepted"] is True
    assert state["input_ticks"] > 0
    assert state["success_ticks"] > 0
    assert state["rollback_ticks"] > 0
    assert driver.stage == "waiting_rollback_save"
    assert driver._deferred_click_pending is False


def test_rollback_confirmation_sets_waiting_save_before_yes_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PySide6 import QtCore, QtWidgets

    monkeypatch.setattr(QtCore.QTimer, "singleShot", staticmethod(lambda _ms, callback: callback()))

    clicks: list[str] = []
    driver = object.__new__(qa._PersonalModelJourneyDriver)
    driver.stage = "waiting_history"
    driver.step_started = 0.0
    driver.started = time.monotonic()
    driver.status = "RUNNING"
    driver.exit_code = 0
    driver.actions = []
    driver._failure_details = {}
    driver._deferred_click_pending = False

    class FakeButton:
        def isEnabled(self) -> bool:
            return True

        def isVisible(self) -> bool:
            return True

        def click(self) -> None:
            assert driver.stage == "waiting_rollback_save"
            clicks.append(driver.stage)

    button = FakeButton()

    class FakeInputDialog:
        pass

    class FakeDialogButtonBox:
        class StandardButton:
            Ok = object()

    class FakeMessageBox:
        class StandardButton:
            Ok = object()
            Yes = object()

        def text(self) -> str:
            return "確認回退"

        def button(self, _kind: Any) -> FakeButton:
            return button

    monkeypatch.setattr(QtWidgets, "QDialogButtonBox", FakeDialogButtonBox)
    monkeypatch.setattr(QtWidgets, "QInputDialog", FakeInputDialog)
    monkeypatch.setattr(QtWidgets, "QMessageBox", FakeMessageBox)
    modal: Any = None
    driver.app = SimpleNamespace(activeModalWidget=lambda: modal)

    class RollbackClick:
        def isEnabled(self) -> bool:
            return True

        def isVisible(self) -> bool:
            return True

        def click(self) -> None:
            nonlocal modal
            assert driver.stage == "waiting_rollback_confirmation"
            modal = FakeMessageBox()
            assert driver._dismiss_modal() is True

    driver._click_in_stage(
        "waiting_rollback_confirmation",
        RollbackClick(),
        "點擊 V2 rollback 操作",
        expected_modal=None,
    )

    assert clicks == ["waiting_rollback_save"]
    assert driver.stage == "waiting_rollback_save"


def _rollback_candidate_selection_driver(
    source_db: Path,
    candidate_root: Path,
    *,
    selected_candidate_root: Any | None = None,
    selected_source_path: str | None = None,
    source_check_enabled: bool = True,
) -> tuple[Any, Any, list[str]]:
    clicks: list[str] = []

    class Combo:
        def currentData(self) -> Any:
            return (
                str(candidate_root.resolve(strict=True))
                if selected_candidate_root is None
                else selected_candidate_root
            )

    class Input:
        def text(self) -> str:
            return (
                str(source_db.resolve(strict=True))
                if selected_source_path is None
                else selected_source_path
            )

    class CheckButton:
        def isEnabled(self) -> bool:
            return source_check_enabled

        def click(self) -> None:
            clicks.append("source_time_check")

    view = SimpleNamespace(
        _personal_candidate_worker=None,
        # rule_only 保存後這個 entry 合法地已清除；rollback 要以 UI 選項重做 fresh proof。
        _personal_candidate_entry=None,
        personal_candidate_combo=Combo(),
        personal_source_database_input=Input(),
        personal_source_time_check_button=CheckButton(),
    )
    driver = object.__new__(qa._PersonalModelJourneyDriver)
    driver.layout = qa.isolated_launcher.RuntimeLayout(
        run_root=source_db.parent,
        data_root_base=source_db.parent,
        output_root_base=source_db.parent,
        data_root_actual=source_db.parent,
        output_root_actual=source_db.parent,
        working_db_path=source_db,
        policy_config_path=source_db.parent / "policy.json",
        receipts_dir=source_db.parent / "receipts",
    )
    driver.stage = "waiting_rollback_candidate_selection"
    driver.step_started = 0.0
    driver.actions = []
    return driver, view, clicks


def test_rollback_candidate_selection_uses_current_ui_inputs_without_stale_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _policy, _proposal, source_db, candidate_root, _identity = _binding_fixture(tmp_path)
    monkeypatch.setattr(qa, "CANDIDATE_ROOT", candidate_root)
    driver, view, clicks = _rollback_candidate_selection_driver(source_db, candidate_root)

    driver._rollback_disable_tick(view)

    assert clicks == ["source_time_check"]
    assert driver.stage == "waiting_rollback_proposal"
    assert driver.actions[0]["action"] == "為 V2 rollback 取得新鮮來源提案"


@pytest.mark.parametrize("mutation", ["candidate", "source", "disabled"])
def test_rollback_candidate_selection_rejects_wrong_ui_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    _policy, _proposal, source_db, candidate_root, _identity = _binding_fixture(tmp_path)
    monkeypatch.setattr(qa, "CANDIDATE_ROOT", candidate_root)
    selected_candidate: Any | None = None
    selected_source: str | None = None
    check_enabled = True
    if mutation == "candidate":
        other_candidate = tmp_path / "learning" / "other-candidate"
        other_candidate.mkdir()
        selected_candidate = str(other_candidate.resolve(strict=True))
    elif mutation == "source":
        other_db = tmp_path / "other.sqlite"
        other_db.write_bytes(b"different isolated source")
        selected_source = str(other_db.resolve(strict=True))
    else:
        check_enabled = False
    driver, view, clicks = _rollback_candidate_selection_driver(
        source_db,
        candidate_root,
        selected_candidate_root=selected_candidate,
        selected_source_path=selected_source,
        source_check_enabled=check_enabled,
    )

    with pytest.raises(qa.AcceptanceError, match="V2 rollback UI candidate/source 選取不符"):
        driver._rollback_disable_tick(view)

    assert clicks == []
    assert driver.stage == "waiting_rollback_candidate_selection"


@pytest.mark.parametrize("mutation", ["stage", "modal"])
def test_deferred_click_fails_closed_if_stage_or_modal_changes(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    from PySide6 import QtCore

    queued: list[Any] = []
    monkeypatch.setattr(
        QtCore.QTimer,
        "singleShot",
        staticmethod(lambda _delay, callback: queued.append(callback)),
    )
    clicked = False
    modal_rejected = False

    class Button:
        def isEnabled(self) -> bool:
            return True

        def isVisible(self) -> bool:
            return True

        def click(self) -> None:
            nonlocal clicked
            clicked = True

    class UnexpectedModal:
        def windowTitle(self) -> str:
            return "Unexpected modal"

        def reject(self) -> None:
            nonlocal modal_rejected
            modal_rejected = True

    modal: Any = None
    driver = object.__new__(qa._PersonalModelJourneyDriver)
    driver.app = SimpleNamespace(activeModalWidget=lambda: modal)
    driver.window = SimpleNamespace(close=lambda: None)
    driver.stage = "before_save"
    driver.started = time.monotonic()
    driver.step_started = driver.started
    driver.status = "RUNNING"
    driver.exit_code = 0
    driver.actions = []
    driver._failure_details = {}
    driver._deferred_click_pending = False

    driver._click_in_stage(
        "waiting_save_dialog", Button(), "deferred test click", expected_modal=None
    )
    assert len(queued) == 1
    assert driver.stage == "waiting_save_dialog"
    assert driver._deferred_click_pending is True
    if mutation == "stage":
        driver.stage = "waiting_capture"
    else:
        modal = UnexpectedModal()

    queued.pop()()

    assert clicked is False
    assert driver.status == "FAILED"
    assert driver.stage == "closing"
    assert driver._deferred_click_pending is False
    assert modal_rejected is (mutation == "modal")


def test_unexpected_modal_is_rejected_when_journey_fails_closed() -> None:
    rejected = False
    closed = False

    class UnexpectedModal:
        def text(self) -> str:
            return "unexpected"

        def windowTitle(self) -> str:
            return "Unexpected dialog"

        def reject(self) -> None:
            nonlocal rejected
            rejected = True

    modal = UnexpectedModal()
    driver = object.__new__(qa._PersonalModelJourneyDriver)
    driver.stage = "waiting_preview"
    driver.step_started = 0.0
    driver.actions = []
    driver._failure_details = {}
    driver.app = SimpleNamespace(activeModalWidget=lambda: modal)

    class Window:
        def close(self) -> None:
            nonlocal closed
            closed = True

    driver.window = Window()

    with pytest.raises(qa.AcceptanceError):
        driver._dismiss_modal()
    driver._finish("FAILED", "unexpected modal")

    assert rejected is True
    assert closed is True
    assert driver._failure_details["modal_rejected_on_fail_closed_stop"][
        "window_title"
    ] == "Unexpected dialog"


@pytest.mark.parametrize(
    "mutation",
    [
        "receipt_outside_run",
        "readback_hash",
        "readback_path",
        "delivered_codes",
        "source_slice",
        "cost_hash",
        "wrong_model_version",
        "no_active",
        "bad_bp",
        "event_identity_value",
        "event_identity_key",
        "event_identity_order",
    ],
)
def test_active_execution_rejects_projection_receipt_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    execution, policy, source_proof, _event, fixture = _verified_projection_fixture(
        tmp_path, monkeypatch
    )
    event = fixture["receipt_event"]
    rows = fixture["payload"]["projections"]
    if mutation == "receipt_outside_run":
        event["path"] = str(tmp_path / "outside" / Path(event["path"]).name)
    elif mutation == "readback_hash":
        fixture["readback_identity"]["receipt_hash"] = "sha256:" + "7" * 64
    elif mutation == "readback_path":
        fixture["readback_identity"]["receipt_path"] = str(
            tmp_path / "outside" / Path(event["path"]).name
        )
    elif mutation == "delivered_codes":
        execution.items = (SimpleNamespace(stock_code="2330"),)
    elif mutation == "source_slice":
        rows[0]["training_provenance"]["source_time_slice_sha256"] = (
            "sha256:" + "9" * 64
        )
    elif mutation == "cost_hash":
        rows[0]["cost_scenario_hash"] = "sha256:" + "8" * 64
    elif mutation == "wrong_model_version":
        rows[0]["model_version"] = "rec-cal-forged"
    elif mutation == "no_active":
        for row in rows:
            row["calibrated_probability_status"] = "unavailable"
    elif mutation == "bad_bp":
        rows[0]["calibrated_probability_bp"] = 10_001
    elif mutation == "event_identity_value":
        event["candidate_identity"]["feature_transform_contract"][
            "canonical_schema"
        ][0]["scale"] = 99
    elif mutation == "event_identity_key":
        del event["candidate_identity"]["feature_transform_contract"][
            "canonical_schema"
        ][0]["name"]
    elif mutation == "event_identity_order":
        event["candidate_identity"]["feature_transform_contract"][
            "canonical_schema"
        ] = tuple(
            reversed(
                event["candidate_identity"]["feature_transform_contract"][
                    "canonical_schema"
                ]
            )
        )

    with pytest.raises(qa.AcceptanceError):
        qa._verify_active_execution(
            SimpleNamespace(current_execution=execution),
            policy,
            run_root=fixture["run_root"],
            expected_source_proof=source_proof,
        )


def test_qt_projection_must_be_absent_before_save_and_match_receipt_after_readback() -> None:
    pre_save = _view(
        pd.DataFrame(
            [
                {
                    "證券代號": "2330",
                    "calibrated_probability_status": "unavailable",
                    "calibrated_probability_bp": None,
                    "calibration_model_version": "",
                }
            ]
        )
    )
    before = qa._assert_model_not_preprojected(pre_save)
    assert before["candidate_visible_before_save"] is False

    after_save = _view(
        pd.DataFrame(
            [
                {
                    "證券代號": "2330",
                    "calibrated_probability_status": "active_effective",
                    "calibrated_probability_bp": 7312,
                    "calibration_model_version": qa.CANDIDATE_ID,
                    "calibration_probability_baseline_id": "fixed_50_percent",
                    "calibration_probability_baseline_kind": "fixed_probability_reference",
                }
            ]
        )
    )
    saved_execution = SimpleNamespace(result_id="rec-visible")
    verified_projection = {
        "result_id": "rec-visible",
        "active_probability_rows": [
            {
                "symbol": "2330",
                "probability_bp": 7312,
                "model_version": qa.CANDIDATE_ID,
                "baseline_id": "fixed_50_percent",
                "baseline_kind": "fixed_probability_reference",
            }
        ],
    }
    result = qa._visible_probability_projection(
        after_save, saved_execution, verified_projection
    )
    assert result["active_rows"] == [
        {
            "symbol": "2330",
            "calibrated_probability_bp": 7312,
            "calibration_model_version": qa.CANDIDATE_ID,
            "calibration_probability_baseline_id": "fixed_50_percent",
            "calibration_probability_baseline_kind": "fixed_probability_reference",
        }
    ]


def test_qt_projection_rejects_mismatch_and_duplicate_active_rows() -> None:
    execution = SimpleNamespace(result_id="rec-visible")
    verified_projection = {
        "result_id": "rec-visible",
        "active_probability_rows": [
            {
                "symbol": "2330",
                "probability_bp": 7312,
                "model_version": qa.CANDIDATE_ID,
                "baseline_id": "fixed_50_percent",
                "baseline_kind": "fixed_probability_reference",
            }
        ],
    }
    mismatch = _view(
        pd.DataFrame(
            [
                {
                    "證券代號": "2330",
                    "calibrated_probability_bp": 7311,
                    "calibrated_probability_status": "active_effective",
                    "calibration_model_version": qa.CANDIDATE_ID,
                    "calibration_probability_baseline_id": "fixed_50_percent",
                    "calibration_probability_baseline_kind": "fixed_probability_reference",
                }
            ]
        )
    )
    with pytest.raises(qa.AcceptanceError, match="sealed execution 不符"):
        qa._visible_probability_projection(mismatch, execution, verified_projection)

    extra_active = _view(
        pd.DataFrame(
            [
                {
                    "證券代號": "2330",
                    "calibrated_probability_bp": 7312,
                    "calibrated_probability_status": "active_effective",
                    "calibration_model_version": qa.CANDIDATE_ID,
                    "calibration_probability_baseline_id": "fixed_50_percent",
                    "calibration_probability_baseline_kind": "fixed_probability_reference",
                },
                {
                    "證券代號": "2317",
                    "calibrated_probability_bp": 6000,
                    "calibrated_probability_status": "active_effective",
                    "calibration_model_version": qa.CANDIDATE_ID,
                    "calibration_probability_baseline_id": "fixed_50_percent",
                    "calibration_probability_baseline_kind": "fixed_probability_reference",
                },
            ]
        )
    )
    with pytest.raises(qa.AcceptanceError, match="active model 股票集合"):
        qa._visible_probability_projection(extra_active, execution, verified_projection)


def _rollback_fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], Any]:
    policy, _proposal, _db, _candidate_root, _identity = _binding_fixture(tmp_path)
    target_revision = 4
    target_hash = "a" * 64
    target_candidate = dict(policy["candidate"])
    target_trust = dict(policy["source_time_trust"])
    new_confirmed_at = "2026-09-28T13:00:00+00:00"
    rolled_policy = {
        **policy,
        "revision": 5,
        "policy_sha256": "b" * 64,
        "confirmed_at": new_confirmed_at,
        "rollback_of_revision": target_revision,
        "rollback_of_policy_sha256": target_hash,
        "source_time_trust": {
            **target_trust,
            "confirmed_at": new_confirmed_at,
        },
    }
    target = SimpleNamespace(
        revision=target_revision,
        policy_sha256=target_hash,
        candidate=SimpleNamespace(to_dict=lambda: dict(target_candidate)),
        source_time_trust=SimpleNamespace(to_dict=lambda: dict(target_trust)),
    )
    return rolled_policy, {
        "revision": target_revision,
        "policy_sha256": target_hash,
        "candidate": target_candidate,
        "source_time_trust": target_trust,
    }, target


def test_rollback_policy_readback_must_match_selected_history_target(tmp_path: Path) -> None:
    policy, target, selected = _rollback_fixture(tmp_path)
    assert qa._rollback_policy_mismatches(
        policy,
        target_revision=target["revision"],
        target_policy_sha256=target["policy_sha256"],
        target_candidate=target["candidate"],
        target_source_time_trust=target["source_time_trust"],
    ) == []
    assert qa._rollback_history_target_mismatches(
        selected,
        target_revision=target["revision"],
        target_policy_sha256=target["policy_sha256"],
        target_candidate=target["candidate"],
        target_source_time_trust=target["source_time_trust"],
    ) == []


@pytest.mark.parametrize("field", ["revision", "policy_sha256"])
def test_rollback_rejects_changed_history_selection(
    tmp_path: Path, field: str
) -> None:
    _policy, target, selected = _rollback_fixture(tmp_path)
    if field == "revision":
        selected.revision += 1
    else:
        selected.policy_sha256 = "d" * 64
    mismatches = qa._rollback_history_target_mismatches(
        selected,
        target_revision=target["revision"],
        target_policy_sha256=target["policy_sha256"],
        target_candidate=target["candidate"],
        target_source_time_trust=target["source_time_trust"],
    )
    assert mismatches


@pytest.mark.parametrize(
    ("field", "expected_reason"),
    [
        ("rollback_of_revision", "rollback_target_revision_mismatch"),
        ("rollback_of_policy_sha256", "rollback_target_policy_hash_mismatch"),
        ("candidate", "rollback_candidate_pins_mismatch"),
        ("source_time_trust", "rollback_source_time_trust_mismatch"),
    ],
)
def test_rollback_readback_rejects_wrong_target_revision_hash_or_pins(
    tmp_path: Path, field: str, expected_reason: str
) -> None:
    policy, target, _selected = _rollback_fixture(tmp_path)
    if field == "rollback_of_revision":
        policy[field] = 3
    elif field == "rollback_of_policy_sha256":
        policy[field] = "c" * 64
    elif field == "candidate":
        policy[field] = {**policy[field], "candidate_artifact_hash": "sha256:" + "1" * 64}
    else:
        policy[field] = {**policy[field], "source_slice_sha256": "sha256:" + "1" * 64}
    mismatches = qa._rollback_policy_mismatches(
        policy,
        target_revision=target["revision"],
        target_policy_sha256=target["policy_sha256"],
        target_candidate=target["candidate"],
        target_source_time_trust=target["source_time_trust"],
    )
    assert expected_reason in mismatches


def test_capture_wait_fails_on_this_result_worker_error_or_cancel() -> None:
    result_id = "rec-result-123"
    message = f"結果 {result_id} 已保存；個人模型擷取未完成。worker cancelled。推薦結果不受影響，可重試擷取。"
    assert qa._capture_failure_message(message, result_id) == "worker cancelled。"
    assert qa._capture_failure_message(message, "different-result") is None
    assert qa._capture_failure_message("擷取仍在執行中", result_id) is None


def test_wait_stages_have_bounded_timeout_and_capture_is_short() -> None:
    assert qa.STAGE_TIMEOUT_SECONDS["waiting_capture"] == 300
    assert qa.STAGE_TIMEOUT_SECONDS["waiting_preview"] == 600
    assert qa.STAGE_TIMEOUT_SECONDS["waiting_execution"] > qa.STAGE_TIMEOUT_SECONDS["waiting_capture"]


def test_learning_root_pin_must_remain_exact() -> None:
    pin = {"tree_pin": {"tree_sha256": "a" * 64, "entry_count": 8}}
    qa._require_same_learning_tree_pin(pin, dict(pin))
    with pytest.raises(qa.AcceptanceError, match="learning root 在 UI 旅程期間改變"):
        qa._require_same_learning_tree_pin(
            pin, {"tree_pin": {"tree_sha256": "b" * 64, "entry_count": 8}}
        )


def test_accept_command_requires_explicit_qt_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_run(_run_id: str) -> dict[str, Any]:
        raise AssertionError("Qt widget run must not start without explicit confirmation")

    monkeypatch.setattr(qa, "run_acceptance", unexpected_run)
    assert qa.main(["accept", "--run-id", "safe-run"]) == 2

    assert "不宣稱 OS 桌面或前景視窗證據" in qa._build_parser().description
    parsed = qa._build_parser().parse_args(
        ["accept", "--run-id", "safe-run", "--confirm-qt-model-run"]
    )
    assert parsed.confirm_qt_model_run is True


def test_run_id_rejects_path_escape_before_filesystem_use() -> None:
    with pytest.raises(qa.AcceptanceError, match="run_id"):
        qa._run_root("../outside")


def test_timeout_only_terminates_runner_owned_child() -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
    )
    try:
        return_code, evidence = qa._wait_for_owned_child(
            child, timeout_seconds=0.05
        )
        assert return_code is not None
        assert evidence is not None
        assert evidence["status"] == "TIMEOUT"
        assert evidence["child_pid"] == child.pid
        assert evidence["manual_attention_required"] is False
        assert evidence["termination_action"] in {
            "verified_tree_descendants_then_root_terminated",
            "verified_tree_exited_after_descendant_termination",
        }
        assert evidence["signals_sent"]
        assert all(
            action["pid"] in {entry["pid"] for entry in evidence["owned_processes_observed"]}
            for action in evidence["signals_sent"]
        )
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_timeout_terminates_verified_owned_descendant_tree(tmp_path: Path) -> None:
    psutil = pytest.importorskip("psutil")
    started_path = tmp_path / "descendant_started.txt"
    script = (
        "import pathlib,subprocess,sys,time;"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']);"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid),encoding='ascii');"
        "time.sleep(30)"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(started_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
    )
    try:
        deadline = time.monotonic() + 5
        while not started_path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert started_path.exists(), "spawned child did not report its owned descendant"
        descendant_pid = int(started_path.read_text(encoding="ascii"))
        return_code, evidence = qa._wait_for_owned_child(child, timeout_seconds=0.05)
        assert return_code is not None
        assert evidence is not None
        assert evidence["manual_attention_required"] is False
        assert evidence["termination_action"] in {
            "verified_tree_descendants_then_root_terminated",
            "verified_tree_exited_after_descendant_termination",
        }
        observed_pids = {entry["pid"] for entry in evidence["owned_processes_observed"]}
        assert descendant_pid in observed_pids
        assert any(action["pid"] != child.pid for action in evidence["signals_sent"])
        with pytest.raises(psutil.NoSuchProcess):
            psutil.Process(descendant_pid).status()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_timeout_does_not_signal_when_process_identity_is_unavailable() -> None:
    class _UnverifiedChild:
        pid = 2_147_483_647
        signalled = False

        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired(cmd="unverified", timeout=timeout or 0)

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.signalled = True

        def kill(self) -> None:
            self.signalled = True

    child = _UnverifiedChild()
    return_code, evidence = qa._wait_for_owned_child(child, timeout_seconds=0.01)  # type: ignore[arg-type]
    assert return_code is None
    assert evidence is not None
    assert evidence["manual_attention_required"] is True
    assert evidence["signals_sent"] == []
    assert child.signalled is False
