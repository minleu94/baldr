import os
import sys
from datetime import date
from threading import Event, get_ident
from time import sleep
from types import SimpleNamespace

import pandas as pd
from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QMessageBox

import ui_qt.shared_market_research_consumer as shared_market_research_consumer
from ui_qt.models.pandas_table_model import PandasTableModel
from ui_qt.views.weak_industries_view import WeakIndustriesView
from ui_qt.views.weak_stocks_view import WeakStocksView
from ui_qt.views.strong_industries_view import StrongIndustriesView
from ui_qt.views.strong_stocks_view import StrongStocksView


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _wait_for(predicate, timeout_ms: int = 5000):
    if predicate():
        return
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(5)
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    poll.start()
    timeout.start(timeout_ms)
    loop.exec()
    poll.stop()
    timeout.stop()
    assert predicate(), "condition did not become true before timeout"


class _ScreeningService:
    def __init__(self) -> None:
        self.fail = False

    @staticmethod
    def _stocks() -> tuple[pd.DataFrame, int]:
        return (
            pd.DataFrame(
                [
                    {
                        "排名": 1,
                        "證券代號": "2330",
                        "證券名稱": "台積電",
                        "收盤價": "1000",
                        "漲幅%": "1.2",
                        "評分": "90",
                        "推薦理由": "測試",
                    }
                ]
            ),
            20,
        )

    @staticmethod
    def _industries() -> pd.DataFrame:
        return pd.DataFrame(
            [{"排名": 1, "指數名稱": "半導體", "收盤指數": "100", "漲幅%": "0.8"}]
        )

    def get_strong_stocks(self, *, period: str, top_n: int):
        if self.fail:
            raise RuntimeError("stock source unavailable")
        return self._stocks()

    def get_weak_stocks(self, *, period: str, top_n: int):
        if self.fail:
            raise RuntimeError("weak stock source unavailable")
        return self._stocks()

    def get_strong_industries(self, *, period: str, top_n: int):
        if self.fail:
            raise RuntimeError("industry source unavailable")
        return self._industries()

    def get_weak_industries(self, *, period: str, top_n: int):
        if self.fail:
            raise RuntimeError("weak industry source unavailable")
        return self._industries()


def _column_index(model: PandasTableModel, column_name: str) -> int:
    return model.getVisibleColumns().index(column_name)


def test_pandas_table_model_can_mark_positive_decline_column_red():
    model = PandasTableModel(pd.DataFrame([{"跌幅%": 9.9}]), red_positive_columns={"跌幅%"})
    index = model.index(0, 0)

    assert model.data(index, Qt.DisplayRole) == "9.90"
    assert model.data(index, Qt.ForegroundRole) == QColor(255, 68, 68)


def test_weak_stocks_show_decline_as_positive_value_with_red_semantic_color():
    app()
    view = WeakStocksView(screening_service=object())
    view._update_table_with_data(
        pd.DataFrame(
            [
                {
                    "排名": 1,
                    "證券代號": "2603",
                    "證券名稱": "長榮",
                    "收盤價": 100.0,
                    "漲幅%": -9.9,
                    "評分": "Bottom 1%",
                    "推薦理由": "相對弱勢",
                }
            ]
        )
    )

    assert view.stocks_model is not None
    decline_index = view.stocks_model.index(0, _column_index(view.stocks_model, "跌幅%"))
    assert view.stocks_model.data(decline_index, Qt.DisplayRole) == "9.90"
    assert view.stocks_model.data(decline_index, Qt.ForegroundRole) == QColor(255, 68, 68)


def test_weak_industries_show_decline_as_positive_value_with_red_semantic_color():
    app()
    view = WeakIndustriesView(screening_service=object())
    view._update_table_with_data(
        pd.DataFrame(
            [
                {
                    "排名": 1,
                    "指數名稱": "航運",
                    "收盤指數": 1234.5,
                    "漲幅%": -7.5,
                }
            ]
        )
    )

    assert view.industries_model is not None
    decline_index = view.industries_model.index(0, _column_index(view.industries_model, "跌幅%"))
    assert view.industries_model.data(decline_index, Qt.DisplayRole) == "7.50"
    assert view.industries_model.data(decline_index, Qt.ForegroundRole) == QColor(255, 68, 68)


