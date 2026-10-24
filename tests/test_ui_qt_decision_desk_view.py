import os
import threading
import time
from datetime import date, datetime, timezone
from dataclasses import replace
from zoneinfo import ZoneInfo

import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QFrame, QPushButton, QScrollArea

from app_module.decision_desk_dtos import (
    DecisionDeskQuality,
    DecisionDeskSnapshot,
    MarketBreadthSummary,
    MarketRegimeSummary,
    PortfolioAlertSummary,
    SectorRotationSummary,
    WatchlistTriggerSummary,
    RelativeStrengthLiquiditySummary,
    DecisionDeskRiskPrompt,
    DecisionDeskRiskPromptSummary,
    PortfolioAlertAttribution,
    DecisionDeskActionSummary,
    DecisionDeskSectorCard,
    DecisionDeskSectorFocus,
    DecisionDeskStockCard,
    DecisionDeskStockFocus,
    IndustryRepresentativeStock,
    IndustryStrengthRow,
    IndustryStrengthSummary,
)
from app_module.decision_desk_service import DecisionDeskSnapshotBuilder
from app_module.exceptions import BacktestCancelledError
from app_module.market_data_visibility_dtos import (
    InstitutionalFlowMarketSummary,
    MarketDataVisibilitySummary,
    MonthlyRevenueBreadthSummary,
    SourceVisibilityStatus,
)
from ui_qt.theme import MIDNIGHT_ANALYST
import ui_qt.views.decision_desk_view as decision_desk_view_module
from ui_qt.views.decision_desk_view import DecisionDeskView


class FakeBuilder:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def build_snapshot(self, as_of_date: date) -> DecisionDeskSnapshot:
        self.calls.append(as_of_date)
        return self.snapshot


def _snapshot(
    *,
    as_of_date: date = date(2026, 6, 15),
    overall_quality: DecisionDeskQuality = DecisionDeskQuality.OBSERVED,
    market_regime_quality=DecisionDeskQuality.OBSERVED,
    market_breadth_quality=DecisionDeskQuality.OBSERVED,
    sector_rotation_quality=DecisionDeskQuality.OBSERVED,
    relative_strength_liquidity_quality=DecisionDeskQuality.OBSERVED,
    watchlist_quality=DecisionDeskQuality.OBSERVED,
    portfolio_quality=DecisionDeskQuality.OBSERVED,
    risk_prompts_quality=DecisionDeskQuality.OBSERVED,
    market_regime_warnings=(),
    market_breadth_warnings=(),
    sector_rotation_warnings=(),
    relative_strength_liquidity_warnings=(),
    watchlist_warnings=(),
    portfolio_warnings=(),
    risk_prompts_warnings=(),
    overall_warnings=(),
    market_data_visibility=None,
) -> DecisionDeskSnapshot:
    as_of = as_of_date
    return DecisionDeskSnapshot(
        as_of_date=as_of,
        generated_at=datetime(2026, 6, 15, 9, 0, 0),
        schema_version=1,
        overall_quality=overall_quality,
        market_regime=MarketRegimeSummary(
            as_of_date=as_of,
            quality=market_regime_quality,
            warnings=market_regime_warnings,
            regime_label="風險中性",
            regime_score=50,
            regime_confidence=7700,
        ),
        market_breadth=MarketBreadthSummary(
            as_of_date=as_of,
            quality=market_breadth_quality,
            warnings=market_breadth_warnings,
            breadth_ratio_bp=4200,
            advancing=120,
            declining=80,
            unchanged=20,
        ),
        sector_rotation=SectorRotationSummary(
            as_of_date=as_of,
            quality=sector_rotation_quality,
            warnings=sector_rotation_warnings,
            leading_sector="半導體",
            trailing_sector="金融",
            rotation_intensity_bp=150,
        ),
        relative_strength_liquidity=RelativeStrengthLiquiditySummary(
            as_of_date=as_of,
            quality=relative_strength_liquidity_quality,
            warnings=relative_strength_liquidity_warnings,
            top_strength_codes=("2330", "2454"),
            weak_strength_codes=("1101",),
            low_liquidity_codes=(),
        ),
        watchlist_triggers=WatchlistTriggerSummary(
            as_of_date=as_of,
            quality=watchlist_quality,
            warnings=watchlist_warnings,
            trigger_count=2,
            triggered_codes=("2330", "2603"),
            top_signal="momentum_breakout",
        ),
        portfolio_alerts=PortfolioAlertSummary(
            as_of_date=as_of,
            quality=portfolio_quality,
            warnings=portfolio_warnings,
            alert_count=1,
            alert_codes=("AAPL",),
            alert_level="low",
        ),
        risk_prompts=DecisionDeskRiskPromptSummary(
            as_of_date=as_of,
            quality=risk_prompts_quality,
            warnings=risk_prompts_warnings,
            prompts=(),
        ),
        action_summary=DecisionDeskActionSummary(
            action_level="積極研究",
            headline="今日主結論：積極研究，市場廣度偏強",
            research_mode_note="研究模式：以下為市場與籌碼輔助判讀，不是交易建議。",
            reasons=("市場狀態：風險中性",),
        ),
        sector_focus=DecisionDeskSectorFocus(
            priority_sectors=(
                DecisionDeskSectorCard("半導體", "priority", "產業輪動領先", DecisionDeskQuality.OBSERVED, "強勢產業"),
            ),
            risk_sectors=(
                DecisionDeskSectorCard("金融", "risk", "產業輪動落後", DecisionDeskQuality.OBSERVED, "弱勢產業"),
            ),
        ),
        stock_focus=DecisionDeskStockFocus(
            priority_stocks=(
                DecisionDeskStockCard("2330", "2330", "priority", "相對強勢名單", "relative_strength"),
            ),
            risk_stocks=(
                DecisionDeskStockCard("2603", "2603", "risk", "持倉或觀察清單風險提示", "portfolio_watchlist"),
            ),
        ),
        market_data_visibility=market_data_visibility,
        warnings=overall_warnings,
    )


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def rendered_view(builder, *, as_of_date: date | None = None) -> DecisionDeskView:
    view = DecisionDeskView(builder, as_of_date=as_of_date, auto_refresh=False, async_refresh=False)
    view.refresh_snapshot()
    return view


def test_decision_desk_view_initialization_does_not_call_builder():
    app()
    builder = FakeBuilder(_snapshot())

    view = DecisionDeskView(builder)

    assert builder.calls == []
    assert "尚未載入" in view.overall_status_label.text()


def test_decision_desk_default_date_uses_taipei_across_host_midnight(monkeypatch):
    app()
    taipei_date = date(2026, 10, 5)
    pacific_date = date(2026, 10, 4)
    pacific = ZoneInfo("America/Los_Angeles")

    # Both instants fall on October 4 in Los Angeles while already on October
    # 5 in Taipei, including times on either side of UTC midnight.
    for instant_utc in (
        datetime(2026, 10, 4, 16, 30, tzinfo=timezone.utc),
        datetime(2026, 10, 5, 6, 30, tzinfo=timezone.utc),
    ):
        assert instant_utc.astimezone(pacific).date() == pacific_date

        class FrozenDateTime:
            @classmethod
            def now(cls, tz=None):
                assert tz is timezone.utc
                return instant_utc.astimezone(tz)

        monkeypatch.setattr(decision_desk_view_module, "datetime", FrozenDateTime)
        view = DecisionDeskView(
            FakeBuilder(_snapshot()),
            auto_refresh=False,
            async_refresh=False,
        )
        assert view.as_of_date == taipei_date
        assert view.decision_date_card.value_label.text() == taipei_date.isoformat()
        view.close()


