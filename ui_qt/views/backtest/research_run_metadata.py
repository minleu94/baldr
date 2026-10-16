"""Research Run metadata 的純組裝與序列化 helper。"""

from __future__ import annotations

from datetime import date, datetime
from dataclasses import asdict, replace
from copy import deepcopy
from decimal import Decimal, DecimalException, ROUND_HALF_UP
import hashlib
from io import BytesIO
import inspect
from pathlib import Path
from typing import Any
import uuid

import pandas as pd

from app_module.research_run_dtos import ResearchRunMetadataDTO, canonical_json
from app_module.saved_strategy_rule_card import result_context_sha256
from app_module.strategy_rule_card_readmodel import fixed_single_backtest_rule_identity, read_single_backtest_execution_rule_card
from decision_module.strategies.contracts import StrategyMeta, StrategySpec


def factor_save_kwargs(details: dict[str, Any]) -> dict[str, Any]:
    factor_records = details.get("factor_records")
    factor_decision_date = details.get("factor_decision_date")
    if not factor_records or factor_decision_date is None:
        return {}
    return {
        "factor_records": list(factor_records),
        "factor_decision_date": factor_decision_date,
    }


def single_backtest_metrics(report: Any) -> dict[str, Any]:
    return {
        "total_return": getattr(report, "total_return", None),
        "annual_return": getattr(report, "annual_return", None),
        "sharpe_ratio": getattr(report, "sharpe_ratio", None),
        "max_drawdown": getattr(report, "max_drawdown", None),
        "win_rate": getattr(report, "win_rate", None),
        "total_trades": getattr(report, "total_trades", None),
        "expectancy": getattr(report, "expectancy", None),
    }


def next_research_run_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "value") and value.__class__.__name__.endswith("Status"):
        return value.value
    return value


