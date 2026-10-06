"""R002 frozen behavior oracle for RecommendationService's public result boundary."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
import numpy as np

from app_module.recommendation_service import RecommendationService
from recommendation_test_support import build_recommendation_test_preparer
from data_module.fundamental_schema import apply_fundamental_schema


DECISION_DATE = "2026-05-20"
MATRIX_FIELDS = (
    "stock_code",
    "stock_name",
    "status",
    "reason_codes",
    "quality",
    "stage",
    "threshold_name",
    "observed_value",
    "required_value",
    "total_score",
    "score_bp",
    "score_percentile_bp",
    "eligible_universe_size",
    "threshold_mode",
    "warnings",
    "industry",
    "as_of_date",
)


class _FrameProvider:
    """Tiny market-source fixture; it never reads configured or formal data."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def __call__(self) -> pd.DataFrame:
        return self.frame.copy(deep=True)


def _market_frame(
    codes: tuple[str, ...],
    *,
    periods: int = 20,
    latest_volume: dict[str, int] | None = None,
) -> pd.DataFrame:
    dates = pd.date_range("2026-05-01", periods=periods, freq="D")
    rows: list[dict[str, object]] = []
    for code in codes:
        for index, current_date in enumerate(dates):
            volume = 1000
            if index == periods - 1 and latest_volume and code in latest_volume:
                volume = latest_volume[code]
            rows.append(
                {
                    "日期": current_date,
                    "available_date": current_date,
                    "證券代號": code,
                    "證券名稱": f"{code}_NAME",
                    "收盤價": Decimal("100.00"),
                    "成交股數": volume,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "日期",
            "available_date",
            "證券代號",
            "證券名稱",
            "收盤價",
            "成交股數",
        ],
    )


def _service(
    tmp_path: Path,
    codes: tuple[str, ...],
    scores: dict[str, object],
    *,
    periods: int = 20,
    latest_volume: dict[str, int] | None = None,
    empty_codes: tuple[str, ...] = (),
    errors: dict[str, Exception] | None = None,
    db_file: Path | None = None,
    pit_reader: object | None = None,
) -> tuple[RecommendationService, list[str]]:
    """Build a deterministic service with only per-test local inputs."""
    frame = _market_frame(codes, periods=periods, latest_volume=latest_volume)
    config = SimpleNamespace(
        db_file=db_file if db_file is not None else tmp_path / "missing-fundamentals.db",
        use_sqlite=False,
        pit_market_scope="twse_listed",
    )
    industry_mapper = MagicMock()
    industry_mapper.get_stock_industries.return_value = []
    market_data_provider = _FrameProvider(frame)
    service = RecommendationService(
        config,
        industry_mapper=industry_mapper,
        market_data_provider=market_data_provider,
        regime_detector=MagicMock(),
        calibration_consumer=None,
        pit_membership_reader=pit_reader,
        input_preparer=build_recommendation_test_preparer(
            config,
            market_data_provider=market_data_provider,
            pit_membership_reader=pit_reader,
        ),
    )
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.return_value = []
    service.reason_engine.format_reason_text.return_value = ""
    calls: list[str] = []
    error_by_code = errors or {}

    def generate(stock_frame: pd.DataFrame, _config: dict[str, object]) -> pd.DataFrame:
        code = str(stock_frame.iloc[-1]["證券代號"])
        calls.append(code)
        if code in error_by_code:
            raise error_by_code[code]
        if code in empty_codes:
            return pd.DataFrame()
        score = scores[code]
        return pd.DataFrame(
            {
                "FinalScore": [score],
                "TotalScore": [score],
                "收盤價": [Decimal("100.00")],
            }
        )

    service.strategy_configurator.generate_recommendations = generate
    return service, calls


def _matrix_projection(row: dict[str, object]) -> dict[str, object]:
    """Compare named semantic columns; fingerprints are checked separately."""
    return {field: row[field] for field in MATRIX_FIELDS}


def _matrix_by_code(service: RecommendationService) -> dict[str, dict[str, object]]:
    return {row["stock_code"]: row for row in service.last_screening_matrix}


def _negative_codes(service: RecommendationService) -> list[str]:
    return [row["stock_code"] for row in service.last_why_not_payload_json]


