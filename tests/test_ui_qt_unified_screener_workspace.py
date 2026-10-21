from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

pytest_plugins = (
    "test_daily_market_technical_official_disposition_composite_query_v2",
    "test_daily_market_technical_universe_price_query_v1",
)

from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePriceResultV1,
)
from tests.test_daily_market_technical_universe_price_query_v1 import _open_session
import tests.test_daily_market_technical_official_disposition_bundle_v1 as composite_fixtures

from ui_qt.views.unified_screener_workspace import (
    UnifiedScreenerWorkspace,
    project_result_funnel,
)


class _Host:
    def __init__(self, splitter: QSplitter, scroll: QScrollArea, tabs: QTabWidget,
                 saved: QWidget, config: QWidget) -> None:
        self.main_splitter = splitter
        self.result_scroll = scroll
        self.result_source_tabs = tabs
        self.result_panel = saved
        self.config_scroll = config


class _Page(QWidget):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.setObjectName(name)
        self.run_count = 0

    def run_query(self) -> None:
        self.run_count += 1


@pytest.fixture
def qtbot():
    app = QApplication.instance() or QApplication([])
    widgets = []

    class _WidgetCleanup:
        def addWidget(self, widget):
            widgets.append(widget)

    yield _WidgetCleanup()
    for widget in reversed(widgets):
        widget.close()
        widget.deleteLater()
    app.processEvents()


def _workspace(qtbot):
    splitter = QSplitter(Qt.Orientation.Horizontal)
    config = QWidget()
    splitter.addWidget(config)
    tabs = QTabWidget()
    saved = _Page("savedStrategySource")
    daily = QWidget()
    daily.setObjectName("dailyMarketResearch")
    nested = QTabWidget(daily)
    nested.setObjectName("dailyMarketResearchSections")
    nested.setGeometry(0, 0, 400, 300)
    daily.research_sections = nested
    price = _Page("priceSource")
    price_layout = QVBoxLayout(price)
    price_table = QTableView(price)
    price_table.setMinimumHeight(240)
    price_layout.addWidget(price_table)
    nested.addTab(price, "價格選股")
    snapshot = _Page("dailySnapshot")
    nested.addTab(snapshot, "每日快照條件")
    official = _Page("officialSource")
    composite = _Page("compositeV2Source")
    composite_layout = QVBoxLayout(composite)
    composite_scroll = QScrollArea(composite)
    composite_scroll.setObjectName("compositeV2PageScroll")
    composite_scroll.setWidgetResizable(True)
    composite_layout.addWidget(composite_scroll, 1)
    h20 = _Page("personalH20Route")
    h20.setProperty("v2_screener_ml_route", True)
    tabs.addTab(saved, "已保存推薦／策略研究")
    tabs.addTab(daily, "每日研究條件")
    tabs.addTab(official, "官方市場／處置研究")
    tabs.addTab(composite, "官方條件與價格研究")
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(tabs)
    splitter.addWidget(scroll)
    host = _Host(splitter, scroll, tabs, saved, config)
    qtbot.addWidget(splitter)
    workspace = UnifiedScreenerWorkspace(host)
    return host, workspace, (saved, daily, nested, price, snapshot, official, composite, h20)


