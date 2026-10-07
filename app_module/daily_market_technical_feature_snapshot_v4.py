"""P02 五項技術觀察的有界、不可變 v4 保存投影。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal, Protocol, TypeAlias, cast
from zoneinfo import ZoneInfo

from app_module.daily_market_technical_method_contract_v4 import (
    DAILY_MARKET_TECHNICAL_FEATURE_KEYS_V4,
    DAILY_MARKET_TECHNICAL_RULE_KEYS_V4,
    daily_market_technical_method_contract_v4_payload,
    daily_market_technical_method_contract_v4_sha256,
    validate_daily_market_technical_method_contract_v4,
)
from app_module.daily_market_technical_source import (
    DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
    DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS,
    DAILY_MARKET_TECHNICAL_SOURCE_SCHEMA,
    DailyMarketTechnicalSourceRow,
    DailyMarketTechnicalSourceWindow,
    _parse_date,
    _source_decimal,
    _source_volume,
    validate_daily_market_technical_calculation_binding,
)
from decision_module.factors.selection_technical_rules import (
    CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
    CAUSAL_INDICATOR_LINEAGE_VERSION,
    RAW_VOLUME_LINEAGE_METHOD_ID,
    RAW_VOLUME_LINEAGE_VERSION,
    TECHNICAL_SOURCE_ID,
    VOLUME_SOURCE_ID,
    VOLUME_UNIT,
    ParameterValue,
    TechnicalFeatureEvidence,
    TechnicalObservedSession,
    TechnicalObservationWindow,
    TechnicalRuleResult,
    evaluate_daily_technical_rules,
    technical_observation_window_fingerprint_sha256,
    technical_session_fingerprint_sha256,
)


DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_SCHEMA_V4 = (
    "daily-market-technical-feature-snapshot.v4"
)
DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES = 256 * 1024
DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_STOCK_CODE_CHARS = 16
DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_PATH_CHARS = 4096
DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_RAW_TOKEN_BYTES = 256
DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_ROW_RAW_BYTES = 1024
DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_EXPLANATION_BYTES = 2048
DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_REASON_COUNT = 64
DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_FACTS_PER_RULE = 20

_TAIPEI = ZoneInfo("Asia/Taipei")
_MIN_CUTOFF = time(16, 0)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ROW_RAW_KEYS = ("date", "stock_code", "open", "high", "low", "close", "volume_shares")
_SOURCE_PIN_KEYS = frozenset({
    "database_path",
    "source_id",
    "schema_identity_sha256",
    "source_file_pin",
    "source_pin_sha256",
    "decision_date",
    "decision_cutoff",
    "cutoff_guard_version",
    "source_available_at",
    "availability_status",
    "historical_pit_eligible",
})
_SNAPSHOT_KEYS = frozenset({
    "schema_version",
    "snapshot_identity_sha256",
    "stock_code",
    "decision_date",
    "decision_cutoff",
    "source_clock",
    "source_clock_sha256",
    "source_id",
    "source_identity",
    "schema_identity_sha256",
    "source_pin_sha256",
    "cutoff_guard_version",
    "raw_source_window_fingerprint_sha256",
    "source_window_fingerprint_sha256",
    "calculation",
    "availability",
    "observed_prefix_contiguous",
    "raw_rows",
    "session_pins",
    "feature_sessions",
    "rules",
    "method_contracts",
    "method_contracts_sha256",
    "policy",
})
_CALCULATION_KEYS = frozenset({
    "method_id", "method_version", "identity_sha256", "talib_version", "binding",
})
_AVAILABILITY_KEYS = frozenset({
    "source_available_at", "availability_status", "historical_pit_eligible",
})
_POLICY = {
    "usage": "current_restated_research_only",
    "official_availability": "unknown",
    "market_calendar_completeness": "unknown",
    "historical_pit_eligible": False,
}
_ROW_KEYS = frozenset({
    "raw_date", "feature_date", "stock_code", "open_price", "high_price",
    "low_price", "close_price", "volume_shares", "raw_values",
    "row_fingerprint_sha256", "ohlc_valid", "volume_valid", "invalid_reasons",
})
_SESSION_PIN_KEYS = frozenset({
    "feature_date", "source_fingerprint_sha256", "session_fingerprint_sha256", "pin_verified",
})
_SESSION_KEYS = frozenset({
    "stock_code", "feature_date", "source_identity", "source_fingerprint_sha256",
    "pin_verified", "features", "session_fingerprint_sha256",
})
_FEATURE_KEYS = frozenset({
    "key", "value", "unit", "state", "source_id", "source_fingerprint_sha256",
    "method_id", "method_version", "parameters", "lineage_verified",
    "warmup_required_sessions", "warmup_observed_sessions", "warmup_contiguous",
})
_RULE_KEYS = frozenset({
    "key", "method_id", "version", "state", "parameters", "supports",
    "counterevidence", "unknown_reasons", "raw_fact_refs", "numerator",
    "denominator", "ratio", "stock_code", "decision_date", "decision_cutoff",
    "feature_date", "previous_feature_date", "source_identity",
    "source_window_fingerprint_sha256", "lookahead_check", "availability_result",
    "usage", "pit_eligible",
})
_FACT_REF_KEYS = frozenset({
    "ordinal", "feature_date", "feature_key", "reference_kind",
    "source_fingerprint_sha256", "source_id", "method_id", "method_version",
    "unit", "parameters", "lineage_verified",
})
_LOOKAHEAD_CHECKS = frozenset({
    "feature_dates_within_decision_date", "future_feature_date", "future_available_at",
    "source_pins_unverified", "observed_prefix_not_contiguous", "window_fingerprint_mismatch",
})
_AVAILABILITY_RESULTS = frozenset({
    "available_at_unknown", "source_unavailable", "available_at_after_cutoff",
})
_SESSION_FEATURE_CONTRACTS = {
    item["key"]: item for item in daily_market_technical_method_contract_v4_payload()["features"]
}
_RULE_CONTRACTS = {
    item["key"]: item for item in daily_market_technical_method_contract_v4_payload()["rules"]
}

SourceFilePin: TypeAlias = tuple[
    tuple[str, int, int, int, int] | tuple[str], ...
]
SnapshotFeatureState: TypeAlias = Literal["observed", "unknown"]
SnapshotRuleState: TypeAlias = Literal["match", "no_match", "unknown"]
ReferenceKind: TypeAlias = Literal["session_feature", "raw_volume_row"]


class SourceClockV4Protocol(Protocol):
    """由共享 read-session 提供；不讓 feature snapshot 反向依賴其實作模組。"""

    @property
    def database_path(self) -> str: ...

    @property
    def source_id(self) -> str: ...

    @property
    def schema_identity_sha256(self) -> str: ...

    @property
    def source_file_pin(self) -> SourceFilePin: ...

    @property
    def source_pin_sha256(self) -> str: ...

    @property
    def decision_date(self) -> date: ...

    @property
    def decision_cutoff(self) -> datetime: ...

    @property
    def cutoff_guard_version(self) -> str: ...

    @property
    def source_available_at(self) -> None: ...

    @property
    def availability_status(self) -> Literal["unknown"]: ...

    @property
    def historical_pit_eligible(self) -> Literal[False]: ...

    @property
    def identity_sha256(self) -> str: ...

    def to_dict(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class TechnicalSessionPinV4:
    feature_date: date
    source_fingerprint_sha256: str
    session_fingerprint_sha256: str
    pin_verified: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "feature_date": self.feature_date.isoformat(),
            "source_fingerprint_sha256": self.source_fingerprint_sha256,
            "session_fingerprint_sha256": self.session_fingerprint_sha256,
            "pin_verified": self.pin_verified,
        }


@dataclass(frozen=True, slots=True)
class TechnicalFactReferenceV4:
    ordinal: int
    feature_date: date
    feature_key: str
    reference_kind: ReferenceKind
    source_fingerprint_sha256: str
    source_id: str
    method_id: str
    method_version: str
    unit: str
    parameters: tuple[tuple[str, ParameterValue], ...]
    lineage_verified: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "feature_date": self.feature_date.isoformat(),
            "feature_key": self.feature_key,
            "reference_kind": self.reference_kind,
            "source_fingerprint_sha256": self.source_fingerprint_sha256,
            "source_id": self.source_id,
            "method_id": self.method_id,
            "method_version": self.method_version,
            "unit": self.unit,
            "parameters": _parameters_to_json(self.parameters),
            "lineage_verified": self.lineage_verified,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalRuleEvidenceV4:
    key: str
    method_id: str
    version: str
    state: SnapshotRuleState
    parameters: tuple[tuple[str, ParameterValue], ...]
    supports: tuple[str, ...]
    counterevidence: tuple[str, ...]
    unknown_reasons: tuple[str, ...]
    raw_fact_refs: tuple[TechnicalFactReferenceV4, ...]
    numerator: Decimal | None
    denominator: Decimal | None
    ratio: Decimal | None
    stock_code: str
    decision_date: date
    decision_cutoff: datetime
    feature_date: date | None
    previous_feature_date: date | None
    source_identity: str
    source_window_fingerprint_sha256: str
    lookahead_check: str
    availability_result: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "method_id": self.method_id,
            "version": self.version,
            "state": self.state,
            "parameters": _parameters_to_json(self.parameters),
            "supports": list(self.supports),
            "counterevidence": list(self.counterevidence),
            "unknown_reasons": list(self.unknown_reasons),
            "raw_fact_refs": [item.to_dict() for item in self.raw_fact_refs],
            "numerator": _decimal_text(self.numerator),
            "denominator": _decimal_text(self.denominator),
            "ratio": _decimal_text(self.ratio),
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "feature_date": self.feature_date.isoformat() if self.feature_date else None,
            "previous_feature_date": (
                self.previous_feature_date.isoformat()
                if self.previous_feature_date
                else None
            ),
            "source_identity": self.source_identity,
            "source_window_fingerprint_sha256": self.source_window_fingerprint_sha256,
            "lookahead_check": self.lookahead_check,
            "availability_result": self.availability_result,
            "usage": "current_restated_research_only",
            "pit_eligible": False,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalFeatureSnapshotV4:
    """固定來源時計、120列原料、最近兩日指標與五條方法結果。"""

    stock_code: str
    decision_date: date
    decision_cutoff: datetime
    source_clock_json: str
    source_clock_sha256: str
    source_id: str
    source_identity: str
    schema_identity_sha256: str
    source_pin_sha256: str
    cutoff_guard_version: str
    raw_source_window_fingerprint_sha256: str
    source_window_fingerprint_sha256: str
    calculation_identity_sha256: str
    calculation_version: str
    talib_version: str
    calculation_binding_json: str
    availability_status: Literal["unknown"]
    observed_prefix_contiguous: bool
    rows: tuple[DailyMarketTechnicalSourceRow, ...]
    session_pins: tuple[TechnicalSessionPinV4, ...]
    feature_sessions: tuple[TechnicalObservedSession, ...]
    rules: tuple[DailyMarketTechnicalRuleEvidenceV4, ...]
    method_contracts_sha256: str
    snapshot_identity_sha256: str

    @property
    def source_clock(self) -> dict[str, object]:
        value = json.loads(self.source_clock_json)
        if not isinstance(value, dict):
            raise ValueError("technical_snapshot_v4_source_clock_invalid")
        return value

    @property
    def previous_session(self) -> TechnicalObservedSession | None:
        return self.feature_sessions[0] if len(self.feature_sessions) == 2 else None

    @property
    def current_session(self) -> TechnicalObservedSession | None:
        return self.feature_sessions[-1] if self.feature_sessions else None

    def to_dict(self) -> dict[str, object]:
        payload = self._payload()
        _validate_snapshot_payload(payload, verify_identity=True)
        _enforce_json_size(payload)
        return payload

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    @classmethod
    def from_source_window(
        cls,
        window: DailyMarketTechnicalSourceWindow,
        *,
        source_clock: SourceClockV4Protocol,
    ) -> DailyMarketTechnicalFeatureSnapshotV4:
        """從已驗證 adapter window 投影；不重算或讀取來源 DB。"""

        if not isinstance(window, DailyMarketTechnicalSourceWindow):
            raise TypeError("window 必須是 DailyMarketTechnicalSourceWindow")
        if window.calculation_binding_json is None:
            raise ValueError("technical_snapshot_v4_calculation_binding_missing")
        binding = json.loads(window.calculation_binding_json)
        validate_daily_market_technical_calculation_binding(
            binding, expected_identity=window.calculation_identity_sha256,
            expected_talib_version=window.talib_version,
        )
        if _canonical_json(binding) != window.calculation_binding_json:
            raise ValueError("technical_snapshot_v4_calculation_binding_noncanonical")
        clock_payload = source_clock.to_dict()
        _validate_source_clock_payload(clock_payload)
        clock_json = _canonical_json(clock_payload)
        clock_sha = _sha256_bytes(clock_json.encode("utf-8"))
        if source_clock.identity_sha256 != clock_sha:
            raise ValueError("technical_snapshot_v4_source_clock_identity_mismatch")
        _validate_window_clock_match(window, clock_payload)
        method_contracts = daily_market_technical_method_contract_v4_payload()
        method_sha = daily_market_technical_method_contract_v4_sha256(method_contracts)
        _validate_window(window, clock_payload)

        session_pins = tuple(
            TechnicalSessionPinV4(
                feature_date=session.feature_date,
                source_fingerprint_sha256=session.source_fingerprint_sha256,
                session_fingerprint_sha256=technical_session_fingerprint_sha256(session),
                pin_verified=session.pin_verified,
            )
            for session in window.sessions
        )
        feature_sessions = tuple(window.sessions[-2:])
        rule_results = window.evaluate()
        if tuple(item.key for item in rule_results) != DAILY_MARKET_TECHNICAL_RULE_KEYS_V4:
            raise ValueError("technical_snapshot_v4_rule_set_mismatch")
        rows_by_ref = {
            (row.feature_date, row.row_fingerprint_sha256): row for row in window.rows
        }
        features_by_ref = {
            (session.feature_date, session.source_fingerprint_sha256, feature.key): (
                session,
                feature,
            )
            for session in feature_sessions
            for feature in session.features
        }
        rules = tuple(
            _rule_evidence_from_result(
                result,
                stock_code=window.stock_code,
                decision_date=window.decision_date,
                decision_cutoff=window.decision_cutoff,
                source_identity=window.source_identity,
                source_window_fingerprint_sha256=window.source_window_fingerprint_sha256,
                rows_by_ref=rows_by_ref,
                features_by_ref=features_by_ref,
            )
            for result in rule_results
        )
        draft = cls(
            stock_code=window.stock_code,
            decision_date=window.decision_date,
            decision_cutoff=window.decision_cutoff,
            source_clock_json=clock_json,
            source_clock_sha256=clock_sha,
            source_id=window.source_id,
            source_identity=window.source_identity,
            schema_identity_sha256=window.schema_identity_sha256,
            source_pin_sha256=window.source_pin_sha256,
            cutoff_guard_version=DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
            raw_source_window_fingerprint_sha256=window.raw_source_window_fingerprint_sha256,
            source_window_fingerprint_sha256=window.source_window_fingerprint_sha256,
            calculation_identity_sha256=window.calculation_identity_sha256,
            calculation_version=window.calculation_version,
            talib_version=window.talib_version,
            calculation_binding_json=window.calculation_binding_json,
            availability_status="unknown",
            observed_prefix_contiguous=window.observed_prefix_contiguous,
            rows=tuple(window.rows),
            session_pins=session_pins,
            feature_sessions=feature_sessions,
            rules=rules,
            method_contracts_sha256=method_sha,
            snapshot_identity_sha256="",
        )
        body = draft._payload()
        identity = _identity_sha256(body)
        payload = {**body, "snapshot_identity_sha256": identity}
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalFeatureSnapshotV4:
        if not isinstance(payload, Mapping):
            raise ValueError("technical_snapshot_v4_invalid")
        _validate_snapshot_payload(payload, verify_identity=True)
        return cls(
            stock_code=cast(str, payload["stock_code"]),
            decision_date=date.fromisoformat(cast(str, payload["decision_date"])),
            decision_cutoff=datetime.fromisoformat(cast(str, payload["decision_cutoff"])),
            source_clock_json=_canonical_json(cast(Mapping[str, Any], payload["source_clock"])),
            source_clock_sha256=cast(str, payload["source_clock_sha256"]),
            source_id=cast(str, payload["source_id"]),
            source_identity=cast(str, payload["source_identity"]),
            schema_identity_sha256=cast(str, payload["schema_identity_sha256"]),
            source_pin_sha256=cast(str, payload["source_pin_sha256"]),
            cutoff_guard_version=cast(str, payload["cutoff_guard_version"]),
            raw_source_window_fingerprint_sha256=cast(str, payload["raw_source_window_fingerprint_sha256"]),
            source_window_fingerprint_sha256=cast(str, payload["source_window_fingerprint_sha256"]),
            calculation_identity_sha256=cast(str, cast(Mapping[str, Any], payload["calculation"])["identity_sha256"]),
            calculation_version=cast(str, cast(Mapping[str, Any], payload["calculation"])["method_version"]),
            talib_version=cast(str, cast(Mapping[str, Any], payload["calculation"])["talib_version"]),
            calculation_binding_json=_canonical_json(cast(Mapping[str, Any], payload["calculation"])["binding"]),
            availability_status="unknown",
            observed_prefix_contiguous=cast(bool, payload["observed_prefix_contiguous"]),
            rows=tuple(_row_from_dict(item) for item in cast(list[Any], payload["raw_rows"])),
            session_pins=tuple(_session_pin_from_dict(item) for item in cast(list[Any], payload["session_pins"])),
            feature_sessions=tuple(_session_from_dict(item) for item in cast(list[Any], payload["feature_sessions"])),
            rules=tuple(_rule_from_dict(item) for item in cast(list[Any], payload["rules"])),
            method_contracts_sha256=cast(str, payload["method_contracts_sha256"]),
            snapshot_identity_sha256=cast(str, payload["snapshot_identity_sha256"]),
        )

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalFeatureSnapshotV4:
        if isinstance(raw, bytes):
            if len(raw) > DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES:
                raise ValueError("technical_snapshot_v4_byte_limit")
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("technical_snapshot_v4_invalid_json") from exc
        elif isinstance(raw, str):
            if len(raw.encode("utf-8")) > DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES:
                raise ValueError("technical_snapshot_v4_byte_limit")
            text = raw
        else:
            raise TypeError("raw 必須是 bytes 或 str")
        try:
            payload = json.loads(
                text,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            if "duplicate_json_key" in str(exc):
                raise ValueError("technical_snapshot_v4_duplicate_json_key") from exc
            raise ValueError("technical_snapshot_v4_invalid_json") from exc
        snapshot = cls.from_dict(payload)
        # from_dict 已完整核驗語義與identity；同一個不可變結果只做格式回轉比對。
        if _canonical_json(snapshot._payload()) != text:
            raise ValueError("technical_snapshot_v4_noncanonical_json")
        return snapshot

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_SCHEMA_V4,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "source_clock": self.source_clock,
            "source_clock_sha256": self.source_clock_sha256,
            "source_id": self.source_id,
            "source_identity": self.source_identity,
            "schema_identity_sha256": self.schema_identity_sha256,
            "source_pin_sha256": self.source_pin_sha256,
            "cutoff_guard_version": self.cutoff_guard_version,
            "raw_source_window_fingerprint_sha256": self.raw_source_window_fingerprint_sha256,
            "source_window_fingerprint_sha256": self.source_window_fingerprint_sha256,
            "calculation": {
                "method_id": CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
                "method_version": self.calculation_version,
                "identity_sha256": self.calculation_identity_sha256,
                "talib_version": self.talib_version,
                "binding": json.loads(self.calculation_binding_json),
            },
            "availability": {
                "source_available_at": None,
                "availability_status": self.availability_status,
                "historical_pit_eligible": False,
            },
            "observed_prefix_contiguous": self.observed_prefix_contiguous,
            "raw_rows": [row.to_dict() for row in self.rows],
            "session_pins": [item.to_dict() for item in self.session_pins],
            "feature_sessions": [_session_to_dict(item) for item in self.feature_sessions],
            "rules": [item.to_dict() for item in self.rules],
            "method_contracts": daily_market_technical_method_contract_v4_payload(),
            "method_contracts_sha256": self.method_contracts_sha256,
            "policy": dict(_POLICY),
        }


def build_daily_market_technical_feature_snapshot_v4(
    window: DailyMarketTechnicalSourceWindow,
    *,
    source_clock: SourceClockV4Protocol,
) -> DailyMarketTechnicalFeatureSnapshotV4:
    """建立可供 v4 repository 驗證的 typed source snapshot。"""

    return DailyMarketTechnicalFeatureSnapshotV4.from_source_window(
        window, source_clock=source_clock
    )


def validate_daily_market_technical_feature_snapshot_v4(
    payload: object,
) -> DailyMarketTechnicalFeatureSnapshotV4:
    return DailyMarketTechnicalFeatureSnapshotV4.from_dict(payload)


def _validate_window_clock_match(
    window: DailyMarketTechnicalSourceWindow,
    clock: Mapping[str, Any],
) -> None:
    if (
        window.database_path != clock["database_path"]
        or window.source_id != clock["source_id"]
        or window.schema_identity_sha256 != clock["schema_identity_sha256"]
        or window.source_file_pin != tuple(tuple(item) for item in clock["source_file_pin"])
        or window.source_pin_sha256 != clock["source_pin_sha256"]
        or window.decision_date.isoformat() != clock["decision_date"]
        or window.decision_cutoff.isoformat() != clock["decision_cutoff"]
        or window.source_available_at is not None
        or window.availability_status != "unknown"
    ):
        raise ValueError("technical_snapshot_v4_source_clock_mismatch")


def _validate_window(
    window: DailyMarketTechnicalSourceWindow,
    clock: Mapping[str, Any],
) -> None:
    if (
        window.source_id != "sqlite.daily_prices"
        or window.stock_code == ""
        or len(window.stock_code) > DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_STOCK_CODE_CHARS
        or window.stock_code.strip() != window.stock_code
        or window.decision_date.isoformat() != clock["decision_date"]
        or window.decision_cutoff.isoformat() != clock["decision_cutoff"]
        or window.schema_identity_sha256 != clock["schema_identity_sha256"]
        or window.source_pin_sha256 != clock["source_pin_sha256"]
        or window.source_file_pin != tuple(tuple(item) for item in clock["source_file_pin"])
        or len(window.rows) > DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS
        or len(window.sessions) > DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS
    ):
        raise ValueError("technical_snapshot_v4_source_window_invalid")
    if not _is_sha256(window.calculation_identity_sha256):
        raise ValueError("technical_snapshot_v4_calculation_identity_invalid")
    if window.calculation_version != CAUSAL_INDICATOR_LINEAGE_VERSION:
        raise ValueError("technical_snapshot_v4_calculation_version_mismatch")
    if not window.talib_version or len(window.talib_version) > 128:
        raise ValueError("technical_snapshot_v4_talib_version_invalid")
    expected_rows = sorted(
        window.rows,
        key=lambda item: (item.feature_date or date.min, item.raw_date, item.raw_values),
    )
    if tuple(expected_rows) != window.rows:
        raise ValueError("technical_snapshot_v4_rows_not_canonical")
    for row in window.rows:
        _validate_source_row(row, expected_stock_code=window.stock_code)
        if row.feature_date is not None and row.feature_date > window.decision_date:
            raise ValueError("technical_snapshot_v4_future_source_date")
    raw_window_hash = _sha256_json({
        "schema_version": DAILY_MARKET_TECHNICAL_SOURCE_SCHEMA,
        "schema_identity_sha256": window.schema_identity_sha256,
        "stock_code": window.stock_code,
        "decision_date": window.decision_date.isoformat(),
        "decision_cutoff": window.decision_cutoff.isoformat(),
        "cutoff_guard_version": DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
        "rows": [row.to_dict() for row in window.rows],
    })
    if raw_window_hash != window.raw_source_window_fingerprint_sha256:
        raise ValueError("technical_snapshot_v4_raw_window_fingerprint_mismatch")
    expected_source_identity = _source_identity_for_window(window)
    if window.source_identity != expected_source_identity:
        raise ValueError("technical_snapshot_v4_source_identity_mismatch")
    if window.observation_window.stock_code != window.stock_code:
        raise ValueError("technical_snapshot_v4_observation_stock_mismatch")
    if any(
        item.stock_code != window.stock_code
        or item.source_identity != window.source_identity
        or item.feature_date > window.decision_date
        or item.source_fingerprint_sha256 not in {
            row.row_fingerprint_sha256
            for row in window.rows
            if row.feature_date == item.feature_date
        }
        for item in window.sessions
    ):
        raise ValueError("technical_snapshot_v4_session_reference_mismatch")
    if not _is_sha256(window.source_window_fingerprint_sha256):
        raise ValueError("technical_snapshot_v4_window_fingerprint_invalid")
    if window.observation_window.source_window_fingerprint_sha256 != window.source_window_fingerprint_sha256:
        raise ValueError("technical_snapshot_v4_window_fingerprint_mismatch")
    _validate_session_sequence(window)
    expected_contract_sha = daily_market_technical_method_contract_v4_sha256()
    if not expected_contract_sha:
        raise ValueError("technical_snapshot_v4_method_contract_invalid")


def _source_identity_for_window(window: DailyMarketTechnicalSourceWindow) -> str:
    identity_payload = {
        "database": window.database_path,
        "source_pin_sha256": window.source_pin_sha256,
        "schema_identity_sha256": window.schema_identity_sha256,
        "stock_code": window.stock_code,
        "decision_date": window.decision_date.isoformat(),
        "decision_cutoff": window.decision_cutoff.isoformat(),
        "cutoff_guard_version": DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
        "raw_source_window_fingerprint_sha256": window.raw_source_window_fingerprint_sha256,
        "calculation_identity_sha256": window.calculation_identity_sha256,
    }
    return f"{TECHNICAL_SOURCE_ID}:{_sha256_json(identity_payload)}"


def _validate_session_sequence(window: DailyMarketTechnicalSourceWindow) -> None:
    sessions = window.sessions
    dates = tuple(item.feature_date for item in sessions)
    if dates != tuple(sorted(dates)):
        raise ValueError("technical_snapshot_v4_sessions_not_sorted")
    if window.observed_prefix_contiguous:
        if not sessions or len(set(dates)) != len(dates):
            raise ValueError("technical_snapshot_v4_contiguous_prefix_invalid")
        if any(not item.pin_verified for item in sessions):
            raise ValueError("technical_snapshot_v4_contiguous_pin_invalid")
    if window.observation_window.sessions != sessions:
        raise ValueError("technical_snapshot_v4_observation_sessions_mismatch")
    if window.observation_window.decision_date != window.decision_date:
        raise ValueError("technical_snapshot_v4_observation_date_mismatch")
    if window.observation_window.decision_cutoff.isoformat() != window.decision_cutoff.isoformat():
        raise ValueError("technical_snapshot_v4_observation_cutoff_mismatch")
    if window.observation_window.source_identity != window.source_identity:
        raise ValueError("technical_snapshot_v4_observation_source_mismatch")
    if window.observation_window.availability_status != "unknown" or window.observation_window.source_available_at is not None:
        raise ValueError("technical_snapshot_v4_observation_availability_invalid")
    expected_window_hash = _sha256_json({
        "stock_code": window.stock_code,
        "decision_date": window.decision_date.isoformat(),
        "source_identity": window.source_identity,
        "sessions": [
            {
                "feature_date": item.feature_date.isoformat(),
                "session_fingerprint_sha256": technical_session_fingerprint_sha256(item),
            }
            for item in sessions
        ],
    })
    if expected_window_hash != window.source_window_fingerprint_sha256:
        raise ValueError("technical_snapshot_v4_window_fingerprint_mismatch")


def _validate_source_row(
    row: DailyMarketTechnicalSourceRow,
    *,
    expected_stock_code: str,
) -> None:
    if not isinstance(row, DailyMarketTechnicalSourceRow):
        raise TypeError("rows 僅能包含 DailyMarketTechnicalSourceRow")
    if (
        row.stock_code != expected_stock_code
        or len(row.raw_date.encode("utf-8")) > 64
        or tuple(key for key, _value in row.raw_values) != _ROW_RAW_KEYS
        or len(row.raw_values) != len(_ROW_RAW_KEYS)
    ):
        raise ValueError("technical_snapshot_v4_raw_row_invalid")
    raw_total = 0
    token_values: dict[str, object] = {}
    for key, token in row.raw_values:
        if not isinstance(token, str):
            raise TypeError("raw token 必須是字串")
        token_bytes = token.encode("utf-8")
        raw_total += len(token_bytes)
        if len(token_bytes) > DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_RAW_TOKEN_BYTES:
            raise ValueError("technical_snapshot_v4_raw_token_limit")
        token_values[key] = _decode_raw_token(token)
    if raw_total > DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_ROW_RAW_BYTES:
        raise ValueError("technical_snapshot_v4_raw_row_token_limit")
    if str(token_values["stock_code"]).strip() != expected_stock_code:
        raise ValueError("technical_snapshot_v4_raw_stock_mismatch")
    expected_raw_date = str(token_values["date"]).strip() if token_values["date"] is not None else ""
    if row.raw_date != expected_raw_date:
        raise ValueError("technical_snapshot_v4_raw_date_token_mismatch")
    parsed_date = _parse_date(token_values["date"])
    expected_date = parsed_date.isoformat() if parsed_date is not None else None
    actual_date = row.feature_date.isoformat() if row.feature_date else None
    if actual_date != expected_date:
        raise ValueError("technical_snapshot_v4_raw_date_mismatch")
    expected_decimals = {
        key: _source_decimal(token_values[key])
        for key in ("open", "high", "low", "close")
    }
    actual_decimals = {
        "open": row.open_price,
        "high": row.high_price,
        "low": row.low_price,
        "close": row.close_price,
    }
    if expected_decimals != actual_decimals:
        raise ValueError("technical_snapshot_v4_raw_ohlc_value_mismatch")
    expected_volume = _source_volume(token_values["volume_shares"])
    if row.volume_shares != expected_volume or row.volume_valid is not (expected_volume is not None):
        raise ValueError("technical_snapshot_v4_raw_volume_mismatch")
    reasons: list[str] = []
    if row.feature_date is None:
        reasons.append("source_date_invalid")
    values = tuple(expected_decimals.values())
    if any(value is None for value in values):
        reasons.append("ohlc_value_missing_or_invalid")
    ohlc_valid = all(value is not None and value.is_finite() and value > 0 for value in values)
    if ohlc_valid:
        open_price = expected_decimals["open"]
        high_price = expected_decimals["high"]
        low_price = expected_decimals["low"]
        close_price = expected_decimals["close"]
        assert open_price is not None and high_price is not None
        assert low_price is not None and close_price is not None
        ohlc_valid = low_price <= min(open_price, close_price) and high_price >= max(open_price, close_price)
        if not ohlc_valid:
            reasons.append("ohlc_range_invalid")
    if token_values["volume_shares"] is None or expected_volume is None:
        reasons.append("volume_shares_missing_or_invalid")
    if row.ohlc_valid is not bool(ohlc_valid) or row.invalid_reasons != tuple(dict.fromkeys(reasons)):
        raise ValueError("technical_snapshot_v4_raw_validity_mismatch")
    row_payload = {
        "stock_code": row.stock_code,
        "feature_date": row.feature_date.isoformat() if row.feature_date else None,
        "raw_values": {key: token for key, token in row.raw_values},
    }
    if row.row_fingerprint_sha256 != _sha256_json(row_payload):
        raise ValueError("technical_snapshot_v4_raw_row_hash_mismatch")


def _decode_raw_token(token: str) -> object:
    try:
        value = json.loads(
            token,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("technical_snapshot_v4_raw_token_invalid") from exc
    if not isinstance(value, dict) or set(value) not in (
        {"type", "value"}, {"type", "hex"}
    ):
        raise ValueError("technical_snapshot_v4_raw_token_invalid")
    if _canonical_json(value) != token:
        raise ValueError("technical_snapshot_v4_raw_token_noncanonical")
    token_type = value.get("type")
    if token_type == "null" and set(value) == {"type", "value"} and value["value"] is None:
        return None
    if token_type == "str" and set(value) == {"type", "value"} and isinstance(value["value"], str):
        return value["value"]
    if token_type == "int" and set(value) == {"type", "value"} and type(value["value"]) is int:
        return value["value"]
    if token_type == "float" and set(value) == {"type", "value"} and isinstance(value["value"], str):
        try:
            decoded = float(value["value"])
        except (ValueError, OverflowError) as exc:
            raise ValueError("technical_snapshot_v4_raw_token_invalid") from exc
        if repr(decoded) != value["value"]:
            raise ValueError("technical_snapshot_v4_raw_token_noncanonical")
        return decoded
    if token_type == "bytes" and set(value) == {"type", "hex"} and isinstance(value["hex"], str):
        try:
            decoded_bytes = bytes.fromhex(value["hex"])
        except ValueError as exc:
            raise ValueError("technical_snapshot_v4_raw_token_invalid") from exc
        if decoded_bytes.hex() != value["hex"]:
            raise ValueError("technical_snapshot_v4_raw_token_noncanonical")
        return decoded_bytes
    raise ValueError("technical_snapshot_v4_raw_token_invalid")


def _rule_evidence_from_result(
    result: TechnicalRuleResult,
    *,
    stock_code: str,
    decision_date: date,
    decision_cutoff: datetime,
    source_identity: str,
    source_window_fingerprint_sha256: str,
    rows_by_ref: Mapping[tuple[date | None, str], DailyMarketTechnicalSourceRow],
    features_by_ref: Mapping[
        tuple[date, str, str],
        tuple[TechnicalObservedSession, TechnicalFeatureEvidence],
    ],
) -> DailyMarketTechnicalRuleEvidenceV4:
    references: list[TechnicalFactReferenceV4] = []
    for ordinal, fact in enumerate(result.raw_facts):
        feature = fact.evidence
        if (
            fact.stock_code != stock_code
            or fact.source_identity != source_identity
            or feature.source_fingerprint_sha256 == ""
        ):
            raise ValueError("technical_snapshot_v4_rule_fact_identity_mismatch")
        if feature.key == "volume_shares":
            row = rows_by_ref.get((fact.feature_date, feature.source_fingerprint_sha256))
            reference_kind: ReferenceKind = "raw_volume_row"
            if row is None:
                raise ValueError("technical_snapshot_v4_volume_fact_unresolved")
        else:
            pair = features_by_ref.get(
                (fact.feature_date, feature.source_fingerprint_sha256, feature.key)
            )
            reference_kind = "session_feature"
            if pair is None or pair[1] != feature:
                raise ValueError("technical_snapshot_v4_indicator_fact_unresolved")
        references.append(TechnicalFactReferenceV4(
            ordinal=ordinal,
            feature_date=fact.feature_date,
            feature_key=feature.key,
            reference_kind=reference_kind,
            source_fingerprint_sha256=feature.source_fingerprint_sha256,
            source_id=feature.source_id,
            method_id=feature.method_id,
            method_version=feature.method_version,
            unit=feature.unit,
            parameters=feature.parameters,
            lineage_verified=feature.lineage_verified,
        ))
    return DailyMarketTechnicalRuleEvidenceV4(
        key=result.key,
        method_id=result.method_id,
        version=result.version,
        state=result.state,
        parameters=result.parameters,
        supports=result.supports,
        counterevidence=result.counterevidence,
        unknown_reasons=result.unknown_reasons,
        raw_fact_refs=tuple(references),
        numerator=result.numerator,
        denominator=result.denominator,
        ratio=result.ratio,
        stock_code=result.stock_code,
        decision_date=result.decision_date,
        decision_cutoff=result.decision_cutoff,
        feature_date=result.feature_date,
        previous_feature_date=result.previous_feature_date,
        source_identity=result.source_identity,
        source_window_fingerprint_sha256=result.source_window_fingerprint_sha256,
        lookahead_check=result.lookahead_check,
        availability_result=result.availability_result,
    )


def _validate_snapshot_payload(payload: Mapping[str, Any], *, verify_identity: bool) -> None:
    if set(payload) != _SNAPSHOT_KEYS or payload.get("schema_version") != DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_SCHEMA_V4:
        raise ValueError("technical_snapshot_v4_schema_invalid")
    _reject_float_tree(payload)
    if (
        not isinstance(payload.get("stock_code"), str)
        or not payload["stock_code"]
        or len(payload["stock_code"]) > DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_STOCK_CODE_CHARS
        or payload["stock_code"].strip() != payload["stock_code"]
        or re.fullmatch(r"[A-Z0-9]{1,16}", payload["stock_code"]) is None
    ):
        raise ValueError("technical_snapshot_v4_stock_invalid")
    decision_day = _parse_iso_date(payload.get("decision_date"), "decision_date")
    cutoff = _parse_aware_datetime(payload.get("decision_cutoff"), "decision_cutoff")
    if cutoff.astimezone(_TAIPEI).date() != decision_day or cutoff.astimezone(_TAIPEI).time() < _MIN_CUTOFF:
        raise ValueError("technical_snapshot_v4_cutoff_invalid")
    clock = payload.get("source_clock")
    if not isinstance(clock, Mapping):
        raise ValueError("technical_snapshot_v4_source_clock_invalid")
    _validate_source_clock_payload(clock)
    clock_json = _canonical_json(clock)
    clock_sha = _sha256_bytes(clock_json.encode("utf-8"))
    if payload.get("source_clock_sha256") != clock_sha:
        raise ValueError("technical_snapshot_v4_source_clock_hash_mismatch")
    if (
        clock["database_path"] == ""
        or len(cast(str, clock["database_path"])) > DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_PATH_CHARS
        or clock["source_id"] != "sqlite.daily_prices"
        or clock["decision_date"] != decision_day.isoformat()
        or clock["decision_cutoff"] != cutoff.isoformat()
    ):
        raise ValueError("technical_snapshot_v4_source_clock_mismatch")
    source_id = payload.get("source_id")
    if source_id != "sqlite.daily_prices":
        raise ValueError("technical_snapshot_v4_source_id_invalid")
    for name in (
        "source_identity", "schema_identity_sha256", "source_pin_sha256",
        "raw_source_window_fingerprint_sha256", "source_window_fingerprint_sha256",
        "cutoff_guard_version", "method_contracts_sha256", "snapshot_identity_sha256",
    ):
        value = payload.get(name)
        if name.endswith("sha256") and not _is_sha256(value):
            raise ValueError(f"technical_snapshot_v4_{name}_invalid")
    if (
        payload.get("schema_identity_sha256") != clock["schema_identity_sha256"]
        or payload.get("source_pin_sha256") != clock["source_pin_sha256"]
        or payload.get("cutoff_guard_version") != DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION
        or clock["cutoff_guard_version"] != DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION
    ):
        raise ValueError("technical_snapshot_v4_source_binding_mismatch")
    calc = payload.get("calculation")
    if not isinstance(calc, Mapping) or set(calc) != _CALCULATION_KEYS:
        raise ValueError("technical_snapshot_v4_calculation_invalid")
    if (
        calc.get("method_id") != CAUSAL_INDICATOR_LINEAGE_METHOD_ID
        or calc.get("method_version") != CAUSAL_INDICATOR_LINEAGE_VERSION
        or not _is_sha256(calc.get("identity_sha256"))
        or not isinstance(calc.get("talib_version"), str)
        or not calc.get("talib_version")
        or len(calc["talib_version"]) > 128
    ):
        raise ValueError("technical_snapshot_v4_calculation_mismatch")
    validate_daily_market_technical_calculation_binding(
        calc["binding"], expected_identity=cast(str, calc["identity_sha256"]),
        expected_talib_version=cast(str, calc["talib_version"]),
    )
    availability = payload.get("availability")
    if (
        not isinstance(availability, Mapping)
        or set(availability) != _AVAILABILITY_KEYS
        or availability.get("source_available_at") is not None
        or availability.get("availability_status") != "unknown"
        or availability.get("historical_pit_eligible") is not False
        or payload.get("observed_prefix_contiguous") not in {True, False}
    ):
        raise ValueError("technical_snapshot_v4_availability_invalid")
    if payload.get("policy") != _POLICY:
        raise ValueError("technical_snapshot_v4_policy_invalid")

    contracts = payload.get("method_contracts")
    contract_sha = payload.get("method_contracts_sha256")
    validated_contracts = validate_daily_market_technical_method_contract_v4(
        contracts if isinstance(contracts, Mapping) else {},
        expected_sha256=cast(str, contract_sha),
    )
    if daily_market_technical_method_contract_v4_sha256(validated_contracts) != contract_sha:
        raise ValueError("technical_snapshot_v4_method_contract_hash_mismatch")

    raw_rows = payload.get("raw_rows")
    if not isinstance(raw_rows, list) or len(raw_rows) > DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS:
        raise ValueError("technical_snapshot_v4_raw_rows_invalid")
    rows = tuple(_row_from_dict(item) for item in raw_rows)
    if any(row.stock_code != payload["stock_code"] for row in rows):
        raise ValueError("technical_snapshot_v4_raw_stock_mismatch")
    if any(row.feature_date is not None and row.feature_date > decision_day for row in rows):
        raise ValueError("technical_snapshot_v4_future_source_date")
    if tuple(sorted(rows, key=lambda item: (item.feature_date or date.min, item.raw_date, item.raw_values))) != rows:
        raise ValueError("technical_snapshot_v4_raw_rows_not_sorted")
    raw_hash = _sha256_json({
        "schema_version": DAILY_MARKET_TECHNICAL_SOURCE_SCHEMA,
        "schema_identity_sha256": payload["schema_identity_sha256"],
        "stock_code": payload["stock_code"],
        "decision_date": decision_day.isoformat(),
        "decision_cutoff": cutoff.isoformat(),
        "cutoff_guard_version": payload["cutoff_guard_version"],
        "rows": [row.to_dict() for row in rows],
    })
    if raw_hash != payload["raw_source_window_fingerprint_sha256"]:
        raise ValueError("technical_snapshot_v4_raw_window_hash_mismatch")
    expected_source_id = _source_identity(
        database_path=cast(str, clock["database_path"]),
        source_pin_sha256=cast(str, payload["source_pin_sha256"]),
        schema_identity_sha256=cast(str, payload["schema_identity_sha256"]),
        stock_code=cast(str, payload["stock_code"]),
        decision_date=decision_day,
        decision_cutoff=cutoff,
        raw_source_window_fingerprint_sha256=cast(str, payload["raw_source_window_fingerprint_sha256"]),
        calculation_identity_sha256=cast(str, calc["identity_sha256"]),
    )
    if payload["source_identity"] != expected_source_id:
        raise ValueError("technical_snapshot_v4_source_identity_mismatch")

    raw_pins = payload.get("session_pins")
    if not isinstance(raw_pins, list) or len(raw_pins) > DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS:
        raise ValueError("technical_snapshot_v4_session_pins_invalid")
    pins = tuple(_session_pin_from_dict(item) for item in raw_pins)
    if tuple(item.feature_date for item in pins) != tuple(sorted(item.feature_date for item in pins)):
        raise ValueError("technical_snapshot_v4_session_pins_not_sorted")
    rows_by_ref: dict[tuple[date | None, str], DailyMarketTechnicalSourceRow] = {
        (row.feature_date, row.row_fingerprint_sha256): row for row in rows
    }
    for pin in pins:
        if pin.feature_date > decision_day or (pin.feature_date, pin.source_fingerprint_sha256) not in rows_by_ref:
            raise ValueError("technical_snapshot_v4_session_pin_unresolved")
    is_contiguous = payload["observed_prefix_contiguous"]
    if is_contiguous and (
        not pins
        or len({item.feature_date for item in pins}) != len(pins)
        or any(not item.pin_verified for item in pins)
    ):
        raise ValueError("technical_snapshot_v4_contiguous_prefix_invalid")
    expected_window_hash = _sha256_json({
        "stock_code": payload["stock_code"],
        "decision_date": decision_day.isoformat(),
        "source_identity": payload["source_identity"],
        "sessions": [
            {
                "feature_date": item.feature_date.isoformat(),
                "session_fingerprint_sha256": item.session_fingerprint_sha256,
            }
            for item in pins
        ],
    })
    if expected_window_hash != payload["source_window_fingerprint_sha256"]:
        raise ValueError("technical_snapshot_v4_window_hash_mismatch")

    raw_feature_sessions = payload.get("feature_sessions")
    if not isinstance(raw_feature_sessions, list) or len(raw_feature_sessions) > 2:
        raise ValueError("technical_snapshot_v4_feature_sessions_invalid")
    feature_sessions = tuple(_session_from_dict(item) for item in raw_feature_sessions)
    expected_recent = pins[-2:]
    if len(feature_sessions) != len(expected_recent):
        raise ValueError("technical_snapshot_v4_feature_session_count_mismatch")
    for session, pin in zip(feature_sessions, expected_recent, strict=True):
        if (
            session.stock_code != payload["stock_code"]
            or session.source_identity != payload["source_identity"]
            or session.feature_date != pin.feature_date
            or session.source_fingerprint_sha256 != pin.source_fingerprint_sha256
            or session.pin_verified != pin.pin_verified
            or technical_session_fingerprint_sha256(session) != pin.session_fingerprint_sha256
        ):
            raise ValueError("technical_snapshot_v4_feature_session_pin_mismatch")
        _validate_feature_session(session, decision_day)
        source_row = rows_by_ref.get(
            (session.feature_date, session.source_fingerprint_sha256)
        )
        volume_feature = next(
            (feature for feature in session.features if feature.key == "volume_shares"),
            None,
        )
        if source_row is None or volume_feature is None:
            raise ValueError("technical_snapshot_v4_session_source_row_missing")
        if (
            volume_feature.value != (
                source_row.volume_shares if source_row.volume_valid else None
            )
            or volume_feature.state != (
                "observed" if source_row.volume_valid else "unknown"
            )
            or volume_feature.lineage_verified is not (
                source_row.volume_valid and session.pin_verified
            )
        ):
            raise ValueError("technical_snapshot_v4_session_volume_binding_mismatch")

    rules = payload.get("rules")
    if not isinstance(rules, list) or tuple(
        item.get("key") for item in rules if isinstance(item, Mapping)
    ) != DAILY_MARKET_TECHNICAL_RULE_KEYS_V4:
        raise ValueError("technical_snapshot_v4_rules_invalid")
    parsed_rules = tuple(_rule_from_dict(item) for item in rules)
    feature_refs = {
        (session.feature_date, session.source_fingerprint_sha256, feature.key): feature
        for session in feature_sessions
        for feature in session.features
    }
    _validate_rules(
        parsed_rules,
        stock_code=cast(str, payload["stock_code"]),
        decision_date=decision_day,
        decision_cutoff=cutoff,
        source_identity=cast(str, payload["source_identity"]),
        source_window_fingerprint_sha256=cast(str, payload["source_window_fingerprint_sha256"]),
        pins=pins,
        rows_by_ref=rows_by_ref,
        feature_refs=feature_refs,
        observed_prefix_contiguous=cast(bool, payload["observed_prefix_contiguous"]),
        contract=validated_contracts,
    )
    _verify_saved_rule_semantics(
        parsed_rules,
        stock_code=cast(str, payload["stock_code"]),
        decision_date=decision_day,
        decision_cutoff=cutoff,
        source_identity=cast(str, payload["source_identity"]),
        observed_prefix_contiguous=cast(bool, payload["observed_prefix_contiguous"]),
        rows=rows,
        pins=pins,
        feature_sessions=feature_sessions,
    )
    _validate_fact_ref_limits(parsed_rules)
    if verify_identity:
        claimed = payload.get("snapshot_identity_sha256")
        if not _is_sha256(claimed) or _identity_sha256(payload) != claimed:
            raise ValueError("technical_snapshot_v4_identity_mismatch")
    _enforce_json_size(payload)


def _validate_source_clock_payload(clock: Mapping[str, Any]) -> None:
    if set(clock) != _SOURCE_PIN_KEYS:
        raise ValueError("technical_snapshot_v4_source_clock_fields_invalid")
    database_path = clock.get("database_path")
    if (
        not isinstance(database_path, str)
        or not database_path
        or len(database_path) > DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_PATH_CHARS
        or not Path(database_path).is_absolute()
        or "\x00" in database_path
    ):
        raise ValueError("technical_snapshot_v4_source_database_path_invalid")
    if clock.get("source_id") != "sqlite.daily_prices":
        raise ValueError("technical_snapshot_v4_source_clock_source_invalid")
    if not _is_sha256(clock.get("schema_identity_sha256")) or not _is_sha256(clock.get("source_pin_sha256")):
        raise ValueError("technical_snapshot_v4_source_clock_hash_invalid")
    raw_pin = clock.get("source_file_pin")
    if not isinstance(raw_pin, list) or len(raw_pin) != 2:
        raise ValueError("technical_snapshot_v4_source_file_pin_invalid")
    normalized_pin: list[list[object]] = []
    for index, item in enumerate(raw_pin):
        if not isinstance(item, list) or len(item) not in ({5} if index == 0 else {1, 5}):
            raise ValueError("technical_snapshot_v4_source_file_pin_invalid")
        if item[0] != (database_path if index == 0 else database_path + "-wal"):
            raise ValueError("technical_snapshot_v4_source_file_pin_path_mismatch")
        if len(item) == 5 and any(type(value) is not int or value < 0 for value in item[1:]):
            raise ValueError("technical_snapshot_v4_source_file_pin_stat_invalid")
        normalized_pin.append(list(item))
    if _sha256_json(normalized_pin) != clock["source_pin_sha256"]:
        raise ValueError("technical_snapshot_v4_source_pin_hash_mismatch")
    day = _parse_iso_date(clock.get("decision_date"), "source_clock.decision_date")
    cutoff = _parse_aware_datetime(clock.get("decision_cutoff"), "source_clock.decision_cutoff")
    if cutoff.astimezone(_TAIPEI).date() != day or cutoff.astimezone(_TAIPEI).time() < _MIN_CUTOFF:
        raise ValueError("technical_snapshot_v4_source_clock_cutoff_invalid")
    if (
        clock.get("cutoff_guard_version") != DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION
        or clock.get("source_available_at") is not None
        or clock.get("availability_status") != "unknown"
        or clock.get("historical_pit_eligible") is not False
    ):
        raise ValueError("technical_snapshot_v4_source_clock_policy_invalid")


def _row_from_dict(value: object) -> DailyMarketTechnicalSourceRow:
    if not isinstance(value, Mapping) or set(value) != _ROW_KEYS:
        raise ValueError("technical_snapshot_v4_raw_row_fields_invalid")
    raw_values = value.get("raw_values")
    if not isinstance(raw_values, Mapping) or set(raw_values) != set(_ROW_RAW_KEYS):
        raise ValueError("technical_snapshot_v4_raw_values_invalid")
    pairs: list[tuple[str, str]] = []
    for key in _ROW_RAW_KEYS:
        token = raw_values[key]
        if not isinstance(token, str):
            raise ValueError("technical_snapshot_v4_raw_token_invalid")
        pairs.append((key, token))
    raw_date_value = value.get("raw_date")
    if (
        not isinstance(raw_date_value, str)
        or len(raw_date_value.encode("utf-8")) > 64
    ):
        raise ValueError("technical_snapshot_v4_raw_date_invalid")
    feature_date_value = value.get("feature_date")
    feature_date = None if feature_date_value is None else _parse_iso_date(feature_date_value, "raw_row.feature_date")
    row = DailyMarketTechnicalSourceRow(
        raw_date=raw_date_value,
        feature_date=feature_date,
        stock_code=_require_bounded_text(value.get("stock_code"), DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_STOCK_CODE_CHARS, "stock_code"),
        open_price=_parse_decimal(value.get("open_price"), "open_price"),
        high_price=_parse_decimal(value.get("high_price"), "high_price"),
        low_price=_parse_decimal(value.get("low_price"), "low_price"),
        close_price=_parse_decimal(value.get("close_price"), "close_price"),
        volume_shares=_parse_decimal(value.get("volume_shares"), "volume_shares"),
        raw_values=tuple(pairs),
        row_fingerprint_sha256=_require_sha(value.get("row_fingerprint_sha256"), "row_fingerprint_sha256"),
        ohlc_valid=_require_bool(value.get("ohlc_valid"), "ohlc_valid"),
        volume_valid=_require_bool(value.get("volume_valid"), "volume_valid"),
        invalid_reasons=_parse_text_tuple(value.get("invalid_reasons"), max_count=8, max_bytes=128),
    )
    _validate_source_row(row, expected_stock_code=row.stock_code)
    return row


def _session_pin_from_dict(value: object) -> TechnicalSessionPinV4:
    if not isinstance(value, Mapping) or set(value) != _SESSION_PIN_KEYS:
        raise ValueError("technical_snapshot_v4_session_pin_fields_invalid")
    return TechnicalSessionPinV4(
        feature_date=_parse_iso_date(value.get("feature_date"), "session_pin.feature_date"),
        source_fingerprint_sha256=_require_sha(value.get("source_fingerprint_sha256"), "session_pin.source_fingerprint_sha256"),
        session_fingerprint_sha256=_require_sha(value.get("session_fingerprint_sha256"), "session_pin.session_fingerprint_sha256"),
        pin_verified=_require_bool(value.get("pin_verified"), "session_pin.pin_verified"),
    )


def _session_from_dict(value: object) -> TechnicalObservedSession:
    if not isinstance(value, Mapping) or set(value) != _SESSION_KEYS:
        raise ValueError("technical_snapshot_v4_session_fields_invalid")
    feature_date = _parse_iso_date(value.get("feature_date"), "feature_session.feature_date")
    raw_features = value.get("features")
    if not isinstance(raw_features, list) or tuple(
        item.get("key") for item in raw_features if isinstance(item, Mapping)
    ) != DAILY_MARKET_TECHNICAL_FEATURE_KEYS_V4:
        raise ValueError("technical_snapshot_v4_session_feature_keys_invalid")
    features = tuple(_feature_from_dict(item) for item in raw_features)
    session = TechnicalObservedSession(
        stock_code=_require_bounded_text(value.get("stock_code"), DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_STOCK_CODE_CHARS, "feature_session.stock_code"),
        feature_date=feature_date,
        source_identity=_require_bounded_text(value.get("source_identity"), 4096, "feature_session.source_identity"),
        source_fingerprint_sha256=_require_sha(value.get("source_fingerprint_sha256"), "feature_session.source_fingerprint_sha256"),
        features=features,
        pin_verified=_require_bool(value.get("pin_verified"), "feature_session.pin_verified"),
    )
    if technical_session_fingerprint_sha256(session) != _require_sha(value.get("session_fingerprint_sha256"), "session_fingerprint_sha256"):
        raise ValueError("technical_snapshot_v4_session_fingerprint_mismatch")
    return session


def _feature_from_dict(value: object) -> TechnicalFeatureEvidence:
    if not isinstance(value, Mapping) or set(value) != _FEATURE_KEYS:
        raise ValueError("technical_snapshot_v4_feature_fields_invalid")
    key = value.get("key")
    if not isinstance(key, str) or key not in _SESSION_FEATURE_CONTRACTS:
        raise ValueError("technical_snapshot_v4_feature_key_invalid")
    contract = _SESSION_FEATURE_CONTRACTS[key]
    parameters = _parameters_from_json(value.get("parameters"), "feature.parameters")
    expected_parameters = contract["parameters"]
    if _parameters_to_json(parameters) != expected_parameters:
        raise ValueError("technical_snapshot_v4_feature_parameters_mismatch")
    expected_warmup = contract["warmup_required_sessions"]
    if value.get("warmup_required_sessions") != expected_warmup:
        raise ValueError("technical_snapshot_v4_feature_warmup_mismatch")
    state = value.get("state")
    if state not in {"observed", "unknown"}:
        raise ValueError("technical_snapshot_v4_feature_state_invalid")
    decimal_value = _parse_decimal(value.get("value"), "feature.value")
    if (state == "observed") != (decimal_value is not None):
        raise ValueError("technical_snapshot_v4_feature_value_state_mismatch")
    if decimal_value is not None:
        _validate_feature_value(key, decimal_value)
    if expected_warmup is None:
        if any(value.get(name) is not None for name in (
            "warmup_required_sessions", "warmup_observed_sessions", "warmup_contiguous"
        )):
            raise ValueError("technical_snapshot_v4_volume_warmup_invalid")
    else:
        observed = value.get("warmup_observed_sessions")
        contiguous = value.get("warmup_contiguous")
        if type(observed) is not int or not 0 <= observed <= DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS:
            raise ValueError("technical_snapshot_v4_feature_warmup_count_invalid")
        if type(contiguous) is not bool:
            raise ValueError("technical_snapshot_v4_feature_warmup_contiguous_invalid")
        if state == "observed" and (observed < expected_warmup or not contiguous):
            raise ValueError("technical_snapshot_v4_observed_feature_warmup_invalid")
    return TechnicalFeatureEvidence(
        key=key,
        value=decimal_value,
        unit=_require_exact_text(value.get("unit"), contract["unit"], "feature.unit"),
        state=cast(SnapshotFeatureState, state),
        source_id=_require_exact_text(value.get("source_id"), contract["source_id"], "feature.source_id"),
        source_fingerprint_sha256=_require_sha(value.get("source_fingerprint_sha256"), "feature.source_fingerprint_sha256"),
        method_id=_require_exact_text(value.get("method_id"), contract["method_id"], "feature.method_id"),
        method_version=_require_exact_text(value.get("method_version"), contract["method_version"], "feature.method_version"),
        parameters=parameters,
        lineage_verified=_require_bool(value.get("lineage_verified"), "feature.lineage_verified"),
        warmup_required_sessions=cast(int | None, expected_warmup),
        warmup_observed_sessions=cast(int | None, value.get("warmup_observed_sessions")),
        warmup_contiguous=cast(bool | None, value.get("warmup_contiguous")),
    )


def _validate_feature_session(session: TechnicalObservedSession, decision_day: date) -> None:
    if session.feature_date > decision_day or len(session.features) != len(DAILY_MARKET_TECHNICAL_FEATURE_KEYS_V4):
        raise ValueError("technical_snapshot_v4_feature_session_date_invalid")
    for feature, key in zip(session.features, DAILY_MARKET_TECHNICAL_FEATURE_KEYS_V4, strict=True):
        if feature.key != key or feature.source_fingerprint_sha256 != session.source_fingerprint_sha256:
            raise ValueError("technical_snapshot_v4_feature_session_binding_invalid")
        _validate_feature_value_if_observed(feature)


def _validate_feature_value_if_observed(feature: TechnicalFeatureEvidence) -> None:
    if feature.value is not None:
        _validate_feature_value(feature.key, feature.value)


def _validate_feature_value(key: str, value: Decimal) -> None:
    if not value.is_finite():
        raise ValueError("technical_snapshot_v4_feature_nonfinite")
    if key in {"MA5", "MA20"} and value <= 0:
        raise ValueError("technical_snapshot_v4_moving_average_nonpositive")
    if key in {"slowk", "slowd"} and not Decimal("0") <= value <= Decimal("100"):
        raise ValueError("technical_snapshot_v4_stochastic_out_of_range")
    if key == "volume_shares" and (value < 0 or value != value.to_integral_value()):
        raise ValueError("technical_snapshot_v4_volume_invalid")


def _session_to_dict(session: TechnicalObservedSession) -> dict[str, object]:
    return {
        "stock_code": session.stock_code,
        "feature_date": session.feature_date.isoformat(),
        "source_identity": session.source_identity,
        "source_fingerprint_sha256": session.source_fingerprint_sha256,
        "pin_verified": session.pin_verified,
        "features": [_feature_to_dict(item) for item in session.features],
        "session_fingerprint_sha256": technical_session_fingerprint_sha256(session),
    }


def _feature_to_dict(feature: TechnicalFeatureEvidence) -> dict[str, object]:
    return {
        "key": feature.key,
        "value": _decimal_text(feature.value),
        "unit": feature.unit,
        "state": feature.state,
        "source_id": feature.source_id,
        "source_fingerprint_sha256": feature.source_fingerprint_sha256,
        "method_id": feature.method_id,
        "method_version": feature.method_version,
        "parameters": _parameters_to_json(feature.parameters),
        "lineage_verified": feature.lineage_verified,
        "warmup_required_sessions": feature.warmup_required_sessions,
        "warmup_observed_sessions": feature.warmup_observed_sessions,
        "warmup_contiguous": feature.warmup_contiguous,
    }


def _rule_from_dict(value: object) -> DailyMarketTechnicalRuleEvidenceV4:
    if not isinstance(value, Mapping) or set(value) != _RULE_KEYS:
        raise ValueError("technical_snapshot_v4_rule_fields_invalid")
    key = value.get("key")
    if not isinstance(key, str) or key not in _RULE_CONTRACTS:
        raise ValueError("technical_snapshot_v4_rule_key_invalid")
    contract = _RULE_CONTRACTS[key]
    parameters = _parameters_from_json(value.get("parameters"), "rule.parameters")
    if _parameters_to_json(parameters) != contract["parameters"]:
        raise ValueError("technical_snapshot_v4_rule_parameters_mismatch")
    state = value.get("state")
    if state not in {"match", "no_match", "unknown"}:
        raise ValueError("technical_snapshot_v4_rule_state_invalid")
    refs_raw = value.get("raw_fact_refs")
    if not isinstance(refs_raw, list) or len(refs_raw) > DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_FACTS_PER_RULE:
        raise ValueError("technical_snapshot_v4_rule_fact_refs_invalid")
    references = tuple(_fact_ref_from_dict(item) for item in refs_raw)
    supports = _parse_text_tuple(value.get("supports"), max_count=8, max_bytes=DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_EXPLANATION_BYTES)
    counterevidence = _parse_text_tuple(value.get("counterevidence"), max_count=8, max_bytes=DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_EXPLANATION_BYTES)
    unknown_reasons = _parse_text_tuple(value.get("unknown_reasons"), max_count=DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_REASON_COUNT, max_bytes=256)
    if (state == "unknown") != bool(unknown_reasons):
        raise ValueError("technical_snapshot_v4_rule_unknown_reason_mismatch")
    if (
        value.get("usage") != "current_restated_research_only"
        or value.get("pit_eligible") is not False
    ):
        raise ValueError("technical_snapshot_v4_rule_policy_invalid")
    return DailyMarketTechnicalRuleEvidenceV4(
        key=key,
        method_id=_require_exact_text(value.get("method_id"), contract["method_id"], "rule.method_id"),
        version=_require_exact_text(value.get("version"), contract["version"], "rule.version"),
        state=cast(SnapshotRuleState, state),
        parameters=parameters,
        supports=supports,
        counterevidence=counterevidence,
        unknown_reasons=unknown_reasons,
        raw_fact_refs=references,
        numerator=_parse_decimal(value.get("numerator"), "rule.numerator"),
        denominator=_parse_decimal(value.get("denominator"), "rule.denominator"),
        ratio=_parse_decimal(value.get("ratio"), "rule.ratio"),
        stock_code=_require_bounded_text(value.get("stock_code"), DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_STOCK_CODE_CHARS, "rule.stock_code"),
        decision_date=_parse_iso_date(value.get("decision_date"), "rule.decision_date"),
        decision_cutoff=_parse_aware_datetime(value.get("decision_cutoff"), "rule.decision_cutoff"),
        feature_date=None if value.get("feature_date") is None else _parse_iso_date(value.get("feature_date"), "rule.feature_date"),
        previous_feature_date=None if value.get("previous_feature_date") is None else _parse_iso_date(value.get("previous_feature_date"), "rule.previous_feature_date"),
        source_identity=_require_bounded_text(value.get("source_identity"), 4096, "rule.source_identity"),
        source_window_fingerprint_sha256=_require_sha(value.get("source_window_fingerprint_sha256"), "rule.source_window_fingerprint_sha256"),
        lookahead_check=_require_enum(value.get("lookahead_check"), _LOOKAHEAD_CHECKS, "rule.lookahead_check"),
        availability_result=_require_enum(value.get("availability_result"), _AVAILABILITY_RESULTS, "rule.availability_result"),
    )


def _fact_ref_from_dict(value: object) -> TechnicalFactReferenceV4:
    if not isinstance(value, Mapping) or set(value) != _FACT_REF_KEYS:
        raise ValueError("technical_snapshot_v4_fact_ref_fields_invalid")
    reference_kind = value.get("reference_kind")
    if reference_kind not in {"session_feature", "raw_volume_row"}:
        raise ValueError("technical_snapshot_v4_fact_ref_kind_invalid")
    feature_key = value.get("feature_key")
    if not isinstance(feature_key, str) or feature_key not in _SESSION_FEATURE_CONTRACTS:
        raise ValueError("technical_snapshot_v4_fact_ref_feature_invalid")
    parameters = _parameters_from_json(value.get("parameters"), "fact_ref.parameters")
    contract = _SESSION_FEATURE_CONTRACTS[feature_key]
    if _parameters_to_json(parameters) != contract["parameters"]:
        raise ValueError("technical_snapshot_v4_fact_ref_parameters_mismatch")
    ordinal = value.get("ordinal")
    if type(ordinal) is not int or not 0 <= ordinal < DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_FACTS_PER_RULE:
        raise ValueError("technical_snapshot_v4_fact_ref_ordinal_invalid")
    return TechnicalFactReferenceV4(
        ordinal=ordinal,
        feature_date=_parse_iso_date(value.get("feature_date"), "fact_ref.feature_date"),
        feature_key=feature_key,
        reference_kind=cast(ReferenceKind, reference_kind),
        source_fingerprint_sha256=_require_sha(value.get("source_fingerprint_sha256"), "fact_ref.source_fingerprint_sha256"),
        source_id=_require_exact_text(value.get("source_id"), contract["source_id"], "fact_ref.source_id"),
        method_id=_require_exact_text(value.get("method_id"), contract["method_id"], "fact_ref.method_id"),
        method_version=_require_exact_text(value.get("method_version"), contract["method_version"], "fact_ref.method_version"),
        unit=_require_exact_text(value.get("unit"), contract["unit"], "fact_ref.unit"),
        parameters=parameters,
        lineage_verified=_require_bool(value.get("lineage_verified"), "fact_ref.lineage_verified"),
    )


def _validate_rules(
    rules: tuple[DailyMarketTechnicalRuleEvidenceV4, ...],
    *,
    stock_code: str,
    decision_date: date,
    decision_cutoff: datetime,
    source_identity: str,
    source_window_fingerprint_sha256: str,
    pins: tuple[TechnicalSessionPinV4, ...],
    rows_by_ref: Mapping[tuple[date | None, str], DailyMarketTechnicalSourceRow],
    feature_refs: Mapping[tuple[date, str, str], TechnicalFeatureEvidence],
    observed_prefix_contiguous: bool,
    contract: Mapping[str, Any],
) -> None:
    rule_contracts = {item["key"]: item for item in contract["rules"]}
    expected_lookahead = (
        "feature_dates_within_decision_date"
        if observed_prefix_contiguous
        else "observed_prefix_not_contiguous"
    )
    for rule in rules:
        if (
            rule.stock_code != stock_code
            or rule.decision_date != decision_date
            or rule.decision_cutoff.isoformat() != decision_cutoff.isoformat()
            or rule.source_identity != source_identity
            or rule.source_window_fingerprint_sha256 != source_window_fingerprint_sha256
            or rule.availability_result != "available_at_unknown"
            or rule.lookahead_check != expected_lookahead
        ):
            raise ValueError("technical_snapshot_v4_rule_binding_mismatch")
        if rule.feature_date is not None and rule.feature_date > decision_date:
            raise ValueError("technical_snapshot_v4_rule_future_date")
        if rule.previous_feature_date is not None and rule.previous_feature_date > decision_date:
            raise ValueError("technical_snapshot_v4_rule_future_previous_date")
        if tuple(item.ordinal for item in rule.raw_fact_refs) != tuple(range(len(rule.raw_fact_refs))):
            raise ValueError("technical_snapshot_v4_rule_fact_ref_order_invalid")
        expected_contract = rule_contracts[rule.key]
        expected_features = tuple(expected_contract["required_feature_keys"])
        current_pin = pins[-1] if pins else None
        previous_pin = pins[-2] if len(pins) >= 2 else None
        expected_current_date = current_pin.feature_date if current_pin else None
        expected_previous_date = previous_pin.feature_date if previous_pin else None
        if (
            rule.feature_date != expected_current_date
            or rule.previous_feature_date != expected_previous_date
        ):
            raise ValueError("technical_snapshot_v4_rule_session_date_mismatch")
        periods = expected_contract["parameters"].get("window_sessions")
        if periods is not None:
            expected_count = periods if len(pins) >= periods else 0
            if len(rule.raw_fact_refs) != expected_count:
                raise ValueError("technical_snapshot_v4_volume_fact_count_mismatch")
            expected_refs = tuple(pins[-periods:]) if expected_count else ()
            if tuple(
                (item.feature_date, item.source_fingerprint_sha256)
                for item in rule.raw_fact_refs
            ) != tuple(
                (item.feature_date, item.source_fingerprint_sha256)
                for item in expected_refs
            ):
                raise ValueError("technical_snapshot_v4_volume_fact_order_mismatch")
        else:
            expected_count = len(expected_features) * 2 if len(pins) >= 2 else 0
            if len(rule.raw_fact_refs) != expected_count:
                raise ValueError("technical_snapshot_v4_cross_fact_count_mismatch")
            expected_ref_order = tuple(
                (session.feature_date, feature_key)
                for session in (
                    (previous_pin, current_pin)
                    if previous_pin is not None and current_pin is not None
                    else ()
                )
                for feature_key in expected_features
            )
            if tuple(
                (item.feature_date, item.feature_key)
                for item in rule.raw_fact_refs
            ) != expected_ref_order:
                raise ValueError("technical_snapshot_v4_cross_fact_order_mismatch")
        for reference in rule.raw_fact_refs:
            if reference.feature_key not in expected_features:
                raise ValueError("technical_snapshot_v4_rule_fact_key_mismatch")
            if reference.reference_kind == "session_feature":
                feature = feature_refs.get(
                    (
                        reference.feature_date,
                        reference.source_fingerprint_sha256,
                        reference.feature_key,
                    )
                )
                if feature is None or not _fact_ref_matches_feature(reference, feature):
                    raise ValueError("technical_snapshot_v4_rule_feature_ref_mismatch")
            else:
                row = rows_by_ref.get((reference.feature_date, reference.source_fingerprint_sha256))
                if reference.feature_key != "volume_shares" or row is None:
                    raise ValueError("technical_snapshot_v4_rule_volume_ref_mismatch")
                if (
                    reference.source_id != VOLUME_SOURCE_ID
                    or reference.method_id != RAW_VOLUME_LINEAGE_METHOD_ID
                    or reference.method_version != RAW_VOLUME_LINEAGE_VERSION
                    or reference.unit != VOLUME_UNIT
                    or reference.lineage_verified is not (row.volume_valid and _pin_verified_for(pins, row))
                ):
                    raise ValueError("technical_snapshot_v4_rule_volume_lineage_mismatch")
        if not rule.key.startswith("volume_ratio_") and any(
            value is not None for value in (rule.numerator, rule.denominator, rule.ratio)
        ):
            raise ValueError("technical_snapshot_v4_cross_ratio_invalid")


def _verify_saved_rule_semantics(
    rules: tuple[DailyMarketTechnicalRuleEvidenceV4, ...],
    *,
    stock_code: str,
    decision_date: date,
    decision_cutoff: datetime,
    source_identity: str,
    observed_prefix_contiguous: bool,
    rows: tuple[DailyMarketTechnicalSourceRow, ...],
    pins: tuple[TechnicalSessionPinV4, ...],
    feature_sessions: tuple[TechnicalObservedSession, ...],
) -> None:
    """用保存證據重建暫存窗口，沿既有純 rules evaluator 核五個結果。"""

    rows_by_ref = {
        (row.feature_date, row.row_fingerprint_sha256): row for row in rows
    }
    saved_sessions = {
        (session.feature_date, session.source_fingerprint_sha256): session
        for session in feature_sessions
    }
    reconstructed_sessions: list[TechnicalObservedSession] = []
    for pin in pins:
        reference = (pin.feature_date, pin.source_fingerprint_sha256)
        saved = saved_sessions.get(reference)
        if saved is not None:
            reconstructed_sessions.append(saved)
            continue
        row = rows_by_ref.get(reference)
        if row is None:
            raise ValueError("technical_snapshot_v4_semantic_source_row_missing")
        reconstructed_sessions.append(
            _semantic_session_from_row(
                row,
                source_identity=source_identity,
                pin_verified=pin.pin_verified,
            )
        )

    session_tuple = tuple(reconstructed_sessions)
    semantic_window_fingerprint = technical_observation_window_fingerprint_sha256(
        stock_code=stock_code,
        decision_date=decision_date,
        source_identity=source_identity,
        sessions=session_tuple,
    )
    semantic_window = TechnicalObservationWindow(
        stock_code=stock_code,
        decision_date=decision_date,
        decision_cutoff=decision_cutoff,
        source_identity=source_identity,
        source_window_fingerprint_sha256=semantic_window_fingerprint,
        source_available_at=None,
        availability_status="unknown",
        sessions=session_tuple,
        observed_prefix_contiguous=observed_prefix_contiguous,
    )
    rebuilt_results = evaluate_daily_technical_rules(semantic_window)
    if tuple(item.key for item in rebuilt_results) != DAILY_MARKET_TECHNICAL_RULE_KEYS_V4:
        raise ValueError("technical_snapshot_v4_semantic_rule_set_invalid")

    features_by_ref = {
        (session.feature_date, session.source_fingerprint_sha256, feature.key): (
            session,
            feature,
        )
        for session in session_tuple
        for feature in session.features
    }
    for actual, result in zip(rules, rebuilt_results, strict=True):
        expected = _rule_evidence_from_result(
            result,
            stock_code=stock_code,
            decision_date=decision_date,
            decision_cutoff=decision_cutoff,
            source_identity=source_identity,
            source_window_fingerprint_sha256=semantic_window_fingerprint,
            rows_by_ref=rows_by_ref,
            features_by_ref=features_by_ref,
        )
        actual_dict = actual.to_dict()
        expected_dict = expected.to_dict()
        # 語義窗口只用保存的原始量能及末兩日完整指標，因此其指紋只存在於
        # 驗證暫存物件。原始完整指紋另由全部 session pins 核對並保留。
        actual_dict.pop("source_window_fingerprint_sha256")
        expected_dict.pop("source_window_fingerprint_sha256")
        if actual_dict != expected_dict:
            raise ValueError(
                f"technical_snapshot_v4_rule_semantics_mismatch:{actual.key}"
            )


def _semantic_session_from_row(
    row: DailyMarketTechnicalSourceRow,
    *,
    source_identity: str,
    pin_verified: bool,
) -> TechnicalObservedSession:
    """以原始成交股數補足舊列，早期指標明確保持 unknown。"""

    features: list[TechnicalFeatureEvidence] = []
    for key in DAILY_MARKET_TECHNICAL_FEATURE_KEYS_V4:
        contract = _SESSION_FEATURE_CONTRACTS[key]
        parameters = _parameters_from_json(contract["parameters"], "semantic.parameters")
        if key == "volume_shares":
            volume_is_observed = row.volume_valid and row.volume_shares is not None
            features.append(TechnicalFeatureEvidence(
                key=key,
                value=row.volume_shares if volume_is_observed else None,
                unit=cast(str, contract["unit"]),
                state="observed" if volume_is_observed else "unknown",
                source_id=cast(str, contract["source_id"]),
                source_fingerprint_sha256=row.row_fingerprint_sha256,
                method_id=cast(str, contract["method_id"]),
                method_version=cast(str, contract["method_version"]),
                parameters=parameters,
                lineage_verified=bool(volume_is_observed and pin_verified),
            ))
            continue
        warmup = cast(int, contract["warmup_required_sessions"])
        features.append(TechnicalFeatureEvidence(
            key=key,
            value=None,
            unit=cast(str, contract["unit"]),
            state="unknown",
            source_id=cast(str, contract["source_id"]),
            source_fingerprint_sha256=row.row_fingerprint_sha256,
            method_id=cast(str, contract["method_id"]),
            method_version=cast(str, contract["method_version"]),
            parameters=parameters,
            lineage_verified=False,
            warmup_required_sessions=warmup,
            warmup_observed_sessions=0,
            warmup_contiguous=False,
        ))
    if row.feature_date is None:
        raise ValueError("technical_snapshot_v4_semantic_feature_date_missing")
    return TechnicalObservedSession(
        stock_code=row.stock_code,
        feature_date=row.feature_date,
        source_identity=source_identity,
        source_fingerprint_sha256=row.row_fingerprint_sha256,
        features=tuple(features),
        pin_verified=pin_verified,
    )


def _fact_ref_matches_feature(
    reference: TechnicalFactReferenceV4,
    feature: TechnicalFeatureEvidence,
) -> bool:
    return (
        reference.reference_kind == "session_feature"
        and reference.source_fingerprint_sha256 == feature.source_fingerprint_sha256
        and reference.source_id == feature.source_id
        and reference.method_id == feature.method_id
        and reference.method_version == feature.method_version
        and reference.unit == feature.unit
        and reference.parameters == feature.parameters
        and reference.lineage_verified is feature.lineage_verified
    )


def _pin_verified_for(
    pins: Sequence[TechnicalSessionPinV4],
    row: DailyMarketTechnicalSourceRow,
) -> bool:
    return any(
        item.feature_date == row.feature_date
        and item.source_fingerprint_sha256 == row.row_fingerprint_sha256
        and item.pin_verified
        for item in pins
    )


def _validate_fact_ref_limits(rules: tuple[DailyMarketTechnicalRuleEvidenceV4, ...]) -> None:
    if len(rules) != len(DAILY_MARKET_TECHNICAL_RULE_KEYS_V4):
        raise ValueError("technical_snapshot_v4_rule_count_invalid")
    for rule in rules:
        if len(rule.raw_fact_refs) > DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_FACTS_PER_RULE:
            raise ValueError("technical_snapshot_v4_rule_fact_limit")


def _source_identity(
    *,
    database_path: str,
    source_pin_sha256: str,
    schema_identity_sha256: str,
    stock_code: str,
    decision_date: date,
    decision_cutoff: datetime,
    raw_source_window_fingerprint_sha256: str,
    calculation_identity_sha256: str,
) -> str:
    payload = {
        "database": database_path,
        "source_pin_sha256": source_pin_sha256,
        "schema_identity_sha256": schema_identity_sha256,
        "stock_code": stock_code,
        "decision_date": decision_date.isoformat(),
        "decision_cutoff": decision_cutoff.isoformat(),
        "cutoff_guard_version": DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
        "raw_source_window_fingerprint_sha256": raw_source_window_fingerprint_sha256,
        "calculation_identity_sha256": calculation_identity_sha256,
    }
    return f"{TECHNICAL_SOURCE_ID}:{_sha256_json(payload)}"


def _parse_parameters(value: object, field_name: str) -> tuple[tuple[str, ParameterValue], ...]:
    if not isinstance(value, Mapping):
        raise ValueError(f"technical_snapshot_v4_{field_name}_invalid")
    result: list[tuple[str, ParameterValue]] = []
    for key, item in value.items():
        if not isinstance(key, str) or not key or isinstance(item, bool) or not isinstance(item, (str, int)):
            raise ValueError(f"technical_snapshot_v4_{field_name}_invalid")
        result.append((key, item))
    return tuple(result)


def _parameters_from_json(value: object, field_name: str) -> tuple[tuple[str, ParameterValue], ...]:
    return _parse_parameters(value, field_name)


def _parameters_to_json(parameters: Sequence[tuple[str, ParameterValue]]) -> dict[str, str | int]:
    result: dict[str, str | int] = {}
    for key, value in parameters:
        if isinstance(value, Decimal):
            result[key] = _decimal_text(value) or "0"
        elif type(value) is int or isinstance(value, str):
            result[key] = value
        else:
            raise ValueError("technical_snapshot_v4_parameter_value_invalid")
    return result


def _parse_decimal(value: object, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError(f"technical_snapshot_v4_{field_name}_invalid")
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"technical_snapshot_v4_{field_name}_invalid") from exc
    if not decimal_value.is_finite() or _decimal_text(decimal_value) != value:
        raise ValueError(f"technical_snapshot_v4_{field_name}_noncanonical")
    return decimal_value


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("technical_snapshot_v4_decimal_invalid")
    rendered = format(value, "f")
    if len(rendered) > 128:
        raise ValueError("technical_snapshot_v4_decimal_limit")
    return rendered


def _parse_text_tuple(value: object, *, max_count: int, max_bytes: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > max_count:
        raise ValueError("technical_snapshot_v4_text_sequence_invalid")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or len(item.encode("utf-8")) > max_bytes:
            raise ValueError("technical_snapshot_v4_text_item_invalid")
        result.append(item)
    return tuple(result)


def _parse_iso_date(value: object, field_name: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"technical_snapshot_v4_{field_name}_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"technical_snapshot_v4_{field_name}_invalid") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"technical_snapshot_v4_{field_name}_noncanonical")
    return parsed


def _parse_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"technical_snapshot_v4_{field_name}_invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"technical_snapshot_v4_{field_name}_invalid") from exc
    if parsed.utcoffset() is None or parsed.isoformat() != value:
        raise ValueError(f"technical_snapshot_v4_{field_name}_invalid")
    return parsed


def _require_bounded_text(value: object, maximum: int, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise ValueError(f"technical_snapshot_v4_{field_name}_invalid")
    return value


def _require_exact_text(value: object, expected: str, field_name: str) -> str:
    if value != expected:
        raise ValueError(f"technical_snapshot_v4_{field_name}_mismatch")
    return expected


def _require_sha(value: object, field_name: str) -> str:
    if not _is_sha256(value):
        raise ValueError(f"technical_snapshot_v4_{field_name}_invalid")
    return cast(str, value)


def _require_bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"technical_snapshot_v4_{field_name}_invalid")
    return cast(bool, value)


def _require_enum(value: object, allowed: frozenset[str], field_name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"technical_snapshot_v4_{field_name}_invalid")
    return value


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _identity_sha256(payload: Mapping[str, Any]) -> str:
    identity = {key: value for key, value in payload.items() if key != "snapshot_identity_sha256"}
    return _sha256_json(identity)


def _sha256_json(payload: object) -> str:
    return _sha256_bytes(_canonical_json(payload).encode("utf-8"))


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: object) -> str:
    _reject_float_tree(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _reject_float_tree(value: object) -> None:
    if isinstance(value, float):
        raise ValueError("technical_snapshot_v4_json_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("technical_snapshot_v4_json_key_invalid")
            _reject_float_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item)


def _enforce_json_size(payload: Mapping[str, Any]) -> None:
    raw = _canonical_json(payload).encode("utf-8")
    if len(raw) > DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES:
        raise ValueError("technical_snapshot_v4_byte_limit")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"unsupported_json_constant:{value}")