def test_fixed_mode_locks_processing_order_decimal_quantum_float_boundary_and_rule_only_output(
    tmp_path: Path,
) -> None:
    codes = ("TIE_B", "HIGH", "TIE_A", "LOW")
    service, calls = _service(
        tmp_path,
        codes,
        {
            "TIE_B": Decimal("70.0100"),
            "HIGH": 91.5,
            "TIE_A": Decimal("70.0100"),
            "LOW": Decimal("30.00"),
        },
    )

    recommendations = service.run_recommendation(
        {"profile_id": "r002-fixture", "recommendation_ranking": {"threshold_mode": "fixed"}},
        top_n=3,
        as_of_date=DECISION_DATE,
        result_id="r002-fixed-001",
    )

    assert calls == ["TIE_B", "HIGH", "TIE_A", "LOW"]
    assert [item.stock_code for item in recommendations] == ["HIGH", "TIE_B", "TIE_A"]
    assert type(recommendations[0].total_score) is np.float64
    assert recommendations[0].total_score == 91.5
    assert type(recommendations[1].total_score) is Decimal
    assert str(recommendations[1].total_score) == "70.0100"
    assert str(recommendations[2].total_score) == "70.0100"
    assert all(item.threshold_mode == "fixed" for item in recommendations)
    assert all(item.score_percentile_bp is None for item in recommendations)
    assert all(item.ranking_score_bp is None for item in recommendations)
    assert all(item.calibrated_probability_bp is None for item in recommendations)
    assert all(item.calibration_status == "unavailable" for item in recommendations)
    assert [
        (
            item.stock_code,
            item.stock_name,
            str(item.close_price),
            item.price_change,
            str(item.total_score),
            type(item.total_score).__name__,
            item.indicator_score,
            item.pattern_score,
            item.volume_score,
            item.recommendation_reasons,
            item.industry,
            item.regime_match,
            item.score_percentile_bp,
            item.eligible_universe_size,
            item.eligible_universe_date,
            item.ranking_method,
            item.threshold_mode,
        )
        for item in recommendations
    ] == [
        (
            "HIGH", "HIGH_NAME", "100.00", 0.0, "91.5", "float64", 0, 0, 0,
            "", "未知", False, None, 4, DECISION_DATE, "fixed", "fixed",
        ),
        (
            "TIE_B", "TIE_B_NAME", "100.00", 0.0, "70.0100", "Decimal", 0, 0, 0,
            "", "未知", False, None, 4, DECISION_DATE, "fixed", "fixed",
        ),
        (
            "TIE_A", "TIE_A_NAME", "100.00", 0.0, "70.0100", "Decimal", 0, 0, 0,
            "", "未知", False, None, 4, DECISION_DATE, "fixed", "fixed",
        ),
    ]

    matrix = _matrix_by_code(service)
    assert [_matrix_projection(matrix[code]) for code in codes] == [
        {
            "stock_code": "TIE_B",
            "stock_name": "TIE_B_NAME",
            "status": "pass",
            "reason_codes": ["recommendation_selected"],
            "quality": "observed",
            "stage": "final_selection",
            "threshold_name": "",
            "observed_value": "",
            "required_value": "",
            "total_score": "70.0100",
            "score_bp": None,
            "score_percentile_bp": None,
            "eligible_universe_size": None,
            "threshold_mode": "fixed",
            "warnings": [],
            "industry": "未知",
            "as_of_date": DECISION_DATE,
        },
        {
            "stock_code": "HIGH",
            "stock_name": "HIGH_NAME",
            "status": "pass",
            "reason_codes": ["recommendation_selected"],
            "quality": "observed",
            "stage": "final_selection",
            "threshold_name": "",
            "observed_value": "",
            "required_value": "",
            "total_score": "91.5",
            "score_bp": None,
            "score_percentile_bp": None,
            "eligible_universe_size": None,
            "threshold_mode": "fixed",
            "warnings": [],
            "industry": "未知",
            "as_of_date": DECISION_DATE,
        },
        {
            "stock_code": "TIE_A",
            "stock_name": "TIE_A_NAME",
            "status": "pass",
            "reason_codes": ["recommendation_selected"],
            "quality": "observed",
            "stage": "final_selection",
            "threshold_name": "",
            "observed_value": "",
            "required_value": "",
            "total_score": "70.0100",
            "score_bp": None,
            "score_percentile_bp": None,
            "eligible_universe_size": None,
            "threshold_mode": "fixed",
            "warnings": [],
            "industry": "未知",
            "as_of_date": DECISION_DATE,
        },
        {
            "stock_code": "LOW",
            "stock_name": "LOW_NAME",
            "status": "fail",
            "reason_codes": ["recommendation_outside_top_n"],
            "quality": "observed",
            "stage": "top_n_gate",
            "threshold_name": "top_n",
            "observed_value": "4",
            "required_value": "3",
            "total_score": "30.00",
            "score_bp": None,
            "score_percentile_bp": None,
            "eligible_universe_size": None,
            "threshold_mode": "fixed",
            "warnings": [],
            "industry": "未知",
            "as_of_date": DECISION_DATE,
        },
    ]
    assert _negative_codes(service) == ["LOW"]
    assert service.last_excluded_candidates_json == [
        {
            "stock_code": "LOW",
            "stock_name": "LOW_NAME",
            "status": "fail",
            "reason_codes": ["recommendation_outside_top_n"],
            "quality": "observed",
        }
    ]
    assert service.last_liquidity_gate_payload_json == []
    assert service.last_exclusion_quality == "observed"
    assert service.last_exclusion_warnings_json == ["screening_matrix_persisted_v1"]

    context = service.last_run_context
    assert context["result_id"] == "r002-fixed-001"
    assert context["schema_version"] == "recommendation-context.v1"
    assert context["as_of_date"] == DECISION_DATE
    assert context["data_date"] == DECISION_DATE
    assert context["profile_id"] == "r002-fixture"
    assert context["temporal_mode"] == "explicit_cutoff_not_natural"
    assert context["cutoff_selection"] == "caller_requested_cutoff"
    assert context["cutoff_policy"] == "caller_explicit_cutoff_not_natural"
    assert context["eligible_universe_size"] == 4
    assert context["universe_spec"]["selected_codes"] == sorted(codes)
    assert context["universe_spec"]["selection_mode"] == "top_max_stocks"
    assert context["warnings"] == ["industry_membership_not_point_in_time"]
    assert context["source_id"] == "_FrameProvider"
    assert context["market_data_fingerprint"] == "750d37566806ba77e4ee22ed23a7920634ce6fbff2ec25d83baa74eccdb4f6a6"
    assert context["data_fingerprint"] == "a420fe3f5b9d2c871132a9e6c8b42432c895b8ffb5718cc965f9dfc215f71d21"
    assert context["universe_id"] == (
        "recommendation-universe-v1:"
        "c3f23d0750e34e732e928cc0ec999839a228ad472ce5a929407fea1c8a14fa75"
    )
    assert context["universe_hash"] == "sha256:c3f23d0750e34e732e928cc0ec999839a228ad472ce5a929407fea1c8a14fa75"
    assert context["universe_policy_id"] == (
        "recommendation-universe-policy-v1:"
        "114c8343a6c748975fcb6506e124ca403c22603bc0f4ca5ae3e4cdc1fba6f3dd"
    )
    assert context["universe_policy_hash"] == "sha256:114c8343a6c748975fcb6506e124ca403c22603bc0f4ca5ae3e4cdc1fba6f3dd"
    assert context["universe_snapshot_id"] == (
        "recommendation-universe-snapshot-v1:"
        "c3f23d0750e34e732e928cc0ec999839a228ad472ce5a929407fea1c8a14fa75"
    )
    assert context["universe_snapshot_hash"] == (
        "sha256:c3f23d0750e34e732e928cc0ec999839a228ad472ce5a929407fea1c8a14fa75"
    )
    assert context["data_fingerprint"] == matrix["LOW"]["data_fingerprint"]
    assert matrix["LOW"]["data_fingerprint"] == service.last_why_not_payload_json[0]["data_fingerprint"]
    decision_at = datetime.fromisoformat(context["decision_at"])
    assert decision_at.utcoffset() == timezone.utc.utcoffset(decision_at)


