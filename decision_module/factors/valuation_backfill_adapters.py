"""Interpret source P/E rows into the existing valuation backfill policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Mapping

from data_module.contracts.valuation import ValuationMetricRecord
from data_module.valuation_metrics_backfill import ValuationMetricsBackfillSourcePlan
from decision_module.factors.factor_dtos import FactorDiagnostic
from decision_module.factors.fundamental_adapters import (
    source_diagnostics_to_factor_diagnostics,
)
from decision_module.factors.valuation_policy import calculate_industry_percentiles_bp


@dataclass(frozen=True)
class ValuationMetricsBackfillPlan:
    records: tuple[ValuationMetricRecord, ...]
    diagnostics: tuple[FactorDiagnostic, ...]
    source_row_count: int
    as_of_date: date | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @property
    def ready_for_apply(self) -> bool:
        return bool(self.records)

    def to_markdown(self) -> str:
        return "\n".join(
            [
                "# Valuation Metrics Backfill Plan",
                "",
                f"- ready_for_apply: {str(self.ready_for_apply).lower()}",
                f"- as_of_date: {self.as_of_date.isoformat() if self.as_of_date else 'none'}",
                f"- source_row_count: {self.source_row_count}",
                f"- normalized_record_count: {len(self.records)}",
                f"- diagnostics: {len(self.diagnostics)}",
            ]
        )


def plan_valuation_metrics_backfill(
    *,
    source_plan: ValuationMetricsBackfillSourcePlan,
    industry_by_stock: Mapping[str, str],
    source_version: str,
) -> ValuationMetricsBackfillPlan:
    diagnostics = list(
        source_diagnostics_to_factor_diagnostics(source_plan.diagnostics)
    )
    if source_plan.as_of_date is None:
        return ValuationMetricsBackfillPlan(
            records=(),
            diagnostics=tuple(diagnostics),
            source_row_count=source_plan.source_row_count,
            as_of_date=None,
        )
    if not source_plan.records:
        return ValuationMetricsBackfillPlan(
            records=(),
            diagnostics=tuple(diagnostics),
            source_row_count=source_plan.source_row_count,
            as_of_date=source_plan.as_of_date,
        )

    percentile_inputs: list[Mapping[str, object]] = []
    for row in source_plan.records:
        industry = str(industry_by_stock.get(row.stock_code, "")).strip()
        if not industry:
            diagnostics.append(
                FactorDiagnostic(
                    code="valuation_backfill.missing_industry",
                    factor_name="valuation.pe",
                    stock_code=row.stock_code,
                    message="stock has P/E source row but no companies.csv industry mapping",
                )
            )
            continue
        if row.diagnostic is not None:
            diagnostics.extend(
                source_diagnostics_to_factor_diagnostics((row.diagnostic,))
            )
            continue
        metric_value = row.metric_value
        if metric_value is None:
            diagnostics.append(
                FactorDiagnostic(
                    code="valuation_backfill.invalid_pe",
                    factor_name="valuation.pe",
                    stock_code=row.stock_code,
                    message="daily_prices P/E value is not numeric",
                )
            )
            continue
        if metric_value <= 0:
            diagnostics.append(
                FactorDiagnostic(
                    code="valuation_backfill.invalid_pe",
                    factor_name="valuation.pe",
                    stock_code=row.stock_code,
                    message="daily_prices P/E value must be positive",
                )
            )
            continue
        percentile_inputs.append(
            {
                "stock_code": row.stock_code,
                "industry": industry,
                "metric_value": metric_value,
            }
        )

    percentiles = calculate_industry_percentiles_bp(percentile_inputs)
    records = tuple(
        ValuationMetricRecord(
            stock_code=str(row["stock_code"]),
            as_of_date=source_plan.as_of_date,
            available_date=source_plan.as_of_date,
            metric_name="pe",
            metric_value=Decimal(str(row["metric_value"])),
            industry=str(row["industry"]),
            industry_percentile_bp=percentiles[
                (str(row["stock_code"]), str(row["industry"]))
            ],
            source="daily_prices.pe",
            source_version=source_version,
            legacy_quality_wire_value=(
                "observed"
                if percentiles[(str(row["stock_code"]), str(row["industry"]))]
                is not None
                else "degraded"
            ),
        )
        for row in percentile_inputs
    )
    return ValuationMetricsBackfillPlan(
        records=records,
        diagnostics=tuple(diagnostics),
        source_row_count=source_plan.source_row_count,
        as_of_date=source_plan.as_of_date,
    )
