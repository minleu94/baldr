"""正式 F17 MA/KDJ/波動率群組發行器與既有讀取路徑的回歸驗證。"""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

import app_module.daily_market_technical_official_disposition_query_reader_v1 as f17_reader
import app_module.daily_market_technical_parent_v4_query as parent_query
import app_module.daily_market_technical_universe_projection_group_session_v2 as group_session_module
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryReaderV1Error,
    open_daily_market_technical_official_disposition_projection_group_session_v2,
    open_daily_market_technical_official_disposition_read_session_v1,
)
from app_module.daily_market_technical_universe_kdj_alignment_query_v1 import (
    DailyMarketTechnicalKDJProjectionCollectorV1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DailyMarketTechnicalMaAlignmentVerifiedCollectorV1,
)
from app_module.daily_market_technical_universe_projection_group_v2 import (
    DailyMarketTechnicalUniverseProjectionGroupV2,
    DailyMarketTechnicalUniverseProjectionGroupV2Error,
)
from app_module.daily_market_technical_universe_volatility_alignment_query_v1 import (
    DailyMarketTechnicalVolatilityProjectionCollectorV1,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Row,
)
from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
)
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
)
from app_module.daily_market_technical_universe_projection_group_session_v2 import (
    DailyMarketTechnicalUniverseProjectionGroupSessionV2,
    _prepare_and_issue_projection_group_session_v2,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4ReadSessionBuilder,
)
from app_module.rule_research_technical_parent_capture_v4 import (
    DailyMarketTechnicalParentCaptureV4VerifiedRead,
)
from test_daily_market_technical_official_disposition_bundle_v1 import (  # type: ignore[import-not-found]
    bundle_fixture,
)
from test_daily_market_technical_official_disposition_query_reader_v1 import (  # type: ignore[import-not-found]
    exact_p01_session,
    exact_query,
)


def _assert_frozen_tree(value: object, seen: set[int] | None = None) -> None:
    """Reject shallow-frozen candidates that contain any live mutable child."""
    visited = set() if seen is None else seen
    if id(value) in visited:
        return
    visited.add(id(value))
    if type(value) in (str, int, bool, bytes, Decimal, date, datetime) or value is None:
        return
    if isinstance(value, Enum):
        return
    if type(value) is tuple or type(value) is frozenset:
        for child in value:
            _assert_frozen_tree(child, visited)
        return
    assert is_dataclass(type(value)), f"unexpected mutable/non-value node: {type(value)!r}"
    params = getattr(type(value), "__dataclass_params__", None)
    assert params is not None and params.frozen, f"dataclass is not frozen: {type(value)!r}"
    for item in fields(value):
        _assert_frozen_tree(getattr(value, item.name), visited)


def _one_code_outer_query(
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    stock_code: str,
) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    # This is only the outer F17 query filter. It must not become the P01
    # source selection or the projection group's population denominator.
    return DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=exact_query.technical_query,
        decision_cutoff=exact_query.decision_cutoff,
        bundle_output_root=exact_query.bundle_output_root,
        bundle_identity_sha256=exact_query.bundle_identity_sha256,
        expected_manifest_sha256=exact_query.expected_manifest_sha256,
        market_assignment_pin_identity_sha256=(
            exact_query.market_assignment_pin_identity_sha256
        ),
        official_disposal_pin_identity_sha256=(
            exact_query.official_disposal_pin_identity_sha256
        ),
        row_scope_filter=exact_query.row_scope_filter,
        market_assignment_states=exact_query.market_assignment_states,
        official_disposal_states=exact_query.official_disposal_states,
        outer_stock_filter_mode="explicit_codes",
        outer_stock_codes=(stock_code,),
        sort_clauses=exact_query.sort_clauses,
    )


def _assert_loaded_formal_reader() -> None:
    module_dir = Path(__file__).resolve().parents[1] / "app_module"
    reader_path = Path(f17_reader.__file__).resolve()
    expected_path = module_dir / "daily_market_technical_official_disposition_query_reader_v1.py"
    assert reader_path == expected_path


