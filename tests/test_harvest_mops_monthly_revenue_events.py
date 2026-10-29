from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from scripts import harvest_mops_monthly_revenue_events as harvest


def test_fetch_ezsearch_window_accepts_valid_json_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    body = json.dumps({"data": [{"COMPANY_ID": "2330"}], "status": "success"}).encode()
    monkeypatch.setattr(harvest.Fetcher, "post", lambda *args, **kwargs: SimpleNamespace(status=200, body=body))

    status, raw, parsed = harvest.fetch_ezsearch_window("sii", date(2026, 1, 1), date(2026, 1, 31))

    assert status == 200
    assert raw == body
    assert parsed == {"data": [{"COMPANY_ID": "2330"}], "status": "success"}


def test_fetch_ezsearch_window_accepts_official_no_announcement_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.dumps(
        {"data": [], "message": ["查無公告資料"], "status": "fail"}, ensure_ascii=False
    ).encode()
    monkeypatch.setattr(harvest.Fetcher, "post", lambda *args, **kwargs: SimpleNamespace(status=200, body=body))

    status, raw, parsed = harvest.fetch_ezsearch_window("pub", date(2026, 9, 6), date(2026, 9, 8))

    assert status == 200
    assert raw == body
    assert parsed["status"] == "fail"
    assert parsed["data"] == []


def test_fetch_ezsearch_window_rejects_application_parameter_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.dumps(
        {"data": [], "message": "參數錯誤", "status": "fail"}, ensure_ascii=False
    ).encode()
    monkeypatch.setattr(harvest.Fetcher, "post", lambda *args, **kwargs: SimpleNamespace(status=200, body=body))

    with pytest.raises(ValueError, match="參數錯誤"):
        harvest.fetch_ezsearch_window("pub", date(2026, 9, 6), date(2026, 9, 8))


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"COMPANY_ID": "2330"}]},
        {"data": [{"COMPANY_ID": "2330"}], "status": ""},
        {"data": [], "status": "success"},
        {"data": [], "status": "fail", "message": ["查無公告資料", "參數錯誤"]},
        {"data": [], "status": "fail", "message": ["查無公告資料", ""]},
    ],
)
def test_fetch_ezsearch_window_rejects_ambiguous_or_mixed_api_results(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode()
    monkeypatch.setattr(harvest.Fetcher, "post", lambda *args, **kwargs: SimpleNamespace(status=200, body=body))

    with pytest.raises(ValueError):
        harvest.fetch_ezsearch_window("pub", date(2026, 9, 6), date(2026, 9, 8))


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


def test_validate_checkpointed_window_requires_manifest_and_events_to_match_raw(tmp_path) -> None:
    payload = {
        "status": "success",
        "data": [{
            "COMPANY_ID": "2330",
            "COMPANY_NAME": "台積電",
            "SUBJECT": "115年8月營收",
            "CDATE": "115/09/10",
            "CTIME": "17:00:00",
        }],
    }
    body = json.dumps(payload, ensure_ascii=False).encode()
    raw_file = tmp_path / "ezsearch_F22_pub_1150906_1150910.json"
    raw_file.write_bytes(body)
    sha = harvest._sha256_of_bytes(body)
    event_rows, corrections = harvest._build_event_rows(
        payload["data"], "pub", raw_file.name, sha
    )
    cp = {
        "sha256": sha,
        "byte_count": len(body),
        "http_status": 200,
        "row_count": 1,
        "corrections_count": corrections,
    }
    manifest = [{
        "file_name": raw_file.name,
        "file_path": f"raw/{raw_file.name}",
        "source_url": harvest.EZSEARCH_URL,
        "http_method": "POST",
        "http_status": "200",
        "market": "pub",
        "query_window": "115/09/06-115/09/10",
        "row_count": "1",
        "sha256": sha,
        "byte_count": str(len(body)),
    }]
    events = [dict(zip(harvest.EVENT_HEADERS, row)) for row in event_rows]

    assert harvest._validate_checkpointed_window(
        window_key="pub_F22_1150906_1150910",
        checkpoint_data=cp,
        raw_filepath=raw_file,
        manifest_rows=manifest,
        event_rows=events,
        market="pub",
        start_roc="115/09/06",
        end_roc="115/09/10",
    ) == (1, 0)

    with pytest.raises(ValueError, match="events.csv"):
        harvest._validate_checkpointed_window(
            window_key="pub_F22_1150906_1150910",
            checkpoint_data=cp,
            raw_filepath=raw_file,
            manifest_rows=manifest,
            event_rows=[],
            market="pub",
            start_roc="115/09/06",
            end_roc="115/09/10",
        )
