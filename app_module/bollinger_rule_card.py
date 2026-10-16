"""布林基礎版的原規格／保存收據投影；不執行策略、查目前Registry或授資格。"""
from dataclasses import replace
from datetime import date
from decimal import Decimal, DecimalException
from collections.abc import Mapping
from typing import Any

from decision_module.strategies.baldr_bollinger_contract import (
    STRATEGY_ID, STRATEGY_VERSION, EXECUTION_SCHEMA, rule_definition,
)

SOURCE_KEYS = frozenset({
    "decision_module.strategies.baldr_bollinger_executor.BaldrBollingerExecutor",
    "backtest_module.broker_simulator.BrokerSimulator", "app_module.backtest_service.BacktestService",
    "analysis_module.technical_analysis.technical_indicators.calculate_causal_indicators",
    "analysis_module.technical_analysis.indicator_kernels.clean_price_values",
    "analysis_module.technical_analysis.technical_date_support.safe_convert_technical_dates",
    "decision_module.strategies.baldr_bollinger_contract.rule_definition",
    "ui_qt.views.backtest.research_run_metadata.execute_single_backtest_with_rule_source",
    "backtest_module.conservative_fill_policy.ConservativeFillPolicy",
    "financial_module.units.to_decimal",
})


def _values(spec, rules, source, meta, *, execution=None):
    broker = execution["broker_config"] if execution is not None else {}
    pending = {"status": "執行後依同次收據核對"}
    return {
        "name": (meta.get("name"), source), "description": (meta.get("description"), source),
        "entry": (rules["entry"], source), "exit": (rules["exit"], source),
        "universe": ({"membership": "explicit_single_stock", "stock_code": execution["stock_code"] if execution else None}, source),
        "period": ({"start_date": execution["start_date"], "end_date": execution["end_date"]} if execution else pending, source),
        "parameters": ({"submitted": spec.config.get("params", {}), "effective": rules}, source),
        "parameter_schema": (meta.get("params"), source),
        "cost": ({"fee_bps": broker.get("fee_bps"), "slippage_bps": broker.get("slippage_bps"),
                  "policy": "沿同次原Broker稅費與最低費用；輸入不是成本權威"} if execution else pending, source),
        "required_features": (["Open", "High", "Low", "Close", "Volume", "causal_BBANDS30_2_SMA"], source),
        "units": ({"price": "原行情元", "quantity": "股", "fee": "bp", "confirmation": "有效交易列"}, source),
        "data_insufficiency": ({"policy": rules["missing"], "warmup": 30,
                                "calendar_completeness": "unknown", "official_availability": "unknown"}, source),
        "execution_mode": (rules["execution"], source),
        "signal_time": ("當日收盤；只用當日與以前資料，確認不回標", source),
        "earliest_execution": ("下一有效可交易session開盤；缺開盤／停牌不補收盤", source),
        "holding_period": ({"fixed_sessions": None, "policy": rules["holding"]}, source),
        "stop_loss": ({"ratio": broker.get("stop_loss_pct"), "mode": "submitted_percentage_only"} if execution else pending, source),
        "take_profit": ({"ratio": broker.get("take_profit_pct"), "mode": "submitted_percentage_only"} if execution else pending, source),
        "position_limits": ({key: broker.get(key) for key in ("sizing_mode", "max_positions", "fixed_amount", "risk_pct", "allow_pyramid", "allow_reentry")} if execution else pending, source),
        "gap_suspension_unfilled": ({"policy": "原Broker缺開盤／零量／漲跌停與參與率守衛；意圖不當成交"}, source),
        "benchmark": ({"recorded": execution["benchmark"], "authority": "unknown"} if execution else pending, source),
        "qualification": ({"historical_pit_eligible": False, "performance_evaluable": False,
                           "status": "research_hypothesis_not_qualified"}, source),
        "source_trace": ({"input_fingerprint": execution["input_fingerprint"], "source_hashes": execution["source_hashes"],
                          "analysis_runtime": execution["analysis_runtime"], "input_context": execution["input_context"],
                          "signal_sessions": len(execution["signals"])} if execution else
                         {"strategy_id": spec.strategy_id, "version": spec.strategy_version, "basis": "original_plan_5.2"}, source),
    }


def read_bollinger_spec_card(spec, meta, identity, errors):
    from app_module.strategy_rule_card_readmodel import _card
    try:
        if (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION):
            raise ValueError("strategy_version")
        rules = rule_definition(spec.config.get("params", {}))
    except (TypeError, ValueError):
        return _card(identity, {}, errors + ("bollinger_rule_spec_invalid",))
    card = _card(identity, _values(spec, rules, "baldr-bollinger-basic.v1", meta), errors)
    return replace(card, rule_status="specified_research_hypothesis" if not card.reasons else "not_evaluable")


