from __future__ import annotations

from dataclasses import dataclass

import pytest

from app_module.portfolio_stress_lab_service import PortfolioStressLabService


@dataclass
class Position:
    stock_code: str
    stock_name: str
    quantity: object
    current_price: object
    is_holding: bool = True
    quote_data_date: object = None
    quote_source_id: object = None
    quote_source_snapshot_hash: object = None
    quote_freshness_status: object = None


def _positions() -> tuple[Position, ...]:
    return (
        Position("2330", "台積電", 1000, 100),
        Position("2317", "鴻海", 1000, 50),
    )


def test_fast_drop_is_decimal_and_research_only() -> None:
    result = PortfolioStressLabService().evaluate_positions(
        _positions(), scenario_id="fast_drop", as_of_date="2026-08-26"
    )

    assert result.status == "ready"
    assert result.base_market_value == 150000
    assert result.stressed_market_value == 135000
    assert result.value_delta == -15000
    assert result.priced_position_count == 2
    assert result.research_only is True
    assert result.investment_effectiveness_claim is False
    payload = result.to_dict()
    assert payload["base_market_value"] == "150000.00"
    # 舊 position fixture 沒有 provenance，既有金額欄維持原值，新增欄明確未知。
    first_row = payload["positions"][0]
    assert first_row["stock_code"] == "2330"
    assert first_row["quantity"] == "1000"
    assert first_row["mark_price"] == "100"
    assert first_row["base_value"] == "100000.00"
    assert first_row["shock_bp"] == -1000
    assert first_row["stressed_value"] == "90000.00"
    assert first_row["value_delta"] == "-10000.00"
    assert first_row["quote_data_date"] is None
    assert first_row["quote_source_id"] is None
    assert first_row["quote_source_snapshot_hash"] is None
    assert first_row["quote_freshness_status"] is None
    assert result.schema_version == "portfolio-stress-lab.v1"


def test_quote_provenance_is_copied_from_exact_input_row() -> None:
    position = Position(
        "2330",
        "台積電",
        1000,
        100,
        quote_data_date="2026-08-26",
        quote_source_id="sqlite.daily_prices",
        quote_source_snapshot_hash="a" * 64,
        quote_freshness_status="current",
    )

    result = PortfolioStressLabService().evaluate_positions([position])

    assert len(result.positions) == 1
    row = result.positions[0]
    assert row.quote_data_date == "2026-08-26"
    assert row.quote_source_id == "sqlite.daily_prices"
    assert row.quote_source_snapshot_hash == "a" * 64
    assert row.quote_freshness_status == "current"
    assert row.to_dict()["mark_price"] == "100"
    assert row.to_dict()["quote_source_snapshot_hash"] == "a" * 64


def test_missing_and_invalid_quote_provenance_remain_unknown() -> None:
    legacy_result = PortfolioStressLabService().evaluate_positions(_positions())
    legacy_row = legacy_result.positions[0]
    assert legacy_row.quote_data_date is None
    assert legacy_row.quote_source_id is None
    assert legacy_row.quote_source_snapshot_hash is None
    assert legacy_row.quote_freshness_status is None

    invalid = Position(
        "2330",
        "台積電",
        1000,
        100,
        quote_data_date="20260826",
        quote_source_id="   ",
        quote_source_snapshot_hash="not-a-sha256",
        quote_freshness_status="trusted",
    )
    invalid_row = PortfolioStressLabService().evaluate_positions([invalid]).positions[0]
    assert invalid_row.quote_data_date is None
    assert invalid_row.quote_source_id is None
    assert invalid_row.quote_source_snapshot_hash is None
    assert invalid_row.quote_freshness_status is None

    partial = Position(
        "2330",
        "台積電",
        1000,
        100,
        quote_data_date="2026-08-26",
        quote_source_id="sqlite.daily_prices",
        quote_source_snapshot_hash="bad-hash",
        quote_freshness_status="unverified",
    )
    partial_row = PortfolioStressLabService().evaluate_positions([partial]).positions[0]
    assert partial_row.quote_data_date == "2026-08-26"
    assert partial_row.quote_source_id == "sqlite.daily_prices"
    assert partial_row.quote_source_snapshot_hash is None
    assert partial_row.quote_freshness_status == "unverified"

    incomplete_current = Position(
        "2330",
        "台積電",
        1000,
        100,
        quote_data_date="2026-08-26",
        quote_source_id="sqlite.daily_prices",
        quote_source_snapshot_hash="bad-hash",
        quote_freshness_status="current",
    )
    incomplete_row = PortfolioStressLabService().evaluate_positions(
        [incomplete_current]
    ).positions[0]
    assert incomplete_row.quote_freshness_status is None