def test_decision_desk_preserves_explicit_historical_date_without_reading_clock(monkeypatch):
    app()

    class ForbiddenClock:
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("explicit as_of_date must not consult the default clock")

    monkeypatch.setattr(decision_desk_view_module, "datetime", ForbiddenClock)
    explicit_date = date(2026, 6, 15)
    view = DecisionDeskView(
        FakeBuilder(_snapshot()),
        as_of_date=explicit_date,
        auto_refresh=False,
        async_refresh=False,
    )
    assert view.as_of_date == explicit_date
    assert view.decision_date_card.value_label.text() == explicit_date.isoformat()
    view.close()


def test_default_decision_desk_refresh_recomputes_taipei_date_and_historical_date_stays_pinned():
    app()
    instants = iter(
        (
            datetime(2026, 10, 6, 15, 59, 59, tzinfo=timezone.utc),
            datetime(2026, 10, 6, 16, 0, tzinfo=timezone.utc),
        )
    )
    current_builder = FakeBuilder(_snapshot(as_of_date=date(2026, 10, 7)))
    current_view = DecisionDeskView(
        current_builder,
        auto_refresh=False,
        async_refresh=False,
        clock=lambda: next(instants),
    )

    assert current_view.as_of_date == date(2026, 10, 6)
    current_view.refresh_snapshot()
    assert current_view.as_of_date == date(2026, 10, 7)
    assert current_builder.calls == [date(2026, 10, 7)]
    assert "本次評估日（台北）：2026-10-07" in current_view.generated_at_label.text()
    assert "快照判讀日：2026-10-07" in current_view.generated_at_label.text()
    current_view.close()

    historical_calls = []
    historical_date = date(2026, 6, 15)
    historical_builder = FakeBuilder(_snapshot())
    historical_view = DecisionDeskView(
        historical_builder,
        as_of_date=historical_date,
        auto_refresh=False,
        async_refresh=False,
        clock=lambda: historical_calls.append("called"),
    )
    historical_view.refresh_snapshot()

    assert historical_calls == []
    assert historical_view.as_of_date == historical_date
    assert historical_builder.calls == [historical_date]
    historical_view.close()


def test_decision_desk_view_auto_refreshes_when_first_shown():
    app_instance = app()
    builder = FakeBuilder(_snapshot())
    target_date = date(2026, 6, 15)
    view = DecisionDeskView(
        builder,
        as_of_date=target_date,
        auto_refresh=True,
        async_refresh=False,
    )

    view.show()
    app_instance.processEvents()

    assert builder.calls == [target_date]
    view.close()


def test_closing_decision_desk_cancels_worker_and_closes_after_native_thread_finishes():
    app_instance = app()
    started = threading.Event()
    cancellation_seen = threading.Event()
    native_thread_finished = threading.Event()

    class CancellableBuilder:
        def build_snapshot(self, as_of_date: date, cancel_callback=None):
            started.set()
            while True:
                if cancel_callback():
                    cancellation_seen.set()
                    break
                time.sleep(0.005)
            raise BacktestCancelledError("載入已取消")

    view = DecisionDeskView(
        CancellableBuilder(),
        as_of_date=date(2026, 6, 15),
        auto_refresh=False,
        async_refresh=True,
    )
    view.show()
    view.refresh_snapshot()

    deadline = time.monotonic() + 2
    while not started.is_set() and time.monotonic() < deadline:
        app_instance.processEvents()
        time.sleep(0.005)
    assert started.is_set()

    worker = view._refresh_worker
    assert worker is not None
    worker.native_thread_finished.connect(native_thread_finished.set)
    view.close()
    assert view._closing

    deadline = time.monotonic() + 3
    while not (
        native_thread_finished.is_set()
        and view._refresh_worker is None
        and not view.isVisible()
    ):
        app_instance.processEvents()
        if time.monotonic() >= deadline:
            break
        time.sleep(0.005)

    assert cancellation_seen.is_set()
    assert native_thread_finished.is_set()
    assert view._refresh_worker is None
    assert not view.isVisible()
    assert view._last_snapshot is None


def test_decision_desk_view_refresh_calls_builder_and_renders_snapshot():
    app()
    s = _snapshot()
    builder = FakeBuilder(s)
    target_date = date(2026, 6, 15)
    view = rendered_view(builder, as_of_date=target_date)

    assert builder.calls == [target_date]
    assert view.overall_status_label.text() == "摘要已載入"
    assert "2026-06-15" in view.generated_at_label.text()


def test_decision_desk_explains_watchlist_changes_and_missing_previous_score():
    app()
    snapshot = _snapshot()
    snapshot = replace(snapshot, watchlist_triggers=replace(
        snapshot.watchlist_triggers,
        trigger_count=2,
        triggered_codes=("2330", "2603"),
        top_signal="new=2330;down=2603",
        warnings=("watchlist_trigger_previous_unknown:2330",),
    ))
    view = rendered_view(FakeBuilder(snapshot))
    text = view.watchlist_triggers_value.text()
    assert "2330：目前分數達觀察門檻，但缺前次分數" in text
    assert "2603：分數較前次下降" in text
    assert "資料日：2026-06-15" in text
    assert "查看選中個股研究報告" in text
    view.close()


def test_decision_desk_view_renders_answer_first_dashboard():
    app()
    view = rendered_view(FakeBuilder(_snapshot()))

    assert "今日主結論" in view.action_headline_label.text()
    assert "不是交易建議" in view.action_note_label.text()
    assert "半導體" in view.priority_sector_label.text()
    assert "金融" in view.risk_sector_label.text()
    assert "2330" in view.priority_stock_label.text()
    assert "2603" in view.risk_stock_label.text()


def test_decision_desk_view_stock_focus_buttons_drill_down_to_smart_money():
    app()
    called: list[str] = []
    view = DecisionDeskView(
        FakeBuilder(_snapshot()),
        auto_refresh=False,
        async_refresh=False,
        navigate_to_smart_money_callback=lambda code: called.append(code),
    )
    view.refresh_snapshot()

    view._navigate_to_smart_money("2330")

    assert called == ["2330"]
    assert any(button.text() == "2330" for button in view.stock_focus_buttons)


def test_decision_desk_view_focus_opens_shared_stock_research_context():
    app()
    contexts: list[object] = []
    view = DecisionDeskView(
        FakeBuilder(_snapshot()),
        auto_refresh=False,
        async_refresh=False,
    )
    view.stockResearchRequested.connect(contexts.append)
    view.refresh_snapshot()

    assert view.stock_focus_research_button.isEnabled()
    assert view.stock_focus_research_button.text() == "開啟 2330 研究報告"
    view.stock_focus_research_button.click()

    assert len(contexts) == 1
    context = contexts[0]
    assert context.stock_code == "2330"
    assert context.source_workspace == "market_explore"
    assert context.source_kind == "decision_desk"
    assert context.decision_date == "2026-06-15"


