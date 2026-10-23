"""只核對 Opus UI gallery fixture 的原值契約與唯讀快照 round trip。"""

from decimal import Decimal
import json

from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_dtos import (
    StockMetricDTO,
    StockPricePointDTO,
    StockResearchReportDTO,
)
from app_module.stock_research_report_snapshot_codec import (
    create_stock_research_report_projection_snapshot,
    read_stock_research_report_projection_snapshot,
)
from tests.opus_ux_review_fixture import full_research_report


def test_full_report_fixture_contains_explicit_qa_sources_and_complete_visual_rows():
    report = full_research_report()

    assert type(report) is StockResearchReportDTO
    assert report.stock_code == "2330"
    assert report.stock_name == "QA完整研究示意（非正式資料）"
    assert report.read_only is True
    assert report.price_points and all(type(item) is StockPricePointDTO for item in report.price_points)
    assert all(type(item.close_price) is Decimal for item in report.price_points)
    assert all(type(item.change) is Decimal for item in report.price_points)
    assert all(type(item.volume) is int for item in report.price_points)
    assert {item.period for item in report.fundamentals if item.kind == "monthly_revenue"} == {
        "2026-05", "2026-07", "2026-09",
    }
    assert len(report.fundamental_comparisons) == 1
    assert len(report.institutional) == 9
    assert len(report.credit) == 6
    assert len(report.shareholding) == 4
    assert len(report.flows) == 15
    assert report.position is not None and report.position.is_holding is True
    assert report.position.unrealized_pnl == Decimal("-100000")
    assert report.position.current_price == Decimal("1100")
    assert report.position.average_cost == Decimal("1200")

    for item in (*report.institutional, *report.credit, *report.shareholding):
        assert type(item) is StockMetricDTO
        assert item.source_id.startswith("qa.fixture.")
        assert item.data_as_of
        assert item.available_at
        assert item.quality == "observed"
    assert all(item.source_id.startswith("qa.fixture.") and item.available_at for item in report.flows)
    assert all(item.source_id.startswith("qa.fixture.") and item.available_at for item in report.price_points)
    assert all("QA示意" in item.source_label for item in report.sources)
    assert all("QA示意" in item.label for item in report.sections)
    assert all(item.historical_pit_eligible is False for item in report.sources)

    tier_metric = next(item for item in report.shareholding if item.key == "shareholding_tiers")
    tier_rows = json.loads(tier_metric.value_text)
    assert [row["tier"] for row in tier_rows] == list(range(1, 18))
    assert tier_rows[0]["holding_ratio_bp"] == 0
    assert tier_rows[15]["tier"] == 16
    assert tier_rows[16]["tier"] == 17
    assert {item.net_shares for item in report.flows} >= {-10000, 0, 10000}


def test_snapshot_save_and_reopen_preserve_the_same_report_and_context():
    report = full_research_report()
    context = ResearchStockContextDTO(
        stock_code=report.stock_code,
        stock_name=report.stock_name,
        decision_date=report.as_of,
        data_date="2026-10-21",
        source_kind="qa_ui_fixture",
        source_label="[QA示意] 完整個股研究 fixture",
        source_workspace="stock_research",
    )

    snapshot = create_stock_research_report_projection_snapshot(report, context)
    reopened = read_stock_research_report_projection_snapshot(
        snapshot.canonical_json,
        expected_identity_sha256=snapshot.identity_sha256,
    )

    assert snapshot.stock_code == report.stock_code == context.stock_code
    assert reopened.identity_sha256 == snapshot.identity_sha256
    assert reopened.report == report
    assert reopened.context == context
    assert reopened.report.price_points == report.price_points
    assert reopened.report.fundamentals == report.fundamentals
    assert reopened.report.institutional == report.institutional
    assert reopened.report.credit == report.credit
    assert reopened.report.shareholding == report.shareholding
    assert reopened.report.flows == report.flows
    assert reopened.report.position == report.position
