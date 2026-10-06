from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
from importlib import import_module
import importlib.util
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from typing import Any, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app_module.daily_market_research_screener import (
    DailyMarketResearchCancelled,
    DailyMarketResearchScreenerService,
)
from app_module.daily_market_research_bookmark import create_daily_market_research_bookmark
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_LEGACY_MANIFEST_SCHEMA,
    DailyMarketSnapshotVerificationError,
    canonical_snapshot_json_bytes,
    snapshot_manifest_relpath,
)
from app_module.research_membership_history_index import MembershipHistoryIndexError
from app_module.research_membership_lifecycle import HistoryCoverage, LifecycleStatus

_LIFECYCLE_FIXTURES = import_module("test_research_membership_lifecycle_read_model")
CONDITION_KEYS = cast(tuple[str, ...], getattr(_LIFECYCLE_FIXTURES, "CONDITION_KEYS"))
TAIPEI: Any = getattr(_LIFECYCLE_FIXTURES, "TAIPEI")


def _service(
    source_root: Path,
    index_root: Path,
    *,
    sessions: object | None = None,
) -> DailyMarketResearchScreenerService:
    return DailyMarketResearchScreenerService(
        SimpleNamespace(db_file=source_root.parent / "fixture-market.sqlite"),
        snapshot_root=source_root,
        history_index_root=index_root,
        membership_session_provider=cast(Any, sessions),
    )


def _write_snapshot(root: Path, decision_date: date, **values: Any):
    writer = getattr(_LIFECYCLE_FIXTURES, "_write_snapshot")
    return writer(root, decision_date, **values)


def _verified_sessions(previous: dict[date, date | None]) -> Any:
    factory = getattr(_LIFECYCLE_FIXTURES, "_VerifiedSessions")
    return factory(previous)


def _weekdays(first_day: date, count: int) -> tuple[date, ...]:
    result: list[date] = []
    cursor = first_day
    while len(result) < count:
        if cursor.weekday() < 5:
            result.append(cursor)
        cursor += timedelta(days=1)
    return tuple(result)


def _sessions(days: tuple[date, ...]) -> Any:
    previous = {
        day: days[position - 1] if position else None
        for position, day in enumerate(days)
    }
    return _verified_sessions(previous)


def _snapshot_archive(root: Path, count: int = 3):
    days = _weekdays(date(2026, 10, 5), count)
    current = None
    for day in days:
        current = _write_snapshot(root, day, matches=True)
    assert current is not None
    return days, current


def _reason(error: pytest.ExceptionInfo[MembershipHistoryIndexError]) -> str:
    return error.value.reason


