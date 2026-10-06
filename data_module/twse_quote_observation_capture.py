"""Prospective TWSE MIS quote-observation custody.

This is deliberately separate from the Paper execution-session collector.  It
can observe an explicit symbol list during today's regular session without
claiming that the list was today's recommendation or that a quote was an
actual fill.  Raw response bytes, response-completion time, best bid/ask and
the derived quote spread are all retained in an immutable research receipt.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import json
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.request import Request
from zoneinfo import ZoneInfo

from data_module.formal_daily_input_producer import (
    TWSE_MIS_STOCK_INFO_ENDPOINT,
    _canonical_json,
    _payload_hash,
    _sha256_bytes,
    _twse_mis_request_url,
)
from data_module.paper_event_source_capture import (
    _fetch_raw_response,
    _require_temp_directory,
    _urlopen_fetcher,
    _write_create_only_bytes,
)


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_OPEN = time(9, 0)
SESSION_CLOSE = time(13, 30)
SCHEMA_VERSION = "twse-mis-quote-observation.v1"
DURABLE_SCHEMA_VERSION = "twse-mis-quote-observation-durable.v1"
DEFAULT_TIMEOUT_SECONDS = 30.0


class TwseQuoteObservationError(ValueError):
    """The official quote response cannot be safely used as an observation."""


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TwseQuoteObservationError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _validate_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(sorted({str(value).strip() for value in symbols if str(value).strip()}))
    if not normalized:
        raise TwseQuoteObservationError("symbols must not be empty")
    if any(len(value) != 4 or not value.isdigit() for value in normalized):
        raise TwseQuoteObservationError("TWSE MIS observation requires four-digit symbols")
    return normalized


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if "_" in text:
        text = text.split("_", 1)[0].strip()
    if text in {"", "-", "--", "N/A", "None"}:
        return None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return parsed


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _integer(value: object) -> int | None:
    parsed = _decimal(value)
    if parsed is None or parsed != parsed.to_integral_value():
        return None
    return int(parsed)


def _parse_rows(
    raw: bytes,
    *,
    symbols: tuple[str, ...],
    observation_date: date,
    captured_at: datetime,
) -> tuple[list[dict[str, object]], str | None]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return [], "twse_mis_quote_response_json_invalid"
    if not isinstance(payload, Mapping):
        return [], "twse_mis_quote_response_not_object"
    if str(payload.get("rtcode") or "") not in {"0", "000", "0000"}:
        return [], "twse_mis_quote_response_status_invalid"
    if str(payload.get("rtmessage") or "") != "OK":
        return [], "twse_mis_quote_response_message_invalid"
    messages = payload.get("msgArray")
    if not isinstance(messages, list) or not messages:
        return [], "twse_mis_quote_response_rows_missing"
    requested = set(symbols)
    seen: set[str] = set()
    rows: list[dict[str, object]] = []
    for item in messages:
        if not isinstance(item, Mapping):
            return [], "twse_mis_quote_response_row_invalid"
        symbol = str(item.get("c") or "").strip()
        # TWSE MIS appends an empty sentinel row to some successful responses.
        # It is not a requested instrument and must not be treated as a
        # malformed quote row.
        if not symbol and str(item.get("s") or "") == "-" and str(item.get("z") or "") == "-":
            continue
        if symbol not in requested or str(item.get("ex") or "") != "tse":
            return [], "twse_mis_quote_response_symbol_mismatch"
        if symbol in seen:
            return [], "twse_mis_quote_response_duplicate_symbol"
        if str(item.get("d") or "") != observation_date.strftime("%Y%m%d"):
            return [], "twse_mis_quote_response_date_mismatch"
        tlong = str(item.get("tlong") or "").strip()
        if not tlong.isdigit():
            return [], "twse_mis_quote_response_timestamp_invalid"
        try:
            seconds, milliseconds = divmod(int(tlong), 1000)
            observed_at = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(
                microsecond=milliseconds * 1000
            )
        except (OverflowError, OSError, ValueError):
            return [], "twse_mis_quote_response_timestamp_invalid"
        local_observed = observed_at.astimezone(TAIPEI)
        if local_observed.date() != observation_date:
            return [], "twse_mis_quote_response_observation_date_mismatch"
        local_time = local_observed.timetz().replace(tzinfo=None)
        if not SESSION_OPEN <= local_time < SESSION_CLOSE:
            return [], "twse_mis_quote_response_outside_regular_session"
        if observed_at > captured_at:
            return [], "twse_mis_quote_response_after_capture"
        last_price = _decimal(item.get("z"))
        best_bid = _decimal(item.get("b"))
        best_ask = _decimal(item.get("a"))
        if best_bid is not None and best_ask is not None and best_ask < best_bid:
            return [], "twse_mis_quote_response_crossed_market"
        spread_bp: int | None = None
        if best_bid is not None and best_ask is not None:
            midpoint = (best_bid + best_ask) / Decimal("2")
            if midpoint > 0:
                spread_bp = int(
                    (((best_ask - best_bid) / midpoint) * Decimal("10000")).quantize(
                        Decimal("1"), rounding=ROUND_HALF_EVEN
                    )
                )
        rows.append(
            {
                "symbol": symbol,
                "exchange": "TWSE",
                "source_trade_date": observation_date.isoformat(),
                "quote_observed_at": observed_at.isoformat(),
                "quote_time_text": str(item.get("t") or ""),
                "last_price": _decimal_text(last_price),
                "best_bid": _decimal_text(best_bid),
                "best_ask": _decimal_text(best_ask),
                "spread_bp": spread_bp,
                "best_bid_levels_raw": str(item.get("b") or ""),
                "best_ask_levels_raw": str(item.get("a") or ""),
                "volume_shares": _integer(item.get("v")),
                "tlong": tlong,
            }
        )
        seen.add(symbol)
    if seen != requested:
        return rows, "twse_mis_quote_response_requested_symbol_missing"
    return rows, None


def capture_twse_quote_observation(
    *,
    symbols: Sequence[str],
    observation_date: date,
    output_dir: Path,
    symbol_source: Mapping[str, object],
    now: datetime | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    fetcher: Callable[[Request, float], object] | None = None,
) -> dict[str, object]:
    """Capture today's official quote observation for an explicit symbol list."""

    if not isinstance(observation_date, date):
        raise TwseQuoteObservationError("observation_date must be date")
    normalized_symbols = _validate_symbols(symbols)
    observed_clock = _aware(now or datetime.now(timezone.utc), "now")
    local_clock = observed_clock.astimezone(TAIPEI)
    if local_clock.date() != observation_date:
        raise TwseQuoteObservationError("observation must run on the observation date")
    if not SESSION_OPEN <= local_clock.timetz().replace(tzinfo=None) < SESSION_CLOSE:
        raise TwseQuoteObservationError("observation must run during Taipei regular session")
    if not 0 < float(timeout_seconds) <= DEFAULT_TIMEOUT_SECONDS:
        raise TwseQuoteObservationError("timeout_seconds is outside bounded range")
    temp_root = _require_temp_directory(Path(output_dir))
    request_channels = "|".join(f"tse_{symbol}.tw" for symbol in normalized_symbols)
    request_url = _twse_mis_request_url(request_channels)
    raw, response, completed_at = _fetch_raw_response(
        request_url,
        timeout_seconds=float(timeout_seconds),
        fetcher=(fetcher or _urlopen_fetcher),
    )
    captured_at = _aware(now or completed_at, "captured_at")
    local_captured = captured_at.astimezone(TAIPEI)
    if local_captured.date() != observation_date or not (
        SESSION_OPEN <= local_captured.timetz().replace(tzinfo=None) < SESSION_CLOSE
    ):
        raise TwseQuoteObservationError("response completion is outside observation session")
    rows, reason = _parse_rows(
        raw,
        symbols=normalized_symbols,
        observation_date=observation_date,
        captured_at=captured_at,
    )
    missing_symbols = sorted(set(normalized_symbols) - {str(row["symbol"]) for row in rows})
    if reason is not None and reason != "twse_mis_quote_response_requested_symbol_missing":
        raise TwseQuoteObservationError(reason)
    raw_hash = _sha256_bytes(raw)
    raw_path = temp_root / "raw_response.bin"
    _write_create_only_bytes(raw_path, raw, "TWSE MIS quote raw response")
    body: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "producer": "data_module.twse_quote_observation_capture",
        "source_authority": "twse",
        "source_url": TWSE_MIS_STOCK_INFO_ENDPOINT,
        "request_url": request_url,
        "request": {"ex_ch": request_channels, "json": "1", "delay": "0"},
        "response": dict(response),
        "observation_date": observation_date.isoformat(),
        "symbols": list(normalized_symbols),
        "symbol_source": dict(symbol_source),
        "captured_at": captured_at.isoformat(),
        "response_completed_at": completed_at.isoformat(),
        "availability_basis": "official_response_body_read_completed_at",
        "source_kind": "official_intraday_quote_observation",
        "raw_response_path": raw_path.name,
        "raw_response_sha256": raw_hash,
        "raw_response_bytes": len(raw),
        "row_count": len(rows),
        "missing_symbols": missing_symbols,
        "coverage_status": "complete" if not missing_symbols else "partial",
        "rows": rows,
        "quote_observation_time_proven": True,
        "execution_event_time_proven": False,
        "actual_fill_proven": False,
        "historical_backfill_claimed": False,
        "formal_source_contract_eligible": False,
        "observed_liquidity_cost_eligible": False,
        "estimated_cost_eligible": False,
    }
    payload = {**body, "content_sha256": _payload_hash(body)}
    observation_path = temp_root / "quote_observation.json"
    observation_bytes = (_canonical_json(payload) + "\n").encode("utf-8")
    _write_create_only_bytes(observation_path, observation_bytes, "TWSE quote observation envelope")
    if _sha256_bytes(raw_path.read_bytes()) != raw_hash:
        raise TwseQuoteObservationError("raw response readback hash mismatch")
    if _sha256_bytes(observation_path.read_bytes()) != _sha256_bytes(observation_bytes):
        raise TwseQuoteObservationError("observation envelope readback hash mismatch")
    return {
        "status": "captured" if not missing_symbols else "partial",
        "schema_version": SCHEMA_VERSION,
        "observation_date": observation_date.isoformat(),
        "symbols": list(normalized_symbols),
        "symbol_source": dict(symbol_source),
        "captured_at": captured_at.isoformat(),
        "response_completed_at": completed_at.isoformat(),
        "raw_response_path": str(raw_path.resolve()),
        "raw_response_sha256": raw_hash,
        "raw_response_bytes": len(raw),
        "observation_path": str(observation_path.resolve()),
        "observation_sha256": _sha256_bytes(observation_bytes),
        "row_count": len(rows),
        "missing_symbols": missing_symbols,
        "coverage_status": "complete" if not missing_symbols else "partial",
        "quote_observation_time_proven": True,
        "execution_event_time_proven": False,
        "actual_fill_proven": False,
        "historical_backfill_claimed": False,
        "formal_source_contract_eligible": False,
        "observed_liquidity_cost_eligible": False,
        "temporary_root": str(temp_root.resolve()),
    }


