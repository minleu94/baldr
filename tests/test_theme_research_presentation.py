from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext

import pytest

from app_module.theme_daily_service import ThemeDailyReport, ThemeDailyRow, ThemeMetricCoverage
from app_module.theme_research_presentation import (
    ThemeChainDirectory, ThemeResearchPresentation, build_theme_research_presentation,
)
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from decision_module.industry_theme_map import ThemeMappingRow

D = Decimal


def daily_row(
    chain: str, theme: str, *, members: int = 2,
    mean_return: Decimal | None = None, turnover: Decimal | None = None,
    institutional_shares: int | None = None, volume: Decimal | None = None,
    returns_coverage: int | None = None, turnover_coverage: int | None = None,
    institutional_coverage: int | None = None, volume_coverage: int | None = None,
    stock_ids: tuple[str, ...] = ("2330", "2317"),
) -> ThemeDailyRow:
    coverage = ThemeMetricCoverage(
        members,
        members if returns_coverage is None else returns_coverage,
        members if turnover_coverage is None else turnover_coverage,
        members if volume_coverage is None else volume_coverage,
        members if institutional_coverage is None else institutional_coverage,
        0,
    )
    return ThemeDailyRow(
        chain_name=chain,
        theme_name=theme,
        stock_ids=stock_ids,
        mean_return_pct=mean_return,
        turnover_twd=turnover,
        volume_multiple_5d=volume,
        institutional_net_shares=institutional_shares,
        institutional_net_turnover_twd=None,
        up_count=0,
        down_count=0,
        flat_count=0,
        institutional_buy_count=0,
        institutional_sell_count=0,
        institutional_flat_count=0,
        advancing_ratio=None,
        institutional_buy_ratio=None,
        coverage=coverage,
        source_ids=(),
    )


def mapping_row(chain: str, theme: str, stock_id: str) -> ThemeMappingRow:
    row = ThemeMappingRow(
        "2026-10-01", "2026-10-02", stock_id, stock_id, "TWSE", "半導體",
        "半導體", "中游", theme, True, "P2_CURATED_CHAIN_TAXONOMY",
        "fixture_curated", "T2", "quarterly_snapshot", "測試分類",
    )
    return replace(row, chain_name=chain, theme_name=theme, stock_id=stock_id)


def snapshot(rows: tuple[ThemeDailyRow, ...], mapping: tuple[ThemeMappingRow, ...] = ()) -> ThemeResearchSnapshot:
    report = ThemeDailyReport(
        date(2026, 10, 16), datetime(2026, 10, 16, 18, tzinfo=timezone.utc),
        "2026-10-01", "2026-10-02", "current_research", rows, (),
    )
    return ThemeResearchSnapshot("a" * 64, report, mapping)


def test_leaders_require_full_coverage_and_keep_none_zero_and_negative_distinct():
    high = daily_row(
        "B", "高", mean_return=D("2.5"), turnover=D("300.25"),
        institutional_shares=50, volume=D("1.5"),
    )
    zero = daily_row(
        "A", "零", mean_return=D(0), turnover=D(0),
        institutional_shares=0, volume=D(0),
    )
    negative = daily_row(
        "A", "負", mean_return=D("-1.25"), institutional_shares=-20,
    )
    partial = daily_row(
        "A", "部分", mean_return=D("999"), turnover=D("999"),
        institutional_shares=999, volume=D("999"), returns_coverage=1,
        turnover_coverage=1, institutional_coverage=1, volume_coverage=1,
    )
    missing = daily_row("M", "缺值")
    no_members = daily_row(
        "N", "無成員", members=0, mean_return=D("999"), turnover=D("999"),
        institutional_shares=999, volume=D("999"),
    )

    result = build_theme_research_presentation(snapshot((high, zero, negative, partial, missing, no_members)))

    assert result.return_leaders == (high, zero, negative)
    assert result.turnover_leaders == (high, zero)
    assert result.institutional_leaders == (high, zero, negative)
    assert result.volume_leaders == (high, zero)
    assert all(type(row.mean_return_pct) is Decimal for row in result.return_leaders)
    assert all(type(row.institutional_net_shares) is int for row in result.institutional_leaders)


def test_leaderboards_are_limited_to_five_rows():
    rows = tuple(
        daily_row(f"鏈{index:02}", "題材", mean_return=D(10 - index))
        for index in range(6)
    )

    leaders = build_theme_research_presentation(snapshot(rows)).return_leaders

    assert len(leaders) == 5
    assert tuple(row.mean_return_pct for row in leaders) == (D(10), D(9), D(8), D(7), D(6))


def test_equal_values_use_chain_then_theme_name_order():
    rows = (
        daily_row("chain-b", "theme-z", mean_return=D("1.00")),
        daily_row("chain-a", "theme-z", mean_return=D("1.0")),
        daily_row("chain-a", "theme-a", mean_return=D("1.000")),
    )

    leaders = build_theme_research_presentation(snapshot(rows)).return_leaders

    assert tuple((row.chain_name, row.theme_name) for row in leaders) == (
        ("chain-a", "theme-a"), ("chain-a", "theme-z"), ("chain-b", "theme-z"),
    )


