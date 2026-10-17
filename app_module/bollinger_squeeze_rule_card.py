"""保存當次布林帶寬研究的唯讀規則卡；不重跑指標或查目前Registry。"""
from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from decimal import Decimal, DecimalException, localcontext
from typing import Any

from app_module.bollinger_rule_card import SOURCE_KEYS as BASIC_SOURCE_KEYS, _values
from decision_module.strategies.baldr_bollinger_squeeze_contract import (
    EXECUTION_SCHEMA, PARAMETER_CONTRACT, STRATEGY_ID, STRATEGY_VERSION, rule_definition,
)

SOURCE_KEYS = frozenset(key.replace("baldr_bollinger_executor.BaldrBollingerExecutor",
                                  "baldr_bollinger_squeeze_executor.BaldrBollingerSqueezeExecutor")
                        .replace("baldr_bollinger_contract.rule_definition",
                                 "baldr_bollinger_squeeze_contract.rule_definition") for key in BASIC_SOURCE_KEYS)
NUMBERS = ("close", "upper", "middle", "lower", "previous_close", "previous_upper", "band_width",
           "floor_width20", "floor_middle20", "observed_volume", "volume_sum20")


def _squeeze_values(spec, rules, source, meta, *, execution=None):
    values = _values(spec, rules, source, meta, execution=execution)
    values["units"] = ({"price": "原行情元", "quantity": "股", "fee": "bp",
                        "bandwidth": "價差除以同列中軌；跨乘比較", "volume_multiple": "1.5"}, source)
    values["data_insufficiency"] = ({"policy": rules["missing"], "warmup": 50,
                                    "calendar_completeness": "unknown", "official_availability": "unknown"}, source)
    if execution is None:
        values["source_trace"] = ({"strategy_id": spec.strategy_id, "version": spec.strategy_version,
                                   "basis": "original_plan_5.6"}, source)
    return values


def read_squeeze_spec_card(spec, meta, identity, errors):
    from app_module.strategy_rule_card_readmodel import _card
    try:
        if (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION):
            raise ValueError("version")
        rules = rule_definition(spec.config.get("params", {}))
    except (TypeError, ValueError):
        return _card(identity, {}, errors + ("squeeze_rule_spec_invalid",))
    card = _card(identity, _squeeze_values(spec, rules, PARAMETER_CONTRACT, meta), errors)
    return replace(card, rule_status="specified_research_hypothesis" if not card.reasons else "not_evaluable")


def _validate_rows(rows: Any, execution: Mapping[str, Any]) -> None:
    if not isinstance(rows, list) or not rows:
        raise ValueError("signals_missing")
    previous = None
    previous_values: dict[str, Decimal | None] | None = None
    previous_band_valid = False
    previous_squeeze: bool | None = None
    with localcontext() as context:
        context.prec = 120
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(NUMBERS) | {
                    "date", "ready", "signal", "entry", "exit", "reason", "squeeze", "previous_squeeze"}:
                raise ValueError("signal_fields")
            when = date.fromisoformat(row["date"])
            if (when.isoformat() != row["date"] or previous is not None and when <= previous
                    or not execution["start_date"] <= row["date"] <= execution["end_date"]
                    or any(type(row[key]) is not bool for key in ("ready", "entry", "exit"))
                    or any(row[key] is not None and type(row[key]) is not bool for key in ("squeeze", "previous_squeeze"))
                    or type(row["signal"]) is not int or row["signal"] not in (-1, 0, 1)
                    or not isinstance(row["reason"], str) or not row["reason"]):
                raise ValueError("signal_identity")
            values: dict[str, Decimal | None] = {}
            for key in NUMBERS:
                raw = row[key]
                if raw is None:
                    values[key] = None
                    continue
                if not isinstance(raw, str):
                    raise ValueError("signal_number_type")
                number = Decimal(raw)
                if not number.is_finite() or len(number.as_tuple().digits) > 60 or abs(number.adjusted()) > 48:
                    raise ValueError("signal_number_bounds")
                if key != "lower" and number < 0:
                    raise ValueError("signal_negative")
                if key in ("close", "upper", "middle", "previous_close", "previous_upper", "floor_middle20") and number <= 0:
                    raise ValueError("signal_price")
                values[key] = number
            close, upper, middle, lower = (values[key] for key in ("close", "upper", "middle", "lower"))
            band_valid = all(value is not None for value in (close, upper, middle, lower))
            if previous_values is not None:
                if (values["previous_close"] != (previous_values["close"] if previous_band_valid else None)
                        or values["previous_upper"] != (previous_values["upper"] if previous_band_valid else None)
                        or row["previous_squeeze"] is not previous_squeeze):
                    raise ValueError("previous_observation_link")
            if band_valid and upper is not None and middle is not None and lower is not None:
                if not upper >= middle >= lower or values["band_width"] != upper - lower:
                    raise ValueError("band_width")
            width, floor_width, floor_middle = (values[key] for key in ("band_width", "floor_width20", "floor_middle20"))
            if row["squeeze"] is not None:
                if any(value is None for value in (width, middle, floor_width, floor_middle)):
                    raise ValueError("squeeze_missing_basis")
                assert width is not None and middle is not None and floor_width is not None and floor_middle is not None
                if row["squeeze"] != (width * floor_middle <= floor_width * middle):
                    raise ValueError("squeeze_basis")
            volume, volume_sum = values["observed_volume"], values["volume_sum20"]
            if volume is not None and volume_sum is not None and volume_sum < volume:
                raise ValueError("volume_sum")
            ready = (band_valid and row["squeeze"] is not None and volume_sum is not None and volume_sum > 0
                     and values["previous_close"] is not None and values["previous_upper"] is not None
                     and row["previous_squeeze"] is not None)
            if row["ready"] != ready:
                raise ValueError("ready")
            if ready:
                assert close is not None and upper is not None and middle is not None
                prior_close, prior_upper = values["previous_close"], values["previous_upper"]
                assert prior_close is not None and prior_upper is not None and volume_sum is not None
                entry = (row["previous_squeeze"] is True and prior_close <= prior_upper and close > upper
                         and volume is not None and volume * 40 > volume_sum * 3)
                exit_match = close < middle
                if row["entry"] != entry or row["exit"] != exit_match:
                    raise ValueError("signal_rule")
            elif row["entry"] or row["exit"]:
                raise ValueError("unknown_signal")
            if row["signal"] != (-1 if row["exit"] else 1 if row["entry"] else 0):
                raise ValueError("signal_intent")
            previous = when
            previous_values = values
            previous_band_valid = band_valid
            previous_squeeze = row["squeeze"]


