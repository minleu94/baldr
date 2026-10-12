"""日常中央 H20 與推薦母體分流；不授來源或自然成熟資格。"""
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.scheduled import run_daily_recommendation_learning as learning
from scripts.scheduled import personal_h20_daily_hook as daily_hook
from app_module.recommendation import personal_h20_activation as activation_module


def test_legacy_lane_keeps_historical_outcome_scan_without_new_h20_registration(tmp_path, monkeypatch):
    from scripts.scheduled import personal_h20_natural_hook
    seen = []
    def forbidden(*args, **kwargs):
        raise AssertionError("一般推薦不得登記新 H20 entry")
    def scan(**kwargs):
        seen.append(kwargs["personal_h20_activation_config"])
        return {"status": "pending", "reason": "natural_maturity_pending"}
    monkeypatch.setattr(personal_h20_natural_hook, "register_personal_h20_natural_entry", forbidden)
    monkeypatch.setattr(learning, "_current_observed_natural_research_fit", scan)
    monkeypatch.setattr(learning, "_natural_maturity_calendar_paths", lambda **kwargs: (None, None))
    monkeypatch.setattr(learning, "NaturalMaturitySessionResolver", lambda **kwargs: object())
    activation = tmp_path / "activation.json"
    result = learning._run_current_observed_natural_research_lane(
        learning_output_root=tmp_path, data_root=tmp_path, source_db=tmp_path / "market.sqlite",
        source_contract_audit={}, current_feature_snapshot={}, decision_date=date(2026, 10, 12),
        evaluation_at=datetime(2026, 10, 12, 13, tzinfo=timezone.utc),
        fixed_round_trip_cost_bp=50, cost_scenario=learning.build_legacy_cost_scenario(50),
        capture_requested=False, calendar_cache_path=None, temporary_closure_path=None,
        personal_h20_activation_config=activation, personal_h20_register_entry=False)
    assert seen == [activation]
    assert result["current_observed_input_capture"]["status"] == "not_requested"
    assert "personal_h20_natural" not in result["current_observed_input_capture"]


def setup_lane(tmp_path, monkeypatch):
    terminal = {"schema_version": "current-stock-research-cycle-terminal.v1", "status": "completed",
                "raw_run_id": "raw-exact", "cycle_id": "raw-exact", "current_symbols": ["2330", "1101"]}
    path = tmp_path / "terminal.json"
    path.write_text(json.dumps(terminal), encoding="utf-8")
    pin = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    activation = SimpleNamespace(enabled=True, market_root=str(tmp_path / "market"), history_start_date="2014-01-01")
    monkeypatch.setattr(activation_module, "read_personal_h20_activation", lambda _: activation)
    seen = []

    def snapshot(**kwargs):
        seen.append(("snapshot", kwargs))
        return {"status": "captured", "symbols": list(kwargs["symbols"]), "verified": True}

    def audit(**kwargs):
        seen.append(("audit", kwargs))
        return {"source_contract": {"fixture": True}}

    def binding(value):
        return {"binding_mode": "current_observed", "symbols": ["1101", "2330"]}, None

    def daily(*args, **kwargs):
        seen.append(("daily", (args, kwargs)))
        return {"status": "completed", "effective_model_run": True}

    def natural(**kwargs):
        seen.append(("natural", kwargs))
        return {"status": "pending", "current_observed_input_capture": {"status": "captured",
                 "personal_h20_natural": {"status": "completed"}},
                "current_observed_natural_research": {"status": "pending", "matured_row_count": 0}}

    monkeypatch.setattr(learning, "_current_observed_feature_snapshot_for_learning", snapshot)
    monkeypatch.setattr(learning, "_audit_source_contract", audit)
    monkeypatch.setattr(learning, "_capture_source_contract_binding", binding)
    monkeypatch.setattr(daily_hook, "run_personal_h20_for_current_cycle", daily)
    monkeypatch.setattr(learning, "_run_current_observed_natural_research_lane", natural)
    request = dict(config_path=tmp_path / "activation.json", config=SimpleNamespace(data_root=Path(activation.market_root)),
                   canonical_output_root=tmp_path / "canonical", learning_output_root=tmp_path / "learning",
                   source_artifact_root=tmp_path / "sources", source_db=tmp_path / "market.sqlite",
                   decision_date=date(2026, 10, 12), observed_at=datetime(2026, 10, 12, 13, tzinfo=timezone.utc),
                   expected_raw_run_id="raw-exact", expected_cycle_terminal=path,
                   expected_cycle_terminal_sha256=pin, fixed_round_trip_cost_bp=50,
                   cost_scenario=learning.build_legacy_cost_scenario(50), calendar_cache_path=tmp_path / "calendar",
                   temporary_closure_path=None, capture_requested=True)
    return request, seen, activation, terminal


