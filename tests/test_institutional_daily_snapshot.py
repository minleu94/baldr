from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pytest

import data_module.institutional_credit_flows_service as flow_service
from app_module.institutional_daily_snapshot import (
    InstitutionalDailySnapshotError,
    InstitutionalDailySnapshotPin,
    read_twse_institutional_daily_snapshot,
    seal_twse_institutional_capture,
)
from data_module.institutional_credit_flows_service import (
    FlowCaptureError,
    HttpResponse,
)
from test_institutional_credit_flows_service import (
    _fake_transport,
    _twse_institutional_payload,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_FIXED_CAPTURE_CLOCK = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
_CUTOFF = datetime(2026, 9, 8, 20, 0, tzinfo=_TAIPEI)


@pytest.mark.parametrize("column", [11, 18])
def test_capture_rejects_official_totals_that_disagree_with_components(tmp_path, monkeypatch, column):
    original = _fake_transport

    def inconsistent(url, params, timeout):
        response = original(url, params, timeout)
        decoded = json.loads(response.payload)
        decoded["data"][0][column] = "999"
        return replace(response, payload=json.dumps(decoded, ensure_ascii=False).encode())

    monkeypatch.setitem(globals(), "_fake_transport", inconsistent)
    with pytest.raises(FlowCaptureError, match="沒有可接受資料列"):
        _capture_twse(tmp_path, monkeypatch)
    # 失敗仍留下真正收到的原件，不將本機算出的合計覆蓋官方值。
    saved = list((tmp_path / "flows").glob("runs/*/raw/*/twse_T86.json"))
    assert saved and json.loads(saved[0].read_bytes())["data"][0][column] == "999"
    assert not list((tmp_path / "flows").glob("runs/*/manifest.json"))


@pytest.mark.parametrize("unit", ["單位：張", "單位：千股", None])
def test_capture_rejects_conflicting_official_quantity_unit(tmp_path, monkeypatch, unit):
    original = _fake_transport

    def wrong_unit(url, params, timeout):
        response = original(url, params, timeout)
        decoded = json.loads(response.payload)
        decoded["hints"] = unit
        return replace(response, payload=json.dumps(decoded, ensure_ascii=False).encode())

    monkeypatch.setitem(globals(), "_fake_transport", wrong_unit)
    with pytest.raises(FlowCaptureError, match="原件股數單位不符"):
        _capture_twse(tmp_path, monkeypatch)


@pytest.mark.parametrize("missing", ["unit", "dealer_total", "three_total"])
def test_daily_seal_requires_raw_unit_and_declared_total_evidence(tmp_path, monkeypatch, missing):
    original = _fake_transport

    def old_evidence(url, params, timeout):
        response = original(url, params, timeout)
        decoded = json.loads(response.payload)
        if missing == "unit":
            decoded.pop("hints")
        else:
            column = 11 if missing == "dealer_total" else 18
            decoded["fields"].pop(column)
            for row in decoded["data"]:
                row.pop(column)
        return replace(response, payload=json.dumps(decoded, ensure_ascii=False).encode())

    monkeypatch.setitem(globals(), "_fake_transport", old_evidence)
    run, captured = _capture_twse(tmp_path, monkeypatch)
    with pytest.raises(InstitutionalDailySnapshotError, match="股數單位或獨立宣告合計"):
        _seal(run, captured["manifest_sha256"])
    assert not (run / "daily_snapshot").exists()


def test_reader_rejects_pending_barrier_after_valid_publication(tmp_path, monkeypatch):
    run, captured = _capture_twse(tmp_path, monkeypatch)
    pin = _seal(run, captured["manifest_sha256"])
    (pin.directory / ".pending.json").write_text("{}", encoding="utf8")
    with pytest.raises(InstitutionalDailySnapshotError, match="pending"):
        read_twse_institutional_daily_snapshot(pin, stock_code="2330", decision_cutoff=_CUTOFF)


def test_reader_finish_rechecks_bytes_even_when_mtime_is_restored(tmp_path, monkeypatch):
    run, captured = _capture_twse(tmp_path, monkeypatch)
    pin = _seal(run, captured["manifest_sha256"])
    raw = run / "raw" / "2026-09-08" / "twse_T86.json"
    before = raw.stat()
    calls = 0

    def mutate_at_finish():
        nonlocal calls
        calls += 1
        if calls == 7:
            original = raw.read_bytes()
            altered = original.replace(b'"100"', b'"101"', 1)
            assert altered != original and len(altered) == len(original)
            raw.write_bytes(altered)
            os.utime(raw, ns=(before.st_atime_ns, before.st_mtime_ns))
        return False

    with pytest.raises(InstitutionalDailySnapshotError, match="讀取期間改變"):
        read_twse_institutional_daily_snapshot(pin, stock_code="2330", decision_cutoff=_CUTOFF,
                                             check_cancel=mutate_at_finish)


def test_exact_hour_completion_keeps_next_hour_publication_guard(tmp_path, monkeypatch):
    run, captured = _capture_twse(tmp_path, monkeypatch)
    boundary = datetime(2026, 9, 8, 20, 0, tzinfo=_TAIPEI)
    pin = _seal(run, captured["manifest_sha256"], times=(boundary, boundary, boundary.replace(second=1)))
    cutoff = boundary.replace(hour=21)
    result = read_twse_institutional_daily_snapshot(pin, stock_code="2330", decision_cutoff=cutoff)
    assert result.available_hour == cutoff
    with pytest.raises(InstitutionalDailySnapshotError):
        read_twse_institutional_daily_snapshot(pin, stock_code="2330", decision_cutoff=boundary)


def test_share_counts_above_binary_float_precision_remain_exact(tmp_path, monkeypatch):
    original_transport = _fake_transport
    shares = 9007199254740993

    def large_counts(url, params, timeout):
        response = original_transport(url, params, timeout)
        decoded = json.loads(response.payload)
        row = decoded["data"][0]
        row[2], row[4], row[18] = str(shares - 10), str(shares - 60), str(shares - 40)
        return replace(response, payload=json.dumps(decoded, ensure_ascii=False).encode("utf8"))

    monkeypatch.setitem(globals(), "_fake_transport", large_counts)
    run, captured = _capture_twse(tmp_path, monkeypatch)
    pin = _seal(run, captured["manifest_sha256"])
    result = read_twse_institutional_daily_snapshot(pin, stock_code="2330", decision_cutoff=_CUTOFF)
    assert result.rows[0].foreign_investor_buy == shares
    assert result.rows[0].foreign_investor_net == shares - 55


def _capture_twse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    sessions: int = 1,
    omit_publication_time: bool = False,
    eof_observed: bool | None = True,
    content_length_delta: int = 0,
) -> tuple[Path, dict[str, Any]]:
    """用既有真實欄位 fixture 捕捉有界 body 證據，不連外。"""

    monkeypatch.setattr(flow_service, "_utc_now", lambda: _FIXED_CAPTURE_CLOCK)

    def transport(
        url: str, params: Mapping[str, str], timeout_seconds: int
    ) -> HttpResponse:
        response = _fake_transport(url, dict(params), timeout_seconds)
        payload = response.payload
        if omit_publication_time and "fund/T86" in url:
            decoded = json.loads(payload.decode("utf-8"))
            decoded.pop("publicationTime", None)
            payload = json.dumps(decoded, ensure_ascii=False).encode("utf-8")
        return replace(
            response,
            payload=payload,
            eof_observed=eof_observed,
            declared_content_length=len(payload) + content_length_delta,
        )

    readback = flow_service.capture_recent_flows(
        output_root=tmp_path / "flows",
        as_of_date=date(2026, 9, 8),
        sessions=sessions,
        max_lookback_days=max(2, sessions),
        transport=transport,
        rate_limit_seconds=0,
        capture_scope="twse_institutional",
    )
    return Path(readback["manifest_path"]).parent, readback


