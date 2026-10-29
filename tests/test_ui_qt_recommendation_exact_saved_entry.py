from __future__ import annotations

import os
import threading
from decimal import Decimal
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from app_module.scheduled_recommendation_status import ScheduledRecommendationPointer
from app_module.recommendation.legacy_dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation.queries import RecommendationExecutionReadModel
from tests.test_personal_recommendation_choice import (
    _canonical_rule_only_query_fixture,
)
from tests.test_ui_qt_personal_recommendation_choice import (
    _IsolatedRecommendationConfig,
    _make_view,
    _wait_for_saved_result_load,
)


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    yield application


def _read_model(result_id: str):
    queries, _ = _canonical_rule_only_query_fixture(result_id)
    read_model = queries.get(result_id)
    assert read_model is not None and read_model.execution is not None
    return queries, read_model


def _view(tmp_path: Path, queries) -> object:
    view = _make_view()
    view.config = _IsolatedRecommendationConfig(tmp_path / "output")
    view.recommendation_composition = SimpleNamespace(queries=queries)
    view.load_saved_result_button.setEnabled(True)
    return view


def _show_view(view: object, qt_app: QApplication) -> None:
    view.resize(1280, 760)
    view.show()
    qt_app.processEvents()


def _assert_saved_result_focus(view: object) -> None:
    viewport = view.result_scroll.viewport()
    status_top = view.result_status_label.mapTo(viewport, QPoint(0, 0)).y()
    table_top = view.results_table.mapTo(viewport, QPoint(0, 0)).y()
    assert -4 <= status_top <= 24
    assert table_top < viewport.height()
    assert table_top + view.results_table.height() > 0


def _assert_saved_table_is_compact(view: object, qt_app: QApplication, row_count: int) -> None:
    qt_app.processEvents()
    table = view.results_table
    assert view.recommendations_model.rowCount() == row_count
    detail_group = view.result_splitter.widget(1)
    if row_count == 0:
        assert view.result_splitter.isHidden()
        assert view.empty_result_state_widget.isVisible()
        assert detail_group.isHidden()
        return
    assert table.minimumHeight() == view.results_table_minimum_height, (
        table.minimumHeight(),
        table.maximumHeight(),
        table.minimumSizeHint().height(),
        table.size().height(),
        view.results_table_minimum_height,
        view.result_splitter.minimumHeight(),
        view.result_splitter.maximumHeight(),
        view.result_splitter.sizes(),
    )
    frame_and_header = table.frameWidth() * 2 + table.horizontalHeader().height()
    five_row_height = frame_and_header + table.verticalHeader().defaultSectionSize() * 5
    assert table.minimumHeight() < five_row_height
    splitter_sizes = view.result_splitter.sizes()
    assert splitter_sizes[0] <= table.minimumHeight() + 12
    assert table.height() >= (
        frame_and_header
        + table.verticalHeader().defaultSectionSize() * max(1, row_count)
    )
    assert not detail_group.isHidden()
    viewport = view.result_scroll.viewport()
    if row_count:
        first_cell_top = table.viewport().mapTo(
            viewport,
            table.visualRect(table.model().index(0, 0)).topLeft(),
        ).y()
        assert 0 <= first_cell_top < viewport.height()
    detail_top = detail_group.mapTo(viewport, QPoint(0, 0)).y()
    source_top = view.company_source_snapshot_label.mapTo(viewport, QPoint(0, 0)).y()
    assert detail_top < viewport.height()
    assert source_top < viewport.height()
    assert source_top + view.company_source_snapshot_label.height() > 0


