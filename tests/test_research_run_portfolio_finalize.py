"""Portfolio result sidecar 發布前 Registry staging CAS contract tests。"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from threading import Barrier
from typing import Any

import pytest

from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_repository import (
    ResearchRunConflictError,
    ResearchRunRepository,
    ResearchRunRepositoryError,
)
from app_module.research_run_service import ResearchRunService
from data_module.config import TWStockConfig


def _sha(char: str) -> str:
    return f"sha256:{char * 64}"


def _descriptor(run_id: str = "portfolio-run-001") -> dict[str, Any]:
    return {
        "schema_version": "recommendation-portfolio-result.v1",
        "schema_revision": 1,
        "registry_run_id": run_id,
        "portfolio_parent_id": "portfolio-parent-001",
        "relative_path": f"portfolio_results/{run_id}.json",
        "raw_payload_sha256": _sha("a"),
        "payload_hash": _sha("b"),
        "equity_parquet_sha256": _sha("c"),
        "trades_parquet_sha256": _sha("d"),
    }


def _base_metadata(
    *, run_id: str = "portfolio-run-001", run_type: str = "recommendation_portfolio"
) -> ResearchRunMetadataDTO:
    return ResearchRunMetadataDTO(
        run_id=run_id,
        run_name="portfolio run",
        run_type=run_type,
        strategy_id="strategy-v1",
        strategy_version="1",
        parameter_contract_version="params.v1",
        original_input={"source": "synthetic"},
        normalized_params={"top_n": 5},
        fallback_reason={},
        universe=["2330"],
        start_date="2026-01-01",
        end_date="2026-01-31",
        data_cutoff_date="2025-12-31",
        data_fingerprint=_sha("e"),
        fingerprint_algorithm="sha256",
        data_manifest={
            "legacy_manifest": {"retained": True},
            "factor_snapshot": {"as_of_date": "2025-12-31", "values": {"pe": "12.3"}},
            "execution_contract": "legacy-same-day-close.v1",
            "replay_lineage_sidecar": {
                "schema_version": "recommendation-replay-lineage.v1",
                "parent_result_id": "replay-parent-001",
            },
        },
        capital_cents=100_000,
        fee_bp_x100=1425,
        slippage_bp_x100=500,
        execution_price="close.v1",
        sizing_mode="fixed_weight",
        metrics={"return_bp": 123},
        payload_hash=_sha("f"),
        equity_path="staging/portfolio-run-001-equity.parquet",
        equity_parquet_hash=_sha("1"),
        trades_path="staging/portfolio-run-001-trades.parquet",
        trades_parquet_hash=_sha("2"),
        created_at="2026-09-24T12:00:00-07:00",
    )


def _final_metadata(
    base: ResearchRunMetadataDTO, repository: ResearchRunRepository
) -> ResearchRunMetadataDTO:
    manifest = deepcopy(base.data_manifest)
    manifest.update(
        portfolio_result_required=True,
        portfolio_result_sidecar=_descriptor(base.run_id),
    )
    final_paths = ResearchRunService(repository.config)._paths_for(base.run_id)
    return replace(
        base,
        data_manifest=manifest,
        payload_hash=_sha("9"),
        equity_path=str(final_paths["equity_final"]),
        equity_parquet_hash=_sha("c"),
        trades_path=str(final_paths["trades_final"]),
        trades_parquet_hash=_sha("d"),
    )


def _repository(tmp_path) -> ResearchRunRepository:
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    return ResearchRunRepository(config)


def _tracked_row(repository: ResearchRunRepository, run_id: str) -> tuple[Any, ...] | None:
    row = repository.get_raw_metadata_row(run_id)
    if row is None:
        return None
    return tuple(
        row[key]
        for key in (
            "run_type",
            "data_manifest_json",
            "payload_hash",
            "equity_path",
            "equity_parquet_hash",
            "trades_path",
            "trades_parquet_hash",
            "storage_state",
            "integrity_status",
        )
    )


def test_portfolio_finalize_atomically_updates_descriptor_and_parquet_bindings(tmp_path):
    repository = _repository(tmp_path)
    base = _base_metadata()
    repository.insert_metadata(base, staging=True)
    finalized = _final_metadata(base, repository)

    result = repository.finalize_portfolio_result_staging(
        base.run_id,
        expected_payload_hash=base.payload_hash,
        finalized_metadata=finalized,
    )

    assert result == finalized
    assert repository.get_metadata(base.run_id) == finalized
    row = repository.get_raw_metadata_row(base.run_id)
    assert row is not None
    assert row["storage_state"] == "staging"
    assert row["integrity_status"] == "pending"


@pytest.mark.parametrize("field", [
    "original_input", "normalized_params", "fallback_reason", "metrics",
    "regime_breakdown", "benchmark_results",
])
@pytest.mark.parametrize("mutate", [False, True])
def test_portfolio_finalize_preserves_exact_json_decimal_and_rejects_changed_cent(
    tmp_path, field, mutate,
):
    repository = _repository(tmp_path)
    capital = Decimal("9007199254740993.01")
    value = {"capital": capital, "nested": (Decimal("0.01"),)}
    base = replace(_base_metadata(), **{field: value})
    repository.insert_metadata(base, staging=True)
    before = repository.get_raw_metadata_row(base.run_id)
    finalized = _final_metadata(base, repository)
    if mutate:
        finalized = replace(finalized, **{field: dict(value, capital=capital + Decimal("0.01"))})
        with pytest.raises(ResearchRunRepositoryError, match=field):
            repository.finalize_portfolio_result_staging(
                base.run_id, expected_payload_hash=base.payload_hash,
                finalized_metadata=finalized,
            )
        assert repository.get_raw_metadata_row(base.run_id) == before
    else:
        repository.finalize_portfolio_result_staging(
            base.run_id, expected_payload_hash=base.payload_hash,
            finalized_metadata=finalized,
        )
        loaded = repository.get_metadata(base.run_id)
        assert loaded is not None
        assert getattr(loaded, field) == {
            "capital": "9007199254740993.01", "nested": ["0.01"],
        }


def test_portfolio_finalize_rejects_stale_hash_and_preserves_row(tmp_path):
    repository = _repository(tmp_path)
    base = _base_metadata()
    repository.insert_metadata(base, staging=True)
    before = _tracked_row(repository, base.run_id)

    with pytest.raises(ResearchRunConflictError):
        repository.finalize_portfolio_result_staging(
            base.run_id,
            expected_payload_hash=_sha("0"),
            finalized_metadata=_final_metadata(base, repository),
        )

    assert _tracked_row(repository, base.run_id) == before


@pytest.mark.parametrize(
    ("storage_state", "integrity_status"),
    [
        ("staging", "valid"),
        ("files_ready", "pending"),
        ("files_ready", "valid"),
        ("committed", "valid"),
        ("failed", "invalid"),
    ],
)
def test_portfolio_finalize_rejects_non_staging_states_without_mutation(
    tmp_path, storage_state: str, integrity_status: str
):
    repository = _repository(tmp_path)
    base = _base_metadata()
    repository.insert_metadata(base, staging=True)
    repository.update_storage_fields(
        base.run_id,
        storage_state=storage_state,
        integrity_status=integrity_status,
    )
    before = _tracked_row(repository, base.run_id)

    with pytest.raises(ResearchRunConflictError):
        repository.finalize_portfolio_result_staging(
            base.run_id,
            expected_payload_hash=base.payload_hash,
            finalized_metadata=_final_metadata(base, repository),
        )

    assert _tracked_row(repository, base.run_id) == before


def test_portfolio_finalize_rejects_missing_run_without_insert(tmp_path):
    repository = _repository(tmp_path)
    base = _base_metadata()

    with pytest.raises(ResearchRunConflictError):
        repository.finalize_portfolio_result_staging(
            base.run_id,
            expected_payload_hash=base.payload_hash,
            finalized_metadata=_final_metadata(base, repository),
        )

    assert repository.get_raw_metadata_row(base.run_id) is None


def test_portfolio_finalize_rejects_row_type_mismatch(tmp_path):
    repository = _repository(tmp_path)
    base = _base_metadata()
    repository.insert_metadata(base, staging=True)
    with sqlite3.connect(repository.db_path) as conn:
        conn.execute(
            "UPDATE research_runs SET run_type = ? WHERE run_id = ?",
            ("single_backtest", base.run_id),
        )
    before = _tracked_row(repository, base.run_id)

    with pytest.raises(ResearchRunConflictError):
        repository.finalize_portfolio_result_staging(
            base.run_id,
            expected_payload_hash=base.payload_hash,
            finalized_metadata=_final_metadata(base, repository),
        )

    assert _tracked_row(repository, base.run_id) == before


@pytest.mark.parametrize(
    "mutate",
    [
        lambda manifest: manifest.pop("portfolio_result_required"),
        lambda manifest: manifest.pop("portfolio_result_sidecar"),
        lambda manifest: manifest["portfolio_result_sidecar"].update(
            registry_run_id="another-run"
        ),
        lambda manifest: manifest["portfolio_result_sidecar"].update(
            portfolio_parent_id="portfolio-run-001"
        ),
        lambda manifest: manifest["portfolio_result_sidecar"].update(
            relative_path="../outside.json"
        ),
        lambda manifest: manifest["portfolio_result_sidecar"].update(
            relative_path="/outside.json"
        ),
        lambda manifest: manifest["portfolio_result_sidecar"].update(
            equity_parquet_sha256=_sha("8")
        ),
    ],
)
def test_portfolio_finalize_rejects_invalid_descriptor_bindings(tmp_path, mutate):
    repository = _repository(tmp_path)
    base = _base_metadata()
    repository.insert_metadata(base, staging=True)
    before = _tracked_row(repository, base.run_id)
    finalized = _final_metadata(base, repository)
    manifest = dict(finalized.data_manifest)
    manifest["portfolio_result_sidecar"] = dict(manifest["portfolio_result_sidecar"])
    mutate(manifest)
    invalid = replace(finalized, data_manifest=manifest)

    with pytest.raises(ResearchRunRepositoryError):
        repository.finalize_portfolio_result_staging(
            base.run_id,
            expected_payload_hash=base.payload_hash,
            finalized_metadata=invalid,
        )

    assert _tracked_row(repository, base.run_id) == before
    assert repository.get_metadata(base.run_id) == base


@pytest.mark.parametrize(
    "mutate",
    [
        lambda manifest: manifest.pop("factor_snapshot"),
        lambda manifest: manifest["factor_snapshot"]["values"].update(pe="999"),
        lambda manifest: manifest["replay_lineage_sidecar"].update(
            parent_result_id="different-parent"
        ),
        lambda manifest: manifest.update(execution_contract="changed.v9"),
    ],
)
def test_portfolio_finalize_cannot_drop_or_mutate_existing_manifest_values(
    tmp_path, mutate
):
    repository = _repository(tmp_path)
    base = _base_metadata()
    repository.insert_metadata(base, staging=True)
    before = _tracked_row(repository, base.run_id)
    finalized = _final_metadata(base, repository)
    manifest = deepcopy(finalized.data_manifest)
    mutate(manifest)

    with pytest.raises(ResearchRunRepositoryError):
        repository.finalize_portfolio_result_staging(
            base.run_id,
            expected_payload_hash=base.payload_hash,
            finalized_metadata=replace(finalized, data_manifest=manifest),
        )

    assert _tracked_row(repository, base.run_id) == before
    assert repository.get_metadata(base.run_id) == base


@pytest.mark.parametrize(
    "existing_key,value",
    [
        ("portfolio_result_required", False),
        ("portfolio_result_sidecar", {"older": "descriptor"}),
    ],
)
def test_portfolio_finalize_does_not_overwrite_reserved_existing_manifest_keys(
    tmp_path, existing_key: str, value: object
):
    repository = _repository(tmp_path)
    base = _base_metadata()
    manifest = deepcopy(base.data_manifest)
    manifest[existing_key] = value
    base = replace(base, data_manifest=manifest)
    repository.insert_metadata(base, staging=True)
    before = _tracked_row(repository, base.run_id)

    with pytest.raises(ResearchRunRepositoryError):
        repository.finalize_portfolio_result_staging(
            base.run_id,
            expected_payload_hash=base.payload_hash,
            finalized_metadata=_final_metadata(base, repository),
        )

    assert _tracked_row(repository, base.run_id) == before
    assert repository.get_metadata(base.run_id) == base


@pytest.mark.parametrize("path_kind", ["relative", "outside", "root"])
def test_portfolio_finalize_rejects_parquet_paths_outside_configured_root(
    tmp_path, path_kind: str
):
    repository = _repository(tmp_path)
    base = _base_metadata()
    repository.insert_metadata(base, staging=True)
    before = _tracked_row(repository, base.run_id)
    finalized = _final_metadata(base, repository)
    if path_kind == "relative":
        bad_path = "parquet/relative.parquet"
    elif path_kind == "outside":
        bad_path = str(tmp_path / "other" / "outside.parquet")
    else:
        bad_path = str(repository.config.research_run_parquet_dir)

    with pytest.raises(ResearchRunRepositoryError):
        repository.finalize_portfolio_result_staging(
            base.run_id,
            expected_payload_hash=base.payload_hash,
            finalized_metadata=replace(finalized, equity_path=bad_path),
        )

    assert _tracked_row(repository, base.run_id) == before


def test_portfolio_finalize_rejects_parquet_path_aliases_after_resolution(tmp_path):
    repository = _repository(tmp_path)
    base = _base_metadata()
    repository.insert_metadata(base, staging=True)
    before = _tracked_row(repository, base.run_id)
    finalized = _final_metadata(base, repository)
    parquet_root = repository.config.research_run_parquet_dir
    aliased = replace(
        finalized,
        equity_path=str(parquet_root / "nested" / ".." / "same.parquet"),
        trades_path=str(parquet_root / "same.parquet"),
    )

    with pytest.raises(ResearchRunRepositoryError, match="必須分離"):
        repository.finalize_portfolio_result_staging(
            base.run_id,
            expected_payload_hash=base.payload_hash,
            finalized_metadata=aliased,
        )

    assert _tracked_row(repository, base.run_id) == before


def test_portfolio_finalize_rejects_changes_to_unrelated_metadata(tmp_path):
    repository = _repository(tmp_path)
    base = _base_metadata()
    repository.insert_metadata(base, staging=True)
    finalized = replace(
        _final_metadata(base, repository), run_name="mutated identity"
    )
    before = _tracked_row(repository, base.run_id)

    with pytest.raises(ResearchRunRepositoryError):
        repository.finalize_portfolio_result_staging(
            base.run_id,
            expected_payload_hash=base.payload_hash,
            finalized_metadata=finalized,
        )

    assert _tracked_row(repository, base.run_id) == before


def test_portfolio_finalize_winner_prevents_same_base_hash_competitor(tmp_path):
    repository = _repository(tmp_path)
    base = _base_metadata()
    repository.insert_metadata(base, staging=True)
    winner = _final_metadata(base, repository)
    repository.finalize_portfolio_result_staging(
        base.run_id,
        expected_payload_hash=base.payload_hash,
        finalized_metadata=winner,
    )
    after_winner = _tracked_row(repository, base.run_id)
    loser = replace(winner, payload_hash=_sha("7"))

    with pytest.raises(ResearchRunConflictError):
        repository.finalize_portfolio_result_staging(
            base.run_id,
            expected_payload_hash=base.payload_hash,
            finalized_metadata=loser,
        )

    assert _tracked_row(repository, base.run_id) == after_winner


def test_portfolio_finalize_concurrent_same_base_hash_has_one_winner(tmp_path):
    repository = _repository(tmp_path)
    base = _base_metadata()
    repository.insert_metadata(base, staging=True)
    candidates = [
        _final_metadata(base, repository),
        replace(_final_metadata(base, repository), payload_hash=_sha("7")),
    ]
    barrier = Barrier(2)

    def finalize(candidate: ResearchRunMetadataDTO) -> bool:
        barrier.wait(timeout=5)
        try:
            repository.finalize_portfolio_result_staging(
                base.run_id,
                expected_payload_hash=base.payload_hash,
                finalized_metadata=candidate,
            )
        except ResearchRunConflictError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(finalize, candidates))

    assert sorted(outcomes) == [False, True]
    loaded = repository.get_metadata(base.run_id)
    assert loaded in candidates


def test_portfolio_finalize_rolls_back_when_sqlite_update_fails(tmp_path):
    repository = _repository(tmp_path)
    base = _base_metadata()
    repository.insert_metadata(base, staging=True)
    before = _tracked_row(repository, base.run_id)
    with sqlite3.connect(repository.db_path) as conn:
        conn.execute(
            """
            CREATE TRIGGER reject_portfolio_finalize
            BEFORE UPDATE OF data_manifest_json ON research_runs
            BEGIN
                SELECT RAISE(ABORT, 'synthetic finalize failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="synthetic finalize failure"):
        repository.finalize_portfolio_result_staging(
            base.run_id,
            expected_payload_hash=base.payload_hash,
            finalized_metadata=_final_metadata(base, repository),
        )

    assert _tracked_row(repository, base.run_id) == before
