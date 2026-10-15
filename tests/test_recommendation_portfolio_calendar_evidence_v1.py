from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import date, datetime, timezone
import hashlib
import json
from dataclasses import replace

import pytest

from app_module.recommendation_portfolio_calendar_evidence_v1 import (
    PORTFOLIO_PERIOD_CALENDAR_EVIDENCE_SCHEMA_V1,
    PortfolioPeriodCalendarEvidenceV1,
    PortfolioPeriodCalendarEvidenceV1Error,
)
from data_module.official_calendar_bundle import (
    MAX_FIXTURE_BYTES,
    TPEX_MARKET_CALENDAR_URL,
    TWSE_HOLIDAY_SCHEDULE_URL,
    CapturedCalendarResponse,
    hash_response_bytes,
)


_CAPTURED_AT = datetime(2026, 8, 28, 1, 0, tzinfo=timezone.utc)
_START = date(2026, 9, 1)
_END = date(2026, 9, 2)
_TWSE_SOURCE = f"{TWSE_HOLIDAY_SCHEDULE_URL}?queryYear=115"
_TPEX_SOURCE = f"{TPEX_MARKET_CALENDAR_URL}?ym=202609&lang=zh-tw"


def _twse_payload() -> list[dict[str, str]]:
    return [
        {"Name": "中秋節", "Date": "1150925", "Description": "依規定放假一日。"},
        {"Name": "國慶日前最後交易日", "Date": "1151009", "Description": "最後交易。"},
    ]


def _tpex_payload() -> dict[str, object]:
    return {
        "calendar": {
            "total": 2,
            "data": {
                "20260901": {"holiday": False, "holidayList": []},
                "20260902": {"holiday": False, "holidayList": []},
            },
            "status": "success",
        },
    }


def _response(
    kind: str,
    key: str,
    source: str,
    payload: object,
    *,
    metadata: Mapping[str, object] | None = None,
) -> CapturedCalendarResponse:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return CapturedCalendarResponse(
        kind=kind,
        key=key,
        source=source,
        source_hash=hash_response_bytes(raw),
        payload=payload,
        raw_bytes=raw,
        metadata=metadata,
    )


def _responses() -> tuple[dict[int, CapturedCalendarResponse], dict[str, CapturedCalendarResponse]]:
    return (
        {2026: _response("twse", "2026", _TWSE_SOURCE, _twse_payload(), metadata={"capture": "fixture"})},
        {"202609": _response("tpex", "202609", _TPEX_SOURCE, _tpex_payload(), metadata={"capture": "fixture"})},
    )


def _evidence() -> PortfolioPeriodCalendarEvidenceV1:
    twse, tpex = _responses()
    return PortfolioPeriodCalendarEvidenceV1.build(
        start_date=_START,
        end_date=_END,
        twse_responses=twse,
        tpex_responses=tpex,
        captured_at=_CAPTURED_AT,
    )


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _resign(value: dict[str, object]) -> str:
    body = dict(value)
    body.pop("evidence_sha256", None)
    value["evidence_sha256"] = hashlib.sha256(_canonical(body)).hexdigest()
    return _canonical(value).decode("utf-8")


def test_roundtrip_keeps_raw_payload_metadata_and_builder_normalized_sessions() -> None:
    original = _evidence()
    raw_json = original.to_json()
    document = json.loads(raw_json)

    assert original.schema_version == PORTFOLIO_PERIOD_CALENDAR_EVIDENCE_SCHEMA_V1
    assert original.start_date == "2026-09-01"
    assert original.end_date == "2026-09-02"
    assert original.candidate_only is True
    assert original.historical_pit_eligible is False
    assert original.performance_eligible is False
    assert original.formal_clock_eligible is False
    assert original.expected_session_dates("twse") == ("2026-09-01", "2026-09-02")
    assert original.expected_session_dates("tpex") == ("2026-09-01", "2026-09-02")
    assert document["twse_responses"][0]["source"] == _TWSE_SOURCE
    assert document["tpex_responses"][0]["metadata"] == {"capture": "fixture"}
    twse_raw = base64.b64decode(document["twse_responses"][0]["raw_response_base64"], validate=True)
    tpex_raw = base64.b64decode(document["tpex_responses"][0]["raw_response_base64"], validate=True)
    assert twse_raw == _response("twse", "2026", _TWSE_SOURCE, _twse_payload()).raw_bytes
    assert tpex_raw == _response("tpex", "202609", _TPEX_SOURCE, _tpex_payload()).raw_bytes

    restored = PortfolioPeriodCalendarEvidenceV1.from_json(raw_json.encode("utf-8"))
    assert restored == original
    assert restored.to_json() == raw_json
    assert restored.evidence_sha256 == original.evidence_sha256


