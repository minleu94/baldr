from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping

import pytest

from data_module.selection_official_events import (
    CurrentOfficialDisposalReader,
    CurrentOfficialDisposalSourcePinV1,
    OFFICIAL_DISPOSAL_PARSER_VERSION,
    OFFICIAL_DISPOSAL_PIN_SCHEMA,
    SelectionOfficialEventError,
    TWSE_OPENAPI_SWAGGER_SHA256,
    TWSE_ROW_FIELDS,
    TWSE_ROW_SCHEMA_VERSION,
)
from tests import test_selection_official_events as fixture_helpers


_TWSE_PIN_V2 = "selection-official-disposal-source-pin.v2"
_TWSE_PARSER_V2 = "selection-official-disposal-parser.v2"
_TAIPEI = timezone(timedelta(hours=8))


def _openapi_row(
    *,
    symbol: str,
    announcement: date,
    effective_from: date,
    effective_to: date,
    count: str = "1",
) -> dict[str, str]:
    """以 Swagger 英文 row contract 建立全字串的 TWSE 測試列。"""
    return {
        "Number": "1",
        "Date": fixture_helpers._roc(announcement),
        "Code": symbol,
        "Name": "合成測試公司",
        "NumberOfAnnouncement": count,
        "ReasonsOfDisposition": "合成測試原因",
        "DispositionPeriod": (
            f"{fixture_helpers._roc(effective_from)}～{fixture_helpers._roc(effective_to)}"
        ),
        "DispositionMeasures": "合成測試措施",
        "Detail": "合成測試內容",
        "LinkInformation": "",
    }


def _openapi_bytes(rows: list[Mapping[str, str]]) -> bytes:
    return json.dumps(list(rows), ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _rebound_pin_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """讓反例的 pin identity 自洽，測試 schema guard 本身。"""
    body = {key: value for key, value in payload.items() if key != "identity_sha256"}
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["identity_sha256"] = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
    return payload


def _capture_twse(tmp_path, raw: bytes, *, captured_at: datetime | None = None):
    stamp = captured_at or datetime.now(timezone.utc) - timedelta(seconds=2)
    pointer = fixture_helpers._capture(
        tmp_path,
        specs=fixture_helpers._specs(markets=("twse",)),
        twse_raw=raw,
        captured_at=stamp,
    )
    return pointer, stamp


def test_v3_openapi_rows_keep_full_raw_and_row_hashes_and_allow_distinct_events(tmp_path) -> None:
    stamp = datetime.now(timezone.utc) - timedelta(seconds=2)
    observed = stamp.astimezone(_TAIPEI).date()
    rows = [
        _openapi_row(
            symbol="2330",
            announcement=observed - timedelta(days=1),
            effective_from=observed - timedelta(days=1),
            effective_to=observed + timedelta(days=2),
        ),
        _openapi_row(
            symbol="2330",
            announcement=observed,
            effective_from=observed + timedelta(days=1),
            effective_to=observed + timedelta(days=4),
            count="2",
        ),
    ]
    raw = _openapi_bytes(rows)
    pointer = fixture_helpers._capture(
        tmp_path,
        specs=fixture_helpers._specs(markets=("twse",)),
        twse_raw=raw,
        captured_at=stamp,
    )

    reader = CurrentOfficialDisposalReader.from_pointer(pointer)
    result = reader.get("2330", market="twse")

    assert tuple(TWSE_ROW_FIELDS) == (
        "Number", "Date", "Code", "Name", "NumberOfAnnouncement",
        "ReasonsOfDisposition", "DispositionPeriod", "DispositionMeasures",
        "Detail", "LinkInformation",
    )
    assert reader.source_pin.schema_version == OFFICIAL_DISPOSAL_PIN_SCHEMA
    assert reader.source_pin.reader_parser_version == OFFICIAL_DISPOSAL_PARSER_VERSION
    assert reader.source_pin.twse_source_schema_version == TWSE_ROW_SCHEMA_VERSION
    assert reader.source_pin.twse_openapi_swagger_sha256 == TWSE_OPENAPI_SWAGGER_SHA256
    assert CurrentOfficialDisposalSourcePinV1.from_json(reader.source_pin.to_json()) == reader.source_pin
    assert result.state == "reported_active"
    assert result.historical_pit_eligible is False
    assert result.source_pin_sha256 == reader.source_pin.identity_sha256
    assert len(result.events) == 2
    assert {
        (event.announcement_date, event.effective_from, event.effective_to, event.state)
        for event in result.events
    } == {
        (observed - timedelta(days=1), observed - timedelta(days=1), observed + timedelta(days=2), "effective_in_reported_period"),
        (observed, observed + timedelta(days=1), observed + timedelta(days=4), "announced_not_yet_effective"),
    }
    capture = next(item for item in reader.source_pin.captures if item.source_id == fixture_helpers.TWSE_SOURCE_ID)
    assert capture.raw_sha256 == f"sha256:{hashlib.sha256(raw).hexdigest()}"
    assert all(event.raw_sha256 == capture.raw_sha256 for event in result.events)
    for row, event in zip(rows, result.events):
        canonical_row = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        assert event.raw_row_sha256 == f"sha256:{hashlib.sha256(canonical_row.encode('utf-8')).hexdigest()}"
        assert event.official_available_at is None
        assert event.scope == "current_only"
        assert event.historical_pit_eligible is False


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("twse_source_schema_version", "unverified-contract"),
        ("twse_openapi_swagger_sha256", "sha256:" + "0" * 64),
    ],
)
def test_v3_pin_rejects_rebound_twse_schema_or_swagger_mismatch(
    tmp_path, field: str, bad_value: str
) -> None:
    stamp = datetime.now(timezone.utc) - timedelta(seconds=2)
    observed = stamp.astimezone(_TAIPEI).date()
    pointer, _ = _capture_twse(
        tmp_path,
        _openapi_bytes([
            _openapi_row(
                symbol="2330", announcement=observed,
                effective_from=observed, effective_to=observed + timedelta(days=1),
            )
        ]),
        captured_at=stamp,
    )
    pin = CurrentOfficialDisposalReader.from_pointer(pointer).source_pin
    payload = pin.to_dict()
    payload[field] = bad_value
    _rebound_pin_payload(payload)

    with pytest.raises(SelectionOfficialEventError, match="source_pin_shape_invalid"):
        CurrentOfficialDisposalSourcePinV1.from_dict(payload)


