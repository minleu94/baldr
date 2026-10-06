from __future__ import annotations

from datetime import date
from hashlib import sha256
import gzip
import io
import json
from pathlib import Path
import zlib

import pytest
import requests

from data_module.mops_ezsearch_statement_availability import (
    MOPS_RESPONSE_MAX_BYTES,
    MOPS_RESPONSE_MAX_DECODED_BYTES,
    MOPS_RESPONSE_PREFIX_BYTES,
    MOPSQueryResult,
    MOPSQueryResponseError,
    MOPS_STATEMENT_AVAILABILITY_SOURCE,
    build_query_payload,
    build_statement_availability_artifact,
    query_mops_ezsearch,
)


def _row(
    *,
    item: str = "F26",
    subject: str = "115年第2季資產負債表",
    clock: str = "18:17:06",
) -> dict[str, str]:
    return {
        "CDATE": "115/07/27",
        "CTIME": clock,
        "TYPEK": "上市",
        "COMPANY_ID": "3321",
        "COMPANY_NAME": "同泰",
        "CODE_NAME": "電子零組件業",
        "AN_CODE": item,
        "AN_NAME": "資產負債表",
        "SUBJECT": subject,
        "HYPERLINK": (
            "https://mopsov.twse.com.tw/mops/web/ajax_t164sb03?"
            "co_id=3321&year=115&season=2"
        ),
    }


def _result(*rows: dict[str, str], item: str = "F26") -> MOPSQueryResult:
    return MOPSQueryResult(
        market="sii",
        announcement_item=item,
        rows=rows,
        response_sha256="a" * 64,
        source_status="success",
    )