def test_quantile_mode_locks_half_up_rounding_percentiles_and_code_tie_break(tmp_path: Path) -> None:
    codes = ("Q50D", "Q90", "Q20", "Q50B", "Q50A", "Q50C")
    service, _ = _service(
        tmp_path,
        codes,
        {
            "Q50C": Decimal("50.0051"),
            "Q90": Decimal("90.0000"),
            "Q20": Decimal("20.0000"),
            "Q50B": Decimal("50.0050"),
            "Q50A": Decimal("50.0049"),
            "Q50D": Decimal("50.0050"),
        },
    )

    recommendations = service.run_recommendation(
        {
            "recommendation_ranking": {
                "threshold_mode": "quantile",
                "recommendation_min_percentile_bp": 8000,
                "recommendation_min_universe_size": 6,
                "recommendation_ranking_method": "nearest_rank",
            }
        },
        top_n=3,
        as_of_date=DECISION_DATE,
        result_id="r002-quantile-001",
    )

    assert [item.stock_code for item in recommendations] == ["Q90", "Q50C", "Q50B"]
    assert [
        (item.score_percentile_bp, item.eligible_universe_size, item.ranking_method)
        for item in recommendations
    ] == [
        (10000, 6, "nearest_rank"),
        (8334, 6, "nearest_rank"),
        (8334, 6, "nearest_rank"),
    ]
    assert [item.eligible_universe_date for item in recommendations] == [DECISION_DATE] * 3
    assert [str(item.total_score) for item in recommendations] == ["90.0000", "50.0051", "50.0050"]

    matrix = _matrix_by_code(service)
    assert {
        code: (
            matrix[code]["score_percentile_bp"],
            matrix[code]["status"],
            matrix[code]["stage"],
            matrix[code]["reason_codes"],
        )
        for code in codes
    } == {
        "Q50C": (8334, "pass", "final_selection", ["recommendation_selected"]),
        "Q90": (10000, "pass", "final_selection", ["recommendation_selected"]),
        "Q20": (1667, "fail", "threshold_gate", ["recommendation_percentile_below_min"]),
        "Q50B": (8334, "pass", "final_selection", ["recommendation_selected"]),
        "Q50A": (3334, "fail", "threshold_gate", ["recommendation_percentile_below_min"]),
        "Q50D": (8334, "fail", "top_n_gate", ["recommendation_outside_top_n"]),
    }
    assert matrix["Q50D"]["threshold_name"] == "top_n"
    assert (matrix["Q50D"]["observed_value"], matrix["Q50D"]["required_value"]) == ("4", "3")
    assert matrix["Q50A"]["threshold_name"] == "recommendation_min_percentile_bp"
    assert (matrix["Q50A"]["observed_value"], matrix["Q50A"]["required_value"]) == ("3334", "8000")
    assert _negative_codes(service) == ["Q50D", "Q20", "Q50A"]
    assert service.last_run_context["result_id"] == "r002-quantile-001"
    assert service.last_run_context["eligible_universe_size"] == 6


