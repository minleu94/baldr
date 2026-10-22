from __future__ import annotations

from datetime import datetime, timezone
from http.client import HTTPResponse
import hashlib
import io
import json
from pathlib import Path
import time

import pytest

import data_module.mops_monthly_revenue_history as history
from data_module.daily_source_snapshot import DailySourceTransportCapture
from data_module.mops_monthly_revenue_history import (
    MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS,
    MopsMonthlyRevenueHistoryCapturePlan,
    MopsMonthlyRevenueHistoryError,
    MopsMonthlyRevenueHistoricalCapture,
    capture_mops_monthly_revenue_history_batch,
    capture_mops_monthly_revenue_history_plan_chunk,
    parse_mops_monthly_revenue_history_capture,
    plan_mops_monthly_revenue_history_capture,
    write_mops_monthly_revenue_history_plan_chunk_receipt_create_only,
    write_mops_monthly_revenue_history_plan_create_only,
    read_mops_monthly_revenue_history_capture,
    write_mops_monthly_revenue_history_capture_create_only,
)
from data_module.monthly_revenue_revision_archive import (
    MonthlyRevenueRawBatchEvidenceV1,
)


CAPTURED_AT = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def _html(market: str = "twse", period: str = "2026-09", amount: str = "1,234") -> bytes:
    year, month = period.split("-")
    roc_year = int(year) - 1911
    title = "上市" if market == "twse" else "上櫃"
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"></head><body>"
        f"<h1>{title}公司{roc_year:03d}年{int(month)}月份月營業收入彙總表</h1>"
        "<p>出表日期：115/10/11</p><p>單位：新臺幣仟元</p>"
        "<table><tr><th>公司代號</th><th>公司名稱</th><th>當月營收</th>"
        "<th>上月營收</th><th>去年當月營收</th><th>上月比較增減(%)</th>"
        "<th>去年同月增減(%)</th><th>當月累計營收</th><th>去年累計營收</th>"
        "<th>前期比較增減(%)</th><th>備註</th></tr>"
        f"<tr><td>2330</td><td>台積電</td><td>{amount}</td><td>1,100</td>"
        "<td>900</td><td>12.2</td><td>37.1</td><td>11,000</td>"
        "<td>8,000</td><td>20</td><td>修正申報</td></tr></table></body></html>"
    ).encode("utf-8")


def _capture(
    *, market: str = "twse", period: str = "2026-09", html: bytes | None = None,
    captured_at: datetime = CAPTURED_AT,
) -> MopsMonthlyRevenueHistoricalCapture:
    body = html or _html(market, period)
    url = history._official_history_url(market, period)
    transport = DailySourceTransportCapture(
        raw_response_bytes=body,
        official_source_url=url,
        response_status=200,
        content_type="text/html; charset=utf-8",
        declared_decoding_encoding="utf-8",
        decoding_basis="http_content_type_charset",
        body_completed_at=captured_at,
        transport_sha256=hashlib.sha256(body).hexdigest(),
        response_body_complete=True,
        received_body_bytes=len(body),
        content_length_original_text=str(len(body)),
        body_completion_evidence_ref="eof:isolated-test-read-until-empty",
        response_url=url,
        content_encoding_original_text="identity",
        eof_observed=True,
        body_observation_ended_at=captured_at,
    )
    return MopsMonthlyRevenueHistoricalCapture(
        market=market,
        period=period,
        requested_url=url,
        response_url=url,
        request_started_at=captured_at,
        transport_capture=transport,
    )


def test_historical_capture_uses_existing_parser_and_never_infers_twd_or_pit():
    capture = _capture()
    rows = parse_mops_monthly_revenue_history_capture(capture)
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "2330"
    assert rows[0]["current_month_revenue"] == "1234"
    assert rows[0]["source"] == "mops.monthly_revenue_static_snapshot"
    assert capture.source_id == MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS["twse"]
    assert capture.observed_unit_annotations == ("仟元",)
    assert capture.to_dict()["source_unit"] == "unknown"
    assert capture.to_dict()["normalized_currency_unit"] is None
    assert capture.availability_at is None
    assert capture.availability_basis == "retrospective_capture_only"
    assert capture.historical_pit_eligible is False
    assert capture.license_status == "not_established_by_current_opendata_dataset_license"
    assert capture.printed_report_date == "2026-10-11"


