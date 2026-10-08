from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, cast

import pytest

import data_module.selection_official_events as official_events_module
from data_module.selection_official_events import (
    CurrentOfficialDisposalReader,
    CurrentOfficialDisposalSourcePinV1,
    TPEX_ENDPOINT_EVIDENCE_DATE,
    TPEX_OPENAPI_SWAGGER_COMPLETED_AT,
    TPEX_OPENAPI_SWAGGER_SHA256,
    TPEX_RESPONSE_ENVELOPE_VERSION,
    TPEX_ROW_FIELDS,
    TPEX_ROW_SCHEMA_VERSION,
    SelectionOfficialEventError,
)
import scripts.refresh_current_market_status_observation as capture_module
from scripts.refresh_current_market_status_observation import SourceSpec, capture_sources


TWSE_SOURCE_ID = "twse.disposition_current"
TPEX_SOURCE_ID = "tpex.disposition_current"
TWSE_URL = "https://openapi.twse.com.tw/v1/announcement/punish"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information"
TPEX_EXACT_CAPTURE_SHA256 = (
    "sha256:25a0905e95b86046493320725927d9a2f32fa5e7c5657162363282acc36340b5"
)
TPEX_EXACT_CAPTURED_AT = datetime.fromisoformat("2026-10-04T00:21:39.057312+00:00")
TWSE_FIELDS = [
    "編號",
    "公布日期",
    "證券代號",
    "證券名稱",
    "累計",
    "處置條件",
    "處置起迄時間",
    "處置措施",
    "處置內容",
    "備註",
]
_TAIPEI = timezone(timedelta(hours=8))


class _FixedCaptureClock(datetime):
    fixed_now: datetime

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> _FixedCaptureClock:
        if tz is None:
            return cast(_FixedCaptureClock, cls.fixed_now.replace(tzinfo=None))
        return cast(_FixedCaptureClock, cls.fixed_now.astimezone(tz))


def _specs(*, markets: tuple[str, ...] = ("twse", "tpex")) -> tuple[SourceSpec, ...]:
    result: list[SourceSpec] = []
    if "twse" in markets:
        result.append(
            SourceSpec(
                TWSE_SOURCE_ID,
                TWSE_URL,
                "trading_restriction",
                "twse",
                "合成 TWSE 處置 OpenAPI",
            )
        )
    if "tpex" in markets:
        result.append(
            SourceSpec(
                TPEX_SOURCE_ID,
                TPEX_URL,
                "trading_restriction",
                "tpex",
                "合成 TPEx 處置 OpenAPI",
            )
        )
    return tuple(result)


def _roc(value: date) -> str:
    return f"{value.year - 1911:03d}/{value.month:02d}/{value.day:02d}"


