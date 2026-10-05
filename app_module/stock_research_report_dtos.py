"""單一個股研究報告的唯讀資料契約。

這個模組只描述研究投影，不負責評分、下單或更新資料。數值欄位在
application boundary 保留 ``Decimal``／整數 bp；只有 UI 圖表在明確的
visualisation boundary 才能轉成 ``float``。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, cast

from app_module.advice_dtos import PortfolioAdviceDTO, RecommendationAdviceDTO
from app_module.watchlist_analysis_service import WatchlistAnalysisDTO


STOCK_RESEARCH_REPORT_SCHEMA_VERSION = "stock-research-report.v1"


class ReportQuality(str, Enum):
    OBSERVED = "observed"
    ESTIMATED = "estimated"
    DEGRADED = "degraded"
    STALE = "stale"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"


class ReportFreshness(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class ReportSectionStatus(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    STALE = "stale"
    MISSING = "missing"
    ERROR = "error"


@dataclass(frozen=True)
class StockReportSourceDTO:
    """一個實際被查詢的來源及其時間／品質邊界。"""

    source_id: str
    source_label: str
    status: str = ReportSectionStatus.AVAILABLE.value
    quality: str = ReportQuality.OBSERVED.value
    data_as_of: str = ""
    available_at: str = ""
    freshness: str = ReportFreshness.UNKNOWN.value
    version: str = ""
    row_count: int = 0
    limitations: tuple[str, ...] = ()
    # 來源 cadence 與 probe 對應的 expected period；不以查詢日猜測來源新鮮度。
    frequency: str = ""
    expected_period: str = ""
    freshness_reason: str = ""
    coverage_status: str = ""
    observed_at: str = ""
    candidate_only: bool = False
    current_observed_only: bool = False
    historical_pit_eligible: bool | None = None

    def __post_init__(self) -> None:
        if not self.source_id or not self.source_label:
            raise ValueError("source_id and source_label are required")
        if isinstance(self.row_count, bool) or self.row_count < 0:
            raise ValueError("row_count must be a non-negative integer")


@dataclass(frozen=True)
class StockReportSectionDTO:
    """畫面 section 的可用性摘要，不把缺資料偽裝成零值。"""

    section_id: str
    label: str
    status: str
    summary: str = ""
    data_as_of: str = ""
    available_at: str = ""
    freshness: str = ReportFreshness.UNKNOWN.value
    source_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class StockMetricDTO:
    key: str
    label: str
    value: Decimal | None = None
    value_text: str = ""
    unit: str = ""
    data_as_of: str = ""
    available_at: str = ""
    source_id: str = ""
    quality: str = ReportQuality.OBSERVED.value


@dataclass(frozen=True)
class StockPricePointDTO:
    data_date: str
    open_price: Decimal | None = None
    high_price: Decimal | None = None
    low_price: Decimal | None = None
    close_price: Decimal | None = None
    volume: int | None = None
    turnover: Decimal | None = None
    change: Decimal | None = None
    available_at: str = ""
    source_id: str = ""
    source_snapshot_hash: str = ""
    quality: str = ReportQuality.OBSERVED.value


@dataclass(frozen=True)
class StockTechnicalSnapshotDTO:
    data_date: str
    indicators: tuple[StockMetricDTO, ...] = ()
    available_at: str = ""
    source_id: str = ""
    quality: str = ReportQuality.OBSERVED.value
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class StockFundamentalObservationDTO:
    kind: str
    label: str
    metric_name: str = ""
    market: str = ""
    period: str = ""
    as_of_date: str = ""
    announced_date: str = ""
    available_at: str = ""
    observed_at: str = ""
    value: Decimal | None = None
    value_text: str = ""
    unit: str = ""
    source_id: str = ""
    source_version: str = ""
    source_snapshot_hash: str = ""
    quality: str = ReportQuality.OBSERVED.value
    period_basis: str = "unknown"
    basis_verified: bool = False
    aggregate_feature_eligible: bool = False
    formal_pit_eligible: bool = False


@dataclass(frozen=True)
class StockFlowObservationDTO:
    data_date: str
    branch_name: str
    buy_shares: int | None = None
    sell_shares: int | None = None
    net_shares: int | None = None
    buy_amount_thousand: Decimal | None = None
    sell_amount_thousand: Decimal | None = None
    net_amount_thousand: Decimal | None = None
    trade_type: str = ""
    available_at: str = ""
    source_id: str = ""
    quality: str = ReportQuality.OBSERVED.value


@dataclass(frozen=True)
class StockOutcomeDTO:
    window_days: int
    outcome_status: str = ""
    forward_return_bp: int | None = None
    benchmark_excess_bp: int | None = None
    data_quality: str = ""
    calculated_at: str = ""


@dataclass(frozen=True)
class StockEvidenceEventDTO:
    event_id: str
    event_date: str
    decision_date: str
    event_type: str
    event_family: str = ""
    source_type: str = ""
    source_id: str = ""
    source_version: str = ""
    data_quality: str = ""
    as_of_date: str = ""
    available_at: str = ""
    reasons: tuple[str, ...] = ()
    why_not_reasons: tuple[str, ...] = ()
    risk_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    score_bp: int | None = None
    outcomes: tuple[StockOutcomeDTO, ...] = ()


@dataclass(frozen=True)
class StockPositionSnapshotDTO:
    is_holding: bool = False
    position_id: str = ""
    portfolio_id: str = ""
    position_as_of: str = ""
    quote_data_date: str = ""
    quote_available_at: str = ""
    quantity: Decimal | None = None
    average_cost: Decimal | None = None
    invested_amount: Decimal | None = None
    current_price: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    unrealized_pnl_pct: Decimal | None = None
    exposure_bp: int | None = None
    source_type: str = ""
    source_id: str = ""
    source_snapshot_hash: str = ""
    quote_source_snapshot_hash: str = ""
    opened_at: str = ""
    last_trade_date: str = ""
    health_status: str = ""
    health_label: str = ""
    health_reasons: tuple[str, ...] = ()
    health_source_trace: tuple[str, ...] = ()
    exit_status: str = "unavailable"
    exit_reasons: tuple[str, ...] = ()
    exit_source_id: str = ""
    exit_available_at: str = ""
    exit_research_only: bool = True
    exit_auto_action_allowed: bool = False
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class StockTradingRestrictionDTO:
    restriction_type: str
    restriction_state: str
    effective_from: str = ""
    effective_to: str = ""
    resumed_on: str = ""
    published_date: str = ""
    notice_reference: str = ""
    source_id: str = ""
    evidence_type: str = ""
    observed_at: str = ""
    source_data_dates: tuple[str, ...] = ()
    market: str = ""
    name: str = ""
    details: str = ""
    raw_sha256: str = ""
    source_url: str = ""


@dataclass(frozen=True)
class StockMarketStatusEvidenceDTO:
    evidence_type: str
    source_id: str
    observed_at: str = ""
    published_date: str = ""
    effective_from: str = ""
    effective_to: str = ""
    resumed_on: str = ""
    notice_reference: str = ""
    source_data_dates: tuple[str, ...] = ()
    raw_sha256: str = ""
    source_url: str = ""
    market: str = ""
    name: str = ""
    details: str = ""
    restriction_type: str = ""
    restriction_state: str = ""


@dataclass(frozen=True)
class StockMarketStatusSnapshotDTO:
    status: str = "unknown"
    listing_status: str = "unknown"
    market: str = ""
    name: str = ""
    trading_restrictions: tuple[StockTradingRestrictionDTO, ...] = ()
    status_evidence: tuple[StockMarketStatusEvidenceDTO, ...] = ()
    source_ids: tuple[str, ...] = ()
    source_data_dates: tuple[str, ...] = ()
    observed_at: str = ""
    source_warnings: tuple[str, ...] = ()
    partial_failure: bool = False
    scope: str = "current_only"
    pit_eligible: bool = False
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class StockMLSnapshotDTO:
    """ML 只有在外部 read provider 提供合格結果時才填入版本欄位。"""

    status: str = ReportQuality.UNAVAILABLE.value
    model_version: str = ""
    dataset_version: str = ""
    inference_at: str = ""
    available_at: str = ""
    model_available_at: str = ""
    research_or_formal: str = ""
    explanations: tuple[str, ...] = ()
    source_id: str = ""
    run_id: str = ""
    scope_mode: str = ""
    event_date: str = ""
    model_manifest_sha256: str = ""
    model_bundle_sha256: str = ""
    source_snapshot_hash: str = ""
    current_price_row_fingerprint_sha256: str = ""
    target_metric: str = ""
    predicted_benchmark_excess_return_bp: Mapping[str, int] = field(default_factory=dict)
    h5_status: str = "unknown"
    h5_horizon: int | None = None
    h5_gross_stock_return_bp: int | None = None
    h5_gross_benchmark_return_bp: int | None = None
    h5_benchmark_excess_after_standard_80bp_cost: int | None = None
    h5_after_lane_cost_stock_return_bp: int | None = None
    h5_horizon_end_date: str = ""
    scope_symbols: tuple[str, ...] = ()
    research_only: bool = True
    historical_pit_eligible: bool = False
    formal_qualified: bool = False
    production_action_allowed: bool = False
    qualification: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class StockSavedSourceOptionDTO:
    result_id: str
    label: str
    decision_date: str = ""
    data_date: str = ""


@dataclass(frozen=True)
class StockAdviceSnapshotDTO:
    """沿用既有 Advice DTO；本 DTO 不新增評分或交易動作。"""

    status: str = ReportQuality.UNAVAILABLE.value
    recommendation: RecommendationAdviceDTO | None = None
    portfolio: PortfolioAdviceDTO | None = None
    saved_analysis: WatchlistAnalysisDTO | None = None
    rule_reasons: tuple[str, ...] = ()
    ml_reasons: tuple[str, ...] = ()
    agreement: str = "not_comparable"
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class StockResearchReportDTO:
    """可由持倉、觀察清單及其他研究入口共用的完整個股投影。"""

    stock_code: str
    stock_name: str = ""
    market: str = "台股"
    industry: str = ""
    as_of: str = ""
    generated_at: str = ""
    sources: tuple[StockReportSourceDTO, ...] = ()
    sections: tuple[StockReportSectionDTO, ...] = ()
    available_modules: tuple[str, ...] = ()
    attention_reasons: tuple[str, ...] = ()
    key_risks: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    price_points: tuple[StockPricePointDTO, ...] = ()
    technical: StockTechnicalSnapshotDTO | None = None
    fundamentals: tuple[StockFundamentalObservationDTO, ...] = ()
    flows: tuple[StockFlowObservationDTO, ...] = ()
    institutional: tuple[StockMetricDTO, ...] = ()
    credit: tuple[StockMetricDTO, ...] = ()
    shareholding: tuple[StockMetricDTO, ...] = ()
    events: tuple[StockEvidenceEventDTO, ...] = ()
    position: StockPositionSnapshotDTO | None = None
    market_status: StockMarketStatusSnapshotDTO = field(default_factory=StockMarketStatusSnapshotDTO)
    advice: StockAdviceSnapshotDTO = StockAdviceSnapshotDTO()
    ml: StockMLSnapshotDTO = StockMLSnapshotDTO()
    rule_reasons: tuple[str, ...] = ()
    saved_source_options: tuple[StockSavedSourceOptionDTO, ...] = ()
    shared_daily_features: Mapping[str, Any] = field(default_factory=dict)
    research_context: Mapping[str, str] = field(default_factory=dict)
    read_only: bool = True
    schema_version: str = STOCK_RESEARCH_REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.stock_code.strip():
            raise ValueError("stock_code is required")
        if not self.read_only:
            raise ValueError("stock research report must remain read-only")
    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return _serialize(asdict(cast(Any, value)))
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value