def test_content_revision_identity_preserves_same_period_changed_raw_as_distinct():
    initial = _capture(html=_html(amount="1,234"))
    changed = _capture(
        html=_html(amount="1,235"),
        captured_at=datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc),
    )
    assert initial.period == changed.period
    assert initial.revision_id != changed.revision_id
    assert initial.source_version != changed.source_version
    assert initial.raw_response_sha256 != changed.raw_response_sha256
    assert initial.to_dict()["parent_revision_id"] is None
    assert changed.to_dict()["parent_revision_id"] is None


def test_capture_converts_to_retrospective_archive_evidence_without_claiming_pit():
    capture = _capture()
    evidence = capture.to_monthly_revenue_raw_batch_evidence()
    assert type(evidence) is MonthlyRevenueRawBatchEvidenceV1
    assert evidence.source_id == MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS["twse"]
    assert evidence.captured_at == evidence.available_at == capture.transport_capture.body_completed_at
    assert evidence.availability_basis == "retrospective_capture_observation"
    assert evidence.official_announcement_at is None
    assert evidence.official_revision_id is None
    assert evidence.rows[0].stock_code == "2330"
    assert dict(evidence.rows[0].source_values)["當月營收"] == "1,234"
    assert evidence.rows[0].source_unit_text == "仟元"
    assert evidence.rows[0].unit_status == "unknown"
    assert evidence.rows[0].unit_proof_sha256 is None
    provenance = dict(evidence.transport_provenance)
    assert provenance["requested_url"] == capture.requested_url
    assert provenance["response_url"] == capture.response_url
    assert provenance["observed_printed_report_date"] == "2026-10-11"
    assert "raw_response_bytes_base64" not in provenance["transport_capture_json"]


def test_capture_artifact_create_only_and_reader_reparse(tmp_path: Path):
    capture = _capture()
    artifact = tmp_path / "history.json"
    write_mops_monthly_revenue_history_capture_create_only(artifact, capture)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    reopened = read_mops_monthly_revenue_history_capture(
        artifact, expected_sha256=digest
    )
    assert reopened.canonical_bytes() == capture.canonical_bytes()
    assert reopened.transport_capture.response_url == capture.response_url
    assert reopened.transport_capture.content_encoding_original_text == "identity"
    assert reopened.transport_capture.eof_observed is True
    assert reopened.transport_capture.body_observation_ended_at == capture.transport_capture.body_observation_ended_at
    assert parse_mops_monthly_revenue_history_capture(reopened) == capture.rows
    with pytest.raises(MopsMonthlyRevenueHistoryError, match="create_only_conflict"):
        write_mops_monthly_revenue_history_capture_create_only(artifact, capture)
    with pytest.raises(MopsMonthlyRevenueHistoryError, match="sha256_mismatch"):
        read_mops_monthly_revenue_history_capture(artifact, expected_sha256="0" * 64)


def test_invalid_market_period_or_report_identity_fails_closed():
    with pytest.raises(MopsMonthlyRevenueHistoryError, match="period_invalid"):
        _capture(period="2026-13")
    with pytest.raises(MopsMonthlyRevenueHistoryError, match="official_report_validation_failed"):
        _capture(html=_html(period="2026-08"))


class _FakeResponse:
    def __init__(self, url: str, body: bytes):
        self._url = url
        self._body = body
        self.status = 200
        self.headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Content-Encoding": "identity",
            "Content-Length": str(len(body)),
        }
        self.fp = _FakeBodyReader(body)
        self.code = self.status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self._url

    def close(self):
        pass

    def read1(self, size: int = -1):
        return self.fp.read1(size)



class _FakeSocket:
    def __init__(self):
        self.timeouts: list[float] = []

    def settimeout(self, timeout: float):
        self.timeouts.append(timeout)


