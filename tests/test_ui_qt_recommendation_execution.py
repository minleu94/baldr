from __future__ import annotations

from datetime import date, datetime, timezone
from dataclasses import replace
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.recommendation.contracts import (
    Context,
    DecisionBatch,
    ExecutionEvent,
    ExecutionStatus,
    IndexStatus,
    RecommendationExecution,
    Request,
    SaveReceipt,
)
from app_module.recommendation.persistence import PartialExecutionPersistenceError
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.recommendation.contracts import ReferenceKind, VersionReference
from decision_module.recommendation.contracts import RecommendationItem
from decision_module.recommendation.contracts import (
    CandidateAssessment,
    FilterOutcome,
)
from ui_qt.models.pandas_table_model import PandasTableModel
from ui_qt.views import recommendation_view as view_module
from ui_qt.views.recommendation.execution_coordinator import RecommendationExecutionRequest
from ui_qt.views.recommendation_view import RecommendationView


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    yield application


def _execution(
    result_id: str,
    *,
    stock_code: str = "2330",
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    empty: bool = False,
) -> RecommendationExecution:
    config = {
        "patterns": {"selected": ["W底"]},
        "signals": {"technical_indicators": ["trend"]},
        "filters": {"price_change_min": "1.25"},
        "profile_id": "momentum",
        "profile_version": "2.1",
        "regime": "Trend",
    }
    snapshot = RecommendationExecutionRequest(config).config_snapshot
    request = Request(
        config_snapshot=snapshot,
        profile_ref=VersionReference(ReferenceKind.PROFILE, "momentum", "2.1"),
        max_stocks=200,
        top_n=50,
    )
    item = RecommendationItem(
        stock_code=stock_code,
        stock_name="台積電" if stock_code == "2330" else f"name-{stock_code}",
        close_price=900,
        price_change=15,
        rule_score=85,
        indicator_score=80,
        pattern_score=90,
        volume_score=85,
        reason_text="量能放大；均線多頭",
        industry="半導體",
        regime_match=True,
        rank=1,
    )
    return RecommendationExecution(
        result_id=result_id,
        request=request,
        context=Context(
            as_of_date=date(2026, 9, 23),
            created_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
            available_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
            decision_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
        ),
        status=status,
        decision=(
            DecisionBatch(items=() if empty else (item,), regime="Trend")
            if status is ExecutionStatus.COMPLETED
            else None
        ),
        failure_reason=None if status is ExecutionStatus.COMPLETED else "cancelled by test",
    )


def _screening_only_execution(result_id: str) -> RecommendationExecution:
    from app_module.recommendation.negative_evidence_projection import (
        project_canonical_negative_evidence,
    )

    rows = (
        {
            "stock_code": "1477",
            "stock_name": "聚陽",
            "status": "fail",
            "reason_codes": ("liquidity_below_minimum",),
            "quality": "observed",
            "stage": "liquidity_gate",
            "threshold_name": "average_dollar_volume_minimum",
            "observed_value": "120000",
            "required_value": "500000",
            "total_score": "",
            "score_bp": None,
            "score_percentile_bp": None,
            "eligible_universe_size": None,
            "threshold_mode": "fixed",
            "warnings": (),
            "industry": "紡織",
            "as_of_date": "2026-09-23",
            "data_fingerprint": "sha256:" + "a" * 64,
        },
        {
            "stock_code": "1101",
            "stock_name": "台泥",
            "status": "fail",
            "reason_codes": ("liquidity_below_minimum",),
            "quality": "observed",
            "stage": "liquidity_gate",
            "threshold_name": "average_dollar_volume_minimum",
            "observed_value": "95000",
            "required_value": "500000",
            "total_score": "",
            "score_bp": None,
            "score_percentile_bp": None,
            "eligible_universe_size": None,
            "threshold_mode": "fixed",
            "warnings": (),
            "industry": "水泥",
            "as_of_date": "2026-09-23",
            "data_fingerprint": "sha256:" + "b" * 64,
        },
    )
    assessments = tuple(
        CandidateAssessment(
            stock_code=str(row["stock_code"]),
            eligible=False,
            filter_outcomes={
                f"legacy:{row['stage']}": FilterOutcome(
                    filter_id=f"legacy:{row['stage']}",
                    passed=False,
                    reason=str(row["reason_codes"][0]),
                    evidence=row,
                )
            },
        )
        for row in rows
    )
    decision = DecisionBatch(items=(), assessments=assessments, regime="Trend")
    negative_evidence = project_canonical_negative_evidence(decision)
    execution = _execution(result_id, empty=True)
    return replace(
        execution,
        decision=decision,
        events=(
            ExecutionEvent(
                event_type="legacy_negative_evidence_capture",
                message="封存同次 typed 篩選列。",
                details=negative_evidence.as_event_details(),
            ),
        ),
    )


