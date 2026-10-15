from __future__ import annotations

import base64
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

import pytest

from app_module import official_calendar_daily_snapshot_v1 as daily_snapshot
from app_module import recommendation_portfolio_calendar_artifact_v1 as calendar_artifact
from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    RecommendationPortfolioCalendarArtifactV1Error,
)
from app_module.recommendation_portfolio_calendar_evidence_v1 import (
    PortfolioPeriodCalendarEvidenceV1Error,
)
from data_module.daily_source_snapshot import DailySourceUseAcceptance
from data_module.official_calendar_bundle import (
    TPEX_MARKET_CALENDAR_URL,
    TWSE_HOLIDAY_SCHEDULE_URL,
)
from data_module.official_calendar_transport_v1 import (
    OfficialCalendarJsonTransportV1,
    OfficialCalendarTransportError,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_START = date(2026, 1, 2)
_END = date(2026, 1, 6)
_SOURCE_STARTED = datetime(2026, 1, 2, 13, 30, tzinfo=_TAIPEI)
_BODY_COMPLETED = datetime(2026, 1, 2, 13, 40, tzinfo=_TAIPEI)
_ACCEPTED_AT = datetime(2026, 1, 2, 13, 45, tzinfo=_TAIPEI)
_FIRST_PERSISTED = datetime(2026, 1, 2, 14, 45, tzinfo=_TAIPEI)
_BATCH_CLOCKS = (
    _FIRST_PERSISTED,
    datetime(2026, 1, 2, 14, 46, tzinfo=_TAIPEI),
    datetime(2026, 1, 2, 14, 47, tzinfo=_TAIPEI),
    datetime(2026, 1, 2, 14, 48, tzinfo=_TAIPEI),
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _acceptances(*, suffix: str = "") -> dict[str, DailySourceUseAcceptance]:
    result: dict[str, DailySourceUseAcceptance] = {}
    endpoints = {
        "twse": TWSE_HOLIDAY_SCHEDULE_URL,
        "tpex": TPEX_MARKET_CALENDAR_URL,
    }
    for market, endpoint in endpoints.items():
        scope = daily_snapshot.calendar_daily_use_scope_v1(market)
        result[market] = DailySourceUseAcceptance(
            scope=scope,
            acceptance_id=f"synthetic-{market}-acceptance{suffix}",
            accepted_at=_ACCEPTED_AT,
            official_source_endpoint=endpoint,
            document_chain=(f"{endpoint}#synthetic-fixture", "synthetic-test-chain"),
            acceptance_evidence_ref=f"synthetic-calendar-acceptance:{market}{suffix}",
            authorization_scope=scope.intended_use,
        )
    return result


def _roots(tmp_path: Path) -> tuple[Path, tuple[Path, ...]]:
    protected = tuple(
        tmp_path / name for name in ("formal-data", "output", "personal-data")
    )
    for path in protected:
        path.mkdir()
    research = tmp_path / "research-candidates"
    research.mkdir()
    return research, protected


def _twse_raw(year: int, *, malformed_schedule: bool = False) -> bytes:
    if malformed_schedule:
        payload: object = {"unexpected": "object instead of annual array"}
    else:
        roc_year = year - 1911
        payload = [
            {
                "Name": "元旦",
                "Date": f"{roc_year:03d}0101",
                "Description": "依規定放假一日。",
            }
        ]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _tpex_raw(month: str, *, extra_holidays: Iterable[str] = ()) -> bytes:
    year, month_number = int(month[:4]), int(month[4:])
    first = date(year, month_number, 1)
    next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    extra = set(extra_holidays)
    rows: dict[str, dict[str, object]] = {}
    current = first
    while current < next_month:
        is_weekend = current.weekday() >= 5
        is_holiday = is_weekend or current.isoformat() in extra
        rows[current.strftime("%Y%m%d")] = {
            "holiday": is_holiday,
            "holidayList": ["synthetic holiday"] if is_holiday else [],
        }
        current += timedelta(days=1)
    payload = {"calendar": {"total": len(rows), "data": rows, "status": "success"}}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _transport(
    kind: str,
    key: str,
    *,
    raw: bytes | None = None,
    started_at: datetime = _SOURCE_STARTED,
    body_completed_at: datetime = _BODY_COMPLETED,
    extra_holidays: Iterable[str] = (),
) -> OfficialCalendarJsonTransportV1:
    if kind == "twse":
        endpoint = TWSE_HOLIDAY_SCHEDULE_URL
        params = {"queryYear": str(int(key) - 1911)}
        body = _twse_raw(int(key)) if raw is None else raw
    else:
        endpoint = TPEX_MARKET_CALENDAR_URL
        params = {"ym": key, "lang": "zh-tw"}
        body = _tpex_raw(key, extra_holidays=extra_holidays) if raw is None else raw
    request_url = endpoint + "?" + "&".join(f"{name}={value}" for name, value in params.items())
    headers = (
        ("content-length", str(len(body))),
        ("content-type", "application/json; charset=utf-8"),
        ("date", "Fri, 02 Jan 2026 05:40:00 GMT"),
        ("last-modified", "Thu, 01 Jan 2026 08:00:00 GMT"),
    )
    return OfficialCalendarJsonTransportV1(
        kind=kind,  # type: ignore[arg-type]
        key=key,
        request_url=request_url,
        response_url=request_url,
        http_status=200,
        headers=headers,
        started_at=started_at,
        body_completed_at=body_completed_at,
        raw_bytes=body,
        raw_sha256=_sha(body),
        received_body_bytes=len(body),
        eof_observed=True,
    )


def _transports(
    start: date = _START,
    end: date = _END,
    *,
    malformed_twse: bool = False,
    extra_tpex_holidays: Iterable[str] = (),
) -> tuple[OfficialCalendarJsonTransportV1, ...]:
    keys: list[tuple[str, str]] = [
        ("twse", str(year)) for year in range(start.year, end.year + 1)
    ]
    month = start.replace(day=1)
    while month <= end:
        keys.append(("tpex", month.strftime("%Y%m")))
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    result = []
    for kind, key in sorted(keys):
        if kind == "twse" and malformed_twse:
            result.append(_transport(kind, key, raw=_twse_raw(int(key), malformed_schedule=True)))
        elif kind == "tpex":
            result.append(_transport(kind, key, extra_holidays=extra_tpex_holidays))
        else:
            result.append(_transport(kind, key))
    return tuple(result)


def _clock(values: Iterable[datetime]) -> tuple[Callable[[], datetime], list[datetime]]:
    iterator = iter(values)
    calls: list[datetime] = []

    def get_time() -> datetime:
        value = next(iterator)
        calls.append(value)
        return value

    return get_time, calls


def _write(
    root: Path,
    protected: tuple[Path, ...],
    *,
    batch_id: str = "calendar-batch-001",
    start: date = _START,
    end: date = _END,
    transports: tuple[OfficialCalendarJsonTransportV1, ...] | None = None,
    acceptances: dict[str, DailySourceUseAcceptance] | None = None,
    clock_values: Iterable[datetime] = _BATCH_CLOCKS,
    check_cancel: Callable[[], bool] | None = None,
) -> tuple[daily_snapshot.OfficialCalendarDailySnapshotV1, list[datetime]]:
    clock, calls = _clock(clock_values)
    result = daily_snapshot.write_official_calendar_daily_snapshot_v1(
        root,
        batch_id=batch_id,
        start_date=start,
        end_date=end,
        transports=_transports(start, end) if transports is None else transports,
        trusted_acceptances=_acceptances() if acceptances is None else acceptances,
        protected_roots=protected,
        clock=clock,
        check_cancel=check_cancel,
    )
    return result, calls


def _read(
    batch_directory: Path,
    protected: tuple[Path, ...],
    *,
    acceptances: dict[str, DailySourceUseAcceptance] | None = None,
    decision_cutoff: datetime | None = None,
) -> daily_snapshot.OfficialCalendarDailySnapshotV1:
    return daily_snapshot.read_official_calendar_daily_snapshot_v1(
        batch_directory,
        expected_manifest_sha256=_sha((batch_directory / "manifest.json").read_bytes()),
        expected_receipt_sha256=_sha((batch_directory / "receipt.json").read_bytes()),
        trusted_acceptances=_acceptances() if acceptances is None else acceptances,
        protected_roots=protected,
        decision_cutoff=decision_cutoff,
    )


def test_writer_fsyncs_create_only_capture_manifest_receipt_and_reads_complete_two_market_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, protected = _roots(tmp_path)
    acceptances = _acceptances()
    assert acceptances["twse"].scope == daily_snapshot.calendar_daily_use_scope_v1("twse")
    assert acceptances["tpex"].scope == daily_snapshot.calendar_daily_use_scope_v1("tpex")
    assert acceptances["twse"].scope != acceptances["tpex"].scope
    fsync_calls: list[int] = []
    original_fsync = calendar_artifact.os.fsync

    def tracked_fsync(descriptor: int) -> None:
        fsync_calls.append(descriptor)
        original_fsync(descriptor)

    monkeypatch.setattr(calendar_artifact.os, "fsync", tracked_fsync)
    snapshot, clock_calls = _write(root, protected, acceptances=acceptances)
    batch = snapshot.batch_directory

    assert clock_calls == list(_BATCH_CLOCKS)
    assert len(fsync_calls) == 4
    assert sorted(path.name for path in batch.iterdir()) == [
        "capture.json", "manifest.json", "receipt.json",
    ]
    capture_raw = (batch / "capture.json").read_bytes()
    manifest_raw = (batch / "manifest.json").read_bytes()
    receipt_raw = (batch / "receipt.json").read_bytes()
    capture = json.loads(capture_raw.decode("utf-8"))
    manifest = json.loads(manifest_raw.decode("utf-8"))
    receipt = json.loads(receipt_raw.decode("utf-8"))

    assert capture["schema_version"] == daily_snapshot.CALENDAR_DAILY_CAPTURE_SCHEMA_V1
    assert len(capture["transports"]) == 2
    assert {item["kind"] for item in capture["transports"]} == {"twse", "tpex"}
    assert manifest["partitions"] == ["tpex:202601", "twse:2026"]
    assert manifest["expected_session_dates"] == {
        "twse": ["2026-01-02", "2026-01-05", "2026-01-06"],
        "tpex": ["2026-01-02", "2026-01-05", "2026-01-06"],
    }
    assert manifest["official_timestamp"] is None
    assert manifest["official_timestamp_original_text"] == ""
    assert manifest["official_time_basis"] == "not_in_supported_source_schema"
    assert receipt["batch_status"] == "success"
    assert receipt["first_persisted_at"] == _FIRST_PERSISTED.isoformat()
    assert receipt["successful_batch_completed_at"] == _BATCH_CLOCKS[1].isoformat()
    assert snapshot.manifest_sha256 == _sha(manifest_raw)
    assert snapshot.receipt_sha256 == _sha(receipt_raw)
    assert snapshot.capture_sha256 == _sha(capture_raw)
    assert snapshot.available_hour == datetime(2026, 1, 2, 15, 0, tzinfo=_TAIPEI)
    assert snapshot.availability_basis == "successful_batch_hour_only"
    assert snapshot.evidence.candidate_only is True
    assert snapshot.evidence.historical_pit_eligible is False
    assert snapshot.evidence.performance_eligible is False
    assert snapshot.evidence.formal_clock_eligible is False
    assert snapshot.historical_pit_eligible is False
    assert snapshot.performance_eligible is False
    assert snapshot.formal_clock_eligible is False
    assert all("date" in dict(item["headers"]) for item in capture["transports"])
    assert all("last-modified" in dict(item["headers"]) for item in capture["transports"])


def test_daily_cutoff_is_exact_and_does_not_round_up_before_available_hour(
    tmp_path: Path,
) -> None:
    root, protected = _roots(tmp_path)
    snapshot, _ = _write(root, protected)

    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotError,
        match="calendar_batch_not_available_at_cutoff",
    ):
        _read(
            snapshot.batch_directory,
            protected,
            decision_cutoff=datetime(2026, 1, 2, 14, 59, 59, tzinfo=_TAIPEI),
        )

    available = _read(
        snapshot.batch_directory,
        protected,
        decision_cutoff=datetime(2026, 1, 2, 15, 0, tzinfo=_TAIPEI),
    )
    assert available.available_hour == datetime(2026, 1, 2, 15, 0, tzinfo=_TAIPEI)
    assert available.is_available_at(datetime(2026, 1, 2, 14, 59, 59, tzinfo=_TAIPEI)) is False
    assert available.is_available_at(datetime(2026, 1, 2, 15, 0, tzinfo=_TAIPEI)) is True


def test_exact_hour_completion_uses_next_hour_publication_guard_basis(tmp_path: Path) -> None:
    root, protected = _roots(tmp_path)
    boundary = datetime(2026, 1, 2, 14, 0, tzinfo=_TAIPEI)
    snapshot, calls = _write(root, protected, clock_values=(boundary,) * 4)

    assert calls == [boundary] * 4
    assert snapshot.successful_batch_completed_at == boundary
    assert snapshot.available_hour == datetime(2026, 1, 2, 15, 0, tzinfo=_TAIPEI)
    assert snapshot.availability_basis == (
        "successful_batch_hour_exact_boundary_publication_guard"
    )


@pytest.mark.parametrize(
    ("case", "mutate"),
    [
        ("missing_twse", lambda values: tuple(item for item in values if item.kind != "twse")),
        ("missing_tpex", lambda values: tuple(item for item in values if item.kind != "tpex")),
        ("duplicate_twse", lambda values: values + (next(item for item in values if item.kind == "twse"),)),
        ("duplicate_tpex", lambda values: values + (next(item for item in values if item.kind == "tpex"),)),
        ("unexpected_twse", lambda values: values + (_transport("twse", "2027"),)),
        ("unexpected_tpex", lambda values: values + (_transport("tpex", "202602"),)),
    ],
)
def test_writer_rejects_missing_duplicate_and_unexpected_market_partitions(
    tmp_path: Path,
    case: str,
    mutate: Callable[[tuple[OfficialCalendarJsonTransportV1, ...]], tuple[OfficialCalendarJsonTransportV1, ...]],
) -> None:
    del case
    root, protected = _roots(tmp_path)
    values = mutate(_transports())

    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotError,
        match="calendar_batch_missing_duplicate_or_unexpected_partition",
    ):
        _write(root, protected, transports=values)

    stage = root / ".staging" / "calendar-batch-001"
    assert (stage / "capture.json").is_file()
    assert (stage / "failure.json").is_file()
    assert not (root / "batches" / "calendar-batch-001").exists()


