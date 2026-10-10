from __future__ import annotations

from datetime import date
from decimal import Decimal

import app_module.paper_portfolio_weekly_evidence_service as evidence_module
from app_module.paper_equal_weight_benchmark_ledger import EqualWeightBenchmarkEntry
from app_module.paper_portfolio_snapshot_repository import PaperPortfolioSnapshot
from app_module.paper_portfolio_weekly_evidence_service import (
    PaperPortfolioWeeklyEvidenceService,
)
from app_module.paper_portfolio_weekly_report import (
    SNAPSHOT_BASIS_GROSS_BEFORE_FILL_COST,
    SNAPSHOT_BASIS_NET_AFTER_FILL_COST,
    PaperPortfolioWeeklyReportService,
    PaperTradeCostRecord,
    _in_preopen_cost_window,
)


def _snapshot(day: str, value: str) -> PaperPortfolioSnapshot:
    return PaperPortfolioSnapshot(
        snapshot_id=f"snapshot-{day}",
        portfolio_id="paper-main",
        decision_date=day,
        source_result_id="source-result",
        cash=Decimal(value),
        total_value=Decimal(value),
        positions=(),
    )


def _benchmark(day: str, value: str) -> EqualWeightBenchmarkEntry:
    return EqualWeightBenchmarkEntry(
        benchmark_id="paper-main-equal",
        decision_date=day,
        constituents=("2330",),
        units=(("2330", Decimal("1")),),
        total_value=Decimal(value),
    )


def test_net_nav_roundtrip_adds_costs_for_report_gross_without_deducting_again() -> None:
    report = PaperPortfolioWeeklyReportService().build(
        portfolio_snapshots=(
            _snapshot("2026-10-05", "500000.00"),
            _snapshot("2026-10-06", "504477.80"),
        ),
        benchmark_entries=(
            _benchmark("2026-10-05", "500000.00"),
            _benchmark("2026-10-06", "500000.00"),
        ),
        trade_costs=(
            PaperTradeCostRecord("2026-10-05", Decimal("522.20"), 89),
            PaperTradeCostRecord("2026-10-06", Decimal("999.99"), 900),
        ),
        expected_trading_days=2,
        snapshot_basis=SNAPSHOT_BASIS_NET_AFTER_FILL_COST,
        cost_window_coverage_proven=True,
    )

    assert report.snapshot_basis == SNAPSHOT_BASIS_NET_AFTER_FILL_COST
    assert report.net_return_bp == 89
    assert report.gross_return_bp == 100
    assert report.gross_return_method == "net_nav_plus_verified_period_cost_addback"
    assert report.total_cost == Decimal("522.20")
    assert "gross_cost_addback_is_not_counterfactual" in report.warnings
    assert report.data_quality == "DEGRADED"


def test_legacy_pure_api_keeps_gross_snapshot_contract() -> None:
    report = PaperPortfolioWeeklyReportService().build(
        portfolio_snapshots=(
            _snapshot("2026-10-05", "500000.00"),
            _snapshot("2026-10-06", "505000.00"),
        ),
        benchmark_entries=(
            _benchmark("2026-10-05", "500000.00"),
            _benchmark("2026-10-06", "500000.00"),
        ),
        trade_costs=(PaperTradeCostRecord("2026-10-05", Decimal("522.20"), 89),),
        expected_trading_days=2,
    )

    assert report.snapshot_basis == SNAPSHOT_BASIS_GROSS_BEFORE_FILL_COST
    assert report.gross_return_bp == 100
    assert report.net_return_bp == 89


def test_preopen_cost_window_includes_start_and_excludes_end() -> None:
    start = "2026-10-05"
    end = "2026-10-06"
    assert _in_preopen_cost_window(start, start, end)
    assert not _in_preopen_cost_window(end, start, end)


def test_unproven_cost_window_cannot_build_a_report() -> None:
    try:
        PaperPortfolioWeeklyReportService().build(
            portfolio_snapshots=(
                _snapshot("2026-10-05", "500000.00"),
                _snapshot("2026-10-06", "505000.00"),
            ),
            benchmark_entries=(
                _benchmark("2026-10-05", "500000.00"),
                _benchmark("2026-10-06", "500000.00"),
            ),
            trade_costs=(),
            expected_trading_days=2,
            cost_window_coverage_proven=False,
        )
    except ValueError as exc:
        assert "proven [S,D)" in str(exc)
    else:
        raise AssertionError("unproven costs must not produce a weekly report")


