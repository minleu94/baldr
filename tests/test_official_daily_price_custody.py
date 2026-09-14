from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from data_module.official_daily_price_custody import (
    OfficialDailyPriceCustodyError,
    persist_official_daily_price_response,
)


def _capture(root, captured_at: datetime, raw: bytes):
    return persist_official_daily_price_response(
        output_root=root,
        venue="twse",
        source_id="twse.mi_index.daily_price",
        source_date="2026-09-14",
        requested_url="https://www.twse.com.tw/exchangeReport/MI_INDEX",
        final_url="https://www.twse.com.tw/exchangeReport/MI_INDEX",
        request_parameters={"response": "json", "date": "20260914"},
        http_status=200,
        response_headers={"Content-Type": "application/json"},
        raw_response=raw,
        captured_at=captured_at,
        row_count=1,
        source_columns=("證券代號", "收盤價"),
        parser_id="test.v1",
    )


def test_identical_response_keeps_first_receipt_and_appends_observations(tmp_path):
    raw = '{"tables":[{"fields":["證券代號"],"data":[["1101"]]}]}'.encode("utf-8")
    first = _capture(
        tmp_path,
        datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc),
        raw,
    )
    second = _capture(
        tmp_path,
        datetime(2026, 9, 14, 5, 1, tzinfo=timezone.utc),
        raw,
    )

    assert first["raw_response_sha256"] == second["raw_response_sha256"]
    assert first["receipt_path"] == second["receipt_path"]
    assert first["observation_receipt_path"] != second["observation_receipt_path"]
    receipt = json.loads(
        (tmp_path / "scheduled" / "daily_price_source_custody" / "twse" / "20260914"
         / first["raw_response_sha256"][7:23] / "receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["captured_at"] == "2026-09-14T05:00:00+00:00"
    observations = list(
        (tmp_path / "scheduled" / "daily_price_source_custody" / "twse" / "20260914"
         / first["raw_response_sha256"][7:23] / "observations").glob("*.json")
    )
    assert len(observations) == 2


def test_tampered_immutable_raw_response_is_rejected(tmp_path):
    raw = b'{"tables":[]}'
    first = _capture(
        tmp_path,
        datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc),
        raw,
    )
    raw_path = first["raw_response_path"]
    with open(raw_path, "wb") as stream:
        stream.write(b"tampered")

    with pytest.raises(OfficialDailyPriceCustodyError):
        _capture(
            tmp_path,
            datetime(2026, 9, 14, 5, 2, tzinfo=timezone.utc),
            raw,
        )
