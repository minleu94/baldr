"""年度官方日曆沿既有 daily batch writer／reader 的限定測試。"""

from __future__ import annotations

import base64
from dataclasses import replace
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from zoneinfo import ZoneInfo

import pytest

from app_module import official_calendar_daily_snapshot_v1 as daily_snapshot
from app_module.recommendation_portfolio_annual_calendar_evidence_v1 import (
    PORTFOLIO_PERIOD_ANNUAL_CALENDAR_EVIDENCE_SCHEMA_V1,
    PortfolioPeriodAnnualCalendarEvidenceV1,
)
from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    RecommendationPortfolioCalendarArtifactV1Error,
)
from data_module.daily_source_snapshot import DailySourceUseAcceptance
from data_module.official_calendar_bundle import (
    TPEX_ANNUAL_TRADING_DATE_URL,
    TPEX_MARKET_CALENDAR_URL,
    TWSE_HOLIDAY_SCHEDULE_URL,
)
from data_module.official_calendar_transport_v1 import (
    OfficialCalendarJsonTransportV1,
    OfficialCalendarTransportError,
)
from data_module.tpex_annual_calendar_transport_v1 import (
    OfficialCalendarTpexAnnualJsonTransportV1,
)
from test_official_calendar_daily_snapshot_v1 import (
    _ACCEPTED_AT,
    _BATCH_CLOCKS,
    _clock,
    _roots,
    _acceptances as _monthly_acceptances,
    _write as _write_monthly,
)
from test_recommendation_portfolio_annual_calendar_evidence_v1 import (
    _transports as _source_annual_transports,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_START = date(2026, 2, 1)
_END = date(2026, 2, 28)
_ANNUAL_PARSER = "portfolio-period-annual-calendar-evidence.v1"
_EXPECTED_FEBRUARY_SESSIONS = (
    "2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06",
    "2026-02-09", "2026-02-10", "2026-02-11", "2026-02-23", "2026-02-24",
    "2026-02-25", "2026-02-26",
)

AnnualTransport = OfficialCalendarJsonTransportV1 | OfficialCalendarTpexAnnualJsonTransportV1


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _annual_transports() -> tuple[AnnualTransport, ...]:
    """保留年度fixture raw，換成與daily測試一致的明示合成時鐘與headers。"""
    twse, tpex = _source_annual_transports()
    started = datetime(2026, 1, 2, 13, 30, tzinfo=_TAIPEI)
    completed = datetime(2026, 1, 2, 13, 40, tzinfo=_TAIPEI)
    headers = (
        ("content-length", ""),
        ("content-type", "application/json"),
        ("date", "Fri, 02 Jan 2026 05:40:00 GMT"),
        ("last-modified", "Thu, 01 Jan 2026 08:00:00 GMT"),
    )
    result: list[AnnualTransport] = []
    for item in (twse, tpex):
        item_headers = tuple(
            (name, str(len(item.raw_bytes)) if name == "content-length" else value)
            for name, value in headers
        )
        result.append(replace(
            item, started_at=started, body_completed_at=completed, headers=item_headers,
        ))
    return tuple(result)


def _annual_acceptances(
    *, suffix: str = "", tpex_endpoint: str = TPEX_ANNUAL_TRADING_DATE_URL,
) -> tuple[DailySourceUseAcceptance, DailySourceUseAcceptance]:
    result: list[DailySourceUseAcceptance] = []
    endpoints = {"twse": TWSE_HOLIDAY_SCHEDULE_URL, "tpex": tpex_endpoint}
    for market in ("twse", "tpex"):
        scope = daily_snapshot.calendar_annual_daily_use_scope_v1(market)
        endpoint = endpoints[market]
        result.append(DailySourceUseAcceptance(
            scope=scope,
            acceptance_id=f"synthetic-annual-{market}-acceptance{suffix}",
            accepted_at=_ACCEPTED_AT,
            official_source_endpoint=endpoint,
            document_chain=(f"{endpoint}#synthetic-annual-fixture", "synthetic-annual-test-chain"),
            acceptance_evidence_ref=f"synthetic-annual-calendar-acceptance:{market}{suffix}",
            authorization_scope=scope.intended_use,
        ))
    return result[0], result[1]


def _ordered_acceptances(
    values: Sequence[DailySourceUseAcceptance],
) -> tuple[DailySourceUseAcceptance, DailySourceUseAcceptance]:
    if len(values) != 2:
        raise AssertionError("annual fixtures require exactly two ordered acceptances")
    return values[0], values[1]


def _ordered_monthly_acceptances() -> tuple[DailySourceUseAcceptance, DailySourceUseAcceptance]:
    values = _monthly_acceptances()
    return values["twse"], values["tpex"]


def _write_annual(
    root: Path,
    protected: tuple[Path, ...],
    *,
    batch_id: str = "annual-calendar-batch-001",
    start: date = _START,
    end: date = _END,
    transports: Sequence[AnnualTransport] | None = None,
    acceptances: Sequence[DailySourceUseAcceptance] | None = None,
    clock_values: Iterable[datetime] = _BATCH_CLOCKS,
    check_cancel: Callable[[], bool] | None = None,
) -> tuple[Any, list[datetime]]:
    get_clock, calls = _clock(clock_values)
    snapshot = daily_snapshot.write_official_calendar_annual_daily_snapshot_v1(
        root,
        batch_id=batch_id,
        start_date=start,
        end_date=end,
        transports=_annual_transports() if transports is None else transports,
        trusted_acceptances={
            item.scope.market: item
            for item in (_annual_acceptances() if acceptances is None else acceptances)
        },
        protected_roots=protected,
        clock=get_clock,
        check_cancel=check_cancel,
    )
    return snapshot, calls


def _read_annual(
    batch_directory: Path,
    protected: tuple[Path, ...],
    *,
    acceptances: Sequence[DailySourceUseAcceptance] | None = None,
    decision_cutoff: datetime | None = None,
    manifest_sha256: str | None = None,
    receipt_sha256: str | None = None,
    check_cancel: Callable[[], bool] | None = None,
) -> Any:
    manifest_path = batch_directory / "manifest.json"
    receipt_path = batch_directory / "receipt.json"
    return daily_snapshot.read_official_calendar_annual_daily_snapshot_v1(
        batch_directory,
        expected_manifest_sha256=(manifest_sha256 or _sha(manifest_path.read_bytes())),
        expected_receipt_sha256=(receipt_sha256 or _sha(receipt_path.read_bytes())),
        trusted_acceptances={
            item.scope.market: item
            for item in (_annual_acceptances() if acceptances is None else acceptances)
        },
        protected_roots=protected,
        decision_cutoff=decision_cutoff,
        check_cancel=check_cancel,
    )


def _change_twse_last_trade_date(
    transports: Sequence[AnnualTransport],
) -> tuple[AnnualTransport, ...]:
    changed: list[AnnualTransport] = []
    for item in transports:
        if type(item) is not OfficialCalendarJsonTransportV1 or item.kind != "twse":
            changed.append(item)
            continue
        rows = json.loads(item.raw_bytes.decode("utf-8"))
        index = next(i for i, row in enumerate(rows) if row["Name"] == "農曆春節前最後交易日")
        rows[index]["Date"], rows[index]["Weekday"] = "1150210", "二"
        rows.insert(index + 1, {
            "Name": "市場無交易，僅辦理結算交割作業", "Date": "1150211",
            "Weekday": "三", "Description": "",
        })
        raw = json.dumps(rows, ensure_ascii=False).encode("utf-8")
        changed.append(replace(
            item,
            raw_bytes=raw,
            raw_sha256=_sha(raw),
            received_body_bytes=len(raw),
            headers=tuple((name, value) for name, value in item.headers if name != "content-length")
            + (("content-length", str(len(raw))),),
        ))
    return tuple(changed)


def test_annual_artifact_uses_annual_schema_raws_and_existing_hour_policy(tmp_path: Path) -> None:
    root, protected = _roots(tmp_path)
    acceptances = _annual_acceptances()
    scopes = tuple(value.scope for value in _ordered_acceptances(acceptances))
    assert scopes[0] == daily_snapshot.calendar_annual_daily_use_scope_v1("twse")
    assert scopes[1] == daily_snapshot.calendar_annual_daily_use_scope_v1("tpex")
    assert scopes[0].source_id == "twse.official_calendar.annual"
    assert scopes[1].source_id == "tpex.official_calendar.annual"
    assert scopes[0].source_schema_version == "twse.holidaySchedule.stock_annual.v1"
    assert scopes[1].source_schema_version == "tpex.tradingDate.stock_annual.v1"
    assert all(scope.parser_version == _ANNUAL_PARSER for scope in scopes)
    assert all(scope.unit == "trading_session_date" for scope in scopes)

    transports = _annual_transports()
    snapshot, clock_calls = _write_annual(root, protected, acceptances=acceptances, transports=transports)
    batch = snapshot.batch_directory
    capture_raw = (batch / "capture.json").read_bytes()
    manifest_raw = (batch / "manifest.json").read_bytes()
    receipt_raw = (batch / "receipt.json").read_bytes()
    capture, manifest, receipt = (
        json.loads(raw.decode("utf-8")) for raw in (capture_raw, manifest_raw, receipt_raw)
    )

    assert clock_calls == list(_BATCH_CLOCKS)
    assert sorted(path.name for path in batch.iterdir()) == ["capture.json", "manifest.json", "receipt.json"]
    assert daily_snapshot.CALENDAR_ANNUAL_DAILY_CAPTURE_SCHEMA_V1 == "official-calendar-annual-daily-capture.v1"
    assert daily_snapshot.CALENDAR_ANNUAL_DAILY_MANIFEST_SCHEMA_V1 == "official-calendar-annual-daily-manifest.v1"
    assert daily_snapshot.CALENDAR_ANNUAL_DAILY_RECEIPT_SCHEMA_V1 == "official-calendar-annual-daily-receipt.v1"
    assert daily_snapshot.CALENDAR_ANNUAL_DAILY_PARSER_V1 == _ANNUAL_PARSER
    assert capture["schema_version"] == daily_snapshot.CALENDAR_ANNUAL_DAILY_CAPTURE_SCHEMA_V1
    assert capture["parser_version"] == _ANNUAL_PARSER
    assert capture["use_acceptances"] == {
        item.scope.market: item.to_dict() for item in _ordered_acceptances(acceptances)
    }
    assert len(capture["transports"]) == 2
    assert {item["schema_version"] for item in capture["transports"]} == {
        "official-calendar-json-transport.v1",
        "official-calendar-tpex-annual-json-transport.v1",
    }
    assert {_canonical(item) for item in capture["transports"]} == {
        _canonical(item.to_dict()) for item in transports
    }
    preserved_raws = {base64.b64decode(item["raw_base64"]) for item in capture["transports"]}
    assert preserved_raws == {item.raw_bytes for item in transports}

    assert manifest["schema_version"] == daily_snapshot.CALENDAR_ANNUAL_DAILY_MANIFEST_SCHEMA_V1
    assert manifest["parser_version"] == _ANNUAL_PARSER
    assert manifest["validation"]["schema"] == PORTFOLIO_PERIOD_ANNUAL_CALENDAR_EVIDENCE_SCHEMA_V1
    assert manifest["partitions"] == ["tpex-annual:2026", "twse:2026"]
    assert manifest["expected_session_dates"] == {
        "twse": list(_EXPECTED_FEBRUARY_SESSIONS),
        "tpex": list(_EXPECTED_FEBRUARY_SESSIONS),
    }
    assert manifest["official_timestamp"] is None
    assert manifest["official_timestamp_original_text"] == ""
    assert manifest["official_time_basis"] == "not_in_supported_source_schema"
    assert receipt["schema_version"] == daily_snapshot.CALENDAR_ANNUAL_DAILY_RECEIPT_SCHEMA_V1
    assert receipt["first_persisted_at"] == _BATCH_CLOCKS[0].isoformat()
    assert receipt["successful_batch_completed_at"] == _BATCH_CLOCKS[1].isoformat()
    assert receipt["available_hour"] == datetime(2026, 1, 2, 15, 0, tzinfo=_TAIPEI).isoformat()
    assert all(
        {"date", "last-modified"} <= set(dict(item["headers"]))
        for item in capture["transports"]
    )
    assert snapshot.available_hour == datetime(2026, 1, 2, 15, 0, tzinfo=_TAIPEI)
    assert snapshot.availability_basis == "successful_batch_hour_only"
    assert type(snapshot.evidence) is PortfolioPeriodAnnualCalendarEvidenceV1
    assert snapshot.evidence.expected_session_dates("twse") == _EXPECTED_FEBRUARY_SESSIONS
    assert snapshot.evidence.expected_session_dates("tpex") == _EXPECTED_FEBRUARY_SESSIONS
    assert snapshot.evidence.candidate_only is True
    assert snapshot.evidence.historical_pit_eligible is False
    assert snapshot.evidence.performance_eligible is False
    assert snapshot.evidence.formal_clock_eligible is False
    assert snapshot.historical_pit_eligible is False
    assert snapshot.performance_eligible is False
    assert snapshot.formal_clock_eligible is False
    assert _read_annual(batch, protected, acceptances=acceptances) == snapshot


def test_acceptance_mode_requires_ordered_pure_family_and_exact_annual_endpoint(
    tmp_path: Path,
) -> None:
    annual = _annual_acceptances()
    monthly = _ordered_monthly_acceptances()
    classify = daily_snapshot.calendar_daily_acceptance_mode_v1
    assert annual[0].scope != monthly[0].scope
    assert annual[1].scope != monthly[1].scope
    assert classify(_ordered_acceptances(annual)) == "annual_v1"
    assert classify(monthly) == "monthly_v1"
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        classify((annual[0], monthly[1]))
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        classify((annual[1], annual[0]))
    wrong_endpoint = _annual_acceptances(tpex_endpoint=TPEX_MARKET_CALENDAR_URL)
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        classify(_ordered_acceptances(wrong_endpoint))

    root, protected = _roots(tmp_path)
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        _write_annual(root, protected, acceptances=(annual[0], monthly[1]))
    assert not (root / "batches" / "annual-calendar-batch-001").exists()


@pytest.mark.parametrize("case", ["missing_twse", "missing_tpex", "duplicate_twse", "duplicate_tpex"])
def test_missing_or_duplicate_annual_partition_keeps_failure_and_never_publishes(
    tmp_path: Path, case: str,
) -> None:
    root, protected = _roots(tmp_path)
    twse, tpex = _annual_transports()
    values: tuple[AnnualTransport, ...] = {
        "missing_twse": (tpex,),
        "missing_tpex": (twse,),
        "duplicate_twse": (twse, twse, tpex),
        "duplicate_tpex": (twse, tpex, tpex),
    }[case]
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        _write_annual(root, protected, transports=values)

    stage = root / ".staging" / "annual-calendar-batch-001"
    capture = json.loads((stage / "capture.json").read_text(encoding="utf-8"))
    assert {base64.b64decode(item["raw_base64"]) for item in capture["transports"]} == {
        item.raw_bytes for item in values
    }
    failure = json.loads((stage / "failure.json").read_text(encoding="utf-8"))
    assert failure["successful"] is False
    assert not (stage / "receipt.json").exists()
    assert not (root / "batches" / "annual-calendar-batch-001").exists()
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        _read_annual(
            stage, protected, manifest_sha256="0" * 64, receipt_sha256="0" * 64,
        )


def test_annual_reader_rejects_wrong_pins_changed_acceptance_and_early_cutoff(tmp_path: Path) -> None:
    root, protected = _roots(tmp_path)
    snapshot, _ = _write_annual(root, protected)
    final = snapshot.batch_directory
    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="external_sha256_mismatch"):
        _read_annual(final, protected, manifest_sha256="0" * 64)
    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="external_sha256_mismatch"):
        _read_annual(final, protected, receipt_sha256="0" * 64)
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        _read_annual(final, protected, acceptances=_annual_acceptances(suffix="-changed"))
    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotError,
        match="calendar_batch_not_available_at_cutoff",
    ):
        _read_annual(
            final, protected,
            decision_cutoff=datetime(2026, 1, 2, 14, 59, 59, tzinfo=_TAIPEI),
        )
    available = _read_annual(
        final, protected, decision_cutoff=datetime(2026, 1, 2, 15, 0, tzinfo=_TAIPEI),
    )
    assert available.available_hour == datetime(2026, 1, 2, 15, 0, tzinfo=_TAIPEI)


