from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from threading import Event
from typing import Any, Iterator, cast

import pytest

pytest_plugins = (
    "test_daily_market_technical_official_disposition_bundle_v1",
    "test_daily_market_technical_official_disposition_revenue_query_reader_v1",
)

from app_module.daily_market_monthly_revenue_yoy_index_v1 import (
    DailyMarketMonthlyRevenueYoyIndexSessionV1,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1,
)
from app_module.daily_market_technical_official_disposition_revenue_source_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1,
    DailyMarketTechnicalOfficialDispositionRevenueSourceV1Cancelled,
    DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error,
    open_daily_market_technical_official_disposition_revenue_bundle_source_v1,
    _verify_saved_query_reference,
    open_daily_market_technical_official_disposition_revenue_source_v1,
    reopen_daily_market_technical_official_disposition_revenue_from_recipe_v1,
    reopen_daily_market_technical_official_disposition_revenue_source_v1,
)
from data_module.daily_market_monthly_revenue_read_session_v1 import (
    DailyMarketMonthlyRevenueSourceReferenceV2,
)
from decision_module.factors.selection_fundamental_chip_rules import (
    SELECTION_REVENUE_YOY_METHOD_ID,
    SELECTION_REVENUE_YOY_METHOD_VERSION,
)
import app_module.daily_market_technical_official_disposition_bundle_v1 as bundle_module


def test_bundle_source_entry_uses_one_exact_f17_open_and_preserves_full_scope(
    bundle_fixture: Any,
    monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
        DailyMarketTechnicalOfficialDispositionMaSortClauseV1,
    )
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        DailyMarketTechnicalOfficialDispositionSortClauseV1,
    )
    from app_module.daily_market_technical_parent_v4_query import (
        DailyMarketTechnicalRuleStateFilterV4,
    )

    original_read_exact = cast(
        Any,
        bundle_module.DailyMarketTechnicalOfficialDispositionBundleReaderV1.read_exact,
    )
    exact_reads = 0

    def counted_read_exact(self: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal exact_reads
        exact_reads += 1
        return original_read_exact(self, *args, **kwargs)

    monkeypatch.setattr(
        bundle_module.DailyMarketTechnicalOfficialDispositionBundleReaderV1,
        "read_exact",
        counted_read_exact,
    )
    root = tmp_path / "bundle-entry-operation"
    opened = open_daily_market_technical_official_disposition_revenue_bundle_source_v1(
        bundle_output_root=bundle_fixture.bundle_root,
        bundle_identity_sha256=bundle_fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=bundle_fixture.reference.manifest_sha256,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
        rule_state_filters=(
            DailyMarketTechnicalRuleStateFilterV4.create(
                "ma5_20_golden_cross", ("match", "no_match", "unknown"),
            ),
        ),
        combine_mode="OR",
        outer_stock_filter_mode="explicit_codes",
        outer_stock_codes=("1000", "1001"),
        f17_sort_clauses=(
            DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),
        ),
        monthly_source_reference=monthly_source_reference,
        operation_root=root,
        ma_states=("unknown",),
        minimum_yoy_percent=Decimal("0"),
        condition_combine_mode="OR",
        unknown_policy="include",
        sort_clauses=(
            DailyMarketTechnicalOfficialDispositionMaSortClauseV1(
                "monthly_revenue_yoy_percent", "desc",
            ),
            DailyMarketTechnicalOfficialDispositionMaSortClauseV1("stock_code", "asc"),
        ),
        page_index=0,
        page_size=4,
    )
    try:
        assert exact_reads == 1
        assert opened.f17_query.bundle_output_root == str(bundle_fixture.bundle_root.resolve())
        assert opened.f17_query.bundle_identity_sha256 == bundle_fixture.reference.bundle_identity_sha256
        assert opened.f17_query.expected_manifest_sha256 == bundle_fixture.reference.manifest_sha256
        assert opened.f17_query.row_scope_filter == (
            "included_processed", "included_pending", "excluded",
        )
        assert opened.f17_query.technical_query.rule_state_filters[0].rule_key == "ma5_20_golden_cross"
        assert opened.f17_query.technical_query.combine_mode == "OR"
        assert opened.query.condition_combine_mode == "OR"
        assert opened.query.minimum_yoy_percent == Decimal("0")
        assert opened.query.unknown_policy == "include"
        assert opened.result.counts.declared_count == len(monthly_source_reference.declared_stock_codes)
        assert opened.result.counts.hard_eligible_count == 2
        assert tuple(row.fact_row.stock_code for row in opened.page.rows) == ("1000", "1001")
        assert opened.source_scope == "current_only"
        assert opened.availability_status == "unknown"
        assert opened.historical_pit_eligible is False
        assert opened.monthly_sqlite_connection_closed is True
    finally:
        opened.close()


