"""由 v4 保存快照推導 Decimal Bollinger bandwidth 與 ATR 原料證據。

此模組是純計算 leaf：只讀取呼叫端提供的 typed snapshot，不做 I/O、SQLite
或來源重開。自洽 SHA 只識別內容，不授予 F17 reader qualification；來源未提供
official available-at 時仍標示 unknown，historical PIT eligibility 固定為 false。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import (
    Clamped,
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    FloatOperation,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    Rounded,
    Subnormal,
    Underflow,
    localcontext,
)
import hashlib
import json
from typing import Literal, NoReturn

from app_module.daily_market_technical_feature_snapshot_v4 import (
    DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES,
    DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS,
    DailyMarketTechnicalFeatureSnapshotV4,
)
from app_module.daily_market_technical_source import DailyMarketTechnicalSourceRow


VOLATILITY_EVIDENCE_SCHEMA_V1 = "daily-market-technical-volatility-evidence.v1"

BOLLINGER_BANDWIDTH_METHOD_ID_V1 = "daily_market.bollinger_bandwidth_sma30_population_2x"
BOLLINGER_BANDWIDTH_METHOD_VERSION_V1 = "bollinger-bandwidth-sma30-population-2x.v1"
BOLLINGER_BANDWIDTH_WINDOW_V1 = 30
BOLLINGER_BANDWIDTH_DEVIATION_MULTIPLIER_V1 = Decimal(2)

ATR14_SMA_METHOD_ID_V1 = "daily_market.atr14_sma_true_range"
ATR14_SMA_METHOD_VERSION_V1 = "atr14-sma-true-range.v1"
ATR14_SMA_TRUE_RANGE_COUNT_V1 = 14
ATR14_SMA_REQUIRED_RAW_ROWS_V1 = ATR14_SMA_TRUE_RANGE_COUNT_V1 + 1

VOLATILITY_DECIMAL_PRECISION_V1 = 34
VOLATILITY_DECIMAL_ROUNDING_V1 = "ROUND_HALF_EVEN"
VOLATILITY_DECIMAL_EMIN_V1 = -6143
VOLATILITY_DECIMAL_EMAX_V1 = 6144
VOLATILITY_DECIMAL_CLAMP_V1 = 0
VOLATILITY_MAX_EVIDENCE_BYTES_V1 = DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES
VOLATILITY_MAX_INPUT_DECIMAL_TOKEN_BYTES_V1 = 96
VOLATILITY_MAX_INPUT_COEFFICIENT_DIGITS_V1 = 34
VOLATILITY_MIN_INPUT_EXPONENT_V1 = -34
VOLATILITY_MAX_INPUT_EXPONENT_V1 = 12
VOLATILITY_MIN_INPUT_ADJUSTED_EXPONENT_V1 = -12
VOLATILITY_MAX_INPUT_ADJUSTED_EXPONENT_V1 = 12
VOLATILITY_MAX_OUTPUT_DECIMAL_TOKEN_BYTES_V1 = 256
VOLATILITY_MAX_OUTPUT_COEFFICIENT_DIGITS_V1 = VOLATILITY_DECIMAL_PRECISION_V1
VOLATILITY_MIN_OUTPUT_EXPONENT_V1 = -100
VOLATILITY_MAX_OUTPUT_EXPONENT_V1 = 100
VOLATILITY_MIN_OUTPUT_ADJUSTED_EXPONENT_V1 = -100
VOLATILITY_MAX_OUTPUT_ADJUSTED_EXPONENT_V1 = 100
VOLATILITY_MAX_REASON_CODES_V1 = 8
VOLATILITY_MAX_REASON_CODE_BYTES_V1 = 128

_SHA256_LENGTH = 64
_TRAPPED_SIGNALS_V1 = frozenset({
    DivisionByZero,
    FloatOperation,
    InvalidOperation,
    Overflow,
})
_DECIMAL_CONTEXT_SIGNALS_V1 = (
    Clamped,
    DivisionByZero,
    FloatOperation,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    Subnormal,
    Underflow,
)
_MEASURE_STATES = frozenset({"observed", "unknown"})


class DailyMarketTechnicalVolatilityEvidenceError(ValueError):
    """波動原料輸入或方法契約無效；`code` 可供呼叫端穩定判讀。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalVolatilityEvidenceError(code)


