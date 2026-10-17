"""三段收縮同次觀測的保存投影；不查目前行情、不重跑executor。"""
from collections import deque
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal, DecimalException, localcontext
from typing import Any, Mapping

from app_module.bollinger_rule_card import _values
from decision_module.strategies.baldr_vcp_contract import (
    CONTEXT_POLICY, EXECUTION_SCHEMA, LOOKBACK_CALENDAR_DAYS, MAX_PRIOR_ROWS,
    PARAMETER_CONTRACT, STRATEGY_ID, STRATEGY_VERSION, rule_definition,
)

SOURCE_KEYS = frozenset({
    "decision_module.strategies.baldr_vcp_executor.BaldrVCPExecutor",
    "decision_module.strategies.baldr_vcp_executor._observe_frame",
    "decision_module.strategies.baldr_vcp_executor._base",
    "decision_module.strategies.baldr_vcp_contract.rule_definition",
    "analysis_module.technical_analysis.technical_date_support.safe_convert_technical_dates",
    "backtest_module.broker_simulator.BrokerSimulator", "app_module.backtest_service.BacktestService",
    "backtest_module.conservative_fill_policy.ConservativeFillPolicy", "financial_module.units.to_decimal",
    "ui_qt.views.backtest.vcp_execution_source.execute_vcp_backtest_with_rule_source",
    "ui_qt.views.backtest.research_run_metadata.execute_single_backtest_with_rule_source",
    "app_module.vcp_rule_card.capture_vcp_observation",
})
NUMBERS = ("open", "high", "low", "close", "previous_close", "observed_volume", "ma20", "ma50", "volume_sum20")


def capture_vcp_observation(when: Any, row: Any) -> dict[str, Any]:
    """只序列化原producer觀測；金融原值寫成十進位字串。"""
    evidence = deepcopy(row["contraction_evidence"])
    for pivot in evidence["pivots"]:
        pivot["price"] = str(pivot["price"])
    for key in ("pivot_price", "first_pullback_volume_sum", "last_pullback_volume_sum"):
        if key in evidence:
            evidence[key] = str(evidence[key])
    source_fields = ("observed_open", "observed_high", "observed_low", "observed_close", "previous_close",
                     "observed_volume", "vcp_ma20", "vcp_ma50", "volume_sum20")
    return {
        "date": when.strftime("%Y-%m-%d"),
        **{key: None if row[field] is None else str(row[field]) for key, field in zip(NUMBERS, source_fields)},
        "ready": bool(row["rule_observation_ready"]), "signal": int(row["signal"]),
        "entry": bool(row["entry_rule_match"]), "exit": bool(row["exit_rule_match"]),
        "reason": str(row["reason_tags"]), "setup_match": row["setup_match"],
        "pattern_already_consumed": bool(row["pattern_already_consumed"]),
        "valid_observed_rows": int(row["valid_observed_rows"]),
        "position": int(row["observation_position"]), "evidence": evidence,
    }


def _vcp_values(spec, rules, source, meta, *, execution=None):
    values = _values(spec, rules, source, meta, execution=execution)
    values["entry"] = ({"pivots": rules["pivot"], "base": rules["base"], "breakout": rules["entry"]}, source)
    values["required_features"] = (["Open", "High", "Low", "Close", "original_integer_Volume", "Decimal_SMA20_50"], source)
    values["units"] = ({"price": "原行情元", "quantity": "原整數股", "fee": "bp", "confirmation": "已觀測列，非已驗官方交易日"}, source)
    values["data_insufficiency"] = ({"policy": rules["missing"], "warmup": 80,
                                    "calendar_completeness": "unknown", "official_availability": "unknown"}, source)
    if execution is None:
        values["source_trace"] = ({"strategy_id": spec.strategy_id, "version": spec.strategy_version, "basis": "original_plan_5.7"}, source)
    return values


def read_vcp_spec_card(spec, meta, identity, errors):
    from app_module.strategy_rule_card_readmodel import _card
    try:
        if (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION):
            raise ValueError("version")
        rules = rule_definition(spec.config.get("params", {}))
    except (TypeError, ValueError):
        return _card(identity, {}, errors + ("vcp_rule_spec_invalid",))
    card = _card(identity, _vcp_values(spec, rules, PARAMETER_CONTRACT, meta), errors)
    return replace(card, rule_status="specified_research_hypothesis" if not card.reasons else "not_evaluable")


def _decimal(raw: Any, *, integer: bool = False, positive: bool = False) -> Decimal:
    if type(raw) is not str:
        raise ValueError("number_type")
    value = Decimal(raw)
    if (not value.is_finite() or len(value.as_tuple().digits) > 120 or abs(value.adjusted()) > 60
            or value < 0 or positive and value <= 0 or integer and value != value.to_integral_value()):
        raise ValueError("number_bounds")
    return value