def test_public_exact_open_focuses_verified_canonical_result_and_table(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    result_id = "exact-visible-canonical-001"
    queries, _ = _read_model(result_id)
    view = _view(tmp_path, queries)
    _show_view(view, qt_app)
    try:
        assert view.open_saved_recommendation_result(result_id)
        _wait_for_saved_result_load(view, qt_app)
        qt_app.processEvents()
        assert view._verified_saved_result_id() == result_id
        _assert_saved_table_is_compact(view, qt_app, 2)
        _assert_saved_result_focus(view)
    finally:
        view.close()
        qt_app.processEvents()


def test_public_exact_open_focuses_verified_legacy_read_only_result(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    result_id = "exact-visible-legacy-001"
    legacy_result = RecommendationResultDTO(
        result_id=result_id,
        result_name="fixture",
        config={},
        recommendations=[
            RecommendationDTO(
                stock_code="2330",
                stock_name="fixture",
                close_price=Decimal("100"),
                price_change=0.0,
                total_score=0.0,
                indicator_score=0.0,
                pattern_score=0.0,
                volume_score=0.0,
                recommendation_reasons="fixture",
                industry="fixture",
                regime_match=False,
            )
        ],
    )
    read_model = RecommendationExecutionReadModel(
        execution=None,
        label="fixture",
        notes=None,
        persisted_at=None,
        payload_hash=None,
        artifact_location="fixture://legacy-result",
        legacy_result=legacy_result,
        raw_artifact_sha256="sha256:" + "a" * 64,
        integrity_basis="legacy_read_time_hash_only",
    )
    view = _view(
        tmp_path,
        SimpleNamespace(
            get=lambda requested_id: read_model,
            list=lambda: pytest.fail("unexpected saved-source enumeration"),
        ),
    )
    _show_view(view, qt_app)
    try:
        assert view.open_saved_recommendation_result(result_id)
        _wait_for_saved_result_load(view, qt_app)
        qt_app.processEvents()
        assert view._verified_legacy_result_id() == result_id
        assert view.recommendations_model.rowCount() == 1
        assert "唯讀開啟舊格式" in view.result_status_label.text()
        _assert_saved_table_is_compact(view, qt_app, 1)
        _assert_saved_result_focus(view)
    finally:
        view.close()
        qt_app.processEvents()


def test_public_exact_open_compacts_empty_canonical_result_to_one_row_frame(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    from app_module.recommendation.composition import build_recommendation_composition
    from tests.test_ui_qt_recommendation_execution import _execution

    result_id = "exact-visible-empty-canonical-001"
    config = _IsolatedRecommendationConfig(tmp_path / "output")
    composition = build_recommendation_composition(config)
    execution = _execution(result_id, empty=True)
    composition.save_service.save_execution(execution, label="empty", notes="fixture")
    view = _view(tmp_path, composition.queries)
    _show_view(view, qt_app)
    try:
        assert view.open_saved_recommendation_result(result_id)
        _wait_for_saved_result_load(view, qt_app)
        qt_app.processEvents()
        assert view._verified_saved_result_id() == result_id
        assert "原結果沒有推薦列" in view.result_status_label.text()
        _assert_saved_table_is_compact(view, qt_app, 0)
        _assert_saved_result_focus(view)
    finally:
        view.close()
        qt_app.processEvents()


def test_public_exact_open_does_not_override_user_scroll_while_reading(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    result_id = "exact-user-scroll-001"
    backing_queries, _ = _read_model(result_id)
    entered = threading.Event()
    release = threading.Event()

    def delayed_get(requested_id: str):
        entered.set()
        assert release.wait(5)
        return backing_queries.get(requested_id)

    view = _view(
        tmp_path,
        SimpleNamespace(get=delayed_get, list=lambda: pytest.fail("unexpected list")),
    )
    _show_view(view, qt_app)
    bar = view.result_scroll.verticalScrollBar()
    focus_values = []
    original_focus = view._focus_public_saved_result_status

    def record_focus_guard(request):
        before = bar.value()
        original_focus(request)
        focus_values.append((before, bar.value()))

    view._focus_public_saved_result_status = record_focus_guard
    try:
        assert view.open_saved_recommendation_result(result_id)
        assert entered.wait(2)
        bar.setRange(0, 1000)
        bar.setValue(140)
        user_revision = view._result_scroll_revision
        request = view._public_saved_result_scroll_request
        assert request is not None
        assert user_revision != request[2]

        release.set()
        _wait_for_saved_result_load(view, qt_app)
        qt_app.processEvents()
        assert view._public_saved_result_scroll_request is None
        assert focus_values
        assert all(before == after for before, after in focus_values)
    finally:
        release.set()
        view.close()
        qt_app.processEvents()


def test_public_exact_open_failure_does_not_schedule_result_focus(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    entered = threading.Event()
    release = threading.Event()

    def delayed_error(_requested_id: str):
        entered.set()
        assert release.wait(5)
        raise ValueError("saved result unavailable")

    view = _view(
        tmp_path,
        SimpleNamespace(get=delayed_error, list=lambda: pytest.fail("unexpected list")),
    )
    _show_view(view, qt_app)
    try:
        assert view.open_saved_recommendation_result("exact-error-001")
        assert entered.wait(2)
        release.set()
        _wait_for_saved_result_load(view, qt_app)
        assert view._public_saved_result_scroll_request is None
        assert "saved result unavailable" in view.result_status_label.text()
        assert view.result_scroll.verticalScrollBar().value() == 0
    finally:
        release.set()
        view.close()
        qt_app.processEvents()


def test_public_exact_open_uses_only_get_and_ignores_other_list_selection(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    result_id = "exact-workbench-open-001"
    backing_queries, read_model = _read_model(result_id)
    entered = threading.Event()
    release = threading.Event()
    get_calls: list[str] = []
    list_calls: list[bool] = []

    def get(requested_id: str):
        get_calls.append(requested_id)
        entered.set()
        assert release.wait(5)
        return backing_queries.get(requested_id)

    def list_sources():
        list_calls.append(True)
        raise AssertionError("exact result opening must not enumerate saved sources")

    view = _view(
        tmp_path,
        SimpleNamespace(get=get, list=list_sources),
    )
    previous_execution = object()
    view.current_execution = previous_execution
    view.saved_result_id_input.setText("older-visible-id")
    view._saved_source_expected_identity = (
        "old-label", "", "", "different-result-id", "", "", "", ""
    )
    try:
        assert view.return_to_daily_decision_button.isHidden()
        previous_generation = view._saved_result_load_generation
        view.result_source_tabs.setCurrentWidget(view.daily_market_research_view)
        view.result_scroll.verticalScrollBar().setValue(120)
        assert view.open_saved_recommendation_result(result_id)
        assert entered.wait(2)
        assert view.result_source_tabs.currentWidget() is view.result_panel
        assert view.result_scroll.verticalScrollBar().value() == 0
        assert view.return_to_daily_decision_button.isHidden()
        assert view._saved_result_load_generation == previous_generation + 1
        assert view.saved_result_id_input.text() == "older-visible-id"
        assert view.current_execution is previous_execution

        view.result_source_tabs.setCurrentWidget(view.daily_market_research_view)
        assert not view.open_saved_recommendation_result("another-result-id")
        assert view.result_source_tabs.currentWidget() is view.daily_market_research_view
        assert "另一筆保存結果仍在讀取" in view.result_status_label.text()
        assert view._saved_result_load_generation == previous_generation + 1
        assert get_calls == [result_id]
        assert list_calls == []

        release.set()
        _wait_for_saved_result_load(view, qt_app)
        assert view.current_read_model == read_model
        assert view._verified_saved_result_id() == result_id
    finally:
        release.set()
        view.close()
        qt_app.processEvents()


@pytest.mark.parametrize("result_id", ("", " ", " padded-id "))
def test_public_exact_open_rejects_non_exact_ids_and_closed_view(
    qt_app: QApplication,
    tmp_path: Path,
    result_id: str,
) -> None:
    get_calls: list[str] = []
    view = _view(
        tmp_path,
        SimpleNamespace(get=lambda value: get_calls.append(value), list=lambda: ()),
    )
    try:
        assert not view.open_saved_recommendation_result(result_id)
        assert view._saved_result_load_generation == 0
        assert get_calls == []
        assert "ID 無效" in view.result_status_label.text()

        event = QCloseEvent()
        view.closeEvent(event)
        assert event.isAccepted()
        assert not view.open_saved_recommendation_result("valid-result-id")
        assert view._saved_result_load_generation == 0
        assert get_calls == []
    finally:
        view.close()
        qt_app.processEvents()


def test_exact_open_cancellation_keeps_old_callback_from_replacing_view(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    result_id = "exact-workbench-cancel-001"
    backing_queries, _ = _read_model(result_id)
    entered = threading.Event()
    release = threading.Event()

    def delayed_get(requested_id: str):
        entered.set()
        assert release.wait(5)
        return backing_queries.get(requested_id)

    view = _view(
        tmp_path,
        SimpleNamespace(get=delayed_get, list=lambda: pytest.fail("unexpected list")),
    )
    previous_execution = object()
    view.current_execution = previous_execution
    try:
        assert view.open_saved_recommendation_result(result_id)
        worker = view._saved_result_load_worker
        assert worker is not None
        assert entered.wait(2)

        view._cancel_saved_source_read()
        assert worker.is_cancel_requested()
        release.set()
        assert worker.wait(10_000)
        qt_app.processEvents()
        qt_app.processEvents()

        assert view.current_execution is previous_execution
        assert view.current_read_model is None
        assert view._verified_saved_result_id() == ""
        assert view._public_saved_result_scroll_request is None
    finally:
        release.set()
        view.close()
        qt_app.processEvents()


def test_exact_open_rejects_new_read_while_shutdown_waits_for_existing_worker(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    first_result_id = "exact-workbench-shutdown-001"
    second_result_id = "exact-workbench-shutdown-002"
    backing_queries, _ = _read_model(first_result_id)
    entered = threading.Event()
    release = threading.Event()
    get_calls: list[str] = []

    def delayed_get(requested_id: str):
        get_calls.append(requested_id)
        entered.set()
        assert release.wait(5)
        return backing_queries.get(requested_id)

    view = _view(
        tmp_path,
        SimpleNamespace(get=delayed_get, list=lambda: pytest.fail("unexpected list")),
    )
    try:
        assert view.open_saved_recommendation_result(first_result_id)
        worker = view._saved_result_load_worker
        assert worker is not None
        assert entered.wait(2)

        assert not view.request_cooperative_shutdown()
        shutdown_generation = view._saved_result_load_generation
        assert view._saved_result_open_closed
        assert not view.open_saved_recommendation_result(second_result_id)
        assert view._saved_result_load_generation == shutdown_generation
        assert get_calls == [first_result_id]

        release.set()
        assert worker.wait(10_000)
        qt_app.processEvents()
        qt_app.processEvents()
        assert get_calls == [first_result_id]
    finally:
        release.set()
        qt_app.processEvents()
        view.close()
        qt_app.processEvents()


@pytest.mark.parametrize(
    ("date_delta", "count_delta", "expected_error"),
    (
        (timedelta(days=1), 0, "每日快照決策日期與保存結果不一致"),
        (timedelta(0), 1, "每日快照候選筆數與保存結果不一致"),
    ),
)
def test_matching_scheduled_pointer_keeps_date_and_count_guards(
    qt_app: QApplication,
    tmp_path: Path,
    date_delta: timedelta,
    count_delta: int,
    expected_error: str,
) -> None:
    result_id = "exact-workbench-scheduled-guard-001"
    backing_queries, read_model = _read_model(result_id)
    execution = read_model.execution
    assert execution is not None
    view = _view(
        tmp_path,
        SimpleNamespace(
            get=backing_queries.get,
            list=lambda: pytest.fail("exact result opening must not enumerate saved sources"),
        ),
    )
    previous_execution = object()
    view.current_execution = previous_execution
    view._pending_scheduled_recommendation = ScheduledRecommendationPointer(
        result_id=result_id,
        decision_date=execution.context.as_of_date + date_delta,
        recommendations_count=len(execution.items) + count_delta,
    )
    try:
        assert view.open_saved_recommendation_result(result_id)
        _wait_for_saved_result_load(view, qt_app)
        assert view.current_execution is previous_execution
        assert view.current_read_model is None
        assert expected_error in view.result_status_label.text()
    finally:
        view.close()
        qt_app.processEvents()
