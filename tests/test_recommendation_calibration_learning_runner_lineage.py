from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import shutil

import pytest

import ml_module.recommendation_calibration_learning_runner as runner_module
from ml_module.model_artifact_manifest import FeatureSchema
from ml_module.recommendation_calibration_learning_runner import (
    DailyRecommendationLearningRunner,
)
from ml_module.recommendation_calibration_training import (
    RecommendationCalibrationSample,
    RecommendationCalibrationTrainingConfig,
    sample_payload,
)
from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
from ml_module.recommendation_training_lineage import (
    read_recommendation_training_lineage,
)


FEATURE_SCHEMA: FeatureSchema = (
    ("momentum_bp", "int", "bp"),
    ("volume_ratio_bp", "int", "bp"),
)


def _samples(count: int = 70) -> tuple[RecommendationCalibrationSample, ...]:
    rows: list[RecommendationCalibrationSample] = []
    start = date(2025, 1, 2)
    for day_index in range(count):
        decision = start + timedelta(days=day_index)
        for symbol_index, symbol in enumerate(("1101", "2330")):
            momentum = ((day_index % 6) - 2) * 1000 + symbol_index * 170
            stock_return = momentum + symbol_index * 120
            rows.append(
                RecommendationCalibrationSample.from_forward_return(
                    row_id=f"historical-replay:{decision.isoformat()}:{symbol}",
                    symbol=symbol,
                    decision_date=decision.isoformat(),
                    feature_as_of_date=(decision - timedelta(days=1)).isoformat(),
                    feature_available_date=(decision - timedelta(days=1)).isoformat(),
                    label_end_date=(decision + timedelta(days=20)).isoformat(),
                    label_available_date=(decision + timedelta(days=20)).isoformat(),
                    feature_values=(momentum, 1000 + (day_index % 7) * 100),
                    stock_return_bp=stock_return,
                    benchmark_return_bp=100,
                    fixed_round_trip_cost_bp=50,
                    observed_liquidity_cost_bp=20,
                    rule_probability_bp=5000,
                    rule_after_cost_probability_bp=5000,
                )
            )
    return tuple(rows)