def _seal(
    run_directory: Path,
    capture_sha256: str,
    *,
    times: tuple[datetime, ...] | None = None,
) -> InstitutionalDailySnapshotPin:
    clock_values = iter(
        times
        or (
            datetime(2026, 9, 8, 19, 45, tzinfo=_TAIPEI),
            datetime(2026, 9, 8, 19, 46, tzinfo=_TAIPEI),
            datetime(2026, 9, 8, 19, 47, tzinfo=_TAIPEI),
        )
    )
    return seal_twse_institutional_capture(
        run_directory,
        capture_sha256,
        clock=lambda: next(clock_values),
    )


def _capture_file_bytes(run_directory: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(run_directory): path.read_bytes()
        for path in run_directory.rglob("*")
        if path.is_file() and "daily_snapshot" not in path.relative_to(run_directory).parts
    }


def _rewrite_json(path: Path, value: Any) -> bytes:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(raw)
    return raw


def test_sealed_twse_capture_reads_exact_rows_and_keeps_original_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_directory, capture = _capture_twse(tmp_path, monkeypatch, sessions=1)
    original_files = _capture_file_bytes(run_directory)
    raw_path = run_directory / "raw" / "2026-09-08" / "twse_T86.json"
    original_raw = raw_path.read_bytes()
    capture_sha = capture["manifest_sha256"]

    pin = _seal(run_directory, capture_sha)
    result = read_twse_institutional_daily_snapshot(
        pin, stock_code="2330", decision_cutoff=_CUTOFF
    )

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.stock_code == "2330"
    assert row.decision_date == "2026-09-08"
    assert tuple(
        getattr(row, name)
        for name in (
            "foreign_investor_buy",
            "foreign_investor_sell",
            "foreign_investor_net",
            "investment_trust_buy",
            "investment_trust_sell",
            "investment_trust_net",
            "dealer_buy",
            "dealer_sell",
            "dealer_net",
        )
    ) == (110, 55, 55, 30, 20, 10, 10, 5, 5)
    assert all(
        type(getattr(row, name)) is int
        for name in (
            "foreign_investor_buy",
            "foreign_investor_sell",
            "foreign_investor_net",
            "investment_trust_buy",
            "investment_trust_sell",
            "investment_trust_net",
            "dealer_buy",
            "dealer_sell",
            "dealer_net",
        )
    )
    assert row.official_timestamp_original_text == "2026-09-08T17:30:00+08:00"
    assert row.official_timestamp == "2026-09-08T17:30:00+08:00"
    assert row.raw_sha256 == sha256(original_raw).hexdigest()
    assert result.total_records == 1
    assert result.first_persisted_at == datetime(2026, 9, 8, 19, 45, tzinfo=_TAIPEI)
    assert result.successful_batch_completed_at == datetime(
        2026, 9, 8, 19, 46, tzinfo=_TAIPEI
    )
    assert result.available_hour == _CUTOFF
    assert result.availability_basis == "official_timestamp_and_successful_batch_completion"
    assert result.candidate_only is True
    assert result.source_use_accepted is False
    assert result.historical_pit_eligible is False
    assert _capture_file_bytes(run_directory) == original_files


