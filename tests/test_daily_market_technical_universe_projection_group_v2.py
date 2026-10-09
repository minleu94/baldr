"""F03 三路同次 parent 投影暫存協調器的合成契約。"""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import threading
from typing import Any

import pytest

from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DailyMarketTechnicalMaAlignmentSourceRequestV1,
    DailyMarketTechnicalMaAlignmentVerifiedCollectorV1,
)
from app_module.daily_market_technical_universe_kdj_alignment_query_v1 import (
    DailyMarketTechnicalKDJProjectionCollectorV1,
)
from app_module.daily_market_technical_universe_projection_group_v2 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES,
    DailyMarketTechnicalUniverseProjectionGroupV2,
    DailyMarketTechnicalUniverseProjectionGroupV2Error,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4ReadSessionBuilder,
)
from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Row,
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
from test_daily_market_technical_universe_v4_query import synthetic_small_full_store


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
    cohort = plan.cohort
    clock = plan.source_clock
    complete = fixture["complete"]
    bundle_id = _sha("projection-group-v2-synthetic-bundle")
    bundle_root = Path(fixture["temporary_root"]) / "unpublished-synthetic-bundle"
    return DailyMarketTechnicalMaAlignmentSourceRequestV1(
        bundle_output_root=str(bundle_root),
        bundle_identity_sha256=bundle_id,
        manifest_relative_path=f"manifests/{bundle_id}.json",
        expected_manifest_sha256=_sha("projection-group-v2-synthetic-manifest"),
        technical_store_output_root=builder.store_output_root,
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=complete.identity_sha256,
        receipt_sha256=complete.content_sha256,
        cohort_identity_sha256=cohort.cohort_identity_sha256,
        source_clock_identity_sha256=clock.identity_sha256,
        method_contracts_sha256=plan.to_dict()["method_contracts_sha256"],
        market_assignment_pin_identity_sha256=_sha("market-pin"),
        official_disposal_pin_identity_sha256=_sha("disposal-pin"),
        decision_date=cohort.decision_date,
        decision_cutoff=clock.decision_cutoff.isoformat(),
        declared_count=len(cohort.declared_stock_codes),
        included_count=len(cohort.included_stock_codes),
        excluded_count=len(cohort.excluded_stock_codes),
        source_coverage_status="complete",
        source_coverage_incomplete_reason_count=0,
        technical_receipt_status="complete",
    )


