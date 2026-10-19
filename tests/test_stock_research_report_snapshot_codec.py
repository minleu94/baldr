from collections import UserDict
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

import pytest

import app_module.stock_research_report_snapshot_codec as codec
from app_module.advice_dtos import (
    AdviceAction,
    AdviceClassification,
    PortfolioAdviceDTO,
    RecommendationAdviceDTO,
)
from app_module.portfolio_research_stock_projection import (
    PortfolioScenarioStockProjection,
    PortfolioScenarioStockReference,
    PortfolioScenarioStockTarget,
)
from app_module.research_session.session_dtos import (
    ResearchRankContextDTO,
    ResearchStockContextDTO,
)
from app_module.stock_research_report_dtos import (
    ReportFreshness,
    ReportQuality,
    ReportSectionStatus,
    StockAdviceSnapshotDTO,
    StockEvidenceEventDTO,
    StockFlowObservationDTO,
    StockFundamentalComparisonDTO,
    StockFundamentalObservationDTO,
    StockMarketStatusEvidenceDTO,
    StockMarketStatusSnapshotDTO,
    StockMetricDTO,
    StockMLSnapshotDTO,
    StockOfficialAttentionDTO,
    StockOfficialAttentionRowDTO,
    StockOriginalRankingReportDTO,
    StockOutcomeDTO,
    StockPositionSnapshotDTO,
    StockPricePointDTO,
    StockReportSectionDTO,
    StockReportSourceDTO,
    StockResearchReportDTO,
    StockSavedSourceOptionDTO,
    StockTechnicalHistoryRowDTO,
    StockTechnicalSnapshotDTO,
    StockTradingRestrictionDTO,
)
from app_module.stock_research_report_snapshot_codec import (
    STOCK_RESEARCH_REPORT_PROJECTION_SNAPSHOT_SCHEMA_V1,
    StockResearchReportSnapshotCodecError,
    create_stock_research_report_projection_snapshot,
    read_stock_research_report_projection_snapshot,
)
from app_module.watchlist_analysis_service import WatchlistAnalysisDTO


def _scenario() -> tuple[
    PortfolioScenarioStockReference, PortfolioScenarioStockProjection
]:
    reference = PortfolioScenarioStockReference(
        account_kind="user_declared",
        portfolio_id="portfolio-qa",
        artifact_id="sha256:" + "a" * 64,
    )
    target = PortfolioScenarioStockTarget(
        scenario_kind="explicit_target",
        rule_requested_weight_bp=2500,
        target_weight_bp=2400,
        current_weight_bp=2000,
        gap_weight_bp=400,
        executable_shares=12,
        executable_amount=Decimal("1234.50"),
        estimated_cost=Decimal("8.64"),
        diagnostics=("原研究診斷",),
    )
    projection = PortfolioScenarioStockProjection(
        reference=reference,
        stock_code="2330",
        snapshot_id="snapshot-qa",
        account_as_of_date="2026-10-15",
        account_available_at="2026-10-15T13:00:00+08:00",
        decision_at="2026-10-16T09:00:00+08:00",
        account_source_hash="b" * 64,
        research_source_hash="c" * 64,
        context_source_hash="d" * 64,
        context_available_at="2026-10-15T13:30:00+08:00",
        cash_amount=Decimal("50000.00"),
        total_value=Decimal("250000.00"),
        quantity=100,
        mark_price=Decimal("1000.00"),
        market_value=Decimal("100000.00"),
        current_weight_bp=4000,
        health_state="unknown",
        health_known=False,
        targets=(target,),
    )
    return reference, projection