class _FakeRawStream:
    def __init__(self, response_socket=None):
        self._sock = response_socket if response_socket is not None else _FakeSocket()


class _BytesHttpSocket:
    """離線HTTPResponse測試用socket替身；wire bytes僅存於記憶體。"""

    def __init__(self, wire_bytes: bytes):
        self._wire_bytes = wire_bytes
        self.timeouts: list[float] = []

    def makefile(self, _mode: str):
        return _BytesHttpFile(self._wire_bytes, self)

    def settimeout(self, timeout: float):
        self.timeouts.append(timeout)


class _BytesHttpFile:
    """模擬標準庫HTTPResponse所需的buffer/raw/socket連結。"""

    def __init__(self, wire_bytes: bytes, response_socket: _BytesHttpSocket):
        self._buffer = io.BytesIO(wire_bytes)
        self.raw = _FakeRawStream(response_socket)

    def read(self, size: int = -1):
        return self._buffer.read(size)

    def read1(self, size: int = -1):
        return self._buffer.read1(size)

    def readline(self, size: int = -1):
        return self._buffer.readline(size)

    def close(self):
        self._buffer.close()


class _FakeBodyReader:
    def __init__(self, body: bytes, *, chunk_size: int | None = None, fail_after_chunks: int | None = None):
        self._body = body
        self._offset = 0
        self._chunk_size = chunk_size
        self._fail_after_chunks = fail_after_chunks
        self._chunks = 0
        self.fp = self
        self.raw = _FakeRawStream()

    def read1(self, size: int = -1):
        if self._fail_after_chunks is not None and self._chunks >= self._fail_after_chunks:
            raise TimeoutError("fixture body timeout")
        if self._offset >= len(self._body):
            return b""
        limit = size if size >= 0 else len(self._body)
        if self._chunk_size is not None:
            limit = min(limit, self._chunk_size)
        piece = self._body[self._offset : self._offset + limit]
        self._offset += len(piece)
        self._chunks += 1
        return piece


def test_bounded_capture_does_at_most_four_single_gets_with_eight_second_timeout(monkeypatch):
    calls: list[tuple[str, float]] = []

    def fake_urlopen(request, *, timeout):
        url = request.full_url
        calls.append((url, timeout))
        market = "twse" if "/sii/" in url else "tpex"
        match = url.rsplit("/", 1)[1]
        year_part, month_part = match.removeprefix("t21sc03_").removesuffix("_0.html").split("_")
        period = f"{int(year_part) + 1911:04d}-{int(month_part):02d}"
        return _FakeResponse(url, _html(market, period))

    monkeypatch.setattr(history, "urlopen", fake_urlopen)
    result = capture_mops_monthly_revenue_history_batch(
        start_period="2026-08",
        end_period="2026-09",
        markets=("twse", "tpex"),
    )
    assert len(calls) == 4
    assert all(timeout == 8.0 for _, timeout in calls)
    assert len(result.captures) == 4
    assert result.failures == ()


