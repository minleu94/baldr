"""R020 Stage B2：Registry portfolio sidecar 發布的 synthetic TEMP tests。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
)
from app_module.recommendation.replay_lineage import (
    ReplayLineageSidecarV1,
    decode_replay_lineage_envelope,
    encode_replay_lineage,
)
from app_module.research_run_dtos import ResearchRunMetadataDTO, canonical_json
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


_PORTFOLIO_PARENT_ID = "portfolio-parent-r020-stage-b2"


def _config(tmp_path: Path) -> TWStockConfig:
    return TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    equity = pd.DataFrame(
        {"date": ["2026-09-22", "2026-09-23"], "equity": [1000, 1010]}
    )
    trades = pd.DataFrame(
        {
            "date": ["2026-09-23"],
            "stock_code": ["2330"],
            "shares": [10],
            "side": ["buy"],
        }
    )
    return equity, trades


def _result(equity: pd.DataFrame, trades: pd.DataFrame) -> RecommendationPortfolioBacktestResultDTO:
    result = RecommendationPortfolioBacktestResultDTO(
        summary={"status": "synthetic", "count": 1},
        equity_curve=equity.copy(deep=True),
        trades=trades.copy(deep=True),
        snapshots=[],
        period_holdings=[],
        stock_contribution=[],
        selection_diagnostics=["TEMP only"],
        improvement_hints=[],
        details={"nested": {"safe": True}},
    )
    result.attach_replay_parent_id(_PORTFOLIO_PARENT_ID)
    return result


def _metadata(
    run_id: str,
    *,
    lineage_unavailable: bool = False,
) -> ResearchRunMetadataDTO:
    manifest: dict[str, object] = {
        "synthetic_source": {"version": "fixture-v1"},
    }
    if lineage_unavailable:
        manifest["replay_lineage_status"] = {
            "schema_version": 1,
            "status": "unavailable",
            "parent_result_id": _PORTFOLIO_PARENT_ID,
            "reason": "canonical_child_unavailable",
        }
    return ResearchRunMetadataDTO(
        run_id=run_id,
        run_name="Synthetic R020 portfolio",
        run_type="recommendation_portfolio",
        strategy_id="synthetic",
        original_input={"config": {"profile_id": "TEMP"}},
        normalized_params={"start_date": "2026-09-22", "end_date": "2026-09-23"},
        metrics={"total_return": "0.01"},
        data_manifest=manifest,
        payload_hash="sha256:caller-input-placeholder",
        created_at="2026-09-24T10:00:00-07:00",
    )


def _save(service: ResearchRunService, run_id: str, *, fail_at: str | None = None):
    equity, trades = _frames()
    return service.save_run(
        _metadata(run_id, lineage_unavailable=True),
        equity,
        trades,
        portfolio_result=_result(equity, trades),
        fail_at=fail_at,
    )


def _replace_lineage_parent_and_rehash_registry(
    service: ResearchRunService,
    metadata: ResearchRunMetadataDTO,
    *,
    new_parent_id: str,
    lineage_path: Path,
) -> None:
    lineage_bytes = encode_replay_lineage(
        ReplayLineageSidecarV1(parent_result_id=new_parent_id, children=())
    )
    envelope = decode_replay_lineage_envelope(lineage_bytes)
    paths = service._paths_for(metadata.run_id)
    manifest = dict(metadata.data_manifest)
    manifest[service.REPLAY_LINEAGE_MANIFEST_KEY] = service._replay_lineage_descriptor(
        envelope, paths
    )
    candidate = replace(metadata, data_manifest=manifest)
    payload_hash = service._recommendation_portfolio_payload_hash(candidate)
    lineage_path.write_bytes(lineage_bytes)
    with sqlite3.connect(service.repository.db_path) as connection:
        connection.execute(
            "UPDATE research_runs SET data_manifest_json = ?, payload_hash = ? WHERE run_id = ?",
            (canonical_json(manifest), payload_hash, metadata.run_id),
        )


def test_opt_in_portfolio_save_readback_and_exact_retry(tmp_path: Path) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    saved = _save(service, "r020-b2-complete")

    descriptor = saved.data_manifest[ResearchRunRepository.PORTFOLIO_RESULT_DESCRIPTOR_KEY]
    assert saved.data_manifest[ResearchRunRepository.PORTFOLIO_RESULT_REQUIRED_MARKER] is True
    assert descriptor["registry_run_id"] == saved.run_id
    assert descriptor["portfolio_parent_id"] == "portfolio-parent-r020-stage-b2"
    assert descriptor["relative_path"].endswith("_portfolio_result.json")
    assert Path(saved.equity_path).is_absolute()
    assert Path(saved.trades_path).is_absolute()

    reader = ResearchRunService(config)
    loaded = reader.load_run_data(saved.run_id)
    assert loaded.equity.equals(_frames()[0])
    assert loaded.trades.equals(_frames()[1])
    assert loaded.portfolio_result_artifact is not None
    assert loaded.portfolio_result_artifact.registry_run_id == saved.run_id
    assert loaded.portfolio_result_artifact.portfolio_parent_id == descriptor[
        "portfolio_parent_id"
    ]
    assert loaded.portfolio_result_artifact.raw_payload_sha256 == descriptor[
        "raw_payload_sha256"
    ]
    assert saved.data_manifest["replay_lineage_status"] == {
        "schema_version": 1,
        "status": "unavailable",
        "parent_result_id": _PORTFOLIO_PARENT_ID,
        "reason": "canonical_child_unavailable",
    }

    retried = _save(ResearchRunService(config), saved.run_id)
    assert retried == saved


@pytest.mark.parametrize(
    "status",
    [
        None,
        {
            "schema_version": 1,
            "status": "unavailable",
            "parent_result_id": "different-parent",
            "reason": "canonical_child_unavailable",
        },
        {
            "schema_version": 1,
            "status": "available",
            "parent_result_id": _PORTFOLIO_PARENT_ID,
            "reason": "canonical_child_unavailable",
        },
        {
            "schema_version": 1,
            "status": "unavailable",
            "parent_result_id": _PORTFOLIO_PARENT_ID,
            "reason": "unspecified",
        },
    ],
)
def test_no_lineage_sidecar_requires_explicit_parent_bound_unavailable_status(
    tmp_path: Path,
    status: object,
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    run_id = "r020-b2-lineage-status-required"
    equity, trades = _frames()
    metadata = _metadata(run_id)
    manifest = dict(metadata.data_manifest)
    if status is None:
        manifest.pop("replay_lineage_status", None)
    else:
        manifest["replay_lineage_status"] = status
    metadata = replace(metadata, data_manifest=manifest)

    with pytest.raises(ResearchRunIntegrityError, match="parent-bound unavailable"):
        service.save_run(
            metadata,
            equity,
            trades,
            portfolio_result=_result(equity, trades),
        )

    assert service.repository.get_raw_metadata_row(run_id) is None
    paths = service._paths_for(run_id)
    assert not paths["equity_temp"].exists()
    assert not paths["portfolio_result_temp"].exists()


def test_lineage_sidecar_rejects_contradictory_unavailable_status(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    run_id = "r020-b2-lineage-status-contradiction"
    equity, trades = _frames()

    with pytest.raises(ResearchRunIntegrityError, match="不可同時提供 replay_lineage_status"):
        service.save_run(
            _metadata(run_id, lineage_unavailable=True),
            equity,
            trades,
            portfolio_result=_result(equity, trades),
            replay_lineage_sidecar=ReplayLineageSidecarV1(
                parent_result_id=_PORTFOLIO_PARENT_ID,
                children=(),
            ),
        )

    assert service.repository.get_raw_metadata_row(run_id) is None
    assert not service._paths_for(run_id)["equity_temp"].exists()


def test_lineage_sidecar_rejects_null_status_key_before_any_write(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    run_id = "r020-b2-lineage-null-status"
    equity, trades = _frames()
    metadata = _metadata(run_id)
    manifest = dict(metadata.data_manifest)
    manifest["replay_lineage_status"] = None

    with pytest.raises(ResearchRunIntegrityError, match="不可同時提供 replay_lineage_status"):
        service.save_run(
            replace(metadata, data_manifest=manifest),
            equity,
            trades,
            portfolio_result=_result(equity, trades),
            replay_lineage_sidecar=ReplayLineageSidecarV1(
                parent_result_id=_PORTFOLIO_PARENT_ID,
                children=(),
            ),
        )

    assert service.repository.get_raw_metadata_row(run_id) is None
    assert not service._paths_for(run_id)["equity_temp"].exists()
    assert not service._paths_for(run_id)["portfolio_result_temp"].exists()


def test_legacy_portfolio_caller_without_dto_remains_markerless(tmp_path: Path) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    equity, trades = _frames()
    metadata = replace(_metadata("r020-b2-legacy"), payload_hash="sha256:legacy")

    saved = service.save_run(metadata, equity, trades)
    loaded = ResearchRunService(config).load_run_data(saved.run_id)

    assert ResearchRunRepository.PORTFOLIO_RESULT_REQUIRED_MARKER not in saved.data_manifest
    assert loaded.portfolio_result_artifact is None
    assert loaded.equity.equals(equity)
    assert loaded.trades.equals(trades)


def test_markerless_committed_run_rejects_orphan_portfolio_sidecar(tmp_path: Path) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    equity, trades = _frames()
    saved = service.save_run(
        replace(_metadata("r020-b2-orphan"), payload_hash="sha256:legacy"),
        equity,
        trades,
    )
    orphan = service._paths_for(saved.run_id)["portfolio_result_final"]
    orphan.write_bytes(b"orphan TEMP artifact")

    with pytest.raises(ResearchRunIntegrityError):
        ResearchRunService(config).load_run_data(saved.run_id)


@pytest.mark.parametrize(
    ("fail_at", "expected_state"),
    [
        ("after_staging_row", "failed"),
        ("after_temp_write", "failed"),
        ("after_portfolio_result_temp_write", "failed"),
        ("after_portfolio_result_finalize", "failed"),
        ("after_hash", "committed"),
        ("after_first_rename", "committed"),
        ("after_second_rename", "committed"),
        ("after_portfolio_result_rename", "committed"),
        ("after_replay_lineage_rename", "committed"),
        ("before_final_commit", "committed"),
    ],
)
def test_reconcile_recovers_only_complete_marked_artifacts(
    tmp_path: Path, fail_at: str, expected_state: str
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    run_id = f"r020-b2-{fail_at}"
    equity, trades = _frames()
    lineage = None
    if fail_at == "after_replay_lineage_rename":
        lineage = ReplayLineageSidecarV1(
            parent_result_id="portfolio-parent-r020-stage-b2", children=()
        )
    with pytest.raises(InjectedResearchRunFailure):
        service.save_run(
            _metadata(run_id, lineage_unavailable=lineage is None),
            equity,
            trades,
            portfolio_result=_result(equity, trades),
            replay_lineage_sidecar=lineage,
            fail_at=fail_at,
        )

    recovered = ResearchRunService(config)
    recovered.reconcile_incomplete_saves()
    row = ResearchRunRepository(config).get_raw_metadata_row(run_id)
    assert row is not None
    assert row["storage_state"] == expected_state
    if expected_state == "failed":
        assert row["integrity_status"] == "failed"
        with pytest.raises(ResearchRunIntegrityError):
            recovered.load_run_data(run_id)
    else:
        loaded = recovered.load_run_data(run_id)
        assert loaded.portfolio_result_artifact is not None


@pytest.mark.parametrize("damage", ["missing-sidecar", "tampered-sidecar", "tampered-parquet"])
def test_files_ready_missing_or_damaged_payload_fails_closed(
    tmp_path: Path, damage: str
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    run_id = f"r020-b2-damage-{damage}"
    with pytest.raises(InjectedResearchRunFailure):
        _save(service, run_id, fail_at="after_hash")
    paths = service._paths_for(run_id)
    target = (
        paths["portfolio_result_temp"]
        if damage in {"missing-sidecar", "tampered-sidecar"}
        else paths["equity_temp"]
    )
    if damage == "missing-sidecar":
        target.unlink()
    else:
        target.write_bytes(b"tampered TEMP bytes")

    service.reconcile_incomplete_saves()
    row = service.repository.get_raw_metadata_row(run_id)
    assert row is not None and row["storage_state"] == "failed"
    with pytest.raises(ResearchRunIntegrityError):
        service.load_run_data(run_id)


def test_committed_tamper_and_same_id_different_content_are_rejected(tmp_path: Path) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    saved = _save(service, "r020-b2-conflict")

    equity, trades = _frames()
    altered = _result(equity, trades)
    altered.details["nested"]["safe"] = False
    with pytest.raises(ResearchRunConflictError):
        service.save_run(
            _metadata(saved.run_id, lineage_unavailable=True),
            equity,
            trades,
            portfolio_result=altered,
        )

    changed_equity = equity.copy(deep=True)
    changed_equity.loc[0, "equity"] = 9999
    changed_result = _result(changed_equity, trades)
    with pytest.raises(ResearchRunConflictError):
        service.save_run(
            _metadata(saved.run_id, lineage_unavailable=True),
            changed_equity,
            trades,
            portfolio_result=changed_result,
        )

    sidecar_path = service._paths_for(saved.run_id)["portfolio_result_final"]
    sidecar_path.write_bytes(b"tampered committed sidecar")
    with pytest.raises(ResearchRunIntegrityError):
        ResearchRunService(config).load_run_data(saved.run_id)

    sidecar_path.unlink()
    with pytest.raises(ResearchRunIntegrityError):
        ResearchRunService(config).load_run_data(saved.run_id)


@pytest.mark.parametrize("fail_at", ["after_staging_row", "after_hash"])
def test_same_id_staging_or_failed_row_is_never_taken_over(
    tmp_path: Path, fail_at: str
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    run_id = f"r020-b2-no-takeover-{fail_at}"
    with pytest.raises(InjectedResearchRunFailure):
        _save(service, run_id, fail_at=fail_at)
    if fail_at == "after_hash":
        paths = service._paths_for(run_id)
        paths["portfolio_result_temp"].unlink()
        service.reconcile_incomplete_saves()
    with pytest.raises((ResearchRunIntegrityError, ResearchRunConflictError)):
        _save(ResearchRunService(config), run_id)


def test_marked_retry_with_optional_replay_lineage_is_verified(tmp_path: Path) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    equity, trades = _frames()
    result = _result(equity, trades)
    lineage = ReplayLineageSidecarV1(
        parent_result_id="portfolio-parent-r020-stage-b2", children=()
    )
    saved = service.save_run(
        _metadata("r020-b2-with-lineage"),
        equity,
        trades,
        portfolio_result=result,
        replay_lineage_sidecar=lineage,
    )

    loaded = ResearchRunService(config).load_run_data(saved.run_id)
    assert loaded.portfolio_result_artifact is not None
    assert loaded.replay_lineage is not None
    assert loaded.replay_lineage.sidecar.parent_result_id == lineage.parent_result_id
    assert (
        ResearchRunService(config).save_run(
            _metadata(saved.run_id),
            equity,
            trades,
            portfolio_result=result,
            replay_lineage_sidecar=lineage,
        )
        == saved
    )


def test_marked_load_rejects_valid_replay_lineage_with_different_parent(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    equity, trades = _frames()
    result = _result(equity, trades)
    matching_parent = "portfolio-parent-r020-stage-b2"
    saved = service.save_run(
        _metadata("r020-b2-cross-parent-load"),
        equity,
        trades,
        portfolio_result=result,
        replay_lineage_sidecar=ReplayLineageSidecarV1(
            parent_result_id=matching_parent, children=()
        ),
    )
    paths = service._paths_for(saved.run_id)
    lineage_path = paths["replay_lineage_final"]
    _replace_lineage_parent_and_rehash_registry(
        service,
        saved,
        new_parent_id="different-valid-parent",
        lineage_path=lineage_path,
    )
    assert (
        decode_replay_lineage_envelope(lineage_path.read_bytes())
        .sidecar.parent_result_id
        == "different-valid-parent"
    )

    with pytest.raises(
        ResearchRunIntegrityError,
        match="portfolio result 與 replay lineage parent identity 不一致",
    ):
        ResearchRunService(config).load_run_data(saved.run_id)


def test_files_ready_reconcile_rejects_valid_lineage_with_different_parent(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    equity, trades = _frames()
    run_id = "r020-b2-cross-parent-reconcile"
    with pytest.raises(InjectedResearchRunFailure):
        service.save_run(
            _metadata(run_id),
            equity,
            trades,
            portfolio_result=_result(equity, trades),
            replay_lineage_sidecar=ReplayLineageSidecarV1(
                parent_result_id="portfolio-parent-r020-stage-b2", children=()
            ),
            fail_at="after_hash",
        )
    staged = service.repository.get_metadata(run_id)
    assert staged is not None
    paths = service._paths_for(run_id)
    _replace_lineage_parent_and_rehash_registry(
        service,
        staged,
        new_parent_id="different-valid-parent",
        lineage_path=paths["replay_lineage_temp"],
    )

    service.reconcile_incomplete_saves()
    raw = service.repository.get_raw_metadata_row(run_id)
    assert raw is not None
    assert raw["storage_state"] == "failed"
    assert raw["integrity_status"] == "failed"


def test_reconciler_stale_failure_cas_cannot_overwrite_a_committed_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    run_id = "r020-b2-reconcile-cas"
    with pytest.raises(InjectedResearchRunFailure):
        _save(service, run_id, fail_at="after_hash")
    stale_row = service.repository.get_raw_metadata_row(run_id)
    metadata = service.repository.get_metadata(run_id)
    assert stale_row is not None and metadata is not None
    finish_files_ready = service._finish_portfolio_files_ready_row

    def competing_verified_owner(_row, _metadata) -> bool:
        # 模擬另一 reconciler 已驗完整 artifacts 並先完成 commit。
        assert finish_files_ready(_row, _metadata)
        service.repository.mark_portfolio_result_committed(
            run_id,
            expected_payload_hash=stale_row["payload_hash"],
            expected_data_manifest=metadata.data_manifest,
        )
        return False

    monkeypatch.setattr(
        service,
        "_finish_portfolio_files_ready_row",
        competing_verified_owner,
    )
    service.reconcile_incomplete_saves()
    current = service.repository.get_raw_metadata_row(run_id)
    assert current is not None
    assert current["storage_state"] == "committed"
    assert current["integrity_status"] == "valid"
    assert service.load_run_data(run_id).portfolio_result_artifact is not None


@pytest.mark.parametrize("rehash_registry_metadata", [False, True])
def test_committed_marker_descriptor_and_sidecar_identity_are_fail_closed(
    tmp_path: Path, rehash_registry_metadata: bool
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    saved = _save(service, "r020-b2-identity")
    repository = service.repository
    descriptor = dict(saved.data_manifest[service.PORTFOLIO_RESULT_DESCRIPTOR_KEY])
    descriptor["registry_run_id"] = "another-run"
    manifest = dict(saved.data_manifest)
    manifest[service.PORTFOLIO_RESULT_DESCRIPTOR_KEY] = descriptor
    candidate = replace(saved, data_manifest=manifest)
    payload_hash = (
        service._recommendation_portfolio_payload_hash(candidate)
        if rehash_registry_metadata
        else saved.payload_hash
    )
    with sqlite3.connect(repository.db_path) as connection:
        connection.execute(
            "UPDATE research_runs SET data_manifest_json = ?, payload_hash = ? WHERE run_id = ?",
            (canonical_json(manifest), payload_hash, saved.run_id),
        )
    with pytest.raises(ResearchRunIntegrityError):
        ResearchRunService(config).load_run_data(saved.run_id)


def test_marked_read_rejects_stale_outer_payload_hash_after_metrics_change(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    service = ResearchRunService(config)
    saved = _save(service, "r020-b2-stale-outer-hash")
    raw_before = service.repository.get_raw_metadata_row(saved.run_id)
    sidecar_before = service._paths_for(saved.run_id)["portfolio_result_final"].read_bytes()
    assert raw_before is not None
    changed_metrics = dict(saved.metrics)
    changed_metrics["total_return"] = "0.02"

    # 只竄改 canonical Registry payload 的 metrics；manifest descriptor、兩份
    # Parquet hashes、sidecar bytes 與舊 outer payload_hash 全部保持原樣。
    with sqlite3.connect(service.repository.db_path) as connection:
        connection.execute(
            "UPDATE research_runs SET metrics_json = ? WHERE run_id = ?",
            (canonical_json(changed_metrics), saved.run_id),
        )
    raw_after = service.repository.get_raw_metadata_row(saved.run_id)
    assert raw_after is not None
    assert raw_after["payload_hash"] == raw_before["payload_hash"]
    assert raw_after["data_manifest_json"] == raw_before["data_manifest_json"]
    assert service._paths_for(saved.run_id)["portfolio_result_final"].read_bytes() == sidecar_before

    with pytest.raises(
        ResearchRunIntegrityError,
        match="payload_hash 未綁定 portfolio result descriptor",
    ):
        ResearchRunService(config).load_run_data(saved.run_id)
