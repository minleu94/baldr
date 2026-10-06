"""R019 service-level characterization for full item projection and late failures."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from app_module.recommendation.body_result import RecommendationBodyResult
from app_module.recommendation.execute import execute_recommendation
from app_module.recommendation_service import RecommendationService
from data_module.config import TWStockConfig
from data_module.fundamental_data import MonthlyRevenueRecord
from data_module.recommendation_input_providers import ValuationPEObservation
from recommendation_test_support import build_recommendation_test_preparer


CUTOFF = date(2026, 5, 20)


class _FrameProvider:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def __call__(self) -> pd.DataFrame:
        return self._frame.copy(deep=True)


def _build_service(
    tmp_path: Path,
    *,
    codes: tuple[str, ...],
    names: dict[str, str],
    strategy_rows: dict[str, dict[str, object]],
) -> RecommendationService:
    config = TWStockConfig(
        data_root=tmp_path / "profile-test-data",
        output_root=tmp_path / "profile-test-output",
        profile="test",
        pit_market_scope="twse_listed",
    )
    market_rows: list[dict[str, object]] = []
    for code in codes:
        for offset in reversed(range(20)):
            current_date = CUTOFF - timedelta(days=offset)
            market_rows.append(
                {
                    "日期": current_date,
                    "available_date": current_date,
                    "證券代號": code,
                    "證券名稱": names[code],
                    "收盤價": Decimal("101.00")
                    if current_date == CUTOFF
                    else Decimal("100.00"),
                    "成交股數": 1000,
                }
            )
    market_provider = _FrameProvider(pd.DataFrame(market_rows))
    input_preparer = build_recommendation_test_preparer(
        config,
        market_data_provider=market_provider,
    )
    industry_mapper = MagicMock()
    industry_mapper.get_stock_industries.return_value = []
    industry_mapper.get_industry_performance.return_value = None
    service = RecommendationService(
        config,
        industry_mapper=industry_mapper,
        market_data_provider=market_provider,
        regime_detector=MagicMock(),
        calibration_consumer=None,
        input_preparer=input_preparer,
    )

    def load_pe(*, stock_code: str, decision_date: str) -> ValuationPEObservation:
        return ValuationPEObservation(
            value=Decimal("10.00"),
            as_of_date=date(2026, 4, 30),
            available_date=date.fromisoformat(decision_date),
            source="synthetic-r019-item-parity",
            source_version="v1",
            quality="observed",
        )

    def load_monthly_revenues(
        *, stock_code: str, decision_date: date
    ) -> tuple[MonthlyRevenueRecord, ...]:
        return (
            MonthlyRevenueRecord(
                stock_code=stock_code,
                period="2025-04",
                as_of_date=date(2025, 4, 30),
                raw_date=date(2025, 5, 10),
                announced_date=date(2025, 5, 10),
                available_date=date(2025, 5, 10),
                revenue=Decimal("100"),
                source="synthetic-r019-item-parity",
                source_version="v1",
            ),
            MonthlyRevenueRecord(
                stock_code=stock_code,
                period="2026-04",
                as_of_date=date(2026, 4, 30),
                raw_date=date(2026, 5, 10),
                announced_date=date(2026, 5, 10),
                available_date=date(2026, 5, 10),
                revenue=Decimal("110"),
                source="synthetic-r019-item-parity",
                source_version="v1",
            ),
        )

    input_preparer.fundamental_input_provider.load_pe = load_pe
    input_preparer.fundamental_input_provider.load_monthly_revenues = (
        load_monthly_revenues
    )

    service.strategy_configurator.generate_recommendations = (
        lambda stock_frame, _runtime_config: pd.DataFrame(
            [strategy_rows[str(stock_frame.iloc[-1]["證券代號"])]]
        )
    )
    service.reason_engine.generate_reasons = lambda _row, _config: [
        {"tag": "synthetic-reason", "evidence": "fixture", "score_contrib": 1}
    ]
    return service


def _run(
    service: RecommendationService,
    monkeypatch: pytest.MonkeyPatch,
    *,
    result_id: str,
    top_n: int = 1,
) -> tuple[Any, RecommendationBodyResult, dict[str, Any]]:
    captured: dict[str, RecommendationBodyResult] = {}
    original = RecommendationService._run_recommendation_body_result

    def capture_body(invocation: RecommendationService, **kwargs: Any):
        body_result = original(invocation, **kwargs)
        assert type(body_result) is RecommendationBodyResult
        captured[str(kwargs.get("result_id"))] = body_result
        return body_result

    monkeypatch.setattr(
        RecommendationService, "_run_recommendation_body_result", capture_body
    )
    capture_sink: dict[str, Any] = {}
    execution = execute_recommendation(
        service,
        {
            "profile_id": "r019-full-item-parity",
            "profile_version": "1",
            "recommendation_ranking": {"threshold_mode": "fixed"},
            "run_id": result_id,
            "filters": {
                "pe_ratio_max": "15",
                "monthly_revenue_yoy_min": "0",
            },
        },
        max_stocks=10,
        top_n=top_n,
        as_of_date=CUTOFF,
        result_id=result_id,
        capture_sink=capture_sink,
    )
    return execution, captured[result_id], capture_sink


def test_successful_full_item_preserves_typed_projection_and_universe_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(
        tmp_path,
        codes=("2330",),
        names={"2330": "台積電（合成測試）"},
        strategy_rows={
            "2330": {
                "FinalScore": np.float64(91.5),
                "TotalScore": Decimal("80.00"),
                "收盤價": Decimal("123.4500"),
                "IndicatorScore": np.int64(85),
                "PatternScore": Decimal("95.000"),
                "VolumeScore": np.float64(90.0),
            }
        },
    )

    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id="r019-full-item-success",
    )

    assert execution.status.value == "completed"
    assert execution.decision is body.decision
    assert len(execution.decision.items) == 1
    item = execution.decision.items[0]
    dto = capture["legacy_recommendations"][0]
    assert dto.stock_name == item.stock_name == "台積電（合成測試）"
    assert type(dto.total_score) is np.float64
    assert dto.total_score == 91.5
    assert type(dto.indicator_score) is np.int64
    assert dto.indicator_score == 85
    assert type(dto.close_price) is Decimal
    assert dto.close_price == Decimal("123.4500")
    assert type(dto.price_change) is float
    assert dto.price_change == 1.0
    assert type(dto.pattern_score) is Decimal
    assert dto.pattern_score == Decimal("95.000")
    assert type(dto.volume_score) is np.float64
    assert dto.volume_score == 90.0
    assert item.rule_score == Decimal("91.5")
    assert type(item.rule_score) is Decimal
    assert item.close_price == Decimal("123.4500")
    assert type(item.close_price) is Decimal
    assert item.price_change == Decimal("1.0")
    assert type(item.price_change) is Decimal
    assert item.indicator_score == Decimal("85")
    assert type(item.indicator_score) is Decimal
    assert item.pattern_score == Decimal("95.000")
    assert type(item.pattern_score) is Decimal
    assert item.volume_score == Decimal("90.0")
    assert type(item.volume_score) is Decimal
    assert item.reasons == ("synthetic-reason",)
    assert item.reason_text == dto.recommendation_reasons

    identity = body.context.universe_identity
    assert identity is not None
    assert identity.policy is not None
    assert identity.snapshot is not None
    assert item.universe_ref is not None
    assert item.universe_ref.policy_id == identity.policy.universe_policy_id
    assert item.universe_ref.snapshot_id == identity.snapshot.universe_snapshot_id
    assert item.universe_ref.as_of_date == CUTOFF
    assert item.universe_ref.members_hash == (
        identity.snapshot.universe_snapshot_selected_codes_hash
    )
    assert body.context.as_of_date == CUTOFF.isoformat()


def test_late_item_conversion_error_has_no_partial_dto_or_success_matrix_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(
        tmp_path,
        codes=("GOOD", "LATE_BAD"),
        names={"GOOD": "Good Company", "LATE_BAD": "Bad Metric Company"},
        strategy_rows={
            "GOOD": {
                "FinalScore": Decimal("90.00"),
                "TotalScore": Decimal("80.00"),
                "收盤價": Decimal("100.00"),
                "IndicatorScore": Decimal("85.00"),
            },
            "LATE_BAD": {
                "FinalScore": Decimal("89.00"),
                "TotalScore": Decimal("80.00"),
                "收盤價": Decimal("100.00"),
                "IndicatorScore": "bad",
            },
        },
    )

    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id="r019-full-item-late-conversion-error",
    )

    assert execution.status.value == "completed"
    assert [item.stock_code for item in execution.decision.items] == ["GOOD"]
    assert [dto.stock_code for dto in capture["legacy_recommendations"]] == ["GOOD"]
    dispositions = {item.stock_code: item for item in body.dispositions}
    assert dispositions["GOOD"].status == "pass"
    assert dispositions["LATE_BAD"].status == "degraded"
    assert dispositions["LATE_BAD"].reason_codes == ("screening_exception",)
    assert dispositions["LATE_BAD"].warnings == (
        "screening_exception:InvalidOperation",
    )

    matrix = capture["compatibility_snapshot"].materialize()["last_screening_matrix"]
    assert [row["stock_code"] for row in matrix] == ["GOOD", "LATE_BAD"]
    matrix_by_code = {row["stock_code"]: row for row in matrix}
    assert matrix_by_code["GOOD"]["status"] == "pass"
    assert matrix_by_code["GOOD"]["reason_codes"] == [
        "recommendation_selected"
    ]
    assert matrix_by_code["LATE_BAD"]["status"] == "degraded"
    assert matrix_by_code["LATE_BAD"]["reason_codes"] == [
        "screening_exception"
    ]
    assert matrix_by_code["LATE_BAD"]["stage"] == "strategy_evaluation"
    assert matrix_by_code["LATE_BAD"]["warnings"] == [
        "screening_exception:InvalidOperation"
    ]