def test_decision_desk_view_renders_comparable_industry_card_and_drills_to_representative_stock():
    app()
    base = _snapshot()
    strength = IndustryStrengthSummary(
        as_of_date=date(2026, 6, 15),
        quality=DecisionDeskQuality.DEGRADED,
        warnings=("industry_mapping_current_research_only",),
        source_version="industry-strength.current-research.v1",
        mapping_source_id="meta_data.companies.csv",
        mapping_version="tw-industry-explicit-map.v1",
        mapping_observed_date=date(2026, 6, 14),
        mapping_available_at="2026-06-14T08:00:00+08:00",
        rows=(
            IndustryStrengthRow(
                industry_name="半導體",
                index_name="半導體類指數",
                industry_level="leaf",
                market_scope="twse",
                return_5d_bp=200,
                return_20d_bp=500,
                excess_5d_bp=100,
                excess_20d_bp=300,
                coverage_5d_bp=10000,
                coverage_20d_bp=10000,
                constituent_count=1,
                eligible_stock_count_5d=1,
                eligible_stock_count_20d=1,
                representative_stocks=(
                    IndustryRepresentativeStock(
                        stock_code="2330",
                        stock_name="台積電",
                        industry_name="半導體",
                    ),
                ),
            ),
        ),
    )
    snapshot = replace(
        base,
        sector_rotation=SectorRotationSummary(
            as_of_date=date(2026, 6, 15),
            quality=DecisionDeskQuality.DEGRADED,
            warnings=("industry_mapping_current_research_only",),
            leading_sector="半導體",
            industry_strength=strength,
        ),
    )
    contexts: list[object] = []
    view = DecisionDeskView(FakeBuilder(snapshot), auto_refresh=False, async_refresh=False)
    view.stockResearchRequested.connect(contexts.append)
    view.refresh_snapshot()

    assert "可比產業" in view.sector_rotation_value.text()
    assert "current research only" in view.sector_rotation_value.text()
    assert view.industry_focus_buttons
    view.industry_focus_buttons[0].click()

    assert len(contexts) == 1
    context = contexts[0]
    assert context.stock_code == "2330"
    assert context.source_kind == "industry_strength"
    assert context.source_label == "市場總覽／半導體代表股"
    assert context.data_date == "2026-06-15"
    assert context.source_version == "industry-strength.current-research.v1"
    assert context.mapping_source_id == "meta_data.companies.csv"
    assert context.mapping_version == "tw-industry-explicit-map.v1"
    assert context.mapping_observed_date == "2026-06-14"
    assert context.has_source is True


def test_industry_strength_chart_separates_groups_distinguishes_unknown_and_zero_and_drills_nonleading_row():
    app()
    base = _snapshot()
    strength = IndustryStrengthSummary(
        as_of_date=date(2026, 6, 13),
        quality=DecisionDeskQuality.DEGRADED,
        warnings=("industry_mapping_current_research_only",),
        source_id="industry_strength.snapshot",
        source_version="snapshot-v2",
        mapping_observed_date=date(2026, 6, 12),
        rows=(
            IndustryStrengthRow(
                industry_name="領先列",
                index_name="領先指數",
                industry_level="leaf",
                market_scope="twse",
                excess_5d_bp=100,
                excess_20d_bp=200,
                coverage_5d_bp=10000,
                coverage_20d_bp=9000,
                representative_stocks=(
                    IndustryRepresentativeStock(
                        stock_code="0001",
                        stock_name="舊代表股",
                        industry_name="領先列",
                    ),
                ),
            ),
            IndustryStrengthRow(
                industry_name="非領先列",
                index_name="非領先指數",
                industry_level="leaf",
                market_scope="twse",
                excess_5d_bp=0,
                excess_20d_bp=None,
                coverage_5d_bp=8000,
                coverage_20d_bp=None,
                representative_stocks=(
                    IndustryRepresentativeStock(
                        stock_code="1234",
                        stock_name="非領先代表股",
                        industry_name="非領先列",
                    ),
                ),
            ),
            IndustryStrengthRow(
                industry_name="尾列",
                index_name="尾列指數",
                industry_level="leaf",
                market_scope="twse",
                excess_5d_bp=-50,
                excess_20d_bp=-100,
            ),
            IndustryStrengthRow(
                industry_name="整體層級",
                index_name="整體指數",
                industry_level="aggregate",
                market_scope="twse",
                excess_5d_bp=500,
                excess_20d_bp=700,
            ),
        ),
    )
    snapshot = replace(
        base,
        sector_rotation=SectorRotationSummary(
            as_of_date=date(2026, 6, 13),
            quality=DecisionDeskQuality.DEGRADED,
            warnings=("industry_mapping_current_research_only",),
            leading_sector="領先列",
            trailing_sector="尾列",
            industry_strength=strength,
        ),
    )
    contexts: list[object] = []
    view = DecisionDeskView(FakeBuilder(snapshot), auto_refresh=False, async_refresh=False)
    view.stockResearchRequested.connect(contexts.append)
    view.refresh_snapshot()

    selector = view.industry_strength_group_selector
    assert selector.count() == 2
    assert tuple(selector.currentData()) == ("leaf", "twse")
    assert selector.currentText() == "層級：細分產業｜市場範圍：上市（TWSE）"
    assert "industry_level=leaf" in selector.accessibleDescription()
    assert "TAIEX" in view.industry_strength_meta.text()
    assert "僅供當期研究（非歷史 PIT）" in view.industry_strength_meta.text()
    assert "current research only" in view.industry_strength_meta.toolTip()
    assert "摘要覆蓋：Unknown" in view.industry_strength_meta.toolTip()
    assert "industry_strength.snapshot" in view.industry_strength_meta.toolTip()
    assert view.industry_strength_leading_button.isEnabled()
    assert view.industry_strength_trailing_button.isEnabled()
    assert "領先列（可定位）" in view.industry_strength_navigation_status.text()
    chart_text = " ".join(label.text() for label in view.industry_strength_chart_content.findChildren(QLabel))
    assert "+0 bp" in chart_text
    assert "Unknown（缺值）" in chart_text
    assert "覆蓋 8,000 bp" in chart_text
    assert all(button.text() != "整體層級" for button in view._industry_strength_row_buttons)
    assert all(
        bar.property("scaleMaxAbsBp") == 200
        for bar in view.industry_strength_chart_content.findChildren(QFrame, "decisionDeskIndustryStrengthBar")
    )

    selector.setCurrentIndex(1)
    assert tuple(selector.currentData()) == ("aggregate", "twse")
    assert selector.currentText() == "層級：整體層級｜市場範圍：上市（TWSE）"
    assert "industry_level=aggregate" in selector.accessibleDescription()
    assert [button.text() for button in view._industry_strength_row_buttons] == ["整體層級"]
    selector.setCurrentIndex(0)
    assert [button.text() for button in view._industry_strength_row_buttons] == ["領先列", "非領先列", "尾列"]

    old_representative_buttons = view.industry_strength_representatives.findChildren(QPushButton)
    assert [button.text() for button in old_representative_buttons] == ["0001 舊代表股"]
    old_representative_button = old_representative_buttons[0]
    row_buttons_before = tuple(view._industry_strength_row_buttons)
    chart_scrollbar = view.industry_strength_chart_scroll.verticalScrollBar()
    chart_scrollbar.setValue(chart_scrollbar.maximum())
    scroll_position_before = chart_scrollbar.value()
    row_buttons_before[1].click()
    assert all(
        before is after
        for before, after in zip(row_buttons_before, view._industry_strength_row_buttons)
    )
    assert chart_scrollbar.value() == scroll_position_before
    assert old_representative_button.isHidden()
    assert not old_representative_button.isEnabled()
    assert old_representative_button.parent() is None
    old_representative_button.click()
    assert contexts == []
    representative_buttons = view.industry_strength_representatives.findChildren(QPushButton)
    assert [button.text() for button in representative_buttons] == ["1234 非領先代表股"]
    representative_buttons[0].click()
    assert len(contexts) == 1
    assert contexts[0].stock_code == "1234"
    assert contexts[0].source_label == "市場總覽／非領先列代表股"
    assert contexts[0].data_date == "2026-06-13"
    assert contexts[0].source_version == "snapshot-v2"

    view._display_loading_snapshot()
    assert view._industry_strength_rows == ()
    assert view.industry_strength_group_selector.count() == 0
    assert not view.industry_strength_chart_scroll.isVisible()
    assert not view.industry_strength_leading_button.isEnabled()
    assert not view.industry_strength_trailing_button.isEnabled()
    assert "沒有可用快照列" in view.industry_strength_navigation_status.text()
    assert view.industry_strength_empty_state.isHidden()
    view._display_exception_snapshot("snapshot unavailable")
    assert view._industry_strength_rows == ()
    assert "Unknown" in view.industry_strength_meta.text()


