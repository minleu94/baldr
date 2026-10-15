from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)

from app_module.daily_market_monthly_revenue_reference_artifact_v3 import (
    read_daily_market_monthly_revenue_reference_artifact_v3,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2,
)
from app_module.daily_market_technical_official_disposition_revenue_source_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2,
    DailyMarketTechnicalOfficialDispositionRevenueSourceV2Cancelled,
    DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error,
    open_daily_market_technical_official_disposition_revenue_bundle_source_v2,
    reopen_daily_market_technical_official_disposition_revenue_from_recipe_v2,
)
from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
)
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)
from tests.test_selection_fundamental_daily_cohort_v2 import (
    _daily_cohort_environment,
    _source_db_state,
)
from tests.test_daily_market_technical_official_disposition_revenue_query_v2 import _daily_f17_environment


_ROW_SCOPES = ("included_processed", "included_pending", "excluded")
_PROTECTED_ROOTS = (Path("Z:/baldr-synthetic-formal-data"),)


def _open_bundle(
    bundle_fixture: Any,
    *,
    provider: RecommendationCurrentFundamentalProvider,
    reader: DailyMonthlyRevenueCohortReader,
    operation_root: Path,
    artifact_root: Path,
    artifact_id: str,
    **overrides: object,
) -> Any:
    artifact_root.mkdir(parents=True, exist_ok=True)
    options: dict[str, object] = {
        "bundle_output_root": bundle_fixture.bundle_root,
        "bundle_identity_sha256": bundle_fixture.reference.bundle_identity_sha256,
        "expected_manifest_sha256": bundle_fixture.reference.manifest_sha256,
        "row_scope_filter": _ROW_SCOPES,
        "operation_root": operation_root,
        "monthly_provider": provider,
        "daily_monthly_cohort_reader": reader,
        "monthly_reference_artifact_root": artifact_root,
        "artifact_id": artifact_id,
        "protected_roots": _PROTECTED_ROOTS,
        "ma_states": ("unknown",),
        "minimum_yoy_percent": Decimal("0"),
        "condition_combine_mode": "OR",
        "unknown_policy": "include",
        "sort_clauses": (
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2(
                "monthly_revenue_yoy_percent", "desc",
            ),
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2("stock_code", "asc"),
        ),
        "page_index": 0,
        "page_size": 8,
    }
    options.update(overrides)
    return open_daily_market_technical_official_disposition_revenue_bundle_source_v2(**options)