def _official_delisted_screening_execution(result_id: str) -> RecommendationExecution:
    from app_module.recommendation.negative_evidence_projection import (
        project_canonical_negative_evidence,
    )

    row = {
        "stock_code": "1477",
        "stock_name": "聚陽",
        "status": "fail",
        "reason_codes": ("official_delisted",),
        "quality": "observed",
        "stage": "current_market_status_gate",
        "threshold_name": "listing_status",
        "observed_value": "delisted",
        "required_value": "listed",
        "total_score": "",
        "score_bp": None,
        "score_percentile_bp": None,
        "eligible_universe_size": None,
        "threshold_mode": "fixed",
        "warnings": (),
        "industry": "紡織",
        "as_of_date": "2026-09-23",
        "data_fingerprint": "sha256:" + "c" * 64,
    }
    assessment = CandidateAssessment(
        stock_code="1477",
        eligible=False,
        filter_outcomes={
            "legacy:current_market_status_gate": FilterOutcome(
                filter_id="legacy:current_market_status_gate",
                passed=False,
                reason="official_delisted",
                evidence=row,
            )
        },
    )
    decision = DecisionBatch(items=(), assessments=(assessment,), regime="Trend")
    projection = project_canonical_negative_evidence(decision)
    execution = _execution(result_id, empty=True)
    return replace(
        execution,
        decision=decision,
        events=(
            ExecutionEvent(
                event_type="legacy_negative_evidence_capture",
                message="封存同次 typed 篩選列。",
                details=projection.as_event_details(),
            ),
        ),
    )


def test_ux02_completed_research_keeps_ml_limit_separate(qt_app, monkeypatch):
    execution = _execution("ux02-current-research")
    view = _view_with_execution(qt_app, execution)
    view._execution_generation = 1
    monkeypatch.setattr(view_module.QMessageBox, "information", lambda *_args: None)
    view._on_recommendation_finished(execution, generation=1)
    assert "研究完成" in view.result_status_label.text()
    assert "ML來源：" in view.result_status_label.text()
    assert "找到" in view.result_status_label.text()
    assert "原始狀態" in view.result_status_label.toolTip()
    assert view.current_execution is execution
    view.close()


