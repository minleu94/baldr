"""V2 自含 snapshot／原件封存；歷史邏輯身份與實體保存位置分離。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Callable
from uuid import uuid4
import weakref

from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortReader
from data_module.fundamental_read_snapshot import (
    MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES, MAX_RAW_ARCHIVE_FILE_BYTES,
    MAX_RAW_ARCHIVE_MANIFEST_BYTES, MAX_SNAPSHOT_SOURCE_FILE_BYTES,
    FundamentalFilePin, FundamentalReadSnapshotError, FundamentalReadSnapshotBinding,
    _canonical_json_bytes, _copy_file_bounded, _make_read_only, _paths_overlap,
    _pin_file, _poll_cancel, _read_canonical_json_file, _reject_reparse_components,
    _require_single_link, _validate_snapshot_root, _verify_finished_snapshot_status,
    _verify_raw_archive_inventory, _verify_snapshot_binding_files,
    _verify_snapshot_capture_manifest, _verify_snapshot_file_inventory,
    _write_create_only_bytes,
)
from data_module.fundamental_read_snapshot_cohort_v2 import (
    FundamentalReadSnapshotReferenceV2, make_snapshot_reference_v2,
    parse_finished_snapshot_cohort_v2, parse_snapshot_source_clock_v2,
)
from data_module.fundamental_read_snapshot_daily_v2 import (
    _VerifiedSnapshotReferenceV2, _verify_daily_reader, _verify_finished_snapshot_reference_v2,
)
from data_module.fundamental_read_snapshot_raw_archive_v2 import (
    FundamentalReadSnapshotArchiveStoredFileV2, FundamentalReadSnapshotRawArchiveFileV2,
    FundamentalReadSnapshotRawArchiveReferenceV2, _expected_snapshot_files,
    make_raw_archive_reference_v2,
)
from data_module.recommendation_current_fundamental_provider import RecommendationCurrentFundamentalProvider

if TYPE_CHECKING:
    from data_module.fundamental_read_archived_copy_contract_v2 import FundamentalReadArchivedCopyBindingV2
    from data_module.fundamental_read_snapshot import _SnapshotAttempt


_ISSUED: dict[int, tuple[weakref.ReferenceType[_VerifiedArchivedSnapshotReferenceV2], str]] = {}


@dataclass(frozen=True, slots=True, weakref_slot=True)
class _VerifiedArchivedSnapshotReferenceV2:
    snapshot: _VerifiedSnapshotReferenceV2
    archive_reference: FundamentalReadSnapshotRawArchiveReferenceV2
    snapshot_manifest_pin: FundamentalFilePin
    archive_manifest_pin: FundamentalFilePin
    archive_file_pins: tuple[FundamentalFilePin, ...]
    archive_all_file_pins: tuple[FundamentalFilePin, ...]
    external_reference_sha256: str


def _require_issued_v2(value: _VerifiedArchivedSnapshotReferenceV2) -> None:
    anchor = _ISSUED.get(id(value))
    if (type(value) is not _VerifiedArchivedSnapshotReferenceV2 or anchor is None
            or anchor[0]() is not value or anchor[1] != _subject_identity(value)):
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_verification_subject_required")


def _subject_identity(value: _VerifiedArchivedSnapshotReferenceV2) -> str:
    return sha256(_canonical_json_bytes({
        "reference": value.archive_reference.to_dict(), "external_sha256": value.external_reference_sha256,
        "snapshot_reference": value.snapshot.reference.to_dict(),
        "snapshot_binding": value.snapshot.binding.to_dict(),
        "source_clock": value.snapshot.source_clock.to_dict(),
        "reader_session_id": value.snapshot.reader_session_id,
        "finished_session_id": value.snapshot.finished_session_id,
        "snapshot_manifest_pin": value.snapshot_manifest_pin.to_dict(),
        "archive_manifest_pin": value.archive_manifest_pin.to_dict(),
        "raw_pins": [pin.to_dict() for pin in value.archive_file_pins],
        "all_pins": [pin.to_dict() for pin in value.archive_all_file_pins],
        "processed_codes": list(value.snapshot.processed_stock_codes),
        "result_identities": [list(pair) for pair in value.snapshot.result_identity_by_stock],
        "result_counts": [list(pair) for pair in value.snapshot.result_status_counts],
    })).hexdigest()


def _inventory(reference: FundamentalReadSnapshotRawArchiveReferenceV2,
               callback: Callable[[], bool] | None) -> None:
    files = {"raw_archive.json", *(item.relative_path for item in reference.files),
             *(item.relative_path for item in reference.snapshot_files)}
    dirs = {"monthly_source", "saved_snapshot", f"saved_snapshot/{reference.snapshot_reference.snapshot_id}",
            f"saved_snapshot/{reference.snapshot_reference.snapshot_id}/captured",
            f"saved_snapshot/{reference.snapshot_reference.snapshot_id}/reader"}
    for name in files:
        dirs.update(str(parent) for parent in PurePosixPath(name).parents if str(parent) != ".")
    _verify_raw_archive_inventory(Path(reference.archive_root), expected_files=files,
                                 expected_dirs=dirs, cancel_callback=callback)


def _relocated_binding(reference: FundamentalReadSnapshotRawArchiveReferenceV2,
                       pins: tuple[FundamentalFilePin, ...]) -> FundamentalReadSnapshotBinding:
    """僅機械驗證用的實體映射；不發行新邏輯 source clock 或修改歷史 pin。"""
    binding = reference.source_clock.snapshot_binding
    root = Path(reference.archived_snapshot_root)
    logical = Path(binding.snapshot_root)
    by_path = {pin.path: pin for pin in pins}

    def physical(pin: FundamentalFilePin) -> FundamentalFilePin:
        path = root / Path(pin.path).relative_to(logical)
        if pin.present:
            actual = by_path.get(str(path))
            if actual is None or (actual.role, actual.size_bytes, actual.sha256) != (pin.role, pin.size_bytes, pin.sha256):
                raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_saved_pin_mapping_mismatch")
            return actual
        if path.exists():
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_absent_sidecar_present")
        return replace(pin, path=str(path))

    captured = tuple(physical(pin) for pin in binding.captured_file_pins_start)
    manifest = physical(binding.capture_manifest_pin_start)
    return replace(binding, snapshot_root=str(root), reader_database_path=str(root / "reader" / Path(binding.source_database_path).name),
                   captured_file_pins_start=captured, captured_file_pins_finish=captured,
                   capture_manifest_pin_start=manifest, capture_manifest_pin_finish=manifest,
                   reader_file_pins_finish=tuple(physical(pin) for pin in binding.reader_file_pins_finish))


def verify_raw_archive_reference_v2(
    reference: FundamentalReadSnapshotRawArchiveReferenceV2, *, expected_reference_sha256: str,
    provider: RecommendationCurrentFundamentalProvider,
    daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
    cancel_callback: Callable[[], bool] | None,
) -> _VerifiedArchivedSnapshotReferenceV2:
    """外部 SHA、完整原件樹與當前 immutable daily pin 都核對後才發行內部 subject。"""
    if type(reference) is not FundamentalReadSnapshotRawArchiveReferenceV2:
        raise TypeError("V2 archive 必須是 exact typed reference")
    reference = FundamentalReadSnapshotRawArchiveReferenceV2.from_json(
        reference.to_json(), expected_reference_sha256=expected_reference_sha256)
    _verify_daily_reader(provider, daily_monthly_cohort_reader, cancel_callback)
    root = Path(reference.archive_root)
    _reject_reparse_components(root)
    clock = reference.source_clock
    if (str(provider.db_file) != clock.database_path
            or daily_monthly_cohort_reader.pin != clock.cohort_pin
            or str(provider.monthly_source_root) != reference.original_monthly_source_root):
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_provider_or_full_pin_mismatch")
    formal = Path(os.path.abspath(os.environ.get("DATA_ROOT", "F:/Min/Python/Project/FA_Data")))
    if any(_paths_overlap(root, path) for path in (provider.output_root, provider.monthly_source_root, formal,
                                                  Path(clock.database_path).parent,
                                                  Path(reference.snapshot_reference.snapshot_root))):
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_protected_root_overlap")
    manifest, manifest_raw = _read_canonical_json_file(root / "raw_archive.json", max_bytes=MAX_RAW_ARCHIVE_MANIFEST_BYTES)
    if (manifest != reference.to_manifest_dict() or sha256(manifest_raw).hexdigest() != reference.archive_manifest_sha256):
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_manifest_changed")
    manifest_pin = _pin_file("monthly_raw_archive_manifest", root / "raw_archive.json", required=True,
                             cancel_callback=cancel_callback)
    _require_single_link(root / "raw_archive.json", "v2_archive_manifest")
    if manifest_pin.sha256 != reference.archive_manifest_sha256:
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_manifest_readback_changed")
    raw_pins: list[FundamentalFilePin] = []
    stored_pins: list[FundamentalFilePin] = []
    for entries, collected in ((reference.files, raw_pins), (reference.snapshot_files, stored_pins)):
        for entry in entries:
            _poll_cancel(cancel_callback)
            path = root / Path(entry.relative_path)
            pin = _pin_file(entry.historical_pin.role, path, required=True, cancel_callback=cancel_callback)
            _require_single_link(path, "v2_archive")
            if (pin.size_bytes, pin.sha256) != (entry.size_bytes, entry.sha256):
                raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_file_bytes_changed")
            collected.append(pin)
    _inventory(reference, cancel_callback)
    saved = Path(reference.archived_snapshot_root)
    finished_manifest, finished_raw = _read_canonical_json_file(saved / "finished_source_clock.json",
                                                              max_bytes=MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES)
    try:
        saved_clock = parse_snapshot_source_clock_v2(finished_manifest.get("source_clock"))
        finished = parse_finished_snapshot_cohort_v2(finished_manifest, saved_clock)
    except (TypeError, ValueError) as error:
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_finished_manifest_invalid") from error
    if (saved_clock != clock or sha256(finished_raw).hexdigest() != reference.snapshot_reference.finished_manifest_sha256
            or make_snapshot_reference_v2(finished, snapshot_root=reference.snapshot_reference.snapshot_root,
                                          snapshot_id=reference.snapshot_reference.snapshot_id) != reference.snapshot_reference):
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_saved_snapshot_identity_mismatch")
    physical_binding = _relocated_binding(reference, tuple(stored_pins))
    _verify_snapshot_binding_files(saved, physical_binding, cancel_callback=cancel_callback)
    _verify_snapshot_capture_manifest(saved, clock.snapshot_binding, cancel_callback=cancel_callback)
    _verify_finished_snapshot_status(saved, clock, finished_manifest, cancel_callback)
    _verify_snapshot_file_inventory(saved, physical_binding, cancel_callback=cancel_callback)
    _verify_daily_reader(provider, daily_monthly_cohort_reader, cancel_callback)
    for pin in (*stored_pins, *raw_pins, manifest_pin):
        if _pin_file(pin.role, Path(pin.path), required=True, cancel_callback=cancel_callback) != pin:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_changed_during_verification")
    _inventory(reference, cancel_callback)
    snapshot_pin = next(pin for pin in stored_pins if pin.role == "finished_source_clock_manifest")
    result = _VerifiedArchivedSnapshotReferenceV2(
        snapshot=_VerifiedSnapshotReferenceV2(reference.snapshot_reference, clock.snapshot_binding, clock,
            finished.reader_session_id, finished.session_id, finished.processed_stock_codes,
            finished.result_identity_by_stock, finished.result_status_counts),
        archive_reference=reference, snapshot_manifest_pin=snapshot_pin, archive_manifest_pin=manifest_pin,
        archive_file_pins=tuple(raw_pins), archive_all_file_pins=tuple(stored_pins + raw_pins),
        external_reference_sha256=expected_reference_sha256)
    key = id(result)
    def remove_reference(_ref: weakref.ReferenceType[_VerifiedArchivedSnapshotReferenceV2]) -> None:
        _ISSUED.pop(key, None)

    _ISSUED[key] = (weakref.ref(result, remove_reference), _subject_identity(result))
    return result


def reverify_raw_archive_reference_v2(
    verified: _VerifiedArchivedSnapshotReferenceV2, *, provider: RecommendationCurrentFundamentalProvider,
    daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
    cancel_callback: Callable[[], bool] | None,
) -> _VerifiedArchivedSnapshotReferenceV2:
    _require_issued_v2(verified)
    current = verify_raw_archive_reference_v2(verified.archive_reference,
        expected_reference_sha256=verified.external_reference_sha256, provider=provider,
        daily_monthly_cohort_reader=daily_monthly_cohort_reader, cancel_callback=cancel_callback)
    if current != verified:
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_changed_after_verification")
    return current


def create_raw_source_archive_v2(
    *, provider: RecommendationCurrentFundamentalProvider,
    snapshot_reference: FundamentalReadSnapshotReferenceV2,
    daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader, archive_parent: Path | str,
    cancel_callback: Callable[[], bool] | None,
) -> FundamentalReadSnapshotRawArchiveReferenceV2:
    original = _verify_finished_snapshot_reference_v2(snapshot_reference, provider=provider,
        daily_monthly_cohort_reader=daily_monthly_cohort_reader, cancel_callback=cancel_callback)
    parent = _validate_snapshot_root(archive_parent, source_database_path=Path(original.source_clock.database_path),
                                    provider=provider)
    if _paths_overlap(parent, Path(snapshot_reference.snapshot_root)):
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_original_snapshot_overlap")
    parent.mkdir(parents=True, exist_ok=True)
    _reject_reparse_components(parent)
    archive_id = uuid4().hex
    root = parent / archive_id
    root.mkdir(exist_ok=False)
    saved = root / "saved_snapshot" / snapshot_reference.snapshot_id
    (saved / "captured").mkdir(parents=True)
    (saved / "reader").mkdir()
    monthly = root / "monthly_source"
    monthly.mkdir()
    raw_entries: list[FundamentalReadSnapshotRawArchiveFileV2] = []
    stored_entries: list[FundamentalReadSnapshotArchiveStoredFileV2] = []
    logical = Path(snapshot_reference.snapshot_root)
    expected = _expected_snapshot_files(snapshot_reference, original.source_clock)
    historical_pins: list[tuple[FundamentalFilePin, str, int]] = []
    for relative, (expected_pin, _size, _digest, role) in sorted(expected.items()):
        actual = _pin_file(role, logical / Path(relative), required=True, cancel_callback=cancel_callback)
        if expected_pin is not None and actual != expected_pin:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_original_saved_file_changed")
        historical_pins.append((actual, f"saved_snapshot/{snapshot_reference.snapshot_id}/{relative}",
                                MAX_SNAPSHOT_SOURCE_FILE_BYTES))
    for pin in original.source_clock.capture_file_pins_start:
        relative = Path(pin.path).relative_to(provider.monthly_source_root).as_posix()
        historical_pins.append((pin, f"monthly_source/{relative}", MAX_RAW_ARCHIVE_FILE_BYTES))
    for pin, relative, limit in historical_pins:
        _poll_cancel(cancel_callback)
        path = Path(pin.path)
        _require_single_link(path, "v2_archive_source")
        if _pin_file(pin.role, path, required=True, cancel_callback=cancel_callback) != pin:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_source_pin_changed")
        destination = root / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        size, digest = _copy_file_bounded(path, destination, max_bytes=limit, cancel_callback=cancel_callback)
        _make_read_only(destination)
        _require_single_link(destination, "v2_archive_destination")
        actual = _pin_file(pin.role, destination, required=True, cancel_callback=cancel_callback)
        if (size, digest) != (pin.size_bytes, pin.sha256) or (actual.size_bytes, actual.sha256) != (size, digest):
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_copy_mismatch")
        if relative.startswith("monthly_source/"):
            raw_entries.append(FundamentalReadSnapshotRawArchiveFileV2(pin, relative, size, digest))
        else:
            stored_entries.append(FundamentalReadSnapshotArchiveStoredFileV2(pin, relative, size, digest))
    _verify_finished_snapshot_reference_v2(snapshot_reference, provider=provider,
        daily_monthly_cohort_reader=daily_monthly_cohort_reader, cancel_callback=cancel_callback)
    reference = make_raw_archive_reference_v2(snapshot_reference=snapshot_reference,
        snapshot_reference_sha256=sha256(snapshot_reference.to_json().encode("utf-8")).hexdigest(),
        source_clock=original.source_clock, archive_root=str(root), archive_id=archive_id,
        archived_snapshot_root=str(saved), archived_monthly_source_root=str(monthly),
        original_monthly_source_root=str(provider.monthly_source_root), files=tuple(raw_entries),
        snapshot_files=tuple(stored_entries))
    _poll_cancel(cancel_callback)
    _write_create_only_bytes(root / "raw_archive.json", _canonical_json_bytes(reference.to_manifest_dict()))
    _make_read_only(root / "raw_archive.json")
    verify_raw_archive_reference_v2(reference, expected_reference_sha256=sha256(reference.to_json().encode("utf-8")).hexdigest(),
        provider=provider, daily_monthly_cohort_reader=daily_monthly_cohort_reader, cancel_callback=cancel_callback)
    return reference


def make_archived_copy_binding_v2(attempt: _SnapshotAttempt, *, verified: _VerifiedArchivedSnapshotReferenceV2,
                                 cancel_callback: Callable[[], bool] | None) -> FundamentalReadArchivedCopyBindingV2:
    from data_module.fundamental_read_snapshot import _SnapshotAttempt, _make_copy_binding
    from data_module.fundamental_read_archived_copy_contract_v2 import (
        FilePinPairV2, _ARCHIVED_BINDING_ISSUER_V2, _issue_archived_copy_binding_v2,
    )
    _require_issued_v2(verified)
    if type(attempt) is not _SnapshotAttempt:
        raise TypeError("V2 archived operation 必須是 exact snapshot attempt")
    reference = verified.archive_reference
    clock = verified.snapshot.source_clock
    return _issue_archived_copy_binding_v2(
        operation_copy_binding=_make_copy_binding(attempt, cancel_callback=cancel_callback),
        historical_snapshot_root=reference.snapshot_reference.snapshot_root,
        archived_snapshot_root=reference.archived_snapshot_root, archive_root=reference.archive_root,
        archived_monthly_source_root=reference.archived_monthly_source_root,
        snapshot_reference_identity_sha256=reference.snapshot_reference.identity_sha256,
        source_clock_identity_sha256=clock.identity_sha256, source_content_identity_sha256=clock.source_content_identity_sha256,
        cohort_identity_sha256=reference.snapshot_reference.cohort_identity_sha256,
        daily_cohort_pin=clock.cohort_pin, daily_cohort_sha256=clock.cohort_sha256,
        raw_archive_identity_sha256=reference.archive_identity_sha256,
        raw_archive_reference_sha256=verified.external_reference_sha256,
        snapshot_manifest_pin=verified.snapshot_manifest_pin,
        archive_manifest_pin=verified.archive_manifest_pin,
        historical_source_pins=clock.database_file_pins_start,
        capture_file_pairs=tuple(FilePinPairV2(entry.historical_pin, pin)
            for entry, pin in zip(reference.files, verified.archive_file_pins, strict=True)),
        archive_file_pins=tuple(sorted(verified.archive_all_file_pins,
                                      key=lambda pin: os.path.normcase(pin.path))),
        issuer_anchor=_ARCHIVED_BINDING_ISSUER_V2)


def verify_finished_archived_operation_v2(
    reference: FundamentalReadSnapshotReferenceV2, *, verified: _VerifiedArchivedSnapshotReferenceV2,
    provider: RecommendationCurrentFundamentalProvider, daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
    cancel_callback: Callable[[], bool] | None,
) -> _VerifiedSnapshotReferenceV2:
    """已完成新 operation 重驗自己的檔案與 ledger，歷史資料改從封存驗證。"""
    from data_module.fundamental_read_snapshot_daily_v2 import _load_finished_snapshot_v2
    reverify_raw_archive_reference_v2(verified, provider=provider,
        daily_monthly_cohort_reader=daily_monthly_cohort_reader, cancel_callback=cancel_callback)
    root = Path(reference.snapshot_root)
    manifest, clock, finished, raw = _load_finished_snapshot_v2(root)
    old = verified.snapshot
    if (make_snapshot_reference_v2(finished, snapshot_root=str(root), snapshot_id=root.name) != reference
            or sha256(raw).hexdigest() != reference.finished_manifest_sha256
            or clock.cohort_pin != old.source_clock.cohort_pin
            or clock.source_content_identity_sha256 != old.source_clock.source_content_identity_sha256
            or finished.processed_stock_codes != old.processed_stock_codes
            or finished.result_identity_by_stock != old.result_identity_by_stock
            or finished.result_status_counts != old.result_status_counts
            or clock.database_file_pins_start != old.source_clock.database_file_pins_start
            or clock.database_file_pins_finish != old.source_clock.database_file_pins_finish
            or clock.capture_file_pins_start != old.source_clock.capture_file_pins_start
            or clock.capture_file_pins_finish != old.source_clock.capture_file_pins_finish):
        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archived_operation_identity_mismatch")
    _verify_snapshot_binding_files(root, clock.snapshot_binding, cancel_callback=cancel_callback)
    _verify_snapshot_capture_manifest(root, clock.snapshot_binding, cancel_callback=cancel_callback)
    _verify_finished_snapshot_status(root, clock, manifest, cancel_callback)
    _verify_snapshot_file_inventory(root, clock.snapshot_binding, cancel_callback=cancel_callback)
    return _VerifiedSnapshotReferenceV2(reference, clock.snapshot_binding, clock, finished.reader_session_id,
        finished.session_id, finished.processed_stock_codes, finished.result_identity_by_stock, finished.result_status_counts)