def test_build_rejects_payload_that_differs_from_independently_parsed_raw() -> None:
    twse, tpex = _responses()
    changed_payload = _twse_payload()
    changed_payload[0]["Name"] = "偽造名稱"
    original = twse[2026]
    twse[2026] = replace(original, payload=changed_payload)

    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="payload_does_not_match_raw"):
        PortfolioPeriodCalendarEvidenceV1.build(
            start_date=_START, end_date=_END, twse_responses=twse,
            tpex_responses=tpex, captured_at=_CAPTURED_AT,
        )


def test_build_requires_raw_bytes_and_rejects_oversize_response() -> None:
    twse, tpex = _responses()
    original = twse[2026]
    twse[2026] = CapturedCalendarResponse(
        kind=original.kind, key=original.key, source=original.source,
        source_hash="sha256:" + "0" * 64, payload=original.payload,
    )
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="raw_bytes_missing"):
        PortfolioPeriodCalendarEvidenceV1.build(
            start_date=_START, end_date=_END, twse_responses=twse,
            tpex_responses=tpex, captured_at=_CAPTURED_AT,
        )

    assert original.raw_bytes is not None
    oversized_raw = b" " * (MAX_FIXTURE_BYTES + 1) + original.raw_bytes
    twse[2026] = CapturedCalendarResponse(
        kind=original.kind, key=original.key, source=original.source,
        source_hash=hash_response_bytes(oversized_raw), payload=original.payload,
        raw_bytes=oversized_raw,
    )
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="raw_bytes_over_limit"):
        PortfolioPeriodCalendarEvidenceV1.build(
            start_date=_START, end_date=_END, twse_responses=twse,
            tpex_responses=tpex, captured_at=_CAPTURED_AT,
        )


def test_build_rejects_wrong_endpoint_period_and_naive_capture_clock() -> None:
    twse, tpex = _responses()
    twse[2026] = replace(twse[2026], source=f"{TWSE_HOLIDAY_SCHEDULE_URL}?queryYear=114")
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="endpoint_or_period_mismatch"):
        PortfolioPeriodCalendarEvidenceV1.build(
            start_date=_START, end_date=_END, twse_responses=twse,
            tpex_responses=tpex, captured_at=_CAPTURED_AT,
        )

    twse, tpex = _responses()
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="timezone_aware"):
        PortfolioPeriodCalendarEvidenceV1.build(
            start_date=_START, end_date=_END, twse_responses=twse,
            tpex_responses=tpex, captured_at=datetime(2026, 8, 28),
        )

    twse, tpex = _responses()
    changed_month_payload = {
        "calendar": {
            "total": 1,
            "data": {"20261001": {"holiday": False, "holidayList": []}},
            "status": "success",
        },
    }
    tpex["202609"] = _response("tpex", "202609", _TPEX_SOURCE, changed_month_payload)
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="month mismatch"):
        PortfolioPeriodCalendarEvidenceV1.build(
            start_date=_START, end_date=_END, twse_responses=twse,
            tpex_responses=tpex, captured_at=_CAPTURED_AT,
        )


def test_build_keeps_93_day_and_eight_response_bounds() -> None:
    twse, tpex = _responses()
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="over_93_days"):
        PortfolioPeriodCalendarEvidenceV1.build(
            start_date=date(2026, 1, 1), end_date=date(2026, 4, 4),
            twse_responses=twse, tpex_responses=tpex, captured_at=_CAPTURED_AT,
        )
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="count_over_limit"):
        PortfolioPeriodCalendarEvidenceV1.build(
            start_date=_START, end_date=_END, twse_responses=twse,
            tpex_responses={**tpex, **{f"2026{month:02d}": tpex["202609"] for month in range(1, 9)}},
            captured_at=_CAPTURED_AT,
        )


def test_decoder_rejects_duplicate_nonfinite_invalid_utf8_and_noncanonical_json() -> None:
    evidence = _evidence()
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="duplicate_json_key"):
        PortfolioPeriodCalendarEvidenceV1.from_json(
            b'{"schema_version":"recommendation-portfolio-period-calendar-evidence.v1",'
            b'"schema_version":"recommendation-portfolio-period-calendar-evidence.v1"}'
        )
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="nonfinite_json_constant"):
        PortfolioPeriodCalendarEvidenceV1.from_json(b'{"unknown":NaN}')
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="invalid_utf8"):
        PortfolioPeriodCalendarEvidenceV1.from_json(b"\xff")
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="not_canonical"):
        PortfolioPeriodCalendarEvidenceV1.from_json(evidence.to_json() + "\n")


