from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
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
from ml_module.recommendation_probability_transform import PROBABILITY_TRANSFORM_ID
from ml_module.recommendation_inference_provenance import (
    RecommendationProvenanceError,
    _hash_payload,
    build_inference_projection_receipt,
    build_inference_provenance,
    build_training_provenance,
    find_inference_projection_receipts,
    persist_inference_projection_receipt,
    read_inference_projection_receipt,
    validate_provenance_compatibility,
    verify_inference_provenance,
    verify_source_contract_binding,
    _sha256_file,
)
from data_module.ml_historical_snapshot_provider import (
    HistoricalPriceObservation,
    HistoricalRawSnapshot,
)
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


def _inference_snapshot(*, close_price: str = "100") -> HistoricalRawSnapshot:
    return HistoricalRawSnapshot(
        decision_date="2025-05-01",
        feature_as_of_date="2025-04-30",
        prices=(
            HistoricalPriceObservation(
                symbol="2330",
                trading_date="2025-04-30",
                open_price=Decimal(close_price),
                high_price=Decimal(close_price) + Decimal("1"),
                low_price=Decimal(close_price) - Decimal("1"),
                close_price=Decimal(close_price),
                volume=1_000,
                turnover_amount_minor=100_000,
            ),
        ),
        technicals=(),
        market=(),
        industries=(),
        # Deliberately keep the provider fingerprint stable while changing
        # bounded raw content in the content-hash test below.
        source_fingerprint="sha256:" + "1" * 64,
        query_count=4,
    )


def _inference_rows(*, momentum: int = 100) -> tuple[dict[str, object], ...]:
    return (
        {
            "symbol": "2330",
            "decision_date": "2025-05-01",
            "feature_as_of_date": "2025-04-30",
            "feature_available_date": "2025-04-30",
            "values": (
                ("momentum_bp", momentum),
                ("volume_ratio_bp", 1_000),
            ),
        },
    )