def test_lowest_five_come_from_full_eligible_population_with_stable_ties():
    rows = tuple(
        daily_row(f"chain-{index:02}", "theme", mean_return=D(index - 4),
                  turnover=D(index), institutional_shares=index - 4, volume=D(index))
        for index in reversed(range(9))
    )
    partial = daily_row("partial", "theme", mean_return=D("-999"), turnover=D(0),
                        institutional_shares=-999, volume=D(0), returns_coverage=1,
                        turnover_coverage=1, institutional_coverage=1, volume_coverage=1)
    missing = daily_row("missing", "theme")
    source = snapshot((*rows, partial, missing))
    original = (source.identity_sha256, source.report, source.mapping)

    high = build_theme_research_presentation(source)
    low = build_theme_research_presentation(source, ascending=True)
    expected_low = tuple(reversed(rows))[:5]
    for field in ("return_leaders", "turnover_leaders", "institutional_leaders", "volume_leaders"):
        assert getattr(low, field) == expected_low
        assert getattr(low, field) != tuple(reversed(getattr(high, field)))
    assert tuple(row.mean_return_pct for row in low.return_leaders) == (
        D(-4), D(-3), D(-2), D(-1), D(0),
    )
    assert (source.identity_sha256, source.report, source.mapping) == original

    ties = (
        daily_row("b", "z", mean_return=D("1.000")),
        daily_row("a", "z", mean_return=D("1.0")),
        daily_row("a", "a", mean_return=D("1.00")),
    )
    for ascending in (False, True):
        result = build_theme_research_presentation(snapshot(ties), ascending=ascending)
        assert tuple((row.chain_name, row.theme_name) for row in result.return_leaders) == (
            ("a", "a"), ("a", "z"), ("b", "z"),
        )


def test_sorting_uses_exact_original_values_under_low_decimal_precision():
    lower_value = D("1.00000000000000000000000000001")
    higher_value = D("1.00000000000000000000000000002")
    lower = daily_row("a", "lower", mean_return=lower_value, turnover=lower_value,
                      volume=lower_value, institutional_shares=10**40)
    higher = daily_row("z", "higher", mean_return=higher_value, turnover=higher_value,
                       volume=higher_value, institutional_shares=10**40 + 1)
    source = snapshot((lower, higher))

    with localcontext() as context:
        context.prec = 2
        for ascending, expected in ((False, (higher, lower)), (True, (lower, higher))):
            result = build_theme_research_presentation(source, ascending=ascending)
            for field in ("return_leaders", "turnover_leaders", "institutional_leaders", "volume_leaders"):
                assert getattr(result, field) == expected
        assert context.prec == 2
    assert higher.mean_return_pct == higher_value
    assert lower.mean_return_pct == lower_value


@pytest.mark.parametrize("ascending", [None, 0, 1, "ascending", [], {}])
def test_sort_direction_rejects_implicit_boolean_conversion(ascending):
    with pytest.raises(TypeError, match="bool"):
        build_theme_research_presentation(snapshot(()), ascending=ascending)


def test_directory_deduplicates_source_metadata_without_merging_theme_metrics():
    mappings = []
    for index in reversed(range(25)):
        chain = f"chain{index:02}"
        mappings.extend((
            mapping_row(chain, "theme-b", "0001"),
            mapping_row(chain, "theme-a", "0001"),
            mapping_row(chain, "theme-a", "0002"),
            mapping_row(chain, "theme-a", "0001"),
        ))
    first_theme = daily_row("chain00", "theme-a", members=1, mean_return=D("2"),
                            institutional_shares=10, stock_ids=("0001",))
    second_theme = daily_row("chain00", "theme-b", members=1, mean_return=D("2"),
                             institutional_shares=10, stock_ids=("0001",))
    source = snapshot((first_theme, second_theme), tuple(mappings))
    original = (source.identity_sha256, source.report, source.mapping)

    result = build_theme_research_presentation(source)

    assert len(result.chains) == 25
    assert result.chains == tuple(
        ThemeChainDirectory(f"chain{index:02}", ("theme-a", "theme-b"), ("0001", "0002"))
        for index in range(25)
    )
    assert tuple((row.chain_name, row.theme_name) for row in result.return_leaders) == (
        ("chain00", "theme-a"), ("chain00", "theme-b"),
    )
    assert tuple(row.institutional_net_shares for row in result.institutional_leaders) == (10, 10)
    assert (source.identity_sha256, source.report, source.mapping) == original


def test_public_presentation_and_directory_are_frozen_and_tuple_backed():
    directory = ThemeChainDirectory("chain", ("theme",), ("2330",))
    row = daily_row("chain", "theme", mean_return=D("1"))
    result = ThemeResearchPresentation((row,), (), (), (), (directory,))

    with pytest.raises(FrozenInstanceError):
        result.chains = ()
    with pytest.raises(FrozenInstanceError):
        directory.chain_name = "renamed"
    with pytest.raises(TypeError):
        ThemeChainDirectory("chain", ["theme"], ("2330",))
