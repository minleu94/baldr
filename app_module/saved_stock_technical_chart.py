"""同次價格／MA20／MA60 的有界不可變保存契約；不讀來源或計算指標。"""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from typing import Any, Mapping, Sequence
import zlib

from app_module.stock_research_report_dtos import (
    StockPricePointDTO, StockTechnicalHistoryRowDTO,
    stock_technical_history_row_fingerprint_sha256,
)
from app_module.stock_research_report_provider_adapters import stock_price_row_fingerprint_sha256

SCHEMA = "stock-research-saved-technical-chart.v1"
MAX_ROWS = 120
MAX_RAW_BYTES = 256 * 1024
MAX_ENVELOPE_BYTES = 48 * 1024
_DECIMALS = {"open_price", "high_price", "low_price", "close_price", "turnover", "change", "ma20", "ma60"}
_HEADER = {"schema_version", "stock_code", "decision_cutoff", "scope_identity", "input_fingerprint_sha256"}


class SavedTechnicalChartError(ValueError):
    pass


@dataclass(frozen=True)
class SavedTechnicalChart:
    stock_code: str
    decision_cutoff: str
    scope_identity: str
    input_fingerprint_sha256: str
    content_sha256: str
    price_points: tuple[StockPricePointDTO, ...]
    technical_history: tuple[StockTechnicalHistoryRowDTO, ...]


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise SavedTechnicalChartError(code)


def _sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(x in "0123456789abcdef" for x in value)