def test_bad_calendar_parser_keeps_transport_raw_in_isolated_failed_staging(
    tmp_path: Path,
) -> None:
    root, protected = _roots(tmp_path)
    malformed = _transports(malformed_twse=True)

    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error,
                       match="official_calendar_builder_rejected"):
        _write(root, protected, transports=malformed)

    stage = root / ".staging" / "calendar-batch-001"
    capture = json.loads((stage / "capture.json").read_text(encoding="utf-8"))
    failure = json.loads((stage / "failure.json").read_text(encoding="utf-8"))
    twse_capture = next(item for item in capture["transports"] if item["kind"] == "twse")
    assert base64.b64decode(twse_capture["raw_base64"]) == _twse_raw(2026, malformed_schedule=True)
    assert failure["successful"] is False
    assert "official_calendar_builder_rejected" in failure["reason"]
    assert not (stage / "receipt.json").exists()
    assert not (root / "batches" / "calendar-batch-001").exists()


def test_writer_rejects_93_day_overflow_but_accepts_93_inclusive_days(
    tmp_path: Path,
) -> None:
    root, protected = _roots(tmp_path)
    start, end_93, end_94 = date(2026, 1, 2), date(2026, 4, 4), date(2026, 4, 5)
    assert (end_93 - start).days + 1 == 93
    assert (end_94 - start).days + 1 == 94
    wide_transports = _transports(start, end_94)

    accepted, _ = _write(
        root,
        protected,
        batch_id="calendar-93-days",
        start=start,
        end=end_93,
        transports=wide_transports,
    )
    assert accepted.evidence.end_date == end_93.isoformat()
    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotError,
        match="calendar_batch_inclusive_93_day_limit",
    ):
        _write(
            root,
            protected,
            batch_id="calendar-94-days",
            start=start,
            end=end_94,
            transports=wide_transports,
        )
    failed = root / ".staging" / "calendar-94-days"
    assert (failed / "capture.json").is_file()
    assert (failed / "failure.json").is_file()
    assert not (root / "batches" / "calendar-94-days").exists()


