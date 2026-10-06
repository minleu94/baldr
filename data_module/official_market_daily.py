"""從 TWSE 月報提供可信的大盤日資料與受控 CSV 寫入。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping
from uuid import uuid4

import pandas as pd

from .ml_restatement_official_market import REPORT_PATHS, parse_monthly_report
from .ml_storage_capacity import acquire_heavy_chain_reservation, release_heavy_chain_reservation


_TWSE_ROOT = "https://www.twse.com.tw"
MARKET_INDEX_COLUMNS = ("日期", "收盤價", "開盤價", "最高價", "最低價", "成交量")


class OfficialMarketDailyError(ValueError):
    """官方大盤月報缺件或不符合跨來源一致性時的錯誤。"""


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise OfficialMarketDailyError("請求日期格式不支援")
    for date_format in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise OfficialMarketDailyError("請求日期格式不合法")


def _month_sequence(start: date, end: date) -> list[str]:
    month = start.year * 12 + start.month - 1
    last = end.year * 12 + end.month - 1
    months: list[str] = []
    while month <= last:
        year, month_index = divmod(month, 12)
        months.append(f"{year:04d}{month_index + 1:02d}")
        month += 1
    return months


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _capture_raw_sources(
    source_dir: Path,
    *,
    start: date,
    cutoff: date,
    captures: list[dict[str, Any]],
    row_count: int,
) -> Path:
    captured_at = datetime.now(timezone.utc)
    capture_id = captured_at.strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid4().hex[:8]
    capture_dir = source_dir / "official_market_daily_sources" / capture_id
    reports: list[dict[str, Any]] = []
    capture_dir.mkdir(parents=True, exist_ok=False)
    for item in captures:
        raw_path = capture_dir / f"{item['month']}-{item['report']}.json"
        _atomic_write(raw_path, item["raw"])
        reports.append({
            "report": item["report"],
            "month": item["month"],
            "url": item["url"],
            "captured_at": item["captured_at"],
            "file": raw_path.name,
            "sha256": "sha256:" + hashlib.sha256(item["raw"]).hexdigest(),
            "byte_count": len(item["raw"]),
            "historical_pit": False,
        })
    manifest = {
        "schema_version": "official-market-daily-source-capture.v1",
        "captured_at": captured_at.isoformat(),
        "requested_start_date": start.isoformat(),
        "requested_cutoff_date": cutoff.isoformat(),
        "historical_pit": False,
        "row_count": row_count,
        "reports": reports,
    }
    manifest_path = capture_dir / "manifest.json"
    _atomic_write(
        manifest_path,
        (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    return manifest_path


def fetch_official_market_daily(
    start_date: date | datetime | str,
    end_date: date | datetime | str,
    *,
    requester: Callable[[str, Mapping[str, str]], Any],
    source_dir: Path,
    capture_manifests: list[Path] | None = None,
) -> list[dict[str, Any]]:
    """取得並核對範圍內 TWSE 官方大盤列，成交量使用股數整數。"""
    start, cutoff = _as_date(start_date), _as_date(end_date)
    if start > cutoff:
        raise OfficialMarketDailyError("請求起始日晚於截止日")

    captures: list[dict[str, Any]] = []
    by_month: dict[str, dict[str, dict[date, dict[str, Decimal]]]] = {}
    for month in _month_sequence(start, cutoff):
        reports: dict[str, dict[date, dict[str, Decimal]]] = {}
        for report in ("FMTQIK", "MI_5MINS_HIST"):
            url = _TWSE_ROOT + REPORT_PATHS[report]
            params = {"date": month + "01", "response": "json"}
            response = requester(url, params)
            if response is None:
                raise OfficialMarketDailyError(f"TWSE {report} {month} 報表無回應")
            try:
                raw = response.content
                payload = response.json()
                decoded = json.loads(raw.decode("utf-8-sig"))
            except Exception as exc:
                raise OfficialMarketDailyError(
                    f"TWSE {report} {month} 報表缺少有效原始 JSON"
                ) from exc
            if not isinstance(payload, dict) or decoded != payload:
                raise OfficialMarketDailyError(f"TWSE {report} {month} 原始回應不一致")
            try:
                parsed = parse_monthly_report(payload, report=report, month=month)
            except (TypeError, ValueError) as exc:
                raise OfficialMarketDailyError(
                    f"TWSE {report} {month} 報表驗證失敗: {exc}"
                ) from exc
            reports[report] = parsed
            captures.append({
                "month": month,
                "report": report,
                "url": f"{url}?date={month}01&response=json",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "raw": raw,
            })
        totals = reports["FMTQIK"]
        prices = reports["MI_5MINS_HIST"]
        if totals.keys() != prices.keys():
            raise OfficialMarketDailyError(f"TWSE {month} 兩份報表交易日集合不同")
        for trading_day in totals:
            if totals[trading_day]["發行量加權股價指數"] != prices[trading_day]["收盤指數"]:
                raise OfficialMarketDailyError(
                    f"TWSE {trading_day.isoformat()} 兩份報表 close 不一致"
                )
        by_month[month] = reports

    rows: list[dict[str, Any]] = []
    for month in _month_sequence(start, cutoff):
        totals = by_month[month]["FMTQIK"]
        prices = by_month[month]["MI_5MINS_HIST"]
        for trading_day in totals:
            if trading_day < start or trading_day > cutoff:
                continue
            volume = totals[trading_day]["成交股數"]
            if volume < 0 or volume != volume.to_integral_value():
                raise OfficialMarketDailyError("TWSE 成交股數不是非負整數")
            price = prices[trading_day]
            rows.append({
                "日期": trading_day.isoformat(),
                "收盤價": price["收盤指數"],
                "開盤價": price["開盤指數"],
                "最高價": price["最高指數"],
                "最低價": price["最低指數"],
                "成交量": int(volume),
            })
    if not rows:
        raise OfficialMarketDailyError("TWSE 官方報表在請求日期範圍內沒有交易日資料")

    manifest_path = _capture_raw_sources(
        Path(source_dir), start=start, cutoff=cutoff, captures=captures, row_count=len(rows),
    )
    if capture_manifests is not None:
        capture_manifests.append(manifest_path)
    return rows


def update_market_index_csv(
    config: Any,
    rows: list[dict[str, Any]],
    *,
    skip_backup: bool = False,
) -> bool:
    """在共用 OS lock 內備份並原子更新大盤 CSV。"""
    if not rows:
        return False
    seen_dates: set[date] = set()
    for row in rows:
        if not isinstance(row, Mapping) or any(column not in row for column in MARKET_INDEX_COLUMNS):
            return False
        try:
            trading_day = _as_date(row["日期"])
            opening, high, low, close = (
                row["開盤價"], row["最高價"], row["最低價"], row["收盤價"],
            )
            volume = row["成交量"]
        except (KeyError, OfficialMarketDailyError):
            return False
        if (
            trading_day in seen_dates
            or any(not isinstance(value, Decimal) or not value.is_finite()
                   for value in (opening, high, low, close))
            or low <= 0
            or not low <= min(opening, close) <= max(opening, close) <= high
            or isinstance(volume, bool)
            or not isinstance(volume, int)
            or volume < 0
        ):
            return False
        seen_dates.add(trading_day)
    target = Path(config.market_index_file)
    reservation = acquire_heavy_chain_reservation(target.with_suffix(".csv.lock"))
    if reservation is None:
        return False

    temp_path: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = pd.read_csv(target, encoding="utf-8-sig", dtype={"日期": "string"})
            if "日期" not in existing.columns:
                return False
            normalized_dates = existing["日期"].map(_as_date)
            existing["__official_date"] = normalized_dates.map(date.isoformat)
            if not skip_backup and config.create_backup(target) is None:
                return False
        else:
            existing = pd.DataFrame(columns=[*MARKET_INDEX_COLUMNS, "__official_date"])

        updates = pd.DataFrame(rows, columns=MARKET_INDEX_COLUMNS)
        updates["__official_date"] = updates["日期"].map(_as_date).map(date.isoformat)
        # 原始日期欄仍採既有 API 的 YYYY-MM-DD 格式，臨時鍵只用來排序與去重。
        combined = pd.concat([existing, updates], ignore_index=True, sort=False)
        combined = combined.drop_duplicates(subset=["__official_date"], keep="last")
        combined = combined.sort_values("__official_date", kind="stable")
        combined = combined.drop(columns=["__official_date"])
        output = combined.to_csv(index=False, encoding="utf-8-sig", lineterminator="\n")
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", prefix=f".{target.name}.",
            suffix=".tmp", dir=target.parent, delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(output)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
        temp_path = None
        return True
    except Exception:
        return False
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        release_heavy_chain_reservation(reservation)
