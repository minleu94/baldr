"""真 F17 全母體與月營收封存來源；沒有用新版本取代原收藏錨點。"""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import stat
from threading import Thread
from types import SimpleNamespace
from typing import Any

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)

from app_module.daily_market_technical_official_disposition_revenue_archived_source_v3 import (
    DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3,
    DailyMarketTechnicalOfficialDispositionRevenueArchivedSourceV3Error,
    open_daily_market_technical_official_disposition_revenue_archived_bundle_source_v3,
    reopen_daily_market_technical_official_disposition_revenue_archived_from_recipe_v3,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2,
)
from tests.test_daily_market_technical_official_disposition_revenue_source_v2 import _PROTECTED_ROOTS, _ROW_SCOPES
from tests.test_daily_market_technical_official_disposition_revenue_query_v2 import _daily_f17_environment
from data_module.fundamental_read_snapshot_raw_archive_v2 import FundamentalReadSnapshotRawArchiveReferenceV2


@pytest.fixture
def archive_environment(bundle_fixture: Any, tmp_path: Path) -> Any:
    provider, reader, pin, _, _ = _daily_f17_environment(tmp_path / "daily-source")
    root3 = tmp_path / "original-reference-artifacts"
    root4 = tmp_path / "archive-reference-artifacts"
    root3.mkdir()
    root4.mkdir()
    exact = open_daily_market_technical_official_disposition_revenue_archived_bundle_source_v3(
        archive_parent=tmp_path / "saved-monthly-archives", archived_reference_artifact_root=root4,
        archived_artifact_id="archive-origin", bundle_output_root=bundle_fixture.bundle_root,
        bundle_identity_sha256=bundle_fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=bundle_fixture.reference.manifest_sha256,
        row_scope_filter=_ROW_SCOPES, operation_root=tmp_path / "original-operation",
        monthly_provider=provider, daily_monthly_cohort_reader=reader,
        monthly_reference_artifact_root=root3, artifact_id="original-monthly",
        protected_roots=_PROTECTED_ROOTS, ma_states=("unknown",), minimum_yoy_percent=Decimal("0"),
        condition_combine_mode="OR", unknown_policy="include", sort_clauses=(
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2("monthly_revenue_yoy_percent", "desc"),
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2("stock_code", "asc")),
        page_index=0, page_size=8)
    try:
        yield SimpleNamespace(provider=provider, reader=reader, pin=pin, exact=exact, root3=root3,
                              root4=root4, temp=tmp_path, bundle=bundle_fixture)
    finally:
        exact.close()


def _reopen(env: Any, recipe: Any, *, artifact_id: str = "fresh-monthly", **overrides: Any) -> Any:
    options = dict(operation_root=env.temp / f"operation-{artifact_id}", monthly_provider=env.provider,
        daily_monthly_cohort_reader=env.reader, monthly_reference_artifact_root=env.temp / f"artifacts-{artifact_id}",
        artifact_id=artifact_id, archived_reference_artifact_root=env.root4,
        expected_archive_descriptor_sha256=recipe.archive_artifact_descriptor_external_sha256,
        expected_archive_reference_sha256=recipe.archive_reference_external_sha256,
        expected_monthly_source_reference_sha256=recipe.base_recipe.monthly_source_reference_external_sha256,
        protected_roots=_PROTECTED_ROOTS)
    options.update(overrides)
    Path(options["monthly_reference_artifact_root"]).mkdir(parents=True, exist_ok=True)
    return reopen_daily_market_technical_official_disposition_revenue_archived_from_recipe_v3(recipe, **options)


def _archive_reference(env: Any) -> FundamentalReadSnapshotRawArchiveReferenceV2:
    from app_module.daily_market_monthly_revenue_archive_reference_artifact_v4 import read_daily_market_monthly_revenue_archive_reference_artifact_v4
    recipe = env.exact.saved_recipe
    artifact = read_daily_market_monthly_revenue_archive_reference_artifact_v4(env.root4,
        descriptor=recipe.archive_artifact_descriptor_json.encode("utf-8"),
        expected_descriptor_sha256=recipe.archive_artifact_descriptor_external_sha256,
        protected_roots=_PROTECTED_ROOTS)
    return artifact.raw_archive_reference.reference


