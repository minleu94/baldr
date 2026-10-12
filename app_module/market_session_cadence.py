"""以已驗證官方日曆區分最新行情與真正 stale；不授予歷史 PIT 資格。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import os
import sys
from typing import Any, Callable
from app_module.position_health_source_providers import OfficialCalendarSourceProvider
from data_module.official_trading_calendar import (
    CalendarObservationClock,
    CalendarObservationClockError,
)
from data_module.market_session_policy import (
    PACIFIC,
    TAIPEI,
    project_market_publication_cutoff,
    resolve_project_market_session_boundary,
)

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

    未指定 ``clock`` 時每次評估明確使用 ``live_now``。指定 clock 是
    deterministic historical-as-of 測試／重播入口，不會被默認解讀為 live。
    """

    def __init__(self, calendar: OfficialCalendarSourceProvider, *, clock: Callable[[], datetime] | None = None):
        self.calendar = calendar
        # 保留既有公開 clock callable，供共用診斷與組合入口傳遞。
        # cadence assess 本身仍用明示的 observation policy，未指定 clock 時不把
        # caller-supplied historical clock 誤認為 live_now。
        self.clock = clock if clock is not None else lambda: datetime.now(timezone.utc)
        self._observation_clock = (
            (lambda: CalendarObservationClock.live_now())
            if clock is None
            else lambda: CalendarObservationClock.historical_as_of(clock())
        )

    @classmethod
    def for_config(cls, config: Any, *, clock: Callable[[], datetime] | None = None) -> MarketSessionCadence:
        # 可攜包不含本機 output；有共同外部研究根時不可回到 bundle 尋找日曆。
        research_root = os.environ.get("RESEARCH_STATE_ROOT", "").strip()
        if research_root:
            repository_root = Path(research_root)
        elif bool(getattr(sys, "frozen", False)):
            repository_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "baldr/research_state"
        else:
            repository_root = Path(__file__).resolve().parents[1]
        default = repository_root / "output/paper_execution_eod_replay/calendar_cache"
        cache = (getattr(config, "official_calendar_cache_path", None)
            or os.environ.get("OFFICIAL_CALENDAR_CACHE_PATH", "").strip() or default)
        return cls(OfficialCalendarSourceProvider(calendar_cache_path=cache,
            temporary_closure_path=getattr(config, "temporary_closure_path", None)), clock=clock)

    def assess(self, decision_date: date, actual_date: date) -> MarketSessionAssessment:
        meta: dict[str, Any] = {"decision_date": decision_date.isoformat(), "actual_date": actual_date.isoformat(),
            "cutoff_policy": "project_daily_data_04:30_America/Los_Angeles", "historical_pit": False}
        try:
            observation = self._observation_clock().capture()
        except CalendarObservationClockError as exc:
            return MarketSessionAssessment("unverified", None, {**meta, "blockers": [str(exc)]})
        now = observation.effective_at
        meta["calendar_observation_clock"] = observation.to_dict()
        boundary = resolve_project_market_session_boundary(now)
        today = boundary.taipei_date
        if decision_date > boundary.taipei_date or actual_date > decision_date:
            return MarketSessionAssessment("future_rejected", None, meta)
        decision_at = now if decision_date == today else datetime.combine(decision_date, time.max, TAIPEI)
        cutoff = project_market_publication_cutoff(decision_date)
        end = (
            boundary.calendar_end_date
            if decision_date == boundary.taipei_date
            else decision_date
        )
        result = self.calendar.read_range(start_date=(end - timedelta(days=21)).isoformat(), end_date=end.isoformat(),
            decision_at=decision_at, observed_at=now,
            observation_clock=observation)
        meta.update({"decision_at": decision_at.isoformat(), "observed_at": now.isoformat(),
            "publication_cutoff": cutoff.isoformat(), "calendar": result.provenance, "blockers": list(result.blockers)})
        dates = result.values.get("trading_dates", ())
        if result.blockers or not dates:
            return MarketSessionAssessment("unverified", None, meta)
        expected = date.fromisoformat(str(dates[-1]))
        meta["expected_date"] = expected.isoformat()
        status = "current" if actual_date == expected else "stale" if actual_date < expected else "future_rejected"
        return MarketSessionAssessment(status, expected, meta)