def test_writer_rejects_cross_hour_first_and_completed_persistence(tmp_path: Path) -> None:
    root, protected = _roots(tmp_path)
    clocks = (
        datetime(2026, 1, 2, 14, 59, tzinfo=_TAIPEI),
        datetime(2026, 1, 2, 15, 0, 1, tzinfo=_TAIPEI),
    )

    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotError,
        match="calendar_batch_persistence_crossed_hour_or_clock_reversed",
    ):
        _write(root, protected, clock_values=clocks)

    stage = root / ".staging" / "calendar-batch-001"
    assert (stage / ".receipt.pending.json").is_file()
    assert (stage / "failure.json").is_file()
    assert not (stage / "receipt.json").exists()
    assert not (root / "batches" / "calendar-batch-001").exists()


def test_published_after_guard_keeps_pending_failure_and_cannot_be_read(tmp_path: Path) -> None:
    root, protected = _roots(tmp_path)
    clocks = (
        datetime(2026, 1, 2, 14, 45, tzinfo=_TAIPEI),
        datetime(2026, 1, 2, 14, 46, tzinfo=_TAIPEI),
        datetime(2026, 1, 2, 14, 47, tzinfo=_TAIPEI),
        datetime(2026, 1, 2, 15, 0, 1, tzinfo=_TAIPEI),
    )

    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotError,
        match="calendar_batch_published_outside_guard",
    ):
        _write(root, protected, clock_values=clocks)

    final = root / "batches" / "calendar-batch-001"
    assert (final / ".receipt.pending.json").is_file()
    assert (final / "failure.json").is_file()
    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotError,
        match="calendar_batch_not_published_or_pending",
    ):
        _read(final, protected)


