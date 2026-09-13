from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

from app_module.dtos import RecommendationDTO
from app_module.recommendation_calibration_consumer import RecommendationCalibrationProjection
from app_module.recommendation_service import RecommendationService


def _make_database(path: Path, *, days: int = 90) -> None:
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
    start = date(2014, 1, 1)
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
                source_trace=("candidate:candidate-model-1", "dataset:dataset-1"),
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
    assert recommendation.calibrated_probability_bp == 5_800
    assert recommendation.after_cost_profit_probability_bp == 5_700
    assert recommendation.sample_size == 120
    assert recommendation.calibration_model_version == "candidate-model-1"
    assert recommendation.calibration_dataset_version == "dataset-1"
    assert recommendation.calibration_status == "active_candidate"
    assert recommendation.calibration_source_trace == [
        "candidate:candidate-model-1",
        "dataset:dataset-1",
    ]
    assert service.last_run_context["calibration_projection_status"] == "active_candidate"


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
