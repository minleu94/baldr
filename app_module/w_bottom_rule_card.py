"""W底當次研究規則的純讀投影；不讀目前Registry、不執行或重建策略訊號。"""
from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from decimal import Decimal, DecimalException
from typing import Any

from decision_module.strategies.baldr_w_bottom_contract import (
    STRATEGY_ID, STRATEGY_VERSION, EXECUTION_SCHEMA, rule_definition,
)

SOURCE_KEYS = frozenset({
    "decision_module.strategies.baldr_w_bottom_executor.BaldrWBottomExecutor",
    "analysis_module.pattern_analysis.causal_w_bottom.observe_w_bottom",
    "analysis_module.technical_analysis.technical_date_support.safe_convert_technical_dates",
    "decision_module.strategies.baldr_w_bottom_contract.rule_definition",
    "ui_qt.views.backtest.research_run_metadata.execute_single_backtest_with_rule_source",
    "app_module.backtest_service.BacktestService", "backtest_module.broker_simulator.BrokerSimulator",
    "backtest_module.conservative_fill_policy.ConservativeFillPolicy", "financial_module.units.to_decimal",
})
EVIDENCE_FIELDS = frozenset({"first_trough_at", "second_trough_at", "neckline_at", "confirmed_at",
                            "first_trough", "second_trough", "neckline", "floor"})
STATES = frozenset({"warming", "observing", "candidate", "invalidated", "entry_intent", "intent_episode", "exit_intent"})


def _values(spec, rules, source, meta, *, execution=None):
    broker = execution["broker_config"] if execution is not None else {}
    pending = {"status": "執行後依同次收據核對"}
    return {
        "name": (meta.get("name"), source), "description": (meta.get("description"), source),
        "entry": ({**rules["entry"], "trough": rules["trough"], "geometry": rules["geometry"]}, source),
        "exit": ({**rules["exit"], "invalidation": rules["invalidation"]}, source),
        "universe": ({"membership": "explicit_single_stock", "stock_code": execution["stock_code"] if execution else None}, source),
        "period": ({"start_date": execution["start_date"], "end_date": execution["end_date"]} if execution else pending, source),
        "parameters": ({"submitted": spec.config.get("params", {}), "effective": rules}, source),
        "parameter_schema": (meta.get("params"), source),
        "cost": ({"fee_bps": broker.get("fee_bps"), "slippage_bps": broker.get("slippage_bps"),
                  "policy": "同次原Broker稅費／最低費用；提交輸入不是成本權威"} if execution else pending, source),
        "required_features": (["Open", "High", "Low", "Close", "Volume", "causal_close_troughs"], source),
        "units": ({"price": "原行情元", "quantity": "股", "fee": "bp", "wait": "觀測列", "numeric": rules["numeric"]}, source),
        "data_insufficiency": ({"policy": rules["missing"], "first_trough_prior_rows": 5, "right_confirmation_rows": 1,
                                "calendar_completeness": "unknown", "official_availability": "unknown"}, source),
        "execution_mode": (rules["execution"], source),
        "signal_time": ("第二谷於右一列收盤確認，之後實際頸線突破日才發意圖，不回標谷日", source),
        "earliest_execution": ("下一有效可交易session開盤；意圖不代表成交", source),
        "holding_period": ({"fixed_sessions": None, "policy": rules["holding"]}, source),
        "stop_loss": ({"ratio": broker.get("stop_loss_pct"), "mode": "submitted_percentage_only"} if execution else pending, source),
        "take_profit": ({"ratio": broker.get("take_profit_pct"), "mode": "submitted_percentage_only"} if execution else pending, source),
        "position_limits": ({key: broker.get(key) for key in ("sizing_mode", "max_positions", "fixed_amount", "risk_pct", "allow_pyramid", "allow_reentry")} if execution else pending, source),
        "gap_suspension_unfilled": ({"policy": "沿原Broker缺開盤／停牌／零量／漲跌停／參與率守衛，不補成交"}, source),
        "benchmark": ({"recorded": execution["benchmark"], "authority": "unknown"} if execution else pending, source),
        "qualification": ({"historical_pit_eligible": False, "performance_evaluable": False,
                           "status": "research_hypothesis_not_qualified"}, source),
        "source_trace": ({"input_fingerprint": execution["input_fingerprint"], "source_hashes": execution["source_hashes"],
                          "input_context": execution["input_context"], "analysis_runtime": execution["analysis_runtime"],
                          "signal_sessions": len(execution["signals"])} if execution else
                         {"strategy_id": spec.strategy_id, "version": spec.strategy_version, "basis": "original_plan_5.3"}, source),
    }


