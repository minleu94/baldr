from __future__ import annotations

from dataclasses import dataclass
from app_module.advice_dtos import AdviceAction, AdviceMode, AdvicePolicyConfig


@dataclass(frozen=True)
class AdvicePolicyDecision:
    action: AdviceAction
    reasons: tuple[str, ...] = ()


class AdvicePolicy:
    """以策略資格與市場證據產生研究建議；不以帳戶預算決定策略是否顯示。"""

    def __init__(self, config: AdvicePolicyConfig | None = None) -> None:
        self._config = config or AdvicePolicyConfig()

    def decide(
        self,
        *,
        mode: AdviceMode,
        strategy_status: str | None,
        data_quality: str | None = None,
        execution_feasible: bool | None = None,
        risk_budget_available: bool | None = None,
        current_position_count: int | None = None,
        cash_reserve_bp: int | None = None,
        target_weight_bp: int | None = None,
        parameters_locked: bool | None = None,
        disclosure_complete: bool | None = None,
        strategy_advice_contract_verified: bool | None = None,
    ) -> AdvicePolicyDecision:
        """只判斷策略資格與輸入品質；帳戶欄位保留相容但不參與策略 action。"""
        if not isinstance(mode, AdviceMode) or not isinstance(self._config.mode, AdviceMode):
            return AdvicePolicyDecision(AdviceAction.NO_NEW_POSITION, ("invalid_mode",))
        if mode is not self._config.mode:
            return AdvicePolicyDecision(AdviceAction.NO_NEW_POSITION, ("mode_config_mismatch",))
        strategy_reasons = self._strategy_reasons(
            mode,
            strategy_status,
            parameters_locked=parameters_locked,
            disclosure_complete=disclosure_complete,
            strategy_advice_contract_verified=strategy_advice_contract_verified,
        )

        quality_decision = self._quality_decision(data_quality)
        if quality_decision is not None:
            return AdvicePolicyDecision(
                quality_decision.action,
                tuple(dict.fromkeys((*strategy_reasons, *quality_decision.reasons))),
            )

        if execution_feasible is False:
            return AdvicePolicyDecision(
                AdviceAction.AVOID,
                tuple(dict.fromkeys((*strategy_reasons, "execution_not_feasible"))),
            )
        # risk_budget／current positions／cash／target weight 屬於可選的
        # Portfolio sizing；不得把它們套成策略 Advice 的帳戶前置條件。
        return AdvicePolicyDecision(AdviceAction.ADD_CANDIDATE, strategy_reasons)

    @staticmethod
    def _strategy_reasons(
        mode: AdviceMode,
        strategy_status: str | None,
        *,
        parameters_locked: bool | None,
        disclosure_complete: bool | None,
        strategy_advice_contract_verified: bool | None,
    ) -> tuple[str, ...]:
        """回報策略生命週期限制，但不以升格／作者文件阻擋人工 Advice。"""

        del mode  # Guided／Professional 都是 Advice 使用方式，不是交易權限。
        reasons: list[str] = []
        if strategy_status != "promoted":
            reasons.append("strategy_lifecycle_not_qualified")
        if parameters_locked is False:
            reasons.append("strategy_parameters_not_locked")
        if disclosure_complete is False:
            reasons.append("strategy_disclosure_incomplete")
        if strategy_advice_contract_verified is False:
            reasons.append("strategy_advice_contract_missing_or_unverified")
        return tuple(reasons)

    @staticmethod
    def _quality_decision(data_quality: str | None) -> AdvicePolicyDecision | None:
        if data_quality is None:
            return AdvicePolicyDecision(AdviceAction.RESEARCH, ("data_quality_missing",))
        if data_quality == "OBSERVED":
            return None
        if data_quality == "DEGRADED":
            return AdvicePolicyDecision(AdviceAction.RESEARCH, ("data_quality_degraded",))
        return AdvicePolicyDecision(AdviceAction.RESEARCH, ("data_quality_not_observed",))
