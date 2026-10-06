from __future__ import annotations

import os
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem

import ui_qt.views.daily_market_research_view as daily_research_module
from app_module.research_session import ResearchStockContextDTO
from ui_qt.views.daily_market_research_view import DailyMarketResearchView
from ui_qt.views.watchlist_view import WatchlistView


_HASH_A = "a" * 64
_HASH_B = "b" * 64
_ROOT = "C:/qa/daily-market-snapshots"
_COHORT = "ux03-cohort"
_DATE = "2026-10-02"
_DATA_DATE = "2026-10-01"
_CONDITIONS = "close_above_ma20,close_above_ma60"


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _context(
    bookmark_id: str,
    stock_code: str,
    *,
    source_hash: str = _HASH_A,
    query_hash: str = "query-a",
    data_date: str = _DATA_DATE,
    condition_keys: str = _CONDITIONS,
    combine_mode: str = "AND",
) -> ResearchStockContextDTO:
    return ResearchStockContextDTO(
        stock_code=stock_code,
        stock_name=f"Stock {stock_code}",
        decision_date=_DATE,
        data_date=data_date,
        source_snapshot_id=f"manifest-{source_hash[0]}",
        source_snapshot_hash=source_hash,
        source_kind="daily_market_research_snapshot",
        source_label="每日市場研究收藏",
        source_workspace="watchlist",
        source_id=bookmark_id,
        daily_snapshot_root=_ROOT,
        daily_snapshot_cohort_id=_COHORT,
        daily_snapshot_condition_keys=condition_keys,
        daily_snapshot_combine_mode=combine_mode,
    )


def _bookmark(
    bookmark_id: str,
    stock_code: str,
    *,
    source_hash: str = _HASH_A,
    query_hash: str = "query-a",
    decision_date: str = _DATE,
    data_date: str = _DATA_DATE,
    condition_keys: str = _CONDITIONS,
    combine_mode: str = "AND",
    root: str = _ROOT,
    cohort_id: str = _COHORT,
    schema_version: str = "daily-market-research-bookmark.v1",
) -> dict[str, Any]:
    keys = condition_keys.split(",") if condition_keys else []
    return {
        "schema_version": schema_version,
        "bookmark_id": bookmark_id,
        "payload_sha256": "c" * 64,
        "query_sha256": query_hash,
        "filter_state": "match",
        "stock_code": stock_code,
        "stock_name": f"Stock {stock_code}",
        "source_snapshot_id": f"manifest-{source_hash[0]}",
        "source_snapshot_hash": source_hash,
        "snapshot_identity_sha256": "d" * 64,
        "input_fingerprint_sha256": "e" * 64,
        "decision_date": decision_date,
        "data_date": data_date,
        "snapshot_root": root,
        "cohort_id": cohort_id,
        "declared_stock_codes": ["2330", "1101"],
        "condition_keys": keys,
        "combine_mode": combine_mode,
        "method_contracts": {"close_above_ma20": {"version": "1"}},
        "method_contracts_sha256": "f" * 64,
        "conditions": [],
        "combined_state": "match",
        "why": [],
        "why_not": [],
        "completeness": "complete_declared_cohort",
        "manifest_schema_version": "daily-market-snapshot.v2",
        "sort_key": "stock_code",
        "descending": False,
        "context": {"source_id": bookmark_id},
    }


class _WatchlistStub:
    def __init__(self, stocks: list[dict[str, Any]]) -> None:
        self.stocks = list(stocks)
        self.contexts = {
            record["bookmark_id"]: _context(
                record["bookmark_id"],
                record["stock_code"],
                source_hash=record["source_snapshot_hash"],
                query_hash=record["query_sha256"],
                data_date=record["data_date"],
                condition_keys=",".join(record["condition_keys"]),
                combine_mode=record["combine_mode"],
            )
            for record in (
                item.get("research_bookmark")
                for item in stocks
                if isinstance(item.get("research_bookmark"), dict)
                and item.get("research_bookmark", {}).get("bookmark_id")
                and item.get("research_bookmark", {}).get("stock_code")
                and item.get("research_bookmark", {}).get("source_snapshot_hash")
                and item.get("research_bookmark", {}).get("query_sha256")
                and item.get("research_bookmark", {}).get("condition_keys") is not None
                and item.get("research_bookmark", {}).get("combine_mode")
                and item.get("research_bookmark", {}).get("data_date") is not None
            )
        }
        self.context_calls: list[str] = []
        self.add_calls: list[object] = []
        self.remove_bookmark_calls: list[str] = []
        self.remove_legacy_calls: list[tuple[str, str, str]] = []
        self.remove_stocks_calls: list[list[str]] = []
        self.restore_calls: list[object] = []
        self.bad_bookmark_ids: set[str] = set()

    def get_stocks(self):
        return list(self.stocks)

    def get_research_bookmark_context(self, bookmark_id: str):
        self.context_calls.append(bookmark_id)
        if bookmark_id in self.bad_bookmark_ids:
            raise ValueError("unsupported or corrupt research bookmark")
        return self.contexts.get(bookmark_id)

    def add_research_bookmark(self, bookmark: object):
        self.add_calls.append(bookmark)
        return SimpleNamespace(status="added", message="added")

    def remove_research_bookmark(self, bookmark_id: str):
        self.remove_bookmark_calls.append(bookmark_id)
        return SimpleNamespace(
            status="removed", restore_token=f"restore:{bookmark_id}"
        )

    def remove_watchlist_item(
        self, stock_code: str, source_id: str, expected_source: str
    ):
        self.remove_legacy_calls.append((stock_code, source_id, expected_source))
        return SimpleNamespace(status="removed")

    def remove_stocks(self, stock_codes: list[str]):
        self.remove_stocks_calls.append(list(stock_codes))
        raise AssertionError("generic code removal must not remove a bookmark row")

    def restore_research_bookmark(self, token: object):
        self.restore_calls.append(token)
        return SimpleNamespace(status="restored")