def _report(
    *,
    shared_daily_features=None,
    calibration_provenance=None,
) -> tuple[StockResearchReportDTO, ResearchStockContextDTO]:
    reference, projection = _scenario()
    fundamental = StockFundamentalObservationDTO(
        kind="income_statement",
        label="營收",
        metric_name="revenue",
        market="TWSE",
        period="2026Q2",
        as_of_date="2026-06-30",
        announced_date="2026-08-10",
        available_at="2026-08-10T16:00:00+08:00",
        observed_at="2026-08-11T09:00:00+08:00",
        value=Decimal("123.40"),
        value_text="123.40",
        unit="TWD",
        source_id="fundamentals-qa",
        source_version="v3",
        source_snapshot_hash="e" * 64,
        quality=ReportQuality.OBSERVED.value,
        period_basis="quarterly",
        basis_verified=True,
        aggregate_feature_eligible=False,
        formal_pit_eligible=False,
    )
    recommendation = RecommendationAdviceDTO(
        stock_code="2330",
        advice_action=AdviceAction.RESEARCH,
        classification=AdviceClassification.PROFESSIONAL_CANDIDATE,
        why_reasons=("保留既有理由",),
        warnings=("保留原警示",),
        decision_date="2026-10-15",
        data_as_of_date="2026-10-14",
        calibration_provenance=(
            calibration_provenance
            if calibration_provenance is not None
            else {"method": "原始說明"}
        ),
    )
    portfolio_advice = PortfolioAdviceDTO(
        stock_code="2330",
        advice_action=AdviceAction.RESEARCH,
        target_weight_bp=2000,
        current_weight_bp=None,
        weight_gap_bp=None,
        reasons=("權重仍未知",),
        diagnostics=("原始診斷",),
    )
    report = StockResearchReportDTO(
        stock_code="2330",
        stock_name="台積電",
        market="TWSE",
        industry="半導體",
        as_of="2026-10-15",
        generated_at="2026-10-16T10:15:00+08:00",
        sources=(
            StockReportSourceDTO(
                source_id="price-qa",
                source_label="固定價格來源",
                status=ReportSectionStatus.PARTIAL.value,
                quality=ReportQuality.DEGRADED.value,
                data_as_of="2026-10-15",
                available_at="2026-10-15T14:00:00+08:00",
                freshness=ReportFreshness.STALE.value,
                version="dataset-v4",
                row_count=2,
                limitations=("保留來源限制",),
                candidate_only=True,
                historical_pit_eligible=False,
            ),
        ),
        sections=(
            StockReportSectionDTO(
                section_id="price",
                label="價格",
                status=ReportSectionStatus.PARTIAL.value,
                summary="資料不完整",
                data_as_of="2026-10-15",
                freshness=ReportFreshness.UNKNOWN.value,
                source_ids=("price-qa",),
                limitations=("不補值",),
            ),
        ),
        available_modules=("price", "technical"),
        attention_reasons=("來源有缺件",),
        key_risks=("保留風險原文",),
        limitations=("只保存顯示投影",),
        price_points=(
            StockPricePointDTO(
                data_date="2026-10-15",
                open_price=Decimal("999.10"),
                high_price=Decimal("1010.00"),
                low_price=Decimal("990.25"),
                close_price=Decimal("1001.20"),
                volume=123456,
                turnover=Decimal("123456789.50"),
                change=Decimal("1.20"),
                available_at="2026-10-15T14:00:00+08:00",
                source_id="price-qa",
                source_snapshot_hash="f" * 64,
                quality=ReportQuality.OBSERVED.value,
            ),
        ),
        technical=StockTechnicalSnapshotDTO(
            data_date="2026-10-15",
            indicators=(
                StockMetricDTO(
                    key="ma20",
                    label="20日均線",
                    value=Decimal("995.125"),
                    value_text="995.125",
                    unit="TWD",
                    data_as_of="2026-10-15",
                    available_at="2026-10-15T14:00:00+08:00",
                    source_id="technical-qa",
                ),
            ),
            available_at="2026-10-15T14:00:00+08:00",
            source_id="technical-qa",
            limitations=("保留技術限制",),
        ),
        fundamentals=(fundamental,),
        flows=(
            StockFlowObservationDTO(
                data_date="2026-10-15",
                branch_name="外資",
                buy_shares=1000,
                sell_shares=800,
                net_shares=200,
                buy_amount_thousand=Decimal("10.25"),
                sell_amount_thousand=Decimal("8.20"),
                net_amount_thousand=Decimal("2.05"),
                trade_type="現貨",
                available_at="2026-10-15T16:00:00+08:00",
                source_id="flow-qa",
            ),
        ),
        institutional=(
            StockMetricDTO(key="trust", label="投信", value=Decimal("20")),
        ),
        credit=(StockMetricDTO(key="margin", label="融資", value=None),),
        shareholding=(StockMetricDTO(key="custody", label="集保", value=Decimal("40.5")),),
        events=(
            StockEvidenceEventDTO(
                event_id="event-qa",
                event_date="2026-10-15",
                decision_date="2026-10-16",
                event_type="research_observation",
                event_family="manual",
                source_type="saved_source",
                source_id="event-source",
                source_version="v1",
                data_quality="partial",
                as_of_date="2026-10-15",
                available_at="2026-10-15T17:00:00+08:00",
                reasons=("原事件理由",),
                why_not_reasons=("原不成立理由",),
                risk_reasons=("原風險理由",),
                warnings=("原事件警示",),
                score_bp=None,
                outcomes=(
                    StockOutcomeDTO(
                        window_days=20,
                        outcome_status="unknown",
                        data_quality="missing",
                    ),
                ),
            ),
        ),
        position=StockPositionSnapshotDTO(
            is_holding=True,
            position_id="position-private",
            portfolio_id="portfolio-private",
            position_as_of="2026-10-15",
            quote_data_date="2026-10-15",
            quote_available_at="2026-10-15T14:00:00+08:00",
            quantity=Decimal("2.5"),
            average_cost=Decimal("900.00"),
            invested_amount=Decimal("2250.00"),
            current_price=Decimal("1001.20"),
            unrealized_pnl=Decimal("253.00"),
            unrealized_pnl_pct=Decimal("11.2444"),
            exposure_bp=1000,
            source_type="manual_portfolio",
            source_id="position-source",
            source_snapshot_hash="1" * 64,
            quote_source_snapshot_hash="2" * 64,
            opened_at="2026-05-01T09:00:00+08:00",
            last_trade_date="2026-05-01",
            health_status="unknown",
            health_label="待查",
            health_reasons=("缺少來源",),
            health_source_trace=("health-source",),
            exit_status="unavailable",
            exit_reasons=("不提供自動動作",),
            exit_research_only=True,
            exit_auto_action_allowed=False,
            limitations=("保留持倉限制",),
        ),
        market_status=StockMarketStatusSnapshotDTO(
            status="partial",
            listing_status="listed",
            market="TWSE",
            name="台積電",
            trading_restrictions=(
                StockTradingRestrictionDTO(
                    restriction_type="attention",
                    restriction_state="observed",
                    published_date="2026-10-15",
                    source_id="status-source",
                    evidence_type="official",
                    source_data_dates=("2026-10-15",),
                    raw_sha256="3" * 64,
                ),
            ),
            status_evidence=(
                StockMarketStatusEvidenceDTO(
                    evidence_type="official_notice",
                    source_id="status-source",
                    observed_at="2026-10-15T18:00:00+08:00",
                    published_date="2026-10-15",
                    source_data_dates=("2026-10-15",),
                    raw_sha256="4" * 64,
                ),
            ),
            source_ids=("status-source",),
            source_data_dates=("2026-10-15",),
            observed_at="2026-10-15T18:00:00+08:00",
            source_warnings=("公告來源部分缺漏",),
            partial_failure=True,
            scope="current_only",
            pit_eligible=False,
            limitations=("不是PIT證明",),
        ),
        advice=StockAdviceSnapshotDTO(
            status="partial",
            recommendation=recommendation,
            portfolio=portfolio_advice,
            saved_analysis=WatchlistAnalysisDTO(
                stock_code="2330",
                status="unknown",
                result_id="saved-run-qa",
                message="未重新計算",
                data_date="2026-10-14",
            ),
            rule_reasons=("既有rule理由",),
            ml_reasons=("既有ML理由",),
            agreement="not_comparable",
            limitations=("保留Advice限制",),
        ),
        ml=StockMLSnapshotDTO(
            status="degraded",
            model_version="model-v2",
            inference_at="2026-10-15T18:00:00+08:00",
            source_id="model-source",
            predicted_benchmark_excess_return_bp={"H5": -120},
            research_only=True,
            historical_pit_eligible=False,
            formal_qualified=False,
            production_action_allowed=False,
            limitations=("未核PIT",),
        ),
        rule_reasons=("原規則理由",),
        saved_source_options=(
            StockSavedSourceOptionDTO("saved-run-qa", "固定保存來源", "2026-10-15", "2026-10-14"),
        ),
        shared_daily_features=(
            shared_daily_features
            if shared_daily_features is not None
            else {
                "nested": ["原文", {"keep": True}],
                "display_float": 0.1,
                "display_decimal": Decimal("1.2300"),
                "display_enum": ReportQuality.STALE,
                "display_tuple": ("first", 2),
            }
        ),
        research_context={"decision_date": "2026-10-16", "data_date": "2026-10-15"},
        original_ranking=StockOriginalRankingReportDTO(
            status="unknown", reason="原排名未知", research_only=True,
        ),
        read_only=True,
        technical_history=(
            StockTechnicalHistoryRowDTO(
                stock_code="2330",
                source_id="technical-qa",
                data_date="2026-10-15",
                source_row_hash="5" * 64,
                ma20=Decimal("995.125"),
                ma60=None,
                available_at="2026-10-15T14:00:00+08:00",
            ),
        ),
        saved_technical_chart_json=' {"exact": "原圖表文字"}\n',
        portfolio_scenario=projection,
        official_attention=StockOfficialAttentionDTO(
            status="candidate_only",
            query_date="2026-10-15",
            source_url="https://example.invalid/frozen",
            rows=(
                StockOfficialAttentionRowDTO(
                    stock_code="2330",
                    stock_name="台積電",
                    official_date_original_text="115/10/15",
                    announcement_count_original_text="2",
                    reason_text="原始理由",
                    closing_price_original_text="1,001.20",
                    pe_original_text="20.5",
                ),
            ),
            manifest_sha256="6" * 64,
            receipt_sha256="7" * 64,
            available_hour="2026-10-15T20:00:00+08:00",
            availability_basis="selected_source_only",
            limitations=("不得用於PIT",),
        ),
        fundamental_comparisons=(
            StockFundamentalComparisonDTO(
                stock_code="2330",
                metric_name="revenue",
                label="營收比較",
                current_period="2026Q2",
                prior_period="2026Q1",
                current_value=Decimal("123.40"),
                prior_value=Decimal("110.00"),
                value_unit="TWD",
                change_value=Decimal("12.1818"),
                change_unit="percent",
                current_source_id="fundamentals-qa",
                current_source_version="v3",
                source_id="fundamentals-prior-qa",
                source_version="v2",
                source_snapshot_hash="8" * 64,
                available_at="2026-08-10T16:00:00+08:00",
                note="保留原比較說明",
            ),
        ),
    )
    context = ResearchStockContextDTO(
        stock_code="2330",
        stock_name="台積電",
        decision_date="2026-10-16",
        data_date="2026-10-15",
        result_id="report-run-qa",
        source_snapshot_id=reference.artifact_id,
        source_snapshot_hash="9" * 64,
        source_kind="portfolio_research_scenario",
        source_label="已保存情境",
        portfolio_scenario_ref=reference,
    )
    return report, context