def test_v3_pin_rejects_parser_version_mismatch(tmp_path) -> None:
    stamp = datetime.now(timezone.utc) - timedelta(seconds=2)
    observed = stamp.astimezone(_TAIPEI).date()
    pointer, _ = _capture_twse(
        tmp_path,
        _openapi_bytes([_openapi_row(
            symbol="2330", announcement=observed,
            effective_from=observed, effective_to=observed + timedelta(days=1),
        )]),
        captured_at=stamp,
    )
    payload = CurrentOfficialDisposalReader.from_pointer(pointer).source_pin.to_dict()
    payload["reader_parser_version"] = _TWSE_PARSER_V2
    _rebound_pin_payload(payload)

    with pytest.raises(SelectionOfficialEventError, match="source_pin_identity_invalid"):
        CurrentOfficialDisposalSourcePinV1.from_dict(payload)


def test_v2_pin_roundtrips_without_v3_keys_and_keeps_english_array_unknown(tmp_path) -> None:
    stamp = datetime.now(timezone.utc) - timedelta(seconds=2)
    observed = stamp.astimezone(_TAIPEI).date()
    raw = _openapi_bytes([
        _openapi_row(
            symbol="2330", announcement=observed,
            effective_from=observed, effective_to=observed + timedelta(days=1),
        )
    ])
    pointer, _ = _capture_twse(tmp_path, raw, captured_at=stamp)
    v3_pin = CurrentOfficialDisposalReader.from_pointer(pointer).source_pin
    payload = v3_pin.to_dict()
    payload["schema_version"] = _TWSE_PIN_V2
    payload["reader_parser_version"] = _TWSE_PARSER_V2
    payload.pop("twse_source_schema_version")
    payload.pop("twse_openapi_swagger_sha256")
    legacy_pin = CurrentOfficialDisposalSourcePinV1.from_dict(_rebound_pin_payload(payload))

    legacy_wire = legacy_pin.to_json()
    decoded = json.loads(legacy_wire)
    assert decoded["schema_version"] == _TWSE_PIN_V2
    assert decoded["reader_parser_version"] == _TWSE_PARSER_V2
    assert "twse_source_schema_version" not in decoded
    assert "twse_openapi_swagger_sha256" not in decoded
    assert CurrentOfficialDisposalSourcePinV1.from_json(legacy_wire) == legacy_pin

    direct_legacy_pin = CurrentOfficialDisposalSourcePinV1(
        output_root=v3_pin.output_root,
        pointer_sha256=v3_pin.pointer_sha256,
        pointer_published_at=v3_pin.pointer_published_at,
        run_id=v3_pin.run_id,
        snapshot_relative_path=v3_pin.snapshot_relative_path,
        snapshot_sha256=v3_pin.snapshot_sha256,
        manifest_relative_path=v3_pin.manifest_relative_path,
        manifest_sha256=v3_pin.manifest_sha256,
        snapshot_observed_at=v3_pin.snapshot_observed_at,
        snapshot_partial_failure=v3_pin.snapshot_partial_failure,
        captures=v3_pin.captures,
        schema_version="selection-official-disposal-source-pin.v2",
        reader_parser_version="selection-official-disposal-parser.v2",
    )
    assert direct_legacy_pin == legacy_pin
    assert direct_legacy_pin.identity_sha256 == legacy_pin.identity_sha256
    assert direct_legacy_pin.to_json() == legacy_wire

    old_reader = CurrentOfficialDisposalReader.from_exact(direct_legacy_pin)
    result = old_reader.get("2330", market="twse")
    assert result.state == "unknown"
    assert result.reason_code == "twse_disposal_schema_unconfirmed"
    assert result.events == ()
    assert result.historical_pit_eligible is False


