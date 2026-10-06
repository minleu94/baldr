"""同來源圖表標記的純身份核驗；不讀帳本、不把研究確認視為成交。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from collections.abc import Sequence

from app_module.stock_research_report_dtos import StockPricePointDTO


class StockChartMarkerKind(str, Enum):
    RECOMMENDATION_CONFIRMED = "recommendation_confirmed"
    RECORDED_BUY = "recorded_buy"
    RECORDED_SELL = "recorded_sell"


@dataclass(frozen=True)
class StockChartMarkerDTO:
    record_id: str
    kind: StockChartMarkerKind
    stock_code: str
    event_date: str
    source_id: str
    source_row_hash: str
    account_id: str
    account_kind: str
    available_at: str
    source_context: tuple[tuple[str, str], ...]
    content_sha256: str = ""

    @property
    def label(self) -> str:
        return {
            StockChartMarkerKind.RECOMMENDATION_CONFIRMED: "推薦確認（研究）",
            StockChartMarkerKind.RECORDED_BUY: "實際記錄買入",
            StockChartMarkerKind.RECORDED_SELL: "實際記錄賣出",
        }[self.kind]


@dataclass(frozen=True)
class StockChartMarkerIdentityDTO:
    """由已核驗 record reader 提供的獨立 pin，不接受候選自己作身份依據。"""
    record_id: str
    kind: StockChartMarkerKind
    stock_code: str
    event_date: str
    source_id: str
    source_row_hash: str
    account_id: str
    account_kind: str
    source_context: tuple[tuple[str, str], ...]
    available_at: str = ""


def stock_chart_marker_fingerprint(marker: StockChartMarkerDTO) -> str:
    """獨立 marker hash 域，絕不與行情 hash 混用。"""
    data = ["stock_chart_marker.v1", marker.record_id, marker.kind.value,
            marker.stock_code, marker.event_date, marker.source_id, marker.source_row_hash,
            marker.account_id, marker.account_kind, marker.available_at,
            sorted(marker.source_context)]
    return sha256(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def verified_stock_chart_markers(
    candidates: Sequence[StockChartMarkerDTO],
    identities: Sequence[StockChartMarkerIdentityDTO],
    *, stock_code: str, cutoff_date: str,
    source_context: tuple[tuple[str, str], ...],
    price_points: Sequence[StockPricePointDTO],
) -> tuple[StockChartMarkerDTO, ...]:
    """同股／同日槽／來源／hash／帳本／scope／可得時鐘全核，缺件不畫。

    pin 是 caller 的受信任核驗邊界；此函式不驗證外部資料真實性，不授 PIT。
    """
    if len(candidates) > 128 or len(identities) > 128 or not source_context:
        return ()
    try:
        cutoff = date.fromisoformat(cutoff_date)
    except (ValueError, TypeError):
        return ()
    if cutoff.isoformat() != cutoff_date:
        return ()
    scope = tuple(sorted(source_context))
    if len(dict(scope)) != len(scope) or any(not k or not v for k, v in scope):
        return ()
    # 重複 record_id 是模糊身份；不能挑第一筆或讓後一筆覆寫。
    counts: dict[str, int] = {}
    pins: dict[str, StockChartMarkerIdentityDTO] = {}
    for identity in identities:
        counts[identity.record_id] = counts.get(identity.record_id, 0) + 1
        pins[identity.record_id] = identity
    candidate_counts: dict[str, int] = {}
    for candidate in candidates:
        candidate_counts[candidate.record_id] = candidate_counts.get(candidate.record_id, 0) + 1
    price_dates = {p.data_date for p in price_points if p.close_price is not None}
    accepted: list[StockChartMarkerDTO] = []
    for marker in candidates:
        pin = pins.get(marker.record_id)
        if pin is None or counts[marker.record_id] != 1 or candidate_counts[marker.record_id] != 1:
            continue
        if not isinstance(marker.kind, StockChartMarkerKind):
            continue
        if not all((marker.record_id.strip(), marker.stock_code.strip(), marker.source_id.strip(), marker.account_id.strip())):
            continue
        if marker.stock_code != stock_code or marker.event_date not in price_dates:
            continue
        if marker.account_kind != ("research" if marker.kind == StockChartMarkerKind.RECOMMENDATION_CONFIRMED else "actual"):
            continue
        try:
            event_day = date.fromisoformat(marker.event_date)
            clock = datetime.fromisoformat(marker.available_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if event_day.isoformat() != marker.event_date or event_day > cutoff or clock.tzinfo is None:
            continue
        available_day = clock.astimezone(ZoneInfo("Asia/Taipei")).date()
        if available_day > cutoff or available_day < event_day:
            continue
        if tuple(sorted(marker.source_context)) != scope or tuple(sorted(pin.source_context)) != scope:
            continue
        if len(dict(marker.source_context)) != len(marker.source_context) or len(dict(pin.source_context)) != len(pin.source_context):
            continue
        fields = ("record_id", "kind", "stock_code", "event_date", "source_id", "source_row_hash", "account_id", "account_kind", "available_at")
        if any(getattr(marker, field) != getattr(pin, field) for field in fields):
            continue
        if len(marker.source_row_hash) != 64 or any(ch not in "0123456789abcdef" for ch in marker.source_row_hash):
            continue
        if marker.content_sha256 != stock_chart_marker_fingerprint(marker):
            continue
        accepted.append(marker)
    return tuple(accepted)