def _canonical_json(wire: object) -> str:
    return json.dumps(wire, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: str | bytes) -> str:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(raw).hexdigest()


def _rank_context() -> ResearchRankContextDTO:
    universe_json = _canonical_json({"stock_codes": ["2330"]})
    engine_json = _canonical_json({"fixture": "codec-test"})
    return ResearchRankContextDTO(
        rank_kind="original_stock_ranking",
        period="day",
        direction="strong",
        rank_snapshot_id="a" * 64,
        source_hash="b" * 64,
        ranking_root="rank-root",
        snapshot_root="snapshot-root",
        decision_date="2026-10-16",
        parent_snapshot_id="c" * 64,
        parent_snapshot_hash="d" * 64,
        parent_cohort_id="cohort-qa",
        selected_stock_code="2330",
        selected_rank=1,
        comparison_date="2026-10-15",
        latest_date="2026-10-16",
        comparison_window_dates=("2026-10-15", "2026-10-16"),
        comparison_window_rule="two fixture dates",
        volume_reference_point_count=2,
        declared_stock_codes=("2330",),
        eligible_stock_codes=("2330",),
        missing_rank_stock_codes=(),
        research_universe_json=universe_json,
        research_universe_sha256=_sha256(universe_json),
        method_name="fixture-method",
        method_version="1",
        method_contract_sha256="e" * 64,
        engine_file_sha256="f" * 64,
        engine_parameters_json=engine_json,
        engine_parameters_sha256=_sha256(engine_json),
        source_schema_sha256="1" * 64,
        selected_input_fingerprint_sha256="2" * 64,
    )


