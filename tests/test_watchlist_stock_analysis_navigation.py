"""候選股下鑽使用畫面排序，且不依賴掃描榜 membership。"""
import os
from types import SimpleNamespace
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication
from ui_qt.views.watchlist_view import WatchlistView
from ui_qt.views.smart_money.smart_money_flow_view import SmartMoneyFlowView
from app_module.watchlist_analysis_service import WatchlistAnalysisService, WatchlistAnalysisDTO
from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation_repository import RecommendationRepository
from app_module.recommendation.contracts import ReferenceKind, VersionReference


class WatchlistStub:
    def query_stock_names(self, codes):
        return {"2330": "台積電", "1101": "台泥"}

    def get_stocks(self):
        return [
            {"stock_code": "2330", "stock_name": "台積電"},
            {"stock_code": "1101", "stock_name": "台泥"},
        ]


def test_sorted_watchlist_opens_selected_stock_and_empty_selection_does_not_emit():
    app = QApplication.instance() or QApplication([])
    view = WatchlistView(WatchlistStub())
    emitted = []
    view.stockAnalysisRequested.connect(emitted.append)
    view.stocks_model.sort(0, Qt.AscendingOrder)
    view.stocks_table.selectRow(0)
    view.stock_analysis_btn.click()
    assert emitted == ["1101"]
    view.stocks_table.clearSelection()
    view.stock_analysis_btn.click()
    assert emitted == ["1101"]
    view.close()