@pytest.mark.parametrize("missing_score", [None, Decimal("NaN"), Decimal("Infinity")])
def test_missing_score_remains_unknown_and_is_not_ranked_as_zero(
    tmp_path: Path, missing_score: object
) -> None:
    service, _ = _service(
        tmp_path,
        ("GOOD", "UNKNOWN"),
        {"GOOD": Decimal("60.00"), "UNKNOWN": missing_score},
    )

    recommendations = service.run_recommendation(
        {}, as_of_date=DECISION_DATE, result_id="r002-missing-001"
    )

    assert [item.stock_code for item in recommendations] == ["GOOD"]
    row = _matrix_by_code(service)["UNKNOWN"]
    assert _matrix_projection(row) == {
        "stock_code": "UNKNOWN",
        "stock_name": "UNKNOWN_NAME",
        "status": "missing",
        "reason_codes": ["total_score_missing_or_nonfinite"],
        "quality": "missing",
        "stage": "strategy_evaluation",
        "threshold_name": "",
        "observed_value": "",
        "required_value": "",
        "total_score": "",
        "score_bp": None,
        "score_percentile_bp": None,
        "eligible_universe_size": None,
        "threshold_mode": "fixed",
        "warnings": [],
        "industry": "",
        "as_of_date": DECISION_DATE,
    }
    assert _negative_codes(service) == ["UNKNOWN"]
    assert service.last_exclusion_quality == "degraded"
    assert service.last_exclusion_warnings_json == [
        "screening_matrix_persisted_v1",
        "screening_contains_unknown_evidence",
    ]
    assert service.last_run_context["result_id"] == "r002-missing-001"


