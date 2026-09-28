from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from time import perf_counter
from typing import Iterator

import pytest

from app_module.recommendation.personal_candidate_inventory import (
    PersonalCandidateInventoryCancelled,
    inspect_personal_calibration_candidate,
    inspect_personal_source_time_binding,
    list_personal_calibration_candidates,
    verify_personal_training_source_time_proof,
)
from app_module.recommendation.personal_use_policy import (
    PERSONAL_CALIBRATED_PROBABILITY_MODE,
    PersonalCalibrationCandidateV1,
    RecommendationPersonalUseSelectionV2,
    load_personal_use_policy_snapshot,
    save_personal_use_policy_v2,
)
from ml_module.model_artifact_manifest import ModelArtifactManifest
from ml_module.recommendation_calibration_learning_runner import (
    DailyRecommendationLearningRunner,
)
from ml_module.recommendation_calibration_training import (
    RecommendationCalibrationSample,
    RecommendationCalibrationTrainingConfig,
    candidate_freeze_hash,
    sample_payload,
)
from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.recommendation_historical_replay import (
    RecommendationHistoricalReplayConfig,
    RecommendationHistoricalReplayService,
    _read_source_content_snapshot,
)
from ml_module.recommendation_calibration_training import (
    recommendation_label_registry_hash,
)
from ml_module.recommendation_training_lineage import (
    build_recommendation_training_lineage,
    persist_recommendation_training_lineage,
    recommendation_training_dataset_hash,
)


FEATURE_SCHEMA = (
    ("momentum_bp", "int", "bp"),
    ("volume_ratio_bp", "int", "bp"),
)
CANDIDATE_ID = "rec-cal-inventory-fixture"
TRAINING_DAY = "2025-04-30"


def _sample() -> RecommendationCalibrationSample:
    decision = date(2025, 1, 2)
    return RecommendationCalibrationSample.from_forward_return(
        row_id="historical-replay:2025-01-02:1101",
        symbol="1101",
        decision_date=decision.isoformat(),
        feature_as_of_date=(decision - timedelta(days=1)).isoformat(),
        feature_available_date=(decision - timedelta(days=1)).isoformat(),
        label_end_date=(decision + timedelta(days=20)).isoformat(),
        label_available_date=(decision + timedelta(days=20)).isoformat(),
        feature_values=(1200, 1500),
        stock_return_bp=700,
        benchmark_return_bp=100,
        fixed_round_trip_cost_bp=50,
        observed_liquidity_cost_bp=20,
        rule_probability_bp=5000,
        rule_after_cost_probability_bp=5000,
    )


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _candidate_package(
    tmp_path: Path,
    *,
    with_lineage: bool = True,
    historical_only: bool = False,
) -> tuple[Path, bytes]:
    output_root = tmp_path / "shadow-output"
    learning_root = output_root / "recommendation_learning"
    candidate_root = (
        learning_root / "runs" / TRAINING_DAY / "candidates" / CANDIDATE_ID
    )
    candidate_root.mkdir(parents=True)
    artifact_bytes = b"inventory must hash these bytes, never deserialize them"
    artifact_hash = _sha(artifact_bytes)
    (candidate_root / "model.joblib").write_bytes(artifact_bytes)

    manifest = ModelArtifactManifest.create(
        model_id=CANDIDATE_ID,
        dataset_id="recommendation-dataset-inventory-fixture",
        created_run_id="daily-recommendation-learning:2025-04-30",
        created_at="2025-04-30T14:00:00+00:00",
        model_family="recommendation_absolute_calibration_v1",
        feature_registry_hash="sha256:" + "1" * 64,
        label_registry_hash="sha256:" + "2" * 64,
        feature_schema=FEATURE_SCHEMA,
        training_as_of=TRAINING_DAY,
        hyperparameters_hash="sha256:" + "3" * 64,
        library_versions={"numpy": "2.3.5", "scikit-learn": "1.7.2"},
        serialization_format="joblib",
        artifact_filename="model.joblib",
        artifact_hash=artifact_hash,
    )
    (candidate_root / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    samples = (_sample(),)
    dataset_hash = recommendation_training_dataset_hash(samples)
    lineage = None
    if with_lineage:
        if historical_only:
            decision_day = "2025-03-01"
            training_day = TRAINING_DAY
            quality = {
                "research_only": True,
                "training_semantics": "historical_research_only",
            }
        else:
            decision_day = TRAINING_DAY
            training_day = TRAINING_DAY
            quality = {"training_data_eligible": True}
        lineage = build_recommendation_training_lineage(
            learning_root=learning_root,
            run_id=f"daily-recommendation-learning:{decision_day}",
            run_scope=None,
            decision_date=decision_day,
            training_as_of=training_day,
            dataset_id="recommendation-dataset-inventory-fixture",
            dataset_hash=dataset_hash,
            samples=samples,
            feature_schema=FEATURE_SCHEMA,
            feature_registry_hash="sha256:" + "1" * 64,
            fixed_round_trip_cost_bp=50,
            cost_scenario=build_legacy_cost_scenario(50),
            dataset_quality=quality,
            candidate_id=CANDIDATE_ID,
            candidate_manifest_hash=manifest.manifest_hash,
            candidate_artifact_hash=artifact_hash,
            source_groups={"replay": samples},
        )
        lineage_path = persist_recommendation_training_lineage(learning_root, lineage)
    evaluation = {
        "evaluation_sample_fingerprint": "sha256:" + "4" * 64,
        "cost_contract_hash": "sha256:" + "5" * 64,
        "candidate_prediction_hash": "sha256:" + "6" * 64,
        "rule_prediction_hash": "sha256:" + "7" * 64,
    }
    payload = {
        "schema_version": "recommendation-calibration-candidate.v1",
        "candidate_id": CANDIDATE_ID,
        "dataset_id": manifest.dataset_id,
        "dataset_hash": dataset_hash,
        "model_id": manifest.model_id,
        "model_version": manifest.model_id,
        "model_family": manifest.model_family,
        "feature_schema": [list(item) for item in FEATURE_SCHEMA],
        "training_as_of": manifest.training_as_of,
        "candidate_frozen_at": manifest.created_at,
        "training_row_count": 1,
        "calibration_sample_count": 1,
        "calibration_gap_bp": 12,
        "evaluation": evaluation,
        "candidate_blockers": ["natural_forward_evidence_required_for_promotion"],
        "training_data_eligible": True,
        "training_semantics": (
            "historical_research_only" if historical_only else "decision_time"
        ),
        "decision_time_eligible": not historical_only,
        "training_cutoff": TRAINING_DAY,
        "shadow_only": True,
        "production_eligible": False,
        "production_action_allowed": False,
        "artifact_hash": artifact_hash,
        "manifest_hash": manifest.manifest_hash,
    }
    payload["candidate_freeze_hash"] = candidate_freeze_hash(
        candidate_id=CANDIDATE_ID,
        dataset_hash=dataset_hash,
        manifest_hash=manifest.manifest_hash,
        artifact_hash=artifact_hash,
        evaluation=evaluation,
    )
    if lineage is not None:
        payload.update(
            {
                "training_lineage_manifest_hash": lineage.manifest_hash,
                "training_lineage_manifest_path": str(lineage_path),
            }
        )
    candidate_bytes = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    (candidate_root / "candidate.json").write_bytes(candidate_bytes)
    return candidate_root, candidate_bytes


def _verified_source_database(
    path: Path,
    *,
    symbols: tuple[str, ...] = ("1101", "2330"),
    days: int = 220,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        '''
        CREATE TABLE daily_prices (
            "日期" TEXT NOT NULL, "證券代號" TEXT NOT NULL, "成交股數" INTEGER,
            "成交金額" INTEGER, "開盤價" TEXT, "最高價" TEXT, "最低價" TEXT,
            "收盤價" TEXT
        );
        CREATE TABLE technical_indicators (
            "日期" TEXT NOT NULL, "證券代號" TEXT NOT NULL,
            "RSI" TEXT, "MACD" TEXT, "ADX" TEXT, "available_at" TEXT NOT NULL
        );
        CREATE TABLE market_indices ("日期" TEXT NOT NULL, "收盤指數" TEXT, "收盤價" TEXT);
        CREATE TABLE industry_indices ("日期" TEXT NOT NULL, "指數名稱" TEXT, "收盤指數" TEXT);
        CREATE TABLE corporate_action_adjustments (
            symbol TEXT NOT NULL, event_date TEXT NOT NULL, available_at TEXT NOT NULL,
            effective_from TEXT NOT NULL, adjustment_factor TEXT NOT NULL
        );
        CREATE TABLE recommendation_source_contract (
            component TEXT PRIMARY KEY, source_id TEXT NOT NULL, source_table TEXT NOT NULL,
            status TEXT NOT NULL, coverage_start TEXT NOT NULL, coverage_end TEXT NOT NULL,
            available_at TEXT NOT NULL, evidence_hash TEXT NOT NULL, source_columns_json TEXT NOT NULL,
            publication_time_verified INTEGER NOT NULL,
            corporate_action_adjustment_verified INTEGER NOT NULL
        );
        '''
    )
    start = date(2025, 1, 1)
    for offset in range(days):
        current = (start + timedelta(days=offset)).strftime("%Y%m%d")
        close_base = 100 + offset
        connection.execute(
            'INSERT INTO market_indices VALUES (?, ?, ?)',
            (current, str(10_000 + offset), str(10_000 + offset)),
        )
        for symbol_index, symbol in enumerate(symbols):
            close = close_base + symbol_index * 20
            connection.execute(
                'INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (current, symbol, 1000 + offset, close * 100, str(close), str(close + 1), str(close - 1), str(close)),
            )
            connection.execute(
                'INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?, ?)',
                (current, symbol, "55", "1.5", "20", current),
            )
    contract_start = start
    contract_end = start + timedelta(days=days - 1)
    for symbol in symbols:
        connection.execute(
            'INSERT INTO corporate_action_adjustments VALUES (?, ?, ?, ?, ?)',
            (symbol, contract_start.isoformat(), contract_start.isoformat(), contract_start.isoformat(), "1"),
        )
    connection.commit()
    technical_content = _read_source_content_snapshot(
        path,
        component="technical",
        source_table="technical_indicators",
        symbols=symbols,
        history_start=contract_start,
        replay_end=contract_end,
    )
    corporate_content = _read_source_content_snapshot(
        path,
        component="corporate_actions",
        source_table="corporate_action_adjustments",
        symbols=symbols,
        history_start=contract_start,
        replay_end=contract_end,
    )
    connection.executemany(
        'INSERT INTO recommendation_source_contract VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            (
                "technical",
                "twse.mi_index.daily_price+tpex.daily_close_quotes",
                "technical_indicators",
                "accepted",
                contract_start.isoformat(),
                contract_end.isoformat(),
                contract_start.isoformat(),
                technical_content["digest"],
                json.dumps(["日期", "證券代號", "RSI", "MACD", "ADX", "available_at"]),
                1,
                0,
            ),
            (
                "corporate_actions",
                "official_market_event_publication",
                "corporate_action_adjustments",
                "accepted",
                contract_start.isoformat(),
                contract_end.isoformat(),
                contract_start.isoformat(),
                corporate_content["digest"],
                json.dumps(["symbol", "event_date", "available_at", "effective_from", "adjustment_factor"]),
                0,
                1,
            ),
        ),
    )
    connection.commit()
    connection.close()