def _build_verified_training_fixture(tmp_path: Path) -> tuple[dict[str, object], dict[str, object], str]:
    samples = _samples()
    dataset_hash = recommendation_training_dataset_hash(samples)
    registry_hash = "sha256:" + "2" * 64
    scenario = build_legacy_cost_scenario(50)
    lineage = build_recommendation_training_lineage(
        learning_root=tmp_path,
        run_id="run-provenance-receipt",
        run_scope="test",
        decision_date="2025-05-01",
        training_as_of="2025-04-01",
        dataset_id="dataset-provenance-receipt",
        dataset_hash=dataset_hash,
        samples=samples,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=registry_hash,
        fixed_round_trip_cost_bp=50,
        cost_scenario=scenario,
        dataset_quality={},
        candidate_id="candidate-provenance-1",
    )
    lineage_path = persist_recommendation_training_lineage(tmp_path, lineage)
    training = build_training_provenance(
        lineage_payload=lineage.payload,
        manifest_hash=lineage.manifest_hash,
        manifest_path=str(lineage_path),
        candidate_payload={"candidate_id": "candidate-provenance-1"},
    )
    inference = build_inference_provenance(
        snapshot=_inference_snapshot(),
        feature_rows=_inference_rows(),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=registry_hash,
        cost_scenario_hash=scenario.scenario_hash,
        probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    return training, inference, scenario.scenario_hash


def _write_receipt_variant(path: Path, body: dict[str, object]) -> Path:
    receipt_hash = _hash_payload(body)
    path.mkdir(parents=True, exist_ok=True)
    target = path.parent / f"{receipt_hash.split(':', 1)[1]}.json"
    target.write_text(
        json.dumps({**body, "receipt_hash": receipt_hash}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return target


def test_inference_provenance_uses_bounded_content_and_rejects_future_rows() -> None:
    registry_hash = "sha256:" + "2" * 64
    first = build_inference_provenance(
        snapshot=_inference_snapshot(),
        feature_rows=_inference_rows(),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=registry_hash,
        probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    replay = build_inference_provenance(
        snapshot=_inference_snapshot(),
        feature_rows=_inference_rows(),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=registry_hash,
        probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    assert first["raw_snapshot_content_sha256"] == replay["raw_snapshot_content_sha256"]
    assert first["feature_rows_sha256"] == replay["feature_rows_sha256"]
    changed_raw = build_inference_provenance(
        snapshot=_inference_snapshot(close_price="101"),
        feature_rows=_inference_rows(),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=registry_hash,
        probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    changed_feature = build_inference_provenance(
        snapshot=_inference_snapshot(),
        feature_rows=_inference_rows(momentum=101),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=registry_hash,
        probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    assert first["source_fingerprint"] == changed_raw["source_fingerprint"]
    assert first["raw_snapshot_content_sha256"] != changed_raw["raw_snapshot_content_sha256"]
    assert first["inference_source_hash"] != changed_raw["inference_source_hash"]
    assert first["feature_rows_sha256"] != changed_feature["feature_rows_sha256"]
    future_rows = _inference_rows()
    future_rows[0]["feature_as_of_date"] = "2025-05-01"
    with pytest.raises(RecommendationProvenanceError, match="future-looking"):
        build_inference_provenance(
            snapshot=_inference_snapshot(),
            feature_rows=future_rows,
            feature_schema=FEATURE_SCHEMA,
            feature_registry_hash=registry_hash,
            probability_transform_id=PROBABILITY_TRANSFORM_ID,
        )


def test_inference_source_contract_binding_matches_exact_feature_rows_and_rejects_substitution(
    tmp_path: Path,
) -> None:
    registry_hash = "sha256:" + "2" * 64
    builder_schema_hash = "sha256:" + "4" * 64
    source_db = (tmp_path / "source.db").resolve()
    source_rows = [
        {
            "symbol": "2330",
            "decision_date": "2025-05-01",
            "feature_as_of_date": "2025-04-30",
            "feature_available_date": "2025-04-30",
            "feature_ids": ["momentum_bp", "volume_ratio_bp"],
            "feature_values": [100, 1_000],
            "snapshot_hash": "",
        }
    ]
    feature_body = {
        "component": "prospective_recommendation_features",
        "source_db": str(source_db),
        "decision_date": "2025-05-01",
        "history_start_date": "2014-01-01",
        "feature_registry_hash": registry_hash,
        "feature_schema_hash": builder_schema_hash,
        "symbols": ["2330"],
        "rows": source_rows,
    }
    feature_snapshot = {
        "status": "captured",
        "verified": True,
        "captured_at": "2025-05-01T00:00:00+00:00",
        **feature_body,
        "row_count": 1,
        "rows_sha256": _hash_payload(feature_body),
        "reason": None,
    }
    feature_snapshot["content_sha256"] = _hash_payload(
        {key: value for key, value in feature_snapshot.items() if key != "content_sha256"}
    )
    contract_body = {
        "schema_version": "recommendation-calibration-source-contract.v1",
        "decision_date": "2025-05-01",
        "symbols": ["2330"],
        "lanes": {
            "price_up_calibration": {
                "prospective_status": "ready",
                "prospective_blockers": [],
            }
        },
        "technical": {"prospective_feature_snapshot": feature_snapshot},
    }
    contract = {**contract_body, "contract_sha256": _hash_payload(contract_body)}
    contract_path = tmp_path / "source-contract.json"
    contract_path.write_text(json.dumps(contract, sort_keys=True), encoding="utf-8")
    binding = {
        "schema_version": "recommendation-calibration-capture-source-binding.v1",
        "contract_path": str(contract_path),
        "contract_content_sha256": contract["contract_sha256"],
        "contract_file_sha256": _sha256_file(contract_path),
        "decision_date": "2025-05-01",
        "symbols": ["2330"],
        "price_up_prospective_status": "ready",
        "historical_pit_eligible": False,
        "feature_snapshot_content_sha256": feature_snapshot["content_sha256"],
        "feature_snapshot_rows_sha256": feature_snapshot["rows_sha256"],
    }
    inference = build_inference_provenance(
        snapshot=_inference_snapshot(),
        feature_rows=_inference_rows(),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=registry_hash,
        feature_builder_schema_hash=builder_schema_hash,
        source_database=str(source_db),
        history_start_date="2014-01-01",
        probability_transform_id=PROBABILITY_TRANSFORM_ID,
        source_contract_binding=binding,
    )
    assert inference["source_contract_status"] == "verified"
    verify_inference_provenance(inference)
    substituted_rows = [dict(inference["feature_rows"][0])]
    substituted_rows[0]["feature_values"] = [999, 1_000]
    with pytest.raises(RecommendationProvenanceError, match="feature rows hash|feature values"):
        verify_source_contract_binding(
            binding,
            decision_date="2025-05-01",
            feature_rows=substituted_rows,
            feature_registry_hash=registry_hash,
            feature_schema_hash=inference["feature_schema_hash"],
            feature_builder_schema_hash=builder_schema_hash,
            source_database=str(source_db),
            history_start_date="2014-01-01",
        )


def test_training_and_next_day_inference_have_distinct_hashes_but_compatible_contracts(
    tmp_path: Path,
) -> None:
    training, inference, cost_hash = _build_verified_training_fixture(tmp_path)
    compatibility = validate_provenance_compatibility(
        training,
        inference,
        expected_cost_scenario_hash=cost_hash,
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    assert compatibility["status"] == "verified"
    assert training["training_source_hash"] != inference["inference_source_hash"]
    assert training["training_pit_hash"] != inference["inference_pit_hash"]


def test_projection_receipt_is_immutable_readback_verified_and_exactly_searchable(
    tmp_path: Path,
) -> None:
    training, inference, cost_hash = _build_verified_training_fixture(tmp_path)
    candidate = {"candidate_id": "candidate-provenance-1"}
    compatibility = validate_provenance_compatibility(
        training,
        inference,
        expected_cost_scenario_hash=cost_hash,
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    projections = (
        {
            "stock_code": "2330",
            "status": "active_candidate",
            "model_version": "candidate-provenance-1",
            "ranking_score_bp": 7_200,
            "ranking_percentile_bp": 8_100,
            "cost_scenario_hash": cost_hash,
        },
    )
    receipt = build_inference_projection_receipt(
        decision_date="2025-05-01",
        result_id="recommendation-result-1",
        candidate_identity=candidate,
        training_provenance=training,
        inference_provenance=inference,
        compatibility=compatibility,
        projections=projections,
    )
    receipt_path = persist_inference_projection_receipt(tmp_path, receipt)
    loaded = read_inference_projection_receipt(
        receipt_path,
        expected_decision_date="2025-05-01",
        expected_candidate_id="candidate-provenance-1",
        expected_result_id="recommendation-result-1",
        expected_stock_code="2330",
        expected_cost_scenario_hash=cost_hash,
    )
    assert loaded.receipt_hash == receipt.receipt_hash
    assert loaded.payload["selection_contract"] == {
        "authority": "rule_top_n",
        "score_kind": "rule_total_score",
        "percentile_kind": "rule_percentile",
        "model_ranking_kind": "model_return_bp",
        "top_n_changed_by_model": False,
    }
    found = find_inference_projection_receipts(
        tmp_path,
        decision_date="2025-05-01",
        candidate_id="candidate-provenance-1",
        result_id="recommendation-result-1",
        stock_code="2330",
        cost_scenario_hash=cost_hash,
    )
    assert [item.receipt_hash for item in found] == [receipt.receipt_hash]
    with pytest.raises(RecommendationProvenanceError):
        read_inference_projection_receipt(
            receipt_path,
            expected_candidate_id="other-candidate",
        )
    with pytest.raises(RecommendationProvenanceError):
        read_inference_projection_receipt(
            receipt_path,
            expected_decision_date="2025-05-02",
        )
    with pytest.raises(RecommendationProvenanceError):
        read_inference_projection_receipt(
            receipt_path,
            expected_cost_scenario_hash="sha256:" + "3" * 64,
        )

    tampered_compatibility = deepcopy(dict(receipt.payload))
    tampered_compatibility["provenance_compatibility"] = {
        **dict(compatibility),
        "status": "blocked",
        "reason": "tampered_outer_rehashed",
    }
    tampered_compatibility_path = _write_receipt_variant(
        tmp_path / "tampered-compatibility",
        tampered_compatibility,
    )
    with pytest.raises(RecommendationProvenanceError, match="compatibility"):
        read_inference_projection_receipt(tampered_compatibility_path)

    tampered_source = deepcopy(dict(receipt.payload))
    tampered_inference = dict(tampered_source["inference_provenance"])
    tampered_inference["source_fingerprint"] = "sha256:" + "f" * 64
    tampered_source["inference_provenance"] = tampered_inference
    tampered_source_path = _write_receipt_variant(
        tmp_path / "tampered-source",
        tampered_source,
    )
    with pytest.raises(RecommendationProvenanceError, match="source hash"):
        read_inference_projection_receipt(tampered_source_path)

    conflicting_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    conflicting_payload["result_id"] = "conflicting-result"
    receipt_path.write_text(
        json.dumps(conflicting_payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(RecommendationProvenanceError, match="immutable receipt conflict"):
        persist_inference_projection_receipt(tmp_path, receipt)


def test_projection_receipt_rejects_partial_training_and_accepts_explicit_legacy(
    tmp_path: Path,
) -> None:
    _, inference, cost_hash = _build_verified_training_fixture(tmp_path)
    legacy_training = build_training_provenance(lineage_payload=None)
    legacy_compatibility = validate_provenance_compatibility(
        legacy_training,
        inference,
        expected_cost_scenario_hash=cost_hash,
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    legacy_receipt = build_inference_projection_receipt(
        decision_date="2025-05-01",
        result_id=None,
        candidate_identity={"candidate_id": "legacy-candidate"},
        training_provenance=legacy_training,
        inference_provenance=inference,
        compatibility=legacy_compatibility,
        projections=(
            {
                "stock_code": "2330",
                "status": "rule_only",
                "model_version": "",
                "cost_scenario_hash": cost_hash,
            },
        ),
    )
    legacy_path = persist_inference_projection_receipt(tmp_path, legacy_receipt)
    assert read_inference_projection_receipt(legacy_path).payload[
        "training_provenance"
    ]["status"] == "legacy_unproven"

    partial = deepcopy(dict(legacy_receipt.payload))
    partial_training = dict(partial["training_provenance"])
    partial_training["training_source_hash"] = "sha256:" + "e" * 64
    partial["training_provenance"] = partial_training
    partial_path = _write_receipt_variant(tmp_path / "partial-training", partial)
    with pytest.raises(RecommendationProvenanceError, match="training provenance"):
        read_inference_projection_receipt(partial_path)
