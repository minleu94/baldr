"""中央日常 exact entry 登記與歷史自然 caller；僅合成資料。"""
from types import SimpleNamespace
from pathlib import Path

from app_module.recommendation.personal_current_observed_h20_capture import digest, encoded
from scripts.scheduled import personal_h20_natural_hook as hook
from tests.test_personal_h20_natural_outcome_batch import cohort, attach, snapshot


def setup_hook(tmp_path, monkeypatch):
    args, body, entry, outcome = cohort(tmp_path)
    attach(args, entry, outcome)
    activation = SimpleNamespace(enabled=True, personal_root=str(args["root"]),
        candidate_id=body["candidate_id"], model_contract_hash=body["contract_hash"])
    monkeypatch.setattr(hook, "read_personal_h20_activation", lambda path: activation)
    ports = {key: args[key] for key in ("prediction_reader", "source_verifier", "contract_verifier",
        "input_capture_verifier", "outcome_verifier")}
    daily = dict(body, effective_model_run=True, receipt_path=str(args["manifest_path"]),
        receipt_sha256=args["manifest_sha256"])
    capture = dict(status="captured", cycle_id=body["cycle_id"], decision_date=body["decision_date"],
        capture_path=str(args["input_capture_path"]), capture_sha256=args["input_capture_sha256"])
    pins = {key: str(args[key]) for key in ("outcome_path", "outcome_sha256")}
    pins.update(capture_path=capture["capture_path"], capture_sha256=capture["capture_sha256"])
    return args, ports, daily, capture, pins


def test_registered_entry_replays_original_cohort_and_mature_join_idempotently(tmp_path, monkeypatch):
    args, ports, daily, entry, pins = setup_hook(tmp_path, monkeypatch)
    sources = {Path(args[key]): (Path(args[key]).read_bytes(), Path(args[key]).stat().st_mtime_ns)
        for key in ("manifest_path", "input_capture_path", "outcome_path")}
    result = hook.register_personal_h20_natural_entry(tmp_path / "config", daily=daily, entry=entry, ports=ports)
    assert result["pending_count"] == 2 and result["matured_count"] == 0
    assert Path(result["entry_binding_path"]).name == entry["capture_sha256"][7:] + ".json"
    matured = hook.consume_personal_h20_natural_outcome(tmp_path / "config", pins=pins, ports=ports)
    assert matured["matured_count"] == 2 and matured["symbols"] == daily["symbols"]
    before = snapshot(args)
    assert hook.consume_personal_h20_natural_outcome(tmp_path / "config", pins=pins, ports=ports) == matured
    assert snapshot(args) == before
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == value for p, value in sources.items())
    assert len(list((args["root"] / "h20_predictions").iterdir())) == 2
    assert len(list((args["root"] / "h20_outcome_joins").iterdir())) == 2


def test_midnight_mismatch_keeps_full_pending_and_does_not_register_entry(tmp_path, monkeypatch):
    args, ports, daily, entry, pins = setup_hook(tmp_path, monkeypatch)
    entry["decision_date"] = "2026-10-01"
    result = hook.register_personal_h20_natural_entry(tmp_path / "config", daily=daily, entry=entry, ports=ports)
    assert result["pending_count"] == 2 and result["symbols"] == daily["symbols"]
    assert "entry_binding_path" not in result
    assert not (args["root"] / "h20_natural_entry_bindings").exists()
    assert hook.consume_personal_h20_natural_outcome(tmp_path / "config", pins=pins, ports=ports)["status"] == "pending"


def test_exact_registered_entry_source_tamper_blocks_without_new_joins(tmp_path, monkeypatch):
    args, ports, daily, entry, pins = setup_hook(tmp_path, monkeypatch)
    hook.register_personal_h20_natural_entry(tmp_path / "config", daily=daily, entry=entry, ports=ports)
    Path(pins["capture_path"]).write_bytes(b"tampered")
    result = hook.consume_personal_h20_natural_outcome(tmp_path / "config", pins=pins, ports=ports)
    assert result["status"] == "blocked" and result["promotion_credit_created"] is False
    assert not (args["root"] / "h20_outcome_joins").exists()


def test_unconfigured_hook_has_zero_ports_or_io(tmp_path, monkeypatch):
    monkeypatch.setattr(hook, "_ports", lambda: (_ for _ in ()).throw(AssertionError("unexpected ports")))
    assert hook.register_personal_h20_natural_entry(None, daily={}, entry={}) == {"status": "not_configured"}
    assert hook.consume_personal_h20_natural_outcome(None, pins={}) == {"status": "not_configured"}
    assert not list(tmp_path.iterdir())