def _refresh_technical_source_contract(
    database: Path,
    *,
    symbols: tuple[str, ...],
    coverage_end: date,
) -> None:
    """依隔離來源資料重算技術來源合約的整庫摘要。"""

    content = _read_source_content_snapshot(
        database,
        component="technical",
        source_table="technical_indicators",
        symbols=symbols,
        history_start=date(2025, 1, 1),
        replay_end=coverage_end,
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE recommendation_source_contract "
            "SET coverage_end = ?, evidence_hash = ? WHERE component = ?",
            (coverage_end.isoformat(), content["digest"], "technical"),
        )


def _source_bound_candidate_package(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...] = ("1101", "2330"),
    decision_dates: int = 1,
    days: int = 220,
    replay_windows: tuple[tuple[str, str], ...] = (("2025-04-01", "2025-06-30"),),
    fit_training_as_of: str | None = None,
    lineage_research_only: bool | None = None,
) -> tuple[Path, bytes, Path, Path]:
    data_root = tmp_path / "configured-data"
    database = data_root / "sqlite" / "twstock.db"
    _verified_source_database(database, symbols=symbols, days=days)
    output_root = tmp_path / "shadow-output"
    learning_root = output_root / "recommendation_learning"
    start = date(2025, 1, 1)
    replay_service = RecommendationHistoricalReplayService(
        MLHistoricalSnapshotProvider(database)
    )
    replays = tuple(
        replay_service.build(
            RecommendationHistoricalReplayConfig(
                history_start_date=start.isoformat(),
                replay_start_date=replay_start,
                replay_end_date=replay_end,
                symbols=symbols,
                fixed_round_trip_cost_bp=50,
                max_decision_dates=decision_dates,
            )
        )
        for replay_start, replay_end in replay_windows
    )
    assert all(replay.training_data_eligible is True for replay in replays)
    assert all(
        replay.source_disclosures["technical"]["source_contract"]["verified"] is True
        for replay in replays
    )
    assert all(
        replay.source_disclosures["corporate_actions"]["source_contract"]["verified"] is True
        for replay in replays
    )
    samples = tuple(
        sorted(
            (sample for replay in replays for sample in replay.samples),
            key=lambda sample: (sample.decision_date, sample.symbol, sample.row_id),
        )
    )
    if not samples:
        raise AssertionError("可信來源 fixture 必須產生 replay samples")
    training_day = max(
        TRAINING_DAY,
        max(sample.label_available_date for sample in samples),
    )
    fit_cutoff = fit_training_as_of or training_day
    candidate_root = (
        learning_root / "runs" / training_day / "candidates" / CANDIDATE_ID
    )
    candidate_root.mkdir(parents=True)
    replay_paths = tuple(replay.persist(output_root) for replay in replays)
    replay_path = replay_paths[0]
    dataset_hash = recommendation_training_dataset_hash(samples)
    merged_dataset_id = "recommendation-dataset-" + dataset_hash.split(":", 1)[1][:16]
    artifact_bytes = b"bounded source-proof fixture artifact; metadata test never deserializes"
    artifact_hash = _sha(artifact_bytes)
    (candidate_root / "model.joblib").write_bytes(artifact_bytes)
    feature_schema = CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema
    manifest = ModelArtifactManifest.create(
        model_id=CANDIDATE_ID,
        dataset_id=merged_dataset_id,
        created_run_id=f"daily-recommendation-learning:{training_day}",
        created_at=f"{training_day}T14:00:00+00:00",
        model_family="recommendation_absolute_calibration_v1",
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        label_registry_hash=recommendation_label_registry_hash(),
        feature_schema=feature_schema,
        training_as_of=fit_cutoff,
        hyperparameters_hash="sha256:" + "3" * 64,
        library_versions={"numpy": "2.3.5", "scikit-learn": "1.7.2"},
        serialization_format="joblib",
        artifact_filename="model.joblib",
        artifact_hash=artifact_hash,
    )
    (candidate_root / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    lineage_quality: dict[str, object] = {
        "training_data_eligible": True,
        "replay_dataset_manifest_path": str(replay_paths[0]),
        **(
            {"replay_manifest_path": str(replay_paths[1])}
            if len(replay_paths) > 1
            else {}
        ),
    }
    if lineage_research_only is not None:
        lineage_quality["research_only"] = lineage_research_only
    lineage = build_recommendation_training_lineage(
        learning_root=learning_root,
        run_id=f"daily-recommendation-learning:{training_day}",
        run_scope=None,
        decision_date=training_day,
        training_as_of=training_day,
        dataset_id=manifest.dataset_id,
        dataset_hash=dataset_hash,
        samples=samples,
        feature_schema=feature_schema,
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        dataset_quality=lineage_quality,
        candidate_id=CANDIDATE_ID,
        candidate_manifest_hash=manifest.manifest_hash,
        candidate_artifact_hash=artifact_hash,
        source_groups={"replay": samples},
    )
    lineage_path = persist_recommendation_training_lineage(learning_root, lineage)
    evaluation = {
        "evaluation_sample_fingerprint": "sha256:" + "4" * 64,
        "cost_contract_hash": "sha256:" + "5" * 64,
        "candidate_prediction_hash": "sha256:" + "6" * 64,
        "rule_prediction_hash": "sha256:" + "7" * 64,
    }
    payload = {
        "schema_version": "recommendation-calibration-candidate.v1",
        "candidate_id": CANDIDATE_ID,
        "dataset_id": manifest.dataset_id,
        "dataset_hash": dataset_hash,
        "model_id": manifest.model_id,
        "model_version": manifest.model_id,
        "model_family": manifest.model_family,
        "feature_schema": [list(item) for item in feature_schema],
        "feature_registry_hash": CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        "training_as_of": manifest.training_as_of,
        "candidate_frozen_at": manifest.created_at,
        "training_row_count": len(samples),
        "calibration_sample_count": len(samples),
        "calibration_gap_bp": 12,
        "evaluation": evaluation,
        "candidate_blockers": ["natural_forward_evidence_required_for_promotion"],
        "training_data_eligible": True,
        "training_semantics": "decision_time",
        "decision_time_eligible": True,
        "training_cutoff": training_day,
        "shadow_only": True,
        "production_eligible": False,
        "production_action_allowed": False,
        "artifact_hash": artifact_hash,
        "manifest_hash": manifest.manifest_hash,
        "training_lineage_manifest_hash": lineage.manifest_hash,
        "training_lineage_manifest_path": str(lineage_path),
    }
    payload["candidate_freeze_hash"] = candidate_freeze_hash(
        candidate_id=CANDIDATE_ID,
        dataset_hash=dataset_hash,
        manifest_hash=manifest.manifest_hash,
        artifact_hash=artifact_hash,
        evaluation=evaluation,
    )
    if lineage_research_only is not None:
        payload["research_only"] = lineage_research_only
    candidate_bytes = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    (candidate_root / "candidate.json").write_bytes(candidate_bytes)
    return candidate_root, candidate_bytes, data_root, replay_path


def test_daily_runner_fit_cutoff_is_bound_to_lineage_cutoff(
    tmp_path: Path,
) -> None:
    samples: list[RecommendationCalibrationSample] = []
    start = date(2025, 1, 2)
    for day_index in range(70):
        decision = start + timedelta(days=day_index)
        for symbol_index, symbol in enumerate(("1101", "2330")):
            momentum = ((day_index % 6) - 2) * 1000 + symbol_index * 170
            stock_return = momentum + symbol_index * 120
            samples.append(
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
    frozen_samples = tuple(samples)
    training_cutoff = "2025-04-30"
    dataset_hash = recommendation_training_dataset_hash(frozen_samples)
    replay_path = tmp_path / "replay" / "runner-output.json"
    replay_path.parent.mkdir(parents=True)
    replay_path.write_text(
        json.dumps(
            {
                "schema_version": "recommendation-historical-replay-dataset.v1",
                "dataset_id": "recommendation-dataset-" + dataset_hash.split(":", 1)[1][:16],
                "dataset_hash": dataset_hash,
                "sample_count": len(frozen_samples),
                "decision_dates": sorted({sample.decision_date for sample in frozen_samples}),
                "samples": [sample_payload(sample) for sample in frozen_samples],
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
    output_root = tmp_path / "runner-output"
    runner = DailyRecommendationLearningRunner(
        output_root=output_root,
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
        decision_date="2025-05-02",
        samples=frozen_samples,
        natural_evidence=None,
        training_as_of=training_cutoff,
        dataset_quality={
            "training_data_eligible": True,
            "replay_dataset_manifest_path": str(replay_path),
        },
        lineage_sources={"replay": frozen_samples},
    )

    assert result.status == "completed"
    assert result.training_lineage_status == "verified"
    candidate_root = Path(result.candidate_root or "")
    candidate_payload = json.loads((candidate_root / "candidate.json").read_text(encoding="utf-8"))
    manifest = json.loads((candidate_root / "manifest.json").read_text(encoding="utf-8"))
    lineage = json.loads(
        Path(candidate_payload["training_lineage_manifest_path"]).read_text(encoding="utf-8")
    )
    assert candidate_payload["training_as_of"] == manifest["training_as_of"]
    assert candidate_payload["training_as_of"] < candidate_payload["training_cutoff"]
    assert candidate_payload["training_cutoff"] == lineage["training_as_of"] == training_cutoff
    assert lineage["pit"]["decision_dates_not_after_training_as_of"] is True
    assert lineage["pit"]["label_available_dates_not_after_training_as_of"] is True
    assert lineage["pit"]["feature_as_of_before_decision"] is True

    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=output_root,
        data_root=tmp_path / "formal-data",
    )
    assert inspected.status == "historical_research_only"
    assert inspected.reason_code == "independent_source_time_authority_missing"
    assert inspected.candidate is None


def test_candidate_training_cutoff_must_match_lineage_cutoff(tmp_path: Path) -> None:
    candidate_root, _, data_root, _ = _source_bound_candidate_package(tmp_path)
    candidate_path = candidate_root / "candidate.json"
    candidate_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate_payload["training_cutoff"] = "2025-05-01"
    candidate_path.write_text(
        json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )

    assert inspected.status == "unavailable"
    assert inspected.reason_code == "training_lineage_invalid"
    assert inspected.candidate is None


def test_candidate_fit_cutoff_cannot_exceed_lineage_cutoff(tmp_path: Path) -> None:
    candidate_root, _, data_root, _ = _source_bound_candidate_package(
        tmp_path,
        fit_training_as_of="2025-05-01",
    )

    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )

    assert inspected.status == "unavailable"
    assert inspected.reason_code == "training_lineage_invalid"
    assert inspected.candidate is None


def test_list_is_lightweight_and_inspection_blocks_without_external_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_root, candidate_bytes, data_root, _ = _source_bound_candidate_package(
        tmp_path
    )
    output_root = tmp_path / "shadow-output"

    import app_module.recommendation.personal_candidate_inventory as inventory

    def reject_hash(*args: object, **kwargs: object) -> str:
        raise AssertionError("清單階段不可讀取或雜湊 artifact")

    monkeypatch.setattr(inventory, "_hash_bounded_file", reject_hash)
    listing = list_personal_calibration_candidates(explicit_output_root=output_root)
    assert listing.status == "complete"
    assert len(listing.entries) == 1
    listed = listing.entries[0]
    assert listed.status == "metadata_unverified"
    assert listed.candidate is None
    assert listed.candidate_id == CANDIDATE_ID
    assert listed.training_semantics == "decision_time"

    monkeypatch.undo()
    import joblib

    def reject_deserialize(*args: object, **kwargs: object) -> object:
        raise AssertionError("metadata inventory 不可反序列化模型")

    monkeypatch.setattr(joblib, "load", reject_deserialize)

    import app_module.recommendation.personal_candidate_inventory as inventory_module

    def reject_untrusted_source_replay(*args: object, **kwargs: object) -> object:
        raise AssertionError("未取得獨立來源權威時 inventory/consumer 不可重播 SQLite")

    monkeypatch.setattr(
        inventory_module,
        "verify_personal_training_source_time_proof",
        reject_untrusted_source_replay,
    )
    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=output_root,
        data_root=data_root,
    )
    assert inspected.status == "historical_research_only", inspected.next_step
    assert inspected.reason_code == "independent_source_time_authority_missing"
    assert inspected.candidate is None

    candidate_payload = json.loads(candidate_bytes)
    lineage_path = Path(candidate_payload["training_lineage_manifest_path"])
    lineage_payload = json.loads(lineage_path.read_text(encoding="utf-8"))
    # 有界 verifier 仍可證明 replay/SQLite 內容一致，但單獨不足以產生個人使用 pin 或官方 PIT 宣稱。
    assert verify_personal_training_source_time_proof(
        lineage_payload=lineage_payload,
        learning_root=candidate_root.parents[3],
        data_root=data_root,
    ) is None

    from app_module.recommendation_calibration_consumer import (
        RecommendationCalibrationConsumer,
    )
    from app_module.recommendation.personal_use_policy import (
        PERSONAL_CALIBRATED_PROBABILITY_MODE,
        PersonalCalibrationCandidateV1,
        RecommendationPersonalUseSelectionV1,
        save_personal_use_policy,
    )

    # 即使手工建立其餘欄位有效的 pin，也不可略過獨立來源權威檢查或進入模型載入器。
    manifest = ModelArtifactManifest.from_dict(
        json.loads((candidate_root / "manifest.json").read_text(encoding="utf-8"))
    )
    candidate_ref = PersonalCalibrationCandidateV1(
        candidate_id=CANDIDATE_ID,
        candidate_root=str(candidate_root.resolve()),
        candidate_json_sha256=_sha(candidate_bytes),
        candidate_manifest_hash=manifest.manifest_hash,
        candidate_artifact_hash=manifest.artifact_hash,
        candidate_freeze_hash=str(candidate_payload["candidate_freeze_hash"]),
        dataset_hash=str(candidate_payload["dataset_hash"]),
    )
    policy = save_personal_use_policy(
        tmp_path / "isolated-personal-policy.json",
        RecommendationPersonalUseSelectionV1(
            scope_id="source-authority-missing-test",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            candidate=candidate_ref,
        ),
        expected_revision=0,
    )
    consumer = RecommendationCalibrationConsumer(
        pointer_path=Path(policy.storage_path or ""),
        feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        data_root=data_root,
        personal_use_policy=policy,
    )
    loader_calls = 0

    def reject_model_load(*args: object, **kwargs: object) -> object:
        nonlocal loader_calls
        loader_calls += 1
        raise AssertionError("缺少獨立來源權威時不可載入模型")

    monkeypatch.setattr(consumer._loader, "load", reject_model_load)
    assert consumer.reload(decision_date="2025-04-30") == "rule_only"
    assert consumer._blocker == "independent_source_time_authority_missing"
    assert loader_calls == 0


def test_v2_source_binding_preview_save_reinspect_and_consumer_gate(
    tmp_path: Path,
) -> None:
    candidate_root, candidate_bytes, data_root, _ = _source_bound_candidate_package(
        tmp_path,
        lineage_research_only=False,
    )
    source_database = data_root / "sqlite" / "twstock.db"
    output_root = tmp_path / "shadow-output"
    policy_path = tmp_path / "personal-policy-v2.json"

    proposal = inspect_personal_source_time_binding(
        candidate_root=candidate_root,
        source_database_path=source_database.resolve(),
        explicit_output_root=output_root,
        data_root=data_root,
    )
    assert proposal.schema_version == "personal-source-time-binding-proposal.v1"
    assert proposal.basis == "user_declared_source_time"
    assert proposal.source_database_path == str(source_database.resolve())
    assert proposal.file_identity.inode > 0
    assert proposal.source_slice_sha256.startswith("sha256:")
    assert proposal.candidate.candidate_id == CANDIDATE_ID
    assert len(proposal.replay_scope.dataset_ids) == 1
    assert proposal.replay_scope.dataset_ids[0].startswith("recommendation-dataset-")
    assert proposal.replay_scope.sample_count == 2
    assert proposal.research_only is True
    assert proposal.official_historical_pit_verified is False

    policy = save_personal_use_policy_v2(
        policy_path,
        RecommendationPersonalUseSelectionV2(
            scope_id="explicit-source-trust-test",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            source_time_binding=proposal,
        ),
        expected_revision=0,
    )
    reloaded_policy = load_personal_use_policy_snapshot(policy_path)
    assert type(reloaded_policy).__name__ == "RecommendationPersonalUsePolicyV2"
    assert reloaded_policy.to_dict() == policy.to_dict()
    assert reloaded_policy.source_time_trust is not None
    assert reloaded_policy.source_time_trust.research_only is True
    assert reloaded_policy.source_time_trust.official_historical_pit_verified is False

    from app_module.recommendation_calibration_consumer import (
        _load_candidate_training_provenance,
    )
    from ml_module.recommendation_inference_provenance import (
        RecommendationProvenanceError,
        _verify_receipt_training_provenance,
    )

    candidate_payload = json.loads(candidate_bytes)
    training_provenance, provenance_error = _load_candidate_training_provenance(
        candidate_root=candidate_root,
        candidate_payload=candidate_payload,
        decision_date="2025-06-30",
        require_personal_source_time=True,
        data_root=data_root,
        personal_use_policy=reloaded_policy,
    )
    assert provenance_error is None
    assert training_provenance["training_semantics"] == "decision_time"
    assert training_provenance["decision_time_eligible"] is True
    assert training_provenance["research_only"] is False
    assert training_provenance["source_time_basis"] == "user_declared_source_time"
    assert training_provenance["source_time_research_only"] is True
    assert training_provenance["official_historical_pit_verified"] is False

    candidate_identity = dict(candidate_payload)
    candidate_identity["training_provenance"] = dict(training_provenance)
    _verify_receipt_training_provenance(
        training_provenance,
        candidate_identity=candidate_identity,
        decision_date="2025-06-30",
    )
    tampered_training_provenance = dict(training_provenance)
    tampered_training_provenance["research_only"] = True
    tampered_identity = dict(candidate_payload)
    tampered_identity["training_provenance"] = dict(tampered_training_provenance)
    with pytest.raises(
        RecommendationProvenanceError,
        match="training lineage readback field mismatch: research_only",
    ):
        _verify_receipt_training_provenance(
            tampered_training_provenance,
            candidate_identity=tampered_identity,
            decision_date="2025-06-30",
        )

    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        source_database_path=source_database.resolve(),
        personal_use_policy=reloaded_policy,
        explicit_output_root=output_root,
        data_root=data_root,
    )
    assert inspected.status == "metadata_pinned_pending_runtime_validation"
    assert inspected.reason_code == "user_declared_source_time_research_only"
    assert inspected.candidate == proposal.candidate
    assert inspected.source_time_basis == "user_declared_source_time"
    assert inspected.research_only is True
    assert inspected.official_historical_pit_verified is False

    # 大小與 mtime 是診斷值，不是綁定 invariant；同一檔案、相同來源切片仍可重驗。
    with sqlite3.connect(source_database) as connection:
        connection.execute("CREATE TABLE unrelated_user_table (value TEXT)")
        connection.execute("INSERT INTO unrelated_user_table VALUES ('kept outside replay scope')")
    size_changed = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        source_database_path=source_database.resolve(),
        personal_use_policy=reloaded_policy,
        explicit_output_root=output_root,
        data_root=data_root,
    )
    assert size_changed.status == "metadata_pinned_pending_runtime_validation", size_changed.reason_code

    from app_module.recommendation_calibration_consumer import (
        RecommendationCalibrationConsumer,
    )

    consumer = RecommendationCalibrationConsumer(
        pointer_path=policy_path,
        feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        data_root=data_root,
        personal_use_policy=reloaded_policy,
    )
    original_load = consumer._loader.load
    loader_calls = 0

    def count_loader_calls(*args: object, **kwargs: object) -> object:
        nonlocal loader_calls
        loader_calls += 1
        return original_load(*args, **kwargs)

    consumer._loader.load = count_loader_calls  # type: ignore[method-assign]
    assert consumer.reload(decision_date="2025-06-30") == "rule_only"
    assert loader_calls == 1
    assert consumer._blocker not in {
        "independent_source_time_authority_missing",
        "personal_source_time_binding_missing_or_invalid",
        "personal_source_time_binding_mismatch",
        "candidate_training_source_time_unverified_fail_closed",
    }