def _clock(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise SavedTechnicalChartError("chart_invalid_clock") from exc
    _require(result.tzinfo is not None and result.utcoffset() is not None, "chart_invalid_clock")
    return result


def _row(value: Mapping[str, Any], cls: Any) -> Any:
    _require(isinstance(value, Mapping) and set(value) == {x.name for x in fields(cls)}, "chart_row_schema")
    result = dict(value)
    for key, item in result.items():
        if key in _DECIMALS:
            if item is not None:
                _require(isinstance(item, str) and len(item) <= 128, "chart_numeric_type")
                try:
                    parsed = Decimal(item)
                except Exception as exc:
                    raise SavedTechnicalChartError("chart_numeric_invalid") from exc
                _require(parsed.is_finite(), "chart_numeric_invalid")
                _require(key == "change" or parsed >= 0, "chart_numeric_invalid")
                result[key] = parsed
        elif key == "volume":
            _require(item is None or type(item) is int and item >= 0, "chart_volume_invalid")
        else:
            _require(isinstance(item, str) and len(item) <= 4096, "chart_text_invalid")
    return cls(**result)


def _validate_rows(chart: SavedTechnicalChart) -> None:
    cutoff = _clock(chart.decision_cutoff)
    for rows in (chart.price_points, chart.technical_history):
        _require(len(rows) <= MAX_ROWS, "chart_row_limit")
        seen: set[str] = set()
        previous = ""
        for row in rows:
            try:
                day = date.fromisoformat(row.data_date)
            except ValueError as exc:
                raise SavedTechnicalChartError("chart_invalid_date") from exc
            _require(day.isoformat() == row.data_date and day <= cutoff.date(), "chart_cutoff_mismatch")
            _require(row.data_date not in seen and row.data_date > previous, "chart_duplicate_or_unsorted_date")
            seen.add(row.data_date)
            previous = row.data_date
            _require(not row.available_at or _clock(row.available_at) <= cutoff, "chart_future_availability")
            if isinstance(row, StockPricePointDTO):
                _require(row.source_id == "sqlite.daily_prices", "chart_price_source_mismatch")
                expected = stock_price_row_fingerprint_sha256(
                    stock_code=chart.stock_code, data_date=row.data_date,
                    open_price=row.open_price, high_price=row.high_price, low_price=row.low_price,
                    close_price=row.close_price, volume=row.volume, turnover=row.turnover,
                )
                _require(row.source_snapshot_hash == expected, "chart_price_hash_mismatch")
            else:
                _require(row.stock_code == chart.stock_code and row.source_id == "sqlite.technical_indicators", "chart_technical_source_mismatch")
                _require(row.data_date in {point.data_date for point in chart.price_points}, "chart_technical_date_mismatch")
                expected = stock_technical_history_row_fingerprint_sha256(
                    stock_code=row.stock_code, source_id=row.source_id, data_date=row.data_date,
                    ma20=row.ma20, ma60=row.ma60, available_at=row.available_at,
                )
                _require(row.source_row_hash == expected, "chart_technical_hash_mismatch")


def build_saved_technical_chart(
    *, stock_code: str, decision_cutoff: datetime, scope_identity: str,
    input_fingerprint_sha256: str, price_points: Sequence[StockPricePointDTO],
    technical_history: Sequence[StockTechnicalHistoryRowDTO],
) -> dict[str, Any]:
    def serialize(row: Any) -> dict[str, Any]:
        return {key: str(value) if isinstance(value, Decimal) else value for key, value in asdict(row).items()}

    header = dict(schema_version=SCHEMA, stock_code=stock_code, decision_cutoff=decision_cutoff.isoformat(),
                  scope_identity=scope_identity, input_fingerprint_sha256=input_fingerprint_sha256)
    raw = canonical({**header, "price_points": [serialize(row) for row in price_points],
                     "technical_history": [serialize(row) for row in technical_history]})
    _require(len(raw) <= MAX_RAW_BYTES, "chart_raw_byte_limit")
    envelope = {**header, "content_sha256": hashlib.sha256(raw).hexdigest(),
                "uncompressed_bytes": len(raw), "payload_zlib_base64": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}
    _require(len(canonical(envelope)) <= MAX_ENVELOPE_BYTES, "chart_envelope_byte_limit")
    read_saved_technical_chart(envelope, stock_code=stock_code, decision_date=decision_cutoff.date(),
                               scope_identity=scope_identity, input_fingerprint_sha256=input_fingerprint_sha256)
    return envelope


def read_saved_technical_chart(
    envelope: Mapping[str, Any], *, stock_code: str, decision_date: date,
    scope_identity: str, input_fingerprint_sha256: str,
) -> SavedTechnicalChart:
    _require(isinstance(envelope, Mapping) and set(envelope) == _HEADER | {"content_sha256", "uncompressed_bytes", "payload_zlib_base64"}, "chart_schema")
    _require(envelope["schema_version"] == SCHEMA, "chart_version")
    _require(envelope["stock_code"] == stock_code and envelope["scope_identity"] == scope_identity and bool(scope_identity), "chart_identity_mismatch")
    _require(envelope["input_fingerprint_sha256"] == input_fingerprint_sha256 and _sha(input_fingerprint_sha256), "chart_input_hash_mismatch")
    _require(_clock(envelope["decision_cutoff"]).date() == decision_date, "chart_cutoff_mismatch")
    size = envelope["uncompressed_bytes"]
    _require(type(size) is int and 0 <= size <= MAX_RAW_BYTES, "chart_raw_byte_limit")
    _require(_sha(envelope["content_sha256"]) and len(canonical(envelope)) <= MAX_ENVELOPE_BYTES, "chart_envelope_invalid")
    try:
        zipped = base64.b64decode(envelope["payload_zlib_base64"], validate=True)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(zipped, MAX_RAW_BYTES + 1)
        _require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail and len(raw) == size, "chart_compression_invalid")
        _require(hashlib.sha256(raw).hexdigest() == envelope["content_sha256"], "chart_content_hash_mismatch")
        payload = json.loads(raw)
    except SavedTechnicalChartError:
        raise
    except Exception as exc:
        raise SavedTechnicalChartError("chart_payload_invalid") from exc
    _require(canonical(payload) == raw and isinstance(payload, dict) and set(payload) == _HEADER | {"price_points", "technical_history"}, "chart_payload_schema")
    _require(all(payload[key] == envelope[key] for key in _HEADER), "chart_payload_identity_mismatch")
    _require(all(isinstance(payload[key], list) and len(payload[key]) <= MAX_ROWS for key in ("price_points", "technical_history")), "chart_row_limit")
    result = SavedTechnicalChart(stock_code, envelope["decision_cutoff"], scope_identity, input_fingerprint_sha256,
                                 envelope["content_sha256"], tuple(_row(row, StockPricePointDTO) for row in payload["price_points"]),
                                 tuple(_row(row, StockTechnicalHistoryRowDTO) for row in payload["technical_history"]))
    _validate_rows(result)
    return result
