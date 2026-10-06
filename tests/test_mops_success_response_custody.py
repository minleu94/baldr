from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import gzip
import json
from pathlib import Path

import pytest

from data_module import mops_success_response_custody as custody
from data_module.mops_ezsearch_statement_availability import (
    MOPS_EZSEARCH_QUERY_URL,
    MOPS_RESPONSE_MAX_BYTES,
    MOPSQueryAttempt,
    MOPSQueryResult,
    build_statement_availability_artifact,
    query_mops_ezsearch,
)
from scripts.fetch_mops_statement_availability import _query_with_retries


_START = date(2026, 7, 27)
_END = date(2026, 7, 28)


def _row() -> dict[str, str]:
    return {
        "CDATE": "115/07/27",
        "CTIME": "18:17:06",
        "TYPEK": "上市",
        "COMPANY_ID": "3321",
        "COMPANY_NAME": "同泰",
        "CODE_NAME": "電子零組件業",
        "AN_CODE": "F26",
        "AN_NAME": "資產負債表",
        "SUBJECT": "115年第2季資產負債表",
        "HYPERLINK": "https://mopsov.twse.com.tw/mops/web/ajax_t164sb03?co_id=3321&year=115&season=2",
    }


class _Raw:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self._offset = 0

    def read(self, size: int, *, decode_content: bool = False) -> bytes:
        del decode_content
        start = self._offset
        self._offset = min(len(self._body), self._offset + size)
        return self._body[start : self._offset]


