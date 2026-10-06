from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tracemalloc
from typing import Any

import pytest

from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION,
    DAILY_MARKET_FEATURE_KEYS,
)
from app_module.daily_market_method_contract import (
    method_contracts_payload,
    method_contracts_sha256,
)
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_LEGACY_MANIFEST_SCHEMA,
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
    canonical_snapshot_json_bytes,
    cohort_identity_sha256,
    snapshot_manifest_identity_sha256,
    snapshot_manifest_relpath,
)
import app_module.research_membership_history_index as history_index
from app_module.research_membership_history_index import (
    MAX_MEMBERSHIP_HISTORY_GENERATION_BYTES,
    MAX_MEMBERSHIP_HISTORY_PAGE_JSON_BYTES,
    MAX_MEMBERSHIP_HISTORY_PAGE_MANIFEST_BYTES,
    MembershipHistoryIndexError,
    read_membership_history_page,
    rebuild_membership_history_index,
    rollback_membership_history_index,
)


COHORT = "history-index-test-cohort"
UTC = timezone.utc
TAIPEI = timezone(timedelta(hours=8))


def _manifest_bytes(
    decision_date: date,
    published_at: datetime,
    *,
    schema_version: str = DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
) -> bytes:
    manifest: dict[str, Any] = {
        "schema_version": schema_version,
        "manifest_identity_sha256": "0" * 64,
        "cohort_id": COHORT,
        "cohort_identity": cohort_identity_sha256(COHORT, ["2330"]),
        "declared_stock_codes": ["2330"],
        "decision_date": decision_date.isoformat(),
        "decision_cutoff": datetime.combine(
            decision_date, time(16, 0), tzinfo=TAIPEI
        ).isoformat(),
        "decision_timezone": "Asia/Taipei",
        "feature_contract_version": DAILY_MARKET_FEATURE_CONTRACT_VERSION,
        "feature_keys": list(DAILY_MARKET_FEATURE_KEYS),
        "method_contracts": method_contracts_payload(),
        "method_contracts_sha256": method_contracts_sha256(),
        "stocks": [],
        "missing_stocks": [{"stock_code": "2330", "reason": "source_unavailable"}],
        "counts": {"declared": 1, "published": 0, "missing": 1},
        "completeness": "partial_research",
        "published_at": published_at.astimezone(UTC).isoformat(),
        "policy": {"research_only": True, "historical_pit_eligible": False},
    }
    if schema_version == DAILY_MARKET_SNAPSHOT_LEGACY_MANIFEST_SCHEMA:
        # 這個最小 payload 用來測索引版本閘門；repository 明確拒絕不相容的 v1。
        manifest["manifest_identity_sha256"] = snapshot_manifest_identity_sha256(manifest)
    else:
        manifest["manifest_identity_sha256"] = snapshot_manifest_identity_sha256(manifest)
    return canonical_snapshot_json_bytes(manifest)


def _write_manifest(
    source: Path,
    decision_date: date,
    published_at: datetime,
    *,
    schema_version: str = DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
) -> str:
    raw = _manifest_bytes(decision_date, published_at, schema_version=schema_version)
    digest = hashlib.sha256(raw).hexdigest()
    path = source / Path(snapshot_manifest_relpath(digest))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return digest


def _write_history(source: Path, *, days: int, revisions: int = 1) -> list[tuple[date, str]]:
    rows: list[tuple[date, str]] = []
    start = date(2024, 1, 1)
    for day_offset in range(days):
        decision_date = start + timedelta(days=day_offset)
        for revision in range(revisions):
            published_at = datetime.combine(
                decision_date, time(12, 0), tzinfo=UTC
            ) + timedelta(seconds=revision)
            digest = _write_manifest(source, decision_date, published_at)
            rows.append((decision_date, digest))
    return rows


def _read_page(
    source: Path,
    cache: Path,
    pin_hash: str,
    pin_date: date,
    *,
    cursor: str | None = None,
    page_size: int = 32,
    cohort: str = COHORT,
    as_of: datetime | None = None,
):
    return read_membership_history_page(
        source,
        cache,
        cohort=cohort,
        as_of=as_of or datetime(2035, 1, 1, tzinfo=UTC),
        current_pin=pin_hash,
        date_to=pin_date,
        page_size=page_size,
        cursor=cursor,
    )