def test_empty_input_and_partial_stock_degradation_keep_distinct_negative_evidence(
    tmp_path: Path,
) -> None:
    empty_service, _ = _service(tmp_path, (), {})
    assert empty_service.run_recommendation(
        {}, as_of_date=DECISION_DATE, result_id="r002-empty-001"
    ) == []
    assert empty_service.last_run_context["eligible_universe_size"] == 0
    assert empty_service.last_run_context["result_id"] == "r002-empty-001"
    assert empty_service.last_screening_matrix == []
    assert empty_service.last_why_not_payload_json == []

    codes = ("PASS", "NO_SIGNAL", "BROKEN", "SHORT")
    service, calls = _service(
        tmp_path,
        codes,
        {"PASS": 80.0, "NO_SIGNAL": 70.0, "BROKEN": 60.0},
        periods=20,
        latest_volume={"NO_SIGNAL": 1200},
        empty_codes=("NO_SIGNAL",),
        errors={"BROKEN": RuntimeError("fixture source failure")},
    )
    short_rows = _market_frame(("SHORT",), periods=19)
    full_rows = _market_frame(
        ("PASS", "NO_SIGNAL", "BROKEN"), latest_volume={"NO_SIGNAL": 1200}
    )
    service.market_data_provider = _FrameProvider(pd.concat([full_rows, short_rows], ignore_index=True))

    recommendations = service.run_recommendation(
        {"filters": {"min_volume_ratio": "1.5"}},
        top_n=1,
        as_of_date=DECISION_DATE,
        result_id="r002-partial-001",
    )

    assert [item.stock_code for item in recommendations] == ["PASS"]
    assert calls == ["PASS", "NO_SIGNAL", "BROKEN"]
    matrix = _matrix_by_code(service)
    assert {
        code: (matrix[code]["status"], matrix[code]["reason_codes"], matrix[code]["quality"])
        for code in codes
    } == {
        "PASS": ("pass", ["recommendation_selected"], "observed"),
        "NO_SIGNAL": ("skipped", ["liquidity_volume_ratio_below_min"], "degraded"),
        "BROKEN": ("degraded", ["screening_exception"], "degraded"),
        "SHORT": ("missing", ["insufficient_history"], "missing"),
    }
    assert matrix["NO_SIGNAL"]["stage"] == "strategy_evaluation"
    assert matrix["NO_SIGNAL"]["threshold_name"] == "liquidity.volume_ratio_min"
    assert (matrix["NO_SIGNAL"]["observed_value"], matrix["NO_SIGNAL"]["required_value"]) == ("20", "50")
    assert matrix["BROKEN"]["warnings"] == ["screening_exception:RuntimeError"]
    assert matrix["SHORT"]["observed_value"] == "19"
    assert matrix["SHORT"]["required_value"] == "20"
    assert _negative_codes(service) == ["NO_SIGNAL", "BROKEN", "SHORT"]
    assert [row["stock_code"] for row in service.last_liquidity_gate_payload_json] == ["NO_SIGNAL"]
    liquidity = service.last_liquidity_gate_payload_json[0]
    assert {
        key: liquidity[key]
        for key in (
            "stock_code",
            "status",
            "reason_codes",
            "observed_value",
            "required_value",
            "as_of_date",
        )
    } == {
        "stock_code": "NO_SIGNAL",
        "status": "skipped",
        "reason_codes": ["liquidity_volume_ratio_below_min"],
        "observed_value": "20",
        "required_value": "50",
        "as_of_date": DECISION_DATE,
    }
    assert service.last_exclusion_quality == "degraded"
    assert service.last_run_context["result_id"] == "r002-partial-001"


def test_pit_industry_filter_uses_verified_membership_and_fails_closed_when_unavailable(
    tmp_path: Path,
) -> None:
    pit_result = SimpleNamespace(
        industry_filter_usable=True,
        rows=(SimpleNamespace(symbol="PIT", industry_category="半導體業"),),
        lineage={"fixture_id": "pit-r002-v1"},
        status="accepted",
        quality="observed",
        warnings=(),
    )
    reader = SimpleNamespace(read=MagicMock(return_value=pit_result))
    service, calls = _service(tmp_path, ("OTHER", "PIT"), {"OTHER": 70.0, "PIT": 80.0}, pit_reader=reader)

    accepted = service.run_recommendation(
        {"filters": {"industry": "半導體業"}, "pit_decision_at": "2026-05-20T16:00:00+08:00"},
        as_of_date=DECISION_DATE,
        result_id="r002-pit-accepted-001",
    )
    assert [item.stock_code for item in accepted] == ["PIT"]
    assert calls == ["PIT"]
    assert service.last_run_context["industry_membership_status"] == "accepted"
    assert service.last_run_context["industry_membership"] == {"fixture_id": "pit-r002-v1"}
    assert service.last_run_context["warnings"] == ["industry_membership_pit_verified"]
    reader.read.assert_called_once_with(
        as_of_date=date(2026, 5, 20),
        decision_at="2026-05-20T16:00:00+08:00",
        market_scope="twse_listed",
    )

    blocked, blocked_calls = _service(tmp_path, ("OTHER", "PIT"), {"OTHER": 70.0, "PIT": 80.0})
    rejected = blocked.run_recommendation(
        {"filters": {"industry": "半導體業"}},
        as_of_date=DECISION_DATE,
        result_id="r002-pit-unavailable-001",
    )
    assert rejected == []
    assert blocked_calls == []
    assert [
        (row["stock_code"], row["status"], row["reason_codes"], row["stage"])
        for row in blocked.last_screening_matrix
    ] == [
        ("OTHER", "missing", ["industry_membership_pit_unavailable"], "universe_gate"),
        ("PIT", "missing", ["industry_membership_pit_unavailable"], "universe_gate"),
    ]
    assert blocked.last_run_context["warnings"] == ["industry_membership_not_point_in_time"]
    assert blocked.last_run_context["result_id"] == "r002-pit-unavailable-001"