class _Response:
    def __init__(self, body: bytes, *, encoding: str = "", status_code: int = 200) -> None:
        self.raw = _Raw(body)
        self.status_code = status_code
        self.reason = "OK" if status_code == 200 else "Unavailable"
        self.url = MOPS_EZSEARCH_QUERY_URL
        self.headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": str(len(body)),
        }
        if encoding:
            self.headers["Content-Encoding"] = encoding
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Session:
    def __init__(self, *responses: _Response) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> _Response:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def _response_payload(*, status: str = "success") -> bytes:
    payload = {
        "status": status,
        "message": ["回傳成功"] if status == "success" else ["查無資料"],
        "data": [_row()] if status == "success" else [],
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _new_writer(run_root: Path) -> custody.MOPSSuccessResponseCustodyWriter:
    run_root.mkdir()
    return custody.MOPSSuccessResponseCustodyWriter(
        run_root=run_root,
        capture_root=run_root / custody.MOPS_SUCCESS_CUSTODY_DIRECTORY,
    )


def _capture_one(
    tmp_path: Path,
    *,
    status: str = "success",
    encoded: bool = False,
) -> tuple[Path, Path, dict[str, object], bytes]:
    run_root = tmp_path / "run"
    writer = _new_writer(run_root)
    decoded = _response_payload(status=status)
    entity = gzip.compress(decoded) if encoded else decoded
    session = _Session(_Response(entity, encoding="gzip" if encoded else ""))
    result = query_mops_ezsearch(
        session,  # type: ignore[arg-type]
        market="sii",
        announcement_item="F26",
        start_date=_START,
        end_date=_END,
        capture_success_entity=True,
    )
    assert session.calls[0]["allow_redirects"] is False
    assert result.attempts[0].success_entity_bytes == entity
    writer.add_result(result)
    artifact = build_statement_availability_artifact(
        [result],
        start_date=_START,
        end_date=_END,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
    artifact_path = run_root / "mops-statement-availability.json"
    artifact_path.write_bytes(
        (json.dumps(artifact, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    writer.reserve_for_output(0)
    receipt = writer.finalize(artifact_path=artifact_path)
    return run_root, artifact_path, receipt, entity


def test_opt_in_adapter_retains_encoded_entity_without_changing_manifest_abi() -> None:
    decoded = _response_payload()
    entity = gzip.compress(decoded)
    session = _Session(_Response(entity, encoding="gzip"))

    result = query_mops_ezsearch(
        session,  # type: ignore[arg-type]
        market="sii",
        announcement_item="F26",
        start_date=_START,
        end_date=_END,
        capture_success_entity=True,
    )

    attempt = result.attempts[0]
    assert attempt.success_entity_bytes == entity
    assert attempt.raw_body_sha256 == sha256(entity).hexdigest()
    assert attempt.response_url == MOPS_EZSEARCH_QUERY_URL
    assert attempt.content_encoding == "gzip"
    assert session.calls[0]["allow_redirects"] is False
    assert "success_entity_bytes" not in attempt.to_manifest_item()

    default_session = _Session(_Response(decoded))
    default_result = query_mops_ezsearch(
        default_session,  # type: ignore[arg-type]
        market="sii",
        announcement_item="F26",
        start_date=_START,
        end_date=_END,
    )
    assert default_result.attempts[0].success_entity_bytes == b""
    assert "allow_redirects" not in default_session.calls[0]


@pytest.mark.parametrize("encoded", [False, True])
def test_writer_and_readback_verify_encoded_success_entity(
    tmp_path: Path,
    encoded: bool,
) -> None:
    run_root, artifact_path, receipt, entity = _capture_one(
        tmp_path,
        encoded=encoded,
    )

    verified = custody.read_mops_success_response_custody(
        capture_root=run_root / custody.MOPS_SUCCESS_CUSTODY_DIRECTORY,
        artifact_path=artifact_path,
    )
    assert receipt["component_count"] == 1
    assert receipt["aggregate_success_entity_bytes"] == len(entity)
    assert verified["component_count"] == 1
    assert verified["components"][0]["raw_entity_sha256"] == f"sha256:{sha256(entity).hexdigest()}"
    assert verified["formal_oos_allowed"] is False
    assert verified["formal_credit_authorized"] is False


def test_official_no_data_response_is_preserved_as_a_real_successful_http_entity(
    tmp_path: Path,
) -> None:
    run_root, artifact_path, receipt, entity = _capture_one(
        tmp_path,
        status="fail",
    )

    verified = custody.read_mops_success_response_custody(
        capture_root=run_root / custody.MOPS_SUCCESS_CUSTODY_DIRECTORY,
        artifact_path=artifact_path,
    )
    assert receipt["status"] == "captured"
    assert receipt["aggregate_success_entity_bytes"] == len(entity)
    assert verified["component_count"] == 1
    assert verified["components"][0]["market"] == "sii"


def test_retry_failure_prefix_and_final_success_are_both_counted_and_bound(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    writer = _new_writer(run_root)
    success_body = _response_payload()
    session = _Session(
        _Response(b"not-json"),
        _Response(success_body),
    )
    result = _query_with_retries(
        session,  # type: ignore[arg-type]
        market="sii",
        announcement_item="F26",
        start_date=_START,
        end_date=_END,
        timeout_seconds=1,
        max_retries=1,
        raw_failure_receipt_root=run_root / "raw_failed_attempts",
        capture_success_entity=True,
    )
    writer.add_result(result)
    artifact = build_statement_availability_artifact(
        [result],
        start_date=_START,
        end_date=_END,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
    artifact_path = run_root / "mops-statement-availability.json"
    artifact_path.write_bytes(
        (json.dumps(artifact, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    receipt = writer.finalize(artifact_path=artifact_path)

    verified = custody.read_mops_success_response_custody(
        capture_root=run_root / custody.MOPS_SUCCESS_CUSTODY_DIRECTORY,
        artifact_path=artifact_path,
    )
    assert result.attempt_count == 2
    assert receipt["failure_prefix_count"] == 1
    assert receipt["aggregate_failure_prefix_bytes"] == len(b"not-json")
    assert verified["aggregate_raw_bytes"] == len(success_body) + len(b"not-json")


@pytest.mark.parametrize("target", ["raw", "metadata", "artifact"])
def test_readback_rejects_tampered_raw_metadata_or_legacy_artifact(
    tmp_path: Path,
    target: str,
) -> None:
    run_root, artifact_path, _, _ = _capture_one(tmp_path)
    capture_root = run_root / custody.MOPS_SUCCESS_CUSTODY_DIRECTORY
    if target == "raw":
        raw_path = next(capture_root.glob("*.entity"))
        raw_path.write_bytes(raw_path.read_bytes() + b" ")
    elif target == "metadata":
        metadata_path = next(capture_root.glob("*.metadata.json"))
        metadata_path.write_bytes(metadata_path.read_bytes() + b" ")
    else:
        artifact_path.write_bytes(artifact_path.read_bytes() + b" ")

    with pytest.raises(custody.MOPSSuccessResponseCustodyError):
        custody.read_mops_success_response_custody(
            capture_root=capture_root,
            artifact_path=artifact_path,
        )


def test_readback_recomputes_canonical_response_hash_not_only_raw_hash(
    tmp_path: Path,
) -> None:
    run_root, artifact_path, _, _ = _capture_one(tmp_path)
    capture_root = run_root / custody.MOPS_SUCCESS_CUSTODY_DIRECTORY
    raw_path = next(capture_root.glob("*.entity"))
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["message"] = ["被竄改"]
    raw_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    metadata_path = next(capture_root.glob("*.metadata.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    new_raw = raw_path.read_bytes()
    metadata["raw_entity_bytes"] = len(new_raw)
    metadata["raw_entity_sha256"] = f"sha256:{sha256(new_raw).hexdigest()}"
    metadata_path.write_bytes(custody._canonical_json_bytes(metadata))
    receipt_path = capture_root / custody.MOPS_SUCCESS_CUSTODY_RECEIPT
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    component = receipt["components"][0]
    component["raw_entity_bytes"] = len(new_raw)
    component["raw_entity_sha256"] = metadata["raw_entity_sha256"]
    component["metadata_sha256"] = f"sha256:{sha256(metadata_path.read_bytes()).hexdigest()}"
    receipt_path.write_bytes(custody._canonical_json_bytes(receipt))

    with pytest.raises(custody.MOPSSuccessResponseCustodyError):
        custody.read_mops_success_response_custody(
            capture_root=capture_root,
            artifact_path=artifact_path,
        )


def test_writer_rejects_duplicate_run_root_and_raw_budget_excess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_root = tmp_path / "run"
    writer = _new_writer(run_root)
    with pytest.raises(custody.MOPSSuccessResponseCustodyError):
        custody.MOPSSuccessResponseCustodyWriter(
            run_root=run_root,
            capture_root=run_root / custody.MOPS_SUCCESS_CUSTODY_DIRECTORY,
        )

    result = MOPSQueryResult(
        market="sii",
        announcement_item="F26",
        rows=(),
        response_sha256="0" * 64,
        source_status="success",
        query_start_date=_START,
        query_end_date=_END,
        attempts=(
            MOPSQueryAttempt(
                attempt_number=1,
                started_at_utc="2026-09-30T12:00:00+00:00",
                completed_at_utc="2026-09-30T12:00:01+00:00",
                source_status="success",
                http_status=200,
                content_length_header=str(MOPS_RESPONSE_MAX_BYTES + 1),
                raw_body_sha256="a" * 64,
                raw_body_bytes_read=MOPS_RESPONSE_MAX_BYTES + 1,
                raw_body_hash_scope="full_body",
                response_url=MOPS_EZSEARCH_QUERY_URL,
                success_entity_bytes=b"x" * (MOPS_RESPONSE_MAX_BYTES + 1),
            ),
        ),
    )
    monkeypatch.setattr(custody, "MOPS_SUCCESS_CUSTODY_MAX_TOTAL_RAW_BYTES", 1)
    with pytest.raises(custody.MOPSSuccessResponseCustodyError):
        writer.add_result(result)
    assert not tuple((run_root / custody.MOPS_SUCCESS_CUSTODY_DIRECTORY).glob("*.entity"))


def test_writer_fails_closed_when_disk_reserve_would_be_breached(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        custody.shutil,
        "disk_usage",
        lambda _: type("Usage", (), {"free": 16 * 1024 * 1024 + 1})(),
    )
    run_root = tmp_path / "run"
    run_root.mkdir()
    with pytest.raises(custody.MOPSSuccessResponseCustodyError, match="disk reserve"):
        custody.MOPSSuccessResponseCustodyWriter(
            run_root=run_root,
            capture_root=run_root / custody.MOPS_SUCCESS_CUSTODY_DIRECTORY,
        )
    assert not (run_root / custody.MOPS_SUCCESS_CUSTODY_DIRECTORY).exists()