def _watchlist_item(
    stock_code: str,
    *,
    name: str | None = None,
    source: str = "manual",
    source_id: str = "",
    research_bookmark: object = None,
) -> dict[str, Any]:
    return {
        "stock_code": stock_code,
        "stock_name": name or f"Stock {stock_code}",
        "added_at": "2026-10-05T00:00:00",
        "source": source,
        "source_id": source_id,
        "decision_identity": {},
        "research_bookmark": research_bookmark,
    }


def _daily_view(
    watchlist_service: object | None,
    *,
    confirm=None,
) -> tuple[DailyMarketResearchView, object, object]:
    daily_service = SimpleNamespace()
    view = DailyMarketResearchView(
        daily_service,
        watchlist_service=watchlist_service,
        bookmark_confirmation_callback=confirm,
    )
    snapshot = SimpleNamespace(
        manifest={
            "cohort_id": _COHORT,
            "decision_date": _DATE,
            "method_contracts_sha256": "f" * 64,
            "source_snapshot_id": "manifest-a",
        },
        manifest_sha256=_HASH_A,
        manifest_identity_sha256="d" * 64,
    )
    row = SimpleNamespace(
        stock_code="2330",
        cohort_id=_COHORT,
        decision_date=_DATE,
        data_date=_DATA_DATE,
        source_snapshot_id="manifest-a",
        source_snapshot_hash=_HASH_A,
        condition_keys=("close_above_ma20", "close_above_ma60"),
        combine_mode="AND",
    )
    view._snapshot = snapshot
    view.sort_key_combo.setCurrentIndex(view.sort_key_combo.findData("ma20"))
    view.sort_direction_combo.setCurrentIndex(view.sort_direction_combo.findData("desc"))
    view.filter_state_combo.setCurrentIndex(view.filter_state_combo.findData("match"))
    view.results_table.setRowCount(1)
    item = QTableWidgetItem("2330")
    item.setData(Qt.ItemDataRole.UserRole, row)
    view.results_table.setItem(0, 0, item)
    view.results_table.selectRow(0)
    view._sync_open_button()
    return view, snapshot, row


def test_daily_bookmark_add_runs_only_after_explicit_confirmation_and_keeps_query(
    monkeypatch,
):
    _app()
    watchlist = _WatchlistStub([])
    view, snapshot, row = _daily_view(watchlist, confirm=lambda _bookmark: True)
    created: list[tuple[object, object, dict[str, object]]] = []
    bookmark = SimpleNamespace(
        bookmark_id="bookmark-2330",
        source_snapshot_id="manifest-a",
        source_snapshot_hash=_HASH_A,
        decision_date=_DATE,
        query={"conditions": ["close_above_ma20", "close_above_ma60"]},
        method_contracts_sha256="f" * 64,
    )

    def create(verified, selected_row, **kwargs):
        created.append((verified, selected_row, kwargs))
        return bookmark

    monkeypatch.setattr(
        daily_research_module,
        "create_daily_market_research_bookmark",
        create,
    )
    saved: list[object] = []
    view.bookmarkSaved.connect(saved.append)

    assert view.bookmark_selected_research()
    assert created == [
        (
            snapshot,
            row,
            {
                "sort_key": "ma20",
                "descending": True,
                "filter_state": "match",
                "stock_name": "",
            },
        )
    ]
    assert watchlist.add_calls == [bookmark]
    assert saved == [bookmark]
    assert view.bookmark_selected_research_button.isEnabled()
    view.close()


