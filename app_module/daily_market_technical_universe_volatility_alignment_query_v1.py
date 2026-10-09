"""F06 波動原料的有界、未核資格 compact projection collector。

本模組只承接呼叫端提供的 typed snapshot 與同列 parent row，依已版本化的
BB30／ATR14-SMA leaf 產生 compact facts。它不開啟來源、不綁定 P01 builder，
也不發行 reader-qualified index、session、query 或 page。metadata/self-hash
與本模組的 collector 都不能代替 F17 exact source qualification。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import json
import re
from typing import TYPE_CHECKING, Literal, NoReturn, cast

from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1,
    DailyMarketTechnicalMaAlignmentSourceRequestV1,
)
from app_module.daily_market_technical_volatility_evidence_v1 import (
    ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
    ATR14_SMA_METHOD_ID_V1,
    ATR14_SMA_METHOD_VERSION_V1,
    BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
    BOLLINGER_BANDWIDTH_METHOD_ID_V1,
    BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
    DailyMarketTechnicalVolatilityEvidenceError,
    DailyMarketTechnicalVolatilityEvidenceV1,
    project_daily_market_technical_volatility_evidence_v1,
)

if TYPE_CHECKING:
    from app_module.daily_market_technical_feature_snapshot_v4 import (
        DailyMarketTechnicalFeatureSnapshotV4,
    )
    from app_module.daily_market_technical_parent_v4_query import (
        DailyMarketTechnicalParentV4Row,
    )


DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_SOURCE_REQUEST_V1_SCHEMA = (
    "daily-market-technical-universe-volatility-source-request.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_COMPACT_ENTRY_V1_SCHEMA = (
    "daily-market-technical-universe-volatility-compact-entry.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_UNQUALIFIED_INDEX_V1_SCHEMA = (
    "daily-market-technical-universe-volatility-unqualified-index.v1"
)

DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_STOCKS_V1 = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1
)
DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1 = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1
)
DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SOURCE_REQUEST_BYTES_V1 = 16 * 1024
# 最終 entry 包含完整 BB30 與 ATR14 日期/fingerprint 窗口及雙重 identity；16 KiB
# 可容納兩個合法窗口的完整證據，不把窗口縮短成小型 fixture 才能通過的大小。
DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_ENTRY_BYTES_V1 = 16 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_JSON_DEPTH_V1 = 32
DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SOURCE_TEXT_BYTES_V1 = 256
DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SEGMENT_INDEX_V1 = 100_000

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")


class DailyMarketTechnicalUniverseVolatilityQueryV1Error(ValueError):
    """F06 compact projection 的穩定拒絕碼。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalUniverseVolatilityQueryV1Error(code, message)


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    if depth > DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_JSON_DEPTH_V1:
        _fail("technical_volatility_projection_json_depth_limit")
    if isinstance(value, float):
        _fail("technical_volatility_projection_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                _fail("technical_volatility_projection_json_key_invalid")
            _reject_float_tree(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item, depth=depth + 1)


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
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise DailyMarketTechnicalUniverseVolatilityQueryV1Error(
            "technical_volatility_projection_json_invalid", str(exc)
        ) from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_sha(value: object, code: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return cast(str, value)


def _strict_cancel_check(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    try:
        cancelled = callback()
    except Exception as exc:
        raise DailyMarketTechnicalUniverseVolatilityQueryV1Error(
            "technical_volatility_projection_cancel_check_failed", str(exc)
        ) from exc
    if type(cancelled) is not bool:
        _fail("technical_volatility_projection_cancel_callback_invalid")
    if cancelled:
        _fail("technical_volatility_projection_cancelled")


def _check_source_text(value: object, code: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8"))
        > DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SOURCE_TEXT_BYTES_V1
    ):
        _fail(code)
    return cast(str, value)


def _validate_segment_index(segment_index: object) -> int:
    if (
        type(segment_index) is not int
        or not 0 <= segment_index < DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SEGMENT_INDEX_V1
    ):
        _fail("technical_volatility_collector_segment_index_invalid")
    return cast(int, segment_index)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseVolatilitySourceRequestV1:
    """明示保存來源的未核 request；兩種方法身份固定綁定。"""

    ma_source_request: DailyMarketTechnicalMaAlignmentSourceRequestV1 = field(
        repr=False, compare=False,
    )
    request_identity_sha256: str

    def __post_init__(self) -> None:
        self.to_dict()

    @classmethod
    def from_ma_source_request(
        cls,
        request: DailyMarketTechnicalMaAlignmentSourceRequestV1,
    ) -> DailyMarketTechnicalUniverseVolatilitySourceRequestV1:
        if type(request) is not DailyMarketTechnicalMaAlignmentSourceRequestV1:
            _fail("technical_volatility_source_request_ma_input_invalid")
        body: dict[str, object] = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_SOURCE_REQUEST_V1_SCHEMA,
            "verification_status": "metadata_unverified",
            "ma_source_request": request.to_dict(),
            "bandwidth_method": {
                "method_id": BOLLINGER_BANDWIDTH_METHOD_ID_V1,
                "method_version": BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
                "method_identity_sha256": BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
            },
            "atr14_sma_method": {
                "method_id": ATR14_SMA_METHOD_ID_V1,
                "method_version": ATR14_SMA_METHOD_VERSION_V1,
                "method_identity_sha256": ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
            },
            "decision_date": request.decision_date.isoformat(),
            "decision_cutoff": request.decision_cutoff,
            "source_clock_identity_sha256": request.source_clock_identity_sha256,
            "declared_count": request.declared_count,
            "included_count": request.included_count,
            "excluded_count": request.excluded_count,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }
        encoded = _canonical_json_bytes(body)
        if len(encoded) > DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SOURCE_REQUEST_BYTES_V1:
            _fail("technical_volatility_source_request_byte_limit")
        result = cls(request, hashlib.sha256(encoded).hexdigest())
        result.to_dict()
        return result

    def _body(self) -> dict[str, object]:
        if type(self.ma_source_request) is not DailyMarketTechnicalMaAlignmentSourceRequestV1:
            _fail("technical_volatility_source_request_ma_input_invalid")
        request = self.ma_source_request
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_SOURCE_REQUEST_V1_SCHEMA,
            "verification_status": "metadata_unverified",
            "ma_source_request": request.to_dict(),
            "bandwidth_method": {
                "method_id": BOLLINGER_BANDWIDTH_METHOD_ID_V1,
                "method_version": BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
                "method_identity_sha256": BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
            },
            "atr14_sma_method": {
                "method_id": ATR14_SMA_METHOD_ID_V1,
                "method_version": ATR14_SMA_METHOD_VERSION_V1,
                "method_identity_sha256": ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
            },
            "decision_date": request.decision_date.isoformat(),
            "decision_cutoff": request.decision_cutoff,
            "source_clock_identity_sha256": request.source_clock_identity_sha256,
            "declared_count": request.declared_count,
            "included_count": request.included_count,
            "excluded_count": request.excluded_count,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }

    def to_dict(self) -> dict[str, object]:
        body = self._body()
        encoded = _canonical_json_bytes(body)
        identity = hashlib.sha256(encoded).hexdigest()
        if identity != _require_sha(
            self.request_identity_sha256,
            "technical_volatility_source_request_identity_invalid",
        ):
            _fail("technical_volatility_source_request_identity_mismatch")
        payload = {**body, "request_identity_sha256": identity}
        if len(_canonical_json_bytes(payload)) > DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SOURCE_REQUEST_BYTES_V1:
            _fail("technical_volatility_source_request_byte_limit")
        return payload


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseVolatilityCompactEntryV1:
    """包含兩個完整窗口的未核資格單股 compact entry。"""

    segment_index: int
    stock_code: str
    decision_date: date
    decision_cutoff: datetime
    source_identity: str
    source_clock_sha256: str
    source_pin_sha256: str
    snapshot_identity_sha256: str
    parent_row_identity_sha256: str
    raw_source_window_fingerprint_sha256: str
    source_window_fingerprint_sha256: str
    evidence: DailyMarketTechnicalVolatilityEvidenceV1 = field(repr=False, compare=False)
    compact_identity_sha256: str

    def __post_init__(self) -> None:
        self.to_dict()

    @classmethod
    def from_unqualified_evidence(
        cls,
        segment_index: int,
        evidence: DailyMarketTechnicalVolatilityEvidenceV1,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> DailyMarketTechnicalUniverseVolatilityCompactEntryV1:
        from app_module.daily_market_technical_parent_v4_query import (
            DailyMarketTechnicalParentV4Row,
        )

        if type(evidence) is not DailyMarketTechnicalVolatilityEvidenceV1:
            _fail("technical_volatility_compact_evidence_type_invalid")
        if type(parent_row) is not DailyMarketTechnicalParentV4Row:
            _fail("technical_volatility_compact_parent_row_type_invalid")
        if (
            type(segment_index) is not int
            or not 0 <= segment_index < DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SEGMENT_INDEX_V1
        ):
            _fail("technical_volatility_compact_segment_invalid")
        try:
            evidence_payload = evidence.to_dict()
            row_payload = parent_row.to_dict()
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise DailyMarketTechnicalUniverseVolatilityQueryV1Error(
                "technical_volatility_compact_input_invalid", str(exc)
            ) from exc
        availability = evidence_payload.get("availability")
        qualification = evidence_payload.get("qualification")
        if (
            parent_row.stock_code != evidence.stock_code
            or parent_row.decision_date != evidence.decision_date
            or parent_row.snapshot_identity_sha256 != evidence.snapshot_identity_sha256
            or parent_row.source_identity != evidence.source_identity
            or parent_row.raw_row_count < 0
            or parent_row.observed_prefix_contiguous != evidence.observed_prefix_contiguous
            or not isinstance(availability, Mapping)
            or availability.get("source_available_at") is not None
            or availability.get("availability_status") != "unknown"
            or availability.get("historical_pit_eligible") is not False
            or not isinstance(qualification, Mapping)
            or qualification.get("reader_qualified") is not False
            or evidence.bandwidth.method_identity_sha256 != BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1
            or evidence.atr14_sma.method_identity_sha256 != ATR14_SMA_METHOD_IDENTITY_SHA256_V1
        ):
            _fail("technical_volatility_compact_snapshot_row_mismatch")
        parent_row_identity = _sha256_json(row_payload)
        evidence_json = evidence.to_dict()
        body: dict[str, object] = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_COMPACT_ENTRY_V1_SCHEMA,
            "verification_status": "projection_unqualified",
            "segment_index": segment_index,
            "stock_code": evidence.stock_code,
            "decision_date": evidence.decision_date.isoformat(),
            "decision_cutoff": evidence.decision_cutoff.isoformat(),
            "source_identity": evidence.source_identity,
            "source_clock_sha256": evidence.source_clock_sha256,
            "source_pin_sha256": evidence.source_pin_sha256,
            "snapshot_identity_sha256": evidence.snapshot_identity_sha256,
            "parent_row_identity_sha256": parent_row_identity,
            "raw_source_window_fingerprint_sha256": evidence.raw_source_window_fingerprint_sha256,
            "source_window_fingerprint_sha256": evidence.source_window_fingerprint_sha256,
            "evidence": evidence_json,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }
        identity = _sha256_json(body)
        return cls(
            segment_index=segment_index,
            stock_code=evidence.stock_code,
            decision_date=evidence.decision_date,
            decision_cutoff=evidence.decision_cutoff,
            source_identity=evidence.source_identity,
            source_clock_sha256=evidence.source_clock_sha256,
            source_pin_sha256=evidence.source_pin_sha256,
            snapshot_identity_sha256=evidence.snapshot_identity_sha256,
            parent_row_identity_sha256=parent_row_identity,
            raw_source_window_fingerprint_sha256=evidence.raw_source_window_fingerprint_sha256,
            source_window_fingerprint_sha256=evidence.source_window_fingerprint_sha256,
            evidence=evidence,
            compact_identity_sha256=identity,
        )

    def _body(self) -> dict[str, object]:
        if (
            type(self.segment_index) is not int
            or not 0 <= self.segment_index < DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SEGMENT_INDEX_V1
            or type(self.stock_code) is not str
            or _STOCK_CODE_RE.fullmatch(self.stock_code) is None
            or type(self.decision_date) is not date
            or type(self.decision_cutoff) is not datetime
            or self.decision_cutoff.utcoffset() is None
            or self.decision_cutoff.date() != self.decision_date
            or type(self.evidence) is not DailyMarketTechnicalVolatilityEvidenceV1
        ):
            _fail("technical_volatility_compact_entry_invalid")
        for name, value in (
            ("source_clock", self.source_clock_sha256),
            ("source_pin", self.source_pin_sha256),
            ("snapshot", self.snapshot_identity_sha256),
            ("parent_row", self.parent_row_identity_sha256),
            ("raw_window", self.raw_source_window_fingerprint_sha256),
            ("source_window", self.source_window_fingerprint_sha256),
        ):
            _require_sha(value, f"technical_volatility_compact_{name}_invalid")
        _check_source_text(self.source_identity, "technical_volatility_compact_source_identity_invalid")
        evidence_payload = self.evidence.to_dict()
        if (
            evidence_payload["stock_code"] != self.stock_code
            or evidence_payload["decision_date"] != self.decision_date.isoformat()
            or evidence_payload["decision_cutoff"] != self.decision_cutoff.isoformat()
            or evidence_payload["source_identity"] != self.source_identity
            or evidence_payload["source_clock_sha256"] != self.source_clock_sha256
            or evidence_payload["source_pin_sha256"] != self.source_pin_sha256
            or evidence_payload["snapshot_identity_sha256"] != self.snapshot_identity_sha256
            or evidence_payload["raw_source_window_fingerprint_sha256"]
            != self.raw_source_window_fingerprint_sha256
            or evidence_payload["source_window_fingerprint_sha256"]
            != self.source_window_fingerprint_sha256
        ):
            _fail("technical_volatility_compact_evidence_mismatch")
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_COMPACT_ENTRY_V1_SCHEMA,
            "verification_status": "projection_unqualified",
            "segment_index": self.segment_index,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "source_identity": self.source_identity,
            "source_clock_sha256": self.source_clock_sha256,
            "source_pin_sha256": self.source_pin_sha256,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "parent_row_identity_sha256": self.parent_row_identity_sha256,
            "raw_source_window_fingerprint_sha256": self.raw_source_window_fingerprint_sha256,
            "source_window_fingerprint_sha256": self.source_window_fingerprint_sha256,
            "evidence": evidence_payload,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }

    def to_dict(self) -> dict[str, object]:
        body = self._body()
        identity = hashlib.sha256(_canonical_json_bytes(body)).hexdigest()
        if identity != _require_sha(
            self.compact_identity_sha256,
            "technical_volatility_compact_identity_invalid",
        ):
            _fail("technical_volatility_compact_identity_mismatch")
        payload = {**body, "compact_identity_sha256": identity}
        if len(_canonical_json_bytes(payload)) > DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_ENTRY_BYTES_V1:
            _fail("technical_volatility_compact_entry_byte_limit")
        return payload


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseVolatilityUnqualifiedIndexV1:
    """明示未核資格的暫存索引；不能供 query/result/page 宣稱來源合格。"""

    source_request: DailyMarketTechnicalUniverseVolatilitySourceRequestV1 = field(
        repr=False, compare=False,
    )
    entries: tuple[DailyMarketTechnicalUniverseVolatilityCompactEntryV1, ...]
    completed_segment_count: int
    index_identity_sha256: str

    def __post_init__(self) -> None:
        self.to_dict()

    def _body(self) -> dict[str, object]:
        if type(self.source_request) is not DailyMarketTechnicalUniverseVolatilitySourceRequestV1:
            _fail("technical_volatility_index_source_request_invalid")
        if (
            type(self.entries) is not tuple
            or len(self.entries) > DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_STOCKS_V1
            or type(self.completed_segment_count) is not int
            or not 0 <= self.completed_segment_count <= DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SEGMENT_INDEX_V1
        ):
            _fail("technical_volatility_index_bounds_invalid")
        request_payload = self.source_request.to_dict()
        request = self.source_request.ma_source_request
        entries_payload: list[dict[str, object]] = []
        previous_segment = -1
        previous_code = ""
        seen: set[str] = set()
        for entry in self.entries:
            if type(entry) is not DailyMarketTechnicalUniverseVolatilityCompactEntryV1:
                _fail("technical_volatility_index_entry_type_invalid")
            payload = entry.to_dict()
            if entry.decision_date != request.decision_date:
                _fail("technical_volatility_index_entry_decision_date_mismatch")
            if entry.decision_cutoff.isoformat() != request.decision_cutoff:
                _fail("technical_volatility_index_entry_decision_cutoff_mismatch")
            if entry.source_clock_sha256 != request.source_clock_identity_sha256:
                _fail("technical_volatility_index_entry_source_clock_mismatch")
            if entry.segment_index < previous_segment:
                _fail("technical_volatility_index_order_invalid")
            if entry.segment_index != previous_segment:
                previous_segment = entry.segment_index
                previous_code = ""
            if entry.stock_code in seen or entry.stock_code <= previous_code:
                _fail("technical_volatility_index_stock_order_invalid")
            if entry.segment_index >= self.completed_segment_count:
                _fail("technical_volatility_index_segment_count_invalid")
            seen.add(entry.stock_code)
            previous_code = entry.stock_code
            entries_payload.append(payload)
        request_body = cast(dict[str, object], request_payload)
        if len(entries_payload) > cast(int, request_body["included_count"]):
            _fail("technical_volatility_index_population_limit")
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_UNQUALIFIED_INDEX_V1_SCHEMA,
            "verification_status": "projection_unqualified",
            "source_request": request_payload,
            "completed_segment_count": self.completed_segment_count,
            "collected_count": len(entries_payload),
            "entries": entries_payload,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
            "reader_qualified": False,
        }

    def to_dict(self) -> dict[str, object]:
        body = self._body()
        identity = hashlib.sha256(_canonical_json_bytes(body)).hexdigest()
        if identity != _require_sha(
            self.index_identity_sha256,
            "technical_volatility_index_identity_invalid",
        ):
            _fail("technical_volatility_index_identity_mismatch")
        payload = {**body, "index_identity_sha256": identity}
        if len(_canonical_json_bytes(payload)) > DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1:
            _fail("technical_volatility_index_byte_limit")
        return payload


