from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path

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
from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus
from app_module.workbench_dtos import WorkbenchLearningReceipt
from data_module.config import TWStockConfig


def _config(tmp_path: Path) -> TWStockConfig:
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    config.db_file = tmp_path / "evidence.sqlite"
    config.research_run_db_file = tmp_path / "research.sqlite"
    return config


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
    _write_json(
        runs_dir / f"{result_id}.json",
        {
            "result_id": result_id,
            "recommendations": [
                {
                    "證券代號": "1528",
                    "證券名稱": "恩德",
                    "產業": "電機機械",
                    "推薦理由": "圖形模式分數+",
                    "總分": "73.13",
                    "ranking_method": "fixed_threshold",
                }
            ],
            "run_context": {
                "as_of_date": "2026-09-14",
                "data_as_of_date": "2026-09-14",
            },
        },
    )


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


def _status(*, event_count: int = 1) -> ScheduledEvidenceStatus:
    return ScheduledEvidenceStatus(
        recommendation_status="passed",
        recommendation_result_id="scheduled-rec-1",
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
