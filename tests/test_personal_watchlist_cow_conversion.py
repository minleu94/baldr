from pathlib import Path
import hashlib
import os
import json
import sqlite3
import subprocess

import pytest

from app_module.personal_data_paths import (
    PersonalDataPathError,
    WatchlistCowControlPaths,
    resolve_personal_data_paths,
)
from data_module.watchlist_json_cow import (
    convert_watchlist_json,
    dry_run_watchlist_json,
)
from data_module.watchlist_sqlite_cow import (
    convert_watchlist_sqlite,
    dry_run_watchlist_sqlite,
)


def _payload() -> dict[str, object]:
    return {
        "version": 1,
        "name": "合成個人清單",
        "description": "只供 converter 測試使用",
        "created_at": "2026-10-05T09:00:00+00:00",
        "updated_at": "2026-10-05T09:00:00+00:00",
        "items": [{
            "stock_code": "2330",
            "stock_name": "合成測試股",
            "added_at": "2026-10-05T09:00:00+00:00",
            "source": "manual",
            "source_id": "",
            "notes": "synthetic",
            "tags": ["fixture"],
            "extension": {"keep": [1, {"raw": True}]},
        }],
        "history": [{"event": "保留為 opaque payload"}],
    }


def _setup(tmp_path: Path, source_name: str = "default.json") -> tuple[Path, Path, WatchlistCowControlPaths]:
    market_root = tmp_path / "FA_Data"
    source = market_root / "output" / "watchlists" / source_name
    source.parent.mkdir(parents=True)
    paths = resolve_personal_data_paths(
        market_root, personal_root=tmp_path / "personal", environ={},
    )
    return source, paths.personal_root, WatchlistCowControlPaths(paths, source)


