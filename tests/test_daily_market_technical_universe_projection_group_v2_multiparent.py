"""F03 三路暫存投影的真實雙 parent StoreReader callback 契約。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

import app_module.daily_market_technical_parent_v4_query as parent_query
from app_module.daily_market_technical_universe_kdj_alignment_query_v1 import (
    DailyMarketTechnicalKDJProjectionCollectorV1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DailyMarketTechnicalMaAlignmentSourceRequestV1,
    DailyMarketTechnicalMaAlignmentVerifiedCollectorV1,
)
from app_module.daily_market_technical_universe_projection_group_v2 import (
    DailyMarketTechnicalUniverseProjectionGroupV2,
)
from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Row,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4ReadSessionBuilder,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4StoreError,
    DailyMarketTechnicalUniverseV4StoreReader,
)
from app_module.daily_market_technical_universe_volatility_alignment_query_v1 import (
    DailyMarketTechnicalVolatilityProjectionCollectorV1,
)
from app_module.rule_research_technical_parent_capture_v4 import (
    DailyMarketTechnicalParentCaptureV4VerifiedRead,
)
from test_daily_market_technical_universe_v4_query import synthetic_full_store


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _builder(fixture: dict[str, Any]) -> DailyMarketTechnicalUniverseV4ReadSessionBuilder:
    plan = fixture["plan"]
    complete = fixture["complete"]
    return DailyMarketTechnicalUniverseV4ReadSessionBuilder(
        store_output_root=fixture["store_output_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=complete.identity_sha256,
        receipt_sha256=complete.content_sha256,
    )


def _source_request(
    fixture: dict[str, Any],
    builder: DailyMarketTechnicalUniverseV4ReadSessionBuilder,
) -> DailyMarketTechnicalMaAlignmentSourceRequestV1:
    plan = fixture["plan"]
    complete = fixture["complete"]
    cohort = plan.cohort
    source_clock = plan.source_clock
    bundle_identity = _sha("f03-multiparent-unpublished-bundle")
    return DailyMarketTechnicalMaAlignmentSourceRequestV1(
        bundle_output_root=str(Path(fixture["temporary_root"]) / "unpublished-bundle"),
        bundle_identity_sha256=bundle_identity,
        manifest_relative_path=f"manifests/{bundle_identity}.json",
        expected_manifest_sha256=_sha("f03-multiparent-unpublished-manifest"),
        technical_store_output_root=builder.store_output_root,
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=complete.identity_sha256,
        receipt_sha256=complete.content_sha256,
        cohort_identity_sha256=cohort.cohort_identity_sha256,
        source_clock_identity_sha256=source_clock.identity_sha256,
        method_contracts_sha256=plan.to_dict()["method_contracts_sha256"],
        market_assignment_pin_identity_sha256=_sha("f03-multiparent-market-pin"),
        official_disposal_pin_identity_sha256=_sha("f03-multiparent-disposal-pin"),
        decision_date=cohort.decision_date,
        decision_cutoff=source_clock.decision_cutoff.isoformat(),
        declared_count=len(cohort.declared_stock_codes),
        included_count=len(cohort.included_stock_codes),
        excluded_count=len(cohort.excluded_stock_codes),
        source_coverage_status="complete",
        source_coverage_incomplete_reason_count=0,
        technical_receipt_status="complete",
    )


def _new_group(
    fixture: dict[str, Any],
) -> tuple[
    DailyMarketTechnicalUniverseV4ReadSessionBuilder,
    DailyMarketTechnicalUniverseProjectionGroupV2,
]:
    builder = _builder(fixture)
    group = DailyMarketTechnicalUniverseProjectionGroupV2(_source_request(fixture, builder))
    group.bind_to_builder(builder)
    return builder, group


def _assert_poisoned(group: DailyMarketTechnicalUniverseProjectionGroupV2) -> None:
    assert group.status == "failed"
    assert group.processed_snapshot_count == 0
    assert group.completed_parent_count == 0
    assert group._seen_parent_identities == set()
    assert group._ma_collector._finished is True
    assert group._ma_collector._issued_session is None
    assert group._ma_collector._active_parent is None
    assert group._ma_collector._observations == []
    assert group._ma_collector._entries == []
    assert group._ma_collector._seen_codes == set()
    assert group._kdj_collector._failed is True
    assert group._kdj_collector._active_parent is None
    assert group._kdj_collector._entries == []
    assert group._kdj_collector._seen_codes == set()
    assert group._volatility_collector._failed is True
    assert group._volatility_collector._active_segment is None
    assert group._volatility_collector._entries == []
    assert group._volatility_collector._seen_codes == set()


def _read_with_callback(
    fixture: dict[str, Any],
    callback: Any,
) -> Any:
    plan = fixture["plan"]
    complete = fixture["complete"]
    return DailyMarketTechnicalUniverseV4StoreReader(
        fixture["store_output_root"]
    ).read_exact_with_verified_parent_callback(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        complete.identity_sha256,
        expected_receipt_sha256=complete.content_sha256,
        expected_plan_sha256=fixture["plan_sha256"],
        parent_verified_callback=callback,
    )


def test_exact_reader_visits_both_real_parents_and_fans_out_same_rows_once(
    synthetic_full_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = synthetic_full_store
    builder, group = _new_group(fixture)
    member_calls: dict[
        str,
        list[
            tuple[
                int,
                str,
                DailyMarketTechnicalFeatureSnapshotV4,
                DailyMarketTechnicalParentV4Row,
            ]
        ],
    ] = {
        "ma": [], "kdj": [], "volatility": [],
    }
    built_rows: list[
        tuple[DailyMarketTechnicalFeatureSnapshotV4, DailyMarketTechnicalParentV4Row]
    ] = []
    callbacks: list[tuple[int, DailyMarketTechnicalParentCaptureV4VerifiedRead]] = []
    transitions: list[tuple[int, str, int, int]] = []

    original_make_row = parent_query._make_row

    def count_row(
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    ) -> DailyMarketTechnicalParentV4Row:
        row = original_make_row(snapshot)
        built_rows.append((snapshot, row))
        return row

    original_ma = DailyMarketTechnicalMaAlignmentVerifiedCollectorV1.consume_verified_snapshot
    original_kdj = DailyMarketTechnicalKDJProjectionCollectorV1.consume_verified_snapshot
    original_volatility = DailyMarketTechnicalVolatilityProjectionCollectorV1.consume_unqualified_snapshot
    original_end = DailyMarketTechnicalUniverseProjectionGroupV2.end_verified_parent

    def observe_ma(
        self: Any,
        segment: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        original_ma(self, segment, snapshot, row)
        member_calls["ma"].append((segment, snapshot.stock_code, snapshot, row))

    def observe_kdj(
        self: Any,
        segment: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        original_kdj(self, segment, snapshot, row)
        member_calls["kdj"].append((segment, snapshot.stock_code, snapshot, row))

    def observe_volatility(
        self: Any,
        segment: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        original_volatility(self, segment, snapshot, row)
        member_calls["volatility"].append((segment, snapshot.stock_code, snapshot, row))

    def observe_parent_end(
        self: Any,
        segment: int,
        parent: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        original_end(self, segment, parent)
        transitions.append((
            segment,
            self.status,
            self.completed_parent_count,
            self.processed_snapshot_count,
        ))

    def callback(
        segment: int,
        parent: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        callbacks.append((segment, parent))
        builder.consume_verified_parent(segment, parent)

    with monkeypatch.context() as patcher:
        patcher.setattr(parent_query, "_make_row", count_row)
        patcher.setattr(
            DailyMarketTechnicalMaAlignmentVerifiedCollectorV1,
            "consume_verified_snapshot",
            observe_ma,
        )
        patcher.setattr(
            DailyMarketTechnicalKDJProjectionCollectorV1,
            "consume_verified_snapshot",
            observe_kdj,
        )
        patcher.setattr(
            DailyMarketTechnicalVolatilityProjectionCollectorV1,
            "consume_unqualified_snapshot",
            observe_volatility,
        )
        patcher.setattr(
            DailyMarketTechnicalUniverseProjectionGroupV2,
            "end_verified_parent",
            observe_parent_end,
        )
        state = _read_with_callback(fixture, callback)

    expected_codes = tuple(f"S{index:04d}" for index in range(257))
    assert state.receipt.status == "complete"
    assert state.counts.to_dict() == {
        "declared_count": 258,
        "included_count": 257,
        "excluded_count": 1,
        "processed_count": 257,
        "pending_count": 0,
        "missing_data_count": 1,
        "missing_data_pending_count": 0,
    }
    assert tuple(segment for segment, _parent in callbacks) == (0, 1)
    assert tuple(index for index, _reference in state.segment_parent_references) == (0, 1)
    assert tuple(
        sum(len(batch.snapshots) for batch in parent.verified_batches)
        for _segment, parent in callbacks
    ) == (256, 1)
    assert [item[0] for item in transitions] == [0, 1]
    assert transitions == [
        (0, "between_parents", 1, 256),
        (1, "between_parents", 2, 257),
    ]
    assert len(built_rows) == 257
    assert len(member_calls["ma"]) == len(member_calls["kdj"]) == len(member_calls["volatility"]) == 257
    for calls in member_calls.values():
        assert tuple(call[1] for call in calls) == expected_codes
        assert tuple(call[0] for call in calls) == (0,) * 256 + (1,)
    for index, (snapshot, row) in enumerate(built_rows):
        assert snapshot.stock_code == expected_codes[index]
        ma_call = member_calls["ma"][index]
        kdj_call = member_calls["kdj"][index]
        volatility_call = member_calls["volatility"][index]
        assert ma_call[2] is kdj_call[2] is volatility_call[2] is snapshot
        assert ma_call[3] is kdj_call[3] is volatility_call[3] is row
    member_codes = (
        tuple(entry.stock_code for entry in group._ma_collector._entries),
        tuple(entry.stock_code for entry in group._kdj_collector._entries),
        tuple(entry.stock_code for entry in group._volatility_collector._entries),
    )
    assert member_codes == (expected_codes, expected_codes, expected_codes)
    assert "X9999" not in member_codes[0]
    assert group.status == "between_parents"
    assert group.completed_parent_count == 2
    assert group.processed_snapshot_count == 257
    assert group.qualification_status == "projection_group_unqualified"
    assert builder.verified_session is None


def test_real_reader_order_and_replayed_parent_callbacks_poison_group(
    synthetic_full_store: dict[str, Any],
) -> None:
    fixture = synthetic_full_store

    # StoreReader 提供的真 typed parent 被刻意以錯誤 segment 傳給 group。
    builder, group = _new_group(fixture)
    wrong_order_seen: list[int] = []

    def wrong_order_callback(
        segment: int,
        parent: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        wrong_order_seen.append(segment)
        group.begin_verified_parent(1, parent)

    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as wrong_order:
        _read_with_callback(fixture, wrong_order_callback)
    assert wrong_order.value.code == "technical_universe_v4_parent_verified_callback_failed"
    assert wrong_order_seen == [0]
    _assert_poisoned(group)
    assert builder.verified_session is None

    # 第二次真 reader callback 收到 segment 1 的 parent；測試 callback 故意重播
    # 第一段 reader 交付的原 parent 物件，group 必須以身份重播拒絕並清空首段暫存。
    builder, group = _new_group(fixture)
    first_parent: DailyMarketTechnicalParentCaptureV4VerifiedRead | None = None
    actual_callbacks: list[tuple[int, DailyMarketTechnicalParentCaptureV4VerifiedRead]] = []

    def replay_callback(
        segment: int,
        parent: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        nonlocal first_parent
        actual_callbacks.append((segment, parent))
        if segment == 0:
            first_parent = parent
            builder.consume_verified_parent(segment, parent)
            return
        assert segment == 1
        assert first_parent is not None
        assert parent is not first_parent
        builder.consume_verified_parent(segment, first_parent)

    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as replayed:
        _read_with_callback(fixture, replay_callback)
    assert replayed.value.code == "technical_universe_v4_parent_verified_callback_failed"
    assert tuple(segment for segment, _parent in actual_callbacks) == (0, 1)
    _assert_poisoned(group)
    assert builder.verified_session is None


def test_failure_on_second_real_parent_clears_all_first_parent_entries(
    synthetic_full_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = synthetic_full_store
    builder, group = _new_group(fixture)
    actual_parent_indices: list[int] = []
    injection: dict[str, object] = {}
    original_volatility = DailyMarketTechnicalVolatilityProjectionCollectorV1.consume_unqualified_snapshot

    def fail_during_second_parent(
        self: Any,
        segment: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        if segment == 1 and not injection:
            partial_member_counts = (
                len(group._ma_collector._entries),
                len(group._kdj_collector._entries),
                len(group._volatility_collector._entries),
            )
            injection.update({
                "segment": segment,
                "stock_code": snapshot.stock_code,
                "processed_before_current_fanout": group.processed_snapshot_count,
                "completed_parent_count": group.completed_parent_count,
                "partial_member_counts": partial_member_counts,
            })
            assert group.completed_parent_count == 1
            assert group.processed_snapshot_count == 256
            # Fan-out 順序是 MA、KDJ、波動度；目前這筆已進前兩個 member。
            assert partial_member_counts == (257, 257, 256)
            assert group._ma_collector._entries[-1].stock_code == snapshot.stock_code
            assert group._kdj_collector._entries[-1].stock_code == snapshot.stock_code
            assert group._volatility_collector._entries[-1].stock_code == "S0255"
            raise RuntimeError("injected_second_parent_volatility_failure")
        original_volatility(self, segment, snapshot, row)

    def callback(
        segment: int,
        parent: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        actual_parent_indices.append(segment)
        builder.consume_verified_parent(segment, parent)

    with monkeypatch.context() as patcher:
        patcher.setattr(
            DailyMarketTechnicalVolatilityProjectionCollectorV1,
            "consume_unqualified_snapshot",
            fail_during_second_parent,
        )
        with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as failed_read:
            _read_with_callback(fixture, callback)

    assert failed_read.value.code == "technical_universe_v4_parent_verified_callback_failed"
    assert isinstance(failed_read.value.__cause__, RuntimeError)
    assert str(failed_read.value.__cause__) == "injected_second_parent_volatility_failure"
    assert actual_parent_indices == [0, 1]
    assert injection == {
        "segment": 1,
        "stock_code": "S0256",
        "processed_before_current_fanout": 256,
        "completed_parent_count": 1,
        "partial_member_counts": (257, 257, 256),
    }
    _assert_poisoned(group)
    assert builder.verified_session is None
