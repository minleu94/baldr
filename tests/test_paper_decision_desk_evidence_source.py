from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

import pytest

from app_module.decision_desk_dtos import (
    DecisionDeskQuality,
    DecisionDeskRiskPromptSummary,
    MarketBreadthSummary,
    MarketRegimeSummary,
    RelativeStrengthLiquiditySummary,
    SectorRotationSummary,
    WatchlistTriggerSummary,
)
from app_module.decision_desk_snapshot_storage_dtos import build_stored_decision_desk_snapshot
from app_module.decision_desk_dtos import DecisionDeskSnapshot
from app_module.evidence_event_importer_dtos import EvidenceCaptureRequest
from app_module.evidence_event_importers import PortfolioAlertEvidenceImporter
from app_module.evidence_pipeline_runner import (
    EvidencePipelineRunner,
    _DecisionDeskSnapshotSectionProvider,
    _transient_section_available,
)
from app_module.paper_decision_desk_evidence_source import (
    PaperDecisionDeskEvidenceSource,
)
from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioPositionSnapshot,
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotRepository,
)
from data_module.config import TWStockConfig


def _snapshot(snapshot_id: str, decision_date: str) -> PaperPortfolioSnapshot:
    return PaperPortfolioSnapshot(
        snapshot_id=snapshot_id,
        portfolio_id="paper-main",
        decision_date=decision_date,
        source_result_id="scheduled-rec",
        cash=Decimal("341000.00"),
        total_value=Decimal("487350.00"),
        positions=(
            PaperPortfolioPositionSnapshot(
                stock_code="2330",
                quantity=100,
                mark_price=Decimal("100.00"),
                market_value=Decimal("10000.00"),
                weight_bp=1000,
            ),
        ),
    )


def _empty_snapshot(
    snapshot_id: str,
    decision_date: str,
    *,
    zero_quantity_row: bool = False,
) -> PaperPortfolioSnapshot:
    positions = (
        (
            PaperPortfolioPositionSnapshot(
                stock_code="2330",
                quantity=0,
                mark_price=Decimal("100.00"),
                market_value=Decimal("0.00"),
                weight_bp=0,
            ),
        )
        if zero_quantity_row
        else ()
    )
    return PaperPortfolioSnapshot(
        snapshot_id=snapshot_id,
        portfolio_id="paper-main",
        decision_date=decision_date,
        source_result_id="scheduled-rec-empty",
        cash=Decimal("487350.00"),
        total_value=Decimal("487350.00"),
        positions=positions,
    )


def _status(path: Path, snapshot: PaperPortfolioSnapshot, state_db: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "paper-portfolio-daily-status.v1",
                "status": "passed",
                "snapshot_id": snapshot.snapshot_id,
                "decision_date": snapshot.decision_date,
                "cash": str(snapshot.cash),
                "total_value": str(snapshot.total_value),
                "state_db": str(state_db.resolve()),
                "writes_market_db": False,
                "auto_rebalance_allowed": False,
                "changes_advice": False,
                "broker_execution": False,
            }
        ),
        encoding="utf-8",
    )


def _health(path: Path, *, decision_date: str = "2026-09-01", state: str = "WATCH") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "decision_date": decision_date,
                "research_only": True,
                "writes_positions_db": False,
                "auto_action_allowed": False,
                "positions": [
                    {
                        "stock_code": "2330",
                        "state": state,
                        "required_human_fields": ["entry_thesis"],
                        "reasons": ["missing_entry_thesis"],
                        "source_trace": ["health-fixture"],
                    }
                ],
                "warnings": ["health_fixture_warning"],
            }
        ),
        encoding="utf-8",
    )


