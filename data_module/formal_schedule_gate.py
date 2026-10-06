"""共用的 Formal scheduled trading-day gate。

所有 Formal/Paper wrapper 必須先用官方日曆判定自然日，再載入只對交易日
有效的 runtime config。如此週末與國定休市日會是成功 no-op，不會被過期的
上一交易日設定誤報為排程故障。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from data_module.official_trading_calendar import OfficialTradingCalendar


TAIPEI = ZoneInfo("Asia/Taipei")


def formal_schedule_day_state(
    *,
    observed: datetime,
    market_db: Path | None = None,
    calendar_cache_root: Path | None = None,
    calendar: OfficialTradingCalendar | None = None,
) -> tuple[bool | None, str]:
    """Return official open/closed/unknown without online probing."""

    provider = calendar or OfficialTradingCalendar(
        db_path=market_db,
        calendar_cache_path=calendar_cache_root,
        temporary_closure_path=calendar_cache_root,
    )
    try:
        return provider.is_official_trading_day(
            observed.astimezone(TAIPEI).date(),
            allow_online_probe=False,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        return None, f"official_calendar_read_failed:{type(error).__name__}"


__all__ = ["formal_schedule_day_state"]
