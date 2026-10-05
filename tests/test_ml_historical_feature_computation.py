from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from data_module.ml_historical_snapshot_provider import (
    HistoricalIndexObservation,
    HistoricalPriceObservation,
    HistoricalRawSnapshot,
    HistoricalTechnicalObservation,
    CurrentObservedRawSnapshot,
)
from data_module.ml_daily_price_revision_gate import VerifiedCurrentRestatedSourceContext
from data_module.ml_price_availability_contract import (
    build_price_unavailable_research_contract,
)
from ml_module.historical_feature_builder import HistoricalFeatureBuilder


def _current_observed_snapshot() -> CurrentObservedRawSnapshot:
    start = datetime.fromisoformat("2026-09-12")
    dates = tuple((start + timedelta(days=day)).date().isoformat() for day in range(21))
    prices = tuple(
        HistoricalPriceObservation(
            symbol="2330",
            trading_date=day,
            open_price=Decimal("100") + index,
            high_price=Decimal("101") + index,
            low_price=Decimal("99") + index,
            close_price=Decimal("100") + index,
            volume=100_000 + index,
            turnover_amount_minor=10_000_000 + index,
        )
        for index, day in enumerate(dates)
    )
    market = tuple(
        HistoricalIndexObservation("market", day, Decimal("10_000") + index)
        for index, day in enumerate(dates)
    )
    industries = tuple(
        HistoricalIndexObservation("T00", day, Decimal("1_000") + index)
        for index, day in enumerate(dates)
    )
    technicals = (
        HistoricalTechnicalObservation(
            "2330", "2026-10-02", Decimal("55"), Decimal("0.5"), Decimal("25")
        ),
    )
    observed = datetime.fromisoformat("2026-10-03T04:00:00+00:00")
    snapshot_path = "C:/repo/output/ml_research/snapshot.sqlite"
    receipt_path = "C:/repo/output/ml_research/snapshot_receipt.json"
    snapshot_sha = "sha256:" + "1" * 64
    receipt_sha = "sha256:" + "2" * 64
    context = VerifiedCurrentRestatedSourceContext(
        source_database_path="D:/data/twstock.db",
        source_database_sha256="3" * 64,
        source_wal_path="D:/data/twstock.db-wal",
        source_wal_sha256=None,
        snapshot_database_path=snapshot_path,
        snapshot_database_sha256=snapshot_sha,
        snapshot_receipt_path=receipt_path,
        snapshot_receipt_sha256=receipt_sha,
        decision_at=datetime.fromisoformat("2026-10-03T03:00:00+00:00"),
        training_as_of=datetime.fromisoformat("2026-10-03T03:30:00+00:00"),
        source_observed_at=datetime.fromisoformat("2026-10-03T02:00:00+00:00"),
        source_generation=1,
        revision_namespace_files=(),
        revision_namespace_bundle_sha256="4" * 64,
        source_revision_evidence_schema_version="validated-source-evidence.v1",
        source_revision_evidence_scope_id="fixture",
        source_revision_evidence_cutoff_date="2026-10-03",
        source_revision_evidence_sha256="5" * 64,
        source_revision_evidence_namespaces=(),
        source_revision_evidence_files=(),
        revision_dependencies_verified_at=datetime.fromisoformat("2026-10-03T03:15:00+00:00"),
        revision_dependency_files=(),
        revision_dependency_bundle_sha256="6" * 64,
        source_wal_present=False,
    )
    hashes = {
        table: "sha256:" + str(index) * 64
        for index, table in enumerate(
            ("daily_prices", "technical_indicators", "market_indices", "industry_indices"),
            start=1,
        )
    }
    return CurrentObservedRawSnapshot(
        decision_date="2026-10-03",
        feature_as_of_date="2026-10-02",
        prices=prices,
        technicals=technicals,
        market=market,
        industries=industries,
        source_fingerprint=snapshot_sha,
        query_count=4,
        local_current_observed_at=observed,
        source_context=context,
        snapshot_database_path=snapshot_path,
        snapshot_database_sha256=snapshot_sha,
        snapshot_receipt_path=receipt_path,
        snapshot_receipt_sha256=receipt_sha,
        source_rows_sha256_by_table=hashes,
        requested_symbols=("2330",),
        cycle_id="raw-run-fixture",
        cycle_terminal_path="C:/repo/output/ml_research/current_stock_cycles/2026-10-02/raw-run-fixture/terminal_receipt.json",
        cycle_terminal_sha256="sha256:" + "7" * 64,
        source_context_envelope_path="C:/repo/output/ml_research/current_stock_cycles/2026-10-02/raw-run-fixture/context/source_context.json",
        source_context_envelope_sha256="sha256:" + "8" * 64,
    )


