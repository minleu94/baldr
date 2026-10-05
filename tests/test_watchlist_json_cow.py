from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from data_module import watchlist_item_storage
from data_module.watchlist_json_cow import (
    convert_watchlist_json,
    dry_run_watchlist_json,
    held_json_source,
)
from data_module.watchlist_item_storage import WatchlistWriteCapacityRequest


def _fixture_payload(count: int = 20) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for index in range(count):
        code = f"{2330 + index:04d}"
        items.append({
            "stock_code": code,
            "stock_name": f"測試股{index}",
            "added_at": f"2026-10-{index + 1:02d}",
            "notes": f"備註 {index}",
            "tags": ["fixture", f"tag-{index}"],
            "source": "bookmark",
            "source_id": f"ranking-{index}",
            "research_bookmark": {
                "schema_version": "daily-market-research-bookmark.v2",
                "selection_reason": f"收藏理由 {index}",
            },
            "unknown_nested": {
                "vendor": "fixture",
                "rank_trace": {"date": "2026-10-05", "position": index + 1},
            },
        })
    return {
        "version": 1,
        "name": "合成清單",
        "description": "單檔 JSON COW fixture",
        "created_at": "2026-09-01T09:00:00",
        "updated_at": "2026-10-05T09:00:00",
        "items": items,
        "history": [{"at": "2026-09-30", "note": "legacy opaque history"}],
        "unknown_envelope": {"nested": {"preserve_me": [1, {"value": "原樣"}] }},
    }


def _write_source(path: Path, payload: object | str) -> bytes:
    raw = payload if isinstance(payload, str) else json.dumps(
        payload, ensure_ascii=False, indent=2,
    )
    encoded = raw.encode("utf-8")
    path.write_bytes(encoded)
    return encoded


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    source_dir = tmp_path / "legacy"
    target_dir = tmp_path / "cow"
    source_dir.mkdir()
    target_dir.mkdir()
    return source_dir / "default.json", target_dir / "default-v3.sqlite"