def _active_pointer(cache: Path) -> bytes:
    return (cache / "active.json").read_bytes()


def test_rebuild_pages_full_history_and_preserves_same_date_revisions(tmp_path: Path):
    source = tmp_path / "snapshot-root"
    cache = tmp_path / "history-cache"
    rows = _write_history(source, days=130, revisions=2)
    result = rebuild_membership_history_index(source, cache)

    assert result.manifest_count == 260
    assert result.index_size_bytes <= MAX_MEMBERSHIP_HISTORY_GENERATION_BYTES
    assert result.retained_generation_count == 1
    assert result.retained_generation_bytes == result.index_size_bytes
    assert result.activated is True

    pin_date, pin_hash = rows[-1]
    cursor = None
    actual: list[str] = []
    pages = []
    while True:
        page = _read_page(source, cache, pin_hash, pin_date, cursor=cursor)
        pages.append(page)
        actual.extend(ref.manifest_sha256 for ref in page.refs)
        assert len(page.refs) <= 32
        assert page.history_coverage == ("truncated" if page.has_more else "complete")
        assert len(json.dumps(page.to_dict(), separators=(",", ":"))) <= MAX_MEMBERSHIP_HISTORY_PAGE_JSON_BYTES
        if not page.has_more:
            break
        assert page.next_cursor
        cursor = page.next_cursor

    expected = [digest for _day, digest in rows]
    assert set(actual) == set(expected)
    assert len(actual) == len(set(actual)) == 260
    for page in pages:
        page_keys = [
            (ref.decision_date, ref.published_at, ref.manifest_sha256)
            for ref in page.refs
        ]
        assert page_keys == sorted(page_keys)
    assert len(pages) == 9
    # 每日兩個 revision 都應可獨立尋址。
    assert pages[0].refs[-1].decision_date == pin_date
    assert sum(ref.decision_date == pin_date for page in pages for ref in page.refs) == 2


def test_cursor_is_query_and_generation_bound_and_tamper_evident(tmp_path: Path):
    source = tmp_path / "source"
    cache = tmp_path / "cache"
    rows = _write_history(source, days=4)
    rebuild_membership_history_index(source, cache)
    pin_date, pin_hash = rows[-1]
    first = _read_page(source, cache, pin_hash, pin_date, page_size=2)
    assert first.has_more and first.next_cursor

    with pytest.raises(MembershipHistoryIndexError) as invalid:
        _read_page(source, cache, pin_hash, pin_date, cursor=first.next_cursor + "x", page_size=2)
    assert invalid.value.reason == "invalid_cursor"

    with pytest.raises(MembershipHistoryIndexError) as changed_query:
        _read_page(
            source,
            cache,
            pin_hash,
            pin_date,
            cursor=first.next_cursor,
            page_size=3,
        )
    assert changed_query.value.reason == "invalid_cursor"

    with pytest.raises(MembershipHistoryIndexError) as changed_as_of:
        _read_page(
            source,
            cache,
            pin_hash,
            pin_date,
            cursor=first.next_cursor,
            page_size=2,
            as_of=datetime(2036, 1, 1, tzinfo=UTC),
        )
    assert changed_as_of.value.reason == "invalid_cursor"


def test_source_directory_change_invalidates_page_without_fallback(tmp_path: Path):
    source = tmp_path / "source"
    cache = tmp_path / "cache"
    rows = _write_history(source, days=3)
    rebuild_membership_history_index(source, cache)
    pin_date, pin_hash = rows[-1]
    (source / "manifests" / ("f" * 64 + ".json")).write_text("{}", encoding="utf-8")

    with pytest.raises(MembershipHistoryIndexError) as changed:
        _read_page(source, cache, pin_hash, pin_date)
    assert changed.value.reason == "source_changed"


