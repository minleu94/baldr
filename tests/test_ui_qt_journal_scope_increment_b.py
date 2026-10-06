"""Increment B：Journey Journal typed identity scope 的實際 widget 驗收。"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from app_module.decision_outcome_journey import (
    DecisionOutcomeJourney,
    JourneyLinkStatus,
    JourneyStatus,
    RecommendationCandidateRecord,
    RecommendationResultRecord,
    RecommendationSourceIdentity,
    _normalize_journal_entry,
)
from app_module.dtos.decision_continuity_dtos import DecisionIdentity
from app_module.research_session import ResearchStockContextDTO
from ui_qt.widgets.decision_outcome_journey_widget import DecisionOutcomeJourneyWidget


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


@pytest.fixture(scope="module", autouse=True)
def _qapp() -> QApplication:
    return _app()


def _context(stock_code: str) -> ResearchStockContextDTO:
    return ResearchStockContextDTO(
        stock_code=stock_code,
        stock_name="合成標的",
        result_id="result-1",
        decision_date="2026-09-14",
        data_date="2026-09-14",
        source_workspace="recommendation",
    )


def _result() -> RecommendationResultRecord:
    return RecommendationResultRecord(
        result_id="result-1",
        decision_date="2026-09-14",
        created_at="2026-09-14T09:00:00+00:00",
        source_identity=RecommendationSourceIdentity(
            result_id="result-1",
            decision_date="2026-09-14",
            source_provider_id="fixture",
        ),
        candidates=(
            RecommendationCandidateRecord(
                candidate_key=("result-1", "2330"),
                stock_code="2330",
                stock_name="標的A",
                recommendation_rank=1,
            ),
            RecommendationCandidateRecord(
                candidate_key=("result-1", "2317"),
                stock_code="2317",
                stock_name="標的B",
                recommendation_rank=2,
            ),
        ),
    )


def _raw_note(
    journal_id: str,
    *,
    identity: DecisionIdentity | None = None,
    linked_id: str = "result-1",
    source_id: str = "result-1",
) -> dict[str, object]:
    raw: dict[str, object] = {
        "journal_id": journal_id,
        "linked_type": "recommendation_result",
        "linked_id": linked_id,
        "source_id": source_id,
        "created_at": "2026-09-14T10:00:00+00:00",
        "body": journal_id,
    }
    if identity is not None:
        raw["decision_identity"] = identity.to_dict()
    return raw


class JourneyStub:
    def __init__(self, journey: DecisionOutcomeJourney) -> None:
        self.journey = journey

    def build(self, result_id: str, *, query_boundary: str | None = None) -> DecisionOutcomeJourney:
        del query_boundary
        assert result_id == self.journey.recommendation_result_id
        return self.journey


def _journey(records) -> DecisionOutcomeJourney:
    return DecisionOutcomeJourney(
        requested_result_id="result-1",
        status=JourneyStatus.LINKED,
        query_boundary=None,
        recommendation_result=_result(),
        journal_entries=tuple(records),
    )


def _wait_for(predicate, timeout_ms: int = 2_000) -> None:
    app = _app()
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    assert predicate()


def test_typed_note_isolated_by_stock_when_same_result_and_survives_switch_back() -> None:
    result = _result()
    note_a = _normalize_journal_entry(
        _raw_note(
            "note-a",
            identity=DecisionIdentity(result_id="result-1", stock_code="2330"),
        ),
        result,
        set(),
    )
    note_b = _normalize_journal_entry(
        _raw_note(
            "note-b",
            identity=DecisionIdentity(result_id="result-1", stock_code="2317"),
        ),
        result,
        set(),
    )
    widget = DecisionOutcomeJourneyWidget(JourneyStub(_journey((note_a, note_b))))
    widget.show()
    widget.set_context(_context("2330"))
    _wait_for(lambda: widget.journey is not None)

    assert widget.journal_table.model().rowCount() == 1
    assert widget.journal_table.model().index(0, 0).data(Qt.DisplayRole) == "note-a"

    widget.set_context(_context("2317"))
    _wait_for(
        lambda: widget._active_code == "2317"
        and widget.journal_table.model().rowCount() == 1
    )
    assert widget.journal_table.model().index(0, 0).data(Qt.DisplayRole) == "note-b"

    widget.set_context(_context("2330"))
    _wait_for(
        lambda: widget._active_code == "2330"
        and widget.journal_table.model().rowCount() == 1
    )
    assert widget.journal_table.model().index(0, 0).data(Qt.DisplayRole) == "note-a"
    _wait_for(lambda: not widget.is_busy())
    widget.close()


def test_legacy_shared_note_remains_explicitly_shared() -> None:
    result = _result()
    legacy = _normalize_journal_entry(
        _raw_note("legacy-shared"),
        result,
        set(),
    )
    assert legacy.decision_identity is None
    widget = DecisionOutcomeJourneyWidget(JourneyStub(_journey((legacy,))))
    widget.show()
    widget.set_context(_context("2317"))
    _wait_for(lambda: widget.journey is not None)

    assert widget.journal_table.model().rowCount() == 1
    assert widget.journal_table.model().index(0, 1).data(Qt.DisplayRole) == "本次推薦共用筆記"
    _wait_for(lambda: not widget.is_busy())
    widget.close()


def test_malformed_unknown_and_conflicting_typed_rows_never_show_as_linked() -> None:
    result = _result()
    unknown = _normalize_journal_entry(
        {
            **_raw_note(
                "note-unknown",
                identity=DecisionIdentity(
                    result_id="result-1",
                    stock_code="2330",
                    identity_status="unknown",
                ),
            ),
        },
        result,
        set(),
    )
    conflict = _normalize_journal_entry(
        {
            **_raw_note(
                "note-conflict",
                identity=DecisionIdentity(
                    result_id="result-1",
                    stock_code="2330",
                    identity_status="conflict",
                ),
            ),
        },
        result,
        set(),
    )
    malformed = _normalize_journal_entry(
        {
            **_raw_note("note-malformed"),
            "decision_identity": ["not-an-object"],
        },
        result,
        set(),
    )
    link_conflict = _normalize_journal_entry(
        _raw_note(
            "note-link-conflict",
            identity=DecisionIdentity(result_id="result-1", stock_code="2330"),
            source_id="other-result",
        ),
        result,
        set(),
    )

    assert unknown.link_status is JourneyLinkStatus.UNKNOWN
    assert conflict.link_status is JourneyLinkStatus.CONFLICT
    assert malformed.link_status is JourneyLinkStatus.CONFLICT
    assert link_conflict.link_status is JourneyLinkStatus.CONFLICT
    assert all(item.decision_identity is not None for item in (unknown, conflict, malformed, link_conflict))

    widget = DecisionOutcomeJourneyWidget(
        JourneyStub(_journey((unknown, conflict, malformed, link_conflict)))
    )
    widget.show()
    widget.set_context(_context("2330"))
    _wait_for(lambda: widget.journey is not None)
    assert widget.journal_table.model().rowCount() == 0
    _wait_for(lambda: not widget.is_busy())
    widget.close()
