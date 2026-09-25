"""R020 跨 store 子程序中止與重啟的合成復原契約。"""

from __future__ import annotations

import multiprocessing
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

import pandas as pd
import pytest

from app_module.recommendation.codec import encode_execution
from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.contracts import (
    Context,
    DecisionBatch,
    ExecutionStatus,
    IndexStatus,
    QualityReport,
    RecommendationExecution,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation.persistence import (
    ExecutionIdentityConflict,
    RecommendationExecutionPersistence,
)
from app_module.recommendation.replay_lineage import ReplayLineageSidecarV1
from app_module.recommendation.replay_lineage_service import (
    persist_replay_lineage_children,
)
from app_module.recommendation.portfolio_result_reader import (
    RecommendationPortfolioResultReadbackError,
    RecommendationPortfolioResultReader,
)
from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
    RecommendationSnapshotDTO,
)
from app_module.research_run_service import ResearchRunService
from app_module.research_run_dtos import ResearchRunMetadataDTO
from data_module.config import TWStockConfig
from data_module.result_artifact_store import ResultArtifactStore
from decision_module.recommendation.contracts import RecommendationItem
from ui_qt.views.backtest.research_run_metadata import (
    build_recommendation_portfolio_metadata,
)


_FIRST_DATE = date(2026, 9, 22)
_SECOND_DATE = date(2026, 9, 23)
_PROCESS_EXIT_CODES = (71, 72, 73)


def _config(root: Path) -> TWStockConfig:
    root = root.resolve()
    return TWStockConfig(
        data_root=root / "data",
        output_root=root / "output",
        profile="test",
    )


def _execution(
    parent_result_id: str,
    snapshot_date: date,
    *,
    result_id: str | None = None,
    score: Decimal = Decimal("82.5"),
) -> RecommendationExecution:
    return RecommendationExecution(
        result_id=result_id or f"r020-proc-child-{snapshot_date:%Y%m%d}",
        request=Request(as_of_date=snapshot_date),
        context=Context(as_of_date=snapshot_date),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(
            items=(
                RecommendationItem(
                    stock_code="2330",
                    stock_name="合成標的",
                    rule_score=score,
                ),
            )
        ),
        quality=QualityReport(),
        related_references=(
            VersionReference(ReferenceKind.REPLAY_PARENT, parent_result_id),
        ),
    )


def _portfolio(parent_result_id: str) -> RecommendationPortfolioBacktestResultDTO:
    snapshots: list[RecommendationSnapshotDTO] = []
    for snapshot_date, score in (
        (_FIRST_DATE, Decimal("82.5")),
        (_SECOND_DATE, Decimal("83.5")),
    ):
        execution = _execution(parent_result_id, snapshot_date, score=score)
        snapshot = RecommendationSnapshotDTO(
            as_of_date=snapshot_date.isoformat(),
            profile_id="synthetic-r020-process-crash",
            strategy_config={"strategy_id": "recommendation_replay"},
            regime="Trend",
            recommendations=[
                {
                    "stock_code": "2330",
                    "stock_name": "合成標的",
                    "total_score": float(score),
                    "selection_reason": "TEMP 合成結果",
                }
            ],
        )
        snapshot.attach_replay_parent_id(parent_result_id)
        snapshot.attach_canonical_execution(execution)
        snapshots.append(snapshot)

    result = RecommendationPortfolioBacktestResultDTO(
        summary={"status": "completed", "total_return": "0.01", "snapshot_count": 2},
        equity_curve=pd.DataFrame(
            [
                {"日期": _FIRST_DATE.isoformat(), "portfolio_value": 1_000_000},
                {"日期": _SECOND_DATE.isoformat(), "portfolio_value": 1_010_000},
            ]
        ),
        trades=pd.DataFrame(
            [
                {
                    "日期": _SECOND_DATE.isoformat(),
                    "stock_code": "2330",
                    "side": "buy",
                    "quantity": 10,
                }
            ]
        ),
        snapshots=snapshots,
        period_holdings=[],
        stock_contribution=[],
        selection_diagnostics=["synthetic process boundary"],
        improvement_hints=["none"],
        details={"data_manifest": {"synthetic_source": "TEMP-only"}},
    )
    result.attach_replay_parent_id(parent_result_id)
    return result


