"""Research Run metadata 的純組裝與序列化 helper。"""

from __future__ import annotations

from datetime import datetime
from dataclasses import asdict, replace
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from io import BytesIO
import inspect
from pathlib import Path
from typing import Any
import uuid

import pandas as pd

from app_module.research_run_dtos import ResearchRunMetadataDTO, canonical_json
from app_module.saved_strategy_rule_card import result_context_sha256
from app_module.strategy_rule_card_readmodel import read_single_backtest_execution_rule_card
from decision_module.strategies.contracts import StrategySpec


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

    訊號與撮合仍由原 service 執行，輸入只載入一次。只支援既有 baseline fixed v1／next-open；
    其他模式仍走原 execution，沒有替缺件推論規則。此 hash 只代表本次資料 bytes，不授 PIT。
    """
    if (type(request.strategy_spec) is not StrategySpec
            or request.strategy_spec.strategy_id != "baseline_score_threshold"
            or request.strategy_spec.strategy_version != "1.0"
            or request.strategy_spec.config.get("params", {}).get("threshold_mode", "fixed") != "fixed"
            or request.execution_price != "next_open"):
        return request.execute(service, check_cancel=check_cancel)

    class BoundExecution:
        def run_backtest(self, **kwargs: Any) -> Any:
            from decision_module.strategies.baseline_score_executor import BaselineScoreExecutor
            from decision_module.strategies.registry import StrategyRegistry
            from backtest_module.broker_simulator import BrokerConfig, BrokerSimulator, NEXT_OPEN_CONTRACT
            if check_cancel is not None and check_cancel():
                raise InterruptedError("回測已取消")
            frame, actual_start, actual_end = service._load_stock_data(
                kwargs["stock_code"], kwargs["start_date"], kwargs["end_date"])
            if frame is None or frame.empty:
                return service.run_backtest(**kwargs)
            if (not isinstance(frame.index, pd.DatetimeIndex) or frame.index.hasnans
                    or frame.index.max() > pd.Timestamp(kwargs["end_date"])
                    or frame.index.min() < pd.Timestamp(kwargs["start_date"])):
                raise ValueError("single_backtest 保存來源不在本次決策期間內")
            raw = BytesIO()
            frame.to_parquet(raw, index=True)
            fingerprint = "sha256:" + hashlib.sha256(raw.getvalue()).hexdigest()
            spec = deepcopy(kwargs["strategy_spec"])
            if spec.data_version is not None and spec.data_version != fingerprint:
                raise ValueError("StrategySpec 的宣告資料版本與本次輸入不同")
            spec.data_version = fingerprint
            executor = StrategyRegistry.get_executor(spec)
            if type(executor) is not BaselineScoreExecutor:
                raise ValueError("baseline typed executor 不一致")
            kwargs.update(strategy_spec=spec, strategy_executor=executor, preloaded_data=frame,
                          actual_start_date=actual_start, actual_end_date=actual_end)
            report = service.run_backtest(**kwargs)
            details = dict(report.details or {})
            if details.get("execution_contract") != NEXT_OPEN_CONTRACT:
                return report
            broker_kwargs = {key: kwargs[key] for key in inspect.signature(BrokerConfig).parameters if key in kwargs}
            broker_config = BrokerConfig(**broker_kwargs)
            sources = {}
            for source in (BaselineScoreExecutor, BrokerSimulator, type(executor.threshold_policy), type(service)):
                filename = inspect.getsourcefile(source)
                if filename is None:
                    raise ValueError("執行契約缺程式來源")
                sources[source.__module__ + "." + source.__name__] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
            execution = json_safe({
                "schema": "single-backtest-rule-execution.v1", "strategy_spec": spec.to_dict(),
                "registry_metadata": StrategyRegistry.get_strategy_meta(spec.strategy_id),
                "source_hashes": sources, "input_fingerprint": fingerprint,
                "executor": {"buy_score": executor.buy_score, "sell_score": executor.sell_score,
                             "buy_confirm_days": executor.buy_confirm_days, "sell_confirm_days": executor.sell_confirm_days,
                             "cooldown_days": executor.cooldown_days, "threshold_mode": "fixed"},
                "broker_config": asdict(broker_config), "execution_contract": NEXT_OPEN_CONTRACT,
                "stock_code": kwargs["stock_code"], "start_date": actual_start, "end_date": actual_end,
                "required_features": list(frame.columns), "benchmark": details.get("benchmark_results") or None,
                "qualification": {"validation_status": getattr(report.validation_status, "value", "unknown"),
                                  "historical_pit_eligible": False, "performance_evaluable": False},
            })
            details.update(strategy_version=spec.strategy_version, parameter_contract_version="baseline-score-fixed.v1",
                           data_version=fingerprint, data_as_of_date=actual_end)
            manifest = dict(details.get("data_manifest") or {})
            manifest.update(strategy_spec=json_safe(spec.to_dict()), single_backtest_rule_execution=execution)
            details["data_manifest"] = manifest
            report.details = details
            return report

    return request.execute(BoundExecution(), check_cancel=check_cancel)


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
        start_date=str(params.get("start_date", "")),
        end_date=str(params.get("end_date", "")),
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
