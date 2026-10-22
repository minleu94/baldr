"""人工確認的保存研究 Paper 模擬事件 producer。"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Callable, Mapping, Protocol
from zoneinfo import ZoneInfo

from app_module.paper_portfolio_policy import (
    PaperPortfolioPolicy,
    PaperPortfolioPolicyConfig,
    PaperPortfolioRebalanceInput,
)
from app_module.execution_slippage_model import FixedBPSlippageModel
from app_module.paper_trade_ledger import (
    MONEY_QUANTUM,
    PaperTradeDailyAppendResult,
    PaperTradeFill,
    PaperTradeLedgerRepository,
    PaperTradeTransition,
)
from app_module.research_timeline_dtos import ResearchTimelineEntry
from app_module.personal_store_routes import PersonalStoreDomain, PersonalStoreMode
from app_module.strategy_paper_account_service import (
    BINDING_SCHEMA_VERSION,
    StrategyPaperAccountBinding,
)
from financial_module.units import calculate_fee, quantize_money


TAIPEI = ZoneInfo("Asia/Taipei")
LINEAGE_SCHEMA_VERSION = "research-paper-confirmed-lineage.v1"
SOURCE_EVENT_PREFIX = "research-paper-confirmation.v1:"
_SHA256_TEXT_LENGTH = 71
CASH_USE_ID = "paper_available_cash_for_confirmed_simulation.v1"
MARK_USE_ID = "paper_same_day_mark_and_execution_reference.v1"
SUPPORTED_COST_MODEL_ID = "taiwan_paper_cost"
SUPPORTED_COST_MODEL_VERSION = "v1"
SUPPORTED_POLICY_ID = "paper_policy_default"
SUPPORTED_POLICY_VERSION = "v1"
SUPPORTED_SLIPPAGE_MODEL_ID = "fixed_bps"
SUPPORTED_SLIPPAGE_MODEL_VERSION = "v1"
SUPPORTED_MINIMUM_FEE = Decimal("20.00")


class ResearchPaperProducerError(ValueError):
    """缺少精確證據、身份或安全條件時拒絕模擬寫入。"""


@dataclass(frozen=True, slots=True)
class HumanConfirmedPaperIntent:
    """已明確綁定候選、帳戶、日期與數量的單筆人工確認意圖。"""

    operation_id: str
    confirmation_id: str
    candidate_identity_sha256: str
    account_namespace: str
    binding_sha256: str
    evidence_fingerprint_sha256: str
    side: str
    quantity: int
    event_date: str
    confirmed_at: str

    def __post_init__(self) -> None:
        for name in (
            "operation_id", "confirmation_id", "candidate_identity_sha256",
            "account_namespace", "binding_sha256", "evidence_fingerprint_sha256",
            "side", "event_date", "confirmed_at",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        _require_sha256(self.candidate_identity_sha256, "candidate_identity_sha256")
        _require_sha256(self.binding_sha256, "binding_sha256")
        _require_sha256(self.evidence_fingerprint_sha256, "evidence_fingerprint_sha256")
        if self.side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int) or self.quantity <= 0:
            raise ValueError("quantity must be a positive integer share count")
        if self.quantity % 1000:
            raise ValueError("quantity must use Taiwan board lots of 1000 shares")
        event_date = _canonical_date(self.event_date, "event_date")
        confirmed_at = _canonical_utc(self.confirmed_at, "confirmed_at")
        if confirmed_at.astimezone(TAIPEI).date() != event_date:
            raise ValueError("event_date must match the Taipei date of confirmation")


@dataclass(frozen=True, slots=True)
class VerifiedResearchCandidate:
    identity_sha256: str
    result_id: str
    record_id: str
    revision_id: str
    stock_code: str
    decision_date: str
    source_identity: str
    source_sha256: str
    provider_id: str

    def __post_init__(self) -> None:
        for name in ("identity_sha256", "source_sha256"):
            _require_sha256(getattr(self, name), name)
        for name in ("record_id", "stock_code", "source_identity", "provider_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.result_id and not isinstance(self.result_id, str):
            raise ValueError("result_id must be text")
        if self.revision_id and not isinstance(self.revision_id, str):
            raise ValueError("revision_id must be text")
        if len(self.stock_code) != 4 or not self.stock_code.isdigit():
            raise ValueError("stock_code must be a four-digit Taiwan symbol")
        _canonical_date(self.decision_date, "decision_date")


@dataclass(frozen=True, slots=True)
class PaperCashEvidence:
    amount: Decimal
    currency: str
    source_id: str
    source_sha256: str
    use_id: str
    use_acceptance_sha256: str
    account_namespace: str
    binding_sha256: str
    available_at: str
    observed_at: str

    def __post_init__(self) -> None:
        _require_money(self.amount, "cash amount")
        if self.currency != "TWD":
            raise ValueError("only the explicitly supported TWD currency is accepted")
        _require_evidence_fields(self)


@dataclass(frozen=True, slots=True)
class PaperMarketEvidence:
    stock_code: str
    currency: str
    mark_price: Decimal
    execution_reference_price: Decimal
    source_id: str
    source_sha256: str
    use_id: str
    use_acceptance_sha256: str
    account_namespace: str
    binding_sha256: str
    event_date: str
    available_at: str
    observed_at: str

    def __post_init__(self) -> None:
        if len(self.stock_code) != 4 or not self.stock_code.isdigit():
            raise ValueError("market stock_code must be a four-digit Taiwan symbol")
        if self.currency != "TWD":
            raise ValueError("only the explicitly supported TWD currency is accepted")
        _require_money(self.mark_price, "mark_price", positive=True)
        _require_money(self.execution_reference_price, "execution_reference_price", positive=True)
        _require_evidence_fields(self)
        _canonical_date(self.event_date, "market event_date")


@dataclass(frozen=True, slots=True)
class VerifiedPaperContext:
    """受信 provider 對同一研究、帳戶、政策、現金與行情版本的核驗結果。"""

    candidate: VerifiedResearchCandidate
    binding: StrategyPaperAccountBinding
    account_manifest_sha256: str
    policy_use_id: str
    policy_artifact_sha256: str
    cost_use_id: str
    cost_artifact_sha256: str
    cost_commission_bp_per_side: int
    cost_slippage_bp_per_side: int
    cost_sell_tax_bp: int
    cost_minimum_fee: Decimal
    slippage_model_id: str
    slippage_model_version: str
    currency: str
    policy: PaperPortfolioPolicyConfig
    cash: PaperCashEvidence
    marks: tuple[PaperMarketEvidence, ...]
    positions: Mapping[str, int]
    sector_by_symbol: Mapping[str, str]
    weekly_turnover_used_bp: int
    trading_days_since_last_trade: int
    ledger_rowset_hash: str
    provider_id: str

    def __post_init__(self) -> None:
        _require_sha256(self.account_manifest_sha256, "account_manifest_sha256")
        _require_sha256(self.policy_artifact_sha256, "policy_artifact_sha256")
        _require_sha256(self.cost_artifact_sha256, "cost_artifact_sha256")
        _require_sha256(self.ledger_rowset_hash, "ledger_rowset_hash")
        if self.currency != "TWD":
            raise ValueError("only the explicitly supported TWD currency is accepted")
        if not self.policy_use_id or not self.cost_use_id or not self.provider_id:
            raise ValueError("policy, cost and provider identities are required")
        if type(self.policy) is not PaperPortfolioPolicyConfig:
            raise TypeError("an exact PaperPortfolioPolicyConfig is required")
        if type(self.candidate) is not VerifiedResearchCandidate:
            raise TypeError("an exact VerifiedResearchCandidate is required")
        if type(self.cash) is not PaperCashEvidence:
            raise TypeError("an exact PaperCashEvidence is required")
        if not isinstance(self.binding, StrategyPaperAccountBinding):
            raise TypeError("a verified StrategyPaperAccountBinding is required")
        try:
            canonical_binding = _canonical_value(self.binding)
            if not isinstance(canonical_binding, Mapping):
                raise ValueError("canonical binding manifest must be a mapping")
            manifest_payload: dict[str, object] = {}
            for key, value in canonical_binding.items():
                if not isinstance(key, str):
                    raise ValueError("canonical binding manifest keys must be text")
                manifest_payload[key] = value
            manifest_payload["schema_version"] = BINDING_SCHEMA_VERSION
            reconstructed_binding = StrategyPaperAccountBinding.from_manifest({
                **manifest_payload,
            })
        except (TypeError, ValueError) as exc:
            raise ValueError("account binding does not satisfy manifest contract") from exc
        if reconstructed_binding != self.binding:
            raise ValueError("account binding differs from its canonical manifest")
        _require_money(self.cost_minimum_fee, "cost_minimum_fee")
        if self.cost_minimum_fee != SUPPORTED_MINIMUM_FEE:
            raise ValueError("only the existing TWD minimum-fee contract is supported")
        if self.slippage_model_id != SUPPORTED_SLIPPAGE_MODEL_ID or self.slippage_model_version != SUPPORTED_SLIPPAGE_MODEL_VERSION:
            raise ValueError("unsupported explicit slippage model")
        for name in ("cost_commission_bp_per_side", "cost_slippage_bp_per_side", "cost_sell_tax_bp"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.marks, tuple):
            raise TypeError("market evidence must be a fixed tuple")
        if any(type(item) is not PaperMarketEvidence for item in self.marks):
            raise TypeError("market evidence must contain exact PaperMarketEvidence values")
        if not isinstance(self.positions, Mapping) or not isinstance(self.sector_by_symbol, Mapping):
            raise TypeError("positions and sectors must be mappings")
        object.__setattr__(self, "positions", MappingProxyType(dict(sorted(self.positions.items()))))
        object.__setattr__(self, "sector_by_symbol", MappingProxyType(dict(sorted(self.sector_by_symbol.items()))))
        for name in ("weekly_turnover_used_bp", "trading_days_since_last_trade"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if any(
            not isinstance(code, str) or len(code) != 4 or not code.isdigit()
            or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0
            for code, quantity in self.positions.items()
        ):
            raise ValueError("positions must map Taiwan symbols to non-negative integer shares")
        if any(not isinstance(code, str) or not sector for code, sector in self.sector_by_symbol.items()):
            raise ValueError("sector map is invalid")


class ResearchPaperEvidenceProvider(Protocol):
    """必須以可信原件 reader 與用途接受證據組成完整 context。"""

    def verify(
        self,
        entry: ResearchTimelineEntry,
        intent: HumanConfirmedPaperIntent,
    ) -> VerifiedPaperContext: ...


@dataclass(frozen=True, slots=True)
class ResearchPaperProductionResult:
    status: str
    candidate_identity_sha256: str
    account_namespace: str
    operation_id: str
    event_date: str
    fill: PaperTradeFill
    transition: PaperTradeTransition
    append: PaperTradeDailyAppendResult
    reopened_fill_ids: tuple[str, ...]
    return_entry: ResearchTimelineEntry


class ResearchPaperProducer:
    """模擬一筆人工確認交易並透過原 Paper ledger 的原子 CAS 保存。"""

    def __init__(
        self,
        *,
        evidence_provider: ResearchPaperEvidenceProvider | None,
        ledger: PaperTradeLedgerRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.evidence_provider = evidence_provider
        self.ledger = ledger
        self.clock = clock or _utc_now

    def produce(
        self,
        entry: ResearchTimelineEntry,
        intent: HumanConfirmedPaperIntent,
    ) -> ResearchPaperProductionResult:
        if type(entry) is not ResearchTimelineEntry:
            raise ResearchPaperProducerError("exact saved research timeline entry is required")
        if type(intent) is not HumanConfirmedPaperIntent:
            raise ResearchPaperProducerError("exact human-confirmed Paper intent is required")
        if not isinstance(self.ledger, PaperTradeLedgerRepository):
            raise ResearchPaperProducerError("the existing PaperTradeLedgerRepository is required")
        if self.evidence_provider is None:
            raise ResearchPaperProducerError("trusted Paper evidence provider is not configured")
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ResearchPaperProducerError("trusted UTC clock returned an invalid timestamp")
        if _canonical_utc(intent.confirmed_at, "confirmed_at") > now.astimezone(timezone.utc):
            raise ResearchPaperProducerError("confirmed_at cannot be in the future")
        candidate_identity = research_candidate_identity_sha256(entry)
        if intent.candidate_identity_sha256 != candidate_identity:
            raise ResearchPaperProducerError("human confirmation candidate identity mismatch")
        context = self.evidence_provider.verify(entry, intent)
        if type(context) is not VerifiedPaperContext:
            raise ResearchPaperProducerError("trusted provider returned an unsupported context")
        binding = context.binding
        if (
            context.candidate.identity_sha256 != candidate_identity
            or context.candidate.record_id != entry.record_id
            or context.candidate.revision_id != _entry_revision_id(entry)
            or context.candidate.result_id != entry.result_id
            or context.candidate.source_identity != entry.source_identity
            or context.candidate.stock_code != entry.stock_code
        ):
            raise ResearchPaperProducerError("verified candidate identity does not match selected research")
        if (
            binding.account_namespace != intent.account_namespace
            or binding.binding_sha256 != intent.binding_sha256
            or binding.portfolio_id != intent.account_namespace
            or binding.policy_sha256 != context.policy_artifact_sha256
            or binding.cost_model_sha256 != context.cost_artifact_sha256
        ):
            raise ResearchPaperProducerError("account, strategy, policy or cost version mismatch")
        if (
            binding.cost_model_id != SUPPORTED_COST_MODEL_ID
            or binding.cost_model_version != SUPPORTED_COST_MODEL_VERSION
            or context.cost_commission_bp_per_side != 15
            or context.cost_slippage_bp_per_side != 10
            or context.cost_sell_tax_bp != 30
            or context.policy.commission_bp_per_side != context.cost_commission_bp_per_side
            or context.policy.slippage_bp_per_side != context.cost_slippage_bp_per_side
            or context.policy.sell_tax_bp != context.cost_sell_tax_bp
        ):
            raise ResearchPaperProducerError("cost artifact semantics do not match the supported taiwan_paper_cost@v1 contract")
        expected_policy = PaperPortfolioPolicyConfig(initial_capital=Decimal("500000"))
        if (
            binding.policy_id != SUPPORTED_POLICY_ID
            or binding.policy_version != SUPPORTED_POLICY_VERSION
            or context.policy != expected_policy
            or binding.max_positions != 8
            or intent.event_date < binding.start_date
        ):
            raise ResearchPaperProducerError("policy artifact semantics or 500000 TWD account binding are unsupported")
        if self.ledger._portfolio_id != binding.portfolio_id:
            raise ResearchPaperProducerError("ledger is not bound to the exact selected account")
        if (
            self.ledger._route is None
            or self.ledger._route.domain is not PersonalStoreDomain.PAPER
            or self.ledger._route.mode is not PersonalStoreMode.PERSONAL
            or self.ledger._route.write_target is None
            or self.ledger._route.identity.key != binding.account_namespace
            or self.ledger._route.paper_account_namespace != binding.account_namespace
            or self.ledger._read_only
        ):
            raise ResearchPaperProducerError("ledger must use the exact PERSONAL Paper account route")
        if context.currency != "TWD" or context.cash.currency != "TWD":
            raise ResearchPaperProducerError("Paper cash currency is not the supported TWD contract")
        if context.policy_use_id != f"{binding.policy_id}@{binding.policy_version}" or context.cost_use_id != f"{binding.cost_model_id}@{binding.cost_model_version}":
            raise ResearchPaperProducerError("policy or cost use identity does not match account binding")
        if verified_context_fingerprint_sha256(context) != intent.evidence_fingerprint_sha256:
            raise ResearchPaperProducerError("human confirmation evidence fingerprint mismatch")
        if (
            context.cash.account_namespace != binding.account_namespace
            or context.cash.binding_sha256 != binding.binding_sha256
            or context.cash.use_id != CASH_USE_ID
        ):
            raise ResearchPaperProducerError("cash evidence account identity mismatch")

        confirmed_at = _canonical_utc(intent.confirmed_at, "confirmed_at")
        _require_available_before(context.cash.available_at, confirmed_at, "cash")
        _require_available_before(context.cash.observed_at, confirmed_at, "cash")
        if context.cash.available_at > context.cash.observed_at:
            raise ResearchPaperProducerError("cash available time follows observation time")
        if (
            _canonical_utc(context.cash.available_at, "cash available_at").astimezone(TAIPEI).date().isoformat() != intent.event_date
            or _canonical_utc(context.cash.observed_at, "cash observed_at").astimezone(TAIPEI).date().isoformat() != intent.event_date
        ):
            raise ResearchPaperProducerError("cash evidence must be available and observed on the confirmed Paper event date")
        if context.cash.amount < 0:
            raise ResearchPaperProducerError("cash balance cannot be negative")
        marks = {item.stock_code: item for item in context.marks}
        if len(marks) != len(context.marks) or entry.stock_code not in marks:
            raise ResearchPaperProducerError("candidate mark evidence is missing or ambiguous")
        for code in set(context.positions) | {entry.stock_code}:
            evidence = marks.get(code)
            if evidence is None:
                raise ResearchPaperProducerError(f"same-day mark evidence is missing:{code}")
            if (
                evidence.account_namespace != binding.account_namespace
                or evidence.binding_sha256 != binding.binding_sha256
                or evidence.currency != "TWD"
                or evidence.event_date != intent.event_date
                or evidence.use_id != MARK_USE_ID
            ):
                raise ResearchPaperProducerError(f"mark evidence identity mismatch:{code}")
            _require_available_before(evidence.available_at, confirmed_at, f"mark:{code}")
            _require_available_before(evidence.observed_at, confirmed_at, f"mark:{code}")
            if evidence.available_at > evidence.observed_at:
                raise ResearchPaperProducerError(f"mark availability follows observation:{code}")
            if (
                _canonical_utc(evidence.available_at, f"mark:{code} available_at").astimezone(TAIPEI).date().isoformat() != intent.event_date
                or _canonical_utc(evidence.observed_at, f"mark:{code} observed_at").astimezone(TAIPEI).date().isoformat() != intent.event_date
            ):
                raise ResearchPaperProducerError(f"same-day mark timestamps are required:{code}")
        existing = self.ledger.get_daily_operation(intent.operation_id, portfolio_id=binding.portfolio_id)
        current_rowset_hash = self.ledger.rowset_hash()
        if existing is None and context.ledger_rowset_hash != current_rowset_hash:
            raise ResearchPaperProducerError("provider account state does not match current ledger rowset")
        if existing is not None and existing.expected_rowset_hash != context.ledger_rowset_hash:
            raise ResearchPaperProducerError("confirmed prestate does not match saved Paper operation")
        if context.policy.initial_capital != Decimal(binding.initial_capital):
            raise ResearchPaperProducerError("policy capital does not match exact bound policy")
        if context.candidate.decision_date > intent.event_date:
            raise ResearchPaperProducerError("Paper event predates the saved research decision")

        candidate_market = marks[entry.stock_code]
        with localcontext() as decimal_context:
            decimal_context.prec = 28
            decimal_context.rounding = ROUND_HALF_UP
            fills, transition = self._build_event(entry, intent, context, marks, candidate_market)
        expected_hash = (
            existing.expected_rowset_hash if existing is not None else context.ledger_rowset_hash
        )
        append = self.ledger.append_daily_operation(
            operation_id=intent.operation_id,
            portfolio_id=binding.portfolio_id,
            event_date=intent.event_date,
            expected_rowset_hash=expected_hash,
            fills=fills,
            transition=transition,
        )
        reopened = self.ledger.read_exact_daily_operation(
            intent.operation_id,
            portfolio_id=binding.portfolio_id,
            event_date=intent.event_date,
        )
        if reopened.ordered_fills != fills or reopened.transition != transition:
            raise ResearchPaperProducerError("Paper ledger exact reopen mismatch")
        status = "already_committed" if append.status == "already_committed" else "appended"
        return ResearchPaperProductionResult(
            status=status,
            candidate_identity_sha256=candidate_identity,
            account_namespace=binding.account_namespace,
            operation_id=intent.operation_id,
            event_date=intent.event_date,
            fill=fills[0],
            transition=transition,
            append=append,
            reopened_fill_ids=tuple(item.fill_id for item in reopened.ordered_fills),
            return_entry=entry,
        )

    @staticmethod
    def _build_event(
        entry: ResearchTimelineEntry,
        intent: HumanConfirmedPaperIntent,
        context: VerifiedPaperContext,
        marks: Mapping[str, PaperMarketEvidence],
        candidate_market: PaperMarketEvidence,
    ) -> tuple[tuple[PaperTradeFill, ...], PaperTradeTransition]:
        policy = context.policy
        positions = dict(context.positions)
        quantity_before = positions.get(entry.stock_code, 0)
        if intent.side == "sell" and intent.quantity > quantity_before:
            raise ResearchPaperProducerError("sell quantity exceeds verified Paper position")
        if intent.side == "buy" and quantity_before == 0 and len([q for q in positions.values() if q > 0]) >= policy.max_positions:
            raise ResearchPaperProducerError("Paper account position limit exceeded")

        pre_positions = {code: qty for code, qty in positions.items() if qty > 0}
        mark_prices = {code: marks[code].mark_price for code in pre_positions}
        mark_prices[entry.stock_code] = candidate_market.mark_price
        pre_cash = context.cash.amount.quantize(MONEY_QUANTUM)
        pre_total = quantize_money(
            pre_cash + sum(
                (mark_prices[code] * Decimal(qty) for code, qty in pre_positions.items()),
                Decimal("0"),
            )
        )
        if pre_total <= 0:
            raise ResearchPaperProducerError("Paper account NAV must be positive")

        reference = candidate_market.execution_reference_price
        fill_price = FixedBPSlippageModel(context.cost_slippage_bp_per_side).calculate_fill_price(
            reference, intent.side
        )
        gross = quantize_money(fill_price * Decimal(intent.quantity))
        commission = calculate_fee(
            gross,
            context.cost_commission_bp_per_side,
            minimum_fee=context.cost_minimum_fee,
        )
        tax = (
            quantize_money(gross * Decimal(policy.sell_tax_bp) / Decimal("10000"))
            if intent.side == "sell" else Decimal("0.00")
        )
        slippage_cost = quantize_money(abs(fill_price - reference) * Decimal(intent.quantity))
        cash_after = quantize_money(
            pre_cash - gross - commission - tax
            if intent.side == "buy" else pre_cash + gross - commission - tax
        )
        if cash_after < 0:
            raise ResearchPaperProducerError("Paper cash is insufficient for confirmed quantity")

        post_positions = dict(pre_positions)
        post_quantity = quantity_before + intent.quantity if intent.side == "buy" else quantity_before - intent.quantity
        if post_quantity:
            post_positions[entry.stock_code] = post_quantity
        else:
            post_positions.pop(entry.stock_code, None)
        post_market_value = quantize_money(
            sum(
                (marks[code].mark_price * Decimal(qty) for code, qty in post_positions.items()),
                Decimal("0"),
            )
        )
        post_total = quantize_money(cash_after + post_market_value)
        if post_total <= 0:
            raise ResearchPaperProducerError("Paper post-trade NAV must remain positive")
        cash_bp = int((pre_cash * Decimal("10000") / pre_total).to_integral_value())
        current_value = quantize_money(candidate_market.mark_price * Decimal(quantity_before))
        current_weight_bp = int((current_value * Decimal("10000") / pre_total).to_integral_value())
        target_value = quantize_money(candidate_market.mark_price * Decimal(post_quantity))
        target_weight_bp = int((target_value * Decimal("10000") / pre_total).to_integral_value())
        sector = context.sector_by_symbol.get(entry.stock_code)
        if not sector:
            raise ResearchPaperProducerError("verified sector mapping is missing")
        sector_value = Decimal("0")
        for code, held in post_positions.items():
            held_sector = context.sector_by_symbol.get(code)
            if not held_sector or code not in mark_prices:
                raise ResearchPaperProducerError(f"verified sector or mark is missing:{code}")
            if held_sector == sector:
                sector_value += mark_prices[code] * Decimal(held)
        sector_weight_after_bp = int(
            (sector_value * Decimal("10000") / pre_total).to_integral_value()
        )
        decision = PaperPortfolioPolicy(policy).evaluate(PaperPortfolioRebalanceInput(
            stock_code=entry.stock_code,
            current_weight_bp=current_weight_bp,
            target_weight_bp=target_weight_bp,
            current_cash_bp=cash_bp,
            sector_weight_after_bp=sector_weight_after_bp,
            weekly_turnover_used_bp=context.weekly_turnover_used_bp,
            trading_days_since_last_trade=context.trading_days_since_last_trade,
        ))
        if decision.action.value != "PAPER_TRADE_CANDIDATE":
            reason = ",".join(decision.reasons) or "paper_policy_rejected"
            raise ResearchPaperProducerError(reason)
        reserve = quantize_money(pre_total * Decimal(policy.minimum_cash_bp) / Decimal("10000"))
        if cash_after < reserve:
            raise ResearchPaperProducerError("minimum Paper cash reserve would be violated")

        candidate = context.candidate
        lineage = {
            "schema_version": LINEAGE_SCHEMA_VERSION,
            "candidate": {
                "identity_sha256": candidate.identity_sha256,
                "kind": entry.kind,
                "record_id": candidate.record_id,
                "revision_id": candidate.revision_id,
                "result_id": candidate.result_id,
                "stock_code": candidate.stock_code,
                "decision_date": candidate.decision_date,
                "source_identity": candidate.source_identity,
                "source_sha256": candidate.source_sha256,
            },
            "account": {
                "namespace": context.binding.account_namespace,
                "binding_sha256": context.binding.binding_sha256,
                "account_manifest_sha256": context.account_manifest_sha256,
                "strategy_version_id": context.binding.strategy_version_id,
                "strategy_artifact_sha256": context.binding.strategy_artifact_sha256,
            },
            "policy": {
                "use_id": context.policy_use_id,
                "artifact_sha256": context.policy_artifact_sha256,
                "config": _policy_projection(policy),
            },
            "cost": {
                "use_id": context.cost_use_id,
                "artifact_sha256": context.cost_artifact_sha256,
                "commission_bp_per_side": context.cost_commission_bp_per_side,
                "slippage_bp_per_side": context.cost_slippage_bp_per_side,
                "sell_tax_bp": context.cost_sell_tax_bp,
                "minimum_fee": str(context.cost_minimum_fee),
                "slippage_model": f"{context.slippage_model_id}.{context.slippage_model_version}",
                "commission": str(commission),
                "tax": str(tax),
                "slippage_cost": str(slippage_cost),
            },
            "currency": "TWD",
            "cash": {
                "source_id": context.cash.source_id,
                "source_sha256": context.cash.source_sha256,
                "use_id": context.cash.use_id,
                "use_acceptance_sha256": context.cash.use_acceptance_sha256,
                "available_at": context.cash.available_at,
                "observed_at": context.cash.observed_at,
                "amount": str(context.cash.amount),
            },
            "market": {
                "source_id": candidate_market.source_id,
                "source_sha256": candidate_market.source_sha256,
                "use_id": candidate_market.use_id,
                "use_acceptance_sha256": candidate_market.use_acceptance_sha256,
                "available_at": candidate_market.available_at,
                "observed_at": candidate_market.observed_at,
                "event_date": candidate_market.event_date,
                "mark_price": str(candidate_market.mark_price),
                "execution_reference_price": str(reference),
            },
            "intent": {
                "operation_id": intent.operation_id,
                "confirmation_id": intent.confirmation_id,
                "confirmed_at": intent.confirmed_at,
                "evidence_fingerprint_sha256": intent.evidence_fingerprint_sha256,
                "side": intent.side,
                "quantity": intent.quantity,
            },
            "fill_semantics": "explicit_user_confirmed_simulation_only",
        }
        lineage_json = _canonical_json(lineage)
        fingerprint = sha256(lineage_json.encode("utf-8")).hexdigest()
        fill_id = "research-paper-fill-v1:" + intent.operation_id
        source_event_id = SOURCE_EVENT_PREFIX + fingerprint
        fill = PaperTradeFill(
            fill_id=fill_id,
            order_id="research-paper-order-v1:" + intent.operation_id,
            portfolio_id=context.binding.portfolio_id,
            event_date=intent.event_date,
            stock_code=entry.stock_code,
            side=intent.side,
            requested_quantity=intent.quantity,
            filled_quantity=intent.quantity,
            reference_price=reference,
            fill_price=fill_price,
            commission=commission,
            tax=tax,
            slippage_cost=slippage_cost,
            turnover_bp=int((reference * Decimal(intent.quantity) * Decimal("10000") / pre_total).to_integral_value()),
            execution_gap_bp=int(((fill_price - reference) * Decimal("10000") / reference).to_integral_value()),
            status="filled",
            source_event_id=source_event_id,
            override_reason=lineage_json,
            source_type="paper_research_confirmed_v1",
        )
        transition = PaperTradeTransition(
            transition_id="research-paper-transition-v1:" + intent.operation_id,
            batch_id="research-paper-batch-v1:" + intent.operation_id,
            portfolio_id=context.binding.portfolio_id,
            event_date=intent.event_date,
            fill_ids=(fill.fill_id,),
            pre_cash=pre_cash,
            pre_total_value=pre_total,
            post_cash=cash_after,
            post_total_value=post_total,
            common_nav=pre_total,
            common_prices=mark_prices,
            pre_positions=pre_positions,
            post_positions=post_positions,
            source_type="paper_research_confirmed_v1",
        )
        return (fill,), transition


def preview_research_paper_simulation(
    entry: ResearchTimelineEntry,
    intent: HumanConfirmedPaperIntent,
    context: VerifiedPaperContext,
) -> tuple[PaperTradeFill, PaperTradeTransition]:
    """使用 producer 的原事件建構器計算唯讀預覽。

    本函式不建立 repository，也不能建立或修改帳本。使用者確認後仍須呼叫
    ``ResearchPaperProducer.produce``；該流程會重讀證據、重核指紋並執行帳本 CAS。
    """
    if type(entry) is not ResearchTimelineEntry or type(intent) is not HumanConfirmedPaperIntent:
        raise ResearchPaperProducerError("exact saved research entry and human intent are required")
    if type(context) is not VerifiedPaperContext:
        raise ResearchPaperProducerError("exact verified Paper context is required")
    if (
        intent.candidate_identity_sha256 != research_candidate_identity_sha256(entry)
        or context.candidate.identity_sha256 != intent.candidate_identity_sha256
        or context.candidate.record_id != entry.record_id
        or context.candidate.revision_id != _entry_revision_id(entry)
        or context.candidate.result_id != entry.result_id
        or context.candidate.source_identity != entry.source_identity
        or context.candidate.stock_code != entry.stock_code
        or context.binding.account_namespace != intent.account_namespace
        or context.binding.binding_sha256 != intent.binding_sha256
        or context.binding.portfolio_id != intent.account_namespace
        or context.cash.account_namespace != intent.account_namespace
        or context.cash.binding_sha256 != intent.binding_sha256
        or context.cash.use_id != CASH_USE_ID
        or context.currency != "TWD"
        or context.cash.currency != "TWD"
        or context.policy_use_id != f"{context.binding.policy_id}@{context.binding.policy_version}"
        or context.cost_use_id != f"{context.binding.cost_model_id}@{context.binding.cost_model_version}"
        or verified_context_fingerprint_sha256(context) != intent.evidence_fingerprint_sha256
    ):
        raise ResearchPaperProducerError("preview intent and verified evidence do not match")
    if (
        context.binding.policy_id != SUPPORTED_POLICY_ID
        or context.binding.policy_version != SUPPORTED_POLICY_VERSION
        or context.binding.cost_model_id != SUPPORTED_COST_MODEL_ID
        or context.binding.cost_model_version != SUPPORTED_COST_MODEL_VERSION
        or context.cost_commission_bp_per_side != 15
        or context.cost_slippage_bp_per_side != 10
        or context.cost_sell_tax_bp != 30
        or context.policy.commission_bp_per_side != 15
        or context.policy.slippage_bp_per_side != 10
        or context.policy.sell_tax_bp != 30
        or context.cost_minimum_fee != SUPPORTED_MINIMUM_FEE
    ):
        raise ResearchPaperProducerError("preview policy or cost semantics are unsupported")
    confirmed_at = _canonical_utc(intent.confirmed_at, "confirmed_at")
    if (
        intent.event_date < context.binding.start_date
        or context.candidate.decision_date > intent.event_date
        or context.policy.initial_capital != Decimal(context.binding.initial_capital)
    ):
        raise ResearchPaperProducerError("preview event date or account capital is outside the bound policy")
    _require_available_before(context.cash.available_at, confirmed_at, "cash")
    _require_available_before(context.cash.observed_at, confirmed_at, "cash")
    if (
        context.cash.available_at > context.cash.observed_at
        or _canonical_utc(context.cash.available_at, "cash available_at").astimezone(TAIPEI).date().isoformat() != intent.event_date
        or _canonical_utc(context.cash.observed_at, "cash observed_at").astimezone(TAIPEI).date().isoformat() != intent.event_date
    ):
        raise ResearchPaperProducerError("preview cash must be available and observed on the confirmed event date")
    marks = {item.stock_code: item for item in context.marks}
    if len(marks) != len(context.marks) or not set(context.positions).issubset(marks):
        raise ResearchPaperProducerError("preview marks must uniquely cover every held position")
    for symbol, evidence in marks.items():
        if (
            evidence.event_date != intent.event_date
            or evidence.currency != "TWD"
            or evidence.account_namespace != intent.account_namespace
            or evidence.binding_sha256 != intent.binding_sha256
            or evidence.use_id != MARK_USE_ID
        ):
            raise ResearchPaperProducerError(f"preview mark identity mismatch:{symbol}")
        _require_available_before(evidence.available_at, confirmed_at, f"mark:{symbol}")
        _require_available_before(evidence.observed_at, confirmed_at, f"mark:{symbol}")
        if (
            evidence.available_at > evidence.observed_at
            or _canonical_utc(evidence.available_at, f"mark:{symbol} available_at").astimezone(TAIPEI).date().isoformat() != intent.event_date
            or _canonical_utc(evidence.observed_at, f"mark:{symbol} observed_at").astimezone(TAIPEI).date().isoformat() != intent.event_date
        ):
            raise ResearchPaperProducerError(f"preview mark must be available and observed on event date:{symbol}")
    market = marks.get(entry.stock_code)
    if (
        market is None
        or market.event_date != intent.event_date
        or market.currency != "TWD"
        or market.account_namespace != intent.account_namespace
        or market.binding_sha256 != intent.binding_sha256
        or market.use_id != MARK_USE_ID
    ):
        raise ResearchPaperProducerError("preview candidate mark identity or date mismatch")
    with localcontext(Context(prec=28, rounding=ROUND_HALF_UP)):
        fills, transition = ResearchPaperProducer._build_event(entry, intent, context, marks, market)
    if len(fills) != 1:
        raise ResearchPaperProducerError("single-candidate Paper preview must produce one event")
    return fills[0], transition


def research_candidate_identity_sha256(entry: ResearchTimelineEntry) -> str:
    """對完整 typed timeline entry（含原件欄位）計算 canonical 身份指紋。"""

    if type(entry) is not ResearchTimelineEntry:
        raise TypeError("ResearchTimelineEntry is required")
    return "sha256:" + sha256(_canonical_json(entry).encode("utf-8")).hexdigest()


def verified_context_fingerprint_sha256(context: VerifiedPaperContext) -> str:
    """計算由人工確認必須綁定的完整候選、帳戶、現金、行情與政策指紋。"""

    if type(context) is not VerifiedPaperContext:
        raise TypeError("VerifiedPaperContext is required")
    payload = _canonical_value(context)
    return "sha256:" + sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(_canonical_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _canonical_value(value: object) -> object:
    if is_dataclass(value):
        return {field.name: _canonical_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical evidence mapping keys must be text")
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical Decimal must be finite")
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float):
        raise TypeError("float is forbidden in Paper identity and evidence")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported canonical evidence value:{type(value).__name__}")


def _policy_projection(policy: PaperPortfolioPolicyConfig) -> dict[str, object]:
    return {
        "initial_capital": str(policy.initial_capital),
        "minimum_cash_bp": policy.minimum_cash_bp,
        "max_positions": policy.max_positions,
        "max_single_position_bp": policy.max_single_position_bp,
        "max_sector_weight_bp": policy.max_sector_weight_bp,
        "rebalance_band_bp": policy.rebalance_band_bp,
        "minimum_trade_bp": policy.minimum_trade_bp,
        "weekly_turnover_cap_bp": policy.weekly_turnover_cap_bp,
        "same_symbol_cooldown_trading_days": policy.same_symbol_cooldown_trading_days,
        "slippage_bp_per_side": policy.slippage_bp_per_side,
        "commission_bp_per_side": policy.commission_bp_per_side,
        "sell_tax_bp": policy.sell_tax_bp,
    }


def _require_evidence_fields(evidence: PaperCashEvidence | PaperMarketEvidence) -> None:
    for name in ("source_id", "use_id", "account_namespace"):
        if not isinstance(getattr(evidence, name), str) or not getattr(evidence, name).strip():
            raise ValueError(f"{name} is required")
    for name in ("source_sha256", "use_acceptance_sha256", "binding_sha256"):
        _require_sha256(getattr(evidence, name), name)
    _canonical_utc(evidence.available_at, "available_at")
    _canonical_utc(evidence.observed_at, "observed_at")


def _entry_revision_id(entry: ResearchTimelineEntry) -> str:
    revision_id = getattr(entry.reference, "revision_id", None)
    if isinstance(revision_id, str) and revision_id:
        return revision_id
    return ""


def _utc_now() -> datetime:
    """Production confirmation time comes from the system UTC clock."""

    return datetime.now(timezone.utc)


def _require_sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str) or len(value) != _SHA256_TEXT_LENGTH
        or not value.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in value[7:])
    ):
        raise ValueError(f"{field} must be canonical sha256 text")
    return value


def _require_money(value: object, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal")
    if positive and value <= 0:
        raise ValueError(f"{field} must be positive")
    if not positive and value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


def _canonical_date(value: str, field: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must use YYYY-MM-DD")
    return parsed


def _canonical_utc(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an aware UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an aware UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be an aware UTC timestamp")
    normalized = parsed.astimezone(timezone.utc)
    if normalized.isoformat() != value:
        raise ValueError(f"{field} must use canonical UTC form")
    return normalized


def _require_available_before(value: str, confirmed_at: datetime, field: str) -> None:
    if _canonical_utc(value, field) > confirmed_at:
        raise ResearchPaperProducerError(f"{field} was unavailable at confirmation time")


__all__ = [
    "HumanConfirmedPaperIntent",
    "PaperCashEvidence",
    "PaperMarketEvidence",
    "ResearchPaperEvidenceProvider",
    "ResearchPaperProducer",
    "ResearchPaperProducerError",
    "ResearchPaperProductionResult",
    "VerifiedPaperContext",
    "VerifiedResearchCandidate",
    "research_candidate_identity_sha256",
    "preview_research_paper_simulation",
    "verified_context_fingerprint_sha256",
]