def test_v2_source_binding_rejects_a_different_database_identity(
    tmp_path: Path,
) -> None:
    import shutil

    candidate_root, _, data_root, _ = _source_bound_candidate_package(tmp_path)
    source_database = data_root / "sqlite" / "twstock.db"
    proposal = inspect_personal_source_time_binding(
        candidate_root=candidate_root,
        source_database_path=source_database.resolve(),
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )
    policy = save_personal_use_policy_v2(
        tmp_path / "policy.json",
        RecommendationPersonalUseSelectionV2(
            scope_id="different-database-test",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            source_time_binding=proposal,
        ),
        expected_revision=0,
    )
    identical_copy = tmp_path / "copy" / "twstock-copy.db"
    identical_copy.parent.mkdir()
    shutil.copyfile(source_database, identical_copy)
    result = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        source_database_path=identical_copy.resolve(),
        personal_use_policy=policy,
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )
    assert result.status == "historical_research_only"
    assert result.reason_code in {
        "source_time_binding_mismatch",
        "training_source_time_replay_mismatch",
    }
    assert result.candidate is None


def test_v2_source_binding_rejects_stale_policy_bytes_before_model_load(
    tmp_path: Path,
) -> None:
    candidate_root, _, data_root, _ = _source_bound_candidate_package(tmp_path)
    source_database = (data_root / "sqlite" / "twstock.db").resolve()
    policy_path = tmp_path / "policy.json"
    proposal = inspect_personal_source_time_binding(
        candidate_root=candidate_root,
        source_database_path=source_database,
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )
    policy = save_personal_use_policy_v2(
        policy_path,
        RecommendationPersonalUseSelectionV2(
            scope_id="stale-policy-bytes-test",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            source_time_binding=proposal,
        ),
        expected_revision=0,
    )
    from app_module.recommendation_calibration_consumer import (
        RecommendationCalibrationConsumer,
    )

    consumer = RecommendationCalibrationConsumer(
        pointer_path=policy_path,
        feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        data_root=data_root,
        personal_use_policy=policy,
    )
    policy_path.write_bytes(policy_path.read_bytes() + b" ")

    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        source_database_path=source_database,
        personal_use_policy=policy,
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )
    assert inspected.status == "historical_research_only"
    assert inspected.reason_code == "source_time_binding_mismatch"
    assert inspected.candidate is None

    loader_calls = 0

    def reject_stale_policy_model_load(*args: object, **kwargs: object) -> object:
        nonlocal loader_calls
        loader_calls += 1
        raise AssertionError("磁碟政策 bytes 改變後不可載入模型")

    consumer._loader.load = reject_stale_policy_model_load  # type: ignore[method-assign]
    assert consumer.reload(decision_date="2025-06-30") == "rule_only"
    assert consumer._blocker == "personal_use_policy_changed_since_load"
    assert loader_calls == 0


