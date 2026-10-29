"""題材版本目錄載入、明選歷史版本與 TaskWorker 生命週期回歸。"""

from __future__ import annotations

from datetime import date, datetime, timezone
import os
import sys
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog

from app_module.theme_daily_service import ThemeDailyReport
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from app_module.theme_snapshot_catalog import (
    ThemeSnapshotCatalogEntry,
    ThemeSnapshotCatalogResult,
    ThemeSnapshotRejection,
)
from ui_qt.views import industry_theme_map_view as view_module


@pytest.fixture(scope="session", autouse=True)
def _application():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application
    application.processEvents()


def _snapshot(identity: str = "a" * 64) -> ThemeResearchSnapshot:
    report = ThemeDailyReport(
        data_date=date(2026, 10, 19),
        known_at=datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc),
        mapping_snapshot_date="2026-10-16",
        mapping_available_date="2026-10-16",
        status="current_research",
        rows=(),
        warnings=(),
    )
    return ThemeResearchSnapshot(identity, report, ())


def _catalog(snapshot: ThemeResearchSnapshot) -> ThemeSnapshotCatalogResult:
    entry = ThemeSnapshotCatalogEntry(
        manifest_path=Path("selected/manifest.json"),
        schema="baldr.theme_research_snapshot.v1",
        data_date=snapshot.report.data_date,
        saved_completed_at=datetime(2026, 10, 20, 0, 1, tzinfo=timezone.utc),
        identity_sha256=snapshot.identity_sha256,
        snapshot=snapshot,
    )
    return ThemeSnapshotCatalogResult(
        entries=(entry,),
        rejections=(),
        candidate_count=1,
        verified_count=1,
        unverified_candidate_count=0,
        limited=False,
        limit_reason=None,
    )


def _wait_until(application, predicate, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    application.processEvents()
    assert predicate(), "背景題材版本工作未在期限內完成"


def _close(view, application) -> None:
    view.shutdown()
    _wait_until(application, lambda: not view.is_busy())
    view.close()
    application.processEvents()


def test_missing_catalog_root_guides_without_calling_resolver(monkeypatch):
    application = QApplication.instance()
    view = view_module.IndustryThemeMapView()

    def unexpected_resolve(*_args, **_kwargs):
        raise AssertionError("未設定目錄時不得掃描任何來源")

    monkeypatch.setattr(
        view_module, "resolve_latest_theme_research_snapshot", unexpected_resolve
    )
    try:
        assert view.load_latest_snapshot() is False
        assert "尚未設定" in view.status_label.text()
        assert view.snapshot is None
    finally:
        _close(view, application)


def test_empty_default_catalog_explains_no_versions_instead_of_asking_for_a_file(
    monkeypatch, tmp_path
):
    application = QApplication.instance()
    view = view_module.IndustryThemeMapView()
    root = tmp_path / "theme_research_snapshots"
    root.mkdir()
    monkeypatch.setattr(
        view_module,
        "list_theme_research_snapshots",
        lambda *_args, **_kwargs: ThemeSnapshotCatalogResult(
            entries=(),
            rejections=(),
            candidate_count=0,
            verified_count=0,
            unverified_candidate_count=0,
            limited=False,
            limit_reason=None,
        ),
    )
    try:
        view.configure_catalog_root(root)
        _wait_until(application, lambda: not view.is_busy())
        assert view.catalog_root_label.text() == str(root)
        assert view.catalog_version_combo.count() == 1
        assert view.catalog_version_combo.itemText(0) == "目前沒有可讀版本"
        assert view.catalog_list_status_label.text() == "目前版本庫沒有已保存的題材版本。"
        assert not view.open_snapshot_button.isEnabled()
        assert view.latest_snapshot_button.isEnabled()
    finally:
        _close(view, application)


def test_rejected_catalog_versions_expose_reader_reason_in_status_tooltip(monkeypatch):
    application = QApplication.instance()
    view = view_module.IndustryThemeMapView()
    rejection = ThemeSnapshotRejection(
        Path("flow-v2/manifest.json"), "路徑超出caller明選root"
    )
    catalog = ThemeSnapshotCatalogResult(
        entries=(),
        rejections=(rejection,),
        candidate_count=1,
        verified_count=0,
        unverified_candidate_count=0,
        limited=False,
        limit_reason=None,
    )
    try:
        view._render_catalog_version_list(catalog)
        assert "未通過讀取驗證" in view.catalog_list_status_label.text()
        assert "manifest.json" in view.catalog_list_status_label.toolTip()
        assert "路徑超出caller明選root" in view.catalog_list_status_label.toolTip()
        assert not view.open_snapshot_button.isEnabled()
    finally:
        _close(view, application)


def test_latest_uses_selected_root_and_applies_resolver_snapshot_directly(monkeypatch, tmp_path):
    application = QApplication.instance()
    view = view_module.IndustryThemeMapView()
    selected_snapshot = _snapshot("b" * 64)
    catalog = _catalog(selected_snapshot)
    root = tmp_path / "approved-theme-root"
    root.mkdir()
    calls = []

    def resolve(selected_root, *, known_at, schema, cancel_callback=None):
        calls.append((selected_root, known_at, schema, callable(cancel_callback)))
        return catalog

    def forbidden_reread(*_args, **_kwargs):
        raise AssertionError("catalog selected.snapshot 不得重讀 manifest")

    monkeypatch.setattr(
        view_module, "resolve_latest_theme_research_snapshot", resolve
    )
    monkeypatch.setattr(
        view_module, "list_theme_research_snapshots", lambda *_args, **_kwargs: catalog
    )
    monkeypatch.setattr(view_module, "read_theme_research_snapshot", forbidden_reread)
    selected_roots = []
    view.catalogRootSelected.connect(selected_roots.append)
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(root),
    )
    try:
        view._choose_catalog_root()
        _wait_until(application, lambda: not view.is_busy())
        assert selected_roots == [root]
        assert view._catalog_entries == catalog.entries
        assert view.catalog_version_combo.count() == 2
        assert "2026-10-19" in view.catalog_version_combo.itemText(1)
        assert view.open_snapshot_button.isEnabled() is False
        view.catalog_version_combo.setCurrentIndex(1)
        assert view.open_snapshot_button.isEnabled()
        assert view.catalog_list_status_label.text() == "已核驗 1 個可讀版本。"
        assert view.load_latest_snapshot()
        _wait_until(application, lambda: not view.is_busy())
        assert calls and calls[0][0] == root
        assert calls[0][1].tzinfo is not None
        assert calls[0][2:] == ("price-v1", True)
        assert view.snapshot is selected_snapshot
        assert "最新可讀 price-v1" in view.status_label.text()
        assert "映射版本：2026-10-16" in view.overview_label.text()
    finally:
        _close(view, application)