def _write_replay_manifest(path: Path, samples: tuple[RecommendationCalibrationSample, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "recommendation-historical-replay-dataset.v1",
                "dataset_id": "recommendation-dataset-fixture",
                "dataset_hash": "sha256:" + "a" * 64,
                "sample_count": len(samples),
                "decision_dates": sorted({row.decision_date for row in samples}),
                "samples": [sample_payload(row) for row in samples],
                "training_data_eligible": True,
                "forward_evidence_eligible": False,
                "formal_candidate_eligible": False,
                "candidate_blockers": [
                    "historical_replay_is_not_natural_forward_evidence"
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _historical_research_quality(**extra: object) -> dict[str, object]:
    quality: dict[str, object] = {
        "research_only": True,
        "training_semantics": "historical_research_only",
    }
    quality.update(extra)
    return quality


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _retry_runner(
    tmp_path: Path,
    *,
    training_config: RecommendationCalibrationTrainingConfig | None = None,
) -> DailyRecommendationLearningRunner:
    return DailyRecommendationLearningRunner(
        output_root=tmp_path / "retry-shadow-output",
        data_root=tmp_path / "formal-data",
        feature_names=("momentum_bp", "volume_ratio_bp"),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash="sha256:" + "b" * 64,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        training_config=training_config
        or RecommendationCalibrationTrainingConfig(
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_canonical_runner_persists_and_replays_immutable_training_lineage(
    tmp_path: Path,
) -> None:
    samples = _samples()
    replay_path = tmp_path / "replay" / "initial.json"
    bootstrap_path = tmp_path / "replay" / "bootstrap.json"
    _write_replay_manifest(replay_path, samples)
    _write_replay_manifest(bootstrap_path, samples)
    quality = {
        **_historical_research_quality(),
        "replay_dataset_manifest_path": str(replay_path),
        "source_contract": {
            "contract_id": "recommendation-forward-source-fixture",
            "contract_version": "v1",
            "status": "ready",
        },
        "training_data_eligible": True,
        "forward_evidence_eligible": False,
        "formal_candidate_eligible": False,
        "candidate_blockers": [
            "historical_replay_is_not_natural_forward_evidence"
        ],
        "historical_bootstrap": {
            "replay_manifest_path": str(bootstrap_path),
            "selection_method": "bounded_fixture",
            "row_ids": [row.row_id for row in samples],
        },
    }
    runner = DailyRecommendationLearningRunner(
        output_root=tmp_path / "shadow-output",
        data_root=tmp_path / "formal-data",
        feature_names=("momentum_bp", "volume_ratio_bp"),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash="sha256:" + "b" * 64,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        training_config=RecommendationCalibrationTrainingConfig(
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )

    first = runner.run(
        decision_date="2026-06-01",
        samples=samples,
        natural_evidence=None,
        training_as_of="2026-12-31",
        dataset_quality=quality,
        lineage_sources={"replay": samples},
    )

    assert first.status == "completed"
    assert first.idempotent_replay is False
    assert first.dataset_hash is not None
    assert first.candidate_id is not None
    assert first.training_lineage_manifest_hash is not None
    assert first.training_lineage_manifest_path is not None
    assert first.training_lineage_status == "verified"
    receipt_path = Path(first.receipt_path)
    candidate_root = Path(first.candidate_root or "")
    lineage_path = Path(first.training_lineage_manifest_path)
    assert receipt_path.is_file()
    assert (candidate_root / "candidate.json").is_file()
    assert lineage_path.is_file()

    receipt = _read_json(receipt_path)
    candidate = _read_json(candidate_root / "candidate.json")
    lineage = read_recommendation_training_lineage(
        lineage_path,
        expected_manifest_hash=first.training_lineage_manifest_hash,
        expected_dataset_hash=first.dataset_hash,
        expected_candidate_id=first.candidate_id,
    ).to_dict()
    assert receipt["training_lineage_manifest_hash"] == first.training_lineage_manifest_hash
    assert receipt["training_lineage_manifest_path"] == str(lineage_path)
    assert candidate["training_lineage_manifest_hash"] == first.training_lineage_manifest_hash
    assert candidate["training_lineage_manifest_path"] == str(lineage_path)
    assert lineage["merged_sample_count"] == len(samples)
    assert lineage["merged_sample_ids"] == sorted(
        (row.row_id for row in samples),
        key=lambda row_id: (row_id.split(":", 2)[1], row_id),
    )
    assert lineage["source_role_row_ids"]["replay"] == lineage["merged_sample_ids"]
    assert {
        item["path"] for item in lineage["replay_manifests"]
    } == {str(replay_path.resolve()), str(bootstrap_path.resolve())}
    assert lineage["replay_manifests"][0]["row_ids"]
    assert lineage["source_contract"]["status"] == "declared"
    assert lineage["training_context"]["semantics"] == "historical_research_only"
    assert lineage["training_context"]["decision_time_eligible"] is False
    assert lineage["pit"]["feature_as_of_before_decision"] is True
    assert lineage["pit"]["label_available_dates_not_after_training_as_of"] is True
    assert lineage["walk_forward"]["status"] == "reconstructed_from_training_result_fold_ids"
    assert lineage["walk_forward"]["folds"]
    assert lineage["walk_forward"]["oof"]
    assert candidate["shadow_only"] is True
    assert candidate["training_semantics"] == "historical_research_only"
    assert candidate["decision_time_eligible"] is False
    assert candidate["research_only"] is True
    assert candidate["production_action_allowed"] is False
    assert receipt["training_semantics"] == "historical_research_only"
    assert receipt["decision_time_eligible"] is False
    assert receipt["research_only"] is True
    assert receipt["formal_order_allowed"] is False

    receipt_before = receipt_path.read_bytes()
    lineage_before = lineage_path.read_bytes()
    candidate_before = (candidate_root / "candidate.json").read_bytes()
    second = runner.run(
        decision_date="2026-06-01",
        samples=samples,
        natural_evidence=None,
        training_as_of="2026-12-31",
        dataset_quality=quality,
        lineage_sources={"replay": samples},
    )
    assert second.idempotent_replay is True
    assert second.receipt_path == first.receipt_path
    assert receipt_path.read_bytes() == receipt_before
    assert lineage_path.read_bytes() == lineage_before
    assert (candidate_root / "candidate.json").read_bytes() == candidate_before


def test_runner_recovers_complete_orphan_candidate_before_refitting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    samples = _samples()
    runner = _retry_runner(tmp_path)
    fit_calls = 0
    original_fit = runner.training_service.fit

    def count_fit(**kwargs):
        nonlocal fit_calls
        fit_calls += 1
        return original_fit(**kwargs)

    monkeypatch.setattr(runner.training_service, "fit", count_fit)
    common = {
        "decision_date": "2026-06-01",
        "samples": samples,
        "natural_evidence": None,
        "training_as_of": "2026-05-29",
        "dataset_quality": {"training_data_eligible": True},
        "lineage_sources": {"replay": samples},
    }
    with pytest.raises(RuntimeError, match="injected_fault_after_candidate"):
        runner.run(**common, fault_after_candidate=True)

    run_dir = runner.runs_root / "2026-06-01"
    candidate_dirs = tuple((run_dir / "candidates").iterdir())
    assert len(candidate_dirs) == 1
    candidate_root = candidate_dirs[0]
    package_before = _tree_bytes(candidate_root)
    assert (run_dir / "run_input_identity.json").is_file()
    assert (candidate_root / "run_input_binding.json").is_file()
    assert not (run_dir / "run_receipt.json").exists()
    assert fit_calls == 1

    recovered = runner.run(**common)
    receipt = _read_json(Path(recovered.receipt_path))
    assert recovered.status == "completed"
    assert recovered.candidate_root == str(candidate_root.resolve())
    assert recovered.candidate_id == candidate_root.name
    assert recovered.training_lineage_status == "verified"
    assert fit_calls == 1
    assert _tree_bytes(candidate_root) == package_before
    assert datetime.fromisoformat(str(receipt["candidate_available_at"])) >= datetime.fromisoformat(
        str(_read_json(candidate_root / "manifest.json")["created_at"])
    )


def test_orphan_candidate_gate_metadata_tampering_fails_before_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    samples = _samples()
    runner = _retry_runner(tmp_path)
    fit_calls = 0
    authority_calls = 0
    original_fit = runner.training_service.fit
    original_authority_evaluate = runner.authority.evaluate_and_apply

    def count_fit(**kwargs):
        nonlocal fit_calls
        fit_calls += 1
        return original_fit(**kwargs)

    def count_authority_evaluate(**kwargs):
        nonlocal authority_calls
        authority_calls += 1
        return original_authority_evaluate(**kwargs)

    monkeypatch.setattr(runner.training_service, "fit", count_fit)
    monkeypatch.setattr(runner.authority, "evaluate_and_apply", count_authority_evaluate)
    common = {
        "decision_date": "2026-06-01",
        "samples": samples,
        "natural_evidence": None,
        "training_as_of": "2026-05-29",
        "dataset_quality": {"training_data_eligible": True},
        "lineage_sources": {"replay": samples},
    }
    with pytest.raises(RuntimeError, match="injected_fault_after_candidate"):
        runner.run(**common, fault_after_candidate=True)

    run_dir = runner.runs_root / "2026-06-01"
    candidate_root = next((run_dir / "candidates").iterdir())
    candidate_path = candidate_root / "candidate.json"
    original_candidate_bytes = candidate_path.read_bytes()
    original_candidate = json.loads(original_candidate_bytes.decode("utf-8"))
    assert isinstance(original_candidate, dict)
    original_blockers = original_candidate.get("candidate_blockers")
    assert isinstance(original_blockers, list)
    assert "natural_forward_evidence_must_be_supplied_to_authority" in original_blockers
    assert original_candidate.get("prospective_price_up_promotion_ready") is False
    assert fit_calls == 1
    assert authority_calls == 0
    assert not (run_dir / "run_receipt.json").exists()

    mutations = (
        (
            "blocker_removed",
            lambda payload: payload["candidate_blockers"].remove(
                "natural_forward_evidence_must_be_supplied_to_authority"
            ),
        ),
        (
            "readiness_changed",
            lambda payload: payload.__setitem__("prospective_price_up_promotion_ready", True),
        ),
        (
            "target_and_readiness_changed",
            lambda payload: payload.update(
                {
                    "prospective_price_up_promotion_ready": True,
                    "promotion_target": "after_cost_outperformance",
                }
            ),
        ),
    )
    for label, mutate in mutations:
        tampered_candidate = json.loads(original_candidate_bytes.decode("utf-8"))
        mutate(tampered_candidate)
        candidate_path.write_text(
            json.dumps(tampered_candidate, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        tampered_state = _tree_bytes(runner.root)

        with pytest.raises(
            runner_module._SameRunInputConflict,
            match="same_run_candidate_binding_mismatch_use_new_run_scope",
        ):
            runner.run(**common)

        assert _tree_bytes(runner.root) == tampered_state, label
        assert fit_calls == 1, label
        assert authority_calls == 0, label
        assert not (run_dir / "run_receipt.json").exists(), label
        candidate_path.write_bytes(original_candidate_bytes)

    assert candidate_path.read_bytes() == original_candidate_bytes


def test_runner_rejects_changed_same_run_inputs_without_mutating_saved_state(
    tmp_path: Path,
) -> None:
    samples = _samples()
    base_config = RecommendationCalibrationTrainingConfig(
        minimum_train_dates=30,
        test_date_count=5,
        purge_trading_days=20,
    )
    runner = _retry_runner(tmp_path, training_config=base_config)
    first = runner.run(
        decision_date="2026-06-01",
        samples=samples,
        natural_evidence=None,
        training_as_of="2026-05-29",
        dataset_quality={"training_data_eligible": True},
        lineage_sources={"replay": samples},
    )
    assert first.status == "completed"

    saved_root = runner.root
    before = _tree_bytes(saved_root)
    changed_sample = replace(
        samples[0],
        feature_values=(samples[0].feature_values[0] + 1, samples[0].feature_values[1]),
    )
    changed_samples = (changed_sample, *samples[1:])
    variants = (
        (
            "training_config",
            _retry_runner(
                tmp_path,
                training_config=replace(base_config, minimum_train_dates=31),
            ),
            {"samples": samples, "lineage_sources": {"replay": samples}},
        ),
        (
            "sample_payload",
            _retry_runner(tmp_path, training_config=base_config),
            {"samples": changed_samples, "lineage_sources": {"replay": samples}},
        ),
        (
            "source_group",
            _retry_runner(tmp_path, training_config=base_config),
            {"samples": samples, "lineage_sources": {"bootstrap": samples}},
        ),
        (
            "cost_scenario",
            DailyRecommendationLearningRunner(
                output_root=tmp_path / "retry-shadow-output",
                data_root=tmp_path / "formal-data",
                feature_names=("momentum_bp", "volume_ratio_bp"),
                feature_schema=FEATURE_SCHEMA,
                feature_registry_hash="sha256:" + "b" * 64,
                fixed_round_trip_cost_bp=51,
                cost_scenario=build_legacy_cost_scenario(51),
                training_config=base_config,
            ),
            {"samples": samples, "lineage_sources": {"replay": samples}},
        ),
    )
    for label, changed_runner, changed in variants:
        with pytest.raises(
            runner_module._SameRunInputConflict,
            match="same_run_input_conflict",
        ):
            changed_runner.run(
                decision_date="2026-06-01",
                samples=changed["samples"],
                natural_evidence=None,
                training_as_of="2026-05-29",
                dataset_quality={"training_data_eligible": True},
                lineage_sources=changed["lineage_sources"],
            )
        assert _tree_bytes(saved_root) == before, label


def test_runner_ignores_natural_observation_counters_in_training_identity(
    tmp_path: Path,
) -> None:
    samples = _samples()
    runner = _retry_runner(tmp_path)
    first = runner.run(
        decision_date="2026-06-01",
        samples=samples,
        natural_evidence=None,
        training_as_of="2026-05-29",
        dataset_quality={"training_data_eligible": True},
        lineage_sources={"replay": samples},
    )
    saved_root = runner.root
    before = _tree_bytes(saved_root)
    replayed = runner.run(
        decision_date="2026-06-01",
        samples=samples,
        natural_evidence=None,
        drift_status="pending",
        training_as_of="2026-05-29",
        dataset_quality={
            "training_data_eligible": True,
            "natural_training_sample_count": 999,
            "replay_sample_count": 12345,
            "forward_evidence_eligible": True,
            "formal_candidate_eligible": True,
            "candidate_blockers": [],
            "prospective_source_contract_ready": True,
            "prospective_price_up_promotion_ready": True,
            "historical_replay_candidate_blockers": [],
            "after_cost_blockers": [],
            "actual_execution_blockers": [],
            "lane_status": {"natural_forward": "matured"},
        },
        lineage_sources={"replay": samples},
    )

    assert first.status == "completed"
    assert replayed.idempotent_replay is True
    assert _tree_bytes(saved_root) == before


def test_frozen_candidate_retry_binds_package_schema_and_cost_without_mutation(
    tmp_path: Path,
) -> None:
    samples = _samples()
    runner = _retry_runner(tmp_path)
    trained = runner.run(
        decision_date="2026-06-01",
        samples=samples,
        natural_evidence=None,
        training_as_of="2026-05-29",
        dataset_quality={"training_data_eligible": True},
        lineage_sources={"replay": samples},
    )
    candidate_root = Path(trained.candidate_root or "")
    frozen_args = {
        "decision_date": "2026-06-02",
        "samples": (),
        "natural_evidence": None,
        "training_as_of": "2026-05-29",
        "dataset_quality": {"training_data_eligible": True},
        "frozen_candidate_root": candidate_root,
    }
    frozen = runner.run(**frozen_args)
    assert frozen.status == "completed"
    run_identity_path = runner.runs_root / "2026-06-02" / "run_input_identity.json"
    assert run_identity_path.is_file()

    state_before_retry = _tree_bytes(runner.root)
    repeated = runner.run(**frozen_args)
    assert repeated.idempotent_replay is True
    assert _tree_bytes(runner.root) == state_before_retry

    changed_cost_runner = DailyRecommendationLearningRunner(
        output_root=runner.root.parent,
        data_root=tmp_path / "formal-data",
        feature_names=("momentum_bp", "volume_ratio_bp"),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash="sha256:" + "b" * 64,
        fixed_round_trip_cost_bp=51,
        cost_scenario=build_legacy_cost_scenario(51),
        training_config=runner.training_config,
    )
    with pytest.raises(
        runner_module._SameRunInputConflict,
        match="same_run_frozen_candidate",
    ):
        changed_cost_runner.run(**frozen_args)
    assert _tree_bytes(runner.root) == state_before_retry

    candidate_path = candidate_root / "candidate.json"
    candidate_payload = _read_json(candidate_path)
    candidate_payload["candidate_schema_probe"] = "changed-after-frozen-run"
    candidate_path.write_text(
        json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    state_after_external_mutation = _tree_bytes(runner.root)
    with pytest.raises(
        runner_module._SameRunInputConflict,
        match="same_run_input_conflict",
    ):
        runner.run(**frozen_args)
    assert _tree_bytes(runner.root) == state_after_external_mutation


def test_runner_preserves_corrupt_orphan_and_requires_new_scope(
    tmp_path: Path,
    monkeypatch,
) -> None:
    samples = _samples()
    runner = _retry_runner(tmp_path)
    fit_calls = 0
    original_fit = runner.training_service.fit

    def count_fit(**kwargs):
        nonlocal fit_calls
        fit_calls += 1
        return original_fit(**kwargs)

    monkeypatch.setattr(runner.training_service, "fit", count_fit)
    common = {
        "decision_date": "2026-06-01",
        "samples": samples,
        "natural_evidence": None,
        "training_as_of": "2026-05-29",
        "dataset_quality": {"training_data_eligible": True},
        "lineage_sources": {"replay": samples},
    }
    with pytest.raises(RuntimeError, match="injected_fault_after_candidate"):
        runner.run(**common, fault_after_candidate=True)
    candidate_root = next((runner.runs_root / "2026-06-01" / "candidates").iterdir())
    artifact = candidate_root / "recommendation_calibration.joblib"
    artifact.write_bytes(b"tampered retained artifact")
    before = _tree_bytes(runner.root)
    with pytest.raises(
        runner_module._SameRunInputConflict,
        match="candidate_artifact_hash_mismatch.*new_run_scope",
    ):
        runner.run(**common)
    assert fit_calls == 1
    assert _tree_bytes(runner.root) == before


def test_runner_uses_actual_fit_time_and_publishes_availability_after_readback(
    tmp_path: Path,
) -> None:
    samples = _samples()
    replay_path = tmp_path / "replay" / "decision-time.json"
    _write_replay_manifest(replay_path, samples)
    quality = {
        "replay_dataset_manifest_path": str(replay_path),
        "training_data_eligible": True,
        "forward_evidence_eligible": False,
        "formal_candidate_eligible": False,
        "candidate_blockers": ["historical_replay_is_not_natural_forward_evidence"],
    }
    runner = DailyRecommendationLearningRunner(
        output_root=tmp_path / "clock-shadow-output",
        data_root=tmp_path / "formal-data",
        feature_names=("momentum_bp", "volume_ratio_bp"),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash="sha256:" + "b" * 64,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        training_config=RecommendationCalibrationTrainingConfig(
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )

    started_at = datetime.now(timezone.utc)
    result = runner.run(
        decision_date="2026-06-01",
        samples=samples,
        natural_evidence=None,
        training_as_of="2026-05-29",
        dataset_quality=quality,
        lineage_sources={"replay": samples},
    )
    completed_at = datetime.now(timezone.utc)

    assert result.status == "completed"
    assert result.training_lineage_status == "verified"
    candidate_root = Path(result.candidate_root or "")
    candidate = _read_json(candidate_root / "candidate.json")
    manifest = _read_json(candidate_root / "manifest.json")
    receipt = _read_json(Path(result.receipt_path))
    frozen_at = datetime.fromisoformat(str(candidate["candidate_frozen_at"]))
    available_at = datetime.fromisoformat(str(receipt["candidate_available_at"]))

    assert frozen_at.tzinfo is not None
    assert frozen_at.utcoffset() == timedelta(0)
    assert started_at <= frozen_at <= completed_at
    assert available_at.tzinfo is not None
    assert available_at.utcoffset() == timedelta(0)
    assert frozen_at <= available_at <= completed_at
    assert manifest["created_at"] == candidate["candidate_frozen_at"]
    assert candidate["training_as_of"] <= "2026-05-29"
    assert candidate["training_cutoff"] == "2026-05-29"
    assert candidate["training_semantics"] == "decision_time"
    assert candidate["decision_time_eligible"] is True
    assert receipt["decision_date"] == "2026-06-01"
    assert receipt["training_as_of"] == "2026-05-29"
    assert receipt["training_semantics"] == "decision_time"
    assert candidate["training_lineage_manifest_hash"] == result.training_lineage_manifest_hash
    assert "candidate_available_at" not in candidate


def test_runner_does_not_publish_availability_when_candidate_readback_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_persist = runner_module._persist_candidate_package

    def persist_then_corrupt_artifact(result, candidate_root, candidate_payload) -> None:
        original_persist(result, candidate_root, candidate_payload)
        (candidate_root / result.manifest.artifact_filename).write_bytes(b"tampered model bytes")

    monkeypatch.setattr(
        runner_module,
        "_persist_candidate_package",
        persist_then_corrupt_artifact,
    )
    runner = DailyRecommendationLearningRunner(
        output_root=tmp_path / "failed-shadow-output",
        data_root=tmp_path / "formal-data",
        feature_names=("momentum_bp", "volume_ratio_bp"),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash="sha256:" + "b" * 64,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        training_config=RecommendationCalibrationTrainingConfig(
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )

    result = runner.run(
        decision_date="2026-06-01",
        samples=_samples(),
        natural_evidence=None,
        training_as_of="2026-05-29",
        dataset_quality={"training_data_eligible": True},
    )

    receipt = _read_json(Path(result.receipt_path))
    assert result.status == "failed_lineage"
    assert receipt["status"] == "failed_lineage"
    assert "candidate_available_at" not in receipt


def test_runner_does_not_publish_availability_when_clock_precedes_freeze(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class _EarlierRunnerClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2000, 1, 1, tzinfo=tz)

    monkeypatch.setattr(runner_module, "datetime", _EarlierRunnerClock)
    runner = DailyRecommendationLearningRunner(
        output_root=tmp_path / "clock-rollback-output",
        data_root=tmp_path / "formal-data",
        feature_names=("momentum_bp", "volume_ratio_bp"),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash="sha256:" + "b" * 64,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        training_config=RecommendationCalibrationTrainingConfig(
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )

    result = runner.run(
        decision_date="2026-06-01",
        samples=_samples(),
        natural_evidence=None,
        training_as_of="2026-05-29",
        dataset_quality={"training_data_eligible": True},
    )

    receipt = _read_json(Path(result.receipt_path))
    assert result.status == "failed_lineage"
    assert receipt["status"] == "failed_lineage"
    assert "candidate_available_at" not in receipt


def test_frozen_candidate_lineage_is_legacy_unproven_or_fails_closed_when_tampered(
    tmp_path: Path,
) -> None:
    samples = _samples()
    runner = DailyRecommendationLearningRunner(
        output_root=tmp_path / "shadow-output",
        data_root=tmp_path / "formal-data",
        feature_names=("momentum_bp", "volume_ratio_bp"),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash="sha256:" + "b" * 64,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        training_config=RecommendationCalibrationTrainingConfig(
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )
    first = runner.run(
        decision_date="2026-06-01",
        samples=samples,
        natural_evidence=None,
        training_as_of="2026-12-31",
        dataset_quality=_historical_research_quality(formal_candidate_eligible=False),
        lineage_sources={"replay": samples},
    )
    candidate_root = Path(first.candidate_root or "")
    candidate_json = candidate_root / "candidate.json"
    candidate_bytes_before = candidate_json.read_bytes()

    legacy_root = tmp_path / "legacy-candidate"
    shutil.copytree(candidate_root, legacy_root)
    legacy_payload = _read_json(legacy_root / "candidate.json")
    legacy_payload.pop("training_lineage_manifest_hash", None)
    legacy_payload.pop("training_lineage_manifest_path", None)
    (legacy_root / "candidate.json").write_text(
        json.dumps(legacy_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    legacy = runner.run(
        decision_date="2026-06-02",
        samples=(),
        natural_evidence=None,
        training_as_of="2026-12-31",
        dataset_quality=_historical_research_quality(),
        frozen_candidate_root=legacy_root,
    )
    legacy_receipt = _read_json(Path(legacy.receipt_path))
    assert legacy.status == "completed"
    assert legacy.training_lineage_status == "legacy_unproven"
    assert legacy_receipt["training_lineage_status"] == "legacy_unproven"
    assert legacy_receipt["steps"]["training_lineage"] == "legacy_unproven"

    for suffix, removed_key, decision_date in (
        (
            "hash-only",
            "training_lineage_manifest_path",
            "2026-06-04",
        ),
        (
            "path-only",
            "training_lineage_manifest_hash",
            "2026-06-05",
        ),
    ):
        partial_root = tmp_path / suffix
        shutil.copytree(candidate_root, partial_root)
        partial_payload = _read_json(partial_root / "candidate.json")
        partial_payload.pop(removed_key, None)
        (partial_root / "candidate.json").write_text(
            json.dumps(partial_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        partial = runner.run(
            decision_date=decision_date,
            samples=(),
            natural_evidence=None,
            training_as_of="2026-12-31",
            dataset_quality=_historical_research_quality(),
            frozen_candidate_root=partial_root,
        )
        partial_receipt = _read_json(Path(partial.receipt_path))
        assert partial.status == "failed_lineage"
        assert partial.training_lineage_status == "invalid"
        assert partial_receipt["training_lineage_status"] == "invalid"
        assert partial_receipt["decision_reason"] == "frozen_candidate_lineage_invalid_fail_closed"

    tampered_root = tmp_path / "tampered-candidate"
    shutil.copytree(candidate_root, tampered_root)
    tampered_lineage_path = tmp_path / "tampered-lineage.json"
    tampered_lineage = _read_json(Path(first.training_lineage_manifest_path or ""))
    tampered_lineage["dataset_hash"] = "sha256:" + "c" * 64
    tampered_lineage_path.write_text(
        json.dumps(tampered_lineage, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    tampered_payload = _read_json(tampered_root / "candidate.json")
    tampered_payload["training_lineage_manifest_path"] = str(tampered_lineage_path)
    (tampered_root / "candidate.json").write_text(
        json.dumps(tampered_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    tampered = runner.run(
        decision_date="2026-06-03",
        samples=(),
        natural_evidence=None,
        training_as_of="2026-12-31",
        dataset_quality=_historical_research_quality(),
        frozen_candidate_root=tampered_root,
    )
    tampered_receipt = _read_json(Path(tampered.receipt_path))
    assert tampered.status == "failed_lineage"
    assert tampered.training_lineage_status == "invalid"
    assert tampered_receipt["training_lineage_status"] == "invalid"
    assert tampered_receipt["decision_reason"] == "frozen_candidate_lineage_invalid_fail_closed"
    assert candidate_json.read_bytes() == candidate_bytes_before


def test_runner_rejects_future_training_cutoff_without_explicit_research_context(
    tmp_path: Path,
) -> None:
    runner = DailyRecommendationLearningRunner(
        output_root=tmp_path / "shadow-output",
        data_root=tmp_path / "formal-data",
        feature_names=("momentum_bp", "volume_ratio_bp"),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash="sha256:" + "b" * 64,
        fixed_round_trip_cost_bp=50,
        training_config=RecommendationCalibrationTrainingConfig(
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )

    result = runner.run(
        decision_date="2026-06-01",
        samples=_samples(),
        natural_evidence=None,
        training_as_of="2026-12-31",
    )

    assert result.status == "failed_training"
    assert result.decision == "retain_current"
    assert result.training_lineage_status == "failed"
    assert "requires_explicit_historical_research_semantics" in result.reason
    assert result.candidate_root is None
    receipt = _read_json(Path(result.receipt_path))
    assert receipt["decision_reason"] == "training_cutoff_invalid_fail_closed"
    assert receipt["training_lineage_status"] == "failed"
    assert not (tmp_path / "shadow-output" / "recommendation_learning" / "training_lineage").exists()