def _reader_issued_composite_v2_result(tmp_path: Path, monkeypatch):
    """在 pytest 實體暫存根建立同一組真實 exact readers。"""
    from app_module.daily_market_technical_official_disposition_bundle_v1 import (
        DailyMarketTechnicalOfficialDispositionBundleReaderV1,
        DailyMarketTechnicalOfficialDispositionBundleWriterV1,
    )
    from app_module.daily_market_technical_official_disposition_query_v1 import (
        DailyMarketTechnicalOfficialDispositionQueryV1,
    )
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        open_daily_market_technical_official_disposition_projection_group_session_v3,
    )
    from app_module.daily_market_technical_official_disposition_composite_query_v1 import (
        DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    )
    from app_module.daily_market_technical_official_disposition_composite_query_v2 import (
        DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
        execute_composite_query_v2,
    )
    from app_module.daily_market_technical_universe_v4_producer import (
        DailyMarketTechnicalUniverseV4ProductionRequest,
        produce_daily_market_technical_universe_v4,
    )
    from app_module.daily_market_technical_universe_v4_query import (
        open_daily_market_technical_universe_v4_read_session,
    )
    from app_module.daily_market_technical_universe_v4_store import (
        DailyMarketTechnicalUniverseV4Cohort,
        DailyMarketTechnicalUniverseV4StoreReader,
    )
    from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
    from data_module.selection_market_assignments import CurrentMarketAssignmentReader
    from data_module.selection_official_events import CurrentOfficialDisposalReader

    root = tmp_path.resolve(strict=True)
    decision_date = composite_fixtures._DECISION_DATE
    cutoff = composite_fixtures._CUTOFF
    database = root / "synthetic_prices.sqlite"
    included_codes = ("1000", "1001")
    excluded_code = "9999"
    composite_fixtures._write_prices(database, included_codes)
    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="ui-funnel-composite-v2",
        population_version="synthetic-ui-funnel-v1",
        decision_date=decision_date,
        raw_stock_codes=(*included_codes, excluded_code),
        excluded_stock_codes=(excluded_code,),
        exclusion_reasons={excluded_code: "合成來源明示排除"},
    )
    scope = ResearchCaptureWriteScope(root / "technical-output", database)
    store_root = scope.root / "technical-store"
    produced = produce_daily_market_technical_universe_v4(
        DailyMarketTechnicalUniverseV4ProductionRequest(
            source_database=database,
            cohort=cohort,
            decision_cutoff=cutoff,
            store_output_root=store_root,
            research_scope=scope,
        )
    )
    assert produced.status == "complete"
    assert produced.plan is not None and produced.receipt is not None

    composite_fixtures._FrozenDateTime.fixed_now = composite_fixtures._PUBLISHED_AT
    monkeypatch.setattr(
        composite_fixtures.capture_module,
        "datetime",
        composite_fixtures._FrozenDateTime,
    )
    market_pointer = composite_fixtures._capture_market_sources(
        root / "market-capture", (included_codes[0],), included_codes[1]
    )
    disposal_pointer = composite_fixtures._capture_disposal_sources(
        root / "disposal-capture", included_codes[0], included_codes[1]
    )
    market_pin = CurrentMarketAssignmentReader.from_pointer(
        market_pointer, cutoff_at=cutoff
    ).source_pin
    disposal_pin = CurrentOfficialDisposalReader.from_pointer(
        disposal_pointer, cutoff_at=cutoff
    ).source_pin

    verified_store = DailyMarketTechnicalUniverseV4StoreReader(store_root).read_exact(
        produced.generation_identity_sha256,
        produced.plan_identity_sha256,
        produced.receipt_identity_sha256,
        expected_receipt_sha256=produced.receipt_content_sha256,
        expected_plan_sha256=produced.plan_sha256,
    )
    plan_sha = produced.plan_sha256
    receipt_sha = produced.receipt_content_sha256
    assert plan_sha is not None and receipt_sha is not None
    technical_session = open_daily_market_technical_universe_v4_read_session(
        store_output_root=store_root,
        generation_identity_sha256=produced.generation_identity_sha256,
        plan_identity_sha256=produced.plan_identity_sha256,
        plan_sha256=plan_sha,
        receipt_identity_sha256=produced.receipt_identity_sha256,
        receipt_sha256=receipt_sha,
    )
    technical_query = technical_session.create_query(
        rule_state_filters=(),
        combine_mode="AND",
        stock_filter=(),
        sort_key="stock_code",
        descending=False,
        page_index=0,
        page_size=1,
    )
    bundle_root = scope.root / "official-disposition-bundle"
    bundle_reference = DailyMarketTechnicalOfficialDispositionBundleWriterV1(
        bundle_root, research_scope=scope
    ).create_from_pins(
        store_output_root=store_root,
        generation_identity_sha256=produced.generation_identity_sha256,
        plan_identity_sha256=produced.plan_identity_sha256,
        expected_plan_sha256=plan_sha,
        receipt_identity_sha256=produced.receipt_identity_sha256,
        expected_receipt_sha256=receipt_sha,
        market_assignment_source_pin=market_pin,
        official_disposal_source_pin=disposal_pin,
    )
    bundle_state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(
        bundle_root
    ).read_exact(
        bundle_reference.bundle_identity_sha256,
        expected_manifest_sha256=bundle_reference.manifest_sha256,
    )
    query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=technical_query,
        decision_cutoff=cutoff,
        bundle_output_root=bundle_root,
        bundle_identity_sha256=bundle_reference.bundle_identity_sha256,
        expected_manifest_sha256=bundle_reference.manifest_sha256,
        market_assignment_pin_identity_sha256=market_pin.identity_sha256,
        official_disposal_pin_identity_sha256=disposal_pin.identity_sha256,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
    )
    projection_session = open_daily_market_technical_official_disposition_projection_group_session_v3(
        query
    )
    base_query = DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        query,
        projection_group_session_identity_sha256=projection_session.identity_sha256,
    )
    composite_query = DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base_query
    )
    result = execute_composite_query_v2(composite_query, projection_session)
    assert bundle_state.reference.bundle_identity_sha256 == bundle_reference.bundle_identity_sha256
    assert projection_session.reader_issued is True
    return result, projection_session


