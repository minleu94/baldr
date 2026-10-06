from dataclasses import replace
from typing import Literal

import pytest

from app_module.recommendation.personal_h20_product_evidence import (
    PersonalH20ProductEvidence,
)
from app_module.stock_research_product_summary import (
    ProductResearchSummary,
    build_stock_research_product_summary,
)
from app_module.stock_research_report_dtos import (
    ReportFreshness,
    ReportSectionStatus,
    StockMLSnapshotDTO,
    StockPositionSnapshotDTO,
    StockPricePointDTO,
    StockReportSectionDTO,
    StockResearchReportDTO,
)


def _h20(
    *,
    stock_code: str = "2382",
    status: Literal["available", "pending", "disabled", "unavailable"] = "available",
    gross_return_bp: int | None = 684,
    reason: str = "自然結果待原 entry 與 20 交易日核驗",
) -> PersonalH20ProductEvidence:
    if status != "available":
        return PersonalH20ProductEvidence(stock_code, status, reason)
    return PersonalH20ProductEvidence(
        stock_code,
        "available",
        reason,
        gross_return_bp,
        "2026-10-07",
        "2026-10-06",
        "2026-10-05",
        "2026-10-06T16:42:07+00:00",
        "model-v1",
        "sample-2382",
        "prediction-2382",
    )


def _saved_h20_report() -> StockResearchReportDTO:
    return StockResearchReportDTO(
        stock_code="2382",
        stock_name="廣達",
        as_of="2026-10-07",
        sections=(
            StockReportSectionDTO(
                "price", "價格", ReportSectionStatus.AVAILABLE.value,
                data_as_of="2026-10-06", freshness=ReportFreshness.FRESH.value,
            ),
            StockReportSectionDTO(
                "fundamentals", "基本面", ReportSectionStatus.PARTIAL.value,
                data_as_of="2026-10-03", freshness=ReportFreshness.STALE.value,
            ),
        ),
        price_points=(StockPricePointDTO(data_date="2026-10-07"),),
        position=StockPositionSnapshotDTO(
            is_holding=True,
            health_status="WATCH",
            health_reasons=("condition_result_missing",),
        ),
        ml=StockMLSnapshotDTO(
            status="available",
            target_metric="benchmark_excess_after_standard_80bp_cost",
            predicted_benchmark_excess_return_bp={"H5": -100},
            target_round_trip_cost_bp=80,
            target_buy_side_cost_bp=25,
            target_sell_side_cost_bp=55,
        ),
        rule_reasons=("收盤站回既有研究條件",),
        research_context={
            "source_kind": "personal_h20_saved_cohort",
        "stock_code": "2382",
            "source_id": "prediction-2382",
            "source_version": "contract-v1",
            "decision_date": "2026-10-07",
            "data_date": "2026-10-06",
            "profile_id": "model-v1",
            "source_snapshot_id": "cycle-20261007",
            "source_snapshot_hash": "sha256:" + "a" * 64,
        },
    )


def test_available_h20_summary_keeps_dates_cohort_holdings_and_h5_separate() -> None:
    summary = build_stock_research_product_summary(_saved_h20_report(), _h20())

    assert isinstance(summary, ProductResearchSummary)
    assert "20 個交易日未扣成本毛報酬 +6.84%" in summary.conclusion
    assert summary.reasons[0].startswith("個股報告既有研究條件（非 H20 模型歸因）")
    assert "未扣成本" in summary.risks
    assert "待檢視" in summary.holding_relation
    assert "比較同份 H20 候選" in summary.next_step
    assert any("資料完整度" in line and "基本面" in line for line in summary.status_lines)
    assert any("資料時效" in line and "基本面" in line for line in summary.status_lines)
    assert any("2026-10-07" in line and "2026-10-06" in line and "2026-10-05" in line
               for line in summary.status_lines)
    assert any("成熟" in line and "entry" in line for line in summary.status_lines)
    assert any("Advice、權重、勝率或買賣指令" in line for line in summary.status_lines)
    assert any("-100 bp" in note and "落後基準 1.00 個百分點" in note for note in summary.advanced_notes)
    assert any("總計 80 bp（買進 25 bp、賣出 55 bp）" in note for note in summary.advanced_notes)
    assert any("不換算為 H20 毛報酬" in note for note in summary.advanced_notes)
    assert any("H20 原始身分" in note and "sample-2382" in note for note in summary.advanced_notes)
    assert any("H20 同份候選名次與母體分母不在" in note for note in summary.advanced_notes)
    assert not any("SHA" in line or "sha256:" in line for line in summary.status_lines)