def _setup(evidence: Any, position: int) -> tuple[bool, Decimal | None, tuple[int, ...]]:
    if not isinstance(evidence, dict) or "pivots" not in evidence:
        raise ValueError("evidence")
    pivots = evidence["pivots"]
    if not isinstance(pivots, list) or len(pivots) > 6:
        raise ValueError("pivots")
    indices: list[int] = []
    prices: list[Decimal] = []
    kinds = []
    for item in pivots:
        if (not isinstance(item, dict) or set(item) != {"kind", "position", "price", "confirmed_position"}
                or item["kind"] not in ("high", "low") or type(item["position"]) is not int
                or type(item["confirmed_position"]) is not int
                or not max(2, position - 59) <= item["position"] < position
                or item["confirmed_position"] != item["position"] + 2 or item["confirmed_position"] > position
                or indices and item["position"] <= indices[-1]):
            raise ValueError("pivot_confirmation")
        indices.append(item["position"])
        kinds.append(item["kind"])
        price = _decimal(item["price"], positive=True)
        if len(price.as_tuple().digits) > 28 or abs(price.adjusted()) > 24:
            raise ValueError("pivot_price_bounds")
        prices.append(price)
    fields = {"pivots", "first_pullback_volume_sum", "first_pullback_rows", "last_pullback_volume_sum", "last_pullback_rows", "pivot_price"}
    if set(evidence) not in ({"pivots"}, fields):
        raise ValueError("evidence_fields")
    structure = (kinds == ["high", "low", "high", "low", "high", "low"]
                 and 15 <= indices[-1] - indices[0] + 1 <= 60
                 and all(indices[i + 1] - indices[i] >= 2 and prices[i] > prices[i + 1] for i in (0, 2, 4))
                 and prices[0] >= prices[2] >= prices[4] and prices[1] < prices[3] < prices[5])
    if structure:
        depths = [prices[i] - prices[i + 1] for i in (0, 2, 4)]
        structure = (depths[0] * 10000 <= prices[0] * 3000 and depths[2] * 10000 <= prices[4] * 800
                     and depths[0] * prices[2] > depths[1] * prices[0]
                     and depths[1] * prices[4] > depths[2] * prices[2])
    if not structure:
        if set(evidence) != {"pivots"}:
            raise ValueError("base_structure")
        return False, None, tuple(indices)
    if set(evidence) != fields:
        raise ValueError("pullback_evidence_missing")
    first, last = (_decimal(evidence[key], integer=True) for key in ("first_pullback_volume_sum", "last_pullback_volume_sum"))
    first_count, last_count = evidence["first_pullback_rows"], evidence["last_pullback_rows"]
    pivot_price = _decimal(evidence["pivot_price"], positive=True)
    if (type(first_count) is not int or type(last_count) is not int
            or first_count != indices[1] - indices[0] + 1 or last_count != indices[5] - indices[4] + 1
            or pivot_price != max(prices[::2])):
        raise ValueError("pullback_basis")
    return first > 0 and last > 0 and last * first_count < first * last_count, pivot_price, tuple(indices)


def _validate_observed_evidence(evidence: dict[str, Any], observed: dict[int, dict[str, Decimal | None]]) -> None:
    """只交叉核對保存內已存在的原觀測；不補讀前置行情或重跑策略。"""
    for pivot in evidence["pivots"]:
        center = pivot["position"]
        positions = tuple(range(center - 2, center + 3))
        if not all(position in observed for position in positions):
            continue
        window = [observed[position] for position in positions]
        if any(value[key] is None for value in window for key in ("open", "high", "low", "close", "observed_volume")):
            raise ValueError("pivot_missing_observation")
        high, low = observed[center]["high"], observed[center]["low"]
        assert high is not None and low is not None
        others = [observed[position] for position in positions if position != center]
        peak = all(value["high"] is not None and high > value["high"] for value in others)
        trough = all(value["low"] is not None and low < value["low"] for value in others)
        if (peak == trough or (pivot["kind"] == "high") != peak
                or _decimal(pivot["price"], positive=True) != (high if peak else low)):
            raise ValueError("pivot_raw_observation_mismatch")
    if "pivot_price" in evidence:
        pivots = evidence["pivots"]
        for high, low, key in ((pivots[0], pivots[1], "first_pullback_volume_sum"),
                               (pivots[4], pivots[5], "last_pullback_volume_sum")):
            positions = tuple(range(high["position"], low["position"] + 1))
            if all(position in observed for position in positions):
                volumes = [observed[position]["observed_volume"] for position in positions]
                if any(value is None for value in volumes) or sum((value for value in volumes if value is not None), Decimal(0)) != _decimal(evidence[key], integer=True):
                    raise ValueError("pullback_raw_observation_mismatch")