def test_version_picker_loads_a_selected_verified_manifest_without_file_dialog(
    monkeypatch, tmp_path
):
    application = QApplication.instance()
    view = view_module.IndustryThemeMapView()
    selected_snapshot = _snapshot("c" * 64)
    catalog = _catalog(selected_snapshot)
    root = tmp_path / "saved-versions"
    root.mkdir()
    read_calls = []

    def list_versions(selected_root, *, known_at, cancel_callback=None):
        assert selected_root == root
        assert known_at.tzinfo is not None
        return catalog

    def read_manifest(path, *, expected_identity_sha256=None, known_at=None):
        read_calls.append((path, expected_identity_sha256))
        return selected_snapshot

    monkeypatch.setattr(view_module, "list_theme_research_snapshots", list_versions)
    monkeypatch.setattr(view_module, "read_theme_research_snapshot", read_manifest)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: pytest.fail("一般選版本不應開啟檔案選擇器"),
    )
    try:
        view.configure_catalog_root(root)
        _wait_until(application, lambda: not view.is_busy())
        view.catalog_version_combo.setCurrentIndex(1)
        view.open_snapshot_button.click()
        _wait_until(application, lambda: not view.is_busy())
        assert read_calls == [(catalog.selected.manifest_path, "c" * 64)]
        assert view.snapshot is selected_snapshot
        assert "已載入明選的本機研究版本" in view.status_label.text()
    finally:
        _close(view, application)