def test_v2_source_binding_rejects_changed_source_slice_and_rehashed_candidate(
    tmp_path: Path,
) -> None:
    candidate_root, _, data_root, _ = _source_bound_candidate_package(tmp_path)
    source_database = data_root / "sqlite" / "twstock.db"
    proposal = inspect_personal_source_time_binding(
        candidate_root=candidate_root,
        source_database_path=source_database.resolve(),
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )
    policy = save_personal_use_policy_v2(
        tmp_path / "policy.json",
        RecommendationPersonalUseSelectionV2(
            scope_id="source-slice-mutation-test",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            source_time_binding=proposal,
        ),
        expected_revision=0,
    )

    with sqlite3.connect(source_database) as connection:
        connection.execute(
            'UPDATE technical_indicators SET available_at = ? WHERE "日期" = ? AND "證券代號" = ?',
            ("20251231", "20250331", "1101"),
        )
    changed_source = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        source_database_path=source_database.resolve(),
        personal_use_policy=policy,
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )
    assert changed_source.status == "historical_research_only"
    assert changed_source.candidate is None
    assert changed_source.reason_code != "user_declared_source_time_research_only"

    from app_module.recommendation_calibration_consumer import (
        RecommendationCalibrationConsumer,
    )

    consumer = RecommendationCalibrationConsumer(
        pointer_path=policy.storage_path,
        feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        data_root=data_root,
        personal_use_policy=policy,
    )
    loader_calls = 0

    def reject_stale_source_model_load(*args: object, **kwargs: object) -> object:
        nonlocal loader_calls
        loader_calls += 1
        raise AssertionError("來源切片改變後不可載入模型")

    consumer._loader.load = reject_stale_source_model_load  # type: ignore[method-assign]
    assert consumer.reload(decision_date="2025-06-30") == "rule_only"
    assert consumer._blocker == "candidate_training_source_time_unverified_fail_closed"
    assert loader_calls == 0

    # 候選本身重算 JSON bytes hash 仍不能替代政策中使用者確認的 pins。
    candidate_payload = json.loads((candidate_root / "candidate.json").read_text(encoding="utf-8"))
    candidate_payload["candidate_blockers"] = ["self_rehashed_candidate_claim"]
    (candidate_root / "candidate.json").write_text(
        json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    forged_candidate = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        source_database_path=source_database.resolve(),
        personal_use_policy=policy,
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )
    assert forged_candidate.status == "historical_research_only"
    assert forged_candidate.reason_code in {
        "training_source_time_contract_unverified",
        "training_source_time_replay_mismatch",
        "source_time_binding_mismatch",
    }
    assert forged_candidate.candidate is None