def test_annual_exact_hour_completion_keeps_next_hour_publication_guard(tmp_path: Path) -> None:
    root, protected = _roots(tmp_path)
    boundary = datetime(2026, 1, 2, 14, 0, tzinfo=_TAIPEI)
    snapshot, calls = _write_annual(root, protected, clock_values=(boundary,) * 4)
    assert calls == [boundary] * 4
    assert snapshot.successful_batch_completed_at == boundary
    assert snapshot.available_hour == datetime(2026, 1, 2, 15, 0, tzinfo=_TAIPEI)
    assert snapshot.availability_basis == (
        "successful_batch_hour_exact_boundary_publication_guard"
    )


def test_annual_writer_keeps_inclusive_93_day_limit(tmp_path: Path) -> None:
    root, protected = _roots(tmp_path)
    start, end_93, end_94 = date(2026, 1, 2), date(2026, 4, 4), date(2026, 4, 5)
    assert (end_93 - start).days + 1 == 93
    assert (end_94 - start).days + 1 == 94
    transports = _annual_transports()
    accepted, _ = _write_annual(
        root, protected, batch_id="annual-calendar-93-days", start=start, end=end_93,
        transports=transports,
    )
    assert accepted.evidence.end_date == end_93.isoformat()
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        _write_annual(
            root, protected, batch_id="annual-calendar-94-days", start=start, end=end_94,
            transports=transports,
        )
    failed = root / ".staging" / "annual-calendar-94-days"
    assert (failed / "failure.json").is_file()
    assert not (root / "batches" / "annual-calendar-94-days").exists()