def test_screening_rows_require_completed_typed_same_run_evidence():
    execution = _screening_only_execution("rec-screening-validation")
    assert view_module._screening_only_result_rows(execution)

    for status in (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
        noncompleted = replace(
            execution,
            status=status,
            decision=None,
            failure_reason=f"{status.value} before completion",
        )
        assert view_module._screening_only_result_rows(noncompleted) == []

    forged_event = ExecutionEvent(
        event_type="legacy_negative_evidence_capture",
        message="與 typed assessments 不一致的事件。",
        details={"screening_matrix": ()},
    )
    forged_same_run = replace(execution, events=(forged_event,))
    assert view_module._screening_only_result_rows(forged_same_run) == []

    no_assessments = _execution("rec-screening-no-assessments", empty=True)
    unrelated_event = execution.events[0]
    forged_empty = replace(no_assessments, events=(unrelated_event,))
    assert view_module._screening_only_result_rows(forged_empty) == []


def test_official_delisting_rows_localize_stage_and_reason_at_display_boundary():
    from app_module.recommendation.negative_evidence_projection import (
        project_canonical_negative_evidence,
    )

    execution = _official_delisted_screening_execution(
        "rec-screening-official-delisted"
    )
    typed_row = project_canonical_negative_evidence(execution.decision).screening_matrix[0]
    assert typed_row["stage"] == "current_market_status_gate"
    assert typed_row["reason_codes"] == ("official_delisted",)
    event_row = execution.events[0].details["screening_matrix"][0]
    assert event_row["stage"] == "current_market_status_gate"
    assert event_row["reason_codes"] == ("official_delisted",)

    display_row = view_module._screening_only_result_rows(execution)[0]
    assert display_row["階段"] == "官方市場狀態（current_market_status_gate）"
    assert display_row["原因代碼"] == "已核驗下市／終止（official_delisted）"


def _readback(execution: RecommendationExecution, label: str, notes: str):
    persisted_at = datetime(2026, 9, 23, 1, tzinfo=timezone.utc)
    payload_hash = "sha256:" + "a" * 64
    artifact = "C:/temp/recommendation-artifact.json"
    receipt = SaveReceipt(
        result_id=execution.result_id,
        payload_hash=payload_hash,
        artifact_location=artifact,
        persisted_at=persisted_at,
        index_status=IndexStatus.INDEXED,
    )
    read_model = RecommendationExecutionReadModel(
        execution=execution,
        label=label,
        notes=notes,
        persisted_at=persisted_at,
        payload_hash=payload_hash,
        artifact_location=artifact,
        integrity_basis="canonical_payload_and_index_verified",
    )
    return receipt, read_model


def _view_with_execution(qt_app, execution, *, composition=None, universe_service=None):
    regime_service = SimpleNamespace(
        detect_regime=lambda: SimpleNamespace(regime="Trend"),
        get_strategy_config=lambda _regime: {},
    )
    view = RecommendationView(
        recommendation_service=MagicMock(),
        regime_service=regime_service,
        universe_service=universe_service,
    )
    view.current_execution = execution
    view.current_config = view._execution_config(execution)
    view.current_profile = "momentum"
    view.current_regime = "Trend"
    view.current_result_id = ""
    view.current_read_model = None
    view.current_save_receipt = None
    view._pending_save_receipt = None
    view._pending_save_metadata = None
    view.recommendation_composition = composition
    rows = view._current_table_rows()
    view.recommendations_model = PandasTableModel(pd.DataFrame(rows))
    view.results_table.setModel(view.recommendations_model)
    if rows:
        view.results_table.selectRow(0)
    return view


def _save_composition(execution, *, label, notes, query_results):
    receipt, read_model = _readback(execution, label, notes)
    save_service = MagicMock()
    save_service.save_execution.return_value = receipt
    queries = MagicMock()
    if isinstance(query_results, list):
        queries.get.side_effect = query_results
    else:
        queries.get.return_value = query_results
    return SimpleNamespace(save_service=save_service, queries=queries), receipt, read_model


def _patch_save_dialogs(monkeypatch, *, label="A result"):
    prompts: list[str] = []
    notices: list[str] = []

    def get_text(*_args, **_kwargs):
        prompts.append("asked")
        return label, True

    monkeypatch.setattr(view_module.QInputDialog, "getText", get_text)
    monkeypatch.setattr(
        view_module.QMessageBox,
        "information",
        lambda *args: notices.append(str(args[-1])),
    )
    monkeypatch.setattr(
        view_module.QMessageBox,
        "warning",
        lambda *args: notices.append(str(args[-1])),
    )
    monkeypatch.setattr(
        view_module.QMessageBox,
        "critical",
        lambda *args: notices.append(str(args[-1])),
    )
    return prompts, notices


def test_ab_execution_then_save_uses_a_once_and_never_acks_without_scope(
    qt_app, monkeypatch
):
    from ui_qt.views.recommendation import execution_coordinator as coordinator

    execution_a = _execution("rec-a")
    execution_b = _execution("rec-b", stock_code="2317")
    results = iter((execution_a, execution_b))
    monkeypatch.setattr(coordinator, "execute_recommendation", lambda *_args, **_kwargs: next(results))
    service = MagicMock()
    request_a = RecommendationExecutionRequest(_config_for_request())
    request_b = RecommendationExecutionRequest(_config_for_request())
    assert request_a.execute(service) is execution_a
    assert request_b.execute(service) is execution_b

    # Service shared state now reflects B, while the UI still holds A as last good.
    service.last_result = execution_b
    service.last_run_context = {"stock_code": "2317", "result_id": "rec-b"}
    expected_notes = "Profile: momentum, Regime: Trend"
    composition, receipt, read_model = _save_composition(
        execution_a,
        label="A result",
        notes=expected_notes,
        query_results=None,
    )
    composition.queries.get.return_value = read_model
    universe = SimpleNamespace(save_watchlist=MagicMock(return_value="watchlist-a"))
    view = _view_with_execution(
        qt_app,
        execution_a,
        composition=composition,
        universe_service=universe,
    )
    journal = MagicMock()
    view.journal_service = journal
    prompts, notices = _patch_save_dialogs(monkeypatch)

    class _SignalProbe:
        def connect(self, _callback):
            return None

    class _PendingWorker:
        def __init__(self, task_function):
            self.task_function = task_function
            self.progress = _SignalProbe()
            self.finished = _SignalProbe()
            self.error = _SignalProbe()
            self.cancelled = _SignalProbe()

        def start(self):
            return None

        def isRunning(self):
            return False

    # 啟動 B，但保留 A 的表格與封存結果；在 B 的完成 callback 送達前可保存 A。
    monkeypatch.setattr(view_module, "ProgressTaskWorker", _PendingWorker)
    monkeypatch.setattr(
        coordinator, "execute_recommendation", lambda *_args, **_kwargs: execution_b
    )
    view.recommendation_service = service
    view.is_beginner_mode = False
    view._collect_config = lambda: _config_for_request()
    view._execute_recommendation()
    assert view.current_execution is execution_a
    assert view._selected_stock_code() == "2330"
    worker_result = view.worker.task_function(lambda *_args: None, lambda: False)
    assert worker_result is execution_b
    # 模擬 A 執行後來源 regime 已切換；保存必須只讀 A 的 sealed snapshot。
    view.regime_service.detect_regime = MagicMock(
        return_value=SimpleNamespace(regime="Reversion")
    )

    view._save_recommendation_result()

    composition.save_service.save_execution.assert_called_once_with(
        execution_a,
        label="A result",
        notes=expected_notes,
    )
    composition.queries.get.assert_called_once_with(execution_a.result_id)
    universe.save_watchlist.assert_called_once()
    assert universe.save_watchlist.call_args.kwargs["codes"] == ["2330"]
    assert view.current_read_model is read_model
    assert view.current_save_receipt is receipt
    assert view.current_result_id == execution_a.result_id
    view.regime_service.detect_regime.assert_not_called()
    assert prompts == ["asked"]
    assert notices and "canonical readback 驗證" in notices[0]
    journal.assert_not_called()
    view._on_recommendation_finished(execution_b)
    assert view.current_result_id == ""
    view.close()


def test_scoped_execution_ack_is_unavailable_to_qt_and_owned_by_r015():
    from ui_qt.views.recommendation_view import _personalization_ack_unavailable_notice

    assert _personalization_ack_unavailable_notice(SimpleNamespace()) == ""
    notice = _personalization_ack_unavailable_notice(
        SimpleNamespace(personalization_scope="research_user")
    )
    assert "ACK 目前不可由 Qt 保存流程提供" in notice
    assert "R015 owner" in notice


def test_verified_save_repeat_does_not_write_or_recreate_watchlist(qt_app, monkeypatch):
    execution = _execution("rec-repeat")
    composition, _receipt, read_model = _save_composition(
        execution,
        label="A result",
        notes="Profile: momentum, Regime: Trend",
        query_results=None,
    )
    composition.queries.get.return_value = read_model
    universe = SimpleNamespace(save_watchlist=MagicMock(return_value="watchlist-a"))
    view = _view_with_execution(
        qt_app,
        execution,
        composition=composition,
        universe_service=universe,
    )
    prompts, notices = _patch_save_dialogs(monkeypatch)

    view._save_recommendation_result()
    view._save_recommendation_result()

    composition.save_service.save_execution.assert_called_once()
    composition.queries.get.assert_called_once_with(execution.result_id)
    universe.save_watchlist.assert_called_once()
    assert prompts == ["asked"]
    assert any("不會重複寫入" in message for message in notices)
    view.close()


def test_readback_failure_retries_same_receipt_without_repeating_save_or_watchlist(
    qt_app, monkeypatch
):
    execution = _execution("rec-query-retry")
    receipt, read_model = _readback(
        execution,
        "A result",
        "Profile: momentum, Regime: Trend",
    )
    composition = SimpleNamespace(
        save_service=SimpleNamespace(save_execution=MagicMock(return_value=receipt)),
        queries=SimpleNamespace(get=MagicMock(side_effect=[None, read_model])),
    )
    universe = SimpleNamespace(save_watchlist=MagicMock(return_value="watchlist-a"))
    view = _view_with_execution(
        qt_app,
        execution,
        composition=composition,
        universe_service=universe,
    )
    prompts, notices = _patch_save_dialogs(monkeypatch)

    view._save_recommendation_result()
    assert view._pending_save_receipt is receipt
    assert view.current_read_model is None
    assert universe.save_watchlist.call_count == 0

    view._save_recommendation_result()
    view._save_recommendation_result()

    composition.save_service.save_execution.assert_called_once_with(
        execution,
        label="A result",
        notes="Profile: momentum, Regime: Trend",
    )
    assert composition.queries.get.call_count == 2
    universe.save_watchlist.assert_called_once()
    assert prompts == ["asked"]
    assert any("verified readback 失敗" in message for message in notices)
    view.close()


def test_partial_index_retry_keeps_first_label_and_uses_canonical_writer_again(
    qt_app, monkeypatch
):
    execution = _execution("rec-partial")
    pending_receipt, _read_model = _readback(
        execution,
        "First label",
        "Profile: momentum, Regime: Trend",
    )
    pending_receipt = SaveReceipt(
        result_id=pending_receipt.result_id,
        payload_hash=pending_receipt.payload_hash,
        artifact_location=pending_receipt.artifact_location,
        persisted_at=pending_receipt.persisted_at,
        index_status=IndexStatus.PENDING,
    )
    indexed_receipt, read_model = _readback(
        execution,
        "First label",
        "Profile: momentum, Regime: Trend",
    )
    save_service = MagicMock()
    save_service.save_execution.side_effect = [
        PartialExecutionPersistenceError(pending_receipt, OSError("index unavailable")),
        indexed_receipt,
    ]
    composition = SimpleNamespace(
        save_service=save_service,
        queries=SimpleNamespace(get=MagicMock(return_value=read_model)),
    )
    universe = SimpleNamespace(save_watchlist=MagicMock(return_value="watchlist-a"))
    view = _view_with_execution(
        qt_app,
        execution,
        composition=composition,
        universe_service=universe,
    )
    prompts, notices = _patch_save_dialogs(monkeypatch, label="First label")

    view._save_recommendation_result()
    assert view._pending_save_metadata == (
        "First label",
        "Profile: momentum, Regime: Trend",
    )
    assert view._pending_save_receipt is None
    assert composition.queries.get.call_count == 0

    view._save_recommendation_result()

    assert save_service.save_execution.call_count == 2
    assert all(call.args[0] is execution for call in save_service.save_execution.call_args_list)
    assert [call.kwargs["label"] for call in save_service.save_execution.call_args_list] == [
        "First label",
        "First label",
    ]
    assert composition.queries.get.call_count == 1
    universe.save_watchlist.assert_called_once()
    assert prompts == ["asked"]
    assert any("索引尚未完成" in message for message in notices)
    view.close()


def test_cancel_and_stale_or_failed_callbacks_preserve_last_good_result(qt_app, monkeypatch):
    execution_a = _execution("rec-good")
    view = _view_with_execution(qt_app, execution_a)
    view._execution_generation = 7
    table_model = view.recommendations_model
    view.results_table.selectRow(0)
    before_config = dict(view.current_config)

    cancelled_b = _execution("rec-cancelled", status=ExecutionStatus.CANCELLED)
    view._on_recommendation_finished(cancelled_b, generation=7)
    assert view.current_execution is execution_a
    assert view.recommendations_model is table_model
    assert view._selected_stock_code() == "2330"
    assert view.current_config == before_config

    class _ErrorBox:
        Critical = 1

        def __init__(self, *_args):
            self.text = ""

        def setIcon(self, *_args):
            pass

        def setWindowTitle(self, *_args):
            pass

        def setText(self, value):
            self.text = value

        def setInformativeText(self, *_args):
            pass

        def setDetailedText(self, *_args):
            pass

        def exec(self):
            pass

    monkeypatch.setattr(view_module, "QMessageBox", _ErrorBox)
    view._on_recommendation_error("failure for next run", generation=7)
    view._on_recommendation_finished(_execution("stale-b"), generation=6)
    view._on_progress("stale progress", 88, generation=6)

    assert view.current_execution is execution_a
    assert view.recommendations_model is table_model
    assert view._selected_stock_code() == "2330"
    assert view.current_config == before_config
    assert "未完成" in view.result_status_label.text()
    view.close()


def test_completed_empty_execution_clears_previous_stock_rows(qt_app, monkeypatch):
    previous = _execution("rec-before-empty")
    empty = _execution("rec-empty", empty=True)
    view = _view_with_execution(qt_app, previous)
    notices = []
    monkeypatch.setattr(
        view_module.QMessageBox,
        "information",
        lambda *args: notices.append(str(args[-1])),
    )
    view._execution_generation = 5

    view._on_recommendation_finished(empty, generation=5)

    assert view.current_execution is empty
    assert view.current_result_id == ""
    assert view.recommendations_model.rowCount() == 0
    assert view._selected_stock_code() == ""
    assert notices and "篩選前沒有可評估的候選資料" in notices[0]
    save_warnings = []
    save_prompts = []
    monkeypatch.setattr(
        view_module.QMessageBox,
        "warning",
        lambda *args: save_warnings.append(str(args[-1])),
    )
    monkeypatch.setattr(
        view_module.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: save_prompts.append("prompt") or ("", True),
    )
    view._save_recommendation_result()
    assert save_warnings and "含有推薦列或同次封存篩選列" in save_warnings[0]
    assert not save_prompts
    assert not view.save_result_btn.isVisible()
    view.close()


@pytest.mark.parametrize(
    "status", (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED)
)
def test_noncompleted_execution_cannot_be_saved_as_screening_result(
    qt_app, monkeypatch, status
):
    execution = _execution(f"rec-noncompleted-{status.value}", status=status, empty=True)
    composition, _receipt, _read_model = _save_composition(
        execution,
        label="不應保存",
        notes="不應呼叫 canonical writer",
        query_results=None,
    )
    view = _view_with_execution(qt_app, execution, composition=composition)
    prompts = []
    warnings = []
    monkeypatch.setattr(
        view_module.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: prompts.append("asked") or ("", True),
    )
    monkeypatch.setattr(
        view_module.QMessageBox,
        "warning",
        lambda *args: warnings.append(str(args[-1])),
    )

    view._save_recommendation_result()

    composition.save_service.save_execution.assert_not_called()
    composition.queries.get.assert_not_called()
    assert prompts == []
    assert warnings and "completed execution" in warnings[0]
    view.close()


def test_screening_only_execution_saves_reopens_and_researches_exact_stock(
    qt_app,
    tmp_path,
    monkeypatch,
):
    from app_module.recommendation.composition import build_recommendation_composition
    from app_module.watchlist_analysis_service import WatchlistAnalysisService
    from data_module.config import TWStockConfig

    execution = _screening_only_execution("rec-screening-only-roundtrip")
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
    )
    composition = build_recommendation_composition(config)
    universe_service = MagicMock()
    view = RecommendationView(
        recommendation_service=MagicMock(),
        regime_service=SimpleNamespace(
            detect_regime=lambda: SimpleNamespace(regime="Trend"),
            get_strategy_config=lambda _regime: {},
        ),
        config=config,
        universe_service=universe_service,
    )
    view.recommendation_composition = composition
    view._execution_generation = 4
    information = []
    save_dialog_titles = []
    monkeypatch.setattr(
        view_module.QMessageBox,
        "information",
        lambda *_args: information.append(_args),
    )
    monkeypatch.setattr(
        view_module.QMessageBox,
        "warning",
        lambda *_args: pytest.fail(f"不應出現保存警告：{_args[-1]}"),
    )
    monkeypatch.setattr(
        view_module.QMessageBox,
        "critical",
        lambda *_args: pytest.fail(f"canonical 保存不應失敗：{_args[-1]}"),
    )

    def enter_save_name(_parent, title, _prompt, *, text):
        save_dialog_titles.append((title, text))
        return "1477 未入選篩選紀錄", True

    monkeypatch.setattr(view_module.QInputDialog, "getText", enter_save_name)
    view.show()
    view._on_recommendation_finished(execution, generation=4)
    qt_app.processEvents()

    frame = view.recommendations_model.getDataFrame()
    assert list(frame["證券代號"]) == ["1477", "1101"]
    assert frame["紀錄類型"].tolist() == ["篩選紀錄／未入選"] * 2
    assert frame["原因代碼"].tolist() == ["liquidity_below_minimum"] * 2
    assert view.current_execution is execution and not view.current_execution.items
    assert view.result_title_label.text() == "篩選紀錄／未入選（僅研究，不代表推薦）"
    assert view.save_result_btn.text() == "保存篩選紀錄"
    assert not view.add_to_watchlist_btn.isVisible()
    assert not view.send_to_backtest_btn.isVisible()
    assert not view.send_profile_to_portfolio_backtest_btn.isVisible()
    assert not view.export_report_btn.isVisible()
    assert view.stock_research_btn.text() == "研究未入選股票"
    assert not view.stock_research_btn.isEnabled()

    view.results_table.selectRow(1)
    qt_app.processEvents()
    assert view.stock_research_btn.isEnabled()
    assert "未入選（僅供研究，不代表推薦）" in view.detail_text.toPlainText()
    immediate_contexts = []
    view.stockResearchRequested.connect(immediate_contexts.append)
    QTest.mouseClick(view.stock_research_btn, Qt.LeftButton)
    assert len(immediate_contexts) == 1
    assert immediate_contexts[0].stock_code == "1101"
    assert immediate_contexts[0].decision_date == "2026-09-23"
    assert immediate_contexts[0].result_id == ""
    assert "篩選紀錄／未入選" in immediate_contexts[0].source_label

    QTest.mouseClick(view.save_result_btn, Qt.LeftButton)
    qt_app.processEvents()
    assert save_dialog_titles and save_dialog_titles[0][0] == "保存篩選紀錄"
    assert view.current_read_model is not None
    assert view.current_read_model.integrity_basis == "canonical_payload_and_index_verified"
    assert view.current_read_model.execution == execution
    assert view.current_read_model.execution.items == ()
    assert view.current_result_id == execution.result_id
    assert view._verified_saved_result_id() == execution.result_id
    assert view.recommendations_model.getDataFrame()["證券代號"].tolist() == ["1477", "1101"]
    assert universe_service.save_watchlist.call_count == 0
    assert information[-1][1] == "篩選紀錄已保存"
    assert "未建立觀察清單、回測或推薦" in information[-1][-1]

    source_service = WatchlistAnalysisService(config)
    exclusion = source_service.fetch("1101", execution.result_id, date(2026, 9, 23))
    assert exclusion.status == "not_in_result"
    assert exclusion.result_id == execution.result_id
    assert exclusion.reasons == "liquidity_below_minimum"
    listed = source_service.list_saved_sources("1101", as_of_date=date(2026, 9, 23))
    assert [item["result_id"] for item in listed] == [execution.result_id]
    assert listed[0]["membership_status"] == "not_in_result"

    reopened = RecommendationView(
        recommendation_service=MagicMock(),
        regime_service=SimpleNamespace(
            detect_regime=lambda: SimpleNamespace(regime="Trend"),
            get_strategy_config=lambda _regime: {},
        ),
        config=config,
        universe_service=MagicMock(),
    )
    reopened.show()
    reopened.saved_result_id_input.setText(execution.result_id)
    QTest.mouseClick(reopened.load_saved_result_button, Qt.LeftButton)
    worker = reopened._saved_result_load_worker
    assert worker is not None and worker.wait(10_000)
    qt_app.processEvents()
    qt_app.processEvents()
    assert reopened.current_read_model is not None
    assert reopened.current_read_model.result_id == execution.result_id
    assert reopened.current_result_id == execution.result_id
    assert reopened._verified_saved_result_id() == execution.result_id
    assert reopened.current_execution.items == ()
    assert reopened.recommendations_model.getDataFrame()["證券代號"].tolist() == [
        "1477",
        "1101",
    ]
    assert "篩選紀錄" in reopened.result_status_label.text()
    assert "不代表推薦" in reopened.result_status_label.text()
    reopened.results_table.selectRow(1)
    qt_app.processEvents()
    assert reopened.stock_research_btn.text() == "研究未入選股票"
    assert reopened.stock_research_btn.isEnabled()
    reopened_contexts = []
    reopened.stockResearchRequested.connect(reopened_contexts.append)
    QTest.mouseClick(reopened.stock_research_btn, Qt.LeftButton)
    assert len(reopened_contexts) == 1
    assert reopened_contexts[0].stock_code == "1101"
    assert reopened_contexts[0].decision_date == "2026-09-23"
    assert reopened_contexts[0].result_id == execution.result_id
    assert reopened_contexts[0].source_id == execution.result_id
    assert "已保存篩選紀錄／未入選" == reopened_contexts[0].source_label

    reopened.close()
    view.close()
    qt_app.processEvents()


