from __future__ import annotations

import threading
from types import SimpleNamespace

from test_ux04_05_daily_market_research_view import (
    _FakeScreener, _MANIFEST_ID, _MANIFEST_SHA, _app, _wait, _select_combo_data,
)
from app_module.daily_market_research_screener import DailyMarketResearchCancelled
from ui_qt.views.daily_market_research_view import DailyMarketResearchView


class LifecycleService(_FakeScreener):
    def __init__(self, *, failure=False, wait_for_cancel=False):
        super().__init__()
        self.lifecycle_calls = []
        self.failure = failure
        self.wait_for_cancel = wait_for_cancel
        self.entered = threading.Event()

    def read_membership_lifecycle(self, snapshot, keys, mode, *, cancel_callback):
        self.lifecycle_calls.append((snapshot.manifest_sha256, keys, mode))
        self.entered.set()
        if self.wait_for_cancel:
            while not cancel_callback():
                threading.Event().wait(0.002)
            raise DailyMarketResearchCancelled("cancelled")
        if self.failure:
            raise RuntimeError("history_manifest_invalid")
        return SimpleNamespace(
            current_manifest_sha256=_MANIFEST_SHA,
            current_manifest_identity_sha256=_MANIFEST_ID,
            condition_keys=tuple(sorted(keys)), combine_mode=mode,
            current_decision_date="2026-10-05", cohort_id="controlled-cohort",
            reason="完整相鄰觀測；未寫事件",
            rows=tuple(SimpleNamespace(
                stock_code=code, status=status, previous_date="2026-10-02",
                reason="完整相鄰比較", current_observation_id="c" * 64,
                previous_observation_id="d" * 64, source_identities=("pinned",),
            ) for code, status in (("2382", "reentered"), ("1477", "incomparable"))),
        )


def test_background_read_summary_selection_and_same_query_filter_cache():
    app = _app()
    service = LifecycleService()
    view = DailyMarketResearchView(service)
    view.on_first_open()
    _wait(view)
    assert len(service.lifecycle_calls) == 1
    assert view.results_table.columnCount() == 11
    assert view.results_table.horizontalHeader().visualIndex(10) == 5
    assert "正在" not in view.status_label.text()
    index = next(i for i in range(view.results_table.rowCount())
                 if view.results_table.item(i, 0).text() == "2382")
    assert "重新入選" in view.results_table.item(index, 10).text()
    view.results_table.selectRow(index)
    assert "前次 2026-10-02" in view.selected_summary_label.text()
    assert "重新入選 1" in view.candidate_summary_label.text()
    _select_combo_data(view.filter_state_combo, "unknown")
    _wait(view)
    assert len(service.lifecycle_calls) == 1
    _select_combo_data(view.combine_mode_combo, "OR")
    _wait(view)
    assert len(service.lifecycle_calls) == 2
    assert service.produce_calls == []
    view.close()
    app.processEvents()


def test_stale_query_and_wrong_identity_cannot_install_result():
    app = _app()
    service = LifecycleService()
    view = DailyMarketResearchView(service)
    view.on_first_open()
    _wait(view)
    original = view._lifecycle_result
    view._accept_membership_read({"query_key": ("e" * 64, (), "OR"), "lifecycle": original})
    assert view._lifecycle_result is original
    bad = SimpleNamespace(current_manifest_sha256="e" * 64,
                          current_manifest_identity_sha256=_MANIFEST_ID)
    view._accept_membership_read({"query_key": view._membership_query_key(), "lifecycle": bad})
    assert view._lifecycle_result is None
    assert "身份不符" in view.candidate_summary_label.text()
    wrong_query = SimpleNamespace(**vars(original))
    wrong_query.combine_mode = "OR"
    view._accept_membership_read({"query_key": view._membership_query_key(), "lifecycle": wrong_query})
    assert view._lifecycle_result is None
    assert "身份不符" in view.candidate_summary_label.text()
    view._lifecycle_pending = False
    view.close()
    app.processEvents()


def test_history_failure_preserves_pinned_current_snapshot():
    app = _app()
    service = LifecycleService(failure=True)
    view = DailyMarketResearchView(service)
    view.on_first_open()
    _wait(view)
    assert view._snapshot is service.snapshot
    assert view.results_table.rowCount() == 2
    assert "保持未知" in view.candidate_summary_label.text()
    assert "history_manifest_invalid" in view.candidate_summary_label.text()
    view.close()
    app.processEvents()


def test_cooperative_cancel_preserves_snapshot_and_does_not_retry_loop():
    app = _app()
    service = LifecycleService(wait_for_cancel=True)
    view = DailyMarketResearchView(service)
    view.on_first_open()
    deadline = __import__("time").monotonic() + 2.5
    while not service.entered.is_set() and __import__("time").monotonic() < deadline:
        app.processEvents()
    assert service.entered.is_set()
    view.cancel_active_operation()
    _wait(view)
    assert view._snapshot is service.snapshot
    assert view._lifecycle_result is None
    assert "已取消" in view.candidate_summary_label.text()
    assert len(service.lifecycle_calls) == 1
    view.close()
    app.processEvents()
