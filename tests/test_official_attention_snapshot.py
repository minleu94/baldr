from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime as _datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

import pytest

from app_module import official_attention_snapshot as snapshot


_QUERY_DATE = date(2026, 10, 15)
_TAIPEI = ZoneInfo("Asia/Taipei")
_STARTED = _datetime(2026, 10, 16, 5, 0, 0, tzinfo=_TAIPEI)
_BODY_OBSERVED = _datetime(2026, 10, 16, 5, 0, 8, tzinfo=_TAIPEI)
_ENDED = _datetime(2026, 10, 16, 5, 0, 10, tzinfo=_TAIPEI)
_RAW_FIXTURE = Path(__file__).parent / "fixtures" / "official_attention" / "twse_20261015.json"


class _NextDayDateTime(_datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 17, 12, 0, tzinfo=tz or _TAIPEI)

    @classmethod
    def fromisoformat(cls, value: str):
        parsed = _datetime.fromisoformat(value)
        return cls(parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute, parsed.second,
                   parsed.microsecond, tzinfo=parsed.tzinfo, fold=parsed.fold)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    receipt_changes: dict[str, object] | None = None,
) -> dict[str, object]:
    raw = _RAW_FIXTURE.read_bytes()
    attempt = tmp_path / "attempt"
    docs_dir = tmp_path / "documents"
    attempt.mkdir()
    docs_dir.mkdir()
    document_bytes = {
        "notice.html": b"synthetic notice document pin\n",
        "web-report.js": b"synthetic report document pin\n",
        "main.js": b"synthetic config document pin\n",
    }
    document_pins = {name: _hash(value) for name, value in document_bytes.items()}
    monkeypatch.setattr(snapshot, "ATTENTION_DOCUMENT_PINS", document_pins)
    documents: dict[str, Path] = {}
    for name, value in document_bytes.items():
        path = docs_dir / name
        path.write_bytes(value)
        documents[name] = path

    (attempt / "response.raw").write_bytes(raw)
    sidecars = {
        "headers.json": _json_bytes({"content-type": "application/json"}),
        "worker_input.json": _json_bytes({"request": "synthetic"}),
        "worker_job.json": _json_bytes({"job": "synthetic"}),
        "cookies.before_request.json": _json_bytes({"cookies": []}),
        "cookies.after_headers.json": _json_bytes({"cookies": []}),
    }
    for name, value in sidecars.items():
        (attempt / name).write_bytes(value)
    result = {
        "body_eof": True,
        "failure_code": None,
        "raw_sha256": _hash(raw),
        "received_body_bytes": len(raw),
        "body_completed_observed_at": _BODY_OBSERVED.isoformat(),
    }
    (attempt / "worker_result.json").write_bytes(_json_bytes(result))
    receipt: dict[str, object] = {
        "schema_version": 1,
        "method": "GET",
        "official_url": snapshot.attention_query_url(_QUERY_DATE),
        "response_url": snapshot.attention_query_url(_QUERY_DATE),
        "response_status": 200,
        "status": "transport_complete_candidate",
        "candidate_complete": True,
        "response_body_complete": True,
        "response_body_eof": True,
        "deadline_exceeded": False,
        "failure_code": None,
        "worker_exit_code": 0,
        "worker_wait_reaped": True,
        "worker_process_handle_closed": True,
        "worker_pid_alive_after_reap": False,
        "worker_terminated_by_controller": False,
        "sidecar_error_code": None,
        "worker_root_named_job_membership_verified": True,
        "worker_root_named_job_pid_absent_after_reap": True,
        "raw_file": "response.raw",
        "raw_bytes": len(raw),
        "raw_sha256": _hash(raw),
        "body_completion_evidence": f"eof:response.raw:{_hash(raw)}",
        "content_encoding_original_values": ["identity"],
        "content_length_original_values": [str(len(raw))],
        "headers_sha256": _hash(sidecars["headers.json"]),
        "request_input_sha256": _hash(sidecars["worker_input.json"]),
        "worker_job_sha256": _hash(sidecars["worker_job.json"]),
        "cookie_input_sha256": _hash(sidecars["cookies.before_request.json"]),
        "cookie_output_sha256": _hash(sidecars["cookies.after_headers.json"]),
        "started_at": _STARTED.isoformat(),
        "ended_at": _ENDED.isoformat(),
    }
    if receipt_changes:
        receipt.update(receipt_changes)
    receipt_bytes = _json_bytes(receipt)
    (attempt / "receipt.json").write_bytes(receipt_bytes)
    return {
        "attempt": attempt,
        "documents": documents,
        "output": tmp_path / "sealed",
        "raw": raw,
        "receipt_sha256": _hash(receipt_bytes),
    }