def test_fundamental_filter_keeps_pit_values_and_marks_missing_database_as_unknown(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "fundamentals.db"
    with sqlite3.connect(db_file) as connection:
        apply_fundamental_schema(connection)
        connection.executemany(
            """
            INSERT INTO fundamental_valuation_metrics(
                stock_code, as_of_date, available_date, metric_name, value,
                source, source_version, quality
            ) VALUES (?, ?, ?, 'pe', ?, 'fixture', 'v1', 'observed')
            """,
            [
                ("AVAILABLE", "2026-05-19", "2026-05-19", "12.00"),
                ("FUTURE", "2026-05-19", "2026-05-21", "12.00"),
                ("TOO_HIGH", "2026-05-19", "2026-05-19", "20.00"),
            ],
        )
    service, calls = _service(
        tmp_path,
        ("AVAILABLE", "FUTURE", "TOO_HIGH"),
        {code: Decimal("80.00") for code in ("AVAILABLE", "FUTURE", "TOO_HIGH")},
        db_file=db_file,
    )

    recommendations = service.run_recommendation(
        {"filters": {"pe_ratio_max": "15"}},
        as_of_date=DECISION_DATE,
        result_id="r002-fundamental-001",
    )

    assert calls == ["AVAILABLE", "FUTURE", "TOO_HIGH"]
    assert [item.stock_code for item in recommendations] == ["AVAILABLE"]
    matrix = _matrix_by_code(service)
    assert (matrix["AVAILABLE"]["status"], matrix["AVAILABLE"]["reason_codes"]) == (
        "pass",
        ["recommendation_selected"],
    )
    assert (matrix["FUTURE"]["status"], matrix["FUTURE"]["reason_codes"], matrix["FUTURE"]["quality"]) == (
        "skipped",
        ["valuation_pe_missing"],
        "missing",
    )
    assert (
        matrix["TOO_HIGH"]["status"],
        matrix["TOO_HIGH"]["reason_codes"],
        matrix["TOO_HIGH"]["observed_value"],
        matrix["TOO_HIGH"]["required_value"],
    ) == (
        "skipped",
        ["valuation_pe_above_max"],
        "20.00",
        "15",
    )
    assert service.last_run_context["fundamental_inputs"] == [
        {
            "stock_code": "AVAILABLE",
            "metric": "pe",
            "value": "12.00",
            "as_of_date": "2026-05-19",
            "available_date": "2026-05-19",
            "source": "fixture",
            "source_version": "v1",
            "quality": "observed",
        },
        {
            "stock_code": "TOO_HIGH",
            "metric": "pe",
            "value": "20.00",
            "as_of_date": "2026-05-19",
            "available_date": "2026-05-19",
            "source": "fixture",
            "source_version": "v1",
            "quality": "observed",
        },
    ]
    assert _negative_codes(service) == ["FUTURE", "TOO_HIGH"]
    assert service.last_run_context["result_id"] == "r002-fundamental-001"

    missing_db = tmp_path / "unavailable-fundamentals.db"
    unavailable, _ = _service(
        tmp_path,
        ("NO_DB",),
        {"NO_DB": Decimal("80.00")},
        db_file=missing_db,
    )
    assert unavailable.run_recommendation(
        {"filters": {"pe_ratio_max": "15"}},
        as_of_date=DECISION_DATE,
        result_id="r002-fundamental-unavailable-001",
    ) == []
    assert not missing_db.exists()
    assert _matrix_by_code(unavailable)["NO_DB"]["reason_codes"] == ["valuation_pe_missing"]
    assert _matrix_by_code(unavailable)["NO_DB"]["quality"] == "missing"
    assert unavailable.last_run_context["result_id"] == "r002-fundamental-unavailable-001"
