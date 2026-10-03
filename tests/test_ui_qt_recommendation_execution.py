from __future__ import annotations

from datetime import date, datetime, timezone
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from app_module.recommendation.contracts import (
    Context,
    DecisionBatch,
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
    view.close()


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


def _config_for_request():
    return {
        "patterns": {"selected": ["W底"]},
        "signals": {"technical_indicators": ["trend"]},
        "filters": {"price_change_min": "1.25"},
        "profile_id": "momentum",
    }
