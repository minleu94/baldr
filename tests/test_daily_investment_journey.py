from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from app_module.daily_investment_journey import (
    DailyInvestmentJourneyService,
    _CandidateRead,
    _EvidenceRead,
    _headline,
    _industry_rotation_summary,
    _project_learning_receipt,
)
from app_module.decision_desk_dtos import (
    DecisionDeskQuality,
    DecisionDeskRiskPromptSummary,
    DecisionDeskSnapshot,
    MarketBreadthSummary,
    MarketRegimeSummary,
    PortfolioAlertSummary,
    RelativeStrengthLiquiditySummary,
    SectorRotationSummary,
    WatchlistTriggerSummary,
)
from app_module.evidence_event_dtos import (
    EvidenceDataQuality,
    EvidenceEvent,
    EvidenceEventType,
    EvidenceOutcome,
    EvidenceOutcomeStatus,
)
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation_repository import RecommendationRepository
from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    QualityReport,
    QualityStatus,
    RecommendationExecution,
    RecommendationResultConfigSnapshot,
    Request,
)
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from data_module.result_artifact_store import ResultArtifactStore
from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus
from app_module.workbench_dtos import WorkbenchLearningReceipt
from data_module.config import TWStockConfig
from decision_module.recommendation.contracts import DecisionBatch, RecommendationItem


def _config(tmp_path: Path) -> TWStockConfig:
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    config.db_file = tmp_path / "evidence.sqlite"
    config.research_run_db_file = tmp_path / "research.sqlite"
    return config


@pytest.fixture
def _scheduled_base_execution(tmp_path: Path, monkeypatch) -> RecommendationExecution:
    """沿既有 scheduled producer fixture 取得完整 typed identities/cohort。"""
    from scripts.scheduled import run_scheduled_recommendation_snapshot as producer
    from tests.test_scheduled_recommendation_snapshot_wrapper import (
        _capture_composition,
        _fake_recommendation_body_result,
    )

    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "scheduled-data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "scheduled-output"))
    monkeypatch.setattr(
        producer.RecommendationService,
        "_run_recommendation_body_result",
        _fake_recommendation_body_result,
    )
    monkeypatch.setattr(
        producer,
        "scheduled_now",
        lambda: datetime(2026, 9, 22, 9, 6, tzinfo=timezone.utc),
    )
    captured = _capture_composition(monkeypatch, order=[])
    assert producer.main(
        [
            "--data-root",
            str(tmp_path / "scheduled-data"),
            "--output-root",
            str(tmp_path / "scheduled-output"),
            "--max-stocks",
            "25",
            "--top-n",
            "5",
        ]
    ) == 0
    read_model = captured["read_model"]
    execution = getattr(read_model, "execution", None)
    assert isinstance(execution, RecommendationExecution)
    return execution