def _read_exact(
    fixture: dict[str, Any],
    builder: DailyMarketTechnicalUniverseV4ReadSessionBuilder,
) -> tuple[Any, list[DailyMarketTechnicalParentCaptureV4VerifiedRead]]:
    plan = fixture["plan"]
    complete = fixture["complete"]
    reader = DailyMarketTechnicalUniverseV4StoreReader(fixture["store_output_root"])
    parents: list[DailyMarketTechnicalParentCaptureV4VerifiedRead] = []

    def callback(
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        parents.append(parent_read)
        builder.consume_verified_parent(segment_index, parent_read)

    state = reader.read_exact_with_verified_parent_callback(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        complete.identity_sha256,
        expected_receipt_sha256=complete.content_sha256,
        expected_plan_sha256=fixture["plan_sha256"],
        parent_verified_callback=callback,
    )
    return state, parents


def _assert_member_poisoned(group: DailyMarketTechnicalUniverseProjectionGroupV2) -> None:
    assert group.status == "failed"
    assert group.processed_snapshot_count == 0
    assert group.completed_parent_count == 0
    assert group._ma_collector._finished is True
    assert group._ma_collector._issued_session is None
    assert group._ma_collector._active_parent is None
    assert group._ma_collector._observations == []
    assert group._ma_collector._entries == []
    assert group._ma_collector._seen_codes == set()
    assert group._kdj_collector._failed is True
    assert group._kdj_collector._entries == []
    assert group._kdj_collector._seen_codes == set()
    assert group._volatility_collector._failed is True
    assert group._volatility_collector._entries == []
    assert group._volatility_collector._seen_codes == set()
    assert not hasattr(group, "members")
    assert not hasattr(group, "entries")
    assert not hasattr(group, "index")
    assert not hasattr(group, "finalize")


def test_real_parent_fans_out_once_and_any_failure_permanently_poisons_all_members(
    synthetic_small_full_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = synthetic_small_full_store

    # 建構與綁定前的取消都要 fail-closed，不能觸發 P01 builder slot。
    with pytest.raises(DailyMarketTechnicalUniverseProjectionGroupV2Error) as cancelled_init:
        DailyMarketTechnicalUniverseProjectionGroupV2(
            object(), cancel_callback=lambda: True  # type: ignore[arg-type]
        )
    assert cancelled_init.value.code == "technical_projection_group_v2_cancelled"

    prebind_builder = _builder(fixture)
    prebind_request = _source_request(fixture, prebind_builder)
    cancel_before_bind = threading.Event()
    prebind_group = DailyMarketTechnicalUniverseProjectionGroupV2(
        prebind_request,
        cancel_callback=cancel_before_bind.is_set,
    )
    held_ma = prebind_group._ma_collector
    cancel_before_bind.set()
    with pytest.raises(DailyMarketTechnicalUniverseProjectionGroupV2Error):
        prebind_group.bind_to_builder(prebind_builder)
    assert prebind_builder._verified_projection is None
    _assert_member_poisoned(prebind_group)
    cancel_before_bind.clear()
    with pytest.raises(Exception):
        held_ma.finalize_verified_publication(
            prebind_builder, object(), object(), object()
        )

    # 真正 StoreReader exact callback 產生一次 parent row，再以相同物件送三路。
    builder = _builder(fixture)
    request = _source_request(fixture, builder)
    group = DailyMarketTechnicalUniverseProjectionGroupV2(request)
    group.bind_to_builder(builder)
    calls: dict[
        str,
        list[tuple[int, DailyMarketTechnicalFeatureSnapshotV4, DailyMarketTechnicalParentV4Row]],
    ] = {
        "ma": [], "kdj": [], "volatility": [],
    }
    original_ma = DailyMarketTechnicalMaAlignmentVerifiedCollectorV1.consume_verified_snapshot
    original_kdj = DailyMarketTechnicalKDJProjectionCollectorV1.consume_verified_snapshot
    original_volatility = DailyMarketTechnicalVolatilityProjectionCollectorV1.consume_unqualified_snapshot

    with monkeypatch.context() as patcher:
        def observe_ma(
            self: Any,
            segment: int,
            snapshot: DailyMarketTechnicalFeatureSnapshotV4,
            parent_row: DailyMarketTechnicalParentV4Row,
        ) -> None:
            original_ma(self, segment, snapshot, parent_row)
            calls["ma"].append((segment, snapshot, parent_row))

        def observe_kdj(
            self: Any,
            segment: int,
            snapshot: DailyMarketTechnicalFeatureSnapshotV4,
            parent_row: DailyMarketTechnicalParentV4Row,
        ) -> None:
            original_kdj(self, segment, snapshot, parent_row)
            calls["kdj"].append((segment, snapshot, parent_row))

        def observe_volatility(
            self: Any,
            segment: int,
            snapshot: DailyMarketTechnicalFeatureSnapshotV4,
            parent_row: DailyMarketTechnicalParentV4Row,
        ) -> None:
            original_volatility(self, segment, snapshot, parent_row)
            calls["volatility"].append((segment, snapshot, parent_row))

        patcher.setattr(DailyMarketTechnicalMaAlignmentVerifiedCollectorV1, "consume_verified_snapshot", observe_ma)
        patcher.setattr(DailyMarketTechnicalKDJProjectionCollectorV1, "consume_verified_snapshot", observe_kdj)
        patcher.setattr(DailyMarketTechnicalVolatilityProjectionCollectorV1, "consume_unqualified_snapshot", observe_volatility)
        state, parents = _read_exact(fixture, builder)

    expected_count = request.included_count
    assert state.receipt.status == "complete"
    assert builder.verified_session is None
    assert len(parents) == 1
    assert group.status == "between_parents"
    assert group.processed_snapshot_count == expected_count
    assert group.completed_parent_count == 1
    assert all(len(calls[name]) == expected_count for name in calls)
    for position in range(expected_count):
        ma_call = calls["ma"][position]
        kdj_call = calls["kdj"][position]
        volatility_call = calls["volatility"][position]
        assert ma_call[0] == kdj_call[0] == volatility_call[0]
        assert ma_call[1] is kdj_call[1] is volatility_call[1]
        assert ma_call[2] is kdj_call[2] is volatility_call[2]
    assert group.qualification_status == "projection_group_unqualified"

    # 已核 parent 的 callback 結束後只代表位於兩段 parent 之間；尚未核完整
    # bundle counts，因此不會把單段完成標成整體完成。
    assert group.completed_parent_count == 1

    # 對三個真實 callback 收集到的同一批 typed parent/snapshot/row 引用做故障矩陣。
    # 此處不重新讀來源；每個案例都建立新 group/builder，確保 poison 無法續用。
    segment_index, first_snapshot, first_row = calls["ma"][0]
    verified_parent = parents[0]

    def new_bound_group(
        *, cancel_callback: Any = None,
    ) -> tuple[DailyMarketTechnicalUniverseV4ReadSessionBuilder, DailyMarketTechnicalUniverseProjectionGroupV2]:
        case_builder = _builder(fixture)
        case_group = DailyMarketTechnicalUniverseProjectionGroupV2(
            request,
            cancel_callback=cancel_callback,
        )
        case_group.bind_to_builder(case_builder)
        return case_builder, case_group

    target_methods: dict[tuple[str, str], tuple[Any, str]] = {
        ("ma", "begin"): (DailyMarketTechnicalMaAlignmentVerifiedCollectorV1, "begin_verified_parent"),
        ("kdj", "begin"): (DailyMarketTechnicalKDJProjectionCollectorV1, "begin_verified_parent"),
        ("volatility", "begin"): (DailyMarketTechnicalVolatilityProjectionCollectorV1, "begin_unqualified_segment"),
        ("ma", "consume"): (DailyMarketTechnicalMaAlignmentVerifiedCollectorV1, "consume_verified_snapshot"),
        ("kdj", "consume"): (DailyMarketTechnicalKDJProjectionCollectorV1, "consume_verified_snapshot"),
        ("volatility", "consume"): (DailyMarketTechnicalVolatilityProjectionCollectorV1, "consume_unqualified_snapshot"),
        ("ma", "end"): (DailyMarketTechnicalMaAlignmentVerifiedCollectorV1, "end_verified_parent"),
        ("kdj", "end"): (DailyMarketTechnicalKDJProjectionCollectorV1, "end_verified_parent"),
        ("volatility", "end"): (DailyMarketTechnicalVolatilityProjectionCollectorV1, "end_unqualified_segment"),
    }

    def run_phase(
        case_group: DailyMarketTechnicalUniverseProjectionGroupV2,
        phase: str,
    ) -> None:
        case_group.begin_verified_parent(segment_index, verified_parent)
        if phase == "begin":
            return
        if phase == "consume":
            case_group.consume_verified_snapshot(segment_index, first_snapshot, first_row)
            return
        for row_segment, snapshot, parent_row in calls["ma"]:
            case_group.consume_verified_snapshot(row_segment, snapshot, parent_row)
        assert phase == "end"
        case_group.end_verified_parent(segment_index, verified_parent)

    for member_name in ("ma", "kdj", "volatility"):
        for phase in ("begin", "consume", "end"):
            case_builder, case_group = new_bound_group()
            member_class, method_name = target_methods[(member_name, phase)]

            def fail_member(*args: Any, **kwargs: Any) -> None:
                raise RuntimeError(f"synthetic {member_name} {phase} failure")

            with monkeypatch.context() as patcher:
                if phase == "begin":
                    with pytest.raises(RuntimeError, match=f"synthetic {member_name} {phase} failure"):
                        with patcher.context() as active_patcher:
                            active_patcher.setattr(member_class, method_name, fail_member)
                            case_group.begin_verified_parent(segment_index, verified_parent)
                else:
                    # begin 與 consume 前置資料由真實 parent 引用建立；end 故障前
                    # 先讓三路各消費完整 segment，然後才替換指定 member 的結尾。
                    case_group.begin_verified_parent(segment_index, verified_parent)
                    if phase == "end":
                        for row_segment, snapshot, parent_row in calls["ma"]:
                            case_group.consume_verified_snapshot(row_segment, snapshot, parent_row)
                    with pytest.raises(RuntimeError, match=f"synthetic {member_name} {phase} failure"):
                        patcher.setattr(member_class, method_name, fail_member)
                        if phase == "consume":
                            case_group.consume_verified_snapshot(segment_index, first_snapshot, first_row)
                        else:
                            case_group.end_verified_parent(segment_index, verified_parent)
            _assert_member_poisoned(case_group)
            with pytest.raises(Exception):
                case_group._ma_collector.finalize_verified_publication(
                    case_builder, object(), object(), object()
                )

    # 在每個 member 的 begin／consume／end 回傳後取消，後續 member 不得繼續，
    # 並且整個 group 永久失效。所有案例重用同一 exact-read 收集到的 typed 輸入。
    for member_name, phase in target_methods:
        case_event = threading.Event()
        case_builder, case_group = new_bound_group(cancel_callback=case_event.is_set)
        member_class, method_name = target_methods[(member_name, phase)]
        original_method = getattr(member_class, method_name)

        def cancel_after_member(*args: Any, **kwargs: Any) -> Any:
            result = original_method(*args, **kwargs)
            case_event.set()
            return result

        if phase != "begin":
            case_group.begin_verified_parent(segment_index, verified_parent)
        if phase == "end":
            for row_segment, snapshot, parent_row in calls["ma"]:
                case_group.consume_verified_snapshot(row_segment, snapshot, parent_row)
        with monkeypatch.context() as patcher:
            patcher.setattr(member_class, method_name, cancel_after_member)
            with pytest.raises(DailyMarketTechnicalUniverseProjectionGroupV2Error) as cancelled_stage:
                if phase == "begin":
                    case_group.begin_verified_parent(segment_index, verified_parent)
                elif phase == "consume":
                    case_group.consume_verified_snapshot(segment_index, first_snapshot, first_row)
                else:
                    case_group.end_verified_parent(segment_index, verified_parent)
        assert cancelled_stage.value.code == "technical_projection_group_v2_cancelled"
        _assert_member_poisoned(case_group)
        assert case_builder._verified_projection is case_group

    # bool 是 int 的子類，但不能當成合法的 parent segment 索引。
    bool_builder, bool_group = new_bound_group()
    with pytest.raises(DailyMarketTechnicalUniverseProjectionGroupV2Error) as bool_segment:
        bool_group.begin_verified_parent(True, verified_parent)  # type: ignore[arg-type]
    assert bool_segment.value.code == "technical_projection_group_v2_parent_order_invalid"
    _assert_member_poisoned(bool_group)

    # 已完成的 parent reference 不可換新 segment 重播。
    with pytest.raises(DailyMarketTechnicalUniverseProjectionGroupV2Error) as replayed:
        group.begin_verified_parent(1, parents[0])
    assert replayed.value.code == "technical_projection_group_v2_parent_replayed"
    _assert_member_poisoned(group)

    # 來源 clock 即使有自洽 SHA，也不能與已保存 parent 混配。
    wrong_builder = _builder(fixture)
    wrong_request = replace(request, source_clock_identity_sha256=_sha("other-clock"))
    wrong_group = DailyMarketTechnicalUniverseProjectionGroupV2(wrong_request)
    wrong_group.bind_to_builder(wrong_builder)
    with pytest.raises(Exception):
        _read_exact(fixture, wrong_builder)
    _assert_member_poisoned(wrong_group)

    # KDJ member 中途故障後，MA 不能利用先前已留住的內部參考單獨 finalize。
    failure_builder = _builder(fixture)
    failure_request = _source_request(fixture, failure_builder)
    failure_group = DailyMarketTechnicalUniverseProjectionGroupV2(failure_request)
    failure_group.bind_to_builder(failure_builder)
    held_member = failure_group._ma_collector
    kdj_calls = 0

    def fail_kdj(
        self: Any,
        segment: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        nonlocal kdj_calls
        kdj_calls += 1
        raise RuntimeError("synthetic KDJ member failure")

    with monkeypatch.context() as patcher:
        patcher.setattr(DailyMarketTechnicalKDJProjectionCollectorV1, "consume_verified_snapshot", fail_kdj)
        with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as member_failure:
            _read_exact(fixture, failure_builder)
    assert member_failure.value.code == "technical_universe_v4_parent_verified_callback_failed"
    assert isinstance(member_failure.value.__cause__, RuntimeError)
    assert "synthetic KDJ member failure" in str(member_failure.value.__cause__)
    assert kdj_calls == 1
    _assert_member_poisoned(failure_group)
    with pytest.raises(Exception):
        held_member.finalize_verified_publication(
            failure_builder, object(), object(), object()
        )

    # 取消發生在 MA callback 返回後、KDJ callback 前，不得留 MA partial。
    cancel_builder = _builder(fixture)
    cancel_request = _source_request(fixture, cancel_builder)
    cancel_event = threading.Event()
    cancel_group = DailyMarketTechnicalUniverseProjectionGroupV2(
        cancel_request,
        cancel_callback=cancel_event.is_set,
    )
    cancel_group.bind_to_builder(cancel_builder)
    kdj_after_cancel: list[str] = []

    def cancel_after_ma(
        self: Any,
        segment: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        original_ma(self, segment, snapshot, parent_row)
        cancel_event.set()

    def observe_kdj_after_cancel(
        self: Any,
        segment: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        kdj_after_cancel.append("called")
        original_kdj(self, segment, snapshot, parent_row)

    with monkeypatch.context() as patcher:
        patcher.setattr(DailyMarketTechnicalMaAlignmentVerifiedCollectorV1, "consume_verified_snapshot", cancel_after_ma)
        patcher.setattr(DailyMarketTechnicalKDJProjectionCollectorV1, "consume_verified_snapshot", observe_kdj_after_cancel)
        with pytest.raises(Exception):
            _read_exact(fixture, cancel_builder)
    assert kdj_after_cancel == []
    _assert_member_poisoned(cancel_group)

    # 累積 byte budget 包含三份最終 compact entries；超限後沒有部分可讀資料。
    budget_builder = _builder(fixture)
    budget_group = DailyMarketTechnicalUniverseProjectionGroupV2(
        _source_request(fixture, budget_builder),
        max_total_bytes=1,
    )
    budget_group.bind_to_builder(budget_builder)
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as budget_error:
        _read_exact(fixture, budget_builder)
    budget_cause: BaseException | None = budget_error.value.__cause__
    assert isinstance(budget_cause, DailyMarketTechnicalUniverseProjectionGroupV2Error)
    assert budget_cause.code == "technical_projection_group_v2_index_budget_exceeded"
    assert DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES == 3 * 64 * 1024 * 1024
    _assert_member_poisoned(budget_group)

