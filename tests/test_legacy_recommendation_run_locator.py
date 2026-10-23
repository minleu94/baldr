from __future__ import annotations

from pathlib import Path

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


def test_catalog_claims_do_not_authorize_original_custody(tmp_path: Path):
    entries = load_pinned_legacy_recommendation_locators()
    assert entries is not None
    for entry in entries:
        assert locate_legacy_recommendation_run(
            str(entry['result_id']), str(entry['origin_path']),
            runs_root=tmp_path, db_row_sha256=str(entry['db_row_sha256']),
        ) is None