class _Response:
    def __init__(
        self,
        payload,
        *,
        status_code: int = 200,
        reason: str = "OK",
        content_type: str = "application/json",
        content_encoding: str = "",
    ) -> None:
        self.body = (
            payload
            if isinstance(payload, bytes)
            else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        self.raw = _RawBody(self.body)
        self.status_code = status_code
        self.reason = reason
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(self.body)),
        }
        if content_encoding:
            self.headers["Content-Encoding"] = content_encoding
        self.closed = False

    def raise_for_status(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _RawBody:
    def __init__(self, body: bytes) -> None:
        self._stream = io.BytesIO(body)

    def read(self, size: int, *, decode_content: bool = False) -> bytes:
        del decode_content
        return self._stream.read(size)


class _Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.response = payload if isinstance(payload, _Response) else _Response(payload)

    def post(self, url, *, data, headers, timeout, stream=False):
        self.calls.append((url, data, headers, timeout, stream))
        return self.response


class _SequenceSession:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = list(responses)
        self.calls = []

    def post(self, url, *, data, headers, timeout, stream=False):
        self.calls.append((url, data, headers, timeout, stream))
        return self.responses.pop(0)


def test_build_query_payload_uses_roc_dates_and_leaves_industry_blank() -> None:
    payload = build_query_payload(
        market="sii",
        announcement_item="F26",
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
    )

    assert payload["TYPEK"] == "sii"
    assert payload["CO_MARKET"] == ""
    assert payload["SDATE"] == "115/07/27"
    assert payload["EDATE"] == "115/07/28"


def test_query_mops_ezsearch_preserves_manifest_hash_and_readonly_headers() -> None:
    payload = {"status": "success", "message": ["回傳成功"], "data": [_row()]}
    session = _Session(payload)

    result = query_mops_ezsearch(
        session,
        market="sii",
        announcement_item="F26",
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
    )

    assert result.rows == (_row(),)
    assert len(result.response_sha256) == 64
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert result.response_sha256 == sha256(canonical.encode("utf-8")).hexdigest()
    assert result.attempts[0].raw_body_sha256 == sha256(session.response.body).hexdigest()
    assert result.attempts[0].raw_body_hash_scope == "full_body"
    assert result.attempts[0].http_status == 200
    assert result.attempts[0].completed_at_utc.endswith("+00:00")
    assert result.query_start_date == date(2026, 7, 27)
    assert result.query_end_date == date(2026, 7, 28)
    assert session.calls[0][1]["CO_MARKET"] == ""
    assert session.calls[0][2]["Referer"].endswith("/ezsearch")
    assert session.calls[0][4] is True
    assert session.calls[0][2]["Accept-Encoding"] == "identity"
    assert session.response.closed is True

    artifact = build_statement_availability_artifact(
        [result],
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
        captured_at="2026-07-28T12:00:00+08:00",
    )
    assert "attempts" not in artifact["query_manifest"][0]


def test_artifact_preserves_official_timestamp_and_projects_next_day() -> None:
    artifact = build_statement_availability_artifact(
        [_result(_row())],
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
        captured_at="2026-07-28T12:00:00+08:00",
    )

    event = artifact["rows"][0]
    mapping = artifact["availability_projection"][0]
    assert event["announcement_at"] == "2026-07-27T18:17:06+08:00"
    assert event["period"] == "2026-Q2"
    assert event["period_end"] == "2026-06-30"
    assert event["source_hash"] == "sha256:" + "a" * 64
    assert mapping == {
        "stock_code": "3321",
        "statement_type": "balance_sheet",
        "period": "2026-Q2",
        "as_of_date": "2026-06-30",
        "announced_date": "2026-07-27",
        "available_date": "2026-07-28",
        "source": MOPS_STATEMENT_AVAILABILITY_SOURCE,
        "source_version": "mops-ezsearch-statement-publication.v1",
        "availability_contract_version": "formal-availability.v2",
        "evidence_class": "official_announcement",
        "source_hash": "sha256:" + "a" * 64,
        "revision": "1",
        "parent_revision": "",
    }
    assert artifact["formal_oos_allowed"] is False
    assert artifact["formal_credit_authorized"] is False
    assert artifact["production_blend_alpha_bp"] == 0
    assert "M31" in artifact["excluded_umbrella_items"]


def test_artifact_deduplicates_exact_events_but_keeps_earliest_revision() -> None:
    later = _row(clock="19:30:00")
    artifact = build_statement_availability_artifact(
        [_result(_row(), _row(), later)],
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
        captured_at="2026-07-28T12:00:00+08:00",
    )

    assert artifact["quality_summary"]["event_count"] == 2
    assert artifact["quality_summary"]["duplicate_event_count"] == 1
    assert artifact["quality_summary"]["projection_count"] == 1
    assert artifact["availability_projection"][0]["announced_date"] == "2026-07-27"


def test_artifact_keeps_valid_rows_when_historical_row_schema_is_incomplete() -> None:
    invalid = _row()
    invalid.pop("CTIME")
    artifact = build_statement_availability_artifact(
        [_result(invalid, _row())],
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
        captured_at="2026-07-28T12:00:00+08:00",
    )

    quality = artifact["quality_summary"]
    assert quality["event_count"] == 1
    assert quality["projection_count"] == 1
    assert quality["invalid_event_count"] == 1
    assert quality["invalid_event_error_counts"] == {
        "MOPS statement row is missing required fields: CTIME": 1
    }
    assert quality["invalid_event_samples"][0]["row_index"] == 1


def test_artifact_quarantines_m31_meeting_notice_as_statement_publication() -> None:
    result = _result(
        _row(
            item="M31",
            subject="公告本公司115年第二季財務報告董事會預計召開日期",
        )
    )

    artifact = build_statement_availability_artifact(
        [result],
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
        captured_at="2026-07-28T12:00:00+08:00",
    )

    assert artifact["quality_summary"]["event_count"] == 0
    assert artifact["quality_summary"]["invalid_event_count"] == 1
    assert artifact["quality_summary"]["invalid_event_error_counts"] == {
        "MOPS statement row announcement item does not match the query": 1
    }


def test_artifact_quarantines_future_timestamp() -> None:
    artifact = build_statement_availability_artifact(
        [_result(_row())],
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
        captured_at="2026-07-27T10:00:00+08:00",
    )

    assert artifact["quality_summary"]["event_count"] == 0
    assert artifact["quality_summary"]["invalid_event_count"] == 1
    assert artifact["quality_summary"]["invalid_event_error_counts"] == {
        "MOPS statement row timestamp is later than captured_at": 1
    }


def test_artifact_rejects_non_sha256_source_hash() -> None:
    with pytest.raises(ValueError, match="response_sha256"):
        build_statement_availability_artifact(
            [
                MOPSQueryResult(
                    market="sii",
                    announcement_item="F26",
                    rows=(_row(),),
                    response_sha256="not-a-hash",
                    source_status="success",
                )
            ],
            start_date=date(2026, 7, 27),
            end_date=date(2026, 7, 28),
            captured_at="2026-07-28T12:00:00+08:00",
        )


def test_artifact_counts_failed_queries_without_treating_them_as_empty_success() -> None:
    artifact = build_statement_availability_artifact(
        [
            _result(_row()),
            MOPSQueryResult(
                market="otc",
                announcement_item="F26",
                rows=(),
                response_sha256="b" * 64,
                source_status="error",
                error_code="network_timeout",
            ),
        ],
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
        captured_at="2026-07-28T12:00:00+08:00",
    )

    assert artifact["quality_summary"]["successful_query_count"] == 1
    assert artifact["quality_summary"]["failed_query_count"] == 1
    assert artifact["query_manifest"][1]["error_code"] == "network_timeout"


def test_artifact_manifest_preserves_query_window_when_present() -> None:
    artifact = build_statement_availability_artifact(
        [
            MOPSQueryResult(
                market="sii",
                announcement_item="F26",
                rows=(_row(),),
                response_sha256="a" * 64,
                source_status="success",
                query_start_date=date(2026, 7, 27),
                query_end_date=date(2026, 7, 28),
            )
        ],
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
        captured_at="2026-07-28T12:00:00+08:00",
    )

    assert artifact["query_manifest"][0]["query_start_date"] == "2026-07-27"
    assert artifact["query_manifest"][0]["query_end_date"] == "2026-07-28"


def test_artifact_separates_official_no_data_queries_from_transport_failures() -> None:
    artifact = build_statement_availability_artifact(
        [
            _result(_row()),
            MOPSQueryResult(
                market="otc",
                announcement_item="F26",
                rows=(),
                response_sha256="b" * 64,
                source_status="fail",
            ),
            MOPSQueryResult(
                market="rotc",
                announcement_item="F26",
                rows=(),
                response_sha256="c" * 64,
                source_status="error",
                error_code="network_timeout",
            ),
        ],
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
        captured_at="2026-07-28T12:00:00+08:00",
    )

    quality = artifact["quality_summary"]
    assert quality["successful_query_count"] == 1
    assert quality["official_no_data_query_count"] == 1
    assert quality["failed_query_count"] == 1
    assert artifact["query_manifest"][1]["source_status"] == "fail"


def test_artifact_rejects_rows_on_official_no_data_query() -> None:
    with pytest.raises(ValueError, match="official no-data query must not contain rows"):
        build_statement_availability_artifact(
            [
                MOPSQueryResult(
                    market="sii",
                    announcement_item="F26",
                    rows=(_row(),),
                    response_sha256="a" * 64,
                    source_status="fail",
                )
            ],
            start_date=date(2026, 7, 27),
            end_date=date(2026, 7, 28),
            captured_at="2026-07-28T12:00:00+08:00",
        )


def test_fetch_cli_safe_query_converts_timeout_to_structured_failure() -> None:
    from scripts.fetch_mops_statement_availability import _safe_query

    class TimeoutSession:
        def post(self, *args, **kwargs):
            del args, kwargs
            raise requests.Timeout("timed out")

    result = _safe_query(
        TimeoutSession(),  # type: ignore[arg-type]
        market="sii",
        announcement_item="F26",
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
        timeout_seconds=1,
    )

    assert result.source_status == "error"
    assert result.error_code == "network_timeout"
    assert result.rows == ()
    assert result.attempts[0].retryable is True
    assert result.attempts[0].error_type == "Timeout"
    assert result.attempts[0].completed_at_utc.endswith("+00:00")


def test_invalid_json_keeps_raw_body_hash_http_metadata_and_bounded_prefix() -> None:
    from scripts.fetch_mops_statement_availability import _safe_query

    body = b"<html><body>temporary upstream response</body></html>"
    session = _Session(_Response(body, content_type="text/html; charset=utf-8"))
    result = _safe_query(
        session,  # type: ignore[arg-type]
        market="sii",
        announcement_item="F26",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        timeout_seconds=1,
    )

    assert result.source_status == "error"
    assert result.error_code == "invalid_json"
    attempt = result.attempts[0]
    assert attempt.http_status == 200
    assert attempt.content_type == "text/html; charset=utf-8"
    assert attempt.raw_body_sha256 == sha256(body).hexdigest()
    assert attempt.raw_body_hash_scope == "full_body"
    assert attempt.raw_body_prefix == body
    assert attempt.retryable is True


@pytest.mark.parametrize(
    ("content_encoding", "encode"),
    [
        ("gzip", gzip.compress),
        ("deflate", zlib.compress),
    ],
)
def test_compressed_response_hashes_entity_but_parses_bounded_decoded_json(
    content_encoding: str,
    encode,
) -> None:
    payload = {"status": "success", "message": ["回傳成功"], "data": [_row()]}
    encoded_body = encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    session = _Session(_Response(encoded_body, content_encoding=content_encoding))

    result = query_mops_ezsearch(
        session,  # type: ignore[arg-type]
        market="sii",
        announcement_item="F26",
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 28),
    )

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert result.rows == (_row(),)
    assert result.response_sha256 == sha256(canonical.encode("utf-8")).hexdigest()
    assert result.attempts[0].raw_body_sha256 == sha256(encoded_body).hexdigest()
    assert result.attempts[0].raw_body_hash_scope == "full_body"
    assert result.attempts[0].content_encoding == content_encoding


