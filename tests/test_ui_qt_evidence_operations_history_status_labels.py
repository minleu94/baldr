from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app_module.evidence_operations_history_dashboard_dtos import (
    EvidenceOperationsHistoryDashboardRow,
)
from app_module.evidence_operations_history_dashboard_service import (
    _candidate_review_decision_summary,
)
from ui_qt.views.evidence_operations_history_view import (
    ActionItemLifecycleDialog,
    EvidenceOperationsHistoryView,
    _weekly_review_approval_text,
)
from ui_qt.models.evidence_operations_history_table_model import (
    EvidenceOperationsHistoryTableModel,
)


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _row(
    *, review_status: str = "coverage_only", scheduler_readiness: str = "ready_for_manual_confirm"
) -> EvidenceOperationsHistoryDashboardRow:
    return EvidenceOperationsHistoryDashboardRow(
        period_start="2026-07-06",
        period_end="2026-07-12",
        review_status=review_status,
        scheduler_readiness=scheduler_readiness,
        production_scheduler_allowed=False,
        decision_quality_reviews_count=1,
        signal_decay_observations_count=2,
        manual_lifecycle_candidate_count=0,
        warnings_count=1,
        review_id="eor_status_labels",
    )


def test_known_evidence_history_statuses_display_chinese_and_keep_raw_tooltips() -> None:
    _app()
    model = EvidenceOperationsHistoryTableModel((_row(),))
    review_column = model.column_index("review_status")
    readiness_column = model.column_index("scheduler_readiness")

    review_index = model.index(0, review_column)
    readiness_index = model.index(0, readiness_column)
    assert model.data(review_index, Qt.DisplayRole) == "僅有覆蓋資料"
    assert model.data(review_index, Qt.ToolTipRole) == "原始碼：coverage_only"
    assert model.data(readiness_index, Qt.DisplayRole) == "待人工確認"
    assert model.data(readiness_index, Qt.ToolTipRole) == "原始碼：ready_for_manual_confirm"
    assert model.raw_value(0, "review_status") == "coverage_only"
    assert model.raw_value(0, "scheduler_readiness") == "ready_for_manual_confirm"


def test_unknown_evidence_history_statuses_remain_raw_and_scheduler_headers_are_chinese() -> None:
    _app()
    model = EvidenceOperationsHistoryTableModel(
        (_row(review_status="future_review_code", scheduler_readiness="future_readiness_code"),)
    )

    review_index = model.index(0, model.column_index("review_status"))
    readiness_index = model.index(0, model.column_index("scheduler_readiness"))
    assert model.data(review_index, Qt.DisplayRole) == "future_review_code"
    assert model.data(review_index, Qt.ToolTipRole) == "原始碼：future_review_code"
    assert model.data(readiness_index, Qt.DisplayRole) == "future_readiness_code"
    assert model.data(readiness_index, Qt.ToolTipRole) == "原始碼：future_readiness_code"
    assert model.headerData(model.column_index("scheduler_readiness"), Qt.Horizontal) == "排程就緒狀態"
    assert model.headerData(model.column_index("production_scheduler_allowed"), Qt.Horizontal) == "允許正式排程"
    allowed_index = model.index(0, model.column_index("production_scheduler_allowed"))
    assert model.data(allowed_index, Qt.DisplayRole) == "否"
    assert model.raw_value(0, "production_scheduler_allowed") is False


def test_history_view_switches_dashboard_and_approval_to_same_working_copy(monkeypatch) -> None:
    _app()
    refreshes = []
    history_sources = []
    approval_sources = []
    view = EvidenceOperationsHistoryView(
        object(),
        history_service_factory=lambda path: history_sources.append(path) or object(),
        approval_service_factory=lambda path: approval_sources.append(path) or object(),
        auto_refresh=False,
    )
    monkeypatch.setattr(view, "refresh_dashboard", lambda: refreshes.append(True))

    assert view._apply_history_source("C:/scratch/weekly.db") is True
    assert history_sources == ["C:/scratch/weekly.db"]
    assert approval_sources == ["C:/scratch/weekly.db"]
    assert len(refreshes) == 1
    assert "C:/scratch/weekly.db" in view.history_source_label.text()


