"""以已完成的月營收 V2 全清冊發行 current-only YoY index。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from threading import Event, Lock, get_ident
from types import TracebackType
from typing import Literal, NoReturn

from data_module.daily_market_monthly_revenue_cohort_v2 import (
    DailyMarketMonthlyRevenueFactV2,
    DailyMarketMonthlyRevenueSourceReferenceV3,
    FinishedDailyMarketMonthlyRevenueCohortV2,
)
from data_module.daily_market_monthly_revenue_read_session_v2 import (
    DailyMarketMonthlyRevenueBatchCandidateV2,
    DailyMarketMonthlyRevenueReadCancelledV2,
    DailyMarketMonthlyRevenueReadIncompleteV2,
    DailyMarketMonthlyRevenueReadSessionV2,
    DailyMarketMonthlyRevenueReadSessionV2Error,
)
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    decode_daily_market_monthly_revenue_source_reference_v3,
)
from data_module.fundamental_read_snapshot_raw_archive_v2 import (
    FundamentalReadSnapshotRawArchiveReferenceV2,
)
from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
)
from data_module.fundamental_read_snapshot_cohort_v2 import FundamentalSnapshotSourceClockV2
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    CurrentObservedMonthlyRevenueInput,
    RecommendationCurrentFundamentalProvider,
)
from data_module.selection_fact_readers import MAX_CODES_PER_BATCH, MAX_STOCK_CODES
from decision_module.factors.selection_monthly_revenue_yoy_v2 import (
    SELECTION_REVENUE_YOY_METHOD_ID,
    SELECTION_REVENUE_YOY_METHOD_VERSION,
    SelectionMonthlyRevenueYoYFactV2,
    project_selection_monthly_revenue_yoy_v2,
)


DAILY_MARKET_MONTHLY_REVENUE_YOY_INDEX_SCHEMA_V2 = (
    "daily-market-monthly-revenue-yoy-index.v2"
)
DAILY_MARKET_MONTHLY_REVENUE_YOY_INDEX_ENTRY_SCHEMA_V2 = (
    "daily-market-monthly-revenue-yoy-index-entry.v2"
)
_STOCK_CODE_RE = re.compile(r"^[0-9]{4,6}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_INDEX_ISSUER = object()
_MAX_INDEX_JSON_BYTES = 64 * 1024 * 1024
_FACT_STATE_ORDER = ("blocked", "observed", "unknown")


class DailyMarketMonthlyRevenueYoyIndexError(ValueError):
    """月營收 YoY V2 index 的穩定拒絕錯誤。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"monthly_revenue_yoy_index_v2_{code}")


class DailyMarketMonthlyRevenueYoyIndexCancelled(DailyMarketMonthlyRevenueYoyIndexError):
    """月營收 YoY V2 操作收到 cooperative cancellation。"""


