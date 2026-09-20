"""以唯讀官方 calendar cache 提供 forward maturity 診斷。

forward outcome producer 的既有 close-to-close return contract 仍使用股價
序列；本模組只提供預定 session，說明 horizon 預計何時成熟。這裡不讀
market rows、不發網路請求，也不會把 outcome 標成 ready。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from data_module.official_trading_calendar_cache import (
    OFFICIAL_CALENDAR_CACHE_SCHEMA_VERSION,
    OfficialCalendarCacheError,
    VerifiedOfficialCalendarCache,
    VerifiedTemporaryClosureCache,
    load_verified_twse_calendar_cache,
    load_verified_twse_temporary_closure_cache,
)


MAX_CACHE_CANDIDATES = 64
MAX_WINDOW_DAYS = 3660


@dataclass(frozen=True)
class OfficialMaturityDiagnostic:
    """與實際價格分離的官方預定成熟度觀測。"""

    planned_date: str | None
    status: str
    remaining_sessions: int | None
    calendar: dict[str, Any]


class OfficialMaturityCalendar:
    """從既有 immutable cache 唯讀解析 TWSE 預定交易 session。"""

    def __init__(
        self,
        cache_path: str | Path,
        *,
        observed_at: datetime,
        temporary_closure_path: str | Path | None = None,
    ) -> None:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must contain a timezone")
        self.cache_path = Path(cache_path).expanduser().resolve()
        self.observed_at = observed_at.astimezone(timezone.utc)
        self.temporary_closure_path = (
            None
            if temporary_closure_path is None
            else Path(temporary_closure_path).expanduser().resolve()
        )
        self._annual: dict[int, VerifiedOfficialCalendarCache | None] = {}
        self._annual_errors: dict[int, str] = {}
        self._temporary: dict[date, VerifiedTemporaryClosureCache | None] = {}
        self._temporary_errors: dict[date, str] = {}
        self._temporary_used: dict[date, VerifiedTemporaryClosureCache] = {}

    def evaluate(
        self,
        *,
        event_date: str,
        window_days: int,
        as_of_date: str,
    ) -> OfficialMaturityDiagnostic:
        """回傳有界的預定成熟度觀測。

        ``as_of_date`` 只控制診斷狀態與已經過 session 數；此方法回傳的
        日期絕不代表股價收盤或 benchmark 已可取得。
        """

        if isinstance(window_days, bool) or window_days <= 0:
            raise ValueError("window_days must be positive")
        if window_days > MAX_WINDOW_DAYS:
            return self._waiting(
                reason="official_calendar_horizon_exceeds_bound",
                years=(),
            )
        event = self._parse_date(event_date, field_name="event_date")
        as_of = self._parse_date(as_of_date, field_name="as_of_date")
        start = event + timedelta(days=1)
        # 一年最多 366 天，多留一個月以涵蓋週末、年度休市與跨年；此
        # lookup 不依賴 market database 的 row 數量。
        scan_end = start + timedelta(days=max(366, window_days * 3 + 31))
        sessions: list[date] = []
        years: set[int] = set()
        current = start
        while current <= scan_end and len(sessions) < window_days:
            if current.weekday() < 5:
                years.add(current.year)
                annual = self._load_annual(current.year)
                if annual is None:
                    return self._waiting(
                        reason=self._annual_errors.get(
                            current.year,
                            "official_calendar_unavailable",
                        ),
                        years=tuple(sorted(years)),
                    )
                is_session = self._is_planned_session(current, annual)
                if is_session is None:
                    return self._waiting(
                        reason=self._temporary_errors.get(
                            current,
                            "official_temporary_closure_unavailable",
                        ),
                        years=tuple(sorted(years)),
                    )
                if is_session:
                    sessions.append(current)
            current += timedelta(days=1)

        if len(sessions) < window_days:
            return self._waiting(
                reason="official_calendar_coverage_insufficient",
                years=tuple(sorted(years)),
            )

        planned = sessions[window_days - 1]
        observed_count = sum(item <= as_of for item in sessions)
        status = "planned_reached" if planned <= as_of else "planned"
        return OfficialMaturityDiagnostic(
            planned_date=planned.isoformat(),
            status=status,
            remaining_sessions=max(window_days - observed_count, 0),
            calendar=self._calendar_payload(years=tuple(sorted(years))),
        )

    def describe(self) -> dict[str, Any]:
        """回傳不探測來源的 receipt 設定摘要。"""

        return {
            "status": "configured",
            "cache_path": str(self.cache_path),
            "temporary_closure_path": (
                None
                if self.temporary_closure_path is None
                else str(self.temporary_closure_path)
            ),
            "observed_at": self.observed_at.isoformat(),
            "loader_schema_version": OFFICIAL_CALENDAR_CACHE_SCHEMA_VERSION,
            "read_only": True,
            "network_fetch": False,
        }

    def _waiting(
        self,
        *,
        reason: str,
        years: tuple[int, ...],
    ) -> OfficialMaturityDiagnostic:
        payload = self._calendar_payload(years=years)
        payload.update(
            {
                "status": "waiting_for_calendar",
                "reason": reason,
            }
        )
        return OfficialMaturityDiagnostic(
            planned_date=None,
            status="waiting_for_calendar",
            remaining_sessions=None,
            calendar=payload,
        )

    def _load_annual(self, calendar_year: int) -> VerifiedOfficialCalendarCache | None:
        if calendar_year in self._annual:
            return self._annual[calendar_year]
        candidates = self._annual_candidates(calendar_year)
        verified: list[VerifiedOfficialCalendarCache] = []
        errors: list[str] = []
        for candidate in candidates:
            try:
                verified.append(
                    load_verified_twse_calendar_cache(
                        candidate,
                        calendar_year=calendar_year,
                        observed_at=self.observed_at,
                    )
                )
            except (OSError, ValueError, OfficialCalendarCacheError) as error:
                errors.append(f"{type(error).__name__}:{str(error)[:240]}")
        selected = (
            max(
                verified,
                key=lambda item: str(item.evidence.get("captured_at", "")),
            )
            if verified
            else None
        )
        self._annual[calendar_year] = selected
        if selected is None:
            self._annual_errors[calendar_year] = (
                errors[0]
                if errors
                else "official_calendar_cache_file_missing"
            )
        return selected

    def _annual_candidates(self, calendar_year: int) -> tuple[Path, ...]:
        root = self.cache_path
        if root.is_file():
            return (root,)
        if root.suffix.casefold() == ".json":
            return (root,)
        if not root.is_dir():
            return ()
        candidates: list[tuple[int, str, Path]] = []
        for candidate in root.glob(
            f"twse_holiday_schedule_{calendar_year}_*.json"
        ):
            try:
                resolved = candidate.resolve()
                resolved.relative_to(root)
                stat = resolved.stat()
            except (OSError, ValueError):
                continue
            if resolved.is_file():
                candidates.append((int(stat.st_mtime_ns), str(resolved), resolved))
        exact = root / f"twse_holiday_schedule_{calendar_year}.json"
        if exact.is_file():
            candidates.append((int(exact.stat().st_mtime_ns), str(exact), exact))
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return tuple(item[2] for item in candidates[:MAX_CACHE_CANDIDATES])

    def _temporary_for(self, target: date) -> VerifiedTemporaryClosureCache | None:
        if self.temporary_closure_path is None:
            return None
        if target in self._temporary:
            return self._temporary[target]
        root = self.temporary_closure_path
        candidates: tuple[Path, ...]
        if root.is_file():
            candidates = (root,)
        elif root.suffix.casefold() == ".json":
            candidates = (root,)
        elif root.is_dir():
            candidates = tuple(
                sorted(root.glob("twse_temporary_closure_*.json"))[
                    :MAX_CACHE_CANDIDATES
                ]
            )
        else:
            candidates = ()
        if not candidates:
            self._temporary_errors[target] = "official_temporary_closure_cache_missing"
            self._temporary[target] = None
            return None
        verified: list[VerifiedTemporaryClosureCache] = []
        errors: list[str] = []
        for candidate in candidates:
            try:
                item = load_verified_twse_temporary_closure_cache(
                    candidate,
                    observed_at=self.observed_at,
                )
            except (OSError, ValueError, OfficialCalendarCacheError) as error:
                errors.append(f"{type(error).__name__}:{str(error)[:240]}")
                continue
            if item.closure_date == target:
                verified.append(item)
        if errors:
            self._temporary_errors[target] = errors[0]
        selected = (
            max(
                verified,
                key=lambda item: str(item.evidence.get("captured_at", "")),
            )
            if verified
            else None
        )
        self._temporary[target] = selected
        if selected is not None:
            self._temporary_used[target] = selected
        return selected

    def _is_planned_session(
        self,
        target: date,
        annual: VerifiedOfficialCalendarCache,
    ) -> bool | None:
        temporary = self._temporary_for(target)
        if target in self._temporary_errors:
            return None
        if temporary is not None:
            return False
        return bool(annual.schedule.get(target, True))

    def _calendar_payload(self, *, years: tuple[int, ...]) -> dict[str, Any]:
        sources: list[dict[str, Any]] = []
        missing: list[int] = []
        for year in years:
            annual = self._annual.get(year)
            if annual is None:
                missing.append(year)
                continue
            evidence = dict(annual.evidence)
            coverage = evidence.get("coverage")
            sources.append(
                {
                    "calendar_year": year,
                    "source_path": evidence.get("path"),
                    "cache_file_sha256": evidence.get("cache_file_sha256"),
                    "cache_content_sha256": evidence.get("cache_content_sha256"),
                    "source_hash": evidence.get("source_hash"),
                    "available_at": evidence.get("available_at"),
                    "expires_at": evidence.get("expires_at"),
                    "coverage": coverage,
                    "schema_version": OFFICIAL_CALENDAR_CACHE_SCHEMA_VERSION,
                    "temporary_closure_coverage": (
                        coverage.get("temporary_closure_coverage")
                        if isinstance(coverage, dict)
                        else "unknown"
                    ),
                }
            )
        temporary_errors = {
            item.isoformat(): reason
            for item, reason in sorted(self._temporary_errors.items())
        }
        temporary_evidence = [
            {
                "closure_date": item.isoformat(),
                "evidence": dict(verified.evidence),
            }
            for item, verified in sorted(self._temporary_used.items())
        ]
        if self.temporary_closure_path is None:
            temporary_status = "unconfigured_future_events_unknown"
        elif temporary_errors:
            temporary_status = "invalid_or_missing"
        else:
            temporary_status = "verified_event_cache_future_unknown"
        payload: dict[str, Any] = {
            "status": (
                "waiting_for_calendar"
                if missing or temporary_errors
                else "annual_plan_only"
            ),
            "observed_at": self.observed_at.isoformat(),
            "schema_version": OFFICIAL_CALENDAR_CACHE_SCHEMA_VERSION,
            "sources": sources,
            "missing_years": missing,
            "temporary_closure_path": (
                None
                if self.temporary_closure_path is None
                else str(self.temporary_closure_path)
            ),
            "temporary_closure_status": temporary_status,
            "temporary_closure_errors": temporary_errors,
            "temporary_closure_evidence": temporary_evidence,
            "network_fetch": False,
            "read_only": True,
        }
        return payload

    @staticmethod
    def _parse_date(value: str, *, field_name: str) -> date:
        try:
            return date.fromisoformat(str(value).strip())
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field_name} must use YYYY-MM-DD") from error
