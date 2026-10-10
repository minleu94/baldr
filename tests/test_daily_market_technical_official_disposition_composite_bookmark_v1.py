"""複合收藏的真來源、新程序與拒絕還原契約測試。"""

from __future__ import annotations

import json
import hashlib
import os
from collections.abc import Callable
from pathlib import Path
import subprocess
import sys

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TESTS_ROOT = _REPO_ROOT / "tests"
if str(_TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TESTS_ROOT))
_CANDIDATE_ROOT = Path(__file__).resolve().parent
if str(_CANDIDATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CANDIDATE_ROOT))

pytest_plugins = (
    "test_daily_market_technical_official_disposition_composite_reader_v1",
)

from app_module.daily_market_technical_official_disposition_composite_query_v1 import (
    DailyMarketTechnicalOfficialDispositionCompositePageRequestV1,
    DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
    DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionReadSessionV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
)
import app_module.daily_market_technical_official_disposition_composite_bookmark_v1 as bookmark_module
import app_module.daily_market_technical_official_disposition_composite_query_v1 as composite_module
from test_daily_market_technical_official_disposition_composite_reader_v1 import (
    _FullOwner,
    _BundleFixture,
    bundle_fixture,
)


def _bookmark_from_full257(
    owner: _FullOwner,
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1:
    assert result._read_session is owner.session
    assert result._projection_group_session is owner.group
    first = result.read_page(0, 8)
    comparison = result.read_page(1, 8)
    return bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1.create_from_real_row_context(
        result,
        first,
        first.rows[0].stock_code,
        scroll_position=23,
        comparison_contexts=((comparison, comparison.rows[1].stock_code),),
    )


def test_exact_bookmark_reopens_in_fresh_process_and_preserves_every_identity(
    full257_no_match_owner: _FullOwner,
    full257_or_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    tmp_path: Path,
) -> None:
    owner = full257_no_match_owner
    result = full257_or_result
    bookmark = _bookmark_from_full257(owner, result)
    raw_path = tmp_path / "composite-bookmark.json"
    raw_path.write_bytes(bookmark.to_json().encode("utf-8"))

    candidate_dir = _CANDIDATE_ROOT
    child = r'''
import json
import hashlib
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[2])
sys.path.insert(0, sys.argv[3])
import app_module.daily_market_technical_official_disposition_composite_bookmark_v1 as bm

calls = []
original_open = bm.open_daily_market_technical_official_disposition_projection_group_session_v2
def counted_open(query, *, cancel_callback=None):
    calls.append(query.to_json())
    return original_open(query, cancel_callback=cancel_callback)
bm.open_daily_market_technical_official_disposition_projection_group_session_v2 = counted_open
context = bm.read_daily_market_technical_official_disposition_composite_bookmark_context_v1(
    Path(sys.argv[1]).read_bytes()
)
selected = context.selected
comparison = context.comparison_selections[0]
request = bm.DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.create(
    context.query,
    page_index=selected.page.page_index,
    page_size=selected.page.page_size,
)
reopened_page = context.read_page_request(request)
assert reopened_page.page_identity_sha256 == selected.selection.page_identity_sha256
assert len(calls) == 1
print(json.dumps({
    "pid": __import__("os").getpid(),
    "open_count": len(calls),
    "query": context.query.query_identity_sha256,
    "f17_query": context.query.f17_query_identity_sha256,
    "group": context.query.projection_group_session_identity_sha256,
    "result": context.result.operation_identity_sha256,
    "counts": selected.selection.result_counts_identity_sha256,
    "pins": [[key, value] for key, value in context.result.source_pins],
    "selected_request": selected.selection.page_request_identity_sha256,
    "selected_page": selected.page.page_identity_sha256,
    "selected_row": selected.row.row_identity_sha256,
    "comparison_request": comparison.selection.page_request_identity_sha256,
    "comparison_page": comparison.page.page_identity_sha256,
    "comparison_row": comparison.row.row_identity_sha256,
    "selected_row_json_sha256": hashlib.sha256(
        selected.selection.row_json.encode("utf-8")
    ).hexdigest(),
    "comparison_row_json_sha256": hashlib.sha256(
        comparison.selection.row_json.encode("utf-8")
    ).hexdigest(),
    "scope": context.scope,
    "availability": context.availability_status,
    "historical_pit_eligible": context.historical_pit_eligible,
    "bookmark_is_reader_certification": context.bookmark_is_reader_certification,
}, sort_keys=True))
'''
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            child,
            str(raw_path),
            str(candidate_dir),
            str(_REPO_ROOT),
        ],
        cwd=_REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=1200,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["pid"] != os.getpid()
    assert payload["open_count"] == 1
    assert payload["query"] == bookmark.query_identity_sha256
    assert payload["f17_query"] == bookmark.f17_query_identity_sha256
    assert payload["group"] == bookmark.projection_group_session_identity_sha256
    assert payload["result"] == bookmark.result_identity_sha256
    assert payload["counts"] == bookmark.result_counts_identity_sha256
    assert payload["pins"] == [[key, value] for key, value in bookmark.source_pins]
    assert len(payload["pins"]) == 37
    assert payload["selected_request"] == bookmark.selected.page_request_identity_sha256
    assert payload["selected_page"] == bookmark.selected.page_identity_sha256
    assert payload["selected_row"] == bookmark.selected.row_identity_sha256
    assert payload["selected_row_json_sha256"] == hashlib.sha256(
        bookmark.selected.row_json.encode("utf-8")
    ).hexdigest()
    comparison = bookmark.comparison_selections[0]
    assert payload["comparison_request"] == comparison.page_request_identity_sha256
    assert payload["comparison_page"] == comparison.page_identity_sha256
    assert payload["comparison_row"] == comparison.row_identity_sha256
    assert payload["comparison_row_json_sha256"] == hashlib.sha256(
        comparison.row_json.encode("utf-8")
    ).hexdigest()
    assert payload["scope"] == "current_only"
    assert payload["availability"] == "unknown"
    assert payload["historical_pit_eligible"] is False
    assert payload["bookmark_is_reader_certification"] is False


