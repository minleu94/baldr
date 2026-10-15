from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from app_module.research_history_lookup import ResearchHistoryLookup
from app_module.research_run_dtos import ResearchRunMetadataDTO, canonical_json
from app_module.research_run_service import ResearchRunService
from app_module.single_backtest_metrics_contract import (
    SINGLE_BACKTEST_METRICS_KEY,
    SINGLE_BACKTEST_METRIC_NAMES,
    capture_single_backtest_metrics_contract,
)
from app_module.strategy_historical_performance_read_service import (
    HistoricalComparabilityState,
    HistoricalMetricsState,
    HistoricalQualificationState,
    HistoricalReadState,
    StrategyHistoricalPerformanceReadService,
)
from backtest_module.performance_metrics import PerformanceAnalyzer
from data_module.config import TWStockConfig
from test_strategy_historical_performance_read_service import (
    _assert_blocked_and_empty,
    _inventory,
    _saved_registry_case,
)


def _saved_versioned_single_stock_case(tmp_path: Path, *, corrupt: str = ""):
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="test",
    )
    equity_dates = ("2025-10-01", "2026-01-02", "2026-10-01")
    equity = pd.DataFrame(
        {"date": equity_dates, "equity": [100_000, 104_000, 105_000]},
        index=pd.to_datetime(equity_dates),
    )
    analyzer = PerformanceAnalyzer()
    trades = analyzer.create_trade_list([], initial_capital=100_000)
    original_metrics = analyzer.summarize(
        [], equity, initial_capital=100_000
    )
    raw_metrics = {
        name: getattr(original_metrics, name)
        for name in SINGLE_BACKTEST_METRIC_NAMES
    }
    contract = capture_single_backtest_metrics_contract(
        original_metrics,
        equity=equity,
        trades=trades,
        stock_code="2330",
    )
    saved_metrics = dict(raw_metrics)
    if corrupt == "wrong_node":
        contract["stock_code"] = "2317"
    elif corrupt == "metrics_hash":
        saved_metrics["total_return"] = 987654.0
    elif corrupt == "table_count":
        contract["equity_rows"] = len(equity) + 1
    elif corrupt == "date_mismatch":
        equity.loc[equity.index[-1], "date"] = "2026-09-30"
    if corrupt in {"wrong_node", "table_count"}:
        unsigned_contract = {
            key: value for key, value in contract.items() if key != "contract_sha256"
        }
        contract["contract_sha256"] = sha256(
            canonical_json(unsigned_contract).encode("utf-8")
        ).hexdigest()

    metadata = ResearchRunMetadataDTO(
        run_id="inc49-versioned-" + (corrupt or "valid"),
        run_name="增量49合成單股回測",
        run_type="single_backtest",
        strategy_id="synthetic-single-stock",
        strategy_version="v1",
        parameter_contract_version="synthetic-params.v1",
        normalized_params={"fixture": "explicit-synthetic-single-stock"},
        universe=["2330"],
        start_date="2025-10-01",
        end_date="2026-10-01",
        data_cutoff_date="2026-10-01",
        data_fingerprint="synthetic-source-fingerprint",
        fingerprint_algorithm="synthetic-sha256-v1",
        data_manifest={
            "run_status": "completed",
            "execution_contract": "next-session-open.v2",
            "source_label": "explicit-synthetic-test-only",
            SINGLE_BACKTEST_METRICS_KEY: contract,
        },
        capital_cents=10_000_000,
        fee_bp_x100=0,
        slippage_bp_x100=0,
        execution_price="next-session-open.v2",
        sizing_mode="fixed",
        metrics=saved_metrics,
        payload_hash="sha256:inc49-synthetic-payload",
        created_at="2026-10-15T12:00:00",
    )

    saved = ResearchRunService(config).save_run(metadata, equity, trades)
    lookup = ResearchHistoryLookup(registry=ResearchRunService(config))
    entry = next(
        item
        for item in lookup.list_entries(limit=100).entries
        if item.run_id == saved.run_id
    )
    return config, saved, lookup, entry, raw_metrics


def _assert_summary_is_unknown(summary) -> None:
    assert all(value is None for value in asdict(summary).values())