def test_v3_keeps_legacy_chinese_twse_payload_and_tpex_contract(tmp_path) -> None:
    stamp = datetime.now(timezone.utc) - timedelta(seconds=2)
    observed = stamp.astimezone(_TAIPEI).date()
    pointer = fixture_helpers._capture(
        tmp_path,
        specs=fixture_helpers._specs(),
        twse_raw=fixture_helpers._twse_raw(
            symbol="2330",
            announcement=observed,
            effective_from=observed + timedelta(days=1),
            effective_to=observed + timedelta(days=3),
        ),
        tpex_raw=fixture_helpers._tpex_raw(
            symbol="5483",
            announcement=observed,
            effective_from=observed,
            effective_to=observed + timedelta(days=2),
        ),
        captured_at=stamp,
    )

    reader = CurrentOfficialDisposalReader.from_pointer(pointer)
    twse = reader.get("2330", market="twse")
    tpex = reader.get("5483", market="tpex")

    assert reader.source_pin.schema_version == OFFICIAL_DISPOSAL_PIN_SCHEMA
    assert twse.state == "reported_upcoming"
    assert twse.events[0].announcement_date == observed
    assert twse.events[0].official_available_at is None
    assert tpex.state == "reported_active"
    assert tpex.events[0].announcement_date == observed
    assert tpex.events[0].measure is None
    assert tpex.events[0].official_available_at is None
    assert reader.source_pin.tpex_source_schema_version == "tpex-disposal-openapi-row-contract.v2"


