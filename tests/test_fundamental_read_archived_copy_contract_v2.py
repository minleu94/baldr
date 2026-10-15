"""V2 archived-copy binding 的 issuer、pin mapping 與完整樹守衛。"""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

import pytest

from data_module.fundamental_read_archived_copy_contract_v2 import (
    FUNDAMENTAL_READ_ARCHIVED_COPY_BINDING_V2_SCHEMA,
    _ARCHIVED_BINDING_ISSUER_V2,
    _issue_archived_copy_binding_v2,
    _is_issued_archived_binding_v2,
    FilePinPairV2,
    FundamentalReadArchivedCopyBindingV2,
    FundamentalReadArchivedCopyBindingV2Error,
)
from data_module.fundamental_read_copy_contract import (
    FundamentalReadCopyBinding,
    FundamentalReadCopyFilePin,
    FundamentalReadCopyFileReference,
    MAX_COPY_FILE_BYTES,
    _pin_file,
)
from tests.test_fundamental_read_snapshot_raw_archive_v2 import _cohort


_SNAPSHOT_ID = "a" * 32
_ARCHIVE_ID = "b" * 32
_OPERATION_ID = "c" * 32


def _fake_pin(
    role: str,
    path: Path,
    *,
    present: bool,
    digest: str | None = None,
    size: int | None = None,
    inode: int = 10,
) -> FundamentalReadCopyFilePin:
    if not present:
        return FundamentalReadCopyFilePin(
            role=role,
            path=str(path),
            present=False,
            device=None,
            inode=None,
            size_bytes=None,
            mtime_ns=None,
            mode=None,
            sha256=None,
        )
    assert digest is not None and size is not None
    return FundamentalReadCopyFilePin(
        role=role,
        path=str(path),
        present=True,
        device=1,
        inode=inode,
        size_bytes=size,
        mtime_ns=2,
        mode=0o100600,
        sha256=digest,
    )


def _operation_copy_binding(
    tmp_path: Path,
) -> tuple[FundamentalReadCopyBinding, tuple[FundamentalReadCopyFilePin, ...]]:
    source_database = tmp_path / "historical-db" / "fundamental.sqlite"
    operation_root = tmp_path / "operation" / _OPERATION_ID
    reader_database = operation_root / "reader" / source_database.name
    source_pins = (
        _fake_pin("sqlite_main", source_database, present=True, digest="1" * 64, size=7),
        _fake_pin("sqlite_wal", Path(f"{source_database}-wal"), present=False),
        _fake_pin("sqlite_shm", Path(f"{source_database}-shm"), present=False),
        _fake_pin(
            "sqlite_rollback_journal",
            Path(f"{source_database}-journal"),
            present=False,
        ),
    )
    reader_pins = (
        _fake_pin("sqlite_main", reader_database, present=True, digest="1" * 64, size=7),
        _fake_pin("sqlite_wal", Path(f"{reader_database}-wal"), present=False),
        _fake_pin("sqlite_shm", Path(f"{reader_database}-shm"), present=False),
        _fake_pin(
            "sqlite_rollback_journal",
            Path(f"{reader_database}-journal"),
            present=False,
        ),
    )
    capture_manifest_pin = _fake_pin(
        "snapshot_capture_manifest",
        operation_root / "snapshot_capture.json",
        present=True,
        digest="2" * 64,
        size=11,
    )
    copy_binding = FundamentalReadCopyBinding(
        snapshot_id=_OPERATION_ID,
        snapshot_root=str(operation_root),
        source_database_path=str(source_database),
        reader_database_path=str(reader_database),
        source_file_pins=source_pins,
        captured_files=(
            FundamentalReadCopyFileReference(
                role="sqlite_main",
                relative_path="captured/fundamental.sqlite",
                size_bytes=7,
                sha256="1" * 64,
            ),
        ),
        reader_files=(
            FundamentalReadCopyFileReference(
                role="sqlite_main",
                relative_path="reader/fundamental.sqlite",
                size_bytes=7,
                sha256="1" * 64,
            ),
        ),
        capture_manifest_pin=capture_manifest_pin,
        reader_file_pins_before_open=reader_pins,
        sqlite_journal_mode="rollback",
        wal_sidecar_state="not_applicable",
        source_snapshot_sha256="3" * 64,
        source_copy_bytes=7,
    )
    return copy_binding, source_pins


