"""純契約測試；合成封套不是實際來源、Registry run 或期間樣本。"""

from __future__ import annotations

from copy import deepcopy
from typing import TypedDict, cast

import pytest

from app_module.recommendation_portfolio_period_precision_v2 import (
    CompletionStatusV2,
    RecommendationPortfolioPeriodObservationV2,
    RecommendationPortfolioPeriodPrecisionV2,
    RecommendationPortfolioPeriodPrecisionV2Error,
    SourceQualityStatusV2,
)


class _PeriodArguments(TypedDict):
    registry_run_id: str
    portfolio_parent_id: str
    strategy_id: str
    strategy_version: str
    stock_code: str
    initial_capital_decimal: str
    currency_code: str | None
    minor_unit_exponent: int | None
    currency_authority: str | None
    source_fingerprint_sha256: str | None
    source_manifest_sha256: str | None
    source_raw_sha256: str | None
    equity_parquet_sha256: str | None
    trades_parquet_sha256: str | None
    source_cutoff_at: str | None
    source_available_at: str | None
    source_availability_basis: str | None
    source_quality_status: SourceQualityStatusV2
    session_calendar_id: str | None
    session_calendar_version: str | None
    session_calendar_sha256: str | None
    expected_session_dates: list[str] | tuple[str, ...] | None
    completion_status: CompletionStatusV2
    execution_contract_id: str
    execution_contract_version: str
    execution_contract_sha256: str | None
    cost_model_id: str
    cost_model_version: str
    cost_model_sha256: str | None
    observations: tuple[RecommendationPortfolioPeriodObservationV2, ...]


def _observation(
    session_date: str,
    *,
    stock_code: str = "2330",
    cash_decimal: str = "100.00",
    position_value_decimal: str = "0.00",
    equity_decimal: str = "100.00",
    realized_pnl_decimal: str | None = None,
    unrealized_pnl_decimal: str | None = None,
) -> RecommendationPortfolioPeriodObservationV2:
    return RecommendationPortfolioPeriodObservationV2(
        session_date=session_date,
        stock_code=stock_code,
        cash_decimal=cash_decimal,
        position_value_decimal=position_value_decimal,
        equity_decimal=equity_decimal,
        realized_pnl_decimal=realized_pnl_decimal,
        unrealized_pnl_decimal=unrealized_pnl_decimal,
    )


def _period(**overrides: object) -> RecommendationPortfolioPeriodPrecisionV2:
    values: dict[str, object] = {
        "registry_run_id": "synthetic-run-only",
        "portfolio_parent_id": "synthetic-parent-only",
        "strategy_id": "synthetic-strategy-a",
        "strategy_version": "fixture-v2",
        "stock_code": "2330",
        "initial_capital_decimal": "100.00",
        "currency_code": "USD",
        "minor_unit_exponent": 2,
        "currency_authority": "synthetic-test-only; not ISO membership evidence",
        "source_fingerprint_sha256": "sha256:" + ("a" * 64),
        "source_manifest_sha256": "sha256:" + ("b" * 64),
        "source_raw_sha256": "sha256:" + ("c" * 64),
        "equity_parquet_sha256": "sha256:" + ("d" * 64),
        "trades_parquet_sha256": "sha256:" + ("e" * 64),
        "source_cutoff_at": "2025-01-03T13:30:00+00:00",
        "source_available_at": "2025-01-03T13:00:00+00:00",
        "source_availability_basis": "synthetic-fixture-clock-only",
        "source_quality_status": "unknown",
        "session_calendar_id": "synthetic-calendar-only",
        "session_calendar_version": "fixture-v1",
        "session_calendar_sha256": "sha256:" + ("f" * 64),
        "expected_session_dates": ["2025-01-02", "2025-01-03"],
        "completion_status": "completed",
        "execution_contract_id": "synthetic-execution-only",
        "execution_contract_version": "fixture-v1",
        "execution_contract_sha256": "sha256:" + ("1" * 64),
        "cost_model_id": "synthetic-cost-only",
        "cost_model_version": "fixture-v1",
        "cost_model_sha256": "sha256:" + ("2" * 64),
        "observations": (
            _observation("2025-01-02"),
            _observation(
                "2025-01-03",
                cash_decimal="90.00",
                position_value_decimal="10.00",
                equity_decimal="100.00",
                realized_pnl_decimal="0.00",
                unrealized_pnl_decimal="0.00",
            ),
        ),
    }
    values.update(overrides)
    return RecommendationPortfolioPeriodPrecisionV2.create(
        **cast(_PeriodArguments, values)
    )