def _seal(capture: dict[str, object]):
    return snapshot.seal_official_attention_snapshot(
        capture["attempt"],
        capture["receipt_sha256"],
        query_date=_QUERY_DATE,
        documents=capture["documents"],
        output_directory=capture["output"],
        clock=lambda: _ENDED + timedelta(minutes=1),
    )


def _read_next_day(monkeypatch: pytest.MonkeyPatch, pin, *, stock_code: str = "*"):
    monkeypatch.setattr(snapshot, "datetime", _NextDayDateTime)
    cutoff = _NextDayDateTime(2026, 10, 17, 12, 0, tzinfo=_TAIPEI)
    return snapshot.read_official_attention_snapshot(pin, stock_code=stock_code, decision_cutoff=cutoff)


def test_seal_is_self_contained_and_returns_the_complete_dated_report(tmp_path, monkeypatch):
    capture = _capture(tmp_path, monkeypatch)
    pin = _seal(capture)
    attempt_path = Path(capture["attempt"]).resolve()
    documents_path = (tmp_path / "documents").resolve()
    temp_root = tmp_path.resolve()
    assert attempt_path.is_relative_to(temp_root) and attempt_path.name == "attempt"
    assert documents_path.is_relative_to(temp_root) and documents_path.name == "documents"
    assert attempt_path.is_dir() and documents_path.is_dir()
    shutil.rmtree(attempt_path)
    shutil.rmtree(documents_path)

    result = _read_next_day(monkeypatch, pin)

    assert result.query_date == "2026-10-15"
    assert result.total_securities == 18
    assert len(result.rows) == 18
    warrant = next(row for row in result.rows if row.stock_code == "053040")
    assert warrant.stock_name == "可寧衛富邦5C購01"
    red_text = next(row for row in result.rows if row.stock_code == "2308")
    assert "<font color='#FF0000'>" in red_text.reason_original_text
    assert "﹝第十一款﹞" in red_text.reason_text
    assert "<font" not in red_text.reason_text
    assert result.source_use_accepted is False
    assert result.historical_pit_eligible is False


def test_existing_snapshot_version_cannot_be_overwritten(tmp_path, monkeypatch):
    capture = _capture(tmp_path, monkeypatch)
    pin = _seal(capture)
    before = {path.relative_to(pin.directory): path.read_bytes() for path in pin.directory.rglob("*") if path.is_file()}

    with pytest.raises(FileExistsError):
        _seal(capture)

    after = {path.relative_to(pin.directory): path.read_bytes() for path in pin.directory.rglob("*") if path.is_file()}
    assert after == before


def test_reader_rejects_cutoff_before_the_published_available_hour(tmp_path, monkeypatch):
    capture = _capture(tmp_path, monkeypatch)
    pin = _seal(capture)
    receipt = json.loads((pin.directory / "receipt.json").read_text(encoding="utf-8"))
    available = _NextDayDateTime.fromisoformat(receipt["available_hour"])
    before_available = available - timedelta(minutes=1)
    cutoff = _NextDayDateTime(before_available.year, before_available.month, before_available.day,
                              before_available.hour, before_available.minute, tzinfo=before_available.tzinfo)
    monkeypatch.setattr(snapshot, "datetime", _NextDayDateTime)

    with pytest.raises(snapshot.OfficialAttentionSnapshotError, match="尚未到注意公告成功批次"):
        snapshot.read_official_attention_snapshot(pin, stock_code="2308", decision_cutoff=cutoff)


def test_reader_rejects_a_real_future_cutoff(tmp_path, monkeypatch):
    capture = _capture(tmp_path, monkeypatch)
    pin = _seal(capture)
    future = _datetime.now(_TAIPEI) + timedelta(days=1)

    with pytest.raises(snapshot.OfficialAttentionSnapshotError, match="不得以未來時鐘"):
        snapshot.read_official_attention_snapshot(pin, stock_code="2308", decision_cutoff=future)


@pytest.mark.parametrize("pin_field", ["manifest_sha256", "receipt_sha256"])
def test_reader_rejects_each_wrong_external_snapshot_hash(tmp_path, monkeypatch, pin_field):
    capture = _capture(tmp_path, monkeypatch)
    pin = _seal(capture)
    bad_pin = replace(pin, **{pin_field: "0" * 64})

    with pytest.raises(snapshot.OfficialAttentionSnapshotError):
        _read_next_day(monkeypatch, bad_pin)