def test_missing_index_uses_read_only_legacy_lifecycle_and_history_requires_explicit_rebuild(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "snapshots"
    index_root = tmp_path / "derived-index"
    days, current = _snapshot_archive(source_root)
    sessions = _sessions(days)
    service = _service(source_root, index_root, sessions=sessions)

    legacy = service.read_membership_lifecycle(current, CONDITION_KEYS, "AND")
    assert legacy.history_coverage is HistoryCoverage.COMPLETE
    assert legacy.rows_by_stock["2382"].status is LifecycleStatus.CONTINUING
    assert not index_root.exists(), "legacy read must not create an index"

    with pytest.raises(MembershipHistoryIndexError) as missing:
        service.read_membership_history_page(current, stock_code="2382")
    assert _reason(missing) == "missing"
    assert not index_root.exists(), "page failure must not trigger implicit rebuild"

    built = service.rebuild_membership_history_index()
    assert built.activated and built.manifest_count == len(days)
    assert index_root.exists()


def test_long_indexed_archive_is_bounded_and_keeps_saved_condition_states_not_events(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "snapshots"
    index_root = tmp_path / "derived-index"
    days, current = _snapshot_archive(source_root, 35)
    service = _service(source_root, index_root, sessions=_sessions(days))
    built = service.rebuild_membership_history_index()

    page = service.read_membership_history_page(
        current,
        page_size=32,
        condition_keys=CONDITION_KEYS,
        combine_mode="AND",
        stock_code="2382",
    )
    assert page.generation_id == built.generation_id
    assert page.current_manifest_sha256 == current.manifest_sha256
    assert page.research_only is True and page.historical_pit_eligible is False
    assert len(page.rows) == 32 and page.has_more and page.next_cursor
    assert {row.state for row in page.rows} == {"match"}
    assert all(row.state not in {"continued", "exited", "reentered"} for row in page.rows)

    older = service.read_membership_history_page(
        current,
        cursor=page.next_cursor,
        page_size=32,
        condition_keys=CONDITION_KEYS,
        combine_mode="AND",
        stock_code="2382",
    )
    assert older.generation_id == built.generation_id
    assert len(older.rows) == 3 and not older.has_more
    assert {row.state for row in older.rows} == {"match"}

    lifecycle = service.read_membership_lifecycle(current, CONDITION_KEYS, "AND")
    assert lifecycle.history_coverage is HistoryCoverage.TRUNCATED
    assert lifecycle.rows_by_stock["2382"].status is LifecycleStatus.CONTINUING


def test_rebuild_cancel_keeps_active_generation_and_explicit_rollback_is_reversible(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "snapshots"
    index_root = tmp_path / "derived-index"
    _days, current = _snapshot_archive(source_root, 5)
    service = _service(source_root, index_root)
    first = service.rebuild_membership_history_index()
    second = service.rebuild_membership_history_index()
    assert first.generation_id != second.generation_id
    assert first.index_path.exists() and second.index_path.exists()

    checks = 0

    def cancel_during_scan() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 4

    with pytest.raises(DailyMarketResearchCancelled):
        service.rebuild_membership_history_index(cancel_callback=cancel_during_scan)
    assert checks >= 4

    page_before = service.read_membership_history_page(current, stock_code="2382")
    assert page_before.generation_id == second.generation_id
    rolled_back = service.rollback_membership_history_index(first.generation_id)
    assert rolled_back.generation_id == first.generation_id
    page_after = service.read_membership_history_page(current, stock_code="2382")
    assert page_after.generation_id == first.generation_id

    active_before_source_change = (index_root / "active.json").read_bytes()
    new_day = _weekdays(_days[-1] + timedelta(days=1), 1)[0]
    _write_snapshot(source_root, new_day, matches=True)
    with pytest.raises(MembershipHistoryIndexError) as changed_rollback:
        service.rollback_membership_history_index(second.generation_id)
    assert _reason(changed_rollback) == "source_changed"
    assert (index_root / "active.json").read_bytes() == active_before_source_change


@pytest.mark.parametrize(
    "schema_version",
    [DAILY_MARKET_SNAPSHOT_LEGACY_MANIFEST_SCHEMA, "daily-market-snapshot-manifest.v999"],
)
def test_unknown_or_legacy_manifest_schema_fails_rebuild_without_switching_pointer(
    tmp_path: Path,
    schema_version: str,
) -> None:
    source_root = tmp_path / "snapshots"
    index_root = tmp_path / "derived-index"
    _days, current = _snapshot_archive(source_root, 2)
    service = _service(source_root, index_root)
    previous = service.rebuild_membership_history_index()
    pointer_path = index_root / "active.json"
    pointer_before = pointer_path.read_bytes()

    manifest = dict(current.manifest)
    manifest["schema_version"] = schema_version
    manifest_bytes = canonical_snapshot_json_bytes(manifest)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_path = source_root / snapshot_manifest_relpath(manifest_sha)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(manifest_bytes)

    with pytest.raises(MembershipHistoryIndexError) as unsupported:
        service.rebuild_membership_history_index()
    assert _reason(unsupported) == "unsupported_manifest_schema"
    assert json.loads(pointer_path.read_bytes()) == json.loads(pointer_before)
    assert previous.index_path.exists()


def test_unsupported_or_corrupt_index_fails_closed_in_service_without_legacy_fallback(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "snapshots"
    index_root = tmp_path / "derived-index"
    days, current = _snapshot_archive(source_root, 3)
    service = _service(source_root, index_root, sessions=_sessions(days))
    service.rebuild_membership_history_index()
    pointer_path = index_root / "active.json"
    pointer_before = pointer_path.read_bytes()

    pointer = json.loads(pointer_before)
    pointer["schema_version"] = "research-membership-history-index-pointer.v999"
    pointer_path.write_bytes(canonical_snapshot_json_bytes(pointer))
    with pytest.raises(MembershipHistoryIndexError) as unsupported:
        service.read_membership_history_page(current, stock_code="2382")
    assert _reason(unsupported) == "unsupported_index_schema"
    with pytest.raises(MembershipHistoryIndexError) as lifecycle_unsupported:
        service.read_membership_lifecycle(current, CONDITION_KEYS, "AND")
    assert _reason(lifecycle_unsupported) == "unsupported_index_schema"
    assert pointer_path.read_bytes() != pointer_before

    pointer_path.write_bytes(b"{")
    with pytest.raises(MembershipHistoryIndexError) as corrupt:
        service.read_membership_history_page(current, stock_code="2382")
    assert _reason(corrupt) == "corrupt"
    assert pointer_path.read_bytes() == b"{"

    pointer_path.write_bytes(pointer_before)
    page = service.read_membership_history_page(current, stock_code="2382")
    assert page.current_manifest_sha256 == current.manifest_sha256
    assert service.history_index_root.exists()


def test_history_page_rereads_pinned_objects_and_same_day_revisions_remain_distinct(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "snapshots"
    index_root = tmp_path / "derived-index"
    first_day, current_day = date(2026, 10, 5), date(2026, 10, 6)
    first_revision = _write_snapshot(
        source_root,
        first_day,
        matches=False,
        published_at=datetime(2026, 10, 5, 16, 0, tzinfo=TAIPEI),
    )
    visible_revision = _write_snapshot(
        source_root,
        first_day,
        matches=True,
        published_at=datetime(2026, 10, 5, 16, 30, tzinfo=TAIPEI),
    )
    current = _write_snapshot(source_root, current_day, matches=True)
    service = _service(
        source_root,
        index_root,
        sessions=_verified_sessions({first_day: None, current_day: first_day}),
    )
    service.rebuild_membership_history_index()

    page = service.read_membership_history_page(current, stock_code="2382")
    revisions = [row for row in page.rows if row.decision_date == first_day.isoformat()]
    assert {row.manifest_sha256 for row in revisions} == {
        first_revision.manifest_sha256,
        visible_revision.manifest_sha256,
    }
    assert {row.state for row in revisions} == {"no_match", "match"}
    lifecycle = service.read_membership_lifecycle(current, CONDITION_KEYS, "AND")
    assert lifecycle.rows_by_stock["2382"].status is LifecycleStatus.INCOMPARABLE

    record = next(item for item in first_revision.manifest["stocks"] if item["stock_code"] == "2382")
    artifact_path = source_root / record["artifact_relpath"]
    artifact_path.write_bytes(b"{\"changed\":true}")
    with pytest.raises(DailyMarketSnapshotVerificationError):
        service.read_membership_history_page(current, stock_code="2382")
    assert current.manifest_sha256 == page.current_manifest_sha256
    assert index_root.exists(), "a source-object fault must not rebuild or rewrite the pinned source"


def test_history_index_fault_preserves_existing_ma_bookmark_and_its_pinned_source(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "snapshots"
    index_root = tmp_path / "derived-index"
    _days, current = _snapshot_archive(source_root, 2)
    service = _service(source_root, index_root)
    row = service.filter_rows(current, CONDITION_KEYS, "AND")[0]
    bookmark = create_daily_market_research_bookmark(
        current,
        row,
        stock_name="fixture",
        filter_state="match",
    )
    original_bookmark = bookmark.to_dict()
    built = service.rebuild_membership_history_index()
    pointer_path = index_root / "active.json"
    pointer_path.write_bytes(b"{")

    with pytest.raises(MembershipHistoryIndexError) as failed_page:
        service.read_membership_history_page(current, stock_code=bookmark.stock_code)
    assert _reason(failed_page) == "corrupt"
    assert bookmark.to_dict() == original_bookmark

    pinned = service.repository.load_manifest(
        bookmark.source_snapshot_hash,
        bookmark.cohort_id,
        date.fromisoformat(bookmark.decision_date),
        expected_stock_codes=bookmark.declared_stock_codes,
    )
    assert pinned.manifest_sha256 == bookmark.source_snapshot_hash
    assert pinned.manifest_identity_sha256 == bookmark.source_snapshot_id
    assert built.index_path.exists()


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 is required for the real TaskWorker consumer check",
)
def test_real_view_taskworker_keeps_current_source_usable_and_rejects_stale_page(
    tmp_path: Path,
) -> None:
    from PySide6.QtWidgets import QApplication

    from ui_qt.views.daily_market_research_view import DailyMarketResearchView

    source_root = tmp_path / "snapshots"
    index_root = tmp_path / "derived-index"
    _days, current = _snapshot_archive(source_root, 4)
    service = _service(source_root, index_root)

    app = QApplication.instance() or QApplication([])
    view = DailyMarketResearchView(service)
    view._snapshot = current
    view._manifest_sha256 = current.manifest_sha256
    view._manifest_identity_sha256 = current.manifest_identity_sha256
    view._loaded_cohort_id = current.cohort_id
    view._loaded_decision_date = current.decision_date.isoformat()
    view._all_rows = service.filter_rows(current, CONDITION_KEYS, "AND")
    view._render_rows()
    view.results_table.selectRow(0)
    app.processEvents()
    assert view._history_stock_code() == "2382"

    view._request_history_page(reset=True)
    deadline = time.monotonic() + 3
    while view._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert view._worker is None
    assert view._snapshot is current
    assert view._history_page is None
    assert not index_root.exists(), "a UI page fault must not implicitly create an index"
    assert view.open_selected_stock_button.isEnabled()

    service.rebuild_membership_history_index()

    entered = threading.Event()
    release = threading.Event()
    worker_threads: list[int] = []
    real_reader = service.read_membership_history_page

    def gated_reader(snapshot, **query):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert release.wait(3)
        return real_reader(snapshot, **query)

    service.read_membership_history_page = gated_reader  # type: ignore[method-assign]
    ui_thread = threading.get_ident()
    view._request_history_page(reset=True)
    deadline = time.monotonic() + 2
    while not entered.is_set() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert entered.is_set()
    app.processEvents()
    assert worker_threads and worker_threads[0] != ui_thread
    assert view._snapshot is current
    assert view.open_selected_stock_button.isEnabled()
    assert view._history_page is None

    view.cancel_active_operation()
    release.set()
    deadline = time.monotonic() + 3
    while view._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert view._worker is None
    assert view._snapshot is current
    assert view._history_page is None
    assert "取消" in view.history_status_label.text()

    service.read_membership_history_page = real_reader  # type: ignore[method-assign]
    view._request_history_page(reset=True)
    deadline = time.monotonic() + 3
    while view._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert view._worker is None
    assert view._snapshot is current
    assert view._history_page is not None
    assert view.history_table.rowCount() == 4

    entered.clear()
    release.clear()
    service.read_membership_history_page = gated_reader  # type: ignore[method-assign]
    view._request_history_page(reset=True)
    deadline = time.monotonic() + 2
    while not entered.is_set() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert entered.is_set()
    view.ma20_checkbox.blockSignals(True)
    view.ma20_checkbox.setChecked(False)
    view.ma20_checkbox.blockSignals(False)
    release.set()
    deadline = time.monotonic() + 3
    while view._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert view._worker is None
    assert view._snapshot is current
    assert view._history_page is None, "a result for the prior query must be rejected"
    assert service.history_index_root.exists()
    view.close()
    app.processEvents()
