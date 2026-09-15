from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ml_module.recommendation_calibration_training import (
    RecommendationCalibrationSample,
    RecommendationCalibrationTrainingConfig,
    sample_payload,
)
from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
from ml_module.recommendation_training_lineage import (
    RecommendationTrainingLineageError,
    build_recommendation_training_lineage,
    persist_recommendation_training_lineage,
    recommendation_training_dataset_hash,
    read_recommendation_training_lineage,
)


FEATURE_SCHEMA = (
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


def _replay_manifest(path: Path, samples: tuple[RecommendationCalibrationSample, ...]) -> None:
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
                "candidate_blockers": ["historical_replay_is_not_natural_forward_evidence"],
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


def test_training_lineage_persists_complete_source_and_readback_identity(tmp_path: Path) -> None:
    samples = _samples(35)
    replay_path = tmp_path / "datasets" / "replay.json"
    _replay_manifest(replay_path, samples)
    scenario = build_legacy_cost_scenario(50)
    config = RecommendationCalibrationTrainingConfig(
        minimum_train_dates=30,
        test_date_count=5,
        purge_trading_days=20,
    )
    training_result = SimpleNamespace(
        fold_ids=("fold-001",),
        evaluation_fold_id="fold-001",
        evaluation={"evaluation_sample_fingerprint": "sha256:" + "b" * 64},
    )
    dataset_hash = recommendation_training_dataset_hash(samples)
    lineage = build_recommendation_training_lineage(
        learning_root=tmp_path / "shadow" / "recommendation_learning",
        run_id="daily-recommendation-learning:2026-06-01",
        run_scope=None,
        decision_date="2026-06-01",
        training_as_of="2026-12-31",
        dataset_id="recommendation-dataset-merged",
        dataset_hash=dataset_hash,
        samples=samples,
        feature_schema=FEATURE_SCHEMA,
        fixed_round_trip_cost_bp=50,
        cost_scenario=scenario,
        dataset_quality={
            **_historical_research_quality(),
            "replay_dataset_manifest_path": str(replay_path),
            "source_contract": {"status": "ready", "contract_hash": "sha256:" + "d" * 64},
        },
        training_result=training_result,
        training_config=config,
        candidate_id="rec-cal-fixture",
        candidate_manifest_hash="sha256:" + "e" * 64,
        candidate_artifact_hash="sha256:" + "f" * 64,
        source_groups={"replay": samples},
    )
    manifest_path = persist_recommendation_training_lineage(
        tmp_path / "shadow" / "recommendation_learning",
        lineage,
    )
    before = manifest_path.read_bytes()
    same_path = persist_recommendation_training_lineage(
        tmp_path / "shadow" / "recommendation_learning",
        lineage,
    )
    assert same_path == manifest_path
    assert manifest_path.read_bytes() == before

    readback = read_recommendation_training_lineage(
        manifest_path,
        expected_manifest_hash=lineage.manifest_hash,
        expected_dataset_hash=dataset_hash,
        expected_candidate_id="rec-cal-fixture",
    )
    payload = readback.to_dict()
    assert payload["merged_sample_count"] == len(samples)
    assert payload["merged_sample_ids"] == [row.row_id for row in sorted(samples, key=lambda row: (row.decision_date, row.symbol, row.row_id))]
    assert payload["source_groups"]["supplied_by_caller"] is True
    assert payload["source_role_row_ids"]["replay"] == payload["merged_sample_ids"]
    assert payload["natural_sample_ids"] == []
    assert payload["replay_manifests"][0]["row_ids"] == sorted(row.row_id for row in samples)
    assert payload["walk_forward"]["status"] == "reconstructed_from_training_result_fold_ids"
    assert payload["cost_scenario_hash"] == scenario.scenario_hash
    assert payload["pit"]["feature_as_of_before_decision"] is True
    assert payload["pit"]["label_available_dates_not_after_training_as_of"] is True


def test_training_lineage_readback_rejects_tampered_body(tmp_path: Path) -> None:
    samples = _samples(2)
    dataset_hash = recommendation_training_dataset_hash(samples)
    lineage = build_recommendation_training_lineage(
        learning_root=tmp_path,
        run_id="run-fixture",
        run_scope=None,
        decision_date="2026-06-01",
        training_as_of="2026-12-31",
        dataset_id="dataset-fixture",
        dataset_hash=dataset_hash,
        samples=samples,
        feature_schema=FEATURE_SCHEMA,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        dataset_quality=_historical_research_quality(),
    )
    path = persist_recommendation_training_lineage(tmp_path / "learning", lineage)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["dataset_hash"] = "sha256:" + "2" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RecommendationTrainingLineageError, match="body hash mismatch"):
        read_recommendation_training_lineage(path)