def test_user_declared_source_slice_allows_same_inode_daily_append_after_cutoff(
    tmp_path: Path,
) -> None:
    candidate_root, candidate_bytes, data_root, replay_path = (
        _source_bound_candidate_package(tmp_path)
    )
    database = data_root / "sqlite" / "twstock.db"
    manifest_before = json.loads(replay_path.read_text(encoding="utf-8"))
    stat_before = database.stat()
    database_hash_before = _sha(database.read_bytes())
    daily_row_count_before = len(manifest_before["samples"])

    # 新增日期晚於 replay/訓練決策截止日；同一檔案的技術整庫摘要會更新，
    # 但候選使用的逐筆歷史樣本及訓練窗來源時間不得改變。
    appended_day = "20250809"
    with sqlite3.connect(database) as connection:
        for index, symbol in enumerate(("1101", "2330")):
            close = 330 + index
            connection.execute(
                'INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    appended_day,
                    symbol,
                    2000,
                    close * 100,
                    str(close),
                    str(close + 1),
                    str(close - 1),
                    str(close),
                ),
            )
            connection.execute(
                'INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?, ?)',
                (appended_day, symbol, "56", "1.6", "21", appended_day),
            )
        connection.execute(
            "INSERT INTO market_indices VALUES (?, ?, ?)",
            (appended_day, "11000", "11000"),
        )
    _refresh_technical_source_contract(
        database,
        symbols=("1101", "2330"),
        coverage_end=date(2025, 8, 9),
    )
    stat_after = database.stat()
    assert (stat_before.st_dev, stat_before.st_ino) == (
        stat_after.st_dev,
        stat_after.st_ino,
    )
    assert _sha(database.read_bytes()) != database_hash_before

    replay_after = RecommendationHistoricalReplayService(
        MLHistoricalSnapshotProvider(database)
    ).build(
        RecommendationHistoricalReplayConfig(
            history_start_date="2025-01-01",
            replay_start_date="2025-04-01",
            replay_end_date="2025-06-30",
            symbols=("1101", "2330"),
            fixed_round_trip_cost_bp=50,
            max_decision_dates=1,
        )
    ).to_dict()
    assert len(replay_after["samples"]) == daily_row_count_before
    assert json.loads(json.dumps(replay_after["samples"])) == manifest_before["samples"]
    assert replay_after["decision_dates"] == manifest_before["decision_dates"]

    # 這四項明確是技術來源合約的整庫彙總；全部都變化，但僅在兩個
    # user-declared source-slice 比較投影中排除。
    aggregate_fields = (
        "content_digest",
        "content_row_count",
        "coverage_end",
        "evidence_hash",
    )
    aggregate_paths = (
        (manifest_before["coverage"]["source_contract"]["technical"],
         replay_after["coverage"]["source_contract"]["technical"]),
        (manifest_before["source_disclosures"]["source_contract"]["technical"],
         replay_after["source_disclosures"]["source_contract"]["technical"]),
        (manifest_before["source_disclosures"]["technical"]["source_contract"],
         replay_after["source_disclosures"]["technical"]["source_contract"]),
    )
    for before_contract, after_contract in aggregate_paths:
        assert all(before_contract[key] != after_contract[key] for key in aggregate_fields)

    from app_module.recommendation.personal_candidate_inventory import (
        _personal_replay_source_slice_projection,
    )

    assert json.dumps(
        _personal_replay_source_slice_projection(manifest_before),
        ensure_ascii=False,
        sort_keys=True,
    ) == json.dumps(
        _personal_replay_source_slice_projection(replay_after),
        ensure_ascii=False,
        sort_keys=True,
    )
    candidate_payload = json.loads(candidate_bytes)
    lineage_payload = json.loads(
        Path(candidate_payload["training_lineage_manifest_path"]).read_text(
            encoding="utf-8"
        )
    )
    assert verify_personal_training_source_time_proof(
        lineage_payload=lineage_payload,
        learning_root=candidate_root.parents[3],
        data_root=data_root,
    ) is None


