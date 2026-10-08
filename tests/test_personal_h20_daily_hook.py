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


def _copy_progress_port(tmp_path, monkeypatch, consumer):
    from scripts.scheduled import personal_h20_sqlite_read_operation as operations

    ports = {}

    def operation(**kwargs):
        ports.update(kwargs)
        return SimpleNamespace(__enter__=lambda: None, close=lambda: None)

    monkeypatch.setattr(operations, "PersonalH20SQLiteReadOperation", operation)
    hook._open_personal_h20_sqlite_operation(
        sqlite_read_root=tmp_path, require_sqlite_copy=True,
        cancel_callback=None, progress_callback=consumer,
    )
    return ports["progress_callback"]


def test_large_copy_display_is_bounded_and_keeps_stage_and_final_bytes(tmp_path, monkeypatch):
    messages = []
    progress = _copy_progress_port(tmp_path, monkeypatch, messages.append)
    messages.clear()
    total = 4_054_339_584
    chunk = 1_048_576
    raw_events = 0
    stages = (("pin_source_file_group_main", "核驗原封存資料"),
              ("copy_snapshot_bytes", "建立安全副本"),
              ("finish_source_revalidation_main", "確認原封存資料未變"))
    for stage, _label in stages:
        progress(stage, 0, total)
        raw_events += 1
        for current in range(chunk, total, chunk):
            progress(stage, current, total)
            raw_events += 1
        progress(stage, total, total)
        raw_events += 1
        assert messages[-1].endswith(f"{total}/{total} 位元組。")
    assert raw_events > 11_000
    assert len(messages) <= 3 * 102
    for stage, label in stages:
        assert any(f"{label}，已核對 0/{total}" in message for message in messages)
        assert any(f"{label}，已核對 {total}/{total}" in message for message in messages)
        assert not any(stage in message for message in messages)


def test_copy_progress_same_size_new_source_restart_is_visible(tmp_path, monkeypatch):
    messages = []
    progress = _copy_progress_port(tmp_path, monkeypatch, messages.append)
    messages.clear()
    for current in (0, 50, 100, 0, 1, 100):
        progress("copy_snapshot_bytes", current, 100)
    assert len(messages) == 6
    assert sum("已核對 0/100" in message for message in messages) == 2
    assert messages[-1].endswith("100/100 位元組。")


def test_delivered_copy_progress_failure_still_aborts_read(tmp_path, monkeypatch):
    def broken_consumer(message):
        if "建立安全副本" in message:
            raise RuntimeError("display channel failed")

    progress = _copy_progress_port(tmp_path, monkeypatch, broken_consumer)
    with pytest.raises(RuntimeError, match="display channel failed"):
        progress("copy_snapshot_bytes", 0, 4_054_339_584)


def test_reader_control_stages_do_not_claim_byte_measurements(tmp_path, monkeypatch):
    messages = []
    progress = _copy_progress_port(tmp_path, monkeypatch, messages.append)
    messages.clear()
    for stage in ("pin_source_file_group", "open_private_reader", "reader_transaction_ready",
                  "finish_source_revalidation"):
        progress(stage, 0, 1)
    assert len(messages) == 4
    assert all("位元組" not in message and "0/1" not in message for message in messages)
    assert any("唯讀來源已就緒" in message for message in messages)
