"""以已完成的月營收來源清冊發行 current-only YoY compact index。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from threading import get_ident
from typing import Literal, NoReturn, cast

from data_module.daily_market_monthly_revenue_read_session_v1 import (
    DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY_V1,
    DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE_V1,
    MAX_CODES_PER_BATCH,
    DailyMarketMonthlyRevenueFinishedCohortV1,
    DailyMarketMonthlyRevenueReadCancelled,
    DailyMarketMonthlyRevenueReadSessionError,
    DailyMarketMonthlyRevenueReadSessionV1,
    DailyMarketMonthlyRevenueSourceReferenceV2,
    MonthlyRevenueReadFactV1,
)
from data_module.fundamental_read_snapshot import FundamentalSnapshotSourceClock
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    RecommendationCurrentFundamentalProvider,
)
from decision_module.factors.selection_fundamental_chip_rules import (
    SELECTION_REVENUE_YOY_METHOD_ID,
    SELECTION_REVENUE_YOY_METHOD_VERSION,
    SelectionMonthlyRevenueYoYFact,
    project_selection_monthly_revenue_yoy,
)


DAILY_MARKET_MONTHLY_REVENUE_YOY_INDEX_SCHEMA_V1 = (
    "daily-market-monthly-revenue-yoy-index.v1"
)
DAILY_MARKET_MONTHLY_REVENUE_YOY_INDEX_ENTRY_SCHEMA_V1 = (
    "daily-market-monthly-revenue-yoy-index-entry.v1"
)
_STOCK_CODE_RE = re.compile(r"^[0-9]{4,6}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_INDEX_ISSUER = object()


class DailyMarketMonthlyRevenueYoyIndexError(ValueError):
    """月營收 YoY index 的穩定拒絕錯誤。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"monthly_revenue_yoy_index_v1_{code}")


class DailyMarketMonthlyRevenueYoyIndexCancelled(
    DailyMarketMonthlyRevenueYoyIndexError
):
    """月營收 YoY index 操作收到 cooperative cancellation。"""


def _fail(code: str) -> NoReturn:
    raise DailyMarketMonthlyRevenueYoyIndexError(code)