def _metadata(run_id: str) -> ResearchRunMetadataDTO:
    return build_recommendation_portfolio_metadata(
        run_id=run_id,
        run_name="R020 process-crash synthetic run",
        notes="TEMP only",
        config={
            "profile_id": "synthetic-r020-process-crash",
            "universe": ["2330"],
            "strategy_config": {"strategy_id": "recommendation_replay"},
        },
        run_params={
            "start_date": _FIRST_DATE.isoformat(),
            "end_date": _SECOND_DATE.isoformat(),
            "initial_capital": 1_000_000,
            "allocation_method": "equal_weight",
        },
        details={"data_manifest": {"synthetic_source": "TEMP-only"}},
        metrics={"status": "completed", "total_return": "0.01"},
        created_at="2026-09-24T10:00:00-07:00",
    )


def _persistence(root: Path) -> RecommendationExecutionPersistence:
    return build_recommendation_composition(_config(root)).persistence


def _execution_for_snapshot(snapshot: RecommendationSnapshotDTO) -> RecommendationExecution:
    execution = snapshot.canonical_execution
    assert execution is not None
    return execution


def _artifact_store(persistence: RecommendationExecutionPersistence) -> ResultArtifactStore:
    return cast(ResultArtifactStore, persistence._store)


def _save_portfolio(
    service: ResearchRunService,
    result: RecommendationPortfolioBacktestResultDTO,
    sidecar: ReplayLineageSidecarV1,
    run_id: str,
) -> None:
    service.save_run(
        _metadata(run_id),
        result.equity_curve,
        result.trades,
        replay_lineage_sidecar=sidecar,
        portfolio_result=result,
    )


def _worker_exit_after_r012_publish(
    root_text: str,
    parent_result_id: str,
    result_id: str,
    exit_code: int,
) -> None:
    """在 child bytes 與 identity claim 發布後、SQLite index 前硬退出。"""

    original_publish = ResultArtifactStore.publish_artifact

    def publish_then_exit(self, payload, metadata):
        original_publish(self, payload, metadata)
        os._exit(exit_code)

    setattr(ResultArtifactStore, "publish_artifact", publish_then_exit)
    execution = _execution(
        parent_result_id,
        _FIRST_DATE,
        result_id=result_id,
    )
    _persistence(Path(root_text)).save(execution)
    os._exit(90)


def _worker_exit_after_children_before_registry(
    root_text: str,
    parent_result_id: str,
    exit_code: int,
) -> None:
    result = _portfolio(parent_result_id)
    sidecar = persist_replay_lineage_children(result, _persistence(Path(root_text)))
    if type(sidecar) is not ReplayLineageSidecarV1:
        os._exit(91)
    # 模擬 UI 已完成 child 保存與 readback，但 Registry save 尚未開始。
    os._exit(exit_code)


def _worker_exit_after_files_ready(
    root_text: str,
    parent_result_id: str,
    run_id: str,
    exit_code: int,
) -> None:
    from app_module.research_run_repository import ResearchRunRepository

    result = _portfolio(parent_result_id)
    sidecar = persist_replay_lineage_children(result, _persistence(Path(root_text)))
    if type(sidecar) is not ReplayLineageSidecarV1:
        os._exit(92)
    original_transition = ResearchRunRepository.mark_portfolio_result_files_ready

    def transition_then_exit(self, *args, **kwargs):
        original_transition(self, *args, **kwargs)
        # CAS transaction 已結束，B2 artifacts 仍在已驗證 staging 路徑。
        os._exit(exit_code)

    setattr(
        ResearchRunRepository,
        "mark_portfolio_result_files_ready",
        transition_then_exit,
    )
    result_service = ResearchRunService(_config(Path(root_text)))
    _save_portfolio(result_service, result, sidecar, run_id)
    os._exit(93)


def _spawn_and_expect_exit(
    target,
    args: tuple[object, ...],
    expected_exit_code: int,
) -> None:
    process = multiprocessing.get_context("spawn").Process(
        target=target,
        args=(*args, expected_exit_code),
    )
    process.start()
    process.join(timeout=45)
    if process.is_alive():
        # 只回收本測試明確建立的 worker；不搜尋或終止其他程序。
        process.terminate()
        process.join(timeout=10)
        pytest.fail("synthetic crash worker 超過 45 秒")
    assert process.exitcode == expected_exit_code


def _assert_under(root: Path, path: Path) -> None:
    assert path.resolve().is_relative_to(root.resolve())