def research_payload_hash(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(json_safe(payload)).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def money_to_cents(value: Any) -> int:
    return int((Decimal(str(value or 0)) * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))


def bps_to_bp_x100(value: Any) -> int:
    return int((Decimal(str(value or 0)) * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))


def pct_to_bp(value: Any) -> int | None:
    if value is None:
        return None
    return int((Decimal(str(value)) * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))


def execution_manifest(details: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    manifest = dict(details.get("data_manifest", {}) or {})
    declarations = {str(value) for value in (
        details.get("execution_contract"), summary.get("execution_contract"),
        manifest.get("execution_contract"),
    ) if value}
    if len(declarations) > 1:
        raise ValueError("研究結果的執行契約宣告不一致")
    if declarations:
        manifest["execution_contract"] = declarations.pop()
    if details.get("portfolio_credibility"):
        manifest["execution_assumptions"] = json_safe(details["portfolio_credibility"])
    status = summary.get("status") or details.get("status")
    if status:
        manifest["run_status"] = str(status)
    return manifest


def ratio_to_bp(value: Any) -> int | None:
    if value is None:
        return None
    return int((Decimal(str(value)) * Decimal("10000")).to_integral_value(rounding=ROUND_HALF_UP))


def execute_single_backtest_with_rule_source(request: Any, service: Any, *, check_cancel: Any = None) -> Any:
    """沿既有 request 執行；同次載入資料／typed executor 的契約在 producer 封存。

    訊號與撮合仍由原service執行，輸入只載入一次。baseline固定版保留v1，
    穩健／暴衝固定版另存v2；其他模式走原execution，不替缺件推論規則或授PIT。
    """
    identity = fixed_single_backtest_rule_identity(request.strategy_spec)
    if request.strategy_spec.strategy_id == "baldr_bollinger_basic_v1" and (
            request.execution_price != "next_open" or request.allow_pyramid
            or request.stop_loss_atr_mult is not None or request.take_profit_atr_mult is not None):
        raise ValueError("布林基礎研究僅支持 next_open、不加碼及百分比風控")
    if request.strategy_spec.strategy_id == "baldr_w_bottom_basic_v1" and (
            request.execution_price != "next_open" or request.allow_pyramid
            or request.stop_loss_atr_mult is not None or request.take_profit_atr_mult is not None):
        raise ValueError("W底基礎研究僅支持 next_open、不加碼及百分比風控")
    if identity is None or request.execution_price != "next_open":
        return request.execute(service, check_cancel=check_cancel)
    schema, executor_ref = identity

    class BoundExecution:
        def run_backtest(self, **kwargs: Any) -> Any:
            from decision_module.strategies.baseline_score_executor import BaselineScoreExecutor
            from decision_module.strategies.stable_conservative_executor import StableConservativeExecutor
            from decision_module.strategies.momentum_aggressive_executor import MomentumAggressiveExecutor
            from decision_module.strategies.baldr_bollinger_executor import BaldrBollingerExecutor
            from decision_module.strategies.baldr_bollinger_contract import rule_definition, confirmation_sessions, EXECUTION_SCHEMA
            from decision_module.strategies.baldr_w_bottom_executor import BaldrWBottomExecutor
            from decision_module.strategies.baldr_w_bottom_contract import (
                EXECUTION_SCHEMA as W_SCHEMA, rule_definition as w_rules, wait_sessions,
            )
            from decision_module.strategies.registry import StrategyRegistry
            from backtest_module.broker_simulator import BrokerConfig, BrokerSimulator, NEXT_OPEN_CONTRACT
            if check_cancel is not None and check_cancel():
                raise InterruptedError("回測已取消")
            context_start = (pd.Timestamp(kwargs["start_date"]) - pd.Timedelta(days=180)).strftime("%Y-%m-%d") if schema == EXECUTION_SCHEMA else kwargs["start_date"]
            frame, actual_start, actual_end = service._load_stock_data(
                kwargs["stock_code"], context_start, kwargs["end_date"])
            if frame is None or frame.empty:
                return service.run_backtest(**kwargs)
            if (not isinstance(frame.index, pd.DatetimeIndex) or frame.index.hasnans
                    or frame.index.max() > pd.Timestamp(kwargs["end_date"])
                    or frame.index.min() < pd.Timestamp(context_start)):
                raise ValueError("single_backtest 保存來源不在本次決策期間內")
            input_context = None
            if schema == EXECUTION_SCHEMA:
                before_start = frame.index < pd.Timestamp(kwargs["start_date"])
                frame = pd.concat([frame.loc[before_start].tail(31), frame.loc[~before_start]])
                input_context = {"lookback_calendar_days": 180, "max_prior_rows": 31,
                                 "start_date": frame.index.min().strftime("%Y-%m-%d"),
                                 "end_date": frame.index.max().strftime("%Y-%m-%d"),
                                 "prior_rows": int((frame.index < pd.Timestamp(kwargs["start_date"])).sum()),
                                 "state_policy": "prefix_indicators_only_reset_confirmation_at_test_start"}
                kwargs["signal_context_start_date"] = context_start
            raw = BytesIO()
            frame.to_parquet(raw, index=True)
            fingerprint = "sha256:" + hashlib.sha256(raw.getvalue()).hexdigest()
            spec = deepcopy(kwargs["strategy_spec"])
            if spec.data_version is not None and spec.data_version != fingerprint:
                raise ValueError("StrategySpec 的宣告資料版本與本次輸入不同")
            spec.data_version = fingerprint
            executor = StrategyRegistry.get_executor(spec)
            executor_types = {
                "baseline_score_threshold": BaselineScoreExecutor,
                "stable_conservative_v1": StableConservativeExecutor,
                "momentum_aggressive_v1": MomentumAggressiveExecutor,
                "baldr_bollinger_basic_v1": BaldrBollingerExecutor,
                "baldr_w_bottom_basic_v1": BaldrWBottomExecutor,
            }
            if (type(executor) is not executor_types.get(spec.strategy_id)
                    or type(executor).__module__ + "." + type(executor).__name__ != executor_ref):
                raise ValueError("fixed typed executor 不一致")
            registry_metadata = None
            if schema in ("single-backtest-rule-execution.v2", EXECUTION_SCHEMA, W_SCHEMA):
                raw_meta = StrategyRegistry.get_strategy_meta(spec.strategy_id)
                registry_metadata = deepcopy(raw_meta.to_dict() if isinstance(raw_meta, StrategyMeta) else raw_meta)
                if not isinstance(registry_metadata, dict):
                    raise ValueError("fixed策略來源metadata缺失")
                versions = [registry_metadata[key] for key in ("version", "strategy_version") if key in registry_metadata]
                if (registry_metadata.get("strategy_id") != spec.strategy_id or not versions
                        or any(version != spec.strategy_version for version in versions)):
                    raise ValueError("fixed策略來源metadata版本不一致")
            kwargs.update(strategy_spec=spec, strategy_executor=executor, preloaded_data=frame,
                          actual_start_date=actual_start, actual_end_date=actual_end)
            report = service.run_backtest(**kwargs)
            if schema in ("single-backtest-rule-execution.v2", EXECUTION_SCHEMA, W_SCHEMA) and check_cancel is not None and check_cancel():
                raise InterruptedError("回測已取消，不發布完整規則來源")
            details = dict(report.details or {})
            if details.get("execution_contract") != NEXT_OPEN_CONTRACT:
                return report
            broker_kwargs = {key: kwargs[key] for key in inspect.signature(BrokerConfig).parameters if key in kwargs}
            broker_config = BrokerConfig(**broker_kwargs)
            sources = {}
            if schema == W_SCHEMA:
                from analysis_module.pattern_analysis.causal_w_bottom import observe_w_bottom
                from analysis_module.technical_analysis.technical_date_support import safe_convert_technical_dates
                from backtest_module.conservative_fill_policy import ConservativeFillPolicy
                from financial_module.units import to_decimal
                source_objects = [type(executor), BrokerSimulator, type(service), observe_w_bottom,
                                  safe_convert_technical_dates, w_rules,
                                  execute_single_backtest_with_rule_source, ConservativeFillPolicy, to_decimal]
                effective_executor = {"max_wait_sessions": wait_sessions(spec.config.get("params", {}))}
            elif schema == EXECUTION_SCHEMA:
                from analysis_module.technical_analysis.technical_indicators import calculate_causal_indicators
                from analysis_module.technical_analysis.indicator_kernels import clean_price_values
                from analysis_module.technical_analysis.technical_date_support import safe_convert_technical_dates
                from backtest_module.conservative_fill_policy import ConservativeFillPolicy
                from financial_module.units import to_decimal
                source_objects = [type(executor), BrokerSimulator, type(service), calculate_causal_indicators,
                                  clean_price_values, safe_convert_technical_dates, rule_definition,
                                  execute_single_backtest_with_rule_source, ConservativeFillPolicy, to_decimal]
                effective_executor = {"entry_confirm_sessions": confirmation_sessions(spec.config.get("params", {}))}
            else:
                source_objects = [type(executor), BrokerSimulator, type(executor.threshold_policy), type(service)]
                effective_executor = {"buy_score": executor.buy_score, "sell_score": executor.sell_score,
                                      "buy_confirm_days": executor.buy_confirm_days, "sell_confirm_days": executor.sell_confirm_days,
                                      "cooldown_days": executor.cooldown_days, "threshold_mode": "fixed"}
            if schema == "single-backtest-rule-execution.v2":
                source_objects.append(execute_single_backtest_with_rule_source)
            for source in source_objects:
                filename = inspect.getsourcefile(source)
                if filename is None:
                    raise ValueError("執行契約缺程式來源")
                sources[source.__module__ + "." + source.__name__] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
            execution = json_safe({
                "schema": schema, "strategy_spec": spec.to_dict(),
                "registry_metadata": registry_metadata if schema in ("single-backtest-rule-execution.v2", EXECUTION_SCHEMA, W_SCHEMA) else StrategyRegistry.get_strategy_meta(spec.strategy_id),
                "source_hashes": sources, "input_fingerprint": fingerprint,
                "executor": effective_executor,
                "broker_config": asdict(broker_config), "execution_contract": NEXT_OPEN_CONTRACT,
                "stock_code": kwargs["stock_code"], "start_date": actual_start, "end_date": actual_end,
                "required_features": list(frame.columns), "benchmark": details.get("benchmark_results") or None,
                "qualification": {"validation_status": getattr(report.validation_status, "value", "unknown"),
                                  "historical_pit_eligible": False, "performance_evaluable": False},
            })
            if schema == "single-backtest-rule-execution.v2":
                # 原兩executor的attribute defaults與policy defaults可能不同；保存真正用來比較的值。
                execution["executor"].update(
                    buy_score=json_safe(executor.threshold_policy.buy_score),
                    sell_score=json_safe(executor.threshold_policy.sell_score),
                    threshold_value_source="ScoreThresholdPolicy.fixed",
                )
            if schema == EXECUTION_SCHEMA:
                import talib
                import numpy as np
                execution.update(rules=rule_definition(spec.config.get("params", {})),
                                 signals=details.get("rule_signal_observations"),
                                 input_context=input_context,
                                 analysis_runtime={"talib": talib.__version__, "numpy": np.__version__, "pandas": pd.__version__})
                execution["start_date"] = details["start_date"]
                execution["end_date"] = details["end_date"]
            if schema == W_SCHEMA:
                import decimal
                import platform
                execution.update(rules=w_rules(spec.config.get("params", {})),
                                 signals=details.get("rule_signal_observations"),
                                 input_context={"prior_rows": 0, "start_date": actual_start, "end_date": actual_end,
                                                "state_policy": "test_window_reset_all_geometry_candidate_episode"},
                                 analysis_runtime={"pandas": pd.__version__, "decimal": decimal.__libmpdec_version__,
                                                   "python": platform.python_version()})
            parameter_contract = {
                "baseline_score_threshold": "baseline-score-fixed.v1",
                "stable_conservative_v1": "stable-conservative-fixed.v1",
                "momentum_aggressive_v1": "momentum-aggressive-fixed.v1",
                "baldr_bollinger_basic_v1": "baldr-bollinger-basic.v1",
                "baldr_w_bottom_basic_v1": "baldr-w-bottom-basic.v1",
            }[spec.strategy_id]
            details.update(strategy_version=spec.strategy_version, parameter_contract_version=parameter_contract,
                           data_version=fingerprint, data_as_of_date=actual_end)
            manifest = dict(details.get("data_manifest") or {})
            manifest.update(strategy_spec=json_safe(spec.to_dict()), single_backtest_rule_execution=execution)
            details["data_manifest"] = manifest
            if check_cancel is not None and check_cancel():
                raise InterruptedError("回測已取消，不發布完整規則來源")
            report.details = details
            return report

    return request.execute(BoundExecution(), check_cancel=check_cancel)


def _validate_w_bottom_metadata_input(params: dict[str, Any], details: dict[str, Any],
                                     execution: dict[str, Any], spec: StrategySpec) -> None:
    """只比對原提交與同次執行，不另算金融結果或從目前設定補值。"""
    from decision_module.strategies.baldr_w_bottom_contract import PARAMETER_CONTRACT

    def same_number(left: Any, right: Any) -> bool:
        if left is None or right is None:
            return left is None and right is None
        if isinstance(left, bool) or isinstance(right, bool):
            return False
        try:
            first, second = Decimal(str(left)), Decimal(str(right))
            return first.is_finite() and second.is_finite() and first == second
        except (DecimalException, ValueError, TypeError):
            return False

    try:
        broker = execution["broker_config"]
        if (any(params.get(key) is None for key in ("capital", "fee_bps", "slippage_bps"))
                or params["strategy_id"] != spec.strategy_id or params["stock_code"] != execution["stock_code"]
                or details["strategy_id"] != spec.strategy_id or details["strategy_version"] != spec.strategy_version
                or details["parameter_contract_version"] != PARAMETER_CONTRACT
                or details["data_version"] != execution["input_fingerprint"]
                or details["data_as_of_date"] != execution["end_date"]
                or canonical_json(json_safe(params["strategy_params"])) != canonical_json(json_safe(spec.config.get("params", {})))
                or not same_number(params["capital"], details["initial_capital"])):
            raise ValueError("identity_or_input")
        requested_start, requested_end = (date.fromisoformat(params[key]) for key in ("start_date", "end_date"))
        actual_start, actual_end = (date.fromisoformat(execution[key]) for key in ("start_date", "end_date"))
        if (not requested_start <= actual_start <= actual_end <= requested_end
                or params["start_date"] != details["requested_start_date"] or params["end_date"] != details["requested_end_date"]
                or details["start_date"] != execution["start_date"] or details["end_date"] != execution["end_date"]):
            raise ValueError("window")
        for key in ("execution_price", "sizing_mode", "position_sizing"):
            if key not in params or params[key] != broker[key]:
                raise ValueError("execution")
        for original, effective in (("allow_pyramid", "allow_pyramid"), ("allow_reentry", "allow_reentry"),
                                     ("enable_limit", "enable_limit_up_down"), ("enable_volume", "enable_volume_constraint")):
            if type(params[original]) is not bool or params[original] is not broker[effective]:
                raise ValueError("execution_flags")
        for original, effective in (("fee_bps", "fee_bps"), ("slippage_bps", "slippage_bps"),
                ("stop_loss_pct", "stop_loss_pct"), ("take_profit_pct", "take_profit_pct"),
                ("stop_loss_atr_mult", "stop_loss_atr_mult"), ("take_profit_atr_mult", "take_profit_atr_mult"),
                ("fixed_amount", "fixed_amount"), ("risk_pct", "risk_pct"), ("max_positions", "max_positions"),
                ("reentry_cooldown_days", "reentry_cooldown_days"), ("max_participation", "max_participation_rate")):
            if not same_number(params[original], broker[effective]):
                raise ValueError("broker_inputs")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("W底研究來源輸入不一致，不能保存不同股票、參數、期間或金融假設") from exc


def build_single_backtest_metadata(
    *,
    run_id: str,
    run_name: str,
    notes: str,
    params: dict[str, Any],
    details: dict[str, Any],
    report: Any,
    created_at: str,
) -> ResearchRunMetadataDTO:
    metrics = single_backtest_metrics(report)
    manifest = execution_manifest(details, {})
    execution = manifest.get("single_backtest_rule_execution")
    is_w_bottom = isinstance(execution, dict) and execution.get("schema") == "single-backtest-w-bottom-execution.v1"
    if is_w_bottom:
        _validate_w_bottom_metadata_input(params, details, execution, StrategySpec.from_dict(manifest["strategy_spec"]))
    payload = {
        "run_type": "single_backtest",
        "params": params,
        "metrics": metrics,
        "validation_status": getattr(report.validation_status, "value", ""),
    }
    # Keep the legacy unversioned hash stable.  New versioned execution
    # metadata binds its manifest (contract/status/assumptions) into the hash.
    if any(key in manifest for key in ("execution_contract", "run_status", "execution_assumptions")):
        payload["data_manifest"] = manifest
    payload_hash = research_payload_hash(payload)
    metadata = ResearchRunMetadataDTO(
        run_id=run_id,
        run_name=run_name,
        run_type="single_backtest",
        strategy_id=str(params.get("strategy_id", "")),
        strategy_version=str(details.get("strategy_version", "")),
        parameter_contract_version=str(details.get("parameter_contract_version", "")),
        original_input={"source": "BacktestView", "notes": notes, "raw_params": params},
        normalized_params=dict(params.get("strategy_params", {}) or {}),
        fallback_reason=dict(details.get("fallback_reason", {}) or {}),
        universe=[str(params.get("stock_code", ""))] if params.get("stock_code") else [],
        start_date=str(execution["start_date"] if is_w_bottom else params.get("start_date", "")),
        end_date=str(execution["end_date"] if is_w_bottom else params.get("end_date", "")),
        data_cutoff_date=str(details.get("data_as_of_date", "")),
        data_fingerprint=str(details.get("data_version", "")),
        fingerprint_algorithm=(
            "sha256" if str(details.get("data_version", "")).startswith("sha256") else ""
        ),
        data_manifest=manifest,
        capital_cents=money_to_cents(params.get("capital", 0)),
        fee_bp_x100=bps_to_bp_x100(params.get("fee_bps", 0)),
        slippage_bp_x100=bps_to_bp_x100(params.get("slippage_bps", 0)),
        stop_loss_bp=pct_to_bp(params.get("stop_loss_pct")),
        take_profit_bp=pct_to_bp(params.get("take_profit_pct")),
        execution_price=str(manifest.get("execution_contract") or details.get("execution_price") or params.get("execution_price", "")),
        sizing_mode=str(params.get("sizing_mode", "")),
        metrics=metrics,
        regime_breakdown=dict(details.get("regime_breakdown", {}) or {}),
        benchmark_results=dict(details.get("benchmark_results", {}) or {}),
        payload_hash=payload_hash,
        created_at=created_at,
    )
    execution = manifest.get("single_backtest_rule_execution")
    if isinstance(execution, dict):
        spec = StrategySpec.from_dict(manifest["strategy_spec"])
        card = read_single_backtest_execution_rule_card(spec, execution)
        if card.reasons:
            raise ValueError("single_backtest 規則執行來源核對失敗：" + ",".join(card.reasons))
        metadata.data_manifest["rule_card_identity"] = asdict(replace(
            card.identity, context_sha256=result_context_sha256(metadata)))
    return metadata


def build_recommendation_portfolio_metadata(
    *,
    run_id: str,
    run_name: str,
    notes: str,
    config: dict[str, Any],
    run_params: dict[str, Any],
    details: dict[str, Any],
    metrics: dict[str, Any],
    created_at: str,
) -> ResearchRunMetadataDTO:
    strategy_config = dict(config.get("strategy_config", {}) or {})
    manifest = execution_manifest(details, metrics)
    assumptions = manifest.get("execution_assumptions", {})
    costs = assumptions.get("execution_costs", {}) if isinstance(assumptions, dict) else {}
    threshold_to_bp = ratio_to_bp if manifest.get("execution_contract") == "next-session-open.v2" else pct_to_bp
    payload_hash = research_payload_hash(
        {
            "run_type": "recommendation_portfolio",
            "config": config,
            "run_params": run_params,
            "metrics": metrics,
            "data_manifest": manifest,
        }
    )
    return ResearchRunMetadataDTO(
        run_id=run_id,
        run_name=run_name,
        run_type="recommendation_portfolio",
        strategy_id=str(strategy_config.get("strategy_id") or config.get("profile_id", "")),
        strategy_version=str(details.get("strategy_version", "")),
        parameter_contract_version=str(details.get("parameter_contract_version", "")),
        original_input={"source": "BacktestView", "notes": notes, "config": config},
        normalized_params=run_params,
        fallback_reason=dict(details.get("fallback_reason", {}) or {}),
        universe=list(config.get("universe", []) or []),
        start_date=str(run_params.get("start_date", "")),
        end_date=str(run_params.get("end_date", "")),
        data_cutoff_date=str(details.get("data_as_of_date", "")),
        data_fingerprint=str(details.get("data_version", "")),
        fingerprint_algorithm=(
            "sha256" if str(details.get("data_version", "")).startswith("sha256") else ""
        ),
        data_manifest=manifest,
        capital_cents=money_to_cents(run_params.get("initial_capital", 0)),
        fee_bp_x100=bps_to_bp_x100(costs.get("fee_bps", run_params.get("fee_bps", 0))),
        slippage_bp_x100=bps_to_bp_x100(costs.get("slippage_bps", run_params.get("slippage_bps", 0))),
        stop_loss_bp=threshold_to_bp(run_params.get("stop_loss_pct")),
        take_profit_bp=threshold_to_bp(run_params.get("take_profit_pct")),
        execution_price=str(manifest.get("execution_contract") or details.get("execution_price", "")),
        sizing_mode=str(run_params.get("allocation_method", "")),
        metrics=metrics,
        regime_breakdown=dict(details.get("regime_breakdown", {}) or {}),
        benchmark_results=dict(details.get("benchmark_results", {}) or {}),
        payload_hash=payload_hash,
        created_at=created_at,
    )