def test_unranked_stock_loads_detail_through_service(monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []

    class FlowStub:
        def load_stock_branch_detail(self, code, period, as_of):
            calls.append((code, period, as_of))

    view = SmartMoneyFlowView(FlowStub())
    view._data_loaded = True
    view._dashboard_as_of_date = date(2026, 9, 4)
    view._apply_scanner_signals([])
    monkeypatch.setattr(view, "_start_request", lambda kind, task, callback: task())
    view.select_stock("2330")
    assert calls[0][0] == "2330"
    assert calls[0][2] == date(2026, 9, 4)
    assert "2330" in view.sub_card_title.text()
    assert "未列入" in view.sub_card_stats.text()
    view.close()


def test_saved_analysis_reads_exact_source_and_rejects_future_without_writing(
    tmp_path, monkeypatch
):
    class OutputRootConfig:
        output_root = tmp_path

        @staticmethod
        def resolve_output_path(relative_path):
            return tmp_path / relative_path

    config = OutputRootConfig()
    result = RecommendationResultDTO(
        result_id="saved-1",
        result_name="策略甲",
        config={},
        run_context={"as_of_date": "2026-09-04"},
        recommendations=[
            RecommendationDTO(
                stock_code="2330",
                stock_name="台積電",
                close_price=Decimal("100"),
                price_change=0.0,
                total_score=75.0,
                indicator_score=25.0,
                pattern_score=25.0,
                volume_score=25.0,
                recommendation_reasons="均線向上",
                industry="半導體",
                regime_match=False,
            )
        ],
        screening_matrix_json=[
            {
                "stock_code": "1101",
                "status": "excluded",
                "reason_codes": ["liquidity_gate"],
            }
        ],
        created_at="2026-09-04T00:00:00",
    )
    RecommendationRepository(config).save_result(result)
    RecommendationRepository(config).save_result(
        RecommendationResultDTO(
            result_id="future-1",
            result_name="未來來源",
            config={},
            run_context={"as_of_date": "2026-09-08"},
            recommendations=[
                RecommendationDTO(
                    stock_code="2330",
                    stock_name="台積電",
                    close_price=Decimal("100"),
                    price_change=0.0,
                    total_score=75.0,
                    indicator_score=25.0,
                    pattern_score=25.0,
                    volume_score=25.0,
                    recommendation_reasons="未來來源測試",
                    industry="半導體",
                    regime_match=False,
                )
            ],
            created_at="2026-09-08T00:00:00",
        )
    )
    runs = tmp_path / "recommendation" / "runs"
    before = {p.name: p.read_bytes() for p in runs.iterdir()}
    service = WatchlistAnalysisService(
        config,
        clock=lambda: datetime(2026, 9, 6, tzinfo=ZoneInfo("Asia/Taipei")),
    )
    result = service.fetch("2330", "saved-1", date(2026, 9, 6))
    assert result.status == "saved"
    assert result.reasons == "均線向上"
    assert result.analysis_date == "2026-09-04"
    assert service.fetch("2330", "saved-1", date(2026, 9, 3)).status == "unavailable"
    assert service.fetch("1101", "saved-1", date(2026, 9, 6)).status == "not_in_result"
    same_stock_sources = service.list_saved_sources("2330", as_of_date=date(2026, 9, 6))
    assert [item["result_id"] for item in same_stock_sources] == ["saved-1"]
    assert [item["result_id"] for item in service.list_saved_sources("2330")] == ["saved-1"]
    assert [
        item["result_id"]
        for item in service.list_saved_sources("2330", as_of_date=date(2026, 9, 9))
    ] == ["future-1", "saved-1"]
    assert same_stock_sources[0]["membership_status"] == "saved"
    assert same_stock_sources[0]["decision_date"] == "2026-09-04"
    assert same_stock_sources[0]["data_date"] == ""
    assert same_stock_sources[0]["source_id"] == ""
    assert same_stock_sources[0]["source_snapshot_id"] == ""
    assert same_stock_sources[0]["source_snapshot_hash"] == ""
    assert service.list_saved_sources("1101", as_of_date=date(2026, 9, 3)) == []
    excluded_sources = service.list_saved_sources("1101", as_of_date=date(2026, 9, 6))
    assert [item["result_id"] for item in excluded_sources] == ["saved-1"]
    assert excluded_sources[0]["membership_status"] == "not_in_result"
    assert excluded_sources[0]["screening_reason"] == "liquidity_gate"
    assert excluded_sources[0]["decision_date"] == "2026-09-04"
    assert excluded_sources[0]["data_date"] == ""
    assert service.list_saved_sources("2880", as_of_date=date(2026, 9, 6)) == []
    assert {p.name: p.read_bytes() for p in runs.iterdir()} == before

    app = QApplication.instance() or QApplication([])
    class ExplicitSourceWatchlistStub(WatchlistStub):
        def get_stocks(self):
            return [
                {
                    "stock_code": "2330",
                    "stock_name": "台積電",
                    "source_id": "saved-1",
                }
            ]

    view = WatchlistView(ExplicitSourceWatchlistStub())
    view.analysis_service = service

    result_loop = QEventLoop(view)
    worker_outcomes = []

    # Capture the result/error signals before the worker starts. The view has
    # already connected its presentation callbacks by the time start() runs.
    from ui_qt.workers.task_worker import TaskWorker

    original_worker_start = TaskWorker.start

    def start_and_capture_worker(worker):
        worker.finished.connect(
            lambda result: (
                worker_outcomes.append(("finished", result)),
                result_loop.quit(),
            )
        )
        worker.error.connect(
            lambda error: (worker_outcomes.append(("error", error)), result_loop.quit())
        )
        worker.cancelled.connect(
            lambda: (worker_outcomes.append(("cancelled", None)), result_loop.quit())
        )
        original_worker_start(worker)

    monkeypatch.setattr(TaskWorker, "start", start_and_capture_worker)
    view.stocks_table.selectRow(0)
    if not worker_outcomes:
        timeout = QTimer(view)
        timeout.setSingleShot(True)
        timeout.timeout.connect(result_loop.quit)
        timeout.start(1_000)
        result_loop.exec()
        timeout.stop()
    assert len(worker_outcomes) == 1
    assert worker_outcomes[0][0] == "finished"
    assert worker_outcomes[0][1].status == "saved"
    assert "均線向上" in view.analysis_text.toPlainText()
    assert "2026-09-04" in view.analysis_text.toPlainText()
    view.close()


def test_explicit_same_stock_screening_source_is_bound_as_exclusion_and_survives_reopen(
    tmp_path, monkeypatch
):
    class OutputRootConfig:
        output_root = tmp_path

        @staticmethod
        def resolve_output_path(relative_path):
            return tmp_path / relative_path

    config = OutputRootConfig()
    result = RecommendationResultDTO(
        result_id="saved-1",
        result_name="策略甲",
        config={},
        run_context={"as_of_date": "2026-09-04", "data_date": "2026-09-03"},
        recommendations=[
            RecommendationDTO(
                stock_code="2330",
                stock_name="台積電",
                close_price=Decimal("100"),
                price_change=0.0,
                total_score=75.0,
                indicator_score=25.0,
                pattern_score=25.0,
                volume_score=25.0,
                recommendation_reasons="均線向上",
                industry="半導體",
                regime_match=False,
            )
        ],
        screening_matrix_json=[
            {
                "stock_code": "1101",
                "status": "excluded",
                "reason_codes": ["liquidity_gate"],
            }
        ],
        created_at="2026-09-04T00:00:00",
    )
    RecommendationRepository(config).save_result(result)
    analysis_service = WatchlistAnalysisService(config)
    from app_module.watchlist_service import WatchlistService

    watchlist_service = WatchlistService(config)
    watchlist_service.add_stocks([{"stock_code": "1101", "stock_name": "台泥"}])
    app = QApplication.instance() or QApplication([])
    view = WatchlistView(watchlist_service, config=config)
    view.analysis_service = analysis_service
    monkeypatch.setattr(view, "_request_stock_summary", lambda *_args: None)
    monkeypatch.setattr(view, "_load_watchlist", lambda: None)
    monkeypatch.setattr(view, "select_stock", lambda *_args: None)
    view.stocks_table.selectRow(0)
    app.processEvents()
    selected = view._selected_watchlist_row()
    assert selected is not None and selected[1] == "1101"

    options = view._saved_source_options("1101")
    assert [item["result_id"] for item in options] == ["saved-1"]
    assert options[0]["membership_status"] == "not_in_result"
    labels = []

    def choose_source(_parent, _title, _prompt, choices, _current, _editable):
        labels.extend(choices)
        return choices[0], True

    monkeypatch.setattr("ui_qt.views.watchlist_view.QInputDialog.getItem", choose_source)
    view._choose_recommendation_source()
    assert "同股明列未入選" in labels[0]

    reopened_service = WatchlistService(config)
    persisted_row = next(row for row in reopened_service.get_stocks() if row["stock_code"] == "1101")
    identity = persisted_row["decision_identity"]
    assert identity["result_id"] == "saved-1"
    assert identity["stock_code"] == "1101"
    assert identity["decision_date"] == "2026-09-04"
    context = view._build_stock_research_context(
        "1101",
        "台泥",
        decision_identity=identity,
    )
    assert context.result_id == "saved-1"
    assert context.decision_date == "2026-09-04"
    assert "明列未入選" in context.source_label
    assert "不代表看空" in context.source_label
    view.close()
    app.processEvents()


def test_source_binding_cancel_and_exact_identity_recheck_do_not_write(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])

    class BindingWatchlistStub(WatchlistStub):
        def __init__(self):
            self.bind_calls = []

        def bind_stock_decision_identity(self, *args, **kwargs):
            self.bind_calls.append((args, kwargs))
            return True

    for invalid_analysis in (
        WatchlistAnalysisDTO("1101", "saved", "2026-09-04", "saved-1"),
        WatchlistAnalysisDTO("2330", "saved", "2099-01-01", "saved-1"),
        WatchlistAnalysisDTO("2330", "saved", "2026-09-04", "different-run"),
    ):
        watchlist = BindingWatchlistStub()
        view = WatchlistView(watchlist)
        view.analysis_service = SimpleNamespace(
            list_saved_sources=lambda _code, **_kwargs: [
                {
                    "result_id": "saved-1",
                    "result_name": "策略甲",
                    "membership_status": "saved",
                    "decision_date": "2026-09-04",
                }
            ],
            fetch=lambda _code, _result_id, _cutoff: invalid_analysis,
        )
        monkeypatch.setattr(view, "_request_stock_summary", lambda *_args: None)
        monkeypatch.setattr(view, "_load_watchlist", lambda: None)
        monkeypatch.setattr(view, "select_stock", lambda *_args: None)
        view.stocks_table.selectRow(0)
        app.processEvents()
        monkeypatch.setattr(
            "ui_qt.views.watchlist_view.QInputDialog.getItem",
            lambda _parent, _title, _prompt, choices, _current, _editable: (choices[0], True),
        )
        view._choose_recommendation_source()
        assert watchlist.bind_calls == []
        view.close()

    watchlist = BindingWatchlistStub()
    view = WatchlistView(watchlist)
    fetch_calls = []
    view.analysis_service = SimpleNamespace(
        list_saved_sources=lambda _code, **_kwargs: [
            {
                "result_id": "saved-1",
                "result_name": "策略甲",
                "membership_status": "saved",
                "decision_date": "2026-09-04",
            }
        ],
        fetch=lambda *_args: fetch_calls.append(_args),
    )
    monkeypatch.setattr(view, "_request_stock_summary", lambda *_args: None)
    monkeypatch.setattr(view, "_load_watchlist", lambda: None)
    monkeypatch.setattr(view, "select_stock", lambda *_args: None)
    view.stocks_table.selectRow(0)
    app.processEvents()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.QInputDialog.getItem",
        lambda _parent, _title, _prompt, _choices, _current, _editable: ("", False),
    )
    view._choose_recommendation_source()
    assert not fetch_calls
    assert watchlist.bind_calls == []
    view.close()
    app.processEvents()