def test_adapter_keeps_legacy_basis_unknown_and_skips_metrics(monkeypatch, tmp_path) -> None:
    start = "2026-10-05"
    end = "2026-10-06"
    monkeypatch.setattr(evidence_module, "paper_portfolio_today", lambda: date.fromisoformat(end))
    service = PaperPortfolioWeeklyEvidenceService(output_root=tmp_path / "output")
    snapshots = (_snapshot(start, "500000.00"), _snapshot(end, "504477.80"))
    benchmarks = (_benchmark(start, "500000.00"), _benchmark(end, "500000.00"))
    costs = (PaperTradeCostRecord(start, Decimal("522.20"), 89),)

    monkeypatch.setattr(service, "_read_snapshots", lambda *args, **kwargs: snapshots)
    monkeypatch.setattr(service, "_read_benchmarks", lambda *args, **kwargs: benchmarks)
    monkeypatch.setattr(service, "_read_costs", lambda *args, **kwargs: costs)

    def metrics_must_not_run(**kwargs):
        raise AssertionError("unknown snapshot basis must block metrics")

    monkeypatch.setattr(service._report_service, "build", metrics_must_not_run)

    result = service.build(
        period_start=start,
        period_end=end,
        expected_trading_days=2,
    )

    assert result.status == "degraded"
    assert result.weekly_report_status == "not_computable"
    assert result.report is None
    assert "paper_weekly_snapshot_cost_basis_unknown" in result.blockers
    assert "paper_weekly_snapshot_ledger_window_unproven" in result.blockers
    assert result.observed_cost_disclosure_total == Decimal("522.20")
    payload = result.to_dict()
    assert payload["cost_window_contract"] == "[period_start, period_end)"
    assert payload["observed_cost_disclosure_total"] == "522.20"
    assert payload["cost_disclosure_complete"] is False
    assert payload["report"] is None


def test_missing_execution_gap_keeps_partial_cost_total_unknown_and_skips_metrics(
    monkeypatch, tmp_path
) -> None:
    start = "2026-10-05"
    end = "2026-10-06"
    monkeypatch.setattr(evidence_module, "paper_portfolio_today", lambda: date.fromisoformat(end))
    service = PaperPortfolioWeeklyEvidenceService(output_root=tmp_path / "output")
    snapshots = (_snapshot(start, "500000.00"), _snapshot(end, "504477.80"))
    benchmarks = (_benchmark(start, "500000.00"), _benchmark(end, "500000.00"))
    valid_costs = (PaperTradeCostRecord(start, Decimal("522.20"), 89),)
    invalid_row = {
        "fill_id": "fill-missing-gap",
        "order_id": "order-missing-gap",
        "portfolio_id": "paper-main",
        "event_date": start,
        "stock_code": "2330",
        "side": "buy",
        "requested_quantity": 1,
        "filled_quantity": 1,
        "reference_price": "500.00",
        "fill_price": "500.10",
        "commission": "1.00",
        "tax": "0.00",
        "slippage_cost": "0.10",
        "turnover_bp": 89,
        "execution_gap_bp": None,
        "status": "filled",
        "source_event_id": "source-event-missing-gap",
        "override_reason": None,
        "source_type": "paper_simulation",
        "research_only": 1,
        "broker_order_allowed": 0,
        "auto_rebalance_allowed": 0,
    }

    monkeypatch.setattr(service, "_read_snapshots", lambda *args, **kwargs: snapshots)
    monkeypatch.setattr(service, "_read_benchmarks", lambda *args, **kwargs: benchmarks)

    def read_costs_with_bad_row(*args, blockers, **kwargs):
        try:
            evidence_module._fill_from_row(invalid_row)
        except (TypeError, ValueError, ArithmeticError):
            blockers.append("paper_trade_ledger_invalid_row")
        return valid_costs

    monkeypatch.setattr(service, "_read_costs", read_costs_with_bad_row)

    def metrics_must_not_run(**kwargs):
        raise AssertionError("invalid cost rows must block metrics")

    monkeypatch.setattr(service._report_service, "build", metrics_must_not_run)
    result = service.build(
        period_start=start,
        period_end=end,
        expected_trading_days=2,
    )

    assert "paper_trade_ledger_invalid_row" in result.blockers
    assert "paper_weekly_snapshot_cost_basis_unknown" in result.blockers
    assert result.cost_record_count == 1
    assert result.observed_cost_disclosure_total is None
    assert result.report is None