def read_bollinger_execution_card(spec, execution: Mapping[str, Any]):
    from app_module.strategy_rule_card_readmodel import _card, _hash, _json, _valid_hash, RuleCardIdentity
    identity = RuleCardIdentity(spec.strategy_id, spec.strategy_version, EXECUTION_SCHEMA,
                                _hash(dict(execution)), _hash(spec.to_dict()), "historical_backtest")
    errors = []
    required = {"schema", "strategy_spec", "registry_metadata", "source_hashes", "input_fingerprint", "executor",
                "broker_config", "execution_contract", "stock_code", "start_date", "end_date", "required_features",
                "benchmark", "qualification", "rules", "signals", "analysis_runtime", "input_context"}
    try:
        rules = rule_definition(spec.config.get("params", {}))
        meta, broker, hashes = (execution[key] for key in ("registry_metadata", "broker_config", "source_hashes"))
        if not all(isinstance(value, dict) for value in (meta, broker, hashes)):
            raise ValueError("fields")
        if (set(execution) != required or execution["schema"] != EXECUTION_SCHEMA
                or (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION)
                or _json(execution["strategy_spec"]) != _json(spec.to_dict())
                or execution["input_fingerprint"] != spec.data_version):
            errors.append("execution_rule_spec_mismatch")
        if (meta.get("strategy_id") != STRATEGY_ID or meta.get("strategy_version") != STRATEGY_VERSION
                or _json(execution["rules"]) != _json(rules)
                or execution["executor"] != {"entry_confirm_sessions": rules["entry"]["confirmation_sessions"]}):
            errors.append("execution_rule_parameter_mismatch")
        if (execution["execution_contract"] != "next-session-open.v2" or broker.get("execution_price") != "next_open"
                or broker.get("allow_pyramid") is not False or broker.get("stop_loss_atr_mult") is not None
                or broker.get("take_profit_atr_mult") is not None):
            errors.append("execution_rule_contract_mismatch")
        if set(hashes) != SOURCE_KEYS or any(not isinstance(value, str) or not _valid_hash(value) for value in hashes.values()):
            errors.append("execution_rule_source_hash_missing")
        runtime = execution["analysis_runtime"]
        if not isinstance(runtime, dict) or set(runtime) != {"talib", "numpy", "pandas"} or any(
                not isinstance(value, str) or not value.strip() for value in runtime.values()):
            errors.append("execution_rule_analysis_runtime_missing")
        qualification = execution["qualification"]
        if (not isinstance(qualification, dict) or qualification.get("historical_pit_eligible") is not False
                or qualification.get("performance_evaluable") is not False):
            errors.append("execution_rule_qualification_invalid")
        context = execution["input_context"]
        if (not isinstance(context, dict) or set(context) != {"lookback_calendar_days", "max_prior_rows", "start_date", "end_date", "prior_rows", "state_policy"}
                or type(context["prior_rows"]) is not int or not 0 <= context["prior_rows"] <= 31
                or context["lookback_calendar_days"] != 180 or context["max_prior_rows"] != 31
                or context["state_policy"] != "prefix_indicators_only_reset_confirmation_at_test_start"
                or date.fromisoformat(context["start_date"]) > date.fromisoformat(execution["start_date"])
                or context["end_date"] != execution["end_date"]):
            errors.append("execution_rule_input_context_invalid")
        rows = execution["signals"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("signals_missing")
        previous = None
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"date", "close", "upper", "middle", "ready", "signal", "entry", "exit", "reason"}:
                raise ValueError("signal_fields")
            when = date.fromisoformat(row["date"])
            if (previous is not None and when <= previous or not execution["start_date"] <= row["date"] <= execution["end_date"]
                    or type(row["signal"]) is not int or row["signal"] not in (-1, 0, 1)
                    or any(type(row[key]) is not bool for key in ("ready", "entry", "exit"))
                    or not isinstance(row["reason"], str)):
                raise ValueError("signal_identity")
            for key in ("close", "upper", "middle"):
                value = row[key]
                if value is None and not row["ready"]:
                    continue
                if not isinstance(value, str) or not Decimal(value).is_finite() or Decimal(value) <= 0:
                    raise ValueError("signal_value")
            if not row["ready"] and (row["signal"] or row["entry"] or row["exit"]):
                raise ValueError("unknown_signal")
            if row["signal"] != (-1 if row["exit"] else 1 if row["entry"] else 0):
                raise ValueError("signal_intent")
            previous = when
    except (KeyError, TypeError, ValueError, DecimalException):
        return _card(identity, {}, tuple(errors + ["bollinger_execution_fields_invalid"]))
    card = _card(identity, _values(spec, rules, EXECUTION_SCHEMA, meta, execution=execution), tuple(errors))
    return replace(card, rule_status="execution_contract_bound" if not card.reasons else "not_evaluable")