def test_catalog_without_usable_candidate_clears_old_snapshot_and_explains_exit(
    monkeypatch, tmp_path
):
    application = QApplication.instance()
    view = view_module.IndustryThemeMapView()
    old_snapshot = _snapshot()
    rejected = ThemeSnapshotRejection(Path("broken/manifest.json"), "reader拒絕")
    catalog = ThemeSnapshotCatalogResult(
        entries=(),
        rejections=(rejected,),
        candidate_count=1,
        verified_count=0,
        unverified_candidate_count=0,
        limited=False,
        limit_reason=None,
    )
    monkeypatch.setattr(
        view_module,
        "resolve_latest_theme_research_snapshot",
        lambda *_args, **_kwargs: catalog,
    )
    try:
        view.set_snapshot(old_snapshot)
        view.configure_catalog_root(tmp_path)
        assert view.load_latest_snapshot()
        assert view.snapshot is None
        _wait_until(application, lambda: not view.is_busy())
        assert view.snapshot is None
        assert "reader拒絕" in view.status_label.text()
        assert "已核驗清單" in view.status_label.text()
    finally:
        _close(view, application)


def test_catalog_limited_result_does_not_claim_latest(monkeypatch, tmp_path):
    application = QApplication.instance()
    view = view_module.IndustryThemeMapView()
    limited = ThemeSnapshotCatalogResult(
        entries=(),
        rejections=(),
        candidate_count=1,
        verified_count=0,
        unverified_candidate_count=1,
        limited=True,
        limit_reason="測試目錄超過搜尋上限",
    )
    monkeypatch.setattr(
        view_module,
        "resolve_latest_theme_research_snapshot",
        lambda *_args, **_kwargs: limited,
    )
    try:
        view.configure_catalog_root(tmp_path)
        assert view.load_latest_snapshot()
        _wait_until(application, lambda: not view.is_busy())
        assert view.snapshot is None
        assert "未宣稱最新版本" in view.status_label.text()
        assert "已核驗清單" in view.status_label.text()
    finally:
        _close(view, application)


def test_taskworker_cancelled_catalog_result_cannot_restore_stale_snapshot(
    monkeypatch, tmp_path
):
    application = QApplication.instance()
    view = view_module.IndustryThemeMapView()
    stale_snapshot = _snapshot("c" * 64)
    started = threading.Event()
    release = threading.Event()
    cancellation_seen = []

    def delayed_resolve(*_args, cancel_callback=None, **_kwargs):
        started.set()
        assert release.wait(timeout=3)
        cancellation_seen.append(cancel_callback is not None and cancel_callback())
        return _catalog(stale_snapshot)

    monkeypatch.setattr(
        view_module, "resolve_latest_theme_research_snapshot", delayed_resolve
    )
    try:
        view.configure_catalog_root(tmp_path)
        assert view.load_latest_snapshot()
        _wait_until(application, started.is_set)
        worker = view._worker
        assert worker is not None
        assert view.clear_research()
        assert worker.is_cancel_requested()
        release.set()
        _wait_until(application, lambda: not view.is_busy())
        assert cancellation_seen == [True]
        assert view.snapshot is None
        assert "背景讀取已停止" in view.status_label.text()
    finally:
        release.set()
        _close(view, application)


def test_taskworker_catalog_failure_clears_previous_snapshot(monkeypatch, tmp_path):
    application = QApplication.instance()
    view = view_module.IndustryThemeMapView()
    old_snapshot = _snapshot("d" * 64)

    def fail_resolve(*_args, **_kwargs):
        raise ValueError("catalog安全檢查拒絕")

    monkeypatch.setattr(
        view_module, "resolve_latest_theme_research_snapshot", fail_resolve
    )
    try:
        view.set_snapshot(old_snapshot)
        view.configure_catalog_root(tmp_path)
        assert view.load_latest_snapshot()
        assert view.snapshot is None
        _wait_until(application, lambda: not view.is_busy())
        assert view.snapshot is None
        assert "catalog安全檢查拒絕" in view.status_label.text()
        assert "沒有沿用舊版本" in view.status_label.text()
    finally:
        _close(view, application)


def test_explicit_historical_manifest_picker_path_remains_available(monkeypatch, tmp_path):
    application = QApplication.instance()
    view = view_module.IndustryThemeMapView()
    historical = _snapshot("e" * 64)
    manifest = tmp_path / "old-price-manifest.json"
    calls = []

    def read_selected(path, *, expected_identity_sha256=None):
        calls.append((path, expected_identity_sha256))
        return historical

    monkeypatch.setattr(view_module, "read_theme_research_snapshot", read_selected)
    try:
        view.load_snapshot(manifest, expected_identity_sha256="f" * 64)
        _wait_until(application, lambda: not view.is_busy())
        assert calls == [(manifest, "f" * 64)]
        assert view.snapshot is historical
        assert "明選的本機研究版本" in view.status_label.text()
    finally:
        _close(view, application)
