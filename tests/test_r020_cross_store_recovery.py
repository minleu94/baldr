"""R020 R012 child 與 Research Run Registry 間的 TEMP 復原契約。"""

from __future__ import annotations

import hashlib
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from app_module.recommendation.contracts import (
    Context,
    DecisionBatch,
    ExecutionStatus,
    QualityReport,
    RecommendationExecution,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation.persistence import (
    ExecutionArtifactIntegrityError,
    ExecutionArtifactWriteError,
    ExecutionIdentityConflict,
    RecommendationExecutionPersistence,
)
from app_module.recommendation.replay_lineage import ReplayLineageSidecarV1
from app_module.recommendation.replay_lineage_service import (
    persist_replay_lineage_children,
    verify_replay_lineage_children,
)
from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
    RecommendationSnapshotDTO,
)
from app_module.research_run_service import (
    InjectedResearchRunFailure,
    ResearchRunIntegrityError,
    ResearchRunService,
)
from data_module.config import TWStockConfig
from decision_module.recommendation.contracts import RecommendationItem
from ui_qt.views.backtest.research_run_metadata import (
    build_recommendation_portfolio_metadata,
)
from ui_qt.views.backtest_view import BacktestView


def _config(tmp_path: Path) -> TWStockConfig:
    return TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="test",
    )


def _child(
    parent_result_id: str,
    snapshot_date: date,
    *,
    score: Decimal = Decimal("82.5"),
) -> RecommendationExecution:
    return RecommendationExecution(
        result_id=f"child-r020-cross-{snapshot_date:%Y%m%d}",
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


def _portfolio(
    parent_result_id: str,
    *,
    first_score: Decimal = Decimal("82.5"),
) -> RecommendationPortfolioBacktestResultDTO:
    snapshots: list[RecommendationSnapshotDTO] = []
    for index, snapshot_date in enumerate(
        (date(2026, 9, 22), date(2026, 9, 23))
    ):
        execution = _child(
            parent_result_id,
            snapshot_date,
            score=first_score if index == 0 else Decimal("83.5"),
        )
        snapshot = RecommendationSnapshotDTO(
            as_of_date=snapshot_date.isoformat(),
            profile_id="synthetic-r020-cross-store",
            strategy_config={"strategy_id": "recommendation_replay"},
            regime="Trend",
            recommendations=[
                {
                    "stock_code": "2330",
                    "stock_name": "合成標的",
                    "total_score": float(execution.decision.items[0].rule_score),
                    "selection_reason": "TEMP 合成資料",
                }
            ],
        )
        snapshot.attach_replay_parent_id(parent_result_id)
        snapshot.attach_canonical_execution(execution)
        snapshots.append(snapshot)

    result = RecommendationPortfolioBacktestResultDTO(
        summary={"status": "completed", "total_return": "0.01"},
        equity_curve=pd.DataFrame(
            [
                {"日期": "2026-09-22", "portfolio_value": 1_000_000},
                {"日期": "2026-09-23", "portfolio_value": 1_010_000},
            ]
        ),
        trades=pd.DataFrame(
            [
                {
                    "日期": "2026-09-23",
                    "stock_code": "2330",
                    "side": "buy",
                    "quantity": 10,
                }
            ]
        ),
        snapshots=snapshots,
        period_holdings=[],
        stock_contribution=[],
        details={"data_manifest": {"synthetic_source": "TEMP-only"}},
    )
    result.attach_replay_parent_id(parent_result_id)
    return result


def _persistence(tmp_path: Path) -> RecommendationExecutionPersistence:
    return build_recommendation_composition(_config(tmp_path)).persistence


def _metadata(run_id: str):
    return build_recommendation_portfolio_metadata(
        run_id=run_id,
        run_name="R020 cross-store synthetic run",
        notes="TEMP only",
        config={
            "profile_id": "synthetic-r020-cross-store",
            "universe": ["2330"],
            "strategy_config": {"strategy_id": "recommendation_replay"},
        },
        run_params={
            "start_date": "2026-09-22",
            "end_date": "2026-09-23",
            "initial_capital": 1_000_000,
            "allocation_method": "equal_weight",
        },
        details={"data_manifest": {"synthetic_source": "TEMP-only"}},
        metrics={"status": "completed", "total_return": "0.01"},
        created_at="2026-09-24T10:00:00-07:00",
    )


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        pd.DataFrame(
            [
                {"日期": "2026-09-22", "portfolio_value": 1_000_000},
                {"日期": "2026-09-23", "portfolio_value": 1_010_000},
            ]
        ),
        pd.DataFrame(
            [
                {
                    "日期": "2026-09-23",
                    "stock_code": "2330",
                    "side": "buy",
                    "quantity": 10,
                }
            ]
        ),
    )


