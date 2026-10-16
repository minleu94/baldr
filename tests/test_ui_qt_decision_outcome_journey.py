"""DecisionOutcomeJourney widget 的唯讀、競態與真實資料驗收。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from decimal import Decimal
import os
from pathlib import Path
import sys
import time
from types import MappingProxyType
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from app_module.decision_outcome_journey import (
    DecisionOutcomeJourney,
    EvidenceEventRecord,
    JourneyLinkStatus,
    JourneyStatus,
    JournalEntryRecord,
    OutcomeMaturityRecord,
    PortfolioLedgerRecord,
    RecommendationCandidateRecord,
    RecommendationResultRecord,
    RecommendationSourceIdentity,
)
from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.dtos.decision_continuity_dtos import DecisionIdentity
from app_module.journal_service import JournalService
from app_module.personalization_contract import (
    PersonalRecommendationChoice,
    PersonalRecommendationOverrideReason,
)
from app_module.recommendation.personal_use_policy import (
    RecommendationPersonalUsePolicyV1,
)
from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_dtos import StockResearchReportDTO
from ui_qt.theme import build_global_stylesheet
from ui_qt.theme.fonts import (
    preferred_qt_chinese_font_family,
    register_qt_chinese_fonts,
)
from ui_qt.widgets.decision_outcome_journey_widget import (
    DecisionOutcomeJourneyWidget,
)
from ui_qt.views.stock_research_report_view import StockResearchReportDialog


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


@pytest.fixture(scope="module", autouse=True)
def _qapp_fixture() -> Iterator[QApplication]:
    """先建立並保留 QApplication，再讓任何 fixture 建立 QWidget。"""

    instance = _app()
    # Match the production theme's Fusion/CJK setup without importing the
    # heavyweight MainWindow module in this isolated widget test.
    instance.setStyle("Fusion")
    families = register_qt_chinese_fonts()
    preferred_family = preferred_qt_chinese_font_family(families)
    if preferred_family:
        instance.setFont(QFont(preferred_family, instance.font().pointSize()))
    instance.setStyleSheet(build_global_stylesheet())
    yield instance


def _wait_for(predicate, timeout_ms: int = 3_000) -> None:
    app = _app()
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    assert predicate()


def _journey(
    *,
    result_id: str = "result-1",
    stock_code: str = "2330",
    outcome_status: str | None = "insufficient_future_data",
    windows: tuple[int, ...] = (20, 5, 60, 10),
) -> DecisionOutcomeJourney:
    candidate_key = (result_id, stock_code)
    identity = RecommendationSourceIdentity(
        result_id=result_id,
        decision_date="2026-09-14",
        source_provider_id="fixture.provider",
    )
    result = RecommendationResultRecord(
        result_id=result_id,
        decision_date="2026-09-14",
        created_at="2026-09-14T09:00:00+00:00",
        source_identity=identity,
        candidates=(
            RecommendationCandidateRecord(
                candidate_key=candidate_key,
                stock_code=stock_code,
                stock_name="合成標的",
                recommendation_rank=1,
            ),
        ),
    )
    event_id = f"event-{result_id}"
    event = EvidenceEventRecord(
        event_id=event_id,
        event_hash=f"hash-{event_id}",
        event_type="recommendation_included",
        event_family="recommendation",
        source_type="recommendation_result",
        source_id=result_id,
        source_snapshot_id=result_id,
        symbol=stock_code,
        decision_date="2026-09-14",
        event_date="2026-09-14",
        as_of_date="2026-09-14",
        available_date="2026-09-14T09:01:00+00:00",
        source_version="fixture-v1",
        created_at="2026-09-14T09:01:00+00:00",
        candidate_key=candidate_key,
        link_status=JourneyLinkStatus.LINKED,
    )
    maturity = tuple(
        OutcomeMaturityRecord(
            candidate_key=candidate_key,
            event_id=event_id,
            window_days=window,
            status=JourneyLinkStatus.LINKED,
            outcome_id=f"outcome-{window}",
            outcome_status=outcome_status,
            reason="outcome fixture status",
        )
        for window in windows
    )
    journal = JournalEntryRecord(
        journal_id="journal-1",
        linked_type="recommendation_result",
        linked_id=result_id,
        thesis_id="thesis-1",
        source_type="recommendation_result",
        source_id=result_id,
        source_snapshot_hash=None,
        created_at="2026-09-14T10:00:00+00:00",
        updated_at=None,
        relationship_type=None,
        relationship_target_id=None,
        link_status=JourneyLinkStatus.LINKED,
    )
    ledger = PortfolioLedgerRecord(
        record_id="ledger-1",
        event_type="trade",
        source_namespace="manual",
        occurred_at="2026-09-15T09:30:00+00:00",
        created_at="2026-09-15T09:31:00+00:00",
        stock_code=stock_code,
        side="buy",
        quantity=100,
        price=Decimal("600.00"),
        fees=Decimal("1.20"),
        taxes=Decimal("0.00"),
        source_id=result_id,
        source_snapshot_hash=None,
        thesis_id="thesis-1",
        reverses_event_id=None,
        reason=None,
        research_only=False,
        broker_fill_proven=False,
        execution_semantics="user_recorded_event_broker_fill_unproven",
        link_status=JourneyLinkStatus.LINKED,
    )
    return DecisionOutcomeJourney(
        requested_result_id=result_id,
        status=JourneyStatus.LINKED,
        query_boundary=None,
        recommendation_result=result,
        evidence_events=(event,),
        outcome_maturity=maturity,
        journal_entries=(journal,),
        portfolio_ledger_events=(ledger,),
    )


class JourneyServiceStub:
    def __init__(
        self,
        journeys: Mapping[str, DecisionOutcomeJourney],
        *,
        delays: Mapping[str, float] | None = None,
        error: str | None = None,
    ) -> None:
        self.journeys = dict(journeys)
        self.delays = dict(delays or {})
        self.error = error
        self.calls: list[str] = []

    def build(
        self,
        result_id: str,
        *,
        query_boundary: str | None = None,
    ) -> DecisionOutcomeJourney:
        del query_boundary
        self.calls.append(result_id)
        delay = self.delays.get(result_id, 0.0)
        if delay:
            time.sleep(delay)
        if self.error is not None:
            raise RuntimeError(self.error)
        return self.journeys[result_id]


class ReportServiceStub:
    def read_report(self, stock_code: str, *, context=None, cancel_callback=None) -> StockResearchReportDTO:
        del context, cancel_callback
        return StockResearchReportDTO(
            stock_code=stock_code,
            stock_name="合成標的",
            as_of="2026-09-14",
        )


def _context(stock_code: str = "2330", result_id: str = "result-1") -> ResearchStockContextDTO:
    return ResearchStockContextDTO(
        stock_code=stock_code,
        stock_name="合成標的",
        decision_date="2026-09-14",
        data_date="2026-09-14",
        result_id=result_id,
        source_id=result_id,
        source_label="合成推薦來源",
        source_workspace="recommendation",
    )


def _choice_history_fixture(
    *,
    choice: str,
    action_at: str,
    result_id: str = "result-1",
    stock_code: str = "2330",
    snapshot_id: str = "universe-snapshot-1",
    snapshot_hash: str = "sha256:" + "f" * 64,
    canonical_hash: str = "sha256:" + "d" * 64,
    artifact_hash: str = "sha256:" + "e" * 64,
    link_status: JourneyLinkStatus = JourneyLinkStatus.LINKED,
    journal_id: str | None = None,
) -> JournalEntryRecord:
    override_reason = (
        PersonalRecommendationOverrideReason(
            code="new_information",
            detail="研究後發現原判斷條件已改變。",
        )
        if choice == "override"
        else None
    )
    typed_choice = PersonalRecommendationChoice(
        result_id=result_id,
        stock_code=stock_code,
        decision_date="2026-09-14",
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot_hash,
        canonical_payload_hash=canonical_hash,
        raw_artifact_sha256=artifact_hash,
        choice=choice,
        requested_mode="rule_only",
        effective_mode="rule_only",
        action_at=action_at,
        recorded_at=action_at,
        request_id=f"choice-{choice}-{action_at}",
        policy_snapshot=RecommendationPersonalUsePolicyV1.default_rule_only(
            "local-profile"
        ).to_dict(),
        override_reason=override_reason,
    )
    payload = _freeze_test_payload(
        {"personal_recommendation_choice": typed_choice.to_dict()}
    )
    return JournalEntryRecord(
        journal_id=journal_id or f"journal-{choice}-{action_at}",
        linked_type="recommendation_result",
        linked_id="result-1",
        thesis_id=None,
        source_type="personal_recommendation_choice",
        source_id="result-1",
        source_snapshot_hash=snapshot_hash,
        created_at=action_at,
        updated_at=None,
        relationship_type=None,
        relationship_target_id=None,
        link_status=link_status,
        original_payload=payload,
        decision_identity=DecisionIdentity(
            result_id=result_id,
            stock_code=stock_code,
            source_snapshot_id=snapshot_id,
            source_snapshot_hash=snapshot_hash,
            decision_date="2026-09-14",
            identity_status="linked",
        ),
    )


def _freeze_test_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_test_payload(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_test_payload(item) for item in value)
    return value


def _journey_with_choice_history(
    entries: tuple[JournalEntryRecord, ...],
) -> DecisionOutcomeJourney:
    base = _journey()
    snapshot_hash = "sha256:" + "f" * 64
    identity = replace(
        base.recommendation_result.source_identity,
        universe_snapshot_id="universe-snapshot-1",
        universe_snapshot_hash=snapshot_hash,
    )
    result = replace(
        base.recommendation_result,
        source_identity=identity,
        canonical_integrity_verified=True,
        canonical_payload_hash="sha256:" + "d" * 64,
        raw_artifact_sha256="sha256:" + "e" * 64,
    )
    return replace(base, recommendation_result=result, journal_entries=entries)


def test_missing_result_id_is_explicitly_unlinked_without_service_call() -> None:
    service = JourneyServiceStub({"result-1": _journey()})
    widget = DecisionOutcomeJourneyWidget(
        service,
        _context(result_id=""),
    )
    widget.show()
    _app().processEvents()

    assert service.calls == []
    assert "未連結" in widget.status_label.text()
    assert "同股同日" in widget.status_label.text()
    assert widget.maturity_table.model().rowCount() == 0
    widget.close()


def test_valid_context_renders_candidate_maturity_and_separates_personal_records() -> None:
    service = JourneyServiceStub({"result-1": _journey()})
    widget = DecisionOutcomeJourneyWidget(service, _context())
    widget.resize(980, 720)
    widget.show()
    _wait_for(lambda: widget.journey is not None)

    assert "載入中" not in widget.identity_label.text()
    assert widget.identity_label.text().startswith("2330 合成標的")
    assert widget.status_badge.text() == "注意"
    assert "尚待結果成熟" in widget.status_label.text()
    maturity_model = widget.maturity_table.model()
    assert maturity_model.rowCount() == 4
    horizons = [
        maturity_model.index(row, 0).data(Qt.DisplayRole)
        for row in range(maturity_model.rowCount())
    ]
    assert horizons == [
        "5個交易日",
        "10個交易日",
        "20個交易日",
        "60個交易日",
    ]
    assert all(
        maturity_model.index(row, 1).data(Qt.DisplayRole) == "已連結"
        for row in range(maturity_model.rowCount())
    )
    assert all(
        maturity_model.index(row, 2).data(Qt.DisplayRole)
        == "待成熟（未有足夠未來資料）"
        for row in range(maturity_model.rowCount())
    )
    assert widget.evidence_table.model().rowCount() == 1
    assert widget.journal_table.model().rowCount() == 1
    assert widget.portfolio_table.model().rowCount() == 1
    assert not widget.technical_details.isVisible()
    assert "前瞻報酬" in widget.safety_label.text()
    assert "與研究結果分開" in widget.portfolio_table.parent().title()
    widget.close()


def test_maturity_reason_is_plain_language_without_changing_source_status() -> None:
    original = _journey(outcome_status="ready")
    journey = replace(
        original,
        outcome_maturity=tuple(
            replace(item, reason="outcome_available_at_query_boundary")
            if item.window_days == 5 else item
            for item in original.outcome_maturity
        ),
    )
    widget = DecisionOutcomeJourneyWidget(JourneyServiceStub({"result-1": journey}), _context())
    widget.show()
    _wait_for(lambda: widget.journey is not None)
    model = widget.maturity_table.model()
    assert model.index(0, 2).data() == "來源已標示 ready"
    assert model.index(0, 3).data() == "已取得該期限的來源結果；是否成熟請看結果狀態。"
    assert next(item for item in widget.journey.outcome_maturity if item.window_days == 5).reason == "outcome_available_at_query_boundary"
    widget.close()


def test_personal_choice_history_is_read_only_ordered_and_keeps_pending_visible() -> None:
    context = replace(
        _context(),
        identity_status="linked",
        source_snapshot_id="universe-snapshot-1",
        source_snapshot_hash="sha256:" + "f" * 64,
    )
    entries = (
        _choice_history_fixture(
            choice="override",
            action_at="2026-09-14T10:02:00+00:00",
        ),
        _choice_history_fixture(
            choice="adopt",
            action_at="2026-09-14T10:00:00+00:00",
        ),
        _choice_history_fixture(
            choice="reject",
            action_at="2026-09-14T10:01:00+00:00",
        ),
    )
    journey = _journey_with_choice_history(entries)
    widget = DecisionOutcomeJourneyWidget(
        JourneyServiceStub({"result-1": journey}),
        context,
    )
    widget.show()
    _wait_for(lambda: widget.journey is not None)

    model = widget.personal_choice_table.model()
    assert model.rowCount() == 3
    assert [model.index(row, 1).data() for row in range(3)] == [
        "個人採用",
        "個人拒絕",
        "推翻原建議",
    ]
    action_times = [model.index(row, 3).data() for row in range(3)]
    assert action_times == sorted(action_times)
    assert model.index(2, 2).data() == "研究後發現原判斷條件已改變。"
    assert all(model.index(row, 0).data() == "result-1:2330" for row in range(3))
    assert all(model.index(row, 4).data() == "已連結" for row in range(3))
    assert "尚待結果成熟" in widget.status_label.text()
    assert all(
        widget.maturity_table.model().index(row, 2).data()
        == "待成熟（未有足夠未來資料）"
        for row in range(widget.maturity_table.model().rowCount())
    )
    widget.close()


def test_personal_choice_history_hides_other_result_artifact_snapshot_and_conflict() -> None:
    context = replace(
        _context(),
        identity_status="linked",
        source_snapshot_id="universe-snapshot-1",
        source_snapshot_hash="sha256:" + "f" * 64,
    )
    entries = (
        _choice_history_fixture(
            choice="adopt",
            action_at="2026-09-14T10:00:00+00:00",
            result_id="result-other",
            journal_id="journal-other-result",
        ),
        _choice_history_fixture(
            choice="reject",
            action_at="2026-09-14T10:01:00+00:00",
            snapshot_id="universe-snapshot-other",
            snapshot_hash="sha256:" + "a" * 64,
            journal_id="journal-other-snapshot",
        ),
        _choice_history_fixture(
            choice="override",
            action_at="2026-09-14T10:02:00+00:00",
            artifact_hash="sha256:" + "c" * 64,
            journal_id="journal-other-artifact",
        ),
        _choice_history_fixture(
            choice="adopt",
            action_at="2026-09-14T10:03:00+00:00",
            link_status=JourneyLinkStatus.CONFLICT,
            journal_id="journal-conflict",
        ),
    )
    journey = _journey_with_choice_history(entries)
    widget = DecisionOutcomeJourneyWidget(
        JourneyServiceStub({"result-1": journey}),
        context,
    )
    widget.show()
    _wait_for(lambda: widget.journey is not None)

    assert widget.personal_choice_table.model().rowCount() == 0
    assert "尚待結果成熟" in widget.status_label.text()
    assert widget.maturity_table.model().rowCount() == 4
    assert all(
        widget.maturity_table.model().index(row, 2).data()
        == "待成熟（未有足夠未來資料）"
        for row in range(widget.maturity_table.model().rowCount())
    )
    widget.close()


def test_recommendation_journey_labels_universe_and_market_facts_separately() -> None:
    journey = _journey()
    identity = replace(
        journey.recommendation_result.source_identity,
        source_snapshot_id=None,
        source_snapshot_hash=None,
        universe_snapshot_id="universe-snapshot-01",
        universe_snapshot_hash="sha256:" + "a" * 64,
        market_data_as_of_date="2026-09-25",
        market_data_source_id="market-provider-01",
        market_data_fingerprint="b" * 64,
    )
    journey = replace(
        journey,
        recommendation_result=replace(
            journey.recommendation_result,
            source_identity=identity,
        ),
    )
    context = replace(
        _context(),
        decision_date="2026-09-28",
        data_date="2026-09-25",
        source_snapshot_id="universe-snapshot-01",
        source_snapshot_hash="sha256:" + "a" * 64,
        source_workspace="recommendation",
    )
    widget = DecisionOutcomeJourneyWidget(
        JourneyServiceStub({"result-1": journey}), context
    )
    widget.show()
    _wait_for(lambda: widget.journey is not None)

    assert "Universe snapshot：universe-snapshot-01" in widget.context_label.text()
    assert "決策日：2026-09-28｜資料日：2026-09-25" in widget.context_label.text()
    identity_text = widget.technical_identity_label.text()
    assert "行情資料日：2026-09-25" in identity_text
    assert "行情來源：market-provider-01" in identity_text
    assert "行情指紋：sha256:" + "b" * 64 in identity_text
    assert "來源 snapshot：未知" in identity_text
    assert "Universe snapshot：universe-snapshot-01" in identity_text
    widget.close()


def test_horizon_conflict_takes_precedence_over_pending_status() -> None:
    base = _journey()
    mixed_maturity = tuple(
        replace(
            item,
            status=JourneyLinkStatus.CONFLICT,
            reason="duplicate outcome fixture",
        )
        if item.window_days == 5
        else item
        for item in base.outcome_maturity
    )
    service = JourneyServiceStub(
        {"result-1": replace(base, outcome_maturity=mixed_maturity)}
    )
    widget = DecisionOutcomeJourneyWidget(service, _context())
    widget.show()
    _wait_for(lambda: widget.journey is not None)

    assert widget.status_badge.text() == "衝突"
    assert "尚待結果成熟" in widget.status_label.text()
    assert "Journey identity" in widget.status_label.text()
    widget.close()


def test_shared_run_note_is_labeled_and_a_only_note_is_hidden_for_b() -> None:
    base = _journey(
        result_id="result-multi",
        stock_code="2330",
        outcome_status="ready",
        windows=(5, 10, 20, 60),
    )
    result = replace(
        base.recommendation_result,
        candidates=(
            *base.recommendation_result.candidates,
            RecommendationCandidateRecord(
                candidate_key=("result-multi", "1101"),
                stock_code="1101",
                stock_name="第二標的",
                recommendation_rank=2,
            ),
        ),
    )
    a_only_note = replace(
        base.journal_entries[0],
        journal_id="journal-a-only",
        linked_type="trade",
        linked_id="ledger-1",
        source_id="result-multi",
        source_snapshot_hash="snapshot-shared",
        thesis_id="thesis-a-only",
    )
    journey = replace(
        base,
        recommendation_result=result,
        journal_entries=(base.journal_entries[0], a_only_note),
    )
    service = JourneyServiceStub({"result-multi": journey})
    widget = DecisionOutcomeJourneyWidget(
        service,
        _context("1101", "result-multi"),
    )
    widget.show()
    _wait_for(lambda: widget.journey is not None)

    model = widget.journal_table.model()
    assert model.rowCount() == 1
    assert model.index(0, 0).data() == "journal-1"
    assert model.index(0, 1).data() == "本次推薦共用筆記"
    assert "journal-a-only" not in {
        model.index(row, 0).data() for row in range(model.rowCount())
    }

    widget.set_context(_context("2330", "result-multi"))
    _wait_for(
        lambda: widget.journey is not None
        and widget._active_code == "2330"
        and widget.journal_table.model().rowCount() == 2
    )
    scopes = {
        widget.journal_table.model().index(row, 1).data()
        for row in range(widget.journal_table.model().rowCount())
    }
    assert scopes == {"本次推薦共用筆記", "此股票關聯筆記"}
    widget.close()


def test_switching_stock_and_result_discards_old_response() -> None:
    service = JourneyServiceStub(
        {
            "result-a": _journey(result_id="result-a", stock_code="2330"),
            "result-b": _journey(result_id="result-b", stock_code="1101"),
        },
        delays={"result-a": 0.15, "result-b": 0.01},
    )
    widget = DecisionOutcomeJourneyWidget(service, _context("2330", "result-a"))
    widget.show()
    QTest.qWait(15)
    widget.set_context(_context("1101", "result-b"))
    _wait_for(lambda: widget.journey is not None and widget.journey.recommendation_result_id == "result-b")
    assert widget._active_code == "1101"
    assert widget.identity_label.text().startswith("1101")
    _wait_for(lambda: not widget.is_busy())
    assert widget.journey is not None
    assert widget.journey.recommendation_result_id == "result-b"
    widget.close()


def test_load_error_keeps_retry_available_and_recovers_to_success(
    tmp_path: Path,
) -> None:
    service = JourneyServiceStub({"result-1": _journey()}, error="synthetic read failure")
    config = SimpleNamespace(
        output_root=tmp_path / "output",
        resolve_output_path=lambda name: tmp_path / "output" / name,
    )
    controller = DecisionContinuityController(JournalService(config))
    widget = DecisionOutcomeJourneyWidget(
        service,
        _context(),
        continuity_controller=controller,
    )
    widget.show()
    _wait_for(lambda: "讀取失敗" in widget.status_label.text())

    assert "synthetic read failure" in widget.status_label.text()
    assert "載入中" not in widget.identity_label.text()
    assert widget.reload_button.isEnabled()
    assert widget.isEnabled()
    assert widget.maturity_table.model().rowCount() == 0

    controls = widget.continuity_controls
    assert controls is not None
    assert not controls.accept_button.isEnabled()
    assert not controls.review_button.isEnabled()

    # A fresh exact request must be able to recover after the prior request
    # failed; the stale failure must not leave candidate actions disabled.
    service.error = None
    widget.set_context(_context())
    _wait_for(lambda: widget.journey is not None)
    assert controls.identity is not None
    assert controls.identity.candidate_key == ("result-1", "2330")
    assert controls.state is not None
    assert controls.accept_button.isEnabled()
    assert controls.review_button.isEnabled()
    widget.close()


def test_stock_report_dialog_exposes_journey_tab_and_updates_context() -> None:
    service = JourneyServiceStub(
        {
            "result-1": _journey(),
            "result-2": _journey(result_id="result-2", stock_code="1101"),
        }
    )
    dialog = StockResearchReportDialog(
        ReportServiceStub(),
        _context(),
        journey_service=service,
    )
    dialog.show()
    _wait_for(
        lambda: dialog.journey_view is not None
        and dialog.journey_view.journey is not None
    )

    assert dialog.dialog_tabs.count() == 2
    assert dialog.dialog_tabs.tabText(1) == "決策 → 結果"
    assert dialog.journey_view is not None
    dialog.set_context(_context("1101", "result-2"))
    _wait_for(
        lambda: dialog.journey_view is not None
        and dialog.journey_view.journey is not None
        and dialog.journey_view.journey.recommendation_result_id == "result-2"
    )
    assert dialog.report_view._active_code == "1101"
    dialog.close()


def test_internal_report_stock_switch_rebinds_journey_and_rejects_late_a_callback() -> None:
    # 報告頁可能在內部切換股票，外層對話框不一定會收到新的 set_context 呼叫。
    # Journey 分頁必須跟隨該 exact context；同一結果沒有 B 候選時也必須安全收斂。
    service = JourneyServiceStub(
        {"result-1": _journey(result_id="result-1", stock_code="2330")},
        delays={"result-1": 0.15},
    )
    dialog = StockResearchReportDialog(
        ReportServiceStub(),
        _context("2330", "result-1"),
        journey_service=service,
    )
    dialog.show()
    QTest.qWait(15)

    dialog.report_view._load_stock("1101")
    assert dialog.windowTitle() == "個股研究報告｜1101"
    assert dialog.journey_view is not None
    _wait_for(
        lambda: dialog.journey_view is not None
        and dialog.journey_view.context is not None
        and dialog.journey_view.context.stock_code == "1101"
        and dialog.journey_view._active_code == "1101"
    )
    journey = dialog.journey_view
    assert journey is not None
    assert journey._active_result_id == "result-1"
    assert journey.identity_label.text().startswith("1101")

    _wait_for(lambda: "沒有 1101 的候選資料" in journey.status_label.text())
    assert journey.maturity_table.model().rowCount() == 0
    assert "candidate Evidence" in journey._empty_labels["evidence"].text()
    request_id = journey._request_id
    journey._on_error(request_id - 1, "2330", "result-1", "late A callback")
    assert "late A callback" not in journey.status_label.text()
    assert journey.identity_label.text().startswith("1101")
    assert journey.context is not None
    assert journey.context.stock_code == "1101"

    _wait_for(lambda: not dialog.is_busy())
    dialog.close()


def test_official_scheduled_result_renders_cjk_journey_screenshot_when_available() -> None:
    opt_in = os.environ.get(
        "RUN_DECISION_OUTCOME_JOURNEY_REAL_SMOKE", ""
    ).strip().lower()
    if opt_in not in {"1", "true", "yes", "on"}:
        pytest.skip("real scheduled Qt smoke requires explicit opt-in")
    output_root = Path(
        os.environ.get("OUTPUT_ROOT", "D:/Min/Python/Project/FA_Data/output")
    ).expanduser().resolve()
    data_root = Path(
        os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data")
    ).expanduser().resolve()
    result_id = "scheduled_rec_20260914_051003"
    result_path = output_root / "recommendation" / "runs" / f"{result_id}.json"
    evidence_path = data_root / "sqlite" / "twstock.db"
    if not result_path.is_file() or not evidence_path.is_file():
        pytest.fail("real scheduled recommendation/evidence sources are required for opt-in smoke")

    from app_module.decision_outcome_journey import DecisionOutcomeJourneyService

    service = DecisionOutcomeJourneyService.from_paths(
        output_root=output_root,
        evidence_db_path=evidence_path,
        journal_path=output_root / "portfolio" / "journal_entries.jsonl",
        portfolio_trades_path=output_root / "portfolio" / "trades.jsonl",
    )
    assert service.evidence_reader is not None
    assert service.evidence_reader.repository.read_only is True
    widget = DecisionOutcomeJourneyWidget(
        service,
        ResearchStockContextDTO(
            stock_code="1528",
            stock_name="恩德",
            result_id=result_id,
            decision_date="2026-09-14",
            source_id=result_id,
            source_label="DefaultRecommendationMarketDataProvider",
            source_workspace="recommendation",
        ),
    )
    widget.resize(1_180, 820)
    widget.show()
    try:
        _wait_for(
            lambda: widget.journey is not None or "讀取失敗" in widget.status_label.text(),
            timeout_ms=12_000,
        )
    except AssertionError as exc:
        worker_state = tuple(
            (item.isRunning(), item.isFinished()) for item in widget._workers
        )
        raise AssertionError(
            f"{exc}; status={widget.status_label.text()!r}; "
            f"busy={widget.is_busy()}; workers={worker_state!r}"
        ) from exc

    assert widget.journey is not None, widget.status_label.text()
    assert widget.journey.recommendation_result_id == result_id
    assert widget.evidence_table.model().rowCount() > 0
    assert widget.maturity_table.model().rowCount() == 4
    expected_maturity = tuple(
        sorted(
            (
                item
                for item in widget.journey.outcome_maturity
                if item.candidate_key == (result_id, "1528")
            ),
            key=lambda item: item.window_days,
        )
    )
    assert len(expected_maturity) == 4
    for row, item in enumerate(expected_maturity):
        assert widget.maturity_table.model().index(row, 1).data() == {
            JourneyLinkStatus.LINKED: "已連結",
            JourneyLinkStatus.DEFERRED: "待可得",
            JourneyLinkStatus.UNKNOWN: "未知／未判定",
            JourneyLinkStatus.UNLINKED: "未連結",
            JourneyLinkStatus.CONFLICT: "衝突",
            JourneyLinkStatus.AMBIGUOUS: "歧義",
        }[item.status]
        assert (
            widget.maturity_table.model().index(row, 2).data()
            == _displayed_outcome_status(item.outcome_status)
        )

    screenshot_path = os.environ.get("DECISION_OUTCOME_JOURNEY_SCREENSHOT_PATH", "").strip()
    if screenshot_path:
        path = Path(screenshot_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        expand_details = os.environ.get(
            "DECISION_OUTCOME_JOURNEY_SCREENSHOT_EXPANDED", ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        if expand_details:
            widget.details_toggle.click()
        _app().processEvents()
        assert widget.grab().save(str(path))
    widget.close()


def _displayed_outcome_status(status: str | None) -> str:
    token = str(status or "").strip() or "unknown"
    return {
        "insufficient_future_data": "待成熟（未有足夠未來資料）",
        "ready": "來源已標示 ready",
        "observed": "已觀測",
        "missing": "缺資料",
        "unknown": "未知",
        "deferred": "待可得",
        "error": "讀取失敗",
    }.get(token, token)