def _sha256_json(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketMonthlyRevenueYoyIndexError("json_invalid") from exc
    return hashlib.sha256(encoded).hexdigest()


def _require_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return cast(str, value)


def _strict_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketMonthlyRevenueYoyIndexError(
            "cancel_check_failed"
        ) from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if value:
        raise DailyMarketMonthlyRevenueYoyIndexCancelled("cancelled")


def _datetime_text(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        _fail("cutoff_not_aware")
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class DailyMarketMonthlyRevenueYoyBatchCandidateV1:
    """未完成全 cohort 驗證的投影批次；不得作為完整 index 使用。"""

    session_identity_sha256: str
    batch_index: int
    stock_codes: tuple[str, ...]
    result_identity_sha256: tuple[str, ...]
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
            or any(type(code) is not str or _STOCK_CODE_RE.fullmatch(code) is None for code in self.stock_codes)
            or len(set(self.stock_codes)) != len(self.stock_codes)
        ):
            _fail("batch_codes_invalid")
        if (
            type(self.result_identity_sha256) is not tuple
            or type(self.projected_fact_identity_sha256) is not tuple
            or len(self.result_identity_sha256) != len(self.stock_codes)
            or len(self.projected_fact_identity_sha256) != len(self.stock_codes)
        ):
            _fail("batch_identity_count_invalid")
        for identity in (*self.result_identity_sha256, *self.projected_fact_identity_sha256):
            _require_sha(identity, "batch_fact_identity_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketMonthlyRevenueYoyIndexEntryV1:
    """單碼 YoY 投影與 source reader 完成後的原始 provider fact。"""

    stock_code: str
    result_identity_sha256: str
    projected_fact: SelectionMonthlyRevenueYoYFact
    source_fact: MonthlyRevenueReadFactV1

    def __post_init__(self) -> None:
        if type(self.stock_code) is not str or _STOCK_CODE_RE.fullmatch(self.stock_code) is None:
            _fail("entry_stock_code_invalid")
        _require_sha(self.result_identity_sha256, "entry_result_identity_invalid")
        if (
            type(self.projected_fact) is not SelectionMonthlyRevenueYoYFact
            or type(self.source_fact) is not MonthlyRevenueReadFactV1
            or self.projected_fact.stock_code != self.stock_code
            or self.source_fact.stock_code != self.stock_code
        ):
            _fail("entry_fact_binding_invalid")
        if (
            self.projected_fact.method_id != SELECTION_REVENUE_YOY_METHOD_ID
            or self.projected_fact.method_version != SELECTION_REVENUE_YOY_METHOD_VERSION
            or self.projected_fact.source_scope != "current_observed_only"
            or self.projected_fact.historical_pit_eligible is not False
            or self.projected_fact.formal_pit_eligible is not False
        ):
            _fail("entry_method_scope_invalid")

    @property
    def state(self) -> Literal["observed", "unknown"]:
        return self.projected_fact.state

    @property
    def growth_percent(self):
        return self.projected_fact.growth_percent

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return self.projected_fact.reason_codes

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": DAILY_MARKET_MONTHLY_REVENUE_YOY_INDEX_ENTRY_SCHEMA_V1,
            "stock_code": self.stock_code,
            "result_identity_sha256": self.result_identity_sha256,
            "projected_fact": self.projected_fact.to_dict(),
            "projected_fact_identity_sha256": self.projected_fact.identity_sha256,
            "source_fact": self.source_fact.to_dict(),
            "source_fact_identity_sha256": self.source_fact.identity_sha256,
            "raw_comparator_evidence": (
                self.source_fact.raw_comparator_evidence.to_dict()
                if self.source_fact.raw_comparator_evidence is not None
                else None
            ),
            "raw_comparator_classification": (
                self.source_fact.raw_comparator_evidence.classification
                if self.source_fact.raw_comparator_evidence is not None
                else None
            ),
        }


class _IndexSealV1:
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
class DailyMarketMonthlyRevenueYoyCompactIndexV1:
    """由同一 source session 的 complete result ledger 發行的 immutable index。"""

    read_session_identity_sha256: str
    finished_cohort_identity_sha256: str
    source_clock: FundamentalSnapshotSourceClock
    declared_stock_codes: tuple[str, ...]
    entries: tuple[DailyMarketMonthlyRevenueYoyIndexEntryV1, ...]
    result_identity_by_stock: tuple[tuple[str, str], ...]
    index_identity_sha256: str
    source_scope: Literal["current_observed_only"]
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]
    formal_pit_eligible: Literal[False]
    _seal: _IndexSealV1 = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        read_session_identity_sha256: str,
        finished_cohort_identity_sha256: str,
        source_clock: FundamentalSnapshotSourceClock,
        declared_stock_codes: tuple[str, ...],
        entries: tuple[DailyMarketMonthlyRevenueYoyIndexEntryV1, ...],
        result_identity_by_stock: tuple[tuple[str, str], ...],
        session: object,
        _issuer: object | None = None,
    ) -> None:
        if _issuer is not _INDEX_ISSUER:
            _fail("index_must_be_reader_issued")
        object.__setattr__(self, "read_session_identity_sha256", read_session_identity_sha256)
        object.__setattr__(self, "finished_cohort_identity_sha256", finished_cohort_identity_sha256)
        object.__setattr__(self, "source_clock", source_clock)
        object.__setattr__(self, "declared_stock_codes", declared_stock_codes)
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "result_identity_by_stock", result_identity_by_stock)
        object.__setattr__(self, "source_scope", "current_observed_only")
        object.__setattr__(self, "availability_status", "unknown")
        object.__setattr__(self, "historical_pit_eligible", False)
        object.__setattr__(self, "formal_pit_eligible", False)
        identity = _index_identity(self)
        object.__setattr__(self, "index_identity_sha256", identity)
        seal = _IndexSealV1(identity, session, issuer=_INDEX_ISSUER)
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
        value = getattr(self.source_clock, "decision_cutoff", None)
        if type(value) is not datetime:
            _fail("source_clock_cutoff_invalid")
        return value

    @property
    def source_clock_identity_sha256(self) -> str:
        value = getattr(self.source_clock, "identity_sha256", None)
        return _require_sha(value, "source_clock_identity_invalid")

    @property
    def cohort_identity_sha256(self) -> str:
        return _require_sha(self.finished_cohort_identity_sha256, "cohort_identity_invalid")

    def _validate_issued(self, session: object) -> None:
        if type(self._seal) is not _IndexSealV1 or self._seal.session is not session:
            _fail("index_not_reader_issued")
        if self._seal.subject is not self:
            _fail("index_seal_subject_mismatch")
        if (
            type(session) is not DailyMarketMonthlyRevenueYoyIndexSessionV1
            or (session._finished_index is not None and session._finished_index is not self)
            or self.read_session_identity_sha256 != session.read_session_identity_sha256
            or session._finished_cohort is None
            or self.source_clock is not session._finished_cohort.source_clock
            or self.finished_cohort_identity_sha256 != session._finished_cohort.identity_sha256
            or self.declared_stock_codes != session.declared_stock_codes
            or tuple(entry.stock_code for entry in self.entries) != self.declared_stock_codes
            or self.result_identity_by_stock != session._finished_cohort.reader_result_identity_by_stock
            or self.source_scope != DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE_V1
            or self.availability_status != DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY_V1
            or self.historical_pit_eligible is not False
            or self.formal_pit_eligible is not False
            or self._seal.identity_sha256 != self.index_identity_sha256
            or _index_identity(self) != self.index_identity_sha256
        ):
            _fail("index_not_reader_issued")

    def require_reader_issued(self, session: object) -> None:
        self._validate_issued(session)

    def validated_entries_for_reader(
        self,
        session: object,
    ) -> tuple[DailyMarketMonthlyRevenueYoyIndexEntryV1, ...]:
        """一次完整核驗後供同一全母體操作線性合併使用。"""
        self._validate_issued(session)
        return self.entries

    def entry_for(self, stock_code: str) -> DailyMarketMonthlyRevenueYoyIndexEntryV1 | None:
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
        source_to_dict = getattr(self.source_clock, "to_dict", None)
        if not callable(source_to_dict):
            _fail("source_clock_invalid")
        return {
            "schema_version": DAILY_MARKET_MONTHLY_REVENUE_YOY_INDEX_SCHEMA_V1,
            "read_session_identity_sha256": self.read_session_identity_sha256,
            "finished_cohort_identity_sha256": self.finished_cohort_identity_sha256,
            "source_clock": source_to_dict(),
            "source_clock_identity_sha256": self.source_clock_identity_sha256,
            "declared_stock_codes": list(self.declared_stock_codes),
            "result_identity_by_stock": [list(item) for item in self.result_identity_by_stock],
            "entries": [entry.to_dict() for entry in self.entries],
            "method_id": SELECTION_REVENUE_YOY_METHOD_ID,
            "method_version": SELECTION_REVENUE_YOY_METHOD_VERSION,
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "official_available_at": None,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "complete": True,
            "index_identity_sha256": self.index_identity_sha256,
        }


