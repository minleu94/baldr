"""Governed valuation observations for presentation-only valuation factors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping

from data_module.contracts.fundamental import (
    SourceDiagnostic,
    SourceDiagnosticKind,
    parse_legacy_quality_wire_value,
)
from data_module.contracts.valuation import ValuationMetricRecord


@dataclass(frozen=True)
class ValuationObservationBuildResult:
    records: tuple[ValuationMetricRecord, ...] = ()
    diagnostics: tuple[SourceDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


def build_valuation_observations(
    rows: list[Mapping[str, str]],
) -> ValuationObservationBuildResult:
    """Parse persisted valuation rows into source facts without quality interpretation."""

    records: list[ValuationMetricRecord] = []
    diagnostics: list[SourceDiagnostic] = []
    for row in rows:
        stock_code = row.get("stock_code", "").strip()
        metric_name = row.get("metric_name", "").strip()
        try:
            metric_value = Decimal(row.get("metric_value", "").strip())
            as_of_date = _parse_date(row.get("as_of_date", ""))
            available_date = _parse_date(row.get("available_date", ""))
            percentile_value = row.get("industry_percentile_bp", "")
            percentile_raw = str(percentile_value).strip()
            percentile = int(percentile_raw) if percentile_raw else None
            quality_wire_value = parse_legacy_quality_wire_value(
                row.get("quality", "").strip()
            )
        except (InvalidOperation, ValueError):
            diagnostics.append(
                SourceDiagnostic(
                    code="valuation_data.invalid_row",
                    stock_code=stock_code,
                    message="valuation row has invalid metric, date, percentile, or quality",
                    kind=SourceDiagnosticKind.VALUATION,
                    metric_name=metric_name or "unknown",
                )
            )
            continue
        records.append(
            ValuationMetricRecord(
                stock_code=stock_code,
                metric_name=metric_name,
                metric_value=metric_value,
                as_of_date=as_of_date,
                available_date=available_date,
                industry_percentile_bp=percentile,
                industry=row.get("industry", "").strip(),
                source=row.get("source", "").strip(),
                source_version=row.get("source_version", "").strip(),
                legacy_quality_wire_value=quality_wire_value,
            )
        )
    return ValuationObservationBuildResult(records=tuple(records), diagnostics=tuple(diagnostics))


def _parse_date(value: str):
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()