def test_market_views_use_empty_models_instead_of_fake_zero_rows():
    app()
    service = _ScreeningService()
    views = (
        StrongStocksView(service),
        WeakStocksView(service),
        StrongIndustriesView(service),
        WeakIndustriesView(service),
    )

    for view in views:
        model = view.stocks_model if hasattr(view, "stocks_model") else view.industries_model
        assert model is not None
        assert model.rowCount() == 0
        assert "尚未載入" in view.status_label.text()
        view.deleteLater()


def test_market_views_clear_stale_rows_and_show_error_status(monkeypatch):
    app()
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *args, **kwargs: None))
    service = _ScreeningService()
    views = (
        StrongStocksView(service),
        WeakStocksView(service),
        StrongIndustriesView(service),
        WeakIndustriesView(service),
    )

    for view in views:
        if hasattr(view, "_refresh_stocks"):
            view._refresh_stocks(use_cache=False)
        else:
            view._refresh_industries(use_cache=False)
    _wait_for(lambda: views[0].status_label.text().startswith("已更新："))
    _wait_for(lambda: views[0]._screening_worker is None)
    counts = [
        (view.stocks_model if hasattr(view, "stocks_model") else view.industries_model).rowCount()
        for view in views
    ]
    statuses = [view.status_label.text() for view in views]
    assert counts == [1, 1, 1, 1], statuses
    assert views[0].universe_label.text() == "Universe: 20 stocks"
    assert "掃描範圍 20 檔" in statuses[0]
    assert "資料日未提供" in statuses[0]

    service.fail = True
    for view in views:
        if hasattr(view, "_refresh_stocks"):
            view._refresh_stocks(use_cache=False)
        else:
            view._refresh_industries(use_cache=False)
    _wait_for(lambda: views[0].status_label.text().startswith("載入失敗："))
    _wait_for(lambda: views[0]._screening_worker is None)

    for view in views:
        model = view.stocks_model if hasattr(view, "stocks_model") else view.industries_model
        assert model is not None
        assert model.rowCount() == 0
        assert view.status_label.text().startswith("載入失敗：")
    assert views[0].universe_label.text() == "Universe: unavailable"

    for view in views:
        view.deleteLater()


def test_strong_stocks_status_shows_dto_effective_date_including_cached_view():
    app()
    dto = SimpleNamespace(
        effective_date=date(2026, 10, 27),
        to_legacy=_ScreeningService._stocks,
    )
    service = SimpleNamespace(get_strong_stocks_dto=lambda **_: dto)
    view = StrongStocksView(service)

    view._refresh_stocks(use_cache=False)
    assert view.status_label.text().startswith("載入中…")
    _wait_for(lambda: view.status_label.text().startswith("已更新："))
    _wait_for(lambda: view._screening_worker is None)
    assert "資料日 2026-10-27" in view.status_label.text()
    assert view.universe_label.text() == "Universe: 20 stocks"

    view._cached_data["week"] = _ScreeningService._stocks()[0]
    view._cached_effective_dates["week"] = date(2026, 10, 24)
    view._cached_universe_counts["week"] = 31
    view._on_period_changed("week")
    assert "資料日 2026-10-24" in view.status_label.text()
    assert "掃描範圍 31 檔" in view.status_label.text()
    assert view.universe_label.text() == "Universe: 31 stocks"
    view.deleteLater()


def test_strong_stocks_status_marks_dto_without_effective_date_as_unprovided():
    app()
    dto = SimpleNamespace(
        effective_date=None,
        to_legacy=_ScreeningService._stocks,
    )
    service = SimpleNamespace(get_strong_stocks_dto=lambda **_: dto)
    view = StrongStocksView(service)

    view._refresh_stocks(use_cache=False)
    _wait_for(lambda: view.status_label.text().startswith("已更新："))
    _wait_for(lambda: view._screening_worker is None)

    assert "資料日未提供" in view.status_label.text()
    view.deleteLater()


def test_strong_stocks_table_shows_row_market_date_and_marks_missing_date_unprovided():
    app()
    view = StrongStocksView(SimpleNamespace())
    view._update_table_with_data(
        pd.DataFrame(
            [
                {"排名": 1, "證券代號": "2330", "證券名稱": "台積電", "行情日": "2026-10-27"},
                {"排名": 2, "證券代號": "2317", "證券名稱": "鴻海", "行情日": None},
            ]
        )
    )

    market_date_column = _column_index(view.stocks_model, "行情日")
    model_frame = view.stocks_model.getDataFrame()
    assert model_frame.iloc[0, market_date_column] == "2026-10-27"
    assert model_frame.iloc[1, market_date_column] == "未提供"
    assert view.stocks_search_count_label.text() == "目前清單 2 檔"

    view._update_table_with_data(
        pd.DataFrame([{"排名": 1, "證券代號": "2330", "證券名稱": "台積電"}])
    )
    assert view.stocks_model.getDataFrame().iloc[0, market_date_column] == "未提供"
    view.deleteLater()


