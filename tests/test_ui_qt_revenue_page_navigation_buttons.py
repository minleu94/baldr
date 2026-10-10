"""月營收換頁按鈕的實際訊號與首末頁邊界回歸。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import cast

import pytest
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1,
)
from ui_qt.views.daily_market_technical_official_disposition_revenue_view import (
    DailyMarketTechnicalOfficialDispositionRevenueView,
)


@dataclass(frozen=True)
class _PageCursorUnitFixture:
    """只提供頁碼的按鈕單元 fixture；不是 reader 發行的查詢頁。"""

    page_index: int
    page_count: int


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    yield instance


@pytest.fixture
def view(app: QApplication) -> DailyMarketTechnicalOfficialDispositionRevenueView:
    instance = DailyMarketTechnicalOfficialDispositionRevenueView()
    yield instance
    instance.close()


def _set_cursor(
    view: DailyMarketTechnicalOfficialDispositionRevenueView,
    page_index: int,
    page_count: int,
) -> None:
    # 頁碼 helper 與按鈕啟用只讀取這兩個游標欄位。
    # 來源與查詢頁身份完整性仍由真來源 UI 旅程驗證。
    view._page = cast(
        DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1,
        _PageCursorUnitFixture(page_index=page_index, page_count=page_count),
    )
    view._set_result_actions_enabled(True)


def test_no_page_starts_at_zero_and_both_navigation_buttons_are_disabled(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionRevenueView,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[int] = []
    monkeypatch.setattr(view, "navigate_page", requested.append)
    view.show()
    app.processEvents()

    assert view.current_page is None
    assert view._page_index() == 0
    assert not view.previous_page_button.isEnabled()
    assert not view.next_page_button.isEnabled()
    view.previous_page_button.click()
    view.next_page_button.click()
    app.processEvents()
    assert requested == []


def test_next_button_uses_current_first_page_index(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionRevenueView,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[int] = []
    monkeypatch.setattr(view, "navigate_page", requested.append)
    _set_cursor(view, page_index=0, page_count=3)
    view.show()
    app.processEvents()

    assert view._page_index() == 0
    assert not view.previous_page_button.isEnabled()
    assert view.next_page_button.isEnabled()
    view.next_page_button.click()
    app.processEvents()
    assert requested == [1]


def test_previous_button_from_second_page_requests_first_page(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionRevenueView,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[int] = []
    monkeypatch.setattr(view, "navigate_page", requested.append)
    _set_cursor(view, page_index=1, page_count=3)
    view.show()
    app.processEvents()

    assert view._page_index() == 1
    assert view.previous_page_button.isEnabled()
    assert view.next_page_button.isEnabled()
    view.previous_page_button.click()
    app.processEvents()
    assert requested == [0]


def test_first_and_last_page_boundaries_keep_outward_buttons_disabled(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionRevenueView,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[int] = []
    monkeypatch.setattr(view, "navigate_page", requested.append)
    view.show()

    _set_cursor(view, page_index=0, page_count=3)
    app.processEvents()
    assert not view.previous_page_button.isEnabled()
    view.previous_page_button.click()

    _set_cursor(view, page_index=2, page_count=3)
    app.processEvents()
    assert view.previous_page_button.isEnabled()
    assert not view.next_page_button.isEnabled()
    view.next_page_button.click()
    app.processEvents()
    assert requested == []
