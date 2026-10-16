"""兩個固定基本策略的已保存研究對照；只讀原 run，不授予歷史績效資格。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app_module.research_history_lookup import (
    ResearchHistoryEntry,
    ResearchHistoryLookup,
    ResearchHistoryUnavailable,
)
from app_module.research_run_dtos import (
    ResearchRunMetadataDTO,
    canonical_json,
    normalize_research_run_json_value,
)
from app_module.research_run_repository import ResearchRunRepositoryError
from app_module.research_run_service import ResearchRunService, ResearchRunServiceError
from app_module.saved_strategy_rule_card import (
    SavedStrategyRuleCard,
    load_saved_strategy_rule_card,
    metadata_sha256,
)
from app_module.strategy_historical_performance_read_service import (
    HistoricalMetricsState,
    HistoricalReadState,
    HistoricalRunCard,
    StrategyHistoricalPerformanceReadService,
)


_EXPECTED = {
    "stable_conservative_v1": ("1.0.0", "stable-conservative-fixed.v1"),
    "momentum_aggressive_v1": ("1.0.0", "momentum-aggressive-fixed.v1"),
}
_COMMON_RAW = (
    "stock_code", "start_date", "end_date", "capital", "fee_bps",
    "slippage_bps", "execution_price", "stop_loss_pct", "take_profit_pct",
    "stop_loss_atr_mult", "take_profit_atr_mult", "sizing_mode",
    "fixed_amount", "risk_pct", "max_positions", "position_sizing",
    "allow_pyramid", "allow_reentry", "reentry_cooldown_days",
    "enable_limit", "enable_volume", "max_participation",
)
_SHARED_SOURCES = (
    "backtest_module.broker_simulator.BrokerSimulator",
    "decision_module.score_threshold_policy.ScoreThresholdPolicy",
    "app_module.backtest_service.BacktestService",
    "ui_qt.views.backtest.research_run_metadata.execute_single_backtest_with_rule_source",
)


@dataclass(frozen=True, slots=True)
class BasicStrategySavedPair:
    state: str
    reasons: tuple[str, ...] = ()
    entries: tuple[ResearchHistoryEntry, ...] = ()
    cards: tuple[HistoricalRunCard, ...] = ()
    rules: tuple[SavedStrategyRuleCard, ...] = ()


def _same(left: object, right: object) -> bool:
    return canonical_json(normalize_research_run_json_value(left)) == canonical_json(
        normalize_research_run_json_value(right)
    )


def _preflight(runs: tuple[ResearchRunMetadataDTO, ...]) -> tuple[str, ...]:
    if len(runs) != 2 or runs[0].run_id == runs[1].run_id:
        return ("必須恰選兩筆不同的已保存 run",)
    if {run.strategy_id for run in runs} != set(_EXPECTED):
        return ("請各選一筆穩健策略與積極策略",)
    reasons: list[str] = []
    raw_values: list[dict[str, object]] = []
    executions: list[dict[str, object]] = []
    metric_periods: list[tuple[str, str] | None] = []
    for run in runs:
        expected = _EXPECTED[run.strategy_id]
        if (run.run_type != "single_backtest"
                or run.strategy_version != expected[0]
                or run.parameter_contract_version != expected[1]):
            reasons.append("策略版本或保存種類不符")
        if (run.execution_contract != "next-session-open.v2"
                or run.data_manifest.get("run_status", "completed") != "completed"
                or run.metrics.get("status", "completed") != "completed"):
            reasons.append("執行契約或完成狀態不符")
        raw = run.original_input.get("raw_params")
        if (run.original_input.get("source") != "BacktestView"
                or not isinstance(raw, dict)
                or any(key not in raw for key in _COMMON_RAW)):
            reasons.append("原執行輸入不完整")
            raw_values.append({})
        else:
            raw_values.append(raw)
            if (raw.get("strategy_id") != run.strategy_id
                    or raw.get("stock_code") not in run.universe
                    or raw.get("start_date") != run.start_date
                    or raw.get("end_date") != run.end_date
                    or raw.get("execution_price") != "next_open"):
                reasons.append("原執行輸入與保存身分不符")
        execution = run.data_manifest.get("single_backtest_rule_execution")
        if not isinstance(execution, dict) or execution.get("schema") != "single-backtest-rule-execution.v2":
            reasons.append("固定策略的原執行來源缺失")
            executions.append({})
        else:
            executions.append(execution)
            if (execution.get("input_fingerprint") != run.data_fingerprint
                    or execution.get("stock_code") not in run.universe
                    or execution.get("execution_contract") != run.execution_contract):
                reasons.append("原執行來源與保存資料不符")
            source_hashes = execution.get("source_hashes")
            if (not isinstance(source_hashes, dict)
                    or any(not source_hashes.get(key) for key in _SHARED_SOURCES)):
                reasons.append("共用執行程式來源缺失")
        metrics_contract = run.data_manifest.get("single_backtest_metrics_contract")
        if (not isinstance(metrics_contract, dict)
                or type(metrics_contract.get("period_start")) is not str
                or type(metrics_contract.get("period_end")) is not str
                or not metrics_contract["period_start"]
                or not metrics_contract["period_end"]):
            reasons.append("保存權益實際期間缺失")
            metric_periods.append(None)
        else:
            metric_periods.append((metrics_contract["period_start"],
                                   metrics_contract["period_end"]))
    left, right = runs
    same_fields = (
        ("股票不同", left.universe, right.universe),
        ("研究期間不同", (left.start_date, left.end_date), (right.start_date, right.end_date)),
        ("資料截止或指紋不同", (left.data_cutoff_date, left.data_fingerprint,
                              left.fingerprint_algorithm), (right.data_cutoff_date,
                              right.data_fingerprint, right.fingerprint_algorithm)),
        ("執行與成本條件不同", (left.execution_contract, left.execution_price,
                                left.sizing_mode, left.capital_cents, left.fee_bp_x100,
                                left.slippage_bp_x100, left.stop_loss_bp, left.take_profit_bp,
                                left.data_manifest.get("execution_assumptions")),
                               (right.execution_contract, right.execution_price,
                                right.sizing_mode, right.capital_cents, right.fee_bp_x100,
                                right.slippage_bp_x100, right.stop_loss_bp, right.take_profit_bp,
                                right.data_manifest.get("execution_assumptions"))),
    )
    for reason, first, second in same_fields:
        if not _same(first, second):
            reasons.append(reason)
    if metric_periods[0] is not None and metric_periods[1] is not None and metric_periods[0] != metric_periods[1]:
        reasons.append("保存權益實際期間不同")
    if raw_values[0] and raw_values[1] and not _same(
        {key: raw_values[0][key] for key in _COMMON_RAW},
        {key: raw_values[1][key] for key in _COMMON_RAW},
    ):
        reasons.append("原策略外輸入不同")
    if executions[0] and executions[1]:
        for reason, key in (("原撮合成本設定不同", "broker_config"),
                            ("原觀測期間不同", "start_date"),
                            ("原觀測期間不同", "end_date")):
            if not _same(executions[0].get(key), executions[1].get(key)):
                reasons.append(reason)
        left_sources = executions[0].get("source_hashes")
        right_sources = executions[1].get("source_hashes")
        if isinstance(left_sources, dict) and isinstance(right_sources, dict) and any(
            left_sources.get(key) != right_sources.get(key) for key in _SHARED_SOURCES
        ):
            reasons.append("共用執行程式版本不同")
    return tuple(dict.fromkeys(reasons))


class BasicStrategySavedPairReader:
    """以所選 metadata 為預期身分，兩筆逐一核原結果、規則及來源。"""

    def __init__(self, registry: ResearchRunService, lookup: ResearchHistoryLookup):
        self._registry = registry
        self._lookup = lookup
        self._historical = StrategyHistoricalPerformanceReadService(lookup)

    def read_selected(
        self,
        expected: tuple[ResearchRunMetadataDTO, ResearchRunMetadataDTO],
        *,
        check_cancel: Callable[[], bool] | None = None,
    ) -> BasicStrategySavedPair:
        reasons = _preflight(expected)
        if reasons:
            return BasicStrategySavedPair("blocked", reasons)
        if check_cancel is not None and check_cancel():
            return BasicStrategySavedPair("blocked", ("讀取已取消",))
        entries: list[ResearchHistoryEntry] = []
        cards: list[HistoricalRunCard] = []
        rules: list[SavedStrategyRuleCard] = []
        try:
            for run in expected:
                entry = self._lookup.select_registry_run(run.run_id, check_cancel=check_cancel)
                if entry.metadata_sha256 != metadata_sha256(run):
                    return BasicStrategySavedPair("blocked", ("所選保存來源已變動",))
                card = self._historical.read_selected(entry, check_cancel=check_cancel)
                if card.read_state != HistoricalReadState.VERIFIED:
                    return BasicStrategySavedPair("blocked", ("原結果讀回失敗：" + str(card.reason),))
                if card.metrics_state != HistoricalMetricsState.DECLARED:
                    return BasicStrategySavedPair("blocked", ("保存績效欄位無版本契約",))
                rule = load_saved_strategy_rule_card(
                    self._registry, run,
                    max_artifact_bytes=64 * 1024 * 1024,
                    max_total_bytes=256 * 1024 * 1024,
                    check_cancel=check_cancel,
                )
                if (rule.reasons or rule.source_status != "source_ref_only"
                        or rule.rule_card.rule_status != "execution_contract_bound"
                        or rule.performance_status != "not_evaluable"
                        or rule.result_ref != "research-run:" + run.run_id):
                    return BasicStrategySavedPair("blocked", ("保存規則來源或資格核對失敗",))
                entries.append(entry)
                cards.append(card)
                rules.append(rule)
            for entry in entries:
                if self._lookup.select_registry_run(entry.run_id, check_cancel=check_cancel) != entry:
                    return BasicStrategySavedPair("blocked", ("讀取期間保存來源已變動",))
        except (ResearchHistoryUnavailable, ResearchRunServiceError,
                ResearchRunRepositoryError, OSError, ValueError, TypeError) as exc:
            return BasicStrategySavedPair("blocked", ("原來源讀取失敗：" + str(exc),))
        if check_cancel is not None and check_cancel():
            return BasicStrategySavedPair("blocked", ("讀取已取消",))
        return BasicStrategySavedPair("saved_conditions_match", (), tuple(entries),
                                      tuple(cards), tuple(rules))
