"""將同次推薦的既有來源 frame 封存為有界圖表；不查資料庫、重算均線或改排名。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, NoReturn

import pandas as pd

from app_module.recommendation_portfolio_dates import parse_stock_dates
from app_module.saved_stock_technical_chart import (
    MAX_ROWS,
    SavedTechnicalChart,
    SavedTechnicalChartError,
    build_saved_technical_chart,
    read_saved_technical_chart,
)
from app_module.stock_research_report_dtos import (
    StockPricePointDTO,
    StockTechnicalHistoryRowDTO,
    stock_technical_history_row_fingerprint_sha256,
)
from app_module.stock_research_report_provider_adapters import stock_price_row_fingerprint_sha256


CAPTURE_SCHEMA = "recommendation-saved-technical-charts.v1"
MAX_CHARTS = 64
MAX_CAPTURE_BYTES = 2 * 1024 * 1024
PRICE_SOURCE_ID = "recommendation.market_frame"
TECHNICAL_SOURCE_ID = "recommendation.market_frame.indicators"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CODE = re.compile(r"^\d{4,6}$")
_CAPTURE_KEYS = {
    "schema_version", "result_id", "source_id", "market_data_fingerprint",
    "decision_cutoff", "stock_codes", "selected_count", "chart_count",
    "missing_count", "missing_counts", "charts", "missing", "status",
    "research_only", "historical_pit_eligible", "capture_sha256",
}
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("日期", "Date", "date", "data_date"),
    "open_price": ("開盤價", "Open", "open", "open_price"),
    "high_price": ("最高價", "High", "high", "high_price"),
    "low_price": ("最低價", "Low", "low", "low_price"),
    "close_price": ("收盤價", "Close", "close", "close_price"),
    "volume": ("成交股數", "成交量", "Volume", "volume"),
    "turnover": ("成交金額", "turnover", "Turnover"),
    "ma20": ("MA20", "ma20"),
    "ma60": ("MA60", "ma60"),
}
_MISSING_REASONS = {
    "capture_byte_limit", "chart_count_limit", "chart_validation_failed",
    "date_column_missing", "duplicate_dates", "incomplete_ohlc",
    "invalid_close_price", "invalid_high_price", "invalid_low_price",
    "invalid_ma20", "invalid_ma60", "invalid_open_price", "invalid_turnover",
    "invalid_volume", "no_rows_on_or_before_cutoff", "stock_column_missing",
    "stock_rows_missing",
}


class RecommendationSavedChartError(ValueError):
    """有界圖表封存或 exact 重讀核驗失敗。"""


class _ProjectionError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text(value: object, field: str, limit: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > limit:
        raise RecommendationSavedChartError(f"{field}_invalid")
    return value


def _cutoff_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise RecommendationSavedChartError("decision_cutoff_timezone_missing")
    return value.isoformat()


def chart_scope_identity(result_id: str, source_id: str, market_data_fingerprint: str) -> str:
    """結果與來源版本範圍的穩定 raw SHA-256 身份。"""
    result = _text(result_id, "result_id")
    source = _text(source_id, "source_id")
    market = _text(market_data_fingerprint, "market_data_fingerprint")
    return _hash({"schema_version": CAPTURE_SCHEMA, "result_id": result,
                  "source_id": source, "market_data_fingerprint": market})


def chart_input_fingerprint(
    result_id: str, source_id: str, market_data_fingerprint: str,
    stock_code: str, decision_cutoff: datetime,
) -> str:
    """核對結果／來源／版本／股號／截止時間的輸入指紋。"""
    scope = chart_scope_identity(result_id, source_id, market_data_fingerprint)
    code = _text(stock_code, "stock_code", 6)
    if not _CODE.fullmatch(code):
        raise RecommendationSavedChartError("stock_code_invalid")
    return _hash({"schema_version": CAPTURE_SCHEMA, "scope_identity": scope,
                  "stock_code": code, "decision_cutoff": _cutoff_text(decision_cutoff)})


def _normal_json(value: object, depth: int = 0) -> Any:
    """將凍結 Mapping／tuple 正規化為 canonical JSON 相容值。"""
    if depth > 32:
        raise RecommendationSavedChartError("capture_nesting_limit")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise RecommendationSavedChartError("capture_mapping_key_invalid")
        return {key: _normal_json(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normal_json(item, depth + 1) for item in value]
    if value is None or type(value) in {str, int, bool}:
        return value
    raise RecommendationSavedChartError("capture_value_not_json_compatible")


def _frame_value_decimal(value: object, field: str, *, allow_missing: bool = True) -> Decimal | None:
    if value is None:
        return None if allow_missing else _raise_projection(f"invalid_{field}")
    try:
        if bool(pd.isna(value)):
            return None if allow_missing else _raise_projection(f"invalid_{field}")
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        raise _ProjectionError(f"invalid_{field}")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise _ProjectionError(f"invalid_{field}") from exc
    if not parsed.is_finite():
        raise _ProjectionError(f"invalid_{field}")
    return parsed


def _raise_projection(reason: str) -> NoReturn:
    raise _ProjectionError(reason)


def _volume(value: object) -> int | None:
    parsed = _frame_value_decimal(value, "volume")
    if parsed is None:
        return None
    if parsed < 0 or parsed != parsed.to_integral_value():
        raise _ProjectionError("invalid_volume")
    return int(parsed)


def _code_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _find_column(columns: Sequence[object], key: str) -> str | None:
    return next((alias for alias in _COLUMN_ALIASES[key] if alias in columns), None)


def _capture_body(
    *, result_id: str, source_id: str, market_data_fingerprint: str,
    cutoff: str, stock_codes: list[str], charts: dict[str, dict[str, Any]],
    missing: dict[str, str],
) -> dict[str, Any]:
    missing_counts = dict(sorted(Counter(missing.values()).items()))
    body: dict[str, Any] = {
        "schema_version": CAPTURE_SCHEMA,
        "result_id": result_id,
        "source_id": source_id,
        "market_data_fingerprint": market_data_fingerprint,
        "decision_cutoff": cutoff,
        "stock_codes": stock_codes,
        "selected_count": len(stock_codes),
        "chart_count": len(charts),
        "missing_count": len(missing),
        "missing_counts": missing_counts,
        "charts": charts,
        "missing": missing,
        "status": "partial" if missing else "complete",
        "research_only": True,
        "historical_pit_eligible": False,
    }
    body["capture_sha256"] = _hash(body)
    return body


def _prepare_frame(frame: pd.DataFrame, stock_column: str, cutoff: date) -> tuple[list[dict[str, Any]], dict[str, str | None]]:
    if not isinstance(frame, pd.DataFrame):
        raise RecommendationSavedChartError("prepared_frame_required")
    if frame.columns.duplicated().any():
        raise RecommendationSavedChartError("prepared_frame_duplicate_columns")
    if stock_column not in frame.columns:
        return [], {"stock_column": None}
    date_column = _find_column(tuple(frame.columns), "date")
    if date_column is None:
        return [], {"date": None}
    mapping = {key: _find_column(tuple(frame.columns), key) for key in _COLUMN_ALIASES}
    # OHLC 必須完整；量、成交金額與指標可明示缺值。
    if any(mapping[key] is None for key in ("open_price", "high_price", "low_price", "close_price")):
        return [], mapping
    work = frame.reset_index(drop=True).copy()
    parsed_dates = parse_stock_dates(work[date_column]).tolist()
    normalized_dates: list[str | None] = []
    for parsed in parsed_dates:
        if pd.isna(parsed):
            normalized_dates.append(None)
        else:
            parsed_date = parsed.date() if hasattr(parsed, "date") else pd.Timestamp(parsed).date()
            normalized_dates.append(parsed_date.isoformat() if parsed_date <= cutoff else None)
    work["_recommendation_chart_stock"] = work[stock_column].map(_code_value)
    work["_recommendation_chart_date"] = normalized_dates
    work = work[work["_recommendation_chart_date"].notna()]
    work = work.sort_values(["_recommendation_chart_stock", "_recommendation_chart_date"], kind="stable")
    work = work.groupby("_recommendation_chart_stock", sort=False).tail(MAX_ROWS)
    records = work.to_dict(orient="records")
    return records, mapping


def _project_symbol(
    records: list[dict[str, Any]], mapping: dict[str, str | None], stock_code: str,
    *, result_id: str, source_id: str, market_data_fingerprint: str,
    decision_cutoff: datetime, scope: str,
) -> dict[str, Any]:
    code_rows = [row for row in records if row["_recommendation_chart_stock"] == stock_code]
    if not code_rows:
        raise _ProjectionError("no_rows_on_or_before_cutoff")
    code_rows.sort(key=lambda row: row["_recommendation_chart_date"])
    rows = code_rows[-MAX_ROWS:]
    days = [row["_recommendation_chart_date"] for row in rows]
    if len(days) != len(set(days)):
        raise _ProjectionError("duplicate_dates")
    prices: list[StockPricePointDTO] = []
    technical: list[StockTechnicalHistoryRowDTO] = []
    for row in rows:
        day = row["_recommendation_chart_date"]
        decimals: dict[str, Decimal | None] = {}
        for field in ("open_price", "high_price", "low_price", "close_price"):
            column = mapping[field]
            if column is None:
                raise _ProjectionError("incomplete_ohlc")
            raw = row.get(column)
            parsed = _frame_value_decimal(raw, field)
            if parsed is None:
                raise _ProjectionError("incomplete_ohlc")
            if parsed < 0:
                raise _ProjectionError(f"invalid_{field}")
            decimals[field] = parsed
        volume_column = mapping["volume"]
        turnover_column = mapping["turnover"]
        raw_volume = row.get(volume_column) if volume_column is not None else None
        raw_turnover = row.get(turnover_column) if turnover_column is not None else None
        volume = _volume(raw_volume)
        turnover = _frame_value_decimal(raw_turnover, "turnover")
        if turnover is not None and turnover < 0:
            raise _ProjectionError("invalid_turnover")
        price_hash = stock_price_row_fingerprint_sha256(
            stock_code=stock_code, data_date=day,
            open_price=decimals["open_price"], high_price=decimals["high_price"],
            low_price=decimals["low_price"], close_price=decimals["close_price"],
            volume=volume, turnover=turnover,
        )
        prices.append(StockPricePointDTO(
            data_date=day, open_price=decimals["open_price"], high_price=decimals["high_price"],
            low_price=decimals["low_price"], close_price=decimals["close_price"],
            volume=volume, turnover=turnover, available_at="", source_id=PRICE_SOURCE_ID,
            source_snapshot_hash=price_hash,
        ))
        indicators: dict[str, Decimal | None] = {}
        for field in ("ma20", "ma60"):
            column = mapping[field]
            raw = row.get(column) if column is not None else None
            value = _frame_value_decimal(raw, field)
            if value is not None and value < 0:
                raise _ProjectionError(f"invalid_{field}")
            indicators[field] = value
        technical_hash = stock_technical_history_row_fingerprint_sha256(
            stock_code=stock_code, source_id=TECHNICAL_SOURCE_ID, data_date=day,
            ma20=indicators["ma20"], ma60=indicators["ma60"], available_at="",
        )
        technical.append(StockTechnicalHistoryRowDTO(
            stock_code=stock_code, source_id=TECHNICAL_SOURCE_ID, data_date=day,
            source_row_hash=technical_hash, ma20=indicators["ma20"], ma60=indicators["ma60"],
            available_at="",
        ))
    input_hash = chart_input_fingerprint(
        result_id, source_id, market_data_fingerprint, stock_code, decision_cutoff,
    )
    return build_saved_technical_chart(
        stock_code=stock_code, decision_cutoff=decision_cutoff,
        scope_identity=scope, input_fingerprint_sha256=input_hash,
        price_points=prices, technical_history=technical,
    )


def build_recommendation_chart_capture(
    *, frame: pd.DataFrame, stock_column: str, stock_codes: Sequence[str],
    result_id: str, source_id: str, market_data_fingerprint: str,
    decision_cutoff: datetime,
) -> dict[str, Any]:
    """將同次已過濾的推薦來源列投影為有界唯讀圖表。"""
    result = _text(result_id, "result_id")
    source = _text(source_id, "source_id")
    market = _text(market_data_fingerprint, "market_data_fingerprint")
    stock_col = _text(stock_column, "stock_column", 256)
    cutoff_text = _cutoff_text(decision_cutoff)
    if not isinstance(stock_codes, Sequence) or isinstance(stock_codes, (str, bytes)):
        raise RecommendationSavedChartError("stock_codes_sequence_required")
    codes = list(stock_codes)
    if any(not isinstance(code, str) or not _CODE.fullmatch(code) for code in codes):
        raise RecommendationSavedChartError("stock_code_invalid")
    if len(codes) != len(set(codes)):
        raise RecommendationSavedChartError("stock_code_duplicate")
    try:
        code_bytes = _canonical(codes)
    except (TypeError, ValueError) as exc:
        raise RecommendationSavedChartError("stock_codes_not_json") from exc
    if len(code_bytes) > MAX_CAPTURE_BYTES:
        raise RecommendationSavedChartError("capture_stock_code_byte_limit")
    scope = chart_scope_identity(result, source, market)
    charts: dict[str, dict[str, Any]] = {}
    missing: dict[str, str] = {}
    if len(codes) > MAX_CHARTS:
        missing = {code: "chart_count_limit" for code in codes}
    else:
        selected_frame = (frame.loc[frame[stock_col].map(_code_value).isin(codes)]
                          if stock_col in frame.columns else frame)
        records, mapping = _prepare_frame(selected_frame, stock_col, decision_cutoff.date())
        for code in codes:
            if stock_col not in frame.columns:
                missing[code] = "stock_column_missing"
                continue
            if mapping.get("date") is None:
                missing[code] = "date_column_missing"
                continue
            if any(mapping.get(key) is None for key in ("open_price", "high_price", "low_price", "close_price")):
                missing[code] = "incomplete_ohlc"
                continue
            try:
                charts[code] = _project_symbol(
                    records, mapping, code, result_id=result, source_id=source,
                    market_data_fingerprint=market, decision_cutoff=decision_cutoff,
                    scope=scope,
                )
            except (_ProjectionError, SavedTechnicalChartError, ValueError, TypeError) as exc:
                reason = str(exc)
                missing[code] = reason if reason in _MISSING_REASONS else "chart_validation_failed"
    capture = _capture_body(
        result_id=result, source_id=source, market_data_fingerprint=market,
        cutoff=cutoff_text, stock_codes=codes, charts=charts, missing=missing,
    )
    if len(_canonical(capture)) > MAX_CAPTURE_BYTES:
        if len(codes) > MAX_CHARTS:
            raise RecommendationSavedChartError("capture_byte_limit")
        capture = _capture_body(
            result_id=result, source_id=source, market_data_fingerprint=market,
            cutoff=cutoff_text, stock_codes=codes, charts={},
            missing={code: "capture_byte_limit" for code in codes},
        )
    if len(_canonical(capture)) > MAX_CAPTURE_BYTES:
        raise RecommendationSavedChartError("capture_byte_limit")
    return capture


def _validate_capture(capture: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, SavedTechnicalChart]]:
    normalized = _normal_json(capture)
    if len(_canonical(normalized)) > MAX_CAPTURE_BYTES:
        raise RecommendationSavedChartError("capture_byte_limit")
    if not isinstance(normalized, dict) or set(normalized) != _CAPTURE_KEYS:
        raise RecommendationSavedChartError("capture_schema_invalid")
    if normalized.get("schema_version") != CAPTURE_SCHEMA:
        raise RecommendationSavedChartError("capture_version_mismatch")
    unsigned = {key: value for key, value in normalized.items() if key != "capture_sha256"}
    if normalized.get("capture_sha256") != _hash(unsigned):
        raise RecommendationSavedChartError("capture_hash_mismatch")
    result = _text(normalized.get("result_id"), "result_id")
    source = _text(normalized.get("source_id"), "source_id")
    market = _text(normalized.get("market_data_fingerprint"), "market_data_fingerprint")
    cutoff = normalized.get("decision_cutoff")
    try:
        parsed_cutoff = datetime.fromisoformat(cutoff) if isinstance(cutoff, str) else None
    except ValueError as exc:
        raise RecommendationSavedChartError("capture_cutoff_invalid") from exc
    if parsed_cutoff is None or parsed_cutoff.tzinfo is None or parsed_cutoff.utcoffset() is None:
        raise RecommendationSavedChartError("capture_cutoff_invalid")
    if normalized.get("research_only") is not True or normalized.get("historical_pit_eligible") is not False:
        raise RecommendationSavedChartError("capture_safety_flags_invalid")
    codes, charts, missing = normalized.get("stock_codes"), normalized.get("charts"), normalized.get("missing")
    if (not isinstance(codes, list) or any(not isinstance(code, str) or not _CODE.fullmatch(code) for code in codes)
            or len(codes) != len(set(codes)) or not isinstance(charts, dict) or not isinstance(missing, dict)):
        raise RecommendationSavedChartError("capture_population_invalid")
    if type(normalized.get("selected_count")) is not int or normalized["selected_count"] != len(codes):
        raise RecommendationSavedChartError("capture_selected_count_mismatch")
    if type(normalized.get("chart_count")) is not int or normalized["chart_count"] != len(charts):
        raise RecommendationSavedChartError("capture_chart_count_mismatch")
    if type(normalized.get("missing_count")) is not int or normalized["missing_count"] != len(missing):
        raise RecommendationSavedChartError("capture_missing_count_mismatch")
    if len(charts) > MAX_CHARTS or set(charts).intersection(missing) or set(charts).union(missing) != set(codes):
        raise RecommendationSavedChartError("capture_code_partition_invalid")
    if any(not isinstance(reason, str) or reason not in _MISSING_REASONS for reason in missing.values()):
        raise RecommendationSavedChartError("capture_missing_reason_invalid")
    expected_counts = dict(sorted(Counter(missing.values()).items()))
    if normalized.get("missing_counts") != expected_counts:
        raise RecommendationSavedChartError("capture_missing_counts_mismatch")
    expected_status = "partial" if missing else "complete"
    if normalized.get("status") != expected_status:
        raise RecommendationSavedChartError("capture_status_mismatch")
    if len(codes) > MAX_CHARTS and (charts or any(reason != "chart_count_limit" for reason in missing.values())):
        raise RecommendationSavedChartError("capture_chart_bound_mismatch")
    scope = chart_scope_identity(result, source, market)
    saved: dict[str, SavedTechnicalChart] = {}
    for code, envelope in charts.items():
        if not isinstance(envelope, dict):
            raise RecommendationSavedChartError("capture_chart_schema_invalid")
        expected_input = chart_input_fingerprint(result, source, market, code, parsed_cutoff)
        try:
            chart = read_saved_technical_chart(
                envelope, stock_code=code, decision_date=parsed_cutoff.date(),
                scope_identity=scope, input_fingerprint_sha256=expected_input,
            )
        except SavedTechnicalChartError as exc:
            raise RecommendationSavedChartError(f"capture_chart_invalid:{exc}") from exc
        if chart.decision_cutoff != cutoff:
            raise RecommendationSavedChartError("capture_chart_cutoff_mismatch")
        if any(point.source_id != PRICE_SOURCE_ID for point in chart.price_points):
            raise RecommendationSavedChartError("capture_price_source_mismatch")
        if any(row.source_id != TECHNICAL_SOURCE_ID for row in chart.technical_history):
            raise RecommendationSavedChartError("capture_technical_source_mismatch")
        if tuple(point.data_date for point in chart.price_points) != tuple(
                row.data_date for row in chart.technical_history):
            raise RecommendationSavedChartError("capture_chart_history_mismatch")
        saved[code] = chart
    return normalized, saved


def read_recommendation_chart_capture(
    capture: Mapping[str, Any], *, stock_code: str, result_id: str,
    source_id: str, market_data_fingerprint: str, decision_cutoff: datetime,
) -> SavedTechnicalChart | None:
    """只讀 exact pins 對應股號的封存圖表，不借最新資料。"""
    normalized, charts = _validate_capture(capture)
    code = _text(stock_code, "stock_code", 6)
    if not _CODE.fullmatch(code):
        raise RecommendationSavedChartError("stock_code_invalid")
    expected = {
        "result_id": _text(result_id, "result_id"),
        "source_id": _text(source_id, "source_id"),
        "market_data_fingerprint": _text(market_data_fingerprint, "market_data_fingerprint"),
        "decision_cutoff": _cutoff_text(decision_cutoff),
    }
    if any(normalized.get(key) != value for key, value in expected.items()):
        raise RecommendationSavedChartError("capture_scope_mismatch")
    if code not in normalized["stock_codes"]:
        raise RecommendationSavedChartError("capture_stock_code_not_selected")
    return charts.get(code)


__all__ = [
    "CAPTURE_SCHEMA", "MAX_CAPTURE_BYTES", "MAX_CHARTS", "RecommendationSavedChartError",
    "build_recommendation_chart_capture", "chart_input_fingerprint", "chart_scope_identity",
    "read_recommendation_chart_capture",
]
