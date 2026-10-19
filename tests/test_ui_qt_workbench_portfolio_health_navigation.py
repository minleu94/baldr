from __future__ import annotations

import os
import sys
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_module.decision_presentation import (
    PositionHealthPresentationDTO,
    PositionHealthReadModel,
)
from app_module.workbench_dtos import WorkbenchDashboardDTO
from test_ui_qt_workbench_view import _dashboard_with_replay
from ui_qt.main import MainWindow
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _health_row(
    position_id: str | None,
    *,
    stock_code: str = "2330",
    entry_lineage_status: str = "same_snapshot_verified",
) -> PositionHealthPresentationDTO:
    return PositionHealthPresentationDTO(
        position_id=position_id,
        stock_code=stock_code,
        decision_date="2026-10-16",
        available_at="2026-10-16T08:30:00+08:00",
        availability_by_source=(("market", "2026-10-16T08:30:00+08:00"),),
        source_status="passed",
        quality="observed",
        source_snapshot_id="snapshot-paper-01",
        cohort_key="paper-main:cohort-01",
        previous_state="WATCH",
        proposed_state="WATCH",
        raw_proposed_state="WATCH",
        action_suitability="WATCH",
        condition_status="observed",
        thesis_status="observed",
        metrics_status="observed",
        entry_lineage_status=entry_lineage_status,
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
    positions: tuple[PositionHealthPresentationDTO, ...] | None = None,
    **changes: Any,
) -> PositionHealthReadModel:
    model = PositionHealthReadModel(
        schema_version="position-health-read-model.v1",
        status="passed",
        decision_date="2026-10-16",
        observed_at="2026-10-16T08:30:01+08:00",
        available_at="2026-10-16T08:30:00+08:00",
        source_status="passed",
        quality="observed",
        portfolio_id="paper-main",
        source_snapshot_id="snapshot-paper-01",
        source_snapshot_rows_sha256="d" * 64,
        cohort_key="paper-main:cohort-01",
        receipt_path="C:/fixture/paper-health/receipt.json",
        result_path="C:/fixture/paper-health/result.json",
        result_sha256="e" * 64,
        receipt_sha256="f" * 64,
        warnings=(),
        blockers=(),
        research_only=True,
        apply_transition=False,
        auto_action_allowed=False,
        broker_execution=False,
        formal_credit=False,
        positions=positions
        if positions is not None
        else (_health_row("paper-position-01"),),
    )
    return replace(model, **changes)


def _dashboard_with_health(
    health: PositionHealthReadModel | None,
) -> WorkbenchDashboardDTO:
    return replace(_dashboard_with_replay(), position_health=health)


class _StaticWorkbenchSourceService:
    def __init__(self, dashboard: WorkbenchDashboardDTO) -> None:
        self.dashboard = dashboard
        self.error: Exception | None = None

    def inspect(
        self,
        *,
        decision_date: str | None,
        replay_summary_json: str | None,
    ) -> WorkbenchDashboardDTO:
        del decision_date, replay_summary_json
        if self.error is not None:
            raise self.error
        return self.dashboard


def _select_health_row(view: UnifiedDecisionWorkbenchView, row: int) -> None:
    view.position_health_table.selectRow(row)
    # Directly invoke the same slot as currentRowChanged so the test does not
    # depend on platform-specific view focus behavior.
    view._show_position_health_row(view.position_health_model.index(row, 0))


def test_workbench_health_navigation_sends_explicit_second_position_identity() -> None:
    _app()
    model = _health_model(
        (
            _health_row("paper-lot-a"),
            _health_row("paper-lot-b"),
        )
    )
    calls: list[tuple[PositionHealthReadModel, str]] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_health(model),
        auto_refresh=False,
        navigate_to_portfolio_position_callback=lambda source, position_id: calls.append(
            (source, position_id)
        ),
    )

    assert view.position_health_open_portfolio_button.isEnabled() is False
    _select_health_row(view, 1)
    assert view.position_health_open_portfolio_button.isEnabled() is True
    view.position_health_open_portfolio_button.click()

    assert len(calls) == 1
    assert calls[0][0] is model
    assert calls[0][1] == "paper-lot-b"
    assert calls[0][1] != model.positions[1].stock_code