def test_canonical_codec_preserves_decimal_text_and_exact_minor_units() -> None:
    period = _period()

    decoded = RecommendationPortfolioPeriodPrecisionV2.from_json(period.to_json())
    document = decoded.to_dict()

    assert document["schema_version"] == "recommendation-portfolio-period-precision.v2"
    assert cast(str, document["observations_sha256"]).startswith("sha256:")
    assert document["coverage_status"] == "complete"
    assert document["money_comparable"] is False
    assert document["expected_session_count"] == 2
    assert document["actual_session_count"] == 2
    assert decoded.historical_pit_eligible is False
    assert decoded.performance_eligible is False
    assert decoded.broker_eligible is False
    rows = cast(list[dict[str, object]], document["observations"])
    first = rows[0]
    assert first["cash_decimal"] == "100.00"
    minor_units = cast(dict[str, object], first["minor_units"])
    assert minor_units["cash"] == 10000
    assert decoded.to_dict() == period.to_dict()


@pytest.mark.parametrize(
    ("currency_code", "minor_unit_exponent", "currency_authority"),
    [(None, None, None)],
)
def test_unknown_currency_cannot_issue_comparable_money(
    currency_code: str | None,
    minor_unit_exponent: int | None,
    currency_authority: str | None,
) -> None:
    period = _period(
        currency_code=currency_code,
        minor_unit_exponent=minor_unit_exponent,
        currency_authority=currency_authority,
    )

    assert period.money_comparable is False
    rows = cast(list[dict[str, object]], period.to_dict()["observations"])
    minor_units = cast(dict[str, object], rows[0]["minor_units"])
    assert minor_units["cash"] is None


def test_missing_source_pins_or_unknown_quality_cannot_issue_comparable_money() -> None:
    period = _period(
        source_fingerprint_sha256=None,
        source_manifest_sha256=None,
        source_raw_sha256=None,
        equity_parquet_sha256=None,
        trades_parquet_sha256=None,
        source_cutoff_at=None,
        source_available_at=None,
        source_availability_basis=None,
        source_quality_status="unknown",
    )

    assert period.money_comparable is False
    assert period.source_raw_sha256 is None


@pytest.mark.parametrize(
    "bad_text",
    ["NaN", "Infinity", "+1.00", "01.00", ".5", "1.", "1e3", " 1.00"],
)
def test_rejects_nonfinite_or_noncanonical_decimal_text(bad_text: str) -> None:
    with pytest.raises(RecommendationPortfolioPeriodPrecisionV2Error):
        _observation(
            "2025-01-02",
            cash_decimal=bad_text,
            position_value_decimal="0.00",
            equity_decimal=bad_text,
        )


def test_rejects_float_boolean_and_decimal_overflow_inputs() -> None:
    with pytest.raises(RecommendationPortfolioPeriodPrecisionV2Error):
        _observation(
            "2025-01-02",
            cash_decimal=cast(str, 1.0),
        )
    with pytest.raises(RecommendationPortfolioPeriodPrecisionV2Error):
        _period(minor_unit_exponent=True)
    with pytest.raises(RecommendationPortfolioPeriodPrecisionV2Error):
        _observation(
            "2025-01-02",
            cash_decimal="9" * 81,
            position_value_decimal="0",
            equity_decimal="9" * 81,
        )