def test_daily_bookmark_cancel_and_missing_service_do_not_write(monkeypatch):
    _app()
    watchlist = _WatchlistStub([])
    view, _snapshot, _row = _daily_view(watchlist, confirm=lambda _bookmark: False)
    monkeypatch.setattr(
        daily_research_module,
        "create_daily_market_research_bookmark",
        lambda *_args, **_kwargs: SimpleNamespace(bookmark_id="cancelled"),
    )
    assert not view.bookmark_selected_research()
    assert not watchlist.add_calls
    view.close()

    no_service_view, _snapshot, _row = _daily_view(None, confirm=lambda _bookmark: True)
    assert not no_service_view.bookmark_selected_research_button.isEnabled()
    assert not no_service_view.bookmark_selected_research()
    no_service_view.close()


def test_daily_explicit_latest_read_uses_bookmark_cohort_once_without_producing(monkeypatch):
    _app()
    calls: list[tuple[str, str]] = []
    service = SimpleNamespace(
        read_latest=lambda cohort_id, **_kwargs: (
            calls.append(("read_latest", cohort_id)) or SimpleNamespace()
        ),
        produce_snapshot=lambda *_args, **_kwargs: calls.append(("produce", "")),
    )
    context = _context("bookmark-2330", "2330")
    view = DailyMarketResearchView(service)
    operations = []
    accepted = []

    def capture(kind, operation):
        operations.append((kind, operation(lambda: False)))

    monkeypatch.setattr(view, "_start_operation", capture)
    monkeypatch.setattr(
        view,
        "_accept_snapshot",
        lambda snapshot, *, sync_cutoff: accepted.append((snapshot, sync_cutoff)),
    )
    assert view.open_latest_research(context)
    view.on_first_open()
    assert operations and operations[0][0] == "latest_research_read"
    assert calls == [("read_latest", _COHORT)]
    assert view.cohort_id_input.text() == _COHORT
    assert view.combine_mode_combo.currentData() == "AND"
    assert view._initial_read_started
    view._on_operation_finished(
        view._operation_generation, operations[0][0], operations[0][1]
    )
    assert accepted == [(operations[0][1], True)]
    view.close()


def _mixed_watchlist() -> tuple[_WatchlistStub, ResearchStockContextDTO]:
    record_a = _bookmark("bookmark-2330-a", "2330", query_hash="query-a")
    record_b = _bookmark("bookmark-2330-b", "2330", query_hash="query-b")
    record_1101 = _bookmark("bookmark-1101-a", "1101", query_hash="query-a")
    other_snapshot = _bookmark(
        "bookmark-1101-other", "1101", source_hash=_HASH_B, query_hash="query-a"
    )
    items = [
        _watchlist_item("2330", source="manual"),
        _watchlist_item("2330", source="recommendation", source_id="advice-2330"),
        _watchlist_item(
            "2330", source="daily_market_research_bookmark", source_id="bookmark-2330-a",
            research_bookmark=record_a,
        ),
        _watchlist_item(
            "2330", source="daily_market_research_bookmark", source_id="bookmark-2330-b",
            research_bookmark=record_b,
        ),
        _watchlist_item(
            "1101", source="daily_market_research_bookmark", source_id="bookmark-1101-a",
            research_bookmark=record_1101,
        ),
        _watchlist_item(
            "1101", source="daily_market_research_bookmark", source_id="bookmark-1101-other",
            research_bookmark=other_snapshot,
        ),
    ]
    return _WatchlistStub(items), _context("bookmark-2330-a", "2330")


def _select_bookmark(view: WatchlistView, bookmark_id: str) -> None:
    frame = view.stocks_model.getDataFrame()
    row_number = next(
        index
        for index, record in enumerate(frame["research_bookmark"])
        if isinstance(record, dict) and record.get("bookmark_id") == bookmark_id
    )
    view.stocks_table.selectRow(row_number)


def test_watchlist_frame_open_and_selector_keep_exact_bookmark_identity():
    _app()
    service, origin = _mixed_watchlist()
    view = WatchlistView(service)
    frame = view.stocks_model.getDataFrame()
    assert "research_bookmark" in frame.columns
    assert "每日研究收藏" in frame.columns
    assert "daily_market_research_bookmark" not in view.stocks_model.headerData(
        3, Qt.Orientation.Horizontal
    )

    assert view.research_bookmark_stock_codes(origin) == ("2330", "1101")
    target = view.research_bookmark_context_for_stock(origin, "1101")
    assert target is not None
    assert target.source_id == "bookmark-1101-a"
    assert target.source_snapshot_hash == origin.source_snapshot_hash
    assert target.daily_snapshot_condition_keys == origin.daily_snapshot_condition_keys
    assert view.research_bookmark_context_for_stock(origin, "9999") is None

    assert view.restore_research_bookmark_stock(origin)
    selected = view._selected_watchlist_row()
    assert selected is not None
    assert selected[0].get("research_bookmark")["bookmark_id"] == "bookmark-2330-a"
    wrong_bookmark = replace(origin, source_id="bookmark-does-not-exist")
    assert not view.restore_research_bookmark_stock(wrong_bookmark)

    opened: list[object] = []
    view.stockResearchRequested.connect(opened.append)
    _select_bookmark(view, "bookmark-2330-a")
    view._open_stock_analysis()
    assert len(opened) == 1
    assert opened[0] == origin
    view.close()


