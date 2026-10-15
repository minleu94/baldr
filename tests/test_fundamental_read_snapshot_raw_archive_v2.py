"""V2 raw archive 純 DTO、清冊與摘要反例。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueMarketSnapshotPin,
)
from data_module.daily_source_snapshot import DAILY_SOURCE_TIME_BASIS_POLICY, DailySourceUseScope
from data_module.fundamental_read_snapshot import (
    FUNDAMENTAL_READ_SNAPSHOT_SCHEMA,
    MAX_SNAPSHOT_CAPTURE_MANIFEST_BYTES,
    FundamentalFilePin,
    FundamentalReadSnapshotBinding,
    FundamentalReadSnapshotFileReference,
    FundamentalSnapshotSourceClock,
    _canonical_json_bytes,
    _canonical_sha256,
)
from data_module.fundamental_read_snapshot_cohort_v2 import (
    FundamentalSnapshotSourceClockV2,
    make_finished_snapshot_manifest_v2,
    make_snapshot_reference_v2,
    parse_finished_snapshot_cohort_v2,
)
from data_module.fundamental_read_snapshot_raw_archive_v2 import (
    FUNDAMENTAL_READ_SNAPSHOT_RAW_ARCHIVE_V2_SCHEMA,
    FundamentalReadSnapshotArchiveStoredFileV2,
    FundamentalReadSnapshotRawArchiveFileV2,
    FundamentalReadSnapshotRawArchiveReferenceV2,
    decode_raw_archive_reference_v2,
    make_raw_archive_reference_v2,
)


_TAIPEI = ZoneInfo("Asia/Taipei")


def _sha(char: str) -> str:
    return char * 64


def _pin(role: str, path: Path, *, digest: str, size: int = 9) -> FundamentalFilePin:
    return FundamentalFilePin(
        role=role,
        path=str(path),
        present=True,
        device=1,
        inode=2,
        size_bytes=size,
        mtime_ns=3,
        mode=0o100600,
        sha256=digest,
    )


def _cohort() -> DailyMonthlyRevenueCohortPin:
    pins: list[DailyMonthlyRevenueMarketSnapshotPin] = []
    for index, market in enumerate(("twse", "tpex")):
        scope = DailySourceUseScope(
            dataset_id="monthly_revenue",
            source_id="mops.monthly_revenue",
            market=market,
            parser_version="mops-html.v2",
            source_schema_version="monthly-revenue-table.v2",
            unit="TWD",
            intended_use="research.monthly_revenue",
        )
        finished = datetime(2026, 10, 14, 9 + index, 45, tzinfo=_TAIPEI)
        available_hour = datetime(2026, 10, 14, 10 + index, 0, tzinfo=_TAIPEI)
        pins.append(
            DailyMonthlyRevenueMarketSnapshotPin(
                market=market,
                period="2026-09",
                batch_id=f"{market}-20261014-archive-test",
                scope=scope,
                acceptance_id=f"acceptance-{market}",
                acceptance_sha256=_sha("1"),
                time_basis_policy=DAILY_SOURCE_TIME_BASIS_POLICY,
                manifest_sha256=_sha("2"),
                receipt_sha256=_sha("3"),
                raw_source_sha256=_sha("4"),
                transport_sha256=_sha("5"),
                record_count=2,
                available_hour=available_hour,
                availability_basis=("batch_completed_at_ceil_hour",),
                source_batch_started_at=datetime(2026, 10, 14, 9 + index, 10, tzinfo=_TAIPEI),
                first_persisted_at=datetime(2026, 10, 14, 9 + index, 30, tzinfo=_TAIPEI),
                successful_batch_completed_at=finished,
            )
        )
    market_pins = tuple(pins)
    return DailyMonthlyRevenueCohortPin(
        period="2026-09",
        required_markets=("twse", "tpex"),
        market_pins=market_pins,
        available_hour=max(item.available_hour for item in market_pins),
    )


def _build_reference(tmp_path: Path) -> FundamentalReadSnapshotRawArchiveReferenceV2:
    snapshot_id = "a" * 32
    snapshot_root = tmp_path / "saved-source" / snapshot_id
    source_db = tmp_path / "live-source" / "fundamental.sqlite"
    reader_db = snapshot_root / "reader" / "fundamental.sqlite"
    captured_db = snapshot_root / "captured" / "fundamental.sqlite"
    monthly_root = tmp_path / "monthly-source"
    archive_id = "b" * 32
    archive_root = tmp_path / "archive" / archive_id

    source_digest = _sha("6")
    source_pin = _pin("sqlite_main", source_db, digest=source_digest)
    captured_reference = FundamentalReadSnapshotFileReference(
        role="sqlite_main",
        relative_path="captured/fundamental.sqlite",
        size_bytes=9,
        sha256=source_digest,
    )
    captured_pin = _pin("sqlite_main", captured_db, digest=source_digest)
    reader_reference = FundamentalReadSnapshotFileReference(
        role="sqlite_main",
        relative_path="reader/fundamental.sqlite",
        size_bytes=9,
        sha256=source_digest,
    )
    reader_pin = _pin("sqlite_main", reader_db, digest=source_digest)
    capture_manifest_pin = _pin(
        "snapshot_capture_manifest",
        snapshot_root / "snapshot_capture.json",
        digest=_sha("7"),
        size=128,
    )
    binding = FundamentalReadSnapshotBinding(
        snapshot_id=snapshot_id,
        snapshot_root=str(snapshot_root),
        source_database_path=str(source_db),
        reader_database_path=str(reader_db),
        source_file_pins_start=(source_pin,),
        source_file_pins_after_copy=(source_pin,),
        source_file_pins_finish=(source_pin,),
        captured_files=(captured_reference,),
        captured_file_pins_start=(captured_pin,),
        captured_file_pins_finish=(captured_pin,),
        capture_manifest_pin_start=capture_manifest_pin,
        capture_manifest_pin_finish=capture_manifest_pin,
        reader_files=(reader_reference,),
        reader_file_pins_finish=(reader_pin,),
        sqlite_journal_mode="rollback",
        wal_sidecar_state="not_applicable",
        source_snapshot_sha256=_canonical_sha256(
            {
                "schema_version": FUNDAMENTAL_READ_SNAPSHOT_SCHEMA,
                "source_database_path": str(source_db),
                "source_file_pins": [source_pin.to_dict()],
                "captured_files": [captured_reference.to_dict()],
            }
        ),
        source_copy_bytes=9,
        reader_only_sidecar_bytes=0,
        duplicated_disk_bytes=18,
    )
    html_pin = _pin("monthly_html", monthly_root / "monthly.html", digest=_sha("8"))
    csv_pin = _pin("monthly_csv", monthly_root / "monthly.csv", digest=_sha("9"))
    comparator_html_pin = _pin(
        "monthly_html", monthly_root / "comparator.html", digest=_sha("a")
    )
    comparator_csv_pin = _pin(
        "monthly_csv", monthly_root / "comparator.csv", digest=_sha("b")
    )
    base_clock = FundamentalSnapshotSourceClock(
        database_path=str(source_db),
        decision_cutoff=datetime(2026, 10, 14, 12, 0, tzinfo=_TAIPEI),
        declared_stock_codes=("2330",),
        schema_identity_sha256=_sha("c"),
        schema_descriptor=((0, "monthly_revenue", "stock_code", 0, None, 0),),
        database_file_pins_start=(source_pin,),
        database_file_pins_finish=(source_pin,),
        capture_file_pins_start=(html_pin, csv_pin, comparator_html_pin, comparator_csv_pin),
        capture_file_pins_finish=(html_pin, csv_pin, comparator_html_pin, comparator_csv_pin),
        snapshot_binding=binding,
    )
    cohort = _cohort()
    source_clock = FundamentalSnapshotSourceClockV2.from_base_clock(
        base_clock,
        cohort_pin=cohort,
        verified_markets=cohort.required_markets,
    )
    finished_manifest = make_finished_snapshot_manifest_v2(
        session_id=_sha("d"),
        reader_session_id=_sha("e"),
        source_clock=source_clock,
        processed_stock_codes=("2330",),
        result_identity_by_stock=(("2330", _sha("f")),),
        result_status_counts=(("available", 1),),
        manifest_state="complete",
    )
    finished = parse_finished_snapshot_cohort_v2(finished_manifest, source_clock)
    snapshot_reference = make_snapshot_reference_v2(
        finished,
        snapshot_root=str(snapshot_root),
        snapshot_id=snapshot_id,
    )
    snapshot_reference_sha = sha256(snapshot_reference.to_json().encode("utf-8")).hexdigest()

    finished_bytes = _canonical_json_bytes(finished_manifest)
    finished_pin = _pin(
        "finished_source_clock_manifest",
        snapshot_root / "finished_source_clock.json",
        digest=sha256(finished_bytes).hexdigest(),
        size=len(finished_bytes),
    )
    status_payload: dict[str, object] = {
        "schema_version": FUNDAMENTAL_READ_SNAPSHOT_SCHEMA,
        "status": "complete",
        "reason": None,
        "source_clock_sha256": source_clock.identity_sha256,
        "cohort_sha256": finished.identity_sha256,
    }
    status_payload["status_sha256"] = _canonical_sha256(status_payload)
    status_bytes = _canonical_json_bytes(status_payload)
    status_pin = _pin(
        "attempt_status",
        snapshot_root / "attempt_status.json",
        digest=sha256(status_bytes).hexdigest(),
        size=len(status_bytes),
    )
    stored_source_pins = (
        ("snapshot_capture.json", capture_manifest_pin),
        ("finished_source_clock.json", finished_pin),
        ("attempt_status.json", status_pin),
        ("captured/fundamental.sqlite", captured_pin),
        ("reader/fundamental.sqlite", reader_pin),
    )
    stored_files = tuple(
        FundamentalReadSnapshotArchiveStoredFileV2(
            historical_pin=pin,
            relative_path=f"saved_snapshot/{snapshot_id}/{relative}",
            size_bytes=pin.size_bytes or 0,
            sha256=pin.sha256 or "",
        )
        for relative, pin in stored_source_pins
    )
    raw_files = (
        FundamentalReadSnapshotRawArchiveFileV2(
            historical_pin=html_pin,
            relative_path="monthly_source/monthly.html",
            size_bytes=html_pin.size_bytes or 0,
            sha256=html_pin.sha256 or "",
        ),
        FundamentalReadSnapshotRawArchiveFileV2(
            historical_pin=csv_pin,
            relative_path="monthly_source/monthly.csv",
            size_bytes=csv_pin.size_bytes or 0,
            sha256=csv_pin.sha256 or "",
        ),
        FundamentalReadSnapshotRawArchiveFileV2(
            historical_pin=comparator_html_pin,
            relative_path="monthly_source/comparator.html",
            size_bytes=comparator_html_pin.size_bytes or 0,
            sha256=comparator_html_pin.sha256 or "",
        ),
        FundamentalReadSnapshotRawArchiveFileV2(
            historical_pin=comparator_csv_pin,
            relative_path="monthly_source/comparator.csv",
            size_bytes=comparator_csv_pin.size_bytes or 0,
            sha256=comparator_csv_pin.sha256 or "",
        ),
    )
    return make_raw_archive_reference_v2(
        snapshot_reference=snapshot_reference,
        snapshot_reference_sha256=snapshot_reference_sha,
        source_clock=source_clock,
        archive_root=str(archive_root),
        archive_id=archive_id,
        archived_snapshot_root=str(archive_root / "saved_snapshot" / snapshot_id),
        archived_monthly_source_root=str(archive_root / "monthly_source"),
        original_monthly_source_root=str(monthly_root),
        files=raw_files,
        snapshot_files=stored_files,
    )


def test_v2_archive_reference_round_trip_and_manifest_body_reparse(tmp_path: Path) -> None:
    reference = _build_reference(tmp_path)
    raw = reference.to_json().encode("utf-8")
    digest = sha256(raw).hexdigest()

    restored = FundamentalReadSnapshotRawArchiveReferenceV2.from_json(
        raw,
        expected_reference_sha256=digest,
    )
    unverified = decode_raw_archive_reference_v2(
        raw,
        expected_reference_sha256=digest,
    )
    manifest_reparsed = FundamentalReadSnapshotRawArchiveReferenceV2.from_manifest_dict(
        reference.to_manifest_dict()
    )

    assert restored == reference
    assert unverified.reference == reference
    assert unverified.external_reference_sha256 == digest
    assert manifest_reparsed == reference
    assert reference.schema_version == FUNDAMENTAL_READ_SNAPSHOT_RAW_ARCHIVE_V2_SCHEMA
    assert reference.source_clock.cohort_pin == _cohort()
    assert tuple(item.historical_pin.role for item in reference.files) == (
        "monthly_html", "monthly_csv", "monthly_html", "monthly_csv"
    )
    assert reference.source_scope == "current_observed_only"
    assert reference.availability_status == "cohort_hour_bound"
    assert reference.historical_pit_eligible is False
    assert reference.formal_pit_eligible is False
    assert set(reference.files[0].to_dict()) == {
        "historical_pin", "relative_path", "size_bytes", "sha256"
    }
    assert set(reference.snapshot_files[0].to_dict()) == {
        "historical_pin", "relative_path", "size_bytes", "sha256"
    }


def test_archive_manifest_and_identity_self_hash_tampering_are_rejected(tmp_path: Path) -> None:
    reference = _build_reference(tmp_path)

    with pytest.raises(ValueError, match="manifest body sha"):
        replace(reference, archive_manifest_sha256=_sha("a"))
    with pytest.raises(ValueError, match="archive identity"):
        replace(reference, archive_identity_sha256=_sha("b"))


def test_archive_reference_requires_external_digest_anchor(tmp_path: Path) -> None:
    raw = _build_reference(tmp_path).to_json().encode("utf-8")

    with pytest.raises(ValueError, match="external reference sha"):
        decode_raw_archive_reference_v2(
            raw,
            expected_reference_sha256=_sha("0"),
        )


def test_manifest_decoder_rejects_v1_extra_fields_and_wrong_fixed_policy(tmp_path: Path) -> None:
    reference = _build_reference(tmp_path)
    manifest = reference.to_manifest_dict()

    with pytest.raises(ValueError, match="欄位不符"):
        FundamentalReadSnapshotRawArchiveReferenceV2.from_manifest_dict(
            {**manifest, "archive_manifest_sha256": reference.archive_manifest_sha256}
        )
    with pytest.raises(ValueError, match="schema 不支援"):
        replace(reference, schema_version="fundamental-monthly-raw-source-archive.v1")
    with pytest.raises(ValueError, match="PIT 資格"):
        replace(reference, formal_pit_eligible=True)


def test_reference_codec_rejects_duplicate_keys_float_and_noncanonical_json(tmp_path: Path) -> None:
    raw = _build_reference(tmp_path).to_json()
    digest = sha256(raw.encode("utf-8")).hexdigest()
    duplicate = raw[:-1] + ',"schema_version":"duplicate"}'
    floating = raw[:-1] + ',"unused":1.5}'
    nan_value = raw[:-1] + ',"unused":NaN}'

    for malformed in (duplicate, floating, nan_value, raw + " "):
        with pytest.raises(ValueError):
            FundamentalReadSnapshotRawArchiveReferenceV2.from_json(
                malformed,
                expected_reference_sha256=sha256(malformed.encode("utf-8")).hexdigest(),
            )
    assert digest != sha256(duplicate.encode("utf-8")).hexdigest()


def test_manifest_parser_rejects_float_and_extra_nested_keys(tmp_path: Path) -> None:
    manifest = _build_reference(tmp_path).to_manifest_dict()
    with pytest.raises(ValueError, match="浮點數"):
        FundamentalReadSnapshotRawArchiveReferenceV2.from_manifest_dict(
            {**manifest, "unused": 1.25}
        )
    clock_value = manifest["source_clock"]
    assert type(clock_value) is dict
    changed_clock = dict(clock_value)
    changed_clock["untrusted"] = True
    with pytest.raises(ValueError):
        FundamentalReadSnapshotRawArchiveReferenceV2.from_manifest_dict(
            {**manifest, "source_clock": changed_clock}
        )


def test_archive_layout_rejects_path_escape_overlap_and_wrong_ids(tmp_path: Path) -> None:
    reference = _build_reference(tmp_path)
    with pytest.raises(ValueError, match="archive 根目錄"):
        replace(reference.files[0], relative_path="monthly_source/../escape.html")
    with pytest.raises(ValueError, match="固定 layout"):
        replace(reference, archived_monthly_source_root=str(tmp_path / "other"))
    with pytest.raises(ValueError, match="重疊"):
        make_raw_archive_reference_v2(
            snapshot_reference=reference.snapshot_reference,
            snapshot_reference_sha256=reference.snapshot_reference_sha256,
            source_clock=reference.source_clock,
            archive_root=reference.snapshot_reference.snapshot_root,
            archive_id=reference.snapshot_reference.snapshot_id,
            archived_snapshot_root=str(
                Path(reference.snapshot_reference.snapshot_root)
                / "saved_snapshot"
                / reference.snapshot_reference.snapshot_id
            ),
            archived_monthly_source_root=str(
                Path(reference.snapshot_reference.snapshot_root) / "monthly_source"
            ),
            original_monthly_source_root=reference.original_monthly_source_root,
            files=reference.files,
            snapshot_files=reference.snapshot_files,
        )
    live_database_parent = Path(reference.source_clock.database_path).parent
    nested_archive_id = "c" * 32
    nested_archive_root = live_database_parent / nested_archive_id
    with pytest.raises(ValueError, match="重疊"):
        make_raw_archive_reference_v2(
            snapshot_reference=reference.snapshot_reference,
            snapshot_reference_sha256=reference.snapshot_reference_sha256,
            source_clock=reference.source_clock,
            archive_root=str(nested_archive_root),
            archive_id=nested_archive_id,
            archived_snapshot_root=str(
                nested_archive_root
                / "saved_snapshot"
                / reference.snapshot_reference.snapshot_id
            ),
            archived_monthly_source_root=str(nested_archive_root / "monthly_source"),
            original_monthly_source_root=reference.original_monthly_source_root,
            files=reference.files,
            snapshot_files=reference.snapshot_files,
        )


def test_raw_capture_inventory_must_match_every_clock_pin(tmp_path: Path) -> None:
    reference = _build_reference(tmp_path)
    with pytest.raises(ValueError, match="inventory"):
        make_raw_archive_reference_v2(
            snapshot_reference=reference.snapshot_reference,
            snapshot_reference_sha256=reference.snapshot_reference_sha256,
            source_clock=reference.source_clock,
            archive_root=reference.archive_root,
            archive_id=reference.archive_id,
            archived_snapshot_root=reference.archived_snapshot_root,
            archived_monthly_source_root=reference.archived_monthly_source_root,
            original_monthly_source_root=reference.original_monthly_source_root,
            files=reference.files[:1],
            snapshot_files=reference.snapshot_files,
        )


def test_saved_snapshot_inventory_must_be_complete_and_pinned(tmp_path: Path) -> None:
    reference = _build_reference(tmp_path)
    with pytest.raises(ValueError, match="inventory"):
        make_raw_archive_reference_v2(
            snapshot_reference=reference.snapshot_reference,
            snapshot_reference_sha256=reference.snapshot_reference_sha256,
            source_clock=reference.source_clock,
            archive_root=reference.archive_root,
            archive_id=reference.archive_id,
            archived_snapshot_root=reference.archived_snapshot_root,
            archived_monthly_source_root=reference.archived_monthly_source_root,
            original_monthly_source_root=reference.original_monthly_source_root,
            files=reference.files,
            snapshot_files=reference.snapshot_files[:-1],
        )
    with pytest.raises(ValueError):
        tampered_pin = replace(reference.snapshot_files[-1].historical_pin, sha256=_sha("0"))
        tampered_file = replace(reference.snapshot_files[-1], historical_pin=tampered_pin)
        replace(reference, snapshot_files=(*reference.snapshot_files[:-1], tampered_file))


def test_raw_and_snapshot_file_pins_reject_bool_sizes_and_hash_drift(tmp_path: Path) -> None:
    reference = _build_reference(tmp_path)
    raw_file = reference.files[0]
    with pytest.raises(ValueError, match="大小上限"):
        replace(raw_file, size_bytes=True)
    with pytest.raises(ValueError, match="歷史 pin"):
        replace(raw_file, sha256=_sha("0"))
    with pytest.raises(ValueError, match="歷史 pin"):
        replace(reference.snapshot_files[0], sha256=_sha("0"))


def test_attempt_status_file_has_manifest_sized_bound(tmp_path: Path) -> None:
    reference = _build_reference(tmp_path)
    status_file = reference.snapshot_files[2]
    oversized = MAX_SNAPSHOT_CAPTURE_MANIFEST_BYTES + 1
    status_pin = replace(status_file.historical_pin, size_bytes=oversized)
    status_file = replace(status_file, historical_pin=status_pin, size_bytes=oversized)

    with pytest.raises(ValueError, match="attempt status 超過大小上限"):
        changed_files = (
            *reference.snapshot_files[:2],
            status_file,
            *reference.snapshot_files[3:],
        )
        replace(reference, snapshot_files=changed_files)


def test_archive_reader_does_not_confuse_wire_hash_with_file_verification(tmp_path: Path) -> None:
    reference = _build_reference(tmp_path)
    raw = reference.to_json().encode("utf-8")
    wire_sha = sha256(raw).hexdigest()
    decoded = decode_raw_archive_reference_v2(raw, expected_reference_sha256=wire_sha)

    assert decoded.reference.archive_identity_sha256 == reference.archive_identity_sha256
    assert decoded.external_reference_sha256 == wire_sha
    assert decoded.reference.files == reference.files
    # Codec 只核摘要與聲明；檔案 bytes 仍須由後續 filesystem reader 實際讀回驗證。

