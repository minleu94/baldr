from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from app_module.dtos import BacktestReportDTO, ValidationStatus
from app_module.research_run_dtos import canonical_json
from app_module.research_run_repository import ResearchRunRepository
from app_module.research_run_service import (
    InjectedResearchRunFailure,
    ResearchRunService,
)
from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
)
from app_module.research_run_dtos import ResearchRunMetadataDTO
from data_module.config import TWStockConfig
from ui_qt.views.backtest.research_run_metadata import (
    build_single_backtest_metadata,
)


def _equity() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-09-23", "2026-09-24"],
            "equity": [Decimal("1000000.00"), Decimal("1012345.67")],
        }
    )


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-09-24"],
            "stock_code": ["1006"],
            "quantity": [100],
            "price": [Decimal("123.456789012345678901")],
        }
    )


def _metadata(run_id: str = "single-decimal-run"):
    report = BacktestReportDTO(
        total_return=Decimal("0.123456789012345678901"),
        annual_return=Decimal("0.234500"),
        sharpe_ratio=Decimal("1.2500"),
        max_drawdown=Decimal("-0.07500"),
        win_rate=Decimal("0.666700"),
        total_trades=1,
        expectancy=Decimal("0.01234567890123456789"),
        details={
            "data_version": "sha256:synthetic-data",
            "data_as_of_date": "2026-09-24",
            "strategy_version": "baseline_score_threshold@1",
            "parameter_contract_version": "strategy-params@1",
            "execution_contract": "next-session-open.v2",
            "portfolio_credibility": {
                "execution_costs": {"fee_bps": Decimal("14.2500")}
            },
            "regime_breakdown": {"Trend": {"return": Decimal("0.0100200")}},
            "benchmark_results": {"TAIEX": {"excess_return": Decimal("0.0012300")}},
            "equity_curve": _equity(),
            "trade_list": _trades(),
        },
        validation_status=ValidationStatus.PASS,
    )
    params = {
        "stock_code": "1006",
        "start_date": "2025-09-25",
        "end_date": "2026-09-25",
        "strategy_id": "baseline_score_threshold",
        "strategy_params": {
            "threshold": Decimal("50.12345678901234567890"),
            "nested": {"weight": Decimal("0.00000000000000000007")},
        },
        "capital": Decimal("1000000.00000000000001"),
        "fee_bps": Decimal("14.2500"),
        "slippage_bps": Decimal("0.5000"),
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "execution_price": "next_open",
        "sizing_mode": "all_in",
    }
    return build_single_backtest_metadata(
        run_id=run_id,
        run_name="Synthetic exact Decimal round trip",
        notes="隔離 synthetic fixture",
        params=params,
        details=report.details,
        report=report,
        created_at=datetime(2026, 9, 25, 12, 0).isoformat(),
    )


def _config(tmp_path: Path) -> TWStockConfig:
    return TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="test",
    )


def _assert_decimal_strings(metadata) -> None:
    assert metadata.original_input["raw_params"]["capital"] == "1000000.00000000000001"
    assert (
        metadata.original_input["raw_params"]["strategy_params"]["nested"]["weight"]
        == "7E-20"
    )
    assert metadata.normalized_params["nested"]["weight"] == "7E-20"
    assert metadata.metrics["total_return"] == "0.123456789012345678901"
    assert metadata.data_manifest["execution_assumptions"]["execution_costs"]["fee_bps"] == "14.2500"
    assert metadata.regime_breakdown["Trend"]["return"] == "0.0100200"
    assert metadata.benchmark_results["TAIEX"]["excess_return"] == "0.0012300"


