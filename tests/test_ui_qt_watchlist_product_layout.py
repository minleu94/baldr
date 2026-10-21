from __future__ import annotations

import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import pandas as pd
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QGroupBox, QScrollArea, QSplitter, QTableView,
    QVBoxLayout, QWidget,
)

from ui_qt.models.pandas_table_model import PandasTableModel
import ui_qt.views.watchlist_product_layout as product_layout
from ui_qt.views.watchlist_product_layout import WatchlistProductLayout
from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkV1,
)
from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceSelectionV1,
)
from app_module.watchlist_service import (
    TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE,
    _bookmark_payload_id,
    _bookmark_source,
)
from tests.test_daily_market_technical_universe_price_query_v1 import _open_session


class _View(QWidget):
    watchlistUpdated = Signal()
    watchlistLoaded = Signal()

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        self.page_scroll = QScrollArea(self)
        self.page_scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        self.page_scroll.setWidget(content)
        root.addWidget(self.page_scroll)
        self.main_splitter = QSplitter(content)
        content_layout.addWidget(self.main_splitter)
        self.candidate_panel = QGroupBox("候選", self.main_splitter)
        candidate_layout = QVBoxLayout(self.candidate_panel)
        self.stocks_table = QTableView(self.candidate_panel)
        candidate_layout.addWidget(self.stocks_table)
        self.saved_panel = QGroupBox("股票代碼", self.main_splitter)
        QVBoxLayout(self.saved_panel)
        self.main_splitter.addWidget(self.candidate_panel)
        self.main_splitter.addWidget(self.saved_panel)
        self.universe_list = object()
        self.universe_stock_list = object()
        self.refresh_btn = None
        self.watchlist_service = SimpleNamespace(read_calls=0, write_calls=0)
        self.stocks_model = PandasTableModel(_rows())
        self.stocks_table.setModel(self.stocks_model)
        self.stocks_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.stocks_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.stocks_table.setSortingEnabled(False)

    @staticmethod
    def _exact_research_bookmark_id_for_row(row):
        payload = row.get("research_bookmark")
        if not isinstance(payload, dict):
            return ""
        code = str(row.get("證券代號", row.get("stock_code", "")))
        source = str(row.get("source", ""))
        identity = str(payload.get("bookmark_id", payload.get("view_bookmark_identity_sha256", "")))
        if payload.get("stock_code") != code or payload.get("source") != source:
            return ""
        return identity if row.get("source_id") == identity else ""

    @staticmethod
    def _row_is_composite_bookmark(row):
        payload = row.get("research_bookmark")
        return isinstance(payload, dict) and str(payload.get("schema_version", "")).startswith(
            "daily-market-technical-official-disposition-composite-view-state."
        )

    @staticmethod
    def _row_declares_research_bookmark(row):
        return bool(row.get("research_bookmark")) or "bookmark" in str(row.get("source", ""))


def _rows():
    composite_source = "technical_official_disposition_composite_research_bookmark_v2"
    return pd.DataFrame([
        {"證券代號": "2330", "stock_code": "2330", "source": "manual", "source_id": "", "research_bookmark": None},
        {"證券代號": "2317", "stock_code": "2317", "source": "test.bookmark", "source_id": "b1", "research_bookmark": {
            "schema_version": "test-typed-bookmark.v1", "source": "test.bookmark", "stock_code": "2317", "bookmark_id": "b1",
        }},
        {"證券代號": "1101", "stock_code": "1101", "source": "test.bookmark", "source_id": "wrong", "research_bookmark": {
            "schema_version": "test-typed-bookmark.v1", "source": "test.bookmark", "stock_code": "1101", "bookmark_id": "b2",
        }},
        {"證券代號": "2603", "stock_code": "2603", "source": composite_source, "source_id": "cmp-1", "research_bookmark": {
            "schema_version": "daily-market-technical-official-disposition-composite-view-state.v2",
            "source": composite_source, "stock_code": "2603", "view_bookmark_identity_sha256": "cmp-1",
        }},
        {"證券代號": "2881", "stock_code": "2881", "source": "future.bookmark", "source_id": "future-id", "research_bookmark": {
            "schema_version": "unsupported.v9", "source": "future.bookmark", "stock_code": "2881", "bookmark_id": "future-id",
        }},
        {"證券代號": "2609", "stock_code": "2609", "source": "manual", "source_id": "b3", "research_bookmark": {
            "schema_version": "test-typed-bookmark.v1", "source": "manual", "stock_code": "2609", "bookmark_id": "b3",
        }},
    ])