def test_serialized_pins_and_page_ids_cannot_be_rewritten_as_a_selection(
    full257_no_match_owner: _FullOwner,
    full257_or_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> None:
    bookmark = _bookmark_from_full257(full257_no_match_owner, full257_or_result)
    payload = bookmark.to_dict()
    payload["source_pins"][0][1] = "0" * 64
    with pytest.raises(bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error):
        bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1.from_dict(payload)

    selection_payload = bookmark.selected.to_dict()
    selection_payload["page_identity_sha256"] = "0" * 64
    with pytest.raises(bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error):
        bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeSelectionV1.from_dict(
            selection_payload,
        )


def test_selection_factory_rejects_a_page_owned_by_another_result(
    full257_no_match_owner: _FullOwner,
    full257_or_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> None:
    owner = full257_no_match_owner
    result = full257_or_result
    first_page = result.read_page(0, 8)
    other_query = bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        owner.session.query,
        projection_group_session_identity_sha256=owner.group.identity_sha256,
        ma_states=("match",),
        kdj_states=(owner.kdj_state,),
        condition_combine_mode="AND",
        unknown_policy="exclude",
    )
    other_result = owner.session.execute_composite_query_v1(other_query)
    other_page = other_result.read_page(0, 8)
    with pytest.raises(bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error):
        bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeSelectionV1.from_real_row_context(
            result,
            other_page,
            first_page.rows[0].stock_code,
        )


def test_source_shard_change_after_save_rejects_restore_without_partial_context(
    bundle_fixture: _BundleFixture,
    full257_no_match_owner: _FullOwner,
    full257_or_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> None:
    bookmark = _bookmark_from_full257(full257_no_match_owner, full257_or_result)
    shard_refs = bundle_fixture.verified_state.manifest["row_shards"]
    assert isinstance(shard_refs, list) and shard_refs
    first_ref = shard_refs[0]
    assert isinstance(first_ref, dict)
    shard_path = bundle_fixture.bundle_root / str(first_ref["relative_path"])
    manifest_path = bundle_fixture.bundle_root / bundle_fixture.reference.manifest_relative_path
    manifest_before = manifest_path.read_bytes()
    original_bytes = shard_path.read_bytes()
    changed_bytes = original_bytes + b" "
    bookmark_before = bookmark.to_json()
    assert changed_bytes != original_bytes
    restored_context: bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV1 | None = None
    try:
        shard_path.write_bytes(changed_bytes)
        with pytest.raises(
            bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error,
        ) as error_info:
            restored_context = bookmark_module.read_daily_market_technical_official_disposition_composite_bookmark_context_v1(
                bookmark.to_json(),
            )
        assert restored_context is None
        assert error_info.value.code == "restore_exact_reopen_failed"
        cause_code = getattr(error_info.value.__cause__, "code", "")
        assert "shard_bytes_sha_mismatch" in cause_code
        assert manifest_path.read_bytes() == manifest_before
        assert bookmark.to_json() == bookmark_before
    finally:
        shard_path.write_bytes(original_bytes)
    assert shard_path.read_bytes() == original_bytes


def test_cancel_before_source_open_never_returns_or_starts_a_context(
    monkeypatch: pytest.MonkeyPatch,
    full257_no_match_owner: _FullOwner,
    full257_or_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> None:
    bookmark = _bookmark_from_full257(full257_no_match_owner, full257_or_result)
    calls = 0
    original_open = bookmark_module.open_daily_market_technical_official_disposition_projection_group_session_v2

    def counted_open(
        query: DailyMarketTechnicalOfficialDispositionQueryV1 | bytes | str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionReadSessionV1:
        nonlocal calls
        calls += 1
        return original_open(query, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        bookmark_module,
        "open_daily_market_technical_official_disposition_projection_group_session_v2",
        counted_open,
    )
    restored_context: (
        bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV1
        | None
    ) = None
    with pytest.raises(
        bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error,
        match="cancelled",
    ):
        restored_context = bookmark_module.read_daily_market_technical_official_disposition_composite_bookmark_context_v1(
            bookmark,
            cancel_callback=lambda: True,
        )
    assert restored_context is None
    assert calls == 0


def test_cancel_after_first_selected_page_never_returns_partial_context(
    monkeypatch: pytest.MonkeyPatch,
    full257_no_match_owner: _FullOwner,
    full257_or_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> None:
    bookmark = _bookmark_from_full257(full257_no_match_owner, full257_or_result)
    cancelled = False
    page_reads = 0

    def cancel_after_first_page() -> bool:
        return cancelled

    result_type = composite_module.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1
    original_read_page_request = result_type.read_page_request

    def cancel_after_materialized_page(
        result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
        request: DailyMarketTechnicalOfficialDispositionCompositePageRequestV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1:
        nonlocal cancelled, page_reads
        page = original_read_page_request(
            result,
            request,
            cancel_callback=cancel_callback,
        )
        page_reads += 1
        if page_reads == 1:
            cancelled = True
        return page

    monkeypatch.setattr(
        result_type,
        "read_page_request",
        cancel_after_materialized_page,
    )
    restored_context: (
        bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV1
        | None
    ) = None
    with pytest.raises(
        bookmark_module.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error,
        match="cancelled",
    ):
        restored_context = bookmark_module.read_daily_market_technical_official_disposition_composite_bookmark_context_v1(
            bookmark,
            cancel_callback=cancel_after_first_page,
        )
    assert restored_context is None
    assert page_reads == 1
