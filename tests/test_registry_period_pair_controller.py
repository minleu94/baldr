from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from app_module.recommendation_portfolio_full_period_pair_v1 import (
    FullPeriodPairReadErrorV1,
    FullPeriodPairReadV1,
    FullPeriodRunReadV1,
)
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.saved_strategy_rule_card import metadata_sha256
from ui_qt.views.research_lab import registry_period_pair_controller as controller_module
from ui_qt.views.research_lab.registry_period_pair_controller import (
    RegistryPeriodPairController,
)
from ui_qt.views.research_lab.run_registry_compare_widget import RunRegistryCompareWidget
from ui_qt.workers.task_worker import TaskWorker


@pytest.fixture
def qt_app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _wait_until(app: QApplication, predicate, timeout_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        QTest.qWait(5)
    app.processEvents()
    return bool(predicate())


def _metadata(run_id: str) -> ResearchRunMetadataDTO:
    return ResearchRunMetadataDTO(
        run_id=run_id,
        run_name=run_id,
        run_type="recommendation_portfolio",
        strategy_id=f"strategy-{run_id}",
        strategy_version="v1",
        original_input={"tags": ["controller-race-test"]},
        start_date="2026-01-02",
        end_date="2026-01-08",
        execution_price="next_open",
        payload_hash=f"sha256:{run_id}",
        created_at="2026-06-14T12:00:00",
    )


class _RegistryService:
    def __init__(self) -> None:
        self.runs = [_metadata("left"), _metadata("right"), _metadata("third")]
        self._metadata_by_id = {item.run_id: item for item in self.runs}
        self.repository = SimpleNamespace(get_metadata=self._metadata_by_id.get)
        self.load_calls: list[str] = []

    def list_runs(self, include_archived: bool = False):
        return list(self.runs)

    def load_run_data(self, run_id: str):
        self.load_calls.append(run_id)
        raise AssertionError("期間配對 controller 不得自行載入 Registry artifact")


def _pair_result(
    left_metadata: ResearchRunMetadataDTO,
    right_metadata: ResearchRunMetadataDTO,
) -> FullPeriodPairReadV1:
    left = FullPeriodRunReadV1(
        registry_run_id=left_metadata.run_id,
        parent_id="left-parent",
        strategy_id=left_metadata.strategy_id,
        strategy_version=left_metadata.strategy_version,
        capture=None,
        precision=None,
        metadata_identity_sha256=metadata_sha256(left_metadata),
    )
    right = FullPeriodRunReadV1(
        registry_run_id=right_metadata.run_id,
        parent_id="right-parent",
        strategy_id=right_metadata.strategy_id,
        strategy_version=right_metadata.strategy_version,
        capture=None,
        precision=None,
        metadata_identity_sha256=metadata_sha256(right_metadata),
    )
    return FullPeriodPairReadV1(
        left=left,
        right=right,
        market="twse",
        calendar_external_sha256="a" * 64,
        calendar_evidence_sha256="b" * 64,
        expected_session_dates=("2026-01-02", "2026-01-05"),
        left_missing_session_dates=("2026-01-05",),
        right_missing_session_dates=(),
        left_unexpected_session_dates=(),
        right_unexpected_session_dates=("2026-01-08",),
        coverage_complete=False,
        status="blocked",
        reasons=("calendar_candidate_only", "precision_capture_missing"),
    )


class _BlockingPairReader:
    def __init__(self, result: FullPeriodPairReadV1, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def read(self, left_id: str, right_id: str, **kwargs) -> FullPeriodPairReadV1:
        self.calls.append((left_id, right_id, kwargs))
        self.entered.set()
        if not self.release.wait(timeout=4.0):
            raise TimeoutError("測試 pair reader 未在期限內釋放")
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def pair_controller(qt_app, tmp_path: Path, monkeypatch):
    service = _RegistryService()
    result = _pair_result(service.runs[0], service.runs[1])
    pair_reader = _BlockingPairReader(result)
    monkeypatch.setattr(
        controller_module,
        "build_recommendation_composition",
        lambda config: SimpleNamespace(persistence=object()),
    )
    monkeypatch.setattr(
        controller_module,
        "RecommendationPortfolioFullPeriodPairReadServiceV1",
        lambda research_run_service, result_reader: pair_reader,
    )

    config = SimpleNamespace(
        data_root=tmp_path / "data-root",
        output_root=tmp_path / "output-root",
        personal_data_root=None,
        personal_store_root=None,
        personal_journal_root=None,
    )
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()
    widget.run_list.item(0).setSelected(True)
    widget.run_list.item(1).setSelected(True)
    generation = [7]
    controller = RegistryPeriodPairController(
        service, config, widget, lambda: generation[0], parent=widget,
    )
    calendar_path = tmp_path / "candidate-calendar.json"
    external_sha = "a" * 64
    controller.artifact_path.setText(str(calendar_path))
    controller.external_sha.setText(external_sha)
    controller.market.setCurrentIndex(controller.market.findData("twse"))

    case = SimpleNamespace(
        app=qt_app,
        service=service,
        result=result,
        reader=pair_reader,
        config=config,
        widget=widget,
        generation=generation,
        controller=controller,
        calendar_path=calendar_path,
        external_sha=external_sha,
    )
    try:
        yield case
    finally:
        pair_reader.release.set()
        worker = controller.worker
        if worker is not None:
            controller.begin_shutdown()
            assert worker.wait(5000), "pair worker 未在 teardown 期限內自然結束"
            assert _wait_until(qt_app, lambda: controller.worker is None)
        widget.close()
        widget.deleteLater()
        qt_app.processEvents()


def _start_read(case) -> TaskWorker:
    case.controller.apply_button.click()
    assert case.controller._pin is not None
    case.widget.compare_period_pair_button.click()
    worker = case.controller.worker
    assert isinstance(worker, TaskWorker)
    assert case.reader.entered.wait(timeout=2.0)
    return worker


def test_controller_keeps_busy_until_native_finish_and_forwards_both_pins(
    pair_controller, monkeypatch,
):
    case = pair_controller
    opened_calendar_paths: list[Path] = []
    original_open = Path.open

    def watch_calendar_open(path: Path, *args, **kwargs):
        if path == case.calendar_path:
            opened_calendar_paths.append(path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", watch_calendar_open)
    worker = _start_read(case)

    assert case.widget._period_pair_busy is True
    assert case.widget.compare_period_pair_button.isEnabled() is False
    assert len(case.reader.calls) == 1
    left_id, right_id, kwargs = case.reader.calls[0]
    assert (left_id, right_id) == ("left", "right")
    assert kwargs["expected_left_metadata_sha256"] == metadata_sha256(case.service.runs[0])
    assert kwargs["expected_right_metadata_sha256"] == metadata_sha256(case.service.runs[1])
    assert kwargs["calendar_path"] == case.calendar_path
    assert kwargs["expected_calendar_sha256"] == case.external_sha
    assert kwargs["market"] == "twse"
    assert kwargs["protected_roots"] == (case.config.data_root, case.config.output_root)
    assert callable(kwargs["check_cancel"])
    assert opened_calendar_paths == []
    assert case.service.load_calls == []

    case.reader.release.set()
    assert worker.wait(5000)
    # 結果與 native-finished 回覆仍在 GUI queue；處理前保留 worker 與 busy。
    assert case.controller.worker is worker
    assert case.widget._period_pair_busy is True
    assert case.widget._period_pair_result is None

    assert _wait_until(case.app, lambda: case.controller.worker is None)
    assert case.widget._period_pair_busy is False
    assert case.widget._period_pair_result is case.result
    assert opened_calendar_paths == []


@pytest.mark.parametrize(
    "change",
    [
        pytest.param("selection", id="selection-changed"),
        pytest.param("generation", id="generation-changed"),
        pytest.param("execution", id="execution-invalidated"),
        pytest.param("calendar", id="calendar-pin-changed"),
        pytest.param("metadata", id="metadata-changed-after-read"),
    ],
)
def test_controller_discards_result_if_request_identity_changes_before_native_callback(
    pair_controller, change: str,
):
    case = pair_controller
    worker = _start_read(case)
    case.reader.release.set()
    assert worker.wait(5000)
    assert case.controller.worker is worker

    if change == "selection":
        case.widget.run_list.item(1).setSelected(False)
        case.widget.run_list.item(2).setSelected(True)
        assert case.widget.selected_run_ids() == ["left", "third"]
    elif change == "generation":
        case.generation[0] += 1
    elif change == "execution":
        case.controller.invalidate_execution()
    elif change == "calendar":
        case.controller.external_sha.setText("c" * 64)
        assert case.controller._pin is None
    else:
        case.service._metadata_by_id["left"] = replace(
            case.service.runs[0], strategy_version="changed-after-read",
        )

    assert _wait_until(case.app, lambda: case.controller.worker is None)
    assert case.widget._period_pair_result is None
    assert case.widget._period_pair_busy is False


def test_controller_cancel_flag_does_not_mask_pair_integrity_error(pair_controller):
    case = pair_controller
    case.reader.error = FullPeriodPairReadErrorV1("synthetic pair integrity failure")
    worker = _start_read(case)

    case.controller.cancel()
    assert worker.is_cancel_requested() is True
    case.reader.release.set()
    assert worker.wait(5000)
    assert _wait_until(case.app, lambda: case.controller.worker is None)

    assert case.widget._period_pair_result is None
    assert "完整期間讀取失敗" in case.controller.status.text()
    assert "synthetic pair integrity failure" in case.controller.status.text()


def test_controller_cancel_after_native_finish_queued_does_not_apply_result(pair_controller):
    case = pair_controller
    worker = _start_read(case)
    case.reader.release.set()
    assert worker.wait(5000)
    assert case.controller.worker is worker

    case.controller.cancel()
    assert worker.is_cancel_requested() is True
    assert _wait_until(case.app, lambda: case.controller.worker is None)

    assert case.widget._period_pair_result is None
    assert "完整期間讀取已取消" in case.controller.status.text()


def test_controller_shutdown_requests_cancel_and_waits_for_natural_worker_exit(pair_controller):
    case = pair_controller
    worker = _start_read(case)
    safety_release = threading.Timer(3.0, case.reader.release.set)
    safety_release.daemon = True
    safety_release.start()
    try:
        started = time.monotonic()
        case.controller.begin_shutdown()
        assert time.monotonic() - started < 1.0
        assert worker.isRunning() is True
        assert worker.is_cancel_requested() is True
        assert case.controller.worker is worker
        assert case.reader.release.is_set() is False

        case.reader.release.set()
        assert worker.wait(5000)
        assert case.controller.worker is worker
        assert _wait_until(case.app, lambda: case.controller.worker is None)
        assert case.widget._period_pair_result is None
    finally:
        case.reader.release.set()
        safety_release.cancel()
