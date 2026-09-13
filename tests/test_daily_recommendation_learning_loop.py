from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil
from types import SimpleNamespace
from typing import Mapping
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_recommendation_learning_runner import DailyRecommendationLearningRunner
from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationConsumer,
    RecommendationCalibrationProjection,
)
from data_module.official_trading_calendar import OfficialTradingCalendar
from ml_module.recommendation_calibration_authority import (
    RecommendationCalibrationPromotionAuthority,
    RecommendationPromotionPolicy,
)
from ml_module.recommendation_calibration_evidence import (
    ActiveModelPredictionCaptureService,
    MaturedRecommendationOutcome,
    NaturalForwardEvidenceBuilder,
    RecommendationPredictionCaptureInput,
    RecommendationPredictionCaptureService,
)
from ml_module.recommendation_natural_outcome_service import RecommendationNaturalOutcomeService
from ml_module.recommendation_calibration_training import (
    RecommendationCalibrationSample,
    RecommendationCalibrationTrainingConfig,
    RecommendationCalibrationTrainingService,
    RecommendationPrediction,
)


FEATURE_NAMES = ("momentum_bp", "volume_ratio_bp")
FEATURE_SCHEMA = (("momentum_bp", "int", "bp"), ("volume_ratio_bp", "int", "bp"))
FEATURE_REGISTRY_HASH = "sha256:" + "3" * 64


class _FixedPredictionModel:
    def __init__(self, model_id: str, probability_bp: int) -> None:
        self.model_id = model_id
        self.probability_bp = probability_bp

    def predict(self, feature_values):
        return RecommendationPrediction(
            ranking_score_bp=1,
            calibrated_probability_bp=self.probability_bp,
            after_cost_profit_probability_bp=self.probability_bp,
            calibrated_probability_status="shadow_candidate",
            after_cost_profit_probability_status="shadow_candidate",
            model_id=self.model_id,
            dataset_id=self.model_id,
            training_as_of="2026-01-01",
            horizon_trading_days=20,
            sample_size=100,
        )


