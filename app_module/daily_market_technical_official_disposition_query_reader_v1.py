"""將 exact F17 projection 與 full-N 技術列唯讀合併、篩選及分頁。"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, NoReturn, cast

from app_module import daily_market_technical_universe_v4_query as _universe_query_module
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_BYTES,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROW_BYTES,
    DailyMarketTechnicalOfficialDispositionBundleError,
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
    DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
    DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1,
    DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
    DailyMarketTechnicalOfficialDispositionFactRowV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPACT_SORT_MAX_BYTES,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_MAX_SORT_CLAUSES,
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
    ConditionTruth,
    DailyMarketTechnicalOfficialDispositionCompactSortKeyV1,
    DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
    DailyMarketTechnicalOfficialDispositionJoinedRowV1,
    DailyMarketTechnicalOfficialDispositionQueryV1,
    DailyMarketTechnicalOfficialDispositionQueryV1Error,
    DailyMarketTechnicalOfficialDispositionSortValueV1,
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
    RowScope,
    evaluate_f17_membership_v1,
    normalize_daily_market_technical_official_source_pin_identity_sha256,
    project_daily_market_technical_official_disposition_sort_key_v1,
    sort_daily_market_technical_official_disposition_sort_keys_v1,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Row,
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_INDEX,
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE,
    DailyMarketTechnicalUniverseV4Counts,
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4QueryError,
    DailyMarketTechnicalUniverseV4ReadSelection,
    DailyMarketTechnicalUniverseV4ReadSelectionPage,
    DailyMarketTechnicalUniverseV4ReadSession,
    open_daily_market_technical_universe_v4_read_session,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4StoreError,
    daily_market_technical_source_clock_v4_from_dict,
)
from data_module.selection_market_assignments import (
    CurrentMarketAssignmentError,
    CurrentMarketAssignmentSourcePinV1,
)
from data_module.selection_official_events import (
    CurrentOfficialDisposalSourcePinV1,
    SelectionOfficialEventError,
)


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_READER_V1_SCHEMA = (
    "daily-market-technical-official-disposition-query-reader.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_PAGE_REQUEST_V1_SCHEMA = (
    "daily-market-technical-official-disposition-page-request.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_READER_V1_MAX_PAGE_SIZE = 256
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_READER_V1_MAX_DECLARED = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_PAGE_REQUEST_V1_MAX_BYTES = (
    8 * 1024 * 1024 + 4096
)

_SHA256_LENGTH = 64
_TRUTH_VALUES: tuple[ConditionTruth, ...] = (
    "match", "no_match", "unknown", "not_evaluated", "not_applicable",
)
_RULE_STATE_VALUES = ("match", "no_match", "unknown")
_MARKET_STATE_VALUES = ("assigned_twse", "assigned_tpex", "unknown")
_DISPOSAL_STATE_VALUES = (
    "reported_upcoming", "reported_active", "reported_elapsed_only", "unknown",
)
_SESSION_SEAL = object()
_RESULT_SEAL_ISSUER = object()
_PAGE_SEAL_ISSUER = object()
_SOURCE_CANCEL_CODES = frozenset({
    "cancelled_before_publish",
    "technical_universe_v4_query_cancelled",
    "technical_universe_v4_read_cancelled",
})


class DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(ValueError):
    """F17 full-N 唯讀 join 的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled(
    DailyMarketTechnicalOfficialDispositionQueryReaderV1Error
):
    """查詢或頁面回讀被取消。"""


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
        f"technical_official_query_reader_v1_{code}"
    )


def _fail_cancelled() -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled(
        "technical_official_query_reader_v1_cancelled"
    )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_sha256(value: object, code: str) -> str:
    if not _is_sha256(value):
        _fail(code)
    return cast(str, value)


def _reject_float_tree(value: object) -> None:
    if isinstance(value, float):
        _fail("float_not_allowed")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("json_object_key_invalid")
            _reject_float_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item)


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
        raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            "technical_official_query_reader_v1_json_invalid"
        ) from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json_sequence(values: Iterable[object]) -> str:
    """以串流方式摘要 canonical JSON array，避免額外保留全量投影清單。"""
    digest = hashlib.sha256()
    digest.update(b"[")
    first = True
    for value in values:
        if not first:
            digest.update(b",")
        digest.update(_canonical_json_bytes(value))
        first = False
    digest.update(b"]")
    return digest.hexdigest()


class _ReaderIssuedIdentitySealV1:
    __slots__ = ("identity_sha256", "subject", "_locked")

    identity_sha256: str
    subject: object
    _locked: bool

    def __init__(self, identity_sha256: str, subject: object, *, issuer: object) -> None:
        if issuer not in {_RESULT_SEAL_ISSUER, _PAGE_SEAL_ISSUER}:
            _fail("reader_identity_seal_issuer_invalid")
        _require_sha256(identity_sha256, "reader_identity_seal_invalid")
        object.__setattr__(self, "identity_sha256", identity_sha256)
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_locked", False):
            raise AttributeError("reader-issued identity seal is immutable")
        object.__setattr__(self, name, value)


def _bundle_reference_payload(
    reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
) -> dict[str, object]:
    return {
        "output_root": reference.output_root,
        "bundle_identity_sha256": reference.bundle_identity_sha256,
        "manifest_relative_path": reference.manifest_relative_path,
        "manifest_sha256": reference.manifest_sha256,
        "row_count": reference.row_count,
        "projection_status": reference.projection_status,
        "technical_receipt_status": reference.technical_receipt_status,
        "source_coverage_status": reference.source_coverage_status,
    }


def _query_operation_identity(
    *,
    query: DailyMarketTechnicalOfficialDispositionQueryV1,
    bundle_reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
    p01_read_session_identity_sha256: str,
    p01_selection_identity_sha256: str,
    p01_query_spec_identity_sha256: str,
    counts: DailyMarketTechnicalOfficialDispositionQueryCountsV1,
    ordered_codes_sha256: str,
) -> str:
    return _sha256_json({
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_READER_V1_SCHEMA,
        "algorithm_version": "f17-full-n-join-v1",
        "query_identity_sha256": query.query_identity_sha256,
        "bundle_identity_sha256": bundle_reference.bundle_identity_sha256,
        "bundle_manifest_sha256": bundle_reference.manifest_sha256,
        "p01_read_session_identity_sha256": p01_read_session_identity_sha256,
        "p01_selection_identity_sha256": p01_selection_identity_sha256,
        "p01_query_spec_identity_sha256": p01_query_spec_identity_sha256,
        "declared_count": counts.population.declared_count,
        "included_count": counts.population.included_count,
        "excluded_count": counts.population.excluded_count,
        "processed_count": counts.population.processed_count,
        "pending_count": counts.population.pending_count,
        "matching_count": counts.matching_count,
        "ordered_codes_sha256": ordered_codes_sha256,
    })


def _verified_result_seal_identity(
    *,
    query: DailyMarketTechnicalOfficialDispositionQueryV1,
    operation_identity_sha256: str,
    ordered_codes_sha256: str,
    counts: DailyMarketTechnicalOfficialDispositionQueryCountsV1,
    bundle_reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
    p01_read_session_identity_sha256: str,
    p01_selection_identity_sha256: str,
    p01_query_spec_identity_sha256: str,
    ordered_sort_keys: Sequence[DailyMarketTechnicalOfficialDispositionCompactSortKeyV1],
) -> str:
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-verified-result-seal.v1",
        "query_identity_sha256": query.query_identity_sha256,
        "operation_identity_sha256": operation_identity_sha256,
        "ordered_codes_sha256": ordered_codes_sha256,
        "ordered_sort_keys_sha256": _sha256_json_sequence(
            key.to_dict() for key in ordered_sort_keys
        ),
        "counts_sha256": _sha256_json(counts.to_dict()),
        "bundle_reference": _bundle_reference_payload(bundle_reference),
        "p01_read_session_identity_sha256": p01_read_session_identity_sha256,
        "p01_selection_identity_sha256": p01_selection_identity_sha256,
        "p01_query_spec_identity_sha256": p01_query_spec_identity_sha256,
    })


def _query_page_identity(
    *,
    operation_identity_sha256: str,
    request_identity_sha256: str,
    page_index: int,
    page_size: int,
    stock_codes: Sequence[str],
    rows: Sequence[DailyMarketTechnicalOfficialDispositionQueryResultRowV1],
) -> str:
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-page.v1",
        "operation_identity_sha256": operation_identity_sha256,
        "request_identity_sha256": request_identity_sha256,
        "page_index": page_index,
        "page_size": page_size,
        "ordered_stock_codes": list(stock_codes),
        "row_identity_sha256s": [row.row_identity_sha256 for row in rows],
    })


def _query_page_seal_identity(
    *,
    query: DailyMarketTechnicalOfficialDispositionQueryV1,
    request_identity_sha256: str,
    operation_identity_sha256: str,
    page_identity_sha256: str,
    page_index: int,
    page_size: int,
    page_count: int,
    counts: DailyMarketTechnicalOfficialDispositionQueryCountsV1,
    rows: Sequence[DailyMarketTechnicalOfficialDispositionQueryResultRowV1],
    bundle_reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
    p01_read_session_identity_sha256: str,
    p01_selection_identity_sha256: str,
    p01_query_spec_identity_sha256: str,
    join_status: str,
    result_status: str,
    technical_processing_status: str,
    bundle_projection_status: str,
    official_source_coverage_status: str,
    source_coverage_incomplete_reasons: Sequence[str],
    scope: str,
    official_available_at: None,
    historical_pit_eligible: bool,
    full_market_claim: bool,
) -> str:
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-page-seal.v1",
        "query_identity_sha256": query.query_identity_sha256,
        "request_identity_sha256": request_identity_sha256,
        "operation_identity_sha256": operation_identity_sha256,
        "page_identity_sha256": page_identity_sha256,
        "page_index": page_index,
        "page_size": page_size,
        "page_count": page_count,
        "counts": counts.to_dict(),
        "rows_sha256": _sha256_json_sequence(row.to_dict() for row in rows),
        "bundle_reference": _bundle_reference_payload(bundle_reference),
        "p01_read_session_identity_sha256": p01_read_session_identity_sha256,
        "p01_selection_identity_sha256": p01_selection_identity_sha256,
        "p01_query_spec_identity_sha256": p01_query_spec_identity_sha256,
        "join_status": join_status,
        "result_status": result_status,
        "technical_processing_status": technical_processing_status,
        "bundle_projection_status": bundle_projection_status,
        "official_source_coverage_status": official_source_coverage_status,
        "source_coverage_incomplete_reasons": list(source_coverage_incomplete_reasons),
        "scope": scope,
        "official_available_at": official_available_at,
        "historical_pit_eligible": historical_pit_eligible,
        "full_market_claim": full_market_claim,
    })


