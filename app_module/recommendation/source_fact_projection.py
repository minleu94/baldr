"""Map read-only recommendation source records to decision-owned fact values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Literal, SupportsFloat, cast
from zoneinfo import ZoneInfo

from data_module.fundamental_data import MonthlyRevenueRecord
from data_module.recommendation_current_fundamental_provider import (
    CurrentObservedMonthlyRevenueInput,
    CurrentObservedPEInput,
)
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
from utils.monthly_revenue_identity import (
    MONTHLY_NORMALIZER_VERSION,
    MONTHLY_SNAPSHOT_SOURCE,
    OPENAPI_MONTHLY_NORMALIZER_VERSION,
    OPENAPI_MONTHLY_SOURCE_IDS,
    is_monthly_derived_source_version,
    is_monthly_yoy_comparator_source_version,
    monthly_derived_source_version_parts,
    monthly_source_version_identity,
    monthly_yoy_comparator_source_version_parts,
)


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


def project_current_pe_observation(
    observation: CurrentObservedPEInput | None,
) -> PEFact:
    """Project one current-only PE capture without granting formal PIT use."""

    if observation is None:
        return PEFact(value=None, available_date=None)
    return PEFact(
        value=_decimal_value(observation.value),
        available_date=observation.available_at.astimezone(
            ZoneInfo("Asia/Taipei")
        ).date(),
        as_of_date=observation.as_of_date,
        source=observation.source,
        source_version=observation.source_version,
        stock_code=observation.stock_code,
        available_at=observation.available_at,
        availability_basis=observation.availability_basis,
        raw_response_sha256=observation.raw_response_sha256,
        formal_pit_eligible=False,
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
            stock_code=record.stock_code,
            availability_basis="formal_pit_available_date",
            formal_pit_eligible=True,
        )
        for record in records
    )
    return MonthlyRevenueFacts(records=projected)


def project_current_monthly_revenue_records(
    current_records: Sequence[CurrentObservedMonthlyRevenueInput],
    formal_records: Sequence[MonthlyRevenueRecord],
    *,
    stock_code: str,
) -> MonthlyRevenueFacts:
    """Use current-observation values and their exact current-lane baseline.

    The current lane never borrows a formal PIT row: legacy monthly records
    carry no reliable unit, and the comparator must share the current report's
    unit, source identity, and availability clock.
    """

    current_for_stock = tuple(
        record
        for record in current_records
        if record.stock_code == stock_code
        and record.input_role == "reported_period_value"
        and _current_monthly_input_version_is_exact(
            record, role="reported_period_value"
        )
    )
    if not current_for_stock:
        return MonthlyRevenueFacts()
    latest_period = max(record.period for record in current_for_stock)
    current_period_rows = tuple(
        record for record in current_for_stock if record.period == latest_period
    )
    latest_clock = max(_current_monthly_revision_clock(record) for record in current_period_rows)
    latest_rows = tuple(
        record
        for record in current_period_rows
        if _current_monthly_revision_clock(record) == latest_clock
    )
    if len({record.revenue for record in latest_rows}) != 1:
        return MonthlyRevenueFacts()
    latest = min(latest_rows, key=lambda record: record.source_version)
    year_text, month_text = latest.period.split("-")
    prior_period = f"{int(year_text) - 1:04d}-{int(month_text):02d}"

    prior_current_rows = tuple(
        record
        for record in current_records
        if record.stock_code == stock_code
        and record.period == prior_period
        and record.input_role == "same_report_prior_year_comparison_baseline"
        and record.parent_report_period == latest.period
        and _current_monthly_input_version_is_exact(
            record, role="same_report_prior_year_comparison_baseline"
        )
        and record.source == latest.source
        and record.market == latest.market
        and record.raw_source_version == latest.raw_source_version
        and record.raw_source_sha256 == latest.raw_source_sha256
        and record.source_available_at == latest.source_available_at
        and record.unit == latest.unit
        and record.period_basis == latest.period_basis
        and record.basis_verified is True
        and record.aggregate_feature_eligible is False
        and record.formal_pit_eligible is False
    )
    if prior_current_rows:
        prior_clock = max(
            _current_monthly_revision_clock(record) for record in prior_current_rows
        )
        prior_current_rows = tuple(
            record
            for record in prior_current_rows
            if _current_monthly_revision_clock(record) == prior_clock
        )
        if len({record.revenue for record in prior_current_rows}) != 1:
            return MonthlyRevenueFacts()
        prior_current = min(
            prior_current_rows, key=lambda record: record.source_version
        )
        prior_fact = _current_monthly_fact(prior_current)
    else:
        # Keep the actual latest report value available for diagnostics and
        # lineage, but do not substitute an older period's observed row as a
        # same-report year-over-year comparator.
        return MonthlyRevenueFacts(records=(_current_monthly_fact(latest),))
    latest_fact = _current_monthly_fact(latest)
    return MonthlyRevenueFacts(records=(prior_fact, latest_fact))


def _current_monthly_input_version_is_exact(
    record: CurrentObservedMonthlyRevenueInput,
    *,
    role: str,
) -> bool:
    """只接受來源、自然鍵、原件雜湊、時鐘和逐列衍生摘要完全相符的輸入。"""

    market = record.market
    if market == "twse":
        market_key: Literal["twse", "tpex"] = "twse"
    elif market == "tpex":
        market_key = "tpex"
    else:
        return False
    expected_source = (
        MONTHLY_SNAPSHOT_SOURCE
        if record.source == MONTHLY_SNAPSHOT_SOURCE
        else OPENAPI_MONTHLY_SOURCE_IDS[market_key]
    )
    if record.source != expected_source:
        return False
    try:
        raw_identity = monthly_source_version_identity(record.raw_source_version)
    except ValueError:
        return False
    expected_period = (
        record.period
        if role == "reported_period_value"
        else record.parent_report_period
    )
    if expected_period is None or raw_identity != (
        expected_source,
        market,
        expected_period,
        record.raw_source_sha256,
    ):
        return False
    if record.source_available_at is None:
        source_available_at = ""
    elif (
        record.source_available_at.tzinfo is None
        or record.source_available_at.utcoffset() is None
    ):
        return False
    else:
        source_available_at = record.source_available_at.astimezone(
            timezone.utc
        ).isoformat()

    if role == "reported_period_value":
        parts = monthly_derived_source_version_parts(record.source_version)
        expected_normalizer = (
            OPENAPI_MONTHLY_NORMALIZER_VERSION
            if expected_source == OPENAPI_MONTHLY_SOURCE_IDS[market_key]
            else MONTHLY_NORMALIZER_VERSION
        )
        if (
            parts is None
            or parts[0] != expected_normalizer
            or parts[1] != market
            or parts[2] != record.period
            or parts[3] != record.raw_source_version
        ):
            return False
        try:
            return is_monthly_derived_source_version(
                record.source_version,
                market=market,
                period=record.period,
                stock_code=record.stock_code,
                value=str(record.revenue),
                unit=record.unit,
                source_available_at=source_available_at,
            )
        except ValueError:
            return False

    if role != "same_report_prior_year_comparison_baseline":
        return False
    version = record.source_version
    suffix_marker = ":verified-csv-sha256:"
    if suffix_marker in version:
        base_version, csv_digest = version.rsplit(suffix_marker, 1)
        if re.fullmatch(r"[0-9a-f]{64}", csv_digest) is None:
            return False
    else:
        base_version = version
    parts = monthly_yoy_comparator_source_version_parts(version)
    if (
        parts is None
        or parts[0] != market
        or parts[1] != record.period
        or parts[2] != expected_period
        or parts[3] != record.raw_source_version
    ):
        return False
    try:
        return is_monthly_yoy_comparator_source_version(
            base_version,
            market=market,
            comparator_period=record.period,
            stock_code=record.stock_code,
            value=str(record.revenue),
            unit=record.unit,
            source_available_at=source_available_at,
        )
    except ValueError:
        return False


def _current_monthly_revision_clock(
    record: CurrentObservedMonthlyRevenueInput,
) -> datetime:
    """Rank actual source revisions separately from local materialization."""

    return record.source_available_at or record.observed_at


def _current_monthly_fact(
    record: CurrentObservedMonthlyRevenueInput,
) -> MonthlyRevenueFact:
    return MonthlyRevenueFact(
        period=record.period,
        available_date=record.observed_at.astimezone(
            ZoneInfo("Asia/Taipei")
        ).date(),
        source_version=record.source_version,
        revenue=record.revenue,
        source=record.source,
        stock_code=record.stock_code,
        available_at=record.available_at,
        observed_at=record.observed_at,
        source_available_at=record.source_available_at,
        availability_basis=record.availability_basis,
        raw_source_sha256=record.raw_source_sha256,
        market=record.market,
        unit=record.unit,
        period_basis=record.period_basis,
        basis_verified=record.basis_verified,
        aggregate_feature_eligible=record.aggregate_feature_eligible,
        formal_pit_eligible=False,
        input_role=record.input_role,
        parent_report_period=record.parent_report_period,
    )


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
    "project_current_monthly_revenue_records",
    "project_current_pe_observation",
    "project_optional_final_score",
    "project_required_legacy_decimal",
    "project_industry_context_fact",
    "project_legacy_industry_reason",
    "project_monthly_revenue_records",
    "project_pe_observation",
)
