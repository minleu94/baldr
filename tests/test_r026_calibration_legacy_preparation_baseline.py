from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app_module.dtos import RecommendationDTO
from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationProjection,
)
from app_module.recommendation_service import RecommendationService
from data_module.ml_historical_snapshot_provider import (
    HistoricalRawSnapshot,
    MLHistoricalSnapshotReadLease,
    MLHistoricalSnapshotProvider,
)
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_feature_builder import HistoricalFeatureBuilder
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenario,
    build_legacy_cost_scenario,
)
from ml_module.recommendation_inference_provenance import RecommendationProvenanceError
from recommendation_test_support import build_recommendation_test_service


_EXPECTED_FEATURE_IDS = (
    "stock_return_1d_bp",
    "stock_return_5d_bp",
    "stock_return_20d_bp",
    "stock_return_60d_bp",
    "trailing_volatility_20d_bp",
    "high_low_range_20d_bp",
    "close_to_ma_5d_bp",
    "close_to_ma_20d_bp",
    "close_to_ma_60d_bp",
    "rsi_normalized_bp",
    "adx_normalized_bp",
    "macd_normalized_bp",
    "volume_ratio_5d_bp",
    "volume_ratio_20d_bp",
    "turnover_amount_minor",
    "market_return_5d_bp",
    "market_return_20d_bp",
    "market_return_60d_bp",
    "stock_minus_market_20d_bp",
    "industry_relative_return_20d_bp",
)

_EXPECTED_VALUES = {
    "AAA": (
        84, 435, 2000, None, 5, 2100, 169, 860, None, 2000,
        3000, 1667, 10020, 10094, 12000, 5, 20, None, 1980, None,
    ),
    "BBB": (
        145, 769, 4000, None, 17, 3960, 294, 1570, None, 6000,
        3000, 2857, 10039, 10186, 14000, 5, 20, None, 3980, None,
    ),
}


