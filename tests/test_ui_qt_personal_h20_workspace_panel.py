"""保存 H20 摘要在父工作區切換期間仍可重新核驗。"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QWidget

from app_module.recommendation.personal_h20_product_evidence import PersonalH20ProductEvidence
from ui_qt.views.stock_research_workspace import StockResearchWorkspace


class _NoopReportService:
    def read_report(self, _stock_code: str, **_kwargs: object) -> object:
        raise AssertionError("此測試不應啟動個股報告讀取")


def test_saved_h20_retry_remains_enabled_when_parent_workspace_is_hidden() -> None:
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    workspace = StockResearchWorkspace(_NoopReportService(), parent=parent)
    parent.hide()
    evidence = PersonalH20ProductEvidence(
        stock_code="2382",
        status="unavailable",
        reason="fixture_h20_source_unavailable",
    )

    workspace.set_personal_h20_saved_evidence(evidence)
    workspace.set_personal_h20_saved_busy(False)
    assert workspace.personal_h20_saved_group.isHidden() is False
    assert workspace.personal_h20_saved_group.isVisible() is False
    assert workspace.personal_h20_saved_recheck_button.isEnabled()

    parent.show()
    app.processEvents()
    assert workspace.personal_h20_saved_group.isVisible()
    assert workspace.personal_h20_saved_recheck_button.isEnabled()
    assert "2382" in workspace.personal_h20_saved_summary.text()

    parent.hide()
    workspace.deleteLater()
    parent.deleteLater()
    app.processEvents()
