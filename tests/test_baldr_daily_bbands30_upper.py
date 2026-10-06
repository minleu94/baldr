"""日常版號接線的 fail-closed 邊界，不操作正式來源。"""
from copy import deepcopy
import json
import sqlite3
import os
from pathlib import Path

import pytest

import app_module.rule_research_daily_owner as owner
import app_module.rule_research_observation_acceptance as acceptance
from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION,
    DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER as V3,
    feature_contract_for_version,
)
from tests.test_rule_research_observation_acceptance import context
from tests.test_rule_research_observation_acceptance import context as observation_context
from tests.test_rule_research_daily_owner import ctx


def test_v3_actual_daily_owner_parent_acceptance_and_exact_replay(ctx):
    """Exercise the real owner, parent publisher and acceptance on an isolated source."""
    path, day, runtime, args, policy = ctx
    with sqlite3.connect(args["db_path"]) as connection:
        connection.execute("ALTER TABLE technical_indicators ADD COLUMN BB_Upper TEXT")
        connection.execute("UPDATE technical_indicators SET BB_Upper='100'")
    runtime["feature_contract_version"] = V3
    policy["feature_contract_version"] = V3
    path.write_text(json.dumps(runtime), encoding="utf-8")
    Path(runtime["policy_config"]).write_text(json.dumps(policy), encoding="utf-8")
    source_pin = (args["db_path"].read_bytes(), args["db_path"].stat().st_mtime_ns)
    result = owner.run_daily_owner(path, day, execute=True)
    assert result["status"] == "observed", result
    attempt = result["attempts"][0]
    assert attempt["acceptance_status"] == "accepted_research_observation"
    identity = attempt["parent_capture"]["receipt"]["capture_identity_sha256"]
    from app_module.rule_research_parent_capture import read_parent_rule_sample_readiness
    ready = read_parent_rule_sample_readiness(
        args["snapshot_root"], args["capture_root"], universe_path=args["universe_path"],
        identity_sha256=identity, contract_version=V3)
    assert ready["feature_contract_version"] == V3
    assert len(ready["method_counts"]) == 3
    assert ready["uncaptured_member_count"] == 0
    def extended_pin(p):
        local = Path("\\\\?\\" + str(p.resolve())) if os.name == "nt" else p
        return local.read_bytes(), local.stat().st_mtime_ns

    pins = {p: extended_pin(p)
            for role in ("snapshot_root", "capture_root", "acceptance_root")
            for p in Path(runtime[role]).rglob("*.json")}
    replay = owner.run_daily_owner(path, day, execute=True)
    assert replay["status"] == "already_observed", replay
    assert replay["attempts"] == []
    assert all(extended_pin(p) == pin for p, pin in pins.items())
    assert source_pin == (args["db_path"].read_bytes(), args["db_path"].stat().st_mtime_ns)
    assert result["qualification"]["source_availability"] == "unknown"
    assert result["qualification"]["training_eligible"] is False


def test_original_policy_retains_v2_shape_and_hash(context):
    _, path, _, value = context
    policy = acceptance.load_observation_policy(path)
    assert policy["value"] == value
    assert "feature_contract_version" not in policy["value"]
    assert policy["method_contracts_sha256"] == feature_contract_for_version(
        DAILY_MARKET_FEATURE_CONTRACT_VERSION).method_contracts_sha256


def test_v3_policy_binds_exact_method_hash_and_rejects_forgery(context):
    _, path, _, value = context
    value["feature_contract_version"] = V3
    path.write_text(json.dumps(value), encoding="utf-8")
    policy = acceptance.load_observation_policy(path)
    assert policy["method_contracts_sha256"] == feature_contract_for_version(V3).method_contracts_sha256
    forged = deepcopy(policy)
    forged["method_contracts_sha256"] = feature_contract_for_version(
        DAILY_MARKET_FEATURE_CONTRACT_VERSION).method_contracts_sha256
    with pytest.raises(ValueError, match="observation_method_contract_binding_invalid"):
        acceptance._validate_policy(forged)


@pytest.mark.parametrize("version", [None, True, "unknown", ""])
def test_invalid_version_rejected_before_parent(context, version):
    _, path, _, value = context
    value["feature_contract_version"] = version
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError):
        acceptance.load_observation_policy(path)


def test_runtime_policy_mismatch_rejects_before_production(ctx, monkeypatch):
    path, day, runtime, _, _ = ctx
    runtime["feature_contract_version"] = V3
    path.write_text(json.dumps(runtime), encoding="utf-8")
    monkeypatch.setattr(owner, "produce_parent_rule_samples", lambda **kwargs: pytest.fail("producer called"))
    result = owner.run_daily_owner(path, day, execute=True)
    assert result["status"] in {"blocked", "unconfigured"}
    assert result["error_code"] == "daily_feature_contract_policy_mismatch"
    assert result["attempts"] == []


def test_v3_runtime_and_policy_readback_bind_same_version(ctx):
    path, _, runtime, _, value = ctx
    runtime["feature_contract_version"] = V3
    value["feature_contract_version"] = V3
    path.write_text(json.dumps(runtime), encoding="utf-8")
    policy_path = runtime["policy_config"]
    from pathlib import Path
    Path(policy_path).write_text(json.dumps(value), encoding="utf-8")
    assert owner.load_daily_runtime(path)["value"]["feature_contract_version"] == V3


@pytest.mark.parametrize("version", [None, V3])
def test_owner_forwards_only_explicit_version_to_parent(ctx, monkeypatch, version):
    path, day, runtime, _, value = ctx
    if version is not None:
        runtime["feature_contract_version"] = version
        value["feature_contract_version"] = version
        from pathlib import Path
        Path(runtime["policy_config"]).write_text(json.dumps(value), encoding="utf-8")
        path.write_text(json.dumps(runtime), encoding="utf-8")
    calls = []

    def bounded_parent_spy(**kwargs):
        calls.append(kwargs)
        raise ValueError("injected_parent_boundary")

    monkeypatch.setattr(owner, "produce_parent_rule_samples", bounded_parent_spy)
    result = owner.run_daily_owner(path, day, execute=True)
    assert calls, result
    for call in calls:
        if version is None:
            assert "contract_version" not in call
        else:
            assert call["contract_version"] == V3
    assert result["status"] != "observed"
    assert result["qualification"]["training_eligible"] is False
