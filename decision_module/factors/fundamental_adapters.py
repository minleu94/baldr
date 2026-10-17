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

REVENUE_PACK_METHOD_VERSION = "fundamental-revenue-pack.v2"


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
    selected = tuple(record for record in records if record.stock_code == stock_code)
    if not _canonical_month(decision_period) or any(not _canonical_month(record.period) for record in selected):
        return FundamentalFactorBuildResult(diagnostics=(FactorDiagnostic(
            code="fundamental_revenue.invalid_period", factor_name="fundamental.revenue", stock_code=stock_code,
            message="需要可核對的YYYY-MM曆月，不能猜測缺少的期別。",
        ),))
    ordered = tuple(
        sorted(
            (record for record in selected if record.period <= decision_period),
            key=lambda item: item.period,
        )
    )
    current_rows = tuple(record for record in ordered if record.period == decision_period)
    if len(current_rows) > 1:
        return FundamentalFactorBuildResult(diagnostics=(FactorDiagnostic(
            code="fundamental_revenue.current_period_conflict", factor_name="fundamental.revenue",
            stock_code=stock_code, message=f"當期有多筆版本，不能任選；period={decision_period}",
        ),))
    current = current_rows[0] if current_rows else None
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

    if len({record.period for record in ordered}) != len(ordered):
        return FundamentalFactorBuildResult(diagnostics=(FactorDiagnostic(
            code="fundamental_revenue.comparison_period_conflict", factor_name="fundamental.revenue", stock_code=stock_code,
            message="前期有多筆版本，不能任選比較輸入。",
        ),))
    if any(type(record.available_date) is not date for record in ordered):
        return FundamentalFactorBuildResult(diagnostics=(FactorDiagnostic(
            code="fundamental_revenue.comparison_available_date_missing", factor_name="fundamental.revenue", stock_code=stock_code,
            message="比較輸入缺可核對的可得日，不產生衍生因子。",
        ),))
    if not isinstance(current.revenue, Decimal) or not current.revenue.is_finite():
        return FundamentalFactorBuildResult(diagnostics=(FactorDiagnostic(
            code="fundamental_revenue.current_value_invalid", factor_name="fundamental.revenue", stock_code=stock_code,
            message="當期營收不是有限Decimal，不能產生比較。",
        ),))

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
    window = _calendar_month_window(ordered, current)
    trend = _three_month_trend(window, current)
    records_out.append(_base_record(current, "fundamental.revenue_3m_trend", trend,
        inputs=window or (current,), unavailable=trend == "insufficient", comparison_scope="three_calendar_months"))
    if trend == "insufficient":
        diagnostics.append(FactorDiagnostic(code="fundamental_revenue.calendar_months_missing",
            factor_name="fundamental.revenue_3m_trend", stock_code=stock_code,
            message=f"需要當期及前兩個曆月的唯一合格輸入；period={current.period}"))
    prior = tuple(record for record in ordered if record.period < current.period)
    high = _new_high_flag(prior, current)
    records_out.append(_base_record(current, "fundamental.revenue_new_high", high,
        inputs=prior + (current,), unavailable=high is None, comparison_scope="provided_prior_months"))
    if high is None:
        diagnostics.append(FactorDiagnostic(
            code="fundamental_revenue.prior_history_missing" if not prior else "fundamental_revenue.prior_history_unusable",
            factor_name="fundamental.revenue_new_high", stock_code=stock_code,
            message=f"沒有唯一且合格的前期樣本，不能判新高；period={current.period}"))
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
    if not _usable_revenue_inputs((baseline, current)):
        diagnostics.append(FactorDiagnostic(code="fundamental_revenue.comparison_input_unusable",
            factor_name=factor_name, stock_code=current.stock_code, message="比較值或來源品質不可用，不產生比率。"))
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

    records_out.append(_base_record(current, factor_name, (current.revenue - baseline.revenue) / baseline.revenue,
        inputs=(baseline, current), comparison_scope="exact_comparison_period"))


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
    window = _calendar_month_window(records, current)
    if len(window) != 3 or not _usable_revenue_inputs(window):
        return "insufficient"
    revenues = tuple(record.revenue for record in window)
    if revenues[0] < revenues[1] < revenues[2]:
        return "up"
    if revenues[0] > revenues[1] > revenues[2]:
        return "down"
    return "mixed"