def test_capture_batch_rejects_more_than_two_months_without_network(monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("network must not be called for invalid bounds")

    monkeypatch.setattr(history, "urlopen", unexpected)
    with pytest.raises(MopsMonthlyRevenueHistoryError, match="two_month_limit"):
        capture_mops_monthly_revenue_history_batch(
            start_period="2026-07",
            end_period="2026-09",
            markets=("twse",),
        )


def test_long_range_plan_is_offline_bounded_and_resumable(monkeypatch, tmp_path: Path):
    plan = plan_mops_monthly_revenue_history_capture(
        start_period="2000-01",
        end_period="2019-12",
        markets=("twse", "tpex"),
    )
    assert isinstance(plan, MopsMonthlyRevenueHistoryCapturePlan)
    assert len(plan.requested_pairs) == 480
    assert len(plan.chunks) == 120
    assert all(1 <= len(chunk) <= 4 for chunk in plan.chunks)
    assert plan.to_dict()["network_enabled"] is False
    attempts: list[tuple[str, str]] = []

    def failed_capture(*, market, period, timeout_seconds, transport_mode="direct_static_v1"):
        attempts.append((market, period))
        raise OSError("isolated failure")

    monkeypatch.setattr(history, "capture_mops_monthly_revenue_history_period", failed_capture)
    chunk = capture_mops_monthly_revenue_history_plan_chunk(plan)
    assert len(attempts) == 4
    assert len(chunk.batch.failures) == 4
    assert chunk.next_cursor is not None
    assert len(chunk.unattempted_pairs) == 476
    assert chunk.to_dict()["next_cursor"] == chunk.next_cursor
    plan_path, plan_sha = write_mops_monthly_revenue_history_plan_create_only(
        tmp_path / "plan.json", plan
    )
    receipt_path, receipt_sha = write_mops_monthly_revenue_history_plan_chunk_receipt_create_only(
        tmp_path / "chunk.json", chunk
    )
    assert plan_path.read_bytes() == plan.canonical_bytes()
    assert hashlib.sha256(plan_path.read_bytes()).hexdigest() == plan_sha
    assert receipt_path.read_bytes() == chunk.canonical_bytes()
    assert hashlib.sha256(receipt_path.read_bytes()).hexdigest() == receipt_sha


def test_long_range_planner_rejects_more_than_240_months():
    with pytest.raises(MopsMonthlyRevenueHistoryError, match="240_month_limit"):
        plan_mops_monthly_revenue_history_capture(
            start_period="2000-01",
            end_period="2020-01",
            markets=("twse",),
        )


def _redirect_chain_responses(*, market="twse", period="2026-09", popup_url=None, static_path=None):
    popup_url = popup_url or "https://mopsov.twse.com.tw/mops/web/t21sc04_ifrs"
    folder = "sii" if market == "twse" else "otc"
    roc_year = int(period[:4]) - 1911
    static_path = static_path or f"/nas/t21/{folder}/t21sc03_{roc_year}_{int(period[5:7])}_0.html"
    redirect_body = (
        '{"result":{"url":"' + popup_url + '"}}'
    ).encode("utf-8")
    popup_body = f"<html><body><script>window.open('{static_path}','')</script></body></html>".encode("utf-8")
    static_body = _html(market, period)
    responses = {
        history.MOPS_REDIRECT_API_URL: _FakeResponse(
            history.MOPS_REDIRECT_API_URL, redirect_body
        ),
        popup_url: _FakeResponse(popup_url, popup_body),
        f"https://mopsov.twse.com.tw{static_path}": _FakeResponse(
            f"https://mopsov.twse.com.tw{static_path}", static_body
        ),
    }
    responses[history.MOPS_REDIRECT_API_URL].headers["Content-Type"] = "application/json; charset=utf-8"
    return responses


def _install_redirect_opener(monkeypatch, responses, *, calls=None):
    calls = calls if calls is not None else []

    class FakeOpener:
        def open(self, request, *, timeout):
            calls.append((request, timeout))
            return responses[request.full_url]

    monkeypatch.setattr(history, "build_opener", lambda *_args: FakeOpener())
    return calls


@pytest.mark.parametrize("market", ["twse", "tpex"])
def test_redirect_chain_mode_captures_each_hop_and_reopens_canonical_artifact(monkeypatch, tmp_path, market):
    responses = _redirect_chain_responses(market=market)
    calls = _install_redirect_opener(monkeypatch, responses)
    monkeypatch.setattr(history, "urlopen", lambda *_args, **_kwargs: pytest.fail("redirect mode must not fallback to direct GET"))
    capture = history.capture_mops_monthly_revenue_history_period(
        market=market, period="2026-09", transport_mode="redirect_chain_v1"
    )
    assert len(calls) == 3
    assert [request.get_method() for request, _ in calls] == ["POST", "GET", "GET"]
    assert [timeout for _, timeout in calls] == [8.0, 8.0, 8.0]
    assert capture.transport_mode == "redirect_chain_v1"
    assert len(capture.transport_hops) == 3
    assert capture.transport_hops[0].request_url == history.MOPS_REDIRECT_API_URL
    assert capture.transport_hops[0].request_body_sha256 == hashlib.sha256(capture.transport_hops[0].request_body).hexdigest()
    post_payload = json.loads(capture.transport_hops[0].request_body.decode("utf-8"))
    assert post_payload["parameters"]["TYPEK"] == ("sii0" if market == "twse" else "otc0")
    assert f"/nas/t21/{'sii' if market == 'twse' else 'otc'}/" in capture.requested_url
    assert capture.source_id == MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS[market]
    assert capture.transport_hops[-1].raw_response_bytes == capture.raw_response_bytes
    assert "redirect-chain.v1" in capture.source_version
    assert parse_mops_monthly_revenue_history_capture(capture)[0]["stock_code"] == "2330"
    evidence = capture.to_monthly_revenue_raw_batch_evidence()
    provenance = dict(evidence.transport_provenance)
    assert provenance["transport_mode"] == "redirect_chain_v1"
    assert '"transport_hops"' not in provenance["transport_chain_json"]
    assert '"raw_response_sha256"' in provenance["transport_chain_json"]

    artifact = tmp_path / "redirect-capture.json"
    write_mops_monthly_revenue_history_capture_create_only(artifact, capture)
    reopened = read_mops_monthly_revenue_history_capture(
        artifact, expected_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest()
    )
    assert reopened.transport_mode == "redirect_chain_v1"
    assert reopened.transport_hops == capture.transport_hops
    assert parse_mops_monthly_revenue_history_capture(reopened) == capture.rows


def test_stdlib_httpresponse_reads_chunked_entity_body_and_preserves_transfer_encoding():
    entity_body = b'{"result":{"url":"https://mopsov.twse.com.tw/mops/web/t21sc04_ifrs"}}'
    chunked_wire_body = (
        f"{len(entity_body):X}\r\n".encode("ascii")
        + entity_body
        + b"\r\n0\r\n\r\n"
    )
    wire = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json; charset=utf-8\r\n"
        b"Transfer-Encoding: chunked\r\n"
        b"\r\n"
        + chunked_wire_body
    )
    response_socket = _BytesHttpSocket(wire)
    response = HTTPResponse(response_socket)
    response.begin()
    started = time.monotonic()
    raw, eof, truncated, _ended = history._read_transport_prefix(
        response,
        started_monotonic=started,
        timeout_seconds=history.MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS,
        max_bytes=history.MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_BYTES,
    )
    assert raw == entity_body
    assert eof is True and truncated is False
    assert raw != chunked_wire_body
    assert response_socket.timeouts
    assert dict(history._safe_response_headers(response.headers))["transfer-encoding"] == "chunked"
    response.close()


