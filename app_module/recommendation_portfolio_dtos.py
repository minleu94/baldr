import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Dict, List, Literal

import pandas as pd

from app_module.recommendation_portfolio_period_precision_v2 import (
    RecommendationPortfolioPeriodObservationV2,
)
from financial_module.units import quantize_money, to_decimal
from app_module.recommendation_portfolio_execution_inputs_v1 import RecommendationPortfolioExecutionInputsV1

if TYPE_CHECKING:
    from app_module.recommendation.contracts import RecommendationExecution


PeriodPrecisionCaptureStatus = Literal[
    "not_applicable",
    "captured_unqualified",
    "partial",
    "not_single_stock",
    "rejected",
]

PeriodPrecisionDescriptorCaptureStatusV2 = Literal["complete", "partial"]
PeriodPrecisionDescriptorCompletionStatusV2 = Literal["completed", "cancelled"]
PeriodPrecisionCostModelStatusV2 = Literal["identified", "unknown"]
_CAPTURE_DECIMAL_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


def _is_nonempty_descriptor_text(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and len(value) <= 256
        and value == value.strip()
        and all(ord(character) >= 32 for character in value)
    )


@dataclass(frozen=True, slots=True)
class RecommendationPortfolioPeriodPrecisionCaptureV2:
    """原 next-open Decimal 迴圈建立的單股期間捕獲描述。

    ``complete`` 只表示 producer loop 正常走完；``observed_session_dates``
    僅列實際產生的觀察日，不代表官方交易日曆完整。此描述不宣稱來源、幣別、
    成本權威或任何績效資格。
    """

    stock_code: str
    stock_scope_status: Literal["exact_single_stock"]
    capture_status: PeriodPrecisionDescriptorCaptureStatusV2
    initial_capital_decimal: str
    requested_start_date: str
    requested_end_date: str
    observed_session_dates: tuple[str, ...]
    completion_status: PeriodPrecisionDescriptorCompletionStatusV2
    execution_contract_id: str
    execution_contract_version: str
    cost_model_status: PeriodPrecisionCostModelStatusV2
    cost_model_id: str | None
    cost_model_version: str | None
    observations: tuple[RecommendationPortfolioPeriodObservationV2, ...]

    def __post_init__(self) -> None:
        if self.stock_scope_status != "exact_single_stock":
            raise ValueError("期間捕獲描述只接受 exact_single_stock")
        if self.capture_status not in ("complete", "partial"):
            raise ValueError("期間捕獲描述狀態無效")
        if self.completion_status not in ("completed", "cancelled"):
            raise ValueError("期間捕獲完成狀態無效")
        if (self.capture_status, self.completion_status) not in (
            ("complete", "completed"),
            ("partial", "cancelled"),
        ):
            raise ValueError("期間捕獲狀態與 producer completion 不一致")
        if (
            type(self.initial_capital_decimal) is not str
            or not self.initial_capital_decimal
            or len(self.initial_capital_decimal) > 128
            or _CAPTURE_DECIMAL_PATTERN.fullmatch(self.initial_capital_decimal) is None
        ):
            raise ValueError("initial_capital_decimal 必須是有界原始 Decimal 文字")
        try:
            initial_capital = Decimal(self.initial_capital_decimal)
        except InvalidOperation as exc:
            raise ValueError("initial_capital_decimal 不是有效 Decimal") from exc
        if (
            not initial_capital.is_finite()
            or initial_capital <= 0
            or format(initial_capital, "f") != self.initial_capital_decimal
            or len(initial_capital.as_tuple().digits) > 80
        ):
            raise ValueError(
                "initial_capital_decimal 必須是正數 canonical Decimal 文字"
            )

        requested_dates: list[date] = []
        for field_name, value in (
            ("requested_start_date", self.requested_start_date),
            ("requested_end_date", self.requested_end_date),
        ):
            if type(value) is not str:
                raise ValueError(f"{field_name} 必須是 YYYY-MM-DD 日期文字")
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{field_name} 不是有效日期") from exc
            if parsed.isoformat() != value:
                raise ValueError(f"{field_name} 必須是 canonical YYYY-MM-DD")
            requested_dates.append(parsed)
        if requested_dates[1] < requested_dates[0]:
            raise ValueError("requested_end_date 不得早於 requested_start_date")

        if type(self.observations) is not tuple or not self.observations:
            raise ValueError("期間捕獲描述必須綁定非空實際 observation tuple")
        if type(self.observed_session_dates) is not tuple:
            raise ValueError("observed_session_dates 必須是 tuple")
        if any(
            type(row) is not RecommendationPortfolioPeriodObservationV2
            for row in self.observations
        ):
            raise ValueError("期間 observations 必須是 typed V2 observation")
        observation_dates = tuple(row.session_date for row in self.observations)
        if self.observed_session_dates != observation_dates:
            raise ValueError("observed_session_dates 必須逐列對應實際 observations")
        if any(row.stock_code != self.stock_code for row in self.observations):
            raise ValueError("期間 observations 必須全屬於同一精確股票代號")
        parsed_observed_dates = [
            date.fromisoformat(value) for value in observation_dates
        ]
        if any(
            current <= previous
            for previous, current in zip(
                parsed_observed_dates, parsed_observed_dates[1:]
            )
        ):
            raise ValueError("observed_session_dates 必須唯一且遞增")
        if any(
            observed < requested_dates[0] or observed > requested_dates[1]
            for observed in parsed_observed_dates
        ):
            raise ValueError("實際 observation 日期超出 requested 範圍")

        if self.cost_model_status == "unknown":
            if self.cost_model_id is not None or self.cost_model_version is not None:
                raise ValueError("unknown cost model 不得附帶猜測的 ID 或版本")
        elif self.cost_model_status == "identified":
            if (
                not _is_nonempty_descriptor_text(self.cost_model_id)
                or not _is_nonempty_descriptor_text(self.cost_model_version)
            ):
                raise ValueError("identified cost model 必須提供原始 ID 與版本")
        else:
            raise ValueError("cost_model_status 必須明示 identified 或 unknown")
        if (
            not _is_nonempty_descriptor_text(self.execution_contract_id)
            or not _is_nonempty_descriptor_text(self.execution_contract_version)
        ):
            raise ValueError("execution contract ID 與版本不得為空")


