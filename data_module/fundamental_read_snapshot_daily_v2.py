"""完整 daily cohort pin 的隔離 snapshot 保存與 exact reopen V2。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, Callable, Literal, Sequence

from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortReader
from data_module.fundamental_read_snapshot import (
    MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES,
    FundamentalReadSnapshotBinding, FundamentalReadSnapshotCancelled,
    FundamentalReadSnapshotError, FundamentalReadSnapshotSession,
    _canonical_json_bytes, _capture_snapshot, _capture_snapshot_from_reference,
    _normalize_snapshot_codes, _paths_overlap, _pin_file, _pin_source_file_set,
    _poll_cancel, _read_canonical_json_file, _reject_reparse_components,
    _safe_source_database_path, _verify_finished_snapshot_status,
    _verify_reference_capture_pins, _verify_snapshot_binding_files,
    _verify_snapshot_capture_manifest, _verify_snapshot_file_inventory,
)
from data_module.fundamental_read_snapshot_cohort_v2 import (
    FinishedFundamentalSnapshotReadCohortV2, FundamentalReadSnapshotReferenceV2,
    FundamentalSnapshotSourceClockV2, decode_snapshot_reference_v2,
    encode_snapshot_reference_v2, make_snapshot_reference_v2,
    parse_finished_snapshot_cohort_v2, parse_snapshot_source_clock_v2,
)
from data_module.recommendation_current_fundamental_provider import RecommendationCurrentFundamentalProvider
from data_module.selection_fact_readers import FundamentalReadBatchCandidateV2

if TYPE_CHECKING:
    from data_module.fundamental_read_snapshot_raw_archive_v2 import FundamentalReadSnapshotRawArchiveReferenceV2


@dataclass(frozen=True, slots=True)
class _VerifiedSnapshotReferenceV2:
    reference: FundamentalReadSnapshotReferenceV2
    binding: FundamentalReadSnapshotBinding
    source_clock: FundamentalSnapshotSourceClockV2
    reader_session_id: str
    finished_session_id: str
    processed_stock_codes: tuple[str, ...]
    result_identity_by_stock: tuple[tuple[str, str], ...]
    result_status_counts: tuple[tuple[str, int], ...]


def _session_cancel_callback(event: Event, callback: Callable[[], bool] | None) -> Callable[[], bool]:
    def cancelled() -> bool:
        if event.is_set():
            return True
        if callback is None:
            return False
        result = callback()
        if type(result) is not bool:
            raise FundamentalReadSnapshotCancelled("fundamental_snapshot_cancel_callback_must_return_bool")
        return result

    return cancelled


def _verify_daily_reader(provider: RecommendationCurrentFundamentalProvider,
                         reader: DailyMonthlyRevenueCohortReader,
                         callback: Callable[[], bool] | None) -> None:
    _poll_cancel(callback)
    if type(provider) is not RecommendationCurrentFundamentalProvider:
        raise TypeError("V2 provider 必須是 exact current fundamental provider")
    if type(reader) is not DailyMonthlyRevenueCohortReader or provider.daily_source_snapshot_reader is not reader:
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_reader_identity_mismatch")
    original_pin = reader.pin
    reader.verify_cohort()
    if reader.pin != original_pin or provider.daily_source_snapshot_reader is not reader:
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_reader_changed_during_verification")
    _poll_cancel(callback)


def _require_cohort_available_at(reader: DailyMonthlyRevenueCohortReader, cutoff_at: datetime) -> None:
    if type(reader) is not DailyMonthlyRevenueCohortReader:
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_reader_identity_mismatch")
    if reader.pin.available_hour > cutoff_at:
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_cohort_after_decision_cutoff")


def _load_finished_snapshot_v2(snapshot_root: Path) -> tuple[
    dict[str, object], FundamentalSnapshotSourceClockV2, FinishedFundamentalSnapshotReadCohortV2, bytes,
]:
    manifest, raw = _read_canonical_json_file(
        snapshot_root / "finished_source_clock.json", max_bytes=MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES,
    )
    try:
        clock = parse_snapshot_source_clock_v2(manifest.get("source_clock"))
        finished = parse_finished_snapshot_cohort_v2(manifest, clock)
    except (TypeError, ValueError) as error:
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_finished_manifest_invalid") from error
    binding = clock.snapshot_binding
    if (binding.snapshot_root != str(snapshot_root) or binding.snapshot_id != snapshot_root.name
            or clock.database_path != binding.source_database_path
            or finished.finished_manifest_sha256 != sha256(raw).hexdigest()):
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_manifest_source_mismatch")
    return manifest, clock, finished, raw


def _verify_finished_snapshot_reference_v2(
    reference: FundamentalReadSnapshotReferenceV2, *,
    provider: RecommendationCurrentFundamentalProvider,
    daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
    cancel_callback: Callable[[], bool] | None,
) -> _VerifiedSnapshotReferenceV2:
    if type(reference) is not FundamentalReadSnapshotReferenceV2:
        raise TypeError("V2 source reference 必須是 exact typed reference")
    _verify_daily_reader(provider, daily_monthly_cohort_reader, cancel_callback)
    snapshot_root = Path(reference.snapshot_root)
    if (not snapshot_root.is_absolute() or Path(os.path.abspath(snapshot_root)) != snapshot_root
            or snapshot_root.name != reference.snapshot_id):
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_reference_path_invalid")
    _reject_reparse_components(snapshot_root)
    manifest, clock, finished, raw = _load_finished_snapshot_v2(snapshot_root)
    actual_reference = make_snapshot_reference_v2(finished, snapshot_root=str(snapshot_root), snapshot_id=snapshot_root.name)
    if actual_reference != reference or daily_monthly_cohort_reader.pin != clock.cohort_pin:
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_reference_pin_mismatch")
    manifest_pin = _pin_file("finished_source_clock_manifest", snapshot_root / "finished_source_clock.json",
                             required=True, cancel_callback=cancel_callback)
    if manifest_pin.sha256 != reference.finished_manifest_sha256 or sha256(raw).hexdigest() != reference.finished_manifest_sha256:
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_finished_manifest_changed")
    source_path = _safe_source_database_path(clock.database_path)
    if provider.db_file != source_path:
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_provider_database_mismatch")
    if any(_paths_overlap(snapshot_root, Path(os.path.abspath(path)))
           for path in (provider.output_root, provider.monthly_source_root)):
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_root_overlaps_provider_root")
    formal_root = Path(os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data")).expanduser()
    if _paths_overlap(snapshot_root, Path(os.path.abspath(formal_root))):
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_root_overlaps_formal_data_root")
    binding = clock.snapshot_binding
    pins = _pin_source_file_set(source_path, cancel_callback=cancel_callback)
    if pins != binding.source_file_pins_start or pins != binding.source_file_pins_finish:
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_original_database_changed")
    _verify_reference_capture_pins(clock, monthly_source_root=provider.monthly_source_root, cancel_callback=cancel_callback)
    _verify_snapshot_binding_files(snapshot_root, binding, cancel_callback=cancel_callback)
    _verify_snapshot_capture_manifest(snapshot_root, binding, cancel_callback=cancel_callback)
    _verify_finished_snapshot_status(snapshot_root, clock, manifest, cancel_callback)
    _verify_snapshot_file_inventory(snapshot_root, binding, cancel_callback=cancel_callback)
    _verify_daily_reader(provider, daily_monthly_cohort_reader, cancel_callback)
    return _VerifiedSnapshotReferenceV2(
        reference=reference, binding=binding, source_clock=clock,
        reader_session_id=finished.reader_session_id, finished_session_id=finished.session_id,
        processed_stock_codes=finished.processed_stock_codes,
        result_identity_by_stock=finished.result_identity_by_stock,
        result_status_counts=finished.result_status_counts,
    )


class FundamentalReadSnapshotSessionV2:
    """V2 facade；沿用同一 copy owner，公開結果與 exact reference 保留 full pin。"""

    def __init__(self, core: FundamentalReadSnapshotSession, reader: DailyMonthlyRevenueCohortReader):
        if type(core) is not FundamentalReadSnapshotSession or type(reader) is not DailyMonthlyRevenueCohortReader:
            raise TypeError("V2 snapshot core／reader 型別錯誤")
        if core._daily_monthly_cohort_reader is not reader:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_core_reader_mismatch")
        self._core = core
        self._reader = reader

    @classmethod
    def open(cls, provider: RecommendationCurrentFundamentalProvider, *, snapshot_root: Path | str,
             stock_codes: Sequence[str], cutoff_at: datetime,
             daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
             cancel_callback: Callable[[], bool] | None = None) -> FundamentalReadSnapshotSessionV2:
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        codes = _normalize_snapshot_codes(stock_codes)
        if type(cutoff_at) is not datetime or cutoff_at.tzinfo is None:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_cutoff_must_be_aware")
        event = Event()
        callback = _session_cancel_callback(event, cancel_callback)
        _verify_daily_reader(provider, daily_monthly_cohort_reader, callback)
        _require_cohort_available_at(daily_monthly_cohort_reader, cutoff_at)
        attempt = _capture_snapshot(provider, snapshot_root=snapshot_root, cancel_callback=callback)
        core = FundamentalReadSnapshotSession._open_reader_attempt(
            provider, attempt, stock_codes=codes, cutoff_at=cutoff_at,
            cancel_callback=cancel_callback, cancel_event=event, expected_reference=None,
            daily_monthly_cohort_reader=daily_monthly_cohort_reader,
        )
        return cls(core, daily_monthly_cohort_reader)

    @classmethod
    def open_exact_archived(
        cls, provider: RecommendationCurrentFundamentalProvider, *, snapshot_root: Path | str,
        raw_archive_reference: FundamentalReadSnapshotRawArchiveReferenceV2 | str | bytes,
        expected_archive_reference_sha256: str, stock_codes: Sequence[str], cutoff_at: datetime,
        daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> FundamentalReadSnapshotSessionV2:
        from data_module.fundamental_read_snapshot_raw_archive_v2 import (
            FundamentalReadSnapshotRawArchiveReferenceV2, decode_raw_archive_reference_v2,
        )
        from data_module.fundamental_read_snapshot_raw_archive_io_v2 import verify_raw_archive_reference_v2
        from data_module.fundamental_read_snapshot import _capture_snapshot_from_archived_reference
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        if type(raw_archive_reference) is FundamentalReadSnapshotRawArchiveReferenceV2:
            raw: str | bytes = raw_archive_reference.to_json()
        elif type(raw_archive_reference) is str or type(raw_archive_reference) is bytes:
            raw = raw_archive_reference
        else:
            raise TypeError("V2 archive 必須是 exact typed archive reference 或原始文字／bytes")
        try:
            unverified = decode_raw_archive_reference_v2(raw, expected_reference_sha256=expected_archive_reference_sha256)
        except (TypeError, ValueError) as error:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_reference_invalid") from error
        reference = unverified.reference
        codes = _normalize_snapshot_codes(stock_codes)
        if (type(cutoff_at) is not datetime or cutoff_at.tzinfo is None
                or cutoff_at.astimezone(timezone.utc).isoformat() != reference.snapshot_reference.decision_cutoff
                or codes != reference.snapshot_reference.declared_stock_codes):
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_exact_cutoff_or_codes_mismatch")
        event = Event()
        callback = _session_cancel_callback(event, cancel_callback)
        _require_cohort_available_at(daily_monthly_cohort_reader, cutoff_at)
        verified = verify_raw_archive_reference_v2(reference,
            expected_reference_sha256=expected_archive_reference_sha256, provider=provider,
            daily_monthly_cohort_reader=daily_monthly_cohort_reader, cancel_callback=callback)
        attempt = _capture_snapshot_from_archived_reference(provider, verified_reference=verified,
            snapshot_root=snapshot_root, cancel_callback=callback)
        core = FundamentalReadSnapshotSession._open_reader_attempt(provider, attempt, stock_codes=codes,
            cutoff_at=cutoff_at, cancel_callback=cancel_callback, cancel_event=event,
            expected_reference=None, expected_archived_reference=verified,
            daily_monthly_cohort_reader=daily_monthly_cohort_reader)
        return cls(core, daily_monthly_cohort_reader)

    def archive_monthly_raw_sources(
        self, archive_parent: Path | str, *, cancel_callback: Callable[[], bool] | None = None,
    ) -> FundamentalReadSnapshotRawArchiveReferenceV2:
        from data_module.fundamental_read_snapshot import _clone_provider_for_reader
        from data_module.fundamental_read_snapshot_raw_archive_io_v2 import create_raw_source_archive_v2
        self._core._require_owner_thread()
        if not self.finished:
            raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_requires_finished_session")
        if self._core._expected_archived_reference is not None:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_rearchive_requires_original_saved_source")
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        reference = self.source_reference
        _, clock, _, _ = _load_finished_snapshot_v2(self.snapshot_root)
        original = _clone_provider_for_reader(self._core._provider, reader_database_path=Path(clock.database_path))
        original.daily_source_snapshot_reader = self._reader
        return create_raw_source_archive_v2(provider=original, snapshot_reference=reference,
            daily_monthly_cohort_reader=self._reader, archive_parent=archive_parent,
            cancel_callback=cancel_callback)

    @classmethod
    def open_exact(cls, provider: RecommendationCurrentFundamentalProvider, *, snapshot_root: Path | str,
                   source_reference: FundamentalReadSnapshotReferenceV2 | str | bytes,
                   expected_reference_sha256: str, stock_codes: Sequence[str], cutoff_at: datetime,
                   daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
                   cancel_callback: Callable[[], bool] | None = None) -> FundamentalReadSnapshotSessionV2:
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        raw_reference: str | bytes
        if type(source_reference) is FundamentalReadSnapshotReferenceV2:
            raw_reference = encode_snapshot_reference_v2(source_reference)
        elif type(source_reference) is str:
            raw_reference = source_reference
        elif type(source_reference) is bytes:
            raw_reference = source_reference
        else:
            raise TypeError("V2 source reference 必須是 exact typed reference 或原始文字／bytes")
        reference = decode_snapshot_reference_v2(raw_reference, expected_reference_sha256=expected_reference_sha256)
        codes = _normalize_snapshot_codes(stock_codes)
        if (type(cutoff_at) is not datetime or cutoff_at.tzinfo is None
                or cutoff_at.astimezone(timezone.utc).isoformat() != reference.decision_cutoff
                or codes != reference.declared_stock_codes):
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_exact_cutoff_or_codes_mismatch")
        event = Event()
        callback = _session_cancel_callback(event, cancel_callback)
        _require_cohort_available_at(daily_monthly_cohort_reader, cutoff_at)
        verified = _verify_finished_snapshot_reference_v2(
            reference, provider=provider, daily_monthly_cohort_reader=daily_monthly_cohort_reader,
            cancel_callback=callback,
        )
        attempt = _capture_snapshot_from_reference(
            provider, source_reference=verified, snapshot_root=snapshot_root, cancel_callback=callback,
        )
        core = FundamentalReadSnapshotSession._open_reader_attempt(
            provider, attempt, stock_codes=codes, cutoff_at=cutoff_at,
            cancel_callback=cancel_callback, cancel_event=event, expected_reference=verified,
            daily_monthly_cohort_reader=daily_monthly_cohort_reader,
        )
        return cls(core, daily_monthly_cohort_reader)

    @property
    def snapshot_id(self) -> str:
        return self._core.snapshot_id

    @property
    def snapshot_root(self) -> Path:
        return self._core.snapshot_root

    @property
    def closed(self) -> bool:
        return self._core.closed

    @property
    def finished(self) -> bool:
        return self._core._state == "finished" and type(self._core._finished) is FinishedFundamentalSnapshotReadCohortV2

    @property
    def declared_stock_codes(self) -> tuple[str, ...]:
        return self._core.declared_stock_codes

    @property
    def source_reference(self) -> FundamentalReadSnapshotReferenceV2:
        self._core._require_owner_thread()
        if not self.finished:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_reference_requires_finished_session")
        _, _, finished, _ = _load_finished_snapshot_v2(self.snapshot_root)
        reference = make_snapshot_reference_v2(finished, snapshot_root=str(self.snapshot_root), snapshot_id=self.snapshot_id)
        origin = self._core._provider
        from data_module.fundamental_read_snapshot import _clone_provider_for_reader
        archived = self._core._expected_archived_reference
        provider = _clone_provider_for_reader(origin, reader_database_path=Path(finished.source_clock.database_path),
            monthly_source_root=(Path(archived.archive_reference.original_monthly_source_root) if archived is not None else None))
        provider.daily_source_snapshot_reader = self._reader
        if archived is not None:
            from data_module.fundamental_read_snapshot_raw_archive_io_v2 import (
                _VerifiedArchivedSnapshotReferenceV2, verify_finished_archived_operation_v2,
            )
            if type(archived) is not _VerifiedArchivedSnapshotReferenceV2:
                raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_reference_kind_mismatch")
            verify_finished_archived_operation_v2(reference, verified=archived, provider=provider,
                daily_monthly_cohort_reader=self._reader, cancel_callback=None)
        else:
            _verify_finished_snapshot_reference_v2(reference, provider=provider,
                # 已發布 token 不再接受原操作取消；所有來源仍重驗。
                daily_monthly_cohort_reader=self._reader, cancel_callback=None)
        return reference

    def load_batch(self, stock_codes: Sequence[str]) -> FundamentalReadBatchCandidateV2:
        self._core._require_owner_thread()
        self._core._require_open()
        batch = self._core._read_session.load_batch(stock_codes)
        if type(batch) is not FundamentalReadBatchCandidateV2 or batch.cohort_sha256 != self._reader.pin.cohort_sha256:
            self.close()
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_batch_pin_mismatch")
        return batch

    def finish(self) -> FinishedFundamentalSnapshotReadCohortV2:
        finished = self._core._finish_core(daily_v2=True)
        if type(finished) is not FinishedFundamentalSnapshotReadCohortV2:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_finished_kind_mismatch")
        reference = self.source_reference
        if reference.finished_manifest_sha256 != finished.finished_manifest_sha256:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_finished_reference_mismatch")
        return finished

    def cancel(self) -> bool:
        return self._core.cancel()

    def close(self) -> None:
        self._core.close()

    def __enter__(self) -> FundamentalReadSnapshotSessionV2:
        self._core._require_owner_thread()
        self._core._require_open()
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc: BaseException | None, traceback: object) -> Literal[False]:
        return self._core.__exit__(exc_type, exc, traceback)
