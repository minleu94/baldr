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
            CREATE TABLE market_indices (
                日期 TEXT NOT NULL, 收盤指數 TEXT, 收盤價 TEXT, 指數名稱 TEXT
            );
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
            index_name = (
                "TAIEX"
                if current.weekday() < 5 and (current.month, current.day) != (1, 1)
                else "TRAINING_CONTEXT"
            )
            connection.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?, ?)",
                (compact_day, str(10_000 + offset), str(10_000 + offset), index_name),
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


def _prepare_mature_outcome_source_rows(
    database_path: Path, *, decision_day: date, endpoint_day: date, symbol: str
) -> None:
    """在隔離來源加入已到期的測試行情列，不代表官方市場表現。"""

    sessions: list[date] = []
    current = decision_day + timedelta(days=1)
    while len(sessions) < 20:
        if current.weekday() < 5 and (current.month, current.day) != (1, 1):
            sessions.append(current)
        current += timedelta(days=1)
    if sessions[-1] != endpoint_day:
        raise AssertionError("合成成熟測試的 endpoint 必須是第 20 個 weekday session")

    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1]) for row in connection.execute('PRAGMA table_info("daily_prices")')
        }
        if not {"日期", "證券代號", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價"}.issubset(columns):
            raise AssertionError("測試來源 daily_prices schema 不符合固定 fixture")
        market_columns = {
            str(row[1])
            for row in connection.execute('PRAGMA table_info("market_indices")')
        }
        if "指數名稱" not in market_columns:
            raise AssertionError("測試來源缺少 TAIEX index identity 欄")

        # 測試用的歷史特徵 market rows 仍保留；只有 resolver 可辨識的 TAIEX
        # 子集使用工作日名稱，避免把週末的訓練背景列誤當官方 session。
        for raw_day, in connection.execute('SELECT "日期" FROM market_indices').fetchall():
            raw_text = str(raw_day)
            parsed_day = (
                date(int(raw_text[:4]), int(raw_text[4:6]), int(raw_text[6:8]))
                if len(raw_text) == 8
                else date.fromisoformat(raw_text[:10])
            )
            index_name = (
                "TAIEX"
                if parsed_day.weekday() < 5
                and (parsed_day.month, parsed_day.day) != (1, 1)
                else "TRAINING_CONTEXT"
            )
            connection.execute(
                'UPDATE market_indices SET "指數名稱"=? WHERE "日期"=?',
                (index_name, raw_day),
            )

        connection.execute(
            'CREATE INDEX IF NOT EXISTS ix_test_daily_prices_symbol_date '
            'ON daily_prices ("證券代號", "日期")'
        )
        start_text = decision_day.strftime("%Y%m%d")
        endpoint_text = endpoint_day.strftime("%Y%m%d")
        for endpoint_text_value, close in ((start_text, "100"), (endpoint_text, "120")):
            existing = connection.execute(
                'SELECT COUNT(*) FROM daily_prices WHERE "證券代號"=? AND "日期"=?',
                (symbol, endpoint_text_value),
            ).fetchone()
            if existing != (0,):
                raise AssertionError("成熟測試 endpoint 不可覆蓋既有來源列")
            connection.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    endpoint_text_value,
                    symbol,
                    100_000,
                    10_000_000,
                    close,
                    close,
                    close,
                    close,
                ),
            )

        existing_index_dates = {
            str(row[0])
            for row in connection.execute('SELECT "日期" FROM market_indices')
        }
        for index, session in enumerate(sessions, start=1):
            session_text = session.strftime("%Y%m%d")
            if session_text in existing_index_dates:
                raise AssertionError("測試市場來源已含未來 session 列")
            close = str(20_000 + index)
            connection.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?, ?)",
                (session_text, close, close, "TAIEX"),
            )


