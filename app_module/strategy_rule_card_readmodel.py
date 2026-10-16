"""版本化規則說明的唯讀投影；不執行策略、不授予績效或交易資格。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, DecimalException
import hashlib
import json
import re
from typing import Any

from app_module.daily_market_method_contract import (
    method_contracts_payload, method_contracts_sha256,
)
from app_module.daily_market_feature_snapshot import DailyMarketFeatureSnapshot
from app_module.strategy_version_service import StrategyVersion
from decision_module.strategies.contracts import StrategyMeta, StrategySpec
from decision_module.strategies.registry import StrategyRegistry


SCHEMA = "strategy-rule-card.v1"
RESULT_KINDS = frozenset({"historical_backtest", "research_forward", "live"})
FIELD_KEYS = (
    "name", "description", "entry", "exit", "universe", "period",
    "parameters", "parameter_schema", "cost", "required_features", "units",
    "data_insufficiency", "execution_mode", "signal_time", "earliest_execution",
    "holding_period", "stop_loss", "take_profit", "position_limits",
    "gap_suspension_unfilled", "benchmark", "qualification", "source_trace",
)


def _json(value: Any) -> str:
    # Decimal 只在 DTO 序列化邊界轉字串，不改金融數值。
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False,
                      default=lambda item: str(item) if isinstance(item, Decimal)
                      else _unsupported(item))


def _unsupported(value: Any) -> Any:
    raise TypeError(f"不支援的契約值：{type(value).__name__}")


def _hash(value: Any) -> str:
    try:
        return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()
    except (TypeError, ValueError):
        return ""


def _valid_hash(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", value))


@dataclass(frozen=True)
class RuleField:
    key: str
    value_json: str
    source: str | None
    missing_reason: str | None = None

    @property
    def value(self) -> Any:
        """每次回傳獨立副本，consumer 無法改寫舊卡。"""
        return json.loads(self.value_json)


@dataclass(frozen=True)
class RuleCardIdentity:
    rule_id: str
    rule_version: str
    source_ref: str
    source_sha256: str
    rule_sha256: str
    result_kind: str
    context_sha256: str = ""


@dataclass(frozen=True)
class StrategyRuleCard:
    identity: RuleCardIdentity
    fields: tuple[RuleField, ...]
    missing: tuple[str, ...]
    reasons: tuple[str, ...]
    observation_qualification: str = "not_evaluable"
    observation_json: str = "null"
    schema: str = SCHEMA
    rule_status: str = "not_evaluable"
    performance_status: str = "not_evaluable"

    def field(self, key: str) -> RuleField:
        return next(item for item in self.fields if item.key == key)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return {
            "schema": self.schema, "identity": asdict(self.identity),
            "fields": {item.key: {"value": item.value, "source": item.source,
                                  "missing_reason": item.missing_reason}
                       for item in self.fields},
            "missing": list(self.missing), "reasons": list(self.reasons),
            "rule_status": self.rule_status,
            "observation_qualification": self.observation_qualification,
            "observation": json.loads(self.observation_json),
            "performance_status": self.performance_status,
        }


def _card(identity: RuleCardIdentity, values: Mapping[str, tuple[Any, str]],
          reasons: tuple[str, ...] = (), *, observation: Any = None,
          observation_qualification: str = "not_evaluable") -> StrategyRuleCard:
    errors = list(reasons)
    projected: list[RuleField] = []
    for key in FIELD_KEYS:
        if key not in values or values[key][0] is None or not values[key][1]:
            projected.append(RuleField(key, "null", None, "source_contract_field_missing"))
            continue
        try:
            projected.append(RuleField(key, _json(values[key][0]), values[key][1]))
        except (TypeError, ValueError):
            projected.append(RuleField(key, "null", values[key][1], "source_contract_value_invalid"))
            errors.append("source_contract_value_invalid:" + key)
    fields = tuple(projected)
    if not identity.rule_id or not identity.rule_version or not identity.source_ref:
        errors.append("rule_identity_missing")
    if not _valid_hash(identity.source_sha256) or not _valid_hash(identity.rule_sha256):
        errors.append("source_hash_missing_or_invalid")
    if identity.result_kind not in RESULT_KINDS:
        errors.append("result_kind_unknown")
    return StrategyRuleCard(identity, fields,
                            tuple(item.key for item in fields if item.missing_reason),
                            tuple(dict.fromkeys(errors)),
                            observation_qualification if not errors else "not_evaluable",
                            _json(observation) if not errors else "null")


def read_strategy_rule_card(spec: StrategySpec, *,
                            version: StrategyVersion | None = None,
                            result_kind: str = "historical_backtest") -> StrategyRuleCard:
    """只讀公開 registry 與傳入 DTO；不建立 VersionService 或 executor。"""
    raw = StrategyRegistry.get_strategy_meta(spec.strategy_id)
    meta = raw.to_dict() if isinstance(raw, StrategyMeta) else raw
    meta = meta if isinstance(meta, dict) else {}
    source = "decision_module.strategies.registry.StrategyRegistry.get_strategy_meta"
    errors: list[str] = []
    if not meta:
        errors.append("registry_metadata_missing")
    if meta and (meta.get("strategy_id") != spec.strategy_id or
                 meta.get("strategy_version", meta.get("version")) != spec.strategy_version):
        errors.append("registry_version_mismatch")
    if version and (version.strategy_id != spec.strategy_id or
                    version.strategy_version != spec.strategy_version or
                    version.config != spec.config):
        errors.append("strategy_version_spec_mismatch")
    if version and any(version.params.get(key) != value
                       for key, value in spec.config.get("params", {}).items()):
        errors.append("strategy_version_params_mismatch")
    payload = {"spec": spec.to_dict(), "registry": meta,
               "version": version.to_dict() if version else None}
    identity = RuleCardIdentity(spec.strategy_id, spec.strategy_version, source,
                                _hash(payload), _hash(spec.to_dict()), result_kind)
    values: dict[str, tuple[Any, str]] = {
        "name": (meta.get("name"), source + ".name"),
        "description": (meta.get("description"), source + ".description"),
        "parameters": (spec.config.get("params"), "StrategySpec.config.params"),
        "parameter_schema": (meta.get("params", meta.get("default_params")),
                             source + (".params" if "params" in meta else ".default_params")),
        "universe": ({"target_type": spec.target_type, "regime": spec.regime,
                      "membership": None}, "StrategySpec.target_type/regime"),
        "qualification": ({"validation_status": version.validation_status,
                           "source_run_id": version.source_run_id},
                          "StrategyVersion.validation_status/source_run_id") if version
                         else (None, ""),
        "source_trace": ({"strategy_id": spec.strategy_id,
                          "strategy_version": spec.strategy_version,
                          "data_version": spec.data_version,
                          "version_id": version.version_id if version else None,
                          "source_run_id": version.source_run_id if version else None},
                         "StrategySpec/StrategyVersion"),
    }
    # config 是原始設定，不把參數名／description 推論為完整出場或執行合約。
    if spec.strategy_id == "baldr_bollinger_basic_v1":
        from app_module.bollinger_rule_card import read_bollinger_spec_card
        return read_bollinger_spec_card(spec, meta, identity, tuple(errors))
    if spec.strategy_id == "baldr_w_bottom_basic_v1":
        from app_module.w_bottom_rule_card import read_w_bottom_spec_card
        return read_w_bottom_spec_card(spec, meta, identity, tuple(errors))
    return _card(identity, values, tuple(errors))


def fixed_single_backtest_rule_identity(spec: StrategySpec) -> tuple[str, str] | None:
    """明示既有fixed執行器的保存版本；不建立executor或補目前預設值。"""
    if (type(spec) is not StrategySpec or not isinstance(spec.config, dict)
            or type(spec.strategy_id) is not str or type(spec.strategy_version) is not str):
        return None
    params = spec.config.get("params", {})
    if not isinstance(params, dict) or params.get("threshold_mode", "fixed") != "fixed":
        return None
    identities = {
        ("baldr_w_bottom_basic_v1", "1.0.0"): (
            "single-backtest-w-bottom-execution.v1",
            "decision_module.strategies.baldr_w_bottom_executor.BaldrWBottomExecutor"),
        ("baldr_bollinger_basic_v1", "1.0.0"): (
            "single-backtest-bollinger-execution.v1",
            "decision_module.strategies.baldr_bollinger_executor.BaldrBollingerExecutor"),
        ("baseline_score_threshold", "1.0"): (
            "single-backtest-rule-execution.v1",
            "decision_module.strategies.baseline_score_executor.BaselineScoreExecutor"),
        ("stable_conservative_v1", "1.0.0"): (
            "single-backtest-rule-execution.v2",
            "decision_module.strategies.stable_conservative_executor.StableConservativeExecutor"),
        ("momentum_aggressive_v1", "1.0.0"): (
            "single-backtest-rule-execution.v2",
            "decision_module.strategies.momentum_aggressive_executor.MomentumAggressiveExecutor"),
    }
    return identities.get((spec.strategy_id, spec.strategy_version))


def _same_rule_number(left: Any, right: Any) -> bool:
    """只核對保存數字，不以浮點或caller Decimal context重算門檻。"""
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    try:
        first, second = Decimal(str(left)), Decimal(str(right))
        return first.is_finite() and second.is_finite() and first == second
    except (DecimalException, TypeError, ValueError):
        return False


def read_single_backtest_execution_rule_card(spec: StrategySpec, execution: Mapping[str, Any]) -> StrategyRuleCard:
    """只投影同次producer已封存的fixed契約，不借現在registry或重跑executor。"""
    if execution.get("schema") == "single-backtest-w-bottom-execution.v1":
        from app_module.w_bottom_rule_card import read_w_bottom_execution_card
        return read_w_bottom_execution_card(spec, execution)
    if execution.get("schema") == "single-backtest-bollinger-execution.v1":
        from app_module.bollinger_rule_card import read_bollinger_execution_card
        return read_bollinger_execution_card(spec, execution)
    source = ("single-backtest-rule-execution.v2"
              if execution.get("schema") == "single-backtest-rule-execution.v2"
              else "single-backtest-rule-execution.v1")
    supported = fixed_single_backtest_rule_identity(spec)
    errors: list[str] = []
    required = {"schema", "strategy_spec", "registry_metadata", "source_hashes", "input_fingerprint",
                "executor", "broker_config", "execution_contract", "stock_code", "start_date", "end_date",
                "required_features", "benchmark", "qualification"}
    if set(execution) != required or execution.get("schema") != source:
        errors.append("execution_rule_schema_invalid")
    if (supported is None or supported[0] != source
            or _json(execution.get("strategy_spec")) != _json(spec.to_dict())
            or execution.get("input_fingerprint") != spec.data_version):
        errors.append("execution_rule_spec_mismatch")
    meta = execution.get("registry_metadata", {})
    executor = execution.get("executor", {})
    broker = execution.get("broker_config", {})
    hashes = execution.get("source_hashes", {})
    if not all(isinstance(item, dict) for item in (meta, executor, broker, hashes)):
        return _card(RuleCardIdentity(spec.strategy_id, spec.strategy_version, source, "", "", "historical_backtest"), {},
                     ("execution_rule_fields_invalid",))
    versions = [meta[key] for key in ("version", "strategy_version") if key in meta]
    metadata_version_matches = (meta.get("version") == spec.strategy_version
                                if source == "single-backtest-rule-execution.v1"
                                else bool(versions) and all(value == spec.strategy_version for value in versions))
    if (meta.get("strategy_id") != spec.strategy_id or not metadata_version_matches
            or executor.get("threshold_mode") != "fixed"
            or execution.get("execution_contract") != "next-session-open.v2"
            or broker.get("execution_price") != "next_open"):
        errors.append("execution_rule_contract_mismatch")
    expected_sources = {supported[1] if supported else "unsupported_executor",
                        "backtest_module.broker_simulator.BrokerSimulator",
                        "decision_module.score_threshold_policy.ScoreThresholdPolicy",
                        "app_module.backtest_service.BacktestService"}
    if source == "single-backtest-rule-execution.v2":
        expected_sources.add("ui_qt.views.backtest.research_run_metadata.execute_single_backtest_with_rule_source")
    if set(hashes) != expected_sources or any(not isinstance(value, str) or not _valid_hash(value) for value in hashes.values()):
        errors.append("execution_rule_source_hash_missing")
    if any(key not in executor for key in ("buy_score", "sell_score", "buy_confirm_days", "sell_confirm_days", "cooldown_days")):
        errors.append("execution_rule_threshold_missing")
    if source == "single-backtest-rule-execution.v2":
        qualification = execution.get("qualification")
        if (not isinstance(qualification, dict)
                or qualification.get("historical_pit_eligible") is not False
                or qualification.get("performance_evaluable") is not False):
            errors.append("execution_rule_qualification_invalid")
        params = spec.config.get("params", {}) if isinstance(spec.config, dict) else {}
        if not isinstance(params, dict):
            params = {}
        parameter_keys = ("buy_score", "sell_score", "buy_confirm_days", "sell_confirm_days", "cooldown_days")
        if (executor.get("threshold_value_source") != "ScoreThresholdPolicy.fixed"
                or any(not _same_rule_number(executor.get(key), executor.get(key)) for key in parameter_keys)
                or any(key in params and not _same_rule_number(executor.get(key), params[key]) for key in parameter_keys)):
            errors.append("execution_rule_parameter_mismatch")
    if not execution.get("stock_code") or not execution.get("required_features"):
        errors.append("execution_rule_input_missing")
    # 已執行的原公式只作說明，沒有在 reader 算分／評績效／授予 PIT。
    values: dict[str, tuple[Any, str]] = {
        "name": (meta.get("name"), source + ".registry_metadata.name"),
        "description": (meta.get("description"), source + ".registry_metadata.description"),
        "entry": ({"relation": "score >= buy_score", "threshold": executor.get("buy_score"),
                   "confirm_sessions": executor.get("buy_confirm_days"), "cooldown_calendar_days": executor.get("cooldown_days")}, source + ".executor"),
        "exit": ({"relation": "score <= sell_score", "threshold": executor.get("sell_score"),
                  "confirm_sessions": executor.get("sell_confirm_days"), "cooldown_calendar_days": executor.get("cooldown_days"),
                  "risk_exits": "收盤確認停損停利，下一有效開盤執行"}, source + ".executor/broker_config"),
        "universe": ({"stock_code": execution.get("stock_code"), "membership": "explicit_single_stock"}, source + ".stock_code"),
        "period": ({"start_date": execution.get("start_date"), "end_date": execution.get("end_date")}, source + ".start_date/end_date"),
        "parameters": (spec.config, source + ".strategy_spec.config"),
        "parameter_schema": (meta.get("params", meta.get("default_params")) if source.endswith(".v2") else meta.get("params"),
                             source + (".registry_metadata.params" if "params" in meta or source.endswith(".v1") else ".registry_metadata.default_params")),
        "cost": ({"fee_bps": broker.get("fee_bps"), "slippage_bps": broker.get("slippage_bps"),
                  "sell_tax_bps": "30", "minimum_fee_currency": "20", "tax_policy": "原 BrokerSimulator next-open 的賣出稅與最低手續費"}, source + ".broker_config/source_hashes"),
        "required_features": (execution.get("required_features"), source + ".required_features"),
        "units": ({"score": "0–100 分", "fees": "bp", "price": "元", "quantity": "股", "confirmation": "交易列", "cooldown": "曆日"}, source),
        "data_insufficiency": ({"historical_availability": "unknown", "policy": "缺來源不補最新；暖機與交易樣本依原報告"}, source + ".qualification"),
        "execution_mode": (execution.get("execution_contract"), source + ".execution_contract"),
        "signal_time": ("當列收盤確認；rolling 確認只含截至當列資料", source + ".source_hashes"),
        "earliest_execution": ("下一有效可交易 session 開盤；缺開盤／停牌不補收盤", source + ".execution_contract"),
        "holding_period": ({"fixed_days": None, "policy": "依原策略出場與風控；期末未平倉只估值"}, source + ".broker_config"),
        "stop_loss": ({"ratio": broker.get("stop_loss_pct"), "atr_multiplier": broker.get("stop_loss_atr_mult"), "atr_period": broker.get("atr_period")}, source + ".broker_config"),
        "take_profit": ({"ratio": broker.get("take_profit_pct"), "atr_multiplier": broker.get("take_profit_atr_mult")}, source + ".broker_config"),
        "position_limits": ({key: broker.get(key) for key in ("sizing_mode", "fixed_amount", "risk_pct", "max_positions", "position_sizing", "allow_pyramid", "allow_reentry", "reentry_cooldown_days")}, source + ".broker_config"),
        "gap_suspension_unfilled": ({key: broker.get(key) for key in ("enable_limit_up_down", "enable_volume_constraint", "max_participation_rate")}, source + ".broker_config"),
        "benchmark": (execution.get("benchmark"), source + ".benchmark"),
        "qualification": (execution.get("qualification"), source + ".qualification"),
        "source_trace": ({"input_fingerprint": execution.get("input_fingerprint"), "source_hashes": hashes}, source + ".source_hashes/input_fingerprint"),
    }
    identity = RuleCardIdentity(spec.strategy_id, spec.strategy_version, source, _hash(dict(execution)),
                                _hash(spec.to_dict()), "historical_backtest")
    card = _card(identity, values, tuple(errors))
    from dataclasses import replace
    return replace(card, rule_status="execution_contract_bound" if not card.reasons else "not_evaluable")


def read_profile_rule_card(profile: Any) -> StrategyRuleCard:
    """Profile 只作選股設定投影；style 名稱與 validation_label 不授交易資格。"""
    payload = {"profile_id": profile.profile_id, "version": profile.version,
               "config": profile.config, "metadata": profile.metadata,
               "source_version_id": profile.source_version_id}
    source = "app_module.recommendation_profile_service.RecommendationProfile"
    identity = RuleCardIdentity(profile.profile_id, profile.version, source,
                                _hash(payload), _hash(payload), "live")
    return _card(identity, {
        "name": (profile.name, source + ".name"),
        "description": (profile.description, source + ".description"),
        "parameters": (profile.config, source + ".config"),
        "universe": ({"regime": profile.applicable_regimes}, source + ".applicable_regimes"),
    }, ("profile_execution_contract_unbound",))


def read_daily_method_rule_card(key: str, *,
                                snapshot: DailyMarketFeatureSnapshot | None = None,
                                result_kind: str = "live") -> StrategyRuleCard:
    """既有 MA 方法與已產生觀察的投影；沒有快照時只提供規則說明。"""
    contracts = method_contracts_payload() if snapshot is None else snapshot.method_contracts
    contract = contracts.get(key, {})
    source = "app_module.daily_market_method_contract.method_contracts_payload"
    source_hash = method_contracts_sha256(contracts)
    identity = RuleCardIdentity(contract.get("method_id", ""), contract.get("version", ""),
                                source, source_hash, _hash(contract), result_kind,
                                _hash(snapshot.to_dict()) if snapshot else "")
    values: dict[str, tuple[Any, str]] = {}
    errors: list[str] = []
    observed: Any = None
    qualification = "not_evaluable"
    if not contract:
        errors.append("method_contract_missing")
    else:
        for dest, origin in [("entry", "parameters"), ("parameters", "parameters"),
                             ("required_features", "required_fields")]:
            values[dest] = (contract.get(origin), source + "." + key + "." + origin)
    if snapshot:
        trace = "DailyMarketFeatureSnapshot"
        values.update({
            "universe": ({"scope_identity": snapshot.scope_identity,
                          "stock_code": snapshot.stock_code}, trace + ".scope_identity/stock_code"),
            "period": ({"decision_date": snapshot.decision_date.isoformat(),
                        "data_date": snapshot.market_date}, trace + ".decision_date/market_date"),
            "execution_mode": (snapshot.usage, trace + ".usage"),
            "qualification": ({"historical_pit_eligible": snapshot.historical_pit_eligible,
                               "official_availability_state": snapshot.official_availability_state,
                               "market_calendar_completeness": snapshot.market_calendar_completeness},
                              trace + ".policy"),
            "source_trace": ({"snapshot_identity_sha256": snapshot.snapshot_identity_sha256,
                              "input_fingerprint_sha256": snapshot.input_fingerprint_sha256,
                              "method_contracts_sha256": snapshot.method_contracts_sha256,
                              "contract_version": snapshot.contract_version}, trace),
            "units": ({item.key: item.unit for item in snapshot.features
                       if item.key in contract.get("required_fields", [])}, trace + ".features.unit"),
        })
        if not _valid_hash(snapshot.snapshot_identity_sha256) or not _valid_hash(snapshot.input_fingerprint_sha256):
            errors.append("snapshot_source_identity_missing")
        if snapshot.method_contracts_sha256 != source_hash:
            errors.append("snapshot_method_hash_mismatch")
        if not snapshot.stock_code or not snapshot.scope_identity:
            errors.append("snapshot_scope_missing")
        for key_required in contract.get("required_fields", []):
            features = [item for item in snapshot.features if item.key == key_required]
            if len(features) != 1:
                errors.append("required_feature_missing_or_duplicate:" + key_required)
                continue
            feature = features[0]
            if (feature.state != "observed" or feature.value is None or
                    not feature.value.is_finite() or feature.value <= Decimal("0") or
                    feature.data_date != snapshot.market_date or not feature.source_id or
                    not _valid_hash(feature.source_fingerprint_sha256)):
                errors.append("required_feature_unknown:" + key_required)
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", snapshot.market_date or ""):
                raise ValueError("資料日期需為 ISO 日")
            if date.fromisoformat(snapshot.market_date or "") > snapshot.decision_date:
                errors.append("future_data_date")
        except ValueError:
            errors.append("data_date_invalid")
        if result_kind != "live" or snapshot.usage != "current_observed_research_only":
            errors.append("snapshot_result_kind_mismatch")
        matches = [item for item in snapshot.conditions if item.name == key]
        if len(matches) != 1:
            errors.append("condition_missing_or_duplicate")
        else:
            condition = matches[0]
            observed = condition.to_dict()
            if (condition.method_id != identity.rule_id or condition.version != identity.rule_version
                    or dict(condition.parameters) != contract.get("parameters")
                    or condition.family != contract.get("family")
                    or condition.decision_date != snapshot.decision_date.isoformat()
                    or condition.data_date != snapshot.market_date):
                errors.append("condition_contract_mismatch")
            expected = {"above": "match", "below": "no_match", "equal": "no_match"}
            if condition.state != "unknown" and (expected.get(condition.relation) != condition.state
                    or condition.eligibility != "eligible"):
                errors.append("condition_state_invalid")
            if condition.state != "unknown" and (
                    condition.close_value is None or condition.reference_value is None or
                    condition.close_value != next((item.value for item in snapshot.features
                                                   if item.key == "close"), None) or
                    condition.reference_value != next((item.value for item in snapshot.features
                                                       if item.key != "close" and item.key in
                                                       contract.get("required_fields", [])), None)):
                errors.append("condition_feature_mismatch")
            if condition.state != "unknown" and condition.close_value is not None and condition.reference_value is not None:
                close, reference = condition.close_value, condition.reference_value
                if not close.is_finite() or not reference.is_finite():
                    errors.append("condition_values_invalid")
                else:
                    # 只核對上游既有關係，不產生或改寫訊號。
                    relation = "above" if close > reference else "below" if close < reference else "equal"
                    if relation != condition.relation:
                        errors.append("condition_relation_mismatch")
            if condition.state == "unknown":
                values["data_insufficiency"] = (condition.unknown_reason or condition.reason,
                                                trace + ".conditions.unknown_reason/reason")
                errors.append("condition_unknown")
            elif condition.state in {"match", "no_match"}:
                qualification = "eligible_observation_only"
            else:
                errors.append("condition_state_invalid")
    return _card(identity, values, tuple(errors), observation=observed,
                 observation_qualification=qualification)


@dataclass(frozen=True)
class RuleCardResultReference:
    """consumer 從已驗證結果來源組成的精確 pin；本模組只核對、不驗證績效。"""
    identity: RuleCardIdentity
    result_ref: str
    result_sha256: str


def bind_result_reference(card: StrategyRuleCard,
                          result: RuleCardResultReference) -> dict[str, Any]:
    """只提供同版同模式來源連結；沒有 metrics 或 verified-performance 升格。"""
    reasons = list(card.reasons)
    if card.identity != result.identity:
        reasons.append("result_identity_mismatch")
    if not result.result_ref or not _valid_hash(result.result_sha256):
        reasons.append("result_source_missing")
    return {"status": "not_evaluable" if reasons else "source_ref_only",
            "performance_status": "not_evaluable", "reasons": list(dict.fromkeys(reasons)),
            "result_kind": card.identity.result_kind,
            "result_ref": result.result_ref if not reasons else None,
            "result_sha256": result.result_sha256 if not reasons else None}
