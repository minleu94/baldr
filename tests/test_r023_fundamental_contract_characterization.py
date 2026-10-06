from datetime import date
from decimal import Decimal

from data_module.contracts.fundamental import SourceDiagnostic
from data_module.contracts.market import AvailabilityStatus
from data_module.fundamental_availability import (
    RETROACTIVE_BASELINE_SOURCE,
    FundamentalAvailabilityInput,
    resolve_fundamental_availability,
)
from data_module.fundamental_availability_sources import (
    load_monthly_revenue_availability_overrides,
)
from data_module.fundamental_data import parse_monthly_revenue_rows
from decision_module.factors.factor_dtos import FactorDiagnostic, FactorQuality
from decision_module.factors.fundamental_adapters import (
    availability_resolution_to_factor_quality,
    source_diagnostics_to_factor_diagnostics,
)


def test_fundamental_availability_facts_and_factor_quality_mapping_keep_legacy_parity():
    inputs = (
        FundamentalAvailabilityInput(
            "2330", "2026-05", date(2026, 5, 31), None, None, "source-a"
        ),
        FundamentalAvailabilityInput(
            "2330", "2026-05", date(2026, 5, 31), None, date(2026, 5, 30), "source-a"
        ),
        FundamentalAvailabilityInput(
            "2330",
            "2026-05",
            date(2026, 5, 31),
            date(2026, 6, 10),
            date(2026, 6, 9),
            "source-a",
        ),
        FundamentalAvailabilityInput(
            "2330", "2026-05", date(2026, 5, 31), None, date(2026, 6, 10), "source-a"
        ),
        FundamentalAvailabilityInput(
            "2330",
            "2026-05",
            date(2026, 5, 31),
            None,
            date(2026, 6, 17),
            RETROACTIVE_BASELINE_SOURCE,
        ),
        FundamentalAvailabilityInput(
            "2330",
            "2026-05",
            date(2026, 5, 31),
            date(2026, 6, 10),
            date(2026, 6, 11),
            "source-a",
        ),
    )

    results = tuple(resolve_fundamental_availability(item) for item in inputs)

    assert tuple(result.availability.status for result in results) == (
        AvailabilityStatus.UNKNOWN,
        AvailabilityStatus.UNKNOWN,
        AvailabilityStatus.UNKNOWN,
        AvailabilityStatus.KNOWN,
        AvailabilityStatus.KNOWN,
        AvailabilityStatus.KNOWN,
    )
    assert tuple(availability_resolution_to_factor_quality(result) for result in results) == (
        FactorQuality.MISSING,
        FactorQuality.MISSING,
        FactorQuality.MISSING,
        FactorQuality.DEGRADED,
        FactorQuality.DEGRADED,
        FactorQuality.OBSERVED,
    )
    assert tuple(
        tuple(diagnostic.code for diagnostic in result.diagnostics)
        for result in results
    ) == (
        ("fundamental_availability.missing_available_date",),
        ("fundamental_availability.available_before_period_end",),
        ("fundamental_availability.available_before_announcement",),
        ("fundamental_availability.missing_announced_date",),
        (),
        (),
    )
    assert tuple(result.available_date for result in results) == (
        None,
        None,
        None,
        date(2026, 6, 10),
        date(2026, 6, 17),
        date(2026, 6, 11),
    )

    source_diagnostics = tuple(
        item for result in results for item in result.diagnostics
    )
    assert all(isinstance(item, SourceDiagnostic) for item in source_diagnostics)
    mapped = source_diagnostics_to_factor_diagnostics(source_diagnostics)
    assert tuple(
        (item.code, item.factor_name) for item in mapped
    ) == (
        ("fundamental_availability.missing_available_date", "fundamental.availability"),
        ("fundamental_availability.available_before_period_end", "fundamental.availability"),
        (
            "fundamental_availability.available_before_announcement",
            "fundamental.availability",
        ),
        ("fundamental_availability.missing_announced_date", "fundamental.availability"),
    )