@pytest.mark.parametrize(
    ("schema_version", "expected_reason"),
    [
        (DAILY_MARKET_SNAPSHOT_LEGACY_MANIFEST_SCHEMA, "unsupported_manifest_schema"),
        ("future-manifest.v99", "unsupported_manifest_schema"),
    ],
)
def test_unknown_or_legacy_manifest_schema_fails_closed_and_keeps_pointer(
    tmp_path: Path,
    schema_version: str,
    expected_reason: str,
):
    source = tmp_path / "source"
    cache = tmp_path / "cache"
    _write_history(source, days=1)
    rebuild_membership_history_index(source, cache)
    pointer_before = _active_pointer(cache)
    _write_manifest(source, date(2024, 2, 1), datetime(2024, 2, 1, 12, tzinfo=UTC), schema_version=schema_version)

    with pytest.raises(MembershipHistoryIndexError) as rejected:
        rebuild_membership_history_index(source, cache)
    assert rejected.value.reason == expected_reason
    assert _active_pointer(cache) == pointer_before


def test_empty_source_and_missing_index_are_distinct(tmp_path: Path):
    source = tmp_path / "empty-source"
    cache = tmp_path / "empty-cache"
    (source / "manifests").mkdir(parents=True)
    with pytest.raises(MembershipHistoryIndexError) as empty:
        rebuild_membership_history_index(source, cache)
    assert empty.value.reason == "empty"

    missing_cache = tmp_path / "missing-cache"
    with pytest.raises(MembershipHistoryIndexError) as missing:
        read_membership_history_page(
            source,
            missing_cache,
            cohort=COHORT,
            as_of=datetime(2035, 1, 1, tzinfo=UTC),
            current_pin="0" * 64,
        )
    assert missing.value.reason == "missing"


def test_cancel_and_activation_fault_preserve_completed_generation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "source"
    cache = tmp_path / "cache"
    rows = _write_history(source, days=5)
    initial = rebuild_membership_history_index(source, cache)
    pointer_before = _active_pointer(cache)

    calls = 0

    def cancel_after_scan_starts() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 2

    with pytest.raises(MembershipHistoryIndexError) as cancelled:
        rebuild_membership_history_index(source, cache, cancel_check=cancel_after_scan_starts)
    assert cancelled.value.reason == "cancelled"
    assert _active_pointer(cache) == pointer_before

    def fail_pointer(_cache_root: Path, _record: Any) -> None:
        raise MembershipHistoryIndexError("partial_update", "injected pointer failure")

    monkeypatch.setattr(history_index, "_write_active_pointer", fail_pointer)
    with pytest.raises(MembershipHistoryIndexError) as failed:
        rebuild_membership_history_index(source, cache)
    assert failed.value.reason == "partial_update"
    assert _active_pointer(cache) == pointer_before

    monkeypatch.undo()
    pin_date, pin_hash = rows[-1]
    page = _read_page(source, cache, pin_hash, pin_date)
    assert page.generation_id == initial.generation_id


def test_rollback_only_activates_a_generation_for_unchanged_source(tmp_path: Path):
    source = tmp_path / "source"
    cache = tmp_path / "cache"
    rows = _write_history(source, days=3)
    first = rebuild_membership_history_index(source, cache)
    second = rebuild_membership_history_index(source, cache)
    assert second.generation_id != first.generation_id

    rolled = rollback_membership_history_index(source, cache, generation_id=first.generation_id)
    assert rolled.generation_id == first.generation_id
    assert json.loads(_active_pointer(cache))["generation_id"] == first.generation_id

    pin_date, pin_hash = rows[-1]
    assert _read_page(source, cache, pin_hash, pin_date).generation_id == first.generation_id

    pointer_before = _active_pointer(cache)
    _write_manifest(source, date(2024, 2, 1), datetime(2024, 2, 1, 12, tzinfo=UTC))
    with pytest.raises(MembershipHistoryIndexError) as changed:
        rollback_membership_history_index(source, cache, generation_id=second.generation_id)
    assert changed.value.reason == "source_changed"
    assert _active_pointer(cache) == pointer_before


def test_corrupt_pointer_and_generation_are_distinguished(tmp_path: Path):
    source = tmp_path / "source"
    cache = tmp_path / "cache"
    rows = _write_history(source, days=2)
    result = rebuild_membership_history_index(source, cache)
    pin_date, pin_hash = rows[-1]
    pointer = json.loads(_active_pointer(cache))
    pointer["schema_version"] = "research-membership-history-index-pointer.v99"
    (cache / "active.json").write_text(json.dumps(pointer), encoding="utf-8")
    with pytest.raises(MembershipHistoryIndexError) as unknown_pointer:
        _read_page(source, cache, pin_hash, pin_date)
    assert unknown_pointer.value.reason == "unsupported_index_schema"

    pointer["schema_version"] = history_index.POINTER_SCHEMA_VERSION
    (cache / "active.json").write_text(json.dumps(pointer), encoding="utf-8")
    generation_path = result.index_path
    generation_path.write_bytes(generation_path.read_bytes() + b"tamper")
    with pytest.raises(MembershipHistoryIndexError) as corrupted:
        _read_page(source, cache, pin_hash, pin_date)
    assert corrupted.value.reason == "corrupt"