def test_training_lineage_create_only_publish_is_concurrent_idempotent(tmp_path: Path) -> None:
    samples = _samples(2)
    lineage = build_recommendation_training_lineage(
        learning_root=tmp_path / "learning",
        run_id="run-concurrent",
        run_scope=None,
        decision_date="2026-06-01",
        training_as_of="2026-12-31",
        dataset_id="dataset-concurrent",
        dataset_hash=recommendation_training_dataset_hash(samples),
        samples=samples,
        feature_schema=FEATURE_SCHEMA,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        dataset_quality=_historical_research_quality(),
    )

    def publish() -> Path:
        return persist_recommendation_training_lineage(tmp_path / "learning", lineage)

    with ThreadPoolExecutor(max_workers=2) as executor:
        paths = tuple(executor.map(lambda _: publish(), range(2)))
    assert paths == (paths[0], paths[0])
    assert paths[0].read_bytes().endswith(b"\n")
    read_recommendation_training_lineage(
        paths[0],
        expected_manifest_hash=lineage.manifest_hash,
        expected_dataset_hash=lineage.dataset_hash,
    )


def test_training_lineage_rejects_conflicting_source_group_identity(tmp_path: Path) -> None:
    row = _samples(1)[0]
    conflicting = RecommendationCalibrationSample.from_forward_return(
        row_id=row.row_id,
        symbol=row.symbol,
        decision_date=row.decision_date,
        feature_as_of_date=row.feature_as_of_date,
        feature_available_date=row.feature_available_date,
        label_end_date=row.label_end_date,
        label_available_date=row.label_available_date,
        feature_values=row.feature_values,
        stock_return_bp=row.stock_return_bp + 1,
        benchmark_return_bp=row.benchmark_return_bp,
        fixed_round_trip_cost_bp=50,
        observed_liquidity_cost_bp=20,
        rule_probability_bp=5000,
        rule_after_cost_probability_bp=5000,
    )
    with pytest.raises(RecommendationTrainingLineageError, match="conflicting payload"):
        build_recommendation_training_lineage(
            learning_root=tmp_path,
            run_id="run-fixture",
            run_scope=None,
            decision_date="2026-06-01",
            training_as_of="2026-12-31",
            dataset_id="dataset-fixture",
            dataset_hash=recommendation_training_dataset_hash((row,)),
            samples=(row,),
            feature_schema=FEATURE_SCHEMA,
            fixed_round_trip_cost_bp=50,
            cost_scenario=build_legacy_cost_scenario(50),
            dataset_quality=_historical_research_quality(),
            source_groups={"replay": (row,), "natural": (conflicting,)},
        )


def test_training_lineage_rejects_future_and_cross_cost_lane_rows(tmp_path: Path) -> None:
    row = _samples(1)[0]
    with pytest.raises(RecommendationTrainingLineageError, match="label_available_date"):
        build_recommendation_training_lineage(
            learning_root=tmp_path,
            run_id="run-future",
            run_scope=None,
            decision_date="2026-06-01",
            training_as_of="2025-01-10",
            dataset_id="dataset-fixture",
            dataset_hash=recommendation_training_dataset_hash((row,)),
            samples=(row,),
            feature_schema=FEATURE_SCHEMA,
            fixed_round_trip_cost_bp=50,
            cost_scenario=build_legacy_cost_scenario(50),
            dataset_quality=None,
        )

    with pytest.raises(RecommendationTrainingLineageError, match="declared replay manifest is missing"):
        build_recommendation_training_lineage(
            learning_root=tmp_path,
            run_id="run-missing-manifest",
            run_scope=None,
            decision_date="2026-06-01",
            training_as_of="2026-12-31",
            dataset_id="dataset-fixture",
            dataset_hash=recommendation_training_dataset_hash((row,)),
            samples=(row,),
            feature_schema=FEATURE_SCHEMA,
            fixed_round_trip_cost_bp=50,
            cost_scenario=build_legacy_cost_scenario(50),
            dataset_quality={
                **_historical_research_quality(),
                "replay_dataset_manifest_path": str(tmp_path / "missing-replay.json")
            },
        )

    with pytest.raises(RecommendationTrainingLineageError, match="sample cost lane"):
        build_recommendation_training_lineage(
            learning_root=tmp_path,
            run_id="run-cross-lane",
            run_scope=None,
            decision_date="2026-06-01",
            training_as_of="2026-12-31",
            dataset_id="dataset-fixture",
            dataset_hash=recommendation_training_dataset_hash((row,)),
            samples=(row,),
            feature_schema=FEATURE_SCHEMA,
            fixed_round_trip_cost_bp=60,
            cost_scenario=build_legacy_cost_scenario(60),
            dataset_quality=_historical_research_quality(),
        )


def test_canonical_learning_runner_has_no_app_module_import() -> None:
    path = Path(__file__).resolve().parents[1] / "ml_module" / "recommendation_calibration_learning_runner.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(module == "app_module" or module.startswith("app_module.") for module in imported)
