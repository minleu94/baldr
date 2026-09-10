from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import sqlite3
from pathlib import Path
from typing import Any

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.evidence_capture_service import EvidenceCaptureService
from app_module.evidence_event_dtos import (
    EvidenceDataQuality,
    EvidenceEventType,
    EvidenceOutcome,
    EvidenceOutcomeStatus,
)
from app_module.evidence_event_importer_dtos import EvidenceCaptureRequest
from app_module.evidence_event_importers import RecommendationEvidenceImporter
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.evidence_event_service import EvidenceEventService
from app_module.scheduled_forward_outcome_service import run_scheduled_forward_outcomes
from app_module.v4_effectiveness_evaluator import evaluate_v4_effectiveness
from app_module.v4_effectiveness_read_model import (
    V4EffectivenessReadModel,
    load_v4_effectiveness_rows_from_evidence_db,
)
from app_module.v4_evidence_identity import (
    DEFAULT_RETURN_BASIS,
    build_recommendation_universe_identity,
    build_strategy_config_identity,
)
from data_module.config import TWStockConfig


def _config(tmp_path: Path) -> TWStockConfig:
    return TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")


def _weekdays(start: date, count: int) -> list[date]:
    values: list[date] = []
    current = start
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current)
        current += timedelta(days=1)
    return values


def _create_forward_sources(config: TWStockConfig, *, symbols: list[str]) -> list[date]:
    dates = _weekdays(date(2026, 9, 1), 14)
    with sqlite3.connect(config.db_file) as conn:
        conn.executescript(
            """
            CREATE TABLE daily_prices (
                日期 TEXT,
                證券代號 TEXT,
                收盤價 REAL,
                PRIMARY KEY (證券代號, 日期)
            );
            CREATE TABLE market_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                PRIMARY KEY (指數名稱, 日期)
            );
            CREATE TABLE industry_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                PRIMARY KEY (指數名稱, 日期)
            );
            """
        )
        for offset, current in enumerate(dates):
            day = current.isoformat()
            for index, symbol in enumerate(symbols):
                conn.execute(
                    "INSERT INTO daily_prices VALUES (?, ?, ?)",
                    (day, symbol, 100 + index + offset),
                )
            conn.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?)",
                (day, "TAIEX", 10_000 + offset),
            )
            conn.execute(
                "INSERT INTO industry_indices VALUES (?, ?, ?)",
                (day, "semiconductor", 2_000 + offset),
            )
    return dates


class _ResultRepository:
    def __init__(self, results: dict[str, RecommendationResultDTO]) -> None:
        self.results = results

    def load_result(self, result_id: str) -> RecommendationResultDTO | None:
        return self.results.get(result_id)


def _recommendation_result(
    *,
    result_id: str,
    decision_date: date,
    selected_codes: list[str],
    strategy_config: dict[str, Any],
) -> RecommendationResultDTO:
    universe_identity = build_recommendation_universe_identity(
        decision_date=decision_date.isoformat(),
        selection_mode="top_max_stocks",
        industry_filter="全部",
        max_stocks=len(selected_codes),
        requested_codes=None,
        selected_codes=selected_codes,
        source_provider_id="integration-test-provider",
    )
    strategy_identity = build_strategy_config_identity(
        strategy_config,
        max_stocks=len(selected_codes),
        top_n=len(selected_codes),
    )
    context = {
        **strategy_config,
        **strategy_identity,
        **universe_identity,
        "evidence_tier": "forward",
        "return_basis": DEFAULT_RETURN_BASIS,
    }
    recommendations = [
        RecommendationDTO(
            stock_code=symbol,
            stock_name=symbol,
            close_price=100,
            price_change=1,
            total_score=90 - index,
            indicator_score=1,
            pattern_score=1,
            volume_score=1,
            recommendation_reasons="integration",
            industry="semiconductor",
            regime_match=True,
        )
        for index, symbol in enumerate(selected_codes)
    ]
    return RecommendationResultDTO(
        result_id=result_id,
        result_name=f"Integration {decision_date.isoformat()}",
        config=context,
        recommendations=recommendations,
        created_at=f"{decision_date.isoformat()}T08:30:00+08:00",
    )