def test_annual_reader_rejects_rehashed_capture_with_tampered_transport(tmp_path: Path) -> None:
    root, protected = _roots(tmp_path)
    snapshot, _ = _write_annual(root, protected)
    final = snapshot.batch_directory
    capture_path, manifest_path, receipt_path = (
        final / "capture.json", final / "manifest.json", final / "receipt.json",
    )
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    twse = next(item for item in capture["transports"] if item.get("kind") == "twse")
    twse["raw_sha256"] = "0" * 64
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

    with pytest.raises(OfficialCalendarTransportError):
        _read_annual(
            final, protected, manifest_sha256=manifest_sha,
            receipt_sha256=_sha(receipt_raw),
        )


def test_monthly_and_annual_readers_never_fallback_or_accept_each_others_batch(
    tmp_path: Path,
) -> None:
    root, protected = _roots(tmp_path)
    annual, _ = _write_annual(root, protected, batch_id="annual-family-batch")
    monthly = _write_monthly(
        root, protected, batch_id="monthly-family-batch",
    )[0]

    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        daily_snapshot.read_official_calendar_daily_snapshot_v1(
            annual.batch_directory,
            expected_manifest_sha256=annual.manifest_sha256,
            expected_receipt_sha256=annual.receipt_sha256,
            trusted_acceptances=_monthly_acceptances(),
            protected_roots=protected,
        )
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        _read_annual(monthly.batch_directory, protected)
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        _read_annual(annual.batch_directory, protected, acceptances=_ordered_monthly_acceptances())