def test_industry_strength_headline_navigation_finds_deep_row_across_groups_in_32_rows():
    application = app()
    base = _snapshot()
    rows = tuple(
        IndustryStrengthRow(
            industry_name=f"{level_label}-{index:02d}",
            index_name=f"{level_label}指數-{index:02d}",
            industry_level=level,
            market_scope="twse",
            excess_5d_bp=index,
            excess_20d_bp=None if level == "leaf" else -index,
            coverage_5d_bp=10000,
            coverage_20d_bp=10000,
            representative_stocks=(
                IndustryRepresentativeStock(
                    stock_code="9001",
                    stock_name="定位代表股",
                    industry_name=f"{level_label}-{index:02d}",
                ),
            ) if level == "aggregate" and index == 15 else (),
        )
        for level, level_label in (("leaf", "細分"), ("aggregate", "整體"))
        for index in range(16)
    )
    strength = IndustryStrengthSummary(
        as_of_date=date(2026, 6, 13),
        quality=DecisionDeskQuality.DEGRADED,
        warnings=("current_research_only",),
        rows=rows,
    )
    snapshot = replace(
        base,
        sector_rotation=SectorRotationSummary(
            as_of_date=date(2026, 6, 13),
            quality=DecisionDeskQuality.DEGRADED,
            warnings=("current_research_only",),
            leading_sector="整體-00",
            trailing_sector="整體-15",
            industry_strength=strength,
        ),
    )
    builder = FakeBuilder(snapshot)
    view = DecisionDeskView(builder, auto_refresh=False, async_refresh=False)
    view.resize(1280, 760)
    view.refresh_snapshot()
    view.show()
    application.processEvents()

    assert len(view._industry_strength_rows) == 32
    assert all(row.excess_20d_bp is None for row in rows if row.industry_level == "leaf")
    assert all(row.excess_20d_bp is not None for row in rows if row.industry_level == "aggregate")
    assert tuple(view.industry_strength_group_selector.currentData()) == ("leaf", "twse")
    view.industry_strength_trailing_button.click()

    assert tuple(view.industry_strength_group_selector.currentData()) == ("aggregate", "twse")
    assert view._industry_strength_selected_name == "整體-15"
    assert [button.text() for button in view._industry_strength_row_buttons][-1] == "整體-15"
    assert view._industry_strength_row_buttons[-1].isChecked()
    application.processEvents()
    assert view.industry_strength_chart_scroll.verticalScrollBar().value() > 0
    viewport = view.industry_strength_chart_scroll.viewport()
    target_row = view._industry_strength_row_widgets[("aggregate", "twse", "整體-15")]
    target_top = target_row.mapTo(viewport, target_row.rect().topLeft()).y()
    assert target_top >= 0
    assert target_top + target_row.height() <= viewport.height()
    outer_viewport = view.main_scroll_area.viewport()
    outer_top = target_row.mapTo(outer_viewport, target_row.rect().topLeft()).y()
    assert outer_top >= 0
    assert outer_top + target_row.height() <= outer_viewport.height()
    assert "資料日 2026-06-13" in view.industry_strength_meta.text()
    representatives = view.industry_strength_representatives.findChildren(QPushButton)
    assert [button.text() for button in representatives] == ["9001 定位代表股"]
    representative_top = representatives[0].mapTo(
        outer_viewport, representatives[0].rect().topLeft()
    ).y()
    assert representative_top >= 0
    assert representative_top + representatives[0].height() <= outer_viewport.height()

    view.industry_strength_chart_scroll.verticalScrollBar().setValue(0)
    view.industry_strength_trailing_button.click()
    refreshed_rows = tuple(
        IndustryStrengthRow(
            industry_name=f"新快照-{index:02d}",
            index_name=f"新快照指數-{index:02d}",
            industry_level="leaf",
            market_scope="twse",
            excess_5d_bp=index,
            excess_20d_bp=index * 2,
        )
        for index in range(18)
    )
    refreshed_strength = IndustryStrengthSummary(
        as_of_date=date(2026, 6, 14),
        quality=DecisionDeskQuality.OBSERVED,
        warnings=(),
        rows=refreshed_rows,
    )
    builder.snapshot = replace(
        base,
        sector_rotation=SectorRotationSummary(
            as_of_date=date(2026, 6, 14),
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
            leading_sector="新快照-00",
            trailing_sector="新快照-17",
            industry_strength=refreshed_strength,
        ),
    )
    view.refresh_snapshot()
    assert view._industry_strength_selected_name == "新快照-00"
    application.processEvents()
    assert view.industry_strength_chart_scroll.verticalScrollBar().value() == 0
    view.close()


def test_industry_strength_all_unknown_group_keeps_metadata_and_partial_unknown_remains_charted():
    app()
    base = _snapshot()
    strength = IndustryStrengthSummary(
        as_of_date=date(2026, 6, 14),
        quality=DecisionDeskQuality.DEGRADED,
        warnings=("industry_index_values_missing",),
        source_id="industry_strength.all_unknown",
        rows=(
            IndustryStrengthRow(
                industry_name="全缺值 A",
                index_name="A 指數",
                industry_level="leaf",
                market_scope="twse",
                excess_5d_bp=None,
                excess_20d_bp=None,
            ),
            IndustryStrengthRow(
                industry_name="全缺值 B",
                index_name="B 指數",
                industry_level="leaf",
                market_scope="twse",
                excess_5d_bp=None,
                excess_20d_bp=None,
            ),
            IndustryStrengthRow(
                industry_name="部分缺值",
                index_name="C 指數",
                industry_level="aggregate",
                market_scope="twse",
                excess_5d_bp=0,
                excess_20d_bp=None,
            ),
        ),
    )
    snapshot = replace(
        base,
        sector_rotation=SectorRotationSummary(
            as_of_date=date(2026, 6, 14),
            quality=DecisionDeskQuality.DEGRADED,
            warnings=(),
            leading_sector=None,
            trailing_sector="不在列中的名稱",
            industry_strength=strength,
        ),
    )
    view = DecisionDeskView(FakeBuilder(snapshot), auto_refresh=False, async_refresh=False)
    view.refresh_snapshot()

    assert view.industry_strength_group_selector.isEnabled()
    assert view.industry_strength_group_selector.count() == 2
    assert "此群組 5 日與 20 日超額值皆為 Unknown" in view.industry_strength_empty_state.text()
    assert not view.industry_strength_empty_state.isHidden()
    assert view.industry_strength_chart_scroll.isHidden()
    assert "2026-06-14" in view.industry_strength_meta.text()
    assert "品質" in view.industry_strength_meta.text()
    assert "industry_strength.all_unknown" in view.industry_strength_meta.toolTip()
    assert not view.industry_strength_leading_button.isEnabled()
    assert not view.industry_strength_trailing_button.isEnabled()
    assert "未出現在產業列表" in view.industry_strength_navigation_status.text()

    view.industry_strength_group_selector.setCurrentIndex(1)
    assert view.industry_strength_empty_state.isHidden()
    assert not view.industry_strength_chart_scroll.isHidden()
    assert [button.text() for button in view._industry_strength_row_buttons] == ["部分缺值"]
    chart_text = " ".join(label.text() for label in view.industry_strength_chart_content.findChildren(QLabel))
    assert "+0 bp" in chart_text
    assert "Unknown（缺值）" in chart_text


