"""題材觀察聚合的金融口徑、版本與缺件回歸；不把測試資料授為來源資格。"""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from app_module.theme_daily_service import (
    ThemeDailyService, ThemeFlowObservation, ThemeMarketInput, ThemePriceObservation, _volume_multiple,
)
from decision_module.industry_theme_map import ThemeMappingRow

D = Decimal
DAY = date(2026, 10, 16)
CLOCK = datetime(2026, 10, 16, 18, tzinfo=timezone(timedelta(hours=8)))
SESSIONS = tuple(date(2026, 10, value) for value in (8, 12, 13, 14, 15))


def mapping(code="2330", theme="晶圓代工", **changes):
    row = ThemeMappingRow(
        "2026-10-01", "2026-10-02", code, code, "TWSE", "半導體",
        "半導體", "中游", theme, True, "P2_CURATED_CHAIN_TAXONOMY",
        "fixture_curated", "T2", "quarterly_snapshot", "測試分類",
    )
    return replace(row, **changes)


class MappingReader:
    def __init__(self, rows=None, status="pit_snapshot_aligned", available="2026-10-02"):
        self.rows = rows if rows is not None else [mapping()]
        self.status = status
        self.available = available

    def load_pit_mapping(self, as_of_date):
        return self.rows, "2026-10-01", self.available, self.status, []


class MarketReader:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def read(self, stock_ids, data_date, known_at):
        self.calls.append((stock_ids, data_date, known_at))
        return self.data


def price(code="2330", **changes):
    return replace(ThemePriceObservation(code, DAY, CLOCK, "fixture.price", D("110"),
                                        D("10"), D("1000.01"), 200), **changes)


def build(data, rows=None, **mapping_args):
    return ThemeDailyService(MappingReader(rows, **mapping_args), MarketReader(data),
                             mapping_available_at=CLOCK).build(DAY, CLOCK)


def test_equal_weight_return_amount_share_units_and_separate_coverage():
    prices = (price(), price("2317", close_twd=D("90"), change_twd=D("-10"), turnover_twd=D("2000.02")))
    flows = (ThemeFlowObservation("2330", DAY, CLOCK, "fixture.flow", 3000, D("123.45")),
             ThemeFlowObservation("2317", DAY, CLOCK, "fixture.flow", -1000))
    row = build(ThemeMarketInput(prices, flows), [mapping(), mapping("2317")]).rows[0]
    assert row.mean_return_pct == D(0)
    assert row.turnover_twd == D("3000.03")
    assert row.institutional_net_shares == 2000
    assert row.institutional_net_turnover_twd == D("123.45")
    assert (row.up_count, row.down_count, row.flat_count) == (1, 1, 0)
    assert (row.institutional_buy_count, row.institutional_sell_count) == (1, 1)
    assert row.advancing_ratio == row.institutional_buy_ratio == D("0.5")
    assert row.coverage.members == row.coverage.returns == row.coverage.turnover == 2
    assert row.coverage.institutional_shares == 2 and row.coverage.institutional_amount == 1


def test_missing_direction_never_filled_from_other_price_or_zero():
    report = build(ThemeMarketInput((price(change_twd=None),)), [mapping(), mapping("2317")])
    row = report.rows[0]
    assert row.mean_return_pct is None and row.advancing_ratio is None
    assert row.turnover_twd == D("1000.01") and row.coverage.turnover == 1
    assert row.coverage.members == 2 and row.coverage.returns == 0
    assert row.institutional_net_shares is None and row.institutional_net_turnover_twd is None
    assert row.up_count == row.down_count == row.flat_count == 0
    assert report.historical_pit_eligible is False


def test_zero_is_distinct_from_missing():
    data = ThemeMarketInput((price(change_twd=D(0), turnover_twd=D(0), volume_shares=0),),
                            (ThemeFlowObservation("2330", DAY, CLOCK, "fixture.flow", 0, D(0)),))
    row = build(data).rows[0]
    assert row.mean_return_pct == row.turnover_twd == D(0)
    assert row.institutional_net_shares == 0 and row.institutional_net_turnover_twd == D(0)
    assert row.flat_count == row.institutional_flat_count == 1


def test_volume_formula_and_unqualified_dates_cannot_enable_it():
    history = tuple(price(data_date=day, volume_shares=100) for day in SESSIONS)
    data = ThemeMarketInput((price(), *history), previous_sessions=SESSIONS, session_source_id="fixture.calendar")
    row = build(data).rows[0]
    assert _volume_multiple(200, 500) == D(2)
    assert _volume_multiple(200, 0) is None
    assert row.volume_multiple_5d is None and row.coverage.volume_history == 0


def test_missing_prior_session_never_uses_sixth_older_row():
    history = tuple(price(data_date=day, volume_shares=100) for day in SESSIONS[1:])
    extra = price(data_date=date(2026, 10, 7), volume_shares=100)
    row = build(ThemeMarketInput((price(), *history, extra), previous_sessions=SESSIONS,
                                session_source_id="fixture.calendar")).rows[0]
    assert row.volume_multiple_5d is None and row.coverage.volume_history == 0


@pytest.mark.parametrize("sessions,source", [((), ""), (SESSIONS[:4], "cal"),
    ((SESSIONS[0],) * 5, "cal"), (tuple(reversed(SESSIONS)), "cal"),
    ((*SESSIONS[:4], DAY), "cal"), (SESSIONS, "")])
