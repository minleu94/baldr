from datetime import date
from decimal import Decimal

from data_module.contracts.fundamental import SourceDiagnostic, SourceDiagnosticKind
from decision_module.factors.factor_dtos import FactorQuality, MissingPolicy
from decision_module.factors.factor_gate import FactorGate
from decision_module.factors.fundamental_adapters import (
    FundamentalObservation,
    build_revenue_yoy_factor,
    source_diagnostics_to_factor_diagnostics,
)


def test_revenue_yoy_factor_preserves_available_date_contract():
    observation = FundamentalObservation(
        stock_code="2330",
        period="2026-05",
        as_of_date=date(2026, 5, 31),
        announced_date=date(2026, 6, 10),
        available_date=date(2026, 6, 10),
        value=Decimal("12.34"),
        source="financial_data.monthly_revenue_csv",
        source_version="fundamental-source-inventory-2026-06-16",
        quality=FactorQuality.OBSERVED,
    )

    result = build_revenue_yoy_factor(observation)

    assert not result.diagnostics
    assert len(result.records) == 1
    record = result.records[0]
    assert record.factor_name == "fundamental.revenue_yoy"
    assert record.stock_code == "2330"
    assert record.as_of_date == date(2026, 5, 31)
    assert record.available_date == date(2026, 6, 10)
    assert record.value == Decimal("12.34")
    assert record.score_bp is None
    assert record.quality == FactorQuality.OBSERVED
    assert record.missing_policy == MissingPolicy.SKIP
    assert record.source_version == "fundamental-source-inventory-2026-06-16"
    assert record.metadata["period"] == "2026-05"
    assert record.metadata["announced_date"] == date(2026, 6, 10)
    assert record.metadata["source"] == "financial_data.monthly_revenue_csv"


def test_revenue_yoy_factor_reports_missing_available_date_without_record():
    observation = FundamentalObservation(
        stock_code="2330",
        period="2026-05",
        as_of_date=date(2026, 5, 31),
        announced_date=None,
        available_date=None,
        value=Decimal("12.34"),
        source="financial_data.monthly_revenue_csv",
        source_version="fundamental-source-inventory-2026-06-16",
        quality=FactorQuality.DEGRADED,
    )

    result = build_revenue_yoy_factor(observation)

    assert result.records == ()
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "fundamental.missing_available_date"
    assert result.diagnostics[0].factor_name == "fundamental.revenue_yoy"
    assert result.diagnostics[0].stock_code == "2330"


def test_revenue_yoy_factor_gate_skips_future_available_date():
    observation = FundamentalObservation(
        stock_code="2330",
        period="2026-05",
        as_of_date=date(2026, 5, 31),
        announced_date=date(2026, 6, 20),
        available_date=date(2026, 6, 20),
        value=Decimal("12.34"),
        source="financial_data.monthly_revenue_csv",
        source_version="fundamental-source-inventory-2026-06-16",
        quality=FactorQuality.OBSERVED,
    )

    build_result = build_revenue_yoy_factor(observation)
    gate_result = FactorGate().validate_for_decision(
        build_result.records,
        decision_date=date(2026, 6, 14),
    )

    assert gate_result.accepted == ()
    assert len(gate_result.skipped) == 1
    assert gate_result.diagnostics[0].code == "factor.skipped_lookahead"


def test_source_diagnostic_adapter_preserves_order_and_legacy_factor_names():
    source_diagnostics = (
        SourceDiagnostic(
            code="monthly_revenue_availability.fetch_failed",
            stock_code="",
            message="twse failed",
            kind=SourceDiagnosticKind.AVAILABILITY_HISTORY,
            market="twse",
        ),
        SourceDiagnostic(
            code="fundamental_revenue.invalid_revenue",
            stock_code="2330",
            message="invalid revenue",
            kind=SourceDiagnosticKind.MONTHLY_REVENUE,
            period="2026-05",
        ),
        SourceDiagnostic(
            code="monthly_revenue_snapshot.fetch_failed",
            stock_code="",
            message="tpex failed",
            kind=SourceDiagnosticKind.MONTHLY_REVENUE_SNAPSHOT,
            market="tpex",
        ),
    )

    diagnostics = source_diagnostics_to_factor_diagnostics(source_diagnostics)

    assert tuple(
        (item.code, item.factor_name, item.stock_code, item.message)
        for item in diagnostics
    ) == (
        (
            "monthly_revenue_availability.fetch_failed",
            "fundamental.availability.twse",
            "",
            "twse failed",
        ),
        (
            "fundamental_revenue.invalid_revenue",
            "fundamental.revenue",
            "2330",
            "invalid revenue",
        ),
        (
            "monthly_revenue_snapshot.fetch_failed",
            "fundamental.monthly_revenue_snapshot.tpex",
            "",
            "tpex failed",
        ),
    )