def _sqlite_source_storage_state(database_path: Path) -> dict[str, Any]:
    """固定測試 DB 與 WAL/SHM 的讀前後 bytes/stat。"""

    metadata = database_path.stat()
    state: dict[str, Any] = {
        "database_sha256": _sha256(database_path.read_bytes()),
        "database_size_bytes": metadata.st_size,
        "database_mtime_ns": metadata.st_mtime_ns,
        "database_device": metadata.st_dev,
        "database_inode": metadata.st_ino,
    }
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(database_path) + suffix)
        if sidecar.exists():
            sidecar_bytes = sidecar.read_bytes()
            sidecar_metadata = sidecar.stat()
            state[suffix] = {
                "sha256": _sha256(sidecar_bytes),
                "size_bytes": sidecar_metadata.st_size,
                "mtime_ns": sidecar_metadata.st_mtime_ns,
            }
        else:
            state[suffix] = None
    return state


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
    from tests.test_recommendation_personal_natural_outcomes import (
        _next_twenty_weekdays,
        _write_natural_source,
    )
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
        use_sqlite=True,
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
        as_of_date=decision_day,
        universe=[_SYMBOL],
        result_id=result_id,
    )
    assert execution.status.value == "completed", execution.failure_reason
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

    # Stage C remains the existing writer/schema.  The app read service derives
    # an exact, read-only assessment projection from its explicit summary path.
    from app_module.personalization_read_service import (
        PersonalizationReadService,
        _stage_c_payload_hash,
    )
    from app_module.recommendation.personal_natural_outcome_daily import (
        run_personal_natural_outcome_daily,
    )
    from tests.test_recommendation_personal_natural_outcomes import _write_natural_source

    _outcome_provider, outcome_resolver, _outcome_sessions = _write_natural_source(
        tmp_path / "assessment-calendar-fixture",
        capture_day=decision_day,
        include_stock_endpoints=False,
    )
    assessment_daily = run_personal_natural_outcome_daily(
        canonical_recommendation_output_root=recommendation_output_root,
        capture_paths=(capture.path,),
        personal_capture_root=capture_root,
        market_source_db=source_database,
        calendar_cache_path=outcome_resolver.calendar_cache_path,
        evaluation_at=datetime.now(timezone.utc),
        isolated_output_root=tmp_path / "assessment-daily-output",
    )
    assert assessment_daily.capture_statuses == ("pending",)
    assessment = PersonalizationReadService.from_paths(
        output_root=recommendation_output_root
    ).read_personal_model_assessment(
        result_id,
        capture.path,
        capture_root,
        assessment_daily.summary_path,
    )
    assert assessment.assessment_status == "insufficient_data"
    assert assessment.recommendation == "insufficient_data"
    assert assessment.evidence_status == "pending"
    assert assessment.matured_sample_count == 0
    assert assessment.pending_sample_count == 1
    assert assessment.metrics["model_brier_bp"] is None
    assert assessment.metrics["fixed_null_benchmark_brier_bp"] is None
    assert assessment.after_cost["status"] == "unavailable"
    assert assessment.after_cost["model_brier_bp"] is None
    assert assessment.scope["upside_baseline"] == {
        "kind": "fixed_null_benchmark_50pct",
        "id": "null_benchmark_50pct_v1",
        "probability_bp": 5_000,
    }
    assert assessment.scope["return_basis"] == "close_to_close_event_date"
    assert assessment.scope["is_execution_pnl"] is False
    assert assessment.auto_switch is False

    # A recomputed outer self-hash cannot associate a summary with another
    # capture.  Keep the original create-only summary intact.
    summary_body = json.loads(assessment_daily.summary_path.read_text(encoding="utf-8"))
    summary_body["captures"][0]["capture_id"] = "sha256:" + ("0" * 64)
    summary_body.pop("payload_sha256")
    summary_body["payload_sha256"] = _stage_c_payload_hash(summary_body)
    forged_summary = (
        assessment_daily.summary_path.parent
        / f"{summary_body['payload_sha256'][7:]}.json"
    )
    forged_summary.write_text(
        json.dumps(
            summary_body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exactly one matching capture"):
        PersonalizationReadService.from_paths(
            output_root=recommendation_output_root
        ).read_personal_model_assessment(
            result_id,
            capture.path,
            capture_root,
            forged_summary,
        )

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


def test_matured_assessment_readback_rechecks_contract_rows_and_prices(
    tmp_path: Path,
) -> None:
    """只驗 matured readback contract；不代表真實 V2 採用或自然成效。"""

    from dataclasses import replace as dataclass_replace

    from app_module.personalization_read_service import (
        PersonalizationReadService,
        _stage_c_payload_hash,
    )
    from app_module.recommendation.contracts import ExecutionEvent
    from app_module.recommendation.personal_use_policy import (
        PERSONAL_USE_POLICY_SCHEMA_V2,
        PERSONAL_USE_POLICY_VERSION_V2,
        PersonalSourceFileIdentityV1,
        PersonalSourceReplayScopeV1,
        PersonalSourceTimeTrustV1,
        validate_personal_use_policy_snapshot,
        _policy_hash,
    )
    from app_module.recommendation.personal_prediction_capture import (
        PERSONAL_PROBABILITY_BASELINE_EVENT_SCHEMA_V2,
        PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2,
        _canonical_utc,
        capture_personal_saved_result,
        read_personal_prediction_capture,
        _canonical_json_bytes,
    )
    from app_module.recommendation.personal_use_policy import PersonalCalibrationCandidateV1
    from app_module.recommendation.personal_natural_outcome_daily import (
        run_personal_natural_outcome_daily,
    )
    from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
    from ml_module.recommendation_inference_provenance import (
        build_inference_projection_receipt,
        persist_inference_projection_receipt,
        read_inference_projection_receipt,
    )
    from tests.test_c1_ml_abi_receipt_readiness import _query_stack
    from tests.test_recommendation_personal_natural_outcomes import (
        _complete_cost_personal_capture,
        _write_natural_source,
    )

    seed_root = tmp_path / "seed-fixture"
    capture_seed = _complete_cost_personal_capture(seed_root)
    result_id = str(capture_seed["result_id"])
    source_database_provider, session_resolver, _sessions = _write_natural_source(
        tmp_path / "mature-market-source",
        capture_day=date.fromisoformat(capture_seed["receipt_binding"]["decision_date"]),
        include_liquidity_costs=True,
    )
    source_database = source_database_provider.database_path.resolve(strict=True)
    with sqlite3.connect(source_database) as connection:
        connection.execute(
            'CREATE INDEX ix_assessment_symbol_date '
            'ON daily_prices ("證券代號", "日期")'
        )

    seed_persistence, seed_queries = _query_stack(seed_root / "canonical")
    del seed_persistence
    seed_read_model = seed_queries.get(result_id)
    assert seed_read_model is not None and seed_read_model.execution is not None
    execution = seed_read_model.execution
    assert seed_read_model.ml_read_status == "verified"

    decision_at_event = next(
        event
        for event in execution.events
        if event.event_type == "personal_use_policy_snapshot"
    )
    old_policy = dict(decision_at_event.details["policy_snapshot"])
    candidate = PersonalCalibrationCandidateV1(**dict(old_policy["candidate"]))
    source_metadata = source_database.stat()
    source_trust = PersonalSourceTimeTrustV1(
        source_database_path=str(source_database),
        file_identity=PersonalSourceFileIdentityV1(
            device=int(source_metadata.st_dev),
            inode=int(source_metadata.st_ino),
        ),
        source_database_size_bytes=int(source_metadata.st_size),
        source_slice_sha256=_sha256(source_database.read_bytes()),
        candidate=candidate,
        replay_scope=PersonalSourceReplayScopeV1(
            dataset_ids=("synthetic-readback-source",),
            decision_dates=("2025-04-29",),
            symbols=("1101", "2330"),
            sample_count=2,
        ),
        confirmed_at=str(old_policy["confirmed_at"]),
    )
    policy_body = {
        key: value
        for key, value in old_policy.items()
        if key not in {"schema_version", "policy_version", "policy_sha256"}
    }
    policy_body.update(
        {
            "schema_version": PERSONAL_USE_POLICY_SCHEMA_V2,
            "policy_version": PERSONAL_USE_POLICY_VERSION_V2,
            "candidate": candidate.to_dict(),
            "source_time_trust": source_trust.to_dict(),
        }
    )
    policy_snapshot = validate_personal_use_policy_snapshot(
        {**policy_body, "policy_sha256": _policy_hash(policy_body)}
    )
    updated_policy_details = {
        **dict(decision_at_event.details),
        "schema_version": "recommendation-personal-use-policy-snapshot.v2",
        "policy_snapshot": policy_snapshot,
        "source_time_basis": "user_declared_source_time",
        "research_only": True,
        "official_historical_pit_verified": False,
    }
    receipt_event = next(
        event
        for event in execution.events
        if event.event_type == "ml_projection_receipt_capture"
    )
    receipt_details = dict(receipt_event.details)
    scenario = build_legacy_cost_scenario(50)
    assert receipt_details["cost_scenario_hash"] == scenario.scenario_hash
    original_receipt = read_inference_projection_receipt(
        receipt_details["path"],
        expected_receipt_hash=str(receipt_details["receipt_hash"]),
        expected_decision_date=str(receipt_details["decision_date"]),
        expected_candidate_id=str(receipt_details["candidate_id"]),
        expected_result_id=result_id,
        expected_cost_scenario_hash=scenario.scenario_hash,
    )
    original_payload = dict(original_receipt.payload)
    scenario_payload = scenario.to_dict(include_hash=True)
    enriched_projections: list[dict[str, Any]] = []
    for raw_projection in original_payload["projections"]:
        projection = dict(raw_projection)
        projection.update(
            {
                "cost_scenario_id": scenario.scenario_id,
                "cost_scenario_version": scenario.scenario_version,
                "cost_scenario_hash": scenario.scenario_hash,
                "cost_basis": scenario.cost_basis,
                "cost_basis_bp": scenario.fixed_round_trip_cost_bp,
                "cost_policy_id": scenario.policy_id,
                "cost_policy_version": scenario.policy_version,
                "policy_estimate_date": scenario.policy_estimate_date,
                "research_order_amount_twd": scenario_payload[
                    "research_order_amount_twd"
                ],
                "research_order_quantity_shares": scenario.research_order_quantity_shares,
                "lot_type": scenario.lot_type,
                "instrument_type": scenario.instrument_type,
                "cost_scenario": scenario_payload,
            }
        )
        enriched_projections.append(projection)
    enriched_receipt = build_inference_projection_receipt(
        decision_date=str(original_payload["decision_date"]),
        result_id=result_id,
        candidate_identity=dict(original_payload["candidate_identity"]),
        training_provenance=dict(original_payload["training_provenance"]),
        inference_provenance=dict(original_payload["inference_provenance"]),
        compatibility=dict(original_payload["provenance_compatibility"]),
        projections=enriched_projections,
        selection_contract=dict(original_payload["selection_contract"]),
    )
    learning_root = Path(str(capture_seed["receipt_binding"]["learning_root"]))
    enriched_receipt_path = persist_inference_projection_receipt(
        learning_root, enriched_receipt
    ).resolve(strict=True)
    enriched_receipt_payload = dict(enriched_receipt.payload)
    projected_codes = [
        str(row["stock_code"]) for row in enriched_receipt_payload["projections"]
    ]
    receipt_details.update(
        {
            "path": str(enriched_receipt_path),
            "receipt_hash": enriched_receipt.receipt_hash,
            "candidate_identity": dict(original_payload["candidate_identity"]),
            "cost_scenario_hash": scenario.scenario_hash,
            "projected_stock_codes": projected_codes,
            "projection_rows_sha256": str(
                enriched_receipt_payload["projection_rows_sha256"]
            ),
        }
    )
    updated_receipt_event = dataclass_replace(receipt_event, details=receipt_details)
    old_binding = execution.ml_receipt_refs[0]
    updated_binding = dataclass_replace(
        old_binding,
        receipt_ref=dataclass_replace(
            old_binding.receipt_ref,
            reference_id=str(enriched_receipt_path),
        ),
        receipt_hash=enriched_receipt.receipt_hash,
        projected_stock_codes=tuple(projected_codes),
        cost_scenario_hash=scenario.scenario_hash,
    )
    updated_projection_ref = dataclass_replace(
        execution.ml_projection_refs[0],
        reference_id=str(enriched_receipt_payload["projection_rows_sha256"]),
    )
    updated_events = [
        dataclass_replace(event, details=updated_policy_details)
        if event is decision_at_event
        else updated_receipt_event
        if event is receipt_event
        else event
        for event in execution.events
    ]
    delivered_codes = [str(item.stock_code) for item in execution.decision.items]
    active_codes = projected_codes
    assert set(delivered_codes) == set(active_codes)
    canonical_decision_at = _canonical_utc(
        decision_at_event.details["decision_at"], "decision_at"
    )
    baseline_decision_at = datetime.fromisoformat(
        canonical_decision_at.replace("Z", "+00:00")
    )
    baseline_body: dict[str, Any] = {
        "schema_version": PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2,
        "result_id": result_id,
        "decision_at": canonical_decision_at,
        "decision_date": capture_seed["receipt_binding"]["decision_date"],
        "receipt_hash": receipt_details["receipt_hash"],
        "projection_rows_sha256": receipt_details["projection_rows_sha256"],
        "cost_scenario_hash": receipt_details["cost_scenario_hash"],
        "projected_stock_codes": active_codes,
        "upside_baseline_kind": "fixed_null_benchmark_50pct",
        "upside_baseline_id": "null_benchmark_50pct_v1",
        "upside_probability_bp_by_symbol": {
            code: 5_000 for code in active_codes
        },
        "after_cost_baseline_status": "unavailable",
        "after_cost_baseline_id": None,
        "after_cost_probability_bp_by_symbol": {
            code: None for code in active_codes
        },
        "delivered_stock_codes": delivered_codes,
        "model_active_stock_codes": active_codes,
        "rule_only_fallback_stock_codes": [],
        "delivered_count": len(delivered_codes),
        "model_active_count": len(active_codes),
        "fallback_count": 0,
        "model_coverage_bp": 10_000,
        "cost_scenario": scenario.to_dict(include_hash=True),
    }
    baseline_body["snapshot_sha256"] = _sha256(
        _canonical_json_bytes(baseline_body)
    )
    updated_events.append(
        ExecutionEvent(
            event_type="personal_probability_baseline_snapshot",
            message="隔離 matured readback 契約測試基準",
            occurred_at=baseline_decision_at,
            details={
                "schema_version": PERSONAL_PROBABILITY_BASELINE_EVENT_SCHEMA_V2,
                "result_id": result_id,
                "decision_at": canonical_decision_at,
                "snapshot": baseline_body,
            },
        )
    )
    v2_execution = dataclass_replace(
        execution,
        events=tuple(updated_events),
        ml_receipt_refs=(updated_binding,),
        ml_projection_refs=(updated_projection_ref,),
    )

    canonical_root = tmp_path / "mature-canonical"
    persistence, queries = _query_stack(canonical_root)
    assert queries.get(result_id) is None
    persistence.save(v2_execution, now=lambda: datetime.now(timezone.utc))
    persisted = queries.get(result_id)
    assert persisted is not None and persisted.execution == v2_execution
    assert persisted.integrity_basis == "canonical_payload_and_index_verified"
    persisted_baseline = next(
        event
        for event in persisted.execution.events
        if event.event_type == "personal_probability_baseline_snapshot"
    )
    assert persisted_baseline.details["schema_version"] == (
        PERSONAL_PROBABILITY_BASELINE_EVENT_SCHEMA_V2
    )
    assert persisted_baseline.details["result_id"] == result_id
    assert persisted_baseline.details["decision_at"] == canonical_decision_at
    assert persisted_baseline.occurred_at == baseline_decision_at

    capture_root = tmp_path / "mature-captures"
    captured = capture_personal_saved_result(result_id, queries, capture_root)
    capture = read_personal_prediction_capture(
        captured.path,
        queries,
        capture_root,
        expected_result_id=result_id,
    )
    assert capture["schema_version"] == "recommendation-personal-prediction-capture.v3"
    assert capture["policy_event"]["research_only"] is True
    assert capture["policy_event"]["official_historical_pit_verified"] is False

    storage_before = _sqlite_source_storage_state(source_database)
    daily = run_personal_natural_outcome_daily(
        canonical_recommendation_output_root=canonical_root,
        capture_paths=(captured.path,),
        personal_capture_root=capture_root,
        market_source_db=source_database,
        calendar_cache_path=session_resolver.calendar_cache_path,
        evaluation_at=datetime.now(timezone.utc),
        isolated_output_root=tmp_path / "mature-assessment-output",
    )
    assert daily.capture_statuses == ("matured",)
    assert _sqlite_source_storage_state(source_database) == storage_before

    reader = PersonalizationReadService.from_paths(output_root=canonical_root)
    assessment = reader.read_personal_model_assessment(
        result_id,
        captured.path,
        capture_root,
        daily.summary_path,
    )
    assert assessment.evidence_status == "matured"
    assert assessment.matured_sample_count == len(active_codes)
    assert assessment.pending_sample_count == 0
    assert assessment.metrics["sample_count"] == len(active_codes)
    assert assessment.metrics["model_brier_bp"] is not None
    assert assessment.identity["verified_market_price_rows_sha256"].startswith(
        "sha256:"
    )
    assert assessment.after_cost["status"] == "unassessed"
    assert assessment.after_cost["model_brier_bp"] is None
    assert assessment.after_cost["fixed_null_benchmark_brier_bp"] is None
    assert _sqlite_source_storage_state(source_database) == storage_before

    def publish_rehashed_outcome_and_summary(
        outcome_body: dict[str, Any], *, tag: str
    ) -> Path:
        outcome_body.pop("payload_sha256", None)
        outcome_digest = _stage_c_payload_hash(outcome_body)
        outcome_body["payload_sha256"] = outcome_digest
        tampered_root = tmp_path / f"tampered-{tag}" / "personal_natural_outcomes"
        outcome_directory = tampered_root / "outcomes"
        summary_directory = tampered_root / "runs"
        outcome_directory.mkdir(parents=True)
        summary_directory.mkdir(parents=True)
        # Stage C names outcomes by capture/evaluation identity, not by payload hash.
        outcome_path = outcome_directory / daily.outcome_paths[0].name
        assert not outcome_path.exists()
        outcome_path.write_text(
            json.dumps(
                outcome_body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        summary_body = json.loads(daily.summary_path.read_text(encoding="utf-8"))
        summary_body["captures"][0]["outcome_artifact"] = {
            "path": str(outcome_path),
            "payload_sha256": outcome_digest,
        }
        summary_body.pop("payload_sha256", None)
        summary_digest = _stage_c_payload_hash(summary_body)
        summary_body["payload_sha256"] = summary_digest
        summary_path = summary_directory / f"{summary_digest[7:]}.json"
        assert not summary_path.exists(), tag
        summary_path.write_text(
            json.dumps(
                summary_body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return summary_path

    original_outcome = json.loads(daily.outcome_paths[0].read_text(encoding="utf-8"))
    forged_return = json.loads(json.dumps(original_outcome))
    forged_row = forged_return["projection"]["outcomes"][0]
    code = str(forged_row["stock_code"])
    # Coordinated、內部 label 相符但與 DB 價格相反的重算仍須被拒絕。
    forged_row["stock_return_bp"] = -1_000 if code == "1101" else 1_000
    forged_row["label"] = int(forged_row["stock_return_bp"] > 0)
    forged_return_summary = publish_rehashed_outcome_and_summary(
        forged_return, tag="coordinated-return-tamper"
    )
    with pytest.raises(ValueError, match="differs from exact read-only source prices"):
        reader.read_personal_model_assessment(
            result_id, captured.path, capture_root, forged_return_summary
        )

    forged_label_kind = json.loads(json.dumps(original_outcome))
    forged_label_kind["projection"]["outcomes"][0]["label_kind"] = (
        "stock_close_return_negative.v1"
    )
    forged_label_summary = publish_rehashed_outcome_and_summary(
        forged_label_kind, tag="label-kind-tamper"
    )
    with pytest.raises(ValueError, match="outcome row does not match"):
        reader.read_personal_model_assessment(
            result_id, captured.path, capture_root, forged_label_summary
        )

    forged_label_relation = json.loads(json.dumps(original_outcome))
    relation_row = forged_label_relation["projection"]["outcomes"][0]
    relation_row["label"] = 1 - int(relation_row["label"])
    forged_relation_summary = publish_rehashed_outcome_and_summary(
        forged_label_relation, tag="label-return-relation-tamper"
    )
    with pytest.raises(ValueError, match="outcome row does not match"):
        reader.read_personal_model_assessment(
            result_id, captured.path, capture_root, forged_relation_summary
        )

    forged_after_cost = json.loads(json.dumps(original_outcome))
    forged_after_cost["projection"]["after_cost_status"] = (
        "matured_with_after_cost_probability"
    )
    forged_after_cost_summary = publish_rehashed_outcome_and_summary(
        forged_after_cost, tag="after-cost-status-tamper"
    )
    after_cost_readback = reader.read_personal_model_assessment(
        result_id, captured.path, capture_root, forged_after_cost_summary
    )
    assert after_cost_readback.after_cost["status"] == "unassessed"
    assert (
        after_cost_readback.after_cost["reported_projection_status"]
        == "matured_with_after_cost_probability"
    )
    assert after_cost_readback.after_cost["model_brier_bp"] is None
    assert after_cost_readback.after_cost["sample_count"] is None
    assert _sqlite_source_storage_state(source_database) == storage_before


def _central_rebuild_args(tmp_path: Path) -> list[str]:
    from data_module.ml_storage_capacity import heavy_chain_lock_path

    data = tmp_path / "data"
    return [
        "--data-root", str(data), "--source-db", str(data / "source.sqlite"),
        "--output-root", str(tmp_path / "new-version"),
        "--heavy-chain-lock", str(heavy_chain_lock_path(data / "output" / "release_v4")),
        "--symbols", "1103,1259", "--history-start-date", "2014-01-01",
        "--replay-start-date", "2024-09-14", "--replay-end-date", "2026-09-14",
        "--training-as-of", "2026-09-14", "--decision-date", "2026-09-14",
        "--max-decision-dates", "100", "--fixed-round-trip-cost-bp", "50",
        "--run-scope", "isolated-central-test",
    ]


def test_central_rebuild_preview_never_fits_publishes_or_locks(tmp_path, monkeypatch, capsys):
    from scripts.scheduled.rebuild_personal_calibration_candidate import main
    from data_module import ml_storage_capacity as capacity
    from data_module import ml_historical_snapshot_provider as provider
    from ml_module import recommendation_historical_replay as replay

    def forbidden(*args, **kwargs):
        pytest.fail("preview must not fit, persist, or acquire a writer lock")

    monkeypatch.setattr(DailyRecommendationLearningRunner, "run", forbidden)
    monkeypatch.setattr(capacity, "acquire_heavy_chain_reservation", forbidden)
    monkeypatch.setattr(provider, "MLHistoricalSnapshotProvider", lambda path: object())
    result = SimpleNamespace(
        samples=(object(),), dataset_hash="sha256:" + "a" * 64,
        source_fingerprint="sha256:" + "b" * 64,
        coverage={"source_contract": {"status": "unverified"}},
        source_disclosures={"publication_time": "unknown"},
        lookahead_checks={}, candidate_blockers=("historical_pit_unknown",),
        persist=forbidden,
    )
    monkeypatch.setattr(replay.RecommendationHistoricalReplayService, "build", lambda self, config: result)
    assert main(_central_rebuild_args(tmp_path)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["model_training_performed"] is False
    assert payload["activation_performed"] is False
    assert payload["historical_blockers"] == ["historical_pit_unknown"]
    assert payload["source_disclosures"]["publication_time"] == "unknown"
    assert not (tmp_path / "new-version").exists()
    assert not (tmp_path / "data").exists()


def test_central_rebuild_existing_output_rejected_before_source_or_fit(tmp_path, monkeypatch):
    from scripts.scheduled.rebuild_personal_calibration_candidate import main

    root = tmp_path / "new-version"
    root.mkdir()
    sentinel = root / "original.json"
    sentinel.write_bytes(b"original-source")
    monkeypatch.setattr(DailyRecommendationLearningRunner, "run", lambda *a, **k: pytest.fail("no fit"))
    with pytest.raises(SystemExit):
        main(_central_rebuild_args(tmp_path) + ["--execute"])
    assert sentinel.read_bytes() == b"original-source"
    assert list(root.iterdir()) == [sentinel]


def test_central_rebuild_busy_shared_lock_never_reads_source_or_fits(tmp_path, monkeypatch, capsys):
    from scripts.scheduled.rebuild_personal_calibration_candidate import main
    from data_module import ml_storage_capacity as capacity
    from data_module import ml_historical_snapshot_provider as provider

    monkeypatch.setattr(capacity, "acquire_heavy_chain_reservation", lambda path: None)
    monkeypatch.setattr(provider, "MLHistoricalSnapshotProvider", lambda *a: pytest.fail("busy before source read"))
    monkeypatch.setattr(DailyRecommendationLearningRunner, "run", lambda *a, **k: pytest.fail("busy before fit"))
    assert main(_central_rebuild_args(tmp_path) + ["--execute"]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "heavy_chain_busy"
    assert not (tmp_path / "new-version").exists()


def test_central_rebuild_scratch_failure_releases_reservation(tmp_path, monkeypatch):
    from scripts.scheduled.rebuild_personal_calibration_candidate import main
    from data_module import ml_storage_capacity as capacity

    reservation = object()
    released = []
    monkeypatch.setattr(capacity, "acquire_heavy_chain_reservation", lambda path: reservation)
    monkeypatch.setattr(capacity, "release_heavy_chain_reservation", released.append)
    original_mkdir = Path.mkdir

    def fail_scratch(path, *args, **kwargs):
        if path.name == "temporary":
            raise OSError("synthetic scratch unavailable")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_scratch)
    with pytest.raises(OSError, match="synthetic scratch unavailable"):
        main(_central_rebuild_args(tmp_path) + ["--execute"])
    assert released == [reservation]
    assert not (tmp_path / "new-version").exists()
