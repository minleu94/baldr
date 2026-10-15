"""將明示策略 Paper checkpoint 接入持倉情境的完整帳戶讀取契約。

本 adapter 只消費公開 exact reader 已核的帳本來源，不自行查 latest、推定
Health 或推算現金。Manual／user_declared 帳戶必須使用各自的來源 reader。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
import json
from zoneinfo import ZoneInfo

from app_module.portfolio_allocation_dtos import _payload_hash, _validate_sha256
from app_module.position_health_daily_refresh_service import (
    PaperHealthSnapshotPosition,
    paper_health_snapshot_rows_sha256,
)
from app_module.portfolio_research_scenario_service import (
    PortfolioResearchAccountState,
    PortfolioResearchPosition,
)
from app_module.portfolio_research_valuation import PortfolioResearchValuation
from app_module.strategy_paper_account_availability import (
    StrategyPaperAccountCheckpointRead,
    read_exact_strategy_paper_account_checkpoint,
)
from app_module.strategy_paper_account_service import (
    AccountBindingStatus,
    StrategyPaperAccountService,
)
from app_module.strategy_paper_account_daily import DailyPriceScalarEvidence


def _mark_evidence(raw: str) -> DailyPriceScalarEvidence:
    payload = json.loads(raw)
    if not isinstance(payload, dict) or set(payload) != set(DailyPriceScalarEvidence.__dataclass_fields__):
        raise ValueError("research_health_mark_evidence_fields_invalid")
    values = dict(payload)
    if not isinstance(values["scalar_value"], str):
        raise ValueError("research_health_mark_price_not_decimal_text")
    values["scalar_value"] = Decimal(values["scalar_value"])
    for name in ("first_observed_at", "written_at"):
        values[name] = datetime.fromisoformat(values[name])
    values["projection_columns"] = tuple(values["projection_columns"])
    result = DailyPriceScalarEvidence(**values)
    if result.to_payload() != payload:
        raise ValueError("research_health_mark_evidence_not_canonical")
    return result


def _checkpoint_entry_ids(checkpoint: StrategyPaperAccountCheckpointRead) -> tuple[tuple[str, str | None], ...]:
    """沿同一已核完整 prefix 的真空倉後買入辨認 entry；seed 持倉不猜 lineage。"""
    result: list[tuple[str, str | None]] = []
    transitions = checkpoint.allocation_prefix_transitions
    fills = checkpoint.allocation_prefix_fills
    for position in sorted(checkpoint.snapshot.positions, key=lambda row: row.stock_code):
        if position.quantity <= 0:
            continue
        entry_id: str | None = None
        if transitions:
            quantity = transitions[0].pre_positions.get(position.stock_code, 0)
            for fill in fills:
                if fill.stock_code != position.stock_code or not fill.filled_quantity:
                    continue
                if fill.side == "buy":
                    if quantity == 0:
                        entry_id = f"strategy:{checkpoint.binding.account_namespace}:{position.stock_code}:{fill.fill_id}"
                    quantity += fill.filled_quantity
                else:
                    quantity -= fill.filled_quantity
                    if quantity < 0:
                        raise ValueError("research_health_entry_lineage_quantity_invalid")
                    if quantity == 0:
                        entry_id = None
            if quantity != position.quantity:
                raise ValueError("research_health_entry_lineage_snapshot_mismatch")
        result.append((position.stock_code, entry_id))
    return tuple(result)


def _weekly_turnover(checkpoint: StrategyPaperAccountCheckpointRead, decision_date: str) -> int:
    # 沿原配置證據的 rolling 7 日及共用 NAV／價格契約，不加總 gross fill turnover。
    from app_module.ml_allocation_shadow_evidence import _common_price_weights
    from financial_module.portfolio_turnover import canonical_turnover_bp

    window_start = (date.fromisoformat(decision_date) - timedelta(days=7)).isoformat()
    total = 0
    with localcontext(Context(prec=60)):
        for transition in checkpoint.allocation_prefix_transitions:
            if not window_start <= transition.event_date < decision_date:
                continue
            before = _common_price_weights(positions=transition.pre_positions,
                prices=transition.common_prices, common_nav=transition.common_nav)
            after = _common_price_weights(positions=transition.post_positions,
                prices=transition.common_prices, common_nav=transition.common_nav)
            symbols = tuple(sorted(set(before.symbol_weights_bp) | set(after.symbol_weights_bp)))
            total += canonical_turnover_bp(
                current_position_weights_bp=tuple(before.weight_for(code) for code in symbols),
                current_cash_bp=before.cash_weight_bp,
                target_position_weights_bp=tuple(after.weight_for(code) for code in symbols),
                target_cash_bp=after.cash_weight_bp,
            )
    return total


def _account_checkpoint_source_hash(
    *, binding_sha256: str, operation_id: str, operation_sha256: str,
    snapshot_id: str, snapshot_sha256: str, base_receipt_sha256: str,
    availability_receipt_sha256: str, ledger_operation_sha256: str,
) -> str:
    return _payload_hash({
        "schema_version": "portfolio-research-strategy-paper-source.v1",
        "binding_sha256": binding_sha256, "operation_id": operation_id,
        "operation_sha256": operation_sha256, "snapshot_id": snapshot_id,
        "snapshot_sha256": snapshot_sha256, "base_receipt_sha256": base_receipt_sha256,
        "availability_receipt_sha256": availability_receipt_sha256,
        "ledger_operation_sha256": ledger_operation_sha256,
    })


@dataclass(frozen=True, slots=True)
class StrategyPaperResearchCheckpointSelection:
    """使用者已選的來源身分；不包含 caller 宣稱的 hashes 或可得時間。"""

    strategy_id: str
    strategy_version_id: str
    account_namespace: str
    operation_id: str
    snapshot_id: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"research_checkpoint_selection_{name}_invalid")


@dataclass(frozen=True, slots=True)
class StrategyPaperResearchHealthSource:
    """同一次 exact checkpoint 的帳戶與 Health 原列投影；不宣稱已知 Health。"""

    selection: StrategyPaperResearchCheckpointSelection
    account: PortfolioResearchAccountState
    snapshot_source_result_id: str
    positions: tuple[PaperHealthSnapshotPosition, ...]
    source_snapshot_rows_sha256: str
    checkpoint_snapshot_sha256: str
    binding_sha256: str
    operation_sha256: str
    base_receipt_sha256: str
    availability_receipt_sha256: str
    ledger_operation_sha256: str
    mark_prices: tuple[DailyPriceScalarEvidence, ...]
    entry_lineage_ids: tuple[tuple[str, str | None], ...]
    allocation_decision_date: str
    allocation_prefix_rowset_hash: str
    weekly_turnover_used_bp: int

    def __post_init__(self) -> None:
        if not isinstance(self.selection, StrategyPaperResearchCheckpointSelection):
            raise ValueError("research_health_checkpoint_selection_required")
        if not isinstance(self.account, PortfolioResearchAccountState):
            raise ValueError("research_health_complete_account_required")
        for name in (
            "source_snapshot_rows_sha256", "checkpoint_snapshot_sha256", "binding_sha256",
            "operation_sha256", "base_receipt_sha256", "availability_receipt_sha256",
            "ledger_operation_sha256", "allocation_prefix_rowset_hash",
        ):
            _validate_sha256(name, getattr(self, name))
        if (
            self.account.account_kind != "paper"
            or self.account.portfolio_id != self.selection.account_namespace
            or self.account.snapshot_id != self.selection.snapshot_id
            or self.selection.account_namespace != "acct-" + self.binding_sha256.removeprefix("sha256:")
        ):
            raise ValueError("research_health_account_binding_mismatch")
        if self.account.source_hash != _account_checkpoint_source_hash(
            binding_sha256=self.binding_sha256, operation_id=self.selection.operation_id,
            operation_sha256=self.operation_sha256, snapshot_id=self.account.snapshot_id,
            snapshot_sha256=self.checkpoint_snapshot_sha256,
            base_receipt_sha256=self.base_receipt_sha256,
            availability_receipt_sha256=self.availability_receipt_sha256,
            ledger_operation_sha256=self.ledger_operation_sha256,
        ):
            raise ValueError("research_health_account_source_hash_mismatch")
        expected_rows_hash = paper_health_snapshot_rows_sha256(
            snapshot_id=self.account.snapshot_id, portfolio_id=self.account.portfolio_id,
            decision_date=self.account.as_of_date, source_result_id=self.snapshot_source_result_id,
            positions=self.positions,
        )
        if expected_rows_hash != self.source_snapshot_rows_sha256:
            raise ValueError("research_health_rows_hash_mismatch")
        if {row.stock_code: row.shares for row in self.positions if row.shares > 0} != {
            row.stock_code: row.quantity for row in self.account.positions
        }:
            raise ValueError("research_health_complete_positions_mismatch")
        if any(row.shares > 0 and row.weight_bp != self.account.current_weights.weight_for(row.stock_code)
               for row in self.positions):
            raise ValueError("research_health_account_weights_mismatch")
        marks = {row.stock_code: row for row in self.mark_prices}
        if len(marks) != len(self.mark_prices) or set(marks) != {row.stock_code for row in self.account.positions}:
            raise ValueError("research_health_complete_mark_evidence_required")
        valued = {row.stock_code: row for row in self.account.valuation.positions}
        for code, mark in marks.items():
            if (mark.scalar_column != "收盤價" or mark.scalar_value != valued[code].mark_price
                    or mark.source_date > self.account.as_of_date or mark.written_at > self.account.available_at):
                raise ValueError("research_health_mark_account_mismatch")
        if tuple(code for code, _ in self.entry_lineage_ids) != tuple(sorted(valued)):
            raise ValueError("research_health_entry_lineage_universe_mismatch")
        if (date.fromisoformat(self.allocation_decision_date).isoformat() != self.allocation_decision_date
                or self.allocation_decision_date <= self.account.as_of_date
                or self.account.available_at.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat() > self.allocation_decision_date
                or type(self.weekly_turnover_used_bp) is not int or self.weekly_turnover_used_bp < 0):
            raise ValueError("research_health_allocation_evidence_invalid")

    @property
    def source_hash(self) -> str:
        return _payload_hash(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "portfolio-research-strategy-health-source.v1",
            "selection": {name: getattr(self.selection, name) for name in self.selection.__dataclass_fields__},
            "account": self.account.to_dict(),
            "snapshot_source_result_id": self.snapshot_source_result_id,
            "positions": [{"stock_code": row.stock_code, "shares": row.shares, "weight_bp": row.weight_bp}
                          for row in self.positions],
            "mark_prices": [row.to_payload() for row in self.mark_prices],
            "entry_lineage_ids": [{"stock_code": code, "entry_lineage_id": identity}
                                  for code, identity in self.entry_lineage_ids],
            "allocation_decision_date": self.allocation_decision_date,
            "allocation_prefix_rowset_hash": self.allocation_prefix_rowset_hash,
            "weekly_turnover_used_bp": self.weekly_turnover_used_bp,
            "weekly_turnover_basis": "paper_trade_transition.canonical_turnover_bp.rolling_7d.exclusive.v1",
            **{name: getattr(self, name) for name in (
                "source_snapshot_rows_sha256", "checkpoint_snapshot_sha256", "binding_sha256",
                "operation_sha256", "base_receipt_sha256", "availability_receipt_sha256",
                "ledger_operation_sha256",
            )},
        }


class StrategyPaperPortfolioResearchAccountReader:
    """綁定明示 checkpoint 與本次決策時計的策略 Paper 帳戶 reader。"""

    def __init__(
        self,
        account_service: StrategyPaperAccountService,
        selection: StrategyPaperResearchCheckpointSelection,
        *,
        decision_cutoff: datetime,
    ) -> None:
        if not isinstance(selection, StrategyPaperResearchCheckpointSelection):
            raise ValueError("research_checkpoint_selection_required")
        if (
            not isinstance(decision_cutoff, datetime)
            or decision_cutoff.tzinfo is None
            or decision_cutoff.utcoffset() is None
        ):
            raise ValueError("research_account_decision_cutoff_timezone_unknown")
        self._service = account_service
        self._selection = selection
        self._decision_cutoff = decision_cutoff.astimezone(timezone.utc)

    def read_exact(
        self, *, account_kind: str, portfolio_id: str, snapshot_id: str
    ) -> PortfolioResearchAccountState:
        checkpoint = self._read_verified_checkpoint(
            account_kind=account_kind, portfolio_id=portfolio_id, snapshot_id=snapshot_id,
        )
        return self._account_from_checkpoint(checkpoint)

    def read_health_source(
        self, *, portfolio_id: str, snapshot_id: str, allocation_decision_date: str | None = None,
    ) -> StrategyPaperResearchHealthSource:
        """重驗原 checkpoint，再從同一份讀回建立 Health 來源，不另查 latest。"""
        selected_date = allocation_decision_date or self._decision_cutoff.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat()
        if (date.fromisoformat(selected_date).isoformat() != selected_date
                or selected_date > self._decision_cutoff.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat()):
            raise ValueError("research_health_allocation_date_after_cutoff")
        checkpoint = self._read_verified_checkpoint(
            account_kind="paper", portfolio_id=portfolio_id, snapshot_id=snapshot_id,
            allocation_decision_date=selected_date,
        )
        account = self._account_from_checkpoint(checkpoint)
        positions = tuple(PaperHealthSnapshotPosition(row.stock_code, row.quantity, row.weight_bp)
                          for row in sorted(checkpoint.snapshot.positions, key=lambda row: row.stock_code))
        return StrategyPaperResearchHealthSource(
            selection=self._selection, account=account,
            snapshot_source_result_id=checkpoint.snapshot.source_result_id,
            positions=positions,
            source_snapshot_rows_sha256=paper_health_snapshot_rows_sha256(
                snapshot_id=snapshot_id, portfolio_id=portfolio_id, decision_date=account.as_of_date,
                source_result_id=checkpoint.snapshot.source_result_id, positions=positions,
            ),
            checkpoint_snapshot_sha256=checkpoint.availability.snapshot_sha256,
            binding_sha256=checkpoint.binding.binding_sha256,
            operation_sha256=checkpoint.operation_sha256,
            base_receipt_sha256=checkpoint.availability.base_receipt_sha256,
            availability_receipt_sha256=checkpoint.availability.receipt_sha256,
            ledger_operation_sha256=checkpoint.ledger_operation.operation_sha256,
            mark_prices=tuple(_mark_evidence(raw) for raw in checkpoint.mark_price_evidence_json),
            entry_lineage_ids=_checkpoint_entry_ids(checkpoint),
            allocation_decision_date=selected_date,
            allocation_prefix_rowset_hash=checkpoint.allocation_prefix_rowset_hash or "",
            weekly_turnover_used_bp=_weekly_turnover(checkpoint, selected_date),
        )

    def _read_verified_checkpoint(
        self, *, account_kind: str, portfolio_id: str, snapshot_id: str,
        allocation_decision_date: str | None = None,
    ) -> StrategyPaperAccountCheckpointRead:
        selection = self._selection
        if account_kind != "paper":
            raise ValueError("strategy_research_reader_requires_paper_account")
        if snapshot_id != selection.snapshot_id:
            raise ValueError("research_account_snapshot_selection_mismatch")
        selected = self._service.select_exact_version(
            strategy_id=selection.strategy_id,
            strategy_version_id=selection.strategy_version_id,
            account_namespace=selection.account_namespace,
        )
        if selected.status is not AccountBindingStatus.READY or selected.binding is None:
            raise ValueError("research_account_binding_unavailable")
        if portfolio_id != selected.binding.portfolio_id:
            raise ValueError("research_account_portfolio_selection_mismatch")
        checkpoint = read_exact_strategy_paper_account_checkpoint(
            self._service,
            strategy_id=selection.strategy_id,
            strategy_version_id=selection.strategy_version_id,
            account_namespace=selection.account_namespace,
            operation_id=selection.operation_id,
            snapshot_id=selection.snapshot_id,
            decision_cutoff=self._decision_cutoff,
            allocation_decision_date=allocation_decision_date,
        )
        if (
            checkpoint.binding != selected.binding
            or checkpoint.snapshot.snapshot_id != snapshot_id
            or checkpoint.snapshot.portfolio_id != portfolio_id
        ):
            raise ValueError("research_account_exact_checkpoint_mismatch")
        return checkpoint

    def _account_from_checkpoint(
        self, checkpoint: StrategyPaperAccountCheckpointRead,
    ) -> PortfolioResearchAccountState:
        selection = self._selection
        snapshot_id = checkpoint.snapshot.snapshot_id
        portfolio_id = checkpoint.snapshot.portfolio_id
        valuation = PortfolioResearchValuation.from_snapshot(checkpoint.snapshot)
        # 綁實際來源的各層身分；content hash 不另授來源時效或績效資格。
        source_hash = _account_checkpoint_source_hash(
            binding_sha256=checkpoint.binding.binding_sha256,
            operation_id=selection.operation_id,
            operation_sha256=checkpoint.operation_sha256,
            snapshot_id=snapshot_id,
            snapshot_sha256=checkpoint.availability.snapshot_sha256,
            base_receipt_sha256=checkpoint.availability.base_receipt_sha256,
            availability_receipt_sha256=checkpoint.availability.receipt_sha256,
            ledger_operation_sha256=checkpoint.ledger_operation.operation_sha256,
        )
        return PortfolioResearchAccountState(
            account_kind="paper",
            portfolio_id=portfolio_id,
            snapshot_id=snapshot_id,
            as_of_date=checkpoint.snapshot.decision_date,
            available_at=checkpoint.availability.available_at,
            source_hash=source_hash,
            capital_amount=valuation.total_value,
            current_weights=valuation.display_weights,
            positions=tuple(
                PortfolioResearchPosition(row.stock_code, row.quantity)
                for row in valuation.positions
            ),
            valuation=valuation,
        )
