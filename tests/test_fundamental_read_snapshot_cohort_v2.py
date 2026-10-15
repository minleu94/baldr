"""每日 cohort 時間依據與 V2 snapshot codec 的純型別反例。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueMarketSnapshotPin,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DailySourceUseScope,
)
from data_module.fundamental_read_snapshot import (
    FundamentalFilePin,
    FundamentalReadSnapshotBinding,
    FundamentalReadSnapshotFileReference,
    FundamentalSnapshotSourceClock,
)
from data_module.fundamental_read_snapshot_cohort_v2 import (
    FUNDAMENTAL_READ_SNAPSHOT_V2_SCHEMA,
    FinishedFundamentalSnapshotReadCohortV2,
    FundamentalReadSnapshotReferenceV2,
    FundamentalSnapshotSourceClockV2,
    decode_snapshot_reference_v2,
    encode_snapshot_reference_v2,
    make_finished_snapshot_manifest_v2,
    make_snapshot_reference_v2,
    parse_finished_snapshot_cohort_v2,
    parse_snapshot_source_clock_v2,
)


_TAIPEI = ZoneInfo("Asia/Taipei")


def _sha(char: str) -> str:
    return char * 64


def _file_pin(role: str, path: Path, *, digest: str, size: int = 9) -> FundamentalFilePin:
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


def _daily_cohort(batch_suffix: str = "a") -> DailyMonthlyRevenueCohortPin:
    market_pins: list[DailyMonthlyRevenueMarketSnapshotPin] = []
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
        batch_finished = datetime(2026, 10, 14, 9 + index, 45, tzinfo=_TAIPEI)
        available_hour = batch_finished.replace(minute=0, second=0, microsecond=0)
        if batch_finished.minute or batch_finished.second or batch_finished.microsecond:
            available_hour = available_hour.replace(hour=available_hour.hour + 1)
        market_pins.append(
            DailyMonthlyRevenueMarketSnapshotPin(
                market=market,
                period="2026-09",
                batch_id=f"{market}-20261014-{batch_suffix}",
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
                source_batch_started_at=datetime(
                    2026, 10, 14, 9 + index, 10, tzinfo=_TAIPEI
                ),
                first_persisted_at=datetime(
                    2026, 10, 14, 9 + index, 30, tzinfo=_TAIPEI
                ),
                successful_batch_completed_at=batch_finished,
            )
        )
    frozen_pins = tuple(market_pins)
    return DailyMonthlyRevenueCohortPin(
        period="2026-09",
        required_markets=("twse", "tpex"),
        market_pins=frozen_pins,
        available_hour=max(item.available_hour for item in frozen_pins),
    )


def _base_clock(tmp_path: Path, *, snapshot_id: str = "a" * 32) -> FundamentalSnapshotSourceClock:
    root = tmp_path / snapshot_id
    source_db = tmp_path / "fundamental.sqlite"
    reader_db = root / "reader" / "fundamental.sqlite"
    manifest_path = root / "capture_manifest.json"
    digest = _sha("6")
    source_pins = (_file_pin("sqlite_main", source_db, digest=digest),)
    captured_ref = FundamentalReadSnapshotFileReference(
        role="sqlite_main",
        relative_path="captured/fundamental.sqlite",
        size_bytes=9,
        sha256=digest,
    )
    reader_ref = FundamentalReadSnapshotFileReference(
        role="sqlite_main",
        relative_path="reader/fundamental.sqlite",
        size_bytes=9,
        sha256=digest,
    )
    # 原始 capture 路徑在不同 snapshot operation 間固定；copy 內部檔案仍由 binding 綁定。
    captured_pin = _file_pin(
        "sqlite_main", tmp_path / "monthly" / "source.html", digest=digest
    )
    reader_pin = _file_pin("sqlite_main", reader_db, digest=digest)
    manifest_pin = _file_pin("capture_manifest", manifest_path, digest=_sha("7"), size=128)
    binding = FundamentalReadSnapshotBinding(
        snapshot_id=snapshot_id,
        snapshot_root=str(root),
        source_database_path=str(source_db),
        reader_database_path=str(reader_db),
        source_file_pins_start=source_pins,
        source_file_pins_after_copy=source_pins,
        source_file_pins_finish=source_pins,
        captured_files=(captured_ref,),
        captured_file_pins_start=(captured_pin,),
        captured_file_pins_finish=(captured_pin,),
        capture_manifest_pin_start=manifest_pin,
        capture_manifest_pin_finish=manifest_pin,
        reader_files=(reader_ref,),
        reader_file_pins_finish=(reader_pin,),
        sqlite_journal_mode="rollback",
        wal_sidecar_state="not_applicable",
        source_snapshot_sha256=_sha("8"),
        source_copy_bytes=9,
        reader_only_sidecar_bytes=0,
        duplicated_disk_bytes=18,
    )
    return FundamentalSnapshotSourceClock(
        database_path=str(source_db),
        decision_cutoff=datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc),
        declared_stock_codes=("2330",),
        schema_identity_sha256=_sha("9"),
        schema_descriptor=((0, "monthly_revenue", "stock_code", 0, None, 0),),
        database_file_pins_start=source_pins,
        database_file_pins_finish=source_pins,
        capture_file_pins_start=(captured_pin,),
        capture_file_pins_finish=(captured_pin,),
        snapshot_binding=binding,
    )


def _clock_v2(
    tmp_path: Path,
    *,
    snapshot_id: str = "a" * 32,
    cohort: DailyMonthlyRevenueCohortPin | None = None,
) -> FundamentalSnapshotSourceClockV2:
    base = _base_clock(tmp_path, snapshot_id=snapshot_id)
    selected_cohort = cohort if cohort is not None else _daily_cohort()
    return FundamentalSnapshotSourceClockV2.from_base_clock(
        base,
        cohort_pin=selected_cohort,
        verified_markets=selected_cohort.required_markets,
    )


def _complete_manifest(
    clock: FundamentalSnapshotSourceClockV2,
    *,
    reader_session_id: str = _sha("b"),
) -> dict[str, object]:
    return make_finished_snapshot_manifest_v2(
        session_id=_sha("c"),
        reader_session_id=reader_session_id,
        source_clock=clock,
        processed_stock_codes=("2330",),
        result_identity_by_stock=(("2330", _sha("d")),),
        result_status_counts=(("available", 1),),
        manifest_state="complete",
    )


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(raw).hexdigest()


def test_source_clock_round_trip_keeps_daily_pin_and_fixed_policies(tmp_path: Path) -> None:
    clock = _clock_v2(tmp_path)

    restored = parse_snapshot_source_clock_v2(clock.to_dict())
    assert restored == clock
    assert FundamentalSnapshotSourceClockV2.from_json(clock.to_json()) == clock
    assert restored.availability_status == "cohort_hour_bound"
    assert restored.source_scope == "current_observed_only"
    assert restored.historical_pit_eligible is False
    assert restored.formal_pit_eligible is False
    assert restored.verified_markets == ("twse", "tpex")
    assert restored.cohort_pin.to_dict() == clock.cohort_pin.to_dict()


def test_empty_result_snapshot_clock_still_refuses_future_cohort(tmp_path: Path) -> None:
    clock = _clock_v2(tmp_path)
    with pytest.raises(ValueError, match="cohort_after_decision_cutoff"):
        replace(clock, decision_cutoff=clock.cohort_pin.available_hour - timedelta(microseconds=1))


def test_content_identity_excludes_copy_binding_but_includes_full_daily_pin(
    tmp_path: Path,
) -> None:
    first = _clock_v2(tmp_path, snapshot_id="a" * 32)
    second = _clock_v2(tmp_path, snapshot_id="e" * 32)
    changed_pin = replace(
        first.cohort_pin.market_pins[0],
        batch_id="twse-20261014-revision",
    )
    changed_cohort = replace(
        first.cohort_pin,
        market_pins=(changed_pin, first.cohort_pin.market_pins[1]),
    )
    third = _clock_v2(tmp_path, cohort=changed_cohort)

    assert first.snapshot_binding != second.snapshot_binding
    assert first.identity_sha256 != second.identity_sha256
    assert first.source_content_identity_sha256 == second.source_content_identity_sha256
    assert first.cohort_sha256 != third.cohort_sha256
    assert first.source_content_identity_sha256 != third.source_content_identity_sha256


def test_source_clock_rejects_v1_extra_fields_and_hash_tampering(tmp_path: Path) -> None:
    clock = _clock_v2(tmp_path)
    payload = clock.to_dict()
    payload["availability_status"] = "unknown"
    with pytest.raises(ValueError, match="source_clock_v2_contract_invalid|availability"):
        parse_snapshot_source_clock_v2(payload)

    payload = clock.to_dict()
    payload["unrecognized"] = "extra"
    with pytest.raises(ValueError, match="fields_invalid"):
        parse_snapshot_source_clock_v2(payload)

    payload = clock.to_dict()
    payload["cohort_sha256"] = _sha("f")
    with pytest.raises(ValueError, match="digest_mismatch"):
        parse_snapshot_source_clock_v2(payload)

    v1_payload = _base_clock(tmp_path).to_dict()
    with pytest.raises(ValueError, match="fields_invalid"):
        parse_snapshot_source_clock_v2(v1_payload)


def test_source_clock_json_rejects_duplicate_keys_and_noncanonical_bytes(tmp_path: Path) -> None:
    clock = _clock_v2(tmp_path)
    duplicate = (
        '{"schema_version":"selection-fundamental-source-clock.snapshot.v2",'
        + clock.to_json()[1:]
    )
    with pytest.raises(ValueError, match="json_invalid"):
        FundamentalSnapshotSourceClockV2.from_json(duplicate)

    with pytest.raises(ValueError, match="not_canonical"):
        FundamentalSnapshotSourceClockV2.from_json(" " + clock.to_json())


def test_complete_manifest_parse_emits_full_canonical_manifest_sha(tmp_path: Path) -> None:
    clock = _clock_v2(tmp_path)
    manifest = _complete_manifest(clock)

    finished = parse_finished_snapshot_cohort_v2(manifest, clock)
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert type(finished) is FinishedFundamentalSnapshotReadCohortV2
    assert finished.finished_manifest_sha256 == sha256(canonical).hexdigest()
    assert finished.reader_session_id == _sha("b")
    assert finished.source_clock.cohort_sha256 == clock.cohort_sha256
    assert manifest["schema_version"] == FUNDAMENTAL_READ_SNAPSHOT_V2_SCHEMA


def test_finished_parser_rejects_candidate_wrong_clock_and_inner_ledger_tampering(
    tmp_path: Path,
) -> None:
    clock = _clock_v2(tmp_path)
    candidate = make_finished_snapshot_manifest_v2(
        session_id=_sha("c"),
        reader_session_id=_sha("b"),
        source_clock=clock,
        processed_stock_codes=("2330",),
        result_identity_by_stock=(("2330", _sha("d")),),
        result_status_counts=(("available", 1),),
        manifest_state="candidate_pending_publication",
    )
    with pytest.raises(ValueError, match="not_complete"):
        parse_finished_snapshot_cohort_v2(candidate, clock)

    with pytest.raises(ValueError, match="clock_mismatch"):
        parse_finished_snapshot_cohort_v2(
            _complete_manifest(clock),
            replace(clock, decision_cutoff=clock.decision_cutoff + timedelta(hours=1)),
        )

    with pytest.raises(ValueError, match="binding_mismatch"):
        parse_finished_snapshot_cohort_v2(
            _complete_manifest(clock), _clock_v2(tmp_path, snapshot_id="e" * 32),
        )

    tampered = _complete_manifest(clock)
    ledger = tampered["finished_cohort"]
    assert isinstance(ledger, dict)
    ledger["reader_session_id"] = _sha("e")
    body = {key: value for key, value in tampered.items() if key != "manifest_sha256"}
    tampered["manifest_sha256"] = _canonical_sha256(body)
    with pytest.raises(ValueError, match="ledger_v2_identity_mismatch"):
        parse_finished_snapshot_cohort_v2(tampered, clock)


def test_reference_v2_requires_external_sha_and_round_trips_exactly(tmp_path: Path) -> None:
    clock = _clock_v2(tmp_path)
    finished = parse_finished_snapshot_cohort_v2(_complete_manifest(clock), clock)
    reference = make_snapshot_reference_v2(
        finished,
        snapshot_root=clock.snapshot_binding.snapshot_root,
        snapshot_id=clock.snapshot_binding.snapshot_id,
    )
    raw = encode_snapshot_reference_v2(reference)
    external_sha = sha256(raw).hexdigest()

    restored = decode_snapshot_reference_v2(
        raw,
        expected_reference_sha256=external_sha,
    )
    assert restored == reference
    assert FundamentalReadSnapshotReferenceV2.from_json(
        reference.to_json(),
        expected_reference_sha256=external_sha,
    ) == reference
    assert restored.daily_cohort_sha256 == clock.cohort_sha256
    assert restored.finished_manifest_sha256 == finished.finished_manifest_sha256

    with pytest.raises(ValueError, match="external_sha_mismatch"):
        decode_snapshot_reference_v2(raw, expected_reference_sha256=_sha("f"))
    with pytest.raises(ValueError, match="external_sha_invalid"):
        decode_snapshot_reference_v2(raw, expected_reference_sha256="sha256:" + external_sha)


def test_reference_v2_rejects_v1_extra_duplicate_and_oversize_inputs(tmp_path: Path) -> None:
    clock = _clock_v2(tmp_path)
    finished = parse_finished_snapshot_cohort_v2(_complete_manifest(clock), clock)
    reference = make_snapshot_reference_v2(
        finished,
        snapshot_root=clock.snapshot_binding.snapshot_root,
        snapshot_id=clock.snapshot_binding.snapshot_id,
    )
    payload = reference.to_dict()
    payload["schema_version"] = "fundamental-read-snapshot-reference.v1"
    v1_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ValueError, match="fields_invalid|schema_unsupported"):
        decode_snapshot_reference_v2(
            v1_bytes,
            expected_reference_sha256=sha256(v1_bytes).hexdigest(),
        )

    duplicate = b'{"schema_version":"fundamental-read-snapshot-reference.v2",' + reference.to_json().encode("utf-8")[1:]
    with pytest.raises(ValueError, match="json_invalid"):
        decode_snapshot_reference_v2(
            duplicate,
            expected_reference_sha256=sha256(duplicate).hexdigest(),
        )

    oversized = b" " * (8 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="exceeds_size_limit"):
        decode_snapshot_reference_v2(
            oversized,
            expected_reference_sha256=sha256(oversized).hexdigest(),
        )
