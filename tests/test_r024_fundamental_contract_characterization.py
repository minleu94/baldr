from __future__ import annotations

from datetime import date
from decimal import Decimal

from data_module.fundamental_statement_data import StatementItemRecord
from decision_module.factors.statement_semantic_mapping import map_statement_items_for_factors
from decision_module.factors.valuation_policy import calculate_industry_percentiles_bp
from decision_module.factors.factor_dtos import FactorQuality
from decision_module.factors.valuation_policy import (
    ValuationBand,
    ValuationObservation,
    classify_relative_valuation,
)


_SOURCE_VERSION = (
    "mops-t164-consolidated-statements-with-mops-ezsearch-publication-xbrl-row-codes.v3"
)


def _statement_record(
    item_code: str,
    item_name: str,
    xbrl_concept: str,
    *,
    value: str = "10",
    statement_type: str = "income_statement",
) -> StatementItemRecord:
    return StatementItemRecord(
        stock_code="2330",
        statement_type=statement_type,
        period="2026-Q2",
        as_of_date=date(2026, 6, 30),
        announced_date=date(2026, 8, 15),
        available_date=date(2026, 9, 8),
        item_code=item_code,
        item_name=item_name,
        value=Decimal(value),
        source="mops.t164sb01.statement",
        source_version=_SOURCE_VERSION + ":content:" + "a" * 64,
        legacy_quality_wire_value=FactorQuality.OBSERVED.value,
        report_basis="consolidated",
        item_code_source="mops.t164sb01.xbrl.row_code",
        item_code_lineage_sha256="sha256:" + "b" * 64,
        official_item_name=item_name,
        xbrl_concept=xbrl_concept,
        candidate_source_version=_SOURCE_VERSION,
        value_unit="TWD",
        value_scale=100,
    )


def test_r024_statement_aliases_units_and_scale_are_characterized() -> None:
    source_rows = (
        _statement_record("9750", "基本每股盈餘合計", "ifrs-full:BasicEarningsLossPerShare"),
        _statement_record("4000", "營業收入合計", "ifrs-full:Revenue"),
        _statement_record("5950", "營業毛利（毛損）淨額", "ifrs-full:GrossProfit"),
        _statement_record(
            "6900", "營業利益（損失）", "ifrs-full:ProfitLossFromOperatingActivities"
        ),
        _statement_record(
            "7900", "繼續營業單位稅前淨利（淨損）", "ifrs-full:ProfitLossBeforeTax"
        ),
        _statement_record("8200", "本期淨利（淨損）", "ifrs-full:ProfitLoss"),
        _statement_record(
            "3XXX",
            "權益總計",
            "ifrs-full:Equity",
            statement_type="balance_sheet",
        ),
    )

    result = map_statement_items_for_factors(source_rows)

    assert result.diagnostics == ()
    assert [record.item_code for record in result.records] == [
        "Equity",
        "EPS",
        "GrossProfit",
        "IncomeBeforeIncomeTax",
        "NetIncome",
        "OperatingIncome",
        "Revenue",
    ]
    assert all(record.value_unit == "TWD" for record in result.records)
    assert all(record.value_scale == 100 for record in result.records)
    assert [record.raw_item_code for record in result.records] == [
        "3XXX",
        "9750",
        "5950",
        "7900",
        "8200",
        "6900",
        "4000",
    ]


def test_r024_statement_mapping_diagnostic_order_is_stable() -> None:
    result = map_statement_items_for_factors(
        (
            _statement_record("4000", "營業收入合計", "wrong:first"),
            _statement_record("5950", "營業毛利（毛損）淨額", "wrong:second"),
            _statement_record("4000", "營業收入合計", "ifrs-full:Revenue", value="1000"),
            _statement_record("4000", "營業收入合計", "ifrs-full:Revenue", value="1001"),
        )
    )

    assert [item.code for item in result.diagnostics] == [
        "fundamental_statement.semantic_mapping_unproven",
        "fundamental_statement.semantic_mapping_unproven",
        "fundamental_statement.revision_ambiguous",
    ]
    assert result.diagnostics[0].message.endswith("source_version=" + _SOURCE_VERSION)
    assert result.diagnostics[1].message.endswith("source_version=" + _SOURCE_VERSION)


def test_r024_valuation_percentile_rank_and_singleton_behavior_are_stable() -> None:
    result = calculate_industry_percentiles_bp(
        [
            {"stock_code": "B", "industry": "semiconductor", "metric_value": Decimal("10")},
            {"stock_code": "A", "industry": "semiconductor", "metric_value": Decimal("10")},
            {"stock_code": "C", "industry": "semiconductor", "metric_value": Decimal("20")},
            {"stock_code": "ONE", "industry": "single", "metric_value": Decimal("3")},
        ]
    )

    assert result == {
        ("A", "semiconductor"): 3333,
        ("B", "semiconductor"): 6667,
        ("C", "semiconductor"): 10000,
        ("ONE", "single"): None,
    }


def test_r024_valuation_band_thresholds_and_missing_policy_are_stable() -> None:
    def classify(percentile: int | None) -> tuple[ValuationBand, tuple[str, ...]]:
        result = classify_relative_valuation(
            ValuationObservation(
                stock_code="2330",
                metric_name="pe",
                metric_value=Decimal("18.5"),
                as_of_date=date(2026, 6, 15),
                available_date=date(2026, 6, 16),
                industry_percentile_bp=percentile,
                quality=FactorQuality.OBSERVED,
                source="daily_prices.pe",
                source_version="daily-price-pe-2026-06-16",
            )
        )
        return result.band, tuple(item.code for item in result.diagnostics)

    assert classify(0) == (ValuationBand.LOW_RELATIVE, ())
    assert classify(2000) == (ValuationBand.LOW_RELATIVE, ())
    assert classify(2001) == (ValuationBand.MID_RELATIVE, ())
    assert classify(8000) == (ValuationBand.MID_RELATIVE, ())
    assert classify(8001) == (ValuationBand.HIGH_RELATIVE, ())
    assert classify(10000) == (ValuationBand.HIGH_RELATIVE, ())
    assert classify(None) == (
        ValuationBand.UNAVAILABLE,
        ("valuation.missing_industry_percentile",),
    )
    assert classify(-1) == (
        ValuationBand.UNAVAILABLE,
        ("valuation.invalid_industry_percentile",),
    )
    assert classify(10001) == (
        ValuationBand.UNAVAILABLE,
        ("valuation.invalid_industry_percentile",),
    )