def test_workbench_health_refresh_clears_explicit_selection_and_old_source() -> None:
    _app()
    old_model = _health_model(
        (_health_row("paper-lot-a"), _health_row("paper-lot-b"))
    )
    new_model = replace(
        old_model,
        receipt_sha256="1" * 64,
        result_sha256="2" * 64,
        positions=(
            replace(old_model.positions[0], source_snapshot_id="snapshot-paper-02"),
            replace(old_model.positions[1], source_snapshot_id="snapshot-paper-02"),
        ),
        source_snapshot_id="snapshot-paper-02",
    )
    calls: list[tuple[PositionHealthReadModel, str]] = []
    source_service = _StaticWorkbenchSourceService(
        _dashboard_with_health(old_model)
    )
    view = UnifiedDecisionWorkbenchView(
        source_service=source_service,
        dashboard=_dashboard_with_health(old_model),
        auto_refresh=False,
        navigate_to_portfolio_position_callback=lambda source, position_id: calls.append(
            (source, position_id)
        ),
    )
    _select_health_row(view, 1)
    assert view._position_health_navigation_id == "paper-lot-b"

    source_service.dashboard = _dashboard_with_health(new_model)
    view.refresh_dashboard()

    assert view._position_health_navigation_source is new_model
    assert view._position_health_navigation_id is None
    assert view.position_health_open_portfolio_button.isEnabled() is False
    assert view._open_selected_position_health() is False
    assert calls == []
    # 刷新清掉舊選取；之後明選新來源必須只送出新版本。
    _select_health_row(view, 0)
    assert view.position_health_open_portfolio_button.isEnabled() is True
    view.position_health_open_portfolio_button.click()
    assert calls == [(new_model, "paper-lot-a")]
    assert calls[0][0] is new_model
    assert calls[0][0] is not old_model


def test_workbench_source_exception_revokes_pending_health_selection() -> None:
    _app()
    model = _health_model()
    source_service = _StaticWorkbenchSourceService(_dashboard_with_health(model))
    calls: list[tuple[PositionHealthReadModel, str]] = []
    view = UnifiedDecisionWorkbenchView(
        source_service=source_service,
        dashboard=_dashboard_with_health(model),
        auto_refresh=False,
        navigate_to_portfolio_position_callback=lambda source, position_id: calls.append(
            (source, position_id)
        ),
    )
    _select_health_row(view, 0)
    assert view.position_health_open_portfolio_button.isEnabled() is True

    source_service.error = RuntimeError("source refresh failed")
    view.refresh_dashboard()

    assert view._position_health_navigation_id is None
    assert view.position_health_open_portfolio_button.isEnabled() is False
    assert view._open_selected_position_health() is False
    assert calls == []


@pytest.mark.parametrize(
    "case",
    (
        "wrong_portfolio",
        "blocked_model",
        "missing_snapshot_rows_pin",
        "transition_enabled",
        "live_paper_action_enabled",
        "row_snapshot_mismatch",
        "duplicate_position_id",
        "missing_position_id",
        "missing_callback",
    ),
)
def test_workbench_health_navigation_refuses_unpinned_or_ambiguous_rows(case: str) -> None:
    _app()
    row = _health_row("paper-lot-a")
    model = _health_model()
    has_callback = case != "missing_callback"

    if case == "wrong_portfolio":
        model = replace(model, portfolio_id="user-declared")
    elif case == "blocked_model":
        model = replace(model, status="blocked")
    elif case == "missing_snapshot_rows_pin":
        model = replace(model, source_snapshot_rows_sha256=None)
    elif case == "transition_enabled":
        model = replace(model, apply_transition=True)
    elif case == "live_paper_action_enabled":
        model = replace(model, broker_execution=True, auto_action_allowed=True)
    elif case == "row_snapshot_mismatch":
        model = replace(
            model,
            positions=(replace(row, source_snapshot_id="snapshot-paper-other"),),
        )
    elif case == "duplicate_position_id":
        model = replace(model, positions=(row, replace(row, stock_code="2330")))
    elif case == "missing_position_id":
        model = replace(model, positions=(replace(row, position_id=None),))

    calls: list[tuple[PositionHealthReadModel, str]] = []
    callback = (
        (lambda source, position_id: calls.append((source, position_id)))
        if has_callback
        else None
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_health(model),
        auto_refresh=False,
        navigate_to_portfolio_position_callback=callback,
    )
    _select_health_row(view, 0)

    assert view.position_health_open_portfolio_button.isEnabled() is False
    assert view._open_selected_position_health() is False
    view.position_health_open_portfolio_button.click()
    assert calls == []


