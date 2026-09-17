from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation_calibration_consumer import RecommendationCalibrationProjection
from app_module.recommendation_service import RecommendationService
from ml_module.recommendation_inference_provenance import read_inference_projection_receipt


def _make_database(path: Path, *, days: int = 90, start: date = date(2014, 1, 1)) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE daily_prices (
            日期 TEXT NOT NULL,
            證券代號 TEXT NOT NULL,
            成交股數 INTEGER,
            成交金額 INTEGER,
            開盤價 TEXT,
            最高價 TEXT,
            最低價 TEXT,
            收盤價 TEXT
        );
        CREATE TABLE technical_indicators (
            日期 TEXT NOT NULL,
            證券代號 TEXT NOT NULL,
            RSI TEXT,
            MACD TEXT,
            ADX TEXT
        );
        CREATE TABLE market_indices (
            日期 TEXT NOT NULL,
            收盤指數 TEXT,
            收盤價 TEXT
        );
        CREATE TABLE industry_indices (
            日期 TEXT NOT NULL,
            指數名稱 TEXT,
            收盤指數 TEXT
        );
        """
    )
    for offset in range(days):
        current = (start + timedelta(days=offset)).strftime("%Y%m%d")
        connection.execute(
            "INSERT INTO market_indices VALUES (?, ?, ?)",
            (current, str(10_000 + offset), str(10_000 + offset)),
        )
        close = 100 + offset
        connection.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (current, "AAA", 1000 + offset, close * 100, close, close + 1, close - 1, close),
        )
        connection.execute(
            "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)",
            (current, "AAA", "55", "1.5", "20"),
        )
    connection.commit()
    connection.close()


class _RecordingConsumer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def active_after_cost_baseline(self, *, decision_date: str):
        assert decision_date == "2014-03-31"
        return "after_cost_null_benchmark_50pct_v1", 5_000

    def project_many(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["decision_date"] == "2014-03-31"
        feature_values = kwargs["feature_values_by_symbol"]["AAA"]
        assert len(feature_values) == 20
        return {
            "AAA": RecommendationCalibrationProjection(
                stock_code="AAA",
                ranking_score_bp=7_200,
                ranking_percentile_bp=8_100,
                ranking_method="absolute_return_shadow_candidate",
                calibrated_probability_bp=5_800,
                calibrated_probability_status="shadow_candidate",
                after_cost_profit_probability_bp=5_700,
                after_cost_profit_probability_status="shadow_candidate",
                confidence_tier="research_candidate",
                evidence_confidence="shadow_candidate",
                sample_size=120,
                horizon="20 trading days",
                cost_basis="fixed_round_trip_bp=50; observed liquidity",
                cost_basis_bp=50,
                model_version="candidate-model-1",
                dataset_version="dataset-1",
                source_trace=(
                    "candidate:candidate-model-1",
                    "dataset:dataset-1",
                    "after_cost_baseline:after_cost_null_benchmark_50pct_v1",
                    "after_cost_baseline_contract:independent_null_benchmark_v1",
                ),
                warnings=("shadow-only",),
                status="active_candidate",
            )
        }


def _recommendation() -> RecommendationDTO:
    return RecommendationDTO(
        stock_code="AAA",
        stock_name="測試股票",
        close_price=Decimal("100"),
        price_change=0.0,
        total_score=80.0,
        indicator_score=80.0,
        pattern_score=80.0,
        volume_score=80.0,
        recommendation_reasons="量價結構",
        industry="",
        regime_match=True,
    )


def _verified_candidate(
    tmp_path: Path,
    *,
    candidate_day: str,
    training_as_of: str,
    samples: tuple[Any, ...] | None = None,
    feature_names: tuple[str, ...] | None = None,
    feature_schema: tuple[tuple[str, str, str], ...] | None = None,
    feature_registry_hash: str | None = None,
    dataset_id: str = "dataset-verified-integration",
) -> tuple[object, Path, dict[str, object]]:
    """Build a real candidate package carrying the P1 training lineage."""

    from ml_module.recommendation_calibration_training import (
        RecommendationCalibrationTrainingConfig,
        RecommendationCalibrationTrainingService,
    )
    from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
    from ml_module.recommendation_training_lineage import (
        build_recommendation_training_lineage,
        persist_recommendation_training_lineage,
        recommendation_training_dataset_hash,
    )
    from test_daily_recommendation_learning_loop import (
        FEATURE_NAMES,
        FEATURE_REGISTRY_HASH,
        FEATURE_SCHEMA,
        _samples,
    )

    resolved_samples = samples if samples is not None else _samples(0)
    resolved_feature_names = feature_names if feature_names is not None else FEATURE_NAMES
    resolved_feature_schema = feature_schema if feature_schema is not None else FEATURE_SCHEMA
    resolved_registry_hash = (
        feature_registry_hash
        if feature_registry_hash is not None
        else FEATURE_REGISTRY_HASH
    )
    dataset_hash = recommendation_training_dataset_hash(resolved_samples)
    result = RecommendationCalibrationTrainingService().fit(
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        samples=resolved_samples,
        feature_names=resolved_feature_names,
        feature_schema=resolved_feature_schema,
        feature_registry_hash=resolved_registry_hash,
        training_as_of=training_as_of,
        fixed_round_trip_cost_bp=50,
        dataset_quality={"formal_candidate_eligible": True},
        created_at=f"{candidate_day}T00:00:00+00:00",
        config=RecommendationCalibrationTrainingConfig(
            minimum_calibration_samples=10,
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )
    candidate_root = tmp_path / "candidate-verified"
    result.persist(candidate_root)
    candidate_metadata = json.loads(
        (candidate_root / "candidate.json").read_text(encoding="utf-8")
    )
    lineage = build_recommendation_training_lineage(
        learning_root=tmp_path / "learning",
        run_id=f"daily-recommendation-learning:{candidate_day}:verified",
        run_scope="integration",
        decision_date=candidate_day,
        training_as_of=training_as_of,
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        samples=resolved_samples,
        feature_schema=resolved_feature_schema,
        feature_registry_hash=resolved_registry_hash,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        dataset_quality={"formal_candidate_eligible": True},
        training_result=result,
        training_config=RecommendationCalibrationTrainingConfig(
            minimum_calibration_samples=10,
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
        candidate_id=result.candidate_id,
        candidate_manifest_hash=result.manifest.manifest_hash,
        candidate_artifact_hash=result.artifact_hash,
        source_groups={"replay": resolved_samples},
    )
    lineage_path = persist_recommendation_training_lineage(tmp_path / "learning", lineage)
    candidate_metadata.update(
        {
            "training_lineage_manifest_hash": lineage.manifest_hash,
            "training_lineage_manifest_path": str(lineage_path),
            "training_source_hash": lineage.payload["training_source_hash"],
            "training_pit_hash": lineage.payload["training_pit_hash"],
            "feature_transform_contract": lineage.payload["feature_transform_contract"],
            "feature_transform_contract_hash": lineage.payload[
                "feature_transform_contract"
            ]["contract_hash"],
        }
    )
    (candidate_root / "candidate.json").write_text(
        json.dumps(candidate_metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result, candidate_root, candidate_metadata


def _core_feature_samples() -> tuple[Any, ...]:
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
    from test_daily_recommendation_learning_loop import _samples

    feature_count = len(CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema)
    return tuple(
        replace(
            row,
            feature_values=(
                tuple(row.feature_values[:2])
                + tuple(
                    (row_index + 1) * (feature_index + 1)
                    for feature_index in range(2, feature_count)
                )
            ),
        )
        for row_index, row in enumerate(_samples(0))
    )


def test_normal_recommendation_service_consumes_injected_projection_adapter(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    _make_database(database)
    consumer = _RecordingConsumer()
    config = SimpleNamespace(
        db_file=database,
        default_start_date="2014-01-01",
        output_root=tmp_path / "output",
        data_root=tmp_path / "formal-data",
    )
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )
    recommendation = _recommendation()

    service._apply_recommendation_calibration([recommendation], decision_date="2014-03-31")

    assert len(consumer.calls) == 1
    assert consumer.calls[0]["after_cost_rule_probability_by_symbol"] == {"AAA": 5_000}
    assert consumer.calls[0]["after_cost_rule_baseline_id_by_symbol"] == {
        "AAA": "after_cost_null_benchmark_50pct_v1"
    }
    assert recommendation.calibrated_probability_bp == 5_800
    assert recommendation.after_cost_profit_probability_bp == 5_700
    assert recommendation.sample_size == 120
    assert recommendation.calibration_model_version == "candidate-model-1"
    assert recommendation.calibration_dataset_version == "dataset-1"
    assert recommendation.calibration_status == "active_candidate"
    assert recommendation.calibration_source_trace == [
        "candidate:candidate-model-1",
        "dataset:dataset-1",
        "after_cost_baseline:after_cost_null_benchmark_50pct_v1",
        "after_cost_baseline_contract:independent_null_benchmark_v1",
    ]
    assert service.last_run_context["calibration_projection_status"] == "active_candidate"
    assert (
        service.last_run_context["calibration_after_cost_baseline_id"]
        == "after_cost_null_benchmark_50pct_v1"
    )


@pytest.mark.parametrize("failure", (PermissionError("receipt directory denied"), ValueError("immutable receipt conflict")))
def test_active_projection_receipt_storage_failure_withdraws_model_fields_but_keeps_rule_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    database = tmp_path / "source.db"
    _make_database(database)
    consumer = _RecordingConsumer()
    consumer.pointer_path = tmp_path / "active-pointer.json"
    consumer.active_identity = lambda *, decision_date: {
        "candidate_id": "candidate-model-1",
    }
    service = RecommendationService(
        SimpleNamespace(
            db_file=database,
            default_start_date="2014-01-01",
            output_root=tmp_path / "output",
            data_root=tmp_path / "formal-data",
        ),
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )
    monkeypatch.setattr(
        RecommendationService,
        "_persist_calibration_projection_receipt",
        staticmethod(lambda **_: (_ for _ in ()).throw(failure)),
    )
    recommendation = _recommendation()
    original_total_score = recommendation.total_score

    service._apply_recommendation_calibration([recommendation], decision_date="2014-03-31")

    assert recommendation.total_score == original_total_score
    assert recommendation.calibrated_probability_bp is None
    assert recommendation.after_cost_profit_probability_bp is None
    assert recommendation.ranking_score_bp is None
    assert recommendation.calibration_status == "rule_only"
    assert recommendation.calibration_provenance["provenance_status"] == "unavailable"
    assert recommendation.calibration_provenance["projection_receipt_status"] == "not_persisted"
    assert service.last_run_context["calibration_projection_status"] == "unavailable"
    assert service.last_run_context["calibration_projection_receipt_status"] == "unavailable"
    assert any(
        warning.startswith("calibration_projection_receipt_unavailable:")
        for warning in service.last_run_context["warnings"]
    )


def test_active_projection_receipt_candidate_race_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    _make_database(database)
    consumer = _RecordingConsumer()
    consumer.pointer_path = tmp_path / "active-pointer.json"
    identities = iter(
        (
            {"candidate_id": "candidate-model-1"},
            {"candidate_id": "candidate-model-2"},
        )
    )
    consumer.active_identity = lambda *, decision_date: next(identities)
    service = RecommendationService(
        SimpleNamespace(
            db_file=database,
            default_start_date="2014-01-01",
            output_root=tmp_path / "output",
            data_root=tmp_path / "formal-data",
        ),
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )
    recommendation = _recommendation()
    original_total_score = recommendation.total_score

    service._apply_recommendation_calibration([recommendation], decision_date="2014-03-31")

    assert recommendation.total_score == original_total_score
    assert recommendation.calibrated_probability_bp is None
    assert recommendation.after_cost_profit_probability_bp is None
    assert recommendation.calibration_status == "rule_only"
    assert recommendation.calibration_provenance["provenance_status"] == "unavailable"
    assert "candidate/model race" in service.last_run_context[
        "calibration_projection_receipt_error_detail"
    ]


def test_isolated_producer_consumer_advice_workbench_ui_path(tmp_path: Path) -> None:
    """Verify the RecommendationService adapter reaches the existing UI contract.

    The consumer seam is injected with a typed projection so this test isolates
    producer→Advice→UI wiring; the following test exercises the real consumer.
    """

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import pytest

    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from app_module.advice_composer import AdviceComposer
    from app_module.advice_dtos import AdviceMode
    from app_module.advice_policy import AdvicePolicy
    from app_module.workbench_dtos import WorkbenchAccessBoundary, WorkbenchDashboardDTO
    from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView

    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)

    database = tmp_path / "source.db"
    _make_database(database)
    consumer = _RecordingConsumer()
    config = SimpleNamespace(
        db_file=database,
        default_start_date="2014-01-01",
        output_root=tmp_path / "output",
        data_root=tmp_path / "formal-data",
    )
    recommendation_service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )
    recommendation = _recommendation()
    recommendation_service._apply_recommendation_calibration(
        [recommendation],
        decision_date="2014-03-31",
    )
    assert recommendation_service.last_calibration_projections["AAA"].status == "active_candidate"

    result = RecommendationResultDTO(
        result_id="rec-isolated-20140331",
        result_name="isolated recommendation",
        config={
            "strategy_status": "promoted",
            "parameters_locked": True,
            "disclosure_complete": True,
            "execution_feasible": True,
            "risk_budget_available": True,
        },
        recommendations=[recommendation],
    )
    advice_dashboard = AdviceComposer(AdvicePolicy()).compose(
        recommendations=result,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date="2014-03-31",
        data_as_of_date="2014-03-30",
        mode=AdviceMode.GUIDED,
    )
    advice = advice_dashboard.recommendations[0]
    assert advice.calibrated_probability_bp == 5_800
    assert advice.after_cost_profit_probability_bp == 5_700
    assert advice.ranking_score_bp == 7_200
    assert advice.sample_size == 120

    dashboard = WorkbenchDashboardDTO(
        as_of_date=date(2014, 3, 31),
        generated_at=datetime(2014, 3, 31, 12, 0, 0),
        source_mode="isolated_producer_consumer",
        access_boundary=WorkbenchAccessBoundary(),
        status_strip=(),
        review_items=(),
        evidence_summary=(),
        market_context={},
        portfolio_watchlist_summary={},
        daily_checklist=(),
        advice_dashboard=advice_dashboard,
    )
    view = UnifiedDecisionWorkbenchView(dashboard=dashboard, auto_refresh=False)
    view._show_advice_row_presentation(view.advice_recommendation_model, 0)
    rendered = view.advice_presentation_detail.text()

    assert "排名分數：7200（僅作排序，不等於機率）" in rendered
    assert "校準機率：58.00%（研究中／shadow）" in rendered
    assert "成本後獲利機率：57.00%（研究中／shadow）" in rendered
    assert "模型：candidate-model-1" in rendered
    assert "資料集：dataset-1" in rendered
    assert "適用期間：20 trading days" in rendered
    assert "樣本：120" in rendered
    assert "自然前瞻驗證" not in rendered
    view.close()


def test_real_consumer_producer_advice_workbench_ui_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Exercise real consumer/receipt to DTO/Advice/UI wiring in isolation.

    The feature builder is intentionally replaced and the result DTO is
    assembled in this test; the public-service, real-builder, and repository
    readback boundary is covered separately below.
    """

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import pytest

    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from app_module.advice_composer import AdviceComposer
    from app_module.advice_dtos import AdviceMode
    from app_module.advice_policy import AdvicePolicy
    from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer
    from app_module.workbench_dtos import WorkbenchAccessBoundary, WorkbenchDashboardDTO
    from ml_module.historical_feature_builder import HistoricalFeatureBuilder
    from ml_module.recommendation_calibration_authority import RecommendationCalibrationPromotionAuthority
    from test_daily_recommendation_learning_loop import (
        FEATURE_REGISTRY_HASH,
        FEATURE_SCHEMA,
        _natural_receipt,
    )
    from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView

    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)

    trained_result, candidate_root, candidate_metadata = _verified_candidate(
        tmp_path,
        candidate_day="2026-06-01",
        training_as_of="2026-05-31",
    )
    natural_evidence = _natural_receipt(
        tmp_path,
        root=candidate_root,
        candidate_day="2026-06-01",
        evaluation_day="2026-06-22",
    )
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    decision = authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=trained_result.candidate_id,
        candidate_root=candidate_root,
        candidate_metadata=candidate_metadata,
        natural_evidence=natural_evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert decision.decision == "adopt"

    real_consumer = RecommendationCalibrationConsumer(
        pointer_path=tmp_path / "authority" / "recommendation-calibration-active-pointer.json",
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "formal-data",
    )
    assert real_consumer.reload(decision_date="2026-06-22") == "active"

    database = tmp_path / "source.db"
    _make_database(database, start=date(2026, 1, 1))
    # Adapter/UI wiring is the isolated boundary here: the builder is replaced
    # with a two-feature row.  The public-service test below keeps the real
    # HistoricalFeatureBuilder and repository path intact.
    monkeypatch.setattr(
        HistoricalFeatureBuilder,
        "compute",
        lambda _self, _snapshot, *, industry_index_name_by_symbol: (
            SimpleNamespace(
                symbol="AAA",
                values=(("momentum_bp", 1000), ("volume_ratio_bp", 2000)),
            ),
        ),
    )
    config = SimpleNamespace(
        db_file=database,
        default_start_date="2026-01-01",
        output_root=tmp_path / "output",
        data_root=tmp_path / "formal-data",
    )
    recommendation_service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
        calibration_consumer=real_consumer,
    )
    recommendation_service.last_run_context["result_id"] = "rec-real-consumer-20260622"
    recommendation = _recommendation()
    recommendation_service._apply_recommendation_calibration(
        [recommendation],
        decision_date="2026-06-22",
    )
    projection = recommendation_service.last_calibration_projections["AAA"]
    assert projection.status == "active_candidate", projection.warnings
    assert projection.calibrated_probability_bp is not None
    # This fixture's training rows use a declared after-cost baseline without
    # a persisted numeric rule value; the production service must keep it
    # unknown instead of reusing 5,000 bp.
    assert projection.after_cost_profit_probability_bp is None
    assert projection.horizon == "20 trading days"
    assert any(item.startswith("candidate:") for item in projection.source_trace)
    assert any(item.startswith("cost_scenario:") for item in projection.source_trace)
    receipt_metadata = recommendation_service.last_run_context["calibration_projection_receipt"]
    receipt = read_inference_projection_receipt(
        receipt_metadata["path"],
        expected_decision_date="2026-06-22",
        expected_candidate_id=trained_result.candidate_id,
        expected_result_id="rec-real-consumer-20260622",
        expected_stock_code="AAA",
    )
    assert receipt.receipt_hash == receipt_metadata["receipt_hash"]
    assert receipt.payload["training_provenance"]["status"] == "verified"
    assert receipt.payload["training_provenance"]["label_registry_hash"] == (
        candidate_metadata["label_registry_hash"]
    )
    assert receipt.payload["training_provenance"]["label_contract_id"] == (
        "recommendation-absolute-labels-v1"
    )
    assert receipt.payload["training_provenance"]["return_basis"] == (
        "close_to_close_event_date"
    )
    assert receipt.payload["projections"][0]["label_registry_hash"] == (
        candidate_metadata["label_registry_hash"]
    )
    assert receipt.payload["projections"][0]["label_contract_id"] == (
        "recommendation-absolute-labels-v1"
    )
    assert receipt.payload["projections"][0]["return_basis"] == (
        "close_to_close_event_date"
    )
    assert receipt.payload["training_provenance"]["status"] == "verified"
    assert receipt.payload["provenance_compatibility"]["status"] == "verified"
    assert receipt.payload["training_provenance"]["training_source_hash"] != receipt.payload[
        "inference_provenance"
    ]["inference_source_hash"]
    assert receipt.payload["training_provenance"]["training_pit_hash"] != receipt.payload[
        "inference_provenance"
    ]["inference_pit_hash"]
    assert recommendation.calibration_provenance["provenance_status"] == "verified"
    assert recommendation.calibration_provenance["projection_receipt_hash"] == receipt.receipt_hash
    result_round_trip = RecommendationResultDTO.from_dict(
        RecommendationResultDTO(
            result_id="rec-real-consumer-20260622",
            result_name="round-trip",
            config={},
            recommendations=[recommendation],
        ).to_dict()
    )
    assert result_round_trip.recommendations[0].calibration_provenance["projection_receipt_hash"] == receipt.receipt_hash
    assert "after_cost_baseline:unavailable" in projection.source_trace
    assert "after_cost_baseline_contract:declared_or_unavailable" in projection.source_trace
    mismatched_after_cost = real_consumer.project(
        stock_code="AAA",
        feature_values=(1000, 2000),
        rule_probability_bp=5_000,
        after_cost_rule_probability_bp=5_000,
        after_cost_rule_baseline_id="null_benchmark_50pct_v1",
        decision_date="2026-06-22",
    )
    assert mismatched_after_cost.status == "rule_only"
    assert mismatched_after_cost.warnings == (
        "after_cost_probability_baseline_mismatch_fail_closed",
    )

    advice_result = RecommendationResultDTO(
        result_id="rec-real-consumer-20260622",
        result_name="real consumer isolated recommendation",
        config={
            "strategy_status": "promoted",
            "parameters_locked": True,
            "disclosure_complete": True,
            "execution_feasible": True,
            "risk_budget_available": True,
        },
        recommendations=[recommendation],
    )
    advice_dashboard = AdviceComposer(AdvicePolicy()).compose(
        recommendations=advice_result,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date="2026-06-22",
        data_as_of_date="2026-06-21",
        mode=AdviceMode.GUIDED,
    )
    advice = advice_dashboard.recommendations[0]
    assert advice.calibrated_probability_bp == projection.calibrated_probability_bp
    assert advice.after_cost_profit_probability_bp is None
    assert advice.sample_size == projection.sample_size
    assert advice.calibration_provenance["projection_receipt_hash"] == receipt.receipt_hash

    dashboard = WorkbenchDashboardDTO(
        as_of_date=date(2026, 6, 22),
        generated_at=datetime(2026, 6, 22, 12, 0, 0),
        source_mode="isolated_real_consumer",
        access_boundary=WorkbenchAccessBoundary(),
        status_strip=(),
        review_items=(),
        evidence_summary=(),
        market_context={},
        portfolio_watchlist_summary={},
        daily_checklist=(),
        advice_dashboard=advice_dashboard,
    )
    view = UnifiedDecisionWorkbenchView(dashboard=dashboard, auto_refresh=False)
    view._show_advice_row_presentation(view.advice_recommendation_model, 0)
    rendered = view.advice_presentation_detail.text()

    assert "研究中／shadow" in rendered
    assert "適用期間：20 trading days" in rendered
    assert f"樣本：{projection.sample_size:,}" in rendered
    assert "cost_scenario:" in rendered
    assert "projection_receipt_path:" in rendered
    assert "自然前瞻驗證" not in rendered
    view.close()