def test_minor_units_require_exact_representation_without_rounding() -> None:
    with pytest.raises(RecommendationPortfolioPeriodPrecisionV2Error, match="禁止二次捨入"):
        _period(
            observations=(
                _observation(
                    "2025-01-02",
                    cash_decimal="0.001",
                    position_value_decimal="99.999",
                    equity_decimal="100.000",
                ),
            ),
            expected_session_dates=["2025-01-02"],
        )


def test_missing_expected_session_is_partial_not_a_complete_period() -> None:
    period = _period(
        observations=(
            _observation("2025-01-02"),
            _observation("2025-01-04", cash_decimal="90.00", position_value_decimal="10.00"),
        ),
        expected_session_dates=["2025-01-02", "2025-01-03", "2025-01-04"],
    )

    document = period.to_dict()
    assert document["actual_session_dates"] == ["2025-01-02", "2025-01-04"]
    assert document["expected_session_count"] == 3
    assert document["actual_session_count"] == 2
    assert document["coverage_status"] == "partial"
    assert period.money_comparable is False


@pytest.mark.parametrize(
    "observations",
    [
        (_observation("2025-01-02"), _observation("2025-01-02")),
        (_observation("2025-01-03"), _observation("2025-01-02")),
    ],
)
def test_duplicate_or_nonincreasing_observation_dates_are_rejected(
    observations: tuple[RecommendationPortfolioPeriodObservationV2, ...],
) -> None:
    with pytest.raises(RecommendationPortfolioPeriodPrecisionV2Error, match="日期"):
        _period(observations=observations)


def test_observation_cannot_crosswire_a_second_stock() -> None:
    with pytest.raises(RecommendationPortfolioPeriodPrecisionV2Error, match="單一股票"):
        _period(
            observations=(
                _observation("2025-01-02"),
                _observation(
                    "2025-01-03",
                    stock_code="2317",
                    cash_decimal="90.00",
                    position_value_decimal="10.00",
                ),
            )
        )


def test_noncompleted_run_cannot_be_marked_money_comparable() -> None:
    period = _period(completion_status="cancelled")

    assert period.to_dict()["completion_status"] == "cancelled"
    assert period.money_comparable is False


def test_decimal_identity_is_exact_and_rejects_mismatched_equity() -> None:
    exact = _observation(
        "2025-01-02",
        cash_decimal="0.10",
        position_value_decimal="0.20",
        equity_decimal="0.30",
    )
    assert exact.equity_decimal == "0.30"
    with pytest.raises(
        RecommendationPortfolioPeriodPrecisionV2Error,
        match=r"cash \+ position_value",
    ):
        _observation(
            "2025-01-02",
            cash_decimal="0.10",
            position_value_decimal="0.20",
            equity_decimal="0.30000000000000004",
        )


def test_from_dict_rejects_tampered_row_even_if_payload_remains_well_shaped() -> None:
    document = deepcopy(_period().to_dict())
    rows = cast(list[dict[str, object]], document["observations"])
    rows[0]["cash_decimal"] = "101.00"

    with pytest.raises(RecommendationPortfolioPeriodPrecisionV2Error):
        RecommendationPortfolioPeriodPrecisionV2.from_dict(document)


def test_rejects_malformed_source_hash_and_currency_code() -> None:
    with pytest.raises(RecommendationPortfolioPeriodPrecisionV2Error, match="sha256"):
        _period(source_raw_sha256="c" * 64)
    with pytest.raises(RecommendationPortfolioPeriodPrecisionV2Error, match="ISO 4217"):
        _period(currency_code="US", minor_unit_exponent=2)


def test_from_json_rejects_duplicate_keys_and_naive_source_clock() -> None:
    with pytest.raises(RecommendationPortfolioPeriodPrecisionV2Error, match="重複 key"):
        RecommendationPortfolioPeriodPrecisionV2.from_json(
            b'{"schema_version":"first","schema_version":"second"}'
        )
    with pytest.raises(RecommendationPortfolioPeriodPrecisionV2Error, match="時區"):
        _period(source_available_at="2025-01-03T13:00:00")