def test_r012_publish_process_exit_before_index_same_hash_retry_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "output"))
    parent_id = "parent-r020-r012-publish-crash"
    result_id = "r020-r012-publish-crash-child"
    expected_exit = _PROCESS_EXIT_CODES[0]

    _spawn_and_expect_exit(
        _worker_exit_after_r012_publish,
        (str(tmp_path), parent_id, result_id),
        expected_exit,
    )

    persistence = _persistence(tmp_path)
    execution = _execution(parent_id, _FIRST_DATE, result_id=result_id)
    store = _artifact_store(persistence)
    artifact_path = store.artifact_root / store.artifact_name_for(result_id)
    _assert_under(tmp_path, artifact_path)
    original_bytes = artifact_path.read_bytes()
    assert original_bytes == encode_execution(execution)
    assert store.get_identity_payload_hash(result_id) is not None
    assert store.get_index(result_id) is None
    with pytest.raises(KeyError):
        persistence.read_verified_envelope(result_id)

    receipt = persistence.save(execution)
    assert receipt.index_status is IndexStatus.INDEXED
    assert persistence.read_verified(result_id)[1] == execution
    assert artifact_path.read_bytes() == original_bytes

    changed = _execution(
        parent_id,
        _FIRST_DATE,
        result_id=result_id,
        score=Decimal("82.6"),
    )
    with pytest.raises(ExecutionIdentityConflict):
        persistence.save(changed)
    assert artifact_path.read_bytes() == original_bytes


def test_process_exit_after_children_before_registry_reuses_same_exact_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "output"))
    parent_id = "parent-r020-all-children-before-registry"
    run_id = "registry-r020-process-retry"
    expected_exit = _PROCESS_EXIT_CODES[1]

    _spawn_and_expect_exit(
        _worker_exit_after_children_before_registry,
        (str(tmp_path), parent_id),
        expected_exit,
    )

    result = _portfolio(parent_id)
    persistence = _persistence(tmp_path)
    child_ids = [
        _execution_for_snapshot(snapshot).result_id for snapshot in result.snapshots
    ]
    store = _artifact_store(persistence)
    before = {child_id: store.read_artifact(child_id) for child_id in child_ids}
    assert all(payload is not None for payload in before.values())
    for snapshot in result.snapshots:
        execution = _execution_for_snapshot(snapshot)
        assert persistence.read_verified(execution.result_id)[1] == execution

    service = ResearchRunService(_config(tmp_path))
    assert service.repository.get_raw_metadata_row(run_id) is None
    sidecar = persist_replay_lineage_children(result, persistence)
    assert type(sidecar) is ReplayLineageSidecarV1
    _save_portfolio(service, result, sidecar, run_id)

    assert {
        child_id: store.read_artifact(child_id) for child_id in child_ids
    } == before
    row = service.repository.get_raw_metadata_row(run_id)
    assert row is not None
    assert (row["storage_state"], row["integrity_status"]) == ("committed", "valid")
    loaded = RecommendationPortfolioResultReader(service, persistence).read(run_id)
    assert type(loaded) is RecommendationPortfolioBacktestResultDTO
    assert [_execution_for_snapshot(snapshot).result_id for snapshot in loaded.snapshots] == (
        child_ids
    )


def test_files_ready_process_exit_reconciles_and_stage_c_restarts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "output"))
    parent_id = "parent-r020-files-ready-crash"
    run_id = "registry-r020-files-ready-crash"
    expected_exit = _PROCESS_EXIT_CODES[2]

    _spawn_and_expect_exit(
        _worker_exit_after_files_ready,
        (str(tmp_path), parent_id, run_id),
        expected_exit,
    )

    service = ResearchRunService(_config(tmp_path))
    persistence = _persistence(tmp_path)
    row = service.repository.get_raw_metadata_row(run_id)
    assert row is not None
    assert (row["storage_state"], row["integrity_status"]) == ("files_ready", "pending")
    paths = service._paths_for(run_id)
    for path_key in (
        "equity_temp",
        "trades_temp",
        "portfolio_result_temp",
        "replay_lineage_temp",
    ):
        _assert_under(tmp_path, paths[path_key])
        assert paths[path_key].is_file()

    child_ids = [
        _execution_for_snapshot(snapshot).result_id
        for snapshot in _portfolio(parent_id).snapshots
    ]
    store = _artifact_store(persistence)
    child_bytes = {child_id: store.read_artifact(child_id) for child_id in child_ids}
    assert all(payload is not None for payload in child_bytes.values())

    # Worker 已退出，沒有並行 writer；新 service 才負責 reconciliation。
    ResearchRunService(_config(tmp_path)).reconcile_incomplete_saves()
    restarted_service = ResearchRunService(_config(tmp_path))
    committed = restarted_service.repository.get_raw_metadata_row(run_id)
    assert committed is not None
    assert (committed["storage_state"], committed["integrity_status"]) == (
        "committed",
        "valid",
    )
    assert {
        child_id: store.read_artifact(child_id) for child_id in child_ids
    } == child_bytes

    loaded = RecommendationPortfolioResultReader(
        restarted_service, persistence
    ).read(run_id)
    assert type(loaded) is RecommendationPortfolioBacktestResultDTO
    assert [_execution_for_snapshot(snapshot).result_id for snapshot in loaded.snapshots] == (
        child_ids
    )