def test_public_service_real_builder_saves_result_and_reverse_reads_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise public service, real builder, repository, and exact receipt lookup."""

    from app_module.recommendation_repository import RecommendationRepository
    from app_module.recommendation_save_coordinator import RecommendationSaveRequest
    from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer
    from app_module.evidence_event_dtos import (
        EvidenceDataQuality,
        EvidenceEvent,
        EvidenceEventType,
        EvidenceOutcome,
        EvidenceOutcomeStatus,
    )
    from app_module.evidence_event_repository import EvidenceEventRepository
    from app_module.journal_service import JournalService
    from app_module.personalization_action_recorder import PersonalizationDecisionRecorder
    from app_module.personalization_read_service import PersonalizationReadService
    from app_module.personalization_save_adapter import (
        PersonalizationRecommendationSaveAdapter,
    )
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
    from ml_module.recommendation_calibration_training import (
        RECOMMENDATION_LABEL_CONTRACT_ID,
    )
    from ml_module.recommendation_calibration_authority import RecommendationCalibrationPromotionAuthority
    from test_daily_recommendation_learning_loop import _natural_receipt
    from ml_module.recommendation_inference_provenance import (
        find_inference_projection_receipts,
        read_inference_projection_receipt,
    )

    class _RepositoryConfig(SimpleNamespace):
        def resolve_output_path(self, relative_path: str) -> Path:
            return Path(self.output_root) / relative_path

    feature_registry = CORE_LONG_HISTORY_FEATURE_REGISTRY
    feature_schema = feature_registry.canonical_schema
    feature_names = feature_registry.canonical_ids
    trained_result, candidate_root, candidate_metadata = _verified_candidate(
        tmp_path,
        candidate_day="2026-06-01",
        training_as_of="2026-05-31",
        samples=_core_feature_samples(),
        feature_names=feature_names,
        feature_schema=feature_schema,
        feature_registry_hash=feature_registry.registry_hash,
        dataset_id="dataset-public-service-integration",
    )
    natural_evidence = _natural_receipt(
        tmp_path,
        root=candidate_root,
        candidate_day="2026-06-01",
        evaluation_day="2026-06-22",
        feature_schema=feature_schema,
        feature_registry_hash=feature_registry.registry_hash,
    )
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    decision = authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=trained_result.candidate_id,
        candidate_root=candidate_root,
        candidate_metadata=candidate_metadata,
        natural_evidence=natural_evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert decision.decision == "adopt"

    database = tmp_path / "source.db"
    _make_database(database, start=date(2026, 1, 1))
    market_frame = pd.DataFrame(
        [
            {
                "日期": date(2026, 1, 1) + timedelta(days=offset),
                "證券代號": "AAA",
                "證券名稱": "測試股票",
                "收盤價": 100 + offset,
                "成交股數": 1_000 + offset,
            }
            for offset in range(173)
        ]
    )
    config = _RepositoryConfig(
        db_file=database,
        default_start_date="2026-01-01",
        output_root=tmp_path / "output",
        data_root=tmp_path / "formal-data",
        use_sqlite=False,
    )
    consumer = RecommendationCalibrationConsumer(
        pointer_path=tmp_path / "authority" / "recommendation-calibration-active-pointer.json",
        feature_schema=feature_schema,
        feature_registry_hash=feature_registry.registry_hash,
        data_root=config.data_root,
    )
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=lambda: market_frame.copy(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )

    # Only the rule scorer is deterministic here.  The public service still
    # runs its real SQLite snapshot provider and HistoricalFeatureBuilder.
    service.strategy_configurator.generate_recommendations = lambda _stock_df, _config: pd.DataFrame(
        {
            "TotalScore": [80],
            "FinalScore": [80],
            "收盤價": [Decimal("100")],
            "成交股數": [1_000],
        }
    )

    # Freeze only the RecommendationService clock so this real producer test
    # exercises an actual T-1 market cutoff: 2026-06-22 16:50 UTC is the next
    # Taipei market date (2026-06-23).  The source itself still selects its
    # latest row; no weekday/date-difference inference is used.
    import app_module.recommendation_service as recommendation_service_module

    class _FrozenRecommendationDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            current = datetime(2026, 6, 22, 16, 50, tzinfo=timezone.utc)
            return current.astimezone(tz) if tz is not None else current.replace(tzinfo=None)

    monkeypatch.setattr(
        recommendation_service_module,
        "datetime",
        _FrozenRecommendationDatetime,
    )
    recommendations = service.run_recommendation(
        {"recommendation_ranking": {"threshold_mode": "fixed"}},
        max_stocks=1,
        top_n=1,
        as_of_date=None,
        universe=["AAA"],
        historical_research=False,
        select_latest_available_cutoff=True,
    )
    assert len(recommendations) == 1
    result_id = str(service.last_run_context["result_id"])
    assert result_id.startswith("rec_")
    assert len(result_id) > len("rec_") + 16
    assert service.last_run_context["calibration_projection_receipt_status"] == "persisted"
    assert service.last_run_context["calibration_projection_receipt"]["result_id"] == result_id
    assert service.last_run_context["as_of_date"] == "2026-06-22"
    assert service.last_run_context["temporal_contract"] == (
        "recommendation-producer-clock.v1"
    )
    assert service.last_run_context["temporal_mode"] == "natural_producer_clock"
    assert service.last_run_context["cutoff_selection"] == (
        "producer_selected_latest_available_cutoff"
    )
    assert service.last_run_context["cutoff_policy"] == "source_latest_available_exact"
    assert service.last_run_context["prediction_decision_anchor"] == (
        "actual_producer_decision_at"
    )
    assert service.last_run_context["horizon_anchor"] == "immutable_projection_receipt"
    assert service.last_run_context["market_calendar_timezone"] == "Asia/Taipei"
    assert service.last_run_context["decision_at"] == (
        "2026-06-22T16:50:00.000000+00:00"
    )
    assert service.last_run_context["personalization_scope"]["decision_date"] == (
        "2026-06-23"
    )
    personalization_scope = service.last_run_context["personalization_scope"]
    assert personalization_scope["scope_id"] == "local_research_scope_v1"
    assert personalization_scope["scope_type"] == "local"
    assert personalization_scope["temporal_status"] == "verified"
    inference = recommendations[0].calibration_provenance
    assert len(inference["feature_rows"][0]["feature_ids"]) == len(feature_schema)
    assert inference["feature_builder_schema_hash"]
    assert inference["projection_receipt_result_id"] == result_id

    save_request = RecommendationSaveRequest(
        result_name="public service provenance integration",
        config={"_recommendation_run_context": service.last_run_context},
        recommendations=tuple(recommendations),
        current_profile=None,
        profile_meta={},
        current_regime=None,
    )
    result = save_request.build_result(
        recommendation_service=service,
        regime_service=MagicMock(),
    )
    # The save coordinator resolves the producer identity before repository I/O;
    # there is no post-hoc result_id binding after receipt publication.
    assert result.result_id == result_id
    repeated_result = save_request.build_result(
        recommendation_service=service,
        regime_service=MagicMock(),
    )
    assert repeated_result.result_id == result_id
    repository = RecommendationRepository(config)
    import app_module.recommendation_save_coordinator as save_coordinator_module

    # Keep persistence, ACK, and the first action before the explicitly
    # declared July forward label.  A real producer clock is still used for
    # the service decision above; this only makes the isolated lifecycle
    # fixture deterministic and lets the later report prove maturity.
    monkeypatch.setattr(
        save_coordinator_module,
        "datetime",
        _FrozenRecommendationDatetime,
    )
    save_outcome = save_request.persist(
        recommendation_repository=repository,
        universe_service=None,
        recommendation_service=service,
        regime_service=MagicMock(),
    )
    assert save_outcome.result_id == result_id
    assert save_outcome.personalization_delivery_statuses == ("persisted",)
    assert save_outcome.personalization_persisted_at
    loaded = repository.load_result(result_id)
    assert loaded is not None
    assert loaded.result_id == result_id
    receipt_metadata = loaded.run_context["calibration_projection_receipt"]
    persisted_provenance = loaded.recommendations[0].calibration_provenance
    assert persisted_provenance["projection_receipt_hash"] == receipt_metadata["receipt_hash"]

    matches = find_inference_projection_receipts(
        tmp_path / "authority",
        decision_date="2026-06-22",
        candidate_id=trained_result.candidate_id,
        result_id=loaded.result_id,
        stock_code="AAA",
    )
    assert len(matches) == 1
    receipt_path = matches[0].receipt_path
    assert receipt_path is not None
    receipt = read_inference_projection_receipt(
        receipt_path,
        expected_decision_date="2026-06-22",
        expected_candidate_id=trained_result.candidate_id,
        expected_result_id=loaded.result_id,
        expected_stock_code="AAA",
    )
    assert receipt.receipt_hash == receipt_metadata["receipt_hash"]

    # Continue through the real shared save/ACK/read path with a cross-day
    # scope.  The producer's source cutoff is 6/22, while its actual Taipei
    # decision market date is 6/23; the forward label must join to that
    # declared event date, not to the source cutoff date.
    saved_capture = PersonalizationRecommendationSaveAdapter().captures_from_result(
        loaded
    )[0]
    assert saved_capture.scope.decision_date == "2026-06-23"
    persisted_clock = datetime.fromisoformat(
        str(save_outcome.personalization_persisted_at).replace("Z", "+00:00")
    )
    delivered_at = (persisted_clock + timedelta(seconds=1)).isoformat(
        timespec="microseconds"
    )
    ack_recorded_at = (persisted_clock + timedelta(seconds=2)).isoformat(
        timespec="microseconds"
    )
    journal = JournalService(config)
    adapter = PersonalizationRecommendationSaveAdapter()
    ack = adapter.acknowledge_delivery(
        recommendation_repository=repository,
        journal_service=journal,
        result_id=result_id,
        scope_id=saved_capture.scope.scope_id,
        delivery_id=saved_capture.delivery_id,
        persisted_at=str(save_outcome.personalization_persisted_at),
        delivered_at=delivered_at,
        recorded_at=ack_recorded_at,
    )
    assert ack.status == "delivered"

    evidence_db = tmp_path / "personalization-evidence.sqlite"
    read_service = PersonalizationReadService.from_paths(
        output_root=config.output_root,
        evidence_db_path=evidence_db,
    )
    linked = read_service.projection_service.build_for_candidate(
        result_id=result_id,
        stock_code="AAA",
        personalization_scope_id=saved_capture.scope.scope_id,
        result=loaded,
        evaluated_as_of="2026-09-18",
        evaluation_cutoff_at=ack_recorded_at,
    )
    assert linked.status == "linked_prediction"
    assert linked.delivery_status == "delivered"
    assert linked.decision_date == "2026-06-23"
    assert linked.prediction["data_as_of_date"] == "2026-06-22"
    assert linked.outcome_status == "not_applicable"
    assert linked.late_delivery is False
    assert linked.prediction_decision_at == saved_capture.scope.decision_at
    assert linked.delivery_at == delivered_at
    assert linked.human_decision_at is None

    recorded = PersonalizationDecisionRecorder(
        journal,
        now=lambda: (persisted_clock + timedelta(seconds=3)).isoformat(
            timespec="microseconds"
        ),
    ).record(
        projection=linked,
        action="accepted",
        decision_kind="recommendation_response",
        request_id="request_public_service_cross_day",
        action_at=delivered_at,
        recorded_at=(persisted_clock + timedelta(seconds=3)).isoformat(
            timespec="microseconds"
        ),
        actor="user:integration",
        note="cross-day producer integration",
    )
    assert recorded.envelope.prediction_id == saved_capture.prediction_id

    identity = {
        "result_id": result_id,
        "stock_code": "AAA",
        "personalization_scope_id": saved_capture.scope.scope_id,
        "prediction_id": saved_capture.prediction_id,
        "prediction_receipt_hash": saved_capture.projection_receipt_hash,
        "horizon_days": 20,
        "cost_scenario_hash": saved_capture.cost_scenario_hash,
        "label_contract_id": RECOMMENDATION_LABEL_CONTRACT_ID,
        "return_basis": "close_to_close_event_date",
    }
    evidence = EvidenceEventRepository(object(), db_path=evidence_db)
    event = EvidenceEvent(
        event_id="event_public_service_cross_day",
        event_hash="sha256:" + ("a" * 64),
        event_date="2026-06-23",
        decision_date="2026-06-23",
        symbol="AAA",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="recommendation_service",
        source_id="public-service-cross-day-fixture",
        available_date="2026-06-23",
        data_quality=EvidenceDataQuality.OBSERVED,
        metadata=dict(identity),
        created_at=saved_capture.scope.decision_at,
    )
    evidence.insert_event(event)
    outcome_metadata = {
        **identity,
        "event_price_date": "2026-06-23",
        "outcome_price_date": "2026-07-21",
        "label_available_date": "2026-07-21",
        "label_available_at": "2026-07-21T08:00:00+00:00",
        "outcome_recorded_at": "2026-07-21T08:00:00+00:00",
        "label": 1,
        "outcome_tier": "natural_forward",
    }
    evidence.upsert_outcome(
        EvidenceOutcome(
            outcome_id="outcome_public_service_cross_day",
            event_id=event.event_id,
            window_days=20,
            return_basis="close_to_close_event_date",
            event_price_date="2026-06-23",
            outcome_price_date="2026-07-21",
            forward_return_bp=800,
            outcome_status=EvidenceOutcomeStatus.READY,
            data_quality=EvidenceDataQuality.OBSERVED,
            calculated_at="2026-07-21T08:00:00+00:00",
            data_as_of_date="2026-07-21",
            metadata=outcome_metadata,
        )
    )
    report = read_service.inspect_scope(
        scope_id=saved_capture.scope.scope_id,
        evaluated_as_of="2026-09-18",
        evaluation_cutoff_at="2026-09-18T00:00:00+00:00",
        result_id=result_id,
        stock_code="AAA",
    )
    assert report.source_consistency_status == "verified"
    assert report.source_completeness_status == "verified"
    assert report.denominators["prediction_available_count"] == 1
    assert report.denominators["action_recorded_count"] == 1
    assert report.denominators["outcome_ready_count"] == 1, report.diagnostics
    assert report.denominators["natural_forward_count"] == 1
    assert report.denominators["action_utility_count"] == 0
    assert report.denominators["evaluation_row_count"] == 1
    assert report.cohort["included_evaluation_row_count"] == 1
    assert report.cohort["excluded_reason_counts"] == {}
    evaluation_row = report.evaluation_rows[0]
    assert evaluation_row["decision_date"] == "2026-06-23"
    assert evaluation_row["label_available_date"] == "2026-07-21"
    assert evaluation_row["window_days"] == 20
    assert evaluation_row["late_delivery"] is False
    assert evaluation_row["prediction_decision_at"] == saved_capture.scope.decision_at
    assert evaluation_row["delivery_at"] == delivered_at
    assert evaluation_row["human_decision_at"] == delivered_at

    # The same real producer can run an older cutoff only in the explicit
    # historical tier.  This keeps an old caller-selected cutoff from being
    # relabeled natural merely because runtime clocks are current.
    historical_service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=lambda: market_frame.copy(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )
    setattr(
        historical_service.strategy_configurator,
        "generate_recommendations",
        service.strategy_configurator.generate_recommendations,
    )
    historical_recommendations = historical_service.run_recommendation(
        {"recommendation_ranking": {"threshold_mode": "fixed"}},
        max_stocks=1,
        top_n=1,
        as_of_date="2026-06-20",
        universe=["AAA"],
        historical_research=True,
        select_latest_available_cutoff=False,
    )
    assert len(historical_recommendations) == 1
    assert historical_service.last_run_context["as_of_date"] == "2026-06-20"
    assert historical_service.last_run_context["temporal_mode"] == (
        "historical_research_not_as_if_available"
    )
    assert historical_service.last_run_context["cutoff_selection"] == (
        "explicit_historical_cutoff"
    )
    assert historical_service.last_run_context["cutoff_policy"] == (
        "explicit_historical_research"
    )


def test_active_training_label_contract_missing_or_mismatched_fails_closed(
    tmp_path: Path,
) -> None:
    from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer
    from ml_module.recommendation_calibration_authority import RecommendationCalibrationPromotionAuthority
    from test_daily_recommendation_learning_loop import (
        FEATURE_REGISTRY_HASH,
        FEATURE_SCHEMA,
        _natural_receipt,
    )

    trained_result, candidate_root, candidate_metadata = _verified_candidate(
        tmp_path,
        candidate_day="2026-06-01",
        training_as_of="2026-05-31",
    )
    natural_evidence = _natural_receipt(
        tmp_path,
        root=candidate_root,
        candidate_day="2026-06-01",
        evaluation_day="2026-06-22",
    )
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    decision = authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=trained_result.candidate_id,
        candidate_root=candidate_root,
        candidate_metadata=candidate_metadata,
        natural_evidence=natural_evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert decision.decision == "adopt"

    consumer = RecommendationCalibrationConsumer(
        pointer_path=authority.pointer_path,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "formal-data",
    )
    assert consumer.reload(decision_date="2026-06-22") == "active"
    original_training_provenance = dict(consumer._training_provenance)
    for field_name, bad_value in (
        ("label_registry_hash", "sha256:" + "0" * 64),
        ("label_contract_id", "tampered-label-contract"),
        ("return_basis", "tampered-return-basis"),
    ):
        consumer._training_provenance = {
            **original_training_provenance,
            field_name: bad_value,
        }
        projection = consumer.project(
            stock_code="AAA",
            feature_values=(1000, 2000),
            rule_probability_bp=5_000,
            decision_date="2026-06-22",
        )
        assert projection.status == "rule_only"
        assert projection.warnings == (
            "active_training_label_contract_unavailable_fail_closed",
        )


def test_active_training_label_contract_missing_from_provenance_fails_closed(
    tmp_path: Path,
) -> None:
    from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer
    from ml_module.recommendation_calibration_authority import RecommendationCalibrationPromotionAuthority
    from test_daily_recommendation_learning_loop import (
        FEATURE_REGISTRY_HASH,
        FEATURE_SCHEMA,
        _natural_receipt,
    )

    trained_result, candidate_root, candidate_metadata = _verified_candidate(
        tmp_path,
        candidate_day="2026-06-01",
        training_as_of="2026-05-31",
    )
    natural_evidence = _natural_receipt(
        tmp_path,
        root=candidate_root,
        candidate_day="2026-06-01",
        evaluation_day="2026-06-22",
    )
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    decision = authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=trained_result.candidate_id,
        candidate_root=candidate_root,
        candidate_metadata=candidate_metadata,
        natural_evidence=natural_evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert decision.decision == "adopt"
    consumer = RecommendationCalibrationConsumer(
        pointer_path=authority.pointer_path,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "formal-data",
    )
    assert consumer.reload(decision_date="2026-06-22") == "active"
    consumer._training_provenance = {
        key: value
        for key, value in consumer._training_provenance.items()
        if key != "return_basis"
    }
    projection = consumer.project(
        stock_code="AAA",
        feature_values=(1000, 2000),
        rule_probability_bp=5_000,
        decision_date="2026-06-22",
    )
    assert projection.status == "rule_only"
    assert projection.warnings == (
        "active_training_label_contract_unavailable_fail_closed",
    )


def test_real_consumer_rejects_future_research_candidate_context(
    tmp_path: Path,
) -> None:
    """A valid active candidate becomes rule-only when its context is future research."""

    from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer
    from ml_module.recommendation_calibration_authority import RecommendationCalibrationPromotionAuthority
    from test_daily_recommendation_learning_loop import (
        FEATURE_REGISTRY_HASH,
        FEATURE_SCHEMA,
        _candidate,
        _natural_receipt,
    )

    trained_result, candidate_root, _candidate_metadata = _candidate(
        tmp_path,
        shift=0,
        candidate_day="2026-06-01",
    )
    natural_evidence = _natural_receipt(
        tmp_path,
        root=candidate_root,
        candidate_day="2026-06-01",
        evaluation_day="2026-06-22",
    )
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    decision = authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=trained_result.candidate_id,
        candidate_root=candidate_root,
        candidate_metadata=json.loads(
            (candidate_root / "candidate.json").read_text(encoding="utf-8")
        ),
        natural_evidence=natural_evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert decision.decision == "adopt"

    consumer = RecommendationCalibrationConsumer(
        pointer_path=tmp_path / "authority" / "recommendation-calibration-active-pointer.json",
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "formal-data",
    )
    assert consumer.reload(decision_date="2026-06-22") == "active"

    candidate_path = candidate_root / "candidate.json"
    candidate_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate_payload.update(
        {
            "training_cutoff": "2026-12-31",
            "training_semantics": "historical_research_only",
            "decision_time_eligible": False,
            "research_only": True,
        }
    )
    candidate_path.write_text(
        json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    assert consumer.reload(decision_date="2026-06-22") == "rule_only"
    projection = consumer.project(
        stock_code="AAA",
        feature_values=(100, 200),
        rule_probability_bp=5_000,
        decision_date="2026-06-22",
    )
    assert projection.status == "rule_only"
    assert projection.warnings == ("candidate_training_cutoff_after_decision",)


def test_real_consumer_independent_after_cost_baseline_reaches_advice_presentation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Use a real trained artifact to prove the independent after-cost lane."""

    from app_module.advice_composer import AdviceComposer
    from app_module.advice_dtos import AdviceMode
    from app_module.advice_policy import AdvicePolicy
    from app_module.decision_presentation import (
        DecisionPresentationService,
        format_decision_lineage_detail,
    )
    from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer
    from ml_module.historical_feature_builder import HistoricalFeatureBuilder
    from ml_module.recommendation_calibration_authority import RecommendationCalibrationPromotionAuthority
    from ml_module.recommendation_calibration_training import (
        RecommendationCalibrationTrainingConfig,
        RecommendationCalibrationTrainingService,
    )
    from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
    from ml_module.recommendation_probability_transform import (
        AFTER_COST_NULL_BENCHMARK_BASELINE_ID,
        AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP,
    )
    from ml_module.recommendation_training_lineage import (
        build_recommendation_training_lineage,
        persist_recommendation_training_lineage,
        recommendation_training_dataset_hash,
    )
    from test_daily_recommendation_learning_loop import (
        FEATURE_REGISTRY_HASH,
        FEATURE_SCHEMA,
        _natural_receipt,
        _samples,
    )

    # The source rows are real training-service inputs; clearing the explicit
    # rule value makes RecommendationCalibrationSample apply its existing
    # independent-null contract instead of the declared-baseline compatibility
    # path.  Everything remains under tmp_path and read-only to formal data.
    samples = tuple(
        replace(
            sample,
            rule_after_cost_probability_bp=None,
            rule_after_cost_baseline_id=None,
        )
        for sample in _samples(0)
    )
    dataset_hash = recommendation_training_dataset_hash(samples)
    trained_result = RecommendationCalibrationTrainingService().fit(
        dataset_id="dataset-independent-after-cost",
        dataset_hash=dataset_hash,
        samples=samples,
        feature_names=("momentum_bp", "volume_ratio_bp"),
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        training_as_of="2026-05-31",
        fixed_round_trip_cost_bp=50,
        dataset_quality={"formal_candidate_eligible": True},
        created_at="2026-06-01T00:00:00+00:00",
        config=RecommendationCalibrationTrainingConfig(
            minimum_calibration_samples=10,
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )
    candidate_root = tmp_path / "candidate-independent-after-cost"
    trained_result.persist(candidate_root)
    candidate_metadata = json.loads((candidate_root / "candidate.json").read_text(encoding="utf-8"))
    assert candidate_metadata["after_cost_baseline_id"] == AFTER_COST_NULL_BENCHMARK_BASELINE_ID
    assert candidate_metadata["after_cost_baseline_probability_bp"] == AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP
    training_config = RecommendationCalibrationTrainingConfig(
        minimum_calibration_samples=10,
        minimum_train_dates=30,
        test_date_count=5,
        purge_trading_days=20,
    )
    lineage = build_recommendation_training_lineage(
        learning_root=tmp_path / "learning",
        run_id="daily-recommendation-learning:independent-after-cost:verified",
        run_scope="integration",
        decision_date="2026-06-01",
        training_as_of="2026-05-31",
        dataset_id="dataset-independent-after-cost",
        dataset_hash=dataset_hash,
        samples=samples,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        dataset_quality={"formal_candidate_eligible": True},
        training_result=trained_result,
        training_config=training_config,
        candidate_id=trained_result.candidate_id,
        candidate_manifest_hash=trained_result.manifest.manifest_hash,
        candidate_artifact_hash=trained_result.artifact_hash,
        source_groups={"replay": samples},
    )
    lineage_path = persist_recommendation_training_lineage(tmp_path / "learning", lineage)
    candidate_metadata.update(
        {
            "training_lineage_manifest_hash": lineage.manifest_hash,
            "training_lineage_manifest_path": str(lineage_path),
            "training_source_hash": lineage.payload["training_source_hash"],
            "training_pit_hash": lineage.payload["training_pit_hash"],
            "feature_transform_contract": lineage.payload["feature_transform_contract"],
            "feature_transform_contract_hash": lineage.payload["feature_transform_contract"][
                "contract_hash"
            ],
        }
    )
    (candidate_root / "candidate.json").write_text(
        json.dumps(candidate_metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    natural_evidence = _natural_receipt(
        tmp_path,
        root=candidate_root,
        candidate_day="2026-06-01",
        evaluation_day="2026-06-22",
    )
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "independent-authority")
    decision = authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=trained_result.candidate_id,
        candidate_root=candidate_root,
        candidate_metadata=candidate_metadata,
        natural_evidence=natural_evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert decision.decision == "adopt"

    consumer = RecommendationCalibrationConsumer(
        pointer_path=tmp_path / "independent-authority" / "recommendation-calibration-active-pointer.json",
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "formal-data",
    )
    assert consumer.active_after_cost_baseline(decision_date="2026-06-22") == (
        AFTER_COST_NULL_BENCHMARK_BASELINE_ID,
        AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP,
    )

    database = tmp_path / "source.db"
    _make_database(database, start=date(2026, 1, 1))
    monkeypatch.setattr(
        HistoricalFeatureBuilder,
        "compute",
        lambda _self, _snapshot, *, industry_index_name_by_symbol: (
            SimpleNamespace(
                symbol="AAA",
                values=(("momentum_bp", 1000), ("volume_ratio_bp", 2000)),
            ),
        ),
    )
    service = RecommendationService(
        SimpleNamespace(
            db_file=database,
            default_start_date="2026-01-01",
            output_root=tmp_path / "output",
            data_root=tmp_path / "formal-data",
        ),
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )
    recommendation = _recommendation()
    service._apply_recommendation_calibration([recommendation], decision_date="2026-06-22")
    projection = service.last_calibration_projections["AAA"]
    assert projection.status == "active_candidate", projection.warnings
    assert projection.after_cost_profit_probability_bp is not None
    model_prediction = consumer._model.predict((1000, 2000))
    assert projection.raw_after_cost_profit_probability_bp == (
        model_prediction.after_cost_profit_probability_bp
    )
    assert projection.after_cost_profit_probability_bp != AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP
    assert "after_cost_baseline:after_cost_null_benchmark_50pct_v1" in projection.source_trace
    assert "after_cost_baseline_contract:independent_null_benchmark_v1" in projection.source_trace
    assert service.last_run_context["calibration_after_cost_baseline_id"] == (
        AFTER_COST_NULL_BENCHMARK_BASELINE_ID
    )

    invalid_null_value = consumer.project(
        stock_code="AAA",
        feature_values=(1000, 2000),
        rule_probability_bp=5_000,
        after_cost_rule_probability_bp=5_001,
        after_cost_rule_baseline_id=AFTER_COST_NULL_BENCHMARK_BASELINE_ID,
        decision_date="2026-06-22",
    )
    assert invalid_null_value.status == "rule_only"
    assert invalid_null_value.warnings == (
        "after_cost_null_benchmark_probability_invalid_fail_closed",
    )

    advice_result = RecommendationResultDTO(
        result_id="rec-independent-after-cost-20260622",
        result_name="independent after-cost recommendation",
        config={
            "strategy_status": "promoted",
            "parameters_locked": True,
            "disclosure_complete": True,
            "execution_feasible": True,
            "risk_budget_available": True,
        },
        recommendations=[recommendation],
    )
    advice_dashboard = AdviceComposer(AdvicePolicy()).compose(
        recommendations=advice_result,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date="2026-06-22",
        data_as_of_date="2026-06-21",
        mode=AdviceMode.GUIDED,
    )
    advice = advice_dashboard.recommendations[0]
    assert advice.after_cost_profit_probability_bp == projection.after_cost_profit_probability_bp
    presentation = DecisionPresentationService().from_recommendation_advice(advice)
    assert presentation.after_cost_profit_probability_bp == projection.after_cost_profit_probability_bp
    lineage_detail = format_decision_lineage_detail(presentation)
    assert "after_cost_baseline:after_cost_null_benchmark_50pct_v1" in lineage_detail
    assert "after_cost_baseline_probability_bp:5000" in lineage_detail


def test_default_recommendation_service_has_read_only_consumer_from_dedicated_shadow_pointer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("RECOMMENDATION_LEARNING_OUTPUT_ROOT", raising=False)
    config = SimpleNamespace(
        output_root=tmp_path / "output",
        data_root=tmp_path / "formal-data",
    )
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
    )

    assert service.calibration_consumer is not None
    assert service.calibration_consumer.pointer_path == (
        (tmp_path / "FA_Data_Shadow" / "recommendation_learning" / "recommendation-calibration-active-pointer.json").resolve()
    )