def test_group_helpers_strictly_reject_corrupt_candidate_before_switching():
    _app()
    service, origin = _mixed_watchlist()
    corrupt = _bookmark("bookmark-1101-corrupt", "1101", query_hash="query-a")
    service.stocks.append(
        _watchlist_item(
            "1101",
            source="daily_market_research_bookmark",
            source_id="bookmark-1101-corrupt",
            research_bookmark=corrupt,
        )
    )
    service.contexts["bookmark-1101-corrupt"] = _context(
        "bookmark-1101-corrupt", "1101", query_hash="query-a"
    )
    service.bad_bookmark_ids.add("bookmark-1101-corrupt")
    view = WatchlistView(service)

    assert view.research_bookmark_stock_codes(origin) == ("2330", "1101")
    target = view.research_bookmark_context_for_stock(origin, "1101")
    assert target is not None and target.source_id == "bookmark-1101-a"
    corrupt_context = service.contexts["bookmark-1101-corrupt"]
    assert not view.restore_research_bookmark_stock(corrupt_context)
    assert "bookmark-1101-corrupt" in service.context_calls
    view.close()


@pytest.mark.parametrize(
    "bad_payload,source",
    [({}, "manual"), ([], "manual"), ("bad", "manual"), (None, "daily_market_research_bookmark")],
)
def test_invalid_or_missing_bookmark_is_visible_and_never_falls_back_to_manual(
    bad_payload, source
):
    _app()
    item = _watchlist_item(
        "2330", source=source, source_id="unsupported-bookmark", research_bookmark=bad_payload
    )
    service = _WatchlistStub([item])
    service.bad_bookmark_ids.add("unsupported-bookmark")
    view = WatchlistView(service)
    label = view.stocks_model.getDataFrame().iloc[0]["每日研究收藏"]
    assert (
        "不可核驗" in label
        or "不完整" in label
        or "格式錯誤" in label
        or "不支援" in label
    )

    opened: list[object] = []
    view.stockResearchRequested.connect(opened.append)
    view.stocks_table.selectRow(0)
    view._open_stock_analysis()
    view._open_latest_source_research()
    assert opened == []
    view.close()


def test_latest_source_request_is_separate_and_preserves_bookmark_context():
    _app()
    service, origin = _mixed_watchlist()
    view = WatchlistView(service)
    requests: list[object] = []
    view.latestResearchRequested.connect(requests.append)
    _select_bookmark(view, "bookmark-2330-a")
    assert view._open_latest_source_research()
    assert len(requests) == 1
    assert requests[0] == origin
    assert requests[0].source_snapshot_hash == _HASH_A
    view.close()


def test_exact_bookmark_remove_cancel_remove_and_restore(monkeypatch):
    _app()
    service, _origin = _mixed_watchlist()
    view = WatchlistView(service)
    _select_bookmark(view, "bookmark-2330-a")
    question_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: question_calls.append(args[2])
        or QMessageBox.StandardButton.No,
    )
    view._remove_selected()
    assert question_calls and "精確研究書籤" in question_calls[0]
    assert service.remove_bookmark_calls == []
    assert service.remove_stocks_calls == []

    monkeypatch.setattr(
        QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)
    view._remove_selected()
    assert service.remove_bookmark_calls == ["bookmark-2330-a"]
    assert service.remove_stocks_calls == []
    assert view.restore_research_bookmark_btn.isEnabled()
    assert view._restore_last_research_bookmark()
    assert service.restore_calls == ["restore:bookmark-2330-a"]
    view.close()


def test_removing_same_code_legacy_row_uses_exact_item_api(monkeypatch):
    _app()
    service, _origin = _mixed_watchlist()
    view = WatchlistView(service)
    frame = view.stocks_model.getDataFrame()
    manual_row = next(
        index
        for index, row in frame.iterrows()
        if row["證券代號"] == "2330" and row["source"] == "manual"
    )
    view.stocks_table.selectRow(manual_row)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)
    view._remove_selected()
    assert service.remove_legacy_calls == [("2330", "", "manual")]
    assert service.remove_bookmark_calls == []
    assert service.remove_stocks_calls == []
    view.close()
