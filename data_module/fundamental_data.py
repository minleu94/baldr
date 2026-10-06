"""基本面 raw CSV 的唯讀正規化契約。"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping

from data_module.contracts.fundamental import (
    AvailabilityProvenance,
    SourceDiagnostic,
    SourceDiagnosticKind,
)
from data_module.fundamental_availability import (
    FundamentalAvailabilityInput,
    resolve_fundamental_availability,
)
from data_module.fundamental_availability_sources import FundamentalAvailabilityOverride


AvailableDateKey = tuple[str, str]
AvailableDateValue = date | FundamentalAvailabilityOverride


@dataclass(frozen=True)
class MonthlyRevenueRecord:
    stock_code: str
    period: str
    as_of_date: date
    raw_date: date
    announced_date: date | None
    available_date: date
    revenue: Decimal
    source: str
    source_version: str
    availability_provenance: AvailabilityProvenance | None = None
    # 原 SQLite quality 欄的未解讀 wire literal；factor 語意只由 decision adapter 解讀。
    legacy_quality_wire_value: str | None = None


@dataclass(frozen=True)
class MonthlyRevenueParseResult:
    records: tuple[MonthlyRevenueRecord, ...] = ()
    diagnostics: tuple[SourceDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


def parse_monthly_revenue_rows(
    rows: Iterable[Mapping[str, str]],
    *,
    available_dates: Mapping[AvailableDateKey, AvailableDateValue],
    source_version: str,
) -> MonthlyRevenueParseResult:
    records: list[MonthlyRevenueRecord] = []
    diagnostics: list[SourceDiagnostic] = []

    for row in rows:
        stock_code = row.get("stock_id", "").strip()
        period = _period(row)
        try:
            revenue = Decimal(row.get("revenue", "").strip())
        except (InvalidOperation, AttributeError):
            diagnostics.append(
                SourceDiagnostic(
                    code="fundamental_revenue.invalid_revenue",
                    stock_code=stock_code,
                    message="monthly revenue value is not a valid Decimal",
                    kind=SourceDiagnosticKind.MONTHLY_REVENUE,
                    period=period,
                    source_id="financial_data.monthly_revenue_csv",
                    source_version=source_version,
                )
            )
            continue

        availability = _resolve_row_availability(
            stock_code=stock_code,
            period=period,
            as_of_date=_month_end(row),
            availability_value=available_dates.get((stock_code, period)),
        )
        diagnostics.extend(
            _revenue_diagnostic_with_source_context(
                diagnostic,
                source_version=source_version,
                availability_value=available_dates.get((stock_code, period)),
            )
            for diagnostic in availability.diagnostics
        )
        if availability.available_date is None:
            continue

        records.append(
            MonthlyRevenueRecord(
                stock_code=stock_code,
                period=period,
                as_of_date=_month_end(row),
                raw_date=_parse_iso_date(row["date"]),
                announced_date=availability.announced_date,
                available_date=availability.available_date,
                revenue=revenue,
                source="financial_data.monthly_revenue_csv",
                source_version=source_version,
                availability_provenance=_availability_provenance(
                    available_dates.get((stock_code, period))
                ),
            )
        )

    return MonthlyRevenueParseResult(records=tuple(records), diagnostics=tuple(diagnostics))


def _period(row: Mapping[str, str]) -> str:
    year = int(row["revenue_year"])
    month = int(row["revenue_month"])
    return f"{year:04d}-{month:02d}"


def _resolve_row_availability(
    *,
    stock_code: str,
    period: str,
    as_of_date: date,
    availability_value: AvailableDateValue | None,
):
    if isinstance(availability_value, FundamentalAvailabilityOverride):
        return resolve_fundamental_availability(
            FundamentalAvailabilityInput(
                stock_code=stock_code,
                period=period,
                as_of_date=as_of_date,
                announced_date=availability_value.announced_date,
                explicit_available_date=availability_value.available_date,
                source=availability_value.source,
            )
        )

    return resolve_fundamental_availability(
        FundamentalAvailabilityInput(
            stock_code=stock_code,
            period=period,
            as_of_date=as_of_date,
            announced_date=None,
            explicit_available_date=availability_value,
            source="financial_data.monthly_revenue_csv",
        )
    )


def _availability_provenance(
    availability_value: AvailableDateValue | None,
) -> AvailabilityProvenance | None:
    if not isinstance(availability_value, FundamentalAvailabilityOverride):
        return None
    return AvailabilityProvenance(
        source_id=availability_value.source,
        source_version=availability_value.source_version,
        evidence_class=availability_value.evidence_class,
        source_hash=availability_value.source_hash,
        revision=availability_value.revision,
        parent_revision=availability_value.parent_revision,
        provenance_mode=availability_value.provenance_mode,
    )


def _revenue_diagnostic_with_source_context(
    diagnostic: SourceDiagnostic,
    *,
    source_version: str,
    availability_value: AvailableDateValue | None,
) -> SourceDiagnostic:
    if not isinstance(availability_value, FundamentalAvailabilityOverride):
        return replace(
            diagnostic,
            source_version=diagnostic.source_version or source_version,
        )
    return replace(
        diagnostic,
        source_version=diagnostic.source_version or source_version,
        source_hash=availability_value.source_hash or None,
        evidence_class=availability_value.evidence_class or None,
        provenance_mode=availability_value.provenance_mode or None,
        revision=availability_value.revision or None,
        parent_revision=availability_value.parent_revision,
    )


def legacy_monthly_revenue_quality_value(record: MonthlyRevenueRecord) -> str:
    """序列化舊 SQLite quality wire 欄位，不建立 FactorQuality 物件。"""

    if record.legacy_quality_wire_value is not None:
        return record.legacy_quality_wire_value
    return "observed" if record.announced_date is not None else "degraded"


def _month_end(row: Mapping[str, str]) -> date:
    year = int(row["revenue_year"])
    month = int(row["revenue_month"])
    return date(year, month, monthrange(year, month)[1])


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()