def _check_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    try:
        result = callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            "technical_official_query_reader_v1_cancel_callback_failed"
        ) from exc
    if type(result) is not bool:
        _fail("cancel_callback_invalid")
    if result:
        _fail_cancelled()


def _check_source_error_cancelled(error: Exception) -> None:
    """將下層取消轉成 reader 的公開取消碼，其餘錯誤保留原因鏈。"""
    if getattr(error, "code", None) in _SOURCE_CANCEL_CODES:
        _fail_cancelled()


def _validate_cancel_callback(callback: Callable[[], object] | None) -> None:
    if callback is not None and not callable(callback):
        _fail("cancel_callback_invalid")


def _mapping(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        _fail(code)
    return cast(Mapping[str, object], value)


def _aware_datetime(value: object, code: str) -> datetime:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _fail(code)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code)
    return parsed


def _parse_query(
    query: DailyMarketTechnicalOfficialDispositionQueryV1 | bytes | str,
) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    if isinstance(query, (str, bytes)):
        try:
            query = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(query)
        except (DailyMarketTechnicalOfficialDispositionQueryV1Error, UnicodeError) as exc:
            raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
                "technical_official_query_reader_v1_query_invalid"
            ) from exc
    if type(query) is not DailyMarketTechnicalOfficialDispositionQueryV1:
        _fail("query_invalid")
    try:
        raw = query.to_json().encode("utf-8")
    except (TypeError, ValueError, DailyMarketTechnicalOfficialDispositionQueryV1Error) as exc:
        raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            "technical_official_query_reader_v1_query_invalid"
        ) from exc
    if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_PAGE_REQUEST_V1_MAX_BYTES:
        _fail("query_size_limit")
    if DailyMarketTechnicalOfficialDispositionQueryV1.from_json(raw).query_identity_sha256 != query.query_identity_sha256:
        _fail("query_identity_mismatch")
    return query


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionPageRequestV1:
    """可在新程序重開的 exact query 與外層頁錨點。"""

    query_json: str
    page_index: int
    page_size: int
    request_identity_sha256: str

    @classmethod
    def create(
        cls,
        query: DailyMarketTechnicalOfficialDispositionQueryV1,
        *,
        page_index: int,
        page_size: int,
    ) -> DailyMarketTechnicalOfficialDispositionPageRequestV1:
        query = _parse_query(query)
        _validate_page_anchor(page_index, page_size)
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_PAGE_REQUEST_V1_SCHEMA,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": page_index,
            "page_size": page_size,
        }
        return cls(
            query_json=query.to_json(),
            page_index=page_index,
            page_size=page_size,
            request_identity_sha256=_sha256_json(body),
        )

    @classmethod
    def from_json(
        cls,
        raw: bytes | str,
    ) -> DailyMarketTechnicalOfficialDispositionPageRequestV1:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if not isinstance(encoded, bytes) or len(encoded) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_PAGE_REQUEST_V1_MAX_BYTES:
            _fail("page_request_size_limit")
        try:
            payload = json.loads(encoded.decode("utf-8"), object_pairs_hook=_unique_object_pairs)
        except DailyMarketTechnicalOfficialDispositionQueryReaderV1Error:
            raise
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
                "technical_official_query_reader_v1_page_request_json_invalid"
            ) from exc
        value = _mapping(payload, "page_request_invalid")
        expected_keys = {
            "schema_version", "query_json", "query_identity_sha256", "page_index",
            "page_size", "request_identity_sha256",
        }
        if set(value) != expected_keys or value.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_PAGE_REQUEST_V1_SCHEMA:
            _fail("page_request_schema_invalid")
        query_json = value.get("query_json")
        if not isinstance(query_json, str):
            _fail("page_request_query_invalid")
        query = _parse_query(query_json)
        if value.get("query_identity_sha256") != query.query_identity_sha256:
            _fail("page_request_query_identity_mismatch")
        page_index = value.get("page_index")
        page_size = value.get("page_size")
        _validate_page_anchor(page_index, page_size)
        identity = _require_sha256(value.get("request_identity_sha256"), "page_request_identity_invalid")
        result = cls.create(query, page_index=cast(int, page_index), page_size=cast(int, page_size))
        if result.request_identity_sha256 != identity or result.to_json().encode("utf-8") != encoded:
            _fail("page_request_noncanonical")
        return result

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionQueryV1:
        return _parse_query(self.query_json)

    def to_dict(self) -> dict[str, object]:
        query = self.query
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_PAGE_REQUEST_V1_SCHEMA,
            "query_json": self.query_json,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
            "request_identity_sha256": self.request_identity_sha256,
        }

    def to_json(self) -> str:
        return _canonical_json_bytes(self.to_dict()).decode("utf-8")


def _unique_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key")
        result[key] = value
    return result