@dataclass
class RecommendationSnapshotDTO:
    as_of_date: str
    profile_id: str
    strategy_config: Dict[str, Any]
    regime: str
    recommendations: List[Dict[str, Any]]
    diagnostics: List[str] = field(default_factory=list)

    @property
    def canonical_execution(self) -> "RecommendationExecution | None":
        """回傳本 snapshot instance 的記憶體型 child execution。"""

        return getattr(self, "_canonical_execution", None)

    @property
    def replay_parent_id(self) -> str | None:
        """回傳此 snapshot 的暫存 replay parent 身分。"""

        return getattr(self, "_replay_parent_id", None)

    def attach_replay_parent_id(self, parent_result_id: str) -> None:
        if type(parent_result_id) is not str or not parent_result_id.strip():
            raise ValueError("parent_result_id 不可為空")
        existing = self.replay_parent_id
        if existing is not None and existing != parent_result_id:
            raise ValueError("snapshot replay parent ID 不可重新綁定")
        object.__setattr__(self, "_replay_parent_id", parent_result_id)

    def attach_canonical_execution(
        self, execution: "RecommendationExecution"
    ) -> None:
        """附加暫存 child；不加入 dataclass 欄位或 legacy wire shape。"""

        from app_module.recommendation.contracts import RecommendationExecution

        if type(execution) is not RecommendationExecution:
            raise TypeError("execution 必須是 RecommendationExecution")
        object.__setattr__(self, "_canonical_execution", execution)


@dataclass
class PeriodHoldingDTO:
    rebalance_date: str
    stock_code: str
    stock_name: str
    rank: int
    total_score: float
    factor_scores: Dict[str, float]
    allocation_amount: float
    allocation_weight: float
    entry_date: str
    entry_price: float
    planned_exit_date: str
    actual_exit_date: str
    actual_exit_price: float
    exit_reason: str
    holding_days: int
    return_pct: float
    shares: int | None = None
    actual_allocation_weight: float | None = None
    execution_contract: str = "legacy-same-day-close.v1"
    position_status: str = "closed"
    exit_signal_date: str = ""
    pnl_cents: int | None = None

    def pnl(self) -> float:
        if self.pnl_cents is not None:
            return float(to_decimal(self.pnl_cents) / 100)  # numeric-boundary: dto
        return float(quantize_money(to_decimal(self.allocation_amount) * to_decimal(self.return_pct)))  # numeric-boundary: dto


@dataclass
class StockContributionDTO:
    stock_code: str
    stock_name: str
    selected_count: int
    total_pnl: float
    avg_return_pct: float
    win_rate: float
    worst_return_pct: float


