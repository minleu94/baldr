"""R019 前置舊輸出 characterization：理由、regime 門檻與 DTO parity。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app_module.recommendation.execute import execute_recommendation
from app_module.recommendation.body_result import RecommendationBodyResult
from app_module.recommendation.codec import decode_execution, encode_execution
from app_module.recommendation.input_preparation import PreparedRecommendationMarket
from app_module.recommendation_service import RecommendationService
from data_module.config import TWStockConfig
from data_module.fundamental_data import MonthlyRevenueRecord
from data_module.recommendation_input_providers import ValuationPEObservation
from recommendation_test_support import build_recommendation_test_preparer


CUTOFF = date(2026, 5, 20)
_BASE_REASONS = (
    {"tag": "基本理由", "evidence": "fixture", "score_contrib": 1},
)


class _FrameProvider:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def __call__(self) -> pd.DataFrame:
        return self.frame.copy(deep=True)


def _build_service(
    tmp_path: Path,
    *,
    industry_percent: object,
    final_score: object = Decimal("84.01"),
    total_score: object = Decimal("80.00"),
    include_total_score: bool = True,
    base_reasons: tuple[dict[str, object], ...] = _BASE_REASONS,
) -> tuple[
    RecommendationService,
    MagicMock,
    SimpleNamespace,
    list[tuple[str, str, str]],
    tuple[list[str], list[list[dict[str, object]]]],
]:
    config = TWStockConfig(
        data_root=tmp_path / "profile-test-data",
        output_root=tmp_path / "profile-test-output",
        profile="test",
        pit_market_scope="twse_listed",
    )
    market_frame = pd.DataFrame(
        [
            {
                "日期": CUTOFF - timedelta(days=offset),
                "available_date": CUTOFF - timedelta(days=offset),
                "證券代號": "2330",
                "證券名稱": "TSMC",
                "收盤價": Decimal("100.00"),
                "成交股數": 1000,
            }
            for offset in reversed(range(20))
        ]
    )
    market_provider = _FrameProvider(market_frame)
    pit_result = SimpleNamespace(
        industry_filter_usable=True,
        rows=(SimpleNamespace(symbol="2330", industry_category="半導體業"),),
        lineage={"fixture_id": "r019-reason-pit"},
        status="accepted",
        quality="observed",
        warnings=(),
    )
    pit_reader = SimpleNamespace(read=MagicMock(return_value=pit_result))
    preparer = build_recommendation_test_preparer(
        config,
        market_data_provider=market_provider,
        pit_membership_reader=pit_reader,
    )
    industry_mapper = MagicMock()
    industry_mapper.get_stock_industries.return_value = ["半導體業"]
    industry_mapper.get_industry_performance.return_value = (
        None
        if industry_percent is None
        else {"漲跌百分比": industry_percent}
    )
    service = RecommendationService(
        config,
        industry_mapper=industry_mapper,
        market_data_provider=market_provider,
        regime_detector=MagicMock(),
        calibration_consumer=None,
        input_preparer=preparer,
    )

    def generate_recommendations(
        _stock_frame: pd.DataFrame, _runtime_config: dict[str, Any]
    ) -> pd.DataFrame:
        rows: dict[str, list[object]] = {
            "FinalScore": [final_score],
            "收盤價": [Decimal("100.00")],
        }
        if include_total_score:
            rows["TotalScore"] = [total_score]
        return pd.DataFrame(rows)

    service.strategy_configurator.generate_recommendations = generate_recommendations

    source_reads: list[tuple[str, str, str]] = []
    order: list[str] = []
    fundamental_provider = preparer.fundamental_input_provider

    def read_pe(*, stock_code: str, decision_date: str) -> ValuationPEObservation:
        source_reads.append(("pe", stock_code, decision_date))
        order.append("pe")
        return ValuationPEObservation(
            value=Decimal("10"),
            as_of_date=date(2026, 4, 30),
            available_date=date.fromisoformat(decision_date),
            source="synthetic-r019",
            source_version="v1",
            quality="observed",
        )

    def read_monthly_revenues(
        *, stock_code: str, decision_date: date
    ) -> tuple[MonthlyRevenueRecord, ...]:
        source_reads.append(("monthly_revenue", stock_code, decision_date.isoformat()))
        order.append("monthly_revenue")
        return (
            MonthlyRevenueRecord(
                stock_code=stock_code,
                period="2025-04",
                as_of_date=date(2025, 4, 30),
                raw_date=date(2025, 5, 10),
                announced_date=date(2025, 5, 10),
                available_date=date(2025, 5, 10),
                revenue=Decimal("100"),
                source="synthetic-r019",
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
                source="synthetic-r019",
                source_version="v1",
            ),
        )

    fundamental_provider.load_pe = read_pe
    fundamental_provider.load_monthly_revenues = read_monthly_revenues

    industry_mapper.get_stock_industries.side_effect = (
        lambda _code: order.append("industry_mapper") or ["半導體業"]
    )
    industry_mapper.get_industry_performance.side_effect = (
        lambda _industry, date: order.append("industry_performance")
        or (
            None
            if industry_percent is None
            else {"漲跌百分比": industry_percent}
        )
    )
    service.reason_engine.generate_reasons = (
        lambda _row, _config: order.append("reason_engine")
        or [dict(reason) for reason in base_reasons]
    )
    formatter = service.reason_engine.format_reason_text
    formatted_inputs: list[list[dict[str, object]]] = []

    def capture_formatter_input(
        reasons: list[dict[str, object]], max_reasons: int | None = 4
    ) -> str:
        formatted_inputs.append([dict(reason) for reason in reasons])
        return formatter(reasons, max_reasons=max_reasons)

    service.reason_engine.format_reason_text = capture_formatter_input
    return service, industry_mapper, pit_reader, source_reads, (order, formatted_inputs)


def _run(
    service: RecommendationService,
    monkeypatch: pytest.MonkeyPatch,
    *,
    result_id: str,
    explicit_cutoff: bool = False,
    regime: object | None = "Trend",
) -> tuple[Any, RecommendationBodyResult, dict[str, Any]]:
    captured: dict[str, RecommendationBodyResult] = {}
    original = RecommendationService._run_recommendation_body_result

    def track_body_result(invocation: RecommendationService, **kwargs: Any):
        body_result = original(invocation, **kwargs)
        assert type(body_result) is RecommendationBodyResult
        captured[str(kwargs.get("result_id"))] = body_result
        return body_result

    monkeypatch.setattr(
        RecommendationService, "_run_recommendation_body_result", track_body_result
    )
    capture_sink: dict[str, Any] = {}
    runtime_config: dict[str, Any] = {
        "profile_id": "r019-reason-regime-profile",
        "profile_version": "1",
        "recommendation_ranking": {"threshold_mode": "fixed"},
        "run_id": result_id,
        "filters": {
            "pe_ratio_max": "15",
            "monthly_revenue_yoy_min": "0",
        },
    }
    if regime is not None:
        runtime_config["regime"] = regime
    if explicit_cutoff:
        runtime_config["as_of_date"] = CUTOFF.isoformat()
        runtime_config["pit_decision_at"] = "2026-05-20T16:00:00+08:00"
        runtime_config["filters"]["industry"] = "半導體業"
    execution = execute_recommendation(
        service,
        runtime_config,
        top_n=1,
        as_of_date=CUTOFF if explicit_cutoff else None,
        result_id=result_id,
        capture_sink=capture_sink,
    )
    body_result = captured[result_id]
    return execution, body_result, capture_sink


@pytest.mark.parametrize(
    (
        "industry_percent",
        "expected_text",
        "expected_tags",
        "expected_evidence",
        "expected_contribution",
    ),
    [
        (
            "1.50%",
            "基本理由+、半導體業指數上漲+",
            ("基本理由", "半導體業指數上漲"),
            "半導體業類指數漲幅 1.50%",
            0.75,
        ),
        (
            Decimal("0.00"),
            "基本理由+",
            ("基本理由",),
            None,
            None,
        ),
        (
            Decimal("-1.50"),
            "基本理由+",
            ("基本理由",),
            None,
            None,
        ),
        (0.0, "基本理由+", ("基本理由",), None, None),
        ("0.00%", "基本理由+", ("基本理由",), None, None),
        (-1.5, "基本理由+", ("基本理由",), None, None),
        ("-1.50%", "基本理由+", ("基本理由",), None, None),
        ("不是百分比", "基本理由+", ("基本理由",), None, None),
        (
            21.0,
            "基本理由+、半導體業指數上漲+",
            ("基本理由", "半導體業指數上漲"),
            "半導體業類指數漲幅 21.00%",
            10.0,
        ),
        (
            2.675,
            "基本理由+、半導體業指數上漲+",
            ("基本理由", "半導體業指數上漲"),
            "半導體業類指數漲幅 2.67%",
            1.3375,
        ),
    ],
)
def test_industry_reason_legacy_text_tags_order_and_source_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    industry_percent: object,
    expected_text: str,
    expected_tags: tuple[str, ...],
    expected_evidence: str | None,
    expected_contribution: float | None,
) -> None:
    service, mapper, _pit_reader, source_reads, captures = _build_service(
        tmp_path, industry_percent=industry_percent
    )
    order, formatted_inputs = captures
    result_id = f"r019-reason-{str(industry_percent).replace('%', 'pct')}"

    execution, body, capture = _run(
        service, monkeypatch, result_id=result_id
    )

    assert execution.status.value == "completed"
    assert len(execution.decision.items) == 1  # type: ignore[union-attr]
    assert source_reads == [
        ("pe", "2330", CUTOFF.isoformat()),
        ("monthly_revenue", "2330", CUTOFF.isoformat()),
    ]
    assert order == [
        "pe",
        "monthly_revenue",
        "industry_mapper",
        "reason_engine",
        "industry_performance",
    ]
    mapper.filter_stocks_by_industry.assert_not_called()
    mapper.get_industry_performance.assert_called_once_with(
        "半導體業", date=CUTOFF.isoformat()
    )
    industry_reasons = [
        reason
        for reason in formatted_inputs[0]
        if reason.get("tag") == "半導體業指數上漲"
    ]
    if expected_evidence is None:
        assert industry_reasons == []
    else:
        assert industry_reasons == [
            {
                "tag": "半導體業指數上漲",
                "evidence": expected_evidence,
                "score_contrib": expected_contribution,
            }
        ]

    dto = capture["legacy_recommendations"][0]
    item = execution.decision.items[0]  # type: ignore[union-attr]
    assert dto.recommendation_reasons == expected_text
    assert item.reason_text == expected_text
    assert item.reasons == expected_tags
    assert body.legacy_recommendations[0].field_value("recommendation_reasons") == expected_text
    assert body.legacy_recommendations[0].field_value("regime_match") is True
    assert item.regime_match is True
    assert body.context.temporal_mode == "natural_producer_clock"
    assert execution.decision is body.decision


def test_service_keeps_all_saved_reasons_and_three_reason_legacy_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_reasons = (
        {"tag": "理由甲", "evidence": "a", "score_contrib": 1},
        {"tag": "理由乙", "evidence": "b", "score_contrib": -1},
        {"tag": "理由丙", "evidence": "c", "score_contrib": 0},
        {"tag": "理由丁", "evidence": "d", "score_contrib": 2},
        {"tag": "理由戊", "evidence": "e", "score_contrib": 0},
    )
    service, _mapper, _pit_reader, _reads, captures = _build_service(
        tmp_path,
        industry_percent="1.50%",
        base_reasons=base_reasons,
    )
    _order, formatted_inputs = captures
    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id="r019-reason-explicit-cutoff-full",
        explicit_cutoff=True,
    )

    expected_summary = "理由甲+、理由乙-、理由丙"
    expected_detail = "理由甲+、理由乙-、理由丙、理由丁+、理由戊"
    expected_tags = ("理由甲", "理由乙", "理由丙", "理由丁", "理由戊")
    reason_rows = formatted_inputs[0]
    assert len(formatted_inputs) == 1
    assert reason_rows == list(base_reasons)
    assert len(reason_rows) == 5
    assert execution.status.value == "completed"
    assert len(execution.decision.items) == 1  # type: ignore[union-attr]
    assert capture["legacy_recommendations"][0].recommendation_reasons == expected_detail
    assert execution.decision.items[0].reason_text == expected_detail  # type: ignore[union-attr]
    assert execution.decision.items[0].reasons == expected_tags  # type: ignore[union-attr]
    assert body.legacy_recommendations[0].field_value("recommendation_reasons") == expected_detail

    # 新保存版本與舊版截短文字都經公開 sealed codec 重開，保留原始 tag。
    current_payload = encode_execution(execution)
    current_replay = decode_execution(current_payload)
    assert encode_execution(current_replay) == current_payload
    assert current_replay.decision is not None
    assert current_replay.decision.items[0].reason_text == expected_detail
    assert current_replay.decision.items[0].reasons == expected_tags

    historical_item = replace(
        current_replay.decision.items[0], reason_text=expected_summary
    )
    historical_batch = replace(
        current_replay.decision, items=(historical_item,)
    )
    historical_execution = replace(current_replay, decision=historical_batch)
    historical_payload = encode_execution(historical_execution)
    historical_replay = decode_execution(historical_payload)
    assert encode_execution(historical_replay) == historical_payload
    assert historical_replay.decision is not None
    assert historical_replay.decision.items[0].reason_text == expected_summary
    assert historical_replay.decision.items[0].reasons == expected_tags


def test_explicit_cutoff_uses_pit_filter_without_current_industry_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, mapper, pit_reader, _reads, captures = _build_service(
        tmp_path, industry_percent="1.50%"
    )
    _order, _formatted_inputs = captures

    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id="r019-explicit-no-current-industry-fallback",
        explicit_cutoff=True,
    )

    assert execution.status.value == "completed"
    assert [item.stock_code for item in execution.decision.items] == ["2330"]  # type: ignore[union-attr]
    pit_reader.read.assert_called_once_with(
        as_of_date=CUTOFF,
        decision_at="2026-05-20T16:00:00+08:00",
        market_scope="twse_listed",
    )
    mapper.filter_stocks_by_industry.assert_not_called()
    mapper.get_stock_industries.assert_not_called()
    mapper.get_industry_performance.assert_not_called()
    assert capture["legacy_recommendations"][0].industry == "未知"
    assert body.decision.items[0].industry == "未知"


def test_no_decision_date_keeps_legacy_malformed_industry_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, mapper, _pit_reader, _reads, captures = _build_service(
        tmp_path, industry_percent="不是百分比"
    )
    order, formatted_inputs = captures
    input_session = service.recommendation_input_preparer.begin(service.config)
    prepared = PreparedRecommendationMarket(
        frame=service.market_data_provider(),
        stock_column="證券代號",
        decision_cutoff="",
        source_id="synthetic-no-decision-date",
        market_data_fingerprint="a" * 64,
        data_date="",
    )
    monkeypatch.setattr(
        input_session,
        "prepare_market",
        lambda *, cutoff, universe=None: prepared,
    )

    body = service._run_recommendation_body_result(
        {"filters": {}},
        result_id="r019-no-date-malformed-industry",
        input_session=input_session,
    )

    assert type(body) is RecommendationBodyResult
    recommendations = [
        snapshot.materialize() for snapshot in body.legacy_recommendations
    ]
    assert len(recommendations) == 1
    assert order == ["industry_mapper", "reason_engine", "industry_performance"]
    mapper.get_industry_performance.assert_called_once_with("半導體業", date="")
    assert formatted_inputs == [[_BASE_REASONS[0]]]
    assert recommendations[0].recommendation_reasons == "基本理由+"
    assert body.decision.items[0].reason_text == "基本理由+"
    assert body.legacy_recommendations[0].field_value(
        "recommendation_reasons"
    ) == "基本理由+"


@pytest.mark.parametrize(
    ("final_score", "expected_match"),
    [
        (Decimal("83.99"), False),
        (Decimal("84.00"), False),
        (Decimal("84.01"), True),
    ],
)
def test_regime_match_uses_strict_one_point_zero_five_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_score: Decimal,
    expected_match: bool,
) -> None:
    service, _mapper, _pit_reader, _reads, _captures = _build_service(
        tmp_path,
        industry_percent=None,
        final_score=final_score,
        total_score=Decimal("80.00"),
    )
    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id=f"r019-regime-{final_score}",
    )

    assert execution.decision.items[0].regime_match is expected_match  # type: ignore[union-attr]
    assert capture["legacy_recommendations"][0].regime_match is expected_match
    assert body.legacy_recommendations[0].field_value("regime_match") is expected_match
    assert body.decision.items[0].regime_match is expected_match
    assert execution.decision is body.decision


def test_regime_match_is_false_when_regime_is_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _mapper, _pit_reader, _reads, _captures = _build_service(
        tmp_path,
        industry_percent=None,
        final_score=Decimal("84.01"),
        total_score=None,
    )
    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id="r019-regime-disabled",
        regime=None,
    )

    assert execution.decision.items[0].regime_match is False  # type: ignore[union-attr]
    assert capture["legacy_recommendations"][0].regime_match is False
    assert body.legacy_recommendations[0].field_value("regime_match") is False


def test_missing_total_score_column_uses_legacy_zero_default_for_regime_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _mapper, _pit_reader, _reads, _captures = _build_service(
        tmp_path,
        industry_percent=None,
        final_score=Decimal("84.01"),
        include_total_score=False,
    )
    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id="r019-regime-total-score-column-missing",
    )

    assert execution.decision.items[0].regime_match is True  # type: ignore[union-attr]
    assert capture["legacy_recommendations"][0].regime_match is True
    assert body.legacy_recommendations[0].field_value("regime_match") is True


def test_present_null_total_score_keeps_legacy_regime_conversion_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _mapper, _pit_reader, _reads, _captures = _build_service(
        tmp_path,
        industry_percent=None,
        final_score=Decimal("84.01"),
        total_score=None,
    )
    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id="r019-regime-total-score-null",
    )

    assert execution.status.value == "completed"
    assert execution.decision.items == ()  # type: ignore[union-attr]
    disposition = body.dispositions[0]
    assert disposition.status == "degraded"
    assert disposition.reason_codes == ("screening_exception",)
    assert disposition.warnings == ("screening_exception:InvalidOperation",)
    assert "ConversionSyntax" in disposition.observed_value
    assert capture["compatibility_snapshot"].materialize()["last_screening_matrix"][0]["reason_codes"] == [
        "screening_exception"
    ]


@pytest.mark.parametrize(
    ("final_score", "expected_status", "expected_quality", "expected_reason"),
    [
        (None, "missing", "missing", "total_score_missing_or_nonfinite"),
        (Decimal("NaN"), "missing", "missing", "total_score_missing_or_nonfinite"),
        (
            Decimal("Infinity"),
            "missing",
            "missing",
            "total_score_missing_or_nonfinite",
        ),
        ("not-a-score", "degraded", "degraded", "screening_exception"),
    ],
)
def test_missing_nonfinite_or_unparsable_score_keeps_legacy_matrix_disposition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_score: object,
    expected_status: str,
    expected_quality: str,
    expected_reason: str,
) -> None:
    service, _mapper, _pit_reader, _reads, _captures = _build_service(
        tmp_path,
        industry_percent="1.50%",
        final_score=final_score,
    )
    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id=f"r019-score-missing-{final_score}",
    )

    assert execution.status.value == "completed"
    assert execution.decision.items == ()  # type: ignore[union-attr]
    assert capture["legacy_recommendations"] == []
    disposition = body.dispositions[0]
    assert disposition.status == expected_status
    assert disposition.quality == expected_quality
    assert disposition.stage == "strategy_evaluation"
    assert disposition.reason_codes == (expected_reason,)
    if expected_status == "missing":
        assert body.decision.assessments[0].eligible is None
    else:
        assert disposition.warnings == ("screening_exception:InvalidOperation",)
    matrix_row = capture["compatibility_snapshot"].materialize()["last_screening_matrix"][0]
    assert matrix_row["status"] == expected_status
    assert matrix_row["quality"] == expected_quality
    assert matrix_row["stage"] == "strategy_evaluation"
    assert matrix_row["reason_codes"] == [expected_reason]


def test_decimal_industry_percent_preserves_legacy_type_error_as_degraded_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _mapper, _pit_reader, _reads, _captures = _build_service(
        tmp_path,
        industry_percent=Decimal("1.50"),
    )
    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id="r019-decimal-industry-percent-type-error",
    )

    assert execution.status.value == "completed"
    assert execution.decision.items == ()  # type: ignore[union-attr]
    disposition = body.dispositions[0]
    assert disposition.status == "degraded"
    assert disposition.quality == "degraded"
    assert disposition.stage == "strategy_evaluation"
    assert disposition.reason_codes == ("screening_exception",)
    assert disposition.warnings == ("screening_exception:TypeError",)
    assert "Decimal" in disposition.observed_value
    matrix_row = capture["compatibility_snapshot"].materialize()["last_screening_matrix"][0]
    assert matrix_row["status"] == "degraded"
    assert matrix_row["reason_codes"] == ["screening_exception"]


def test_late_malformed_final_score_does_not_override_earlier_reason_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _mapper, _pit_reader, _source_reads, captures = _build_service(
        tmp_path,
        industry_percent=None,
        final_score="not-a-score",
        total_score=Decimal("80.00"),
    )
    order, _formatted_inputs = captures

    def fail_reason_generation(
        _row: pd.Series, _config: dict[str, Any]
    ) -> list[dict[str, object]]:
        order.append("reason_engine")
        raise RuntimeError("synthetic reason failure")

    service.reason_engine.generate_reasons = fail_reason_generation
    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id="r019-final-score-late-error-priority",
    )

    assert execution.status.value == "completed"
    assert execution.decision.items == ()  # type: ignore[union-attr]
    assert capture["legacy_recommendations"] == []
    assert order == ["pe", "monthly_revenue", "industry_mapper", "reason_engine"]
    disposition = body.dispositions[0]
    assert disposition.status == "degraded"
    assert disposition.quality == "degraded"
    assert disposition.reason_codes == ("screening_exception",)
    assert disposition.warnings == ("screening_exception:RuntimeError",)
    assert disposition.observed_value == "synthetic reason failure"
    matrix_row = capture["compatibility_snapshot"].materialize()["last_screening_matrix"][0]
    assert matrix_row["status"] == "degraded"
    assert matrix_row["threshold_name"] == "RuntimeError"
    assert matrix_row["observed_value"] == "synthetic reason failure"
    assert matrix_row["warnings"] == ["screening_exception:RuntimeError"]


@pytest.mark.parametrize(
    ("score_field", "score_value", "expected_score", "expected_regime_match"),
    [
        ("TotalScore", Decimal("80.00"), Decimal("80.00"), False),
        ("綜合評分", Decimal("84.01"), Decimal("84.01"), True),
    ],
    ids=("total-score-fallback", "legacy-combined-score-fallback"),
)
def test_absent_final_score_keeps_legacy_score_fallback_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    score_field: str,
    score_value: Decimal,
    expected_score: Decimal,
    expected_regime_match: bool,
) -> None:
    service, _mapper, _pit_reader, _reads, _captures = _build_service(
        tmp_path,
        industry_percent=None,
    )
    service.strategy_configurator.generate_recommendations = (
        lambda _stock_frame, _runtime_config: pd.DataFrame(
            {
                score_field: [score_value],
                "收盤價": [Decimal("100.00")],
            }
        )
    )

    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id=f"r019-score-fallback-{score_field}",
    )

    assert execution.status.value == "completed"
    assert execution.decision is body.decision
    assert len(execution.decision.items) == 1  # type: ignore[union-attr]
    dto = capture["legacy_recommendations"][0]
    item = body.decision.items[0]
    assert type(dto.total_score) is Decimal
    assert dto.total_score == expected_score
    assert type(item.rule_score) is Decimal
    assert item.rule_score == expected_score
    assert item.regime_match is expected_regime_match
    matrix_row = capture["compatibility_snapshot"].materialize()["last_screening_matrix"][0]
    assert matrix_row["status"] == "pass"
    assert matrix_row["total_score"] == str(expected_score)
    assert matrix_row["reason_codes"] == ["recommendation_selected"]