@pytest.mark.parametrize(
    ("claimed_length", "entity_body", "expected_eof", "expected_truncated"),
    [
        (5, b"hello", True, False),
        (8, b"short", False, True),
    ],
)
def test_stdlib_httpresponse_content_length_complete_vs_short_body(
    claimed_length, entity_body, expected_eof, expected_truncated
):
    wire = (
        b"HTTP/1.1 200 OK\r\n"
        + f"Content-Length: {claimed_length}\r\n".encode("ascii")
        + b"Content-Type: text/html; charset=utf-8\r\n\r\n"
        + entity_body
    )
    response_socket = _BytesHttpSocket(wire)
    response = HTTPResponse(response_socket)
    response.begin()
    raw, eof, truncated, _ended = history._read_transport_prefix(
        response,
        started_monotonic=time.monotonic(),
        timeout_seconds=history.MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS,
        max_bytes=history.MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_BYTES,
    )
    assert raw == entity_body
    assert eof is expected_eof
    assert truncated is expected_truncated
    assert response_socket.timeouts
    response.close()


@pytest.mark.parametrize(
    ("claimed_length", "entity_body", "expect_incomplete"),
    [
        (5, b"hello", False),
        (8, b"short", True),
    ],
)
def test_direct_httpresponse_content_length_complete_vs_short_body(
    claimed_length, entity_body, expect_incomplete
):
    wire = (
        b"HTTP/1.1 200 OK\r\n"
        + f"Content-Length: {claimed_length}\r\n".encode("ascii")
        + b"Content-Type: text/html; charset=utf-8\r\n\r\n"
        + entity_body
    )
    response_socket = _BytesHttpSocket(wire)
    response = HTTPResponse(response_socket)
    response.begin()
    if expect_incomplete:
        with pytest.raises(MopsMonthlyRevenueHistoryError, match="response_body_incomplete"):
            history._read_bounded_eof(
                response,
                started_monotonic=time.monotonic(),
                timeout_seconds=history.MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS,
            )
    else:
        assert history._read_bounded_eof(
            response,
            started_monotonic=time.monotonic(),
            timeout_seconds=history.MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS,
        ) == entity_body
    assert response_socket.timeouts
    response.close()