def test_annual_pending_marker_blocks_public_reader(tmp_path: Path) -> None:
    root, protected = _roots(tmp_path)
    snapshot, _ = _write_annual(root, protected)
    pending = snapshot.batch_directory / ".receipt.pending.json"
    pending.write_bytes(_canonical({"status": "synthetic_pending"}))
    with pytest.raises(
        daily_snapshot.OfficialCalendarDailySnapshotError,
        match="calendar_batch_not_published_or_pending",
    ):
        _read_annual(snapshot.batch_directory, protected)


def test_naive_clock_preserves_failure_without_success(tmp_path: Path) -> None:
    root, protected = _roots(tmp_path)
    naive = datetime(2026, 1, 2, 14, 45)
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        _write_annual(root, protected, clock_values=(naive,))
    stage = root / ".staging" / "annual-calendar-batch-001"
    assert (stage / "failure.json").is_file()
    assert not (root / "batches" / "annual-calendar-batch-001").exists()


def test_cancel_during_pending_read_keeps_annual_batch_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancelled_root = tmp_path / "cancelled"
    cancelled_root.mkdir()
    root2, protected2 = _roots(cancelled_root)
    original_read = daily_snapshot.read_calendar_version_bytes_exact_v1
    pending_read = False

    def read_then_cancel(
        path: Path, *, expected_sha256: str, protected_roots: tuple[Path, ...],
    ) -> bytes:
        nonlocal pending_read
        raw = original_read(path, expected_sha256=expected_sha256, protected_roots=protected_roots)
        if path.name == ".receipt.pending.json":
            pending_read = True
        return raw

    monkeypatch.setattr(daily_snapshot, "read_calendar_version_bytes_exact_v1", read_then_cancel)
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotCancelled):
        _write_annual(root2, protected2, check_cancel=lambda: pending_read)
    final = root2 / "batches" / "annual-calendar-batch-001"
    assert pending_read is True
    assert (final / ".receipt.pending.json").is_file()
    assert (final / "failure.json").is_file()
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        _read_annual(final, protected2)


def test_correction_uses_new_create_only_batch_and_preserves_original_raws(tmp_path: Path) -> None:
    root, protected = _roots(tmp_path)
    original, _ = _write_annual(root, protected, batch_id="annual-calendar-original")
    original_directory = original.batch_directory
    original_bytes = {
        name: (original_directory / name).read_bytes()
        for name in ("capture.json", "manifest.json", "receipt.json")
    }
    with pytest.raises(daily_snapshot.OfficialCalendarDailySnapshotError):
        _write_annual(root, protected, batch_id="annual-calendar-original")

    corrected, _ = _write_annual(
        root,
        protected,
        batch_id="annual-calendar-correction",
        transports=_change_twse_last_trade_date(_annual_transports()),
    )
    assert corrected.batch_id != original.batch_id
    assert corrected.evidence.expected_session_dates("twse") != original.evidence.expected_session_dates("twse")
    assert corrected.evidence.expected_session_dates("tpex") == original.evidence.expected_session_dates("tpex")
    assert all((original_directory / name).read_bytes() == raw for name, raw in original_bytes.items())