def test_central_lane_uses_complete_terminal_cohort_and_separate_natural_root(tmp_path, monkeypatch):
    request, seen, _, _ = setup_lane(tmp_path, monkeypatch)
    result = learning._run_personal_h20_central_natural_lane(**request)
    assert result["status"] == "completed_with_pending"
    assert result["symbols"] == ["1101", "2330"]
    assert [name for name, _ in seen] == ["snapshot", "audit", "daily", "natural"]
    assert seen[0][1]["symbols"] == ("1101", "2330")
    assert "snapshot_cohort" not in seen[0][1]
    assert seen[-1][1]["learning_output_root"] == request["learning_output_root"] / "personal_h20_natural"
    assert seen[-1][1]["source_contract_audit"]["personal_h20_daily"]["effective_model_run"] is True
    assert seen[-1][1]["personal_h20_activation_config"] == request["config_path"]
    assert result["formal_training_allowed"] is False
    assert result["promotion_credit_created"] is False
    assert result["current_observed_natural_research"]["matured_row_count"] == 0


@pytest.mark.parametrize("mutation", [{"status": "failed"}, {"raw_run_id": "other"},
                                      {"cycle_id": "other"}, {"current_symbols": ["2330", "2330"]}])
def test_invalid_central_terminal_never_reaches_model_or_capture(tmp_path, monkeypatch, mutation):
    request, seen, _, terminal = setup_lane(tmp_path, monkeypatch)
    terminal.update(mutation)
    path = request["expected_cycle_terminal"]
    path.write_text(json.dumps(terminal), encoding="utf-8")
    request["expected_cycle_terminal_sha256"] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    result = learning._run_personal_h20_central_natural_lane(**request)
    assert result["status"] in {"pending", "blocked"}
    assert seen == []


def test_terminal_pin_tamper_never_reaches_model(tmp_path, monkeypatch):
    request, seen, _, _ = setup_lane(tmp_path, monkeypatch)
    request["expected_cycle_terminal"].write_bytes(b"tampered")
    result = learning._run_personal_h20_central_natural_lane(**request)
    assert result["status"] == "blocked"
    assert seen == []


def test_disabled_activation_does_not_read_terminal_or_source(tmp_path, monkeypatch):
    request, seen, activation, _ = setup_lane(tmp_path, monkeypatch)
    activation.enabled = False
    request["expected_cycle_terminal"].unlink()
    assert learning._run_personal_h20_central_natural_lane(**request)["status"] == "disabled"
    assert seen == []


def test_registration_blocker_does_not_become_completed(tmp_path, monkeypatch):
    request, _, _, _ = setup_lane(tmp_path, monkeypatch)
    monkeypatch.setattr(learning, "_run_current_observed_natural_research_lane", lambda **_: {
        "status": "pending", "current_observed_input_capture": {
            "status": "captured", "personal_h20_natural": {"status": "blocked", "reason": "wrong_entry"}},
        "current_observed_natural_research": {"status": "pending"}})
    result = learning._run_personal_h20_central_natural_lane(**request)
    assert result["status"] == "blocked"
    assert result["current_observed_input_capture"]["personal_h20_natural"]["reason"] == "wrong_entry"