def test_v2_bundle_source_binds_full_f17_scope_daily_pin_and_create_only_artifact(
    bundle_fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.daily_market_technical_official_disposition_bundle_v1 as bundle_module

    provider, reader, pin, _, _ = _daily_f17_environment(tmp_path / "daily-source")
    source_state = _source_db_state(provider.db_file)
    original_read_exact = bundle_module.DailyMarketTechnicalOfficialDispositionBundleReaderV1.read_exact
    exact_reads = 0

    def counted_read_exact(self: Any, *args: object, **kwargs: object) -> Any:
        nonlocal exact_reads
        exact_reads += 1
        return original_read_exact(self, *args, **kwargs)

    monkeypatch.setattr(
        bundle_module.DailyMarketTechnicalOfficialDispositionBundleReaderV1,
        "read_exact",
        counted_read_exact,
    )
    artifact_root = tmp_path / "monthly-reference-artifacts"
    opened = _open_bundle(
        bundle_fixture,
        provider=provider,
        reader=reader,
        operation_root=tmp_path / "operation-one",
        artifact_root=artifact_root,
        artifact_id="first-source",
    )
    try:
        assert exact_reads == 1
        assert opened.f17_query.bundle_identity_sha256 == bundle_fixture.reference.bundle_identity_sha256
        assert opened.f17_query.expected_manifest_sha256 == bundle_fixture.reference.manifest_sha256
        # Declared full-N also retains the one explicitly excluded member.
        assert opened.result.counts.declared_count == bundle_fixture.reference.row_count
        assert sum(count for _, count in opened.result.counts.monthly_source_state_counts) == bundle_fixture.reference.row_count
        assert sum(count for _, count in opened.result.counts.monthly_projected_state_counts) == bundle_fixture.reference.row_count
        assert dict(opened.result.counts.monthly_source_state_counts) == {"blocked": 0, "observed": 1, "unknown": 257}
        assert dict(opened.result.counts.monthly_projected_state_counts) == {"observed": 1, "unknown": 257}
        assert opened.page.rows[0].stock_code == "1000"
        assert opened.page.rows[0].monthly_entry.projected_fact.growth_percent == Decimal("22.006875")
        assert opened.query.monthly_cohort_sha256 == pin.cohort_sha256
        assert opened.monthly_cohort_pin == pin
        assert opened.query.monthly_source_reference_external_sha256 == opened.monthly_reference.external_reference_sha256
        assert opened.query.monthly_source_content_identity_sha256 == opened.monthly_reference.source_content_identity_sha256
        assert opened.query.monthly_availability_status == "cohort_hour_bound"
        assert opened.availability_status == "unknown"
        assert opened.source_scope == "current_only"
        assert opened.official_available_at is None
        assert opened.monthly_official_available_at is None
        assert opened.historical_pit_eligible is False
        assert opened.formal_pit_eligible is False
        assert opened.monthly_sqlite_connection_closed is True
        assert opened.page.request_identity_sha256 == opened.request.request_identity_sha256

        recipe = opened.saved_recipe
        reread_recipe = DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2.from_json(recipe.to_json())
        assert reread_recipe.to_json() == recipe.to_json()
        assert reread_recipe.monthly_cohort_pin_json == pin.to_json()
        assert reread_recipe.monthly_source_reference_external_sha256 == opened.monthly_reference.external_reference_sha256

        descriptor = opened.artifact_descriptor
        artifact_read = read_daily_market_monthly_revenue_reference_artifact_v3(
            artifact_root,
            descriptor=descriptor.to_bytes(),
            expected_descriptor_sha256=descriptor.external_descriptor_sha256,
            protected_roots=_PROTECTED_ROOTS,
        )
        assert artifact_read.source_reference.reference.to_json() == opened.monthly_reference.to_json()
        assert artifact_read.source_reference.external_reference_sha256 == opened.monthly_reference.external_reference_sha256
        assert artifact_read.descriptor.to_json() == descriptor.to_json()
        assert _source_db_state(provider.db_file) == source_state
    finally:
        opened.close()


def test_v2_exact_recipe_reopen_requires_external_anchors_and_reissues_page_and_artifact(
    bundle_fixture: Any,
    tmp_path: Path,
) -> None:
    provider, reader, pin, _, _ = _daily_cohort_environment(tmp_path / "daily-source")
    source_state = _source_db_state(provider.db_file)
    artifact_root = tmp_path / "monthly-reference-artifacts"
    first = _open_bundle(
        bundle_fixture,
        provider=provider,
        reader=reader,
        operation_root=tmp_path / "operation-first",
        artifact_root=artifact_root,
        artifact_id="first-source",
    )
    recipe = first.saved_recipe
    try:
        with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error, match="external"):
            reopen_daily_market_technical_official_disposition_revenue_from_recipe_v2(
                recipe,
                operation_root=tmp_path / "reopen-missing-anchor",
                monthly_provider=provider,
                daily_monthly_cohort_reader=reader,
                monthly_reference_artifact_root=artifact_root,
                artifact_id="reopen-missing-anchor",
                expected_descriptor_sha256="0" * 64,
                expected_monthly_source_reference_sha256="0" * 64,
                protected_roots=_PROTECTED_ROOTS,
            )
        assert not (tmp_path / "reopen-missing-anchor").exists()

        reopened = reopen_daily_market_technical_official_disposition_revenue_from_recipe_v2(
            recipe,
            operation_root=tmp_path / "operation-reopened",
            monthly_provider=provider,
            daily_monthly_cohort_reader=reader,
            monthly_reference_artifact_root=artifact_root,
            artifact_id="reopened-source",
            expected_descriptor_sha256=recipe.artifact_descriptor_external_sha256,
            expected_monthly_source_reference_sha256=recipe.monthly_source_reference_external_sha256,
            protected_roots=_PROTECTED_ROOTS,
        )
        try:
            assert reopened.f17_query.to_json() == first.f17_query.to_json()
            assert reopened.query.ma_query.ma_states == first.query.ma_query.ma_states
            assert reopened.query.minimum_yoy_percent == Decimal("0")
            assert reopened.query.condition_combine_mode == "OR"
            assert reopened.query.unknown_policy == "include"
            assert reopened.query.sort_clauses == first.query.sort_clauses
            assert reopened.request.page_index == first.request.page_index
            assert reopened.request.page_size == first.request.page_size
            assert reopened.monthly_cohort_pin == pin
            assert reopened.query.monthly_cohort_sha256 == pin.cohort_sha256
            assert reopened.monthly_sqlite_connection_closed is True
            assert reopened.source_scope == "current_only"
            assert reopened.availability_status == "unknown"
            assert reopened.historical_pit_eligible is False
            assert reopened.formal_pit_eligible is False
            assert reopened.artifact_descriptor.artifact_id == "reopened-source"
            assert reopened.saved_recipe.monthly_cohort_pin_json == recipe.monthly_cohort_pin_json
            assert _source_db_state(provider.db_file) == source_state
        finally:
            reopened.close()
    finally:
        first.close()


