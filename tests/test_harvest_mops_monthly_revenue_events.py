from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from scripts import harvest_mops_monthly_revenue_events as harvest


def test_fetch_ezsearch_window_accepts_valid_json_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    body = json.dumps({"data": [{"COMPANY_ID": "2330"}]}).encode()
    monkeypatch.setattr(harvest.Fetcher, "post", lambda *args, **kwargs: SimpleNamespace(status=200, body=body))

    status, raw, parsed = harvest.fetch_ezsearch_window("sii", date(2026, 1, 1), date(2026, 1, 31))

    assert status == 200
    assert raw == body
    assert parsed == {"data": [{"COMPANY_ID": "2330"}]}


@pytest.mark.parametrize("body", [b"not-json", b"[]", b"{}", b'{"data": {}}', b'{"data": [null]}'])
def test_fetch_ezsearch_window_rejects_invalid_http_200_payloads(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    monkeypatch.setattr(harvest.Fetcher, "post", lambda *args, **kwargs: SimpleNamespace(status=200, body=body))

    with pytest.raises(ValueError):
        harvest.fetch_ezsearch_window("sii", date(2026, 1, 1), date(2026, 1, 31))


def test_fetch_ezsearch_window_keeps_non_200_for_retry_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harvest.Fetcher, "post", lambda *args, **kwargs: SimpleNamespace(status=503, body=b"busy"))

    status, raw, parsed = harvest.fetch_ezsearch_window("sii", date(2026, 1, 1), date(2026, 1, 31))

    assert status == 503
    assert raw == b"busy"
    assert parsed == {}