def _canonical_json_bytes(value: object) -> bytes:
    _reject_float_tree(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise DailyMarketTechnicalVolatilityEvidenceError(
            "volatility_json_payload_invalid"
        ) from exc


def _reject_float_tree(value: object) -> None:
    if isinstance(value, float):
        _fail("volatility_float_payload_rejected")
    if isinstance(value, dict):
        for nested in value.values():
            _reject_float_tree(nested)
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _reject_float_tree(nested)


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_sha(value: object, code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(code)
    return value


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        _fail("volatility_decimal_output_invalid")
    decimal_tuple = value.as_tuple()
    if type(decimal_tuple.exponent) is not int:
        _fail("volatility_decimal_output_invalid")
    adjusted_exponent = value.adjusted() if value else 0
    if (
        len(decimal_tuple.digits) > VOLATILITY_MAX_OUTPUT_COEFFICIENT_DIGITS_V1
        or decimal_tuple.exponent < VOLATILITY_MIN_OUTPUT_EXPONENT_V1
        or decimal_tuple.exponent > VOLATILITY_MAX_OUTPUT_EXPONENT_V1
        or adjusted_exponent < VOLATILITY_MIN_OUTPUT_ADJUSTED_EXPONENT_V1
        or adjusted_exponent > VOLATILITY_MAX_OUTPUT_ADJUSTED_EXPONENT_V1
    ):
        _fail("volatility_decimal_output_range_limit")
    text = str(value)
    if len(text.encode("utf-8")) > VOLATILITY_MAX_OUTPUT_DECIMAL_TOKEN_BYTES_V1:
        _fail("volatility_decimal_output_limit")
    return text


def _new_decimal_context() -> Context:
    """回傳與 KDJ evidence 相同、明示全部 traps 的固定 Decimal context。"""

    context = Context(
        prec=VOLATILITY_DECIMAL_PRECISION_V1,
        rounding=ROUND_HALF_EVEN,
        Emin=VOLATILITY_DECIMAL_EMIN_V1,
        Emax=VOLATILITY_DECIMAL_EMAX_V1,
        clamp=VOLATILITY_DECIMAL_CLAMP_V1,
    )
    for signal in _DECIMAL_CONTEXT_SIGNALS_V1:
        context.traps[signal] = signal in _TRAPPED_SIGNALS_V1
    return context


def _decimal_trap_policy_payload() -> dict[str, bool]:
    return {
        signal.__name__: signal in _TRAPPED_SIGNALS_V1
        for signal in _DECIMAL_CONTEXT_SIGNALS_V1
    }


def _numeric_context_payload() -> dict[str, object]:
    return {
        "precision": VOLATILITY_DECIMAL_PRECISION_V1,
        "rounding": VOLATILITY_DECIMAL_ROUNDING_V1,
        "emin": VOLATILITY_DECIMAL_EMIN_V1,
        "emax": VOLATILITY_DECIMAL_EMAX_V1,
        "clamp": VOLATILITY_DECIMAL_CLAMP_V1,
        "traps": _decimal_trap_policy_payload(),
    }


def _method_identity(
    method_id: str,
    method_version: str,
    parameters: dict[str, object],
) -> str:
    return _sha256_json({
        "method_id": method_id,
        "method_version": method_version,
        "parameters": parameters,
        "numeric_context": {
            "precision": VOLATILITY_DECIMAL_PRECISION_V1,
            "rounding": VOLATILITY_DECIMAL_ROUNDING_V1,
            "emin": VOLATILITY_DECIMAL_EMIN_V1,
            "emax": VOLATILITY_DECIMAL_EMAX_V1,
            "clamp": VOLATILITY_DECIMAL_CLAMP_V1,
            "traps": _decimal_trap_policy_payload(),
        },
    })


BOLLINGER_BANDWIDTH_METHOD_PARAMETERS_V1: dict[str, object] = {
    "observation_window": BOLLINGER_BANDWIDTH_WINDOW_V1,
    "middle": "simple_arithmetic_mean",
    "variance": "population_sum_squared_deviation_divided_by_30",
    "standard_deviation": "decimal_context_sqrt",
    "band_multiplier": "2",
    "bandwidth_formula": "(upper_minus_lower)/middle*100",
    "warmup": "30_valid_consecutive_observed_rows",
    "missing_policy": "unknown_without_fallback_or_fill",
    "input_decimal_bounds": {
        "token_bytes_max": VOLATILITY_MAX_INPUT_DECIMAL_TOKEN_BYTES_V1,
        "coefficient_digits_max": VOLATILITY_MAX_INPUT_COEFFICIENT_DIGITS_V1,
        "exponent_min": VOLATILITY_MIN_INPUT_EXPONENT_V1,
        "exponent_max": VOLATILITY_MAX_INPUT_EXPONENT_V1,
        "adjusted_exponent_min": VOLATILITY_MIN_INPUT_ADJUSTED_EXPONENT_V1,
        "adjusted_exponent_max": VOLATILITY_MAX_INPUT_ADJUSTED_EXPONENT_V1,
    },
    "output_decimal_bounds": {
        "token_bytes_max": VOLATILITY_MAX_OUTPUT_DECIMAL_TOKEN_BYTES_V1,
        "coefficient_digits_max": VOLATILITY_MAX_OUTPUT_COEFFICIENT_DIGITS_V1,
        "exponent_min": VOLATILITY_MIN_OUTPUT_EXPONENT_V1,
        "exponent_max": VOLATILITY_MAX_OUTPUT_EXPONENT_V1,
        "adjusted_exponent_min": VOLATILITY_MIN_OUTPUT_ADJUSTED_EXPONENT_V1,
        "adjusted_exponent_max": VOLATILITY_MAX_OUTPUT_ADJUSTED_EXPONENT_V1,
    },
}
ATR14_SMA_METHOD_PARAMETERS_V1: dict[str, object] = {
    "true_range_count": ATR14_SMA_TRUE_RANGE_COUNT_V1,
    "required_raw_rows": ATR14_SMA_REQUIRED_RAW_ROWS_V1,
    "true_range_formula": "max(high-low,abs(high-previous_close),abs(low-previous_close))",
    "smoothing": "simple_arithmetic_mean",
    "recursive_seed": None,
    "normalization": "atr/current_close*100",
    "warmup": "14_true_ranges_with_one_preceding_close_anchor",
    "missing_policy": "unknown_without_fallback_or_fill",
    "input_decimal_bounds": {
        "token_bytes_max": VOLATILITY_MAX_INPUT_DECIMAL_TOKEN_BYTES_V1,
        "coefficient_digits_max": VOLATILITY_MAX_INPUT_COEFFICIENT_DIGITS_V1,
        "exponent_min": VOLATILITY_MIN_INPUT_EXPONENT_V1,
        "exponent_max": VOLATILITY_MAX_INPUT_EXPONENT_V1,
        "adjusted_exponent_min": VOLATILITY_MIN_INPUT_ADJUSTED_EXPONENT_V1,
        "adjusted_exponent_max": VOLATILITY_MAX_INPUT_ADJUSTED_EXPONENT_V1,
    },
    "output_decimal_bounds": {
        "token_bytes_max": VOLATILITY_MAX_OUTPUT_DECIMAL_TOKEN_BYTES_V1,
        "coefficient_digits_max": VOLATILITY_MAX_OUTPUT_COEFFICIENT_DIGITS_V1,
        "exponent_min": VOLATILITY_MIN_OUTPUT_EXPONENT_V1,
        "exponent_max": VOLATILITY_MAX_OUTPUT_EXPONENT_V1,
        "adjusted_exponent_min": VOLATILITY_MIN_OUTPUT_ADJUSTED_EXPONENT_V1,
        "adjusted_exponent_max": VOLATILITY_MAX_OUTPUT_ADJUSTED_EXPONENT_V1,
    },
}
_METHOD_PARAMETERS_BY_ID_V1: dict[str, dict[str, object]] = {
    BOLLINGER_BANDWIDTH_METHOD_ID_V1: BOLLINGER_BANDWIDTH_METHOD_PARAMETERS_V1,
    ATR14_SMA_METHOD_ID_V1: ATR14_SMA_METHOD_PARAMETERS_V1,
}
BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1 = _method_identity(
    BOLLINGER_BANDWIDTH_METHOD_ID_V1,
    BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
    BOLLINGER_BANDWIDTH_METHOD_PARAMETERS_V1,
)
ATR14_SMA_METHOD_IDENTITY_SHA256_V1 = _method_identity(
    ATR14_SMA_METHOD_ID_V1,
    ATR14_SMA_METHOD_VERSION_V1,
    ATR14_SMA_METHOD_PARAMETERS_V1,
)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalVolatilityMeasureV1:
    """單一波動原料結果；unknown 不會被轉成零或策略 match。"""

    method_id: str
    method_version: str
    method_identity_sha256: str
    state: Literal["observed", "unknown"]
    value: Decimal | None
    unit: Literal["percent", "TWD/share"]
    normalized_value: Decimal | None
    normalized_unit: Literal["percent"] | None
    reason_codes: tuple[str, ...]
    input_feature_dates: tuple[date | None, ...]
    input_row_fingerprints_sha256: tuple[str, ...]
    input_rows_required: int
    warmup_observations_required: int
    warmup_observations_observed: int
    window_observations_contiguous: bool
    window_identity_sha256: str

    def _payload(self) -> dict[str, object]:
        expected_methods = {
            BOLLINGER_BANDWIDTH_METHOD_ID_V1: (
                BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
                BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
                "percent",
                None,
                BOLLINGER_BANDWIDTH_WINDOW_V1,
                BOLLINGER_BANDWIDTH_WINDOW_V1,
            ),
            ATR14_SMA_METHOD_ID_V1: (
                ATR14_SMA_METHOD_VERSION_V1,
                ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
                "TWD/share",
                "percent",
                ATR14_SMA_REQUIRED_RAW_ROWS_V1,
                ATR14_SMA_TRUE_RANGE_COUNT_V1,
            ),
        }
        expected = expected_methods.get(self.method_id)
        expected_parameters = _METHOD_PARAMETERS_BY_ID_V1.get(self.method_id)
        if (
            expected is None
            or expected_parameters is None
            or self.method_version != expected[0]
            or self.method_identity_sha256 != expected[1]
            or self.unit != expected[2]
            or self.normalized_unit != expected[3]
            or self.input_rows_required != expected[4]
            or self.warmup_observations_required != expected[5]
            or self.state not in _MEASURE_STATES
            or type(self.reason_codes) is not tuple
            or len(self.reason_codes) > VOLATILITY_MAX_REASON_CODES_V1
            or any(
                not isinstance(reason, str)
                or not reason
                or len(reason.encode("utf-8")) > VOLATILITY_MAX_REASON_CODE_BYTES_V1
                for reason in self.reason_codes
            )
            or type(self.input_feature_dates) is not tuple
            or type(self.input_row_fingerprints_sha256) is not tuple
            or len(self.input_feature_dates) != len(self.input_row_fingerprints_sha256)
            or len(self.input_feature_dates) > expected[4]
            or any(value is not None and type(value) is not date for value in self.input_feature_dates)
            or any(
                _require_sha(value, "volatility_row_fingerprint_invalid") != value
                for value in self.input_row_fingerprints_sha256
            )
            or type(self.input_rows_required) is not int
            or type(self.warmup_observations_required) is not int
            or type(self.warmup_observations_observed) is not int
            or not 0 <= self.warmup_observations_observed <= self.warmup_observations_required
            or type(self.window_observations_contiguous) is not bool
        ):
            _fail("volatility_measure_contract_invalid")
        _require_sha(self.window_identity_sha256, "volatility_window_identity_invalid")
        value_text = _decimal_text(self.value)
        normalized_text = _decimal_text(self.normalized_value)
        if self.state == "observed":
            if (
                self.reason_codes
                or self.value is None
                or not self.window_observations_contiguous
                or len(self.input_feature_dates) != self.input_rows_required
                or any(value is None for value in self.input_feature_dates)
                or any(
                    earlier is not None and later is not None and earlier >= later
                    for earlier, later in zip(
                        self.input_feature_dates,
                        self.input_feature_dates[1:],
                    )
                )
                or self.warmup_observations_observed != self.warmup_observations_required
            ):
                _fail("volatility_observed_measure_invalid")
            if self.method_id == ATR14_SMA_METHOD_ID_V1 and self.normalized_value is None:
                _fail("volatility_atr_normalized_value_missing")
            if self.method_id == BOLLINGER_BANDWIDTH_METHOD_ID_V1 and self.normalized_value is not None:
                _fail("volatility_bandwidth_normalized_value_unexpected")
        elif (
            not self.reason_codes
            or self.value is not None
            or self.normalized_value is not None
        ):
            _fail("volatility_unknown_measure_invalid")
        expected_window_identity = _sha256_json({
            "schema": "daily-market-technical-volatility-window.v1",
            "method_identity_sha256": self.method_identity_sha256,
            "feature_dates": [
                item.isoformat() if item is not None else None
                for item in self.input_feature_dates
            ],
            "source_row_fingerprints_sha256": list(self.input_row_fingerprints_sha256),
        })
        if expected_window_identity != self.window_identity_sha256:
            _fail("volatility_window_identity_mismatch")
        return {
            "method_id": self.method_id,
            "method_version": self.method_version,
            "method_identity_sha256": self.method_identity_sha256,
            "method_parameters": dict(expected_parameters),
            "numeric_context": _numeric_context_payload(),
            "state": self.state,
            "value": value_text,
            "unit": self.unit,
            "normalized_value": normalized_text,
            "normalized_unit": self.normalized_unit,
            "reason_codes": list(self.reason_codes),
            "input_feature_dates": [
                value.isoformat() if value is not None else None
                for value in self.input_feature_dates
            ],
            "input_row_fingerprints_sha256": list(self.input_row_fingerprints_sha256),
            "input_rows_required": self.input_rows_required,
            "warmup_observations_required": self.warmup_observations_required,
            "warmup_observations_observed": self.warmup_observations_observed,
            "window_observations_contiguous": self.window_observations_contiguous,
            "window_identity_sha256": self.window_identity_sha256,
        }

    def to_dict(self) -> dict[str, object]:
        body = self._payload()
        return {**body, "measurement_identity_sha256": _sha256_json(body)}


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalVolatilityEvidenceV1:
    """單一快照的獨立 bandwidth 與 ATR 原料，不表示收斂或突破。"""

    stock_code: str
    decision_date: date
    decision_cutoff: datetime
    source_id: str
    source_identity: str
    source_clock_sha256: str
    source_pin_sha256: str
    raw_source_window_fingerprint_sha256: str
    source_window_fingerprint_sha256: str
    snapshot_identity_sha256: str
    observed_prefix_contiguous: bool
    current_feature_date: date | None
    current_row_fingerprint_sha256: str | None
    bandwidth: DailyMarketTechnicalVolatilityMeasureV1
    atr14_sma: DailyMarketTechnicalVolatilityMeasureV1

    def _payload(self) -> dict[str, object]:
        if (
            type(self.stock_code) is not str
            or not self.stock_code
            or len(self.stock_code) > 16
            or type(self.decision_date) is not date
            or type(self.decision_cutoff) is not datetime
            or self.decision_cutoff.utcoffset() is None
            or self.decision_cutoff.date() != self.decision_date
            or type(self.source_id) is not str
            or not self.source_id
            or len(self.source_id.encode("utf-8")) > 128
            or type(self.source_identity) is not str
            or not self.source_identity
            or len(self.source_identity.encode("utf-8")) > 256
            or type(self.observed_prefix_contiguous) is not bool
            or (self.current_feature_date is not None and type(self.current_feature_date) is not date)
            or (
                self.current_feature_date is not None
                and self.current_feature_date > self.decision_date
            )
            or type(self.bandwidth) is not DailyMarketTechnicalVolatilityMeasureV1
            or type(self.atr14_sma) is not DailyMarketTechnicalVolatilityMeasureV1
        ):
            _fail("volatility_evidence_contract_invalid")
        for name, value in (
            ("source_clock", self.source_clock_sha256),
            ("source_pin", self.source_pin_sha256),
            ("raw_source_window", self.raw_source_window_fingerprint_sha256),
            ("source_window", self.source_window_fingerprint_sha256),
            ("snapshot", self.snapshot_identity_sha256),
        ):
            _require_sha(value, f"volatility_{name}_identity_invalid")
        if self.current_row_fingerprint_sha256 is not None:
            _require_sha(
                self.current_row_fingerprint_sha256,
                "volatility_current_row_fingerprint_invalid",
            )
        if (self.current_feature_date is None) != (self.current_row_fingerprint_sha256 is None):
            _fail("volatility_current_row_binding_invalid")
        bandwidth = self.bandwidth.to_dict()
        atr14_sma = self.atr14_sma.to_dict()
        if (
            bandwidth["method_id"] != BOLLINGER_BANDWIDTH_METHOD_ID_V1
            or atr14_sma["method_id"] != ATR14_SMA_METHOD_ID_V1
        ):
            _fail("volatility_measure_method_mismatch")
        for measure in (self.bandwidth, self.atr14_sma):
            dates = measure.input_feature_dates
            if any(value is not None and value > self.decision_date for value in dates):
                _fail("volatility_future_observation_rejected")
            last_date = dates[-1] if dates else None
            last_fingerprint = (
                measure.input_row_fingerprints_sha256[-1]
                if measure.input_row_fingerprints_sha256
                else None
            )
            if (last_date, last_fingerprint) != (
                self.current_feature_date,
                self.current_row_fingerprint_sha256,
            ):
                _fail("volatility_measure_current_observation_mismatch")
        return {
            "schema": VOLATILITY_EVIDENCE_SCHEMA_V1,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "source_id": self.source_id,
            "source_identity": self.source_identity,
            "source_clock_sha256": self.source_clock_sha256,
            "source_pin_sha256": self.source_pin_sha256,
            "raw_source_window_fingerprint_sha256": self.raw_source_window_fingerprint_sha256,
            "source_window_fingerprint_sha256": self.source_window_fingerprint_sha256,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "current_observation": {
                "feature_date": (
                    self.current_feature_date.isoformat()
                    if self.current_feature_date is not None
                    else None
                ),
                "source_row_fingerprint_sha256": self.current_row_fingerprint_sha256,
            },
            "observed_prefix_contiguous": self.observed_prefix_contiguous,
            "measurements": {
                "bollinger_bandwidth": bandwidth,
                "atr14_sma_true_range": atr14_sma,
            },
            "availability": {
                "source_available_at": None,
                "availability_status": "unknown",
                "historical_pit_eligible": False,
            },
            "qualification": {
                "reader_qualified": False,
                "qualification_note": "snapshot_content_hash_is_not_source_qualification",
            },
            "decision": {
                "contraction_state": "not_evaluated",
                "breakout_state": "not_evaluated",
            },
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._payload()
        if len(_canonical_json_bytes(payload)) > VOLATILITY_MAX_EVIDENCE_BYTES_V1:
            _fail("volatility_evidence_byte_limit")
        payload["evidence_identity_sha256"] = _sha256_json(payload)
        if len(_canonical_json_bytes(payload)) > VOLATILITY_MAX_EVIDENCE_BYTES_V1:
            _fail("volatility_evidence_byte_limit")
        return payload

    @property
    def evidence_identity_sha256(self) -> str:
        payload = self._payload()
        if len(_canonical_json_bytes(payload)) > VOLATILITY_MAX_EVIDENCE_BYTES_V1:
            _fail("volatility_evidence_byte_limit")
        return _sha256_json(payload)


def project_daily_market_technical_volatility_evidence_v1(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
) -> DailyMarketTechnicalVolatilityEvidenceV1:
    """從已保存 snapshot 計算兩種獨立、bounded 的原料證據。

    每個方法只看固定的最新原始觀測切片；中間缺值不會被略過，日期只須嚴格
    遞增，不要求相鄰日曆日。任一方法暖機不足或窗口 OHLC 無效時，該方法單獨
    回 unknown；另一方法仍可按自己的窗口計算。最新列無效時不回退到舊列。
    """

    if type(snapshot) is not DailyMarketTechnicalFeatureSnapshotV4:
        _fail("volatility_snapshot_type_invalid")
    try:
        with localcontext(_new_decimal_context()):
            snapshot.to_dict()
    except (TypeError, ValueError, OverflowError, DecimalException) as exc:
        raise DailyMarketTechnicalVolatilityEvidenceError(
            "volatility_snapshot_transport_invalid"
        ) from exc

    rows = snapshot.rows
    if len(rows) > DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS:
        _fail("volatility_snapshot_row_limit")
    _validate_input_decimal_window(rows[-BOLLINGER_BANDWIDTH_WINDOW_V1:])
    current = rows[-1] if rows else None
    if current is not None and current.feature_date is not None and current.feature_date > snapshot.decision_date:
        _fail("volatility_future_observation_rejected")
    current_date = current.feature_date if current is not None else None
    current_fingerprint = current.row_fingerprint_sha256 if current is not None and current_date is not None else None
    if current is not None and current.ohlc_valid:
        session = snapshot.current_session
        if session is None or session.feature_date != current.feature_date:
            _fail("volatility_current_session_mismatch")

    try:
        with localcontext(_new_decimal_context()):
            bandwidth = _build_bandwidth_measure(snapshot, rows)
            atr14 = _build_atr_measure(snapshot, rows)
    except DecimalException as exc:
        raise DailyMarketTechnicalVolatilityEvidenceError(
            "volatility_decimal_calculation_invalid"
        ) from exc

    evidence = DailyMarketTechnicalVolatilityEvidenceV1(
        stock_code=snapshot.stock_code,
        decision_date=snapshot.decision_date,
        decision_cutoff=snapshot.decision_cutoff,
        source_id=snapshot.source_id,
        source_identity=snapshot.source_identity,
        source_clock_sha256=snapshot.source_clock_sha256,
        source_pin_sha256=snapshot.source_pin_sha256,
        raw_source_window_fingerprint_sha256=snapshot.raw_source_window_fingerprint_sha256,
        source_window_fingerprint_sha256=snapshot.source_window_fingerprint_sha256,
        snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        observed_prefix_contiguous=snapshot.observed_prefix_contiguous,
        current_feature_date=current_date,
        current_row_fingerprint_sha256=current_fingerprint,
        bandwidth=bandwidth,
        atr14_sma=atr14,
    )
    evidence.to_dict()
    return evidence


def _build_bandwidth_measure(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    rows: tuple[DailyMarketTechnicalSourceRow, ...],
) -> DailyMarketTechnicalVolatilityMeasureV1:
    selected = rows[-BOLLINGER_BANDWIDTH_WINDOW_V1:]
    reasons = _window_reasons(
        snapshot,
        selected,
        required_rows=BOLLINGER_BANDWIDTH_WINDOW_V1,
    )
    window_contiguous = _window_is_contiguous(snapshot, selected)
    warmup_observed = _trailing_valid_row_count(selected)
    if reasons:
        return _make_measure(
            method_id=BOLLINGER_BANDWIDTH_METHOD_ID_V1,
            method_version=BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
            method_identity=BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
            unit="percent",
            normalized_unit=None,
            selected=selected,
            input_rows_required=BOLLINGER_BANDWIDTH_WINDOW_V1,
            warmup_required=BOLLINGER_BANDWIDTH_WINDOW_V1,
            warmup_observed=warmup_observed,
            contiguous=window_contiguous,
            reasons=reasons,
        )
    closes = tuple(row.close_price for row in selected)
    if any(type(value) is not Decimal for value in closes):
        _fail("volatility_bandwidth_close_missing_after_validation")
    value = _calculate_bandwidth_percent(tuple(value for value in closes if value is not None))
    if value is None:
        return _make_measure(
            method_id=BOLLINGER_BANDWIDTH_METHOD_ID_V1,
            method_version=BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
            method_identity=BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
            unit="percent",
            normalized_unit=None,
            selected=selected,
            input_rows_required=BOLLINGER_BANDWIDTH_WINDOW_V1,
            warmup_required=BOLLINGER_BANDWIDTH_WINDOW_V1,
            warmup_observed=warmup_observed,
            contiguous=True,
            reasons=("bandwidth_zero_middle",),
        )
    return _make_measure(
        method_id=BOLLINGER_BANDWIDTH_METHOD_ID_V1,
        method_version=BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
        method_identity=BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
        unit="percent",
        normalized_unit=None,
        selected=selected,
        input_rows_required=BOLLINGER_BANDWIDTH_WINDOW_V1,
        warmup_required=BOLLINGER_BANDWIDTH_WINDOW_V1,
        warmup_observed=warmup_observed,
        contiguous=True,
        reasons=(),
        value=value,
    )


def _build_atr_measure(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    rows: tuple[DailyMarketTechnicalSourceRow, ...],
) -> DailyMarketTechnicalVolatilityMeasureV1:
    selected = rows[-ATR14_SMA_REQUIRED_RAW_ROWS_V1:]
    reasons = _window_reasons(
        snapshot,
        selected,
        required_rows=ATR14_SMA_REQUIRED_RAW_ROWS_V1,
    )
    window_contiguous = _window_is_contiguous(snapshot, selected)
    warmup_observed = _trailing_true_range_count(selected)
    if reasons:
        return _make_measure(
            method_id=ATR14_SMA_METHOD_ID_V1,
            method_version=ATR14_SMA_METHOD_VERSION_V1,
            method_identity=ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
            unit="TWD/share",
            normalized_unit="percent",
            selected=selected,
            input_rows_required=ATR14_SMA_REQUIRED_RAW_ROWS_V1,
            warmup_required=ATR14_SMA_TRUE_RANGE_COUNT_V1,
            warmup_observed=warmup_observed,
            contiguous=window_contiguous,
            reasons=reasons,
        )
    true_ranges = _calculate_true_ranges(selected)
    if len(true_ranges) != ATR14_SMA_TRUE_RANGE_COUNT_V1:
        _fail("volatility_atr_true_range_count_mismatch")
    atr14 = sum(true_ranges, Decimal(0)) / Decimal(ATR14_SMA_TRUE_RANGE_COUNT_V1)
    close = selected[-1].close_price
    if type(close) is not Decimal or close <= 0:
        return _make_measure(
            method_id=ATR14_SMA_METHOD_ID_V1,
            method_version=ATR14_SMA_METHOD_VERSION_V1,
            method_identity=ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
            unit="TWD/share",
            normalized_unit="percent",
            selected=selected,
            input_rows_required=ATR14_SMA_REQUIRED_RAW_ROWS_V1,
            warmup_required=ATR14_SMA_TRUE_RANGE_COUNT_V1,
            warmup_observed=warmup_observed,
            contiguous=window_contiguous,
            reasons=("atr_current_close_nonpositive",),
        )
    return _make_measure(
        method_id=ATR14_SMA_METHOD_ID_V1,
        method_version=ATR14_SMA_METHOD_VERSION_V1,
        method_identity=ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
        unit="TWD/share",
        normalized_unit="percent",
        selected=selected,
        input_rows_required=ATR14_SMA_REQUIRED_RAW_ROWS_V1,
        warmup_required=ATR14_SMA_TRUE_RANGE_COUNT_V1,
        warmup_observed=warmup_observed,
        contiguous=window_contiguous,
        reasons=(),
        value=atr14,
        normalized_value=_normalize_atr_percent(atr14, close),
    )


def _window_reasons(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    selected: tuple[DailyMarketTechnicalSourceRow, ...],
    *,
    required_rows: int,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if len(selected) < required_rows:
        reasons.append("warmup_insufficient")
    if not snapshot.observed_prefix_contiguous:
        reasons.append("source_observed_prefix_not_contiguous")
    dates = tuple(row.feature_date for row in selected)
    if any(value is None for value in dates):
        reasons.append("observation_date_invalid")
    known_dates = tuple(value for value in dates if value is not None)
    if len(known_dates) != len(set(known_dates)) or any(
        earlier >= later for earlier, later in zip(known_dates, known_dates[1:])
    ):
        reasons.append("observed_dates_not_increasing")
    if any(
        row.feature_date is not None and row.feature_date > snapshot.decision_date
        for row in selected
    ):
        _fail("volatility_future_observation_rejected")
    if any(not _valid_ohlc_row(row) for row in selected):
        reasons.append("ohlc_missing_or_invalid")
    return tuple(dict.fromkeys(reasons))


def _window_is_contiguous(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    selected: tuple[DailyMarketTechnicalSourceRow, ...],
) -> bool:
    dates = tuple(row.feature_date for row in selected)
    return (
        snapshot.observed_prefix_contiguous
        and all(_valid_ohlc_row(row) for row in selected)
        and all(value is not None for value in dates)
        and all(
            earlier is not None and later is not None and earlier < later
            for earlier, later in zip(dates, dates[1:])
        )
    )


def _validate_input_decimal_window(
    selected: tuple[DailyMarketTechnicalSourceRow, ...],
) -> None:
    """在公式前核對每個方法窗口內的 Decimal 資源界限。"""

    for row in selected:
        raw_values = dict(row.raw_values)
        for field_name, value in (
            ("open", row.open_price),
            ("high", row.high_price),
            ("low", row.low_price),
            ("close", row.close_price),
        ):
            raw_token = raw_values.get(field_name)
            if not isinstance(raw_token, str):
                _fail("volatility_input_decimal_token_missing")
            if len(raw_token.encode("utf-8")) > VOLATILITY_MAX_INPUT_DECIMAL_TOKEN_BYTES_V1:
                _fail("volatility_input_decimal_token_limit")
            if value is None:
                continue
            if type(value) is not Decimal or not value.is_finite():
                _fail("volatility_input_decimal_invalid")
            decimal_tuple = value.as_tuple()
            exponent = decimal_tuple.exponent
            if type(exponent) is not int:
                _fail("volatility_input_decimal_invalid")
            adjusted_exponent = value.adjusted() if value else 0
            if (
                len(decimal_tuple.digits) > VOLATILITY_MAX_INPUT_COEFFICIENT_DIGITS_V1
                or exponent < VOLATILITY_MIN_INPUT_EXPONENT_V1
                or exponent > VOLATILITY_MAX_INPUT_EXPONENT_V1
                or adjusted_exponent < VOLATILITY_MIN_INPUT_ADJUSTED_EXPONENT_V1
                or adjusted_exponent > VOLATILITY_MAX_INPUT_ADJUSTED_EXPONENT_V1
            ):
                _fail("volatility_input_decimal_range_limit")


def _valid_ohlc_row(row: DailyMarketTechnicalSourceRow) -> bool:
    values = (row.open_price, row.high_price, row.low_price, row.close_price)
    if (
        row.feature_date is None
        or row.ohlc_valid is not True
        or any(type(value) is not Decimal or not value.is_finite() or value <= 0 for value in values)
    ):
        return False
    open_price, high_price, low_price, close_price = values
    assert open_price is not None and high_price is not None
    assert low_price is not None and close_price is not None
    return (
        low_price <= min(open_price, close_price)
        and high_price >= max(open_price, close_price)
    )


def _trailing_valid_row_count(rows: tuple[DailyMarketTechnicalSourceRow, ...]) -> int:
    count = 0
    next_date: date | None = None
    for row in reversed(rows):
        if not _valid_ohlc_row(row):
            break
        if next_date is not None and row.feature_date is not None and row.feature_date >= next_date:
            break
        count += 1
        next_date = row.feature_date
    return count


def _trailing_true_range_count(rows: tuple[DailyMarketTechnicalSourceRow, ...]) -> int:
    count = 0
    for index in range(len(rows) - 1, 0, -1):
        previous = rows[index - 1]
        current = rows[index]
        if (
            not _valid_ohlc_row(previous)
            or not _valid_ohlc_row(current)
            or previous.feature_date is None
            or current.feature_date is None
            or previous.feature_date >= current.feature_date
        ):
            break
        count += 1
    return count


def _calculate_bandwidth_percent(closes: tuple[Decimal, ...]) -> Decimal | None:
    if (
        len(closes) != BOLLINGER_BANDWIDTH_WINDOW_V1
        or any(type(value) is not Decimal or not value.is_finite() for value in closes)
    ):
        _fail("volatility_bandwidth_input_invalid")
    middle = sum(closes, Decimal(0)) / Decimal(BOLLINGER_BANDWIDTH_WINDOW_V1)
    if middle == 0:
        return None
    variance = sum(
        ((value - middle) * (value - middle) for value in closes),
        Decimal(0),
    ) / Decimal(BOLLINGER_BANDWIDTH_WINDOW_V1)
    sigma = variance.sqrt()
    upper = middle + BOLLINGER_BANDWIDTH_DEVIATION_MULTIPLIER_V1 * sigma
    lower = middle - BOLLINGER_BANDWIDTH_DEVIATION_MULTIPLIER_V1 * sigma
    return ((upper - lower) / middle) * Decimal(100)


def _normalize_atr_percent(atr: Decimal, current_close: Decimal) -> Decimal | None:
    if (
        type(atr) is not Decimal
        or type(current_close) is not Decimal
        or not atr.is_finite()
        or not current_close.is_finite()
    ):
        _fail("volatility_atr_normalization_input_invalid")
    if current_close <= 0:
        return None
    return atr / current_close * Decimal(100)


def _calculate_true_ranges(
    rows: tuple[DailyMarketTechnicalSourceRow, ...],
) -> tuple[Decimal, ...]:
    if len(rows) != ATR14_SMA_REQUIRED_RAW_ROWS_V1 or any(
        not _valid_ohlc_row(row) for row in rows
    ):
        _fail("volatility_atr_input_invalid")
    result: list[Decimal] = []
    for previous, current in zip(rows[:-1], rows[1:], strict=True):
        previous_close = previous.close_price
        current_high = current.high_price
        current_low = current.low_price
        if any(type(value) is not Decimal for value in (previous_close, current_high, current_low)):
            _fail("volatility_atr_decimal_input_missing")
        assert previous_close is not None and current_high is not None and current_low is not None
        result.append(max(
            current_high - current_low,
            abs(current_high - previous_close),
            abs(current_low - previous_close),
        ))
    return tuple(result)


def _make_measure(
    *,
    method_id: str,
    method_version: str,
    method_identity: str,
    unit: Literal["percent", "TWD/share"],
    normalized_unit: Literal["percent"] | None,
    selected: tuple[DailyMarketTechnicalSourceRow, ...],
    input_rows_required: int,
    warmup_required: int,
    warmup_observed: int,
    contiguous: bool,
    reasons: tuple[str, ...],
    value: Decimal | None = None,
    normalized_value: Decimal | None = None,
) -> DailyMarketTechnicalVolatilityMeasureV1:
    dates = tuple(row.feature_date for row in selected)
    fingerprints = tuple(row.row_fingerprint_sha256 for row in selected)
    window_identity = _sha256_json({
        "schema": "daily-market-technical-volatility-window.v1",
        "method_identity_sha256": method_identity,
        "feature_dates": [item.isoformat() if item is not None else None for item in dates],
        "source_row_fingerprints_sha256": list(fingerprints),
    })
    return DailyMarketTechnicalVolatilityMeasureV1(
        method_id=method_id,
        method_version=method_version,
        method_identity_sha256=method_identity,
        state="observed" if not reasons and value is not None else "unknown",
        value=value if not reasons else None,
        unit=unit,
        normalized_value=normalized_value if not reasons else None,
        normalized_unit=normalized_unit,
        reason_codes=reasons,
        input_feature_dates=dates,
        input_row_fingerprints_sha256=fingerprints,
        input_rows_required=input_rows_required,
        warmup_observations_required=warmup_required,
        warmup_observations_observed=min(warmup_observed, warmup_required),
        window_observations_contiguous=contiguous,
        window_identity_sha256=window_identity,
    )

