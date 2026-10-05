from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

import app_module.daily_market_feature_snapshot as snapshot_module
from app_module.daily_market_feature_snapshot import (
    DailyMarketFeatureSnapshot,
    DailyMarketFeatureSnapshotService,
)
from app_module.stock_research_report_dtos import (
    StockMetricDTO,
    StockPricePointDTO,
    StockTechnicalSnapshotDTO,
)


PRICE_SOURCE = "sqlite.daily_prices"
TECHNICAL_SOURCE = "sqlite.technical_indicators"


def _trading_dates(count: int) -> list[date]:
    current = date(2026, 1, 5)
    result: list[date] = []
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def _prices(count: int) -> tuple[StockPricePointDTO, ...]:
    points = []
    for index, market_date in enumerate(_trading_dates(count)):
        close = Decimal(100 + index)
        points.append(
            StockPricePointDTO(
                data_date=market_date.isoformat(),
                open_price=close,
                high_price=close + Decimal("1"),
                low_price=close - Decimal("1"),
                close_price=close,
                volume=1000 + index,
                turnover=close * Decimal(1000 + index),
                change=Decimal("0"),
                available_at="2026-10-05T16:00:00+08:00",
                source_id=PRICE_SOURCE,
                source_snapshot_hash=f"price-row-{index:03d}",
                quality="observed",
            )
        )
    return tuple(points)


def _technical(
    market_date: str,
    *,
    ma20: Decimal | None = Decimal("150.125"),
    ma60: Decimal | None = Decimal("160.75"),
    quality: str = "observed",
    metric_date: str | None = None,
    duplicate_ma20: bool = False,
) -> StockTechnicalSnapshotDTO:
    date_for_metrics = metric_date if metric_date is not None else market_date
    metrics = [
        StockMetricDTO(
            key="MA20",
            label="MA20",
            value=ma20,
            unit="TWD/share",
            data_as_of=date_for_metrics,
            source_id=TECHNICAL_SOURCE,
            quality=quality,
        ),
        StockMetricDTO(
            key="MA60",
            label="MA60",
            value=ma60,
            unit="TWD/share",
            data_as_of=date_for_metrics,
            source_id=TECHNICAL_SOURCE,
            quality=quality,
        ),
    ]
    if duplicate_ma20:
        metrics.append(replace(metrics[0], value=Decimal("151.125")))
    return StockTechnicalSnapshotDTO(
        data_date=market_date,
        indicators=tuple(metrics),
        source_id=TECHNICAL_SOURCE,
        quality=quality,
    )


def _project(
    points: tuple[StockPricePointDTO, ...],
    technical: StockTechnicalSnapshotDTO | None = None,
    *,
    stock_code: str = "2382",
    decision_date: date | None = None,
    scope_identity: str = "stock-report-symbol:2382",
    service: DailyMarketFeatureSnapshotService | None = None,
) -> DailyMarketFeatureSnapshot:
    selected_service = service or DailyMarketFeatureSnapshotService()
    cutoff = decision_date or date.fromisoformat(points[-1].data_date[:10])
    snapshot = selected_service.project(
        stock_code,
        cutoff,
        scope_identity,
        points,
        technical,
    )
    return snapshot


def test_projects_existing_decimal_values_and_three_state_observations_without_recomputing():
    points = _prices(60)
    market_date = points[-1].data_date
    technical = _technical(
        market_date,
        ma20=Decimal("777.123456789"),
        ma60=Decimal("160.75"),
    )

    snapshot = _project(points, technical)

    assert tuple(item.key for item in snapshot.features) == ("close", "MA20", "MA60")
    assert snapshot.feature("close").value == Decimal("159")
    assert snapshot.feature("MA20").value == Decimal("777.123456789")
    assert snapshot.feature("MA20").warmup_required_count == 20
    assert snapshot.feature("MA20").warmup_observed_count == 60
    assert snapshot.feature("MA20").warmup_state == "sufficient_observed_prefix"
    assert snapshot.feature("MA60").value == Decimal("160.75")
    assert snapshot.feature("MA60").warmup_required_count == 60
    assert snapshot.feature("MA60").warmup_observed_count == 60
    assert snapshot.condition("close_above_ma20").state == "no_match"
    assert snapshot.condition("close_above_ma20").relation == "below"
    assert snapshot.condition("close_above_ma60").state == "no_match"
    assert snapshot.condition("close_above_ma60").relation == "below"
    assert all(item.semantics == "existing_observation" for item in snapshot.conditions)

    above_and_equal = _project(
        points,
        _technical(
            market_date,
            ma20=Decimal("150"),
            ma60=Decimal("159"),
        ),
    )
    assert above_and_equal.condition("close_above_ma20").state == "match"
    assert above_and_equal.condition("close_above_ma20").relation == "above"
    assert above_and_equal.condition("close_above_ma60").state == "no_match"
    assert above_and_equal.condition("close_above_ma60").relation == "equal"

    payload = snapshot.to_dict()
    assert payload["features"]["MA20"]["value"] == "777.123456789"
    assert payload["conditions"]["close_above_ma60"]["relation"] == "below"
    assert payload["policy"] == {
        "usage": "current_observed_research_only",
        "official_availability_state": "unknown",
        "market_calendar_completeness": "unknown",
        "historical_pit_eligible": False,
        "warmup_is_formal_or_calendar_qualification": False,
    }


