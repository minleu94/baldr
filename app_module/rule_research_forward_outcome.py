"""以固定研究母體和明示價格投影 H5/H10/H20 收盤到收盤結果。

本模組只接受 caller 傳入的 immutable capture/receipt package、交易日曆、
價格點、benchmark 與成本政策；不讀檔、不查資料庫、不取網、不執行策略。
結果是 endpoint-only research outcome，不代表可成交、PIT、正式或訓練資格。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

from app_module.outcome_maturity_service import OutcomeMaturityService
from app_module.rule_research_parent_capture import (
    PARENT_RECEIPT_SCHEMA,
    RuleResearchParentCapture,
    _child_spec,
    _parent_identity,
)
from app_module.rule_research_sample_capture import (
    CAPTURE_SCHEMA,
    RECEIPT_SCHEMA,
    RuleResearchCapture,
    _identity as _capture_identity,
)


FORWARD_OUTCOME_SCHEMA = "rule-research-forward-outcomes.v1"
LABEL_SCHEMA = "research_return_sign.v1"
HORIZONS: tuple[int, ...] = (5, 10, 20)
MAX_POPULATION = 512
MAX_POINTS_PER_INSTRUMENT = 21
MAX_CALENDAR_DATES = 260
MAX_TEXT_LENGTH = 512
MAX_DECIMAL_DIGITS = 64
MAX_DECIMAL_EXPONENT = 64
SUPPORTED_COST_FORMULA = "proportional_entry_add_exit_deduct.v1"
_RESEARCH_POLICY = {
    "historical_pit_eligible": False,
    "formal_eligible": False,
    "training_eligible": False,
    "natural_authority": False,
    "execution_eligible": False,
}
_CAPTURE_STATES = {"matched", "notmatched", "unknown", "excluded"}
_PRICE_STATES = {"available", "missing", "suspended", "unknown"}


class ForwardOutcomeError(ValueError):
    """穩定的研究輸入拒絕理由。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ForwardOutcomeError(code)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _text(value: object, field: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    _require(isinstance(value, str) and bool(value.strip()), f"{field}_invalid")
    assert isinstance(value, str)
    _require(len(value) <= MAX_TEXT_LENGTH, f"{field}_too_long")
    return value.strip()


def _iso_date(value: object, field: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    _require(isinstance(value, str), f"{field}_invalid")
    assert isinstance(value, str)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ForwardOutcomeError(f"{field}_invalid") from error
    _require(parsed.isoformat() == value, f"{field}_invalid")
    return value


def _required_iso_date(value: object, field: str) -> str:
    result = _iso_date(value, field)
    assert result is not None
    return result


def _decimal_text(value: Decimal) -> str:
    """回傳不受 Decimal context 影響的 plain canonical 數字字串。"""
    sign, digits_tuple, exponent = value.as_tuple()
    assert isinstance(exponent, int)
    digits = "".join(str(digit) for digit in digits_tuple) or "0"
    if all(digit == "0" for digit in digits):
        return "0"
    while len(digits) > 1 and digits.endswith("0"):
        digits = digits[:-1]
        exponent += 1
    if exponent >= 0:
        body = digits + ("0" * exponent)
    else:
        point = len(digits) + exponent
        if point > 0:
            body = digits[:point] + "." + digits[point:]
        else:
            body = "0." + ("0" * -point) + digits
    return ("-" if sign else "") + body


def _check_price(value: object) -> Decimal:
    _require(isinstance(value, Decimal), "price_must_be_decimal")
    assert isinstance(value, Decimal)
    _require(value.is_finite() and value > 0, "price_must_be_positive_finite")
    sign, digits, exponent = value.as_tuple()
    del sign
    assert isinstance(exponent, int)
    _require(len(digits) <= MAX_DECIMAL_DIGITS, "price_decimal_precision_bound")
    _require(abs(exponent) <= MAX_DECIMAL_EXPONENT, "price_decimal_exponent_bound")
    return value


@dataclass(frozen=True, slots=True)
class Calendar:
    """caller 明示的研究日曆；complete 僅是 caller 的完整性宣告。"""

    trading_dates: tuple[str, ...]
    known: bool
    complete: bool
    coverage_start: str | None
    coverage_end: str | None
    source_identity: str | None
    available_date: str | None

    def __post_init__(self) -> None:
        _require(type(self.known) is bool and type(self.complete) is bool, "calendar_flags_invalid")
        _require(isinstance(self.trading_dates, tuple), "calendar_dates_must_be_tuple")
        _require(len(self.trading_dates) <= MAX_CALENDAR_DATES, "calendar_date_bound")
        dates = tuple(_required_iso_date(item, "calendar_date") for item in self.trading_dates)
        _require(dates == tuple(sorted(set(dates))), "calendar_dates_not_canonical")
        _iso_date(self.available_date, "calendar_available_date", optional=True)
        if not self.known:
            _require(
                not self.complete
                and not dates
                and self.coverage_start is None
                and self.coverage_end is None
                and self.source_identity is None,
                "unknown_calendar_must_not_claim_coverage",
            )
            return
        _require(isinstance(self.complete, bool), "calendar_completeness_invalid")
        start = _iso_date(self.coverage_start, "calendar_coverage_start")
        end = _iso_date(self.coverage_end, "calendar_coverage_end")
        assert start is not None and end is not None
        _require(start <= end, "calendar_coverage_range_invalid")
        _text(self.source_identity, "calendar_source_identity")
        _require(all(start <= item <= end for item in dates), "calendar_date_outside_coverage")
        _require(bool(dates), "known_calendar_dates_missing")

    @property
    def content_identity_sha256(self) -> str:
        return _sha256(_canonical_json(self.to_payload()).encode("utf-8"))

    def to_payload(self) -> dict[str, Any]:
        return {
            "trading_dates": list(self.trading_dates),
            "known": self.known,
            "complete": self.complete,
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
            "source_identity": self.source_identity,
            "available_date": self.available_date,
        }


@dataclass(frozen=True, slots=True)
class PricePoint:
    """單一 instrument/date 的明示日收盤價或缺件狀態。"""

    instrument_id: str
    trade_date: str
    state: str
    price: Decimal | None
    source_identity: str
    currency: str
    unit: str
    price_basis: str
    corporate_action_basis: str
    available_date: str | None
    content_identity_sha256: str | None = None

    def __post_init__(self) -> None:
        _text(self.instrument_id, "instrument_id")
        _iso_date(self.trade_date, "trade_date")
        _require(self.state in _PRICE_STATES, "price_state_invalid")
        _text(self.source_identity, "price_source_identity")
        _text(self.currency, "price_currency")
        _text(self.unit, "price_unit")
        _text(self.price_basis, "price_basis")
        _text(self.corporate_action_basis, "corporate_action_basis")
        available = _iso_date(self.available_date, "price_available_date", optional=True)
        if available is not None:
            _require(available >= self.trade_date, "price_available_before_trade_date")
        if self.state == "available":
            _check_price(self.price)
        else:
            _require(self.price is None, "unavailable_price_must_be_null")
        if self.content_identity_sha256 is not None:
            _require(
                self.content_identity_sha256 == self.computed_content_identity_sha256,
                "price_content_identity_mismatch",
            )

    @property
    def computed_content_identity_sha256(self) -> str:
        return _sha256(_canonical_json(self.content_payload()).encode("utf-8"))

    def content_payload(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "trade_date": self.trade_date,
            "state": self.state,
            "price": None if self.price is None else _decimal_text(self.price),
            "source_identity": self.source_identity,
            "currency": self.currency,
            "unit": self.unit,
            "price_basis": self.price_basis,
            "corporate_action_basis": self.corporate_action_basis,
            "available_date": self.available_date,
        }

    def to_payload(self) -> dict[str, Any]:
        return {
            **self.content_payload(),
            "content_identity_sha256": self.computed_content_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkSpec:
    """單一 benchmark 的比較基礎；價格點仍須逐日明示。"""

    instrument_id: str
    currency: str
    unit: str
    price_basis: str
    corporate_action_basis: str
    source_identity: str

    def __post_init__(self) -> None:
        _text(self.instrument_id, "benchmark_instrument_id")
        _text(self.currency, "benchmark_currency")
        _text(self.unit, "benchmark_unit")
        _text(self.price_basis, "benchmark_price_basis")
        _text(self.corporate_action_basis, "benchmark_corporate_action_basis")
        _text(self.source_identity, "benchmark_source_identity")

    def to_payload(self) -> dict[str, str]:
        return {
            "instrument_id": self.instrument_id,
            "currency": self.currency,
            "unit": self.unit,
            "price_basis": self.price_basis,
            "corporate_action_basis": self.corporate_action_basis,
            "source_identity": self.source_identity,
        }


@dataclass(frozen=True, slots=True)
class CostPolicy:
    """明示且版本化的整數 bp 成本；target/benchmark 進出成本分開。"""

    version: str
    formula_id: str
    target_entry_bp: int | None
    target_exit_bp: int | None
    benchmark_entry_bp: int | None
    benchmark_exit_bp: int | None

    def __post_init__(self) -> None:
        _text(self.version, "cost_policy_version")
        _text(self.formula_id, "cost_formula_id")
        for name in (
            "target_entry_bp",
            "target_exit_bp",
            "benchmark_entry_bp",
            "benchmark_exit_bp",
        ):
            value = getattr(self, name)
            if value is not None:
                _require(type(value) is int and 0 <= value <= 10000, f"{name}_invalid")

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "formula_id": self.formula_id,
            "target_entry_bp": self.target_entry_bp,
            "target_exit_bp": self.target_exit_bp,
            "benchmark_entry_bp": self.benchmark_entry_bp,
            "benchmark_exit_bp": self.benchmark_exit_bp,
        }


@dataclass(frozen=True, slots=True)
class ForwardOutcomeProjection:
    """不可變 canonical JSON 結果；每次 to_dict 都回傳新物件。"""

    body_json: str

    def to_dict(self) -> dict[str, Any]:
        _require(isinstance(self.body_json, str), "outcome_body_invalid")
        try:
            body = json.loads(self.body_json)
        except json.JSONDecodeError as error:
            raise ForwardOutcomeError("outcome_json_invalid") from error
        _require(isinstance(body, dict) and _canonical_json(body) == self.body_json, "outcome_json_not_canonical")
        digest = body.get("result_identity_sha256")
        stable = {key: value for key, value in body.items() if key != "result_identity_sha256"}
        _require(body.get("schema_version") == FORWARD_OUTCOME_SCHEMA, "outcome_schema_mismatch")
        _require(digest == _sha256(_canonical_json(stable).encode("utf-8")), "outcome_identity_mismatch")
        _validate_projection_semantics(body)
        return body

    @property
    def result_identity_sha256(self) -> str:
        return str(self.to_dict()["result_identity_sha256"])


def _sealed(payload: dict[str, Any]) -> ForwardOutcomeProjection:
    body = {"schema_version": FORWARD_OUTCOME_SCHEMA, **payload}
    body["result_identity_sha256"] = _sha256(_canonical_json(body).encode("utf-8"))
    result = ForwardOutcomeProjection(_canonical_json(body))
    result.to_dict()
    return result


def _validate_projection_semantics(body: dict[str, Any]) -> None:
    """雜湊只能驗證內容一致；不得把呼叫端改寫的研究結果升格為資格。"""
    for key in ("historical_pit_eligible", "formal_eligible", "training_eligible", "natural_authority", "execution_eligible"):
        _require(body.get(key) is False, "outcome_research_policy_invalid")
    _require(body.get("projection_scope") in {"single_child_capture", "parent_exact_children"}, "outcome_scope_invalid")
    population = body.get("population")
    members = body.get("members")
    _require(isinstance(population, dict) and isinstance(members, list), "outcome_population_shape_invalid")
    assert isinstance(population, dict) and isinstance(members, list)
    _require(0 < len(members) <= MAX_POPULATION * 2, "outcome_member_bound")
    represented = population.get("represented_denominator")
    _require(type(represented) is int and 1 <= represented <= MAX_POPULATION, "outcome_denominator_invalid")
    _require(population.get("population_count") == represented, "outcome_population_count_invalid")
    _require(population.get("selection_status") == "unknown" and population.get("selected_count") is None, "outcome_selection_claim_invalid")
    by_method: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    valid_states = _CAPTURE_STATES | {"uncaptured"}
    for member in members:
        _require(isinstance(member, dict), "outcome_member_shape_invalid")
        method_id = member.get("method_id")
        stock_code = member.get("stock_code")
        state = member.get("member_state")
        _require(isinstance(method_id, str) and bool(method_id), "outcome_method_invalid")
        _require(isinstance(stock_code, str) and bool(stock_code), "outcome_stock_code_invalid")
        _require(isinstance(state, str) and state in valid_states, "outcome_member_state_invalid")
        member_key = (method_id, stock_code)
        _require(member_key not in seen, "outcome_duplicate_member")
        seen.add(member_key)
        _require(member.get("selection_status") == "unknown", "outcome_member_selection_claim_invalid")
        marker = member.get("capture_selected_marker")
        _require(marker is False or marker is None, "outcome_capture_marker_invalid")
        _require(type(member.get("declared_excluded")) is bool, "outcome_exclusion_flag_invalid")
        exclusion_reason = member.get("declared_exclusion_reason")
        _require(exclusion_reason is None or isinstance(exclusion_reason, str), "outcome_exclusion_reason_invalid")
        _require(not member["declared_excluded"] or bool(exclusion_reason), "outcome_exclusion_reason_missing")
        _require(
            not member["declared_excluded"] or state in {"excluded", "uncaptured"},
            "outcome_declared_exclusion_state_invalid",
        )
        horizons = member.get("horizons")
        _require(isinstance(horizons, list) and len(horizons) == len(HORIZONS), "outcome_horizons_invalid")
        assert isinstance(horizons, list)
        for horizon, sessions in zip(horizons, HORIZONS):
            _require(isinstance(horizon, dict), "outcome_horizon_shape_invalid")
            _require(horizon.get("horizon") == f"H{sessions}" and horizon.get("sessions") == sessions, "outcome_horizon_order_invalid")
            _require(horizon.get("label_schema") == LABEL_SCHEMA, "outcome_label_schema_invalid")
            qualification = horizon.get("qualification")
            _require(isinstance(qualification, dict), "outcome_qualification_shape_invalid")
            assert isinstance(qualification, dict)
            for key in ("historical_pit_eligible", "formal_eligible", "training_eligible", "execution_eligible"):
                _require(qualification.get(key) is False, "outcome_horizon_eligibility_invalid")
            qualification_status = qualification.get("status")
            _require(
                isinstance(qualification_status, str)
                and qualification_status in {"ineligible", "unknown"},
                "outcome_qualification_status_invalid",
            )
        by_method.setdefault(method_id, []).append(member)
    _require(len(by_method) == 2, "outcome_method_count_invalid")
    _require(all(len(rows) == represented for rows in by_method.values()), "outcome_method_denominator_invalid")
    counts = population.get("method_state_counts")
    _require(isinstance(counts, dict) and set(counts) == set(by_method), "outcome_state_counts_shape_invalid")
    assert isinstance(counts, dict)
    states = ("matched", "notmatched", "unknown", "excluded", "uncaptured")
    for method_id, rows in by_method.items():
        expected = {state: sum(member["member_state"] == state for member in rows) for state in states}
        actual = counts.get(method_id)
        _require(isinstance(actual, dict) and actual == expected, "outcome_state_counts_mismatch")
        _require(sum(expected.values()) == represented, "outcome_state_denominator_invalid")
    marker_count = sum(member["capture_selected_marker"] is False for member in members)
    _require(population.get("capture_selected_marker_method_rows") == marker_count, "outcome_capture_marker_count_invalid")


def _package_body(package: object, *, kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
    _require(isinstance(package, Mapping), f"{kind}_package_invalid")
    assert isinstance(package, Mapping)
    _require(set(package.keys()) == {"capture", "receipt"}, f"{kind}_package_shape_invalid")
    capture = package.get("capture")
    receipt = package.get("receipt")
    _require(isinstance(capture, Mapping) and isinstance(receipt, Mapping), f"{kind}_package_invalid")
    assert isinstance(capture, Mapping) and isinstance(receipt, Mapping)
    body_dict = dict(capture)
    try:
        body_json = _canonical_json(body_dict)
    except (TypeError, ValueError) as error:
        raise ForwardOutcomeError(f"{kind}_capture_json_invalid") from error
    try:
        if kind == "child":
            body = RuleResearchCapture(body_json).to_dict()
            expected = {
                "schema_version": RECEIPT_SCHEMA,
                "status": "complete",
                "capture_identity_sha256": body["capture_identity_sha256"],
                "capture_sha256": _sha256(body_json.encode("utf-8")),
                "rows_count": len(body["rows"]),
                "observed_at": body["observed_at"],
                "research_only": True,
            }
        else:
            body = RuleResearchParentCapture(body_json).to_dict()
            expected = {
                "schema_version": PARENT_RECEIPT_SCHEMA,
                "status": "complete",
                "capture_identity_sha256": body["capture_identity_sha256"],
                "capture_sha256": _sha256(body_json.encode("utf-8")),
                "observed_at": body["observed_at"],
                "research_only": True,
                "cohort_status": body["status"],
                "batches_count": len(body["batches"]),
            }
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ForwardOutcomeError):
            raise
        raise ForwardOutcomeError(f"{kind}_capture_invalid") from error
    _require(dict(receipt) == expected, f"{kind}_receipt_mismatch")
    return body, dict(receipt)


def _date_args(decision_date: object, as_of_date: object) -> tuple[str, str]:
    decision = _iso_date(decision_date, "decision_date")
    as_of = _iso_date(as_of_date, "as_of_date")
    assert decision is not None and as_of is not None
    _require(as_of >= decision, "as_of_before_decision")
    return decision, as_of


def _capture_clock_date(body: Mapping[str, Any], field: str) -> str:
    value = body.get(field)
    _require(isinstance(value, str), f"capture_{field}_invalid")
    assert isinstance(value, str)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ForwardOutcomeError(f"capture_{field}_invalid") from error
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, f"capture_{field}_timezone_missing")
    return parsed.astimezone(timezone.utc).date().isoformat()


def _validate_outcome_as_of(as_of: str, *capture_bodies: Mapping[str, Any]) -> None:
    for body in capture_bodies:
        for field in ("as_of", "observed_at"):
            _require(as_of >= _capture_clock_date(body, field), "outcome_as_of_precedes_capture_clock")


def _validate_market_inputs(
    *,
    stock_codes: set[str],
    calendar: Calendar,
    prices: Sequence[PricePoint],
    benchmark: BenchmarkSpec | None,
) -> dict[tuple[str, str], PricePoint]:
    _require(isinstance(calendar, Calendar), "calendar_type_invalid")
    _require(isinstance(prices, Sequence) and not isinstance(prices, (str, bytes)), "prices_type_invalid")
    _require(benchmark is None or isinstance(benchmark, BenchmarkSpec), "benchmark_type_invalid")
    benchmark_ids = set() if benchmark is None else {benchmark.instrument_id}
    _require(not (stock_codes & benchmark_ids), "benchmark_stock_code_collision")
    max_instruments = len(stock_codes) + len(benchmark_ids)
    _require(max_instruments <= MAX_POPULATION + 1, "instrument_bound")
    _require(len(prices) <= max_instruments * MAX_POINTS_PER_INSTRUMENT, "price_point_bound")
    by_key: dict[tuple[str, str], PricePoint] = {}
    by_instrument: dict[str, list[PricePoint]] = {}
    allowed = stock_codes | benchmark_ids
    for point in prices:
        _require(isinstance(point, PricePoint), "price_point_type_invalid")
        _require(point.instrument_id in allowed, "unrequested_instrument_rejected")
        key = (point.instrument_id, point.trade_date)
        _require(key not in by_key, "duplicate_price_point")
        by_key[key] = point
        by_instrument.setdefault(point.instrument_id, []).append(point)
    for instrument, points in by_instrument.items():
        _require(len(points) <= MAX_POINTS_PER_INSTRUMENT, "instrument_price_point_bound")
        bases = {
            (point.currency, point.unit, point.price_basis, point.corporate_action_basis)
            for point in points
        }
        _require(len(bases) <= 1, "instrument_price_basis_mismatch")
        if benchmark is not None and instrument == benchmark.instrument_id:
            expected_basis = (
                benchmark.currency,
                benchmark.unit,
                benchmark.price_basis,
                benchmark.corporate_action_basis,
            )
            _require(bases <= {expected_basis}, "benchmark_point_spec_mismatch")
            _require(
                all(point.source_identity == benchmark.source_identity for point in points),
                "benchmark_point_source_mismatch",
            )
    return by_key


def _cost_complete(policy: CostPolicy | None, prefix: str) -> bool:
    if policy is None or policy.formula_id != SUPPORTED_COST_FORMULA:
        return False
    return (
        getattr(policy, f"{prefix}_entry_bp") is not None
        and getattr(policy, f"{prefix}_exit_bp") is not None
    )


def _net_return(
    entry: Decimal,
    exit: Decimal,
    entry_bp: int,
    exit_bp: int,
) -> Decimal:
    with localcontext(Context(prec=256, rounding=ROUND_HALF_EVEN)):
        basis = Decimal(10000)
        buy_cost_factor = Decimal(1) + Decimal(entry_bp) / basis
        sell_proceeds_factor = Decimal(1) - Decimal(exit_bp) / basis
        return (exit * sell_proceeds_factor) / (entry * buy_cost_factor) - Decimal(1)


def _gross_return(entry: Decimal, exit: Decimal) -> Decimal:
    with localcontext(Context(prec=256, rounding=ROUND_HALF_EVEN)):
        return exit / entry - Decimal(1)


def _return_bp(value: Decimal) -> int:
    with localcontext(Context(prec=256, rounding=ROUND_HALF_EVEN)):
        return int((value * Decimal(10000)).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def _sign(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


def _return_payload(value: Decimal | None) -> dict[str, Any]:
    return {
        "decimal": None if value is None else _decimal_text(value),
        "integer_bp_half_even": None if value is None else _return_bp(value),
    }


def _availability(
    calendar: Calendar,
    *,
    target_slots: Sequence[PricePoint | None] | None,
    benchmark_slots: Sequence[PricePoint | None] | None,
    decision: str,
    as_of: str,
) -> dict[str, Any]:
    def summarize(slots: Sequence[PricePoint | None] | None) -> dict[str, str | None] | None:
        if slots is None:
            return None
        dates = [calendar.available_date]
        dates.extend(None if point is None else point.available_date for point in slots)
        if any(item is not None and item > as_of for item in dates):
            as_of_status = "after_as_of_unusable"
        elif any(item is None for item in dates):
            as_of_status = "unknown"
        else:
            as_of_status = "known_by_as_of"
        if any(item is None for item in dates):
            decision_status = "unknown"
        elif any(item is not None and item > decision for item in dates):
            decision_status = "known_after_decision"
        else:
            decision_status = "known_by_decision"
        aggregate = max(item for item in dates if item is not None) if all(item is not None for item in dates) else None
        return {
            "as_of_status": as_of_status,
            "decision_time_status": decision_status,
            "aggregate_available_date": aggregate,
        }

    all_slots: list[PricePoint | None] = []
    if target_slots is not None:
        all_slots.extend(target_slots)
    if benchmark_slots is not None:
        all_slots.extend(benchmark_slots)
    overall = summarize(all_slots)
    assert overall is not None
    target = summarize(target_slots)
    benchmark = summarize(benchmark_slots)
    return {**overall, "target": target, "benchmark": benchmark}


def _null_measurements() -> dict[str, Any]:
    return {
        "gross_return": _return_payload(None),
        "net_return": _return_payload(None),
        "gross_sign_label": None,
        "net_sign_label": None,
        "cost_status": "unknown",
    }


def _basis_comparable(target: PricePoint, benchmark: BenchmarkSpec) -> bool | None:
    basis_values = (
        target.currency,
        target.price_basis,
        target.corporate_action_basis,
        benchmark.currency,
        benchmark.price_basis,
        benchmark.corporate_action_basis,
    )
    unknown_markers = {"unknown", "unavailable", "none", "null", "n/a"}
    if any(value.strip().casefold() in unknown_markers for value in basis_values):
        return None
    return (
        target.currency == benchmark.currency
        and target.price_basis == benchmark.price_basis
        and target.corporate_action_basis == benchmark.corporate_action_basis
    )


def _horizon_projection(
    *,
    stock_code: str,
    decision: str,
    as_of: str,
    horizon: int,
    calendar: Calendar,
    prices: Mapping[tuple[str, str], PricePoint],
    benchmark: BenchmarkSpec | None,
    cost_policy: CostPolicy | None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "horizon": f"H{horizon}",
        "sessions": horizon,
        "entry_basis": "decision_date_close_research_anchor_not_executable_entry",
        "measurement_scope": "endpoint_close_to_close_only",
        "path_metrics_available": False,
        "calendar": {
            "known": calendar.known,
            "complete": calendar.complete,
            "source_identity": calendar.source_identity,
            "content_identity_sha256": calendar.content_identity_sha256,
            "available_date": calendar.available_date,
            "coverage_start": calendar.coverage_start,
            "coverage_end": calendar.coverage_end,
        },
        "expected_end_date": None,
        "maturity_status": "unknown",
        "calculation_status": "unknown",
        "reason_codes": [],
        "input_availability": {
            "as_of_status": "unknown",
            "decision_time_status": "unknown",
            "aggregate_available_date": None,
            "target": None,
            "benchmark": None,
        },
        "target": _null_measurements(),
        "benchmark": {**_null_measurements(), "instrument_id": None if benchmark is None else benchmark.instrument_id},
        "comparison": {
            "status": "unknown",
            "gross_excess_return": _return_payload(None),
            "net_excess_return": _return_payload(None),
            "net_excess_sign_label": None,
            "basis_comparable": None,
        },
        "label_schema": LABEL_SCHEMA,
        "qualification": {
            "status": "ineligible",
            "historical_pit_eligible": False,
            "formal_eligible": False,
            "training_eligible": False,
            "execution_eligible": False,
            "reasons": ["research_only_capture", "decision_date_close_is_not_executable_entry"],
        },
    }
    reasons: list[str] = []
    if not calendar.known:
        reasons.append("calendar_unknown")
        base["calculation_status"] = "unknown"
        base["reason_codes"] = reasons
        return base
    if not calendar.complete:
        reasons.append("calendar_coverage_incomplete")
        base["calculation_status"] = "unknown"
        base["reason_codes"] = reasons
        return base
    assert calendar.coverage_start is not None and calendar.coverage_end is not None
    if not calendar.coverage_start <= decision <= calendar.coverage_end:
        reasons.append("decision_date_outside_calendar_coverage")
        base["calculation_status"] = "unknown"
        base["reason_codes"] = reasons
        return base
    if decision not in calendar.trading_dates:
        reasons.append("decision_date_not_in_explicit_calendar")
        base["calculation_status"] = "unknown"
        base["reason_codes"] = reasons
        return base
    if calendar.available_date is not None and calendar.available_date > as_of:
        reasons.append("calendar_not_available_as_of")
        base["calculation_status"] = "unknown"
        base["reason_codes"] = reasons
        base["input_availability"] = _availability(
            calendar,
            target_slots=None,
            benchmark_slots=None,
            decision=decision,
            as_of=as_of,
        )
        return base

    base["input_availability"] = _availability(
        calendar,
        target_slots=None,
        benchmark_slots=None,
        decision=decision,
        as_of=as_of,
    )

    maturity = OutcomeMaturityService().evaluate(
        event_date=decision,
        window_days=horizon,
        trading_dates=calendar.trading_dates,
        as_of_date=as_of,
    )
    if maturity.expected_trading_date is None:
        reasons.append("calendar_horizon_coverage_insufficient")
        base["calculation_status"] = "unknown"
        base["reason_codes"] = reasons
        return base
    if maturity.expected_trading_date > calendar.coverage_end:
        reasons.append("calendar_horizon_outside_complete_coverage")
        base["calculation_status"] = "unknown"
        base["reason_codes"] = reasons
        return base
    base["expected_end_date"] = maturity.expected_trading_date
    base["maturity_status"] = maturity.status
    if maturity.status != "ready":
        base["calculation_status"] = "pending"
        base["reason_codes"] = ["horizon_not_matured_as_of"]
        return base

    target_entry = prices.get((stock_code, decision))
    target_end = prices.get((stock_code, maturity.expected_trading_date))
    benchmark_entry: PricePoint | None = None
    benchmark_end: PricePoint | None = None
    if benchmark is not None:
        benchmark_entry = prices.get((benchmark.instrument_id, decision))
        benchmark_end = prices.get((benchmark.instrument_id, maturity.expected_trading_date))
    availability = _availability(
        calendar,
        target_slots=(target_entry, target_end),
        benchmark_slots=(benchmark_entry, benchmark_end) if benchmark is not None else None,
        decision=decision,
        as_of=as_of,
    )
    base["input_availability"] = availability

    target_missing = False
    target_unknown = False
    for name, point in (("entry", target_entry), ("end", target_end)):
        if point is None:
            reasons.append(f"target_{name}_price_missing")
            target_missing = True
        elif point.state in {"missing", "suspended"}:
            reasons.append(f"target_{name}_price_{point.state}")
            target_missing = True
        elif point.state == "unknown":
            reasons.append(f"target_{name}_price_unknown")
            target_unknown = True
        elif point.available_date is not None and point.available_date > as_of:
            reasons.append(f"target_{name}_price_not_available_as_of")
            target_unknown = True
    if target_missing or target_unknown:
        base["calculation_status"] = "unknown" if target_unknown else "unavailable"
        base["reason_codes"] = reasons
        return base
    assert target_entry is not None and target_end is not None
    assert target_entry.price is not None and target_end.price is not None
    target_gross = _gross_return(target_entry.price, target_end.price)
    target_net: Decimal | None = None
    target_cost_status = "unknown"
    if cost_policy is not None:
        if cost_policy.formula_id != SUPPORTED_COST_FORMULA:
            target_cost_status = "unsupported_formula"
        elif _cost_complete(cost_policy, "target"):
            assert cost_policy.target_entry_bp is not None and cost_policy.target_exit_bp is not None
            target_net = _net_return(
                target_entry.price,
                target_end.price,
                cost_policy.target_entry_bp,
                cost_policy.target_exit_bp,
            )
            target_cost_status = "explicit"
        else:
            target_cost_status = "incomplete"
    base["target"] = {
        "gross_return": _return_payload(target_gross),
        "net_return": _return_payload(target_net),
        "gross_sign_label": _sign(target_gross),
        "net_sign_label": _sign(target_net),
        "cost_status": target_cost_status,
        "entry_price_date": decision,
        "end_price_date": maturity.expected_trading_date,
        "entry_price_identity": target_entry.computed_content_identity_sha256,
        "end_price_identity": target_end.computed_content_identity_sha256,
    }

    bench_gross: Decimal | None = None
    bench_net: Decimal | None = None
    bench_status = "unavailable"
    bench_cost_status = "unknown"
    if benchmark is None:
        reasons.append("benchmark_not_provided")
    else:
        benchmark_missing = False
        benchmark_unknown = False
        for name, point in (("entry", benchmark_entry), ("end", benchmark_end)):
            if point is None:
                reasons.append(f"benchmark_{name}_price_missing")
                benchmark_missing = True
            elif point.state in {"missing", "suspended"}:
                reasons.append(f"benchmark_{name}_price_{point.state}")
                benchmark_missing = True
            elif point.state == "unknown":
                reasons.append(f"benchmark_{name}_price_unknown")
                benchmark_unknown = True
            elif point.available_date is not None and point.available_date > as_of:
                reasons.append(f"benchmark_{name}_price_not_available_as_of")
                benchmark_unknown = True
        if benchmark_unknown:
            bench_status = "unknown"
        elif benchmark_missing:
            bench_status = "unavailable"
        else:
            assert benchmark_entry is not None and benchmark_end is not None
            assert benchmark_entry.price is not None and benchmark_end.price is not None
            bench_gross = _gross_return(benchmark_entry.price, benchmark_end.price)
            if cost_policy is not None:
                if cost_policy.formula_id != SUPPORTED_COST_FORMULA:
                    bench_cost_status = "unsupported_formula"
                elif _cost_complete(cost_policy, "benchmark"):
                    assert cost_policy.benchmark_entry_bp is not None and cost_policy.benchmark_exit_bp is not None
                    bench_net = _net_return(
                        benchmark_entry.price,
                        benchmark_end.price,
                        cost_policy.benchmark_entry_bp,
                        cost_policy.benchmark_exit_bp,
                    )
                    bench_cost_status = "explicit"
                else:
                    bench_cost_status = "incomplete"
            bench_status = "ready_research"
            base["benchmark"] = {
                "gross_return": _return_payload(bench_gross),
                "net_return": _return_payload(bench_net),
                "gross_sign_label": _sign(bench_gross),
                "net_sign_label": _sign(bench_net),
                "cost_status": bench_cost_status,
                "instrument_id": benchmark.instrument_id,
                "entry_price_date": decision,
                "end_price_date": maturity.expected_trading_date,
                "entry_price_identity": benchmark_entry.computed_content_identity_sha256,
                "end_price_identity": benchmark_end.computed_content_identity_sha256,
            }

    comparable: bool | None = False
    comparison_status = "unavailable"
    gross_excess: Decimal | None = None
    net_excess: Decimal | None = None
    if benchmark is not None and bench_status == "ready_research":
        assert benchmark_entry is not None and benchmark_end is not None
        assert target_entry is not None
        comparable = _basis_comparable(target_entry, benchmark)
        if comparable is None:
            comparison_status = "basis_unknown"
            reasons.append("benchmark_comparison_basis_unknown")
        elif not comparable:
            comparison_status = "incompatible_basis"
            reasons.append("benchmark_currency_or_price_basis_incompatible")
        else:
            assert target_gross is not None and bench_gross is not None
            with localcontext(Context(prec=256, rounding=ROUND_HALF_EVEN)):
                gross_excess = target_gross - bench_gross
                if target_net is not None and bench_net is not None:
                    net_excess = target_net - bench_net
                    comparison_status = "ready_gross_and_net"
                else:
                    comparison_status = "ready_gross_net_cost_unknown"
    elif benchmark is not None and bench_status == "unknown":
        comparison_status = "unknown"
    base["comparison"] = {
        "status": comparison_status,
        "gross_excess_return": _return_payload(gross_excess),
        "net_excess_return": _return_payload(net_excess),
        "net_excess_sign_label": _sign(net_excess),
        "basis_comparable": comparable if benchmark is not None and bench_status == "ready_research" else None,
        "basis": "target_net_minus_benchmark_net" if net_excess is not None else None,
    }
    base["calculation_status"] = "ready_research"
    base["reason_codes"] = reasons
    return base


def _member_projection(
    *,
    method_id: str,
    stock_code: str,
    member_state: str,
    reason: str,
    captured: bool,
    declared_excluded: bool = False,
    declared_exclusion_reason: str | None = None,
    decision: str,
    as_of: str,
    calendar: Calendar,
    prices: Mapping[tuple[str, str], PricePoint],
    benchmark: BenchmarkSpec | None,
    cost_policy: CostPolicy | None,
) -> dict[str, Any]:
    horizons: list[dict[str, Any]] = []
    if not captured:
        horizons = [
            {
                "horizon": f"H{horizon}",
                "sessions": horizon,
                "calculation_status": "uncaptured",
                "maturity_status": "unknown",
                "expected_end_date": None,
                "reason_codes": ["parent_batch_not_captured"],
                "target": _null_measurements(),
                "benchmark": {**_null_measurements(), "instrument_id": None if benchmark is None else benchmark.instrument_id},
                "comparison": {
                    "status": "unknown",
                    "gross_excess_return": _return_payload(None),
                    "net_excess_return": _return_payload(None),
                    "net_excess_sign_label": None,
                    "basis_comparable": None,
                },
                "label_schema": LABEL_SCHEMA,
                "qualification": {
                    **_RESEARCH_POLICY,
                    "status": "unknown",
                    "reasons": ["uncaptured_parent_member"],
                },
            }
            for horizon in HORIZONS
        ]
    elif member_state == "excluded":
        horizons = [
            {
                "horizon": f"H{horizon}",
                "sessions": horizon,
                "calculation_status": "excluded",
                "maturity_status": "unknown",
                "expected_end_date": None,
                "reason_codes": ["member_excluded_by_declared_cohort"],
                "target": _null_measurements(),
                "benchmark": {**_null_measurements(), "instrument_id": None if benchmark is None else benchmark.instrument_id},
                "comparison": {
                    "status": "unavailable",
                    "gross_excess_return": _return_payload(None),
                    "net_excess_return": _return_payload(None),
                    "net_excess_sign_label": None,
                    "basis_comparable": None,
                },
                "label_schema": LABEL_SCHEMA,
                "qualification": {
                    **_RESEARCH_POLICY,
                    "status": "ineligible",
                    "reasons": ["excluded_member"],
                },
            }
            for horizon in HORIZONS
        ]
    else:
        horizons = [
            _horizon_projection(
                stock_code=stock_code,
                decision=decision,
                as_of=as_of,
                horizon=horizon,
                calendar=calendar,
                prices=prices,
                benchmark=benchmark,
                cost_policy=cost_policy,
            )
            for horizon in HORIZONS
        ]
    return {
        "method_id": method_id,
        "stock_code": stock_code,
        "member_state": member_state,
        "member_reason": reason,
        "declared_excluded": declared_excluded,
        "declared_exclusion_reason": declared_exclusion_reason,
        "capture_status": "captured" if captured else "uncaptured",
        "capture_selected_marker": False if captured else None,
        "selection_status": "unknown",
        "horizons": horizons,
    }


def _population_summary(members: Sequence[dict[str, Any]], *, included: int | None, represented: int) -> dict[str, Any]:
    methods = sorted({member["method_id"] for member in members})
    by_method: dict[str, dict[str, int]] = {}
    states = ("matched", "notmatched", "unknown", "excluded", "uncaptured")
    for method in methods:
        rows = [member for member in members if member["method_id"] == method]
        by_method[method] = {state: sum(member["member_state"] == state for member in rows) for state in states}
        _require(sum(by_method[method].values()) == represented, "output_population_denominator_mismatch")
    return {
        "population_count": represented,
        "included_denominator": included,
        "represented_denominator": represented,
        "method_state_counts": by_method,
        "selection_status": "unknown",
        "selected_count": None,
        "capture_selected_marker_method_rows": sum(member["capture_selected_marker"] is False for member in members),
    }


def build_rule_research_forward_outcome(
    capture: Mapping[str, Any],
    *,
    decision_date: str,
    calendar: Calendar,
    prices: Sequence[PricePoint],
    benchmark: BenchmarkSpec | None,
    cost_policy: CostPolicy | None,
    as_of_date: str,
) -> ForwardOutcomeProjection:
    """投影一個 UX20 child read package 的全部 method/member rows。"""
    decision, as_of = _date_args(decision_date, as_of_date)
    body, receipt = _package_body(capture, kind="child")
    _validate_outcome_as_of(as_of, body)
    _require(body["decision_date"] == decision, "capture_decision_date_mismatch")
    _require(cost_policy is None or isinstance(cost_policy, CostPolicy), "cost_policy_type_invalid")
    rows = body["rows"]
    stock_codes = {row["stock_code"] for row in rows}
    _require(1 <= len(stock_codes) <= MAX_POPULATION, "capture_population_bound")
    price_map = _validate_market_inputs(
        stock_codes=stock_codes,
        calendar=calendar,
        prices=prices,
        benchmark=benchmark,
    )
    members = [
        _member_projection(
            method_id=row["method_id"],
            stock_code=row["stock_code"],
            member_state=row["state"],
            reason=row["reason"],
            captured=True,
            decision=decision,
            as_of=as_of,
            calendar=calendar,
            prices=price_map,
            benchmark=benchmark,
            cost_policy=cost_policy,
        )
        for row in rows
    ]
    members.sort(key=lambda item: (item["method_id"], item["stock_code"]))
    return _sealed(
        {
            "projection_scope": "single_child_capture",
            "capture_identity_sha256": body["capture_identity_sha256"],
            "capture_receipt": receipt,
            "decision_date": decision,
            "as_of_date": as_of,
            "calendar": calendar.to_payload(),
            "price_points": [point.to_payload() for point in sorted(prices, key=lambda item: (item.instrument_id, item.trade_date))],
            "benchmark": None if benchmark is None else benchmark.to_payload(),
            "cost_policy": None if cost_policy is None else cost_policy.to_payload(),
            "population": _population_summary(
                members,
                included=body.get("included_denominator"),
                represented=len(stock_codes),
            ),
            "members": members,
            **_RESEARCH_POLICY,
        }
    )


def _validate_parent_child_bindings(
    parent: dict[str, Any],
    children: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, tuple[dict[str, Any], dict[str, Any]]], set[str]]:
    batches = parent["batches"]
    captured_batches = [batch for batch in batches if batch["status"] == "captured"]
    _require(len(children) == len(captured_batches), "parent_exact_child_count_mismatch")
    child_by_id: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for package in children:
        body, receipt = _package_body(package, kind="child")
        identity = body["capture_identity_sha256"]
        _require(identity not in child_by_id, "parent_duplicate_child")
        child_by_id[identity] = (body, receipt)
        source = parent.get("source_binding")
    captured_codes: set[str] = set()
    universe = parent["universe"]["value"]
    for batch in captured_batches:
        identity = batch["capture_identity_sha256"]
        _require(identity in child_by_id, "parent_captured_child_missing")
        child, _ = child_by_id[identity]
        _require(child["capture_identity_sha256"] == identity, "parent_child_identity_mismatch")
        _require(child["cohort_id"] == batch["cohort_id"], "parent_child_cohort_mismatch")
        _require(child["decision_date"] == universe["as_of_date"], "parent_child_decision_date_mismatch")
        _require(child["decision_cutoff"] == parent["decision_cutoff"], "parent_child_decision_cutoff_mismatch")
        _require(child["as_of"] == parent["as_of"], "parent_child_as_of_mismatch")
        _require(child["snapshot_sha256"] == batch["manifest_sha256"], "parent_child_snapshot_mismatch")
        expected_universe = _child_spec(universe, batch)
        expected_spec_sha256 = _sha256(_canonical_json(expected_universe).encode("utf-8"))
        expected_spec_ref = str(
            Path(parent["snapshot_root"])
            / "universes"
            / parent["plan_sha256"]
            / f"{batch['batch_id']}.json"
        )
        actual_universe = dict(child["universe"])
        expected_universe.pop("schema_version", None)
        actual_universe.pop("schema_version", None)
        child_spec_ref = actual_universe.pop("source_ref", None)
        child_spec_sha256 = actual_universe.pop("source_sha256", None)
        _require(actual_universe == expected_universe, "parent_child_universe_mismatch")
        _require(child_spec_ref == expected_spec_ref, "parent_child_universe_source_ref_mismatch")
        _require(child_spec_sha256 == expected_spec_sha256, "parent_child_universe_source_sha_mismatch")
        _require(child["method_contracts"] == parent["method_contracts"], "parent_child_methods_mismatch")
        _require(isinstance(source, dict), "parent_captured_without_source_binding")
        assert isinstance(source, dict)
        database = source["database"]
        expected_refs = {
            "database": database,
            "schema_identity_sha256": source["schema_identity_sha256"],
            "price": database + "#daily_prices",
            "technical": database + "#technical_indicators",
        }
        _require(
            all(reference.get("source_refs") == expected_refs for reference in child["source_refs"]),
            "parent_child_source_refs_mismatch",
        )
        captured_codes.update(batch["included_stock_codes"])
        captured_codes.update(item["stock_code"] for item in batch["excluded_stock_codes"])
    _require(set(child_by_id) == {batch["capture_identity_sha256"] for batch in captured_batches}, "parent_extra_child")
    if parent["status"] == "complete":
        _require(len(captured_batches) == len(batches), "parent_false_complete")
    return child_by_id, captured_codes


def build_parent_rule_research_forward_outcome(
    parent_capture: Mapping[str, Any],
    child_captures: Sequence[Mapping[str, Any]],
    *,
    decision_date: str,
    calendar: Calendar,
    prices: Sequence[PricePoint],
    benchmark: BenchmarkSpec | None,
    cost_policy: CostPolicy | None,
    as_of_date: str,
) -> ForwardOutcomeProjection:
    """以 parent receipt 與完整 exact child 集合保留整個固定母體。"""
    decision, as_of = _date_args(decision_date, as_of_date)
    parent, parent_receipt = _package_body(parent_capture, kind="parent")
    _validate_outcome_as_of(as_of, parent)
    universe = parent["universe"]["value"]
    _require(decision == universe["as_of_date"], "parent_decision_date_mismatch")
    _require(isinstance(child_captures, Sequence) and not isinstance(child_captures, (str, bytes)), "children_type_invalid")
    child_by_id, captured_codes = _validate_parent_child_bindings(parent, child_captures)
    _validate_outcome_as_of(as_of, *(body for body, _receipt in child_by_id.values()))
    _require(cost_policy is None or isinstance(cost_policy, CostPolicy), "cost_policy_type_invalid")
    included = list(universe["included_stock_codes"])
    exclusions = {item["stock_code"]: item["reason"] for item in universe["excluded_stock_codes"]}
    represented = len(included) + len(exclusions)
    _require(1 <= represented <= MAX_POPULATION, "parent_population_bound")
    stock_codes = set(included) | set(exclusions)
    price_map = _validate_market_inputs(
        stock_codes=stock_codes,
        calendar=calendar,
        prices=prices,
        benchmark=benchmark,
    )
    methods = sorted({value["method_id"] for value in parent["method_contracts"].values()})
    _require(len(methods) == 2, "parent_method_count_invalid")
    captured_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for body, _ in child_by_id.values():
        for row in body["rows"]:
            key = (row["method_id"], row["stock_code"])
            _require(key not in captured_rows, "parent_duplicate_member_row")
            captured_rows[key] = row
    members: list[dict[str, Any]] = []
    for method_id in methods:
        for code in sorted(stock_codes):
            if code in exclusions:
                row = captured_rows.get((method_id, code))
                exclusion_reason = exclusions[code]
                reason = exclusion_reason if code in captured_codes else "parent_batch_not_captured"
                _require(row is None or (row["state"] == "excluded" and row["reason"] == reason), "parent_exclusion_child_mismatch")
                captured = code in captured_codes
                state = "excluded" if captured else "uncaptured"
            else:
                exclusion_reason = None
                row = captured_rows.get((method_id, code))
                if row is None:
                    state = "uncaptured"
                    reason = "parent_batch_not_captured"
                    captured = False
                else:
                    state = row["state"]
                    reason = row["reason"]
                    captured = True
                    _require(state in _CAPTURE_STATES - {"excluded"}, "parent_included_child_state_invalid")
            members.append(
                _member_projection(
                    method_id=method_id,
                    stock_code=code,
                    member_state=state,
                    reason=reason,
                    captured=captured,
                    declared_excluded=code in exclusions,
                    declared_exclusion_reason=exclusions.get(code),
                    decision=decision,
                    as_of=as_of,
                    calendar=calendar,
                    prices=price_map,
                    benchmark=benchmark,
                    cost_policy=cost_policy,
                )
            )
    members.sort(key=lambda item: (item["method_id"], item["stock_code"]))
    return _sealed(
        {
            "projection_scope": "parent_exact_children",
            "parent_identity_sha256": parent["capture_identity_sha256"],
            "parent_receipt": parent_receipt,
            "child_identity_sha256s": sorted(child_by_id),
            "cohort_id": universe["universe_id"],
            "cohort_version": universe["version"],
            "cohort_status": parent["status"],
            "decision_date": decision,
            "as_of_date": as_of,
            "calendar": calendar.to_payload(),
            "price_points": [point.to_payload() for point in sorted(prices, key=lambda item: (item.instrument_id, item.trade_date))],
            "benchmark": None if benchmark is None else benchmark.to_payload(),
            "cost_policy": None if cost_policy is None else cost_policy.to_payload(),
            "population": _population_summary(
                members,
                included=len(included),
                represented=represented,
            ),
            "members": members,
            **_RESEARCH_POLICY,
        }
    )
