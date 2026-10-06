"""單一個股研究報告的唯讀資料契約。

這個模組只描述研究投影，不負責評分、下單或更新資料。數值欄位在
application boundary 保留 ``Decimal``／整數 bp；只有 UI 圖表在明確的
visualisation boundary 才能轉成 ``float``。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from decimal import Decimal
from enum import Enum
import hashlib
import json
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
class StockTechnicalHistoryRowDTO:
    """單一既有技術指標列；不代表 PIT 或指標暖機資格。"""

    stock_code: str
    source_id: str
    data_date: str
    source_row_hash: str
    ma20: Decimal | None = None
    ma60: Decimal | None = None
    available_at: str = ""


def stock_technical_history_row_fingerprint_sha256(
    *,
    stock_code: str,
    source_id: str,
    data_date: str,
    ma20: Decimal | None,
    ma60: Decimal | None,
    available_at: str = "",
) -> str:
    """以投影欄位建立技術歷史列指紋，不寫入 legacy SQLite schema。"""

    def decimal_text(value: Decimal | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError("technical history values must be finite Decimal or None")
        return format(value, "f")

    identity = (
        str(stock_code).strip(),
        str(source_id).strip(),
        str(data_date).strip(),
        decimal_text(ma20),
        decimal_text(ma60),
        str(available_at or "").strip(),
    )
    if not identity[0] or not identity[1] or not identity[2]:
        raise ValueError("technical history row identity is required")
    payload = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def technical_history_saved_scope_limitation(
    context: Mapping[str, object] | None,
) -> str | None:
    """回傳不可由目前 SQLite 補接歷史線的保存來源說明。"""

    if not isinstance(context, Mapping) or not context:
        return None
    source_kind = str(context.get("source_kind", "") or "").strip()
    scope_mode = str(context.get("ml_scope_mode", "") or "").strip()
    if source_kind in {
        "daily_market_research_snapshot",
        "original_stock_ranking",
        "original_stock_ranking_bookmark",
    }:
        return "保存來源沒有綁定相同版本的 MA20/MA60 歷史列；不以目前 SQLite 資料補接。"
    # 與既有個股研究 scope 規則一致：明確標記 current_stock_research 時，舊 metadata
    # 不會把目前個股研究誤判成已保存決策；每日快照已在上方先行封鎖。
    if scope_mode == "current_stock_research":
        return None
    if source_kind == "explicit_latest_stock_research" and not any(
        str(context.get(key, "") or "").strip()
        for key in ("result_id", "source_snapshot_id", "source_snapshot_hash")
    ):
        return None
    if scope_mode and scope_mode != "current_stock_research":
        return "目前選取的是已保存研究來源；沒有同來源 MA20/MA60 歷史列，因此不接目前 SQLite。"
    if source_kind:
        return "目前選取的是已保存研究來源；沒有同來源 MA20/MA60 歷史列，因此不接目前 SQLite。"
    if any(
        str(context.get(key, "") or "").strip()
        for key in ("result_id", "source_snapshot_id", "source_snapshot_hash")
    ) or source_kind == "recommendation":
        return "目前選取的是已保存研究來源；沒有同來源 MA20/MA60 歷史列，因此不接目前 SQLite。"
    return None


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
class StockOriginalRankingReportDTO:
    """個股報告中的原始日／週排名來源，不包含數值評分。"""

    status: str = "unknown"
    reason: str = ""
    rank_kind: str = "original_stock_ranking"
    period: str = ""
    direction: str = ""
    direction_label: str = ""
    native_score_label: str = ""
    rank: int | None = None
    decision_date: str = ""
    comparison_date: str = ""
    latest_date: str = ""
    comparison_window_dates: tuple[str, ...] = ()
    comparison_window_rule: str = ""
    volume_reference_point_count: int = 0
    declared_stock_codes: tuple[str, ...] = ()
    eligible_stock_codes: tuple[str, ...] = ()
    missing_rank_stock_codes: tuple[str, ...] = ()
    research_universe_json: str = ""
    research_universe_sha256: str = ""
    method_name: str = ""
    method_version: str = ""
    method_contract_sha256: str = ""
    engine_file_sha256: str = ""
    engine_parameters_json: str = ""
    engine_parameters_sha256: str = ""
    source_schema_sha256: str = ""
    selected_input_fingerprint_sha256: str = ""
    ranking_root: str = ""
    snapshot_root: str = ""
    rank_manifest_identity_sha256: str = ""
    rank_manifest_sha256: str = ""
    parent_snapshot_identity_sha256: str = ""
    parent_snapshot_sha256: str = ""
    parent_cohort_id: str = ""
    filter_state: str = "all"
    sort_key: str = "rank"
    descending: bool = False
    research_only: bool = True
    historical_pit_eligible: bool = False

    def __post_init__(self) -> None:
        if self.status not in {"available", "unknown"}:
            raise ValueError("原始排名狀態只接受 available 或 unknown")
        if self.period and self.period not in {"day", "week"}:
            raise ValueError("原始排名 period 只接受 day 或 week")
        if self.direction and self.direction not in {"strong", "weak"}:
            raise ValueError("原始排名 direction 只接受 strong 或 weak")
        if self.status == "available":
            if type(self.rank) is not int or self.rank < 1:
                raise ValueError("已核驗的原始排名必須保留正整數原名次")
            if self.direction_label not in {"Top", "Bottom"}:
                raise ValueError("已核驗的原始排名只呈現 Top 或 Bottom 標籤")
            if not self.native_score_label:
                raise ValueError("已核驗的原始排名必須逐字保留 publisher 原始標籤")
            if not self.comparison_date or not self.latest_date:
                raise ValueError("已核驗的原始排名必須保留實際比較日與最新日")
        elif self.rank is not None:
            raise ValueError("來源未知時原始名次必須保持未知")


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
    original_ranking: StockOriginalRankingReportDTO | None = None
    read_only: bool = True
    schema_version: str = STOCK_RESEARCH_REPORT_SCHEMA_VERSION
    # 保留在欄位尾端以維持既有位置參數呼叫相容。
    technical_history: tuple[StockTechnicalHistoryRowDTO, ...] = ()
    saved_technical_chart_json: str = ""

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