def test_redirect_chain_accepts_exact_official_ajax_popup_parameters_query(monkeypatch):
    popup_url = (
        "https://mopsov.twse.com.tw/mops/web/ajax_t21sc04_ifrs?parameters="
        + "a1" * 64
    )
    responses = _redirect_chain_responses(popup_url=popup_url)
    calls = _install_redirect_opener(monkeypatch, responses)
    capture = history.capture_mops_monthly_revenue_history_period(
        market="twse", period="2026-09", transport_mode="redirect_chain_v1"
    )
    assert len(calls) == 3
    assert capture.transport_hops[1].request_url == popup_url
    assert capture.requested_url.endswith("/nas/t21/sii/t21sc03_115_9_0.html")


@pytest.mark.parametrize(
    "popup_url",
    [
        "https://example.invalid/mops/web/ajax_t21sc04_ifrs?parameters=" + "a1" * 32,
        "https://mopsov.twse.com.tw/mops/web/ajax_t21sc04_ifrs?parameters=" + "a1" * 32 + "&parameters=" + "b2" * 32,
        "https://mopsov.twse.com.tw/mops/web/ajax_t21sc04_ifrs?parameters=" + "a1" * 32 + "&extra=1",
        "https://mopsov.twse.com.tw/mops/web/other?parameters=" + "a1" * 32,
        "https://mopsov.twse.com.tw/mops/web/ajax_t21sc04_ifrs?parameters=" + "zz" * 32,
    ],
)
def test_official_popup_url_rejects_host_duplicate_or_extra_query(popup_url):
    assert history._is_official_popup_url(popup_url) is False


def test_official_popup_url_keeps_legacy_no_query_fixture_compatible():
    assert history._is_official_popup_url(
        "https://mopsov.twse.com.tw/mops/web/t21sc04_ifrs"
    ) is True


def test_direct_reader_uses_httpresponse_entity_body_after_chunk_decoding():
    entity_body = b"<html><body>monthly report</body></html>"
    wire = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"Transfer-Encoding: chunked\r\n\r\n"
        + f"{len(entity_body):X}\r\n".encode("ascii")
        + entity_body
        + b"\r\n0\r\n\r\n"
    )
    response = HTTPResponse(_BytesHttpSocket(wire))
    response.begin()
    raw = history._read_bounded_eof(
        response,
        started_monotonic=time.monotonic(),
        timeout_seconds=history.MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS,
    )
    assert raw == entity_body
    response.close()


@pytest.mark.parametrize(
    ("popup_url", "static_path", "expected_reason"),
    [
        ("https://example.invalid/mops/web/t21sc04_ifrs", None, "redirect_popup_url_invalid"),
        (None, "/nas/t21/otc/t21sc03_115_9_0.html", "popup_static_path_market_period_mismatch"),
        (None, "/nas/t21/sii/t21sc03_115_8_0.html", "popup_static_path_market_period_mismatch"),
    ],
)
def test_redirect_chain_rejects_unofficial_host_and_wrong_market_with_raw_receipt(
    monkeypatch, popup_url, static_path, expected_reason
):
    responses = _redirect_chain_responses(popup_url=popup_url, static_path=static_path)
    _install_redirect_opener(monkeypatch, responses)
    with pytest.raises(MopsMonthlyRevenueHistoryError, match=expected_reason) as caught:
        history.capture_mops_monthly_revenue_history_period(
            market="twse", period="2026-09", transport_mode="redirect_chain_v1"
        )
    assert caught.value.transport_hops
    first = caught.value.transport_hops[0]
    assert first.raw_response_bytes == responses[history.MOPS_REDIRECT_API_URL].fp._body
    assert first.eof_observed is True
    assert first.raw_response_sha256 == hashlib.sha256(first.raw_response_bytes).hexdigest()