def _validate_page_anchor(page_index: object, page_size: object) -> None:
    if (
        type(page_index) is not int
        or not 0 <= page_index <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_INDEX
        or type(page_size) is not int
        or not 1 <= page_size <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_READER_V1_MAX_PAGE_SIZE
    ):
        _fail("page_anchor_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionTruthCountsV1:
    match: int
    no_match: int
    unknown: int
    not_evaluated: int
    not_applicable: int

    @property
    def total(self) -> int:
        return self.match + self.no_match + self.unknown + self.not_evaluated + self.not_applicable

    def to_dict(self) -> dict[str, int]:
        return {
            "match": self.match,
            "no_match": self.no_match,
            "unknown": self.unknown,
            "not_evaluated": self.not_evaluated,
            "not_applicable": self.not_applicable,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMembershipCountsV1:
    matched: int
    unmatched: int

    @property
    def total(self) -> int:
        return self.matched + self.unmatched

    def to_dict(self) -> dict[str, int]:
        return {"matched": self.matched, "unmatched": self.unmatched}


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRuleStateCountsV1:
    rule_key: str
    match: int
    no_match: int
    unknown: int

    @property
    def total(self) -> int:
        return self.match + self.no_match + self.unknown

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_key": self.rule_key,
            "match": self.match,
            "no_match": self.no_match,
            "unknown": self.unknown,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionQueryCountsV1:
    """以 code 為單位的全母體分母、來源 truth 與 filter counts。"""

    population: DailyMarketTechnicalUniverseV4Counts
    unknown_rule_stock_count: int
    rule_state_counts: tuple[DailyMarketTechnicalOfficialDispositionRuleStateCountsV1, ...]
    market_state_counts: tuple[tuple[str, int], ...]
    disposal_state_counts: tuple[tuple[str, int], ...]
    truth_counts: tuple[tuple[str, DailyMarketTechnicalOfficialDispositionTruthCountsV1], ...]
    membership_counts: tuple[tuple[str, DailyMarketTechnicalOfficialDispositionMembershipCountsV1], ...]
    matching_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.population, DailyMarketTechnicalUniverseV4Counts):
            _fail("query_counts_population_invalid")
        declared = self.population.declared_count
        if (
            type(self.unknown_rule_stock_count) is not int
            or not 0 <= self.unknown_rule_stock_count <= self.population.processed_count
            or type(self.matching_count) is not int
            or not 0 <= self.matching_count <= declared
        ):
            _fail("query_counts_invalid")
        if len({item.rule_key for item in self.rule_state_counts}) != len(self.rule_state_counts):
            _fail("query_counts_rule_duplicate")
        if any(item.total != self.population.processed_count for item in self.rule_state_counts):
            _fail("query_counts_rule_total_mismatch")
        if (
            sum(value for _key, value in self.market_state_counts) != declared
            or sum(value for _key, value in self.disposal_state_counts) != declared
            or len({key for key, _value in self.market_state_counts}) != len(self.market_state_counts)
            or len({key for key, _value in self.disposal_state_counts}) != len(self.disposal_state_counts)
        ):
            _fail("query_counts_source_state_mismatch")
        truth_keys = tuple(key for key, _value in self.truth_counts)
        member_keys = tuple(key for key, _value in self.membership_counts)
        if len(set(truth_keys)) != len(truth_keys) or len(set(member_keys)) != len(member_keys):
            _fail("query_counts_filter_duplicate")
        if any(value.total != declared for _key, value in self.truth_counts):
            _fail("query_counts_truth_total_mismatch")
        if any(value.total != declared for _key, value in self.membership_counts):
            _fail("query_counts_membership_total_mismatch")

    @property
    def missing_data_count(self) -> int:
        return self.population.missing_data_count

    @property
    def pending_count(self) -> int:
        return self.population.pending_count

    @property
    def declared_count(self) -> int:
        return self.population.declared_count

    def truth(self, key: str) -> DailyMarketTechnicalOfficialDispositionTruthCountsV1:
        for name, value in self.truth_counts:
            if name == key:
                return value
        _fail("query_counts_truth_key_missing")

    def membership(self, key: str) -> DailyMarketTechnicalOfficialDispositionMembershipCountsV1:
        for name, value in self.membership_counts:
            if name == key:
                return value
        _fail("query_counts_membership_key_missing")

    def to_dict(self) -> dict[str, object]:
        return {
            "population": self.population.to_dict(),
            "unknown_rule_stock_count": self.unknown_rule_stock_count,
            "rule_state_counts": [item.to_dict() for item in self.rule_state_counts],
            "market_state_counts": {key: value for key, value in self.market_state_counts},
            "disposal_state_counts": {key: value for key, value in self.disposal_state_counts},
            "truth_counts": {key: value.to_dict() for key, value in self.truth_counts},
            "membership_counts": {key: value.to_dict() for key, value in self.membership_counts},
            "matching_count": self.matching_count,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionQueryResultRowV1:
    """一列 exact F17 fact 與可選技術 row；不攜帶 snapshot 或 parent bytes。"""

    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1
    technical_row: DailyMarketTechnicalParentV4Row | None
    filter_evaluation: DailyMarketTechnicalOfficialDispositionFilterEvaluationV1
    technical_stock_filter_match: bool
    technical_filter_match: bool
    technical_filter_truth: ConditionTruth
    overall_match: bool
    row_identity_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.fact_row, DailyMarketTechnicalOfficialDispositionFactRowV1):
            _fail("result_row_fact_invalid")
        if self.technical_row is not None and (
            not isinstance(self.technical_row, DailyMarketTechnicalParentV4Row)
            or self.technical_row.stock_code != self.fact_row.stock_code
        ):
            _fail("result_row_technical_invalid")
        if self.filter_evaluation.stock_code != self.fact_row.stock_code:
            _fail("result_row_evaluation_invalid")
        if self.technical_filter_truth not in _TRUTH_VALUES:
            _fail("result_row_technical_truth_invalid")
        _require_sha256(self.row_identity_sha256, "result_row_identity_invalid")

    @property
    def stock_code(self) -> str:
        return self.fact_row.stock_code

    def to_dict(self) -> dict[str, object]:
        return {
            "stock_code": self.stock_code,
            "fact_row": self.fact_row.to_dict(),
            "technical_row": None if self.technical_row is None else self.technical_row.to_dict(),
            "filter_evaluation": {
                "row_scope": self.filter_evaluation.row_scope,
                "row_scope_match": self.filter_evaluation.row_scope_match,
                "stock_filter_match": self.filter_evaluation.stock_filter_match,
                "market_assignment_match": self.filter_evaluation.market_assignment_match,
                "market_assignment_truth": self.filter_evaluation.market_assignment_truth,
                "official_disposal_match": self.filter_evaluation.official_disposal_match,
                "official_disposal_truth": self.filter_evaluation.official_disposal_truth,
            },
            "technical_stock_filter_match": self.technical_stock_filter_match,
            "technical_filter_match": self.technical_filter_match,
            "technical_filter_truth": self.technical_filter_truth,
            "overall_match": self.overall_match,
            "row_identity_sha256": self.row_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionQueryPageV1:
    """固定 exact operation 的全域排序頁與不混合的完整來源狀態。"""

    query: DailyMarketTechnicalOfficialDispositionQueryV1
    request_identity_sha256: str
    operation_identity_sha256: str
    page_identity_sha256: str
    page_index: int
    page_size: int
    page_count: int
    counts: DailyMarketTechnicalOfficialDispositionQueryCountsV1
    rows: tuple[DailyMarketTechnicalOfficialDispositionQueryResultRowV1, ...]
    bundle_reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1
    p01_read_session_identity_sha256: str
    p01_selection_identity_sha256: str
    p01_query_spec_identity_sha256: str
    join_status: Literal["verified"]
    result_status: Literal["complete", "partial"]
    technical_processing_status: Literal["complete", "partial"]
    bundle_projection_status: Literal["complete"]
    official_source_coverage_status: Literal["complete", "partial"]
    source_coverage_incomplete_reasons: tuple[str, ...]
    scope: Literal["current_only"]
    official_available_at: None
    historical_pit_eligible: Literal[False]
    full_market_claim: Literal[False]
    _read_session: DailyMarketTechnicalOfficialDispositionReadSessionV1
    _seal: _ReaderIssuedIdentitySealV1

    def __post_init__(self) -> None:
        if (
            type(self._seal) is not _ReaderIssuedIdentitySealV1
            or self._seal.subject is not self._read_session
            or type(self._read_session) is not DailyMarketTechnicalOfficialDispositionReadSessionV1
            or self._read_session.query.query_identity_sha256 != self.query.query_identity_sha256
            or self._read_session._bundle_state.reference != self.bundle_reference
            or self._read_session.p01_read_session_identity_sha256 != self.p01_read_session_identity_sha256
            or self._read_session.p01_selection_identity_sha256 != self.p01_selection_identity_sha256
            or self._read_session.p01_query_spec_identity_sha256 != self.p01_query_spec_identity_sha256
        ):
            _fail("page_not_reader_issued")
        for value in (
            self.request_identity_sha256,
            self.operation_identity_sha256,
            self.page_identity_sha256,
            self.p01_read_session_identity_sha256,
            self.p01_selection_identity_sha256,
            self.p01_query_spec_identity_sha256,
        ):
            _require_sha256(value, "page_identity_invalid")
        _validate_page_anchor(self.page_index, self.page_size)
        if (
            self.page_count != (self.counts.matching_count + self.page_size - 1) // self.page_size
            or len(self.rows) > self.page_size
            or self.counts.matching_count > self.counts.declared_count
            or self.join_status != "verified"
            or self.bundle_projection_status != "complete"
            or self.scope != "current_only"
            or self.official_available_at is not None
            or self.historical_pit_eligible is not False
            or self.full_market_claim is not False
            or self.result_status not in {"complete", "partial"}
            or self.technical_processing_status not in {"complete", "partial"}
            or self.official_source_coverage_status not in {"complete", "partial"}
        ):
            _fail("page_shape_invalid")
        expected_status: Literal["complete", "partial"] = (
            "complete"
            if self.technical_processing_status == "complete"
            and self.official_source_coverage_status == "complete"
            else "partial"
        )
        if self.result_status != expected_status:
            _fail("page_status_inconsistent")
        if any(type(row) is not DailyMarketTechnicalOfficialDispositionQueryResultRowV1 for row in self.rows):
            _fail("page_row_type_invalid")
        if len({row.stock_code for row in self.rows}) != len(self.rows):
            _fail("page_duplicate_stock")
        expected_request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
            self.query,
            page_index=self.page_index,
            page_size=self.page_size,
        )
        if expected_request.request_identity_sha256 != self.request_identity_sha256:
            _fail("page_request_identity_mismatch")
        expected_page_identity = _query_page_identity(
            operation_identity_sha256=self.operation_identity_sha256,
            request_identity_sha256=self.request_identity_sha256,
            page_index=self.page_index,
            page_size=self.page_size,
            stock_codes=tuple(row.stock_code for row in self.rows),
            rows=self.rows,
        )
        if self.page_identity_sha256 != expected_page_identity:
            _fail("page_identity_digest_mismatch")
        expected_seal_identity = _query_page_seal_identity(
            query=self.query,
            request_identity_sha256=self.request_identity_sha256,
            operation_identity_sha256=self.operation_identity_sha256,
            page_identity_sha256=self.page_identity_sha256,
            page_index=self.page_index,
            page_size=self.page_size,
            page_count=self.page_count,
            counts=self.counts,
            rows=self.rows,
            bundle_reference=self.bundle_reference,
            p01_read_session_identity_sha256=self.p01_read_session_identity_sha256,
            p01_selection_identity_sha256=self.p01_selection_identity_sha256,
            p01_query_spec_identity_sha256=self.p01_query_spec_identity_sha256,
            join_status=self.join_status,
            result_status=self.result_status,
            technical_processing_status=self.technical_processing_status,
            bundle_projection_status=self.bundle_projection_status,
            official_source_coverage_status=self.official_source_coverage_status,
            source_coverage_incomplete_reasons=self.source_coverage_incomplete_reasons,
            scope=self.scope,
            official_available_at=self.official_available_at,
            historical_pit_eligible=self.historical_pit_eligible,
            full_market_claim=self.full_market_claim,
        )
        if self._seal.identity_sha256 != expected_seal_identity:
            _fail("page_reader_seal_mismatch")

    @property
    def is_complete(self) -> bool:
        return self.result_status == "complete"

    @property
    def matching_count(self) -> int:
        return self.counts.matching_count

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_READER_V1_SCHEMA,
            "query": self.query.to_dict(),
            "request_identity_sha256": self.request_identity_sha256,
            "operation_identity_sha256": self.operation_identity_sha256,
            "page_identity_sha256": self.page_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
            "page_count": self.page_count,
            "matching_count": self.matching_count,
            "counts": self.counts.to_dict(),
            "rows": [row.to_dict() for row in self.rows],
            "bundle_reference": {
                "output_root": self.bundle_reference.output_root,
                "bundle_identity_sha256": self.bundle_reference.bundle_identity_sha256,
                "manifest_relative_path": self.bundle_reference.manifest_relative_path,
                "manifest_sha256": self.bundle_reference.manifest_sha256,
                "row_count": self.bundle_reference.row_count,
                "projection_status": self.bundle_reference.projection_status,
                "technical_receipt_status": self.bundle_reference.technical_receipt_status,
                "source_coverage_status": self.bundle_reference.source_coverage_status,
            },
            "p01_read_session_identity_sha256": self.p01_read_session_identity_sha256,
            "p01_selection_identity_sha256": self.p01_selection_identity_sha256,
            "p01_query_spec_identity_sha256": self.p01_query_spec_identity_sha256,
            "join_status": self.join_status,
            "result_status": self.result_status,
            "technical_processing_status": self.technical_processing_status,
            "bundle_projection_status": self.bundle_projection_status,
            "official_source_coverage_status": self.official_source_coverage_status,
            "source_coverage_incomplete_reasons": list(self.source_coverage_incomplete_reasons),
            "scope": self.scope,
            "official_available_at": None,
            "historical_pit_eligible": False,
            "full_market_claim": False,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1:
    """單次全母體 join/filter/sort 的 reader-issued immutable operation。"""

    query: DailyMarketTechnicalOfficialDispositionQueryV1
    operation_identity_sha256: str
    ordered_codes_sha256: str
    counts: DailyMarketTechnicalOfficialDispositionQueryCountsV1
    bundle_reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1
    p01_read_session_identity_sha256: str
    p01_selection_identity_sha256: str
    p01_query_spec_identity_sha256: str
    _ordered_sort_keys: tuple[DailyMarketTechnicalOfficialDispositionCompactSortKeyV1, ...]
    _read_session: DailyMarketTechnicalOfficialDispositionReadSessionV1
    _seal: _ReaderIssuedIdentitySealV1

    def __post_init__(self) -> None:
        if (
            type(self._seal) is not _ReaderIssuedIdentitySealV1
            or self._seal.subject is not self._read_session
        ):
            _fail("query_result_not_reader_issued")
        for value in (
            self.operation_identity_sha256,
            self.ordered_codes_sha256,
            self.p01_read_session_identity_sha256,
            self.p01_selection_identity_sha256,
            self.p01_query_spec_identity_sha256,
        ):
            _require_sha256(value, "query_result_identity_invalid")
        if (
            type(self.query) is not DailyMarketTechnicalOfficialDispositionQueryV1
            or type(self.counts) is not DailyMarketTechnicalOfficialDispositionQueryCountsV1
            or type(self.bundle_reference) is not DailyMarketTechnicalOfficialDispositionBundleReferenceV1
            or type(self._read_session) is not DailyMarketTechnicalOfficialDispositionReadSessionV1
            or len(self._ordered_sort_keys) != self.counts.matching_count
            or len(self._ordered_sort_keys) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_READER_V1_MAX_DECLARED
            or self._read_session.query.query_identity_sha256 != self.query.query_identity_sha256
            or self._read_session.bundle_reference != self.bundle_reference
            or self._read_session.p01_read_session_identity_sha256 != self.p01_read_session_identity_sha256
            or self._read_session.p01_selection_identity_sha256 != self.p01_selection_identity_sha256
            or self._read_session.p01_query_spec_identity_sha256 != self.p01_query_spec_identity_sha256
        ):
            _fail("query_result_shape_invalid")
        if any(
            type(item) is not DailyMarketTechnicalOfficialDispositionCompactSortKeyV1
            or item.query_identity_sha256 != self.query.query_identity_sha256
            or item.market_assignment_pin_identity_sha256
            != self.query.market_assignment_pin_identity_sha256
            or item.official_disposal_pin_identity_sha256
            != self.query.official_disposal_pin_identity_sha256
            for item in self._ordered_sort_keys
        ):
            _fail("query_result_key_query_mismatch")
        ordered_codes = tuple(item.stock_code for item in self._ordered_sort_keys)
        if (
            len(set(ordered_codes)) != len(ordered_codes)
            or _sha256_json_sequence(ordered_codes) != self.ordered_codes_sha256
        ):
            _fail("query_result_ordered_codes_digest_mismatch")
        expected_operation_identity = _query_operation_identity(
            query=self.query,
            bundle_reference=self.bundle_reference,
            p01_read_session_identity_sha256=self.p01_read_session_identity_sha256,
            p01_selection_identity_sha256=self.p01_selection_identity_sha256,
            p01_query_spec_identity_sha256=self.p01_query_spec_identity_sha256,
            counts=self.counts,
            ordered_codes_sha256=self.ordered_codes_sha256,
        )
        if self.operation_identity_sha256 != expected_operation_identity:
            _fail("query_result_operation_identity_mismatch")
        expected_seal_identity = _verified_result_seal_identity(
            query=self.query,
            operation_identity_sha256=self.operation_identity_sha256,
            ordered_codes_sha256=self.ordered_codes_sha256,
            counts=self.counts,
            bundle_reference=self.bundle_reference,
            p01_read_session_identity_sha256=self.p01_read_session_identity_sha256,
            p01_selection_identity_sha256=self.p01_selection_identity_sha256,
            p01_query_spec_identity_sha256=self.p01_query_spec_identity_sha256,
            ordered_sort_keys=self._ordered_sort_keys,
        )
        if self._seal.identity_sha256 != expected_seal_identity:
            _fail("query_result_reader_seal_mismatch")

    def read_page(
        self,
        page_index: int,
        page_size: int,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionQueryPageV1:
        request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
            self.query,
            page_index=page_index,
            page_size=page_size,
        )
        return self.read_page_request(request, cancel_callback=cancel_callback)

    def read_page_request(
        self,
        request: DailyMarketTechnicalOfficialDispositionPageRequestV1 | bytes | str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionQueryPageV1:
        if type(self._seal) is not _ReaderIssuedIdentitySealV1:
            _fail("query_result_not_reader_issued")
        _validate_cancel_callback(cancel_callback)
        if isinstance(request, (bytes, str)):
            request = DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(request)
        if type(request) is not DailyMarketTechnicalOfficialDispositionPageRequestV1:
            _fail("page_request_invalid")
        if request.query.query_identity_sha256 != self.query.query_identity_sha256:
            _fail("page_request_query_mismatch")
        _check_cancel(cancel_callback)
        return self._read_session._materialize_page(self, request, cancel_callback)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionReadSessionV1:
    """固定 F17 bundle、P01 source session 與 unfiltered selection。"""

    query: DailyMarketTechnicalOfficialDispositionQueryV1
    bundle_reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1
    p01_read_session_identity_sha256: str
    p01_selection_identity_sha256: str
    p01_query_spec_identity_sha256: str
    _bundle_state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1
    _technical_session: DailyMarketTechnicalUniverseV4ReadSession
    _base_query: DailyMarketTechnicalUniverseV4Query
    _selection: DailyMarketTechnicalUniverseV4ReadSelection
    _technical_store_descriptor: Mapping[str, object]
    _manifest: Mapping[str, object]
    _seal: object

    def __post_init__(self) -> None:
        if self._seal is not _SESSION_SEAL:
            _fail("read_session_not_reader_issued")
        for value in (
            self.p01_read_session_identity_sha256,
            self.p01_selection_identity_sha256,
            self.p01_query_spec_identity_sha256,
        ):
            _require_sha256(value, "read_session_identity_invalid")
        if (
            self._bundle_state.reference != self.bundle_reference
            or self._technical_session.read_session_identity_sha256 != self.p01_read_session_identity_sha256
            or self._selection.selection_identity_sha256 != self.p01_selection_identity_sha256
            or self._selection_query_spec_identity(self._selection) != self.p01_query_spec_identity_sha256
            or not self._technical_session.matches_source(self._base_query)
        ):
            _fail("read_session_source_mismatch")

    @staticmethod
    def _selection_query_spec_identity(
        selection: DailyMarketTechnicalUniverseV4ReadSelection,
    ) -> str:
        # 只讀 owner 凍結的 public getter；不以 private hash 演算法自行重算。
        value = getattr(selection, "query_spec_identity_sha256", None)
        return value if isinstance(value, str) else ""

    def with_conditions(
        self,
        *,
        row_scope_filter: Sequence[RowScope],
        rule_state_filters: Sequence[DailyMarketTechnicalRuleStateFilterV4] = (),
        combine_mode: Literal["AND", "OR"] = "AND",
        market_assignment_states: Sequence[str] = (),
        official_disposal_states: Sequence[str] = (),
        outer_stock_filter_mode: Literal["all", "explicit_codes"] = "all",
        outer_stock_codes: Sequence[str] = (),
        sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionSortClauseV1] = (),
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionReadSessionV1:
        """修改研究條件但沿用原完整核驗來源；明確重驗須另開 exact session。"""
        _validate_cancel_callback(cancel_callback)
        _check_cancel(cancel_callback)
        self.__post_init__()
        _validate_bundle_query_relationship(self.query, self._bundle_state)
        try:
            technical_query = self._technical_session.create_query(
                rule_state_filters=rule_state_filters,
                combine_mode=combine_mode,
                stock_filter=(),
                sort_key="stock_code",
                descending=False,
                page_index=0,
                page_size=1,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )
            query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
                technical_query=technical_query,
                decision_cutoff=self.query.decision_cutoff,
                bundle_output_root=self.query.bundle_output_root,
                bundle_identity_sha256=self.query.bundle_identity_sha256,
                expected_manifest_sha256=self.query.expected_manifest_sha256,
                market_assignment_pin_identity_sha256=self.query.market_assignment_pin_identity_sha256,
                official_disposal_pin_identity_sha256=self.query.official_disposal_pin_identity_sha256,
                row_scope_filter=row_scope_filter,
                market_assignment_states=market_assignment_states,
                official_disposal_states=official_disposal_states,
                outer_stock_filter_mode=outer_stock_filter_mode,
                outer_stock_codes=outer_stock_codes,
                sort_clauses=sort_clauses,
            )
        except (DailyMarketTechnicalUniverseV4QueryError,
                DailyMarketTechnicalOfficialDispositionQueryV1Error) as exc:
            _check_source_error_cancelled(exc)
            raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
                "technical_official_query_reader_v1_research_conditions_invalid"
            ) from exc
        _validate_bundle_query_relationship(query, self._bundle_state)
        if not self._technical_session.matches_source(query.technical_query):
            _fail("p01_base_query_source_mismatch")
        session = replace(self, query=query)
        _check_cancel(cancel_callback)
        return session

    def execute(
        self,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1:
        if self._seal is not _SESSION_SEAL:
            _fail("read_session_not_reader_issued")
        _validate_cancel_callback(cancel_callback)
        _check_cancel(cancel_callback)
        counts_builder = _CountsBuilder(self.query, self._technical_session.source_counts)
        sort_keys: list[DailyMarketTechnicalOfficialDispositionCompactSortKeyV1] = []
        expected_counts = self._technical_session.source_counts
        expected_processed = expected_counts.processed_count
        processed_index = 0
        last_fact_code: str | None = None
        technical_rows = iter(self._iter_selection_rows(cancel_callback))
        current_technical = next(technical_rows, None)
        for fact in self._iter_verified_bundle_rows(cancel_callback):
            _check_cancel(cancel_callback)
            if last_fact_code is not None and fact.stock_code <= last_fact_code:
                _fail("bundle_rows_not_unique_sorted")
            last_fact_code = fact.stock_code
            payload = fact.to_dict()
            status = payload.get("technical_status")
            if status == "processed":
                if (
                    processed_index >= len(self._selection.stock_codes)
                    or self._selection.stock_codes[processed_index] != fact.stock_code
                    or current_technical is None
                    or current_technical.stock_code != fact.stock_code
                ):
                    _fail("processed_stock_join_mismatch")
                technical_row = current_technical
                current_technical = next(technical_rows, None)
                processed_index += 1
            else:
                technical_row = None
                if current_technical is not None and current_technical.stock_code <= fact.stock_code:
                    _fail("unexpected_technical_stock_row")
            joined = DailyMarketTechnicalOfficialDispositionJoinedRowV1(
                fact_row=fact,
                technical_row=technical_row,
            )
            outer = evaluate_f17_membership_v1(self.query, fact)
            technical_match, technical_truth, technical_stock_match = _technical_filter_evaluation(
                self.query,
                fact,
                technical_row,
            )
            sort_key = project_daily_market_technical_official_disposition_sort_key_v1(
                self.query,
                joined,
                cancel_callback=cast(Callable[[], object] | None, cancel_callback),
            )
            overall_match = outer.filter_membership and technical_match
            counts_builder.add(
                fact=fact,
                technical_row=technical_row,
                outer=outer,
                technical_stock_match=technical_stock_match,
                technical_match=technical_match,
                technical_truth=technical_truth,
                overall_match=overall_match,
            )
            if overall_match:
                sort_keys.append(sort_key)
            _check_cancel(cancel_callback)
        if current_technical is not None or next(technical_rows, None) is not None:
            _fail("extra_technical_stock_rows")
        if processed_index != expected_processed or processed_index != len(self._selection.stock_codes):
            _fail("processed_count_mismatch")
        counts = counts_builder.finish()
        if counts.population != expected_counts:
            _fail("bundle_technical_counts_mismatch")
        if len(sort_keys) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_READER_V1_MAX_DECLARED:
            _fail("matching_stock_limit")
        _check_cancel(cancel_callback)
        ordered_keys = sort_daily_market_technical_official_disposition_sort_keys_v1(
            self.query,
            sort_keys,
            cancel_callback=cast(Callable[[], object] | None, cancel_callback),
        )
        ordered_codes = tuple(item.stock_code for item in ordered_keys)
        if len(set(ordered_codes)) != len(ordered_codes):
            _fail("matching_stock_duplicate")
        ordered_codes_sha = _sha256_json(list(ordered_codes))
        operation_identity = _query_operation_identity(
            query=self.query,
            bundle_reference=self.bundle_reference,
            p01_read_session_identity_sha256=self.p01_read_session_identity_sha256,
            p01_selection_identity_sha256=self.p01_selection_identity_sha256,
            p01_query_spec_identity_sha256=self.p01_query_spec_identity_sha256,
            counts=counts,
            ordered_codes_sha256=ordered_codes_sha,
        )
        result_seal_identity = _verified_result_seal_identity(
            query=self.query,
            operation_identity_sha256=operation_identity,
            ordered_codes_sha256=ordered_codes_sha,
            counts=counts,
            bundle_reference=self.bundle_reference,
            p01_read_session_identity_sha256=self.p01_read_session_identity_sha256,
            p01_selection_identity_sha256=self.p01_selection_identity_sha256,
            p01_query_spec_identity_sha256=self.p01_query_spec_identity_sha256,
            ordered_sort_keys=ordered_keys,
        )
        _check_cancel(cancel_callback)
        result = DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1(
            query=self.query,
            operation_identity_sha256=operation_identity,
            ordered_codes_sha256=ordered_codes_sha,
            counts=counts,
            bundle_reference=self.bundle_reference,
            p01_read_session_identity_sha256=self.p01_read_session_identity_sha256,
            p01_selection_identity_sha256=self.p01_selection_identity_sha256,
            p01_query_spec_identity_sha256=self.p01_query_spec_identity_sha256,
            _ordered_sort_keys=ordered_keys,
            _read_session=self,
            _seal=_ReaderIssuedIdentitySealV1(
                result_seal_identity,
                self,
                issuer=_RESULT_SEAL_ISSUER,
            ),
        )
        _check_cancel(cancel_callback)
        return result

    def _iter_selection_rows(
        self,
        cancel_callback: Callable[[], object] | None,
    ) -> Iterator[DailyMarketTechnicalParentV4Row]:
        codes = self._selection.stock_codes
        count = self._selection.matching_count
        page_size = DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE
        page_count = (count + page_size - 1) // page_size
        if count != len(codes) or count > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_READER_V1_MAX_DECLARED:
            _fail("selection_count_invalid")
        for page_index in range(page_count):
            _check_cancel(cancel_callback)
            try:
                page = self._technical_session.read_selection_page(
                    self._selection,
                    page_index=page_index,
                    page_size=page_size,
                    cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
                )
            except (DailyMarketTechnicalUniverseV4QueryError, DailyMarketTechnicalUniverseV4StoreError) as exc:
                _check_source_error_cancelled(exc)
                raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
                    "technical_official_query_reader_v1_p01_selection_page_failed"
                ) from exc
            if not isinstance(page, DailyMarketTechnicalUniverseV4ReadSelectionPage):
                _fail("selection_page_type_invalid")
            start = page_index * page_size
            expected_codes = codes[start:start + page_size]
            page_rows = page.rows
            if (
                page.selection_identity_sha256 != self.p01_selection_identity_sha256
                or page.page_index != page_index
                or page.page_size != page_size
                or page.matching_count != count
                or page.page_count != page_count
                or tuple(row.stock_code for row in page_rows) != expected_codes
            ):
                _fail("selection_page_identity_mismatch")
            for row in page_rows:
                _check_cancel(cancel_callback)
                if not isinstance(row, DailyMarketTechnicalParentV4Row):
                    _fail("selection_page_row_type_invalid")
                yield row
                _check_cancel(cancel_callback)

    def _iter_verified_bundle_rows(
        self,
        cancel_callback: Callable[[], object] | None,
    ) -> Iterator[DailyMarketTechnicalOfficialDispositionFactRowV1]:
        try:
            yield from self._bundle_state.iter_verified_rows(
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback)
            )
        except DailyMarketTechnicalOfficialDispositionBundleError as exc:
            _check_source_error_cancelled(exc)
            raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
                "technical_official_query_reader_v1_bundle_row_read_failed"
            ) from exc

    def _materialize_page(
        self,
        result: DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1,
        request: DailyMarketTechnicalOfficialDispositionPageRequestV1,
        cancel_callback: Callable[[], object] | None,
    ) -> DailyMarketTechnicalOfficialDispositionQueryPageV1:
        if result._read_session is not self or result.query.query_identity_sha256 != self.query.query_identity_sha256:
            _fail("query_result_session_mismatch")
        _check_cancel(cancel_callback)
        matching_count = result.counts.matching_count
        page_count = (matching_count + request.page_size - 1) // request.page_size
        start = request.page_index * request.page_size
        selected_keys = result._ordered_sort_keys[start:start + request.page_size]
        selected_codes = tuple(item.stock_code for item in selected_keys)
        selected_set = set(selected_codes)
        if len(selected_set) != len(selected_codes):
            _fail("page_duplicate_stock")
        try:
            selected = self._bundle_state.read_selected_rows(
                selected_codes,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )
        except DailyMarketTechnicalOfficialDispositionBundleError as exc:
            _check_source_error_cancelled(exc)
            raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
                "technical_official_query_reader_v1_bundle_selected_rows_failed"
            ) from exc
        if type(selected) is not DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1:
            _fail("bundle_selected_rows_type_invalid")
        selected_payload = selected.to_dict()
        facts = selected.rows
        if (
            selected_payload.get("schema_version")
            != "daily-market-technical-official-disposition-selected-rows.v1"
            or selected.output_root != self.bundle_reference.output_root
            or selected.bundle_identity_sha256 != self.bundle_reference.bundle_identity_sha256
            or selected.manifest_relative_path != self.bundle_reference.manifest_relative_path
            or selected.manifest_sha256 != self.bundle_reference.manifest_sha256
            or selected.requested_stock_codes != selected_codes
            or tuple(fact.stock_code for fact in facts) != selected_codes
        ):
            _fail("bundle_selected_rows_identity_mismatch")
        processed_codes = tuple(
            fact.stock_code for fact in facts
            if fact.to_dict().get("technical_status") == "processed"
        )
        batch = self._materialize_selected_rows(processed_codes, cancel_callback)
        technical_by_code = {row.stock_code: row for row in batch.rows}
        if tuple(technical_by_code) != processed_codes or len(technical_by_code) != len(batch.rows):
            _fail("page_materialized_rows_order_invalid")
        page_rows: list[DailyMarketTechnicalOfficialDispositionQueryResultRowV1] = []
        for key, fact in zip(selected_keys, facts, strict=True):
            _check_cancel(cancel_callback)
            status = fact.to_dict().get("technical_status")
            technical_row = technical_by_code.get(fact.stock_code)
            if (status == "processed") != (technical_row is not None):
                _fail("page_technical_row_scope_invalid")
            joined = DailyMarketTechnicalOfficialDispositionJoinedRowV1(fact, technical_row)
            outer = evaluate_f17_membership_v1(self.query, fact)
            technical_match, technical_truth, technical_stock_match = _technical_filter_evaluation(
                self.query,
                fact,
                technical_row,
            )
            regenerated_key = project_daily_market_technical_official_disposition_sort_key_v1(
                self.query,
                joined,
                cancel_callback=cast(Callable[[], object] | None, cancel_callback),
            )
            if regenerated_key != key or not (outer.filter_membership and technical_match):
                _fail("page_selected_row_changed")
            overall = outer.filter_membership and technical_match
            row_identity = _sha256_json({
                "schema_version": "daily-market-technical-official-disposition-result-row.v1",
                "fact_row_sha256": key.fact_row_sha256,
                "technical_snapshot_identity_sha256": key.technical_snapshot_identity_sha256,
                "technical_source_identity": key.technical_source_identity,
                "filter_evaluation": _filter_evaluation_payload(outer),
                "technical_stock_filter_match": technical_stock_match,
                "technical_filter_match": technical_match,
                "technical_filter_truth": technical_truth,
                "overall_match": overall,
            })
            page_rows.append(DailyMarketTechnicalOfficialDispositionQueryResultRowV1(
                fact_row=fact,
                technical_row=technical_row,
                filter_evaluation=outer,
                technical_stock_filter_match=technical_stock_match,
                technical_filter_match=technical_match,
                technical_filter_truth=technical_truth,
                overall_match=overall,
                row_identity_sha256=row_identity,
            ))
        page_identity = _query_page_identity(
            operation_identity_sha256=result.operation_identity_sha256,
            request_identity_sha256=request.request_identity_sha256,
            page_index=request.page_index,
            page_size=request.page_size,
            stock_codes=selected_codes,
            rows=page_rows,
        )
        _check_cancel(cancel_callback)
        technical_complete = (
            self.bundle_reference.technical_receipt_status == "complete"
            and result.counts.population.pending_count == 0
            and result.counts.population.processed_count == result.counts.population.included_count
        )
        official_coverage = self.bundle_reference.source_coverage_status
        result_status: Literal["complete", "partial"] = (
            "complete" if technical_complete and official_coverage == "complete" else "partial"
        )
        coverage = _mapping(self._manifest.get("source_coverage"), "source_coverage_invalid")
        reasons = coverage.get("incomplete_reasons")
        if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
            _fail("source_coverage_reasons_invalid")
        page_rows_tuple = tuple(page_rows)
        page_seal_identity = _query_page_seal_identity(
            query=self.query,
            request_identity_sha256=request.request_identity_sha256,
            operation_identity_sha256=result.operation_identity_sha256,
            page_identity_sha256=page_identity,
            page_index=request.page_index,
            page_size=request.page_size,
            page_count=page_count,
            counts=result.counts,
            rows=page_rows_tuple,
            bundle_reference=self.bundle_reference,
            p01_read_session_identity_sha256=self.p01_read_session_identity_sha256,
            p01_selection_identity_sha256=self.p01_selection_identity_sha256,
            p01_query_spec_identity_sha256=self.p01_query_spec_identity_sha256,
            join_status="verified",
            result_status=result_status,
            technical_processing_status="complete" if technical_complete else "partial",
            bundle_projection_status="complete",
            official_source_coverage_status=official_coverage,
            source_coverage_incomplete_reasons=tuple(reasons),
            scope="current_only",
            official_available_at=None,
            historical_pit_eligible=False,
            full_market_claim=False,
        )
        page = DailyMarketTechnicalOfficialDispositionQueryPageV1(
            query=self.query,
            request_identity_sha256=request.request_identity_sha256,
            operation_identity_sha256=result.operation_identity_sha256,
            page_identity_sha256=page_identity,
            page_index=request.page_index,
            page_size=request.page_size,
            page_count=page_count,
            counts=result.counts,
            rows=page_rows_tuple,
            bundle_reference=self.bundle_reference,
            p01_read_session_identity_sha256=self.p01_read_session_identity_sha256,
            p01_selection_identity_sha256=self.p01_selection_identity_sha256,
            p01_query_spec_identity_sha256=self.p01_query_spec_identity_sha256,
            join_status="verified",
            result_status=result_status,
            technical_processing_status="complete" if technical_complete else "partial",
            bundle_projection_status="complete",
            official_source_coverage_status=official_coverage,
            source_coverage_incomplete_reasons=tuple(reasons),
            scope="current_only",
            official_available_at=None,
            historical_pit_eligible=False,
            full_market_claim=False,
            _read_session=self,
            _seal=_ReaderIssuedIdentitySealV1(
                page_seal_identity,
                self,
                issuer=_PAGE_SEAL_ISSUER,
            ),
        )
        _check_cancel(cancel_callback)
        return page

    def _materialize_selected_rows(
        self,
        stock_codes: tuple[str, ...],
        cancel_callback: Callable[[], object] | None,
    ) -> Any:
        if len(stock_codes) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_READER_V1_MAX_PAGE_SIZE:
            _fail("materializer_batch_size_invalid")
        method = getattr(self._technical_session, "materialize_selected_stock_codes", None)
        if not callable(method):
            _fail("p01_selected_rows_materializer_unavailable")
        _check_cancel(cancel_callback)
        try:
            batch = method(
                self._selection,
                explicit_stock_codes=stock_codes,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )
        except (DailyMarketTechnicalUniverseV4QueryError, OSError, RuntimeError, ValueError) as exc:
            _check_source_error_cancelled(exc)
            raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
                "technical_official_query_reader_v1_p01_selected_rows_failed"
            ) from exc
        _check_cancel(cancel_callback)
        batch_type = getattr(_universe_query_module, "DailyMarketTechnicalUniverseV4SelectedRows", None)
        if not isinstance(batch_type, type) or type(batch) is not batch_type:
            _fail("p01_selected_rows_type_invalid")
        if (
            getattr(batch, "read_session_identity_sha256", None) != self.p01_read_session_identity_sha256
            or getattr(batch, "selection_identity_sha256", None) != self.p01_selection_identity_sha256
            or getattr(batch, "query_spec_identity_sha256", None) != self.p01_query_spec_identity_sha256
            or getattr(batch, "requested_stock_codes", None) != stock_codes
        ):
            _fail("p01_selected_rows_identity_mismatch")
        for name in (
            "ordered_stock_codes_sha256", "rows_identity_sha256", "materialization_identity_sha256",
        ):
            _require_sha256(getattr(batch, name, None), f"p01_selected_rows_{name}_invalid")
        rows = getattr(batch, "rows", None)
        if not isinstance(rows, tuple) or any(
            not isinstance(row, DailyMarketTechnicalParentV4Row) for row in rows
        ):
            _fail("p01_selected_rows_rows_invalid")
        if tuple(row.stock_code for row in rows) != stock_codes:
            _fail("p01_selected_rows_order_mismatch")
        try:
            row_payloads = [row.to_dict() for row in rows]
            payload = _mapping(cast(Any, batch).to_dict(), "p01_selected_rows_payload_invalid")
        except (AttributeError, TypeError, ValueError) as exc:
            raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
                "technical_official_query_reader_v1_p01_selected_rows_payload_invalid"
            ) from exc
        expected_keys = {
            "schema", "read_session_identity_sha256", "selection_identity_sha256",
            "query_spec_identity_sha256", "requested_stock_codes",
            "ordered_stock_codes_sha256", "rows", "rows_identity_sha256",
            "materialization_identity_sha256",
        }
        if (
            set(payload) != expected_keys
            or payload.get("schema") != "daily-market-technical-universe-v4-selected-rows.v1"
            or payload.get("read_session_identity_sha256") != self.p01_read_session_identity_sha256
            or payload.get("selection_identity_sha256") != self.p01_selection_identity_sha256
            or payload.get("query_spec_identity_sha256") != self.p01_query_spec_identity_sha256
            or payload.get("requested_stock_codes") != list(stock_codes)
            or payload.get("rows") != row_payloads
        ):
            _fail("p01_selected_rows_payload_mismatch")
        ordered_codes_sha = _sha256_json(list(stock_codes))
        rows_sha = _sha256_json(row_payloads)
        expected_materialization_sha = _sha256_json({
            "schema": "daily-market-technical-universe-v4-selected-rows.identity.v1",
            "read_session_identity_sha256": self.p01_read_session_identity_sha256,
            "selection_identity_sha256": self.p01_selection_identity_sha256,
            "query_spec_identity_sha256": self.p01_query_spec_identity_sha256,
            "ordered_stock_codes_sha256": ordered_codes_sha,
            "requested_count": len(stock_codes),
            "rows_identity_sha256": rows_sha,
            "row_count": len(rows),
        })
        if (
            payload.get("ordered_stock_codes_sha256") != ordered_codes_sha
            or getattr(batch, "ordered_stock_codes_sha256", None) != ordered_codes_sha
            or payload.get("rows_identity_sha256") != rows_sha
            or getattr(batch, "rows_identity_sha256", None) != rows_sha
            or payload.get("materialization_identity_sha256") != expected_materialization_sha
            or getattr(batch, "materialization_identity_sha256", None) != expected_materialization_sha
        ):
            _fail("p01_selected_rows_digest_mismatch")
        return batch


