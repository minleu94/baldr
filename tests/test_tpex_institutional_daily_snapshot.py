"""以合成單日 OpenAPI 原件檢查 TPEx daily snapshot 的 pin、時鐘與失敗守衛。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import app_module.institutional_daily_snapshot as daily
import data_module.institutional_credit_flows_service as flow_service
from app_module.institutional_daily_snapshot import (
    InstitutionalDailySnapshotError,
    InstitutionalDailySnapshotPin,
    read_institutional_daily_snapshot,
    read_twse_institutional_daily_snapshot,
    seal_institutional_capture,
    seal_twse_institutional_capture,
)
from data_module.institutional_credit_flows_service import FlowCaptureError, HttpResponse
from data_module.tpex_institutional_openapi import (
    DEALER,
    EX_FOREIGN,
    FOREIGN_DEALERS,
    FOREIGN_TOTAL,
    FIELDS,
    TPEX_OPENAPI_ENDPOINT,
    TPEX_OPENAPI_URL,
    TRUST,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_SESSION_DATE = date(2026, 9, 8)
_CAPTURE_CLOCK_UTC = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
_AVAILABLE = datetime(2026, 9, 8, 20, 0, tzinfo=_TAIPEI)
_CUTOFF_BEFORE_AVAILABLE = _AVAILABLE - timedelta(seconds=1)


def _roc_date(value: date) -> str:
    return f"{value.year - 1911:03d}{value.month:02d}{value.day:02d}"


def _payload(report_date: date = _SESSION_DATE) -> bytes:
    row = {name: "0" for name in sorted(FIELDS)}
    row.update({
        "Date": _roc_date(report_date),
        "SecuritiesCompanyCode": "6488",
        "CompanyName": "Synthetic Co.",
        "Dealers -TotalSell": "10",
        "TotalDifference": "85",
        EX_FOREIGN[0]: "100",
        EX_FOREIGN[1]: "60",
        EX_FOREIGN[2]: "40",
        FOREIGN_DEALERS[0]: "20",
        FOREIGN_DEALERS[1]: "10",
        FOREIGN_DEALERS[2]: "10",
        FOREIGN_TOTAL[0]: "120",
        FOREIGN_TOTAL[1]: "70",
        FOREIGN_TOTAL[2]: "50",
        TRUST[0]: "30",
        TRUST[1]: "15",
        TRUST[2]: "15",
        DEALER[0]: "40",
        DEALER[1]: "20",
        DEALER[2]: "20",
    })
    return json.dumps([row], ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _transport(
    payload: bytes,
    calls: list[tuple[str, dict[str, str], int]],
):
    def fetch(url: str, params: Mapping[str, str], timeout_seconds: int) -> HttpResponse:
        calls.append((url, dict(params), timeout_seconds))
        return HttpResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            payload=payload,
            url=url,
            attempts=1,
            eof_observed=True,
            declared_content_length=len(payload),
            content_encoding="identity",
        )

    return fetch


def _capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: bytes | None = None,
    as_of_date: date = _SESSION_DATE,
    calls: list[tuple[str, dict[str, str], int]] | None = None,
    **overrides: Any,
) -> tuple[Path, dict[str, Any], list[tuple[str, dict[str, str], int]]]:
    monkeypatch.setattr(flow_service, "_utc_now", lambda: _CAPTURE_CLOCK_UTC)
    call_log = calls if calls is not None else []
    options: dict[str, Any] = {
        "sessions": 1,
        "max_lookback_days": 1,
        "max_attempts": 1,
        "rate_limit_seconds": 0,
        "capture_scope": "tpex_openapi_institutional",
    }
    options.update(overrides)
    readback = flow_service.capture_recent_flows(
        output_root=tmp_path / "capture",
        as_of_date=as_of_date,
        transport=_transport(_payload() if payload is None else payload, call_log),
        **options,
    )
    return Path(readback["manifest_path"]).parent, readback, call_log


def _seal(
    run_directory: Path,
    capture_sha256: str,
    *,
    times: tuple[datetime, ...] | None = None,
    check_cancel=None,
) -> InstitutionalDailySnapshotPin:
    clock_values = iter(times or (
        datetime(2026, 9, 8, 19, 10, tzinfo=_TAIPEI),
        datetime(2026, 9, 8, 19, 12, tzinfo=_TAIPEI),
        datetime(2026, 9, 8, 19, 14, tzinfo=_TAIPEI),
    ))
    return seal_institutional_capture(
        run_directory,
        capture_sha256,
        clock=lambda: next(clock_values),
        check_cancel=check_cancel,
    )


def _capture_files(run_directory: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(run_directory): path.read_bytes()
        for path in run_directory.rglob("*")
        if path.is_file() and "daily_snapshot" not in path.relative_to(run_directory).parts
    }


def _rewrite_json(path: Path, value: object) -> bytes:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(raw)
    return raw


def test_tpex_single_day_capture_seal_and_read_preserve_exact_shares_and_pins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, capture, calls = _capture(tmp_path, monkeypatch)
    original_files = _capture_files(run)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    source = manifest["sources"][0]
    raw_path = run / source["raw_artifacts"][0]["path"]
    metadata_path = run / source["raw_artifacts"][0]["metadata_path"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    original_raw = raw_path.read_bytes()

    assert calls == [(TPEX_OPENAPI_URL, {}, 30)]
    assert manifest["as_of_date"] == _SESSION_DATE.isoformat()
    assert manifest["discovered_sessions"] == [_SESSION_DATE.isoformat()]
    assert manifest["capture_scope"]["name"] == "tpex_openapi_institutional"
    assert manifest["capture_scope"]["markets"] == ["TPEx"]
    assert manifest["capture_scope"]["endpoint_ids"] == [TPEX_OPENAPI_ENDPOINT]
    assert metadata["quantity_unit"] == "shares"

    pin = _seal(run, capture["manifest_sha256"])
    snapshot_manifest = (pin.directory / "manifest.json").read_bytes()
    snapshot_receipt = (pin.directory / "receipt.json").read_bytes()
    assert pin.manifest_sha256 == sha256(snapshot_manifest).hexdigest()
    assert pin.receipt_sha256 == sha256(snapshot_receipt).hexdigest()

    with pytest.raises(InstitutionalDailySnapshotError, match="尚未到"):
        read_institutional_daily_snapshot(
            pin,
            stock_code="6488",
            decision_cutoff=_CUTOFF_BEFORE_AVAILABLE,
        )
    result = read_institutional_daily_snapshot(
        pin,
        stock_code="6488",
        decision_cutoff=_AVAILABLE,
    )

    assert result.market == "TPEx"
    assert len(result.rows) == 1
    row = result.rows[0]
    flow_names = (
        "foreign_investor_buy", "foreign_investor_sell", "foreign_investor_net",
        "investment_trust_buy", "investment_trust_sell", "investment_trust_net",
        "dealer_buy", "dealer_sell", "dealer_net",
    )
    assert tuple(getattr(row, name) for name in flow_names) == (120, 70, 50, 30, 15, 15, 40, 20, 20)
    assert all(type(getattr(row, name)) is int for name in flow_names)
    assert row.decision_date == _SESSION_DATE.isoformat()
    assert row.raw_sha256 == sha256(original_raw).hexdigest()
    assert row.official_timestamp is None
    assert result.available_hour == _AVAILABLE
    assert result.available_hour.tzinfo == _TAIPEI
    assert result.availability_basis == "successful_batch_completion_fallback"
    assert result.candidate_only is True
    assert result.source_use_accepted is False
    assert result.historical_pit_eligible is False
    assert _capture_files(run) == original_files
    assert raw_path.read_bytes() == original_raw


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("sessions", True), ("sessions", 1.0), ("sessions", 2),
        ("max_lookback_days", True), ("max_lookback_days", 1.0), ("max_lookback_days", 2),
        ("max_attempts", True), ("max_attempts", 1.0), ("max_attempts", 2),
    ],
)
def test_tpex_scope_requires_explicit_single_integer_attempt_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    argument: str,
    value: object,
) -> None:
    monkeypatch.setattr(flow_service, "_utc_now", lambda: _CAPTURE_CLOCK_UTC)
    calls: list[tuple[str, dict[str, str], int]] = []
    options: dict[str, Any] = {
        "sessions": 1,
        "max_lookback_days": 1,
        "max_attempts": 1,
        "rate_limit_seconds": 0,
        "capture_scope": "tpex_openapi_institutional",
    }
    options[argument] = value

    with pytest.raises(ValueError):
        flow_service.capture_recent_flows(
            output_root=tmp_path / "capture",
            as_of_date=_SESSION_DATE,
            transport=_transport(_payload(), calls),
            **options,
        )

    assert calls == []
    assert not (tmp_path / "capture").exists()


@pytest.mark.parametrize("case", ["report_date_mismatch", "empty_rows"])
def test_tpex_capture_rejects_date_mismatch_or_empty_day(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    payload = _payload(date(2026, 9, 7)) if case == "report_date_mismatch" else b"[]"
    calls: list[tuple[str, dict[str, str], int]] = []

    with pytest.raises(FlowCaptureError):
        _capture(tmp_path, monkeypatch, payload=payload, calls=calls)

    assert calls == [(TPEX_OPENAPI_URL, {}, 30)]
    run_directories = list((tmp_path / "capture" / "runs").glob("*"))
    assert len(run_directories) == 1
    assert not (run_directories[0] / "manifest.json").exists()
    assert list((run_directories[0] / "raw").rglob("*.json"))


@pytest.mark.parametrize("field", ["quantity_unit", "endpoint_id"])
def test_tpex_reader_rejects_changed_source_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    run, capture, _ = _capture(tmp_path, monkeypatch)
    pin = _seal(run, capture["manifest_sha256"])
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    metadata_path = run / manifest["sources"][0]["raw_artifacts"][0]["metadata_path"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field] = "lots" if field == "quantity_unit" else "tpex:3itrade"
    _rewrite_json(metadata_path, metadata)

    with pytest.raises(InstitutionalDailySnapshotError):
        read_institutional_daily_snapshot(
            pin,
            stock_code="6488",
            decision_cutoff=_AVAILABLE,
        )


def test_tpex_reader_rejects_raw_bytes_changed_after_seal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, capture, _ = _capture(tmp_path, monkeypatch)
    pin = _seal(run, capture["manifest_sha256"])
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    raw_path = run / manifest["sources"][0]["raw_artifacts"][0]["path"]
    raw_path.write_bytes(raw_path.read_bytes() + b" ")

    with pytest.raises(InstitutionalDailySnapshotError):
        read_institutional_daily_snapshot(
            pin,
            stock_code="6488",
            decision_cutoff=_AVAILABLE,
        )


def test_tpex_seal_rejects_rebound_wrong_capture_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, _capture_readback, _ = _capture(tmp_path, monkeypatch)
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["capture_scope"]["markets"] = ["TWSE"]
    rebound_sha = sha256(_rewrite_json(manifest_path, manifest)).hexdigest()

    with pytest.raises(InstitutionalDailySnapshotError):
        _seal(run, rebound_sha)
    assert not (run / "daily_snapshot").exists()


@pytest.mark.parametrize("barrier", [".pending.json", "failure.json"])
def test_tpex_reader_rejects_pending_or_failed_batch_barrier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    barrier: str,
) -> None:
    run, capture, _ = _capture(tmp_path, monkeypatch)
    pin = _seal(run, capture["manifest_sha256"])
    (pin.directory / barrier).write_text("{}", encoding="utf-8")

    with pytest.raises(InstitutionalDailySnapshotError, match="pending|失敗"):
        read_institutional_daily_snapshot(
            pin,
            stock_code="6488",
            decision_cutoff=_AVAILABLE,
        )


def test_legacy_twse_ports_reject_tpex_capture_and_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, capture, _ = _capture(tmp_path, monkeypatch)

    with pytest.raises(InstitutionalDailySnapshotError):
        seal_twse_institutional_capture(
            run,
            capture["manifest_sha256"],
            clock=lambda: datetime(2026, 9, 8, 19, 10, tzinfo=_TAIPEI),
        )
    assert not (run / "daily_snapshot").exists()

    pin = _seal(run, capture["manifest_sha256"])
    with pytest.raises(InstitutionalDailySnapshotError):
        read_twse_institutional_daily_snapshot(
            pin,
            stock_code="6488",
            decision_cutoff=_AVAILABLE,
        )


@pytest.mark.parametrize(("operation", "trigger"), [("seal", 4), ("read", 3)])
def test_cancel_during_same_capture_reverification_is_observed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    trigger: int,
) -> None:
    run, capture, _ = _capture(tmp_path, monkeypatch)
    pin = _seal(run, capture["manifest_sha256"]) if operation == "read" else None
    original_read = daily._read_exact_file
    reads, cancelled = 0, False

    def read_then_cancel(path: Path, **kwargs: Any):
        nonlocal reads, cancelled
        result = original_read(path, **kwargs)
        if path.name == "readback.json":
            reads += 1
            if reads == trigger:
                cancelled = True
        return result

    monkeypatch.setattr(daily, "_read_exact_file", read_then_cancel)
    with pytest.raises(InstitutionalDailySnapshotError, match="取消"):
        if operation == "read":
            assert pin is not None
            read_institutional_daily_snapshot(
                pin,
                stock_code="6488",
                decision_cutoff=_AVAILABLE,
                check_cancel=lambda: cancelled,
            )
        else:
            _seal(
                run,
                capture["manifest_sha256"],
                check_cancel=lambda: cancelled,
            )
    if operation == "seal":
        assert (run / "daily_snapshot" / ".pending.json").exists()
        assert (run / "daily_snapshot" / "failure.json").exists()
