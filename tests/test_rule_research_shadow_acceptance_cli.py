"""CLI 的缺件、安全參數、來源重驗及新程序收據重讀。"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from app_module.rule_research_sample_capture import BoundedRuleResearchCaptureWriter
from scripts.run_rule_research_shadow_acceptance import main
from tests.test_rule_research_forward_isolated import pipeline
from tests.test_rule_research_label_readiness import _saved


def test_missing_configuration_is_plain_fallback(pipeline, capsys):
    parent, outcome, _ = _saved(pipeline)
    assert main(["--receipt", str(parent), str(outcome), "--case-id", "cli-missing"]) == 0
    summary = capsys.readouterr().out
    assert "未啟用" in summary and "未合格" in summary
    assert "{" not in summary


@pytest.mark.parametrize("args", [[], ["--case-id", "empty"], ["--identity", "a" * 64],
    ["--store", "output/qa/ux23-empty"], ["--save"]])
def test_explicit_arguments_required(args, capsys):
    assert main(args + ["--json"]) == 2
    assert json.loads(capsys.readouterr().out)["shadow_enabled"] is False


def test_saved_missing_configuration_reopens_in_new_process(pipeline, tmp_path, monkeypatch, capsys):
    parent, outcome, _ = _saved(pipeline)
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter, "_free_bytes", lambda self: 10**12)
    store = tmp_path / "ux23-cli-store"
    args = ["--receipt", str(parent), str(outcome), "--case-id", "cli-repeat",
            "--save", "--store", str(store), "--json"]
    assert main(args) == 0
    saved = json.loads(capsys.readouterr().out)
    identity = saved["receipt"]["capture_identity_sha256"]
    read_args = ["--store", str(store), "--identity", identity, "--json"]
    assert main(read_args) == 0
    first = json.loads(capsys.readouterr().out)
    second = subprocess.run([sys.executable, "scripts/run_rule_research_shadow_acceptance.py", *read_args],
                            capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(second.stdout) == first
    assert "未啟用" in first["capture"]["summary_text"]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "duplicate"


def test_read_rejects_new_inputs_without_writing(tmp_path, capsys):
    store = tmp_path / "absent"
    assert main(["--store", str(store), "--identity", "a" * 64,
                 "--case-id", "ambiguous", "--json"]) == 2
    assert not store.exists()
    assert json.loads(capsys.readouterr().out)["reason"] == "exact_read_requires_only_store_and_identity"


def test_invalid_config_rejected_without_receipt(pipeline, tmp_path, capsys):
    parent, outcome, _ = _saved(pipeline)
    export = tmp_path / "invalid.json"
    export.write_text('{"model_id":"one","model_id":"two"}', encoding="utf-8")
    assert main(["--receipt", str(parent), str(outcome), "--case-id", "bad-config",
                 "--lifecycle-export", str(export), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "rejected"