def test_archive_source_reopens_original_full_cohort_after_live_and_original_artifact_drift(archive_environment: Any) -> None:
    env = archive_environment
    exact = env.exact
    assert type(exact) is DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3
    assert len(exact.monthly_reference.declared_stock_codes) == 258
    assert exact.page.rows[0].stock_code == "1000"
    assert exact.page.rows[0].monthly_entry.projected_fact.growth_percent == Decimal("22.006875")
    exact.read_page(1, 8)
    recipe = exact.saved_recipe
    original_page_codes = tuple(row.stock_code for row in exact.page.rows)
    original_result_ledger = exact.monthly_reference.result_identity_by_stock
    original_fact_ledger = exact.monthly_reference.fact_identity_by_stock
    original_identity = exact.source_pair_identity_sha256
    original_snapshot = Path(exact.monthly_reference.upstream_reference.snapshot_root)
    raw = recipe.to_json().encode("utf-8")
    archived = _archive_reference(env)
    before = tuple((item.relative_path, sha256((Path(archived.archive_root) / item.relative_path).read_bytes()).hexdigest())
                   for item in (*archived.files, *archived.snapshot_files))
    exact.close()
    with sqlite3.connect(env.provider.db_file) as connection:
        cursor = connection.execute("UPDATE fundamental_current_observations SET value=? WHERE stock_code=? AND kind='monthly_revenue' AND item_code='revenue'",
                                    ("999999999999", "1000"))
        assert cursor.rowcount >= 1
    for item in archived.files:
        path = Path(item.historical_pin.path)
        path.write_bytes(path.read_bytes() + b"\nprivate-revision\n")
    original_snapshot.rename(env.temp / "preserved-original-snapshot")
    env.root3.rename(env.temp / "preserved-original-reference-artifacts")
    assert not original_snapshot.exists() and not env.root3.exists()
    reopened = _reopen(env, recipe)
    try:
        assert reopened.monthly_cohort_pin == env.pin
        assert reopened.monthly_reference.result_identity_by_stock == original_result_ledger
        assert reopened.monthly_reference.fact_identity_by_stock == original_fact_ledger
        assert len(reopened.monthly_reference.declared_stock_codes) == 258
        assert reopened.source_pair_identity_sha256 == original_identity
        assert tuple(row.stock_code for row in reopened.page.rows) == original_page_codes
        assert reopened.request.page_index == 1 and reopened.monthly_sqlite_connection_closed
        assert reopened.saved_recipe.base_recipe.monthly_source_reference_external_sha256 == recipe.base_recipe.monthly_source_reference_external_sha256
        assert reopened.monthly_reference.external_reference_sha256 != recipe.base_recipe.monthly_source_reference_external_sha256
        assert reopened.saved_recipe.to_json().encode("utf-8") == raw
        assert reopened.historical_pit_eligible is reopened.formal_pit_eligible is False
    finally:
        reopened.close()
    after = tuple((item.relative_path, sha256((Path(archived.archive_root) / item.relative_path).read_bytes()).hexdigest())
                  for item in (*archived.files, *archived.snapshot_files))
    assert before == after


@pytest.mark.parametrize("field", ["expected_archive_descriptor_sha256", "expected_archive_reference_sha256", "expected_monthly_source_reference_sha256"])
def test_archive_source_wrong_external_anchor_is_rejected_before_new_operation(archive_environment: Any, field: str) -> None:
    env = archive_environment
    recipe = env.exact.saved_recipe
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueArchivedSourceV3Error):
        _reopen(env, recipe, **{field: "0" * 64})
    assert not (env.temp / "operation-fresh-monthly").exists()