def _read_mutated(snapshot, mutate):
    wire = json.loads(snapshot.canonical_json)
    mutate(wire)
    payload = _canonical_json(wire)
    return read_stock_research_report_projection_snapshot(
        payload, expected_identity_sha256=_sha256(payload)
    )


def test_full_report_and_context_round_trip_keep_typed_fields_and_canonical_identity() -> None:
    report, context = _report()
    snapshot = create_stock_research_report_projection_snapshot(report, context)

    assert snapshot.stock_code == "2330"
    assert snapshot.identity_sha256 == _sha256(snapshot.canonical_json)
    wire = json.loads(snapshot.canonical_json)
    assert wire["schema_version"] == STOCK_RESEARCH_REPORT_PROJECTION_SNAPSHOT_SCHEMA_V1
    assert snapshot.canonical_json == _canonical_json(wire)
    assert snapshot.report == report
    assert snapshot.context == context
    assert snapshot.report.position.position_id == "position-private"
    assert snapshot.report.position.portfolio_id == "portfolio-private"
    assert snapshot.report.sources[0].candidate_only is True
    assert snapshot.report.sources[0].historical_pit_eligible is False
    assert snapshot.report.market_status.source_warnings == ("公告來源部分缺漏",)
    assert snapshot.report.advice.recommendation.advice_action is AdviceAction.RESEARCH
    assert snapshot.report.advice.recommendation.classification is (
        AdviceClassification.PROFESSIONAL_CANDIDATE
    )
    assert snapshot.report.ml.predicted_benchmark_excess_return_bp == {"H5": -120}
    assert snapshot.report.price_points[0].close_price == Decimal("1001.20")
    assert snapshot.report.shared_daily_features["display_decimal"] == Decimal("1.2300")
    assert snapshot.report.shared_daily_features["display_float"].hex() == (0.1).hex()
    assert snapshot.report.shared_daily_features["display_enum"] is ReportQuality.STALE
    assert snapshot.report.shared_daily_features["display_tuple"] == ("first", 2)
    assert snapshot.report.saved_technical_chart_json == ' {"exact": "原圖表文字"}\n'
    assert snapshot.context.portfolio_scenario_ref == snapshot.report.portfolio_scenario.reference
    assert snapshot.report.official_attention.rows[0].closing_price_original_text == "1,001.20"
    assert snapshot.report.fundamental_comparisons[0].current_value == Decimal("123.40")
    bytes_read = read_stock_research_report_projection_snapshot(
        snapshot.canonical_json.encode("utf-8"),
        expected_identity_sha256=snapshot.identity_sha256,
    )
    assert bytes_read.report == report
    assert bytes_read.context == context

    price_point_node = json.loads(snapshot.canonical_json)["report"]["fields"]["price_points"]
    assert price_point_node["$type"] == "tuple"
    assert price_point_node["items"][0]["fields"]["close_price"] == {
        "$type": "decimal",
        "value": "1001.20",
    }