def test_industry_strength_chart_keeps_full_row_viewport_and_representatives_below_at_1280_width():
    application = app()
    base = _snapshot()
    strength = IndustryStrengthSummary(
        as_of_date=date(2026, 6, 15),
        quality=DecisionDeskQuality.OBSERVED,
        warnings=(),
        rows=(
            IndustryStrengthRow(
                industry_name="半導體",
                index_name="半導體類指數",
                industry_level="leaf",
                market_scope="twse",
                excess_5d_bp=100,
                excess_20d_bp=250,
                coverage_5d_bp=10000,
                coverage_20d_bp=10000,
                representative_stocks=(
                    IndustryRepresentativeStock(
                        stock_code="2330",
                        stock_name="台積電",
                        industry_name="半導體",
                    ),
                ),
            ),
        ),
    )
    snapshot = replace(
        base,
        sector_rotation=SectorRotationSummary(
            as_of_date=date(2026, 6, 15),
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
            leading_sector="半導體",
            industry_strength=strength,
        ),
    )
    view = DecisionDeskView(FakeBuilder(snapshot), auto_refresh=False, async_refresh=False)
    view.resize(1280, 760)
    view.refresh_snapshot()
    view.show()
    application.processEvents()

    main_scroll = view.findChild(QScrollArea, "decisionDeskMainScrollArea")
    assert main_scroll is not None
    assert main_scroll.widgetResizable()
    viewport = view.industry_strength_chart_scroll.viewport()
    assert viewport.height() >= 220
    first_industry_row = view.industry_strength_chart_layout.itemAt(1).widget()
    assert first_industry_row is not None
    assert first_industry_row.height() <= viewport.height()
    assert view.industry_strength_representatives.isVisible()
    assert (
        view.industry_strength_representatives.geometry().top()
        >= view.industry_strength_chart_scroll.geometry().bottom() + 1
    )

    view.close()


def test_decision_desk_view_shows_degraded_status():
    app()
    s = _snapshot(
        overall_quality=DecisionDeskQuality.DEGRADED,
        market_breadth_quality=DecisionDeskQuality.DEGRADED,
        market_breadth_warnings=("market_breadth_fetch_error:timeout",),
    )
    view = rendered_view(FakeBuilder(s))

    assert view.overall_status_label.text() == "摘要已載入"
    assert "降級" in view.market_breadth_status.text()
    assert "降級" in view._status_badges[view.market_breadth_status].text()


def test_decision_desk_view_shows_missing_status():
    app()
    s = _snapshot(
        overall_quality=DecisionDeskQuality.MISSING,
        market_regime_quality=DecisionDeskQuality.MISSING,
        market_regime_warnings=("no_data",),
    )
    view = rendered_view(FakeBuilder(s))

    assert view.overall_status_label.text() == "摘要已載入"
    assert "資料缺件" in view.market_regime_status.text()
    assert "資料缺件" in view._status_badges[view.market_regime_status].text()
    assert "資料可見性：缺漏" in view.overall_warn_label.toPlainText()


def test_decision_desk_view_aggregates_warning_lines_and_refresh_button():
    app()
    s = _snapshot(
        overall_quality=DecisionDeskQuality.DEGRADED,
        watchlist_quality=DecisionDeskQuality.DEGRADED,
        watchlist_warnings=("watchlist_stale",),
        overall_warnings=("global_warning",),
        sector_rotation_quality=DecisionDeskQuality.MISSING,
        sector_rotation_warnings=("sector_missing",),
    )
    builder = FakeBuilder(s)
    view = rendered_view(builder)
    view.refresh_btn.click()

    assert builder.calls
    combined_text = view.overall_warn_label.toPlainText()
    assert "global_warning" in combined_text
    assert "Watchlist" in combined_text
    assert "資料可能不是最新" in combined_text
    assert "產業輪動" in combined_text
    assert "資料缺漏" in combined_text


def test_decision_desk_warning_summary_and_collapsible_details_refresh_cleanly():
    app()
    base = _snapshot()
    observed_visibility = MarketDataVisibilitySummary(
        as_of_date=base.as_of_date.isoformat(),
        monthly_revenue=MonthlyRevenueBreadthSummary(
            latest_period=None,
            stock_count=0,
            mom_comparable_count=0,
            mom_positive_count=0,
            mom_positive_ratio_bp=None,
            yoy_comparable_count=0,
            yoy_positive_count=0,
            yoy_positive_ratio_bp=None,
            quality="OBSERVED",
        ),
        institutional_flow=InstitutionalFlowMarketSummary(
            latest_date=None,
            stock_count=0,
            foreign_net_shares=None,
            investment_trust_net_shares=None,
            dealer_net_shares=None,
            quality="OBSERVED",
        ),
        source_statuses=(),
        overall_quality="OBSERVED",
    )
    initial = replace(
        base,
        overall_quality=DecisionDeskQuality.DEGRADED,
        market_data_visibility=observed_visibility,
        warnings=("資料來源需要覆核", "樣本範圍有限"),
    )
    builder = FakeBuilder(initial)
    view = rendered_view(builder)

    summary = view.warning_summary_label.text()
    assert "資料品質：品質降級" in summary
    assert "提示數：2" in summary
    assert "首條：資料來源需要覆核" in summary
    assert view.warning_details_panel.is_collapsed()
    assert view.warning_details_panel.content_widget.isHidden()
    assert view.overall_warn_label.toPlainText() == "資料來源需要覆核\n樣本範圍有限"

    view.warning_details_panel.toggle_button.click()
    assert not view.warning_details_panel.is_collapsed()
    assert not view.warning_details_panel.content_widget.isHidden()
    assert "資料來源需要覆核" in view.overall_warn_label.toPlainText()
    assert "樣本範圍有限" in view.overall_warn_label.toPlainText()

    builder.snapshot = replace(
        initial,
        warnings=("新警示已取代舊內容",),
    )
    view.refresh_snapshot()
    assert view.warning_summary_label.text().endswith("首條：新警示已取代舊內容")
    assert view.overall_warn_label.toPlainText() == "新警示已取代舊內容"
    assert "資料來源需要覆核" not in view.overall_warn_label.toPlainText()

    builder.snapshot = replace(
        initial,
        overall_quality=DecisionDeskQuality.MISSING,
        warnings=(),
    )
    view.refresh_snapshot()
    summary = view.warning_summary_label.text()
    assert "資料品質：資料缺件" in summary
    assert "提示數：0" in summary
    assert "未收到額外警示" in summary
    assert "狀態仍為「資料缺件」" in summary
    assert "目前無警示" not in summary
    assert view.overall_warn_label.toPlainText() == ""
    assert view.warning_list.empty_label.text() == "無警示"
    view.close()


def test_decision_desk_view_humanizes_warning_tokens():
    app()
    s = _snapshot(
        overall_quality=DecisionDeskQuality.DEGRADED,
        overall_warnings=(
            "relative_strength_liquidity_skipped_symbols:1162",
            "watchlist_trigger_data_insufficient:2884",
        ),
    )
    view = rendered_view(FakeBuilder(s))

    combined_text = view.overall_warn_label.toPlainText()
    assert "強弱與流動性" in combined_text
    assert "跳過 1162 檔股票" in combined_text
    assert "Watchlist 提示" in combined_text
    assert "2884 資料不足" in combined_text
    assert "relative_strength_liquidity_skipped_symbols:1162" not in combined_text


def test_decision_desk_localizes_market_diagnostics_and_preserves_unknown_codes():
    app()
    snapshot = _snapshot(
        overall_quality=DecisionDeskQuality.DEGRADED,
        market_regime_warnings=("market_regime_fetch_error:timeout:provider offline",),
        market_breadth_warnings=("market_breadth_fetch_error:timeout",),
        sector_rotation_warnings=(
            "sector_rotation_fetch_error:provider unavailable",
            "vendor_specific_diagnostic:keep_raw_detail",
            "vendor_date_unavailable_or_future",
        ),
        risk_prompts_warnings=("risk_prompt_source_quality:sector_rotation:degraded",),
        overall_warnings=("Why Not / 風險提示:legacy_unknown_detail",),
    )
    view = rendered_view(FakeBuilder(snapshot))

    text = view.overall_warn_label.toPlainText()
    assert "市場情勢資料取得失敗：timeout:provider offline" in text
    assert "市場廣度資料取得失敗：timeout" in text
    assert "產業輪動資料取得失敗：provider unavailable" in text
    assert "vendor_specific_diagnostic:keep_raw_detail" in text
    assert "vendor_date_unavailable_or_future" in text
    assert "風險提示：legacy_unknown_detail" in text
    assert "風險提示來源「產業輪動」目前為降級資料" in text
    assert "Why Not" not in text
    assert "Why Not" not in [label.text() for label in view.findChildren(QLabel)]
    assert "風險提示" in view._section_badges
    view.close()


