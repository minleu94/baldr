"""官方成對來源的真背景產製按鈕與保存失敗判讀。"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import scripts.refresh_current_market_status_observation as capture_module
import tests.test_selection_market_assignments as market_helpers
import ui_qt.views.daily_market_technical_universe_v4_view as view_module
import ui_qt.views.daily_market_technical_official_disposition_view as official_view_module
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleError,
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
    DailyMarketTechnicalOfficialDispositionBundleWriterV1,
)
from tests.test_daily_market_technical_universe_v4_producer import (
    _write_source, _cohort, _request,
)
from tests.test_daily_market_technical_official_disposition_bundle_v1 import _FrozenDateTime
from tests.test_ui_qt_daily_market_technical_universe_v4_view import app, _wait
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from ui_qt.widgets.daily_market_technical_v4_production_setup import (
    DailyMarketTechnicalV4DeferredProductionSetup, ProductionSetupSummary,
)


@pytest.mark.parametrize("publication_fails", [False, True])
@pytest.mark.parametrize("use_deferred", [False, True])
def test_actual_button_runs_worker_and_reports_saved_or_failed_bundle(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    publication_fails: bool,
    use_deferred: bool,
) -> None:
    database = tmp_path / "synthetic.sqlite"
    _write_source(database, ("1101",))
    source_before = database.read_bytes()
    configured_root = tmp_path / "configured-output"
    scope = ResearchCaptureWriteScope(configured_root, database)
    store_root = scope.root / "technical_universe"
    request = _request(database, _cohort(("1101",)), store_root, scope)
    monkeypatch.setattr(_FrozenDateTime, "fixed_now", request.decision_cutoff - timedelta(seconds=2))
    monkeypatch.setattr(capture_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(market_helpers, "datetime", _FrozenDateTime)
    capture_root = tmp_path / "capture"
    capture_root.mkdir()
    pointer = market_helpers._create_capture(capture_root)
    monkeypatch.setattr(view_module.QFileDialog, "getOpenFileName", lambda *_args: (str(pointer), ""))
    if publication_fails:
        def refuse(*_args: object, **_kwargs: object) -> object:
            raise DailyMarketTechnicalOfficialDispositionBundleError("synthetic_publication_refused")
        monkeypatch.setattr(DailyMarketTechnicalOfficialDispositionBundleWriterV1, "create_from_pins", refuse)
    setup = DailyMarketTechnicalV4DeferredProductionSetup(
        mode="new", source_database=database, configured_output_root=configured_root,
        store_output_root=store_root, cohort=request.cohort, decision_cutoff=request.decision_cutoff,
        summary=ProductionSetupSummary(
            mode="new", source_database=database, configured_output_root=configured_root,
            store_output_root=store_root, cohort=request.cohort, decision_cutoff=request.decision_cutoff),
    )
    view = view_module.DailyMarketTechnicalUniverseV4View(
        store_root, production_request_factory=lambda _entry: setup if use_deferred else request)
    finished: list[object] = []
    published: list[object] = []
    view.productionFinished.connect(finished.append)
    view.officialBundleProduced.connect(published.append)
    view.show()
    try:
        QTest.mouseClick(view.produce_official_button, Qt.MouseButton.LeftButton)
        _wait(app, lambda: bool(finished) and view._worker is None)
        assert len(finished) == 1
        assert database.read_bytes() == source_before
        text = view.official_publication_status.text()
        if publication_fails:
            assert not published
            assert "未完成" in text and "synthetic_publication_refused" in text
            assert "技術收據可另行查詢" in text
        else:
            assert len(published) == 1
            reference = published[0]
            assert reference.output_root in text
            reopened = DailyMarketTechnicalOfficialDispositionBundleReaderV1(reference.output_root).read_exact(
                reference.bundle_identity_sha256, expected_manifest_sha256=reference.manifest_sha256)
            assert tuple(row.stock_code for row in reopened.iter_verified_rows()) == ("1101",)
            # 沿 Manual 的實際資料夾與 catalog 入口接續，不直接塞來源 DTO。
            official = official_view_module.DailyMarketTechnicalOfficialDispositionView(None)
            selected: list[object] = []
            bookmarks: list[object] = []
            official.stockSelected.connect(selected.append)
            official.bookmarkPrepared.connect(bookmarks.append)
            monkeypatch.setattr(official_view_module.QFileDialog, "getExistingDirectory", lambda *_args: reference.output_root)
            official.show()
            try:
                QTest.mouseClick(official.choose_root_button, Qt.MouseButton.LeftButton)
                _wait(app, lambda: official.active_worker is None)
                assert len(official._catalog_entries) == 1
                official.catalog_list.setCurrentRow(0)
                _wait(app, lambda: official.active_worker is None)
                assert official.current_result is not None and official.current_page is not None
                assert official.current_page.counts.population.declared_count == 1
                assert official.current_page.historical_pit_eligible is False
                assert official.select_stock_code("1101")
                origin = official.current_request
                QTest.mouseClick(official.detail_button, Qt.MouseButton.LeftButton)
                assert len(selected) == 1 and selected[0].stock_code == "1101"
                assert official.results_stack.currentIndex() == 1
                QTest.mouseClick(official.back_button, Qt.MouseButton.LeftButton)
                assert official.results_stack.currentIndex() == 0
                assert official.current_request == origin
                QTest.mouseClick(official.bookmark_button, Qt.MouseButton.LeftButton)
                _wait(app, lambda: official.active_worker is None)
                assert len(bookmarks) == 1 and bookmarks[0].selected_stock_code == "1101"
            finally:
                official.begin_shutdown()
                _wait(app, lambda: official.active_worker is None)
                official.close()
    finally:
        view.begin_shutdown()
        _wait(app, lambda: view._worker is None)
        view.close()


def test_cancel_file_selection_never_requests_production(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = Mock()
    view = view_module.DailyMarketTechnicalUniverseV4View(tmp_path, production_request_factory=factory)
    monkeypatch.setattr(view_module.QFileDialog, "getOpenFileName", lambda *_args: ("", ""))
    view.produce_with_official_sources()
    factory.assert_not_called()
    assert view._worker is None
    view.close()


def test_external_read_only_view_does_not_enable_combined_production(app: QApplication, tmp_path: Path) -> None:
    view = view_module.DailyMarketTechnicalUniverseV4View(tmp_path)
    assert not view.produce_official_button.isEnabled()
    view.close()
