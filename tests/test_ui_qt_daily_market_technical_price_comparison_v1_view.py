"""F07 價格比較視圖保留各欄原查詢與來源身份。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceComparisonV1,
    DailyMarketTechnicalUniversePriceSelectionV1,
    read_daily_market_technical_universe_price_comparison_v1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePriceReadSessionV1,
    open_daily_market_technical_universe_price_read_session_v1,
)
from ui_qt.views.daily_market_technical_price_comparison_v1_view import (
    DailyMarketTechnicalPriceComparisonV1View,
)


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


def test_true_comparison_preserves_each_original_query_and_return_origin(
    app: QApplication,
    exact_price_store: dict[str, Any],
) -> None:
    session = _open_session(exact_price_store)
    first_query = session.create_query(min_close_price=None, unknown_price_policy="include")
    second_query = session.create_query(min_close_price=Decimal("100"), unknown_price_policy="only")
    first_result = session.execute(first_query)
    second_result = session.execute(second_query)
    first_page = first_result.read_page(first_result.create_page_request(0, page_size=4))
    second_page = second_result.read_page(second_result.create_page_request(0, page_size=4))
    first_selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(first_query, first_page, "S0001")
    second_selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(second_query, second_page, "S0003")
    comparison = read_daily_market_technical_universe_price_comparison_v1((first_selection, second_selection))

    view = DailyMarketTechnicalPriceComparisonV1View()
    view.resize(680, 640)
    view.show()
    app.processEvents()
    view.show_comparison(comparison)

    assert isinstance(comparison, DailyMarketTechnicalUniversePriceComparisonV1)
    assert view.table.columnCount() == 2
    first_header = view.table.horizontalHeaderItem(0)
    second_header = view.table.horizontalHeaderItem(1)
    assert first_header is not None and first_header.text() == "S0001"
    assert second_header is not None and second_header.text() == "S0003"
    assert first_selection.query.query_identity_sha256 != second_selection.query.query_identity_sha256
    assert first_selection.source_identity_sha256 == second_selection.source_identity_sha256
    assert first_selection.query.source.decision_date.isoformat() in view.evidence.toPlainText()
    assert first_selection.query.source.source_clock_identity_sha256 in view.evidence.toPlainText()
    price_state_item = view.table.item(1, 1)
    assert price_state_item is not None
    assert price_state_item.text() == "未知價格"

    view.table.setCurrentCell(0, 1)
    app.processEvents()
    assert second_selection.query.query_identity_sha256 in view.evidence.toPlainText()
    assert second_selection.source_identity_sha256 in view.evidence.toPlainText()
    returned: list[object] = []
    view.originRequested.connect(returned.append)
    QTest.mouseClick(view.return_button, Qt.MouseButton.LeftButton)
    assert returned == [second_selection]
    view.close()


def test_comparison_view_rejects_one_column_without_replacing_existing_result(
    app: QApplication,
    exact_price_store: dict[str, Any],
) -> None:
    session = _open_session(exact_price_store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    page = result.read_page(result.create_page_request(0, page_size=4))
    selections = tuple(
        DailyMarketTechnicalUniversePriceSelectionV1.from_page(query, page, code)
        for code in ("S0001", "S0002")
    )
    comparison = read_daily_market_technical_universe_price_comparison_v1(selections)
    view = DailyMarketTechnicalPriceComparisonV1View()
    view.show_comparison(comparison)
    old_summary = view.summary.text()

    with pytest.raises(TypeError, match="reader 發行"):
        view.show_comparison(object())  # type: ignore[arg-type]
    assert view.summary.text() == old_summary
