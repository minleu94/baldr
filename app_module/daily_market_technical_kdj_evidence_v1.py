"""由保存的技術快照推導 KDJ 9/3/3 SMA 方法證據。

此模組是純計算 leaf：不讀取或重開資料來源、不連接 SQLite，也不發布
reader-qualified 資格。快照內的 SHA-256 只用於追溯內容，不能取代 F17 exact
reader observer 的來源核驗。
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
from typing import Literal

from app_module.daily_market_technical_feature_snapshot_v4 import (
    DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS,
    DailyMarketTechnicalFeatureSnapshotV4,
)
from app_module.daily_market_technical_source import DailyMarketTechnicalSourceRow


KDJ_EVIDENCE_SCHEMA_V1 = "daily-market-technical-kdj-evidence.v1"
KDJ_METHOD_ID_V1 = "daily_market.kdj_kd_golden_cross_9_3_3_sma"
KDJ_METHOD_VERSION_V1 = "kdj-sma.v1"
KDJ_DECIMAL_PRECISION_V1 = 34
KDJ_DECIMAL_ROUNDING_V1 = "ROUND_HALF_EVEN"
KDJ_DECIMAL_EMIN_V1 = -6143
KDJ_DECIMAL_EMAX_V1 = 6144
KDJ_DECIMAL_CLAMP_V1 = 0
KDJ_WARMUP_REQUIRED_SESSIONS_V1 = 14
_TRAPPED_SIGNALS_V1 = frozenset({
    DivisionByZero,
    FloatOperation,
    InvalidOperation,
    Overflow,
})
_DECIMAL_TRAPPED_SIGNAL_NAMES_V1 = (
    "DivisionByZero",
    "FloatOperation",
    "InvalidOperation",
    "Overflow",
)

_METHOD_PARAMETERS_V1: dict[str, object] = {
    "rsv_window": 9,
    "k_smoothing": "SMA_3",
    "d_smoothing": "SMA_3",
    "j_formula": "3*K-2*D",
    "cross_predicate": "current_K>current_D_and_previous_K<=previous_D",
    "decimal_precision": KDJ_DECIMAL_PRECISION_V1,
    "decimal_rounding": KDJ_DECIMAL_ROUNDING_V1,
    "decimal_emin": KDJ_DECIMAL_EMIN_V1,
    "decimal_emax": KDJ_DECIMAL_EMAX_V1,
    "decimal_clamp": KDJ_DECIMAL_CLAMP_V1,
    "decimal_trapped_signals": _DECIMAL_TRAPPED_SIGNAL_NAMES_V1,
    "warmup_required_sessions": KDJ_WARMUP_REQUIRED_SESSIONS_V1,
}


class DailyMarketTechnicalKDJError(ValueError):
    """KDJ 輸入或版本契約無效；`code` 可供呼叫端穩定判讀。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalKDJDayV1:
    """單一觀測日的 KDJ 數值；J 不限制在 0–100。"""

    feature_date: date
    source_row_fingerprint_sha256: str
    rsv: Decimal
    k: Decimal
    d: Decimal
    j: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "feature_date": self.feature_date.isoformat(),
            "source_row_fingerprint_sha256": self.source_row_fingerprint_sha256,
            "rsv": _decimal_text(self.rsv),
            "k": _decimal_text(self.k),
            "d": _decimal_text(self.d),
            "j": _decimal_text(self.j),
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalKDJEvidenceV1:
    """保存來源衍生的單股 KDJ 證據，不代表 reader qualification。"""

    stock_code: str
    decision_date: date
    decision_cutoff: datetime
    source_id: str
    source_identity: str
    source_clock_sha256: str
    source_pin_sha256: str
    raw_source_window_fingerprint_sha256: str
    snapshot_identity_sha256: str
    state: Literal["match", "no_match", "unknown"]
    reason_codes: tuple[str, ...]
    previous: DailyMarketTechnicalKDJDayV1 | None
    current: DailyMarketTechnicalKDJDayV1 | None
    input_feature_dates: tuple[date | None, ...]
    input_row_fingerprints_sha256: tuple[str, ...]
    warmup_required_sessions: int
    warmup_observed_sessions: int
    warmup_contiguous: bool
    observed_prefix_contiguous: bool
    availability_status: Literal["unknown"] = "unknown"
    source_available_at: None = None
    historical_pit_eligible: Literal[False] = False
    reader_qualified: Literal[False] = False
    method_id: str = KDJ_METHOD_ID_V1
    method_version: str = KDJ_METHOD_VERSION_V1
    decimal_precision: int = KDJ_DECIMAL_PRECISION_V1
    decimal_rounding: str = KDJ_DECIMAL_ROUNDING_V1

    def _payload(self) -> dict[str, object]:
        if (
            self.availability_status != "unknown"
            or self.source_available_at is not None
            or self.historical_pit_eligible is not False
            or self.reader_qualified is not False
            or self.method_id != KDJ_METHOD_ID_V1
            or self.method_version != KDJ_METHOD_VERSION_V1
            or self.decimal_precision != KDJ_DECIMAL_PRECISION_V1
            or self.decimal_rounding != KDJ_DECIMAL_ROUNDING_V1
        ):
            raise DailyMarketTechnicalKDJError("kdj_evidence_contract_invalid")
        if self.state == "unknown":
            if not self.reason_codes or self.previous is not None or self.current is not None:
                raise DailyMarketTechnicalKDJError("kdj_unknown_evidence_invalid")
        elif self.state in {"match", "no_match"}:
            if self.reason_codes or self.previous is None or self.current is None:
                raise DailyMarketTechnicalKDJError("kdj_known_evidence_invalid")
        else:
            raise DailyMarketTechnicalKDJError("kdj_evidence_state_invalid")
        return {
            "schema": KDJ_EVIDENCE_SCHEMA_V1,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "source_id": self.source_id,
            "source_identity": self.source_identity,
            "source_clock_sha256": self.source_clock_sha256,
            "source_pin_sha256": self.source_pin_sha256,
            "raw_source_window_fingerprint_sha256": self.raw_source_window_fingerprint_sha256,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "method": {
                "id": self.method_id,
                "version": self.method_version,
                "parameters": dict(_METHOD_PARAMETERS_V1),
                "identity_sha256": KDJ_METHOD_IDENTITY_SHA256_V1,
            },
            "state": self.state,
            "reason_codes": list(self.reason_codes),
            "previous": self.previous.to_dict() if self.previous is not None else None,
            "current": self.current.to_dict() if self.current is not None else None,
            "input_feature_dates": [
                value.isoformat() if value is not None else None
                for value in self.input_feature_dates
            ],
            "input_row_fingerprints_sha256": list(self.input_row_fingerprints_sha256),
            "warmup": {
                "required_sessions": self.warmup_required_sessions,
                "observed_sessions": self.warmup_observed_sessions,
                "contiguous_observations": self.warmup_contiguous,
                "source_observed_prefix_contiguous": self.observed_prefix_contiguous,
            },
            "availability": {
                "status": self.availability_status,
                "source_available_at": None,
                "historical_pit_eligible": False,
            },
            "qualification": {
                "reader_qualified": False,
                "qualification_note": "evidence_only_requires_f17_exact_observer",
            },
            "numeric_policy": {
                "precision": self.decimal_precision,
                "rounding": self.decimal_rounding,
                "emin": KDJ_DECIMAL_EMIN_V1,
                "emax": KDJ_DECIMAL_EMAX_V1,
                "clamp": KDJ_DECIMAL_CLAMP_V1,
                "trapped_signals": list(_DECIMAL_TRAPPED_SIGNAL_NAMES_V1),
            },
        }

    @property
    def evidence_identity_sha256(self) -> str:
        """回傳內容識別 hash；它不是來源簽章或資格 token。"""

        return _sha256_json(self._payload())

    def to_dict(self) -> dict[str, object]:
        payload = self._payload()
        payload["evidence_identity_sha256"] = _sha256_json(payload)
        return payload