def test_legacy_json_dry_run_and_convert_preserve_raw_payload_and_mark_one_baseline(
    tmp_path: Path,
) -> None:
    source, target = _paths(tmp_path)
    payload = _fixture_payload()
    source_bytes = _write_source(source, payload)
    source_stat = source.stat()

    preview = dry_run_watchlist_json(source, target)

    assert preview["status"] == "dry_run"
    assert preview["source_format"] == "legacy_json_v1"
    assert preview["canonical_path"] == str(source.resolve())
    assert preview["source_schema_version"] == 1
    assert preview["target_schema_version"] == 3
    assert preview["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert preview["comparison"]["raw_payload_bytes_preserved"] is True
    assert preview["comparison"]["ordered_raw_items_preserved"] is True
    assert preview["comparison"]["ordered_raw_item_count"] == 20
    assert preview["comparison"]["payload_envelope_fields_preserved"] == [
        "created_at", "description", "history", "name", "unknown_envelope", "updated_at", "version",
    ]
    assert preview["comparison"]["history_like_field_paths_preserved_as_opaque_payload"] == ["$.history"]
    assert preview["comparison"]["source_revision_ledger"] == "not_provided_by_legacy_json_v1"
    assert preview["comparison"]["history_interpreted_as_revision_events"] is False
    assert preview["comparison"]["target_synthetic_baseline_count"] == 1
    assert source.read_bytes() == source_bytes
    assert source.stat().st_mtime_ns == source_stat.st_mtime_ns
    assert not target.exists()
    assert not Path(preview["receipt_path"]).exists()

    converted = convert_watchlist_json(source, target)

    assert converted["status"] == "ready"
    assert converted["schema_version"] == "watchlist-cow-conversion.v1"
    assert converted["source_format"] == "legacy_json_v1"
    assert converted["source_path"] == str(source.resolve())
    assert converted["canonical_path"] == str(source.resolve())
    assert converted["source_stat"] == {
        "size": source_stat.st_size,
        "mtime_ns": source_stat.st_mtime_ns,
        "inode": source_stat.st_ino,
        "device": source_stat.st_dev,
    }
    assert converted["revision_count"] == 1
    assert converted["revision_counts"] == {"default": 1}
    assert converted["item_count"] == 20
    assert converted["comparison"]["payload_hashes_matched"] == 1
    assert converted["comparison"]["target_synthetic_baseline_count"] == 1
    assert source.read_bytes() == source_bytes
    assert target.exists()
    receipt_path = Path(converted["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt == converted
    assert "legacy opaque history" not in receipt_path.read_text(encoding="utf-8")

    with sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True) as connection:
        inventory = watchlist_item_storage.inventory(connection)
        revisions = list(watchlist_item_storage.iter_revisions(connection, "default"))
        current = inventory["watchlists"][0]
        object_rows = connection.execute(
            "SELECT ci.position,io.item_json FROM watchlist_current_items ci "
            "JOIN watchlist_item_objects io USING(object_hash) "
            "WHERE ci.watchlist_id=? ORDER BY ci.position",
            ("default",),
        ).fetchall()

    assert inventory["complete"] is True
    assert inventory["historical_payload_hashes_verified"] is True
    assert current["payload"] == payload
    assert current["payload_json"] == source_bytes.decode("utf-8")
    assert [json.loads(row[1]) for row in object_rows] == payload["items"]
    assert all(
        hashlib.sha256(row[1].encode("utf-8")).hexdigest() == digest
        for row, digest in zip(object_rows, converted["comparison"]["ordered_raw_item_sha256"])
    )
    assert len(revisions) == 1
    revision = revisions[0]
    assert revision["revision"] == 1
    assert revision["revision_id"] == f"cow-v1-baseline:{converted['source_sha256']}:default"
    assert revision["operation"] == "migration_baseline"
    assert revision["created_at"] == ""
    assert revision["revision_of"] == ""
    assert revision["is_synthetic_baseline"] is True
    assert revision["source_revision_id"] == ""
    assert revision["payload"] == payload


@pytest.mark.parametrize(
    ("raw", "error_code"),
    [
        ('{"items":[],"items":[]}', "duplicate_json_key"),
        ('{"items":[],"value":NaN}', "nonfinite_json_number"),
        ('[]', "invalid_payload_shape"),
        ('{"version":1,"name":"x","created_at":"x","updated_at":"x","items":{}}', "invalid_payload_shape"),
        ('{"version":2,"name":"x","created_at":"x","updated_at":"x","items":[]}', "unsupported_legacy_json_version"),
        ('{"version":true,"name":"x","created_at":"x","updated_at":"x","items":[]}', "unsupported_legacy_json_version"),
        ('{"name":"x","created_at":"x","updated_at":"x","items":[]}', "unsupported_legacy_json_version"),
        ('{"version":1,"name":"x","updated_at":"x","items":[]}', "invalid_legacy_envelope_created_at"),
        ('{"version":1,"name":null,"created_at":"x","updated_at":"x","items":[]}', "invalid_legacy_envelope_name"),
        ('{"version":1,"name":"x","created_at":"x","updated_at":"x","items":[null]}', "invalid_item_object"),
    ],
)
def test_invalid_legacy_json_envelope_is_blocked_without_publishing(
    tmp_path: Path, raw: str, error_code: str,
) -> None:
    source, target = _paths(tmp_path)
    _write_source(source, raw)

    result = convert_watchlist_json(source, target)

    assert result["status"] == "blocked"
    assert result["error_code"] == error_code
    assert not target.exists()
    assert not Path(f"{target}.cow-conversion.v1.json").exists()


@pytest.mark.parametrize(
    ("item", "error_code"),
    [
        ({"stock_code": 2330, "stock_name": "x", "added_at": "t", "source": "manual"}, "invalid_legacy_item_stock_code"),
        ({"stock_code": "2330", "stock_name": 7, "added_at": "t", "source": "manual"}, "invalid_legacy_item_stock_name"),
        ({"stock_code": "2330", "stock_name": "x", "added_at": 7, "source": "manual"}, "invalid_legacy_item_added_at"),
        ({"stock_code": "2330", "stock_name": "x", "added_at": "t", "source": 7}, "invalid_legacy_item_source"),
        ({"stock_code": "2330", "stock_name": "x", "added_at": "t", "source": "manual", "notes": 7}, "invalid_legacy_item_notes"),
        ({"stock_code": "2330", "stock_name": "x", "added_at": "t", "source": "manual", "source_id": 7}, "invalid_legacy_item_source_id"),
        ({"stock_code": "2330", "stock_name": "x", "added_at": "t", "source": "manual", "tags": ["ok", 3]}, "invalid_legacy_item_tags"),
        ({"stock_code": "2330", "stock_name": "", "added_at": "t", "source": "manual"}, "invalid_legacy_item_stock_name"),
        ({"stock_code": "2330", "stock_name": "x", "added_at": "", "source": "manual"}, "invalid_legacy_item_added_at"),
        ({"stock_code": "2330", "stock_name": "x", "added_at": "t", "source": ""}, "invalid_legacy_item_source"),
        ({"stock_code": " 2330", "stock_name": "x", "added_at": "t", "source": "manual"}, "invalid_legacy_item_stock_code"),
        ({"stock_code": "2330", "stock_name": "x", "added_at": "t", "source": "manual", "decision_identity": {"result_id": 7}}, "invalid_legacy_decision_identity_result_id"),
    ],
)
def test_invalid_legacy_json_item_fields_are_blocked_without_publishing(
    tmp_path: Path, item: dict[str, object], error_code: str,
) -> None:
    source, target = _paths(tmp_path)
    _write_source(source, {
        "version": 1, "name": "fixture", "created_at": "t", "updated_at": "t",
        "items": [item],
    })

    result = convert_watchlist_json(source, target)

    assert result["status"] == "blocked"
    assert result["error_code"] == error_code
    assert not target.exists()
    assert not Path(f"{target}.cow-conversion.v1.json").exists()


def test_utf8_bom_is_an_explicitly_unsupported_encoding(tmp_path: Path) -> None:
    source, target = _paths(tmp_path)
    source.write_bytes(b"\xef\xbb\xbf" + json.dumps(_fixture_payload()).encode("utf-8"))

    result = dry_run_watchlist_json(source, target)

    assert result["status"] == "blocked"
    assert result["error_code"] == "unsupported_utf8_bom"
    assert not target.exists()


def test_payload_and_row_limits_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, target = _paths(tmp_path)
    _write_source(source, _fixture_payload(4))
    monkeypatch.setattr(watchlist_item_storage, "MAX_PAYLOAD_BYTES", 20)

    too_large = dry_run_watchlist_json(source, target)

    assert too_large["status"] == "blocked"
    assert too_large["error_code"] == "payload_limit_exceeded"

    monkeypatch.undo()
    source.write_bytes(json.dumps(_fixture_payload(4), ensure_ascii=False).encode("utf-8"))
    monkeypatch.setattr(watchlist_item_storage, "MAX_ROWS", 4)
    too_many_rows = dry_run_watchlist_json(source, target)

    assert too_many_rows["status"] == "blocked"
    assert too_many_rows["error_code"] == "row_limit_exceeded"
    assert not target.exists()


@pytest.mark.parametrize("extension", [
    {"nested": {"deeper": {"value": 1}}},
    [None],
])
def test_payload_depth_and_node_limits_fail_closed(
    tmp_path: Path, extension: object,
) -> None:
    from data_module import watchlist_json_cow

    source, target = _paths(tmp_path)
    payload = _fixture_payload(0)
    if isinstance(extension, list):
        payload["large_unknown_list"] = [None] * (watchlist_json_cow._MAX_JSON_NODES + 1)
    else:
        nested: object = 1
        for _ in range(watchlist_json_cow._MAX_JSON_DEPTH + 2):
            nested = {"nested": nested}
        payload["deep_unknown_value"] = nested
    _write_source(source, payload)

    result = dry_run_watchlist_json(source, target)

    expected = (
        "payload_node_limit_exceeded" if isinstance(extension, list)
        else "payload_depth_limit_exceeded"
    )
    assert result["status"] == "blocked"
    assert result["error_code"] == expected
    assert not target.exists()


def test_capacity_rejection_does_not_publish_target_or_receipt(tmp_path: Path) -> None:
    source, target = _paths(tmp_path)
    _write_source(source, _fixture_payload(2))

    result = convert_watchlist_json(source, target, capacity_preflight=lambda _request: False)

    assert result["status"] == "blocked"
    assert result["error_code"] == "capacity_insufficient"
    assert not target.exists()
    assert not Path(f"{target}.cow-conversion.v1.json").exists()


def test_other_json_watchlist_in_directory_blocks_single_file_scope(tmp_path: Path) -> None:
    source, target = _paths(tmp_path)
    _write_source(source, _fixture_payload(1))
    _write_source(source.with_name("secondary.json"), _fixture_payload(1))

    result = dry_run_watchlist_json(source, target)

    assert result["status"] == "blocked"
    assert result["error_code"] == "other_json_sources_present"
    assert not target.exists()


def test_existing_canonical_database_blocks_legacy_json_scope(tmp_path: Path) -> None:
    source, target = _paths(tmp_path)
    _write_source(source, _fixture_payload(1))
    (source.parent / "watchlists.db").write_bytes(b"not a sqlite database")

    result = dry_run_watchlist_json(source, target)

    assert result["status"] == "blocked"
    assert result["error_code"] == "canonical_database_present"
    assert not target.exists()


def test_held_source_blocks_concurrent_write_during_conversion(tmp_path: Path) -> None:
    import os

    if os.name != "nt":
        pytest.skip("Windows share-mode read lock is the tested native contract")
    source, target = _paths(tmp_path)
    source_bytes = _write_source(source, _fixture_payload(2))

    def try_write_source(_request: WatchlistWriteCapacityRequest) -> bool:
        try:
            with source.open("ab") as handle:
                handle.write(b" ")
        except OSError:
            pass
        else:
            raise AssertionError("held source allowed a concurrent writer")
        return True

    result = convert_watchlist_json(source, target, capacity_preflight=try_write_source)

    assert result["status"] == "ready"
    assert source.read_bytes() == source_bytes
    assert target.exists()


def test_held_source_rejects_an_existing_writer_handle(tmp_path: Path) -> None:
    import os

    if os.name != "nt":
        pytest.skip("Windows share-mode writer detection is the tested native contract")
    source, target = _paths(tmp_path)
    _write_source(source, _fixture_payload(1))

    with source.open("ab"):
        result = dry_run_watchlist_json(source, target)

    assert result["status"] == "blocked"
    assert result["error_code"] == "source_writer_busy"
    assert not target.exists()


def test_held_source_allows_readers_but_blocks_new_writer_handles(tmp_path: Path) -> None:
    import os

    if os.name != "nt":
        pytest.skip("Windows share-mode reader/writer contract is native")
    source, _target = _paths(tmp_path)
    source_bytes = _write_source(source, _fixture_payload(1))

    with held_json_source(source):
        assert source.read_bytes() == source_bytes
        with pytest.raises(OSError):
            with source.open("ab") as writer:
                writer.write(b" ")


def test_cli_selects_legacy_json_only_when_explicitly_requested(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.watchlist_sqlite_cow import main

    source, target = _paths(tmp_path)
    _write_source(source, _fixture_payload(2))

    exit_code = main([
        "dry-run", "--source", str(source), "--destination", str(target),
        "--source-format", "legacy-json",
    ])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "dry_run"
    assert output["source_format"] == "legacy_json_v1"
    assert not target.exists()


def test_manual_bookmark_source_is_refused_before_typed_reinterpretation(tmp_path: Path) -> None:
    source, target = _paths(tmp_path)
    payload = _fixture_payload(1)
    payload["items"][0]["source"] = "manual"
    raw = _write_source(source, payload)
    result = convert_watchlist_json(source, target)
    assert result["status"] == "blocked"
    assert result["error_code"] == "ambiguous_legacy_manual_bookmark_source"
    assert source.read_bytes() == raw
    assert not target.exists()
