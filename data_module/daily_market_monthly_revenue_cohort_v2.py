"""把每日 TWSE/TPEX 月營收 cohort 綁入 current-only 全清冊讀取。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import re
from typing import Literal, Sequence, cast

from data_module.current_fundamental_snapshots import (
    MONTHLY_SNAPSHOT_SOURCE,
    _monthly_source_version_parts,
)
from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueMarketSnapshotPin,
)
from data_module.fundamental_read_snapshot_cohort_v2 import (
    FinishedFundamentalSnapshotReadCohortV2,
    FundamentalReadSnapshotReferenceV2,
    FundamentalSnapshotSourceClockV2,
    decode_snapshot_reference_v2,
    encode_snapshot_reference_v2,
    make_snapshot_reference_v2,
)
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    CurrentObservedMonthlyRevenueInput,
)
from data_module.selection_fact_readers import _result_identity_sha256_v2


DAILY_MARKET_MONTHLY_REVENUE_FACT_V2_SCHEMA: Literal[
    "daily-market-monthly-revenue-fact.v2"
] = (
    "daily-market-monthly-revenue-fact.v2"
)
DAILY_MARKET_MONTHLY_REVENUE_FINISHED_COHORT_V2_SCHEMA: Literal[
    "daily-market-monthly-revenue-finished-cohort.v2"
] = (
    "daily-market-monthly-revenue-finished-cohort.v2"
)
DAILY_MARKET_MONTHLY_REVENUE_SOURCE_REFERENCE_V3_SCHEMA: Literal[
    "daily-market-monthly-revenue-source-reference.v3"
] = (
    "daily-market-monthly-revenue-source-reference.v3"
)
DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND: Literal[
    "daily_monthly_revenue_cohort"
] = "daily_monthly_revenue_cohort"
DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE: Literal[
    "current_observed_only"
] = "current_observed_only"
DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY: Literal[
    "cohort_hour_bound"
] = "cohort_hour_bound"
_MAX_REFERENCE_BYTES = 32 * 1024 * 1024
_MAX_REFERENCE_DEPTH = 24
_MAX_DECLARED_CODES = 100_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[0-9]{4,6}$")
_PERIOD_RE = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
_RESULT_STATUSES = frozenset({"ready", "missing", "invalid", "ambiguous", "unavailable"})
_FACT_STATES = ("blocked", "observed", "unknown")
_FINISHED_ISSUER = object()


class DailyMarketMonthlyRevenueCohortV2Error(ValueError):
    """每日月營收 V2 fact、完成 token 或 V3 參照不符合契約。"""


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_json_value_not_canonical"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()


def _require_sha256(value: object, field_name: str) -> str:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{field_name}_sha256_invalid"
        )
    return value


def _require_text(value: object, field_name: str, *, max_length: int = 512) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or len(value) > max_length
        or any(ord(char) < 0x20 for char in value)
    ):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{field_name}_invalid"
        )
    return value


def _require_period(value: object, field_name: str) -> str:
    if type(value) is not str or not _PERIOD_RE.fullmatch(value):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{field_name}_invalid"
        )
    return value


def _require_aware(value: object, field_name: str) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{field_name}_must_be_aware"
        )
    return value


def _datetime_text(value: datetime) -> str:
    return _require_aware(value, "datetime").astimezone(timezone.utc).isoformat()


def _require_nonnegative_int(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{field_name}_must_be_nonnegative_int"
        )
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_json_duplicate_key"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise DailyMarketMonthlyRevenueCohortV2Error(
        f"monthly_revenue_v3_json_constant_not_allowed:{value}"
    )


def _validate_json_depth(raw: bytes) -> None:
    depth = 0
    in_string = False
    escaped = False
    for byte in raw:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x7B, 0x5B):
            depth += 1
            if depth > _MAX_REFERENCE_DEPTH:
                raise DailyMarketMonthlyRevenueCohortV2Error(
                    "monthly_revenue_v3_json_depth_exceeded"
                )
        elif byte in (0x7D, 0x5D):
            depth -= 1
            if depth < 0:
                raise DailyMarketMonthlyRevenueCohortV2Error(
                    "monthly_revenue_v3_json_depth_invalid"
                )
    if in_string or depth != 0:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v3_json_depth_invalid"
        )


def _prior_year_period(period: str) -> str:
    year, month = period.split("-")
    return f"{int(year) - 1:04d}-{month}"


def _latest_current(
    result: CurrentMonthlyRevenueReadResult,
) -> CurrentObservedMonthlyRevenueInput | None:
    if result.latest_period is None:
        return None
    candidates = tuple(
        item
        for item in result.observations
        if item.stock_code == result.stock_code
        and item.period == result.latest_period
        and item.input_role == "reported_period_value"
    )
    if len(candidates) > 1:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_latest_current_not_unique"
        )
    return candidates[0] if candidates else None


def _market_pin_for_observation(
    pin: DailyMonthlyRevenueCohortPin,
    observation: CurrentObservedMonthlyRevenueInput,
) -> DailyMonthlyRevenueMarketSnapshotPin:
    try:
        return pin.for_market(observation.market)
    except (AttributeError, ValueError) as exc:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_observation_market_not_pinned:{observation.market}"
        ) from exc


def _validate_observation(
    observation: object,
    *,
    stock_code: str,
    pin: DailyMonthlyRevenueCohortPin,
    cutoff: datetime,
    report_period: str,
    role: Literal["current", "comparator"],
) -> CurrentObservedMonthlyRevenueInput:
    if type(observation) is not CurrentObservedMonthlyRevenueInput:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_observation_type_invalid"
        )
    item = observation
    if item.stock_code != stock_code or not _STOCK_CODE_RE.fullmatch(stock_code):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_stock_code_mismatch"
        )
    expected_role = (
        "reported_period_value"
        if role == "current"
        else "same_report_prior_year_comparison_baseline"
    )
    if item.input_role != expected_role:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_input_role_mismatch"
        )
    _require_period(item.period, f"{role}_period")
    if type(item.revenue) is not Decimal or not item.revenue.is_finite():
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_revenue_must_be_finite_decimal"
        )
    if (
        item.source != MONTHLY_SNAPSHOT_SOURCE
        or item.unit != "TWD"
        or item.period_basis != "monthly_flow"
        or item.basis_verified is not True
        or item.aggregate_feature_eligible is not False
        or item.formal_pit_eligible is not False
    ):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_source_unit_or_basis_invalid"
        )
    if item.market not in pin.required_markets:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_market_not_required"
        )
    if role == "current" and item.period != pin.period:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_current_period_does_not_match_cohort"
        )
    if role == "comparator" and item.period != _prior_year_period(report_period):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_comparator_period_mismatch"
        )
    if role == "comparator" and item.parent_report_period != report_period:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_comparator_parent_period_mismatch"
        )
    if type(item.source_version) is not str or not item.source_version:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_source_version_missing"
        )
    if type(item.raw_source_version) is not str or not item.raw_source_version:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_raw_source_version_missing"
        )
    raw_parts = _monthly_source_version_parts(item.raw_source_version)
    if (
        raw_parts is None
        or raw_parts[0] != item.market
        or raw_parts[1] != report_period
        or raw_parts[2] != item.raw_source_sha256
        or not _SHA256_RE.fullmatch(item.raw_source_sha256)
    ):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_raw_source_identity_mismatch"
        )
    if item.availability_basis not in {
        "successful_batch_completion_fallback",
        "successful_batch_completion_exact_hour_publication_guard",
        "official_timestamp_and_successful_batch_completion",
        "official_timestamp_and_successful_batch_completion_exact_hour_publication_guard",
    }:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_availability_basis_invalid"
        )
    market_pin = _market_pin_for_observation(pin, item)
    if (
        item.availability_snapshot_batch_id != market_pin.batch_id
        or item.availability_first_persisted_at != market_pin.first_persisted_at
        or item.availability_basis not in market_pin.availability_basis
    ):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_daily_batch_binding_mismatch"
        )
    observed_at = _require_aware(item.observed_at, f"{role}_observed_at")
    available_at = _require_aware(item.available_at, f"{role}_available_at")
    source_available_at = (
        _require_aware(item.source_available_at, f"{role}_source_available_at")
        if item.source_available_at is not None
        else None
    )
    if type(item.availability_first_persisted_at) is not datetime:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_availability_persisted_at_missing"
        )
    persisted_at = _require_aware(
        item.availability_first_persisted_at,
        f"{role}_availability_first_persisted_at",
    )
    if (
        observed_at.astimezone(timezone.utc) > cutoff.astimezone(timezone.utc)
        or available_at.astimezone(timezone.utc) > cutoff.astimezone(timezone.utc)
        or (
            source_available_at is not None
            and source_available_at.astimezone(timezone.utc)
            > cutoff.astimezone(timezone.utc)
        )
        or persisted_at.astimezone(timezone.utc) > cutoff.astimezone(timezone.utc)
    ):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_clock_after_cutoff"
        )
    if available_at.astimezone(timezone.utc) < pin.available_hour.astimezone(timezone.utc):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v2_{role}_available_before_cohort_hour"
        )
    if role == "comparator" and item.revenue <= 0:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_comparator_not_positive"
        )
    return item


def _validate_result(
    result: CurrentMonthlyRevenueReadResult,
    *,
    cohort_pin: DailyMonthlyRevenueCohortPin,
) -> None:
    if type(result) is not CurrentMonthlyRevenueReadResult:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_provider_result_type_invalid"
        )
    if type(result.stock_code) is not str or not _STOCK_CODE_RE.fullmatch(result.stock_code):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_provider_stock_code_invalid"
        )
    if type(result.status) is not str or result.status not in _RESULT_STATUSES:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_provider_status_invalid"
        )
    cutoff = _require_aware(result.cutoff_at, "provider_cutoff_at")
    cohort_available_hour = _require_aware(
        cohort_pin.available_hour,
        "cohort_available_hour",
    )
    if cohort_available_hour.astimezone(timezone.utc) > cutoff.astimezone(timezone.utc):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_cohort_hour_after_cutoff"
        )
    if result.latest_period is not None:
        _require_period(result.latest_period, "provider_latest_period")
    if type(result.observations) is not tuple or len(result.observations) > 100_000:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_provider_observations_invalid"
        )
    if type(result.diagnostics) is not tuple or any(
        type(item) is not str or not item or len(item) > 4_096
        for item in result.diagnostics
    ):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_provider_diagnostics_invalid"
        )
    if (
        type(result.blocked_periods) is not tuple
        or any(type(period) is not str for period in result.blocked_periods)
        or result.blocked_periods != tuple(sorted(set(result.blocked_periods)))
    ):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_blocked_periods_not_canonical"
        )
    for period in result.blocked_periods:
        _require_period(period, "blocked_period")
    _require_nonnegative_int(
        result.diagnostic_source_row_count, "diagnostic_source_row_count"
    )
    _require_nonnegative_int(
        result.diagnostic_comparator_row_count,
        "diagnostic_comparator_row_count",
    )
    if result.comparison_snapshot_sha256 is not None:
        _require_sha256(result.comparison_snapshot_sha256, "comparison_snapshot")
    for item in result.observations:
        if type(item) is not CurrentObservedMonthlyRevenueInput:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_provider_observation_type_invalid"
            )
        report_period = (
            item.parent_report_period
            if item.input_role == "same_report_prior_year_comparison_baseline"
            else item.period
        )
        if report_period is None:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_observation_report_period_missing"
            )
        _validate_observation(
            item,
            stock_code=result.stock_code,
            pin=cohort_pin,
            cutoff=cutoff,
            report_period=report_period,
            role=(
                "comparator"
                if item.input_role == "same_report_prior_year_comparison_baseline"
                else "current"
            ),
        )
    current = _latest_current(result)
    comparator = result.comparison_baseline
    if comparator is not None:
        if current is None:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_comparator_without_current"
            )
        _validate_observation(
            comparator,
            stock_code=result.stock_code,
            pin=cohort_pin,
            cutoff=cutoff,
            report_period=current.period,
            role="comparator",
        )
        if (
            comparator.parent_report_period != current.period
            or comparator.period != _prior_year_period(current.period)
            or comparator.raw_source_version != current.raw_source_version
            or comparator.raw_source_sha256 != current.raw_source_sha256
            or comparator.market != current.market
            or comparator.unit != current.unit
        ):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_comparator_not_bound_to_current_report"
            )
    if result.status == "ready":
        if current is None or result.latest_period != cohort_pin.period:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_ready_result_missing_pinned_current"
            )


def _classify_result_state(
    result: CurrentMonthlyRevenueReadResult,
) -> Literal["observed", "unknown", "blocked"]:
    current = _latest_current(result)
    if result.status == "ready":
        if current is None:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_ready_result_missing_current"
            )
        return "observed" if result.comparison_baseline is not None else "unknown"
    if result.status in {"invalid", "ambiguous", "unavailable"} or result.blocked_periods:
        return "blocked"
    return "unknown"


def _reason_codes(result: CurrentMonthlyRevenueReadResult) -> tuple[str, ...]:
    current = _latest_current(result)
    comparator = result.comparison_baseline
    reasons: list[str] = []
    if result.blocked_periods:
        reasons.append("current_monthly_revenue_period_blocked_by_unverified_revision")
    elif result.status in {"invalid", "ambiguous", "unavailable"}:
        reasons.append(f"current_monthly_revenue_provider_{result.status}")
    if result.status == "missing":
        if result.diagnostic_source_row_count > 0 and current is None:
            reasons.append("current_monthly_revenue_no_cutoff_eligible_observation")
        else:
            reasons.append("current_monthly_revenue_missing")
    if current is not None and comparator is None:
        if any(
            "comparator_observed_after_invocation_freeze" in item
            for item in result.diagnostics
        ):
            reasons.append("same_report_yoy_comparator_observed_after_cutoff")
        else:
            reasons.append("same_report_yoy_comparator_missing_or_unverified")
    if result.status == "ready" and current is None:
        reasons.append("current_monthly_revenue_current_observation_missing")
    if not reasons and result.status != "ready":
        reasons.append(f"current_monthly_revenue_{result.status}")
    return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True, slots=True)
class DailyMarketMonthlyRevenueFactV2:
    """一檔股票的原始 provider 結果、identity 與每日 cohort 綁定。"""

    result: CurrentMonthlyRevenueReadResult
    result_identity_sha256: str
    cohort_pin: DailyMonthlyRevenueCohortPin
    source_kind: Literal["daily_monthly_revenue_cohort"] = "daily_monthly_revenue_cohort"

    def __post_init__(self) -> None:
        if type(self.cohort_pin) is not DailyMonthlyRevenueCohortPin:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_fact_cohort_pin_type_invalid"
            )
        if type(self.source_kind) is not str or self.source_kind != DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_fact_source_kind_invalid"
            )
        _validate_result(self.result, cohort_pin=self.cohort_pin)
        expected = _result_identity_sha256_v2(
            self.result,
            cohort_pin=self.cohort_pin,
        )
        if type(self.result_identity_sha256) is not str or self.result_identity_sha256 != expected:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_fact_result_identity_mismatch"
            )

    @property
    def stock_code(self) -> str:
        return self.result.stock_code

    @property
    def status(self) -> str:
        return self.result.status

    @property
    def current(self) -> CurrentObservedMonthlyRevenueInput | None:
        return _latest_current(self.result)

    @property
    def comparator(self) -> CurrentObservedMonthlyRevenueInput | None:
        return self.result.comparison_baseline

    @property
    def state(self) -> Literal["observed", "unknown", "blocked"]:
        return _classify_result_state(self.result)

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return _reason_codes(self.result)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(
            {
                "schema_version": DAILY_MARKET_MONTHLY_REVENUE_FACT_V2_SCHEMA,
                "source_kind": self.source_kind,
                "source_scope": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE,
                "availability_status": DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY,
                "historical_pit_eligible": False,
                "formal_pit_eligible": False,
                "stock_code": self.stock_code,
                "result_identity_sha256": self.result_identity_sha256,
                "cohort_sha256": self.cohort_pin.cohort_sha256,
                "state": self.state,
                "reason_codes": list(self.reason_codes),
            }
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": DAILY_MARKET_MONTHLY_REVENUE_FACT_V2_SCHEMA,
            "source_kind": self.source_kind,
            "source_scope": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE,
            "availability_status": DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "stock_code": self.stock_code,
            "provider_status": self.status,
            "state": self.state,
            "latest_period": self.result.latest_period,
            "result_identity_sha256": self.result_identity_sha256,
            "cohort_sha256": self.cohort_pin.cohort_sha256,
            "reason_codes": list(self.reason_codes),
            "fact_identity_sha256": self.identity_sha256,
        }


def _count_result_statuses(
    facts: Sequence[DailyMarketMonthlyRevenueFactV2],
) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for fact in facts:
        counts[fact.status] = counts.get(fact.status, 0) + 1
    return tuple(sorted(counts.items()))


def _count_fact_states(
    facts: Sequence[DailyMarketMonthlyRevenueFactV2],
) -> tuple[tuple[str, int], ...]:
    counts = {state: 0 for state in _FACT_STATES}
    for fact in facts:
        counts[fact.state] += 1
    return tuple((state, counts[state]) for state in _FACT_STATES)


def _identity_ledger(
    facts: Sequence[DailyMarketMonthlyRevenueFactV2],
) -> tuple[tuple[str, str], ...]:
    return tuple((fact.stock_code, fact.identity_sha256) for fact in facts)


def _source_content_identity(
    *,
    source_clock: FundamentalSnapshotSourceClockV2,
    declared_stock_codes: tuple[str, ...],
    result_identity_by_stock: tuple[tuple[str, str], ...],
    fact_identity_by_stock: tuple[tuple[str, str], ...],
    reader_result_status_counts: tuple[tuple[str, int], ...],
    fact_state_counts: tuple[tuple[str, int], ...],
) -> str:
    return _canonical_sha256(
        {
            "schema_version": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_REFERENCE_V3_SCHEMA,
            "source_kind": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND,
            "source_scope": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE,
            "availability_status": DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "decision_cutoff": _datetime_text(source_clock.decision_cutoff),
            "upstream_source_content_identity_sha256": (
                source_clock.source_content_identity_sha256
            ),
            "daily_cohort_pin": source_clock.cohort_pin.to_dict(),
            "declared_stock_codes": list(declared_stock_codes),
            "result_identity_by_stock": [list(item) for item in result_identity_by_stock],
            "fact_identity_by_stock": [list(item) for item in fact_identity_by_stock],
            "reader_result_status_counts": [
                list(item) for item in reader_result_status_counts
            ],
            "fact_state_counts": [list(item) for item in fact_state_counts],
        }
    )


def _finished_identity(
    *,
    upstream_reference: FundamentalReadSnapshotReferenceV2,
    upstream_reference_sha256: str,
    source_content_identity_sha256: str,
    result_identity_by_stock: tuple[tuple[str, str], ...],
    fact_identity_by_stock: tuple[tuple[str, str], ...],
    reader_result_status_counts: tuple[tuple[str, int], ...],
    fact_state_counts: tuple[tuple[str, int], ...],
) -> str:
    return _canonical_sha256(
        {
            "schema_version": DAILY_MARKET_MONTHLY_REVENUE_FINISHED_COHORT_V2_SCHEMA,
            "source_kind": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND,
            "source_scope": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE,
            "availability_status": DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "upstream_reference_identity_sha256": upstream_reference.identity_sha256,
            "upstream_reference_sha256": upstream_reference_sha256,
            "source_content_identity_sha256": source_content_identity_sha256,
            "result_identity_by_stock": [
                list(item) for item in result_identity_by_stock
            ],
            "fact_identity_by_stock": [list(item) for item in fact_identity_by_stock],
            "reader_result_status_counts": [
                list(item) for item in reader_result_status_counts
            ],
            "fact_state_counts": [list(item) for item in fact_state_counts],
        }
    )


@dataclass(frozen=True, slots=True, init=False)
class FinishedDailyMarketMonthlyRevenueCohortV2:
    """由 private issuer 發行的全清冊月營收結果；不提供 JSON 驗證式建構。"""

    snapshot_finished: FinishedFundamentalSnapshotReadCohortV2
    upstream_reference: FundamentalReadSnapshotReferenceV2
    facts: tuple[DailyMarketMonthlyRevenueFactV2, ...]
    result_identity_by_stock: tuple[tuple[str, str], ...]
    fact_identity_by_stock: tuple[tuple[str, str], ...]
    reader_result_status_counts: tuple[tuple[str, int], ...]
    fact_state_counts: tuple[tuple[str, int], ...]
    source_content_identity_sha256: str
    finished_cohort_identity_sha256: str
    schema_version: Literal[
        "daily-market-monthly-revenue-finished-cohort.v2"
    ] = "daily-market-monthly-revenue-finished-cohort.v2"
    source_kind: Literal["daily_monthly_revenue_cohort"] = "daily_monthly_revenue_cohort"
    source_scope: Literal["current_observed_only"] = "current_observed_only"
    availability_status: Literal["cohort_hour_bound"] = "cohort_hour_bound"
    historical_pit_eligible: Literal[False] = False
    formal_pit_eligible: Literal[False] = False

    def __init__(
        self,
        *,
        snapshot_finished: FinishedFundamentalSnapshotReadCohortV2,
        upstream_reference: FundamentalReadSnapshotReferenceV2,
        facts: tuple[DailyMarketMonthlyRevenueFactV2, ...],
        result_identity_by_stock: tuple[tuple[str, str], ...],
        fact_identity_by_stock: tuple[tuple[str, str], ...],
        reader_result_status_counts: tuple[tuple[str, int], ...],
        fact_state_counts: tuple[tuple[str, int], ...],
        source_content_identity_sha256: str,
        finished_cohort_identity_sha256: str,
        _issuer: object,
    ) -> None:
        if _issuer is not _FINISHED_ISSUER:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_private_issuer_required"
            )
        for name, value in (
            ("snapshot_finished", snapshot_finished),
            ("upstream_reference", upstream_reference),
            ("facts", facts),
            ("result_identity_by_stock", result_identity_by_stock),
            ("fact_identity_by_stock", fact_identity_by_stock),
            ("reader_result_status_counts", reader_result_status_counts),
            ("fact_state_counts", fact_state_counts),
            ("source_content_identity_sha256", source_content_identity_sha256),
            ("finished_cohort_identity_sha256", finished_cohort_identity_sha256),
        ):
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "schema_version",
            DAILY_MARKET_MONTHLY_REVENUE_FINISHED_COHORT_V2_SCHEMA,
        )
        object.__setattr__(self, "source_kind", DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND)
        object.__setattr__(self, "source_scope", DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE)
        object.__setattr__(
            self, "availability_status", DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY
        )
        object.__setattr__(self, "historical_pit_eligible", False)
        object.__setattr__(self, "formal_pit_eligible", False)
        self._validate_issued_contents()

    def _validate_issued_contents(self) -> None:
        if type(self.snapshot_finished) is not FinishedFundamentalSnapshotReadCohortV2:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_snapshot_token_invalid"
            )
        if type(self.upstream_reference) is not FundamentalReadSnapshotReferenceV2:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_upstream_reference_invalid"
            )
        expected_reference = make_snapshot_reference_v2(
            self.snapshot_finished,
            snapshot_root=self.upstream_reference.snapshot_root,
            snapshot_id=self.upstream_reference.snapshot_id,
        )
        if expected_reference != self.upstream_reference:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_upstream_reference_mismatch"
            )
        declared = self.snapshot_finished.processed_stock_codes
        if (
            type(self.facts) is not tuple
            or len(self.facts) != len(declared)
            or any(type(fact) is not DailyMarketMonthlyRevenueFactV2 for fact in self.facts)
        ):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_fact_coverage_incomplete"
            )
        if tuple(fact.stock_code for fact in self.facts) != declared:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_fact_coverage_incomplete"
            )
        clock = self.snapshot_finished.source_clock
        if type(clock) is not FundamentalSnapshotSourceClockV2:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_source_clock_invalid"
            )
        if type(clock.cohort_pin) is not DailyMonthlyRevenueCohortPin:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_cohort_pin_invalid"
            )
        if clock.cohort_sha256 != clock.cohort_pin.cohort_sha256:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_cohort_hash_mismatch"
            )
        clock_cutoff = _require_aware(
            clock.decision_cutoff,
            "finished_decision_cutoff",
        )
        clock_cohort_hour = _require_aware(
            clock.cohort_pin.available_hour,
            "finished_cohort_available_hour",
        )
        if clock_cohort_hour.astimezone(timezone.utc) > clock_cutoff.astimezone(
            timezone.utc
        ):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_cohort_hour_after_cutoff"
            )
        if self.snapshot_finished.processed_stock_codes != clock.declared_stock_codes:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_declared_codes_mismatch"
            )
        if self.upstream_reference.daily_cohort_sha256 != clock.cohort_sha256:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_upstream_cohort_mismatch"
            )
        expected_result_ledger = tuple(
            (fact.stock_code, fact.result_identity_sha256) for fact in self.facts
        )
        if expected_result_ledger != self.snapshot_finished.result_identity_by_stock:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_result_identity_ledger_mismatch"
            )
        for fact in self.facts:
            if fact.source_kind != DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND:
                raise DailyMarketMonthlyRevenueCohortV2Error(
                    "monthly_revenue_v2_finished_fact_source_kind_invalid"
                )
            _validate_result(fact.result, cohort_pin=fact.cohort_pin)
            expected_fact_result_identity = _result_identity_sha256_v2(
                fact.result,
                cohort_pin=fact.cohort_pin,
            )
            if fact.result_identity_sha256 != expected_fact_result_identity:
                raise DailyMarketMonthlyRevenueCohortV2Error(
                    "monthly_revenue_v2_finished_fact_result_identity_mismatch"
                )
            if fact.cohort_pin != clock.cohort_pin:
                raise DailyMarketMonthlyRevenueCohortV2Error(
                    "monthly_revenue_v2_finished_fact_cohort_pin_mismatch"
                )
            if _require_aware(fact.result.cutoff_at, "fact_cutoff").astimezone(
                timezone.utc
            ) != clock.decision_cutoff.astimezone(timezone.utc):
                raise DailyMarketMonthlyRevenueCohortV2Error(
                    "monthly_revenue_v2_finished_fact_cutoff_mismatch"
                )
        expected_fact_ledger = _identity_ledger(self.facts)
        if self.result_identity_by_stock != expected_result_ledger:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_result_ledger_mismatch"
            )
        if self.fact_identity_by_stock != expected_fact_ledger:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_fact_ledger_mismatch"
            )
        expected_statuses = _count_result_statuses(self.facts)
        if (
            self.reader_result_status_counts != expected_statuses
            or self.snapshot_finished.result_status_counts != expected_statuses
        ):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_result_status_counts_mismatch"
            )
        expected_states = _count_fact_states(self.facts)
        if self.fact_state_counts != expected_states:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_fact_state_counts_mismatch"
            )
        if self.source_kind != DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_source_kind_invalid"
            )
        if self.source_scope != DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_source_scope_invalid"
            )
        if self.availability_status != DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_availability_status_invalid"
            )
        if self.historical_pit_eligible is not False or self.formal_pit_eligible is not False:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_pit_must_remain_false"
            )
        expected_content = _source_content_identity(
            source_clock=clock,
            declared_stock_codes=declared,
            result_identity_by_stock=expected_result_ledger,
            fact_identity_by_stock=expected_fact_ledger,
            reader_result_status_counts=expected_statuses,
            fact_state_counts=expected_states,
        )
        if self.source_content_identity_sha256 != expected_content:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_source_content_identity_mismatch"
            )
        expected_finished_identity = _finished_identity(
            upstream_reference=self.upstream_reference,
            upstream_reference_sha256=sha256(
                encode_snapshot_reference_v2(self.upstream_reference)
            ).hexdigest(),
            source_content_identity_sha256=expected_content,
            result_identity_by_stock=expected_result_ledger,
            fact_identity_by_stock=expected_fact_ledger,
            reader_result_status_counts=expected_statuses,
            fact_state_counts=expected_states,
        )
        if self.finished_cohort_identity_sha256 != expected_finished_identity:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_finished_identity_mismatch"
            )

    @property
    def declared_stock_codes(self) -> tuple[str, ...]:
        return self.snapshot_finished.processed_stock_codes

    @property
    def result_status_counts(self) -> tuple[tuple[str, int], ...]:
        return self.reader_result_status_counts

    @property
    def result_identity_sha256_by_stock(self) -> tuple[tuple[str, str], ...]:
        return self.result_identity_by_stock

    @property
    def decision_cutoff(self) -> datetime:
        return self.snapshot_finished.source_clock.decision_cutoff

    @property
    def source_clock(self) -> FundamentalSnapshotSourceClockV2:
        return self.snapshot_finished.source_clock

    @property
    def cohort_pin(self) -> DailyMonthlyRevenueCohortPin:
        return self.snapshot_finished.source_clock.cohort_pin

    @property
    def identity_sha256(self) -> str:
        return self.finished_cohort_identity_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_kind": self.source_kind,
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "snapshot_finished_identity_sha256": self.snapshot_finished.identity_sha256,
            "upstream_reference_identity_sha256": self.upstream_reference.identity_sha256,
            "decision_cutoff": _datetime_text(self.decision_cutoff),
            "declared_stock_codes": list(self.declared_stock_codes),
            "result_identity_by_stock": [list(item) for item in self.result_identity_by_stock],
            "fact_identity_by_stock": [list(item) for item in self.fact_identity_by_stock],
            "reader_result_status_counts": [
                list(item) for item in self.reader_result_status_counts
            ],
            "fact_state_counts": [list(item) for item in self.fact_state_counts],
            "source_content_identity_sha256": self.source_content_identity_sha256,
            "finished_cohort_identity_sha256": self.finished_cohort_identity_sha256,
        }


def _issue_finished_daily_market_monthly_revenue_cohort_v2(
    *,
    snapshot_finished: FinishedFundamentalSnapshotReadCohortV2,
    upstream_reference: FundamentalReadSnapshotReferenceV2,
    facts: Sequence[DailyMarketMonthlyRevenueFactV2],
) -> FinishedDailyMarketMonthlyRevenueCohortV2:
    """唯一完成 issuer；以上游 finish、pin 與每股結果 ledger 重驗全清冊。"""

    if type(snapshot_finished) is not FinishedFundamentalSnapshotReadCohortV2:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_issuer_snapshot_finished_type_invalid"
        )
    if type(upstream_reference) is not FundamentalReadSnapshotReferenceV2:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_issuer_upstream_reference_type_invalid"
        )
    if isinstance(facts, (str, bytes)) or not isinstance(facts, Sequence):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_issuer_facts_must_be_sequence"
        )
    frozen_facts = tuple(facts)
    declared = snapshot_finished.processed_stock_codes
    if len(frozen_facts) != len(declared) or tuple(
        getattr(item, "stock_code", None) for item in frozen_facts
    ) != declared:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v2_issuer_fact_coverage_incomplete_or_unordered"
        )
    for fact in frozen_facts:
        if type(fact) is not DailyMarketMonthlyRevenueFactV2:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v2_issuer_fact_type_invalid"
            )
    result_ledger = tuple(
        (fact.stock_code, fact.result_identity_sha256) for fact in frozen_facts
    )
    fact_ledger = _identity_ledger(frozen_facts)
    status_counts = _count_result_statuses(frozen_facts)
    state_counts = _count_fact_states(frozen_facts)
    source_content_identity = _source_content_identity(
        source_clock=snapshot_finished.source_clock,
        declared_stock_codes=declared,
        result_identity_by_stock=result_ledger,
        fact_identity_by_stock=fact_ledger,
        reader_result_status_counts=status_counts,
        fact_state_counts=state_counts,
    )
    finished_identity = _finished_identity(
        upstream_reference=upstream_reference,
        upstream_reference_sha256=sha256(
            encode_snapshot_reference_v2(upstream_reference)
        ).hexdigest(),
        source_content_identity_sha256=source_content_identity,
        result_identity_by_stock=result_ledger,
        fact_identity_by_stock=fact_ledger,
        reader_result_status_counts=status_counts,
        fact_state_counts=state_counts,
    )
    return FinishedDailyMarketMonthlyRevenueCohortV2(
        snapshot_finished=snapshot_finished,
        upstream_reference=upstream_reference,
        facts=frozen_facts,
        result_identity_by_stock=result_ledger,
        fact_identity_by_stock=fact_ledger,
        reader_result_status_counts=status_counts,
        fact_state_counts=state_counts,
        source_content_identity_sha256=source_content_identity,
        finished_cohort_identity_sha256=finished_identity,
        _issuer=_FINISHED_ISSUER,
    )


def _fact_ledger_identity_sha256(
    fact_identity_by_stock: tuple[tuple[str, str], ...],
) -> str:
    return _canonical_sha256(
        {
            "schema_version": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_REFERENCE_V3_SCHEMA,
            "fact_identity_by_stock": [list(item) for item in fact_identity_by_stock],
        }
    )


def _reference_finished_identity(
    *,
    upstream_reference: FundamentalReadSnapshotReferenceV2,
    upstream_reference_sha256: str,
    source_content_identity_sha256: str,
    result_identity_by_stock: tuple[tuple[str, str], ...],
    fact_identity_by_stock: tuple[tuple[str, str], ...],
    reader_result_status_counts: tuple[tuple[str, int], ...],
    fact_state_counts: tuple[tuple[str, int], ...],
) -> str:
    return _canonical_sha256(
        {
            "schema_version": DAILY_MARKET_MONTHLY_REVENUE_FINISHED_COHORT_V2_SCHEMA,
            "source_kind": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND,
            "source_scope": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE,
            "availability_status": DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "upstream_reference_identity_sha256": upstream_reference.identity_sha256,
            "upstream_reference_sha256": upstream_reference_sha256,
            "source_content_identity_sha256": source_content_identity_sha256,
            "result_identity_by_stock": [
                list(item) for item in result_identity_by_stock
            ],
            "fact_identity_by_stock": [list(item) for item in fact_identity_by_stock],
            "reader_result_status_counts": [
                list(item) for item in reader_result_status_counts
            ],
            "fact_state_counts": [list(item) for item in fact_state_counts],
        }
    )


def _validate_identity_ledger(
    value: object,
    *,
    field_name: str,
    declared_codes: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v3_{field_name}_coverage_invalid"
        )
    entries = cast(tuple[object, ...], value)
    if any(type(item) is not tuple or len(item) != 2 for item in entries):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v3_{field_name}_coverage_invalid"
        )
    if tuple(cast(tuple[object, ...], item)[0] for item in entries) != declared_codes:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v3_{field_name}_coverage_invalid"
        )
    typed: list[tuple[str, str]] = []
    for item in entries:
        if type(item) is not tuple or len(item) != 2:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                f"monthly_revenue_v3_{field_name}_entry_invalid"
            )
        pair = cast(tuple[object, ...], item)
        if type(pair[0]) is not str or type(pair[1]) is not str:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                f"monthly_revenue_v3_{field_name}_entry_type_invalid"
            )
        _require_sha256(pair[1], field_name)
        typed.append((cast(str, pair[0]), cast(str, pair[1])))
    return tuple(typed)


def _validate_status_counts(
    value: object,
    *,
    field_name: str,
    allowed: frozenset[str],
    expected_total: int,
    exact_order: tuple[str, ...] | None = None,
) -> tuple[tuple[str, int], ...]:
    if type(value) is not tuple or not value:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v3_{field_name}_invalid"
        )
    entries = cast(tuple[object, ...], value)
    typed: list[tuple[str, int]] = []
    for item in entries:
        if type(item) is not tuple or len(item) != 2:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                f"monthly_revenue_v3_{field_name}_entry_invalid"
            )
        pair = cast(tuple[object, ...], item)
        if (
            type(pair[0]) is not str
            or pair[0] not in allowed
            or type(pair[1]) is not int
            or pair[1] < 0
        ):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                f"monthly_revenue_v3_{field_name}_entry_invalid"
            )
        typed.append((cast(str, pair[0]), cast(int, pair[1])))
    keys = tuple(item[0] for item in typed)
    if keys != (exact_order if exact_order is not None else tuple(sorted(set(keys)))):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v3_{field_name}_order_invalid"
        )
    if len(set(keys)) != len(keys) or sum(item[1] for item in typed) != expected_total:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v3_{field_name}_denominator_invalid"
        )
    if exact_order is None and any(item[1] == 0 for item in typed):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v3_{field_name}_zero_count_not_canonical"
        )
    return tuple(typed)


@dataclass(frozen=True, slots=True)
class DailyMarketMonthlyRevenueSourceReferenceV3:
    """V3 月營收參照；解碼後仍是未驗證資料，不是來源授權。"""

    upstream_reference: FundamentalReadSnapshotReferenceV2
    upstream_reference_sha256: str
    decision_cutoff: str
    declared_stock_codes: tuple[str, ...]
    declared_stock_codes_sha256: str
    result_identity_by_stock: tuple[tuple[str, str], ...]
    fact_identity_by_stock: tuple[tuple[str, str], ...]
    fact_ledger_identity_sha256: str
    reader_result_status_counts: tuple[tuple[str, int], ...]
    fact_state_counts: tuple[tuple[str, int], ...]
    source_content_identity_sha256: str
    finished_cohort_identity_sha256: str
    cohort_pin: DailyMonthlyRevenueCohortPin
    identity_sha256: str = field(init=False)
    schema_version: Literal[
        "daily-market-monthly-revenue-source-reference.v3"
    ] = "daily-market-monthly-revenue-source-reference.v3"
    source_kind: Literal["daily_monthly_revenue_cohort"] = "daily_monthly_revenue_cohort"
    source_scope: Literal["current_observed_only"] = "current_observed_only"
    availability_status: Literal["cohort_hour_bound"] = "cohort_hour_bound"
    historical_pit_eligible: Literal[False] = False
    formal_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if type(self.upstream_reference) is not FundamentalReadSnapshotReferenceV2:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_upstream_reference_type_invalid"
            )
        if type(self.cohort_pin) is not DailyMonthlyRevenueCohortPin:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_cohort_pin_type_invalid"
            )
        if self.schema_version != DAILY_MARKET_MONTHLY_REVENUE_SOURCE_REFERENCE_V3_SCHEMA:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_schema_unsupported"
            )
        if self.source_kind != DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_source_kind_invalid"
            )
        if self.source_scope != DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_source_scope_invalid"
            )
        if self.availability_status != DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_availability_status_invalid"
            )
        if self.historical_pit_eligible is not False or self.formal_pit_eligible is not False:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_pit_must_remain_false"
            )
        upstream_sha = _require_sha256(
            self.upstream_reference_sha256, "upstream_reference"
        )
        if sha256(encode_snapshot_reference_v2(self.upstream_reference)).hexdigest() != upstream_sha:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_upstream_reference_sha_mismatch"
            )
        _require_sha256(self.source_content_identity_sha256, "source_content_identity")
        _require_sha256(self.finished_cohort_identity_sha256, "finished_cohort_identity")
        cutoff = _require_text(self.decision_cutoff, "decision_cutoff", max_length=64)
        try:
            parsed_cutoff = datetime.fromisoformat(cutoff)
        except ValueError as exc:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_decision_cutoff_invalid"
            ) from exc
        if (
            parsed_cutoff.tzinfo is None
            or parsed_cutoff.utcoffset() is None
            or parsed_cutoff.isoformat() != cutoff
            or cutoff != self.upstream_reference.decision_cutoff
        ):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_decision_cutoff_mismatch"
            )
        cohort_available_hour = _require_aware(
            self.cohort_pin.available_hour,
            "v3_cohort_available_hour",
        )
        if cohort_available_hour.astimezone(timezone.utc) > parsed_cutoff.astimezone(
            timezone.utc
        ):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_cohort_hour_after_cutoff"
            )
        codes = self.declared_stock_codes
        if (
            type(codes) is not tuple
            or not codes
            or len(codes) > _MAX_DECLARED_CODES
            or codes != tuple(sorted(set(codes)))
            or any(type(code) is not str or not _STOCK_CODE_RE.fullmatch(code) for code in codes)
            or codes != self.upstream_reference.declared_stock_codes
        ):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_declared_codes_invalid"
            )
        if self.declared_stock_codes_sha256 != _canonical_sha256(list(codes)):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_declared_codes_sha_mismatch"
            )
        result_ledger = _validate_identity_ledger(
            self.result_identity_by_stock,
            field_name="result_identity_by_stock",
            declared_codes=codes,
        )
        fact_ledger = _validate_identity_ledger(
            self.fact_identity_by_stock,
            field_name="fact_identity_by_stock",
            declared_codes=codes,
        )
        _require_sha256(self.fact_ledger_identity_sha256, "fact_ledger_identity")
        if self.fact_ledger_identity_sha256 != _fact_ledger_identity_sha256(fact_ledger):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_fact_ledger_identity_mismatch"
            )
        status_counts = _validate_status_counts(
            self.reader_result_status_counts,
            field_name="reader_result_status_counts",
            allowed=_RESULT_STATUSES,
            expected_total=len(codes),
        )
        state_counts = _validate_status_counts(
            self.fact_state_counts,
            field_name="fact_state_counts",
            allowed=frozenset(_FACT_STATES),
            expected_total=len(codes),
            exact_order=_FACT_STATES,
        )
        if self.cohort_pin.cohort_sha256 != self.upstream_reference.daily_cohort_sha256:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_upstream_cohort_pin_mismatch"
            )
        source_clock_content_identity = self.upstream_reference.source_content_identity_sha256
        recomputed_content_identity = _canonical_sha256(
            {
                "schema_version": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_REFERENCE_V3_SCHEMA,
                "source_kind": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND,
                "source_scope": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE,
                "availability_status": DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY,
                "historical_pit_eligible": False,
                "formal_pit_eligible": False,
                "decision_cutoff": cutoff,
                "upstream_source_content_identity_sha256": source_clock_content_identity,
                "daily_cohort_pin": self.cohort_pin.to_dict(),
                "declared_stock_codes": list(codes),
                "result_identity_by_stock": [list(item) for item in result_ledger],
                "fact_identity_by_stock": [list(item) for item in fact_ledger],
                "reader_result_status_counts": [list(item) for item in status_counts],
                "fact_state_counts": [list(item) for item in state_counts],
            }
        )
        if self.source_content_identity_sha256 != recomputed_content_identity:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_source_content_identity_mismatch"
            )
        expected_finished = _reference_finished_identity(
            upstream_reference=self.upstream_reference,
            upstream_reference_sha256=upstream_sha,
            source_content_identity_sha256=self.source_content_identity_sha256,
            result_identity_by_stock=result_ledger,
            fact_identity_by_stock=fact_ledger,
            reader_result_status_counts=status_counts,
            fact_state_counts=state_counts,
        )
        if self.finished_cohort_identity_sha256 != expected_finished:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_finished_identity_mismatch"
            )
        object.__setattr__(self, "identity_sha256", _canonical_sha256(self._identity_payload()))

    @classmethod
    def from_finished(
        cls,
        finished: FinishedDailyMarketMonthlyRevenueCohortV2,
        *,
        upstream_reference: FundamentalReadSnapshotReferenceV2,
    ) -> DailyMarketMonthlyRevenueSourceReferenceV3:
        if type(finished) is not FinishedDailyMarketMonthlyRevenueCohortV2:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_finished_cohort_type_invalid"
            )
        finished._validate_issued_contents()
        if upstream_reference != finished.upstream_reference:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_upstream_reference_does_not_match_finished"
            )
        upstream_raw = encode_snapshot_reference_v2(upstream_reference)
        return cls(
            upstream_reference=upstream_reference,
            upstream_reference_sha256=sha256(upstream_raw).hexdigest(),
            decision_cutoff=_datetime_text(finished.decision_cutoff),
            declared_stock_codes=finished.declared_stock_codes,
            declared_stock_codes_sha256=_canonical_sha256(
                list(finished.declared_stock_codes)
            ),
            result_identity_by_stock=finished.result_identity_by_stock,
            fact_identity_by_stock=finished.fact_identity_by_stock,
            fact_ledger_identity_sha256=_fact_ledger_identity_sha256(
                finished.fact_identity_by_stock
            ),
            reader_result_status_counts=finished.reader_result_status_counts,
            fact_state_counts=finished.fact_state_counts,
            source_content_identity_sha256=finished.source_content_identity_sha256,
            finished_cohort_identity_sha256=(
                _reference_finished_identity(
                    upstream_reference=upstream_reference,
                    upstream_reference_sha256=sha256(upstream_raw).hexdigest(),
                    source_content_identity_sha256=finished.source_content_identity_sha256,
                    result_identity_by_stock=finished.result_identity_by_stock,
                    fact_identity_by_stock=finished.fact_identity_by_stock,
                    reader_result_status_counts=finished.reader_result_status_counts,
                    fact_state_counts=finished.fact_state_counts,
                )
            ),
            cohort_pin=finished.cohort_pin,
        )

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_kind": self.source_kind,
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "upstream_reference": self.upstream_reference.to_dict(),
            "upstream_reference_sha256": self.upstream_reference_sha256,
            "decision_cutoff": self.decision_cutoff,
            "declared_stock_codes": list(self.declared_stock_codes),
            "declared_stock_codes_sha256": self.declared_stock_codes_sha256,
            "result_identity_by_stock": [list(item) for item in self.result_identity_by_stock],
            "fact_identity_by_stock": [list(item) for item in self.fact_identity_by_stock],
            "fact_ledger_identity_sha256": self.fact_ledger_identity_sha256,
            "reader_result_status_counts": [
                list(item) for item in self.reader_result_status_counts
            ],
            "fact_state_counts": [list(item) for item in self.fact_state_counts],
            "source_content_identity_sha256": self.source_content_identity_sha256,
            "finished_cohort_identity_sha256": self.finished_cohort_identity_sha256,
            "cohort_pin": self.cohort_pin.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._identity_payload()
        payload["identity_sha256"] = self.identity_sha256
        return payload

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > _MAX_REFERENCE_BYTES:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_reference_exceeds_size_limit"
            )
        return raw.decode("utf-8")

    @property
    def external_reference_sha256(self) -> str:
        return sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def _from_dict(
        cls,
        payload: object,
        *,
        expected_reference_sha256: str,
    ) -> DailyMarketMonthlyRevenueSourceReferenceV3:
        if type(payload) is not dict:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_reference_object_required"
            )
        expected_keys = {
            "schema_version",
            "source_kind",
            "source_scope",
            "availability_status",
            "historical_pit_eligible",
            "formal_pit_eligible",
            "upstream_reference",
            "upstream_reference_sha256",
            "decision_cutoff",
            "declared_stock_codes",
            "declared_stock_codes_sha256",
            "result_identity_by_stock",
            "fact_identity_by_stock",
            "fact_ledger_identity_sha256",
            "reader_result_status_counts",
            "fact_state_counts",
            "source_content_identity_sha256",
            "finished_cohort_identity_sha256",
            "cohort_pin",
            "identity_sha256",
        }
        if set(payload) != expected_keys:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_reference_fields_invalid"
            )
        string_keys = {
            "schema_version",
            "source_kind",
            "source_scope",
            "availability_status",
            "upstream_reference_sha256",
            "decision_cutoff",
            "declared_stock_codes_sha256",
            "fact_ledger_identity_sha256",
            "source_content_identity_sha256",
            "finished_cohort_identity_sha256",
            "identity_sha256",
        }
        if any(type(payload[key]) is not str for key in string_keys):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_reference_string_type_invalid"
            )
        if (
            type(payload["historical_pit_eligible"]) is not bool
            or type(payload["formal_pit_eligible"]) is not bool
        ):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_reference_pit_type_invalid"
            )
        codes_raw = payload["declared_stock_codes"]
        if (
            type(codes_raw) is not list
            or not codes_raw
            or len(codes_raw) > _MAX_DECLARED_CODES
            or any(type(code) is not str or len(code) > 6 for code in codes_raw)
        ):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_reference_codes_invalid"
            )
        result_ledger = _parse_ledger(payload["result_identity_by_stock"], "result_identity_by_stock")
        fact_ledger = _parse_ledger(payload["fact_identity_by_stock"], "fact_identity_by_stock")
        status_counts = _parse_counts(payload["reader_result_status_counts"], "reader_result_status_counts")
        state_counts = _parse_counts(payload["fact_state_counts"], "fact_state_counts")
        upstream_raw = _canonical_json_bytes(payload["upstream_reference"])
        upstream_sha = payload["upstream_reference_sha256"]
        upstream_reference = decode_snapshot_reference_v2(
            upstream_raw,
            expected_reference_sha256=upstream_sha,
        )
        cohort_pin = DailyMonthlyRevenueCohortPin.from_dict(payload["cohort_pin"])
        reference = cls(
            upstream_reference=upstream_reference,
            upstream_reference_sha256=upstream_sha,
            decision_cutoff=payload["decision_cutoff"],
            declared_stock_codes=tuple(codes_raw),
            declared_stock_codes_sha256=payload["declared_stock_codes_sha256"],
            result_identity_by_stock=result_ledger,
            fact_identity_by_stock=fact_ledger,
            fact_ledger_identity_sha256=payload["fact_ledger_identity_sha256"],
            reader_result_status_counts=status_counts,
            fact_state_counts=state_counts,
            source_content_identity_sha256=payload["source_content_identity_sha256"],
            finished_cohort_identity_sha256=payload["finished_cohort_identity_sha256"],
            cohort_pin=cohort_pin,
            schema_version=payload["schema_version"],
            source_kind=payload["source_kind"],
            source_scope=payload["source_scope"],
            availability_status=payload["availability_status"],
            historical_pit_eligible=cast(Literal[False], payload["historical_pit_eligible"]),
            formal_pit_eligible=cast(Literal[False], payload["formal_pit_eligible"]),
        )
        if reference.identity_sha256 != payload["identity_sha256"]:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_reference_identity_mismatch"
            )
        if sha256(_canonical_json_bytes(payload)).hexdigest() != expected_reference_sha256:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_external_reference_sha_mismatch"
            )
        return reference


def _parse_ledger(value: object, field_name: str) -> tuple[tuple[str, str], ...]:
    if type(value) is not list or len(value) > _MAX_DECLARED_CODES:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v3_{field_name}_invalid"
        )
    result: list[tuple[str, str]] = []
    for item in value:
        if (
            type(item) is not list
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not str
        ):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                f"monthly_revenue_v3_{field_name}_entry_invalid"
            )
        result.append((item[0], item[1]))
    return tuple(result)


def _parse_counts(value: object, field_name: str) -> tuple[tuple[str, int], ...]:
    if type(value) is not list or len(value) > 8:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            f"monthly_revenue_v3_{field_name}_invalid"
        )
    result: list[tuple[str, int]] = []
    for item in value:
        if (
            type(item) is not list
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
        ):
            raise DailyMarketMonthlyRevenueCohortV2Error(
                f"monthly_revenue_v3_{field_name}_entry_invalid"
            )
        result.append((item[0], item[1]))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3:
    """外部 hash 綁定的 parse 結果；呼叫端仍須 exact-reopen 上游來源。"""

    reference: DailyMarketMonthlyRevenueSourceReferenceV3
    external_reference_sha256: str

    def __post_init__(self) -> None:
        if type(self.reference) is not DailyMarketMonthlyRevenueSourceReferenceV3:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_unverified_wrapper_reference_type_invalid"
            )
        _require_sha256(self.external_reference_sha256, "external_reference")
        if self.external_reference_sha256 != self.reference.external_reference_sha256:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_unverified_wrapper_sha_mismatch"
            )


def decode_daily_market_monthly_revenue_source_reference_v3(
    raw: str | bytes,
    *,
    expected_reference_sha256: str,
) -> UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3:
    """以 caller 提供的外部 SHA 解碼；不宣告來源或 fact 已重新驗證。"""

    expected_sha = _require_sha256(expected_reference_sha256, "external_reference")
    if type(raw) is bytes:
        encoded = raw
    elif type(raw) is str:
        try:
            encoded = raw.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise DailyMarketMonthlyRevenueCohortV2Error(
                "monthly_revenue_v3_reference_not_utf8"
            ) from exc
    else:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v3_reference_json_type_invalid"
        )
    if len(encoded) > _MAX_REFERENCE_BYTES:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v3_reference_exceeds_size_limit"
        )
    actual_sha = sha256(encoded).hexdigest()
    if actual_sha != expected_sha:
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v3_external_reference_sha_mismatch"
        )
    _validate_json_depth(encoded)
    try:
        payload = json.loads(
            encoded.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        DailyMarketMonthlyRevenueCohortV2Error,
        RecursionError,
    ) as exc:
        if isinstance(exc, DailyMarketMonthlyRevenueCohortV2Error):
            raise
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v3_reference_json_invalid"
        ) from exc
    reference = DailyMarketMonthlyRevenueSourceReferenceV3._from_dict(
        payload,
        expected_reference_sha256=expected_sha,
    )
    if encoded != reference.to_json().encode("utf-8"):
        raise DailyMarketMonthlyRevenueCohortV2Error(
            "monthly_revenue_v3_reference_not_canonical"
        )
    return UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3(
        reference=reference,
        external_reference_sha256=expected_sha,
    )


__all__ = [
    "DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY",
    "DAILY_MARKET_MONTHLY_REVENUE_FACT_V2_SCHEMA",
    "DAILY_MARKET_MONTHLY_REVENUE_FINISHED_COHORT_V2_SCHEMA",
    "DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND",
    "DAILY_MARKET_MONTHLY_REVENUE_SOURCE_REFERENCE_V3_SCHEMA",
    "DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE",
    "DailyMarketMonthlyRevenueCohortV2Error",
    "DailyMarketMonthlyRevenueFactV2",
    "DailyMarketMonthlyRevenueSourceReferenceV3",
    "FinishedDailyMarketMonthlyRevenueCohortV2",
    "UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3",
    "_issue_finished_daily_market_monthly_revenue_cohort_v2",
    "decode_daily_market_monthly_revenue_source_reference_v3",
]
