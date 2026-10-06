"""R019 closure coverage across populated execution, codec, and calibration."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pandas as pd

from app_module.recommendation.codec import decode_execution, encode_execution
from app_module.recommendation.execute import execute_recommendation
from app_module.recommendation.body_result import RecommendationBodyResult
from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationProjection,
)
from app_module.recommendation_service import RecommendationService
from decision_module.recommendation.contracts import DecisionBatch
from recommendation_test_support import build_recommendation_test_preparer


_CUTOFF = date(2026, 5, 20)


class _FrameProvider:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def __call__(self) -> pd.DataFrame:
        return self._frame.copy(deep=True)


def _market_frame(codes: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "日期": current,
                "available_date": current,
                "證券代號": code,
                "證券名稱": f"{code}_NAME",
                "收盤價": Decimal("100.00"),
                "成交股數": 1_000,
            }
            for code in codes
            for current in (
                _CUTOFF - timedelta(days=offset)
                for offset in reversed(range(20))
            )
        ]
    )


def _service(
    tmp_path: Path,
    scores: dict[str, object],
    *,
    calibration_consumer: object | None = None,
) -> RecommendationService:
    data_root = tmp_path / "DATA_ROOT"
    output_root = tmp_path / "OUTPUT_ROOT"
    config = SimpleNamespace(
        db_file=data_root / "synthetic.sqlite",
        data_root=data_root,
        output_root=output_root,
        default_start_date="2026-05-01",
        profile="test",
        use_sqlite=False,
        pit_market_scope="twse_listed",
    )
    if calibration_consumer is not None:
        data_root.mkdir(parents=True, exist_ok=True)
        config.db_file.touch()
    codes = tuple(scores)
    provider = _FrameProvider(_market_frame(codes))
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=provider,
        regime_detector=MagicMock(),
        calibration_consumer=calibration_consumer,
        input_preparer=build_recommendation_test_preparer(
            config,
            market_data_provider=provider,
        ),
    )
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.return_value = []
    service.reason_engine.format_reason_text.return_value = ""

    def generate(stock_frame: pd.DataFrame, _config: dict[str, Any]) -> pd.DataFrame:
        code = str(stock_frame.iloc[-1]["證券代號"])
        score = scores[code]
        return pd.DataFrame(
            {
                "FinalScore": [score],
                "TotalScore": [score],
                "收盤價": [Decimal("100.00")],
            }
        )

    service.strategy_configurator.generate_recommendations = generate
    return service


def _config() -> dict[str, Any]:
    return {
        "profile_id": "r019-closure-test",
        "profile_version": "1",
        "recommendation_ranking": {"threshold_mode": "fixed"},
        "as_of_date": _CUTOFF.isoformat(),
    }


def _track_body_results(monkeypatch) -> dict[str, tuple[RecommendationService, object]]:
    observed: dict[str, tuple[RecommendationService, object]] = {}
    original = RecommendationService._run_recommendation_body_result

    def tracked(invocation: RecommendationService, **kwargs: Any):
        body_result = original(invocation, **kwargs)
        result_id = str(kwargs.get("result_id") or "")
        observed[result_id] = (invocation, body_result)
        return body_result

    monkeypatch.setattr(
        RecommendationService, "_run_recommendation_body_result", tracked
    )
    return observed


def test_populated_execute_codec_round_trip_matches_same_body_decision_and_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _service(
        tmp_path,
        {"HIGH": Decimal("91.50"), "LOW": Decimal("30.00")},
    )
    observed = _track_body_results(monkeypatch)
    result_id = "r019-populated-codec-roundtrip"

    execution = execute_recommendation(
        service,
        _config(),
        max_stocks=10,
        top_n=2,
        result_id=result_id,
    )

    _invocation, body_result = observed[result_id]
    assert type(body_result) is RecommendationBodyResult
    assert execution.decision is body_result.decision
    assert type(execution.decision) is DecisionBatch
    assert [item.stock_code for item in execution.decision.items] == ["HIGH", "LOW"]
    assert execution.context.as_of_date == _CUTOFF
    assert execution.context.decision_at.isoformat() == body_result.context.decision_at
    assert execution.context.strategy_identity == body_result.context.strategy_identity
    assert execution.context.universe_identity == body_result.context.universe_identity
    assert execution.context.warnings == (
        *body_result.context.warnings,
        "legacy_source_identity_unbound",
    )

    encoded = encode_execution(execution)
    decoded = decode_execution(encoded)
    assert decoded == execution
    assert decoded.decision == body_result.decision
    assert decoded.context == execution.context
    assert encode_execution(decoded) == encoded


class _ReversePredictionConsumer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def project_many(self, **kwargs: Any) -> dict[str, RecommendationCalibrationProjection]:
        assert kwargs["selection_authority"] == "rule_top_n"
        assert kwargs["selection_score_kind"] == "rule_total_score"
        assert kwargs["selection_percentile_kind"] == "rule_percentile"
        assert kwargs["top_n_changed_by_model"] is False
        codes = tuple(kwargs["feature_values_by_symbol"])
        self.calls.append(codes)
        return {
            code: RecommendationCalibrationProjection(
                stock_code=code,
                ranking_score_bp=100 if code == "HIGH" else 9_900,
                ranking_percentile_bp=None,
                ranking_method="synthetic-reverse",
                calibrated_probability_bp=(100 if code == "HIGH" else 9_900),
                calibrated_probability_status="shadow_candidate",
                after_cost_profit_probability_bp=None,
                after_cost_profit_probability_status="unavailable",
                confidence_tier="synthetic",
                evidence_confidence="observed",
                sample_size=10,
                horizon="20 trading days",
                cost_basis="synthetic fixture",
                cost_basis_bp=0,
                model_version="synthetic-model",
                dataset_version="synthetic-dataset",
                source_trace=("synthetic-reversed-ranking",),
                status="active_candidate",
            )
            for code in codes
        }


def test_reverse_calibration_predictions_cannot_change_rule_top_n_or_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
    from ml_module.historical_feature_builder import HistoricalFeatureBuilder
    import app_module.recommendation_service as service_module

    consumer = _ReversePredictionConsumer()
    service = _service(
        tmp_path,
        {"HIGH": Decimal("91.50"), "LOW": Decimal("30.00")},
        calibration_consumer=consumer,
    )
    observed = _track_body_results(monkeypatch)

    def load_snapshot(
        _provider: MLHistoricalSnapshotProvider,
        *,
        decision_date: str,
        history_start_date: str,
        symbols: tuple[str, ...],
        industry_index_names: tuple[str, ...],
    ) -> SimpleNamespace:
        assert decision_date == _CUTOFF.isoformat()
        assert history_start_date == "2026-05-01"
        return SimpleNamespace(
            decision_date=decision_date,
            feature_as_of_date=decision_date,
            symbols=symbols,
        )

    def compute_features(
        _builder: HistoricalFeatureBuilder,
        snapshot: SimpleNamespace,
        *,
        industry_index_name_by_symbol: dict[str, str],
    ) -> tuple[SimpleNamespace, ...]:
        return tuple(
            SimpleNamespace(
                symbol=code,
                values=(("synthetic_feature", index + 1),),
                decision_date=snapshot.decision_date,
                feature_as_of_date=snapshot.feature_as_of_date,
                feature_available_date=snapshot.decision_date,
                snapshot_hash=f"synthetic-{code}",
            )
            for index, code in enumerate(snapshot.symbols)
        )

    monkeypatch.setattr(MLHistoricalSnapshotProvider, "load", load_snapshot)
    monkeypatch.setattr(HistoricalFeatureBuilder, "compute", compute_features)
    monkeypatch.setattr(
        service_module,
        "build_inference_provenance",
        lambda **_kwargs: {"fixture": "synthetic"},
    )

    two_selected = execute_recommendation(
        service,
        _config(),
        max_stocks=10,
        top_n=2,
        result_id="r019-reverse-calibration-top-two",
    )
    _invocation, body_result = observed["r019-reverse-calibration-top-two"]
    assert type(body_result) is RecommendationBodyResult
    assert consumer.calls == [("HIGH", "LOW")]
    assert two_selected.decision is body_result.decision
    assert [item.stock_code for item in two_selected.decision.items] == ["HIGH", "LOW"]
    assert [
        dto.field_value("stock_code")
        for dto in body_result.legacy_recommendations
    ] == ["HIGH", "LOW"]
    assert [dto.field_value("ranking_score_bp") for dto in body_result.legacy_recommendations] == [
        100,
        9_900,
    ]
    assert [item.rule_score for item in two_selected.decision.items] == [
        Decimal("91.50"),
        Decimal("30.00"),
    ]

    one_selected = execute_recommendation(
        service,
        _config(),
        max_stocks=10,
        top_n=1,
        result_id="r019-reverse-calibration-top-one",
    )
    _invocation, one_body_result = observed["r019-reverse-calibration-top-one"]
    assert type(one_body_result) is RecommendationBodyResult
    assert consumer.calls == [("HIGH", "LOW"), ("HIGH",)]
    assert one_selected.decision is one_body_result.decision
    assert [item.stock_code for item in one_selected.decision.items] == ["HIGH"]
    assert [
        dto.field_value("stock_code")
        for dto in one_body_result.legacy_recommendations
    ] == ["HIGH"]
