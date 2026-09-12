from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app_module.recommendation_calibration import sample_evidence_rows
from app_module.v41_historical_method_pack import (
    build_sample_v41_historical_method_pack,
    build_v41_historical_method_pack,
    write_frozen_method_pack,
)


def test_manifest_has_row_level_time_identity_and_candidate_gaps() -> None:
    pack = build_sample_v41_historical_method_pack()
    manifest = pack["dataset_manifest"]
    row = manifest["rows"][0]

    assert {
        "decision_date",
        "available_at",
        "label_maturity",
        "strategy_version_id",
        "strategy_config_id",
        "universe_policy_id",
        "return_basis",
        "benchmark_id",
        "cost_model_id",
        "source_hash",
        "gap_codes",
    }.issubset(row)
    assert row["label_maturity"] == "mature"
    assert row["return_basis"] == "close_to_close_event_date"
    assert manifest["candidate_coverage"]["chip_funding_v1"]["status"] == "blocked"
    assert manifest["candidate_coverage"]["pit_theme_v1"]["status"] == "blocked"


def test_candidate_available_at_after_decision_is_fail_closed() -> None:
    events, outcomes = sample_evidence_rows()
    event = events[0]
    metadata = {
        **event.metadata,
        "chip_score_bp": 6000,
        "funding_score_bp": 6000,
        "chip_available_at": "2099-01-01T00:00:00+08:00",
        "funding_available_at": "2024-01-02T16:00:00+08:00",
        "chip_source_hash": "sha256:" + "a" * 64,
        "funding_source_hash": "sha256:" + "b" * 64,
    }
    dataset = build_v41_historical_method_pack(
        (replace(event, metadata=metadata),),
        outcomes,
        source_mode="test_only",
    )
    row = dataset["dataset_manifest"]["rows"][0]
    candidate = row["candidate_features"]["chip_funding_v1"]

    assert candidate["status"] == "blocked"
    assert "chip_available_at_after_decision" in candidate["gap_codes"]
    assert row["eligible_for_calibration"] is True


def test_missing_outcome_is_machine_readable_and_never_promotable() -> None:
    events, _ = sample_evidence_rows()
    pack = build_v41_historical_method_pack(
        events[:1],
        (),
        source_mode="test_only",
    )

    assert pack["calibration_report"]["status"] == "not_evaluable"
    assert pack["natural_time_insufficiency"]["status"] == "blocked_missing_outcome"
    assert pack["dataset_manifest"]["row_classification"]["label_maturity_counts"]["missing_outcome"] == 2
    assert pack["frozen_candidate_artifact"]["frozen"] is True
    assert pack["frozen_candidate_artifact"]["access_boundary"]["promotion_eligible"] is False
    assert pack["frozen_candidate_artifact"]["access_boundary"]["production_eligible"] is False


def test_frozen_pack_writer_is_create_only(tmp_path: Path) -> None:
    pack = build_sample_v41_historical_method_pack()
    paths = write_frozen_method_pack(pack, tmp_path)

    assert set(paths) == {
        "historical_dataset_manifest.json",
        "historical_calibration_report.json",
        "frozen_candidate_artifact.json",
    }
    with pytest.raises(FileExistsError, match="拒絕覆寫"):
        write_frozen_method_pack(pack, tmp_path)


def test_calibration_metrics_include_discrimination_coverage_turnover_and_uncertainty() -> None:
    pack = build_sample_v41_historical_method_pack()
    metrics = pack["calibration_report"]["oos"]["targets"]["upside_20d"]["feature_sets"]["score_percentile_v1"]["calibrated"]

    assert metrics["discrimination"]["status"] == "measured"
    assert metrics["coverage"]["coverage_bp"] is not None
    assert "turnover" in metrics
    assert "positive_rate_ci95_bp" in metrics["uncertainty"]
