"""F02 四均線排列的輕量傳輸索引與查詢條件。

此模組只處理可自我檢查的傳輸 DTO 與純篩選投影。其 SHA256 不代表來源核驗，
也不會發行 reader-issued session/page；正式來源資格須由 F17 exact reader 在
同一次 StoreReader parent callback 中建立。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal, NoReturn, TYPE_CHECKING, cast, overload

from app_module.daily_market_technical_ma_alignment_evidence_v1 import (
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
    DailyMarketTechnicalMaAlignmentEvidenceV1,
    DailyMarketTechnicalMaAlignmentEvidenceV1Error,
)

if TYPE_CHECKING:
    from app_module.daily_market_technical_feature_snapshot_v4 import (
        DailyMarketTechnicalFeatureSnapshotV4,
    )
    from app_module.daily_market_technical_parent_v4_query import (
        DailyMarketTechnicalParentV4Row,
    )
    from app_module.daily_market_technical_read_session import (
        DailyMarketTechnicalSourceClockV4,
    )
    from app_module.daily_market_technical_universe_v4_query import (
        DailyMarketTechnicalUniverseV4Query,
    )


DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_INDEX_V1_SCHEMA = (
    "daily-market-technical-universe-ma-alignment-index.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_QUERY_V1_SCHEMA = (
    "daily-market-technical-universe-ma-alignment-query.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_PAGE_V1_SCHEMA = (
    "daily-market-technical-universe-ma-alignment-page.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1 = 100_000
DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1 = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_QUERY_BYTES_V1 = 8 * 1024 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_PAGE_SIZE_V1 = 256
DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_PAGE_INDEX_V1 = 1_000_000
DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_JSON_DEPTH_V1 = 32
DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_DECIMAL_DIGITS_V1 = 128
DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_DECIMAL_EXPONENT_V1 = 128
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1 = "unverified_transport_only"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")
_STATES = ("match", "no_match", "unknown")
_COMBINE_MODES = frozenset({"AND", "OR"})
_INDEX_KEYS = frozenset({
    "schema_version", "verification_status", "base_query_json",
    "base_query_identity_sha256", "generation_identity_sha256",
    "plan_identity_sha256", "plan_sha256", "receipt_identity_sha256",
    "receipt_sha256", "cohort_identity_sha256", "source_clock_identity_sha256",
    "source_clock_json", "method_contracts_sha256", "decision_date",
    "segment_count", "counts", "method_rule_keys", "method_id", "method_version",
    "entries", "ma_state_counts", "source_available_at", "availability_status",
    "historical_pit_eligible", "index_identity_sha256",
})
_ENTRY_KEYS = frozenset({
    "schema_version", "stock_code", "segment_index", "decision_date",
    "latest_feature_date", "raw_row_count", "observed_prefix_contiguous",
    "source_identity", "snapshot_identity_sha256",
    "raw_source_window_fingerprint_sha256", "evidence_identity_sha256",
    "source_clock_identity_sha256", "feature_date", "ma_state", "ma_reason_codes",
    "warmup_observed_sessions", "warmup_contiguous", "base_rule_facts",
})
_RULE_FACT_KEYS = frozenset({"key", "state", "numerator", "denominator", "ratio"})
_COUNTS_KEYS = frozenset({
    "declared_count", "included_count", "excluded_count", "processed_count",
    "pending_count", "missing_data_count", "missing_data_pending_count",
})
_QUERY_KEYS = frozenset({
    "schema_version", "verification_status", "base_query_json",
    "base_query_identity_sha256", "ma_index_identity_sha256", "ma_states",
    "combine_mode", "eligible_stock_codes", "sort_mode", "descending",
    "page_index", "page_size", "query_identity_sha256",
})
_PAGE_KEYS = frozenset({
    "schema_version", "verification_status", "query_json", "query_identity_sha256",
    "index_identity_sha256", "counts", "page_index", "page_size", "rows",
    "source_available_at", "availability_status", "historical_pit_eligible",
    "page_identity_sha256",
})

MaStateV1 = Literal["match", "no_match", "unknown"]
CombineModeV1 = Literal["AND", "OR"]
SortModeV1 = Literal["base", "ma_alignment_state"]


class DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(ValueError):
    """F02 compact transport/query 的穩定錯誤。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(code, message)


def _canonical_json_bytes(value: object) -> bytes:
    _reject_float_tree(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
            "technical_ma_alignment_query_v1_json_invalid", str(exc)
        ) from exc


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _require_sha(value: object, code: str) -> str:
    if not _is_sha(value):
        _fail(code)
    return cast(str, value)


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    if depth > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_JSON_DEPTH_V1:
        _fail("technical_ma_alignment_query_v1_json_depth_limit")
    if isinstance(value, float):
        _fail("technical_ma_alignment_query_v1_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("technical_ma_alignment_query_v1_json_invalid")
            _reject_float_tree(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item, depth=depth + 1)


def _preflight_json_depth(text: str) -> None:
    depth = 0
    quoted = False
    escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
            continue
        if character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_JSON_DEPTH_V1:
                _fail("technical_ma_alignment_query_v1_json_depth_limit")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                _fail("technical_ma_alignment_query_v1_json_invalid")
    if quoted or escaped or depth != 0:
        _fail("technical_ma_alignment_query_v1_json_invalid")


def _parse_json(raw: bytes | str, *, maximum: int, byte_code: str) -> object:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if not isinstance(encoded, bytes):
            _fail("technical_ma_alignment_query_v1_json_invalid")
        if len(encoded) > maximum:
            _fail(byte_code)
        text = encoded.decode("utf-8")
        _preflight_json_depth(text)

        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in items:
                if key in result:
                    _fail("technical_ma_alignment_query_v1_duplicate_json_key")
                result[key] = item
            return result

        def reject_float(_value: str) -> NoReturn:
            _fail("technical_ma_alignment_query_v1_float_forbidden")

        def reject_constant(_value: str) -> NoReturn:
            _fail("technical_ma_alignment_query_v1_json_invalid")

        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
        _reject_float_tree(value)
        if _canonical_json_bytes(value) != encoded:
            _fail("technical_ma_alignment_query_v1_noncanonical_json")
        return value
    except DailyMarketTechnicalUniverseMaAlignmentQueryV1Error:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
        raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
            "technical_ma_alignment_query_v1_json_invalid", str(exc)
        ) from exc


def _parse_date(value: object, code: str) -> date:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(code) from exc
    if parsed.isoformat() != value:
        _fail(code)
    return parsed


def _decimal_text(value: object, code: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 256:
        _fail(code)
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(code) from exc
    if not parsed.is_finite():
        _fail(code)
    tup = parsed.as_tuple()
    if not isinstance(tup.exponent, int):
        _fail(code)
    if (
        len(tup.digits) > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_DECIMAL_DIGITS_V1
        or abs(tup.exponent) > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_DECIMAL_EXPONENT_V1
        or str(parsed) != value
    ):
        _fail(code)
    return value


def _strict_cancel_check(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
            "technical_ma_alignment_query_v1_cancel_check_failed", str(exc)
        ) from exc
    if type(value) is not bool:
        _fail("technical_ma_alignment_query_v1_cancel_callback_invalid")
    if value:
        _fail("technical_ma_alignment_query_v1_cancelled")


def _base_query(value: object) -> DailyMarketTechnicalUniverseV4Query:
    from app_module.daily_market_technical_universe_v4_query import (
        DailyMarketTechnicalUniverseV4Query,
        DailyMarketTechnicalUniverseV4QueryError,
    )

    try:
        if type(value) is DailyMarketTechnicalUniverseV4Query:
            result = value
        elif isinstance(value, (bytes, str)):
            result = DailyMarketTechnicalUniverseV4Query.from_json(value)
        else:
            _fail("technical_ma_alignment_query_v1_base_query_invalid")
    except DailyMarketTechnicalUniverseV4QueryError as exc:
        raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
            "technical_ma_alignment_query_v1_base_query_invalid", str(exc)
        ) from exc
    return cast(DailyMarketTechnicalUniverseV4Query, result)


def _parse_rule_fact(payload: object) -> DailyMarketTechnicalMaAlignmentRuleFactV1:
    if not isinstance(payload, Mapping) or set(payload) != _RULE_FACT_KEYS:
        _fail("technical_ma_alignment_query_v1_rule_fact_invalid")
    key = payload.get("key")
    state = payload.get("state")
    if not isinstance(key, str) or not key or len(key) > 128 or state not in _STATES:
        _fail("technical_ma_alignment_query_v1_rule_fact_invalid")
    return DailyMarketTechnicalMaAlignmentRuleFactV1(
        key=key,
        state=cast(MaStateV1, state),
        numerator=_decimal_text(payload.get("numerator"), "technical_ma_alignment_query_v1_rule_fact_decimal_invalid"),
        denominator=_decimal_text(payload.get("denominator"), "technical_ma_alignment_query_v1_rule_fact_decimal_invalid"),
        ratio=_decimal_text(payload.get("ratio"), "technical_ma_alignment_query_v1_rule_fact_decimal_invalid"),
    )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaAlignmentRuleFactV1:
    """v4 單條規則的 compact 狀態與精確 Decimal 字串。"""

    key: str
    state: MaStateV1
    numerator: str | None
    denominator: str | None
    ratio: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "state": self.state,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "ratio": self.ratio,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaAlignmentCompactEntryV1:
    """一列 compact facts；transport 可重雜湊，故永不代表來源核驗。"""

    stock_code: str
    segment_index: int
    decision_date: date
    latest_feature_date: date | None
    raw_row_count: int
    observed_prefix_contiguous: bool
    source_identity: str
    snapshot_identity_sha256: str
    raw_source_window_fingerprint_sha256: str
    evidence_identity_sha256: str
    source_clock_identity_sha256: str
    feature_date: date | None
    ma_state: MaStateV1
    ma_reason_codes: tuple[str, ...]
    warmup_observed_sessions: int
    warmup_contiguous: bool
    base_rule_facts: tuple[DailyMarketTechnicalMaAlignmentRuleFactV1, ...]

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": "daily-market-technical-ma-alignment-entry.v1",
            "stock_code": self.stock_code,
            "segment_index": self.segment_index,
            "decision_date": self.decision_date.isoformat(),
            "latest_feature_date": self.latest_feature_date.isoformat() if self.latest_feature_date else None,
            "raw_row_count": self.raw_row_count,
            "observed_prefix_contiguous": self.observed_prefix_contiguous,
            "source_identity": self.source_identity,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "raw_source_window_fingerprint_sha256": self.raw_source_window_fingerprint_sha256,
            "evidence_identity_sha256": self.evidence_identity_sha256,
            "source_clock_identity_sha256": self.source_clock_identity_sha256,
            "feature_date": self.feature_date.isoformat() if self.feature_date else None,
            "ma_state": self.ma_state,
            "ma_reason_codes": list(self.ma_reason_codes),
            "warmup_observed_sessions": self.warmup_observed_sessions,
            "warmup_contiguous": self.warmup_contiguous,
            "base_rule_facts": [item.to_dict() for item in self.base_rule_facts],
        }
        _validate_entry_dict(payload)
        return payload

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalMaAlignmentCompactEntryV1:
        payload = _validate_entry_dict(value)
        return cls(
            stock_code=cast(str, payload["stock_code"]),
            segment_index=cast(int, payload["segment_index"]),
            decision_date=_parse_date(payload["decision_date"], "technical_ma_alignment_query_v1_entry_date_invalid"),
            latest_feature_date=(None if payload["latest_feature_date"] is None else _parse_date(payload["latest_feature_date"], "technical_ma_alignment_query_v1_entry_date_invalid")),
            raw_row_count=cast(int, payload["raw_row_count"]),
            observed_prefix_contiguous=cast(bool, payload["observed_prefix_contiguous"]),
            source_identity=cast(str, payload["source_identity"]),
            snapshot_identity_sha256=cast(str, payload["snapshot_identity_sha256"]),
            raw_source_window_fingerprint_sha256=cast(str, payload["raw_source_window_fingerprint_sha256"]),
            evidence_identity_sha256=cast(str, payload["evidence_identity_sha256"]),
            source_clock_identity_sha256=cast(str, payload["source_clock_identity_sha256"]),
            feature_date=(None if payload["feature_date"] is None else _parse_date(payload["feature_date"], "technical_ma_alignment_query_v1_entry_date_invalid")),
            ma_state=cast(MaStateV1, payload["ma_state"]),
            ma_reason_codes=cast(tuple[str, ...], tuple(cast(Sequence[object], payload["ma_reason_codes"]))),
            warmup_observed_sessions=cast(int, payload["warmup_observed_sessions"]),
            warmup_contiguous=cast(bool, payload["warmup_contiguous"]),
            base_rule_facts=tuple(_parse_rule_fact(item) for item in cast(Sequence[object], payload["base_rule_facts"])),
        )


def _validate_entry_dict(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _ENTRY_KEYS:
        _fail("technical_ma_alignment_query_v1_entry_fields_invalid")
    payload = dict(value)
    if payload.get("schema_version") != "daily-market-technical-ma-alignment-entry.v1":
        _fail("technical_ma_alignment_query_v1_entry_schema_unsupported")
    code = payload.get("stock_code")
    if not isinstance(code, str) or _STOCK_CODE_RE.fullmatch(code) is None:
        _fail("technical_ma_alignment_query_v1_entry_stock_invalid")
    if type(payload.get("segment_index")) is not int or payload["segment_index"] < 0:
        _fail("technical_ma_alignment_query_v1_entry_segment_invalid")
    decision = _parse_date(payload.get("decision_date"), "technical_ma_alignment_query_v1_entry_date_invalid")
    latest_raw = payload.get("latest_feature_date")
    latest = None if latest_raw is None else _parse_date(latest_raw, "technical_ma_alignment_query_v1_entry_date_invalid")
    feature_raw = payload.get("feature_date")
    feature = None if feature_raw is None else _parse_date(feature_raw, "technical_ma_alignment_query_v1_entry_date_invalid")
    if any(item is not None and item > decision for item in (latest, feature)) or latest != feature:
        _fail("technical_ma_alignment_query_v1_entry_feature_date_mismatch")
    if type(payload.get("raw_row_count")) is not int or not 0 <= payload["raw_row_count"] <= 120:
        _fail("technical_ma_alignment_query_v1_entry_row_count_invalid")
    if type(payload.get("observed_prefix_contiguous")) is not bool or type(payload.get("warmup_contiguous")) is not bool:
        _fail("technical_ma_alignment_query_v1_entry_boolean_invalid")
    source = payload.get("source_identity")
    if not isinstance(source, str) or not source.strip() or len(source.encode("utf-8")) > 4096:
        _fail("technical_ma_alignment_query_v1_entry_source_invalid")
    for key in (
        "snapshot_identity_sha256", "raw_source_window_fingerprint_sha256",
        "evidence_identity_sha256", "source_clock_identity_sha256",
    ):
        _require_sha(payload.get(key), "technical_ma_alignment_query_v1_entry_pin_invalid")
    if payload.get("ma_state") not in _STATES:
        _fail("technical_ma_alignment_query_v1_entry_state_invalid")
    reasons = payload.get("ma_reason_codes")
    if (
        not isinstance(reasons, list) or not 1 <= len(reasons) <= 4
        or any(not isinstance(item, str) or not item.startswith("ma_alignment_") or len(item) > 128 for item in reasons)
        or len(set(reasons)) != len(reasons)
    ):
        _fail("technical_ma_alignment_query_v1_entry_reasons_invalid")
    if type(payload.get("warmup_observed_sessions")) is not int or not 0 <= payload["warmup_observed_sessions"] <= 60:
        _fail("technical_ma_alignment_query_v1_entry_warmup_invalid")
    facts = payload.get("base_rule_facts")
    if not isinstance(facts, list) or len(facts) != 5:
        _fail("technical_ma_alignment_query_v1_entry_rule_facts_invalid")
    parsed_facts = tuple(_parse_rule_fact(item) for item in facts)
    if len({item.key for item in parsed_facts}) != 5:
        _fail("technical_ma_alignment_query_v1_entry_rule_facts_invalid")
    payload["decision_date"] = decision.isoformat()
    payload["latest_feature_date"] = latest.isoformat() if latest else None
    payload["feature_date"] = feature.isoformat() if feature else None
    payload["ma_reason_codes"] = list(cast(list[str], reasons))
    payload["base_rule_facts"] = [item.to_dict() for item in parsed_facts]
    return payload


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaAlignmentPopulationCountsV1:
    declared_count: int
    included_count: int
    excluded_count: int
    processed_count: int
    pending_count: int
    missing_data_count: int
    missing_data_pending_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "declared_count": self.declared_count,
            "included_count": self.included_count,
            "excluded_count": self.excluded_count,
            "processed_count": self.processed_count,
            "pending_count": self.pending_count,
            "missing_data_count": self.missing_data_count,
            "missing_data_pending_count": self.missing_data_pending_count,
        }

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalMaAlignmentPopulationCountsV1:
        if not isinstance(value, Mapping) or set(value) != _COUNTS_KEYS:
            _fail("technical_ma_alignment_query_v1_counts_invalid")
        items: dict[str, int] = {}
        for key in _COUNTS_KEYS:
            number = value.get(key)
            if type(number) is not int or number < 0:
                _fail("technical_ma_alignment_query_v1_counts_invalid")
            items[key] = number
        if (
            items["declared_count"] != items["included_count"] + items["excluded_count"]
            or items["processed_count"] + items["pending_count"] != items["included_count"]
            or items["missing_data_count"] > items["processed_count"]
            or items["missing_data_pending_count"] != items["pending_count"]
            or items["declared_count"] > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1
        ):
            _fail("technical_ma_alignment_query_v1_counts_inconsistent")
        return cls(**items)