def _validate_rows(rows: Any, execution: Mapping[str, Any]) -> None:
    if not isinstance(rows, list) or not rows:
        raise ValueError("signals_missing")
    required = set(NUMBERS) | {"date", "ready", "signal", "entry", "exit", "reason", "setup_match",
                              "pattern_already_consumed", "valid_observed_rows", "position", "evidence"}
    previous = None
    prior_values = None
    prior_valid = False
    prior_count = 0
    consumed: set[tuple[int, ...]] = set()
    recent: deque[tuple[Decimal, Decimal]] = deque(maxlen=50)
    observed: dict[int, dict[str, Decimal | None]] = {}
    with localcontext() as context:
        context.prec = 120
        for number, row in enumerate(rows):
            if not isinstance(row, dict) or set(row) != required:
                raise ValueError("signal_fields")
            when = date.fromisoformat(row["date"])
            if (when.isoformat() != row["date"] or previous is not None and when <= previous
                    or not execution["start_date"] <= row["date"] <= execution["end_date"]
                    or any(type(row[key]) is not bool for key in ("ready", "entry", "exit", "pattern_already_consumed"))
                    or row["setup_match"] is not None and type(row["setup_match"]) is not bool
                    or type(row["signal"]) is not int or row["signal"] not in (-1, 0, 1)
                    or type(row["position"]) is not int or row["position"] != execution["input_context"]["prior_rows"] + number
                    or type(row["valid_observed_rows"]) is not int or not 0 <= row["valid_observed_rows"] <= row["position"] + 1):
                raise ValueError("signal_identity")
            values = {key: None if row[key] is None else _decimal(row[key], integer=key in ("observed_volume", "volume_sum20"),
                       positive=key not in ("observed_volume", "volume_sum20")) for key in NUMBERS}
            for key in ("open", "high", "low", "close", "previous_close", "observed_volume"):
                value = values[key]
                if value is not None and (len(value.as_tuple().digits) > 28 or abs(value.adjusted()) > 24):
                    raise ValueError("raw_number_bounds")
            open_value, high, low, close, volume = (values[key] for key in ("open", "high", "low", "close", "observed_volume"))
            valid = all(value is not None for value in (open_value, high, low, close, volume))
            count = row["valid_observed_rows"]
            if prior_values is not None and values["previous_close"] != (prior_values["close"] if prior_valid else None):
                raise ValueError("previous_close_link")
            if valid:
                assert open_value is not None and high is not None and low is not None and close is not None and volume is not None
                if high < max(open_value, close) or low > min(open_value, close) or high < low or count < 1:
                    raise ValueError("raw_ohlcv")
                if number and count != prior_count + 1:
                    raise ValueError("valid_window_link")
                recent.append((close, volume))
            else:
                if count != 0 or any(values[key] is not None for key in ("ma20", "ma50", "volume_sum20")):
                    raise ValueError("missing_window")
                recent.clear()
                consumed.clear()
            for window, key in ((20, "ma20"), (50, "ma50")):
                if (values[key] is not None) != (count >= window):
                    raise ValueError("ma_availability")
                if len(recent) >= window and values[key] != sum((item[0] for item in tuple(recent)[-window:]), Decimal(0)) / window:
                    raise ValueError("ma_basis")
            if ((values["volume_sum20"] is not None) != (count >= 20)
                    or len(recent) >= 20 and values["volume_sum20"] != sum(item[1] for item in tuple(recent)[-20:])):
                raise ValueError("volume_window")
            volume_sum = values["volume_sum20"]
            ready = count >= 80 and volume_sum is not None and volume_sum > 0
            if row["ready"] != ready or ready and values["previous_close"] is None:
                raise ValueError("ready")
            setup, pivot_price, identity = _setup(row["evidence"], row["position"])
            observed[row["position"]] = values
            _validate_observed_evidence(row["evidence"], observed)
            if (row["setup_match"] != (setup if ready else None)
                    or not ready and (row["evidence"] != {"pivots": []} or row["pattern_already_consumed"])):
                raise ValueError("setup")
            if number == 0 and row["pattern_already_consumed"]:
                if not setup or execution["input_context"]["prior_rows"] == 0:
                    raise ValueError("consumed_context")
                consumed.add(identity)
            if row["pattern_already_consumed"] != (identity in consumed):
                raise ValueError("consumed_link")
            ma20, ma50, prior_close = values["ma20"], values["ma50"], values["previous_close"]
            exit_match = ready and close is not None and ma20 is not None and close < ma20
            entry = (ready and setup and identity not in consumed and not exit_match
                     and prior_close is not None and pivot_price is not None and close is not None and ma50 is not None
                     and prior_close <= pivot_price < close and close > ma50 and volume is not None
                     and volume_sum is not None and volume * 40 > volume_sum * 3)
            reason = ("warming_or_missing_inputs" if not ready else "below_sma20_exit_intent" if exit_match
                      else "three_contraction_breakout_entry_intent" if entry else "pattern_not_matched" if not setup else "rule_hold")
            if (row["entry"] != entry or row["exit"] != exit_match or row["signal"] != (-1 if exit_match else 1 if entry else 0)
                    or row["reason"] != reason):
                raise ValueError("signal_basis")
            if entry:
                consumed.add(identity)
            previous, prior_values, prior_valid, prior_count = when, values, valid, count