def project_daily_market_technical_kdj_evidence_v1(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
) -> DailyMarketTechnicalKDJEvidenceV1:
    """從一份已保存的 typed 快照投影 KDJ evidence，不做來源 I/O。

    `snapshot.to_dict()` 會重驗快照 transport、raw token、Decimal 欄位與逐列
    fingerprint；此處不將自洽快照 hash 當成 F17 reader qualification。
    計算只使用最後 14 筆有效觀測；不足、零區間或最新列不可用會回 unknown，
    不回退到舊日期或補值。
    """

    if type(snapshot) is not DailyMarketTechnicalFeatureSnapshotV4:
        raise DailyMarketTechnicalKDJError("kdj_snapshot_type_invalid")
    try:
        with localcontext(_new_kdj_decimal_context()):
            snapshot.to_dict()
    except (TypeError, ValueError, OverflowError) as exc:
        raise DailyMarketTechnicalKDJError("kdj_snapshot_transport_invalid") from exc

    rows = snapshot.rows
    input_rows = rows[-KDJ_WARMUP_REQUIRED_SESSIONS_V1:]
    input_dates = tuple(row.feature_date for row in input_rows)
    input_fingerprints = tuple(row.row_fingerprint_sha256 for row in input_rows)
    warmup_observed = _trailing_valid_session_count(rows)
    current_session = snapshot.current_session
    reasons: list[str] = []

    if not rows or current_session is None:
        reasons.append("kdj_current_observation_unavailable")
    elif rows[-1].feature_date != current_session.feature_date:
        reasons.append("kdj_current_observation_not_latest_raw_row")

    if len(input_rows) < KDJ_WARMUP_REQUIRED_SESSIONS_V1 or warmup_observed < KDJ_WARMUP_REQUIRED_SESSIONS_V1:
        reasons.append("kdj_warmup_insufficient")

    if any(value is None for value in input_dates):
        reasons.append("kdj_observation_date_invalid")
    known_dates = tuple(value for value in input_dates if value is not None)
    if len(known_dates) != len(set(known_dates)):
        reasons.append("kdj_observation_date_duplicate")
    if any(
        earlier is not None and later is not None and earlier >= later
        for earlier, later in zip(input_dates, input_dates[1:])
    ):
        reasons.append("kdj_observation_dates_not_increasing")
    if any(row.feature_date is not None and row.feature_date > snapshot.decision_date for row in input_rows):
        raise DailyMarketTechnicalKDJError("kdj_future_observation_rejected")

    if len(input_rows) == KDJ_WARMUP_REQUIRED_SESSIONS_V1:
        if any(not _valid_ohlc_row(row) for row in input_rows):
            reasons.append("kdj_invalid_ohlc_in_warmup")

    if reasons:
        return _build_unknown_evidence(
            snapshot,
            input_rows,
            input_dates,
            input_fingerprints,
            warmup_observed,
            tuple(dict.fromkeys(reasons)),
        )

    try:
        with localcontext(_new_kdj_decimal_context()):
            observations = _calculate_observations(input_rows)
    except DecimalException as exc:
        raise DailyMarketTechnicalKDJError("kdj_decimal_calculation_invalid") from exc
    except ZeroDivisionError as exc:
        # 零區間在計算前會被轉為 unknown；此 guard 防止意外改動時除零。
        raise DailyMarketTechnicalKDJError("kdj_zero_range_guard_failed") from exc

    if observations is None:
        return _build_unknown_evidence(
            snapshot,
            input_rows,
            input_dates,
            input_fingerprints,
            warmup_observed,
            ("kdj_zero_range",),
        )

    previous, current = observations
    state: Literal["match", "no_match"] = (
        "match"
        if current.k > current.d and previous.k <= previous.d
        else "no_match"
    )
    return DailyMarketTechnicalKDJEvidenceV1(
        stock_code=snapshot.stock_code,
        decision_date=snapshot.decision_date,
        decision_cutoff=snapshot.decision_cutoff,
        source_id=snapshot.source_id,
        source_identity=snapshot.source_identity,
        source_clock_sha256=snapshot.source_clock_sha256,
        source_pin_sha256=snapshot.source_pin_sha256,
        raw_source_window_fingerprint_sha256=snapshot.raw_source_window_fingerprint_sha256,
        snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        state=state,
        reason_codes=(),
        previous=previous,
        current=current,
        input_feature_dates=input_dates,
        input_row_fingerprints_sha256=input_fingerprints,
        warmup_required_sessions=KDJ_WARMUP_REQUIRED_SESSIONS_V1,
        warmup_observed_sessions=KDJ_WARMUP_REQUIRED_SESSIONS_V1,
        warmup_contiguous=True,
        observed_prefix_contiguous=snapshot.observed_prefix_contiguous,
    )