def read_squeeze_execution_card(spec, execution: Mapping[str, Any]):
    from app_module.strategy_rule_card_readmodel import _card, _hash, _json, _valid_hash, RuleCardIdentity
    identity = RuleCardIdentity(spec.strategy_id, spec.strategy_version, EXECUTION_SCHEMA,
                               _hash(dict(execution)), _hash(spec.to_dict()), "historical_backtest")
    try:
        required = {"schema", "strategy_spec", "registry_metadata", "source_hashes", "input_fingerprint", "executor",
                    "broker_config", "execution_contract", "stock_code", "start_date", "end_date", "required_features",
                    "benchmark", "qualification", "rules", "signals", "analysis_runtime", "input_context"}
        rules = rule_definition(spec.config.get("params", {}))
        meta, broker, hashes = (execution[key] for key in ("registry_metadata", "broker_config", "source_hashes"))
        if not all(isinstance(value, dict) for value in (meta, broker, hashes)):
            raise ValueError("fields")
        if (set(execution) != required or execution["schema"] != EXECUTION_SCHEMA
                or (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION)
                or _json(execution["strategy_spec"]) != _json(spec.to_dict())
                or execution["input_fingerprint"] != spec.data_version or execution["executor"] != {}
                or meta.get("strategy_id") != STRATEGY_ID or meta.get("strategy_version") != STRATEGY_VERSION
                or _json(execution["rules"]) != _json(rules)):
            raise ValueError("execution_rule_spec_mismatch")
        if (execution["execution_contract"] != "next-session-open.v2" or broker.get("execution_price") != "next_open"
                or broker.get("allow_pyramid") is not False or broker.get("stop_loss_atr_mult") is not None
                or broker.get("take_profit_atr_mult") is not None):
            raise ValueError("execution_contract")
        if set(hashes) != SOURCE_KEYS or any(not isinstance(value, str) or not _valid_hash(value) for value in hashes.values()):
            raise ValueError("source_hash_missing")
        runtime = execution["analysis_runtime"]
        if not isinstance(runtime, dict) or set(runtime) != {"talib", "numpy", "pandas"} or any(
                not isinstance(value, str) or not value.strip() for value in runtime.values()):
            raise ValueError("runtime")
        qualification = execution["qualification"]
        if (not isinstance(qualification, dict) or qualification.get("historical_pit_eligible") is not False
                or qualification.get("performance_evaluable") is not False):
            raise ValueError("qualification")
        context = execution["input_context"]
        if (not isinstance(context, dict) or set(context) != {"lookback_calendar_days", "max_prior_rows", "start_date", "end_date", "prior_rows", "state_policy"}
                or type(context["prior_rows"]) is not int or not 0 <= context["prior_rows"] <= 50
                or context["lookback_calendar_days"] != 180 or context["max_prior_rows"] != 50
                or context["state_policy"] != "prefix_indicators_and_previous_squeeze_no_orders_before_test_start"
                or date.fromisoformat(context["start_date"]) > date.fromisoformat(execution["start_date"])
                or context["end_date"] != execution["end_date"]):
            raise ValueError("input_context")
        _validate_rows(execution["signals"], execution)
    except (KeyError, TypeError, ValueError, DecimalException):
        return _card(identity, {}, ("squeeze_execution_fields_invalid",))
    card = _card(identity, _squeeze_values(spec, rules, EXECUTION_SCHEMA, meta, execution=execution), ())
    return replace(card, rule_status="execution_contract_bound" if not card.reasons else "not_evaluable")
