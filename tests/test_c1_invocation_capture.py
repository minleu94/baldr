"""C1 U3 同次 invocation postprocess capture fixtures。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from threading import Event, Barrier, local
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from unittest.mock import MagicMock

from app_module.forward_position_thesis_candidate_producer import _sha256_json
from app_module.recommendation.contracts import (
    RecommendationConfigSnapshot,
    RecommendationResultConfigSnapshot,
    RecommendationRunEvidenceIdentity,
    SnapshotCohort,
    SnapshotCohortCoverage,
    SnapshotCohortCoverageStatus,
)
from app_module.recommendation.execute import (
    RecommendationPostprocessFacts,
    RecommendationPostprocessInput,
    execute_recommendation,
)
from app_module.recommendation_service import RecommendationService
from recommendation_test_support import build_recommendation_test_preparer
from scripts.scheduled.scheduled_clock import SCHEDULE_TIMEZONE


class _FrameProvider:
    def __init__(
        self,
        frames: dict[str, pd.DataFrame],
        *,
        barrier: Barrier | None = None,
    ) -> None:
        self.frames = frames
        self.barrier = barrier
        self.invocation = local()

    def __call__(self) -> pd.DataFrame:
        run_id = self.invocation.run_id
        if self.barrier is not None:
            self.barrier.wait(timeout=5)
        return self.frames[run_id].copy(deep=True)


class _ThreadClock(datetime):
    invocation = local()
    bases: dict[str, datetime] = {}

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        run_id = cls.invocation.run_id
        tick = getattr(cls.invocation, "tick", 0)
        cls.invocation.tick = tick + 1
        value = cls.bases[run_id] + timedelta(seconds=10 * tick)
        return value if tz is None else value.astimezone(tz)


def _market_frame(code: str, *, start: date = date(2026, 5, 1)) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "日期": start + timedelta(days=offset),
                "available_date": start + timedelta(days=offset),
                "證券代號": code,
                "證券名稱": f"{code}_NAME",
                "收盤價": Decimal("100.00"),
                "成交股數": 1_000,
            }
            for offset in range(20)
        ]
    )


def _service(tmp_path: Path, provider: object) -> RecommendationService:
    config = SimpleNamespace(
        db_file=tmp_path / "missing-fundamentals.db",
        use_sqlite=False,
        pit_market_scope="twse_listed",
    )
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=provider,
        regime_detector=MagicMock(),
        calibration_consumer=None,
        input_preparer=build_recommendation_test_preparer(
            config, market_data_provider=provider
        ),
    )
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.return_value = []
    service.reason_engine.format_reason_text.return_value = "合成推薦理由"

    def generate(_frame: pd.DataFrame, _config: dict[str, Any]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "FinalScore": [Decimal("91.50")],
                "TotalScore": [Decimal("91.50")],
                "IndicatorScore": [Decimal("31.2500")],
                "PatternScore": [Decimal("27.50")],
                "VolumeScore": [Decimal("18.00")],
                "收盤價": [Decimal("100.00")],
            }
        )

    service.strategy_configurator.generate_recommendations = generate
    return service


def _caller_config(run_id: str, as_of_date: str, numeric_text: str) -> dict[str, Any]:
    return {
        "profile_id": f"c1-profile-{run_id}",
        "profile_version": "1",
        "strategy_version_id": "c1-strategy-v1",
        "cost_model_id": "c1-cost-model-v1",
        "benchmark_id": "TAIEX",
        "horizon_days": 20,
        "evidence_tier": "forward",
        "return_basis": "close_to_close_event_date",
        "as_of_date": as_of_date,
        "decision_date": "2026-05-21",
        "max_stocks": 1,
        "top_n": 1,
        "research_only": True,
        "profile_name": f"C1 synthetic {run_id}",
        "look_ahead_check": "synthetic input uses decision-time observations",
        "safety_boundary": {
            "confirm": False,
            "writes_evidence_db": False,
            "auto_trading": False,
            "lifecycle_action": False,
        },
        "recommendation_ranking": {"threshold_mode": "fixed"},
        "numeric_text": numeric_text,
    }


def _snapshot(config: dict[str, Any]) -> RecommendationConfigSnapshot:
    raw = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return RecommendationConfigSnapshot(
        raw_config_json=raw,
        raw_json_sha256="sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def _cohort_from_input(
    postprocess_input: RecommendationPostprocessInput,
) -> tuple[dict[str, Any], SnapshotCohort]:
    from scripts.scheduled.run_scheduled_recommendation_snapshot import (
        _build_snapshot_cohort,
    )

    raw = _build_snapshot_cohort(
        screening_matrix=[dict(row) for row in postprocess_input.screening_matrix],
        recommendations=list(postprocess_input.recommendations),
    )
    cohort = SnapshotCohort(
        cohort_hash=raw["cohort_hash"],
        requested_symbols=tuple(raw["requested_symbols"]),
        eligible_symbols=tuple(raw["eligible_symbols"]),
        missing_symbols=tuple(raw["missing_symbols"]),
        degraded_symbols=tuple(raw["degraded_symbols"]),
        excluded_symbols=tuple(raw["excluded_symbols"]),
        requested_count=raw["requested_count"],
        eligible_count=raw["eligible_count"],
        missing_count=raw["missing_count"],
        degraded_count=raw["degraded_count"],
        excluded_count=raw["excluded_count"],
        coverage_status=SnapshotCohortCoverageStatus(raw["coverage_status"]),
        coverage_by_symbol={
            symbol: SnapshotCohortCoverage(
                status=row["status"],
                quality=row["quality"],
                stage=row["stage"],
                reason_codes=tuple(row["reason_codes"]),
                warnings=tuple(row["warnings"]),
            )
            for symbol, row in raw["coverage_by_symbol"].items()
        },
        eligible_definition=raw["eligible_definition"],
        missing_definition=raw["missing_definition"],
        degraded_definition=raw["degraded_definition"],
        excluded_definition=raw["excluded_definition"],
        schema_version=raw["schema_version"],
    )
    return raw, cohort


def _postprocess(postprocess_input: RecommendationPostprocessInput) -> RecommendationPostprocessFacts:
    raw_cohort, cohort = _cohort_from_input(postprocess_input)
    caller_config = json.loads(
        postprocess_input.request.config_snapshot.raw_config_json
    )
    result_config = deepcopy(caller_config)
    raw_context = postprocess_input.context.raw_context
    body_context = postprocess_input.body_result.context
    result_config["scheduled_snapshot"] = True
    result_config["snapshot_cohort"] = raw_cohort
    result_config.update(
        {
            "data_as_of_date": body_context.as_of_date,
            "temporal_mode": body_context.temporal_mode,
            "cutoff_selection": body_context.cutoff_selection,
            "cutoff_policy": body_context.cutoff_policy,
            "decision_date": (
                datetime.fromisoformat(body_context.decision_at)
                .astimezone(SCHEDULE_TIMEZONE)
                .date()
                .isoformat()
            ),
        }
    )
    for key in (
        "strategy_config_id",
        "strategy_config_hash",
        "strategy_config_schema",
        "strategy_config_spec",
        "universe_id",
        "universe_hash",
        "universe_identity_schema",
        "universe_policy_id",
        "universe_policy_hash",
        "universe_policy_schema",
        "universe_policy_spec",
        "universe_snapshot_id",
        "universe_snapshot_hash",
        "universe_snapshot_schema",
        "universe_snapshot_source_provider_id",
        "universe_snapshot_selected_codes_hash",
        "universe_snapshot_spec",
    ):
        result_config[key] = deepcopy(raw_context[key])
    evidence = RecommendationRunEvidenceIdentity(
        cost_model_id=caller_config["cost_model_id"],
        benchmark_id=caller_config["benchmark_id"],
        industry_benchmark_id=caller_config.get("industry_benchmark_id"),
        horizon_days=caller_config["horizon_days"],
        evidence_tier=caller_config["evidence_tier"],
        return_basis=caller_config["return_basis"],
    )
    result_config_snapshot = RecommendationResultConfigSnapshot(
        raw_result_config_json=json.dumps(
            result_config,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        config_sha256=_sha256_json(result_config),
    )
    return RecommendationPostprocessFacts(
        result_id=postprocess_input.body_result.result_id,
        invocation_id=postprocess_input.body_result.invocation_id,
        created_at=postprocess_input.context.created_at,
        snapshot_cohort=cohort,
        evidence_identity=evidence,
        result_config_snapshot=result_config_snapshot,
    )


def _postprocess_with_marker(
    postprocess_input: RecommendationPostprocessInput,
    *,
    scheduled: bool,
) -> RecommendationPostprocessFacts:
    facts = _postprocess(postprocess_input)
    result_config = json.loads(
        facts.result_config_snapshot.raw_result_config_json
    )
    result_config["scheduled_snapshot"] = scheduled
    if not scheduled:
        result_config.pop("evidence_tier", None)
        result_config.pop("return_basis", None)
    snapshot = RecommendationResultConfigSnapshot(
        raw_result_config_json=json.dumps(
            result_config,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        config_sha256=_sha256_json(result_config),
    )
    evidence_identity = (
        facts.evidence_identity
        if scheduled
        else postprocess_input.body_result.context.evidence_identity
    )
    assert evidence_identity is not None
    return RecommendationPostprocessFacts(
        result_id=facts.result_id,
        invocation_id=facts.invocation_id,
        created_at=facts.created_at,
        snapshot_cohort=facts.snapshot_cohort,
        evidence_identity=evidence_identity,
        result_config_snapshot=snapshot,
    )


def _runtime_config(config: dict[str, Any]) -> dict[str, Any]:
    runtime = deepcopy(config)
    runtime["numeric_text"] = float(config["numeric_text"])
    return runtime


def test_c1_capture_seals_full_same_invocation_request_context_and_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.recommendation_service as recommendation_service_module

    provider = _FrameProvider({"A": _market_frame("AAA")})
    provider.invocation.run_id = "A"
    service = _service(tmp_path, provider)
    original = _caller_config("A", "2026-05-20", "1.2500")
    runtime = _runtime_config(original)
    _ThreadClock.bases = {
        "A": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    }
    _ThreadClock.invocation.run_id = "A"
    _ThreadClock.invocation.tick = 0
    monkeypatch.setattr(recommendation_service_module, "datetime", _ThreadClock)
    wrapper_created_at = datetime(2026, 5, 20, 11, 59, tzinfo=timezone.utc)

    execution = service.execute_recommendation(
        runtime,
        max_stocks=1,
        top_n=1,
        request_config_snapshot=_snapshot(original),
        postprocess_callback=_postprocess,
        created_at=wrapper_created_at,
        result_id="c1-A",
    )

    assert execution.status.value == "completed"
    assert execution.result_id == "c1-A"
    assert execution.request.config_snapshot.raw_config_json == _snapshot(original).raw_config_json
    assert execution.request.max_stocks == 1
    assert execution.request.top_n == 1
    assert execution.request.as_of_date == date(2026, 5, 20)
    assert execution.request.config_snapshot.raw_config_json.find('"numeric_text":"1.2500"') >= 0
    assert runtime["numeric_text"] == 1.25
    assert execution.context.as_of_date == date(2026, 5, 20)
    assert execution.context.result_config_snapshot is not None
    result_config = json.loads(
        execution.context.result_config_snapshot.raw_result_config_json
    )
    assert result_config["decision_date"] == "2026-05-20"
    assert result_config["numeric_text"] == "1.2500"
    assert execution.context.result_config_snapshot.config_sha256 == _sha256_json(
        result_config
    )
    assert execution.context.strategy_identity is not None
    assert execution.context.universe_identity is not None
    assert execution.context.snapshot_cohort is not None
    assert execution.context.evidence_identity is not None
    assert execution.context.created_at == wrapper_created_at
    assert execution.context.available_at is not None
    assert execution.context.decision_at is not None
    assert execution.context.available_at <= execution.context.decision_at
    clock_event = next(
        event
        for event in execution.events
        if event.event_type == "recommendation_invocation_clock_capture"
    )
    assert clock_event.details["created_at"] == wrapper_created_at
    assert clock_event.details["service_run_started_at"] == datetime(
        2026, 5, 20, 12, 0, tzinfo=timezone.utc
    )

    item = execution.items[0]
    assert item.stock_code == "AAA"
    assert item.rule_score == Decimal("91.50")
    assert item.close_price == Decimal("100.00")
    assert item.price_change == Decimal("0.0")
    assert item.indicator_score == Decimal("31.2500")
    assert item.pattern_score == Decimal("27.50")
    assert item.volume_score == Decimal("18.00")
    assert item.industry == "未知"
    assert item.reason_text == "合成推薦理由"
    assert not hasattr(item, "total_score")
    assert service.last_run_context == {}
    assert service.last_screening_matrix == []


def test_c1_scheduled_input_cannot_be_downgraded_by_callback_result_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.recommendation.execute as execute_module
    import app_module.recommendation_service as recommendation_service_module

    provider = _FrameProvider({"A": _market_frame("AAA")})
    provider.invocation.run_id = "A"
    service = _service(tmp_path, provider)
    _ThreadClock.bases = {
        "A": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    }
    _ThreadClock.invocation.run_id = "A"
    _ThreadClock.invocation.tick = 0
    monkeypatch.setattr(recommendation_service_module, "datetime", _ThreadClock)
    caller = _caller_config("A", "2026-05-20", "1.2500")
    caller["scheduled_snapshot"] = True
    builder_called = False
    original_builder = execute_module._build_execution

    def missing_score_if_builder_reached(**kwargs: Any):
        nonlocal builder_called
        builder_called = True
        recommendations = deepcopy(kwargs["recommendations"])
        recommendations[0].total_score = None
        kwargs["recommendations"] = recommendations
        return original_builder(**kwargs)

    monkeypatch.setattr(
        execute_module, "_build_execution", missing_score_if_builder_reached
    )
    with pytest.raises(ValueError, match="scheduled caller config"):
        service.execute_recommendation(
            _runtime_config(caller),
            max_stocks=1,
            top_n=1,
            request_config_snapshot=_snapshot(caller),
            postprocess_callback=lambda postprocess_input: _postprocess_with_marker(
                postprocess_input, scheduled=False
            ),
            created_at=datetime(2026, 5, 20, 11, 59, tzinfo=timezone.utc),
            result_id="c1-marker-downgrade",
        )

    assert builder_called is False
    assert service.last_run_context == {}


def test_c1_scheduled_result_requires_explicit_caller_created_at(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.recommendation_service as recommendation_service_module

    provider = _FrameProvider({"A": _market_frame("AAA")})
    provider.invocation.run_id = "A"
    service = _service(tmp_path, provider)
    _ThreadClock.bases = {
        "A": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    }
    _ThreadClock.invocation.run_id = "A"
    _ThreadClock.invocation.tick = 0
    monkeypatch.setattr(recommendation_service_module, "datetime", _ThreadClock)
    caller = _caller_config("A", "2026-05-20", "1.2500")

    with pytest.raises(ValueError, match="明示原 caller created_at"):
        service.execute_recommendation(
            _runtime_config(caller),
            max_stocks=1,
            top_n=1,
            request_config_snapshot=_snapshot(caller),
            postprocess_callback=_postprocess,
            result_id="c1-missing-caller-clock",
        )

    assert service.last_run_context == {}


def test_c1_non_scheduled_callback_preserves_unknown_caller_created_at(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.recommendation_service as recommendation_service_module

    provider = _FrameProvider({"A": _market_frame("AAA")})
    provider.invocation.run_id = "A"
    service = _service(tmp_path, provider)
    _ThreadClock.bases = {
        "A": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    }
    _ThreadClock.invocation.run_id = "A"
    _ThreadClock.invocation.tick = 0
    monkeypatch.setattr(recommendation_service_module, "datetime", _ThreadClock)
    caller = _caller_config("A", "2026-05-20", "1.2500")

    execution = service.execute_recommendation(
        _runtime_config(caller),
        max_stocks=1,
        top_n=1,
        request_config_snapshot=_snapshot(caller),
        postprocess_callback=lambda postprocess_input: _postprocess_with_marker(
            postprocess_input, scheduled=False
        ),
        result_id="c1-non-scheduled-unknown-created-at",
    )

    assert execution.context.created_at is None
    clock_event = next(
        event
        for event in execution.events
        if event.event_type == "recommendation_invocation_clock_capture"
    )
    assert clock_event.details["created_at"] is None
    assert clock_event.details["service_run_started_at"] is not None


def test_c1_callback_required_for_direct_execution_even_without_scheduled_input_marker(
    tmp_path: Path,
) -> None:
    provider = _FrameProvider({"A": _market_frame("AAA")})
    provider.invocation.run_id = "A"
    service = _service(tmp_path, provider)
    original = _caller_config("A", "2026-05-20", "1.2500")
    body_calls = 0
    original_body = service._run_recommendation_body

    def counted_body(**kwargs: Any):
        nonlocal body_calls
        body_calls += 1
        return original_body(**kwargs)

    service._run_recommendation_body = counted_body
    with pytest.raises(TypeError, match="postprocess_callback"):
        service.execute_recommendation(  # type: ignore[call-arg]
            _runtime_config(original),
            request_config_snapshot=_snapshot(original),
        )
    assert body_calls == 0

    with pytest.raises(ValueError, match="scheduled recommendation"):
        execute_recommendation(
            service,
            {"scheduled_snapshot": True},
            request_config_snapshot=_snapshot(original),
        )
    assert body_calls == 0


@pytest.mark.parametrize(
    ("field", "bad_value", "expected_field"),
    [
        ("total_score", None, "rule_score"),
        ("close_price", None, "close_price"),
        ("price_change", None, "price_change"),
        ("indicator_score", None, "indicator_score"),
        ("pattern_score", None, "pattern_score"),
        ("volume_score", None, "volume_score"),
        ("indicator_score", float("inf"), "indicator_score"),
        ("industry", None, "industry"),
        ("recommendation_reasons", None, "reason_text"),
    ],
)
def test_c1_scheduled_capture_rejects_missing_or_nonfinite_consumer_numeric(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    bad_value: object,
    expected_field: str,
) -> None:
    import app_module.recommendation_service as recommendation_service_module

    provider = _FrameProvider({"A": _market_frame("AAA")})
    provider.invocation.run_id = "A"
    service = _service(tmp_path, provider)
    import app_module.recommendation.execute as execute_module

    original_build_execution = execute_module._build_execution

    def invalid_row_at_seal(**kwargs: Any):
        if kwargs.get("status").value == "completed":
            recommendations = deepcopy(kwargs["recommendations"])
            setattr(recommendations[0], field, bad_value)
            kwargs["recommendations"] = recommendations
        return original_build_execution(**kwargs)

    monkeypatch.setattr(execute_module, "_build_execution", invalid_row_at_seal)
    _ThreadClock.bases = {
        "A": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    }
    _ThreadClock.invocation.run_id = "A"
    _ThreadClock.invocation.tick = 0
    monkeypatch.setattr(recommendation_service_module, "datetime", _ThreadClock)
    original = _caller_config("A", "2026-05-20", "1.2500")

    with pytest.raises(ValueError, match=expected_field):
        service.execute_recommendation(
            _runtime_config(original),
            max_stocks=1,
            top_n=1,
            request_config_snapshot=_snapshot(original),
            postprocess_callback=_postprocess,
            created_at=datetime(2026, 5, 20, 11, 59, tzinfo=timezone.utc),
            result_id="c1-invalid-row",
        )
    assert service.last_run_context == {}


def test_c1_callback_rejects_missing_result_config_owner_and_callback_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.recommendation_service as recommendation_service_module

    provider = _FrameProvider({"A": _market_frame("AAA")})
    provider.invocation.run_id = "A"
    service = _service(tmp_path, provider)
    _ThreadClock.bases = {
        "A": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    }
    _ThreadClock.invocation.run_id = "A"
    _ThreadClock.invocation.tick = 0
    monkeypatch.setattr(recommendation_service_module, "datetime", _ThreadClock)
    original = _caller_config("A", "2026-05-20", "1.2500")

    def missing_owner(postprocess_input: RecommendationPostprocessInput):
        facts = _postprocess(postprocess_input)
        config = json.loads(facts.result_config_snapshot.raw_result_config_json)
        config.pop("benchmark_id")
        snapshot = RecommendationResultConfigSnapshot(
            raw_result_config_json=json.dumps(
                config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            config_sha256=_sha256_json(config),
        )
        return RecommendationPostprocessFacts(
            result_id=facts.result_id,
            invocation_id=facts.invocation_id,
            created_at=facts.created_at,
            snapshot_cohort=facts.snapshot_cohort,
            evidence_identity=facts.evidence_identity,
            result_config_snapshot=snapshot,
        )

    with pytest.raises(ValueError, match="benchmark_id"):
        service.execute_recommendation(
            _runtime_config(original),
            max_stocks=1,
            top_n=1,
            request_config_snapshot=_snapshot(original),
            postprocess_callback=missing_owner,
            created_at=datetime(2026, 5, 20, 11, 59, tzinfo=timezone.utc),
            result_id="c1-missing-owner",
        )

    def callback_error(_postprocess_input: RecommendationPostprocessInput):
        raise RuntimeError("synthetic callback failure")

    with pytest.raises(RuntimeError, match="synthetic callback failure"):
        service.execute_recommendation(
            _runtime_config(original),
            max_stocks=1,
            top_n=1,
            request_config_snapshot=_snapshot(original),
            postprocess_callback=callback_error,
            result_id="c1-callback-error",
        )

    def bad_hash(postprocess_input: RecommendationPostprocessInput):
        facts = _postprocess(postprocess_input)
        invalid_snapshot = RecommendationResultConfigSnapshot(
            raw_result_config_json=facts.result_config_snapshot.raw_result_config_json,
            config_sha256="sha256:" + ("0" * 64),
        )
        return RecommendationPostprocessFacts(
            result_id=facts.result_id,
            invocation_id=facts.invocation_id,
            created_at=facts.created_at,
            snapshot_cohort=facts.snapshot_cohort,
            evidence_identity=facts.evidence_identity,
            result_config_snapshot=invalid_snapshot,
        )

    with pytest.raises(ValueError, match="config_sha256"):
        service.execute_recommendation(
            _runtime_config(original),
            max_stocks=1,
            top_n=1,
            request_config_snapshot=_snapshot(original),
            postprocess_callback=bad_hash,
            created_at=datetime(2026, 5, 20, 11, 59, tzinfo=timezone.utc),
            result_id="c1-bad-hash",
        )

    def bad_created_at(postprocess_input: RecommendationPostprocessInput):
        facts = _postprocess(postprocess_input)
        return RecommendationPostprocessFacts(
            result_id=facts.result_id,
            invocation_id=facts.invocation_id,
            created_at=facts.created_at + timedelta(seconds=1),
            snapshot_cohort=facts.snapshot_cohort,
            evidence_identity=facts.evidence_identity,
            result_config_snapshot=facts.result_config_snapshot,
        )

    with pytest.raises(ValueError, match="created_at"):
        service.execute_recommendation(
            _runtime_config(original),
            max_stocks=1,
            top_n=1,
            request_config_snapshot=_snapshot(original),
            postprocess_callback=bad_created_at,
            created_at=datetime(2026, 5, 20, 11, 59, tzinfo=timezone.utc),
            result_id="c1-bad-clock",
        )
    assert service.last_run_context == {}


def test_c1_postprocess_required_execution_propagates_body_failure_without_partial_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.recommendation_service as recommendation_service_module

    class FailingProvider:
        def __call__(self) -> pd.DataFrame:
            raise RuntimeError("synthetic market provider failure")

    service = _service(tmp_path, FailingProvider())
    original = _caller_config("A", "2026-05-20", "1.2500")
    _ThreadClock.bases = {
        "A": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    }
    _ThreadClock.invocation.run_id = "A"
    _ThreadClock.invocation.tick = 0
    monkeypatch.setattr(recommendation_service_module, "datetime", _ThreadClock)
    callback_called = False

    def callback(
        postprocess_input: RecommendationPostprocessInput,
    ) -> RecommendationPostprocessFacts:
        nonlocal callback_called
        callback_called = True
        return _postprocess(postprocess_input)

    with pytest.raises(RuntimeError, match="synthetic market provider failure"):
        service.execute_recommendation(
            _runtime_config(original),
            max_stocks=1,
            top_n=1,
            request_config_snapshot=_snapshot(original),
            postprocess_callback=callback,
            result_id="c1-body-failure",
        )

    assert callback_called is False
    assert service.last_run_context == {}
    assert service.last_screening_matrix == []


def test_c1_ab_interleave_and_source_update_cannot_cross_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.recommendation_service as recommendation_service_module

    provider = _FrameProvider(
        {"A": _market_frame("AAA"), "B": _market_frame("BBB")},
        barrier=Barrier(2),
    )
    service = _service(tmp_path, provider)
    _ThreadClock.bases = {
        "A": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
        "B": datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc),
    }
    monkeypatch.setattr(recommendation_service_module, "datetime", _ThreadClock)
    both_callbacks_entered = Event()
    release_callbacks = Event()
    callback_inputs: dict[str, RecommendationPostprocessInput] = {}

    def synchronized_callback(
        postprocess_input: RecommendationPostprocessInput,
    ) -> RecommendationPostprocessFacts:
        callback_inputs[postprocess_input.result_id] = postprocess_input
        if len(callback_inputs) == 2:
            both_callbacks_entered.set()
        if not release_callbacks.wait(timeout=5):
            raise TimeoutError("兩個 callback 未同步完成")
        return _postprocess(postprocess_input)

    def invoke(run_id: str, as_of_date: str, numeric_text: str):
        _ThreadClock.invocation.run_id = run_id
        _ThreadClock.invocation.tick = 0
        provider.invocation.run_id = run_id
        original = _caller_config(run_id, as_of_date, numeric_text)
        return service.execute_recommendation(
            _runtime_config(original),
            max_stocks=1,
            top_n=1,
            request_config_snapshot=_snapshot(original),
            postprocess_callback=synchronized_callback,
            created_at=datetime.fromisoformat(as_of_date + "T11:59:00+00:00"),
            result_id=f"c1-{run_id}",
        )

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="c1-u3") as pool:
        future_a = pool.submit(invoke, "A", "2026-05-20", "1.2500")
        future_b = pool.submit(invoke, "B", "2026-06-20", "2.5000")
        assert both_callbacks_entered.wait(timeout=5)
        provider.frames["A"] = _market_frame("UPDATED_A", start=date(2026, 7, 1))
        provider.frames["B"] = _market_frame("UPDATED_B", start=date(2026, 7, 1))
        release_callbacks.set()
        execution_a = future_a.result(timeout=10)
        execution_b = future_b.result(timeout=10)

    assert execution_a.result_id == "c1-A"
    assert execution_b.result_id == "c1-B"
    assert [item.stock_code for item in execution_a.items] == ["AAA"]
    assert [item.stock_code for item in execution_b.items] == ["BBB"]
    assert execution_a.request.config_snapshot.raw_config_json.find('"numeric_text":"1.2500"') >= 0
    assert execution_b.request.config_snapshot.raw_config_json.find('"numeric_text":"2.5000"') >= 0
    assert execution_a.context.as_of_date == date(2026, 5, 20)
    assert execution_b.context.as_of_date == date(2026, 6, 20)
    assert execution_a.context.snapshot_cohort.eligible_symbols == ("AAA",)
    assert execution_b.context.snapshot_cohort.eligible_symbols == ("BBB",)
    assert execution_a.context.available_at < execution_a.context.decision_at
    assert execution_b.context.available_at < execution_b.context.decision_at
    assert execution_a.context.strategy_identity.strategy_config_hash != execution_b.context.strategy_identity.strategy_config_hash
    assert (
        execution_a.context.universe_identity.snapshot.universe_snapshot_hash
        != execution_b.context.universe_identity.snapshot.universe_snapshot_hash
    )
    assert callback_inputs["c1-A"].screening_matrix[0]["stock_code"] == "AAA"
    assert callback_inputs["c1-B"].screening_matrix[0]["stock_code"] == "BBB"
    assert service.last_run_context == {}
    assert service.last_screening_matrix == []
