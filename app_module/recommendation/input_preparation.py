"""Application-owned cutoff and market-frame preparation for recommendation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping, Protocol, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from app_module.recommendation_market_data_provider import (
    DefaultRecommendationMarketDataProvider,
)
from app_module.recommendation_market_frame import normalize_market_frame
from app_module.recommendation_portfolio_dates import parse_stock_dates
from app_module.market_session_cadence import MarketSessionAssessment, MarketSessionCadence
from data_module.recommendation_input_providers import (
    HistoricalRecommendationMarketFrameProvider,
    PITRecommendationMembershipProvider,
    RecommendationFundamentalInputProvider,
    ValuationPEObservation,
)
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    CurrentObservedPEInput,
    RecommendationCurrentFundamentalProvider,
)
from data_module.fundamental_data import MonthlyRevenueRecord
from data_module.fundamental_sqlite_provider import FundamentalSQLiteProvider
from data_module.pit_sector_membership_reader import PITMembershipReadResult
from data_module.pit_sector_membership_reader import PITSectorMembershipReader
from app_module.recommendation.current_market_status_preflight import (
    CurrentMarketStatusPreflight,
    CurrentMarketStatusPreflightResult,
)

_TAIPEI = ZoneInfo("Asia/Taipei")


class RecommendationMarketSessionBlocked(ValueError):
    """Natural market preparation could not verify the official session."""


@dataclass(frozen=True, slots=True)
class RecommendationCutoffResolution:
    cutoff: str | None
    temporal_mode: str
    cutoff_selection: str
    cutoff_policy: str


@dataclass(frozen=True, slots=True)
class PreparedRecommendationMarket:
    """按既有 PIT 可得日規則篩選後的行情 frame 與來源 identity。"""

    frame: pd.DataFrame
    stock_column: str
    decision_cutoff: str
    source_id: str
    market_data_fingerprint: str
    data_date: str
    expected_market_date: str | None = None
    market_calendar_status: str | None = None
    market_calendar_reason_code: str | None = None


class _MarketProvider(Protocol):
    def __call__(self) -> pd.DataFrame: ...


class _HistoricalMarketProvider(Protocol):
    def __call__(self, cutoff: str | None) -> pd.DataFrame: ...


class RecommendationInputSession:
    """單次推薦呼叫使用的明確 source/read session。

    Session 建立不會讀取任何資料。市場、PIT 與基本面都只會在原流程
    要使用該來源時讀取，保留 candidate loop 的逐檔查詢與早退順序。
    """

    def __init__(
        self,
        *,
        config: Any,
        market_data_provider: _MarketProvider,
        historical_market_provider: _HistoricalMarketProvider,
        pit_membership_provider: PITRecommendationMembershipProvider,
        fundamental_input_provider: RecommendationFundamentalInputProvider,
        current_fundamental_provider: RecommendationCurrentFundamentalProvider | None = None,
        current_market_status_source_root: Path | None = None,
        market_session_cadence: MarketSessionCadence | None = None,
        invocation_frozen_at: datetime | None = None,
    ) -> None:
        self.config = config
        self.market_data_provider = market_data_provider
        self.historical_market_provider = historical_market_provider
        self.pit_membership_provider = pit_membership_provider
        self.fundamental_input_provider = fundamental_input_provider
        self.current_fundamental_provider = current_fundamental_provider
        self.current_market_status_source_root = (
            current_market_status_source_root.resolve()
            if current_market_status_source_root is not None
            else None
        )
        self._current_market_status_preflight: CurrentMarketStatusPreflight | None = None
        self._current_market_status_scope = False
        if invocation_frozen_at is not None and (
            invocation_frozen_at.tzinfo is None
            or invocation_frozen_at.utcoffset() is None
        ):
            raise ValueError("recommendation invocation clock must be timezone-aware")
        self.invocation_frozen_at = invocation_frozen_at
        self.market_session_cadence = market_session_cadence
        self.expected_market_date: str | None = None
        self.market_calendar_status: str | None = None
        self._loaded_natural_market_frame: pd.DataFrame | None = None

    def resolve_cutoff(
        self,
        *,
        runtime_config: Mapping[str, Any],
        as_of_date: str | date | None,
        historical_research: bool,
        select_latest_available_cutoff: bool,
    ) -> RecommendationCutoffResolution:
        resolution = resolve_recommendation_cutoff(
            config=runtime_config,
            as_of_date=as_of_date,
            historical_research=historical_research,
            select_latest_available_cutoff=select_latest_available_cutoff,
        )
        self._current_market_status_scope = (
            as_of_date is None
            and not historical_research
            and not select_latest_available_cutoff
            and resolution.cutoff is None
        )
        return resolution

    def validate_cutoff_request(
        self,
        *,
        runtime_config: Mapping[str, Any],
        as_of_date: str | date | None,
        historical_research: bool,
        select_latest_available_cutoff: bool,
    ) -> None:
        validate_recommendation_cutoff_request(
            config=runtime_config,
            as_of_date=as_of_date,
            historical_research=historical_research,
            select_latest_available_cutoff=select_latest_available_cutoff,
        )

    def prepare_market(
        self,
        *,
        cutoff: str | None,
        universe: Sequence[str] | None = None,
        decision_date: str | None = None,
        source_frame: pd.DataFrame | None = None,
    ) -> PreparedRecommendationMarket:
        market_data_cutoff: str | None = None
        session_assessment: MarketSessionAssessment | None = None
        effective_decision_date = decision_date
        if (
            source_frame is None
            and cutoff is None
            and self._loaded_natural_market_frame is not None
        ):
            source_frame = self._loaded_natural_market_frame.copy(deep=True)
        if cutoff is None and self.market_session_cadence is not None:
            probe_frame = (
                source_frame.copy(deep=True)
                if source_frame is not None
                else self.market_data_provider()
            )
            if source_frame is not None and probe_frame.empty:
                # An explicitly supplied empty frame is still the caller's input;
                # preserve the early-return path without inventing a session date.
                source_frame = probe_frame
            else:
                market_data_cutoff, session_assessment = self._natural_market_boundary(
                    probe_frame,
                    decision_date=effective_decision_date,
                )
                if source_frame is None:
                    source_frame = (
                        self.load_market_frame(cutoff=market_data_cutoff)
                        if type(self.market_data_provider)
                        is DefaultRecommendationMarketDataProvider
                        else probe_frame
                    )
        if source_frame is None:
            source_frame = self.load_market_frame(cutoff=cutoff)
        prepared = prepare_recommendation_market(
            source_frame=source_frame,
            cutoff=cutoff,
            decision_date=effective_decision_date,
            market_data_cutoff=market_data_cutoff,
            availability_date_cutoff=self._availability_date_cutoff(
                cutoff=cutoff,
                decision_date=effective_decision_date,
            ),
            market_data_provider=self.market_data_provider,
            universe=universe,
        )
        return self._bind_market_session(
            prepared,
            session_assessment,
            decision_date=effective_decision_date,
        )

    def load_market_frame(self, *, cutoff: str | None) -> pd.DataFrame:
        """讀取一次來源行情；呼叫者可在讀取完成後凍結決策時鐘再準備。"""

        frame = load_recommendation_market_frame(
            config=self.config,
            market_data_provider=self.market_data_provider,
            historical_market_provider=self.historical_market_provider,
            cutoff=cutoff,
        )
        if cutoff is None:
            self._loaded_natural_market_frame = frame.copy(deep=True)
        return frame

    def load_market_frame_with_minimum_bars(
        self, *, cutoff: str | None, minimum_bars: int
    ) -> pd.DataFrame:
        frame = load_recommendation_market_frame(
            config=self.config,
            market_data_provider=self.market_data_provider,
            historical_market_provider=self.historical_market_provider,
            cutoff=cutoff,
            minimum_bars=minimum_bars,
        )
        if cutoff is None:
            self._loaded_natural_market_frame = frame.copy(deep=True)
        return frame

    def prepare_market_with_minimum_bars(
        self,
        *,
        cutoff: str | None,
        minimum_bars: int,
        universe: Sequence[str] | None = None,
        decision_date: str | None = None,
        source_frame: pd.DataFrame | None = None,
    ) -> PreparedRecommendationMarket:
        market_data_cutoff: str | None = None
        session_assessment: MarketSessionAssessment | None = None
        effective_decision_date = decision_date
        if (
            source_frame is None
            and cutoff is None
            and self._loaded_natural_market_frame is not None
        ):
            source_frame = self._loaded_natural_market_frame.copy(deep=True)
        if cutoff is None and self.market_session_cadence is not None:
            probe_frame = (
                source_frame.copy(deep=True)
                if source_frame is not None
                else self.market_data_provider()
            )
            if source_frame is not None and probe_frame.empty:
                source_frame = probe_frame
            else:
                market_data_cutoff, session_assessment = self._natural_market_boundary(
                    probe_frame,
                    decision_date=effective_decision_date,
                )
                if source_frame is not None:
                    # A caller-supplied frame is the frozen input for this invocation.
                    # Do not replace it with a second historical read merely because
                    # the live provider subclasses the default provider.
                    source_frame = probe_frame
                elif type(self.market_data_provider) is DefaultRecommendationMarketDataProvider:
                    source_frame = self.load_market_frame_with_minimum_bars(
                        cutoff=market_data_cutoff,
                        minimum_bars=minimum_bars,
                    )
                else:
                    source_frame = probe_frame
        if source_frame is None:
            source_frame = self.load_market_frame_with_minimum_bars(
                cutoff=cutoff,
                minimum_bars=minimum_bars,
            )
        prepared = prepare_recommendation_market(
            source_frame=source_frame,
            cutoff=cutoff,
            decision_date=effective_decision_date,
            market_data_cutoff=market_data_cutoff,
            availability_date_cutoff=self._availability_date_cutoff(
                cutoff=cutoff,
                decision_date=effective_decision_date,
            ),
            market_data_provider=self.market_data_provider,
            universe=universe,
        )
        return self._bind_market_session(
            prepared,
            session_assessment,
            decision_date=effective_decision_date,
        )

    def _availability_date_cutoff(
        self,
        *,
        cutoff: str | None,
        decision_date: str | None,
    ) -> str | None:
        """Keep natural availability time independent of event/source dates."""

        if cutoff is not None:
            return cutoff
        if self.invocation_frozen_at is not None:
            return self._invocation_decision_date().isoformat()
        return decision_date

    def _invocation_decision_date(self) -> date:
        frozen_at = self.invocation_frozen_at
        if frozen_at is None:
            raise RecommendationMarketSessionBlocked(
                "natural_market_invocation_clock_missing"
            )
        return frozen_at.astimezone(_TAIPEI).date()

    def _session_decision_date(self, decision_date: str | None) -> date:
        if decision_date is None:
            return self._invocation_decision_date()
        return date.fromisoformat(_normalize_decision_date(decision_date))

    def _natural_market_boundary(
        self,
        source_frame: pd.DataFrame,
        *,
        decision_date: str | None,
    ) -> tuple[str, MarketSessionAssessment]:
        cadence = self.market_session_cadence
        if cadence is None:
            raise RecommendationMarketSessionBlocked(
                "natural_market_official_calendar_unavailable"
            )
        boundary_decision_date = self._session_decision_date(decision_date)
        normalized, _stock_column = normalize_market_frame(source_frame)
        if normalized.empty or "日期" not in normalized.columns:
            raise RecommendationMarketSessionBlocked(
                "natural_market_actual_session_date_missing"
            )
        parsed_dates = parse_stock_dates(normalized["日期"])
        eligible_dates = parsed_dates[
            parsed_dates.notna()
            & (parsed_dates.dt.date <= boundary_decision_date)
        ]
        if eligible_dates.empty:
            raise RecommendationMarketSessionBlocked(
                "natural_market_actual_session_date_missing"
            )
        actual_date = eligible_dates.max().date()
        assessment = cadence.assess(boundary_decision_date, actual_date)
        if assessment.expected_date is None or assessment.status == "unverified":
            blockers = assessment.metadata.get("blockers", ())
            blocker_text = ",".join(str(item) for item in blockers) or "expected_session_missing"
            raise RecommendationMarketSessionBlocked(
                f"natural_market_official_calendar_unverified:{blocker_text}"
            )
        expected_date = assessment.expected_date.isoformat()
        self.expected_market_date = expected_date
        return expected_date, assessment

    def _bind_market_session(
        self,
        prepared: PreparedRecommendationMarket,
        initial_assessment: MarketSessionAssessment | None,
        *,
        decision_date: str | None,
    ) -> PreparedRecommendationMarket:
        cadence = self.market_session_cadence
        expected = self.expected_market_date
        if cadence is None or initial_assessment is None or expected is None:
            return prepared
        actual_date = (
            date.fromisoformat(prepared.data_date) if prepared.data_date else None
        )
        if actual_date is None:
            status = "stale"
            reason_code = "market_quote_date_missing"
        else:
            assessment = cadence.assess(
                self._session_decision_date(decision_date), actual_date
            )
            if assessment.expected_date is None or assessment.status == "unverified":
                blockers = assessment.metadata.get("blockers", ())
                blocker_text = ",".join(str(item) for item in blockers) or "expected_session_missing"
                raise RecommendationMarketSessionBlocked(
                    f"natural_market_official_calendar_unverified:{blocker_text}"
                )
            if assessment.expected_date.isoformat() != expected:
                raise RecommendationMarketSessionBlocked(
                    "natural_market_expected_session_changed_within_invocation"
                )
            status = assessment.status
            reason_code = (
                "quote_matches_expected_official_session"
                if status == "current"
                else "quote_date_before_expected_official_session"
                if status == "stale"
                else "quote_date_after_expected_official_session"
            )
        self.market_calendar_status = status
        return replace(
            prepared,
            expected_market_date=expected,
            market_calendar_status=status,
            market_calendar_reason_code=reason_code,
        )

    def read_pit_membership(
        self, cutoff: str, runtime_config: Mapping[str, Any]
    ) -> PITMembershipReadResult | None:
        return self.pit_membership_provider.read(cutoff, runtime_config)

    def load_pe(
        self, *, stock_code: str, decision_date: str
    ) -> ValuationPEObservation | None:
        return self.fundamental_input_provider.load_pe(
            stock_code=stock_code,
            decision_date=decision_date,
        )

    def load_monthly_revenues(
        self, *, stock_code: str, decision_date: date
    ) -> tuple[MonthlyRevenueRecord, ...]:
        return self.fundamental_input_provider.load_monthly_revenues(
            stock_code=stock_code,
            decision_date=decision_date,
        )

    def load_current_pe(
        self,
        *,
        stock_code: str,
        cutoff_at: datetime,
        expected_market_date: date | str,
    ) -> tuple[CurrentObservedPEInput | None, tuple[str, ...]]:
        provider = self.current_fundamental_provider
        if provider is None:
            return None, ("current_fundamental_provider_unavailable",)
        expected = self.expected_market_date
        provided = (
            expected_market_date.isoformat()
            if isinstance(expected_market_date, date)
            else str(expected_market_date)
        )
        if expected is None or provided != expected:
            return None, ("current_pe_expected_market_date_not_session_verified",)
        if self.market_calendar_status != "current":
            return None, ("current_pe_market_data_session_not_current",)
        return provider.load_pe(
            stock_code=stock_code,
            cutoff_at=cutoff_at,
            expected_market_date=expected,
        )

    def load_current_monthly_revenues(
        self,
        *,
        stock_code: str,
        cutoff_at: datetime,
    ) -> CurrentMonthlyRevenueReadResult:
        provider = self.current_fundamental_provider
        if provider is None:
            return CurrentMonthlyRevenueReadResult(
                "unavailable",
                stock_code,
                cutoff_at,
                None,
                diagnostics=("current_fundamental_provider_unavailable",),
            )
        return provider.load_monthly_revenues(
            stock_code=stock_code,
            cutoff_at=cutoff_at,
        )

    def get_current_market_status(
        self,
        stock_code: str,
        *,
        cutoff_at: datetime,
        decision_date: date,
    ) -> CurrentMarketStatusPreflightResult:
        """Read one verified current-only status under this invocation's clock.

        Historical, replay, and select-latest callers are intentionally denied
        access to this current-only source.  For live calls, the status source
        uses the exact same configured canonical root as current PE/MOPS input,
        even when recommendation artifacts are written to a shadow root.
        """

        if not self._current_market_status_scope:
            return CurrentMarketStatusPreflightResult(
                str(stock_code), "unavailable", "current_market_status_not_live_scope"
            )
        frozen_at = self.invocation_frozen_at
        if frozen_at is None or frozen_at.tzinfo is None or frozen_at.utcoffset() is None:
            return CurrentMarketStatusPreflightResult(
                str(stock_code), "unavailable", "current_market_status_invocation_clock_missing"
            )
        if (
            cutoff_at.tzinfo is None
            or cutoff_at.utcoffset() is None
            or cutoff_at.astimezone(timezone.utc) != frozen_at.astimezone(timezone.utc)
        ):
            return CurrentMarketStatusPreflightResult(
                str(stock_code), "unavailable", "current_market_status_invocation_clock_mismatch"
            )
        source_root = self.current_market_status_source_root
        if source_root is None:
            return CurrentMarketStatusPreflightResult(
                str(stock_code), "unavailable", "current_market_status_source_root_unavailable"
            )
        if self._current_market_status_preflight is None:
            self._current_market_status_preflight = CurrentMarketStatusPreflight(source_root)
        return self._current_market_status_preflight.get(
            stock_code,
            cutoff_at=frozen_at,
            decision_date=decision_date,
        )


class RecommendationInputPreparer:
    """Composition-created application facade for recommendation source reads."""

    def __init__(
        self,
        *,
        market_data_provider: _MarketProvider,
        historical_market_provider: _HistoricalMarketProvider,
        pit_membership_provider: PITRecommendationMembershipProvider,
        fundamental_input_provider: RecommendationFundamentalInputProvider,
        current_fundamental_provider: RecommendationCurrentFundamentalProvider | None = None,
        current_market_status_source_root: Path | None = None,
        market_session_cadence_factory: Callable[..., MarketSessionCadence] | None = None,
    ) -> None:
        self.market_data_provider = market_data_provider
        self.historical_market_provider = historical_market_provider
        self.pit_membership_provider = pit_membership_provider
        self.fundamental_input_provider = fundamental_input_provider
        self.current_fundamental_provider = current_fundamental_provider
        self.current_market_status_source_root = current_market_status_source_root
        self.market_session_cadence_factory = market_session_cadence_factory

    def begin(
        self,
        config: Any,
        *,
        market_data_provider: _MarketProvider | None = None,
        invocation_frozen_at: datetime | None = None,
    ) -> RecommendationInputSession:
        """建立 invocation-local wrapper，刻意不執行來源 I/O。"""

        frozen_at = invocation_frozen_at or datetime.now(timezone.utc)
        if frozen_at.tzinfo is None or frozen_at.utcoffset() is None:
            raise ValueError("recommendation invocation clock must be timezone-aware")
        cadence_factory = self.market_session_cadence_factory
        cadence = (
            cadence_factory(config, clock=lambda: frozen_at)
            if cadence_factory is not None
            else None
        )

        return RecommendationInputSession(
            config=config,
            market_data_provider=(
                market_data_provider
                if market_data_provider is not None
                else self.market_data_provider
            ),
            historical_market_provider=self.historical_market_provider,
            pit_membership_provider=self.pit_membership_provider,
            fundamental_input_provider=self.fundamental_input_provider,
            current_fundamental_provider=self.current_fundamental_provider,
            current_market_status_source_root=self.current_market_status_source_root,
            market_session_cadence=cadence,
            invocation_frozen_at=frozen_at,
        )


def build_default_recommendation_input_preparer(
    config: Any,
    *,
    market_data_provider: _MarketProvider | None = None,
    pit_membership_reader: PITSectorMembershipReader | None = None,
    market_session_cadence_factory: Callable[..., MarketSessionCadence] | None = None,
    current_fundamental_source_root: Path | None = None,
) -> RecommendationInputPreparer:
    """由 application composition 建立來源 providers。

    ``current_fundamental_source_root`` 將官方即時估值與 MOPS 月營收
    原始來源位置，和 ``config.output_root`` 的 recommendation 產物位置分開。
    未指定時保留一般 UI/呼叫端以 ``config.output_root`` 作為 canonical root。
    """

    active_market_provider = (
        market_data_provider
        if market_data_provider is not None
        else DefaultRecommendationMarketDataProvider(config)
    )
    raw_db_file = getattr(config, "db_file", None)
    if isinstance(raw_db_file, (str, Path)):
        db_file = Path(raw_db_file)
    else:
        # 非完整設定通常只出現在隔離測試；使用唯一、未建立的 TEMP path，
        # PE 仍以 read-only URI fail closed，不觸碰 repository/formal data。
        db_file = Path(tempfile.gettempdir()) / f"recommendation-missing-{uuid4().hex}.db"

    def monthly_revenue_provider_factory() -> FundamentalSQLiteProvider | None:
        if not db_file.is_file():
            return None
        raw_availability_file = getattr(
            config, "monthly_revenue_availability_file", None
        )
        availability_file = (
            Path(raw_availability_file)
            if isinstance(raw_availability_file, (str, Path))
            else None
        )
        return FundamentalSQLiteProvider(
            db_file,
            monthly_revenue_availability_file=availability_file,
        )

    configured_market_scope = getattr(config, "pit_market_scope", None)
    raw_output_root = getattr(config, "output_root", None)
    raw_current_fundamental_source_root = (
        current_fundamental_source_root
        if current_fundamental_source_root is not None
        else raw_output_root
    )
    current_fundamental_provider = (
        RecommendationCurrentFundamentalProvider(
            db_file=db_file,
            output_root=Path(raw_current_fundamental_source_root),
            monthly_source_root=Path(raw_current_fundamental_source_root),
        )
        if isinstance(raw_current_fundamental_source_root, (str, Path))
        else None
    )
    current_market_status_source_root = (
        Path(raw_current_fundamental_source_root)
        if isinstance(raw_current_fundamental_source_root, (str, Path))
        else None
    )
    return RecommendationInputPreparer(
        market_data_provider=active_market_provider,
        historical_market_provider=HistoricalRecommendationMarketFrameProvider(
            config
        ),
        pit_membership_provider=PITRecommendationMembershipProvider(
            pit_membership_reader,
            configured_market_scope=configured_market_scope,
        ),
        fundamental_input_provider=RecommendationFundamentalInputProvider(
            db_file,
            monthly_revenue_provider_factory=monthly_revenue_provider_factory,
        ),
        current_fundamental_provider=current_fundamental_provider,
        current_market_status_source_root=current_market_status_source_root,
        market_session_cadence_factory=(
            market_session_cadence_factory or MarketSessionCadence.for_config
        ),
    )


def resolve_recommendation_cutoff(
    *,
    config: Mapping[str, Any],
    as_of_date: str | date | None,
    historical_research: bool,
    select_latest_available_cutoff: bool,
) -> RecommendationCutoffResolution:
    """保留推薦 caller/historical/latest cutoff 的既有相容契約。"""

    validate_recommendation_cutoff_request(
        config=config,
        as_of_date=as_of_date,
        historical_research=historical_research,
        select_latest_available_cutoff=select_latest_available_cutoff,
    )
    config_cutoff = config.get("as_of_date")
    has_config_cutoff = config_cutoff not in (None, "")

    cutoff_input = (
        as_of_date
        if historical_research
        else None
        if select_latest_available_cutoff
        else as_of_date
        if as_of_date is not None
        else config_cutoff
    )
    cutoff = (
        _normalize_decision_date(cutoff_input)
        if cutoff_input is not None
        else None
    )
    temporal_mode = (
        "historical_research_not_as_if_available"
        if historical_research
        else "natural_producer_clock"
        if select_latest_available_cutoff or not (as_of_date is not None or has_config_cutoff)
        else "explicit_cutoff_not_natural"
    )
    cutoff_selection = (
        "explicit_historical_cutoff"
        if historical_research
        else "producer_selected_latest_available_cutoff"
        if select_latest_available_cutoff or not (as_of_date is not None or has_config_cutoff)
        else "caller_requested_cutoff"
    )
    cutoff_policy = (
        "explicit_historical_research"
        if historical_research
        else "source_latest_available_exact"
        if cutoff_selection == "producer_selected_latest_available_cutoff"
        else "caller_explicit_cutoff_not_natural"
    )
    return RecommendationCutoffResolution(
        cutoff=cutoff,
        temporal_mode=temporal_mode,
        cutoff_selection=cutoff_selection,
        cutoff_policy=cutoff_policy,
    )


def validate_recommendation_cutoff_request(
    *,
    config: Mapping[str, Any],
    as_of_date: str | date | None,
    historical_research: bool,
    select_latest_available_cutoff: bool,
) -> None:
    """先驗證 request tuple；不解析日期，讓 caller 保留舊錯誤順序。"""

    if not isinstance(historical_research, bool):
        raise ValueError("historical_research 必須是布林值")
    if not isinstance(select_latest_available_cutoff, bool):
        raise ValueError("select_latest_available_cutoff 必須是布林值")
    config_cutoff = config.get("as_of_date")
    has_config_cutoff = config_cutoff not in (None, "")
    if historical_research and select_latest_available_cutoff:
        raise ValueError(
            "historical_research 不得與 select_latest_available_cutoff 同時啟用"
        )
    if historical_research and as_of_date is None:
        raise ValueError("historical_research 必須明示 as_of_date")
    if select_latest_available_cutoff and (
        as_of_date is not None or has_config_cutoff
    ):
        raise ValueError("select_latest_available_cutoff 不得搭配 caller cutoff")


def load_recommendation_market_frame(
    *,
    config: Any,
    market_data_provider: Callable[[], pd.DataFrame],
    historical_market_provider: _HistoricalMarketProvider,
    cutoff: str | None,
    minimum_bars: int | None = None,
) -> pd.DataFrame:
    """可見地保留 default provider 的歷史／即時來源分流。"""

    if isinstance(market_data_provider, DefaultRecommendationMarketDataProvider):
        should_use_history = cutoff or getattr(config, "use_sqlite", False)
        is_builtin_provider = type(market_data_provider) is DefaultRecommendationMarketDataProvider
        if minimum_bars is not None and is_builtin_provider:
            load_with_minimum_bars = getattr(
                historical_market_provider, "load_with_minimum_bars", None
            )
            if callable(load_with_minimum_bars):
                return load_with_minimum_bars(cutoff, minimum_bars)
        if should_use_history:
            return historical_market_provider(cutoff)
    return market_data_provider()


def minimum_recommendation_history_rows(config: Mapping[str, Any]) -> int:
    """依啟用指標的實際週期決定所需交易 bar 數，並設 60 bar 下限。"""

    from analysis_module.technical_analysis.indicator_parameter_registry import (
        IndicatorParameterRegistry,
    )

    schema_version = IndicatorParameterRegistry.get_config_schema_version(
        dict(config)
    )
    technical = config.get("technical", {})
    if not isinstance(technical, Mapping):
        return 60
    required_rows = [60]

    def section_is_enabled(section_name: str) -> Mapping[str, Any] | None:
        section = technical.get(section_name)
        if not isinstance(section, Mapping):
            return None
        enabled = section.get("enabled", schema_version >= 1)
        if enabled is not True:
            return None
        return section

    def enabled_params(
        section: Mapping[str, Any], indicator_name: str
    ) -> dict[str, Any] | None:
        raw = section.get(indicator_name)
        if raw is None:
            enabled = schema_version < 1
            params: dict[str, Any] = {}
        elif isinstance(raw, Mapping):
            enabled = raw.get("enabled", True) is True
            params = {key: value for key, value in raw.items() if key != "enabled"}
        elif raw is True:
            enabled = True
            params = {}
        else:
            enabled = False
            params = {}
        if not enabled:
            return None
        return IndicatorParameterRegistry.validate_and_sanitize(
            indicator_name,
            params,
            dict(config),
        )

    momentum = section_is_enabled("momentum")
    if momentum is not None:
        rsi = enabled_params(momentum, "rsi")
        if rsi is not None:
            required_rows.append(int(rsi["timeperiod"]) + 1)
        macd = enabled_params(momentum, "macd")
        if macd is not None:
            required_rows.append(
                int(macd["slowperiod"]) + int(macd["signalperiod"])
            )
        kd = enabled_params(momentum, "kd")
        if kd is not None:
            required_rows.append(
                int(kd["fastk_period"])
                + int(kd["slowk_period"])
                + int(kd["slowd_period"])
            )

    trend = section_is_enabled("trend")
    if trend is not None:
        adx = enabled_params(trend, "adx")
        if adx is not None:
            required_rows.append(2 * int(adx["timeperiod"]))
        tsf = enabled_params(trend, "tsf")
        if tsf is not None:
            required_rows.append(int(tsf["timeperiod"]))
        ma = enabled_params(trend, "ma")
        if ma is not None:
            required_rows.append(max(int(value) for value in ma["windows"]))

    volatility = section_is_enabled("volatility")
    if volatility is not None:
        bollinger = enabled_params(volatility, "bollinger")
        if bollinger is not None:
            required_rows.append(int(bollinger["timeperiod"]))
        sar = enabled_params(volatility, "sar")
        if sar is not None:
            required_rows.append(2)
        atr = enabled_params(volatility, "atr")
        if atr is not None:
            required_rows.append(int(atr["timeperiod"]) + 1)

    return max(required_rows)


def prepare_recommendation_market(
    *,
    source_frame: pd.DataFrame,
    cutoff: str | None,
    market_data_provider: object,
    universe: Sequence[str] | None = None,
    decision_date: str | None = None,
    market_data_cutoff: str | None = None,
    availability_date_cutoff: str | None = None,
) -> PreparedRecommendationMarket:
    """依明示 cutoff/決策日篩選，同時保留來源 frame 的真實資料日。"""

    frame, stock_column = normalize_market_frame(source_frame)
    if frame.empty:
        # 舊 `_decision_frame` 在 normalize 後立即早退；空來源可合法缺少
        # 日期欄，也保留原 frame 欄位/index，不做 date filter、astype 或 reset。
        fingerprint = hashlib.sha256(
            json.dumps([], ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return PreparedRecommendationMarket(
            frame=frame,
            stock_column=stock_column,
            decision_cutoff=cutoff or decision_date or "",
            source_id=type(market_data_provider).__name__,
            market_data_fingerprint=fingerprint,
            data_date="",
        )
    if not frame.empty:
        frame["日期"] = parse_stock_dates(frame["日期"])
        frame = frame[frame["日期"].notna()].copy()
    source_data_cutoff = (
        frame["日期"].max().strftime("%Y-%m-%d") if not frame.empty else ""
    )
    requested_cutoff = cutoff or decision_date
    frame_cutoff = market_data_cutoff or requested_cutoff or source_data_cutoff
    availability_cutoff = (
        availability_date_cutoff
        or cutoff
        or decision_date
        or frame_cutoff
    )
    if frame_cutoff:
        limit = pd.Timestamp(frame_cutoff)
        frame = frame[frame["日期"] <= limit].copy()
        if "available_date" in frame:
            available = parse_stock_dates(frame["available_date"])
            availability_limit = pd.Timestamp(availability_cutoff)
            frame = frame[
                available.notna() & (available <= availability_limit)
            ].copy()
            frame["available_date"] = available.loc[frame.index]
            frame = frame.sort_values("available_date", kind="stable").drop_duplicates(
                [stock_column, "日期"], keep="last"
            )
    frame[stock_column] = frame[stock_column].astype(str)
    frame = frame.reset_index(drop=True)
    if universe is not None and not frame.empty:
        frame = frame[frame[stock_column].isin({str(code) for code in universe})].copy()
    canonical = (
        frame.sort_values([stock_column, "日期"], kind="stable")
        if not frame.empty
        else frame
    )
    fingerprint_payload = (
        canonical.reindex(sorted(canonical.columns), axis=1)
        .astype(str)
        .to_dict("records")
    )
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    data_date = (
        canonical["日期"].max().strftime("%Y-%m-%d") if not canonical.empty else ""
    )
    decision_cutoff = requested_cutoff or data_date
    return PreparedRecommendationMarket(
        frame=frame,
        stock_column=stock_column,
        decision_cutoff=decision_cutoff,
        source_id=type(market_data_provider).__name__,
        market_data_fingerprint=fingerprint,
        data_date=data_date,
    )


def _normalize_decision_date(raw_date: Any) -> str:
    if isinstance(raw_date, (pd.Timestamp, datetime, date)):
        if pd.isna(raw_date):
            raise ValueError("decision date is missing")
        return raw_date.strftime("%Y-%m-%d")
    date_text = str(raw_date).strip()
    if not date_text:
        raise ValueError("decision date is empty")
    normalized_text = date_text.replace("-", "").replace("/", "")
    if len(normalized_text) != 8 or not normalized_text.isdigit():
        raise ValueError(f"unsupported decision date: {date_text}")
    return datetime.strptime(normalized_text, "%Y%m%d").date().isoformat()


__all__ = (
    "PreparedRecommendationMarket",
    "RecommendationCutoffResolution",
    "RecommendationInputPreparer",
    "RecommendationInputSession",
    "build_default_recommendation_input_preparer",
    "load_recommendation_market_frame",
    "minimum_recommendation_history_rows",
    "prepare_recommendation_market",
    "resolve_recommendation_cutoff",
    "validate_recommendation_cutoff_request",
)