def test_same_size_generation_tamper_with_restored_mtime_fails_full_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "source"
    cache = tmp_path / "cache"
    rows = _write_history(source, days=2)
    result = rebuild_membership_history_index(source, cache)
    pin_date, pin_hash = rows[-1]
    index_path = result.index_path
    original_stat = index_path.stat()
    corrupted = bytearray(index_path.read_bytes())
    corrupted[-1] ^= 0x01
    index_path.write_bytes(corrupted)
    os.utime(index_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    restored_stat = index_path.stat()
    assert restored_stat.st_size == original_stat.st_size
    assert restored_stat.st_mtime_ns == original_stat.st_mtime_ns

    opened_database = False
    original_connect = history_index._connect_readonly

    def record_database_open(path: Path):
        nonlocal opened_database
        opened_database = True
        return original_connect(path)

    monkeypatch.setattr(history_index, "_connect_readonly", record_database_open)
    with pytest.raises(MembershipHistoryIndexError) as rejected:
        _read_page(source, cache, pin_hash, pin_date)
    assert rejected.value.reason == "corrupt"
    assert not opened_database


def test_cache_path_cannot_be_source_or_nested_under_source(tmp_path: Path):
    source = tmp_path / "source"
    _write_history(source, days=1)
    with pytest.raises(MembershipHistoryIndexError) as same_path:
        rebuild_membership_history_index(source, source)
    assert same_path.value.reason == "unsafe_cache_path"
    with pytest.raises(MembershipHistoryIndexError) as nested_path:
        rebuild_membership_history_index(source, source / "derived-cache")
    assert nested_path.value.reason == "unsafe_cache_path"
    assert set(path.name for path in (source / "manifests").iterdir()) == {
        next((source / "manifests").iterdir()).name
    }


def test_page_resource_reads_are_bounded_and_do_not_load_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "source"
    cache = tmp_path / "cache"
    rows = _write_history(source, days=96, revisions=2)
    built = rebuild_membership_history_index(source, cache)
    pin_date, pin_hash = rows[-1]

    hashed_files: list[tuple[Path, int]] = []
    manifest_reads: list[tuple[Path, int]] = []
    original_sha = history_index._sha256_file
    original_manifest_read = history_index._read_manifest_json

    def record_sha(path: Path, *, cancel_check: Any = None) -> str:
        hashed_files.append((path, path.stat().st_size))
        return original_sha(path, cancel_check=cancel_check)

    def record_manifest(path_root: Path, path: Path) -> tuple[bytes, dict[str, Any]]:
        value = original_manifest_read(path_root, path)
        manifest_reads.append((path, len(value[0])))
        return value

    monkeypatch.setattr(history_index, "_sha256_file", record_sha)
    monkeypatch.setattr(history_index, "_read_manifest_json", record_manifest)
    tracemalloc.start()
    try:
        page = _read_page(source, cache, pin_hash, pin_date)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert len(page.refs) == 32
    assert len(hashed_files) == 1
    assert hashed_files[0][0] == built.index_path
    assert hashed_files[0][1] == built.index_size_bytes <= MAX_MEMBERSHIP_HISTORY_GENERATION_BYTES
    assert len(manifest_reads) <= 33
    assert sum(size for _path, size in manifest_reads) <= MAX_MEMBERSHIP_HISTORY_PAGE_MANIFEST_BYTES
    assert len(json.dumps(page.to_dict(), separators=(",", ":"))) <= MAX_MEMBERSHIP_HISTORY_PAGE_JSON_BYTES
    assert peak < 16 * 1024 * 1024
    # Fixture 只含 manifest refs，讀頁不需要也不會載入 snapshot object。
    assert not list(source.rglob("objects"))