def test_redirect_chain_truncated_response_retains_prefix_sha_and_failure_receipt(monkeypatch):
    oversized = b"x" * (history.MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_BYTES + 1)
    response = _FakeResponse(history.MOPS_REDIRECT_API_URL, oversized)
    response.headers["Content-Type"] = "application/json"
    responses = {history.MOPS_REDIRECT_API_URL: response}
    _install_redirect_opener(monkeypatch, responses)
    with pytest.raises(MopsMonthlyRevenueHistoryError, match="response_body_truncated") as caught:
        history.capture_mops_monthly_revenue_history_period(
            market="twse", period="2026-09", transport_mode="redirect_chain_v1"
        )
    hop = caught.value.transport_hops[0]
    assert hop.raw_response_bytes == oversized[: history.MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_BYTES]
    assert hop.eof_observed is False and hop.body_truncated is True
    assert hop.raw_response_sha256 is None
    assert hop.observed_bytes_sha256 == hashlib.sha256(hop.raw_response_bytes).hexdigest()


def test_redirect_chain_absolute_deadline_preserves_observed_prefix(monkeypatch):
    response = _FakeResponse(history.MOPS_REDIRECT_API_URL, b"partial response")
    response.headers["Content-Type"] = "application/json"
    response.fp = _FakeBodyReader(b"partial response", chunk_size=7)
    clock = iter((1.0, 1.0, 9.0))
    monkeypatch.setattr(history.time, "monotonic", lambda: next(clock))
    responses = {history.MOPS_REDIRECT_API_URL: response}
    _install_redirect_opener(monkeypatch, responses)
    with pytest.raises(MopsMonthlyRevenueHistoryError, match="response_body_truncated") as caught:
        history.capture_mops_monthly_revenue_history_period(
            market="twse", period="2026-09", transport_mode="redirect_chain_v1"
        )
    hop = caught.value.transport_hops[0]
    assert hop.raw_response_bytes == b"partial"
    assert hop.body_truncated is True and hop.eof_observed is False
    assert hop.raw_response_sha256 is None
    assert hop.observed_bytes_sha256 == hashlib.sha256(b"partial").hexdigest()


def test_redirect_chain_challenge_is_not_followed_and_failure_batch_keeps_raw(monkeypatch):
    challenge_body = b"<html><title>Access Denied</title>captcha challenge</html>"
    response = _FakeResponse(history.MOPS_REDIRECT_API_URL, challenge_body)
    response.status = 403
    response.code = 403
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    responses = {history.MOPS_REDIRECT_API_URL: response}
    calls = _install_redirect_opener(monkeypatch, responses)
    result = history.capture_mops_monthly_revenue_history_batch(
        start_period="2026-09", end_period="2026-09", markets=("twse",),
        transport_mode="redirect_chain_v1",
    )
    assert len(calls) == 1
    assert result.captures == ()
    assert "official_challenge_response" in result.failures[0][2]
    assert len(result.failure_receipts) == 1
    hop = result.failure_receipts[0].transport_hops[0]
    assert hop.response_status == 403
    assert hop.raw_response_bytes == challenge_body
    assert hop.eof_observed is True
    assert hop.raw_response_sha256 == hashlib.sha256(challenge_body).hexdigest()


def test_transport_mode_must_be_explicitly_supported_before_network(monkeypatch):
    monkeypatch.setattr(history, "urlopen", lambda *_args, **_kwargs: pytest.fail("network must not run"))
    monkeypatch.setattr(history, "build_opener", lambda *_args: pytest.fail("network must not run"))
    with pytest.raises(MopsMonthlyRevenueHistoryError, match="transport_mode_invalid"):
        history.capture_mops_monthly_revenue_history_period(
            market="twse", period="2026-09", transport_mode="automatic_fallback"
        )