def persist_twse_quote_observation(
    capture_result: Mapping[str, object],
    *,
    durable_root: Path,
    allowed_root: Path,
) -> dict[str, object]:
    """Copy a validated temporary capture into an immutable durable bucket."""

    root = Path(durable_root).expanduser().resolve()
    allowed = Path(allowed_root).expanduser().resolve()
    if root == allowed or root.is_symlink() or not root.is_relative_to(allowed):
        raise TwseQuoteObservationError("durable quote root must be a child of allowed output")
    raw_path = Path(str(capture_result.get("raw_response_path") or "")).resolve()
    observation_path = Path(str(capture_result.get("observation_path") or "")).resolve()
    temporary_root = Path(str(capture_result.get("temporary_root") or "")).resolve()
    for path in (raw_path, observation_path):
        if path.is_symlink() or not path.is_file() or not path.is_relative_to(temporary_root):
            raise TwseQuoteObservationError("temporary quote capture path is invalid")
    raw_hash = str(capture_result.get("raw_response_sha256") or "")
    if not raw_hash.startswith("sha256:") or len(raw_hash) != 71:
        raise TwseQuoteObservationError("raw response hash is invalid")
    observation_date = str(capture_result.get("observation_date") or "")
    bucket = root / observation_date / raw_hash[7:23]
    bucket.mkdir(parents=True, exist_ok=True)
    durable_raw = bucket / "raw_response.bin"
    durable_observation = bucket / "quote_observation.json"
    raw = raw_path.read_bytes()
    observation = observation_path.read_bytes()
    if _sha256_bytes(raw) != raw_hash:
        raise TwseQuoteObservationError("temporary raw response hash mismatch")
    _write_create_only_bytes(durable_raw, raw, "durable TWSE quote raw response")
    _write_create_only_bytes(durable_observation, observation, "durable TWSE quote envelope")
    manifest_body: dict[str, object] = {
        "schema_version": DURABLE_SCHEMA_VERSION,
        "source_kind": "official_intraday_quote_observation",
        "observation_date": observation_date,
        "captured_at": capture_result.get("captured_at"),
        "capture_status": capture_result.get("status"),
        "missing_symbols": capture_result.get("missing_symbols", []),
        "coverage_status": capture_result.get("coverage_status"),
        "symbol_source": capture_result.get("symbol_source"),
        "raw_response_path": durable_raw.name,
        "raw_response_sha256": raw_hash,
        "observation_path": durable_observation.name,
        "observation_sha256": _sha256_bytes(observation),
        "quote_observation_time_proven": True,
        "execution_event_time_proven": False,
        "actual_fill_proven": False,
        "historical_backfill_claimed": False,
        "formal_source_contract_eligible": False,
        "observed_liquidity_cost_eligible": False,
    }
    manifest = {**manifest_body, "manifest_sha256": _payload_hash(manifest_body)}
    manifest_path = bucket / "manifest.json"
    _write_create_only_bytes(
        manifest_path,
        (_canonical_json(manifest) + "\n").encode("utf-8"),
        "durable TWSE quote manifest",
    )
    return {
        **dict(capture_result),
        "status": "durable" if capture_result.get("status") == "captured" else "durable_partial",
        "durable_root": str(bucket.resolve()),
        "durable_raw_response_path": str(durable_raw.resolve()),
        "durable_observation_path": str(durable_observation.resolve()),
        "durable_manifest_path": str(manifest_path.resolve()),
        "durable_manifest_sha256": _sha256_bytes(manifest_path.read_bytes()),
        "idempotent_replay": True,
    }


__all__ = [
    "SCHEMA_VERSION",
    "DURABLE_SCHEMA_VERSION",
    "TwseQuoteObservationError",
    "capture_twse_quote_observation",
    "persist_twse_quote_observation",
]
