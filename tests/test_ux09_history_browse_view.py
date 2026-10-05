from __future__ import annotations

import threading
from types import SimpleNamespace

from test_ux09_membership_lifecycle_view import LifecycleService
from test_ux04_05_daily_market_research_view import _app, _wait, _MANIFEST_ID, _MANIFEST_SHA
from app_module.daily_market_research_screener import DailyMarketResearchCancelled
from ui_qt.views.daily_market_research_view import DailyMarketResearchView


class BrowseService(LifecycleService):
    def __init__(self, *, page_failure=False, block=False):
        super().__init__()
        self.page_calls = []
        self.build_calls = 0
        self.page_failure = page_failure
        self.block = block
        self.page_entered = threading.Event()

    def read_membership_history_page(self, snapshot, **query):
        self.page_calls.append(query)
        self.page_entered.set()
        if self.block:
            while not query["cancel_callback"]():
                threading.Event().wait(0.002)
            raise DailyMarketResearchCancelled("cancelled")
        if self.page_failure:
            raise ValueError("source_changed")
        number = int(query["cursor"] or 0)
        return SimpleNamespace(
            current_manifest_sha256=_MANIFEST_SHA, current_manifest_identity_sha256=_MANIFEST_ID,
            cohort_id="controlled-cohort", condition_keys=tuple(sorted(query["condition_keys"])),
            combine_mode=query["combine_mode"], stock_code=query["stock_code"],
            generation_id="g" * 64, source_fingerprint="s" * 64,
            has_more=number < 80, next_cursor=str(number + 1) if number < 80 else None,
            rows=(SimpleNamespace(decision_date=f"fixture-page-{number}", stock_code=query["stock_code"],
                                  state="match", reason="受控觀測", published_at="2026-10-05T16:00:00+08:00",
                                  cutoff_at="2026-10-05T15:00:00+08:00", manifest_sha256="a" * 64,
                                  manifest_identity_sha256="b" * 64, artifact_sha256="c" * 64),),
        )

    def rebuild_membership_history_index(self, *, cancel_callback):
        self.build_calls += 1
        return SimpleNamespace(activated=True, generation_id="g" * 64)


def _view(service):
    app = _app()
    view = DailyMarketResearchView(service)
    view.on_first_open()
    _wait(view)
    view.results_table.selectRow(0)
    app.processEvents()
    return app, view


def test_history_background_navigation_does_not_replace_current_source():
    service = BrowseService()
    app, view = _view(service)
    original = view._snapshot
    assert service.build_calls == 0
    view._request_history_page(reset=True)
    _wait(view)
    assert view.history_table.rowCount() == 1
    assert view.history_table.item(0, 0).text() == "fixture-page-0"
    assert "manifest=" in view.history_table.item(0, 0).toolTip()
    view._request_history_page(step=1)
    _wait(view)
    assert view.history_table.item(0, 0).text() == "fixture-page-1"
    view._request_history_page(step=-1)
    _wait(view)
    assert view.history_table.item(0, 0).text() == "fixture-page-0"
    assert view._snapshot is original
    assert service.produce_calls == [] and service.build_calls == 0
    assert "正在" not in view.status_label.text()
    view.close()
    app.processEvents()


def test_navigation_window_is_bounded_and_does_not_truncate_long_history():
    service = BrowseService()
    app, view = _view(service)
    view._request_history_page(reset=True)
    _wait(view)
    for _ in range(67):
        view._request_history_page(step=1)
        _wait(view)
    assert len(view._history_cursors) == 64
    assert view._history_base_position == 4
    assert view._history_position == 63
    assert view.history_table.item(0, 0).text() == "fixture-page-67"
    assert "第 68 頁" in view.history_status_label.text()
    assert view.history_table.rowCount() == 1
    view._request_history_page(step=-1)
    _wait(view)
    assert view.history_table.item(0, 0).text() == "fixture-page-66"
    view._request_history_page(reset=True)
    _wait(view)
    assert view._history_base_position == 0
    assert len(view._history_cursors) == 1
    view.close()
    app.processEvents()


def test_history_stale_generation_query_and_wrong_pin_are_rejected():
    service = BrowseService()
    app, view = _view(service)
    view._request_history_page(reset=True)
    _wait(view)
    original = view._history_page
    view._on_operation_finished(view._operation_generation - 1, "membership_history_page", {})
    assert view._history_page is original
    view._accept_history_operation("membership_history_page", {"query_key": ("stale",), "page": None})
    assert view._history_page is original
    bad = SimpleNamespace(**vars(original))
    bad.current_manifest_sha256 = "e" * 64
    view._accept_history_operation("membership_history_page", {"query_key": view._history_query_key(), "page": bad})
    assert view._history_page is None
    assert "身份不符" in view.history_status_label.text()
    assert view._snapshot is service.snapshot
    view.close()
    app.processEvents()


def test_index_rebuild_is_explicit_and_refreshes_only_lifecycle():
    service = BrowseService()
    app, view = _view(service)
    assert service.build_calls == 0
    before_calls = len(service.lifecycle_calls)
    view._request_history_rebuild()
    _wait(view)
    assert service.build_calls == 1
    assert len(service.lifecycle_calls) == before_calls + 1
    assert view._snapshot is service.snapshot
    assert service.produce_calls == []
    view.close()
    app.processEvents()


def test_history_failure_preserves_current_and_does_not_rebuild():
    service = BrowseService(page_failure=True)
    app, view = _view(service)
    view._request_history_page(reset=True)
    _wait(view)
    assert "source_changed" in view.history_status_label.text()
    assert view._snapshot is service.snapshot
    assert view._history_page is None
    assert service.build_calls == 0
    view.close()
    app.processEvents()


def test_history_cancel_preserves_current_and_stops_without_retry():
    service = BrowseService(block=True)
    app, view = _view(service)
    view._request_history_page(reset=True)
    deadline = __import__("time").monotonic() + 2
    while not service.page_entered.is_set() and __import__("time").monotonic() < deadline:
        app.processEvents()
    assert service.page_entered.is_set()
    app.processEvents()
    assert view.open_selected_stock_button.isEnabled()
    assert view.ma20_checkbox.isEnabled() and view.filter_state_combo.isEnabled()
    assert not view.history_browse_button.isEnabled()
    view.cancel_active_operation()
    _wait(view)
    assert view._snapshot is service.snapshot
    assert "已取消" in view.history_status_label.text()
    assert len(service.page_calls) == 1 and service.build_calls == 0
    view.close()
    app.processEvents()


def test_rebuild_without_activated_receipt_cannot_report_completion():
    service = BrowseService()
    app, view = _view(service)
    calls = len(service.lifecycle_calls)
    view._accept_history_operation("membership_history_rebuild", {"query_key": view._membership_query_key(), "build": SimpleNamespace(activated=False)})
    assert "沒有完整啟用收據" in view._history_message
    assert len(service.lifecycle_calls) == calls
    assert view._snapshot is service.snapshot
    view.close()
    app.processEvents()