def test_create_and_each_read_reconstruct_mutable_mappings_without_caller_aliases() -> None:
    mutable_features = {"nested": ["before", {"value": 1}]}
    report, context = _report(shared_daily_features=mutable_features)
    snapshot = create_stock_research_report_projection_snapshot(report, context)

    mutable_features["nested"][0] = "after"
    mutable_features["nested"][1]["value"] = 2
    assert snapshot.report.shared_daily_features["nested"] == ["before", {"value": 1}]
    assert snapshot.report.shared_daily_features is not mutable_features
    assert snapshot.report.shared_daily_features["nested"] is not mutable_features["nested"]

    first_read = read_stock_research_report_projection_snapshot(
        snapshot.canonical_json, expected_identity_sha256=snapshot.identity_sha256
    )
    second_read = read_stock_research_report_projection_snapshot(
        snapshot.canonical_json, expected_identity_sha256=snapshot.identity_sha256
    )
    assert first_read is not second_read
    assert first_read.report is not second_read.report
    assert first_read.report.shared_daily_features is not second_read.report.shared_daily_features
    assert first_read.report.shared_daily_features["nested"] is not (
        second_read.report.shared_daily_features["nested"]
    )
    assert first_read.canonical_json == second_read.canonical_json == snapshot.canonical_json


