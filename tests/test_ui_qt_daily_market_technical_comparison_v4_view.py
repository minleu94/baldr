"""原保存比較的選股／選規則證據及返回維持同一版本。"""

from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_universe_v4_bookmark import read_daily_market_technical_universe_v4_bookmark
from ui_qt.views.daily_market_technical_comparison_v4_view import DailyMarketTechnicalComparisonV4View

pytest_plugins = ("tests.test_daily_market_technical_universe_v4_bookmark",)


def test_verified_comparison_shows_original_evidence_and_keeps_return_query(pinned_bookmark):
    app = QApplication.instance() or QApplication([])
    state = read_daily_market_technical_universe_v4_bookmark(pinned_bookmark["bookmark"])
    comparison = state.comparison
    assert comparison is not None
    original = comparison.to_dict()
    view = DailyMarketTechnicalComparisonV4View()
    view.resize(900, 650)
    view.show()
    returned = []
    view.originRequested.connect(returned.append)
    try:
        view.show_comparison(comparison)
        app.processEvents()
        assert view.source_details.is_collapsed()
        assert "2382" in view.evidence_summary.heading.text()
        assert "納入 3／宣告 3 檔" in view.evidence_summary.conditions.text()
        assert "不是全市場分母" in view.evidence_summary.conditions.text()
        view.table.setCurrentCell(8, 1)
        app.processEvents()
        selected = comparison.columns[1]
        rule = selected.row.rule("volume_ratio_5_including_current")
        assert "9999" in view.evidence_summary.heading.text()
        assert "5 日均量比" in view.evidence_summary.heading.text()
        assert str(rule.denominator) in view.evidence_summary.context.text()
        assert "決策截止" in view.evidence_summary.context.text()
        assert all(value in view.evidence_summary.values["counter"].toPlainText() for value in rule.counterevidence)
        assert view.table.item(9, 1).text() == selected.origin_query.receipt_identity_sha256[:12] + "…"
        view.source_details.toggle_button.click()
        assert not view.source_details.is_collapsed()
        assert selected.origin_query.receipt_identity_sha256 in view.evidence.toPlainText()
        view.return_button.click()
        assert returned == [(selected.origin_query, selected.row.stock_code)]
        assert comparison.to_dict() == original
    finally:
        view.close()
