"""Read-only current-observed fundamental inputs for natural recommendation runs.

These records remain separate from formal PIT tables.  A run may use them only
when its caller supplies the single aware invocation cutoff captured for that
run.  No database schema or row is created or updated here.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
import csv
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Iterator, Mapping
from zoneinfo import ZoneInfo

from data_module.current_fundamental_snapshots import (
    OPENAPI_MONTHLY_NORMALIZER_VERSION,
    OPENAPI_MONTHLY_SOURCE_IDS,
    MONTHLY_SNAPSHOT_SOURCE,
    MONTHLY_NORMALIZER_VERSION,
    MONTHLY_YOY_COMPARATOR_ITEM_CODE,
    TABLE as CURRENT_FUNDAMENTAL_TABLE,
    _derived_monthly_yoy_comparator_version,
    _is_monthly_yoy_comparator_source_version,
    _monthly_source_available_at,
    _monthly_source_version_parts,
    normalize_current_observation,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_SNAPSHOT_DATASET_ID,
    DAILY_SOURCE_SNAPSHOT_SOURCE_ID,
    DailySourceSnapshot,
    DailySourceSnapshotRecord,
    DailySourceSnapshotReadPort,
    DailySourceUseScope,
)
from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin, DailyMonthlyRevenueCohortReader,
)
from data_module.current_official_valuation import (
    CurrentOfficialValuationReadProvider,
)
from data_module.official_trading_calendar import OfficialTradingCalendar
from data_module.market_session_policy import resolve_project_market_session_boundary


_TAIPEI = ZoneInfo("Asia/Taipei")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OFFICIAL_CALENDAR_CACHE_ROOT = (
    _REPOSITORY_ROOT / "output" / "paper_execution_eod_replay" / "calendar_cache"
)
_DERIVED_MONTHLY_VERSION = re.compile(
    r"(?P<normalizer>mops-current-revenue-normalizer\.v2|"
    r"twse-tpex-openapi-monthly-revenue-parser\.v1):"
    r"(?P<market>twse|tpex):(?P<period>\d{4}-\d{2}):raw:(?P<raw>.+)"
    r":derived:sha256:(?P<digest>[0-9a-f]{64})"
)


def _resolve_calendar_cache_path(value: Path | str | None) -> Path:
    if value is None:
        return DEFAULT_OFFICIAL_CALENDAR_CACHE_ROOT.resolve(strict=False)
    if not isinstance(value, (Path, str)) or not str(value).strip():
        raise ValueError("calendar_cache_path must be a non-empty path")
    return Path(value).expanduser().resolve(strict=False)


def _resolve_temporary_closure_path(
    value: Path | str | None,
    *,
    calendar_cache_path: Path,
) -> Path:
    if value is not None:
        if not isinstance(value, (Path, str)) or not str(value).strip():
            raise ValueError("temporary_closure_path must be a non-empty path")
        return Path(value).expanduser().resolve(strict=False)
    if calendar_cache_path.suffix.casefold() == ".json":
        return calendar_cache_path.parent
    return calendar_cache_path


@dataclass(frozen=True, slots=True)
class CurrentObservedPEInput:
    stock_code: str
    value: Decimal
    as_of_date: date
    available_at: datetime
    source: str
    source_version: str
    market: str
    raw_response_sha256: str
    market_calendar_session_date: date
    market_calendar_reason_code: str
    formal_pit_eligible: bool = False
    availability_basis: str = "official_body_capture"


@dataclass(frozen=True, slots=True)
class CurrentObservedMonthlyRevenueInput:
    stock_code: str
    period: str
    revenue: Decimal
    observed_at: datetime
    source_available_at: datetime | None
    available_at: datetime
    source: str
    source_version: str
    market: str
    raw_source_version: str
    raw_source_sha256: str
    unit: str = "TWD"
    period_basis: str = "monthly_flow"
    basis_verified: bool = True
    aggregate_feature_eligible: bool = False
    formal_pit_eligible: bool = False
    availability_basis: str = "local_verified_observation"
    input_role: str = "reported_period_value"
    parent_report_period: str | None = None
    availability_snapshot_batch_id: str | None = None
    availability_first_persisted_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CurrentMonthlyRevenueReadResult:
    status: str
    stock_code: str
    cutoff_at: datetime
    latest_period: str | None
    observations: tuple[CurrentObservedMonthlyRevenueInput, ...] = ()
    diagnostics: tuple[str, ...] = ()
    blocked_periods: tuple[str, ...] = ()
    comparison_baseline: CurrentObservedMonthlyRevenueInput | None = None
    comparison_snapshot_sha256: str | None = None
    # Counts bind the diagnostic budget to rows actually scanned by this
    # invocation; they are not availability or historical-eligibility claims.
    diagnostic_source_row_count: int = 0
    diagnostic_comparator_row_count: int = 0


class RecommendationCurrentFundamentalProvider:
    """Read current PE captures and verified current monthly-flow observations.

    ``output_root`` is the same canonical output root used by the collector.
    ``db_file`` must already exist; the provider opens it with SQLite read-only
    mode and never materializes the current-observation table.
    """

    def __init__(
        self,
        *,
        db_file: Path,
        output_root: Path,
        monthly_source_root: Path | None = None,
        valuation_provider_factory: Callable[..., Any] | None = None,
        official_calendar_factory: Callable[..., Any] | None = None,
        calendar_cache_path: Path | str | None = None,
        temporary_closure_path: Path | str | None = None,
        daily_source_snapshot_reader: DailySourceSnapshotReadPort | None = None,
    ) -> None:
        self.db_file = Path(db_file).expanduser().resolve(strict=False)
        self.output_root = Path(output_root).expanduser().resolve(strict=False)
        self.monthly_source_root = Path(
            monthly_source_root if monthly_source_root is not None else output_root
        ).expanduser().resolve(strict=False)
        self.daily_source_snapshot_reader = daily_source_snapshot_reader
        self._verified_monthly_capture_cache: dict[
            tuple[str, str, str],
            tuple[dict[str, dict[str, str]], str, tuple[str, ...]],
        ] = {}
        self._valuation_provider_factory = (
            valuation_provider_factory or CurrentOfficialValuationReadProvider
        )
        self.calendar_cache_path = _resolve_calendar_cache_path(calendar_cache_path)
        self.temporary_closure_path = _resolve_temporary_closure_path(
            temporary_closure_path,
            calendar_cache_path=self.calendar_cache_path,
        )
        if official_calendar_factory is None:
            self._official_calendar_factory = self._build_official_calendar
        else:
            # Keep the existing one-argument injection contract for callers and
            # tests that provide their own calendar implementation.
            self._official_calendar_factory = official_calendar_factory

    def _build_official_calendar(self, database: Path) -> OfficialTradingCalendar:
        return OfficialTradingCalendar(
            database,
            calendar_cache_path=self.calendar_cache_path,
            temporary_closure_path=self.temporary_closure_path,
        )

    def with_daily_source_snapshot_reader(
        self, reader: DailySourceSnapshotReadPort,
    ) -> RecommendationCurrentFundamentalProvider:
        """建立同來源設定的新 provider，將每日 port 鎖在單次決策。"""
        return RecommendationCurrentFundamentalProvider(
            db_file=self.db_file,
            output_root=self.output_root,
            monthly_source_root=self.monthly_source_root,
            valuation_provider_factory=self._valuation_provider_factory,
            official_calendar_factory=self._official_calendar_factory,
            calendar_cache_path=self.calendar_cache_path,
            temporary_closure_path=self.temporary_closure_path,
            daily_source_snapshot_reader=reader,
        )

    def load_pe(
        self,
        *,
        stock_code: str,
        cutoff_at: datetime,
        expected_market_date: date | str,
    ) -> tuple[CurrentObservedPEInput | None, tuple[str, ...]]:
        cutoff = _require_aware_utc(cutoff_at, "cutoff_at")
        code = _validate_stock_code(stock_code)
        expected_date = (
            expected_market_date
            if type(expected_market_date) is date
            else date.fromisoformat(str(expected_market_date)[:10])
        )
        expected_session, calendar_evidence = self._latest_official_session(cutoff)
        if expected_session is None:
            return None, (calendar_evidence,)
        if expected_date != expected_session:
            return None, (
                "current_market_data_date_not_latest_official_session:"
                f"{expected_date.isoformat()}:{expected_session.isoformat()}",
            )
        provider = self._valuation_provider_factory(
            self.output_root,
            clock=lambda: cutoff,
        )
        report = provider.read_current(
            code,
            cutoff.astimezone(_TAIPEI).date(),
            expected_market_date=expected_date,
        )
        if report.status != "ready":
            return None, tuple(str(item) for item in report.diagnostics) + (
                f"current_pe_freshness_not_verified:{report.status}",
            )
        pe_rows = tuple(
            observation
            for observation in report.observations
            if observation.stock_code == code and observation.metric_name == "pe"
        )
        if len(pe_rows) != 1:
            return None, tuple(str(item) for item in report.diagnostics) + (
                f"current_pe_unavailable:{report.status}",
            )
        observation = pe_rows[0]
        available_at = _require_aware_utc(observation.available_at, "available_at")
        if observation.as_of_date != expected_date:
            return None, ("current_pe_source_date_does_not_match_market_data_date",)
        if available_at > cutoff:
            return None, ("current_pe_capture_after_invocation_freeze",)
        raw_hash = str(observation.raw_response_sha256).removeprefix("sha256:")
        if not re.fullmatch(r"[0-9a-f]{64}", raw_hash):
            return None, ("current_pe_raw_response_hash_invalid",)
        if observation.formal_pit_eligible is not False:
            return None, ("current_pe_must_remain_outside_formal_pit",)
        return (
            CurrentObservedPEInput(
                stock_code=code,
                value=observation.value,
                as_of_date=observation.as_of_date,
                available_at=available_at,
                source=observation.source,
                source_version=observation.source_version,
                market=observation.market,
                raw_response_sha256=raw_hash,
                market_calendar_session_date=expected_session,
                market_calendar_reason_code=calendar_evidence,
            ),
            tuple(str(item) for item in report.diagnostics),
        )

    def _latest_official_session(self, cutoff_at: datetime) -> tuple[date | None, str]:
        """Resolve the project-cutoff session using the offline calendar.

        The reference date is shared with recommendation market preparation:
        04:30 America/Los_Angeles, DST-aware. The official calendar then
        establishes weekends, verified schedules, and local session evidence.
        Unknown calendar status fails closed.
        """

        from data_module.official_trading_calendar import OfficialTradingCalendarError

        try:
            calendar = self._official_calendar_factory(self.db_file)
            boundary = resolve_project_market_session_boundary(cutoff_at)
            reference_date = boundary.calendar_end_date
            current = reference_date
            while True:
                is_session, reason_code = calendar.is_official_trading_day(
                    current,
                    allow_online_probe=False,
                )
                if is_session is None:
                    return None, (
                        "official_trading_calendar_unresolved:"
                        f"{current.isoformat()}:{reason_code}"
                    )
                if is_session:
                    return current, str(reason_code)
                current -= timedelta(days=1)
        except (OfficialTradingCalendarError, OSError, sqlite3.Error, ValueError) as exc:
            return None, f"official_trading_calendar_unavailable:{type(exc).__name__}"

    def load_monthly_revenues(
        self,
        *,
        stock_code: str,
        cutoff_at: datetime,
        read_session_connection: sqlite3.Connection | None = None,
        pinned_daily_batch_id: str | None = None,
        pinned_daily_cohort: DailyMonthlyRevenueCohortPin | None = None,
    ) -> CurrentMonthlyRevenueReadResult:
        cutoff = _require_aware_utc(cutoff_at, "cutoff_at")
        code = _validate_stock_code(stock_code)
        if pinned_daily_cohort is not None:
            cohort_reader = self.daily_source_snapshot_reader
            if (
                not isinstance(pinned_daily_cohort, DailyMonthlyRevenueCohortPin)
                or pinned_daily_batch_id is not None
                or not isinstance(cohort_reader, DailyMonthlyRevenueCohortReader)
            ):
                return CurrentMonthlyRevenueReadResult(
                    "unavailable", code, cutoff, None,
                    diagnostics=("daily_source_cohort_pin_or_port_invalid",),
                )
            try:
                if cohort_reader.pin != pinned_daily_cohort:
                    raise ValueError("daily_source_cohort_does_not_match_reader_binding")
                cohort_reader.verify_cohort()
            except (OSError, TypeError, ValueError) as exc:
                return CurrentMonthlyRevenueReadResult(
                    "unavailable", code, cutoff, None,
                    diagnostics=(f"daily_source_cohort_rejected:{type(exc).__name__}:{exc}",),
                )
            if pinned_daily_cohort.available_hour > cutoff:
                return CurrentMonthlyRevenueReadResult(
                    "missing", code, cutoff, None,
                    diagnostics=("daily_source_cohort_not_available_at_cutoff",),
                )
        elif pinned_daily_batch_id is not None and isinstance(
            self.daily_source_snapshot_reader, DailyMonthlyRevenueCohortReader
        ):
            return CurrentMonthlyRevenueReadResult(
                "unavailable", code, cutoff, None,
                diagnostics=("daily_source_cohort_requires_complete_cohort_pin",),
            )
        if pinned_daily_batch_id is not None and (
            not isinstance(pinned_daily_batch_id, str) or not pinned_daily_batch_id.strip()
        ):
            return CurrentMonthlyRevenueReadResult(
                "unavailable",
                code,
                cutoff,
                None,
                diagnostics=("daily_source_snapshot_batch_id_invalid",),
            )
        if pinned_daily_batch_id is not None and self.daily_source_snapshot_reader is None:
            return CurrentMonthlyRevenueReadResult(
                "unavailable",
                code,
                cutoff,
                None,
                diagnostics=("daily_source_snapshot_port_missing_for_pinned_batch",),
            )
        if not self.db_file.is_file():
            return CurrentMonthlyRevenueReadResult(
                "unavailable",
                code,
                cutoff,
                None,
                diagnostics=("current_fundamental_database_missing",),
            )

        if read_session_connection is not None:
            self._validate_read_session_connection(read_session_connection)

        try:
            with self._monthly_read_connection(read_session_connection) as connection:
                rows = connection.execute(
                    f"SELECT * FROM {CURRENT_FUNDAMENTAL_TABLE} "
                    "WHERE stock_code=? AND kind='monthly_revenue' AND item_code='revenue' "
                    "ORDER BY period ASC, observed_at ASC, source_version ASC",
                    (code,),
                ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return CurrentMonthlyRevenueReadResult(
                    "unavailable",
                    code,
                    cutoff,
                    None,
                    diagnostics=("current_fundamental_observation_table_missing",),
                )
            return CurrentMonthlyRevenueReadResult(
                "unavailable",
                code,
                cutoff,
                None,
                diagnostics=(f"current_fundamental_read_error:{type(exc).__name__}",),
            )
        except (OSError, sqlite3.DatabaseError) as exc:
            return CurrentMonthlyRevenueReadResult(
                "unavailable",
                code,
                cutoff,
                None,
                diagnostics=(f"current_fundamental_read_error:{type(exc).__name__}",),
            )

        if not rows:
            return CurrentMonthlyRevenueReadResult(
                "missing", code, cutoff, None, diagnostics=("current_monthly_revenue_missing",)
            )
        diagnostic_source_row_count = len(rows)

        cutoff_date = cutoff.astimezone(_TAIPEI).date()
        diagnostics: list[str] = []
        snapshot_by_market: dict[str, DailySourceSnapshot | None] = {}
        opendata_amounts_by_market: dict[str, dict[str, Decimal] | None] = {}
        eligible_by_period: dict[str, list[CurrentObservedMonthlyRevenueInput]] = {}
        invalid_by_period: dict[str, list[tuple[datetime | None, str]]] = {}
        for row in rows:
            raw = dict(row)
            period = str(raw.get("period") or "").strip()
            period_end = _month_end(period)
            if period_end is None:
                diagnostics.append("current_monthly_revenue_invalid_period")
                continue
            if period_end > cutoff_date:
                continue
            try:
                observed_clock = _parse_aware_optional(raw.get("observed_at"))
            except ValueError:
                observed_clock = None
            try:
                source_clock = _parse_aware_optional(raw.get("source_available_at"))
            except ValueError:
                source_clock = None
            # Both clocks constrain an observation.  In particular, an old
            # local materialization must not make a source body captured after
            # this invocation appear available inside the frozen run.
            if (
                (observed_clock is not None and observed_clock > cutoff)
                or (source_clock is not None and source_clock > cutoff)
            ):
                continue
            pinned_snapshot: DailySourceSnapshot | None = None
            pinned_snapshot_record: DailySourceSnapshotRecord | None = None
            selected_batch_id = pinned_daily_batch_id
            if pinned_daily_cohort is not None:
                raw_market = str(raw.get("market") or "").strip()
                try:
                    selected_batch_id = pinned_daily_cohort.for_market(raw_market).batch_id
                except (TypeError, ValueError):
                    diagnostics.append(f"daily_source_cohort_market_not_in_pin:{raw_market}")
                    continue
            if selected_batch_id is not None:
                snapshot_reader = self.daily_source_snapshot_reader
                if snapshot_reader is None:
                    return CurrentMonthlyRevenueReadResult(
                        "unavailable",
                        code,
                        cutoff,
                        None,
                        diagnostics=("daily_source_snapshot_port_missing_for_pinned_batch",),
                        diagnostic_source_row_count=diagnostic_source_row_count,
                    )
                # 先以原始版本、雜湊與身份對 pinned manifest 篩選，避免批次外壞列污染同期間。
                raw_market = str(raw.get("market") or "").strip()
                derived_version = _DERIVED_MONTHLY_VERSION.fullmatch(
                    str(raw.get("source_version") or "")
                )
                if (
                    raw_market not in {"twse", "tpex"}
                    or derived_version is None
                    or derived_version.group("market") != raw_market
                    or derived_version.group("period") != period
                ):
                    diagnostics.append(
                        "daily_source_snapshot_record_not_in_pinned_batch:"
                        f"{period}:{raw.get('source_version') or ''}"
                    )
                    continue
                if raw_market not in snapshot_by_market:
                    raw_source = str(raw.get("source") or "")
                    if raw_source == MONTHLY_SNAPSHOT_SOURCE:
                        expected_source_id = DAILY_SOURCE_SNAPSHOT_SOURCE_ID
                        parser_version = MONTHLY_NORMALIZER_VERSION
                        source_schema_version = "mops-static-snapshot.v2"
                    elif raw_source == OPENAPI_MONTHLY_SOURCE_IDS.get(raw_market):
                        expected_source_id = raw_source
                        parser_version = OPENAPI_MONTHLY_NORMALIZER_VERSION
                        source_schema_version = "twse-tpex-openapi-monthly-revenue-14-fields.v1"
                    else:
                        diagnostics.append("monthly_source_profile_not_allowlisted")
                        continue
                    expected_scope = DailySourceUseScope(
                        dataset_id=DAILY_SOURCE_SNAPSHOT_DATASET_ID,
                        source_id=expected_source_id,
                        market=raw_market,
                        parser_version=parser_version,
                        source_schema_version=source_schema_version,
                        unit="TWD",
                        intended_use="recommendation_current_fundamental",
                    )
                    try:
                        candidate_snapshot = snapshot_reader.read_snapshot(
                            selected_batch_id,
                            expected_scope=expected_scope,
                        )
                    except ValueError as exc:
                        if str(exc) == "快照來源用途範圍與呼叫端預期不符":
                            snapshot_by_market[raw_market] = None
                            diagnostics.append(
                                "daily_source_snapshot_market_not_in_pinned_batch:"
                                f"{raw_market}"
                            )
                            continue
                        return CurrentMonthlyRevenueReadResult(
                            "unavailable",
                            code,
                            cutoff,
                            None,
                            diagnostics=(
                                "daily_source_snapshot_rejected:"
                                f"{type(exc).__name__}:{exc}",
                            ),
                            diagnostic_source_row_count=diagnostic_source_row_count,
                        )
                    except (OSError, TypeError) as exc:
                        return CurrentMonthlyRevenueReadResult(
                            "unavailable",
                            code,
                            cutoff,
                            None,
                            diagnostics=(
                                "daily_source_snapshot_rejected:"
                                f"{type(exc).__name__}:{exc}",
                            ),
                            diagnostic_source_row_count=diagnostic_source_row_count,
                        )
                    if not isinstance(candidate_snapshot, DailySourceSnapshot):
                        return CurrentMonthlyRevenueReadResult(
                            "unavailable",
                            code,
                            cutoff,
                            None,
                            diagnostics=(
                                "daily_source_snapshot_reader_result_invalid:"
                                f"{type(candidate_snapshot).__name__}",
                            ),
                            diagnostic_source_row_count=diagnostic_source_row_count,
                        )
                    if candidate_snapshot.batch_id != selected_batch_id:
                        return CurrentMonthlyRevenueReadResult(
                            "unavailable",
                            code,
                            cutoff,
                            None,
                            diagnostics=(
                                "daily_source_snapshot_batch_id_mismatch:"
                                f"expected={selected_batch_id}:"
                                f"actual={candidate_snapshot.batch_id}",
                            ),
                            diagnostic_source_row_count=diagnostic_source_row_count,
                        )
                    snapshot_by_market[raw_market] = candidate_snapshot
                pinned_snapshot = snapshot_by_market[raw_market]
                if pinned_snapshot is None:
                    continue
                if str(raw.get("source") or "") in OPENAPI_MONTHLY_SOURCE_IDS.values():
                    if raw_market not in opendata_amounts_by_market:
                        try:
                            from data_module.opendata_monthly_revenue import (
                                verify_openapi_snapshot_raw_batch,
                            )

                            opendata_amounts_by_market[raw_market] = (
                                verify_openapi_snapshot_raw_batch(pinned_snapshot)
                            )
                        except (TypeError, ValueError) as exc:
                            return CurrentMonthlyRevenueReadResult(
                                "unavailable",
                                code,
                                cutoff,
                                None,
                                diagnostics=(
                                    "daily_source_snapshot_raw_reparse_rejected:"
                                    f"{type(exc).__name__}:{exc}",
                                ),
                                diagnostic_source_row_count=diagnostic_source_row_count,
                            )
                try:
                    raw_version_parts = _monthly_source_version_parts(
                        derived_version.group("raw")
                    )
                except ValueError:
                    raw_version_parts = None
                if raw_version_parts is not None and raw_version_parts[:2] == (
                    raw_market,
                    period,
                ):
                    pinned_snapshot_record = pinned_snapshot.find_record(
                        stock_code=str(raw.get("stock_code") or ""),
                        market=raw_market,
                        period=period,
                        source_version=derived_version.group("raw"),
                        raw_source_sha256=raw_version_parts[2],
                        unit=str(raw.get("unit") or ""),
                    )
                if pinned_snapshot_record is None:
                    diagnostics.append(
                        "daily_source_snapshot_record_not_in_pinned_batch:"
                        f"{period}:{derived_version.group('raw')}"
                    )
                    continue
            try:
                normalized = normalize_current_observation(raw)
                if normalized.get("stock_code") != code:
                    raise ValueError("current monthly source returned a different stock")
                observation = _monthly_input_from_normalized(normalized, cutoff)
                if observation.source in OPENAPI_MONTHLY_SOURCE_IDS.values():
                    batch_amounts = opendata_amounts_by_market.get(observation.market)
                    source_amount = (
                        batch_amounts.get(observation.stock_code)
                        if batch_amounts is not None
                        else None
                    )
                    if source_amount is None or observation.revenue != source_amount:
                        diagnostics.append(
                            "daily_source_snapshot_normalized_value_differs_from_raw_response:"
                            f"{observation.period}:{observation.stock_code}"
                        )
                        continue
                if selected_batch_id is not None:
                    if (
                        pinned_snapshot is None
                        or pinned_snapshot_record is None
                        or observation.stock_code != pinned_snapshot_record.stock_code
                        or observation.market != pinned_snapshot_record.market
                        or observation.period != pinned_snapshot_record.period
                        or observation.raw_source_version
                        != pinned_snapshot_record.source_version
                        or observation.raw_source_sha256
                        != pinned_snapshot_record.raw_source_sha256
                        or observation.unit != pinned_snapshot_record.unit
                    ):
                        diagnostics.append(
                            "daily_source_snapshot_normalized_identity_mismatch:"
                            f"{period}"
                        )
                        continue
                    if not pinned_snapshot.is_available_by(pinned_snapshot_record, cutoff):
                        diagnostics.append(
                            "daily_source_snapshot_not_available_at_cutoff:"
                            f"{observation.period}"
                        )
                        continue
                    available_hour, availability_basis = pinned_snapshot.availability_for(
                        pinned_snapshot_record
                    )
                    if pinned_daily_cohort is not None:
                        available_hour = max(available_hour, pinned_daily_cohort.available_hour)
                    observation = replace(
                        observation,
                        available_at=max(observation.available_at, available_hour),
                        availability_basis=availability_basis,
                        availability_snapshot_batch_id=pinned_snapshot.batch_id,
                        availability_first_persisted_at=pinned_snapshot.first_persisted_at,
                    )
            except (InvalidOperation, TypeError, ValueError) as exc:
                # Unknown-clock invalid rows remain blockers unless a
                # hash-bound verified revision supersedes them below.  When a
                # source capture clock exists it defines source revision order;
                # only rows without one fall back to local materialization.
                revision_clock = source_clock or observed_clock
                invalid_by_period.setdefault(period, []).append(
                    (revision_clock, str(raw.get("source_version") or ""))
                )
                diagnostics.append(
                    f"current_monthly_revenue_unverified_revision_preserved:"
                    f"{period}:{type(exc).__name__}"
                )
                continue
            eligible_by_period.setdefault(period, []).append(observation)

        blocked_periods: set[str] = set()
        for period, invalid_versions in invalid_by_period.items():
            valid_versions = eligible_by_period.get(period, [])
            latest_valid_clock = max(
                (_monthly_revision_clock(item) for item in valid_versions),
                default=None,
            )
            for invalid_clock, invalid_source_version in invalid_versions:
                bound_verified = any(
                    item.raw_source_version == invalid_source_version
                    for item in valid_versions
                )
                superseded_by_later_verified_observation = (
                    invalid_clock is not None
                    and latest_valid_clock is not None
                    and latest_valid_clock > invalid_clock
                )
                if bound_verified or superseded_by_later_verified_observation:
                    diagnostics.append(
                        f"current_monthly_revenue_unverified_revision_superseded:"
                        f"{period}"
                    )
                else:
                    blocked_periods.add(period)
                    diagnostics.append(
                        f"current_monthly_revenue_unverified_revision_blocks_period:"
                        f"{period}"
                    )

        all_periods = set(eligible_by_period) | blocked_periods
        if not all_periods:
            return CurrentMonthlyRevenueReadResult(
                "missing",
                code,
                cutoff,
                None,
                diagnostics=tuple(diagnostics) or ("no_verified_current_monthly_revenue",),
                diagnostic_source_row_count=diagnostic_source_row_count,
            )
        latest_period = max(all_periods)
        if latest_period in blocked_periods:
            return CurrentMonthlyRevenueReadResult(
                "invalid",
                code,
                cutoff,
                latest_period,
                diagnostics=tuple(diagnostics),
                blocked_periods=tuple(sorted(blocked_periods)),
                diagnostic_source_row_count=diagnostic_source_row_count,
            )

        selected: list[CurrentObservedMonthlyRevenueInput] = []
        for period, versions in sorted(eligible_by_period.items()):
            if period in blocked_periods:
                continue
            latest_at = max(_monthly_revision_clock(item) for item in versions)
            latest = [
                item for item in versions if _monthly_revision_clock(item) == latest_at
            ]
            values = {item.revenue for item in latest}
            if len(values) != 1:
                diagnostics.append(f"current_monthly_revenue_ambiguous_revision:{period}")
                if period == latest_period:
                    return CurrentMonthlyRevenueReadResult(
                        "ambiguous",
                        code,
                        cutoff,
                        latest_period,
                        diagnostics=tuple(diagnostics),
                        diagnostic_source_row_count=diagnostic_source_row_count,
                    )
                continue
            selected.append(min(latest, key=lambda item: item.source_version))

        selected_by_period = {item.period: item for item in selected}
        if latest_period not in selected_by_period:
            return CurrentMonthlyRevenueReadResult(
                "invalid",
                code,
                cutoff,
                latest_period,
                diagnostics=tuple(diagnostics) or ("latest_current_monthly_revenue_unavailable",),
                diagnostic_source_row_count=diagnostic_source_row_count,
            )
        latest_observation = selected_by_period[latest_period]
        (
            comparison_baseline,
            comparison_diagnostics,
            diagnostic_comparator_row_count,
        ) = self._read_materialized_yoy_baseline(
            latest_observation,
            cutoff,
            connection=read_session_connection,
        )
        comparison_csv_hash: str | None = None
        if comparison_baseline is None and comparison_diagnostics == (
            "current_monthly_revenue_yoy_comparator_missing",
        ):
            # Backward-compatible read-only fallback for already captured
            # natural sources whose DB snapshot predates the comparator item.
            # New materializations persist the typed comparator row above.
            (
                comparison_baseline,
                comparison_csv_hash,
                raw_pair_diagnostics,
            ) = self._same_report_yoy_baseline(
                latest_observation,
                use_instance_cache=read_session_connection is None,
            )
            comparison_diagnostics = (
                (
                    "current_monthly_revenue_yoy_comparator_materialization_missing;"
                    "exact_raw_pair_fallback_verified",
                )
                if comparison_baseline is not None
                else (*comparison_diagnostics, *raw_pair_diagnostics)
            )
        diagnostics.extend(comparison_diagnostics)
        if comparison_baseline is not None:
            diagnostics.append(
                "current_monthly_revenue_same_report_yoy_baseline_verified:"
                f"{comparison_baseline.period}"
            )
        return CurrentMonthlyRevenueReadResult(
            "ready",
            code,
            cutoff,
            latest_period,
            tuple(selected_by_period[key] for key in sorted(selected_by_period)),
            tuple(diagnostics),
            tuple(sorted(blocked_periods)),
            comparison_baseline,
            comparison_csv_hash,
            diagnostic_source_row_count,
            diagnostic_comparator_row_count,
        )

    def _read_materialized_yoy_baseline(
        self,
        current: CurrentObservedMonthlyRevenueInput,
        cutoff: datetime,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> tuple[CurrentObservedMonthlyRevenueInput | None, tuple[str, ...], int]:
        year_text, month_text = current.period.split("-")
        prior_period = f"{int(year_text) - 1:04d}-{month_text}"
        try:
            with self._monthly_read_connection(connection) as read_connection:
                rows = read_connection.execute(
                    f"SELECT * FROM {CURRENT_FUNDAMENTAL_TABLE} "
                    "WHERE stock_code=? AND kind='monthly_revenue' "
                    "AND period=? AND item_code=?",
                    (current.stock_code, prior_period, MONTHLY_YOY_COMPARATOR_ITEM_CODE),
                ).fetchall()
        except (OSError, sqlite3.DatabaseError) as exc:
            return (
                None,
                (f"current_monthly_revenue_yoy_comparator_read_error:{type(exc).__name__}",),
                0,
            )

        diagnostic_comparator_row_count = len(rows)

        eligible: list[CurrentObservedMonthlyRevenueInput] = []
        diagnostics: list[str] = []
        for db_row in rows:
            row = dict(db_row)
            try:
                if (
                    row.get("kind") != "monthly_revenue"
                    or row.get("item_code") != MONTHLY_YOY_COMPARATOR_ITEM_CODE
                    or row.get("source") != MONTHLY_SNAPSHOT_SOURCE
                    or row.get("market") != current.market
                    or row.get("unit") != "TWD"
                    or row.get("period_basis") != "monthly_flow"
                    or row.get("basis_verified") != 1
                    or row.get("aggregate_feature_eligible") != 0
                    or row.get("formal_pit_eligible") not in (None, False, 0)
                ):
                    raise ValueError("comparator row metadata is not verified")
                source_version = str(row.get("source_version") or "")
                if not _is_monthly_yoy_comparator_source_version(
                    source_version,
                    market=current.market,
                    comparator_period=prior_period,
                    stock_code=current.stock_code,
                    value=str(row.get("value") or ""),
                    unit="TWD",
                    source_available_at=str(row.get("source_available_at") or ""),
                ):
                    raise ValueError("comparator source version does not verify")
                source_period_match = re.search(r":from:(\d{4}-\d{2}):raw:", source_version)
                raw_source_match = re.search(r":raw:(.+):derived:sha256:[0-9a-f]{64}$", source_version)
                if (
                    source_period_match is None
                    or source_period_match.group(1) != current.period
                    or raw_source_match is None
                    or raw_source_match.group(1) != current.raw_source_version
                ):
                    raise ValueError("comparator is not bound to the selected current report")
                observed_at = _parse_aware_required(row.get("observed_at"), "observed_at")
                source_available_at = _parse_aware_optional(row.get("source_available_at"))
                if source_available_at != current.source_available_at:
                    raise ValueError("comparator and current row source clocks differ")
                available_at = max(observed_at, source_available_at or observed_at)
                if current.availability_snapshot_batch_id is not None:
                    # 同份 pinned 報表的前期比較也必須等成功批次的小時 gate。
                    available_at = max(available_at, current.available_at)
                if available_at > cutoff or observed_at > cutoff:
                    diagnostics.append(
                        "current_monthly_revenue_yoy_comparator_observed_after_invocation_freeze"
                    )
                    continue
                value = Decimal(str(row.get("value") or ""))
                if not value.is_finite() or value <= 0:
                    raise ValueError("comparator value is not positive finite TWD")
                eligible.append(
                    CurrentObservedMonthlyRevenueInput(
                        stock_code=current.stock_code,
                        period=prior_period,
                        revenue=value,
                        observed_at=observed_at,
                        source_available_at=source_available_at,
                        available_at=available_at,
                        source=current.source,
                        source_version=source_version,
                        market=current.market,
                        raw_source_version=current.raw_source_version,
                        raw_source_sha256=current.raw_source_sha256,
                        unit="TWD",
                        period_basis="monthly_flow",
                        basis_verified=True,
                        aggregate_feature_eligible=False,
                        formal_pit_eligible=False,
                        availability_basis=current.availability_basis,
                        input_role="same_report_prior_year_comparison_baseline",
                        parent_report_period=current.period,
                        availability_snapshot_batch_id=(
                            current.availability_snapshot_batch_id
                        ),
                        availability_first_persisted_at=(
                            current.availability_first_persisted_at
                        ),
                    )
                )
            except (InvalidOperation, TypeError, ValueError) as exc:
                diagnostics.append(
                    f"current_monthly_revenue_yoy_comparator_invalid:{type(exc).__name__}"
                )
        if len(eligible) > 1:
            if len({row.revenue for row in eligible}) != 1:
                return (
                    None,
                    (*diagnostics, "current_monthly_revenue_yoy_comparator_ambiguous"),
                    diagnostic_comparator_row_count,
                )
            eligible.sort(key=lambda row: row.source_version)
        if eligible:
            return eligible[-1], tuple(diagnostics), diagnostic_comparator_row_count
        if diagnostics:
            return None, tuple(diagnostics), diagnostic_comparator_row_count
        return (
            None,
            ("current_monthly_revenue_yoy_comparator_missing",),
            diagnostic_comparator_row_count,
        )

    @contextmanager
    def _monthly_read_connection(
        self,
        read_session_connection: sqlite3.Connection | None,
    ) -> Iterator[sqlite3.Connection]:
        if read_session_connection is not None:
            yield read_session_connection
            return
        uri = f"{self.db_file.as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.row_factory = sqlite3.Row
            yield connection

    def _validate_read_session_connection(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        if not connection.in_transaction:
            raise ValueError("read_session_connection must hold an active read transaction")
        try:
            query_only = int(connection.execute("PRAGMA query_only").fetchone()[0])
            database_rows = connection.execute("PRAGMA database_list").fetchall()
        except sqlite3.Error as exc:
            raise ValueError("read_session_connection cannot be verified") from exc
        main_path = next(
            (
                Path(str(row[2])).resolve(strict=False)
                for row in database_rows
                if row[1] == "main"
            ),
            None,
        )
        if query_only != 1:
            raise ValueError("read_session_connection must be query_only")
        if main_path != self.db_file.resolve(strict=False):
            raise ValueError("read_session_connection database does not match provider")

    def _same_report_yoy_baseline(
        self,
        current: CurrentObservedMonthlyRevenueInput,
        *,
        use_instance_cache: bool = True,
    ) -> tuple[
        CurrentObservedMonthlyRevenueInput | None,
        str | None,
        tuple[str, ...],
    ]:
        """Read the prior-year comparator from the exact current MOPS response.

        The comparator is available only in the natural current-observation lane.
        Its date remains the local observation date; this function never treats
        the report's prior-year comparison column as a historical publication.
        """

        parts = _monthly_source_version_parts(current.raw_source_version)
        if (
            parts is None
            or parts[:2] != (current.market, current.period)
            or parts[2] != current.raw_source_sha256
        ):
            return None, None, ("current_monthly_revenue_comparison_raw_identity_invalid",)

        cache_key = (current.market, current.period, current.raw_source_version)
        cached = (
            self._verified_monthly_capture_cache.get(cache_key)
            if use_instance_cache
            else None
        )
        if cached is None:
            cached = self._read_verified_monthly_capture(
                market=current.market,
                period=current.period,
                raw_source_version=current.raw_source_version,
                expected_raw_sha256=current.raw_source_sha256,
            )
            if use_instance_cache:
                self._verified_monthly_capture_cache[cache_key] = cached
        parsed_by_code, snapshot_csv_sha256, diagnostics = cached
        if diagnostics:
            return None, None, diagnostics
        row = parsed_by_code.get(current.stock_code)
        if row is None:
            return None, None, ("current_monthly_revenue_comparison_stock_missing",)

        try:
            current_raw = Decimal(row["current_month_revenue"])
            previous_year_raw = Decimal(row["previous_year_month_revenue"])
        except (InvalidOperation, KeyError) as exc:
            return None, None, (
                f"current_monthly_revenue_comparison_value_invalid:{type(exc).__name__}",
            )
        if (
            not current_raw.is_finite()
            or not previous_year_raw.is_finite()
            or current_raw <= 0
            or previous_year_raw <= 0
        ):
            return None, None, ("current_monthly_revenue_comparison_value_nonpositive",)
        if current_raw * Decimal(1000) != current.revenue:
            return None, None, ("current_monthly_revenue_comparison_current_value_mismatch",)

        year_text, month_text = current.period.split("-")
        prior_period = f"{int(year_text) - 1:04d}-{int(month_text):02d}"
        baseline_value = previous_year_raw * Decimal(1000)
        comparator_version = _derived_monthly_yoy_comparator_version(
            current.raw_source_version,
            stock_code=current.stock_code,
            source_period=current.period,
            comparator_period=prior_period,
            value=format(baseline_value, "f"),
            unit="TWD",
            source_available_at=_monthly_source_available_at(
                current.raw_source_version,
                market=current.market,
                period=current.period,
            ),
        )
        comparator_version = (
            f"{comparator_version}:verified-csv-sha256:{snapshot_csv_sha256}"
        )
        return (
            CurrentObservedMonthlyRevenueInput(
                stock_code=current.stock_code,
                period=prior_period,
                revenue=baseline_value,
                observed_at=current.observed_at,
                source_available_at=current.source_available_at,
                available_at=current.available_at,
                source=current.source,
                source_version=comparator_version,
                market=current.market,
                raw_source_version=current.raw_source_version,
                raw_source_sha256=current.raw_source_sha256,
                unit="TWD",
                period_basis="monthly_flow",
                basis_verified=True,
                aggregate_feature_eligible=False,
                formal_pit_eligible=False,
                availability_basis=current.availability_basis,
                input_role="same_report_prior_year_comparison_baseline",
                parent_report_period=current.period,
                availability_snapshot_batch_id=current.availability_snapshot_batch_id,
                availability_first_persisted_at=current.availability_first_persisted_at,
            ),
            snapshot_csv_sha256,
            (),
        )

    def _read_verified_monthly_capture(
        self,
        *,
        market: str,
        period: str,
        raw_source_version: str,
        expected_raw_sha256: str,
    ) -> tuple[dict[str, dict[str, str]], str, tuple[str, ...]]:
        capture_root = self.monthly_source_root / "monthly_revenue_mops_snapshots"
        html_path = capture_root / "raw_html" / f"{market}_{period}.html"
        if not html_path.is_file():
            return {}, "", ("current_monthly_revenue_comparison_raw_html_missing",)
        try:
            html = html_path.read_bytes().decode("utf-8-sig")
        except (OSError, UnicodeError) as exc:
            return {}, "", (
                f"current_monthly_revenue_comparison_raw_html_unreadable:{type(exc).__name__}",
            )
        actual_raw_hash = sha256(html.encode("utf-8")).hexdigest()
        if actual_raw_hash != expected_raw_sha256:
            return {}, "", ("current_monthly_revenue_comparison_raw_html_hash_mismatch",)

        from data_module.monthly_revenue_snapshot_harvester import (
            MOPS_SNAPSHOT_COLUMNS,
            parse_mops_monthly_revenue_snapshot_html,
        )

        # The source's prior-year comparison value shares the same table unit
        # and row identity as current_month_revenue. Parse the official HTML
        # again and verify the persisted CSV row by row before using it.
        parsed_rows: dict[str, dict[str, str]] = {}
        try:
            csv_paths = sorted(capture_root.glob("mops_monthly_revenue_snapshot_*.csv"))
            matching_csvs: list[tuple[Path, dict[str, dict[str, str]], str]] = []
            for csv_path in csv_paths:
                with csv_path.open(encoding="utf-8-sig", newline="") as stream:
                    actual_rows = list(csv.DictReader(stream))
                if not actual_rows:
                    continue
                candidate_version = str(actual_rows[0].get("source_version") or "")
                candidate_parts = _monthly_source_version_parts(candidate_version)
                if (
                    candidate_version != raw_source_version
                    or candidate_parts is None
                    or candidate_parts[:2] != (market, period)
                ):
                    continue
                fetched_at = str(actual_rows[0].get("fetched_at") or "")
                parsed_list, parse_diagnostics = parse_mops_monthly_revenue_snapshot_html(
                    html,
                    market=market,
                    period=period,
                    fetched_at=fetched_at,
                    source_version=raw_source_version,
                )
                if parse_diagnostics or not parsed_list:
                    continue
                expected_by_code = {
                    str(row["stock_code"]): row for row in parsed_list
                }
                actual_by_code = {
                    str(row.get("stock_code") or ""): row
                    for row in actual_rows
                    if row.get("source_version") == raw_source_version
                }
                if (
                    len(actual_by_code) != len(actual_rows)
                    or set(actual_by_code) != set(expected_by_code)
                ):
                    continue
                row_match = all(
                    all(
                        str(actual_by_code[code].get(column) or "")
                        == str(expected_by_code[code].get(column) or "")
                        for column in MOPS_SNAPSHOT_COLUMNS
                    )
                    for code in expected_by_code
                )
                if not row_match:
                    continue
                csv_sha256 = sha256(csv_path.read_bytes()).hexdigest()
                matching_csvs.append((csv_path, expected_by_code, csv_sha256))
        except (OSError, UnicodeError, csv.Error, TypeError, ValueError) as exc:
            return {}, "", (
                f"current_monthly_revenue_comparison_csv_invalid:{type(exc).__name__}",
            )

        if not matching_csvs:
            return {}, "", ("current_monthly_revenue_comparison_csv_raw_pair_missing",)
        distinct_payloads = {
            tuple(
                (code, row["current_month_revenue"], row["previous_year_month_revenue"])
                for code, row in sorted(rows.items())
            )
            for _, rows, _ in matching_csvs
        }
        if len(distinct_payloads) != 1:
            return {}, "", ("current_monthly_revenue_comparison_csv_pair_ambiguous",)
        selected_path, parsed_rows, selected_hash = matching_csvs[-1]
        if not selected_path.is_file():
            return {}, "", ("current_monthly_revenue_comparison_csv_missing",)
        return parsed_rows, selected_hash, ()


def _monthly_input_from_normalized(
    row: Mapping[str, str], cutoff: datetime
) -> CurrentObservedMonthlyRevenueInput:
    if row.get("kind") != "monthly_revenue" or row.get("item_code") != "revenue":
        raise ValueError("unexpected current fundamental identity")
    source = str(row.get("source") or "")
    market = row.get("market", "")
    if source != MONTHLY_SNAPSHOT_SOURCE and source != OPENAPI_MONTHLY_SOURCE_IDS.get(market):
        raise ValueError("monthly source is outside the exact MOPS/OpenData profile")
    if row.get("unit") != "TWD":
        raise ValueError("monthly current value is not normalized to TWD")
    if row.get("period_basis") != "monthly_flow" or row.get("basis_verified") != "1":
        raise ValueError("monthly current observation basis is not verified monthly flow")
    if row.get("aggregate_feature_eligible") != "0":
        raise ValueError("monthly revenue must remain a single-period flow")
    if market not in {"twse", "tpex"}:
        raise ValueError("monthly current source market is invalid")
    period = str(row.get("period") or "")
    raw_version = str(row.get("source_version") or "")
    match = _DERIVED_MONTHLY_VERSION.fullmatch(raw_version)
    if (
        match is None
        or match.group("market") != market
        or match.group("period") != period
    ):
        raise ValueError("monthly version does not bind market and period")
    expected_normalizer = (
        OPENAPI_MONTHLY_NORMALIZER_VERSION
        if source in OPENAPI_MONTHLY_SOURCE_IDS.values()
        else MONTHLY_NORMALIZER_VERSION
    )
    if match.group("normalizer") != expected_normalizer:
        raise ValueError("monthly source and normalizer profiles do not match")
    raw_source_version = match.group("raw")
    raw_parts = _monthly_source_version_parts(raw_source_version)
    if raw_parts is None or raw_parts[:2] != (market, period):
        raise ValueError("monthly raw version does not bind market and period")
    if row.get("source_available_at"):
        availability_basis = "official_body_capture"
        source_available_at = _parse_aware_required(
            row.get("source_available_at"), "source_available_at"
        )
        if source_available_at > cutoff:
            raise ValueError("monthly official source capture is after invocation freeze")
    else:
        # New normalization may verify the raw body/rows/hash while the old
        # harvester timestamp is known only to be a batch start.  The live
        # eligibility clock is then the actual local materialization below.
        availability_basis = "local_verified_observation"
        source_available_at = None

    observed_at = _parse_aware_required(row.get("observed_at"), "observed_at")
    if observed_at > cutoff:
        raise ValueError("monthly local observation is after invocation freeze")
    value = Decimal(str(row.get("value") or ""))
    if not value.is_finite():
        raise ValueError("monthly current revenue must be finite")
    period_end = _month_end(period)
    if period_end is None or period_end > observed_at.astimezone(_TAIPEI).date():
        raise ValueError("monthly period is invalid or ends after local observation")
    return CurrentObservedMonthlyRevenueInput(
        stock_code=str(row.get("stock_code") or ""),
        period=period,
        revenue=value,
        observed_at=observed_at,
        source_available_at=source_available_at,
        available_at=max(observed_at, source_available_at or observed_at),
        source=str(row.get("source") or ""),
        source_version=raw_version,
        market=market,
        raw_source_version=raw_source_version,
        raw_source_sha256=raw_parts[2],
        availability_basis=availability_basis,
    )


def _validate_stock_code(stock_code: str) -> str:
    code = str(stock_code).strip()
    if not re.fullmatch(r"\d{4,6}", code):
        raise ValueError("stock_code must contain 4 to 6 digits")
    return code


def _monthly_revision_clock(
    record: CurrentObservedMonthlyRevenueInput,
) -> datetime:
    """Return source capture time, falling back to local observation time.

    ``available_at`` is the earliest safe use-time for the row, not a source
    revision ordering key: a replayed normalization can have a new local
    materialization clock while still binding an older official body.
    """

    return record.source_available_at or record.observed_at


def _require_aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_aware_optional(value: object) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    return _parse_aware_required(value, "timestamp")


def _parse_aware_required(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be an aware ISO timestamp")
    return parsed.astimezone(timezone.utc)


def _month_end(period: str) -> date | None:
    if not re.fullmatch(r"\d{4}-\d{2}", str(period)):
        return None
    year, month = (int(part) for part in str(period).split("-"))
    if year < 1 or not 1 <= month <= 12:
        return None
    from calendar import monthrange

    return date(year, month, monthrange(year, month)[1])


__all__ = (
    "CurrentMonthlyRevenueReadResult",
    "CurrentObservedMonthlyRevenueInput",
    "CurrentObservedPEInput",
    "RecommendationCurrentFundamentalProvider",
)