@pytest.mark.parametrize("anchor_kind", ["descriptor", "reference"])
def test_v2_recipe_reopen_rejects_each_wrong_external_anchor_before_operation_root(
    bundle_fixture: Any,
    tmp_path: Path,
    anchor_kind: str,
) -> None:
    provider, reader, _, _, _ = _daily_cohort_environment(tmp_path / "daily-source")
    artifact_root = tmp_path / "monthly-reference-artifacts"
    opened = _open_bundle(
        bundle_fixture,
        provider=provider,
        reader=reader,
        operation_root=tmp_path / "operation-first",
        artifact_root=artifact_root,
        artifact_id="first-source",
    )
    try:
        recipe = opened.saved_recipe
        bad_descriptor_sha = (
            "f" * 64
            if anchor_kind == "descriptor"
            else recipe.artifact_descriptor_external_sha256
        )
        bad_reference_sha = (
            "e" * 64
            if anchor_kind == "reference"
            else recipe.monthly_source_reference_external_sha256
        )
        target = tmp_path / "must-not-open"
        with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error):
            reopen_daily_market_technical_official_disposition_revenue_from_recipe_v2(
                recipe,
                operation_root=target,
                monthly_provider=provider,
                daily_monthly_cohort_reader=reader,
                monthly_reference_artifact_root=artifact_root,
                artifact_id="bad-anchor",
                expected_descriptor_sha256=bad_descriptor_sha,
                expected_monthly_source_reference_sha256=bad_reference_sha,
                protected_roots=_PROTECTED_ROOTS,
            )
        assert not target.exists()
    finally:
        opened.close()


def test_v2_precancel_does_not_open_f17_or_create_operation_or_artifact(
    bundle_fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.daily_market_technical_official_disposition_query_reader_v1 as reader_module

    def forbidden_open(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("pre-cancelled source must not open F17")

    monkeypatch.setattr(reader_module, "open_daily_market_technical_official_disposition_bundle_session_v1", forbidden_open, raising=False)
    provider, reader, _, _, _ = _daily_cohort_environment(tmp_path / "daily-source")
    operation_root = tmp_path / "cancelled-operation"
    artifact_root = tmp_path / "monthly-reference-artifacts"
    artifact_root.mkdir()
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV2Cancelled):
        _open_bundle(
            bundle_fixture,
            provider=provider,
            reader=reader,
            operation_root=operation_root,
            artifact_root=artifact_root,
            artifact_id="cancelled",
            cancel_callback=lambda: True,
        )
    assert not operation_root.exists()
    assert tuple(artifact_root.iterdir()) == ()


def test_v2_cutoff_factory_receives_exact_f17_cutoff_and_clones_only_the_daily_port(
    bundle_fixture: Any,
    tmp_path: Path,
) -> None:
    base_provider, reader, pin, _, _ = _daily_cohort_environment(tmp_path / "daily-source")
    base_provider.daily_source_snapshot_reader = None
    observed_cutoffs: list[object] = []

    def factory(cutoff: object) -> DailyMonthlyRevenueCohortReader:
        observed_cutoffs.append(cutoff)
        return reader

    artifact_root = tmp_path / "monthly-reference-artifacts"
    opened = _open_bundle(
        bundle_fixture,
        provider=base_provider,
        reader=reader,
        operation_root=tmp_path / "operation-factory",
        artifact_root=artifact_root,
        artifact_id="factory-source",
        daily_monthly_cohort_reader=None,
        daily_monthly_cohort_reader_factory=factory,
    )
    try:
        assert observed_cutoffs == [opened.f17_query.decision_cutoff]
        assert opened.monthly_cohort_pin == pin
        assert opened.monthly_cohort_pin.available_hour <= opened.f17_query.decision_cutoff
        assert opened.query.monthly_cohort_sha256 == pin.cohort_sha256
    finally:
        opened.close()


def test_v2_wrong_port_or_future_pin_is_rejected_without_fallback(
    bundle_fixture: Any,
    tmp_path: Path,
) -> None:
    provider, reader, _, _, _ = _daily_cohort_environment(tmp_path / "daily-source")
    wrong_provider, _, _, _, _ = _daily_cohort_environment(tmp_path / "wrong-daily-source")
    artifact_root = tmp_path / "monthly-reference-artifacts"
    artifact_root.mkdir()
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error, match="port_mismatch"):
        _open_bundle(
            bundle_fixture,
            provider=wrong_provider,
            reader=reader,
            operation_root=tmp_path / "wrong-port-operation",
            artifact_root=artifact_root,
            artifact_id="wrong-port",
        )
    assert not (tmp_path / "wrong-port-operation").exists()

    future_pin = cast(
        DailyMonthlyRevenueCohortPin,
        SimpleNamespace(
            available_hour=reader.pin.available_hour.replace(year=2027),
            time_basis_policy="daily-hour.v1",
        ),
    )
    assert future_pin.available_hour > reader.pin.available_hour
    # cohort reader 不可變；這裡單獨驗證來源 preflight 的 future-hour 守衛。
    from app_module.daily_market_technical_official_disposition_revenue_source_v2 import (
        _validate_cutoff_and_pin,
    )
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        open_daily_market_technical_official_disposition_bundle_session_v1,
    )

    f17_session = open_daily_market_technical_official_disposition_bundle_session_v1(
        bundle_output_root=bundle_fixture.bundle_root,
        bundle_identity_sha256=bundle_fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=bundle_fixture.reference.manifest_sha256,
        row_scope_filter=_ROW_SCOPES,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error, match="after_f17_cutoff"):
        _validate_cutoff_and_pin(f17_session.query, future_pin)