def test_source_binding_rejects_pinned_identity_changes_after_dialog(tmp_path, monkeypatch):
    from dataclasses import replace

    app = QApplication.instance() or QApplication([])
    base_analysis = WatchlistAnalysisDTO(
        "2330",
        "saved",
        "2026-09-04",
        "saved-1",
        decision_date="2026-09-04",
        data_date="2026-09-03",
        source_id="lineage-a",
        source_snapshot_id="snapshot-a",
        source_snapshot_hash="sha256:" + "a" * 64,
    )
    base_pins = {
        "membership_status": "saved",
        "decision_date": "2026-09-04",
        "data_date": "2026-09-03",
        "source_id": "lineage-a",
        "source_snapshot_id": "snapshot-a",
        "source_snapshot_hash": "sha256:" + "a" * 64,
    }
    cases = (
        (
            base_pins,
            replace(base_analysis, decision_date="2026-09-05"),
        ),
        (
            base_pins,
            replace(base_analysis, data_date="2026-09-02"),
        ),
        (
            base_pins,
            replace(base_analysis, source_id="lineage-b"),
        ),
        (
            base_pins,
            replace(base_analysis, source_snapshot_id="snapshot-b"),
        ),
        (
            base_pins,
            replace(base_analysis, source_snapshot_hash="sha256:" + "b" * 64),
        ),
        (
            {**base_pins, "data_date": ""},
            base_analysis,
        ),
        (
            {**base_pins, "source_snapshot_hash": ""},
            base_analysis,
        ),
    )
    for pins, refreshed_analysis in cases:
        watchlist = WatchlistStub()
        bind_calls = []
        watchlist.bind_stock_decision_identity = (
            lambda *args, **kwargs: bind_calls.append((args, kwargs)) or True
        )
        view = WatchlistView(watchlist)
        view.analysis_service = SimpleNamespace(
            list_saved_sources=lambda _code, **_kwargs: [
                {
                    "result_id": "saved-1",
                    "result_name": "策略甲",
                    **pins,
                }
            ],
            fetch=lambda *_args, result=refreshed_analysis: result,
        )
        monkeypatch.setattr(view, "_request_stock_summary", lambda *_args: None)
        monkeypatch.setattr(view, "_load_watchlist", lambda: None)
        monkeypatch.setattr(view, "select_stock", lambda *_args: None)
        view.stocks_table.selectRow(0)
        app.processEvents()
        monkeypatch.setattr(
            "ui_qt.views.watchlist_view.QInputDialog.getItem",
            lambda _parent, _title, _prompt, choices, _current, _editable: (
                choices[0],
                True,
            ),
        )

        view._choose_recommendation_source()

        assert bind_calls == []
        assert "未寫入來源" in view.status_label.text()
        view.close()
    app.processEvents()


