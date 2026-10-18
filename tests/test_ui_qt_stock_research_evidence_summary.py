"""First-screen evidence and saved-advice boundaries for stock research."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from app_module.advice_dtos import AdviceAction, RecommendationAdviceDTO
from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_dtos import (
    StockAdviceSnapshotDTO,
    StockMLSnapshotDTO,
    StockMetricDTO,
    StockTechnicalSnapshotDTO,
)
from tests.test_ui_qt_stock_research_report import _app, _current_h20_case, _report_for
from ui_qt.views import stock_research_report_view as module


def _context(
    code: str = "2382",
    *,
    decision_date: str = "2026-09-08",
    data_date: str = "2026-09-08",
    result_id: str = "saved-2382",
    scope: str = "selected_saved_decision",
) -> ResearchStockContextDTO:
    return ResearchStockContextDTO(
        stock_code=code,
        decision_date=decision_date,
        data_date=data_date,
        result_id=result_id,
        source_id="recommendation-run-2382",
        source_version="recommendation-v1",
        source_kind="saved_recommendation",
        ml_scope_mode=scope,
    )


def _report_with_saved_advice(code: str = "2382"):
    report = _report_for(code, "330")
    recommendation = RecommendationAdviceDTO(
        stock_code=code,
        advice_action=AdviceAction.RESEARCH,
        why_reasons=("保存支持原句",),
        why_not_reasons=("保存反對原句",),
        risk_reasons=("保存風險原句",),
        invalidation_conditions=("保存失效條件原句",),
        decision_date="2026-09-08",
        data_as_of_date="2026-09-08",
    )
    return replace(
        report,
        advice=StockAdviceSnapshotDTO(
            recommendation=recommendation,
            rule_reasons=("已保存 Rule 原句",),
        ),
    )


def _view_for(report, context: ResearchStockContextDTO | None):
    _app()
    view = module.StockResearchReportView(SimpleNamespace())
    view.context = context
    view._loaded_request_context = context
    view._loaded_context_identity = view._context_identity(context, report.stock_code)
    view._render_report(report)
    return view


def test_final_summary_keeps_market_facts_and_separates_holding_relation():
    report = _report_for("2382", "330")
    view = _view_for(report, None)
    try:
        expected_facts = module._report_evidence_text(report)
        holding = module.build_stock_research_product_summary(report).holding_relation
        rendered = view.summary_focus.evidence_label.text()

        assert expected_facts in rendered
        assert rendered.startswith("主要證據／資料日：" + expected_facts)
        assert "持倉關係（獨立持倉欄位，非上述行情來源）：" + holding in rendered
        assert "持倉關係：" not in rendered
    finally:
        view.close()


def test_current_technical_clues_stay_separate_from_saved_reasons_and_h5():
    report = _report_with_saved_advice()
    report = replace(
        report,
        rule_reasons=("本次技術線索原句", "已保存 Rule 原句", "本次技術線索原句"),
        ml=StockMLSnapshotDTO(
            status="degraded",
            h5_status="not_mature",
            target_metric="benchmark_excess_after_standard_80bp_cost",
            predicted_benchmark_excess_return_bp={"H5": -100},
            research_only=True,
            formal_qualified=False,
        ),
    )
    context = _context(scope="current_stock_research")
    view = _view_for(report, context)
    try:
        current_text = view.summary_focus.reasons_label.text()
        saved_text = view.summary_saved_advice_label.text()

        assert "本次技術線索（查詢日 2026-09-08；各欄資料日另列）" in current_text
        assert current_text.count("本次技術線索原句") == 1
        assert "已保存 Rule 原句" not in current_text
        assert "結果尚未成熟" in module._report_pending_text(report)
        assert "結果尚未成熟" not in current_text
        assert "當時保存的推薦判斷" in saved_text
        assert "保存支持原句" in saved_text
        assert "保存反對原句" in saved_text
        assert "保存支持原句" in view.summary_saved_advice_label.toolTip()
        assert "保存反對原句" in view.summary_saved_advice_label.toolTip()
    finally:
        view.close()


def test_query_date_is_not_mislabeled_as_market_data_date():
    query_date = "2026-10-19"
    market_date = "2026-09-23"
    report = _report_with_saved_advice()
    point = replace(report.price_points[-1], data_date=market_date)
    report = replace(
        report,
        as_of=query_date,
        price_points=(point,),
        technical=StockTechnicalSnapshotDTO(
            data_date=market_date,
            indicators=(
                StockMetricDTO(
                    key="MA20",
                    label="MA20",
                    value=Decimal("320"),
                ),
            ),
        ),
        rule_reasons=("本次技術線索原句",),
    )
    view = _view_for(report, _context(scope="current_stock_research"))
    try:
        reasons = view.summary_focus.reasons_label.text()
        evidence = view.summary_focus.evidence_label.text()

        assert f"本次技術線索（查詢日 {query_date}；各欄資料日另列）" in reasons
        assert f"資料日 {query_date}" not in reasons
        assert f"{market_date} 收盤" in evidence
        assert "收盤高於 MA20" in evidence
        assert f"資料日 {query_date}" not in evidence
        assert query_date not in evidence
    finally:
        view.close()


def test_available_h20_keeps_existing_model_reasons_branch():
    report, context, evidence, _now = _current_h20_case()
    view = _view_for(report, context)
    try:
        view._personal_h20_evidence = evidence
        view._render_product_summary(report)
        expected = module.build_stock_research_product_summary(report, evidence)

        assert "模型研究依據（H20）" in view.summary_focus.reasons_label.text()
        for reason in expected.reasons:
            assert reason in view.summary_focus.reasons_label.text()
        assert "待驗證條件" not in view.summary_focus.reasons_label.text()
    finally:
        view.close()


@pytest.mark.parametrize(
    "case",
    ("not_selected", "stock_mismatch", "decision_date", "data_date", "source_changed"),
)
def test_saved_advice_summary_fails_closed_when_binding_is_missing_or_mismatched(case):
    report = _report_with_saved_advice()
    context = _context()
    if case == "not_selected":
        context = replace(context, result_id="")
    elif case == "stock_mismatch":
        context = replace(context, stock_code="2330")
    elif case == "decision_date":
        context = replace(context, decision_date="2026-09-07")
    elif case == "data_date":
        context = replace(context, data_date="2026-09-07")
    view = _view_for(report, context)
    try:
        if case == "source_changed":
            changed = replace(context, source_id="different-source")
            view._loaded_context_identity = view._context_identity(changed, report.stock_code)
        view._render_product_summary(report)

        rendered = view.summary_saved_advice_label.text()
        assert "保存支持原句" not in rendered
        assert "保存反對原句" not in rendered
        assert "保存支持原句" not in view.summary_saved_advice_label.toolTip()
        assert "當時保存的推薦判斷" in view.summary_focus.reasons_label.text()
        assert "Rule" not in view.summary_focus.reasons_label.text()
        if case == "not_selected":
            assert "尚未明確選取保存來源" in rendered
        else:
            assert "理由不顯示" in rendered
    finally:
        view.close()


def test_missing_counter_reason_is_not_support_and_full_advice_stays_in_tooltip():
    report = _report_with_saved_advice()
    original_reason = "逐字保存的支持理由，" * 8
    recommendation = replace(
        report.advice.recommendation,
        why_reasons=(original_reason,),
        why_not_reasons=(),
    )
    report = replace(
        report,
        advice=replace(report.advice, recommendation=recommendation),
    )
    view = _view_for(report, _context())
    try:
        summary = view.summary_saved_advice_label.text()
        tooltip = view.summary_saved_advice_label.toolTip()

        assert "未提供反對理由" in summary
        assert "缺少反對證據不代表支持" in summary
        assert original_reason not in summary
        assert original_reason in tooltip
    finally:
        view.close()


def test_empty_risk_semantics_and_saved_advice_summary_clear_on_loading_failure_and_switch():
    report = _report_with_saved_advice()
    context = _context()
    view = _view_for(report, context)
    try:
        assert "不代表沒有風險" in view.summary_focus.risk_label.text()
        assert "保存支持原句" in view.summary_saved_advice_label.text()

        view._active_code = report.stock_code
        view._request_id = 2
        view._set_loading_state(report.stock_code)
        assert view.summary_saved_advice_label.text() == ""
        assert view.summary_saved_advice_label.toolTip() == ""

        view._render_report(report)
        assert "保存支持原句" in view.summary_saved_advice_label.text()
        view._on_report_error(2, report.stock_code, "temporary source failure")
        assert view.summary_saved_advice_label.text() == ""
        assert view.summary_saved_advice_label.toolTip() == ""

        view._render_report(report)
        view._active_code = "2330"
        view._request_id = 3
        view._set_loading_state("2330")
        assert view._loaded_report is None
        assert view.summary_saved_advice_label.text() == ""
        assert view.summary_saved_advice_label.toolTip() == ""
    finally:
        view.close()
