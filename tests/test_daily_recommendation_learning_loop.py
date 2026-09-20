from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil
from types import SimpleNamespace
from typing import Mapping
from zoneinfo import ZoneInfo

import pytest

from ml_module.recommendation_calibration_learning_runner import DailyRecommendationLearningRunner
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
    sample_payload,
)
from tests.natural_session_source_fixture import (
    make_verified_natural_fixture,
    make_verified_source_binding,
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


def _candidate(
    tmp_path: Path,
    *,
    shift: int,
    candidate_day: str,
    dataset_quality: Mapping[str, object] | None = None,
) -> tuple[object, Path, dict[str, object]]:
    training_as_of = (date.fromisoformat(candidate_day) - timedelta(days=1)).isoformat()
    samples = tuple(
        sample
        for sample in _samples(shift)
        if sample.decision_date <= training_as_of
        and sample.label_available_date <= training_as_of
    )
    digest = "a" if shift == 0 else "b"
    root = tmp_path / f"candidate-{digest}"
    from ml_module.recommendation_training_lineage import recommendation_training_dataset_hash

    dataset_hash = recommendation_training_dataset_hash(samples)
    result = RecommendationCalibrationTrainingService().fit(
        dataset_id=f"dataset-{digest}",
        dataset_hash=dataset_hash,
        samples=samples,
        feature_names=FEATURE_NAMES,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        training_as_of="2026-12-31",
        fixed_round_trip_cost_bp=50,
        dataset_quality=(
            dict(dataset_quality)
            if dataset_quality is not None
            else {"formal_candidate_eligible": True}
        ),
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
    from ml_module.recommendation_training_lineage import (
        build_recommendation_training_lineage,
        persist_recommendation_training_lineage,
    )

    lineage_quality = dict(dataset_quality or {})
    lineage_quality.setdefault("research_only", True)
    lineage_quality.setdefault("training_semantics", "historical_research_only")
    lineage_quality.setdefault("decision_time_eligible", False)
    lineage = build_recommendation_training_lineage(
        learning_root=tmp_path,
        run_id=f"fixture-{result.candidate_id}",
        run_scope="daily-loop-test",
        decision_date=candidate_day,
        training_as_of=training_as_of,
        dataset_id=f"dataset-{digest}",
        dataset_hash=str(metadata["dataset_hash"]),
        samples=samples,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        fixed_round_trip_cost_bp=50,
        cost_scenario=None,
        dataset_quality=lineage_quality,
        training_result=result,
        training_config=RecommendationCalibrationTrainingConfig(
            minimum_calibration_samples=10,
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
        candidate_id=result.candidate_id,
        candidate_manifest_hash=str(metadata["manifest_hash"]),
        candidate_artifact_hash=str(metadata["artifact_hash"]),
    )
    lineage_path = persist_recommendation_training_lineage(tmp_path, lineage)
    metadata["training_lineage_manifest_hash"] = lineage.manifest_hash
    metadata["training_lineage_manifest_path"] = str(lineage_path)
    (root / "candidate.json").write_text(
        json.dumps(metadata, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result, root, metadata


def _natural_receipt(
    tmp_path: Path,
    *,
    root: Path,
    candidate_day: str,
    evaluation_day: str,
    capture_dates: tuple[date, ...] | None = None,
    feature_schema: tuple[tuple[str, str, str], ...] = FEATURE_SCHEMA,
    feature_registry_hash: str = FEATURE_REGISTRY_HASH,
) -> object:
    captures: list[Path] = []
    outcomes: list[MaturedRecommendationOutcome] = []
    start = date.fromisoformat(candidate_day)
    if capture_dates is None:
        selected_dates: list[date] = []
        cursor = start
        while len(selected_dates) < 20:
            if cursor.weekday() < 5:
                selected_dates.append(cursor)
            cursor += timedelta(days=1)
        dates = tuple(selected_dates)
    else:
        if any(item.weekday() >= 5 for item in capture_dates):
            raise ValueError("explicit natural capture dates must be official weekdays")
        dates = tuple(capture_dates)
    fixture = make_verified_natural_fixture(
        tmp_path,
        tuple(dict.fromkeys(dates)),
        evaluation_day,
        feature_schema=feature_schema,
        feature_registry_hash=feature_registry_hash,
    )
    for index, capture_day in enumerate(dates):
        capture_input = fixture.input_for(capture_day)
        source_binding = fixture.binding_for(capture_day)
        if capture_day in dates[:index]:
            # 保留「20 rows、19 distinct dates」邊界；同日第二列使用另一
            # symbol 與獨立 source contract，避免用重複 row 假造日期成熟度。
            capture_input = replace(
                capture_input,
                row_id=f"forward-{index:02d}",
                symbol="2330",
            )
            source_binding = make_verified_source_binding(
                tmp_path,
                capture_day,
                (capture_input,),
                fixture.db_path,
                feature_schema=feature_schema,
                feature_registry_hash=feature_registry_hash,
            )
        capture = RecommendationPredictionCaptureService().capture(
            candidate_root=root,
            feature_schema=feature_schema,
            feature_registry_hash=feature_registry_hash,
            policy_hash=RecommendationPromotionPolicy().policy_hash,
            decision_date=capture_day.isoformat(),
            captured_at=f"{capture_day.isoformat()}T09:00:00+00:00",
            inputs=(capture_input,),
            fixed_round_trip_cost_bp=50,
            data_root=tmp_path / "formal-data",
            source_contract_binding=source_binding,
        )
        capture_path = tmp_path / "captures" / capture_day.isoformat() / f"{index:02d}.json"
        capture.persist(capture_path)
        captures.append(capture_path)
        for row in capture.rows:
            outcomes.append(
                MaturedRecommendationOutcome(
                    capture_row_id=str(row["row_id"]),
                    label_end_date=fixture.endpoint_dates[capture_day.isoformat()],
                    label_available_date=fixture.endpoint_dates[capture_day.isoformat()],
                    stock_return_bp=2000 if int(row["candidate_probability_bp"]) >= 5000 else -2000,
                    observed_liquidity_cost_bp=20,
                    benchmark_return_bp=100,
                    session_proof=fixture.proof_for(capture_day),
                )
            )
    return NaturalForwardEvidenceBuilder().build_many(
        captures=tuple(captures),
        outcomes=tuple(outcomes),
        evaluation_date=evaluation_day,
        output_path=tmp_path / f"natural-{candidate_day}.json",
        evaluation_at=fixture.evaluation_at,
        source_id="scheduled_forward_outcomes",
    )


def _prospective_price_up_quality() -> dict[str, object]:
    return {
        "research_only": True,
        "training_semantics": "historical_research_only",
        "training_data_eligible": True,
        "forward_evidence_eligible": False,
        "formal_candidate_eligible": False,
        "candidate_blockers": [
            "historical_replay_is_not_natural_forward_evidence",
            "technical_publication_time_unverified",
            "corporate_action_source_or_adjustment_unverified",
        ],
        "historical_replay_candidate_blockers": [
            "historical_replay_is_not_natural_forward_evidence",
            "technical_publication_time_unverified",
            "corporate_action_source_or_adjustment_unverified",
        ],
        "prospective_source_contract_ready": True,
        "prospective_price_up_promotion_ready": True,
        "promotion_target": "price_up_calibration",
        "after_cost_blockers": [
            "observed_liquidity_cost_not_matured_with_fill_lineage",
        ],
        "actual_execution_blockers": ["broker_actual_fill_custody_not_in_scope"],
        "lane_status": {
            "price_up_calibration": {
                "prospective_status": "ready",
                "prospective_blockers": [],
            },
            "after_cost_calibration": {
                "prospective_status": "blocked",
                "blockers": [
                    "observed_liquidity_cost_not_matured_with_fill_lineage",
                ],
            },
            "actual_execution": {
                "status": "blocked",
                "blockers": ["broker_actual_fill_custody_not_in_scope"],
            },
        },
    }


def test_prospective_price_up_lane_can_promote_after_natural_maturity(tmp_path: Path) -> None:
    _, candidate_root, metadata = _candidate(
        tmp_path,
        shift=0,
        candidate_day="2026-06-01",
        dataset_quality=_prospective_price_up_quality(),
    )
    natural = _natural_receipt(
        tmp_path,
        root=candidate_root,
        candidate_day="2026-06-01",
        evaluation_day="2026-07-27",
    )
    authority = RecommendationCalibrationPromotionAuthority(
        output_root=tmp_path / "authority",
        policy=RecommendationPromotionPolicy(),
    )

    decision = authority.evaluate_and_apply(
        decision_date="2026-07-27",
        candidate_id=str(metadata["candidate_id"]),
        candidate_root=candidate_root,
        candidate_metadata=metadata,
        natural_evidence=natural,
        data_status="ready",
        drift_status="clean",
    )

    assert decision.decision == "adopt"
    assert decision.reason == "natural_same_sample_same_cost_gates_qualified"
    assert metadata["forward_evidence_eligible"] is False
    assert metadata["formal_candidate_eligible"] is False
    assert metadata["prospective_price_up_promotion_ready"] is True
    assert metadata["after_cost_blockers"] == [
        "observed_liquidity_cost_not_matured_with_fill_lineage"
    ]


def test_prospective_price_up_lane_needs_natural_distinct_decision_dates(tmp_path: Path) -> None:
    _, candidate_root, metadata = _candidate(
        tmp_path,
        shift=0,
        candidate_day="2026-06-01",
        dataset_quality=_prospective_price_up_quality(),
    )
    start = date(2026, 6, 1)
    natural = _natural_receipt(
        tmp_path,
        root=candidate_root,
        candidate_day="2026-06-01",
        evaluation_day="2026-07-27",
        capture_dates=tuple(
            day
            for day in (start + timedelta(days=index) for index in range(30))
            if day.weekday() < 5
        )[:19]
        + (date(2026, 6, 25),),
    )
    authority = RecommendationCalibrationPromotionAuthority(
        output_root=tmp_path / "authority",
        policy=RecommendationPromotionPolicy(),
    )

    decision = authority.evaluate_and_apply(
        decision_date="2026-07-27",
        candidate_id=str(metadata["candidate_id"]),
        candidate_root=candidate_root,
        candidate_metadata=metadata,
        natural_evidence=natural,
        data_status="ready",
        drift_status="clean",
    )

    assert decision.decision == "retain_current"
    assert decision.reason == "natural_forward_distinct_decision_dates_insufficient"


def test_daily_runner_is_idempotent_and_does_not_fabricate_natural_maturity(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    first = runner.run(
        decision_date="2026-06-01",
        samples=_samples(),
        natural_evidence=None,
        drift_status="clean",
        training_as_of="2026-12-31",
        dataset_quality={
            "research_only": True,
            "training_semantics": "historical_research_only",
        },
    )
    second = runner.run(
        decision_date="2026-06-01",
        samples=_samples(),
        natural_evidence=None,
        drift_status="clean",
        training_as_of="2026-12-31",
        dataset_quality={
            "research_only": True,
            "training_semantics": "historical_research_only",
        },
    )

    assert first.status == "completed"
    assert first.decision == "retain_current"
    assert first.decision_reason == "candidate_training_as_of_after_decision_fail_closed"
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
    legacy_attempt = json.loads(attempts[0].read_text(encoding="utf-8"))
    assert legacy_attempt["recoverable"] is True
    legacy_attempt["next_step"] = "legacy retry wording"
    attempts[0].write_text(json.dumps(legacy_attempt), encoding="utf-8")

    retried_failed = runner.run(
        decision_date="2026-06-01",
        samples=_samples(),
        natural_evidence=None,
        data_dependency_status="failed",
        outcome_dependency_status="failed",
        drift_status="not_checked",
    )
    assert retried_failed.status == "failed_dependency"
    assert retried_failed.receipt_path != str(attempts[0])
    assert json.loads(Path(retried_failed.receipt_path).read_text(encoding="utf-8"))["recoverable"] is True
    assert json.loads(attempts[0].read_text(encoding="utf-8"))["next_step"] == "legacy retry wording"

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


def test_natural_maturity_caller_binds_source_clock_and_explicit_calendar_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import scripts.scheduled.run_daily_recommendation_learning as daily_learning

    monkeypatch.delenv("NATURAL_MATURITY_CALENDAR_CACHE_PATH", raising=False)
    monkeypatch.delenv("ML_FORWARD_CALENDAR_CACHE_ROOT", raising=False)
    monkeypatch.delenv("NATURAL_MATURITY_TEMPORARY_CLOSURE_PATH", raising=False)
    default_calendar, default_temporary = daily_learning._natural_maturity_calendar_paths(
        calendar_cache_path=None,
        temporary_closure_path=None,
    )
    assert default_calendar == daily_learning.DEFAULT_NATURAL_MATURITY_CALENDAR_CACHE_PATH.resolve()
    assert default_temporary is None

    configured_calendar = tmp_path / "annual-cache"
    configured_temporary = tmp_path / "temporary-cache"
    monkeypatch.setenv(
        "NATURAL_MATURITY_CALENDAR_CACHE_PATH",
        str(configured_calendar),
    )
    monkeypatch.setenv(
        "NATURAL_MATURITY_TEMPORARY_CLOSURE_PATH",
        str(configured_temporary),
    )
    calendar_path, temporary_path = daily_learning._natural_maturity_calendar_paths(
        calendar_cache_path=None,
        temporary_closure_path=None,
    )
    assert calendar_path == configured_calendar.resolve()
    assert temporary_path == configured_temporary.resolve()

    database = tmp_path / "source.db"
    checked = datetime(2026, 9, 18, 8, 25, 1, tzinfo=ZoneInfo("Asia/Taipei"))
    context = daily_learning._natural_maturity_context(
        source_db=database,
        calendar_cache_path=calendar_path,
        temporary_closure_path=temporary_path,
        evaluation_at=checked,
        evaluation_date=date(2026, 9, 17),
    )
    assert context["source_db_path"] == str(database.resolve())
    assert context["calendar_cache_path"] == str(configured_calendar.resolve())
    assert context["evaluation_at"] == checked.isoformat()
    assert context["evaluation_date_matches_checked_clock"] is False

    class _SpyService:
        def __init__(self, provider, **kwargs):
            self.provider = provider
            self.kwargs = kwargs

    monkeypatch.setattr(daily_learning, "RecommendationNaturalOutcomeService", _SpyService)
    resolver = object()
    service = daily_learning._build_natural_outcome_service(
        provider=SimpleNamespace(database_path=database),
        source_db=database,
        session_resolver=resolver,
        evaluation_at=checked,
    )
    assert service.kwargs == {
        "evidence_db_path": database,
        "session_resolver": resolver,
        "evaluation_at": checked,
    }


@pytest.mark.parametrize("calendar_mode", ["missing", "expired"])
def test_natural_maturity_calendar_gap_stays_pending_without_credit(
    tmp_path: Path,
    calendar_mode: str,
) -> None:
    from data_module.natural_maturity_session_resolver import NaturalMaturitySessionResolver
    from data_module.official_trading_calendar_cache import (
        build_twse_calendar_cache,
        write_twse_calendar_cache,
    )

    database = tmp_path / "market.db"
    connection = sqlite3.connect(database)
    connection.execute(
        'CREATE TABLE market_indices ("日期" TEXT NOT NULL, "指數名稱" TEXT NOT NULL, "收盤指數" TEXT)'
    )
    # 保留 capture 日 baseline，讓此回歸真正走到官方 calendar gap，而不是
    # 先因市場 baseline 缺失而 pending。
    cursor = date(2026, 1, 5)
    inserted = 0
    while inserted < 45:
        if cursor.weekday() < 5:
            connection.execute(
                'INSERT INTO market_indices VALUES (?, ?, ?)',
                (cursor.isoformat(), "TAIEX", "23000"),
            )
            inserted += 1
        cursor += timedelta(days=1)
    connection.commit()
    connection.close()

    calendar_root = tmp_path / "calendar"
    if calendar_mode == "missing":
        calendar_path = calendar_root
    else:
        calendar_root.mkdir(parents=True)
        expired = build_twse_calendar_cache(
            calendar_year=2026,
            raw_response=(
                b'[{"Name":"\\u4e2d\\u83ef\\u6c11\\u570b\\u958b\\u570b\\u7d00\\u5ff5\\u65e5",'
                b'"Date":"1150101","Weekday":"\\u56db",'
                b'"Description":"\\u4f9d\\u898f\\u5b9a\\u653e\\u5047\\u0031\\u65e5\\u3002"}]'
            ),
            requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            response_status=200,
            max_age=timedelta(days=1),
        )
        write_twse_calendar_cache(
            calendar_root / "twse_holiday_schedule_2026_expired.json",
            expired,
            allowed_root=tmp_path,
        )
        calendar_path = calendar_root

    from ml_module.recommendation_natural_outcome_service import RecommendationNaturalOutcomeService

    evaluation_at = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
    resolver = NaturalMaturitySessionResolver(
        db_path=database,
        calendar_cache_path=calendar_path,
    )
    service = RecommendationNaturalOutcomeService(
        SimpleNamespace(database_path=database),
        evidence_db_path=database,
        session_resolver=resolver,
        evaluation_at=evaluation_at,
    )
    resolution, reason = service._resolve_maturity_sessions(
        date(2026, 1, 5),
        date(2026, 1, 10),
    )

    assert resolution is None
    assert reason.startswith("natural_maturity_session_waiting_for_calendar:")
    assert "calendar" in reason.casefold()


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
                "schema_version": "recommendation-historical-replay-dataset.v1",
                "dataset_id": self.dataset_id,
                "dataset_hash": self.dataset_hash,
                "sample_count": len(self.samples),
                "decision_dates": sorted({row.decision_date for row in self.samples}),
                "samples": [sample_payload(row) for row in self.samples],
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

    # The replay/training attempt can complete, but the same run's live
    # capture is blocked by the missing prospective source contract. That is
    # a recoverable dependency failure, not normal natural-maturity pending.
    assert daily_learning.main(common_args) == 2
    second_payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert second_payload["error"].startswith("live_capture_blocked:")
    assert second_payload["recoverable"] is True
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


def test_scheduled_experiment_scope_is_stable_while_daily_capture_scope_tracks_cohort() -> None:
    from scripts.scheduled.run_daily_recommendation_learning import (
        _scheduled_capture_scope,
        _scheduled_experiment_scope,
        _scheduled_run_scope,
    )

    cohorts = (
        {
            "requested_symbols": ["1101", "2330"],
            "eligible_symbols": ["1101"],
            "degraded_symbols": ["2330"],
            "cohort_hash": "sha256:" + "1" * 64,
        },
        {
            "requested_symbols": ["1528", "1569"],
            "eligible_symbols": ["1528"],
            "degraded_symbols": ["1569"],
            "cohort_hash": "sha256:" + "2" * 64,
        },
        {
            "requested_symbols": ["0050", "1558", "1560"],
            "eligible_symbols": ["1558", "1560"],
            "degraded_symbols": [],
            "cohort_hash": "sha256:" + "3" * 64,
        },
    )
    experiment_scopes = {
        _scheduled_experiment_scope(fixed_round_trip_cost_bp=50),
        _scheduled_experiment_scope(fixed_round_trip_cost_bp=50),
    }
    run_scopes = {
        _scheduled_run_scope(
            symbols=tuple(cohort["eligible_symbols"]),
            snapshot_cohort=cohort,
        )
        for cohort in cohorts
    }
    capture_scopes = {
        _scheduled_capture_scope(
            symbols=tuple(cohort["eligible_symbols"]),
            snapshot_cohort=cohort,
        )
        for cohort in cohorts
    }

    # The challenger experiment is stable across three different daily
    # cohorts; receipt/capture scopes remain day/cohort-specific.
    assert len(experiment_scopes) == 1
    assert len(run_scopes) == 3
    assert len(capture_scopes) == 3

    # A daily symbol/quality change stays in the same experiment, while a
    # changed cost contract must start a fresh incompatible experiment.
    assert _scheduled_experiment_scope(fixed_round_trip_cost_bp=50) == _scheduled_experiment_scope(
        fixed_round_trip_cost_bp=50,
    )
    assert _scheduled_experiment_scope(fixed_round_trip_cost_bp=50) != _scheduled_experiment_scope(
        fixed_round_trip_cost_bp=100,
    )


def test_three_daily_receipts_reuse_one_frozen_candidate_across_symbol_quality_changes(
    tmp_path: Path,
) -> None:
    from scripts.scheduled.run_daily_recommendation_learning import (
        _scheduled_experiment_scope,
        _scheduled_run_scope,
    )

    assert _scheduled_experiment_scope().startswith("scheduled-experiment-")
    runner = _runner(tmp_path)
    frozen_root: Path | None = None
    candidate_ids: list[str] = []
    for index, (day, symbols, quality) in enumerate(
        (
            ("2026-09-14", ("1101",), "observed"),
            ("2026-09-15", ("1528",), "degraded"),
            ("2026-09-16", ("1569", "2330"), "observed"),
        )
    ):
        cohort = {
            "requested_symbols": list(symbols),
            "eligible_symbols": list(symbols[:1]),
            "degraded_symbols": list(symbols[1:]) if quality == "degraded" else [],
            "cohort_hash": "sha256:" + str(index + 4) * 64,
        }
        result = runner.run(
            decision_date=day,
            run_scope=_scheduled_run_scope(symbols=symbols, snapshot_cohort=cohort),
            samples=_samples(),
            natural_evidence=None,
            data_dependency_status="ready",
            outcome_dependency_status="ready",
            drift_status="not_checked",
            dataset_quality={"formal_candidate_eligible": True},
            frozen_candidate_root=frozen_root,
        )
        if frozen_root is None:
            frozen_root = Path(str(result.candidate_root))
        candidate_ids.append(str(result.candidate_id))
        assert Path(result.receipt_path).is_file()
    assert len(set(candidate_ids)) == 1


def test_manual_three_stock_capture_cannot_be_reused_for_normal_one_stock_scope(
    tmp_path: Path,
) -> None:
    from scripts.scheduled.run_daily_recommendation_learning import _capture_matches_request

    _, candidate_root, metadata = _candidate(
        tmp_path,
        shift=0,
        candidate_day="2026-09-14",
    )
    service = RecommendationPredictionCaptureService()
    inputs = tuple(
        RecommendationPredictionCaptureInput(
            row_id=f"scheduled-live:2026-09-14:{symbol}",
            symbol=symbol,
            decision_date="2026-09-14",
            feature_as_of_date="2026-09-13",
            feature_available_date="2026-09-13",
            feature_values=(1000 + index, 2000 + index),
            rule_probability_bp=5000,
        )
        for index, symbol in enumerate(("1101", "2330", "1528"))
    )
    manual_capture = service.capture(
        candidate_root=candidate_root,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        policy_hash=RecommendationPromotionPolicy().policy_hash,
        decision_date="2026-09-14",
        captured_at="2026-09-14T09:00:00+00:00",
        inputs=inputs,
        fixed_round_trip_cost_bp=50,
        data_root=tmp_path / "formal-data",
    )
    manual_path = tmp_path / "manual" / "2026-09-14" / "manual-3.json"
    manual_capture.persist(manual_path)
    normal_one = (inputs[0],)

    assert _capture_matches_request(
        json.loads(manual_path.read_text(encoding="utf-8")),
        candidate_metadata=metadata,
        candidate_root=candidate_root,
        decision_date="2026-09-14",
        inputs=normal_one,
        source_contract_binding=None,
    ) is False
    assert _capture_matches_request(
        json.loads(manual_path.read_text(encoding="utf-8")),
        candidate_metadata=metadata,
        candidate_root=candidate_root,
        decision_date="2026-09-14",
        inputs=inputs,
        source_contract_binding=None,
    ) is True


def test_same_day_new_symbol_capture_does_not_claim_old_capture_coverage(
    tmp_path: Path,
) -> None:
    from scripts.scheduled.run_daily_recommendation_learning import (
        _scan_cross_capture_identity,
    )

    _, candidate_root, metadata = _candidate(
        tmp_path,
        shift=0,
        candidate_day="2026-09-14",
    )
    service = RecommendationPredictionCaptureService()
    existing_input = RecommendationPredictionCaptureInput(
        row_id="scheduled-live:2026-09-14:1101",
        symbol="1101",
        decision_date="2026-09-14",
        feature_as_of_date="2026-09-13",
        feature_available_date="2026-09-13",
        feature_values=(1000, 2000),
        rule_probability_bp=5000,
        rule_after_cost_probability_bp=5000,
    )
    existing_capture = service.capture(
        candidate_root=candidate_root,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        policy_hash=RecommendationPromotionPolicy().policy_hash,
        decision_date="2026-09-14",
        captured_at="2026-09-14T09:00:00+00:00",
        inputs=(existing_input,),
        fixed_round_trip_cost_bp=50,
        data_root=tmp_path / "formal-data",
    )
    capture_root = tmp_path / "captures" / "2026-09-14"
    existing_path = capture_root / "old-scope" / "capture.json"
    existing_capture.persist(existing_path)
    new_input = RecommendationPredictionCaptureInput(
        row_id="scheduled-live:2026-09-14:2330",
        symbol="2330",
        decision_date="2026-09-14",
        feature_as_of_date="2026-09-13",
        feature_available_date="2026-09-13",
        feature_values=(3000, 4000),
        rule_probability_bp=5000,
        rule_after_cost_probability_bp=5000,
    )

    identity = _scan_cross_capture_identity(
        capture_root=capture_root,
        destination=capture_root / "new-scope" / "capture.json",
        candidate_id=str(metadata["candidate_id"]),
        decision_date="2026-09-14",
        inputs=(existing_input, new_input),
        source_contract_binding=None,
    )

    assert identity["exact_symbols"] == ["1101"]
    assert "2330" not in identity["exact_symbols"]
    assert identity["source_capture_paths"] == [str(existing_path.resolve())]


def test_qualified_adoption_changes_consumer_projection_with_cap(tmp_path: Path) -> None:
    result, root, metadata = _candidate(tmp_path, shift=0, candidate_day="2026-06-01")
    evidence = _natural_receipt(tmp_path, root=root, candidate_day="2026-06-01", evaluation_day="2026-07-27")
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    decision = authority.evaluate_and_apply(
        decision_date="2026-07-27",
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
        decision_date="2026-07-27",
    )
    assert projection.status == "active_candidate"
    assert projection.calibrated_probability_bp in {4000, 6000}
    assert projection.calibrated_probability_bp != 5000
    assert projection.after_cost_profit_probability_bp in {4000, 6000}
    assert any(item.startswith("candidate:") for item in projection.source_trace)


def test_effective_probability_lineage_caps_against_delivered_previous_output(tmp_path: Path) -> None:
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    first_result, first_root, first_metadata = _candidate(tmp_path, shift=0, candidate_day="2026-06-01")
    first_evidence = _natural_receipt(tmp_path, root=first_root, candidate_day="2026-06-01", evaluation_day="2026-07-27")
    assert authority.evaluate_and_apply(
        decision_date="2026-07-27",
        candidate_id=first_result.candidate_id,
        candidate_root=first_root,
        candidate_metadata=first_metadata,
        natural_evidence=first_evidence,
        data_status="ready",
        drift_status="clean",
    ).decision == "adopt"
    second_result, second_root, second_metadata = _candidate(tmp_path, shift=100, candidate_day="2026-07-01")
    second_evidence = _natural_receipt(tmp_path, root=second_root, candidate_day="2026-07-01", evaluation_day="2026-08-27")
    assert authority.evaluate_and_apply(
        decision_date="2026-08-27",
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
    assert consumer.reload(decision_date="2026-08-27") == "active"
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
        decision_date="2026-08-27",
    )
    assert projection.calibrated_probability_bp == 7000
    assert projection.raw_calibrated_probability_bp == 8000
    baseline = consumer.champion_baseline(
        feature_values=(0, 0),
        decision_date="2026-08-27",
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
        decision_date="2026-08-27",
    )
    assert failed.status == "rule_only"
    assert "lineage" in failed.warnings[0]


def test_adopt_twice_then_emergency_rollback_restores_complete_previous_candidate(tmp_path: Path) -> None:
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    first_result, first_root, first_metadata = _candidate(tmp_path, shift=0, candidate_day="2026-06-01")
    first_evidence = _natural_receipt(tmp_path, root=first_root, candidate_day="2026-06-01", evaluation_day="2026-07-27")
    first = authority.evaluate_and_apply(
        decision_date="2026-07-27",
        candidate_id=first_result.candidate_id,
        candidate_root=first_root,
        candidate_metadata=first_metadata,
        natural_evidence=first_evidence,
        data_status="ready",
        drift_status="clean",
    )
    second_result, second_root, second_metadata = _candidate(tmp_path, shift=100, candidate_day="2026-07-01")
    second_evidence = _natural_receipt(tmp_path, root=second_root, candidate_day="2026-07-01", evaluation_day="2026-08-27")
    second = authority.evaluate_and_apply(
        decision_date="2026-08-27",
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
    evidence = _natural_receipt(tmp_path, root=root, candidate_day="2026-06-01", evaluation_day="2026-07-27")
    adopted = authority.evaluate_and_apply(
        decision_date="2026-07-27",
        candidate_id=result.candidate_id,
        candidate_root=root,
        candidate_metadata=metadata,
        natural_evidence=evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert adopted.decision == "adopt"
    fault = authority.evaluate_and_apply(
        decision_date="2026-07-28",
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
        decision_date="2026-07-28",
    )
    assert projection.status == "rule_only"
    assert projection.calibrated_probability_bp is None


def test_consumer_reloads_and_fails_closed_on_pointer_tamper_or_unknown_data_status(tmp_path: Path) -> None:
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    result, root, metadata = _candidate(tmp_path, shift=0, candidate_day="2026-06-01")
    evidence = _natural_receipt(tmp_path, root=root, candidate_day="2026-06-01", evaluation_day="2026-07-27")
    authority.evaluate_and_apply(
        decision_date="2026-07-27",
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
        decision_date="2026-07-27",
    )
    assert first.status == "active_candidate"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["policy_hash"] = "sha256:" + "f" * 64
    pointer_path.write_text(json.dumps(pointer, sort_keys=True), encoding="utf-8")
    tampered = consumer.project(
        stock_code="1101",
        feature_values=(2000, 1000),
        rule_probability_bp=5000,
        decision_date="2026-07-27",
    )
    assert tampered.status == "rule_only"
    assert "policy_hash" in tampered.warnings[0]

    unknown_authority = RecommendationCalibrationPromotionAuthority(tmp_path / "unknown-authority")
    unknown_result, unknown_root, unknown_metadata = _candidate(tmp_path / "unknown", shift=0, candidate_day="2026-06-01")
    unknown_evidence = _natural_receipt(tmp_path / "unknown", root=unknown_root, candidate_day="2026-06-01", evaluation_day="2026-07-27")
    unknown = unknown_authority.evaluate_and_apply(
        decision_date="2026-07-27",
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
    result, root, metadata = _candidate(tmp_path, shift=0, candidate_day="2026-05-12")
    evidence = _natural_receipt(
        tmp_path,
        root=root,
        candidate_day="2026-05-12",
        evaluation_day="2026-07-10",
    )
    adopted = authority.evaluate_and_apply(
        decision_date="2026-07-10",
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
    identity = real_consumer.active_identity(decision_date="2026-07-10")
    assert identity is not None

    class _FixedActiveConsumer:
        def __init__(self, **_: object) -> None:
            self._loaded_pointer = {"effective_date": "2026-07-10"}

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
    capture_day = date(2026, 7, 13)
    captured_days: list[date] = []
    while len(captured_days) < 20:
        if capture_day.weekday() < 5:
            captured_days.append(capture_day)
        capture_day += timedelta(days=1)
    active_fixture = make_verified_natural_fixture(
        tmp_path,
        captured_days,
        "2026-09-10",
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
    )
    _ForwardProvider.database_path = active_fixture.db_path
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
    natural = RecommendationNaturalOutcomeService(
        _ForwardProvider(),
        evidence_db_path=active_fixture.db_path,
        session_resolver=active_fixture.resolver,
        evaluation_at=active_fixture.evaluation_at,
    ).scan_and_build_active_model_evidence(
        output_root=tmp_path / "authority",
        evaluation_date="2026-09-10",
        output_path=tmp_path
        / "authority"
        / "recommendation_learning"
        / "active_evidence"
        / result.candidate_id
        / "2026-09-10.json",
        active_candidate_id=result.candidate_id,
        active_identity_hash=identity_hash,
        active_effective_date="2026-07-10",
    )
    assert natural.status == "matured"
    assert natural.matured_sample_count == 20

    import app_module.recommendation_calibration_consumer as consumer_module
    from scripts.scheduled.run_daily_recommendation_learning import _inspect_active_model_performance

    monkeypatch.setattr(consumer_module, "RecommendationCalibrationConsumer", _FixedActiveConsumer)
    performance = _inspect_active_model_performance(
        output_root=tmp_path / "authority",
        data_root=tmp_path / "formal-data",
        decision_date=date(2026, 9, 10),
        policy=RecommendationPromotionPolicy(),
        source_db=_ForwardProvider.database_path,
    )
    assert performance["status"] == "drifted"
    assert performance["active_candidate_id"] == result.candidate_id
    assert performance["matured_decision_date_count"] == 20

    daily_runner = _runner(tmp_path / "daily-run", authority=authority)
    rollback = daily_runner.run(
        decision_date="2026-09-10",
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
        source_db=tmp_path / "source.db",
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
    import ml_module.recommendation_calibration_evidence as evidence_module
    import ml_module.recommendation_historical_replay as replay_module
    from data_module.recommendation_calibration_source_contract import (
        _hash_payload,
        write_source_contract,
    )
    from data_module.official_trading_calendar_cache import (
        build_twse_calendar_cache,
        write_twse_calendar_cache,
    )

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
        CREATE TABLE market_indices (
            "日期" TEXT NOT NULL,
            "指數名稱" TEXT NOT NULL,
            "收盤指數" TEXT,
            "收盤價" TEXT
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
    market_day = date(2026, 5, 25)
    market_value = 20_000
    while market_day <= date(2026, 9, 18):
        if market_day.weekday() < 5:
            compact_day = market_day.strftime("%Y%m%d")
            source_connection.execute(
                'INSERT INTO market_indices("日期", "指數名稱", "收盤指數", "收盤價") VALUES (?, ?, ?, ?)',
                (compact_day, "TAIEX", str(market_value), str(market_value)),
            )
            market_value += 1
        market_day += timedelta(days=1)
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
        label_date = _weekdays(decision + timedelta(days=1), 20)[-1]
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
            candidate_files = tuple(candidate_dir.rglob("*.json")) if candidate_dir.is_dir() else ()
            active_files = tuple(active_dir.rglob("*.json")) if active_dir.is_dir() else ()

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
            future_dates = [
                start + timedelta(days=offset)
                for offset in range(1, (end - start).days + 1)
                if (start + timedelta(days=offset)).weekday() < 5
            ]
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
                        business_day_index = sum(
                            1
                            for offset in range(
                                (start - date(2026, 5, 25)).days + 1
                            )
                            if (date(2026, 5, 25) + timedelta(days=offset)).weekday() < 5
                        ) - 1
                        positive = (
                            (business_day_index + (0 if symbol == "1101" else 1)) % 5
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
            if decision >= date(2026, 5, 25):
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

    calendar_root = tmp_path / "calendar-cache"
    calendar_root.mkdir(parents=True, exist_ok=True)
    calendar_raw = json.dumps(
        [
            {
                "Name": "測試年度休市",
                "Date": "1150101",
                "Weekday": "四",
                "Description": "測試用年度休市紀錄。",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    def _qualified_source_contract_audit(**kwargs):
        """Inject a qualified prospective source snapshot for this authority test.

        Source lineage and tamper checks are covered by the dedicated custody
        tests.  This regression test focuses on the daily capture -> natural
        maturity -> active-model authority loop, so it supplies an explicit
        qualified contract instead of silently relying on an unqualified
        fixture to pass the production gate.
        """

        symbols = tuple(str(symbol) for symbol in kwargs["symbols"])
        decision_date = kwargs["decision_date"].isoformat()
        feature_registry = daily_learning.CORE_LONG_HISTORY_FEATURE_REGISTRY
        feature_rows = [
            {
                "symbol": symbol,
                "decision_date": decision_date,
                "feature_as_of_date": (kwargs["decision_date"] - timedelta(days=1)).isoformat(),
                "feature_available_date": (kwargs["decision_date"] - timedelta(days=1)).isoformat(),
                "feature_ids": list(feature_registry.canonical_ids),
                "feature_values": [100_000 for _ in feature_registry.canonical_ids],
                "snapshot_hash": "sha256:test-feature-row-" + symbol,
            }
            for symbol in sorted(symbols)
        ]
        feature_snapshot_body = {
            "component": "prospective_recommendation_features",
            "source_db": str(kwargs["source_db"]),
            "decision_date": decision_date,
            "history_start_date": "2025-01-01",
            "feature_registry_hash": feature_registry.registry_hash,
            "feature_schema_hash": "sha256:test-feature-schema",
            "symbols": sorted(symbols),
            "rows": feature_rows,
        }
        available_at = f"{decision_date}T08:00:00+08:00"
        fixture_root = (
            Path(kwargs["learning_output_root"])
            / "fixture_source_lineage"
            / decision_date
        )
        fixture_root.mkdir(parents=True, exist_ok=True)

        def _write_hashed_json(path: Path, body: dict[str, object], hash_field: str) -> str:
            payload = {
                **body,
                hash_field: _hash_payload(body),
            }
            path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return str(payload[hash_field])

        raw_response_path = fixture_root / "daily-source.raw.json"
        raw_response_path.write_text(
            json.dumps(
                {
                    "decision_date": decision_date,
                    "symbols": sorted(symbols),
                    "source": "authority-test-fixture",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        daily_receipt_path = fixture_root / "daily-source.receipt.json"
        daily_receipt_hash = _write_hashed_json(
            daily_receipt_path,
            {
                "schema_version": "fixture-daily-source-receipt.v1",
                "decision_date": decision_date,
                "available_at": available_at,
                "raw_response_path": str(raw_response_path.resolve()),
                "symbols": sorted(symbols),
            },
            "content_sha256",
        )
        technical_output_body = {
            "component": "technical_indicators",
            "decision_date": decision_date,
            "symbols": sorted(symbols),
            "rows_sha256": _hash_payload({"rows": feature_rows}),
        }
        technical_output = {
            **technical_output_body,
            "content_sha256": _hash_payload(technical_output_body),
        }
        publication_payload_body = {
            "schema_version": "fixture-technical-publication-receipt.v1",
            "decision_date": decision_date,
            "available_at": available_at,
            "technical_step_status": "fixture",
            "technical_output": technical_output,
            "source_receipts": [
                {
                    "receipt_path": str(daily_receipt_path.resolve()),
                    "receipt_sha256": evidence_module._sha256_file(daily_receipt_path),
                    "raw_response_path": str(raw_response_path.resolve()),
                    "raw_response_sha256": evidence_module._sha256_file(raw_response_path),
                    "available_at": available_at,
                }
            ],
        }
        publication_payload = {
            **publication_payload_body,
            "content_sha256": _hash_payload(publication_payload_body),
        }
        publication_path = fixture_root / "technical-publication.receipt.json"
        publication_path.write_text(
            json.dumps(publication_payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        adjustment_section_paths: dict[str, Path] = {}
        for section_name in ("adjustments", "coverage"):
            section_path = fixture_root / f"corporate-{section_name}.json"
            section_body = {
                "decision_date": decision_date,
                "section": section_name,
                "symbols": sorted(symbols),
            }
            section_path.write_text(
                json.dumps(section_body, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            adjustment_section_paths[section_name] = section_path
        adjustment_manifest_body = {
            "schema_version": "fixture-corporate-adjustment-manifest.v1",
            "decision_date": decision_date,
            "adjustments": {
                "path": adjustment_section_paths["adjustments"].name,
                "file_hash": evidence_module._sha256_file(adjustment_section_paths["adjustments"]),
            },
            "coverage": {
                "path": adjustment_section_paths["coverage"].name,
                "file_hash": evidence_module._sha256_file(adjustment_section_paths["coverage"]),
            },
        }
        adjustment_manifest_path = fixture_root / "corporate-adjustment.manifest.json"
        adjustment_manifest_hash = _write_hashed_json(
            adjustment_manifest_path,
            adjustment_manifest_body,
            "manifest_hash",
        )
        event_manifest_path = fixture_root / "official-events.manifest.json"
        event_manifest_hash = _write_hashed_json(
            event_manifest_path,
            {
                "schema_version": "fixture-official-event-manifest.v1",
                "decision_date": decision_date,
                "symbols": sorted(symbols),
            },
            "manifest_hash",
        )
        feature_snapshot = {
            "status": "captured",
            "verified": True,
            **feature_snapshot_body,
            "row_count": len(feature_rows),
            "rows_sha256": _hash_payload(feature_snapshot_body),
            "captured_at": available_at,
            "reason": None,
        }
        feature_snapshot["content_sha256"] = _hash_payload(
            {key: value for key, value in feature_snapshot.items() if key != "content_sha256"}
        )
        contract_body = {
            "schema_version": "recommendation-calibration-source-contract.v1",
            "status": "blocked",
            "decision_date": decision_date,
            "symbols": list(symbols),
            "source_root": str(kwargs["output_root"]),
            "data_root": str(kwargs["data_root"]),
            "source_database": str(kwargs["source_db"]),
            "technical": {
                "status": "ready",
                "formal_source_contract": {"verified": True},
                "prospective_available": True,
                "prospective_blockers": [],
                "publication_receipt": {
                    "path": str(publication_path.resolve()),
                    "sha256": evidence_module._sha256_file(publication_path),
                    "payload": publication_payload,
                    "available_at": available_at,
                },
                "publication_available_at": available_at,
                "source_receipt_available_ats": [available_at],
                "prospective_feature_snapshot": feature_snapshot,
            },
            "corporate_actions": {
                "status": "ready",
                "formal_source_contract": {"verified": True},
                "adjustment_custody": {
                    "prospective_verified": True,
                    "manifest_hash": "sha256:" + ("0" * 64),
                    "manifest_path": str(adjustment_manifest_path.resolve()),
                    "manifest_file_hash": evidence_module._sha256_file(adjustment_manifest_path),
                    "available_at": available_at,
                },
                "event_publication": {
                    "manifest_path": str(event_manifest_path.resolve()),
                    "manifest_file_sha256": evidence_module._sha256_file(event_manifest_path),
                    "manifest_hash": event_manifest_hash,
                    "source_publication_available_at": available_at,
                },
            },
            "lanes": {
                "price_up_calibration": {
                    "status": "blocked",
                    "prospective_status": "ready",
                    "blockers": [],
                    "prospective_blockers": [],
                },
                "after_cost_calibration": {
                    "status": "blocked",
                    "prospective_status": "blocked",
                    "blockers": ["observed_liquidity_cost_not_matured_with_fill_lineage"],
                    "prospective_blockers": ["observed_liquidity_cost_not_matured_with_fill_lineage"],
                },
                "actual_execution": {
                    "status": "blocked",
                    "blockers": ["broker_actual_fill_custody_not_in_scope"],
                },
            },
            "historical_pit_policy": {
                "eligible": False,
                "reason": "prospective_test_snapshot_only",
            },
            "replay_vs_prospective": {
                "historical_replay_status": "separately_verified_fixture",
                "prospective_input_status": "ready_for_future_capture_only",
            },
        }
        contract = {
            **contract_body,
            "contract_sha256": _hash_payload(contract_body),
        }
        receipt = write_source_contract(
            contract,
            learning_output_root=kwargs["learning_output_root"],
        )
        return {
            "source_contract": contract,
            "source_contract_receipt": receipt,
        }

    monkeypatch.setattr(daily_learning, "_audit_source_contract", _qualified_source_contract_audit)

    def _run(day: date) -> dict[str, object]:
        clock["day"] = day
        checked = _clock_now()
        calendar_path = calendar_root / f"twse_holiday_schedule_2026_{day.isoformat()}.json"
        if not calendar_path.exists():
            calendar_payload = build_twse_calendar_cache(
                calendar_year=2026,
                raw_response=calendar_raw,
                requested_at=checked - timedelta(seconds=2),
                captured_at=checked - timedelta(seconds=1),
                response_status=200,
                response_headers={"ETag": f'"daily-fixture-{day.isoformat()}"'},
                max_age=timedelta(days=31),
            )
            write_twse_calendar_cache(
                calendar_path,
                calendar_payload,
                allowed_root=calendar_root,
            )
        exit_code = daily_learning.main(
            [
                "--data-root", str(data_root),
                "--output-root", str(output_root),
                "--source-db", str(source_db),
                "--calendar-cache-path", str(calendar_root),
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

    for day in _weekdays(date(2026, 5, 25), 20):
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

    evaluation_payload = _run(date(2026, 9, 14))
    assert evaluation_payload["dependencies"]["model_performance"]["status"] == "pending"
    assert evaluation_payload["active_model_natural_evidence"]["status"] == "matured"
    assert evaluation_payload["active_model_natural_evidence"]["matured_sample_count"] >= 20

    # 最後一筆 capture 是 2026-08-17；保留正式的 20-session maturity 與
    # distinct-date gate：2026-09-14 收盤資料可用後，2026-09-15 才是
    # 二十個 active capture dates 全部自然成熟的第一個測試日。post-scan
    # performance refresh 必須在該日自行發現 breach，不依賴人工 flags。
    rollback_payload = _run(date(2026, 9, 15))
    assert rollback_payload["dependencies"]["model_performance"]["status"] == "drifted"
    assert rollback_payload["run"]["decision"] == "rollback"
    final_pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert final_pointer["status"] == "rule_only"
