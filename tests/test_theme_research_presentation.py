from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext

import pytest

from app_module.theme_daily_service import ThemeDailyReport, ThemeDailyRow, ThemeMetricCoverage
from app_module.theme_research_presentation import (
    ThemeChainDirectory, ThemeResearchPresentation, ThemeReturnTile, ThemeTurnoverTile,
    build_theme_research_presentation, build_theme_return_two_version_presentation,
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


def snapshot(rows: tuple[ThemeDailyRow, ...], mapping: tuple[ThemeMappingRow, ...] = (), *,
             identity: str = "a" * 64, data_date: date = date(2026, 10, 16),
             mapping_snapshot_date: str = "2026-10-01", mapping_available_date: str = "2026-10-02") -> ThemeResearchSnapshot:
    report = ThemeDailyReport(
        data_date, datetime(2026, 10, 16, 18, tzinfo=timezone.utc),
        mapping_snapshot_date, mapping_available_date, "current_research", rows, (),
    )
    return ThemeResearchSnapshot(identity, report, mapping)


def test_two_version_presentation_keeps_each_original_observation_independent():
    first_row = replace(daily_row("半導體", "AI", mean_return=D("1.230000"), stock_ids=("2330", "2303")),
                        source_ids=("source-first",))
    second_row = replace(daily_row("半導體", "AI", mean_return=D("-0.250"), stock_ids=("2317", "2454")),
                         source_ids=("source-second-a", "source-second-b"))
    first = snapshot((first_row,), identity="1" * 64, data_date=date(2026, 10, 15),
                     mapping_snapshot_date="2026-10-01", mapping_available_date="2026-10-03")
    second = snapshot((second_row,), identity="2" * 64, data_date=date(2026, 10, 16),
                      mapping_snapshot_date="2026-10-10", mapping_available_date="2026-10-11")

    result = build_theme_return_two_version_presentation(first, second, chain_name="半導體", theme_name="AI")

    earlier, later = result.observations
    assert (earlier.snapshot_identity, later.snapshot_identity) == ("1" * 64, "2" * 64)
    assert (earlier.data_date, later.data_date) == ("2026-10-15", "2026-10-16")
    assert (earlier.mapping_snapshot_date, later.mapping_snapshot_date) == ("2026-10-01", "2026-10-10")
    assert (earlier.mapping_available_date, later.mapping_available_date) == ("2026-10-03", "2026-10-11")
    assert (earlier.stock_ids, later.stock_ids) == (("2330", "2303"), ("2317", "2454"))
    assert (earlier.member_count, later.member_count) == (2, 2)
    assert (earlier.mean_return_pct, later.mean_return_pct) == (D("1.230000"), D("-0.250"))
    assert (earlier.returns_coverage, later.returns_coverage) == (2, 2)
    assert (earlier.source_ids, later.source_ids) == (("source-first",), ("source-second-a", "source-second-b"))
    assert type(earlier.mean_return_pct) is Decimal and type(later.mean_return_pct) is Decimal


def test_two_version_missing_and_partial_returns_remain_unknown():
    partial = replace(daily_row("半導體", "AI", mean_return=D("999"), returns_coverage=1,
                                stock_ids=("2330", "2317")), source_ids=("partial-source",))
    first = snapshot((), (mapping_row("半導體", "AI", "2330"), mapping_row("半導體", "AI", "2317")),
                     identity="3" * 64)
    second = snapshot((partial,), identity="4" * 64)

    result = build_theme_return_two_version_presentation(first, second, chain_name="半導體", theme_name="AI")

    absent, incomplete = result.observations
    assert absent.mean_return_pct is None
    assert (absent.stock_ids, absent.member_count, absent.returns_coverage) == (("2330", "2317"), 2, None)
    assert absent.row_present is False
    assert absent.source_ids == ()
    assert incomplete.mean_return_pct is None
    assert (incomplete.stock_ids, incomplete.member_count, incomplete.returns_coverage) == (("2330", "2317"), 2, 1)
    assert incomplete.row_present is True
    assert incomplete.source_ids == ("partial-source",)
    with pytest.raises(ValueError, match="完整非空成員覆蓋"):
        replace(incomplete, mean_return_pct=D("0"))
    with pytest.raises(ValueError, match="不得推定覆蓋數"):
        replace(absent, returns_coverage=0)


def test_two_version_presentation_rejects_duplicate_identity_and_duplicate_theme_rows():
    source = snapshot((daily_row("半導體", "AI", mean_return=D("1")),), identity="5" * 64)
    with pytest.raises(ValueError, match="同一快照身份"):
        build_theme_return_two_version_presentation(source, source, chain_name="半導體", theme_name="AI")
    duplicate = snapshot((daily_row("半導體", "AI", mean_return=D("1")),
                          daily_row("半導體", "AI", mean_return=D("2"))), identity="6" * 64)
    with pytest.raises(ValueError, match="重複題材觀察列"):
        build_theme_return_two_version_presentation(source, duplicate, chain_name="半導體", theme_name="AI")


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


def test_return_tiles_require_full_coverage_and_keep_exact_source_context():
    positive = replace(
        daily_row("科技鏈", "正值", mean_return=D("1.230000")),
        source_ids=("price-source-v1",),
    )
    zero = replace(
        daily_row("中性鏈", "零值", mean_return=D("0.000")),
        source_ids=("price-source-v1",),
    )
    negative = replace(
        daily_row("能源鏈", "負值", mean_return=D("-2.500")),
        source_ids=("price-source-v1",),
    )
    partial = daily_row(
        "科技鏈", "部分", mean_return=D("999"), returns_coverage=1,
    )
    nonfinite_partial = daily_row(
        "科技鏈", "非有限", mean_return=D("NaN"), returns_coverage=1,
    )
    missing = daily_row("科技鏈", "缺值", mean_return=None)
    empty = daily_row("科技鏈", "無成員", members=0, mean_return=D("5"))
    source = snapshot((positive, zero, negative, partial, nonfinite_partial, missing, empty))

    result = build_theme_research_presentation(source)

    assert result.return_tile_total == 7
    assert all(type(tile) is ThemeReturnTile for tile in result.return_tiles)
    assert tuple((tile.chain_name, tile.theme_name) for tile in result.return_tiles) == (
        ("科技鏈", "正值"), ("中性鏈", "零值"), ("能源鏈", "負值"),
    )
    positive_tile = result.return_tiles[0]
    assert positive_tile.mean_return_pct is positive.mean_return_pct
    assert positive_tile.mean_return_pct == D("1.230000")
    assert (positive_tile.returns_coverage, positive_tile.members) == (2, 2)
    assert positive_tile.data_date == "2026-10-16"
    assert positive_tile.mapping_snapshot_date == "2026-10-01"
    assert positive_tile.mapping_available_date == "2026-10-02"
    assert positive_tile.known_at == "2026-10-16T18:00:00+00:00"
    assert positive_tile.snapshot_identity == source.identity_sha256
    assert positive_tile.source_ids == ("price-source-v1",)
    assert tuple(tile.mean_return_pct for tile in result.return_tiles) == (
        D("1.230000"), D("0.000"), D("-2.500"),
    )
    with pytest.raises(FrozenInstanceError):
        positive_tile.theme_name = "changed"


def test_turnover_tiles_require_full_coverage_and_preserve_zero_and_source_context():
    positive = replace(
        daily_row("科技鏈", "正值", turnover=D("123456789.0100")),
        source_ids=("price-source-v1", "flow-source-v2"),
    )
    zero = replace(
        daily_row("能源鏈", "零值", turnover=D("0.000")),
        source_ids=("price-source-v1",),
    )
    partial = daily_row("科技鏈", "部分", turnover=D("999999"), turnover_coverage=1)
    missing = daily_row("科技鏈", "缺值", turnover=None)
    # 現有排行榜會拒絕完整覆蓋但非有限的值；部分覆蓋仍由此投影略過。
    nonfinite = daily_row("科技鏈", "非有限", turnover=D("NaN"), turnover_coverage=1)
    no_members = daily_row("科技鏈", "無成員", members=0, turnover=D("999"))
    source = snapshot((positive, zero, partial, missing, nonfinite, no_members))

    result = build_theme_research_presentation(source)

    assert result.turnover_tile_total == 6
    assert tuple((tile.chain_name, tile.theme_name) for tile in result.turnover_tiles) == (
        ("科技鏈", "正值"), ("能源鏈", "零值"),
    )
    positive_tile = result.turnover_tiles[0]
    assert type(positive_tile) is ThemeTurnoverTile
    assert positive_tile.turnover_twd is positive.turnover_twd
    assert positive_tile.turnover_twd == D("123456789.0100")
    assert (positive_tile.turnover_coverage, positive_tile.members) == (2, 2)
    assert positive_tile.data_date == "2026-10-16"
    assert positive_tile.mapping_snapshot_date == "2026-10-01"
    assert positive_tile.mapping_available_date == "2026-10-02"
    assert positive_tile.known_at == "2026-10-16T18:00:00+00:00"
    assert positive_tile.snapshot_identity == source.identity_sha256
    assert positive_tile.source_ids == ("price-source-v1", "flow-source-v2")
    assert result.turnover_tiles[1].turnover_twd == D("0.000")
    with pytest.raises(FrozenInstanceError):
        positive_tile.theme_name = "changed"


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