def test_saved_empty_canonical_execution_load_keeps_identity_and_date(
    qt_app,
    tmp_path,
):
    from app_module.recommendation.composition import build_recommendation_composition

    result_id = "rec-empty-canonical-readback"
    execution = _execution(result_id, empty=True)
    output_root = tmp_path / "output"

    class _IsolatedConfig:
        def resolve_output_path(self, subfolder):
            path = output_root / subfolder
            path.mkdir(parents=True, exist_ok=True)
            return path

    config = _IsolatedConfig()
    composition = build_recommendation_composition(config)
    receipt = composition.save_service.save_execution(
        execution,
        label="空結果 canonical 讀回",
        notes="test-owned isolated store",
    )
    assert receipt.result_id == result_id

    view = RecommendationView(
        recommendation_service=MagicMock(),
        regime_service=SimpleNamespace(
            detect_regime=lambda: SimpleNamespace(regime="Trend"),
            get_strategy_config=lambda _regime: {},
        ),
    )
    view.config = config
    view.recommendation_composition = composition
    view.saved_result_id_input.setText(result_id)
    view.load_saved_result_button.setEnabled(True)

    try:
        view._load_saved_recommendation_result()
        worker = view._saved_result_load_worker
        assert worker is not None
        assert worker.wait(10_000)
        qt_app.processEvents()
        qt_app.processEvents()

        assert view.current_read_model is not None, view.result_status_label.text()
        assert view.current_read_model.integrity_basis == (
            "canonical_payload_and_index_verified"
        )
        assert view.current_result_id == result_id
        assert view.current_execution == execution
        assert view.current_execution.context.as_of_date == execution.context.as_of_date
        assert view._verified_saved_result_id() == result_id
        assert view._loaded_saved_result_identity == (
            view._canonical_loaded_result_identity(view.current_read_model, result_id)
        )
        assert view.recommendations_model is not None
        assert view.recommendations_model.rowCount() == 0
        assert view.recommendations_model.getDataFrame().empty
        assert "原結果沒有推薦列" in view.result_status_label.text()
    finally:
        view.close()


