"""同次 exact bundle 的 MA 私有 prepare，不授三路共同資格。"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DailyMarketTechnicalMaAlignmentCompactIndexV1,
    DailyMarketTechnicalMaAlignmentSourceRequestV1,
    DailyMarketTechnicalUniverseMaAlignmentQueryV1Error,
)
from app_module.daily_market_technical_universe_projection_group_v2 import (
    DailyMarketTechnicalUniverseProjectionGroupV2,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4ReadSessionBuilder,
)
from test_daily_market_technical_official_disposition_bundle_v1 import (  # type: ignore[import-not-found]
    bundle_fixture,
)


def _read_group(fixture: Any) -> tuple[Any, Any, Any, Any, Any]:
    reader = DailyMarketTechnicalOfficialDispositionBundleReaderV1(fixture.bundle_root)
    metadata = reader.read_manifest_metadata(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    request = DailyMarketTechnicalMaAlignmentSourceRequestV1.from_unverified_manifest_metadata(
        metadata,
        bundle_output_root=fixture.bundle_root,
        bundle_identity_sha256=fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    builder = DailyMarketTechnicalUniverseV4ReadSessionBuilder(
        store_output_root=metadata.technical_store_output_root_label,
        generation_identity_sha256=metadata.technical_generation_identity_sha256,
        plan_identity_sha256=metadata.technical_plan_identity_sha256,
        plan_sha256=metadata.technical_plan_sha256,
        receipt_identity_sha256=metadata.technical_receipt_identity_sha256,
        receipt_sha256=metadata.technical_receipt_sha256,
    )
    group = DailyMarketTechnicalUniverseProjectionGroupV2(request)
    group.bind_to_builder(builder)
    state = reader.read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
        technical_read_session_builder=builder,
    )
    session = builder.verified_session
    assert session is not None
    query = session.create_query(stock_filter=(fixture.included_codes[-1],), descending=True)
    selection = session.select_stock_codes(query, eligible_stock_codes=None)
    return group, builder, state, query, selection


def _assert_poisoned(group: Any) -> None:
    assert group.status == "failed"
    assert group._ma_collector._finished is True
    assert group._ma_collector._issued_session is None
    assert group._ma_collector._entries == []
    assert group._kdj_collector._entries == []
    assert group._volatility_collector._entries == []


def test_two_parent_prepare_keeps_full_population_without_issuing_any_member(
    bundle_fixture: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module import daily_market_technical_universe_ma_alignment_query_v1 as module

    group, builder, state, query, selection = _read_group(bundle_fixture)
    assert group.completed_parent_count == 2
    assert len(selection.stock_codes) == 1

    def forbidden_issue(**kwargs: object) -> None:
        pytest.fail("prepare 不得呼叫 session issuer")

    monkeypatch.setattr(module, "_issue_ma_alignment_read_session_v1", forbidden_issue)
    candidate = group._ma_collector._prepare_for_projection_group(
        group, builder, state, query, selection,
    )
    assert candidate.reader_issued is False
    assert candidate.index.reader_issued is False
    assert candidate.builder is builder
    assert candidate.bundle_state is state
    assert candidate.p01_session is builder.verified_session
    assert candidate.base_query is query
    assert candidate.selection is selection
    assert candidate.request is group._source_request
    assert tuple(row.stock_code for row in candidate.index.entries) == bundle_fixture.included_codes
    assert len(candidate.parent_observations) == 2
    references = builder.verified_session._state.segment_parent_references
    for observation, (segment_index, reference) in zip(candidate.parent_observations, references, strict=True):
        assert observation.segment_index == segment_index
        assert observation.parent_root == reference.parent_root
        assert observation.snapshot_repository_root != reference.parent_root
    assert group.status == "between_parents"
    assert group.qualification_status == "projection_group_unqualified"
    assert group._ma_collector._finished is False
    assert group._ma_collector._issued_session is None
    # 同一 group 不能藉舊 MA-only public finalizer 取得單獨資格。
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error) as denied:
        group._ma_collector.finalize_verified_publication(builder, state, query, selection)
    assert denied.value.code == "technical_ma_alignment_collector_publication_input_invalid"


@pytest.mark.parametrize("fault", ("foreign_observer", "missing_observation", "late_cancel", "late_poison"))
def test_group_prepare_failure_never_leaves_partial_member_buffers(
    bundle_fixture: Any, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    group, builder, state, query, selection = _read_group(bundle_fixture)
    cancelled = threading.Event()
    if fault == "foreign_observer":
        builder._verified_projection = object()
    elif fault == "missing_observation":
        group._ma_collector._observations.pop()
    else:
        original = DailyMarketTechnicalMaAlignmentCompactIndexV1.create_unverified_transport

        def inject_after_index(*args: Any, **kwargs: Any) -> Any:
            index = original(*args, **kwargs)
            if fault == "late_cancel":
                cancelled.set()
            else:
                group._poison()
            return index

        monkeypatch.setattr(
            DailyMarketTechnicalMaAlignmentCompactIndexV1,
            "create_unverified_transport", staticmethod(inject_after_index),
        )
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error):
        group._ma_collector._prepare_for_projection_group(
            group, builder, state, query, selection,
            cancel_callback=cancelled.is_set,
        )
    _assert_poisoned(group)