class _CountsBuilder:
    def __init__(
        self,
        query: DailyMarketTechnicalOfficialDispositionQueryV1,
        expected: DailyMarketTechnicalUniverseV4Counts,
    ) -> None:
        self.query = query
        self.expected = expected
        self.roles = {"included_processed": 0, "included_pending": 0, "excluded": 0}
        self.rule_counts: dict[str, dict[str, int]] = {
            key: {state: 0 for state in _RULE_STATE_VALUES}
            for key in query.technical_query.method_rule_keys
        }
        self.market_states = {state: 0 for state in _MARKET_STATE_VALUES}
        self.disposal_states = {state: 0 for state in _DISPOSAL_STATE_VALUES}
        truth_names = ("technical", "market_assignment", "official_disposal")
        self.truth = {
            name: {state: 0 for state in _TRUTH_VALUES}
            for name in truth_names
        }
        member_names = (
            "row_scope", "outer_stock_filter", "technical_stock_filter",
            "technical_filter", "market_assignment", "official_disposal", "combined",
        )
        self.membership = {
            name: {"matched": 0, "unmatched": 0}
            for name in member_names
        }
        self.missing_data = 0
        self.unknown_rule_stocks = 0
        self.processed = 0
        self.pending = 0
        self.included = 0
        self.excluded = 0
        self.declared = 0
        self.matching = 0
        self.last_code: str | None = None

    def add(
        self,
        *,
        fact: DailyMarketTechnicalOfficialDispositionFactRowV1,
        technical_row: DailyMarketTechnicalParentV4Row | None,
        outer: DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
        technical_stock_match: bool,
        technical_match: bool,
        technical_truth: ConditionTruth,
        overall_match: bool,
    ) -> None:
        payload = fact.to_dict()
        code = fact.stock_code
        if self.last_code is not None and code <= self.last_code:
            _fail("counts_rows_not_unique_sorted")
        self.last_code = code
        role = payload.get("cohort_role")
        status = payload.get("technical_status")
        if role == "excluded" and status == "excluded":
            scope = "excluded"
            self.excluded += 1
        elif role == "included" and status == "processed":
            scope = "included_processed"
            self.included += 1
            self.processed += 1
        elif role == "included" and status == "pending":
            scope = "included_pending"
            self.included += 1
            self.pending += 1
        else:
            _fail("counts_fact_role_status_invalid")
        self.declared += 1
        self.roles[scope] += 1
        market = _mapping(payload.get("market_assignment"), "fact_market_invalid")
        disposal = _mapping(payload.get("official_disposal"), "fact_disposal_invalid")
        market_state = market.get("state")
        disposal_state = disposal.get("state")
        if market_state not in self.market_states or disposal_state not in self.disposal_states:
            _fail("fact_source_state_invalid")
        self.market_states[cast(str, market_state)] += 1
        self.disposal_states[cast(str, disposal_state)] += 1
        if technical_row is not None:
            if technical_row.has_missing_data:
                self.missing_data += 1
            if technical_row.has_unknown_rules:
                self.unknown_rule_stocks += 1
            for rule in technical_row.rules:
                if rule.key not in self.rule_counts or rule.state not in _RULE_STATE_VALUES:
                    _fail("fact_rule_state_invalid")
                self.rule_counts[rule.key][rule.state] += 1
        self._count_membership("row_scope", outer.row_scope_match)
        self._count_membership("outer_stock_filter", outer.stock_filter_match)
        self._count_membership("technical_stock_filter", technical_stock_match)
        self._count_membership("technical_filter", technical_match)
        self._count_membership("market_assignment", outer.market_assignment_match)
        self._count_membership("official_disposal", outer.official_disposal_match)
        self._count_membership("combined", overall_match)
        self._count_truth("technical", technical_truth)
        self._count_truth("market_assignment", outer.market_assignment_truth)
        self._count_truth("official_disposal", outer.official_disposal_truth)
        if overall_match:
            self.matching += 1

    def _count_membership(self, name: str, value: bool) -> None:
        self.membership[name]["matched" if value else "unmatched"] += 1

    def _count_truth(self, name: str, value: ConditionTruth) -> None:
        if value not in self.truth[name]:
            _fail("condition_truth_invalid")
        self.truth[name][value] += 1

    def finish(self) -> DailyMarketTechnicalOfficialDispositionQueryCountsV1:
        population = DailyMarketTechnicalUniverseV4Counts(
            declared_count=self.declared,
            included_count=self.included,
            excluded_count=self.excluded,
            processed_count=self.processed,
            pending_count=self.pending,
            missing_data_count=self.missing_data,
            missing_data_pending_count=self.pending,
        )
        if (
            population.declared_count != self.expected.declared_count
            or population.included_count != self.expected.included_count
            or population.excluded_count != self.expected.excluded_count
            or population.processed_count != self.expected.processed_count
            or population.pending_count != self.expected.pending_count
            or population.missing_data_count != self.expected.missing_data_count
            or population.missing_data_pending_count != self.expected.missing_data_pending_count
        ):
            _fail("population_counts_mismatch")
        rule_states = tuple(
            DailyMarketTechnicalOfficialDispositionRuleStateCountsV1(
                rule_key=key,
                match=counts["match"],
                no_match=counts["no_match"],
                unknown=counts["unknown"],
            )
            for key, counts in self.rule_counts.items()
        )
        return DailyMarketTechnicalOfficialDispositionQueryCountsV1(
            population=population,
            unknown_rule_stock_count=self.unknown_rule_stocks,
            rule_state_counts=rule_states,
            market_state_counts=tuple((key, self.market_states[key]) for key in _MARKET_STATE_VALUES),
            disposal_state_counts=tuple((key, self.disposal_states[key]) for key in _DISPOSAL_STATE_VALUES),
            truth_counts=tuple(
                (name, DailyMarketTechnicalOfficialDispositionTruthCountsV1(**values))
                for name, values in self.truth.items()
            ),
            membership_counts=tuple(
                (name, DailyMarketTechnicalOfficialDispositionMembershipCountsV1(**values))
                for name, values in self.membership.items()
            ),
            matching_count=self.matching,
        )


