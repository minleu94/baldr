"""從成對 exact 策略帳與原 Health 封存建立首次配置研究。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable
from zoneinfo import ZoneInfo

from app_module.portfolio_allocation_dtos import AllocationWeightContract, PortfolioAllocationContextRow, _payload_hash
from app_module.portfolio_research_account_reader import (
    StrategyPaperPortfolioResearchAccountReader, StrategyPaperResearchCheckpointSelection,
)
from app_module.portfolio_research_scenario_service import (
    PortfolioResearchContextEvidence, PortfolioResearchScenarioComparison,
    PortfolioResearchScenarioRequest, PortfolioResearchScenarioService,
)
from app_module.position_health_strategy_archive import (
    StrategyHealthArchiveReference, list_strategy_saved_health_receipts,
    read_strategy_saved_health_exact,
)
from app_module.position_health_saved_archive import SavedHealthArchiveError
from app_module.position_health_transition_read_service import PositionHealthTransitionReadService
from app_module.strategy_paper_account_availability import list_strategy_paper_account_checkpoint_candidates
from app_module.strategy_paper_account_service import StrategyPaperAccountService


def _cancel(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise InterruptedError("研究操作已取消")


@dataclass(frozen=True, slots=True)
class InitialPortfolioResearchSelection:
    checkpoint: StrategyPaperResearchCheckpointSelection
    health_reference: StrategyHealthArchiveReference

    def __post_init__(self) -> None:
        if not isinstance(self.checkpoint, StrategyPaperResearchCheckpointSelection) or not isinstance(
            self.health_reference, StrategyHealthArchiveReference
        ):
            raise ValueError("必須明選策略 checkpoint 與 Health v2 收據")


@dataclass(frozen=True, slots=True)
class InitialPortfolioResearchCandidate:
    selection: InitialPortfolioResearchSelection
    label: str


@dataclass(frozen=True, slots=True)
class InitialPortfolioResearchCatalogue:
    candidates: tuple[InitialPortfolioResearchCandidate, ...]
    truncated: bool
    later_day_receipts: int = 0


class PortfolioResearchInitialSourceProvider:
    """只讀明示帳戶及成對收據；不建立來源、不查全域 latest。"""

    def __init__(self, account_service: StrategyPaperAccountService,
                 health_reader: PositionHealthTransitionReadService) -> None:
        self.account_service = account_service
        self.health_reader = health_reader

    def list_sources(self, *, strategy_id: str, strategy_version_id: str, account_namespace: str,
                     cancel_callback: Callable[[], bool] | None = None) -> InitialPortfolioResearchCatalogue:
        _cancel(cancel_callback)
        now = datetime.now(timezone.utc)
        checkpoints = list_strategy_paper_account_checkpoint_candidates(
            self.account_service, strategy_id=strategy_id, strategy_version_id=strategy_version_id,
            account_namespace=account_namespace, decision_cutoff=now,
        )
        _cancel(cancel_callback)
        health, truncated = list_strategy_saved_health_receipts(
            reader=self.health_reader, strategy_id=strategy_id, strategy_version_id=strategy_version_id,
            account_namespace=account_namespace, decision_cutoff=now, cancel_callback=cancel_callback,
        )
        keys = {(row.operation_id, row.snapshot_id) for row in checkpoints.rows
                if row.row_state == "candidate_pending_exact_reader"}
        candidates: list[InitialPortfolioResearchCandidate] = []
        later_day_receipts = 0
        for row in health:
            if (row.selection.operation_id, row.selection.snapshot_id) not in keys:
                continue
            available = datetime.fromisoformat(row.available_at)
            if available.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat() != row.decision_date:
                later_day_receipts += 1
                continue
            candidates.append(InitialPortfolioResearchCandidate(
                InitialPortfolioResearchSelection(row.selection, row.reference),
                f"{row.decision_date}｜可得 {available.astimezone(ZoneInfo('Asia/Taipei')):%H:%M}｜"
                f"{row.selection.snapshot_id}｜{row.reference.receipt_id[-12:]}（待精確重核）",
            ))
        _cancel(cancel_callback)
        return InitialPortfolioResearchCatalogue(
            tuple(candidates), truncated or checkpoints.truncated, later_day_receipts,
        )

    def compare(self, selection: InitialPortfolioResearchSelection, *, candidate_symbols: tuple[str, ...],
                explicit_weights: AllocationWeightContract | None = None,
                decision_at: datetime | None = None,
                cancel_callback: Callable[[], bool] | None = None) -> PortfolioResearchScenarioComparison:
        _cancel(cancel_callback)
        now = datetime.now(timezone.utc)
        checkpoint = selection.checkpoint
        if decision_at is None:
            # 先只核收據 metadata，避免用現在帳本讀取阻擋原時刻仍有效的舊 checkpoint。
            receipts, _truncated = list_strategy_saved_health_receipts(
                reader=self.health_reader, strategy_id=checkpoint.strategy_id,
                strategy_version_id=checkpoint.strategy_version_id,
                account_namespace=checkpoint.account_namespace, decision_cutoff=now,
                cancel_callback=cancel_callback,
            )
            matching = tuple(row for row in receipts if row.selection == checkpoint
                             and row.reference == selection.health_reference)
            if len(matching) != 1:
                same_receipt = tuple(row for row in receipts if row.selection == checkpoint
                                     and row.reference.receipt_id == selection.health_reference.receipt_id)
                if len(same_receipt) == 1 and (
                    same_receipt[0].reference.receipt_sha256 != selection.health_reference.receipt_sha256
                ):
                    raise SavedHealthArchiveError("strategy_health_external_receipt_hash_mismatch")
                raise ValueError("所選 Health 收據已不在同帳戶有界清單，請重新載入來源")
            receipt = matching[0]
            decision = datetime.fromisoformat(receipt.available_at)
            if decision.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat() != receipt.decision_date:
                raise ValueError("Health 收據在評估日後才保存，不能倒填原日研究決策時間")
        else:
            decision = decision_at
        if decision.tzinfo is None or decision.utcoffset() is None or decision > now:
            raise ValueError("研究決策時間無時區或晚於目前時間")
        account_reader = StrategyPaperPortfolioResearchAccountReader(
            self.account_service, checkpoint, decision_cutoff=decision,
        )
        saved = read_strategy_saved_health_exact(
            reader=self.health_reader, reference=selection.health_reference, account_reader=account_reader,
            portfolio_id=checkpoint.account_namespace, snapshot_id=checkpoint.snapshot_id, decision_cutoff=decision,
        )
        _cancel(cancel_callback)
        if saved.decision_date != decision.astimezone(ZoneInfo("Asia/Taipei")).date():
            raise ValueError("Health 評估日期與本次研究決策日不同，請先保存當日有效評估")
        source = saved.source
        if source.weekly_turnover_used_bp > 10000:
            raise ValueError("已核週換手超過目前配置契約上限，未裁切數值")
        required = set(candidate_symbols) | {row.stock_code for row in source.account.positions}
        marks = {row.stock_code: row for row in source.mark_prices}
        entries = dict(source.entry_lineage_ids)
        contexts: list[PortfolioResearchContextEvidence] = []
        for code in sorted(required):
            row = saved.health.for_position(entries.get(code))
            mark = marks.get(code)
            if row is None or row.stock_code != code or mark is None:
                raise ValueError(f"{code} 缺少同一帳戶來源的 Health／行情；不能補造未持有候選的資料")
            if not isinstance(mark.scalar_value, Decimal):
                raise ValueError(f"{code} 行情不是原始 Decimal 價格")
            known = (row.is_identity_verified and row.source_status == "verified"
                     and row.quality in {"verified", "observed"}
                     and row.thesis_status == "verified" and row.metrics_status == "verified"
                     and row.condition_status in {"valid", "warning", "invalid"}
                     and not row.required_human_fields and not row.blockers
                     and row.proposed_state == row.raw_proposed_state and row.proposed_state != "CLOSED")
            if not known:
                raise ValueError(f"{code} 的 Health 來源缺件或未完成治理：" + ",".join((*row.blockers, *row.required_human_fields, *row.why_not)))
            contexts.append(PortfolioResearchContextEvidence(
                account_kind="paper", portfolio_id=source.account.portfolio_id,
                snapshot_id=source.account.snapshot_id,
                context=PortfolioAllocationContextRow(
                    stock_code=code, current_weight_bp=source.account.current_weights.weight_for(code),
                    current_shares=next(item.quantity for item in source.account.positions if item.stock_code == code),
                    health_state=row.proposed_state, reference_price=mark.scalar_value,
                    hard_risk_reasons=row.reasons if row.proposed_state == "EXIT_CANDIDATE" else (),
                    market_data_as_of_date=mark.source_date,
                    median_volume_20d_shares=None, trading_days_since_last_trade=None,
                ),
                available_at=max(source.account.available_at, saved.available_at, mark.written_at),
                source_hash=_payload_hash({"schema_version": "portfolio-research-initial-context.v1",
                    "account_source": source.source_hash, "health_receipt": saved.reference.receipt_sha256,
                    "health_result": saved.result_sha256, "health_position": row.to_dict(),
                    "mark": mark.to_payload()}), health_known=True,
            ))
        request = PortfolioResearchScenarioRequest(
            account_kind="paper", portfolio_id=source.account.portfolio_id, snapshot_id=source.account.snapshot_id,
            decision_at=decision, candidate_symbols=candidate_symbols, contexts=tuple(contexts),
            explicit_weights=explicit_weights, weekly_turnover_used_bp=source.weekly_turnover_used_bp,
            research_source_hash=_payload_hash({"schema_version": "portfolio-research-initial-source.v1",
                "source_sha256": source.source_hash, "health_receipt_sha256": saved.reference.receipt_sha256,
                "health_result_sha256": saved.result_sha256, "health_baseline_sha256": saved.baseline_sha256}),
        )
        result = PortfolioResearchScenarioService(account_reader).compare(request)
        _cancel(cancel_callback)
        return result