@pytest.fixture
def qt_driver():
    app = QApplication.instance() or QApplication(sys.argv)

    class Driver:
        def __init__(self):
            self.widgets = []

        def addWidget(self, widget):
            self.widgets.append(widget)

    driver = Driver()
    yield driver
    for widget in reversed(driver.widgets):
        widget.close()
        widget.deleteLater()
    app.processEvents()


@pytest.fixture
def typed_decoder(monkeypatch):
    def decode(payload):
        if payload.get("schema_version") not in {
            "test-typed-bookmark.v1",
            "daily-market-technical-official-disposition-composite-view-state.v2",
        }:
            raise ValueError("typed_schema_unsupported")
        return SimpleNamespace(stock_code=payload["stock_code"], source=payload["source"])

    monkeypatch.setattr(product_layout, "decode_daily_market_research_bookmark", decode)
    monkeypatch.setattr(product_layout, "_bookmark_source", lambda bookmark: bookmark.source)
    monkeypatch.setattr(product_layout, "_bookmark_payload_id", _bookmark_payload_id)
    envelope = object()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view._decode_composite_envelope",
        lambda _payload: envelope,
    )
    return envelope


def test_sections_preserve_original_view_model_and_filter_only_verified_typed_rows(
    qt_driver, typed_decoder,
):
    view = _View()
    qt_driver.addWidget(view)
    original_model = view.stocks_model
    original_selection_model = view.stocks_table.selectionModel()
    analysis_selection_rows = []
    original_selection_model.selectionChanged.connect(
        lambda selected, _deselected: analysis_selection_rows.extend(
            index.row() for index in selected.indexes() if index.column() == 0
        )
    )
    original_candidate_parent = view.candidate_panel.parent()
    adapter = WatchlistProductLayout(view)

    assert adapter.install()
    assert view.stocks_table.model() is original_model
    assert view.stocks_table.selectionModel() is original_selection_model
    assert view.candidate_panel.parent() is original_candidate_parent
    assert adapter._active_section == "pure_self"
    assert not view.stocks_table.isRowHidden(0)
    assert view.stocks_table.isRowHidden(1)
    assert view.stocks_table.isRowHidden(2)
    assert view.stocks_table.isRowHidden(3)
    assert view.stocks_table.isRowHidden(4)
    assert view.stocks_table.isRowHidden(5)
    assert "顯示手動加入的股票" in adapter.section_status.text()
    # 純自選選列仍來自原 model，原始代碼與來源身份沒有轉換。
    view.stocks_table.selectRow(0)
    selected = view.stocks_table.selectionModel().selectedRows()
    assert len(selected) == 1
    selected_row = original_model.getDataFrame().iloc[selected[0].row()]
    assert selected_row["stock_code"] == "2330"
    assert selected_row["source"] == "manual"
    assert analysis_selection_rows == [0]

    assert adapter.select_section("candidates")
    assert not view.stocks_table.isRowHidden(0)
    assert view.stocks_table.isRowHidden(1)
    assert not view.stocks_table.isRowHidden(2)
    assert view.stocks_table.isRowHidden(3)
    assert not view.stocks_table.isRowHidden(4)
    assert view.stocks_table.isRowHidden(5)
    assert "保留其他來源的候選" in adapter.section_status.text()
    assert "未能核對的舊收藏" in adapter.section_status.text()

    assert adapter.select_section("research_bookmarks")
    assert view.stocks_table.isRowHidden(0)
    assert not view.stocks_table.isRowHidden(1)
    assert view.stocks_table.isRowHidden(2)
    assert not view.stocks_table.isRowHidden(3)
    assert view.stocks_table.isRowHidden(4)
    assert not view.stocks_table.isRowHidden(5)
    assert "已核對保存身份的研究與查詢：3 筆" in adapter.section_status.text()

    assert adapter.select_section("saved_codes")
    assert adapter.candidate_panel.isHidden()
    assert not adapter.saved_codes_panel.isHidden()
    assert all(not view.stocks_table.isRowHidden(row) for row in range(original_model.rowCount()))
    assert adapter.section_status.text().startswith("這類清單只保存股票代碼")
    assert view.watchlist_service.read_calls == 0
    assert view.watchlist_service.write_calls == 0