def read_vcp_execution_card(spec, execution: Mapping[str, Any]):
    from app_module.strategy_rule_card_readmodel import _card, _hash, _json, _valid_hash, RuleCardIdentity
    identity = RuleCardIdentity(spec.strategy_id, spec.strategy_version, EXECUTION_SCHEMA,
                               _hash(dict(execution)), _hash(spec.to_dict()), "historical_backtest")
    try:
        required = {"schema", "strategy_spec", "registry_metadata", "source_hashes", "input_fingerprint", "executor",
                    "broker_config", "execution_contract", "stock_code", "start_date", "end_date", "required_features",
                    "benchmark", "qualification", "rules", "signals", "analysis_runtime", "input_context"}
        rules = rule_definition(spec.config.get("params", {}))
        meta, broker, hashes = (execution[key] for key in ("registry_metadata", "broker_config", "source_hashes"))
        if (set(execution) != required or execution["schema"] != EXECUTION_SCHEMA or execution["executor"] != {}
                or (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION)
                or _json(execution["strategy_spec"]) != _json(spec.to_dict()) or execution["input_fingerprint"] != spec.data_version
                or meta.get("strategy_id") != STRATEGY_ID or meta.get("strategy_version") != STRATEGY_VERSION
                or _json(execution["rules"]) != _json(rules)):
            raise ValueError("spec")
        features = execution["required_features"]
        if (not isinstance(features, list) or not all(type(key) is str for key in features)
                or len(features) != len(set(features))
                or any(not any(key in features for key in group) for group in (
                    ("開盤價", "Open", "open"), ("最高價", "High", "high"), ("最低價", "Low", "low"),
                    ("收盤價", "Close", "close"), ("成交股數", "Volume", "volume")))
                or type(spec.data_version) is not str or not spec.data_version.startswith("sha256:")
                or not _valid_hash(spec.data_version[7:])):
            raise ValueError("input_features")
        if (execution["execution_contract"] != "next-session-open.v2" or broker.get("execution_price") != "next_open"
                or broker.get("allow_pyramid") is not False or broker.get("stop_loss_atr_mult") is not None
                or broker.get("take_profit_atr_mult") is not None):
            raise ValueError("broker_contract")
        if set(hashes) != SOURCE_KEYS or any(not isinstance(value, str) or not _valid_hash(value) for value in hashes.values()):
            raise ValueError("source_hashes")
        runtime = execution["analysis_runtime"]
        if (not isinstance(runtime, dict) or set(runtime) != {"python", "decimal", "pandas", "numpy"}
                or any(type(value) is not str or not value for value in runtime.values())):
            raise ValueError("runtime")
        qualification = execution["qualification"]
        if qualification.get("historical_pit_eligible") is not False or qualification.get("performance_evaluable") is not False:
            raise ValueError("qualification")
        context = execution["input_context"]
        if (set(context) != {"lookback_calendar_days", "max_prior_rows", "start_date", "end_date", "prior_rows", "state_policy"}
                or context["lookback_calendar_days"] != LOOKBACK_CALENDAR_DAYS or context["max_prior_rows"] != MAX_PRIOR_ROWS
                or type(context["prior_rows"]) is not int or not 0 <= context["prior_rows"] <= MAX_PRIOR_ROWS
                or context["state_policy"] != CONTEXT_POLICY or context["end_date"] != execution["end_date"]
                or date.fromisoformat(context["start_date"]) > date.fromisoformat(execution["start_date"])):
            raise ValueError("input_context")
        _validate_rows(execution["signals"], execution)
    except (KeyError, TypeError, ValueError, AttributeError, DecimalException):
        return _card(identity, {}, ("vcp_execution_fields_invalid",))
    card = _card(identity, _vcp_values(spec, rules, EXECUTION_SCHEMA, meta, execution=execution), ())
    return replace(card, rule_status="execution_contract_bound" if not card.reasons else "not_evaluable")