def test_strong_stocks_local_search_filters_loaded_rows_and_restores_them():
    app()
    view = StrongStocksView(SimpleNamespace())
    frame = pd.DataFrame(
        [
            {"排名": 1, "證券代號": "2330", "證券名稱": "台積電"},
            {"排名": 2, "證券代號": "2454", "證券名稱": "聯發科"},
            {"排名": 3, "證券代號": "2317", "證券名稱": "鴻海"},
        ]
    )
    view._update_table_with_data(frame)
    view.universe_label.setText("Universe: 20 stocks")
    view._set_status_label(view.status_label, "已更新：3 筆", level="success")
    source_model = view.stocks_model

    assert view.stocks_search_count_label.text() == "目前清單 3 檔"
    assert view.stocks_search_input.accessibleName() == "強勢個股目前清單搜尋"
    assert "不會重新查詢" in view.stocks_search_input.accessibleDescription()

    view.stocks_search_input.setText("2330")
    assert view.stocks_search_count_label.text() == "符合 1／3 檔"
    assert [view.stocks_table.isRowHidden(row) for row in range(3)] == [False, True, True]

    view.stocks_search_input.setText("聯發")
    assert view.stocks_search_count_label.text() == "符合 1／3 檔"
    assert [view.stocks_table.isRowHidden(row) for row in range(3)] == [True, False, True]

    view.stocks_search_input.setText("不存在")
    assert view.stocks_search_count_label.text() == "此清單無符合標的（0／3）"
    assert all(view.stocks_table.isRowHidden(row) for row in range(3))

    view.stocks_search_input.clear()
    assert view.stocks_search_count_label.text() == "目前清單 3 檔"
    assert not any(view.stocks_table.isRowHidden(row) for row in range(3))
    assert view.stocks_model is source_model
    assert view.stocks_model.rowCount() == 3

    code_column = _column_index(view.stocks_model, "證券代號")
    view.stocks_table.sortByColumn(code_column, Qt.SortOrder.DescendingOrder)
    sorted_codes = view.stocks_model.getDataFrame()["證券代號"].tolist()
    view.stocks_table.selectRow(sorted_codes.index("2330"))
    view.stocks_search_input.setText("2454")
    assert view.stocks_search_count_label.text() == "符合 1／3 檔"
    assert [view.stocks_table.isRowHidden(row) for row in range(3)] == [
        code != "2454" for code in sorted_codes
    ]
    assert not view.stocks_table.selectionModel().selectedRows()
    view.stocks_search_input.clear()
    assert not any(view.stocks_table.isRowHidden(row) for row in range(3))
    assert view.universe_label.text() == "Universe: 20 stocks"
    assert view.status_label.text() == "已更新：3 筆"
    view.deleteLater()


def test_strong_stocks_local_search_distinguishes_unloaded_and_loaded_empty():
    app()
    view = StrongStocksView(SimpleNamespace())
    assert view.stocks_search_count_label.text() == "尚未載入"

    view._update_table_with_data(
        pd.DataFrame(columns=["排名", "證券代號", "證券名稱"])
    )
    assert view.stocks_search_count_label.text() == "目前清單 0 檔（已載入空清單）"

    view.stocks_search_input.setText("2330")
    assert view.stocks_search_count_label.text() == "符合 0／0 檔（已載入空清單）"
    view.deleteLater()