def test_monthly_revenue_parser_preserves_decimal_units_availability_and_diagnostic_order():
    rows = (
        {
            "date": "2026-06-10",
            "stock_id": "2330",
            "revenue": "not-a-number",
            "revenue_month": "5",
            "revenue_year": "2026",
        },
        {
            "date": "2026-06-10",
            "stock_id": "2330",
            "revenue": "1000000000.00",
            "revenue_month": "5",
            "revenue_year": "2026",
        },
        {
            "date": "2026-07-10",
            "stock_id": "2330",
            "revenue": "1100000000.25",
            "revenue_month": "6",
            "revenue_year": "2026",
        },
    )

    result = parse_monthly_revenue_rows(
        rows,
        available_dates={
            ("2330", "2026-05"): date(2026, 6, 10),
            ("2330", "2026-06"): date(2026, 7, 10),
        },
        source_version="monthly-revenue-fixture-v1",
    )

    assert tuple(record.revenue for record in result.records) == (
        Decimal("1000000000.00"),
        Decimal("1100000000.25"),
    )
    assert tuple(record.available_date for record in result.records) == (
        date(2026, 6, 10),
        date(2026, 7, 10),
    )
    assert tuple(record.source_version for record in result.records) == (
        "monthly-revenue-fixture-v1",
        "monthly-revenue-fixture-v1",
    )
    assert all(record.legacy_quality_wire_value is None for record in result.records)
    assert tuple(diagnostic.code for diagnostic in result.diagnostics) == (
        "fundamental_revenue.invalid_revenue",
        "fundamental_availability.missing_announced_date",
        "fundamental_availability.missing_announced_date",
    )
    assert tuple(
        (diagnostic.source_id, diagnostic.source_version)
        for diagnostic in result.diagnostics
    ) == (
        ("financial_data.monthly_revenue_csv", "monthly-revenue-fixture-v1"),
        ("financial_data.monthly_revenue_csv", "monthly-revenue-fixture-v1"),
        ("financial_data.monthly_revenue_csv", "monthly-revenue-fixture-v1"),
    )
    mapped = source_diagnostics_to_factor_diagnostics(result.diagnostics)
    assert all(isinstance(item, FactorDiagnostic) for item in mapped)
    assert tuple(
        (item.code, item.factor_name, item.message) for item in mapped
    ) == (
        (
            "fundamental_revenue.invalid_revenue",
            "fundamental.revenue",
            "monthly revenue value is not a valid Decimal",
        ),
        (
            "fundamental_availability.missing_announced_date",
            "fundamental.availability",
            "announced_date missing; available_date is explicit but quality is degraded; "
            "period=2026-05; source=financial_data.monthly_revenue_csv",
        ),
        (
            "fundamental_availability.missing_announced_date",
            "fundamental.availability",
            "announced_date missing; available_date is explicit but quality is degraded; "
            "period=2026-06; source=financial_data.monthly_revenue_csv",
        ),
    )


def test_availability_revision_history_retains_same_date_lineage_without_row_revision():
    base = {
        "stock_code": "2330",
        "period": "2026-05",
        "as_of_date": "2026-05-31",
        "announced_date": "2026-06-10",
        "available_date": "2026-06-11",
        "source": "twse.monthly_revenue_announcement",
        "availability_contract_version": "formal-availability.v2",
        "evidence_class": "official_announcement",
    }
    first = {
        **base,
        "source_version": "announcement-v1",
        "source_hash": "a" * 64,
        "revision": "1",
        "parent_revision": "",
    }
    second = {
        **base,
        "source_version": "announcement-v2",
        "source_hash": "b" * 64,
        "revision": "2",
        "parent_revision": "1",
    }

    result = load_monthly_revenue_availability_overrides([first, second])
    key = ("2330", "2026-05")
    latest = result.overrides[key]
    history = result.revision_history[key]

    assert result.diagnostics == ()
    assert latest.available_date == date(2026, 6, 11)
    assert latest.source_version == "announcement-v2"
    assert latest.revision == 2
    assert latest.parent_revision == 1
    assert tuple(item.available_date for item in history) == (
        date(2026, 6, 11),
        date(2026, 6, 11),
    )
    assert tuple(item.source_version for item in history) == (
        "announcement-v1",
        "announcement-v2",
    )
    assert tuple(item.source_hash for item in history) == ("a" * 64, "b" * 64)
    assert tuple(item.revision for item in history) == (1, 2)
    assert not hasattr(latest, "quality")
