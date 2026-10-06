"""Pure valuation source records; presentation and quality interpretation live in decision."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from data_module.contracts.fundamental import SourceDiagnostic


@dataclass(frozen=True, slots=True)
class ValuationBackfillSourceRow:
    stock_code: str
    metric_value: Decimal | None
    diagnostic: SourceDiagnostic | None = None


@dataclass(frozen=True, slots=True)
class ValuationMetricRecord:
    stock_code: str
    metric_name: str
    metric_value: Decimal
    as_of_date: date
    available_date: date
    industry_percentile_bp: int | None
    industry: str
    source: str
    source_version: str
    legacy_quality_wire_value: str


__all__ = ("ValuationBackfillSourceRow", "ValuationMetricRecord")