def test_cancellation_after_publication_keeps_barrier_and_does_not_issue_readable_success(
    tmp_path: Path,
) -> None:
    root, protected = _roots(tmp_path)
    calls = 0

    def cancel_after_publish() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 4

    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotCancelled,
        match="calendar_batch_cancelled",
    ):
        _write(root, protected, check_cancel=cancel_after_publish)

    final = root / "batches" / "calendar-batch-001"
    assert (final / ".receipt.pending.json").is_file()
    assert (final / "failure.json").is_file()
    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotError,
        match="calendar_batch_not_published_or_pending",
    ):
        _read(final, protected)


def test_pending_marker_unlink_failure_keeps_batch_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, protected = _roots(tmp_path)
    original_unlink = Path.unlink

    def fail_final_pending_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == ".receipt.pending.json" and path.parent.parent.name == "batches":
            raise OSError("synthetic pending unlink failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_final_pending_unlink)
    with pytest.raises(OSError, match="synthetic pending unlink failure"):
        _write(root, protected)

    final = root / "batches" / "calendar-batch-001"
    assert (final / ".receipt.pending.json").is_file()
    assert (final / "failure.json").is_file()
    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotError,
        match="calendar_batch_not_published_or_pending",
    ):
        _read(final, protected)


def test_cancel_during_pending_read_keeps_barrier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, protected = _roots(tmp_path)
    original_read = daily_snapshot.read_calendar_version_bytes_exact_v1
    cancelled = False

    def read_then_cancel(path: Path, *, expected_sha256: str, protected_roots: tuple[Path, ...]) -> bytes:
        nonlocal cancelled
        raw = original_read(path, expected_sha256=expected_sha256, protected_roots=protected_roots)
        if path.name == ".receipt.pending.json":
            cancelled = True
        return raw

    monkeypatch.setattr(daily_snapshot, "read_calendar_version_bytes_exact_v1", read_then_cancel)
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotCancelled):
        _write(root, protected, check_cancel=lambda: cancelled)
    final = root / "batches" / "calendar-batch-001"
    assert cancelled is True
    assert (final / ".receipt.pending.json").is_file()
    assert (final / "failure.json").is_file()
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError,
                       match="calendar_batch_not_published_or_pending"):
        _read(final, protected)


