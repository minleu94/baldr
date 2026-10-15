"""Build a candidate-only TWSE/TPEX official trading-calendar bundle.

This module is deliberately separate from the prospective clock planner.  It
normalizes already captured official responses (or a small, explicitly
confirmed network capture) into the planner's ``official-trading-calendar-
bundle.v1`` shape.  It never creates a clock, changes a controlled path, or
writes market data.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unicodedata
from typing import TYPE_CHECKING, Any, Callable

from data_module.official_phase3c_fetcher import safe_request
from data_module.prospective_formal_clock import payload_hash
if TYPE_CHECKING:
    from data_module.tpex_trading_date_html_v1 import TpexTradingDateRowV1
    from data_module.official_calendar_transport_v1 import OfficialCalendarJsonTransportV1
    from data_module.tpex_annual_calendar_transport_v1 import OfficialCalendarTpexAnnualJsonTransportV1


OFFICIAL_CALENDAR_BUNDLE_SCHEMA_VERSION = "official-trading-calendar-bundle.v1"
TWSE_HOLIDAY_SCHEDULE_URL = (
    "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
)
TPEX_MARKET_CALENDAR_URL = "https://info.tpex.org.tw/api/mktCalendar"
TPEX_ANNUAL_TRADING_DATE_URL = "https://www.tpex.org.tw/www/zh-tw/bulletin/tradingDate"
MAX_CAPTURE_DAYS = 93
MAX_FIXTURE_BYTES = 4 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPEN_MARKERS = ("開始交易", "最後交易", "恢復交易", "照常交易")
_DATE_KEY_PATTERN = re.compile(r"^\d{8}$")


class OfficialCalendarBundleError(ValueError):
    """Official calendar input is malformed or insufficient for a bundle."""


@dataclass(frozen=True)
class CapturedCalendarResponse:
    """One immutable response and the fingerprint of its captured raw bytes.

    ``raw_bytes`` is optional for compatibility with older in-memory callers,
    but every network capture and fixture loaded by this module supplies it.
    A response hash is never reconstructed from a decoded/re-encoded payload.
    """

    kind: str
    key: str
    source: str
    source_hash: str
    payload: object
    raw_bytes: bytes | None = None
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"twse", "tpex"}:
            raise OfficialCalendarBundleError("response kind must be twse or tpex")
        if not self.key.strip():
            raise OfficialCalendarBundleError("response key must be non-empty")
        if not self.source.strip():
            raise OfficialCalendarBundleError("response source must be non-empty")
        if SHA256_PATTERN.fullmatch(self.source_hash) is None:
            raise OfficialCalendarBundleError(
                "response source_hash must be sha256: plus 64 lowercase hex"
            )
        if self.raw_bytes is not None:
            if not isinstance(self.raw_bytes, bytes) or not self.raw_bytes:
                raise OfficialCalendarBundleError(
                    "response raw_bytes must be non-empty bytes"
                )
            if hash_response_bytes(self.raw_bytes) != self.source_hash:
                raise OfficialCalendarBundleError(
                    "response source_hash does not match captured raw_bytes"
                )
        if self.metadata is not None and not isinstance(self.metadata, Mapping):
            raise OfficialCalendarBundleError("response metadata must be an object")


def hash_response_bytes(raw: bytes) -> str:
    """Return the evidence hash for the bytes actually captured."""

    return "sha256:" + hashlib.sha256(raw).hexdigest()


def build_official_calendar_bundle(
    *,
    start_date: date,
    end_date: date,
    twse_responses: Mapping[int, CapturedCalendarResponse],
    tpex_responses: Mapping[str, CapturedCalendarResponse],
    capture_mode: str = "fixture_only",
    network_enabled: bool = False,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    """Normalize captured annual/monthly responses into a planner bundle.

    TWSE's annual endpoint lists holidays, so a weekday absent from a valid
    annual response is an official open day under the existing project policy.
    TPEX's monthly endpoint is expected to contain every weekday in that
    month; a missing weekday is therefore rejected rather than guessed.
    """

    _validate_date_range(start_date, end_date)
    if not isinstance(twse_responses, Mapping) or not twse_responses:
        raise OfficialCalendarBundleError("twse_responses must be non-empty")
    if not isinstance(tpex_responses, Mapping) or not tpex_responses:
        raise OfficialCalendarBundleError("tpex_responses must be non-empty")
    if capture_mode not in {"fixture_only", "bounded_network", "mixed"}:
        raise OfficialCalendarBundleError("capture_mode is invalid")
    if not isinstance(network_enabled, bool):
        raise OfficialCalendarBundleError("network_enabled must be boolean")
    if network_enabled and capture_mode == "fixture_only":
        raise OfficialCalendarBundleError(
            "fixture_only capture cannot claim network_enabled"
        )

    parsed_twse: dict[int, dict[date, bool]] = {}
    for year_key, response in twse_responses.items():
        if not isinstance(year_key, int) or isinstance(year_key, bool):
            raise OfficialCalendarBundleError("TWSE response keys must be years")
        _validate_response(response, "twse", str(year_key))
        parsed_year, schedule = _parse_twse_schedule(response.payload)
        if parsed_year != year_key:
            raise OfficialCalendarBundleError(
                f"TWSE response key/year mismatch: {year_key} != {parsed_year}"
            )
        parsed_twse[year_key] = schedule

    parsed_tpex: dict[str, dict[date, bool]] = {}
    for month_key, response in tpex_responses.items():
        if not isinstance(month_key, str) or not re.fullmatch(r"\d{6}", month_key):
            raise OfficialCalendarBundleError(
                "TPEX response keys must be YYYYMM text"
            )
        _validate_response(response, "tpex", month_key)
        parsed_month, calendar = _parse_tpex_calendar(response.payload)
        if parsed_month != month_key:
            raise OfficialCalendarBundleError(
                f"TPEX response key/month mismatch: {month_key} != {parsed_month}"
            )
        parsed_tpex[month_key] = calendar

    days: list[dict[str, object]] = []
    current = start_date
    while current <= end_date:
        year = current.year
        month_key = current.strftime("%Y%m")
        twse_response = twse_responses.get(year)
        tpex_response = tpex_responses.get(month_key)
        if twse_response is None:
            raise OfficialCalendarBundleError(
                f"missing TWSE annual response for {year}"
            )
        if tpex_response is None:
            raise OfficialCalendarBundleError(
                f"missing TPEX monthly response for {month_key}"
            )

        is_weekend = current.weekday() >= 5
        twse_trading = False if is_weekend else parsed_twse[year].get(current, True)
        tpex_trading = parsed_tpex[month_key].get(current)
        if tpex_trading is None:
            if not is_weekend:
                raise OfficialCalendarBundleError(
                    f"TPEX response has no explicit weekday row for {current.isoformat()}"
                )
            tpex_trading = False

        days.append(
            {
                "date": current.isoformat(),
                "twse": {
                    "is_trading_day": twse_trading,
                    "source": twse_response.source,
                    "source_hash": twse_response.source_hash,
                },
                "tpex": {
                    "is_trading_day": tpex_trading,
                    "source": tpex_response.source,
                    "source_hash": tpex_response.source_hash,
                },
            }
        )
        current += timedelta(days=1)

    captured_at_value = captured_at or datetime.now(timezone.utc)
    if (
        not isinstance(captured_at_value, datetime)
        or captured_at_value.tzinfo is None
        or captured_at_value.utcoffset() is None
    ):
        raise OfficialCalendarBundleError("captured_at must include timezone")

    bundle: dict[str, object] = {
        "schema_version": OFFICIAL_CALENDAR_BUNDLE_SCHEMA_VERSION,
        "range": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "day_count": len(days),
        },
        "generated_at_utc": captured_at_value.astimezone(timezone.utc).isoformat(),
        "capture_mode": capture_mode,
        "network_enabled": network_enabled,
        "candidate_only": True,
        "formal_clock_created": False,
        "source_responses": {
            "twse": [
                _response_source_record(response, identity_field="year", identity=year)
                for year, response in sorted(twse_responses.items())
            ],
            "tpex": [
                _response_source_record(response, identity_field="month", identity=month)
                for month, response in sorted(tpex_responses.items())
            ],
        },
        "days": days,
        "safety": {
            "read_only": True,
            "market_db_written": False,
            "formal_paths_written": False,
            "formal_oos_allowed": False,
            "production_scheduler_allowed": False,
            "broker_order_allowed": False,
            "secret_values_emitted": False,
        },
    }
    bundle["bundle_hash"] = payload_hash(bundle)
    return bundle


def load_fixture_response(path: Path, *, kind: str) -> CapturedCalendarResponse:
    """Read one bounded raw fixture without writing or contacting the network."""

    resolved = path.expanduser().resolve()
    raw = resolved.read_bytes()
    if len(raw) > MAX_FIXTURE_BYTES:
        raise OfficialCalendarBundleError(
            f"fixture exceeds {MAX_FIXTURE_BYTES} bytes: {resolved}"
        )
    try:
        payload: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OfficialCalendarBundleError(
            f"fixture must be UTF-8 JSON: {resolved}"
        ) from error

    if kind == "twse":
        year, _ = _parse_twse_schedule(payload)
        roc_year = year - 1911
        source = f"{TWSE_HOLIDAY_SCHEDULE_URL}?queryYear={roc_year}"
        key = str(year)
    elif kind == "tpex":
        month, _ = _parse_tpex_calendar(payload)
        source = f"{TPEX_MARKET_CALENDAR_URL}?ym={month}&lang=zh-tw"
        key = month
    else:
        raise OfficialCalendarBundleError("fixture kind must be twse or tpex")
    return CapturedCalendarResponse(
        kind=kind,
        key=key,
        source=f"{source} (fixture:{resolved})",
        source_hash=hash_response_bytes(raw),
        payload=payload,
        raw_bytes=raw,
        metadata={
            "capture_mode": "fixture_only",
            "fixture_path": str(resolved),
        },
    )


def write_candidate_bundle(path: Path, bundle: Mapping[str, object]) -> str:
    """Create a candidate bundle once, restricted to the OS TEMP directory."""

    resolved = path.expanduser().resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    try:
        resolved.relative_to(temp_root)
    except ValueError as error:
        raise OfficialCalendarBundleError(
            "candidate bundle output must be under the operating-system TEMP directory"
        ) from error
    if not resolved.parent.exists():
        raise OfficialCalendarBundleError(
            "candidate bundle output parent directory must already exist"
        )
    if not isinstance(bundle, Mapping):
        raise OfficialCalendarBundleError("bundle must be an object")
    encoded = (
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        with resolved.open("xb") as handle:
            handle.write(encoded)
    except FileExistsError as error:
        raise OfficialCalendarBundleError(
            "candidate bundle output already exists; choose a new path"
        ) from error
    return hash_response_bytes(encoded)


def write_raw_response_evidence(
    root: Path,
    responses: Mapping[str, CapturedCalendarResponse],
) -> dict[str, object]:
    """Persist the exact response bytes and metadata in a create-only bundle.

    The raw files are written byte-for-byte from ``CapturedCalendarResponse``.
    This function intentionally has no payload serialization fallback, and it
    is restricted to the operating-system TEMP directory like the candidate
    bundle writer.  The returned manifest can be bound into the candidate
    bundle after all sidecars have been written.
    """

    resolved = root.expanduser().resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    try:
        resolved.relative_to(temp_root)
    except ValueError as error:
        raise OfficialCalendarBundleError(
            "raw response evidence output must be under the operating-system TEMP directory"
        ) from error
    if not resolved.parent.exists():
        raise OfficialCalendarBundleError(
            "raw response evidence parent directory must already exist"
        )
    if resolved.exists():
        raise OfficialCalendarBundleError(
            "raw response evidence output already exists; choose a new path"
        )
    if not isinstance(responses, Mapping) or not responses:
        raise OfficialCalendarBundleError("raw response evidence responses must be non-empty")

    try:
        resolved.mkdir()
    except FileExistsError as error:
        raise OfficialCalendarBundleError(
            "raw response evidence output already exists; choose a new path"
        ) from error

    entries: list[dict[str, object]] = []
    for label, response in sorted(responses.items(), key=lambda item: str(item[0])):
        if not isinstance(response, CapturedCalendarResponse):
            raise OfficialCalendarBundleError(
                f"raw response evidence {label} has invalid response type"
            )
        raw = response.raw_bytes
        if raw is None:
            raise OfficialCalendarBundleError(
                f"raw response evidence {label} lacks captured raw bytes"
            )
        raw_hash = hash_response_bytes(raw)
        if raw_hash != response.source_hash:
            raise OfficialCalendarBundleError(
                f"raw response evidence {label} hash does not match source_hash"
            )
        safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", response.key)
        raw_name = f"{response.kind}_{safe_key}.response.bin"
        metadata_name = f"{response.kind}_{safe_key}.metadata.json"
        raw_path = resolved / raw_name
        metadata_path = resolved / metadata_name
        metadata = {
            "schema_version": "official-calendar-raw-response.v1",
            "kind": response.kind,
            "key": response.key,
            "source": response.source,
            "source_hash": response.source_hash,
            "raw_file": raw_name,
            "raw_size_bytes": len(raw),
            "metadata": _json_safe_mapping(response.metadata),
            "read_only": True,
            "formal_clock_created": False,
            "formal_oos_allowed": False,
            "production_scheduler_allowed": False,
            "broker_order_allowed": False,
        }
        try:
            with raw_path.open("xb") as handle:
                handle.write(raw)
            metadata_bytes = (
                json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            with metadata_path.open("xb") as handle:
                handle.write(metadata_bytes)
        except FileExistsError as error:
            raise OfficialCalendarBundleError(
                "raw response evidence file already exists; choose a new path"
            ) from error
        entries.append(
            {
                "label": str(label),
                "kind": response.kind,
                "key": response.key,
                "source": response.source,
                "source_hash": response.source_hash,
                "raw_file": raw_name,
                "raw_file_hash": hash_response_bytes(raw),
                "raw_size_bytes": len(raw),
                "metadata_file": metadata_name,
                "metadata_file_hash": hash_response_bytes(metadata_bytes),
            }
        )

    manifest: dict[str, object] = {
        "schema_version": "official-calendar-raw-evidence-manifest.v1",
        "entries": entries,
        "entry_count": len(entries),
        "safety": {
            "read_only": True,
            "market_db_written": False,
            "formal_paths_written": False,
            "formal_clock_created": False,
            "formal_oos_allowed": False,
            "production_scheduler_allowed": False,
            "broker_order_allowed": False,
            "secret_values_emitted": False,
        },
    }
    manifest["manifest_hash"] = payload_hash(manifest)
    manifest_path = resolved / "manifest.json"
    encoded = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        with manifest_path.open("xb") as handle:
            handle.write(encoded)
    except FileExistsError as error:
        raise OfficialCalendarBundleError(
            "raw response evidence manifest already exists; choose a new path"
        ) from error
    return {
        "schema_version": str(manifest["schema_version"]),
        "manifest_path": str(manifest_path),
        "manifest_file_hash": hash_response_bytes(encoded),
        "manifest_hash": str(manifest["manifest_hash"]),
        "entry_count": len(entries),
        "entries": entries,
    }


def fetch_network_responses(
    *,
    years: set[int],
    months: set[str],
    request_fn: Callable[..., Any] = safe_request,
) -> tuple[dict[int, CapturedCalendarResponse], dict[str, CapturedCalendarResponse]]:
    """Fetch only the bounded annual/monthly official endpoints requested."""

    twse: dict[int, CapturedCalendarResponse] = {}
    for year in sorted(years):
        roc_year = year - 1911
        if roc_year <= 0:
            raise OfficialCalendarBundleError(f"invalid TWSE year: {year}")
        response = request_fn(
            TWSE_HOLIDAY_SCHEDULE_URL,
            params={"queryYear": str(roc_year)},
            timeout_seconds=10,
            max_attempts=1,
        )
        payload = _response_json(response, f"TWSE {year}")
        raw = _response_bytes(response, payload)
        parsed_year, _ = _parse_twse_schedule(payload)
        if parsed_year != year:
            raise OfficialCalendarBundleError(
                f"TWSE response year mismatch: {year} != {parsed_year}"
            )
        twse[year] = CapturedCalendarResponse(
            kind="twse",
            key=str(year),
            source=f"{TWSE_HOLIDAY_SCHEDULE_URL}?queryYear={roc_year}",
            source_hash=hash_response_bytes(raw),
            payload=payload,
            raw_bytes=raw,
            metadata=_response_metadata(
                response,
                source=f"{TWSE_HOLIDAY_SCHEDULE_URL}?queryYear={roc_year}",
                params={"queryYear": str(roc_year)},
            ),
        )

    tpex: dict[str, CapturedCalendarResponse] = {}
    for month in sorted(months):
        response = request_fn(
            TPEX_MARKET_CALENDAR_URL,
            params={"ym": month, "lang": "zh-tw"},
            timeout_seconds=10,
            max_attempts=1,
        )
        payload = _response_json(response, f"TPEX {month}")
        raw = _response_bytes(response, payload)
        parsed_month, _ = _parse_tpex_calendar(payload)
        if parsed_month != month:
            raise OfficialCalendarBundleError(
                f"TPEX response month mismatch: {month} != {parsed_month}"
            )
        tpex[month] = CapturedCalendarResponse(
            kind="tpex",
            key=month,
            source=f"{TPEX_MARKET_CALENDAR_URL}?ym={month}&lang=zh-tw",
            source_hash=hash_response_bytes(raw),
            payload=payload,
            raw_bytes=raw,
            metadata=_response_metadata(
                response,
                source=f"{TPEX_MARKET_CALENDAR_URL}?ym={month}&lang=zh-tw",
                params={"ym": month, "lang": "zh-tw"},
            ),
        )
    return twse, tpex


def _validate_date_range(start_date: date, end_date: date) -> None:
    if type(start_date) is not date or type(end_date) is not date:
        raise OfficialCalendarBundleError("start_date/end_date must be dates")
    if end_date < start_date:
        raise OfficialCalendarBundleError("end_date must not precede start_date")
    span = (end_date - start_date).days + 1
    if span > MAX_CAPTURE_DAYS:
        raise OfficialCalendarBundleError(
            f"capture range cannot exceed {MAX_CAPTURE_DAYS} calendar days"
        )


def _validate_response(
    response: CapturedCalendarResponse,
    expected_kind: str,
    expected_key: str,
) -> None:
    if not isinstance(response, CapturedCalendarResponse):
        raise OfficialCalendarBundleError(
            f"{expected_kind} response {expected_key} has invalid type"
        )
    if response.kind != expected_kind or response.key != expected_key:
        raise OfficialCalendarBundleError(
            f"{expected_kind} response identity mismatch: {expected_key}"
        )


def _parse_twse_schedule(payload: object) -> tuple[int, dict[date, bool]]:
    if not isinstance(payload, list) or not payload:
        raise OfficialCalendarBundleError(
            "TWSE holidaySchedule payload must be a non-empty array"
        )
    schedule: dict[date, bool] = {}
    parsed_year: int | None = None
    valid_rows = 0
    for index, raw_row in enumerate(payload):
        if not isinstance(raw_row, Mapping) or "Date" not in raw_row:
            raise OfficialCalendarBundleError(
                f"TWSE holidaySchedule row {index} lacks Date"
            )
        row_date = _parse_roc_date(raw_row["Date"], index=index)
        if parsed_year is None:
            parsed_year = row_date.year
        elif row_date.year != parsed_year:
            raise OfficialCalendarBundleError(
                "TWSE holidaySchedule fixture contains multiple years"
            )
        description = " ".join(
            str(raw_row.get(field, ""))
            for field in ("Name", "Description")
        )
        schedule[row_date] = schedule.get(row_date, False) or any(
            marker in description for marker in _OPEN_MARKERS
        )
        valid_rows += 1
    if parsed_year is None or valid_rows == 0:
        raise OfficialCalendarBundleError("TWSE holidaySchedule has no valid rows")
    return parsed_year, schedule


def _parse_tpex_calendar(payload: object) -> tuple[str, dict[date, bool]]:
    if not isinstance(payload, Mapping):
        raise OfficialCalendarBundleError("TPEX calendar payload must be an object")
    calendar = payload.get("calendar")
    if not isinstance(calendar, Mapping):
        raise OfficialCalendarBundleError("TPEX calendar payload lacks calendar")
    status = payload.get("status", calendar.get("status", ""))
    if str(status).casefold() != "success":
        raise OfficialCalendarBundleError("TPEX calendar status must be success")
    raw_data = calendar.get("data")
    if not isinstance(raw_data, Mapping) or not raw_data:
        raise OfficialCalendarBundleError("TPEX calendar data must be non-empty")

    month: str | None = None
    parsed: dict[date, bool] = {}
    for raw_key, raw_row in raw_data.items():
        key = str(raw_key)
        if _DATE_KEY_PATTERN.fullmatch(key) is None:
            raise OfficialCalendarBundleError(
                f"TPEX calendar contains invalid date key: {key}"
            )
        try:
            row_date = datetime.strptime(key, "%Y%m%d").date()
        except ValueError as error:
            raise OfficialCalendarBundleError(
                f"TPEX calendar contains invalid date: {key}"
            ) from error
        row_month = row_date.strftime("%Y%m")
        if month is None:
            month = row_month
        elif row_month != month:
            raise OfficialCalendarBundleError(
                "TPEX calendar fixture contains multiple months"
            )
        if not isinstance(raw_row, Mapping):
            raise OfficialCalendarBundleError(f"TPEX row {key} must be an object")
        holiday = raw_row.get("holiday")
        if not isinstance(holiday, bool):
            raise OfficialCalendarBundleError(
                f"TPEX row {key}.holiday must be boolean"
            )
        holiday_list = raw_row.get("holidayList", [])
        if not isinstance(holiday_list, list):
            raise OfficialCalendarBundleError(
                f"TPEX row {key}.holidayList must be an array"
            )
        parsed[row_date] = not holiday
    if month is None or not parsed:
        raise OfficialCalendarBundleError("TPEX calendar has no valid rows")
    return month, parsed


def _parse_roc_date(value: object, *, index: int) -> date:
    digits = re.sub(r"\D", "", str(value))
    if len(digits) != 7:
        raise OfficialCalendarBundleError(
            f"TWSE holidaySchedule row {index} Date must be 7 ROC digits"
        )
    try:
        return date(
            int(digits[:3]) + 1911,
            int(digits[3:5]),
            int(digits[5:7]),
        )
    except ValueError as error:
        raise OfficialCalendarBundleError(
            f"TWSE holidaySchedule row {index} Date is invalid"
        ) from error


def _response_json(response: Any, label: str) -> object:
    try:
        payload = response.json()
    except Exception as error:  # noqa: BLE001 - external payload boundary
        raise OfficialCalendarBundleError(f"{label} response is not valid JSON") from error
    return payload


def _response_bytes(response: Any, payload: object) -> bytes:
    raw = getattr(response, "content", None)
    if isinstance(raw, bytes) and raw:
        return raw
    # ``payload`` is intentionally unused.  Re-serializing a decoded object
    # changes whitespace/key order/encoding and cannot prove custody of the
    # bytes returned by the official endpoint.
    del payload
    raise OfficialCalendarBundleError(
        "official response content bytes are unavailable; raw custody cannot be proven"
    )


def _response_source_record(
    response: CapturedCalendarResponse,
    *,
    identity_field: str,
    identity: int | str,
) -> dict[str, object]:
    record: dict[str, object] = {
        identity_field: identity,
        "source": response.source,
        "source_hash": response.source_hash,
    }
    raw = response.raw_bytes
    if raw is not None:
        raw_hash = hash_response_bytes(raw)
        if raw_hash != response.source_hash:
            raise OfficialCalendarBundleError(
                f"{response.kind} {response.key} raw bytes do not match source_hash"
            )
        record["raw_response"] = {
            "encoding": "base64",
            "sha256": raw_hash,
            "size_bytes": len(raw),
            "content_base64": base64.b64encode(raw).decode("ascii"),
            "metadata": _json_safe_mapping(response.metadata),
        }
    return record


def _json_safe_mapping(value: Mapping[str, object] | None) -> dict[str, object]:
    """Keep response metadata JSON-safe without copying response bodies."""

    if value is None:
        return {}
    result: dict[str, object] = {}
    for key, item in value.items():
        name = str(key)
        if item is None or isinstance(item, (str, int, float, bool)):
            result[name] = item
        elif isinstance(item, Mapping):
            result[name] = _json_safe_mapping(item)
        elif isinstance(item, (list, tuple)):
            result[name] = [
                _json_safe_value(entry)
                for entry in item
            ]
        else:
            result[name] = str(item)
    return result


def _json_safe_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    return str(value)


def _response_metadata(
    response: Any,
    *,
    source: str,
    params: Mapping[str, str],
) -> dict[str, object]:
    """Capture non-secret HTTP provenance beside the exact raw response."""

    headers = getattr(response, "headers", None)
    selected_headers: dict[str, str] = {}
    if isinstance(headers, Mapping):
        allowed = {
            "content-type",
            "content-length",
            "date",
            "etag",
            "last-modified",
            "server",
        }
        for key, value in headers.items():
            if str(key).casefold() in allowed:
                selected_headers[str(key).lower()] = str(value)
    response_url = getattr(response, "url", None)
    captured_at = datetime.now(timezone.utc).isoformat()
    return {
        "provider": "TWSE" if "twse" in source.casefold() else "TPEX",
        "endpoint": source.split("?", 1)[0],
        "request_params": {str(key): str(value) for key, value in params.items()},
        "request_url": str(response_url) if response_url else source,
        "http_status": getattr(response, "status_code", None),
        "response_headers": selected_headers,
        "captured_at_utc": captured_at,
    }


@dataclass(frozen=True, slots=True)
class TpexAnnualStockScheduleV1:
    """年度表的股票市場解析結果；原件／來源用途與歷史資格各自核對。"""

    year: int
    raw_sha256: str
    html_sha256: str
    source_baseline_date: str
    holiday_dates: tuple[str, ...]
    stock_settlement_only_dates: tuple[str, ...]
    open_marker_dates: tuple[str, ...]
    rows: tuple[TpexTradingDateRowV1, ...]
    ignored_non_stock_rows: tuple[TpexTradingDateRowV1, ...]
    parser_version: str = "tpex-annual-stock-schedule.v1"

    def expected_session_dates(self, start_date: date, end_date: date) -> tuple[str, ...]:
        if type(start_date) is not date or type(end_date) is not date:
            raise OfficialCalendarBundleError("tpex_annual_exact_date_required")
        _validate_date_range(start_date, end_date)
        if start_date.year != self.year or end_date.year != self.year:
            raise OfficialCalendarBundleError("tpex_annual_period_year_mismatch")
        closed = frozenset(self.holiday_dates + self.stock_settlement_only_dates)
        result: list[str] = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5 and current.isoformat() not in closed:
                result.append(current.isoformat())
            current += timedelta(days=1)
        return tuple(result)

    @property
    def candidate_only(self) -> bool:
        return True

    @property
    def historical_pit_eligible(self) -> bool:
        return False

    @property
    def performance_eligible(self) -> bool:
        return False


def _tpex_annual_text(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


_TPEX_ANNUAL_HOLIDAYS = frozenset(_tpex_annual_text(value) for value in (
    "中華民國開國紀念日", "農曆除夕及春節", "和平紀念日", "兒童節及民族掃墓節",
    "勞動節", "端午節", "中秋節", "孔子誕辰紀念日/教師節", "國慶日",
    "臺灣光復暨金門古寧頭大捷紀念日", "行憲紀念日",
))
_TPEX_ANNUAL_OPEN_ROWS = frozenset((
    "國曆新年開始交易日", "農曆春節後開始交易日", "農曆春節前股票交易系統最後交易日",
))
_TPEX_ANNUAL_NON_STOCK_ROWS = frozenset(_tpex_annual_text(value) for value in (
    "農曆春節前國際債券交易系統最後交易日",
    "農曆春節前債券等殖成交系統（含比對系統）最後交易日",
    "農曆春節前債券處所議價最後交易日",
))
_TPEX_ANNUAL_REPEATED_HOLIDAY_ROWS = {
    "和平紀念日": 2, "兒童節及民族掃墓節": 4, "國慶日": 2,
    "臺灣光復暨金門古寧頭大捷紀念日": 2,
}
_TPEX_ANNUAL_DATE = re.compile(r"([0-9]{1,2})月([0-9]{1,2})日")


def _tpex_annual_dates(value: str, year: int) -> tuple[date, ...]:
    text = _tpex_annual_text(value)
    matches = list(_TPEX_ANNUAL_DATE.finditer(text))
    remainder = _TPEX_ANNUAL_DATE.sub("", text).replace("、", "").replace("及", "")
    if not matches or remainder or len(matches) > 31:
        raise OfficialCalendarBundleError("tpex_annual_date_cell_invalid")
    try:
        result = tuple(date(year, int(item[1]), int(item[2])) for item in matches)
    except ValueError as exc:
        raise OfficialCalendarBundleError("tpex_annual_date_invalid") from exc
    if len(set(result)) != len(result):
        raise OfficialCalendarBundleError("tpex_annual_duplicate_date_in_row")
    return result


def parse_tpex_annual_stock_schedule_v1(
    raw: bytes, *, expected_year: int, expected_sha256: str,
) -> TpexAnnualStockScheduleV1:
    """沿原日曆模組解析新年度來源；不cast舊monthly格式或發行接受錨點。"""
    # transport沿用本模組的既有常數；執行時才載入葉片以避免循環import。
    from data_module.tpex_trading_date_html_v1 import (
        TpexTradingDateHtmlError, decode_tpex_trading_date_rows_v1,
    )

    try:
        source = decode_tpex_trading_date_rows_v1(
            raw, expected_year=expected_year, expected_sha256=expected_sha256,
        )
    except TpexTradingDateHtmlError as exc:
        raise OfficialCalendarBundleError("tpex_annual_html_structure_invalid:" + str(exc)) from exc
    holidays: set[date] = set()
    settlement: set[date] = set()
    open_rows: dict[str, date] = {}
    holiday_names: set[str] = set()
    holiday_rows: dict[str, int] = {}
    holiday_groups: dict[str, list[date]] = {}
    previous_name: str | None = None
    ignored: dict[str, TpexTradingDateRowV1] = {}
    weekday_names = "一二三四五六日"
    for row in source.rows:
        name = _tpex_annual_text(row.name)
        days = _tpex_annual_dates(row.date_text, source.year)
        weekdays = _tpex_annual_text(row.weekday_text)
        if len(weekdays) != len(days) or any(
            label != weekday_names[day.weekday()] for day, label in zip(days, weekdays)
        ):
            raise OfficialCalendarBundleError("tpex_annual_date_weekday_mismatch")
        if name in _TPEX_ANNUAL_NON_STOCK_ROWS:
            if name in ignored or len(days) != 1:
                raise OfficialCalendarBundleError("tpex_annual_non_stock_row_duplicate")
            ignored[name] = row
        elif name in _TPEX_ANNUAL_OPEN_ROWS:
            if name in open_rows or len(days) != 1 or days[0].weekday() >= 5:
                raise OfficialCalendarBundleError("tpex_annual_open_marker_invalid")
            open_rows[name] = days[0]
            if name == "農曆春節前股票交易系統最後交易日":
                description = _tpex_annual_text(row.description or "")
                match = re.fullmatch(
                    r"(?P<dates>[0-9]{1,2}月[0-9]{1,2}日(?:[、及][0-9]{1,2}月[0-9]{1,2}日)*)"
                    r"市場無交易[,，]僅辦理給付結算[。.]?", description,
                )
                if match is None:
                    raise OfficialCalendarBundleError("tpex_annual_stock_settlement_description_invalid")
                declared = _tpex_annual_dates(match["dates"], source.year)
                if any(day <= days[0] or day.weekday() >= 5 for day in declared):
                    raise OfficialCalendarBundleError("tpex_annual_stock_settlement_order_invalid")
                settlement.update(declared)
        elif name in _TPEX_ANNUAL_HOLIDAYS:
            if row.description is None or not _tpex_annual_text(row.description):
                raise OfficialCalendarBundleError("tpex_annual_holiday_description_missing")
            count = holiday_rows.get(name, 0) + 1
            if (count > _TPEX_ANNUAL_REPEATED_HOLIDAY_ROWS.get(name, 1)
                    or (name in holiday_names and previous_name != name)
                    or (name != "農曆除夕及春節" and len(days) != 1)):
                raise OfficialCalendarBundleError("tpex_annual_duplicate_holiday_row")
            holiday_rows[name] = count
            holiday_groups.setdefault(name, []).extend(days)
            holiday_names.add(name)
            if holidays.intersection(days):
                raise OfficialCalendarBundleError("tpex_annual_duplicate_holiday_date")
            holidays.update(days)
        else:
            raise OfficialCalendarBundleError("tpex_annual_unknown_row_name:" + name)
        previous_name = name
    if (holiday_names != _TPEX_ANNUAL_HOLIDAYS or set(open_rows) != _TPEX_ANNUAL_OPEN_ROWS
            or set(ignored) != _TPEX_ANNUAL_NON_STOCK_ROWS):
        raise OfficialCalendarBundleError("tpex_annual_required_rows_missing")
    if any(any(right - left != timedelta(days=1) for left, right in zip(days, days[1:]))
           for days in holiday_groups.values()):
        raise OfficialCalendarBundleError("tpex_annual_holiday_group_nonconsecutive")
    opened = frozenset(open_rows.values())
    if opened.intersection(holidays | settlement) or holidays.intersection(settlement):
        raise OfficialCalendarBundleError("tpex_annual_conflicting_stock_state")
    last = open_rows["農曆春節前股票交易系統最後交易日"]
    resumed = open_rows["農曆春節後開始交易日"]
    if not last < resumed or any(day >= resumed for day in settlement):
        raise OfficialCalendarBundleError("tpex_annual_spring_order_invalid")
    current = last + timedelta(days=1)
    while current < resumed:
        if current.weekday() < 5 and current not in holidays | settlement:
            raise OfficialCalendarBundleError("tpex_annual_spring_stock_gap_missing")
        current += timedelta(days=1)
    return TpexAnnualStockScheduleV1(
        year=source.year, raw_sha256=source.raw_sha256, html_sha256=source.html_sha256,
        source_baseline_date=source.source_baseline_date,
        holiday_dates=tuple(day.isoformat() for day in sorted(holidays)),
        stock_settlement_only_dates=tuple(day.isoformat() for day in sorted(settlement)),
        open_marker_dates=tuple(day.isoformat() for day in sorted(opened)), rows=source.rows,
        ignored_non_stock_rows=tuple(ignored[name] for name in sorted(ignored)),
    )


def _parse_twse_stock_annual_v1(
    payload: object, year: int,
) -> tuple[dict[date, bool], dict[str, frozenset[date]]]:
    """新年度用途的欄位／股票語義核對；舊TWSE parser契約不變。"""
    if type(payload) is not list or not 1 <= len(payload) <= 256:
        raise OfficialCalendarBundleError("twse_annual_rows_invalid")
    open_names = frozenset(("國曆新年開始交易日", "農曆春節前最後交易日", "農曆春節後開始交易日"))
    opens: dict[str, date] = {}
    holidays: dict[str, list[date]] = {}
    settlement: set[date] = set()
    schedule: dict[date, bool] = {}
    previous: date | None = None
    for index, row in enumerate(payload):
        if (type(row) is not dict or set(row) != {"Name", "Date", "Weekday", "Description"}
                or any(type(row[field]) is not str for field in row)):
            raise OfficialCalendarBundleError("twse_annual_row_schema_invalid")
        day = _parse_roc_date(row["Date"], index=index)
        if day.year != year or (previous is not None and day <= previous):
            raise OfficialCalendarBundleError("twse_annual_year_duplicate_or_order_invalid")
        previous = day
        if row["Weekday"].strip() != "一二三四五六日"[day.weekday()]:
            raise OfficialCalendarBundleError("twse_annual_weekday_mismatch")
        name = _tpex_annual_text(row["Name"])
        description = re.sub(r"<br\s*/?>", "", row["Description"], flags=re.IGNORECASE)
        if "<" in description or ">" in description:
            raise OfficialCalendarBundleError("twse_annual_description_markup_unknown")
        if name in open_names:
            if name in opens or day.weekday() >= 5 or not description.strip():
                raise OfficialCalendarBundleError("twse_annual_open_marker_invalid")
            opens[name] = day
            schedule[day] = True
        elif name in _TPEX_ANNUAL_HOLIDAYS:
            group = holidays.setdefault(name, [])
            limit = 31 if name == "農曆除夕及春節" else _TPEX_ANNUAL_REPEATED_HOLIDAY_ROWS.get(name, 1)
            if (len(group) >= limit or not description.strip()
                    or (group and day - group[-1] != timedelta(days=1))):
                raise OfficialCalendarBundleError("twse_annual_holiday_group_invalid")
            group.append(day)
            schedule[day] = False
        elif name == "市場無交易,僅辦理結算交割作業":
            if day.weekday() >= 5 or len(settlement) >= 5:
                raise OfficialCalendarBundleError("twse_annual_settlement_invalid")
            settlement.add(day)
            schedule[day] = False
        else:
            raise OfficialCalendarBundleError("twse_annual_unknown_row_name:" + name)
    if set(opens) != open_names or set(holidays) != _TPEX_ANNUAL_HOLIDAYS or not settlement:
        raise OfficialCalendarBundleError("twse_annual_required_rows_missing")
    last, resumed = opens["農曆春節前最後交易日"], opens["農曆春節後開始交易日"]
    if not last < resumed or any(not last < day < resumed for day in settlement):
        raise OfficialCalendarBundleError("twse_annual_settlement_order_invalid")
    current = last + timedelta(days=1)
    while current < resumed:
        if current.weekday() < 5 and schedule.get(current) is not False:
            raise OfficialCalendarBundleError("twse_annual_spring_gap_missing")
        current += timedelta(days=1)
    return schedule, {name: frozenset(days) for name, days in holidays.items()}


def derive_annual_calendar_sessions_v1(
    *, start_date: date, end_date: date,
    twse_transports: Sequence[OfficialCalendarJsonTransportV1],
    tpex_transports: Sequence[OfficialCalendarTpexAnnualJsonTransportV1],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """雙市場逐年完整原件衍生，與原monthly response／資格分開。"""
    from data_module.official_calendar_transport_v1 import OfficialCalendarJsonTransportV1
    from data_module.tpex_annual_calendar_transport_v1 import OfficialCalendarTpexAnnualJsonTransportV1

    _validate_date_range(start_date, end_date)
    if (not isinstance(twse_transports, Sequence) or not isinstance(tpex_transports, Sequence)
            or not 1 <= len(twse_transports) <= 2 or not 1 <= len(tpex_transports) <= 2):
        raise OfficialCalendarBundleError("annual_calendar_bounded_transports_required")
    years = set(range(start_date.year, end_date.year + 1))
    twse: dict[int, dict[date, bool]] = {}
    twse_holidays: dict[int, dict[str, frozenset[date]]] = {}
    tpex: dict[int, TpexAnnualStockScheduleV1] = {}
    for item in twse_transports:
        if type(item) is not OfficialCalendarJsonTransportV1 or item.kind != "twse":
            raise OfficialCalendarBundleError("annual_calendar_twse_transport_required")
        verified = OfficialCalendarJsonTransportV1.from_dict(item.to_dict())
        year = int(verified.key)
        if year not in years or year in twse:
            raise OfficialCalendarBundleError("annual_calendar_twse_partition_invalid")
        twse[year], twse_holidays[year] = _parse_twse_stock_annual_v1(verified.to_response().payload, year)
    for annual in tpex_transports:
        if type(annual) is not OfficialCalendarTpexAnnualJsonTransportV1:
            raise OfficialCalendarBundleError("annual_calendar_tpex_transport_required")
        verified_annual = OfficialCalendarTpexAnnualJsonTransportV1.from_dict(annual.to_dict())
        if verified_annual.year not in years or verified_annual.year in tpex:
            raise OfficialCalendarBundleError("annual_calendar_tpex_partition_invalid")
        tpex[verified_annual.year] = parse_tpex_annual_stock_schedule_v1(
            verified_annual.raw_bytes, expected_year=verified_annual.year,
            expected_sha256=verified_annual.raw_sha256,
        )
    if set(twse) != years or set(tpex) != years:
        raise OfficialCalendarBundleError("annual_calendar_both_markets_years_required")
    # 此年度用途以兩份獨立表互證同名國定假日；不一致僅拒絕，不能借另一市場補值。
    for year in years:
        tpex_holidays: dict[str, set[date]] = {}
        for row in tpex[year].rows:
            name = _tpex_annual_text(row.name)
            if name in _TPEX_ANNUAL_HOLIDAYS:
                tpex_holidays.setdefault(name, set()).update(_tpex_annual_dates(row.date_text, year))
        if twse_holidays[year] != {name: frozenset(days) for name, days in tpex_holidays.items()}:
            raise OfficialCalendarBundleError("annual_calendar_holiday_dates_disagree")
    twse_dates: list[str] = []
    tpex_dates: list[str] = []
    for year in sorted(years):
        first = max(start_date, date(year, 1, 1))
        last = min(end_date, date(year, 12, 31))
        current = first
        while current <= last:
            if current.weekday() < 5 and twse[year].get(current, True):
                twse_dates.append(current.isoformat())
            current += timedelta(days=1)
        tpex_dates.extend(tpex[year].expected_session_dates(first, last))
    return tuple(twse_dates), tuple(tpex_dates)
