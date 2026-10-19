from __future__ import annotations

import os
import sys
import time
from dataclasses import replace
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from app_module.decision_presentation import (
    PositionHealthPresentationDTO,
    PositionHealthReadModel,
)
from test_ui_qt_portfolio_view import (
    FakeChipService,
    FakeConditionMonitor,
    FakeConfig,
    FakeJournalService,
    _SequencedAsyncPortfolioService,
    make_portfolio_view,
)
from ui_qt.views.portfolio_view import PortfolioView


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


class _HealthReadService:
    def __init__(self, model: PositionHealthReadModel) -> None:
        self.model = model
        self.calls = 0

    def read_latest(self, *, max_age_days: int) -> PositionHealthReadModel:
        assert max_age_days == 1
        self.calls += 1
        return self.model


def _health_row(
    position_id: str = "paper-lot-2330",
    *,
    stock_code: str = "2330",
    decision_date: str = "2026-10-16",
    source_snapshot_id: str = "snapshot-paper-01",
) -> PositionHealthPresentationDTO:
    return PositionHealthPresentationDTO(
        position_id=position_id,
        stock_code=stock_code,
        decision_date=decision_date,
        available_at="2026-10-16T08:30:00+08:00",
        availability_by_source=(("market", "2026-10-16T08:30:00+08:00"),),
        source_status="passed",
        quality="observed",
        source_snapshot_id=source_snapshot_id,
        cohort_key="paper-main:cohort-01",
        previous_state="WATCH",
        proposed_state="WATCH",
        raw_proposed_state="WATCH",
        action_suitability="WATCH",
        condition_status="observed",
        thesis_status="observed",
        metrics_status="observed",
        entry_lineage_status="same_snapshot_verified",
        required_human_fields=(),
        reasons=("沿用原 Paper 評估；僅供研究覆盤。",),
        why="同一保存評估的部位識別。",
        why_not=("不構成自動交易指令。",),
        proposal_event_id="proposal-01",
        input_hash="a" * 64,
        policy_hash="b" * 64,
        source_trace=("fixture:verified-paper-health",),
        source_hashes=(("snapshot", "c" * 64),),
        review_required=True,
        research_only=True,
        auto_action_allowed=False,
        warnings=(),
        blockers=(),
    )


def _health_model(
    *,
    position_id: str = "paper-lot-2330",
    stock_code: str = "2330",
    decision_date: str = "2026-10-16",
    source_snapshot_id: str = "snapshot-paper-01",
    receipt_sha256: str = "f" * 64,
    result_sha256: str = "e" * 64,
    rows_sha256: str = "d" * 64,
    positions: tuple[PositionHealthPresentationDTO, ...] | None = None,
    **changes: object,
) -> PositionHealthReadModel:
    model = PositionHealthReadModel(
        schema_version="position-health-read-model.v1",
        status="passed",
        decision_date=decision_date,
        observed_at="2026-10-16T08:30:01+08:00",
        available_at="2026-10-16T08:30:00+08:00",
        source_status="passed",
        quality="observed",
        portfolio_id="paper-main",
        source_snapshot_id=source_snapshot_id,
        source_snapshot_rows_sha256=rows_sha256,
        cohort_key="paper-main:cohort-01",
        receipt_path="C:/fixture/paper-health/receipt.json",
        result_path="C:/fixture/paper-health/result.json",
        result_sha256=result_sha256,
        receipt_sha256=receipt_sha256,
        warnings=(),
        blockers=(),
        research_only=True,
        apply_transition=False,
        auto_action_allowed=False,
        broker_execution=False,
        formal_credit=False,
        positions=positions
        if positions is not None
        else (
            _health_row(
                position_id,
                stock_code=stock_code,
                decision_date=decision_date,
                source_snapshot_id=source_snapshot_id,
            ),
        ),
    )
    return replace(model, **changes)


