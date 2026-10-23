"""合法 H20 晚到時同步首屏與下一步，切股不保留舊預測。"""
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

from app_module.stock_research_report_dtos import StockMetricDTO
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


def test_quote_header_and_four_summary_facets_keep_original_report_values(monkeypatch):
    _app()
    report, context, _evidence, _ = _current_h20_case()
    if report.price_points:
        report = replace(
            report,
            price_points=(*report.price_points[:-1], replace(report.price_points[-1], change=None)),
            key_risks=("需要常顯的風險短摘要。" + "完整風險證據與限制。" * 30,),
        )
    monkeypatch.setattr(module, "_current_h20_observation_allows", lambda *args, **kwargs: True)
    view = module.StockResearchReportView(SimpleNamespace())
    try:
        view.context = context
        view._loaded_request_context = context
        view._render_report(report)
        if report.price_points:
            latest = report.price_points[-1]
            assert latest.data_date in view.quote_summary_label.text()
            assert module._decimal_text(latest.close_price) in view.quote_summary_label.text()
            assert latest.change is None
            assert "漲跌 未知" in view.quote_summary_label.text()
        for name in ("營收", "法人", "信用", "集保"):
            assert view.findChild(module.QGroupBox, f"stockResearchSummaryFacet_{name}") is not None
        risk_short = view.summary_focus.risk_label.text()
        assert not view.summary_focus.risk_label.isHidden()
        assert "主要風險／反證：" in risk_short
        view.summary_questions_toggle.setChecked(True)
        assert not view.summary_focus.risk_label.isHidden()
        assert "完整風險證據與限制。" in view.summary_focus.risk_label.text()
        assert len(view.summary_focus.risk_label.text()) > len(risk_short)
        from tests.opus_ux_review_fixture import full_research_report

        view._render_flows(full_research_report())
        for name in ("法人", "信用", "集保", "分點"):
            assert view.findChild(module.QGroupBox, f"stockResearchFacet_{name}") is not None
        flow_institutional = view.findChild(
            module.QLabel, "stockResearchFacetSummary_法人"
        ).text()
        for label in ("外資買賣超", "投信買賣超", "自營商買賣超"):
            assert label in flow_institutional
        assert "外資買進" not in flow_institutional
        flow_credit = view.findChild(
            module.QLabel, "stockResearchFacetSummary_信用"
        ).text()
        assert "融資餘額" in flow_credit and "融券餘額" in flow_credit
        assert "融資買進" not in flow_credit
        flow_tdcc = view.findChild(
            module.QLabel, "stockResearchFacetSummary_集保"
        ).text()
        for label in (
            "大額持有人比例（原基點）", "小額持有人比例（原基點）",
            "分散指標（原基點）",
        ):
            assert label in flow_tdcc
        assert "來源、日期或單位不一致" not in flow_tdcc
        flow_toggle = view.findChild(module.QToolButton, "stockResearchFlowDetailsToggle")
        assert flow_toggle is not None and not flow_toggle.isChecked()
        flow_toggle.setChecked(True)
        assert not view.findChild(module.QWidget, "stockResearchFlowDetails").isHidden()
        view._clear_loaded_report()
        assert view.quote_summary_label.text() == "收盤 未知｜漲跌 未知｜行情日 未知"
    finally:
        view.close()


def test_summary_facet_refuses_to_mix_different_sources_or_dates():
    metrics = (
        StockMetricDTO("foreign", "外資淨買賣", Decimal("120"), unit="股",
                       data_as_of="2026-10-21", source_id="source-a"),
        StockMetricDTO("trust", "投信淨買賣", Decimal("80"), unit="股",
                       data_as_of="2026-10-20", source_id="source-b"),
    )
    value, date, state, tooltip = module._summary_metric_payload(metrics, "目前缺件")
    assert "保留未知" in value
    assert "待核對" in date and state == "待核對"
    assert "source-a" in tooltip and "source-b" in tooltip


def test_monthly_revenue_summary_uses_latest_period_after_out_of_order_rows():
    report, context, _evidence, _ = _current_h20_case()
    from tests.opus_ux_review_fixture import full_research_report

    fixture = full_research_report()
    monthly_rows = tuple(item for item in fixture.fundamentals if item.kind == "monthly_revenue")
    observations = tuple(reversed(monthly_rows))
    report = replace(report, fundamentals=observations)
    view = module.StockResearchReportView(SimpleNamespace())
    try:
        view.context = context
        view._loaded_request_context = context
        view._render_report(report)
        summary = view.findChild(module.QLabel, "stockResearchSummaryFacetText_營收").text()
        assert "2026-09" in summary
        assert "1,410.00" in summary
        assert "1325" not in summary
    finally:
        view.close()


def test_monthly_revenue_summary_keeps_multiple_identity_groups_unknown():
    report, context, _evidence, _ = _current_h20_case()
    from tests.opus_ux_review_fixture import full_research_report

    fixture = full_research_report()
    base = next(item for item in fixture.fundamentals if item.kind == "monthly_revenue")
    second = replace(base, label="第二來源同期間 QA 示意", source_id="qa.fixture.monthly_revenue.alternate", value=Decimal("999"))
    report = replace(report, fundamentals=(base, second))
    view = module.StockResearchReportView(SimpleNamespace())
    try:
        view.context = context
        view._loaded_request_context = context
        view._render_report(report)
        summary = view.findChild(module.QLabel, "stockResearchSummaryFacetText_營收").text()
        assert "摘要保留未知" in summary
        assert "待核對" in summary
        assert "999" not in summary and "190" not in summary
    finally:
        view.close()


def test_institutional_summary_selects_all_three_net_fields_from_full_report_fixture():
    from tests.opus_ux_review_fixture import full_research_report

    report = full_research_report()
    _fixture_report, context, _evidence, _ = _current_h20_case()
    view = module.StockResearchReportView(SimpleNamespace())
    try:
        view.context = context
        view._loaded_request_context = context
        view._render_report(report)
        summary = view.findChild(module.QLabel, "stockResearchSummaryFacetText_法人").text()
        for label in ("外資買賣超", "投信買賣超", "自營商買賣超", "資料日 2026-10-21"):
            assert label in summary
        credit = view.findChild(module.QLabel, "stockResearchSummaryFacetText_信用").text()
        assert "融資餘額" in credit and "融券餘額" in credit
        tdcc = view.findChild(module.QLabel, "stockResearchSummaryFacetText_集保").text()
        assert "大額持有人比例" in tdcc
        assert "小額持有人比例" in tdcc
        assert "分散指標（原基點）" in tdcc
        assert "400" not in tdcc
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
