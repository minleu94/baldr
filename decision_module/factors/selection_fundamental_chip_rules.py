"""月營收 YoY 的 current-only 精確事實投影與條件排序。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
import json
import re
from typing import Literal, TypeAlias
from zoneinfo import ZoneInfo

from data_module.current_fundamental_snapshots import (
    MONTHLY_SNAPSHOT_SOURCE,
    _derived_monthly_yoy_comparator_version,
    _is_monthly_derived_source_version,
    _is_monthly_yoy_comparator_source_version,
    _monthly_source_version_parts,
)
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    CurrentObservedMonthlyRevenueInput,
)


SelectionRevenueYoYState: TypeAlias = Literal["observed", "unknown"]
SelectionRevenueYoYAvailability: TypeAlias = Literal[
    "verified", "unknown", "unavailable"
]
SelectionConditionState: TypeAlias = Literal["match", "no_match", "unknown"]

SELECTION_REVENUE_YOY_SCHEMA = "selection-monthly-revenue-yoy.v1"
SELECTION_REVENUE_YOY_METHOD_ID = "selection.monthly_revenue_yoy"
SELECTION_REVENUE_YOY_METHOD_VERSION = "current-observed-decimal.v1"
SELECTION_REVENUE_YOY_SOURCE_SCOPE = "current_observed_only"
SELECTION_REVENUE_YOY_FORMULA = "(current_twd - comparator_twd) / comparator_twd"
SELECTION_REVENUE_RATIO_UNIT = "ratio"
SELECTION_REVENUE_PERCENT_UNIT = "percent"
SELECTION_REVENUE_UNIT = "TWD"
SELECTION_REVENUE_PERIOD_BASIS = "monthly_flow"
SELECTION_REVENUE_CUTOFF_TIMEZONE = ZoneInfo("Asia/Taipei")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^\d{4,6}$")


@dataclass(frozen=True, slots=True)
class MonthlyRevenueSourceEvidence:
    """保留一筆當期月流量或同報告比較基期的來源欄位。"""

    stock_code: str
    period: str
    period_end: date | None
    revenue: Decimal
    source: str
    source_version: str
    market: str
    raw_source_version: str
    raw_source_sha256: str
    unit: str
    period_basis: str
    basis_verified: bool
    aggregate_feature_eligible: bool
    formal_pit_eligible: bool
    observed_at: datetime
    source_available_at: datetime | None
    available_at: datetime
    availability_basis: str
    input_role: str
    parent_report_period: str | None

    def __post_init__(self) -> None:
        for name in (
            "stock_code",
            "period",
            "source",
            "source_version",
            "market",
            "raw_source_version",
            "raw_source_sha256",
            "unit",
            "period_basis",
            "availability_basis",
            "input_role",
        ):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} 必須是字串")
        if self.parent_report_period is not None and type(self.parent_report_period) is not str:
            raise TypeError("parent_report_period 必須是字串或 None")
        if type(self.revenue) is not Decimal:
            raise TypeError("revenue 必須是 Decimal")
        if self.period_end is not None and type(self.period_end) is not date:
            raise TypeError("period_end 必須是 date 或 None")
        for name in ("basis_verified", "aggregate_feature_eligible", "formal_pit_eligible"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} 必須是 bool")
        _require_aware_datetime(self.observed_at, "observed_at")
        _require_aware_datetime(self.available_at, "available_at")
        if self.source_available_at is not None:
            _require_aware_datetime(self.source_available_at, "source_available_at")

    def to_dict(self) -> dict[str, object]:
        """回傳不含 float 的 JSON-ready 原始事實投影。"""

        return {
            "stock_code": self.stock_code,
            "period": self.period,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "revenue": _decimal_text(self.revenue),
            "source": self.source,
            "source_version": self.source_version,
            "market": self.market,
            "raw_source_version": self.raw_source_version,
            "raw_source_sha256": self.raw_source_sha256,
            "unit": self.unit,
            "period_basis": self.period_basis,
            "basis_verified": self.basis_verified,
            "aggregate_feature_eligible": self.aggregate_feature_eligible,
            "formal_pit_eligible": self.formal_pit_eligible,
            "observed_at": _datetime_text(self.observed_at),
            "source_available_at": (
                _datetime_text(self.source_available_at)
                if self.source_available_at is not None
                else None
            ),
            "available_at": _datetime_text(self.available_at),
            "availability_basis": self.availability_basis,
            "input_role": self.input_role,
            "parent_report_period": self.parent_report_period,
        }


@dataclass(frozen=True, slots=True)
class SelectionMonthlyRevenueYoYFact:
    """一檔股票的月營收年增率與完整 current-only 來源證據。"""

    stock_code: str
    state: SelectionRevenueYoYState
    availability: SelectionRevenueYoYAvailability
    decision_cutoff: datetime | None
    decision_date: date | None
    current: MonthlyRevenueSourceEvidence | None
    comparator: MonthlyRevenueSourceEvidence | None
    growth_ratio: Decimal | None
    growth_percent: Decimal | None
    comparison_snapshot_sha256: str | None
    reason_codes: tuple[str, ...] = ()
    source_diagnostics: tuple[str, ...] = ()
    schema_version: Literal["selection-monthly-revenue-yoy.v1"] = (
        "selection-monthly-revenue-yoy.v1"
    )
    method_id: Literal["selection.monthly_revenue_yoy"] = (
        "selection.monthly_revenue_yoy"
    )
    method_version: Literal["current-observed-decimal.v1"] = (
        "current-observed-decimal.v1"
    )
    source_scope: Literal["current_observed_only"] = "current_observed_only"
    formula: Literal["(current_twd - comparator_twd) / comparator_twd"] = (
        "(current_twd - comparator_twd) / comparator_twd"
    )
    ratio_unit: Literal["ratio"] = "ratio"
    percent_unit: Literal["percent"] = "percent"
    current_unit: Literal["TWD"] = "TWD"
    period_basis: Literal["monthly_flow"] = "monthly_flow"
    historical_pit_eligible: Literal[False] = False
    formal_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if type(self.stock_code) is not str or not self.stock_code:
            raise TypeError("stock_code 必須是非空字串")
        if self.state not in {"observed", "unknown"}:
            raise ValueError("state 不支援")
        if self.availability not in {"verified", "unknown", "unavailable"}:
            raise ValueError("availability 不支援")
        if self.decision_cutoff is not None:
            _require_aware_datetime(self.decision_cutoff, "decision_cutoff")
        if self.decision_date is not None and type(self.decision_date) is not date:
            raise TypeError("decision_date 必須是 date 或 None")
        for name in ("current", "comparator"):
            value = getattr(self, name)
            if value is not None and type(value) is not MonthlyRevenueSourceEvidence:
                raise TypeError(f"{name} 必須是 MonthlyRevenueSourceEvidence 或 None")
        for name in ("growth_ratio", "growth_percent"):
            value = getattr(self, name)
            if value is not None and (type(value) is not Decimal or not value.is_finite()):
                raise TypeError(f"{name} 必須是有限 Decimal 或 None")
        if type(self.reason_codes) is not tuple or any(
            type(item) is not str or not item for item in self.reason_codes
        ):
            raise TypeError("reason_codes 必須是非空字串 tuple")
        if type(self.source_diagnostics) is not tuple or any(
            type(item) is not str for item in self.source_diagnostics
        ):
            raise TypeError("source_diagnostics 必須是字串 tuple")
        if self.comparison_snapshot_sha256 is not None and (
            not isinstance(self.comparison_snapshot_sha256, str)
            or not _SHA256_RE.fullmatch(self.comparison_snapshot_sha256)
        ):
            raise ValueError("comparison_snapshot_sha256 格式不符")
        if self.historical_pit_eligible is not False or self.formal_pit_eligible is not False:
            raise ValueError("current-only 營收事實不得標記為 PIT eligible")
        if self.state == "observed":
            if (
                self.availability != "verified"
                or self.decision_cutoff is None
                or self.current is None
                or self.comparator is None
                or self.growth_ratio is None
                or self.growth_percent is None
                or self.reason_codes
            ):
                raise ValueError("observed YoY 事實缺少已核驗來源證據")
        elif self.growth_ratio is not None or self.growth_percent is not None:
            raise ValueError("unknown YoY 事實不可攜帶數值")

    @property
    def identity_sha256(self) -> str:
        return sha256(self.to_json().encode("utf-8")).hexdigest()

    @property
    def growth_ratio_unit(self) -> str:
        return self.ratio_unit

    @property
    def growth_percent_unit(self) -> str:
        return self.percent_unit

    def to_dict(self) -> dict[str, object]:
        """回傳可持久化、數值不含 float 的完整來源投影。"""

        return {
            "schema_version": self.schema_version,
            "stock_code": self.stock_code,
            "state": self.state,
            "availability": self.availability,
            "decision_cutoff": (
                _datetime_text(self.decision_cutoff)
                if self.decision_cutoff is not None
                else None
            ),
            "decision_date": self.decision_date.isoformat() if self.decision_date else None,
            "current": self.current.to_dict() if self.current else None,
            "comparator": self.comparator.to_dict() if self.comparator else None,
            "growth_ratio": _decimal_text(self.growth_ratio),
            "growth_ratio_unit": self.ratio_unit,
            "growth_percent": _decimal_text(self.growth_percent),
            "growth_percent_unit": self.percent_unit,
            "current_unit": self.current_unit,
            "period_basis": self.period_basis,
            "formula": self.formula,
            "method_id": self.method_id,
            "method_version": self.method_version,
            "source_scope": self.source_scope,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "comparison_snapshot_sha256": self.comparison_snapshot_sha256,
            "reason_codes": list(self.reason_codes),
            "source_diagnostics": list(self.source_diagnostics),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


def project_selection_monthly_revenue_yoy(
    result: CurrentMonthlyRevenueReadResult,
) -> SelectionMonthlyRevenueYoYFact:
    """從 provider 的單股結果投影出嚴格 current-only YoY 事實。"""

    if type(result) is not CurrentMonthlyRevenueReadResult:
        raise TypeError("result 必須是 CurrentMonthlyRevenueReadResult")

    cutoff = result.cutoff_at
    cutoff_is_aware = _is_aware_datetime(cutoff)
    normalized_cutoff = cutoff.astimezone(timezone.utc) if cutoff_is_aware else None
    decision_date = (
        cutoff.astimezone(SELECTION_REVENUE_CUTOFF_TIMEZONE).date()
        if cutoff_is_aware
        else None
    )
    current, current_reason = _select_current_observation(result)
    comparator = result.comparison_baseline
    current_evidence = _evidence(current) if current is not None else None
    comparator_evidence = _evidence(comparator) if comparator is not None else None
    reasons: list[str] = []

    if not cutoff_is_aware:
        reasons.append("decision_cutoff_not_aware")
    if result.status != "ready":
        status = _safe_code(result.status)
        reasons.append(f"monthly_revenue_source_{status}")
    if current_reason is not None:
        reasons.append(current_reason)
    if current is not None and cutoff_is_aware:
        reasons.extend(_validate_source_observation(current, cutoff, role="current"))
    if comparator is None:
        reasons.append("same_report_yoy_comparator_missing")
    elif current is not None and cutoff_is_aware:
        reasons.extend(
            _validate_source_observation(
                comparator,
                cutoff,
                role="comparator",
                comparison_snapshot_sha256=result.comparison_snapshot_sha256,
            )
        )
        reasons.extend(_validate_comparator_binding(current, comparator, result))

    comparison_snapshot_sha256 = result.comparison_snapshot_sha256
    if comparison_snapshot_sha256 is not None and (
        not isinstance(comparison_snapshot_sha256, str)
        or not _SHA256_RE.fullmatch(comparison_snapshot_sha256)
    ):
        reasons.append("comparison_snapshot_sha256_invalid")

    if current is not None and comparator is not None:
        if type(current.revenue) is not Decimal or not current.revenue.is_finite():
            reasons.append("current_revenue_not_finite_decimal")
        if (
            type(comparator.revenue) is not Decimal
            or not comparator.revenue.is_finite()
            or comparator.revenue <= Decimal("0")
        ):
            reasons.append("comparison_baseline_not_positive_finite_decimal")

    unique_reasons = tuple(dict.fromkeys(reasons))
    diagnostics = tuple(str(item) for item in result.diagnostics)
    if unique_reasons:
        availability: SelectionRevenueYoYAvailability = (
            "unavailable"
            if result.status in {"missing", "unavailable"} and current is None
            else "unknown"
        )
        return SelectionMonthlyRevenueYoYFact(
            stock_code=str(result.stock_code),
            state="unknown",
            availability=availability,
            decision_cutoff=normalized_cutoff,
            decision_date=decision_date,
            current=current_evidence,
            comparator=comparator_evidence,
            growth_ratio=None,
            growth_percent=None,
            comparison_snapshot_sha256=(
                comparison_snapshot_sha256
                if isinstance(comparison_snapshot_sha256, str)
                and _SHA256_RE.fullmatch(comparison_snapshot_sha256)
                else None
            ),
            reason_codes=unique_reasons,
            source_diagnostics=diagnostics,
        )

    assert current is not None and comparator is not None and normalized_cutoff is not None
    with localcontext() as context:
        context.prec = 28
        growth_ratio = (current.revenue - comparator.revenue) / comparator.revenue
        growth_percent = growth_ratio * Decimal("100")
    return SelectionMonthlyRevenueYoYFact(
        stock_code=current.stock_code,
        state="observed",
        availability="verified",
        decision_cutoff=normalized_cutoff,
        decision_date=decision_date,
        current=current_evidence,
        comparator=comparator_evidence,
        growth_ratio=growth_ratio,
        growth_percent=growth_percent,
        comparison_snapshot_sha256=comparison_snapshot_sha256,
        reason_codes=(),
        source_diagnostics=diagnostics,
    )


def evaluate_monthly_revenue_yoy_min(
    fact: SelectionMonthlyRevenueYoYFact,
    *,
    minimum_yoy_percent: Decimal,
) -> SelectionConditionState:
    """套用呼叫端明確提供的既有 YoY 百分比門檻；不建立預設值。"""

    if type(fact) is not SelectionMonthlyRevenueYoYFact:
        raise TypeError("fact 必須是 SelectionMonthlyRevenueYoYFact")
    if type(minimum_yoy_percent) is not Decimal or not minimum_yoy_percent.is_finite():
        raise TypeError("minimum_yoy_percent 必須是有限 Decimal")
    if fact.state != "observed" or fact.growth_percent is None:
        return "unknown"
    return "match" if fact.growth_percent >= minimum_yoy_percent else "no_match"


def sort_selection_monthly_revenue_yoy(
    facts: tuple[SelectionMonthlyRevenueYoYFact, ...],
    *,
    descending: bool = False,
) -> tuple[SelectionMonthlyRevenueYoYFact, ...]:
    """按 YoY 百分比排序；未知值雙向置尾，股票代碼固定升序打破同值。"""

    if type(facts) is not tuple or any(
        type(item) is not SelectionMonthlyRevenueYoYFact for item in facts
    ):
        raise TypeError("facts 必須是 SelectionMonthlyRevenueYoYFact tuple")
    if type(descending) is not bool:
        raise TypeError("descending 必須是 bool")
    stock_codes = [item.stock_code for item in facts]
    if len(stock_codes) != len(set(stock_codes)):
        raise ValueError("同一 YoY 結果不可重複股票代碼")

    known: list[SelectionMonthlyRevenueYoYFact] = []
    unknown: list[SelectionMonthlyRevenueYoYFact] = []
    for item in facts:
        if item.state == "observed" and item.growth_percent is not None:
            known.append(item)
        else:
            unknown.append(item)
    known.sort(key=lambda item: item.stock_code)
    known.sort(
        key=lambda item: item.growth_percent
        if item.growth_percent is not None
        else Decimal("0"),
        reverse=descending,
    )
    unknown.sort(key=lambda item: item.stock_code)
    return tuple((*known, *unknown))


def _select_current_observation(
    result: CurrentMonthlyRevenueReadResult,
) -> tuple[CurrentObservedMonthlyRevenueInput | None, str | None]:
    latest_period = result.latest_period
    if not latest_period:
        return None, "current_monthly_revenue_period_missing"
    candidates = tuple(
        row
        for row in result.observations
        if isinstance(row, CurrentObservedMonthlyRevenueInput)
        and row.stock_code == result.stock_code
        and row.period == latest_period
        and row.input_role == "reported_period_value"
    )
    if not candidates:
        return None, "current_monthly_revenue_observation_missing"
    if len(candidates) != 1:
        return None, "current_monthly_revenue_revision_ambiguous"
    return candidates[0], None


def _validate_source_observation(
    record: CurrentObservedMonthlyRevenueInput,
    cutoff: datetime,
    *,
    role: Literal["current", "comparator"],
    comparison_snapshot_sha256: str | None = None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    stock_prefix = "current" if role == "current" else "comparator"
    if not _STOCK_CODE_RE.fullmatch(str(record.stock_code)):
        reasons.append(f"{stock_prefix}_stock_code_invalid")
    if record.source != MONTHLY_SNAPSHOT_SOURCE:
        reasons.append(f"{stock_prefix}_source_mismatch")
    if record.market not in {"twse", "tpex"}:
        reasons.append(f"{stock_prefix}_market_unknown")
    if record.unit != SELECTION_REVENUE_UNIT:
        reasons.append(f"{stock_prefix}_unit_mismatch")
    if record.period_basis != SELECTION_REVENUE_PERIOD_BASIS:
        reasons.append(f"{stock_prefix}_period_basis_mismatch")
    if record.basis_verified is not True:
        reasons.append(f"{stock_prefix}_basis_unverified")
    if record.aggregate_feature_eligible is not False:
        reasons.append(f"{stock_prefix}_aggregate_feature_scope_mismatch")
    if record.formal_pit_eligible is not False:
        reasons.append(f"{stock_prefix}_formal_pit_scope_mismatch")
    expected_role = (
        "reported_period_value"
        if role == "current"
        else "same_report_prior_year_comparison_baseline"
    )
    if record.input_role != expected_role:
        reasons.append(f"{stock_prefix}_input_role_mismatch")

    period_end = _period_end(record.period)
    if period_end is None:
        reasons.append(f"{stock_prefix}_period_invalid")
    elif period_end > cutoff.astimezone(SELECTION_REVENUE_CUTOFF_TIMEZONE).date():
        reasons.append(f"{stock_prefix}_period_after_decision_date")

    if not _is_aware_datetime(record.observed_at):
        reasons.append(f"{stock_prefix}_observed_at_not_aware")
    if not _is_aware_datetime(record.available_at):
        reasons.append(f"{stock_prefix}_available_at_not_aware")
    if record.source_available_at is not None and not _is_aware_datetime(
        record.source_available_at
    ):
        reasons.append(f"{stock_prefix}_source_available_at_not_aware")
    if reasons and any(
        reason.endswith("_not_aware") for reason in reasons
    ):
        return tuple(reasons)

    observed_utc = record.observed_at.astimezone(timezone.utc)
    available_utc = record.available_at.astimezone(timezone.utc)
    cutoff_utc = cutoff.astimezone(timezone.utc)
    source_available_utc = (
        record.source_available_at.astimezone(timezone.utc)
        if record.source_available_at is not None
        else None
    )
    if observed_utc > cutoff_utc:
        reasons.append(f"{stock_prefix}_observed_after_cutoff")
    if available_utc > cutoff_utc:
        reasons.append(f"{stock_prefix}_available_after_cutoff")
    if source_available_utc is not None:
        if source_available_utc > cutoff_utc:
            reasons.append(f"{stock_prefix}_source_available_after_cutoff")
        if source_available_utc > observed_utc:
            reasons.append(f"{stock_prefix}_source_available_after_observation")
        if record.availability_basis != "official_body_capture":
            reasons.append(f"{stock_prefix}_availability_basis_mismatch")
        expected_available = max(observed_utc, source_available_utc)
    else:
        if record.availability_basis != "local_verified_observation":
            reasons.append(f"{stock_prefix}_availability_basis_unknown")
        expected_available = observed_utc
    if available_utc != expected_available:
        reasons.append(f"{stock_prefix}_available_at_inconsistent")

    try:
        raw_parts = _monthly_source_version_parts(record.raw_source_version)
    except (TypeError, ValueError):
        raw_parts = None
    raw_report_period = (
        record.period if role == "current" else record.parent_report_period
    )
    if (
        not _SHA256_RE.fullmatch(str(record.raw_source_sha256))
        or raw_parts is None
        or raw_parts != (record.market, raw_report_period, record.raw_source_sha256)
    ):
        reasons.append(f"{stock_prefix}_raw_source_identity_invalid")
    else:
        source_available_text = (
            source_available_utc.isoformat() if source_available_utc is not None else ""
        )
        source_version = record.source_version
        if role == "comparator" and ":verified-csv-sha256:" in source_version:
            suffix = f":verified-csv-sha256:{comparison_snapshot_sha256}"
            if (
                comparison_snapshot_sha256 is not None
                and _SHA256_RE.fullmatch(comparison_snapshot_sha256)
                and source_version.endswith(suffix)
            ):
                source_version = source_version[: -len(suffix)]
            else:
                source_version = ""
        version_valid = (
            _is_monthly_derived_source_version(
                source_version,
                market=record.market,
                period=record.period,
                stock_code=record.stock_code,
                value=str(record.revenue),
                unit=record.unit,
                source_available_at=source_available_text,
            )
            if role == "current"
            else _is_monthly_yoy_comparator_source_version(
                source_version,
                market=record.market,
                comparator_period=record.period,
                stock_code=record.stock_code,
                value=str(record.revenue),
                unit=record.unit,
                source_available_at=source_available_text,
            )
        )
        if not version_valid:
            reasons.append(f"{stock_prefix}_derived_source_version_invalid")
    if type(record.revenue) is not Decimal or not record.revenue.is_finite():
        reasons.append(f"{stock_prefix}_revenue_not_finite_decimal")
    return tuple(reasons)


def _validate_comparator_binding(
    current: CurrentObservedMonthlyRevenueInput,
    comparator: CurrentObservedMonthlyRevenueInput,
    result: CurrentMonthlyRevenueReadResult,
) -> tuple[str, ...]:
    reasons: list[str] = []
    expected_period = _prior_year_period(current.period)
    if expected_period is None or comparator.period != expected_period:
        reasons.append("same_report_yoy_comparator_period_mismatch")
    if comparator.parent_report_period != current.period:
        reasons.append("same_report_yoy_comparator_parent_mismatch")
    if comparator.stock_code != current.stock_code:
        reasons.append("same_report_yoy_comparator_stock_mismatch")
    for field_name in ("source", "market", "raw_source_version", "raw_source_sha256", "unit", "period_basis"):
        if getattr(comparator, field_name) != getattr(current, field_name):
            reasons.append(f"same_report_yoy_comparator_{field_name}_mismatch")
    if comparator.source_available_at != current.source_available_at:
        reasons.append("same_report_yoy_comparator_source_clock_mismatch")
    if comparator.availability_basis != current.availability_basis:
        reasons.append("same_report_yoy_comparator_availability_basis_mismatch")
    if comparator.basis_verified is not True:
        reasons.append("same_report_yoy_comparator_basis_unverified")
    if comparator.aggregate_feature_eligible is not False:
        reasons.append("same_report_yoy_comparator_aggregate_scope_mismatch")
    if comparator.formal_pit_eligible is not False:
        reasons.append("same_report_yoy_comparator_formal_pit_scope_mismatch")
    comparison_sha = result.comparison_snapshot_sha256
    expected_version = None
    if expected_period is not None:
        source_available_at = current.source_available_at
        source_available_text = (
            source_available_at.astimezone(timezone.utc).isoformat()
            if source_available_at is not None
            and _is_aware_datetime(source_available_at)
            else ""
        )
        try:
            expected_version = _derived_monthly_yoy_comparator_version(
                current.raw_source_version,
                stock_code=current.stock_code,
                source_period=current.period,
                comparator_period=expected_period,
                value=str(comparator.revenue),
                unit=comparator.unit,
                source_available_at=source_available_text,
            )
        except (TypeError, ValueError):
            reasons.append("same_report_yoy_comparator_source_identity_invalid")
    if expected_version is not None:
        if comparator.source_version == expected_version:
            pass
        elif (
            comparison_sha is not None
            and _SHA256_RE.fullmatch(comparison_sha)
            and comparator.source_version
            == f"{expected_version}:verified-csv-sha256:{comparison_sha}"
        ):
            pass
        else:
            reasons.append("same_report_yoy_comparator_version_mismatch")
    return tuple(reasons)


def _evidence(
    record: CurrentObservedMonthlyRevenueInput,
) -> MonthlyRevenueSourceEvidence:
    period = str(record.period)
    return MonthlyRevenueSourceEvidence(
        stock_code=str(record.stock_code),
        period=period,
        period_end=_period_end(period),
        revenue=record.revenue,
        source=str(record.source),
        source_version=str(record.source_version),
        market=str(record.market),
        raw_source_version=str(record.raw_source_version),
        raw_source_sha256=str(record.raw_source_sha256),
        unit=str(record.unit),
        period_basis=str(record.period_basis),
        basis_verified=record.basis_verified is True,
        aggregate_feature_eligible=record.aggregate_feature_eligible is True,
        formal_pit_eligible=record.formal_pit_eligible is True,
        observed_at=record.observed_at,
        source_available_at=record.source_available_at,
        available_at=record.available_at,
        availability_basis=str(record.availability_basis),
        input_role=str(record.input_role),
        parent_report_period=record.parent_report_period,
    )


def _period_end(period: str) -> date | None:
    if type(period) is not str or not re.fullmatch(r"\d{4}-\d{2}", period):
        return None
    year, month = (int(part) for part in period.split("-"))
    if year < 1 or not 1 <= month <= 12:
        return None
    from calendar import monthrange

    return date(year, month, monthrange(year, month)[1])


def _prior_year_period(period: str) -> str | None:
    if _period_end(period) is None:
        return None
    year, month = (int(part) for part in period.split("-"))
    if year <= 1:
        return None
    return f"{year - 1:04d}-{month:02d}"


def _is_aware_datetime(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _require_aware_datetime(value: object, name: str) -> None:
    if not _is_aware_datetime(value):
        raise ValueError(f"{name} 必須是 aware datetime")


def _datetime_text(value: datetime) -> str:
    _require_aware_datetime(value, "datetime")
    return value.astimezone(timezone.utc).isoformat()


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not value.is_finite():
        raise ValueError("不可序列化非有限 Decimal")
    return format(value, "f")


def _safe_code(value: object) -> str:
    text = str(value or "unknown").strip().casefold()
    if re.fullmatch(r"[a-z0-9_]{1,48}", text):
        return text
    return "invalid"
