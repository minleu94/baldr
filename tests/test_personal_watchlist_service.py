from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app_module.personal_data_paths import resolve_personal_data_paths
from app_module.personal_watchlist_service import (
    PersonalWatchlistSelectionError,
    PersonalWatchlistService,
    build_watchlist_service,
)
from app_module.watchlist_service import WatchlistService
from data_module.watchlist_repository import WatchlistRepository


def _config(tmp_path: Path, *, personal: bool = True, source_name: str = "default.json") -> SimpleNamespace:
    market_root = tmp_path / "market"
    output_root = tmp_path / "market-output"
    source = output_root / "watchlist" / source_name
    source.parent.mkdir(parents=True, exist_ok=True)
    values: dict[str, Any] = {
        "data_root": market_root,
        "output_root": output_root,
        "personal_data_root": tmp_path / "personal" if personal else None,
        "personal_watchlist_source": source if personal else None,
    }
    values["resolve_output_path"] = lambda relative: output_root / relative
    values["resolve_data_path"] = lambda relative: market_root / relative
    return SimpleNamespace(**values)


def _payload() -> dict[str, Any]:
    return {
        "version": 1,
        "name": "合成清單",
        "description": "personal adapter fixture",
        "created_at": "2026-10-06T08:00:00+00:00",
        "updated_at": "2026-10-06T08:00:00+00:00",
        "items": [{
            "stock_code": "2330",
            "stock_name": "台積電",
            "added_at": "2026-10-06T08:00:00+00:00",
            "source": "manual",
            "notes": "synthetic",
            "tags": ["fixture"],
            "opaque_extension": {"keep": [1, {"raw": True}]},
        }],
        "opaque_watchlist_extension": {"keep": "original"},
    }


