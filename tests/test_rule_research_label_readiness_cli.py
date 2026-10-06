"""新程序僅讀封存來源；明示設定、缺件與錯誤不改舊收據。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from app_module.rule_research_forward_store import run_forward_isolated
from tests.test_rule_research_forward_isolated import pipeline

CLI = Path(__file__).resolve().parents[1] / "scripts" / "run_rule_research_label_readiness.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True,
                          text=True, encoding="utf-8", check=False)


def test_new_process_same_saved_source_and_missing_policy(pipeline):
    args, parent, _, runtime, *_ = pipeline
    saved = run_forward_isolated(runtime, execute=True)
    assert saved["status"] == "saved", saved
    paths = [Path(parent), Path(saved["receipt_path"]), Path(args["db_path"])]
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    first = _run("--receipt", str(parent), saved["receipt_path"])
    second = _run("--receipt", str(parent), saved["receipt_path"])
    assert first.returncode == second.returncode == 0, first.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)
    assert {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths} == before
    assert "label_policy" in first.stdout
    database = Path(args["db_path"])
    parked = database.with_suffix(".parked-fixture")
    database.rename(parked)
    try:
        without_database = _run("--receipt", str(parent), saved["receipt_path"])
        assert without_database.returncode == 0, without_database.stderr
        assert json.loads(without_database.stdout) == json.loads(first.stdout)
    finally:
        parked.rename(database)


def test_explicit_policy_and_split_rejected_without_touching_sources(pipeline):
    _, parent, _, runtime, *_ = pipeline
    saved = run_forward_isolated(runtime, execute=True)
    policy = runtime.parent / "label-policy.json"
    policy.write_text(json.dumps({"schema_version": "rule-research-label-policy.v1",
        "policy_id": "fixture-gross", "version": "1", "measure": "gross", "horizons": [5, 10, 20]}), encoding="utf-8")
    explicit = _run("--receipt", str(parent), saved["receipt_path"], "--label-policy", str(policy))
    assert explicit.returncode == 0, explicit.stderr
    assert "fixture-gross" in explicit.stdout
    bad = runtime.parent / "bad-policy.json"
    bad.write_text(json.dumps({"schema_version": "future.v99"}), encoding="utf-8")
    rejected = _run("--receipt", str(parent), saved["receipt_path"], "--label-policy", str(bad))
    assert rejected.returncode == 2 and json.loads(rejected.stdout)["status"] == "rejected"
    oversized = runtime.parent / "oversized-policy.json"
    oversized.write_bytes(b" " * (64 * 1024 + 1))
    rejected = _run("--receipt", str(parent), saved["receipt_path"], "--label-policy", str(oversized))
    assert rejected.returncode == 2 and "label_config_byte_bound" in rejected.stdout


def test_duplicate_policy_keys_are_not_silently_selected(tmp_path):
    policy = tmp_path / "duplicate.json"
    policy.write_text('{"measure":"gross","measure":"net"}', encoding="utf-8")
    result = _run("--receipt", "unused-parent", "unused-outcome", "--label-policy", str(policy))
    assert result.returncode == 2
    assert "label_config_duplicate_key" in result.stdout
