"""以每日雙市場來源 cohort 與 fundamental V2 snapshot 讀取月營收全 cohort。

本模組只保存既有 provider 的 typed 結果，不讀取 SQLite、不挑選 latest、
不重算月營收或 YoY。V3 reference 的 decoder 只驗輸入 bytes/hash；完成資格
須由本 session 在 exact upstream snapshot 與全部 facts 重讀後發行。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from threading import Event, Lock, get_ident
from typing import Callable, Literal, Sequence

from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
)
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    DailyMarketMonthlyRevenueFactV2,
    DailyMarketMonthlyRevenueSourceReferenceV3,
    FinishedDailyMarketMonthlyRevenueCohortV2,
    UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3,
    _issue_finished_daily_market_monthly_revenue_cohort_v2,
    decode_daily_market_monthly_revenue_source_reference_v3,
)
from data_module.fundamental_read_snapshot_cohort_v2 import (
    FundamentalReadSnapshotReferenceV2,
    FinishedFundamentalSnapshotReadCohortV2,
)
from data_module.fundamental_read_snapshot_daily_v2 import (
    FundamentalReadSnapshotSessionV2,
)
from data_module.fundamental_read_snapshot_raw_archive_v2 import (
    FundamentalReadSnapshotRawArchiveReferenceV2,
    decode_raw_archive_reference_v2,
)
from data_module.fundamental_read_snapshot_raw_archive_io_v2 import (
    _VerifiedArchivedSnapshotReferenceV2,
    verify_raw_archive_reference_v2,
)
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)
from data_module.selection_fact_readers import (
    FundamentalReadBatchCandidateV2,
    FundamentalReadSessionCancelled,
    MAX_CODES_PER_BATCH,
    MAX_STOCK_CODES,
)
from data_module.fundamental_read_snapshot import (
    FundamentalReadSnapshotCancelled,
    FundamentalReadSnapshotError,
)


DAILY_MARKET_MONTHLY_REVENUE_READ_SESSION_SCHEMA_V2 = (
    "daily-market-monthly-revenue-read-session.v2"
)
_STOCK_CODE_RE = re.compile(r"^[0-9]{4,6}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DailyMarketMonthlyRevenueReadSessionV2Error(RuntimeError):
    """V2 月營收消費 session 無法維持來源或完整 cohort 契約。"""


class DailyMarketMonthlyRevenueReadCancelledV2(DailyMarketMonthlyRevenueReadSessionV2Error):
    """V2 月營收讀取收到 cooperative cancellation。"""


class DailyMarketMonthlyRevenueReadIncompleteV2(DailyMarketMonthlyRevenueReadSessionV2Error):
    """宣告股票清冊尚未全部讀取，不能發行 finished token。"""


@dataclass(frozen=True, slots=True)
class DailyMarketMonthlyRevenueBatchCandidateV2:
    """尚未完成來源重驗的 provisional batch，不代表完整 cohort。"""

    session_identity_sha256: str
    batch_index: int
    stock_codes: tuple[str, ...]
    facts: tuple[DailyMarketMonthlyRevenueFactV2, ...]
    result_identity_sha256: tuple[str, ...]
    cohort_sha256: str
    complete: Literal[False] = False

    def __post_init__(self) -> None:
        if type(self.session_identity_sha256) is not str or not _SHA256_RE.fullmatch(
            self.session_identity_sha256
        ):
            raise ValueError("monthly_revenue_v2_batch_session_identity_invalid")
        if type(self.batch_index) is not int or self.batch_index < 0:
            raise ValueError("monthly_revenue_v2_batch_index_invalid")
        if type(self.stock_codes) is not tuple or not self.stock_codes:
            raise ValueError("monthly_revenue_v2_batch_codes_invalid")
        if len(self.stock_codes) > MAX_CODES_PER_BATCH:
            raise ValueError("monthly_revenue_v2_batch_too_large")
        if type(self.facts) is not tuple or len(self.facts) != len(self.stock_codes):
            raise ValueError("monthly_revenue_v2_batch_facts_mismatch")
        if (type(self.result_identity_sha256) is not tuple
                or len(self.result_identity_sha256) != len(self.stock_codes)):
            raise ValueError("monthly_revenue_v2_batch_result_identities_mismatch")
        if type(self.cohort_sha256) is not str or not _SHA256_RE.fullmatch(self.cohort_sha256):
            raise ValueError("monthly_revenue_v2_batch_cohort_sha_invalid")
        if self.complete is not False:
            raise ValueError("monthly_revenue_v2_batch_must_remain_provisional")
        for code, fact, identity in zip(
            self.stock_codes, self.facts, self.result_identity_sha256, strict=True
        ):
            if type(fact) is not DailyMarketMonthlyRevenueFactV2 or fact.stock_code != code:
                raise ValueError("monthly_revenue_v2_batch_fact_stock_mismatch")
            if fact.result_identity_sha256 != identity or fact.cohort_pin.cohort_sha256 != self.cohort_sha256:
                raise ValueError("monthly_revenue_v2_batch_fact_pin_or_identity_mismatch")


class DailyMarketMonthlyRevenueReadSessionV2:
    """由同一 verified daily reader 與 FundamentalReadSnapshotSessionV2 發行月營收 facts。"""

    def __init__(
        self,
        *,
        provider: RecommendationCurrentFundamentalProvider,
        daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
        snapshot_session: FundamentalReadSnapshotSessionV2,
        stock_codes: tuple[str, ...],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None,
        cancel_event: Event,
        expected_source_reference: DailyMarketMonthlyRevenueSourceReferenceV3 | None = None,
    ) -> None:
        if type(provider) is not RecommendationCurrentFundamentalProvider:
            raise TypeError("V2 provider 必須是 exact provider instance")
        if type(daily_monthly_cohort_reader) is not DailyMonthlyRevenueCohortReader:
            raise TypeError("V2 daily cohort reader 型別錯誤")
        if type(snapshot_session) is not FundamentalReadSnapshotSessionV2:
            raise TypeError("V2 fundamental snapshot session 型別錯誤")
        if provider.daily_source_snapshot_reader is not daily_monthly_cohort_reader:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_provider_reader_identity_mismatch"
            )
        if snapshot_session.declared_stock_codes != stock_codes:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_snapshot_declared_codes_mismatch"
            )
        self._provider = provider
        self._reader = daily_monthly_cohort_reader
        self._initial_pin = daily_monthly_cohort_reader.pin
        self._snapshot_session = snapshot_session
        self._stock_codes = stock_codes
        self._cutoff_at = cutoff_at
        self._cancel_callback = cancel_callback
        self._cancel_event = cancel_event
        self._owner_thread_id = get_ident()
        self._expected_source_reference = expected_source_reference
        self._batches: list[DailyMarketMonthlyRevenueBatchCandidateV2] = []
        self._next_index = 0
        self._operation_lock = Lock()
        self._publication_lock = Lock()
        self._state: Literal["open", "finished", "cancelled", "failed"] = "open"
        self._finished: FinishedDailyMarketMonthlyRevenueCohortV2 | None = None
        self._session_identity_sha256 = _canonical_sha256(
            {
                "schema_version": DAILY_MARKET_MONTHLY_REVENUE_READ_SESSION_SCHEMA_V2,
                "snapshot_id": snapshot_session.snapshot_id,
                "database_path": str(provider.db_file),
                "decision_cutoff": _datetime_text(cutoff_at),
                "declared_stock_codes": list(stock_codes),
                "cohort_sha256": self._initial_pin.cohort_sha256,
            }
        )

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
    ) -> DailyMarketMonthlyRevenueReadSessionV2:
        if type(provider) is not RecommendationCurrentFundamentalProvider:
            raise TypeError("provider 必須是 exact RecommendationCurrentFundamentalProvider")
        if type(daily_monthly_cohort_reader) is not DailyMonthlyRevenueCohortReader:
            raise TypeError("daily_monthly_cohort_reader 必須是 exact typed reader")
        if provider.daily_source_snapshot_reader is not daily_monthly_cohort_reader:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_provider_reader_identity_mismatch"
            )
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        codes = _normalize_stock_codes(stock_codes)
        cutoff = _require_aware_utc(cutoff_at)
        _verify_cohort_hour_bound(daily_monthly_cohort_reader.pin, cutoff)
        cancel_event = Event()

        def effective_cancel() -> bool:
            return _cancel_requested(cancel_event, cancel_callback)

        if effective_cancel():
            raise DailyMarketMonthlyRevenueReadCancelledV2(
                "monthly_revenue_v2_cancelled_before_open"
            )
        try:
            snapshot_session = FundamentalReadSnapshotSessionV2.open(
                provider,
                snapshot_root=snapshot_root,
                stock_codes=codes,
                cutoff_at=cutoff,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                cancel_callback=effective_cancel,
            )
        except (FundamentalReadSnapshotCancelled, FundamentalReadSessionCancelled) as exc:
            raise DailyMarketMonthlyRevenueReadCancelledV2(
                "monthly_revenue_v2_cancelled_during_upstream_open"
            ) from exc
        except FundamentalReadSnapshotError as exc:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                f"monthly_revenue_v2_upstream_open_failed:{type(exc).__name__}"
            ) from exc
        try:
            return cls(
                provider=provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                snapshot_session=snapshot_session,
                stock_codes=codes,
                cutoff_at=cutoff,
                cancel_callback=cancel_callback,
                cancel_event=cancel_event,
            )
        except BaseException as exc:
            try:
                snapshot_session.close()
            except BaseException as cleanup_exc:
                raise DailyMarketMonthlyRevenueReadSessionV2Error(
                    "monthly_revenue_v2_session_construction_and_cleanup_failed"
                ) from BaseExceptionGroup(
                    "monthly revenue V2 construction and upstream cleanup failure",
                    [exc, cleanup_exc],
                )
            raise

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
    ) -> DailyMarketMonthlyRevenueReadSessionV2:
        if type(provider) is not RecommendationCurrentFundamentalProvider:
            raise TypeError("provider 必須是 exact RecommendationCurrentFundamentalProvider")
        if type(daily_monthly_cohort_reader) is not DailyMonthlyRevenueCohortReader:
            raise TypeError("daily_monthly_cohort_reader 必須是 exact typed reader")
        if provider.daily_source_snapshot_reader is not daily_monthly_cohort_reader:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_provider_reader_identity_mismatch"
            )
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        if type(expected_reference_sha256) is not str or not _SHA256_RE.fullmatch(
            expected_reference_sha256
        ):
            raise ValueError("monthly_revenue_v3_external_reference_sha_invalid")
        raw_reference: str | bytes
        if type(source_reference) is DailyMarketMonthlyRevenueSourceReferenceV3:
            raw_reference = source_reference.to_json()
        elif type(source_reference) is str:
            raw_reference = source_reference
        elif type(source_reference) is bytes:
            raw_reference = source_reference
        else:
            raise TypeError("source_reference 必須是 typed V3 reference、str 或 bytes")
        unverified = decode_daily_market_monthly_revenue_source_reference_v3(
            raw_reference,
            expected_reference_sha256=expected_reference_sha256,
        )
        if type(unverified) is not UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v3_decoder_returned_unexpected_type"
            )
        reference = unverified.reference
        if type(reference) is not DailyMarketMonthlyRevenueSourceReferenceV3:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v3_unverified_reference_type_mismatch"
            )
        codes = _normalize_stock_codes(stock_codes)
        cutoff = _require_aware_utc(cutoff_at)
        _verify_cohort_hour_bound(daily_monthly_cohort_reader.pin, cutoff)
        _verify_cohort_hour_bound(reference.cohort_pin, cutoff)
        if (codes != reference.declared_stock_codes
                or _datetime_text(cutoff) != reference.decision_cutoff
                or daily_monthly_cohort_reader.pin != reference.cohort_pin
                or reference.upstream_reference.daily_cohort_sha256
                != reference.cohort_pin.cohort_sha256):
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v3_exact_clock_codes_or_cohort_mismatch"
            )
        cancel_event = Event()

        def effective_cancel() -> bool:
            return _cancel_requested(cancel_event, cancel_callback)

        if effective_cancel():
            raise DailyMarketMonthlyRevenueReadCancelledV2(
                "monthly_revenue_v2_cancelled_before_exact_open"
            )
        try:
            snapshot_session = FundamentalReadSnapshotSessionV2.open_exact(
                provider,
                snapshot_root=snapshot_root,
                source_reference=reference.upstream_reference,
                expected_reference_sha256=reference.upstream_reference_sha256,
                stock_codes=codes,
                cutoff_at=cutoff,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                cancel_callback=effective_cancel,
            )
        except (FundamentalReadSnapshotCancelled, FundamentalReadSessionCancelled) as exc:
            raise DailyMarketMonthlyRevenueReadCancelledV2(
                "monthly_revenue_v2_cancelled_during_exact_upstream_open"
            ) from exc
        except FundamentalReadSnapshotError as exc:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                f"monthly_revenue_v2_exact_upstream_open_failed:{type(exc).__name__}"
            ) from exc
        try:
            return cls(
                provider=provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                snapshot_session=snapshot_session,
                stock_codes=codes,
                cutoff_at=cutoff,
                cancel_callback=cancel_callback,
                cancel_event=cancel_event,
                expected_source_reference=reference,
            )
        except BaseException as exc:
            try:
                snapshot_session.close()
            except BaseException as cleanup_exc:
                raise DailyMarketMonthlyRevenueReadSessionV2Error(
                    "monthly_revenue_v2_exact_session_construction_and_cleanup_failed"
                ) from BaseExceptionGroup(
                    "monthly revenue V2 exact construction and upstream cleanup failure",
                    [exc, cleanup_exc],
                )
            raise

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
    ) -> DailyMarketMonthlyRevenueReadSessionV2:
        """由兩個外部 SHA 固定的 V3 月營收與自含原件 archive 重開。"""

        if type(provider) is not RecommendationCurrentFundamentalProvider:
            raise TypeError("provider 必須是 exact RecommendationCurrentFundamentalProvider")
        if type(daily_monthly_cohort_reader) is not DailyMonthlyRevenueCohortReader:
            raise TypeError("daily_monthly_cohort_reader 必須是 exact typed reader")
        if provider.daily_source_snapshot_reader is not daily_monthly_cohort_reader:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_provider_reader_identity_mismatch"
            )
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        if type(expected_reference_sha256) is not str or not _SHA256_RE.fullmatch(
            expected_reference_sha256
        ):
            raise ValueError("monthly_revenue_v3_external_reference_sha_invalid")
        if type(expected_archive_reference_sha256) is not str or not _SHA256_RE.fullmatch(
            expected_archive_reference_sha256
        ):
            raise ValueError("monthly_revenue_v2_external_archive_sha_invalid")

        raw_reference: str | bytes
        if type(source_reference) is DailyMarketMonthlyRevenueSourceReferenceV3:
            raw_reference = source_reference.to_json()
        elif type(source_reference) is str or type(source_reference) is bytes:
            raw_reference = source_reference
        else:
            raise TypeError("source_reference 必須是 typed V3 reference、str 或 bytes")
        try:
            unverified = decode_daily_market_monthly_revenue_source_reference_v3(
                raw_reference,
                expected_reference_sha256=expected_reference_sha256,
            )
        except (TypeError, ValueError) as exc:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                f"monthly_revenue_v3_exact_archive_reference_invalid:{exc}"
            ) from exc
        if type(unverified) is not UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v3_decoder_returned_unexpected_type"
            )
        reference = unverified.reference
        if type(reference) is not DailyMarketMonthlyRevenueSourceReferenceV3:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v3_unverified_reference_type_mismatch"
            )

        raw_archive: str | bytes
        if type(raw_archive_reference) is FundamentalReadSnapshotRawArchiveReferenceV2:
            raw_archive = raw_archive_reference.to_json()
        elif type(raw_archive_reference) is str or type(raw_archive_reference) is bytes:
            raw_archive = raw_archive_reference
        else:
            raise TypeError(
                "raw_archive_reference 必須是 typed V2 archive reference、str 或 bytes"
            )
        try:
            unverified_archive = decode_raw_archive_reference_v2(
                raw_archive,
                expected_reference_sha256=expected_archive_reference_sha256,
            )
        except (TypeError, ValueError) as exc:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                f"monthly_revenue_v2_archive_reference_invalid:{exc}"
            ) from exc
        if type(unverified_archive.reference) is not FundamentalReadSnapshotRawArchiveReferenceV2:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_archive_decoder_returned_unexpected_type"
            )
        archive_reference = unverified_archive.reference

        codes = _normalize_stock_codes(stock_codes)
        cutoff = _require_aware_utc(cutoff_at)
        _verify_cohort_hour_bound(daily_monthly_cohort_reader.pin, cutoff)
        _verify_cohort_hour_bound(reference.cohort_pin, cutoff)
        if (
            codes != reference.declared_stock_codes
            or _datetime_text(cutoff) != reference.decision_cutoff
            or daily_monthly_cohort_reader.pin != reference.cohort_pin
            or reference.upstream_reference != archive_reference.snapshot_reference
            or reference.upstream_reference_sha256
            != archive_reference.snapshot_reference_sha256
            or reference.upstream_reference.daily_cohort_sha256
            != reference.cohort_pin.cohort_sha256
        ):
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v3_archive_reference_or_scope_mismatch"
            )

        cancel_event = Event()

        def effective_cancel() -> bool:
            return _cancel_requested(cancel_event, cancel_callback)

        if effective_cancel():
            raise DailyMarketMonthlyRevenueReadCancelledV2(
                "monthly_revenue_v2_cancelled_before_archived_open"
            )
        try:
            verified = verify_raw_archive_reference_v2(
                archive_reference,
                expected_reference_sha256=expected_archive_reference_sha256,
                provider=provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                cancel_callback=effective_cancel,
            )
            if type(verified) is not _VerifiedArchivedSnapshotReferenceV2:
                raise DailyMarketMonthlyRevenueReadSessionV2Error(
                    "monthly_revenue_v2_archive_verifier_returned_unexpected_type"
                )
            snapshot = verified.snapshot
            clock = snapshot.source_clock
            if (
                verified.archive_reference != archive_reference
                or verified.external_reference_sha256
                != expected_archive_reference_sha256
                or snapshot.reference != reference.upstream_reference
                or snapshot.processed_stock_codes != codes
                or snapshot.result_identity_by_stock != reference.result_identity_by_stock
                or snapshot.result_status_counts != reference.reader_result_status_counts
                or clock.cohort_pin != reference.cohort_pin
                or clock.decision_cutoff != cutoff
                or clock.declared_stock_codes != codes
                or clock.source_content_identity_sha256
                != reference.upstream_reference.source_content_identity_sha256
            ):
                raise DailyMarketMonthlyRevenueReadSessionV2Error(
                    "monthly_revenue_v3_archive_snapshot_clock_or_ledger_mismatch"
                )
            snapshot_session = FundamentalReadSnapshotSessionV2.open_exact_archived(
                provider,
                snapshot_root=snapshot_root,
                raw_archive_reference=archive_reference,
                expected_archive_reference_sha256=expected_archive_reference_sha256,
                stock_codes=codes,
                cutoff_at=cutoff,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                cancel_callback=effective_cancel,
            )
        except (FundamentalReadSnapshotCancelled, FundamentalReadSessionCancelled) as exc:
            raise DailyMarketMonthlyRevenueReadCancelledV2(
                "monthly_revenue_v2_cancelled_during_archived_upstream_open"
            ) from exc
        except FundamentalReadSnapshotError as exc:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                f"monthly_revenue_v2_archived_upstream_open_failed:{exc}"
            ) from exc
        except OSError as exc:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                f"monthly_revenue_v2_archived_upstream_io_failed:{exc}"
            ) from exc
        except (TypeError, ValueError) as exc:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                f"monthly_revenue_v2_archived_upstream_reference_or_path_invalid:{exc}"
            ) from exc

        try:
            return cls(
                provider=provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                snapshot_session=snapshot_session,
                stock_codes=codes,
                cutoff_at=cutoff,
                cancel_callback=cancel_callback,
                cancel_event=cancel_event,
                expected_source_reference=reference,
            )
        except BaseException as exc:
            try:
                snapshot_session.close()
            except BaseException as cleanup_exc:
                raise DailyMarketMonthlyRevenueReadSessionV2Error(
                    "monthly_revenue_v2_archived_session_construction_and_cleanup_failed"
                ) from BaseExceptionGroup(
                    "monthly revenue V2 archived construction and upstream cleanup failure",
                    [exc, cleanup_exc],
                )
            raise

    @property
    def declared_stock_codes(self) -> tuple[str, ...]:
        return self._stock_codes

    @property
    def decision_cutoff(self) -> datetime:
        return self._cutoff_at

    @property
    def snapshot_id(self) -> str:
        return self._snapshot_session.snapshot_id

    @property
    def snapshot_root(self) -> Path:
        return self._snapshot_session.snapshot_root

    @property
    def closed(self) -> bool:
        return self._snapshot_session.closed

    @property
    def finished(self) -> bool:
        return self._state == "finished" and self._finished is not None

    @property
    def source_reference(self) -> DailyMarketMonthlyRevenueSourceReferenceV3:
        self._require_owner_thread()
        finished = self._finished
        if not self.finished or finished is None:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v3_reference_requires_finished_session"
            )
        upstream_reference = self._snapshot_session.source_reference
        if upstream_reference != finished.upstream_reference:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v3_finished_upstream_reference_mismatch"
            )
        reference = DailyMarketMonthlyRevenueSourceReferenceV3.from_finished(
            finished,
            upstream_reference=upstream_reference,
        )
        return reference

    def archive_monthly_raw_sources(
        self,
        archive_parent: Path | str,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> FundamentalReadSnapshotRawArchiveReferenceV2:
        """封存已完成 session 的原 snapshot 與月營收原件。"""

        self._require_owner_thread()
        if not self.finished:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_archive_requires_finished_session"
            )
        reference = self.source_reference
        archive_reference = self._snapshot_session.archive_monthly_raw_sources(
            archive_parent,
            cancel_callback=cancel_callback,
        )
        if (
            type(archive_reference) is not FundamentalReadSnapshotRawArchiveReferenceV2
            or archive_reference.snapshot_reference != reference.upstream_reference
            or archive_reference.snapshot_reference_sha256
            != reference.upstream_reference_sha256
        ):
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_archive_snapshot_reference_mismatch"
            )
        return archive_reference

    def load_batch(
        self,
        stock_codes: Sequence[str],
    ) -> DailyMarketMonthlyRevenueBatchCandidateV2:
        self._require_owner_thread()
        codes = _normalize_batch_codes(stock_codes)
        with self._operation_lock:
            self._require_open()
            expected = self._stock_codes[self._next_index:self._next_index + len(codes)]
            if codes != expected:
                raise ValueError("monthly_revenue_v2_batch_must_match_next_declared_codes")
            try:
                self._poll_cancel()
                self._verify_reader_pin()
                underlying = self._snapshot_session.load_batch(codes)
                if type(underlying) is not FundamentalReadBatchCandidateV2:
                    raise DailyMarketMonthlyRevenueReadSessionV2Error(
                        "monthly_revenue_v2_upstream_batch_type_mismatch"
                    )
                if (underlying.stock_codes != codes
                        or underlying.batch_index != len(self._batches)
                        or len(underlying.results) != len(codes)
                        or len(underlying.result_identity_sha256) != len(codes)
                        or underlying.cohort_sha256 != self._initial_pin.cohort_sha256):
                    raise DailyMarketMonthlyRevenueReadSessionV2Error(
                        "monthly_revenue_v2_upstream_batch_ledger_or_pin_mismatch"
                    )
                facts = tuple(
                    DailyMarketMonthlyRevenueFactV2(
                        result=result,
                        result_identity_sha256=identity,
                        cohort_pin=self._initial_pin,
                    )
                    for result, identity in zip(
                        underlying.results,
                        underlying.result_identity_sha256,
                        strict=True,
                    )
                )
                self._poll_cancel()
                self._verify_reader_pin()
                candidate = DailyMarketMonthlyRevenueBatchCandidateV2(
                    session_identity_sha256=self._session_identity_sha256,
                    batch_index=underlying.batch_index,
                    stock_codes=underlying.stock_codes,
                    facts=facts,
                    result_identity_sha256=underlying.result_identity_sha256,
                    cohort_sha256=underlying.cohort_sha256,
                )
                self._batches.append(candidate)
                self._next_index += len(codes)
                return candidate
            except BaseException as exc:
                self._mark_failed(exc)
                raise

    def finish(self) -> FinishedDailyMarketMonthlyRevenueCohortV2:
        self._require_owner_thread()
        with self._operation_lock:
            if self._finished is not None:
                self._require_open_or_finished()
                return self._finished
            self._require_open()
            if self._next_index != len(self._stock_codes):
                missing = len(self._stock_codes) - self._next_index
                incomplete = DailyMarketMonthlyRevenueReadIncompleteV2(
                    f"monthly_revenue_v2_cohort_incomplete:{missing}"
                )
                self._close_failed(incomplete)
                raise incomplete
            try:
                self._poll_cancel()
                self._verify_reader_pin()
                snapshot_finished = self._snapshot_session.finish()
                if type(snapshot_finished) is not FinishedFundamentalSnapshotReadCohortV2:
                    raise DailyMarketMonthlyRevenueReadSessionV2Error(
                        "monthly_revenue_v2_upstream_finished_type_mismatch"
                    )
                source_clock = snapshot_finished.source_clock
                if (snapshot_finished.complete is not True
                        or snapshot_finished.processed_stock_codes != self._stock_codes
                        or source_clock.declared_stock_codes != self._stock_codes
                        or source_clock.decision_cutoff != self._cutoff_at
                        or source_clock.cohort_pin != self._initial_pin
                        or source_clock.source_scope != "current_observed_only"
                        or source_clock.availability_status != "cohort_hour_bound"
                        or source_clock.historical_pit_eligible is not False
                        or source_clock.formal_pit_eligible is not False):
                    raise DailyMarketMonthlyRevenueReadSessionV2Error(
                        "monthly_revenue_v2_upstream_finished_clock_or_scope_mismatch"
                    )
                facts = self._flatten_facts()
                result_ledger = tuple(
                    (code, identity)
                    for batch in self._batches
                    for code, identity in zip(
                        batch.stock_codes,
                        batch.result_identity_sha256,
                        strict=True,
                    )
                )
                if result_ledger != snapshot_finished.result_identity_by_stock:
                    raise DailyMarketMonthlyRevenueReadSessionV2Error(
                        "monthly_revenue_v2_upstream_result_ledger_mismatch"
                    )
                self._poll_cancel()
                upstream_reference = self._snapshot_session.source_reference
                if (upstream_reference.source_content_identity_sha256
                        != source_clock.source_content_identity_sha256
                        or upstream_reference.daily_cohort_sha256 != self._initial_pin.cohort_sha256
                        or upstream_reference.decision_cutoff != _datetime_text(self._cutoff_at)
                        or upstream_reference.declared_stock_codes != self._stock_codes):
                    raise DailyMarketMonthlyRevenueReadSessionV2Error(
                        "monthly_revenue_v2_upstream_reference_mismatch"
                    )
                issued = _issue_finished_daily_market_monthly_revenue_cohort_v2(
                    snapshot_finished=snapshot_finished,
                    upstream_reference=upstream_reference,
                    facts=facts,
                )
                if type(issued) is not FinishedDailyMarketMonthlyRevenueCohortV2:
                    raise DailyMarketMonthlyRevenueReadSessionV2Error(
                        "monthly_revenue_v2_finished_issuer_type_mismatch"
                    )
                self._verify_expected_source_reference(issued)
                self._poll_cancel()
                with self._publication_lock:
                    if self._cancel_event.is_set() or self._state != "open":
                        raise DailyMarketMonthlyRevenueReadCancelledV2(
                            "monthly_revenue_v2_cancelled_before_publication"
                        )
                    self._finished = issued
                    self._state = "finished"
                    return issued
            except BaseException as exc:
                self._mark_failed(exc)
                raise

    def cancel(self) -> bool:
        """可跨執行緒要求取消；finished token 發行後不回溯撤銷。"""

        with self._publication_lock:
            if self._state == "finished":
                return False
            if self._state in {"cancelled", "failed"}:
                return True
            self._state = "cancelled"
            self._cancel_event.set()
        self._snapshot_session.cancel()
        return True

    def close(self) -> None:
        """由建立 session 的 thread 關閉隔離 copy；close 不會發行月營收 token。"""

        self._require_owner_thread()
        with self._publication_lock:
            if self._state == "open":
                self._state = "cancelled"
                self._cancel_event.set()
        self._snapshot_session.close()
        if not self._snapshot_session.closed:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_upstream_reader_connection_not_closed"
            )

    def __enter__(self) -> DailyMarketMonthlyRevenueReadSessionV2:
        self._require_owner_thread()
        self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> Literal[False]:
        try:
            self.close()
        except BaseException as cleanup_exc:
            if exc is not None:
                raise DailyMarketMonthlyRevenueReadSessionV2Error(
                    "monthly_revenue_v2_context_exit_cleanup_failed"
                ) from BaseExceptionGroup(
                    "primary context exception and monthly revenue V2 cleanup failure",
                    [exc, cleanup_exc],
                )
            raise
        return False

    def _flatten_facts(self) -> tuple[DailyMarketMonthlyRevenueFactV2, ...]:
        facts: list[DailyMarketMonthlyRevenueFactV2] = []
        for batch in self._batches:
            if batch.session_identity_sha256 != self._session_identity_sha256:
                raise DailyMarketMonthlyRevenueReadSessionV2Error(
                    "monthly_revenue_v2_batch_session_identity_mismatch"
                )
            facts.extend(batch.facts)
        if len(facts) != len(self._stock_codes):
            raise DailyMarketMonthlyRevenueReadIncompleteV2(
                "monthly_revenue_v2_fact_ledger_incomplete"
            )
        return tuple(facts)

    def _verify_expected_source_reference(
        self,
        issued: FinishedDailyMarketMonthlyRevenueCohortV2,
    ) -> None:
        expected = self._expected_source_reference
        if expected is None:
            return
        actual_fact_ledger = tuple(
            (fact.stock_code, fact.identity_sha256) for fact in issued.facts
        )
        if (issued.source_content_identity_sha256 != expected.source_content_identity_sha256
                or issued.decision_cutoff.isoformat() != expected.decision_cutoff
                or issued.declared_stock_codes != expected.declared_stock_codes
                or issued.cohort_pin != expected.cohort_pin
                or actual_fact_ledger != expected.fact_identity_by_stock
                or issued.result_identity_by_stock != expected.result_identity_by_stock
                or issued.reader_result_status_counts != expected.reader_result_status_counts
                or issued.fact_state_counts != expected.fact_state_counts):
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v3_exact_reopen_fact_or_source_ledger_mismatch"
            )

    def _verify_reader_pin(self) -> None:
        current_pin = self._reader.pin
        if (self._provider.daily_source_snapshot_reader is not self._reader
                or current_pin != self._initial_pin):
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_daily_reader_or_pin_changed"
            )
        _verify_cohort_hour_bound(current_pin, self._cutoff_at)

    def _poll_cancel(self) -> None:
        if _cancel_requested(self._cancel_event, self._cancel_callback):
            raise DailyMarketMonthlyRevenueReadCancelledV2(
                "monthly_revenue_v2_read_cancelled"
            )

    def _mark_failed(self, exc: BaseException) -> None:
        with self._publication_lock:
            self._state = "cancelled" if isinstance(
                exc,
                (DailyMarketMonthlyRevenueReadCancelledV2,
                 FundamentalReadSessionCancelled,
                 FundamentalReadSnapshotCancelled),
            ) else "failed"
        try:
            self._snapshot_session.close()
        except BaseException as cleanup_exc:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_operation_and_cleanup_failed"
            ) from BaseExceptionGroup(
                "primary monthly revenue V2 operation and cleanup failure",
                [exc, cleanup_exc],
            )
        if not self._snapshot_session.closed:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_reader_connection_not_closed_after_failure"
            ) from exc

    def _close_failed(self, exc: BaseException) -> None:
        with self._publication_lock:
            self._state = "failed"
        try:
            self._snapshot_session.close()
        except BaseException as cleanup_exc:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_incomplete_and_cleanup_failed"
            ) from BaseExceptionGroup(
                "incomplete monthly revenue V2 cohort and cleanup failure",
                [exc, cleanup_exc],
            )
        if not self._snapshot_session.closed:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_reader_connection_not_closed_after_incomplete"
            ) from exc

    def _require_owner_thread(self) -> None:
        if get_ident() != self._owner_thread_id:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                "monthly_revenue_v2_session_thread_affinity_violation"
            )

    def _require_open(self) -> None:
        if self._state != "open":
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                f"monthly_revenue_v2_session_{self._state}"
            )

    def _require_open_or_finished(self) -> None:
        if self._state not in {"open", "finished"}:
            raise DailyMarketMonthlyRevenueReadSessionV2Error(
                f"monthly_revenue_v2_session_{self._state}"
            )


def _normalize_stock_codes(stock_codes: Sequence[str]) -> tuple[str, ...]:
    if isinstance(stock_codes, (str, bytes, bytearray)):
        raise TypeError("stock_codes 必須是股票代碼序列")
    codes: list[str] = []
    for index, code in enumerate(stock_codes):
        if index >= MAX_STOCK_CODES:
            raise ValueError("monthly_revenue_v2_cohort_exceeds_bound")
        if type(code) is not str or not _STOCK_CODE_RE.fullmatch(code):
            raise ValueError("monthly_revenue_v2_stock_code_invalid")
        codes.append(code)
    if not codes or len(codes) != len(set(codes)):
        raise ValueError("monthly_revenue_v2_cohort_codes_empty_or_duplicated")
    return tuple(sorted(codes))


def _normalize_batch_codes(stock_codes: Sequence[str]) -> tuple[str, ...]:
    if isinstance(stock_codes, (str, bytes, bytearray)):
        raise TypeError("batch stock_codes 必須是股票代碼序列")
    codes: list[str] = []
    for index, code in enumerate(stock_codes):
        if index >= MAX_CODES_PER_BATCH:
            raise ValueError("monthly_revenue_v2_batch_exceeds_bound")
        if type(code) is not str or not _STOCK_CODE_RE.fullmatch(code):
            raise ValueError("monthly_revenue_v2_batch_stock_code_invalid")
        codes.append(code)
    if not codes or len(codes) != len(set(codes)):
        raise ValueError("monthly_revenue_v2_batch_empty_or_duplicated")
    return tuple(codes)


def _require_aware_utc(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("cutoff_at 必須是 aware datetime")
    return value.astimezone(timezone.utc)


def _verify_cohort_hour_bound(
    pin: DailyMonthlyRevenueCohortPin,
    cutoff_at: datetime,
) -> None:
    if type(pin) is not DailyMonthlyRevenueCohortPin:
        raise DailyMarketMonthlyRevenueReadSessionV2Error(
            "monthly_revenue_v2_cohort_pin_type_invalid"
        )
    try:
        available_hour = _require_aware_utc(pin.available_hour)
    except ValueError as exc:
        raise DailyMarketMonthlyRevenueReadSessionV2Error(
            "monthly_revenue_v2_cohort_available_hour_invalid"
        ) from exc
    if available_hour > cutoff_at:
        raise DailyMarketMonthlyRevenueReadSessionV2Error(
            "monthly_revenue_v2_cohort_available_hour_after_cutoff"
        )


def _datetime_text(value: datetime) -> str:
    return _require_aware_utc(value).isoformat()


def _cancel_requested(event: Event, callback: Callable[[], bool] | None) -> bool:
    if event.is_set():
        return True
    if callback is None:
        return False
    try:
        value = callback()
    except BaseException as exc:
        raise DailyMarketMonthlyRevenueReadSessionV2Error(
            f"monthly_revenue_v2_cancel_callback_failed:{type(exc).__name__}"
        ) from exc
    if type(value) is not bool:
        raise DailyMarketMonthlyRevenueReadSessionV2Error(
            "monthly_revenue_v2_cancel_callback_must_return_bool"
        )
    return event.is_set() or value


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


__all__ = [
    "DAILY_MARKET_MONTHLY_REVENUE_READ_SESSION_SCHEMA_V2",
    "DailyMarketMonthlyRevenueBatchCandidateV2",
    "DailyMarketMonthlyRevenueReadCancelledV2",
    "DailyMarketMonthlyRevenueReadIncompleteV2",
    "DailyMarketMonthlyRevenueReadSessionV2",
    "DailyMarketMonthlyRevenueReadSessionV2Error",
]