def test_warmup_uses_last_contiguous_valid_ohlc_streak_and_is_window_specific():
    rows = list(_prices(60))
    rows[38] = replace(rows[38], open_price=None)
    points = tuple(rows)
    technical = _technical(points[-1].data_date)

    snapshot = _project(points, technical)

    assert snapshot.feature("close").state == "observed"
    assert snapshot.feature("MA20").state == "observed"
    assert snapshot.feature("MA20").warmup_observed_count == 21
    assert snapshot.feature("MA20").warmup_state == "sufficient_observed_prefix"
    assert snapshot.feature("MA60").state == "unknown"
    assert snapshot.feature("MA60").warmup_observed_count == 21
    assert snapshot.feature("MA60").warmup_state == "unknown"
    assert snapshot.feature("MA60").reason == "invalid_ohlc_row"
    assert snapshot.condition("close_above_ma60").state == "unknown"
    assert snapshot.condition("close_above_ma60").relation == "unknown"


def test_short_history_and_invalid_ohlc_do_not_claim_sma_coverage():
    short_points = _prices(30)
    short_snapshot = _project(short_points, _technical(short_points[-1].data_date))
    assert short_snapshot.feature("MA20").state == "observed"
    assert short_snapshot.feature("MA20").warmup_observed_count == 30
    assert short_snapshot.feature("MA60").state == "unknown"
    assert short_snapshot.feature("MA60").reason == "insufficient_valid_ohlc_streak"

    invalid_rows = list(_prices(25))
    latest = invalid_rows[-1]
    invalid_rows[-1] = replace(latest, high_price=latest.close_price - Decimal("1"))
    invalid_points = tuple(invalid_rows)
    invalid_snapshot = _project(
        invalid_points,
        _technical(invalid_points[-1].data_date),
    )
    assert invalid_snapshot.feature("close").state == "observed"
    assert invalid_snapshot.feature("MA20").state == "unknown"
    assert invalid_snapshot.feature("MA20").warmup_observed_count == 0
    assert invalid_snapshot.feature("MA20").reason == "invalid_ohlc_row"


def test_latest_missing_or_invalid_close_never_falls_back_to_an_older_price():
    points = list(_prices(60))
    market_date = points[-1].data_date
    points[-1] = replace(points[-1], close_price=None)
    snapshot = _project(tuple(points), _technical(market_date))

    assert snapshot.feature("close").value is None
    assert snapshot.feature("close").reason == "latest_close_missing"
    assert snapshot.feature("MA20").state == "unknown"
    assert snapshot.feature("MA20").reason == "invalid_ohlc_row"
    assert snapshot.condition("close_above_ma20").state == "unknown"


def test_future_invalid_duplicate_and_mismatched_dates_are_unknown_with_reasons():
    points = _prices(60)
    latest_date = date.fromisoformat(points[-1].data_date)

    future_point = replace(
        points[-1],
        data_date=(latest_date + timedelta(days=1)).isoformat(),
        source_snapshot_hash="future-row",
    )
    future_snapshot = _project(
        points + (future_point,),
        _technical(points[-1].data_date),
        decision_date=latest_date,
    )
    assert future_snapshot.feature("close").state == "unknown"
    assert future_snapshot.feature("close").reason == "future_market_date"
    assert future_snapshot.condition("close_above_ma20").state == "unknown"

    duplicate = replace(points[-1], data_date=latest_date.strftime("%Y%m%d"))
    duplicate_snapshot = _project(points + (duplicate,), _technical(points[-1].data_date))
    assert duplicate_snapshot.feature("close").reason == "duplicate_market_date"
    assert duplicate_snapshot.feature("MA20").reason == "duplicate_market_date"

    invalid_date = replace(points[-1], data_date="not-a-date")
    invalid_snapshot = _project(
        points[:-1] + (invalid_date,),
        _technical(points[-2].data_date),
        decision_date=latest_date,
    )
    assert invalid_snapshot.feature("close").reason == "invalid_market_date"
    assert invalid_snapshot.feature("MA20").reason == "invalid_market_date"

    mismatched = _technical(points[-2].data_date)
    date_mismatch_snapshot = _project(points, mismatched)
    assert date_mismatch_snapshot.feature("close").state == "observed"
    assert date_mismatch_snapshot.feature("MA20").reason == "technical_date_mismatch"
    assert date_mismatch_snapshot.condition("close_above_ma20").state == "unknown"


def test_technical_quality_metric_duplicates_and_metric_date_are_guarded():
    points = _prices(60)
    market_date = points[-1].data_date

    stale_snapshot = _project(points, _technical(market_date, quality="stale"))
    assert stale_snapshot.feature("MA20").state == "unknown"
    assert stale_snapshot.feature("MA20").reason == "technical_quality_not_observed"

    duplicate_snapshot = _project(
        points,
        _technical(market_date, duplicate_ma20=True),
    )
    assert duplicate_snapshot.feature("MA20").reason == "duplicate_technical_metric"
    assert duplicate_snapshot.condition("close_above_ma20").state == "unknown"

    stale_metric_date = _technical(market_date, metric_date=points[-2].data_date)
    metric_date_snapshot = _project(points, stale_metric_date)
    assert metric_date_snapshot.feature("MA20").reason == "technical_metric_date_mismatch"