def test_history_view_keeps_current_source_when_working_copy_is_rejected(monkeypatch) -> None:
    _app()
    warnings = []
    monkeypatch.setattr(
        "ui_qt.views.evidence_operations_history_view.QMessageBox.warning",
        lambda *args: warnings.append(args[-1]),
    )
    view = EvidenceOperationsHistoryView(
        object(),
        history_service_factory=lambda _path: (_ for _ in ()).throw(
            ValueError("weekly_review_formal_db_forbidden")
        ),
        approval_service_factory=lambda _path: object(),
        history_source_path="default-db",
        auto_refresh=False,
    )
    current_dashboard = view.dashboard_service

    assert view._apply_history_source("formal-db") is False
    assert view.dashboard_service is current_dashboard
    assert view.history_source_path == "default-db"
    assert warnings == ["正式 twstock.db 不可作為 weekly-review working-copy 來源。"]


def test_candidate_decision_history_save_requires_explicit_working_copy_and_reports_hash(monkeypatch):
    _app()
    calls = []
    refreshes = []
    record = type(
        "Record",
        (),
        {"review_id": "eor_exact", "review_hash": "sha256:" + "c" * 64},
    )()
    view = EvidenceOperationsHistoryView(
        object(),
        history_service_factory=lambda path: object(),
        approval_service_factory=lambda path: object(),
        candidate_history_save_service_factory=lambda db_path, **kwargs: calls.append(
            (db_path, kwargs)
        ) or record,
        auto_refresh=False,
        async_refresh=False,
    )
    monkeypatch.setattr(view, "refresh_dashboard", lambda: refreshes.append(True))
    assert not view.save_candidate_history_button.isEnabled()
    assert view._apply_history_source("C:/scratch/weekly.db")
    assert view.save_candidate_history_button.isEnabled()

    values = iter(("2026-10-19", "2026-10-25"))
    monkeypatch.setattr(
        "ui_qt.views.evidence_operations_history_view.date_filter_value",
        lambda _widget: next(values),
    )
    selected = iter(
        (
            ("C:/scratch/decision.json", "JSON artifact (*.json)"),
            ("C:/scratch/sidecar.db", "SQLite database (*.db)"),
        )
    )
    monkeypatch.setattr(
        "ui_qt.views.evidence_operations_history_view.QFileDialog.getOpenFileName",
        lambda *_args: next(selected),
    )
    monkeypatch.setattr(
        "ui_qt.views.evidence_operations_history_view.QMessageBox.question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    view._save_candidate_decision_to_history()

    assert calls == [
        (
            "C:/scratch/weekly.db",
            {
                "start_date": "2026-10-19",
                "end_date": "2026-10-25",
                "decision_artifact_path": "C:/scratch/decision.json",
                "sidecar_path": "C:/scratch/sidecar.db",
            },
        )
    ]
    assert "eor_exact" in view.save_candidate_history_status_label.text()
    assert "sha256:" + "c" * 64 in view.save_candidate_history_status_label.text()
    assert len(refreshes) == 2


def test_candidate_history_save_locks_source_and_conflicting_review_controls() -> None:
    _app()
    factory_calls = []

    class _ActionLifecycleService:
        def list_action_items(self):
            return []

    def history_factory(path):
        factory_calls.append(("history", path))
        return object()

    def approval_factory(path):
        factory_calls.append(("approval", path))
        return object()

    view = EvidenceOperationsHistoryView(
        object(),
        history_service_factory=history_factory,
        approval_service_factory=approval_factory,
        action_lifecycle_service_factory=lambda *_args: _ActionLifecycleService(),
        candidate_history_save_service_factory=lambda *_args, **_kwargs: None,
        auto_refresh=False,
        async_refresh=False,
    )
    assert view._apply_history_source("C:/scratch/weekly.db")
    view.action_item_projection_path = "C:/scratch/actions.json"
    view._update_action_lifecycle_controls()
    original_factory_calls = list(factory_calls)

    view._set_candidate_history_operation_busy(True)

    assert not view.choose_history_source_button.isEnabled()
    assert not view.default_history_source_button.isEnabled()
    assert not view.refresh_button.isEnabled()
    assert not view.start_date_input.isEnabled()
    assert not view.end_date_input.isEnabled()
    assert not view.choose_action_item_projection_button.isEnabled()
    assert not view.review_action_items_button.isEnabled()
    assert not view.owner_approval_button.isEnabled()
    assert not view.save_candidate_history_button.isEnabled()
    assert view._apply_history_source("C:/scratch/other-weekly.db") is False
    assert factory_calls == original_factory_calls
    assert view.history_source_path == "C:/scratch/weekly.db"

    view._set_candidate_history_operation_busy(False)

    assert view.choose_history_source_button.isEnabled()
    assert view.default_history_source_button.isEnabled()
    assert view.refresh_button.isEnabled()
    assert view.start_date_input.isEnabled()
    assert view.end_date_input.isEnabled()
    assert view.choose_action_item_projection_button.isEnabled()
    assert view.review_action_items_button.isEnabled()


def test_candidate_history_save_callbacks_restore_controls(monkeypatch) -> None:
    _app()
    refreshes = []
    view = EvidenceOperationsHistoryView(
        object(),
        history_service_factory=lambda _path: object(),
        approval_service_factory=lambda _path: object(),
        candidate_history_save_service_factory=lambda *_args, **_kwargs: None,
        auto_refresh=False,
        async_refresh=False,
    )
    monkeypatch.setattr(view, "refresh_dashboard", lambda: refreshes.append(True))
    monkeypatch.setattr(
        "ui_qt.views.evidence_operations_history_view.QMessageBox.warning",
        lambda *_args: None,
    )
    assert view._apply_history_source("C:/scratch/weekly.db")

    view._set_candidate_history_operation_busy(True)
    view._on_candidate_history_save_error("candidate validation failed")
    assert not view._candidate_history_save_in_progress
    assert view.choose_history_source_button.isEnabled()
    assert view.default_history_source_button.isEnabled()
    assert view.refresh_button.isEnabled()
    assert view.start_date_input.isEnabled()
    assert view.end_date_input.isEnabled()
    assert view.save_candidate_history_button.isEnabled()

    view._set_candidate_history_operation_busy(True)
    record = type(
        "Record",
        (),
        {"review_id": "eor_exact", "review_hash": "sha256:" + "c" * 64},
    )()
    view._on_candidate_history_saved(record)
    assert not view._candidate_history_save_in_progress
    assert view.choose_history_source_button.isEnabled()
    assert view.default_history_source_button.isEnabled()
    assert view.refresh_button.isEnabled()
    assert view.save_candidate_history_button.isEnabled()
    assert len(refreshes) == 2


def test_action_item_lifecycle_requires_explicit_source_and_separate_projection(monkeypatch) -> None:
    _app()
    lifecycle_calls = []

    class _LifecycleService:
        def list_action_items(self):
            return []

    def _lifecycle_factory(db_path, projection_path):
        lifecycle_calls.append((db_path, projection_path))
        return _LifecycleService()

    view = EvidenceOperationsHistoryView(
        object(),
        history_service_factory=lambda _path: object(),
        approval_service_factory=lambda _path: object(),
        action_lifecycle_service_factory=_lifecycle_factory,
        history_source_path="default-database-path",
        auto_refresh=False,
    )
    monkeypatch.setattr(view, "refresh_dashboard", lambda: None)

    assert not view.choose_action_item_projection_button.isEnabled()
    assert not view.review_action_items_button.isEnabled()
    assert view._apply_history_source("C:/scratch/weekly.db")
    assert view.choose_action_item_projection_button.isEnabled()
    assert not view.review_action_items_button.isEnabled()

    monkeypatch.setattr(
        "ui_qt.views.evidence_operations_history_view.QFileDialog.getSaveFileName",
        lambda *args: ("C:/scratch/action-lifecycle.json", "JSON files (*.json)"),
    )
    view._choose_action_item_projection()
    assert lifecycle_calls == [("C:/scratch/weekly.db", "C:/scratch/action-lifecycle.json")]
    assert view.review_action_items_button.isEnabled()

    assert view._apply_history_source("C:/scratch/other-weekly.db")
    assert view.action_item_projection_path == ""
    assert not view.review_action_items_button.isEnabled()
    assert view._apply_history_source(None)
    assert not view.choose_action_item_projection_button.isEnabled()
    assert not view.review_action_items_button.isEnabled()


def test_action_item_lifecycle_dialog_shows_source_identity_and_only_allowed_next_states() -> None:
    _app()
    item = {
        "action_item_id": "action-1",
        "item_id": "item-1",
        "review_id": "review-1",
        "review_hash": "sha256:" + "a" * 64,
        "period_start": "2026-10-19",
        "period_end": "2026-10-25",
        "owner": "review-owner",
        "description": "檢查本週來源缺口",
        "lifecycle_status": "reviewed",
        "latest_event": {
            "from_status": "open",
            "to_status": "reviewed",
            "recorded_at": "2026-10-26T20:00:00Z",
            "actor_name": "Owner",
            "actor_role": "owner",
            "note": "已核對來源狀態",
        },
        "lifecycle_history": [
            {
                "from_status": "open",
                "to_status": "reviewed",
                "recorded_at": "2026-10-26T20:00:00Z",
                "actor_name": "Owner",
                "actor_role": "owner",
                "note": "已核對來源狀態",
            }
        ],
    }
    dialog = ActionItemLifecycleDialog([item])

    assert dialog.status_combo.count() == 1
    assert dialog.status_combo.currentData() == "follow_up"
    details = dialog.action_detail.toPlainText()
    assert "review-1" in details
    assert "item-1" in details
    assert "已核對來源狀態" in details
    dialog.actor_name_input.setText("Owner")
    dialog.actor_role_input.setText("owner")
    dialog.note_input.setPlainText("已安排下次跟進")
    assert dialog.selection() == {
        "action_item_id": "action-1",
        "new_status": "follow_up",
        "actor_name": "Owner",
        "actor_role": "owner",
        "note": "已安排下次跟進",
    }


def test_history_details_show_hash_bound_candidate_decision_and_limitations() -> None:
    _app()
    row = EvidenceOperationsHistoryDashboardRow(
        period_start="2026-10-19",
        period_end="2026-10-25",
        review_status="coverage_only",
        scheduler_readiness="ready_for_manual_confirm",
        production_scheduler_allowed=False,
        decision_quality_reviews_count=0,
        signal_decay_observations_count=0,
        manual_lifecycle_candidate_count=0,
        warnings_count=16,
        review_id="eor_candidate_review",
        review_hash="sha256:" + "b" * 64,
        candidate_review_decision_summary=(
            "處置：follow_up",
            "Owner：Owner One",
            "Reviewer：Reviewer One",
            "理由：逐筆追查來源證據",
            "候選 collection：ewc_123",
            "候選 source hash：sha256:" + "c" * 64,
            "原始決定檔 SHA-256：sha256:" + "d" * 64,
            "資格：候選人工處置；不代表 Gate 2 接受或正式排程允許。",
        ),
    )
    view = EvidenceOperationsHistoryView(object(), auto_refresh=False)
    view._render_details(row, type("Result", (), {"limitations": ()})())

    details = view.detail_panel.toPlainText()
    for expected in (
        "候選人工處置（已綁定此週報 hash）",
        "follow_up",
        "Owner One",
        "Reviewer One",
        "逐筆追查來源證據",
        "ewc_123",
        "候選人工處置；不代表 Gate 2 接受或正式排程允許",
    ):
        assert expected in details

    approval_text = _weekly_review_approval_text(row)
    assert "ewc_123" in approval_text
    assert "原始決定檔 SHA-256" in approval_text
    assert "不會批准 production scheduler" in approval_text


def test_history_dashboard_only_projects_candidate_only_decision_payload() -> None:
    artifact = {
        "decision": "follow_up",
        "note": "逐筆追查來源證據",
        "owner": {"name": "Owner One", "role": "Portfolio Owner"},
        "reviewer": {"name": "Reviewer One", "role": "Reviewer"},
        "source": {
            "collection_id": "ewc_123",
            "source_hash": "sha256:" + "c" * 64,
        },
        "artifact_sha256": "sha256:" + "d" * 64,
        "candidate_only": True,
        "formal_credit_authorized": False,
        "production_scheduler_allowed": False,
        "approved_projection_emitted": False,
    }

    summary = _candidate_review_decision_summary(
        {"candidate_review_decision": artifact}
    )
    assert any("follow_up" in line for line in summary)
    assert any("ewc_123" in line for line in summary)
    assert any("sha256:" + "d" * 64 in line for line in summary)
    assert "candidate_only" not in " ".join(
        _candidate_review_decision_summary(
            {"candidate_review_decision": {**artifact, "candidate_only": False}}
        )
    )
    assert _candidate_review_decision_summary({"status": "legacy"}) == ()