def _base_query_context(raw: object) -> tuple[DailyMarketTechnicalUniverseV4Query, dict[str, object]]:
    base = _base_query(raw)
    return base, base.to_dict()


_BASE_QUERY_CONDITION_KEYS = frozenset({
    "state_filters", "combine_mode", "stock_filter", "sort_key", "descending",
    "page_index", "page_size", "query_identity_sha256",
})


def _base_query_source_scope(query: DailyMarketTechnicalUniverseV4Query) -> dict[str, object]:
    """保留固定資料來源身分，排除可在同一讀取工作階段調整的條件。"""

    payload = query.to_dict()
    for key in _BASE_QUERY_CONDITION_KEYS:
        payload.pop(key, None)
    return payload


def _same_base_query_source_scope(
    left: DailyMarketTechnicalUniverseV4Query,
    right: DailyMarketTechnicalUniverseV4Query,
) -> bool:
    return _base_query_source_scope(left) == _base_query_source_scope(right)


def _clock_payload(raw: object, expected_identity: str) -> dict[str, object]:
    if not isinstance(raw, (bytes, str)):
        _fail("technical_ma_alignment_query_v1_source_clock_invalid")
    parsed = _parse_json(
        raw,
        maximum=8192,
        byte_code="technical_ma_alignment_query_v1_source_clock_byte_limit",
    )
    if not isinstance(parsed, Mapping):
        _fail("technical_ma_alignment_query_v1_source_clock_invalid")
    from app_module.daily_market_technical_universe_v4_store import (
        DailyMarketTechnicalUniverseV4StoreError,
        daily_market_technical_source_clock_v4_from_dict,
    )

    try:
        clock = daily_market_technical_source_clock_v4_from_dict(parsed)
    except (DailyMarketTechnicalUniverseV4StoreError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
            "technical_ma_alignment_query_v1_source_clock_invalid", str(exc)
        ) from exc
    if clock.identity_sha256 != expected_identity or _canonical_json_bytes(clock.to_dict()) != _canonical_json_bytes(parsed):
        _fail("technical_ma_alignment_query_v1_source_clock_pin_mismatch")
    return cast(dict[str, object], clock.to_dict())


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaAlignmentCompactIndexV1:
    """Compact MA+v4 rule facts，僅是可重雜湊的 unverified transport。"""

    base_query_json: str
    base_query_identity_sha256: str
    generation_identity_sha256: str
    plan_identity_sha256: str
    plan_sha256: str
    receipt_identity_sha256: str
    receipt_sha256: str
    cohort_identity_sha256: str
    source_clock_identity_sha256: str
    source_clock_json: str
    method_contracts_sha256: str
    decision_date: date
    segment_count: int
    counts: DailyMarketTechnicalMaAlignmentPopulationCountsV1
    method_rule_keys: tuple[str, ...]
    entries: tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, ...]
    ma_state_counts: tuple[tuple[str, int], ...]
    index_identity_sha256: str

    @property
    def verification_status(self) -> str:
        return DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1

    @property
    def reader_issued(self) -> Literal[False]:
        return False

    @classmethod
    def create_unverified_transport(
        cls,
        base_query: DailyMarketTechnicalUniverseV4Query,
        *,
        source_clock_json: str,
        entries: Sequence[DailyMarketTechnicalMaAlignmentCompactEntryV1],
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalMaAlignmentCompactIndexV1:
        _strict_cancel_check(cancel_callback)
        base_query = _base_query(base_query)
        if isinstance(entries, (str, bytes)) or len(entries) > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1:
            _fail("technical_ma_alignment_query_v1_entry_limit")
        query_payload = base_query.to_dict()
        clock_payload = _clock_payload(source_clock_json, base_query.source_clock_identity_sha256)
        if _parse_date(clock_payload.get("decision_date"), "technical_ma_alignment_query_v1_source_clock_invalid") != base_query.decision_date:
            _fail("technical_ma_alignment_query_v1_source_clock_date_mismatch")
        normalized: list[DailyMarketTechnicalMaAlignmentCompactEntryV1] = []
        seen: set[str] = set()
        for index, entry in enumerate(entries):
            if index % 256 == 0:
                _strict_cancel_check(cancel_callback)
            if type(entry) is not DailyMarketTechnicalMaAlignmentCompactEntryV1:
                _fail("technical_ma_alignment_query_v1_entry_type_invalid")
            payload = entry.to_dict()
            checked = DailyMarketTechnicalMaAlignmentCompactEntryV1.from_dict(payload)
            if (
                checked.stock_code in seen
                or checked.segment_index >= base_query.segment_count
                or checked.decision_date != base_query.decision_date
                or checked.source_clock_identity_sha256 != base_query.source_clock_identity_sha256
                or tuple(item.key for item in checked.base_rule_facts) != base_query.method_rule_keys
            ):
                _fail("technical_ma_alignment_query_v1_entry_source_mismatch")
            seen.add(checked.stock_code)
            normalized.append(checked)
        if (
            len(normalized) != base_query.counts.processed_count
            or tuple(sorted(item.stock_code for item in normalized)) != tuple(item.stock_code for item in normalized)
        ):
            _fail("technical_ma_alignment_query_v1_entry_population_mismatch")
        state_counts = tuple((state, sum(item.ma_state == state for item in normalized)) for state in _STATES)
        return _issue_index(
            base_query_json=base_query.to_json(),
            base_query_identity_sha256=base_query.query_identity_sha256,
            generation_identity_sha256=base_query.generation_identity_sha256,
            plan_identity_sha256=base_query.plan_identity_sha256,
            plan_sha256=base_query.plan_sha256,
            receipt_identity_sha256=base_query.receipt_identity_sha256,
            receipt_sha256=base_query.receipt_sha256,
            cohort_identity_sha256=base_query.cohort_identity_sha256,
            source_clock_identity_sha256=base_query.source_clock_identity_sha256,
            source_clock_json=_canonical_json_bytes(clock_payload).decode("utf-8"),
            method_contracts_sha256=base_query.method_contracts_sha256,
            decision_date=base_query.decision_date,
            segment_count=base_query.segment_count,
            counts=DailyMarketTechnicalMaAlignmentPopulationCountsV1.from_dict(
                base_query.counts.to_dict()
            ),
            method_rule_keys=base_query.method_rule_keys,
            entries=tuple(normalized),
            ma_state_counts=cast(tuple[tuple[str, int], ...], state_counts),
            cancel_callback=cancel_callback,
        )

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalMaAlignmentCompactIndexV1:
        payload = _validate_index_dict(value)
        result = cls(
            base_query_json=cast(str, payload["base_query_json"]),
            base_query_identity_sha256=cast(str, payload["base_query_identity_sha256"]),
            generation_identity_sha256=cast(str, payload["generation_identity_sha256"]),
            plan_identity_sha256=cast(str, payload["plan_identity_sha256"]),
            plan_sha256=cast(str, payload["plan_sha256"]),
            receipt_identity_sha256=cast(str, payload["receipt_identity_sha256"]),
            receipt_sha256=cast(str, payload["receipt_sha256"]),
            cohort_identity_sha256=cast(str, payload["cohort_identity_sha256"]),
            source_clock_identity_sha256=cast(str, payload["source_clock_identity_sha256"]),
            source_clock_json=cast(str, payload["source_clock_json"]),
            method_contracts_sha256=cast(str, payload["method_contracts_sha256"]),
            decision_date=_parse_date(payload["decision_date"], "technical_ma_alignment_query_v1_index_date_invalid"),
            segment_count=cast(int, payload["segment_count"]),
            counts=DailyMarketTechnicalMaAlignmentPopulationCountsV1.from_dict(payload["counts"]),
            method_rule_keys=cast(tuple[str, ...], tuple(cast(Sequence[object], payload["method_rule_keys"]))),
            entries=tuple(DailyMarketTechnicalMaAlignmentCompactEntryV1.from_dict(item) for item in cast(Sequence[object], payload["entries"])),
            ma_state_counts=cast(tuple[tuple[str, int], ...], tuple((item["state"], item["count"]) for item in cast(Sequence[Mapping[str, object]], payload["ma_state_counts"]))),
            index_identity_sha256=cast(str, payload["index_identity_sha256"]),
        )
        if result.to_dict() != dict(payload):
            _fail("technical_ma_alignment_query_v1_index_noncanonical")
        return result

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalMaAlignmentCompactIndexV1:
        value = _parse_json(
            raw,
            maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1,
            byte_code="technical_ma_alignment_query_v1_index_byte_limit",
        )
        return cls.from_dict(value)

    def to_dict(self) -> dict[str, object]:
        payload = _index_payload(self)
        body = {key: value for key, value in payload.items() if key != "index_identity_sha256"}
        identity = _sha256_json(body)
        if identity != self.index_identity_sha256:
            _fail("technical_ma_alignment_query_v1_index_identity_mismatch")
        result = {**body, "index_identity_sha256": identity}
        if len(_canonical_json_bytes(result)) > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1:
            _fail("technical_ma_alignment_query_v1_index_byte_limit")
        return result

    def to_json(self) -> str:
        return _canonical_json_bytes(self.to_dict()).decode("utf-8")


def _issue_index(
    *,
    cancel_callback: Callable[[], object] | None = None,
    **fields: object,
) -> DailyMarketTechnicalMaAlignmentCompactIndexV1:
    _strict_cancel_check(cancel_callback)
    result = DailyMarketTechnicalMaAlignmentCompactIndexV1(
        **cast(Any, fields),
        index_identity_sha256="0" * 64,
    )
    body = {key: value for key, value in _index_payload(result).items() if key != "index_identity_sha256"}
    identity = _sha256_json(body)
    result = DailyMarketTechnicalMaAlignmentCompactIndexV1(
        **cast(Any, fields),
        index_identity_sha256=identity,
    )
    # 自我雜湊只驗傳輸完整性；不發行來源核驗 seal。
    _strict_cancel_check(cancel_callback)
    result.to_dict()
    return result


def _index_payload(index: DailyMarketTechnicalMaAlignmentCompactIndexV1) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_INDEX_V1_SCHEMA,
        "verification_status": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1,
        "base_query_json": index.base_query_json,
        "base_query_identity_sha256": index.base_query_identity_sha256,
        "generation_identity_sha256": index.generation_identity_sha256,
        "plan_identity_sha256": index.plan_identity_sha256,
        "plan_sha256": index.plan_sha256,
        "receipt_identity_sha256": index.receipt_identity_sha256,
        "receipt_sha256": index.receipt_sha256,
        "cohort_identity_sha256": index.cohort_identity_sha256,
        "source_clock_identity_sha256": index.source_clock_identity_sha256,
        "source_clock_json": index.source_clock_json,
        "method_contracts_sha256": index.method_contracts_sha256,
        "decision_date": index.decision_date.isoformat(),
        "segment_count": index.segment_count,
        "counts": index.counts.to_dict(),
        "method_rule_keys": list(index.method_rule_keys),
        "method_id": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
        "method_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
        "entries": [item.to_dict() for item in index.entries],
        "ma_state_counts": [
            {"state": state, "count": count} for state, count in index.ma_state_counts
        ],
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
        "index_identity_sha256": index.index_identity_sha256,
    }