def test_same_code_positions_keep_their_own_quote_provenance_and_order() -> None:
    positions = (
        Position(
            "2330",
            "台積電持倉 A",
            100,
            100,
            quote_data_date="2026-08-26",
            quote_source_id="sqlite.daily_prices",
            quote_source_snapshot_hash="a" * 64,
            quote_freshness_status="current",
        ),
        Position(
            "2330",
            "台積電持倉 B",
            200,
            101,
            quote_data_date="2026-08-25",
            quote_source_id="csv.daily_prices",
            quote_source_snapshot_hash="b" * 64,
            quote_freshness_status="stale",
        ),
    )

    result = PortfolioStressLabService().evaluate_positions(positions)

    assert [row.stock_name for row in result.positions] == [
        "台積電持倉 A",
        "台積電持倉 B",
    ]
    assert [row.quote_data_date for row in result.positions] == [
        "2026-08-26",
        "2026-08-25",
    ]
    assert [row.quote_source_id for row in result.positions] == [
        "sqlite.daily_prices",
        "csv.daily_prices",
    ]
    assert [row.quote_source_snapshot_hash for row in result.positions] == [
        "a" * 64,
        "b" * 64,
    ]


def test_concentration_event_only_shocks_largest_position() -> None:
    result = PortfolioStressLabService().evaluate_positions(
        _positions(), scenario_id="concentration_event"
    )

    rows = {row.stock_code: row for row in result.positions}
    assert rows["2330"].shock_bp == -2000
    assert rows["2317"].shock_bp == 0
    assert result.stressed_market_value == 130000
    assert result.value_delta == -20000


def test_missing_price_is_partial_and_never_extrapolated() -> None:
    positions = (
        *_positions(),
        Position(
            "1101",
            "台泥",
            1000,
            None,
            quote_data_date="2026-08-26",
            quote_source_id="sqlite.daily_prices",
            quote_source_snapshot_hash="c" * 64,
            quote_freshness_status="current",
        ),
    )
    result = PortfolioStressLabService().evaluate_positions(positions, scenario_id="fast_drop")

    assert result.status == "partial"
    assert result.priced_position_count == 2
    assert result.total_position_count == 3
    assert result.missing_price_codes == ("1101",)
    assert result.base_market_value == 150000
    assert result.stressed_market_value == 135000
    assert "partial_positions_only_no_extrapolation" in result.warnings
    assert len(result.positions) == 2
    assert all(row.stock_code != "1101" for row in result.positions)


def test_no_priced_rows_remains_not_computable_without_provenance_rows() -> None:
    result = PortfolioStressLabService().evaluate_positions(
        [
            Position(
                "1101",
                "台泥",
                1000,
                None,
                quote_data_date="2026-08-26",
                quote_source_id="sqlite.daily_prices",
                quote_source_snapshot_hash="c" * 64,
                quote_freshness_status="current",
            )
        ],
        scenario_id="fast_drop",
    )

    assert result.status == "not_computable"
    assert result.positions == ()
    assert result.missing_price_codes == ("1101",)


@pytest.mark.parametrize("scenario_id", ("rotation_failure", "source_outage"))
def test_unsupported_or_outage_scenarios_are_fail_closed(scenario_id: str) -> None:
    result = PortfolioStressLabService().evaluate_positions(
        _positions(), scenario_id=scenario_id
    )

    assert result.status == "not_computable"
    assert result.base_market_value is None
    assert result.stressed_market_value is None
    assert result.value_delta is None
    assert result.blockers


def test_empty_positions_are_not_computable() -> None:
    result = PortfolioStressLabService().evaluate_positions((), scenario_id="fast_drop")

    assert result.status == "not_computable"
    assert result.blockers == ("active_positions_missing",)


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported stress scenario"):
        PortfolioStressLabService().evaluate_positions(_positions(), scenario_id="unknown")
