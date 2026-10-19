from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from app_module.research_session import ResearchStockContextDTO
from app_module.workbench_dtos import WorkbenchDailyEvidence
from ui_qt.main import MainWindow


def _daily() -> WorkbenchDailyEvidence:
    return WorkbenchDailyEvidence(
        status="observed",
        decision_date="2026-10-16",
        data_as_of_date="2026-10-15",
        headline="每日候選來源可讀。",
        next_action="逐檔查看既有來源。",
        market_summary="來源已提供。",
        industry_summary="來源已提供。",
        stock_summary="候選由每日來源提供。",
        watchlist_summary="只讀。",
        portfolio_summary="只讀。",
        candidate_symbols=("2330", "2603"),
        candidate_count=2,
        candidate_status="candidate",
        candidate_result_id="result-1",
        candidate_source_id="source-1",
        candidate_source_snapshot_id="snapshot-1",
        candidate_data_date="2026-10-15",
    )


def _context() -> ResearchStockContextDTO:
    return ResearchStockContextDTO(
        stock_code="2603",
        decision_date="2026-10-16",
        data_date="2026-10-15",
        result_id="result-1",
        source_id="source-1",
        source_snapshot_id="snapshot-1",
        source_kind="scheduled_recommendation",
        source_label="每日推薦研究候選",
        source_workspace="workbench",
    )


class _StatusBarStub:
    def __init__(self, events: list[tuple[object, ...]]) -> None:
        self._events = events

    def showMessage(self, message: str, timeout_ms: int) -> None:
        self._events.append(("status", message, timeout_ms))


def _host(
    *,
    daily: WorkbenchDailyEvidence | None = None,
    selected_code: str | None = "2603",
    openable: bool = True,
    with_workbench: bool = True,
    with_selector: bool = True,
) -> tuple[SimpleNamespace, list[tuple[object, ...]]]:
    events: list[tuple[object, ...]] = []
    workbench = SimpleNamespace(
        _daily_investment_evidence=_daily() if daily is None else daily,
        _daily_candidate_selection_is_openable=lambda: openable,
    )
    if with_selector:
        workbench.daily_candidate_selector = SimpleNamespace(
            currentData=lambda: selected_code
        )
    host = SimpleNamespace(
        _coerce_stock_research_context=lambda value: MainWindow._coerce_stock_research_context(None, value),
        workbench_view=workbench if with_workbench else None,
        statusBar=lambda: _StatusBarStub(events),
        _select_main_workspace=lambda workspace: events.append(("workspace", workspace)),
    )
    return host, events


def _assert_rejected(events: list[tuple[object, ...]]) -> None:
    assert not any(event[0] == "workspace" for event in events)
    status_events = [event for event in events if event[0] == "status"]
    assert len(status_events) == 1
    assert "首頁原候選已改變或不可讀" in str(status_events[0][1])


def test_returns_to_workbench_only_for_the_same_open_daily_candidate() -> None:
    host, events = _host()

    MainWindow._return_to_research_source(host, _context())

    assert events == [("workspace", "workbench")]


@pytest.mark.parametrize("outcome", [True, False, "error"])
def test_saved_result_bridge_switches_workspace_only_after_exact_read_is_queued(outcome) -> None:
    host, events = _host()

    def open_saved(result_id):
        events.append(("open_saved", result_id))
        if outcome == "error":
            raise ValueError("來源不可用")
        return outcome

    host.recommendation_view = SimpleNamespace(open_saved_recommendation_result=open_saved)
    accepted = MainWindow._open_workbench_saved_recommendation(host, "exact-result")
    assert events[0] == ("open_saved", "exact-result")
    assert accepted is (outcome is True)
    assert ("workspace", "recommendation") in events if outcome is True else not any(
        event[0] == "workspace" for event in events
    )


@pytest.mark.parametrize(
    ("identity_field", "changed_value"),
    (
        ("result_id", "result-2"),
        ("source_id", "source-2"),
        ("source_snapshot_id", "snapshot-2"),
        ("decision_date", "2026-10-17"),
        ("data_date", "2026-10-14"),
        ("stock_code", "2330"),
    ),
    ids=(
        "changed-run",
        "changed-source",
        "changed-snapshot",
        "changed-decision-date",
        "changed-data-date",
        "changed-stock",
    ),
)
def test_rejects_return_when_any_selected_candidate_identity_changed(
    identity_field: str,
    changed_value: str,
) -> None:
    host, events = _host()
    context = replace(_context(), **{identity_field: changed_value})

    MainWindow._return_to_research_source(host, context)

    _assert_rejected(events)


@pytest.mark.parametrize(
    "host_state",
    ("unreadable", "missing-workbench", "missing-daily-evidence", "missing-selector"),
)
def test_rejects_return_when_homepage_candidate_is_not_openable(
    host_state: str,
) -> None:
    host, events = _host(
        openable=host_state != "unreadable",
        with_workbench=host_state != "missing-workbench",
        daily=None if host_state == "missing-daily-evidence" else _daily(),
        with_selector=host_state != "missing-selector",
    )
    if host_state == "missing-daily-evidence":
        host.workbench_view._daily_investment_evidence = None

    MainWindow._return_to_research_source(host, _context())

    _assert_rejected(events)