def _validate_index_dict(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _INDEX_KEYS:
        _fail("technical_ma_alignment_query_v1_index_fields_invalid")
    payload = dict(value)
    if (
        payload.get("schema_version") != DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_INDEX_V1_SCHEMA
        or payload.get("verification_status") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1
        or payload.get("method_id") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1
        or payload.get("method_version") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1
        or payload.get("source_available_at") is not None
        or payload.get("availability_status") != "unknown"
        or payload.get("historical_pit_eligible") is not False
    ):
        _fail("technical_ma_alignment_query_v1_index_policy_invalid")
    base, base_payload = _base_query_context(payload.get("base_query_json"))
    if (
        base.to_json() != payload.get("base_query_json")
        or base.query_identity_sha256 != payload.get("base_query_identity_sha256")
    ):
        _fail("technical_ma_alignment_query_v1_index_base_query_mismatch")
    pins = {
        "generation_identity_sha256": base.generation_identity_sha256,
        "plan_identity_sha256": base.plan_identity_sha256,
        "plan_sha256": base.plan_sha256,
        "receipt_identity_sha256": base.receipt_identity_sha256,
        "receipt_sha256": base.receipt_sha256,
        "cohort_identity_sha256": base.cohort_identity_sha256,
        "source_clock_identity_sha256": base.source_clock_identity_sha256,
        "method_contracts_sha256": base.method_contracts_sha256,
    }
    if any(payload.get(key) != expected for key, expected in pins.items()):
        _fail("technical_ma_alignment_query_v1_index_pin_mismatch")
    for key in pins:
        _require_sha(payload.get(key), "technical_ma_alignment_query_v1_index_pin_invalid")
    decision = _parse_date(payload.get("decision_date"), "technical_ma_alignment_query_v1_index_date_invalid")
    if decision != base.decision_date or _clock_payload(payload.get("source_clock_json"), base.source_clock_identity_sha256).get("decision_date") != decision.isoformat():
        _fail("technical_ma_alignment_query_v1_index_clock_mismatch")
    if type(payload.get("segment_count")) is not int or payload["segment_count"] != base.segment_count:
        _fail("technical_ma_alignment_query_v1_index_segment_count_invalid")
    counts = DailyMarketTechnicalMaAlignmentPopulationCountsV1.from_dict(payload.get("counts"))
    if counts.to_dict() != base.counts.to_dict():
        _fail("technical_ma_alignment_query_v1_index_counts_mismatch")
    keys = payload.get("method_rule_keys")
    if not isinstance(keys, list) or tuple(keys) != base.method_rule_keys:
        _fail("technical_ma_alignment_query_v1_index_rule_keys_mismatch")
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list) or len(raw_entries) > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1:
        _fail("technical_ma_alignment_query_v1_entry_limit")
    entries = tuple(DailyMarketTechnicalMaAlignmentCompactEntryV1.from_dict(item) for item in raw_entries)
    codes = tuple(item.stock_code for item in entries)
    if (
        len(entries) != counts.processed_count
        or codes != tuple(sorted(set(codes)))
        or any(item.segment_index >= base.segment_count or item.decision_date != decision or item.source_clock_identity_sha256 != base.source_clock_identity_sha256 for item in entries)
        or any(tuple(rule.key for rule in item.base_rule_facts) != base.method_rule_keys for item in entries)
        or sum(item.raw_row_count == 0 for item in entries) != counts.missing_data_count
    ):
        _fail("technical_ma_alignment_query_v1_index_population_mismatch")
    expected_state_counts = tuple((state, sum(item.ma_state == state for item in entries)) for state in _STATES)
    raw_state_counts = payload.get("ma_state_counts")
    if not isinstance(raw_state_counts, list) or len(raw_state_counts) != len(_STATES):
        _fail("technical_ma_alignment_query_v1_index_state_counts_invalid")
    normalized_state_counts: list[tuple[str, int]] = []
    for expected_state, raw in zip(_STATES, raw_state_counts):
        if not isinstance(raw, Mapping) or set(raw) != {"state", "count"}:
            _fail("technical_ma_alignment_query_v1_index_state_counts_invalid")
        state, count = raw.get("state"), raw.get("count")
        if state != expected_state or type(count) is not int or count < 0:
            _fail("technical_ma_alignment_query_v1_index_state_counts_invalid")
        normalized_state_counts.append((expected_state, count))
    if tuple(normalized_state_counts) != expected_state_counts:
        _fail("technical_ma_alignment_query_v1_index_state_counts_mismatch")
    index_id = _require_sha(payload.get("index_identity_sha256"), "technical_ma_alignment_query_v1_index_identity_invalid")
    body = {key: item for key, item in payload.items() if key != "index_identity_sha256"}
    if _sha256_json(body) != index_id:
        _fail("technical_ma_alignment_query_v1_index_identity_mismatch")
    payload["decision_date"] = decision.isoformat()
    payload["counts"] = counts.to_dict()
    payload["entries"] = [item.to_dict() for item in entries]
    payload["ma_state_counts"] = [{"state": state, "count": count} for state, count in normalized_state_counts]
    # 確認 P01 query 仍為 canonical，解析只驗 request，不讀 store 或來源資料。
    _ = base_payload
    return payload


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaAlignmentQueryV1:
    """固定 base P01 query、MA condition、eligibility、排序與分頁請求。"""

    base_query_json: str
    base_query_identity_sha256: str
    ma_index_identity_sha256: str
    ma_states: tuple[MaStateV1, ...] | None
    combine_mode: CombineModeV1
    eligible_stock_codes: tuple[str, ...] | None
    sort_mode: SortModeV1
    descending: bool
    page_index: int
    page_size: int
    query_identity_sha256: str

    @property
    def verification_status(self) -> str:
        return DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1

    @property
    def reader_issued(self) -> Literal[False]:
        return False

    @classmethod
    def create(
        cls,
        base_query: DailyMarketTechnicalUniverseV4Query,
        index: DailyMarketTechnicalMaAlignmentCompactIndexV1,
        *,
        ma_states: Sequence[MaStateV1] | None = None,
        combine_mode: CombineModeV1 = "AND",
        eligible_stock_codes: Sequence[str] | None = None,
        sort_mode: SortModeV1 = "base",
        descending: bool = False,
        page_index: int = 0,
        page_size: int = 50,
    ) -> DailyMarketTechnicalMaAlignmentQueryV1:
        base_query = _base_query(base_query)
        if type(index) is not DailyMarketTechnicalMaAlignmentCompactIndexV1:
            _fail("technical_ma_alignment_query_v1_query_input_invalid")
        index.to_dict()
        indexed_base_query = _base_query(index.base_query_json)
        if not _same_base_query_source_scope(indexed_base_query, base_query):
            _fail("technical_ma_alignment_query_v1_query_source_scope_mismatch")
        state_tuple = _normalize_states(ma_states)
        codes = _normalize_codes(eligible_stock_codes, allow_none=True)
        if combine_mode not in _COMBINE_MODES or sort_mode not in {"base", "ma_alignment_state"} or type(descending) is not bool:
            _fail("technical_ma_alignment_query_v1_query_conditions_invalid")
        if type(page_index) is not int or not 0 <= page_index <= DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_PAGE_INDEX_V1:
            _fail("technical_ma_alignment_query_v1_page_invalid")
        if type(page_size) is not int or not 1 <= page_size <= DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_PAGE_SIZE_V1:
            _fail("technical_ma_alignment_query_v1_page_invalid")
        if sort_mode == "base" and descending:
            # base 方向已由 exact P01 query 的 sort clause 固定，避免第二次反轉。
            _fail("technical_ma_alignment_query_v1_base_sort_direction_invalid")
        values: dict[str, object] = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_QUERY_V1_SCHEMA,
            "verification_status": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1,
            "base_query_json": base_query.to_json(),
            "base_query_identity_sha256": base_query.query_identity_sha256,
            "ma_index_identity_sha256": index.index_identity_sha256,
            "ma_states": None if state_tuple is None else list(state_tuple),
            "combine_mode": combine_mode,
            "eligible_stock_codes": None if codes is None else list(codes),
            "sort_mode": sort_mode,
            "descending": descending,
            "page_index": page_index,
            "page_size": page_size,
        }
        query_id = _sha256_json(values)
        return cls.from_dict({**values, "query_identity_sha256": query_id})

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalMaAlignmentQueryV1:
        payload = _validate_query_dict(value)
        return cls(
            base_query_json=cast(str, payload["base_query_json"]),
            base_query_identity_sha256=cast(str, payload["base_query_identity_sha256"]),
            ma_index_identity_sha256=cast(str, payload["ma_index_identity_sha256"]),
            ma_states=(None if payload["ma_states"] is None else cast(tuple[MaStateV1, ...], tuple(cast(Sequence[object], payload["ma_states"])))),
            combine_mode=cast(CombineModeV1, payload["combine_mode"]),
            eligible_stock_codes=(None if payload["eligible_stock_codes"] is None else cast(tuple[str, ...], tuple(cast(Sequence[object], payload["eligible_stock_codes"])))),
            sort_mode=cast(SortModeV1, payload["sort_mode"]),
            descending=cast(bool, payload["descending"]),
            page_index=cast(int, payload["page_index"]),
            page_size=cast(int, payload["page_size"]),
            query_identity_sha256=cast(str, payload["query_identity_sha256"]),
        )

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalMaAlignmentQueryV1:
        value = _parse_json(raw, maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_QUERY_BYTES_V1, byte_code="technical_ma_alignment_query_v1_query_byte_limit")
        result = cls.from_dict(value)
        if result.to_json().encode("utf-8") != (raw.encode("utf-8") if isinstance(raw, str) else raw):
            _fail("technical_ma_alignment_query_v1_query_noncanonical_json")
        return result

    def to_dict(self) -> dict[str, object]:
        payload = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_QUERY_V1_SCHEMA,
            "verification_status": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1,
            "base_query_json": self.base_query_json,
            "base_query_identity_sha256": self.base_query_identity_sha256,
            "ma_index_identity_sha256": self.ma_index_identity_sha256,
            "ma_states": None if self.ma_states is None else list(self.ma_states),
            "combine_mode": self.combine_mode,
            "eligible_stock_codes": None if self.eligible_stock_codes is None else list(self.eligible_stock_codes),
            "sort_mode": self.sort_mode,
            "descending": self.descending,
            "page_index": self.page_index,
            "page_size": self.page_size,
        }
        identity = _sha256_json(payload)
        if identity != self.query_identity_sha256:
            _fail("technical_ma_alignment_query_v1_query_identity_mismatch")
        return {**payload, "query_identity_sha256": identity}

    def to_json(self) -> str:
        payload = _canonical_json_bytes(self.to_dict())
        if len(payload) > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_QUERY_BYTES_V1:
            _fail("technical_ma_alignment_query_v1_query_byte_limit")
        return payload.decode("utf-8")


def _normalize_states(values: Sequence[str] | None) -> tuple[MaStateV1, ...] | None:
    if values is None:
        return None
    if isinstance(values, (str, bytes)):
        _fail("technical_ma_alignment_query_v1_ma_states_invalid")
    items = tuple(values)
    if any(item not in _STATES for item in items) or len(set(items)) != len(items):
        _fail("technical_ma_alignment_query_v1_ma_states_invalid")
    return cast(tuple[MaStateV1, ...], tuple(state for state in _STATES if state in items))


def _normalize_codes(values: Sequence[str] | None, *, allow_none: bool) -> tuple[str, ...] | None:
    if values is None:
        if allow_none:
            return None
        _fail("technical_ma_alignment_query_v1_codes_invalid")
    if isinstance(values, (str, bytes)):
        _fail("technical_ma_alignment_query_v1_codes_invalid")
    items = tuple(values)
    if len(items) > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1 or any(
        not isinstance(item, str) or _STOCK_CODE_RE.fullmatch(item) is None for item in items
    ) or len(set(items)) != len(items):
        _fail("technical_ma_alignment_query_v1_codes_invalid")
    return tuple(sorted(items))


def _validate_query_dict(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _QUERY_KEYS:
        _fail("technical_ma_alignment_query_v1_query_fields_invalid")
    payload = dict(value)
    if payload.get("schema_version") != DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_QUERY_V1_SCHEMA or payload.get("verification_status") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1:
        _fail("technical_ma_alignment_query_v1_query_schema_or_status_invalid")
    base = _base_query(payload.get("base_query_json"))
    if base.to_json() != payload.get("base_query_json") or base.query_identity_sha256 != payload.get("base_query_identity_sha256"):
        _fail("technical_ma_alignment_query_v1_base_query_mismatch")
    _require_sha(payload.get("ma_index_identity_sha256"), "technical_ma_alignment_query_v1_index_identity_invalid")
    states = _normalize_states(payload.get("ma_states"))
    if states is not None and list(states) != payload.get("ma_states"):
        _fail("technical_ma_alignment_query_v1_ma_states_noncanonical")
    codes = _normalize_codes(payload.get("eligible_stock_codes"), allow_none=True)
    if codes is not None and list(codes) != payload.get("eligible_stock_codes"):
        _fail("technical_ma_alignment_query_v1_codes_noncanonical")
    if payload.get("combine_mode") not in _COMBINE_MODES or payload.get("sort_mode") not in {"base", "ma_alignment_state"} or type(payload.get("descending")) is not bool:
        _fail("technical_ma_alignment_query_v1_query_conditions_invalid")
    if payload["sort_mode"] == "base" and payload["descending"] is not False:
        _fail("technical_ma_alignment_query_v1_base_sort_direction_invalid")
    if type(payload.get("page_index")) is not int or not 0 <= payload["page_index"] <= DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_PAGE_INDEX_V1 or type(payload.get("page_size")) is not int or not 1 <= payload["page_size"] <= DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_PAGE_SIZE_V1:
        _fail("technical_ma_alignment_query_v1_page_invalid")
    identity = _require_sha(payload.get("query_identity_sha256"), "technical_ma_alignment_query_v1_query_identity_invalid")
    body = {key: item for key, item in payload.items() if key != "query_identity_sha256"}
    if _sha256_json(body) != identity:
        _fail("technical_ma_alignment_query_v1_query_identity_mismatch")
    payload["ma_states"] = None if states is None else list(states)
    payload["eligible_stock_codes"] = None if codes is None else list(codes)
    return payload


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaAlignmentPageV1:
    """純篩選器輸出；即使 SHA 正確也不代表 exact-source reader 發行。"""

    query_json: str
    query_identity_sha256: str
    index_identity_sha256: str
    counts: tuple[tuple[str, int], ...]
    page_index: int
    page_size: int
    rows: tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, ...]
    page_identity_sha256: str

    @property
    def verification_status(self) -> str:
        return DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1

    @property
    def reader_issued(self) -> Literal[False]:
        return False

    def to_dict(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_PAGE_V1_SCHEMA,
            "verification_status": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1,
            "query_json": self.query_json,
            "query_identity_sha256": self.query_identity_sha256,
            "index_identity_sha256": self.index_identity_sha256,
            "counts": [{"name": key, "value": value} for key, value in self.counts],
            "page_index": self.page_index,
            "page_size": self.page_size,
            "rows": [item.to_dict() for item in self.rows],
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }
        if _sha256_json(body) != self.page_identity_sha256:
            _fail("technical_ma_alignment_query_v1_page_identity_mismatch")
        return {**body, "page_identity_sha256": self.page_identity_sha256}


@overload
def evaluate_unverified_ma_alignment_page_v1(
    query: DailyMarketTechnicalMaAlignmentQueryV1,
    index: DailyMarketTechnicalMaAlignmentCompactIndexV1,
    *,
    cancel_callback: Callable[[], object] | None = None,
    _return_all: Literal[False] = False,
) -> DailyMarketTechnicalMaAlignmentPageV1: ...


@overload
def evaluate_unverified_ma_alignment_page_v1(
    query: DailyMarketTechnicalMaAlignmentQueryV1,
    index: DailyMarketTechnicalMaAlignmentCompactIndexV1,
    *,
    cancel_callback: Callable[[], object] | None = None,
    _return_all: Literal[True],
) -> tuple[
    tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, ...],
    tuple[tuple[str, int], ...],
]: ...