def _build_unknown_evidence(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    input_rows: tuple[DailyMarketTechnicalSourceRow, ...],
    input_dates: tuple[date | None, ...],
    input_fingerprints: tuple[str, ...],
    warmup_observed: int,
    reason_codes: tuple[str, ...],
) -> DailyMarketTechnicalKDJEvidenceV1:
    return DailyMarketTechnicalKDJEvidenceV1(
        stock_code=snapshot.stock_code,
        decision_date=snapshot.decision_date,
        decision_cutoff=snapshot.decision_cutoff,
        source_id=snapshot.source_id,
        source_identity=snapshot.source_identity,
        source_clock_sha256=snapshot.source_clock_sha256,
        source_pin_sha256=snapshot.source_pin_sha256,
        raw_source_window_fingerprint_sha256=snapshot.raw_source_window_fingerprint_sha256,
        snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        state="unknown",
        reason_codes=reason_codes,
        previous=None,
        current=None,
        input_feature_dates=input_dates,
        input_row_fingerprints_sha256=input_fingerprints,
        warmup_required_sessions=KDJ_WARMUP_REQUIRED_SESSIONS_V1,
        warmup_observed_sessions=min(warmup_observed, KDJ_WARMUP_REQUIRED_SESSIONS_V1),
        warmup_contiguous=(
            len(input_rows) == KDJ_WARMUP_REQUIRED_SESSIONS_V1
            and warmup_observed >= KDJ_WARMUP_REQUIRED_SESSIONS_V1
            and all(value is not None for value in input_dates)
            and len({value for value in input_dates if value is not None}) == len(input_dates)
            and all(
                earlier is not None and later is not None and earlier < later
                for earlier, later in zip(input_dates, input_dates[1:])
            )
            and all(_valid_ohlc_row(row) for row in input_rows)
        ),
        observed_prefix_contiguous=snapshot.observed_prefix_contiguous,
    )