def test_reader_rejects_wrong_external_pins_changed_acceptance_and_transport_hash(
    tmp_path: Path,
) -> None:
    root, protected = _roots(tmp_path)
    snapshot, _ = _write(root, protected)
    final = snapshot.batch_directory

    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="external_sha256_mismatch"):
        daily_snapshot.read_official_calendar_daily_snapshot_v1(
            final,
            expected_manifest_sha256="0" * 64,
            expected_receipt_sha256=snapshot.receipt_sha256,
            trusted_acceptances=_acceptances(),
            protected_roots=protected,
        )

    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotError,
        match="calendar_batch_capture_or_trusted_acceptance_mismatch",
    ):
        _read(final, protected, acceptances=_acceptances(suffix="-changed"))

    capture_path = final / "capture.json"
    manifest_path = final / "manifest.json"
    receipt_path = final / "receipt.json"
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    capture["transports"][0]["raw_sha256"] = "0" * 64
    capture_raw = _canonical(capture)
    capture_sha = _sha(capture_raw)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["capture_sha256"] = capture_sha
    manifest_raw = _canonical(manifest)
    manifest_sha = _sha(manifest_raw)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["capture_sha256"] = capture_sha
    receipt["manifest_sha256"] = manifest_sha
    receipt_raw = _canonical(receipt)
    capture_path.write_bytes(capture_raw)
    manifest_path.write_bytes(manifest_raw)
    receipt_path.write_bytes(receipt_raw)

    with pytest.raises(OfficialCalendarTransportError, match="calendar_transport_decode_failed"):
        daily_snapshot.read_official_calendar_daily_snapshot_v1(
            final,
            expected_manifest_sha256=manifest_sha,
            expected_receipt_sha256=_sha(receipt_raw),
            trusted_acceptances=_acceptances(),
            protected_roots=protected,
        )


