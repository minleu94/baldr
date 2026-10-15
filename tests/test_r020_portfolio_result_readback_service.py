"""R020 Stage C：以 synthetic TEMP 驗證完整 portfolio Registry 讀回。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    RecommendationExecution,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.portfolio_result_reader import (
    PortfolioResultReadbackUnavailable,
    PortfolioResultUnavailableReason,
    RecommendationPortfolioResultReadCancelledError,
    RecommendationPortfolioResultReadbackError,
    RecommendationPortfolioResultReader,
)
from app_module.recommendation.replay_lineage import (
    ReplayLineageChildV1,
    ReplayLineageSidecarV1,
)
from app_module.recommendation.replay_lineage_service import (
    persist_replay_lineage_children,
)
from app_module.recommendation_portfolio_dtos import (
    PeriodHoldingDTO,
    RecommendationPortfolioBacktestResultDTO,
    RecommendationSnapshotDTO,
    StockContributionDTO,
)
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_service import ResearchRunService
from data_module.config import TWStockConfig
from decision_module.recommendation.contracts import DecisionBatch, RecommendationItem


_PARENT_ID = "portfolio-parent-r020-stage-c"
_FIRST_DATE = date(2026, 9, 15)
_SECOND_DATE = date(2026, 9, 22)


def _config(tmp_path: Path) -> TWStockConfig:
    return TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="test",
    )


def _execution(snapshot_date: date, *, parent_id: str = _PARENT_ID) -> RecommendationExecution:
    return RecommendationExecution(
        result_id=f"stage-c-child-{snapshot_date:%Y%m%d}",
        request=Request(as_of_date=snapshot_date),
        context=Context(as_of_date=snapshot_date),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(
            items=(
                RecommendationItem(
                    stock_code=f"S{snapshot_date.day:02d}",
                    stock_name="合成標的",
                    rule_score=Decimal("84.25"),
                ),
            )
        ),
        related_references=(
            VersionReference(ReferenceKind.REPLAY_PARENT, parent_id),
        ),
    )


def _snapshot(snapshot_date: date, *, include_child: bool) -> RecommendationSnapshotDTO:
    snapshot = RecommendationSnapshotDTO(
        as_of_date=snapshot_date.isoformat(),
        profile_id="synthetic-stage-c-profile",
        strategy_config={"strategy_id": "recommendation_replay", "top_n": 2},
        regime="Trend",
        recommendations=[
            {
                "stock_code": f"S{snapshot_date.day:02d}",
                "stock_name": "合成標的",
                "total_score": 84.25,
                "selection_reason": "獨立固定的合成理由",
                "reason_tags": ["rule_selected"],
            }
        ],
        diagnostics=[f"snapshot-{snapshot_date:%Y%m%d}"],
    )
    snapshot.attach_replay_parent_id(_PARENT_ID)
    if include_child:
        snapshot.attach_canonical_execution(_execution(snapshot_date))
    return snapshot


def _portfolio_result(
    *,
    snapshots: list[RecommendationSnapshotDTO] | None = None,
    include_children: bool = True,
    equity: pd.DataFrame | None = None,
    trades: pd.DataFrame | None = None,
) -> RecommendationPortfolioBacktestResultDTO:
    result = RecommendationPortfolioBacktestResultDTO(
        summary={
            "status": "completed",
            "total_return": "0.0125",
            "cash_cents": 250_000,
            "snapshot_count": 2,
        },
        equity_curve=(
            equity.copy(deep=True)
            if equity is not None
            else pd.DataFrame(
                [
                    {"日期": "2026-09-15", "portfolio_value": 1_010_000},
                    {"日期": "2026-09-22", "portfolio_value": 1_012_500},
                ]
            )
        ),
        trades=(
            trades.copy(deep=True)
            if trades is not None
            else pd.DataFrame(
                [
                    {"日期": "2026-09-16", "stock_code": "S15", "side": "buy", "shares": 10},
                    {"日期": "2026-09-23", "stock_code": "S22", "side": "sell", "shares": 10},
                ]
            )
        ),
        snapshots=(
            snapshots
            if snapshots is not None
            else [
                _snapshot(_SECOND_DATE, include_child=include_children),
                _snapshot(_FIRST_DATE, include_child=include_children),
            ]
        ),
        period_holdings=[
            PeriodHoldingDTO(
                rebalance_date="2026-09-15",
                stock_code="S15",
                stock_name="合成標的",
                rank=1,
                total_score=84.25,
                factor_scores={"rule": 84.25},
                allocation_amount=500_000.0,
                allocation_weight=0.5,
                entry_date="2026-09-16",
                entry_price=100.0,
                planned_exit_date="2026-09-23",
                actual_exit_date="2026-09-23",
                actual_exit_price=101.25,
                exit_reason="scheduled_exit",
                holding_days=5,
                return_pct=0.0125,
                shares=10,
                pnl_cents=6_250,
            )
        ],
        stock_contribution=[
            StockContributionDTO(
                stock_code="S15",
                stock_name="合成標的",
                selected_count=1,
                total_pnl=62.5,
                avg_return_pct=0.0125,
                win_rate=1.0,
                worst_return_pct=0.0125,
            )
        ],
        selection_diagnostics=["synthetic selection diagnostic"],
        improvement_hints=["synthetic improvement hint"],
        details={
            "cash_cents": 250_000,
            "manifest": {"fixture": "stage-c-v1", "source_hash": "sha256:synthetic"},
            "nested": {"preserve": ["list", "order"]},
        },
    )
    result.attach_replay_parent_id(_PARENT_ID)
    return result


def _metadata(
    run_id: str,
) -> ResearchRunMetadataDTO:
    return ResearchRunMetadataDTO(
        run_id=run_id,
        run_name="Stage C synthetic portfolio",
        run_type="recommendation_portfolio",
        strategy_id="recommendation_replay",
        original_input={"config": {"profile_id": "synthetic-stage-c-profile"}},
        normalized_params={"start_date": "2026-09-15", "end_date": "2026-09-22"},
        metrics={"total_return": "0.0125"},
        data_manifest={"synthetic_source": {"version": "stage-c-v1"}},
        payload_hash="sha256:caller-placeholder",
        created_at="2026-09-24T10:00:00-07:00",
    )


def _services(tmp_path: Path) -> tuple[
    ResearchRunService,
    RecommendationExecutionPersistence,
    RecommendationPortfolioResultReader,
]:
    config = _config(tmp_path)
    research_service = ResearchRunService(config)
    persistence = build_recommendation_composition(config).persistence
    reader = RecommendationPortfolioResultReader(research_service, persistence)
    return research_service, persistence, reader


def _save_result(
    service: ResearchRunService,
    persistence: RecommendationExecutionPersistence,
    run_id: str,
    result: RecommendationPortfolioBacktestResultDTO,
    *,
    lineage: ReplayLineageSidecarV1 | None = None,
) -> ResearchRunMetadataDTO:
    if lineage is None and result.snapshots and all(
        snapshot.canonical_execution is not None for snapshot in result.snapshots
    ):
        lineage = persist_replay_lineage_children(result, persistence)
    manifest = {"synthetic_source": {"version": "stage-c-v1"}}
    if lineage is None:
        manifest["replay_lineage_status"] = {
            "schema_version": 1,
            "status": "unavailable",
            "parent_result_id": result.replay_parent_id,
            "reason": "canonical_child_unavailable",
        }
    return service.save_run(
        replace(_metadata(run_id), data_manifest=manifest),
        result.equity_curve,
        result.trades,
        portfolio_result=result,
        replay_lineage_sidecar=lineage,
    )


def test_restart_materializes_full_dto_and_maps_sorted_children_by_date(
    tmp_path: Path,
) -> None:
    service, persistence, _ = _services(tmp_path)
    expected = _portfolio_result()
    saved = _save_result(
        service,
        persistence,
        "stage-c-reversed-snapshots",
        expected,
    )

    # 使用新的 Registry reader instance 模擬程序重啟；sidecar children 依日期排序，
    # snapshots 則刻意維持相反次序，兩者必須按 ISO 日期對齊。
    restarted_service, restarted_persistence, _ = _services(tmp_path)
    restarted_reader = RecommendationPortfolioResultReader(
        restarted_service, restarted_persistence
    )
    loaded = restarted_reader.read(saved.run_id)

    assert type(loaded) is RecommendationPortfolioBacktestResultDTO
    assert loaded.summary == expected.summary
    assert loaded.equity_curve.equals(expected.equity_curve)
    assert loaded.trades.equals(expected.trades)
    assert [snapshot.as_of_date for snapshot in loaded.snapshots] == [
        "2026-09-22",
        "2026-09-15",
    ]
    assert [snapshot.recommendations for snapshot in loaded.snapshots] == [
        expected.snapshots[0].recommendations,
        expected.snapshots[1].recommendations,
    ]
    assert [snapshot.diagnostics for snapshot in loaded.snapshots] == [
        expected.snapshots[0].diagnostics,
        expected.snapshots[1].diagnostics,
    ]
    assert [snapshot.canonical_execution.result_id for snapshot in loaded.snapshots] == [
        "stage-c-child-20260922",
        "stage-c-child-20260915",
    ]
    assert [
        snapshot.canonical_execution.context.as_of_date.isoformat()
        for snapshot in loaded.snapshots
    ] == [snapshot.as_of_date for snapshot in loaded.snapshots]
    assert all(
        snapshot.canonical_execution.related_references[0].reference_id == _PARENT_ID
        for snapshot in loaded.snapshots
    )
    assert loaded.period_holdings == expected.period_holdings
    assert loaded.stock_contribution == expected.stock_contribution
    assert loaded.selection_diagnostics == expected.selection_diagnostics
    assert loaded.improvement_hints == expected.improvement_hints
    assert loaded.details == expected.details


def test_markerless_legacy_registry_run_is_typed_unavailable(tmp_path: Path) -> None:
    service, persistence, reader = _services(tmp_path)
    legacy = RecommendationPortfolioBacktestResultDTO(
        summary={"legacy": True},
        equity_curve=pd.DataFrame([{"日期": "2026-09-22", "value": 100}]),
        trades=pd.DataFrame(columns=["日期", "stock_code", "side"]),
        snapshots=[],
        period_holdings=[],
        stock_contribution=[],
    )
    saved = service.save_run(_metadata("stage-c-legacy-unavailable"), legacy.equity_curve, legacy.trades)

    unavailable = reader.read(saved.run_id)

    assert type(unavailable) is PortfolioResultReadbackUnavailable
    assert unavailable.status == "unavailable"
    assert unavailable.registry_run_id == saved.run_id
    assert (
        unavailable.reason
        is PortfolioResultUnavailableReason.LEGACY_REGISTRY_RUN_WITHOUT_MARKER
    )
    assert persistence is not None


@pytest.mark.parametrize("damage", ["missing-sidecar", "tampered-sidecar", "tampered-equity"])
def test_marked_registry_artifact_or_parquet_damage_fails_closed(
    tmp_path: Path,
    damage: str,
) -> None:
    service, persistence, reader = _services(tmp_path)
    result = _portfolio_result(include_children=False)
    saved = _save_result(service, persistence, f"stage-c-damaged-{damage}", result)
    paths = service._paths_for(saved.run_id)
    target = (
        paths["equity_final"] if damage == "tampered-equity" else paths["portfolio_result_final"]
    )
    if damage == "missing-sidecar":
        target.unlink()
    else:
        target.write_bytes(target.read_bytes() + b"tamper")

    with pytest.raises(RecommendationPortfolioResultReadbackError):
        reader.read(saved.run_id)


def test_lineage_date_set_must_exactly_match_snapshots_before_child_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, persistence, reader = _services(tmp_path)
    result = _portfolio_result()
    first_execution = _execution(_FIRST_DATE)
    persistence.save(first_execution)
    only_first_child = ReplayLineageSidecarV1(
        parent_result_id=_PARENT_ID,
        children=(
            ReplayLineageChildV1.from_execution(
                first_execution, snapshot_date=_FIRST_DATE
            ),
        ),
    )
    saved = _save_result(
        service,
        persistence,
        "stage-c-date-set-mismatch",
        result,
        lineage=only_first_child,
    )

    def unexpected_child_read(*_args: object, **_kwargs: object) -> object:
        pytest.fail("日期集合不符時不得開始 child 讀回")

    monkeypatch.setattr(
        "app_module.recommendation.portfolio_result_reader.verify_replay_lineage_children",
        unexpected_child_read,
    )
    with pytest.raises(RecommendationPortfolioResultReadbackError, match="日期集合"):
        reader.read(saved.run_id)


def test_corrupt_child_fails_before_any_snapshot_is_attached(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, persistence, reader = _services(tmp_path)
    result = _portfolio_result()
    saved = _save_result(
        service,
        persistence,
        "stage-c-corrupt-child-batch",
        result,
    )
    second_id = "stage-c-child-20260922"
    child_path = (
        persistence._store.artifact_root
        / persistence._store.artifact_name_for(second_id)
    )
    child_path.write_bytes(child_path.read_bytes() + b"tamper")

    attached: list[str] = []
    original_attach = RecommendationSnapshotDTO.attach_canonical_execution

    def track_attach(
        snapshot: RecommendationSnapshotDTO,
        execution: RecommendationExecution,
    ) -> None:
        attached.append(snapshot.as_of_date)
        original_attach(snapshot, execution)

    monkeypatch.setattr(RecommendationSnapshotDTO, "attach_canonical_execution", track_attach)
    with pytest.raises(RecommendationPortfolioResultReadbackError):
        reader.read(saved.run_id)
    assert attached == []


def test_cancel_between_child_reads_stops_second_child_without_partial_dto_or_attach(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, persistence, reader = _services(tmp_path)
    result = _portfolio_result()
    saved = _save_result(
        service,
        persistence,
        "stage-c-cancel-between-children",
        result,
    )
    cancelled = False
    child_reads: list[str] = []
    attached: list[str] = []
    original_read_verified_envelope = persistence.read_verified_envelope
    original_attach = RecommendationSnapshotDTO.attach_canonical_execution

    def read_first_then_cancel(result_id: str) -> Any:
        nonlocal cancelled
        envelope = original_read_verified_envelope(result_id)
        child_reads.append(result_id)
        if len(child_reads) == 1:
            cancelled = True
        return envelope

    def track_attach(
        snapshot: RecommendationSnapshotDTO,
        execution: RecommendationExecution,
    ) -> None:
        attached.append(snapshot.as_of_date)
        original_attach(snapshot, execution)

    monkeypatch.setattr(persistence, "read_verified_envelope", read_first_then_cancel)
    monkeypatch.setattr(RecommendationSnapshotDTO, "attach_canonical_execution", track_attach)

    with pytest.raises(RecommendationPortfolioResultReadCancelledError) as exc_info:
        reader.read(saved.run_id, check_cancel=lambda: cancelled)

    assert type(exc_info.value) is RecommendationPortfolioResultReadCancelledError
    assert child_reads == ["stage-c-child-20260915"]
    assert attached == []


def test_lineage_unavailable_preserves_v1_rows_without_canonical_execution(
    tmp_path: Path,
) -> None:
    service, persistence, reader = _services(tmp_path)
    result = _portfolio_result(include_children=False)
    saved = _save_result(
        service,
        persistence,
        "stage-c-lineage-unavailable",
        result,
    )

    loaded = reader.read(saved.run_id)

    assert type(loaded) is RecommendationPortfolioBacktestResultDTO
    assert [snapshot.recommendations for snapshot in loaded.snapshots] == [
        snapshot.recommendations for snapshot in result.snapshots
    ]
    assert all(snapshot.canonical_execution is None for snapshot in loaded.snapshots)


@pytest.mark.parametrize(
    "malformation",
    ["missing-status", "wrong-status-type", "wrong-parent"],
)
def test_marked_result_without_lineage_requires_matching_unavailable_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    malformation: str,
) -> None:
    service, persistence, reader = _services(tmp_path)
    result = _portfolio_result(include_children=False)
    saved = _save_result(
        service,
        persistence,
        f"stage-c-lineage-status-{malformation}",
        result,
    )
    loaded = service.load_run_data(saved.run_id)
    malformed_manifest = dict(loaded.metadata.data_manifest)
    if malformation == "missing-status":
        malformed_manifest.pop("replay_lineage_status", None)
    elif malformation == "wrong-status-type":
        malformed_manifest["replay_lineage_status"] = "unavailable"
    else:
        status = dict(malformed_manifest["replay_lineage_status"])
        status["parent_result_id"] = "different-parent"
        malformed_manifest["replay_lineage_status"] = status
    malformed_loaded = replace(
        loaded,
        metadata=replace(loaded.metadata, data_manifest=malformed_manifest),
    )
    monkeypatch.setattr(
        service,
        "load_run_data",
        lambda _run_id: malformed_loaded,
    )

    with pytest.raises(
        RecommendationPortfolioResultReadbackError,
        match="replay_lineage_status",
    ):
        reader.read(saved.run_id)


def test_marked_empty_portfolio_restarts_with_explicit_unavailable_lineage(
    tmp_path: Path,
) -> None:
    service, persistence, _ = _services(tmp_path)
    expected = RecommendationPortfolioBacktestResultDTO(
        summary={
            "status": "completed",
            "snapshot_count": 0,
            "cash_cents": 1_000_000,
        },
        equity_curve=pd.DataFrame(columns=["日期", "portfolio_value"]),
        trades=pd.DataFrame(columns=["日期", "stock_code", "side", "shares"]),
        snapshots=[],
        period_holdings=[],
        stock_contribution=[],
        selection_diagnostics=["empty synthetic run"],
        improvement_hints=["none"],
        details={"empty": True, "data_manifest": {"source": "synthetic"}},
    )
    expected.attach_replay_parent_id(_PARENT_ID)
    saved = _save_result(
        service,
        persistence,
        "stage-c-empty-result-no-lineage",
        expected,
    )

    restarted_service, restarted_persistence, _ = _services(tmp_path)
    loaded = RecommendationPortfolioResultReader(
        restarted_service, restarted_persistence
    ).read(saved.run_id)

    assert type(loaded) is RecommendationPortfolioBacktestResultDTO
    assert loaded.summary == expected.summary
    assert loaded.details == expected.details
    assert loaded.equity_curve.equals(expected.equity_curve)
    assert loaded.trades.equals(expected.trades)
    assert loaded.snapshots == []
    assert loaded.period_holdings == []
    assert loaded.stock_contribution == []
    assert loaded.selection_diagnostics == expected.selection_diagnostics
    assert loaded.improvement_hints == expected.improvement_hints


def test_lineage_cannot_coexist_with_unavailable_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, persistence, reader = _services(tmp_path)
    result = _portfolio_result()
    unavailable_status = {
        "schema_version": 1,
        "status": "unavailable",
        "parent_result_id": _PARENT_ID,
        "reason": "canonical_child_unavailable",
    }
    saved = _save_result(
        service,
        persistence,
        "stage-c-lineage-conflicts-with-unavailable",
        result,
    )
    loaded = service.load_run_data(saved.run_id)
    manifest = dict(loaded.metadata.data_manifest)
    manifest["replay_lineage_status"] = unavailable_status
    contradictory_loaded = replace(
        loaded,
        metadata=replace(loaded.metadata, data_manifest=manifest),
    )
    monkeypatch.setattr(
        service,
        "load_run_data",
        lambda _run_id: contradictory_loaded,
    )

    with pytest.raises(
        RecommendationPortfolioResultReadbackError,
        match="不得同時宣告 unavailable",
    ):
        reader.read(saved.run_id)


def test_noncanonical_snapshot_date_fails_closed(tmp_path: Path) -> None:
    service, persistence, reader = _services(tmp_path)
    result = _portfolio_result(include_children=False)
    result.snapshots[0].as_of_date = "20260922"
    saved = _save_result(
        service,
        persistence,
        "stage-c-noncanonical-snapshot-date",
        result,
    )

    with pytest.raises(RecommendationPortfolioResultReadbackError, match="canonical"):
        reader.read(saved.run_id)