def test_mappingproxy_is_supported_but_custom_mapping_hooks_are_not_called() -> None:
    report, context = _report(shared_daily_features=MappingProxyType({"fixed": 3}))
    snapshot = create_stock_research_report_projection_snapshot(report, context)
    assert snapshot.report.shared_daily_features == {"fixed": 3}

    class ExplosiveMapping(UserDict):
        def items(self):
            raise AssertionError("custom mapping code must not be called")

    invalid, invalid_context = _report(
        shared_daily_features=ExplosiveMapping({"fixed": 3})
    )
    with pytest.raises(StockResearchReportSnapshotCodecError, match="Mapping field"):
        create_stock_research_report_projection_snapshot(invalid, invalid_context)


def test_any_nested_values_reject_non_json_objects_and_nonfinite_numbers() -> None:
    forbidden = (
        b"bytes",
        Path("relative/path"),
        date(2026, 10, 15),
        datetime(2026, 10, 15, 12, 0),
        object(),
        float("nan"),
        float("inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
    )
    for item in forbidden:
        report, context = _report(shared_daily_features={"forbidden": item})
        with pytest.raises(StockResearchReportSnapshotCodecError):
            create_stock_research_report_projection_snapshot(report, context)

    report, context = _report(shared_daily_features={1: "Mapping key is not text"})
    with pytest.raises(StockResearchReportSnapshotCodecError, match="Mapping keys"):
        create_stock_research_report_projection_snapshot(report, context)


def test_rank_context_is_explicitly_rejected_without_resolving_paths(monkeypatch) -> None:
    rank = _rank_context()
    rank_context = ResearchStockContextDTO(
        stock_code="2330",
        decision_date="2026-10-16",
        source_kind="original_stock_ranking",
        rank_context=rank,
    )
    report, _ = _report()

    path_calls = []

    def observe_resolve(self, *args, **kwargs):
        path_calls.append(self)
        return self

    monkeypatch.setattr(Path, "resolve", observe_resolve)
    with pytest.raises(StockResearchReportSnapshotCodecError, match="ResearchRankContextDTO"):
        create_stock_research_report_projection_snapshot(report, rank_context)
    assert path_calls == []

    base = create_stock_research_report_projection_snapshot(report)
    wire = json.loads(base.canonical_json)
    wire["context"] = {
        "$type": "dataclass",
        "class": "app_module.research_session.session_dtos.ResearchStockContextDTO",
        "fields": {
            "stock_code": "2330",
            "rank_context": {
                "$type": "dataclass",
                "class": "app_module.research_session.session_dtos.ResearchRankContextDTO",
                "fields": {},
            },
        },
    }
    payload = _canonical_json(wire)
    with pytest.raises(StockResearchReportSnapshotCodecError, match="ResearchRankContextDTO"):
        read_stock_research_report_projection_snapshot(
            payload, expected_identity_sha256=_sha256(payload)
        )
    assert path_calls == []


def test_context_stock_mismatch_is_rejected() -> None:
    report, context = _report()
    with pytest.raises(StockResearchReportSnapshotCodecError, match="stock identity mismatch"):
        create_stock_research_report_projection_snapshot(
            report, replace(context, stock_code="2317", portfolio_scenario_ref=None,
                            source_kind="manual_research", source_snapshot_id="")
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda wire: wire["report"]["fields"]["portfolio_scenario"]["fields"].__setitem__(
                "cash_amount", "50000.00"
            ),
            "decimal",
        ),
        (
            lambda wire: wire["report"]["fields"]["price_points"]["items"][0]["fields"].__setitem__(
                "volume", True
            ),
            "Union",
        ),
    ],
)
def test_canonical_outer_payload_with_nested_wrong_type_is_rejected(mutate, message) -> None:
    report, context = _report()
    snapshot = create_stock_research_report_projection_snapshot(report, context)
    with pytest.raises(StockResearchReportSnapshotCodecError, match=message):
        _read_mutated(snapshot, mutate)