def test_stale_analysis_callback_cannot_replace_current_stock():
    app = QApplication.instance() or QApplication([])
    view = WatchlistView(WatchlistStub())
    view._analysis_request_id = 2
    view.analysis_text.setPlainText("1101")
    view._show_selected_analysis(1, WatchlistAnalysisDTO("2330", "missing"))
    assert view.analysis_text.toPlainText() == "1101"
    view._show_selected_analysis(2, WatchlistAnalysisDTO("1101", "saved", "2026-09-04", "run", "75", "30", "均線向上"))
    assert "均線向上" in view.analysis_text.toPlainText()
    assert "2026-09-04" in view.analysis_text.toPlainText()
    view.close()


def test_saved_list_preview_does_not_modify_candidate_pool(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])

    class UniverseStub:
        def list_watchlists(self):
            return [{"name": "成長觀察", "count": 1, "watchlist_id": "growth"}]

        def load_watchlist(self, identifier):
            assert identifier == "growth"
            return SimpleNamespace(codes=["2330"])

    monkeypatch.setattr("ui_qt.views.watchlist_view.UniverseService", lambda config: UniverseStub())
    view = WatchlistView(WatchlistStub(), config=SimpleNamespace(output_root=tmp_path))
    emitted = []
    view.stockAnalysisRequested.connect(emitted.append)
    view.universe_list.setCurrentRow(0)
    assert view.universe_stock_list.count() == 1
    assert "台積電" in view.universe_stock_list.item(0).text()
    view.universe_stock_list.itemDoubleClicked.emit(view.universe_stock_list.item(0))
    assert emitted == ["2330"]
    assert view.stocks_model.rowCount() == 2
    view.close()