def test_invalid_calendar_cannot_enable_volume(sessions, source):
    history = tuple(price(data_date=day, volume_shares=100) for day in SESSIONS)
    report = build(ThemeMarketInput((price(), *history), previous_sessions=sessions, session_source_id=source))
    assert report.rows[0].volume_multiple_5d is None
    assert "five_session_calendar_unavailable" in report.warnings


def test_partial_member_volume_is_not_full_theme_multiple():
    history = tuple(price(data_date=day, volume_shares=100) for day in SESSIONS)
    row = build(ThemeMarketInput((price(), price("2317"), *history), previous_sessions=SESSIONS,
                                session_source_id="cal"), [mapping(), mapping("2317")]).rows[0]
    assert row.coverage.volume_history == 0 and row.volume_multiple_5d is None


@pytest.mark.parametrize("clock", [None, CLOCK + timedelta(seconds=1), CLOCK - timedelta(days=1)])
def test_unknown_future_or_impossible_source_clock_does_not_enter_metrics(clock):
    data = ThemeMarketInput((price(available_at=clock),),
        (ThemeFlowObservation("2330", DAY, clock, "fixture.flow", 1, D(1)),))
    row = build(data).rows[0]
    assert row.mean_return_pct is None and row.turnover_twd is None
    assert row.institutional_net_shares is None


def test_available_at_cutoff_is_inclusive_and_timezone_aware():
    utc = CLOCK.astimezone(timezone.utc)
    row = build(ThemeMarketInput((price(available_at=utc),))).rows[0]
    assert row.mean_return_pct == D(10)


@pytest.mark.parametrize("status", ["current_snapshot_replay_only", "in_memory_bootstrap", "unknown"])
def test_unaligned_mapping_blocks_only_aggregation_without_requesting_market_data(status):
    market = MarketReader(ThemeMarketInput((price(),)))
    report = ThemeDailyService(MappingReader(status=status), market).build(DAY, CLOCK)
    assert report.status == "mapping_unavailable" and report.rows == ()
    assert market.calls == []


@pytest.mark.parametrize("rows,available", [([mapping(available_date="2026-10-17")], "2026-10-17"),
    ([mapping(), mapping("2317", available_date="2026-10-17")], "2026-10-02"),
    ([mapping(snapshot_date="2026-11-01")], "2026-10-02"), ([], "2026-10-02")])
def test_mapping_checks_every_member_not_only_manifest(rows, available):
    report = build(ThemeMarketInput((price(),)), rows, available=available)
    assert report.status == "mapping_unavailable" and not report.rows


def test_duplicate_mapping_deduplicates_and_multiple_themes_stay_separate():
    rows = [mapping(), mapping(), mapping(theme="先進封裝")]
    result = build(ThemeMarketInput((price(),)), rows).rows
    assert len(result) == 2
    assert all(row.coverage.members == 1 and row.turnover_twd == D("1000.01") for row in result)


def test_conflicting_mapping_is_rejected():
    with pytest.raises(ValueError, match="映射互相衝突"):
        build(ThemeMarketInput(), [mapping(), mapping(stock_name="不一致")])


@pytest.mark.parametrize("kind", ["prices", "flows"])
def test_duplicate_source_versions_are_not_silently_summed(kind):
    observation = price() if kind == "prices" else ThemeFlowObservation("2330", DAY, CLOCK, "flow", 1)
    with pytest.raises(ValueError, match="重複"):
        build(ThemeMarketInput(**{kind: (observation, observation)}))


def test_other_day_and_unrelated_stock_do_not_leak_into_requested_day():
    row = build(ThemeMarketInput((price("9999"), price(data_date=DAY - timedelta(days=1))),
        (ThemeFlowObservation("2330", DAY - timedelta(days=1), CLOCK, "flow", 999),))).rows[0]
    assert row.mean_return_pct is None and row.institutional_net_shares is None


def test_order_and_decimal_context_do_not_change_results():
    rows = [mapping(), mapping("2317")]
    data = ThemeMarketInput((price(), price("2317", close_twd=D(7), change_twd=D(1))))
    original = build(data, rows)
    with localcontext() as context:
        context.prec = 5
        reordered = build(replace(data, prices=tuple(reversed(data.prices))), list(reversed(rows)))
    assert original == reordered


@pytest.mark.parametrize("field,value", [("close_twd", 1.2), ("turnover_twd", D("NaN")),
    ("change_twd", D("Infinity")), ("turnover_twd", D(-1)), ("volume_shares", True),
    ("volume_shares", -1)])
def test_invalid_precision_or_units_are_rejected(field, value):
    with pytest.raises(ValueError):
        price(**{field: value})


def test_naive_clock_and_future_query_are_rejected():
    with pytest.raises(ValueError, match="時區"):
        price(available_at=CLOCK.replace(tzinfo=None))
    service = ThemeDailyService(MappingReader(), MarketReader(ThemeMarketInput()))
    with pytest.raises(ValueError, match="時區"):
        service.build(DAY, CLOCK.replace(tzinfo=None))
    with pytest.raises(ValueError, match="資料日"):
        service.build(DAY + timedelta(days=1), CLOCK)


@pytest.mark.parametrize("available_at", [None, CLOCK + timedelta(hours=1)])
def test_mapping_day_label_cannot_override_missing_or_later_save_clock(available_at):
    market = MarketReader(ThemeMarketInput((price(),)))
    report = ThemeDailyService(MappingReader(), market, mapping_available_at=available_at).build(DAY, CLOCK)
    assert report.status == "mapping_unavailable" and market.calls == []
    assert "mapping_clock_unavailable_or_future" in report.warnings
