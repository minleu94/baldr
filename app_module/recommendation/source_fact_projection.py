"""Map read-only recommendation source records to decision-owned fact values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import SupportsFloat, cast

from data_module.fundamental_data import MonthlyRevenueRecord
from data_module.recommendation_input_providers import ValuationPEObservation
from decision_module.recommendation.industry_reasons import IndustryPerformanceReason
from decision_module.recommendation.evaluate import (
    IndustryChangeSourceKind,
    IndustryContextFact,
    MonthlyRevenueFact,
    MonthlyRevenueFacts,
    PEFact,
    StrategyEvaluationError,
)
from decision_module.recommendation.finalization import LegacyDecimalConversionFact
from financial_module.units import to_decimal


def project_pe_observation(
    observation: ValuationPEObservation | None,
) -> PEFact:
    """Normalize PE source values while keeping their uninterpreted lineage."""

    if observation is None:
        return PEFact(value=None, available_date=None)
    return PEFact(
        value=_decimal_value(observation.value),
        available_date=_date_value(observation.available_date),
        as_of_date=_date_value(observation.as_of_date),
        source=_optional_literal(observation.source),
        source_version=_optional_literal(observation.source_version),
        quality_literal=_optional_literal(observation.quality),
    )


def project_monthly_revenue_records(
    records: Sequence[MonthlyRevenueRecord],
) -> MonthlyRevenueFacts:
    """Copy source values into immutable decision facts without applying gates."""

    projected = tuple(
        MonthlyRevenueFact(
            period=record.period,
            available_date=record.available_date,
            source_version=record.source_version,
            revenue=record.revenue,
            source=record.source,
            quality_literal=record.legacy_quality_wire_value,
        )
        for record in records
    )
    return MonthlyRevenueFacts(records=projected)


def project_industry_context_fact(
    industries: Sequence[str],
    performance: Mapping[str, object] | None = None,
) -> IndustryContextFact:
    """Normalize mapper output while retaining the legacy numeric source kind.

    String-to-float coercion is confined to this source boundary because the
    legacy mapper contract parsed percent strings with ``float``. Decision
    policy receives only Decimal values and the source-kind marker.
    """

    projected_industries = tuple(industries)
    if performance is None:
        return IndustryContextFact(industries=projected_industries)

    raw_change = performance.get("漲跌百分比", 0)
    if isinstance(raw_change, Decimal):
        return IndustryContextFact(
            industries=projected_industries,
            first_industry_change_percent=raw_change,
            first_industry_change_source_kind=IndustryChangeSourceKind.LEGACY_DECIMAL,
        )
    if isinstance(raw_change, str):
        try:
            parsed_change = float(raw_change.replace("%", ""))
        except Exception:
            return IndustryContextFact(
                industries=projected_industries,
                first_industry_change_percent=Decimal("0"),
                first_industry_change_source_kind=IndustryChangeSourceKind.FALLBACK_ZERO,
            )
        return IndustryContextFact(
            industries=projected_industries,
            first_industry_change_percent=Decimal.from_float(parsed_change),
            first_industry_change_source_kind=IndustryChangeSourceKind.LEGACY_FLOAT,
        )
    if isinstance(raw_change, bool):
        return IndustryContextFact(
            industries=projected_industries,
            first_industry_change_percent=Decimal(int(raw_change)),
            first_industry_change_source_kind=IndustryChangeSourceKind.INTEGER,
        )
    if isinstance(raw_change, int):
        source_kind = IndustryChangeSourceKind.INTEGER
        if raw_change > 0:
            try:
                # The legacy policy multiplied a positive native int by 0.5.
                # Python first converts that int to float; preserve its
                # OverflowError as typed source compatibility evidence without
                # moving float arithmetic into the decision layer.
                float(raw_change)
            except OverflowError:
                source_kind = IndustryChangeSourceKind.LEGACY_INTEGER_OVERFLOW
        return IndustryContextFact(
            industries=projected_industries,
            first_industry_change_percent=Decimal(raw_change),
            first_industry_change_source_kind=source_kind,
        )
    if isinstance(raw_change, float):
        return IndustryContextFact(
            industries=projected_industries,
            first_industry_change_percent=Decimal.from_float(raw_change),
            first_industry_change_source_kind=IndustryChangeSourceKind.LEGACY_FLOAT,
        )
    if raw_change is None:
        return IndustryContextFact(
            industries=projected_industries,
            first_industry_change_source_kind=IndustryChangeSourceKind.UNSUPPORTED,
        )
    try:
        parsed_change = float(cast(SupportsFloat, raw_change))
    except Exception:
        return IndustryContextFact(
            industries=projected_industries,
            first_industry_change_source_kind=IndustryChangeSourceKind.UNSUPPORTED,
        )
    return IndustryContextFact(
        industries=projected_industries,
        first_industry_change_percent=Decimal.from_float(parsed_change),
        first_industry_change_source_kind=IndustryChangeSourceKind.LEGACY_FLOAT,
    )


def project_legacy_industry_reason(
    reason: IndustryPerformanceReason,
) -> dict[str, object]:
    """Project decision reason facts to the existing ReasonEngine DTO shape."""

    return {
        "tag": reason.tag,
        "evidence": reason.evidence,
        "score_contrib": float(reason.score_contrib),
    }


def project_optional_final_score(value: object) -> LegacyDecimalConversionFact:
    """Project a possibly absent legacy score without interpreting its policy."""

    if value is None:
        return LegacyDecimalConversionFact()
    return project_required_legacy_decimal(value)


def project_required_legacy_decimal(value: object) -> LegacyDecimalConversionFact:
    """Capture the existing Decimal(str(value)) conversion at the app boundary."""

    try:
        return LegacyDecimalConversionFact(value=to_decimal(value))
    except Exception as exc:
        return LegacyDecimalConversionFact(
            error=StrategyEvaluationError(
                error_type=type(exc).__name__,
                message=str(exc),
            )
        )


def _decimal_value(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        decimal_value = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    # Preserve source NaN/Infinity for the evaluator to reproduce the old
    # comparison/error path; source parsing must not silently turn them missing.
    return decimal_value


def _date_value(value: object) -> date | None:
    if type(value) is date:
        return value
    if type(value) is datetime:
        return value.date()
    if type(value) is not str:
        return None
    text = value.strip()
    try:
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").date()
        return date.fromisoformat(text)
    except ValueError:
        return None


def _optional_literal(value: object) -> str | None:
    if value is None:
        return None
    return value if type(value) is str else str(value)


__all__ = (
    "project_optional_final_score",
    "project_required_legacy_decimal",
    "project_industry_context_fact",
    "project_legacy_industry_reason",
    "project_monthly_revenue_records",
    "project_pe_observation",
)
