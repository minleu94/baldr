"""CLI preserves explicit policies and reports absent candidates plainly."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.run_rule_research_fair_comparison import MAX_BUNDLE_BYTES, main
from app_module.rule_research_label_readiness import build_label_readiness_batch
from tests.test_rule_research_fair_comparison import _prepared, _bundle_for
from tests.test_rule_research_forward_isolated import pipeline
from tests.test_rule_research_label_readiness import _saved


def test_missing_configuration_is_plain_research_result(pipeline, capsys):
    parent, outcome, _ = _saved(pipeline)
    assert main(["--receipt", str(parent), str(outcome)]) == 0
    text = capsys.readouterr().out
    assert "ML" in text
    assert "{" not in text


def test_missing_configuration_json_is_repeatable_in_new_process(pipeline, capsys):
    parent, outcome, _ = _saved(pipeline)
    args = ["--receipt", str(parent), str(outcome), "--json"]
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    result = subprocess.run([sys.executable, "scripts/run_rule_research_fair_comparison.py", *args],
                            capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(result.stdout) == first
    assert first["training_eligible"] is False
    assert first["formal_eligible"] is False
    assert first["status"] != "comparable"


@pytest.mark.parametrize("content", ['{"version":"1","version":"2"}', '[]'])
def test_bundle_duplicate_keys_and_non_object_rejected(pipeline, tmp_path, capsys, content):
    parent, outcome, _ = _saved(pipeline)
    path = tmp_path / "bundle.json"
    path.write_text(content, encoding="utf-8")
    assert main(["--receipt", str(parent), str(outcome), "--inputs-bundle", str(path), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "rejected"


def test_bundle_bound_rejected_without_truncation(pipeline, tmp_path, capsys):
    parent, outcome, _ = _saved(pipeline)
    path = tmp_path / "bundle.json"
    path.write_bytes(b" " * (MAX_BUNDLE_BYTES + 1))
    assert main(["--receipt", str(parent), str(outcome), "--inputs-bundle", str(path), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "fair_inputs_bundle_byte_bound"


def test_complete_export_is_scored_then_candidate_missing_is_plain(pipeline, tmp_path, capsys):
    receipts, labels, split, policy = _prepared(pipeline)
    bundle = _bundle_for(build_label_readiness_batch(receipts, labels, split), policy)
    args = []
    for parent, outcome in receipts:
        args += ["--receipt", str(parent), str(outcome)]
    for option, value in (("--label-policy", labels), ("--split-policy", split),
                          ("--comparison-policy", policy), ("--inputs-bundle", bundle)):
        path = tmp_path / (option.removeprefix("--") + ".json")
        path.write_text(json.dumps(value), encoding="utf-8")
        args += [option, str(path)]
    assert main(args + ["--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "research_only_comparison"
    assert result["common_cohort"]["count"] == 2
    assert result["training_eligible"] is False
    bundle["candidate"] = None
    (tmp_path / "inputs-bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    assert main(args) == 0
    summary = capsys.readouterr().out
    assert "候選模型" in summary
    assert "未計算兩模型指標" in summary
