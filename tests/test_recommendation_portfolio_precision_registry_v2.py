"""實際 producer Decimal capture 的隔離 Registry／public reader 回歸。"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.portfolio_result_reader import RecommendationPortfolioResultReader
from app_module.recommendation_portfolio_backtest_service import RecommendationPortfolioBacktestService
from app_module.recommendation_portfolio_dtos import RecommendationPortfolioBacktestResultDTO
from app_module.recommendation_portfolio_result_artifact_v2 import RecommendationPortfolioResultArtifactV2
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_repository import ResearchRunConflictError
from app_module.research_run_service import (
    InjectedResearchRunFailure, ResearchRunIntegrityError, ResearchRunService,
)
from data_module.config import TWStockConfig
from financial_module.banktaiwan_cost_policy import BANKTAIWAN_ELECTRONIC_COST_POLICY_ID


_CAPITAL = Decimal("9007199254740993.01")
_DATES = ("2026-01-02", "2026-01-05", "2026-01-06")


def _producer(*, cancelled: bool = False, named_cost: bool = False) -> RecommendationPortfolioBacktestResultDTO:
    def provider(*_args):
        return [{"stock_code": "2330", "stock_name": "合成股", "total_score": 90,
                 "factor_scores": {"technical": 90}}]

    checks = 0

    def check_cancel() -> bool:
        nonlocal checks
        checks += 1
        return cancelled and checks >= 2

    history = pd.DataFrame([
        {"日期": day, "證券代號": "2330", "證券名稱": "合成股",
         "開盤價": Decimal("100.01"), "收盤價": Decimal("100.00")}
        for day in _DATES
    ])
    return RecommendationPortfolioBacktestService(provider=provider)._run_next_open_portfolio(
        start_date=_DATES[0], end_date=_DATES[-1], profile_id="precision-registry-fixture",
        config={"regime": "Trend"}, history=history, initial_capital=_CAPITAL,
        rebalance_frequency="once", top_n=1, allocation_method="equal_weight", holding_days=10,
        stop_loss_pct=None, take_profit_pct=None, max_participation_rate=None,
        fee_bps=Decimal("0"), slippage_bps=Decimal("0"), tax_bps=Decimal("0"),
        lot_size=1000 if named_cost else 1, check_cancel=check_cancel, include_benchmark=False,
        cost_policy_id=BANKTAIWAN_ELECTRONIC_COST_POLICY_ID if named_cost else None,
        cost_policy_instrument_type="ordinary_stock" if named_cost else None,
        cost_policy_lot_type="full_lot" if named_cost else None,
        parent_result_id="precision-registry-producer-parent",
    )


def _config(tmp_path: Path) -> TWStockConfig:
    return TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output", profile="test")


def _metadata(run_id: str = "precision-registry-run") -> ResearchRunMetadataDTO:
    return ResearchRunMetadataDTO(
        run_id=run_id, run_name="隔離精確觀察", run_type="recommendation_portfolio",
        strategy_id="synthetic-profile", strategy_version="fixture-v1",
        original_input={"config": {"profile_id": "precision-registry-fixture"}},
        normalized_params={"start_date": _DATES[0], "end_date": _DATES[-1]},
        start_date=_DATES[0], end_date=_DATES[-1], capital_cents=900719925474099301,
        data_manifest={"execution_contract": "next-session-open.v2", "replay_lineage_status": {
            "schema_version": 1, "status": "unavailable",
            "parent_result_id": "precision-registry-producer-parent", "reason": "canonical_child_unavailable",
        }}, payload_hash="sha256:caller-placeholder",
    )


def _save(service: ResearchRunService, result: RecommendationPortfolioBacktestResultDTO,
          metadata: ResearchRunMetadataDTO | None = None, *, fail_at: str | None = None):
    return service.save_run(metadata or _metadata(), result.equity_curve, result.trades,
                            portfolio_result=result, fail_at=fail_at)


@pytest.mark.parametrize("cancelled", [False, True])
def test_actual_producer_capture_is_saved_and_public_reader_restores_exact_decimals(tmp_path: Path, cancelled: bool) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    result = _producer(cancelled=cancelled)
    saved = _save(service, result)
    descriptor = saved.data_manifest[service.PORTFOLIO_RESULT_DESCRIPTOR_KEY]
    assert (descriptor["schema_version"], descriptor["schema_revision"]) == ("recommendation-portfolio-result.v2", 2)

    reopened = ResearchRunService(config)
    loaded = reopened.load_run_data(saved.run_id, max_artifact_bytes=16 * 1024 * 1024,
                                   max_total_bytes=32 * 1024 * 1024)
    artifact = loaded.portfolio_result_artifact
    assert type(artifact) is RecommendationPortfolioResultArtifactV2
    assert artifact.period_precision_capture == result.period_precision_capture
    assert artifact.period_precision is None
    assert "cost_model_id" in artifact.missing_precision_identity
    reader = RecommendationPortfolioResultReader(reopened, build_recommendation_composition(config).persistence)
    restored = reader.read(saved.run_id)
    assert type(restored) is RecommendationPortfolioBacktestResultDTO
    assert restored.period_precision_capture == result.period_precision_capture
    assert restored.period_precision_observations == result.period_precision_observations
    assert restored.period_precision_observations[0].equity_decimal == "9007199254740993.01"
    assert restored.period_precision_capture_status == result.period_precision_capture_status
    assert restored.period_precision_capture_reason == result.period_precision_capture_reason
    assert len(restored.period_precision_observations) == (1 if cancelled else 3)
    assert _save(ResearchRunService(config), result) == saved


def test_named_cost_precision_preserves_unknown_authorities_and_does_not_claim_calendar(tmp_path: Path, monkeypatch) -> None:
    original_costs = RecommendationPortfolioBacktestService._next_open_execution_costs
    evaluations = 0

    def count_original_costs(self, **kwargs):
        nonlocal evaluations
        evaluations += 1
        return original_costs(self, **kwargs)

    monkeypatch.setattr(RecommendationPortfolioBacktestService, "_next_open_execution_costs", count_original_costs)
    service = ResearchRunService(_config(tmp_path))
    result = _producer(named_cost=True)
    assert evaluations < 100
    saved = _save(service, result)
    artifact = service.load_run_data(saved.run_id).portfolio_result_artifact
    assert type(artifact) is RecommendationPortfolioResultArtifactV2
    precision = artifact.period_precision
    assert precision is not None
    assert precision.initial_capital_decimal == "9007199254740993.01"
    assert precision.strategy_id == saved.strategy_id
    assert precision.strategy_version == saved.strategy_version
    assert precision.execution_contract_version == "v2"
    assert precision.cost_model_id == BANKTAIWAN_ELECTRONIC_COST_POLICY_ID
    assert precision.equity_parquet_sha256 == saved.equity_parquet_hash
    assert precision.trades_parquet_sha256 == saved.trades_parquet_hash
    assert precision.source_quality_status == "unknown"
    assert precision.currency_code is None and precision.currency_authority is None
    assert precision.expected_session_dates is None and precision.coverage_status == "unknown"
    assert not precision.money_comparable
    assert not precision.performance_eligible and not precision.historical_pit_eligible and not precision.broker_eligible


def test_missing_strategy_version_keeps_capture_without_inventing_execution_version(tmp_path: Path) -> None:
    service = ResearchRunService(_config(tmp_path))
    saved = _save(service, _producer(named_cost=True), replace(_metadata(), strategy_version=""))
    artifact = service.load_run_data(saved.run_id).portfolio_result_artifact
    assert type(artifact) is RecommendationPortfolioResultArtifactV2
    assert artifact.period_precision_capture.execution_contract_version == "v2"
    assert artifact.metadata_strategy_version is None
    assert artifact.period_precision is None
    assert "metadata_strategy_version" in artifact.missing_precision_identity


@pytest.mark.parametrize("fail_at", ["after_hash", "after_first_rename", "after_portfolio_result_rename"])
def test_files_ready_reconciliation_recovers_complete_v2_group(tmp_path: Path, fail_at: str) -> None:
    service = ResearchRunService(_config(tmp_path))
    result = _producer()
    with pytest.raises(InjectedResearchRunFailure):
        _save(service, result, fail_at=fail_at)
    with pytest.raises(ResearchRunIntegrityError):
        service.load_run_data(_metadata().run_id)
    service.reconcile_incomplete_saves()
    artifact = service.load_run_data(_metadata().run_id).portfolio_result_artifact
    assert type(artifact) is RecommendationPortfolioResultArtifactV2
    assert artifact.period_precision_capture == result.period_precision_capture


def test_damaged_v2_staging_is_quarantined_without_publishing(tmp_path: Path) -> None:
    service = ResearchRunService(_config(tmp_path))
    with pytest.raises(InjectedResearchRunFailure):
        _save(service, _producer(), fail_at="after_hash")
    paths = service._paths_for(_metadata().run_id)
    paths["portfolio_result_temp"].write_bytes(b"{}")
    service.reconcile_incomplete_saves()
    assert service.repository.get_raw_metadata_row(_metadata().run_id)["storage_state"] == "failed"
    assert not paths["portfolio_result_final"].exists()
    assert not paths["equity_final"].exists()
    with pytest.raises(ResearchRunIntegrityError):
        service.load_run_data(_metadata().run_id)


def test_same_run_different_capture_is_conflict_and_preserves_original_bytes(tmp_path: Path) -> None:
    service = ResearchRunService(_config(tmp_path))
    result = _producer()
    saved = _save(service, result)
    path = service._paths_for(saved.run_id)["portfolio_result_final"]
    original = path.read_bytes()
    assert result.period_precision_capture is not None
    result.period_precision_capture = replace(result.period_precision_capture, requested_end_date="2026-01-07")
    # 同步 caller metadata 的 requested period，仍不可接管既有 immutable run。
    with pytest.raises(ResearchRunConflictError):
        _save(service, result, replace(_metadata(), end_date="2026-01-07"))
    assert path.read_bytes() == original


@pytest.mark.parametrize("change", [{"capital_cents": 100}, {"capital_cents": 0},
                                   {"start_date": "2026-01-01"}, {"start_date": ""}, {"end_date": ""},
                                   {"execution_price": "", "data_manifest": {}},
                                   {"execution_price": "legacy-same-day-close.v1", "data_manifest": {}}])
def test_capture_metadata_mismatch_is_rejected_before_registry_write(tmp_path: Path, change: dict) -> None:
    service = ResearchRunService(_config(tmp_path))
    metadata = replace(_metadata(), **change)
    if "data_manifest" in change:
        metadata = replace(metadata, data_manifest={"replay_lineage_status": _metadata().data_manifest["replay_lineage_status"]})
    with pytest.raises(ResearchRunIntegrityError):
        _save(service, _producer(), metadata)
    assert not service.repository.db_path.exists()


def test_capture_without_descriptor_is_rejected_before_write(tmp_path: Path) -> None:
    service = ResearchRunService(_config(tmp_path))
    result = _producer()
    result.period_precision_capture = None
    with pytest.raises(ResearchRunIntegrityError, match="不得退回 V1"):
        _save(service, result)
    assert not service.repository.db_path.exists()


def test_v2_load_honours_byte_budget_and_cancellation(tmp_path: Path) -> None:
    service = ResearchRunService(_config(tmp_path))
    saved = _save(service, _producer())
    with pytest.raises(ResearchRunIntegrityError, match="byte_budget"):
        service.load_run_data(saved.run_id, max_artifact_bytes=1)
    with pytest.raises(ResearchRunIntegrityError, match="read_cancelled"):
        service.load_run_data(saved.run_id, check_cancel=lambda: True)


def test_mutated_registry_strategy_is_rejected_even_when_outer_metadata_hash_omits_it(tmp_path: Path) -> None:
    service = ResearchRunService(_config(tmp_path))
    saved = _save(service, _producer())
    with sqlite3.connect(service.repository.db_path) as connection:
        connection.execute("UPDATE research_runs SET strategy_version = ? WHERE run_id = ?", ("wrong", saved.run_id))
    with pytest.raises(ResearchRunIntegrityError, match="strategy identity"):
        service.load_run_data(saved.run_id)