def test_missing_committed_child_fails_reader_before_any_snapshot_attachment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_id = "parent-r020-committed-missing-child"
    run_id = "registry-r020-committed-missing-child"
    result = _portfolio(parent_id)
    persistence = _persistence(tmp_path)
    sidecar = persist_replay_lineage_children(result, persistence)
    assert type(sidecar) is ReplayLineageSidecarV1
    service = ResearchRunService(_config(tmp_path))
    _save_portfolio(service, result, sidecar, run_id)
    child_id = sidecar.children[-1].result_id
    store = _artifact_store(persistence)
    child_path = store.artifact_root / store.artifact_name_for(child_id)
    _assert_under(tmp_path, child_path)
    before_child_bytes = child_path.read_bytes()
    before_sidecar_bytes = service._paths_for(run_id)["replay_lineage_final"].read_bytes()
    child_path.unlink()

    restarted_service = ResearchRunService(_config(tmp_path))
    restarted_persistence = _persistence(tmp_path)
    attached_dates: list[str] = []
    original_attach = RecommendationSnapshotDTO.attach_canonical_execution

    def track_attach(
        snapshot: RecommendationSnapshotDTO,
        execution: RecommendationExecution,
    ) -> None:
        attached_dates.append(snapshot.as_of_date)
        original_attach(snapshot, execution)

    monkeypatch.setattr(RecommendationSnapshotDTO, "attach_canonical_execution", track_attach)
    with pytest.raises(RecommendationPortfolioResultReadbackError):
        RecommendationPortfolioResultReader(
            restarted_service, restarted_persistence
        ).read(run_id)

    assert attached_dates == []
    row = restarted_service.repository.get_raw_metadata_row(run_id)
    assert row is not None
    assert (row["storage_state"], row["integrity_status"]) == ("committed", "valid")
    assert restarted_service._paths_for(run_id)["replay_lineage_final"].read_bytes() == (
        before_sidecar_bytes
    )
    assert child_path.exists() is False
    assert _artifact_store(restarted_persistence).get_index(child_id) is not None
    assert before_child_bytes == encode_execution(
        _execution_for_snapshot(result.snapshots[-1])
    )


def test_missing_committed_child_needs_explicit_same_hash_execution_republish(
    tmp_path: Path,
) -> None:
    parent_id = "parent-r020-explicit-child-repair"
    run_id = "registry-r020-explicit-child-repair"
    result = _portfolio(parent_id)
    persistence = _persistence(tmp_path)
    sidecar = persist_replay_lineage_children(result, persistence)
    assert type(sidecar) is ReplayLineageSidecarV1
    service = ResearchRunService(_config(tmp_path))
    _save_portfolio(service, result, sidecar, run_id)

    missing_snapshot = result.snapshots[-1]
    execution = _execution_for_snapshot(missing_snapshot)
    child_id = execution.result_id
    store = _artifact_store(persistence)
    child_path = store.artifact_root / store.artifact_name_for(child_id)
    _assert_under(tmp_path, child_path)
    original_bytes = child_path.read_bytes()
    child_path.unlink()

    restarted_service = ResearchRunService(_config(tmp_path))
    with pytest.raises(RecommendationPortfolioResultReadbackError):
        RecommendationPortfolioResultReader(
            restarted_service, _persistence(tmp_path)
        ).read(run_id)

    receipt = persistence.save(execution)
    assert receipt.index_status is IndexStatus.INDEXED
    assert child_path.read_bytes() == original_bytes == encode_execution(execution)
    loaded = RecommendationPortfolioResultReader(
        ResearchRunService(_config(tmp_path)), _persistence(tmp_path)
    ).read(run_id)
    assert type(loaded) is RecommendationPortfolioBacktestResultDTO
    assert loaded.snapshots[-1].canonical_execution == execution