def _twse_raw(
    *,
    symbol: str,
    announcement: date,
    effective_from: date,
    effective_to: date,
) -> bytes:
    row: list[object] = [
        1,
        _roc(announcement),
        symbol,
        "測試公司",
        1,
        "測試條件",
        f"{_roc(effective_from)}～{_roc(effective_to)}",
        "第一次處置",
        "合成處置內容",
        "",
    ]
    return json.dumps(
        {"title": "公布處置有價證券資訊", "fields": TWSE_FIELDS, "data": [row]},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _tpex_raw(
    *,
    symbol: str,
    announcement: date,
    effective_from: date,
    effective_to: date,
) -> bytes:
    row = {
        "CompanyName": "合成 TPEx 名稱",
        "Date": _roc(announcement),
        "DisposalCondition": "合成處置內容",
        "DispositionPeriod": f"{_roc(effective_from)}~{_roc(effective_to)}",
        "DispositionReasons": "合成處置原因",
        "SecuritiesCompanyCode": symbol,
    }
    return json.dumps([row], ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _capture(
    output_root: Path,
    *,
    specs: tuple[SourceSpec, ...] | None = None,
    twse_raw: bytes | None = None,
    tpex_raw: bytes | None = None,
    captured_at: datetime | None = None,
) -> Path:
    stamp = captured_at or datetime.now(timezone.utc)
    raw_by_url = {
        TWSE_URL: twse_raw or _twse_raw(
            symbol="1303",
            announcement=stamp.astimezone(_TAIPEI).date(),
            effective_from=stamp.astimezone(_TAIPEI).date() + timedelta(days=1),
            effective_to=stamp.astimezone(_TAIPEI).date() + timedelta(days=10),
        ),
        TPEX_URL: tpex_raw or _tpex_raw(
            symbol="5483",
            announcement=stamp.astimezone(_TAIPEI).date(),
            effective_from=stamp.astimezone(_TAIPEI).date(),
            effective_to=stamp.astimezone(_TAIPEI).date() + timedelta(days=5),
        ),
    }

    def fetcher(url: str, *, timeout: float, method: str = "GET", params: Mapping[str, object] | None = None):
        assert timeout > 0
        assert method == "GET"
        assert params == {}
        return raw_by_url[url], 200, "application/json", url, stamp, {"content-type": "application/json"}

    capture_sources(
        output_dir=output_root,
        specs=specs or _specs(),
        fetcher=fetcher,
    )
    return output_root / "current_market_status_pointer.json"


def _reader(tmp_path: Path, **kwargs: Any) -> CurrentOfficialDisposalReader:
    pointer = _capture(tmp_path / "current-status", **kwargs)
    return CurrentOfficialDisposalReader.from_pointer(pointer)


def test_twse_event_keeps_announcement_effective_and_first_observed_dates_separate(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    observed = stamp.astimezone(_TAIPEI).date()
    reader = _reader(
        tmp_path,
        specs=_specs(markets=("twse",)),
        twse_raw=_twse_raw(
            symbol="1303",
            announcement=observed,
            effective_from=observed + timedelta(days=1),
            effective_to=observed + timedelta(days=8),
        ),
        captured_at=stamp,
    )

    item = reader.get("1303", market="twse")

    assert item.state == "reported_upcoming"
    assert item.observed_date == observed
    assert item.source_data_dates == ()
    assert item.source_id == TWSE_SOURCE_ID
    assert item.source_raw_sha256 is not None
    assert item.events[0].announcement_date == observed
    assert item.events[0].effective_from == observed + timedelta(days=1)
    assert item.events[0].effective_to == observed + timedelta(days=8)
    assert item.events[0].observed_at == stamp
    assert item.events[0].official_available_at is None
    assert item.events[0].availability_basis == "announcement_date_only_first_observed_not_official_time"
    assert item.events[0].state == "announced_not_yet_effective"
    assert item.events[0].historical_pit_eligible is False


@pytest.mark.parametrize(
    ("start_delta", "end_delta", "expected"),
    [
        (1, 5, "announced_not_yet_effective"),
        (0, 5, "effective_in_reported_period"),
        (-5, 0, "effective_in_reported_period"),
        (-5, -1, "reported_period_elapsed"),
    ],
)
def test_twse_period_boundaries_are_inclusive_and_not_a_safe_no_match(
    tmp_path: Path,
    start_delta: int,
    end_delta: int,
    expected: str,
) -> None:
    stamp = datetime.now(timezone.utc)
    observed = stamp.astimezone(_TAIPEI).date()
    reader = _reader(
        tmp_path,
        specs=_specs(markets=("twse",)),
        twse_raw=_twse_raw(
            symbol="1303",
            announcement=observed,
            effective_from=observed + timedelta(days=start_delta),
            effective_to=observed + timedelta(days=end_delta),
        ),
        captured_at=stamp,
    )

    result = reader.get("1303", market="twse")

    assert result.state == {
        "announced_not_yet_effective": "reported_upcoming",
        "effective_in_reported_period": "reported_active",
        "reported_period_elapsed": "reported_elapsed_only",
    }[expected]
    assert result.events[0].state == expected
    assert result.reason_code is None
    assert result.scope == "current_only"
    assert result.historical_pit_eligible is False


def test_tpex_swagger_fields_keep_dates_separate_without_s46_t_plus_one(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    observed = stamp.astimezone(_TAIPEI).date()
    reader = _reader(
        tmp_path,
        specs=_specs(markets=("tpex",)),
        tpex_raw=_tpex_raw(
            symbol="5483",
            announcement=observed,
            effective_from=observed,
            effective_to=observed + timedelta(days=2),
        ),
        captured_at=stamp,
    )

    result = reader.get("5483", market="tpex")

    assert result.state == "reported_active"
    assert result.source_id == TPEX_SOURCE_ID
    assert result.source_data_dates == ()
    assert result.events[0].announcement_date == observed
    assert result.events[0].effective_from == observed
    assert result.events[0].effective_to == observed + timedelta(days=2)
    assert result.events[0].observed_at == stamp
    assert result.events[0].observed_date == observed
    assert result.events[0].name == "合成 TPEx 名稱"
    assert result.events[0].reason == "合成處置原因"
    assert result.events[0].measure is None
    assert result.events[0].details == "合成處置內容"
    assert result.events[0].official_available_at is None
    assert result.events[0].raw_sha256 == result.source_raw_sha256
    assert result.events[0].historical_pit_eligible is False
    assert reader.source_pin.tpex_source_schema_version == TPEX_ROW_SCHEMA_VERSION
    assert reader.source_pin.tpex_response_envelope_version == TPEX_RESPONSE_ENVELOPE_VERSION
    assert reader.source_pin.tpex_openapi_swagger_sha256 == TPEX_OPENAPI_SWAGGER_SHA256
    assert (
        reader.source_pin.tpex_openapi_swagger_completed_at
        == TPEX_OPENAPI_SWAGGER_COMPLETED_AT
    )
    assert reader.source_pin.tpex_endpoint_evidence_date == TPEX_ENDPOINT_EVIDENCE_DATE
    assert (
        CurrentOfficialDisposalSourcePinV1.from_json(reader.source_pin.to_json())
        == reader.source_pin
    )


def test_both_market_sources_read_from_one_exact_current_run(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    observed = stamp.astimezone(_TAIPEI).date()
    reader = _reader(
        tmp_path,
        specs=_specs(),
        twse_raw=_twse_raw(
            symbol="1303",
            announcement=observed,
            effective_from=observed + timedelta(days=1),
            effective_to=observed + timedelta(days=4),
        ),
        tpex_raw=_tpex_raw(
            symbol="5483",
            announcement=observed,
            effective_from=observed,
            effective_to=observed + timedelta(days=2),
        ),
        captured_at=stamp,
    )

    twse = reader.get("1303", market="twse")
    tpex = reader.get("5483", market="tpex")
    wrong_market = reader.get("5483", market="twse")

    assert len(reader.source_pin.captures) == 2
    assert twse.source_raw_sha256 != tpex.source_raw_sha256
    assert twse.state == "reported_upcoming"
    assert tpex.state == "reported_active"
    assert wrong_market.state == "unknown"
    assert wrong_market.reason_code == "no_row_absence_not_certified"
    assert wrong_market.source_id == TWSE_SOURCE_ID


def test_missing_source_or_missing_symbol_remains_unknown(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    raw = json.dumps(
        {"title": "公布處置有價證券資訊", "fields": TWSE_FIELDS, "data": []},
        ensure_ascii=False,
    ).encode("utf-8")
    reader = _reader(
        tmp_path,
        specs=_specs(markets=("twse",)),
        twse_raw=raw,
        captured_at=stamp,
    )

    absent = reader.get("2330", market="twse")
    missing_market = reader.get("5483", market="tpex")

    assert absent.state == "unknown"
    assert absent.reason_code == "no_row_absence_not_certified"
    assert missing_market.state == "unknown"
    assert missing_market.reason_code == "market_source_not_captured"
    assert absent.events == ()
    assert absent.historical_pit_eligible is False
    assert absent.observed_at is None
    assert absent.observed_date is None


def test_tpex_unknown_container_and_fields_get_named_unknown(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    raw = json.dumps(
        {"data": [{"SecuritiesCompanyCode": "5483"}]},
        ensure_ascii=False,
    ).encode("utf-8")
    reader = _reader(
        tmp_path,
        specs=_specs(markets=("tpex",)),
        tpex_raw=raw,
        captured_at=stamp,
    )

    result = reader.get("5483", market="tpex")

    assert result.state == "unknown"
    assert result.reason_code == "tpex_disposal_openapi_schema_unconfirmed"
    assert result.partial_failure is True
    assert result.source_warnings == ("tpex_disposal_openapi_schema_unconfirmed",)


def test_future_announcement_is_rejected_but_future_effective_date_is_allowed(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    observed = stamp.astimezone(_TAIPEI).date()
    future_announcement = _twse_raw(
        symbol="1303",
        announcement=observed + timedelta(days=1),
        effective_from=observed + timedelta(days=2),
        effective_to=observed + timedelta(days=5),
    )
    pointer = _capture(
        tmp_path / "future-announcement",
        specs=_specs(markets=("twse",)),
        twse_raw=future_announcement,
        captured_at=stamp,
    )
    with pytest.raises(SelectionOfficialEventError, match="future_announcement_after_observation"):
        CurrentOfficialDisposalReader.from_pointer(pointer)

    tpex_row = json.loads(
        _tpex_raw(
            symbol="5483",
            announcement=observed + timedelta(days=1),
            effective_from=observed + timedelta(days=2),
            effective_to=observed + timedelta(days=5),
        ).decode("utf-8")
    )[0]
    tpex_row["DispositionPeriod"] = "無法解析"
    tpex_pointer = _capture(
        tmp_path / "future-tpex-announcement",
        specs=_specs(markets=("tpex",)),
        tpex_raw=json.dumps([tpex_row], ensure_ascii=False).encode("utf-8"),
        captured_at=stamp,
    )
    with pytest.raises(SelectionOfficialEventError, match="future_announcement_after_observation"):
        CurrentOfficialDisposalReader.from_pointer(tpex_pointer)


def test_tpex_guessed_chinese_contract_and_field_drift_are_rejected(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    observed = stamp.astimezone(_TAIPEI).date()
    guessed_row = {
        "公告日期": _roc(observed),
        "證券代號": "5483",
        "證券名稱": "合成名稱",
        "處置起訖時間": f"{_roc(observed)}~{_roc(observed + timedelta(days=2))}",
        "處置條件": "合成條件",
        "處置措施": "合成措施",
        "處置內容": "合成內容",
    }
    old_schema_reader = _reader(
        tmp_path / "old-chinese-schema",
        specs=_specs(markets=("tpex",)),
        tpex_raw=json.dumps([guessed_row], ensure_ascii=False).encode("utf-8"),
        captured_at=stamp,
    )
    old_schema_result = old_schema_reader.get("5483", market="tpex")
    assert old_schema_result.state == "unknown"
    assert old_schema_result.reason_code == "tpex_disposal_openapi_schema_unconfirmed"

    changed_row = json.loads(
        _tpex_raw(
            symbol="5483",
            announcement=observed,
            effective_from=observed,
            effective_to=observed + timedelta(days=2),
        ).decode("utf-8")
    )
    changed_row[0]["UnexpectedField"] = "schema drift"
    drift_reader = _reader(
        tmp_path / "unexpected-field",
        specs=_specs(markets=("tpex",)),
        tpex_raw=json.dumps(changed_row, ensure_ascii=False).encode("utf-8"),
        captured_at=stamp,
    )
    drift_result = drift_reader.get("5483", market="tpex")
    assert drift_result.state == "unknown"
    assert drift_result.reason_code == "tpex_disposal_openapi_schema_unconfirmed"

    non_string_row = json.loads(
        _tpex_raw(
            symbol="5483",
            announcement=observed,
            effective_from=observed,
            effective_to=observed + timedelta(days=2),
        ).decode("utf-8")
    )
    non_string_row[0]["SecuritiesCompanyCode"] = 5483
    non_string_reader = _reader(
        tmp_path / "non-string-field",
        specs=_specs(markets=("tpex",)),
        tpex_raw=json.dumps(non_string_row, ensure_ascii=False).encode("utf-8"),
        captured_at=stamp,
    )
    non_string_result = non_string_reader.get("5483", market="tpex")
    assert non_string_result.state == "unknown"
    assert non_string_result.reason_code == "tpex_disposal_openapi_schema_unconfirmed"


def test_tpex_exact_local_capture_has_29_rows_when_enabled(
    tmp_path: Path,
) -> None:
    capture_path_text = os.environ.get("BALDR_TPEX_DISPOSITION_EXACT_CAPTURE")
    if not capture_path_text:
        pytest.skip("需明確指定本機唯讀 TPEx exact capture 才執行")
    assert capture_path_text is not None
    capture_path = Path(capture_path_text)
    raw = capture_path.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == TPEX_EXACT_CAPTURE_SHA256.removeprefix("sha256:")
    )
    decoded = json.loads(raw)
    assert isinstance(decoded, list)
    assert len(decoded) == 29
    assert all(
        isinstance(row, dict) and set(row) == set(TPEX_ROW_FIELDS) for row in decoded
    )
    assert all(type(value) is str for row in decoded for value in row.values())

    pointer = _capture(
        tmp_path / "exact-local-capture",
        specs=_specs(markets=("tpex",)),
        tpex_raw=raw,
        captured_at=TPEX_EXACT_CAPTURED_AT,
    )
    reader = CurrentOfficialDisposalReader.from_pointer(pointer)
    capture_pin = next(
        item for item in reader.source_pin.captures if item.source_id == TPEX_SOURCE_ID
    )
    assert capture_pin.raw_sha256 == TPEX_EXACT_CAPTURE_SHA256
    assert capture_pin.raw_bytes == len(raw)
    event_count = 0
    for symbol in {row["SecuritiesCompanyCode"] for row in decoded}:
        result = reader.get(symbol, market="tpex")
        event_count += len(result.events)
        assert all(event.official_available_at is None for event in result.events)
        assert all(event.observed_at == TPEX_EXACT_CAPTURED_AT for event in result.events)
        assert all(event.historical_pit_eligible is False for event in result.events)
    assert event_count == 29

    receipt_path_text = os.environ.get("BALDR_TPEX_LOCAL_EVIDENCE_PATH")
    if receipt_path_text:
        receipt_path = Path(receipt_path_text)
        receipt_path.parent.mkdir(parents=True, exist_ok=False)
        receipt_path.write_text(
            json.dumps(
                {
                    "schema_version": "tpex-disposal-exact-capture-test-receipt.v1",
                    "capture_date": TPEX_ENDPOINT_EVIDENCE_DATE,
                    "captured_at": TPEX_EXACT_CAPTURED_AT.isoformat(),
                    "raw_sha256": TPEX_EXACT_CAPTURE_SHA256,
                    "raw_bytes": len(raw),
                    "row_count": len(decoded),
                    "parsed_event_count": event_count,
                    "row_fields": list(TPEX_ROW_FIELDS),
                    "source_scope": "current_only",
                    "historical_pit_eligible": False,
                    "official_available_at": None,
                },
                ensure_ascii=True,
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def test_capture_observed_after_pointer_publication_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_at = datetime.now(timezone.utc) - timedelta(hours=1)
    captured_at = published_at + timedelta(seconds=1)
    _FixedCaptureClock.fixed_now = published_at
    monkeypatch.setattr(capture_module, "datetime", _FixedCaptureClock)
    observed = captured_at.astimezone(_TAIPEI).date()
    pointer = _capture(
        tmp_path / "future-capture",
        specs=_specs(markets=("twse",)),
        twse_raw=_twse_raw(
            symbol="1303",
            announcement=observed,
            effective_from=observed + timedelta(days=1),
            effective_to=observed + timedelta(days=4),
        ),
        captured_at=captured_at,
    )

    with pytest.raises(SelectionOfficialEventError, match="source_observed_after_pointer_publication"):
        CurrentOfficialDisposalReader.from_pointer(pointer)


def test_self_consistent_future_capture_is_rejected_by_default_read_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    future = datetime.now(timezone.utc) + timedelta(days=2)
    _FixedCaptureClock.fixed_now = future
    monkeypatch.setattr(capture_module, "datetime", _FixedCaptureClock)
    observed_date = future.astimezone(_TAIPEI).date()
    pointer = _capture(
        tmp_path / "future-self-consistent-capture",
        specs=_specs(markets=("twse",)),
        twse_raw=_twse_raw(
            symbol="1303",
            announcement=observed_date,
            effective_from=observed_date + timedelta(days=1),
            effective_to=observed_date + timedelta(days=4),
        ),
        captured_at=future,
    )
    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    snapshot = json.loads(
        (pointer.parent / pointer_payload["snapshot_path"]).read_text(encoding="utf-8")
    )
    source_capture = next(
        item
        for item in snapshot["source_captures"]
        if item["source_id"] == TWSE_SOURCE_ID
    )
    assert pointer_payload["published_at"] == future.isoformat()
    assert snapshot["observed_at"] == future.isoformat()
    assert source_capture["captured_at"] == future.isoformat()

    with pytest.raises(
        SelectionOfficialEventError,
        match="pointer_published_after_read_cutoff",
    ):
        CurrentOfficialDisposalReader.from_pointer(pointer)


def test_from_exact_cutoff_enforces_inclusive_timestamp_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    historical = datetime.now(timezone.utc) - timedelta(hours=1)
    _FixedCaptureClock.fixed_now = historical
    monkeypatch.setattr(capture_module, "datetime", _FixedCaptureClock)
    observed_date = historical.astimezone(_TAIPEI).date()
    pointer = _capture(
        tmp_path / "historical-pinned-capture",
        specs=_specs(markets=("twse",)),
        twse_raw=_twse_raw(
            symbol="1303",
            announcement=observed_date,
            effective_from=observed_date,
            effective_to=observed_date + timedelta(days=2),
        ),
        captured_at=historical,
    )
    source_pin = CurrentOfficialDisposalReader.from_pointer(pointer).source_pin

    with pytest.raises(
        SelectionOfficialEventError,
        match="pointer_published_after_read_cutoff",
    ):
        CurrentOfficialDisposalReader.from_exact(
            source_pin,
            cutoff_at=historical - timedelta(microseconds=1),
        )

    reopened = CurrentOfficialDisposalReader.from_exact(
        source_pin,
        cutoff_at=historical,
    )
    assert reopened.get("1303", market="twse").events[0].observed_at == historical
    assert reopened.source_pin == source_pin


@pytest.mark.parametrize("entrypoint", ("pointer", "exact"))
@pytest.mark.parametrize("invalid_cutoff", ("naive", "non_datetime", "future"))
def test_reader_rejects_invalid_cutoff_values(
    tmp_path: Path,
    entrypoint: str,
    invalid_cutoff: str,
) -> None:
    pointer = _capture(
        tmp_path / "invalid-cutoff-capture",
        specs=_specs(markets=("twse",)),
    )
    source_pin = CurrentOfficialDisposalReader.from_pointer(pointer).source_pin
    if invalid_cutoff == "naive":
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
        expected_error = "read_cutoff_must_be_aware_datetime"
    elif invalid_cutoff == "non_datetime":
        cutoff = cast(datetime, "not a datetime")
        expected_error = "read_cutoff_must_be_aware_datetime"
    else:
        cutoff = datetime.now(timezone.utc) + timedelta(days=1)
        expected_error = "read_cutoff_after_read_now"

    with pytest.raises(SelectionOfficialEventError, match=expected_error):
        if entrypoint == "pointer":
            CurrentOfficialDisposalReader.from_pointer(pointer, cutoff_at=cutoff)
        else:
            CurrentOfficialDisposalReader.from_exact(source_pin, cutoff_at=cutoff)


@pytest.mark.parametrize("entrypoint", ("pointer", "exact"))
def test_reader_samples_default_utc_clock_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
) -> None:
    pointer = _capture(
        tmp_path / "single-read-clock-capture",
        specs=_specs(markets=("twse",)),
    )
    source_pin = CurrentOfficialDisposalReader.from_pointer(pointer).source_pin
    sampled = datetime.now(timezone.utc)
    calls: list[datetime] = []

    def fixed_read_now() -> datetime:
        calls.append(sampled)
        return sampled

    monkeypatch.setattr(official_events_module, "_read_now_utc", fixed_read_now)
    if entrypoint == "pointer":
        CurrentOfficialDisposalReader.from_pointer(pointer)
    else:
        CurrentOfficialDisposalReader.from_exact(source_pin)
    assert calls == [sampled]


def test_exact_pin_reopens_old_run_after_pointer_moves_and_in_fresh_process(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    observed = stamp.astimezone(_TAIPEI).date()
    output_root = tmp_path / "same-output-root"
    old_pointer = _capture(
        output_root,
        specs=_specs(markets=("twse",)),
        twse_raw=_twse_raw(
            symbol="1303",
            announcement=observed,
            effective_from=observed + timedelta(days=1),
            effective_to=observed + timedelta(days=4),
        ),
        captured_at=stamp,
    )
    old_reader = CurrentOfficialDisposalReader.from_pointer(old_pointer)
    old_pin = old_reader.source_pin
    old_result = old_reader.get("1303", market="twse")
    new_stamp = datetime.now(timezone.utc)
    new_observed = new_stamp.astimezone(_TAIPEI).date()
    _capture(
        output_root,
        specs=_specs(markets=("twse",)),
        twse_raw=_twse_raw(
            symbol="1304",
            announcement=new_observed,
            effective_from=new_observed,
            effective_to=new_observed + timedelta(days=2),
        ),
        captured_at=new_stamp,
    )

    reopened = CurrentOfficialDisposalReader.from_exact(old_pin)
    reopened_result = reopened.get("1303", market="twse")
    assert reopened_result == old_result
    assert reopened.get("1304", market="twse").state == "unknown"

    pin_path = tmp_path / "saved-source-pin.json"
    pin_path.write_text(old_pin.to_json(), encoding="utf-8")
    code = (
        "import json, sys; "
        "from pathlib import Path; "
        "from data_module.selection_official_events import CurrentOfficialDisposalReader, CurrentOfficialDisposalSourcePinV1; "
        "pin = CurrentOfficialDisposalSourcePinV1.from_json(Path(sys.argv[1]).read_text(encoding='utf-8')); "
        "obs = CurrentOfficialDisposalReader.from_exact(pin).get('1303', market='twse'); "
        "print(obs.state + '|' + obs.events[0].raw_sha256)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code, str(pin_path)],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.stdout.strip() == f"reported_upcoming|{old_result.events[0].raw_sha256}"


def test_exact_pin_rejects_raw_tamper_and_hardlink(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    observed = stamp.astimezone(_TAIPEI).date()
    pointer = _capture(
        tmp_path / "tamper-root",
        specs=_specs(markets=("twse",)),
        twse_raw=_twse_raw(
            symbol="1303",
            announcement=observed,
            effective_from=observed + timedelta(days=1),
            effective_to=observed + timedelta(days=4),
        ),
        captured_at=stamp,
    )
    pin = CurrentOfficialDisposalReader.from_pointer(pointer).source_pin
    twse_capture = pin.captures[0]
    assert twse_capture.raw_relative_path is not None
    raw_path = Path(pin.output_root).joinpath(*twse_capture.raw_relative_path.split("/"))
    alias_path = tmp_path / "raw-hardlink.bin"
    try:
        os.link(raw_path, alias_path)
    except (OSError, NotImplementedError):
        pytest.skip("此測試檔案系統不支援 hard link")
    with pytest.raises(SelectionOfficialEventError, match="raw_source_physical_link_count_invalid"):
        CurrentOfficialDisposalReader.from_exact(pin)
    alias_path.unlink()

    raw_path.write_bytes(raw_path.read_bytes() + b"tamper")
    with pytest.raises(SelectionOfficialEventError, match="raw_source_hash_or_size_mismatch"):
        CurrentOfficialDisposalReader.from_exact(pin)


def test_pointer_path_traversal_and_duplicate_capture_are_rejected(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    observed = stamp.astimezone(_TAIPEI).date()
    pointer = _capture(
        tmp_path / "path-root",
        specs=_specs(markets=("twse",)),
        twse_raw=_twse_raw(
            symbol="1303",
            announcement=observed,
            effective_from=observed,
            effective_to=observed + timedelta(days=2),
        ),
        captured_at=stamp,
    )
    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    pointer_payload["snapshot_path"] = "../outside/snapshot.json"
    pointer.write_text(json.dumps(pointer_payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SelectionOfficialEventError, match="current_status_pointer_path_invalid"):
        CurrentOfficialDisposalReader.from_pointer(pointer)

    duplicate_pointer = _capture(
        tmp_path / "duplicate-root",
        specs=(
            SourceSpec(TWSE_SOURCE_ID, TWSE_URL, "trading_restriction", "twse", "重複一"),
            SourceSpec(TWSE_SOURCE_ID, TWSE_URL, "trading_restriction", "twse", "重複二"),
        ),
        twse_raw=_twse_raw(
            symbol="1303",
            announcement=observed,
            effective_from=observed,
            effective_to=observed + timedelta(days=2),
        ),
    )
    with pytest.raises(SelectionOfficialEventError, match="duplicate_disposal_source_capture"):
        CurrentOfficialDisposalReader.from_pointer(duplicate_pointer)


def test_source_market_mismatch_is_rejected(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    observed = stamp.astimezone(_TAIPEI).date()
    pointer = _capture(
        tmp_path / "wrong-market",
        specs=(SourceSpec(TPEX_SOURCE_ID, TPEX_URL, "trading_restriction", "twse", "錯誤市場"),),
        tpex_raw=_tpex_raw(
            symbol="5483",
            announcement=observed,
            effective_from=observed,
            effective_to=observed + timedelta(days=2),
        ),
        captured_at=stamp,
    )
    with pytest.raises(SelectionOfficialEventError, match="disposal_source_market_or_endpoint_mismatch"):
        CurrentOfficialDisposalReader.from_pointer(pointer)


def test_manifest_capture_projection_tamper_is_rejected(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    observed = stamp.astimezone(_TAIPEI).date()
    pointer = _capture(
        tmp_path / "manifest-root",
        specs=_specs(markets=("twse",)),
        twse_raw=_twse_raw(
            symbol="1303",
            announcement=observed,
            effective_from=observed,
            effective_to=observed + timedelta(days=2),
        ),
        captured_at=stamp,
    )
    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    manifest_path = pointer.parent / pointer_payload["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["raw_sources"][0]["raw_sha256"] = "sha256:" + "0" * 64
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    pointer_payload["manifest_sha256"] = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    pointer.write_text(json.dumps(pointer_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(SelectionOfficialEventError, match="manifest_capture_projection_mismatch"):
        CurrentOfficialDisposalReader.from_pointer(pointer)


def test_pin_decoder_rejects_identity_or_historical_scope_changes(tmp_path: Path) -> None:
    stamp = datetime.now(timezone.utc)
    observed = stamp.astimezone(_TAIPEI).date()
    reader = _reader(
        tmp_path,
        specs=_specs(markets=("twse",)),
        twse_raw=_twse_raw(
            symbol="1303",
            announcement=observed,
            effective_from=observed,
            effective_to=observed + timedelta(days=2),
        ),
        captured_at=stamp,
    )
    payload = reader.source_pin.to_dict()
    payload["historical_pit_eligible"] = True
    with pytest.raises(SelectionOfficialEventError, match="source_pin_identity_invalid"):
        CurrentOfficialDisposalSourcePinV1.from_dict(payload)
    payload = reader.source_pin.to_dict()
    payload["run_id"] = "other-run"
    with pytest.raises(SelectionOfficialEventError, match="source_pin_identity_invalid"):
        CurrentOfficialDisposalSourcePinV1.from_dict(payload)
    payload = reader.source_pin.to_dict()
    payload["tpex_source_schema_version"] = "unverified-new-contract"
    with pytest.raises(SelectionOfficialEventError, match="source_pin_identity_invalid"):
        CurrentOfficialDisposalSourcePinV1.from_dict(payload)