def test_v2_cancel_after_first_monthly_batch_closes_reader_without_artifact(
    bundle_fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.daily_market_monthly_revenue_yoy_index_v2 import (
        DailyMarketMonthlyRevenueYoyIndexSessionV2,
    )

    provider, reader, _, _, _ = _daily_cohort_environment(tmp_path / "daily-source")
    source_state = _source_db_state(provider.db_file)
    original_load_batch = DailyMarketMonthlyRevenueYoyIndexSessionV2.load_batch
    original_close = DailyMarketMonthlyRevenueYoyIndexSessionV2.close
    cancelled = False
    batch_count = 0
    closed_sessions: list[bool] = []

    def cancel_after_first_batch(self: Any, stock_codes: object) -> Any:
        nonlocal cancelled, batch_count
        candidate = original_load_batch(self, stock_codes)
        batch_count += 1
        if batch_count == 1:
            cancelled = True
        return candidate

    def tracked_close(self: Any) -> None:
        original_close(self)
        closed_sessions.append(self.closed)

    monkeypatch.setattr(
        DailyMarketMonthlyRevenueYoyIndexSessionV2,
        "load_batch",
        cancel_after_first_batch,
    )
    monkeypatch.setattr(
        DailyMarketMonthlyRevenueYoyIndexSessionV2,
        "close",
        tracked_close,
    )
    artifact_root = tmp_path / "monthly-reference-artifacts"
    artifact_root.mkdir()
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV2Cancelled):
        _open_bundle(
            bundle_fixture,
            provider=provider,
            reader=reader,
            operation_root=tmp_path / "cancel-after-batch-operation",
            artifact_root=artifact_root,
            artifact_id="cancel-after-batch",
            cancel_callback=lambda: cancelled,
        )
    assert batch_count == 1
    assert closed_sessions == [True]
    assert tuple(artifact_root.iterdir()) == ()
    assert _source_db_state(provider.db_file) == source_state


def test_v2_recipe_codec_rejects_v1_schema_and_duplicate_json_keys() -> None:
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error):
        DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2.from_json(
            b'{"schema_version":"daily-market-technical-official-disposition-revenue-saved-recipe.v1"}'
        )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error, match="duplicate"):
        DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2.from_json(
            b'{"schema_version":"daily-market-technical-official-disposition-revenue-saved-recipe.v2","schema_version":"daily-market-technical-official-disposition-revenue-saved-recipe.v2"}'
        )

