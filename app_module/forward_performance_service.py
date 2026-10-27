from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from contextlib import closing
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import sqlite3
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

from app_module.evidence_event_dtos import (
    EvidenceDataQuality,
    EvidenceEvent,
    EvidenceEventType,
    EvidenceOutcome,
    EvidenceOutcomeStatus,
)
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.evidence_event_service import EvidenceEventService
from app_module.evidence_event_importer_dtos import capture_context_is_valid
from app_module.corporate_action_policy import CorporateActionProvider, CorporateActionPolicy
from app_module.trading_restriction_policy import TradingRestrictionProvider, TradingRestrictionPolicy
from app_module.event_price_resolver import (
    EventPriceObservation,
    EventPriceResolution,
    EventPriceResolver,
)
from app_module.official_maturity_calendar import OfficialMaturityCalendar
from app_module.outcome_maturity_service import OutcomeMaturity, OutcomeMaturityService
from app_module.paper_portfolio_time import TAIWAN_MARKET_TIMEZONE
from app_module.forward_source_observation import ForwardSourceObservationRecorder
from app_module.forward_daily_price_source_binding import (
    ForwardDailyPriceSourceBinder, PRICE_PROJECTION_COLUMNS, PRICE_DIRECTION_COLUMNS,
    has_full_price_projection, unknown_price_source_binding,
)
from data_module.twse_quote_observation_capture import SESSION_CLOSE


_DATETIME_TYPE = datetime
DEFAULT_MARKET_BENCHMARK_ID = "TAIEX"
INDEX_TABLES = {"market_indices", "industry_indices"}
INDEX_DATE_COLUMNS = ("日期", "Date", "date")
INDEX_NAME_COLUMNS = ("指數名稱", "index_name", "name")
INDEX_CLOSE_COLUMNS = ("收盤指數", "收盤價", "Close", "close")
MARKET_BENCHMARK_ALIASES = (
    DEFAULT_MARKET_BENCHMARK_ID,
    "發行量加權股價指數",
    "加權指數",
    "TAIEX Total Index",
)


def _source_qualified_warnings(
    warnings: Iterable[str], source_family: str
) -> tuple[str, ...]:
    """Keep a missing-source warning attributable to the source that emitted it."""

    return tuple(
        f"{source_family}_source_not_ingested"
        if warning == "source_not_ingested"
        else warning
        for warning in warnings
    )


def _has_complete_cohort_identity(event: EvidenceEvent) -> bool:
    """Return whether an event can be placed in a V4 effectiveness cohort."""

    if not all(
        _identity_text(value)
        for value in (
            event.strategy_version_id,
            event.cost_model_id,
            event.benchmark_id,
        )
    ):
        return False
    metadata: Mapping[str, Any] = event.metadata if isinstance(event.metadata, Mapping) else {}
    policy_id = metadata.get("universe_policy_id")
    snapshot_id = metadata.get("universe_snapshot_id")
    policy_hash = metadata.get("universe_policy_hash")
    snapshot_hash = metadata.get("universe_snapshot_hash")
    identity_schema = _identity_text(metadata.get("universe_identity_schema"))
    if _identity_text(policy_id):
        if (
            not _identity_text(snapshot_id)
            or not _identity_text(snapshot_hash)
            or not _identity_text(policy_hash)
        ):
            return False
    elif identity_schema in {
        "recommendation-universe.v1",
        "recommendation-universe-snapshot.v1",
    }:
        # 舊版 daily digest 不能被當成跨日政策身份。
        return False
    elif not _identity_text(metadata.get("universe_id")):
        # 保留無新版 schema 的舊 caller 相容性；它只作 legacy 診斷。
        return False
    strategy_config_schema = _identity_text(metadata.get("strategy_config_schema"))
    if strategy_config_schema and not _identity_text(metadata.get("strategy_config_id")):
        return False
    horizon = metadata.get("horizon_days", metadata.get("expected_horizon_days"))
    if horizon is None or isinstance(horizon, bool):
        return False
    try:
        parsed_horizon = Decimal(str(horizon).strip())
    except (InvalidOperation, TypeError, ValueError):
        return False
    return (
        parsed_horizon.is_finite()
        and parsed_horizon == parsed_horizon.to_integral_value()
        and parsed_horizon > 0
    )


def _identity_text(value: object) -> str:
    if value is None or isinstance(value, (bool, Mapping, list, tuple)):
        return ""
    return str(value).strip()


def extract_event_decision_cutoff(event: EvidenceEvent | None) -> datetime | None:
    """只解析既有 capture context 的研究時鐘；零散 metadata 不是時間證據。"""
    if event is None:
        return None
    meta = event.metadata if isinstance(event.metadata, Mapping) else {}
    context = meta.get("capture_context")
    if not isinstance(context, Mapping) or not capture_context_is_valid(context):
        return None
    if (
        context.get("temporal_status") != "verified"
        or context.get("research_only") is not True
        or context.get("preopen_authority") is not False
        or context.get("natural_authority") is not False
        or context.get("source_availability_preserved") is not True
    ):
        return None
    try:
        cutoff = datetime.fromisoformat(str(context["decision_at"]).replace("Z", "+00:00"))
        captured = datetime.fromisoformat(str(context["captured_at"]).replace("Z", "+00:00"))
        if any(value.tzinfo is None or value.utcoffset() is None for value in (cutoff, captured)):
            return None
        day = cutoff.astimezone(TAIWAN_MARKET_TIMEZONE).date()
        if date.fromisoformat(event.decision_date) != day or date.fromisoformat(event.event_date) > day:
            return None
        if captured < cutoff or date.fromisoformat(str(context["as_of"])) > day:
            return None
        for field in ("decision_cutoff", "decision_cutoff_at", "decision_cutoff_utc", "event_decision_cutoff"):
            if meta.get(field) is not None:
                other = datetime.fromisoformat(str(meta[field]).replace("Z", "+00:00"))
                if other.tzinfo is None or other.utcoffset() is None or other != cutoff:
                    return None
        return cutoff.astimezone(timezone.utc)
    except (ValueError, TypeError, KeyError, OverflowError):
        return None