def test_recommendation_to_outcome_to_read_model_accumulates_cross_day_cohort(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    symbols = [f"{2300 + index}" for index in range(22)]
    dates = _create_forward_sources(config, symbols=symbols)
    repository = EvidenceEventRepository(config)
    results: dict[str, RecommendationResultDTO] = {}
    capture = EvidenceCaptureService(
        EvidenceEventService(repository),
        {"recommendation": RecommendationEvidenceImporter(_ResultRepository(results))},
    )
    strategy_config = {
        "strategy_version_id": "rule-v4",
        "cost_model_id": "gross-close-to-close-no-cost-v1",
        "benchmark_id": "TAIEX",
        "industry_benchmark_id": "semiconductor",
        "horizon_days": 1,
        "filters": {"industry": "全部"},
    }

    for index, decision_date in enumerate(dates[:3]):
        selected = symbols[index : index + 20]
        result = _recommendation_result(
            result_id=f"integration-{decision_date.isoformat()}",
            decision_date=decision_date,
            selected_codes=selected,
            strategy_config=strategy_config,
        )
        results[result.result_id] = result
        first_capture = capture.capture(
            EvidenceCaptureRequest(
                source="recommendation",
                decision_date=decision_date.isoformat(),
                result_id=result.result_id,
                dry_run=False,
                confirm=True,
            )
        )
        assert first_capture.events_inserted == 20
        assert first_capture.events_failed == 0

    duplicate_capture = capture.capture(
        EvidenceCaptureRequest(
            source="recommendation",
            decision_date=dates[0].isoformat(),
            result_id="integration-2026-09-01",
            dry_run=False,
            confirm=True,
        )
    )
    assert duplicate_capture.events_inserted == 0
    assert duplicate_capture.events_skipped_duplicate == 20
    assert len(repository.list_events()) == 60
    first_event = repository.list_events()[0]
    assert first_event.metadata["universe_policy_id"].startswith(
        "recommendation-universe-policy-v1:"
    )
    assert first_event.metadata["universe_snapshot_id"].startswith(
        "recommendation-universe-snapshot-v1:"
    )
    assert first_event.metadata["evidence_lineage"]["declared_tier"] == "forward"

    producer = run_scheduled_forward_outcomes(
        config=config,
        now=datetime.fromisoformat("2026-09-20T06:00:00+08:00"),
        confirm=True,
        allow_production_db_confirm=True,
        windows=(1,),
        start_date=dates[0].isoformat(),
        end_date=dates[-1].isoformat(),
        data_as_of_date=dates[-1].isoformat(),
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED.value,
        require_cohort_identity=True,
        max_events=1000,
    )
    assert producer["status"] == "passed_with_warnings"
    assert producer["summary"]["events_scanned"] == 60
    assert producer["summary"]["events_skipped_incomplete_identity"] == 0
    assert producer["summary"]["outcomes_created"] == 60
    assert producer["health"]["classification"] == "normal_completion"
    assert producer["health"]["cohort_count"] == 1
    assert producer["health"]["cohorts"][0]["decision_day_count"] == 3
    assert producer["health"]["cohorts"][0]["universe_snapshot_count"] == 3
    assert producer["health"]["horizons"]["1"]["ready"] == 60

    rows, warnings = load_v4_effectiveness_rows_from_evidence_db(
        config.db_file,
        window_days=1,
    )
    assert warnings == ()
    assert len(rows) == 60
    report = V4EffectivenessReadModel(
        k=20,
        minimum_decision_days=3,
        minimum_mature_outcomes=20,
    ).build_report(rows=rows)
    assert len(report.slices) == 1
    slice_ = report.slices[0]
    assert slice_.decision_day_count == 3
    assert slice_.mature_outcome_count == 60
    assert slice_.universe_snapshot_count == 3
    assert slice_.universe_component_change_count == 2
    assert slice_.evaluation_status == "ready_for_manual_review_with_warnings"
    assert "cost_model_not_cost_adjusted" in slice_.warnings


def _identity_row(
    *,
    day: str,
    outcome_id: str,
    policy_seed: str = "policy-a",
    strategy_config_id: str = "strategy-a",
    horizon: int = 5,
    cost_model: str = "cost-a",
    benchmark: str = "benchmark-a",
    return_basis: str = DEFAULT_RETURN_BASIS,
    evidence_tier: str = "forward",
    selected_codes: tuple[str, ...] = ("2330", "2317"),
    status: str = "ready",
    return_bp: int = 100,
) -> dict[str, Any]:
    return {
        "decision_date": day,
        "outcome_id": outcome_id,
        "horizon_days": horizon,
        "strategy_version": "rule-v4",
        "strategy_config_id": strategy_config_id,
        "strategy_config_schema": "recommendation-strategy-config.v1",
        "universe_policy_id": policy_seed,
        "universe_policy_hash": f"sha256:{policy_seed}",
        "universe_policy_schema": "recommendation-universe-policy.v1",
        "universe_snapshot_id": f"snapshot-{day}-{policy_seed}",
        "universe_snapshot_hash": f"sha256:snapshot-{day}-{policy_seed}",
        "universe_snapshot_schema": "recommendation-universe-snapshot.v1",
        "universe_snapshot_selected_codes_hash": f"sha256:{','.join(selected_codes)}",
        "cost_model": cost_model,
        "benchmark_id": benchmark,
        "return_basis": return_basis,
        "evidence_tier": evidence_tier,
        "status": status,
        "score_bp": 9000,
        "return_bp": return_bp,
        "benchmark_excess_bp": 10,
        "industry_excess_bp": 5,
    }


def test_policy_snapshot_and_comparison_identities_are_separate() -> None:
    rows: list[dict[str, Any]] = []
    for index, day in enumerate(("2026-09-01", "2026-09-02", "2026-09-03")):
        rows.append(
            _identity_row(
                day=day,
                outcome_id=f"a-{index}",
                selected_codes=("2330", "2317") if index == 0 else ("2330", "2412"),
            )
        )
    rows.extend(
        [
            _identity_row(day="2026-09-01", outcome_id="policy-b", policy_seed="policy-b"),
            _identity_row(
                day="2026-09-01",
                outcome_id="strategy-b",
                strategy_config_id="strategy-b",
            ),
            _identity_row(day="2026-09-01", outcome_id="horizon-10", horizon=10),
            _identity_row(day="2026-09-01", outcome_id="cost-b", cost_model="cost-b"),
            _identity_row(day="2026-09-01", outcome_id="benchmark-b", benchmark="benchmark-b"),
            _identity_row(
                day="2026-09-01",
                outcome_id="basis-b",
                return_basis="open_to_close_event_date",
            ),
            _identity_row(day="2026-09-01", outcome_id="tier-b", evidence_tier="replay"),
        ]
    )

    report = evaluate_v4_effectiveness(
        rows,
        minimum_decision_days=1,
        minimum_mature_outcomes=1,
    )
    assert len(report.slices) == 8
    primary = next(item for item in report.slices if item.universe_id == "policy-a")
    assert primary.decision_day_count == 3
    assert primary.universe_snapshot_count == 3
    assert primary.universe_component_change_count == 1
    assert {item.strategy_config_id for item in report.slices} >= {
        "strategy-a",
        "strategy-b",
    }
    assert {item.evidence_tier for item in report.slices} >= {"forward", "replay"}
    assert {item.horizon_days for item in report.slices} >= {5, 10}
    assert {item.return_basis for item in report.slices} >= {
        DEFAULT_RETURN_BASIS,
        "open_to_close_event_date",
    }

    duplicate = deepcopy(rows[0])
    conflict = deepcopy(rows[0])
    conflict["return_bp"] = -100
    duplicate_report = evaluate_v4_effectiveness(
        [rows[0], duplicate, conflict],
        minimum_decision_days=1,
        minimum_mature_outcomes=1,
    )
    assert duplicate_report.slices[0].mature_outcome_count == 1
    assert "conflicting_duplicate_outcome" in duplicate_report.slices[0].warnings


def test_old_daily_universe_schema_is_diagnosed_without_policy_backfill() -> None:
    row = _identity_row(day="2026-09-01", outcome_id="legacy")
    row.pop("universe_policy_id")
    row.pop("universe_policy_hash")
    row.pop("universe_policy_schema")
    row["universe_id"] = "recommendation-universe-v1:daily"
    row["universe_hash"] = "sha256:daily"
    row["universe_identity_schema"] = "recommendation-universe.v1"
    report = evaluate_v4_effectiveness(
        [row],
        minimum_decision_days=1,
        minimum_mature_outcomes=1,
    )
    assert report.slices == ()
    assert report.warnings == (
        "no_valid_cohort_rows",
        "rows_incomplete_cohort_identity:1",
    )


def test_incomplete_outcomes_are_prioritized_within_bounded_event_scan(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    repository = EvidenceEventRepository(config)
    service = EvidenceEventService(repository)

    def add_event(event_date: str, symbol: str) -> str:
        event = service.record_event(
            event_date=event_date,
            decision_date=event_date,
            symbol=symbol,
            event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
            event_family="recommendation",
            source_type="test",
            source_id=f"source-{event_date}-{symbol}",
            score_bp=9000,
            data_quality=EvidenceDataQuality.OBSERVED,
            as_of_date=event_date,
            available_date=event_date,
            strategy_version_id="rule-v4",
            cost_model_id="cost-a",
            benchmark_id="TAIEX",
            metadata={
                "universe_id": "legacy-universe",
                "horizon_days": 60,
            },
        )
        return event.event_id

    pending_id = add_event("2026-01-01", "2330")
    new_ids = [add_event(f"2026-09-0{index}", f"23{30 + index}") for index in range(1, 4)]
    for event_id in new_ids:
        repository.upsert_outcome(
            EvidenceOutcome(
                outcome_id=f"ready-{event_id}",
                event_id=event_id,
                window_days=60,
                return_basis=DEFAULT_RETURN_BASIS,
                outcome_status=EvidenceOutcomeStatus.READY,
                data_quality=EvidenceDataQuality.OBSERVED,
                forward_return_bp=100,
                metadata={"return_basis": DEFAULT_RETURN_BASIS},
            )
        )

    selected = repository.list_events(
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        limit=1,
        incomplete_outcomes_first=True,
        outcome_windows=(60,),
    )
    assert [event.event_id for event in selected] == [pending_id]
