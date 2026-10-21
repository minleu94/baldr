from __future__ import annotations

import csv
from dataclasses import fields
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

import pytest

from app_module import theme_snapshot_catalog as catalog
from decision_module.industry_theme_map import ThemeMappingRow


_DATA_DATE = "2026-10-16"
_KNOWN_AT = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
_FIELDS = tuple(field.name for field in fields(ThemeMappingRow))


def _write_candidate(
    folder: Path,
    *,
    data_date: str = _DATA_DATE,
    saved_completed_at: str = "2026-10-17T06:05:12+00:00",
    schema: str = "baldr.theme_research_snapshot.v1",
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    mapping_path = folder / "map.csv"
    values = {
        "snapshot_date": data_date,
        "available_date": data_date,
        "stock_id": "2330",
        "stock_name": "台積電",
        "market_type": "上市",
        "l1_industry_category": "半導體",
        "chain_name": "半導體",
        "chain_tier": "中游",
        "theme_name": "晶圓製造",
        "is_primary": "true",
        "assignment_method": "catalog-test",
        "source_name": "catalog-fixture",
        "source_tier": "T1",
        "pit_mode": "quarterly_snapshot",
        "evidence_note": "synthetic test mapping",
    }
    with mapping_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerow(values)

    prices_path = folder / "prices.sqlite"
    with sqlite3.connect(prices_path) as connection:
        connection.execute('CREATE TABLE daily_prices ("證券代號" TEXT, "日期" TEXT)')
        connection.execute('INSERT INTO daily_prices VALUES (?, ?)', ("2330", data_date))

    manifest_path = folder / "any-name.json"
    manifest: dict[str, object] = {
        "schema": schema,
        "data_date": data_date,
        "saved_completed_at": saved_completed_at,
        "mapping": {"path": "map.csv", "sha256": _sha_file(mapping_path)},
        "prices": {"path": "prices.sqlite", "sha256": _sha_file(prices_path)},
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def _sha_file(path: Path) -> str:
    from hashlib import sha256

    return sha256(path.read_bytes()).hexdigest()


def test_latest_legal_uses_data_date_and_completion_clock_not_manifest_name_or_mtime(tmp_path: Path) -> None:
    root = tmp_path / "versions"
    older = _write_candidate(root / "older", data_date="2026-10-15")
    newer_earlier_completion = _write_candidate(
        root / "newer", data_date="2026-10-16", saved_completed_at="2026-10-17T05:00:00+00:00",
    )
    newer_later_completion = _write_candidate(
        root / "later", data_date="2026-10-16", saved_completed_at="2026-10-17T06:05:12+00:00",
    )
    os.utime(older, (1, 1))
    os.utime(newer_later_completion, (2, 2))

    result = catalog.resolve_latest_theme_research_snapshot(root, known_at=_KNOWN_AT)

    assert result.selected is not None
    assert result.selected.manifest_path == newer_later_completion.resolve()
    assert result.selected.data_date.isoformat() == "2026-10-16"
    assert result.selected.saved_completed_at.isoformat() == "2026-10-17T06:05:12+00:00"
    assert result.verified_count == 1
    assert result.unverified_candidate_count == 2
    assert result.limited is False
    assert older != newer_earlier_completion


def test_not_yet_available_newest_candidate_is_rejected_and_older_legal_is_selected(tmp_path: Path) -> None:
    root = tmp_path / "versions"
    available = _write_candidate(root / "available", data_date="2026-10-15")
    _write_candidate(
        root / "later", data_date="2026-10-16", saved_completed_at="2026-10-20T12:00:01+00:00",
    )

    result = catalog.resolve_latest_theme_research_snapshot(root, known_at=_KNOWN_AT)

    assert result.selected is not None
    assert result.selected.manifest_path == available.resolve()
    assert any("尚未到可用小時" in item.reason for item in result.rejections)


def test_manifest_identity_change_between_catalog_read_and_reader_is_rejected(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "versions"
    manifest = _write_candidate(root / "only")
    original_read = catalog._read_small_manifest

    def read_then_replace(path: Path) -> bytes:
        raw = original_read(path)
        payload = json.loads(raw)
        payload["saved_completed_at"] = "2026-10-17T07:05:12+00:00"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return raw

    monkeypatch.setattr(catalog, "_read_small_manifest", read_then_replace)

    result = catalog.resolve_latest_theme_research_snapshot(root, known_at=_KNOWN_AT)

    assert result.selected is None
    assert any("原保存身份SHA256不符" in item.reason for item in result.rejections)
    assert manifest.exists()


def test_empty_root_returns_empty_catalog_without_scanning_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()

    result = catalog.resolve_latest_theme_research_snapshot(root, known_at=_KNOWN_AT)

    assert result.entries == ()
    assert result.rejections == ()
    assert result.candidate_count == 0
    assert result.verified_count == 0
    assert result.unverified_candidate_count == 0
    assert result.limited is False


def test_symlinked_candidate_subtree_is_rejected_without_following_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    _write_candidate(outside / "candidate")
    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"此環境無法建立目錄symlink：{exc}")

    result = catalog.resolve_latest_theme_research_snapshot(root, known_at=_KNOWN_AT)

    assert result.selected is None
    assert result.candidate_count == 0
    assert any(item.path == link for item in result.rejections)


def test_default_price_schema_does_not_fall_back_to_flow_only_manifest(tmp_path: Path) -> None:
    root = tmp_path / "versions"
    price = _write_candidate(root / "price")
    flow = _write_candidate(root / "flow", data_date="2026-10-19",
                            schema="baldr.theme_research_snapshot.tpex_flows.v2")

    result = catalog.resolve_latest_theme_research_snapshot(root, known_at=_KNOWN_AT)

    assert result.selected is not None
    assert result.selected.manifest_path == price.resolve()
    assert result.selected.schema == "baldr.theme_research_snapshot.v1"
    assert flow.exists()


def test_catalog_requires_aware_known_at_and_explicit_existing_root(tmp_path: Path) -> None:
    root = tmp_path / "versions"
    root.mkdir()

    with pytest.raises(ValueError, match="aware datetime"):
        catalog.resolve_latest_theme_research_snapshot(
            root, known_at=datetime(2026, 10, 20, 12, 0),
        )
    with pytest.raises(ValueError, match="絕對Path"):
        catalog.resolve_latest_theme_research_snapshot(Path("relative"), known_at=_KNOWN_AT)


def test_scan_consumes_only_remaining_budget_plus_one_and_never_selects_partial_root(
    tmp_path: Path, monkeypatch,
) -> None:
    root = tmp_path / "versions"
    _write_candidate(root / "candidate")
    for index in range(8):
        (root / f"noise-{index}.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(catalog, "_MAX_DISCOVERY_ENTRIES", 2)
    monkeypatch.setattr(catalog, "_validate_root", lambda _root: root)
    real_scandir = os.scandir
    consumed = [0]

    class _CountingIterator:
        def __init__(self, path: Path) -> None:
            self._context = real_scandir(path)
            self._iterator = None

        def __enter__(self):
            self._iterator = self._context.__enter__()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return self._context.__exit__(exc_type, exc_value, traceback)

        def __iter__(self):
            return self

        def __next__(self):
            assert self._iterator is not None
            item = next(self._iterator)
            consumed[0] += 1
            return item

    def tracked_scandir(path):
        return _CountingIterator(Path(path)) if Path(path) == root else real_scandir(path)

    monkeypatch.setattr(catalog.os, "scandir", tracked_scandir)

    result = catalog.resolve_latest_theme_research_snapshot(root, known_at=_KNOWN_AT)

    assert consumed[0] == 3
    assert result.limited is True
    assert result.selected is None
    assert result.limit_reason == "目錄項目超過2項上限"


def test_oversized_manifest_is_rejected_after_bounded_binary_read(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "versions"
    root.mkdir()
    oversized = root / "large.json"
    oversized.write_bytes(b"{" + b" " * (1024 * 1024))
    real_open = Path.open
    read_sizes: list[int] = []

    class _ReadSpy:
        def __init__(self, handle) -> None:
            self._handle = handle

        def __enter__(self):
            self._handle.__enter__()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return self._handle.__exit__(exc_type, exc_value, traceback)

        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            return self._handle.read(size)

    def open_spy(path: Path, *args, **kwargs):
        handle = real_open(path, *args, **kwargs)
        return _ReadSpy(handle) if path == oversized else handle

    monkeypatch.setattr(Path, "open", open_spy)

    result = catalog.resolve_latest_theme_research_snapshot(root, known_at=_KNOWN_AT)

    assert read_sizes == [32 * 1024 + 1]
    assert result.selected is None
    assert any("超過32KiB上限" in item.reason for item in result.rejections)


def test_cancel_callback_stops_after_bounded_candidate_preflight(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "versions"
    _write_candidate(root / "candidate")
    original_charge = catalog._artifact_charge
    cancelled = [False]

    def charge_then_cancel(*args, **kwargs) -> int:
        charge = original_charge(*args, **kwargs)
        cancelled[0] = True
        return charge

    def forbidden_reader(*_args, **_kwargs):
        pytest.fail("取消後不應呼叫既有reader")

    monkeypatch.setattr(catalog, "_artifact_charge", charge_then_cancel)
    monkeypatch.setattr(catalog, "read_theme_research_snapshot", forbidden_reader)

    with pytest.raises(ValueError, match="解析已取消"):
        catalog.resolve_latest_theme_research_snapshot(
            root, known_at=_KNOWN_AT, cancel_callback=lambda: cancelled[0],
        )
