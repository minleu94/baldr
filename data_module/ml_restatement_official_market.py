"""核驗現在取得的官方大盤歷史月報，供隔離修訂研究使用。

只讀封存回應；不接觸正式資料庫，不追認歷史 PIT。成交量固定為
FMTQIK 的成交股數，開高低收固定來自 MI_5MINS_HIST，不用收盤代填。
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo


REPORT_FIELDS = {
    "FMTQIK": (
        "日期", "成交股數", "成交金額", "成交筆數", "發行量加權股價指數", "漲跌點數",
    ),
    "MI_5MINS_HIST": ("日期", "開盤指數", "最高指數", "最低指數", "收盤指數"),
}
REPORT_PATHS = {
    "FMTQIK": "/rwd/zh/afterTrading/FMTQIK",
    "MI_5MINS_HIST": "/indicesReport/MI_5MINS_HIST",
}
_NUMBER = re.compile(r"^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$")
_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
_TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class OfficialMarketCapture:
    """已從原始回應重新驗算的獨立來源；values 均為 Decimal。"""

    manifest_path: Path
    manifest_file_sha256: str
    available_at: datetime
    cutoff_date: date
    rows: Mapping[date, Mapping[str, Any]]
    response_hashes: tuple[tuple[str, str], ...]
    original_calendar_missing: tuple[date, ...]
    additional_official_dates: tuple[date, ...]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _clock(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name}: 缺少實際時鐘")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name}: 時鐘須含時區")
    return result


def _number(value: Any) -> Decimal:
    if not isinstance(value, str) or not _NUMBER.fullmatch(value):
        raise ValueError("官方數值格式或千分位分組不合法")
    try:
        result = Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("官方數值無法解析") from exc
    if not result.is_finite():
        raise ValueError("官方數值不是有限值")
    return result


def parse_monthly_report(
    payload: Mapping[str, Any], *, report: str, month: str,
) -> dict[date, dict[str, Decimal]]:
    """驗證報表種類、原始欄序、月份、日期唯一性與精確數值。"""
    if report not in REPORT_FIELDS or not re.fullmatch(r"\d{6}", month):
        raise ValueError("不支援的官方報表或月份")
    date(int(month[:4]), int(month[4:]), 1)
    fields = REPORT_FIELDS[report]
    if (
        payload.get("stat") != "OK"
        or payload.get("date") != month + "01"
        or payload.get("fields") != list(fields)
    ):
        raise ValueError("官方報表狀態、月份或欄位不符")
    raw_rows = payload.get("data")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("官方報表缺少交易日資料")
    result: dict[date, dict[str, Decimal]] = {}
    previous: date | None = None
    for raw in raw_rows:
        if not isinstance(raw, list) or len(raw) != len(fields):
            raise ValueError("官方報表欄位長度不符")
        if not isinstance(raw[0], str) or not re.fullmatch(r"\d{3}/\d{2}/\d{2}", raw[0]):
            raise ValueError("官方日期須為民國年月日")
        year, number, day = (int(part) for part in raw[0].split("/"))
        trading_day = date(year + 1911, number, day)
        if trading_day.strftime("%Y%m") != month or (previous and trading_day <= previous):
            raise ValueError("官方日期跨月、重複或未排序")
        values = {key: _number(value) for key, value in zip(fields[1:], raw[1:], strict=True)}
        if report == "FMTQIK":
            for key in ("成交股數", "成交金額", "成交筆數"):
                if values[key] < 0 or values[key] != values[key].to_integral_value():
                    raise ValueError("官方成交量值及筆數須為非負整數")
            if values["發行量加權股價指數"] <= 0:
                raise ValueError("官方收盤指數須為正值")
        else:
            opening, high, low, close = (values[key] for key in fields[1:])
            if low <= 0 or not low <= min(opening, close) <= max(opening, close) <= high:
                raise ValueError("官方 OHLC 範圍不符")
        result[trading_day] = values
        previous = trading_day
    return result


def _read_object(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("官方來源清冊或回應不是物件")
    return result


def load_official_market_capture(
    manifest_path: Path, *, expected_file_sha256: str, as_of: datetime,
) -> OfficialMarketCapture:
    """逐份重驗月報，對照清冊衍生列；不以 cached rows 代替來源。"""
    path = manifest_path.resolve(strict=True)
    if not _SHA.fullmatch(expected_file_sha256) or file_sha256(path) != expected_file_sha256:
        raise ValueError("官方來源清冊 hash 不符")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of 須含時區")
    manifest = _read_object(path)
    if (
        manifest.get("schema_version") != "official-market-source-capture.v1"
        or manifest.get("historical_pit") is not False
        or manifest.get("source_db_write") is not False
        or manifest.get("failures") != []
        or manifest.get("volume_unit") != "TWSE FMTQIK 成交股數（股）"
        or manifest.get("ohlc_source") != "TWSE MI_5MINS_HIST"
    ):
        raise ValueError("官方來源清冊不符合唯讀修訂研究契約")
    available_at = _clock(manifest.get("finished_at"), "finished_at")
    started_at = _clock(manifest.get("started_at"), "started_at")
    if started_at > available_at or available_at > as_of:
        raise ValueError("官方來源尚未可得或執行時鐘顛倒")
    cutoff = date.fromisoformat(manifest["cutoff_date"])
    if cutoff >= available_at.astimezone(_TAIPEI).date():
        raise ValueError("官方研究來源只能消費實際取得日以前的市場資料")
    months = manifest.get("months")
    if not isinstance(months, list) or not months or months != sorted(set(months)):
        raise ValueError("官方來源月份缺少、重複或未排序")
    month_numbers = []
    for month in months:
        if not isinstance(month, str) or not re.fullmatch(r"\d{6}", month):
            raise ValueError("官方來源月份格式不符")
        first = date(int(month[:4]), int(month[4:]), 1)
        month_numbers.append(first.year * 12 + first.month)
    if month_numbers != list(range(month_numbers[0], month_numbers[-1] + 1)):
        raise ValueError("官方來源月份不連續")
    if months[-1] != cutoff.strftime("%Y%m"):
        raise ValueError("官方來源截止日與最後月份不一致")
    receipts = manifest.get("receipts")
    if not isinstance(receipts, list) or len(receipts) != len(months) * 2:
        raise ValueError("官方來源每月須有兩份回應")
    parsed: dict[tuple[str, str], dict[date, dict[str, Decimal]]] = {}
    hashes: list[tuple[str, str]] = []
    for item in receipts:
        if not isinstance(item, dict):
            raise ValueError("官方來源 receipt 格式不符")
        report, month = item.get("report"), item.get("month")
        if (
            not isinstance(report, str) or not isinstance(month, str)
            or report not in REPORT_FIELDS or month not in months or (month, report) in parsed
        ):
            raise ValueError("官方來源 receipt 類型、月份或唯一性不符")
        name = f"{month}-{report}.json"
        if item.get("file") != name or item.get("historical_pit") is not False:
            raise ValueError("官方來源檔名或 PIT 宣告不符")
        url = urlparse(str(item.get("url")))
        if (
            url.scheme != "https" or url.netloc != "www.twse.com.tw"
            or url.path != REPORT_PATHS[report]
            or parse_qs(url.query) != {"date": [month + "01"], "response": ["json"]}
        ):
            raise ValueError("官方來源 URL 不符")
        captured_at = _clock(item.get("captured_at"), "captured_at")
        # 允許 resume 使用更早已封存的回應，但不能晚於本次完成時鐘。
        # 舊月份只須支援該月月底；拼接新月份不改寫舊回應的真正取得時鐘。
        year, number = int(month[:4]), int(month[4:])
        required_through = min(cutoff, date(year, number, monthrange(year, number)[1]))
        if captured_at > available_at or captured_at.astimezone(_TAIPEI).date() <= required_through:
            raise ValueError("官方回應時鐘不足以支持截止日")
        source = (path.parent / name).resolve(strict=True)
        if source.parent != path.parent or file_sha256(source) != item.get("file_sha256"):
            raise ValueError("官方回應路徑或 hash 不符")
        if source.stat().st_size != item.get("byte_count"):
            raise ValueError("官方回應 byte count 不符")
        parsed[(month, report)] = parse_monthly_report(_read_object(source), report=report, month=month)
        hashes.append((name, item["file_sha256"]))
    source_rows: dict[str, dict[str, str]] = {}
    result: dict[date, dict[str, Any]] = {}
    for month in months:
        totals = parsed[(month, "FMTQIK")]
        prices = parsed[(month, "MI_5MINS_HIST")]
        if totals.keys() != prices.keys():
            raise ValueError("官方兩報表的交易日集合不一致")
        for day in totals:
            if day > cutoff:
                continue
            t, p = totals[day], prices[day]
            if t["發行量加權股價指數"] != p["收盤指數"]:
                raise ValueError("官方兩報表收盤指數不一致")
            source_rows[day.isoformat()] = {key: str(value) for key, value in {**t, **p}.items()}
            result[day] = {
                "日期": day.strftime("%Y%m%d"), "指數名稱": "TAIEX",
                "收盤指數": p["收盤指數"], "收盤價": p["收盤指數"],
                "開盤價": p["開盤指數"], "最高價": p["最高指數"], "最低價": p["最低指數"],
                "成交量": t["成交股數"], "漲跌點數": t["漲跌點數"],
                "漲跌百分比": None,  # 官方這兩份原始回應沒有此欄，不另外設計特徵。
            }
    if manifest.get("rows") != source_rows or manifest.get("row_count") != len(result):
        raise ValueError("官方清冊的衍生列與原始回應不一致")
    missing = tuple(date.fromisoformat(value) for value in manifest["original_observed_dates_missing_official"])
    additional = tuple(date.fromisoformat(value) for value in manifest["official_additional_dates"])
    # 初版擷取工具將原資料庫含非官方交易日也記作 incomplete。
    # 只允許這個明確原因；所有月報、來源 hashes 及衍生列仍必須完整重驗。
    expected_status = "incomplete" if missing else "complete"
    if manifest.get("status") != expected_status:
        raise ValueError("官方擷取狀態與既有交易日差異不符")
    if any(day in result for day in missing) or any(day not in result for day in additional):
        raise ValueError("官方與原始交易日差異宣告不一致")
    if file_sha256(path) != expected_file_sha256:
        raise ValueError("官方來源清冊在驗證期間變更")
    for name, digest in hashes:
        if file_sha256(path.parent / name) != digest:
            raise ValueError("官方回應在驗證期間變更")
    return OfficialMarketCapture(
        path, expected_file_sha256, available_at, cutoff, result,
        tuple(sorted(hashes)), missing, additional,
    )
