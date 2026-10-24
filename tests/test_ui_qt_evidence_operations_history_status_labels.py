from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app_module.evidence_operations_history_dashboard_dtos import (
    EvidenceOperationsHistoryDashboardRow,
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
