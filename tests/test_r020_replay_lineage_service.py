"""R020 lineage coordinator 的 tmp_path artifact 保存與讀回測試。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    RecommendationExecution,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation.persistence import (
    ExecutionArtifactIntegrityError,
    ExecutionIdentityConflict,
    RecommendationExecutionPersistence,
)
from app_module.recommendation.replay_lineage import (
    ReplayLineageSidecarV1,
    decode_replay_lineage_envelope,
    encode_replay_lineage,
)
from app_module.recommendation.replay_lineage_service import (
    persist_replay_lineage_children,
    verify_replay_lineage_children,
)
from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
    RecommendationSnapshotDTO,
)
from data_module.result_artifact_store import ResultArtifactStore
from decision_module.recommendation.contracts import DecisionBatch, RecommendationItem


def _execution(
    result_id: str,
    parent_result_id: str,
    as_of_date: date,
    score: Decimal,
) -> RecommendationExecution:
    return RecommendationExecution(
        result_id=result_id,
        request=Request(as_of_date=as_of_date),
        context=Context(as_of_date=as_of_date),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(
            items=(
                RecommendationItem(
                    stock_code=f"S{as_of_date.day:02d}",
                    stock_name="合成標的",
                    rule_score=score,
                ),
            )
        ),
        related_references=(
            VersionReference(ReferenceKind.REPLAY_PARENT, parent_result_id),
        ),
    )


def _snapshot(
    execution: RecommendationExecution | None,
    *,
    parent_result_id: str,
    as_of_date: date,
) -> RecommendationSnapshotDTO:
    snapshot = RecommendationSnapshotDTO(
        as_of_date=as_of_date.isoformat(),
        profile_id="profile-r020-lineage-test",
        strategy_config={},
        regime="Trend",
        recommendations=[],
    )
    snapshot.attach_replay_parent_id(parent_result_id)
    if execution is not None:
        snapshot.attach_canonical_execution(execution)
    return snapshot


def _portfolio_result(
    parent_result_id: str,
    snapshots: list[RecommendationSnapshotDTO],
) -> RecommendationPortfolioBacktestResultDTO:
    result = RecommendationPortfolioBacktestResultDTO(
        summary={},
        equity_curve=pd.DataFrame(),
        trades=pd.DataFrame(),
        snapshots=snapshots,
        period_holdings=[],
        stock_contribution=[],
    )
    result.attach_replay_parent_id(parent_result_id)
    return result


def _persistence(tmp_path: Path) -> tuple[ResultArtifactStore, RecommendationExecutionPersistence]:
    runs_dir = tmp_path / "output" / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    return store, RecommendationExecutionPersistence(store)


def _children(
    parent_result_id: str,
) -> tuple[RecommendationExecution, RecommendationExecution]:
    return (
        _execution(
            "child-r020-20260915",
            parent_result_id,
            date(2026, 9, 15),
            Decimal("81.25"),
        ),
        _execution(
            "child-r020-20260922",
            parent_result_id,
            date(2026, 9, 22),
            Decimal("92.50"),
        ),
    )


def test_coordinator_saves_children_and_verifies_actual_artifact_bytes(
    tmp_path: Path,
) -> None:
    parent_result_id = "portfolio-parent-r020-service-success"
    executions = _children(parent_result_id)
    result = _portfolio_result(
        parent_result_id,
        [
            _snapshot(
                execution,
                parent_result_id=parent_result_id,
                as_of_date=execution.context.as_of_date,
            )
            for execution in executions
        ],
    )
    store, persistence = _persistence(tmp_path)

    sidecar = persist_replay_lineage_children(result, persistence)

    assert type(sidecar) is ReplayLineageSidecarV1
    assert sidecar.parent_result_id == parent_result_id
    assert [child.result_id for child in sidecar.children] == [
        execution.result_id for execution in executions
    ]
    for child, execution in zip(sidecar.children, executions):
        record, loaded = persistence.read_verified(child.result_id)
        assert loaded == execution
        assert record.metadata.payload_hash == child.canonical_payload_sha256
        assert child.replay_parent_ref.reference_id == parent_result_id

    envelope = decode_replay_lineage_envelope(encode_replay_lineage(sidecar))
    verified = verify_replay_lineage_children(envelope, persistence)
    assert verified == executions
    assert len(tuple(store.iter_artifacts())) == 2


def test_empty_parent_produces_empty_sidecar_without_child_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_result_id = "portfolio-parent-r020-empty"
    result = _portfolio_result(parent_result_id, [])
    store, persistence = _persistence(tmp_path)

    def unexpected_save(*_args: object, **_kwargs: object) -> None:
        pytest.fail("empty parent 不得呼叫 child writer")

    monkeypatch.setattr(persistence, "save", unexpected_save)
    sidecar = persist_replay_lineage_children(result, persistence)

    assert sidecar == ReplayLineageSidecarV1(parent_result_id=parent_result_id)
    assert tuple(store.iter_artifacts()) == ()


def test_missing_child_is_prevalidated_before_any_child_writer_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_result_id = "portfolio-parent-r020-missing-child"
    valid, _ = _children(parent_result_id)
    result = _portfolio_result(
        parent_result_id,
        [
            _snapshot(
                valid,
                parent_result_id=parent_result_id,
                as_of_date=valid.context.as_of_date,
            ),
            _snapshot(
                None,
                parent_result_id=parent_result_id,
                as_of_date=date(2026, 9, 22),
            ),
        ],
    )
    store, persistence = _persistence(tmp_path)

    def unexpected_save(*_args: object, **_kwargs: object) -> None:
        pytest.fail("所有 child 必須預驗證後才可開始保存")

    monkeypatch.setattr(persistence, "save", unexpected_save)
    sidecar = persist_replay_lineage_children(result, persistence)

    assert sidecar is None
    assert tuple(store.iter_artifacts()) == ()


def test_tampered_child_artifact_fails_lineage_readback(
    tmp_path: Path,
) -> None:
    parent_result_id = "portfolio-parent-r020-tamper"
    execution, _ = _children(parent_result_id)
    result = _portfolio_result(
        parent_result_id,
        [
            _snapshot(
                execution,
                parent_result_id=parent_result_id,
                as_of_date=execution.context.as_of_date,
            )
        ],
    )
    store, persistence = _persistence(tmp_path)
    sidecar = persist_replay_lineage_children(result, persistence)
    assert sidecar is not None
    envelope = decode_replay_lineage_envelope(encode_replay_lineage(sidecar))

    artifact_path = store.artifact_root / store.artifact_name_for(execution.result_id)
    before = artifact_path.read_bytes()
    artifact_path.write_bytes(before + b" ")

    with pytest.raises(ExecutionArtifactIntegrityError):
        verify_replay_lineage_children(envelope, persistence)


def test_coordinator_rejects_corruption_between_save_and_verified_readback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_result_id = "portfolio-parent-r020-readback-corrupt"
    execution, _ = _children(parent_result_id)
    result = _portfolio_result(
        parent_result_id,
        [
            _snapshot(
                execution,
                parent_result_id=parent_result_id,
                as_of_date=execution.context.as_of_date,
            )
        ],
    )
    store, persistence = _persistence(tmp_path)
    original_save = persistence.save

    def save_then_corrupt(
        value: RecommendationExecution,
        **kwargs: Any,
    ):
        receipt = original_save(value, **kwargs)
        artifact_path = store.artifact_root / store.artifact_name_for(value.result_id)
        artifact_path.write_bytes(artifact_path.read_bytes() + b" ")
        return receipt

    monkeypatch.setattr(persistence, "save", save_then_corrupt)

    with pytest.raises(ExecutionArtifactIntegrityError):
        persist_replay_lineage_children(result, persistence)


def test_same_id_same_hash_retry_is_idempotent_and_hash_conflict_preserves_first(
    tmp_path: Path,
) -> None:
    parent_result_id = "portfolio-parent-r020-retry"
    first_execution, _ = _children(parent_result_id)
    first_result = _portfolio_result(
        parent_result_id,
        [
            _snapshot(
                first_execution,
                parent_result_id=parent_result_id,
                as_of_date=first_execution.context.as_of_date,
            )
        ],
    )
    store, persistence = _persistence(tmp_path)

    first_sidecar = persist_replay_lineage_children(first_result, persistence)
    raw_before = store.read_artifact(first_execution.result_id)
    second_sidecar = persist_replay_lineage_children(first_result, persistence)

    assert first_sidecar == second_sidecar
    assert raw_before is not None
    assert store.read_artifact(first_execution.result_id) == raw_before
    assert len(tuple(store.iter_artifacts())) == 1

    changed_execution = _execution(
        first_execution.result_id,
        parent_result_id,
        first_execution.context.as_of_date,
        Decimal("81.26"),
    )
    changed_result = _portfolio_result(
        parent_result_id,
        [
            _snapshot(
                changed_execution,
                parent_result_id=parent_result_id,
                as_of_date=changed_execution.context.as_of_date,
            )
        ],
    )

    with pytest.raises(ExecutionIdentityConflict):
        persist_replay_lineage_children(changed_result, persistence)
    assert store.read_artifact(first_execution.result_id) == raw_before
    _, persisted_execution = persistence.read_verified(first_execution.result_id)
    assert persisted_execution == first_execution


def test_parent_mismatch_is_rejected_before_any_artifact_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio_parent = "portfolio-parent-r020-parent-mismatch"
    other_parent = "portfolio-parent-r020-other"
    execution = _execution(
        "child-r020-wrong-parent",
        other_parent,
        date(2026, 9, 15),
        Decimal("80"),
    )
    result = _portfolio_result(
        portfolio_parent,
        [
            _snapshot(
                execution,
                parent_result_id=portfolio_parent,
                as_of_date=execution.context.as_of_date,
            )
        ],
    )
    store, persistence = _persistence(tmp_path)

    def unexpected_save(*_args: object, **_kwargs: object) -> None:
        pytest.fail("parent identity 不符時不得呼叫 writer")

    monkeypatch.setattr(persistence, "save", unexpected_save)
    with pytest.raises(ValueError, match="REPLAY_PARENT"):
        persist_replay_lineage_children(result, persistence)
    assert tuple(store.iter_artifacts()) == ()