def _source(tmp_path: Path) -> tuple[PaperDecisionDeskEvidenceSource, Path, Path, Path]:
    operation_root = tmp_path / "paper_execution_eod_replay"
    state_db = operation_root / "paper_portfolio" / "paper_portfolio.sqlite"
    status_path = operation_root / "scheduled" / "paper_portfolio_daily" / "latest_status.json"
    health_path = tmp_path / "health" / "baseline.json"
    repository = PaperPortfolioSnapshotRepository(state_db)
    snapshot = _snapshot("paper-main-20260901", "2026-09-01")
    repository.append(snapshot)
    _status(status_path, snapshot, state_db)
    _health(health_path)
    return (
        PaperDecisionDeskEvidenceSource(
            state_db_path=state_db,
            status_path=status_path,
            health_baseline_path=health_path,
        ),
        state_db,
        status_path,
        health_path,
    )


def _append_empty_snapshot(
    state_db: Path,
    status_path: Path,
    health_path: Path,
    *,
    zero_quantity_row: bool = False,
) -> None:
    repository = PaperPortfolioSnapshotRepository(state_db)
    snapshot = _empty_snapshot(
        "paper-main-20260902",
        "2026-09-02",
        zero_quantity_row=zero_quantity_row,
    )
    repository.append(snapshot)
    _status(status_path, snapshot, state_db)
    health_path.write_text(
        json.dumps(
            {
                "decision_date": snapshot.decision_date,
                "research_only": True,
                "writes_positions_db": False,
                "auto_action_allowed": False,
                "positions": [],
                "diagnostics": [
                    "no_active_paper_positions",
                    "position_health_baseline_is_not_an_exit_instruction",
                ],
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )


def test_paper_source_keeps_real_health_attribution_and_hash_bound_provenance(tmp_path: Path) -> None:
    source, state_db, status_path, health_path = _source(tmp_path)
    before = (state_db.read_bytes(), status_path.read_bytes(), health_path.read_bytes())

    result = source.build(date(2026, 9, 1))

    assert result.status == "degraded"
    assert result.portfolio_alerts.quality is DecisionDeskQuality.DEGRADED
    assert result.portfolio_alerts.alert_codes == ("2330",)
    attribution = result.portfolio_alerts.attributions[0]
    assert attribution.source_label == "paper_position_health"
    assert attribution.condition_status == "warning"
    assert "missing_entry_thesis" in attribution.reasons
    assert result.metadata["paper_snapshot_id"] == "paper-main-20260901"
    assert str(result.metadata["paper_snapshot_rows_sha256"]).startswith("sha256:")
    assert str(result.metadata["paper_health_baseline_sha256"]).startswith("sha256:")
    assert (state_db.read_bytes(), status_path.read_bytes(), health_path.read_bytes()) == before


def test_missing_or_future_health_stays_unknown_without_synthetic_attributions(tmp_path: Path) -> None:
    source, _state_db, _status_path, health_path = _source(tmp_path)
    health_path.unlink()

    missing = source.build(date(2026, 9, 1))
    assert missing.status == "unknown"
    assert missing.portfolio_alerts.quality is DecisionDeskQuality.MISSING
    assert missing.portfolio_alerts.attributions == ()

    _health(health_path, decision_date="2026-09-02")
    future = source.build(date(2026, 9, 1))
    assert future.status == "unknown"
    assert "paper_health_baseline_future_dated" in future.blockers
    assert future.portfolio_alerts.attributions == ()


@pytest.mark.parametrize("zero_quantity_row", (False, True))
def test_verified_empty_paper_snapshot_is_observed_and_scoped_as_research(
    tmp_path: Path,
    zero_quantity_row: bool,
) -> None:
    source, state_db, status_path, health_path = _source(tmp_path)
    _append_empty_snapshot(
        state_db,
        status_path,
        health_path,
        zero_quantity_row=zero_quantity_row,
    )

    result = source.build(date(2026, 9, 2))

    assert result.status == "ready"
    assert result.portfolio_alerts.quality is DecisionDeskQuality.OBSERVED
    assert result.portfolio_alerts.population_status == "no_positions"
    assert result.portfolio_alerts.alert_count == 0
    assert result.portfolio_alerts.alert_codes == ()
    assert result.metadata["source_scope"] == "paper_research"
    assert result.metadata["population_status"] == "no_positions"
    assert result.metadata["paper_position_count"] == 0
    assert result.metadata["paper_health_diagnostics"] == [
        "no_active_paper_positions",
        "position_health_baseline_is_not_an_exit_instruction",
    ]


def test_1418_unproven_position_remains_degraded_and_explicitly_paper_research(
    tmp_path: Path,
) -> None:
    source, state_db, status_path, health_path = _source(tmp_path)
    repository = PaperPortfolioSnapshotRepository(state_db)
    snapshot = PaperPortfolioSnapshot(
        snapshot_id="paper-main-20260902",
        portfolio_id="paper-main",
        decision_date="2026-09-02",
        source_result_id="scheduled-rec-1418-seed",
        cash=Decimal("341000.00"),
        total_value=Decimal("487350.00"),
        positions=(
            PaperPortfolioPositionSnapshot(
                stock_code="1418",
                quantity=3000,
                mark_price=Decimal("30.00"),
                market_value=Decimal("90000.00"),
                weight_bp=1847,
            ),
        ),
    )
    repository.append(snapshot)
    _status(status_path, snapshot, state_db)
    health_path.write_text(
        json.dumps(
            {
                "decision_date": snapshot.decision_date,
                "research_only": True,
                "writes_positions_db": False,
                "auto_action_allowed": False,
                "positions": [
                    {
                        "stock_code": "1418",
                        "state": "WATCH",
                        "entry_thesis": None,
                        "required_human_fields": ["entry_thesis", "invalidation"],
                        "reasons": ["missing_entry_thesis", "missing_invalidation"],
                    }
                ],
                "warnings": [
                    "human_thesis_required_before_health_transition_validation",
                    "paper_position_identity_unproven:1418",
                ],
            }
        ),
        encoding="utf-8",
    )

    result = source.build(date(2026, 9, 2))

    assert result.status == "degraded"
    assert result.portfolio_alerts.quality is DecisionDeskQuality.DEGRADED
    assert result.portfolio_alerts.population_status == "has_positions"
    assert result.portfolio_alerts.alert_codes == ("1418",)
    assert "human_thesis_required_before_health_transition_validation" in result.warnings
    assert "paper_position_identity_unproven:1418" in result.warnings
    assert result.metadata["source_scope"] == "paper_research"
    assert result.metadata["research_only"] is True
    assert result.metadata["formal_credit"] is False


@pytest.mark.parametrize(
    "invalid_source",
    ("missing_snapshot", "bad_status", "bad_schema", "bad_date", "bad_quantity"),
)
def test_invalid_paper_sources_do_not_claim_no_positions(
    tmp_path: Path,
    invalid_source: str,
) -> None:
    source, state_db, status_path, health_path = _source(tmp_path)
    _append_empty_snapshot(
        state_db,
        status_path,
        health_path,
        zero_quantity_row=True,
    )
    if invalid_source == "missing_snapshot":
        with sqlite3.connect(state_db) as connection:
            connection.execute("DELETE FROM paper_portfolio_positions")
            connection.execute("DELETE FROM paper_portfolio_snapshots WHERE snapshot_id = ?", ("paper-main-20260902",))
    elif invalid_source == "bad_status":
        payload = json.loads(status_path.read_text(encoding="utf-8"))
        payload["status"] = "failed"
        status_path.write_text(json.dumps(payload), encoding="utf-8")
    elif invalid_source == "bad_schema":
        with sqlite3.connect(state_db) as connection:
            connection.execute("DROP TABLE paper_portfolio_positions")
            connection.execute(
                "CREATE TABLE paper_portfolio_positions "
                "(snapshot_id TEXT, stock_code TEXT, quantity INTEGER)"
            )
    elif invalid_source == "bad_date":
        with sqlite3.connect(state_db) as connection:
            connection.execute(
                "UPDATE paper_portfolio_snapshots SET decision_date = ? WHERE snapshot_id = ?",
                ("not-a-date", "paper-main-20260902"),
            )
    elif invalid_source == "bad_quantity":
        with sqlite3.connect(state_db) as connection:
            connection.execute(
                "UPDATE paper_portfolio_positions SET quantity = ? WHERE stock_code = ?",
                (-1, "2330"),
            )

    result = source.build(date(2026, 9, 2))

    assert result.status == "unknown"
    assert result.portfolio_alerts.population_status == "unknown"
    assert result.portfolio_alerts.quality is DecisionDeskQuality.MISSING


def test_future_paper_snapshot_is_excluded_and_does_not_become_current_evidence(tmp_path: Path) -> None:
    source, state_db, status_path, health_path = _source(tmp_path)
    repository = PaperPortfolioSnapshotRepository(state_db)
    future = _snapshot("paper-main-20260902", "2026-09-02")
    repository.append(future)
    _status(status_path, future, state_db)

    result = source.build(date(2026, 9, 1))

    assert result.status == "degraded"
    assert result.metadata["paper_snapshot_id"] == "paper-main-20260901"
    assert "paper_snapshot_future_rows_excluded:1" in result.warnings
    assert result.metadata["paper_health_baseline_date"] == "2026-09-01"
    assert health_path.is_file()


def test_runner_persists_paper_provenance_and_importer_consumes_same_snapshot(tmp_path: Path) -> None:
    source, _state_db, _status_path, _health_path = _source(tmp_path)
    result = source.build(date(2026, 9, 1))
    base = DecisionDeskSnapshot(
        as_of_date=date(2026, 9, 1),
        generated_at=__import__("datetime").datetime(2026, 9, 1, 5, 15),
        schema_version=2,
        overall_quality=DecisionDeskQuality.OBSERVED,
        market_regime=MarketRegimeSummary(date(2026, 9, 1), DecisionDeskQuality.OBSERVED, ()),
        market_breadth=MarketBreadthSummary(date(2026, 9, 1), DecisionDeskQuality.OBSERVED, ()),
        sector_rotation=SectorRotationSummary(date(2026, 9, 1), DecisionDeskQuality.OBSERVED, ()),
        relative_strength_liquidity=RelativeStrengthLiquiditySummary(date(2026, 9, 1), DecisionDeskQuality.OBSERVED, ()),
        watchlist_triggers=WatchlistTriggerSummary(date(2026, 9, 1), DecisionDeskQuality.OBSERVED, ()),
        portfolio_alerts=result.portfolio_alerts,
        risk_prompts=DecisionDeskRiskPromptSummary(date(2026, 9, 1), DecisionDeskQuality.OBSERVED, ()),
    )
    runner = EvidencePipelineRunner(TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output"), paper_evidence_source=source)
    merged, metadata = runner._apply_paper_evidence_source(base, date(2026, 9, 1))
    stored = build_stored_decision_desk_snapshot(
        merged,
        decision_date="2026-09-01",
        metadata={"paper_evidence_source": metadata},
    )
    provider = _DecisionDeskSnapshotSectionProvider(stored, "portfolio-alert")
    imported = PortfolioAlertEvidenceImporter(provider).collect(
        EvidenceCaptureRequest(source="portfolio-alert", decision_date="2026-09-01")
    )

    assert merged.overall_quality is DecisionDeskQuality.DEGRADED
    assert merged.portfolio_alerts.attributions[0].source_label == "paper_position_health"
    assert any(prompt.code == "2330" for prompt in merged.risk_prompts.prompts)
    assert provider.metadata["paper_evidence_source"]["paper_snapshot_id"] == "paper-main-20260901"
    assert imported.event_payloads[0]["metadata"]["paper_evidence_source"]["paper_snapshot_id"] == "paper-main-20260901"


def test_degraded_transient_section_is_available_but_not_capture_ready() -> None:
    payload = {"as_of_date": "2026-09-01", "quality": "degraded", "warnings": ["stale"]}
    assert _transient_section_available(payload) is True
