"""在固定 v4 技術母體上做 Decimal 收盤價範圍與全域排序。

價格只從 StoreReader 同次 strict parent callback 已驗證的 snapshot 投影。
本模組不連接市場資料庫、不尋找最新資料，也不提供歷史 PIT 資格。
價格 compact index 的 canonical serialized budget 為 64 MiB；這不是 Python RSS 上限，
且不包含 P01 session 自己的 serialized index。
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal, NoReturn, cast

from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
    DailyMarketTechnicalSourceRow,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Row,
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_snapshot_v4_repository import (
    DailyMarketTechnicalBatchArtifactV4,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_INDEX,
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE,
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_READ_SESSION_MAX_INDEX_BYTES,
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4QueryError,
    DailyMarketTechnicalUniverseV4ReadSelection,
    DailyMarketTechnicalUniverseV4ReadSession,
    DailyMarketTechnicalUniverseV4ReadSessionBuilder,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
    DailyMarketTechnicalUniverseV4Counts,
    DailyMarketTechnicalUniverseV4ParentReceiptReference,
    DailyMarketTechnicalUniverseV4StoreError,
    DailyMarketTechnicalUniverseV4StoreReader,
    DailyMarketTechnicalUniverseV4VerifiedState,
)
from app_module.rule_research_technical_parent_capture_v4 import (
    DailyMarketTechnicalParentCaptureV4VerifiedRead,
)


DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_QUERY_V1_SCHEMA = (
    "daily-market-technical-universe-price-query.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_SOURCE_V1_SCHEMA = (
    "daily-market-technical-universe-price-source.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_PAGE_REQUEST_V1_SCHEMA = (
    "daily-market-technical-universe-price-page-request.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_PAGE_V1_SCHEMA = (
    "daily-market-technical-universe-price-page.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_STOCK_V1_SCHEMA = (
    "daily-market-technical-universe-price-stock.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_METHOD_VERSION = (
    "daily-market-technical-universe-price-range.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_UNIT = "TWD/share"
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_QUERY_BYTES = 8 * 1024 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_INDEX_BYTES = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_READ_SESSION_MAX_INDEX_BYTES
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_STOCKS = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_SIZE = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_INDEX = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_INDEX
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_STOCK_BYTES = 512 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_COMBINE_MODES = frozenset({"AND", "OR"})
_PRICE_STATES = frozenset({"pass", "fail", "unknown"})
_UNKNOWN_POLICIES = frozenset({"include", "exclude", "only"})
_RECEIPT_STATUSES = frozenset({"partial", "failed", "cancelled", "complete"})
_QUERY_SEAL = object()
_SESSION_SEAL = object()
_RESULT_SEAL = object()
_PAGE_SEAL = object()
_STOCK_SEAL = object()
_ANCHOR_TOKEN = object()


class DailyMarketTechnicalUniversePriceQueryV1Error(ValueError):
    """F07 價格查詢與精確重開的穩定錯誤。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalUniversePriceQueryV1Error(code, message)


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    if depth > 32:
        _fail("technical_universe_price_json_depth_limit")
    if isinstance(value, float):
        _fail("technical_universe_price_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("technical_universe_price_json_key_invalid")
            _reject_float_tree(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item, depth=depth + 1)


def _canonical_json(value: object) -> str:
    _reject_float_tree(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalUniversePriceQueryV1Error(
            "technical_universe_price_json_invalid"
        ) from exc


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _require_sha(value: object, code: str) -> str:
    if not _is_sha256(value):
        _fail(code)
    return cast(str, value)


def _parse_json(raw: bytes | str, *, maximum: int, code: str) -> object:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if not isinstance(encoded, bytes) or len(encoded) > maximum:
            _fail("technical_universe_price_json_byte_limit")

        def pairs(pairs_: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in pairs_:
                if key in result:
                    _fail("technical_universe_price_json_duplicate_key")
                result[key] = item
            return result

        def parse_float(_value: str) -> NoReturn:
            _fail("technical_universe_price_float_forbidden")

        def parse_constant(_value: str) -> NoReturn:
            _fail("technical_universe_price_json_constant_invalid")

        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=parse_float,
            parse_constant=parse_constant,
        )
        _reject_float_tree(value)
        if _canonical_json(value).encode("utf-8") != encoded:
            _fail("technical_universe_price_json_noncanonical")
        return value
    except DailyMarketTechnicalUniversePriceQueryV1Error:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniversePriceQueryV1Error(code) from exc


def _parse_date(value: object, code: str) -> date:
    if not isinstance(value, str):
        _fail(code)
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise DailyMarketTechnicalUniversePriceQueryV1Error(code) from exc
    if result.isoformat() != value:
        _fail(code)
    return result


def _canonical_store_root(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 4096:
        return False
    try:
        path = Path(value)
    except (TypeError, ValueError):
        return False
    return (
        path.is_absolute()
        and ".." not in path.parts
        and str(path) == value
        and not value.startswith(("\\\\?\\", "\\\\.\\"))
    )


def _decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        _fail("technical_universe_price_bound_invalid")
    exponent = value.as_tuple().exponent
    if (
        len(value.as_tuple().digits) > 64
        or not isinstance(exponent, int)
        or abs(exponent) > 64
    ):
        _fail("technical_universe_price_bound_limit")
    # Decimal.normalize() 會受目前運算精度限制（通常為 28 位）。
    # 直接格式化可完整保留來源 Decimal 精度。
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if not rendered or len(rendered) > 128:
        _fail("technical_universe_price_bound_limit")
    return rendered


def _parse_decimal_text(value: object, code: str) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > 128:
        _fail(code)
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise DailyMarketTechnicalUniversePriceQueryV1Error(code) from exc
    if not result.is_finite() or result <= 0 or _decimal_text(result) != value:
        _fail(code)
    return result


def _check_cancel(cancel_callback: Callable[[], object] | None) -> None:
    if cancel_callback is None:
        return
    try:
        cancelled = cancel_callback()
    except Exception as exc:
        raise DailyMarketTechnicalUniversePriceQueryV1Error(
            "technical_universe_price_cancel_check_failed"
        ) from exc
    if type(cancelled) is not bool:
        _fail("technical_universe_price_cancel_callback_invalid")
    if cancelled:
        _fail("technical_universe_price_cancelled")


def _bounded_codes(
    value: object,
    *,
    code: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(code)
    result: list[str] = []
    for index, item in enumerate(value):
        if index >= DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_STOCKS:
            _fail("technical_universe_price_stock_count_limit")
        if not isinstance(item, str) or _STOCK_CODE_RE.fullmatch(item) is None:
            _fail(code)
        result.append(item)
    normalized = tuple(result)
    if (not allow_empty and not normalized) or normalized != tuple(sorted(set(normalized))):
        _fail(code)
    return normalized


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceSourceV1:
    """一次 exact store read 所核的完整技術來源描述。"""

    store_output_root: str
    generation_identity_sha256: str
    plan_identity_sha256: str
    plan_sha256: str
    receipt_identity_sha256: str
    receipt_sha256: str
    receipt_status: Literal["partial", "failed", "cancelled", "complete"]
    cohort_identity_sha256: str
    source_clock_identity_sha256: str
    method_contracts_sha256: str
    universe_id: str
    population_version: str
    decision_date: date
    segment_count: int
    counts: DailyMarketTechnicalUniverseV4Counts
    method_rule_keys: tuple[str, ...]
    exclusion_reasons_sha256: str
    p01_read_session_identity_sha256: str
    price_index_identity_sha256: str
    price_index_bytes: int
    schema_version: str = DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_SOURCE_V1_SCHEMA
    source_available_at: None = None
    availability_status: Literal["unknown"] = "unknown"
    historical_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if self.schema_version != DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_SOURCE_V1_SCHEMA:
            _fail("technical_universe_price_source_schema_invalid")
        if not _canonical_store_root(self.store_output_root):
            _fail("technical_universe_price_source_root_invalid")
        for name in (
            "generation_identity_sha256", "plan_identity_sha256", "plan_sha256",
            "receipt_identity_sha256", "receipt_sha256", "cohort_identity_sha256",
            "source_clock_identity_sha256", "method_contracts_sha256", "exclusion_reasons_sha256",
            "p01_read_session_identity_sha256", "price_index_identity_sha256",
        ):
            _require_sha(getattr(self, name), "technical_universe_price_source_pin_invalid")
        if not isinstance(self.receipt_status, str) or self.receipt_status not in _RECEIPT_STATUSES:
            _fail("technical_universe_price_source_status_invalid")
        if (
            not isinstance(self.universe_id, str)
            or not self.universe_id.strip()
            or not isinstance(self.population_version, str)
            or not self.population_version.strip()
            or not isinstance(self.decision_date, date)
            or isinstance(self.decision_date, datetime)
            or type(self.segment_count) is not int
            or self.segment_count < 0
            or type(self.price_index_bytes) is not int
            or not 0 <= self.price_index_bytes <= DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_INDEX_BYTES
            or not isinstance(self.counts, DailyMarketTechnicalUniverseV4Counts)
            or not isinstance(self.method_rule_keys, tuple)
            or len(self.method_rule_keys) != 5
            or any(not isinstance(key, str) or not key for key in self.method_rule_keys)
            or len(self.method_rule_keys) != len(set(self.method_rule_keys))
            or self.source_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
        ):
            _fail("technical_universe_price_source_invalid")

    @property
    def source_identity_sha256(self) -> str:
        return _sha256_json(self.to_dict())

    def open_kwargs(self) -> dict[str, object]:
        """提供 exact reopen 所需的具名 pins；不作 latest 選擇。"""

        return {
            "store_output_root": self.store_output_root,
            "generation_identity_sha256": self.generation_identity_sha256,
            "plan_identity_sha256": self.plan_identity_sha256,
            "plan_sha256": self.plan_sha256,
            "receipt_identity_sha256": self.receipt_identity_sha256,
            "receipt_sha256": self.receipt_sha256,
        }

    @property
    def current_only(self) -> Literal[True]:
        return True

    @property
    def full_market_claim(self) -> Literal[False]:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "store_output_root": self.store_output_root,
            "generation_identity_sha256": self.generation_identity_sha256,
            "plan_identity_sha256": self.plan_identity_sha256,
            "plan_sha256": self.plan_sha256,
            "receipt_identity_sha256": self.receipt_identity_sha256,
            "receipt_sha256": self.receipt_sha256,
            "receipt_status": self.receipt_status,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "source_clock_identity_sha256": self.source_clock_identity_sha256,
            "method_contracts_sha256": self.method_contracts_sha256,
            "universe_id": self.universe_id,
            "population_version": self.population_version,
            "decision_date": self.decision_date.isoformat(),
            "segment_count": self.segment_count,
            "counts": self.counts.to_dict(),
            "method_rule_keys": list(self.method_rule_keys),
            "exclusion_reasons_sha256": self.exclusion_reasons_sha256,
            "p01_read_session_identity_sha256": self.p01_read_session_identity_sha256,
            "price_index_identity_sha256": self.price_index_identity_sha256,
            "price_index_bytes": self.price_index_bytes,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
            "current_only": True,
            "full_market_claim": False,
        }

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalUniversePriceSourceV1:
        expected = {
            "schema_version", "store_output_root", "generation_identity_sha256",
            "plan_identity_sha256", "plan_sha256", "receipt_identity_sha256",
            "receipt_sha256", "receipt_status", "cohort_identity_sha256",
            "source_clock_identity_sha256", "method_contracts_sha256", "universe_id",
            "population_version", "decision_date", "segment_count", "counts",
            "method_rule_keys", "exclusion_reasons_sha256", "p01_read_session_identity_sha256",
            "price_index_identity_sha256", "price_index_bytes", "source_available_at",
            "availability_status", "historical_pit_eligible", "current_only",
            "full_market_claim",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            _fail("technical_universe_price_source_fields_invalid")
        if (
            payload["source_available_at"] is not None
            or payload["availability_status"] != "unknown"
            or payload["historical_pit_eligible"] is not False
            or payload["current_only"] is not True
            or payload["full_market_claim"] is not False
            or not isinstance(payload["method_rule_keys"], list)
        ):
            _fail("technical_universe_price_source_qualification_invalid")
        counts = DailyMarketTechnicalUniverseV4Counts.from_dict(payload["counts"])
        keys = tuple(cast(list[str], payload["method_rule_keys"]))
        result = cls(
            schema_version=cast(str, payload["schema_version"]),
            store_output_root=cast(str, payload["store_output_root"]),
            generation_identity_sha256=cast(str, payload["generation_identity_sha256"]),
            plan_identity_sha256=cast(str, payload["plan_identity_sha256"]),
            plan_sha256=cast(str, payload["plan_sha256"]),
            receipt_identity_sha256=cast(str, payload["receipt_identity_sha256"]),
            receipt_sha256=cast(str, payload["receipt_sha256"]),
            receipt_status=cast(Any, payload["receipt_status"]),
            cohort_identity_sha256=cast(str, payload["cohort_identity_sha256"]),
            source_clock_identity_sha256=cast(str, payload["source_clock_identity_sha256"]),
            method_contracts_sha256=cast(str, payload["method_contracts_sha256"]),
            universe_id=cast(str, payload["universe_id"]),
            population_version=cast(str, payload["population_version"]),
            decision_date=_parse_date(payload["decision_date"], "technical_universe_price_source_date_invalid"),
            segment_count=cast(int, payload["segment_count"]),
            counts=counts,
            method_rule_keys=keys,
            exclusion_reasons_sha256=cast(str, payload["exclusion_reasons_sha256"]),
            p01_read_session_identity_sha256=cast(str, payload["p01_read_session_identity_sha256"]),
            price_index_identity_sha256=cast(str, payload["price_index_identity_sha256"]),
            price_index_bytes=cast(int, payload["price_index_bytes"]),
            source_available_at=None,
            availability_status="unknown",
            historical_pit_eligible=False,
        )
        if result.to_dict() != dict(payload):
            _fail("technical_universe_price_source_noncanonical")
        return result


def _source_from_verified_state(
    *,
    store_output_root: str,
    state: DailyMarketTechnicalUniverseV4VerifiedState,
    plan_sha256: str,
    receipt_sha256: str,
    p01_session: DailyMarketTechnicalUniverseV4ReadSession,
    price_index_identity_sha256: str,
    price_index_bytes: int,
) -> DailyMarketTechnicalUniversePriceSourceV1:
    plan_body = state.plan.to_dict()
    cohort = state.plan.cohort
    method_contracts = cast(Mapping[str, object], plan_body["method_contracts"])
    rules = method_contracts.get("rules")
    if not isinstance(rules, list):
        _fail("technical_universe_price_method_contract_invalid")
    rule_keys: list[str] = []
    for item in rules:
        if not isinstance(item, Mapping) or not isinstance(item.get("key"), str):
            _fail("technical_universe_price_method_contract_invalid")
        rule_keys.append(cast(str, item["key"]))
    if len(rule_keys) != len(set(rule_keys)) or not rule_keys:
        _fail("technical_universe_price_method_contract_invalid")
    return DailyMarketTechnicalUniversePriceSourceV1(
        store_output_root=store_output_root,
        generation_identity_sha256=state.plan.generation_identity_sha256,
        plan_identity_sha256=state.plan.identity_sha256,
        plan_sha256=plan_sha256,
        receipt_identity_sha256=state.receipt.identity_sha256,
        receipt_sha256=receipt_sha256,
        receipt_status=cast(Any, state.receipt.status),
        cohort_identity_sha256=cohort.cohort_identity_sha256,
        source_clock_identity_sha256=state.plan.source_clock.identity_sha256,
        method_contracts_sha256=cast(str, plan_body["method_contracts_sha256"]),
        universe_id=cohort.universe_id,
        population_version=cohort.population_version,
        decision_date=cohort.decision_date,
        segment_count=len(state.plan.segments),
        counts=state.counts,
        method_rule_keys=tuple(rule_keys),
        exclusion_reasons_sha256=_sha256_json(dict(cohort.exclusion_reasons)),
        p01_read_session_identity_sha256=p01_session.read_session_identity_sha256,
        price_index_identity_sha256=price_index_identity_sha256,
        price_index_bytes=price_index_bytes,
    )


def _price_fact_payload(
    *,
    stock_code: str,
    status: Literal["known", "unknown"],
    close_price: Decimal | None,
    observation_date: date | None,
    raw_row_fingerprint_sha256: str | None,
    snapshot_identity_sha256: str,
    source_identity: str,
    reason_codes: tuple[str, ...],
) -> dict[str, object]:
    return {
        "stock_code": stock_code,
        "status": status,
        "close_price": _decimal_text(close_price) if close_price is not None else None,
        "unit": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_UNIT,
        "observation_date": observation_date.isoformat() if observation_date else None,
        "raw_row_fingerprint_sha256": raw_row_fingerprint_sha256,
        "snapshot_identity_sha256": snapshot_identity_sha256,
        "source_identity": source_identity,
        "reason_codes": list(reason_codes),
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceFactV1:
    stock_code: str
    status: Literal["known", "unknown"]
    close_price: Decimal | None
    observation_date: date | None
    raw_row_fingerprint_sha256: str | None
    snapshot_identity_sha256: str
    source_identity: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.stock_code, str)
            or _STOCK_CODE_RE.fullmatch(self.stock_code) is None
            or not isinstance(self.status, str)
            or self.status not in {"known", "unknown"}
            or not _is_sha256(self.snapshot_identity_sha256)
            or not isinstance(self.source_identity, str)
            or not self.source_identity
            or not isinstance(self.reason_codes, tuple)
            or len(self.reason_codes) > 64
            or any(not isinstance(item, str) or not item or len(item) > 256 for item in self.reason_codes)
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
        ):
            _fail("technical_universe_price_fact_invalid")
        if self.status == "known":
            if (
                not isinstance(self.close_price, Decimal)
                or not self.close_price.is_finite()
                or self.close_price <= 0
                or not isinstance(self.observation_date, date)
                or isinstance(self.observation_date, datetime)
                or not _is_sha256(self.raw_row_fingerprint_sha256)
                or self.reason_codes
            ):
                _fail("technical_universe_price_fact_invalid")
        elif (
            self.close_price is not None
            or (self.observation_date is not None and (
                not isinstance(self.observation_date, date)
                or isinstance(self.observation_date, datetime)
            ))
            or (self.raw_row_fingerprint_sha256 is not None and not _is_sha256(self.raw_row_fingerprint_sha256))
            or not self.reason_codes
        ):
            _fail("technical_universe_price_fact_invalid")

    def to_dict(self) -> dict[str, object]:
        return _price_fact_payload(
            stock_code=self.stock_code,
            status=self.status,
            close_price=self.close_price,
            observation_date=self.observation_date,
            raw_row_fingerprint_sha256=self.raw_row_fingerprint_sha256,
            snapshot_identity_sha256=self.snapshot_identity_sha256,
            source_identity=self.source_identity,
            reason_codes=self.reason_codes,
        )

    @property
    def identity_sha256(self) -> str:
        return _sha256_json(self.to_dict())


def _unknown_fact(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    *,
    code: str,
    observation_date: date | None = None,
    row_fingerprint: str | None = None,
    reasons: Sequence[str] = (),
) -> DailyMarketTechnicalUniversePriceFactV1:
    reason_codes = tuple(sorted({code, *reasons}))
    return DailyMarketTechnicalUniversePriceFactV1(
        stock_code=snapshot.stock_code,
        status="unknown",
        close_price=None,
        observation_date=observation_date,
        raw_row_fingerprint_sha256=row_fingerprint,
        snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        source_identity=snapshot.source_identity,
        reason_codes=reason_codes,
    )


def _price_fact_from_snapshot(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    *,
    decision_date: date,
) -> DailyMarketTechnicalUniversePriceFactV1:
    if snapshot.decision_date != decision_date:
        _fail("technical_universe_price_snapshot_decision_date_mismatch")
    current = snapshot.current_session
    if current is None:
        return _unknown_fact(snapshot, code="price_current_session_missing")
    observed = current.feature_date
    if observed > decision_date:
        _fail("technical_universe_price_future_current_session")
    if current.stock_code != snapshot.stock_code or current.source_identity != snapshot.source_identity:
        return _unknown_fact(
            snapshot,
            code="price_current_session_source_mismatch",
            observation_date=observed,
            row_fingerprint=current.source_fingerprint_sha256,
        )
    if current.pin_verified is not True:
        return _unknown_fact(
            snapshot,
            code="price_current_session_pin_unverified",
            observation_date=observed,
            row_fingerprint=current.source_fingerprint_sha256,
        )
    matching_pins = tuple(pin for pin in snapshot.session_pins if pin.feature_date == observed)
    if (
        len(matching_pins) != 1
        or matching_pins[0].pin_verified is not True
        or matching_pins[0].source_fingerprint_sha256 != current.source_fingerprint_sha256
    ):
        return _unknown_fact(
            snapshot,
            code="price_current_session_pin_missing_or_ambiguous",
            observation_date=observed,
            row_fingerprint=current.source_fingerprint_sha256,
        )
    rows_same_date = tuple(row for row in snapshot.rows if row.feature_date == observed)
    if len(rows_same_date) != 1:
        return _unknown_fact(
            snapshot,
            code="price_current_session_row_missing_or_duplicate",
            observation_date=observed,
            row_fingerprint=current.source_fingerprint_sha256,
        )
    row = rows_same_date[0]
    if row.row_fingerprint_sha256 != current.source_fingerprint_sha256:
        return _unknown_fact(
            snapshot,
            code="price_current_session_row_fingerprint_mismatch",
            observation_date=observed,
            row_fingerprint=row.row_fingerprint_sha256,
        )
    if row.stock_code != snapshot.stock_code:
        return _unknown_fact(
            snapshot,
            code="price_current_session_row_stock_mismatch",
            observation_date=observed,
            row_fingerprint=row.row_fingerprint_sha256,
        )
    if not row.ohlc_valid:
        return _unknown_fact(
            snapshot,
            code="price_current_session_ohlc_invalid",
            observation_date=observed,
            row_fingerprint=row.row_fingerprint_sha256,
            reasons=row.invalid_reasons,
        )
    close = row.close_price
    if not isinstance(close, Decimal) or not close.is_finite() or close <= 0:
        return _unknown_fact(
            snapshot,
            code="price_current_session_close_missing_or_invalid",
            observation_date=observed,
            row_fingerprint=row.row_fingerprint_sha256,
            reasons=row.invalid_reasons,
        )
    return DailyMarketTechnicalUniversePriceFactV1(
        stock_code=snapshot.stock_code,
        status="known",
        close_price=close,
        observation_date=observed,
        raw_row_fingerprint_sha256=row.row_fingerprint_sha256,
        snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        source_identity=snapshot.source_identity,
        reason_codes=(),
    )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceQueryV1:
    """固定 exact v4 來源與技術/價格條件；頁碼由獨立 request 保存。"""

    source: DailyMarketTechnicalUniversePriceSourceV1
    rule_state_filters: tuple[DailyMarketTechnicalRuleStateFilterV4, ...]
    combine_mode: Literal["AND", "OR"]
    technical_stock_filter: tuple[str, ...]
    eligible_stock_codes: tuple[str, ...] | None
    min_close_price: Decimal | None
    min_inclusive: bool
    max_close_price: Decimal | None
    max_inclusive: bool
    unknown_price_policy: Literal["include", "exclude", "only"]
    descending: bool
    query_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_QUERY_V1_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_QUERY_V1_SCHEMA:
            _fail("technical_universe_price_query_schema_invalid")
        if not isinstance(self.source, DailyMarketTechnicalUniversePriceSourceV1):
            _fail("technical_universe_price_query_source_invalid")
        if (
            not isinstance(self.combine_mode, str)
            or self.combine_mode not in _COMBINE_MODES
            or not isinstance(self.unknown_price_policy, str)
            or self.unknown_price_policy not in _UNKNOWN_POLICIES
        ):
            _fail("technical_universe_price_query_conditions_invalid")
        if type(self.min_inclusive) is not bool or type(self.max_inclusive) is not bool or type(self.descending) is not bool:
            _fail("technical_universe_price_query_conditions_invalid")
        if self.min_close_price is not None:
            _decimal_text(self.min_close_price)
        if self.max_close_price is not None:
            _decimal_text(self.max_close_price)
        if (
            self.min_close_price is not None
            and self.max_close_price is not None
            and self.min_close_price > self.max_close_price
        ):
            _fail("technical_universe_price_range_invalid")
        if (
            not isinstance(self.rule_state_filters, tuple)
            or len(self.rule_state_filters) > len(self.source.method_rule_keys)
        ):
            _fail("technical_universe_price_rule_filter_limit")
        filter_keys: list[str] = []
        for item in self.rule_state_filters:
            if not isinstance(item, DailyMarketTechnicalRuleStateFilterV4):
                _fail("technical_universe_price_rule_filter_invalid")
            if item.rule_key not in self.source.method_rule_keys:
                _fail("technical_universe_price_rule_key_invalid")
            filter_keys.append(item.rule_key)
        if len(filter_keys) != len(set(filter_keys)):
            _fail("technical_universe_price_rule_filter_duplicate")
        _bounded_codes(self.technical_stock_filter, code="technical_universe_price_technical_stock_filter_invalid", allow_empty=True)
        if self.eligible_stock_codes is not None:
            _bounded_codes(self.eligible_stock_codes, code="technical_universe_price_eligible_stock_filter_invalid", allow_empty=True)
        expected = _sha256_json(self._body_without_identity())
        if not _is_sha256(self.query_identity_sha256) or expected != self.query_identity_sha256:
            _fail("technical_universe_price_query_identity_mismatch")

    @classmethod
    def create(
        cls,
        *,
        source: DailyMarketTechnicalUniversePriceSourceV1,
        rule_state_filters: Sequence[DailyMarketTechnicalRuleStateFilterV4] = (),
        combine_mode: Literal["AND", "OR"] = "AND",
        technical_stock_filter: Sequence[str] = (),
        eligible_stock_codes: Sequence[str] | None = None,
        min_close_price: Decimal | None = None,
        min_inclusive: bool = True,
        max_close_price: Decimal | None = None,
        max_inclusive: bool = True,
        unknown_price_policy: Literal["include", "exclude", "only"] = "include",
        descending: bool = False,
    ) -> DailyMarketTechnicalUniversePriceQueryV1:
        if not isinstance(source, DailyMarketTechnicalUniversePriceSourceV1):
            _fail("technical_universe_price_query_source_invalid")
        if isinstance(rule_state_filters, (str, bytes)) or not isinstance(rule_state_filters, Sequence):
            _fail("technical_universe_price_rule_filter_invalid")
        filter_items: list[DailyMarketTechnicalRuleStateFilterV4] = []
        for index, item in enumerate(rule_state_filters):
            if index >= len(source.method_rule_keys):
                _fail("technical_universe_price_rule_filter_limit")
            if not isinstance(item, DailyMarketTechnicalRuleStateFilterV4):
                _fail("technical_universe_price_rule_filter_invalid")
            filter_items.append(item)
        filters = tuple(filter_items)
        stock_filter = _bounded_codes(
            technical_stock_filter,
            code="technical_universe_price_technical_stock_filter_invalid",
            allow_empty=True,
        )
        eligible = (
            None
            if eligible_stock_codes is None
            else _bounded_codes(
                eligible_stock_codes,
                code="technical_universe_price_eligible_stock_filter_invalid",
                allow_empty=True,
            )
        )
        provisional = cls.__new__(cls)
        object.__setattr__(provisional, "source", source)
        object.__setattr__(provisional, "rule_state_filters", filters)
        object.__setattr__(provisional, "combine_mode", combine_mode)
        object.__setattr__(provisional, "technical_stock_filter", stock_filter)
        object.__setattr__(provisional, "eligible_stock_codes", eligible)
        object.__setattr__(provisional, "min_close_price", min_close_price)
        object.__setattr__(provisional, "min_inclusive", min_inclusive)
        object.__setattr__(provisional, "max_close_price", max_close_price)
        object.__setattr__(provisional, "max_inclusive", max_inclusive)
        object.__setattr__(provisional, "unknown_price_policy", unknown_price_policy)
        object.__setattr__(provisional, "descending", descending)
        object.__setattr__(provisional, "schema_version", DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_QUERY_V1_SCHEMA)
        body = provisional._body_without_identity()
        return cls(
            source=source,
            rule_state_filters=filters,
            combine_mode=combine_mode,
            technical_stock_filter=stock_filter,
            eligible_stock_codes=eligible,
            min_close_price=min_close_price,
            min_inclusive=min_inclusive,
            max_close_price=max_close_price,
            max_inclusive=max_inclusive,
            unknown_price_policy=unknown_price_policy,
            descending=descending,
            query_identity_sha256=_sha256_json(body),
        )

    def _body_without_identity(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source": self.source.to_dict(),
            "rule_state_filters": [item.to_dict() for item in self.rule_state_filters],
            "combine_mode": self.combine_mode,
            "technical_stock_filter": list(self.technical_stock_filter),
            "eligible_stock_filter": (
                {"mode": "all"}
                if self.eligible_stock_codes is None
                else {"mode": "explicit", "codes": list(self.eligible_stock_codes)}
            ),
            "min_close_price": _decimal_text(self.min_close_price) if self.min_close_price is not None else None,
            "min_inclusive": self.min_inclusive,
            "max_close_price": _decimal_text(self.max_close_price) if self.max_close_price is not None else None,
            "max_inclusive": self.max_inclusive,
            "unknown_price_policy": self.unknown_price_policy,
            "descending": self.descending,
            "unit": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_UNIT,
            "method_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_METHOD_VERSION,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body_without_identity(), "query_identity_sha256": self.query_identity_sha256}

    def to_json(self) -> str:
        raw = _canonical_json(self.to_dict())
        if len(raw.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_QUERY_BYTES:
            _fail("technical_universe_price_query_byte_limit")
        return raw

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalUniversePriceQueryV1:
        expected_keys = {
            "schema_version", "source", "rule_state_filters", "combine_mode",
            "technical_stock_filter", "eligible_stock_filter", "min_close_price",
            "min_inclusive", "max_close_price", "max_inclusive",
            "unknown_price_policy", "descending", "unit", "method_version",
            "query_identity_sha256",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected_keys:
            _fail("technical_universe_price_query_fields_invalid")
        if (
            payload["schema_version"] != DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_QUERY_V1_SCHEMA
            or payload["unit"] != DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_UNIT
            or payload["method_version"] != DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_METHOD_VERSION
            or not isinstance(payload["rule_state_filters"], list)
            or not isinstance(payload["technical_stock_filter"], list)
            or not isinstance(payload["eligible_stock_filter"], Mapping)
            or not isinstance(payload["source"], Mapping)
        ):
            _fail("technical_universe_price_query_schema_invalid")
        source_payload = cast(Mapping[str, object], payload["source"])
        method_rule_keys = source_payload.get("method_rule_keys")
        if (
            not isinstance(method_rule_keys, list)
            or len(cast(list[object], payload["rule_state_filters"])) > len(method_rule_keys)
        ):
            _fail("technical_universe_price_rule_filter_limit")
        eligible_payload = cast(Mapping[str, object], payload["eligible_stock_filter"])
        if set(eligible_payload) == {"mode"} and eligible_payload.get("mode") == "all":
            eligible_codes = None
        elif set(eligible_payload) == {"mode", "codes"} and eligible_payload.get("mode") == "explicit" and isinstance(eligible_payload.get("codes"), list):
            eligible_codes = cast(list[str], eligible_payload["codes"])
        else:
            _fail("technical_universe_price_eligible_stock_filter_invalid")
        filters = tuple(
            DailyMarketTechnicalRuleStateFilterV4.from_dict(item)
            for item in cast(list[object], payload["rule_state_filters"])
        )
        minimum = None if payload["min_close_price"] is None else _parse_decimal_text(payload["min_close_price"], "technical_universe_price_min_bound_invalid")
        maximum = None if payload["max_close_price"] is None else _parse_decimal_text(payload["max_close_price"], "technical_universe_price_max_bound_invalid")
        if type(payload["min_inclusive"]) is not bool or type(payload["max_inclusive"]) is not bool or type(payload["descending"]) is not bool:
            _fail("technical_universe_price_query_boolean_invalid")
        source = DailyMarketTechnicalUniversePriceSourceV1.from_dict(payload["source"])
        result = cls.create(
            source=source,
            rule_state_filters=filters,
            combine_mode=cast(Any, payload["combine_mode"]),
            technical_stock_filter=cast(list[str], payload["technical_stock_filter"]),
            eligible_stock_codes=eligible_codes,
            min_close_price=minimum,
            min_inclusive=cast(bool, payload["min_inclusive"]),
            max_close_price=maximum,
            max_inclusive=cast(bool, payload["max_inclusive"]),
            unknown_price_policy=cast(Any, payload["unknown_price_policy"]),
            descending=cast(bool, payload["descending"]),
        )
        if result.query_identity_sha256 != payload["query_identity_sha256"] or result.to_dict() != dict(payload):
            _fail("technical_universe_price_query_identity_mismatch")
        return result

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalUniversePriceQueryV1:
        value = _parse_json(
            raw,
            maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_QUERY_BYTES,
            code="technical_universe_price_query_json_invalid",
        )
        result = cls.from_dict(value)
        if result.to_json().encode("utf-8") != (raw.encode("utf-8") if isinstance(raw, str) else raw):
            _fail("technical_universe_price_query_json_noncanonical")
        return result


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceCountsV1:
    """全技術母體選取中的價格三態及套用 unknown policy 後分母。"""

    base_matching_count: int
    pass_count: int
    fail_count: int
    unknown_count: int
    matching_count: int

    def __post_init__(self) -> None:
        values = (
            self.base_matching_count,
            self.pass_count,
            self.fail_count,
            self.unknown_count,
            self.matching_count,
        )
        if any(type(item) is not int or item < 0 for item in values):
            _fail("technical_universe_price_counts_invalid")
        if self.pass_count + self.fail_count + self.unknown_count != self.base_matching_count:
            _fail("technical_universe_price_counts_inconsistent")
        if self.matching_count > self.base_matching_count:
            _fail("technical_universe_price_counts_inconsistent")

    def to_dict(self) -> dict[str, int]:
        return {
            "base_matching_count": self.base_matching_count,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "unknown_count": self.unknown_count,
            "matching_count": self.matching_count,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePricePageRequestV1:
    """一個已完成操作的固定頁面座標，可隨 query 書籤保存後精確重開。"""

    query_identity_sha256: str
    operation_identity_sha256: str
    selection_identity_sha256: str
    page_index: int
    page_size: int
    request_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_PAGE_REQUEST_V1_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_PAGE_REQUEST_V1_SCHEMA:
            _fail("technical_universe_price_page_request_schema_invalid")
        for value in (
            self.query_identity_sha256,
            self.operation_identity_sha256,
            self.selection_identity_sha256,
        ):
            _require_sha(value, "technical_universe_price_page_request_pin_invalid")
        if (
            type(self.page_index) is not int
            or not 0 <= self.page_index <= DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_INDEX
            or type(self.page_size) is not int
            or not 1 <= self.page_size <= DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_SIZE
        ):
            _fail("technical_universe_price_page_request_range_invalid")
        if self.request_identity_sha256 != _sha256_json(self._body_without_identity()):
            _fail("technical_universe_price_page_request_identity_mismatch")

    @classmethod
    def create(
        cls,
        *,
        query_identity_sha256: str,
        operation_identity_sha256: str,
        selection_identity_sha256: str,
        page_index: int,
        page_size: int,
    ) -> DailyMarketTechnicalUniversePricePageRequestV1:
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_PAGE_REQUEST_V1_SCHEMA,
            "query_identity_sha256": query_identity_sha256,
            "operation_identity_sha256": operation_identity_sha256,
            "selection_identity_sha256": selection_identity_sha256,
            "page_index": page_index,
            "page_size": page_size,
        }
        return cls(
            query_identity_sha256=query_identity_sha256,
            operation_identity_sha256=operation_identity_sha256,
            selection_identity_sha256=selection_identity_sha256,
            page_index=page_index,
            page_size=page_size,
            request_identity_sha256=_sha256_json(body),
        )

    def _body_without_identity(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "query_identity_sha256": self.query_identity_sha256,
            "operation_identity_sha256": self.operation_identity_sha256,
            "selection_identity_sha256": self.selection_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._body_without_identity(),
            "request_identity_sha256": self.request_identity_sha256,
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalUniversePricePageRequestV1:
        expected = {
            "schema_version", "query_identity_sha256", "operation_identity_sha256",
            "selection_identity_sha256", "page_index", "page_size",
            "request_identity_sha256",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            _fail("technical_universe_price_page_request_fields_invalid")
        if any(type(payload[key]) is not int for key in ("page_index", "page_size")):
            _fail("technical_universe_price_page_request_range_invalid")
        return cls(
            schema_version=cast(str, payload["schema_version"]),
            query_identity_sha256=cast(str, payload["query_identity_sha256"]),
            operation_identity_sha256=cast(str, payload["operation_identity_sha256"]),
            selection_identity_sha256=cast(str, payload["selection_identity_sha256"]),
            page_index=cast(int, payload["page_index"]),
            page_size=cast(int, payload["page_size"]),
            request_identity_sha256=cast(str, payload["request_identity_sha256"]),
        )

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalUniversePricePageRequestV1:
        value = _parse_json(
            raw,
            maximum=4096,
            code="technical_universe_price_page_request_json_invalid",
        )
        result = cls.from_dict(value)
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if result.to_json().encode("utf-8") != encoded:
            _fail("technical_universe_price_page_request_json_noncanonical")
        return result


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceRowV1:
    """一列 exact P01 技術 facts 與同次 verified current-close 投影。"""

    technical_row: DailyMarketTechnicalParentV4Row
    price_fact: DailyMarketTechnicalUniversePriceFactV1
    price_state: Literal["pass", "unknown"]
    row_identity_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.technical_row, DailyMarketTechnicalParentV4Row):
            _fail("technical_universe_price_page_row_invalid")
        if not isinstance(self.price_fact, DailyMarketTechnicalUniversePriceFactV1):
            _fail("technical_universe_price_page_row_invalid")
        if self.price_state not in {"pass", "unknown"}:
            _fail("technical_universe_price_page_row_state_invalid")
        if (
            self.technical_row.stock_code != self.price_fact.stock_code
            or self.technical_row.snapshot_identity_sha256 != self.price_fact.snapshot_identity_sha256
            or self.technical_row.source_identity != self.price_fact.source_identity
            or self.technical_row.latest_feature_date != self.price_fact.observation_date
            or (
                self.price_fact.observation_date is not None
                and self.price_fact.observation_date > self.technical_row.decision_date
            )
            or (self.price_state == "pass" and self.price_fact.status != "known")
            or (self.price_state == "unknown" and self.price_fact.status != "unknown")
        ):
            _fail("technical_universe_price_page_row_source_mismatch")
        if self.row_identity_sha256 != _sha256_json(self._body_without_identity()):
            _fail("technical_universe_price_page_row_identity_mismatch")

    @classmethod
    def create(
        cls,
        *,
        technical_row: DailyMarketTechnicalParentV4Row,
        price_fact: DailyMarketTechnicalUniversePriceFactV1,
        price_state: Literal["pass", "unknown"],
    ) -> DailyMarketTechnicalUniversePriceRowV1:
        provisional = cls.__new__(cls)
        object.__setattr__(provisional, "technical_row", technical_row)
        object.__setattr__(provisional, "price_fact", price_fact)
        object.__setattr__(provisional, "price_state", price_state)
        body = provisional._body_without_identity()
        return cls(
            technical_row=technical_row,
            price_fact=price_fact,
            price_state=price_state,
            row_identity_sha256=_sha256_json(body),
        )

    def _body_without_identity(self) -> dict[str, object]:
        return {
            "schema_version": "daily-market-technical-universe-price-row.v1",
            "technical_row": self.technical_row.to_dict(),
            "price_fact": self.price_fact.to_dict(),
            "price_state": self.price_state,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._body_without_identity(),
            "row_identity_sha256": self.row_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class _PriceCandidateV1:
    fact: DailyMarketTechnicalUniversePriceFactV1
    state: Literal["pass", "unknown"]

    @property
    def stock_code(self) -> str:
        return self.fact.stock_code

    def to_dict(self) -> dict[str, object]:
        return {"state": self.state, "fact": self.fact.to_dict()}


class _IssuedAnchorV1:
    __slots__ = ("_identity_sha256", "_token", "_bindings")
    _identity_sha256: str
    _token: object
    _bindings: tuple[object, ...]

    def __init__(self, identity_sha256: str, bindings: tuple[object, ...]) -> None:
        object.__setattr__(self, "_identity_sha256", identity_sha256)
        object.__setattr__(self, "_token", _ANCHOR_TOKEN)
        object.__setattr__(self, "_bindings", bindings)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("issued price-query anchor is immutable")

    @property
    def identity_sha256(self) -> str:
        return self._identity_sha256

    @property
    def token(self) -> object:
        return self._token

    @property
    def bindings(self) -> tuple[object, ...]:
        return self._bindings


def _new_anchor(identity_sha256: str, *bindings: object) -> _IssuedAnchorV1:
    return _IssuedAnchorV1(identity_sha256, tuple(bindings))


def _validate_anchor(
    anchor: object,
    identity_sha256: str,
    *bindings: object,
    code: str,
) -> None:
    if (
        not isinstance(anchor, _IssuedAnchorV1)
        or anchor.identity_sha256 != identity_sha256
        or anchor.token is not _ANCHOR_TOKEN
        or len(anchor.bindings) != len(bindings)
        or any(saved is not current for saved, current in zip(anchor.bindings, bindings))
    ):
        _fail(code)


def _stream_digest(
    items: Iterable[object],
    *,
    maximum_bytes: int,
    cancel_callback: Callable[[], object] | None = None,
) -> tuple[str, int]:
    digest = hashlib.sha256()
    digest.update(b"[")
    size = 2
    for index, item in enumerate(items):
        if index % 256 == 0:
            _check_cancel(cancel_callback)
        if index:
            digest.update(b",")
            size += 1
        encoded = _canonical_json(item).encode("utf-8")
        size += len(encoded)
        if size > maximum_bytes:
            _fail("technical_universe_price_index_byte_limit")
        digest.update(encoded)
    digest.update(b"]")
    return digest.hexdigest(), size


def _classify_price(
    fact: DailyMarketTechnicalUniversePriceFactV1,
    query: DailyMarketTechnicalUniversePriceQueryV1,
) -> Literal["pass", "fail", "unknown"]:
    if fact.status == "unknown" or fact.close_price is None:
        return "unknown"
    price = fact.close_price
    minimum = query.min_close_price
    maximum = query.max_close_price
    if minimum is not None and (price < minimum or (price == minimum and not query.min_inclusive)):
        return "fail"
    if maximum is not None and (price > maximum or (price == maximum and not query.max_inclusive)):
        return "fail"
    return "pass"


def _operation_payload(
    *,
    source: DailyMarketTechnicalUniversePriceSourceV1,
    query: DailyMarketTechnicalUniversePriceQueryV1,
    base_query_identity_sha256: str,
    selection_identity_sha256: str,
    selection_query_spec_identity_sha256: str,
    counts: DailyMarketTechnicalUniversePriceCountsV1,
    classification_identity_sha256: str,
    ordered_candidates: Sequence[_PriceCandidateV1],
    full_population_complete: bool,
    cancel_callback: Callable[[], object] | None = None,
) -> dict[str, object]:
    ordered_digest, ordered_bytes = _stream_digest(
        (item.to_dict() for item in ordered_candidates),
        maximum_bytes=DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_INDEX_BYTES,
        cancel_callback=cancel_callback,
    )
    if ordered_bytes > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_INDEX_BYTES:
        _fail("technical_universe_price_index_byte_limit")
    ordered_codes_digest, ordered_codes_bytes = _stream_digest(
        (item.stock_code for item in ordered_candidates),
        maximum_bytes=DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_INDEX_BYTES,
        cancel_callback=cancel_callback,
    )
    if ordered_codes_bytes > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_INDEX_BYTES:
        _fail("technical_universe_price_index_byte_limit")
    return {
        "schema_version": "daily-market-technical-universe-price-operation.v1",
        "source_identity_sha256": source.source_identity_sha256,
        "price_index_identity_sha256": source.price_index_identity_sha256,
        "query_identity_sha256": query.query_identity_sha256,
        "base_query_identity_sha256": base_query_identity_sha256,
        "selection_identity_sha256": selection_identity_sha256,
        "selection_query_spec_identity_sha256": selection_query_spec_identity_sha256,
        "classification_identity_sha256": classification_identity_sha256,
        "ordered_match_identity_sha256": ordered_digest,
        "ordered_stock_codes_sha256": ordered_codes_digest,
        "matching_count": len(ordered_candidates),
        "counts": counts.to_dict(),
        "coverage_scope": "all_processed_included_v4",
        "full_n_aggregation": True,
        "full_population_complete": full_population_complete,
        "full_market_claim": False,
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
        "price_method_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_METHOD_VERSION,
    }


def _session_identity_payload(
    source: DailyMarketTechnicalUniversePriceSourceV1,
) -> dict[str, object]:
    return {
        "schema_version": "daily-market-technical-universe-price-session.v1",
        "source_identity_sha256": source.source_identity_sha256,
        "p01_read_session_identity_sha256": source.p01_read_session_identity_sha256,
        "price_index_identity_sha256": source.price_index_identity_sha256,
        "price_index_bytes": source.price_index_bytes,
    }


def _result_identity_payload(
    *,
    query: DailyMarketTechnicalUniversePriceQueryV1,
    source: DailyMarketTechnicalUniversePriceSourceV1,
    p01_selection: DailyMarketTechnicalUniverseV4ReadSelection,
    price_counts: DailyMarketTechnicalUniversePriceCountsV1,
    operation_identity_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": "daily-market-technical-universe-price-result.v1",
        "query_identity_sha256": query.query_identity_sha256,
        "source_identity_sha256": source.source_identity_sha256,
        "p01_read_session_identity_sha256": source.p01_read_session_identity_sha256,
        "selection_identity_sha256": p01_selection.selection_identity_sha256,
        "selection_query_spec_identity_sha256": p01_selection.query_spec_identity_sha256,
        "operation_identity_sha256": operation_identity_sha256,
        "source_counts": source.counts.to_dict(),
        "price_counts": price_counts.to_dict(),
        "exclusion_reasons_sha256": source.exclusion_reasons_sha256,
        "coverage_scope": "all_processed_included_v4",
        "full_n_aggregation": True,
        "full_population_complete": (
            source.receipt_status == "complete" and source.counts.pending_count == 0
        ),
        "full_market_claim": False,
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }


def _page_identity_payload(
    *,
    request: DailyMarketTechnicalUniversePricePageRequestV1,
    result_identity_sha256: str,
    source_counts: DailyMarketTechnicalUniverseV4Counts,
    price_counts: DailyMarketTechnicalUniversePriceCountsV1,
    matching_count: int,
    page_count: int,
    rows: tuple[DailyMarketTechnicalUniversePriceRowV1, ...],
    full_population_complete: bool,
) -> dict[str, object]:
    rows_digest, _rows_bytes = _stream_digest(
        (row.to_dict() for row in rows),
        maximum_bytes=DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_BYTES,
    )
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_PAGE_V1_SCHEMA,
        "request": request.to_dict(),
        "result_identity_sha256": result_identity_sha256,
        "source_counts": source_counts.to_dict(),
        "price_counts": price_counts.to_dict(),
        "matching_count": matching_count,
        "page_count": page_count,
        "rows_identity_sha256": rows_digest,
        "row_count": len(rows),
        "coverage_scope": "all_processed_included_v4",
        "full_n_aggregation": True,
        "full_population_complete": full_population_complete,
        "full_market_claim": False,
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }


def _same_p01_row_and_fact(
    row: DailyMarketTechnicalParentV4Row,
    fact: DailyMarketTechnicalUniversePriceFactV1,
    *,
    decision_date: date,
    rule_keys: tuple[str, ...],
) -> bool:
    row_rule_keys = tuple(rule.key for rule in row.rules)
    return (
        row.stock_code == fact.stock_code
        and row.decision_date == decision_date
        and row.snapshot_identity_sha256 == fact.snapshot_identity_sha256
        and row.source_identity == fact.source_identity
        and row.latest_feature_date == fact.observation_date
        and (row.latest_feature_date is None or row.latest_feature_date <= decision_date)
        and row.raw_row_count >= 0
        and row.has_missing_data is (row.raw_row_count == 0)
        and row_rule_keys == rule_keys
    )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePricePageV1:
    """全域排序後的一頁；未知值在升冪與降冪時都留在尾端。"""

    request: DailyMarketTechnicalUniversePricePageRequestV1
    result_identity_sha256: str
    source_counts: DailyMarketTechnicalUniverseV4Counts
    price_counts: DailyMarketTechnicalUniversePriceCountsV1
    matching_count: int
    page_count: int
    rows: tuple[DailyMarketTechnicalUniversePriceRowV1, ...]
    page_identity_sha256: str
    full_population_complete: bool
    _anchor: _IssuedAnchorV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _PAGE_SEAL:
            _fail("technical_universe_price_page_not_reader_issued")
        if not isinstance(self.request, DailyMarketTechnicalUniversePricePageRequestV1):
            _fail("technical_universe_price_page_invalid")
        if not isinstance(self.source_counts, DailyMarketTechnicalUniverseV4Counts):
            _fail("technical_universe_price_page_invalid")
        if not isinstance(self.price_counts, DailyMarketTechnicalUniversePriceCountsV1):
            _fail("technical_universe_price_page_invalid")
        expected_pages = (self.matching_count + self.request.page_size - 1) // self.request.page_size
        start = self.request.page_index * self.request.page_size
        expected_rows = max(0, min(self.request.page_size, self.matching_count - start))
        if (
            not _is_sha256(self.result_identity_sha256)
            or type(self.matching_count) is not int
            or self.matching_count < 0
            or type(self.page_count) is not int
            or self.page_count != expected_pages
            or type(self.full_population_complete) is not bool
            or not isinstance(self.rows, tuple)
            or len(self.rows) != expected_rows
            or self.matching_count != self.price_counts.matching_count
            or any(not isinstance(row, DailyMarketTechnicalUniversePriceRowV1) for row in self.rows)
            or len({row.technical_row.stock_code for row in self.rows}) != len(self.rows)
        ):
            _fail("technical_universe_price_page_invalid")
        expected = _sha256_json(_page_identity_payload(
            request=self.request,
            result_identity_sha256=self.result_identity_sha256,
            source_counts=self.source_counts,
            price_counts=self.price_counts,
            matching_count=self.matching_count,
            page_count=self.page_count,
            rows=self.rows,
            full_population_complete=self.full_population_complete,
        ))
        if self.page_identity_sha256 != expected:
            _fail("technical_universe_price_page_identity_mismatch")
        _validate_anchor(
            self._anchor,
            self.page_identity_sha256,
            self.request,
            self.result_identity_sha256,
            self.source_counts,
            self.price_counts,
            self.rows,
            code="technical_universe_price_page_not_reader_issued",
        )

    @property
    def is_complete(self) -> bool:
        return self.full_population_complete

    def to_dict(self) -> dict[str, object]:
        payload = {
            **_page_identity_payload(
                request=self.request,
                result_identity_sha256=self.result_identity_sha256,
                source_counts=self.source_counts,
                price_counts=self.price_counts,
                matching_count=self.matching_count,
                page_count=self.page_count,
                rows=self.rows,
                full_population_complete=self.full_population_complete,
            ),
            "page_identity_sha256": self.page_identity_sha256,
            "rows": [row.to_dict() for row in self.rows],
        }
        if len(_canonical_json(payload).encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_BYTES:
            _fail("technical_universe_price_page_byte_limit")
        return payload

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceReadSessionV1:
    """一個 exact store graph 讀取與同次 verified close projection。"""

    source: DailyMarketTechnicalUniversePriceSourceV1
    _p01_session: DailyMarketTechnicalUniverseV4ReadSession = field(repr=False)
    _state: DailyMarketTechnicalUniverseV4VerifiedState = field(repr=False)
    _facts: tuple[DailyMarketTechnicalUniversePriceFactV1, ...] = field(repr=False)
    _fact_codes: tuple[str, ...] = field(repr=False)
    read_session_identity_sha256: str
    _anchor: _IssuedAnchorV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SESSION_SEAL:
            _fail("technical_universe_price_read_session_not_reader_issued")
        if (
            not isinstance(self.source, DailyMarketTechnicalUniversePriceSourceV1)
            or not isinstance(self._p01_session, DailyMarketTechnicalUniverseV4ReadSession)
            or not isinstance(self._state, DailyMarketTechnicalUniverseV4VerifiedState)
            or not isinstance(self._facts, tuple)
            or not isinstance(self._fact_codes, tuple)
            or tuple(item.stock_code for item in self._facts) != self._fact_codes
            or self._fact_codes != tuple(sorted(set(self._fact_codes)))
            or len(self._facts) != self.source.counts.processed_count
            or self.source.p01_read_session_identity_sha256
            != self._p01_session.read_session_identity_sha256
            or self.source.counts != self._state.counts
        ):
            _fail("technical_universe_price_read_session_invalid")
        expected = _sha256_json(_session_identity_payload(self.source))
        if self.read_session_identity_sha256 != expected:
            _fail("technical_universe_price_read_session_identity_mismatch")
        _validate_anchor(
            self._anchor,
            self.read_session_identity_sha256,
            self.source,
            self._p01_session,
            self._state,
            self._facts,
            self._fact_codes,
            code="technical_universe_price_read_session_not_reader_issued",
        )

    @property
    def source_counts(self) -> DailyMarketTechnicalUniverseV4Counts:
        return self.source.counts

    @property
    def pending_stock_codes(self) -> tuple[str, ...]:
        included = self._state.plan.cohort.included_stock_codes
        return included[self._state.counts.processed_count :]

    @property
    def missing_data_stock_codes(self) -> tuple[str, ...]:
        return self._state.missing_data_stock_codes

    @property
    def missing_data_pending_count(self) -> int:
        return self.source.counts.missing_data_pending_count

    @property
    def excluded_stock_codes(self) -> tuple[str, ...]:
        return self._state.plan.cohort.excluded_stock_codes

    @property
    def exclusion_reasons(self) -> tuple[tuple[str, str], ...]:
        return self._state.plan.cohort.exclusion_reasons

    @property
    def population_complete(self) -> bool:
        return self.source.receipt_status == "complete" and self.source.counts.pending_count == 0

    def _validate_issued(self) -> None:
        _validate_anchor(
            self._anchor,
            self.read_session_identity_sha256,
            self.source,
            self._p01_session,
            self._state,
            self._facts,
            self._fact_codes,
            code="technical_universe_price_read_session_not_reader_issued",
        )

    def _fact_for_code(self, stock_code: str) -> DailyMarketTechnicalUniversePriceFactV1:
        index = bisect_left(self._fact_codes, stock_code)
        if index >= len(self._fact_codes) or self._fact_codes[index] != stock_code:
            _fail("technical_universe_price_processed_stock_fact_missing")
        return self._facts[index]

    def create_query(
        self,
        *,
        rule_state_filters: Sequence[DailyMarketTechnicalRuleStateFilterV4] = (),
        combine_mode: Literal["AND", "OR"] = "AND",
        technical_stock_filter: Sequence[str] = (),
        eligible_stock_codes: Sequence[str] | None = None,
        min_close_price: Decimal | None = None,
        min_inclusive: bool = True,
        max_close_price: Decimal | None = None,
        max_inclusive: bool = True,
        unknown_price_policy: Literal["include", "exclude", "only"] = "include",
        descending: bool = False,
    ) -> DailyMarketTechnicalUniversePriceQueryV1:
        self._validate_issued()
        return DailyMarketTechnicalUniversePriceQueryV1.create(
            source=self.source,
            rule_state_filters=rule_state_filters,
            combine_mode=combine_mode,
            technical_stock_filter=technical_stock_filter,
            eligible_stock_codes=eligible_stock_codes,
            min_close_price=min_close_price,
            min_inclusive=min_inclusive,
            max_close_price=max_close_price,
            max_inclusive=max_inclusive,
            unknown_price_policy=unknown_price_policy,
            descending=descending,
        )

    def matches_query(self, query: DailyMarketTechnicalUniversePriceQueryV1) -> bool:
        return (
            isinstance(query, DailyMarketTechnicalUniversePriceQueryV1)
            and query.source.source_identity_sha256 == self.source.source_identity_sha256
        )

    def execute(
        self,
        query: DailyMarketTechnicalUniversePriceQueryV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceResultV1:
        self._validate_issued()
        if not self.matches_query(query):
            _fail("technical_universe_price_query_source_mismatch")
        _check_cancel(cancel_callback)
        try:
            base_query = self._p01_session.create_query(
                rule_state_filters=query.rule_state_filters,
                combine_mode=query.combine_mode,
                stock_filter=query.technical_stock_filter,
                sort_key="stock_code",
                descending=False,
                page_index=0,
                page_size=DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_SIZE,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )
            selection = self._p01_session.select_stock_codes(
                base_query,
                eligible_stock_codes=query.eligible_stock_codes,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )
        except DailyMarketTechnicalUniverseV4QueryError as exc:
            raise DailyMarketTechnicalUniversePriceQueryV1Error(exc.code, str(exc)) from exc
        if not isinstance(selection, DailyMarketTechnicalUniverseV4ReadSelection):
            _fail("technical_universe_price_selection_invalid")
        if selection.stock_codes != tuple(sorted(set(selection.stock_codes))):
            _fail("technical_universe_price_base_selection_order_invalid")
        _check_cancel(cancel_callback)
        classification_states: list[Literal["pass", "fail", "unknown"]] = []
        candidates: list[_PriceCandidateV1] = []
        pass_count = 0
        fail_count = 0
        unknown_count = 0
        for index, stock_code in enumerate(selection.stock_codes):
            if index % 256 == 0:
                _check_cancel(cancel_callback)
            fact = self._fact_for_code(stock_code)
            state = _classify_price(fact, query)
            classification_states.append(state)
            if state == "pass":
                pass_count += 1
                if query.unknown_price_policy != "only":
                    candidates.append(_PriceCandidateV1(fact=fact, state="pass"))
            elif state == "fail":
                fail_count += 1
            else:
                unknown_count += 1
                if query.unknown_price_policy != "exclude":
                    candidates.append(_PriceCandidateV1(fact=fact, state="unknown"))
        classification_identity, classification_bytes = _stream_digest(
            (
                {"stock_code": stock_code, "state": state}
                for stock_code, state in zip(selection.stock_codes, classification_states)
            ),
            maximum_bytes=DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_INDEX_BYTES,
            cancel_callback=cancel_callback,
        )
        if classification_bytes > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_INDEX_BYTES:
            _fail("technical_universe_price_index_byte_limit")
        counts = DailyMarketTechnicalUniversePriceCountsV1(
            base_matching_count=selection.matching_count,
            pass_count=pass_count,
            fail_count=fail_count,
            unknown_count=unknown_count,
            matching_count=(
                pass_count + unknown_count
                if query.unknown_price_policy == "include"
                else pass_count
                if query.unknown_price_policy == "exclude"
                else unknown_count
            ),
        )
        known: list[_PriceCandidateV1] = []
        unknown: list[_PriceCandidateV1] = []
        for index, item in enumerate(candidates):
            if index % 256 == 0:
                _check_cancel(cancel_callback)
            (known if item.state == "pass" else unknown).append(item)
        key_checks = 0

        def price_sort_key(item: _PriceCandidateV1) -> Decimal:
            nonlocal key_checks
            key_checks += 1
            if key_checks % 256 == 0:
                _check_cancel(cancel_callback)
            price = item.fact.close_price
            if price is None:
                _fail("technical_universe_price_sort_candidate_invalid")
            return price

        known.sort(key=price_sort_key, reverse=query.descending)
        ordered_candidates = tuple((*known, *unknown))
        _check_cancel(cancel_callback)
        operation_payload = _operation_payload(
            source=self.source,
            query=query,
            base_query_identity_sha256=base_query.query_identity_sha256,
            selection_identity_sha256=selection.selection_identity_sha256,
            selection_query_spec_identity_sha256=selection.query_spec_identity_sha256,
            counts=counts,
            classification_identity_sha256=classification_identity,
            ordered_candidates=ordered_candidates,
            full_population_complete=self.population_complete,
            cancel_callback=cancel_callback,
        )
        operation_json = _canonical_json(operation_payload)
        operation_identity = _sha256_bytes(operation_json.encode("utf-8"))
        result_identity = _sha256_json(_result_identity_payload(
            query=query,
            source=self.source,
            p01_selection=selection,
            price_counts=counts,
            operation_identity_sha256=operation_identity,
        ))
        _check_cancel(cancel_callback)
        result = DailyMarketTechnicalUniversePriceResultV1(
            query=query,
            _session=self,
            source_counts=self.source_counts,
            price_counts=counts,
            _selection=selection,
            _ordered_candidates=ordered_candidates,
            base_query_identity_sha256=base_query.query_identity_sha256,
            classification_identity_sha256=classification_identity,
            _operation_payload_json=operation_json,
            operation_identity_sha256=operation_identity,
            result_identity_sha256=result_identity,
            _anchor=_new_anchor(
                result_identity,
                query,
                self,
                self.source_counts,
                counts,
                selection,
                ordered_candidates,
                operation_json,
                base_query.query_identity_sha256,
                classification_identity,
            ),
            _seal=_RESULT_SEAL,
        )
        _check_cancel(cancel_callback)
        return result


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceResultV1:
    """一次完整技術＋價格條件運算；只保存緊湊排序候選，不保存全部原始 snapshot。"""

    query: DailyMarketTechnicalUniversePriceQueryV1
    _session: DailyMarketTechnicalUniversePriceReadSessionV1 = field(repr=False)
    source_counts: DailyMarketTechnicalUniverseV4Counts
    price_counts: DailyMarketTechnicalUniversePriceCountsV1
    _selection: DailyMarketTechnicalUniverseV4ReadSelection = field(repr=False)
    _ordered_candidates: tuple[_PriceCandidateV1, ...] = field(repr=False)
    base_query_identity_sha256: str
    classification_identity_sha256: str
    _operation_payload_json: str = field(repr=False)
    operation_identity_sha256: str
    result_identity_sha256: str
    _anchor: _IssuedAnchorV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _RESULT_SEAL:
            _fail("technical_universe_price_result_not_reader_issued")
        if (
            not isinstance(self.query, DailyMarketTechnicalUniversePriceQueryV1)
            or not isinstance(self._session, DailyMarketTechnicalUniversePriceReadSessionV1)
            or not isinstance(self.source_counts, DailyMarketTechnicalUniverseV4Counts)
            or not isinstance(self.price_counts, DailyMarketTechnicalUniversePriceCountsV1)
            or not isinstance(self._selection, DailyMarketTechnicalUniverseV4ReadSelection)
            or not isinstance(self._ordered_candidates, tuple)
            or len(self._ordered_candidates) != self.price_counts.matching_count
            or tuple(item.stock_code for item in self._ordered_candidates)
            != tuple(dict.fromkeys(item.stock_code for item in self._ordered_candidates))
            or not self._session.matches_query(self.query)
            or self.source_counts != self._session.source_counts
            or not _is_sha256(self.base_query_identity_sha256)
            or not _is_sha256(self.classification_identity_sha256)
            or not isinstance(self._operation_payload_json, str)
            or _sha256_bytes(self._operation_payload_json.encode("utf-8"))
            != self.operation_identity_sha256
        ):
            _fail("technical_universe_price_result_invalid")
        expected = _sha256_json(_result_identity_payload(
            query=self.query,
            source=self.query.source,
            p01_selection=self._selection,
            price_counts=self.price_counts,
            operation_identity_sha256=self.operation_identity_sha256,
        ))
        if self.result_identity_sha256 != expected:
            _fail("technical_universe_price_result_identity_mismatch")
        _validate_anchor(
            self._anchor,
            self.result_identity_sha256,
            self.query,
            self._session,
            self.source_counts,
            self.price_counts,
            self._selection,
            self._ordered_candidates,
            self._operation_payload_json,
            self.base_query_identity_sha256,
            self.classification_identity_sha256,
            code="technical_universe_price_result_not_reader_issued",
        )

    @property
    def matching_count(self) -> int:
        return self.price_counts.matching_count

    @property
    def pending_stock_codes(self) -> tuple[str, ...]:
        return self._session.pending_stock_codes

    @property
    def missing_data_stock_codes(self) -> tuple[str, ...]:
        return self._session.missing_data_stock_codes

    @property
    def excluded_stock_codes(self) -> tuple[str, ...]:
        return self._session.excluded_stock_codes

    @property
    def exclusion_reasons(self) -> tuple[tuple[str, str], ...]:
        return self._session.exclusion_reasons

    @property
    def full_population_complete(self) -> bool:
        return self._session.population_complete

    @property
    def operation_identity(self) -> dict[str, object]:
        value = json.loads(self._operation_payload_json)
        if not isinstance(value, dict):
            _fail("technical_universe_price_result_operation_invalid")
        return value

    def _validate_issued(self) -> None:
        self._session._validate_issued()
        _validate_anchor(
            self._anchor,
            self.result_identity_sha256,
            self.query,
            self._session,
            self.source_counts,
            self.price_counts,
            self._selection,
            self._ordered_candidates,
            self._operation_payload_json,
            self.base_query_identity_sha256,
            self.classification_identity_sha256,
            code="technical_universe_price_result_not_reader_issued",
        )

    def _validate_request(self, request: DailyMarketTechnicalUniversePricePageRequestV1) -> None:
        self._validate_issued()
        if not isinstance(request, DailyMarketTechnicalUniversePricePageRequestV1):
            _fail("technical_universe_price_page_request_invalid")
        if (
            request.query_identity_sha256 != self.query.query_identity_sha256
            or request.operation_identity_sha256 != self.operation_identity_sha256
            or request.selection_identity_sha256 != self._selection.selection_identity_sha256
        ):
            _fail("technical_universe_price_page_request_source_mismatch")
        expected_page_count = (self.matching_count + request.page_size - 1) // request.page_size
        if (expected_page_count == 0 and request.page_index != 0) or (
            expected_page_count > 0 and request.page_index >= expected_page_count
        ):
            _fail("technical_universe_price_page_not_found")

    def create_page_request(
        self,
        page_index: int,
        *,
        page_size: int = 50,
    ) -> DailyMarketTechnicalUniversePricePageRequestV1:
        self._validate_issued()
        request = DailyMarketTechnicalUniversePricePageRequestV1.create(
            query_identity_sha256=self.query.query_identity_sha256,
            operation_identity_sha256=self.operation_identity_sha256,
            selection_identity_sha256=self._selection.selection_identity_sha256,
            page_index=page_index,
            page_size=page_size,
        )
        self._validate_request(request)
        return request

    def read_page(
        self,
        request: DailyMarketTechnicalUniversePricePageRequestV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePricePageV1:
        self._validate_request(request)
        _check_cancel(cancel_callback)
        start = request.page_index * request.page_size
        chosen = self._ordered_candidates[start : start + request.page_size]
        requested_codes = tuple(item.stock_code for item in chosen)
        try:
            materialized = self._session._p01_session.materialize_selected_stock_codes(
                self._selection,
                explicit_stock_codes=requested_codes,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )
        except DailyMarketTechnicalUniverseV4QueryError as exc:
            raise DailyMarketTechnicalUniversePriceQueryV1Error(exc.code, str(exc)) from exc
        _check_cancel(cancel_callback)
        if (
            materialized.read_session_identity_sha256
            != self.query.source.p01_read_session_identity_sha256
            or materialized.selection_identity_sha256
            != self._selection.selection_identity_sha256
            or materialized.query_spec_identity_sha256
            != self._selection.query_spec_identity_sha256
            or materialized.requested_stock_codes != requested_codes
        ):
            _fail("technical_universe_price_page_materialization_mismatch")
        candidates_by_code = {item.stock_code: item for item in chosen}
        rows: list[DailyMarketTechnicalUniversePriceRowV1] = []
        for index, technical_row in enumerate(materialized.rows):
            if index % 32 == 0:
                _check_cancel(cancel_callback)
            candidate = candidates_by_code.get(technical_row.stock_code)
            if candidate is None or not _same_p01_row_and_fact(
                technical_row,
                candidate.fact,
                decision_date=self.query.source.decision_date,
                rule_keys=self.query.source.method_rule_keys,
            ):
                _fail("technical_universe_price_page_row_source_mismatch")
            rows.append(DailyMarketTechnicalUniversePriceRowV1.create(
                technical_row=technical_row,
                price_fact=candidate.fact,
                price_state=candidate.state,
            ))
        row_tuple = tuple(rows)
        if tuple(row.technical_row.stock_code for row in row_tuple) != requested_codes:
            _fail("technical_universe_price_page_materialization_order_mismatch")
        page_count = (self.matching_count + request.page_size - 1) // request.page_size
        page_identity = _sha256_json(_page_identity_payload(
            request=request,
            result_identity_sha256=self.result_identity_sha256,
            source_counts=self.source_counts,
            price_counts=self.price_counts,
            matching_count=self.matching_count,
            page_count=page_count,
            rows=row_tuple,
            full_population_complete=self.full_population_complete,
        ))
        _check_cancel(cancel_callback)
        page = DailyMarketTechnicalUniversePricePageV1(
            request=request,
            result_identity_sha256=self.result_identity_sha256,
            source_counts=self.source_counts,
            price_counts=self.price_counts,
            matching_count=self.matching_count,
            page_count=page_count,
            rows=row_tuple,
            page_identity_sha256=page_identity,
            full_population_complete=self.full_population_complete,
            _anchor=_new_anchor(
                page_identity,
                request,
                self.result_identity_sha256,
                self.source_counts,
                self.price_counts,
                row_tuple,
            ),
            _seal=_PAGE_SEAL,
        )
        _check_cancel(cancel_callback)
        return page

    def read_stock_snapshot(
        self,
        request: DailyMarketTechnicalUniversePricePageRequestV1,
        stock_code: str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceStockV1:
        self._validate_request(request)
        if not isinstance(stock_code, str) or _STOCK_CODE_RE.fullmatch(stock_code) is None:
            _fail("technical_universe_price_stock_code_invalid")
        _check_cancel(cancel_callback)
        start = request.page_index * request.page_size
        chosen = self._ordered_candidates[start : start + request.page_size]
        candidate = next((item for item in chosen if item.stock_code == stock_code), None)
        if candidate is None:
            _fail("technical_universe_price_stock_not_in_origin_page")
        selection_codes = self._selection.stock_codes
        selection_index = bisect_left(selection_codes, stock_code)
        if selection_index >= len(selection_codes) or selection_codes[selection_index] != stock_code:
            _fail("technical_universe_price_stock_not_in_base_selection")
        base_page_index = selection_index // DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_SIZE
        try:
            _base_query, segment_index, parent_reference, snapshot = (
                self._session._p01_session.read_selection_stock_snapshot(
                    self._selection,
                    stock_code,
                    page_index=base_page_index,
                    page_size=DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_SIZE,
                    cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
                )
            )
        except DailyMarketTechnicalUniverseV4QueryError as exc:
            raise DailyMarketTechnicalUniversePriceQueryV1Error(exc.code, str(exc)) from exc
        _check_cancel(cancel_callback)
        fact = _price_fact_from_snapshot(
            snapshot,
            decision_date=self.query.source.decision_date,
        )
        if fact.to_dict() != candidate.fact.to_dict():
            _fail("technical_universe_price_stock_snapshot_changed")
        technical_row = _parent_row_from_snapshot(snapshot)
        if not _same_p01_row_and_fact(
            technical_row,
            fact,
            decision_date=self.query.source.decision_date,
            rule_keys=self.query.source.method_rule_keys,
        ):
            _fail("technical_universe_price_stock_row_source_mismatch")
        row = DailyMarketTechnicalUniversePriceRowV1.create(
            technical_row=technical_row,
            price_fact=fact,
            price_state=candidate.state,
        )
        stock_body = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_STOCK_V1_SCHEMA,
            "result_identity_sha256": self.result_identity_sha256,
            "request": request.to_dict(),
            "stock_code": stock_code,
            "row_identity_sha256": row.row_identity_sha256,
            "segment_index": segment_index,
            "parent_reference": parent_reference.to_dict(),
            "snapshot_identity_sha256": snapshot.snapshot_identity_sha256,
            "source_identity": snapshot.source_identity,
        }
        stock_identity = _sha256_json(stock_body)
        _check_cancel(cancel_callback)
        stock = DailyMarketTechnicalUniversePriceStockV1(
            request=request,
            result_identity_sha256=self.result_identity_sha256,
            stock_code=stock_code,
            row=row,
            segment_index=segment_index,
            parent_reference=parent_reference,
            snapshot=snapshot,
            stock_identity_sha256=stock_identity,
            _anchor=_new_anchor(
                stock_identity,
                request,
                self.result_identity_sha256,
                row,
                parent_reference,
                snapshot,
            ),
            _seal=_STOCK_SEAL,
        )
        _check_cancel(cancel_callback)
        return stock

    def to_dict(self) -> dict[str, object]:
        self._validate_issued()
        return {
            "schema_version": "daily-market-technical-universe-price-result.v1",
            "query": self.query.to_dict(),
            "source_counts": self.source_counts.to_dict(),
            "price_counts": self.price_counts.to_dict(),
            "operation_identity_sha256": self.operation_identity_sha256,
            "result_identity_sha256": self.result_identity_sha256,
            "pending_count": len(self.pending_stock_codes),
            "missing_data_count": len(self.missing_data_stock_codes),
            "missing_data_pending_count": self._session.missing_data_pending_count,
            "excluded_count": len(self.excluded_stock_codes),
            "exclusion_reasons_sha256": self.query.source.exclusion_reasons_sha256,
            "full_population_complete": self.full_population_complete,
            "coverage_scope": "all_processed_included_v4",
            "full_n_aggregation": True,
            "full_market_claim": False,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }

    def to_json(self) -> str:
        raw = _canonical_json(self.to_dict())
        if len(raw.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_BYTES:
            _fail("technical_universe_price_result_byte_limit")
        return raw


def _parent_row_from_snapshot(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
) -> DailyMarketTechnicalParentV4Row:
    """把 exact snapshot 投影為既有 public parent row 欄位，不新增金融計算。"""

    current = snapshot.current_session
    return DailyMarketTechnicalParentV4Row(
        stock_code=snapshot.stock_code,
        decision_date=snapshot.decision_date,
        snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        source_identity=snapshot.source_identity,
        raw_row_count=len(snapshot.rows),
        observed_prefix_contiguous=snapshot.observed_prefix_contiguous,
        latest_feature_date=current.feature_date if current is not None else None,
        rules=snapshot.rules,
    )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceStockV1:
    """一個原 F07 結果頁內的 exact 個股重開與來源 reference。"""

    request: DailyMarketTechnicalUniversePricePageRequestV1
    result_identity_sha256: str
    stock_code: str
    row: DailyMarketTechnicalUniversePriceRowV1
    segment_index: int
    parent_reference: DailyMarketTechnicalUniverseV4ParentReceiptReference
    snapshot: DailyMarketTechnicalFeatureSnapshotV4
    stock_identity_sha256: str
    _anchor: _IssuedAnchorV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _STOCK_SEAL:
            _fail("technical_universe_price_stock_not_reader_issued")
        if (
            not isinstance(self.request, DailyMarketTechnicalUniversePricePageRequestV1)
            or not _is_sha256(self.result_identity_sha256)
            or not isinstance(self.stock_code, str)
            or _STOCK_CODE_RE.fullmatch(self.stock_code) is None
            or not isinstance(self.row, DailyMarketTechnicalUniversePriceRowV1)
            or type(self.segment_index) is not int
            or self.segment_index < 0
            or not isinstance(self.parent_reference, DailyMarketTechnicalUniverseV4ParentReceiptReference)
            or not isinstance(self.snapshot, DailyMarketTechnicalFeatureSnapshotV4)
            or self.snapshot.stock_code != self.stock_code
            or self.row.technical_row.stock_code != self.stock_code
            or self.row.price_fact.stock_code != self.stock_code
            or self.snapshot.snapshot_identity_sha256 != self.row.price_fact.snapshot_identity_sha256
            or self.snapshot.source_identity != self.row.price_fact.source_identity
        ):
            _fail("technical_universe_price_stock_invalid")
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_STOCK_V1_SCHEMA,
            "result_identity_sha256": self.result_identity_sha256,
            "request": self.request.to_dict(),
            "stock_code": self.stock_code,
            "row_identity_sha256": self.row.row_identity_sha256,
            "segment_index": self.segment_index,
            "parent_reference": self.parent_reference.to_dict(),
            "snapshot_identity_sha256": self.snapshot.snapshot_identity_sha256,
            "source_identity": self.snapshot.source_identity,
        }
        if self.stock_identity_sha256 != _sha256_json(body):
            _fail("technical_universe_price_stock_identity_mismatch")
        _validate_anchor(
            self._anchor,
            self.stock_identity_sha256,
            self.request,
            self.result_identity_sha256,
            self.row,
            self.parent_reference,
            self.snapshot,
            code="technical_universe_price_stock_not_reader_issued",
        )

    def to_dict(self) -> dict[str, object]:
        _validate_anchor(
            self._anchor,
            self.stock_identity_sha256,
            self.request,
            self.result_identity_sha256,
            self.row,
            self.parent_reference,
            self.snapshot,
            code="technical_universe_price_stock_not_reader_issued",
        )
        payload = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_STOCK_V1_SCHEMA,
            "result_identity_sha256": self.result_identity_sha256,
            "request": self.request.to_dict(),
            "stock_code": self.stock_code,
            "row": self.row.to_dict(),
            "segment_index": self.segment_index,
            "parent_reference": self.parent_reference.to_dict(),
            "snapshot": self.snapshot.to_dict(),
            "stock_identity_sha256": self.stock_identity_sha256,
        }
        if len(_canonical_json(payload).encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_STOCK_BYTES:
            _fail("technical_universe_price_stock_byte_limit")
        return payload


def open_daily_market_technical_universe_price_read_session_v1(
    *,
    store_output_root: str | Path,
    generation_identity_sha256: str,
    plan_identity_sha256: str,
    plan_sha256: str,
    receipt_identity_sha256: str,
    receipt_sha256: str,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalUniversePriceReadSessionV1:
    """同一次 strict graph callback 建立 P01 session 與收盤價 compact projection。"""

    _check_cancel(cancel_callback)
    try:
        reader = DailyMarketTechnicalUniverseV4StoreReader(store_output_root)
        root = reader.output_root
        builder = DailyMarketTechnicalUniverseV4ReadSessionBuilder(
            store_output_root=root,
            generation_identity_sha256=generation_identity_sha256,
            plan_identity_sha256=plan_identity_sha256,
            plan_sha256=plan_sha256,
            receipt_identity_sha256=receipt_identity_sha256,
            receipt_sha256=receipt_sha256,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
    except DailyMarketTechnicalUniverseV4StoreError as exc:
        raise DailyMarketTechnicalUniversePriceQueryV1Error(exc.code, str(exc)) from exc
    facts_by_code: dict[str, DailyMarketTechnicalUniversePriceFactV1] = {}
    callback_count = 0

    def consume_parent(
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        nonlocal callback_count
        try:
            _check_cancel(cancel_callback)
            if type(segment_index) is not int or segment_index != callback_count:
                _fail("technical_universe_price_segment_order_invalid")
            if not isinstance(parent_read, DailyMarketTechnicalParentCaptureV4VerifiedRead):
                _fail("technical_universe_price_parent_read_invalid")
            builder.consume_verified_parent(segment_index, parent_read)
            for batch in parent_read.verified_batches:
                _check_cancel(cancel_callback)
                if not isinstance(batch, DailyMarketTechnicalBatchArtifactV4):
                    _fail("technical_universe_price_parent_batch_invalid")
                snapshot_codes = tuple(snapshot.stock_code for snapshot in batch.snapshots)
                if (
                    not batch.expected_stock_codes
                    or tuple(sorted(set(snapshot_codes))) != batch.expected_stock_codes
                    or len(snapshot_codes) != len(set(snapshot_codes))
                ):
                    _fail("technical_universe_price_parent_batch_membership_invalid")
                for row_index, snapshot in enumerate(batch.snapshots):
                    if row_index % 32 == 0:
                        _check_cancel(cancel_callback)
                    if (
                        snapshot.decision_date != batch.decision_date
                        or snapshot.source_clock_sha256 != batch.source_clock_identity_sha256
                        or snapshot.method_contracts_sha256 != batch.method_contract_sha256
                        or snapshot.stock_code not in batch.expected_stock_codes
                    ):
                        _fail("technical_universe_price_parent_snapshot_identity_mismatch")
                    if snapshot.stock_code in facts_by_code:
                        _fail("technical_universe_price_duplicate_processed_stock")
                    facts_by_code[snapshot.stock_code] = _price_fact_from_snapshot(
                        snapshot,
                        decision_date=batch.decision_date,
                    )
                    if len(facts_by_code) > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_STOCKS:
                        _fail("technical_universe_price_stock_count_limit")
            callback_count += 1
        except DailyMarketTechnicalUniverseV4StoreError:
            raise
        except DailyMarketTechnicalUniversePriceQueryV1Error as exc:
            # StoreReader 只會原樣保留自家的 typed error；跨 callback 維持 F07 錯誤碼。
            raise DailyMarketTechnicalUniverseV4StoreError(exc.code, str(exc)) from exc

    try:
        state = reader.read_exact_with_verified_parent_callback(
            generation_identity_sha256,
            plan_identity_sha256,
            receipt_identity_sha256,
            expected_receipt_sha256=receipt_sha256,
            expected_plan_sha256=plan_sha256,
            parent_verified_callback=consume_parent,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
    except DailyMarketTechnicalUniverseV4StoreError as exc:
        raise DailyMarketTechnicalUniversePriceQueryV1Error(exc.code, str(exc)) from exc
    _check_cancel(cancel_callback)
    if len(facts_by_code) != state.counts.processed_count:
        _fail("technical_universe_price_processed_stock_count_mismatch")
    facts = tuple(facts_by_code[code] for code in sorted(facts_by_code))
    fact_codes = tuple(fact.stock_code for fact in facts)
    price_index_identity, price_index_bytes = _stream_digest(
        (fact.to_dict() for fact in facts),
        maximum_bytes=DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_INDEX_BYTES,
        cancel_callback=cancel_callback,
    )
    _check_cancel(cancel_callback)
    try:
        p01_session = builder.build_verified_session(root=root, state=state)
    except DailyMarketTechnicalUniverseV4QueryError as exc:
        raise DailyMarketTechnicalUniversePriceQueryV1Error(exc.code, str(exc)) from exc
    _check_cancel(cancel_callback)
    source = _source_from_verified_state(
        store_output_root=str(root),
        state=state,
        plan_sha256=plan_sha256,
        receipt_sha256=receipt_sha256,
        p01_session=p01_session,
        price_index_identity_sha256=price_index_identity,
        price_index_bytes=price_index_bytes,
    )
    session_identity = _sha256_json(_session_identity_payload(source))
    _check_cancel(cancel_callback)
    session = DailyMarketTechnicalUniversePriceReadSessionV1(
        source=source,
        _p01_session=p01_session,
        _state=state,
        _facts=facts,
        _fact_codes=fact_codes,
        read_session_identity_sha256=session_identity,
        _anchor=_new_anchor(
            session_identity,
            source,
            p01_session,
            state,
            facts,
            fact_codes,
        ),
        _seal=_SESSION_SEAL,
    )
    _check_cancel(cancel_callback)
    return session


def open_daily_market_technical_universe_price_session_for_query_v1(
    query: DailyMarketTechnicalUniversePriceQueryV1 | bytes | str,
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> tuple[
    DailyMarketTechnicalUniversePriceReadSessionV1,
    DailyMarketTechnicalUniversePriceQueryV1,
]:
    """由已保存 query 的 exact pins 建立 fresh read session。"""

    _check_cancel(cancel_callback)
    parsed = (
        query
        if isinstance(query, DailyMarketTechnicalUniversePriceQueryV1)
        else DailyMarketTechnicalUniversePriceQueryV1.from_json(query)
    )
    source = parsed.source
    session = open_daily_market_technical_universe_price_read_session_v1(
        store_output_root=source.store_output_root,
        generation_identity_sha256=source.generation_identity_sha256,
        plan_identity_sha256=source.plan_identity_sha256,
        plan_sha256=source.plan_sha256,
        receipt_identity_sha256=source.receipt_identity_sha256,
        receipt_sha256=source.receipt_sha256,
        cancel_callback=cancel_callback,
    )
    if not session.matches_query(parsed):
        _fail("technical_universe_price_query_source_mismatch")
    _check_cancel(cancel_callback)
    return session, parsed