def test_latest_quality_and_non_decimal_values_are_unknown_without_float_conversion():
    points = list(_prices(60))
    market_date = points[-1].data_date

    stale_latest = tuple(points[:-1] + [replace(points[-1], quality="stale")])
    stale_snapshot = _project(stale_latest, _technical(market_date))
    assert stale_snapshot.feature("close").state == "unknown"
    assert stale_snapshot.feature("close").reason == "price_quality_not_observed"

    float_latest = tuple(points[:-1] + [replace(points[-1], close_price=159.0)])
    float_snapshot = _project(float_latest, _technical(market_date))
    assert float_snapshot.feature("close").state == "unknown"
    assert float_snapshot.feature("close").reason == "latest_close_invalid"

    float_ma = _technical(market_date, ma20=Decimal("150"))
    float_metric = replace(float_ma.indicators[0], value=150.0)  # type: ignore[arg-type]
    float_technical = replace(float_ma, indicators=(float_metric, float_ma.indicators[1]))
    float_ma_snapshot = _project(tuple(points), float_technical)
    assert float_ma_snapshot.feature("MA20").state == "unknown"
    assert float_ma_snapshot.feature("MA20").reason == "technical_metric_invalid"

    non_finite_latest = tuple(
        points[:-1] + [replace(points[-1], close_price=Decimal("NaN"))]
    )
    non_finite_snapshot = _project(non_finite_latest, _technical(market_date))
    assert non_finite_snapshot.feature("close").state == "unknown"
    assert non_finite_snapshot.feature("close").reason == "latest_close_invalid"


def test_cache_identity_binds_full_values_scope_date_source_and_contract_version(monkeypatch):
    service = DailyMarketFeatureSnapshotService()
    points = _prices(60)
    market_date = date.fromisoformat(points[-1].data_date)
    technical = _technical(points[-1].data_date)

    first = service.project("2382", market_date, "cohort:a", points, technical)
    same = service.project("2382", market_date, "cohort:a", points, technical)
    assert same is first

    changed_price = points[:-1] + (
        replace(points[-1], source_snapshot_hash="revised-price-row"),
    )
    changed_technical = replace(
        technical,
        indicators=(
            replace(technical.indicators[0], value=Decimal("151.25")),
            technical.indicators[1],
        ),
    )
    changed_source = service.project("2382", market_date, "cohort:a", changed_price, technical)
    changed_value = service.project("2382", market_date, "cohort:a", points, changed_technical)
    changed_scope = service.project("2382", market_date, "cohort:b", points, technical)
    changed_date = service.project(
        "2382",
        market_date + timedelta(days=1),
        "cohort:a",
        points,
        technical,
    )
    assert len(
        {
            first.snapshot_identity_sha256,
            changed_source.snapshot_identity_sha256,
            changed_value.snapshot_identity_sha256,
            changed_scope.snapshot_identity_sha256,
            changed_date.snapshot_identity_sha256,
        }
    ) == 5

    monkeypatch.setattr(
        snapshot_module,
        "DAILY_MARKET_FEATURE_CONTRACT_VERSION",
        "daily-market-feature-snapshot.v2",
    )
    changed_version = service.project("2382", market_date, "cohort:a", points, technical)
    assert changed_version.contract_version.endswith("v2")
    assert changed_version.snapshot_identity_sha256 != first.snapshot_identity_sha256
    assert len(service._cache) == 1

    for index in range(8):
        service.project("2382", market_date, f"cohort:{index}", points, technical)
    assert len(service._cache) <= 4
    with pytest.raises(ValueError, match="max_entries"):
        DailyMarketFeatureSnapshotService(max_entries=5)


def test_snapshot_identity_and_serialization_are_stable_and_scope_is_required():
    service = DailyMarketFeatureSnapshotService()
    points = _prices(60)
    technical = _technical(points[-1].data_date)

    first = service.project("2382", date.fromisoformat(points[-1].data_date), "cohort:a", points, technical)
    second = service.project("2382", date.fromisoformat(points[-1].data_date), "cohort:a", points, technical)
    assert first.snapshot_identity_sha256 == second.snapshot_identity_sha256
    assert first.to_dict() == second.to_dict()
    exposed = first.to_dict()
    exposed["features"]["MA20"]["value"] = "mutated"
    exposed["conditions"]["close_above_ma20"]["state"] = "mutated"
    assert first.feature("MA20").value == Decimal("150.125")
    assert first.condition("close_above_ma20").state != "mutated"
    assert first.to_dict()["features"]["MA20"]["value"] == "150.125"
    with pytest.raises(ValueError, match="scope_identity"):
        service.project("2382", date.fromisoformat(points[-1].data_date), " ", points, technical)
