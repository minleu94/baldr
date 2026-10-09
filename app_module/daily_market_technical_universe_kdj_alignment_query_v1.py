"""F03 KDJ compact projection 的未核資格骨架。

本模組只累積同次 parent callback 的有界 KDJ compact facts，並提供不可變有序
projection group。它不建立 qualified index/session/query/page；來源資格只能由
日後 F17 exact publication seam 在 MA 與 KDJ 均完成驗證後原子發行。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import re
from typing import TYPE_CHECKING, Literal, NoReturn, cast

from app_module.daily_market_technical_kdj_evidence_v1 import (
    KDJ_METHOD_IDENTITY_SHA256_V1,
    KDJ_METHOD_ID_V1,
    KDJ_METHOD_VERSION_V1,
    DailyMarketTechnicalKDJDayV1,
    DailyMarketTechnicalKDJEvidenceV1,
    DailyMarketTechnicalKDJError,
    project_daily_market_technical_kdj_evidence_v1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1,
    DailyMarketTechnicalMaAlignmentSourceRequestV1,
    DailyMarketTechnicalMaAlignmentVerifiedCollectorV1,
)

if TYPE_CHECKING:
    from app_module.daily_market_technical_feature_snapshot_v4 import (
        DailyMarketTechnicalFeatureSnapshotV4,
    )
    from app_module.daily_market_technical_parent_v4_query import (
        DailyMarketTechnicalParentV4Row,
    )
    from app_module.rule_research_technical_parent_capture_v4 import (
        DailyMarketTechnicalParentCaptureV4VerifiedRead,
    )


DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_SOURCE_REQUEST_V1_SCHEMA = (
    "daily-market-technical-universe-kdj-source-request.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_COMPACT_ENTRY_V1_SCHEMA = (
    "daily-market-technical-universe-kdj-compact-entry.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_PROJECTION_GROUP_V1_SCHEMA = (
    "daily-market-technical-universe-kdj-projection-group.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_STOCKS_V1 = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1
)
DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_INDEX_BYTES_V1 = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1
)
DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_ENTRY_BYTES_V1 = 4 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_SOURCE_REQUEST_BYTES_V1 = 16 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_SOURCE_ID_BYTES_V1 = 128
DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_SOURCE_IDENTITY_BYTES_V1 = 256
DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_REASON_CODES_V1 = 8
DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_REASON_CODE_BYTES_V1 = 96
DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_DECIMAL_TOKEN_BYTES_V1 = 96
DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_WINDOW_ROWS_V1 = 14

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")
_KDJ_STATES = frozenset({"match", "no_match", "unknown"})


class DailyMarketTechnicalUniverseKDJQueryV1Error(ValueError):
    """F03 KDJ compact projection 的穩定錯誤碼。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalUniverseKDJQueryV1Error(code, message)


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
        raise DailyMarketTechnicalUniverseKDJQueryV1Error(
            "technical_kdj_projection_json_invalid", str(exc)
        ) from exc


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    if depth > 32:
        _fail("technical_kdj_projection_json_depth_limit")
    if isinstance(value, float):
        _fail("technical_kdj_projection_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("technical_kdj_projection_json_invalid")
            _reject_float_tree(item, depth=depth + 1)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _reject_float_tree(item, depth=depth + 1)


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _strict_cancel_check(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    try:
        cancelled = callback()
    except Exception as exc:
        raise DailyMarketTechnicalUniverseKDJQueryV1Error(
            "technical_kdj_projection_cancel_check_failed", str(exc)
        ) from exc
    if type(cancelled) is not bool:
        _fail("technical_kdj_projection_cancel_callback_invalid")
    if cancelled:
        _fail("technical_kdj_projection_cancelled")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseKDJSourceRequestV1:
    """包住 MA/F17 同來源要求的 metadata-unverified KDJ request。"""

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
    ) -> DailyMarketTechnicalUniverseKDJSourceRequestV1:
        if type(request) is not DailyMarketTechnicalMaAlignmentSourceRequestV1:
            _fail("technical_kdj_source_request_ma_input_invalid")
        request_payload = request.to_dict()
        body: dict[str, object] = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_SOURCE_REQUEST_V1_SCHEMA,
            "verification_status": "metadata_unverified",
            "ma_source_request": request_payload,
            "kdj_method_id": KDJ_METHOD_ID_V1,
            "kdj_method_version": KDJ_METHOD_VERSION_V1,
            "kdj_method_identity_sha256": KDJ_METHOD_IDENTITY_SHA256_V1,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }
        result = cls(request, _sha256_json(body))
        result.to_dict()
        return result

    def _body(self) -> dict[str, object]:
        if type(self.ma_source_request) is not DailyMarketTechnicalMaAlignmentSourceRequestV1:
            _fail("technical_kdj_source_request_ma_input_invalid")
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_SOURCE_REQUEST_V1_SCHEMA,
            "verification_status": "metadata_unverified",
            "ma_source_request": self.ma_source_request.to_dict(),
            "kdj_method_id": KDJ_METHOD_ID_V1,
            "kdj_method_version": KDJ_METHOD_VERSION_V1,
            "kdj_method_identity_sha256": KDJ_METHOD_IDENTITY_SHA256_V1,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }

    def to_dict(self) -> dict[str, object]:
        body = self._body()
        encoded = _canonical_json_bytes(body)
        if len(encoded) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_SOURCE_REQUEST_BYTES_V1:
            _fail("technical_kdj_source_request_byte_limit")
        identity = hashlib.sha256(encoded).hexdigest()
        if identity != _require_sha(
            self.request_identity_sha256, "technical_kdj_source_request_identity_invalid"
        ):
            _fail("technical_kdj_source_request_identity_mismatch")
        payload = {**body, "request_identity_sha256": identity}
        if len(_canonical_json_bytes(payload)) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_SOURCE_REQUEST_BYTES_V1:
            _fail("technical_kdj_source_request_byte_limit")
        return payload


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseKDJCompactDayV1:
    """單日 KDJ 數值的緊湊 Decimal 表示。"""

    feature_date: date
    source_row_fingerprint_sha256: str
    rsv: Decimal
    k: Decimal
    d: Decimal
    j: Decimal

    def to_dict(self) -> dict[str, object]:
        if type(self.feature_date) is not date:
            _fail("technical_kdj_compact_day_date_invalid")
        _require_sha(
            self.source_row_fingerprint_sha256,
            "technical_kdj_compact_day_fingerprint_invalid",
        )
        values: dict[str, str] = {}
        for name, value in (("rsv", self.rsv), ("k", self.k), ("d", self.d), ("j", self.j)):
            if type(value) is not Decimal or not value.is_finite():
                _fail("technical_kdj_compact_decimal_invalid")
            text_value = str(value)
            if len(text_value.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_DECIMAL_TOKEN_BYTES_V1:
                _fail("technical_kdj_compact_decimal_limit")
            values[name] = text_value
        return {
            "feature_date": self.feature_date.isoformat(),
            "source_row_fingerprint_sha256": self.source_row_fingerprint_sha256,
            **values,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseKDJCompactEntryV1:
    """單股 KDJ compact evidence；hash 是內容追溯，不是來源資格。"""

    segment_index: int
    stock_code: str
    decision_date: date
    decision_cutoff: datetime
    source_id: str
    source_identity: str
    source_clock_sha256: str
    source_pin_sha256: str
    snapshot_identity_sha256: str
    raw_source_window_fingerprint_sha256: str
    window_identity_sha256: str
    evidence_identity_sha256: str
    state: Literal["match", "no_match", "unknown"]
    reason_codes: tuple[str, ...]
    previous: DailyMarketTechnicalUniverseKDJCompactDayV1 | None
    current: DailyMarketTechnicalUniverseKDJCompactDayV1 | None
    input_row_count: int
    warmup_observed_sessions: int
    warmup_contiguous: bool
    observed_prefix_contiguous: bool

    def __post_init__(self) -> None:
        self._payload_with_identity()

    @classmethod
    def from_unqualified_evidence(
        cls,
        segment_index: int,
        evidence: DailyMarketTechnicalKDJEvidenceV1,
    ) -> DailyMarketTechnicalUniverseKDJCompactEntryV1:
        if type(evidence) is not DailyMarketTechnicalKDJEvidenceV1:
            _fail("technical_kdj_compact_evidence_type_invalid")
        try:
            payload = evidence.to_dict()
        except DailyMarketTechnicalKDJError as exc:
            raise DailyMarketTechnicalUniverseKDJQueryV1Error(
                "technical_kdj_compact_evidence_invalid", str(exc)
            ) from exc
        input_dates = payload.get("input_feature_dates")
        input_fingerprints = payload.get("input_row_fingerprints_sha256")
        if (
            type(segment_index) is not int
            or segment_index < 0
            or not isinstance(input_dates, list)
            or not isinstance(input_fingerprints, list)
            or len(input_dates) != len(input_fingerprints)
            or len(input_dates) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_WINDOW_ROWS_V1
            or any(item is not None and not isinstance(item, str) for item in input_dates)
            or any(not isinstance(item, str) or _SHA256_RE.fullmatch(item) is None for item in input_fingerprints)
        ):
            _fail("technical_kdj_compact_window_invalid")
        if (
            not isinstance(evidence.stock_code, str)
            or _STOCK_CODE_RE.fullmatch(evidence.stock_code) is None
            or not isinstance(evidence.source_id, str)
            or not isinstance(evidence.source_identity, str)
            or len(evidence.source_id.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_SOURCE_ID_BYTES_V1
            or len(evidence.source_identity.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_SOURCE_IDENTITY_BYTES_V1
            or type(evidence.reason_codes) is not tuple
            or len(evidence.reason_codes) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_REASON_CODES_V1
            or any(
                not isinstance(reason, str)
                or not reason
                or len(reason.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_REASON_CODE_BYTES_V1
                for reason in evidence.reason_codes
            )
            or type(evidence.decision_date) is not date
            or type(evidence.decision_cutoff) is not datetime
            or evidence.decision_cutoff.utcoffset() is None
            or evidence.decision_cutoff.date() != evidence.decision_date
            or any(
                value is not None and type(value) is not DailyMarketTechnicalKDJDayV1
                for value in (evidence.previous, evidence.current)
            )
        ):
            _fail("technical_kdj_compact_evidence_bounds_invalid")
        for day in (evidence.previous, evidence.current):
            if day is not None and (
                type(day.feature_date) is not date or day.feature_date > evidence.decision_date
            ):
                _fail("technical_kdj_compact_evidence_bounds_invalid")
        source_clock = _require_sha(
            evidence.source_clock_sha256, "technical_kdj_compact_source_clock_invalid"
        )
        source_pin = _require_sha(evidence.source_pin_sha256, "technical_kdj_compact_source_pin_invalid")
        snapshot_identity = _require_sha(
            evidence.snapshot_identity_sha256, "technical_kdj_compact_snapshot_identity_invalid"
        )
        raw_window = _require_sha(
            evidence.raw_source_window_fingerprint_sha256,
            "technical_kdj_compact_raw_window_invalid",
        )
        evidence_identity = _require_sha(
            cast(object, payload.get("evidence_identity_sha256")),
            "technical_kdj_compact_evidence_identity_invalid",
        )
        window_identity = _sha256_json({
            "input_feature_dates": input_dates,
            "input_row_fingerprints_sha256": input_fingerprints,
        })
        return cls(
            segment_index=segment_index,
            stock_code=evidence.stock_code,
            decision_date=evidence.decision_date,
            decision_cutoff=evidence.decision_cutoff,
            source_id=evidence.source_id,
            source_identity=evidence.source_identity,
            source_clock_sha256=source_clock,
            source_pin_sha256=source_pin,
            snapshot_identity_sha256=snapshot_identity,
            raw_source_window_fingerprint_sha256=raw_window,
            window_identity_sha256=window_identity,
            evidence_identity_sha256=evidence_identity,
            state=cast(Literal["match", "no_match", "unknown"], evidence.state),
            reason_codes=tuple(evidence.reason_codes),
            previous=_compact_day(evidence.previous),
            current=_compact_day(evidence.current),
            input_row_count=len(input_dates),
            warmup_observed_sessions=evidence.warmup_observed_sessions,
            warmup_contiguous=evidence.warmup_contiguous,
            observed_prefix_contiguous=evidence.observed_prefix_contiguous,
        )

    def _body(self) -> dict[str, object]:
        if (
            type(self.segment_index) is not int
            or self.segment_index < 0
            or not isinstance(self.stock_code, str)
            or _STOCK_CODE_RE.fullmatch(self.stock_code) is None
            or not isinstance(self.state, str)
            or self.state not in _KDJ_STATES
            or type(self.decision_date) is not date
            or type(self.decision_cutoff) is not datetime
            or self.decision_cutoff.utcoffset() is None
            or self.decision_cutoff.date() != self.decision_date
            or type(self.reason_codes) is not tuple
            or len(self.reason_codes) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_REASON_CODES_V1
            or type(self.input_row_count) is not int
            or self.input_row_count < 0
            or self.input_row_count > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_WINDOW_ROWS_V1
            or type(self.warmup_observed_sessions) is not int
            or not 0 <= self.warmup_observed_sessions <= 14
            or type(self.warmup_contiguous) is not bool
            or type(self.observed_prefix_contiguous) is not bool
            or self.decision_cutoff.utcoffset() is None
            or any(
                not isinstance(reason, str)
                or not reason
                or len(reason.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_REASON_CODE_BYTES_V1
                for reason in self.reason_codes
            )
        ):
            _fail("technical_kdj_compact_entry_invalid")
        if self.state == "unknown":
            if not self.reason_codes or self.previous is not None or self.current is not None:
                _fail("technical_kdj_compact_unknown_invalid")
        elif self.reason_codes or self.previous is None or self.current is None:
            _fail("technical_kdj_compact_known_invalid")
        if any(
            value is not None and type(value) is not DailyMarketTechnicalUniverseKDJCompactDayV1
            for value in (self.previous, self.current)
        ):
            _fail("technical_kdj_compact_day_type_invalid")
        if self.previous is not None and self.current is not None:
            if not self.previous.feature_date < self.current.feature_date:
                _fail("technical_kdj_compact_observation_order_invalid")
            if self.current.feature_date > self.decision_date:
                _fail("technical_kdj_compact_future_observation_rejected")
        for name, value in (
            ("source_clock", self.source_clock_sha256),
            ("source_pin", self.source_pin_sha256),
            ("snapshot", self.snapshot_identity_sha256),
            ("raw_window", self.raw_source_window_fingerprint_sha256),
            ("window", self.window_identity_sha256),
            ("evidence", self.evidence_identity_sha256),
        ):
            _require_sha(value, f"technical_kdj_compact_{name}_identity_invalid")
        if (
            not isinstance(self.source_id, str)
            or not isinstance(self.source_identity, str)
            or len(self.source_id.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_SOURCE_ID_BYTES_V1
            or len(self.source_identity.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_SOURCE_IDENTITY_BYTES_V1
        ):
            _fail("technical_kdj_compact_source_text_limit")
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_COMPACT_ENTRY_V1_SCHEMA,
            "verification_status": "projection_unqualified",
            "segment_index": self.segment_index,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "source_id": self.source_id,
            "source_identity": self.source_identity,
            "source_clock_sha256": self.source_clock_sha256,
            "source_pin_sha256": self.source_pin_sha256,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "raw_source_window_fingerprint_sha256": self.raw_source_window_fingerprint_sha256,
            "window_identity_sha256": self.window_identity_sha256,
            "evidence_identity_sha256": self.evidence_identity_sha256,
            "state": self.state,
            "reason_codes": list(self.reason_codes),
            "previous": self.previous.to_dict() if self.previous is not None else None,
            "current": self.current.to_dict() if self.current is not None else None,
            "input_row_count": self.input_row_count,
            "warmup_observed_sessions": self.warmup_observed_sessions,
            "warmup_contiguous": self.warmup_contiguous,
            "observed_prefix_contiguous": self.observed_prefix_contiguous,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }

    @property
    def compact_identity_sha256(self) -> str:
        return self._payload_with_identity()[1]

    def _payload_with_identity(self) -> tuple[dict[str, object], str]:
        body = self._body()
        identity = _sha256_json(body)
        payload = {**body, "compact_identity_sha256": identity}
        if len(_canonical_json_bytes(payload)) > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_ENTRY_BYTES_V1:
            _fail("technical_kdj_compact_entry_byte_limit")
        return payload, identity

    def to_dict(self) -> dict[str, object]:
        return self._payload_with_identity()[0]


def _compact_day(
    day: DailyMarketTechnicalKDJDayV1 | None,
) -> DailyMarketTechnicalUniverseKDJCompactDayV1 | None:
    if day is None:
        return None
    if type(day) is not DailyMarketTechnicalKDJDayV1:
        _fail("technical_kdj_compact_day_type_invalid")
    result = DailyMarketTechnicalUniverseKDJCompactDayV1(
        feature_date=day.feature_date,
        source_row_fingerprint_sha256=day.source_row_fingerprint_sha256,
        rsv=day.rsv,
        k=day.k,
        d=day.d,
        j=day.j,
    )
    result.to_dict()
    return result


@dataclass(frozen=True, slots=True)
class _ActiveParentV1:
    segment_index: int
    parent_read: object = field(repr=False, compare=False)
    expected_stock_codes: tuple[str, ...]
    expected_snapshots: tuple[object, ...] = field(repr=False, compare=False)
    consumed_stock_codes: list[str] = field(repr=False, compare=False)


class DailyMarketTechnicalKDJProjectionCollectorV1:
    """由未核 source request 綁定、只累積 compact projection 的暫存 collector。"""

    qualification_status = "projection_unqualified"

    def __init__(
        self,
        source_request: DailyMarketTechnicalUniverseKDJSourceRequestV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
        max_stocks: int = DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_STOCKS_V1,
        max_index_bytes: int = DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_INDEX_BYTES_V1,
    ) -> None:
        if type(source_request) is not DailyMarketTechnicalUniverseKDJSourceRequestV1:
            _fail("technical_kdj_collector_source_request_invalid")
        source_request.to_dict()
        if (
            type(max_stocks) is not int
            or not 1 <= max_stocks <= DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_STOCKS_V1
            or type(max_index_bytes) is not int
            or not 1 <= max_index_bytes <= DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_INDEX_BYTES_V1
        ):
            _fail("technical_kdj_collector_budget_invalid")
        _strict_cancel_check(cancel_callback)
        self.source_request = source_request
        self.cancel_callback = cancel_callback
        self.max_stocks = max_stocks
        self.max_index_bytes = max_index_bytes
        self._entries: list[DailyMarketTechnicalUniverseKDJCompactEntryV1] = []
        self._seen_codes: set[str] = set()
        self._index_byte_count = 0
        self._next_segment_index = 0
        self._active_parent: _ActiveParentV1 | None = None
        self._projection_group: DailyMarketTechnicalVerifiedProjectionGroupV1 | None = None
        self._bound_builder: object | None = None
        self._bind_attempted = False
        self._failed = False

    @property
    def unqualified_entries(self) -> tuple[DailyMarketTechnicalUniverseKDJCompactEntryV1, ...]:
        """回傳目前暫存的未核 entry；不代表完整母體或來源資格。"""

        if self._failed:
            _fail("technical_kdj_collector_failed")
        return tuple(self._entries)

    @property
    def collected_count(self) -> int:
        return len(self._entries)

    def _attach_projection_group(
        self, group: DailyMarketTechnicalVerifiedProjectionGroupV1,
    ) -> None:
        if (
            self._projection_group is not None
            or type(group) is not DailyMarketTechnicalVerifiedProjectionGroupV1
            or not group.contains_exact_member(self)
        ):
            _fail("technical_kdj_collector_group_binding_invalid")
        self._projection_group = group

    def bind_to_builder(self, builder: object) -> None:
        try:
            self._bind_to_builder(builder)
        except BaseException:
            self._failed = True
            self._active_parent = None
            raise

    def _bind_to_builder(self, builder: object) -> None:
        from app_module.daily_market_technical_universe_v4_query import (
            DailyMarketTechnicalUniverseV4ReadSessionBuilder,
        )

        _strict_cancel_check(self.cancel_callback)
        request = self.source_request.ma_source_request
        if (
            self._bind_attempted
            or self._bound_builder is not None
            or self._projection_group is None
            or type(builder) is not DailyMarketTechnicalUniverseV4ReadSessionBuilder
            or builder.store_output_root != request.technical_store_output_root
            or builder.generation_identity_sha256 != request.generation_identity_sha256
            or builder.plan_identity_sha256 != request.plan_identity_sha256
            or builder.plan_sha256 != request.plan_sha256
            or builder.receipt_identity_sha256 != request.receipt_identity_sha256
            or builder.receipt_sha256 != request.receipt_sha256
            or builder._bundle_pin is not None
            or builder.verified_session is not None
        ):
            _fail("technical_kdj_collector_builder_source_mismatch")
        self._bind_attempted = True
        self._bound_builder = builder

    def begin_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        try:
            self._begin_verified_parent(segment_index, parent_read)
        except BaseException:
            self._failed = True
            self._active_parent = None
            raise

    def _begin_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        from app_module.daily_market_technical_feature_snapshot_v4 import (
            DailyMarketTechnicalFeatureSnapshotV4,
        )
        from app_module.daily_market_technical_snapshot_v4_repository import (
            DailyMarketTechnicalBatchArtifactV4,
        )
        from app_module.daily_market_technical_universe_v4_store import (
            daily_market_technical_source_clock_v4_from_dict,
        )
        from app_module.daily_market_technical_method_contract_v4 import (
            validate_daily_market_technical_method_contract_v4,
        )
        from app_module.rule_research_technical_parent_capture_v4 import (
            DailyMarketTechnicalParentCaptureV4VerifiedRead,
        )

        _strict_cancel_check(self.cancel_callback)
        if (
            self._failed
            or self._projection_group is None
            or not self._projection_group.contains_exact_member(self)
            or self._bound_builder is None
            or self._active_parent is not None
            or type(segment_index) is not int
            or segment_index != self._next_segment_index
            or type(parent_read) is not DailyMarketTechnicalParentCaptureV4VerifiedRead
        ):
            _fail("technical_kdj_collector_parent_order_invalid")
        package = parent_read.package
        plan = package.get("plan")
        receipt = package.get("receipt")
        if not isinstance(plan, Mapping) or not isinstance(receipt, Mapping):
            _fail("technical_kdj_collector_parent_invalid")
        cohort = plan.get("cohort")
        clock_payload = plan.get("source_clock")
        method = plan.get("method_contracts")
        if not isinstance(cohort, Mapping) or not isinstance(clock_payload, Mapping) or not isinstance(method, Mapping):
            _fail("technical_kdj_collector_parent_invalid")
        request = self.source_request.ma_source_request
        try:
            source_clock = daily_market_technical_source_clock_v4_from_dict(clock_payload)
            validate_daily_market_technical_method_contract_v4(
                method, expected_sha256=request.method_contracts_sha256,
            )
        except Exception as exc:
            raise DailyMarketTechnicalUniverseKDJQueryV1Error(
                "technical_kdj_collector_parent_contract_invalid", str(exc)
            ) from exc
        included = cohort.get("included_stock_codes")
        batches = plan.get("batches")
        artifacts = receipt.get("batch_artifacts")
        verified_batches = parent_read.verified_batches
        if (
            plan.get("source_clock_identity_sha256") != request.source_clock_identity_sha256
            or receipt.get("source_clock_identity_sha256") != request.source_clock_identity_sha256
            or source_clock.identity_sha256 != request.source_clock_identity_sha256
            or source_clock.decision_date != request.decision_date
            or source_clock.decision_cutoff.isoformat() != request.decision_cutoff
            or plan.get("method_contracts_sha256") != request.method_contracts_sha256
            or cohort.get("decision_date") != request.decision_date.isoformat()
            or receipt.get("status") != "complete"
            or not isinstance(included, list)
            or any(not isinstance(code, str) or _STOCK_CODE_RE.fullmatch(code) is None for code in included)
            or tuple(included) != tuple(sorted(set(included)))
            or len(included) > self.max_stocks
            or not isinstance(batches, list)
            or not isinstance(artifacts, list)
            or len(batches) != len(artifacts)
            or len(artifacts) != len(verified_batches)
        ):
            _fail("technical_kdj_collector_parent_source_mismatch")
        expected_codes: list[str] = []
        expected_snapshots: list[DailyMarketTechnicalFeatureSnapshotV4] = []
        for batch_plan, artifact, verified in zip(batches, artifacts, verified_batches, strict=True):
            _strict_cancel_check(self.cancel_callback)
            if (
                not isinstance(batch_plan, Mapping)
                or not isinstance(artifact, Mapping)
                or type(verified) is not DailyMarketTechnicalBatchArtifactV4
            ):
                _fail("technical_kdj_collector_parent_batch_invalid")
            codes = batch_plan.get("expected_stock_codes")
            if (
                not isinstance(codes, list)
                or any(not isinstance(code, str) for code in codes)
                or tuple(codes) != verified.expected_stock_codes
                or tuple(snapshot.stock_code for snapshot in verified.snapshots) != tuple(codes)
                or artifact.get("manifest_path") != str(verified.manifest_path)
                or artifact.get("manifest_sha256") != verified.manifest_sha256
                or tuple(artifact.get("expected_stock_codes", ())) != tuple(codes)
            ):
                _fail("technical_kdj_collector_parent_batch_mismatch")
            expected_codes.extend(cast(list[str], codes))
            for snapshot in verified.snapshots:
                if type(snapshot) is not DailyMarketTechnicalFeatureSnapshotV4:
                    _fail("technical_kdj_collector_parent_snapshot_invalid")
                expected_snapshots.append(snapshot)
        if tuple(expected_codes) != tuple(included) or tuple(
            snapshot.stock_code for snapshot in expected_snapshots
        ) != tuple(included):
            _fail("technical_kdj_collector_parent_population_mismatch")
        self._active_parent = _ActiveParentV1(
            segment_index=segment_index,
            parent_read=parent_read,
            expected_stock_codes=tuple(cast(list[str], included)),
            expected_snapshots=tuple(expected_snapshots),
            consumed_stock_codes=[],
        )
        _strict_cancel_check(self.cancel_callback)

    def consume_verified_snapshot(
        self,
        segment_index: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        try:
            self._consume_verified_snapshot(segment_index, snapshot, parent_row)
        except BaseException:
            self._failed = True
            raise

    def _consume_verified_snapshot(
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
        active = self._active_parent
        position = len(active.consumed_stock_codes) if active is not None else -1
        if (
            self._failed
            or self._projection_group is None
            or not self._projection_group.contains_exact_member(self)
            or active is None
            or active.segment_index != segment_index
            or position < 0
            or type(snapshot) is not DailyMarketTechnicalFeatureSnapshotV4
            or type(parent_row) is not DailyMarketTechnicalParentV4Row
            or position >= len(active.expected_stock_codes)
            or snapshot is not active.expected_snapshots[position]
            or snapshot.stock_code != active.expected_stock_codes[position]
            or snapshot.stock_code in self._seen_codes
        ):
            _fail("technical_kdj_collector_snapshot_order_invalid")
        request = self.source_request.ma_source_request
        try:
            source_clock = daily_market_technical_source_clock_v4_from_dict(snapshot.source_clock)
        except (TypeError, ValueError) as exc:
            raise DailyMarketTechnicalUniverseKDJQueryV1Error(
                "technical_kdj_collector_source_clock_invalid", str(exc)
            ) from exc
        if (
            source_clock.identity_sha256 != request.source_clock_identity_sha256
            or source_clock.decision_date != request.decision_date
            or source_clock.decision_cutoff.isoformat() != request.decision_cutoff
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
            _fail("technical_kdj_collector_snapshot_source_mismatch")
        _strict_cancel_check(self.cancel_callback)
        try:
            evidence = project_daily_market_technical_kdj_evidence_v1(snapshot)
        except DailyMarketTechnicalKDJError as exc:
            raise DailyMarketTechnicalUniverseKDJQueryV1Error(
                "technical_kdj_collector_evidence_invalid", str(exc)
            ) from exc
        if (
            evidence.stock_code != snapshot.stock_code
            or evidence.decision_date != snapshot.decision_date
            or evidence.decision_cutoff != snapshot.decision_cutoff
            or evidence.snapshot_identity_sha256 != snapshot.snapshot_identity_sha256
            or evidence.source_identity != snapshot.source_identity
            or evidence.source_clock_sha256 != snapshot.source_clock_sha256
            or evidence.source_pin_sha256 != snapshot.source_pin_sha256
            or evidence.method_id != KDJ_METHOD_ID_V1
            or evidence.method_version != KDJ_METHOD_VERSION_V1
            or evidence.reader_qualified is not False
            or evidence.historical_pit_eligible is not False
            or evidence.source_available_at is not None
        ):
            _fail("technical_kdj_collector_evidence_snapshot_mismatch")
        entry = DailyMarketTechnicalUniverseKDJCompactEntryV1.from_unqualified_evidence(
            segment_index, evidence,
        )
        encoded_size = len(_canonical_json_bytes(entry.to_dict()))
        if encoded_size > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_ENTRY_BYTES_V1:
            _fail("technical_kdj_collector_entry_byte_limit")
        if (
            len(self._entries) >= self.max_stocks
            or len(self._entries) >= request.included_count
            or self._index_byte_count + encoded_size + 1 > self.max_index_bytes
        ):
            _fail("technical_kdj_collector_index_limit")
        _strict_cancel_check(self.cancel_callback)
        active.consumed_stock_codes.append(snapshot.stock_code)
        self._seen_codes.add(snapshot.stock_code)
        self._entries.append(entry)
        self._index_byte_count += encoded_size + 1
        _strict_cancel_check(self.cancel_callback)

    def end_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        try:
            self._end_verified_parent(segment_index, parent_read)
        except BaseException:
            self._failed = True
            self._active_parent = None
            raise

    def _end_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        _strict_cancel_check(self.cancel_callback)
        active = self._active_parent
        if (
            self._failed
            or active is None
            or active.segment_index != segment_index
            or active.parent_read is not parent_read
            or tuple(active.consumed_stock_codes) != active.expected_stock_codes
            or len(active.expected_snapshots) != len(active.expected_stock_codes)
        ):
            _fail("technical_kdj_collector_parent_incomplete")
        self._active_parent = None
        self._next_segment_index += 1
        _strict_cancel_check(self.cancel_callback)


class DailyMarketTechnicalVerifiedProjectionGroupV1:
    """不可變有序 fan-out；不發行或代表來源資格。"""

    qualification_status = "projection_group_unqualified"
    _members: tuple[
        DailyMarketTechnicalMaAlignmentVerifiedCollectorV1,
        DailyMarketTechnicalKDJProjectionCollectorV1,
    ]
    _cancel_callback: Callable[[], object] | None
    _bound_builder: object | None
    _bind_attempted: bool
    _active_parent: object | None
    _active_segment_index: int | None
    _next_segment_index: int
    _failed: bool
    __slots__ = (
        "_members", "_cancel_callback", "_bound_builder", "_bind_attempted",
        "_active_parent", "_active_segment_index", "_next_segment_index", "_failed",
    )

    def __init__(
        self,
        ma_collector: DailyMarketTechnicalMaAlignmentVerifiedCollectorV1,
        kdj_collector: DailyMarketTechnicalKDJProjectionCollectorV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> None:
        if (
            type(ma_collector) is not DailyMarketTechnicalMaAlignmentVerifiedCollectorV1
            or type(kdj_collector) is not DailyMarketTechnicalKDJProjectionCollectorV1
            or ma_collector.source_request is not kdj_collector.source_request.ma_source_request
        ):
            _fail("technical_kdj_projection_group_members_invalid")
        _strict_cancel_check(cancel_callback)
        object.__setattr__(self, "_members", (ma_collector, kdj_collector))
        object.__setattr__(self, "_cancel_callback", cancel_callback)
        object.__setattr__(self, "_bound_builder", None)
        object.__setattr__(self, "_bind_attempted", False)
        object.__setattr__(self, "_active_parent", None)
        object.__setattr__(self, "_active_segment_index", None)
        object.__setattr__(self, "_next_segment_index", 0)
        object.__setattr__(self, "_failed", False)
        kdj_collector._attach_projection_group(self)

    def __setattr__(self, name: str, value: object) -> None:
        if name == "_members" and hasattr(self, "_members"):
            _fail("technical_kdj_projection_group_members_immutable")
        object.__setattr__(self, name, value)

    @property
    def members(self) -> tuple[
        DailyMarketTechnicalMaAlignmentVerifiedCollectorV1,
        DailyMarketTechnicalKDJProjectionCollectorV1,
    ]:
        return self._members

    def contains_exact_member(self, candidate: object) -> bool:
        return any(member is candidate for member in self._members)

    def bind_to_builder(self, builder: object) -> None:
        try:
            self._bind_to_builder(builder)
        except BaseException:
            self._poison()
            raise

    def _poison(self) -> None:
        self._failed = True
        self._active_parent = None
        self._active_segment_index = None
        self._members[1]._failed = True
        self._members[1]._active_parent = None

    def _bind_to_builder(self, builder: object) -> None:
        from app_module.daily_market_technical_universe_v4_query import (
            DailyMarketTechnicalUniverseV4ReadSessionBuilder,
        )

        _strict_cancel_check(self._cancel_callback)
        if (
            self._failed
            or self._bind_attempted
            or self._bound_builder is not None
            or type(builder) is not DailyMarketTechnicalUniverseV4ReadSessionBuilder
        ):
            _fail("technical_kdj_projection_group_bind_invalid")
        self._bind_attempted = True
        try:
            self._members[0].bind_to_builder(builder)
            self._members[1].bind_to_builder(builder)
            _strict_cancel_check(self._cancel_callback)
            builder.bind_verified_projection(self)
            self._bound_builder = builder
        except BaseException:
            self._failed = True
            raise

    def begin_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        try:
            self._begin_verified_parent(segment_index, parent_read)
        except BaseException:
            self._poison()
            raise

    def _begin_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        _strict_cancel_check(self._cancel_callback)
        if (
            self._failed
            or self._bound_builder is None
            or self._active_parent is not None
            or type(segment_index) is not int
            or segment_index != self._next_segment_index
        ):
            _fail("technical_kdj_projection_group_parent_order_invalid")
        self._active_segment_index = segment_index
        try:
            for member in self._members:
                member.begin_verified_parent(segment_index, parent_read)
                _strict_cancel_check(self._cancel_callback)
        except BaseException:
            self._failed = True
            self._active_segment_index = None
            raise
        self._active_parent = parent_read

    def consume_verified_snapshot(
        self,
        segment_index: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        try:
            self._consume_verified_snapshot(segment_index, snapshot, parent_row)
        except BaseException:
            self._poison()
            raise

    def _consume_verified_snapshot(
        self,
        segment_index: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        _strict_cancel_check(self._cancel_callback)
        if (
            self._failed
            or self._bound_builder is None
            or self._active_parent is None
            or self._active_segment_index != segment_index
        ):
            _fail("technical_kdj_projection_group_snapshot_outside_parent")
        try:
            self._members[0].consume_verified_snapshot(segment_index, snapshot, parent_row)
            _strict_cancel_check(self._cancel_callback)
            self._members[1].consume_verified_snapshot(segment_index, snapshot, parent_row)
            _strict_cancel_check(self._cancel_callback)
        except BaseException:
            self._failed = True
            raise

    def end_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        try:
            self._end_verified_parent(segment_index, parent_read)
        except BaseException:
            self._poison()
            raise

    def _end_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        _strict_cancel_check(self._cancel_callback)
        if (
            self._failed
            or self._active_parent is not parent_read
            or self._active_segment_index != segment_index
        ):
            _fail("technical_kdj_projection_group_parent_end_mismatch")
        try:
            for member in self._members:
                member.end_verified_parent(segment_index, parent_read)
                _strict_cancel_check(self._cancel_callback)
        except BaseException:
            self._failed = True
            raise
        self._active_parent = None
        self._active_segment_index = None
        self._next_segment_index += 1


def _require_sha256(value: object, code: str) -> str:
    return _require_sha(value, code)