def test_unknown_fields_classes_schema_duplicate_keys_and_sha_are_rejected() -> None:
    report, context = _report()
    snapshot = create_stock_research_report_projection_snapshot(report, context)

    with pytest.raises(StockResearchReportSnapshotCodecError, match="unknown or missing field"):
        _read_mutated(
            snapshot,
            lambda wire: wire["report"]["fields"].__setitem__("not_a_report_field", "x"),
        )
    with pytest.raises(StockResearchReportSnapshotCodecError, match="class does not match"):
        _read_mutated(
            snapshot,
            lambda wire: wire["report"].__setitem__("class", "builtins.object"),
        )
    with pytest.raises(StockResearchReportSnapshotCodecError, match="unsupported report schema"):
        _read_mutated(
            snapshot,
            lambda wire: wire["report"]["fields"].__setitem__("schema_version", "future"),
        )

    duplicate = '{"schema_version":"x","schema_version":"y"}'
    with pytest.raises(StockResearchReportSnapshotCodecError, match="duplicate JSON"):
        read_stock_research_report_projection_snapshot(
            duplicate, expected_identity_sha256=_sha256(duplicate)
        )
    with pytest.raises(StockResearchReportSnapshotCodecError, match="SHA-256"):
        read_stock_research_report_projection_snapshot(
            snapshot.canonical_json, expected_identity_sha256="0" * 64
        )
    with pytest.raises(StockResearchReportSnapshotCodecError, match="lowercase SHA-256"):
        read_stock_research_report_projection_snapshot(
            snapshot.canonical_json, expected_identity_sha256="A" * 64
        )


def test_noncanonical_and_wrong_envelope_identity_are_rejected() -> None:
    report, context = _report()
    snapshot = create_stock_research_report_projection_snapshot(report, context)
    spaced = " " + snapshot.canonical_json
    with pytest.raises(StockResearchReportSnapshotCodecError, match="not canonical"):
        read_stock_research_report_projection_snapshot(
            spaced, expected_identity_sha256=_sha256(spaced)
        )

    with pytest.raises(StockResearchReportSnapshotCodecError, match="envelope/report stock"):
        _read_mutated(snapshot, lambda wire: wire.__setitem__("stock_code", "2317"))

    with pytest.raises(StockResearchReportSnapshotCodecError, match="read-only"):
        _read_mutated(
            snapshot,
            lambda wire: wire["report"]["fields"].__setitem__("read_only", False),
        )


def test_any_dataclass_enum_allowlists_prevent_unknown_nested_classes() -> None:
    report, context = _report()
    snapshot = create_stock_research_report_projection_snapshot(report, context)
    with pytest.raises(StockResearchReportSnapshotCodecError, match="Enum class"):
        _read_mutated(
            snapshot,
            lambda wire: wire["report"]["fields"]["shared_daily_features"]["items"][
                "display_enum"
            ].__setitem__("class", "builtins.object"),
        )


def test_short_float_hex_with_unbounded_exponent_is_rejected() -> None:
    report, context = _report()
    snapshot = create_stock_research_report_projection_snapshot(report, context)
    with pytest.raises(StockResearchReportSnapshotCodecError, match="invalid float hex"):
        _read_mutated(
            snapshot,
            lambda wire: wire["report"]["fields"]["shared_daily_features"]["items"][
                "display_float"
            ].__setitem__("hex", "0x1p999999999"),
        )


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff",
        "{" + "\"x\":NaN}",
        "{" + "\"x\":Infinity}",
    ],
)
def test_invalid_utf8_and_nonfinite_json_constants_are_rejected(payload) -> None:
    with pytest.raises(StockResearchReportSnapshotCodecError):
        read_stock_research_report_projection_snapshot(
            payload, expected_identity_sha256="0" * 64
        )