def test_decision_desk_explains_unknown_regime_date_and_degraded_detector():
    app()
    snapshot = _snapshot(
        overall_quality=DecisionDeskQuality.DEGRADED,
        market_regime_warnings=(
            "market_regime_effective_date_unknown",
            "market_regime_detector_degraded",
            "vendor_specific_diagnostic:keep_raw_detail",
        ),
        overall_warnings=("市場情勢:market_regime_effective_date_unknown",),
    )
    view = rendered_view(FakeBuilder(snapshot))

    summary = view.warning_summary_label.text()
    details = view.overall_warn_label.toPlainText()
    assert "首條：市場情勢：有效資料日未知，無法確認資料日期" in summary
    assert "市場情勢：有效資料日未知，無法確認資料日期" in details
    assert "市場情勢：偵測器回報錯誤，結果品質降級" in details
    assert "vendor_specific_diagnostic:keep_raw_detail" in details
    assert "market_regime_effective_date_unknown" not in details
    assert "market_regime_detector_degraded" not in details
    view.close()

    fallback = DecisionDeskView._humanize_warning_token(
        "市場情勢:market_regime_as_of_fallback:2026-10-22"
    )
    assert fallback == "市場情勢：採用備援有效資料日：2026-10-22"
    assert DecisionDeskView._humanize_warning_token(
        "市場情勢:market_regime_effective_date_unknown:vendor_detail"
    ) == "市場情勢：market_regime_effective_date_unknown:vendor_detail"


class FailingBuilder:
    def build_snapshot(self, as_of_date: date):
        raise RuntimeError("service not ready")


def test_decision_desk_view_fallback_to_degraded_if_builder_exception():
    app()
    view = rendered_view(FailingBuilder())

    assert "載入失敗" in view.overall_status_label.text()
    assert "snapshot_error" in view.overall_warn_label.toPlainText()


def test_decision_desk_view_localizes_machine_warning_tokens():
    app()
    s = _snapshot(
        overall_quality=DecisionDeskQuality.DEGRADED,
        overall_warnings=(
            "relative_strength_liquidity:relative_strength_liquidity_skipped_symbols:24",
            "portfolio_alerts:portfolio_alert_top_source:manual:3",
            "portfolio_alerts:portfolio_alerts_chip_estimated:2330",
            "portfolio_alerts:portfolio_alerts_chip_estimated:2382",
            "risk_prompts:risk_prompt_source_quality:relative_strength_liquidity:degraded",
            "risk_prompts:risk_prompt_source_quality:portfolio_alerts:estimated",
        ),
    )
    view = rendered_view(FakeBuilder(s))

    combined_text = view.overall_warn_label.toPlainText()
    assert "跳過 24 檔股票" in combined_text
    assert "持倉警示主要來源為「手動來源」，共 3 筆" in combined_text
    assert "2330 籌碼張數使用估算資料" in combined_text
    assert "風險提示來源「強弱與流動性」目前為降級資料" in combined_text
    assert "風險提示來源「持倉警示」目前為估算資料" in combined_text
    assert "relative_strength_liquidity_skipped_symbols" not in combined_text
    assert "portfolio_alert_top_source" not in combined_text
    assert "risk_prompt_source_quality" not in combined_text


def test_decision_desk_view_renders_risk_prompts():
    app()
    s = _snapshot()
    prompt = DecisionDeskRiskPrompt(
        category="liquidity",
        severity="warning",
        source="relative_strength_liquidity",
        code="1101",
        title="低流動性",
        reason="1101 低於平均成交金額門檻",
        action_hint="檢查可成交金額",
    )
    s = replace(
        s,
        risk_prompts=DecisionDeskRiskPromptSummary(
            as_of_date=s.as_of_date,
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
            prompts=(prompt,),
        ),
    )
    view = rendered_view(FakeBuilder(s))

    assert "低流動性" in view.risk_prompts_value.text()
    assert "1101" in view.risk_prompts_value.text()


def test_decision_desk_view_renders_portfolio_alert_attributions():
    app()
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        portfolio_alerts=PortfolioAlertSummary(
            as_of_date=snapshot.as_of_date,
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
            alert_count=1,
            alert_codes=("2330",),
            alert_level="high",
            attributions=(
                PortfolioAlertAttribution(
                    stock_code="2330",
                    source_label="recommendation_result:rec_001",
                    condition_status="warning",
                    chip_risk_level="bearish",
                    severity=80,
                    reasons=("condition:warning", "chip:risk_level:bearish"),
                    data_quality_flags=(),
                ),
            ),
        ),
    )

    view = rendered_view(FakeBuilder(snapshot))

    assert "推薦結果 rec_001" in view.portfolio_alerts_value.text()
    assert "條件：警示" in view.portfolio_alerts_value.text()
    assert "籌碼：偏空" in view.portfolio_alerts_value.text()


def test_decision_desk_view_compacts_long_relative_strength_lists():
    app()
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        relative_strength_liquidity=RelativeStrengthLiquiditySummary(
            as_of_date=snapshot.as_of_date,
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
            top_strength_codes=tuple(f"T{i:03d}" for i in range(20)),
            weak_strength_codes=tuple(f"W{i:03d}" for i in range(18)),
            low_liquidity_codes=tuple(f"L{i:03d}" for i in range(22)),
        ),
    )

    view = rendered_view(FakeBuilder(snapshot))
    rendered = view.relative_strength_codes.text()

    assert view.relative_strength_liquidity_value.isHidden()
    assert view.relative_strength_liquidity_value.text() == ""
    assert view.relative_strength_codes.wordWrap()
    assert "\n" in rendered
    assert "另 12 檔" in rendered
    assert "T019" not in rendered


def test_decision_desk_uses_single_relative_strength_presentation():
    app()
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        relative_strength_liquidity=RelativeStrengthLiquiditySummary(
            as_of_date=snapshot.as_of_date,
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
            top_strength_codes=("2330", "2454"),
            weak_strength_codes=("1101",),
            low_liquidity_codes=("9999",),
        ),
    )

    view = rendered_view(FakeBuilder(snapshot))

    assert view.relative_strength_liquidity_value.isHidden()
    assert view.relative_strength_liquidity_value.text() == ""
    assert "強勢：2330, 2454" in view.relative_strength_codes.text()
    assert "弱勢：1101" in view.relative_strength_codes.text()
    assert "低流動性：9999" in view.relative_strength_codes.text()


def test_decision_desk_sections_use_quality_badges_in_headers():
    app()
    view = rendered_view(FakeBuilder(_snapshot(market_breadth_quality=DecisionDeskQuality.DEGRADED)))

    assert view.market_breadth_status.isHidden()
    badge = view._status_badges[view.market_breadth_status]
    assert "降級" in badge.text()
    assert MIDNIGHT_ANALYST.warning in badge.styleSheet()


def test_decision_desk_view_uses_readable_overview_typography():
    app()
    view = rendered_view(FakeBuilder(_snapshot()))

    assert view.overall_status_label.font().pointSize() >= 12
    assert view.generated_at_label.font().pointSize() >= 10
    assert "background" in view.overall_status_label.styleSheet()


def test_decision_desk_view_uses_midnight_reference_widgets():
    app()
    view = rendered_view(FakeBuilder(_snapshot()))

    assert hasattr(view, "overall_quality_badge")
    assert hasattr(view, "relative_strength_codes")
    assert hasattr(view, "warning_list")
    assert view.relative_strength_codes.wordWrap()
    assert "#08111f" not in view.styleSheet()