def _three_valued_combine(
    values: Sequence[ConditionTruth],
    mode: Literal["AND", "OR"],
) -> ConditionTruth:
    if not values:
        return "not_applicable"
    if mode == "AND":
        if "no_match" in values:
            return "no_match"
        if "not_evaluated" in values:
            return "not_evaluated"
        if "unknown" in values:
            return "unknown"
        return "match"
    if "match" in values:
        return "match"
    if "not_evaluated" in values:
        return "not_evaluated"
    if "unknown" in values:
        return "unknown"
    return "no_match"


def _technical_filter_evaluation(
    query: DailyMarketTechnicalOfficialDispositionQueryV1,
    fact: DailyMarketTechnicalOfficialDispositionFactRowV1,
    row: DailyMarketTechnicalParentV4Row | None,
) -> tuple[bool, ConditionTruth, bool]:
    payload = fact.to_dict()
    status = payload.get("technical_status")
    if (status == "processed") != (row is not None):
        _fail("technical_row_scope_invalid")
    stock_filter = query.technical_query.stock_filter
    stock_match = not stock_filter or fact.stock_code in stock_filter
    stock_truth: ConditionTruth = (
        "not_applicable" if not stock_filter else ("match" if stock_match else "no_match")
    )
    state_filters = query.technical_query.rule_state_filters
    rule_match = True
    rule_truth: ConditionTruth = "not_applicable"
    if state_filters:
        if status == "pending":
            rule_match = False
            rule_truth = "not_evaluated"
        elif status == "excluded":
            rule_match = False
            rule_truth = "not_applicable"
        elif row is None:
            _fail("technical_row_missing")
        else:
            memberships: list[bool] = []
            truths: list[ConditionTruth] = []
            for item in state_filters:
                evidence = row.rule(item.rule_key)
                if evidence.state not in _RULE_STATE_VALUES:
                    _fail("technical_rule_state_invalid")
                memberships.append(evidence.state in item.states)
                truths.append(
                    "unknown" if evidence.state == "unknown"
                    else "match" if evidence.state in item.states
                    else "no_match"
                )
            if query.technical_query.combine_mode == "AND":
                rule_match = all(memberships)
            elif query.technical_query.combine_mode == "OR":
                rule_match = any(memberships)
            else:
                _fail("technical_combine_mode_invalid")
            rule_truth = _three_valued_combine(
                truths,
                cast(Literal["AND", "OR"], query.technical_query.combine_mode),
            )
    applied_truths = [
        truth for truth in (stock_truth, rule_truth)
        if truth != "not_applicable"
    ]
    technical_truth = _three_valued_combine(applied_truths, "AND")
    technical_match = stock_match and rule_match
    return technical_match, technical_truth, stock_match