@pytest.mark.parametrize("filename", ["capture.json", "receipt.json"])
def test_reader_rejects_source_or_receipt_changed_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
) -> None:
    root, protected = _roots(tmp_path)
    snapshot, _ = _write(root, protected)
    original_read = daily_snapshot.read_calendar_version_bytes_exact_v1
    changed = False

    def read_then_replace(path: Path, *, expected_sha256: str, protected_roots: tuple[Path, ...]) -> bytes:
        nonlocal changed
        raw = original_read(path, expected_sha256=expected_sha256, protected_roots=protected_roots)
        if path.name == filename and not changed:
            path.write_bytes(raw + b" ")
            changed = True
        return raw

    monkeypatch.setattr(daily_snapshot, "read_calendar_version_bytes_exact_v1", read_then_replace)
    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="external_sha256_mismatch"):
        _read(snapshot.batch_directory, protected)
    assert changed is True


def test_correction_uses_new_batch_and_preserves_original_create_only_bytes(
    tmp_path: Path,
) -> None:
    root, protected = _roots(tmp_path)
    original, _ = _write(root, protected, batch_id="calendar-original")
    original_dir = original.batch_directory
    original_bytes = {
        name: (original_dir / name).read_bytes()
        for name in ("capture.json", "manifest.json", "receipt.json")
    }

    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotError,
        match="calendar_batch_create_only_collision",
    ):
        _write(root, protected, batch_id="calendar-original")

    corrected, _ = _write(
        root,
        protected,
        batch_id="calendar-correction",
        transports=_transports(extra_tpex_holidays=("2026-01-05",)),
    )
    assert corrected.batch_id != original.batch_id
    assert corrected.evidence.expected_session_dates("tpex") == (
        "2026-01-02", "2026-01-06",
    )
    assert all((original_dir / name).read_bytes() == raw for name, raw in original_bytes.items())
    assert (corrected.batch_directory / "capture.json").is_file()
