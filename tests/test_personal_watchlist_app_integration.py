"""個人模式 App 邊界；所有來源皆為隔離合成資料。"""
from pathlib import Path
import json
import os
from types import SimpleNamespace

import pytest

from data_module.config import TWStockConfig
from tests.test_personal_watchlist_cow_conversion import _payload
from tests.test_watchlist_sqlite_cow_cli import _call


def test_config_candidate_does_not_create_personal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PERSONAL_DATA_ROOT", raising=False)
    monkeypatch.delenv("PERSONAL_WATCHLIST_SOURCE", raising=False)
    market = tmp_path / "market"
    personal = tmp_path / "personal"
    source = market / "output" / "watchlist" / "default.json"
    config = TWStockConfig(data_root=market, output_root=market / "output",
                           personal_data_root=personal, personal_watchlist_source=source)
    assert config.personal_data_root == personal
    assert not personal.exists()
    assert not source.exists()


def test_config_partial_selection_blocks_before_directory_creation(tmp_path: Path) -> None:
    market = tmp_path / "market"
    with pytest.raises(ValueError, match="personal_storage_selection_incomplete"):
        TWStockConfig(data_root=market, output_root=market / "output",
                      personal_data_root=tmp_path / "personal", personal_watchlist_source=None)
    assert not market.exists()


def test_config_rejects_application_package_as_personal_root(tmp_path: Path) -> None:
    market = tmp_path / "market"
    with pytest.raises(ValueError, match="personal_root_overlaps_application_package"):
        TWStockConfig(data_root=market, output_root=market / "output",
                      personal_data_root=Path(__file__).resolve().parents[1] / "private",
                      personal_watchlist_source=market / "default.json")
    assert not market.exists()


def test_personal_cli_new_process_convert_activate_rollback_preserves_source(tmp_path: Path) -> None:
    market = tmp_path / "market"
    output = market / "output"
    source = output / "watchlist" / "default.json"
    source.parent.mkdir(parents=True)
    original = json.dumps(_payload(), ensure_ascii=False).encode("utf-8")
    source.write_bytes(original)
    personal = tmp_path / "personal"
    target = personal / "watchlists" / "watchlists.v3.sqlite"
    roots = ["--source", str(source), "--personal-root", str(personal),
             "--market-root", str(market), "--legacy-output-root", str(output)]
    for action, extra, expected in (
        ("dry-run", ["--source-format", "legacy-json", "--destination", str(target)], "dry_run"),
        ("convert", ["--source-format", "legacy-json", "--destination", str(target)], "ready"),
        ("activate", ["--destination", str(target)], "activated"),
        ("rollback", [], "rolled_back"),
    ):
        code, result = _call(action, *roots, *extra)
        assert code == 0 and result["status"] == expected, result
        assert source.read_bytes() == original
        assert sorted(p.name for p in source.parent.iterdir()) == ["default.json"]
        if action == "dry-run":
            assert not personal.exists()
    assert target.is_file()
    assert list((personal / "backups" / "watchlists").glob("source.*.json"))
    assert list((personal / "activation_backups" / "watchlists").glob("rollback.*.json"))


def test_personal_cli_partial_selection_is_blocked(tmp_path: Path) -> None:
    code, result = _call("status", "--source", str(tmp_path / "missing.json"),
                         "--personal-root", str(tmp_path / "personal"))
    assert code == 2 and result["status"] == "blocked"
    assert not (tmp_path / "personal").exists()


def test_personal_ui_preview_cancel_then_explicit_enable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app_module.personal_watchlist_service import build_watchlist_service
    from ui_qt.views.watchlist_view import WatchlistView

    qapp = QApplication.instance() or QApplication([])
    market = tmp_path / "market"
    source = market / "output" / "watchlist" / "default.json"
    source.parent.mkdir(parents=True)
    original = json.dumps(_payload(), ensure_ascii=False).encode("utf-8")
    source.write_bytes(original)
    personal = tmp_path / "personal"
    config = SimpleNamespace(data_root=market, output_root=market / "output",
                             personal_data_root=personal, personal_watchlist_source=source)
    service = build_watchlist_service(config)
    view = WatchlistView(service, config=None)
    prompts: list[str] = []
    def cancel(_parent: object, _title: str, message: str, *_args: object) -> QMessageBox.StandardButton:
        prompts.append(message)
        return QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, "question", cancel)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    view._upgrade_watchlist_storage()
    assert prompts and str(source) in prompts[0] and str(personal) in prompts[0]
    assert not personal.exists()
    assert not service.get_storage_status().is_repository
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    view._upgrade_watchlist_storage()
    assert service.get_storage_status().is_repository
    assert service.repository is not None
    assert service.repository.db_path == personal / "watchlists" / "watchlists.v3.sqlite"
    assert source.read_bytes() == original
    assert sorted(p.name for p in source.parent.iterdir()) == ["default.json"]
    view.close()
    qapp.processEvents()