def evaluate_unverified_ma_alignment_page_v1(
    query: DailyMarketTechnicalMaAlignmentQueryV1,
    index: DailyMarketTechnicalMaAlignmentCompactIndexV1,
    *,
    cancel_callback: Callable[[], object] | None = None,
    _return_all: bool = False,
) -> DailyMarketTechnicalMaAlignmentPageV1 | tuple[
    tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, ...],
    tuple[tuple[str, int], ...],
]:
    """用傳輸索引做可測的 global filter/sort/page；不會發行來源資格。"""

    _strict_cancel_check(cancel_callback)
    if type(query) is not DailyMarketTechnicalMaAlignmentQueryV1 or type(index) is not DailyMarketTechnicalMaAlignmentCompactIndexV1:
        _fail("technical_ma_alignment_query_v1_evaluator_input_invalid")
    query.to_dict()
    index.to_dict()
    query_base = _base_query(query.base_query_json)
    indexed_base = _base_query(index.base_query_json)
    if (
        query.ma_index_identity_sha256 != index.index_identity_sha256
        or not _same_base_query_source_scope(query_base, indexed_base)
    ):
        _fail("technical_ma_alignment_query_v1_evaluator_pin_mismatch")
    base = query_base
    entries = index.entries
    entry_by_code = {item.stock_code: item for item in entries}
    base_filters = base.rule_state_filters
    base_stock_filter = set(base.stock_filter)
    outer_stock_filter = None if query.eligible_stock_codes is None else set(query.eligible_stock_codes)
    matching: list[DailyMarketTechnicalMaAlignmentCompactEntryV1] = []
    base_matching_count = 0
    base_unknown_count = 0
    selected_unknown_count = 0
    for position, entry in enumerate(entries):
        if position % 256 == 0:
            _strict_cancel_check(cancel_callback)
        facts = {item.key: item for item in entry.base_rule_facts}
        if tuple(facts) != base.method_rule_keys:
            _fail("technical_ma_alignment_query_v1_entry_rule_scope_mismatch")
        base_outcomes = tuple(facts[item.rule_key].state in item.states for item in base_filters)
        base_condition = (
            (all(base_outcomes) if base.combine_mode == "AND" else any(base_outcomes))
            if base_outcomes else True
        )
        if base_condition:
            base_matching_count += 1
            if any(facts[item].state == "unknown" for item in base.method_rule_keys):
                base_unknown_count += 1
        ma_filter_present = query.ma_states is not None
        ma_condition = True if not ma_filter_present else entry.ma_state in cast(tuple[str, ...], query.ma_states)
        if base_filters and ma_filter_present:
            condition_match = (
                base_condition and ma_condition
                if query.combine_mode == "AND"
                else base_condition or ma_condition
            )
        elif base_filters:
            condition_match = base_condition
        elif ma_filter_present:
            condition_match = ma_condition
        else:
            condition_match = True
        if base_stock_filter and entry.stock_code not in base_stock_filter:
            continue
        if outer_stock_filter is not None and entry.stock_code not in outer_stock_filter:
            continue
        if condition_match:
            matching.append(entry)
            if entry.ma_state == "unknown":
                selected_unknown_count += 1

    if query.sort_mode == "base":
        sort_key = base.sort_key
        descending = base.descending
    else:
        sort_key = "ma_alignment_state"
        descending = query.descending

    def value_for(entry: DailyMarketTechnicalMaAlignmentCompactEntryV1) -> object | None:
        if sort_key == "stock_code":
            return entry.stock_code
        if sort_key == "decision_date":
            return entry.decision_date
        if sort_key == "latest_feature_date":
            return entry.latest_feature_date
        if sort_key == "raw_row_count":
            return entry.raw_row_count
        if sort_key == "ma_alignment_state":
            return None if entry.ma_state == "unknown" else (0 if entry.ma_state == "match" else 1)
        rule_key, field_name = sort_key.rsplit(".", 1)
        fact = next((item for item in entry.base_rule_facts if item.key == rule_key), None)
        if fact is None:
            _fail("technical_ma_alignment_query_v1_sort_rule_invalid")
        raw = getattr(fact, field_name, None)
        if raw is None:
            return None
        try:
            return Decimal(raw)
        except (InvalidOperation, TypeError) as exc:
            raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
                "technical_ma_alignment_query_v1_sort_value_invalid"
            ) from exc

    # 同一個 query 只會選一種 scalar 類型；輸入已由前述公開欄位契約驗證。
    known: list[tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, Any]] = []
    nulls: list[DailyMarketTechnicalMaAlignmentCompactEntryV1] = []
    for position, entry in enumerate(matching):
        if position % 256 == 0:
            _strict_cancel_check(cancel_callback)
        value = value_for(entry)
        if value is None:
            nulls.append(entry)
        else:
            known.append((entry, value))
    known.sort(key=lambda pair: pair[0].stock_code)
    known.sort(key=lambda pair: pair[1], reverse=descending)
    nulls.sort(key=lambda item: item.stock_code)
    ordered = [item for item, _value in known] + nulls
    matching_count = len(ordered)
    page_count = (matching_count + query.page_size - 1) // query.page_size
    start = query.page_index * query.page_size
    rows = tuple(ordered[start:start + query.page_size])
    count_values = (
        ("declared_count", index.counts.declared_count),
        ("included_count", index.counts.included_count),
        ("excluded_count", index.counts.excluded_count),
        ("processed_count", index.counts.processed_count),
        ("pending_count", index.counts.pending_count),
        ("missing_data_count", index.counts.missing_data_count),
        ("missing_data_pending_count", index.counts.missing_data_pending_count),
        ("ma_match_count", dict(index.ma_state_counts)["match"]),
        ("ma_no_match_count", dict(index.ma_state_counts)["no_match"]),
        ("ma_unknown_count", dict(index.ma_state_counts)["unknown"]),
        ("base_condition_match_count", base_matching_count),
        ("base_condition_unknown_count", base_unknown_count),
        ("matching_count", matching_count),
        ("matching_ma_unknown_count", selected_unknown_count),
        ("page_count", page_count),
    )
    if _return_all:
        _strict_cancel_check(cancel_callback)
        return tuple(ordered), count_values
    _strict_cancel_check(cancel_callback)
    page_body: dict[str, object] = {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_PAGE_V1_SCHEMA,
        "verification_status": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1,
        "query_json": query.to_json(),
        "query_identity_sha256": query.query_identity_sha256,
        "index_identity_sha256": index.index_identity_sha256,
        "counts": [{"name": key, "value": value} for key, value in count_values],
        "page_index": query.page_index,
        "page_size": query.page_size,
        "rows": [item.to_dict() for item in rows],
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }
    page = DailyMarketTechnicalMaAlignmentPageV1(
        query_json=query.to_json(),
        query_identity_sha256=query.query_identity_sha256,
        index_identity_sha256=index.index_identity_sha256,
        counts=count_values,
        page_index=query.page_index,
        page_size=query.page_size,
        rows=rows,
        page_identity_sha256=_sha256_json(page_body),
    )
    _strict_cancel_check(cancel_callback)
    page.to_dict()
    _strict_cancel_check(cancel_callback)
    return page


def project_unverified_entry_from_evidence_v1(
    segment_index: int,
    evidence: DailyMarketTechnicalMaAlignmentEvidenceV1,
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    parent_row: DailyMarketTechnicalParentV4Row,
    *,
    base_query: DailyMarketTechnicalUniverseV4Query,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalMaAlignmentCompactEntryV1:
    """把兩個 typed 值投影成 transport entry；不聲稱它們來自同次 exact read。"""

    _strict_cancel_check(cancel_callback)
    from app_module.daily_market_technical_feature_snapshot_v4 import DailyMarketTechnicalFeatureSnapshotV4
    from app_module.daily_market_technical_parent_v4_query import DailyMarketTechnicalParentV4Row
    from app_module.daily_market_technical_universe_v4_store import daily_market_technical_source_clock_v4_from_dict
    from app_module.daily_market_technical_ma_alignment_evidence_v1 import (
        verify_daily_market_technical_ma_alignment_evidence_v1,
    )

    if (
        type(evidence) is not DailyMarketTechnicalMaAlignmentEvidenceV1
        or type(snapshot) is not DailyMarketTechnicalFeatureSnapshotV4
        or type(parent_row) is not DailyMarketTechnicalParentV4Row
    ):
        _fail("technical_ma_alignment_query_v1_projection_input_invalid")
    base_query = _base_query(base_query)
    try:
        evidence_payload = evidence.to_dict()
        clock = daily_market_technical_source_clock_v4_from_dict(snapshot.source_clock)
        verified_evidence = verify_daily_market_technical_ma_alignment_evidence_v1(
            evidence,
            snapshot,
            expected_stock_code=snapshot.stock_code,
            expected_snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
            expected_source_identity=snapshot.source_identity,
            expected_source_clock=clock,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
        evidence_payload = verified_evidence.to_dict()
    except DailyMarketTechnicalMaAlignmentEvidenceV1Error as exc:
        raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
            "technical_ma_alignment_query_v1_evidence_transport_invalid", str(exc)
        ) from exc
    if (
        snapshot.method_contracts_sha256 != base_query.method_contracts_sha256
        or snapshot.source_clock_sha256 != base_query.source_clock_identity_sha256
        or snapshot.decision_date != base_query.decision_date
        or segment_index < 0 or segment_index >= base_query.segment_count
        or verified_evidence.stock_code != parent_row.stock_code
        or evidence.decision_date != parent_row.decision_date
        or evidence.feature_date != parent_row.latest_feature_date
        or evidence.snapshot_identity_sha256 != parent_row.snapshot_identity_sha256
        or evidence.source_identity != parent_row.source_identity
        or evidence.decision_date != base_query.decision_date
        or evidence.source_clock_sha256 != base_query.source_clock_identity_sha256
    ):
        _fail("technical_ma_alignment_query_v1_projection_pin_mismatch")
    if tuple(item.key for item in parent_row.rules) != base_query.method_rule_keys:
        _fail("technical_ma_alignment_query_v1_rule_scope_mismatch")
    rule_facts = tuple(
        DailyMarketTechnicalMaAlignmentRuleFactV1(
            key=item.key,
            state=cast(MaStateV1, item.state),
            numerator=None if item.numerator is None else str(item.numerator),
            denominator=None if item.denominator is None else str(item.denominator),
            ratio=None if item.ratio is None else str(item.ratio),
        )
        for item in parent_row.rules
    )
    entry = DailyMarketTechnicalMaAlignmentCompactEntryV1(
        stock_code=evidence.stock_code,
        segment_index=segment_index,
        decision_date=evidence.decision_date,
        latest_feature_date=parent_row.latest_feature_date,
        raw_row_count=parent_row.raw_row_count,
        observed_prefix_contiguous=parent_row.observed_prefix_contiguous,
        source_identity=parent_row.source_identity,
        snapshot_identity_sha256=parent_row.snapshot_identity_sha256,
        raw_source_window_fingerprint_sha256=evidence.raw_source_window_fingerprint_sha256,
        evidence_identity_sha256=cast(str, evidence_payload["evidence_identity_sha256"]),
        source_clock_identity_sha256=evidence.source_clock_sha256,
        feature_date=evidence.feature_date,
        ma_state=evidence.state,
        ma_reason_codes=evidence.reason_codes,
        warmup_observed_sessions=evidence.warmup_observed_sessions,
        warmup_contiguous=evidence.warmup_contiguous,
        base_rule_facts=rule_facts,
    )
    entry.to_dict()
    _strict_cancel_check(cancel_callback)
    return entry


def _issue_page(
    query: DailyMarketTechnicalMaAlignmentQueryV1,
    index: DailyMarketTechnicalMaAlignmentCompactIndexV1,
    counts: tuple[tuple[str, int], ...],
    rows: tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, ...],
) -> DailyMarketTechnicalMaAlignmentPageV1:
    body: dict[str, object] = {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_PAGE_V1_SCHEMA,
        "verification_status": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1,
        "query_json": query.to_json(),
        "query_identity_sha256": query.query_identity_sha256,
        "index_identity_sha256": index.index_identity_sha256,
        "counts": [{"name": key, "value": value} for key, value in counts],
        "page_index": query.page_index,
        "page_size": query.page_size,
        "rows": [item.to_dict() for item in rows],
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }
    return DailyMarketTechnicalMaAlignmentPageV1(
        query_json=query.to_json(),
        query_identity_sha256=query.query_identity_sha256,
        index_identity_sha256=index.index_identity_sha256,
        counts=counts,
        page_index=query.page_index,
        page_size=query.page_size,
        rows=rows,
        page_identity_sha256=_sha256_json(body),
    )


DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_SOURCE_REQUEST_V1_SCHEMA = (
    "daily-market-technical-ma-alignment-source-request.v1"
)
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_ISSUED_SESSION_V1_SCHEMA = (
    "daily-market-technical-ma-alignment-read-session.v1"
)
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_ISSUED_RESULT_V1_SCHEMA = (
    "daily-market-technical-ma-alignment-query-result.v1"
)
DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_ISSUED_PAGE_V1_SCHEMA = (
    "daily-market-technical-ma-alignment-read-page.v1"
)

_ISSUED_SESSION_SEAL = object()
_ISSUED_RESULT_SEAL = object()
_ISSUED_PAGE_SEAL = object()


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaAlignmentSourceRequestV1:
    """從明示 manifest metadata 建立的來源要求；自身仍未核驗。"""

    bundle_output_root: str
    bundle_identity_sha256: str
    manifest_relative_path: str
    expected_manifest_sha256: str
    technical_store_output_root: str
    generation_identity_sha256: str
    plan_identity_sha256: str
    plan_sha256: str
    receipt_identity_sha256: str
    receipt_sha256: str
    cohort_identity_sha256: str
    source_clock_identity_sha256: str
    method_contracts_sha256: str
    market_assignment_pin_identity_sha256: str
    official_disposal_pin_identity_sha256: str
    decision_date: date
    decision_cutoff: str
    declared_count: int
    included_count: int
    excluded_count: int
    source_coverage_status: Literal["complete", "partial"]
    source_coverage_incomplete_reason_count: int
    technical_receipt_status: Literal["complete"]

    @classmethod
    def from_unverified_manifest_metadata(
        cls,
        metadata: object,
        *,
        bundle_output_root: str | Path,
        bundle_identity_sha256: str,
        expected_manifest_sha256: str,
    ) -> DailyMarketTechnicalMaAlignmentSourceRequestV1:
        from app_module.daily_market_technical_official_disposition_bundle_v1 import (
            DailyMarketTechnicalOfficialDispositionBundleManifestMetadataV1,
        )
        from app_module.daily_market_technical_official_disposition_query_v1 import (
            normalize_daily_market_technical_official_source_pin_identity_sha256,
        )

        _strict_cancel_check(None)
        if type(metadata) is not DailyMarketTechnicalOfficialDispositionBundleManifestMetadataV1:
            _fail("technical_ma_alignment_source_request_metadata_type_invalid")
        if metadata.metadata_state != "metadata_unverified":
            _fail("technical_ma_alignment_source_request_metadata_state_invalid")
        root_text = str(bundle_output_root)
        if (
            not isinstance(bundle_output_root, (str, Path))
            or not Path(root_text).is_absolute()
            or root_text != metadata.output_root
            or bundle_identity_sha256 != metadata.bundle_identity_sha256
            or expected_manifest_sha256 != metadata.manifest_sha256
        ):
            _fail("technical_ma_alignment_source_request_bundle_pin_mismatch")
        cutoff = metadata.decision_cutoff_label
        if (
            type(metadata.decision_date_label) is not date
            or type(cutoff) is not datetime
            or cutoff.utcoffset() is None
            or cutoff.date() != metadata.decision_date_label
            or type(metadata.row_count) is not int
            or type(metadata.declared_count) is not int
            or type(metadata.included_count) is not int
            or type(metadata.excluded_count) is not int
            or type(metadata.source_coverage_incomplete_reason_count) is not int
            or metadata.row_count != metadata.declared_count
            or metadata.declared_count != metadata.included_count + metadata.excluded_count
            or metadata.declared_count > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1
        ):
            _fail("technical_ma_alignment_source_request_population_invalid")
        if (
            not isinstance(metadata.manifest_relative_path, str)
            or metadata.manifest_relative_path
            != f"manifests/{metadata.bundle_identity_sha256}.json"
            or metadata.saved_scope_label != "current_only"
            or metadata.saved_historical_pit_eligible_label is not False
            or metadata.saved_official_available_at_label is not None
            or metadata.technical_receipt_status_label != "complete"
            or metadata.source_coverage_incomplete_reason_count < 0
            or metadata.source_coverage_status_label not in {"complete", "partial"}
        ):
            _fail("technical_ma_alignment_source_request_metadata_policy_invalid")
        normalized_market = normalize_daily_market_technical_official_source_pin_identity_sha256(
            metadata.market_assignment_pin_identity_sha256
        )
        normalized_disposal = normalize_daily_market_technical_official_source_pin_identity_sha256(
            metadata.official_disposal_pin_identity_sha256
        )
        result = cls(
            bundle_output_root=root_text,
            bundle_identity_sha256=_require_sha(
                bundle_identity_sha256,
                "technical_ma_alignment_source_request_bundle_pin_invalid",
            ),
            manifest_relative_path=metadata.manifest_relative_path,
            expected_manifest_sha256=_require_sha(
                expected_manifest_sha256,
                "technical_ma_alignment_source_request_bundle_pin_invalid",
            ),
            technical_store_output_root=metadata.technical_store_output_root_label,
            generation_identity_sha256=_require_sha(
                metadata.technical_generation_identity_sha256,
                "technical_ma_alignment_source_request_technical_pin_invalid",
            ),
            plan_identity_sha256=_require_sha(
                metadata.technical_plan_identity_sha256,
                "technical_ma_alignment_source_request_technical_pin_invalid",
            ),
            plan_sha256=_require_sha(
                metadata.technical_plan_sha256,
                "technical_ma_alignment_source_request_technical_pin_invalid",
            ),
            receipt_identity_sha256=_require_sha(
                metadata.technical_receipt_identity_sha256,
                "technical_ma_alignment_source_request_technical_pin_invalid",
            ),
            receipt_sha256=_require_sha(
                metadata.technical_receipt_sha256,
                "technical_ma_alignment_source_request_technical_pin_invalid",
            ),
            cohort_identity_sha256=_require_sha(
                metadata.cohort_identity_sha256,
                "technical_ma_alignment_source_request_technical_pin_invalid",
            ),
            source_clock_identity_sha256=_require_sha(
                metadata.source_clock_identity_sha256,
                "technical_ma_alignment_source_request_technical_pin_invalid",
            ),
            method_contracts_sha256=_require_sha(
                metadata.method_contracts_sha256,
                "technical_ma_alignment_source_request_technical_pin_invalid",
            ),
            market_assignment_pin_identity_sha256=normalized_market,
            official_disposal_pin_identity_sha256=normalized_disposal,
            decision_date=metadata.decision_date_label,
            decision_cutoff=metadata.decision_cutoff_label.isoformat(),
            declared_count=metadata.declared_count,
            included_count=metadata.included_count,
            excluded_count=metadata.excluded_count,
            source_coverage_status=metadata.source_coverage_status_label,
            source_coverage_incomplete_reason_count=metadata.source_coverage_incomplete_reason_count,
            technical_receipt_status="complete",
        )
        result.to_dict()
        return result

    @property
    def request_identity_sha256(self) -> str:
        return _sha256_json(self.to_dict())

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
        if (
            not Path(self.bundle_output_root).is_absolute()
            or not Path(self.technical_store_output_root).is_absolute()
            or self.manifest_relative_path
            != f"manifests/{self.bundle_identity_sha256}.json"
            or self.source_coverage_status not in {"complete", "partial"}
            or type(self.declared_count) is not int
            or type(self.included_count) is not int
            or type(self.excluded_count) is not int
            or self.declared_count != self.included_count + self.excluded_count
            or self.declared_count > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1
            or type(self.source_coverage_incomplete_reason_count) is not int
            or self.source_coverage_incomplete_reason_count < 0
            or self.technical_receipt_status != "complete"
            or type(self.decision_date) is not date
            or self.source_coverage_status not in {"complete", "partial"}
        ):
            _fail("technical_ma_alignment_source_request_invalid")
        try:
            cutoff = datetime.fromisoformat(self.decision_cutoff)
        except (TypeError, ValueError) as exc:
            raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
                "technical_ma_alignment_source_request_cutoff_invalid", str(exc)
            ) from exc
        if cutoff.utcoffset() is None or cutoff.isoformat() != self.decision_cutoff or cutoff.date() != self.decision_date:
            _fail("technical_ma_alignment_source_request_cutoff_invalid")
        for value in (
            self.bundle_identity_sha256,
            self.expected_manifest_sha256,
            self.generation_identity_sha256,
            self.plan_identity_sha256,
            self.plan_sha256,
            self.receipt_identity_sha256,
            self.receipt_sha256,
            self.cohort_identity_sha256,
            self.source_clock_identity_sha256,
            self.method_contracts_sha256,
            self.market_assignment_pin_identity_sha256,
            self.official_disposal_pin_identity_sha256,
        ):
            _require_sha(value, "technical_ma_alignment_source_request_pin_invalid")
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_SOURCE_REQUEST_V1_SCHEMA,
            "verification_status": "metadata_unverified",
            "bundle_output_root": self.bundle_output_root,
            "bundle_identity_sha256": self.bundle_identity_sha256,
            "manifest_relative_path": self.manifest_relative_path,
            "expected_manifest_sha256": self.expected_manifest_sha256,
            "technical_store_output_root": self.technical_store_output_root,
            "generation_identity_sha256": self.generation_identity_sha256,
            "plan_identity_sha256": self.plan_identity_sha256,
            "plan_sha256": self.plan_sha256,
            "receipt_identity_sha256": self.receipt_identity_sha256,
            "receipt_sha256": self.receipt_sha256,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "source_clock_identity_sha256": self.source_clock_identity_sha256,
            "method_contracts_sha256": self.method_contracts_sha256,
            "market_assignment_pin_identity_sha256": self.market_assignment_pin_identity_sha256,
            "official_disposal_pin_identity_sha256": self.official_disposal_pin_identity_sha256,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff,
            "declared_count": self.declared_count,
            "included_count": self.included_count,
            "excluded_count": self.excluded_count,
            "source_coverage_status": self.source_coverage_status,
            "source_coverage_incomplete_reason_count": self.source_coverage_incomplete_reason_count,
            "technical_receipt_status": self.technical_receipt_status,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }


@dataclass(frozen=True, slots=True)
class _ParentProjectionObservationV1:
    segment_index: int
    parent_root: str | None
    snapshot_repository_root: str
    parent_plan_identity_sha256: str
    parent_plan_sha256: str
    parent_receipt_identity_sha256: str
    parent_receipt_sha256: str
    cohort_identity_sha256: str
    included_stock_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ActiveParentProjectionV1:
    segment_index: int
    parent_read: object = field(repr=False, compare=False)
    expected_stock_codes: tuple[str, ...]
    expected_snapshots: tuple[object, ...] = field(repr=False, compare=False)
    consumed_stock_codes: list[str] = field(repr=False, compare=False)


class DailyMarketTechnicalMaAlignmentVerifiedCollectorV1:
    """在 exact parent callback 的既有 snapshot→row 迴圈累積一次 MA 投影。"""

    def __init__(
        self,
        source_request: DailyMarketTechnicalMaAlignmentSourceRequestV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> None:
        if type(source_request) is not DailyMarketTechnicalMaAlignmentSourceRequestV1:
            _fail("technical_ma_alignment_collector_source_request_invalid")
        source_request.to_dict()
        self.source_request = source_request
        self.cancel_callback = cancel_callback
        self._bound_builder: object | None = None
        self._active_parent: _ActiveParentProjectionV1 | None = None
        self._observations: list[_ParentProjectionObservationV1] = []
        self._entries: list[DailyMarketTechnicalMaAlignmentCompactEntryV1] = []
        self._seen_codes: set[str] = set()
        self._finished = False
        self._issued_session: DailyMarketTechnicalMaAlignmentReadSessionV1 | None = None

    def bind_to_builder(self, builder: object) -> None:
        from app_module.daily_market_technical_universe_v4_query import (
            DailyMarketTechnicalUniverseV4ReadSessionBuilder,
        )

        _strict_cancel_check(self.cancel_callback)
        if type(builder) is not DailyMarketTechnicalUniverseV4ReadSessionBuilder:
            _fail("technical_ma_alignment_collector_builder_type_invalid")
        if self._bound_builder is not None or self._observations or self._finished:
            _fail("technical_ma_alignment_collector_already_bound")
        request = self.source_request
        if (
            builder.store_output_root != request.technical_store_output_root
            or builder.generation_identity_sha256 != request.generation_identity_sha256
            or builder.plan_identity_sha256 != request.plan_identity_sha256
            or builder.plan_sha256 != request.plan_sha256
            or builder.receipt_identity_sha256 != request.receipt_identity_sha256
            or builder.receipt_sha256 != request.receipt_sha256
            or builder._bundle_pin is not None
            or builder.verified_session is not None
        ):
            _fail("technical_ma_alignment_collector_builder_source_mismatch")
        self._bound_builder = builder

    def begin_verified_parent(self, segment_index: int, parent_read: object) -> None:
        from app_module.rule_research_technical_parent_capture_v4 import (
            DailyMarketTechnicalParentCaptureV4VerifiedRead,
        )
        from app_module.daily_market_technical_feature_snapshot_v4 import (
            DailyMarketTechnicalFeatureSnapshotV4,
        )
        from app_module.daily_market_technical_method_contract_v4 import (
            DAILY_MARKET_TECHNICAL_RULE_KEYS_V4,
            validate_daily_market_technical_method_contract_v4,
        )
        from app_module.daily_market_technical_universe_v4_store import (
            daily_market_technical_source_clock_v4_from_dict,
        )

        _strict_cancel_check(self.cancel_callback)
        if (
            self._bound_builder is None
            or self._finished
            or self._active_parent is not None
            or type(segment_index) is not int
            or segment_index != len(self._observations)
            or type(parent_read) is not DailyMarketTechnicalParentCaptureV4VerifiedRead
        ):
            _fail("technical_ma_alignment_collector_parent_order_invalid")
        package = parent_read.package
        plan = package.get("plan")
        receipt = package.get("receipt")
        if not isinstance(plan, Mapping) or not isinstance(receipt, Mapping):
            _fail("technical_ma_alignment_collector_parent_invalid")
        cohort = plan.get("cohort")
        clock = plan.get("source_clock")
        method = plan.get("method_contracts")
        if not isinstance(cohort, Mapping) or not isinstance(clock, Mapping) or not isinstance(method, Mapping):
            _fail("technical_ma_alignment_collector_parent_invalid")
        rules = method.get("rules")
        if not isinstance(rules, list):
            _fail("technical_ma_alignment_collector_method_invalid")
        try:
            source_clock = daily_market_technical_source_clock_v4_from_dict(clock)
            validate_daily_market_technical_method_contract_v4(
                method, expected_sha256=self.source_request.method_contracts_sha256
            )
        except Exception as exc:
            raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
                "technical_ma_alignment_collector_parent_contract_invalid", str(exc)
            ) from exc
        rule_keys = tuple(
            item.get("key") for item in rules if isinstance(item, Mapping)
        )
        request = self.source_request
        included = cohort.get("included_stock_codes")
        parent_generation_identity = plan.get("generation_identity_sha256")
        parent_plan_identity = plan.get("parent_plan_identity_sha256")
        parent_receipt_identity = receipt.get("receipt_identity_sha256")
        parent_plan_sha256 = package.get("plan_sha256")
        parent_receipt_sha256 = package.get("receipt_sha256")
        if (
            not isinstance(parent_generation_identity, str)
            or not _is_sha(parent_generation_identity)
            or not isinstance(parent_plan_identity, str)
            or not _is_sha(parent_plan_identity)
            or not isinstance(parent_receipt_identity, str)
            or not _is_sha(parent_receipt_identity)
            or not isinstance(parent_plan_sha256, str)
            or not _is_sha(parent_plan_sha256)
            or not isinstance(parent_receipt_sha256, str)
            or not _is_sha(parent_receipt_sha256)
            or receipt.get("generation_identity_sha256") != parent_generation_identity
            or plan.get("source_clock_identity_sha256") != request.source_clock_identity_sha256
            or receipt.get("source_clock_identity_sha256") != request.source_clock_identity_sha256
            or source_clock.identity_sha256 != request.source_clock_identity_sha256
            or source_clock.decision_date != request.decision_date
            or source_clock.decision_cutoff.isoformat() != request.decision_cutoff
            or plan.get("method_contracts_sha256") != request.method_contracts_sha256
            or tuple(rule_keys) != tuple(DAILY_MARKET_TECHNICAL_RULE_KEYS_V4)
            or cohort.get("decision_date") != request.decision_date.isoformat()
            or not isinstance(cohort.get("universe_id"), str)
            or not isinstance(cohort.get("population_version"), str)
            or receipt.get("status") != "complete"
            or receipt.get("parent_plan_identity_sha256") != parent_plan_identity
            or not isinstance(included, list)
            or any(not isinstance(code, str) or _STOCK_CODE_RE.fullmatch(code) is None for code in included)
            or tuple(included) != tuple(sorted(set(included)))
        ):
            _fail("technical_ma_alignment_collector_parent_source_mismatch")
        batches = plan.get("batches")
        artifacts = receipt.get("batch_artifacts")
        verified_batches = parent_read.verified_batches
        if (
            not isinstance(batches, list)
            or not isinstance(artifacts, list)
            or len(batches) != len(artifacts)
            or len(artifacts) != len(verified_batches)
        ):
            _fail("technical_ma_alignment_collector_parent_batch_mismatch")
        batch_codes: list[str] = []
        for batch in batches:
            if not isinstance(batch, Mapping) or not isinstance(batch.get("expected_stock_codes"), list):
                _fail("technical_ma_alignment_collector_parent_batch_mismatch")
            raw_codes = batch["expected_stock_codes"]
            if any(not isinstance(code, str) for code in raw_codes):
                _fail("technical_ma_alignment_collector_parent_batch_mismatch")
            batch_codes.extend(cast(list[str], raw_codes))
        if tuple(batch_codes) != tuple(cast(list[str], included)):
            _fail("technical_ma_alignment_collector_parent_batch_mismatch")
        verified_snapshots = tuple(
            snapshot
            for verified_batch in verified_batches
            for snapshot in verified_batch.snapshots
        )
        if (
            len(verified_snapshots) != len(batch_codes)
            or any(type(item) is not DailyMarketTechnicalFeatureSnapshotV4 for item in verified_snapshots)
            or tuple(item.stock_code for item in verified_snapshots) != tuple(batch_codes)
        ):
            _fail("technical_ma_alignment_collector_parent_snapshot_order_invalid")
        self._active_parent = _ActiveParentProjectionV1(
            segment_index=segment_index,
            parent_read=parent_read,
            expected_stock_codes=tuple(cast(list[str], included)),
            expected_snapshots=verified_snapshots,
            consumed_stock_codes=[],
        )

    def consume_verified_snapshot(
        self,
        segment_index: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        from app_module.daily_market_technical_feature_snapshot_v4 import (
            DailyMarketTechnicalFeatureSnapshotV4,
        )
        from app_module.daily_market_technical_parent_v4_query import (
            DailyMarketTechnicalParentV4Row,
        )
        from app_module.daily_market_technical_read_session import (
            DailyMarketTechnicalSourceClockV4,
        )
        from app_module.daily_market_technical_universe_v4_store import (
            daily_market_technical_source_clock_v4_from_dict,
        )
        from app_module.daily_market_technical_ma_alignment_evidence_v1 import (
            build_daily_market_technical_ma_alignment_evidence_v1,
        )

        _strict_cancel_check(self.cancel_callback)
        active = self._active_parent
        if (
            self._finished
            or active is None
            or segment_index != active.segment_index
            or type(snapshot) is not DailyMarketTechnicalFeatureSnapshotV4
            or type(parent_row) is not DailyMarketTechnicalParentV4Row
        ):
            _fail("technical_ma_alignment_collector_snapshot_input_invalid")
        expected_codes = active.expected_stock_codes
        consumed_codes = active.consumed_stock_codes
        position = len(consumed_codes)
        if (
            position >= len(expected_codes)
            or snapshot.stock_code != expected_codes[position]
            or position >= len(active.expected_snapshots)
            or snapshot is not active.expected_snapshots[position]
            or snapshot.stock_code in self._seen_codes
        ):
            _fail("technical_ma_alignment_collector_snapshot_order_invalid")
        request = self.source_request
        try:
            clock = daily_market_technical_source_clock_v4_from_dict(snapshot.source_clock)
        except (TypeError, ValueError) as exc:
            raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
                "technical_ma_alignment_collector_source_clock_invalid", str(exc)
            ) from exc
        if not isinstance(clock, DailyMarketTechnicalSourceClockV4) or (
            clock.identity_sha256 != request.source_clock_identity_sha256
            or clock.decision_date != request.decision_date
            or clock.decision_cutoff.isoformat() != request.decision_cutoff
            or snapshot.method_contracts_sha256 != request.method_contracts_sha256
            or snapshot.decision_date != request.decision_date
            or parent_row.decision_date != request.decision_date
            or parent_row.stock_code != snapshot.stock_code
            or parent_row.snapshot_identity_sha256 != snapshot.snapshot_identity_sha256
            or parent_row.source_identity != snapshot.source_identity
            or parent_row.raw_row_count != len(snapshot.rows)
            or parent_row.observed_prefix_contiguous != snapshot.observed_prefix_contiguous
            or parent_row.latest_feature_date != (
                snapshot.current_session.feature_date if snapshot.current_session else None
            )
            or tuple(parent_row.rules) != tuple(snapshot.rules)
        ):
            _fail("technical_ma_alignment_collector_snapshot_source_mismatch")
        try:
            evidence = build_daily_market_technical_ma_alignment_evidence_v1(
                snapshot,
                expected_stock_code=snapshot.stock_code,
                expected_snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
                expected_source_identity=snapshot.source_identity,
                expected_source_clock=clock,
                cancel_callback=cast(Callable[[], bool] | None, self.cancel_callback),
            )
        except DailyMarketTechnicalMaAlignmentEvidenceV1Error as exc:
            raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
                "technical_ma_alignment_collector_evidence_invalid", str(exc)
            ) from exc
        entry = _project_verified_snapshot_entry_v1(
            segment_index, evidence, snapshot, parent_row, request
        )
        consumed_codes.append(snapshot.stock_code)
        self._seen_codes.add(snapshot.stock_code)
        self._entries.append(entry)
        _strict_cancel_check(self.cancel_callback)

    def end_verified_parent(self, segment_index: int, parent_read: object) -> None:
        active = self._active_parent
        if (
            active is None
            or active.segment_index != segment_index
            or active.parent_read is not parent_read
            or tuple(active.consumed_stock_codes) != active.expected_stock_codes
            or len(active.expected_snapshots) != len(active.expected_stock_codes)
        ):
            _fail("technical_ma_alignment_collector_parent_incomplete")
        package = cast(Any, parent_read).package
        plan = cast(Mapping[str, object], package["plan"])
        receipt = cast(Mapping[str, object], package["receipt"])
        cohort = cast(Mapping[str, object], plan["cohort"])
        observation = _ParentProjectionObservationV1(
            segment_index=segment_index,
            # 這是 parent receipt 指向的子快照 repository；parent capture root
            # 要等完整 P01 state 發行後，才能從同段 exact reference 綁定。
            parent_root=None,
            snapshot_repository_root=cast(str, receipt["repository_output_root"]),
            parent_plan_identity_sha256=cast(str, plan["parent_plan_identity_sha256"]),
            parent_plan_sha256=cast(str, package["plan_sha256"]),
            parent_receipt_identity_sha256=cast(str, receipt["receipt_identity_sha256"]),
            parent_receipt_sha256=cast(str, package["receipt_sha256"]),
            cohort_identity_sha256=cast(str, cohort["cohort_identity_sha256"]),
            included_stock_codes=active.expected_stock_codes,
        )
        if (
            not isinstance(observation.snapshot_repository_root, str)
            or not observation.snapshot_repository_root
            or not Path(observation.snapshot_repository_root).is_absolute()
            or not all(_is_sha(value) for value in (
                observation.parent_plan_identity_sha256,
                observation.parent_plan_sha256,
                observation.parent_receipt_identity_sha256,
                observation.parent_receipt_sha256,
                observation.cohort_identity_sha256,
            ))
        ):
            _fail("technical_ma_alignment_collector_parent_reference_invalid")
        self._observations.append(observation)
        self._active_parent = None
        _strict_cancel_check(self.cancel_callback)

    def finalize_verified_publication(
        self,
        builder: object,
        bundle_state: object,
        base_query: object,
        selection: object,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalMaAlignmentReadSessionV1:
        from app_module.daily_market_technical_official_disposition_bundle_v1 import (
            DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
        )
        from app_module.daily_market_technical_universe_v4_query import (
            DailyMarketTechnicalUniverseV4Query,
            DailyMarketTechnicalUniverseV4ReadSelection,
            DailyMarketTechnicalUniverseV4ReadSession,
            DailyMarketTechnicalUniverseV4ReadSessionBuilder,
        )
        from app_module.daily_market_technical_universe_v4_store import (
            DailyMarketTechnicalUniverseV4VerifiedState,
        )

        _strict_cancel_check(self.cancel_callback)
        _strict_cancel_check(cancel_callback)
        if (
            self._finished
            or self._active_parent is not None
            or self._bound_builder is not builder
            or type(builder) is not DailyMarketTechnicalUniverseV4ReadSessionBuilder
            or builder._verified_projection is not self
            or type(bundle_state) is not DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1
            or type(base_query) is not DailyMarketTechnicalUniverseV4Query
            or type(selection) is not DailyMarketTechnicalUniverseV4ReadSelection
        ):
            _fail("technical_ma_alignment_collector_publication_input_invalid")
        request = self.source_request
        p01_session = builder.verified_session
        if (
            p01_session is None
            or builder._built_session is not p01_session
            or builder._bundle_pin != (
                request.bundle_output_root,
                request.bundle_identity_sha256,
                request.expected_manifest_sha256,
            )
            or type(p01_session) is not DailyMarketTechnicalUniverseV4ReadSession
            or not p01_session.matches_source(base_query)
            or selection._query != base_query
            or selection._read_session_identity_sha256 != p01_session.read_session_identity_sha256
        ):
            _fail("technical_ma_alignment_collector_publication_source_mismatch")
        try:
            bundle_state.__post_init__()
            p01_session._validate_selection(selection)
        except Exception as exc:
            if isinstance(exc, DailyMarketTechnicalUniverseMaAlignmentQueryV1Error):
                raise
            raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
                "technical_ma_alignment_collector_publication_proof_invalid", str(exc)
            ) from exc
        manifest = bundle_state.manifest
        _validate_bundle_source_request_v1(request, bundle_state, manifest)
        store_state = p01_session._state
        if type(store_state) is not DailyMarketTechnicalUniverseV4VerifiedState:
            _fail("technical_ma_alignment_collector_store_state_invalid")
        _validate_p01_state_against_request_v1(request, store_state)
        _validate_query_source_request_v1(request, cast(DailyMarketTechnicalUniverseV4Query, base_query))
        finalized_parent_observations = _validate_collector_observations_v1(
            self._observations, store_state
        )
        if (
            len(self._entries) != store_state.counts.processed_count
            or tuple(entry.stock_code for entry in self._entries)
            != tuple(sorted(set(entry.stock_code for entry in self._entries)))
            or sum(entry.raw_row_count == 0 for entry in self._entries)
            != store_state.counts.missing_data_count
            or any(code not in self._seen_codes for code in selection.stock_codes)
        ):
            _fail("technical_ma_alignment_collector_population_mismatch")
        method_keys = cast(tuple[str, ...], tuple(base_query.method_rule_keys))
        if any(tuple(fact.key for fact in entry.base_rule_facts) != method_keys for entry in self._entries):
            _fail("technical_ma_alignment_collector_rule_scope_mismatch")
        index = DailyMarketTechnicalMaAlignmentCompactIndexV1.create_unverified_transport(
            cast(DailyMarketTechnicalUniverseV4Query, base_query),
            source_clock_json=_canonical_json_bytes(store_state.plan.source_clock.to_dict()).decode("utf-8"),
            entries=tuple(self._entries),
            cancel_callback=cancel_callback,
        )
        _strict_cancel_check(self.cancel_callback)
        _strict_cancel_check(cancel_callback)
        issued = _issue_ma_alignment_read_session_v1(
            request=request,
            builder=builder,
            bundle_state=bundle_state,
            p01_session=p01_session,
            base_query=cast(DailyMarketTechnicalUniverseV4Query, base_query),
            selection=selection,
            index=index,
            parent_observations=finalized_parent_observations,
        )
        _strict_cancel_check(self.cancel_callback)
        _strict_cancel_check(cancel_callback)
        self._finished = True
        self._issued_session = issued
        return issued