def test_archive_source_rejects_raw_tamper_without_saving_a_new_finished_source(archive_environment: Any) -> None:
    env = archive_environment
    recipe = env.exact.saved_recipe
    reference = _archive_reference(env)
    path = Path(reference.archive_root) / reference.files[0].relative_path
    path.chmod(stat.S_IREAD | stat.S_IWRITE)
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises((ValueError, RuntimeError)):
        _reopen(env, recipe)
    artifact_root = env.temp / "artifacts-fresh-monthly"
    assert not artifact_root.exists() or tuple(artifact_root.iterdir()) == ()


def test_archive_source_owner_thread_and_original_anchor_survive_paging(archive_environment: Any) -> None:
    exact = archive_environment.exact
    original = exact.saved_recipe
    errors: list[BaseException] = []

    def foreign_read() -> None:
        try:
            exact.read_page(1, 8)
        except BaseException as error:
            errors.append(error)

    worker = Thread(target=foreign_read)
    worker.start(); worker.join(timeout=5)
    assert not worker.is_alive() and len(errors) == 1
    assert type(errors[0]) is DailyMarketTechnicalOfficialDispositionRevenueArchivedSourceV3Error
    exact.read_page(1, 8)
    saved = exact.saved_recipe
    assert saved.base_recipe.page_index == 1
    assert saved.base_recipe.monthly_source_reference_external_sha256 == original.base_recipe.monthly_source_reference_external_sha256
    assert saved.archive_artifact_descriptor_external_sha256 == original.archive_artifact_descriptor_external_sha256


@pytest.mark.parametrize("phase", ["open", "reopen"])
def test_archive_source_late_cancel_does_not_retract_committed_token(
    archive_environment: Any, monkeypatch: pytest.MonkeyPatch, phase: str,
) -> None:
    import app_module.daily_market_technical_official_disposition_revenue_archived_source_v3 as module
    env = archive_environment
    cancelled = False

    def callback() -> bool:
        return cancelled

    function_name = ("publish_daily_market_monthly_revenue_archive_reference_artifact_v4"
                     if phase == "open" else "_open_and_publish_v2")
    original = getattr(module, function_name)

    def commit_then_cancel(*args: Any, **kwargs: Any) -> Any:
        nonlocal cancelled
        result = original(*args, **kwargs)
        cancelled = True
        return result

    monkeypatch.setattr(module, function_name, commit_then_cancel)
    if phase == "reopen":
        opened = _reopen(env, env.exact.saved_recipe, artifact_id="late-cancel-fresh", cancel_callback=callback)
    else:
        (env.temp / "late-archive-artifacts").mkdir()
        (env.temp / "late-original-artifacts").mkdir()
        opened = open_daily_market_technical_official_disposition_revenue_archived_bundle_source_v3(
            archive_parent=env.temp / "late-archives", archived_reference_artifact_root=env.temp / "late-archive-artifacts",
            archived_artifact_id="late-archive", bundle_output_root=env.bundle.bundle_root,
            bundle_identity_sha256=env.bundle.reference.bundle_identity_sha256,
            expected_manifest_sha256=env.bundle.reference.manifest_sha256,
            row_scope_filter=_ROW_SCOPES, operation_root=env.temp / "late-original-operation",
            monthly_provider=env.provider, daily_monthly_cohort_reader=env.reader,
            monthly_reference_artifact_root=env.temp / "late-original-artifacts", artifact_id="late-original",
            protected_roots=_PROTECTED_ROOTS, page_size=8, cancel_callback=callback)
    try:
        assert cancelled is True
        assert type(opened) is DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3
        assert not opened.closed and opened.monthly_sqlite_connection_closed
        assert opened.saved_recipe.archive_artifact_descriptor_external_sha256 == opened.artifact_descriptor.external_descriptor_sha256
        assert len(opened.monthly_reference.declared_stock_codes) == 258
    finally:
        opened.close()