@pytest.mark.parametrize("barrier", [".pending.json", "failure.json"])
def test_reader_refuses_pending_or_failed_snapshot_versions(tmp_path, monkeypatch, barrier):
    capture = _capture(tmp_path, monkeypatch)
    pin = _seal(capture)
    (pin.directory / barrier).write_text("{}", encoding="utf-8")

    with pytest.raises(snapshot.OfficialAttentionSnapshotError, match="pending或已失敗"):
        _read_next_day(monkeypatch, pin)


def test_reader_rejects_raw_changes_before_reading(tmp_path, monkeypatch):
    capture = _capture(tmp_path, monkeypatch)
    pin = _seal(capture)
    raw_path = pin.directory / "response.raw"
    raw_path.write_bytes(b"x" * len(capture["raw"]))

    with pytest.raises(snapshot.OfficialAttentionSnapshotError):
        _read_next_day(monkeypatch, pin)


@pytest.mark.parametrize(
    "receipt_change",
    [
        {"response_body_eof": False},
        {"deadline_exceeded": True},
        {"raw_sha256": "0" * 64},
    ],
    ids=["missing-eof", "deadline", "wrong-raw-hash"],
)
def test_seal_rejects_incomplete_or_inconsistent_http_transport(tmp_path, monkeypatch, receipt_change):
    capture = _capture(tmp_path, monkeypatch, receipt_changes=receipt_change)

    with pytest.raises(snapshot.OfficialAttentionSnapshotError):
        _seal(capture)


def test_seal_cancellation_leaves_a_read_blocking_pending_failure_barrier(tmp_path, monkeypatch):
    capture = _capture(tmp_path, monkeypatch)

    def cancel_after_first_saved_artifact() -> bool:
        return (Path(capture["output"]) / ".pending.json").exists() and (
            Path(capture["output"]) / "response.raw"
        ).exists()

    with pytest.raises(snapshot.OfficialAttentionSnapshotError, match="已取消"):
        snapshot.seal_official_attention_snapshot(
            capture["attempt"],
            capture["receipt_sha256"],
            query_date=_QUERY_DATE,
            documents=capture["documents"],
            output_directory=capture["output"],
            clock=lambda: _ENDED + timedelta(minutes=1),
            check_cancel=cancel_after_first_saved_artifact,
        )

    assert (capture["output"] / ".pending.json").exists()
    assert (capture["output"] / "failure.json").exists()
    dummy_pin = snapshot.OfficialAttentionSnapshotPin(capture["output"], "0" * 64, "0" * 64)
    monkeypatch.setattr(snapshot, "datetime", _NextDayDateTime)
    cutoff = _NextDayDateTime(2026, 10, 17, 12, 0, tzinfo=_TAIPEI)
    with pytest.raises(snapshot.OfficialAttentionSnapshotError, match="pending或已失敗"):
        snapshot.read_official_attention_snapshot(dummy_pin, stock_code="*", decision_cutoff=cutoff)


def test_reader_cancellation_is_propagated(tmp_path, monkeypatch):
    capture = _capture(tmp_path, monkeypatch)
    pin = _seal(capture)
    monkeypatch.setattr(snapshot, "datetime", _NextDayDateTime)
    cutoff = _NextDayDateTime(2026, 10, 17, 12, 0, tzinfo=_TAIPEI)

    with pytest.raises(snapshot.OfficialAttentionSnapshotError, match="已取消"):
        snapshot.read_official_attention_snapshot(
            pin, stock_code="*", decision_cutoff=cutoff, check_cancel=lambda: True
        )


def test_reader_detects_an_artifact_changed_during_its_consistent_read(tmp_path, monkeypatch):
    capture = _capture(tmp_path, monkeypatch)
    pin = _seal(capture)
    manifest = json.loads((pin.directory / "manifest.json").read_text(encoding="utf-8"))
    artifact_count = len(manifest["artifact_pins"])
    calls = 0

    def mutate_during_final_recheck() -> bool:
        nonlocal calls
        calls += 1
        if calls == artifact_count + 3:
            raw_path = pin.directory / "response.raw"
            raw_path.write_bytes(b"y" * len(capture["raw"]))
        return False

    monkeypatch.setattr(snapshot, "datetime", _NextDayDateTime)
    cutoff = _NextDayDateTime(2026, 10, 17, 12, 0, tzinfo=_TAIPEI)
    with pytest.raises(snapshot.OfficialAttentionSnapshotError, match="讀取期間改變"):
        snapshot.read_official_attention_snapshot(
            pin, stock_code="*", decision_cutoff=cutoff, check_cancel=mutate_during_final_recheck
        )