def _event_identity_metadata(event: EvidenceEvent) -> dict[str, Any]:
    """把事件的明確 cohort identity 複製到 outcome metadata。

    Read model 仍以 event join 為主；這份副本讓單獨保存的 outcome receipt
    也能保留政策／快照追溯，不會由下游重新猜測身份。
    """

    source = event.metadata if isinstance(event.metadata, Mapping) else {}
    keys = (
        "strategy_config_id",
        "strategy_config_hash",
        "strategy_config_schema",
        "universe_id",
        "universe_hash",
        "universe_identity_schema",
        "universe_policy_id",
        "universe_policy_hash",
        "universe_policy_schema",
        "universe_snapshot_id",
        "universe_snapshot_hash",
        "universe_snapshot_schema",
        "universe_snapshot_source_provider_id",
        "universe_snapshot_selected_codes_hash",
        "horizon_days",
        "evidence_tier",
        "return_basis",
    )
    metadata = {
        key: source[key]
        for key in keys
        if key in source and source[key] not in (None, "")
    }
    metadata.update(
        {
            "strategy_version_id": event.strategy_version_id,
            "cost_model_id": event.cost_model_id,
            "benchmark_id": event.benchmark_id,
            "industry_benchmark_id": event.industry_benchmark_id,
        }
    )
    return metadata


@dataclass(frozen=True)
class ForwardOutcomeSummary:
    events_scanned: int = 0
    events_skipped_incomplete_identity: int = 0
    events_ready: int = 0
    outcomes_created: int = 0
    outcomes_updated: int = 0
    pending_insufficient_future_data: int = 0
    missing_event_price: int = 0
    missing_outcome_price: int = 0
    missing_benchmark: int = 0
    missing_industry_benchmark: int = 0
    blocked_time_contract_count: int = 0
    warnings_count: int = 0
    warning_counts: Mapping[str, int] = field(default_factory=dict)
    dry_run: bool = True
    invocation_at: str | None = None
    invocation_date_taipei: str | None = None
    requested_data_as_of_date: str | None = None
    effective_data_as_of_date: str | None = None
    price_read_cutoff_date: str | None = None
    price_read_cutoff_basis: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _ForwardPriceReadWindow:
    invocation_at: datetime
    invocation_date_taipei: str
    requested_data_as_of_date: str | None
    effective_data_as_of_date: str
    price_read_cutoff_date: str
    price_read_cutoff_basis: str

    def to_metadata(self) -> dict[str, str | None]:
        return {
            "invocation_at": self.invocation_at.isoformat(),
            "invocation_date_taipei": self.invocation_date_taipei,
            "requested_data_as_of_date": self.requested_data_as_of_date,
            "effective_data_as_of_date": self.effective_data_as_of_date,
            "price_read_cutoff_date": self.price_read_cutoff_date,
            "price_read_cutoff_basis": self.price_read_cutoff_basis,
        }