def test_public_opener_issues_one_full_multi_parent_group_for_one_code_outer_filter(
    bundle_fixture: Any,
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_loaded_formal_reader()
    fixture = bundle_fixture
    query = _one_code_outer_query(exact_query, fixture.included_codes[0])
    # Rebuild through the canonical factory so identity covers the new outer
    # filter, while every source, cutoff, P01 query, and row condition is kept.
    assert query.technical_query is exact_query.technical_query
    assert query.decision_cutoff == exact_query.decision_cutoff
    assert query.bundle_output_root == exact_query.bundle_output_root
    assert query.bundle_identity_sha256 == exact_query.bundle_identity_sha256
    assert query.expected_manifest_sha256 == exact_query.expected_manifest_sha256
    assert query.market_assignment_pin_identity_sha256 == (
        exact_query.market_assignment_pin_identity_sha256
    )
    assert query.official_disposal_pin_identity_sha256 == (
        exact_query.official_disposal_pin_identity_sha256
    )
    assert query.row_scope_filter == exact_query.row_scope_filter
    assert query.market_assignment_states == exact_query.market_assignment_states
    assert query.official_disposal_states == exact_query.official_disposal_states
    assert query.sort_clauses == exact_query.sort_clauses
    assert query.query_identity_sha256 != exact_query.query_identity_sha256
    groups: list[DailyMarketTechnicalUniverseProjectionGroupV2] = []
    builders: list[DailyMarketTechnicalUniverseV4ReadSessionBuilder] = []
    exact_reads: list[tuple[object, ...]] = []
    row_builds: list[tuple[DailyMarketTechnicalFeatureSnapshotV4, DailyMarketTechnicalParentV4Row]] = []
    member_calls: dict[
        str,
        list[tuple[int, DailyMarketTechnicalFeatureSnapshotV4, DailyMarketTechnicalParentV4Row]],
    ] = {"ma": [], "kdj": [], "volatility": []}
    parent_ends: list[tuple[int, str, int]] = []
    group_issue_calls: list[object] = []

    original_bind_group = f17_reader._bind_projection_group
    original_read_exact = DailyMarketTechnicalOfficialDispositionBundleReaderV1.read_exact
    original_make_row = parent_query._make_row
    original_ma = DailyMarketTechnicalMaAlignmentVerifiedCollectorV1.consume_verified_snapshot
    original_kdj = DailyMarketTechnicalKDJProjectionCollectorV1.consume_verified_snapshot
    original_volatility = DailyMarketTechnicalVolatilityProjectionCollectorV1.consume_unqualified_snapshot
    original_parent_end = DailyMarketTechnicalUniverseProjectionGroupV2.end_verified_parent
    original_group_issue = group_session_module._prepare_and_issue_projection_group_session_v2

    def capture_group(*args: Any, **kwargs: Any) -> DailyMarketTechnicalUniverseProjectionGroupV2:
        builder = args[0]
        group = original_bind_group(*args, **kwargs)
        builders.append(builder)
        groups.append(group)
        return group

    def count_exact_read(self: Any, *args: Any, **kwargs: Any) -> Any:
        exact_reads.append(tuple(args))
        return original_read_exact(self, *args, **kwargs)

    def count_row(
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    ) -> DailyMarketTechnicalParentV4Row:
        row = original_make_row(snapshot)
        row_builds.append((snapshot, row))
        return row

    def record_ma(
        self: Any,
        segment_index: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        original_ma(self, segment_index, snapshot, row)
        member_calls["ma"].append((segment_index, snapshot, row))

    def record_kdj(
        self: Any,
        segment_index: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        original_kdj(self, segment_index, snapshot, row)
        member_calls["kdj"].append((segment_index, snapshot, row))

    def record_volatility(
        self: Any,
        segment_index: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        original_volatility(self, segment_index, snapshot, row)
        member_calls["volatility"].append((segment_index, snapshot, row))

    def record_parent_end(
        self: Any,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        original_parent_end(self, segment_index, parent_read)
        if not group_issue_calls:
            assert self.status == "between_parents"
        parent_ends.append((segment_index, self.status, self.completed_parent_count))

    def count_issue(*args: Any, **kwargs: Any) -> Any:
        group_issue_calls.append(args[0])
        return original_group_issue(*args, **kwargs)

    monkeypatch.setattr(f17_reader, "_bind_projection_group", capture_group)
    monkeypatch.setattr(DailyMarketTechnicalOfficialDispositionBundleReaderV1, "read_exact", count_exact_read)
    monkeypatch.setattr(parent_query, "_make_row", count_row)
    monkeypatch.setattr(DailyMarketTechnicalMaAlignmentVerifiedCollectorV1, "consume_verified_snapshot", record_ma)
    monkeypatch.setattr(DailyMarketTechnicalKDJProjectionCollectorV1, "consume_verified_snapshot", record_kdj)
    monkeypatch.setattr(DailyMarketTechnicalVolatilityProjectionCollectorV1, "consume_unqualified_snapshot", record_volatility)
    monkeypatch.setattr(DailyMarketTechnicalUniverseProjectionGroupV2, "end_verified_parent", record_parent_end)
    monkeypatch.setattr(group_session_module, "_prepare_and_issue_projection_group_session_v2", count_issue)

    session = open_daily_market_technical_official_disposition_projection_group_session_v2(query)
    issued = session.projection_group_session
    assert issued is not None
    assert session.ma_alignment_session is None
    assert len(groups) == len(builders) == 1
    assert len(exact_reads) == 1
    assert len(group_issue_calls) == 1
    assert tuple((index, status, completed) for index, status, completed in parent_ends) == (
        (0, "between_parents", 1),
        (1, "between_parents", 2),
    )

    # Keep the three relevant denominators distinct: the source has 258
    # declared, 257 included/processed and one excluded; the outer query asks
    # for one code; the group still publishes all 257 included source rows.
    p01 = session._technical_session
    state = p01._state
    counts = state.counts
    full_included_codes = tuple(
        code
        for segment_index in range(len(state.plan.segments))
        for code in state.plan.segment_cohort(segment_index).included_stock_codes
    )
    assert counts.declared_count == 258
    assert counts.included_count == 257
    assert counts.excluded_count == 1
    assert counts.processed_count == 257
    assert counts.pending_count == 0
    assert full_included_codes == fixture.included_codes
    # Selection/query identity is validated independently. The population
    # denominator comes from the verified-state plan and counts above.
    assert session._selection.selection_identity_sha256 == session.p01_selection_identity_sha256
    assert session._selection.query_spec_identity_sha256 == session.p01_query_spec_identity_sha256
    assert session.query.outer_stock_filter_mode == "explicit_codes"
    assert session.query.outer_stock_codes == (fixture.included_codes[0],)
    assert session.query.technical_query.page_size == 1
    assert len(issued.ma_index.entries) == 257
    assert len(issued.kdj_entries) == 257
    assert len(issued.volatility_entries) == 257
    assert tuple(item.stock_code for item in issued.ma_index.entries) == full_included_codes
    assert tuple(item.stock_code for item in issued.kdj_entries) == full_included_codes
    assert tuple(item.stock_code for item in issued.volatility_entries) == full_included_codes
    _assert_frozen_tree(issued.ma_index)
    _assert_frozen_tree(issued.kdj_entries)
    _assert_frozen_tree(issued.volatility_entries)

    # The normal public opener performs one exact BundleReader read and creates
    # each parent row once; the three observers receive the same snapshot/row
    # identities in the same full-population order.
    assert len(row_builds) == 257
    assert all(len(member_calls[name]) == 257 for name in member_calls)
    assert tuple(snapshot.stock_code for snapshot, _ in row_builds) == full_included_codes
    for ma_event, kdj_event, vol_event, built in zip(
        member_calls["ma"], member_calls["kdj"], member_calls["volatility"], row_builds,
        strict=True,
    ):
        assert ma_event[0] == kdj_event[0] == vol_event[0]
        assert ma_event[1] is kdj_event[1] is vol_event[1] is built[0]
        assert ma_event[2] is kdj_event[2] is vol_event[2] is built[1]

    # The issued object owns immutable prepared values. Replacing mutable live
    # collectors and the callback ledger cannot change its full-N views.
    saved_views = (issued.ma_index, issued.kdj_entries, issued.volatility_entries)
    group = groups[0]
    assert group._ma_collector._finished is True
    assert group._ma_collector._issued_session is None
    group._ma_collector._entries = []
    group._kdj_collector._entries = []
    group._volatility_collector._entries = []
    row_provenance = group._row_provenance
    saved_row_provenance = tuple(row_provenance)
    assert len(saved_row_provenance) == 257
    with pytest.raises(DailyMarketTechnicalUniverseProjectionGroupV2Error) as immutable_ledger:
        group._row_provenance = []
    assert immutable_ledger.value.code == "technical_projection_group_v2_members_immutable"
    assert group._row_provenance is row_provenance
    assert tuple(row_provenance) == saved_row_provenance
    row_provenance.clear()
    assert group._row_provenance is row_provenance
    assert row_provenance == []
    seen_parent_identities = group._seen_parent_identities
    assert len(seen_parent_identities) == 2
    group._seen_parent_identities.clear()
    assert group._seen_parent_identities is seen_parent_identities
    assert seen_parent_identities == set()
    assert issued.ma_index is saved_views[0]
    assert issued.kdj_entries is saved_views[1]
    assert issued.volatility_entries is saved_views[2]

    # Changing the outer conditions would need a new exact-open so the group
    # remains anchored to this query and source verification.
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error) as conditions:
        session.with_conditions(row_scope_filter=())
    assert conditions.value.code == "technical_official_query_reader_v1_projection_group_session_conditions_require_exact_reopen"

    # Duplicate issue is a named rejection, while the already issued view
    # remains usable and the lifecycle group is not poisoned.
    prepared = issued._anchor.prepared
    with pytest.raises(DailyMarketTechnicalUniverseProjectionGroupV2Error) as duplicate:
        _prepare_and_issue_projection_group_session_v2(
            group,
            group._bound_builder,
            prepared.ma.bundle_state,
            prepared.ma.base_query,
            prepared.ma.selection,
            outer_query=query,
        )
    assert duplicate.value.code == "technical_projection_group_session_already_issued"
    assert not group._failed
    assert issued.ma_index is saved_views[0]

    # There is no public transport decoder or initializer that can reproduce
    # the reader-issued object from its fields.
    assert not hasattr(DailyMarketTechnicalUniverseProjectionGroupSessionV2, "from_dict")
    assert not hasattr(DailyMarketTechnicalUniverseProjectionGroupSessionV2, "from_json")
    with pytest.raises(TypeError):
        replace(issued)
    with pytest.raises(TypeError):
        replace(issued, _anchor=object())

    group._poison()
    for getter in (lambda: issued.ma_index, lambda: issued.kdj_entries, lambda: issued.volatility_entries):
        with pytest.raises(Exception) as poisoned:
            getter()
        assert poisoned.value.code == "technical_projection_group_session_poisoned_or_not_reader_issued"


def test_cancel_after_prepare_before_group_issue_poisoned_without_session(
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups: list[DailyMarketTechnicalUniverseProjectionGroupV2] = []
    original_bind_group = f17_reader._bind_projection_group
    original_prepare = group_session_module._prepare_projection_group_v2
    cancel_state = {"cancelled": False}

    def capture_group(*args: Any, **kwargs: Any) -> DailyMarketTechnicalUniverseProjectionGroupV2:
        group = original_bind_group(*args, **kwargs)
        groups.append(group)
        return group

    def cancel_after_prepare(*args: Any, **kwargs: Any) -> Any:
        prepared = original_prepare(*args, **kwargs)
        cancel_state["cancelled"] = True
        return prepared

    monkeypatch.setattr(f17_reader, "_bind_projection_group", capture_group)
    monkeypatch.setattr(group_session_module, "_prepare_projection_group_v2", cancel_after_prepare)
    with pytest.raises(DailyMarketTechnicalUniverseProjectionGroupV2Error) as cancelled:
        open_daily_market_technical_official_disposition_projection_group_session_v2(
            exact_query,
            cancel_callback=lambda: cancel_state["cancelled"],
        )
    assert cancelled.value.code == "technical_projection_group_v2_cancelled"
    assert len(groups) == 1
    group = groups[0]
    assert group._failed
    assert group._ma_collector._finished is True
    assert group._ma_collector._issued_session is None
    assert group._ma_collector._entries == []


@pytest.mark.parametrize(
    ("member_name", "phase"),
    (
        ("ma", "begin"),
        ("ma", "consume"),
        ("ma", "end"),
        ("kdj", "begin"),
        ("kdj", "consume"),
        ("kdj", "end"),
        ("volatility", "begin"),
        ("volatility", "consume"),
        ("volatility", "end"),
    ),
)
def test_public_opener_callback_failure_poisoned_without_group_session(
    member_name: str,
    phase: str,
    bundle_fixture: Any,
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del bundle_fixture
    targets = {
        ("ma", "begin"): (DailyMarketTechnicalMaAlignmentVerifiedCollectorV1, "begin_verified_parent"),
        ("ma", "consume"): (DailyMarketTechnicalMaAlignmentVerifiedCollectorV1, "consume_verified_snapshot"),
        ("ma", "end"): (DailyMarketTechnicalMaAlignmentVerifiedCollectorV1, "end_verified_parent"),
        ("kdj", "begin"): (DailyMarketTechnicalKDJProjectionCollectorV1, "begin_verified_parent"),
        ("kdj", "consume"): (DailyMarketTechnicalKDJProjectionCollectorV1, "consume_verified_snapshot"),
        ("kdj", "end"): (DailyMarketTechnicalKDJProjectionCollectorV1, "end_verified_parent"),
        ("volatility", "begin"): (DailyMarketTechnicalVolatilityProjectionCollectorV1, "begin_unqualified_segment"),
        ("volatility", "consume"): (DailyMarketTechnicalVolatilityProjectionCollectorV1, "consume_unqualified_snapshot"),
        ("volatility", "end"): (DailyMarketTechnicalVolatilityProjectionCollectorV1, "end_unqualified_segment"),
    }
    member_class, method_name = targets[(member_name, phase)]
    groups: list[DailyMarketTechnicalUniverseProjectionGroupV2] = []
    callback_hits: list[str] = []
    original_bind_group = f17_reader._bind_projection_group
    original_issue = group_session_module._prepare_and_issue_projection_group_session_v2
    issue_calls: list[object] = []

    def capture_group(*args: Any, **kwargs: Any) -> DailyMarketTechnicalUniverseProjectionGroupV2:
        group = original_bind_group(*args, **kwargs)
        groups.append(group)
        return group

    def fail_callback(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        callback_hits.append(f"{member_name}:{phase}")
        raise RuntimeError(f"injected {member_name} {phase} callback failure")

    def count_issue(*args: Any, **kwargs: Any) -> Any:
        issue_calls.append(args[0])
        return original_issue(*args, **kwargs)

    monkeypatch.setattr(f17_reader, "_bind_projection_group", capture_group)
    monkeypatch.setattr(member_class, method_name, fail_callback)
    monkeypatch.setattr(group_session_module, "_prepare_and_issue_projection_group_session_v2", count_issue)
    with pytest.raises(Exception):
        open_daily_market_technical_official_disposition_projection_group_session_v2(exact_query)

    assert callback_hits == [f"{member_name}:{phase}"]
    assert issue_calls == []
    assert len(groups) == 1
    group = groups[0]
    assert group._failed
    assert group._ma_collector._finished is True
    assert group._ma_collector._issued_session is None
    assert group._ma_collector._observations == []
    assert group._ma_collector._entries == []
    assert group._kdj_collector._failed
    assert group._kdj_collector._entries == []
    assert group._volatility_collector._entries == []
    assert group._row_provenance == []


def test_public_opener_issuer_rejects_envelope_over_cap_after_prepare(
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups: list[DailyMarketTechnicalUniverseProjectionGroupV2] = []
    prepared_values: list[object] = []
    original_bind_group = f17_reader._bind_projection_group
    original_prepare = group_session_module._prepare_projection_group_v2

    def capture_group(*args: Any, **kwargs: Any) -> DailyMarketTechnicalUniverseProjectionGroupV2:
        group = original_bind_group(*args, **kwargs)
        groups.append(group)
        return group

    def prepare_then_tighten_issue_budget(*args: Any, **kwargs: Any) -> Any:
        prepared = original_prepare(*args, **kwargs)
        group = args[0]
        prepared_values.append(prepared)
        # The candidate has already passed prepare. The test then reduces only
        # the issuer envelope allowance to force its independent final check.
        group._max_total_bytes = prepared.total_canonical_payload_bytes
        return prepared

    monkeypatch.setattr(f17_reader, "_bind_projection_group", capture_group)
    monkeypatch.setattr(
        group_session_module,
        "_prepare_projection_group_v2",
        prepare_then_tighten_issue_budget,
    )
    with pytest.raises(DailyMarketTechnicalUniverseProjectionGroupV2Error) as over_cap:
        open_daily_market_technical_official_disposition_projection_group_session_v2(exact_query)

    assert over_cap.value.code == "technical_projection_group_session_payload_limit"
    assert len(prepared_values) == 1
    assert len(groups) == 1
    group = groups[0]
    assert group._failed
    assert group._ma_collector._finished is True
    assert group._ma_collector._issued_session is None
    assert group._ma_collector._entries == []
    assert group._kdj_collector._entries == []
    assert group._volatility_collector._entries == []


def test_existing_default_opener_remains_ma_only(
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_group_bind(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("legacy opener must not construct or bind the projection group")

    monkeypatch.setattr(f17_reader, "_bind_projection_group", unexpected_group_bind)
    session = open_daily_market_technical_official_disposition_read_session_v1(exact_query)
    assert session.projection_group_session is None
    assert session.ma_alignment_session is not None


def test_legacy_openers_do_not_import_group_runtime_dependencies_in_fresh_process(tmp_path: Path) -> None:
    """Import and stubbed legacy read paths must stay free of group-only modules."""
    script = r'''
import builtins
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

private_root = Path(sys.argv[1]).resolve()
repo_root = Path(sys.argv[2]).resolve()
os.environ["DATA_ROOT"] = str(private_root / "data")
os.environ["OUTPUT_ROOT"] = str(private_root / "output")
os.environ["TEMP"] = str(private_root / "temp")
os.environ["TMP"] = str(private_root / "temp")
os.environ["TMPDIR"] = str(private_root / "temp")
for name in (
    "FORMAL_DAILY_RUNTIME_CONFIG",
    "FORMAL_DAILY_RUNTIME_CONFIG_ROOT",
    "FORMAL_DAILY_ROLLING_CALENDAR_BUNDLE",
    "FORMAL_DAILY_PORTFOLIO_CLOCK_MANIFEST",
):
    os.environ.pop(name, None)
missing_binding = private_root / "missing-formal-runtime-environment.json"
os.environ["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"] = str(missing_binding)
assert not missing_binding.exists()

watched = (
    "app_module.daily_market_technical_universe_projection_group_session_v2",
    "app_module.daily_market_technical_universe_projection_group_v2",
    "app_module.daily_market_technical_universe_projection_group_prepare_v2",
    "app_module.daily_market_technical_universe_kdj_alignment_query_v1",
    "app_module.daily_market_technical_universe_volatility_alignment_query_v1",
)
attempts = []
original_import = builtins.__import__
def import_spy(name, *args, **kwargs):
    if any(name == prefix or name.startswith(prefix + ".") for prefix in watched):
        attempts.append(name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = import_spy

import app_module.daily_market_technical_official_disposition_query_reader_v1 as reader
reader_path = Path(reader.__file__).resolve()
assert reader_path == repo_root / "app_module" / "daily_market_technical_official_disposition_query_reader_v1.py"

root = "qa-bundle-root"
bundle_id = "a" * 64
manifest_sha = "b" * 64
reference = SimpleNamespace(
    output_root=root,
    bundle_identity_sha256=bundle_id,
    manifest_sha256=manifest_sha,
)
manifest = {
    "technical_store": {"source_clock": {"stub": True}},
    "source_pins": {"market_assignment": {}, "official_disposal": {}},
}
bundle_state = SimpleNamespace(reference=reference, manifest=manifest)
metadata = SimpleNamespace(
    output_root=root,
    bundle_identity_sha256=bundle_id,
    manifest_sha256=manifest_sha,
)

class VerifiedSession:
    def create_query(self, **kwargs):
        return object()

class Builder:
    verified_session = None

builder = Builder()
builder.verified_session = VerifiedSession()
class BundleReader:
    def __init__(self, output_root):
        self.output_root = output_root
    def read_manifest_metadata(self, *args, **kwargs):
        return metadata
    def read_exact(self, *args, **kwargs):
        return bundle_state

class Pin:
    @classmethod
    def from_dict(cls, value):
        return SimpleNamespace(identity_sha256="c" * 64)

parsed_query = SimpleNamespace(
    technical_query=object(),
    bundle_output_root=root,
    bundle_identity_sha256=bundle_id,
    expected_manifest_sha256=manifest_sha,
)
marker = object()
reader._parse_query = lambda value: parsed_query
reader._technical_session_builder_from_query = lambda *args, **kwargs: builder
reader._technical_session_builder_from_manifest_metadata = lambda *args, **kwargs: builder
reader.DailyMarketTechnicalOfficialDispositionBundleReaderV1 = BundleReader
reader._bind_ma_projection = lambda *args, **kwargs: object()
reader.daily_market_technical_source_clock_v4_from_dict = lambda value: SimpleNamespace(
    decision_cutoff=datetime(2026, 10, 9, tzinfo=timezone.utc)
)
reader.CurrentMarketAssignmentSourcePinV1 = Pin
reader.CurrentOfficialDisposalSourcePinV1 = Pin
class QueryFactory:
    @staticmethod
    def create(**kwargs):
        return parsed_query
reader.DailyMarketTechnicalOfficialDispositionQueryV1 = QueryFactory
def issue(*args, **kwargs):
    assert kwargs.get("projection_group") is None
    return marker
reader._issue_session_from_verified_bundle = issue

assert reader.open_daily_market_technical_official_disposition_read_session_v1("stub") is marker
assert reader.open_daily_market_technical_official_disposition_bundle_session_v1(
    bundle_output_root=root,
    bundle_identity_sha256=bundle_id,
    expected_manifest_sha256=manifest_sha,
    row_scope_filter=(),
) is marker
assert attempts == [], attempts
assert not any(name in sys.modules for name in watched)
'''
    completed = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", "-c", script, str(tmp_path), str(Path(__file__).resolve().parents[1])],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
