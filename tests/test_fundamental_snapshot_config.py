"""正常配置基本面副本根；連線僅及reader copy，來源原檔保持不變。"""
from pathlib import Path
import shutil
import sqlite3
import json

import pytest

from app_module.application_bootstrap import resolve_application_settings
from data_module.config import TWStockConfig
from data_module.fundamental_read_snapshot import FundamentalReadSnapshotError, FundamentalReadSnapshotSession
from tests.test_baldr_completion_p03_sources import _seed_provider, _source_file_bytes_and_mtimes, CUTOFF


def test_portable_config_opens_only_copy_and_finishes_original_source_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path / "source")
    root = tmp_path / "isolated_copies"
    portable = tmp_path / "portable.json"
    portable.write_text(json.dumps({"DATA_ROOT": str(tmp_path / "source"),
        "OUTPUT_ROOT": str(provider.output_root), "FUNDAMENTAL_READ_SNAPSHOT_ROOT": str(root)}), encoding="utf-8")
    settings = resolve_application_settings(environ={"LOCALAPPDATA": str(tmp_path / "local"),
        "BALDR_CONFIG": str(portable)})
    for key, value in settings.environment.items():
        monkeypatch.setenv(key, value)
    config = TWStockConfig()
    shutil.copyfile(provider.db_file, config.db_file)
    before = _source_file_bytes_and_mtimes(config.db_file)
    connect_calls: list[str] = []
    original_connect = sqlite3.connect

    def observe_connect(database, *args, **kwargs):
        connect_calls.append(str(database))
        assert str(config.db_file).replace("\\", "/") not in str(database).replace("\\", "/")
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", observe_connect)
    assert not root.exists()
    session = FundamentalReadSnapshotSession.open_from_config(
        config, stock_codes=("1101", "2330"), cutoff_at=CUTOFF)
    session.load_batch(("1101", "2330"))
    finished = session.finish()
    assert session.snapshot_root.parent == root
    assert connect_calls
    assert session.reader_database_path != config.db_file
    assert finished.source_clock.database_path == str(config.db_file.resolve())
    assert finished.source_clock.snapshot_binding.source_database_path == str(config.db_file.resolve())
    assert _source_file_bytes_and_mtimes(config.db_file) == before


@pytest.mark.parametrize("selected", [None, "data", "output"])
def test_missing_or_overlapping_configured_root_never_copies_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selected: str | None,
) -> None:
    monkeypatch.delenv("FUNDAMENTAL_READ_SNAPSHOT_ROOT", raising=False)
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    root = tmp_path / selected / "forbidden_copies" if selected else None
    config.fundamental_read_snapshot_root = root
    expected = "not_configured" if root is None else "overlaps_configured"
    with pytest.raises(FundamentalReadSnapshotError, match=expected):
        FundamentalReadSnapshotSession.open_from_config(config, stock_codes=("2330",), cutoff_at=CUTOFF)
    assert root is None or not root.exists()


@pytest.mark.parametrize("value", ["", " ", "relative/copies"])
def test_invalid_portable_root_is_not_replaced_by_a_qa_default(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError, match="FUNDAMENTAL_READ_SNAPSHOT_ROOT"):
        resolve_application_settings(environ={"LOCALAPPDATA": str(tmp_path / "local"),
            "FUNDAMENTAL_READ_SNAPSHOT_ROOT": value})
    assert not (tmp_path / "local").exists()


def test_configured_source_provider_cannot_silently_switch_database(tmp_path: Path) -> None:
    provider = _seed_provider(tmp_path / "source")
    root = tmp_path / "copies"
    config = TWStockConfig(data_root=tmp_path / "other_data", output_root=provider.output_root,
        fundamental_read_snapshot_root=root)
    with pytest.raises(FundamentalReadSnapshotError, match="provider_config_identity_mismatch"):
        FundamentalReadSnapshotSession.open_from_config(config, stock_codes=("2330",),
            cutoff_at=CUTOFF, provider=provider)
    assert not root.exists()


def test_frozen_copy_root_is_rejected_before_source_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = tmp_path / "bundle"
    monkeypatch.setattr("sys._MEIPASS", str(bundle), raising=False)
    with pytest.raises(ValueError, match="FUNDAMENTAL_READ_SNAPSHOT_ROOT"):
        resolve_application_settings(environ={"LOCALAPPDATA": str(tmp_path / "local"),
            "FUNDAMENTAL_READ_SNAPSHOT_ROOT": str(bundle / "copies")}, resource_root=bundle, frozen=True)
    assert not bundle.exists()
