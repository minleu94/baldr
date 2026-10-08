"""F17 metadata catalog 僅列 manifest，選取後走既有 exact reader。"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Callable
from uuid import uuid4

import pytest

import app_module.daily_market_technical_official_disposition_bundle_v1 as bundle_module
import app_module.daily_market_technical_official_disposition_bundle_catalog_v1 as catalog_module
from app_module.daily_market_technical_official_disposition_bundle_catalog_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_LIMIT,
    DailyMarketTechnicalOfficialDispositionBundleCatalogCancelled,
    DailyMarketTechnicalOfficialDispositionBundleCatalogError,
    DailyMarketTechnicalOfficialDispositionBundleCatalogV1,
)
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleError,
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4StoreReader,
)
from data_module.selection_market_assignments import CurrentMarketAssignmentReader
from data_module.selection_official_events import CurrentOfficialDisposalReader
from test_daily_market_technical_official_disposition_bundle_v1 import (  # type: ignore[import-not-found]
    bundle_fixture,
)


def _copy_manifest_root(fixture: Any, label: str) -> tuple[Path, Path]:
    root = fixture.qa_root / f"catalog-{label}-{uuid4().hex}"
    manifests = root / "manifests"
    manifests.mkdir(parents=True, exist_ok=False)
    source = fixture.bundle_root / fixture.reference.manifest_relative_path
    target = manifests / source.name
    shutil.copyfile(source, target)
    return root, target


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _add_metadata_only_variant(manifests: Path, source_raw: bytes, label: str) -> Path:
    payload = json.loads(source_raw.decode("utf-8"))
    body = deepcopy(payload)
    body.pop("bundle_identity_sha256")
    body["source_coverage_status"] = "partial"
    coverage = body["source_coverage"]
    coverage["incomplete_reasons"].append(f"catalog metadata variant {label}")
    identity = hashlib.sha256(_canonical_json(body)).hexdigest()
    candidate = {**body, "bundle_identity_sha256": identity}
    target = manifests / f"{identity}.json"
    target.write_bytes(_canonical_json(candidate))
    return target


def test_catalog_lists_real_bundle_as_unverified_without_reading_sources_or_rows(
    bundle_fixture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = bundle_fixture
    reads: list[Path] = []
    original_read = bundle_module._read_bounded_regular_file

    def manifest_only_read(
        path: Path,
        limit: int,
        code: str,
        *,
        expected_link_count: int = 1,
    ) -> bytes:
        path_value = Path(path)
        reads.append(path_value)
        assert path_value.parent.name == "manifests"
        return original_read(
            path,
            limit,
            code,
            expected_link_count=expected_link_count,
        )

    def forbid_full_read(*args: object, **kwargs: object) -> object:
        raise AssertionError("catalog_must_not_open_exact_sources_or_row_shards")

    monkeypatch.setattr(bundle_module, "_read_bounded_regular_file", manifest_only_read)
    monkeypatch.setattr(DailyMarketTechnicalOfficialDispositionBundleReaderV1, "read_exact", forbid_full_read)
    monkeypatch.setattr(DailyMarketTechnicalUniverseV4StoreReader, "read_exact_with_verified_parent_callback", forbid_full_read)
    monkeypatch.setattr(CurrentMarketAssignmentReader, "from_exact", forbid_full_read)
    monkeypatch.setattr(CurrentOfficialDisposalReader, "from_exact", forbid_full_read)

    page = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(fixture.bundle_root).list_page()

    assert page.scan_complete is True
    assert page.has_more is False
    assert page.next_cursor is None
    assert len(page.entries) == 1
    entry = page.entries[0]
    assert entry.metadata_state == "metadata_unverified"
    assert entry.can_attempt_exact_read is True
    assert entry.bundle_identity_sha256 == fixture.reference.bundle_identity_sha256
    assert entry.manifest_sha256 == fixture.reference.manifest_sha256
    assert entry.metadata is not None
    assert entry.metadata.row_count == 258
    assert entry.metadata.declared_count == 258
    assert entry.metadata.included_count == 257
    assert entry.metadata.excluded_count == 1
    assert entry.metadata.saved_scope_label == "current_only"
    assert entry.metadata.saved_historical_pit_eligible_label is False
    assert entry.metadata.saved_official_available_at_label is None
    assert "清單只檢查 manifest" in page.scan_cost_notice
    assert reads == [fixture.bundle_root / fixture.reference.manifest_relative_path]


def test_metadata_candidate_exact_open_matches_the_true_258_row_bundle_reference(
    bundle_fixture: Any,
) -> None:
    fixture = bundle_fixture
    page = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(fixture.bundle_root).list_page()
    candidate = page.entries[0].metadata
    assert candidate is not None
    assert candidate.metadata_state == "metadata_unverified"

    state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(fixture.bundle_root).read_exact(
        candidate.bundle_identity_sha256,
        expected_manifest_sha256=candidate.manifest_sha256,
    )

    assert state.reference == fixture.reference
    assert len(tuple(state.iter_verified_rows())) == 258


def test_exact_reader_rejects_old_candidate_sha_after_manifest_bytes_drift(
    bundle_fixture: Any,
) -> None:
    fixture = bundle_fixture
    root, target = _copy_manifest_root(fixture, "sha-drift")
    candidate = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page().entries[0].metadata
    assert candidate is not None
    with open(target, "ab") as stream:
        stream.write(b" ")
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as raised:
        DailyMarketTechnicalOfficialDispositionBundleReaderV1(root).read_exact(
            candidate.bundle_identity_sha256,
            expected_manifest_sha256=candidate.manifest_sha256,
        )
    assert raised.value.code == "manifest_bytes_sha_mismatch"


def test_cursor_binds_complete_manifest_inventory_and_rejects_drift(
    bundle_fixture: Any,
) -> None:
    fixture = bundle_fixture
    root, original = _copy_manifest_root(fixture, "cursor-stale")
    raw = original.read_bytes()
    _add_metadata_only_variant(original.parent, raw, "first")
    catalog = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root)
    first = catalog.list_page(limit=1)
    assert first.scan_complete is True
    assert first.has_more is True
    assert first.next_cursor is not None

    _add_metadata_only_variant(original.parent, raw, "second")
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleCatalogError) as raised:
        catalog.list_page(limit=1, cursor=first.next_cursor)
    assert raised.value.code == "catalog_cursor_stale"


@pytest.mark.parametrize(
    ("limit", "cursor"),
    [
        (-1, None),
        (0, None),
        (DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_LIMIT + 1, None),
        (DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT, "!invalid"),
    ],
)
def test_catalog_rejects_negative_or_invalid_page_inputs(
    bundle_fixture: Any,
    limit: int,
    cursor: str | None,
) -> None:
    catalog = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(bundle_fixture.bundle_root)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleCatalogError):
        catalog.list_page(limit=limit, cursor=cursor)


def test_catalog_final_cancel_poll_prevents_returning_completed_inventory(
    bundle_fixture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(bundle_fixture.bundle_root)
    original_scan = catalog._scan_inventory
    cancelled = False

    def scan_then_cancel(
        *,
        page_limit: int,
        after_relative_path: str | None,
        cancel_callback: Callable[[], bool] | None,
    ) -> object:
        nonlocal cancelled
        result = original_scan(
            page_limit=page_limit,
            after_relative_path=after_relative_path,
            cancel_callback=cancel_callback,
        )
        cancelled = True
        return result

    monkeypatch.setattr(catalog, "_scan_inventory", scan_then_cancel)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleCatalogCancelled) as raised:
        catalog.list_page(cancel_callback=lambda: cancelled)
    assert raised.value.code == "catalog_cancelled"


@pytest.mark.parametrize(
    ("callback", "expected_code"),
    [
        (lambda: 1, "cancel_callback_invalid"),
        (lambda: (_ for _ in ()).throw(RuntimeError("callback failure")), "cancel_callback_failed"),
    ],
)
def test_catalog_cancellation_callback_must_return_strict_bool(
    bundle_fixture: Any,
    callback: Callable[[], object],
    expected_code: str,
) -> None:
    catalog = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(bundle_fixture.bundle_root)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleCatalogError) as raised:
        catalog.list_page(cancel_callback=callback)  # type: ignore[arg-type]
    assert raised.value.code == expected_code


def test_catalog_hardlink_makes_inventory_incomplete_without_a_cursor(
    bundle_fixture: Any,
) -> None:
    fixture = bundle_fixture
    root, copied_manifest = _copy_manifest_root(fixture, "hardlink")
    linked_path = copied_manifest.with_name("f" * 64 + ".json")
    try:
        os.link(copied_manifest, linked_path)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"平台無法建立合成 hardlink：{type(error).__name__}")

    page = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page()

    assert page.scan_complete is False
    assert page.next_cursor is None
    assert page.has_more is None
    assert page.source_inventory_state == "inventory_incomplete"
    assert page.diagnostic_code in {
        "catalog_manifest_hardlink_rejected",
        "catalog_manifest_inventory_changed",
    }


def test_catalog_manifest_stat_drift_is_incomplete_and_never_pages(
    bundle_fixture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = bundle_fixture
    root, manifest_path = _copy_manifest_root(fixture, "stat-drift")
    reader_method = DailyMarketTechnicalOfficialDispositionBundleReaderV1.read_manifest_metadata

    def read_then_touch(
        reader: DailyMarketTechnicalOfficialDispositionBundleReaderV1,
        identity: str,
        *,
        expected_manifest_sha256: str | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> object:
        result = reader_method(
            reader,
            identity,
            expected_manifest_sha256=expected_manifest_sha256,
            cancel_callback=cancel_callback,
        )
        info = manifest_path.stat()
        os.utime(
            manifest_path,
            ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000),
        )
        return result

    monkeypatch.setattr(DailyMarketTechnicalOfficialDispositionBundleReaderV1, "read_manifest_metadata", read_then_touch)
    page = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page()
    assert page.scan_complete is False
    assert page.next_cursor is None
    assert page.diagnostic_code == "catalog_manifest_changed_during_inventory"


def test_catalog_aggregate_byte_budget_fails_closed_without_reading_candidate(
    bundle_fixture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = bundle_fixture
    root, manifest_path = _copy_manifest_root(fixture, "byte-budget")
    monkeypatch.setattr(
        catalog_module,
        "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_INVENTORY_BYTES",
        manifest_path.stat().st_size - 1,
    )

    def forbid_metadata(*args: object, **kwargs: object) -> object:
        raise AssertionError("over-budget manifest must not be read")

    monkeypatch.setattr(DailyMarketTechnicalOfficialDispositionBundleReaderV1, "read_manifest_metadata", forbid_metadata)
    page = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page()
    assert page.scan_complete is False
    assert page.next_cursor is None
    assert page.diagnostic_code == "catalog_inventory_byte_budget_exceeded"
    assert page.manifest_bytes_scanned == 0


def test_catalog_per_manifest_byte_cap_fails_closed_without_reading_candidate(
    bundle_fixture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = bundle_fixture
    root, _manifest_path = _copy_manifest_root(fixture, "manifest-byte-cap")
    monkeypatch.setattr(
        catalog_module,
        "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES",
        1,
    )

    def forbid_metadata(*args: object, **kwargs: object) -> object:
        raise AssertionError("over-limit manifest must not be read")

    monkeypatch.setattr(DailyMarketTechnicalOfficialDispositionBundleReaderV1, "read_manifest_metadata", forbid_metadata)
    page = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page()
    assert page.scan_complete is False
    assert page.next_cursor is None
    assert page.diagnostic_code == "catalog_manifest_byte_limit"


def test_catalog_entry_budget_fails_closed_without_claiming_more_pages(
    bundle_fixture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = bundle_fixture
    root, original = _copy_manifest_root(fixture, "entry-budget")
    _add_metadata_only_variant(original.parent, original.read_bytes(), "budget")
    monkeypatch.setattr(
        catalog_module,
        "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_ENTRIES",
        1,
    )
    page = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page()
    assert page.scan_complete is False
    assert page.next_cursor is None
    assert page.has_more is None
    assert page.diagnostic_code == "catalog_entry_budget_exceeded"
