"""中央 invocation 接線：未配置零模型呼叫、raw-cycle 身分與 entry pending。"""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.recommendation.personal_h20_activation import (
    PersonalH20Activation, publish_personal_h20_activation,
)
from scripts.scheduled import personal_h20_daily_hook as hook


def _activation(tmp_path):
    return PersonalH20Activation(1, True, "personal.default", str(tmp_path / "market"),
        str(tmp_path / "private"), str(tmp_path / "fit.json"), "sha256:" + "a" * 64,
        "candidate", "model", "sha256:" + "b" * 64, "2014-01-01")


def _binding():
    pins = {key: "raw-run" if key == "raw_run_id" else "pin-" + key for key in hook.SOURCE_PIN_KEYS}
    return dict(pins, binding_mode="current_observed", decision_date="2026-10-06",
        feature_as_of_date="2026-10-05", symbols=["2330", "1101"],
        current_observed_feature_snapshot={"symbols": ["2330", "1101"],
            "entry_observation": {"status": "pending"}}, observed_at="caller-clock-forbidden")


def _contract(*args, **kwargs):
    return {"contract_hash": "sha256:" + "b" * 64,
        "contract": {"candidate_id": "candidate", "model_id": "model"}}


def test_unconfigured_and_disabled_do_not_touch_source_contract_or_runner(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("unconfigured/disabled touched model or source")

    monkeypatch.setattr(hook, "read_personal_h20_activation", forbidden)
    assert hook.run_personal_h20_for_current_cycle(None, None, market_root=tmp_path,
        expected_raw_run_id=None, runner=forbidden, contract_verifier=forbidden)["status"] == "not_configured"
    activation = replace(_activation(tmp_path), enabled=False)
    monkeypatch.setattr(hook, "read_personal_h20_activation", lambda path: activation)
    assert hook.run_personal_h20_for_current_cycle(activation.config_path, None, market_root=tmp_path,
        expected_raw_run_id=None, runner=forbidden, contract_verifier=forbidden)["status"] == "disabled"


def test_public_config_entry_pending_still_dispatches_exact_frozen_request(tmp_path):
    activation = _activation(tmp_path)
    publish_personal_h20_activation(activation, expected_revision=0, execute=True)
    before = activation.config_path.read_bytes()
    calls = []

    def runner(**kwargs):
        calls.append(kwargs)
        return {"status": "synthetic_port_received", "effective_model_run": False}

    result = hook.run_personal_h20_for_current_cycle(activation.config_path, _binding(),
        market_root=Path(activation.market_root), expected_raw_run_id="raw-run",
        runner=runner, contract_verifier=_contract)
    assert result["status"] == "synthetic_port_received"
    assert len(calls) == 1
    request = calls[0]["request"]
    assert set(request) == {"schema_version", "data_root", "source_pins", "symbols",
        "history_start_date", "expected_feature_as_of_date"}
    assert request["symbols"] == ["1101", "2330"]
    assert request["data_root"] == activation.market_root
    assert request["source_pins"]["raw_run_id"] == "raw-run"
    assert "observed_at" not in request["source_pins"]
    assert "natural_outcome" not in request
    assert calls[0]["receipt_root"] == Path(activation.personal_root)
    assert result["activation_revision"] == 1
    assert activation.config_path.read_bytes() == before


@pytest.mark.parametrize("mutation,reason", [
    ({"raw_run_id": "other-run"}, "exact_raw_run_required"),
    ({"cycle_terminal_sha256": None}, "complete_source_pins_required"),
    ({"symbols": ["1101"]}, "complete_feature_scope_required"),
    ({"feature_as_of_date": "2026-10-06"}, "feature_not_before_decision"),
    ({"current_observed_feature_snapshot": {"symbols": ["1101", "1101"]}}, "unique_feature_scope_required"),
])
def test_invocation_mismatch_never_dispatches_model(tmp_path, monkeypatch, mutation, reason):
    activation = _activation(tmp_path)
    monkeypatch.setattr(hook, "read_personal_h20_activation", lambda path: activation)
    binding = _binding()
    binding.update(mutation)
    result = hook.run_personal_h20_for_current_cycle(activation.config_path, binding,
        market_root=Path(activation.market_root), expected_raw_run_id="raw-run",
        runner=lambda **kwargs: pytest.fail("mismatch dispatched"), contract_verifier=_contract)
    assert result["status"] == "blocked"
    assert reason in result["reason"]
    assert result["effective_model_run"] is False


def test_contract_mismatch_and_runner_failure_are_visible(tmp_path, monkeypatch):
    activation = _activation(tmp_path)
    monkeypatch.setattr(hook, "read_personal_h20_activation", lambda path: activation)
    kwargs = dict(market_root=Path(activation.market_root), expected_raw_run_id="raw-run")
    result = hook.run_personal_h20_for_current_cycle(activation.config_path, _binding(), **kwargs,
        contract_verifier=lambda *a, **k: {"contract_hash": "wrong"},
        runner=lambda **k: pytest.fail("wrong contract dispatched"))
    assert "activation_contract_mismatch" in result["reason"]

    def fail(**kwargs):
        raise ValueError("original_source_byte_hash_changed")

    result = hook.run_personal_h20_for_current_cycle(activation.config_path, _binding(), **kwargs,
        contract_verifier=_contract, runner=fail)
    assert result == {"status": "blocked", "reason": "original_source_byte_hash_changed", "effective_model_run": False}


def test_pipeline_forwards_opt_in_without_changing_original_cycle_arguments(tmp_path):
    from scripts.scheduled.run_daily_recommendation_learning_pipeline import _learning_child_arguments

    class Cycle:
        def learning_arguments(self, **kwargs):
            return ["--current-observed-expected-raw-run-id", "exact-run"]

    args = SimpleNamespace(history_start_date="2014-01-01", fixed_round_trip_cost_bp=50,
        max_decision_dates=10, cost_scenario="fixed", capture_active_model=False,
        calendar_cache_path=None, temporary_closure_cache_path=None, cost_policy_estimate_date=None,
        personal_h20_activation_config=None, symbols=None, temporary_closure_path=None)
    kwargs = dict(args=args, data_root=tmp_path, output_root=tmp_path, source_db=tmp_path / "source.sqlite",
        decision_date="2026-10-06", snapshot_result_id="result", snapshot_cohort_hash="hash",
        snapshot_invocation_output_sha256="raw", snapshot_invocation_output_path="invocation",
        current_cycle_pin=Cycle(), current_observed_source_output_root=tmp_path)
    original = _learning_child_arguments(**kwargs)
    args.personal_h20_activation_config = tmp_path / "private" / "activation.json"
    enabled = _learning_child_arguments(**kwargs)
    index = enabled.index("--personal-h20-activation-config")
    assert enabled[index + 1] == str(args.personal_h20_activation_config)
    assert enabled[:index] + enabled[index + 2:] == original
    assert original[original.index("--current-observed-expected-raw-run-id") + 1] == "exact-run"


def test_completed_hook_publishes_only_verified_full_scope_and_failure_preserves_pointer(tmp_path):
    import json
    from tests.test_personal_h20_product_evidence import _store
    from app_module.recommendation.personal_h20_product_evidence import read_personal_h20_product_for_stock
    activation, prediction, daily, reader = _store(tmp_path)
    body = json.loads(daily.read_bytes())
    binding = _binding()
    binding["symbols"] = ["2330"]
    binding["current_observed_feature_snapshot"]["symbols"] = ["2330"]
    binding["cycle_id"] = "cycle"
    result = hook.run_personal_h20_for_current_cycle(activation.config_path, binding,
        market_root=Path(activation.market_root), expected_raw_run_id="raw-run",
        contract_verifier=_contract, runner=lambda **k: body,
        prediction_reader=reader, daily_reader=reader)
    assert result["effective_model_run"] is True
    assert read_personal_h20_product_for_stock(activation.config_path, stock_code="2330",
        market_root=Path(activation.market_root), daily_reader=reader, prediction_reader=reader).gross_return_bp == 123
    pointer = Path(activation.personal_root) / "h20_product_reference.json"
    before = pointer.read_bytes(), pointer.stat().st_mtime_ns
    failed = hook.run_personal_h20_for_current_cycle(activation.config_path, binding,
        market_root=Path(activation.market_root), expected_raw_run_id="raw-run",
        contract_verifier=_contract, runner=lambda **k: dict(body, captures=[]),
        prediction_reader=reader, daily_reader=reader)
    assert failed["effective_model_run"] is False
    assert (pointer.read_bytes(), pointer.stat().st_mtime_ns) == before
