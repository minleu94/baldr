"""以隔離合成資料驗證個人模型從訓練到保存捕獲的完整路徑。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app_module.recommendation import execute as execute_module
from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.personal_prediction_capture import (
    PersonalPredictionCaptureError,
    capture_personal_saved_result,
)
from app_module.recommendation.personal_candidate_inventory import (
    inspect_personal_calibration_candidate,
    inspect_personal_source_time_binding,
)
from app_module.recommendation.personal_use_policy import (
    PERSONAL_CALIBRATED_PROBABILITY_MODE,
    RULE_ONLY_MODE,
    PersonalCalibrationCandidateV1,
    RecommendationPersonalUseSelectionV2,
    RecommendationPersonalUseSelectionV1,
    save_personal_use_policy,
    save_personal_use_policy_v2,
)
from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationConsumer,
    _library_versions,
)
from app_module.recommendation_market_data_provider import (
    DefaultRecommendationMarketDataProvider,
)
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.model_artifact_loader import (
    ArtifactCompatibilityExpectation,
    SafeShadowModelArtifactLoader,
)
from ml_module.recommendation_calibration_learning_runner import (
    DailyRecommendationLearningRunner,
)
from ml_module.recommendation_calibration_training import (
    InvalidCalibrationOutputError,
    RecommendationCalibrationSample,
    RecommendationCalibrationTrainingConfig,
    recommendation_label_registry_hash,
)
from ml_module.probability_calibration import FittedShadowProbabilityCalibrator
from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
from ml_module.recommendation_historical_replay import (
    RecommendationHistoricalReplayConfig,
    RecommendationHistoricalReplayService,
    _read_source_content_snapshot,
)
from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
from ml_module.recommendation_training_lineage import (
    read_recommendation_training_lineage,
)
from recommendation_test_support import build_recommendation_test_service


_TAIPEI = ZoneInfo("Asia/Taipei")
_SYMBOL = "AAA"


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _aware_utc(value: object) -> datetime:
    assert type(value) is str
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None and parsed.utcoffset() is not None
    return parsed.astimezone(timezone.utc)


def _synthetic_samples(
    *, decision_day: date, feature_count: int
) -> tuple[RecommendationCalibrationSample, ...]:
    """建立明示合成、逐列符合 PIT 的固定成本訓練資料。"""

    first_day = decision_day - timedelta(days=170)
    rows: list[RecommendationCalibrationSample] = []
    for day_index in range(100):
        sample_day = first_day + timedelta(days=day_index)
        for symbol_index, symbol in enumerate(("AAA", "BBB")):
            momentum = ((day_index % 13) - 6) * 500 + symbol_index * 175
            feature_values = (
                momentum,
                4_000 + (day_index % 9) * 350 + symbol_index * 125,
                *tuple(
                    ((day_index + 3) * (feature_index + 5) % 4_001) - 2_000
                    for feature_index in range(2, feature_count)
                ),
            )
            rows.append(
                RecommendationCalibrationSample.from_forward_return(
                    row_id=f"synthetic-full-stack:{sample_day.isoformat()}:{symbol}",
                    symbol=symbol,
                    decision_date=sample_day.isoformat(),
                    feature_as_of_date=(sample_day - timedelta(days=1)).isoformat(),
                    feature_available_date=(sample_day - timedelta(days=1)).isoformat(),
                    label_end_date=(sample_day + timedelta(days=20)).isoformat(),
                    label_available_date=(sample_day + timedelta(days=20)).isoformat(),
                    feature_values=feature_values,
                    stock_return_bp=momentum + ((day_index % 5) - 2) * 180,
                    benchmark_return_bp=100,
                    fixed_round_trip_cost_bp=50,
                    observed_liquidity_cost_bp=20,
                    rule_probability_bp=5_000,
                    rule_after_cost_probability_bp=5_000,
                    source_quality="synthetic_test_fixture",
                )
            )
    assert rows
    return tuple(rows)


def _write_synthetic_source_database(
    database_path: Path, *, first_day: date, days: int
) -> None:
    """只在 pytest tmp_path 建立四表歷史來源，供真唯讀 feature provider 使用。"""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
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
            current = first_day + timedelta(days=offset)
            compact_day = current.strftime("%Y%m%d")
            close = Decimal(80 + offset) + Decimal(offset % 7) / Decimal(10)
            volume = 100_000 + offset * 25
            connection.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    compact_day,
                    _SYMBOL,
                    volume,
                    int(close * volume),
                    str(close - Decimal("0.50")),
                    str(close + Decimal("1.00")),
                    str(close - Decimal("1.00")),
                    str(close),
                ),
            )
            connection.execute(
                "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)",
                (compact_day, _SYMBOL, str(45 + offset % 21), str(offset % 9), "22"),
            )
            market_close = Decimal(10_000 + offset)
            connection.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?)",
                (compact_day, str(market_close), str(market_close)),
            )
        connection.commit()
    finally:
        connection.close()


class _SyntheticMarketProvider(DefaultRecommendationMarketDataProvider):
    def __init__(self, config: Any, frame: pd.DataFrame) -> None:
        super().__init__(config)
        self._frame = frame
        self.calls = 0

    def __call__(self) -> pd.DataFrame:
        self.calls += 1
        return self._frame.copy(deep=True)


class _SyntheticIndustryMapper:
    def __init__(self) -> None:
        self.companies_df = pd.DataFrame()

    def filter_stocks_by_industry(
        self, stock_codes: list[str], _industry: str
    ) -> list[str]:
        return stock_codes

    def get_all_industries(self) -> list[str]:
        return []

    def get_stock_industries(self, _stock_code: str) -> list[str]:
        return []

    def get_industry_performance(
        self, _industry: str, *, date: str
    ) -> None:
        del date
        return None


def _market_frame(*, first_day: date, days: int, future_day: date) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for offset in range(days):
        current = first_day + timedelta(days=offset)
        close = Decimal(80 + offset) + Decimal(offset % 7) / Decimal(10)
        rows.append(
            {
                "日期": current,
                "available_date": current,
                "證券代號": _SYMBOL,
                "證券名稱": "合成測試標的",
                "收盤價": close,
                "成交股數": 100_000 + offset * 25,
            }
        )
    rows.append(
        {
            "日期": future_day,
            "available_date": future_day,
            "證券代號": _SYMBOL,
            "證券名稱": "未來列不得參與推薦",
            "收盤價": Decimal("999999.00"),
            "成交股數": 1,
        }
    )
    return pd.DataFrame(rows)


def _make_service(
    *,
    config: Any,
    market_provider: _SyntheticMarketProvider,
    consumer: RecommendationCalibrationConsumer,
    scored_dates: list[str],
):
    service = build_recommendation_test_service(
        config,
        industry_mapper=_SyntheticIndustryMapper(),
        market_data_provider=market_provider,
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.return_value = []
    service.reason_engine.format_reason_text.return_value = "隔離合成模型測試"

    def generate_recommendations(
        stock_frame: pd.DataFrame, _runtime_config: dict[str, Any]
    ) -> pd.DataFrame:
        latest = pd.Timestamp(stock_frame["日期"].max()).date()
        scored_dates.append(latest.isoformat())
        return pd.DataFrame(
            {
                "FinalScore": [Decimal("91.50")],
                "TotalScore": [Decimal("91.50")],
                "IndicatorScore": [Decimal("31.25")],
                "PatternScore": [Decimal("27.50")],
                "VolumeScore": [Decimal("18.00")],
                "收盤價": [stock_frame.iloc[-1]["收盤價"]],
                "成交股數": [stock_frame.iloc[-1]["成交股數"]],
            }
        )

    service.strategy_configurator.generate_recommendations = generate_recommendations
    return service


def _write_user_declared_replay_source(
    database_path: Path,
    *,
    first_day: date,
    days: int,
    symbols: tuple[str, ...] = ("AAA", "BBB"),
) -> None:
    """建立只供隔離 user-declared replay 使用、非官方 PIT 的可重播 SQLite。"""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL, 證券代號 TEXT NOT NULL, 成交股數 INTEGER,
                成交金額 INTEGER, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, 收盤價 TEXT
            );
            CREATE TABLE technical_indicators (
                日期 TEXT NOT NULL, 證券代號 TEXT NOT NULL,
                RSI TEXT, MACD TEXT, ADX TEXT, available_at TEXT NOT NULL
            );
            CREATE TABLE market_indices (日期 TEXT NOT NULL, 收盤指數 TEXT, 收盤價 TEXT);
            CREATE TABLE industry_indices (日期 TEXT NOT NULL, 指數名稱 TEXT, 收盤指數 TEXT);
            CREATE TABLE corporate_action_adjustments (
                symbol TEXT NOT NULL, event_date TEXT NOT NULL, available_at TEXT NOT NULL,
                effective_from TEXT NOT NULL, adjustment_factor TEXT NOT NULL
            );
            CREATE TABLE recommendation_source_contract (
                component TEXT PRIMARY KEY, source_id TEXT NOT NULL, source_table TEXT NOT NULL,
                status TEXT NOT NULL, coverage_start TEXT NOT NULL, coverage_end TEXT NOT NULL,
                available_at TEXT NOT NULL, evidence_hash TEXT NOT NULL,
                source_columns_json TEXT NOT NULL, publication_time_verified INTEGER NOT NULL,
                corporate_action_adjustment_verified INTEGER NOT NULL
            );
            """
        )
        last_day = first_day + timedelta(days=days - 1)
        for offset in range(days):
            current = first_day + timedelta(days=offset)
            compact_day = current.strftime("%Y%m%d")
            # 固定三日合成週期使 purged OOF 視窗同時包含兩類；
            # 此資料只驗工程路徑，不代表任何市場效果。
            base_close = (100, 102, 101)[offset % 3]
            connection.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?)",
                (compact_day, str(10_000 + offset), str(10_000 + offset)),
            )
            for symbol_index, symbol in enumerate(symbols):
                close = Decimal(base_close + symbol_index * 25)
                volume = 100_000 + offset * 25 + symbol_index * 1_000
                connection.execute(
                    "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        compact_day,
                        symbol,
                        volume,
                        int(close * volume),
                        str(close - Decimal("0.50")),
                        str(close + Decimal("1.00")),
                        str(close - Decimal("1.00")),
                        str(close),
                    ),
                )
                connection.execute(
                    "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        compact_day,
                        symbol,
                        str(35 + ((offset * 7 + symbol_index * 11) % 31)),
                        str((offset % 17) - 8),
                        str(15 + (offset % 18)),
                        compact_day,
                    ),
                )
        for symbol in symbols:
            connection.execute(
                "INSERT INTO corporate_action_adjustments VALUES (?, ?, ?, ?, ?)",
                (
                    symbol,
                    first_day.isoformat(),
                    first_day.isoformat(),
                    first_day.isoformat(),
                    "1",
                ),
            )
        connection.commit()

        technical = _read_source_content_snapshot(
            database_path,
            component="technical",
            source_table="technical_indicators",
            symbols=symbols,
            history_start=first_day,
            replay_end=last_day,
        )
        corporate = _read_source_content_snapshot(
            database_path,
            component="corporate_actions",
            source_table="corporate_action_adjustments",
            symbols=symbols,
            history_start=first_day,
            replay_end=last_day,
        )
        connection.executemany(
            "INSERT INTO recommendation_source_contract VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    "technical",
                    "twse.mi_index.daily_price+tpex.daily_close_quotes",
                    "technical_indicators",
                    "accepted",
                    first_day.isoformat(),
                    last_day.isoformat(),
                    first_day.isoformat(),
                    technical["digest"],
                    json.dumps(
                        ["日期", "證券代號", "RSI", "MACD", "ADX", "available_at"]
                    ),
                    1,
                    0,
                ),
                (
                    "corporate_actions",
                    "official_market_event_publication",
                    "corporate_action_adjustments",
                    "accepted",
                    first_day.isoformat(),
                    last_day.isoformat(),
                    first_day.isoformat(),
                    corporate["digest"],
                    json.dumps(
                        [
                            "symbol",
                            "event_date",
                            "available_at",
                            "effective_from",
                            "adjustment_factor",
                        ]
                    ),
                    0,
                    1,
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_personal_full_stack(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """證明自述 synthetic-only 候選不會啟用，canonical save/readback 仍保真。"""

    registry = CORE_LONG_HISTORY_FEATURE_REGISTRY
    decision_day = datetime.now(_TAIPEI).date()
    samples = _synthetic_samples(
        decision_day=decision_day,
        feature_count=len(registry.canonical_schema),
    )
    training_as_of = max(date.fromisoformat(row.label_available_date) for row in samples)
    assert training_as_of <= decision_day
    assert all(
        date.fromisoformat(row.feature_as_of_date) < date.fromisoformat(row.decision_date)
        and date.fromisoformat(row.feature_available_date)
        <= date.fromisoformat(row.decision_date)
        and date.fromisoformat(row.label_end_date)
        >= date.fromisoformat(row.decision_date)
        and date.fromisoformat(row.label_available_date)
        <= training_as_of
        for row in samples
    )

    learning_output_root = tmp_path
    model_data_root = tmp_path / "m"
    runner = DailyRecommendationLearningRunner(
        output_root=learning_output_root,
        data_root=model_data_root,
        feature_names=registry.canonical_ids,
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        training_config=RecommendationCalibrationTrainingConfig(
            minimum_calibration_samples=10,
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )
    dataset_quality = {
        "training_data_eligible": True,
        "forward_evidence_eligible": False,
        "formal_candidate_eligible": False,
        "candidate_blockers": ["synthetic_test_data_not_formal_source"],
        "source_contract": {
            "contract_id": "synthetic-personal-model-full-stack",
            "contract_version": "v1",
            "source_kind": "synthetic_test_fixture",
            "status": "synthetic_only",
            "pit_eligible": False,
        },
    }
    learning_started_at = datetime.now(timezone.utc)
    training_result = runner.run(
        decision_date=decision_day.isoformat(),
        run_scope="x",
        samples=samples,
        natural_evidence=None,
        data_dependency_status="ready",
        outcome_dependency_status="not_checked",
        dataset_quality=dataset_quality,
        training_as_of=training_as_of.isoformat(),
        lineage_sources={"synthetic_fixture": samples},
    )
    learning_finished_at = datetime.now(timezone.utc)

    assert training_result.status == "completed", training_result.reason
    assert training_result.candidate_id
    assert training_result.candidate_root
    assert training_result.training_lineage_status == "verified"
    assert training_result.training_lineage_manifest_hash
    assert training_result.training_lineage_manifest_path
    assert training_result.decision != "adopt"

    candidate_root = Path(training_result.candidate_root)
    candidate_json_path = candidate_root / "candidate.json"
    manifest_path = candidate_root / "manifest.json"
    run_receipt_path = Path(training_result.receipt_path)
    candidate_bytes = candidate_json_path.read_bytes()
    candidate_metadata = json.loads(candidate_bytes)
    candidate_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_receipt = json.loads(run_receipt_path.read_text(encoding="utf-8"))
    assert candidate_metadata["candidate_id"] == training_result.candidate_id
    assert candidate_metadata["formal_candidate_eligible"] is False
    assert candidate_metadata["production_action_allowed"] is False
    assert "candidate_available_at" not in candidate_metadata
    assert run_receipt["candidate_available_at"]
    candidate_frozen_at = _aware_utc(candidate_metadata["candidate_frozen_at"])
    candidate_available_at = _aware_utc(run_receipt["candidate_available_at"])
    assert candidate_frozen_at <= candidate_available_at
    assert learning_started_at <= candidate_available_at <= learning_finished_at

    lineage = read_recommendation_training_lineage(
        Path(training_result.training_lineage_manifest_path),
        expected_manifest_hash=training_result.training_lineage_manifest_hash,
        expected_dataset_hash=training_result.dataset_hash,
        expected_candidate_id=training_result.candidate_id,
    )
    assert lineage.payload["training_context"]["decision_time_eligible"] is True
    assert lineage.payload["pit"]["feature_as_of_before_decision"] is True
    assert lineage.payload["pit"]["feature_available_not_after_decision"] is True
    assert lineage.payload["pit"]["label_available_dates_not_after_training_as_of"] is True
    assert lineage.payload["dataset_quality"]["formal_candidate_eligible"] is False

    expected = ArtifactCompatibilityExpectation(
        expected_model_family=str(candidate_manifest["model_family"]),
        expected_feature_registry_hash=registry.registry_hash,
        expected_label_registry_hash=recommendation_label_registry_hash(),
        expected_feature_schema=registry.canonical_schema,
        installed_library_versions=_library_versions(),
    )
    loaded = SafeShadowModelArtifactLoader(data_root=model_data_root).load(
        candidate_root,
        expectation=expected,
    )
    assert loaded.status == "shadow_model_ready"
    assert loaded.model is not None
    assert str(getattr(loaded.model, "model_id", "")) == training_result.candidate_id

    personal_candidate = PersonalCalibrationCandidateV1(
        candidate_id=training_result.candidate_id,
        candidate_root=str(candidate_root.resolve()),
        candidate_json_sha256=_sha256(candidate_bytes),
        candidate_manifest_hash=str(candidate_metadata["manifest_hash"]),
        candidate_artifact_hash=str(candidate_metadata["artifact_hash"]),
        candidate_freeze_hash=str(candidate_metadata["candidate_freeze_hash"]),
        dataset_hash=str(candidate_metadata["dataset_hash"]),
    )
    personal_root = tmp_path / "p"
    policy_path = personal_root / "u.json"
    capture_root = tmp_path / "c"
    policy = save_personal_use_policy(
        policy_path,
        RecommendationPersonalUseSelectionV1(
            scope_id="synthetic-full-stack-user",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            candidate=personal_candidate,
        ),
        expected_revision=0,
    )
    assert type(policy.candidate) is PersonalCalibrationCandidateV1
    assert policy.candidate.candidate_id == training_result.candidate_id
    assert policy.confirmed_at is not None
    policy_confirmed_at = _aware_utc(policy.confirmed_at)
    assert candidate_available_at <= policy_confirmed_at

    source_start = decision_day - timedelta(days=100)
    source_days = 100
    source_database = tmp_path / "s" / "d"
    _write_synthetic_source_database(
        source_database,
        first_day=source_start,
        days=source_days,
    )
    market_data = _market_frame(
        first_day=source_start,
        days=source_days,
        future_day=decision_day + timedelta(days=3_650),
    )
    recommendation_output_root = tmp_path / "r"

    class _SyntheticConfig(SimpleNamespace):
        def resolve_output_path(self, subfolder: str) -> Path:
            return Path(self.output_root) / subfolder

    config = _SyntheticConfig(
        db_file=source_database,
        default_start_date=source_start.isoformat(),
        output_root=recommendation_output_root,
        data_root=model_data_root,
        use_sqlite=False,
        pit_market_scope="twse_listed",
    )
    config.resolve_output_path = lambda subfolder: recommendation_output_root / subfolder
    global_pointer = tmp_path / "g.json"
    base_consumer = RecommendationCalibrationConsumer(
        pointer_path=global_pointer,
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
        data_root=model_data_root,
    )
    provider = _SyntheticMarketProvider(config, market_data)
    scored_dates: list[str] = []
    base_service = _make_service(
        config=config,
        market_provider=provider,
        consumer=base_consumer,
        scored_dates=scored_dates,
    )
    personal_service = base_service.with_personal_use_policy(policy)

    execution_started_at = datetime.now(timezone.utc)
    execution = execute_module.execute_recommendation(
        personal_service,
        {
            "profile_id": "synthetic-personal-full-stack",
            "profile_version": "1",
            "recommendation_ranking": {"threshold_mode": "fixed"},
            "filters": {"industry": "全部"},
        },
        max_stocks=1,
        top_n=1,
        result_id=f"synthetic-personal-full-stack-{decision_day.isoformat()}",
    )
    execution_finished_at = datetime.now(timezone.utc)

    assert execution.status.value == "completed"
    assert execution.decision is not None
    assert tuple(item.stock_code for item in execution.decision.items) == (_SYMBOL,)
    assert provider.calls == 1
    assert scored_dates and all(
        date.fromisoformat(item) < execution.request.as_of_date for item in scored_dates
    )
    assert execution.context.as_of_date == execution.request.as_of_date
    assert execution.context.decision_at is not None
    decision_at = execution.context.decision_at.astimezone(timezone.utc)
    assert execution_started_at <= decision_at <= execution_finished_at
    assert policy_confirmed_at <= decision_at

    policy_event = next(
        event
        for event in execution.events
        if event.event_type == "personal_use_policy_snapshot"
    )
    assert policy_event.details["requested_mode"] == PERSONAL_CALIBRATED_PROBABILITY_MODE
    assert policy_event.details["effective_mode"] == RULE_ONLY_MODE
    assert "synthetic" in str(dataset_quality["source_contract"]["source_kind"])
    assert "synthetic" in str(dataset_quality["source_contract"]["status"])
    assert not any(
        event.event_type == "ml_projection_receipt_capture"
        for event in execution.events
    )
    assert not any(
        event.event_type == "personal_probability_baseline_snapshot"
        for event in execution.events
    )
    assert execution.ml_projection_refs == ()
    assert execution.ml_receipt_refs == ()
    assert not (model_data_root / "recommendation_learning" / "inference_projection").exists()

    composition = build_recommendation_composition(config)
    save_receipt = composition.save_service.save_execution(execution)
    assert save_receipt.result_id == execution.result_id
    fresh_composition = build_recommendation_composition(config)
    readback = fresh_composition.queries.get(execution.result_id)
    assert readback is not None
    assert readback.execution == execution
    assert readback.integrity_basis == "canonical_payload_and_index_verified"
    assert readback.ml_read_status != "verified"
    assert readback.ml_projection_rows == ()
    assert not global_pointer.exists()
    with pytest.raises(PersonalPredictionCaptureError):
        capture_personal_saved_result(
            execution.result_id,
            fresh_composition.queries,
            capture_root,
        )
    assert not capture_root.exists()

    # 在第二個隔離 package 中翻轉一個 artifact byte；原正例候選/政策/收據
    # 均保持不變，fresh personal consumer 必須退回 rule-only 且不產模型收據。
    tampered_root = tmp_path / "t"
    shutil.copytree(candidate_root, tampered_root)
    artifact_filename = str(candidate_manifest["artifact_filename"])
    tampered_artifact = tampered_root / artifact_filename
    original_artifact_bytes = tampered_artifact.read_bytes()
    assert original_artifact_bytes
    changed_last_byte = bytes((original_artifact_bytes[-1] ^ 1,))
    tampered_artifact.write_bytes(original_artifact_bytes[:-1] + changed_last_byte)
    assert candidate_json_path.read_bytes() == candidate_bytes

    bad_loaded = SafeShadowModelArtifactLoader(data_root=model_data_root).load(
        tampered_root,
        expectation=expected,
    )
    assert bad_loaded.status != "shadow_model_ready"
    assert bad_loaded.model is None

    tampered_policy_path = tmp_path / "b" / "u.json"
    tampered_candidate = PersonalCalibrationCandidateV1(
        candidate_id=training_result.candidate_id,
        candidate_root=str(tampered_root.resolve()),
        candidate_json_sha256=_sha256((tampered_root / "candidate.json").read_bytes()),
        candidate_manifest_hash=str(candidate_metadata["manifest_hash"]),
        candidate_artifact_hash=str(candidate_metadata["artifact_hash"]),
        candidate_freeze_hash=str(candidate_metadata["candidate_freeze_hash"]),
        dataset_hash=str(candidate_metadata["dataset_hash"]),
    )
    tampered_policy = save_personal_use_policy(
        tampered_policy_path,
        RecommendationPersonalUseSelectionV1(
            scope_id="synthetic-tampered-candidate-user",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            candidate=tampered_candidate,
        ),
        expected_revision=0,
    )
    tampered_provider = _SyntheticMarketProvider(config, market_data)
    tampered_service = _make_service(
        config=config,
        market_provider=tampered_provider,
        consumer=base_consumer,
        scored_dates=[],
    ).with_personal_use_policy(tampered_policy)
    negative_execution = execute_module.execute_recommendation(
        tampered_service,
        {
            "profile_id": "synthetic-personal-tampered-candidate",
            "profile_version": "1",
            "recommendation_ranking": {"threshold_mode": "fixed"},
            "filters": {"industry": "全部"},
        },
        max_stocks=1,
        top_n=1,
        result_id=f"synthetic-personal-tampered-{decision_day.isoformat()}",
    )
    assert negative_execution.status.value == "completed"
    assert negative_execution.decision is not None
    assert tuple(item.stock_code for item in negative_execution.decision.items) == (_SYMBOL,)
    negative_policy_event = next(
        event
        for event in negative_execution.events
        if event.event_type == "personal_use_policy_snapshot"
    )
    assert negative_policy_event.details["requested_mode"] == PERSONAL_CALIBRATED_PROBABILITY_MODE
    assert negative_policy_event.details["effective_mode"] == RULE_ONLY_MODE
    negative_receipt_events = tuple(
        event
        for event in negative_execution.events
        if event.event_type == "ml_projection_receipt_capture"
    )
    assert negative_receipt_events == ()
    assert negative_execution.ml_projection_refs == ()
    assert negative_execution.ml_receipt_refs == ()
    assert not (tampered_policy_path.parent / "inference_projection").exists()
    assert not global_pointer.exists()


def test_personal_daily_public_path_keeps_canonical_capture_pending_without_forward_prices(
    tmp_path: Path,
) -> None:
    """真 app capture/readback 進入日常入口；缺 forward 價格時只能 pending。"""

    from app_module.recommendation.personal_natural_outcome_daily import (
        run_personal_natural_outcome_daily,
    )
    from tests.test_recommendation_personal_natural_outcomes import _write_natural_source
    from tests.test_recommendation_personal_prediction_capture import _build_case

    root = tmp_path / "pending-daily-case"
    execution, _receipt, _receipt_path, _persistence, queries, _policy = _build_case(
        root
    )
    capture_root = root / "personal-captures"
    capture = capture_personal_saved_result(
        execution.result_id,
        queries,
        capture_root,
    )
    capture_day = date.fromisoformat(
        str(execution.context.as_of_date.isoformat())
    )
    provider, resolver, _sessions = _write_natural_source(
        root / "outcome-source",
        capture_day=capture_day,
        include_stock_endpoints=False,
    )
    source_before = provider.database_path.read_bytes()

    receipt = run_personal_natural_outcome_daily(
        canonical_recommendation_output_root=root / "canonical",
        capture_paths=(capture.path,),
        personal_capture_root=capture_root,
        market_source_db=provider.database_path,
        calendar_cache_path=resolver.calendar_cache_path,
        evaluation_at=datetime.now(timezone.utc),
        isolated_output_root=root / "isolated-outcomes",
    )

    assert receipt.status == "completed_with_pending"
    assert receipt.capture_statuses == ("pending",)
    assert receipt.outcome_paths == ()
    assert provider.database_path.read_bytes() == source_before


def test_user_declared_v2_candidate_reaches_personal_service_and_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """隔離 user-declared SQLite 可經真 runner、consumer 與 canonical capture 使用。

    此測試只證明明示資料庫來源下的研究用工程路徑；不宣稱官方 PIT、自然樣本
    效果或 promotion，也不接觸正式資料根目錄或全域 active pointer。
    """

    registry = CORE_LONG_HISTORY_FEATURE_REGISTRY
    decision_day = datetime.now(_TAIPEI).date()
    data_root = tmp_path / "data-root"
    source_database = data_root / "sqlite" / "twstock.db"
    source_start = decision_day - timedelta(days=620)
    source_days = 620
    _write_user_declared_replay_source(
        source_database,
        first_day=source_start,
        days=source_days,
        symbols=("AAA", "BBB", "CCC"),
    )

    learning_output_root = tmp_path / "learning-output"
    replay_start = decision_day - timedelta(days=240)
    replay_end = decision_day - timedelta(days=60)
    replay_config = RecommendationHistoricalReplayConfig(
        history_start_date=source_start.isoformat(),
        replay_start_date=replay_start.isoformat(),
        replay_end_date=replay_end.isoformat(),
        symbols=("AAA", "BBB", "CCC"),
        fixed_round_trip_cost_bp=50,
        max_decision_dates=64,
        selection_policy="chronological_first_eligible_date",
    )
    replay = RecommendationHistoricalReplayService(
        MLHistoricalSnapshotProvider(source_database)
    ).build(replay_config)
    assert replay.training_data_eligible is True
    assert replay.forward_evidence_eligible is False
    assert replay.formal_candidate_eligible is False
    assert replay.samples
    assert replay.lookahead_checks["feature_snapshot_rows_strictly_before_decision"] is True
    assert replay.lookahead_checks["feature_available_date_not_after_decision"] is True
    assert replay.source_disclosures["technical"]["source_contract"]["verified"] is True
    assert replay.source_disclosures["corporate_actions"]["source_contract"]["verified"] is True
    replay_manifest_path = replay.persist(learning_output_root)
    training_as_of = max(
        date.fromisoformat(sample.label_available_date) for sample in replay.samples
    )
    assert training_as_of <= decision_day

    runner = DailyRecommendationLearningRunner(
        output_root=learning_output_root,
        data_root=data_root,
        feature_names=registry.canonical_ids,
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        training_config=RecommendationCalibrationTrainingConfig(
            minimum_training_rows=20,
            minimum_fold_train_rows=10,
            minimum_calibration_samples=10,
            minimum_train_dates=30,
            test_date_count=2,
            purge_trading_days=20,
        ),
    )
    dataset_quality = {
        "training_data_eligible": True,
        # 這是訓練 cutoff 的語義欄位；個人來源仍由下方 V2 trust 標示為 research-only。
        "research_only": False,
        "forward_evidence_eligible": False,
        "formal_candidate_eligible": False,
        "candidate_blockers": [
            "user_declared_source_time_is_research_only_not_official_pit",
            "natural_forward_evidence_required_for_promotion",
        ],
        "replay_dataset_manifest_path": str(replay_manifest_path),
        "replay_coverage": dict(replay.coverage),
        "replay_selection_policy": replay_config.selection_policy,
        "replay_sample_count": replay.sample_count,
    }
    training_result = runner.run(
        decision_date=decision_day.isoformat(),
        run_scope="user-declared-v2-injected-source",
        samples=replay.samples,
        natural_evidence=None,
        data_dependency_status="ready",
        outcome_dependency_status="not_checked",
        dataset_quality=dataset_quality,
        training_as_of=training_as_of.isoformat(),
        lineage_sources={"replay": replay.samples},
    )
    assert training_result.status == "completed", training_result.reason
    assert training_result.candidate_root
    assert training_result.candidate_id
    assert training_result.training_lineage_status == "verified"
    assert training_result.decision != "adopt"
    candidate_root = Path(training_result.candidate_root)
    candidate_metadata = json.loads(
        (candidate_root / "candidate.json").read_text(encoding="utf-8")
    )
    assert candidate_metadata["training_semantics"] == "decision_time"
    assert candidate_metadata["training_data_eligible"] is True
    assert candidate_metadata["formal_candidate_eligible"] is False
    assert candidate_metadata["production_action_allowed"] is False

    proposal = inspect_personal_source_time_binding(
        candidate_root=candidate_root,
        source_database_path=source_database,
        data_root=data_root,
        explicit_output_root=learning_output_root,
    )
    assert proposal.candidate.candidate_id == training_result.candidate_id
    policy_path = tmp_path / "personal-profile" / "policy.json"
    policy = save_personal_use_policy_v2(
        policy_path,
        RecommendationPersonalUseSelectionV2(
            scope_id="user-declared-v2-full-stack",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            source_time_binding=proposal,
        ),
        expected_revision=0,
    )
    assert policy.mode == PERSONAL_CALIBRATED_PROBABILITY_MODE
    assert policy.source_time_trust is not None
    assert policy.source_time_trust.basis == "user_declared_source_time"
    assert policy.source_time_trust.research_only is True
    assert policy.source_time_trust.official_historical_pit_verified is False

    inspected = inspect_personal_calibration_candidate(
        candidate_root=candidate_root,
        data_root=data_root,
        explicit_output_root=learning_output_root,
        source_database_path=source_database,
        personal_use_policy=policy,
    )
    assert inspected.status == "metadata_pinned_pending_runtime_validation"
    assert inspected.candidate is not None
    assert inspected.candidate.to_dict() == policy.candidate.to_dict()

    market_start = decision_day - timedelta(days=100)
    market_data = _market_frame(
        first_day=market_start,
        days=100,
        future_day=decision_day + timedelta(days=3_650),
    )
    recommendation_output_root = tmp_path / "recommendation-output"

    class _Config(SimpleNamespace):
        def resolve_output_path(self, subfolder: str) -> Path:
            return recommendation_output_root / subfolder

    config = _Config(
        db_file=source_database,
        default_start_date=source_start.isoformat(),
        output_root=recommendation_output_root,
        data_root=data_root,
        use_sqlite=False,
        pit_market_scope="twse_listed",
    )
    global_pointer = tmp_path / "global-pointer-must-not-be-used.json"
    base_consumer = RecommendationCalibrationConsumer(
        pointer_path=global_pointer,
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
        data_root=data_root,
    )
    provider = _SyntheticMarketProvider(config, market_data)
    scored_dates: list[str] = []
    base_service = _make_service(
        config=config,
        market_provider=provider,
        consumer=base_consumer,
        scored_dates=scored_dates,
    )
    personal_service = base_service.with_personal_use_policy(policy)
    assert type(personal_service.calibration_consumer) is RecommendationCalibrationConsumer
    assert personal_service.calibration_consumer.pointer_path == policy_path.resolve()

    result_id = f"user-declared-v2-personal-{decision_day.isoformat()}"
    execution = execute_module.execute_recommendation(
        personal_service,
        {
            "profile_id": "user-declared-v2-personal",
            "profile_version": "1",
            "recommendation_ranking": {"threshold_mode": "fixed"},
            "filters": {"industry": "全部"},
        },
        max_stocks=1,
        top_n=1,
        result_id=result_id,
    )
    assert execution.status.value == "completed"
    assert execution.decision is not None
    assert tuple(item.stock_code for item in execution.decision.items) == (_SYMBOL,)
    assert execution.context.decision_at is not None
    assert execution.context.as_of_date == execution.request.as_of_date == decision_day
    assert all(
        date.fromisoformat(item) < decision_day for item in scored_dates
    )
    policy_event = next(
        event
        for event in execution.events
        if event.event_type == "personal_use_policy_snapshot"
    )
    assert (
        policy_event.details["effective_mode"]
        == PERSONAL_CALIBRATED_PROBABILITY_MODE
    )
    policy_trust = policy_event.details["policy_snapshot"]["source_time_trust"]
    assert policy_trust["basis"] == "user_declared_source_time"
    assert policy_trust["research_only"] is True
    assert policy_trust["official_historical_pit_verified"] is False
    assert any(
        event.event_type == "ml_projection_receipt_capture"
        for event in execution.events
    )
    assert any(
        event.event_type == "personal_probability_baseline_snapshot"
        for event in execution.events
    )

    canonical = build_recommendation_composition(config)
    save_receipt = canonical.save_service.save_execution(execution)
    assert save_receipt.result_id == result_id
    fresh = build_recommendation_composition(config)
    readback = fresh.queries.get(result_id)
    assert readback is not None
    assert readback.execution == execution
    assert readback.integrity_basis == "canonical_payload_and_index_verified"
    assert readback.ml_read_status == "verified"
    assert len(readback.ml_projection_rows) == 1
    assert readback.ml_projection_rows[0]["stock_code"] == _SYMBOL
    active_projection = readback.ml_projection_rows[0]
    assert active_projection["status"] == "active_candidate", active_projection
    assert active_projection["calibrated_probability_status"] == "active_effective"
    assert type(active_projection["calibrated_probability_bp"]) is int
    assert active_projection["model_version"] == training_result.candidate_id
    assert (
        readback.ml_projection_rows[0]["calibrated_probability_bp"]
        == active_projection["calibrated_probability_bp"]
    )
    capture_root = tmp_path / "personal-capture"
    capture = capture_personal_saved_result(result_id, fresh.queries, capture_root)
    capture_payload = json.loads(capture.path.read_text(encoding="utf-8"))
    assert capture_payload["schema_version"] == "recommendation-personal-prediction-capture.v3"
    assert capture_payload["probability_baseline_snapshot"]["schema_version"] == (
        "recommendation-personal-probability-baseline-snapshot.v2"
    )
    capture_policy = capture_payload["policy_event"]["policy_snapshot"]
    assert capture_payload["policy_event"]["schema_version"] == (
        "recommendation-personal-use-policy-snapshot.v2"
    )
    assert capture_payload["policy_event"]["source_time_basis"] == (
        "user_declared_source_time"
    )
    assert capture_payload["policy_event"]["research_only"] is True
    assert capture_payload["policy_event"]["official_historical_pit_verified"] is False
    assert capture_policy["source_time_trust"]["research_only"] is True
    assert capture_policy["source_time_trust"][
        "official_historical_pit_verified"
    ] is False
    assert capture_payload["receipt_binding"]["projection_rows_sha256"] == (
        execution.ml_projection_refs[0].reference_id
    )
    assert not global_pointer.exists()

    def run_fallback_and_readback(
        suffix: str, *, expected_warning: str
    ) -> None:
        negative_result_id = f"{result_id}-{suffix}"
        negative_service = base_service.with_personal_use_policy(policy)
        negative_execution = execute_module.execute_recommendation(
            negative_service,
            {
                "profile_id": "user-declared-v2-personal",
                "profile_version": "1",
                "recommendation_ranking": {"threshold_mode": "fixed"},
                "filters": {"industry": "全部"},
            },
            max_stocks=1,
            top_n=1,
            result_id=negative_result_id,
        )
        assert negative_execution.status.value == "completed"
        assert negative_execution.decision is not None
        assert tuple(
            item.stock_code for item in negative_execution.decision.items
        ) == (_SYMBOL,)
        negative_policy_event = next(
            event
            for event in negative_execution.events
            if event.event_type == "personal_use_policy_snapshot"
        )
        assert (
            negative_policy_event.details["requested_mode"]
            == PERSONAL_CALIBRATED_PROBABILITY_MODE
        )
        assert negative_policy_event.details["effective_mode"] == RULE_ONLY_MODE
        context_event = next(
            event
            for event in negative_execution.events
            if event.event_type == "legacy_invocation_context"
        )
        sealed_warnings = tuple(context_event.details["warnings"])
        assert expected_warning in sealed_warnings, sealed_warnings

        negative_save = canonical.save_service.save_execution(negative_execution)
        assert negative_save.result_id == negative_result_id
        negative_readback = build_recommendation_composition(config).queries.get(
            negative_result_id
        )
        assert negative_readback is not None
        assert negative_readback.execution == negative_execution
        assert (
            negative_readback.integrity_basis
            == "canonical_payload_and_index_verified"
        )
        negative_readback_policy_event = next(
            event
            for event in negative_readback.execution.events
            if event.event_type == "personal_use_policy_snapshot"
        )
        assert negative_readback_policy_event.details["effective_mode"] == RULE_ONLY_MODE
        negative_readback_context = next(
            event
            for event in negative_readback.execution.events
            if event.event_type == "legacy_invocation_context"
        )
        readback_warnings = tuple(negative_readback_context.details["warnings"])
        assert expected_warning in readback_warnings, readback_warnings
        if negative_readback.ml_projection_rows:
            assert len(negative_readback.ml_projection_rows) == 1
            fallback_row = negative_readback.ml_projection_rows[0]
            assert fallback_row["stock_code"] == _SYMBOL
            # RecommendationCalibrationProjection.unavailable() serializes
            # status='rule_only'; the separate probability status is
            # 'unavailable'. Require the exact DTO values so missing fields
            # cannot satisfy a negative-control assertion.
            assert fallback_row["status"] == "rule_only", fallback_row
            assert fallback_row["calibrated_probability_bp"] is None, fallback_row
            assert (
                fallback_row["calibrated_probability_status"] == "unavailable"
            ), fallback_row
            row_warnings = fallback_row["warnings"]
            assert isinstance(row_warnings, list), fallback_row
            assert expected_warning in row_warnings, fallback_row
        else:
            assert negative_readback.ml_read_status == "unavailable"
            assert "ml_receipt_binding_missing" in negative_readback.diagnostics
        with pytest.raises(PersonalPredictionCaptureError):
            capture_personal_saved_result(
                negative_result_id,
                build_recommendation_composition(config).queries,
                tmp_path / f"must-not-capture-{suffix}",
            )
        assert not (tmp_path / f"must-not-capture-{suffix}").exists()

    # 非有限校準輸出只在模型數值邊界做故障注入；真實 public caller 仍須
    # 產生 rule 結果、封存具名 blocker 並由 fresh canonical query 讀回。
    def _nonfinite_calibration_output(
        _calibrator: FittedShadowProbabilityCalibrator, _raw: object
    ) -> list[float]:
        return [float("inf")]

    with monkeypatch.context() as invalid_output_patch:
        invalid_output_patch.setattr(
            FittedShadowProbabilityCalibrator,
            "predict",
            _nonfinite_calibration_output,
        )
        with pytest.raises(InvalidCalibrationOutputError):
            # 直接確認數值轉換守門使用具名錯誤；後面的同一 bad output 由
            # consumer 捕捉並轉成 fail-closed projection。
            from ml_module.recommendation_calibration_training import _calibrated_bp

            _calibrated_bp(
                FittedShadowProbabilityCalibrator(
                    calibration_id="invalid-test",
                    model_id="invalid-test",
                    estimator=object(),
                    sample_count=10,
                    fold_count=2,
                ),
                0.5,
            )
        run_fallback_and_readback(
            "nonfinite-output",
            expected_warning="model_probability_output_invalid_fail_closed",
        )

    # 修改隔離 replay slice 的一個 RSI 值，應在候選載入/投影前被來源信任
    # 重驗擋下；復原原值後再測 artifact hash，兩個負控互不遮蔽。
    source_sample = next(sample for sample in replay.samples if sample.symbol == _SYMBOL)
    source_feature_day = date.fromisoformat(source_sample.feature_as_of_date).strftime(
        "%Y%m%d"
    )
    with sqlite3.connect(source_database) as connection:
        original_row = connection.execute(
            "SELECT RSI FROM technical_indicators WHERE 日期=? AND 證券代號=?",
            (source_feature_day, _SYMBOL),
        ).fetchone()
        assert original_row is not None
        original_rsi = str(original_row[0])
        connection.execute(
            "UPDATE technical_indicators SET RSI=? WHERE 日期=? AND 證券代號=?",
            (str(Decimal(original_rsi) + Decimal(1)), source_feature_day, _SYMBOL),
        )
        connection.commit()
    try:
        run_fallback_and_readback(
            "source-slice-mismatch",
            expected_warning="candidate_training_source_time_unverified_fail_closed",
        )
    finally:
        with sqlite3.connect(source_database) as connection:
            connection.execute(
                "UPDATE technical_indicators SET RSI=? WHERE 日期=? AND 證券代號=?",
                (original_rsi, source_feature_day, _SYMBOL),
            )
            connection.commit()

    candidate_manifest = json.loads(
        (candidate_root / "manifest.json").read_text(encoding="utf-8")
    )
    artifact_path = candidate_root / str(candidate_manifest["artifact_filename"])
    artifact_bytes = artifact_path.read_bytes()
    assert artifact_bytes
    artifact_path.write_bytes(artifact_bytes[:-1] + bytes((artifact_bytes[-1] ^ 1,)))
    run_fallback_and_readback(
        "artifact-hash-mismatch",
        expected_warning="artifact_hash_mismatch",
    )
