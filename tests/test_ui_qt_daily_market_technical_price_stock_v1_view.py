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