@dataclass(frozen=True, slots=True)
class _MaAlignmentSessionAnchorV1:
    identity_sha256: str
    request_identity_sha256: str
    bundle_state: object = field(repr=False, compare=False)
    builder: object = field(repr=False, compare=False)
    p01_session: object = field(repr=False, compare=False)
    base_query: object = field(repr=False, compare=False)
    selection: object = field(repr=False, compare=False)
    index: object = field(repr=False, compare=False)
    parent_observations_identity_sha256: str


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaAlignmentReadSessionV1:
    """同一已核 P01/F17 工作階段的 MA compact index reader。"""

    source_request: DailyMarketTechnicalMaAlignmentSourceRequestV1
    read_session_identity_sha256: str
    index_identity_sha256: str
    source_available_at: None
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]
    _p01_session: object = field(repr=False, compare=False)
    _base_query: object = field(repr=False, compare=False)
    _initial_selection: object = field(repr=False, compare=False)
    _index: object = field(repr=False, compare=False)
    _anchor: _MaAlignmentSessionAnchorV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _ISSUED_SESSION_SEAL
            or type(self._anchor) is not _MaAlignmentSessionAnchorV1
            or self._anchor.identity_sha256 != self.read_session_identity_sha256
            or self._anchor.request_identity_sha256 != self.source_request.request_identity_sha256
            or self._anchor.p01_session is not self._p01_session
            or self._anchor.base_query is not self._base_query
            or self._anchor.selection is not self._initial_selection
            or self._anchor.index is not self._index
            or self._anchor.bundle_state is None
            or self._anchor.builder is None
            or self.source_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
            or self.index_identity_sha256 != cast(DailyMarketTechnicalMaAlignmentCompactIndexV1, self._index).index_identity_sha256
            or _ma_session_identity_v1(
                self.source_request,
                self._p01_session,
                self._base_query,
                self._initial_selection,
                self._index,
                self._anchor.bundle_state,
                self._anchor.parent_observations_identity_sha256,
            ) != self.read_session_identity_sha256
        ):
            _fail("technical_ma_alignment_read_session_invalid")

    @property
    def reader_issued(self) -> Literal[True]:
        return True

    def create_query(
        self,
        base_query: object,
        *,
        ma_states: Sequence[MaStateV1] | None = None,
        combine_mode: CombineModeV1 = "AND",
        eligible_stock_codes: Sequence[str] | None = None,
        sort_mode: SortModeV1 = "base",
        descending: bool = False,
        page_index: int = 0,
        page_size: int = 50,
    ) -> DailyMarketTechnicalMaAlignmentQueryV1:
        from app_module.daily_market_technical_universe_v4_query import DailyMarketTechnicalUniverseV4Query

        self._validate_session_anchor()
        if type(base_query) is not DailyMarketTechnicalUniverseV4Query:
            _fail("technical_ma_alignment_query_v1_base_query_invalid")
        _validate_query_source_request_v1(self.source_request, cast(DailyMarketTechnicalUniverseV4Query, base_query))
        if not cast(Any, self._p01_session).matches_source(base_query):
            _fail("technical_ma_alignment_query_v1_query_source_mismatch")
        return DailyMarketTechnicalMaAlignmentQueryV1.create(
            cast(DailyMarketTechnicalUniverseV4Query, base_query),
            cast(DailyMarketTechnicalMaAlignmentCompactIndexV1, self._index),
            ma_states=ma_states,
            combine_mode=combine_mode,
            eligible_stock_codes=eligible_stock_codes,
            sort_mode=sort_mode,
            descending=descending,
            page_index=page_index,
            page_size=page_size,
        )

    def execute(
        self,
        query: DailyMarketTechnicalMaAlignmentQueryV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalMaAlignmentReadResultV1:
        self._validate_session_anchor()
        _strict_cancel_check(cancel_callback)
        if type(query) is not DailyMarketTechnicalMaAlignmentQueryV1:
            _fail("technical_ma_alignment_issued_query_invalid")
        query.to_dict()
        index = cast(DailyMarketTechnicalMaAlignmentCompactIndexV1, self._index)
        base_query = _base_query(query.base_query_json)
        _validate_query_source_request_v1(self.source_request, base_query)
        if (
            query.ma_index_identity_sha256 != self.index_identity_sha256
            or not _same_base_query_source_scope(base_query, _base_query(index.base_query_json))
            or not cast(Any, self._p01_session).matches_source(base_query)
        ):
            _fail("technical_ma_alignment_issued_query_source_mismatch")
        ordered, counts = cast(
            tuple[tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, ...], tuple[tuple[str, int], ...]],
            evaluate_unverified_ma_alignment_page_v1(
                query,
                index,
                cancel_callback=cancel_callback,
                _return_all=True,
            ),
        )
        _strict_cancel_check(cancel_callback)
        p01_session = cast(Any, self._p01_session)
        unrestricted = p01_session.create_query(
            rule_state_filters=(),
            combine_mode="AND",
            stock_filter=(),
            sort_key="stock_code",
            descending=False,
            page_index=0,
            page_size=1,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
        selected_codes = tuple(entry.stock_code for entry in ordered)
        selection = p01_session.select_stock_codes(
            unrestricted,
            eligible_stock_codes=selected_codes,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
        if selection.matching_count != len(selected_codes):
            _fail("technical_ma_alignment_issued_selection_mismatch")
        result = _issue_ma_alignment_read_result_v1(
            read_session=self,
            query=query,
            selection=selection,
            ordered_entries=ordered,
            counts=counts,
        )
        _strict_cancel_check(cancel_callback)
        return result

    def _validate_session_anchor(self) -> None:
        if (
            self._seal is not _ISSUED_SESSION_SEAL
            or type(self._anchor) is not _MaAlignmentSessionAnchorV1
            or self._anchor.identity_sha256 != self.read_session_identity_sha256
            or self._anchor.request_identity_sha256 != self.source_request.request_identity_sha256
            or self._anchor.builder is None
            or getattr(self._anchor.builder, "verified_session", None) is not self._p01_session
            or getattr(self._anchor.builder, "_bundle_pin", None) != (
                self.source_request.bundle_output_root,
                self.source_request.bundle_identity_sha256,
                self.source_request.expected_manifest_sha256,
            )
            or self._anchor.bundle_state is None
            or self._anchor.p01_session is not self._p01_session
            or self._anchor.index is not self._index
            or self.index_identity_sha256
            != cast(DailyMarketTechnicalMaAlignmentCompactIndexV1, self._index).index_identity_sha256
            or _ma_session_identity_v1(
                self.source_request,
                self._p01_session,
                self._base_query,
                self._initial_selection,
                self._index,
                self._anchor.bundle_state,
                self._anchor.parent_observations_identity_sha256,
            ) != self.read_session_identity_sha256
        ):
            _fail("technical_ma_alignment_read_session_invalid")


def _ma_session_identity_v1(
    request: DailyMarketTechnicalMaAlignmentSourceRequestV1,
    p01_session: object,
    base_query: object,
    selection: object,
    index: object,
    bundle_state: object,
    parent_observations_identity_sha256: str,
) -> str:
    from app_module.daily_market_technical_universe_v4_query import (
        DailyMarketTechnicalUniverseV4ReadSelection,
        DailyMarketTechnicalUniverseV4ReadSession,
        DailyMarketTechnicalUniverseV4Query,
    )
    from app_module.daily_market_technical_official_disposition_bundle_v1 import (
        DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
    )

    if (
        type(p01_session) is not DailyMarketTechnicalUniverseV4ReadSession
        or type(base_query) is not DailyMarketTechnicalUniverseV4Query
        or type(selection) is not DailyMarketTechnicalUniverseV4ReadSelection
        or type(bundle_state) is not DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1
        or type(index) is not DailyMarketTechnicalMaAlignmentCompactIndexV1
    ):
        _fail("technical_ma_alignment_session_identity_input_invalid")
    reference = bundle_state.reference
    return _sha256_json({
        "schema": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_ISSUED_SESSION_V1_SCHEMA,
        "source_request_identity_sha256": request.request_identity_sha256,
        "bundle_identity_sha256": reference.bundle_identity_sha256,
        "bundle_manifest_sha256": reference.manifest_sha256,
        "p01_read_session_identity_sha256": p01_session.read_session_identity_sha256,
        "base_source_scope_identity_sha256": _sha256_json(_base_query_source_scope(base_query)),
        "initial_selection_identity_sha256": selection.selection_identity_sha256,
        "ma_index_identity_sha256": index.index_identity_sha256,
        "parent_observations_identity_sha256": parent_observations_identity_sha256,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    })


def _issue_ma_alignment_read_session_v1(
    *,
    request: DailyMarketTechnicalMaAlignmentSourceRequestV1,
    builder: object,
    bundle_state: object,
    p01_session: object,
    base_query: object,
    selection: object,
    index: object,
    parent_observations: tuple[_ParentProjectionObservationV1, ...],
) -> DailyMarketTechnicalMaAlignmentReadSessionV1:
    parent_digest = _sha256_json([
        {
            "segment_index": item.segment_index,
            "parent_root": item.parent_root,
            "snapshot_repository_root": item.snapshot_repository_root,
            "parent_plan_identity_sha256": item.parent_plan_identity_sha256,
            "parent_plan_sha256": item.parent_plan_sha256,
            "parent_receipt_identity_sha256": item.parent_receipt_identity_sha256,
            "parent_receipt_sha256": item.parent_receipt_sha256,
            "cohort_identity_sha256": item.cohort_identity_sha256,
            "included_stock_codes": list(item.included_stock_codes),
        }
        for item in parent_observations
    ])
    identity = _ma_session_identity_v1(
        request, p01_session, base_query, selection, index, bundle_state, parent_digest
    )
    anchor = _MaAlignmentSessionAnchorV1(
        identity_sha256=identity,
        request_identity_sha256=request.request_identity_sha256,
        bundle_state=bundle_state,
        builder=builder,
        p01_session=p01_session,
        base_query=base_query,
        selection=selection,
        index=index,
        parent_observations_identity_sha256=parent_digest,
    )
    return DailyMarketTechnicalMaAlignmentReadSessionV1(
        source_request=request,
        read_session_identity_sha256=identity,
        index_identity_sha256=cast(DailyMarketTechnicalMaAlignmentCompactIndexV1, index).index_identity_sha256,
        source_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
        _p01_session=p01_session,
        _base_query=base_query,
        _initial_selection=selection,
        _index=index,
        _anchor=anchor,
        _seal=_ISSUED_SESSION_SEAL,
    )


def _validate_bundle_source_request_v1(
    request: DailyMarketTechnicalMaAlignmentSourceRequestV1,
    bundle_state: object,
    manifest: Mapping[str, object],
) -> None:
    from app_module.daily_market_technical_official_disposition_bundle_v1 import (
        DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
    )
    from app_module.daily_market_technical_official_disposition_query_v1 import (
        normalize_daily_market_technical_official_source_pin_identity_sha256,
    )
    from app_module.daily_market_technical_universe_v4_store import (
        daily_market_technical_source_clock_v4_from_dict,
    )

    if type(bundle_state) is not DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1:
        _fail("technical_ma_alignment_bundle_state_invalid")
    reference = bundle_state.reference
    technical = manifest.get("technical_store")
    pins = manifest.get("source_pins")
    if not isinstance(technical, Mapping) or not isinstance(pins, Mapping):
        _fail("technical_ma_alignment_bundle_manifest_pins_invalid")
    try:
        clock = daily_market_technical_source_clock_v4_from_dict(technical.get("source_clock"))
    except Exception as exc:
        raise DailyMarketTechnicalUniverseMaAlignmentQueryV1Error(
            "technical_ma_alignment_bundle_source_clock_invalid", str(exc)
        ) from exc
    expected_technical = {
        "output_root": request.technical_store_output_root,
        "generation_identity_sha256": request.generation_identity_sha256,
        "plan_identity_sha256": request.plan_identity_sha256,
        "plan_sha256": request.plan_sha256,
        "receipt_identity_sha256": request.receipt_identity_sha256,
        "receipt_sha256": request.receipt_sha256,
        "cohort_identity_sha256": request.cohort_identity_sha256,
        "decision_date": request.decision_date.isoformat(),
        "declared_count": request.declared_count,
        "included_count": request.included_count,
        "excluded_count": request.excluded_count,
        "source_clock_identity_sha256": request.source_clock_identity_sha256,
        "method_contracts_sha256": request.method_contracts_sha256,
        "receipt_status": "complete",
    }
    if (
        reference.output_root != request.bundle_output_root
        or reference.bundle_identity_sha256 != request.bundle_identity_sha256
        or reference.manifest_sha256 != request.expected_manifest_sha256
        or reference.manifest_relative_path != request.manifest_relative_path
        or reference.projection_status != "complete"
        or reference.row_count != request.declared_count
        or manifest.get("scope") != "current_only"
        or manifest.get("historical_pit_eligible") is not False
        or manifest.get("official_available_at") is not None
        or manifest.get("source_coverage_status") != request.source_coverage_status
        or clock.identity_sha256 != request.source_clock_identity_sha256
        or clock.decision_date != request.decision_date
        or clock.decision_cutoff.isoformat() != request.decision_cutoff
        or any(technical.get(key) != value for key, value in expected_technical.items())
    ):
        _fail("technical_ma_alignment_bundle_manifest_source_mismatch")
    coverage = manifest.get("source_coverage")
    if (
        not isinstance(coverage, Mapping)
        or not isinstance(coverage.get("incomplete_reasons"), list)
        or len(cast(list[object], coverage["incomplete_reasons"]))
        != request.source_coverage_incomplete_reason_count
    ):
        _fail("technical_ma_alignment_bundle_coverage_mismatch")
    market = pins.get("market_assignment")
    disposal = pins.get("official_disposal")
    if not isinstance(market, Mapping) or not isinstance(disposal, Mapping):
        _fail("technical_ma_alignment_bundle_manifest_source_mismatch")
    market_identity = normalize_daily_market_technical_official_source_pin_identity_sha256(
        market.get("identity_sha256")
    )
    disposal_identity = normalize_daily_market_technical_official_source_pin_identity_sha256(
        disposal.get("identity_sha256")
    )
    if (
        market_identity != request.market_assignment_pin_identity_sha256
        or disposal_identity != request.official_disposal_pin_identity_sha256
    ):
        _fail("technical_ma_alignment_bundle_source_pin_mismatch")


def _validate_p01_state_against_request_v1(
    request: DailyMarketTechnicalMaAlignmentSourceRequestV1,
    state: object,
) -> None:
    from app_module.daily_market_technical_universe_v4_store import DailyMarketTechnicalUniverseV4VerifiedState

    if type(state) is not DailyMarketTechnicalUniverseV4VerifiedState:
        _fail("technical_ma_alignment_store_state_invalid")
    cohort = state.plan.cohort
    if (
        state.plan.generation_identity_sha256 != request.generation_identity_sha256
        or state.plan.identity_sha256 != request.plan_identity_sha256
        or _sha256_bytes(state.plan.to_json().encode("utf-8")) != request.plan_sha256
        or state.receipt.identity_sha256 != request.receipt_identity_sha256
        or _sha256_bytes(state.receipt.to_json().encode("utf-8")) != request.receipt_sha256
        or cohort.cohort_identity_sha256 != request.cohort_identity_sha256
        or state.plan.source_clock.identity_sha256 != request.source_clock_identity_sha256
        or state.plan.source_clock.decision_date != request.decision_date
        or state.plan.source_clock.decision_cutoff.isoformat() != request.decision_cutoff
        or state.plan.to_dict().get("method_contracts_sha256") != request.method_contracts_sha256
        or len(cohort.declared_stock_codes) != request.declared_count
        or len(cohort.included_stock_codes) != request.included_count
        or len(cohort.excluded_stock_codes) != request.excluded_count
        or state.counts.declared_count != request.declared_count
        or state.counts.included_count != request.included_count
        or state.counts.excluded_count != request.excluded_count
        or state.receipt.status != request.technical_receipt_status
        or state.counts.processed_count + state.counts.pending_count
        != state.counts.included_count
    ):
        _fail("technical_ma_alignment_store_source_mismatch")


def _validate_query_source_request_v1(
    request: DailyMarketTechnicalMaAlignmentSourceRequestV1,
    query: DailyMarketTechnicalUniverseV4Query,
) -> None:
    if (
        query.store_output_root != request.technical_store_output_root
        or query.generation_identity_sha256 != request.generation_identity_sha256
        or query.plan_identity_sha256 != request.plan_identity_sha256
        or query.plan_sha256 != request.plan_sha256
        or query.receipt_identity_sha256 != request.receipt_identity_sha256
        or query.receipt_sha256 != request.receipt_sha256
        or query.cohort_identity_sha256 != request.cohort_identity_sha256
        or query.source_clock_identity_sha256 != request.source_clock_identity_sha256
        or query.method_contracts_sha256 != request.method_contracts_sha256
        or query.decision_date != request.decision_date
        or query.declared_count != request.declared_count
        or query.included_count != request.included_count
        or query.excluded_count != request.excluded_count
    ):
        _fail("technical_ma_alignment_query_source_scope_mismatch")


def _validate_collector_observations_v1(
    observations: Sequence[_ParentProjectionObservationV1],
    state: object,
) -> tuple[_ParentProjectionObservationV1, ...]:
    from app_module.daily_market_technical_universe_v4_store import DailyMarketTechnicalUniverseV4VerifiedState

    if type(state) is not DailyMarketTechnicalUniverseV4VerifiedState:
        _fail("technical_ma_alignment_store_state_invalid")
    references = state.segment_parent_references
    if tuple(item.segment_index for item in observations) != tuple(index for index, _ in references):
        _fail("technical_ma_alignment_parent_callback_coverage_mismatch")
    finalized: list[_ParentProjectionObservationV1] = []
    for observation, (segment_index, reference) in zip(observations, references):
        expected_segment = state.plan.segment_cohort(segment_index)
        if (
            observation.segment_index != segment_index
            or observation.parent_root is not None
            or not isinstance(reference.parent_root, str)
            or not Path(reference.parent_root).is_absolute()
            or observation.parent_plan_identity_sha256 != reference.parent_plan_identity_sha256
            or observation.parent_plan_sha256 != reference.parent_plan_sha256
            or observation.parent_receipt_identity_sha256 != reference.parent_receipt_identity_sha256
            or observation.parent_receipt_sha256 != reference.parent_receipt_sha256
            or observation.cohort_identity_sha256 != expected_segment.cohort_identity_sha256
            or observation.included_stock_codes != expected_segment.included_stock_codes
        ):
            _fail("technical_ma_alignment_parent_reference_mismatch")
        # StoreReader 已從此 exact reference root 讀取相符 plan/receipt；僅在
        # reference 與 callback 的各項 identity/bytes/cohort pins 相符後，
        # 才將此已核 parent capture root 補入 session identity。
        finalized.append(_ParentProjectionObservationV1(
            segment_index=observation.segment_index,
            parent_root=reference.parent_root,
            snapshot_repository_root=observation.snapshot_repository_root,
            parent_plan_identity_sha256=observation.parent_plan_identity_sha256,
            parent_plan_sha256=observation.parent_plan_sha256,
            parent_receipt_identity_sha256=observation.parent_receipt_identity_sha256,
            parent_receipt_sha256=observation.parent_receipt_sha256,
            cohort_identity_sha256=observation.cohort_identity_sha256,
            included_stock_codes=observation.included_stock_codes,
        ))
    return tuple(finalized)


def _project_verified_snapshot_entry_v1(
    segment_index: int,
    evidence: DailyMarketTechnicalMaAlignmentEvidenceV1,
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    parent_row: DailyMarketTechnicalParentV4Row,
    request: DailyMarketTechnicalMaAlignmentSourceRequestV1,
) -> DailyMarketTechnicalMaAlignmentCompactEntryV1:
    if (
        evidence.stock_code != snapshot.stock_code
        or evidence.decision_date != request.decision_date
        or evidence.snapshot_identity_sha256 != snapshot.snapshot_identity_sha256
        or evidence.source_identity != snapshot.source_identity
        or evidence.source_clock_sha256 != request.source_clock_identity_sha256
        or snapshot.method_contracts_sha256 != request.method_contracts_sha256
        or tuple(item.key for item in parent_row.rules) != tuple(
            item.key for item in snapshot.rules
        )
    ):
        _fail("technical_ma_alignment_collector_projection_pin_mismatch")
    facts = tuple(
        DailyMarketTechnicalMaAlignmentRuleFactV1(
            key=item.key,
            state=cast(MaStateV1, item.state),
            numerator=None if item.numerator is None else str(item.numerator),
            denominator=None if item.denominator is None else str(item.denominator),
            ratio=None if item.ratio is None else str(item.ratio),
        )
        for item in parent_row.rules
    )
    entry = DailyMarketTechnicalMaAlignmentCompactEntryV1(
        stock_code=evidence.stock_code,
        segment_index=segment_index,
        decision_date=evidence.decision_date,
        latest_feature_date=parent_row.latest_feature_date,
        raw_row_count=parent_row.raw_row_count,
        observed_prefix_contiguous=parent_row.observed_prefix_contiguous,
        source_identity=parent_row.source_identity,
        snapshot_identity_sha256=parent_row.snapshot_identity_sha256,
        raw_source_window_fingerprint_sha256=evidence.raw_source_window_fingerprint_sha256,
        evidence_identity_sha256=evidence.evidence_identity_sha256,
        source_clock_identity_sha256=evidence.source_clock_sha256,
        feature_date=evidence.feature_date,
        ma_state=evidence.state,
        ma_reason_codes=evidence.reason_codes,
        warmup_observed_sessions=evidence.warmup_observed_sessions,
        warmup_contiguous=evidence.warmup_contiguous,
        base_rule_facts=facts,
    )
    entry.to_dict()
    return entry


@dataclass(frozen=True, slots=True)
class _MaAlignmentResultAnchorV1:
    result_identity_sha256: str
    ordered_codes_sha256: str
    counts_sha256: str
    read_session: object = field(repr=False, compare=False)
    query: object = field(repr=False, compare=False)
    selection: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class _MaAlignmentPageAnchorV1:
    page_identity_sha256: str
    result_identity_sha256: str
    entries_sha256: str
    parent_rows_sha256: str
    result: object = field(repr=False, compare=False)
    materialization: object = field(repr=False, compare=False)


def _counts_json(counts: tuple[tuple[str, int], ...]) -> list[dict[str, object]]:
    return [{"name": key, "value": value} for key, value in counts]


def _ma_result_identity_v1(
    *,
    query: DailyMarketTechnicalMaAlignmentQueryV1,
    read_session_identity_sha256: str,
    selection_identity_sha256: str,
    ordered_stock_codes: tuple[str, ...],
    counts: tuple[tuple[str, int], ...],
) -> str:
    return _sha256_json({
        "schema": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_ISSUED_RESULT_V1_SCHEMA,
        "query_json": query.to_json(),
        "query_identity_sha256": query.query_identity_sha256,
        "read_session_identity_sha256": read_session_identity_sha256,
        "index_identity_sha256": query.ma_index_identity_sha256,
        "selection_identity_sha256": selection_identity_sha256,
        "ordered_stock_codes_sha256": _sha256_json(list(ordered_stock_codes)),
        "matching_count": len(ordered_stock_codes),
        "counts": _counts_json(counts),
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    })


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaAlignmentReadResultV1:
    """一次已核 source session 的完整全域 MA filter/sort 結果；不含完整列物件。"""

    query_json: str
    query_identity_sha256: str
    read_session_identity_sha256: str
    index_identity_sha256: str
    selection_identity_sha256: str
    ordered_stock_codes: tuple[str, ...]
    counts: tuple[tuple[str, int], ...]
    matching_count: int
    page_count: int
    result_identity_sha256: str
    source_available_at: None
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]
    _read_session: object = field(repr=False, compare=False)
    _query: DailyMarketTechnicalMaAlignmentQueryV1 = field(repr=False, compare=False)
    _selection: object = field(repr=False, compare=False)
    _anchor: _MaAlignmentResultAnchorV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _ISSUED_RESULT_SEAL
            or type(self._anchor) is not _MaAlignmentResultAnchorV1
            or self._anchor.read_session is not self._read_session
            or self._anchor.query is not self._query
            or self._anchor.selection is not self._selection
            or self._anchor.result_identity_sha256 != self.result_identity_sha256
            or self._anchor.ordered_codes_sha256 != _sha256_json(list(self.ordered_stock_codes))
            or self._anchor.counts_sha256 != _sha256_json(_counts_json(self.counts))
            or self.query_json != self._query.to_json()
            or self.query_identity_sha256 != self._query.query_identity_sha256
            or self.index_identity_sha256 != self._query.ma_index_identity_sha256
            or self.read_session_identity_sha256
            != cast(DailyMarketTechnicalMaAlignmentReadSessionV1, self._read_session).read_session_identity_sha256
            or self.selection_identity_sha256
            != cast(Any, self._selection).selection_identity_sha256
            or self.matching_count != len(self.ordered_stock_codes)
            or len(set(self.ordered_stock_codes)) != len(self.ordered_stock_codes)
            or type(self.matching_count) is not int
            or type(self.page_count) is not int
            or self.page_count != (self.matching_count + self._query.page_size - 1) // self._query.page_size
            or self.source_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
            or _ma_result_identity_v1(
                query=self._query,
                read_session_identity_sha256=self.read_session_identity_sha256,
                selection_identity_sha256=self.selection_identity_sha256,
                ordered_stock_codes=self.ordered_stock_codes,
                counts=self.counts,
            ) != self.result_identity_sha256
        ):
            _fail("technical_ma_alignment_read_result_invalid")

    @property
    def reader_issued(self) -> Literal[True]:
        return True

    @property
    def query(self) -> DailyMarketTechnicalMaAlignmentQueryV1:
        return self._query

    def to_dict(self) -> dict[str, object]:
        self._validate_anchor()
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_ISSUED_RESULT_V1_SCHEMA,
            "query_json": self.query_json,
            "query_identity_sha256": self.query_identity_sha256,
            "read_session_identity_sha256": self.read_session_identity_sha256,
            "index_identity_sha256": self.index_identity_sha256,
            "selection_identity_sha256": self.selection_identity_sha256,
            "ordered_stock_codes": list(self.ordered_stock_codes),
            "ordered_stock_codes_sha256": _sha256_json(list(self.ordered_stock_codes)),
            "counts": _counts_json(self.counts),
            "matching_count": self.matching_count,
            "page_count": self.page_count,
            "result_identity_sha256": self.result_identity_sha256,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }

    def read_page(
        self,
        page_index: int | None = None,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalMaAlignmentReadPageV1:
        self._validate_anchor()
        _strict_cancel_check(cancel_callback)
        selected_page_index = self._query.page_index if page_index is None else page_index
        if (
            type(selected_page_index) is not int
            or not 0 <= selected_page_index <= DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_PAGE_INDEX_V1
        ):
            _fail("technical_ma_alignment_issued_page_index_invalid")
        start = selected_page_index * self._query.page_size
        page_codes = self.ordered_stock_codes[start : start + self._query.page_size]
        session = cast(DailyMarketTechnicalMaAlignmentReadSessionV1, self._read_session)
        session._validate_session_anchor()
        p01_session = cast(Any, session._p01_session)
        materialization = p01_session.materialize_selected_stock_codes(
            self._selection,
            explicit_stock_codes=page_codes,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
        from app_module.daily_market_technical_universe_v4_query import (
            DailyMarketTechnicalUniverseV4SelectedRows,
        )

        if type(materialization) is not DailyMarketTechnicalUniverseV4SelectedRows:
            _fail("technical_ma_alignment_page_materialization_invalid")
        if (
            materialization.requested_stock_codes != page_codes
            or materialization.read_session_identity_sha256 != p01_session.read_session_identity_sha256
            or materialization.selection_identity_sha256 != cast(Any, self._selection).selection_identity_sha256
        ):
            _fail("technical_ma_alignment_page_materialization_pin_mismatch")
        index = cast(DailyMarketTechnicalMaAlignmentCompactIndexV1, session._index)
        entry_by_code = {item.stock_code: item for item in index.entries}
        entries = tuple(entry_by_code[code] for code in page_codes if code in entry_by_code)
        rows = materialization.rows
        if (
            tuple(item.stock_code for item in entries) != page_codes
            or tuple(row.stock_code for row in rows) != page_codes
            or len(entries) != len(rows)
            or any(not _parent_row_matches_ma_entry_v1(row, entry) for row, entry in zip(rows, entries))
        ):
            _fail("technical_ma_alignment_page_row_materialization_mismatch")
        _strict_cancel_check(cancel_callback)
        page = _issue_ma_alignment_read_page_v1(
            result=self,
            page_index=selected_page_index,
            entries=entries,
            parent_rows=rows,
            materialization=materialization,
        )
        _strict_cancel_check(cancel_callback)
        return page

    def _validate_anchor(self) -> None:
        if (
            self._seal is not _ISSUED_RESULT_SEAL
            or type(self._anchor) is not _MaAlignmentResultAnchorV1
            or self._anchor.read_session is not self._read_session
            or self._anchor.query is not self._query
            or self._anchor.selection is not self._selection
            or self._anchor.result_identity_sha256 != self.result_identity_sha256
            or self._anchor.ordered_codes_sha256 != _sha256_json(list(self.ordered_stock_codes))
            or self._anchor.counts_sha256 != _sha256_json(_counts_json(self.counts))
            or self.query_json != self._query.to_json()
            or self.query_identity_sha256 != self._query.query_identity_sha256
            or self.index_identity_sha256 != self._query.ma_index_identity_sha256
            or self.read_session_identity_sha256
            != cast(DailyMarketTechnicalMaAlignmentReadSessionV1, self._read_session).read_session_identity_sha256
            or self.selection_identity_sha256
            != cast(Any, self._selection).selection_identity_sha256
            or _ma_result_identity_v1(
                query=self._query,
                read_session_identity_sha256=self.read_session_identity_sha256,
                selection_identity_sha256=self.selection_identity_sha256,
                ordered_stock_codes=self.ordered_stock_codes,
                counts=self.counts,
            ) != self._anchor.result_identity_sha256
        ):
            _fail("technical_ma_alignment_read_result_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalMaAlignmentReadPageV1:
    """只包含單頁 compact MA facts 與同次核對的 P01 parent rows。"""

    result_identity_sha256: str
    query_identity_sha256: str
    read_session_identity_sha256: str
    selection_identity_sha256: str
    page_index: int
    page_size: int
    matching_count: int
    page_count: int
    counts: tuple[tuple[str, int], ...]
    entries: tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, ...]
    parent_rows: tuple[Any, ...]
    page_identity_sha256: str
    source_available_at: None
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]
    _anchor: _MaAlignmentPageAnchorV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _ISSUED_PAGE_SEAL
            or type(self._anchor) is not _MaAlignmentPageAnchorV1
            or self._anchor.page_identity_sha256 != self.page_identity_sha256
            or self._anchor.entries_sha256 != _sha256_json([item.to_dict() for item in self.entries])
            or self._anchor.parent_rows_sha256 != _sha256_json([row.to_dict() for row in self.parent_rows])
            or self._anchor.result_identity_sha256 != self.result_identity_sha256
            or len(self.entries) != len(self.parent_rows)
            or len(self.entries) > DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_PAGE_SIZE_V1
            or any(not _parent_row_matches_ma_entry_v1(row, entry) for row, entry in zip(self.parent_rows, self.entries))
            or self.source_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
            or _ma_page_identity_v1(
                result_identity_sha256=self.result_identity_sha256,
                query_identity_sha256=self.query_identity_sha256,
                read_session_identity_sha256=self.read_session_identity_sha256,
                selection_identity_sha256=self.selection_identity_sha256,
                page_index=self.page_index,
                page_size=self.page_size,
                matching_count=self.matching_count,
                page_count=self.page_count,
                counts=self.counts,
                entries=self.entries,
                parent_rows=self.parent_rows,
                materialization_identity_sha256=cast(Any, self._anchor.materialization).materialization_identity_sha256,
            ) != self.page_identity_sha256
        ):
            _fail("technical_ma_alignment_read_page_invalid")

    @property
    def reader_issued(self) -> Literal[True]:
        return True

    def to_dict(self) -> dict[str, object]:
        self._validate_anchor()
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_ISSUED_PAGE_V1_SCHEMA,
            "result_identity_sha256": self.result_identity_sha256,
            "query_identity_sha256": self.query_identity_sha256,
            "read_session_identity_sha256": self.read_session_identity_sha256,
            "selection_identity_sha256": self.selection_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
            "matching_count": self.matching_count,
            "page_count": self.page_count,
            "counts": _counts_json(self.counts),
            "entries": [item.to_dict() for item in self.entries],
            "parent_rows": [row.to_dict() for row in self.parent_rows],
            "materialization_identity_sha256": cast(Any, self._anchor.materialization).materialization_identity_sha256,
            "page_identity_sha256": self.page_identity_sha256,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }

    def _validate_anchor(self) -> None:
        result = self._anchor.result
        materialization = self._anchor.materialization
        from app_module.daily_market_technical_universe_v4_query import (
            DailyMarketTechnicalUniverseV4ReadSession,
            DailyMarketTechnicalUniverseV4SelectedRows,
        )

        if (
            type(result) is not DailyMarketTechnicalMaAlignmentReadResultV1
            or type(materialization) is not DailyMarketTechnicalUniverseV4SelectedRows
        ):
            _fail("technical_ma_alignment_read_page_invalid")
        issued_session = cast(DailyMarketTechnicalMaAlignmentReadSessionV1, result._read_session)
        if type(issued_session) is not DailyMarketTechnicalMaAlignmentReadSessionV1:
            _fail("technical_ma_alignment_read_page_invalid")
        p01_session = cast(DailyMarketTechnicalUniverseV4ReadSession, issued_session._p01_session)
        if type(p01_session) is not DailyMarketTechnicalUniverseV4ReadSession:
            _fail("technical_ma_alignment_read_page_invalid")

        expected_entries = tuple(
            result.ordered_stock_codes[
                self.page_index * self.page_size : self.page_index * self.page_size + self.page_size
            ]
        ) if isinstance(result, DailyMarketTechnicalMaAlignmentReadResultV1) else ()
        if (
            self._seal is not _ISSUED_PAGE_SEAL
            or type(self._anchor) is not _MaAlignmentPageAnchorV1
            or type(result) is not DailyMarketTechnicalMaAlignmentReadResultV1
            or type(materialization) is not DailyMarketTechnicalUniverseV4SelectedRows
            or result.result_identity_sha256 != self.result_identity_sha256
            or self._anchor.result_identity_sha256 != self.result_identity_sha256
            or result.query_identity_sha256 != self.query_identity_sha256
            or result.read_session_identity_sha256 != self.read_session_identity_sha256
            or result.selection_identity_sha256 != self.selection_identity_sha256
            or result.counts != self.counts
            or result.matching_count != self.matching_count
            or result.page_count != self.page_count
            or result.query.page_size != self.page_size
            or not 0 <= self.page_index <= DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_PAGE_INDEX_V1
            or tuple(item.stock_code for item in self.entries) != expected_entries
            or materialization.requested_stock_codes != expected_entries
            or materialization.read_session_identity_sha256
            != p01_session.read_session_identity_sha256
            or materialization.selection_identity_sha256
            != cast(Any, result._selection).selection_identity_sha256
            or self._anchor.page_identity_sha256 != self.page_identity_sha256
            or self._anchor.entries_sha256 != _sha256_json([item.to_dict() for item in self.entries])
            or self._anchor.parent_rows_sha256 != _sha256_json([row.to_dict() for row in self.parent_rows])
            or _ma_page_identity_v1(
                result_identity_sha256=self.result_identity_sha256,
                query_identity_sha256=self.query_identity_sha256,
                read_session_identity_sha256=self.read_session_identity_sha256,
                selection_identity_sha256=self.selection_identity_sha256,
                page_index=self.page_index,
                page_size=self.page_size,
                matching_count=self.matching_count,
                page_count=self.page_count,
                counts=self.counts,
                entries=self.entries,
                parent_rows=self.parent_rows,
                materialization_identity_sha256=materialization.materialization_identity_sha256,
            ) != self.page_identity_sha256
        ):
            _fail("technical_ma_alignment_read_page_invalid")


