"""Application-owned cutoff and market-frame preparation for recommendation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping, Protocol, Sequence
from uuid import uuid4

import pandas as pd

from app_module.recommendation_market_data_provider import (
    DefaultRecommendationMarketDataProvider,
)
from app_module.recommendation_market_frame import normalize_market_frame
from app_module.recommendation_portfolio_dates import parse_stock_dates
from data_module.recommendation_input_providers import (
    HistoricalRecommendationMarketFrameProvider,
    PITRecommendationMembershipProvider,
    RecommendationFundamentalInputProvider,
    ValuationPEObservation,
)
from data_module.fundamental_data import MonthlyRevenueRecord
from data_module.fundamental_sqlite_provider import FundamentalSQLiteProvider
from data_module.pit_sector_membership_reader import PITMembershipReadResult
from data_module.pit_sector_membership_reader import PITSectorMembershipReader


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
    ) -> None:
        self.config = config
        self.market_data_provider = market_data_provider
        self.historical_market_provider = historical_market_provider
        self.pit_membership_provider = pit_membership_provider
        self.fundamental_input_provider = fundamental_input_provider

    def resolve_cutoff(
        self,
        *,
        runtime_config: Mapping[str, Any],
        as_of_date: str | date | None,
        historical_research: bool,
        select_latest_available_cutoff: bool,
    ) -> RecommendationCutoffResolution:
        return resolve_recommendation_cutoff(
            config=runtime_config,
            as_of_date=as_of_date,
            historical_research=historical_research,
            select_latest_available_cutoff=select_latest_available_cutoff,
        )

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
        if source_frame is None:
            source_frame = self.load_market_frame(cutoff=cutoff)
        return prepare_recommendation_market(
            source_frame=source_frame,
            cutoff=cutoff,
            decision_date=decision_date,
            market_data_provider=self.market_data_provider,
            universe=universe,
        )

    def load_market_frame(self, *, cutoff: str | None) -> pd.DataFrame:
        """讀取一次來源行情；呼叫者可在讀取完成後凍結決策時鐘再準備。"""

        return load_recommendation_market_frame(
            config=self.config,
            market_data_provider=self.market_data_provider,
            historical_market_provider=self.historical_market_provider,
            cutoff=cutoff,
        )

    def load_market_frame_with_minimum_bars(
        self, *, cutoff: str | None, minimum_bars: int
    ) -> pd.DataFrame:
        return load_recommendation_market_frame(
            config=self.config,
            market_data_provider=self.market_data_provider,
            historical_market_provider=self.historical_market_provider,
            cutoff=cutoff,
            minimum_bars=minimum_bars,
        )

    def prepare_market_with_minimum_bars(
        self,
        *,
        cutoff: str | None,
        minimum_bars: int,
        universe: Sequence[str] | None = None,
        decision_date: str | None = None,
        source_frame: pd.DataFrame | None = None,
    ) -> PreparedRecommendationMarket:
        if source_frame is None:
            source_frame = self.load_market_frame_with_minimum_bars(
                cutoff=cutoff,
                minimum_bars=minimum_bars,
            )
        return prepare_recommendation_market(
            source_frame=source_frame,
            cutoff=cutoff,
            decision_date=decision_date,
            market_data_provider=self.market_data_provider,
            universe=universe,
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


class RecommendationInputPreparer:
    """Composition-created application facade for recommendation source reads."""

    def __init__(
        self,
        *,
        market_data_provider: _MarketProvider,
        historical_market_provider: _HistoricalMarketProvider,
        pit_membership_provider: PITRecommendationMembershipProvider,
        fundamental_input_provider: RecommendationFundamentalInputProvider,
    ) -> None:
        self.market_data_provider = market_data_provider
        self.historical_market_provider = historical_market_provider
        self.pit_membership_provider = pit_membership_provider
        self.fundamental_input_provider = fundamental_input_provider

    def begin(
        self,
        config: Any,
        *,
        market_data_provider: _MarketProvider | None = None,
    ) -> RecommendationInputSession:
        """建立 invocation-local wrapper，刻意不執行來源 I/O。"""

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
        )


def build_default_recommendation_input_preparer(
    config: Any,
    *,
    market_data_provider: _MarketProvider | None = None,
    pit_membership_reader: PITSectorMembershipReader | None = None,
) -> RecommendationInputPreparer:
    """由 application composition 明示建立 recommendation data providers。"""

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
    decision_cutoff = cutoff or decision_date or (
        frame["日期"].max().strftime("%Y-%m-%d") if not frame.empty else ""
    )
    if decision_cutoff:
        limit = pd.Timestamp(decision_cutoff)
        frame = frame[frame["日期"] <= limit].copy()
        if "available_date" in frame:
            available = parse_stock_dates(frame["available_date"])
            frame = frame[available.notna() & (available <= limit)].copy()
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
