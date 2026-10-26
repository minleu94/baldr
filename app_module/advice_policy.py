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
        strategy_decision = self._strategy_decision(
            mode,
            strategy_status,
            parameters_locked=parameters_locked,
            disclosure_complete=disclosure_complete,
        )
        if strategy_decision is not None:
            return strategy_decision

        quality_decision = self._quality_decision(data_quality)
        if quality_decision is not None:
            return quality_decision

        if execution_feasible is False:
            return AdvicePolicyDecision(AdviceAction.AVOID, ("execution_not_feasible",))
        if (
            mode is AdviceMode.GUIDED
            and strategy_advice_contract_verified is not True
        ):
            return AdvicePolicyDecision(
                AdviceAction.NO_NEW_POSITION,
                ("guided_mode_strategy_advice_contract_missing_or_unverified",),
            )
        # risk_budget／current positions／cash／target weight 屬於可選的
        # Portfolio sizing；不得把它們套成策略 Advice 的帳戶前置條件。
        return AdvicePolicyDecision(AdviceAction.ADD_CANDIDATE)

    @staticmethod
    def _strategy_decision(
        mode: AdviceMode,
        strategy_status: str | None,
        *,
        parameters_locked: bool | None,
        disclosure_complete: bool | None,
    ) -> AdvicePolicyDecision | None:
        if mode is AdviceMode.GUIDED:
            if strategy_status != "promoted":
                return AdvicePolicyDecision(
                    AdviceAction.NO_NEW_POSITION,
                    ("guided_mode_strategy_not_promoted",),
                )
            if parameters_locked is not True:
                return AdvicePolicyDecision(
                    AdviceAction.NO_NEW_POSITION,
                    ("guided_mode_strategy_parameters_not_locked",),
                )
            if disclosure_complete is not True:
                return AdvicePolicyDecision(
                    AdviceAction.NO_NEW_POSITION,
                    ("guided_mode_strategy_disclosure_incomplete",),
                )
            return None
        if strategy_status == "promoted":
            return None
        if strategy_status == "candidate":
            return AdvicePolicyDecision(
                AdviceAction.RESEARCH,
                ("professional_candidate_research_only",),
            )
        return AdvicePolicyDecision(AdviceAction.RESEARCH, ("strategy_status_not_promoted",))

    @staticmethod
    def _quality_decision(data_quality: str | None) -> AdvicePolicyDecision | None:
        if data_quality is None:
            return AdvicePolicyDecision(AdviceAction.RESEARCH, ("data_quality_missing",))
        if data_quality == "OBSERVED":
            return None
        if data_quality == "DEGRADED":
            return AdvicePolicyDecision(AdviceAction.RESEARCH, ("data_quality_degraded",))
        return AdvicePolicyDecision(AdviceAction.RESEARCH, ("data_quality_not_observed",))
