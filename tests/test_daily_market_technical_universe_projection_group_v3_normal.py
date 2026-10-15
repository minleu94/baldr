"""正常 bundle V3 入口沿用原257股／双parent consumer原斷言。"""
from __future__ import annotations

from typing import Any
import pytest
import test_daily_market_technical_universe_projection_group_v3 as original
import app_module.daily_market_technical_official_disposition_query_reader_v1 as reader

pytest_plugins = ("test_daily_market_technical_official_disposition_composite_reader_v1",)


def _route_original_assertions_to_normal_bundle_opener(monkeypatch: pytest.MonkeyPatch) -> None:
    """原三案例共用同一組嚴格斷言，本組只更換公開入口與參數形式。"""
    def open_normal(query: Any, *, cancel_callback: Any = None) -> Any:
        return reader.open_daily_market_technical_official_disposition_bundle_projection_group_session_v3(
            bundle_output_root=query.bundle_output_root,
            bundle_identity_sha256=query.bundle_identity_sha256,
            expected_manifest_sha256=query.expected_manifest_sha256,
            row_scope_filter=query.row_scope_filter,
            rule_state_filters=query.technical_query.rule_state_filters,
            combine_mode=query.technical_query.combine_mode,
            market_assignment_states=query.market_assignment_states,
            official_disposal_states=query.official_disposal_states,
            outer_stock_filter_mode=query.outer_stock_filter_mode,
            outer_stock_codes=query.outer_stock_codes,
            sort_clauses=query.sort_clauses,
            cancel_callback=cancel_callback,
        )
    monkeypatch.setattr(reader,
        "open_daily_market_technical_official_disposition_projection_group_session_v3", open_normal)


def test_normal_bundle_v3_opener_same_four_members_and_two_parent_callbacks(
    monkeypatch: pytest.MonkeyPatch, bundle_fixture: Any, exact_query: Any,
) -> None:
    assert len(bundle_fixture.included_codes) == 257
    _route_original_assertions_to_normal_bundle_opener(monkeypatch)
    original.test_v3_exact_opener_builds_four_members_from_one_real_two_parent_read(
        monkeypatch, bundle_fixture, exact_query)


def test_normal_bundle_v3_mismatch_poison_has_no_issued_session(
    monkeypatch: pytest.MonkeyPatch, exact_query: Any,
) -> None:
    _route_original_assertions_to_normal_bundle_opener(monkeypatch)
    original.test_v3_mismatched_fact_is_poisoned_before_any_session_is_issued(monkeypatch, exact_query)


def test_normal_bundle_v3_cancel_clears_partial_four_members(
    monkeypatch: pytest.MonkeyPatch, exact_query: Any,
) -> None:
    _route_original_assertions_to_normal_bundle_opener(monkeypatch)
    original.test_v3_cancel_after_first_fact_clears_all_partial_members_and_does_not_issue(monkeypatch, exact_query)