def test_two_session_parent_and_missing_stock_are_not_zero_filled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_directory, capture = _capture_twse(tmp_path, monkeypatch, sessions=2)
    pin = _seal(run_directory, capture["manifest_sha256"])

    hit = read_twse_institutional_daily_snapshot(
        pin, stock_code="2330", decision_cutoff=_CUTOFF
    )
    miss = read_twse_institutional_daily_snapshot(
        pin, stock_code="2317", decision_cutoff=_CUTOFF
    )

    assert tuple(row.decision_date for row in hit.rows) == (
        "2026-09-07",
        "2026-09-08",
    )
    assert hit.total_records == 2
    assert miss.rows == ()
    assert miss.total_records == 2


def test_missing_official_publication_time_uses_batch_completion_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_directory, capture = _capture_twse(
        tmp_path, monkeypatch, omit_publication_time=True
    )
    pin = _seal(run_directory, capture["manifest_sha256"])

    result = read_twse_institutional_daily_snapshot(
        pin, stock_code="2330", decision_cutoff=_CUTOFF
    )

    assert result.rows[0].official_timestamp_original_text == ""
    assert result.rows[0].official_timestamp is None
    assert result.available_hour == _CUTOFF
    assert result.availability_basis == "successful_batch_completion_fallback"


@pytest.mark.parametrize(
    "cutoff",
    [
        datetime(2026, 9, 8, 19, 59, 59, tzinfo=_TAIPEI),
        datetime(2026, 9, 8, 20, 0),
    ],
    ids=("before_available_hour", "naive_cutoff"),
)
def test_reader_rejects_early_or_naive_cutoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cutoff: datetime
) -> None:
    run_directory, capture = _capture_twse(tmp_path, monkeypatch)
    pin = _seal(run_directory, capture["manifest_sha256"])

    with pytest.raises(InstitutionalDailySnapshotError):
        read_twse_institutional_daily_snapshot(
            pin, stock_code="2330", decision_cutoff=cutoff
        )


@pytest.mark.parametrize(
    ("eof_observed", "content_length_delta"),
    [(False, 0), (True, 1)],
    ids=("missing_eof", "wrong_content_length"),
)
def test_seal_rejects_incomplete_http_body_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    eof_observed: bool,
    content_length_delta: int,
) -> None:
    run_directory, capture = _capture_twse(
        tmp_path,
        monkeypatch,
        eof_observed=eof_observed,
        content_length_delta=content_length_delta,
    )

    with pytest.raises(InstitutionalDailySnapshotError):
        _seal(run_directory, capture["manifest_sha256"])
    assert not (run_directory / "daily_snapshot").exists()


