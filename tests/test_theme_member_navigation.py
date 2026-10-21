"""同一題材版本成員導航的 immutable context 守衛。"""

from dataclasses import replace

from app_module.research_session import ResearchStockContextDTO
from ui_qt.views.theme_member_navigation import ThemeMemberNavigation


def _navigation(**changes) -> ThemeMemberNavigation:
    values = {
        "snapshot_ref": object(),
        "snapshot_identity": "a" * 64,
        "theme_key": ("科技鏈", "AI"),
        "member_stock_codes": ("2330", "2317"),
        "member_names": (("2330", "台積電"), ("2317", "鴻海")),
        "origin_stock_code": "2330",
        "origin_row_index": 0,
        "source_data_date": "2026-10-16",
        "mapping_version": "2026-10-15",
        "selection_revision": 4,
    }
    values.update(changes)
    return ThemeMemberNavigation(**values)


def _context() -> ResearchStockContextDTO:
    return ResearchStockContextDTO(
        stock_code="2330",
        stock_name="台積電",
        data_date="2026-10-16",
        source_snapshot_id="a" * 64,
        source_snapshot_hash="a" * 64,
        source_id="local.theme_research_snapshot",
        source_version="a" * 64,
        mapping_version="2026-10-15",
        source_kind="industry_theme_snapshot",
        source_workspace="market_explore",
        source_label="自選本機題材版本",
        ml_scope_mode="current_stock_research",
    )


def test_same_snapshot_theme_members_can_step_and_return_without_changing_lineage():
    navigation = _navigation()
    context = _context()

    next_context = navigation.resolve_context(context, "2317", navigation)
    assert next_context is not None
    assert next_context.stock_code == "2317"
    assert next_context.stock_name == "鴻海"
    assert replace(next_context, stock_code=context.stock_code,
                   stock_name=context.stock_name) == context

    returned = navigation.resolve_context(next_context, "2330", navigation)
    assert returned is not None
    assert returned.stock_code == "2330"
    assert returned.stock_name == "台積電"
    assert replace(returned, stock_code=next_context.stock_code,
                   stock_name=next_context.stock_name) == next_context


def test_navigation_rejects_nonmembers_stale_snapshot_theme_filter_or_origin_row():
    navigation = _navigation()
    context = _context()
    assert navigation.resolve_context(context, "2881", navigation) is None
    assert navigation.resolve_context(context, "2317", None) is None
    assert navigation.resolve_context(
        context, "2317", _navigation(snapshot_ref=object())
    ) is None
    assert navigation.resolve_context(
        context, "2317", _navigation(theme_key=("金融鏈", "保險"))
    ) is None
    assert navigation.resolve_context(
        context, "2317", _navigation(member_stock_codes=("2330", "2881"))
    ) is None
    assert navigation.resolve_context(
        context, "2317", _navigation(origin_stock_code="2317", origin_row_index=1)
    ) is None
    assert navigation.resolve_context(
        context, "2317", _navigation(selection_revision=5)
    ) is None


def test_navigation_rejects_context_with_changed_source_or_dates():
    navigation = _navigation()
    for changed in (
        {"source_snapshot_hash": "b" * 64},
        {"source_version": "b" * 64},
        {"source_kind": "daily_market_research_snapshot"},
        {"source_workspace": "watchlist"},
        {"data_date": "2026-10-17"},
        {"mapping_version": "2026-10-16"},
    ):
        assert navigation.resolve_context(
            replace(_context(), **changed), "2317", navigation
        ) is None
