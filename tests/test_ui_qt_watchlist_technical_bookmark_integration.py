"""候選池整合完整母體收藏控制項與 typed reopen。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app_module.daily_market_technical_universe_v4_bookmark import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE,
    DailyMarketTechnicalUniverseV4Bookmark,
    DailyMarketTechnicalUniverseV4BookmarkState,
    create_daily_market_technical_universe_v4_bookmark,
)
from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionRequest,
    produce_daily_market_technical_universe_v4,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4Query,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4Cohort,
)
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from app_module.watchlist_service import WatchlistService
from ui_qt.views.watchlist_view import WatchlistView


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    return instance


def _wait_for(app: QApplication, predicate: Any, *, timeout_seconds: float = 40.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("候選池完整母體收藏背景工作逾時")
        time.sleep(0.005)
    app.processEvents()


def _create_service(
    tmp_path: Path,
    *,
    include_invalid_bookmark_row: bool,
) -> tuple[
    WatchlistService,
    DailyMarketTechnicalUniverseV4Bookmark,
    DailyMarketTechnicalUniverseV4Query,
]:
    """以真實 SQLite producer 與隔離 COW 建立可重開的完整母體收藏。"""

    database = tmp_path / "synthetic-daily-prices.sqlite"
    decision = date(2026, 10, 6)
    stock_codes = ("2382", "9999")
    connection = sqlite3.connect(database)
    with connection:
        connection.execute(
            "CREATE TABLE daily_prices "
            "(日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER)"
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
            [
                (
                    (decision - timedelta(days=39 - offset)).isoformat(),
                    code,
                    str(100 + offset),
                    str(101 + offset),
                    str(99 + offset),
                    str(100 + offset),
                    1000 + offset,
                )
                for code in stock_codes
                for offset in range(40)
            ],
        )
    connection.close()

    capture_scope = ResearchCaptureWriteScope(tmp_path / "research-output", database)
    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-watchlist-full-n",
        population_version="fixture-v1",
        decision_date=decision,
        raw_stock_codes=stock_codes,
    )
    store_root = capture_scope.root / "technical-universe"
    produced = produce_daily_market_technical_universe_v4(
        DailyMarketTechnicalUniverseV4ProductionRequest(
            source_database=database,
            cohort=cohort,
            decision_cutoff=datetime(
                2026, 10, 6, 16, 0, tzinfo=ZoneInfo("Asia/Taipei")
            ),
            store_output_root=store_root,
            research_scope=capture_scope,
        )
    )
    assert produced.status == "complete", produced.to_dict()
    assert produced.plan is not None and produced.receipt is not None
    assert produced.plan_sha256 is not None
    query = DailyMarketTechnicalUniverseV4Query.create(
        store_output_root=store_root,
        generation_identity_sha256=produced.plan.generation_identity_sha256,
        plan_identity_sha256=produced.plan.identity_sha256,
        plan_sha256=produced.plan_sha256,
        receipt_identity_sha256=produced.receipt.identity_sha256,
        receipt_sha256=produced.receipt.content_sha256,
        page_size=10,
    )
    bookmark = create_daily_market_technical_universe_v4_bookmark(
        query,
        "2382",
        scroll_position=11,
    )

    watchlist_root = tmp_path / "watchlist-output"
    config = SimpleNamespace(
        output_root=watchlist_root,
        resolve_output_path=lambda relative: watchlist_root / relative,
    )
    initial_service = WatchlistService(config)
    assert initial_service.add_research_bookmark(bookmark).status == "added"
    if include_invalid_bookmark_row:
        assert initial_service.add_stocks(
            [{"stock_code": "7777", "stock_name": "錯誤收藏列"}],
            source=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE,
        ) == 1
    assert initial_service.add_stocks(
        [{"stock_code": "8888", "stock_name": "一般列"}],
        source="manual",
    ) == 1
    assert initial_service.upgrade_to_repository().is_repository

    repository, storage_status = WatchlistService.discover_repository(config)
    assert repository is not None
    service = WatchlistService(
        config,
        repository=repository,
        storage_status=storage_status,
    )
    database.unlink()
    return service, bookmark, query


def _bookmark_rows(view: WatchlistView) -> list[tuple[int, dict[str, object]]]:
    assert view.stocks_model is not None
    frame = view.stocks_model.getDataFrame()
    result: list[tuple[int, dict[str, object]]] = []
    for row_number, (_, row) in enumerate(frame.iterrows()):
        payload = row.get("research_bookmark")
        if isinstance(payload, dict):
            result.append((row_number, payload))
    return result


def test_watchlist_view_refreshes_and_forwards_typed_bookmark_state(
    app: QApplication,
    tmp_path: Path,
) -> None:
    service, bookmark, query = _create_service(
        tmp_path,
        include_invalid_bookmark_row=True,
    )
    view = WatchlistView(service)
    emitted: list[object] = []
    legacy_research: list[object] = []
    latest_research: list[object] = []
    view.technicalBookmarkStateReady.connect(emitted.append)
    view.stockResearchRequested.connect(legacy_research.append)
    view.latestResearchRequested.connect(latest_research.append)

    try:
        _wait_for(app, lambda: view.technical_bookmark_controls._worker is None)
        assert view.technical_bookmark_controls.bookmarks.count() == 2
        model = view.stocks_model
        assert model is not None
        frame = model.getDataFrame()
        assert "完整母體技術研究收藏" in frame.iloc[0]["來源"]
        assert "完整母體書籤內容缺失" in frame.iloc[1]["每日研究收藏"]
        manual = frame.query("證券代號 == '8888'").iloc[0]
        assert manual["來源"] == "manual"
        assert manual["每日研究收藏"] == "—"

        second = create_daily_market_technical_universe_v4_bookmark(
            query,
            "9999",
            scroll_position=23,
        )
        assert service.add_research_bookmark(second).status == "added"
        view.refresh_all()
        _wait_for(app, lambda: view.technical_bookmark_controls._worker is None)
        assert view.technical_bookmark_controls.bookmarks.count() == 3

        matching_rows = [
            row_number
            for row_number, payload in _bookmark_rows(view)
            if payload.get("bookmark_identity_sha256") == bookmark.bookmark_identity_sha256
        ]
        assert len(matching_rows) == 1
        view.stocks_table.selectRow(matching_rows[0])
        assert view.stock_analysis_btn.isEnabled() is False
        assert view.latest_research_btn.isEnabled() is False
        view._open_stock_analysis()
        assert legacy_research == []
        assert "拒絕舊個股研究路徑" in view.status_label.text()
        assert view._open_latest_source_research() is False
        assert latest_research == []

        control = view.technical_bookmark_controls
        selected_row = next(
            index
            for index in range(control.bookmarks.count())
            if getattr(
                control.bookmarks.item(index).data(Qt.ItemDataRole.UserRole),
                # Qt.UserRole 保存的是控制項已驗證的 exact bookmark entry。
                "bookmark_id",
                "",
            )
            == bookmark.bookmark_identity_sha256
        )
        control.bookmarks.setCurrentRow(selected_row)
        control.open_selected()
        _wait_for(app, lambda: control._worker is None)
        assert len(emitted) == 1
        state = emitted[0]
        assert isinstance(state, DailyMarketTechnicalUniverseV4BookmarkState)
        assert state.bookmark.bookmark_identity_sha256 == bookmark.bookmark_identity_sha256
        assert state.selected_stock.snapshot.stock_code == "2382"

        request_before_close = view._analysis_request_id
        view.close()
        app.processEvents()
        assert view._analysis_request_id == request_before_close + 1
        assert control._closing is True
    finally:
        view.close()
        app.processEvents()


def test_full_n_delete_and_clear_use_exact_identity_not_stock_code(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, first, query = _create_service(
        tmp_path,
        include_invalid_bookmark_row=False,
    )
    second = create_daily_market_technical_universe_v4_bookmark(
        query,
        "2382",
        scroll_position=29,
    )
    assert first.bookmark_identity_sha256 != second.bookmark_identity_sha256
    assert service.add_research_bookmark(second).status == "added"
    view = WatchlistView(service)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *_args, **_kwargs: pytest.fail("精確刪除不應失敗"),
    )
    monkeypatch.setattr(
        service,
        "remove_stocks",
        lambda *_args, **_kwargs: pytest.fail("full-N 收藏不得按股票代碼刪除"),
    )

    try:
        _wait_for(app, lambda: view.technical_bookmark_controls._worker is None)
        model = view.stocks_model
        assert model is not None
        frame = model.getDataFrame()
        rows = [
            row_number
            for row_number, (_, row) in enumerate(frame.iterrows())
            if isinstance(row.get("research_bookmark"), dict)
            and row["research_bookmark"].get("bookmark_identity_sha256")
            == first.bookmark_identity_sha256
        ]
        assert len(rows) == 1
        payload = frame.iloc[rows[0]]["research_bookmark"]
        assert "bookmark_id" not in payload
        view.stocks_table.selectRow(rows[0])
        view._remove_selected()

        remaining_ids = {
            row.get("research_bookmark", {}).get("bookmark_identity_sha256")
            for row in service.get_stocks()
            if isinstance(row.get("research_bookmark"), dict)
        }
        assert first.bookmark_identity_sha256 not in remaining_ids
        assert second.bookmark_identity_sha256 in remaining_ids

        view._clear_watchlist()
        assert service.get_stocks() == []
    finally:
        view.close()
        app.processEvents()