@pytest.mark.parametrize("field", ["quantity_unit", "source_version"])
def test_seal_rejects_wrong_source_unit_or_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    run_directory, capture = _capture_twse(tmp_path, monkeypatch)
    metadata_path = run_directory / "raw" / "2026-09-08" / "twse_T86.json.metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field] = "lots" if field == "quantity_unit" else "other-T86.v9"
    _rewrite_json(metadata_path, metadata)

    with pytest.raises(InstitutionalDailySnapshotError):
        _seal(run_directory, capture["manifest_sha256"])
    assert not (run_directory / "daily_snapshot").exists()


def test_seal_rejects_forged_candidate_even_when_its_hashes_are_rebound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_directory, capture = _capture_twse(tmp_path, monkeypatch)
    manifest_path = run_directory / "manifest.json"
    readback_path = run_directory / "readback.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest["sources"][0]
    candidate_path = run_directory / source["candidate_rows_path"]
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate[0]["values"]["foreign_investor_net"] += 1
    candidate_bytes = _rewrite_json(candidate_path, candidate)
    source["candidate_rows_sha256"] = sha256(candidate_bytes).hexdigest()
    manifest_bytes = _rewrite_json(manifest_path, manifest)
    manifest_sha = sha256(manifest_bytes).hexdigest()
    readback = json.loads(readback_path.read_text(encoding="utf-8"))
    readback["manifest_sha256"] = manifest_sha
    _rewrite_json(readback_path, readback)

    assert manifest_sha != capture["manifest_sha256"]
    with pytest.raises(InstitutionalDailySnapshotError, match="候選全文不一致"):
        _seal(run_directory, manifest_sha)
    assert not (run_directory / "daily_snapshot").exists()


def test_wrong_capture_and_public_receipt_pins_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_directory, capture = _capture_twse(tmp_path, monkeypatch)
    with pytest.raises(InstitutionalDailySnapshotError):
        _seal(run_directory, "f" * 64)
    assert not (run_directory / "daily_snapshot").exists()

    pin = _seal(run_directory, capture["manifest_sha256"])
    wrong_pin = replace(pin, receipt_sha256="e" * 64)
    with pytest.raises(InstitutionalDailySnapshotError):
        read_twse_institutional_daily_snapshot(
            wrong_pin, stock_code="2330", decision_cutoff=_CUTOFF
        )


def test_cross_hour_seal_keeps_pending_and_failure_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_directory, capture = _capture_twse(tmp_path, monkeypatch)
    with pytest.raises(InstitutionalDailySnapshotError, match="跨小時"):
        _seal(
            run_directory,
            capture["manifest_sha256"],
            times=(
                datetime(2026, 9, 8, 19, 59, tzinfo=_TAIPEI),
                datetime(2026, 9, 8, 20, 0, tzinfo=_TAIPEI),
            ),
        )

    target = run_directory / "daily_snapshot"
    assert (target / ".pending.json").is_file()
    assert (target / "failure.json").is_file()
    assert not (target / "receipt.json").exists()


def test_daily_snapshot_directory_collision_does_not_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_directory, capture = _capture_twse(tmp_path, monkeypatch)
    pin = _seal(run_directory, capture["manifest_sha256"])
    target = pin.directory
    before = {
        path.name: path.read_bytes()
        for path in target.iterdir()
        if path.is_file()
    }

    with pytest.raises(FileExistsError):
        _seal(run_directory, capture["manifest_sha256"])

    assert {
        path.name: path.read_bytes()
        for path in target.iterdir()
        if path.is_file()
    } == before


class _FakeRawResponse:
    def __init__(self, payload: bytes) -> None:
        self._stream = BytesIO(payload)
        self.read_sizes: list[int] = []
        self.closed = False

    def read(self, amount: int, *, decode_content: bool) -> bytes:
        assert decode_content is False
        self.read_sizes.append(amount)
        return self._stream.read(amount)

    def close(self) -> None:
        self.closed = True
        self._stream.close()


class _FakeRequestsResponse:
    def __init__(self, payload: bytes) -> None:
        self.status_code = 200
        self.url = "https://www.twse.com.tw/fund/T86"
        self.headers = {
            "Content-Length": str(len(payload)),
            "Content-Encoding": "identity",
            "content-type": "application/json",
        }
        self.raw = _FakeRawResponse(payload)
        self.closed = False

    def __enter__(self) -> _FakeRequestsResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        self.closed = True
        self.raw.close()


