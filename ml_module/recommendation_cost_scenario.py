"""推薦 calibration 的成本情境 contract 與臺銀研究估算。

本模組把「成本設定」和「單筆市場觀測」分開：scenario hash 是跨日期穩定
的 cohort／experiment identity；market replay date 只存在於每筆 estimate，
不會把同一個 scenario 拆成每日不同的 experiment。臺銀路徑使用明確的
研究訂單金額或股數，並在成熟後以決策日買入價與 label 結束價估算買賣兩邊
成本。無法取得必要價格或 policy 時回傳 unavailable，絕不把成本補成零。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
import hashlib
import json
from typing import Any, Mapping

from financial_module.banktaiwan_cost_policy import (
    BANKTAIWAN_ELECTRONIC_COST_POLICY_ID,
    BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION,
    BankTaiwanElectronicCostPolicy,
    BankTaiwanInstrumentType,
    BankTaiwanLotType,
    BankTaiwanOrder,
    BankTaiwanSide,
)


LEGACY_RECOMMENDATION_COST_SCENARIO_ID = "legacy-fixed-round-trip-bp"
LEGACY_RECOMMENDATION_COST_SCENARIO_VERSION = "legacy-fixed-round-trip-bp-v1"
BANKTAIWAN_RECOMMENDATION_COST_SCENARIO_ID = "banktaiwan-electronic-estimate"
BANKTAIWAN_RECOMMENDATION_COST_SCENARIO_VERSION = (
    "banktaiwan-electronic-estimate-2026-v1"
)
BANKTAIWAN_DEFAULT_RESEARCH_ORDER_AMOUNT_TWD = "100000"
BANKTAIWAN_DEFAULT_POLICY_ESTIMATE_DATE = "2026-01-01"


class RecommendationCostScenarioError(ValueError):
    """成本情境 contract 不合法。"""


def _decimal(value: Decimal | int | str, *, field_name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise RecommendationCostScenarioError(f"{field_name} 不可為 bool 或 float")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RecommendationCostScenarioError(
            f"{field_name} 無法解析為 Decimal：{value!r}"
        ) from exc
    if not result.is_finite() or result <= 0:
        raise RecommendationCostScenarioError(f"{field_name} 必須是大於零的有限數值")
    return result


def _money_text(value: Decimal | int | str, *, field_name: str) -> str:
    return str(_decimal(value, field_name=field_name).quantize(Decimal("0.01")))


def _date_text(value: str | date, *, field_name: str) -> str:
    try:
        return (value if isinstance(value, date) else date.fromisoformat(str(value)[:10])).isoformat()
    except (TypeError, ValueError) as exc:
        raise RecommendationCostScenarioError(
            f"{field_name} 必須是 ISO 日期"
        ) from exc


@dataclass(frozen=True, slots=True)
class RecommendationCostScenario:
    """跨日期穩定的成本／研究 sizing contract。"""

    scenario_id: str
    scenario_version: str
    cost_basis: str
    fixed_round_trip_cost_bp: int | None = None
    policy_id: str | None = None
    policy_version: str | None = None
    policy_estimate_date: str | None = None
    research_order_amount_twd: str | Decimal | int | None = None
    research_order_quantity_shares: int | None = None
    lot_type: str | None = None
    instrument_type: str | None = None

    def __post_init__(self) -> None:
        if not str(self.scenario_id).strip() or not str(self.scenario_version).strip():
            raise RecommendationCostScenarioError("scenario id／version 不可為空")
        basis = str(self.cost_basis).strip()
        if basis not in {"fixed_round_trip_bp", "estimated_research_only"}:
            raise RecommendationCostScenarioError("不支援的 cost_basis")
        object.__setattr__(self, "cost_basis", basis)
        if basis == "fixed_round_trip_bp":
            if (
                isinstance(self.fixed_round_trip_cost_bp, bool)
                or not isinstance(self.fixed_round_trip_cost_bp, int)
                or self.fixed_round_trip_cost_bp < 0
            ):
                raise RecommendationCostScenarioError(
                    "fixed scenario 需要非負整數 fixed_round_trip_cost_bp"
                )
            if any(
                value is not None
                for value in (
                    self.policy_id,
                    self.policy_version,
                    self.policy_estimate_date,
                    self.research_order_amount_twd,
                    self.research_order_quantity_shares,
                    self.lot_type,
                    self.instrument_type,
                )
            ):
                raise RecommendationCostScenarioError(
                    "fixed scenario 不可混入臺銀 policy 或研究 sizing"
                )
            return

        if self.fixed_round_trip_cost_bp is not None:
            raise RecommendationCostScenarioError(
                "estimated scenario 不可帶 fixed_round_trip_cost_bp"
            )
        if self.policy_id != BANKTAIWAN_ELECTRONIC_COST_POLICY_ID:
            raise RecommendationCostScenarioError(
                "臺銀 scenario 必須綁定明確 policy_id"
            )
        if self.policy_version != BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION:
            raise RecommendationCostScenarioError(
                "臺銀 scenario policy_version 不受支援"
            )
        policy_date = _date_text(
            self.policy_estimate_date or BANKTAIWAN_DEFAULT_POLICY_ESTIMATE_DATE,
            field_name="policy_estimate_date",
        )
        # Select the version at construction time so an unavailable future or
        # historical policy cannot silently become a zero-cost observation.
        try:
            selected_version = BankTaiwanElectronicCostPolicy().select_version(policy_date)
        except (TypeError, ValueError) as exc:
            raise RecommendationCostScenarioError(
                f"臺銀 policy date 不可用：{policy_date}：{exc}"
            ) from exc
        if selected_version != self.policy_version:
            raise RecommendationCostScenarioError("臺銀 policy version selection mismatch")
        object.__setattr__(self, "policy_estimate_date", policy_date)

        has_amount = self.research_order_amount_twd is not None
        has_quantity = self.research_order_quantity_shares is not None
        if has_amount == has_quantity:
            raise RecommendationCostScenarioError(
                "臺銀 scenario 必須擇一提供研究訂單金額或股數"
            )
        if has_amount:
            object.__setattr__(
                self,
                "research_order_amount_twd",
                _money_text(
                    self.research_order_amount_twd,  # type: ignore[arg-type]
                    field_name="research_order_amount_twd",
                ),
            )
        if has_quantity:
            quantity = self.research_order_quantity_shares
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
                raise RecommendationCostScenarioError(
                    "research_order_quantity_shares 必須是正整數"
                )
            object.__setattr__(self, "research_order_quantity_shares", quantity)
        policy = BankTaiwanElectronicCostPolicy()
        try:
            normalized_lot = policy.normalize_lot_type(self.lot_type or "full_lot")
            normalized_instrument = policy.normalize_instrument_type(
                self.instrument_type or BankTaiwanInstrumentType.ORDINARY_STOCK.value
            )
        except ValueError as exc:
            raise RecommendationCostScenarioError(str(exc)) from exc
        object.__setattr__(self, "lot_type", normalized_lot)
        object.__setattr__(self, "instrument_type", normalized_instrument)
        if has_quantity:
            # Reuse the public order validator for the exact lot boundary.
            quantity = self.research_order_quantity_shares
            if not isinstance(quantity, int) or isinstance(quantity, bool):
                raise RecommendationCostScenarioError(
                    "research_order_quantity_shares 必須是正整數"
                )
            try:
                BankTaiwanOrder(
                    order_id="scenario-validation",
                    trade_date=policy_date,
                    side=BankTaiwanSide.BUY,
                    price=Decimal("1"),
                    quantity_shares=quantity,
                    lot_type=normalized_lot,
                    instrument_type=normalized_instrument,
                )
            except ValueError as exc:
                raise RecommendationCostScenarioError(str(exc)) from exc

    @property
    def is_estimated(self) -> bool:
        return self.cost_basis == "estimated_research_only"

    @property
    def scenario_hash(self) -> str:
        return _hash_payload(self.to_dict(include_hash=False))

    @property
    def contract_hash(self) -> str:
        """Alias used by candidate／capture contracts."""

        return self.scenario_hash

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "cost_basis": self.cost_basis,
            "fixed_round_trip_cost_bp": self.fixed_round_trip_cost_bp,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_estimate_date": self.policy_estimate_date,
            "research_order_amount_twd": (
                None
                if self.research_order_amount_twd is None
                else str(self.research_order_amount_twd)
            ),
            "research_order_quantity_shares": self.research_order_quantity_shares,
            "lot_type": self.lot_type,
            "instrument_type": self.instrument_type,
            "scope_key_semantics": (
                "stable_across_market_replay_dates; market_replay_date_is_observation_only"
            ),
            "estimated_research_only": self.is_estimated,
        }
        if self.is_estimated:
            payload["estimated_components"] = "commission_and_sell_tax"
            payload["liquidity_cost_role"] = (
                "diagnostic_only_not_in_fees_tax_only_label; missing_is_not_zero_observation"
            )
            payload["slippage"] = "not_modeled"
            payload["policy_metadata"] = BankTaiwanElectronicCostPolicy().metadata(
                lot_type=self.lot_type,
                instrument_type=self.instrument_type,
            )
        if include_hash:
            payload["scenario_hash"] = self.scenario_hash
        return payload

    def metadata(self) -> dict[str, Any]:
        """Return consumer／receipt-safe scenario metadata."""

        return self.to_dict(include_hash=True)


def build_legacy_cost_scenario(fixed_round_trip_cost_bp: int) -> RecommendationCostScenario:
    return RecommendationCostScenario(
        scenario_id=LEGACY_RECOMMENDATION_COST_SCENARIO_ID,
        scenario_version=LEGACY_RECOMMENDATION_COST_SCENARIO_VERSION,
        cost_basis="fixed_round_trip_bp",
        fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
    )


def build_banktaiwan_cost_scenario(
    *,
    policy_estimate_date: str = BANKTAIWAN_DEFAULT_POLICY_ESTIMATE_DATE,
    research_order_amount_twd: str | Decimal | int | None = None,
    research_order_quantity_shares: int | None = None,
    lot_type: str = BankTaiwanLotType.FULL_LOT.value,
    instrument_type: str = BankTaiwanInstrumentType.ORDINARY_STOCK.value,
) -> RecommendationCostScenario:
    if research_order_amount_twd is None and research_order_quantity_shares is None:
        research_order_amount_twd = BANKTAIWAN_DEFAULT_RESEARCH_ORDER_AMOUNT_TWD
    return RecommendationCostScenario(
        scenario_id=BANKTAIWAN_RECOMMENDATION_COST_SCENARIO_ID,
        scenario_version=BANKTAIWAN_RECOMMENDATION_COST_SCENARIO_VERSION,
        cost_basis="estimated_research_only",
        policy_id=BANKTAIWAN_ELECTRONIC_COST_POLICY_ID,
        policy_version=BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION,
        policy_estimate_date=policy_estimate_date,
        research_order_amount_twd=research_order_amount_twd,
        research_order_quantity_shares=research_order_quantity_shares,
        lot_type=lot_type,
        instrument_type=instrument_type,
    )


def normalize_cost_scenario(
    scenario: RecommendationCostScenario | Mapping[str, Any] | None,
    *,
    fixed_round_trip_cost_bp: int | None,
) -> RecommendationCostScenario:
    """Normalize a caller setting while retaining legacy call compatibility."""

    if scenario is None:
        if fixed_round_trip_cost_bp is None:
            raise RecommendationCostScenarioError(
                "未提供 scenario 時需要 fixed_round_trip_cost_bp"
            )
        return build_legacy_cost_scenario(fixed_round_trip_cost_bp)
    if isinstance(scenario, RecommendationCostScenario):
        if scenario.is_estimated and fixed_round_trip_cost_bp is not None:
            raise RecommendationCostScenarioError(
                "estimated scenario 不可與 fixed_round_trip_cost_bp 同時提供"
            )
        if (
            not scenario.is_estimated
            and fixed_round_trip_cost_bp is not None
            and scenario.fixed_round_trip_cost_bp != fixed_round_trip_cost_bp
        ):
            raise RecommendationCostScenarioError(
                "fixed cost 與 scenario fixed_round_trip_cost_bp 不一致"
            )
        return scenario
    if not isinstance(scenario, Mapping):
        raise RecommendationCostScenarioError("cost scenario 必須是 contract 或 mapping")
    basis = str(scenario.get("cost_basis") or "").strip()
    scenario_id = str(scenario.get("scenario_id") or "").strip()
    if not basis:
        raise RecommendationCostScenarioError("cost_basis 不可省略")
    if basis not in {"fixed_round_trip_bp", "estimated_research_only"}:
        raise RecommendationCostScenarioError(f"不支援的 cost_basis：{basis}")
    if basis == "fixed_round_trip_bp" or scenario_id == LEGACY_RECOMMENDATION_COST_SCENARIO_ID:
        if basis != "fixed_round_trip_bp" or (
            scenario_id and scenario_id != LEGACY_RECOMMENDATION_COST_SCENARIO_ID
        ):
            raise RecommendationCostScenarioError("legacy cost scenario identity 不一致")
        if any(
            scenario.get(key) not in (None, "")
            for key in (
                "policy_id",
                "policy_version",
                "policy_estimate_date",
                "research_order_amount_twd",
                "research_order_quantity_shares",
                "lot_type",
                "instrument_type",
            )
        ):
            raise RecommendationCostScenarioError(
                "legacy scenario 不可混入臺銀 policy 或研究 sizing"
            )
        fixed = scenario.get("fixed_round_trip_cost_bp", fixed_round_trip_cost_bp)
        if isinstance(fixed, bool) or not isinstance(fixed, int) or fixed < 0:
            raise RecommendationCostScenarioError("legacy fixed cost 必須是整數")
        normalized = build_legacy_cost_scenario(fixed)
        declared_version = scenario.get("scenario_version")
        if declared_version not in (None, "", normalized.scenario_version):
            raise RecommendationCostScenarioError("legacy scenario version mismatch")
        declared_hash = scenario.get("cost_scenario_hash", scenario.get("scenario_hash"))
        if declared_hash not in (None, "") and str(declared_hash) != normalized.scenario_hash:
            raise RecommendationCostScenarioError("legacy scenario hash mismatch")
        return normalized
    if scenario_id != BANKTAIWAN_RECOMMENDATION_COST_SCENARIO_ID:
        raise RecommendationCostScenarioError("不支援的 estimated cost scenario id")
    if scenario.get("fixed_round_trip_cost_bp") is not None:
        raise RecommendationCostScenarioError(
            "estimated mapping 不可混入 fixed_round_trip_cost_bp"
        )
    quantity_value = scenario.get("research_order_quantity_shares")
    if quantity_value is not None and (
        isinstance(quantity_value, bool)
        or not isinstance(quantity_value, int)
    ):
        raise RecommendationCostScenarioError(
            "research_order_quantity_shares 必須保留為整數，不可先轉型"
        )
    normalized = RecommendationCostScenario(
        scenario_id=scenario_id,
        scenario_version=str(
            scenario.get("scenario_version") or BANKTAIWAN_RECOMMENDATION_COST_SCENARIO_VERSION
        ),
        cost_basis="estimated_research_only",
        fixed_round_trip_cost_bp=None,
        policy_id=str(scenario.get("policy_id") or BANKTAIWAN_ELECTRONIC_COST_POLICY_ID),
        policy_version=str(
            scenario.get("policy_version") or BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION
        ),
        policy_estimate_date=str(
            scenario.get("policy_estimate_date") or BANKTAIWAN_DEFAULT_POLICY_ESTIMATE_DATE
        ),
        research_order_amount_twd=scenario.get("research_order_amount_twd"),
        research_order_quantity_shares=quantity_value,
        lot_type=str(scenario.get("lot_type") or BankTaiwanLotType.FULL_LOT.value),
        instrument_type=str(
            scenario.get("instrument_type")
            or BankTaiwanInstrumentType.ORDINARY_STOCK.value
        ),
    )
    declared_hash = scenario.get("cost_scenario_hash", scenario.get("scenario_hash"))
    if declared_hash not in (None, "") and str(declared_hash) != normalized.scenario_hash:
        raise RecommendationCostScenarioError("estimated scenario hash mismatch")
    return normalized


def cost_scenario_from_metadata(
    metadata: Mapping[str, Any],
    *,
    fixed_round_trip_cost_bp: int | None = None,
) -> RecommendationCostScenario:
    """Reconstruct and verify the scenario declared by a candidate/receipt."""

    scenario_value = metadata.get("cost_scenario")
    if isinstance(scenario_value, Mapping):
        scenario = normalize_cost_scenario(
            scenario_value,
            fixed_round_trip_cost_bp=(
                fixed_round_trip_cost_bp
                if fixed_round_trip_cost_bp is not None
                else _optional_int(metadata.get("fixed_round_trip_cost_bp"))
            ),
        )
        nested_hash = scenario_value.get("scenario_hash")
        if nested_hash not in (None, "") and str(nested_hash) != scenario.scenario_hash:
            raise RecommendationCostScenarioError("nested cost scenario hash mismatch")
    elif metadata.get("cost_scenario_id"):
        scenario = normalize_cost_scenario(
            {
                "scenario_id": metadata.get("cost_scenario_id"),
                "scenario_version": metadata.get("cost_scenario_version"),
                "cost_basis": metadata.get("cost_basis"),
                "fixed_round_trip_cost_bp": metadata.get("fixed_round_trip_cost_bp"),
                "policy_id": metadata.get("cost_policy_id") or metadata.get("policy_id"),
                "policy_version": metadata.get("cost_policy_version") or metadata.get("policy_version"),
                "policy_estimate_date": metadata.get("policy_estimate_date"),
                "research_order_amount_twd": metadata.get("research_order_amount_twd"),
                "research_order_quantity_shares": metadata.get("research_order_quantity_shares"),
                "lot_type": metadata.get("lot_type"),
                "instrument_type": metadata.get("instrument_type"),
            },
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        )
    else:
        legacy_fixed = _optional_int(
            metadata.get(
                "fixed_round_trip_cost_bp",
                fixed_round_trip_cost_bp,
            )
        )
        scenario = build_legacy_cost_scenario(
            legacy_fixed if legacy_fixed is not None else 50
        )
    declared_hash = metadata.get("cost_scenario_hash")
    if declared_hash not in (None, "") and str(declared_hash) != scenario.scenario_hash:
        raise RecommendationCostScenarioError("cost scenario hash mismatch")
    return scenario


@dataclass(frozen=True, slots=True)
class RecommendationCostEstimate:
    """一筆買賣成本 observation；unavailable 不提供虛假的零金額。"""

    scenario_id: str
    scenario_version: str
    scenario_hash: str
    cost_basis: str
    market_replay_date: str
    policy_estimate_date: str | None
    buy_price_twd: str | None
    sell_price_twd: str | None
    research_order_amount_twd: str | None
    research_order_quantity_shares: int | None
    estimated_buy_cost_twd: str | None
    estimated_sell_cost_twd: str | None
    estimated_round_trip_cost_twd: str | None
    estimated_round_trip_cost_bp: int | None
    gross_buy_amount_twd: str | None
    gross_sell_amount_twd: str | None
    net_profit_twd: str | None
    net_profit_label: int | None
    status: str
    diagnostics: tuple[str, ...] = ()
    buy_estimate: Mapping[str, Any] | None = None
    sell_estimate: Mapping[str, Any] | None = None

    @property
    def available(self) -> bool:
        return self.status == "estimated" and self.estimated_round_trip_cost_bp is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cost_scenario_id": self.scenario_id,
            "cost_scenario_version": self.scenario_version,
            "cost_scenario_hash": self.scenario_hash,
            "cost_basis": self.cost_basis,
            "market_replay_date": self.market_replay_date,
            "policy_estimate_date": self.policy_estimate_date,
            "buy_price_twd": self.buy_price_twd,
            "sell_price_twd": self.sell_price_twd,
            "research_order_amount_twd": self.research_order_amount_twd,
            "research_order_quantity_shares": self.research_order_quantity_shares,
            "estimated_buy_cost_twd": self.estimated_buy_cost_twd,
            "estimated_sell_cost_twd": self.estimated_sell_cost_twd,
            "estimated_round_trip_cost_twd": self.estimated_round_trip_cost_twd,
            "estimated_round_trip_cost_bp": self.estimated_round_trip_cost_bp,
            "gross_buy_amount_twd": self.gross_buy_amount_twd,
            "gross_sell_amount_twd": self.gross_sell_amount_twd,
            "net_profit_twd": self.net_profit_twd,
            "net_profit_label": self.net_profit_label,
            "cost_estimate_status": self.status,
            "cost_estimate_diagnostics": list(self.diagnostics),
            "buy_cost_estimate": dict(self.buy_estimate) if self.buy_estimate else None,
            "sell_cost_estimate": dict(self.sell_estimate) if self.sell_estimate else None,
        }

    def sample_metadata(self) -> dict[str, Any]:
        return self.to_dict()


def estimate_round_trip_cost(
    scenario: RecommendationCostScenario,
    *,
    market_replay_date: str | date,
    buy_price_twd: Decimal | int | str | None,
    sell_price_twd: Decimal | int | str | None,
) -> RecommendationCostEstimate:
    """Estimate a buy+sell round trip for one matured observation."""

    market_date = _date_text(market_replay_date, field_name="market_replay_date")
    if not scenario.is_estimated:
        fixed = scenario.fixed_round_trip_cost_bp
        return RecommendationCostEstimate(
            scenario_id=scenario.scenario_id,
            scenario_version=scenario.scenario_version,
            scenario_hash=scenario.scenario_hash,
            cost_basis=scenario.cost_basis,
            market_replay_date=market_date,
            policy_estimate_date=None,
            buy_price_twd=None,
            sell_price_twd=None,
            research_order_amount_twd=None,
            research_order_quantity_shares=None,
            estimated_buy_cost_twd=None,
            estimated_sell_cost_twd=None,
            estimated_round_trip_cost_twd=None,
            estimated_round_trip_cost_bp=fixed,
            gross_buy_amount_twd=None,
            gross_sell_amount_twd=None,
            net_profit_twd=None,
            net_profit_label=None,
            status="fixed_assumption",
            diagnostics=("legacy_fixed_round_trip_cost_contract",),
        )

    buy_price: Decimal | None = None
    sell_price: Decimal | None = None
    try:
        buy_price = _decimal(buy_price_twd, field_name="buy_price_twd") if buy_price_twd is not None else None
        sell_price = _decimal(sell_price_twd, field_name="sell_price_twd") if sell_price_twd is not None else None
    except RecommendationCostScenarioError as exc:
        return _unavailable_estimate(
            scenario,
            market_date,
            f"invalid_price:{exc}",
            buy_price_twd=buy_price,
            sell_price_twd=sell_price,
        )
    if buy_price is None or sell_price is None:
        return _unavailable_estimate(
            scenario,
            market_date,
            "buy_or_sell_price_missing",
            buy_price_twd=buy_price,
            sell_price_twd=sell_price,
        )
    try:
        quantity = _quantity_for_scenario(scenario, buy_price)
    except RecommendationCostScenarioError as exc:
        return _unavailable_estimate(
            scenario,
            market_date,
            f"quantity_unavailable:{exc}",
            buy_price_twd=buy_price,
            sell_price_twd=sell_price,
        )
    if quantity <= 0:
        return _unavailable_estimate(
            scenario,
            market_date,
            "research_order_amount_cannot_buy_one_valid_order",
            buy_price_twd=buy_price,
            sell_price_twd=sell_price,
        )
    policy = BankTaiwanElectronicCostPolicy()
    try:
        # The policy date intentionally differs from market_replay_date when
        # replaying pre-2026 observations: this is a declared counterfactual,
        # never a claim about the historical broker fee actually charged then.
        buy_order = BankTaiwanOrder(
            order_id=f"{scenario.scenario_hash[:24]}:{market_date}:buy",
            trade_date=str(scenario.policy_estimate_date),
            side=BankTaiwanSide.BUY,
            price=buy_price,
            quantity_shares=quantity,
            lot_type=str(scenario.lot_type),
            instrument_type=str(scenario.instrument_type),
        )
        sell_order = BankTaiwanOrder(
            order_id=f"{scenario.scenario_hash[:24]}:{market_date}:sell",
            trade_date=str(scenario.policy_estimate_date),
            side=BankTaiwanSide.SELL,
            price=sell_price,
            quantity_shares=quantity,
            lot_type=str(scenario.lot_type),
            instrument_type=str(scenario.instrument_type),
        )
        buy = policy.estimate(buy_order)
        sell = policy.estimate(sell_order)
    except (TypeError, ValueError) as exc:
        return _unavailable_estimate(
            scenario,
            market_date,
            f"policy_estimate_failed:{exc}",
            buy_price_twd=buy_price,
            sell_price_twd=sell_price,
        )
    round_trip = buy.total_cost + sell.total_cost
    gross_reference = buy.gross_amount
    if gross_reference <= 0:
        return _unavailable_estimate(
            scenario,
            market_date,
            "buy_gross_reference_missing",
            buy_price_twd=buy_price,
            sell_price_twd=sell_price,
        )
    round_trip_bp = int(
        ((round_trip / gross_reference) * Decimal("10000")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    net_profit = sell.gross_amount - buy.gross_amount - round_trip
    diagnostics = [
        "estimated_research_only",
        "broker_fill_not_observed",
        "slippage_not_modeled",
    ]
    if market_date != scenario.policy_estimate_date:
        diagnostics.append("policy_date_is_explicit_counterfactual_for_market_replay")
    return RecommendationCostEstimate(
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        scenario_hash=scenario.scenario_hash,
        cost_basis=scenario.cost_basis,
        market_replay_date=market_date,
        policy_estimate_date=scenario.policy_estimate_date,
        buy_price_twd=str(buy_price),
        sell_price_twd=str(sell_price),
        research_order_amount_twd=(
            str(scenario.research_order_amount_twd)
            if scenario.research_order_amount_twd is not None
            else None
        ),
        research_order_quantity_shares=quantity,
        estimated_buy_cost_twd=str(buy.total_cost),
        estimated_sell_cost_twd=str(sell.total_cost),
        estimated_round_trip_cost_twd=str(round_trip),
        estimated_round_trip_cost_bp=round_trip_bp,
        gross_buy_amount_twd=str(buy.gross_amount),
        gross_sell_amount_twd=str(sell.gross_amount),
        net_profit_twd=str(net_profit),
        net_profit_label=int(net_profit > 0),
        status="estimated",
        diagnostics=tuple(diagnostics),
        buy_estimate=buy.to_dict(),
        sell_estimate=sell.to_dict(),
    )


def verify_estimated_cost_observation(
    scenario: RecommendationCostScenario,
    observation: Mapping[str, Any],
    *,
    expected_market_replay_date: str | date,
) -> RecommendationCostEstimate:
    """Recompute and verify one durable estimated-cost observation.

    Natural evidence is an input to promotion authority, not an authority for
    its own fee/tax numbers.  The comparison must therefore carry the typed
    source prices and resolved order quantity whenever a fee/tax estimate is
    available, so this helper can rerun the versioned policy.  A legitimate
    unavailable observation may explicitly omit a missing price, but it must
    carry no cost or label.  The helper rejects floating-point monetary inputs
    and checks both the minimum-fee and tax outputs returned by the policy,
    rather than trusting producer-supplied cost fields.
    """

    if not scenario.is_estimated:
        raise RecommendationCostScenarioError(
            "estimated cost observation requires an estimated research scenario"
        )
    market_date = _date_text(
        expected_market_replay_date,
        field_name="expected_market_replay_date",
    )
    declared_market_date = _date_text(
        str(observation.get("market_replay_date") or ""),
        field_name="market_replay_date",
    )
    if declared_market_date != market_date:
        raise RecommendationCostScenarioError(
            "market_replay_date does not match the capture-bound outcome date"
        )
    buy_price = _optional_decimal_text(observation.get("buy_price_twd"), "buy_price_twd")
    sell_price = _optional_decimal_text(observation.get("sell_price_twd"), "sell_price_twd")
    estimate = estimate_round_trip_cost(
        scenario,
        market_replay_date=market_date,
        buy_price_twd=buy_price,
        sell_price_twd=sell_price,
    )

    expected_identity: dict[str, Any] = {
        "cost_scenario_id": scenario.scenario_id,
        "cost_scenario_version": scenario.scenario_version,
        "cost_scenario_hash": scenario.scenario_hash,
        "cost_basis": scenario.cost_basis,
        "cost_policy_id": scenario.policy_id,
        "cost_policy_version": scenario.policy_version,
        "policy_estimate_date": scenario.policy_estimate_date,
        "lot_type": scenario.lot_type,
        "instrument_type": scenario.instrument_type,
    }
    for field_name, expected in expected_identity.items():
        if observation.get(field_name) != expected:
            raise RecommendationCostScenarioError(
                f"estimated cost observation identity mismatch: {field_name}"
            )
    _require_money_equal(
        observation.get("research_order_amount_twd"),
        scenario.research_order_amount_twd,
        "research_order_amount_twd",
    )
    declared_quantity = observation.get("research_order_quantity_shares")
    if estimate.research_order_quantity_shares is None:
        if declared_quantity is not None:
            raise RecommendationCostScenarioError(
                "estimated cost observation quantity must be unavailable"
            )
    elif (
        isinstance(declared_quantity, bool)
        or not isinstance(declared_quantity, int)
        or declared_quantity != estimate.research_order_quantity_shares
    ):
        raise RecommendationCostScenarioError(
            "estimated cost observation quantity does not match policy sizing"
        )

    if estimate.status != str(observation.get("cost_estimate_status") or ""):
        raise RecommendationCostScenarioError(
            "estimated cost observation status does not match policy result"
        )
    declared_cost_fields = (
        ("estimated_buy_cost_twd", estimate.estimated_buy_cost_twd),
        ("estimated_sell_cost_twd", estimate.estimated_sell_cost_twd),
        ("estimated_round_trip_cost_twd", estimate.estimated_round_trip_cost_twd),
        ("gross_buy_amount_twd", estimate.gross_buy_amount_twd),
        ("gross_sell_amount_twd", estimate.gross_sell_amount_twd),
        ("net_profit_twd", estimate.net_profit_twd),
    )
    for field_name, expected in declared_cost_fields:
        _require_money_equal(observation.get(field_name), expected, field_name)
    declared_bp = observation.get("estimated_round_trip_cost_bp")
    if estimate.estimated_round_trip_cost_bp is None:
        if declared_bp is not None:
            raise RecommendationCostScenarioError(
                "estimated round-trip cost bp must be unavailable"
            )
    elif (
        isinstance(declared_bp, bool)
        or not isinstance(declared_bp, int)
        or declared_bp != estimate.estimated_round_trip_cost_bp
    ):
        raise RecommendationCostScenarioError(
            "estimated round-trip cost bp does not match policy result"
        )
    declared_label = observation.get("after_cost_profit_label")
    expected_label = estimate.net_profit_label
    if declared_label != expected_label:
        raise RecommendationCostScenarioError(
            "estimated after-cost label does not match policy net profit"
        )
    return estimate


def _quantity_for_scenario(scenario: RecommendationCostScenario, buy_price: Decimal) -> int:
    if scenario.research_order_quantity_shares is not None:
        return int(scenario.research_order_quantity_shares)
    if scenario.research_order_amount_twd is None:
        raise RecommendationCostScenarioError("研究 sizing 缺失")
    raw = (Decimal(str(scenario.research_order_amount_twd)) / buy_price).to_integral_value(
        rounding=ROUND_DOWN
    )
    quantity = int(raw)
    if scenario.lot_type == BankTaiwanLotType.FULL_LOT.value:
        return (quantity // 1000) * 1000
    return min(quantity, 999)


def _unavailable_estimate(
    scenario: RecommendationCostScenario,
    market_date: str,
    diagnostic: str,
    *,
    buy_price_twd: Decimal | None = None,
    sell_price_twd: Decimal | None = None,
) -> RecommendationCostEstimate:
    return RecommendationCostEstimate(
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        scenario_hash=scenario.scenario_hash,
        cost_basis=scenario.cost_basis,
        market_replay_date=market_date,
        policy_estimate_date=scenario.policy_estimate_date,
        # Preserve any validated source price even when sizing/policy inputs
        # make the estimate unavailable; this keeps the unavailable branch
        # auditable without turning it into a zero-cost label.
        buy_price_twd=str(buy_price_twd) if buy_price_twd is not None else None,
        sell_price_twd=str(sell_price_twd) if sell_price_twd is not None else None,
        research_order_amount_twd=(
            str(scenario.research_order_amount_twd)
            if scenario.research_order_amount_twd is not None
            else None
        ),
        research_order_quantity_shares=scenario.research_order_quantity_shares,
        estimated_buy_cost_twd=None,
        estimated_sell_cost_twd=None,
        estimated_round_trip_cost_twd=None,
        estimated_round_trip_cost_bp=None,
        gross_buy_amount_twd=None,
        gross_sell_amount_twd=None,
        net_profit_twd=None,
        net_profit_label=None,
        status="unavailable",
        diagnostics=(diagnostic,),
    )


def _optional_decimal_text(value: Any, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (bool, float)):
        raise RecommendationCostScenarioError(
            f"{field_name} 必須以 Decimal-safe text/整數提供"
        )
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RecommendationCostScenarioError(
            f"{field_name} 無法解析為 Decimal"
        ) from exc
    if not parsed.is_finite() or parsed <= 0:
        raise RecommendationCostScenarioError(
            f"{field_name} 必須是大於零的有限數值"
        )
    return parsed


def _require_money_equal(actual: Any, expected: Decimal | int | str | None, field_name: str) -> None:
    if expected is None:
        if actual is not None:
            raise RecommendationCostScenarioError(
                f"{field_name} 應為 unavailable"
            )
        return
    if actual is None or isinstance(actual, (bool, float)):
        raise RecommendationCostScenarioError(f"{field_name} 缺少 Decimal-safe 值")
    try:
        actual_decimal = Decimal(str(actual))
        expected_decimal = Decimal(str(expected))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RecommendationCostScenarioError(
            f"{field_name} 無法解析為 Decimal"
        ) from exc
    if (
        not actual_decimal.is_finite()
        or (
            field_name
            in {
                "estimated_buy_cost_twd",
                "estimated_sell_cost_twd",
                "estimated_round_trip_cost_twd",
            }
            and actual_decimal < 0
        )
        or actual_decimal != expected_decimal
    ):
        raise RecommendationCostScenarioError(
            f"{field_name} 不符合 versioned policy 重算值"
        )


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hash_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "BANKTAIWAN_DEFAULT_POLICY_ESTIMATE_DATE",
    "BANKTAIWAN_DEFAULT_RESEARCH_ORDER_AMOUNT_TWD",
    "BANKTAIWAN_RECOMMENDATION_COST_SCENARIO_ID",
    "BANKTAIWAN_RECOMMENDATION_COST_SCENARIO_VERSION",
    "LEGACY_RECOMMENDATION_COST_SCENARIO_ID",
    "LEGACY_RECOMMENDATION_COST_SCENARIO_VERSION",
    "RecommendationCostEstimate",
    "RecommendationCostScenario",
    "RecommendationCostScenarioError",
    "build_banktaiwan_cost_scenario",
    "build_legacy_cost_scenario",
    "cost_scenario_from_metadata",
    "estimate_round_trip_cost",
    "normalize_cost_scenario",
    "verify_estimated_cost_observation",
]