def test_payload_byte_depth_integer_text_node_and_display_text_limits_are_enforced() -> None:
    oversized = " " * (4 * 1024 * 1024 + 1)
    with pytest.raises(StockResearchReportSnapshotCodecError, match="4 MiB"):
        read_stock_research_report_projection_snapshot(
            oversized, expected_identity_sha256=_sha256(oversized)
        )
    oversized_bytes = b"\xff" * (4 * 1024 * 1024 + 1)
    with pytest.raises(StockResearchReportSnapshotCodecError, match="4 MiB"):
        read_stock_research_report_projection_snapshot(
            oversized_bytes, expected_identity_sha256=_sha256(oversized_bytes)
        )

    deep = "[" * 65 + "null" + "]" * 65
    with pytest.raises(StockResearchReportSnapshotCodecError, match="nesting"):
        read_stock_research_report_projection_snapshot(
            deep, expected_identity_sha256=_sha256(deep)
        )

    huge_integer = "9" * 257
    with pytest.raises(StockResearchReportSnapshotCodecError, match="integer text"):
        read_stock_research_report_projection_snapshot(
            huge_integer, expected_identity_sha256=_sha256(huge_integer)
        )

    report, context = _report(shared_daily_features={"many": [None] * 100_100})
    with pytest.raises(StockResearchReportSnapshotCodecError, match="node count"):
        create_stock_research_report_projection_snapshot(report, context)

    report, context = _report()
    with pytest.raises(StockResearchReportSnapshotCodecError, match="size limit"):
        create_stock_research_report_projection_snapshot(
            replace(report, saved_technical_chart_json="x" * (4 * 1024 * 1024 + 1)),
            context,
        )


def test_oversized_text_is_rejected_before_encode_or_json_dumps(monkeypatch) -> None:
    class ExplosiveText(str):
        def encode(self, *args, **kwargs):
            raise AssertionError("oversized text must be rejected before UTF-8 encoding")

    dumps_calls = []

    def unexpected_dumps(*args, **kwargs):
        dumps_calls.append(True)
        raise AssertionError("oversized text must be rejected before json.dumps")

    monkeypatch.setattr(codec.json, "dumps", unexpected_dumps)
    budget = codec._Budget()
    with pytest.raises(StockResearchReportSnapshotCodecError, match="size limit"):
        budget.text(ExplosiveText("x" * (4 * 1024 * 1024 + 1)))
    assert budget.quoted_text_bytes == 0
    assert dumps_calls == []


def test_reader_rejects_over_node_limit_before_json_loads(monkeypatch) -> None:
    escaped_syntax = '"' + ('\\"[]{}:,null' * 100_000) + '"'
    assert len(escaped_syntax.encode("utf-8")) < 4 * 1024 * 1024
    codec._check_raw_node_count(escaped_syntax)

    payload = "[" + ",".join(["null"] * 100_000) + "]"
    assert len(payload.encode("utf-8")) < 4 * 1024 * 1024
    loads_calls = []
    original_loads = codec.json.loads

    def track_loads(*args, **kwargs):
        loads_calls.append(True)
        return original_loads(*args, **kwargs)

    monkeypatch.setattr(codec.json, "loads", track_loads)
    with pytest.raises(StockResearchReportSnapshotCodecError, match="node count"):
        read_stock_research_report_projection_snapshot(
            payload, expected_identity_sha256=_sha256(payload)
        )
    assert loads_calls == []


def test_canonical_serialization_stops_when_incremental_size_exceeds_limit(monkeypatch) -> None:
    emitted: list[str] = []

    class TrackingEncoder(json.JSONEncoder):
        def iterencode(self, value, _one_shot=False):
            for part in super().iterencode(value, _one_shot):
                emitted.append(part)
                yield part

    def unexpected_dumps(*args, **kwargs):
        raise AssertionError("canonical serialization must use bounded iterencode")

    monkeypatch.setattr(codec.json, "JSONEncoder", TrackingEncoder)
    monkeypatch.setattr(codec.json, "dumps", unexpected_dumps)
    payload = {
        "c": "sentinel-after-limit",
        "b": "b" * (2 * 1024 * 1024),
        "a": "a" * (2 * 1024 * 1024),
    }
    with pytest.raises(StockResearchReportSnapshotCodecError, match="4 MiB"):
        codec._canonical_json(payload)
    assert emitted
    assert all("sentinel-after-limit" not in part for part in emitted)
