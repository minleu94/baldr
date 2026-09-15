from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import shutil

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