def _fail(code: str) -> NoReturn:
    raise DailyMarketMonthlyRevenueYoyIndexError(code)


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketMonthlyRevenueYoyIndexError("index_json_invalid") from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_sha(value: object, code: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _datetime_text(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        _fail("cutoff_not_aware")
    return value.astimezone(timezone.utc).isoformat()


def _observation_to_dict(
    value: CurrentObservedMonthlyRevenueInput | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "stock_code": value.stock_code,
        "period": value.period,
        "revenue": format(value.revenue, "f"),
        "observed_at": _datetime_text(value.observed_at),
        "source_available_at": (
            _datetime_text(value.source_available_at)
            if value.source_available_at is not None
            else None
        ),
        "available_at": _datetime_text(value.available_at),
        "source": value.source,
        "source_version": value.source_version,
        "market": value.market,
        "raw_source_version": value.raw_source_version,
        "raw_source_sha256": value.raw_source_sha256,
        "unit": value.unit,
        "period_basis": value.period_basis,
        "basis_verified": value.basis_verified,
        "aggregate_feature_eligible": value.aggregate_feature_eligible,
        "formal_pit_eligible": value.formal_pit_eligible,
        "availability_basis": value.availability_basis,
        "input_role": value.input_role,
        "parent_report_period": value.parent_report_period,
        "availability_snapshot_batch_id": value.availability_snapshot_batch_id,
        "availability_first_persisted_at": (
            _datetime_text(value.availability_first_persisted_at)
            if value.availability_first_persisted_at is not None
            else None
        ),
    }


def _read_result_to_dict(value: CurrentMonthlyRevenueReadResult) -> dict[str, object]:
    return {
        "status": value.status,
        "stock_code": value.stock_code,
        "cutoff_at": _datetime_text(value.cutoff_at),
        "latest_period": value.latest_period,
        "observations": [_observation_to_dict(item) for item in value.observations],
        "diagnostics": list(value.diagnostics),
        "blocked_periods": list(value.blocked_periods),
        "comparison_baseline": _observation_to_dict(value.comparison_baseline),
        "comparison_snapshot_sha256": value.comparison_snapshot_sha256,
        "diagnostic_source_row_count": value.diagnostic_source_row_count,
        "diagnostic_comparator_row_count": value.diagnostic_comparator_row_count,
    }


def _normalize_cutoff(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        _fail("cutoff_not_aware")
    return value.astimezone(timezone.utc)


def _strict_cancel(callback: Callable[[], object] | None, event: Event) -> None:
    if event.is_set():
        raise DailyMarketMonthlyRevenueYoyIndexCancelled("cancelled")
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        value = callback()
    except BaseException as exc:
        raise DailyMarketMonthlyRevenueYoyIndexError("cancel_check_failed") from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if event.is_set() or value:
        raise DailyMarketMonthlyRevenueYoyIndexCancelled("cancelled")


def _normalize_codes(
    stock_codes: Sequence[str],
    *,
    maximum: int,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(stock_codes, (str, bytes, bytearray)) or not isinstance(
        stock_codes, Sequence
    ):
        _fail("stock_codes_invalid")
    result: list[str] = []
    for index, code in enumerate(stock_codes):
        if index >= maximum:
            _fail("stock_code_limit")
        if type(code) is not str or _STOCK_CODE_RE.fullmatch(code) is None:
            _fail("stock_code_invalid")
        result.append(code)
    if not allow_empty and not result:
        _fail("stock_codes_empty")
    if len(result) != len(set(result)):
        _fail("stock_codes_duplicate")
    return tuple(result)


def _status_counts(
    facts: Sequence[DailyMarketMonthlyRevenueFactV2],
) -> tuple[tuple[str, int], ...]:
    counts = Counter(fact.result.status for fact in facts)
    return tuple((status, counts[status]) for status in sorted(counts))


def _fact_state_counts(
    facts: Sequence[DailyMarketMonthlyRevenueFactV2],
) -> tuple[tuple[str, int], ...]:
    counts: Counter[str] = Counter(fact.state for fact in facts)
    return tuple((state, counts[state]) for state in _FACT_STATE_ORDER)


def _projected_state_counts(
    entries: Sequence[DailyMarketMonthlyRevenueYoyIndexEntryV2],
) -> tuple[tuple[str, int], ...]:
    counts: Counter[str] = Counter(entry.projected_fact.state for entry in entries)
    return tuple((state, counts[state]) for state in ("observed", "unknown"))


@dataclass(frozen=True, slots=True)
class DailyMarketMonthlyRevenueYoyIndexEntryV2:
    """同一股票的原始 V2 source fact 與既有 selection YoY 投影。"""

    stock_code: str
    result_identity_sha256: str
    source_fact: DailyMarketMonthlyRevenueFactV2
    projected_fact: SelectionMonthlyRevenueYoYFactV2

    def __post_init__(self) -> None:
        if type(self.stock_code) is not str or _STOCK_CODE_RE.fullmatch(self.stock_code) is None:
            _fail("entry_stock_code_invalid")
        _require_sha(self.result_identity_sha256, "entry_result_identity_invalid")
        if (
            type(self.source_fact) is not DailyMarketMonthlyRevenueFactV2
            or type(self.projected_fact) is not SelectionMonthlyRevenueYoYFactV2
            or self.source_fact.stock_code != self.stock_code
            or self.projected_fact.stock_code != self.stock_code
            or self.source_fact.source_kind != "daily_monthly_revenue_cohort"
            or self.source_fact.result_identity_sha256 != self.result_identity_sha256
            or self.projected_fact.source_fact_identity_sha256
            != self.source_fact.identity_sha256
        ):
            _fail("entry_fact_binding_invalid")
        projected = self.projected_fact
        if (
            projected.method_id != SELECTION_REVENUE_YOY_METHOD_ID
            or projected.method_version != SELECTION_REVENUE_YOY_METHOD_VERSION
            or projected.source_scope != "current_observed_only"
            or projected.historical_pit_eligible is not False
            or projected.formal_pit_eligible is not False
            or projected.decision_cutoff is None
            or _datetime_text(projected.decision_cutoff)
            != _datetime_text(self.source_fact.result.cutoff_at)
        ):
            _fail("entry_method_clock_or_scope_invalid")

    @property
    def state(self) -> Literal["observed", "unknown"]:
        return self.projected_fact.state

    @property
    def growth_percent(self) -> Decimal | None:
        return self.projected_fact.growth_percent

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return self.projected_fact.reason_codes

    @property
    def source_fact_identity_sha256(self) -> str:
        return self.source_fact.identity_sha256

    @property
    def projected_fact_identity_sha256(self) -> str:
        return self.projected_fact.identity_sha256

    @property
    def identity_sha256(self) -> str:
        return _sha256_json(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": DAILY_MARKET_MONTHLY_REVENUE_YOY_INDEX_ENTRY_SCHEMA_V2,
            "stock_code": self.stock_code,
            "result_identity_sha256": self.result_identity_sha256,
            "source_fact": self.source_fact.to_dict(),
            "source_result": _read_result_to_dict(self.source_fact.result),
            "cohort_pin": self.source_fact.cohort_pin.to_dict(),
            "source_fact_identity_sha256": self.source_fact_identity_sha256,
            "projected_fact": self.projected_fact.to_dict(),
            "projected_fact_identity_sha256": self.projected_fact_identity_sha256,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketMonthlyRevenueYoyBatchCandidateV2:
    """尚未完成全 cohort 驗證的投影批次；不代表完整 index。"""

    session_identity_sha256: str
    batch_index: int
    stock_codes: tuple[str, ...]
    result_identity_sha256: tuple[str, ...]
    source_fact_identity_sha256: tuple[str, ...]
    projected_fact_identity_sha256: tuple[str, ...]
    complete: Literal[False] = False

    def __post_init__(self) -> None:
        _require_sha(self.session_identity_sha256, "batch_session_identity_invalid")
        if type(self.batch_index) is not int or self.batch_index < 0:
            _fail("batch_index_invalid")
        if type(self.complete) is not bool or self.complete:
            _fail("batch_must_be_incomplete")
        if (
            type(self.stock_codes) is not tuple
            or not self.stock_codes
            or len(self.stock_codes) > MAX_CODES_PER_BATCH
            or any(type(code) is not str or _STOCK_CODE_RE.fullmatch(code) is None
                   for code in self.stock_codes)
            or len(set(self.stock_codes)) != len(self.stock_codes)
        ):
            _fail("batch_codes_invalid")
        ledgers = (
            self.result_identity_sha256,
            self.source_fact_identity_sha256,
            self.projected_fact_identity_sha256,
        )
        if any(type(ledger) is not tuple or len(ledger) != len(self.stock_codes) for ledger in ledgers):
            _fail("batch_identity_count_invalid")
        for identity in (item for ledger in ledgers for item in ledger):
            _require_sha(identity, "batch_fact_identity_invalid")


class _IndexSealV2:
    __slots__ = ("identity_sha256", "session", "subject", "locked")

    def __init__(self, identity_sha256: str, session: object, *, issuer: object) -> None:
        if issuer is not _INDEX_ISSUER:
            _fail("index_seal_issuer_invalid")
        _require_sha(identity_sha256, "index_seal_identity_invalid")
        self.identity_sha256 = identity_sha256
        self.session = session
        self.subject: object | None = None
        self.locked = True

    def claim(self, subject: object) -> None:
        if self.subject is None:
            object.__setattr__(self, "subject", subject)
        elif self.subject is not subject:
            _fail("index_seal_subject_mismatch")

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "locked", False):
            raise AttributeError("index seal is immutable")
        object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True, init=False)
class DailyMarketMonthlyRevenueYoyCompactIndexV2:
    """綁定 private-issued V2 monthly finished token 的 immutable YoY index。"""

    read_session_identity_sha256: str
    finished_cohort_identity_sha256: str
    source_content_identity_sha256: str
    source_reference_identity_sha256: str
    source_reference_external_sha256: str
    source_clock: FundamentalSnapshotSourceClockV2
    declared_stock_codes: tuple[str, ...]
    entries: tuple[DailyMarketMonthlyRevenueYoyIndexEntryV2, ...]
    result_identity_by_stock: tuple[tuple[str, str], ...]
    fact_identity_by_stock: tuple[tuple[str, str], ...]
    projected_fact_identity_by_stock: tuple[tuple[str, str], ...]
    reader_result_status_counts: tuple[tuple[str, int], ...]
    fact_state_counts: tuple[tuple[str, int], ...]
    projected_state_counts: tuple[tuple[str, int], ...]
    index_identity_sha256: str
    source_scope: Literal["current_observed_only"]
    availability_status: Literal["cohort_hour_bound"]
    historical_pit_eligible: Literal[False]
    formal_pit_eligible: Literal[False]
    complete: Literal[True]
    _finished_cohort: FinishedDailyMarketMonthlyRevenueCohortV2 = field(
        repr=False, compare=False
    )
    _source_reference: DailyMarketMonthlyRevenueSourceReferenceV3 = field(
        repr=False, compare=False
    )
    _seal: _IndexSealV2 = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        read_session_identity_sha256: str,
        finished_cohort: FinishedDailyMarketMonthlyRevenueCohortV2,
        source_reference: DailyMarketMonthlyRevenueSourceReferenceV3,
        entries: tuple[DailyMarketMonthlyRevenueYoyIndexEntryV2, ...],
        session: object,
        _issuer: object | None = None,
    ) -> None:
        if _issuer is not _INDEX_ISSUER:
            _fail("index_must_be_reader_issued")
        if type(finished_cohort) is not FinishedDailyMarketMonthlyRevenueCohortV2:
            _fail("finished_cohort_invalid")
        if type(source_reference) is not DailyMarketMonthlyRevenueSourceReferenceV3:
            _fail("source_reference_invalid")
        source_clock = finished_cohort.source_clock
        if type(source_clock) is not FundamentalSnapshotSourceClockV2:
            _fail("source_clock_must_remain_v2")
        result_ledger = finished_cohort.result_identity_by_stock
        fact_ledger = finished_cohort.fact_identity_by_stock
        source_reference_sha = source_reference.external_reference_sha256
        fields: dict[str, object] = {
            "read_session_identity_sha256": read_session_identity_sha256,
            "finished_cohort_identity_sha256": finished_cohort.identity_sha256,
            "source_content_identity_sha256": finished_cohort.source_content_identity_sha256,
            "source_reference_identity_sha256": source_reference.identity_sha256,
            "source_reference_external_sha256": source_reference_sha,
            "source_clock": source_clock,
            "declared_stock_codes": finished_cohort.declared_stock_codes,
            "entries": entries,
            "result_identity_by_stock": result_ledger,
            "fact_identity_by_stock": fact_ledger,
            "projected_fact_identity_by_stock": tuple(
                (entry.stock_code, entry.projected_fact_identity_sha256)
                for entry in entries
            ),
            "reader_result_status_counts": finished_cohort.reader_result_status_counts,
            "fact_state_counts": finished_cohort.fact_state_counts,
            "projected_state_counts": _projected_state_counts(entries),
            "source_scope": "current_observed_only",
            "availability_status": "cohort_hour_bound",
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "complete": True,
            "_finished_cohort": finished_cohort,
            "_source_reference": source_reference,
        }
        for name, value in fields.items():
            object.__setattr__(self, name, value)
        identity = _index_identity_payload(self)
        object.__setattr__(self, "index_identity_sha256", _sha256_json(identity))
        seal = _IndexSealV2(self.index_identity_sha256, session, issuer=_INDEX_ISSUER)
        object.__setattr__(self, "_seal", seal)
        seal.claim(self)
        self._validate_issued(session)

    @property
    def is_reader_issued(self) -> bool:
        try:
            self._validate_issued(self._seal.session)
        except (TypeError, ValueError, AttributeError):
            return False
        return True

    @property
    def decision_cutoff(self) -> datetime:
        return self.source_clock.decision_cutoff

    @property
    def cohort_pin(self) -> DailyMonthlyRevenueCohortPin:
        return self.source_clock.cohort_pin

    def _validate_issued(self, session: object) -> None:
        if type(self._seal) is not _IndexSealV2 or self._seal.session is not session:
            _fail("index_not_reader_issued")
        if self._seal.subject is not self:
            _fail("index_seal_subject_mismatch")
        if (
            type(session) is not DailyMarketMonthlyRevenueYoyIndexSessionV2
            or session._state not in {"open", "finished"}
            or (session._finished_index is not None and session._finished_index is not self)
            or (session._finished_cohort is not None
                and session._finished_cohort is not self._finished_cohort)
            or (session._source_reference is not None
                and session._source_reference != self._source_reference)
            or self.read_session_identity_sha256 != session.read_session_identity_sha256
            or self.source_clock is not self._finished_cohort.source_clock
            or type(self.source_clock) is not FundamentalSnapshotSourceClockV2
            or self.finished_cohort_identity_sha256 != self._finished_cohort.identity_sha256
            or self.source_content_identity_sha256
            != self._finished_cohort.source_content_identity_sha256
            or self.source_reference_identity_sha256 != self._source_reference.identity_sha256
            or self.source_reference_external_sha256
            != self._source_reference.external_reference_sha256
            or self.declared_stock_codes != session.declared_stock_codes
            or tuple(entry.stock_code for entry in self.entries) != self.declared_stock_codes
            or self.result_identity_by_stock != self._finished_cohort.result_identity_by_stock
            or self.fact_identity_by_stock != self._finished_cohort.fact_identity_by_stock
            or self.projected_fact_identity_by_stock
            != tuple(
                (entry.stock_code, entry.projected_fact_identity_sha256)
                for entry in self.entries
            )
            or tuple((entry.stock_code, entry.result_identity_sha256) for entry in self.entries)
            != self.result_identity_by_stock
            or tuple((entry.stock_code, entry.source_fact.identity_sha256) for entry in self.entries)
            != self.fact_identity_by_stock
            or self.reader_result_status_counts
            != self._finished_cohort.reader_result_status_counts
            or self.fact_state_counts != self._finished_cohort.fact_state_counts
            or self.projected_state_counts != _projected_state_counts(self.entries)
            or tuple(entry.source_fact for entry in self.entries)
            != self._finished_cohort.facts
            or self.source_scope != "current_observed_only"
            or self.availability_status != "cohort_hour_bound"
            or self.historical_pit_eligible is not False
            or self.formal_pit_eligible is not False
            or self.complete is not True
            or self._seal.identity_sha256 != self.index_identity_sha256
            or _sha256_json(_index_identity_payload(self)) != self.index_identity_sha256
        ):
            _fail("index_not_reader_issued")
        expected_reference = DailyMarketMonthlyRevenueSourceReferenceV3.from_finished(
            self._finished_cohort,
            upstream_reference=self._finished_cohort.upstream_reference,
        )
        if expected_reference != self._source_reference:
            _fail("index_source_reference_not_bound_to_finished_token")

    def require_reader_issued(self, session: object) -> None:
        self._validate_issued(session)

    def validated_entries_for_reader(
        self,
        session: object,
    ) -> tuple[DailyMarketMonthlyRevenueYoyIndexEntryV2, ...]:
        self._validate_issued(session)
        return self.entries

    def entry_for(self, stock_code: str) -> DailyMarketMonthlyRevenueYoyIndexEntryV2 | None:
        self._validate_issued(self._seal.session)
        if type(stock_code) is not str:
            _fail("stock_code_invalid")
        low = 0
        high = len(self.entries)
        while low < high:
            middle = (low + high) // 2
            code = self.entries[middle].stock_code
            if code < stock_code:
                low = middle + 1
            else:
                high = middle
        if low < len(self.entries) and self.entries[low].stock_code == stock_code:
            return self.entries[low]
        return None

    def to_dict(self) -> dict[str, object]:
        self._validate_issued(self._seal.session)
        payload = _index_identity_payload(self)
        payload["source_reference"] = self._source_reference.to_dict()
        payload["index_identity_sha256"] = self.index_identity_sha256
        return payload

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > _MAX_INDEX_JSON_BYTES:
            _fail("index_payload_exceeds_size_limit")
        return raw.decode("utf-8")


def _index_identity_payload(index: DailyMarketMonthlyRevenueYoyCompactIndexV2) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_MONTHLY_REVENUE_YOY_INDEX_SCHEMA_V2,
        "read_session_identity_sha256": index.read_session_identity_sha256,
        "finished_cohort_identity_sha256": index.finished_cohort_identity_sha256,
        "source_content_identity_sha256": index.source_content_identity_sha256,
        "source_reference_identity_sha256": index.source_reference_identity_sha256,
        "source_reference_external_sha256": index.source_reference_external_sha256,
        "source_clock": index.source_clock.to_dict(),
        "source_clock_identity_sha256": index.source_clock.identity_sha256,
        "declared_stock_codes": list(index.declared_stock_codes),
        "result_identity_by_stock": [list(item) for item in index.result_identity_by_stock],
        "fact_identity_by_stock": [list(item) for item in index.fact_identity_by_stock],
        "projected_fact_identity_by_stock": [
            list(item) for item in index.projected_fact_identity_by_stock
        ],
        "reader_result_status_counts": [list(item) for item in index.reader_result_status_counts],
        "fact_state_counts": [list(item) for item in index.fact_state_counts],
        "projected_state_counts": [list(item) for item in index.projected_state_counts],
        "entries": [entry.to_dict() for entry in index.entries],
        "method_id": SELECTION_REVENUE_YOY_METHOD_ID,
        "method_version": SELECTION_REVENUE_YOY_METHOD_VERSION,
        "source_scope": "current_observed_only",
        "availability_status": "cohort_hour_bound",
        "official_available_at": None,
        "historical_pit_eligible": False,
        "formal_pit_eligible": False,
        "complete": True,
    }


class DailyMarketMonthlyRevenueYoyIndexSessionV2:
    """以同一 V2 source session 實際批次投影全清冊 YoY index。"""

    def __init__(
        self,
        *,
        provider: RecommendationCurrentFundamentalProvider,
        daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
        source_session: DailyMarketMonthlyRevenueReadSessionV2,
        stock_codes: tuple[str, ...],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None,
        cancel_event: Event,
        expected_source_reference: DailyMarketMonthlyRevenueSourceReferenceV3 | None = None,
    ) -> None:
        if type(provider) is not RecommendationCurrentFundamentalProvider:
            _fail("provider_invalid")
        if type(daily_monthly_cohort_reader) is not DailyMonthlyRevenueCohortReader:
            _fail("daily_cohort_reader_invalid")
        if type(source_session) is not DailyMarketMonthlyRevenueReadSessionV2:
            _fail("source_session_invalid")
        if (
            provider.daily_source_snapshot_reader is not daily_monthly_cohort_reader
            or source_session.declared_stock_codes != stock_codes
            or source_session.decision_cutoff.astimezone(timezone.utc)
            != cutoff_at.astimezone(timezone.utc)
        ):
            _fail("source_session_binding_mismatch")
        self._provider = provider
        self._reader = daily_monthly_cohort_reader
        self._initial_pin = daily_monthly_cohort_reader.pin
        self._source_session = source_session
        self._stock_codes = stock_codes
        self._cutoff_at = cutoff_at
        self._cancel_callback = cancel_callback
        self._cancel_event = cancel_event
        self._owner_thread_id = get_ident()
        self._expected_source_reference = expected_source_reference
        self._batches: list[DailyMarketMonthlyRevenueYoyBatchCandidateV2] = []
        self._entries_by_code: dict[str, DailyMarketMonthlyRevenueYoyIndexEntryV2] = {}
        self._next_index = 0
        self._publication_lock = Lock()
        self._state: Literal["open", "finished", "failed", "cancelled"] = "open"
        self._finished_cohort: FinishedDailyMarketMonthlyRevenueCohortV2 | None = None
        self._source_reference: DailyMarketMonthlyRevenueSourceReferenceV3 | None = None
        self._finished_index: DailyMarketMonthlyRevenueYoyCompactIndexV2 | None = None
        self._session_identity_sha256 = _sha256_json({
            "schema_version": "daily-market-monthly-revenue-yoy-index-session.v2",
            "source_snapshot_id": source_session.snapshot_id,
            "source_snapshot_root": str(source_session.snapshot_root),
            "declared_stock_codes": list(stock_codes),
            "decision_cutoff": _datetime_text(cutoff_at),
            "cohort_sha256": self._initial_pin.cohort_sha256,
            "method_id": SELECTION_REVENUE_YOY_METHOD_ID,
            "method_version": SELECTION_REVENUE_YOY_METHOD_VERSION,
        })

    @classmethod
    def open(
        cls,
        provider: RecommendationCurrentFundamentalProvider,
        *,
        daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
        snapshot_root: Path | str,
        stock_codes: Sequence[str],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketMonthlyRevenueYoyIndexSessionV2:
        codes = tuple(sorted(_normalize_codes(
            stock_codes,
            maximum=MAX_STOCK_CODES,
            allow_empty=False,
        )))
        cutoff = _normalize_cutoff(cutoff_at)
        event = Event()
        _strict_cancel(cancel_callback, event)
        try:
            source_session = DailyMarketMonthlyRevenueReadSessionV2.open(
                provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                snapshot_root=snapshot_root,
                stock_codes=codes,
                cutoff_at=cutoff,
                cancel_callback=cancel_callback,
            )
        except DailyMarketMonthlyRevenueReadCancelledV2 as exc:
            raise DailyMarketMonthlyRevenueYoyIndexCancelled("source_open_cancelled") from exc
        except (DailyMarketMonthlyRevenueReadSessionV2Error, OSError, TypeError, ValueError) as exc:
            raise DailyMarketMonthlyRevenueYoyIndexError(
                f"source_open_failed:{type(exc).__name__}"
            ) from exc
        try:
            result = cls(
                provider=provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                source_session=source_session,
                stock_codes=codes,
                cutoff_at=cutoff,
                cancel_callback=cancel_callback,
                cancel_event=event,
            )
            return result
        except BaseException as exc:
            _raise_with_source_cleanup(exc, source_session, "open_and_cleanup_failed")

    @classmethod
    def open_exact(
        cls,
        provider: RecommendationCurrentFundamentalProvider,
        *,
        daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
        snapshot_root: Path | str,
        source_reference: DailyMarketMonthlyRevenueSourceReferenceV3 | str | bytes,
        expected_reference_sha256: str,
        stock_codes: Sequence[str],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketMonthlyRevenueYoyIndexSessionV2:
        codes = tuple(sorted(_normalize_codes(
            stock_codes,
            maximum=MAX_STOCK_CODES,
            allow_empty=False,
        )))
        cutoff = _normalize_cutoff(cutoff_at)
        event = Event()
        _strict_cancel(cancel_callback, event)
        if type(source_reference) is DailyMarketMonthlyRevenueSourceReferenceV3:
            raw_reference: str | bytes = source_reference.to_json()
        elif type(source_reference) is str:
            raw_reference = source_reference
        elif type(source_reference) is bytes:
            raw_reference = source_reference
        else:
            _fail("source_reference_invalid")
        try:
            unverified = decode_daily_market_monthly_revenue_source_reference_v3(
                raw_reference,
                expected_reference_sha256=expected_reference_sha256,
            )
        except (TypeError, ValueError) as exc:
            raise DailyMarketMonthlyRevenueYoyIndexError(
                f"source_reference_decode_failed:{type(exc).__name__}"
            ) from exc
        if type(unverified.reference) is not DailyMarketMonthlyRevenueSourceReferenceV3:
            _fail("source_reference_decode_returned_unexpected_type")
        expected_source_reference = unverified.reference
        try:
            source_session = DailyMarketMonthlyRevenueReadSessionV2.open_exact(
                provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                snapshot_root=snapshot_root,
                source_reference=raw_reference,
                expected_reference_sha256=expected_reference_sha256,
                stock_codes=codes,
                cutoff_at=cutoff,
                cancel_callback=cancel_callback,
            )
        except DailyMarketMonthlyRevenueReadCancelledV2 as exc:
            raise DailyMarketMonthlyRevenueYoyIndexCancelled(
                "source_exact_open_cancelled"
            ) from exc
        except (DailyMarketMonthlyRevenueReadSessionV2Error, OSError, TypeError, ValueError) as exc:
            raise DailyMarketMonthlyRevenueYoyIndexError(
                f"source_exact_open_failed:{type(exc).__name__}"
            ) from exc
        try:
            result = cls(
                provider=provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                source_session=source_session,
                stock_codes=codes,
                cutoff_at=cutoff,
                cancel_callback=cancel_callback,
                cancel_event=event,
                expected_source_reference=(
                    expected_source_reference
                ),
            )
            _strict_cancel(cancel_callback, event)
            return result
        except BaseException as exc:
            _raise_with_source_cleanup(exc, source_session, "exact_open_and_cleanup_failed")

    @classmethod
    def open_exact_archived(
        cls,
        provider: RecommendationCurrentFundamentalProvider,
        *,
        daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
        snapshot_root: Path | str,
        source_reference: DailyMarketMonthlyRevenueSourceReferenceV3 | str | bytes,
        expected_reference_sha256: str,
        raw_archive_reference: FundamentalReadSnapshotRawArchiveReferenceV2 | str | bytes,
        expected_archive_reference_sha256: str,
        stock_codes: Sequence[str],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketMonthlyRevenueYoyIndexSessionV2:
        """以固定 V3 reference 與自含 raw archive 重開 YoY index source。"""

        codes = tuple(sorted(_normalize_codes(
            stock_codes,
            maximum=MAX_STOCK_CODES,
            allow_empty=False,
        )))
        cutoff = _normalize_cutoff(cutoff_at)
        event = Event()
        _strict_cancel(cancel_callback, event)
        if type(source_reference) is DailyMarketMonthlyRevenueSourceReferenceV3:
            raw_reference: str | bytes = source_reference.to_json()
        elif type(source_reference) is str or type(source_reference) is bytes:
            raw_reference = source_reference
        else:
            _fail("source_reference_invalid")
        try:
            unverified = decode_daily_market_monthly_revenue_source_reference_v3(
                raw_reference,
                expected_reference_sha256=expected_reference_sha256,
            )
        except (TypeError, ValueError) as exc:
            raise DailyMarketMonthlyRevenueYoyIndexError(
                f"source_reference_decode_failed:{type(exc).__name__}:{exc}"
            ) from exc
        if type(unverified.reference) is not DailyMarketMonthlyRevenueSourceReferenceV3:
            _fail("source_reference_decode_returned_unexpected_type")
        expected_source_reference = unverified.reference
        try:
            source_session = DailyMarketMonthlyRevenueReadSessionV2.open_exact_archived(
                provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                snapshot_root=snapshot_root,
                source_reference=raw_reference,
                expected_reference_sha256=expected_reference_sha256,
                raw_archive_reference=raw_archive_reference,
                expected_archive_reference_sha256=expected_archive_reference_sha256,
                stock_codes=codes,
                cutoff_at=cutoff,
                cancel_callback=cancel_callback,
            )
        except DailyMarketMonthlyRevenueReadCancelledV2 as exc:
            raise DailyMarketMonthlyRevenueYoyIndexCancelled(
                "source_archived_exact_open_cancelled"
            ) from exc
        except (DailyMarketMonthlyRevenueReadSessionV2Error, OSError, TypeError, ValueError) as exc:
            raise DailyMarketMonthlyRevenueYoyIndexError(
                f"source_archived_exact_open_failed:{type(exc).__name__}:{exc}"
            ) from exc
        try:
            result = cls(
                provider=provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                source_session=source_session,
                stock_codes=codes,
                cutoff_at=cutoff,
                cancel_callback=cancel_callback,
                cancel_event=event,
                expected_source_reference=expected_source_reference,
            )
            _strict_cancel(cancel_callback, event)
            return result
        except BaseException as exc:
            _raise_with_source_cleanup(
                exc,
                source_session,
                "archived_exact_open_and_cleanup_failed",
            )

    @property
    def read_session_identity_sha256(self) -> str:
        return self._session_identity_sha256

    @property
    def declared_stock_codes(self) -> tuple[str, ...]:
        return self._stock_codes

    @property
    def decision_cutoff(self) -> datetime:
        return self._cutoff_at

    @property
    def source_clock(self) -> FundamentalSnapshotSourceClockV2 | None:
        finished = self._finished_cohort
        return finished.source_clock if finished is not None else None

    @property
    def finished(self) -> bool:
        return self._state == "finished" and self._finished_index is not None

    @property
    def closed(self) -> bool:
        return self._source_session.closed

    @property
    def processed_stock_codes(self) -> tuple[str, ...]:
        self._require_owner()
        return tuple(self._entries_by_code)

    @property
    def read_status_counts(self) -> tuple[tuple[str, int], ...]:
        self._require_owner()
        finished = self._finished_cohort
        if finished is not None:
            return finished.reader_result_status_counts
        facts = tuple(entry.source_fact for entry in self._entries_by_code.values())
        return _status_counts(facts)

    @property
    def source_reference(self) -> DailyMarketMonthlyRevenueSourceReferenceV3:
        self._require_owner()
        if not self.finished:
            _fail("source_reference_requires_finished_index_session")
        reference = self._source_session.source_reference
        if type(reference) is not DailyMarketMonthlyRevenueSourceReferenceV3:
            _fail("source_reference_not_v3")
        if self._source_reference is None or reference != self._source_reference:
            _fail("source_reference_changed_after_index_publication")
        return reference

    def archive_monthly_raw_sources(
        self,
        archive_parent: Path | str,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> FundamentalReadSnapshotRawArchiveReferenceV2:
        """封存已完成 index 所固定的原 snapshot 與月營收原件。"""

        self._require_owner()
        if not self.finished:
            _fail("raw_archive_requires_finished_index_session")
        reference = self.source_reference
        archive_reference = self._source_session.archive_monthly_raw_sources(
            archive_parent,
            cancel_callback=cancel_callback,
        )
        if (
            type(archive_reference) is not FundamentalReadSnapshotRawArchiveReferenceV2
            or archive_reference.snapshot_reference != reference.upstream_reference
            or archive_reference.snapshot_reference_sha256
            != reference.upstream_reference_sha256
        ):
            _fail("raw_archive_snapshot_reference_mismatch")
        return archive_reference

    @property
    def index(self) -> DailyMarketMonthlyRevenueYoyCompactIndexV2:
        self._require_owner()
        if self._finished_index is None:
            _fail("index_not_finished")
        self._finished_index.require_reader_issued(self)
        return self._finished_index

    def validated_entries(
        self,
    ) -> tuple[DailyMarketMonthlyRevenueYoyIndexEntryV2, ...]:
        index = self.index
        return index.validated_entries_for_reader(self)

    def load_batch(
        self,
        stock_codes: Sequence[str],
    ) -> DailyMarketMonthlyRevenueYoyBatchCandidateV2:
        self._require_owner()
        self._require_open()
        try:
            _strict_cancel(self._cancel_callback, self._cancel_event)
            codes = _normalize_codes(
                stock_codes,
                maximum=MAX_CODES_PER_BATCH,
                allow_empty=False,
            )
            expected = self._stock_codes[self._next_index:self._next_index + len(codes)]
            if codes != expected:
                _fail("batch_order_or_scope_mismatch")
            source_batch = self._source_session.load_batch(codes)
            if (
                type(source_batch) is not DailyMarketMonthlyRevenueBatchCandidateV2
                or source_batch.complete is not False
                or source_batch.stock_codes != codes
                or source_batch.batch_index != len(self._batches)
                or len(source_batch.facts) != len(codes)
                or len(source_batch.result_identity_sha256) != len(codes)
                or source_batch.cohort_sha256 != self._initial_pin.cohort_sha256
            ):
                _fail("source_batch_shape_or_pin_mismatch")
            entries: list[DailyMarketMonthlyRevenueYoyIndexEntryV2] = []
            for code, source_fact, result_identity in zip(
                codes,
                source_batch.facts,
                source_batch.result_identity_sha256,
                strict=True,
            ):
                _strict_cancel(self._cancel_callback, self._cancel_event)
                if (
                    type(source_fact) is not DailyMarketMonthlyRevenueFactV2
                    or source_fact.stock_code != code
                    or source_fact.result_identity_sha256 != result_identity
                    or source_fact.cohort_pin != self._initial_pin
                    or source_fact.source_kind != "daily_monthly_revenue_cohort"
                    or _datetime_text(source_fact.result.cutoff_at)
                    != _datetime_text(self._cutoff_at)
                ):
                    _fail("source_fact_identity_clock_or_pin_mismatch")
                projected = project_selection_monthly_revenue_yoy_v2(source_fact)
                if type(projected) is not SelectionMonthlyRevenueYoYFactV2:
                    _fail("projection_returned_unexpected_type")
                if (
                    projected.stock_code != code
                    or projected.decision_cutoff is None
                    or _datetime_text(projected.decision_cutoff)
                    != _datetime_text(self._cutoff_at)
                    or projected.method_id != SELECTION_REVENUE_YOY_METHOD_ID
                    or projected.method_version != SELECTION_REVENUE_YOY_METHOD_VERSION
                    or projected.source_scope != "current_observed_only"
                    or projected.source_fact_identity_sha256 != source_fact.identity_sha256
                    or projected.historical_pit_eligible is not False
                    or projected.formal_pit_eligible is not False
                ):
                    _fail("projected_fact_source_scope_mismatch")
                entries.append(DailyMarketMonthlyRevenueYoyIndexEntryV2(
                    stock_code=code,
                    result_identity_sha256=result_identity,
                    source_fact=source_fact,
                    projected_fact=projected,
                ))
            _strict_cancel(self._cancel_callback, self._cancel_event)
            if any(code in self._entries_by_code for code in codes):
                _fail("duplicate_projected_stock")
            frozen_entries = tuple(entries)
            candidate = DailyMarketMonthlyRevenueYoyBatchCandidateV2(
                session_identity_sha256=self._session_identity_sha256,
                batch_index=source_batch.batch_index,
                stock_codes=codes,
                result_identity_sha256=source_batch.result_identity_sha256,
                source_fact_identity_sha256=tuple(
                    entry.source_fact.identity_sha256 for entry in frozen_entries
                ),
                projected_fact_identity_sha256=tuple(
                    entry.projected_fact_identity_sha256 for entry in frozen_entries
                ),
            )
            for entry in frozen_entries:
                self._entries_by_code[entry.stock_code] = entry
            self._batches.append(candidate)
            self._next_index += len(codes)
            _strict_cancel(self._cancel_callback, self._cancel_event)
            return candidate
        except BaseException as exc:
            with self._publication_lock:
                self._state = (
                    "cancelled"
                    if isinstance(exc, (DailyMarketMonthlyRevenueReadCancelledV2,
                                       DailyMarketMonthlyRevenueYoyIndexCancelled))
                    else "failed"
                )
            _raise_with_source_cleanup(exc, self._source_session, "batch_failed_and_cleanup_failed")

    def finish(self) -> DailyMarketMonthlyRevenueYoyCompactIndexV2:
        self._require_owner()
        if self._finished_index is not None:
            self._finished_index.require_reader_issued(self)
            return self._finished_index
        self._require_open()
        try:
            _strict_cancel(self._cancel_callback, self._cancel_event)
            if self._next_index != len(self._stock_codes):
                _fail("cohort_incomplete")
            finished = self._source_session.finish()
            if type(finished) is not FinishedDailyMarketMonthlyRevenueCohortV2:
                _fail("finished_source_cohort_type_mismatch")
            clock = finished.source_clock
            if type(clock) is not FundamentalSnapshotSourceClockV2:
                _fail("finished_source_clock_must_remain_v2")
            if (
                finished.declared_stock_codes != self._stock_codes
                or finished.snapshot_finished.complete is not True
                or finished.snapshot_finished.processed_stock_codes != self._stock_codes
                or clock.declared_stock_codes != self._stock_codes
                or _datetime_text(clock.decision_cutoff) != _datetime_text(self._cutoff_at)
                or clock.cohort_pin != self._initial_pin
                or clock.cohort_pin.available_hour.astimezone(timezone.utc)
                > clock.decision_cutoff.astimezone(timezone.utc)
                or clock.source_scope != "current_observed_only"
                or clock.availability_status != "cohort_hour_bound"
                or clock.historical_pit_eligible is not False
                or clock.formal_pit_eligible is not False
                or finished.historical_pit_eligible is not False
                or finished.formal_pit_eligible is not False
            ):
                _fail("finished_source_clock_or_scope_mismatch")
            entries = tuple(self._entries_by_code[code] for code in self._stock_codes)
            if tuple(self._entries_by_code) != self._stock_codes:
                _fail("projected_code_order_mismatch")
            self._verify_batch_ledger(entries)
            if tuple(entry.source_fact for entry in entries) != finished.facts:
                _fail("finished_source_fact_mismatch")
            for entry in entries:
                _strict_cancel(self._cancel_callback, self._cancel_event)
                projected = project_selection_monthly_revenue_yoy_v2(entry.source_fact)
                if (
                    type(projected) is not SelectionMonthlyRevenueYoYFactV2
                    or projected.identity_sha256 != entry.projected_fact.identity_sha256
                ):
                    _fail("finished_projected_fact_reissue_mismatch")
            result_ledger = tuple(
                (entry.stock_code, entry.result_identity_sha256) for entry in entries
            )
            fact_ledger = tuple(
                (entry.stock_code, entry.source_fact.identity_sha256) for entry in entries
            )
            if (
                result_ledger != finished.result_identity_by_stock
                or fact_ledger != finished.fact_identity_by_stock
                or _status_counts(tuple(entry.source_fact for entry in entries))
                != finished.reader_result_status_counts
                or _fact_state_counts(tuple(entry.source_fact for entry in entries))
                != finished.fact_state_counts
                or tuple(code for code, _ in result_ledger) != self._stock_codes
                or tuple(code for code, _ in fact_ledger) != self._stock_codes
            ):
                _fail("finished_source_ledgers_or_denominators_mismatch")
            _strict_cancel(self._cancel_callback, self._cancel_event)
            reference = self._source_session.source_reference
            if type(reference) is not DailyMarketMonthlyRevenueSourceReferenceV3:
                _fail("finished_source_reference_not_v3")
            if (
                reference.declared_stock_codes != self._stock_codes
                or reference.decision_cutoff != _datetime_text(self._cutoff_at)
                or reference.cohort_pin != self._initial_pin
                or reference.source_content_identity_sha256
                != finished.source_content_identity_sha256
                or reference.result_identity_by_stock != finished.result_identity_by_stock
                or reference.fact_identity_by_stock != finished.fact_identity_by_stock
                or reference.reader_result_status_counts
                != finished.reader_result_status_counts
                or reference.fact_state_counts != finished.fact_state_counts
                or reference.availability_status != "cohort_hour_bound"
                or reference.historical_pit_eligible is not False
                or reference.formal_pit_eligible is not False
            ):
                _fail("finished_source_reference_mismatch")
            expected = self._expected_source_reference
            if expected is not None and (
                reference.source_content_identity_sha256
                != expected.source_content_identity_sha256
                or reference.result_identity_by_stock != expected.result_identity_by_stock
                or reference.fact_identity_by_stock != expected.fact_identity_by_stock
                or reference.reader_result_status_counts != expected.reader_result_status_counts
                or reference.fact_state_counts != expected.fact_state_counts
                or reference.cohort_pin != expected.cohort_pin
                or reference.declared_stock_codes != expected.declared_stock_codes
                or reference.decision_cutoff != expected.decision_cutoff
            ):
                _fail("exact_source_reference_reissue_mismatch")
            index = DailyMarketMonthlyRevenueYoyCompactIndexV2(
                read_session_identity_sha256=self._session_identity_sha256,
                finished_cohort=finished,
                source_reference=reference,
                entries=entries,
                session=self,
                _issuer=_INDEX_ISSUER,
            )
            _strict_cancel(self._cancel_callback, self._cancel_event)
            with self._publication_lock:
                if self._cancel_event.is_set() or self._state != "open":
                    raise DailyMarketMonthlyRevenueYoyIndexCancelled("cancelled_before_publication")
                self._finished_cohort = finished
                self._source_reference = reference
                self._finished_index = index
                self._state = "finished"
            return index
        except DailyMarketMonthlyRevenueReadCancelledV2 as exc:
            with self._publication_lock:
                self._state = "cancelled"
            _raise_with_source_cleanup(
                DailyMarketMonthlyRevenueYoyIndexCancelled("source_finish_cancelled"),
                self._source_session,
                "finish_failed_and_cleanup_failed",
                primary_cause=exc,
            )
        except BaseException as exc:
            with self._publication_lock:
                self._state = (
                    "cancelled"
                    if isinstance(exc, DailyMarketMonthlyRevenueYoyIndexCancelled)
                    else "failed"
                )
            _raise_with_source_cleanup(exc, self._source_session, "finish_failed_and_cleanup_failed")

    def cancel(self) -> bool:
        with self._publication_lock:
            if self._state == "finished":
                return False
            if self._state in {"failed", "cancelled"}:
                return True
            self._state = "cancelled"
            self._cancel_event.set()
        return self._source_session.cancel()

    def close(self) -> None:
        self._require_owner()
        with self._publication_lock:
            if self._state == "open":
                self._state = "cancelled"
                self._cancel_event.set()
        self._source_session.close()
        if not self._source_session.closed:
            _fail("source_connection_not_closed")

    def __enter__(self) -> DailyMarketMonthlyRevenueYoyIndexSessionV2:
        self._require_owner()
        self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            self.close()
        except BaseException as cleanup_exc:
            if exc is not None:
                raise DailyMarketMonthlyRevenueYoyIndexError(
                    "context_exit_cleanup_failed"
                ) from BaseExceptionGroup(
                    "primary context exception and V2 YoY cleanup failure",
                    [exc, cleanup_exc],
                )
            raise
        return False

    def _require_owner(self) -> None:
        if get_ident() != self._owner_thread_id:
            _fail("wrong_owner_thread")

    def _require_open(self) -> None:
        if self._state != "open":
            _fail("session_not_open")

    def _verify_batch_ledger(
        self,
        entries: tuple[DailyMarketMonthlyRevenueYoyIndexEntryV2, ...],
    ) -> None:
        flattened: list[str] = []
        offset = 0
        for batch_index, batch in enumerate(self._batches):
            if (
                type(batch) is not DailyMarketMonthlyRevenueYoyBatchCandidateV2
                or batch.session_identity_sha256 != self._session_identity_sha256
                or batch.batch_index != batch_index
                or batch.complete is not False
                or not batch.stock_codes
                or batch.stock_codes
                != self._stock_codes[offset:offset + len(batch.stock_codes)]
            ):
                _fail("batch_ledger_identity_or_order_mismatch")
            end = offset + len(batch.stock_codes)
            expected_entries = entries[offset:end]
            if (
                len(expected_entries) != len(batch.stock_codes)
                or batch.result_identity_sha256
                != tuple(entry.result_identity_sha256 for entry in expected_entries)
                or batch.source_fact_identity_sha256
                != tuple(entry.source_fact_identity_sha256 for entry in expected_entries)
                or batch.projected_fact_identity_sha256
                != tuple(entry.projected_fact_identity_sha256 for entry in expected_entries)
            ):
                _fail("batch_ledger_content_mismatch")
            flattened.extend(batch.stock_codes)
            offset = end
        if tuple(flattened) != self._stock_codes:
            _fail("batch_ledger_coverage_incomplete")


def _raise_with_source_cleanup(
    primary: BaseException,
    source_session: DailyMarketMonthlyRevenueReadSessionV2,
    cleanup_code: str,
    *,
    primary_cause: BaseException | None = None,
) -> NoReturn:
    try:
        source_session.close()
        if not source_session.closed:
            _fail("source_connection_not_closed")
    except BaseException as cleanup_exc:
        raise DailyMarketMonthlyRevenueYoyIndexError(cleanup_code) from BaseExceptionGroup(
            "primary V2 YoY failure and source cleanup failure",
            [primary, cleanup_exc],
        )
    if isinstance(primary, DailyMarketMonthlyRevenueYoyIndexCancelled):
        if primary_cause is not None:
            raise primary from primary_cause
        raise primary
    if isinstance(primary, DailyMarketMonthlyRevenueReadCancelledV2):
        raise DailyMarketMonthlyRevenueYoyIndexCancelled(
            "source_operation_cancelled"
        ) from primary
    if isinstance(primary, DailyMarketMonthlyRevenueReadIncompleteV2):
        raise DailyMarketMonthlyRevenueYoyIndexError("cohort_incomplete") from primary
    if isinstance(primary, DailyMarketMonthlyRevenueReadSessionV2Error):
        raise DailyMarketMonthlyRevenueYoyIndexError(
            f"source_operation_failed:{type(primary).__name__}"
        ) from primary
    if isinstance(primary, DailyMarketMonthlyRevenueYoyIndexError):
        raise primary
    raise primary


__all__ = [
    "DAILY_MARKET_MONTHLY_REVENUE_YOY_INDEX_ENTRY_SCHEMA_V2",
    "DAILY_MARKET_MONTHLY_REVENUE_YOY_INDEX_SCHEMA_V2",
    "DailyMarketMonthlyRevenueYoyBatchCandidateV2",
    "DailyMarketMonthlyRevenueYoyIndexCancelled",
    "DailyMarketMonthlyRevenueYoyIndexEntryV2",
    "DailyMarketMonthlyRevenueYoyIndexError",
    "DailyMarketMonthlyRevenueYoyIndexSessionV2",
    "DailyMarketMonthlyRevenueYoyCompactIndexV2",
]