def _ma_page_identity_v1(
    *,
    result_identity_sha256: str,
    query_identity_sha256: str,
    read_session_identity_sha256: str,
    selection_identity_sha256: str,
    page_index: int,
    page_size: int,
    matching_count: int,
    page_count: int,
    counts: tuple[tuple[str, int], ...],
    entries: tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, ...],
    parent_rows: tuple[Any, ...],
    materialization_identity_sha256: str,
) -> str:
    return _sha256_json({
        "schema": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_ISSUED_PAGE_V1_SCHEMA,
        "result_identity_sha256": result_identity_sha256,
        "query_identity_sha256": query_identity_sha256,
        "read_session_identity_sha256": read_session_identity_sha256,
        "selection_identity_sha256": selection_identity_sha256,
        "page_index": page_index,
        "page_size": page_size,
        "matching_count": matching_count,
        "page_count": page_count,
        "counts": _counts_json(counts),
        "entries": [item.to_dict() for item in entries],
        "parent_rows": [row.to_dict() for row in parent_rows],
        "materialization_identity_sha256": materialization_identity_sha256,
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    })


def _issue_ma_alignment_read_page_v1(
    *,
    result: DailyMarketTechnicalMaAlignmentReadResultV1,
    page_index: int,
    entries: tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, ...],
    parent_rows: tuple[Any, ...],
    materialization: object,
) -> DailyMarketTechnicalMaAlignmentReadPageV1:
    identity = _ma_page_identity_v1(
        result_identity_sha256=result.result_identity_sha256,
        query_identity_sha256=result.query_identity_sha256,
        read_session_identity_sha256=result.read_session_identity_sha256,
        selection_identity_sha256=result.selection_identity_sha256,
        page_index=page_index,
        page_size=result.query.page_size,
        matching_count=result.matching_count,
        page_count=result.page_count,
        counts=result.counts,
        entries=entries,
        parent_rows=parent_rows,
        materialization_identity_sha256=cast(Any, materialization).materialization_identity_sha256,
    )
    anchor = _MaAlignmentPageAnchorV1(
        page_identity_sha256=identity,
        result_identity_sha256=result.result_identity_sha256,
        entries_sha256=_sha256_json([item.to_dict() for item in entries]),
        parent_rows_sha256=_sha256_json([row.to_dict() for row in parent_rows]),
        result=result,
        materialization=materialization,
    )
    return DailyMarketTechnicalMaAlignmentReadPageV1(
        result_identity_sha256=result.result_identity_sha256,
        query_identity_sha256=result.query_identity_sha256,
        read_session_identity_sha256=result.read_session_identity_sha256,
        selection_identity_sha256=result.selection_identity_sha256,
        page_index=page_index,
        page_size=result.query.page_size,
        matching_count=result.matching_count,
        page_count=result.page_count,
        counts=result.counts,
        entries=entries,
        parent_rows=parent_rows,
        page_identity_sha256=identity,
        source_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
        _anchor=anchor,
        _seal=_ISSUED_PAGE_SEAL,
    )


