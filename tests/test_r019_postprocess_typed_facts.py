"""R019 typed postprocess facts must own cohort, identity, and cutoff data."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app_module.dtos import RecommendationDTO
from app_module.recommendation.body_result import (
    CandidateRowFacts,
    InvocationLegacyContextOwner,
    LegacyRecommendationSnapshot,
    RecommendationBodyContextFacts,
    RecommendationBodyResult,
    snapshot_cohort_from_body_result,
    snapshot_cohort_payload_from_body_result,
    strategy_identity_from_payload,
    universe_identity_from_payload,
)
from app_module.recommendation.contracts import (
    RecommendationConfigSnapshot,
    RecommendationRunEvidenceIdentity,
    Request,
)
from app_module.recommendation.execute import (
    RecommendationInvocationContext,
    RecommendationPostprocessFacts,
    RecommendationPostprocessInput,
    _validate_postprocess_facts,
    execute_recommendation,
)
from app_module.v4_evidence_identity import (
    DEFAULT_RETURN_BASIS,
    build_recommendation_universe_identity,
    build_strategy_config_identity,
)
from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    RecommendationItem,
)
from decision_module.recommendation.evaluate import CandidateDecisionDisposition
from scripts.scheduled.run_scheduled_recommendation_snapshot import (
    _build_scheduled_postprocess_callback,
    _build_snapshot_cohort,
)
from scripts.scheduled.scheduled_clock import SCHEDULE_TIMEZONE


AS_OF = date(2026, 9, 21)
CREATED_AT = datetime(2026, 9, 22, 9, 4, tzinfo=timezone.utc)
RUN_STARTED_AT = datetime(2026, 9, 22, 9, 4, 10, tzinfo=timezone.utc)
AVAILABLE_AT = datetime(2026, 9, 22, 9, 4, 30, tzinfo=timezone.utc)
DECISION_AT = datetime(2026, 9, 22, 9, 5, 6, tzinfo=timezone.utc)
CUTOFF_SELECTION = "latest_available_at_or_before_decision"
CUTOFF_POLICY = "source_available_at_le_decision_at"


@pytest.fixture(autouse=True)
def _isolated_temp_test_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "output"))


def _json_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _candidate_specs(*, empty: bool = False) -> tuple[dict[str, Any], ...]:
    if empty:
        return ()
    return (
        {
            "code": "SEL",
            "name": "Selected Co",
            "status": "pass",
            "quality": "observed",
            "stage": "final_selection",
            "reasons": ("recommendation_selected",),
            "warnings": (),
            "eligible": True,
            "scored": True,
            "selected": True,
        },
        {
            "code": "TOPN",
            "name": "Top N Excluded Co",
            "status": "fail",
            "quality": "observed",
            "stage": "top_n_gate",
            "reasons": ("recommendation_outside_top_n",),
            "warnings": ("ranking_limit_applied",),
            "eligible": True,
            "scored": True,
            "selected": False,
        },
        {
            "code": "MISS",
            "name": "Missing Co",
            "status": "skipped",
            "quality": "missing",
            "stage": "source_fact_gate",
            "reasons": ("monthly_revenue_missing",),
            "warnings": ("source_missing",),
            "eligible": False,
            "scored": False,
            "selected": False,
        },
        {
            "code": "DEG",
            "name": "Degraded Co",
            "status": "skipped",
            "quality": "degraded",
            "stage": "source_quality_gate",
            "reasons": ("industry_membership_unverified",),
            "warnings": ("source_quality_degraded",),
            "eligible": False,
            "scored": False,
            "selected": False,
        },
    )


def _body_result(
    result_id: str = "r019-postprocess-A",
    invocation_id: str | None = None,
    *,
    empty: bool = False,
    decision_at: datetime = DECISION_AT,
) -> tuple[RecommendationBodyResult, tuple[dict[str, Any], ...]]:
    invocation = invocation_id or f"{result_id}:invocation"
    specs = _candidate_specs(empty=empty)
    names = [str(spec["code"]) for spec in specs]
    strategy_config: dict[str, object] = {
        "strategy_version_id": "scheduled-test-strategy-v1",
        "cost_model_id": "synthetic-gross-close-v1",
        "benchmark_id": "TAIEX",
        "horizon_days": 20,
        "recommendation_ranking": {"threshold_mode": "fixed"},
    }
    strategy_payload = build_strategy_config_identity(
        strategy_config,
        max_stocks=10,
        top_n=1,
    )
    strategy_payload["strategy_version_id"] = strategy_config["strategy_version_id"]
    universe_payload = build_recommendation_universe_identity(
        decision_date=AS_OF.isoformat(),
        selection_mode="top_max_stocks",
        industry_filter="全部",
        max_stocks=10,
        requested_codes=None,
        selected_codes=names,
        source_provider_id="SyntheticTypedPostprocessProvider",
    )
    evidence = RecommendationRunEvidenceIdentity(
        cost_model_id="synthetic-gross-close-v1",
        benchmark_id="TAIEX",
        horizon_days=20,
        evidence_tier="forward",
        return_basis=DEFAULT_RETURN_BASIS,
    )
    raw_context: dict[str, object] = {
        "result_id": result_id,
        "as_of_date": AS_OF.isoformat(),
        "decision_at": decision_at.isoformat(),
        "data_fingerprint": "sha256:data-synthetic-01",
        "market_data_fingerprint": "sha256:market-synthetic-01",
        "source_id": "SyntheticTypedPostprocessProvider",
        "temporal_mode": "point_in_time",
        "eligible_universe_size": 1 if not empty else 0,
        "warnings": ["synthetic_fixture"],
        **strategy_payload,
        **universe_payload,
        "cost_model_id": evidence.cost_model_id,
        "benchmark_id": evidence.benchmark_id,
        "industry_benchmark_id": evidence.industry_benchmark_id,
        "horizon_days": evidence.horizon_days,
        "evidence_tier": evidence.evidence_tier,
        "return_basis": evidence.return_basis,
        "cutoff_selection": CUTOFF_SELECTION,
        "cutoff_policy": CUTOFF_POLICY,
    }
    context_owner = InvocationLegacyContextOwner(invocation)
    context_owner.mutable_context.update(raw_context)
    typed_context = RecommendationBodyContextFacts.capture(
        result_id=result_id,
        invocation_id=invocation,
        as_of_date=AS_OF,
        data_fingerprint="sha256:data-synthetic-01",
        market_data_fingerprint="sha256:market-synthetic-01",
        source_id="SyntheticTypedPostprocessProvider",
        temporal_mode="point_in_time",
        decision_at=decision_at.isoformat(),
        eligible_universe_size=1 if not empty else 0,
        warnings=("synthetic_fixture",),
        legacy_context=context_owner.freeze_current_context(),
        strategy_identity=strategy_identity_from_payload(
            raw_context,
            strategy_version_id=raw_context.get("strategy_version_id"),
        ),
        universe_identity=universe_identity_from_payload(raw_context),
        evidence_identity=evidence,
        cutoff_selection=CUTOFF_SELECTION,
        cutoff_policy=CUTOFF_POLICY,
    )

    assessments: list[CandidateAssessment] = []
    dispositions: list[CandidateDecisionDisposition] = []
    candidate_facts: list[CandidateRowFacts] = []
    items: list[RecommendationItem] = []
    recommendations: list[RecommendationDTO] = []
    rows: list[dict[str, Any]] = []
    for spec in specs:
        code = str(spec["code"])
        reasons = tuple(spec["reasons"])
        assessment = CandidateAssessment(
            stock_code=code,
            eligible=bool(spec["eligible"]),
            reasons=reasons,
        )
        assessments.append(assessment)
        dispositions.append(
            CandidateDecisionDisposition(
                invocation_id=invocation,
                stock_code=code,
                status=str(spec["status"]),
                quality=str(spec["quality"]),
                stage=str(spec["stage"]),
                reason_codes=reasons,
                threshold_name="top_n" if code == "TOPN" else "",
                observed_value="2" if code == "TOPN" else "",
                required_value="1" if code == "TOPN" else "",
                warnings=tuple(spec["warnings"]),
                assessment=assessment,
                scored=bool(spec["scored"]),
            )
        )
        if bool(spec["selected"]):
            score = Decimal("88.5000")
            dto = RecommendationDTO(
                stock_code=code,
                stock_name=str(spec["name"]),
                close_price=Decimal("100.00"),
                price_change=Decimal("1.25"),  # type: ignore[arg-type]
                total_score=score,  # type: ignore[arg-type]
                indicator_score=Decimal("30.00"),  # type: ignore[arg-type]
                pattern_score=Decimal("30.00"),  # type: ignore[arg-type]
                volume_score=Decimal("20.00"),  # type: ignore[arg-type]
                recommendation_reasons="selected by synthetic rule",
                industry="Semiconductor",
                regime_match=True,
                eligible_universe_size=1,
                eligible_universe_date=AS_OF.isoformat(),
                ranking_method="fixed_threshold",
                threshold_mode="fixed",
            )
            recommendations.append(dto)
            items.append(
                RecommendationItem(
                    stock_code=code,
                    stock_name=str(spec["name"]),
                    rule_score=score,
                    close_price=Decimal("100.00"),
                    price_change=Decimal("1.25"),
                    indicator_score=Decimal("30.00"),
                    pattern_score=Decimal("30.00"),
                    volume_score=Decimal("20.00"),
                    industry="Semiconductor",
                    reason_text="selected by synthetic rule",
                    rank=1,
                    eligible_universe_size=1,
                    eligible_universe_date=AS_OF,
                    ranking_method="fixed_threshold",
                    threshold_mode="fixed",
                    regime_match=True,
                )
            )
        candidate_facts.append(
            CandidateRowFacts(
                stock_code=code,
                stock_name=str(spec["name"]),
                industry="Semiconductor" if bool(spec["selected"]) else "",
                total_score_text="88.5000" if bool(spec["selected"]) else "",
                threshold_mode="fixed",
                invocation_id=invocation,
            )
        )
        rows.append(
            {
                "stock_code": code,
                "stock_name": spec["name"],
                "status": spec["status"],
                "quality": spec["quality"],
                "stage": spec["stage"],
                "reason_codes": list(reasons),
                "warnings": list(spec["warnings"]),
            }
        )

    result = RecommendationBodyResult(
        result_id=result_id,
        invocation_id=invocation,
        decision=DecisionBatch(
            items=tuple(items),
            assessments=tuple(assessments),
        ),
        dispositions=tuple(dispositions),
        candidate_facts=tuple(candidate_facts),
        context=typed_context,
        legacy_recommendations=tuple(
            LegacyRecommendationSnapshot.capture(
                recommendation,
                invocation_id=invocation,
                result_id=result_id,
            )
            for recommendation in recommendations
        ),
    )
    return result, tuple(rows)


def _postprocess_input(
    body: RecommendationBodyResult,
    rows: tuple[dict[str, Any], ...],
    *,
    created_at: datetime = CREATED_AT,
) -> RecommendationPostprocessInput:
    typed = body.context
    raw_context = typed.legacy_context.thaw()
    assert isinstance(raw_context, dict)
    post_context = RecommendationInvocationContext(
        as_of_date=AS_OF,
        created_at=created_at,
        service_run_started_at=created_at + timedelta(seconds=10),
        available_at=created_at + timedelta(seconds=30),
        decision_at=datetime.fromisoformat(typed.decision_at),
        strategy_identity=typed.strategy_identity,
        universe_identity=typed.universe_identity,
        raw_context=raw_context,
    )
    return RecommendationPostprocessInput(
        result_id=body.result_id,
        request=Request(as_of_date=AS_OF, max_stocks=10, top_n=1),
        runtime_config={"scheduled_snapshot": True},
        recommendations=tuple(
            snapshot.materialize() for snapshot in body.legacy_recommendations
        ),
        screening_matrix=rows,
        context=post_context,
        body_result=body,
    )


def _scheduled_callback(
    body_result: RecommendationBodyResult,
    rows: tuple[dict[str, Any], ...],
    *,
    created_at: datetime = CREATED_AT,
):
    return _build_scheduled_postprocess_callback(
        caller_config={
            "result_id": body_result.result_id,
            # The scheduled callback must source market cutoff provenance from
            # BodyResult even when the caller config does not carry it.
            "cost_model_id": body_result.context.evidence_identity.cost_model_id,
            "benchmark_id": body_result.context.evidence_identity.benchmark_id,
            "horizon_days": body_result.context.evidence_identity.horizon_days,
            "return_basis": body_result.context.evidence_identity.return_basis,
        },
        decision_date=_scheduled_date_from_created_at(created_at),
        max_stocks=10,
        top_n=1,
    )(_postprocess_input(body_result, rows, created_at=created_at))


def _scheduled_date_from_created_at(created_at: datetime = CREATED_AT) -> str:
    return created_at.astimezone(SCHEDULE_TIMEZONE).date().isoformat()


def test_typed_cohort_v1_json_hash_matches_legacy_builder_for_all_coverage_classes() -> None:
    body, matrix = _body_result()
    typed_payload = snapshot_cohort_payload_from_body_result(body)
    legacy_payload = _build_snapshot_cohort(
        screening_matrix=[dict(row) for row in matrix],
        recommendations=[snapshot.materialize() for snapshot in body.legacy_recommendations],
    )

    assert typed_payload == legacy_payload
    assert typed_payload["cohort_hash"] == legacy_payload["cohort_hash"]
    assert typed_payload["eligible_symbols"] == ["SEL"]
    assert typed_payload["excluded_symbols"] == ["TOPN"]
    assert typed_payload["missing_symbols"] == ["MISS"]
    assert typed_payload["degraded_symbols"] == ["DEG"]
    assert typed_payload["coverage_status"] == "partial"


def test_typed_empty_cohort_v1_json_hash_matches_legacy_builder() -> None:
    body, matrix = _body_result("r019-postprocess-empty", empty=True)
    typed_payload = snapshot_cohort_payload_from_body_result(body)
    legacy_payload = _build_snapshot_cohort(
        screening_matrix=[dict(row) for row in matrix],
        recommendations=[],
    )

    assert typed_payload == legacy_payload
    assert typed_payload["requested_symbols"] == []
    assert typed_payload["eligible_symbols"] == []
    assert typed_payload["coverage_status"] == "complete"
    assert typed_payload["cohort_hash"] == _json_hash(
        {key: value for key, value in typed_payload.items() if key != "cohort_hash"}
    )


def test_postprocess_input_and_facts_reject_cross_result_or_invocation_identity() -> None:
    body_a, rows_a = _body_result("r019-postprocess-A", "r019-postprocess-A:invocation")
    body_b, rows_b = _body_result("r019-postprocess-B", "r019-postprocess-B:invocation")
    input_a = _postprocess_input(body_a, rows_a)
    facts_a = _scheduled_callback(body_a, rows_a)

    with pytest.raises(ValueError, match="result_id 與 BodyResult 不一致"):
        replace(input_a, result_id=body_b.result_id)
    with pytest.raises(ValueError, match="result_id 與 BodyResult 不一致"):
        replace(input_a, body_result=body_b)

    _validate_postprocess_facts(facts=facts_a, body_result=body_a, scheduled=True)
    with pytest.raises(ValueError, match="facts result_id"):
        _validate_postprocess_facts(
            facts=replace(facts_a, result_id=body_b.result_id),
            body_result=body_a,
            scheduled=True,
        )
    with pytest.raises(ValueError, match="facts invocation_id"):
        _validate_postprocess_facts(
            facts=replace(facts_a, invocation_id=body_b.invocation_id),
            body_result=body_a,
            scheduled=True,
        )
    assert facts_a.snapshot_cohort == _scheduled_callback(body_a, rows_a).snapshot_cohort
    assert body_b.result_id != body_a.result_id


def test_legacy_matrix_and_raw_context_pollution_cannot_change_typed_postprocess_facts() -> None:
    body, rows = _body_result()
    input_value = _postprocess_input(body, rows)
    canonical_payload = snapshot_cohort_payload_from_body_result(body)
    canonical_cutoff = (body.context.cutoff_selection, body.context.cutoff_policy)
    callback = _build_scheduled_postprocess_callback(
        caller_config={
            "result_id": body.result_id,
            "cost_model_id": body.context.evidence_identity.cost_model_id,
            "benchmark_id": body.context.evidence_identity.benchmark_id,
            "horizon_days": body.context.evidence_identity.horizon_days,
            "return_basis": body.context.evidence_identity.return_basis,
        },
        decision_date=_scheduled_date_from_created_at(),
        max_stocks=10,
        top_n=1,
    )

    poisoned_matrix = [dict(row) for row in input_value.screening_matrix]
    poisoned_matrix[0]["quality"] = "missing"
    poisoned_input = replace(input_value, screening_matrix=tuple(poisoned_matrix))
    with pytest.raises(ValueError, match="legacy/typed snapshot cohort v1 parity mismatch"):
        callback(poisoned_input)

    raw_context = input_value.context.raw_context
    assert isinstance(raw_context, dict)
    raw_context["cutoff_selection"] = "tampered_legacy_cutoff"
    raw_context["cutoff_policy"] = "tampered_legacy_policy"
    raw_context["cost_model_id"] = "tampered_legacy_model"
    with pytest.raises(ValueError, match="legacy/typed scheduled evidence identity parity mismatch"):
        callback(input_value)

    # A cutoff-only mutation in the legacy sidecar is ignored by the canonical
    # postprocess projection. The typed cutoff remains in the validated result
    # config; a contradictory caller config is separately rejected below.
    raw_context["cost_model_id"] = body.context.evidence_identity.cost_model_id
    clean_again = _postprocess_input(body, rows)
    clean_raw = clean_again.context.raw_context
    assert isinstance(clean_raw, dict)
    clean_raw["cutoff_selection"] = "tampered_legacy_cutoff"
    clean_raw["cutoff_policy"] = "tampered_legacy_policy"
    facts = callback(clean_again)
    result_config = json.loads(facts.result_config_snapshot.raw_result_config_json)
    assert result_config["cutoff_selection"] == canonical_cutoff[0]
    assert result_config["cutoff_policy"] == canonical_cutoff[1]
    assert facts.snapshot_cohort == snapshot_cohort_from_body_result(body)
    assert snapshot_cohort_payload_from_body_result(body) == canonical_payload
    _validate_postprocess_facts(facts=facts, body_result=body, scheduled=True)

    contradictory = _build_scheduled_postprocess_callback(
        caller_config={
            "cutoff_selection": "caller_wrong_cutoff",
            "cutoff_policy": canonical_cutoff[1],
        },
        decision_date=_scheduled_date_from_created_at(),
        max_stocks=10,
        top_n=1,
    )
    with pytest.raises(ValueError, match="caller config cutoff_selection"):
        contradictory(_postprocess_input(body, rows))


class _SyntheticService:
    """Execution shell that can publish one typed body without IO."""

    recommendation_input_preparer = None
    market_data_provider = None
    config = None

    def __init__(self, body_result: RecommendationBodyResult, *, fail: bool = False) -> None:
        self.body_result = body_result
        self.fail = fail

    def _reset_negative_evidence_buffers(self) -> None:
        self.last_calibration_projections = []
        self.last_screening_matrix = []
        self.last_excluded_candidates_json = []
        self.last_why_not_payload_json = []
        self.last_liquidity_gate_payload_json = []
        self.last_exclusion_quality = "observed"
        self.last_exclusion_warnings_json = []
        self.last_run_context = {}

    def _get_fundamental_sqlite_provider(self) -> None:
        return None

    def _run_recommendation_body_result(
        self, **_kwargs: object
    ) -> RecommendationBodyResult:
        if self.fail:
            raise RuntimeError("synthetic body failure")
        self._reset_negative_evidence_buffers()
        self.last_run_context = self.body_result.context.legacy_context.thaw()
        self.last_screening_matrix = [
            {
                "stock_code": item.stock_code,
                "status": item.status,
                "quality": item.quality,
                "stage": item.stage,
                "reason_codes": list(item.reason_codes),
                "warnings": list(item.warnings),
            }
            for item in self.body_result.dispositions
        ]
        self._personalization_execution_clocks = {
            "run_started_at": RUN_STARTED_AT.isoformat(),
            "available_at": AVAILABLE_AT.isoformat(),
        }
        return self.body_result


def _config_snapshot() -> RecommendationConfigSnapshot:
    raw = "{}"
    return RecommendationConfigSnapshot(
        raw_config_json=raw,
        raw_json_sha256=_json_hash({}),
    )


def test_failed_or_cancelled_execute_does_not_invoke_postprocess_callback() -> None:
    body, _rows = _body_result("r019-postprocess-execution", "r019-postprocess-execution:invocation")
    callback_calls: list[RecommendationPostprocessInput] = []

    def callback(value: RecommendationPostprocessInput) -> RecommendationPostprocessFacts:
        callback_calls.append(value)
        return _scheduled_callback(body, _rows)

    with pytest.raises(RuntimeError, match="synthetic body failure"):
        execute_recommendation(
            _SyntheticService(body, fail=True),
            runtime_config={"scheduled_snapshot": True, "as_of_date": AS_OF.isoformat()},
            as_of_date=AS_OF,
            result_id=body.result_id,
            request_config_snapshot=_config_snapshot(),
            postprocess_callback=callback,
        )
    assert callback_calls == []

    before = execute_recommendation(
        _SyntheticService(body),
        runtime_config={"scheduled_snapshot": True, "as_of_date": AS_OF.isoformat()},
        as_of_date=AS_OF,
        result_id=f"{body.result_id}-cancel-before",
        request_config_snapshot=_config_snapshot(),
        postprocess_callback=callback,
        cancel=lambda: True,
    )
    assert before.status.value == "cancelled"
    assert callback_calls == []

    checks = 0

    def cancel_after_body() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    after = execute_recommendation(
        _SyntheticService(body),
        runtime_config={"scheduled_snapshot": True, "as_of_date": AS_OF.isoformat()},
        as_of_date=AS_OF,
        result_id=body.result_id,
        request_config_snapshot=_config_snapshot(),
        postprocess_callback=callback,
        cancel=cancel_after_body,
        created_at=CREATED_AT,
    )
    assert after.status.value == "cancelled"
    assert callback_calls == []
    assert any(event.event_type == "legacy_negative_evidence_capture" for event in after.events)