class ForwardPerformanceService:
    """Calculate close-to-close forward research outcomes for evidence events."""

    def __init__(
        self,
        config: Any,
        repository: EvidenceEventRepository | None = None,
        *,
        db_path: str | Path | None = None,
        maturity_calendar: OfficialMaturityCalendar | None = None,
        clock: Callable[[], datetime] | None = None,
        source_observer: ForwardSourceObservationRecorder | None = None,
        price_source_binder: ForwardDailyPriceSourceBinder | None = None,
    ) -> None:
        self.config = config
        self.repository = repository or EvidenceEventRepository(config)
        self.db_path = Path(db_path) if db_path is not None else Path(config.db_file)
        self._daily_price_cache: dict[
            tuple[str, str | None, str | None], tuple[tuple[str, ...], tuple[tuple[str, Decimal], ...]]
        ] = {}
        self._index_return_cache: dict[tuple[str, str | None, str, str], int | None] = {}
        self._index_table_columns_cache: dict[str, tuple[str, ...]] = {}
        self._source_observer = source_observer
        self._price_source_binder = price_source_binder
        self._daily_price_observation_ids: dict[tuple[str, str | None, str | None], str] = {}
        self._index_return_observation_ids: dict[
            tuple[str, str | None, str, str], tuple[str, ...]
        ] = {}
        self._index_table_column_observation_ids: dict[str, str] = {}
        self._maturity_calendar = maturity_calendar
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._corporate_action_policy = CorporateActionPolicy(CorporateActionProvider(self.db_path))
        self._trading_restriction_policy = TradingRestrictionPolicy(TradingRestrictionProvider(self.db_path))

    def calculate(
        self,
        *,
        windows: Iterable[int] = (5, 10, 20, 60),
        dry_run: bool = True,
        decision_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        event_ids: Iterable[str] | None = None,
        event_type: EvidenceEventType | str | None = None,
        symbol: str | None = None,
        limit: int | None = None,
        data_as_of_date: str | None = None,
        invocation_at: datetime | None = None,
        require_cohort_identity: bool = False,
    ) -> ForwardOutcomeSummary:
        if self._source_observer is not None:
            self._source_observer.begin_calculation()
        self._daily_price_cache.clear()
        self._index_return_cache.clear()
        self._index_table_columns_cache.clear()
        self._daily_price_observation_ids.clear()
        self._index_return_observation_ids.clear()
        self._index_table_column_observation_ids.clear()
        read_window = self._resolve_price_read_window(
            data_as_of_date=data_as_of_date,
            invocation_at=invocation_at,
        )
        windows = tuple(int(item) for item in windows)
        events = self.repository.list_events(
            symbol=symbol,
            event_type=event_type,
            decision_date=decision_date,
            start_date=start_date,
            end_date=end_date,
            event_ids=event_ids,
            limit=limit,
            incomplete_outcomes_first=True,
            outcome_windows=windows,
        )
        skipped_incomplete_identity = 0
        if require_cohort_identity:
            # Keep a bounded diagnostic pass for the skip count, then use a
            # SQL identity gate before applying the same bounded event limit.
            # This prevents a large legacy backlog from consuming all slots
            # and starving a valid long-horizon pending event.
            skipped_incomplete_identity = sum(
                not _has_complete_cohort_identity(event) for event in events
            )
            events = self.repository.list_events(
                symbol=symbol,
                event_type=event_type,
                decision_date=decision_date,
                start_date=start_date,
                end_date=end_date,
                event_ids=event_ids,
                limit=limit,
                incomplete_outcomes_first=True,
                outcome_windows=windows,
                complete_cohort_identity_only=True,
            )
        counters = {
            "events_scanned": len(events),
            "events_skipped_incomplete_identity": skipped_incomplete_identity,
            "events_ready": 0,
            "outcomes_created": 0,
            "outcomes_updated": 0,
            "pending_insufficient_future_data": 0,
            "missing_event_price": 0,
            "missing_outcome_price": 0,
            "missing_benchmark": 0,
            "missing_industry_benchmark": 0,
            "blocked_time_contract_count": 0,
            "warnings_count": 0,
        }
        warning_counts: Counter[str] = Counter()
        pending_writes: list[EvidenceOutcome] = []

        for event in events:
            if not event.symbol or event.symbol.upper() == "MARKET":
                continue
            counters["events_ready"] += 1
            for window in tuple(int(item) for item in windows):
                existing = self.repository.get_outcome(event.event_id, window)
                if self._source_observer is not None:
                    self._source_observer.begin_outcome(
                        event_id=event.event_id, window_days=window
                    )
                try:
                    outcome = self._build_outcome(
                        event,
                        window,
                        data_as_of_date=read_window.price_read_cutoff_date,
                    )
                except Exception:
                    if self._source_observer is not None:
                        self._source_observer.end_outcome()
                        # 計算失敗時仍須發布已讀取的部分觀察資料，再向外拋出例外；
                        # 錯誤路徑不會 upsert outcome。
                        self._source_observer.persist()
                    raise
                else:
                    query_ids = (
                        self._source_observer.end_outcome()
                        if self._source_observer is not None
                        else ()
                    )
                outcome = replace(outcome, metadata={
                    **outcome.metadata,
                    **read_window.to_metadata(),
                    "evidence_lineage": EvidenceEventService.lineage_for(event),
                    "is_execution_pnl": False,
                    **_event_identity_metadata(event),
                })
                if self._source_observer is not None:
                    self._source_observer.record_outcome(
                        event_id=event.event_id,
                        window_days=window,
                        return_basis=outcome.return_basis,
                        outcome_status=getattr(
                            outcome.outcome_status,
                            "value",
                            str(outcome.outcome_status),
                        ),
                        outcome_payload={
                            "outcome_id": outcome.outcome_id,
                            "event_id": outcome.event_id,
                            "window_days": outcome.window_days,
                            "window_type": outcome.window_type,
                            "return_basis": outcome.return_basis,
                            "event_price_date": outcome.event_price_date,
                            "event_close": outcome.event_close,
                            "outcome_price_date": outcome.outcome_price_date,
                            "outcome_close": outcome.outcome_close,
                            "forward_return_bp": outcome.forward_return_bp,
                            "benchmark_return_bp": outcome.benchmark_return_bp,
                            "benchmark_excess_bp": outcome.benchmark_excess_bp,
                            "industry_return_bp": outcome.industry_return_bp,
                            "industry_excess_bp": outcome.industry_excess_bp,
                            "max_adverse_excursion_bp": outcome.max_adverse_excursion_bp,
                            "max_favorable_excursion_bp": outcome.max_favorable_excursion_bp,
                            "outcome_status": getattr(
                                outcome.outcome_status,
                                "value",
                                str(outcome.outcome_status),
                            ),
                            "data_quality": getattr(
                                outcome.data_quality,
                                "value",
                                str(outcome.data_quality),
                            ),
                            "warnings": list(outcome.warnings),
                            "data_as_of_date": outcome.data_as_of_date,
                            "metadata": outcome.metadata,
                        },
                        query_ids=query_ids,
                    )
                counters["warnings_count"] += len(outcome.warnings)
                warning_counts.update(outcome.warnings)
                if outcome.metadata.get("time_contract_state") == "blocked_time_contract":
                    counters["blocked_time_contract_count"] += 1
                if outcome.outcome_status == EvidenceOutcomeStatus.INSUFFICIENT_FUTURE_DATA:
                    counters["pending_insufficient_future_data"] += 1
                if "missing_event_price" in outcome.warnings:
                    counters["missing_event_price"] += 1
                if "missing_outcome_price" in outcome.warnings:
                    counters["missing_outcome_price"] += 1
                if "missing_benchmark" in outcome.warnings:
                    counters["missing_benchmark"] += 1
                if "missing_industry_benchmark" in outcome.warnings:
                    counters["missing_industry_benchmark"] += 1
                if existing is None:
                    counters["outcomes_created"] += 1
                else:
                    counters["outcomes_updated"] += 1
                if not dry_run:
                    pending_writes.append(outcome)

        if self._source_observer is not None:
            self._source_observer.persist()

        if not dry_run:
            # Commit the bounded run as one transaction.  A source or SQLite
            # failure therefore leaves the outcome table unchanged instead of
            # exposing a partially written batch to the next scheduled run.
            self.repository.upsert_outcomes(pending_writes)

        return ForwardOutcomeSummary(
            events_scanned=counters["events_scanned"],
            events_skipped_incomplete_identity=counters[
                "events_skipped_incomplete_identity"
            ],
            events_ready=counters["events_ready"],
            outcomes_created=counters["outcomes_created"],
            outcomes_updated=counters["outcomes_updated"],
            pending_insufficient_future_data=counters[
                "pending_insufficient_future_data"
            ],
            missing_event_price=counters["missing_event_price"],
            missing_outcome_price=counters["missing_outcome_price"],
            missing_benchmark=counters["missing_benchmark"],
            missing_industry_benchmark=counters["missing_industry_benchmark"],
            blocked_time_contract_count=counters["blocked_time_contract_count"],
            warnings_count=counters["warnings_count"],
            warning_counts=dict(sorted(warning_counts.items())),
            dry_run=dry_run,
            invocation_at=read_window.invocation_at.isoformat(),
            invocation_date_taipei=read_window.invocation_date_taipei,
            requested_data_as_of_date=read_window.requested_data_as_of_date,
            effective_data_as_of_date=read_window.effective_data_as_of_date,
            price_read_cutoff_date=read_window.price_read_cutoff_date,
            price_read_cutoff_basis=read_window.price_read_cutoff_basis,
        )

    def _resolve_price_read_window(
        self,
        *,
        data_as_of_date: str | None,
        invocation_at: datetime | None,
    ) -> _ForwardPriceReadWindow:
        clock_now = self._aware_utc(self._clock(), field_name="clock")
        frozen_at = (
            clock_now
            if invocation_at is None
            else self._aware_utc(invocation_at, field_name="invocation_at")
        )
        if frozen_at > clock_now:
            raise ValueError("invocation_at cannot be in the future")

        invocation_local = frozen_at.astimezone(TAIWAN_MARKET_TIMEZONE)
        invocation_day = invocation_local.date()
        requested_day = (
            invocation_day
            if data_as_of_date is None
            else self._parse_iso_date(data_as_of_date, field_name="data_as_of_date")
        )
        if requested_day > invocation_day:
            raise ValueError("data_as_of_date cannot be later than invocation date")

        session_closed = invocation_local.timetz().replace(tzinfo=None) >= SESSION_CLOSE
        clock_read_day = (
            invocation_day
            if session_closed
            else invocation_day - timedelta(days=1)
        )
        price_read_day = min(requested_day, clock_read_day)
        if requested_day < invocation_day:
            cutoff_basis = "explicit_historical_data_as_of_date"
        elif session_closed:
            cutoff_basis = "official_session_close_elapsed"
        else:
            cutoff_basis = "current_session_close_not_reached"

        return _ForwardPriceReadWindow(
            invocation_at=frozen_at,
            invocation_date_taipei=invocation_day.isoformat(),
            requested_data_as_of_date=(
                None if data_as_of_date is None else requested_day.isoformat()
            ),
            effective_data_as_of_date=requested_day.isoformat(),
            price_read_cutoff_date=price_read_day.isoformat(),
            price_read_cutoff_basis=cutoff_basis,
        )

    @staticmethod
    def _aware_utc(value: datetime, *, field_name: str) -> datetime:
        if not isinstance(value, _DATETIME_TYPE):
            raise ValueError(f"{field_name} must be an aware datetime")
        try:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be an aware datetime")
            return value.astimezone(timezone.utc)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an aware datetime") from exc

    @classmethod
    def _parse_iso_date(cls, value: str, *, field_name: str) -> date:
        normalized = cls._date_iso(value)
        try:
            return date.fromisoformat(normalized)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a valid ISO date") from exc

    def _build_outcome(
        self,
        event: EvidenceEvent,
        window_days: int,
        *,
        data_as_of_date: str,
    ) -> EvidenceOutcome:
        warnings: list[str] = []
        event_price = self._find_event_price(str(event.symbol), event.event_date, data_as_of_date=data_as_of_date, event=event)
        if event_price is None:
            return EvidenceOutcome(
                outcome_id=f"out_{uuid4().hex}",
                event_id=event.event_id,
                window_days=window_days,
                outcome_status=EvidenceOutcomeStatus.MISSING_PRICE,
                data_quality=EvidenceDataQuality.MISSING,
                warnings=("missing_event_price",),
                metadata={"return_basis": "close_to_close_event_date"},
            )

        event_price_date = str(event_price.price_date)
        event_close = event_price.close
        assert event_close is not None
        event_price_metadata: dict[str, Any] = {
            "return_basis": "close_to_close_event_date",
            "expected_maturity_date_basis": "verified_official_market_sessions_required",
            "maturity_status_basis": "verified_official_market_sessions_required",
        }
        if event_price.fallback_reason is not None:
            event_price_metadata["event_price_fallback_reason"] = event_price.fallback_reason

        if self._maturity_calendar is None:
            event_price_metadata.update(
                {
                    "maturity_basis": "verified_official_market_sessions_required",
                    "time_contract_state": "blocked_time_contract",
                    "readiness_blocker": "official_maturity_calendar_unavailable",
                    "target_price_state": "waiting_for_verified_official_session",
                    "maturity_calendar_comparison": "official_calendar_not_configured",
                }
            )
            return EvidenceOutcome(
                outcome_id=f"out_{uuid4().hex}",
                event_id=event.event_id,
                window_days=window_days,
                event_price_date=event_price_date,
                event_close=str(event_close),
                outcome_status=EvidenceOutcomeStatus.PENDING,
                data_quality=EvidenceDataQuality.DEGRADED,
                warnings=(
                    "blocked_time_contract_requires_review",
                    "official_maturity_calendar_unavailable",
                ),
                metadata=event_price_metadata,
            )

        maturity = self._outcome_maturity(
            str(event.symbol),
            event_price_date,
            window_days,
            data_as_of_date=data_as_of_date,
        )
        # Preserve row-offset results only as diagnostics. The verified
        # calendar below is the sole source of the maturity date/status used
        # to determine outcome readiness.
        event_price_metadata["expected_maturity_date_basis"] = (
            "legacy_price_row_offset"
        )
        event_price_metadata["maturity_status_basis"] = "legacy_price_row_offset"
        if maturity.expected_trading_date is not None:
            event_price_metadata["expected_maturity_date"] = maturity.expected_trading_date
        event_price_metadata["maturity_status"] = maturity.status
        event_price_metadata["remaining_trading_days"] = maturity.remaining_trading_days
        calendar_as_of_date = self._date_iso(data_as_of_date)
        planned = self._maturity_calendar.evaluate(
            event_date=event_price_date,
            window_days=window_days,
            as_of_date=calendar_as_of_date,
        )
        event_price_metadata.update(
            {
                "maturity_basis": "official_market_sessions",
                "planned_official_maturity_date": planned.planned_date,
                "planned_official_maturity_status": planned.status,
                "planned_official_maturity_remaining_sessions": (
                    planned.remaining_sessions
                ),
                "planned_official_calendar": planned.calendar,
            }
        )
        legacy_expected = maturity.expected_trading_date
        if legacy_expected is None or planned.planned_date is None:
            comparison = (
                "official_calendar_unavailable"
                if planned.planned_date is None
                else "legacy_expected_unavailable"
            )
        else:
            comparison = (
                "match"
                if legacy_expected == planned.planned_date
                else "legacy_price_row_offset_differs"
            )
        event_price_metadata["maturity_calendar_comparison"] = comparison
        if planned.planned_date is None:
            event_price_metadata["time_contract_state"] = "blocked_time_contract"
            event_price_metadata["readiness_blocker"] = (
                "official_maturity_calendar_unavailable"
            )
            event_price_metadata["target_price_state"] = "waiting_for_verified_official_session"
            return EvidenceOutcome(
                outcome_id=f"out_{uuid4().hex}",
                event_id=event.event_id,
                window_days=window_days,
                event_price_date=event_price_date,
                event_close=str(event_close),
                outcome_status=EvidenceOutcomeStatus.PENDING,
                data_quality=EvidenceDataQuality.DEGRADED,
                warnings=(
                    "blocked_time_contract_requires_review",
                    "official_maturity_calendar_unavailable",
                ),
                metadata=event_price_metadata,
            )
        planned_date = str(planned.planned_date)
        event_price_metadata["official_maturity_date"] = planned_date
        if planned_date > calendar_as_of_date:
            event_price_metadata["target_price_state"] = "waiting_for_planned_official_session"
            event_price_metadata["source_price_gap_reason"] = None
            return EvidenceOutcome(
                outcome_id=f"out_{uuid4().hex}",
                event_id=event.event_id,
                window_days=window_days,
                event_price_date=event_price_date,
                event_close=str(event_close),
                outcome_status=EvidenceOutcomeStatus.INSUFFICIENT_FUTURE_DATA,
                data_quality=EvidenceDataQuality.MISSING,
                warnings=("insufficient_future_data",),
                metadata=event_price_metadata,
            )
        outcome_price, lookup_status = self._find_exact_official_outcome_price(
            str(event.symbol),
            planned_date,
            data_as_of_date=calendar_as_of_date,
        )
        event_price_metadata["official_target_price_lookup_status"] = lookup_status
        if outcome_price is None:
            event_price_metadata["target_price_state"] = "missing_at_planned_official_session"
            event_price_metadata["source_price_gap_reason"] = (
                "no_close_on_planned_official_session"
            )
            event_price_metadata["official_target_price_lookup_detail"] = lookup_status
            return EvidenceOutcome(
                outcome_id=f"out_{uuid4().hex}",
                event_id=event.event_id,
                window_days=window_days,
                event_price_date=event_price_date,
                event_close=str(event_close),
                outcome_status=EvidenceOutcomeStatus.MISSING_PRICE,
                data_quality=EvidenceDataQuality.MISSING,
                warnings=(
                    "missing_outcome_price",
                    "official_target_session_price_missing",
                ),
                metadata=event_price_metadata,
            )
        event_price_metadata["target_price_state"] = "observed_on_planned_official_session"
        event_price_metadata["source_price_gap_reason"] = None
        event_price_metadata["official_target_price_lookup_detail"] = lookup_status
        if outcome_price is None:
            return EvidenceOutcome(
                outcome_id=f"out_{uuid4().hex}",
                event_id=event.event_id,
                window_days=window_days,
                event_price_date=event_price_date,
                event_close=str(event_close),
                outcome_status=EvidenceOutcomeStatus.INSUFFICIENT_FUTURE_DATA,
                data_quality=EvidenceDataQuality.MISSING,
                warnings=("insufficient_future_data",),
                metadata=event_price_metadata,
            )

        outcome_price_date, outcome_close = outcome_price
        forward_return_bp = self._return_bp(outcome_close, event_close)
        benchmark_return_bp = self._index_return_bp(
            "market_indices",
            event.benchmark_id or DEFAULT_MARKET_BENCHMARK_ID,
            event_price_date,
            outcome_price_date,
        )
        if benchmark_return_bp is None:
            warnings.append("missing_benchmark")
        benchmark_excess_bp = (
            None if benchmark_return_bp is None else forward_return_bp - benchmark_return_bp
        )

        industry_name = event.industry_benchmark_id or event.sector
        industry_return_bp = self._index_return_bp(
            "industry_indices",
            industry_name,
            event_price_date,
            outcome_price_date,
        )
        if industry_return_bp is None:
            warnings.append("missing_industry_benchmark")
        industry_excess_bp = None if industry_return_bp is None else forward_return_bp - industry_return_bp

        corporate_action_warnings = self._corporate_action_policy.check_corporate_action_gap(
            str(event.symbol), event_price_date, outcome_price_date
        )
        warnings.extend(
            _source_qualified_warnings(corporate_action_warnings, "corporate_action")
        )
        
        trading_restriction_warnings = self._trading_restriction_policy.check_restriction_gap(
            str(event.symbol), event_price_date, outcome_price_date
        )
        warnings.extend(
            _source_qualified_warnings(trading_restriction_warnings, "trading_restriction")
        )

        quality = EvidenceDataQuality.OBSERVED if not warnings else EvidenceDataQuality.DEGRADED
        return EvidenceOutcome(
            outcome_id=f"out_{uuid4().hex}",
            event_id=event.event_id,
            window_days=window_days,
            event_price_date=event_price_date,
            event_close=str(event_close),
            outcome_price_date=outcome_price_date,
            outcome_close=str(outcome_close),
            forward_return_bp=forward_return_bp,
            benchmark_return_bp=benchmark_return_bp,
            benchmark_excess_bp=benchmark_excess_bp,
            industry_return_bp=industry_return_bp,
            industry_excess_bp=industry_excess_bp,
            outcome_status=EvidenceOutcomeStatus.READY,
            data_quality=quality,
            warnings=tuple(warnings),
            data_as_of_date=outcome_price_date,
            metadata=event_price_metadata,
        )

    def _find_event_price(
        self,
        symbol: str,
        event_date: str,
        *,
        data_as_of_date: str | None = None,
        event: EvidenceEvent | None = None,
    ) -> EventPriceResolution | None:
        target = self._date_key(event_date)
        as_of = self._date_key(data_as_of_date) if data_as_of_date else None
        event_cutoff = extract_event_decision_cutoff(event) if event is not None else None
        cutoff_isolation_key = None
        active_baseline_policy = None
        if self._price_source_binder is not None:
            conf_policy = getattr(self._price_source_binder, "qualification_policy", None)
            if conf_policy is not None and getattr(conf_policy, "temporal_role", None) == "decision_baseline":
                context_verified = False
                if event_cutoff is not None and event is not None:
                    expected_hash = EvidenceEventService(self.repository).build_event_hash(
                        event_date=event.event_date, decision_date=event.decision_date,
                        symbol=event.symbol, event_type=event.event_type,
                        source_type=event.source_type, source_id=event.source_id,
                        source_snapshot_id=event.source_snapshot_id,
                        reason_codes=event.reason_codes, why_not_codes=event.why_not_codes,
                        risk_codes=event.risk_codes, strategy_version_id=event.strategy_version_id,
                        profile_id=event.profile_id, run_id=event.run_id, metadata=event.metadata,
                    )
                    context_capture = datetime.fromisoformat(
                        event.metadata["capture_context"]["captured_at"].replace("Z", "+00:00")
                    )
                    context_verified = (
                        expected_hash == event.event_hash
                        and event_cutoff <= conf_policy.cutoff_at
                        and context_capture <= conf_policy.cutoff_at
                    )
                if context_verified and event is not None and event_cutoff is not None:
                    cutoff_isolation_key = f"{event.event_id}:{event.event_hash}:{event_cutoff.isoformat()}"
                    parsed_event_date = self._parse_iso_date(event_date, field_name="event_date")
                    active_baseline_policy = self._price_source_binder.build_event_policy(
                        temporal_role="decision_baseline",
                        cutoff_at=event_cutoff,
                        decision_cutoff_at=event_cutoff,
                        event_price_date=parsed_event_date,
                        event_context={
                            "qualification_event_id": event.event_id,
                            "qualification_event_hash": event.event_hash,
                            "qualification_event_context_hash": event.metadata["capture_context"]["capture_context_identity_hash"],
                            "qualification_event_price_date": parsed_event_date.isoformat(),
                            "qualification_context_basis": "validated_research_capture_context",
                        },
                    )
                else:
                    cutoff_isolation_key = f"unverifiable:{event.event_id if event else 'no_event'}"
                    active_baseline_policy = "decision_cutoff_missing_or_unverifiable"
        if cutoff_isolation_key is not None or active_baseline_policy is not None:
            _, values = self._daily_price_series(
                symbol,
                as_of_date=data_as_of_date,
                cutoff_isolation_key=cutoff_isolation_key,
                qualification_policy=active_baseline_policy,
            )
        else:
            _, values = self._daily_price_series(
                symbol,
                as_of_date=data_as_of_date,
            )
        resolution = EventPriceResolver().resolve(
            decision_date=self._date_iso(target),
            data_as_of_date=self._date_iso(as_of) if as_of is not None else None,
            prices=tuple(
                EventPriceObservation(self._date_iso(date_key), close_value)
                for date_key, close_value in values
            ),
        )
        if resolution.price_date is None or resolution.close is None:
            return None
        return resolution

    def _outcome_maturity(
        self,
        symbol: str,
        event_price_date: str,
        window_days: int,
        *,
        data_as_of_date: str | None,
    ) -> OutcomeMaturity:
        keys, _ = self._daily_price_series(
            symbol,
            as_of_date=data_as_of_date,
        )
        trading_dates = tuple(self._date_iso(key) for key in keys)
        as_of = data_as_of_date or (trading_dates[-1] if trading_dates else event_price_date)
        return OutcomeMaturityService().evaluate(
            event_date=event_price_date,
            window_days=window_days,
            trading_dates=trading_dates,
            as_of_date=as_of,
        )

    def _find_outcome_price(
        self,
        symbol: str,
        event_price_date: str,
        window_days: int,
        *,
        data_as_of_date: str | None = None,
    ) -> tuple[str, Decimal] | None:
        target = self._date_key(event_price_date)
        as_of = self._date_key(data_as_of_date) if data_as_of_date else None
        keys, values = self._daily_price_series(
            symbol,
            as_of_date=data_as_of_date,
        )
        start_index = bisect_right(keys, target)
        outcome_index = start_index + int(window_days) - 1
        if outcome_index >= len(values):
            return None
        date_key, close_value = values[outcome_index]
        if as_of and date_key > as_of:
            return None
        return (self._date_iso(date_key), close_value)

    def _find_exact_official_outcome_price(
        self,
        symbol: str,
        planned_date: str,
        *,
        data_as_of_date: str,
    ) -> tuple[tuple[str, Decimal] | None, str]:
        """Read only the exact, already-matured official target session close."""

        target_key = self._date_key(planned_date)
        as_of_key = self._date_key(data_as_of_date)
        if target_key > as_of_key:
            return None, "target_after_data_cutoff"
        date_column = "\u65e5\u671f"
        symbol_column = "\u8b49\u5238\u4ee3\u865f"
        close_column = "\u6536\u76e4\u50f9"
        with closing(
            sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)
        ) as conn:
            conn.execute("PRAGMA query_only = ON")
            fetched_columns = self._price_fetch_columns(conn, date_column, close_column)
            selected_columns = ", ".join(self._quote_identifier(column) for column in fetched_columns)
            query = f"""
                SELECT {selected_columns}
                FROM daily_prices
                WHERE {self._quote_identifier(symbol_column)} = ?
                  AND REPLACE(REPLACE(CAST({self._quote_identifier(date_column)} AS TEXT), '-', ''), '/', '') = ?
                LIMIT 2
                """
            parameters = (symbol, target_key)
            rows = conn.execute(query, parameters).fetchall()
            if self._source_observer is not None:
                self._source_observer.observe_query(
                    table="daily_prices",
                    query=query,
                    parameters=parameters,
                    rows=rows,
                    symbol=symbol,
                    purpose="exact_official_target_price",
                    **self._price_binding_observation_options(
                        fetched_columns,
                        rows,
                        qualification_policy=(
                            self._price_source_binder.outcome_policy()
                            if self._price_source_binder is not None
                            and getattr(self._price_source_binder, "qualification_policy", None) is not None else None
                        ),
                    ),
                )
        if not rows:
            return None, "no_daily_price_row_on_planned_official_session"
        if len(rows) != 1:
            return None, "multiple_daily_price_rows_on_planned_official_session"
        raw_date, raw_close = rows[0][:2]
        if self._date_key(raw_date) != target_key:
            return None, "daily_price_date_does_not_match_planned_official_session"
        close_value = self._to_decimal(raw_close)
        if close_value is None or close_value <= 0:
            return None, "daily_price_close_missing_or_invalid_on_planned_official_session"
        return (self._date_iso(raw_date), close_value), "verified_unique_close"

    def _index_return_bp(
        self,
        table_name: str,
        index_name: str | None,
        event_price_date: str,
        outcome_price_date: str,
    ) -> int | None:
        if table_name not in INDEX_TABLES:
            return None
        index_candidates = self._index_name_candidates(table_name, index_name)
        if not index_candidates:
            return None

        start_key = self._date_key(event_price_date)
        end_key = self._date_key(outcome_price_date)
        cache_key = (table_name, str(index_name or ""), start_key, end_key)
        if cache_key in self._index_return_cache:
            if self._source_observer is not None:
                for query_id in self._index_return_observation_ids.get(cache_key, ()):
                    self._source_observer.record_use(
                        query_id, purpose=f"{table_name}_benchmark_cache_reuse"
                    )
            return self._index_return_cache[cache_key]
        query_observation_ids: list[str] = []
        with closing(sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.execute("PRAGMA query_only = ON")
            columns = self._index_table_columns(
                conn, table_name, observation_ids=query_observation_ids
            )
            date_column = self._first_existing_column(columns, INDEX_DATE_COLUMNS)
            close_columns = self._existing_columns(columns, INDEX_CLOSE_COLUMNS)
            name_column = self._first_existing_column(columns, INDEX_NAME_COLUMNS)
            if date_column is not None and close_columns:
                for candidate in index_candidates:
                    for close_column in close_columns:
                        start = self._index_value(
                            conn,
                            table_name=table_name,
                            date_column=date_column,
                            name_column=name_column,
                            close_column=close_column,
                            index_name=candidate,
                            date_key=start_key,
                            observation_ids=query_observation_ids,
                        )
                        end = self._index_value(
                            conn,
                            table_name=table_name,
                            date_column=date_column,
                            name_column=name_column,
                            close_column=close_column,
                            index_name=candidate,
                            date_key=end_key,
                            observation_ids=query_observation_ids,
                        )
                        start_value = self._to_decimal(start)
                        end_value = self._to_decimal(end)
                        if start_value is None or end_value is None or start_value <= 0:
                            continue
                        result = self._return_bp(end_value, start_value)
                        self._index_return_cache[cache_key] = result
                        self._index_return_observation_ids[cache_key] = tuple(
                            dict.fromkeys(query_observation_ids)
                        )
                        return result

        self._index_return_cache[cache_key] = None
        self._index_return_observation_ids[cache_key] = tuple(
            dict.fromkeys(query_observation_ids)
        )
        return None

    def _index_table_columns(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        *,
        observation_ids: list[str] | None = None,
    ) -> tuple[str, ...]:
        if table_name not in self._index_table_columns_cache:
            query = f"PRAGMA table_info({self._quote_identifier(table_name)})"
            rows = conn.execute(query).fetchall()
            self._index_table_columns_cache[table_name] = tuple(str(row[1]) for row in rows)
            if self._source_observer is not None:
                query_id = self._source_observer.observe_query(
                    table=table_name,
                    query=query,
                    parameters=(),
                    rows=rows,
                    symbol=None,
                    purpose="index_table_schema",
                )
                self._index_table_column_observation_ids[table_name] = query_id
                if observation_ids is not None:
                    observation_ids.append(query_id)
        elif self._source_observer is not None:
            cached_query_id = self._index_table_column_observation_ids.get(table_name)
            if cached_query_id is not None:
                self._source_observer.record_use(
                    cached_query_id, purpose="index_table_schema_cache_reuse"
                )
                if observation_ids is not None:
                    observation_ids.append(cached_query_id)
        return self._index_table_columns_cache[table_name]

    def _index_value(
        self,
        conn: sqlite3.Connection,
        *,
        table_name: str,
        date_column: str,
        name_column: str | None,
        close_column: str,
        index_name: str | None,
        date_key: str,
        observation_ids: list[str] | None = None,
    ) -> Any:
        table_sql = self._quote_identifier(table_name)
        date_sql = self._quote_identifier(date_column)
        close_sql = self._quote_identifier(close_column)
        parameters: tuple[str, ...]
        if index_name is None:
            if name_column is None:
                query = f"""
                    SELECT {close_sql}
                    FROM {table_sql}
                    WHERE REPLACE(REPLACE(CAST({date_sql} AS TEXT), '-', ''), '/', '') = ?
                      AND {close_sql} IS NOT NULL
                    LIMIT 1
                    """
                parameters = (date_key,)
                row = conn.execute(query, parameters).fetchone()
                self._observe_index_value(
                    observation_ids, table_name, query, parameters, row, index_name
                )
                return None if row is None else row[0]
            name_sql = self._quote_identifier(name_column)
            query = f"""
                SELECT {close_sql}
                FROM {table_sql}
                WHERE ({name_sql} IS NULL OR TRIM(CAST({name_sql} AS TEXT)) = '')
                  AND REPLACE(REPLACE(CAST({date_sql} AS TEXT), '-', ''), '/', '') = ?
                  AND {close_sql} IS NOT NULL
                LIMIT 1
                """
            parameters = (date_key,)
            row = conn.execute(query, parameters).fetchone()
            self._observe_index_value(
                observation_ids, table_name, query, parameters, row, index_name
            )
            return None if row is None else row[0]

        if name_column is None:
            return None
        name_sql = self._quote_identifier(name_column)
        query = f"""
            SELECT {close_sql}
            FROM {table_sql}
            WHERE {name_sql} = ?
              AND REPLACE(REPLACE(CAST({date_sql} AS TEXT), '-', ''), '/', '') = ?
              AND {close_sql} IS NOT NULL
            LIMIT 1
            """
        parameters = (index_name, date_key)
        row = conn.execute(query, parameters).fetchone()
        self._observe_index_value(
            observation_ids, table_name, query, parameters, row, index_name
        )
        return None if row is None else row[0]

    def _observe_index_value(
        self,
        observation_ids: list[str] | None,
        table_name: str,
        query: str,
        parameters: tuple[Any, ...],
        row: tuple[Any, ...] | None,
        index_name: str | None,
    ) -> None:
        if self._source_observer is None:
            return
        query_id = self._source_observer.observe_query(
            table=table_name,
            query=query,
            parameters=parameters,
            rows=() if row is None else (row,),
            symbol=index_name,
            purpose="benchmark_value",
        )
        if observation_ids is not None:
            observation_ids.append(query_id)

    @classmethod
    def _index_name_candidates(cls, table_name: str, index_name: str | None) -> tuple[str | None, ...]:
        raw = str(index_name or "").strip()
        if table_name == "market_indices":
            candidates: list[str | None] = []
            if raw:
                cls._append_unique(candidates, raw)
            if not raw or raw.upper() == DEFAULT_MARKET_BENCHMARK_ID:
                for alias in MARKET_BENCHMARK_ALIASES:
                    cls._append_unique(candidates, alias)
                cls._append_unique(candidates, None)
            return tuple(candidates)

        if not raw:
            return ()
        candidates = []
        for token in cls._split_index_name_tokens(raw):
            for base in cls._industry_base_names(token):
                cls._append_unique(candidates, base)
                cls._append_unique(candidates, f"{base}類指數")
                cls._append_unique(candidates, f"{base}類報酬指數")
        return tuple(candidates)

    @staticmethod
    def _split_index_name_tokens(value: str) -> tuple[str, ...]:
        normalized = value.replace("、", ",").replace("/", ",")
        return tuple(token.strip() for token in normalized.split(",") if token.strip())

    @classmethod
    def _industry_base_names(cls, value: str) -> tuple[str, ...]:
        bases: list[str] = []
        cls._append_unique(bases, value)
        for suffix in ("類報酬指數", "類指數", "報酬指數", "指數"):
            if value.endswith(suffix):
                cls._append_unique(bases, value[: -len(suffix)])

        for base in tuple(bases):
            for suffix in ("工業", "產業", "業"):
                if base.endswith(suffix) and len(base) > len(suffix):
                    cls._append_unique(bases, base[: -len(suffix)])
        return tuple(bases)

    @staticmethod
    def _append_unique(values: list[Any], value: Any) -> None:
        if value not in values:
            values.append(value)

    @staticmethod
    def _first_existing_column(columns: tuple[str, ...], candidates: tuple[str, ...]) -> str | None:
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None

    @staticmethod
    def _existing_columns(columns: tuple[str, ...], candidates: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(candidate for candidate in candidates if candidate in columns)

    @staticmethod
    def _quote_identifier(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    def _daily_price_series(
        self,
        symbol: str,
        *,
        as_of_date: str | None = None,
        cutoff_isolation_key: str | None = None,
        qualification_policy: Any | None = None,
    ) -> tuple[tuple[str, ...], tuple[tuple[str, Decimal], ...]]:
        as_of_key = self._date_key(as_of_date) if as_of_date is not None else None
        cache_key = (symbol, as_of_key, cutoff_isolation_key)
        if (
            qualification_policy is None and cutoff_isolation_key is None
            and self._price_source_binder is not None
            and getattr(self._price_source_binder, "qualification_policy", None) is not None
        ):
            qualification_policy = self._price_source_binder.outcome_policy()
        if cache_key in self._daily_price_cache:
            if self._source_observer is not None:
                query_id = self._daily_price_observation_ids.get(cache_key)
                if query_id is not None:
                    self._source_observer.record_use(
                        query_id, purpose="daily_price_series_cache_reuse"
                    )
            return self._daily_price_cache[cache_key]
        rows: list[tuple[str, Decimal]] = []
        with closing(sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.execute("PRAGMA query_only = ON")
            date_column = "\u65e5\u671f"
            symbol_column = "\u8b49\u5238\u4ee3\u865f"
            close_column = "\u6536\u76e4\u50f9"
            date_sql = self._quote_identifier(date_column)
            symbol_sql = self._quote_identifier(symbol_column)
            close_sql = self._quote_identifier(close_column)
            fetched_columns = self._price_fetch_columns(conn, date_column, close_column)
            selected_columns = ", ".join(self._quote_identifier(column) for column in fetched_columns)
            normalized_date_sql = f"REPLACE(REPLACE(CAST({date_sql} AS TEXT), '-', ''), '/', '')"
            query = f"""
                SELECT {selected_columns}
                FROM daily_prices
                WHERE {symbol_sql} = ?
                  AND {close_sql} IS NOT NULL
                  AND (? IS NULL OR {normalized_date_sql} <= ?)
                ORDER BY {normalized_date_sql} ASC
            """
            parameters = (symbol, as_of_key, as_of_key)
            fetched = conn.execute(query, parameters).fetchall()
            if self._source_observer is not None:
                query_id = self._source_observer.observe_query(
                    table="daily_prices",
                    query=query,
                    parameters=parameters,
                    rows=fetched,
                    symbol=symbol,
                    purpose="decision_baseline" if cutoff_isolation_key is not None else "daily_price_series",
                    **self._price_binding_observation_options(
                        fetched_columns,
                        fetched,
                        qualification_policy=qualification_policy,
                    ),
                )
                self._daily_price_observation_ids[cache_key] = query_id
        for row in fetched:
            raw_date, raw_close = row[:2]
            close_value = self._to_decimal(raw_close)
            if close_value is None:
                continue
            rows.append((self._date_key(raw_date), close_value))
        values = tuple(rows)
        keys = tuple(row[0] for row in values)
        self._daily_price_cache[cache_key] = (keys, values)
        return keys, values

    def _price_fetch_columns(
        self, connection: sqlite3.Connection, date_column: str, close_column: str,
    ) -> tuple[str, ...]:
        if self._price_source_binder is None or self._source_observer is None:
            return date_column, close_column
        present = {row[1] for row in connection.execute('PRAGMA table_info("daily_prices")').fetchall()}
        if not has_full_price_projection(tuple(present)):
            return date_column, close_column
        return (date_column, close_column) + tuple(
            column for column in PRICE_PROJECTION_COLUMNS
            if column not in {date_column, close_column} and column in present
        ) + tuple(
            column for column in PRICE_DIRECTION_COLUMNS
            if column in present and column not in PRICE_PROJECTION_COLUMNS
        )

    def _price_binding_observation_options(
        self,
        columns: tuple[str, ...],
        rows: list[Any],
        *,
        qualification_policy: Any | None = None,
    ) -> dict[str, Any]:
        if self._price_source_binder is None:
            return {}
        if not has_full_price_projection(columns):
            bindings = tuple(unknown_price_source_binding("price_projection_columns_missing") for _ in rows)
        else:
            fetched_rows = tuple(dict(zip(columns, row, strict=True)) for row in rows)
            bindings = (
                self._price_source_binder.bind_rows(fetched_rows)
                if qualification_policy is None
                else self._price_source_binder.bind_rows(
                    fetched_rows, qualification_policy=qualification_policy
                )
            )
        return {"columns": columns, "source_bindings": bindings}

    @staticmethod
    def _return_bp(current: Decimal, base: Decimal) -> int:
        value = ((current - base) / base) * Decimal("10000")
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            parsed = Decimal(str(value).replace(",", ""))
        except (InvalidOperation, ValueError, TypeError):
            return None
        return parsed if parsed.is_finite() else None

    @staticmethod
    def _date_key(value: Any) -> str:
        return str(value).strip().replace("-", "").replace("/", "")

    @classmethod
    def _date_iso(cls, value: Any) -> str:
        key = cls._date_key(value)
        if len(key) == 8 and key.isdigit():
            return f"{key[:4]}-{key[4:6]}-{key[6:]}"
        return str(value)