def read_w_bottom_spec_card(spec, meta, identity, errors):
    from app_module.strategy_rule_card_readmodel import _card
    try:
        if (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION):
            raise ValueError("strategy_version")
        rules = rule_definition(spec.config.get("params", {}))
    except (TypeError, ValueError):
        return _card(identity, {}, errors + ("w_bottom_rule_spec_invalid",))
    card = _card(identity, _values(spec, rules, "baldr-w-bottom-basic.v1", meta), errors)
    return replace(card, rule_status="specified_research_hypothesis" if not card.reasons else "not_evaluable")


def _day(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("date_type")
    when = date.fromisoformat(value)
    if when.isoformat() != value:
        raise ValueError("date_format")
    return when


def _positive(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("price_type")
    number = Decimal(value)
    digits = number.as_tuple()
    if (not number.is_finite() or number <= 0 or not isinstance(digits.exponent, int)
            or digits.exponent < -12 or len(digits.digits) + max(digits.exponent, 0) > 28):
        raise ValueError("price_contract")
    return number


def _validate_rows(rows, start: date, end: date, max_wait: int) -> None:
    """核封存結構、日期／原值與意圖連續性，不重跑形態或產生新訊號。"""
    if not isinstance(rows, list) or not rows:
        raise ValueError("signals_missing")
    known = {}
    episode = None
    candidate = None
    previous = None
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"date", "close", "ready", "signal", "entry", "exit", "reason", "state", "evidence"}:
            raise ValueError("signal_fields")
        when = _day(row["date"])
        if (not start <= when <= end or previous is not None and when <= previous
                or type(row["signal"]) is not int or row["signal"] not in (-1, 0, 1)
                or any(type(row[key]) is not bool for key in ("ready", "entry", "exit"))
                or row["state"] not in STATES or not isinstance(row["reason"], str) or not row["reason"]):
            raise ValueError("signal_identity")
        close = _positive(row["close"]) if row["close"] is not None else None
        if (row["ready"] and close is None or not row["ready"] and (row["signal"] or row["entry"] or row["exit"])
                or row["entry"] and row["exit"]
                or row["signal"] != (-1 if row["exit"] else 1 if row["entry"] else 0)):
            raise ValueError("signal_intent")
        known[when] = (position, close)
        evidence = row["evidence"]
        if evidence is not None:
            if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS:
                raise ValueError("evidence_fields")
            first, second, neck_date, confirmed = (_day(evidence[key]) for key in
                ("first_trough_at", "second_trough_at", "neckline_at", "confirmed_at"))
            if (not start <= first < neck_date < second < confirmed <= when
                    or any(day not in known for day in (first, second, neck_date, confirmed))
                    or not 3 <= known[second][0] - known[first][0] <= 20
                    or known[confirmed][0] != known[second][0] + 1):
                raise ValueError("evidence_dates")
            left, right, neck, floor = (_positive(evidence[key]) for key in ("first_trough", "second_trough", "neckline", "floor"))
            if (left != known[first][1] or right != known[second][1] or neck != known[neck_date][1]
                    or floor != min(left, right) or neck <= max(left, right)):
                raise ValueError("evidence_prices")
        if row["entry"]:
            if (episode is not None or evidence is None or row["state"] != "entry_intent" or close is None
                    or close <= _positive(evidence["neckline"])
                    or position - known[_day(evidence["confirmed_at"])][0] > max_wait):
                raise ValueError("entry_episode")
            if candidate is not None and evidence != candidate:
                raise ValueError("candidate_changed")
            episode = evidence; candidate = None
        elif row["exit"]:
            if (episode is None or evidence != episode or row["state"] != "exit_intent" or close is None
                    or close >= _positive(episode["neckline"])):
                raise ValueError("exit_episode")
            episode = None; candidate = None
        elif episode is not None:
            if evidence != episode or row["state"] != "intent_episode":
                raise ValueError("episode_changed")
        elif row["state"] == "candidate":
            if (evidence is None or not row["ready"] or candidate is not None and evidence != candidate
                    or position - known[_day(evidence["confirmed_at"])][0] > max_wait):
                raise ValueError("candidate_changed")
            candidate = evidence
        elif row["state"] == "invalidated":
            if evidence is None or candidate is None or evidence != candidate:
                raise ValueError("candidate_invalidation")
            candidate = None
        elif row["state"] in ("warming", "observing"):
            if evidence is not None:
                raise ValueError("unexpected_evidence")
            candidate = None
        else:
            raise ValueError("unexpected_episode_state")
        previous = when
    if _day(rows[0]["date"]) != start or _day(rows[-1]["date"]) != end:
        raise ValueError("signal_window")


def read_w_bottom_execution_card(spec, execution: Mapping[str, Any]):
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
        fingerprint = execution["input_fingerprint"]
        if (set(execution) != required or execution["schema"] != EXECUTION_SCHEMA
                or (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION)
                or _json(execution["strategy_spec"]) != _json(spec.to_dict()) or fingerprint != spec.data_version
                or not isinstance(fingerprint, str) or not fingerprint.startswith("sha256:") or not _valid_hash(fingerprint[7:])):
            errors.append("execution_rule_spec_mismatch")
        if (meta.get("strategy_id") != STRATEGY_ID or meta.get("strategy_version") != STRATEGY_VERSION
                or _json(execution["rules"]) != _json(rules)
                or execution["executor"] != {"max_wait_sessions": rules["entry"]["max_wait_sessions"]}):
            errors.append("execution_rule_parameter_mismatch")
        if (execution["execution_contract"] != "next-session-open.v2" or broker.get("execution_price") != "next_open"
                or broker.get("allow_pyramid") is not False or broker.get("stop_loss_atr_mult") is not None
                or broker.get("take_profit_atr_mult") is not None):
            errors.append("execution_rule_contract_mismatch")
        if set(hashes) != SOURCE_KEYS or any(not isinstance(value, str) or not _valid_hash(value) for value in hashes.values()):
            errors.append("execution_rule_source_hash_missing")
        runtime = execution["analysis_runtime"]
        if not isinstance(runtime, dict) or set(runtime) != {"pandas", "decimal", "python"} or any(
                not isinstance(value, str) or not value.strip() for value in runtime.values()):
            errors.append("execution_rule_analysis_runtime_missing")
        qualification = execution["qualification"]
        if (not isinstance(qualification, dict) or qualification.get("historical_pit_eligible") is not False
                or qualification.get("performance_evaluable") is not False):
            errors.append("execution_rule_qualification_invalid")
        start, end = _day(execution["start_date"]), _day(execution["end_date"])
        context = execution["input_context"]
        if (not isinstance(context, dict) or set(context) != {"prior_rows", "start_date", "end_date", "state_policy"}
                or type(context["prior_rows"]) is not int or context["prior_rows"] != 0
                or context["start_date"] != execution["start_date"] or context["end_date"] != execution["end_date"]
                or context["state_policy"] != "test_window_reset_all_geometry_candidate_episode"):
            errors.append("execution_rule_input_context_invalid")
        _validate_rows(execution["signals"], start, end, rules["entry"]["max_wait_sessions"])
    except (KeyError, TypeError, ValueError, DecimalException):
        return _card(identity, {}, tuple(errors + ["w_bottom_execution_fields_invalid"]))
    card = _card(identity, _values(spec, rules, EXECUTION_SCHEMA, meta, execution=execution), tuple(errors))
    return replace(card, rule_status="execution_contract_bound" if not card.reasons else "not_evaluable")