def _samples(shift: int = 0) -> tuple[RecommendationCalibrationSample, ...]:
    rows: list[RecommendationCalibrationSample] = []
    start = date(2026, 1, 2)
    for day_index in range(110):
        decision = start + timedelta(days=day_index)
        for symbol_index, symbol in enumerate(("1101", "2330")):
            momentum = ((day_index % 6) - 2) * 1000 + symbol_index * 170
            stock_return = momentum + symbol_index * 120 + shift
            rows.append(
                RecommendationCalibrationSample.from_forward_return(
                    row_id=f"{decision.isoformat()}-{symbol}",
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


def _runner(
    tmp_path: Path,
    authority: RecommendationCalibrationPromotionAuthority | None = None,
    data_root: Path | None = None,
) -> DailyRecommendationLearningRunner:
    return DailyRecommendationLearningRunner(
        output_root=tmp_path,
        data_root=data_root,
        feature_names=FEATURE_NAMES,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        fixed_round_trip_cost_bp=50,
        authority=authority,
        training_config=RecommendationCalibrationTrainingConfig(
            minimum_calibration_samples=10,
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )


def _candidate(tmp_path: Path, *, shift: int, candidate_day: str) -> tuple[object, Path, dict[str, object]]:
    samples = _samples(shift)
    digest = "a" if shift == 0 else "b"
    root = tmp_path / f"candidate-{digest}"
    result = RecommendationCalibrationTrainingService().fit(
        dataset_id=f"dataset-{digest}",
        dataset_hash="sha256:" + digest * 64,
        samples=samples,
        feature_names=FEATURE_NAMES,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        training_as_of="2026-12-31",
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
    result.persist(root)
    metadata = json.loads((root / "candidate.json").read_text(encoding="utf-8"))
    return result, root, metadata


def _natural_receipt(
    tmp_path: Path,
    *,
    root: Path,
    candidate_day: str,
    evaluation_day: str,
) -> object:
    captures: list[Path] = []
    outcomes: list[MaturedRecommendationOutcome] = []
    start = date.fromisoformat(candidate_day)
    for index in range(20):
        capture_day = start + timedelta(days=index)
        capture_input = RecommendationPredictionCaptureInput(
            row_id=f"forward-{index:02d}",
            symbol="1101" if index % 2 == 0 else "2330",
            decision_date=capture_day.isoformat(),
            feature_as_of_date=(capture_day - timedelta(days=1)).isoformat(),
            feature_available_date=(capture_day - timedelta(days=1)).isoformat(),
            feature_values=(((index % 6) - 2) * 1000, 1000 + index * 10),
            rule_probability_bp=5000,
            rule_after_cost_probability_bp=5000,
        )
        capture = RecommendationPredictionCaptureService().capture(
            candidate_root=root,
            feature_schema=FEATURE_SCHEMA,
            feature_registry_hash=FEATURE_REGISTRY_HASH,
            policy_hash=RecommendationPromotionPolicy().policy_hash,
            decision_date=capture_day.isoformat(),
            captured_at=f"{capture_day.isoformat()}T09:00:00+00:00",
            inputs=(capture_input,),
            fixed_round_trip_cost_bp=50,
            data_root=tmp_path / "formal-data",
        )
        capture_path = tmp_path / "captures" / capture_day.isoformat() / f"{index:02d}.json"
        capture.persist(capture_path)
        captures.append(capture_path)
        for row in capture.rows:
            outcomes.append(
                MaturedRecommendationOutcome(
                    capture_row_id=str(row["row_id"]),
                    label_end_date=evaluation_day,
                    label_available_date=evaluation_day,
                    stock_return_bp=2000 if int(row["candidate_probability_bp"]) >= 5000 else -2000,
                    observed_liquidity_cost_bp=20,
                    benchmark_return_bp=100,
                )
            )
    return NaturalForwardEvidenceBuilder().build_many(
        captures=tuple(captures),
        outcomes=tuple(outcomes),
        evaluation_date=evaluation_day,
        output_path=tmp_path / f"natural-{candidate_day}.json",
        source_id="scheduled_forward_outcomes",
    )


def test_daily_runner_is_idempotent_and_does_not_fabricate_natural_maturity(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    first = runner.run(
        decision_date="2026-06-01",
        samples=_samples(),
        natural_evidence=None,
        drift_status="clean",
        training_as_of="2026-12-31",
    )
    second = runner.run(
        decision_date="2026-06-01",
        samples=_samples(),
        natural_evidence=None,
        drift_status="clean",
        training_as_of="2026-12-31",
    )

    assert first.status == "completed"
    assert first.decision == "retain_current"
    assert "natural_forward_evidence_receipt_missing" in first.decision_reason
    assert second.idempotent_replay is True
    assert second.candidate_id == first.candidate_id
    receipt = json.loads(
        (tmp_path / "recommendation_learning" / "runs" / "2026-06-01" / "run_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["formal_order_allowed"] is False
    assert receipt["shadow_only"] is True
    assert receipt["natural_matured_sample_count"] == 0
    assert len(list((tmp_path / "recommendation_learning" / "decisions").glob("*.json"))) == 1
    assert (tmp_path / "recommendation_learning" / "latest_status.json").is_file()


def test_daily_runner_dependency_attempt_can_recover_then_locks_success(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    failed = runner.run(
        decision_date="2026-06-01",
        samples=_samples(),
        natural_evidence=None,
        data_dependency_status="failed",
        outcome_dependency_status="failed",
        drift_status="not_checked",
    )
    assert failed.status == "failed_dependency"
    assert failed.decision == "retain_current"
    assert not (tmp_path / "recommendation_learning" / "runs" / "2026-06-01" / "run_receipt.json").exists()
    attempts = list((tmp_path / "recommendation_learning" / "runs" / "2026-06-01" / "attempts").glob("*.json"))
    assert len(attempts) == 1
    assert json.loads(attempts[0].read_text(encoding="utf-8"))["recoverable"] is True

    recovered = runner.run(
        decision_date="2026-06-01",
        samples=_samples(),
        natural_evidence=None,
        data_dependency_status="ready",
        outcome_dependency_status="ready",
        drift_status="pending",
    )
    assert recovered.status == "completed"
    assert recovered.decision == "retain_current"
    replayed = runner.run(
        decision_date="2026-06-01",
        samples=_samples(),
        natural_evidence=None,
        data_dependency_status="ready",
        outcome_dependency_status="ready",
        drift_status="pending",
    )
    assert replayed.idempotent_replay is True
    assert json.loads(
        (tmp_path / "recommendation_learning" / "runs" / "2026-06-01" / "run_receipt.json").read_text(
            encoding="utf-8"
        )
    )["finalized"] is True


def test_consumer_is_fail_closed_when_pointer_is_absent(tmp_path: Path) -> None:
    consumer = RecommendationCalibrationConsumer(
        pointer_path=tmp_path / "missing-pointer.json",
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "formal-data",
    )
    projection = consumer.project(
        stock_code="1101",
        feature_values=(100, 1000),
        rule_probability_bp=5000,
        decision_date="2026-06-01",
    )
    assert projection.status == "rule_only"
    assert projection.calibrated_probability_bp is None
    assert projection.after_cost_profit_probability_bp is None


def test_taipei_calendar_never_infers_weekend_as_a_trading_day(tmp_path: Path) -> None:
    calendar = OfficialTradingCalendar(db_path=tmp_path / "not-needed-on-weekend.db")
    is_trading_day, reason = calendar.is_official_trading_day(date(2026, 9, 13), allow_online_probe=False)
    assert is_trading_day is False
    assert reason == "weekend_closed"


def test_default_config_uses_external_shared_shadow_root_and_loader_reads_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Default config must not place learning artifacts below formal DATA_ROOT."""

    from app_module.recommendation_calibration_consumer import (
        _library_versions,
        build_default_recommendation_calibration_consumer,
    )
    from app_module.recommendation_learning_paths import resolve_recommendation_learning_paths
    from app_module.workbench_source_service import WorkbenchSourceService
    from data_module.config import TWStockConfig
    from ml_module.model_artifact_loader import ArtifactCompatibilityExpectation, SafeShadowModelArtifactLoader
    from ml_module.recommendation_calibration_training import recommendation_label_registry_hash

    monkeypatch.delenv("OUTPUT_ROOT", raising=False)
    monkeypatch.delenv("RECOMMENDATION_LEARNING_OUTPUT_ROOT", raising=False)
    config = TWStockConfig(data_root=tmp_path / "formal-data")
    paths = resolve_recommendation_learning_paths(data_root=config.data_root)

    assert paths.output_root == (tmp_path / "FA_Data_Shadow").resolve()
    assert config.data_root.resolve() not in paths.output_root.parents
    assert paths.output_root != config.output_root.resolve()

    runner = _runner(paths.output_root, data_root=config.data_root)
    result = runner.run(
        decision_date="2026-06-01",
        samples=_samples(),
        natural_evidence=None,
        data_dependency_status="ready",
        outcome_dependency_status="ready",
        drift_status="not_checked",
    )
    assert result.candidate_root is not None
    candidate_root = Path(result.candidate_root)
    manifest_payload = json.loads((candidate_root / "manifest.json").read_text(encoding="utf-8"))
    loaded = SafeShadowModelArtifactLoader(data_root=config.data_root).load(
        candidate_root,
        expectation=ArtifactCompatibilityExpectation(
            expected_model_family=str(manifest_payload["model_family"]),
            expected_feature_registry_hash=FEATURE_REGISTRY_HASH,
            expected_label_registry_hash=recommendation_label_registry_hash(),
            expected_feature_schema=FEATURE_SCHEMA,
            installed_library_versions=_library_versions(),
        ),
    )
    assert loaded.status == "shadow_model_ready"
    assert candidate_root.is_relative_to(paths.learning_root)

    consumer = build_default_recommendation_calibration_consumer(config)
    assert consumer is not None
    assert consumer.pointer_path == paths.active_pointer_path
    status, diagnostics = WorkbenchSourceService(config)._load_recommendation_learning_status(None)
    assert diagnostics == []
    assert status is not None
    assert status["run_id"] == result.run_id


def test_recommendation_learning_root_rejects_formal_data_root_descendant(tmp_path: Path) -> None:
    from app_module.recommendation_learning_paths import (
        RecommendationLearningPathError,
        resolve_recommendation_learning_paths,
    )

    formal_root = tmp_path / "formal-data"
    with pytest.raises(RecommendationLearningPathError, match="outside DATA_ROOT"):
        resolve_recommendation_learning_paths(
            data_root=formal_root,
            explicit_output_root=formal_root / "output",
        )


def test_daily_cli_reports_invalid_learning_root_without_starting_replay(
    tmp_path: Path,
    capsys,
) -> None:
    from scripts.scheduled.run_daily_recommendation_learning import main

    formal_root = tmp_path / "formal-data"
    assert main(
        [
            "--data-root",
            str(formal_root),
            "--output-root",
            str(formal_root / "unsafe-output"),
        ]
    ) == 2
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["decision_reason"] == "recommendation_learning_output_root_invalid"
    assert "outside DATA_ROOT" in payload["error"]


def test_daily_main_missing_snapshot_is_recoverable_and_unblocks_same_day(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """A delayed scheduled snapshot must not finalize a false rollback for the day."""

    import scripts.scheduled.run_daily_recommendation_learning as daily_learning

    data_root = tmp_path / "formal-data"
    output_root = tmp_path / "learning-shadow"
    scheduled_output_root = tmp_path / "scheduled-output"
    source_db = tmp_path / "source.db"
    decision_day = date(2026, 9, 14)
    taipei = ZoneInfo("Asia/Taipei")

    monkeypatch.setenv("OUTPUT_ROOT", str(scheduled_output_root))
    monkeypatch.delenv("RECOMMENDATION_LEARNING_OUTPUT_ROOT", raising=False)
    monkeypatch.setattr(
        daily_learning,
        "_taipei_now",
        lambda: datetime(2026, 9, 14, 9, 0, tzinfo=taipei),
    )
    monkeypatch.setattr(daily_learning, "_official_trading_day", lambda **_: (True, "test_calendar"))

    class _Provider:
        def __init__(self, database_path: Path) -> None:
            self.database_path = Path(database_path)

        def list_trading_dates(self, *, start_date: str, end_date: str, symbols: tuple[str, ...]):
            return (start_date[:10],)

        def load_forward_price_window(self, *, start_date: str, end_date: str, symbols: tuple[str, ...]):
            return SimpleNamespace(
                prices=(),
                market=(),
                source_fingerprint=f"forward:{start_date[:10]}:{end_date[:10]}",
            )

        def load(self, *, decision_date: str, history_start_date: str, symbols: tuple[str, ...], industry_index_names):
            return SimpleNamespace(
                decision_date=decision_date[:10],
                feature_as_of_date="2026-09-13",
                source_fingerprint=f"snapshot:{decision_date[:10]}",
                prices=(),
                technicals=(),
                market=(),
                industries=(),
            )

    class _FeatureBuilder:
        def __init__(self, registry) -> None:
            self.registry = registry

        def compute(self, snapshot, *, industry_index_name_by_symbol):
            return ()

    class _ReplayResult:
        source_fingerprint = "sha256:fixture-source"
        training_data_eligible = False
        forward_evidence_eligible = False
        formal_candidate_eligible = False
        candidate_blockers = ("fixture_has_no_rows",)
        dataset_id = "fixture-dataset"
        dataset_hash = "sha256:" + "1" * 64
        source_disclosures = ()
        lookahead_checks = ()
        decision_dates = ()
        rows_skipped_missing_price = 0
        rows_skipped_missing_benchmark = 0
        rows_skipped_missing_feature = 0
        selection_policy = "latest_eligible_dates"

        def __init__(self) -> None:
            feature_count = len(daily_learning.CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids)
            rows: list[RecommendationCalibrationSample] = []
            start = date(2025, 1, 2)
            for day_index in range(110):
                decision = start + timedelta(days=day_index)
                for symbol_index, symbol in enumerate(("1101", "2330")):
                    rows.append(
                        RecommendationCalibrationSample.from_forward_return(
                            row_id=f"{decision.isoformat()}-{symbol}",
                            symbol=symbol,
                            decision_date=decision.isoformat(),
                            feature_as_of_date=(decision - timedelta(days=1)).isoformat(),
                            feature_available_date=(decision - timedelta(days=1)).isoformat(),
                            label_end_date=(decision + timedelta(days=20)).isoformat(),
                            label_available_date=(decision + timedelta(days=20)).isoformat(),
                            feature_values=tuple(
                                ((day_index % 6) - 2) * 1000 + symbol_index * 170
                                for _ in range(feature_count)
                            ),
                            stock_return_bp=((day_index % 6) - 2) * 1000 + symbol_index * 120,
                            benchmark_return_bp=100,
                            fixed_round_trip_cost_bp=50,
                            observed_liquidity_cost_bp=20,
                            rule_probability_bp=5000,
                            rule_after_cost_probability_bp=5000,
                        )
                    )
            self.samples = tuple(rows)
            self.training_data_eligible = True
            self.formal_candidate_eligible = True
            self.candidate_blockers = ()

        def persist(self, root: Path) -> Path:
            path = Path(root) / "recommendation_learning" / "datasets" / "fixture.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.to_dict()), encoding="utf-8")
            return path

        def to_dict(self) -> dict[str, object]:
            return {
                "dataset_id": self.dataset_id,
                "dataset_hash": self.dataset_hash,
                "sample_count": len(self.samples),
                "decision_dates": sorted({row.decision_date for row in self.samples}),
                "source_fingerprint": self.source_fingerprint,
                "training_data_eligible": self.training_data_eligible,
                "forward_evidence_eligible": self.forward_evidence_eligible,
                "formal_candidate_eligible": self.formal_candidate_eligible,
                "candidate_blockers": list(self.candidate_blockers),
                "source_disclosures": [],
                "lookahead_checks": [],
            }

    class _ReplayService:
        def __init__(self, provider) -> None:
            self.provider = provider

        def build(self, config):
            assert config.symbols == ("1101",)
            return _ReplayResult()

    monkeypatch.setattr(daily_learning, "MLHistoricalSnapshotProvider", _Provider)
    monkeypatch.setattr(daily_learning, "HistoricalFeatureBuilder", _FeatureBuilder)
    monkeypatch.setattr(daily_learning, "RecommendationHistoricalReplayService", _ReplayService)

    emergency_result = _runner(output_root, data_root=data_root).run(
        decision_date=decision_day.isoformat(),
        samples=(),
        natural_evidence=None,
        data_dependency_status="failed",
        outcome_dependency_status="failed",
        drift_status="failed",
        emergency_rollback=True,
    )
    emergency_receipt_path = Path(emergency_result.receipt_path)
    emergency_receipt_hash = hashlib.sha256(emergency_receipt_path.read_bytes()).hexdigest()
    emergency_pointer_path = output_root / "recommendation_learning" / "recommendation-calibration-active-pointer.json"
    emergency_pointer = json.loads(emergency_pointer_path.read_text(encoding="utf-8"))
    assert emergency_pointer["status"] == "rule_only"

    common_args = [
        "--data-root",
        str(data_root),
        "--output-root",
        str(output_root),
        "--source-db",
        str(source_db),
        "--decision-date",
        decision_day.isoformat(),
        "--history-start-date",
        "2025-01-01",
        "--replay-start-date",
        "2025-01-02",
        "--replay-end-date",
        decision_day.isoformat(),
        "--max-decision-dates",
        "100",
        "--fixed-round-trip-cost-bp",
        "50",
    ]

    assert daily_learning.main(common_args) == 2
    first_payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    first_receipt_path = Path(first_payload["run"]["receipt_path"])
    first_receipt = json.loads(first_receipt_path.read_text(encoding="utf-8"))
    assert first_payload["run"]["status"] == "failed_dependency"
    assert first_payload["run"]["reason"] == "symbol_cohort_preflight_failed:ValueError"
    assert first_payload["dependencies"]["recovery_policy"] == "recoverable_attempt"
    assert first_receipt["finalized"] is False
    assert first_receipt["recoverable"] is True
    assert "同一 decision date" in first_receipt["next_step"]
    assert not first_receipt_path.parents[1].joinpath("run_receipt.json").exists()

    snapshot_path = (
        scheduled_output_root
        / "recommendation"
        / "runs"
        / "scheduled_rec_20260914_051004.json"
    )
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(
            {
                "config": {"scheduled_snapshot": True, "decision_date": decision_day.isoformat()},
                "recommendations": [{"證券代號": "1101"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert daily_learning.main(common_args) == 0
    second_payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    second_receipt_path = Path(second_payload["run"]["receipt_path"])
    latest_status = json.loads(
        (output_root / "recommendation_learning" / "latest_status.json").read_text(encoding="utf-8")
    )
    assert second_payload["symbol_source"].startswith("scheduled_recommendation_snapshot:")
    assert second_payload["symbols"] == ["1101"]
    assert second_payload["run"]["status"] == "completed"
    assert second_payload["run"]["reason"] == "candidate_trained_and_gate_evaluated"
    assert second_payload["run"]["candidate_id"]
    candidate_metadata = json.loads(
        (Path(second_payload["run"]["candidate_root"]) / "candidate.json").read_text(encoding="utf-8")
    )
    assert int(candidate_metadata["training_row_count"]) > 0
    assert second_receipt_path != first_receipt_path
    assert latest_status["finalized"] is True
    assert hashlib.sha256(emergency_receipt_path.read_bytes()).hexdigest() == emergency_receipt_hash


def test_preflight_failure_classifies_transient_and_integrity_faults() -> None:
    from scripts.scheduled.run_daily_recommendation_learning import _preflight_requires_emergency

    assert _preflight_requires_emergency(OSError("provider temporarily unavailable")) is False
    assert _preflight_requires_emergency(RuntimeError("database is locked")) is False
    assert _preflight_requires_emergency(RuntimeError("historical SQLite source changed during snapshot load")) is True
    assert _preflight_requires_emergency(ValueError("required table is missing: daily_prices")) is True


def test_symbol_resolution_accepts_native_scheduled_snapshot_identifier(tmp_path: Path) -> None:
    from scripts.scheduled.run_daily_recommendation_learning import _resolve_symbols

    runs_root = tmp_path / "recommendation" / "runs"
    runs_root.mkdir(parents=True)
    (runs_root / "scheduled_rec_20260913_051004.json").write_text(
        json.dumps(
            {
                "config": {
                    "scheduled_snapshot": True,
                    "decision_date": "2026-09-13",
                },
                "recommendations": [
                    {"證券代號": "1569"},
                    {"證券代號": "1528"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    symbols, source = _resolve_symbols(
        output_root=tmp_path,
        explicit_symbols=None,
        decision_date=date(2026, 9, 13),
    )

    assert symbols == ("1528", "1569")
    assert source == "scheduled_recommendation_snapshot:scheduled_rec_20260913_051004.json"


def test_qualified_adoption_changes_consumer_projection_with_cap(tmp_path: Path) -> None:
    result, root, metadata = _candidate(tmp_path, shift=0, candidate_day="2026-06-01")
    evidence = _natural_receipt(tmp_path, root=root, candidate_day="2026-06-01", evaluation_day="2026-06-22")
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    decision = authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=result.candidate_id,
        candidate_root=root,
        candidate_metadata=metadata,
        natural_evidence=evidence,
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
    projection = consumer.project(
        stock_code="1101",
        feature_values=(2000, 1000),
        rule_probability_bp=5000,
        after_cost_rule_probability_bp=5000,
        ranking_percentile_bp=7000,
        decision_date="2026-06-22",
    )
    assert projection.status == "active_candidate"
    assert projection.calibrated_probability_bp in {4000, 6000}
    assert projection.calibrated_probability_bp != 5000
    assert projection.after_cost_profit_probability_bp in {4000, 6000}
    assert any(item.startswith("candidate:") for item in projection.source_trace)


def test_effective_probability_lineage_caps_against_delivered_previous_output(tmp_path: Path) -> None:
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    first_result, first_root, first_metadata = _candidate(tmp_path, shift=0, candidate_day="2026-06-01")
    first_evidence = _natural_receipt(tmp_path, root=first_root, candidate_day="2026-06-01", evaluation_day="2026-06-22")
    assert authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=first_result.candidate_id,
        candidate_root=first_root,
        candidate_metadata=first_metadata,
        natural_evidence=first_evidence,
        data_status="ready",
        drift_status="clean",
    ).decision == "adopt"
    second_result, second_root, second_metadata = _candidate(tmp_path, shift=100, candidate_day="2026-07-01")
    second_evidence = _natural_receipt(tmp_path, root=second_root, candidate_day="2026-07-01", evaluation_day="2026-07-22")
    assert authority.evaluate_and_apply(
        decision_date="2026-07-22",
        candidate_id=second_result.candidate_id,
        candidate_root=second_root,
        candidate_metadata=second_metadata,
        natural_evidence=second_evidence,
        data_status="ready",
        drift_status="clean",
    ).decision == "adopt"

    consumer = RecommendationCalibrationConsumer(
        pointer_path=tmp_path / "authority" / "recommendation-calibration-active-pointer.json",
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "formal-data",
    )
    assert consumer.reload(decision_date="2026-07-22") == "active"
    # Deliberately make the raw outputs large and close the exact consumer
    # contract: A raw 9000 -> effective 6000 from null 5000; B raw 8000 must
    # then be capped at 7000, not compared with A's raw 9000.
    consumer._lineage_models = (
        (consumer._probability_lineage[1], _FixedPredictionModel("A", 9000)),
        (consumer._probability_lineage[2], _FixedPredictionModel("B", 8000)),
    )
    consumer._model = consumer._lineage_models[-1][1]
    consumer._baseline_model = consumer._lineage_models[-2][1]
    projection = consumer.project(
        stock_code="1101",
        feature_values=(0, 0),
        rule_probability_bp=5000,
        decision_date="2026-07-22",
    )
    assert projection.calibrated_probability_bp == 7000
    assert projection.raw_calibrated_probability_bp == 8000
    baseline = consumer.champion_baseline(
        feature_values=(0, 0),
        decision_date="2026-07-22",
        baseline_probability_bp=5000,
    )
    assert baseline is not None
    assert baseline.calibrated_probability_bp == 6000

    # A missing previous artifact cannot silently turn B's baseline into the
    # null benchmark; the active pointer becomes rule-only instead.
    shutil.rmtree(first_root)
    failed_consumer = RecommendationCalibrationConsumer(
        pointer_path=tmp_path / "authority" / "recommendation-calibration-active-pointer.json",
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "formal-data",
    )
    failed = failed_consumer.project(
        stock_code="1101",
        feature_values=(0, 0),
        rule_probability_bp=5000,
        decision_date="2026-07-22",
    )
    assert failed.status == "rule_only"
    assert "lineage" in failed.warnings[0]


def test_adopt_twice_then_emergency_rollback_restores_complete_previous_candidate(tmp_path: Path) -> None:
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    first_result, first_root, first_metadata = _candidate(tmp_path, shift=0, candidate_day="2026-06-01")
    first_evidence = _natural_receipt(tmp_path, root=first_root, candidate_day="2026-06-01", evaluation_day="2026-06-22")
    first = authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=first_result.candidate_id,
        candidate_root=first_root,
        candidate_metadata=first_metadata,
        natural_evidence=first_evidence,
        data_status="ready",
        drift_status="clean",
    )
    second_result, second_root, second_metadata = _candidate(tmp_path, shift=100, candidate_day="2026-07-01")
    second_evidence = _natural_receipt(tmp_path, root=second_root, candidate_day="2026-07-01", evaluation_day="2026-07-22")
    second = authority.evaluate_and_apply(
        decision_date="2026-07-22",
        candidate_id=second_result.candidate_id,
        candidate_root=second_root,
        candidate_metadata=second_metadata,
        natural_evidence=second_evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert first.decision == "adopt"
    assert second.decision == "adopt"
    assert first_result.candidate_id != second_result.candidate_id

    rollback = authority.evaluate_and_apply(
        decision_date="2026-07-23",
        candidate_id=None,
        candidate_root=None,
        candidate_metadata=None,
        natural_evidence=None,
        data_status="failed",
        drift_status="clean",
        emergency_rollback=True,
    )
    assert rollback.decision == "rollback"
    pointer = json.loads((tmp_path / "authority" / "recommendation-calibration-active-pointer.json").read_text(encoding="utf-8"))
    assert pointer["status"] == "active"
    assert pointer["candidate_id"] == first_result.candidate_id
    assert pointer["candidate_manifest_hash"]
    assert pointer["candidate_artifact_hash"]
    assert pointer["candidate_freeze_hash"]


def test_first_adoption_fault_rolls_back_to_explicit_rule_only(tmp_path: Path) -> None:
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    result, root, metadata = _candidate(tmp_path, shift=0, candidate_day="2026-06-01")
    evidence = _natural_receipt(tmp_path, root=root, candidate_day="2026-06-01", evaluation_day="2026-06-22")
    adopted = authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=result.candidate_id,
        candidate_root=root,
        candidate_metadata=metadata,
        natural_evidence=evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert adopted.decision == "adopt"
    fault = authority.evaluate_and_apply(
        decision_date="2026-06-23",
        candidate_id=None,
        candidate_root=None,
        candidate_metadata=None,
        natural_evidence=None,
        data_status="failed",
        drift_status="clean",
        emergency_rollback=True,
    )
    assert fault.decision == "rollback"
    pointer_path = tmp_path / "authority" / "recommendation-calibration-active-pointer.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["status"] == "rule_only"
    assert pointer["candidate_id"] is None
    consumer = RecommendationCalibrationConsumer(
        pointer_path=pointer_path,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "formal-data",
    )
    projection = consumer.project(
        stock_code="1101",
        feature_values=(2000, 1000),
        rule_probability_bp=5000,
        decision_date="2026-06-23",
    )
    assert projection.status == "rule_only"
    assert projection.calibrated_probability_bp is None


def test_consumer_reloads_and_fails_closed_on_pointer_tamper_or_unknown_data_status(tmp_path: Path) -> None:
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    result, root, metadata = _candidate(tmp_path, shift=0, candidate_day="2026-06-01")
    evidence = _natural_receipt(tmp_path, root=root, candidate_day="2026-06-01", evaluation_day="2026-06-22")
    authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=result.candidate_id,
        candidate_root=root,
        candidate_metadata=metadata,
        natural_evidence=evidence,
        data_status="ready",
        drift_status="clean",
    )
    pointer_path = tmp_path / "authority" / "recommendation-calibration-active-pointer.json"
    consumer = RecommendationCalibrationConsumer(
        pointer_path=pointer_path,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "formal-data",
    )
    first = consumer.project(
        stock_code="1101",
        feature_values=(2000, 1000),
        rule_probability_bp=5000,
        decision_date="2026-06-22",
    )
    assert first.status == "active_candidate"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["policy_hash"] = "sha256:" + "f" * 64
    pointer_path.write_text(json.dumps(pointer, sort_keys=True), encoding="utf-8")
    tampered = consumer.project(
        stock_code="1101",
        feature_values=(2000, 1000),
        rule_probability_bp=5000,
        decision_date="2026-06-22",
    )
    assert tampered.status == "rule_only"
    assert "policy_hash" in tampered.warnings[0]

    unknown_authority = RecommendationCalibrationPromotionAuthority(tmp_path / "unknown-authority")
    unknown_result, unknown_root, unknown_metadata = _candidate(tmp_path / "unknown", shift=0, candidate_day="2026-06-01")
    unknown_evidence = _natural_receipt(tmp_path / "unknown", root=unknown_root, candidate_day="2026-06-01", evaluation_day="2026-06-22")
    unknown = unknown_authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=unknown_result.candidate_id,
        candidate_root=unknown_root,
        candidate_metadata=unknown_metadata,
        natural_evidence=unknown_evidence,
        data_status="ready",
        drift_status="not_checked",
    )
    assert unknown.decision == "retain_current"
    assert "not_checked" in unknown.reason


def test_active_model_monitor_recomputes_post_adoption_window_and_daily_entry_rolls_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A remains active while B is a challenger; A's later drift rolls it back."""

    authority_root = tmp_path / "authority" / "recommendation_learning"
    authority = RecommendationCalibrationPromotionAuthority(authority_root)
    result, root, metadata = _candidate(tmp_path, shift=0, candidate_day="2026-06-01")
    evidence = _natural_receipt(
        tmp_path,
        root=root,
        candidate_day="2026-06-01",
        evaluation_day="2026-06-22",
    )
    adopted = authority.evaluate_and_apply(
        decision_date="2026-06-22",
        candidate_id=result.candidate_id,
        candidate_root=root,
        candidate_metadata=metadata,
        natural_evidence=evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert adopted.decision == "adopt"
    # The next challenger is intentionally created but not promoted.  Its
    # existence must not replace A as the active monitoring identity.
    challenger_result, _, _ = _candidate(tmp_path, shift=100, candidate_day="2026-07-01")
    assert challenger_result.candidate_id != result.candidate_id

    pointer_path = authority_root / "recommendation-calibration-active-pointer.json"
    real_consumer = RecommendationCalibrationConsumer(
        pointer_path=pointer_path,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "formal-data",
    )
    identity = real_consumer.active_identity(decision_date="2026-06-22")
    assert identity is not None

    class _FixedActiveConsumer:
        def __init__(self, **_: object) -> None:
            self._loaded_pointer = {"effective_date": "2026-06-22"}

        def reload(self, *, decision_date: str) -> str:
            return "active"

        def active_identity(self, *, decision_date: str):
            return identity

        def project(self, **_: object) -> RecommendationCalibrationProjection:
            return RecommendationCalibrationProjection(
                stock_code="1101",
                ranking_score_bp=100,
                ranking_percentile_bp=None,
                ranking_method="absolute_return_shadow_candidate",
                calibrated_probability_bp=9000,
                calibrated_probability_status="active_effective",
                after_cost_profit_probability_bp=None,
                after_cost_profit_probability_status="unavailable",
                confidence_tier="research_candidate",
                evidence_confidence="active_model",
                sample_size=100,
                horizon="20 trading days",
                cost_basis="fixed_round_trip_bp=50; observed liquidity",
                cost_basis_bp=50,
                model_version=str(identity["model_id"]),
                dataset_version="active-dataset",
                source_trace=("active:model",),
                probability_baseline_probability_bp=5000,
                raw_calibrated_probability_bp=9000,
                warnings=(),
                status="active_candidate",
            )

    class _ForwardProvider:
        database_path = tmp_path / "source.db"

        def load_forward_price_window(self, *, start_date: str, end_date: str, symbols: tuple[str, ...]):
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
            symbol = symbols[0]
            trading_days: list[date] = [start]
            cursor = start + timedelta(days=1)
            while len(trading_days) < 21 and cursor <= end:
                if cursor.weekday() < 5:
                    trading_days.append(cursor)
                cursor += timedelta(days=1)
            prices = tuple(
                SimpleNamespace(
                    symbol=symbol,
                    trading_date=day.isoformat(),
                    close_price=Decimal("100") if index == 0 else Decimal("90"),
                )
                for index, day in enumerate(trading_days)
            )
            market = tuple(
                SimpleNamespace(trading_date=day.isoformat(), close_value=Decimal("100"))
                for day in trading_days
            )
            return SimpleNamespace(prices=prices, market=market)

    fake_consumer = _FixedActiveConsumer()
    captures_root = authority_root / "active_captures"
    capture_day = date(2026, 6, 23)
    captured_days: list[date] = []
    while len(captured_days) < 20:
        if capture_day.weekday() < 5:
            captured_days.append(capture_day)
        capture_day += timedelta(days=1)
    for index, day in enumerate(captured_days):
        active_capture = ActiveModelPredictionCaptureService().capture(
            consumer=fake_consumer,
            feature_schema=FEATURE_SCHEMA,
            feature_registry_hash=FEATURE_REGISTRY_HASH,
            policy_hash=RecommendationPromotionPolicy().policy_hash,
            decision_date=day.isoformat(),
            captured_at=f"{day.isoformat()}T09:00:00+08:00",
            inputs=(
                RecommendationPredictionCaptureInput(
                    row_id=f"active-monitor:{day.isoformat()}:1101",
                    symbol="1101",
                    decision_date=day.isoformat(),
                    feature_as_of_date=(day - timedelta(days=1)).isoformat(),
                    feature_available_date=(day - timedelta(days=1)).isoformat(),
                    feature_values=(0, 0),
                    rule_probability_bp=5000,
                ),
            ),
            fixed_round_trip_cost_bp=50,
        )
        active_capture.persist(captures_root / day.isoformat() / f"{index:02d}.json")

    identity_hash = "sha256:" + hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    natural = RecommendationNaturalOutcomeService(_ForwardProvider()).scan_and_build_active_model_evidence(
        output_root=tmp_path / "authority",
        evaluation_date="2026-09-01",
        output_path=tmp_path
        / "authority"
        / "recommendation_learning"
        / "active_evidence"
        / result.candidate_id
        / "2026-09-01.json",
        active_candidate_id=result.candidate_id,
        active_identity_hash=identity_hash,
        active_effective_date="2026-06-22",
    )
    assert natural.status == "matured"
    assert natural.matured_sample_count == 20

    import app_module.recommendation_calibration_consumer as consumer_module
    from scripts.scheduled.run_daily_recommendation_learning import _inspect_active_model_performance

    monkeypatch.setattr(consumer_module, "RecommendationCalibrationConsumer", _FixedActiveConsumer)
    performance = _inspect_active_model_performance(
        output_root=tmp_path / "authority",
        data_root=tmp_path / "formal-data",
        decision_date=date(2026, 9, 1),
        policy=RecommendationPromotionPolicy(),
    )
    assert performance["status"] == "drifted"
    assert performance["active_candidate_id"] == result.candidate_id
    assert performance["matured_decision_date_count"] == 20

    daily_runner = _runner(tmp_path / "daily-run", authority=authority)
    rollback = daily_runner.run(
        decision_date="2026-09-01",
        samples=(),
        natural_evidence=None,
        data_dependency_status="ready",
        outcome_dependency_status="ready",
        drift_status=performance["status"],
        emergency_rollback=True,
    )
    assert rollback.decision == "rollback"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["status"] == "rule_only"


def test_active_pointer_invalid_json_fails_closed(tmp_path: Path) -> None:
    from scripts.scheduled.run_daily_recommendation_learning import _inspect_active_model_performance

    pointer_path = (
        tmp_path
        / "recommendation_learning"
        / "recommendation-calibration-active-pointer.json"
    )
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text("{", encoding="utf-8")

    performance = _inspect_active_model_performance(
        output_root=tmp_path,
        data_root=tmp_path / "formal-data",
        decision_date=date(2026, 9, 1),
        policy=RecommendationPromotionPolicy(),
    )

    assert performance["status"] == "failed"
    assert performance["reason"] == "active_pointer_invalid_json_fail_closed"


def test_daily_main_discovers_maturity_and_rolls_back_active_model_without_flags(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Exercise the real scheduled entrypoint with only clock/source seams replaced."""

    import scripts.scheduled.run_daily_recommendation_learning as daily_learning
    import ml_module.recommendation_historical_replay as replay_module

    output_root = tmp_path / "daily-output"
    data_root = tmp_path / "daily-data"
    source_db = tmp_path / "daily-source.db"
    source_connection = sqlite3.connect(source_db)
    source_connection.executescript(
        """
        CREATE TABLE technical_indicators (
            日期 TEXT NOT NULL,
            證券代號 TEXT NOT NULL,
            RSI TEXT,
            MACD TEXT,
            ADX TEXT,
            available_at TEXT
        );
        CREATE TABLE corporate_action_adjustments (
            symbol TEXT NOT NULL,
            event_date TEXT NOT NULL,
            available_at TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            adjustment_factor TEXT NOT NULL
        );
        CREATE TABLE recommendation_source_contract (
            component TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            source_table TEXT NOT NULL,
            status TEXT NOT NULL,
            coverage_start TEXT NOT NULL,
            coverage_end TEXT NOT NULL,
            available_at TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            source_columns_json TEXT NOT NULL,
            publication_time_verified INTEGER NOT NULL,
            corporate_action_adjustment_verified INTEGER NOT NULL
        );
        CREATE TABLE evidence_events (
            event_id TEXT PRIMARY KEY,
            decision_date TEXT NOT NULL,
            symbol TEXT NOT NULL
        );
        CREATE TABLE evidence_outcomes (
            outcome_id INTEGER PRIMARY KEY,
            event_id TEXT NOT NULL,
            window_days INTEGER NOT NULL,
            outcome_status TEXT NOT NULL,
            outcome_price_date TEXT NOT NULL,
            liquidity_cost_bp INTEGER NOT NULL,
            calculated_at TEXT NOT NULL
        );
        """
    )
    source_day = date(2025, 1, 1)
    while source_day <= date(2026, 12, 31):
        for symbol in ("1101", "2330"):
            source_connection.execute(
                "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?, ?)",
                (source_day.isoformat(), symbol, "55", "1.5", "20", source_day.isoformat()),
            )
        source_day += timedelta(days=1)
    for symbol in ("1101", "2330"):
        source_connection.execute(
            "INSERT INTO corporate_action_adjustments VALUES (?, ?, ?, ?, ?)",
            (symbol, "2025-01-01", "2025-01-01", "2025-01-01", "1"),
        )
        source_connection.execute(
            "INSERT INTO corporate_action_adjustments VALUES (?, ?, ?, ?, ?)",
            (symbol, "2026-12-31", "2026-12-31", "2026-12-31", "1"),
        )
    source_connection.commit()
    technical_content = replay_module._read_source_content_snapshot(
        source_db,
        component="technical",
        source_table="technical_indicators",
        symbols=("1101", "2330"),
        history_start=date(2025, 1, 1),
        replay_end=date(2026, 12, 31),
    )
    corporate_content = replay_module._read_source_content_snapshot(
        source_db,
        component="corporate_actions",
        source_table="corporate_action_adjustments",
        symbols=("1101", "2330"),
        history_start=date(2025, 1, 1),
        replay_end=date(2026, 12, 31),
    )
    source_connection.executemany(
        "INSERT INTO recommendation_source_contract VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            (
                "technical",
                "fixture-technical-publication-v1",
                "technical_indicators",
                "accepted",
                "2025-01-01",
                "2026-12-31",
                "2024-12-31",
                technical_content["digest"],
                json.dumps(["日期", "證券代號", "RSI", "MACD", "ADX", "available_at"], ensure_ascii=False),
                1,
                0,
            ),
            (
                "corporate_actions",
                "fixture-corporate-actions-v1",
                "corporate_action_adjustments",
                "accepted",
                "2025-01-01",
                "2026-12-31",
                "2024-12-31",
                corporate_content["digest"],
                json.dumps(
                    ["symbol", "event_date", "available_at", "effective_from", "adjustment_factor"]
                ),
                0,
                1,
            ),
        ),
    )
    taipei = ZoneInfo("Asia/Taipei")
    clock = {"day": date(2026, 6, 1)}

    def _clock_now() -> datetime:
        current = clock["day"]
        return datetime(current.year, current.month, current.day, 9, 0, tzinfo=taipei)

    def _weekdays(start: date, count: int) -> tuple[date, ...]:
        values: list[date] = []
        current = start
        while len(values) < count:
            if current.weekday() < 5:
                values.append(current)
            current += timedelta(days=1)
        return tuple(values)

    outcome_id = 1
    for decision in _weekdays(date(2025, 1, 2), 500):
        label_date = decision + timedelta(days=20)
        for symbol in ("1101", "2330"):
            event_id = f"fixture-event-{decision.isoformat()}-{symbol}"
            source_connection.execute(
                "INSERT INTO evidence_events(event_id, decision_date, symbol) VALUES (?, ?, ?)",
                (event_id, decision.isoformat(), symbol),
            )
            source_connection.execute(
                "INSERT INTO evidence_outcomes(outcome_id, event_id, window_days, outcome_status, outcome_price_date, liquidity_cost_bp, calculated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    outcome_id,
                    event_id,
                    20,
                    "ready",
                    label_date.isoformat(),
                    20,
                    label_date.isoformat() + "T00:00:00+08:00",
                ),
            )
            outcome_id += 1
    source_connection.commit()
    source_connection.close()

    class _Provider:
        def __init__(self, database_path: Path) -> None:
            self.database_path = Path(database_path)
            self.forward_calls: dict[tuple[str, str], int] = {}

        def list_trading_dates(self, *, start_date: str, end_date: str, symbols: tuple[str, ...]):
            start = date.fromisoformat(start_date[:10])
            end = date.fromisoformat(end_date[:10])
            return tuple(
                current.isoformat()
                for current in _weekdays(start, ((end - start).days + 1) * 2)
                if current <= end
            )

        def load(self, *, decision_date: str, history_start_date: str, symbols: tuple[str, ...], industry_index_names):
            decision = date.fromisoformat(decision_date[:10])
            prior = (decision - timedelta(days=1)).isoformat()
            return SimpleNamespace(
                decision_date=decision.isoformat(),
                feature_as_of_date=prior,
                source_fingerprint=f"snapshot:{decision.isoformat()}",
                prices=(),
                technicals=tuple(
                    SimpleNamespace(symbol=symbol, trading_date=prior)
                    for symbol in symbols
                ),
                market=(),
                industries=(),
            )

        def load_forward_price_window(self, *, start_date: str, end_date: str, symbols: tuple[str, ...]):
            start = date.fromisoformat(start_date[:10])
            end = date.fromisoformat(end_date[:10])
            key = (start.isoformat(), end.isoformat())
            self.forward_calls[key] = self.forward_calls.get(key, 0) + 1
            request_number = self.forward_calls[key]
            candidate_dir = output_root / "recommendation_learning" / "captures" / start.isoformat()
            active_dir = output_root / "recommendation_learning" / "active_captures" / start.isoformat()
            candidate_files = tuple(candidate_dir.glob("*.json")) if candidate_dir.is_dir() else ()
            active_files = tuple(active_dir.glob("*.json")) if active_dir.is_dir() else ()

            candidate_rows: dict[str, Mapping[str, object]] = {}
            active_rows: dict[str, Mapping[str, object]] = {}
            for path in candidate_files:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    candidate_rows = {
                        str(row["symbol"]): row
                        for row in payload.get("rows", [])
                        if isinstance(row, Mapping) and row.get("symbol")
                    }
                except (OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError):
                    candidate_rows = {}
            for path in active_files:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    active_rows = {
                        str(row["symbol"]): row
                        for row in payload.get("rows", [])
                        if isinstance(row, Mapping) and row.get("symbol")
                    }
                except (OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError):
                    active_rows = {}

            prices: list[SimpleNamespace] = []
            market: list[SimpleNamespace] = []
            future_dates = [start + timedelta(days=offset) for offset in range(1, 21) if start + timedelta(days=offset) <= end]
            observed_dates = [start, *future_dates]
            for index, current in enumerate(observed_dates):
                market.append(SimpleNamespace(trading_date=current.isoformat(), close_value=Decimal("100")))
                for symbol in symbols:
                    if active_rows:
                        # Once A is active, the source deliberately returns
                        # the opposite label for the active monitor; this is
                        # an external read-only source seam, not a drift flag.
                        positive = False
                        row = active_rows.get(symbol)
                    elif candidate_rows:
                        row = candidate_rows.get(symbol)
                        # The read-only fixture has a 60% positive rate,
                        # matching the frozen candidate's capped 6000bp
                        # output.  This makes the natural gate qualify
                        # on its observed same-sample improvement without
                        # passing a caller-supplied gate flag.
                        positive = (
                            (start.toordinal() + (0 if symbol == "1101" else 1)) % 5
                        ) < 3
                    else:
                        row = None
                        positive = start.toordinal() % 2 == 0
                    if active_rows and request_number > 1 and row is None:
                        positive = False
                    close = Decimal("120") if positive else Decimal("80")
                    prices.append(
                        SimpleNamespace(
                            symbol=symbol,
                            trading_date=current.isoformat(),
                            close_price=Decimal("100") if index == 0 else close,
                        )
                    )
            return SimpleNamespace(
                prices=tuple(prices),
                market=tuple(market),
                source_fingerprint=f"forward:{start.isoformat()}:{end.isoformat()}:{request_number}",
            )

    class _FeatureBuilder:
        def __init__(self, registry) -> None:
            self.registry = registry

        def compute(self, snapshot, *, industry_index_name_by_symbol):
            decision = date.fromisoformat(snapshot.decision_date)
            if decision >= date(2026, 6, 1):
                values = tuple((feature, 100_000) for feature in self.registry.canonical_ids)
            else:
                sign = 1 if decision.toordinal() % 2 == 0 else -1
                values = tuple((feature, sign * 100_000) for feature in self.registry.canonical_ids)
            return tuple(
                SimpleNamespace(
                    symbol=symbol,
                    feature_as_of_date=(decision - timedelta(days=1)).isoformat(),
                    available_date=(decision - timedelta(days=1)).isoformat(),
                    values=values,
                )
                for observation in snapshot.technicals
                for symbol in (observation.symbol,)
            )

    provider_holder: dict[str, _Provider] = {}

    def _provider_factory(database_path: Path) -> _Provider:
        provider = _Provider(database_path)
        provider_holder["provider"] = provider
        return provider

    monkeypatch.setattr(daily_learning, "MLHistoricalSnapshotProvider", _provider_factory)
    monkeypatch.setattr(daily_learning, "HistoricalFeatureBuilder", _FeatureBuilder)
    monkeypatch.setattr(replay_module, "HistoricalFeatureBuilder", _FeatureBuilder)
    monkeypatch.setattr(daily_learning, "_official_trading_day", lambda **_: (True, "test_clock_calendar"))
    monkeypatch.setattr(daily_learning, "_taipei_now", _clock_now)

    def _run(day: date) -> dict[str, object]:
        clock["day"] = day
        exit_code = daily_learning.main(
            [
                "--data-root", str(data_root),
                "--output-root", str(output_root),
                "--source-db", str(source_db),
                "--symbols", "1101,2330",
                "--history-start-date", "2025-01-01",
                "--replay-start-date", "2025-01-02",
                "--replay-end-date", day.isoformat(),
                "--decision-date", day.isoformat(),
                "--training-as-of", day.isoformat(),
                "--max-decision-dates", "100",
                "--fixed-round-trip-cost-bp", "50",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr().out.strip().splitlines()
        assert captured, f"scheduled entrypoint produced no JSON for {day}"
        return json.loads(captured[-1])

    for day in _weekdays(date(2026, 6, 1), 20):
        _run(day)

    adoption_payload = _run(date(2026, 7, 20))
    pointer_path = output_root / "recommendation_learning" / "recommendation-calibration-active-pointer.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["status"] == "active"
    active_candidate_id = str(pointer["candidate_id"])
    assert adoption_payload["run"]["decision"] == "adopt"
    assert adoption_payload["challenger"]["status"] == "active"
    candidate_metadata = json.loads(
        (Path(str(pointer["candidate_root"])) / "candidate.json").read_text(encoding="utf-8")
    )
    assert candidate_metadata["after_cost_calibration_sample_count"] > 0
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY

    active_consumer = RecommendationCalibrationConsumer(
        pointer_path=pointer_path,
        feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        data_root=data_root,
    )
    active_projection = active_consumer.project(
        stock_code="1101",
        feature_values=tuple(100_000 for _ in CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids),
        rule_probability_bp=5_000,
        after_cost_rule_probability_bp=5_000,
        decision_date="2026-07-20",
    )
    assert active_projection.after_cost_profit_probability_bp is not None
    no_cost_projection = active_consumer.project(
        stock_code="1101",
        feature_values=tuple(100_000 for _ in CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids),
        rule_probability_bp=5_000,
        decision_date="2026-07-20",
    )
    assert no_cost_projection.after_cost_profit_probability_bp is None

    active_capture_days = _weekdays(date(2026, 7, 21), 20)
    first_b_payload = _run(active_capture_days[0])
    challenger_path = output_root / "recommendation_learning" / "challenger" / "current.json"
    challenger = json.loads(challenger_path.read_text(encoding="utf-8"))
    assert challenger["status"] == "pending"
    assert challenger["candidate_id"] != active_candidate_id
    assert first_b_payload["active_pointer"]["candidate_id"] == active_candidate_id
    for day in active_capture_days[1:]:
        _run(day)

    evaluation_payload = _run(date(2026, 9, 1))
    assert evaluation_payload["dependencies"]["model_performance"]["status"] == "pending"
    assert evaluation_payload["active_model_natural_evidence"]["status"] == "matured"
    assert evaluation_payload["active_model_natural_evidence"]["matured_sample_count"] >= 20

    # The final capture is 2026-08-17.  Keep the production 20-day maturity
    # and distinct-date gates intact: 2026-09-10 is the first test day on
    # which all twenty active capture dates have naturally matured.  The
    # post-scan performance refresh must discover the breach on that day.
    rollback_payload = _run(date(2026, 9, 10))
    assert rollback_payload["dependencies"]["model_performance"]["status"] == "drifted"
    assert rollback_payload["run"]["decision"] == "rollback"
    final_pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert final_pointer["status"] == "rule_only"