def test_bundle_source_entry_rejects_precancel_before_open_or_operation_root(
    bundle_fixture: Any,
    monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original_read_exact = cast(
        Any,
        bundle_module.DailyMarketTechnicalOfficialDispositionBundleReaderV1.read_exact,
    )
    reads = 0

    def counted_read_exact(self: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal reads
        reads += 1
        return original_read_exact(self, *args, **kwargs)

    monkeypatch.setattr(
        bundle_module.DailyMarketTechnicalOfficialDispositionBundleReaderV1,
        "read_exact",
        counted_read_exact,
    )
    operation_root = tmp_path / "must-not-be-created"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV1Cancelled):
        open_daily_market_technical_official_disposition_revenue_bundle_source_v1(
            bundle_output_root=bundle_fixture.bundle_root,
            bundle_identity_sha256=bundle_fixture.reference.bundle_identity_sha256,
            expected_manifest_sha256=bundle_fixture.reference.manifest_sha256,
            row_scope_filter=("included_processed",),
            monthly_source_reference=monthly_source_reference,
            operation_root=operation_root,
            cancel_callback=lambda: True,
        )
    assert reads == 0
    assert not operation_root.exists()


def test_saved_query_uses_selection_yoy_method_contract() -> None:
    from types import SimpleNamespace

    source_clock_identity = "a" * 64
    cutoff = "2026-10-07T16:00:00+00:00"
    source_reference = SimpleNamespace(
        snapshot_reference=SimpleNamespace(
            source_clock_identity_sha256=source_clock_identity,
            decision_cutoff=cutoff,
        )
    )
    valid_query = SimpleNamespace(
        monthly_yoy_source_clock_identity_sha256=source_clock_identity,
        monthly_yoy_cutoff=cutoff,
        monthly_yoy_method_id=SELECTION_REVENUE_YOY_METHOD_ID,
        monthly_yoy_method_version=SELECTION_REVENUE_YOY_METHOD_VERSION,
    )

    _verify_saved_query_reference(cast(Any, valid_query), cast(Any, source_reference))

    wrong_method_id = SimpleNamespace(**vars(valid_query))
    wrong_method_id.monthly_yoy_method_id = "current-monthly-revenue-yoy.v1"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error) as wrong_id:
        _verify_saved_query_reference(cast(Any, wrong_method_id), cast(Any, source_reference))
    assert wrong_id.value.code == "saved_query_monthly_source_reference_mismatch"

    wrong_method_version = SimpleNamespace(**vars(valid_query))
    wrong_method_version.monthly_yoy_method_version = "archive-reader.v2"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error) as wrong_version:
        _verify_saved_query_reference(cast(Any, wrong_method_version), cast(Any, source_reference))
    assert wrong_version.value.code == "saved_query_monthly_source_reference_mismatch"


@pytest.fixture(scope="module")
def monthly_source_reference(
    revenue_context: Any,
    tmp_path_factory: pytest.TempPathFactory,
) -> DailyMarketMonthlyRevenueSourceReferenceV2:
    archive_parent = tmp_path_factory.mktemp("f12-monthly-source-archive")
    reference = revenue_context.index_session.archive_source(archive_parent)
    assert type(reference) is DailyMarketMonthlyRevenueSourceReferenceV2
    assert reference.source_scope == "current_observed_only"
    assert reference.availability_status == "unknown"
    assert reference.historical_pit_eligible is False
    assert reference.formal_pit_eligible is False
    return reference