def test_default_transport_uses_bounded_identity_stream_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _twse_institutional_payload("2026-09-08")
    response = _FakeRequestsResponse(payload)
    received: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> _FakeRequestsResponse:
        received.update(url=url, **kwargs)
        return response

    monkeypatch.setattr(flow_service.requests, "get", fake_get)
    result = flow_service._default_transport(
        "https://www.twse.com.tw/fund/T86", {"date": "20260908"}, 10
    )

    assert received["stream"] is True
    assert received["headers"]["Accept-Encoding"] == "identity"
    assert received["timeout"] == 10
    assert result.payload == payload
    assert result.eof_observed is True
    assert result.declared_content_length == len(payload)
    assert response.raw.read_sizes and max(response.raw.read_sizes) <= 65536
    assert response.closed is True
    assert response.raw.closed is True


def test_default_transport_rejects_over_cap_body_and_still_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"x" * (flow_service.MAX_RESPONSE_BYTES + 1)
    response = _FakeRequestsResponse(payload)

    def fake_get(_url: str, **_kwargs: Any) -> _FakeRequestsResponse:
        return response

    monkeypatch.setattr(flow_service.requests, "get", fake_get)

    with pytest.raises(FlowCaptureError, match="bounded cap"):
        flow_service._default_transport(
            "https://www.twse.com.tw/fund/T86", {"date": "20260908"}, 10
        )

    assert response.raw.read_sizes
    assert max(response.raw.read_sizes) <= 65536
    assert response.closed is True
    assert response.raw.closed is True


def test_compressed_legacy_transport_keeps_bounded_decoding_and_encoding_evidence(monkeypatch):
    payload = _twse_institutional_payload("2026-09-08")
    response = _FakeRequestsResponse(b"compressed-wire-body")
    response.headers["Content-Encoding"] = "gzip"
    response.iter_content = lambda chunk_size: iter((payload[:100], payload[100:]))
    monkeypatch.setattr(flow_service.requests, "get", lambda *args, **kwargs: response)
    result = flow_service._default_transport("https://www.twse.com.tw/fund/T86", {"date": "20260908"}, 10)
    assert result.payload == payload and result.content_encoding == "gzip"
    assert not response.raw.read_sizes and response.closed


@pytest.mark.parametrize("operation,trigger", [("seal", 4), ("read", 3)])
def test_cancel_arriving_during_final_file_is_observed(tmp_path, monkeypatch, operation, trigger):
    import app_module.institutional_daily_snapshot as daily
    run, capture = _capture_twse(tmp_path, monkeypatch)
    pin = _seal(run, capture["manifest_sha256"]) if operation == "read" else None
    original_read = daily._read_exact_file
    count, cancelled = 0, False

    def read_then_cancel(path, **kwargs):
        nonlocal count, cancelled
        result = original_read(path, **kwargs)
        if path.name == "readback.json":
            count += 1
            if count == trigger:
                cancelled = True
        return result

    monkeypatch.setattr(daily, "_read_exact_file", read_then_cancel)
    with pytest.raises(InstitutionalDailySnapshotError, match="取消"):
        if operation == "read":
            daily.read_twse_institutional_daily_snapshot(pin, stock_code="2330", decision_cutoff=_CUTOFF,
                                                       check_cancel=lambda: cancelled)
        else:
            values = iter((datetime(2026, 9, 8, 19, 45, tzinfo=_TAIPEI), datetime(2026, 9, 8, 19, 46, tzinfo=_TAIPEI)))
            daily.seal_twse_institutional_capture(run, capture["manifest_sha256"], clock=lambda: next(values),
                                                 check_cancel=lambda: cancelled)
    if operation == "seal":
        assert (run / "daily_snapshot" / ".pending.json").exists()


def test_final_reverification_cannot_cross_publication_hour(tmp_path, monkeypatch):
    import app_module.institutional_daily_snapshot as daily
    run, capture = _capture_twse(tmp_path, monkeypatch)
    original_read = daily._read_exact_file
    count, crossed = 0, False

    def slow_final_read(path, **kwargs):
        nonlocal count, crossed
        result = original_read(path, **kwargs)
        if path.name == "readback.json":
            count += 1
            crossed = count >= 4
        return result

    values = iter((datetime(2026, 9, 8, 19, 45, tzinfo=_TAIPEI), datetime(2026, 9, 8, 19, 46, tzinfo=_TAIPEI)))
    def clock():
        return _CUTOFF.replace(second=1) if crossed else next(values)
    monkeypatch.setattr(daily, "_read_exact_file", slow_final_read)
    with pytest.raises(InstitutionalDailySnapshotError, match="可用小時之前"):
        daily.seal_twse_institutional_capture(run, capture["manifest_sha256"], clock=clock)
    assert crossed and (run / "daily_snapshot" / ".pending.json").exists()
