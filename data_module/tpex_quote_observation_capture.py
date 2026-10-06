"""Prospective TPEx venue-aware daily quote observation.

TPEx's public OpenAPI daily quote response is a close-quote publication, not
an intraday execution feed.  This module records that distinction explicitly:
the response can prove source availability and last bid/ask fields for its
published source date, but it cannot prove a current-session quote timestamp
or an actual fill.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Mapping, Sequence
import uuid

from data_module.tpex_daily_price_backfill import normalize_tpex_daily_price_rows
from data_module.tpex_daily_price_source import TpexDailyPriceSource


SCHEMA_VERSION = "tpex-daily-close-quote-observation.v1"


class TpexQuoteObservationError(ValueError):
    """The TPEx close-quote response cannot be safely bound to a receipt."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _write_create_only(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise TpexQuoteObservationError(f"immutable TPEx observation conflict: {path}")
        return
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(raw)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def capture_tpex_daily_close_observation(
    *,
    symbols: Sequence[str],
    requested_date: str,
    output_root: Path,
    symbol_source: Mapping[str, object],
) -> dict[str, object]:
    """Fetch TPEx's official daily-close route without writing a CSV/SQLite row."""

    normalized_symbols = tuple(sorted({str(value).strip() for value in symbols if str(value).strip()}))
    if not normalized_symbols or any(len(value) != 4 or not value.isdigit() for value in normalized_symbols):
        raise TpexQuoteObservationError("TPEx symbols must be explicit four-digit codes")
    source = TpexDailyPriceSource(
        output_dir=Path(tempfile.gettempdir()) / f"tpex_quote_observation_{uuid.uuid4().hex}",
        source_custody_root=Path(output_root),
    )
    try:
        raw_rows = source._fetch_official_rows(str(requested_date))
        normalized = normalize_tpex_daily_price_rows(
            raw_rows,
            fallback_date=str(requested_date),
            strict=False,
        )
        source_dates = sorted({str(row.get("日期")) for row in normalized.rows if row.get("日期")})
        requested_text = str(requested_date).strip().replace("/", "-")
        if len(requested_text) == 8 and requested_text.isdigit():
            requested_text = (
                f"{requested_text[:4]}-{requested_text[4:6]}-{requested_text[6:8]}"
            )
        source_date = source_dates[-1] if source_dates else requested_text
        requested_rows = [
            row for row in normalized.rows
            if str(row.get("證券代號") or "") in normalized_symbols
        ]
        missing_symbols = sorted(
            set(normalized_symbols) - {str(row.get("證券代號")) for row in requested_rows}
        )
        if not source._last_response_custody:
            raise TpexQuoteObservationError("TPEx response custody metadata is missing")
        receipt = source._persist_response_custody(
            source_date=source_date,
            row_count=len(normalized.rows),
            source_columns=(
                tuple(normalized.rows[0].keys()) if normalized.rows else ()
            ),
        )
        if not receipt:
            raise TpexQuoteObservationError("TPEx response custody receipt is missing")
        receipt_path = Path(str(receipt["receipt_path"])).resolve()
        receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        observation_rows: list[dict[str, object]] = []
        for row in requested_rows:
            bid = row.get("最後揭示買價")
            ask = row.get("最後揭示賣價")
            spread_bp: int | None = None
            try:
                if bid not in (None, "") and ask not in (None, ""):
                    bid_value = float(str(bid))
                    ask_value = float(str(ask))
                    midpoint = (bid_value + ask_value) / 2
                    if midpoint > 0:
                        spread_bp = round((ask_value - bid_value) / midpoint * 10000)
            except (TypeError, ValueError):
                spread_bp = None
            observation_rows.append(
                {
                    "symbol": str(row["證券代號"]),
                    "exchange": "TPEx",
                    "source_date": str(row.get("日期") or source_date),
                    "close": row.get("收盤價"),
                    "best_bid": bid,
                    "best_ask": ask,
                    "spread_bp": spread_bp,
                    "volume_shares": row.get("成交股數"),
                }
            )
        body: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "producer": "data_module.tpex_quote_observation_capture",
            "source_authority": "tpex",
            "source_id": "tpex.daily_close_quotes",
            "source_url": receipt_payload.get("requested_url"),
            "requested_date": str(requested_date)[:10],
            "source_date": source_date,
            "symbol_source": dict(symbol_source),
            "symbols": list(normalized_symbols),
            "missing_symbols": missing_symbols,
            "rows": observation_rows,
            "row_count": len(observation_rows),
            "coverage_status": (
                "no_rows" if not normalized.rows else "complete" if not missing_symbols else "partial"
            ),
            "captured_at": receipt_payload.get("captured_at"),
            "available_at": receipt_payload.get("available_at"),
            "raw_response_sha256": receipt_payload.get("raw_response_sha256"),
            "raw_response_path": receipt_payload.get("raw_response_path"),
            "custody_receipt_path": str(receipt_path),
            "observation_semantics": "official_daily_close_response;not_intraday_quote",
            "current_session_quote_time_proven": False,
            "quote_observation_time_proven": False,
            "execution_event_time_proven": False,
            "actual_fill_proven": False,
            "historical_backfill_claimed": False,
            "formal_source_contract_eligible": False,
            "observed_liquidity_cost_eligible": False,
        }
        encoded = (_canonical_json({**body, "content_sha256": _hash_bytes(_canonical_json(body).encode("utf-8"))}) + "\n").encode("utf-8")
        digest = _hash_bytes(encoded)
        observation_root = (
            Path(output_root).resolve()
            / "paper_execution_eod_replay"
            / "prospective_quote_observations"
            / "tpex"
            / str(requested_date)[:10]
            / digest[7:23]
        )
        observation_path = observation_root / "observation.json"
        _write_create_only(observation_path, encoded)
        return {
            "status": (
                "durable_no_rows"
                if not normalized.rows
                else "durable"
                if not missing_symbols
                else "durable_partial"
            ),
            "schema_version": SCHEMA_VERSION,
            "venue": "TPEx",
            "requested_date": str(requested_date)[:10],
            "source_date": source_date,
            "symbols": list(normalized_symbols),
            "missing_symbols": missing_symbols,
            "coverage_status": (
                "no_rows" if not normalized.rows else "complete" if not missing_symbols else "partial"
            ),
            "captured_at": body["captured_at"],
            "available_at": body["available_at"],
            "observation_semantics": body["observation_semantics"],
            "custody_receipt_path": str(receipt_path),
            "observation_path": str(observation_path.resolve()),
            "observation_sha256": _hash_bytes(encoded),
            "raw_response_sha256": body["raw_response_sha256"],
            "current_session_quote_time_proven": False,
            "execution_event_time_proven": False,
            "actual_fill_proven": False,
            "historical_backfill_claimed": False,
            "formal_source_contract_eligible": False,
            "observed_liquidity_cost_eligible": False,
        }
    finally:
        try:
            source.output_dir.rmdir()
        except OSError:
            pass


__all__ = ["SCHEMA_VERSION", "TpexQuoteObservationError", "capture_tpex_daily_close_observation"]
