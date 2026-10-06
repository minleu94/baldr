"""UX21 明示研究基準設定與保存驗證；不替呼叫者選政策。"""
from __future__ import annotations

from dataclasses import fields, replace
import json
from pathlib import Path
from typing import Any, Mapping

from app_module.rule_research_benchmark_adapter import ExplicitBenchmarkRequest, ExplicitBenchmarkResult
from app_module.rule_research_sample_capture import _digest, _json, _require

SETTINGS_SCHEMA = "rule-research-explicit-benchmark-settings.v1"
_DERIVED = {"decision_date", "endpoint_dates", "as_of_date"}
_FIELDS = {field.name for field in fields(ExplicitBenchmarkRequest)} - _DERIVED


def read_benchmark_settings(value: object) -> dict[str, Any]:
    _require(isinstance(value, Mapping) and set(value) == _FIELDS | {
        "schema_version", "version", "target_source_pin_sha256"}, "benchmark_settings_schema_invalid")
    assert isinstance(value, Mapping)
    settings = json.loads(_json(dict(value)))
    _require(len(_json(settings).encode("utf-8")) <= 48 * 1024,
             "benchmark_settings_byte_limit")
    _require(settings["schema_version"] == SETTINGS_SCHEMA
             and isinstance(settings["version"], str) and 0 < len(settings["version"]) <= 128,
             "benchmark_settings_version_invalid")
    _require(isinstance(settings["database_path"], str)
             and Path(settings["database_path"]).is_absolute(), "benchmark_database_absolute_path_required")
    for field in ("source_identity", "benchmark_name"):
        _require(isinstance(settings[field], str) and 0 < len(settings[field]) <= 256,
                 "benchmark_explicit_name_required")
    pin = settings["target_source_pin_sha256"]
    _require(pin is None or isinstance(pin, str) and len(pin) == 64
             and all(c in "0123456789abcdef" for c in pin), "benchmark_target_pin_invalid")
    return settings


def benchmark_request(settings: dict[str, Any], *, decision_date: str,
                      endpoint_dates: list[str], as_of_date: str,
                      target_source_pin: str) -> tuple[ExplicitBenchmarkRequest, str]:
    settings = read_benchmark_settings(settings)
    _require(settings["target_currency"] in {None, "TWD"}
             and settings["target_price_basis"] in {None, "unadjusted_close"},
             "benchmark_target_declared_basis_mismatch")
    declared_pin = settings["target_source_pin_sha256"]
    _require(declared_pin is None or declared_pin == target_source_pin,
             "benchmark_target_source_pin_mismatch")
    request = ExplicitBenchmarkRequest(**{field: settings[field] for field in _FIELDS},
                                      decision_date=decision_date, endpoint_dates=endpoint_dates, as_of_date=as_of_date)
    status = "caller_declared_research_only" if declared_pin is not None else "unknown"
    if declared_pin is None:
        # 尚未明示接受 target source revision，不能將宣告 basis 用於相容比較。
        request = replace(request, target_corporate_action_basis=None)
    return request, status


def result_payload(result: ExplicitBenchmarkResult) -> dict[str, Any]:
    return {"status": result.status, "reason_codes": list(result.reason_codes),
            "benchmark": None if result.benchmark is None else result.benchmark.to_payload(),
            "prices": [point.to_payload() for point in result.prices],
            "observed_rowset_sha256": result.observed_rowset_sha256,
            "observed_decision_row_sha256": result.observed_decision_row_sha256,
            "source_contract_sha256": result.source_contract_sha256,
            "source_contract_json": result.source_contract_json,
            "qualification_scope": result.qualification_scope,
            **{flag: False for flag in ("historical_pit_eligible", "formal_eligible", "training_eligible",
                                        "trading_eligible", "execution_eligible", "natural_authority")}}


