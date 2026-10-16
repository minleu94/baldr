"""已保存 Research Run 的唯讀規則來源核對；不產生規則 pin 或績效資格。"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import Decimal, DecimalException, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
import json
import re
from typing import Any
from app_module.research_run_dtos import ResearchRunMetadataDTO, canonical_json, normalize_research_run_json_value
from app_module.research_run_service import ResearchRunService
from app_module.strategy_rule_card_readmodel import (RuleCardIdentity, RuleCardResultReference, StrategyRuleCard, bind_result_reference, read_strategy_rule_card, read_single_backtest_execution_rule_card)
from decision_module.strategies.contracts import StrategySpec

_KINDS = {"single_backtest": "historical_backtest", "batch_backtest_stock": "historical_backtest", "fixed_basket_stock": "historical_backtest", "research_forward": "research_forward"}


def metadata_sha256(metadata: ResearchRunMetadataDTO) -> str:
    return hashlib.sha256(canonical_json(normalize_research_run_json_value(asdict(metadata))).encode("utf-8")).hexdigest()


def _sha(value: str) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", value))


def _costs(metadata: ResearchRunMetadataDTO) -> tuple[dict[str, int] | None, str | None]:
    raw = metadata.original_input.get("raw_params", {})
    if not isinstance(raw, dict) or not all(key in raw for key in ("fee_bps", "slippage_bps")):
        return None, "cost_source_missing"
    result = {}
    for source, target in (("fee_bps", "fee_bp_x100"), ("slippage_bps", "slippage_bp_x100")):
        recorded = getattr(metadata, target)
        if type(recorded) is not int or recorded < 0 or isinstance(raw[source], bool):
            return None, "cost_type_invalid"
        try:
            scaled = Decimal(str(raw[source])) * Decimal("100")
        except (InvalidOperation, ValueError):
            return None, "cost_type_invalid"
        if not scaled.is_finite() or scaled != scaled.to_integral_value() or scaled != recorded:
            return None, "cost_value_mismatch"
        result[target] = recorded
    return result, None


def result_context_sha256(metadata: ResearchRunMetadataDTO) -> str:
    """核對保存時的聲明；consumer 不把回傳值寫成來源 pin。"""
    costs, _ = _costs(metadata)
    context = {"run_id": metadata.run_id, "result_kind": _KINDS.get(metadata.run_type, "unknown"),
               "strategy_id": metadata.strategy_id, "strategy_version": metadata.strategy_version,
               "params": metadata.normalized_params, "parameter_contract_version": metadata.parameter_contract_version,
               "universe": metadata.universe, "capital_cents": metadata.capital_cents,
               "stop_loss_bp": metadata.stop_loss_bp, "take_profit_bp": metadata.take_profit_bp,
               "sizing_mode": metadata.sizing_mode,
               "start_date": metadata.start_date, "end_date": metadata.end_date,
               "data_cutoff_date": metadata.data_cutoff_date, "data_fingerprint": metadata.data_fingerprint,
               "payload_hash": metadata.payload_hash, "costs": costs,
               "execution_contract": metadata.execution_contract,
               "benchmark": metadata.benchmark_results or None}
    return hashlib.sha256(canonical_json(normalize_research_run_json_value(context)).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SavedStrategyRuleCard:
    rule_card: StrategyRuleCard
    source_status: str
    result_kind: str
    result_ref: str | None
    reasons: tuple[str, ...]
    origin_json: str
    performance_status: str = "not_evaluable"

    @property
    def origin(self) -> dict[str, Any]:
        return json.loads(self.origin_json)

    def to_dict(self) -> dict[str, Any]:
        return {"source_status": self.source_status, "result_kind": self.result_kind,
                "result_ref": self.result_ref, "reasons": list(self.reasons), "origin": self.origin,
                "performance_status": self.performance_status, "rule_card": self.rule_card.to_dict()}


def load_saved_strategy_rule_card(service: ResearchRunService, expected: ResearchRunMetadataDTO) -> SavedStrategyRuleCard:
    """使用既有完整性 reader；不建立 service、回抓、save 或替舊來源補章。"""
    loaded = service.load_run_data(expected.run_id)
    metadata = loaded.metadata
    errors: list[str] = []
    if metadata_sha256(metadata) != metadata_sha256(expected):
        errors.append("selected_source_changed")
    kind = _KINDS.get(metadata.run_type, "unknown")
    if kind == "unknown":
        errors.append("result_kind_unbound")
    raw_spec = metadata.data_manifest.get("strategy_spec")
    spec = None
    if isinstance(raw_spec, dict):
        try:
            spec = StrategySpec.from_dict(raw_spec)
            if not isinstance(spec.config, dict):
                spec = None
        except (TypeError, ValueError):
            pass
    if spec is None:
        errors.append("saved_strategy_spec_missing")
        # 只說明保存的參數，缺版不借目前1.0／defaults；結果連結保持拒絕。
        spec = StrategySpec(metadata.strategy_id, metadata.strategy_version, config={"params": metadata.normalized_params})
    if (spec.strategy_id != metadata.strategy_id or spec.strategy_version != metadata.strategy_version
            or spec.config.get("params") != metadata.normalized_params):
        errors.append("saved_strategy_identity_mismatch")
    if spec.data_version != metadata.data_fingerprint:
        errors.append("spec_data_source_unbound")
    if not metadata.strategy_version or metadata.strategy_version == "unknown":
        errors.append("saved_strategy_version_missing")
    try:
        start, end, cutoff = (date.fromisoformat(value) for value in (metadata.start_date, metadata.end_date, metadata.data_cutoff_date))
        if start > end or cutoff < end:
            errors.append("result_window_invalid")
    except (TypeError, ValueError):
        errors.append("result_date_invalid")
    if not metadata.universe or any(not isinstance(code, str) or not code for code in metadata.universe):
        errors.append("result_universe_missing")
    if not _sha(metadata.payload_hash) or not _sha(metadata.data_fingerprint):
        errors.append("result_source_hash_missing")
    if metadata.execution_contract == "unversioned":
        errors.append("execution_contract_missing")
    costs, cost_error = _costs(metadata)
    if cost_error:
        errors.append(cost_error)
    execution = metadata.data_manifest.get("single_backtest_rule_execution")
    card = (read_single_backtest_execution_rule_card(spec, execution)
            if isinstance(execution, dict) and metadata.run_type == "single_backtest"
            else read_strategy_rule_card(spec, result_kind=kind))
    if isinstance(execution, dict):
        if (metadata.run_type != "single_backtest" or execution.get("stock_code") not in metadata.universe
                or not isinstance(execution.get("start_date"), str) or not isinstance(execution.get("end_date"), str)
                or str(execution.get("start_date")) < metadata.start_date or str(execution.get("end_date")) > metadata.end_date
                or execution.get("execution_contract") != metadata.execution_contract
                or execution.get("benchmark") != (metadata.benchmark_results or None)):
            errors.append("execution_rule_result_context_mismatch")
        if execution.get("schema") == "single-backtest-rule-execution.v2":
            broker = execution.get("broker_config")
            if not isinstance(broker, dict):
                errors.append("execution_rule_saved_cost_mismatch")
            else:
                # 由保存的整數單位構造精確Decimal，不用caller context乘除或補目前費率。
                for key, recorded, exponent in (
                    ("fee_bps", metadata.fee_bp_x100, -2),
                    ("slippage_bps", metadata.slippage_bp_x100, -2),
                ):
                    raw = broker.get(key)
                    try:
                        matches = (key in broker and (raw is None if recorded is None else type(recorded) is int
                                   and not isinstance(raw, bool)
                                   and Decimal(str(raw)).is_finite()
                                   and Decimal(str(raw)) == Decimal(str(recorded) + "E" + str(exponent))))
                    except (DecimalException, TypeError, ValueError):
                        matches = False
                    if not matches:
                        errors.append("execution_rule_saved_cost_mismatch")
                        break
                # 舊 pct_to_bp 實為 ratio*100 的整數百分比；不能當真 bp 反推精確原 ratio。
                # 精確值交叉核原輸入，再核舊整數投影，避免拒絕 0.055 等原合法值。
                original = metadata.original_input.get("raw_params", {})
                for key, risk_recorded in (("stop_loss_pct", metadata.stop_loss_bp),
                                      ("take_profit_pct", metadata.take_profit_bp)):
                    raw = broker.get(key)
                    expected_raw = original.get(key) if isinstance(original, dict) else None
                    try:
                        matches = (key in broker and isinstance(original, dict) and key in original
                                   and not isinstance(raw, bool) and not isinstance(expected_raw, bool))
                        if raw is None or expected_raw is None:
                            matches = matches and raw is None and expected_raw is None and risk_recorded is None
                        else:
                            value, expected_value = Decimal(str(raw)), Decimal(str(expected_raw))
                            with localcontext() as context:
                                context.prec = 60
                                matches = (matches and type(risk_recorded) is int and value.is_finite()
                                           and expected_value.is_finite() and value == expected_value
                                           and int((value * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP)) == risk_recorded)
                    except (DecimalException, TypeError, ValueError, OverflowError):
                        matches = False
                    if not matches:
                        errors.append("execution_rule_saved_cost_mismatch")
                        break
    card = replace(card, identity=replace(card.identity, context_sha256=result_context_sha256(metadata)))
    pin = metadata.data_manifest.get("rule_card_identity")
    saved_identity = None
    if isinstance(pin, dict) and all(isinstance(value, str) for value in pin.values()):
        try:
            saved_identity = RuleCardIdentity(**pin)
        except TypeError:
            pass
    if saved_identity is None:
        errors.append("saved_rule_pin_missing")
    elif saved_identity != card.identity:
        errors.append("saved_rule_pin_mismatch")
    errors.extend(card.reasons)
    errors = list(dict.fromkeys(errors))
    card = replace(card, reasons=tuple(errors))
    reference = None
    status = "not_evaluable"
    if not errors and saved_identity is not None:
        bound = bind_result_reference(card, RuleCardResultReference(saved_identity,
                  "research-run:" + metadata.run_id, metadata_sha256(metadata)))
        status, reference = bound["status"], bound["result_ref"]
    origin = {"run_id": metadata.run_id, "run_name": metadata.run_name, "strategy_version": metadata.strategy_version,
              "universe": metadata.universe, "start_date": metadata.start_date, "end_date": metadata.end_date,
              "data_cutoff_date": metadata.data_cutoff_date, "costs": costs,
              "benchmark": metadata.benchmark_results or None, "execution_contract": metadata.execution_contract,
              "metadata_sha256": metadata_sha256(metadata), "payload_hash": metadata.payload_hash,
              "data_fingerprint": metadata.data_fingerprint, "equity_sha256": metadata.equity_parquet_hash,
              "trades_sha256": metadata.trades_parquet_hash,
              "equity_path": metadata.equity_path, "trades_path": metadata.trades_path}
    return SavedStrategyRuleCard(card, status, kind, reference, tuple(errors), canonical_json(normalize_research_run_json_value(origin)))