def _make_synthetic_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
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
            CREATE TABLE market_indices (日期 TEXT, 收盤指數 TEXT, 收盤價 TEXT);
            CREATE TABLE industry_indices (日期 TEXT, 指數名稱 TEXT, 收盤指數 TEXT);
            """
        )
        first_day = date(2024, 1, 1)
        for offset in range(25):
            day = (first_day + timedelta(days=offset)).strftime("%Y%m%d")
            for symbol, multiplier in (("AAA", 1), ("BBB", 2)):
                close = 100 + offset * multiplier
                connection.execute(
                    "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        day,
                        symbol,
                        1000 + offset * multiplier,
                        close * 100,
                        str(close),
                        str(close + 1),
                        str(close - 1),
                        str(close),
                    ),
                )
                connection.execute(
                    "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)",
                    (day, symbol, str(40 + offset * multiplier), str(offset * multiplier), str(10 + offset)),
                )
            connection.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?)",
                (day, str(10_000 + offset), str(10_000 + offset)),
            )
        connection.commit()
    finally:
        connection.close()


class _RecordingConsumer:
    feature_schema = CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema
    feature_registry_hash = CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash

    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self.calls = calls
        self.pointer_path: Path | None = None
        self.resolved_identity: dict[str, str] | None = None
        self.resolved_cost_scenario: RecommendationCostScenario = (
            build_legacy_cost_scenario(50)
        )

    def active_identity(self, *, decision_date: str) -> dict[str, str]:
        self.calls.append(("active_identity", decision_date))
        self.resolved_identity = {
            "candidate_id": "synthetic-candidate-2024-01-22",
            "pointer_version": "synthetic-pointer-v1",
            "cost_scenario_hash": self.resolved_cost_scenario.scenario_hash,
        }
        return dict(self.resolved_identity)

    def active_cost_scenario(
        self, *, decision_date: str
    ) -> RecommendationCostScenario:
        self.calls.append(("active_cost_scenario", decision_date))
        return self.resolved_cost_scenario

    def active_after_cost_baseline(self, *, decision_date: str) -> tuple[str, int]:
        self.calls.append(("active_after_cost_baseline", decision_date))
        return "after_cost_null_benchmark_50pct_v1", 5_000

    def project_many(self, **kwargs: Any) -> dict[str, RecommendationCalibrationProjection]:
        self.calls.append(("project_many", kwargs))
        return {
            symbol: RecommendationCalibrationProjection.unavailable(
                stock_code=symbol,
                warning="synthetic_rule_only_baseline",
            )
            for symbol in kwargs["rule_probability_by_symbol"]
        }


def _recommendations() -> list[RecommendationDTO]:
    return [
        RecommendationDTO(
            stock_code=symbol,
            stock_name=f"合成股票{symbol}",
            close_price=Decimal("100"),
            price_change=Decimal("0"),
            total_score=Decimal("80"),
            indicator_score=Decimal("80"),
            pattern_score=Decimal("80"),
            volume_score=Decimal("80"),
            recommendation_reasons="合成舊規則結果",
            industry="",
            regime_match=True,
        )
        for symbol in ("BBB", "AAA")
    ]


def _service(tmp_path: Path, calls: list[tuple[str, Any]]) -> tuple[Any, _RecordingConsumer]:
    database = tmp_path / "source" / "synthetic.sqlite"
    _make_synthetic_database(database)
    consumer = _RecordingConsumer(calls)
    config = SimpleNamespace(
        db_file=database,
        default_start_date="2024-01-01",
        output_root=tmp_path / "output",
        data_root=tmp_path / "data",
    )
    service = build_recommendation_test_service(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )
    return service, consumer


def test_legacy_preparation_freezes_t1_features_hashes_identity_and_call_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, Any]] = []
    service, consumer = _service(tmp_path, calls)
    snapshots: list[HistoricalRawSnapshot] = []
    computed_rows: list[Any] = []

    original_enter = MLHistoricalSnapshotReadLease.__enter__
    original_load = MLHistoricalSnapshotReadLease.load
    original_assert_unchanged = MLHistoricalSnapshotReadLease.assert_unchanged
    original_exit = MLHistoricalSnapshotReadLease.__exit__

    def recording_enter(self: MLHistoricalSnapshotReadLease):
        lease = original_enter(self)
        calls.append(("lease.open", None))
        return lease

    def recording_load(
        self: MLHistoricalSnapshotReadLease, **kwargs: Any
    ) -> HistoricalRawSnapshot:
        calls.append(("provider.load", dict(kwargs)))
        snapshot = original_load(self, **kwargs)
        snapshots.append(snapshot)
        return snapshot

    def recording_assert_unchanged(self: MLHistoricalSnapshotReadLease) -> None:
        calls.append(("lease.assert_unchanged", None))
        original_assert_unchanged(self)

    def recording_exit(
        self: MLHistoricalSnapshotReadLease,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        original_exit(self, exc_type, exc, traceback)
        calls.append(("lease.close", None))

    original_compute = HistoricalFeatureBuilder.compute

    def recording_compute(
        self: HistoricalFeatureBuilder,
        snapshot: HistoricalRawSnapshot,
        **kwargs: Any,
    ):
        calls.append(("feature_builder.compute", snapshot.feature_as_of_date))
        rows = original_compute(self, snapshot, **kwargs)
        computed_rows.extend(rows)
        return rows

    def record_receipt_attempt(**kwargs: Any) -> None:
        calls.append(
            (
                "receipt_attempt",
                kwargs["decision_date"],
                tuple(kwargs["projections"]),
                dict(kwargs["active_identity"]),
            )
        )
        return None

    monkeypatch.setattr(MLHistoricalSnapshotReadLease, "__enter__", recording_enter)
    monkeypatch.setattr(MLHistoricalSnapshotReadLease, "load", recording_load)
    monkeypatch.setattr(
        MLHistoricalSnapshotReadLease, "assert_unchanged", recording_assert_unchanged
    )
    monkeypatch.setattr(MLHistoricalSnapshotReadLease, "__exit__", recording_exit)
    monkeypatch.setattr(HistoricalFeatureBuilder, "compute", recording_compute)
    monkeypatch.setattr(
        RecommendationService,
        "_persist_calibration_projection_receipt",
        staticmethod(record_receipt_attempt),
    )
    recommendations = _recommendations()

    service._apply_recommendation_calibration(recommendations, decision_date="2024-01-22")

    assert [entry[0] for entry in calls] == [
        "lease.open",
        "provider.load",
        "feature_builder.compute",
        "active_identity",
        "active_cost_scenario",
        "active_after_cost_baseline",
        "project_many",
        "lease.assert_unchanged",
        "lease.close",
        "receipt_attempt",
    ]
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.decision_date == "2024-01-22"
    assert snapshot.feature_as_of_date == "2024-01-21"
    assert snapshot.query_count == 5
    assert tuple(snapshot.source_tables) == (
        "daily_prices",
        "technical_indicators",
        "market_indices",
        "industry_indices",
    )
    assert all(row.trading_date <= snapshot.feature_as_of_date for row in snapshot.prices)
    assert all(row.trading_date <= snapshot.feature_as_of_date for row in snapshot.technicals)
    assert all(row.trading_date <= snapshot.feature_as_of_date for row in snapshot.market)
    assert {row.trading_date for row in snapshot.prices} == {
        (date(2024, 1, 1) + timedelta(days=offset)).isoformat()
        for offset in range(21)
    }
    assert tuple(row.symbol for row in computed_rows) == ("AAA", "BBB")
    assert all(row.decision_date == "2024-01-22" for row in computed_rows)
    assert all(row.feature_as_of_date == "2024-01-21" for row in computed_rows)
    assert all(row.available_date == "2024-01-22" for row in computed_rows)
    assert tuple(CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids) == _EXPECTED_FEATURE_IDS
    assert tuple(CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_dtypes) == ("int",) * 20
    assert tuple(row.values for row in computed_rows) == tuple(
        tuple(zip(_EXPECTED_FEATURE_IDS, _EXPECTED_VALUES[symbol]))
        for symbol in ("AAA", "BBB")
    )

    projection_call = next(kwargs for name, kwargs in calls if name == "project_many")
    assert tuple(projection_call["feature_values_by_symbol"]) == ("AAA", "BBB")
    assert projection_call["feature_values_by_symbol"] == _EXPECTED_VALUES
    assert tuple(projection_call["rule_probability_by_symbol"]) == ("BBB", "AAA")
    assert projection_call["rule_probability_by_symbol"] == {"BBB": 5_000, "AAA": 5_000}
    assert projection_call["after_cost_rule_probability_by_symbol"] == {
        "BBB": 5_000,
        "AAA": 5_000,
    }
    assert projection_call["after_cost_rule_baseline_id_by_symbol"] == {
        "BBB": "after_cost_null_benchmark_50pct_v1",
        "AAA": "after_cost_null_benchmark_50pct_v1",
    }

    provenance = projection_call["inference_provenance"]
    assert provenance["decision_date"] == "2024-01-22"
    assert provenance["feature_as_of_date"] == "2024-01-21"
    assert provenance["symbols"] == ["AAA", "BBB"]
    assert provenance["feature_registry_hash"] == (
        "sha256:1a2adbeee4aa4a3935be1e30bf31bfbc6136a8fa84d975a1429e5fee4326e4b6"
    )
    assert provenance["feature_builder_schema_hash"] == (
        "sha256:6584386cf16161c8cbd3a70b9f8b2143ba7e3d49d6081b1eb46fec7e9194f5be"
    )
    assert provenance["source_contract_status"] == "not_supplied"
    assert provenance["raw_snapshot_content_sha256"] == (
        "sha256:19957d62a1770ea5659520c536506035b042c64c65df69267460066b8c191c0d"
    )
    assert provenance["feature_rows_sha256"] == (
        "sha256:db22ca1fc85c72ae91d2858ef9daed6453a4b1f9e3079a9f01f66a60ee8bd17f"
    )
    assert provenance["feature_snapshot_fingerprint"] == (
        "sha256:9bc0e5bd47f18995e4ce8fd0dbed2a829442ccc23ddcb2c49e64e8043ce1d572"
    )
    assert provenance["source_fingerprint"] == snapshot.source_fingerprint
    assert provenance["cost_scenario_hash"] == (
        "sha256:1e50e15cf30f3bd25f1a142f264d9755fed486fee234c9c794d5534122906d5e"
    )
    expected_schema = tuple(
        (
            feature_id,
            "int",
            "minor_currency_unit" if feature_id == "turnover_amount_minor" else "bp",
        )
        for feature_id in _EXPECTED_FEATURE_IDS
    )
    assert tuple(
        tuple(item)
        for item in provenance["feature_transform_contract"]["canonical_schema"]
    ) == expected_schema
    assert provenance["source_fingerprint"].startswith("sha256:")
    assert provenance["source_fingerprint"] not in {
        provenance["raw_snapshot_content_sha256"],
        provenance["feature_rows_sha256"],
        provenance["feature_snapshot_fingerprint"],
    }
    assert [row["symbol"] for row in provenance["feature_rows"]] == ["AAA", "BBB"]
    assert [tuple(row["feature_ids"]) for row in provenance["feature_rows"]] == [
        _EXPECTED_FEATURE_IDS,
        _EXPECTED_FEATURE_IDS,
    ]
    assert [tuple(row["feature_values"]) for row in provenance["feature_rows"]] == [
        _EXPECTED_VALUES["AAA"],
        _EXPECTED_VALUES["BBB"],
    ]
    assert all(
        value is None or type(value) is int
        for row in provenance["feature_rows"]
        for value in row["feature_values"]
    )
    expected_missing = (
        "stock_return_60d_bp",
        "close_to_ma_60d_bp",
        "market_return_60d_bp",
        "industry_relative_return_20d_bp",
    )
    assert [
        tuple(
            feature_id
            for feature_id, value in zip(row["feature_ids"], row["feature_values"])
            if value is None
        )
        for row in provenance["feature_rows"]
    ] == [expected_missing, expected_missing]
    assert [row["snapshot_hash"] for row in provenance["feature_rows"]] == ["", ""]
    assert consumer.resolved_identity == {
        "candidate_id": "synthetic-candidate-2024-01-22",
        "pointer_version": "synthetic-pointer-v1",
        "cost_scenario_hash": (
            "sha256:1e50e15cf30f3bd25f1a142f264d9755fed486fee234c9c794d5534122906d5e"
        ),
    }
    assert consumer.resolved_cost_scenario is not None
    assert consumer.resolved_cost_scenario.scenario_id == "legacy-fixed-round-trip-bp"
    assert consumer.resolved_cost_scenario.scenario_version == "legacy-fixed-round-trip-bp-v1"
    assert calls[-1][3]["candidate_id"] == "synthetic-candidate-2024-01-22"
    assert tuple(item.stock_code for item in recommendations) == ("BBB", "AAA")
    assert service.last_calibration_projections.keys() == {"BBB", "AAA"}
    assert all(item.calibration_status == "rule_only" for item in recommendations)
    assert [item.total_score for item in recommendations] == [Decimal("80"), Decimal("80")]


@pytest.mark.parametrize(
    ("mutation_date", "mutation_affects_captured_window"),
    (
        ("20240121", True),
        ("20240123", False),
    ),
    ids=("already-read-row", "future-row"),
)
def test_live_source_update_after_snapshot_load_fails_closed_before_receipt_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation_date: str,
    mutation_affects_captured_window: bool,
) -> None:
    calls: list[tuple[str, Any]] = []
    service, _consumer = _service(tmp_path, calls)
    database = Path(service.config.db_file)
    snapshots: list[HistoricalRawSnapshot] = []
    computed_rows: list[Any] = []
    source_stat_at_snapshot: list[tuple[int, int]] = []
    mutation_observations: list[tuple[tuple[int, int], tuple[int, int]]] = []
    receipt_attempts: list[dict[str, Any]] = []

    original_enter = MLHistoricalSnapshotReadLease.__enter__
    original_load = MLHistoricalSnapshotReadLease.load
    original_assert_unchanged = MLHistoricalSnapshotReadLease.assert_unchanged
    original_exit = MLHistoricalSnapshotReadLease.__exit__

    def recording_enter(self: MLHistoricalSnapshotReadLease):
        lease = original_enter(self)
        calls.append(("lease.open", None))
        return lease

    def recording_load(
        self: MLHistoricalSnapshotReadLease, **kwargs: Any
    ) -> HistoricalRawSnapshot:
        calls.append(("provider.load", dict(kwargs)))
        before = database.stat()
        snapshot = original_load(self, **kwargs)
        after = database.stat()
        snapshots.append(snapshot)
        source_stat_at_snapshot.append((before.st_size, before.st_mtime_ns))
        assert (after.st_size, after.st_mtime_ns) == (
            before.st_size,
            before.st_mtime_ns,
        )
        return snapshot

    def recording_assert_unchanged(self: MLHistoricalSnapshotReadLease) -> None:
        calls.append(("lease.assert_unchanged", None))
        original_assert_unchanged(self)

    def recording_exit(
        self: MLHistoricalSnapshotReadLease,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        original_exit(self, exc_type, exc, traceback)
        calls.append(("lease.close", None))

    original_compute = HistoricalFeatureBuilder.compute

    def update_source_then_compute(
        self: HistoricalFeatureBuilder,
        snapshot: HistoricalRawSnapshot,
        **kwargs: Any,
    ) -> list[Any]:
        calls.append(("feature_builder.compute", snapshot.feature_as_of_date))
        before = database.stat()
        connection = sqlite3.connect(database)
        try:
            cursor = connection.execute(
                'UPDATE daily_prices SET "收盤價" = ? '
                'WHERE "日期" = ? AND "證券代號" = ?',
                ("99999", mutation_date, "AAA"),
            )
            assert cursor.rowcount == 1
            connection.commit()
        finally:
            connection.close()
        after = database.stat()
        mutation_observations.append(
            ((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))
        )
        rows = original_compute(self, snapshot, **kwargs)
        computed_rows.extend(rows)
        return rows

    def record_receipt_attempt(**kwargs: Any) -> None:
        calls.append(
            (
                "receipt_attempt",
                kwargs["decision_date"],
                tuple(kwargs["projections"]),
                dict(kwargs["active_identity"]),
            )
        )
        receipt_attempts.append(dict(kwargs))

    monkeypatch.setattr(MLHistoricalSnapshotReadLease, "__enter__", recording_enter)
    monkeypatch.setattr(MLHistoricalSnapshotReadLease, "load", recording_load)
    monkeypatch.setattr(
        MLHistoricalSnapshotReadLease, "assert_unchanged", recording_assert_unchanged
    )
    monkeypatch.setattr(MLHistoricalSnapshotReadLease, "__exit__", recording_exit)
    monkeypatch.setattr(HistoricalFeatureBuilder, "compute", update_source_then_compute)
    monkeypatch.setattr(
        RecommendationService,
        "_persist_calibration_projection_receipt",
        staticmethod(record_receipt_attempt),
    )

    recommendations = _recommendations()
    service._apply_recommendation_calibration(
        recommendations, decision_date="2024-01-22"
    )

    assert [entry[0] for entry in calls][:3] == [
        "lease.open",
        "provider.load",
        "feature_builder.compute",
    ]
    assert calls[-1][0] == "lease.close"
    assert "receipt_attempt" not in [entry[0] for entry in calls]
    assert len(snapshots) == 1
    captured_snapshot = snapshots[0]
    assert captured_snapshot.feature_as_of_date == "2024-01-21"
    assert source_stat_at_snapshot == [mutation_observations[0][0]]
    assert len(mutation_observations) == 1
    before_stat, after_stat = mutation_observations[0]

    current_snapshot = MLHistoricalSnapshotProvider(database).load(
        decision_date="2024-01-22",
        history_start_date="2024-01-01",
        symbols=("AAA", "BBB"),
        industry_index_names=(),
    )
    assert current_snapshot.feature_as_of_date == captured_snapshot.feature_as_of_date
    metadata_changed = before_stat != after_stat
    assert (current_snapshot.source_fingerprint != captured_snapshot.source_fingerprint) == (
        metadata_changed
    )
    (tmp_path / "source_update_metadata_observation.txt").write_text(
        f"mutation_date={mutation_date}\n"
        f"before_stat={before_stat!r}\n"
        f"after_stat={after_stat!r}\n"
        f"metadata_changed={metadata_changed}\n"
        "source_fingerprint_changed="
        f"{current_snapshot.source_fingerprint != captured_snapshot.source_fingerprint}\n",
        encoding="utf-8",
    )
    current_rows = original_compute(
        HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY),
        current_snapshot,
        industry_index_name_by_symbol={},
    )
    current_values = {
        row.symbol: tuple(value for _, value in row.values) for row in current_rows
    }
    if mutation_affects_captured_window:
        captured_close = next(
            row.close_price
            for row in captured_snapshot.prices
            if row.symbol == "AAA" and row.trading_date == "2024-01-21"
        )
        current_close = next(
            row.close_price
            for row in current_snapshot.prices
            if row.symbol == "AAA" and row.trading_date == "2024-01-21"
        )
        assert captured_close == Decimal("120")
        assert current_close == Decimal("99999")
        assert current_values["AAA"] != _EXPECTED_VALUES["AAA"]
        assert current_values["BBB"] == _EXPECTED_VALUES["BBB"]
    else:
        assert all(
            row.trading_date != "2024-01-23"
            for row in captured_snapshot.prices
            if row.symbol == "AAA"
        )
        assert all(
            row.trading_date != "2024-01-23"
            for row in current_snapshot.prices
            if row.symbol == "AAA"
        )
        assert current_values == _EXPECTED_VALUES

    assert tuple(row.values for row in computed_rows) == tuple(
        tuple(zip(_EXPECTED_FEATURE_IDS, _EXPECTED_VALUES[symbol]))
        for symbol in ("AAA", "BBB")
    )
    project_calls = [entry for entry in calls if entry[0] == "project_many"]
    assert len(project_calls) == 1
    call_names = [entry[0] for entry in calls]
    assert call_names.index("project_many") < call_names.index("lease.assert_unchanged")
    assert receipt_attempts == []
    assert service.last_calibration_projections == {}
    assert service.last_run_context["calibration_projection_status"] == "unavailable"
    assert "calibration_projection_rows" not in service.last_run_context
    assert all(item.calibration_status == "unavailable" for item in recommendations)
    assert all(item.calibrated_probability_bp is None for item in recommendations)
    assert all(item.calibration_model_version == "" for item in recommendations)
    assert [item.total_score for item in recommendations] == [Decimal("80"), Decimal("80")]


def test_live_source_update_during_project_many_discards_projection_and_skips_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, Any]] = []
    service, consumer = _service(tmp_path, calls)
    database = Path(service.config.db_file)
    receipt_attempts: list[dict[str, Any]] = []
    original_enter = MLHistoricalSnapshotReadLease.__enter__
    original_assert_unchanged = MLHistoricalSnapshotReadLease.assert_unchanged
    original_exit = MLHistoricalSnapshotReadLease.__exit__
    lease_closed: list[bool] = []

    def recording_enter(self: MLHistoricalSnapshotReadLease):
        lease = original_enter(self)
        calls.append(("lease.open", None))
        return lease

    def recording_assert_unchanged(self: MLHistoricalSnapshotReadLease) -> None:
        calls.append(("lease.assert_unchanged", None))
        original_assert_unchanged(self)

    def recording_exit(
        self: MLHistoricalSnapshotReadLease,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        original_exit(self, exc_type, exc, traceback)
        lease_closed.append(True)
        calls.append(("lease.close", None))

    def project_and_mutate(**kwargs: Any) -> dict[str, RecommendationCalibrationProjection]:
        calls.append(("project_many", kwargs))
        connection = sqlite3.connect(database)
        try:
            cursor = connection.execute(
                'UPDATE daily_prices SET "收盤價" = ? '
                'WHERE "日期" = ? AND "證券代號" = ?',
                ("77777", "20240120", "AAA"),
            )
            assert cursor.rowcount == 1
            connection.commit()
        finally:
            connection.close()
        return {
            symbol: replace(
                RecommendationCalibrationProjection.unavailable(
                    stock_code=symbol,
                    warning="synthetic projection before lease check",
                ),
                status="active_candidate",
                ranking_score_bp=7_200,
                calibrated_probability_bp=5_800,
                calibrated_probability_status="shadow_candidate",
                after_cost_profit_probability_bp=5_700,
                after_cost_profit_probability_status="shadow_candidate",
                evidence_confidence="shadow_candidate",
                sample_size=120,
                model_version="candidate-model-1",
                dataset_version="dataset-1",
                warnings=(),
            )
            for symbol in kwargs["rule_probability_by_symbol"]
        }

    def record_receipt_attempt(**kwargs: Any) -> None:
        receipt_attempts.append(dict(kwargs))

    monkeypatch.setattr(MLHistoricalSnapshotReadLease, "__enter__", recording_enter)
    monkeypatch.setattr(
        MLHistoricalSnapshotReadLease, "assert_unchanged", recording_assert_unchanged
    )
    monkeypatch.setattr(MLHistoricalSnapshotReadLease, "__exit__", recording_exit)
    monkeypatch.setattr(
        _RecordingConsumer,
        "project_many",
        lambda self, **kwargs: project_and_mutate(**kwargs),
    )
    monkeypatch.setattr(
        RecommendationService,
        "_persist_calibration_projection_receipt",
        staticmethod(record_receipt_attempt),
    )

    recommendations = _recommendations()
    for recommendation in recommendations:
        recommendation.ranking_score_bp = 7_200
        recommendation.calibrated_probability_bp = 5_800
        recommendation.calibrated_probability_status = "shadow_candidate"
        recommendation.calibration_model_version = "stale-candidate"
        recommendation.calibration_provenance = {"model_version": "stale-candidate"}
    service.last_run_context.update(
        {
            "calibration_projection_rows": {"STALE": {"model_version": "stale-candidate"}},
            "calibration_projection_receipt": {"path": "stale-receipt"},
        }
    )
    service._apply_recommendation_calibration(
        recommendations, decision_date="2024-01-22"
    )

    call_names = [name for name, _ in calls]
    assert call_names.index("lease.open") < call_names.index("project_many")
    assert call_names.index("project_many") < call_names.index("lease.assert_unchanged")
    assert call_names.index("lease.assert_unchanged") < call_names.index("lease.close")
    assert "receipt_attempt" not in call_names
    assert receipt_attempts == []
    assert lease_closed == [True]
    assert service.last_calibration_projections == {}
    assert service.last_run_context["calibration_projection_status"] == "unavailable"
    assert "calibration_projection_rows" not in service.last_run_context
    assert all(item.calibration_status == "unavailable" for item in recommendations)
    assert all(item.calibrated_probability_bp is None for item in recommendations)
    assert all(item.ranking_score_bp is None for item in recommendations)
    assert all(item.calibration_model_version == "" for item in recommendations)
    assert all(item.calibration_provenance == {} for item in recommendations)
    assert "calibration_projection_receipt" not in service.last_run_context
    assert [item.total_score for item in recommendations] == [Decimal("80"), Decimal("80")]


@pytest.mark.parametrize(
    "journal_mode",
    ("delete", "wal"),
    ids=("delete-writer-blocked", "wal-writer-commits-reader-rejects"),
)
def test_provider_load_pins_query_window_and_rejects_concurrent_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    journal_mode: str,
) -> None:
    database = tmp_path / "query-window-source.db"
    _make_synthetic_database(database)
    setup = sqlite3.connect(database)
    try:
        mode_row = setup.execute(f"PRAGMA journal_mode={journal_mode}").fetchone()
        assert mode_row is not None
        assert str(mode_row[0]).lower() == journal_mode
        if journal_mode == "wal":
            setup.execute("PRAGMA wal_autocheckpoint=0")
    finally:
        setup.close()
    provider = MLHistoricalSnapshotProvider(database)
    source_stat_before = database.stat()
    query_order: list[str] = []
    query_rows: dict[str, list[tuple[Any, ...]]] = {}
    update_stats: list[tuple[tuple[int, int], tuple[int, int]]] = []
    reader_journal_modes: list[str] = []
    writer_journal_modes: list[str] = []
    reader_transaction_states: list[bool] = []
    writer_transaction_states: list[bool] = []
    writer_commit_outcomes: list[str] = []
    reader_events: list[str] = []
    updated = False

    def update_source_between_price_and_technical_queries() -> None:
        nonlocal updated
        assert not updated
        before = database.stat()
        assert (before.st_size, before.st_mtime_ns) == (
            source_stat_before.st_size,
            source_stat_before.st_mtime_ns,
        )
        writer = sqlite3.connect(database, timeout=0)
        try:
            journal_mode = writer.execute("PRAGMA journal_mode").fetchone()
            assert journal_mode is not None
            writer_journal_modes.append(str(journal_mode[0]).lower())
            if str(journal_mode[0]).lower() == "wal":
                writer.execute("PRAGMA wal_autocheckpoint=0")
            price_cursor = writer.execute(
                'UPDATE daily_prices SET "收盤價" = ? '
                'WHERE "日期" = ? AND "證券代號" = ?',
                ("999", "20240121", "AAA"),
            )
            technical_cursor = writer.execute(
                'UPDATE technical_indicators SET "RSI" = ? '
                'WHERE "日期" = ? AND "證券代號" = ?',
                ("99", "20240121", "AAA"),
            )
            assert price_cursor.rowcount == 1
            assert technical_cursor.rowcount == 1
            writer_transaction_states.append(writer.in_transaction)
            try:
                writer.commit()
            except sqlite3.OperationalError as exc:
                writer_commit_outcomes.append(f"blocked:{exc}")
                if journal_mode[0].lower() != "delete" or "locked" not in str(exc).lower():
                    raise
                writer_transaction_states.append(writer.in_transaction)
                writer.rollback()
                writer_transaction_states.append(writer.in_transaction)
            else:
                writer_commit_outcomes.append("committed")
                writer_transaction_states.append(writer.in_transaction)
        finally:
            writer.close()

        after = database.stat()
        update_stats.append(
            (
                (before.st_size, before.st_mtime_ns),
                (after.st_size, after.st_mtime_ns),
            )
        )
        updated = True

    class _RecordingCursor:
        def __init__(self, cursor: Any, label: str | None) -> None:
            self._cursor = cursor
            self._label = label

        def _record(self, row: Any) -> None:
            if self._label is not None:
                query_rows.setdefault(self._label, []).append(tuple(row))

        def __iter__(self) -> Any:
            for row in self._cursor:
                self._record(row)
                yield row

        def fetchone(self) -> Any:
            row = self._cursor.fetchone()
            if row is not None:
                self._record(row)
            return row

        def fetchall(self) -> list[Any]:
            rows = self._cursor.fetchall()
            for row in rows:
                self._record(row)
            return rows

    class _InterleavingConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
            assert journal_mode is not None
            reader_journal_modes.append(str(journal_mode[0]).lower())

        def __getattr__(self, name: str) -> Any:
            return getattr(self._connection, name)

        def execute(self, statement: str, parameters: Any = ()) -> _RecordingCursor:
            normalized = " ".join(statement.lower().split())
            label: str | None = None
            if normalized == "pragma data_version":
                reader_events.append("data_version")
            elif normalized == "begin":
                reader_events.append("begin")
            if "select max(" in normalized and "from daily_prices" in normalized:
                label = "cutoff"
            elif "select name from sqlite_master" in normalized:
                reader_events.append("schema")
            elif "from daily_prices" in normalized:
                label = "prices"
            elif "from technical_indicators" in normalized:
                label = "technicals"
            elif "from market_indices" in normalized:
                label = "market"
            elif "from industry_indices" in normalized:
                label = "industries"

            if label == "technicals" and not updated:
                reader_transaction_states.append(self._connection.in_transaction)
                query_order.append("writer_update")
                update_source_between_price_and_technical_queries()
            if label is not None:
                query_order.append(label)
            return _RecordingCursor(
                self._connection.execute(statement, parameters), label
            )

        def close(self) -> None:
            self._connection.close()

    original_connect = provider._connect
    monkeypatch.setattr(
        provider,
        "_connect",
        lambda: _InterleavingConnection(original_connect()),
    )

    load_kwargs = {
        "decision_date": "2024-01-22",
        "history_start_date": "2024-01-01",
        "symbols": ("AAA", "BBB"),
        "industry_index_names": ("SYNTHETIC INDUSTRY",),
    }
    if journal_mode == "delete":
        snapshot = provider.load(**load_kwargs)
    else:
        with pytest.raises(
            RuntimeError,
            match="historical SQLite source changed during snapshot load",
        ):
            provider.load(**load_kwargs)
        snapshot = None

    assert updated
    assert reader_journal_modes == [journal_mode]
    assert writer_journal_modes == [journal_mode]
    assert reader_transaction_states == [True]
    assert reader_events[:3] == ["data_version", "begin", "schema"]
    assert reader_events[-1] == "data_version"
    assert writer_transaction_states == (
        [True, True, False] if journal_mode == "delete" else [True, False]
    )
    assert (
        writer_commit_outcomes[0].startswith("blocked:database is locked")
        if journal_mode == "delete"
        else writer_commit_outcomes == ["committed"]
    )
    assert query_order == [
        "cutoff",
        "prices",
        "writer_update",
        "technicals",
        "market",
        "industries",
    ]
    assert len(update_stats) == 1
    before_stat, after_stat = update_stats[0]
    assert before_stat == (source_stat_before.st_size, source_stat_before.st_mtime_ns)
    assert after_stat == before_stat

    price_query_row = next(
        row
        for row in query_rows["prices"]
        if row[0] == "AAA" and row[1] == "20240121"
    )
    technical_query_row = next(
        row
        for row in query_rows["technicals"]
        if row[0] == "AAA" and row[1] == "20240121"
    )
    assert price_query_row[7] == "120"
    assert technical_query_row[2] == "60"

    if journal_mode == "delete":
        assert snapshot is not None
        assert snapshot.query_count == 5
        captured_price = next(
            row
            for row in snapshot.prices
            if row.symbol == "AAA" and row.trading_date == "2024-01-21"
        )
        captured_technical = next(
            row
            for row in snapshot.technicals
            if row.symbol == "AAA" and row.trading_date == "2024-01-21"
        )
        assert captured_price.close_price == Decimal("120")
        assert captured_technical.rsi == Decimal("60")
        fresh_snapshot = MLHistoricalSnapshotProvider(database).load(**load_kwargs)
        fresh_price = next(
            row
            for row in fresh_snapshot.prices
            if row.symbol == "AAA" and row.trading_date == "2024-01-21"
        )
        fresh_technical = next(
            row
            for row in fresh_snapshot.technicals
            if row.symbol == "AAA" and row.trading_date == "2024-01-21"
        )
        assert fresh_price.close_price == Decimal("120")
        assert fresh_technical.rsi == Decimal("60")
        assert snapshot.prices == fresh_snapshot.prices
        assert snapshot.source_fingerprint == fresh_snapshot.source_fingerprint
    else:
        assert snapshot is None
        fresh_snapshot = MLHistoricalSnapshotProvider(database).load(**load_kwargs)
        fresh_price = next(
            row
            for row in fresh_snapshot.prices
            if row.symbol == "AAA" and row.trading_date == "2024-01-21"
        )
        fresh_technical = next(
            row
            for row in fresh_snapshot.technicals
            if row.symbol == "AAA" and row.trading_date == "2024-01-21"
        )
        assert fresh_price.close_price == Decimal("999")
        assert fresh_technical.rsi == Decimal("99")

    outcome = "delete_writer_commit_blocked" if journal_mode == "delete" else "wal_commit_detected"
    (tmp_path / "query_window_interleave_evidence.txt").write_text(
        f"outcome={outcome}\n"
        "query_order=cutoff,prices,writer_update,technicals,market,industries\n"
        f"source_stat_before={source_stat_before.st_size},{source_stat_before.st_mtime_ns}\n"
        f"source_stat_after_update={after_stat[0]},{after_stat[1]}\n"
        f"reader_journal_mode={reader_journal_modes[0]}\n"
        f"writer_journal_mode={writer_journal_modes[0]}\n"
        f"reader_in_transaction_before_technical={reader_transaction_states[0]}\n"
        f"writer_transaction_states={writer_transaction_states!r}\n"
        f"writer_commit_outcomes={writer_commit_outcomes!r}\n"
        f"price_close_seen_by_prices_query={price_query_row[7]}\n"
        f"rsi_seen_by_technicals_query={technical_query_row[2]}\n"
        f"returned_snapshot={snapshot is not None}\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("entry", ("load", "load_forward_price_window"))
def test_provider_detects_commit_between_version_baseline_and_revision_precheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> None:
    from data_module import ml_historical_snapshot_provider as provider_module

    database = tmp_path / f"precheck-race-{entry}.db"
    _make_synthetic_database(database)
    setup = sqlite3.connect(database)
    try:
        mode_row = setup.execute("PRAGMA journal_mode=wal").fetchone()
        assert mode_row is not None and str(mode_row[0]).lower() == "wal"
        setup.execute("PRAGMA wal_autocheckpoint=0")
    finally:
        setup.close()

    provider = MLHistoricalSnapshotProvider(database)
    raw_connect = provider._connect
    events: list[str] = []

    class _ConnectionProbe:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def __getattr__(self, name: str) -> Any:
            return getattr(self._connection, name)

        def execute(self, statement: str, parameters: Any = ()) -> Any:
            normalized = " ".join(statement.lower().split())
            if normalized == "pragma data_version":
                events.append("data_version")
            elif normalized == "begin":
                events.append("begin")
            return self._connection.execute(statement, parameters)

        def close(self) -> None:
            self._connection.close()

    monkeypatch.setattr(provider, "_connect", lambda: _ConnectionProbe(raw_connect()))
    source_stat_before = database.stat()

    def commit_source_update(**_kwargs: Any) -> None:
        events.append("revision_precheck")
        writer = sqlite3.connect(database, timeout=0)
        try:
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute(
                'UPDATE daily_prices SET "收盤價" = ? '
                'WHERE "日期" = ? AND "證券代號" = ?',
                ("999", "20240121", "AAA"),
            )
            writer.execute(
                'UPDATE technical_indicators SET "RSI" = ? '
                'WHERE "日期" = ? AND "證券代號" = ?',
                ("99", "20240121", "AAA"),
            )
            writer.commit()
        finally:
            writer.close()
        current = database.stat()
        assert current.st_size == source_stat_before.st_size
        os.utime(
            database,
            ns=(current.st_atime_ns, source_stat_before.st_mtime_ns),
        )
        restored = database.stat()
        assert (restored.st_size, restored.st_mtime_ns) == (
            source_stat_before.st_size,
            source_stat_before.st_mtime_ns,
        )

    monkeypatch.setattr(
        provider_module,
        "check_daily_price_source_revision",
        commit_source_update,
    )
    with pytest.raises(RuntimeError, match="historical SQLite source changed"):
        if entry == "load":
            provider.load(
                decision_date="2024-01-22",
                history_start_date="2024-01-01",
                symbols=("AAA", "BBB"),
            )
        else:
            provider.load_forward_price_window(
                start_date="2024-01-21",
                end_date="2024-01-22",
                symbols=("AAA", "BBB"),
            )

    assert events[:3] == ["data_version", "revision_precheck", "begin"]
    assert events[-1] == "data_version"
    assert events.count("data_version") == 2
    assert events.count("revision_precheck") == 1
    assert events.count("begin") == 1
    assert (database.stat().st_size, database.stat().st_mtime_ns) == (
        source_stat_before.st_size,
        source_stat_before.st_mtime_ns,
    )
    check = sqlite3.connect(database)
    try:
        assert check.execute(
            'SELECT "收盤價" FROM daily_prices '
            'WHERE "日期" = ? AND "證券代號" = ?',
            ("20240121", "AAA"),
        ).fetchone() == ("999",)
        assert check.execute(
            'SELECT "RSI" FROM technical_indicators '
            'WHERE "日期" = ? AND "證券代號" = ?',
            ("20240121", "AAA"),
        ).fetchone() == ("99",)
    finally:
        check.close()


@pytest.mark.parametrize(
    ("entry", "failure_stage"),
    (
        ("load", "success"),
        ("load", "precheck"),
        ("load", "schema"),
        ("list_trading_dates", "success"),
        ("list_trading_dates", "schema"),
        ("load_forward_price_window", "success"),
        ("load_forward_price_window", "precheck"),
        ("load_forward_price_window", "schema"),
    ),
)
def test_provider_public_read_entries_release_connections_on_success_and_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
    failure_stage: str,
) -> None:
    from data_module import ml_historical_snapshot_provider as provider_module

    database = tmp_path / f"lifecycle-{entry}-{failure_stage}.db"
    _make_synthetic_database(database)
    provider = MLHistoricalSnapshotProvider(database)
    raw_connect = provider._connect
    events: list[str] = []
    closed_transaction_states: list[bool] = []

    class _ConnectionProbe:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def __getattr__(self, name: str) -> Any:
            return getattr(self._connection, name)

        def execute(self, statement: str, parameters: Any = ()) -> Any:
            normalized = " ".join(statement.lower().split())
            if normalized == "pragma data_version":
                events.append("data_version")
            elif normalized == "begin":
                events.append("begin")
            return self._connection.execute(statement, parameters)

        def close(self) -> None:
            closed_transaction_states.append(self._connection.in_transaction)
            events.append("close")
            self._connection.close()

    monkeypatch.setattr(provider, "_connect", lambda: _ConnectionProbe(raw_connect()))
    if failure_stage == "precheck":
        def fail_precheck(**_kwargs: Any) -> None:
            events.append("precheck")
            raise ValueError("synthetic precheck failure")

        monkeypatch.setattr(provider_module, "check_daily_price_source_revision", fail_precheck)
    elif failure_stage == "schema":
        def fail_schema(_connection: Any) -> dict[str, tuple[str, ...]]:
            raise ValueError("synthetic schema failure")

        monkeypatch.setattr(provider, "_validate_schema", fail_schema)

    def invoke() -> Any:
        if entry == "load":
            return provider.load(
                decision_date="2024-01-22",
                history_start_date="2024-01-01",
                symbols=("AAA", "BBB"),
            )
        if entry == "list_trading_dates":
            return provider.list_trading_dates(
                start_date="2024-01-01",
                end_date="2024-01-22",
                symbols=("AAA", "BBB"),
            )
        return provider.load_forward_price_window(
            start_date="2024-01-21",
            end_date="2024-01-22",
            symbols=("AAA", "BBB"),
        )

    if failure_stage == "success":
        assert invoke() is not None
    else:
        expected = "precheck" if failure_stage == "precheck" else "schema"
        with pytest.raises(ValueError, match=f"synthetic {expected} failure"):
            invoke()

    assert closed_transaction_states == [False]
    assert events[-1] == "close"
    assert events[0] == "data_version"
    if failure_stage == "precheck":
        assert events == ["data_version", "precheck", "close"]
    else:
        assert "begin" in events
        assert events.index("begin") < events.index("close")


@pytest.mark.parametrize(
    "failure",
    (
        PermissionError("synthetic receipt write denied"),
        RecommendationProvenanceError("synthetic receipt readback mismatch"),
    ),
)
def test_receipt_write_or_readback_failure_keeps_rule_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    calls: list[tuple[str, Any]] = []
    service, consumer = _service(tmp_path, calls)
    consumer.pointer_path = tmp_path / "active-pointer.json"
    recommendations = _recommendations()
    original_scores = tuple(item.total_score for item in recommendations)

    def fail_receipt(**kwargs: Any) -> None:
        calls.append(("receipt_failure", kwargs["decision_date"], tuple(kwargs["projections"])))
        raise failure

    monkeypatch.setattr(
        RecommendationService,
        "_persist_calibration_projection_receipt",
        staticmethod(fail_receipt),
    )
    service._apply_recommendation_calibration(recommendations, decision_date="2024-01-22")

    assert [entry[0] for entry in calls] == [
        "active_identity",
        "active_cost_scenario",
        "active_after_cost_baseline",
        "project_many",
        "receipt_failure",
    ]
    assert [item.stock_code for item in recommendations] == ["BBB", "AAA"]
    assert tuple(item.total_score for item in recommendations) == original_scores
    assert all(item.calibration_status == "rule_only" for item in recommendations)
    assert all(item.calibrated_probability_bp is None for item in recommendations)
    assert service.last_run_context["calibration_projection_status"] == "unavailable"
    assert service.last_run_context["calibration_projection_receipt_status"] == "unavailable"
    assert all(
        item.calibration_provenance["projection_receipt_status"] == "not_persisted"
        for item in recommendations
    )