@pytest.mark.parametrize(
    "mutation",
    ["missing_field", "extra_field", "non_string_field"],
)
def test_v3_openapi_field_drift_stays_unknown_and_partial(tmp_path, mutation: str) -> None:
    stamp = datetime.now(timezone.utc) - timedelta(seconds=2)
    observed = stamp.astimezone(_TAIPEI).date()
    row = _openapi_row(
        symbol="2330", announcement=observed,
        effective_from=observed, effective_to=observed + timedelta(days=1),
    )
    if mutation == "missing_field":
        row.pop("Name")
    elif mutation == "extra_field":
        row["NewField"] = "schema drift"
    if mutation == "non_string_field":
        non_string_row: dict[str, object] = dict(row)
        non_string_row["Code"] = 2330
        raw = json.dumps([non_string_row], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    else:
        raw = _openapi_bytes([row])
    pointer, _ = _capture_twse(tmp_path, raw, captured_at=stamp)

    result = CurrentOfficialDisposalReader.from_pointer(pointer).get("2330", market="twse")

    assert result.state == "unknown"
    assert result.reason_code == "twse_disposal_openapi_schema_unconfirmed"
    assert result.events == ()
    assert result.partial_failure is True


def test_v3_bad_date_wrong_source_empty_duplicate_and_unmatched_never_certify_absence(tmp_path) -> None:
    stamp = datetime.now(timezone.utc) - timedelta(seconds=2)
    observed = stamp.astimezone(_TAIPEI).date()
    invalid_period = _openapi_row(
        symbol="2330", announcement=observed,
        effective_from=observed, effective_to=observed + timedelta(days=1),
    )
    invalid_period["DispositionPeriod"] = "not-a-date-range"
    invalid_pointer, _ = _capture_twse(
        tmp_path / "invalid-period", _openapi_bytes([invalid_period]), captured_at=stamp
    )
    invalid = CurrentOfficialDisposalReader.from_pointer(invalid_pointer).get("2330", market="twse")
    assert invalid.state == "unknown"
    assert invalid.reason_code == "twse_effective_period_unrecognized"

    invalid_date_row = _openapi_row(
        symbol="2330", announcement=observed,
        effective_from=observed, effective_to=observed + timedelta(days=1),
    )
    invalid_date_row["Date"] = "not-a-date"
    invalid_date_pointer, _ = _capture_twse(
        tmp_path / "invalid-announcement", _openapi_bytes([invalid_date_row]), captured_at=stamp
    )
    invalid_date = CurrentOfficialDisposalReader.from_pointer(invalid_date_pointer).get(
        "2330", market="twse"
    )
    assert invalid_date.state == "unknown"
    assert invalid_date.reason_code == "twse_announcement_date_invalid"

    invalid_count_row = _openapi_row(
        symbol="2330", announcement=observed,
        effective_from=observed, effective_to=observed + timedelta(days=1),
        count="not-a-count",
    )
    invalid_count_pointer, _ = _capture_twse(
        tmp_path / "invalid-count", _openapi_bytes([invalid_count_row]), captured_at=stamp
    )
    invalid_count = CurrentOfficialDisposalReader.from_pointer(invalid_count_pointer).get(
        "2330", market="twse"
    )
    assert invalid_count.state == "unknown"
    assert invalid_count.reason_code == "twse_announcement_count_invalid"

    future_row = _openapi_row(
        symbol="2330", announcement=observed + timedelta(days=1),
        effective_from=observed + timedelta(days=2), effective_to=observed + timedelta(days=3),
    )
    future_pointer, _ = _capture_twse(
        tmp_path / "future-announcement", _openapi_bytes([future_row]), captured_at=stamp
    )
    with pytest.raises(SelectionOfficialEventError, match="future_announcement_after_observation"):
        CurrentOfficialDisposalReader.from_pointer(future_pointer)

    wrong_market_spec = fixture_helpers.SourceSpec(
        fixture_helpers.TWSE_SOURCE_ID,
        fixture_helpers.TWSE_URL,
        "trading_restriction",
        "tpex",
        "不相符測試來源",
    )
    wrong_source_pointer = fixture_helpers._capture(
        tmp_path / "wrong-source",
        specs=(wrong_market_spec,),
        twse_raw=_openapi_bytes([_openapi_row(
            symbol="2330", announcement=observed,
            effective_from=observed, effective_to=observed + timedelta(days=1),
        )]),
        captured_at=stamp,
    )
    with pytest.raises(SelectionOfficialEventError, match="disposal_source_market_or_endpoint_mismatch"):
        CurrentOfficialDisposalReader.from_pointer(wrong_source_pointer)

    empty_pointer, _ = _capture_twse(tmp_path / "empty", b"[]", captured_at=stamp)
    empty = CurrentOfficialDisposalReader.from_pointer(empty_pointer).get("2330", market="twse")
    assert empty.state == "unknown"
    assert empty.reason_code == "twse_empty_feed_has_no_absence_certificate"
    assert empty.events == ()
    assert empty.partial_failure is True

    duplicate = _openapi_row(
        symbol="2330", announcement=observed,
        effective_from=observed, effective_to=observed + timedelta(days=1),
    )
    duplicate_pointer, _ = _capture_twse(
        tmp_path / "duplicate", _openapi_bytes([duplicate, duplicate]), captured_at=stamp
    )
    duplicated = CurrentOfficialDisposalReader.from_pointer(duplicate_pointer).get("2330", market="twse")
    assert len(duplicated.events) == 1
    assert duplicated.partial_failure is True
    assert "duplicate_disposal_event" in duplicated.source_warnings

    missing_source_pointer = fixture_helpers._capture(
        tmp_path / "missing-source",
        specs=fixture_helpers._specs(markets=("tpex",)),
        tpex_raw=fixture_helpers._tpex_raw(
            symbol="5483", announcement=observed,
            effective_from=observed, effective_to=observed + timedelta(days=1),
        ),
        captured_at=stamp,
    )
    missing_source = CurrentOfficialDisposalReader.from_pointer(missing_source_pointer).get(
        "2330", market="twse"
    )
    assert missing_source.state == "unknown"
    assert missing_source.reason_code == "market_source_not_captured"
    assert missing_source.events == ()

    unmatched_pointer, _ = _capture_twse(
        tmp_path / "unmatched",
        _openapi_bytes([_openapi_row(
            symbol="2330", announcement=observed,
            effective_from=observed, effective_to=observed + timedelta(days=1),
        )]),
        captured_at=stamp,
    )
    unmatched = CurrentOfficialDisposalReader.from_pointer(unmatched_pointer).get("2317", market="twse")
    assert unmatched.state == "unknown"
    assert unmatched.reason_code == "no_row_absence_not_certified"
    assert unmatched.events == ()