@dataclass
class RecommendationPortfolioBacktestResultDTO:
    summary: Dict[str, Any]
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    snapshots: List[RecommendationSnapshotDTO]
    period_holdings: List[PeriodHoldingDTO]
    stock_contribution: List[StockContributionDTO]
    selection_diagnostics: List[str] = field(default_factory=list)
    improvement_hints: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    period_precision_observations: tuple[
        RecommendationPortfolioPeriodObservationV2, ...
    ] = ()
    period_precision_capture_status: PeriodPrecisionCaptureStatus = "not_applicable"
    period_precision_capture_reason: str | None = None
    period_precision_capture: (
        RecommendationPortfolioPeriodPrecisionCaptureV2 | None
    ) = None
    execution_input_capture: RecommendationPortfolioExecutionInputsV1 | None = None

    @property
    def replay_parent_id(self) -> str | None:
        """回傳本次執行中所有 snapshot 共用的暫存 replay parent。"""

        attached = getattr(self, "_replay_parent_id", None)
        parent_ids = {
            snapshot.replay_parent_id
            for snapshot in self.snapshots
            if snapshot.replay_parent_id is not None
        }
        if self.snapshots and any(
            snapshot.replay_parent_id is None for snapshot in self.snapshots
        ) and (attached is not None or parent_ids):
            raise ValueError("同一次 portfolio 執行不可混用已知與未知 replay parent")
        if len(parent_ids) > 1:
            raise ValueError("同一次 portfolio 執行不可混用 replay parent ID")
        if attached is not None:
            if parent_ids and parent_ids != {attached}:
                raise ValueError("portfolio parent ID 與 snapshot parent 不一致")
            return attached
        return next(iter(parent_ids), None)

    def attach_replay_parent_id(self, parent_result_id: str) -> None:
        if type(parent_result_id) is not str or not parent_result_id.strip():
            raise ValueError("parent_result_id 不可為空")
        existing = self.replay_parent_id
        if existing is not None and existing != parent_result_id:
            raise ValueError("portfolio replay parent ID 不可重新綁定")
        object.__setattr__(self, "_replay_parent_id", parent_result_id)
        _ = self.replay_parent_id

    def to_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict
        return {
            "summary": self.summary,
            "equity_curve": self.equity_curve.to_dict(orient="records") if not self.equity_curve.empty else [],
            "trades": self.trades.to_dict(orient="records") if not self.trades.empty else [],
            "snapshots": [asdict(s) for s in self.snapshots],
            "period_holdings": [asdict(h) for h in self.period_holdings],
            "stock_contribution": [asdict(c) for c in self.stock_contribution],
            "selection_diagnostics": self.selection_diagnostics,
            "improvement_hints": self.improvement_hints,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecommendationPortfolioBacktestResultDTO":
        summary = data.get("summary", {})
        equity_curve = pd.DataFrame(data.get("equity_curve", []))
        trades = pd.DataFrame(data.get("trades", []))
        
        snapshots = []
        for s in data.get("snapshots", []):
            snapshots.append(RecommendationSnapshotDTO(**s))
            
        period_holdings = []
        for h in data.get("period_holdings", []):
            period_holdings.append(PeriodHoldingDTO(**h))
            
        stock_contribution = []
        for c in data.get("stock_contribution", []):
            stock_contribution.append(StockContributionDTO(**c))
            
        selection_diagnostics = data.get("selection_diagnostics", [])
        improvement_hints = data.get("improvement_hints", [])
        details = data.get("details", {})
        
        return cls(
            summary=summary,
            equity_curve=equity_curve,
            trades=trades,
            snapshots=snapshots,
            period_holdings=period_holdings,
            stock_contribution=stock_contribution,
            selection_diagnostics=selection_diagnostics,
            improvement_hints=improvement_hints,
            details=details,
        )

    def period_holdings_dataframe(self) -> pd.DataFrame:
        columns = [
            "再平衡日",
            "股票代號",
            "股票名稱",
            "排名",
            "總分",
            "配置金額",
            "配置權重",
            "實際配置權重",
            "進場日",
            "進場價",
            "預計出場日",
            "實際出場日",
            "實際出場價",
            "出場原因",
            "持有天數",
            "報酬率",
            "損益",
        ]
        rows = []
        for holding in self.period_holdings:
            rows.append(
                {
                    "再平衡日": holding.rebalance_date,
                    "股票代號": holding.stock_code,
                    "股票名稱": holding.stock_name,
                    "排名": holding.rank,
                    "總分": holding.total_score,
                    "配置金額": holding.allocation_amount,
                    "配置權重": holding.allocation_weight,
                    "實際配置權重": holding.actual_allocation_weight,
                    "進場日": holding.entry_date,
                    "進場價": holding.entry_price,
                    "預計出場日": holding.planned_exit_date,
                    "實際出場日": holding.actual_exit_date,
                    "實際出場價": holding.actual_exit_price,
                    "出場原因": holding.exit_reason,
                    "持有天數": holding.holding_days,
                    "報酬率": holding.return_pct,
                    "損益": holding.pnl(),
                }
            )
        return pd.DataFrame(rows, columns=columns)

    def stock_contribution_dataframe(self) -> pd.DataFrame:
        columns = [
            "股票代號",
            "股票名稱",
            "被選次數",
            "總損益",
            "平均報酬率",
            "勝率",
            "最大單筆虧損",
        ]
        rows = []
        for item in self.stock_contribution:
            rows.append(
                {
                    "股票代號": item.stock_code,
                    "股票名稱": item.stock_name,
                    "被選次數": item.selected_count,
                    "總損益": item.total_pnl,
                    "平均報酬率": item.avg_return_pct,
                    "勝率": item.win_rate,
                    "最大單筆虧損": item.worst_return_pct,
                }
            )
        return pd.DataFrame(rows, columns=columns)