def test_decision_desk_view_renders_compact_code_widget_from_snapshot():
    app()
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        relative_strength_liquidity=RelativeStrengthLiquiditySummary(
            as_of_date=snapshot.as_of_date,
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
            top_strength_codes=tuple(f"T{i:03d}" for i in range(10)),
            weak_strength_codes=("W001",),
            low_liquidity_codes=("L001", "L002"),
        ),
    )

    view = rendered_view(FakeBuilder(snapshot))
    text = view.relative_strength_codes.text()

    assert "強勢：T000, T001, T002, T003, T004, T005, T006, T007（另 2 檔）" in text
    assert "弱勢：W001" in text
    assert "低流動性：L001, L002" in text


def test_decision_desk_view_renders_visibility_quality_missing_state_and_action_hint():
    app()
    visibility = MarketDataVisibilitySummary(
        as_of_date="2026-06-15",
        monthly_revenue=MonthlyRevenueBreadthSummary(
            latest_period="2026-05",
            stock_count=1200,
            mom_comparable_count=1100,
            mom_positive_count=620,
            mom_positive_ratio_bp=5636,
            yoy_comparable_count=1050,
            yoy_positive_count=700,
            yoy_positive_ratio_bp=6667,
            quality="DEGRADED",
            warnings=("historical_pit_unverified",),
        ),
        institutional_flow=InstitutionalFlowMarketSummary(
            latest_date=None,
            stock_count=0,
            foreign_net_shares=None,
            investment_trust_net_shares=None,
            dealer_net_shares=None,
            quality="MISSING",
            warnings=("尚未匯入（0 筆）",),
        ),
        source_statuses=(
            SourceVisibilityStatus(
                source_id="fundamental_monthly_revenues",
                display_name="月營收",
                as_of_date="2026-06-15",
                latest_observation_date="2026-05",
                available_date="2026-06-10",
                row_count=3600,
                stock_count=1200,
                quality="DEGRADED",
                pit_status="historical_pit_unverified",
                eligibility="research_only",
                warnings=("historical_pit_unverified",),
            ),
            SourceVisibilityStatus(
                source_id="institutional_flows",
                display_name="三大法人",
                as_of_date="2026-06-15",
                latest_observation_date=None,
                available_date=None,
                row_count=0,
                stock_count=0,
                quality="MISSING",
                pit_status="missing",
                eligibility="none",
                warnings=("尚未匯入（0 筆）",),
            ),
        ),
        overall_quality="DEGRADED",
        warnings=("historical_pit_unverified", "尚未匯入（0 筆）"),
    )

    view = rendered_view(
        FakeBuilder(_snapshot(market_data_visibility=visibility))
    )

    assert any(
        "資料可見性與擴充因子" in label.text()
        for label in view.visibility_section.findChildren(QLabel)
    )
    assert "2026-05" in view.revenue_visibility_card.value_label.text()
    assert "月增正向 56.36%" in view.revenue_visibility_card.value_label.text()
    assert "尚未匯入（0 筆）" in view.institutional_visibility_card.value_label.text()
    assert "外資 0" not in view.institutional_visibility_card.value_label.text()
    assert "降級" in view.visibility_quality_badge.text()
    assert "僅供研究可見性" in view.visibility_action_hint.text()
    assert "三大法人" in view.visibility_sources_label.text()
    assert "資料缺件" in view.visibility_sources_label.text()


def test_decision_desk_displays_valid_regime_source_date_separately_from_decision_date():
    app()
    base = _snapshot()
    summary = replace(
        base.market_regime,
        meta={
            "source_data_date": "2026-06-13",
            "source_id": "legacy_provider",
            "source_version": "legacy-v1",
        },
    )
    snapshot = replace(base, market_regime=summary)
    view = rendered_view(FakeBuilder(snapshot))

    text = view.market_regime_value.text()
    assert "行情日：2026-06-13" in text
    assert "判斷日：2026-06-15" in text
    assert "訊號強度：7700" in text
    view.close()

    for source_data_date in ("2026-6-13", "2026-06-16", None):
        summary = replace(
            base.market_regime,
            meta={"source_data_date": source_data_date},
        )
        view = rendered_view(FakeBuilder(replace(base, market_regime=summary)))
        text = view.market_regime_value.text()
        assert "行情日：未知" in text
        assert "判斷日：2026-06-15" in text
        view.close()


def test_decision_desk_shows_unknown_regime_metrics_and_preserves_real_zero():
    app()
    base = _snapshot()
    missing_score = replace(
        base.market_regime,
        regime_score=None,
        regime_confidence=9109,
        meta={"regime_value_kind": "match_score_bp"},
    )
    view = rendered_view(
        FakeBuilder(replace(base, market_regime=missing_score))
    )
    text = view.market_regime_value.text()
    assert "得分：未知" in text
    assert "匹配分數（bp）：9109" in text
    assert "行情日：未知" in text
    assert "判斷日：2026-06-15" in text
    view.close()

    unknown_match_score = replace(
        base.market_regime,
        regime_confidence=None,
        meta={"regime_value_kind": "match_score_bp"},
    )
    view = rendered_view(
        FakeBuilder(replace(base, market_regime=unknown_match_score))
    )
    assert "匹配分數（bp）：未知" in view.market_regime_value.text()
    view.close()

    real_zero = replace(
        base.market_regime,
        regime_score=0,
        regime_confidence=0,
        meta={"regime_value_kind": "match_score_bp"},
    )
    view = rendered_view(FakeBuilder(replace(base, market_regime=real_zero)))
    text = view.market_regime_value.text()
    assert "得分：0" in text
    assert "匹配分數（bp）：0" in text
    view.close()


def test_decision_desk_market_breadth_preserves_missing_partial_and_zero_values():
    app()
    base = _snapshot()

    missing = replace(
        base.market_breadth,
        advancing=None,
        declining=None,
        unchanged=None,
        breadth_ratio_bp=None,
    )
    view = rendered_view(FakeBuilder(replace(base, market_breadth=missing)))
    text = view.market_breadth_value.text()
    assert "多方：未提供" in text
    assert "空方：未提供" in text
    assert "持平：未提供" in text
    assert "廣度比率BP：未知" in text
    view.close()

    zeros = replace(
        base.market_breadth,
        advancing=0,
        declining=0,
        unchanged=0,
        breadth_ratio_bp=0,
    )
    view = rendered_view(FakeBuilder(replace(base, market_breadth=zeros)))
    text = view.market_breadth_value.text()
    assert "多方：0" in text
    assert "空方：0" in text
    assert "持平：0" in text
    assert "廣度比率BP：0" in text
    view.close()

    partial = replace(
        base.market_breadth,
        advancing=0,
        declining=None,
        unchanged=3,
        breadth_ratio_bp=None,
    )
    view = rendered_view(FakeBuilder(replace(base, market_breadth=partial)))
    text = view.market_breadth_value.text()
    assert "多方：0" in text
    assert "空方：未提供" in text
    assert "持平：3" in text
    assert "廣度比率BP：未知" in text
    view.close()


def test_decision_desk_market_breadth_bar_uses_integer_stretches_and_accessible_counts():
    app()
    base = _snapshot()
    breadth = replace(base.market_breadth, advancing=120, declining=80, unchanged=0)
    view = rendered_view(FakeBuilder(replace(base, market_breadth=breadth)))
    segments = [view.market_breadth_bar.findChild(QFrame, f"decisionDeskBreadthSegment{i}") for i in range(3)]
    assert [segment.property("breadthCount") for segment in segments] == [120, 80, 0]
    assert [view.market_breadth_bar_layout.stretch(i) for i in range(3)] == [120, 80, 0]
    assert segments[2].width() == 0
    assert [segment.accessibleName() for segment in segments] == ["上漲 120 家", "下跌 80 家", "平盤 0 家"]
    assert view.market_breadth_legend.text() == "上漲：120 家｜下跌：80 家｜平盤：0 家"
    assert "已載入家數分布；非指數報酬／交易訊號" in view.market_breadth_caption.text()
    assert "來源日：2026-06-15" in view.market_breadth_caption.text()
    assert "品質：觀察到" in view.market_breadth_caption.text()
    view.close()