def test_compressed_response_with_oversized_decoded_body_fails_closed() -> None:
    body = gzip.compress(b"x" * (MOPS_RESPONSE_MAX_DECODED_BYTES + 1))
    session = _Session(_Response(body, content_encoding="gzip"))

    from scripts.fetch_mops_statement_availability import _query_with_retries

    result = _query_with_retries(
        session,  # type: ignore[arg-type]
        market="sii",
        announcement_item="F27",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        timeout_seconds=1,
        max_retries=1,
    )

    assert len(session.calls) == 1
    assert result.error_code == "decoded_body_limit"
    assert result.attempts[0].retryable is False
    assert result.attempts[0].raw_body_hash_scope == "full_body"
    assert result.attempts[0].raw_body_sha256 == sha256(body).hexdigest()


def test_failure_prefix_is_create_only_and_attempt_lineage_survives_retry(
    tmp_path: Path,
) -> None:
    from scripts.fetch_mops_statement_availability import _query_with_retries

    failed_body = b"<html>" + (b"x" * (MOPS_RESPONSE_PREFIX_BYTES + 500))
    success_payload = {"status": "success", "data": [_row()]}
    session = _SequenceSession(
        [
            _Response(failed_body, content_type="text/html"),
            _Response(success_payload),
        ]
    )
    result = _query_with_retries(
        session,  # type: ignore[arg-type]
        market="sii",
        announcement_item="F26",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        timeout_seconds=1,
        max_retries=1,
        raw_failure_receipt_root=tmp_path / "raw_failed_attempts",
    )

    assert result.source_status == "success"
    assert result.attempt_count == 2
    assert result.retry_error_codes == ("invalid_json",)
    assert len(result.attempts) == 2
    failed_attempt = result.attempts[0]
    assert failed_attempt.raw_body_sha256 == sha256(failed_body).hexdigest()
    assert failed_attempt.raw_body_hash_scope == "full_body"
    assert failed_attempt.raw_body_prefix_path is not None
    prefix_path = tmp_path / failed_attempt.raw_body_prefix_path
    assert prefix_path.read_bytes() == failed_body[:MOPS_RESPONSE_PREFIX_BYTES]
    assert len(prefix_path.read_bytes()) == MOPS_RESPONSE_PREFIX_BYTES
    assert failed_attempt.raw_body_prefix_sha256 == sha256(prefix_path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        from scripts.fetch_mops_statement_availability import _write_failure_prefix_receipt

        _write_failure_prefix_receipt(
            tmp_path / "raw_failed_attempts",
            failed_attempt,
            market="sii",
            announcement_item="F26",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 7),
        )

    artifact = build_statement_availability_artifact(
        [result],
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        captured_at="2026-08-08T12:00:00+08:00",
    )
    assert artifact["query_manifest"][0]["attempt_count"] == 2
    assert artifact["query_manifest"][0]["retry_error_codes"] == ["invalid_json"]
    assert artifact["query_manifest"][0]["attempts"][0]["raw_body_prefix_path"] == (
        "raw_failed_attempts/"
        "mops_sii_F26_2026-08-01_2026-08-07_attempt_1.body.prefix"
    )
    # The official success hash still identifies the final canonical JSON payload.
    canonical = json.dumps(
        success_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert result.response_sha256 == sha256(canonical.encode("utf-8")).hexdigest()


def test_response_read_limit_hash_scope_is_prefix_and_does_not_retry() -> None:
    from scripts.fetch_mops_statement_availability import _query_with_retries

    body = b"x" * (MOPS_RESPONSE_MAX_BYTES + 123)
    response = _Response(body, content_type="text/html")
    session = _Session(response)
    result = _query_with_retries(
        session,  # type: ignore[arg-type]
        market="sii",
        announcement_item="F27",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        timeout_seconds=1,
        max_retries=1,
    )

    assert len(session.calls) == 1
    assert result.error_code == "response_body_limit"
    attempt = result.attempts[0]
    assert attempt.retryable is False
    assert attempt.raw_body_bytes_read == MOPS_RESPONSE_MAX_BYTES
    assert attempt.raw_body_hash_scope == "read_prefix"
    assert attempt.raw_body_sha256 == sha256(body[:MOPS_RESPONSE_MAX_BYTES]).hexdigest()
    assert len(attempt.raw_body_prefix) == MOPS_RESPONSE_PREFIX_BYTES


def test_fetch_cli_date_windows_are_bounded_and_cover_range() -> None:
    from scripts.fetch_mops_statement_availability import _iter_date_windows

    windows = _iter_date_windows(
        date(2026, 5, 1),
        date(2026, 5, 31),
        window_days=7,
    )

    assert windows == (
        (date(2026, 5, 1), date(2026, 5, 7)),
        (date(2026, 5, 8), date(2026, 5, 14)),
        (date(2026, 5, 15), date(2026, 5, 21)),
        (date(2026, 5, 22), date(2026, 5, 28)),
        (date(2026, 5, 29), date(2026, 5, 31)),
    )


def test_fetch_cli_retries_failed_query_and_preserves_error_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import fetch_mops_statement_availability as fetch_cli

    failed = MOPSQueryResult(
        market="otc",
        announcement_item="F29",
        rows=(),
        response_sha256="b" * 64,
        source_status="error",
        error_code="network_error",
        query_start_date=date(2026, 5, 1),
        query_end_date=date(2026, 5, 7),
    )
    succeeded = MOPSQueryResult(
        market="otc",
        announcement_item="F29",
        rows=(_row(item="F29"),),
        response_sha256="c" * 64,
        source_status="success",
        query_start_date=date(2026, 5, 1),
        query_end_date=date(2026, 5, 7),
    )
    results = iter((failed, succeeded))
    monkeypatch.setattr(fetch_cli, "_safe_query", lambda *args, **kwargs: next(results))

    result = fetch_cli._query_with_retries(
        object(),  # type: ignore[arg-type]
        market="otc",
        announcement_item="F29",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 7),
        timeout_seconds=1,
        max_retries=1,
    )

    assert result.source_status == "success"
    assert result.attempt_count == 2
    assert result.retry_error_codes == ("network_error",)


def test_fetch_cli_rejects_more_than_one_retry_before_request() -> None:
    from scripts.fetch_mops_statement_availability import _query_with_retries

    session = _Session(_Response({"status": "success", "data": [_row()]}))

    with pytest.raises(ValueError, match="at most 2 total attempts"):
        _query_with_retries(
            session,  # type: ignore[arg-type]
            market="sii",
            announcement_item="F26",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 7),
            timeout_seconds=1,
            max_retries=2,
        )

    assert session.calls == []


def test_fetch_cli_configures_utf8_stdio_when_streams_support_reconfigure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import fetch_mops_statement_availability as fetch_cli

    class ReconfigurableStream:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def reconfigure(self, **kwargs: str) -> None:
            self.calls.append(kwargs)

    stdout = ReconfigurableStream()
    stderr = ReconfigurableStream()
    monkeypatch.setattr(fetch_cli.sys, "stdout", stdout)
    monkeypatch.setattr(fetch_cli.sys, "stderr", stderr)

    fetch_cli._configure_utf8_stdio()

    assert stdout.calls == [{"encoding": "utf-8", "errors": "backslashreplace"}]
    assert stderr.calls == [{"encoding": "utf-8", "errors": "backslashreplace"}]