def _snapshot(*, future: bool = False) -> HistoricalRawSnapshot:
    prices = tuple(
        HistoricalPriceObservation(
            symbol="2330", trading_date=f"2024-01-{day:02d}",
            open_price=Decimal(day), high_price=Decimal(day + 1),
            low_price=Decimal(day - 1), close_price=Decimal(day),
            volume=day * 100, turnover_amount_minor=day * 1000,
        )
        for day in range(1, 22)
    )
    if future:
        prices += (replace(prices[-1], trading_date="2024-02-01", close_price=Decimal("999")),)
    market = tuple(
        HistoricalIndexObservation("market", f"2024-01-{day:02d}", Decimal(day * 2))
        for day in range(1, 22)
    )
    industry = tuple(
        HistoricalIndexObservation("半導體類指數", f"2024-01-{day:02d}", Decimal(day * 3))
        for day in range(1, 22)
    )
    return HistoricalRawSnapshot(
        decision_date="2024-01-22", feature_as_of_date="2024-01-21",
        prices=prices, technicals=(HistoricalTechnicalObservation(
            "2330", "2024-01-21", Decimal("55"), Decimal("0.5"), Decimal("25")
        ),), market=market, industries=industry,
        source_fingerprint="sha256:" + "1" * 64, query_count=5,
    )


def test_computation_uses_integer_units_and_excludes_fundamental_and_broker() -> None:
    row = HistoricalFeatureBuilder().compute(
        _snapshot(), industry_index_name_by_symbol={"2330": "半導體類指數"}
    )[0]
    values = dict(row.values)

    assert row.feature_as_of_date == "2024-01-21"
    assert values["stock_return_20d_bp"] == 200000
    assert values["market_return_20d_bp"] == 200000
    assert values["stock_minus_market_20d_bp"] == 0
    assert values["industry_relative_return_20d_bp"] == 0
    assert values["turnover_amount_minor"] == 21000
    assert all(value is None or type(value) is int for value in values.values())
    assert not any("fundamental" in name or "broker" in name for name in values)


def test_current_observed_feature_row_pins_all_20_slots_without_pit_qualification() -> None:
    row = HistoricalFeatureBuilder().compute_current_observed(
        _current_observed_snapshot(),
        industry_index_name_by_symbol={"2330": "T00"},
    )[0]

    assert row.symbol == "2330"
    assert row.decision_date == "2026-10-03"
    assert row.feature_as_of_date == "2026-10-02"
    assert row.local_current_observed_at.isoformat() == "2026-10-03T04:00:00+00:00"
    assert len(row.feature_ids) == 20
    assert tuple(feature_id for feature_id, _ in row.values) == row.feature_ids
    assert row.source_row_sha256_by_table[0][0] == "daily_prices"
    assert len(row.source_row_sha256_by_table) == 4
    assert row.historical_pit_eligible is False
    assert row.formal_training_allowed is False
    assert row.research_only is True
    assert row.row_sha256.startswith("sha256:")
    assert all(value is None or type(value) is int for _, value in row.values)


def test_current_observed_feature_row_rejects_same_day_feature_cutoff() -> None:
    snapshot = _current_observed_snapshot()
    with pytest.raises(ValueError, match="must precede decision date"):
        replace(snapshot, feature_as_of_date=snapshot.decision_date)


def test_future_rows_are_ignored_and_do_not_change_existing_feature_vector() -> None:
    builder = HistoricalFeatureBuilder()
    arguments = {"industry_index_name_by_symbol": {"2330": "半導體類指數"}}

    prefix = builder.compute(_snapshot(), **arguments)
    extended = builder.compute(_snapshot(future=True), **arguments)

    assert extended == prefix


def test_missing_close_inside_window_is_not_compressed_into_a_different_horizon() -> None:
    snapshot = _snapshot()
    prices = list(snapshot.prices)
    prices[-6] = replace(prices[-6], close_price=None)

    row = HistoricalFeatureBuilder().compute(
        replace(snapshot, prices=tuple(prices)),
        industry_index_name_by_symbol={"2330": "半導體類指數"},
    )[0]

    assert dict(row.values)["close_to_ma_20d_bp"] is None
    assert dict(row.values)["trailing_volatility_20d_bp"] is None
    assert dict(row.values)["stock_return_20d_bp"] is None


def test_three_day_price_gap_is_consumed_as_a_feature_window_break() -> None:
    snapshot = _snapshot()
    prices = list(snapshot.prices)
    prices[-2] = replace(
        prices[-2],
        open_price=None,
        high_price=None,
        low_price=None,
        close_price=None,
    )

    row = HistoricalFeatureBuilder().compute(
        replace(snapshot, prices=tuple(prices)),
        industry_index_name_by_symbol={"2330": "半導體類指數"},
    )[0]
    values = dict(row.values)

    # The latest valid day must not use day[-3] as a synthetic prior day.
    assert values["stock_return_1d_bp"] is None
    assert values["close_to_ma_5d_bp"] is None
    assert values["volume_ratio_5d_bp"] is None