def _filter_evaluation_payload(
    value: DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
) -> dict[str, object]:
    return {
        "stock_code": value.stock_code,
        "row_scope": value.row_scope,
        "row_scope_match": value.row_scope_match,
        "stock_filter_match": value.stock_filter_match,
        "market_assignment_match": value.market_assignment_match,
        "market_assignment_truth": value.market_assignment_truth,
        "official_disposal_match": value.official_disposal_match,
        "official_disposal_truth": value.official_disposal_truth,
    }


def _row_identity_payload(
    key: DailyMarketTechnicalOfficialDispositionCompactSortKeyV1,
    evaluation: DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
    *,
    technical_stock_match: bool,
    technical_match: bool,
    technical_truth: ConditionTruth,
    overall_match: bool,
) -> dict[str, object]:
    return {
        "schema_version": "daily-market-technical-official-disposition-result-row.v1",
        "fact_row_sha256": key.fact_row_sha256,
        "technical_snapshot_identity_sha256": key.technical_snapshot_identity_sha256,
        "technical_source_identity": key.technical_source_identity,
        "filter_evaluation": _filter_evaluation_payload(evaluation),
        "technical_stock_filter_match": technical_stock_match,
        "technical_filter_match": technical_match,
        "technical_filter_truth": technical_truth,
        "overall_match": overall_match,
    }


