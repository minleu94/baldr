"""Bounded read-model presentation checks; all fixtures are explicitly controlled."""

from dataclasses import replace
from decimal import Decimal
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel, QPushButton
from PySide6.QtGui import QFont, QFontDatabase

from app_module.stock_research_report_dtos import (
    StockEvidenceEventDTO, StockMetricDTO, StockMLSnapshotDTO,
    StockPositionSnapshotDTO, StockPricePointDTO, StockReportSectionDTO,
    StockResearchReportDTO, StockTechnicalSnapshotDTO, StockAdviceSnapshotDTO,
)
from app_module.stock_research_report_service import _key_risks
from app_module.watchlist_analysis_service import WatchlistAnalysisDTO
from app_module.position_health_service import PositionHealthService, PositionHealthState
from ui_qt.views.stock_research_report_view import (
    StockResearchReportView, _decimal_text, _report_conclusion,
    _report_evidence_text, _report_limitations_text, _report_pending_text, _ml_estimate_summary,
)


def _report() -> StockResearchReportDTO:
    """Prices reconstruct screenshot facts; ML/history are test scenarios, not evidence."""
    return StockResearchReportDTO(
        stock_code="2382", stock_name="廣達", as_of="2026-10-05",
        price_points=(StockPricePointDTO(data_date="2026-10-02", close_price=Decimal("332"), change=Decimal("-2")),),
        technical=StockTechnicalSnapshotDTO(data_date="2026-10-02", indicators=(
            StockMetricDTO(key="MA20", label="MA20", value=Decimal("338.2733333333")),
            StockMetricDTO(key="MA60", label="MA60", value=Decimal("331.6433333333")),
        )),
        sections=(StockReportSectionDTO(section_id="price", label="價格", status="available"),),
        position=StockPositionSnapshotDTO(is_holding=True, health_status="WATCH", health_reasons=("condition_result_missing",)),
        events=(StockEvidenceEventDTO(event_id="controlled-history", event_date="2026-09-30", decision_date="2026-09-30",
                                     event_type="portfolio_alert_condition_warning", data_quality="critical",
                                     risk_reasons=("condition_result_missing",)),),
        ml=StockMLSnapshotDTO(status="degraded", target_metric="cost-adjusted benchmark excess bp",
                             predicted_benchmark_excess_return_bp={"H5": -120}, h5_status="pending",
                             run_id="controlled-fixture-2382", model_manifest_sha256="sha256:" + "a" * 64,
                             model_bundle_sha256="sha256:" + "b" * 64, source_snapshot_hash="sha256:" + "c" * 64,
                             limitations=("來源資格仍為研究，未具正式資格。",)),
    )


def test_current_facts_replace_historical_headline_and_bound_precision():
    report = _report()
    assert _report_conclusion(report) == "收盤低於MA20、高於MA60；僅為同日技術觀察，不是買賣建議。"
    evidence = _report_evidence_text(report)
    assert len(evidence.split("；")) == 3
    assert "332.00" in evidence and "-2.00" in evidence
    assert "338.27" in evidence and "331.64" in evidence
    assert "333333" not in evidence
    assert _decimal_text(Decimal("0")) == "0.00"
    assert _decimal_text(None) == "—"
    stale = replace(report, technical=replace(report.technical, data_date="2026-10-01"))
    assert "日期不同，不直接比較" in _report_evidence_text(stale)
    assert "收盤低於MA20" not in _report_conclusion(stale)