def _issue_ma_alignment_read_result_v1(
    *,
    read_session: DailyMarketTechnicalMaAlignmentReadSessionV1,
    query: DailyMarketTechnicalMaAlignmentQueryV1,
    selection: object,
    ordered_entries: tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, ...],
    counts: tuple[tuple[str, int], ...],
) -> DailyMarketTechnicalMaAlignmentReadResultV1:
    ordered_codes = tuple(item.stock_code for item in ordered_entries)
    matching_count = len(ordered_codes)
    page_count = (matching_count + query.page_size - 1) // query.page_size
    identity = _ma_result_identity_v1(
        query=query,
        read_session_identity_sha256=read_session.read_session_identity_sha256,
        selection_identity_sha256=cast(Any, selection).selection_identity_sha256,
        ordered_stock_codes=ordered_codes,
        counts=counts,
    )
    anchor = _MaAlignmentResultAnchorV1(
        result_identity_sha256=identity,
        ordered_codes_sha256=_sha256_json(list(ordered_codes)),
        counts_sha256=_sha256_json(_counts_json(counts)),
        read_session=read_session,
        query=query,
        selection=selection,
    )
    return DailyMarketTechnicalMaAlignmentReadResultV1(
        query_json=query.to_json(),
        query_identity_sha256=query.query_identity_sha256,
        read_session_identity_sha256=read_session.read_session_identity_sha256,
        index_identity_sha256=query.ma_index_identity_sha256,
        selection_identity_sha256=cast(Any, selection).selection_identity_sha256,
        ordered_stock_codes=ordered_codes,
        counts=counts,
        matching_count=matching_count,
        page_count=page_count,
        result_identity_sha256=identity,
        source_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
        _read_session=read_session,
        _query=query,
        _selection=selection,
        _anchor=anchor,
        _seal=_ISSUED_RESULT_SEAL,
    )


def _parent_row_matches_ma_entry_v1(parent_row: object, entry: DailyMarketTechnicalMaAlignmentCompactEntryV1) -> bool:
    from app_module.daily_market_technical_parent_v4_query import DailyMarketTechnicalParentV4Row

    if type(parent_row) is not DailyMarketTechnicalParentV4Row:
        return False
    rules = tuple(parent_row.rules)
    return (
        parent_row.stock_code == entry.stock_code
        and parent_row.decision_date == entry.decision_date
        and parent_row.snapshot_identity_sha256 == entry.snapshot_identity_sha256
        and parent_row.source_identity == entry.source_identity
        and parent_row.raw_row_count == entry.raw_row_count
        and parent_row.observed_prefix_contiguous == entry.observed_prefix_contiguous
        and parent_row.latest_feature_date == entry.latest_feature_date
        and tuple(item.key for item in rules) == tuple(item.key for item in entry.base_rule_facts)
        and tuple(item.state for item in rules) == tuple(item.state for item in entry.base_rule_facts)
        and tuple(
            (None if item.numerator is None else str(item.numerator),
             None if item.denominator is None else str(item.denominator),
             None if item.ratio is None else str(item.ratio))
            for item in rules
        ) == tuple((item.numerator, item.denominator, item.ratio) for item in entry.base_rule_facts)
    )
