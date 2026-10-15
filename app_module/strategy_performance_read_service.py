"""P08a Paper 單一 checkpoint 唯讀 read model 候選。

此檔只投影 public exact checkpoint reader 已驗證的 DTO；不寫帳戶、
讀 latest、計算金融指標或授予績效資格。尚未接入正式 UI。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app_module.paper_trade_ledger import PaperTradeDailyOperationMarker, PaperTradeFill
from app_module.strategy_paper_account_availability import (
    StrategyPaperAccountAvailability,
    StrategyPaperAccountAvailabilityError,
    StrategyPaperAccountCheckpointRead,
    read_exact_strategy_paper_account_checkpoint,
)
from app_module.strategy_paper_account_service import (
    AccountBindingStatus,
    StrategyPaperAccountBinding,
    StrategyPaperAccountService,
)


_PAPER_METRIC_NAMES = (
    "period_return",
    "net_return",
    "cagr",
    "max_drawdown",
    "win_rate",
)


class ReadStatus(str, Enum):
    VERIFIED = "verified"
    BLOCKED = "blocked"


class QualificationStatus(str, Enum):
    UNKNOWN = "unknown"
    NOT_QUALIFIED = "not_qualified"


class SourceAvailabilityStatus(str, Enum):
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class PaperCheckpointSelector:
    """呼叫端明示 exact identity；不接受 hash、latest 或 eligible 參數。"""

    strategy_id: str
    strategy_version_id: str
    account_namespace: str
    operation_id: str
    snapshot_id: str
    decision_cutoff: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "strategy_id",
            "strategy_version_id",
            "account_namespace",
            "operation_id",
            "snapshot_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be explicit non-empty text")
        if (
            not isinstance(self.decision_cutoff, datetime)
            or self.decision_cutoff.tzinfo is None
            or self.decision_cutoff.utcoffset() is None
        ):
            raise ValueError("decision_cutoff must be timezone-aware")


@dataclass(frozen=True)
class MetricCell:
    """只以 Decimal 表示已解碼值；缺值必須帶明確原因。"""

    value: Decimal | None
    unit: str
    reason: str | None
    source_key: str | None

    def __post_init__(self) -> None:
        if self.value is not None and (
            not isinstance(self.value, Decimal) or not self.value.is_finite()
        ):
            raise ValueError("MetricCell value must be a finite Decimal")
        if self.value is None and not self.reason:
            raise ValueError("missing MetricCell values require a reason")


@dataclass(frozen=True)
class AccountBindingRead:
    strategy_id: str
    strategy_version_id: str
    strategy_version: str
    strategy_artifact_sha256: str
    params_sha256: str
    config_sha256: str
    source_run_id: str
    account_namespace: str
    portfolio_id: str
    binding_sha256: str
    policy_id: str
    policy_version: str
    policy_sha256: str
    cost_model_id: str
    cost_model_version: str
    cost_model_sha256: str
    benchmark_id: str
    benchmark_version: str
    benchmark_sha256: str
    start_date: str
    initial_capital: str
    max_positions: int


@dataclass(frozen=True)
class PaperPositionRead:
    stock_code: str
    quantity: int
    mark_price: Decimal
    market_value: Decimal
    weight_bp: int


@dataclass(frozen=True)
class PaperFillRead:
    fill_id: str
    order_id: str
    portfolio_id: str
    event_date: str
    stock_code: str
    side: str
    requested_quantity: int
    filled_quantity: int
    reference_price: Decimal
    fill_price: Decimal | None
    commission: Decimal
    tax: Decimal
    slippage_cost: Decimal
    turnover_bp: int | None
    execution_gap_bp: int | None
    status: str
    source_event_id: str
    override_reason: str | None
    source_type: str
    research_only: bool
    broker_order_allowed: bool
    auto_rebalance_allowed: bool


@dataclass(frozen=True)
class LedgerMarkerRead:
    operation_id: str
    portfolio_id: str
    event_date: str
    expected_rowset_hash: str
    rowset_hash_after: str
    ordered_fill_ids: tuple[str, ...]
    fill_batch_sha256: str
    transition_id: str | None
    transition_sha256: str | None
    operation_sha256: str
    marker_sha256: str
    zero_fill: bool


@dataclass(frozen=True)
class CheckpointAvailabilityRead:
    schema_version: str
    operation_id: str
    snapshot_id: str
    portfolio_id: str
    account_namespace: str
    binding_sha256: str
    snapshot_sha256: str
    base_receipt_sha256: str
    persisted_at: datetime
    available_at: datetime
    receipt_sha256: str


@dataclass(frozen=True)
class RowProvenance:
    strategy_id: str
    strategy_version_id: str
    account_namespace: str
    portfolio_id: str
    binding_sha256: str
    policy_id: str
    policy_version: str
    policy_sha256: str
    cost_model_id: str
    cost_model_version: str
    cost_model_sha256: str
    benchmark_id: str
    benchmark_version: str
    benchmark_sha256: str
    source_result_id: str
    operation_id: str
    operation_sha256: str
    ledger_operation_sha256: str
    snapshot_id: str
    snapshot_sha256: str
    availability_receipt_sha256: str
    availability_base_receipt_sha256: str
    persisted_at: datetime
    available_at: datetime
    ledger_marker_sha256: str
    ledger_fill_batch_sha256: str
    rowset_hash_before: str
    rowset_hash_after: str
    ordered_fill_ids: tuple[str, ...]
    source_event_ids: tuple[str, ...]
    transition_id: str | None
    transition_sha256: str | None


@dataclass(frozen=True)
class PaperCheckpointCard:
    account_status: AccountBindingStatus | None
    read_status: ReadStatus
    qualification: QualificationStatus
    strategy_id: str
    strategy_version_id: str
    account_namespace: str
    operation_id: str
    operation_sha256: str | None
    snapshot_id: str
    decision_cutoff: datetime
    binding: AccountBindingRead | None
    decision_date: str | None
    cash: Decimal | None
    nav: Decimal | None
    positions: tuple[PaperPositionRead, ...]
    fills: tuple[PaperFillRead, ...]
    zero_fill: bool | None
    ledger_marker: LedgerMarkerRead | None
    availability: CheckpointAvailabilityRead | None
    row_provenance: RowProvenance | None
    source_availability_status: SourceAvailabilityStatus
    source_available_at: datetime | None
    official_session: str | None
    period_curve_status: str
    metrics: tuple[tuple[str, MetricCell], ...]
    qualification_reasons: tuple[str, ...]
    reason: str | None


def _paper_metric_cells(reason: str) -> tuple[tuple[str, MetricCell], ...]:
    return tuple(
        (
            name,
            MetricCell(
                value=None,
                unit="not_available_from_single_checkpoint",
                reason=reason,
                source_key=None,
            ),
        )
        for name in _PAPER_METRIC_NAMES
    )


def _safe_error_code(exc: Exception) -> str:
    """只顯示穩定錯誤碼，避免把本機路徑帶進 UI。"""

    code = str(exc).split(":", maxsplit=1)[0].strip()
    if code and len(code) <= 120 and "\\" not in code and "/" not in code:
        return code
    return type(exc).__name__


def _binding_read(binding: StrategyPaperAccountBinding) -> AccountBindingRead:
    return AccountBindingRead(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        strategy_version=binding.strategy_version,
        strategy_artifact_sha256=binding.strategy_artifact_sha256,
        params_sha256=binding.params_sha256,
        config_sha256=binding.config_sha256,
        source_run_id=binding.source_run_id,
        account_namespace=binding.account_namespace,
        portfolio_id=binding.portfolio_id,
        binding_sha256=binding.binding_sha256,
        policy_id=binding.policy_id,
        policy_version=binding.policy_version,
        policy_sha256=binding.policy_sha256,
        cost_model_id=binding.cost_model_id,
        cost_model_version=binding.cost_model_version,
        cost_model_sha256=binding.cost_model_sha256,
        benchmark_id=binding.benchmark_id,
        benchmark_version=binding.benchmark_version,
        benchmark_sha256=binding.benchmark_sha256,
        start_date=binding.start_date,
        initial_capital=binding.initial_capital,
        max_positions=binding.max_positions,
    )


def _fill_read(fill: PaperTradeFill) -> PaperFillRead:
    return PaperFillRead(
        fill_id=fill.fill_id,
        order_id=fill.order_id,
        portfolio_id=fill.portfolio_id,
        event_date=fill.event_date,
        stock_code=fill.stock_code,
        side=fill.side,
        requested_quantity=fill.requested_quantity,
        filled_quantity=fill.filled_quantity,
        reference_price=fill.reference_price,
        fill_price=fill.fill_price,
        commission=fill.commission,
        tax=fill.tax,
        slippage_cost=fill.slippage_cost,
        turnover_bp=fill.turnover_bp,
        execution_gap_bp=fill.execution_gap_bp,
        status=fill.status,
        source_event_id=fill.source_event_id,
        override_reason=fill.override_reason,
        source_type=fill.source_type,
        research_only=fill.research_only,
        broker_order_allowed=fill.broker_order_allowed,
        auto_rebalance_allowed=fill.auto_rebalance_allowed,
    )


def _marker_read(marker: PaperTradeDailyOperationMarker) -> LedgerMarkerRead:
    return LedgerMarkerRead(
        operation_id=marker.operation_id,
        portfolio_id=marker.portfolio_id,
        event_date=marker.event_date,
        expected_rowset_hash=marker.expected_rowset_hash,
        rowset_hash_after=marker.rowset_hash_after,
        ordered_fill_ids=marker.ordered_fill_ids,
        fill_batch_sha256=marker.fill_batch_sha256,
        transition_id=marker.transition_id,
        transition_sha256=marker.transition_sha256,
        operation_sha256=marker.operation_sha256,
        marker_sha256=marker.marker_sha256,
        zero_fill=marker.zero_fill,
    )


def _availability_read(
    availability: StrategyPaperAccountAvailability,
) -> CheckpointAvailabilityRead:
    return CheckpointAvailabilityRead(
        schema_version=availability.schema_version,
        operation_id=availability.operation_id,
        snapshot_id=availability.snapshot_id,
        portfolio_id=availability.portfolio_id,
        account_namespace=availability.account_namespace,
        binding_sha256=availability.binding_sha256,
        snapshot_sha256=availability.snapshot_sha256,
        base_receipt_sha256=availability.base_receipt_sha256,
        persisted_at=availability.persisted_at,
        available_at=availability.available_at,
        receipt_sha256=availability.receipt_sha256,
    )


def _row_provenance(
    checkpoint: StrategyPaperAccountCheckpointRead,
) -> RowProvenance:
    binding = checkpoint.binding
    availability = checkpoint.availability
    marker = checkpoint.ledger_operation
    return RowProvenance(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
        portfolio_id=binding.portfolio_id,
        binding_sha256=binding.binding_sha256,
        policy_id=binding.policy_id,
        policy_version=binding.policy_version,
        policy_sha256=binding.policy_sha256,
        cost_model_id=binding.cost_model_id,
        cost_model_version=binding.cost_model_version,
        cost_model_sha256=binding.cost_model_sha256,
        benchmark_id=binding.benchmark_id,
        benchmark_version=binding.benchmark_version,
        benchmark_sha256=binding.benchmark_sha256,
        source_result_id=checkpoint.snapshot.source_result_id,
        operation_id=availability.operation_id,
        operation_sha256=checkpoint.operation_sha256,
        ledger_operation_sha256=marker.operation_sha256,
        snapshot_id=checkpoint.snapshot.snapshot_id,
        snapshot_sha256=availability.snapshot_sha256,
        availability_receipt_sha256=availability.receipt_sha256,
        availability_base_receipt_sha256=availability.base_receipt_sha256,
        persisted_at=availability.persisted_at,
        available_at=availability.available_at,
        ledger_marker_sha256=marker.marker_sha256,
        ledger_fill_batch_sha256=marker.fill_batch_sha256,
        rowset_hash_before=marker.expected_rowset_hash,
        rowset_hash_after=marker.rowset_hash_after,
        ordered_fill_ids=marker.ordered_fill_ids,
        source_event_ids=tuple(fill.source_event_id for fill in checkpoint.ordered_fills),
        transition_id=marker.transition_id,
        transition_sha256=marker.transition_sha256,
    )


class StrategyPerformanceReadService:
    """Paper exact read bridge；沒有 writer、latest selector 或資格輸入。"""

    def __init__(self, *, account_service: StrategyPaperAccountService) -> None:
        self._account_service = account_service

    def read_paper_checkpoint(
        self, selector: PaperCheckpointSelector
    ) -> PaperCheckpointCard:
        try:
            checkpoint = read_exact_strategy_paper_account_checkpoint(
                self._account_service,
                strategy_id=selector.strategy_id,
                strategy_version_id=selector.strategy_version_id,
                account_namespace=selector.account_namespace,
                operation_id=selector.operation_id,
                snapshot_id=selector.snapshot_id,
                decision_cutoff=selector.decision_cutoff,
            )
        except (StrategyPaperAccountAvailabilityError, OSError, ValueError) as exc:
            return PaperCheckpointCard(
                account_status=None,
                read_status=ReadStatus.BLOCKED,
                qualification=QualificationStatus.UNKNOWN,
                strategy_id=selector.strategy_id,
                strategy_version_id=selector.strategy_version_id,
                account_namespace=selector.account_namespace,
                operation_id=selector.operation_id,
                operation_sha256=None,
                snapshot_id=selector.snapshot_id,
                decision_cutoff=selector.decision_cutoff,
                binding=None,
                decision_date=None,
                cash=None,
                nav=None,
                positions=(),
                fills=(),
                zero_fill=None,
                ledger_marker=None,
                availability=None,
                row_provenance=None,
                source_availability_status=SourceAvailabilityStatus.UNVERIFIED,
                source_available_at=None,
                official_session=None,
                period_curve_status="unavailable",
                metrics=_paper_metric_cells("exact_checkpoint_read_failed"),
                qualification_reasons=("exact_paper_checkpoint_read_unverified",),
                reason=_safe_error_code(exc),
            )
        return self._verified_card(selector, checkpoint)

    @staticmethod
    def _verified_card(
        selector: PaperCheckpointSelector,
        checkpoint: StrategyPaperAccountCheckpointRead,
    ) -> PaperCheckpointCard:
        snapshot = checkpoint.snapshot
        availability = checkpoint.availability
        marker = checkpoint.ledger_operation
        return PaperCheckpointCard(
            account_status=AccountBindingStatus.READY,
            read_status=ReadStatus.VERIFIED,
            qualification=QualificationStatus.NOT_QUALIFIED,
            strategy_id=checkpoint.binding.strategy_id,
            strategy_version_id=checkpoint.binding.strategy_version_id,
            account_namespace=checkpoint.binding.account_namespace,
            operation_id=availability.operation_id,
            operation_sha256=checkpoint.operation_sha256,
            snapshot_id=snapshot.snapshot_id,
            decision_cutoff=selector.decision_cutoff,
            binding=_binding_read(checkpoint.binding),
            decision_date=snapshot.decision_date,
            cash=snapshot.cash,
            nav=snapshot.total_value,
            positions=tuple(
                PaperPositionRead(
                    stock_code=item.stock_code,
                    quantity=item.quantity,
                    mark_price=item.mark_price,
                    market_value=item.market_value,
                    weight_bp=item.weight_bp,
                )
                for item in snapshot.positions
            ),
            fills=tuple(_fill_read(item) for item in checkpoint.ordered_fills),
            zero_fill=marker.zero_fill,
            ledger_marker=_marker_read(marker),
            availability=_availability_read(availability),
            row_provenance=_row_provenance(checkpoint),
            source_availability_status=SourceAvailabilityStatus.UNVERIFIED,
            source_available_at=None,
            official_session=None,
            period_curve_status="unavailable",
            metrics=_paper_metric_cells(
                "single_checkpoint_has_no_public_source_availability_or_period_curve"
            ),
            qualification_reasons=(
                "public_checkpoint_availability_is_not_underlying_source_availability",
                "official_session_and_market_source_clock_are_unverified",
                "period_curve_and_qualified_cost_window_are_unavailable",
                "read_verified_does_not_grant_performance_qualification",
            ),
            reason=None,
        )