def _index_identity(index: DailyMarketMonthlyRevenueYoyCompactIndexV1) -> str:
    source_clock = getattr(index, "source_clock", None)
    source_to_dict = getattr(source_clock, "to_dict", None)
    if not callable(source_to_dict):
        _fail("source_clock_invalid")
    return _sha256_json({
        "schema_version": DAILY_MARKET_MONTHLY_REVENUE_YOY_INDEX_SCHEMA_V1,
        "read_session_identity_sha256": index.read_session_identity_sha256,
        "finished_cohort_identity_sha256": index.finished_cohort_identity_sha256,
        "source_clock": source_to_dict(),
        "source_clock_identity_sha256": getattr(source_clock, "identity_sha256", None),
        "declared_stock_codes": list(index.declared_stock_codes),
        "result_identity_by_stock": [list(item) for item in index.result_identity_by_stock],
        "entries": [entry.to_dict() for entry in index.entries],
        "method_id": SELECTION_REVENUE_YOY_METHOD_ID,
        "method_version": SELECTION_REVENUE_YOY_METHOD_VERSION,
        "source_scope": "current_observed_only",
        "availability_status": "unknown",
        "official_available_at": None,
        "historical_pit_eligible": False,
        "formal_pit_eligible": False,
        "complete": True,
    })


