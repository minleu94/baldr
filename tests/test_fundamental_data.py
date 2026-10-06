from datetime import date
from decimal import Decimal

from data_module.fundamental_availability_sources import FundamentalAvailabilityOverride
from data_module.fundamental_data import (
    legacy_monthly_revenue_quality_value,
    parse_monthly_revenue_rows,
)


def test_parse_monthly_revenue_rows_requires_explicit_available_date():
    rows = [
        {
            "date": "2026-06-10",
            "stock_id": "2330",
            "country": "Taiwan",
            "revenue": "1000000000",
            "revenue_month": "5",
            "revenue_year": "2026",
        }
    ]

    result = parse_monthly_revenue_rows(
        rows,
        available_dates={},
        source_version="financial-data-csv-preflight-v1",
    )

    assert result.records == ()
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "fundamental_availability.missing_available_date"
    assert result.diagnostics[0].stock_code == "2330"


def test_parse_monthly_revenue_rows_builds_normalized_record_with_available_date():
    rows = [
        {
            "date": "2026-06-10",
            "stock_id": "2330",
            "country": "Taiwan",
            "revenue": "1000000000",
            "revenue_month": "5",
            "revenue_year": "2026",
        }
    ]

    result = parse_monthly_revenue_rows(
        rows,
        available_dates={("2330", "2026-05"): date(2026, 6, 10)},
        source_version="financial-data-csv-preflight-v1",
    )

    assert len(result.records) == 1
    record = result.records[0]
    assert record.stock_code == "2330"
    assert record.period == "2026-05"
    assert record.as_of_date == date(2026, 5, 31)
    assert record.raw_date == date(2026, 6, 10)
    assert record.announced_date is None
    assert record.available_date == date(2026, 6, 10)
    assert record.revenue == Decimal("1000000000")
    assert record.source == "financial_data.monthly_revenue_csv"
    assert record.source_version == "financial-data-csv-preflight-v1"
    assert record.availability_provenance is None
    assert record.legacy_quality_wire_value is None
    assert legacy_monthly_revenue_quality_value(record) == "degraded"
    assert result.diagnostics[0].code == "fundamental_availability.missing_announced_date"


def test_parse_monthly_revenue_rows_uses_governed_availability_override():
    rows = [
        {
            "date": "2026-06-10",
            "stock_id": "2330",
            "country": "Taiwan",
            "revenue": "1000000000",
            "revenue_month": "5",
            "revenue_year": "2026",
        }
    ]

    result = parse_monthly_revenue_rows(
        rows,
        available_dates={
            ("2330", "2026-05"): FundamentalAvailabilityOverride(
                stock_code="2330",
                period="2026-05",
                as_of_date=date(2026, 5, 31),
                announced_date=date(2026, 6, 10),
                available_date=date(2026, 6, 11),
                source="manual.twse_monthly_revenue_announcement_log",
                source_version="announcement-log-2026-06-16",
                evidence_class="official_announcement",
                source_hash=f"sha256:{'a' * 64}",
                revision=2,
                parent_revision=1,
                provenance_mode="formal_v2",
            )
        },
        source_version="financial-data-csv-preflight-v1",
    )

    assert result.diagnostics == ()
    assert len(result.records) == 1
    record = result.records[0]
    assert record.announced_date == date(2026, 6, 10)
    assert record.available_date == date(2026, 6, 11)
    assert record.availability_provenance is not None
    assert record.availability_provenance.source_id == (
        "manual.twse_monthly_revenue_announcement_log"
    )
    assert record.availability_provenance.source_version == "announcement-log-2026-06-16"
    assert record.availability_provenance.source_hash == f"sha256:{'a' * 64}"
    assert record.availability_provenance.revision == 2
    assert record.availability_provenance.parent_revision == 1
    assert legacy_monthly_revenue_quality_value(record) == "observed"
    assert result.diagnostics == ()


def test_parse_monthly_revenue_rows_reports_invalid_decimal_without_record():
    rows = [
        {
            "date": "2026-06-10",
            "stock_id": "2330",
            "country": "Taiwan",
            "revenue": "not-a-number",
            "revenue_month": "5",
            "revenue_year": "2026",
        }
    ]

    result = parse_monthly_revenue_rows(
        rows,
        available_dates={("2330", "2026-05"): date(2026, 6, 10)},
        source_version="financial-data-csv-preflight-v1",
    )

    assert result.records == ()
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "fundamental_revenue.invalid_revenue"
