"""Registry equity 快照的實際日期保留工具。"""

from __future__ import annotations

from datetime import date, datetime
from numbers import Integral
import re

import pandas as pd


_DATE_COLUMN_NAMES = ("date", "日期")
_ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_COMPACT_DATE_PATTERN = re.compile(r"\d{8}\Z")


class ResearchRunDatedEquityError(ValueError):
    """日期曲線缺少可驗證的逐列日期。"""


def research_run_dated_equity_copy(equity: pd.DataFrame) -> pd.DataFrame:
    """複製 equity，確保 index=False 保存時每列仍帶有實際日期。

    僅接受 producer 已提供的 `date`/`日期` 欄位或 DatetimeIndex；不從
    requested metadata 推導日期，也不把整數 index 當 Unix epoch 解讀。
    原始金額、其他欄位、列順序及 attrs 均保留。
    """

    if not isinstance(equity, pd.DataFrame):
        raise TypeError("equity 必須是 pandas DataFrame")
    if equity.empty:
        raise ResearchRunDatedEquityError("equity 曲線不可為空")
    if equity.columns.has_duplicates:
        raise ResearchRunDatedEquityError("equity 欄名重複，無法確認日期欄")

    date_columns = [name for name in _DATE_COLUMN_NAMES if name in equity.columns]
    if len(date_columns) > 1:
        raise ResearchRunDatedEquityError("equity 同時包含多個日期欄，來源不明確")

    if date_columns:
        date_column = date_columns[0]
        date_keys = _validated_daily_date_keys(
            equity[date_column].tolist(), source=f"日期欄 {date_column}"
        )
        if isinstance(equity.index, pd.DatetimeIndex):
            index_keys = _validated_daily_date_keys(
                equity.index.tolist(), source="DatetimeIndex"
            )
            if date_keys != index_keys:
                raise ResearchRunDatedEquityError(
                    "既有日期欄與 DatetimeIndex 不一致"
                )
        return equity.copy(deep=True)

    if not isinstance(equity.index, pd.DatetimeIndex):
        raise ResearchRunDatedEquityError(
            "equity 必須有 date/日期 欄或 DatetimeIndex；拒絕推測數字 index 日期及 epoch 誤判"
        )

    _validated_daily_date_keys(equity.index.tolist(), source="DatetimeIndex")
    copied = equity.copy(deep=True)
    copied.insert(0, "date", equity.index.copy())
    return copied


def _validated_daily_date_keys(
    values: list[object], *, source: str
) -> tuple[tuple[int, int, int], ...]:
    if not values:
        raise ResearchRunDatedEquityError(f"{source} 不可為空")

    keys = tuple(_calendar_date_key(value, source=source) for value in values)
    if len(set(keys)) != len(keys):
        raise ResearchRunDatedEquityError(f"{source} 含重複日期")
    if any(previous >= current for previous, current in zip(keys, keys[1:])):
        raise ResearchRunDatedEquityError(f"{source} 必須嚴格遞增")
    return keys


def _calendar_date_key(value: object, *, source: str) -> tuple[int, int, int]:
    parsed: pd.Timestamp
    if isinstance(value, pd.Timestamp):
        parsed = value
    elif isinstance(value, datetime):
        parsed = pd.Timestamp(value)
    elif isinstance(value, date):
        parsed = pd.Timestamp(value)
    elif isinstance(value, str):
        text = value.strip()
        if _ISO_DATE_PATTERN.fullmatch(text):
            parsed = _parse_formatted_date(text, "%Y-%m-%d", source=source)
        elif _COMPACT_DATE_PATTERN.fullmatch(text):
            parsed = _parse_formatted_date(text, "%Y%m%d", source=source)
        else:
            raise ResearchRunDatedEquityError(
                f"{source} 含非明確日期字串；僅接受 YYYY-MM-DD 或 YYYYMMDD"
            )
    elif isinstance(value, Integral) and not isinstance(value, bool):
        text = str(int(value))
        if not _COMPACT_DATE_PATTERN.fullmatch(text):
            raise ResearchRunDatedEquityError(
                f"{source} 含非 YYYYMMDD 整數日期；拒絕 epoch 誤判"
            )
        parsed = _parse_formatted_date(text, "%Y%m%d", source=source)
    else:
        raise ResearchRunDatedEquityError(f"{source} 含不支援或缺失的日期值")

    if pd.isna(parsed):
        raise ResearchRunDatedEquityError(f"{source} 含缺失日期")
    return int(parsed.year), int(parsed.month), int(parsed.day)


def _parse_formatted_date(value: str, date_format: str, *, source: str) -> pd.Timestamp:
    try:
        return pd.Timestamp(datetime.strptime(value, date_format))
    except ValueError as exc:
        raise ResearchRunDatedEquityError(f"{source} 含無效日曆日期") from exc