class DailyMarketMonthlyRevenueYoyIndexSessionV1:
    """包裝真 source reader，僅以其實際批次結果建立可發行的 YoY index。"""

    def __init__(self, source_session: DailyMarketMonthlyRevenueReadSessionV1) -> None:
        if type(source_session) is not DailyMarketMonthlyRevenueReadSessionV1:
            _fail("source_session_invalid")
        self._source_session = source_session
        self._owner_thread_id = get_ident()
        self._session_identity_sha256 = _sha256_json({
            "schema_version": "daily-market-monthly-revenue-yoy-index-session.v1",
            "source_snapshot_id": source_session.snapshot_id,
            "source_reader_database_path": str(source_session.reader_database_path),
            "declared_stock_codes": list(source_session.declared_stock_codes),
            "decision_cutoff": _datetime_text(source_session.decision_cutoff),
            "method_id": SELECTION_REVENUE_YOY_METHOD_ID,
            "method_version": SELECTION_REVENUE_YOY_METHOD_VERSION,
        })
        self._projected_by_code: dict[str, tuple[str, SelectionMonthlyRevenueYoYFact]] = {}
        self._next_index = 0
        self._batch_index = 0
        self._state: Literal["open", "finished", "failed", "cancelled"] = "open"
        self._finished_cohort: DailyMarketMonthlyRevenueFinishedCohortV1 | None = None
        self._finished_index: DailyMarketMonthlyRevenueYoyCompactIndexV1 | None = None

    @classmethod
    def open(
        cls,
        provider: RecommendationCurrentFundamentalProvider,
        *,
        snapshot_root: Path | str,
        stock_codes: Sequence[str],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketMonthlyRevenueYoyIndexSessionV1:
        _strict_cancel(cancel_callback)
        try:
            source_session = DailyMarketMonthlyRevenueReadSessionV1.open(
                provider,
                snapshot_root=snapshot_root,
                stock_codes=stock_codes,
                cutoff_at=cutoff_at,
                cancel_callback=cancel_callback,
            )
        except DailyMarketMonthlyRevenueReadCancelled as exc:
            raise DailyMarketMonthlyRevenueYoyIndexCancelled("source_open_cancelled") from exc
        except DailyMarketRevenueReadErrorTypes as exc:
            raise DailyMarketMonthlyRevenueYoyIndexError(
                f"source_open_failed:{type(exc).__name__}:{exc}"
            ) from exc
        return cls(source_session)

    @classmethod
    def open_exact_archived(
        cls,
        provider: RecommendationCurrentFundamentalProvider,
        *,
        snapshot_root: Path | str,
        source_reference: DailyMarketMonthlyRevenueSourceReferenceV2 | str | bytes,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketMonthlyRevenueYoyIndexSessionV1:
        """以 V2 raw archive 與 sealed snapshot 建立新的 exact index 工作階段。"""

        _strict_cancel(cancel_callback)
        try:
            source_session = DailyMarketMonthlyRevenueReadSessionV1.open_exact_archived(
                provider,
                snapshot_root=snapshot_root,
                source_reference=source_reference,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )
        except DailyMarketMonthlyRevenueReadCancelled as exc:
            raise DailyMarketMonthlyRevenueYoyIndexCancelled(
                "source_archived_open_cancelled"
            ) from exc
        except DailyMarketRevenueReadErrorTypes as exc:
            raise DailyMarketMonthlyRevenueYoyIndexError(
                f"source_archived_open_failed:{type(exc).__name__}:{exc}"
            ) from exc
        try:
            _strict_cancel(cancel_callback)
            return cls(source_session)
        except BaseException as exc:
            try:
                source_session.close()
                if not source_session.closed:
                    raise DailyMarketMonthlyRevenueReadSessionError(
                        "archived_source_close_did_not_complete"
                    )
            except BaseException as cleanup_exc:
                raise DailyMarketMonthlyRevenueYoyIndexError(
                    "source_archived_open_and_cleanup_failed"
                ) from BaseExceptionGroup(
                    "archived index open failure and source cleanup failure",
                    [exc, cleanup_exc],
                )
            if isinstance(exc, DailyMarketMonthlyRevenueYoyIndexCancelled):
                raise
            raise

    @property
    def read_session_identity_sha256(self) -> str:
        return self._session_identity_sha256

    @property
    def reader_database_path(self) -> Path:
        """回傳本次 operation 專屬唯讀副本路徑，不是歷史原始 DB 路徑。"""

        self._require_owner()
        return self._source_session.reader_database_path

    @property
    def declared_stock_codes(self) -> tuple[str, ...]:
        return self._source_session.declared_stock_codes

    @property
    def decision_cutoff(self) -> datetime:
        return self._source_session.decision_cutoff

    @property
    def source_reference(self) -> DailyMarketMonthlyRevenueSourceReferenceV2:
        """回傳 exact archived session 完成後由來源 reader 核發的 V2 reference。"""

        self._require_owner()
        if not self.finished:
            _fail("source_reference_requires_finished_index_session")
        reference = self._source_session.source_reference
        if type(reference) is not DailyMarketMonthlyRevenueSourceReferenceV2:
            _fail("archived_source_reference_not_v2")
        return reference

    def archive_source(
        self,
        archive_parent: Path | str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketMonthlyRevenueSourceReferenceV2:
        """以已完成來源封存 raw captures，供之後 exact 重開使用。"""

        self._require_owner()
        if not self.finished:
            _fail("archive_requires_finished_index_session")
        _strict_cancel(cancel_callback)
        try:
            reference = self._source_session.archive_source(
                archive_parent,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )
        except DailyMarketMonthlyRevenueReadCancelled as exc:
            raise DailyMarketMonthlyRevenueYoyIndexCancelled(
                "source_archive_cancelled"
            ) from exc
        except DailyMarketRevenueReadErrorTypes as exc:
            raise DailyMarketMonthlyRevenueYoyIndexError(
                f"source_archive_failed:{type(exc).__name__}:{exc}"
            ) from exc
        if type(reference) is not DailyMarketMonthlyRevenueSourceReferenceV2:
            _fail("source_archive_reference_not_v2")
        return reference

    @property
    def finished(self) -> bool:
        return self._state == "finished"

    @property
    def closed(self) -> bool:
        return self._source_session.closed

    @property
    def index(self) -> DailyMarketMonthlyRevenueYoyCompactIndexV1:
        return self.validated_index_and_entries()[0]

    def validated_index_and_entries(
        self,
    ) -> tuple[
        DailyMarketMonthlyRevenueYoyCompactIndexV1,
        tuple[DailyMarketMonthlyRevenueYoyIndexEntryV1, ...],
    ]:
        """一次核驗發行錨點後回傳 immutable index 與列，供 reader 合併。"""
        if self._finished_index is None:
            _fail("index_not_finished")
        self._finished_index.require_reader_issued(self)
        return self._finished_index, self._finished_index.entries

    def load_batch(
        self,
        stock_codes: Sequence[str],
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketMonthlyRevenueYoyBatchCandidateV1:
        self._require_owner()
        self._require_open()
        try:
            _strict_cancel(cancel_callback)
            codes = _normalize_codes(stock_codes, maximum=MAX_CODES_PER_BATCH, allow_empty=False)
            expected = self.declared_stock_codes[self._next_index:self._next_index + len(codes)]
            if codes != expected:
                _fail("batch_order_or_scope_mismatch")
            batch = self._source_session.load_batch(codes)
            if (
                len(batch.results) != len(codes)
                or batch.stock_codes != codes
                or batch.batch_index != self._batch_index
            ):
                _fail("source_batch_shape_mismatch")
            result_ids = tuple(batch.result_identity_sha256)
            if len(result_ids) != len(codes):
                _fail("source_batch_identity_count_mismatch")
            projected: list[SelectionMonthlyRevenueYoYFact] = []
            for code, result, result_identity in zip(codes, batch.results, result_ids, strict=True):
                _strict_cancel(cancel_callback)
                if type(result) is not CurrentMonthlyRevenueReadResult or result.stock_code != code:
                    _fail("source_batch_result_scope_mismatch")
                _require_sha(result_identity, "source_result_identity_invalid")
                fact = project_selection_monthly_revenue_yoy(result)
                if (
                    type(fact) is not SelectionMonthlyRevenueYoYFact
                    or fact.stock_code != code
                    or fact.decision_cutoff is None
                    or fact.decision_cutoff.astimezone(timezone.utc)
                    != self.decision_cutoff.astimezone(timezone.utc)
                    or fact.availability not in {"verified", "unknown", "unavailable"}
                    or fact.historical_pit_eligible is not False
                    or fact.formal_pit_eligible is not False
                ):
                    _fail("projected_fact_source_scope_mismatch")
                projected.append(fact)
                _strict_cancel(cancel_callback)
            if any(code in self._projected_by_code for code in codes):
                _fail("duplicate_projected_stock")
            for code, identity, fact in zip(codes, result_ids, projected, strict=True):
                self._projected_by_code[code] = (identity, fact)
            self._next_index += len(codes)
            self._batch_index += 1
            _strict_cancel(cancel_callback)
            return DailyMarketMonthlyRevenueYoyBatchCandidateV1(
                session_identity_sha256=self._session_identity_sha256,
                batch_index=batch.batch_index,
                stock_codes=codes,
                result_identity_sha256=result_ids,
                projected_fact_identity_sha256=tuple(item.identity_sha256 for item in projected),
            )
        except BaseException as exc:
            self._state = (
                "cancelled"
                if isinstance(exc, (DailyMarketMonthlyRevenueReadCancelled,
                                    DailyMarketMonthlyRevenueYoyIndexCancelled))
                else "failed"
            )
            cleanup_exc = self._close_source_session()
            if cleanup_exc is not None:
                raise DailyMarketMonthlyRevenueYoyIndexError(
                    "batch_failed_and_cleanup_failed"
                ) from BaseExceptionGroup(
                    "primary monthly revenue batch failure and source cleanup failure",
                    [exc, cleanup_exc],
                )
            if isinstance(exc, DailyMarketMonthlyRevenueReadCancelled):
                raise DailyMarketMonthlyRevenueYoyIndexCancelled(
                    "source_batch_cancelled"
                ) from exc
            raise

    def finish(
        self,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketMonthlyRevenueYoyCompactIndexV1:
        self._require_owner()
        if self._finished_index is not None:
            self._finished_index.require_reader_issued(self)
            return self._finished_index
        self._require_open()
        try:
            _strict_cancel(cancel_callback)
            if self._next_index != len(self.declared_stock_codes):
                _fail("cohort_incomplete")
            cohort = self._source_session.finish()
            if (
                type(cohort) is not DailyMarketMonthlyRevenueFinishedCohortV1
                or not cohort.is_reader_issued
                or cohort.complete is not True
                or cohort.processed_stock_codes != self.declared_stock_codes
                or cohort.source_clock.declared_stock_codes != self.declared_stock_codes
                or cohort.source_clock.decision_cutoff.astimezone(timezone.utc)
                != self.decision_cutoff.astimezone(timezone.utc)
                or cohort.source_clock.availability_status != "unknown"
                or cohort.source_clock.historical_pit_eligible is not False
                or cohort.source_clock.formal_pit_eligible is not False
            ):
                _fail("finished_source_cohort_mismatch")
            if tuple(code for code, _ in cohort.reader_result_identity_by_stock) != self.declared_stock_codes:
                _fail("finished_ledger_code_order_mismatch")
            if tuple(self._projected_by_code) != self.declared_stock_codes:
                _fail("projected_code_order_mismatch")
            if tuple((code, self._projected_by_code[code][0]) for code in self.declared_stock_codes) != cohort.reader_result_identity_by_stock:
                _fail("finished_result_identity_ledger_mismatch")
            if tuple(fact.stock_code for fact in cohort.facts) != self.declared_stock_codes:
                _fail("finished_fact_code_order_mismatch")
            self._finished_cohort = cohort
            entries = tuple(
                DailyMarketMonthlyRevenueYoyIndexEntryV1(
                    stock_code=code,
                    result_identity_sha256=self._projected_by_code[code][0],
                    projected_fact=self._projected_by_code[code][1],
                    source_fact=source_fact,
                )
                for code, source_fact in zip(self.declared_stock_codes, cohort.facts, strict=True)
            )
            _strict_cancel(cancel_callback)
            index = DailyMarketMonthlyRevenueYoyCompactIndexV1(
                read_session_identity_sha256=self._session_identity_sha256,
                finished_cohort_identity_sha256=cohort.identity_sha256,
                source_clock=cohort.source_clock,
                declared_stock_codes=self.declared_stock_codes,
                entries=entries,
                result_identity_by_stock=cohort.reader_result_identity_by_stock,
                session=self,
                _issuer=_INDEX_ISSUER,
            )
            _strict_cancel(cancel_callback)
            self._finished_index = index
            self._state = "finished"
            return index
        except BaseException as exc:
            self._state = (
                "cancelled"
                if isinstance(exc, (DailyMarketMonthlyRevenueReadCancelled,
                                    DailyMarketMonthlyRevenueYoyIndexCancelled))
                else "failed"
            )
            cleanup_exc = self._close_source_session()
            if cleanup_exc is not None:
                code = (
                    "cohort_incomplete_and_cleanup_failed"
                    if isinstance(exc, DailyMarketMonthlyRevenueYoyIndexError)
                    and exc.code == "monthly_revenue_yoy_index_v1_cohort_incomplete"
                    else "finish_failed_and_cleanup_failed"
                )
                raise DailyMarketMonthlyRevenueYoyIndexError(code) from BaseExceptionGroup(
                    "primary monthly revenue finish failure and source cleanup failure",
                    [exc, cleanup_exc],
                )
            if isinstance(exc, DailyMarketMonthlyRevenueReadCancelled):
                raise DailyMarketMonthlyRevenueYoyIndexCancelled(
                    "source_finish_cancelled"
                ) from exc
            raise

    def cancel(self) -> bool:
        if self._state == "finished":
            return False
        if self._state in {"failed", "cancelled"}:
            return True
        self._state = "cancelled"
        return self._source_session.cancel()

    def close(self) -> None:
        self._require_owner()
        if not self._source_session.closed:
            self._source_session.close()
        if not self._source_session.closed:
            _fail("source_connection_not_closed")
        if self._state == "open":
            self._state = "cancelled"

    def _close_source_session(self) -> BaseException | None:
        """只在 owner thread 呼叫 close，並把清理異常交給呼叫端保留。"""
        self._require_owner()
        try:
            self._source_session.close()
            if not self._source_session.closed:
                return DailyMarketMonthlyRevenueYoyIndexError(
                    "source_connection_not_closed"
                )
        except BaseException as exc:
            return exc
        return None

    def _require_owner(self) -> None:
        if get_ident() != self._owner_thread_id:
            _fail("wrong_owner_thread")

    def _require_open(self) -> None:
        if self._state != "open":
            _fail("session_not_open")


DailyMarketRevenueReadErrorTypes = (
    DailyMarketMonthlyRevenueReadSessionError,
    OSError,
    TypeError,
    ValueError,
)


def _normalize_codes(
    stock_codes: Sequence[str],
    *,
    maximum: int,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(stock_codes, (str, bytes, bytearray)) or not isinstance(stock_codes, Sequence):
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