def test_user_declared_source_slice_rejects_missing_training_window_available_at(
    tmp_path: Path,
) -> None:
    candidate_root, candidate_bytes, data_root, _ = _source_bound_candidate_package(
        tmp_path
    )
    database = data_root / "sqlite" / "twstock.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            'UPDATE technical_indicators SET available_at = ? '
            'WHERE "日期" <= ? AND "證券代號" IN (?, ?)',
            ("", "20250630", "1101", "2330"),
        )
    _refresh_technical_source_contract(
        database,
        symbols=("1101", "2330"),
        coverage_end=date(2025, 8, 8),
    )
    candidate_payload = json.loads(candidate_bytes)
    lineage_payload = json.loads(
        Path(candidate_payload["training_lineage_manifest_path"]).read_text(
            encoding="utf-8"
        )
    )

    proof_error = verify_personal_training_source_time_proof(
        lineage_payload=lineage_payload,
        learning_root=candidate_root.parents[3],
        data_root=data_root,
    )

    assert proof_error in {
        "training_source_time_contract_unverified",
        "training_source_time_replay_mismatch",
    }


def test_user_declared_source_slice_rejects_training_window_price_mutation(
    tmp_path: Path,
) -> None:
    candidate_root, candidate_bytes, data_root, replay_path = (
        _source_bound_candidate_package(tmp_path)
    )
    manifest = json.loads(replay_path.read_text(encoding="utf-8"))
    sample = manifest["samples"][0]
    database = data_root / "sqlite" / "twstock.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            'UPDATE daily_prices SET "收盤價" = ? WHERE "日期" = ? AND "證券代號" = ?',
            ("9999", sample["label_end_date"].replace("-", ""), sample["symbol"]),
        )
    candidate_payload = json.loads(candidate_bytes)
    lineage_payload = json.loads(
        Path(candidate_payload["training_lineage_manifest_path"]).read_text(
            encoding="utf-8"
        )
    )

    proof_error = verify_personal_training_source_time_proof(
        lineage_payload=lineage_payload,
        learning_root=candidate_root.parents[3],
        data_root=data_root,
    )

    assert proof_error == "training_source_time_replay_mismatch"


def test_user_declared_source_slice_rejects_changed_source_contract_identity(
    tmp_path: Path,
) -> None:
    candidate_root, candidate_bytes, data_root, _ = _source_bound_candidate_package(
        tmp_path
    )
    database = data_root / "sqlite" / "twstock.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE recommendation_source_contract SET source_id = ? WHERE component = ?",
            ("self_asserted_test_source", "technical"),
        )
    candidate_payload = json.loads(candidate_bytes)
    lineage_payload = json.loads(
        Path(candidate_payload["training_lineage_manifest_path"]).read_text(
            encoding="utf-8"
        )
    )

    proof_error = verify_personal_training_source_time_proof(
        lineage_payload=lineage_payload,
        learning_root=candidate_root.parents[3],
        data_root=data_root,
    )

    assert proof_error == "training_source_time_contract_unverified"


def test_rehashed_replay_manifest_cannot_change_cost_scenario(
    tmp_path: Path,
) -> None:
    candidate_root, candidate_bytes, data_root, replay_path = (
        _source_bound_candidate_package(tmp_path)
    )
    manifest = json.loads(replay_path.read_text(encoding="utf-8"))
    forged_hash = "sha256:" + "f" * 64
    manifest["coverage"]["cost_scenario_hash"] = forged_hash
    manifest["source_disclosures"]["cost"]["cost_scenario_hash"] = forged_hash
    forged_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    replay_path.write_bytes(forged_bytes)
    candidate_payload = json.loads(candidate_bytes)
    lineage_payload = json.loads(
        Path(candidate_payload["training_lineage_manifest_path"]).read_text(
            encoding="utf-8"
        )
    )
    lineage_payload["replay_manifests"][0]["file_hash"] = _sha(forged_bytes)

    proof_error = verify_personal_training_source_time_proof(
        lineage_payload=lineage_payload,
        learning_root=candidate_root.parents[3],
        data_root=data_root,
    )

    assert proof_error == "training_source_time_proof_cost_scenario_mismatch"


def test_distinct_verified_replay_manifests_bind_the_complete_merged_union(
    tmp_path: Path,
) -> None:
    candidate_root, candidate_bytes, data_root, _ = _source_bound_candidate_package(
        tmp_path,
        replay_windows=(("2025-04-01", "2025-04-30"), ("2025-05-01", "2025-05-31")),
    )
    candidate_payload = json.loads(candidate_bytes)
    lineage = json.loads(
        Path(candidate_payload["training_lineage_manifest_path"]).read_text(
            encoding="utf-8"
        )
    )
    references = lineage["replay_manifests"]
    assert len(references) == 2
    first_ids = set(references[0]["row_ids"])
    second_ids = set(references[1]["row_ids"])
    assert first_ids
    assert second_ids
    assert first_ids.isdisjoint(second_ids)
    assert set(lineage["merged_sample_ids"]) == first_ids | second_ids

    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )

    assert inspected.status == "historical_research_only", inspected.next_step
    assert inspected.reason_code == "independent_source_time_authority_missing"
    assert inspected.candidate is None
    lineage_path = Path(candidate_payload["training_lineage_manifest_path"])
    lineage_payload = json.loads(lineage_path.read_text(encoding="utf-8"))
    assert verify_personal_training_source_time_proof(
        lineage_payload=lineage_payload,
        learning_root=candidate_root.parents[3],
        data_root=data_root,
    ) is None


