"""R019 history-only decision preflight regression tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

import app_module.recommendation_service as recommendation_service_module
from app_module.recommendation_service import RecommendationService
from app_module.recommendation.body_result import RecommendationBodyResult
from decision_module.recommendation.evaluate import (
    CandidateHistoryFacts,
    CandidateSeed,
    RecommendationEvaluationPolicy,
    RecommendationEvaluator,
)
from recommendation_test_support import build_recommendation_test_preparer


def _market_frame(*, periods: int) -> pd.DataFrame:
    dates = pd.date_range("2026-05-01", periods=periods, freq="D")
    return pd.DataFrame(
        [
            {
                "日期": current_date,
                "available_date": current_date,
                "證券代號": "2330",
                "證券名稱": "台積電",
                "收盤價": Decimal("100.00"),
                "成交股數": 1000,
            }
            for current_date in dates
        ],
        columns=[
            "日期",
            "available_date",
            "證券代號",
            "證券名稱",
            "收盤價",
            "成交股數",
        ],
    )


def _build_service(
    tmp_path: Path, *, periods: int
) -> tuple[RecommendationService, list[str]]:
    config = SimpleNamespace(
        db_file=tmp_path / "missing-fundamentals.db",
        use_sqlite=False,
        pit_market_scope="twse_listed",
    )
    frame = _market_frame(periods=periods)
    provider = lambda: frame.copy(deep=True)
    preparer = build_recommendation_test_preparer(
        config,
        market_data_provider=provider,
    )
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=provider,
        regime_detector=MagicMock(),
        calibration_consumer=None,
        input_preparer=preparer,
    )
    calls: list[str] = []
    service.strategy_configurator.generate_recommendations = (
        lambda stock_frame, _config: calls.append("scorer") or pd.DataFrame()
    )
    return service, calls


def _run_body_result(
    service: RecommendationService, *, result_id: str
) -> RecommendationBodyResult:
    input_session = service.recommendation_input_preparer.begin(
        service.config,
        market_data_provider=service.market_data_provider,
    )
    return service._run_recommendation_body_result(
        {},
        result_id=result_id,
        input_session=input_session,
    )


def test_history_preflight_matches_legacy_start_diagnostics_at_19_and_allows_20() -> None:
    evaluator = RecommendationEvaluator()
    policy = RecommendationEvaluationPolicy(
        invocation_id="r019-history-boundary",
        decision_date=date(2026, 5, 20),
        decision_date_text="2026-05-20",
    )
    facts = CandidateHistoryFacts(
        invocation_id=policy.invocation_id,
        stock_code="2330",
        history_rows=19,
    )

    preflight = evaluator.preflight_history(facts)
    legacy_start = evaluator.start(
        CandidateSeed(
            invocation_id=policy.invocation_id,
            stock_code="2330",
            stock_name="台積電",
            history_rows=19,
            strategy_result_present=True,
        ),
        policy,
    )

    assert preflight is not None
    assert legacy_start.outcome == preflight
    assert preflight.status == "missing"
    assert preflight.quality == "missing"
    assert preflight.stage == "pre_evaluation"
    assert preflight.reason_codes == ("insufficient_history",)
    assert preflight.threshold_name == "minimum_history_rows"
    assert preflight.observed_value == "19"
    assert preflight.required_value == "20"
    assert preflight.assessment is not None
    assert preflight.assessment.missing_data == ("insufficient_history",)
    assert evaluator.preflight_history(
        CandidateHistoryFacts(
            invocation_id=policy.invocation_id,
            stock_code="2330",
            history_rows=20,
        )
    ) is None


def test_history_preflight_rejects_invalid_history_facts() -> None:
    with pytest.raises(ValueError, match="history_rows"):
        CandidateHistoryFacts(
            invocation_id="r019-history-invalid",
            stock_code="2330",
            history_rows=True,  # type: ignore[arg-type]
        )


def test_service_short_history_skips_features_scorer_and_keeps_legacy_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, scorer_calls = _build_service(tmp_path, periods=19)
    feature_calls: list[int] = []
    caplog.set_level("INFO")

    def should_not_enrich(frame: pd.DataFrame) -> pd.DataFrame:
        feature_calls.append(len(frame))
        raise AssertionError("19-row candidate must stop before feature enrichment")

    monkeypatch.setattr(
        recommendation_service_module,
        "enrich_latest_market_features",
        should_not_enrich,
    )

    body_result = _run_body_result(service, result_id="r019-history-19")

    assert body_result.decision.items == ()
    assert scorer_calls == []
    assert feature_calls == []
    assert service.last_screening_matrix == [
        {
            "stock_code": "2330",
            "stock_name": "台積電",
            "status": "missing",
            "reason_codes": ["insufficient_history"],
            "quality": "missing",
            "stage": "pre_evaluation",
            "threshold_name": "minimum_history_rows",
            "observed_value": "19",
            "required_value": "20",
            "total_score": "",
            "score_bp": None,
            "score_percentile_bp": None,
            "eligible_universe_size": None,
            "threshold_mode": "fixed",
            "warnings": [],
            "industry": "",
            "as_of_date": body_result.context.as_of_date,
            "data_fingerprint": body_result.context.data_fingerprint,
        }
    ]
    assert "數據不足=1" in caplog.text


def test_service_20_rows_continues_to_features_then_scorer_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, scorer_calls = _build_service(tmp_path, periods=20)
    events: list[str] = []
    original_enrich = recommendation_service_module.enrich_latest_market_features

    def track_enrichment(frame: pd.DataFrame) -> pd.DataFrame:
        events.append("features")
        return original_enrich(frame)

    monkeypatch.setattr(
        recommendation_service_module,
        "enrich_latest_market_features",
        track_enrichment,
    )
    service.strategy_configurator.generate_recommendations = (
        lambda _frame, _config: events.append("scorer")
        or scorer_calls.append("scorer")
        or pd.DataFrame()
    )

    body_result = _run_body_result(service, result_id="r019-history-20")

    assert body_result.decision.items == ()
    assert events == ["features", "scorer"]
    assert scorer_calls == ["scorer"]
    assert service.last_screening_matrix[0]["reason_codes"] == [
        "strategy_filter_no_signal"
    ]
