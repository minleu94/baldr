"""官方交易日曆判定介面。

嚴禁單純以「週一至週五」當作台股交易日。本模組以 TWSE 官方
``holidaySchedule`` 年度休市表為主要證據；只有在年度表成功取得且通過
結構驗證後，才可將「非週末且不在休市表」判為開市。官方表取得失敗時
一律回傳未知，不得以一般工作日推定開市。
若呼叫端提供新鮮且 hash-bound 的官方 annual cache，則可在官方請求不可得時
唯讀重驗該 cache；cache 缺失、過期或竄改時仍回傳未知。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from contextlib import closing
from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
import sqlite3
from _thread import LockType
from threading import Lock
from typing import Mapping, Optional, Tuple

from data_module.config import TWStockConfig
from data_module.official_phase3c_fetcher import safe_request
from data_module.official_trading_calendar_cache import (
    OfficialCalendarCacheError,
    OfficialCalendarCacheExpired,
    TWSE_TEMPORARY_CLOSURE_POLICY_URL,
    VerifiedOfficialCalendarCache,
    VerifiedTemporaryClosureCache,
    load_verified_twse_calendar_cache,
    load_verified_twse_temporary_closure_cache,
    parse_twse_annual_schedule,
)
from app_module.sqlite_read_only import (
    ReadOperationCancelled,
    check_read_cancelled,
    connect_read_only_sqlite,
)

logger = logging.getLogger(__name__)

# 測試可替換公開 ``datetime.now`` 以證明 live clock 只捕捉一次；完整性檢查
# 使用模組載入時保存的型別與時鐘，確保後續每次讀取仍核對真實 UTC 現在。
_CLOCK_VALIDATION_DATETIME = datetime

HOLIDAY_SCHEDULE_URL = (
    "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
)
_OFFICIAL_OPEN_MARKERS = (
    "開始交易",
    "最後交易",
    "恢復交易",
    "照常交易",
)


class CalendarObservationClockError(ValueError):
    """日曆觀測時鐘缺失、無效或已被使用。"""


@dataclass(frozen=True)
class CalendarObservationClock:
    """明示一次日曆讀取使用 live 現在或指定的歷史 as-of 時鐘。

    ``live_now`` 是每次 operation 開始時重新取 UTC 現在時間的政策，
    不保存建構 clock policy 時的時間。``historical_as_of`` 必須傳入
    aware datetime；歷史讀取不可在線查詢，也不可用目前 SQLite 代替來源。
    """

    mode: str
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        self._validate_policy()

    def _validate_policy(self) -> None:
        if type(self) is not CalendarObservationClock:
            raise CalendarObservationClockError(
                "calendar_observation_clock_type_invalid"
            )
        if type(self.mode) is not str:
            raise CalendarObservationClockError(
                "calendar_observation_clock_mode_invalid"
            )
        if self.mode not in {"live_now", "historical_as_of"}:
            raise CalendarObservationClockError(
                "calendar_observation_clock_mode_invalid"
            )
        if self.mode == "live_now" and self.as_of is not None:
            raise CalendarObservationClockError(
                "live_now_clock_cannot_carry_as_of"
            )
        if self.mode == "historical_as_of":
            if type(self.as_of) is not _CLOCK_VALIDATION_DATETIME:
                raise CalendarObservationClockError(
                    "historical_as_of_requires_datetime"
                )
            if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
                raise CalendarObservationClockError(
                    "calendar_observation_clock_requires_aware_datetime"
                )

    @classmethod
    def live_now(cls) -> "CalendarObservationClock":
        return cls(mode="live_now")

    @classmethod
    def historical_as_of(
        cls, observed_at: datetime
    ) -> "CalendarObservationClock":
        return cls(mode="historical_as_of", as_of=observed_at)

    def capture(self) -> "CalendarObservation":
        self._validate_policy()
        if self.mode == "live_now":
            effective_at = datetime.now(timezone.utc)
        else:
            assert self.as_of is not None
            effective_at = self.as_of.astimezone(timezone.utc)
            actual_now = _CLOCK_VALIDATION_DATETIME.now(timezone.utc)
            if effective_at > actual_now:
                raise CalendarObservationClockError(
                    "calendar_observation_clock_future_rejected"
                )
        effective_at = _canonical_utc_datetime(effective_at)
        _validate_calendar_observation_values(self.mode, effective_at)
        return CalendarObservation._issued(self.mode, effective_at)


_CALENDAR_OBSERVATION_ISSUER = object()


class CalendarObservation:
    """單一 operation 已捕捉的時鐘；只能交給一個讀取 operation。"""

    _mode: str
    _effective_at: datetime
    _sealed_mode: str
    _sealed_effective_at: datetime
    _claimed: bool
    _claim_lock: LockType

    __slots__ = (
        "_mode",
        "_effective_at",
        "_sealed_mode",
        "_sealed_effective_at",
        "_claimed",
        "_claim_lock",
    )

    def __init__(
        self,
        mode: str,
        effective_at: datetime,
        *,
        _issuer: object | None = None,
    ) -> None:
        if _issuer is not _CALENDAR_OBSERVATION_ISSUER:
            raise CalendarObservationClockError(
                "calendar_observation_must_be_captured_from_clock"
            )
        normalized_at = _validate_calendar_observation_values(mode, effective_at)
        object.__setattr__(self, "_mode", mode)
        object.__setattr__(self, "_effective_at", normalized_at)
        object.__setattr__(self, "_sealed_mode", mode)
        object.__setattr__(self, "_sealed_effective_at", normalized_at)
        object.__setattr__(self, "_claimed", False)
        object.__setattr__(self, "_claim_lock", Lock())

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("calendar_observation_is_immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("calendar_observation_is_immutable")

    @property
    def mode(self) -> str:
        self._validate()
        return self._mode

    @property
    def effective_at(self) -> datetime:
        self._validate()
        return self._effective_at

    def _validate(self) -> None:
        if type(self) is not CalendarObservation:
            raise CalendarObservationClockError(
                "calendar_observation_type_invalid"
            )
        normalized_at = _validate_calendar_observation_values(
            self._mode,
            self._effective_at,
        )
        if (
            self._mode != self._sealed_mode
            or normalized_at != self._sealed_effective_at
            or self._effective_at != normalized_at
        ):
            raise CalendarObservationClockError(
                "calendar_observation_mutated"
            )

    @classmethod
    def _issued(cls, mode: str, effective_at: datetime) -> "CalendarObservation":
        return cls(
            mode,
            effective_at,
            _issuer=_CALENDAR_OBSERVATION_ISSUER,
        )

    def _claim(self) -> None:
        self._validate()
        with self._claim_lock:
            if self._claimed:
                raise CalendarObservationClockError(
                    "calendar_observation_already_consumed"
                )
            object.__setattr__(self, "_claimed", True)

    def to_dict(self) -> dict[str, str]:
        self._validate()
        return {
            "mode": self._mode,
            "effective_at": self._effective_at.isoformat(),
        }


def _validate_calendar_observation_values(
    mode: object,
    effective_at: object,
) -> datetime:
    if type(mode) is not str or mode not in {"live_now", "historical_as_of"}:
        raise CalendarObservationClockError(
            "calendar_observation_clock_mode_invalid"
        )
    if type(effective_at) is not _CLOCK_VALIDATION_DATETIME:
        raise CalendarObservationClockError(
            "calendar_observation_clock_requires_datetime"
        )
    if effective_at.tzinfo is None or effective_at.utcoffset() is None:
        raise CalendarObservationClockError(
            "calendar_observation_clock_requires_aware_datetime"
        )
    normalized_at = effective_at.astimezone(timezone.utc)
    if effective_at.tzinfo is not timezone.utc or normalized_at != effective_at:
        raise CalendarObservationClockError(
            "calendar_observation_clock_requires_utc_datetime"
        )
    if normalized_at > _CLOCK_VALIDATION_DATETIME.now(timezone.utc):
        raise CalendarObservationClockError(
            "calendar_observation_clock_future_rejected"
        )
    return normalized_at


def _canonical_utc_datetime(value: datetime) -> datetime:
    """將 datetime 子類也正規化成內建 UTC datetime。"""

    if not isinstance(value, _CLOCK_VALIDATION_DATETIME):
        raise CalendarObservationClockError(
            "calendar_observation_clock_requires_datetime"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise CalendarObservationClockError(
            "calendar_observation_clock_requires_aware_datetime"
        )
    return _CLOCK_VALIDATION_DATETIME.fromisoformat(
        value.astimezone(timezone.utc).isoformat()
    )


@dataclass
class _CalendarOperationState:
    observation: CalendarObservation
    observation_mode: str
    observation_effective_at: datetime
    allow_online_probe: bool
    schedules: dict[int, Mapping[date, bool] | None] = field(default_factory=dict)
    schedule_evidence: dict[int, dict[str, object]] = field(default_factory=dict)
    schedule_failure_reason: dict[int, str] = field(default_factory=dict)
    schedule_cache_errors: dict[int, OfficialCalendarCacheError] = field(
        default_factory=dict
    )
    temporary_closures: dict[
        date, VerifiedTemporaryClosureCache | None
    ] = field(default_factory=dict)
    temporary_closure_failure_reason: dict[date, str] = field(
        default_factory=dict
    )
    temporary_cache_candidates_loaded: bool = False
    temporary_cache_candidates: list[VerifiedTemporaryClosureCache] = field(
        default_factory=list
    )
    temporary_cache_errors: list[OfficialCalendarCacheError] = field(
        default_factory=list
    )


class OfficialCalendarReadOperation:
    """在固定觀測時鐘與 operation-local cache 下讀取日曆證據。"""

    def __init__(
        self,
        calendar: "OfficialTradingCalendar",
        state: _CalendarOperationState,
    ) -> None:
        self._calendar = calendar
        self._state = state
        self._entered = False
        self._closed = False

    def __enter__(self) -> "OfficialCalendarReadOperation":
        if self._entered or self._closed:
            raise CalendarObservationClockError(
                "calendar_read_operation_cannot_be_reentered"
            )
        self._validate_observation()
        self._entered = True
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._closed = True
        self._entered = False

    def _ensure_active(self) -> None:
        if not self._entered or self._closed:
            raise CalendarObservationClockError(
                "calendar_read_operation_requires_context"
            )
        self._validate_observation()

    def _validate_observation(self) -> None:
        observation = self._state.observation
        observation._validate()
        if (
            observation._mode != self._state.observation_mode
            or observation._effective_at
            != self._state.observation_effective_at
        ):
            raise CalendarObservationClockError(
                "calendar_read_operation_observation_mismatch"
            )

    @property
    def observation(self) -> CalendarObservation:
        self._ensure_active()
        return self._state.observation

    def is_official_trading_day(
        self, target_date: date
    ) -> Tuple[Optional[bool], str]:
        self._ensure_active()
        return self._calendar._is_official_trading_day(
            target_date, self._state
        )

    def evidence_for(self, target_date: date) -> dict[str, object]:
        self._ensure_active()
        return self._calendar._evidence_for(target_date, self._state)

    def get_trading_days_in_range(
        self,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, object]]:
        self._ensure_active()
        return self._calendar._get_trading_days_in_range(
            start_date, end_date, self._state
        )

    def require_trading_days_in_range(
        self,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, object]]:
        self._ensure_active()
        return self._calendar._require_trading_days_in_range(
            start_date, end_date, self._state
        )

    def get_recent_official_trading_days(
        self,
        reference_date: date,
        count: int,
        *,
        include_reference: bool = True,
        max_lookback_days: int = 92,
    ) -> list[dict[str, object]]:
        self._ensure_active()
        return self._calendar._get_recent_official_trading_days(
            reference_date,
            count,
            self._state,
            include_reference=include_reference,
            max_lookback_days=max_lookback_days,
        )


class OfficialTradingCalendar:
    """台股官方交易日判定器。"""

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        *,
        calendar_cache_path: Optional[str | Path] = None,
        temporary_closure_path: Optional[str | Path] = None,
    ) -> None:
        if db_path is None:
            config = TWStockConfig()
            self.db_path = Path(config.db_file)
        else:
            self.db_path = Path(db_path)
        self.calendar_cache_path = (
            None
            if calendar_cache_path is None
            else Path(calendar_cache_path)
        )
        self.temporary_closure_path = (
            None
            if temporary_closure_path is None
            else Path(temporary_closure_path)
        )
        # 網路取回的年表維持既有 instance memo 行為，特別是失敗後不在
        # 同一個 calendar instance 無限制重試。Cache-backed 證據則只留在
        # _CalendarOperationState；每個新 operation 必須重驗目前檔案 bytes
        # 與 freshness clock。
        self._live_network_schedule_cache: dict[
            int,
            tuple[
                Mapping[date, bool] | None,
                dict[str, object] | None,
                str | None,
            ],
        ] = {}

    def read_operation(
        self,
        *,
        observation_clock: CalendarObservationClock | CalendarObservation | None = None,
        allow_online_probe: bool = True,
    ) -> OfficialCalendarReadOperation:
        """建立單一日曆讀取 operation，供複合呼叫共用同一時鐘與驗證結果。"""

        clock = (
            CalendarObservationClock.live_now()
            if observation_clock is None
            else observation_clock
        )
        if type(clock) is CalendarObservationClock:
            observation = clock.capture()
        elif type(clock) is CalendarObservation:
            observation = clock
        else:
            raise CalendarObservationClockError(
                "calendar_observation_clock_type_invalid"
            )
        observation._validate()
        if observation.mode == "historical_as_of" and allow_online_probe:
            raise CalendarObservationClockError(
                "historical_calendar_operation_cannot_probe_online"
            )
        observation._claim()
        state = _CalendarOperationState(
            observation=observation,
            observation_mode=observation.mode,
            observation_effective_at=observation.effective_at,
            allow_online_probe=allow_online_probe,
        )
        return OfficialCalendarReadOperation(self, state)

    @staticmethod
    def _parse_roc_date(value: object, *, expected_year: int) -> date:
        digits = re.sub(r"\D", "", str(value))
        if len(digits) != 7:
            raise ValueError("TWSE holidaySchedule Date 必須是 7 碼民國日期")
        roc_year = int(digits[:3])
        result = date(roc_year + 1911, int(digits[3:5]), int(digits[5:7]))
        if result.year != expected_year:
            raise ValueError("TWSE holidaySchedule 回傳非查詢年度日期")
        return result

    @staticmethod
    def _row_is_open(row: Mapping[str, object]) -> bool:
        description = " ".join(
            str(row.get(field, "")) for field in ("Name", "Description")
        )
        return any(marker in description for marker in _OFFICIAL_OPEN_MARKERS)

    def _fetch_official_year_schedule(
        self,
        calendar_year: int,
        operation: _CalendarOperationState,
    ) -> Mapping[date, bool] | None:
        if calendar_year in operation.schedules:
            return operation.schedules[calendar_year]

        cached = self._load_cached_year_schedule(calendar_year, operation)
        if cached is not None:
            operation.schedules[calendar_year] = cached.schedule
            operation.schedule_evidence[calendar_year] = dict(cached.evidence)
            return operation.schedules[calendar_year]

        cache_error = operation.schedule_cache_errors.get(calendar_year)
        if not operation.allow_online_probe:
            operation.schedules[calendar_year] = None
            if cache_error is not None:
                operation.schedule_failure_reason[calendar_year] = (
                    self._cache_error_reason(cache_error)
                )
            else:
                operation.schedule_failure_reason[calendar_year] = (
                    "lacks_official_evidence"
                )
            return None

        cached_network = self._live_network_schedule_cache.get(calendar_year)
        if cached_network is not None:
            schedule, evidence, failure_reason = cached_network
            operation.schedules[calendar_year] = schedule
            if evidence is not None:
                operation.schedule_evidence[calendar_year] = dict(evidence)
            if failure_reason is not None:
                operation.schedule_failure_reason[calendar_year] = (
                    self._cache_error_reason(cache_error)
                    if cache_error is not None
                    else failure_reason
                )
            return schedule

        try:
            response = safe_request(
                HOLIDAY_SCHEDULE_URL,
                params={"queryYear": str(calendar_year - 1911)},
                timeout_seconds=8,
                max_attempts=1,
            )
            payload = response.json()
            if not isinstance(payload, list) or not payload:
                raise ValueError("TWSE holidaySchedule 必須回傳非空 array")

            schedule = parse_twse_annual_schedule(
                payload,
                expected_year=calendar_year,
            )
            response_content = getattr(response, "content", b"")
            source_hash = None
            if isinstance(response_content, bytes) and response_content:
                import hashlib

                source_hash = "sha256:" + hashlib.sha256(response_content).hexdigest()
            evidence = {
                "mode": "live_official_calendar",
                "source": HOLIDAY_SCHEDULE_URL,
                "request_params": {"queryYear": str(calendar_year - 1911)},
                "source_hash": source_hash,
                "validated_at": operation.observation.effective_at.isoformat(),
                "calendar_observation": operation.observation.to_dict(),
                "annual_schedule_scope": "planned_annual_closures",
                "temporary_closure_scope": {
                    "provider": "TWSE",
                    "url": TWSE_TEMPORARY_CLOSURE_POLICY_URL,
                    "source_kind": "official_policy_only",
                    "event_evidence_required": True,
                },
            }
            operation.schedule_evidence[calendar_year] = evidence
            operation.schedules[calendar_year] = schedule
            self._live_network_schedule_cache[calendar_year] = (
                schedule,
                dict(evidence),
                None,
            )
        except Exception as exc:  # noqa: BLE001 - 網路／官方格式皆須 fail closed
            logger.warning(
                "取得 TWSE holidaySchedule 失敗 (%s): %s",
                calendar_year,
                exc,
            )
            operation.schedules[calendar_year] = None
            if cache_error is not None:
                failure_reason = self._cache_error_reason(cache_error)
                operation.schedule_failure_reason[calendar_year] = (
                    self._cache_error_reason(cache_error)
                )
            else:
                failure_reason = "twse_holiday_schedule_unavailable"
                operation.schedule_failure_reason[calendar_year] = failure_reason
            self._live_network_schedule_cache[calendar_year] = (
                None,
                None,
                failure_reason,
            )
        return operation.schedules[calendar_year]

    def _cache_candidates(self, calendar_year: int) -> tuple[Path, ...]:
        """列出指定年度的 immutable cache candidates。"""

        if self.calendar_cache_path is None:
            return ()
        root = self.calendar_cache_path.expanduser()
        if root.exists() and root.is_file():
            return (root,)
        if root.suffix.casefold() == ".json":
            return (root,)
        if not root.is_dir():
            return ()
        candidates = list(
            root.glob(f"twse_holiday_schedule_{calendar_year}_*.json")
        )
        exact = root / f"twse_holiday_schedule_{calendar_year}.json"
        if exact.exists():
            candidates.append(exact)
        return tuple(sorted(set(candidates)))

    def _load_cached_year_schedule(
        self,
        calendar_year: int,
        operation: _CalendarOperationState,
    ) -> VerifiedOfficialCalendarCache | None:
        """只讀載入最新且仍在 freshness window 的官方 cache。"""

        operation.schedule_cache_errors.pop(calendar_year, None)
        candidates = self._cache_candidates(calendar_year)
        if not candidates:
            if self.calendar_cache_path is not None:
                operation.schedule_cache_errors[calendar_year] = OfficialCalendarCacheError(
                    "calendar cache file is missing"
                )
            return None
        verified: list[VerifiedOfficialCalendarCache] = []
        errors: list[OfficialCalendarCacheError] = []
        observed = operation.observation.effective_at
        for candidate in candidates:
            try:
                verified.append(
                    load_verified_twse_calendar_cache(
                        candidate,
                        calendar_year=calendar_year,
                        observed_at=observed,
                    )
                )
            except OfficialCalendarCacheError as error:
                errors.append(error)
        if verified:
            verified.sort(
                key=lambda item: str(item.evidence.get("captured_at", ""))
            )
            return verified[-1]
        if errors:
            operation.schedule_cache_errors[calendar_year] = errors[0]
        return None

    @staticmethod
    def _cache_error_reason(error: OfficialCalendarCacheError) -> str:
        if isinstance(error, OfficialCalendarCacheExpired):
            return "twse_holiday_schedule_cache_expired"
        message = str(error).casefold()
        if "year mismatch" in message:
            return "twse_holiday_schedule_cache_wrong_year"
        if "missing" in message:
            return "twse_holiday_schedule_cache_missing"
        return "twse_holiday_schedule_cache_invalid"

    def _schedule_reason(
        self, calendar_year: int, operation: _CalendarOperationState
    ) -> str:
        return operation.schedule_failure_reason.get(
            calendar_year,
            "twse_holiday_schedule_unavailable",
        )

    def _temporary_closure_candidates(self) -> tuple[Path, ...]:
        if self.temporary_closure_path is None:
            return ()
        root = self.temporary_closure_path.expanduser()
        if root.exists() and root.is_file():
            return (root,)
        if root.suffix.casefold() == ".json":
            return (root,)
        if not root.is_dir():
            return ()
        return tuple(sorted(root.glob("twse_temporary_closure_*.json")))

    def _temporary_closure_for(
        self,
        target_date: date,
        operation: _CalendarOperationState,
    ) -> VerifiedTemporaryClosureCache | None:
        """讀取指定日期的官方臨時全面休市事件，缺件不猜。"""

        if self.temporary_closure_path is None:
            return None
        if target_date in operation.temporary_closures:
            return operation.temporary_closures[target_date]
        if not operation.temporary_cache_candidates_loaded:
            observed = operation.observation.effective_at
            for candidate in self._temporary_closure_candidates():
                try:
                    item = load_verified_twse_temporary_closure_cache(
                        candidate,
                        observed_at=observed,
                    )
                except OfficialCalendarCacheError as error:
                    operation.temporary_cache_errors.append(error)
                    continue
                operation.temporary_cache_candidates.append(item)
            operation.temporary_cache_candidates_loaded = True
        verified = [
            item
            for item in operation.temporary_cache_candidates
            if item.closure_date == target_date
        ]
        selected: VerifiedTemporaryClosureCache | None = None
        if verified:
            verified.sort(
                key=lambda item: str(item.evidence.get("captured_at", ""))
            )
            selected = verified[-1]
        if operation.temporary_cache_errors:
            operation.temporary_closure_failure_reason[target_date] = (
                f"{type(operation.temporary_cache_errors[0]).__name__}:"
                f"{operation.temporary_cache_errors[0]}"
            )
        operation.temporary_closures[target_date] = selected
        return selected

    def _temporary_closure_scope(
        self, target_date: date, operation: _CalendarOperationState
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "provider": "TWSE",
            "policy_url": TWSE_TEMPORARY_CLOSURE_POLICY_URL,
            "source_kind": "official_event_announcement_optional",
            "event_evidence_required": True,
            "event_evidence_required_for_unplanned_closure": True,
            "path": (
                None
                if self.temporary_closure_path is None
                else str(self.temporary_closure_path.expanduser())
            ),
            "target_date": target_date.isoformat(),
            "status": "not_captured",
        }
        error = operation.temporary_closure_failure_reason.get(target_date)
        if error is not None:
            result.update({"status": "invalid", "error": error})
        return result

    def evidence_for(
        self,
        target_date: date,
        *,
        observation_clock: CalendarObservationClock | CalendarObservation | None = None,
    ) -> dict[str, object]:
        """以一個新 operation 傳回 calendar source custody evidence。"""

        with self.read_operation(
            observation_clock=observation_clock,
            allow_online_probe=True,
        ) as operation:
            return operation.evidence_for(target_date)

    def _evidence_for(
        self,
        target_date: date,
        operation: _CalendarOperationState,
    ) -> dict[str, object]:
        observation = operation.observation.to_dict()
        if target_date.weekday() >= 5:
            return {
                "mode": "calendar_weekend_convention",
                "target_date": target_date.isoformat(),
                "is_trading_day": False,
                "reason_code": "weekend_closed",
                "calendar_observation": observation,
            }
        temporary = self._temporary_closure_for(target_date, operation)
        if temporary is not None:
            evidence = dict(temporary.evidence)
            evidence.update(
                {
                    "target_date": target_date.isoformat(),
                    "is_trading_day": False,
                    "reason_code": "twse_temporary_closure_official",
                    "temporary_closure_scope": {
                        **self._temporary_closure_scope(target_date, operation),
                        "status": "verified",
                    },
                    "annual_schedule_evidence": {
                        "status": "not_required_for_explicit_closure"
                    },
                    "calendar_observation": observation,
                }
            )
            return evidence
        schedule = self._fetch_official_year_schedule(target_date.year, operation)
        evidence = dict(operation.schedule_evidence.get(target_date.year, {}))
        evidence["target_date"] = target_date.isoformat()
        evidence.setdefault(
            "annual_schedule_scope",
            "planned_annual_closures",
        )
        evidence["temporary_closure_scope"] = self._temporary_closure_scope(
            target_date, operation
        )
        evidence["calendar_observation"] = observation
        if schedule is None:
            evidence["is_trading_day"] = None
            evidence["reason_code"] = self._schedule_reason(
                target_date.year, operation
            )
        else:
            flag = (
                schedule[target_date]
                if target_date in schedule
                else True
            )
            evidence["is_trading_day"] = flag
            if evidence.get("mode") == "hash_bound_official_calendar_cache":
                evidence["reason_code"] = (
                    "twse_holiday_schedule_cache_explicit_open"
                    if target_date in schedule and flag
                    else "twse_holiday_schedule_cache_closed"
                    if target_date in schedule
                    else "twse_holiday_schedule_cache_open"
                )
            else:
                evidence["reason_code"] = (
                    "twse_holiday_schedule_explicit_open"
                    if target_date in schedule and flag
                    else "twse_holiday_schedule_closed"
                    if target_date in schedule
                    else "twse_holiday_schedule_open"
                )
        return evidence

    def _has_local_market_index_evidence(self, target_date: date) -> bool:
        """僅供停用線上查詢的歷史回補使用，不推定缺列是休市。"""

        date_yyyymmdd = target_date.strftime("%Y%m%d")
        if not self.db_path.exists():
            return False
        try:
            with closing(connect_read_only_sqlite(self.db_path)) as conn:
                columns = {
                    str(row[1])
                    for row in conn.execute("PRAGMA table_info(market_indices)")
                }
                date_column = next(
                    (
                        column
                        for column in ("日期", "trade_date", "date")
                        if column in columns
                    ),
                    None,
                )
                if date_column is None:
                    return False
                count = conn.execute(
                    f'SELECT COUNT(*) FROM market_indices WHERE "{date_column}" = ?',
                    (date_yyyymmdd,),
                ).fetchone()[0]
                check_read_cancelled()
                return bool(count > 0)
        except ReadOperationCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - 本地證據失效時保持未知
            check_read_cancelled()
            logger.warning("讀取 DB 交易日證據失敗 (%s): %s", target_date, exc)
            return False

    def is_official_trading_day(
        self,
        target_date: date,
        allow_online_probe: bool = True,
        *,
        observation_clock: CalendarObservationClock | CalendarObservation | None = None,
    ) -> Tuple[Optional[bool], str]:
        """判定單日；此單次呼叫自成 operation。"""

        with self.read_operation(
            observation_clock=observation_clock,
            allow_online_probe=allow_online_probe,
        ) as operation:
            return operation.is_official_trading_day(target_date)

    def _is_official_trading_day(
        self,
        target_date: date,
        operation: _CalendarOperationState,
    ) -> Tuple[Optional[bool], str]:
        if target_date.weekday() >= 5:
            return False, "weekend_closed"
        if self._temporary_closure_for(target_date, operation) is not None:
            return False, "twse_temporary_closure_official"

        schedule = self._fetch_official_year_schedule(target_date.year, operation)
        if schedule is None:
            if (
                not operation.allow_online_probe
                and operation.observation.mode != "historical_as_of"
                and self._has_local_market_index_evidence(target_date)
            ):
                return True, "twstock_db_market_indices_evidence"
            return None, (
                "lacks_official_evidence"
                if not operation.allow_online_probe
                else self._schedule_reason(target_date.year, operation)
            )

        if operation.schedule_evidence.get(target_date.year, {}).get("mode") == (
            "hash_bound_official_calendar_cache"
        ):
            if target_date not in schedule:
                return True, "twse_holiday_schedule_cache_open"
            if schedule[target_date]:
                return True, "twse_holiday_schedule_cache_explicit_open"
            return False, "twse_holiday_schedule_cache_closed"
        if target_date not in schedule:
            return True, "twse_holiday_schedule_open"
        if schedule[target_date]:
            return True, "twse_holiday_schedule_explicit_open"
        return False, "twse_holiday_schedule_closed"

    def get_trading_days_in_range(
        self,
        start_date: date,
        end_date: date,
        allow_online_probe: bool = True,
        *,
        observation_clock: CalendarObservationClock | CalendarObservation | None = None,
    ) -> list[dict[str, object]]:
        """掃描區間；所有日子共用同一 operation 與觀測時鐘。"""

        with self.read_operation(
            observation_clock=observation_clock,
            allow_online_probe=allow_online_probe,
        ) as operation:
            return operation.get_trading_days_in_range(start_date, end_date)

    def _get_trading_days_in_range(
        self,
        start_date: date,
        end_date: date,
        operation: _CalendarOperationState,
    ) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        current = start_date
        while current <= end_date:
            is_td, reason = self._is_official_trading_day(current, operation)
            results.append(
                {
                    "date": current,
                    "date_str": current.isoformat(),
                    "is_trading_day": is_td,
                    "reason_code": reason,
                }
            )
            current += timedelta(days=1)
        return results

    def require_trading_days_in_range(
        self,
        start_date: date,
        end_date: date,
        *,
        allow_online_probe: bool = True,
        observation_clock: CalendarObservationClock | CalendarObservation | None = None,
    ) -> list[dict[str, object]]:
        """拒絕未解析日期，並在同一 operation 回傳來源 custody evidence。"""

        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")
        with self.read_operation(
            observation_clock=observation_clock,
            allow_online_probe=allow_online_probe,
        ) as operation:
            return operation.require_trading_days_in_range(start_date, end_date)

    def _require_trading_days_in_range(
        self,
        start_date: date,
        end_date: date,
        operation: _CalendarOperationState,
    ) -> list[dict[str, object]]:
        results = self._get_trading_days_in_range(start_date, end_date, operation)
        unknown = [
            str(item["date_str"])
            for item in results
            if item.get("is_trading_day") is None
        ]
        if unknown:
            raise OfficialTradingCalendarError(
                "official trading calendar unresolved: " + ", ".join(unknown)
            )
        for item in results:
            target = item.get("date")
            if isinstance(target, date):
                item["evidence"] = self._evidence_for(target, operation)
        return results

    def get_recent_official_trading_days(
        self,
        reference_date: date,
        count: int,
        *,
        include_reference: bool = True,
        allow_online_probe: bool = True,
        max_lookback_days: int = 92,
        observation_clock: CalendarObservationClock | CalendarObservation | None = None,
    ) -> list[dict[str, object]]:
        """取得最近交易日；掃描和各日 evidence 共用一個 operation。"""

        if count <= 0:
            return []
        if max_lookback_days < count:
            raise ValueError("max_lookback_days must be >= count")
        with self.read_operation(
            observation_clock=observation_clock,
            allow_online_probe=allow_online_probe,
        ) as operation:
            return operation.get_recent_official_trading_days(
                reference_date,
                count,
                include_reference=include_reference,
                max_lookback_days=max_lookback_days,
            )

    def _get_recent_official_trading_days(
        self,
        reference_date: date,
        count: int,
        operation: _CalendarOperationState,
        *,
        include_reference: bool,
        max_lookback_days: int,
    ) -> list[dict[str, object]]:
        selected: list[dict[str, object]] = []
        current = reference_date
        scanned = 0
        while scanned <= max_lookback_days and len(selected) < count:
            check_read_cancelled()
            is_trading, reason = self._is_official_trading_day(current, operation)
            if is_trading is None:
                raise OfficialTradingCalendarError(
                    f"official trading calendar unresolved: {current.isoformat()} ({reason})"
                )
            if is_trading and (include_reference or current != reference_date):
                selected.append(
                    {
                        "date": current,
                        "date_str": current.isoformat(),
                        "is_trading_day": True,
                        "reason_code": reason,
                        "evidence": self._evidence_for(current, operation),
                    }
                )
            current -= timedelta(days=1)
            scanned += 1
        if len(selected) < count:
            raise OfficialTradingCalendarError(
                "official trading calendar lookback exhausted: "
                f"requested={count}, resolved={len(selected)}, "
                f"reference={reference_date.isoformat()}"
            )
        selected.reverse()
        return selected


class OfficialTradingCalendarError(RuntimeError):
    """Raised when an update cannot establish an official trading-day set."""