def test_source_selection_keeps_original_tabs_and_does_not_run_queries(qtbot):
    host, workspace, pages = _workspace(qtbot)
    saved, _daily, _nested, price, _snapshot, official, _composite, _h20 = pages
    original_tabs = host.result_source_tabs
    original_pages = [original_tabs.widget(index) for index in range(original_tabs.count())]

    price_entry = next(item for item in workspace._sources if item.widget is price)
    assert workspace.select_source(price_entry.key)
    assert host.result_source_tabs.currentWidget() is pages[1]
    assert pages[2].currentWidget() is price
    assert workspace.combo.currentData() == price_entry.key
    assert price.run_count == official.run_count == saved.run_count == 0
    assert host.result_source_tabs is original_tabs
    assert [original_tabs.widget(index) for index in range(original_tabs.count())] == original_pages
    assert host.result_source_tabs.tabBar().isHidden()
    assert pages[2].tabBar().isHidden()
    assert host.result_source_tabs.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Preferred
    assert host.result_scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded


def test_external_navigation_updates_combo_and_keeps_original_callback_surface(qtbot):
    host, workspace, pages = _workspace(qtbot)
    _saved, _daily, _nested, _price, _snapshot, official, _composite, _h20 = pages
    host.result_source_tabs.setCurrentWidget(official)
    entry = next(item for item in workspace._sources if item.widget is official)
    assert workspace.combo.currentData() == entry.key
    assert host.result_source_tabs.widget(host.result_source_tabs.indexOf(official)) is official
    host.result_source_tabs.setCurrentWidget(pages[1])
    snapshot = pages[4]
    pages[2].setCurrentWidget(snapshot)
    nested_entry = next(item for item in workspace._sources if item.widget is snapshot)
    assert workspace.combo.currentData() == nested_entry.key


def test_nested_scroll_source_fills_the_result_viewport(qtbot):
    _host, workspace, pages = _workspace(qtbot)
    composite = pages[-2]
    entry = next(item for item in workspace._sources if item.widget is composite)
    assert workspace.select_source(entry.key)
    assert workspace.tabs.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Ignored
    assert workspace.scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert composite.findChild(QScrollArea).widgetResizable()


def test_funnel_uses_result_counts_and_leaves_missing_denominator_unknown():
    view = SimpleNamespace(
        current_result=None,
        current_page=SimpleNamespace(rows=tuple(range(500)), matching_count=500),
    )
    projection = project_result_funnel(view)
    assert not projection.available
    assert projection.metrics == ()

    counts = SimpleNamespace(
        source_counts=SimpleNamespace(declared_count=40, processed_count=37, pending_count=3),
        price_counts=SimpleNamespace(
            base_matching_count=37,
            pass_count=10,
            fail_count=20,
            unknown_count=7,
            matching_count=10,
        ),
    )
    result = SimpleNamespace(
        query=SimpleNamespace(schema_version="daily-market-technical-universe-price-query.v1"),
        counts=None,
        source_counts=counts.source_counts,
        price_counts=counts.price_counts,
    )
    projection = project_result_funnel(SimpleNamespace(current_result=result, current_page=None))
    assert projection.available
    assert projection.schema == "daily-market-technical-universe-price-query.v1"
    assert projection.source_identity is None
    assert projection.query_identity is None
    assert projection.data_date is None
    assert projection.metrics[0].domain == "來源母體"
    assert projection.metrics[0].denominator == 40
    price_metric = next(item for item in projection.metrics if item.domain == "價格條件")
    assert (price_metric.denominator, price_metric.match, price_metric.no_match, price_metric.unknown) == (
        37, 10, 20, 7
    )


@pytest.mark.parametrize(
    "states",
    (
        (("match", 2), ("no_match", -1), ("unknown", 1), ("not_evaluated", 0), ("not_applicable", 0)),
        (("match", 2), ("no_match", 1), ("not_evaluated", 0), ("not_applicable", 0)),
        (("match", 2), ("no_match", True), ("unknown", 1), ("not_evaluated", 0), ("not_applicable", 0)),
    ),
)
def test_invalid_or_incomplete_domain_counts_never_shrink_the_denominator(states):
    result = SimpleNamespace(
        counts=SimpleNamespace(composite_truth_counts=states),
        query=SimpleNamespace(query_identity_sha256="a" * 64),
        source_pins=(),
    )
    projection = project_result_funnel(SimpleNamespace(current_result=result, current_page=None))
    domain = next(item for item in projection.metrics if item.domain == "官方＋技術條件")
    assert domain.denominator is None
    assert domain.match is None
    assert domain.no_match is None
    assert domain.unknown is None


