"""V3 月營收封存研究資料夾的固定 layout 與路徑守衛反例。"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import cast

import pytest

from app_module.daily_market_technical_official_disposition_revenue_archived_storage_v3 import (
    ArchivedRevenueResearchStorageV3Error,
    prepare_archived_revenue_research_storage_v3,
    read_archived_revenue_binding_source_roots_v3,
)
from data_module.daily_monthly_revenue_cohort_binding import (
    DAILY_MONTHLY_REVENUE_COHORT_BINDING_SCHEMA,
)
from data_module.daily_monthly_revenue_cohort import (
    build_daily_monthly_revenue_cohort_pin,
    write_daily_monthly_revenue_cohort_pin_create_only,
)
from data_module.daily_monthly_revenue_series import (
    DailyMonthlyRevenueSeriesMarketTrustV1,
    DailyMonthlyRevenueSeriesTrustV1,
)
from data_module.daily_monthly_revenue_series_binding import (
    serialize_daily_monthly_revenue_series_binding_v1,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DailySourceSnapshotFileReader,
    DailySourceUseAcceptance,
    DailySourceUseScope,
)
from tests.test_daily_monthly_revenue_series import _write_market_batch


_CHILD_NAMES = (
    "monthly-references.v3",
    "raw-archives.v2",
    "archive-references.v4",
)


def _neutral_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "formal-data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "formal-output"))
    monkeypatch.delenv("PERSONAL_DATA_ROOT", raising=False)
    monkeypatch.delenv("PERSONAL_STORE_ROOT", raising=False)


def _child_paths(root: Path) -> tuple[Path, Path, Path]:
    return (
        root / _CHILD_NAMES[0],
        root / _CHILD_NAMES[1],
        root / _CHILD_NAMES[2],
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _acceptance(market: str) -> DailySourceUseAcceptance:
    return DailySourceUseAcceptance(
        scope=DailySourceUseScope(
            dataset_id="fundamental_current_observations.monthly_revenue",
            source_id="mops.monthly_revenue_static_snapshot",
            market=market,
            parser_version="mops-current-revenue-normalizer.v2",
            source_schema_version="mops-static-snapshot.v2",
            unit="TWD",
            intended_use="recommendation_current_fundamental",
        ),
        acceptance_id=f"synthetic-mops-current-{market}-v1",
        accepted_at=datetime.fromisoformat("2026-10-01T08:00:00+08:00"),
        official_source_endpoint="https://mops.twse.com.tw/mops/web/t05st10_ifrs",
        document_chain=(
            "synthetic-test-evidence",
            "https://mops.twse.com.tw/mops/web/t05st10_ifrs",
        ),
        acceptance_evidence_ref="test-fixture:explicit-trusted-acceptance",
        authorization_scope="recommendation_current_fundamental only",
        time_basis_policy=DAILY_SOURCE_TIME_BASIS_POLICY,
    )


def _acceptance_dict(market: str) -> dict[str, object]:
    return _acceptance(market).to_dict()


def _write_binding(path: Path, document: dict[str, object]) -> tuple[bytes, str]:
    raw = _canonical(document)
    path.write_bytes(raw)
    return raw, _sha256(raw)


def _cohort_document(
    pin_root: Path,
    market_roots: tuple[tuple[str, Path], ...],
    cohort_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MONTHLY_REVENUE_COHORT_BINDING_SCHEMA,
        "cohort_pin_root": str(pin_root),
        "cohort_sha256": cohort_sha256,
        "markets": [
            {
                "market": market,
                "snapshot_root": str(root),
                "trusted_acceptance": _acceptance_dict(market),
            }
            for market, root in market_roots
        ],
    }


def _cohort_binding_fixture(
    root: Path,
    markets: tuple[str, ...],
) -> tuple[Path, bytes, Path, tuple[tuple[str, Path], ...], str]:
    pin_root = root / "cohort-pins"
    pin_root.mkdir()
    readers: dict[str, DailySourceSnapshotFileReader] = {}
    batch_ids: dict[str, str] = {}
    market_roots: list[tuple[str, Path]] = []
    for index, market in enumerate(markets):
        snapshot_root = root / f"daily-{market}"
        batch_id = f"storage-binding-{market}-v1"
        readers[market], _ = _write_market_batch(
            snapshot_root,
            market,
            batch_id=batch_id,
            body_hour=10 + index,
        )
        batch_ids[market] = batch_id
        market_roots.append((market, snapshot_root))
    pin = build_daily_monthly_revenue_cohort_pin(
        period="2026-04",
        required_markets=markets,
        batch_ids=batch_ids,
        readers=readers,
    )
    write_daily_monthly_revenue_cohort_pin_create_only(pin_root, pin)
    document = _cohort_document(
        pin_root,
        tuple(market_roots),
        pin.cohort_sha256,
    )
    binding_path = root / "cohort-binding.json"
    payload, binding_sha256 = _write_binding(binding_path, document)
    return binding_path, payload, pin_root, tuple(market_roots), binding_sha256


def _series_binding_fixture(root: Path) -> tuple[Path, bytes, tuple[Path, ...]]:
    pin_root = root / "pins"
    twse_root = root / "daily-twse"
    tpex_root = root / "daily-tpex"
    catalog_root = root / "catalog"
    for directory in (pin_root, twse_root, tpex_root, catalog_root):
        directory.mkdir(parents=True)
    trust = DailyMonthlyRevenueSeriesTrustV1(
        cohort_pin_root=pin_root,
        market_sources=(
            DailyMonthlyRevenueSeriesMarketTrustV1(
                "twse", twse_root, _acceptance("twse")
            ),
            DailyMonthlyRevenueSeriesMarketTrustV1(
                "tpex", tpex_root, _acceptance("tpex")
            ),
        ),
    )
    pointer_path = catalog_root / "current.json"
    payload = serialize_daily_monthly_revenue_series_binding_v1(
        trust=trust,
        catalog_root=catalog_root,
        pointer_path=pointer_path,
    )
    binding_path = root / "series-binding.json"
    binding_path.write_bytes(payload)
    return binding_path, payload, (pin_root, catalog_root, twse_root, tpex_root)


def test_prepare_reuses_existing_children_without_changing_saved_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _neutral_environment(tmp_path, monkeypatch)
    root = tmp_path / "research"
    root.mkdir()
    children = _child_paths(root)
    for child in children:
        child.mkdir()
    saved = children[0] / "existing-recipe.json"
    original = b'{"saved":true}\n'
    saved.write_bytes(original)
    operation_parent = tmp_path / "operations"
    operation_parent.mkdir()

    layout = prepare_archived_revenue_research_storage_v3(
        root,
        protected_roots=(tmp_path / "config-data", tmp_path / "config-output", tmp_path / "provider"),
        source_roots=(tmp_path / "daily-twse", tmp_path / "daily-tpex", tmp_path / "f17-bundle"),
        operation_root_parent=operation_parent,
    )

    assert layout.root == root
    assert layout.monthly_reference_artifact_root == children[0]
    assert layout.raw_archive_parent == children[1]
    assert layout.archived_reference_artifact_root == children[2]
    assert saved.read_bytes() == original


@pytest.mark.parametrize("overlap", ("formal", "source", "operation"))
def test_rejects_overlapping_roots_before_creating_any_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overlap: str,
) -> None:
    _neutral_environment(tmp_path, monkeypatch)
    root = tmp_path / "research"
    root.mkdir()
    children = _child_paths(root)
    protected = (tmp_path / "config-data",)
    sources: tuple[Path, ...] = ()
    operation_parent: Path | None = None
    if overlap == "formal":
        # 此正式 root 尚不存在；不能因 missing 而略過字面重疊檢查。
        monkeypatch.setenv("DATA_ROOT", str(root / "future-formal-data"))
    elif overlap == "source":
        sources = (root / "future-source-root",)
    else:
        operation_parent = root

    with pytest.raises(ArchivedRevenueResearchStorageV3Error):
        prepare_archived_revenue_research_storage_v3(
            root,
            protected_roots=protected,
            source_roots=sources,
            operation_root_parent=operation_parent,
        )

    assert all(not child.exists() for child in children)


def test_rejects_a_child_file_collision_before_creating_sibling_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _neutral_environment(tmp_path, monkeypatch)
    root = tmp_path / "research"
    root.mkdir()
    children = _child_paths(root)
    original = b"do not replace"
    children[0].write_bytes(original)

    with pytest.raises(ArchivedRevenueResearchStorageV3Error, match="child_0_must_be_directory"):
        prepare_archived_revenue_research_storage_v3(root, protected_roots=(tmp_path / "formal",))

    assert children[0].read_bytes() == original
    assert not children[1].exists()
    assert not children[2].exists()


def test_rejects_a_reparse_child_without_creating_other_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _neutral_environment(tmp_path, monkeypatch)
    root = tmp_path / "research"
    root.mkdir()
    children = _child_paths(root)
    target = tmp_path / "source-target"
    target.mkdir()
    try:
        children[1].symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"此環境無法建立 symlink/reparse 測試 fixture：{exc}")

    with pytest.raises(ArchivedRevenueResearchStorageV3Error, match="reparse_or_component_invalid"):
        prepare_archived_revenue_research_storage_v3(root, protected_roots=(tmp_path / "formal",))

    assert children[1].is_symlink()
    assert not children[0].exists()
    assert not children[2].exists()


@pytest.mark.parametrize("bad_root", (False, 1.25, b"C:/not-a-path"))
def test_rejects_bool_float_and_bytes_storage_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_root: object,
) -> None:
    _neutral_environment(tmp_path, monkeypatch)
    with pytest.raises(ArchivedRevenueResearchStorageV3Error, match="storage_root_type_invalid"):
        prepare_archived_revenue_research_storage_v3(
            cast(Path | str, bad_root), protected_roots=(tmp_path / "formal",)
        )


@pytest.mark.parametrize("bad_root", (False, 1.25, b"C:/not-a-root"))
def test_rejects_untyped_protected_roots_before_creating_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_root: object,
) -> None:
    _neutral_environment(tmp_path, monkeypatch)
    root = tmp_path / "research"
    root.mkdir()
    with pytest.raises(ArchivedRevenueResearchStorageV3Error, match="protected_root_0_must_be_path"):
        prepare_archived_revenue_research_storage_v3(
            root, protected_roots=(cast(Path, bad_root),)
        )
    assert all(not child.exists() for child in _child_paths(root))


def test_rejects_noncanonical_alias_path_without_creating_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _neutral_environment(tmp_path, monkeypatch)
    root = tmp_path / "research"
    root.mkdir()
    alias = root / ".." / "research" / "source"
    with pytest.raises(ArchivedRevenueResearchStorageV3Error, match="source_root_0_must_be_absolute_normal"):
        prepare_archived_revenue_research_storage_v3(
            root,
            protected_roots=(tmp_path / "formal",),
            source_roots=(alias,),
        )
    assert all(not child.exists() for child in _child_paths(root))


@pytest.mark.parametrize("markets", (("twse",), ("tpex",), ("twse", "tpex")))
def test_cohort_binding_metadata_returns_declared_roots_without_opening_snapshots(
    tmp_path: Path,
    markets: tuple[str, ...],
) -> None:
    binding_path, payload, pin_root, market_roots, digest = _cohort_binding_fixture(
        tmp_path, markets
    )
    before = tuple(
        (root, tuple(sorted(path.name for path in root.iterdir())))
        for _, root in market_roots
    )

    roots = read_archived_revenue_binding_source_roots_v3(
        binding_path,
        expected_binding_sha256=digest,
    )

    assert roots == (pin_root, *(item[1] for item in market_roots))
    assert binding_path.read_bytes() == payload
    after = tuple(
        (root, tuple(sorted(path.name for path in root.iterdir())))
        for _, root in market_roots
    )
    assert after == before


def test_series_binding_metadata_does_not_read_mutable_pointer_or_catalog(
    tmp_path: Path,
) -> None:
    binding_path, payload, expected_roots = _series_binding_fixture(tmp_path)

    roots = read_archived_revenue_binding_source_roots_v3(
        binding_path,
        expected_binding_sha256=_sha256(payload),
    )

    assert roots == expected_roots
    assert not (tmp_path / "catalog" / "current.json").exists()
    assert tuple((tmp_path / "catalog").iterdir()) == ()
    assert all(tuple(root.iterdir()) == () for root in expected_roots)


def test_binding_root_reader_rejects_wrong_external_hash_before_parsing(
    tmp_path: Path,
) -> None:
    binding_path, _, _, _, digest = _cohort_binding_fixture(
        tmp_path, ("twse",)
    )

    with pytest.raises(ArchivedRevenueResearchStorageV3Error, match="external_hash_mismatch"):
        read_archived_revenue_binding_source_roots_v3(
            binding_path,
            expected_binding_sha256="0" * 64 if digest != "0" * 64 else "1" * 64,
        )


@pytest.mark.parametrize(
    "mutation,reason",
    (
        ("schema", "binding_schema_unsupported"),
        ("missing_pin_root", "cohort_binding_fields_invalid"),
        ("duplicate_market", "cohort_binding_market_1_identity_invalid"),
        ("too_many_markets", "cohort_binding_required_markets_invalid"),
        ("relative_root", "snapshot_root_twse_not_canonical"),
    ),
)
def test_cohort_binding_metadata_rejects_bad_schema_roots_and_market_sets(
    tmp_path: Path,
    mutation: str,
    reason: str,
) -> None:
    binding_path, payload, _, _, _ = _cohort_binding_fixture(
        tmp_path, ("twse", "tpex")
    )
    document = json.loads(payload.decode("utf-8"))
    assert isinstance(document, dict)
    if mutation == "schema":
        document["schema_version"] = "daily-monthly-revenue-cohort-binding.v9"
    elif mutation == "missing_pin_root":
        document.pop("cohort_pin_root")
    elif mutation == "duplicate_market":
        raw_markets = document["markets"]
        assert isinstance(raw_markets, list)
        raw_markets[1] = dict(raw_markets[0])
    elif mutation == "too_many_markets":
        raw_markets = document["markets"]
        assert isinstance(raw_markets, list)
        raw_markets.append(dict(raw_markets[0]))
    else:
        raw_markets = document["markets"]
        assert isinstance(raw_markets, list)
        first_market = raw_markets[0]
        assert isinstance(first_market, dict)
        first_market["snapshot_root"] = "relative/daily-twse"
    _, digest = _write_binding(binding_path, document)

    with pytest.raises(ArchivedRevenueResearchStorageV3Error, match=reason):
        read_archived_revenue_binding_source_roots_v3(
            binding_path,
            expected_binding_sha256=digest,
        )


def test_binding_root_reader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    pin_root = tmp_path / "pins"
    snapshot_root = tmp_path / "daily-twse"
    pin_root.mkdir()
    snapshot_root.mkdir()
    raw = (
        b'{"schema_version":"daily-monthly-revenue-cohort-binding.v1",'
        b'"schema_version":"daily-monthly-revenue-cohort-binding.v1"}'
    )
    binding_path = tmp_path / "duplicate-binding.json"
    binding_path.write_bytes(raw)

    with pytest.raises(ArchivedRevenueResearchStorageV3Error, match="duplicate_key"):
        read_archived_revenue_binding_source_roots_v3(
            binding_path,
            expected_binding_sha256=_sha256(raw),
        )


def test_series_binding_root_reader_rejects_incomplete_required_market_pair(
    tmp_path: Path,
) -> None:
    binding_path, payload, _ = _series_binding_fixture(tmp_path)
    document = json.loads(payload.decode("utf-8"))
    trust = document["trust"]
    assert isinstance(trust, dict)
    trust["required_markets"] = ["twse"]
    bad_payload = _canonical(document)
    binding_path.write_bytes(bad_payload)

    with pytest.raises(ArchivedRevenueResearchStorageV3Error, match="series_trust_markets_invalid"):
        read_archived_revenue_binding_source_roots_v3(
            binding_path,
            expected_binding_sha256=_sha256(bad_payload),
        )


def test_series_binding_metadata_rejects_unsupported_exact_schema(
    tmp_path: Path,
) -> None:
    binding_path, payload, _ = _series_binding_fixture(tmp_path)
    document = json.loads(payload.decode("utf-8"))
    document["schema_version"] = "daily-monthly-revenue-series-binding.v2"
    bad_payload = _canonical(document)
    binding_path.write_bytes(bad_payload)

    with pytest.raises(ArchivedRevenueResearchStorageV3Error, match="binding_schema_unsupported"):
        read_archived_revenue_binding_source_roots_v3(
            binding_path,
            expected_binding_sha256=_sha256(bad_payload),
        )


def test_cohort_source_roots_may_share_path_and_return_canonical_deduped_roots(
    tmp_path: Path,
) -> None:
    binding_path, payload, pin_root, market_roots, digest = _cohort_binding_fixture(
        tmp_path, ("twse",)
    )
    document = json.loads(payload.decode("utf-8"))
    assert isinstance(document, dict)
    markets = document["markets"]
    assert isinstance(markets, list)
    market = markets[0]
    assert isinstance(market, dict)
    market["snapshot_root"] = str(pin_root)
    _, changed_digest = _write_binding(binding_path, document)

    roots = read_archived_revenue_binding_source_roots_v3(
        binding_path,
        expected_binding_sha256=changed_digest,
    )

    assert roots == (pin_root,)
    assert market_roots[0][1] not in roots


def test_binding_root_reader_rejects_hardlinked_binding_file(
    tmp_path: Path,
) -> None:
    binding_path, _, _, _, digest = _cohort_binding_fixture(
        tmp_path, ("twse",)
    )
    linked_path = tmp_path / "second-name.json"
    try:
        os.link(binding_path, linked_path)
    except OSError as exc:
        pytest.skip(f"此環境無法建立 hardlink 測試 fixture：{exc}")

    with pytest.raises(ArchivedRevenueResearchStorageV3Error, match="hardlinks"):
        read_archived_revenue_binding_source_roots_v3(
            binding_path,
            expected_binding_sha256=digest,
        )
