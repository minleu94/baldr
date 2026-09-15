from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation_calibration_consumer import RecommendationCalibrationProjection
from app_module.recommendation_service import RecommendationService


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
    """Exercise a minimal real pointer/artifact consumer through the same UI path."""

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
        _candidate,
        _natural_receipt,
    )
    from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView

    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)

    trained_result, candidate_root, candidate_metadata = _candidate(
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

    database = tmp_path / "source.db"
    _make_database(database, start=date(2026, 1, 1))
    # The minimal fixture intentionally has the consumer's two-feature schema;
    # the production adapter and UI are still exercised with a bounded feature
    # source, without creating a formal data artifact.
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
    assert "自然前瞻驗證" not in rendered
    view.close()


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
    from ml_module.recommendation_probability_transform import (
        AFTER_COST_NULL_BENCHMARK_BASELINE_ID,
        AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP,
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
    trained_result = RecommendationCalibrationTrainingService().fit(
        dataset_id="dataset-independent-after-cost",
        dataset_hash="sha256:" + "c" * 64,
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
