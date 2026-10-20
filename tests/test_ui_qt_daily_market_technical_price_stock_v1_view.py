"""F07 價格個股視圖以真實合成來源驗證理由、來源限制與返回錨點。"""

from __future__ import annotations

from typing import Any, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceSelectionV1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePriceReadSessionV1,
    DailyMarketTechnicalUniversePriceStockV1,
    open_daily_market_technical_universe_price_read_session_v1,
)
from ui_qt.views.daily_market_technical_price_stock_v1_view import DailyMarketTechnicalPriceStockV1View


pytest_plugins = ("tests.test_daily_market_technical_universe_price_query_v1",)


def _open_session(fixture: dict[str, Any]) -> DailyMarketTechnicalUniversePriceReadSessionV1:
    plan = fixture["plan"]
    receipt = fixture["receipt"]
    return open_daily_market_technical_universe_price_read_session_v1(
        store_output_root=fixture["store_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=receipt.identity_sha256,
        receipt_sha256=receipt.content_sha256,
    )


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return cast(QApplication, instance)


def test_true_stock_detail_renders_saved_facts_and_returns_exact_selection(
    app: QApplication,
    exact_price_store: dict[str, Any],
) -> None:
    session = _open_session(exact_price_store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    request = result.create_page_request(0, page_size=4)
    page = result.read_page(request)
    stock = result.read_stock_snapshot(request, "S0001")
    selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(query, page, "S0001")

    view = DailyMarketTechnicalPriceStockV1View()
    view.resize(520, 520)
    view.show()
    app.processEvents()
    view.show_stock(stock, selection)

    assert isinstance(stock, DailyMarketTechnicalUniversePriceStockV1)
    summary = view.summary.text()
    evidence = view.evidence.toPlainText()
    assert "S0001" in summary
    assert "決策日：2026-10-06" in summary
    assert "可得時間未知" in summary
    assert "歷史 PIT" in summary
    assert "TWD／股" in evidence
    assert view.detail_tabs.currentIndex() == 0
    assert view.price_table.rowCount() == len(stock.snapshot.rows)
    assert tuple(point.close_price for point in view.price_chart._points) == tuple(
        row.close_price if row.ohlc_valid else None
        for row in stock.snapshot.rows if row.feature_date is not None
    )
    assert all(point.available_at == "" and point.change is None for point in view.price_chart._points)
    assert all(point.quality == "unknown" for point in view.price_chart._points)
    view.detail_tabs.setCurrentWidget(view.evidence)
    app.processEvents()
    assert "價格觀測日：2026-10-06" in evidence
    for rule in stock.snapshot.rules:
        assert rule.key in selection.query.source.method_rule_keys
        assert rule.version in evidence
        for reason in (*rule.supports, *rule.counterevidence, *rule.unknown_reasons):
            assert reason in evidence
    assert view.evidence.verticalScrollBar().maximum() > 0
    view.evidence.verticalScrollBar().setValue(view.evidence.verticalScrollBar().maximum())
    assert view.evidence.verticalScrollBar().value() == view.evidence.verticalScrollBar().maximum()
    assert view.audit.isHidden()
    QTest.mouseClick(view.audit_toggle, Qt.MouseButton.LeftButton)
    assert view.audit.isVisible()
    assert selection.selection_identity_sha256 in view.audit.toPlainText()

    returned: list[object] = []
    view.returnRequested.connect(returned.append)
    QTest.mouseClick(view.return_button, Qt.MouseButton.LeftButton)
    assert returned == [selection]
    view.close()


def test_stock_view_rejects_selection_from_another_stock_without_replacing_detail(
    app: QApplication,
    exact_price_store: dict[str, Any],
) -> None:
    session = _open_session(exact_price_store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    request = result.create_page_request(0, page_size=4)
    page = result.read_page(request)
    stock = result.read_stock_snapshot(request, "S0001")
    other = DailyMarketTechnicalUniversePriceSelectionV1.from_page(query, page, "S0002")
    view = DailyMarketTechnicalPriceStockV1View()
    view.show_stock(stock, DailyMarketTechnicalUniversePriceSelectionV1.from_page(query, page, "S0001"))
    previous = view.summary.text()

    with pytest.raises(ValueError, match="origin_selection_mismatch"):
        view.show_stock(stock, other)
    assert view.summary.text() == previous


def test_embedded_workspace_uses_exact_saved_rows_without_general_report_read(
    app: QApplication, exact_price_store: dict[str, Any],
) -> None:
    from ui_qt.views.stock_research_workspace import StockResearchWorkspace

    class NoGeneralRead:
        def read_report(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("原價格研究不可改讀一般價庫")

    session = _open_session(exact_price_store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    request = result.create_page_request(0, page_size=4)
    page = result.read_page(request)
    first, second = (result.read_stock_snapshot(request, code) for code in ("S0001", "S0002"))
    first_selection, second_selection = (
        DailyMarketTechnicalUniversePriceSelectionV1.from_page(query, page, code)
        for code in ("S0001", "S0002")
    )
    workspace = StockResearchWorkspace(cast(Any, NoGeneralRead()))
    workspace.resize(900, 720)
    shown_contexts: list[object] = []
    workspace.sourceContextShown.connect(shown_contexts.append)
    workspace.show()
    workspace.show_price_research(first, first_selection)
    app.processEvents()
    old = workspace.price_research_view
    assert old is not None and old.isVisible()
    assert workspace.report_view._loaded_report is None
    assert old.price_chart._points[-1].close_price == first.snapshot.rows[-1].close_price
    assert old.price_table.verticalScrollBar().maximum() > 0
    with pytest.raises(ValueError, match="origin_selection_mismatch"):
        workspace.show_price_research(second, first_selection)
    assert workspace.price_research_view is old and old.isVisible()
    workspace.show_price_research(second, second_selection)
    app.processEvents()
    current = workspace.price_research_view
    assert current is not None and current is not old and current.isVisible()
    assert current.price_chart._points[-1].close_price == second.snapshot.rows[-1].close_price
    assert workspace.content_stack.count() == 2
    assert workspace.price_research_context.stock_code == second.stock_code
    assert workspace.price_research_context.source_snapshot_hash == second.snapshot.snapshot_identity_sha256
    assert shown_contexts[-1] == workspace.price_research_context
    returned: list[object] = []
    workspace.priceResearchReturnRequested.connect(returned.append)
    current.return_button.click()
    assert returned == [second_selection]
    workspace.general_lookup_button.click()
    app.processEvents()
    assert workspace.content_stack.currentWidget() is workspace.general_report_page
    assert workspace.report_view._loaded_report is None
    assert not current.isVisible()
    # 明確另開一般查詢會建立空名稱的新脈絡；合成S代號仍不可由一般價庫補值。
    independent = shown_contexts[-1]
    assert independent is workspace.report_view.context
    assert independent.stock_code == second.stock_code and independent.stock_name == ""
    assert independent.source_kind == "explicit_latest_stock_research"
    assert not independent.result_id and not independent.source_snapshot_hash and not independent.data_date
    assert workspace.price_research_context.source_snapshot_hash == second.snapshot.snapshot_identity_sha256
    # 新的明確一般查詢走背景worker；等原3秒有界期限結束才驗關閉。
    for _ in range(300):
        if not workspace.is_busy():
            break
        QTest.qWait(10)
    assert not workspace.is_busy()
    assert workspace.request_close()
    workspace.close()