def _make_saved_query(context: Any) -> tuple[Any, Any, Any]:
    from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
        DailyMarketTechnicalOfficialDispositionMaSortClauseV1,
    )

    from tests.test_daily_market_technical_official_disposition_revenue_query_reader_v1 import (
        _ALL_ROW_SCOPES,
    )

    conditioned = context.session.with_conditions(
        row_scope_filter=_ALL_ROW_SCOPES,
        market_assignment_states=("assigned_twse",),
    )
    query = conditioned.create_revenue_query_v1(
        ma_states=("unknown",),
        minimum_yoy_percent=Decimal("0"),
        condition_combine_mode="OR",
        unknown_policy="include",
        sort_clauses=(
            DailyMarketTechnicalOfficialDispositionMaSortClauseV1(
                "monthly_revenue_yoy_percent", "desc"
            ),
            DailyMarketTechnicalOfficialDispositionMaSortClauseV1("stock_code", "asc"),
        ),
    )
    result = conditioned.execute_revenue_query_v1(query)
    request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.create(
        query,
        page_index=0,
        page_size=4,
    )
    return query, result, request


def _inventory(root: Path) -> tuple[tuple[str, int, int, int, str], ...]:
    if not root.is_dir():
        raise AssertionError(f"synthetic source root is missing: {root}")
    values: list[tuple[str, int, int, int, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        info = path.lstat()
        if path.is_symlink() or not path.is_file():
            if path.is_dir() and not path.is_symlink():
                continue
            raise AssertionError(f"unexpected non-regular source entry: {path}")
        raw = path.read_bytes()
        values.append((
            path.relative_to(root).as_posix(),
            info.st_size,
            info.st_mtime_ns,
            info.st_nlink,
            hashlib.sha256(raw).hexdigest(),
        ))
    return tuple(values)


def _collapse_roots(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    ordered = sorted(
        {Path(os.path.abspath(str(path))) for path in paths},
        key=lambda item: (len(item.parts), item.as_posix()),
    )
    roots: list[Path] = []
    for path in ordered:
        if any(path == root or root in path.parents for root in roots):
            continue
        roots.append(path)
    return tuple(roots)


@contextmanager
def _temporarily_detach_historical_roots(
    roots: tuple[Path, ...],
    quarantine_root: Path,
) -> Iterator[tuple[tuple[Path, Path], ...]]:
    quarantine_root.mkdir()
    moved: list[tuple[Path, Path]] = []
    try:
        for index, source in enumerate(_collapse_roots(roots)):
            if not source.is_dir():
                raise AssertionError(f"synthetic historical root is missing: {source}")
            target = quarantine_root / f"detached-{index}"
            source.rename(target)
            moved.append((source, target))
        yield tuple(moved)
    finally:
        for source, target in reversed(moved):
            if target.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                target.rename(source)


def _page_facts(page: Any) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            row.fact_row.stock_code,
            row.fact_row.to_dict(),
            row.monthly_entry.projected_fact.to_dict(),
            row.monthly_entry.source_fact.to_dict(),
            row.technical_condition_truth,
            row.ma_condition_truth,
            row.revenue_condition_truth,
            row.composite_condition_truth,
            row.included_by_unknown_policy,
        )
        for row in page.rows
    )


def _rehash_recipe_body(body: dict[str, object]) -> dict[str, object]:
    body.pop("recipe_identity_sha256", None)
    body["recipe_identity_sha256"] = hashlib.sha256(
        json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return body


def _assert_recipe_rejects_mixed_or_tampered_reference(
    recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1,
    reference: DailyMarketMonthlyRevenueSourceReferenceV2,
) -> None:
    mixed_pin_body = _rehash_recipe_body(recipe.to_dict())
    mixed_pin_body["monthly_source_reference_identity_sha256"] = "a" * 64
    _rehash_recipe_body(mixed_pin_body)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error) as mixed_pin:
        DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1.from_dict(mixed_pin_body)
    assert mixed_pin.value.code == "saved_recipe_monthly_reference_mismatch"

    tampered_reference = reference.to_dict()
    raw_ledger = tampered_reference["fact_identity_by_stock"]
    assert isinstance(raw_ledger, list)
    tampered_ledger = [list(item) for item in cast(list[list[object]], raw_ledger)]
    tampered_ledger[0][1] = "b" * 64
    tampered_reference["fact_identity_by_stock"] = tampered_ledger
    tampered_reference_body = _rehash_recipe_body(recipe.to_dict())
    tampered_reference_body["monthly_source_reference_json"] = json.dumps(
        tampered_reference,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    _rehash_recipe_body(tampered_reference_body)
    with pytest.raises(ValueError):
        DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1.from_dict(
            tampered_reference_body
        )


def test_exact_dual_source_reopen_survives_missing_historical_ancestors(
    revenue_context: Any,
    monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved_query, old_result, saved_request = _make_saved_query(revenue_context)
    old_page = old_result.read_page_request(saved_request)
    f17_query = saved_query.ma_query.f17_query

    snapshot_root = Path(monthly_source_reference.snapshot_reference.snapshot_root)
    raw_archive_root = Path(monthly_source_reference.raw_archive_reference.raw_archive_root)
    raw_origin_root = Path(
        monthly_source_reference.raw_archive_reference.original_monthly_source_root
    )
    original_database = Path(revenue_context.index_session.index.source_clock.database_path)
    original_database_root = original_database.parent
    f17_root = Path(f17_query.bundle_output_root)
    protected_roots = (f17_root, snapshot_root, raw_archive_root, raw_origin_root)
    before = {path: _inventory(path) for path in protected_roots}
    original_database_sha = hashlib.sha256(original_database.read_bytes()).hexdigest()

    opened_sqlite_uris: list[str] = []
    opened_connections: list[sqlite3.Connection] = []
    original_connect = sqlite3.connect

    def tracked_connect(
        database: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *args: Any,
        **kwargs: Any,
    ) -> sqlite3.Connection:
        uri_text = str(database)
        opened_sqlite_uris.append(uri_text)
        connection = original_connect(database, *args, **kwargs)
        opened_connections.append(connection)
        return connection

    monkeypatch.setattr("data_module.fundamental_read_snapshot.sqlite3.connect", tracked_connect)
    initial_operation_root = tmp_path / "initial-exact-open"
    initial_exact = open_daily_market_technical_official_disposition_revenue_source_v1(
        f17_query,
        monthly_source_reference,
        operation_root=initial_operation_root,
        ma_states=saved_query.ma_query.ma_states,
        minimum_yoy_percent=saved_query.minimum_yoy_percent,
        condition_combine_mode=saved_query.condition_combine_mode,
        unknown_policy=saved_query.unknown_policy,
        sort_clauses=saved_query.sort_clauses,
        page_index=saved_request.page_index,
        page_size=saved_request.page_size,
    )
    try:
        recipe = initial_exact.saved_recipe
        recipe_json = recipe.to_json()
        _assert_recipe_rejects_mixed_or_tampered_reference(
            recipe,
            monthly_source_reference,
        )
        initial_reader_path = initial_exact.monthly_reader_database_path
        initial_operation_clock = initial_exact.monthly_operation_clock_identity_sha256
        assert initial_exact.query.monthly_yoy_source_clock_identity_sha256 == initial_operation_clock
        assert recipe.monthly_source_clock_identity_sha256 == monthly_source_reference.snapshot_reference.source_clock_identity_sha256
        assert initial_operation_clock != recipe.monthly_source_clock_identity_sha256
        assert _page_facts(initial_exact.page) == _page_facts(old_page)
        assert initial_exact.monthly_sqlite_connection_closed is True
    finally:
        initial_exact.close()

    initial_expected_uri = f"{initial_reader_path.as_uri()}?mode=ro"
    assert initial_reader_path.is_relative_to(initial_operation_root)
    assert all(_is_closed_connection(connection) for connection in opened_connections)

    move_roots = (original_database_root, raw_origin_root)
    with _temporarily_detach_historical_roots(move_roots, tmp_path / "history-quarantine") as moved:
        assert moved
        assert not original_database.exists()
        assert not raw_origin_root.exists()
        operation_root = tmp_path / "dual-source-operation"
        reopened = reopen_daily_market_technical_official_disposition_revenue_from_recipe_v1(
            recipe_json,
            operation_root=operation_root,
        )
        try:
            assert reopened.f17_query.to_json() == f17_query.to_json()
            assert reopened.monthly_source_reference.to_json() == monthly_source_reference.to_json()
            assert reopened.query.ma_query.f17_query.to_json() == f17_query.to_json()
            assert reopened.query.query_identity_sha256 != saved_query.query_identity_sha256
            assert (
                reopened.monthly_source_clock_identity_sha256
                == monthly_source_reference.snapshot_reference.source_clock_identity_sha256
            )
            assert (
                reopened.query.monthly_yoy_source_clock_identity_sha256
                == reopened.monthly_operation_clock_identity_sha256
            )
            assert (
                reopened.monthly_operation_clock_identity_sha256
                != reopened.monthly_source_clock_identity_sha256
            )
            assert (
                reopened.query.monthly_yoy_read_session_identity_sha256
                != saved_query.monthly_yoy_read_session_identity_sha256
            )
            assert (
                reopened.query.monthly_yoy_index_identity_sha256
                != saved_query.monthly_yoy_index_identity_sha256
            )
            assert reopened.result.operation_identity_sha256 != old_result.operation_identity_sha256
            assert reopened.result.counts.to_dict() == old_result.counts.to_dict()
            assert reopened.page_request.page_index == saved_request.page_index
            assert reopened.page_request.page_size == saved_request.page_size
            assert (
                reopened.page_request.query.query_identity_sha256
                == reopened.query.query_identity_sha256
            )
            assert (
                reopened.page_request.request_identity_sha256
                != saved_request.request_identity_sha256
            )
            assert _page_facts(reopened.page) == _page_facts(old_page)
            assert reopened.source_scope == "current_only"
            assert reopened.availability_status == "unknown"
            assert reopened.official_available_at is None
            assert reopened.monthly_official_available_at is None
            assert reopened.historical_pit_eligible is False
            assert reopened.monthly_sqlite_connection_closed is True

            monthly_reader_path = reopened.monthly_reader_database_path
            assert monthly_reader_path.is_relative_to(operation_root)
            assert monthly_reader_path != original_database
            assert not (operation_root / "neutral_provider_guard" / "never-open-this.sqlite").exists()
            expected_uri = f"{monthly_reader_path.as_uri()}?mode=ro"
            assert opened_sqlite_uris
            assert opened_sqlite_uris == [initial_expected_uri, expected_uri]
            assert all(
                _is_closed_connection(connection)
                for connection in opened_connections
            )

            recipe_from_first_reopen = reopened.saved_recipe
            assert recipe_from_first_reopen.to_json() == recipe_json
            decoded_recipe = DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1.from_json(
                recipe_json
            )
            assert decoded_recipe.to_json() == recipe_json
            assert decoded_recipe.recipe_identity_sha256 == recipe.recipe_identity_sha256
            changed_recipe = decoded_recipe.with_conditions(
                ma_states=decoded_recipe.ma_states,
                minimum_yoy_percent=Decimal("1"),
                condition_combine_mode=decoded_recipe.condition_combine_mode,
                unknown_policy=decoded_recipe.unknown_policy,
                sort_clauses=decoded_recipe.sort_clauses,
            )
            assert changed_recipe.recipe_identity_sha256 != recipe.recipe_identity_sha256
            assert (
                changed_recipe.monthly_source_reference_identity_sha256
                == recipe.monthly_source_reference_identity_sha256
            )

            next_page = reopened.read_page(1, 4)
            expected_next_page = old_result.read_page(1, 4)
            assert _page_facts(next_page) == _page_facts(expected_next_page)
            assert reopened.monthly_sqlite_connection_closed is True

            page_one_recipe = reopened.saved_recipe
            assert page_one_recipe.page_index == 1
            assert page_one_recipe.page_size == recipe.page_size
            assert page_one_recipe.recipe_identity_sha256 != recipe.recipe_identity_sha256
            assert (
                page_one_recipe.monthly_source_reference_identity_sha256
                == recipe.monthly_source_reference_identity_sha256
            )
            assert page_one_recipe.f17_query_json == recipe.f17_query_json
            assert page_one_recipe.ma_states == recipe.ma_states
            assert page_one_recipe.minimum_yoy_percent == recipe.minimum_yoy_percent
            assert page_one_recipe.condition_combine_mode == recipe.condition_combine_mode
            assert page_one_recipe.unknown_policy == recipe.unknown_policy
            assert page_one_recipe.sort_clauses == recipe.sort_clauses

            reopened_again_root = tmp_path / "recipe-reopen-operation"
            reopened_again = reopen_daily_market_technical_official_disposition_revenue_from_recipe_v1(
                page_one_recipe.to_json(),
                operation_root=reopened_again_root,
            )
            try:
                assert reopened_again.saved_recipe.to_json() == page_one_recipe.to_json()
                assert reopened_again.query.query_identity_sha256 != reopened.query.query_identity_sha256
                assert reopened_again.result.operation_identity_sha256 != reopened.result.operation_identity_sha256
                assert reopened_again.result.counts.to_dict() == reopened.result.counts.to_dict()
                assert _page_facts(reopened_again.page) == _page_facts(next_page)
                assert reopened_again.page_request.page_index == page_one_recipe.page_index
                assert reopened_again.page_request.page_size == page_one_recipe.page_size
                assert reopened_again.page_request.request_identity_sha256 != reopened.page_request.request_identity_sha256
                assert reopened_again.monthly_source_clock_identity_sha256 == recipe.monthly_source_clock_identity_sha256
                assert reopened_again.monthly_operation_clock_identity_sha256 != recipe.monthly_source_clock_identity_sha256
                assert reopened_again.source_scope == "current_only"
                assert reopened_again.availability_status == "unknown"
                assert reopened_again.monthly_official_available_at is None
                assert reopened_again.historical_pit_eligible is False
                assert reopened_again.monthly_sqlite_connection_closed is True
                second_reader_path = reopened_again.monthly_reader_database_path
                assert second_reader_path.is_relative_to(reopened_again_root)
                assert second_reader_path != monthly_reader_path
                assert opened_sqlite_uris == [
                    initial_expected_uri,
                    expected_uri,
                    f"{second_reader_path.as_uri()}?mode=ro",
                ]
                assert all(_is_closed_connection(connection) for connection in opened_connections)
            finally:
                reopened_again.close()
            assert reopened_again.closed is True
        finally:
            reopened.close()
        assert reopened.closed is True
        assert reopened.monthly_sqlite_connection_closed is True
        with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error) as closed:
            reopened.read_page(0, 4)
        assert closed.value.code == "source_operation_closed"

    assert hashlib.sha256(original_database.read_bytes()).hexdigest() == original_database_sha
    assert {path: _inventory(path) for path in protected_roots} == before


def _is_closed_connection(connection: sqlite3.Connection) -> bool:
    try:
        connection.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


def test_cancel_and_cutoff_mismatch_fail_before_operation_root_or_reader(
    revenue_context: Any,
    monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved_query, _result, _request = _make_saved_query(revenue_context)
    f17_query = saved_query.ma_query.f17_query

    cancelled_root = tmp_path / "cancelled-before-open"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV1Cancelled):
        open_daily_market_technical_official_disposition_revenue_source_v1(
            f17_query,
            monthly_source_reference,
            operation_root=cancelled_root,
            cancel_callback=lambda: True,
        )
    assert not cancelled_root.exists()

    from app_module.daily_market_technical_official_disposition_query_v1 import (
        DailyMarketTechnicalOfficialDispositionQueryV1,
    )

    mismatched_f17_query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=f17_query.technical_query,
        decision_cutoff=f17_query.decision_cutoff + timedelta(seconds=1),
        bundle_output_root=f17_query.bundle_output_root,
        bundle_identity_sha256=f17_query.bundle_identity_sha256,
        expected_manifest_sha256=f17_query.expected_manifest_sha256,
        market_assignment_pin_identity_sha256=f17_query.market_assignment_pin_identity_sha256,
        official_disposal_pin_identity_sha256=f17_query.official_disposal_pin_identity_sha256,
        row_scope_filter=f17_query.row_scope_filter,
        market_assignment_states=f17_query.market_assignment_states,
        official_disposal_states=f17_query.official_disposal_states,
        outer_stock_filter_mode=f17_query.outer_stock_filter_mode,
        outer_stock_codes=f17_query.outer_stock_codes,
        sort_clauses=f17_query.sort_clauses,
    )
    mismatch_root = tmp_path / "cutoff-mismatch"
    opened = False

    def reject_reader(*_args: object, **_kwargs: object) -> object:
        nonlocal opened
        opened = True
        raise AssertionError("cutoff mismatch must fail before either source opens")

    import app_module.daily_market_technical_official_disposition_query_reader_v1 as f17_reader

    monkeypatch.setattr(
        f17_reader,
        "open_daily_market_technical_official_disposition_read_session_v1",
        reject_reader,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error) as mismatch:
        open_daily_market_technical_official_disposition_revenue_source_v1(
            mismatched_f17_query,
            monthly_source_reference,
            operation_root=mismatch_root,
        )
    assert mismatch.value.code == "source_cutoff_mismatch"
    assert opened is False
    assert not mismatch_root.exists()

    legacy_operation_root = tmp_path / "legacy-operation-query-clock"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error) as legacy_query:
        reopen_daily_market_technical_official_disposition_revenue_source_v1(
            saved_query,
            monthly_source_reference,
            operation_root=legacy_operation_root,
            saved_page_request=_request,
        )
    assert legacy_query.value.code == "saved_query_monthly_source_reference_mismatch"
    assert not legacy_operation_root.exists()

    from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
        DailyMarketTechnicalOfficialDispositionRevenueQueryV1,
        _sha256_json,
    )

    mismatched_query_body = saved_query.to_dict()
    mismatched_query_body.pop("query_identity_sha256")
    mismatched_query_body["monthly_yoy_source_clock_identity_sha256"] = "f" * 64
    mismatched_query = DailyMarketTechnicalOfficialDispositionRevenueQueryV1.from_dict({
        **mismatched_query_body,
        "query_identity_sha256": _sha256_json(mismatched_query_body),
    })
    mismatched_request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.create(
        mismatched_query,
        page_index=0,
        page_size=4,
    )
    source_pin_mismatch_root = tmp_path / "source-clock-pin-mismatch"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error) as pin_mismatch:
        reopen_daily_market_technical_official_disposition_revenue_source_v1(
            mismatched_query,
            monthly_source_reference,
            operation_root=source_pin_mismatch_root,
            saved_page_request=mismatched_request,
        )
    assert pin_mismatch.value.code == "saved_query_monthly_source_reference_mismatch"
    assert opened is False
    assert not source_pin_mismatch_root.exists()