@dataclass(slots=True)
class _ActiveSegmentV1:
    segment_index: int
    expected_codes: tuple[str, ...]
    expected_snapshots: tuple[object, ...] = field(repr=False)
    consumed_codes: list[str] = field(default_factory=list, repr=False)


class DailyMarketTechnicalVolatilityProjectionCollectorV1:
    """暫存未核 projection；任一失敗永久毒化且不能讀取 partial entries。"""

    qualification_status = "projection_unqualified"

    def __init__(
        self,
        source_request: DailyMarketTechnicalUniverseVolatilitySourceRequestV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
        max_stocks: int = DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_STOCKS_V1,
        max_index_bytes: int = DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1,
    ) -> None:
        if type(source_request) is not DailyMarketTechnicalUniverseVolatilitySourceRequestV1:
            _fail("technical_volatility_collector_source_request_invalid")
        source_request.to_dict()
        if (
            type(max_stocks) is not int
            or not 1 <= max_stocks <= DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_STOCKS_V1
            or type(max_index_bytes) is not int
            or not 1 <= max_index_bytes <= DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1
        ):
            _fail("technical_volatility_collector_budget_invalid")
        _strict_cancel_check(cancel_callback)
        self.source_request = source_request
        self.cancel_callback = cancel_callback
        self.max_stocks = max_stocks
        self.max_index_bytes = max_index_bytes
        self._entries: list[DailyMarketTechnicalUniverseVolatilityCompactEntryV1] = []
        self._seen_codes: set[str] = set()
        self._active_segment: _ActiveSegmentV1 | None = None
        self._next_segment_index = 0
        self._index_bytes = 0
        self._failed = False

    def _poison(self) -> None:
        self._failed = True
        self._active_segment = None

    @property
    def unqualified_entries(
        self,
    ) -> tuple[DailyMarketTechnicalUniverseVolatilityCompactEntryV1, ...]:
        if self._failed:
            _fail("technical_volatility_collector_failed")
        if self._active_segment is not None:
            _fail("technical_volatility_collector_segment_incomplete")
        return tuple(self._entries)

    @property
    def collected_count(self) -> int:
        if self._failed:
            _fail("technical_volatility_collector_failed")
        return len(self._entries)

    def begin_unqualified_segment(
        self,
        segment_index: int,
        snapshots: tuple[DailyMarketTechnicalFeatureSnapshotV4, ...],
    ) -> None:
        try:
            self._begin_unqualified_segment(segment_index, snapshots)
        except BaseException:
            self._poison()
            raise

    def _begin_unqualified_segment(
        self,
        segment_index: int,
        snapshots: tuple[DailyMarketTechnicalFeatureSnapshotV4, ...],
    ) -> None:
        from app_module.daily_market_technical_feature_snapshot_v4 import (
            DailyMarketTechnicalFeatureSnapshotV4,
        )

        _strict_cancel_check(self.cancel_callback)
        segment_index = _validate_segment_index(segment_index)
        if (
            self._failed
            or self._active_segment is not None
            or segment_index != self._next_segment_index
            or type(snapshots) is not tuple
            or len(snapshots) > self.max_stocks - len(self._entries)
        ):
            _fail("technical_volatility_collector_segment_order_invalid")
        _strict_cancel_check(self.cancel_callback)
        codes: list[str] = []
        for snapshot in snapshots:
            if type(snapshot) is not DailyMarketTechnicalFeatureSnapshotV4:
                _fail("technical_volatility_collector_snapshot_type_invalid")
            code = snapshot.stock_code
            if type(code) is not str or _STOCK_CODE_RE.fullmatch(code) is None:
                _fail("technical_volatility_collector_stock_code_invalid")
            codes.append(code)
        if (
            tuple(codes) != tuple(sorted(set(codes)))
            or any(code in self._seen_codes for code in codes)
            or len(self._entries) + len(codes) > self.source_request.ma_source_request.included_count
        ):
            _fail("technical_volatility_collector_segment_population_invalid")
        self._active_segment = _ActiveSegmentV1(
            segment_index=segment_index,
            expected_codes=tuple(codes),
            expected_snapshots=tuple(snapshots),
        )
        _strict_cancel_check(self.cancel_callback)

    def consume_unqualified_snapshot(
        self,
        segment_index: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        try:
            self._consume_unqualified_snapshot(segment_index, snapshot, parent_row)
        except BaseException:
            self._poison()
            raise

    def _consume_unqualified_snapshot(
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
        from app_module.daily_market_technical_universe_v4_store import (
            daily_market_technical_source_clock_v4_from_dict,
        )

        _strict_cancel_check(self.cancel_callback)
        segment_index = _validate_segment_index(segment_index)
        active = self._active_segment
        position = len(active.consumed_codes) if active is not None else -1
        if (
            self._failed
            or active is None
            or active.segment_index != segment_index
            or type(snapshot) is not DailyMarketTechnicalFeatureSnapshotV4
            or type(parent_row) is not DailyMarketTechnicalParentV4Row
            or position < 0
            or position >= len(active.expected_codes)
            or snapshot is not active.expected_snapshots[position]
            or snapshot.stock_code != active.expected_codes[position]
            or snapshot.stock_code in self._seen_codes
        ):
            _fail("technical_volatility_collector_snapshot_order_invalid")
        request = self.source_request.ma_source_request
        try:
            snapshot.to_dict()
            parent_payload = parent_row.to_dict()
            source_clock = daily_market_technical_source_clock_v4_from_dict(snapshot.source_clock)
        except Exception as exc:
            raise DailyMarketTechnicalUniverseVolatilityQueryV1Error(
                "technical_volatility_collector_snapshot_invalid", str(exc)
            ) from exc
        if (
            source_clock.identity_sha256 != request.source_clock_identity_sha256
            or source_clock.decision_date != request.decision_date
            or source_clock.decision_cutoff.isoformat() != request.decision_cutoff
            or snapshot.method_contracts_sha256 != request.method_contracts_sha256
            or snapshot.decision_date != request.decision_date
            or snapshot.decision_cutoff.isoformat() != request.decision_cutoff
            or parent_payload != _snapshot_parent_row(snapshot).to_dict()
        ):
            _fail("technical_volatility_collector_source_row_mismatch")
        _strict_cancel_check(self.cancel_callback)
        try:
            evidence = project_daily_market_technical_volatility_evidence_v1(snapshot)
        except DailyMarketTechnicalVolatilityEvidenceError as exc:
            raise DailyMarketTechnicalUniverseVolatilityQueryV1Error(
                "technical_volatility_collector_evidence_invalid", str(exc)
            ) from exc
        if (
            evidence.stock_code != snapshot.stock_code
            or evidence.decision_date != snapshot.decision_date
            or evidence.decision_cutoff != snapshot.decision_cutoff
            or evidence.source_clock_sha256 != snapshot.source_clock_sha256
            or evidence.source_pin_sha256 != snapshot.source_pin_sha256
            or evidence.snapshot_identity_sha256 != snapshot.snapshot_identity_sha256
            or evidence.source_identity != snapshot.source_identity
            or evidence.raw_source_window_fingerprint_sha256
            != snapshot.raw_source_window_fingerprint_sha256
            or evidence.source_window_fingerprint_sha256
            != snapshot.source_window_fingerprint_sha256
        ):
            _fail("technical_volatility_collector_evidence_snapshot_mismatch")
        entry = DailyMarketTechnicalUniverseVolatilityCompactEntryV1.from_unqualified_evidence(
            segment_index,
            evidence,
            parent_row,
        )
        encoded = _canonical_json_bytes(entry.to_dict())
        if len(encoded) > DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_ENTRY_BYTES_V1:
            _fail("technical_volatility_collector_entry_byte_limit")
        if (
            len(self._entries) >= self.max_stocks
            or len(self._entries) >= request.included_count
            or self._index_bytes + len(encoded) + 1 > self.max_index_bytes
        ):
            _fail("technical_volatility_collector_index_limit")
        _strict_cancel_check(self.cancel_callback)
        active.consumed_codes.append(snapshot.stock_code)
        self._seen_codes.add(snapshot.stock_code)
        self._entries.append(entry)
        self._index_bytes += len(encoded) + 1
        _strict_cancel_check(self.cancel_callback)

    def end_unqualified_segment(self, segment_index: int) -> None:
        try:
            self._end_unqualified_segment(segment_index)
        except BaseException:
            self._poison()
            raise

    def _end_unqualified_segment(self, segment_index: int) -> None:
        _strict_cancel_check(self.cancel_callback)
        segment_index = _validate_segment_index(segment_index)
        active = self._active_segment
        if (
            self._failed
            or active is None
            or active.segment_index != segment_index
            or tuple(active.consumed_codes) != active.expected_codes
        ):
            _fail("technical_volatility_collector_segment_incomplete")
        self._active_segment = None
        self._next_segment_index += 1
        _strict_cancel_check(self.cancel_callback)

    def unqualified_index(self) -> DailyMarketTechnicalUniverseVolatilityUnqualifiedIndexV1:
        try:
            _strict_cancel_check(self.cancel_callback)
            if self._failed:
                _fail("technical_volatility_collector_failed")
            if self._active_segment is not None:
                _fail("technical_volatility_collector_segment_incomplete")
            entries = tuple(self._entries)
            body: dict[str, object] = {
                "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_UNQUALIFIED_INDEX_V1_SCHEMA,
                "verification_status": "projection_unqualified",
                "source_request": self.source_request.to_dict(),
                "completed_segment_count": self._next_segment_index,
                "collected_count": len(entries),
                "entries": [entry.to_dict() for entry in entries],
                "source_available_at": None,
                "availability_status": "unknown",
                "historical_pit_eligible": False,
                "reader_qualified": False,
            }
            encoded = _canonical_json_bytes(body)
            if len(encoded) > self.max_index_bytes:
                _fail("technical_volatility_collector_index_limit")
            identity = hashlib.sha256(encoded).hexdigest()
            result = DailyMarketTechnicalUniverseVolatilityUnqualifiedIndexV1(
                source_request=self.source_request,
                entries=entries,
                completed_segment_count=self._next_segment_index,
                index_identity_sha256=identity,
            )
            final_payload = result.to_dict()
            if len(_canonical_json_bytes(final_payload)) > self.max_index_bytes:
                _fail("technical_volatility_collector_index_limit")
            _strict_cancel_check(self.cancel_callback)
            return result
        except BaseException:
            self._poison()
            raise


def _snapshot_parent_row(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
) -> DailyMarketTechnicalParentV4Row:
    from app_module.daily_market_technical_parent_v4_query import (
        DailyMarketTechnicalParentV4Row,
    )

    return DailyMarketTechnicalParentV4Row(
        stock_code=snapshot.stock_code,
        decision_date=snapshot.decision_date,
        snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        source_identity=snapshot.source_identity,
        raw_row_count=len(snapshot.rows),
        observed_prefix_contiguous=snapshot.observed_prefix_contiguous,
        latest_feature_date=(
            snapshot.current_session.feature_date if snapshot.current_session is not None else None
        ),
        rules=snapshot.rules,
    )
