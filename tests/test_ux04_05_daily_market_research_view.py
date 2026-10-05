from __future__ import annotations

from datetime import datetime
import os
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtTest import QTest

from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_dtos import StockResearchReportDTO
from ui_qt.views.daily_market_research_view import DailyMarketResearchView
from ui_qt.views.recommendation_view import _CurrentPageSizeTabWidget
from ui_qt.views.stock_research_report_view import (
    StockResearchReportView,
    _read_report_with_context_cutoff,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_MANIFEST_SHA = "b" * 64
_MANIFEST_ID = "a" * 64


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _snapshot() -> SimpleNamespace:
    return SimpleNamespace(
        manifest={
            "cohort_id": "controlled-cohort",
            "decision_date": "2026-10-05",
            "decision_cutoff": "2026-10-05T10:30:00+08:00",
            "completeness": "complete_declared_cohort",
            "declared_stock_codes": ["1477", "2382"],
        },
        manifest_sha256=_MANIFEST_SHA,
        manifest_identity_sha256=_MANIFEST_ID,
        stock_snapshots={"1477": {}, "2382": {}},
    )


def _condition(key: str, state: str, relation: str, reason: str = "") -> SimpleNamespace:
    return SimpleNamespace(key=key, state=state, relation=relation, reason=reason)


class _FakeScreener:
    def __init__(self, *, source_error: bool = False) -> None:
        self.snapshot = _snapshot()
        self.source_error = source_error
        self.calls: list[tuple[object, ...]] = []
        self.produce_calls: list[tuple[object, ...]] = []

    def read_latest(self, cohort_id: str, *, cancel_callback=None):
        self.calls.append(("read_latest", cohort_id))
        if cancel_callback and cancel_callback():
            raise RuntimeError("cancelled")
        if self.source_error:
            raise RuntimeError("snapshot_input_hash_mismatch")
        return self.snapshot

    def read_snapshot(
        self,
        cohort_id: str,
        decision_date,
        *,
        manifest_sha256=None,
        cancel_callback=None,
    ):
        self.calls.append(("read_snapshot", cohort_id, decision_date, manifest_sha256))
        if cancel_callback and cancel_callback():
            raise RuntimeError("cancelled")
        if self.source_error:
            raise RuntimeError("snapshot_input_hash_mismatch")
        return self.snapshot

    def produce_snapshot(
        self,
        stock_codes,
        decision_cutoff: datetime,
        cohort_id: str,
        *,
        cancel_callback=None,
    ):
        self.produce_calls.append((tuple(stock_codes), decision_cutoff, cohort_id))
        return SimpleNamespace(
            status="published_complete",
            manifest_sha256=_MANIFEST_SHA,
            reused_stock_codes=("1477",),
            recomputed_stock_codes=("2382",),
        )

    def filter_rows(self, _snapshot, condition_keys, combine_mode):
        self.calls.append(("filter", tuple(condition_keys), combine_mode))
        left = _condition("close_above_ma20", "match", "above", "收盤高於 MA20")
        right = _condition("close_above_ma60", "no_match", "below", "收盤低於 MA60")
        unknown20 = _condition(
            "close_above_ma20", "unknown", "unknown", "insufficient_valid_ohlc_streak"
        )
        unknown60 = _condition("close_above_ma60", "unknown", "unknown", "technical_missing")
        states = (
            ("2382", (left, right), "match" if combine_mode == "OR" else "no_match"),
            ("1477", (unknown20, unknown60), "unknown"),
        )
        rows = []
        for code, conditions, combined in states:
            selected_conditions = tuple(
                condition for condition in conditions if condition.key in condition_keys
            )
            rows.append(
                SimpleNamespace(
                    stock_code=code,
                    cohort_id="controlled-cohort",
                    decision_date="2026-10-05",
                    data_date="2026-10-02",
                    condition_keys=tuple(condition_keys),
                    combine_mode=combine_mode,
                    conditions=selected_conditions,
                    combined_state=combined,
                    why=("收盤高於 MA20",) if combined == "match" else (),
                    why_not=("收盤低於 MA60",) if combined != "match" else (),
                    source_snapshot_id=_MANIFEST_ID,
                    source_snapshot_hash=_MANIFEST_SHA,
                    snapshot_identity_sha256=f"{code:0>64}",
                    input_fingerprint_sha256="c" * 64,
                    research_scope_label="明示研究 cohort；非全市場／非正式推薦",
                )
            )
        return tuple(rows)

    def context_for_stock(self, row, *, stock_name=""):
        return ResearchStockContextDTO(
            stock_code=row.stock_code,
            stock_name=stock_name,
            decision_date=row.decision_date,
            data_date=row.data_date,
            source_kind="daily_market_research_snapshot",
            source_workspace="recommendation",
            source_snapshot_id=row.source_snapshot_id,
            source_snapshot_hash=row.source_snapshot_hash,
            daily_snapshot_root="C:/qa/daily-market",
            daily_snapshot_cohort_id=row.cohort_id,
            daily_snapshot_condition_keys=",".join(row.condition_keys),
            daily_snapshot_combine_mode=row.combine_mode,
        )


def _wait(view: DailyMarketResearchView, timeout_ms: int = 2500) -> None:
    app = _app()
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        if view._worker is None:
            return
        QTest.qWait(5)
    assert view._worker is None


def _select_combo_data(combo, value: str) -> None:
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


def test_first_open_is_read_only_unknown_stays_visible_and_drilldown_is_pinned() -> None:
    app = _app()
    service = _FakeScreener()
    view = DailyMarketResearchView(service)
    emitted: list[ResearchStockContextDTO] = []
    view.stockResearchRequested.connect(emitted.append)

    view.on_first_open()
    _wait(view)
    assert service.produce_calls == []
    assert service.calls[0] == ("read_latest", "daily-market-research")
    assert view.results_table.rowCount() == 2
    assert "符合 0" in view.summary_label.text()  # default AND has one explicit no-match and one unknown
    assert "未知 1" in view.summary_label.text()

    _select_combo_data(view.combine_mode_combo, "OR")
    app.processEvents()
    assert "符合 1" in view.summary_label.text()
    assert "未知 1" in view.summary_label.text()
    _select_combo_data(view.filter_state_combo, "unknown")
    app.processEvents()
    assert view.results_table.rowCount() == 1
    assert view.results_table.item(0, 0).text() == "1477"
    assert "insufficient_valid_ohlc_streak" in view.results_table.item(0, 5).text()

    _select_combo_data(view.filter_state_combo, "all")
    app.processEvents()
    row_number = next(
        index
        for index in range(view.results_table.rowCount())
        if view.results_table.item(index, 0).text() == "2382"
    )
    view.results_table.selectRow(row_number)
    assert view.open_selected_stock()
    assert len(emitted) == 1
    context = emitted[0]
    assert context.source_kind == "daily_market_research_snapshot"
    assert context.source_snapshot_hash == _MANIFEST_SHA
    assert context.source_snapshot_id == _MANIFEST_ID
    assert context.daily_snapshot_condition_keys == "close_above_ma20,close_above_ma60"
    assert context.daily_snapshot_combine_mode == "OR"
    assert context.decision_date == "2026-10-05"
    assert context.data_date == "2026-10-02"
    assert set(view.research_snapshot_stock_codes()) == {"1477", "2382"}
    assert view.restore_research_snapshot_stock("2382", _MANIFEST_SHA)
    assert not view.restore_research_snapshot_stock("2382", "d" * 64)
    view.close()
    app.processEvents()


def test_explicit_update_is_only_producer_path_and_failed_readback_clears_stale_rows() -> None:
    app = _app()
    service = _FakeScreener()
    view = DailyMarketResearchView(service)
    view.on_first_open()
    _wait(view)
    assert service.produce_calls == []

    view.start_snapshot_update()
    _wait(view)
    assert len(service.produce_calls) == 1
    codes, cutoff, cohort_id = service.produce_calls[0]
    assert codes == ("2382", "1477")
    assert cohort_id == "daily-market-research"
    assert cutoff.tzinfo is not None and cutoff.tzinfo.utcoffset(cutoff).total_seconds() == 8 * 3600
    assert (
        "read_snapshot",
        cohort_id,
        cutoff.date(),
        _MANIFEST_SHA,
    ) in service.calls
    assert view.results_table.rowCount() == 2

    service.source_error = True
    view.reload_published_snapshot()
    _wait(view)
    assert len(service.produce_calls) == 1
    assert view.results_table.rowCount() == 0
    assert "未知" in view.status_label.text()
    view.close()
    app.processEvents()


def test_stock_report_keeps_pinned_date_and_displays_backend_combined_evaluation() -> None:
    app = _app()
    context = ResearchStockContextDTO(
        stock_code="2382",
        decision_date="2026-10-05",
        data_date="2026-10-02",
        source_kind="daily_market_research_snapshot",
        source_workspace="recommendation",
        source_snapshot_id=_MANIFEST_ID,
        source_snapshot_hash=_MANIFEST_SHA,
        ml_scope_mode="current_stock_research",
        daily_snapshot_root="C:/qa/daily-market",
        daily_snapshot_cohort_id="controlled-cohort",
        daily_snapshot_condition_keys="close_above_ma20,close_above_ma60",
        daily_snapshot_combine_mode="OR",
    )

    class ReadService:
        def __init__(self) -> None:
            self.as_of_date = None

        def read_report(self, stock_code, *, context=None, cancel_callback=None, as_of_date=None):
            del context, cancel_callback
            self.as_of_date = as_of_date
            return StockResearchReportDTO(stock_code=stock_code)

    service = ReadService()
    _read_report_with_context_cutoff(service, "2382", context=context)
    assert service.as_of_date == "2026-10-05"

    report = StockResearchReportDTO(
        stock_code="2382",
        as_of="2026-10-05",
        shared_daily_features={
            "readback": {
                "mode": "verified_pinned_daily_market_research_snapshot",
                "manifest_sha256": _MANIFEST_SHA,
                "manifest_identity_sha256": _MANIFEST_ID,
                "cohort_id": "controlled-cohort",
                "stock_code": "2382",
                "data_date": "2026-10-02",
                "filter_evaluation": {
                    "condition_keys": ["close_above_ma20", "close_above_ma60"],
                    "combine_mode": "OR",
                    "combined_state": "match",
                    "conditions": [
                        {"key": "close_above_ma20", "state": "match", "relation": "above", "reason": ""},
                        {"key": "close_above_ma60", "state": "no_match", "relation": "below", "reason": ""},
                    ],
                    "why": ["close_above_ma20:above"],
                    "why_not": ["close_above_ma60:below"],
                },
            }
        },
    )
    view = StockResearchReportView(SimpleNamespace())
    view.context = context
    view._request_id = 1
    view._active_code = "2382"
    view._on_report_loaded(1, "2382", report, context=context)
    label = view.daily_market_research_condition_label
    assert not label.isHidden()
    assert "符合" in label.text()
    assert "資料日：2026-10-02" in label.text()
    assert "不符合／未知原因" in label.text()
    assert "研究條件已核驗" in view.status_label.text()
    view.close()
    app.processEvents()


def test_result_tabs_size_to_active_page_and_preserve_saved_page_size() -> None:
    app = _app()

    class SizedPage(QWidget):
        def __init__(self, width: int, height: int) -> None:
            super().__init__()
            self._size = QSize(width, height)

        def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
            return self._size

        def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
            return self._size

    tabs = _CurrentPageSizeTabWidget()
    saved_page = SizedPage(500, 2100)
    daily_page = SizedPage(617, 646)
    tabs.addTab(saved_page, "saved")
    tabs.addTab(daily_page, "daily")
    saved_minimum = tabs.minimumSizeHint().height()
    tabs.setCurrentWidget(daily_page)
    app.processEvents()
    daily_minimum = tabs.minimumSizeHint().height()

    assert saved_minimum > 2000
    assert 646 <= daily_minimum < 800
    tabs.setCurrentWidget(saved_page)
    app.processEvents()
    assert tabs.minimumSizeHint().height() == saved_minimum
    tabs.close()