def test_shared_conditions_control_headline_and_evidence_without_recomparison():
    report = _report()
    snapshot = {
        "market_date": "2026-10-02",
        "conditions": {
            "close_above_ma20": {"state": "unknown", "relation": "unknown"},
            "close_above_ma60": {"state": "no_match", "relation": "equal", "data_date": "2026-10-02", "reference_value": "332"},
        },
        "features": {"MA20": {"warmup_state": "unknown", "warmup_observed_count": 12, "warmup_required_count": 20}},
    }
    projected = replace(report, shared_daily_features=snapshot)
    assert "MA20 尚無法判讀" in _report_conclusion(projected)
    assert "等於MA60" in _report_conclusion(projected)
    assert "低於MA20" not in _report_conclusion(projected)
    assert "12/20" in _report_evidence_text(projected)
    assert "收盤等於 MA60 332.00" in _report_evidence_text(projected)
    snapshot["conditions"]["close_above_ma60"]["data_date"] = "2026-10-01"
    assert "MA20、MA60 尚無法判讀" in _report_conclusion(projected)
    snapshot["conditions"]["close_above_ma60"]["relation"] = []
    assert "MA20、MA60 尚無法判讀" in _report_conclusion(projected)


def test_missing_conditions_are_limits_and_do_not_change_watch_policy():
    report = _report()
    assert _key_risks(StockAdviceSnapshotDTO(), report.events, report.position, ("來源讀取失敗",)) == ()
    assert "持倉健康缺少條件結果" in _report_limitations_text(report)
    assert "condition_result_missing" not in _report_limitations_text(report)
    health = PositionHealthService().evaluate(stock_code="2382", condition_result=None,
                                            feedback_status=None, source_trace=("test-source",))
    assert health.state is PositionHealthState.WATCH
    assert health.auto_action_allowed is False
    genuine = replace(report.position, health_reasons=("condition_result_missing", "趨勢條件轉弱"))
    assert _key_risks(StockAdviceSnapshotDTO(), report.events, genuine, ()) == ("趨勢條件轉弱",)


@pytest.mark.parametrize("status", ["blocked", "failed", "error"])
def test_outcome_failure_is_not_relabelled_as_waiting(status):
    report = _report()
    assert "受阻" in _report_pending_text(replace(report, ml=replace(report.ml, h5_status=status)))
    broken = replace(report, sections=(StockReportSectionDTO(section_id="price", label="價格", status="error"),))
    assert _report_limitations_text(broken).startswith("價格讀取失敗")


@pytest.fixture
def readable_fonts():
    app = QApplication.instance() or QApplication([])
    old_font = app.font()
    loaded = []
    for filename in ("msjh.ttc", "msjhbd.ttc", "arial.ttf"):
        path = Path("C:/Windows/Fonts") / filename
        if path.is_file():
            loaded.append(QFontDatabase.addApplicationFont(str(path)))
    app.setFont(QFont("Microsoft JhengHei", 9))
    yield app
    app.setFont(old_font)
    for font_id in loaded:
        if font_id >= 0:
            QFontDatabase.removeApplicationFont(font_id)


def test_controlled_2382_render_keeps_audit_collapsed_and_preserves_raw_identity(readable_fonts):
    app = readable_fonts
    view = StockResearchReportView(SimpleNamespace())
    report = _report()
    view._active_code = report.stock_code
    view._render_report(report)
    view.resize(1000, 835)
    view.show()
    app.processEvents()
    assert "低於MA20、高於MA60" in view.summary_focus.conclusion_label.text()
    assert "condition_result_missing" not in view.summary_focus.risk_label.text()
    assert "持倉健康缺少條件結果" in view.summary_focus.sufficiency_label.text()
    assert "待驗證條件" in view.summary_focus.reasons_label.text()
    output = os.environ.get("STOCK_RESEARCH_READABILITY_OUTPUT", "")
    if output:
        root = Path(output)
        root.mkdir(parents=True, exist_ok=True)
        view.status_label.setText("受控 DTO 重建：價格／均線參考原截圖；ML／歷史為測試情境，非自然證據。")
        view.status_badge.setText("受控渲染")
        assert view.grab().save(str(root / "2382_summary_controlled.png"))
        (root / "controlled_report.json").write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    view.tabs.setCurrentIndex(5)
    app.processEvents()
    audit = view.findChild(QGroupBox, "stockResearchMLAudit")
    assert audit is not None and audit.isHidden()
    history = view.findChild(QGroupBox, "stockResearchHistoryAudit")
    assert history is not None and history.isHidden()
    visible = "\n".join(label.text() for label in view.findChildren(QLabel) if label.isVisible())
    assert "-120 bp" in visible and "不是股價漲跌預測" in visible
    assert "基準名稱" in visible and "未提供" in visible
    assert "controlled-fixture-2382" not in visible and "sha256:" not in visible
    assert "1.2%" not in visible
    assert "ML 品質降級：來源資格仍為研究，未具正式資格。" in visible
    if output:
        assert view.grab().save(str(Path(output) / "2382_ml_collapsed_controlled.png"))
    toggle = view.findChild(QPushButton, "stockResearchMLAuditToggle")
    assert toggle is not None and not toggle.isChecked()
    assert toggle.text().startswith("展開資料稽核")
    toggle.click()
    app.processEvents()
    assert not audit.isHidden()
    assert toggle.isChecked() and toggle.text().startswith("收合資料稽核")
    if output:
        assert view.grab().save(str(Path(output) / "2382_ml_audit_controlled.png"))
    toggle.click()
    app.processEvents()
    assert audit.isHidden() and not toggle.isChecked()
    assert toggle.text().startswith("展開資料稽核")
    view.close()