def test_strong_stocks_shared_result_search_does_not_change_source_scope_or_query(
    monkeypatch,
):
    app()
    frame = pd.DataFrame(
        [
            {"原始名次": 1, "證券代號": "2330"},
            {"原始名次": 2, "證券代號": "2454"},
        ]
    )
    monkeypatch.setattr(
        shared_market_research_consumer,
        "shared_market_research_frame",
        lambda _read: frame.copy(),
    )
    monkeypatch.setattr(
        shared_market_research_consumer,
        "shared_market_research_summary",
        lambda _read: ("已核驗快照摘要", "快照稽核資料"),
    )
    view = StrongStocksView(SimpleNamespace())
    selector = view.shared_research_mode_selector
    selector.setCurrentIndex(selector.findData("shared_research"))
    assert view.stocks_search_input.placeholderText() == "股票代號（快照目前不含名稱）"
    assert "只有股票代號欄" in view.stocks_search_input.accessibleDescription()

    query = SimpleNamespace(combine_mode="AND", filter_state="match")
    read = SimpleNamespace(query=query, ranking_error="")
    view._on_shared_research_result(read)
    source_scope = view.source_scope_label.text()
    requested_queries = []
    view.request_shared_research = lambda: requested_queries.append("requested")

    view.stocks_search_input.setText("台積")
    assert view.stocks_search_count_label.text() == "此清單無符合標的（0／2）"
    view.stocks_search_input.setText("2330")

    assert view._shared_read is read
    assert read.query is query
    assert view.source_scope_label.text() == source_scope
    assert view.stocks_search_count_label.text() == "符合 1／2 檔"
    assert [view.stocks_table.isRowHidden(row) for row in range(2)] == [False, True]
    assert requested_queries == []
    view.deleteLater()


def test_strong_stock_load_runs_in_worker_and_applies_result_on_gui_thread():
    app()
    main_thread = get_ident()
    source_threads = []
    render_threads = []

    def load_dto(**_kwargs):
        source_threads.append(get_ident())
        sleep(0.05)
        return SimpleNamespace(
            effective_date=date(2026, 10, 27),
            to_legacy=_ScreeningService._stocks,
        )

    view = StrongStocksView(SimpleNamespace(get_strong_stocks_dto=load_dto))
    original_render = view._update_table_with_data

    def render_on_gui_thread(frame):
        render_threads.append(get_ident())
        original_render(frame)

    view._update_table_with_data = render_on_gui_thread
    view._refresh_stocks(use_cache=False)

    assert view.status_label.text().startswith("載入中…")
    assert not view.load_btn.isEnabled()
    _wait_for(lambda: view.status_label.text().startswith("已更新："))

    assert source_threads and source_threads[0] != main_thread
    assert render_threads == [main_thread]
    _wait_for(lambda: view._screening_worker is None)
    assert view.load_btn.isEnabled()
    view.deleteLater()


def test_strong_stock_period_switch_discards_slow_old_generation():
    app()
    started = Event()
    release = Event()

    def load_dto(*, period: str, **_kwargs):
        if period == "day":
            started.set()
            release.wait(timeout=2)
        return SimpleNamespace(
            effective_date=date(2026, 10, 27),
            to_legacy=_ScreeningService._stocks,
        )

    view = StrongStocksView(SimpleNamespace(get_strong_stocks_dto=load_dto))
    view._refresh_stocks(use_cache=False)
    assert started.wait(timeout=2)

    view._on_period_changed("week")
    assert view.status_label.text().startswith("尚未載入：")
    assert view.universe_label.text() == "Universe: -"
    assert view.stocks_model is not None
    assert view.stocks_model.rowCount() == 0

    release.set()
    _wait_for(
        lambda: view._screening_worker is None
        and not view._retired_screening_workers
    )
    assert view.status_label.text().startswith("尚未載入：")
    assert view._cached_data["day"] is None
    assert view.stocks_model.rowCount() == 0
    view.deleteLater()