def _make_binding(
    tmp_path: Path, *, issue: bool = True
) -> FundamentalReadArchivedCopyBindingV2:
    archive_root = tmp_path / "raw-archives" / _ARCHIVE_ID
    archived_snapshot_root = archive_root / "saved_snapshot" / _SNAPSHOT_ID
    archived_monthly_root = archive_root / "monthly_source"
    historical_snapshot_root = tmp_path / "historical-snapshot" / _SNAPSHOT_ID
    archived_snapshot_root.mkdir(parents=True)
    archived_monthly_root.mkdir(parents=True)
    (archived_snapshot_root / "finished_source_clock.json").write_bytes(b"snapshot")
    (archived_monthly_root / "monthly.html").write_bytes(b"monthly-html")
    (archive_root / "raw_archive.json").write_bytes(b"raw-archive")

    snapshot_manifest_pin = _pin_file(
        "finished_source_clock_manifest",
        archived_snapshot_root / "finished_source_clock.json",
        required=True,
        max_bytes=MAX_COPY_FILE_BYTES,
        cancel_callback=None,
    )
    archive_capture_pin = _pin_file(
        "monthly_html",
        archived_monthly_root / "monthly.html",
        required=True,
        max_bytes=MAX_COPY_FILE_BYTES,
        cancel_callback=None,
    )
    assert archive_capture_pin.sha256 is not None
    assert archive_capture_pin.size_bytes is not None
    archive_manifest_pin = _pin_file(
        "monthly_raw_archive_manifest",
        archive_root / "raw_archive.json",
        required=True,
        max_bytes=MAX_COPY_FILE_BYTES,
        cancel_callback=None,
    )
    historical_capture_pin = _fake_pin(
        "monthly_html",
        tmp_path / "original-monthly" / "monthly.html",
        present=True,
        digest=archive_capture_pin.sha256,
        size=archive_capture_pin.size_bytes,
        inode=20,
    )
    copy_binding, source_pins = _operation_copy_binding(tmp_path)
    archive_file_pins = tuple(
        sorted(
            (snapshot_manifest_pin, archive_capture_pin),
            key=lambda pin: os.path.normcase(pin.path),
        )
    )
    cohort_pin = _cohort()
    capture_file_pairs = (
        FilePinPairV2(
            historical_pin=historical_capture_pin,
            archive_pin=archive_capture_pin,
        ),
    )
    if not issue:
        return FundamentalReadArchivedCopyBindingV2(
            operation_copy_binding=copy_binding,
            historical_snapshot_root=str(historical_snapshot_root),
            archived_snapshot_root=str(archived_snapshot_root),
            archive_root=str(archive_root),
            archived_monthly_source_root=str(archived_monthly_root),
            snapshot_reference_identity_sha256="4" * 64,
            source_clock_identity_sha256="5" * 64,
            source_content_identity_sha256="6" * 64,
            cohort_identity_sha256="7" * 64,
            daily_cohort_pin=cohort_pin,
            daily_cohort_sha256=cohort_pin.cohort_sha256,
            raw_archive_identity_sha256="8" * 64,
            raw_archive_reference_sha256="9" * 64,
            snapshot_manifest_pin=snapshot_manifest_pin,
            archive_manifest_pin=archive_manifest_pin,
            historical_source_pins=source_pins,
            capture_file_pairs=capture_file_pairs,
            archive_file_pins=archive_file_pins,
            _issuer_anchor=_ARCHIVED_BINDING_ISSUER_V2,
        )
    return _issue_archived_copy_binding_v2(
        issuer_anchor=_ARCHIVED_BINDING_ISSUER_V2,
        operation_copy_binding=copy_binding,
        historical_snapshot_root=str(historical_snapshot_root),
        archived_snapshot_root=str(archived_snapshot_root),
        archive_root=str(archive_root),
        archived_monthly_source_root=str(archived_monthly_root),
        snapshot_reference_identity_sha256="4" * 64,
        source_clock_identity_sha256="5" * 64,
        source_content_identity_sha256="6" * 64,
        cohort_identity_sha256="7" * 64,
        daily_cohort_pin=cohort_pin,
        daily_cohort_sha256=cohort_pin.cohort_sha256,
        raw_archive_identity_sha256="8" * 64,
        raw_archive_reference_sha256="9" * 64,
        snapshot_manifest_pin=snapshot_manifest_pin,
        archive_manifest_pin=archive_manifest_pin,
        historical_source_pins=source_pins,
        capture_file_pairs=capture_file_pairs,
        archive_file_pins=archive_file_pins,
    )


def test_v2_capture_pairs_require_matching_role_size_and_raw_sha(tmp_path: Path) -> None:
    binding = _make_binding(tmp_path)
    pair = binding.capture_file_pairs[0]

    assert pair.archive_pin.sha256 == pair.historical_pin.sha256
    with pytest.raises(ValueError, match="來源不同"):
        FilePinPairV2(
            historical_pin=replace(pair.historical_pin, role="monthly_csv"),
            archive_pin=pair.archive_pin,
        )
    with pytest.raises(ValueError, match="bytes"):
        FilePinPairV2(
            historical_pin=replace(pair.historical_pin, sha256="0" * 64),
            archive_pin=pair.archive_pin,
        )