def _write_json(config: SimpleNamespace) -> bytes:
    source = Path(config.personal_watchlist_source)
    raw = (json.dumps(_payload(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    source.write_bytes(raw)
    return raw


def test_unconfigured_selector_preserves_legacy_watchlist_service(tmp_path: Path) -> None:
    config = _config(tmp_path, personal=False)

    service = build_watchlist_service(config)

    assert type(service) is WatchlistService
    assert service.get_storage_status().mode in {"legacy_json", "upgrade_available"}
    assert config.resolve_output_path("watchlist/default.json").is_file()
    assert service.add_stocks([{"stock_code": "2330", "stock_name": "fixture"}]) == 1
    assert service.get_stock_codes() == ["2330"]


def test_partial_personal_configuration_fails_closed_without_creating_paths(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.personal_watchlist_source = None
    output_before = {
        path.relative_to(config.output_root): path.read_bytes()
        for path in config.output_root.rglob("*") if path.is_file()
    }

    with pytest.raises(PersonalWatchlistSelectionError, match="configured together"):
        build_watchlist_service(config)

    assert not (tmp_path / "personal").exists()
    assert {
        path.relative_to(config.output_root): path.read_bytes()
        for path in config.output_root.rglob("*") if path.is_file()
    } == output_before


def test_personal_startup_reads_legacy_json_without_creating_or_writing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    original = _write_json(config)

    service = build_watchlist_service(config)
    preview = service.personal_storage_preview()

    assert isinstance(service, PersonalWatchlistService)
    assert service.get_storage_status().mode == "personal_source_readonly"
    assert service.get_storage_status().upgrade_available is True
    assert service.get_stock_codes() == ["2330"]
    assert preview["source"] == str(config.personal_watchlist_source)
    assert preview["target"].endswith("watchlists.v3.sqlite")
    assert preview["marker"].startswith(str(tmp_path / "personal"))
    assert preview["receipt"].startswith(str(tmp_path / "personal"))
    assert preview["backup"].startswith(str(tmp_path / "personal"))
    assert preview["rollback_audit_root"].startswith(str(tmp_path / "personal"))
    assert not (tmp_path / "personal").exists()
    assert not config.output_root.joinpath("watchlist", "watchlists.db").exists()
    with pytest.raises(PersonalWatchlistSelectionError, match="不可保存"):
        service.add_stocks([{"stock_code": "2317", "stock_name": "fixture"}])
    assert Path(config.personal_watchlist_source).read_bytes() == original


def test_personal_upgrade_new_process_add_and_rollback_keep_source_immutable(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = Path(config.personal_watchlist_source)
    original = _write_json(config)
    paths = resolve_personal_data_paths(
        config.data_root,
        personal_root=config.personal_data_root,
        legacy_output_root=config.output_root,
        environ={},
    )

    service = build_watchlist_service(config)
    status = service.upgrade_to_repository()

    assert status.mode == "repository"
    assert paths.watchlist_db.is_file()
    assert paths.activation_marker.is_file()
    assert paths.conversion_receipt.is_file()
    assert paths.backup_root.joinpath(
        f"source.{__import__('hashlib').sha256(str(source.resolve()).encode('utf-8')).hexdigest()}.json"
    ).read_bytes() == original
    assert source.read_bytes() == original
    assert not config.output_root.joinpath("watchlist", "watchlists.db").exists()

    child_code = r'''
import sys
from pathlib import Path
from types import SimpleNamespace
from app_module.personal_watchlist_service import build_watchlist_service

market, output, personal, source = map(Path, sys.argv[1:])
config = SimpleNamespace(data_root=market, output_root=output,
                         personal_data_root=personal,
                         personal_watchlist_source=source,
                         resolve_data_path=lambda value: market / value)
service = build_watchlist_service(config)
assert service.get_storage_status().mode == "repository"
assert service.get_stock_codes() == ["2330"]
assert service.add_stocks([{"stock_code": "2317", "stock_name": "synthetic"}]) == 1
assert service.get_stock_codes() == ["2330", "2317"]
print("personal-selector-child-ok")
'''
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            child_code,
            str(config.data_root),
            str(config.output_root),
            str(config.personal_data_root),
            str(source),
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert child.returncode == 0, child.stderr
    assert "personal-selector-child-ok" in child.stdout
    assert source.read_bytes() == original

    reopened = build_watchlist_service(config)
    assert reopened.get_stock_codes() == ["2330", "2317"]
    current = reopened.get_default_watchlist()
    assert current is not None
    assert current._storage_extensions["opaque_watchlist_extension"] == {"keep": "original"}
    assert current.items[0]._storage_extensions["opaque_extension"] == {
        "keep": [1, {"raw": True}],
    }

    target_before_rollback = paths.watchlist_db.read_bytes()
    rolled = reopened.rollback_to_source()

    assert rolled["status"] == "rolled_back"
    assert reopened.get_storage_status().mode == "personal_rolled_back_readonly"
    assert reopened.get_stock_codes() == ["2330"]
    assert paths.watchlist_db.read_bytes() == target_before_rollback
    assert WatchlistRepository(paths.watchlist_db).load("default")[0]["items"][-1]["stock_code"] == "2317"
    with pytest.raises(PersonalWatchlistSelectionError, match="不可保存"):
        reopened.add_stocks([{"stock_code": "2882", "stock_name": "fixture"}])
    assert source.read_bytes() == original


def test_personal_sqlite_v1_source_is_read_only_until_explicit_upgrade(tmp_path: Path) -> None:
    config = _config(tmp_path, source_name="watchlists.sqlite")
    source = Path(config.personal_watchlist_source)
    payload = _payload()
    with sqlite3.connect(source) as connection:
        connection.execute(
            "CREATE TABLE watchlists (watchlist_id TEXT PRIMARY KEY, "
            "payload_json TEXT NOT NULL, revision INTEGER NOT NULL, "
            "source_hash TEXT NOT NULL DEFAULT '')"
        )
        connection.execute(
            "INSERT INTO watchlists VALUES ('default', ?, 7, '')",
            (json.dumps(payload, ensure_ascii=False),),
        )
    original = source.read_bytes()

    service = build_watchlist_service(config)

    assert service.get_storage_status().mode == "repository_readonly"
    assert service.get_storage_status().upgrade_available is True
    assert service.get_stock_codes() == ["2330"]
    with pytest.raises(PersonalWatchlistSelectionError, match="不可保存"):
        service.add_stocks([{"stock_code": "2317", "stock_name": "fixture"}])
    assert source.read_bytes() == original
    assert not Path(config.personal_data_root).exists()


def test_unconfigured_factory_still_discovers_existing_canonical_repository(tmp_path: Path) -> None:
    config = _config(tmp_path, personal=False)
    repository_path = config.output_root / "watchlist" / "watchlists.db"
    WatchlistRepository(repository_path, initialize=True)

    service = build_watchlist_service(config)

    assert type(service) is WatchlistService
    assert service.get_storage_status().mode == "repository"
    assert service.repository is not None
    assert service.repository.db_path == repository_path.resolve()


def test_personal_source_that_becomes_hardlinked_is_not_read(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = Path(config.personal_watchlist_source)
    original = _write_json(config)
    service = build_watchlist_service(config)
    alias = source.with_name("source-alias.json")
    os.link(source, alias)

    with pytest.raises(PersonalWatchlistSelectionError, match="source_unavailable"):
        service.get_stock_codes()

    assert source.read_bytes() == original
    assert not Path(config.personal_data_root).exists()


def test_personal_root_overlapping_application_package_is_rejected(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.personal_data_root = Path(__file__).resolve().parents[1] / "personal-root-fixture"

    with pytest.raises(PersonalWatchlistSelectionError, match="overlaps_application_package"):
        build_watchlist_service(config)

    assert not config.personal_data_root.exists()