def test_missing_middle_market_session_is_not_compressed_into_feature_window() -> None:
    snapshot = _snapshot()
    prices = tuple(
        row for row in snapshot.prices if row.trading_date != "2024-01-20"
    )

    row = HistoricalFeatureBuilder().compute(
        replace(snapshot, prices=prices),
        industry_index_name_by_symbol={"2330": "半導體類指數"},
    )[0]
    values = dict(row.values)

    # The observed market-date path still expects 2024-01-20.  Its absent
    # stock row stays an empty slot, so a trailing helper cannot bridge it by
    # taking an earlier observation as the prior session.
    assert values["stock_return_1d_bp"] is None
    assert values["close_to_ma_5d_bp"] is None
    assert values["volume_ratio_5d_bp"] is None


def test_missing_market_cutoff_does_not_relabel_prior_date_as_feature_cutoff() -> None:
    snapshot = _snapshot()
    market = tuple(row for row in snapshot.market if row.trading_date != "2024-01-21")

    row = HistoricalFeatureBuilder().compute(
        replace(snapshot, market=market),
        industry_index_name_by_symbol={"2330": "半導體類指數"},
    )[0]
    values = dict(row.values)

    assert row.feature_as_of_date == "2024-01-21"
    assert values["stock_return_1d_bp"] == 500
    assert values["turnover_amount_minor"] == 21000
    assert values["market_return_5d_bp"] is None


def test_missing_middle_market_session_remains_an_empty_index_slot() -> None:
    snapshot = _snapshot()
    market = tuple(row for row in snapshot.market if row.trading_date != "2024-01-20")

    row = HistoricalFeatureBuilder().compute(
        replace(snapshot, market=market),
        industry_index_name_by_symbol={"2330": "半導體類指數"},
    )[0]
    values = dict(row.values)

    assert values["stock_return_1d_bp"] == 500
    assert values["market_return_5d_bp"] is None
    assert values["industry_relative_return_20d_bp"] == 0
    assert values["stock_minus_market_20d_bp"] is None


def test_explicit_price_contract_blocks_complete_snapshot_without_none_row() -> None:
    contract = build_price_unavailable_research_contract(
        symbol="2330",
        date_iso="2024-01-20",
        raw_row={
            "symbol": "2330",
            "open": "--",
            "high": "--",
            "low": "--",
            "close": "--",
            "volume": 100,
        },
        feature_window_dates=tuple(
            f"2024-01-{day:02d}" for day in range(1, 22)
        ),
    )

    row = HistoricalFeatureBuilder().compute(
        _snapshot(),
        industry_index_name_by_symbol={"2330": "半導體類指數"},
        price_unavailable_contracts=(contract,),
    )[0]
    values = dict(row.values)

    assert values["stock_return_1d_bp"] is None
    assert values["stock_return_5d_bp"] is None
    assert values["trailing_volatility_20d_bp"] is None
    assert values["volume_ratio_5d_bp"] is None


def test_early_gap_preserves_short_lookbacks_but_blocks_long_lookbacks() -> None:
    contract = build_price_unavailable_research_contract(
        symbol="2330",
        date_iso="2024-01-10",
        raw_row={
            "symbol": "2330",
            "open": "--",
            "high": "--",
            "low": "--",
            "close": "--",
            "volume": 100,
        },
        feature_window_dates=tuple(
            f"2024-01-{day:02d}" for day in range(1, 22)
        ),
    )

    row = HistoricalFeatureBuilder().compute(
        _snapshot(),
        industry_index_name_by_symbol={"2330": "半導體類指數"},
        price_unavailable_contracts=(contract,),
    )[0]
    values = dict(row.values)

    # The context window proves the anchor exists, but only the anchor is a
    # source gap.  Therefore the recent windows remain usable while the
    # 20-session lookback that crosses 2024-01-10 is missing.
    assert values["stock_return_1d_bp"] == 500
    assert values["stock_return_5d_bp"] == 3125
    assert values["stock_return_20d_bp"] is None
    assert values["close_to_ma_5d_bp"] is not None
    assert values["close_to_ma_20d_bp"] is None


def test_anchor_only_price_contract_is_rejected_by_feature_consumer() -> None:
    contract = build_price_unavailable_research_contract(
        symbol="2330",
        date_iso="2024-01-10",
        raw_row={
            "symbol": "2330",
            "open": "--",
            "high": "--",
            "low": "--",
            "close": "--",
            "volume": 100,
        },
    )

    with pytest.raises(ValueError, match="feature window is incomplete"):
        HistoricalFeatureBuilder().compute(
            _snapshot(),
            industry_index_name_by_symbol={},
            price_unavailable_contracts=(contract,),
        )