def _trailing_valid_session_count(rows: tuple[DailyMarketTechnicalSourceRow, ...]) -> int:
    count = 0
    previous_date: date | None = None
    for row in reversed(rows):
        if not _valid_ohlc_row(row) or row.feature_date is None:
            break
        if previous_date is not None and row.feature_date >= previous_date:
            break
        count += 1
        previous_date = row.feature_date
    return count


def _valid_ohlc_row(row: DailyMarketTechnicalSourceRow) -> bool:
    values = (row.open_price, row.high_price, row.low_price, row.close_price)
    return (
        row.feature_date is not None
        and row.ohlc_valid is True
        and all(type(value) is Decimal and value.is_finite() and value > 0 for value in values)
        and row.low_price is not None
        and row.high_price is not None
        and row.close_price is not None
        and row.low_price <= row.close_price <= row.high_price
    )


def _calculate_observations(
    rows: tuple[DailyMarketTechnicalSourceRow, ...],
) -> tuple[DailyMarketTechnicalKDJDayV1, DailyMarketTechnicalKDJDayV1] | None:
    if len(rows) != KDJ_WARMUP_REQUIRED_SESSIONS_V1:
        return None

    rsv_by_index: dict[int, Decimal] = {}
    for index in range(8, len(rows)):
        window = rows[index - 8:index + 1]
        highs = tuple(row.high_price for row in window)
        lows = tuple(row.low_price for row in window)
        close = rows[index].close_price
        if (
            any(type(value) is not Decimal or not value.is_finite() for value in highs + lows)
            or type(close) is not Decimal
            or not close.is_finite()
        ):
            return None
        highest = max(value for value in highs if value is not None)
        lowest = min(value for value in lows if value is not None)
        if highest == lowest:
            return None
        rsv_by_index[index] = (Decimal(100) * (close - lowest)) / (highest - lowest)

    k_by_index: dict[int, Decimal] = {}
    for index in range(10, len(rows)):
        values = (rsv_by_index[index - 2], rsv_by_index[index - 1], rsv_by_index[index])
        k_by_index[index] = sum(values, Decimal(0)) / Decimal(3)

    d_by_index: dict[int, Decimal] = {}
    for index in range(12, len(rows)):
        values = (k_by_index[index - 2], k_by_index[index - 1], k_by_index[index])
        d_by_index[index] = sum(values, Decimal(0)) / Decimal(3)

    day_values: list[DailyMarketTechnicalKDJDayV1] = []
    for index in (12, 13):
        row = rows[index]
        if row.feature_date is None or row.close_price is None:
            return None
        k_value = k_by_index[index]
        d_value = d_by_index[index]
        day_values.append(DailyMarketTechnicalKDJDayV1(
            feature_date=row.feature_date,
            source_row_fingerprint_sha256=row.row_fingerprint_sha256,
            rsv=rsv_by_index[index],
            k=k_value,
            d=d_value,
            j=Decimal(3) * k_value - Decimal(2) * d_value,
        ))
    return day_values[0], day_values[1]


def _decimal_text(value: Decimal) -> str:
    if type(value) is not Decimal or not value.is_finite():
        raise DailyMarketTechnicalKDJError("kdj_decimal_output_invalid")
    text = str(value)
    if len(text.encode("utf-8")) > 256:
        raise DailyMarketTechnicalKDJError("kdj_decimal_output_limit")
    return text


def _new_kdj_decimal_context() -> Context:
    context = Context(
        prec=KDJ_DECIMAL_PRECISION_V1,
        rounding=ROUND_HALF_EVEN,
        Emin=KDJ_DECIMAL_EMIN_V1,
        Emax=KDJ_DECIMAL_EMAX_V1,
        clamp=KDJ_DECIMAL_CLAMP_V1,
    )
    for signal in tuple(context.traps):
        context.traps[signal] = signal in _TRAPPED_SIGNALS_V1
    for signal in (Clamped, Inexact, Rounded, Subnormal, Underflow):
        context.traps[signal] = False
    return context


def _sha256_json(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DailyMarketTechnicalKDJError("kdj_json_payload_invalid") from exc
    return hashlib.sha256(encoded).hexdigest()


KDJ_METHOD_IDENTITY_SHA256_V1 = _sha256_json({
    "method_id": KDJ_METHOD_ID_V1,
    "method_version": KDJ_METHOD_VERSION_V1,
    "parameters": _METHOD_PARAMETERS_V1,
})
