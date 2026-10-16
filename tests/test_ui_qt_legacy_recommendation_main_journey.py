"""舊格式推薦在正常 MainWindow 的唯讀選取、下鑽與精確返回。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from data_module.config import TWStockConfig
from tests.test_c1_legacy_query_readiness import _install_legacy_row
from ui_qt.main import MainWindow, _drain_qt_deferred_deletes


def _wait_for(app: QApplication, predicate, *, seconds: float = 15.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    app.processEvents()
    assert predicate()


def _load_legacy_result(window: MainWindow, app: QApplication):
    window.left_navigation.button_for_key("recommendation").click()
    view = window.recommendation_view
    view.refresh_saved_sources_button.click()
    _wait_for(app, lambda: view.saved_source_combo.count() == 2)
    assert "舊格式推薦／唯讀" in view.saved_source_combo.itemText(1)
    view.saved_source_combo.setCurrentIndex(1)
    view.load_saved_result_button.click()
    _wait_for(app, lambda: view._verified_legacy_result_id() == "c1-r016-legacy")
    return view


def test_mainwindow_legacy_source_to_stock_and_exact_return(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "market"
    output_root = tmp_path / "output"
    for name in (
        "PERSONAL_DATA_ROOT", "PERSONAL_WATCHLIST_SOURCE", "PERSONAL_JOURNAL_ROOT",
        "PERSONAL_JOURNAL_MODE", "PERSONAL_STORE_ROOT", "PERSONAL_STORE_MODE",
        "PERSONAL_MODEL_POLICY_PATH", "PAPER_CONTRACT_ARTIFACTS_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("RESEARCH_STATE_ROOT", str(tmp_path / "registry"))
    monkeypatch.setenv("OFFICIAL_CALENDAR_CACHE_PATH", str(tmp_path / "calendar"))
    monkeypatch.setenv("PROFILE", "test")
    runs_dir = TWStockConfig().resolve_output_path("recommendation/runs")
    raw_path, raw_before = _install_legacy_row(runs_dir)
    database_path = runs_dir / "recommendation_runs.db"
    database_sha_before = hashlib.sha256(database_path.read_bytes()).hexdigest()
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    try:
        view = _load_legacy_result(window, app)
        assert view.current_execution is None
        assert view._verified_saved_result_id() == ""
        assert not view.save_result_btn.isVisible()
        assert not view.add_to_watchlist_btn.isVisible()
        view.results_table.selectRow(0)
        assert view.stock_research_btn.isEnabled()
        view.stock_research_btn.click()
        _wait_for(app, lambda: window.left_navigation.current_key() == "stock_research")
        workspace = window.stock_research_workspace
        assert workspace is not None
        context = workspace.report_view.context
        assert context is not None
        assert context.stock_code == "2330"
        assert context.result_id == "c1-r016-legacy"
        assert context.source_workspace == "recommendation"
        assert "歷史可得性未獨立驗證" in context.source_label
        workspace.report_view.return_button.click()
        _wait_for(app, lambda: window.left_navigation.current_key() == "recommendation")
        selection = view.results_table.selectionModel().selectedRows()
        assert len(selection) == 1 and selection[0].row() == 0
        assert view._verified_legacy_result_id() == "c1-r016-legacy"
        assert raw_path.read_bytes() == raw_before
        assert hashlib.sha256(database_path.read_bytes()).hexdigest() == database_sha_before
    finally:
        window.close()
        _wait_for(app, lambda: not window.isVisible())
        _drain_qt_deferred_deletes(app, (window,))
    fresh = subprocess.run(
        (
            sys.executable, "-X", "utf8", "-B", "-m",
            "tests.test_ui_qt_legacy_recommendation_main_journey",
            "--fresh-child", str(raw_path), hashlib.sha256(raw_before).hexdigest(),
            str(database_path), database_sha_before,
        ),
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert fresh.returncode == 0, (fresh.stdout[-3000:], fresh.stderr[-3000:])
    assert "BALDR_LEGACY_FRESH_OK" in fresh.stdout


def _fresh_child(raw_path: Path, raw_sha: str, database_path: Path, database_sha: str) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    try:
        view = _load_legacy_result(window, app)
        assert view.current_execution is None
        assert view._verified_saved_result_id() == ""
        view.results_table.selectRow(0)
        view.stock_research_btn.click()
        _wait_for(app, lambda: window.left_navigation.current_key() == "stock_research")
        workspace = window.stock_research_workspace
        assert workspace is not None
        assert workspace.report_view.context.result_id == "c1-r016-legacy"
        workspace.report_view.return_button.click()
        _wait_for(app, lambda: window.left_navigation.current_key() == "recommendation")
        assert view._verified_legacy_result_id() == "c1-r016-legacy"
        assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == raw_sha
        assert hashlib.sha256(database_path.read_bytes()).hexdigest() == database_sha
        print("BALDR_LEGACY_FRESH_OK")
    finally:
        window.close()
        _wait_for(app, lambda: not window.isVisible())
        _drain_qt_deferred_deletes(app, (window,))


if __name__ == "__main__" and len(sys.argv) == 6 and sys.argv[1] == "--fresh-child":
    _fresh_child(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), sys.argv[5])
