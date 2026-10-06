"""Research Run Registry replay lineage sidecar 的隔離保存測試。"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

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
from app_module.recommendation.replay_lineage import (
    ReplayLineageChildV1,
    ReplayLineageSidecarV1,
    decode_replay_lineage_envelope,
    encode_replay_lineage,
)
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_repository import (
    ResearchRunConflictError,
    ResearchRunRepository,
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
    research_payload_hash,
)


def _config(tmp_path: Path) -> TWStockConfig:
    return TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    equity = pd.DataFrame(
        {"日期": ["2026-09-22", "2026-09-23"], "portfolio_value": [1_000_000, 1_010_000]}
    )
    trades = pd.DataFrame(
        {"日期": ["2026-09-23"], "stock_code": ["2330"], "side": ["buy"], "quantity": [10]}
    )
    return equity, trades


def _metadata(run_id: str) -> ResearchRunMetadataDTO:
    return build_recommendation_portfolio_metadata(
        run_id=run_id,
        run_name="Synthetic portfolio replay",
        notes="TEMP only",
        config={
            "profile_id": "synthetic-test",
            "universe": ["2330"],
            "strategy_config": {"strategy_id": "synthetic"},
        },
        run_params={
            "start_date": "2026-09-22",
            "end_date": "2026-09-23",
            "initial_capital": 1_000_000,
            "allocation_method": "equal",
        },
        details={"data_manifest": {"synthetic_source": {"version": "fixture-v1"}}},
        metrics={"total_return": "0.01", "status": "completed"},
        created_at="2026-09-24T10:00:00-07:00",
    )


def _sidecar(parent_result_id: str, child_result_id: str = "child-2026-09-23") -> ReplayLineageSidecarV1:
    snapshot_date = date(2026, 9, 23)
    execution = RecommendationExecution(
        result_id=child_result_id,
        request=Request(as_of_date=snapshot_date),
        context=Context(as_of_date=snapshot_date),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(
            items=(RecommendationItem(stock_code="2330", rule_score=Decimal("82.5")),)
        ),
        quality=QualityReport(),
        related_references=(
            VersionReference(
                kind=ReferenceKind.REPLAY_PARENT,
                reference_id=parent_result_id,
            ),
        ),
    )
    child = ReplayLineageChildV1.from_execution(
        execution,
        snapshot_date=snapshot_date,
    )
    return ReplayLineageSidecarV1(
        parent_result_id=parent_result_id,
        children=(child,),
    )


def _expected_portfolio_hash(metadata: ResearchRunMetadataDTO) -> str:
    config = metadata.original_input["config"]
    return research_payload_hash(
        {
            "run_type": "recommendation_portfolio",
            "config": config,
            "run_params": metadata.normalized_params,
            "metrics": metadata.metrics,
            "data_manifest": metadata.data_manifest,
        }
    )


def test_sidecar_is_manifest_and_payload_hash_bound_and_reads_back(tmp_path: Path) -> None:
    service = ResearchRunService(_config(tmp_path))
    metadata = _metadata("registry-run-001")
    sidecar = _sidecar("replay-parent-001")
    equity, trades = _frames()

    saved = service.save_run(
        metadata,
        equity,
        trades,
        replay_lineage_sidecar=sidecar,
    )

    descriptor = saved.data_manifest[service.REPLAY_LINEAGE_MANIFEST_KEY]
    assert descriptor == {
        "schema_version": "recommendation-replay-lineage.v1",
        "schema_revision": 1,
        "parent_result_id": "replay-parent-001",
        "relative_path": Path(saved.equity_path).name.replace("_equity.parquet", "_replay_lineage.json"),
        "raw_payload_sha256": "sha256:" + hashlib.sha256(
            encode_replay_lineage(sidecar)
        ).hexdigest(),
        "payload_hash": decode_replay_lineage_envelope(encode_replay_lineage(sidecar)).payload_hash,
        "child_count": 1,
    }
    assert saved.payload_hash == _expected_portfolio_hash(saved)
    loaded = service.load_run_data(saved.run_id)
    assert loaded.replay_lineage is not None
    assert loaded.replay_lineage.sidecar == sidecar
    assert loaded.replay_lineage.raw_payload == encode_replay_lineage(sidecar)
    assert loaded.equity.equals(equity)
    assert loaded.trades.equals(trades)


def test_same_id_retry_is_idempotent_and_different_sidecar_cannot_replace_bytes(
    tmp_path: Path,
) -> None:
    service = ResearchRunService(_config(tmp_path))
    equity, trades = _frames()
    first = service.save_run(
        _metadata("registry-run-retry"),
        equity,
        trades,
        replay_lineage_sidecar=_sidecar("replay-parent-first"),
    )
    final_path = service.parquet_dir / first.data_manifest[service.REPLAY_LINEAGE_MANIFEST_KEY][
        "relative_path"
    ]
    original_bytes = final_path.read_bytes()

    repeated = service.save_run(
        _metadata("registry-run-retry"),
        equity,
        trades,
        replay_lineage_sidecar=_sidecar("replay-parent-first"),
    )
    assert repeated.payload_hash == first.payload_hash
    assert final_path.read_bytes() == original_bytes

    with pytest.raises(ResearchRunConflictError):
        service.save_run(
            _metadata("registry-run-retry"),
            equity,
            trades,
            replay_lineage_sidecar=_sidecar("replay-parent-different"),
        )
    assert final_path.read_bytes() == original_bytes


@pytest.mark.parametrize(
    "fail_at",
    ["after_second_rename", "after_replay_lineage_rename", "before_final_commit"],
)
def test_reconcile_recovers_sidecar_at_files_ready_failpoints(
    tmp_path: Path, fail_at: str
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    run_id = f"registry-{fail_at}"

    with pytest.raises(InjectedResearchRunFailure):
        service.save_run(
            _metadata(run_id),
            *_frames(),
            replay_lineage_sidecar=_sidecar(f"parent-{fail_at}"),
            fail_at=fail_at,
        )

    recovery = ResearchRunService(config)
    recovery.reconcile_incomplete_saves()
    raw = ResearchRunRepository(config).get_raw_metadata_row(run_id)
    assert raw is not None
    assert raw["storage_state"] == "committed"
    assert raw["integrity_status"] == "valid"
    loaded = recovery.load_run_data(run_id)
    assert loaded.replay_lineage is not None
    assert loaded.replay_lineage.sidecar.parent_result_id == f"parent-{fail_at}"


def test_reconcile_marks_tampered_staging_sidecar_failed_without_publishing_it(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    run_id = "registry-tampered-temp"

    with pytest.raises(InjectedResearchRunFailure):
        service.save_run(
            _metadata(run_id),
            *_frames(),
            replay_lineage_sidecar=_sidecar("parent-tampered-temp"),
            fail_at="after_second_rename",
        )
    paths = service._paths_for(run_id)
    paths["replay_lineage_temp"].write_bytes(b"different bytes")

    service.reconcile_incomplete_saves()
    raw = ResearchRunRepository(config).get_raw_metadata_row(run_id)
    assert raw is not None
    assert raw["storage_state"] == "failed"
    assert not paths["replay_lineage_final"].exists()
    with pytest.raises(ResearchRunIntegrityError):
        service.load_run_data(run_id)


def test_atomic_link_failure_leaves_no_partial_final_and_reconcile_can_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app_module.research_run_service as research_run_service_module

    config = _config(tmp_path)
    service = ResearchRunService(config)
    run_id = "registry-link-unavailable"
    original_link = research_run_service_module.os.link

    def fail_link(_source: object, _target: object) -> None:
        raise OSError("synthetic hard-link publication failure")

    monkeypatch.setattr(research_run_service_module.os, "link", fail_link)
    with pytest.raises(OSError, match="synthetic hard-link"):
        service.save_run(
            _metadata(run_id),
            *_frames(),
            replay_lineage_sidecar=_sidecar("parent-link-unavailable"),
        )

    paths = service._paths_for(run_id)
    raw = ResearchRunRepository(config).get_raw_metadata_row(run_id)
    assert raw is not None
    assert raw["storage_state"] == "files_ready"
    assert paths["replay_lineage_temp"].exists()
    assert not paths["replay_lineage_final"].exists()

    monkeypatch.setattr(research_run_service_module.os, "link", original_link)
    service.reconcile_incomplete_saves()
    assert ResearchRunRepository(config).get_raw_metadata_row(run_id)["storage_state"] == "committed"
    loaded = service.load_run_data(run_id)
    assert loaded.replay_lineage is not None
    assert loaded.replay_lineage.sidecar.parent_result_id == "parent-link-unavailable"


@pytest.mark.parametrize(
    "replacement_sidecar",
    [
        _sidecar("parent-replaced"),
        ReplayLineageSidecarV1(parent_result_id="parent-original", children=()),
    ],
    ids=("wrong-parent", "wrong-child-count"),
)
def test_load_rejects_valid_but_mismatched_sidecar_and_legacy_run_has_none(
    tmp_path: Path,
    replacement_sidecar: ReplayLineageSidecarV1,
) -> None:
    service = ResearchRunService(_config(tmp_path))
    saved = service.save_run(
        _metadata("registry-wrong-parent"),
        *_frames(),
        replay_lineage_sidecar=_sidecar("parent-original"),
    )
    sidecar_path = service.parquet_dir / saved.data_manifest[
        service.REPLAY_LINEAGE_MANIFEST_KEY
    ]["relative_path"]
    sidecar_path.write_bytes(encode_replay_lineage(replacement_sidecar))
    replaced_bytes = sidecar_path.read_bytes()

    with pytest.raises(ResearchRunIntegrityError):
        service.load_run_data(saved.run_id)
    with pytest.raises(ResearchRunIntegrityError):
        service.save_run(
            _metadata("registry-wrong-parent"),
            *_frames(),
            replay_lineage_sidecar=_sidecar("parent-original"),
        )
    assert sidecar_path.read_bytes() == replaced_bytes

    legacy_service = ResearchRunService(_config(tmp_path / "legacy"))
    legacy = legacy_service.save_run(
        _metadata("registry-legacy-no-lineage"),
        *_frames(),
    )
    assert legacy_service.load_run_data(legacy.run_id).replay_lineage is None


def test_registry_and_replay_parent_identity_must_remain_distinct(tmp_path: Path) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    with pytest.raises(ResearchRunIntegrityError):
        service.save_run(
            _metadata("same-identity"),
            *_frames(),
            replay_lineage_sidecar=_sidecar("same-identity"),
        )
    assert ResearchRunRepository(config).get_raw_metadata_row("same-identity") is None


def test_manifest_descriptor_without_sidecar_bytes_fails_before_reservation(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    metadata = _metadata("registry-descriptor-only")
    metadata = replace(
        metadata,
        data_manifest={
            **metadata.data_manifest,
            service.REPLAY_LINEAGE_MANIFEST_KEY: None,
        },
    )

    with pytest.raises(ResearchRunIntegrityError):
        service.save_run(metadata, *_frames())
    assert ResearchRunRepository(config).get_raw_metadata_row(metadata.run_id) is None


def test_load_and_retry_reject_final_symlink_without_touching_target(
    tmp_path: Path,
) -> None:
    service = ResearchRunService(_config(tmp_path))
    saved = service.save_run(
        _metadata("registry-symlink"),
        *_frames(),
        replay_lineage_sidecar=_sidecar("parent-symlink"),
    )
    final_path = service.parquet_dir / saved.data_manifest[
        service.REPLAY_LINEAGE_MANIFEST_KEY
    ]["relative_path"]
    target_path = tmp_path / "external-sidecar.json"
    original_bytes = final_path.read_bytes()
    target_path.write_bytes(original_bytes)
    final_path.unlink()
    try:
        final_path.symlink_to(target_path)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"此環境不允許建立合成 symlink: {exc}")

    with pytest.raises(ResearchRunIntegrityError):
        service.load_run_data(saved.run_id)
    with pytest.raises(ResearchRunIntegrityError):
        service.save_run(
            _metadata("registry-symlink"),
            *_frames(),
            replay_lineage_sidecar=_sidecar("parent-symlink"),
        )
    assert target_path.read_bytes() == original_bytes
