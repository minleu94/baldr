"""已保存健康評估清單狀態標籤的聚焦回歸。"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication

from app_module.position_health_saved_archive import SavedHealthReceiptCandidate
from ui_qt.widgets.position_health_saved_panel import PositionHealthSavedPanel


@pytest.fixture
def application() -> QApplication:
    current = QApplication.instance()
    if current is not None:
        return current
    return QApplication(["position-health-saved-status-labels"])


def _candidate(status: str, receipt_id: str) -> SavedHealthReceiptCandidate:
    return SavedHealthReceiptCandidate(
        receipt_id=receipt_id,
        receipt_sha256="a" * 64,
        result_sha256="b" * 64,
        portfolio_id="paper-main",
        snapshot_id="paper-snapshot-2026-10-08",
        decision_date=date(2026, 10, 8),
        source_snapshot_rows_sha256="c" * 64,
        status=status,
        observed_at="2026-10-08T09:06:00+08:00",
        available_at="2026-10-08T09:07:00+08:00",
    )


def test_saved_candidate_rows_localize_known_status_and_retain_unknown_token(
    application: QApplication,
) -> None:
    candidates = (
        _candidate("passed", "receipt-passed-123456789012"),
        _candidate("degraded", "receipt-degraded-123456789012"),
        _candidate("blocked", "receipt-blocked-123456789012"),
        _candidate("future_status", "receipt-unknown-123456789012"),
    )
    panel = PositionHealthSavedPanel(
        reader=object(), scope_factory=object(), selection_store=object()
    )
    try:
        panel._on_finished(0, "list_candidates", candidates)

        labels = [
            panel.saved_receipt_selector.itemText(index)
            for index in range(panel.saved_receipt_selector.count())
        ]
        assert "來源與評估資料已核對（passed）" in labels[0]
        assert "評估資料有來源限制（degraded）" in labels[1]
        assert "評估資料受阻，結果保持未知（blocked）" in labels[2]
        assert "評估狀態未知（原值：future_status）" in labels[3]
        assert all(candidate.status in label for candidate, label in zip(candidates, labels))

        # 顯示用標籤不改候選 DTO；精確 receipt 與 Paper 主帳戶識別仍由原物件承載。
        assert panel.saved_receipt_selector.currentIndex() == -1
        assert panel.saved_receipt_selector.itemData(0) is candidates[0]
        assert panel.saved_receipt_selector.itemData(3) is candidates[3]
        assert candidates[0].receipt_id.endswith("123456789012")
        assert candidates[0].portfolio_id == "paper-main"
        assert candidates[0].source_snapshot_rows_sha256 == "c" * 64
    finally:
        panel.begin_shutdown()
        panel.close()
