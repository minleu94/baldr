"""由已保存 v4 原始列投影精確四均線排列證據。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Literal, NoReturn, cast

from app_module.daily_market_technical_feature_snapshot_v4 import (
    DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES,
    DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_STOCK_CODE_CHARS,
    DailyMarketTechnicalFeatureSnapshotV4,
    TechnicalSessionPinV4,
    validate_daily_market_technical_feature_snapshot_v4,
)
from app_module.daily_market_technical_read_session import DailyMarketTechnicalSourceClockV4
from app_module.daily_market_technical_source import DailyMarketTechnicalSourceRow
from app_module.daily_market_technical_universe_v4_store import (
    daily_market_technical_source_clock_v4_from_dict,
)
from decision_module.factors.selection_technical_rules import TECHNICAL_SOURCE_ID
from decision_module.factors.selection_technical_rules import (
    TechnicalObservedSession,
    technical_session_fingerprint_sha256,
)


DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_EVIDENCE_V1_SCHEMA = (
    "daily-market-technical-ma-alignment-evidence.v1"
)
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1 = "sma_close_alignment_5_10_20_60"
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1 = "1"
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_PERIODS_V1 = (5, 10, 20, 60)
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_COMPARISONS_V1 = ((5, 10), (10, 20), (20, 60))
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_WARMUP_V1 = 60
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_EVIDENCE_BYTES_V1 = 64 * 1024
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_JSON_DEPTH_V1 = 32
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_CLOSE_TEXT_CHARS_V1 = 128
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_RAW_DATE_CHARS_V1 = 64
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_ABS_DECIMAL_EXPONENT_V1 = 128
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_SCALED_INTEGER_DIGITS_V1 = 512
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_CALENDAR_STATUS_V1 = "unknown"
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_SESSION_BASIS_V1 = (
    "verified_observed_source_rows_not_official_trading_calendar"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")
_EVIDENCE_KEYS = frozenset({
    "schema_version",
    "method_id",
    "method_version",
    "stock_code",
    "decision_date",
    "decision_cutoff",
    "feature_date",
    "source_clock",
    "source_clock_sha256",
    "source_id",
    "source_identity",
    "schema_identity_sha256",
    "source_pin_sha256",
    "snapshot_identity_sha256",
    "raw_source_window_fingerprint_sha256",
    "source_window_fingerprint_sha256",
    "calculation_identity_sha256",
    "calculation_version",
    "talib_version",
    "periods",
    "warmup_required_sessions",
    "warmup_observed_sessions",
    "warmup_contiguous",
    "observed_prefix_contiguous",
    "session_basis",
    "official_calendar_completeness",
    "raw_row_refs",
    "common_decimal_exponent",
    "period_close_scaled_sums",
    "comparisons",
    "state",
    "reason_codes",
    "source_available_at",
    "availability_status",
    "historical_pit_eligible",
    "evidence_identity_sha256",
})
_RAW_ROW_REF_KEYS = frozenset({
    "raw_date",
    "feature_date",
    "close_decimal_text",
    "row_fingerprint_sha256",
    "session_fingerprint_sha256",
})
_COMPARISON_KEYS = frozenset({
    "left_period",
    "right_period",
    "left_cross_product",
    "right_cross_product",
    "relation",
})
_UNKNOWN_REASONS = frozenset({
    "ma_alignment_current_session_missing",
    "ma_alignment_current_session_pin_nonunique",
    "ma_alignment_current_row_nonunique",
    "ma_alignment_current_row_pin_mismatch",
    "ma_alignment_raw_row_after_current_session",
    "ma_alignment_source_prefix_not_contiguous",
    "ma_alignment_insufficient_observed_sessions",
    "ma_alignment_tail_session_pin_missing",
    "ma_alignment_tail_session_pin_unverified",
    "ma_alignment_tail_close_missing_or_invalid",
    "ma_alignment_decimal_scale_out_of_bounds",
})

AlignmentStateV1 = Literal["match", "no_match", "unknown"]
ComparisonRelationV1 = Literal["greater", "equal", "less"]


class DailyMarketTechnicalMaAlignmentEvidenceV1Error(ValueError):
    """MA 證據輸入、精確計算或保存格式不符合版本契約。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaRawRowRefV1:
    """一筆觀測列及其原快照指紋；不取代 exact-reader 證明。"""

    raw_date: str
    feature_date: date
    close_decimal_text: str
    row_fingerprint_sha256: str
    session_fingerprint_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_date": self.raw_date,
            "feature_date": self.feature_date.isoformat(),
            "close_decimal_text": self.close_decimal_text,
            "row_fingerprint_sha256": self.row_fingerprint_sha256,
            "session_fingerprint_sha256": self.session_fingerprint_sha256,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaComparisonV1:
    """以共同整數尺度呈現兩個 SMA 的精確交叉乘積比較。"""

    left_period: int
    right_period: int
    left_cross_product: int
    right_cross_product: int
    relation: ComparisonRelationV1

    def to_dict(self) -> dict[str, object]:
        return {
            "left_period": self.left_period,
            "right_period": self.right_period,
            "left_cross_product": self.left_cross_product,
            "right_cross_product": self.right_cross_product,
            "relation": self.relation,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaAlignmentEvidenceV1:
    """獨立、精確且可重新由 exact snapshot 投影核對的排列事實。"""

    stock_code: str
    decision_date: date
    decision_cutoff: datetime
    feature_date: date | None
    source_clock_json: str
    source_clock_sha256: str
    source_id: str
    source_identity: str
    schema_identity_sha256: str
    source_pin_sha256: str
    snapshot_identity_sha256: str
    raw_source_window_fingerprint_sha256: str
    source_window_fingerprint_sha256: str
    calculation_identity_sha256: str
    calculation_version: str
    talib_version: str
    warmup_observed_sessions: int
    warmup_contiguous: bool
    observed_prefix_contiguous: bool
    raw_row_refs: tuple[DailyMarketTechnicalMaRawRowRefV1, ...]
    common_decimal_exponent: int | None
    period_close_scaled_sums: tuple[tuple[int, int], ...]
    comparisons: tuple[DailyMarketTechnicalMaComparisonV1, ...]
    state: AlignmentStateV1
    reason_codes: tuple[str, ...]
    evidence_identity_sha256: str

    @property
    def decision_cutoff_text(self) -> str:
        return self.decision_cutoff.isoformat()

    @property
    def warmup_required_sessions(self) -> int:
        return DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_WARMUP_V1

    @property
    def session_basis(self) -> str:
        return DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_SESSION_BASIS_V1

    @property
    def official_calendar_completeness(self) -> str:
        return DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_CALENDAR_STATUS_V1

    @property
    def source_available_at(self) -> None:
        return None

    @property
    def availability_status(self) -> Literal["unknown"]:
        return "unknown"

    @property
    def historical_pit_eligible(self) -> Literal[False]:
        return False

    def to_dict(self) -> dict[str, object]:
        body = self._body()
        _validate_evidence_body(body)
        identity = _sha256_json(body)
        if identity != self.evidence_identity_sha256:
            _fail("technical_ma_alignment_v1_evidence_identity_mismatch")
        payload = {**body, "evidence_identity_sha256": identity}
        if len(_canonical_json(payload).encode("utf-8")) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_EVIDENCE_BYTES_V1:
            _fail("technical_ma_alignment_v1_evidence_byte_limit")
        return payload

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    @classmethod
    def from_dict(
        cls,
        payload: object,
    ) -> DailyMarketTechnicalMaAlignmentEvidenceV1:
        if not isinstance(payload, Mapping) or set(payload) != _EVIDENCE_KEYS:
            _fail("technical_ma_alignment_v1_evidence_fields_invalid")
        payload_mapping = cast(Mapping[str, object], payload)
        parsed = _parse_evidence_payload(payload_mapping)
        evidence = cls(**parsed)
        if evidence.to_dict() != dict(payload_mapping):
            _fail("technical_ma_alignment_v1_evidence_noncanonical")
        return evidence

    @classmethod
    def from_json(
        cls,
        raw: bytes | str,
    ) -> DailyMarketTechnicalMaAlignmentEvidenceV1:
        text = _decode_json_input(raw)
        _preflight_json_depth(
            text,
            error_code="technical_ma_alignment_v1_evidence_json_depth_limit",
        )
        try:
            payload = json.loads(
                text,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
            if "duplicate_json_key" in str(exc):
                _fail("technical_ma_alignment_v1_evidence_duplicate_key")
            _fail("technical_ma_alignment_v1_evidence_json_invalid", str(exc))
        evidence = cls.from_dict(payload)
        if evidence.to_json() != text:
            _fail("technical_ma_alignment_v1_evidence_noncanonical_json")
        return evidence

    def _body(self) -> dict[str, object]:
        source_clock = _parse_source_clock_json(
            self.source_clock_json,
            expected_sha256=self.source_clock_sha256,
        ).to_dict()
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_EVIDENCE_V1_SCHEMA,
            "method_id": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
            "method_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "feature_date": self.feature_date.isoformat() if self.feature_date else None,
            "source_clock": source_clock,
            "source_clock_sha256": self.source_clock_sha256,
            "source_id": self.source_id,
            "source_identity": self.source_identity,
            "schema_identity_sha256": self.schema_identity_sha256,
            "source_pin_sha256": self.source_pin_sha256,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "raw_source_window_fingerprint_sha256": self.raw_source_window_fingerprint_sha256,
            "source_window_fingerprint_sha256": self.source_window_fingerprint_sha256,
            "calculation_identity_sha256": self.calculation_identity_sha256,
            "calculation_version": self.calculation_version,
            "talib_version": self.talib_version,
            "periods": list(DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_PERIODS_V1),
            "warmup_required_sessions": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_WARMUP_V1,
            "warmup_observed_sessions": self.warmup_observed_sessions,
            "warmup_contiguous": self.warmup_contiguous,
            "observed_prefix_contiguous": self.observed_prefix_contiguous,
            "session_basis": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_SESSION_BASIS_V1,
            "official_calendar_completeness": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_CALENDAR_STATUS_V1,
            "raw_row_refs": [item.to_dict() for item in self.raw_row_refs],
            "common_decimal_exponent": self.common_decimal_exponent,
            "period_close_scaled_sums": [
                {"period": period, "scaled_sum": total}
                for period, total in self.period_close_scaled_sums
            ],
            "comparisons": [item.to_dict() for item in self.comparisons],
            "state": self.state,
            "reason_codes": list(self.reason_codes),
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }


def build_daily_market_technical_ma_alignment_evidence_v1(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    *,
    expected_stock_code: str,
    expected_snapshot_identity_sha256: str,
    expected_source_identity: str,
    expected_source_clock: DailyMarketTechnicalSourceClockV4,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalMaAlignmentEvidenceV1:
    """由 exact-read snapshot 建立 SMA5/10/20/60 排列事實。"""

    _check_cancel(cancel_callback)
    if type(snapshot) is not DailyMarketTechnicalFeatureSnapshotV4:
        _fail("technical_ma_alignment_v1_snapshot_type_invalid")
    try:
        validated_snapshot = validate_daily_market_technical_feature_snapshot_v4(
            snapshot.to_dict()
        )
    except (TypeError, ValueError, OverflowError) as exc:
        _fail("technical_ma_alignment_v1_snapshot_invalid", str(exc))
    _check_cancel(cancel_callback)

    clock_payload = _validated_expected_clock(expected_source_clock)
    clock_json = _canonical_json(clock_payload)
    clock_sha = _sha256_bytes(clock_json.encode("utf-8"))
    if (
        not _is_sha256(expected_snapshot_identity_sha256)
        or not isinstance(expected_source_identity, str)
        or len(expected_source_identity.encode("utf-8")) > 4096
        or not _is_source_identity(expected_source_identity)
        or not isinstance(expected_stock_code, str)
        or _STOCK_CODE_RE.fullmatch(expected_stock_code) is None
    ):
        _fail("technical_ma_alignment_v1_expected_pin_invalid")
    if (
        validated_snapshot.stock_code != expected_stock_code
        or validated_snapshot.snapshot_identity_sha256 != expected_snapshot_identity_sha256
        or validated_snapshot.source_identity != expected_source_identity
        or validated_snapshot.source_clock_sha256 != clock_sha
        or validated_snapshot.source_clock_json != clock_json
        or validated_snapshot.source_id != expected_source_clock.source_id
        or validated_snapshot.schema_identity_sha256 != expected_source_clock.schema_identity_sha256
        or validated_snapshot.source_pin_sha256 != expected_source_clock.source_pin_sha256
        or validated_snapshot.decision_date != expected_source_clock.decision_date
        or validated_snapshot.decision_cutoff != expected_source_clock.decision_cutoff
    ):
        _fail("technical_ma_alignment_v1_current_pin_mismatch")

    base = _base_evidence_fields(validated_snapshot, clock_json, clock_sha)
    current = validated_snapshot.current_session
    if current is None:
        evidence = _issue_evidence(
            **base,
            feature_date=None,
            warmup_observed_sessions=0,
            warmup_contiguous=False,
            raw_row_refs=(),
            common_decimal_exponent=None,
            period_close_scaled_sums=(),
            comparisons=(),
            state="unknown",
            reason_codes=("ma_alignment_current_session_missing",),
        )
        _check_cancel(cancel_callback)
        return evidence

    current_date = current.feature_date
    if current_date > validated_snapshot.decision_date:
        _fail("technical_ma_alignment_v1_future_feature_date")
    pins_by_date: dict[date, list[TechnicalSessionPinV4]] = {}
    for pin in validated_snapshot.session_pins:
        _check_cancel(cancel_callback)
        pins_by_date.setdefault(pin.feature_date, []).append(pin)
    rows_by_date: dict[date, list[DailyMarketTechnicalSourceRow]] = {}
    for row in validated_snapshot.rows:
        _check_cancel(cancel_callback)
        if row.feature_date is not None:
            rows_by_date.setdefault(row.feature_date, []).append(row)

    current_pins = pins_by_date.get(current_date, [])
    if len(current_pins) != 1:
        return _issue_unknown(
            base,
            current_date,
            validated_snapshot.observed_prefix_contiguous,
            "ma_alignment_current_session_pin_nonunique",
            cancel_callback,
        )
    current_rows = rows_by_date.get(current_date, [])
    if len(current_rows) != 1:
        return _issue_unknown(
            base,
            current_date,
            validated_snapshot.observed_prefix_contiguous,
            "ma_alignment_current_row_nonunique",
            cancel_callback,
        )
    current_pin = current_pins[0]
    current_row = current_rows[0]
    if (
        current.stock_code != validated_snapshot.stock_code
        or current.source_identity != validated_snapshot.source_identity
        or current.source_fingerprint_sha256 != current_row.row_fingerprint_sha256
        or current.source_fingerprint_sha256 != current_pin.source_fingerprint_sha256
        or current.pin_verified is not True
        or current_pin.pin_verified is not True
        or technical_session_fingerprint_sha256(current)
        != current_pin.session_fingerprint_sha256
    ):
        _fail("technical_ma_alignment_v1_current_pin_mismatch")

    later_rows = [
        row for row in validated_snapshot.rows
        if row.feature_date is not None and row.feature_date > current_date
    ]
    if later_rows:
        return _issue_unknown(
            base,
            current_date,
            False,
            "ma_alignment_raw_row_after_current_session",
            cancel_callback,
        )
    if not validated_snapshot.observed_prefix_contiguous:
        return _issue_unknown(
            base,
            current_date,
            False,
            "ma_alignment_source_prefix_not_contiguous",
            cancel_callback,
        )

    ordered_rows = tuple(
        row for row in validated_snapshot.rows
        if row.feature_date is not None and row.feature_date <= current_date
    )
    if not ordered_rows or ordered_rows[-1].feature_date != current_date:
        return _issue_unknown(
            base,
            current_date,
            False,
            "ma_alignment_current_row_pin_mismatch",
            cancel_callback,
        )
    if len(ordered_rows) < DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_WARMUP_V1:
        available_refs = _available_unique_tail_refs(
            ordered_rows,
            pins_by_date,
            limit=DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_WARMUP_V1,
        )
        return _issue_unknown(
            base,
            current_date,
            True,
            "ma_alignment_insufficient_observed_sessions",
            cancel_callback,
            raw_row_refs=available_refs,
        )

    tail_rows = ordered_rows[-DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_WARMUP_V1:]
    tail_refs: list[DailyMarketTechnicalMaRawRowRefV1] = []
    decimals: list[Decimal] = []
    for row in tail_rows:
        _check_cancel(cancel_callback)
        if row.feature_date is None:
            return _issue_unknown(
                base,
                current_date,
                False,
                "ma_alignment_source_prefix_not_contiguous",
                cancel_callback,
            )
        date_pins = pins_by_date.get(row.feature_date, [])
        date_rows = rows_by_date.get(row.feature_date, [])
        if len(date_pins) != 1 or len(date_rows) != 1:
            return _issue_unknown(
                base,
                current_date,
                False,
                "ma_alignment_tail_session_pin_missing",
                cancel_callback,
            )
        pin = date_pins[0]
        if pin.pin_verified is not True:
            return _issue_unknown(
                base,
                current_date,
                False,
                "ma_alignment_tail_session_pin_unverified",
                cancel_callback,
            )
        if (
            row.stock_code != validated_snapshot.stock_code
            or row.row_fingerprint_sha256 != pin.source_fingerprint_sha256
        ):
            _fail("technical_ma_alignment_v1_current_pin_mismatch")
        if (
            row.ohlc_valid is not True
            or row.close_price is None
            or not row.close_price.is_finite()
            or row.close_price <= 0
        ):
            return _issue_unknown(
                base,
                current_date,
                False,
                "ma_alignment_tail_close_missing_or_invalid",
                cancel_callback,
            )
        close_text = _canonical_close_text(row.close_price)
        tail_refs.append(DailyMarketTechnicalMaRawRowRefV1(
            raw_date=row.raw_date,
            feature_date=row.feature_date,
            close_decimal_text=close_text,
            row_fingerprint_sha256=row.row_fingerprint_sha256,
            session_fingerprint_sha256=pin.session_fingerprint_sha256,
        ))
        decimals.append(row.close_price)

    if len(tail_refs) != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_WARMUP_V1:
        _fail("technical_ma_alignment_v1_internal_warmup_count_mismatch")
    if any(
        left.feature_date >= right.feature_date
        for left, right in zip(tail_refs, tail_refs[1:])
    ):
        return _issue_unknown(
            base,
            current_date,
            False,
            "ma_alignment_source_prefix_not_contiguous",
            cancel_callback,
        )
    if tail_refs[-1].feature_date != current_date:
        _fail("technical_ma_alignment_v1_current_pin_mismatch")

    scaled_result = _scale_and_sum(decimals)
    if scaled_result is None:
        return _issue_unknown(
            base,
            current_date,
            True,
            "ma_alignment_decimal_scale_out_of_bounds",
            cancel_callback,
            raw_row_refs=tuple(tail_refs),
        )
    exponent, scaled_values = scaled_result
    sums = tuple(
        (period, sum(scaled_values[-period:]))
        for period in DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_PERIODS_V1
    )
    comparisons = _comparisons_from_sums(sums)
    if any(
        len(str(abs(value))) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_SCALED_INTEGER_DIGITS_V1
        for _period, value in sums
    ) or any(
        len(str(abs(value))) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_SCALED_INTEGER_DIGITS_V1
        for item in comparisons
        for value in (item.left_cross_product, item.right_cross_product)
    ):
        return _issue_unknown(
            base,
            current_date,
            True,
            "ma_alignment_decimal_scale_out_of_bounds",
            cancel_callback,
            raw_row_refs=tuple(tail_refs),
        )
    matched = all(item.relation == "greater" for item in comparisons)
    evidence = _issue_evidence(
        **base,
        feature_date=current_date,
        warmup_observed_sessions=DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_WARMUP_V1,
        warmup_contiguous=True,
        raw_row_refs=tuple(tail_refs),
        common_decimal_exponent=exponent,
        period_close_scaled_sums=sums,
        comparisons=comparisons,
        state="match" if matched else "no_match",
        reason_codes=(
            "ma_alignment_strictly_descending"
            if matched else "ma_alignment_not_strictly_descending",
        ),
    )
    _check_cancel(cancel_callback)
    return evidence


def verify_daily_market_technical_ma_alignment_evidence_v1(
    evidence: DailyMarketTechnicalMaAlignmentEvidenceV1,
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    *,
    expected_stock_code: str,
    expected_snapshot_identity_sha256: str,
    expected_source_identity: str,
    expected_source_clock: DailyMarketTechnicalSourceClockV4,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalMaAlignmentEvidenceV1:
    """以 exact-read snapshot 重建並比對完整 evidence，不信任自簽 identity。"""

    if type(evidence) is not DailyMarketTechnicalMaAlignmentEvidenceV1:
        _fail("technical_ma_alignment_v1_evidence_type_invalid")
    try:
        supplied = evidence.to_dict()
    except (TypeError, ValueError, OverflowError) as exc:
        _fail("technical_ma_alignment_v1_evidence_invalid", str(exc))
    rebuilt = build_daily_market_technical_ma_alignment_evidence_v1(
        snapshot,
        expected_stock_code=expected_stock_code,
        expected_snapshot_identity_sha256=expected_snapshot_identity_sha256,
        expected_source_identity=expected_source_identity,
        expected_source_clock=expected_source_clock,
        cancel_callback=cancel_callback,
    )
    if supplied != rebuilt.to_dict():
        _fail("technical_ma_alignment_v1_reader_projection_mismatch")
    return rebuilt


def _base_evidence_fields(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    clock_json: str,
    clock_sha: str,
) -> dict[str, Any]:
    return {
        "stock_code": snapshot.stock_code,
        "decision_date": snapshot.decision_date,
        "decision_cutoff": snapshot.decision_cutoff,
        "source_clock_json": clock_json,
        "source_clock_sha256": clock_sha,
        "source_id": snapshot.source_id,
        "source_identity": snapshot.source_identity,
        "schema_identity_sha256": snapshot.schema_identity_sha256,
        "source_pin_sha256": snapshot.source_pin_sha256,
        "snapshot_identity_sha256": snapshot.snapshot_identity_sha256,
        "raw_source_window_fingerprint_sha256": snapshot.raw_source_window_fingerprint_sha256,
        "source_window_fingerprint_sha256": snapshot.source_window_fingerprint_sha256,
        "calculation_identity_sha256": snapshot.calculation_identity_sha256,
        "calculation_version": snapshot.calculation_version,
        "talib_version": snapshot.talib_version,
        "observed_prefix_contiguous": snapshot.observed_prefix_contiguous,
    }


def _available_unique_tail_refs(
    rows: Sequence[object],
    pins_by_date: Mapping[date, Sequence[object]],
    *,
    limit: int,
) -> tuple[DailyMarketTechnicalMaRawRowRefV1, ...]:
    result: list[DailyMarketTechnicalMaRawRowRefV1] = []
    seen_dates: set[date] = set()
    for row in rows[-limit:]:
        feature_date = getattr(row, "feature_date", None)
        if not isinstance(feature_date, date) or isinstance(feature_date, datetime):
            continue
        pins = pins_by_date.get(feature_date, ())
        if len(pins) != 1 or feature_date in seen_dates:
            continue
        pin = pins[0]
        if (
            getattr(row, "stock_code", None) is None
            or getattr(row, "row_fingerprint_sha256", None)
            != getattr(pin, "source_fingerprint_sha256", None)
            or getattr(pin, "pin_verified", False) is not True
        ):
            continue
        close = getattr(row, "close_price", None)
        close_text = None
        if isinstance(close, Decimal) and close.is_finite() and close > 0:
            try:
                close_text = _canonical_close_text(close)
            except DailyMarketTechnicalMaAlignmentEvidenceV1Error:
                close_text = None
        if close_text is None:
            continue
        result.append(DailyMarketTechnicalMaRawRowRefV1(
            raw_date=cast(str, getattr(row, "raw_date")),
            feature_date=feature_date,
            close_decimal_text=close_text,
            row_fingerprint_sha256=cast(str, getattr(row, "row_fingerprint_sha256")),
            session_fingerprint_sha256=cast(str, getattr(pin, "session_fingerprint_sha256")),
        ))
        seen_dates.add(feature_date)
    return tuple(result)


def _issue_unknown(
    base: Mapping[str, Any],
    feature_date: date | None,
    warmup_contiguous: bool,
    reason: str,
    cancel_callback: Callable[[], bool] | None,
    *,
    raw_row_refs: tuple[DailyMarketTechnicalMaRawRowRefV1, ...] = (),
) -> DailyMarketTechnicalMaAlignmentEvidenceV1:
    evidence = _issue_evidence(
        **dict(base),
        feature_date=feature_date,
        warmup_observed_sessions=len(raw_row_refs),
        warmup_contiguous=warmup_contiguous,
        raw_row_refs=raw_row_refs,
        common_decimal_exponent=None,
        period_close_scaled_sums=(),
        comparisons=(),
        state="unknown",
        reason_codes=(reason,),
    )
    _check_cancel(cancel_callback)
    return evidence


def _issue_evidence(
    *,
    stock_code: str,
    decision_date: date,
    decision_cutoff: datetime,
    source_clock_json: str,
    source_clock_sha256: str,
    source_id: str,
    source_identity: str,
    schema_identity_sha256: str,
    source_pin_sha256: str,
    snapshot_identity_sha256: str,
    raw_source_window_fingerprint_sha256: str,
    source_window_fingerprint_sha256: str,
    calculation_identity_sha256: str,
    calculation_version: str,
    talib_version: str,
    observed_prefix_contiguous: bool,
    feature_date: date | None,
    warmup_observed_sessions: int,
    warmup_contiguous: bool,
    raw_row_refs: tuple[DailyMarketTechnicalMaRawRowRefV1, ...],
    common_decimal_exponent: int | None,
    period_close_scaled_sums: tuple[tuple[int, int], ...],
    comparisons: tuple[DailyMarketTechnicalMaComparisonV1, ...],
    state: AlignmentStateV1,
    reason_codes: tuple[str, ...],
) -> DailyMarketTechnicalMaAlignmentEvidenceV1:
    draft = DailyMarketTechnicalMaAlignmentEvidenceV1(
        stock_code=stock_code,
        decision_date=decision_date,
        decision_cutoff=decision_cutoff,
        feature_date=feature_date,
        source_clock_json=source_clock_json,
        source_clock_sha256=source_clock_sha256,
        source_id=source_id,
        source_identity=source_identity,
        schema_identity_sha256=schema_identity_sha256,
        source_pin_sha256=source_pin_sha256,
        snapshot_identity_sha256=snapshot_identity_sha256,
        raw_source_window_fingerprint_sha256=raw_source_window_fingerprint_sha256,
        source_window_fingerprint_sha256=source_window_fingerprint_sha256,
        calculation_identity_sha256=calculation_identity_sha256,
        calculation_version=calculation_version,
        talib_version=talib_version,
        warmup_observed_sessions=warmup_observed_sessions,
        warmup_contiguous=warmup_contiguous,
        observed_prefix_contiguous=observed_prefix_contiguous,
        raw_row_refs=raw_row_refs,
        common_decimal_exponent=common_decimal_exponent,
        period_close_scaled_sums=period_close_scaled_sums,
        comparisons=comparisons,
        state=state,
        reason_codes=reason_codes,
        evidence_identity_sha256="",
    )
    body = draft._body()
    _validate_evidence_body(body)
    return DailyMarketTechnicalMaAlignmentEvidenceV1.from_dict({
        **body,
        "evidence_identity_sha256": _sha256_json(body),
    })


def _validate_evidence_body(value: Mapping[str, object]) -> None:
    if set(value) != _EVIDENCE_KEYS - {"evidence_identity_sha256"}:
        _fail("technical_ma_alignment_v1_evidence_fields_invalid")
    if (
        value.get("schema_version") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_EVIDENCE_V1_SCHEMA
        or value.get("method_id") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1
        or value.get("method_version") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1
        or value.get("periods") != list(DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_PERIODS_V1)
        or value.get("warmup_required_sessions") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_WARMUP_V1
        or value.get("session_basis") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_SESSION_BASIS_V1
        or value.get("official_calendar_completeness") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_CALENDAR_STATUS_V1
        or value.get("source_available_at") is not None
        or value.get("availability_status") != "unknown"
        or value.get("historical_pit_eligible") is not False
    ):
        _fail("technical_ma_alignment_v1_method_or_policy_invalid")
    stock_code = value.get("stock_code")
    if not isinstance(stock_code, str) or _STOCK_CODE_RE.fullmatch(stock_code) is None:
        _fail("technical_ma_alignment_v1_stock_invalid")
    decision_date = _parse_date(value.get("decision_date"), "decision_date")
    decision_cutoff = _parse_aware_datetime(value.get("decision_cutoff"), "decision_cutoff")
    feature_date_value = value.get("feature_date")
    feature_date = (
        None if feature_date_value is None else _parse_date(feature_date_value, "feature_date")
    )
    if feature_date is not None and feature_date > decision_date:
        _fail("technical_ma_alignment_v1_future_feature_date")
    clock_value = value.get("source_clock")
    if not isinstance(clock_value, Mapping):
        _fail("technical_ma_alignment_v1_source_clock_invalid")
    clock = daily_market_technical_source_clock_v4_from_dict(clock_value)
    source_clock_sha = _require_sha(value.get("source_clock_sha256"), "source_clock_sha256")
    if clock.identity_sha256 != source_clock_sha:
        _fail("technical_ma_alignment_v1_source_clock_identity_mismatch")
    if (
        clock.decision_date != decision_date
        or clock.decision_cutoff != decision_cutoff
        or clock.source_id != value.get("source_id")
        or clock.schema_identity_sha256 != value.get("schema_identity_sha256")
        or clock.source_pin_sha256 != value.get("source_pin_sha256")
    ):
        _fail("technical_ma_alignment_v1_source_clock_binding_mismatch")
    for field_name in (
        "schema_identity_sha256",
        "source_pin_sha256",
        "snapshot_identity_sha256",
        "raw_source_window_fingerprint_sha256",
        "source_window_fingerprint_sha256",
        "calculation_identity_sha256",
    ):
        _require_sha(value.get(field_name), field_name)
    source_identity = value.get("source_identity")
    if (
        not isinstance(source_identity, str)
        or len(source_identity.encode("utf-8")) > 4096
        or not _is_source_identity(source_identity)
    ):
        _fail("technical_ma_alignment_v1_source_identity_invalid")
    if (
        not isinstance(value.get("calculation_version"), str)
        or not value["calculation_version"]
        or len(cast(str, value["calculation_version"]).encode("utf-8")) > 128
        or not isinstance(value.get("talib_version"), str)
        or not value["talib_version"]
        or len(cast(str, value["talib_version"]).encode("utf-8")) > 128
    ):
        _fail("technical_ma_alignment_v1_calculation_lineage_invalid")
    for boolean_name in (
        "warmup_contiguous",
        "observed_prefix_contiguous",
    ):
        if type(value.get(boolean_name)) is not bool:
            _fail("technical_ma_alignment_v1_contiguity_flag_invalid")
    if value.get("warmup_contiguous") is True and value.get("observed_prefix_contiguous") is not True:
        _fail("technical_ma_alignment_v1_contiguity_flag_mismatch")
    warmup_observed = value.get("warmup_observed_sessions")
    if type(warmup_observed) is not int or not 0 <= warmup_observed <= 60:
        _fail("technical_ma_alignment_v1_warmup_count_invalid")
    raw_refs_value = value.get("raw_row_refs")
    if not isinstance(raw_refs_value, list) or len(raw_refs_value) > 60:
        _fail("technical_ma_alignment_v1_raw_refs_invalid")
    raw_refs = tuple(
        _raw_ref_from_dict(item) for item in cast(list[object], raw_refs_value)
    )
    if warmup_observed != len(raw_refs):
        _fail("technical_ma_alignment_v1_warmup_count_mismatch")
    if feature_date is None and raw_refs:
        _fail("technical_ma_alignment_v1_feature_date_missing")
    if feature_date is not None and any(item.feature_date > feature_date for item in raw_refs):
        _fail("technical_ma_alignment_v1_raw_ref_after_feature_date")

    state = value.get("state")
    reason_codes_value = value.get("reason_codes")
    if (
        state not in {"match", "no_match", "unknown"}
        or not isinstance(reason_codes_value, list)
        or not 1 <= len(reason_codes_value) <= 4
        or any(not isinstance(item, str) or len(item) > 128 for item in reason_codes_value)
        or len(set(cast(list[str], reason_codes_value))) != len(reason_codes_value)
    ):
        _fail("technical_ma_alignment_v1_state_or_reasons_invalid")
    reason_codes = cast(list[str], reason_codes_value)
    sums_value = value.get("period_close_scaled_sums")
    comparisons_value = value.get("comparisons")
    exponent_value = value.get("common_decimal_exponent")
    if state == "unknown":
        if (
            len(reason_codes) != 1
            or reason_codes[0] not in _UNKNOWN_REASONS
            or sums_value != []
            or comparisons_value != []
            or exponent_value is not None
        ):
            _fail("technical_ma_alignment_v1_unknown_payload_invalid")
    else:
        if (
            reason_codes != [
                "ma_alignment_strictly_descending"
                if state == "match" else "ma_alignment_not_strictly_descending"
            ]
            or feature_date is None
            or len(raw_refs) != 60
            or raw_refs[-1].feature_date != feature_date
            or warmup_observed != 60
            or value.get("warmup_contiguous") is not True
            or value.get("observed_prefix_contiguous") is not True
            or type(exponent_value) is not int
            or not -DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_ABS_DECIMAL_EXPONENT_V1
                <= cast(int, exponent_value)
                <= DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_ABS_DECIMAL_EXPONENT_V1
        ):
            _fail("technical_ma_alignment_v1_computed_payload_invalid")
        _validate_computed_payload(
            raw_refs=raw_refs,
            exponent=cast(int, exponent_value),
            sums_value=sums_value,
            comparisons_value=comparisons_value,
            state=cast(AlignmentStateV1, state),
        )


def _validate_computed_payload(
    *,
    raw_refs: tuple[DailyMarketTechnicalMaRawRowRefV1, ...],
    exponent: int,
    sums_value: object,
    comparisons_value: object,
    state: AlignmentStateV1,
) -> None:
    if not isinstance(sums_value, list) or len(sums_value) != 4:
        _fail("technical_ma_alignment_v1_period_sums_invalid")
    if not isinstance(comparisons_value, list) or len(comparisons_value) != 3:
        _fail("technical_ma_alignment_v1_comparisons_invalid")
    closes = tuple(_parse_close_text(item.close_decimal_text) for item in raw_refs)
    if any(left.feature_date >= right.feature_date for left, right in zip(raw_refs, raw_refs[1:])):
        _fail("technical_ma_alignment_v1_raw_ref_order_invalid")
    scale = _scale_and_sum(closes)
    if scale is None or scale[0] != exponent:
        _fail("technical_ma_alignment_v1_decimal_scale_invalid")
    scaled_values = scale[1]
    expected_sums = tuple(
        (period, sum(scaled_values[-period:]))
        for period in DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_PERIODS_V1
    )
    parsed_sums: list[tuple[int, int]] = []
    for index, item in enumerate(cast(list[object], sums_value)):
        if not isinstance(item, Mapping) or set(item) != {"period", "scaled_sum"}:
            _fail("technical_ma_alignment_v1_period_sum_fields_invalid")
        item_mapping = cast(Mapping[str, object], item)
        period = item_mapping.get("period")
        total = item_mapping.get("scaled_sum")
        if (
            type(period) is not int
            or type(total) is not int
            or len(str(abs(total))) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_SCALED_INTEGER_DIGITS_V1
            or period != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_PERIODS_V1[index]
        ):
            _fail("technical_ma_alignment_v1_period_sum_invalid")
        parsed_sums.append((period, total))
    if tuple(parsed_sums) != expected_sums:
        _fail("technical_ma_alignment_v1_period_sum_mismatch")
    expected_comparisons = _comparisons_from_sums(expected_sums)
    parsed_comparisons = tuple(
        _comparison_from_dict(item)
        for item in cast(list[object], comparisons_value)
    )
    if parsed_comparisons != expected_comparisons:
        _fail("technical_ma_alignment_v1_comparison_mismatch")
    expected_state: AlignmentStateV1 = (
        "match"
        if all(item.relation == "greater" for item in expected_comparisons)
        else "no_match"
    )
    if state != expected_state:
        _fail("technical_ma_alignment_v1_state_mismatch")


def _raw_ref_from_dict(value: object) -> DailyMarketTechnicalMaRawRowRefV1:
    if not isinstance(value, Mapping) or set(value) != _RAW_ROW_REF_KEYS:
        _fail("technical_ma_alignment_v1_raw_ref_fields_invalid")
    raw_mapping = cast(Mapping[str, object], value)
    raw_date = raw_mapping.get("raw_date")
    close_text = raw_mapping.get("close_decimal_text")
    if (
        not isinstance(raw_date, str)
        or not raw_date
        or len(raw_date.encode("utf-8")) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_RAW_DATE_CHARS_V1
        or not isinstance(close_text, str)
        or len(close_text) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_CLOSE_TEXT_CHARS_V1
    ):
        _fail("technical_ma_alignment_v1_raw_ref_value_invalid")
    parsed_close = _parse_close_text(close_text)
    if parsed_close <= 0:
        _fail("technical_ma_alignment_v1_raw_close_nonpositive")
    return DailyMarketTechnicalMaRawRowRefV1(
        raw_date=raw_date,
        feature_date=_parse_date(raw_mapping.get("feature_date"), "raw_ref_date"),
        close_decimal_text=close_text,
        row_fingerprint_sha256=_require_sha(raw_mapping.get("row_fingerprint_sha256"), "row_fingerprint_sha256"),
        session_fingerprint_sha256=_require_sha(raw_mapping.get("session_fingerprint_sha256"), "session_fingerprint_sha256"),
    )


def _comparison_from_dict(value: object) -> DailyMarketTechnicalMaComparisonV1:
    if not isinstance(value, Mapping) or set(value) != _COMPARISON_KEYS:
        _fail("technical_ma_alignment_v1_comparison_fields_invalid")
    comparison_mapping = cast(Mapping[str, object], value)
    left = comparison_mapping.get("left_period")
    right = comparison_mapping.get("right_period")
    left_product = comparison_mapping.get("left_cross_product")
    right_product = comparison_mapping.get("right_cross_product")
    relation = comparison_mapping.get("relation")
    if (
        type(left) is not int
        or type(right) is not int
        or type(left_product) is not int
        or type(right_product) is not int
        or len(str(abs(cast(int, left_product)))) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_SCALED_INTEGER_DIGITS_V1
        or len(str(abs(cast(int, right_product)))) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_SCALED_INTEGER_DIGITS_V1
        or relation not in {"greater", "equal", "less"}
    ):
        _fail("technical_ma_alignment_v1_comparison_invalid")
    expected_relation = _relation(cast(int, left_product), cast(int, right_product))
    if relation != expected_relation:
        _fail("technical_ma_alignment_v1_comparison_relation_invalid")
    return DailyMarketTechnicalMaComparisonV1(
        left_period=cast(int, left),
        right_period=cast(int, right),
        left_cross_product=cast(int, left_product),
        right_cross_product=cast(int, right_product),
        relation=cast(ComparisonRelationV1, relation),
    )


def _parse_evidence_payload(value: Mapping[str, object]) -> dict[str, Any]:
    _validate_evidence_body({key: item for key, item in value.items() if key != "evidence_identity_sha256"})
    identity = _require_sha(value.get("evidence_identity_sha256"), "evidence_identity_sha256")
    body = {key: item for key, item in value.items() if key != "evidence_identity_sha256"}
    if _sha256_json(body) != identity:
        _fail("technical_ma_alignment_v1_evidence_identity_mismatch")
    clock = _parse_source_clock_mapping(value.get("source_clock"), value.get("source_clock_sha256"))
    raw_refs_value = cast(list[object], value["raw_row_refs"])
    sums_value = cast(list[object], value["period_close_scaled_sums"])
    comparisons_value = cast(list[object], value["comparisons"])
    feature_date = (
        None if value.get("feature_date") is None
        else _parse_date(value.get("feature_date"), "feature_date")
    )
    return {
        "stock_code": cast(str, value["stock_code"]),
        "decision_date": _parse_date(value["decision_date"], "decision_date"),
        "decision_cutoff": _parse_aware_datetime(value["decision_cutoff"], "decision_cutoff"),
        "feature_date": feature_date,
        "source_clock_json": _canonical_json(clock.to_dict()),
        "source_clock_sha256": cast(str, value["source_clock_sha256"]),
        "source_id": cast(str, value["source_id"]),
        "source_identity": cast(str, value["source_identity"]),
        "schema_identity_sha256": cast(str, value["schema_identity_sha256"]),
        "source_pin_sha256": cast(str, value["source_pin_sha256"]),
        "snapshot_identity_sha256": cast(str, value["snapshot_identity_sha256"]),
        "raw_source_window_fingerprint_sha256": cast(str, value["raw_source_window_fingerprint_sha256"]),
        "source_window_fingerprint_sha256": cast(str, value["source_window_fingerprint_sha256"]),
        "calculation_identity_sha256": cast(str, value["calculation_identity_sha256"]),
        "calculation_version": cast(str, value["calculation_version"]),
        "talib_version": cast(str, value["talib_version"]),
        "warmup_observed_sessions": cast(int, value["warmup_observed_sessions"]),
        "warmup_contiguous": cast(bool, value["warmup_contiguous"]),
        "observed_prefix_contiguous": cast(bool, value["observed_prefix_contiguous"]),
        "raw_row_refs": tuple(_raw_ref_from_dict(item) for item in raw_refs_value),
        "common_decimal_exponent": cast(int | None, value["common_decimal_exponent"]),
        "period_close_scaled_sums": tuple(
            (cast(int, item["period"]), cast(int, item["scaled_sum"]))
            for item in cast(list[Mapping[str, object]], sums_value)
        ),
        "comparisons": tuple(_comparison_from_dict(item) for item in comparisons_value),
        "state": cast(AlignmentStateV1, value["state"]),
        "reason_codes": tuple(cast(list[str], value["reason_codes"])),
        "evidence_identity_sha256": identity,
    }


def _parse_source_clock_json(
    raw: str,
    *,
    expected_sha256: str,
) -> DailyMarketTechnicalSourceClockV4:
    if not isinstance(raw, str):
        _fail("technical_ma_alignment_v1_source_clock_invalid")
    try:
        encoded = raw.encode("utf-8")
    except UnicodeEncodeError as exc:
        _fail("technical_ma_alignment_v1_source_clock_invalid", str(exc))
    if len(encoded) > 8192:
        _fail("technical_ma_alignment_v1_source_clock_invalid")
    _preflight_json_depth(
        raw,
        error_code="technical_ma_alignment_v1_source_clock_json_depth_limit",
    )
    try:
        payload = json.loads(
            raw,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
        if "duplicate_json_key" in str(exc):
            _fail("technical_ma_alignment_v1_source_clock_duplicate_key")
        _fail("technical_ma_alignment_v1_source_clock_invalid", str(exc))
    clock = _parse_source_clock_mapping(payload, expected_sha256)
    if _canonical_json(clock.to_dict()) != raw:
        _fail("technical_ma_alignment_v1_source_clock_noncanonical")
    return clock


def _parse_source_clock_mapping(
    payload: object,
    expected_sha256: object,
) -> DailyMarketTechnicalSourceClockV4:
    if not isinstance(payload, Mapping):
        _fail("technical_ma_alignment_v1_source_clock_invalid")
    try:
        clock = daily_market_technical_source_clock_v4_from_dict(payload)
    except (TypeError, ValueError) as exc:
        _fail("technical_ma_alignment_v1_source_clock_invalid", str(exc))
    expected = _require_sha(expected_sha256, "source_clock_sha256")
    if clock.identity_sha256 != expected:
        _fail("technical_ma_alignment_v1_source_clock_identity_mismatch")
    return clock


def _validated_expected_clock(
    value: DailyMarketTechnicalSourceClockV4,
) -> dict[str, object]:
    if type(value) is not DailyMarketTechnicalSourceClockV4:
        _fail("technical_ma_alignment_v1_expected_clock_invalid")
    try:
        payload = value.to_dict()
        clock = daily_market_technical_source_clock_v4_from_dict(payload)
    except (TypeError, ValueError) as exc:
        _fail("technical_ma_alignment_v1_expected_clock_invalid", str(exc))
    if clock.identity_sha256 != value.identity_sha256:
        _fail("technical_ma_alignment_v1_expected_clock_identity_mismatch")
    return clock.to_dict()


def _scale_and_sum(
    decimals: Sequence[Decimal],
) -> tuple[int, tuple[int, ...]] | None:
    if not decimals:
        return None
    parts: list[tuple[int, tuple[int, ...], int]] = []
    for value in decimals:
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            return None
        sign, digits, exponent = value.as_tuple()
        if (
            sign != 0
            or not isinstance(exponent, int)
            or abs(exponent) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_ABS_DECIMAL_EXPONENT_V1
            or not digits
            or len(digits) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_CLOSE_TEXT_CHARS_V1
        ):
            return None
        parts.append((sign, digits, exponent))
    common_exponent = min(item[2] for item in parts)
    max_shift = max(item[2] - common_exponent for item in parts)
    if max_shift > 2 * DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_ABS_DECIMAL_EXPONENT_V1:
        return None
    scaled: list[int] = []
    for _sign, digits, exponent in parts:
        coefficient = int("".join(str(item) for item in digits))
        shift = exponent - common_exponent
        value = coefficient * (10 ** shift)
        if len(str(abs(value))) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_SCALED_INTEGER_DIGITS_V1:
            return None
        scaled.append(value)
    return common_exponent, tuple(scaled)


def _comparisons_from_sums(
    sums: Sequence[tuple[int, int]],
) -> tuple[DailyMarketTechnicalMaComparisonV1, ...]:
    by_period = dict(sums)
    if tuple(by_period) != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_PERIODS_V1:
        _fail("technical_ma_alignment_v1_period_sums_invalid")
    results: list[DailyMarketTechnicalMaComparisonV1] = []
    for left, right in DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_COMPARISONS_V1:
        left_product = by_period[left] * right
        right_product = by_period[right] * left
        results.append(DailyMarketTechnicalMaComparisonV1(
            left_period=left,
            right_period=right,
            left_cross_product=left_product,
            right_cross_product=right_product,
            relation=_relation(left_product, right_product),
        ))
    return tuple(results)


def _relation(left: int, right: int) -> ComparisonRelationV1:
    if left > right:
        return "greater"
    if left < right:
        return "less"
    return "equal"


def _canonical_close_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        _fail("technical_ma_alignment_v1_close_text_invalid")
    _sign, digits, exponent = value.as_tuple()
    if (
        not isinstance(exponent, int)
        or abs(exponent) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_ABS_DECIMAL_EXPONENT_V1
        or not digits
        or len(digits) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_CLOSE_TEXT_CHARS_V1
    ):
        _fail("technical_ma_alignment_v1_decimal_scale_out_of_bounds")
    try:
        rendered = format(value, "f")
    except (InvalidOperation, ValueError) as exc:
        _fail("technical_ma_alignment_v1_close_text_invalid", str(exc))
    if len(rendered) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_CLOSE_TEXT_CHARS_V1:
        _fail("technical_ma_alignment_v1_decimal_scale_out_of_bounds")
    return rendered


def _parse_close_text(value: str) -> Decimal:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_CLOSE_TEXT_CHARS_V1
    ):
        _fail("technical_ma_alignment_v1_close_text_invalid")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        _fail("technical_ma_alignment_v1_close_text_invalid", str(exc))
    if not parsed.is_finite() or parsed <= 0:
        _fail("technical_ma_alignment_v1_close_text_invalid")
    _sign, digits, exponent = parsed.as_tuple()
    if (
        not isinstance(exponent, int)
        or abs(exponent) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_ABS_DECIMAL_EXPONENT_V1
        or not digits
        or len(digits) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_CLOSE_TEXT_CHARS_V1
    ):
        _fail("technical_ma_alignment_v1_decimal_scale_out_of_bounds")
    if format(parsed, "f") != value:
        _fail("technical_ma_alignment_v1_close_text_invalid")
    return parsed


def _parse_date(value: object, name: str) -> date:
    if not isinstance(value, str):
        _fail(f"technical_ma_alignment_v1_{name}_invalid")
    date_text = cast(str, value)
    try:
        parsed = date.fromisoformat(date_text)
    except ValueError as exc:
        _fail(f"technical_ma_alignment_v1_{name}_invalid", str(exc))
    if parsed.isoformat() != date_text:
        _fail(f"technical_ma_alignment_v1_{name}_noncanonical")
    return parsed


def _parse_aware_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        _fail(f"technical_ma_alignment_v1_{name}_invalid")
    datetime_text = cast(str, value)
    try:
        parsed = datetime.fromisoformat(datetime_text)
    except ValueError as exc:
        _fail(f"technical_ma_alignment_v1_{name}_invalid", str(exc))
    if parsed.utcoffset() is None or parsed.isoformat() != datetime_text:
        _fail(f"technical_ma_alignment_v1_{name}_noncanonical")
    return parsed


def _decode_json_input(raw: bytes | str) -> str:
    if isinstance(raw, bytes):
        if len(raw) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_EVIDENCE_BYTES_V1:
            _fail("technical_ma_alignment_v1_evidence_byte_limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            _fail("technical_ma_alignment_v1_evidence_json_invalid", str(exc))
    elif isinstance(raw, str):
        try:
            encoded = raw.encode("utf-8")
        except UnicodeEncodeError as exc:
            _fail("technical_ma_alignment_v1_evidence_json_invalid", str(exc))
        if len(encoded) > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_EVIDENCE_BYTES_V1:
            _fail("technical_ma_alignment_v1_evidence_byte_limit")
        text = raw
    else:
        _fail("technical_ma_alignment_v1_evidence_json_invalid")
    return text


def _preflight_json_depth(text: str, *, error_code: str) -> None:
    """在解析前有界掃描 JSON 結構，字串中的括號不計入巢狀深度。"""

    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_JSON_DEPTH_V1:
                _fail(error_code)
        elif character in "]}" and depth > 0:
            depth -= 1


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"json_constant_rejected:{value}")


def _require_sha(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(f"technical_ma_alignment_v1_{name}_invalid")
    return cast(str, value)


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _is_source_identity(value: str) -> bool:
    prefix = f"{TECHNICAL_SOURCE_ID}:"
    return value.startswith(prefix) and _is_sha256(value[len(prefix):])


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_json(value: object) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _check_cancel(callback: Callable[[], bool] | None) -> None:
    if callback is None:
        return
    try:
        result = callback()
    except Exception as exc:
        _fail("technical_ma_alignment_v1_cancel_callback_failed", str(exc))
    if type(result) is not bool:
        _fail("technical_ma_alignment_v1_cancel_callback_invalid")
    if result:
        _fail("technical_ma_alignment_v1_cancelled")


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalMaAlignmentEvidenceV1Error(code, message or code)