def test_missing_model_and_report_data_remain_distinct_from_zero_or_maturity() -> None:
    report = StockResearchReportDTO(
        stock_code="2330",
        sections=(
            StockReportSectionDTO(
                "price", "價格", ReportSectionStatus.MISSING.value,
                freshness=ReportFreshness.UNKNOWN.value,
            ),
        ),
    )

    summary = build_stock_research_product_summary(report)

    assert "價格缺少或讀取失敗" in summary.status_lines[0]
    assert "時效未核" in summary.status_lines[1]
    assert "沒有提供個人 H20" in summary.status_lines[2]
    assert "成熟狀態未知" in summary.status_lines[4]
    assert "不產生 Advice" in summary.status_lines[5]
    assert "+0.00%" not in summary.conclusion
    assert "未知不等於沒有持倉" in summary.holding_relation


def test_unavailable_h20_does_not_retain_or_reuse_an_old_estimate() -> None:
    summary = build_stock_research_product_summary(
        _saved_h20_report(),
        _h20(status="unavailable", reason="capture SHA256 mismatch"),
    )

    assert "無法核驗" in summary.status_lines[2]
    assert "+6.84%" not in summary.conclusion
    assert "不沿用其他日期的估計" in summary.status_lines[2]
    assert any("capture SHA256 mismatch" in note for note in summary.advanced_notes)


def test_h20_stock_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="股票代碼與個股報告不一致"):
        build_stock_research_product_summary(_saved_h20_report(), _h20(stock_code="2330"))


@pytest.mark.parametrize(
    "key,value",
    [
        ("stock_code", "2330"),
        ("profile_id", "different-model"),
        ("source_id", "different-prediction"),
        ("decision_date", "2026-10-08"),
        ("data_date", "2026-10-05"),
    ],
)
def test_saved_h20_cohort_identity_mismatch_is_rejected(key: str, value: str) -> None:
    report = _saved_h20_report()
    context = dict(report.research_context)
    context[key] = value

    with pytest.raises(ValueError, match="身分不一致或缺少"):
        build_stock_research_product_summary(replace(report, research_context=context), _h20())


def test_late_h20_readback_is_labelled_independent_from_a_newer_report_source() -> None:
    report = StockResearchReportDTO(
        stock_code="2382",
        as_of="2026-10-08",
        price_points=(StockPricePointDTO(data_date="2026-10-08"),),
        research_context={
            "source_kind": "daily_market_research_snapshot",
            "decision_date": "2026-10-08",
            "data_date": "2026-10-08",
            "daily_snapshot_cohort_id": "market-cohort-20261008",
        },
    )

    summary = build_stock_research_product_summary(report, _h20())

    assert "+6.84%" in summary.conclusion
    assert any("來源日 2026-10-06" in line for line in summary.status_lines)
    assert "獨立 H20 估計" in summary.status_lines[5]
    assert "回原 H20 名單核對" in summary.next_step
    assert any("報告資料日：2026-10-08" in note for note in summary.advanced_notes)


def test_conflicting_h5_values_are_not_presented_as_a_valid_estimate() -> None:
    report = _saved_h20_report()
    report = replace(
        report,
        ml=replace(report.ml, h5_benchmark_excess_after_standard_80bp_cost=-120),
    )

    summary = build_stock_research_product_summary(report, _h20())

    assert any("H5 原值欄位不一致" in note for note in summary.advanced_notes)
    assert not any("-100 bp" in note for note in summary.advanced_notes)


def test_wrong_runtime_type_is_rejected() -> None:
    with pytest.raises(TypeError, match="PersonalH20ProductEvidence"):
        build_stock_research_product_summary(_saved_h20_report(), object())  # type: ignore[arg-type]
