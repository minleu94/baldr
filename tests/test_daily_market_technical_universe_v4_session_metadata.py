"""驗證同次 exact session 的不可變來源摘要重用契約。"""

from __future__ import annotations

from dataclasses import replace as dataclass_replace
import os
from pathlib import Path
from typing import Any

import pytest

pytest_plugins = ("tests.test_daily_market_technical_universe_v4_read_session",)

from app_module import daily_market_technical_universe_v4_query as query_module
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4QueryError,
    DailyMarketTechnicalUniverseV4ReadSession,
    open_daily_market_technical_universe_v4_read_session,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4Plan,
    DailyMarketTechnicalUniverseV4Receipt,
)


def _open_session(fixture: dict[str, Any]) -> DailyMarketTechnicalUniverseV4ReadSession:
    plan = fixture["plan"]
    receipt = fixture["complete"]
    return open_daily_market_technical_universe_v4_read_session(
        store_output_root=fixture["store_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=receipt.identity_sha256,
        receipt_sha256=receipt.content_sha256,
    )


def test_exact_session_reuses_metadata_without_changing_query_or_pages(
    synthetic_read_session_source: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(synthetic_read_session_source)
    metadata = session._source_metadata
    assert metadata is not None
    assert metadata.matches_session(session)

    expected = query_module._query_from_verified_state(
        root=session._root,
        state=session._state,
        plan_sha256=session._plan_sha256,
        receipt_sha256=session._receipt_sha256,
        rule_state_filters=(),
        combine_mode="AND",
        stock_filter=(),
        sort_key="stock_code",
        descending=False,
        page_index=0,
        page_size=4,
    )
    query = session.create_query(sort_key="stock_code", page_size=4)
    assert query.to_dict() == expected.to_dict()

    def unexpected_plan_decode(_self: Any) -> Any:
        raise AssertionError("同一 reader-issued session 不應重建已核 plan/cohort metadata")

    def unexpected_receipt_decode(_self: Any) -> Any:
        raise AssertionError("同一 reader-issued session 不應重建已核 receipt metadata")

    monkeypatch.setattr(DailyMarketTechnicalUniverseV4Plan, "to_dict", unexpected_plan_decode)
    monkeypatch.setattr(DailyMarketTechnicalUniverseV4Receipt, "to_dict", unexpected_receipt_decode)

    assert session.matches_source(query)
    first_page = session.read_page(query)
    selection = session.select_stock_codes(query)
    second_page = session.read_selection_page(selection, page_index=1, page_size=4)
    assert tuple(row.stock_code for row in first_page.rows) == (
        "S0000", "S0001", "S0002", "S0003"
    )
    assert tuple(row.stock_code for row in second_page.rows) == (
        "S0004", "S0005", "S0006", "S0007"
    )
    assert session._source_metadata is metadata
    assert metadata.matches_session(session)


def test_replaced_session_does_not_copy_metadata_summary(
    synthetic_read_session_source: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(synthetic_read_session_source)
    query = session.create_query()
    clone = dataclass_replace(session)
    assert clone._source_metadata is None
    assert clone._source_metadata_token is None

    original = DailyMarketTechnicalUniverseV4Plan.to_dict
    calls = 0

    def counted(self: DailyMarketTechnicalUniverseV4Plan) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return original(self)

    monkeypatch.setattr(DailyMarketTechnicalUniverseV4Plan, "to_dict", counted)
    assert clone.matches_source(query)
    assert calls > 0


@pytest.mark.parametrize(
    "tamper",
    (
        "state_owner",
        "plan_body",
        "receipt_body",
        "root",
        "plan_pin",
        "receipt_pin",
        "session_identity",
        "candidate_tuple",
        "artifact_reference_tuple",
        "unknown_codes_tuple",
        "index_bytes",
        "token",
    ),
)
def test_changed_owner_body_or_pins_do_not_use_summary_fast_path(
    synthetic_read_session_source: dict[str, Any],
    tamper: str,
) -> None:
    session = _open_session(synthetic_read_session_source)
    original_state = session._state
    original_root = session._root
    original_plan_sha = session._plan_sha256
    original_receipt_sha = session._receipt_sha256
    original_session_identity = session.read_session_identity_sha256
    original_candidates = session._candidates
    original_artifact_references = session._artifact_references
    original_unknown_codes = session._unknown_rule_stock_codes
    original_index_bytes = session.index_bytes
    original_token = session._source_metadata_token
    original_plan = original_state.plan
    original_receipt = original_state.receipt
    try:
        if tamper == "state_owner":
            object.__setattr__(session, "_state", dataclass_replace(original_state))
        elif tamper == "plan_body":
            object.__setattr__(
                original_state,
                "plan",
                dataclass_replace(original_plan, body_json=original_plan.body_json + " "),
            )
        elif tamper == "receipt_body":
            object.__setattr__(
                original_state,
                "receipt",
                dataclass_replace(original_receipt, body_json=original_receipt.body_json + " "),
            )
        elif tamper == "root":
            object.__setattr__(session, "_root", Path(str(original_root) + "-foreign"))
        elif tamper == "plan_pin":
            object.__setattr__(session, "_plan_sha256", "f" * 64)
        elif tamper == "receipt_pin":
            object.__setattr__(session, "_receipt_sha256", "f" * 64)
        elif tamper == "candidate_tuple":
            object.__setattr__(session, "_candidates", original_candidates[:-1])
        elif tamper == "artifact_reference_tuple":
            object.__setattr__(session, "_artifact_references", ())
        elif tamper == "unknown_codes_tuple":
            object.__setattr__(session, "_unknown_rule_stock_codes", ())
        elif tamper == "index_bytes":
            object.__setattr__(session, "index_bytes", original_index_bytes + 1)
        elif tamper == "token":
            object.__setattr__(session, "_source_metadata_token", object())
        else:
            object.__setattr__(session, "read_session_identity_sha256", "f" * 64)

        with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as rejected:
            session.create_query()
        assert rejected.value.code == "technical_universe_v4_read_session_metadata_binding_mismatch"
    finally:
        object.__setattr__(session, "_state", original_state)
        object.__setattr__(session, "_root", original_root)
        object.__setattr__(session, "_plan_sha256", original_plan_sha)
        object.__setattr__(session, "_receipt_sha256", original_receipt_sha)
        object.__setattr__(session, "read_session_identity_sha256", original_session_identity)
        object.__setattr__(session, "_candidates", original_candidates)
        object.__setattr__(session, "_artifact_references", original_artifact_references)
        object.__setattr__(session, "_unknown_rule_stock_codes", original_unknown_codes)
        object.__setattr__(session, "index_bytes", original_index_bytes)
        object.__setattr__(session, "_source_metadata_token", original_token)
        object.__setattr__(original_state, "plan", original_plan)
        object.__setattr__(original_state, "receipt", original_receipt)


def test_foreign_query_and_precancel_do_not_pollute_session_summary(
    synthetic_read_session_source: dict[str, Any],
) -> None:
    session = _open_session(synthetic_read_session_source)
    query = session.create_query(page_size=4)
    summary = session._source_metadata
    assert summary is not None

    payload = query.to_dict()
    payload["store_output_root"] = str(
        synthetic_read_session_source["empty"]["store_root"]
    )
    payload["query_identity_sha256"] = query_module._sha256_json(
        {key: value for key, value in payload.items() if key != "query_identity_sha256"}
    )
    foreign = DailyMarketTechnicalUniverseV4Query.from_dict(payload)
    assert not session.matches_source(foreign)
    assert session._source_metadata is summary


def test_fast_summary_and_replaced_session_strict_path_are_identical_for_queries_and_pages(
    synthetic_read_session_source: dict[str, Any],
) -> None:
    fast_session = _open_session(synthetic_read_session_source)
    strict_session = dataclass_replace(fast_session)
    assert strict_session._source_metadata is None
    assert strict_session._source_metadata_token is None

    filters = (
        DailyMarketTechnicalRuleStateFilterV4.create(
            "volume_ratio_20_including_current", ("match", "unknown")
        ),
        DailyMarketTechnicalRuleStateFilterV4.create(
            "ma5_20_golden_cross", ("match",)
        ),
    )
    conditions = (
        {
            "rule_state_filters": filters,
            "combine_mode": "AND",
            "sort_key": "volume_ratio_20_including_current.ratio",
            "descending": True,
            "page_index": 0,
            "page_size": 4,
        },
        {
            "rule_state_filters": filters,
            "combine_mode": "OR",
            "stock_filter": ("S0001", "S0002", "S0016"),
            "sort_key": "latest_feature_date",
            "descending": True,
            "page_index": 1,
            "page_size": 2,
        },
    )

    for condition in conditions:
        fast_query = fast_session.create_query(**condition)
        strict_query = strict_session.create_query(**condition)
        assert fast_query.to_dict() == strict_query.to_dict()
        assert fast_session.read_page(fast_query).to_dict() == strict_session.read_page(
            strict_query
        ).to_dict()

        fast_selection = fast_session.select_stock_codes(fast_query)
        strict_selection = strict_session.select_stock_codes(strict_query)
        assert fast_selection == strict_selection
        assert fast_selection.selection_identity_sha256 == strict_selection.selection_identity_sha256
        assert fast_selection.query_spec_identity_sha256 == strict_selection.query_spec_identity_sha256
        assert fast_selection.stock_codes == strict_selection.stock_codes

        for page_index in (0, 1):
            fast_selection_page = fast_session.read_selection_page(
                fast_selection, page_index=page_index, page_size=2
            )
            strict_selection_page = strict_session.read_selection_page(
                strict_selection, page_index=page_index, page_size=2
            )
            assert (
                fast_selection_page.selection_identity_sha256,
                fast_selection_page.page_index,
                fast_selection_page.page_size,
                fast_selection_page.matching_count,
                fast_selection_page.page_count,
                None if fast_selection_page.page is None else fast_selection_page.page.to_dict(),
            ) == (
                strict_selection_page.selection_identity_sha256,
                strict_selection_page.page_index,
                strict_selection_page.page_size,
                strict_selection_page.matching_count,
                strict_selection_page.page_count,
                None if strict_selection_page.page is None else strict_selection_page.page.to_dict(),
            )


def test_cached_metadata_does_not_skip_fresh_selected_artifact_hash(
    synthetic_read_session_source: dict[str, Any],
) -> None:
    session = _open_session(synthetic_read_session_source)
    query = session.create_query(sort_key="stock_code", page_size=4)
    original_page = session.read_page(query)
    assert original_page.rows
    summary = session._source_metadata
    assert summary is not None and summary.matches_session(session)

    reference = next(
        item for item in session._artifact_references if item.semantic_proof is not None
    )
    assert reference.semantic_proof is not None
    manifest = reference.semantic_proof.manifest
    selected_codes = {row.stock_code for row in original_page.rows}
    selected_ref = next(
        item for item in manifest.artifact_refs if item.stock_code in selected_codes
    )
    selected_path = manifest.manifest_path.parent.joinpath(
        *selected_ref.relative_path.split("/")
    )
    internal_path = to_internal_io_path(selected_path)
    with open(internal_path, "rb") as reader:
        original_bytes = reader.read()
    original_stat = os.stat(internal_path)
    assert original_bytes

    try:
        with open(internal_path, "wb") as writer:
            writer.write(bytes((original_bytes[0] ^ 1,)) + original_bytes[1:])
        os.utime(
            internal_path,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
        with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as tampered:
            session.read_page(query)
        assert tampered.value.code == "technical_snapshot_v4_artifact_sha_mismatch"
        assert session._source_metadata is summary
    finally:
        with open(internal_path, "wb") as writer:
            writer.write(original_bytes)
        os.utime(
            internal_path,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )

    assert session.read_page(query).to_dict() == original_page.to_dict()
    assert session._source_metadata is summary


def test_cancel_after_proof_based_child_read_returns_no_partial_page(
    synthetic_read_session_source: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(synthetic_read_session_source)
    query = session.create_query(sort_key="stock_code", page_size=4)
    selection = session.select_stock_codes(query)
    summary = session._source_metadata
    assert summary is not None
    original_read = query_module._read_session_child_snapshots
    child_read_completed = False
    child_reads = 0

    def cancel_after_child_read(
        reference: Any,
        *,
        selected_stock_codes: Any,
        cancel_callback: Any,
    ) -> Any:
        nonlocal child_read_completed, child_reads
        snapshots = original_read(
            reference,
            selected_stock_codes=selected_stock_codes,
            cancel_callback=cancel_callback,
        )
        child_reads += 1
        child_read_completed = True
        return snapshots

    monkeypatch.setattr(
        query_module, "_read_session_child_snapshots", cancel_after_child_read
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as interrupted:
        session.read_selection_page(
            selection,
            page_index=0,
            page_size=4,
            cancel_callback=lambda: child_read_completed,
        )
    assert interrupted.value.code == "technical_universe_v4_query_cancelled"
    assert child_reads == 1
    assert session._source_metadata is summary

    monkeypatch.setattr(query_module, "_read_session_child_snapshots", original_read)
    page = session.read_selection_page(selection, page_index=0, page_size=4)
    assert page.page is not None
    assert tuple(row.stock_code for row in page.rows) == (
        "S0000", "S0001", "S0002", "S0003"
    )
    assert session._source_metadata is summary

    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as cancelled:
        session.read_page(query, cancel_callback=lambda: True)
    assert cancelled.value.code == "technical_universe_v4_query_cancelled"
    assert session._source_metadata is summary

    page = session.read_page(query)
    assert tuple(row.stock_code for row in page.rows) == (
        "S0000", "S0001", "S0002", "S0003"
    )
    assert session._source_metadata is summary
