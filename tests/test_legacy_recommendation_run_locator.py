from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app_module.recommendation.queries import RecommendationExecutionQueries
from app_module.recommendation_repository import RecommendationRepository
from data_module.legacy_recommendation_run_locator import (
    load_pinned_legacy_recommendation_locators,
    locate_legacy_recommendation_run,
)


def test_legacy_recommendation_locator_catalog_loads_all_88_entries():
    entries = load_pinned_legacy_recommendation_locators()
    assert entries is not None
    assert len(entries) == 88
    tiers: dict[str, int] = {}
    for entry in entries:
        assert entry["origin_path"].startswith("D:\\Min\\Python\\Project\\FA_Data\\output\\recommendation\\runs\\")
        assert entry["current_path"].endswith(".json")
        assert len(entry["relocated_file_sha256"].removeprefix("sha256:")) == 64
        assert entry["relocated_size_bytes"] > 0
        t = entry["custody_verification_tier"]
        tiers[t] = tiers.get(t, 0) + 1
    assert tiers.get("tier1_independent_pre_migration_file_sha256") == 16
    assert tiers.get("tier2_pre_migration_db_index_and_twstock_event_hash") == 28
    assert tiers.get("tier3_pre_migration_db_index_only_no_independent_file_sha256") == 44


def test_legacy_recommendation_locator_rejects_unpinned(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    unpinned = "D:\\Min\\Python\\Project\\FA_Data\\output\\recommendation\\runs\\rec_unpinned_999999.json"
    assert (
        locate_legacy_recommendation_run(
            "unpinned_id",
            unpinned,
            runs_root=runs_dir,
        )
        is None
    )


def test_full_121_recommendation_query_and_repository_readback_without_db_mutation():
    from app_module.recommendation.persistence import RecommendationExecutionPersistence
    from data_module.config import TWStockConfig
    from data_module.result_artifact_store import ResultArtifactStore

    runs_dir = Path(r"F:\Min\Python\Project\FA_Data\output\recommendation\runs")
    db_path = runs_dir / "recommendation_runs.db"
    if not db_path.is_file() or not runs_dir.is_dir():
        pytest.skip("Formal FA_Data recommendation runs not mounted on this host")

    before_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()

    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=db_path,
    )
    persistence = RecommendationExecutionPersistence(store)
    queries = RecommendationExecutionQueries(persistence)
    models = queries.list()
    assert len(models) == 121

    canonical = [m for m in models if m.execution is not None]
    legacy = [m for m in models if m.legacy_result is not None]
    assert len(canonical) == 33
    assert len(legacy) == 88

    trusted_verified = [m for m in legacy if m.integrity_basis == "legacy_trusted_hash_verified"]
    read_time_only = [m for m in legacy if m.integrity_basis == "legacy_read_time_hash_only"]
    assert len(trusted_verified) == 16
    assert len(read_time_only) == 72

    cfg = TWStockConfig()
    repo = RecommendationRepository(cfg)
    loaded = repo.load_result(legacy[0].result_id)
    assert loaded is not None
    assert loaded.result_id == legacy[0].result_id

    after_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert before_sha == after_sha
