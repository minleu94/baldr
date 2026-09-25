"""基本面資料的 Factor adapter 前置契約。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from data_module.contracts.fundamental import (
    SourceDiagnostic,
    SourceDiagnosticKind,
)
from data_module.contracts.market import AvailabilityStatus
from data_module.fundamental_availability import FundamentalAvailabilityResolution
from data_module.fundamental_data import MonthlyRevenueRecord
from decision_module.factors.factor_dtos import (
    FactorDiagnostic,
    FactorQuality,
    FactorRecord,
    MissingPolicy,
)


@dataclass(frozen=True)
class FundamentalObservation:
    stock_code: str
    period: str
    as_of_date: date
    announced_date: date | None
    available_date: date | None
    value: Decimal | int | str | None
    source: str
    source_version: str
    quality: FactorQuality


@dataclass(frozen=True)
class FundamentalFactorBuildResult:
    records: tuple[FactorRecord, ...] = ()
    diagnostics: tuple[FactorDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


def availability_resolution_to_factor_quality(
    resolution: FundamentalAvailabilityResolution,
) -> FactorQuality:
    """唯一將基本面 availability facts 轉為 factor quality 的映射。"""

    if resolution.availability.status is not AvailabilityStatus.KNOWN:
        return FactorQuality.MISSING
    if resolution.announced_date is None:
        return FactorQuality.DEGRADED
    return FactorQuality.OBSERVED


def source_diagnostics_to_factor_diagnostics(
    diagnostics: Iterable[SourceDiagnostic],
) -> tuple[FactorDiagnostic, ...]:
    """將來源診斷投影為 domain 因子診斷，不改 code/message 順序。"""

    result: list[FactorDiagnostic] = []
    for diagnostic in diagnostics:
        kind = diagnostic.kind or SourceDiagnosticKind.AVAILABILITY
        if kind is SourceDiagnosticKind.AVAILABILITY:
            factor_name = "fundamental.availability"
        elif kind is SourceDiagnosticKind.AVAILABILITY_HISTORY:
            factor_name = "fundamental.availability"
            if diagnostic.market:
                factor_name = f"{factor_name}.{diagnostic.market}"
        elif kind is SourceDiagnosticKind.MONTHLY_REVENUE:
            factor_name = "fundamental.revenue"
        elif kind is SourceDiagnosticKind.STATEMENT:
            factor_name = "fundamental.statement"
            if diagnostic.statement_type:
                factor_name = f"{factor_name}.{diagnostic.statement_type}"
        elif kind is SourceDiagnosticKind.STATEMENT_AVAILABILITY:
            factor_name = "fundamental.statement_availability"
        elif kind is SourceDiagnosticKind.VALUATION:
            factor_name = (
                f"valuation.{diagnostic.metric_name}"
                if diagnostic.metric_name
                else "valuation.pe"
            )
        else:
            factor_name = "fundamental.monthly_revenue_snapshot"
            if diagnostic.market:
                factor_name = f"{factor_name}.{diagnostic.market}"
        result.append(
            FactorDiagnostic(
                code=diagnostic.code,
                factor_name=factor_name,
                stock_code=diagnostic.stock_code,
                message=diagnostic.message,
            )
        )
    return tuple(result)


def build_revenue_yoy_factor(
    observation: FundamentalObservation,
) -> FundamentalFactorBuildResult:
    factor_name = "fundamental.revenue_yoy"
    if observation.available_date is None:
        return FundamentalFactorBuildResult(
            diagnostics=(
                FactorDiagnostic(
                    code="fundamental.missing_available_date",
                    factor_name=factor_name,
                    stock_code=observation.stock_code,
                    message="fundamental observation missing available_date; no factor record emitted",
                ),
            )
        )

    return FundamentalFactorBuildResult(
        records=(
            FactorRecord(
                factor_name=factor_name,
                stock_code=observation.stock_code,
                as_of_date=observation.as_of_date,
                available_date=observation.available_date,
                value=observation.value,
                score_bp=None,
                quality=observation.quality,
                missing_policy=MissingPolicy.SKIP,
                source_version=observation.source_version,
                metadata={
                    "period": observation.period,
                    "announced_date": observation.announced_date,
                    "source": observation.source,
                },
            ),
        )
    )


def build_revenue_factor_pack(
    records: tuple[MonthlyRevenueRecord, ...],
    *,
    stock_code: str,
    decision_period: str,
) -> FundamentalFactorBuildResult:
    ordered = tuple(
        sorted(
            (record for record in records if record.stock_code == stock_code),
            key=lambda item: item.period,
        )
    )
    current = next((record for record in ordered if record.period == decision_period), None)
    if current is None:
        return FundamentalFactorBuildResult(
            diagnostics=(
                FactorDiagnostic(
                    code="fundamental_revenue.current_period_missing",
                    factor_name="fundamental.revenue",
                    stock_code=stock_code,
                    message=f"current revenue period missing; period={decision_period}",
                ),
            )
        )

    records_out: list[FactorRecord] = []
    diagnostics: list[FactorDiagnostic] = []
    _append_ratio_factor(
        records_out,
        diagnostics,
        current,
        _same_month_previous_year(ordered, current),
        "fundamental.revenue_yoy",
    )
    _append_ratio_factor(
        records_out,
        diagnostics,
        current,
        _previous_month(ordered, current),
        "fundamental.revenue_mom",
    )
    records_out.append(_string_factor(current, "fundamental.revenue_3m_trend", _three_month_trend(ordered, current)))
    records_out.append(_integer_factor(current, "fundamental.revenue_new_high", _new_high_flag(ordered, current)))
    return FundamentalFactorBuildResult(records=tuple(records_out), diagnostics=tuple(diagnostics))


def _append_ratio_factor(
    records_out: list[FactorRecord],
    diagnostics: list[FactorDiagnostic],
    current: MonthlyRevenueRecord,
    baseline: MonthlyRevenueRecord | None,
    factor_name: str,
) -> None:
    if baseline is None:
        diagnostics.append(
            FactorDiagnostic(
                code="fundamental_revenue.baseline_missing",
                factor_name=factor_name,
                stock_code=current.stock_code,
                message=f"revenue baseline missing; period={current.period}",
            )
        )
        return
    if baseline.revenue == Decimal("0"):
        diagnostics.append(
            FactorDiagnostic(
                code="fundamental_revenue.baseline_zero",
                factor_name=factor_name,
                stock_code=current.stock_code,
                message=f"revenue baseline is zero; period={baseline.period}",
            )
        )
        return

    records_out.append(_base_record(current, factor_name, (current.revenue - baseline.revenue) / baseline.revenue))


def _same_month_previous_year(
    records: tuple[MonthlyRevenueRecord, ...],
    current: MonthlyRevenueRecord,
) -> MonthlyRevenueRecord | None:
    year, month = _period_parts(current.period)
    target = f"{year - 1:04d}-{month:02d}"
    return next((record for record in records if record.period == target), None)


def _previous_month(
    records: tuple[MonthlyRevenueRecord, ...],
    current: MonthlyRevenueRecord,
) -> MonthlyRevenueRecord | None:
    year, month = _period_parts(current.period)
    if month == 1:
        year -= 1
        month = 12
    else:
        month -= 1
    target = f"{year:04d}-{month:02d}"
    return next((record for record in records if record.period == target), None)


def _three_month_trend(
    records: tuple[MonthlyRevenueRecord, ...],
    current: MonthlyRevenueRecord,
) -> str:
    current_index = next(index for index, record in enumerate(records) if record is current)
    window = records[max(0, current_index - 2) : current_index + 1]
    if len(window) < 3:
        return "insufficient"
    revenues = tuple(record.revenue for record in window)
    if revenues[0] < revenues[1] < revenues[2]:
        return "up"
    if revenues[0] > revenues[1] > revenues[2]:
        return "down"
    return "mixed"


def _new_high_flag(
    records: tuple[MonthlyRevenueRecord, ...],
    current: MonthlyRevenueRecord,
) -> int:
    prior_revenues = tuple(record.revenue for record in records if record.period < current.period)
    if not prior_revenues:
        return 1
    return 1 if current.revenue > max(prior_revenues) else 0


def _string_factor(record: MonthlyRevenueRecord, factor_name: str, value: str) -> FactorRecord:
    return _base_record(record, factor_name, value)


def _integer_factor(record: MonthlyRevenueRecord, factor_name: str, value: int) -> FactorRecord:
    return _base_record(record, factor_name, value)


def _factor_metadata(record: MonthlyRevenueRecord) -> dict[str, object]:
    return {
        "period": record.period,
        "announced_date": record.announced_date,
        "source": record.source,
    }


def _base_record(record: MonthlyRevenueRecord, factor_name: str, value: Decimal | int | str) -> FactorRecord:
    return FactorRecord(
        factor_name=factor_name,
        stock_code=record.stock_code,
        as_of_date=record.as_of_date,
        available_date=record.available_date,
        value=value,
        score_bp=None,
        quality=_monthly_revenue_factor_quality(record),
        missing_policy=MissingPolicy.SKIP,
        source_version=record.source_version,
        metadata=_factor_metadata(record),
    )


def _monthly_revenue_factor_quality(record: MonthlyRevenueRecord) -> FactorQuality:
    if record.legacy_quality_wire_value is not None:
        return FactorQuality(record.legacy_quality_wire_value)
    if record.announced_date is None:
        return FactorQuality.DEGRADED
    return FactorQuality.OBSERVED


def _period_parts(period: str) -> tuple[int, int]:
    year, month = period.split("-")
    return int(year), int(month)