def verify_saved_benchmark(source: dict[str, Any], projection: dict[str, Any],
                           runtime: dict[str, Any]) -> None:
    settings = read_benchmark_settings(source["benchmark_request"])
    _require(settings == runtime["benchmark"], "forward_saved_benchmark_runtime_mismatch")
    _require(source["target_source_pin_sha256"] == _digest(_json({
        "database": str(Path(source["database"]).resolve()), "schema_identity": source["schema_identity_sha256"],
        "database_revision_pin": source["database_revision_pin"]}).encode("utf-8")),
        "forward_saved_target_source_pin_mismatch")
    result = source["benchmark_result"]
    _require(isinstance(result, dict) and result["status"] == source["benchmark_status"]
             and result["benchmark"] == projection["benchmark"], "forward_saved_benchmark_result_mismatch")
    for flag in ("historical_pit_eligible", "formal_eligible", "training_eligible",
                 "trading_eligible", "execution_eligible", "natural_authority"):
        _require(result.get(flag) is False, "forward_saved_benchmark_qualification_invalid")
    _require(projection["cost_policy"] == runtime["cost_policy"], "forward_saved_cost_policy_mismatch")
    _require(result["status"] in {"unknown", "rejected", "qualified_research"},
             "forward_saved_benchmark_status_invalid")
    if result["source_contract_json"] is None:
        _require(result["benchmark"] is None and not result["prices"], "forward_saved_benchmark_unsealed")
        return
    text = result["source_contract_json"]
    _require(_digest(text.encode("utf-8")) == result["source_contract_sha256"],
             "forward_saved_benchmark_contract_hash_mismatch")
    contract = json.loads(text)
    _require(_json(contract) == text and contract["benchmark_name"] == settings["benchmark_name"]
             and contract["caller_source_identity"] == settings["source_identity"]
             and contract["database_path"] == str(Path(settings["database_path"]).resolve())
             and contract["decision_date"] == projection["decision_date"]
             and contract["as_of_date"] == projection["as_of_date"]
             and contract["endpoint_dates"] == source["benchmark_endpoint_dates"]
             and contract["observed_rowset_sha256"] == result["observed_rowset_sha256"]
             and contract["observed_decision_row_sha256"] == result["observed_decision_row_sha256"],
             "forward_saved_benchmark_period_or_source_mismatch")
    if result["status"] == "qualified_research":
        _require(settings["expected_rowset_sha256"] == result["observed_rowset_sha256"]
                 and settings["expected_decision_row_sha256"] == result["observed_decision_row_sha256"]
                 and settings["target_source_pin_sha256"] == source["target_source_pin_sha256"]
                 and source["target_basis_status"] == "caller_declared_research_only",
                 "forward_saved_benchmark_pin_mismatch")
        spec = result["benchmark"]
        _require(spec is not None and spec["source_identity"].endswith(result["source_contract_sha256"]),
                 "forward_saved_benchmark_spec_source_mismatch")
        _require(contract["source_metadata"] == {field: settings[field] for field in (
            "currency", "unit", "price_basis", "corporate_action_basis")},
            "forward_saved_benchmark_metadata_mismatch")
        _require(contract["target_metadata"] == {field: settings["target_" + field] for field in (
            "currency", "price_basis", "corporate_action_basis")}
                 and contract["availability_by_date"] == settings["availability_by_date"],
                 "forward_saved_benchmark_availability_or_target_basis_mismatch")
        _require([point for point in projection["price_points"] if point["instrument_id"] == spec["instrument_id"]]
                 == result["prices"], "forward_saved_benchmark_points_mismatch")
        for point in result["prices"]:
            _require(point["instrument_id"] == spec["instrument_id"]
                     and point["source_identity"] == spec["source_identity"]
                     and point["trade_date"] in contract["endpoint_dates"],
                     "forward_saved_benchmark_price_source_mismatch")
    else:
        _require(result["benchmark"] is None and not result["prices"], "forward_saved_unknown_benchmark_has_prices")