@pytest.fixture
def qt_app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _view(
    config: TWStockConfig,
    registry: ResearchRunService,
    result: RecommendationPortfolioBacktestResultDTO,
) -> BacktestView:
    view = BacktestView(backtest_service=MagicMock(), config=config)
    view.research_run_service = registry
    view.current_recommendation_portfolio_result = result
    view.current_recommendation_portfolio_config = {
        "profile_id": "synthetic-r020-cross-store",
        "strategy_config": {"strategy_id": "recommendation_replay"},
    }
    view.current_recommendation_portfolio_run_params = {
        "start_date": "2026-09-22",
        "end_date": "2026-09-23",
        "initial_capital": 1_000_000,
        "top_n": 5,
        "allocation_method": "equal_weight",
    }
    view._execution_generation = 1
    view._recommendation_portfolio_result_generation = 1
    view._recommendation_portfolio_result_source = "execution"
    return view


def test_child_two_writer_failure_keeps_first_bytes_and_same_hash_retry_commits(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    registry = ResearchRunService(config)
    parent_id = "parent-cross-store-writer-retry"
    run_id = "registry-cross-store-writer-retry"
    result = _portfolio(parent_id)
    view = _view(config, registry, result)
    view._next_research_run_id = lambda _prefix: run_id

    composition = _persistence(tmp_path)
    original_save = RecommendationExecutionPersistence.save
    child_ids = [snapshot.canonical_execution.result_id for snapshot in result.snapshots]
    calls = 0

    def fail_second_writer_once(
        self: RecommendationExecutionPersistence,
        execution: RecommendationExecution,
        **kwargs: object,
    ):
        nonlocal calls
        calls += 1
        if execution.result_id == child_ids[1]:
            raise ExecutionArtifactWriteError("synthetic child 2 writer failure")
        return original_save(self, execution, **kwargs)

    monkeypatch.setattr(
        RecommendationExecutionPersistence, "save", fail_second_writer_once
    )
    with pytest.raises(ExecutionArtifactWriteError):
        view._save_recommendation_portfolio_to_research_registry(
            "TEMP writer failure", "child 2 must fail before Registry save"
        )

    assert calls == 2
    first_bytes = composition._store.read_artifact(child_ids[0])
    assert first_bytes is not None
    assert composition.read_verified(child_ids[0])[1] == result.snapshots[
        0
    ].canonical_execution
    assert composition._store.read_artifact(child_ids[1]) is None
    assert registry.repository.get_raw_metadata_row(run_id) is None
    assert not registry._paths_for(run_id)["replay_lineage_final"].exists()

    # 同 ID 的異 hash child 必須衝突，且不得覆寫已保存的第一個 child。
    changed = _portfolio(parent_id, first_score=Decimal("82.6"))
    with pytest.raises(ExecutionIdentityConflict):
        persist_replay_lineage_children(changed, composition)
    assert composition._store.read_artifact(child_ids[0]) == first_bytes
    assert registry.repository.get_raw_metadata_row(run_id) is None

    # 原始同 ID／同 hash child 可重用；UI 路徑接著保存 sidecar 與 Registry run。
    monkeypatch.setattr(RecommendationExecutionPersistence, "save", original_save)
    saved_run_id = view._save_recommendation_portfolio_to_research_registry(
        "TEMP same-hash retry", "child 1 reused, child 2 saved"
    )
    assert saved_run_id == run_id
    loaded = registry.load_run_data(run_id)
    assert loaded.replay_lineage is not None
    verified = verify_replay_lineage_children(
        loaded.replay_lineage, composition
    )
    assert [execution.result_id for execution in verified] == child_ids
    assert composition._store.read_artifact(child_ids[0]) == first_bytes


def test_ui_registry_preinsert_failure_retries_same_run_id_without_rewriting_children(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    registry = ResearchRunService(config)
    parent_id = "parent-cross-store-ui-registry-retry"
    run_id = "registry-cross-store-ui-retry"
    result = _portfolio(parent_id)
    view = _view(config, registry, result)
    view._next_research_run_id = lambda _prefix: run_id
    persistence = _persistence(tmp_path)
    child_ids = [
        snapshot.canonical_execution.result_id for snapshot in result.snapshots
    ]
    original_child_bytes = {
        child_id: persistence._store.read_artifact(child_id)
        for child_id in child_ids
    }
    assert all(payload is None for payload in original_child_bytes.values())

    original_save = registry.save_run
    attempted_metadata = []
    attempts = 0

    def fail_before_registry_insert_once(metadata, equity, trades, **kwargs):
        nonlocal attempts
        attempts += 1
        attempted_metadata.append(metadata)
        if attempts == 1:
            return original_save(
                metadata,
                equity,
                trades,
                **kwargs,
                fail_at="before_temp_write",
            )
        return original_save(metadata, equity, trades, **kwargs)

    monkeypatch.setattr(registry, "save_run", fail_before_registry_insert_once)
    with pytest.raises(InjectedResearchRunFailure, match="before_temp_write"):
        view._save_recommendation_portfolio_to_research_registry(
            "TEMP registry pre-insert failure", "retry the same generated run_id"
        )

    assert attempts == 1
    assert attempted_metadata[0].run_id == run_id
    assert view.__dict__.get("current_recommendation_registry_run_id") is None
    # Registry 保存尚未插入 row 或發佈 sidecar；已完成的 R012 child bytes 保留。
    assert registry.repository.get_raw_metadata_row(run_id) is None
    paths = registry._paths_for(run_id)
    assert not paths["replay_lineage_temp"].exists()
    assert not paths["replay_lineage_final"].exists()
    child_bytes_after_failure = {
        child_id: persistence._store.read_artifact(child_id)
        for child_id in child_ids
    }
    assert all(payload is not None for payload in child_bytes_after_failure.values())
    assert child_bytes_after_failure != original_child_bytes

    retried_run_id = view._save_recommendation_portfolio_to_research_registry(
        "TEMP same-run-id retry", "Registry insert 前失敗後重試"
    )

    assert attempts == 2
    assert retried_run_id == run_id
    assert [metadata.run_id for metadata in attempted_metadata] == [run_id, run_id]
    assert view.__dict__.get("current_recommendation_registry_run_id") == run_id
    raw_row = registry.repository.get_raw_metadata_row(run_id)
    assert raw_row is not None
    assert raw_row["storage_state"] == "committed"
    assert raw_row["integrity_status"] == "valid"
    stored_metadata = registry.repository.get_metadata(run_id)
    assert stored_metadata is not None
    assert raw_row["payload_hash"] == stored_metadata.payload_hash
    descriptor = stored_metadata.data_manifest[
        registry.REPLAY_LINEAGE_MANIFEST_KEY
    ]
    assert descriptor["parent_result_id"] == parent_id
    sidecar_bytes = paths["replay_lineage_final"].read_bytes()
    assert paths["replay_lineage_temp"].exists() is False
    assert descriptor["raw_payload_sha256"] == (
        "sha256:" + hashlib.sha256(sidecar_bytes).hexdigest()
    )
    assert (
        persistence._store.read_artifact(child_ids[0]),
        persistence._store.read_artifact(child_ids[1]),
    ) == tuple(child_bytes_after_failure[child_id] for child_id in child_ids)

    loaded = registry.load_run_data(run_id)
    assert loaded.replay_lineage is not None
    verified_children = verify_replay_lineage_children(
        loaded.replay_lineage, persistence
    )
    assert [execution.result_id for execution in verified_children] == child_ids
    assert loaded.replay_lineage.raw_payload == sidecar_bytes


def test_child_two_readback_failure_leaves_saved_children_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_id = "parent-cross-store-readback-retry"
    result = _portfolio(parent_id)
    persistence = _persistence(tmp_path)
    child_ids = [snapshot.canonical_execution.result_id for snapshot in result.snapshots]
    original_read = RecommendationExecutionPersistence.read_verified_envelope
    failed = False

    def fail_second_read_once(
        self: RecommendationExecutionPersistence,
        result_id: str,
    ):
        nonlocal failed
        if result_id == child_ids[1] and not failed:
            failed = True
            raise ExecutionArtifactIntegrityError("synthetic child 2 readback failure")
        return original_read(self, result_id)

    monkeypatch.setattr(
        RecommendationExecutionPersistence,
        "read_verified_envelope",
        fail_second_read_once,
    )
    with pytest.raises(ExecutionArtifactIntegrityError):
        persist_replay_lineage_children(result, persistence)

    assert failed
    raw_after_failure = {
        child_id: persistence._store.read_artifact(child_id)
        for child_id in child_ids
    }
    assert all(raw is not None for raw in raw_after_failure.values())

    sidecar = persist_replay_lineage_children(result, persistence)
    assert type(sidecar) is ReplayLineageSidecarV1
    assert [child.result_id for child in sidecar.children] == child_ids
    assert {
        child_id: persistence._store.read_artifact(child_id)
        for child_id in child_ids
    } == raw_after_failure


@pytest.mark.parametrize(
    ("fail_at", "expected_state"),
    [
        ("after_staging_row", "failed"),
        ("after_hash", "committed"),
        ("after_first_rename", "committed"),
        ("after_second_rename", "committed"),
        ("after_replay_lineage_rename", "committed"),
        ("before_final_commit", "committed"),
    ],
)
def test_registry_reconciliation_never_changes_saved_child_bytes(
    tmp_path: Path,
    fail_at: str,
    expected_state: str,
) -> None:
    config = _config(tmp_path)
    persistence = _persistence(tmp_path)
    result = _portfolio(f"parent-registry-{fail_at}")
    sidecar = persist_replay_lineage_children(result, persistence)
    assert type(sidecar) is ReplayLineageSidecarV1
    child_ids = [child.result_id for child in sidecar.children]
    original_child_bytes = {
        child_id: persistence._store.read_artifact(child_id)
        for child_id in child_ids
    }
    assert all(raw is not None for raw in original_child_bytes.values())

    service = ResearchRunService(config)
    run_id = f"registry-cross-store-{fail_at}"
    with pytest.raises(InjectedResearchRunFailure):
        service.save_run(
            _metadata(run_id),
            *_frames(),
            replay_lineage_sidecar=sidecar,
            fail_at=fail_at,
        )

    ResearchRunService(config).reconcile_incomplete_saves()
    raw_row = service.repository.get_raw_metadata_row(run_id)
    assert raw_row is not None
    assert raw_row["storage_state"] == expected_state
    expected_integrity = "failed" if expected_state == "failed" else "valid"
    assert raw_row["integrity_status"] == expected_integrity
    assert {
        child_id: persistence._store.read_artifact(child_id)
        for child_id in child_ids
    } == original_child_bytes

    if expected_state == "failed":
        with pytest.raises(ResearchRunIntegrityError):
            service.load_run_data(run_id)
        return

    loaded = ResearchRunService(config).load_run_data(run_id)
    assert loaded.replay_lineage is not None
    verified = verify_replay_lineage_children(loaded.replay_lineage, persistence)
    assert [execution.result_id for execution in verified] == child_ids


def test_committed_registry_readback_does_not_hide_corrupt_child_from_verifier(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    persistence = _persistence(tmp_path)
    result = _portfolio("parent-cross-store-post-commit-corruption")
    sidecar = persist_replay_lineage_children(result, persistence)
    assert type(sidecar) is ReplayLineageSidecarV1
    run_id = "registry-cross-store-post-commit-corruption"
    service = ResearchRunService(config)
    service.save_run(
        _metadata(run_id),
        *_frames(),
        replay_lineage_sidecar=sidecar,
    )

    damaged_child_id = sidecar.children[-1].result_id
    artifact_path = (
        persistence._store.artifact_root
        / persistence._store.artifact_name_for(damaged_child_id)
    )
    assert artifact_path.resolve().is_relative_to(tmp_path.resolve())
    original = artifact_path.read_bytes()
    assert original == persistence._store.read_artifact(damaged_child_id)
    artifact_path.write_bytes(original + b" ")
    assert artifact_path.read_bytes() != original

    # Registry 只驗自己的 Parquet 與 sidecar；child bytes 由跨 store verifier 驗。
    loaded = ResearchRunService(config).load_run_data(run_id)
    assert loaded.replay_lineage is not None
    verified = None
    with pytest.raises(ExecutionArtifactIntegrityError):
        verified = verify_replay_lineage_children(
            loaded.replay_lineage, persistence
        )
    assert verified is None
    committed = service.repository.get_raw_metadata_row(run_id)
    assert committed is not None
    assert committed["storage_state"] == "committed"
    assert committed["integrity_status"] == "valid"