def _calendar_month_window(
    records: tuple[MonthlyRevenueRecord, ...], current: MonthlyRevenueRecord,
) -> tuple[MonthlyRevenueRecord, ...]:
    year, month = _period_parts(current.period)
    window: list[MonthlyRevenueRecord] = []
    for offset in (2, 1, 0):
        target_year, target_month = divmod(year * 12 + month - 1 - offset, 12)
        target = f"{target_year:04d}-{target_month + 1:02d}"
        matches = tuple(record for record in records if record.period == target)
        if len(matches) != 1:
            return ()
        window.append(matches[0])
    return tuple(window)


def _usable_revenue_inputs(records: tuple[MonthlyRevenueRecord, ...]) -> bool:
    return all(isinstance(record.revenue, Decimal) and record.revenue.is_finite()
        and _monthly_revenue_factor_quality(record) not in {FactorQuality.MISSING, FactorQuality.NEUTRAL} for record in records)


def _new_high_flag(
    records: tuple[MonthlyRevenueRecord, ...],
    current: MonthlyRevenueRecord,
) -> int | None:
    prior = tuple(record for record in records if record.period < current.period)
    if not prior or len({record.period for record in prior}) != len(prior) or not _usable_revenue_inputs(prior + (current,)):
        return None
    prior_revenues = tuple(record.revenue for record in prior)
    return 1 if current.revenue > max(prior_revenues) else 0


def _factor_metadata(record: MonthlyRevenueRecord) -> dict[str, object]:
    return {
        "period": record.period,
        "announced_date": record.announced_date,
        "source": record.source,
    }


def _base_record(record: MonthlyRevenueRecord, factor_name: str, value: Decimal | int | str | None,
                 *, inputs: tuple[MonthlyRevenueRecord, ...], unavailable: bool = False,
                 comparison_scope: str) -> FactorRecord:
    # 最晚消耗可得日與最弱來源品質必須同行，不能只沿當期較早的時鐘。
    quality_order = (FactorQuality.OBSERVED, FactorQuality.ESTIMATED, FactorQuality.DEGRADED,
                     FactorQuality.STALE, FactorQuality.NEUTRAL, FactorQuality.MISSING)
    quality = max((_monthly_revenue_factor_quality(item) for item in inputs), key=quality_order.index)
    metadata = dict(_factor_metadata(record), method_version=REVENUE_PACK_METHOD_VERSION,
        comparison_scope=comparison_scope, inputs=tuple({"period": item.period,
            "available_date": item.available_date, "source": item.source, "source_version": item.source_version,
            "revenue": item.revenue, "quality": _monthly_revenue_factor_quality(item).value,
            "as_of_date": item.as_of_date, "announced_date": item.announced_date,
            "source_hash": getattr(item.availability_provenance, "source_hash", None)} for item in inputs))
    return FactorRecord(
        factor_name=factor_name,
        stock_code=record.stock_code,
        as_of_date=record.as_of_date,
        available_date=max(item.available_date for item in inputs),
        value=value,
        score_bp=None,
        quality=FactorQuality.MISSING if unavailable else quality,
        missing_policy=MissingPolicy.SKIP,
        source_version=record.source_version,
        metadata=metadata,
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


def _canonical_month(period: str) -> bool:
    try:
        year, month = _period_parts(period)
        date(year, month, 1)
    except (ValueError, TypeError, AttributeError):
        return False
    return period == f"{year:04d}-{month:02d}"