def test_self_asserted_synthetic_source_is_not_personal_candidate_proof(
    tmp_path: Path,
) -> None:
    candidate_root, _ = _candidate_package(tmp_path)
    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=tmp_path / "shadow-output",
        data_root=tmp_path / "empty-configured-data",
    )
    assert inspected.status == "historical_research_only"
    assert inspected.reason_code == "independent_source_time_authority_missing"
    assert inspected.candidate is None


def test_replay_manifest_outside_learning_root_is_rejected(
    tmp_path: Path,
) -> None:
    candidate_root, candidate_bytes, data_root, _ = _source_bound_candidate_package(
        tmp_path
    )
    payload = json.loads(candidate_bytes)
    lineage_path = Path(payload["training_lineage_manifest_path"])
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    outside_path = tmp_path / "outside" / "dataset.json"
    outside_path.parent.mkdir()
    outside_path.write_text("{}", encoding="utf-8")
    lineage["replay_manifests"][0]["path"] = str(outside_path.resolve())
    learning_root = candidate_root.parents[3]

    result = verify_personal_training_source_time_proof(
        lineage_payload=lineage,
        learning_root=learning_root,
        data_root=data_root,
    )

    assert result == "training_source_time_proof_manifest_path_invalid"


def test_source_contract_row_budget_fails_closed_before_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_root, _, data_root, _ = _source_bound_candidate_package(tmp_path)
    import app_module.recommendation.personal_candidate_inventory as inventory

    monkeypatch.setattr(inventory, "MAX_SOURCE_PROOF_CONTRACT_ROWS", 5)
    candidate_payload = json.loads(
        (candidate_root / "candidate.json").read_text(encoding="utf-8")
    )
    lineage_payload = json.loads(
        Path(candidate_payload["training_lineage_manifest_path"]).read_text(
            encoding="utf-8"
        )
    )
    result = verify_personal_training_source_time_proof(
        lineage_payload=lineage_payload,
        learning_root=candidate_root.parents[3],
        data_root=data_root,
    )
    assert result == "training_source_time_proof_budget_exceeded"