def _wait_until(predicate, timeout_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        _app().processEvents()
        if predicate():
            return True
        QTest.qWait(10)
    _app().processEvents()
    return bool(predicate())


def _view(tmp_path, reader: _HealthReadService) -> PortfolioView:
    view = make_portfolio_view(
        tmp_path,
        position_health_read_service=reader,
    )
    return view


def test_explicit_focus_refreshes_exact_paper_row_and_preserves_manual_selection(
    tmp_path,
) -> None:
    _app()
    model = _health_model()
    reader = _HealthReadService(model)
    view = _view(tmp_path, reader)
    view.resize(1280, 900)
    view.show()
    _app().processEvents()
    assert view.select_stock("2317") is True
    assert view.selected_stock_code == "2317"
    assert view.portfolio_account_selector.currentData() == "manual"

    generation = view._refresh_generation
    read_count = reader.calls
    assert view.request_position_health_focus(model, "paper-lot-2330") is True
    assert view._refresh_generation == generation
    assert reader.calls == read_count

    view.refresh_all()

    assert view.portfolio_account_selector.currentData() == "paper"
    assert view.selected_stock_code == "2317"
    selected_rows = view.position_health_table.selectionModel().selectedRows()
    assert len(selected_rows) == 1
    assert view.position_health_model.row_at(selected_rows[0].row()) == model.positions[0]
    assert view.paper_health_group.isVisible()
    selected_rect = view.position_health_table.visualRect(selected_rows[0])
    assert selected_rect.isValid()
    assert view.position_health_table.viewport().rect().contains(selected_rect.center())
    assert "同一保存評估的部位識別" in view.position_health_detail_label.text()
    assert view._pending_position_health_focus is None
    view.begin_shutdown()


def test_explicit_focus_reveals_row_in_outer_scroll_viewport(tmp_path) -> None:
    _app()
    model = _health_model()
    view = _view(tmp_path, _HealthReadService(model))
    # 對應 1280×760 主視窗扣除導覽列與狀態列後的持倉區。
    view.resize(1084, 730)
    view.show()
    _app().processEvents()
    assert view.request_position_health_focus(model, model.positions[0].position_id)
    view.refresh_all()

    def selected_row_visible() -> bool:
        index = view.position_health_table.currentIndex()
        if not index.isValid():
            return False
        viewport = view.portfolio_advanced_scroll.viewport()
        center = view.position_health_table.visualRect(index).center()
        point = view.position_health_table.viewport().mapTo(viewport, center)
        return viewport.rect().contains(point)

    assert _wait_until(selected_row_visible)
    view.begin_shutdown()


@pytest.mark.parametrize("invalidate", ["generation", "account", "source", "selection"])
def test_late_reveal_does_not_scroll_after_context_changed(tmp_path, monkeypatch, invalidate) -> None:
    _app()
    model = _health_model()
    view = _view(tmp_path, _HealthReadService(model))
    view.show()
    assert view.request_position_health_focus(model, model.positions[0].position_id)
    view.refresh_all()
    generation = view._refresh_generation
    if invalidate == "generation":
        view._refresh_generation += 1
    elif invalidate == "account":
        view.portfolio_account_selector.setCurrentIndex(view.portfolio_account_selector.findData("manual"))
    elif invalidate == "source":
        view._position_health_read_model = replace(model, receipt_sha256="1" * 64)
    else:
        view.position_health_table.setCurrentIndex(view.position_health_model.index(-1, -1))
    calls = []
    monkeypatch.setattr(view.portfolio_advanced_scroll, "ensureVisible", lambda *args: calls.append(args))
    view._reveal_position_health_focus(generation, model, model.positions[0])
    _app().processEvents()
    assert calls == []
    view.begin_shutdown()


def test_missing_model_and_same_stock_different_position_id_do_not_fallback(
    tmp_path,
) -> None:
    _app()
    model = _health_model()
    reader = _HealthReadService(model)
    view = _view(tmp_path, reader)
    assert view.select_stock("2330") is True
    assert view.selected_stock_code == "2330"

    assert view.request_position_health_focus(
        cast(PositionHealthReadModel, None), "paper-lot-2330"
    ) is False
    assert view.request_position_health_focus(model, "default:2330") is False
    duplicated = replace(model, positions=(model.positions[0], model.positions[0]))
    assert view.request_position_health_focus(duplicated, "paper-lot-2330") is False
    manual_account_model = replace(model, portfolio_id="manual")
    assert view.request_position_health_focus(
        manual_account_model, "paper-lot-2330"
    ) is False
    unsafe_model = replace(model, auto_action_allowed=True)
    assert view.request_position_health_focus(unsafe_model, "paper-lot-2330") is False

    assert view.portfolio_account_selector.currentData() == "manual"
    assert view.selected_stock_code == "2330"
    assert view._pending_position_health_focus is None
    view.begin_shutdown()


@pytest.mark.parametrize(
    "updated_source",
    [
        lambda model: replace(model, receipt_sha256="1" * 64),
        lambda model: replace(model, result_sha256="2" * 64),
        lambda model: replace(model, source_snapshot_rows_sha256="3" * 64),
        lambda model: replace(
            model,
            decision_date="2026-10-17",
            positions=(replace(model.positions[0], decision_date="2026-10-17"),),
        ),
        lambda model: replace(
            model,
            source_snapshot_id="snapshot-paper-02",
            positions=(
                replace(model.positions[0], source_snapshot_id="snapshot-paper-02"),
            ),
        ),
    ],
    ids=("receipt-hash", "result-hash", "rows-hash", "decision-date", "snapshot"),
)
def test_refresh_does_not_focus_if_any_source_pin_changed(
    tmp_path,
    updated_source,
) -> None:
    _app()
    original = _health_model()
    reader = _HealthReadService(original)
    view = _view(tmp_path, reader)
    assert view.portfolio_account_selector.currentData() == "manual"
    assert view.request_position_health_focus(original, "paper-lot-2330") is True
    reader.model = updated_source(original)

    view.refresh_all()

    assert view.portfolio_account_selector.currentData() == "manual"
    assert view.position_health_table.selectionModel().selectedRows() == []
    assert "已改變" in view.position_health_detail_label.text()
    assert view._pending_position_health_focus is None
    view.begin_shutdown()


def test_delayed_previous_refresh_cannot_consume_next_generation_focus(tmp_path) -> None:
    _app()
    service = _SequencedAsyncPortfolioService(FakeConfig(tmp_path))
    model = _health_model()
    reader = _HealthReadService(model)
    view = PortfolioView(
        portfolio_service=service,
        journal_service=FakeJournalService(),
        condition_monitor=FakeConditionMonitor(),
        position_health_read_service=reader,
        async_refresh=True,
    )
    view._update_lifecycle_review = lambda *_args, **_kwargs: None
    view.chip_service = FakeChipService()

    assert _wait_until(service.read_started.is_set)
    previous_generation = view._refresh_generation
    assert view.request_position_health_focus(model, "paper-lot-2330") is True
    view.refresh_all()
    assert view._refresh_generation == previous_generation + 1
    service.release_first_read.set()

    assert _wait_until(
        lambda: service.calls >= 2
        and view._refresh_worker is None
        and view.portfolio_account_selector.currentData() == "paper"
    )
    assert reader.calls == 1
    assert view.position_health_model.row_at(0) == model.positions[0]
    assert view._pending_position_health_focus is None
    view.begin_shutdown()


def test_ordinary_refresh_does_not_auto_select_paper_health_row(tmp_path) -> None:
    _app()
    reader = _HealthReadService(_health_model())
    view = _view(tmp_path, reader)

    view.refresh_all()

    assert view.portfolio_account_selector.currentData() == "manual"
    assert view.position_health_table.selectionModel().selectedRows() == []
    assert view._pending_position_health_focus is None
    view.begin_shutdown()