def test_v2_binding_uses_private_issuance_and_exact_bidirectional_pin_mapping(
    tmp_path: Path,
) -> None:
    binding = _make_binding(tmp_path)
    pair = binding.capture_file_pairs[0]

    assert _is_issued_archived_binding_v2(binding)
    assert binding.schema_version == FUNDAMENTAL_READ_ARCHIVED_COPY_BINDING_V2_SCHEMA
    assert binding.source_scope == "current_observed_only"
    assert binding.availability_status == "cohort_hour_bound"
    assert binding.historical_pit_eligible is False
    assert binding.formal_pit_eligible is False
    assert binding.remap_capture_pin(pair.historical_pin) == pair.archive_pin
    assert binding.restore_capture_pin(pair.archive_pin) == pair.historical_pin

    same_bytes_other_path = replace(
        pair.historical_pin,
        path=str(Path(pair.historical_pin.path).with_name("alias.html")),
    )
    with pytest.raises(FundamentalReadArchivedCopyBindingV2Error, match="unmapped"):
        binding.remap_capture_pin(same_bytes_other_path)
    same_bytes_other_path = replace(
        pair.archive_pin,
        path=str(Path(pair.archive_pin.path).with_name("alias.html")),
    )
    with pytest.raises(FundamentalReadArchivedCopyBindingV2Error, match="unmapped"):
        binding.restore_capture_pin(same_bytes_other_path)


def test_v2_binding_requires_issuer_and_detects_nested_identity_tampering(
    tmp_path: Path,
) -> None:
    unissued = _make_binding(tmp_path / "unissued", issue=False)
    assert not _is_issued_archived_binding_v2(unissued)
    with pytest.raises(FundamentalReadArchivedCopyBindingV2Error, match="not_issued"):
        unissued.remap_capture_pin(unissued.capture_file_pairs[0].historical_pin)

    with pytest.raises(FundamentalReadArchivedCopyBindingV2Error, match="issuer_rejected"):
        _issue_archived_copy_binding_v2(
            issuer_anchor=object(),
            operation_copy_binding=unissued.operation_copy_binding,
            historical_snapshot_root=unissued.historical_snapshot_root,
            archived_snapshot_root=unissued.archived_snapshot_root,
            archive_root=unissued.archive_root,
            archived_monthly_source_root=unissued.archived_monthly_source_root,
            snapshot_reference_identity_sha256=unissued.snapshot_reference_identity_sha256,
            source_clock_identity_sha256=unissued.source_clock_identity_sha256,
            source_content_identity_sha256=unissued.source_content_identity_sha256,
            cohort_identity_sha256=unissued.cohort_identity_sha256,
            daily_cohort_pin=unissued.daily_cohort_pin,
            daily_cohort_sha256=unissued.daily_cohort_sha256,
            raw_archive_identity_sha256=unissued.raw_archive_identity_sha256,
            raw_archive_reference_sha256=unissued.raw_archive_reference_sha256,
            snapshot_manifest_pin=unissued.snapshot_manifest_pin,
            archive_manifest_pin=unissued.archive_manifest_pin,
            historical_source_pins=unissued.historical_source_pins,
            capture_file_pairs=unissued.capture_file_pairs,
            archive_file_pins=unissued.archive_file_pins,
        )

    issued = _make_binding(tmp_path / "issued")
    original = issued.source_content_identity_sha256
    object.__setattr__(issued, "source_content_identity_sha256", "0" * 64)
    assert not _is_issued_archived_binding_v2(issued)
    with pytest.raises(FundamentalReadArchivedCopyBindingV2Error, match="not_issued"):
        issued.restore_capture_pin(issued.capture_file_pairs[0].archive_pin)
    object.__setattr__(issued, "source_content_identity_sha256", original)
    assert _is_issued_archived_binding_v2(issued)


def test_v2_full_archive_tree_accepts_only_exact_pinned_files_and_directories(
    tmp_path: Path,
) -> None:
    binding = _make_binding(tmp_path)
    binding._verify_full_archived_tree(cancel_callback=None)

    extra_directory = Path(binding.archive_root) / "unlisted"
    extra_directory.mkdir()
    with pytest.raises(
        FundamentalReadArchivedCopyBindingV2Error,
        match="tree_contains_unpinned_directory",
    ):
        binding._verify_full_archived_tree(cancel_callback=None)

    extra_directory.rmdir()
    extra_file = Path(binding.archived_monthly_source_root) / "unlisted.bin"
    extra_file.write_bytes(b"not pinned")
    with pytest.raises(
        FundamentalReadArchivedCopyBindingV2Error,
        match="tree_contains_unpinned_file",
    ):
        binding._verify_full_archived_tree(cancel_callback=None)


def test_v2_full_archive_tree_rejects_content_changed_after_pin(tmp_path: Path) -> None:
    binding = _make_binding(tmp_path)
    changed_file = Path(binding.archived_monthly_source_root) / "monthly.html"
    changed_file.write_bytes(b"changed content")

    with pytest.raises(FundamentalReadArchivedCopyBindingV2Error, match="file_pin_changed"):
        binding._verify_full_archived_tree(cancel_callback=None)