def test_workbench_close_revokes_pending_health_navigation() -> None:
    _app()
    model = _health_model()
    calls: list[tuple[PositionHealthReadModel, str]] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_health(model),
        auto_refresh=False,
        navigate_to_portfolio_position_callback=lambda source, position_id: calls.append(
            (source, position_id)
        ),
    )
    _select_health_row(view, 0)
    assert view.position_health_open_portfolio_button.isEnabled() is True

    view.begin_shutdown()

    assert view._open_selected_position_health() is False
    assert calls == []


def test_generic_portfolio_navigation_remains_available_without_position_callback() -> None:
    _app()
    model = _health_model()
    generic_calls: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_health(model),
        auto_refresh=False,
        navigate_to_portfolio_callback=lambda: generic_calls.append("portfolio"),
    )

    view.portfolio_button.click()
    _select_health_row(view, 0)

    assert generic_calls == ["portfolio"]
    assert view.position_health_open_portfolio_button.isEnabled() is False
    assert view._open_selected_position_health() is False


class _StatusBarStub:
    def __init__(self, events: list[tuple[object, ...]]) -> None:
        self.events = events

    def showMessage(self, message: str, timeout_ms: int) -> None:
        self.events.append(("status", message, timeout_ms))


def _main_stub(request_result: object):
    events: list[tuple[object, ...]] = []
    status_bar = _StatusBarStub(events)

    def request_focus(source: PositionHealthReadModel, position_id: str) -> object:
        events.append(("request", source, position_id))
        if isinstance(request_result, BaseException):
            raise request_result
        return request_result

    host = SimpleNamespace(
        portfolio_view=SimpleNamespace(request_position_health_focus=request_focus),
        statusBar=lambda: status_bar,
        _select_main_workspace=lambda workspace: events.append(("workspace", workspace)),
    )
    return host, events


def test_main_requests_portfolio_focus_before_switching_workspace() -> None:
    source = _health_model()
    host, events = _main_stub(True)

    result = MainWindow._open_workbench_position_health(
        host, source, "paper-position-01"
    )

    assert result is True
    assert events == [
        ("request", source, "paper-position-01"),
        ("workspace", "portfolio"),
    ]


@pytest.mark.parametrize("request_result", (False, RuntimeError("source changed")))
def test_main_refusal_or_focus_exception_never_switches_workspace(request_result) -> None:
    source = _health_model()
    host, events = _main_stub(request_result)

    if isinstance(request_result, BaseException):
        try:
            MainWindow._open_workbench_position_health(
                host, source, "paper-position-01"
            )
        except RuntimeError:
            pass
    else:
        assert (
            MainWindow._open_workbench_position_health(
                host, source, "paper-position-01"
            )
            is False
        )

    assert events[0] == ("request", source, "paper-position-01")
    assert not any(event[:1] == ("workspace",) for event in events)
    assert not any(event[:1] == ("write",) for event in events)
    assert not any(event[:1] == ("producer",) for event in events)
    if request_result is False:
        assert any(event[:1] == ("status",) for event in events)