def _scheduled_candidate_execution(
    base: RecommendationExecution,
    result_id: str,
    *,
    decision_date: str,
    config_overrides: dict[str, object] | None = None,
    decision_at: datetime | None = None,
) -> RecommendationExecution:
    """只調日期角色，沿用 producer 產生的完整不可變執行身份。"""
    snapshot = base.context.result_config_snapshot
    assert snapshot is not None
    result_config = json.loads(snapshot.raw_result_config_json)
    market_date = date.fromisoformat(decision_date) - timedelta(days=1)
    result_config.update(
        {
            "decision_date": decision_date,
            "data_as_of_date": market_date.isoformat(),
            "market_cutoff_date": market_date.isoformat(),
            "temporal_mode": "natural_producer_clock",
            "cutoff_policy": "source_latest_available_exact",
            "cutoff_selection": "producer_selected_latest_available_cutoff",
            "date_semantics_schema": "scheduled-recommendation-date-roles.v1",
            "decision_timezone": "Asia/Taipei",
        }
    )
    result_config.update(config_overrides or {})
    raw_config = json.dumps(
        result_config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    result_snapshot = RecommendationResultConfigSnapshot(
        raw_result_config_json=raw_config,
        config_sha256="sha256:" + hashlib.sha256(raw_config.encode("utf-8")).hexdigest(),
    )
    market_date = date.fromisoformat(result_config["data_as_of_date"])
    request = replace(base.request, as_of_date=market_date)
    context = replace(
        base.context,
        as_of_date=market_date,
        decision_at=decision_at
        or datetime.fromisoformat(f"{decision_date}T08:10:00+08:00"),
        result_config_snapshot=result_snapshot,
    )
    return replace(base, result_id=result_id, request=request, context=context)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _seed_candidate_outputs(config: TWStockConfig) -> None:
    runs_dir = config.output_root / "recommendation" / "runs"
    result_id = "scheduled-rec-1"
    _write_json(
        config.output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json",
        {
            "status": "passed",
            "decision_date": "2026-09-14",
            "data_as_of_date": "2026-09-14",
            "result_id": result_id,
            "recommendations_count": 1,
            "runs_dir": str(runs_dir),
            "snapshot_cohort": {
                "cohort_hash": "sha256:cohort-1",
                "requested_count": 2,
                "eligible_count": 1,
                "degraded_symbols": 1,
                "missing_symbols": 0,
                "coverage_status": "degraded",
                "universe_snapshot_id": "snapshot-1",
            },
            "evidence_identity": {
                "strategy_version_id": "strategy-1",
                "strategy_config_id": "config-1",
                "universe_policy_id": "policy-1",
                "universe_policy_hash": "sha256:policy-1",
                "universe_snapshot_id": "snapshot-1",
                "universe_snapshot_hash": "sha256:snapshot-1",
                "benchmark_id": "TAIEX",
                "cost_model_id": "cost-1",
                "horizon_days": 20,
            },
        },
    )
    RecommendationRepository(config).save_result(
        RecommendationResultDTO(
            result_id=result_id,
            result_name="合成排程結果",
            config={},
            recommendations=[
                RecommendationDTO(
                    stock_code="1528",
                    stock_name="恩德",
                    close_price=0,
                    price_change=0,
                    total_score=73.13,
                    indicator_score=0,
                    pattern_score=0,
                    volume_score=0,
                    recommendation_reasons="圖形模式分數+",
                    industry="電機機械",
                    regime_match=False,
                    ranking_method="fixed_threshold",
                )
            ],
            run_context={
                "as_of_date": "2026-09-14",
                "data_as_of_date": "2026-09-14",
            },
            created_at="2026-09-14T08:00:00+08:00",
        ),
        result_name="合成排程結果",
    )


def _seed_canonical_candidate(
    config: TWStockConfig,
    result_id: str,
    *,
    execution_as_of_date: date | None = None,
    execution_override: RecommendationExecution | None = None,
) -> Path:
    runs_dir = config.output_root / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    result_config: dict[str, object] = {
        "data_as_of_date": "2026-09-13",
        "strategy_version_id": "strategy-1",
        "strategy_config_id": "config-1",
        "universe_policy_id": "policy-1",
        "universe_policy_hash": "sha256:policy-1",
        "universe_snapshot_id": "snapshot-1",
        "universe_snapshot_hash": "sha256:snapshot-1",
        "cost_model_id": "cost-1",
        "benchmark_id": "TAIEX",
        "horizon_days": 20,
        "return_basis": "close_to_close",
    }
    if execution_override is not None:
        execution = execution_override
    else:
        effective_as_of_date = execution_as_of_date or date(2026, 9, 14)
        raw_config = json.dumps(result_config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        saved_config = RecommendationResultConfigSnapshot(
            raw_result_config_json=raw_config,
            config_sha256="sha256:" + hashlib.sha256(raw_config.encode("utf-8")).hexdigest(),
        )
        execution = RecommendationExecution(
            result_id=result_id,
            request=Request(as_of_date=effective_as_of_date),
            context=Context(
                as_of_date=effective_as_of_date,
                result_config_snapshot=saved_config,
            ),
            status=ExecutionStatus.COMPLETED,
            decision=DecisionBatch(
                items=(
                    RecommendationItem(
                        stock_code="1528",
                        stock_name="恩德",
                        industry="電機機械",
                        rule_score=Decimal("73.13"),
                        reason_text="圖形模式分數+",
                        rank=4,
                        ranking_method="fixed_threshold",
                    ),
                )
            ),
            quality=QualityReport(QualityStatus.DEGRADED, warnings=("saved_quality_warning",)),
        )
    receipt = persistence.save(execution, label="合成 canonical 排程結果")
    assert receipt.artifact_location is not None
    artifact_path = store.artifact_root / receipt.artifact_location
    return artifact_path


def _write_canonical_candidate_status(
    config: TWStockConfig,
    result_id: str,
    *,
    decision_date: str,
    data_as_of_date: str,
    execution: RecommendationExecution | None = None,
) -> None:
    result_config: dict[str, object] | None = None
    if execution is not None and execution.context.result_config_snapshot is not None:
        result_config = json.loads(execution.context.result_config_snapshot.raw_result_config_json)
    if result_config is None:
        status_cohort: dict[str, object] = {
            "cohort_hash": "sha256:cohort-1",
            "requested_count": 2,
            "eligible_count": 1,
            "degraded_symbols": 1,
            "missing_symbols": 0,
            "coverage_status": "degraded",
            "universe_policy_id": "policy-1",
            "universe_policy_hash": "sha256:policy-1",
            "universe_snapshot_id": "snapshot-1",
            "universe_snapshot_hash": "sha256:snapshot-1",
        }
        evidence_identity: dict[str, object] = {
            "strategy_version_id": "strategy-1",
            "strategy_config_id": "config-1",
            "universe_policy_id": "policy-1",
            "universe_policy_hash": "sha256:policy-1",
            "universe_snapshot_id": "snapshot-1",
            "universe_snapshot_hash": "sha256:snapshot-1",
            "benchmark_id": "TAIEX",
            "cost_model_id": "cost-1",
            "horizon_days": 20,
        }
        source_snapshot_id = "snapshot-1"
    else:
        status_cohort = result_config["snapshot_cohort"]
        evidence_keys = (
            "strategy_version_id",
            "strategy_config_id",
            "universe_policy_id",
            "universe_policy_hash",
            "universe_snapshot_id",
            "universe_snapshot_hash",
            "cost_model_id",
            "benchmark_id",
            "horizon_days",
            "return_basis",
        )
        evidence_identity = {key: result_config[key] for key in evidence_keys}
        source_snapshot_id = result_config["universe_snapshot_id"]
    _write_json(
        config.output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json",
        {
            "status": "passed",
            "decision_date": decision_date,
            "data_as_of_date": data_as_of_date,
            "result_id": result_id,
            "source_snapshot_id": source_snapshot_id,
            "recommendations_count": 1,
            "snapshot_cohort": status_cohort,
            "evidence_identity": evidence_identity,
        },
    )


def _seed_registered_legacy_payload(
    config: TWStockConfig,
    *,
    result_id: str,
    payload: dict[str, object],
) -> Path:
    repository = RecommendationRepository(config)
    repository.save_result(
        RecommendationResultDTO(
            result_id=result_id,
            result_name="合成 legacy 結果",
            config={},
            recommendations=[],
            created_at="2026-09-14T08:00:00+08:00",
        ),
        result_name="合成 legacy 結果",
    )
    path = repository.runs_dir / f"{result_id}.json"
    _write_json(path, payload)
    return path


def _write_forward_receipt(config: TWStockConfig, *, skipped: int = 1) -> None:
    _write_json(
        config.output_root / "scheduled" / "forward_outcomes" / "latest_status.json",
        {
            "status": "passed_with_warnings",
            "event_type": "recommendation_included",
            "start_date": "2026-09-10",
            "end_date": "2026-09-14",
            "windows": [5, 10],
            "require_cohort_identity": True,
            "max_events": 2500,
            "summary": {
                "events_scanned": 1,
                "events_skipped_incomplete_identity": skipped,
                "outcomes_written": 2,
            },
            "health": {
                "events_skipped_incomplete_identity": skipped,
                "qualifying_event_count": 1,
            },
        },
    )


def _learning_payload(*, learning_date: str = "2026-09-14") -> dict[str, object]:
    return {
        "cli_schema_version": "daily-recommendation-learning-cli-result.v3",
        "status": "completed",
        "cli_result_updated_at": "2026-09-14T20:47:26+08:00",
        "decision_date": learning_date,
        "decision": "retain_current",
        "decision_reason": "natural_forward_evidence_receipt_missing",
        "candidate_id": "candidate-1",
        "natural_matured_sample_count": 0,
        "formal_order_allowed": False,
        "shadow_only": True,
        "active_pointer": {
            "status": "rule_only",
            "candidate_id": "",
            "effective_date": "2026-09-14",
        },
        "challenger": {
            "status": "pending",
            "last_evaluated_matured_sample_count": 7,
            "last_evaluated_decision_date_count": 2,
        },
        "active_model_natural_evidence": {
            "status": "pending",
            "reason": "active_pointer_not_active",
            "matured_sample_count": 9,
            "matured_decision_date_count": 3,
        },
        "active_model_performance": {
            "status": "clean",
            "reason": "no_active_model_pointer",
        },
        "decision_receipt": {
            "schema_version": "recommendation-calibration-decision-receipt.v2",
            "decision_id": "decision-1",
            "decision_receipt_hash": "sha256:receipt-1",
            "natural_matured_sample_count": 0,
            "natural_matured_decision_date_count": 0,
        },
    }


def _seed_evidence(config: TWStockConfig) -> None:
    repository = EvidenceEventRepository(config, db_path=config.db_file)
    complete = repository.insert_event(
        EvidenceEvent(
            event_id="evt-complete",
            event_hash="sha256:event-complete",
            event_date="2026-09-14",
            decision_date="2026-09-14",
            symbol="1528",
            event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
            event_family="recommendation",
            source_type="scheduled_recommendation",
            source_id="scheduled-rec-1",
            source_snapshot_id="scheduled-rec-1",
            strategy_version_id="strategy-1",
            cost_model_id="cost-1",
            benchmark_id="TAIEX",
            data_quality=EvidenceDataQuality.OBSERVED,
            as_of_date="2026-09-14",
            available_date="2026-09-14",
            metadata={
                "universe_policy_id": "policy-1",
                "universe_policy_hash": "sha256:policy-1",
                "universe_snapshot_id": "snapshot-1",
                "universe_snapshot_hash": "sha256:snapshot-1",
                "horizon_days": 20,
            },
        )
    )
    incomplete = repository.insert_event(
        EvidenceEvent(
            event_id="evt-incomplete",
            event_hash="sha256:event-incomplete",
            event_date="2026-09-14",
            decision_date="2026-09-14",
            symbol="2330",
            event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
            event_family="recommendation",
            source_type="legacy_result",
            source_id="legacy-rec",
            data_quality=EvidenceDataQuality.OBSERVED,
            as_of_date="2026-09-14",
            available_date="2026-09-14",
        )
    )
    repository.upsert_outcomes(
        EvidenceOutcome(
            outcome_id=f"out-{event_id}-{window}",
            event_id=event_id,
            window_days=window,
            outcome_status=EvidenceOutcomeStatus.INSUFFICIENT_FUTURE_DATA,
            data_quality=EvidenceDataQuality.MISSING,
        )
        for event_id in (complete.event_id, incomplete.event_id)
        for window in (5, 10)
    )


def _status(
    *, event_count: int = 1, result_id: str = "scheduled-rec-1"
) -> ScheduledEvidenceStatus:
    return ScheduledEvidenceStatus(
        recommendation_status="passed",
        recommendation_result_id=result_id,
        forward_outcome_status="passed_with_warnings",
        forward_outcome_events_scanned=event_count,
        forward_health_events_skipped_incomplete_identity=1,
    )


def test_daily_journey_matches_scheduled_scope_and_keeps_learning_domains_separate(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_candidate_outputs(config)
    _write_forward_receipt(config)
    _seed_evidence(config)

    daily = DailyInvestmentJourneyService(config, evidence_db_path=config.db_file).build(
        decision_snapshot=None,
        scheduled_status=_status(),
        recommendation_learning_status=_learning_payload(),
        requested_decision_date="2026-09-14",
    )

    assert daily.candidate_symbols == ("1528",)
    assert daily.candidate_status == "candidate_degraded"
    assert daily.candidate_quality == "degraded"
    assert daily.candidate_result_id == "scheduled-rec-1"
    assert all("fixed_threshold" not in reason for reason in daily.candidate_reasons)
    assert any("ranking_method=fixed_threshold" in item for item in daily.source_trace)
    assert daily.evidence_event_count == 1
    assert daily.evidence_daily_event_count == 1
    assert daily.evidence_skipped_incomplete_identity == 1
    assert daily.outcome_total == 2
    assert daily.outcome_ready == 0
    assert daily.outcome_pending == 2
    assert daily.outcome_missing == 0
    assert [(item.window_days, item.total, item.pending) for item in daily.evidence_windows] == [
        (5, 1, 1),
        (10, 1, 1),
    ]
    assert daily.learning is not None
    assert daily.learning.natural_matured_sample_count == 0
    assert daily.learning.candidate_natural_matured_sample_count == 7
    assert daily.learning.active_natural_matured_sample_count == 9
    assert daily.learning.active_pointer_status == "rule_only"
    assert daily.learning.candidate_status == "challenger_candidate"
    assert daily.learning.checked_at == "2026-09-14T20:47:26+08:00"
    # Without a DecisionDesk snapshot the overall journey stays degraded, but
    # the matched forward evidence scope remains independently inspectable.
    assert daily.status == "degraded"
    assert "市場快照缺失" in daily.headline
    assert "cohort identity" not in daily.headline
    assert "recommendation_included" not in daily.headline
    assert any("不完整 identity" in warning for warning in daily.warnings)
    assert any("candidate natural sample" in item for item in daily.diagnostics)


def test_daily_journey_reads_canonical_execution_and_preserves_status_identity(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result_id = "canonical-daily-rec-1"
    artifact_path = _seed_canonical_candidate(config, result_id)
    before = artifact_path.read_bytes()
    before_hash = "sha256:" + hashlib.sha256(before).hexdigest()
    _write_json(
        config.output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json",
        {
            "status": "passed",
            "decision_date": "2026-09-14",
            "data_as_of_date": "2026-09-13",
            "result_id": result_id,
            "source_snapshot_id": "snapshot-1",
            "recommendations_count": 1,
            "snapshot_cohort": {
                "cohort_hash": "sha256:cohort-1",
                "requested_count": 2,
                "eligible_count": 1,
                "degraded_symbols": 1,
                "missing_symbols": 0,
                "coverage_status": "degraded",
                "universe_policy_id": "policy-1",
                "universe_policy_hash": "sha256:policy-1",
                "universe_snapshot_id": "snapshot-1",
                "universe_snapshot_hash": "sha256:snapshot-1",
            },
            "evidence_identity": {
                "strategy_version_id": "strategy-1",
                "strategy_config_id": "config-1",
                "universe_policy_id": "policy-1",
                "universe_policy_hash": "sha256:policy-1",
                "universe_snapshot_id": "snapshot-1",
                "universe_snapshot_hash": "sha256:snapshot-1",
                "benchmark_id": "TAIEX",
                "cost_model_id": "cost-1",
                "horizon_days": 20,
            },
        },
    )
    _write_forward_receipt(config)

    daily = DailyInvestmentJourneyService(config, evidence_db_path=config.db_file).build(
        decision_snapshot=None,
        scheduled_status=_status(result_id=result_id),
        recommendation_learning_status=None,
        requested_decision_date="2026-09-14",
    )

    assert daily.candidate_symbols == ("1528",)
    assert daily.candidate_result_id == result_id
    assert daily.candidate_source_id == result_id
    assert daily.candidate_source_snapshot_id == "snapshot-1"
    assert daily.candidate_data_date == "2026-09-13"
    assert daily.candidate_status == "candidate_degraded"
    assert daily.candidate_quality == "degraded"
    assert daily.candidate_reasons == (
        "1528 恩德｜產業 電機機械｜理由 圖形模式分數+｜排名分數 73.13",
    )
    assert "strategy_version_id=strategy-1" in daily.candidate_identity
    assert any("format=RecommendationExecution" in item for item in daily.source_trace)
    assert any("recommendation_rank=4" in item for item in daily.source_trace)
    assert any(f"raw_artifact_sha256={before_hash}" in item for item in daily.source_trace)
    assert not (config.output_root / "recommendation" / "runs" / f"{result_id}.json").exists()
    assert artifact_path.read_bytes() == before
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == before_hash.removeprefix("sha256:")


def test_daily_journey_accepts_scheduled_cutoff_before_decision_date(
    tmp_path: Path, _scheduled_base_execution: RecommendationExecution
) -> None:
    config = _config(tmp_path)
    result_id = "scheduled-cutoff-before-decision"
    execution = _scheduled_candidate_execution(
        _scheduled_base_execution, result_id, decision_date="2026-10-21"
    )
    artifact_path = _seed_canonical_candidate(config, result_id, execution_override=execution)
    _write_canonical_candidate_status(
        config,
        result_id,
        decision_date="2026-10-21",
        data_as_of_date="2026-10-20",
        execution=execution,
    )

    daily = DailyInvestmentJourneyService(config).build(
        decision_snapshot=None,
        scheduled_status=_status(result_id=result_id),
        recommendation_learning_status=None,
        requested_decision_date="2026-10-21",
    )

    assert daily.candidate_symbols == ("2330",)
    assert daily.candidate_result_id == result_id
    assert daily.candidate_status == "candidate"
    assert daily.candidate_quality == "observed"
    assert daily.candidate_data_date == "2026-10-20"
    assert not any(
        item.startswith("recommendation_execution_as_of_mismatch:")
        for item in daily.diagnostics
    )
    assert artifact_path.is_file()


@pytest.mark.parametrize(
    ("config_overrides", "decision_at"),
    [
        ({}, datetime.fromisoformat("2026-10-20T23:00:00+08:00")),
        ({"cutoff_policy": "unverified_policy"}, None),
    ],
)
def test_invalid_scheduled_clock_or_policy_does_not_fall_back_to_same_day(
    tmp_path: Path,
    _scheduled_base_execution: RecommendationExecution,
    config_overrides: dict[str, object],
    decision_at: datetime | None,
) -> None:
    config = _config(tmp_path)
    result_id = "scheduled-invalid-clock-or-policy"
    execution = _scheduled_candidate_execution(
        _scheduled_base_execution,
        result_id,
        decision_date="2026-10-21",
        config_overrides=config_overrides,
        decision_at=decision_at,
    )
    _seed_canonical_candidate(config, result_id, execution_override=execution)
    _write_canonical_candidate_status(
        config,
        result_id,
        decision_date="2026-10-21",
        data_as_of_date="2026-10-20",
        execution=execution,
    )

    daily = DailyInvestmentJourneyService(config).build(
        decision_snapshot=None,
        scheduled_status=_status(result_id=result_id),
        recommendation_learning_status=None,
        requested_decision_date="2026-10-21",
    )

    assert daily.candidate_symbols == ()
    assert daily.candidate_status == "degraded"
    assert "recommendation_scheduled_decision_date_invalid" in daily.diagnostics


def test_scheduled_result_must_match_status_decision_date(
    tmp_path: Path, _scheduled_base_execution: RecommendationExecution
) -> None:
    config = _config(tmp_path)
    result_id = "scheduled-status-date-mismatch"
    execution = _scheduled_candidate_execution(
        _scheduled_base_execution, result_id, decision_date="2026-10-21"
    )
    _seed_canonical_candidate(config, result_id, execution_override=execution)
    _write_canonical_candidate_status(
        config,
        result_id,
        decision_date="2026-10-20",
        data_as_of_date="2026-10-20",
        execution=execution,
    )

    daily = DailyInvestmentJourneyService(config).build(
        decision_snapshot=None,
        scheduled_status=_status(result_id=result_id),
        recommendation_learning_status=None,
        requested_decision_date="2026-10-21",
    )

    assert daily.candidate_symbols == ()
    assert (
        "recommendation_scheduled_decision_date_mismatch:2026-10-21!=2026-10-20"
        in daily.diagnostics
    )


def test_non_scheduled_execution_keeps_same_day_cutoff_check(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result_id = "non-scheduled-cutoff-mismatch"
    _seed_canonical_candidate(
        config,
        result_id,
        execution_as_of_date=date(2026, 9, 13),
    )
    _write_canonical_candidate_status(
        config,
        result_id,
        decision_date="2026-09-14",
        data_as_of_date="2026-09-13",
    )

    daily = DailyInvestmentJourneyService(config).build(
        decision_snapshot=None,
        scheduled_status=_status(result_id=result_id),
        recommendation_learning_status=None,
        requested_decision_date="2026-09-14",
    )

    assert daily.candidate_symbols == ()
    assert (
        "recommendation_execution_as_of_mismatch:2026-09-13!=2026-09-14"
        in daily.diagnostics
    )


def test_daily_journey_legacy_projection_preserves_exact_identity_rank_and_date(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    result_id = "daily-legacy-exact-payload"
    payload = {
        "result_id": result_id,
        "result_name": "合成 legacy 結果",
        "created_at": "2026-09-14T08:00:00+08:00",
        "config": {},
        "run_context": {"as_of_date": "2026-09-14"},
        "source_id": "legacy-source-42",
        "source_snapshot_id": "legacy-snapshot-42",
        "source_snapshot_hash": "sha256:" + "c" * 64,
        "payload_date": "2026-09-12",
        "recommendations": [
            {
                "stock_code": "2330",
                "stock_name": "台積電",
                "推薦理由": "合成歷史推薦",
                "總分": 88,
                "recommendation_rank": 7,
                "opaque_candidate": {"provider_rank_source": "saved"},
            }
        ],
        "opaque_root": {"retained": [1, {"nested": True}]},
    }
    artifact_path = _seed_registered_legacy_payload(
        config,
        result_id=result_id,
        payload=payload,
    )
    original_bytes = artifact_path.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    _write_json(
        config.output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json",
        {
            "status": "passed",
            "decision_date": "2026-09-14",
            "result_id": result_id,
            "recommendations_count": 1,
            "runs_dir": str(artifact_path.parent),
        },
    )

    daily = DailyInvestmentJourneyService(config).build(
        decision_snapshot=None,
        scheduled_status=_status(result_id=result_id),
        recommendation_learning_status=None,
        requested_decision_date="2026-09-14",
    )

    assert daily.candidate_symbols == ("2330",)
    assert daily.candidate_source_id == "legacy-source-42"
    assert daily.candidate_source_snapshot_id == "legacy-snapshot-42"
    assert daily.candidate_data_date == "2026-09-12"
    assert any("recommendation_rank=7" in item for item in daily.source_trace)
    assert any(f"raw_artifact_sha256=sha256:{original_hash}" in item for item in daily.source_trace)
    assert artifact_path.read_bytes() == original_bytes


def test_daily_journey_legacy_identity_mismatch_fails_closed_without_lineage_fallback(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    result_id = "daily-legacy-identity-conflict"
    payload = {
        "result_id": result_id,
        "result_name": "合成 legacy 結果",
        "created_at": "2026-09-14T08:00:00+08:00",
        "config": {},
        "run_context": {"as_of_date": "2026-09-14"},
        "source_id": "legacy-source-42",
        "source_snapshot_id": "legacy-snapshot-42",
        "source_snapshot_hash": "sha256:" + "c" * 64,
        "recommendations": [
            {"stock_code": "2330", "stock_name": "台積電", "recommendation_rank": 7}
        ],
    }
    artifact_path = _seed_registered_legacy_payload(
        config,
        result_id=result_id,
        payload=payload,
    )
    original_bytes = artifact_path.read_bytes()
    _write_json(
        config.output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json",
        {
            "status": "passed",
            "decision_date": "2026-09-14",
            "result_id": result_id,
            "source_id": "wrapper-source-conflict",
            "source_snapshot_id": "wrapper-snapshot-conflict",
            "recommendations_count": 1,
            "runs_dir": str(artifact_path.parent),
        },
    )

    daily = DailyInvestmentJourneyService(config).build(
        decision_snapshot=None,
        scheduled_status=_status(result_id=result_id),
        recommendation_learning_status=None,
        requested_decision_date="2026-09-14",
    )

    assert daily.candidate_status == "degraded"
    assert daily.candidate_symbols == ()
    assert daily.candidate_source_id is None
    assert daily.candidate_source_snapshot_id is None
    assert any("recommendation_legacy_identity_mismatch:source_id" in item for item in daily.diagnostics)
    assert not any("raw_artifact_sha256=" in item for item in daily.source_trace)
    assert artifact_path.read_bytes() == original_bytes


def test_daily_journey_unindexed_legacy_uses_query_verified_original_payload(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    result_id = "daily-unindexed-legacy"
    runs_dir = config.output_root / "recommendation" / "runs"
    artifact_path = runs_dir / f"{result_id}.json"
    payload = {
        "result_id": result_id,
        "result_name": "合成 unindexed legacy 結果",
        "created_at": "2026-09-14T08:00:00+08:00",
        "config": {},
        "run_context": {"as_of_date": "2026-09-14"},
        "source_id": "unindexed-source-17",
        "source_snapshot_id": "unindexed-snapshot-17",
        "source_snapshot_hash": "sha256:" + "d" * 64,
        "payload_date": "2026-09-11",
        "recommendations": [
            {
                "stock_code": "2603",
                "stock_name": "長榮",
                "推薦理由": "合成 unindexed 候選",
                "recommendation_rank": 3,
                "opaque_candidate": {"provider": "saved"},
            }
        ],
        "opaque_root": {"unindexed_extension": ["preserved"]},
    }
    _write_json(artifact_path, payload)
    original_bytes = artifact_path.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    _write_json(
        config.output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json",
        {
            "status": "passed",
            "decision_date": "2026-09-14",
            "result_id": result_id,
            "recommendations_count": 1,
            "runs_dir": str(runs_dir),
        },
    )

    daily = DailyInvestmentJourneyService(config).build(
        decision_snapshot=None,
        scheduled_status=_status(result_id=result_id),
        recommendation_learning_status=None,
        requested_decision_date="2026-09-14",
    )

    assert daily.candidate_symbols == ("2603",)
    assert daily.candidate_source_id == "unindexed-source-17"
    assert daily.candidate_source_snapshot_id == "unindexed-snapshot-17"
    assert daily.candidate_data_date == "2026-09-11"
    assert any("original_payload_source=unindexed_legacy_file" in item for item in daily.source_trace)
    assert any("integrity_basis=legacy_read_time_hash_only" in item for item in daily.source_trace)
    assert any(f"raw_artifact_sha256=sha256:{original_hash}" in item for item in daily.source_trace)
    assert artifact_path.read_bytes() == original_bytes


def test_daily_journey_registered_legacy_cross_read_byte_change_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    result_id = "daily-legacy-cross-read-change"
    payload = {
        "result_id": result_id,
        "result_name": "合成 legacy 結果",
        "created_at": "2026-09-14T08:00:00+08:00",
        "config": {},
        "run_context": {"as_of_date": "2026-09-14"},
        "source_id": "legacy-source-original",
        "source_snapshot_id": "legacy-snapshot-original",
        "recommendations": [
            {"stock_code": "2330", "stock_name": "台積電", "recommendation_rank": 1}
        ],
    }
    artifact_path = _seed_registered_legacy_payload(
        config,
        result_id=result_id,
        payload=payload,
    )
    _write_json(
        config.output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json",
        {
            "status": "passed",
            "decision_date": "2026-09-14",
            "result_id": result_id,
            "recommendations_count": 1,
            "runs_dir": str(artifact_path.parent),
        },
    )
    service = DailyInvestmentJourneyService(config)
    query = service.recommendation_queries
    original_get_projection = query.get_legacy_original_payload

    def replace_before_original_projection(
        requested_id: str,
        *,
        allow_unindexed_legacy: bool = False,
    ) -> object:
        assert requested_id == result_id
        changed_payload = dict(payload)
        changed_payload["source_id"] = "legacy-source-replaced-between-reads"
        _write_json(artifact_path, changed_payload)
        return original_get_projection(
            requested_id,
            allow_unindexed_legacy=allow_unindexed_legacy,
        )

    monkeypatch.setattr(
        query,
        "get_legacy_original_payload",
        replace_before_original_projection,
    )

    daily = service.build(
        decision_snapshot=None,
        scheduled_status=_status(result_id=result_id),
        recommendation_learning_status=None,
        requested_decision_date="2026-09-14",
    )

    assert daily.candidate_symbols == ()
    assert daily.candidate_status == "degraded"
    assert any("recommendation_run_legacy_payload_read_mismatch" in item for item in daily.diagnostics)
    assert not any("raw_artifact_sha256=" in item for item in daily.source_trace)


def test_daily_journey_legacy_payload_with_unsupported_row_fails_closed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result_id = "daily-legacy-unsupported-row"
    payload = {
        "result_id": result_id,
        "result_name": "合成 legacy 結果",
        "created_at": "2026-09-14T08:00:00+08:00",
        "config": {},
        "run_context": {"as_of_date": "2026-09-14"},
        "source_id": "legacy-source-42",
        "source_snapshot_id": "legacy-snapshot-42",
        "recommendations": [
            {"stock_code": "2330", "stock_name": "台積電", "recommendation_rank": 1},
            "unsupported row",
        ],
    }
    artifact_path = _seed_registered_legacy_payload(
        config,
        result_id=result_id,
        payload=payload,
    )
    _write_json(
        config.output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json",
        {
            "status": "passed",
            "decision_date": "2026-09-14",
            "result_id": result_id,
            "recommendations_count": 2,
            "runs_dir": str(artifact_path.parent),
        },
    )

    daily = DailyInvestmentJourneyService(config).build(
        decision_snapshot=None,
        scheduled_status=_status(result_id=result_id),
        recommendation_learning_status=None,
        requested_decision_date="2026-09-14",
    )

    assert daily.candidate_symbols == ()
    assert daily.candidate_status == "degraded"
    assert any("recommendation_run_legacy_candidate_rows_unsupported" in item for item in daily.diagnostics)


def test_learning_date_is_checked_against_decision_date(tmp_path: Path) -> None:
    config = _config(tmp_path)
    daily = DailyInvestmentJourneyService(config, evidence_db_path=config.db_file).build(
        decision_snapshot=None,
        scheduled_status=ScheduledEvidenceStatus(),
        recommendation_learning_status=_learning_payload(learning_date="2026-09-13"),
        requested_decision_date="2026-09-14",
    )

    assert daily.status == "stale"
    assert any("recommendation_learning_stale_date" in item for item in daily.diagnostics)
    assert daily.learning is not None
    assert daily.learning.candidate_natural_matured_sample_count == 7


def test_invalid_daily_source_status_overrides_matured_learning_claim() -> None:
    decision_date = date(2026, 9, 14)
    snapshot = DecisionDeskSnapshot(
        as_of_date=decision_date,
        generated_at=datetime(2026, 9, 14, 12, 0, 0),
        schema_version=1,
        overall_quality=DecisionDeskQuality.OBSERVED,
        market_regime=MarketRegimeSummary(
            as_of_date=decision_date,
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
            regime_label="趨勢追蹤",
        ),
        market_breadth=MarketBreadthSummary(
            as_of_date=decision_date,
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
        ),
        sector_rotation=SectorRotationSummary(
            as_of_date=decision_date,
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
        ),
        relative_strength_liquidity=RelativeStrengthLiquiditySummary(
            as_of_date=decision_date,
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
        ),
        watchlist_triggers=WatchlistTriggerSummary(
            as_of_date=decision_date,
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
            trigger_count=0,
        ),
        portfolio_alerts=PortfolioAlertSummary(
            as_of_date=decision_date,
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
            alert_count=1,
        ),
        risk_prompts=DecisionDeskRiskPromptSummary(
            as_of_date=decision_date,
            quality=DecisionDeskQuality.OBSERVED,
            warnings=(),
        ),
    )
    candidate = _CandidateRead(symbols=("1528",))
    evidence = _EvidenceRead(event_count=1, outcome_total=1, outcome_ready=1)
    learning = WorkbenchLearningReceipt(
        schema_version="receipt.v2",
        status="completed",
        decision_date=decision_date.isoformat(),
        checked_at="2026-09-14T20:47:26+08:00",
        decision="retain_current",
        decision_reason="natural_forward_evidence_receipt_missing",
        active_pointer_status="active",
        active_natural_matured_sample_count=9,
    )

    for status in ("stale", "future_blocked", "read_failure"):
        headline = _headline(
            decision_date=decision_date.isoformat(),
            decision_snapshot=snapshot,
            candidate=candidate,
            evidence=evidence,
            learning=learning,
            status=status,
        )
        assert "暫不形成投資結論" in headline
        assert "模型已有自然成熟樣本" not in headline
        assert "今日研究候選：1528" not in headline


def test_industry_proxy_is_not_presented_as_true_sector_strength() -> None:
    rotation = SectorRotationSummary(
        as_of_date=date(2026, 9, 14),
        quality=DecisionDeskQuality.DEGRADED,
        warnings=(),
        leading_sector="金融類日報酬兩倍指數",
        trailing_sector="金融類日報酬反向一倍指數",
        meta={"source": "sqlite_industry_indices"},
    )

    summary = _industry_rotation_summary(rotation)

    assert "市場指數代理" in summary
    assert "含槓桿／反向名稱" in summary
    assert "暫不判定強弱" in summary
    assert "領先" not in summary
    assert "落後" not in summary


def test_missing_database_is_not_created_by_daily_read_model(tmp_path: Path) -> None:
    config = _config(tmp_path)
    missing_db = tmp_path / "does-not-exist.sqlite"
    daily = DailyInvestmentJourneyService(config, evidence_db_path=missing_db).build(
        decision_snapshot=None,
        scheduled_status=ScheduledEvidenceStatus(),
        recommendation_learning_status=None,
        requested_decision_date="2026-09-14",
    )

    assert daily.status == "missing"
    assert daily.evidence_event_count == 0
    assert any("evidence_db_missing" in item for item in daily.diagnostics)
    assert not missing_db.exists()


def test_learning_projection_preserves_active_candidate_distinction() -> None:
    payload = _learning_payload()
    payload["active_pointer"] = {
        "status": "active",
        "candidate_id": "candidate-1",
        "effective_date": "2026-09-14",
    }
    receipt = _project_learning_receipt(payload, requested_date="2026-09-14")
    assert isinstance(receipt, WorkbenchLearningReceipt)
    assert receipt.candidate_status == "active_model"
    assert receipt.active_candidate_id == "candidate-1"
    assert receipt.natural_matured_sample_count == 0
