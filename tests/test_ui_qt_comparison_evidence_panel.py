"""比較第一層保留原證據、未知與純文字；換選不得沿用前股理由。"""

from PySide6.QtWidgets import QApplication, QDialog, QScrollArea, QWidget
from ui_qt.theme import MIDNIGHT_ANALYST

from ui_qt.widgets.comparison_evidence_panel import (
    ComparisonEvidencePanel,
    compact_comparison_audit,
    style_comparison_dialog,
)
from ui_qt.widgets.theme_widgets import CollapsibleSectionPanel


def test_original_text_and_missing_counterevidence_are_not_interpreted_or_carried_forward():
    app = QApplication.instance() or QApplication([])
    panel = ComparisonEvidencePanel()
    try:
        panel.set_evidence(
            heading="2330｜原規則", context="資料日 2026-10-06｜分母 0",
            supports=("<b>原件文字，不是HTML</b>",), counterevidence=(), unknown_reasons=("原資料日缺件",),
        )
        app.processEvents()
        assert panel.values["support"].toPlainText() == "<b>原件文字，不是HTML</b>"
        assert "不代表沒有風險" in panel.values["counter"].toPlainText()
        assert "分母 0" in panel.context.text()
        assert panel.unknown_details.is_collapsed()
        assert "1 項；選取查看" in panel.unknown_details.title_label.text()
        assert f"color: {MIDNIGHT_ANALYST.text_secondary}" in panel.values["unknown"].styleSheet()
        panel.unknown_details.toggle_button.click()
        assert not panel.unknown_details.is_collapsed()
        assert "原資料日缺件" in panel.values["unknown"].toPlainText()
        panel.set_evidence(heading="2603｜未知", context="資料日未知", supports=(), counterevidence=(), unknown_reasons=())
        assert "2330" not in panel.heading.text()
        assert "原件文字" not in panel.values["support"].toPlainText()
        assert "原資料日缺件" not in panel.values["unknown"].toPlainText()
        assert "原件未提供" in panel.values["unknown"].toPlainText()
        assert "未知原因（未提供" in panel.unknown_details.title_label.text()
    finally:
        panel.close()


def test_comparison_dialog_has_opaque_background_under_transparent_scroll_ancestor():
    app = QApplication.instance() or QApplication([])
    scroll = QScrollArea()
    scroll.setStyleSheet("QScrollArea QWidget { background: transparent; }")
    parent = QWidget()
    scroll.setWidget(parent)
    dialog = QDialog(parent)
    style_comparison_dialog(dialog)
    dialog.resize(400, 240)
    dialog.show()
    app.processEvents()
    try:
        assert dialog.grab().toImage().pixelColor(2, 2).alpha() == 255
    finally:
        dialog.close()
        scroll.close()


def test_compact_comparison_disclosure_keeps_toggle_text_unclipped():
    app = QApplication.instance() or QApplication([])
    panel = CollapsibleSectionPanel("完整來源與原假設", collapsed=True)
    try:
        compact_comparison_audit(panel)
        app.processEvents()
        assert panel.toggle_button.height() == 28
        assert panel.toggle_button.maximumWidth() > 48
        assert panel.toggle_button.text() == "展開"
    finally:
        panel.close()
