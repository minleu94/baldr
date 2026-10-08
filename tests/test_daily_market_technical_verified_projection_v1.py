"""原核驗迴圈只產生一次 row，且投影失敗不能交出工作階段。"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app_module import daily_market_technical_parent_v4_query as parent_query
from app_module.daily_market_technical_feature_snapshot_v4 import DailyMarketTechnicalFeatureSnapshotV4
from app_module.daily_market_technical_parent_v4_query import DailyMarketTechnicalParentV4Row
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4ReadSessionBuilder,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4StoreError, DailyMarketTechnicalUniverseV4StoreReader,
)
from app_module.rule_research_technical_parent_capture_v4 import DailyMarketTechnicalParentCaptureV4VerifiedRead
from tests.test_daily_market_technical_universe_v4_read_session import synthetic_read_session_source


class _Projection:
    def __init__(self, fail_after: int | None = None) -> None:
        self.fail_after = fail_after
        self.codes: list[str] = []
        self.events: list[tuple[str, int]] = []

    def begin_verified_parent(self, segment_index: int, parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead) -> None:
        assert isinstance(parent_read.verified_batches, tuple)
        self.events.append(('begin', segment_index))

    def consume_verified_snapshot(self, segment_index: int, snapshot: DailyMarketTechnicalFeatureSnapshotV4, parent_row: DailyMarketTechnicalParentV4Row) -> None:
        assert snapshot.stock_code == parent_row.stock_code
        assert snapshot.snapshot_identity_sha256 == parent_row.snapshot_identity_sha256
        self.codes.append(snapshot.stock_code)
        if self.fail_after == len(self.codes):
            raise RuntimeError('intentional_projection_failure')

    def end_verified_parent(self, segment_index: int, parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead) -> None:
        self.events.append(('end', segment_index))


def _builder(fixture: dict[str, Any], cancel_callback: Callable[[], bool] | None = None) -> DailyMarketTechnicalUniverseV4ReadSessionBuilder:
    return DailyMarketTechnicalUniverseV4ReadSessionBuilder(
        store_output_root=fixture['store_root'],
        generation_identity_sha256=fixture['plan'].generation_identity_sha256,
        plan_identity_sha256=fixture['plan'].identity_sha256,
        plan_sha256=fixture['plan_sha256'],
        receipt_identity_sha256=fixture['complete'].identity_sha256,
        receipt_sha256=fixture['complete'].content_sha256,
        cancel_callback=cancel_callback,
    )


def _read(fixture: dict[str, Any], builder: DailyMarketTechnicalUniverseV4ReadSessionBuilder) -> Any:
    return DailyMarketTechnicalUniverseV4StoreReader(fixture['store_root']).read_exact_with_verified_parent_callback(
        fixture['plan'].generation_identity_sha256,
        fixture['plan'].identity_sha256,
        fixture['complete'].identity_sha256,
        expected_receipt_sha256=fixture['complete'].content_sha256,
        expected_plan_sha256=fixture['plan_sha256'],
        parent_verified_callback=builder.consume_verified_parent,
    )


def test_projection_uses_each_original_row_once(synthetic_read_session_source: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = synthetic_read_session_source
    builder = _builder(fixture)
    projection = _Projection()
    builder.bind_verified_projection(projection)
    original = parent_query._make_row
    made_codes: list[str] = []

    def record(snapshot: DailyMarketTechnicalFeatureSnapshotV4) -> DailyMarketTechnicalParentV4Row:
        made_codes.append(snapshot.stock_code)
        return original(snapshot)

    monkeypatch.setattr(parent_query, '_make_row', record)
    state = _read(fixture, builder)
    assert len(projection.codes) == state.counts.processed_count == 17
    assert projection.codes == made_codes
    assert len(set(projection.codes)) == 17
    assert projection.events == [
        event for index, _reference in state.segment_parent_references
        for event in [('begin', index), ('end', index)]
    ]
    assert builder.verified_session is None  # Store callback本身沒有Bundle發行資格。


def test_projection_failure_does_not_publish_partial_state(synthetic_read_session_source: dict[str, Any]) -> None:
    fixture = synthetic_read_session_source
    builder = _builder(fixture)
    projection = _Projection(fail_after=2)
    builder.bind_verified_projection(projection)
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError, match='intentional_projection_failure') as denied:
        _read(fixture, builder)
    assert denied.value.code == 'technical_universe_v4_parent_verified_callback_failed'
    assert len(projection.codes) == 2
    assert projection.events == [('begin', 0)]
    assert builder.verified_session is None
    assert builder._built_session is None


def test_cancel_during_projection_never_publishes_partial_session(synthetic_read_session_source: dict[str, Any]) -> None:
    fixture = synthetic_read_session_source
    cancelled = [False]

    class CancellingProjection(_Projection):
        def consume_verified_snapshot(self, segment_index: int, snapshot: DailyMarketTechnicalFeatureSnapshotV4, parent_row: DailyMarketTechnicalParentV4Row) -> None:
            super().consume_verified_snapshot(segment_index, snapshot, parent_row)
            if len(self.codes) == 2:
                cancelled[0] = True

    builder = _builder(fixture, cancel_callback=lambda: cancelled[0])
    projection = CancellingProjection()
    builder.bind_verified_projection(projection)
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as denied:
        _read(fixture, builder)
    assert denied.value.code == 'technical_universe_v4_query_cancelled'
    assert projection.codes == list(fixture['plan'].cohort.included_stock_codes[:2])
    assert projection.events == [('begin', 0)]
    assert builder.verified_session is None
    assert builder._built_session is None
