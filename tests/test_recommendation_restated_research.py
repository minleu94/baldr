from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ml_module.current_restated_research_bridge import (
    CurrentRestatedResearchInvocation,
)
from scripts.scheduled import (
    run_banktaiwan_recommendation_learning_daily as bank,
    run_daily_recommendation_learning as legacy,
    run_daily_recommendation_learning_pipeline as pipeline,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _invocation(tmp_path: Path) -> CurrentRestatedResearchInvocation:
    artifact_root = tmp_path / "output" / "ml_research"
    return CurrentRestatedResearchInvocation(
        source_context_path=artifact_root / "context.json",
        source_context_sha256="1" * 64,
        outcome_receipt_path=artifact_root / "direct" / "receipt.json",
        outcome_receipt_sha256="2" * 64,
        raw_publication_manifest_sha256="3" * 64,
        raw_dataset_manifest_sha256="4" * 64,
        outcome_feature_registry_sha256="5" * 64,
        b_consumption_receipt_path=artifact_root / "b" / "receipt.json",
        b_consumption_receipt_sha256="6" * 64,
        b_candidate_manifest_sha256="7" * 64,
        b_adapted_manifest_sha256="8" * 64,
        b_feature_registry_sha256="9" * 64,
        model_manifest_path=artifact_root / "model" / "manifest.json",
        model_manifest_sha256="a" * 64,
        model_bundle_sha256="b" * 64,
        current_symbols=("2317", "2330"),
        current_event_date="2026-10-02",
        b_current_observation_freeze="2026-10-02T23:30:00+00:00",
        inference_at=None,
        output_root=artifact_root,
    )


def _result(*, lane: str = "legacy", binding: str = "c" * 64) -> SimpleNamespace:
    return SimpleNamespace(
        status="verified_research_sidecar",
        receipt_path=Path("output/ml_research/source_row_research") / lane / "receipt.json",
        receipt_sha256="d" * 64,
        binding_sha256=binding,
        sample_cohort_sha256="e" * 64,
        core19_numeric_vector_sha256_by_symbol={
            "2317": "f" * 64,
            "2330": "0" * 64,
        },
        payload={},
    )


def _snapshot_reference_file(path: Path) -> tuple[bytes, str, str]:
    cohort_hash = "sha256:" + ("1" * 64)
    payload = {
        "task": "baldr-recommendation-snapshot-daily",
        "decision_date": "2026-10-02",
        "status": "passed",
        "result_id": "snapshot-20261002-run-1",
        "snapshot_cohort": {
            "schema_version": "scheduled-recommendation-snapshot-cohort.v1",
            "cohort_hash": cohort_hash,
            "eligible_symbols": ["1101", "1301", "2881"],
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw, cohort_hash, "sha256:" + hashlib.sha256(raw).hexdigest()


def test_legacy_research_entry_reuses_verified_sidecar_and_keeps_formal_lane_blocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation = _invocation(tmp_path)
    calls: list[dict[str, Any]] = []

    def fake_sidecar(received: Any, **kwargs: Any) -> SimpleNamespace:
        calls.append({"invocation": received, **kwargs})
        return _result()

    monkeypatch.setattr(legacy, "parse_current_restated_research_invocation", lambda _args: invocation)
    monkeypatch.setattr(legacy, "run_current_restated_research_sidecar", fake_sidecar)
    monkeypatch.setattr(
        legacy,
        "TWStockConfig",
        lambda **_kwargs: pytest.fail("research entry must return before formal configuration"),
    )

    assert legacy.main(["--current-restated-research-only"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "verified_research_sidecar"
    assert payload["lane"] == "legacy"
    assert payload["receipt_sha256"] == "d" * 64
    assert payload["core19_numeric_vector_sha256_by_symbol"].keys() == {"2317", "2330"}
    assert payload["model_training_performed"] is False
    assert payload["verified_model_reused"] is True
    assert payload["formal_calibration_performed"] is False
    assert payload["formal_order_allowed"] is False
    assert payload["historical_pit_eligible"] is False
    assert len(calls) == 1
    assert calls[0]["invocation"] is invocation
    assert calls[0]["lane"] == "legacy"
    assert calls[0]["cost_scenario"].fixed_round_trip_cost_bp == 50
    assert calls[0].get("upstream_terminal_receipt_path") is None


def test_legacy_research_opt_in_without_complete_pins_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        legacy,
        "run_current_restated_research_sidecar",
        lambda *_args, **_kwargs: pytest.fail("invalid research pins must not call the sidecar"),
    )
    assert legacy.main(["--current-restated-research-only"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["reason"] == "current_restated_research_input_invalid"
    assert payload["formal_calibration_performed"] is False


def test_pipeline_snapshot_reference_is_read_only_and_never_becomes_training_cohort(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "formal-output" / "runs" / "snapshot.stdout.bin"
    _raw, cohort_hash, output_sha = _snapshot_reference_file(snapshot_path)
    invocation = _invocation(tmp_path)
    args = Namespace(
        output_root=snapshot_path.parents[1],
        research_reference_snapshot_result_id="snapshot-20261002-run-1",
        research_reference_snapshot_cohort_hash=cohort_hash,
        research_reference_snapshot_output_path=snapshot_path,
        research_reference_snapshot_output_sha256=output_sha,
    )
    monkeypatch.setattr(
        pipeline,
        "_read_regular_file_no_follow",
        lambda path, _root, **_kwargs: path.read_bytes(),
    )

    reference = pipeline._validate_research_reference_snapshot(
        args,
        research_invocation=invocation,
    )

    assert reference["cohort_relation"] == "no_symbol_overlap_reference_only"
    assert reference["source_row_symbols"] == ["2317", "2330"]
    assert reference["overlap_symbols"] == []
    assert reference["used_as_research_training_cohort"] is False


def test_pipeline_reference_snapshot_hash_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "formal-output" / "runs" / "snapshot.stdout.bin"
    _raw, cohort_hash, _output_sha = _snapshot_reference_file(snapshot_path)
    args = Namespace(
        output_root=snapshot_path.parents[1],
        research_reference_snapshot_result_id="snapshot-20261002-run-1",
        research_reference_snapshot_cohort_hash=cohort_hash,
        research_reference_snapshot_output_path=snapshot_path,
        research_reference_snapshot_output_sha256="sha256:" + ("0" * 64),
    )
    monkeypatch.setattr(
        pipeline,
        "_read_regular_file_no_follow",
        lambda path, _root, **_kwargs: path.read_bytes(),
    )
    with pytest.raises(ValueError, match="bytes differ"):
        pipeline._validate_research_reference_snapshot(
            args,
            research_invocation=_invocation(tmp_path),
        )


def test_pipeline_verifies_legacy_terminal_before_exposing_bank_barrier(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation = _invocation(tmp_path)
    binding = "a" * 64
    child = {
        "schema_version": "daily-recommendation-learning-research-only.v1",
        "status": "verified_research_sidecar",
        "terminal": True,
        "lane": "legacy",
        "receipt_path": str(tmp_path / "output" / "ml_research" / "legacy-receipt.json"),
        "receipt_sha256": "b" * 64,
        "binding_sha256": binding,
        "sample_cohort_sha256": "c" * 64,
        "core19_numeric_vector_sha256_by_symbol": {"2317": "d" * 64, "2330": "e" * 64},
        "model_training_performed": False,
        "verified_model_reused": True,
        "formal_calibration_performed": False,
        "historical_pit_eligible": False,
        "decision_time_eligible": False,
    }
    reference = {
        "cohort_relation": "no_symbol_overlap_reference_only",
        "source_row_symbols": ["2317", "2330"],
        "overlap_symbols": [],
        "used_as_research_training_cohort": False,
    }
    command_observed: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        command_observed.append(command)
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is False
        return SimpleNamespace(returncode=0, stdout=json.dumps(child).encode("utf-8"), stderr=b"")

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)
    monkeypatch.setattr(
        pipeline,
        "current_restated_research_input_binding_sha256",
        lambda _invocation: binding,
    )
    monkeypatch.setattr(
        pipeline,
        "verify_current_restated_legacy_terminal_receipt",
        lambda path, **kwargs: {
            "sample_cohort_sha256": child["sample_cohort_sha256"],
            "core19_numeric_vector_sha256_by_symbol": child[
                "core19_numeric_vector_sha256_by_symbol"
            ],
            "lane": "legacy",
            "terminal": True,
            "receipt_path": str(path),
            "expected_binding_sha256": kwargs["expected_binding_sha256"],
        },
    )
    args = Namespace(
        child_timeout_seconds=120,
        cost_scenario="legacy_fixed_bp",
        fixed_round_trip_cost_bp=50,
        research_order_amount_twd=None,
        research_order_quantity_shares=None,
    )

    assert pipeline._run_current_restated_research_pipeline(
        args,
        research_invocation=invocation,
        reference_snapshot=reference,
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "verified_research_sidecar"
    assert payload["terminal"] is True
    assert payload["receipt_sha256"] == child["receipt_sha256"]
    assert payload["binding_sha256"] == binding
    assert payload["recommendation_reference_snapshot"]["cohort_relation"] == (
        "no_symbol_overlap_reference_only"
    )
    assert payload["model_training_performed"] is False
    assert len(command_observed) == 1
    assert "run_daily_recommendation_learning.py" in command_observed[0][1]
    assert "--cost-scenario" in command_observed[0]
    assert "legacy_fixed_bp" in command_observed[0]


def test_pipeline_rejects_ambiguous_or_nonterminal_legacy_stdout() -> None:
    with pytest.raises(ValueError, match="missing or ambiguous"):
        pipeline._research_child_payload_from_stdout(b"{}\n{}\n")
    bad = {
        "schema_version": "daily-recommendation-learning-research-only.v1",
        "status": "blocked",
        "terminal": True,
        "lane": "legacy",
    }
    with pytest.raises(ValueError, match="required terminal contract"):
        pipeline._research_child_payload_from_stdout(json.dumps(bad).encode("utf-8"))


def test_bank_requires_legacy_terminal_barrier_and_reuses_same_pins(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    invocation = _invocation(tmp_path)
    receipt_path = tmp_path / "output" / "ml_research" / "legacy" / "receipt.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text("placeholder; API is mocked", encoding="utf-8")
    args = bank.build_parser().parse_args(
        [
            "--current-restated-research-only",
            "--research-upstream-terminal-receipt",
            str(receipt_path),
            "--research-upstream-terminal-receipt-sha256",
            "f" * 64,
            "--research-expected-upstream-binding-sha256",
            "a" * 64,
        ]
    )
    monkeypatch.setattr(bank, "parse_current_restated_research_invocation", lambda _args: invocation)
    calls: list[dict[str, Any]] = []

    def fake_sidecar(received: Any, **kwargs: Any) -> SimpleNamespace:
        calls.append({"invocation": received, **kwargs})
        return _result(lane="banktaiwan", binding="a" * 64)

    monkeypatch.setattr(bank, "run_current_restated_research_sidecar", fake_sidecar)
    code, payload = bank.run_once(args)

    assert code == 0
    assert payload["status"] == "verified_research_sidecar"
    assert payload["lane"] == "banktaiwan"
    assert payload["upstream_legacy_terminal_receipt_sha256"] == "f" * 64
    assert payload["model_training_performed"] is False
    assert payload["broker_action"] is False
    assert len(calls) == 1
    assert calls[0]["invocation"] is invocation
    assert calls[0]["lane"] == "banktaiwan"
    assert calls[0]["cost_scenario"].is_estimated is True
    assert calls[0]["upstream_terminal_receipt_path"] == receipt_path
    assert calls[0]["expected_upstream_terminal_receipt_sha256"] == "f" * 64
    assert calls[0]["expected_upstream_binding_sha256"] == "a" * 64


def test_bank_missing_or_unscoped_upstream_barrier_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    invocation = _invocation(tmp_path)
    monkeypatch.setattr(bank, "parse_current_restated_research_invocation", lambda _args: invocation)
    monkeypatch.setattr(
        bank,
        "run_current_restated_research_sidecar",
        lambda *_args, **_kwargs: pytest.fail("incomplete upstream barrier must not call the sidecar"),
    )
    research_args = bank.build_parser().parse_args(["--current-restated-research-only"])
    code, payload = bank.run_once(research_args)
    assert code == 2
    assert payload["reason"] == "current_restated_research_requires_complete_legacy_terminal_barrier"

    unscoped_args = bank.build_parser().parse_args(
        [
            "--research-upstream-terminal-receipt-sha256",
            "a" * 64,
        ]
    )
    monkeypatch.setattr(bank, "parse_current_restated_research_invocation", lambda _args: None)
    code, payload = bank.run_once(unscoped_args)
    assert code == 2
    assert payload["reason"] == "upstream_terminal_pins_require_current_restated_research_opt_in"