def test_comparison_section_returns_selected_original_composite_envelope_only(
    qt_driver, typed_decoder,
):
    view = _View()
    qt_driver.addWidget(view)
    adapter = WatchlistProductLayout(view)
    assert adapter.install()
    emitted = []
    adapter.comparisonRequested.connect(emitted.append)

    assert adapter.select_section("comparison")
    assert "來源內比較" in adapter.comparison_status.text()
    assert "尚不支援另外建立或編輯獨立比較清單" in adapter.comparison_status.text()
    assert not adapter.comparison_button.isEnabled()
    assert adapter.main_splitter.isHidden()
    assert not adapter.comparison_panel.isHidden()

    assert adapter.select_section("research_bookmarks")
    view.stocks_table.selectRow(3)
    assert adapter.select_section("comparison")
    assert adapter.comparison_button.isEnabled()
    adapter.comparison_button.click()

    assert emitted == [typed_decoder]
    assert view.stocks_table.model() is view.stocks_model
    assert view.watchlist_service.read_calls == 0
    assert view.watchlist_service.write_calls == 0


def test_unknown_section_is_rejected_without_changing_selection(qt_driver, typed_decoder):
    view = _View()
    qt_driver.addWidget(view)
    adapter = WatchlistProductLayout(view)
    assert adapter.install()
    before = adapter._active_section

    assert not adapter.select_section("some-new-storage-kind")
    assert adapter._active_section == before


def _real_price_bookmark(exact_price_store):
    """用真實 F07 reader fixture 建立 typed Price 收藏，驗證正式身分契約。"""
    from decimal import Decimal

    session = _open_session(exact_price_store)
    query = session.create_query(
        unknown_price_policy="include",
        descending=True,
        min_close_price=Decimal("0.00000000000001"),
        max_close_price=Decimal("999999999999999.999999999999"),
        technical_stock_filter=("S0001", "S0002", "S0003"),
    )
    result = session.execute(query)
    for page_index in range(2):
        page = result.read_page(result.create_page_request(page_index, page_size=2))
        if any(row.technical_row.stock_code == "S0001" for row in page.rows):
            selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(
                query, page, "S0001"
            )
            return DailyMarketTechnicalUniversePriceBookmarkV1.create(
                selected=selection, scroll_position=19
            )
    raise AssertionError("fixture 中找不到 S0001 價格列")


def test_real_f07_price_bookmark_requires_payload_source_and_identity(
    qt_driver, exact_price_store,
):
    bookmark = _real_price_bookmark(exact_price_store)
    payload = bookmark.to_dict()
    assert "source" not in payload
    assert _bookmark_source(bookmark) == TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE
    source_id = _bookmark_payload_id(payload)
    assert source_id == bookmark.bookmark_identity_sha256

    code = bookmark.stock_code
    valid = {
        "證券代號": code,
        "stock_code": code,
        "source": TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE,
        "source_id": source_id,
        "research_bookmark": payload,
    }
    wrong_source = {**valid, "source": "wrong.price.source"}
    wrong_identity = {**valid, "source_id": "0" * 64}
    view = _View()
    qt_driver.addWidget(view)
    view.stocks_model = PandasTableModel(pd.DataFrame([valid, wrong_source, wrong_identity]))
    view.stocks_table.setModel(view.stocks_model)

    adapter = WatchlistProductLayout(view)
    assert adapter.install()
    assert adapter.select_section("research_bookmarks")
    assert not view.stocks_table.isRowHidden(0)
    assert view.stocks_table.isRowHidden(1)
    assert view.stocks_table.isRowHidden(2)


def test_loaded_model_reconnects_filter_and_comparison_to_current_selection_model(
    qt_driver, typed_decoder,
):
    view = _View()
    qt_driver.addWidget(view)
    old_model = view.stocks_model
    adapter = WatchlistProductLayout(view)
    assert adapter.install()
    assert adapter._connected_model is old_model

    new_model = PandasTableModel(_rows())
    view.stocks_model = new_model
    view.stocks_table.setModel(new_model)
    new_selection_model = view.stocks_table.selectionModel()
    view.watchlistLoaded.emit()

    assert adapter._connected_model is new_model
    assert adapter._connected_selection_model is new_selection_model
    assert adapter.select_section("research_bookmarks")
    view.stocks_table.selectRow(3)
    assert adapter.comparison_button.isEnabled()

    # 舊 model 的 layout 事件不得再觸發 adapter 去綁定目前的第三個 model。
    third_model = PandasTableModel(_rows())
    view.stocks_model = third_model
    view.stocks_table.setModel(third_model)
    old_model.setDataFrame(pd.DataFrame([]))
    assert adapter._connected_model is new_model

    view.watchlistLoaded.emit()
    assert adapter._connected_model is third_model
    assert adapter._connected_selection_model is view.stocks_table.selectionModel()
    assert adapter.select_section("candidates")
    assert view.stocks_table.isRowHidden(3)
    assert "保留其他來源的候選" in adapter.section_status.text()
    assert "未能核對的舊收藏" in adapter.section_status.text()