def test_daily_snapshot_auto_load_uses_exact_status_identity(qt_app, tmp_path):
    result_id = "rec-scheduled-ui-smoke"
    output_root = tmp_path / "output"
    runs_dir = output_root / "recommendation" / "runs"
    runs_dir.mkdir(parents=True)
    status_path = (
        output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    )
    status_path.parent.mkdir(parents=True)
    status_path.write_text(
        json.dumps(
            {
                "task": "baldr-recommendation-snapshot-daily",
                "status": "passed",
                "confirm": False,
                "writes_recommendation_result": True,
                "writes_evidence_db": False,
                "auto_trading": False,
                "lifecycle_action": False,
                "decision_date": "2026-09-23",
                "result_id": result_id,
                "recommendations_count": 1,
                "output_root": str(output_root),
                "runs_dir": str(runs_dir),
            }
        ),
        encoding="utf-8",
    )

    class _Config:
        def __init__(self, root) -> None:
            self.output_root = root

        def resolve_output_path(self, subfolder):
            path = self.output_root / subfolder
            path.mkdir(parents=True, exist_ok=True)
            return path

    execution = _execution(result_id)
    from app_module.recommendation.composition import build_recommendation_composition

    composition = build_recommendation_composition(_Config(output_root))
    composition.save_service.save_execution(
        execution, label="daily snapshot", notes="test"
    )
    view = RecommendationView(
        recommendation_service=MagicMock(),
        regime_service=SimpleNamespace(
            detect_regime=lambda: SimpleNamespace(regime="Trend"),
            get_strategy_config=lambda _regime: {},
        ),
        config=_Config(output_root),
        universe_service=MagicMock(),
    )
    view.recommendation_composition = composition
    try:
        qt_app.processEvents()
        worker = view._saved_result_load_worker
        assert worker is not None and worker.wait(10_000)
        qt_app.processEvents()
        qt_app.processEvents()

        assert view.current_read_model is not None, view.result_status_label.text()
        assert view.current_read_model.result_id == result_id
        assert view.current_save_receipt is None
        assert view._verified_saved_result_id() == result_id
        assert "每日排程研究候選" in view.result_status_label.text()
        assert "僅供研究判讀" in view.result_status_label.text()
    finally:
        view.close()
        qt_app.processEvents()


def _config_for_request():
    return {
        "patterns": {"selected": ["W底"]},
        "signals": {"technical_indicators": ["trend"]},
        "filters": {"price_change_min": "1.25"},
        "profile_id": "momentum",
    }