def test_versioned_single_stock_read_projects_original_metrics_without_qualifying(
    tmp_path: Path,
) -> None:
    _, saved, lookup, entry, raw_metrics = _saved_versioned_single_stock_case(tmp_path)
    before = _inventory(tmp_path)

    card = StrategyHistoricalPerformanceReadService(lookup).read_selected(entry)

    assert card.read_state is HistoricalReadState.VERIFIED
    assert card.metrics_state is HistoricalMetricsState.DECLARED
    assert card.metrics_reason == "saved_original_analytics_not_performance_qualification"
    assert card.comparability_state is HistoricalComparabilityState.NOT_ASSESSED
    assert card.qualification_state is HistoricalQualificationState.UNKNOWN
    assert card.identity is not None
    assert card.identity.run_id == saved.run_id
    assert card.identity.run_type == "single_backtest"
    assert card.identity.universe == ("2330",)
    assert card.provenance is not None
    assert card.provenance.metadata_sha256 == entry.metadata_sha256
    assert card.provenance.context_sha256 == entry.context_sha256
    assert card.provenance.equity_parquet_sha256 == saved.equity_parquet_hash
    assert card.provenance.trades_parquet_sha256 == saved.trades_parquet_hash

    assert card.summary.stock_count == 1
    assert card.summary.signal_count is None
    assert card.summary.completed_trades == 0
    assert card.summary.average_trade_return is None
    assert card.summary.total_return == Decimal(str(raw_metrics["total_return"]))
    assert card.summary.annual_return == Decimal(str(raw_metrics["annual_return"]))
    assert card.summary.cagr == Decimal(str(raw_metrics["annual_return"]))
    assert card.summary.max_drawdown == Decimal(str(raw_metrics["max_drawdown"]))
    assert card.summary.sharpe_ratio == Decimal(str(raw_metrics["sharpe_ratio"]))
    assert card.summary.win_rate is None
    assert card.summary.expectancy is None
    assert card.summary.profit_factor is None

    assert card.details is not None
    assert card.details.metadata_json is not None
    saved_metadata = json.loads(card.details.metadata_json)
    assert saved_metadata["metrics"] == raw_metrics
    contract = saved_metadata["data_manifest"][SINGLE_BACKTEST_METRICS_KEY]
    assert contract["unit"] == "ratio_except_total_trades_count_and_sharpe_ratio"
    assert contract["closed_pairs"] == card.details.trades.row_count == 0
    assert contract["equity_rows"] == card.details.equity.row_count == 3
    assert contract["metric_status"]["total_trades"] == "observed"
    assert contract["metric_status"]["win_rate"] == "unavailable"
    assert contract["metric_status"]["expectancy"] == "unavailable"
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize(
    "corrupt", ("wrong_node", "metrics_hash", "table_count", "date_mismatch")
)
def test_versioned_contract_mismatch_is_rejected_before_registry_writes(
    tmp_path: Path, corrupt: str
) -> None:
    before = _inventory(tmp_path)
    with pytest.raises(ValueError):
        _saved_versioned_single_stock_case(tmp_path, corrupt=corrupt)
    assert _inventory(tmp_path) == before


def test_existing_unversioned_run_stays_unversioned_with_empty_summary(
    tmp_path: Path,
) -> None:
    _, saved, lookup, entry = _saved_registry_case(tmp_path)
    before = _inventory(tmp_path)

    card = StrategyHistoricalPerformanceReadService(lookup).read_selected(entry)

    assert card.read_state is HistoricalReadState.VERIFIED
    assert card.metrics_state is HistoricalMetricsState.UNVERSIONED
    assert card.qualification_state is HistoricalQualificationState.UNKNOWN
    _assert_summary_is_unknown(card.summary)
    assert card.details is not None and card.details.metadata_json is not None
    saved_metadata = json.loads(card.details.metadata_json)
    assert SINGLE_BACKTEST_METRICS_KEY not in saved_metadata["data_manifest"]
    assert saved_metadata["metrics"]["total_return"] == 0.0
    assert saved_metadata["metrics"]["total_trades"] == 0
    assert card.provenance is not None
    assert card.provenance.equity_parquet_sha256 == saved.equity_parquet_hash
    assert card.provenance.trades_parquet_sha256 == saved.trades_parquet_hash
    assert _inventory(tmp_path) == before
