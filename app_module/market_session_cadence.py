"""以已驗證官方日曆區分最新行情與真正 stale；不授予歷史 PIT 資格。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app_module.position_health_source_providers import OfficialCalendarSourceProvider

TAIPEI = ZoneInfo("Asia/Taipei")
PACIFIC = ZoneInfo("America/Los_Angeles")


@dataclass(frozen=True)
class MarketSessionAssessment:
    status: str
    expected_date: date | None
    metadata: dict[str, Any]

    @property
    def current(self) -> bool:
        return self.status == "current"


class MarketSessionCadence:
    """04:30 Pacific 為專案資料截止約定，並非交易所發布時間證明。

    決策當日截止前接受上一個已完成交易日；截止後要求當日行情。
    假日／週末必須由 hash-bound 且未過期的官方離線日曆確認。
    歷史查詢不能使用決策當時尚未取得的日曆替代 PIT 證據。
    """

    def __init__(self, calendar: OfficialCalendarSourceProvider, *, clock: Callable[[], datetime] | None = None):
        self.calendar = calendar
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @classmethod
    def for_config(cls, config: Any, *, clock: Callable[[], datetime] | None = None) -> MarketSessionCadence:
        default = Path(__file__).resolve().parents[1] / "output/paper_execution_eod_replay/calendar_cache"
        cache = getattr(config, "official_calendar_cache_path", None) or default
        return cls(OfficialCalendarSourceProvider(calendar_cache_path=cache,
            temporary_closure_path=getattr(config, "temporary_closure_path", None)), clock=clock)

    def assess(self, decision_date: date, actual_date: date) -> MarketSessionAssessment:
        now = self.clock()
        meta: dict[str, Any] = {"decision_date": decision_date.isoformat(), "actual_date": actual_date.isoformat(),
            "cutoff_policy": "project_daily_data_04:30_America/Los_Angeles", "historical_pit": False}
        if now.tzinfo is None or now.utcoffset() is None:
            return MarketSessionAssessment("unverified", None, {**meta, "blockers": ["cadence_clock_timezone_missing"]})
        today = now.astimezone(TAIPEI).date()
        if decision_date > today or actual_date > decision_date:
            return MarketSessionAssessment("future_rejected", None, meta)
        decision_at = now if decision_date == today else datetime.combine(decision_date, time.max, TAIPEI)
        # Use the decision's Taipei date when deriving the Pacific deadline (DST-aware).
        local = datetime.combine(decision_date, time(23), TAIPEI).astimezone(PACIFIC)
        cutoff = datetime.combine(local.date(), time(4, 30), PACIFIC)
        end = decision_date
        if decision_date == today and now < cutoff:
            end -= timedelta(days=1)
        result = self.calendar.read_range(start_date=(end - timedelta(days=21)).isoformat(), end_date=end.isoformat(),
            decision_at=decision_at, observed_at=now)
        meta.update({"decision_at": decision_at.isoformat(), "observed_at": now.isoformat(),
            "publication_cutoff": cutoff.isoformat(), "calendar": result.provenance, "blockers": list(result.blockers)})
        dates = result.values.get("trading_dates", ())
        if result.blockers or not dates:
            return MarketSessionAssessment("unverified", None, meta)
        expected = date.fromisoformat(str(dates[-1]))
        meta["expected_date"] = expected.isoformat()
        status = "current" if actual_date == expected else "stale" if actual_date < expected else "future_rejected"
        return MarketSessionAssessment(status, expected, meta)