def _validate_bundle_query_relationship(
    query: DailyMarketTechnicalOfficialDispositionQueryV1,
    bundle_state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    reference = bundle_state.reference
    if (
        Path(reference.output_root) != Path(query.bundle_output_root)
        or reference.bundle_identity_sha256 != query.bundle_identity_sha256
        or reference.manifest_sha256 != query.expected_manifest_sha256
        or reference.manifest_relative_path != f"manifests/{query.bundle_identity_sha256}.json"
        or reference.projection_status != "complete"
    ):
        _fail("bundle_reference_mismatch")
    manifest = _mapping(bundle_state.manifest, "bundle_manifest_invalid")
    technical = _mapping(manifest.get("technical_store"), "technical_store_descriptor_invalid")
    pins = _mapping(manifest.get("source_pins"), "source_pins_invalid")
    if set(pins) != {"market_assignment", "official_disposal"}:
        _fail("source_pins_invalid")
    try:
        market_pin = CurrentMarketAssignmentSourcePinV1.from_dict(pins.get("market_assignment"))
        disposal_pin = CurrentOfficialDisposalSourcePinV1.from_dict(pins.get("official_disposal"))
        market_pin_identity = normalize_daily_market_technical_official_source_pin_identity_sha256(
            market_pin.identity_sha256
        )
        disposal_pin_identity = normalize_daily_market_technical_official_source_pin_identity_sha256(
            disposal_pin.identity_sha256
        )
    except (CurrentMarketAssignmentError, SelectionOfficialEventError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            "technical_official_query_reader_v1_source_pin_invalid"
        ) from exc
    if (
        market_pin_identity != query.market_assignment_pin_identity_sha256
        or disposal_pin_identity != query.official_disposal_pin_identity_sha256
    ):
        _fail("source_pin_query_mismatch")
    try:
        clock = daily_market_technical_source_clock_v4_from_dict(technical.get("source_clock"))
    except (DailyMarketTechnicalUniverseV4StoreError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            "technical_official_query_reader_v1_source_clock_invalid"
        ) from exc
    if (
        clock.identity_sha256 != technical.get("source_clock_identity_sha256")
        or clock.decision_date != query.decision_date
        or clock.decision_cutoff != query.decision_cutoff
        or clock.historical_pit_eligible is not False
        or clock.source_available_at is not None
        or clock.availability_status != "unknown"
    ):
        _fail("source_clock_query_mismatch")
    if _aware_datetime(market_pin.cutoff_at, "market_pin_cutoff_invalid") != query.decision_cutoff:
        _fail("market_pin_cutoff_mismatch")
    technical_query = query.technical_query
    expected_fields: tuple[tuple[str, object, object], ...] = (
        ("store root", Path(technical_query.store_output_root), Path(str(technical.get("output_root")))),
        ("generation identity", technical_query.generation_identity_sha256, technical.get("generation_identity_sha256")),
        ("plan identity", technical_query.plan_identity_sha256, technical.get("plan_identity_sha256")),
        ("plan bytes", technical_query.plan_sha256, technical.get("plan_sha256")),
        ("receipt identity", technical_query.receipt_identity_sha256, technical.get("receipt_identity_sha256")),
        ("receipt bytes", technical_query.receipt_sha256, technical.get("receipt_sha256")),
        ("receipt status", technical_query.receipt_status, technical.get("receipt_status")),
        ("cohort identity", technical_query.cohort_identity_sha256, technical.get("cohort_identity_sha256")),
        ("decision date", technical_query.decision_date.isoformat(), technical.get("decision_date")),
        ("declared count", technical_query.declared_count, technical.get("declared_count")),
        ("included count", technical_query.included_count, technical.get("included_count")),
        ("excluded count", technical_query.excluded_count, technical.get("excluded_count")),
        ("source clock", technical_query.source_clock_identity_sha256, technical.get("source_clock_identity_sha256")),
        ("method contract", technical_query.method_contracts_sha256, technical.get("method_contracts_sha256")),
        ("counts", technical_query.counts.to_dict(), technical.get("counts")),
    )
    if any(actual != expected for _name, actual, expected in expected_fields):
        _fail("technical_query_bundle_descriptor_mismatch")
    if (
        type(manifest.get("row_count")) is not int
        or manifest.get("row_count") != technical_query.declared_count
        or reference.row_count != technical_query.declared_count
        or reference.technical_receipt_status != technical_query.receipt_status
        or reference.source_coverage_status != manifest.get("source_coverage_status")
    ):
        _fail("bundle_declared_count_mismatch")
    return technical, manifest


def _open_technical_session(
    technical: Mapping[str, object],
    cancel_callback: Callable[[], object] | None,
) -> DailyMarketTechnicalUniverseV4ReadSession:
    required = (
        "output_root", "generation_identity_sha256", "plan_identity_sha256", "plan_sha256",
        "receipt_identity_sha256", "receipt_sha256",
    )
    if any(not isinstance(technical.get(key), str) for key in required):
        _fail("technical_store_descriptor_invalid")
    _check_cancel(cancel_callback)
    try:
        return open_daily_market_technical_universe_v4_read_session(
            store_output_root=cast(str, technical["output_root"]),
            generation_identity_sha256=cast(str, technical["generation_identity_sha256"]),
            plan_identity_sha256=cast(str, technical["plan_identity_sha256"]),
            plan_sha256=cast(str, technical["plan_sha256"]),
            receipt_identity_sha256=cast(str, technical["receipt_identity_sha256"]),
            receipt_sha256=cast(str, technical["receipt_sha256"]),
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
    except DailyMarketTechnicalUniverseV4StoreError as exc:
        _check_source_error_cancelled(exc)
        raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            "technical_official_query_reader_v1_p01_exact_open_failed"
        ) from exc


def _open_base_selection(
    query: DailyMarketTechnicalOfficialDispositionQueryV1,
    technical: Mapping[str, object],
    cancel_callback: Callable[[], object] | None,
    *,
    preloaded_session: DailyMarketTechnicalUniverseV4ReadSession | None = None,
) -> tuple[
    DailyMarketTechnicalUniverseV4ReadSession,
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4ReadSelection,
    str,
]:
    _check_cancel(cancel_callback)
    read_session = (
        _open_technical_session(technical, cancel_callback)
        if preloaded_session is None else preloaded_session
    )
    if not read_session.matches_source(query.technical_query):
        _fail("p01_base_query_source_mismatch")
    try:
        base_query = read_session.create_query(
            rule_state_filters=(),
            combine_mode="AND",
            stock_filter=(),
            sort_key="stock_code",
            descending=False,
            page_index=0,
            page_size=1,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
        if not read_session.matches_source(base_query):
            _fail("p01_base_query_source_mismatch")
        selection = read_session.select_stock_codes(
            base_query,
            eligible_stock_codes=None,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
    except DailyMarketTechnicalUniverseV4StoreError as exc:
        _check_source_error_cancelled(exc)
        raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            "technical_official_query_reader_v1_p01_exact_open_failed"
        ) from exc
    except DailyMarketTechnicalUniverseV4QueryError as exc:
        _check_source_error_cancelled(exc)
        raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            "technical_official_query_reader_v1_p01_selection_failed"
        ) from exc
    _check_cancel(cancel_callback)
    source_counts = read_session.source_counts
    if (
        source_counts != query.technical_query.counts
        or selection.matching_count != source_counts.processed_count
        or selection.stock_codes != tuple(sorted(set(selection.stock_codes)))
        or len(selection.stock_codes) != source_counts.processed_count
    ):
        _fail("p01_base_selection_counts_invalid")
    query_spec_identity = getattr(selection, "query_spec_identity_sha256", None)
    if not _is_sha256(query_spec_identity):
        _fail("p01_selection_query_spec_identity_unavailable")
    return read_session, base_query, selection, cast(str, query_spec_identity)


def open_daily_market_technical_official_disposition_read_session_v1(
    query: DailyMarketTechnicalOfficialDispositionQueryV1 | bytes | str,
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionReadSessionV1:
    """依 query 中的固定 bundle/store pins 建立唯一 reader-issued session。"""

    _validate_cancel_callback(cancel_callback)
    parsed_query = _parse_query(query)
    _check_cancel(cancel_callback)
    try:
        bundle_state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(
            parsed_query.bundle_output_root
        ).read_exact(
            parsed_query.bundle_identity_sha256,
            expected_manifest_sha256=parsed_query.expected_manifest_sha256,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
    except DailyMarketTechnicalOfficialDispositionBundleError as exc:
        _check_source_error_cancelled(exc)
        raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            f"technical_official_query_reader_v1_bundle_exact_read_failed:{exc.code}"
        ) from exc
    return _issue_session_from_verified_bundle(parsed_query, bundle_state, cancel_callback)


def _issue_session_from_verified_bundle(
    parsed_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    bundle_state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
    cancel_callback: Callable[[], object] | None,
    *,
    preloaded_session: DailyMarketTechnicalUniverseV4ReadSession | None = None,
) -> DailyMarketTechnicalOfficialDispositionReadSessionV1:
    """共用發行邊界；factory 沿用同次完整核驗，避免重開來源。"""
    technical, manifest = _validate_bundle_query_relationship(parsed_query, bundle_state)
    _check_cancel(cancel_callback)
    technical_session, base_query, selection, query_spec_identity = _open_base_selection(
        parsed_query,
        technical,
        cancel_callback,
        preloaded_session=preloaded_session,
    )
    if (
        technical_session.store_output_root != str(Path(cast(str, technical["output_root"])))
        or technical_session.read_session_identity_sha256 == ""
        or selection.selection_identity_sha256 == ""
    ):
        _fail("p01_session_identity_invalid")
    _check_cancel(cancel_callback)
    session = DailyMarketTechnicalOfficialDispositionReadSessionV1(
        query=parsed_query,
        bundle_reference=bundle_state.reference,
        p01_read_session_identity_sha256=technical_session.read_session_identity_sha256,
        p01_selection_identity_sha256=selection.selection_identity_sha256,
        p01_query_spec_identity_sha256=query_spec_identity,
        _bundle_state=bundle_state,
        _technical_session=technical_session,
        _base_query=base_query,
        _selection=selection,
        _technical_store_descriptor=technical,
        _manifest=manifest,
        _seal=_SESSION_SEAL,
    )
    _check_cancel(cancel_callback)
    return session


def open_daily_market_technical_official_disposition_bundle_session_v1(
    *,
    bundle_output_root: str | Path,
    bundle_identity_sha256: str,
    expected_manifest_sha256: str,
    row_scope_filter: Sequence[RowScope],
    rule_state_filters: Sequence[DailyMarketTechnicalRuleStateFilterV4] = (),
    combine_mode: Literal["AND", "OR"] = "AND",
    market_assignment_states: Sequence[str] = (),
    official_disposal_states: Sequence[str] = (),
    outer_stock_filter_mode: Literal["all", "explicit_codes"] = "all",
    outer_stock_codes: Sequence[str] = (),
    sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionSortClauseV1] = (),
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionReadSessionV1:
    """由明示保存 bundle 核驗來源並建 query；不使用 latest 或現在時鐘。"""
    _validate_cancel_callback(cancel_callback)
    _check_cancel(cancel_callback)
    try:
        bundle_state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(
            bundle_output_root
        ).read_exact(
            bundle_identity_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
    except DailyMarketTechnicalOfficialDispositionBundleError as exc:
        _check_source_error_cancelled(exc)
        raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            f"technical_official_query_reader_v1_bundle_exact_read_failed:{exc.code}"
        ) from exc
    manifest = _mapping(bundle_state.manifest, "bundle_manifest_invalid")
    technical = _mapping(manifest.get("technical_store"), "technical_store_descriptor_invalid")
    pins = _mapping(manifest.get("source_pins"), "source_pins_invalid")
    try:
        clock = daily_market_technical_source_clock_v4_from_dict(technical.get("source_clock"))
        market_pin = CurrentMarketAssignmentSourcePinV1.from_dict(pins.get("market_assignment"))
        disposal_pin = CurrentOfficialDisposalSourcePinV1.from_dict(pins.get("official_disposal"))
    except (DailyMarketTechnicalUniverseV4StoreError, CurrentMarketAssignmentError,
            SelectionOfficialEventError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            "technical_official_query_reader_v1_bundle_source_descriptor_invalid"
        ) from exc
    _check_cancel(cancel_callback)
    technical_session = _open_technical_session(technical, cancel_callback)
    try:
        technical_query = technical_session.create_query(
            rule_state_filters=rule_state_filters,
            combine_mode=combine_mode,
            stock_filter=(),
            sort_key="stock_code",
            descending=False,
            page_index=0,
            page_size=1,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
        query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
            technical_query=technical_query,
            decision_cutoff=clock.decision_cutoff,
            bundle_output_root=bundle_state.reference.output_root,
            bundle_identity_sha256=bundle_state.reference.bundle_identity_sha256,
            expected_manifest_sha256=bundle_state.reference.manifest_sha256,
            market_assignment_pin_identity_sha256=market_pin.identity_sha256,
            official_disposal_pin_identity_sha256=disposal_pin.identity_sha256,
            row_scope_filter=row_scope_filter,
            market_assignment_states=market_assignment_states,
            official_disposal_states=official_disposal_states,
            outer_stock_filter_mode=outer_stock_filter_mode,
            outer_stock_codes=outer_stock_codes,
            sort_clauses=sort_clauses,
        )
    except (DailyMarketTechnicalUniverseV4QueryError,
            DailyMarketTechnicalOfficialDispositionQueryV1Error) as exc:
        _check_source_error_cancelled(exc)
        raise DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            "technical_official_query_reader_v1_research_conditions_invalid"
        ) from exc
    return _issue_session_from_verified_bundle(
        query, bundle_state, cancel_callback, preloaded_session=technical_session
    )


def read_daily_market_technical_official_disposition_page_v1(
    request: DailyMarketTechnicalOfficialDispositionPageRequestV1 | bytes | str,
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionQueryPageV1:
    """在新程序由 canonical request 重新 exact-open、全域查詢並讀一頁。"""

    if isinstance(request, (bytes, str)):
        request = DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(request)
    if type(request) is not DailyMarketTechnicalOfficialDispositionPageRequestV1:
        _fail("page_request_invalid")
    session = open_daily_market_technical_official_disposition_read_session_v1(
        request.query,
        cancel_callback=cancel_callback,
    )
    result = session.execute(cancel_callback=cancel_callback)
    page = result.read_page_request(request, cancel_callback=cancel_callback)
    _check_cancel(cancel_callback)
    return page

