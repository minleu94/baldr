from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from http.client import IncompleteRead
from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

import data_module.paper_event_source_capture as paper_capture_module
from data_module.formal_daily_input_producer import (
    PAPER_EXECUTION_EVENT_CAPTURE_MAX_BYTES,
    _canonical_json,
    _sha256_bytes,
    _twse_mis_request_url,
)
from data_module.paper_event_source_capture import PaperEventSourceCaptureError
from data_module.paper_event_source_capture import capture_twse_session_open_prices
from data_module.twse_quote_observation_capture import (
    TwseQuoteObservationError,
    capture_twse_quote_observation,
)


OBSERVATION_DATE = date(2026, 9, 7)
CAPTURED_AT = datetime(2026, 9, 7, 1, 5, tzinfo=timezone.utc)
REQUEST_URL = _twse_mis_request_url("tse_2330.tw")


def _valid_raw() -> bytes:
    return _canonical_json(
        {
            "rtcode": "0000",
            "rtmessage": "OK",
            "msgArray": [
                {
                    "c": "2330",
                    "ex": "tse",
                    "d": "20260907",
                    "t": "09:01:00",
                    "tlong": "1788742860000",
                    "z": "10.50",
                    "b": "10.40_1000_10.30_2",
                    "a": "10.60_1",
                    "v": "12",
                }
            ],
        }
    ).encode("utf-8")


class _FakeResponse:
    status = 200

    def __init__(
        self,
        raw: object,
        *,
        final_url: str = REQUEST_URL,
        content_type: str = "application/json; charset=UTF-8",
        read_error: BaseException | None = None,
    ) -> None:
        self._raw = raw
        self._final_url = final_url
        self._read_error = read_error
        self.headers = {
            "Content-Type": content_type,
            "Content-Encoding": "identity",
        }

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def geturl(self) -> str:
        return self._final_url

    def read(self, limit: int) -> object:
        assert limit == PAPER_EXECUTION_EVENT_CAPTURE_MAX_BYTES + 1
        if self._read_error is not None:
            raise self._read_error
        return self._raw


def _install_response_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter((CAPTURED_AT - timedelta(milliseconds=1), CAPTURED_AT))
    monkeypatch.setattr(paper_capture_module, "_utc_now", lambda: next(ticks))


def _capture(
    tmp_path: Path,
    *,
    fetcher: object,
) -> dict[str, object]:
    return capture_twse_quote_observation(
        symbols=("2330",),
        observation_date=OBSERVATION_DATE,
        output_dir=tmp_path / "capture",
        symbol_source={"source": "isolated-test"},
        now=CAPTURED_AT,
        fetcher=fetcher,  # type: ignore[arg-type]
    )


def test_quote_capture_accepts_0000_ok_and_preserves_decimal_integer_and_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_response_clock(monkeypatch)
    raw = _valid_raw()
    requested: list[str] = []

    def fetcher(request: object, timeout: float) -> _FakeResponse:
        assert timeout == 30.0
        requested.append(str(request.full_url))  # type: ignore[attr-defined]
        return _FakeResponse(raw)

    result = _capture(tmp_path, fetcher=fetcher)

    assert result["status"] == "captured"
    assert requested == [REQUEST_URL]
    assert result["captured_at"] == CAPTURED_AT.isoformat()
    assert result["response_completed_at"] == CAPTURED_AT.isoformat()
    raw_path = Path(str(result["raw_response_path"]))
    assert raw_path.read_bytes() == raw
    assert result["raw_response_sha256"] == _sha256_bytes(raw)
    payload = json.loads(
        Path(str(result["observation_path"])).read_text(encoding="utf-8")
    )
    row = payload["rows"][0]
    assert Decimal(row["last_price"]) == Decimal("10.50")
    assert Decimal(row["best_bid"]) == Decimal("10.40")
    assert Decimal(row["best_ask"]) == Decimal("10.60")
    assert row["volume_shares"] == 12
    assert isinstance(row["volume_shares"], int)
    assert row["spread_bp"] == 190
    assert payload["response"]["http_status"] == 200
    assert payload["response"]["final_url"] == REQUEST_URL


def test_paper_attempt_helper_keeps_http_error_raw_response_custody(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_response_clock(monkeypatch)
    raw = b'{"rtcode":"999","rtmessage":"temporarily unavailable","msgArray":[]}'

    def fetcher(request: object, timeout: float) -> object:
        del timeout
        from email.message import Message

        headers = Message()
        headers["Content-Type"] = "application/json"
        raise HTTPError(
            str(request.full_url),  # type: ignore[attr-defined]
            503,
            "Service unavailable",
            headers,
            BytesIO(raw),
        )

    output = tmp_path / "paper-attempt"
    with pytest.raises(PaperEventSourceCaptureError, match="HTTP status 不是 200"):
        capture_twse_session_open_prices(
            symbols=("2330",),
            execution_date=OBSERVATION_DATE,
            output_dir=output,
            now=CAPTURED_AT,
            fetcher=fetcher,  # type: ignore[arg-type]
        )

    assert (output / "raw_response.bin").read_bytes() == raw
    receipt = json.loads(
        (output / "capture_attempt.json").read_text(encoding="utf-8")
    )
    assert receipt["response"]["http_status"] == 503
    assert receipt["raw_response"]["bytes"] == len(raw)
    assert receipt["raw_response"]["sha256"] == _sha256_bytes(raw)
    assert receipt["parser"]["status"] == "not_attempted"
    assert receipt["failure"]["reason"] == "TWSE MIS HTTP status 不是 200"


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("http_error", "HTTP status 不是 200"),
        ("partial_read", "body read 不完整"),
        ("oversize", "超過 bounded bytes"),
        ("wrong_type", "bytes 為空"),
        ("wrong_media", "content type 不是 JSON"),
        ("wrong_final_url", "final URL 與固定 request 不一致"),
    ],
)
def test_quote_capture_rejects_invalid_http_response_before_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected_error: str,
) -> None:
    _install_response_clock(monkeypatch)
    raw = _valid_raw()

    def fetcher(request: object, timeout: float) -> _FakeResponse:
        del timeout
        request_url = str(request.full_url)  # type: ignore[attr-defined]
        assert request_url == REQUEST_URL
        if case == "http_error":
            from email.message import Message

            headers = Message()
            headers["Content-Type"] = "application/json"
            raise HTTPError(
                request_url,
                503,
                "Service unavailable",
                headers,
                BytesIO(raw),
            )
        if case == "partial_read":
            return _FakeResponse(
                raw,
                read_error=IncompleteRead(raw[:32], len(raw)),
            )
        if case == "oversize":
            return _FakeResponse(b"x" * (PAPER_EXECUTION_EVENT_CAPTURE_MAX_BYTES + 1))
        if case == "wrong_type":
            return _FakeResponse("not bytes")
        if case == "wrong_media":
            return _FakeResponse(raw, content_type="text/html")
        if case == "wrong_final_url":
            return _FakeResponse(raw, final_url="https://example.invalid/redirect")
        raise AssertionError(f"unhandled response case: {case}")

    with pytest.raises((PaperEventSourceCaptureError, TwseQuoteObservationError)) as error:
        _capture(tmp_path, fetcher=fetcher)
    assert expected_error in str(error.value)