def test_decision_desk_market_breadth_bar_hides_invalid_or_unqualified_data_and_clears_on_refresh():
    app()
    base = _snapshot()
    invalid_cases = (
        replace(base.market_breadth, advancing=None),
        replace(base.market_breadth, advancing=True),
        replace(base.market_breadth, declining=-1),
        replace(base.market_breadth, advancing=0, declining=0, unchanged=0),
        replace(base.market_breadth, quality=DecisionDeskQuality.MISSING),
        replace(base.market_breadth, quality="pending"),
        replace(base.market_breadth, as_of_date=None),
        replace(base.market_breadth, as_of_date=date(2026, 6, 16)),
    )
    for breadth in invalid_cases:
        view = rendered_view(FakeBuilder(replace(base, market_breadth=breadth)))
        assert view.market_breadth_bar.isHidden()
        assert view.market_breadth_legend.isHidden()
        assert view.market_breadth_caption.isHidden()
        view.close()

    degraded = replace(base.market_breadth, quality=DecisionDeskQuality.DEGRADED)
    view = rendered_view(FakeBuilder(replace(base, market_breadth=degraded)))
    assert not view.market_breadth_bar.isHidden()
    assert "品質：降級" in view.market_breadth_caption.text()
    refreshed = replace(base.market_breadth, advancing=1, declining=2, unchanged=3)
    view._render_snapshot(replace(base, market_breadth=refreshed))
    assert [segment.property("breadthCount") for segment in view.market_breadth_bar.findChildren(QFrame)] == [1, 2, 3]
    view._display_loading_snapshot()
    assert view.market_breadth_bar.isHidden()
    assert view.market_breadth_legend.text() == ""
    assert view.market_breadth_caption.text() == ""
    view.close()


def _institutional_visibility(
    *,
    foreign=120,
    trust=-60,
    dealer=0,
    quality="OBSERVED",
    warnings=(),
    source_date="2026-06-15",
    decision_date="2026-06-15",
):
    return MarketDataVisibilitySummary(
        as_of_date=decision_date,
        monthly_revenue=MonthlyRevenueBreadthSummary(
            latest_period=None,
            stock_count=0,
            mom_comparable_count=0,
            mom_positive_count=0,
            mom_positive_ratio_bp=None,
            yoy_comparable_count=0,
            yoy_positive_count=0,
            yoy_positive_ratio_bp=None,
            quality="MISSING",
        ),
        institutional_flow=InstitutionalFlowMarketSummary(
            latest_date=source_date,
            stock_count=1200,
            foreign_net_shares=foreign,
            investment_trust_net_shares=trust,
            dealer_net_shares=dealer,
            quality=quality,
            warnings=warnings,
        ),
        source_statuses=(),
        overall_quality=quality,
    )


def test_decision_desk_institutional_flow_bar_uses_signed_values_and_common_zero_axis():
    app()
    view = rendered_view(
        FakeBuilder(_snapshot(market_data_visibility=_institutional_visibility()))
    )

    assert view.institutional_flow_bar.objectName() == "decisionDeskInstitutionalFlowBar"
    assert not view.institutional_flow_bar.isHidden()
    assert view.institutional_flow_zero_axis.objectName() == "decisionDeskInstitutionalFlowZeroAxis"
    assert set(view.institutional_flow_rows) == {"外資", "投信", "自營商"}
    foreign_bar = view.institutional_flow_rows["外資"][1]
    trust_bar = view.institutional_flow_rows["投信"][1]
    dealer_bar = view.institutional_flow_rows["自營商"][1]
    assert foreign_bar.property("netShares") == 120
    assert trust_bar.property("netShares") == -60
    assert foreign_bar.property("relativeScaleMax") == 120
    assert foreign_bar.width() == 52
    assert trust_bar.width() == 26
    assert dealer_bar.width() == 3
    assert "資料日 2026-06-15" in view.institutional_flow_bar.accessibleDescription()
    assert "品質 OBSERVED" in view.institutional_flow_bar.accessibleDescription()
    assert "外資：+120 股" in view.institutional_flow_rows["外資"][2].toolTip()
    assert "外資 120 股" in view.institutional_visibility_card.value_label.text()


def test_decision_desk_institutional_flow_bar_shows_degraded_quality_and_warnings():
    app()
    visibility = _institutional_visibility(
        quality="DEGRADED", warnings=("來源範圍有限",)
    )
    view = rendered_view(FakeBuilder(_snapshot(market_data_visibility=visibility)))

    assert not view.institutional_flow_bar.isHidden()
    assert view.institutional_flow_rows["外資"][1].property("quality") == "DEGRADED"
    assert "品質 DEGRADED" in view.institutional_flow_bar.accessibleDescription()
    assert "提示：來源範圍有限" in view.institutional_visibility_card.value_label.text()


def test_decision_desk_institutional_flow_bar_hides_for_missing_or_invalid_values():
    app()
    view = rendered_view(
        FakeBuilder(
            _snapshot(
                market_data_visibility=_institutional_visibility(foreign=None)
            )
        )
    )
    assert view.institutional_flow_bar.isHidden()
    assert view.institutional_flow_rows == {}
    assert "外資 N/A 股" in view.institutional_visibility_card.value_label.text()

    missing = _institutional_visibility(quality="MISSING", warnings=("來源缺件",))
    view._render_market_data_visibility(missing)
    assert view.institutional_flow_bar.isHidden()
    assert "來源缺件" in view.institutional_visibility_card.value_label.text()


def test_decision_desk_institutional_flow_bar_clears_on_rerender_and_pending_state():
    app()
    view = rendered_view(
        FakeBuilder(_snapshot(market_data_visibility=_institutional_visibility()))
    )
    assert not view.institutional_flow_bar.isHidden()

    view._render_market_data_visibility(None)
    assert view.institutional_flow_bar.isHidden()
    assert view.institutional_flow_rows == {}

    view._render_market_data_visibility(_institutional_visibility())
    assert not view.institutional_flow_bar.isHidden()
    assert len(
        view.institutional_flow_bar.findChildren(
            QFrame, "decisionDeskInstitutionalFlowSegment0"
        )
    ) == 1
    view._render_market_data_visibility(_institutional_visibility())
    assert len(
        view.institutional_flow_bar.findChildren(
            QFrame, "decisionDeskInstitutionalFlowSegment0"
        )
    ) == 1
    view._display_loading_snapshot()
    assert view.institutional_flow_bar.isHidden()

    view._render_market_data_visibility(_institutional_visibility())
    view._display_pending_snapshot()
    assert view.institutional_flow_bar.isHidden()
    assert view.institutional_flow_rows == {}
    view.close()


def test_decision_desk_institutional_flow_bar_rejects_future_or_invalid_dates_but_keeps_text():
    app()
    future = _institutional_visibility(source_date="2026-06-16")
    view = rendered_view(FakeBuilder(_snapshot(market_data_visibility=future)))
    assert view.institutional_flow_bar.isHidden()
    assert "2026-06-16｜1200 檔" in view.institutional_visibility_card.value_label.text()
    assert "外資 120 股" in view.institutional_visibility_card.value_label.text()

    invalid_decision_date = _institutional_visibility(decision_date="not-a-date")
    view._render_market_data_visibility(invalid_decision_date)
    assert view.institutional_flow_bar.isHidden()
    assert "外資 120 股" in view.institutional_visibility_card.value_label.text()
    view.close()
