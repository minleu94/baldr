"""保存單股策略實際研究窗的共同價量；不推論原件權威、PIT或日曆完整。"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any

import pandas as pd

SCHEMA = "saved-strategy-signal-price-window.v1"
NORMALIZATION = "consumed-ohlcv-decimal-text.v1"
MAX_ROWS = 20000
_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
_ALIASES = {
    "Open": ("開盤價", "Open", "open", "開盤"),
    "High": ("最高價", "High", "high", "最高"),
    "Low": ("最低價", "Low", "low", "最低"),
    "Close": ("收盤價", "Close", "close", "收盤"),
    "Volume": ("成交股數", "成交量", "Volume", "volume"),
}


def has_strategy_signal_prices(frame: pd.DataFrame) -> bool:
    """沿原typed策略／next-open的價量欄位順序辨認輸入，不以Close補Open。"""
    return all(any(alias in frame.columns for alias in aliases) for aliases in _ALIASES.values())


def _date(value: Any) -> date:
    if type(value) is not str:
        raise ValueError("價量日期必須是ISO日期文字")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("價量日期不是canonical ISO格式")
    return parsed


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _number(value: Any) -> str | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, bool):
        raise ValueError("價量輸入不能是布林值")
    try:
        number = Decimal(str(value))
    except (ValueError, InvalidOperation) as error:
        raise ValueError("價量輸入無法保真保存") from error
    if number.is_nan():
        return None
    if not number.is_finite() or abs(number.adjusted()) > 100 or len(number.as_tuple().digits) > 128:
        raise ValueError("價量輸入超出有限數值範圍")
    if number.is_zero():
        return "0"
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def capture_strategy_signal_context(frame: pd.DataFrame, *, stock_code: str, start_date: str, end_date: str) -> dict[str, Any]:
    """只擷取同次executor消費的原價量窗；不同暖機不改這份共同身分。"""
    if (not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is not None
            or frame.index.hasnans or frame.index.has_duplicates or frame.columns.has_duplicates or not frame.index.is_monotonic_increasing
            or not has_strategy_signal_prices(frame)):
        raise ValueError("訊號對照需要唯一遞增的每日OHLCV輸入")
    start, end = _date(start_date), _date(end_date)
    if start > end or not stock_code.strip():
        raise ValueError("訊號對照股票或研究窗無效")
    window = frame.loc[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
    if not 1 <= len(window) <= MAX_ROWS:
        raise ValueError("訊號對照價量列數超界或為空")
    columns = {name: next(alias for alias in aliases if alias in frame.columns) for name, aliases in _ALIASES.items()}
    # 多個原別名同時存在時，保留未知亦不能用另一欄補值或掩蓋不同價量。
    for name, aliases in _ALIASES.items():
        chosen = tuple(_number(value) for value in window[columns[name]])
        if any(tuple(_number(value) for value in window[alias]) != chosen for alias in aliases if alias in window.columns):
            raise ValueError("訊號對照的重複價量別名存在不同值，不可任選或補缺")
    selected = window.loc[:, list(columns.values())]
    rows = []
    for when, *values in selected.itertuples(index=True, name=None):
        if when != when.normalize():
            raise ValueError("訊號對照只接受每日觀測，不合併盤中資料")
        rows.append({"date": when.strftime("%Y-%m-%d"), **dict(zip(_COLUMNS, (_number(value) for value in values)))})
    payload = {"schema": SCHEMA, "normalization": NORMALIZATION, "stock_code": stock_code,
        "start_date": start_date, "end_date": end_date, "rows": rows,
        "input_numeric_policy": str(frame.attrs.get("price_input_preparation", "unversioned")),
        "historical_pit_eligible": False, "source_qualification": "research_only"}
    payload["sha256"] = hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()
    return payload


def validate_strategy_signal_context(raw: Any) -> dict[str, Any]:
    """驗保存內容與canonical指紋；缺舊證據不查目前行情補入。"""
    required = {"schema", "normalization", "stock_code", "start_date", "end_date", "rows", "input_numeric_policy", "historical_pit_eligible", "source_qualification", "sha256"}
    if (not isinstance(raw, dict) or set(raw) != required or raw["schema"] != SCHEMA
            or raw["normalization"] != NORMALIZATION or raw["historical_pit_eligible"] is not False
            or not isinstance(raw["input_numeric_policy"], str) or not raw["input_numeric_policy"].strip()
            or raw["source_qualification"] != "research_only" or not isinstance(raw["stock_code"], str) or not raw["stock_code"].strip()):
        raise ValueError("缺少或不支援保存訊號的共同價量版本；請保留舊run並另做新研究")
    start, end = _date(raw["start_date"]), _date(raw["end_date"])
    rows = raw["rows"]
    if start > end or not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError("保存訊號的共同價量窗超界")
    previous = None
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"date", *_COLUMNS}:
            raise ValueError("保存訊號的共同價量列缺件")
        when = _date(row["date"])
        if not start <= when <= end or previous is not None and when <= previous:
            raise ValueError("保存訊號的共同價量日期不符或重複")
        for name in _COLUMNS:
            value = row[name]
            if value is not None and (type(value) is not str or _number(value) != value):
                raise ValueError("保存價量不是原canonical數值文字")
        previous = when
    digest = hashlib.sha256(_json({key: value for key, value in raw.items() if key != "sha256"}).encode("utf-8")).hexdigest()
    if raw["sha256"] != digest:
        raise ValueError("保存訊號的共同價量SHA不符")
    return json.loads(_json(raw))