def test_backtest_report_decimal_metadata_saves_and_fresh_service_reads_exact_strings(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    writer = ResearchRunService(config)
    metadata = _metadata()

    saved = writer.save_run(metadata, _equity(), _trades())
    reader = ResearchRunService(config)
    loaded = reader.load_run_data(saved.run_id)

    assert loaded.metadata.payload_hash == metadata.payload_hash
    _assert_decimal_strings(loaded.metadata)
    assert loaded.equity["equity"].tolist() == [Decimal("1000000.00"), Decimal("1012345.67")]
    assert loaded.trades["price"].tolist() == [Decimal("123.456789012345678901")]

    # Same run_id and payload remains an idempotent retry after the persisted
    # JSON representation converts Decimal leaves to exact strings.
    repeated = reader.save_run(metadata, _equity(), _trades())
    assert repeated.run_id == saved.run_id
    assert repeated.payload_hash == metadata.payload_hash
    _assert_decimal_strings(repeated)


def test_backtest_report_decimal_metadata_recovers_after_hash_stage(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    writer = ResearchRunService(config)
    metadata = _metadata("single-decimal-recovery")

    with pytest.raises(InjectedResearchRunFailure, match="after_hash"):
        writer.save_run(metadata, _equity(), _trades(), fail_at="after_hash")

    recovered = ResearchRunService(config)
    recovered.reconcile_incomplete_saves()
    loaded = ResearchRunService(config).load_run_data(metadata.run_id)

    assert loaded.metadata.payload_hash == metadata.payload_hash
    _assert_decimal_strings(loaded.metadata)
    row = ResearchRunRepository(config).get_raw_metadata_row(metadata.run_id)
    assert row is not None
    assert row["storage_state"] == "committed"
    assert row["integrity_status"] == "valid"


def test_research_run_json_rejects_non_finite_decimal_and_unknown_values(
    tmp_path: Path,
) -> None:
    repository = ResearchRunRepository(_config(tmp_path))
    metadata = _metadata("single-decimal-invalid")

    with pytest.raises(ValueError, match="有限"):
        repository._dto_to_row(
            replace(metadata, metrics={"total_return": Decimal("NaN")})
        )
    with pytest.raises(TypeError):
        repository._dto_to_row(
            replace(metadata, original_input={"unexpected": object()})
        )
    assert repository.get_raw_metadata_row(metadata.run_id) is None
    assert canonical_json({"b": 2, "a": ["x", 1]}) == '{"a":["x",1],"b":2}'


def _frames_with_decimal_attrs() -> tuple[pd.DataFrame, pd.DataFrame]:
    equity = _equity()
    equity.attrs = {
        "execution_contract": "next-session-open.v2",
        "terminal_position": 19000,
        "execution_diagnostics": [
            {"side": "buy", "volume": Decimal("2023591.0"), "filled_shares": 19000}
        ],
    }
    trades = _trades()
    trades.attrs = {
        "execution_costs": {"fee": Decimal("14.2500"), "slippage": None}
    }
    return equity, trades


def test_parquet_attrs_decimal_save_readback_retry_and_reconcile_are_exact(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    equity, trades = _frames_with_decimal_attrs()
    original_equity_attrs = deepcopy(equity.attrs)
    original_trades_attrs = deepcopy(trades.attrs)
    metadata = _metadata("single-decimal-attrs")

    with pytest.raises(InjectedResearchRunFailure, match="after_hash"):
        service.save_run(metadata, equity, trades, fail_at="after_hash")

    assert equity.attrs == original_equity_attrs
    assert trades.attrs == original_trades_attrs
    assert isinstance(equity.attrs["execution_diagnostics"][0]["volume"], Decimal)
    assert isinstance(trades.attrs["execution_costs"]["fee"], Decimal)

    recovered = ResearchRunService(config)
    recovered.reconcile_incomplete_saves()
    loaded = ResearchRunService(config).load_run_data(metadata.run_id)

    assert loaded.equity.attrs == {
        "execution_contract": "next-session-open.v2",
        "terminal_position": 19000,
        "execution_diagnostics": [
            {"side": "buy", "volume": "2023591.0", "filled_shares": 19000}
        ],
    }
    assert loaded.trades.attrs == {
        "execution_costs": {"fee": "14.2500", "slippage": None}
    }
    assert loaded.equity["equity"].tolist() == [
        Decimal("1000000.00"),
        Decimal("1012345.67"),
    ]
    assert loaded.trades["price"].tolist() == [Decimal("123.456789012345678901")]

    retried = ResearchRunService(config).save_run(metadata, equity, trades)
    assert retried.run_id == metadata.run_id
    assert retried.payload_hash == metadata.payload_hash
    assert equity.attrs == original_equity_attrs
    assert trades.attrs == original_trades_attrs


def test_decimal_free_parquet_attrs_keep_the_same_wire_bytes(tmp_path: Path) -> None:
    frame = _equity()
    original = BytesIO()
    frame.to_parquet(original, index=False)

    normalized_copy = ResearchRunService._parquet_frame_copy(frame)
    normalized = BytesIO()
    normalized_copy.to_parquet(normalized, index=False)

    assert frame.attrs == {}
    assert normalized_copy.attrs == {}
    assert original.getvalue() == normalized.getvalue()


def test_portfolio_decimal_manifest_passes_stage_cas_readback_and_reconcile(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    equity = pd.DataFrame(
        {"date": ["2026-09-23", "2026-09-24"], "equity": [1000000, 1012345]}
    )
    equity.attrs = {
        "execution_diagnostics": [{"volume": Decimal("2023591.0")}]
    }
    trades = pd.DataFrame(
        {"date": ["2026-09-24"], "stock_code": ["1006"], "shares": [10]}
    )
    trades.attrs = {"execution_costs": {"fee": Decimal("14.2500")}}
    metadata = ResearchRunMetadataDTO(
        run_id="portfolio-decimal-manifest",
        run_name="TEMP Decimal manifest",
        run_type="recommendation_portfolio",
        strategy_id="synthetic",
        original_input={"config": {"profile_id": "TEMP"}},
        normalized_params={"start_date": "2026-09-23", "end_date": "2026-09-24"},
        metrics={"total_return": "0.0100"},
        data_manifest={
            "execution_contract": "next-session-open.v2",
            "exact_decimal_config": {"fee_bps": Decimal("14.2500")},
            "replay_lineage_status": {
                "schema_version": 1,
                "status": "unavailable",
                "parent_result_id": "portfolio-decimal-parent",
                "reason": "canonical_child_unavailable",
            },
        },
        payload_hash="sha256:placeholder",
        created_at="2026-09-25T12:00:00",
    )
    portfolio_result = RecommendationPortfolioBacktestResultDTO(
        summary={"total_return": "0.0100", "total_trades": 1},
        equity_curve=equity.copy(deep=True),
        trades=trades.copy(deep=True),
        snapshots=[],
        period_holdings=[],
        stock_contribution=[],
        details={"synthetic": True},
    )
    portfolio_result.attach_replay_parent_id("portfolio-decimal-parent")
    original_equity_attrs = deepcopy(equity.attrs)
    original_trades_attrs = deepcopy(trades.attrs)

    with pytest.raises(InjectedResearchRunFailure, match="after_hash"):
        service.save_run(
            metadata,
            equity,
            trades,
            portfolio_result=portfolio_result,
            fail_at="after_hash",
        )

    recovered = ResearchRunService(config)
    recovered.reconcile_incomplete_saves()
    loaded = ResearchRunService(config).load_run_data(metadata.run_id)

    assert loaded.metadata.data_manifest["exact_decimal_config"]["fee_bps"] == "14.2500"
    assert loaded.equity.attrs["execution_diagnostics"][0]["volume"] == "2023591.0"
    assert loaded.trades.attrs["execution_costs"]["fee"] == "14.2500"
    assert loaded.portfolio_result_artifact is not None
    assert equity.attrs == original_equity_attrs
    assert trades.attrs == original_trades_attrs
    assert portfolio_result.equity_curve.attrs == original_equity_attrs
    assert portfolio_result.trades.attrs == original_trades_attrs

    retried = ResearchRunService(config).save_run(
        metadata, equity, trades, portfolio_result=portfolio_result
    )
    assert retried.run_id == loaded.metadata.run_id
    assert retried.payload_hash == loaded.metadata.payload_hash


def test_portfolio_failed_state_cas_normalizes_decimal_manifest(tmp_path: Path) -> None:
    config = _config(tmp_path)
    repository = ResearchRunRepository(config)
    metadata = ResearchRunMetadataDTO(
        run_id="portfolio-decimal-failure-cas",
        run_name="TEMP Decimal failure CAS",
        run_type="recommendation_portfolio",
        strategy_id="synthetic",
        original_input={"config": {"profile_id": "TEMP"}},
        data_manifest={
            ResearchRunRepository.PORTFOLIO_RESULT_REQUIRED_MARKER: True,
            "exact_decimal_config": {"fee_bps": Decimal("14.2500")},
        },
        payload_hash="sha256:failure-cas",
        created_at="2026-09-25T12:00:00",
    )
    repository.insert_metadata(metadata, staging=True)

    repository.mark_portfolio_result_failed(
        metadata.run_id,
        expected_payload_hash=metadata.payload_hash,
        expected_data_manifest=metadata.data_manifest,
        expected_storage_state="staging",
        expected_integrity_status="pending",
    )

    row = repository.get_raw_metadata_row(metadata.run_id)
    assert row is not None
    assert row["storage_state"] == "failed"
    assert row["integrity_status"] == "failed"