def test_build_rejects_duplicate_keys_and_invalid_utf8_in_raw_source_bytes() -> None:
    twse, tpex = _responses()
    duplicate_raw = b'[ {"Name":"x","Date":"1150925","Description":"holiday"}, {"Date":"1151009","Date":"1151009"} ]'
    twse[2026] = CapturedCalendarResponse(
        kind="twse", key="2026", source=_TWSE_SOURCE,
        source_hash=hash_response_bytes(duplicate_raw), payload=_twse_payload(), raw_bytes=duplicate_raw,
    )
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="duplicate_json_key"):
        PortfolioPeriodCalendarEvidenceV1.build(
            start_date=_START, end_date=_END, twse_responses=twse,
            tpex_responses=tpex, captured_at=_CAPTURED_AT,
        )

    invalid_raw = b"\xff"
    twse[2026] = CapturedCalendarResponse(
        kind="twse", key="2026", source=_TWSE_SOURCE,
        source_hash=hash_response_bytes(invalid_raw), payload=_twse_payload(), raw_bytes=invalid_raw,
    )
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="invalid_utf8"):
        PortfolioPeriodCalendarEvidenceV1.build(
            start_date=_START, end_date=_END, twse_responses=twse,
            tpex_responses=tpex, captured_at=_CAPTURED_AT,
        )


def test_decoder_rejects_unknown_keys_false_hash_and_duplicate_responses() -> None:
    original = _evidence()
    unknown = json.loads(original.to_json())
    unknown["source_qualification"] = True
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="fields_invalid"):
        PortfolioPeriodCalendarEvidenceV1.from_json(_resign(unknown))

    bad_hash = json.loads(original.to_json())
    bad_hash["twse_responses"][0]["source_hash"] = "sha256:" + "0" * 64
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="raw_hash_mismatch"):
        PortfolioPeriodCalendarEvidenceV1.from_json(_resign(bad_hash))

    duplicate = json.loads(original.to_json())
    duplicate["twse_responses"].append(dict(duplicate["twse_responses"][0]))
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="duplicated"):
        PortfolioPeriodCalendarEvidenceV1.from_json(_resign(duplicate))


def test_recomputed_outer_hash_cannot_hide_missing_tpex_weekday() -> None:
    original = _evidence()
    altered = json.loads(original.to_json())
    record = altered["tpex_responses"][0]
    payload = _tpex_payload()
    calendar = payload["calendar"]
    assert isinstance(calendar, dict)
    calendar["data"] = {"20260901": {"holiday": False, "holidayList": []}}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    record["payload"] = payload
    record["raw_response_base64"] = base64.b64encode(raw).decode("ascii")
    record["source_hash"] = hash_response_bytes(raw)

    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="no explicit weekday row"):
        PortfolioPeriodCalendarEvidenceV1.from_json(_resign(altered))


def test_recomputed_outer_hash_cannot_hide_payload_raw_mismatch_or_unknown_response_field() -> None:
    original = _evidence()
    changed_payload = json.loads(original.to_json())
    changed_payload["twse_responses"][0]["payload"][0]["Name"] = "假資料"
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="payload_does_not_match_raw"):
        PortfolioPeriodCalendarEvidenceV1.from_json(_resign(changed_payload))

    unknown_field = json.loads(original.to_json())
    unknown_field["tpex_responses"][0]["unreviewed"] = True
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="response_fields_invalid"):
        PortfolioPeriodCalendarEvidenceV1.from_json(_resign(unknown_field))


def test_changed_original_response_has_new_identity_and_does_not_mutate_old_evidence() -> None:
    original = _evidence()
    original_json = original.to_json()
    twse, tpex = _responses()
    corrected = _twse_payload()
    corrected[0]["Description"] = "修正後的原始回應文字。"
    twse[2026] = _response("twse", "2026", _TWSE_SOURCE, corrected, metadata={"capture": "corrected"})
    revised = PortfolioPeriodCalendarEvidenceV1.build(
        start_date=_START, end_date=_END, twse_responses=twse,
        tpex_responses=tpex, captured_at=_CAPTURED_AT,
    )

    assert revised.evidence_sha256 != original.evidence_sha256
    assert original.to_json() == original_json
    assert revised.to_dict()["twse_responses"] != json.loads(original_json)["twse_responses"]


def test_decoder_cannot_self_assert_candidate_qualification() -> None:
    evidence = _evidence()
    altered = json.loads(evidence.to_json())
    altered["performance_eligible"] = True
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error, match="qualification_flags_invalid"):
        PortfolioPeriodCalendarEvidenceV1.from_json(_resign(altered))