@pytest.mark.parametrize("scope", ["current_stock_research", "selected_saved_decision", ""])
def test_ml_heading_uses_declared_scope_and_missing_degradation_reason(readable_fonts, scope):
    report = _report()
    report = replace(report, ml=replace(report.ml, scope_mode=scope,
                                       event_date="2026-09-30", limitations=()))
    view = StockResearchReportView(SimpleNamespace())
    view._active_code = report.stock_code
    view._render_report(report)
    view.tabs.setCurrentIndex(5)
    view.show()
    readable_fonts.processEvents()
    group = view.findChild(QGroupBox, "stockResearchMLGroup")
    assert group is not None
    if scope == "current_stock_research":
        assert group.title() == "當前ML研究（研究日：2026-10-05）"
    elif scope == "selected_saved_decision":
        assert group.title() == "所選保存決策ML研究（模型事件日：2026-09-30）"
    else:
        assert group.title().startswith("ML 研究輸出")
    visible = "\n".join(label.text() for label in view.findChildren(QLabel) if label.isVisible())
    assert "ML 品質降級：原因未提供。" in visible
    history = view.tabs.currentWidget().findChild(QGroupBox, "stockResearchHistoryGroup")
    assert history is not None and "所選決策日：未選定" in history.title()
    selected = replace(report, advice=replace(report.advice, saved_analysis=WatchlistAnalysisDTO(
        stock_code="2382", status="saved", result_id="controlled-saved-2382",
        decision_date="2026-09-30",
    )))
    view.close()
    view = StockResearchReportView(SimpleNamespace())
    view._active_code = selected.stock_code
    view._render_report(selected)
    view.tabs.setCurrentIndex(5)
    readable_fonts.processEvents()
    history = view.tabs.currentWidget().findChild(QGroupBox, "stockResearchHistoryGroup")
    assert history is not None and "所選決策日：2026-09-30" in history.title()
    view.close()


def test_dated_saved_advice_and_historical_rule_are_not_current_risk_or_headline():
    report = _report()
    saved = StockAdviceSnapshotDTO(recommendation=SimpleNamespace(risk_reasons=("原決策風險",), decision_date="2026-09-30"))
    assert _key_risks(saved, (), None, (), as_of_date="2026-10-05") == ()
    assert _key_risks(saved, (), None, (), as_of_date="2026-09-30") == ("原決策風險",)
    assert saved.recommendation.risk_reasons == ("原決策風險",)
    history_only = replace(report, price_points=(), technical=None, attention_reasons=(),
                           rule_reasons=("condition_result_missing",))
    assert "值得深入核對" not in _report_conclusion(history_only)


def test_unknown_cost_definition_does_not_claim_after_cost_estimate():
    ml = replace(_report().ml, target_metric="cost not accounted for")
    assert "成本定義未提供" in _ml_estimate_summary(ml)
    assert "成本後基準超額報酬" not in _ml_estimate_summary(ml)