def test_industry_rows_drill_down_to_read_only_stock_research_context_without_watchlist_write():
    app()
    row = pd.DataFrame(
        [
            {
                "排名": 2,
                "產業名稱": "半導體業",
                "指數名稱": "半導體類指數",
                "產業層級": "leaf",
                "市場範圍": "twse",
                "收盤指數": "100",
                "漲幅%": "2.00",
                "相對大盤超額BP": 120,
                "5日漲幅BP": 200,
                "20日漲幅BP": 500,
                "成分數": 1,
                "20日有效成分": 1,
                "20日覆蓋率BP": 10000,
                "代表股票代號": "2330, 2454",
                "代表股票名稱": "台積電, 聯發科",
                "代表股票": "2330 台積電, 2454 聯發科",
                "資料日": "2026-09-14",
                "資料來源": "industry_strength.sqlite_current_research",
                "資料版本": "industry-strength.current-research.v1",
                "映射來源": "meta_data.companies.csv",
                "映射版本": "tw-industry-explicit-map.v1",
                "映射觀測日": "2026-08-11",
                "資料品質": "degraded",
            },
            {
                "排名": 1,
                "產業名稱": "金融保險",
                "指數名稱": "金融保險類指數",
                "產業層級": "leaf",
                "市場範圍": "twse",
                "收盤指數": "80",
                "漲幅%": "-1.00",
                "相對大盤超額BP": -80,
                "5日漲幅BP": -100,
                "20日漲幅BP": -300,
                "成分數": 1,
                "20日有效成分": 1,
                "20日覆蓋率BP": 10000,
                "代表股票代號": "2883",
                "代表股票名稱": "凱基金",
                "代表股票": "2883 凱基金",
                "資料日": "2026-09-13",
                "資料來源": "industry_strength.sqlite_current_research",
                "資料版本": "industry-strength.current-research.v1",
                "映射來源": "meta_data.companies.csv",
                "映射版本": "tw-industry-explicit-map.v1",
                "映射觀測日": "2026-08-11",
                "資料品質": "degraded",
            },
        ]
    )
    for view in (StrongIndustriesView(object()), WeakIndustriesView(object())):
        contexts = []
        view.stockResearchRequested.connect(contexts.append)
        view._update_table_with_data(row)
        rank_column = _column_index(view.industries_model, "排名")
        view.industries_model.sort(rank_column, Qt.DescendingOrder)
        view._select_representative_row(view.industries_model.index(0, 0))
        assert view.representative_selector.count() == 2
        visible_columns = view.industries_model.getVisibleColumns()
        assert visible_columns[:3] == ["排名", "產業名稱", "產業層級"]
        assert view.industries_model.data(
            view.industries_model.index(0, visible_columns.index("產業名稱")),
            Qt.DisplayRole,
        ) == "半導體業"
        view.representative_selector.setCurrentIndex(1)
        view.open_representative_button.click()

        assert len(contexts) == 1
        context = contexts[0]
        assert context.stock_code == "2454"
        assert context.stock_name == "聯發科"
        assert context.source_kind == "industry_strength"
        assert context.source_workspace == "market_explore"
        assert context.source_id == "industry_strength.sqlite_current_research"
        assert context.source_version == "industry-strength.current-research.v1"
        assert context.mapping_source_id == "meta_data.companies.csv"
        assert context.mapping_version == "tw-industry-explicit-map.v1"
        assert context.mapping_observed_date == "2026-08-11"
        view.deleteLater()


def test_comparable_industry_controls_show_session_windows_and_separate_levels():
    app()
    comparable_service = SimpleNamespace(industry_strength_service=object())
    rows = pd.DataFrame(
        [
            {
                "排名": 1,
                "產業名稱": "綜合醫療",
                "產業層級": "aggregate",
                "漲幅%": "-1.00",
                "5日漲幅%": "-1.00",
                "20日漲幅%": "-2.00",
                "5日超額%": "-0.50",
                "20日超額%": "-1.50",
                "5日覆蓋率%": "100.00",
                "20日覆蓋率%": "100.00",
                "資料品質": "observed",
            },
            {
                "排名": 1,
                "產業名稱": "細分半導體",
                "產業層級": "leaf",
                "漲幅%": "2.00",
                "5日漲幅%": "2.00",
                "20日漲幅%": "4.00",
                "5日超額%": "1.50",
                "20日超額%": "3.50",
                "5日覆蓋率%": "100.00",
                "20日覆蓋率%": "100.00",
                "資料品質": "degraded",
            },
        ]
    )
    for view_type in (StrongIndustriesView, WeakIndustriesView):
        view = view_type(comparable_service)
        assert view.period_btn_day.text() == "近5交易日"
        assert view.period_btn_week.text() == "近20交易日"
        view._cached_data["day"] = rows.copy()
        view._update_table_with_data(rows)

        assert view.industries_model is not None
        assert view.industries_model.rowCount() == 1
        visible = view.industries_model.getVisibleColumns()
        assert view.industries_model.data(
            view.industries_model.index(0, visible.index("產業層級")), Qt.DisplayRole
        ) == "細分產業"
        assert view.industries_model.data(
            view.industries_model.index(0, visible.index("資料品質")), Qt.DisplayRole
        ) == "降級"

        view.level_selector.setCurrentIndex(1)
        assert view.industries_model.rowCount() == 1
        assert view.industries_model.data(
            view.industries_model.index(0, visible.index("產業名稱")), Qt.DisplayRole
        ) == "綜合醫療"
        assert view.industries_model.data(
            view.industries_model.index(0, visible.index("產業層級")), Qt.DisplayRole
        ) == "綜合類別"

        view.level_selector.setCurrentIndex(2)
        assert view.industries_model.rowCount() == 2
        view.deleteLater()