def test_rehashed_replay_manifest_cannot_forge_source_time_proof(
    tmp_path: Path,
) -> None:
    candidate_root, candidate_bytes, data_root, replay_path = (
        _source_bound_candidate_package(tmp_path)
    )
    candidate_payload = json.loads(candidate_bytes)
    learning_root = tmp_path / "shadow-output" / "recommendation_learning"
    lineage_path = Path(candidate_payload["training_lineage_manifest_path"])
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    replay_reference = lineage["replay_manifests"][0]

    replay_manifest = json.loads(replay_path.read_text(encoding="utf-8"))
    replay_manifest["samples"][0]["feature_available_date"] = "2025-04-02"
    replay_manifest["dataset_hash"] = "sha256:" + "a" * 64
    forged_bytes = json.dumps(
        replay_manifest, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    replay_path.write_bytes(forged_bytes)
    replay_reference["file_hash"] = _sha(forged_bytes)
    replay_reference["dataset_hash"] = replay_manifest["dataset_hash"]

    from ml_module.recommendation_training_lineage import (
        _hash_payload,
        training_pit_hash_from_payload,
        training_source_hash_from_payload,
    )

    lineage.pop("manifest_hash", None)
    lineage["training_source_hash"] = training_source_hash_from_payload(lineage)
    lineage["training_pit_hash"] = training_pit_hash_from_payload(lineage)
    forged_lineage_hash = _hash_payload(lineage)
    lineage["manifest_hash"] = forged_lineage_hash
    forged_lineage_path = (
        learning_root
        / "training_lineage"
        / str(lineage["decision_date"])
        / forged_lineage_hash.split(":", 1)[1]
        / "lineage.json"
    )
    forged_lineage_path.parent.mkdir(parents=True)
    forged_lineage_path.write_text(
        json.dumps(lineage, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    candidate_payload["training_lineage_manifest_hash"] = forged_lineage_hash
    candidate_payload["training_lineage_manifest_path"] = str(forged_lineage_path)
    forged_candidate_bytes = json.dumps(
        candidate_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    (candidate_root / "candidate.json").write_bytes(forged_candidate_bytes)

    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )
    assert inspected.status == "historical_research_only"
    assert inspected.reason_code == "independent_source_time_authority_missing"
    assert inspected.candidate is None
    assert verify_personal_training_source_time_proof(
        lineage_payload=lineage,
        learning_root=learning_root,
        data_root=data_root,
    ) == "training_source_time_replay_mismatch"


def test_configured_source_change_is_detected_and_consumer_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_root, candidate_bytes, data_root, _ = _source_bound_candidate_package(
        tmp_path
    )
    database = data_root / "sqlite" / "twstock.db"
    connection = sqlite3.connect(database)
    connection.execute(
        'UPDATE technical_indicators SET available_at = ? WHERE "日期" = ? AND "證券代號" = ?',
        ("20251231", "20250331", "1101"),
    )
    connection.commit()
    connection.close()

    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )
    assert inspected.status == "historical_research_only"
    assert inspected.reason_code == "independent_source_time_authority_missing"
    assert inspected.candidate is None

    from app_module.recommendation_calibration_consumer import (
        _load_candidate_training_provenance,
    )

    provenance, error = _load_candidate_training_provenance(
        candidate_root=candidate_root,
        candidate_payload=json.loads(candidate_bytes),
        decision_date="2025-06-30",
        require_personal_source_time=True,
        data_root=data_root,
    )
    assert error == "candidate_training_source_time_unverified_fail_closed"
    assert provenance.get("status") == "legacy_unproven"

    from app_module.recommendation_calibration_consumer import (
        RecommendationCalibrationConsumer,
    )
    from app_module.recommendation.personal_use_policy import (
        PERSONAL_CALIBRATED_PROBABILITY_MODE,
        PersonalCalibrationCandidateV1,
        RecommendationPersonalUseSelectionV1,
        save_personal_use_policy,
    )

    candidate_payload = json.loads(candidate_bytes)
    candidate_ref = PersonalCalibrationCandidateV1(
        candidate_id=CANDIDATE_ID,
        candidate_root=str(candidate_root.resolve()),
        candidate_json_sha256=_sha(candidate_bytes),
        candidate_manifest_hash=str(candidate_payload["manifest_hash"]),
        candidate_artifact_hash=str(candidate_payload["artifact_hash"]),
        candidate_freeze_hash=str(candidate_payload["candidate_freeze_hash"]),
        dataset_hash=str(candidate_payload["dataset_hash"]),
    )
    policy = save_personal_use_policy(
        tmp_path / "isolated-personal-policy.json",
        RecommendationPersonalUseSelectionV1(
            scope_id="source-proof-before-model-load-test",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            candidate=candidate_ref,
        ),
        expected_revision=0,
    )
    consumer = RecommendationCalibrationConsumer(
        pointer_path=Path(policy.storage_path or ""),
        feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        data_root=data_root,
        personal_use_policy=policy,
    )
    loader_called = False

    def reject_model_load(*args: object, **kwargs: object) -> object:
        nonlocal loader_called
        loader_called = True
        raise AssertionError("來源時間證明失敗時不可先解碼模型")

    monkeypatch.setattr(consumer._loader, "load", reject_model_load)
    consumer_status = consumer.reload(
        decision_date=str(candidate_payload["training_as_of"])
    )
    assert consumer_status == "rule_only"
    assert consumer._blocker == "independent_source_time_authority_missing"
    assert loader_called is False


def test_practical_source_proof_budget_supports_64_dates_32_symbols(
    tmp_path: Path,
) -> None:
    package_started = perf_counter()
    candidate_root, _, data_root, _ = _source_bound_candidate_package(
        tmp_path,
        symbols=tuple(f"{index:04d}" for index in range(32)),
        decision_dates=64,
        days=730,
    )
    package_elapsed = perf_counter() - package_started
    inventory_started = perf_counter()
    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=tmp_path / "shadow-output",
        data_root=data_root,
    )
    inventory_elapsed = perf_counter() - inventory_started
    assert inspected.status == "historical_research_only", inspected.next_step
    assert inspected.reason_code == "independent_source_time_authority_missing"
    assert inspected.candidate is None
    assert inspected.training_row_count == 64 * 32

    candidate_payload = json.loads(
        (candidate_root / "candidate.json").read_text(encoding="utf-8")
    )
    lineage_payload = json.loads(
        Path(candidate_payload["training_lineage_manifest_path"]).read_text(
            encoding="utf-8"
        )
    )
    verification_started = perf_counter()
    source_consistency_error = verify_personal_training_source_time_proof(
        lineage_payload=lineage_payload,
        learning_root=candidate_root.parents[3],
        data_root=data_root,
    )
    verification_elapsed = perf_counter() - verification_started
    assert source_consistency_error is None
    print(
        "source-time proof timing (64 dates / 32 symbols / 2048 rows): "
        + json.dumps(
            {
                "fixture_and_initial_replay_seconds": round(package_elapsed, 3),
                "inventory_admission_seconds": round(inventory_elapsed, 3),
                "bounded_source_consistency_seconds": round(verification_elapsed, 3),
                "note": "direct internal consistency check only; not an admission or official PIT proof",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    assert package_elapsed + inventory_elapsed + verification_elapsed < 30.0


def test_missing_lineage_is_reported_as_legacy_unproven(tmp_path: Path) -> None:
    candidate_root, _ = _candidate_package(tmp_path, with_lineage=False)
    output_root = tmp_path / "shadow-output"

    listing = list_personal_calibration_candidates(explicit_output_root=output_root)
    assert listing.entries[0].status == "legacy_unproven"
    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=output_root,
    )
    assert inspected.status == "legacy_unproven"
    assert inspected.reason_code == "training_lineage_missing"
    assert inspected.candidate is None
    assert "重跑" in inspected.next_step


def test_historical_research_lineage_is_not_personal_runtime_eligible(
    tmp_path: Path,
) -> None:
    candidate_root, _ = _candidate_package(tmp_path, historical_only=True)
    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=tmp_path / "shadow-output",
    )
    assert inspected.status == "historical_research_only"
    assert inspected.reason_code == "training_not_decision_time_eligible"
    assert inspected.candidate is None


def test_artifact_tampering_and_outside_root_fail_closed(tmp_path: Path) -> None:
    candidate_root, _ = _candidate_package(tmp_path)
    output_root = tmp_path / "shadow-output"
    (candidate_root / "model.joblib").write_bytes(b"tampered")
    tampered = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=output_root,
    )
    assert tampered.status == "unavailable"
    assert tampered.reason_code == "artifact_hash_mismatch"
    assert tampered.candidate is None

    outside = tmp_path / "outside" / "candidate"
    outside.mkdir(parents=True)
    rejected = inspect_personal_calibration_candidate(
        candidate_root=outside,
        explicit_output_root=output_root,
    )
    assert rejected.status == "unavailable"
    assert rejected.reason_code == "path_outside_or_reparse_rejected"


def test_candidate_frozen_time_must_match_the_manifest(tmp_path: Path) -> None:
    candidate_root, candidate_bytes = _candidate_package(tmp_path)
    payload = json.loads(candidate_bytes)
    payload["candidate_frozen_at"] = "2025-04-29T14:00:00+00:00"
    (candidate_root / "candidate.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=tmp_path / "shadow-output",
    )
    assert inspected.status == "unavailable"
    assert inspected.reason_code == "candidate_frozen_at_mismatch"
    assert inspected.candidate is None


def test_candidate_count_budget_is_explicitly_truncated(tmp_path: Path) -> None:
    output_root = tmp_path / "shadow-output"
    candidates = (
        output_root
        / "recommendation_learning"
        / "runs"
        / TRAINING_DAY
        / "candidates"
    )
    payload = {
        "schema_version": "recommendation-calibration-candidate.v1",
        "candidate_id": "",
    }
    candidates.mkdir(parents=True)
    for index in range(501):
        candidate_id = f"candidate-{index:03d}"
        candidate_root = candidates / candidate_id
        candidate_root.mkdir()
        candidate_payload = {**payload, "candidate_id": candidate_id}
        (candidate_root / "candidate.json").write_text(
            json.dumps(candidate_payload), encoding="utf-8"
        )

    listing = list_personal_calibration_candidates(explicit_output_root=output_root)
    assert listing.status == "truncated"
    assert listing.truncated is True
    assert listing.candidates_scanned == 500
    assert len(listing.entries) == 500
    assert "candidate_limit_reached:500" in listing.warnings


def test_directory_entry_budget_and_unreadable_run_root_are_not_reported_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.recommendation.personal_candidate_inventory as inventory

    output_root = tmp_path / "shadow-output"
    runs_root = output_root / "recommendation_learning" / "runs"
    runs_root.mkdir(parents=True)
    for index in range(12):
        (runs_root / f"irrelevant-{index:02d}").mkdir()
    monkeypatch.setattr(inventory, "MAX_DIRECTORY_ENTRIES", 5)
    limited = list_personal_calibration_candidates(explicit_output_root=output_root)
    assert limited.status == "truncated"
    assert limited.truncated is True
    assert "directory_entry_limit_reached:5" in limited.warnings

    monkeypatch.setattr(inventory, "MAX_DIRECTORY_ENTRIES", 10_000)
    original_scandir = inventory.os.scandir

    def denied(path: str | Path) -> Iterator[os.DirEntry[str]]:
        if Path(path) == runs_root:
            raise PermissionError("fixture denies run listing")
        return original_scandir(path)

    monkeypatch.setattr(inventory.os, "scandir", denied)
    unreadable = list_personal_calibration_candidates(explicit_output_root=output_root)
    assert unreadable.status == "incomplete"
    assert unreadable.entries == ()
    assert "runs_directory_unreadable" in unreadable.warnings
    assert "無法讀取" in unreadable.next_step


def test_unreadable_candidate_directory_is_not_reported_as_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_root, _ = _candidate_package(tmp_path)
    candidates_dir = candidate_root.parent
    output_root = tmp_path / "shadow-output"
    import app_module.recommendation.personal_candidate_inventory as inventory

    original_scandir = inventory.os.scandir

    def denied(path: str | Path) -> Iterator[os.DirEntry[str]]:
        if Path(path) == candidates_dir:
            raise PermissionError("fixture denies candidate listing")
        return original_scandir(path)

    monkeypatch.setattr(inventory.os, "scandir", denied)
    listing = list_personal_calibration_candidates(explicit_output_root=output_root)
    assert listing.status == "incomplete"
    assert listing.entries == ()
    assert any("candidate_directory_unreadable" in item for item in listing.warnings)


def test_inspection_honors_cancellation_and_artifact_byte_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_root, _ = _candidate_package(tmp_path)
    with pytest.raises(PersonalCandidateInventoryCancelled):
        inspect_personal_calibration_candidate(
            candidate_root=candidate_root,
            explicit_output_root=tmp_path / "shadow-output",
            cancellation_requested=lambda: True,
        )

    import app_module.recommendation.personal_candidate_inventory as inventory

    monkeypatch.setattr(inventory, "MAX_ARTIFACT_BYTES", 4)
    over_budget = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        explicit_output_root=tmp_path / "shadow-output",
    )
    assert over_budget.status == "unavailable"
    assert over_budget.reason_code == "artifact_size_limit_exceeded"
    assert over_budget.candidate is None
