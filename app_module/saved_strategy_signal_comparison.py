"""原保存策略的逐日進場意圖對照；不重算訊號、撮合或績效。"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import json
from typing import Callable, Sequence

from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_service import ResearchRunService, ResearchRunServiceError, ResearchRunReadCancelledError
from app_module.saved_strategy_rule_card import SavedStrategyRuleCard, load_saved_strategy_rule_card
from app_module.strategy_signal_context import validate_strategy_signal_context

FAMILIES = {
    "baseline_score_threshold": ("1.1.0", "score", "綜合計分"),
    "stable_conservative_v1": ("1.1.0", "score", "綜合計分"),
    "momentum_aggressive_v1": ("1.1.0", "score", "綜合計分"),
    "baldr_bollinger_basic_v1": ("1.0.0", "bollinger", "布林"),
    "baldr_bollinger_squeeze_v1": ("1.0.0", "bollinger", "布林"),
    "baldr_w_bottom_basic_v1": ("1.0.0", "pattern", "形態"),
    "baldr_ma_alignment_basic_v1": ("1.0.0", "trend", "趨勢"),
    "baldr_vcp_three_contractions_v1": ("1.0.0", "vcp", "轉折收縮"),
}


@dataclass(frozen=True)
class SavedSignalStrategy:
    run_id: str
    run_name: str
    strategy_id: str
    strategy_version: str
    family_id: str
    family_label: str
    rule_source: SavedStrategyRuleCard


@dataclass(frozen=True)
class SavedStrategySignal:
    state: str
    signal: int
    reason: str


@dataclass(frozen=True)
class SavedSignalComparisonDay:
    data_date: str
    signals: tuple[SavedStrategySignal, ...]
    common_entry_state: str
    matching_strategy_count: int
    matching_family_count: int


@dataclass(frozen=True)
class SavedSignalComparison:
    state: str
    reasons: tuple[str, ...] = ()
    strategies: tuple[SavedSignalStrategy, ...] = ()
    rows: tuple[SavedSignalComparisonDay, ...] = ()
    stock_code: str = ""
    requested_start: str = ""
    requested_end: str = ""
    input_sha256: str = ""
    historical_pit_eligible: bool = False
    performance_evaluable: bool = False


def _comparison_day(when: str, strategies: Sequence[SavedSignalStrategy], signals: tuple[SavedStrategySignal, ...]) -> SavedSignalComparisonDay:
    state = ("no_match" if any(signal.state == "no_match" for signal in signals) else
        "unknown" if any(signal.state == "unknown" for signal in signals) else "match")
    matches = [strategy for strategy, signal in zip(strategies, signals) if signal.state == "match"]
    return SavedSignalComparisonDay(when, signals, state, len(matches), len({strategy.family_id for strategy in matches}))


def read_saved_strategy_signal_comparison(service: ResearchRunService,
    selected: Sequence[ResearchRunMetadataDTO], *, check_cancel: Callable[[], bool] | None = None) -> SavedSignalComparison:
    """明選2至5筆；每筆只沿原完整性port載入一次，缺件／混源整組拒對照。"""
    def cancel() -> None:
        if check_cancel is not None and check_cancel():
            raise InterruptedError("策略訊號對照已取消")

    cancel()
    if not 2 <= len(selected) <= 5:
        return SavedSignalComparison("unavailable", ("請選2至5筆已保存的不同單股策略",))
    runs = tuple(deepcopy(run) for run in selected)
    if len({run.run_id for run in runs}) != len(runs) or len({run.strategy_id for run in runs}) != len(runs):
        return SavedSignalComparison("unavailable", ("同一策略只能選一個版本／參數run，不能以重複配置增加策略數",))
    strategies: list[SavedSignalStrategy] = []
    histories: list[dict[str, SavedStrategySignal]] = []
    common = None
    active = ""
    try:
        for run in runs:
            cancel()
            active = run.run_id
            family = FAMILIES.get(run.strategy_id)
            if (run.run_type != "single_backtest" or len(run.universe) != 1 or family is None
                    or run.strategy_version != family[0]):
                raise ValueError("此功能只讀已支援的具名單股策略版本；批次逐股與推薦回放另沿原入口")
            card = load_saved_strategy_rule_card(service, run, max_artifact_bytes=16 * 1024**2,
                max_total_bytes=32 * 1024**2, check_cancel=check_cancel)
            cancel()
            if card.source_status != "source_ref_only" or card.reasons:
                raise ValueError("原保存規則／結果未綁定：" + "、".join(card.reasons))
            execution = json.loads(card.execution_json)
            context = validate_strategy_signal_context(json.loads(card.signal_context_json))
            qualification = execution.get("qualification", {})
            if (not isinstance(qualification, dict) or qualification.get("signal_context_schema") != context["schema"]
                    or qualification.get("signal_context_sha256") != context["sha256"]):
                raise ValueError("共同價量未綁定原保存執行規則；重新計算外層SHA不能替代原來源")
            raw_params = run.original_input.get("raw_params", {})
            if (context["stock_code"] != run.universe[0] or not isinstance(raw_params, dict)
                    or context["start_date"] != raw_params.get("start_date") or context["end_date"] != raw_params.get("end_date")
                    or context["rows"][0]["date"] < run.start_date or context["rows"][-1]["date"] > run.end_date):
                raise ValueError("共同價量窗與原run股票／實際及提交期間不符")
            if common is not None and context != common:
                raise ValueError("研究窗價量、日期、股票或解析版本不同；不得以整段暖機指紋或日期交集代替")
            common = context
            raw_rows = execution.get("score_observations") if execution.get("schema") == "single-backtest-rule-execution.v3" else execution.get("signals")
            if not isinstance(raw_rows, list) or len(raw_rows) != len(context["rows"]):
                raise ValueError("原逐日訊號缺件，不能由成交數、持倉或目前門檻反推")
            history: dict[str, SavedStrategySignal] = {}
            for price_row, observation in zip(context["rows"], raw_rows):
                cancel()
                if (not isinstance(observation, dict) or observation.get("date") != price_row["date"]
                        or type(observation.get("ready")) is not bool or type(observation.get("signal")) is not int
                        or observation["signal"] not in (-1, 0, 1)):
                    raise ValueError("原逐日訊號與共同價量日期不符或型別錯誤")
                when = observation["date"]
                date.fromisoformat(when)
                signal = observation["signal"]
                state = "unknown" if not observation["ready"] else "match" if signal == 1 else "no_match"
                reason = str(observation.get("reason") or ("原策略輸入未就緒" if state == "unknown" else
                    "原保存進場意圖" if signal == 1 else "原保存出場意圖" if signal == -1 else "本日未發進場意圖"))
                history[when] = SavedStrategySignal(state, signal, reason)
            strategies.append(SavedSignalStrategy(run.run_id, run.run_name, run.strategy_id, run.strategy_version,
                family[1], family[2], card))
            histories.append(history)
        assert common is not None
        rows = []
        for price_row in common["rows"]:
            cancel()
            when = price_row["date"]
            signals = tuple(history[when] for history in histories)
            rows.append(_comparison_day(when, strategies, signals))
        cancel()
        return SavedSignalComparison("available", strategies=tuple(strategies), rows=tuple(rows), stock_code=common["stock_code"],
            requested_start=common["start_date"], requested_end=common["end_date"], input_sha256=common["sha256"])
    except ResearchRunReadCancelledError:
        raise
    except (ValueError, TypeError, KeyError, OSError, ResearchRunServiceError) as error:
        return SavedSignalComparison("unavailable", (active + "：" + str(error),))
