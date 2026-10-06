"""合法 H20 晚到時同步首屏與下一步，切股不保留舊預測。"""
from dataclasses import replace
from types import SimpleNamespace

from ui_qt.views import stock_research_report_view as module
from tests.test_ui_qt_stock_research_report import _app, _current_h20_case


def test_h20_updates_conclusion_status_and_next_step_together(monkeypatch):
    _app()
    report, context, evidence, _ = _current_h20_case()
    # 此案例驗呈現；原 observation/cutoff guard 由既有專屬案例驗證。
    monkeypatch.setattr(module, "_current_h20_observation_allows", lambda *args, **kwargs: True)
    view = module.StockResearchReportView(SimpleNamespace())
    try:
        view.context = context
        view._loaded_request_context = context
        view._render_report(report)
        view.set_personal_h20_evidence(evidence)
        assert "+6.84%" in view.summary_focus.conclusion_label.text()
        assert "未扣成本" in view.summary_focus.conclusion_label.text()
        assert "比較" in view.summary_focus.next_step_label.text()
        assert "無需先保存 Advice" in view.summary_focus.next_step_label.text()
        states = view._find_widget("stockResearchLimitations").text()
        for text in ("資料完整度", "資料時效", "模型可用性", "自然結果", "2026-10-07", "2026-10-06", "2026-10-05"):
            assert text in states
        assert not view.summary_source_group.isVisible()
        assert "prediction" in view.summary_limitations_detail_label.text()
        before = view.summary_focus.conclusion_label.text()
        view.context = replace(context, stock_code="2330")
        view.set_personal_h20_evidence(replace(evidence, gross_return_bp=999))
        assert view.summary_focus.conclusion_label.text() == before
        view._clear_loaded_report()
        assert view._personal_h20_evidence is None
        assert "+6.84%" not in view.summary_focus.conclusion_label.text()
        view.set_personal_h20_evidence(evidence)
        assert "+6.84%" not in view.summary_focus.conclusion_label.text()
    finally:
        view.close()


def test_unavailable_h20_refreshes_visible_status_without_old_estimate(monkeypatch):
    _app()
    report, context, evidence, _ = _current_h20_case()
    monkeypatch.setattr(module, "_current_h20_observation_allows", lambda *args, **kwargs: True)
    view = module.StockResearchReportView(SimpleNamespace())
    try:
        view.context = context
        view._loaded_request_context = context
        view._render_report(report)
        view.set_personal_h20_evidence(evidence)
        missing = replace(evidence, status="unavailable", gross_return_bp=None,
                          reason="保存來源損壞")
        view.set_personal_h20_evidence(missing)
        assert "+6.84%" not in view.summary_focus.conclusion_label.text()
        assert "無法核驗" in view._find_widget("stockResearchLimitations").text()
        assert "保存來源損壞" in view.summary_limitations_detail_label.text()
    finally:
        view.close()


def test_wrong_cohort_is_visible_rejection_without_signal_exception(monkeypatch):
    _app()
    report, context, evidence, _ = _current_h20_case()
    report = replace(report, research_context={
        "source_kind": "personal_h20_saved_cohort", "profile_id": "other-model",
    })
    monkeypatch.setattr(module, "_current_h20_observation_allows", lambda *args, **kwargs: True)
    view = module.StockResearchReportView(SimpleNamespace())
    try:
        view.context = context
        view._loaded_request_context = context
        view._render_report(report)
        view.set_personal_h20_evidence(evidence)
        assert view._personal_h20_evidence is None
        assert "+6.84%" not in view.summary_focus.conclusion_label.text()
        assert "來源不一致" in view._find_widget("stockResearchLimitations").text()
        assert "拒絕診斷" in view.summary_limitations_detail_label.text()
    finally:
        view.close()