def test_initial_dashboard_completion_retains_requested_unranked_stock(monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []
    service = SimpleNamespace(load_stock_branch_detail=lambda code, period, cutoff: calls.append((code, cutoff)))
    view = SmartMoneyFlowView(service)
    monkeypatch.setattr(view, "load_data_if_needed", lambda: None)
    monkeypatch.setattr(view, "_start_request", lambda kind, task, callback: task())
    monkeypatch.setattr(view, "_on_branch_changed", lambda: None)
    monkeypatch.setattr(view.summary_strip, "update_summary", lambda summary: None)
    view.select_stock("2330")
    view._apply_dashboard_snapshot(SimpleNamespace(
        as_of_date=date(2026, 9, 4), top_signals=[], bottom_signals=[],
        summary=None, semantics_by_code={}, tracked_branches=[], quality="observed",
    ))
    assert calls[-1] == ("2330", date(2026, 9, 4))
    assert view.sub_card_title.text() == "2330"
    view.close()


def test_saved_source_data_date_must_not_exceed_query_cutoff(tmp_path):
    class OutputRootConfig:
        output_root = tmp_path

        @staticmethod
        def resolve_output_path(relative_path):
            return tmp_path / relative_path

    config = OutputRootConfig()
    result = RecommendationResultDTO(
        result_id="data-date-boundary",
        result_name="boundary fixture",
        config={},
        run_context={
            "as_of_date": "2026-09-08",
            "data_date": "2026-09-07",
        },
        recommendations=[
            RecommendationDTO(
                stock_code="1477",
                stock_name="fixture",
                close_price=Decimal("55"),
                price_change=0.0,
                total_score=70.0,
                indicator_score=70.0,
                pattern_score=70.0,
                volume_score=70.0,
                recommendation_reasons="fixture only",
                industry="fixture",
                regime_match=False,
            )
        ],
        created_at="2026-09-08T15:00:00+08:00",
    )
    RecommendationRepository(config).save_result(result)
    runs_root = tmp_path / "recommendation" / "runs"
    before = {path.name: path.read_bytes() for path in runs_root.iterdir()}
    service = WatchlistAnalysisService(
        config,
        clock=lambda: datetime(2026, 9, 10, 16, 0, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    historical = service.fetch("1477", result.result_id, date(2026, 9, 7))
    assert historical.status == "unavailable"
    assert "晚於查詢日期" in historical.message
    assert service.list_saved_sources("1477", as_of_date=date(2026, 9, 7)) == []

    same_day = service.fetch("1477", result.result_id, date(2026, 9, 8))
    assert same_day.status == "saved"
    assert same_day.decision_date == "2026-09-08"
    assert same_day.data_date == "2026-09-07"
    assert [item["result_id"] for item in service.list_saved_sources("1477")] == [
        result.result_id
    ]
    assert {path.name: path.read_bytes() for path in runs_root.iterdir()} == before



def test_saved_market_date_after_source_decision_stays_rejected_for_later_query(
    tmp_path,
):
    class OutputRootConfig:
        output_root = tmp_path

        @staticmethod
        def resolve_output_path(relative_path):
            return tmp_path / relative_path

    config = OutputRootConfig()
    result = RecommendationResultDTO(
        result_id="future-relative-to-decision",
        result_name="source date after decision",
        config={},
        run_context={
            "as_of_date": "2026-09-08",
            "data_date": "2026-09-09",
        },
        recommendations=[
            RecommendationDTO(
                stock_code="1477",
                stock_name="fixture",
                close_price=Decimal("55"),
                price_change=0.0,
                total_score=70.0,
                indicator_score=70.0,
                pattern_score=70.0,
                volume_score=70.0,
                recommendation_reasons="fixture only",
                industry="fixture",
                regime_match=False,
            )
        ],
        created_at="2026-09-08T15:00:00+08:00",
    )
    RecommendationRepository(config).save_result(result)
    runs_root = tmp_path / "recommendation" / "runs"
    before = {path.name: path.read_bytes() for path in runs_root.iterdir()}
    service = WatchlistAnalysisService(
        config,
        clock=lambda: datetime(2026, 9, 10, 16, 0, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    later_query = service.fetch("1477", result.result_id, date(2026, 9, 10))

    assert later_query.status == "unavailable"
    assert later_query.decision_date == "2026-09-08"
    assert later_query.data_date == "2026-09-09"
    assert "2026-09-09" in later_query.message
    assert "2026-09-08" in later_query.message
    assert service.list_saved_sources(
        "1477", as_of_date=date(2026, 9, 10)
    ) == []
    assert {path.name: path.read_bytes() for path in runs_root.iterdir()} == before


def _current_lineage_read_model(
    *,
    result_id="rec_current_lineage_fixture",
    data_date="2026-10-02",
    market_status="current",
    expected_market_date="2026-10-02",
    event_result_id=None,
    event_invocation_id=None,
    event_fingerprint=None,
    event_decision_at="2026-10-04T20:34:40.690639+00:00",
    event_cutoff_at="2026-10-04T20:34:37.209412+00:00",
    refs=None,
    duplicate_event=False,
    include_lineage=True,
):
    from types import SimpleNamespace

    from app_module.recommendation.contracts import ExecutionEvent, ExecutionStatus

    market_fingerprint = "a" * 64
    data_fingerprint = "b" * 64
    invocation_id = event_invocation_id or f"{result_id}:0123456789abcdef0123456789abcdef"
    decision_at = datetime.fromisoformat("2026-10-04T20:34:40.690639+00:00")
    details = {
        "schema_version": "recommendation-current-fundamental-lineage.v1",
        "result_id": event_result_id or result_id,
        "invocation_id": invocation_id,
        "scope": "natural_current_observation",
        "as_of_date": "2026-10-05",
        "data_date": data_date,
        "expected_market_date": expected_market_date,
        "market_calendar_status": market_status,
        "decision_at": event_decision_at,
        "current_observation_cutoff_at": event_cutoff_at,
        "source_id": "DefaultRecommendationMarketDataProvider",
        "market_data_fingerprint": event_fingerprint or market_fingerprint,
        "data_fingerprint": data_fingerprint,
    }
    events = (
        (ExecutionEvent(
            event_type="current_fundamental_lineage",
            message="fixture",
            occurred_at=decision_at,
            details=details,
        ),)
        if include_lineage
        else ()
    )
    if duplicate_event:
        events = (*events, *events)
    data_refs = refs if refs is not None else (
        VersionReference(
            kind=ReferenceKind.DATA_SNAPSHOT,
            reference_id=market_fingerprint,
            version=f"DefaultRecommendationMarketDataProvider:{data_date}",
        ),
    )
    context = SimpleNamespace(
        as_of_date=date(2026, 10, 5),
        decision_at=decision_at,
        created_at=decision_at,
        result_config_snapshot=None,
        profile_ref=None,
        source_refs=(),
        data_snapshot_refs=data_refs,
    )
    item = SimpleNamespace(
        stock_code="1477",
        rule_score=75,
        close_price=Decimal("55"),
        reason_text="fixture",
        reasons=(),
        eligible_universe_size=1,
        score_percentile_bp=None,
        ranking_method="",
    )
    execution = SimpleNamespace(
        result_id=result_id,
        status=ExecutionStatus.COMPLETED,
        decision=SimpleNamespace(items=(item,), assessments=()),
        context=context,
        events=events,
        ml_receipt_refs=(),
    )
    read_model = SimpleNamespace(
        result_id=result_id,
        legacy_result=None,
        execution=execution,
        ml_read_status="unavailable",
        ml_projection_rows=(),
        schema_revision=2,
        label="fixture",
        persisted_at=decision_at,
    )
    return read_model


def test_current_saved_source_projects_same_execution_quote_date(tmp_path):
    read_model = _current_lineage_read_model()

    class Queries:
        def get(self, result_id):
            return read_model if result_id == read_model.result_id else None

        def list(self):
            return (read_model,)

    config = SimpleNamespace(
        output_root=tmp_path,
        resolve_output_path=lambda relative_path: tmp_path / relative_path,
    )
    service = WatchlistAnalysisService(config, queries=Queries())

    analysis = service.fetch(
        "1477", read_model.result_id, date(2026, 10, 5)
    )
    options = service.list_saved_sources("1477", as_of_date=date(2026, 10, 5))

    assert analysis.status == "saved"
    assert analysis.decision_date == "2026-10-05"
    assert analysis.data_date == "2026-10-02"
    assert options[0]["result_id"] == read_model.result_id
    assert options[0]["decision_date"] == "2026-10-05"
    assert options[0]["data_date"] == "2026-10-02"

    wrong_stock = service.fetch(
        "2330", read_model.result_id, date(2026, 10, 5)
    )
    assert wrong_stock.status == "not_in_result"
    assert wrong_stock.data_date == ""


def test_stale_same_run_lineage_keeps_real_quote_date_without_requiring_current():
    read_model = _current_lineage_read_model(
        data_date="2026-10-01",
        expected_market_date="2026-10-02",
        market_status="stale",
        refs=(
            VersionReference(
                kind=ReferenceKind.DATA_SNAPSHOT,
                reference_id="a" * 64,
                version="DefaultRecommendationMarketDataProvider:2026-10-01",
            ),
        ),
    )

    class Queries:
        def get(self, result_id):
            return read_model

        def list(self):
            return (read_model,)

    config = SimpleNamespace(
        output_root=".",
        resolve_output_path=lambda relative_path: relative_path,
    )
    analysis = WatchlistAnalysisService(config, queries=Queries()).fetch(
        "1477", read_model.result_id, date(2026, 10, 5)
    )

    assert analysis.status == "saved"
    assert analysis.data_date == "2026-10-01"


@pytest.mark.parametrize(
    "changes",
    (
        {"event_result_id": "another-result"},
        {"event_invocation_id": "another-result:0123456789abcdef0123456789abcdef"},
        {"event_fingerprint": "c" * 64},
        {"data_date": "2026-10-06"},
        {"event_decision_at": "2026-10-04T19:34:40.690639+00:00"},
        {"duplicate_event": True},
        {"refs": ()},
        {
            "refs": (
                VersionReference(
                    kind=ReferenceKind.DATA_SNAPSHOT,
                    reference_id="a" * 64,
                    version="DefaultRecommendationMarketDataProvider:2026-10-02",
                ),
                VersionReference(
                    kind=ReferenceKind.DATA_SNAPSHOT,
                    reference_id="c" * 64,
                    version="OtherProvider:2026-10-02",
                ),
            )
        },
        {"market_status": "future_rejected"},
    ),
)
def test_current_saved_source_rejects_unbound_or_conflicting_lineage(changes, tmp_path):
    read_model = _current_lineage_read_model(**changes)

    class Queries:
        def get(self, result_id):
            return read_model

        def list(self):
            return (read_model,)

    config = SimpleNamespace(
        output_root=tmp_path,
        resolve_output_path=lambda relative_path: tmp_path / relative_path,
    )
    analysis = WatchlistAnalysisService(config, queries=Queries()).fetch(
        "1477", read_model.result_id, date(2026, 10, 5)
    )

    assert analysis.status == "saved"
    assert analysis.data_date == ""


def test_old_canonical_saved_source_without_lineage_keeps_data_date_unknown(tmp_path):
    read_model = _current_lineage_read_model(include_lineage=False)

    class Queries:
        def get(self, result_id):
            return read_model

        def list(self):
            return (read_model,)

    config = SimpleNamespace(
        output_root=tmp_path,
        resolve_output_path=lambda relative_path: tmp_path / relative_path,
    )
    analysis = WatchlistAnalysisService(config, queries=Queries()).fetch(
        "1477", read_model.result_id, date(2026, 10, 5)
    )

    assert analysis.status == "saved"
    assert analysis.data_date == ""


def _attach_market_data_provenance(
    read_model,
    *,
    scope="formal_pit",
    data_date="2026-10-02",
    decision_at=None,
    provenance_updates=None,
    event_updates=None,
    duplicate_invocation=False,
    lineage_data_date=None,
):
    from app_module.recommendation.contracts import ExecutionEvent

    execution = read_model.execution
    context = execution.context
    if scope == "formal_pit":
        context.decision_at = decision_at
        context.data_snapshot_refs = ()

    events = list(execution.events)
    lineage_events = [
        event for event in events
        if event.event_type == "current_fundamental_lineage"
    ]
    if lineage_data_date is not None:
        assert len(lineage_events) == 1
        original = lineage_events[0]
        lineage_details = dict(original.details)
        lineage_details["data_date"] = lineage_data_date
        lineage_details["market_calendar_status"] = "stale"
        lineage_details["expected_market_date"] = "2026-10-02"
        events[events.index(original)] = ExecutionEvent(
            event_type=original.event_type,
            message=original.message,
            occurred_at=original.occurred_at,
            details=lineage_details,
        )
        context.data_snapshot_refs = (
            VersionReference(
                kind=ReferenceKind.DATA_SNAPSHOT,
                reference_id="a" * 64,
                version=f"DefaultRecommendationMarketDataProvider:{lineage_data_date}",
            ),
        )
        lineage_events = [
            event for event in events
            if event.event_type == "current_fundamental_lineage"
        ]

    lineage_details = (
        lineage_events[0].details if lineage_events else {}
    )
    result_id = read_model.result_id
    invocation_id = str(
        lineage_details.get("invocation_id")
        or f"{result_id}:0123456789abcdef0123456789abcdef"
    )
    source_id = str(
        lineage_details.get("source_id")
        or "DefaultRecommendationMarketDataProvider"
    )
    market_fingerprint = str(lineage_details.get("market_data_fingerprint") or "a" * 64)
    if decision_at is None and scope == "natural_current_observation":
        decision_at = context.decision_at.isoformat()
    provenance = {
        "schema_version": "recommendation-market-data-provenance.v1",
        "result_id": result_id,
        "invocation_id": invocation_id,
        "scope": scope,
        "as_of_date": context.as_of_date.isoformat(),
        "data_date": data_date,
        "decision_at": decision_at,
        "source_id": source_id,
        "market_data_fingerprint": market_fingerprint,
    }
    if provenance_updates:
        provenance.update(provenance_updates)
    details = {
        "result_id": result_id,
        "invocation_id": invocation_id,
        "source_id": source_id,
        "market_data_fingerprint": market_fingerprint,
        "market_data_provenance": provenance,
    }
    if event_updates:
        details.update(event_updates)
    invocation_event = ExecutionEvent(
        event_type="legacy_invocation_context",
        message="fixture invocation provenance",
        # The event clock is deliberately absent: it is not quote availability.
        occurred_at=None,
        details=details,
    )
    events.append(invocation_event)
    if duplicate_invocation:
        events.append(invocation_event)
    execution.events = tuple(events)
    return read_model


def _service_for_read_model(tmp_path, read_model):
    class Queries:
        def get(self, result_id):
            return read_model if result_id == read_model.result_id else None

        def list(self):
            return (read_model,)

    config = SimpleNamespace(
        output_root=tmp_path,
        resolve_output_path=lambda relative_path: tmp_path / relative_path,
    )
    return WatchlistAnalysisService(config, queries=Queries())


def test_formal_market_provenance_projects_saved_quote_date_without_event_clock(
    tmp_path,
):
    read_model = _attach_market_data_provenance(
        _current_lineage_read_model(include_lineage=False),
        scope="formal_pit",
    )

    analysis = _service_for_read_model(tmp_path, read_model).fetch(
        "1477", read_model.result_id, date(2026, 10, 5)
    )

    assert analysis.status == "saved"
    assert analysis.decision_date == "2026-10-05"
    assert analysis.data_date == "2026-10-02"


def test_current_market_provenance_must_match_existing_lineage_proof(tmp_path):
    read_model = _attach_market_data_provenance(
        _current_lineage_read_model(),
        scope="natural_current_observation",
    )

    analysis = _service_for_read_model(tmp_path, read_model).fetch(
        "1477", read_model.result_id, date(2026, 10, 5)
    )

    assert analysis.status == "saved"
    assert analysis.data_date == "2026-10-02"


def test_current_market_provenance_preserves_dated_stale_observation(tmp_path):
    read_model = _attach_market_data_provenance(
        _current_lineage_read_model(
            data_date="2026-10-01",
            expected_market_date="2026-10-02",
            market_status="stale",
            refs=(
                VersionReference(
                    kind=ReferenceKind.DATA_SNAPSHOT,
                    reference_id="a" * 64,
                    version="DefaultRecommendationMarketDataProvider:2026-10-01",
                ),
            ),
        ),
        scope="natural_current_observation",
        data_date="2026-10-01",
    )

    analysis = _service_for_read_model(tmp_path, read_model).fetch(
        "1477", read_model.result_id, date(2026, 10, 5)
    )

    assert analysis.status == "saved"
    assert analysis.data_date == "2026-10-01"


@pytest.mark.parametrize(
    "provenance_updates,event_updates,decision_at,duplicate_invocation",
    (
        ({"result_id": "other-result"}, None, None, False),
        ({"invocation_id": "rec_formal:0123456789abcdef0123456789abcdef"}, None, None, False),
        (None, {"invocation_id": "other-result:0123456789abcdef0123456789abcdef"}, None, False),
        ({"as_of_date": "2026-10-04"}, None, None, False),
        ({"scope": []}, None, None, False),
        ({"data_date": "2026-10-06"}, None, None, False),
        ({"data_date": "2026/10/02"}, None, None, False),
        ({"decision_at": "2026-10-04T20:34:40+00:00"}, None, None, False),
        ({"source_id": "OtherProvider"}, None, None, False),
        ({"market_data_fingerprint": "A" * 64}, None, None, False),
        (None, {"market_data_fingerprint": "c" * 64}, None, False),
        (None, None, None, True),
    ),
)
def test_formal_market_provenance_rejects_wrong_identity_clock_or_date(
    tmp_path, provenance_updates, event_updates, decision_at, duplicate_invocation
):
    read_model = _attach_market_data_provenance(
        _current_lineage_read_model(include_lineage=False),
        scope="formal_pit",
        decision_at=decision_at,
        provenance_updates=provenance_updates,
        event_updates=event_updates,
        duplicate_invocation=duplicate_invocation,
    )

    analysis = _service_for_read_model(tmp_path, read_model).fetch(
        "1477", read_model.result_id, date(2026, 10, 5)
    )

    assert analysis.status == "saved"
    assert analysis.data_date == ""


def test_current_provenance_rejects_conflicting_lineage_and_wrong_clock(tmp_path):
    read_model = _attach_market_data_provenance(
        _current_lineage_read_model(
            data_date="2026-10-01",
            expected_market_date="2026-10-02",
            market_status="stale",
            refs=(
                VersionReference(
                    kind=ReferenceKind.DATA_SNAPSHOT,
                    reference_id="a" * 64,
                    version="DefaultRecommendationMarketDataProvider:2026-10-01",
                ),
            ),
        ),
        scope="natural_current_observation",
        lineage_data_date="2026-10-01",
        data_date="2026-10-02",
    )

    analysis = _service_for_read_model(tmp_path, read_model).fetch(
        "1477", read_model.result_id, date(2026, 10, 5)
    )
    assert analysis.status == "saved"
    assert analysis.data_date == ""

    wrong_clock = _attach_market_data_provenance(
        _current_lineage_read_model(),
        scope="natural_current_observation",
        provenance_updates={"decision_at": "2026-10-04T19:34:40.690639+00:00"},
    )
    wrong_clock_analysis = _service_for_read_model(tmp_path, wrong_clock).fetch(
        "1477", wrong_clock.result_id, date(2026, 10, 5)
    )
    assert wrong_clock_analysis.status == "saved"
    assert wrong_clock_analysis.data_date == ""


@pytest.mark.parametrize(
    "scope,include_lineage",
    (
        ("natural_current_observation", False),
        ("formal_pit", True),
    ),
)
def test_market_provenance_scope_must_match_lineage_lane(
    tmp_path, scope, include_lineage
):
    read_model = _attach_market_data_provenance(
        _current_lineage_read_model(include_lineage=include_lineage),
        scope=scope,
    )

    analysis = _service_for_read_model(tmp_path, read_model).fetch(
        "1477", read_model.result_id, date(2026, 10, 5)
    )

    assert analysis.status == "saved"
    assert analysis.data_date == ""


def test_formal_without_saved_quote_provenance_keeps_data_date_unknown(tmp_path):
    read_model = _current_lineage_read_model(include_lineage=False)
    read_model.execution.context.decision_at = None
    read_model.execution.events = ()

    analysis = _service_for_read_model(tmp_path, read_model).fetch(
        "1477", read_model.result_id, date(2026, 10, 5)
    )

    assert analysis.status == "saved"
    assert analysis.data_date == ""