def _write_json_source(source: Path) -> bytes:
    raw = (json.dumps(_payload(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    source.write_bytes(raw)
    return raw


def _write_sqlite_source(source: Path) -> bytes:
    source.parent.mkdir(parents=True, exist_ok=True)
    payload_json = json.dumps(_payload(), ensure_ascii=False, sort_keys=True)
    with sqlite3.connect(source) as connection:
        connection.execute(
            "CREATE TABLE watchlists (watchlist_id TEXT PRIMARY KEY, "
            "payload_json TEXT NOT NULL, revision INTEGER NOT NULL, "
            "source_hash TEXT NOT NULL DEFAULT '')"
        )
        connection.execute(
            "INSERT INTO watchlists VALUES ('default', ?, 7, '')",
            (payload_json,),
        )
    return source.read_bytes()


def test_personal_json_dry_run_does_not_create_any_control_directories(tmp_path: Path) -> None:
    source, personal_root, controls = _setup(tmp_path)
    source_bytes = _write_json_source(source)
    source_stat = source.stat()

    result = dry_run_watchlist_json(
        source, controls.personal_paths.watchlist_db, control_paths=controls,
    )

    assert result["status"] == "dry_run", result
    assert result["receipt_path"] == str(controls.receipt_path)
    assert not personal_root.exists()
    assert source.read_bytes() == source_bytes
    assert source.stat().st_mtime_ns == source_stat.st_mtime_ns


def test_personal_json_conversion_saves_exact_create_only_source_backup(tmp_path: Path) -> None:
    source, personal_root, controls = _setup(tmp_path)
    source_bytes = _write_json_source(source)
    source_stat = source.stat()

    result = convert_watchlist_json(
        source, controls.personal_paths.watchlist_db, control_paths=controls,
    )

    assert result["status"] == "ready", result
    assert Path(result["target_path"]) == controls.personal_paths.watchlist_db
    assert Path(result["receipt_path"]) == controls.receipt_path
    assert controls.source_backup_path.read_bytes() == source_bytes
    assert result["source_backup_path"] == str(controls.source_backup_path)
    assert result["source_backup_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    receipt = json.loads(controls.receipt_path.read_text(encoding="utf-8"))
    assert receipt["source_backup_path"] == str(controls.source_backup_path)
    assert receipt["source_backup_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert source.read_bytes() == source_bytes
    assert source.stat().st_mtime_ns == source_stat.st_mtime_ns
    assert controls.personal_paths.watchlist_db.stat().st_nlink == 1
    assert all(
        controls.assert_personal(path) == path
        for path in personal_root.rglob("*") if path.is_file()
    )


def test_personal_json_target_and_explicit_receipt_mismatches_fail_closed(tmp_path: Path) -> None:
    source, personal_root, controls = _setup(tmp_path)
    _write_json_source(source)

    outside_result = dry_run_watchlist_json(
        source, tmp_path / "outside.sqlite", control_paths=controls,
    )
    assert outside_result["status"] == "blocked"
    assert outside_result["error_code"] == "control_path_outside_personal"

    wrong_target_result = dry_run_watchlist_json(
        source, personal_root / "wrong.sqlite", control_paths=controls,
    )
    assert wrong_target_result["status"] == "blocked"
    assert wrong_target_result["error_code"] == "control_target_mismatch"
    assert not personal_root.exists()
    with pytest.raises(PersonalDataPathError) as outside_error:
        controls.validate(
            source,
            controls.personal_paths.watchlist_db,
            tmp_path / "outside-receipt.json",
        )
    assert outside_error.value.code == "control_path_outside_personal"
    wrong_default = personal_root / "wrong-receipt.json"
    with pytest.raises(PersonalDataPathError) as mismatch_error:
        controls.validate(
            source, controls.personal_paths.watchlist_db, wrong_default,
        )
    assert mismatch_error.value.code == "control_receipt_mismatch"
    assert not personal_root.exists()


@pytest.mark.parametrize(
    ("control_file", "expected_code"),
    [
        ("legacy_marker", "legacy_control_marker_requires_review"),
        ("backup_conflict", "source_backup_conflict"),
    ],
)
def test_personal_json_rejects_legacy_marker_or_conflicting_backup(
    tmp_path: Path, control_file: str, expected_code: str,
) -> None:
    source, personal_root, controls = _setup(tmp_path)
    source_bytes = _write_json_source(source)
    if control_file == "legacy_marker":
        source.with_name(source.name + ".cow-active.json").write_text("{}", encoding="utf-8")
    else:
        controls.source_backup_path.parent.mkdir(parents=True)
        controls.source_backup_path.write_bytes(b"conflicting synthetic backup")

    result = convert_watchlist_json(
        source, controls.personal_paths.watchlist_db, control_paths=controls,
    )

    assert result["status"] == "blocked"
    assert result["error_code"] == expected_code
    assert source.read_bytes() == source_bytes
    assert not controls.personal_paths.watchlist_db.exists()
    assert not controls.receipt_path.exists()
    if control_file == "backup_conflict":
        assert controls.source_backup_path.read_bytes() == b"conflicting synthetic backup"


def test_personal_sqlite_dry_run_is_read_only_and_creates_no_directories(
    tmp_path: Path,
) -> None:
    source, personal_root, controls = _setup(tmp_path, "watchlists.db")
    source_bytes = _write_sqlite_source(source)
    source_stat = source.stat()
    sidecars = [Path(f"{source}{suffix}") for suffix in ("-journal", "-wal", "-shm")]

    result = dry_run_watchlist_sqlite(
        source, controls.personal_paths.watchlist_db, control_paths=controls,
    )

    assert result["status"] == "dry_run", result
    assert not personal_root.exists()
    assert source.read_bytes() == source_bytes
    assert source.stat().st_mtime_ns == source_stat.st_mtime_ns
    assert not any(path.exists() for path in sidecars)


def test_personal_sqlite_with_sibling_legacy_json_requires_review(tmp_path: Path) -> None:
    source, personal_root, controls = _setup(tmp_path, "watchlists.db")
    source_bytes = _write_sqlite_source(source)
    sibling_json = source.with_name("default.json")
    sibling_json.write_bytes(b"synthetic legacy list")

    result = convert_watchlist_sqlite(
        source, controls.personal_paths.watchlist_db, control_paths=controls,
    )

    assert result["status"] == "blocked"
    assert result["error_code"] == "legacy_json_scope_requires_review"
    assert not personal_root.exists()
    assert source.read_bytes() == source_bytes
    assert sibling_json.read_bytes() == b"synthetic legacy list"

@pytest.mark.parametrize(("source_name", "kind"), [
    ("default.json", "json"), ("watchlists.db", "sqlite"),
])
def test_personal_converter_rejects_hardlinked_source(
    tmp_path: Path, source_name: str, kind: str,
) -> None:
    source, personal_root, controls = _setup(tmp_path, source_name)
    source_bytes = _write_json_source(source) if kind == "json" else _write_sqlite_source(source)
    alias = source.with_name("source-hardlink.fixture")
    try:
        os.link(source, alias)
    except OSError as exc:
        pytest.skip(f"此檔案系統不支援合成 hardlink：{exc}")

    converter = convert_watchlist_json if kind == "json" else convert_watchlist_sqlite
    result = converter(source, controls.personal_paths.watchlist_db, control_paths=controls)

    assert result["status"] == "blocked"
    assert result["error_code"] == "source_path_alias"
    assert source.read_bytes() == source_bytes
    assert alias.read_bytes() == source_bytes
    assert not personal_root.exists()


def _create_source_directory_link(link_path: Path, target: Path, link_kind: str) -> None:
    if link_kind == "junction":
        if os.name != "nt":
            pytest.skip("Windows junction coverage requires Windows")
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link_path), str(target)],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        assert result.returncode == 0, f"mklink /J failed: {result.stdout}{result.stderr}"
        return

    try:
        link_path.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"此環境不允許建立合成目錄連結：{exc}")


@pytest.mark.parametrize(("source_name", "kind", "link_kind"), [
    ("default.json", "json", "symlink"),
    ("watchlists.db", "sqlite", "symlink"),
    ("default.json", "json", "junction"),
    ("watchlists.db", "sqlite", "junction"),
])
def test_personal_converter_rejects_linked_source_directory(
    tmp_path: Path, source_name: str, kind: str, link_kind: str,
) -> None:
    source, personal_root, controls = _setup(tmp_path, source_name)
    source_bytes = _write_json_source(source) if kind == "json" else _write_sqlite_source(source)
    alias_root = tmp_path / "source-alias"
    converter = convert_watchlist_json if kind == "json" else convert_watchlist_sqlite

    try:
        _create_source_directory_link(alias_root, source.parent, link_kind)
        alias = alias_root / source.name
        result = converter(alias, controls.personal_paths.watchlist_db, control_paths=controls)

        assert result["status"] == "blocked"
        assert result["error_code"] == "linked_path"
        assert source.read_bytes() == source_bytes
        assert not personal_root.exists()
    finally:
        if os.path.lexists(alias_root):
            if link_kind == "junction":
                os.rmdir(alias_root)
            else:
                alias_root.unlink()
