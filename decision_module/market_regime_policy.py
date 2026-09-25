"""純市場狀態轉移政策與暫時計算結果契約。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegimeTransition:
    """一次 regime 評估的輸入候選、輸出值與持久化決策。"""

    transition_date: str | None
    candidate_regime: str
    effective_regime: str
    prior_regime: str | None
    persist_candidate: bool
    outcome: str


@dataclass(frozen=True, slots=True)
class RegimeAssessment:
    """純 detector 結果；不包含來源讀取或持久化副作用。"""

    regime: str
    confidence: float
    details: Mapping[str, object]
    transition: RegimeTransition


def transition_regime(
    candidate_regime: str,
    transition_date: str,
    prior_history: Mapping[str, object],
    *,
    min_confirm_days: int = 2,
    cooldown_days: int = 3,
) -> RegimeTransition:
    """沿用既有日期排序、兩日確認與 cooldown 規則，回傳明示轉移。

    ``prior_history`` 使用既有 history entry 形狀（每個日期對應帶有
    ``regime`` 欄位的 mapping），但只讀取日期與 regime，不修改輸入。
    持久化時間戳仍由 app adapter 產生。
    """

    sorted_history = sorted(
        (
            (history_date, history_entry)
            for history_date, history_entry in prior_history.items()
            if history_date < transition_date
        ),
        reverse=True,
    )
    if not sorted_history:
        return RegimeTransition(
            transition_date=transition_date,
            candidate_regime=candidate_regime,
            effective_regime=candidate_regime,
            prior_regime=None,
            persist_candidate=True,
            outcome="initial",
        )

    recent: list[tuple[str, str]] = []
    for history_date, history_entry in sorted_history[: min_confirm_days + cooldown_days]:
        if not isinstance(history_entry, Mapping):
            raise TypeError(f"regime history entry 必須是 mapping: {history_date}")
        regime = history_entry.get("regime")
        if not isinstance(regime, str):
            raise TypeError(f"regime history regime 必須是字串: {history_date}")
        recent.append((history_date, regime))
    last_regime = recent[0][1]

    if len(recent) >= cooldown_days:
        for index in range(min(cooldown_days, len(recent) - 1)):
            if recent[index][1] != recent[index + 1][1]:
                if recent[0][1] != candidate_regime:
                    return RegimeTransition(
                        transition_date=transition_date,
                        candidate_regime=candidate_regime,
                        effective_regime=last_regime,
                        prior_regime=last_regime,
                        persist_candidate=False,
                        outcome="cooldown_suppressed",
                    )
                break

    if last_regime != candidate_regime:
        if len(recent) >= 2 and recent[1][1] == candidate_regime:
            return RegimeTransition(
                transition_date=transition_date,
                candidate_regime=candidate_regime,
                effective_regime=candidate_regime,
                prior_regime=last_regime,
                persist_candidate=True,
                outcome="confirmed",
            )
        return RegimeTransition(
            transition_date=transition_date,
            candidate_regime=candidate_regime,
            effective_regime=last_regime,
            prior_regime=last_regime,
            persist_candidate=True,
            outcome="candidate_pending",
        )

    return RegimeTransition(
        transition_date=transition_date,
        candidate_regime=candidate_regime,
        effective_regime=candidate_regime,
        prior_regime=last_regime,
        persist_candidate=True,
        outcome="stable",
    )


__all__ = ["RegimeAssessment", "RegimeTransition", "transition_regime"]