def test_cancel_after_monthly_batch_closes_operation_reader_without_publishing(
    revenue_context: Any,
    monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved_query, _result, _request = _make_saved_query(revenue_context)
    f17_query = saved_query.ma_query.f17_query
    cancel_event = Event()
    batch_calls = 0
    closed_sessions: list[DailyMarketMonthlyRevenueYoyIndexSessionV1] = []
    original_load = DailyMarketMonthlyRevenueYoyIndexSessionV1.load_batch
    original_close = DailyMarketMonthlyRevenueYoyIndexSessionV1.close

    def load_and_cancel_after_first_batch(
        session: DailyMarketMonthlyRevenueYoyIndexSessionV1,
        stock_codes: object,
        *,
        cancel_callback: object = None,
    ) -> object:
        nonlocal batch_calls
        result = original_load(
            session,
            stock_codes,  # type: ignore[arg-type]
            cancel_callback=cancel_callback,  # type: ignore[arg-type]
        )
        batch_calls += 1
        if batch_calls == 1:
            cancel_event.set()
        return result

    def close_and_record(session: DailyMarketMonthlyRevenueYoyIndexSessionV1) -> None:
        original_close(session)
        closed_sessions.append(session)

    monkeypatch.setattr(
        DailyMarketMonthlyRevenueYoyIndexSessionV1,
        "load_batch",
        load_and_cancel_after_first_batch,
    )
    monkeypatch.setattr(DailyMarketMonthlyRevenueYoyIndexSessionV1, "close", close_and_record)

    operation_root = tmp_path / "cancel-after-first-monthly-batch"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueSourceV1Cancelled):
        open_daily_market_technical_official_disposition_revenue_source_v1(
            f17_query,
            monthly_source_reference,
            operation_root=operation_root,
            ma_states=("unknown",),
            minimum_yoy_percent=Decimal("0"),
            condition_combine_mode="OR",
            unknown_policy="include",
            cancel_callback=cancel_event.is_set,
        )
    assert batch_calls == 1
    assert len(closed_sessions) == 1
    assert closed_sessions[0].closed is True
    assert closed_sessions[0].finished is False
    assert (operation_root / "monthly_snapshot_operations").exists()
