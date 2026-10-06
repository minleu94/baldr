"""Increment B：候選池頁的明確 storage upgrade 入口與結果提示。"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from app_module.watchlist_service import WatchlistService
from ui_qt.views.watchlist_view import WatchlistView


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    return instance if instance is not None else QApplication([])


def _config(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        output_root=root / "output",
        resolve_output_path=lambda name: root / "output" / name,
    )


def test_watchlist_page_requires_explicit_upgrade_and_shows_cow_success(
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WatchlistService(_config(tmp_path))
    view = WatchlistView(service, config=None)
    view.show()
    qapp.processEvents()

    assert view.upgrade_storage_btn.isVisible()
    assert view.upgrade_storage_btn.isEnabled()
    assert "原 JSON" in view.storage_status_label.text()

    messages: list[str] = []
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.QMessageBox.information",
        lambda _parent, _title, message: messages.append(str(message)),
    )
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.QMessageBox.warning",
        lambda _parent, _title, message: messages.append(str(message)),
    )
    view.upgrade_storage_btn.click()
    qapp.processEvents()

    status = service.get_storage_status()
    assert status.is_repository, status.message
    assert not view.upgrade_storage_btn.isVisible()
    assert "SQLite" in view.storage_status_label.text()
    assert service.repository is not None
    assert service.repository.detect_storage_format()["schema_version"] == 3
    assert service.repository.db_path.name.startswith("watchlists.v3-cow-default-")
    assert service.repository.db_path.suffix == ".sqlite"
    assert not WatchlistService.repository_path(service.config).exists()
    assert (service.watchlist_dir / "default.json.cow-active.json").is_file()
    assert messages and "啟用並核對成功" in messages[-1]
    view.close()