def test_funnel_projects_reader_issued_f07_counts(exact_price_store):
    session = _open_session(exact_price_store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    assert isinstance(result, DailyMarketTechnicalUniversePriceResultV1)
    projection = project_result_funnel(SimpleNamespace(current_result=result, current_page=None))
    source = next(item for item in projection.metrics if item.domain == "來源母體")
    price = next(item for item in projection.metrics if item.domain == "價格條件")
    assert source.denominator == result.source_counts.declared_count
    assert price.denominator == result.price_counts.base_matching_count
    assert (price.match, price.no_match, price.unknown) == (
        result.price_counts.pass_count,
        result.price_counts.fail_count,
        result.price_counts.unknown_count,
    )
    assert projection.data_date == result.query.source.decision_date.isoformat()
    assert projection.source_identity == result.query.source.source_identity_sha256[:12]
    assert projection.query_identity == result.query.query_identity_sha256[:12]


def test_funnel_projects_reader_issued_composite_v2_counts(tmp_path, monkeypatch):
    result, session = _reader_issued_composite_v2_result(tmp_path, monkeypatch)
    projection = project_result_funnel(SimpleNamespace(current_result=result, current_page=None))
    final = next(item for item in projection.metrics if item.domain == "最終條件")
    technical = next(item for item in projection.metrics if item.domain == "技術")
    expected = dict(result.counts.final_truth_counts)
    expected_technical = dict(result.counts.base_composite_counts.technical_truth_counts)
    assert final.denominator == result.counts.declared_count
    assert (final.match, final.no_match, final.unknown) == (
        expected["match"], expected["no_match"], expected["unknown"]
    )
    assert technical.denominator == result.counts.declared_count
    assert (technical.match, technical.no_match, technical.unknown) == (
        expected_technical["match"],
        expected_technical["no_match"],
        expected_technical["unknown"],
    )
    assert projection.data_date == result.query.f17_query.decision_date.isoformat()
    assert projection.source_identity == session.identity_sha256[:12]
    assert projection.query_identity == result.query.query_identity_sha256[:12]
    assert projection.schema == type(result.query).__name__


def test_ml_mode_isolates_h20_source_and_never_merges_its_counts(qtbot):
    host, workspace, pages = _workspace(qtbot)
    h20 = pages[-1]
    host.result_source_tabs.addTab(h20, "個人化 H20")
    workspace.sync_sources()
    normal = pages[-3]
    normal_entry = next(item for item in workspace._sources if item.widget is normal)
    assert workspace.select_source(normal_entry.key)
    assert workspace.set_ml_mode(True)
    h20_entry = next(item for item in workspace._sources if item.widget is h20)
    assert workspace.combo.count() == 1
    assert workspace.combo.itemData(0) == h20_entry.key
    assert workspace.select_source(h20_entry.key)
    assert workspace.tabs.currentWidget() is h20
    assert workspace.select_source(0)
    assert workspace.tabs.currentWidget() is h20
    assert workspace.set_ml_mode(False)
    assert workspace.tabs.currentWidget() is normal
    assert workspace.combo.currentData() == normal_entry.key
    assert workspace.set_ml_mode(True)
    assert workspace.tabs.currentWidget() is h20
    assert h20.run_count == normal.run_count == 0
    assert workspace.set_ml_mode(False)
    assert workspace.tabs.currentWidget() is normal
    assert workspace.combo.count() == sum(not item.ml for item in workspace._sources) + 2
    assert workspace.combo.findData("__unwired_revenue__") == -1
    assert workspace.combo.findData("__unwired_institutional__") >= 0
    assert not workspace.combo.model().item(workspace.combo.findData("__unwired_institutional__")).isEnabled()


def test_quick_routes_require_exact_mounted_source_class_and_show_missing_reason(qtbot):
    _host, workspace, _pages = _workspace(qtbot)
    assert workspace.source_route_group_label.text() == "來源"
    assert workspace.condition_recipe_group_label.text() == "條件範本"
    assert workspace.disabled_note.text() == "先載入並核驗保存來源；套用條件後仍需明確查詢。"
    revenue = workspace.quick_route_buttons["official_technical_revenue"]
    composite = workspace.quick_route_buttons["official_technical_price"]
    price = workspace.quick_route_buttons["price_universe"]
    assert not revenue.isEnabled()
    assert not composite.isEnabled()
    assert not price.isEnabled()
    assert "尚未掛載" in revenue.toolTip()
    assert not workspace.select_recipe("official_technical_revenue")
    assert not workspace.select_recipe("unknown_recipe")
    assert "題材條件" in workspace.unavailable_conditions.text()
    assert "財報條件" in workspace.unavailable_conditions.text()
    assert "月營收可由" in workspace.unavailable_conditions.text()


def test_condition_recipe_routes_without_query_and_keeps_return_source(qtbot):
    host, workspace, pages = _workspace(qtbot)
    applied = []

    class _RecipePage(_Page):
        def apply_condition_recipe(self, key):
            applied.append(key)
            return True

    recipe_page = _RecipePage("dailyTechnicalV4RecipeSource")
    nested = pages[2]
    nested.addTab(recipe_page, "每日技術規則研究")
    workspace._CONDITION_RECIPE_SOURCE = (
        type(recipe_page).__module__, type(recipe_page).__name__
    )
    workspace.sync_sources()

    original = next(item for item in workspace._sources if item.widget is pages[3])
    assert workspace.select_source(original.key)
    button = workspace.condition_recipe_buttons["macd_golden_cross"]
    assert button.isEnabled()
    button.click()

    assert applied == ["macd_golden_cross"]
    assert host.result_source_tabs.currentWidget() is pages[1]
    assert nested.currentWidget() is recipe_page
    assert recipe_page.run_count == 0
    assert "尚未查詢" in workspace.disabled_note.text()
    assert workspace.select_source(original.key)
    assert nested.currentWidget() is pages[3]


def test_v4_condition_recipe_changes_only_rule_controls_and_never_queries(qtbot):
    from ui_qt.views.daily_market_technical_universe_v4_view import (
        DailyMarketTechnicalUniverseV4View,
    )

    rule_keys = (
        "ma5_20_golden_cross",
        "kd_golden_cross",
        "macd_golden_cross",
        "volume_ratio_20_including_current",
        "volume_ratio_5_including_current",
    )
    rule_filters = {}
    emitted = []
    for key in rule_keys:
        combo = QComboBox()
        combo.addItem("不限制", "all")
        combo.addItem("符合", "match")
        combo.addItem("未知", "unknown")
        combo.setCurrentIndex(2)
        combo.currentIndexChanged.connect(lambda _index, name=key: emitted.append(name))
        rule_filters[key] = combo
        qtbot.addWidget(combo)
    mode = QComboBox()
    mode.addItem("OR", "OR")
    mode.addItem("AND", "AND")
    mode.setCurrentIndex(0)
    mode.currentIndexChanged.connect(lambda _index: emitted.append("mode"))
    stock_filter = QLineEdit("2330")
    qtbot.addWidget(mode)
    qtbot.addWidget(stock_filter)
    original_query = SimpleNamespace(method_rule_keys=rule_keys)
    view = SimpleNamespace(
        _query=original_query,
        _closing=False,
        _worker=None,
        _pending=None,
        _rule_filters=rule_filters,
        mode=mode,
        stock_filter=stock_filter,
    )

    for recipe, target in (
        ("ma5_20_golden_cross", "ma5_20_golden_cross"),
        ("kd_golden_cross", "kd_golden_cross"),
        ("macd_golden_cross", "macd_golden_cross"),
    ):
        assert DailyMarketTechnicalUniverseV4View.apply_condition_recipe(view, recipe)
        assert mode.currentData() == "AND"
        assert all(
            combo.currentData() == ("match" if key == target else "all")
            for key, combo in rule_filters.items()
        )
        assert view._query is original_query
        assert stock_filter.text() == "2330"
        assert emitted == []

    before = (mode.currentData(), tuple(combo.currentData() for combo in rule_filters.values()))
    assert not DailyMarketTechnicalUniverseV4View.apply_condition_recipe(view, "unknown")
    view._query = None
    assert not DailyMarketTechnicalUniverseV4View.apply_condition_recipe(
        view, "ma5_20_golden_cross"
    )
    view._query = original_query
    view._worker = object()
    assert not DailyMarketTechnicalUniverseV4View.apply_condition_recipe(
        view, "ma5_20_golden_cross"
    )
    assert (mode.currentData(), tuple(combo.currentData() for combo in rule_filters.values())) == before
